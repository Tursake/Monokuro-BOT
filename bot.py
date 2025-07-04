const fs = require('fs');
const tokenJSON = require('./token.json');
const token = tokenJSON.token;
const moment = require('moment');
moment().format();

// Bot setup
const { Client, MessageAttachment } = require('discord.js');
const bot = new Client();

var lastMoment;
var alertHours = 24;
var cooldownTime = 600; // 100ms per tick
var clearTime = 60;     // 100ms per tick

// Guild specifics
var guilds = {};
function guildsSetup() {
  console.log("Parsing bot guild list");

  bot.guilds.cache.forEach((guild) => {
    if (!guilds[guild.id]) {
      const curr = guild.id;
      guilds[curr] = {};
      guilds[curr].setChannel = "";
      guilds[curr].setGuild = guild.name;
      guilds[curr].setID = curr;
      guilds[curr].messagesToPin = ["", "", ""];
      guilds[curr].alerted = false;
      guilds[curr].systemMessageClearTimer = 0;
      guilds[curr].clearSystemMessages = false;
      guilds[curr].cooldown = 0;
      guilds[curr].onCooldown = false;
      guilds[curr].operationRunning = false;
      console.log(" -> Found server " + guilds[curr].setGuild);
    }
  });
}

// HTML scraping
const rp = require('request-promise');
const cheerio = require('cheerio');
const imgdownloader = require('image-downloader');
const imgresize = require('sharp');

var gameUrls = ["", ""];     // Indexes for games
var gameTitles = ["", ""];   // 0 = current game on offer
var imgPath = ["", ""];      // 1 = upcoming offer

var imgDir = __dirname + "/img/";
var switchMoment = "";
var switchDate = "";

const urlOptions = {
  method: "POST",
  url: "https://graphql.epicgames.com/graphql",
  body: {
    "query": "\n          query promotionsQuery($namespace: String!, $country: String!) {\n            Catalog {\n              catalogOffers(namespace: $namespace, params: {category: \"freegames\", country: $country, sortBy: \"effectiveDate\", sortDir: \"asc\"}) {\n                elements {\n                  title\n                  keyImages {\n                    type\n                    url\n                  }\n                  promotions {\n                    promotionalOffers {\n                      promotionalOffers {\n                        startDate\n                        endDate\n                      }\n                    }\n                    upcomingPromotionalOffers {\n                      promotionalOffers {\n                        startDate\n                        endDate\n                      }\n                    }\n                  }\n                }\n              }\n            }\n          }\n        ",
    "variables": { "namespace": "epic", "country": "US" }
  },
  json: true
};

async function getInfo() {
  try {
    const parsedBody = await rp(urlOptions);

    if (JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[0].title) != gameTitles[0]) {
      clearImageFolder();
    }

    gameTitles[0] = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[0].title);
    gameTitles[1] = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].title);
    gameUrls[0] = getUrlFromJSON(0, parsedBody);
    gameUrls[1] = getUrlFromJSON(1, parsedBody);

    getSwitchDate(parsedBody);
  } catch (err) {
    console.error(err);
  }
}

async function sendInfo(ID, channel) {
  if (!guilds[ID].operationRunning) {
    guilds[ID].operationRunning = true;
    console.log("Task started for server: " +
      guilds[ID].setGuild + " - #" + guilds[ID].setChannel);

    await getInfo();

    const imgOptions1 = {
      url: gameUrls[0],
      dest: imgDir
    };

    const imgOptions2 = {
      url: gameUrls[1],
      dest: imgDir
    };

    await downloadImage(0, imgOptions1);
    await downloadImage(1, imgOptions2);

    let attachment = new MessageAttachment(imgDir + imgPath[0]);
    let attachment2 = new MessageAttachment(imgDir + imgPath[1]);

    await unpinMessages(guilds[ID].messagesToPin);

    let hours = moment(switchDate).diff(moment(), 'hours') % 24;

    channel.send("The current free game on Epic Store is: **"
      + gameTitles[0] + "**", attachment)
      .then(toPin => {
        guilds[ID].messagesToPin[0] = toPin;
      })
      .then(() => channel.send("The next free game is: **" + gameTitles[1]
        + "**", attachment2))
      .then(toPin => {
        guilds[ID].messagesToPin[1] = toPin;
      })
      .then(() => channel.send("The next game will be available **"
        + switchMoment + " and " + hours + " hours** ("
        + switchDate.substring(0, switchDate.indexOf("T")) + ")"))
      .then(toPin => {
        guilds[ID].messagesToPin[2] = toPin;
        pinMessages(guilds[ID].messagesToPin);
      })
      .catch(error => {
        console.error(error);
      });

    return false;
  }
}

function pinMessages(messages) {
  for (var i = messages.length - 1; i >= 0; i--) {
    if (messages[i] !== "") {
      messages[i].pin();
    }
  }
}

function unpinMessages(messages) {
  for (var i = 0; i < messages.length; i++) {
    if (messages[i] !== "") {
      messages[i].unpin();
    }
  }
}

function clearMessages(guildName) {
  let currGuild = bot.guilds.cache.find(foundGuild => foundGuild.name === guildName);
  if (!currGuild) return;
  let channels = currGuild.channels.cache.filter(chan => chan.type === "text");
  channels.forEach(channel => {
    channel.messages.fetchPinned()
      .then(messages => {
        const botMessages = messages.filter(msg => msg.author.username === bot.user.username);
        channel.bulkDelete(botMessages, true).catch(console.error);
      });
  });
}

async function downloadImage(index, imgOptions) {
  if (gameUrls[index].substring(gameUrls[index].lastIndexOf("/") + 1) !== imgPath[index]) {

    if (index === 0) {
      console.log(" -> Downloading/replacing image for CURRENT OFFER");
    } else if (index === 1) {
      console.log(" -> Downloading/replacing image for UPCOMING OFFER");
    }

    let filenameObj = await imgdownloader.image(imgOptions);
    let filename = filenameObj.filename;

    console.log('   -> Saved to', filename);
    imgPath[index] = filename.substring(filename.lastIndexOf("\\") + 1);
    if (process.platform === "win32") {
      await resizeImage(imgDir + imgPath[index]);
    } else {
      await resizeImage(imgPath[index]);
    }

  } else {
    if (index === 0) {
      console.log(" -> Correct image for CURRENT OFFER already exists!");
    } else if (index === 1) {
      console.log(" -> Correct image for UPCOMING OFFER already exists!");
    }
  }
}

function getUrlFromJSON(index, parsedBody) {
  var urlFound = "";
  var parsed = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[index].keyImages);
  var obj = JSON.parse(parsed);
  var keys = Object.keys(obj);
  for (var i = 0; i < keys.length; i++) {
    var item = obj[keys[i]];

    if (item.type === "ComingSoon") {
      urlFound = item.url;
      break;
    }
  }

  return urlFound;
}

function clearImageFolder() {
  console.log("Clearing image folder");

  fs.readdir(imgDir, (err, files) => {
    if (err) throw err;

    let count = 0;

    for (let file of files) {
      if (file !== ".gitkeep") {
        let path = imgDir + file;
        fs.unlink(path, err => {
          if (err) throw err;
        });
        count++;
      }
    }

    if (count > 0) {
      console.log(" -> Deleted (" + count + ") files");
    } else {
      console.log(" -> Folder was already empty");
    }
  });
}

async function resizeImage(filePath) {
  console.log("    -> Resizing from path: " + filePath);
  imgresize.cache(false);
  try {
    await imgresize(filePath).resize(350).toBuffer().then(buffer => {
      fs.writeFileSync(filePath, buffer);
      console.log("     -> File resized!");
    });
  } catch (err) {
    console.error(err);
  }
}

function getSwitchDate(parsedBody) {
  switchDate = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].
    promotions.upcomingPromotionalOffers[0].promotionalOffers[0].startDate);
  switchDate = switchDate.substring(1, switchDate.length - 2);
  switchMoment = moment(switchDate).fromNow();
}

function alertUsers() {
  for (var i = 0; i < Object.keys(guilds).length; i++) {
    if (!guilds[Object.keys(guilds)[i]].alerted && guilds[Object.keys(guilds)[i]].setChannel !== "") {
      let currGuild = bot.guilds.cache.find(foundGuild => foundGuild.name === guilds[Object.keys(guilds)[i]].setGuild);
      if (!currGuild) continue;
      let currChannel = currGuild.channels.cache.find(foundChan => foundChan.name === guilds[Object.keys(guilds)[i]].setChannel);
      if (!currChannel) continue;
      currChannel.send("ALERT! Game selection will change in " +
        moment(switchDate).diff(moment(), 'hours') + " hours");
      guilds[Object.keys(guilds)[i]].alerted = true;
    }
  }
}

function resetAlerts() {
  for (var i = 0; i < Object.keys(guilds).length; i++) {
    guilds[Object.keys(guilds)[i]].alerted = false;
  }
}

function deleteSystemMessages(guildName, channelName) {
  console.log("Deleting pin messages from server: " + guildName + " - #" + channelName);

  let currGuild = bot.guilds.cache.find(foundGuild => foundGuild.name === guildName);
  if (!currGuild) return;
  let channel = currGuild.channels.cache.find(foundChan => foundChan.name === channelName);
  if (!channel) return;

  channel.messages.fetch({ limit: 10 })
    .then(messages => {
      const systemMessages = messages.filter(msg => msg.system);
      channel.bulkDelete(systemMessages, true).catch(console.error);
    });
}

async function pollDate() {

  let dateChangedAlert = false;

  if (switchDate !== "" && switchMoment !== "") {

    for (var i = 0; i < Object.keys(guilds).length; i++) {
      let guildKey = Object.keys(guilds)[i];
      if (guilds[guildKey].onCooldown) {
        guilds[guildKey].cooldown--;
        if (guilds[guildKey].cooldown <= 0) {
          guilds[guildKey].onCooldown = false;
          console.log("Cooldown finished for server: "
            + guilds[guildKey].setGuild + " - #"
            + guilds[guildKey].setChannel);
        }
      }

      if (guilds[guildKey].clearSystemMessages) {
        guilds[guildKey].systemMessageClearTimer--;
        if (guilds[guildKey].systemMessageClearTimer <= 0) {
          guilds[guildKey].clearSystemMessages = false;
          if (guilds[guildKey].setChannel !== "") {
            deleteSystemMessages(guilds[guildKey].setGuild, guilds[guildKey].setChannel);
          }
        }
      }

      if (lastMoment != null) {
        if (moment().dayOfYear() > lastMoment || (moment().dayOfYear() === 1 && lastMoment === 365)) {
          if (!dateChangedAlert) console.log("Date changed, updating info");
          dateChangedAlert = true;
          let currGuild = bot.guilds.cache.find(foundGuild =>
            foundGuild.name === guilds[guildKey].setGuild);
          if (!currGuild) continue;
          let channel = currGuild.channels.cache.find(foundChan =>
            foundChan.name === guilds[guildKey].setChannel);
          if (channel != null) {  // Only run if bot has actually been !set
            let hours = moment(switchDate).diff(moment(), 'hours') % 24;
            if (guilds[currGuild.id] && guilds[currGuild.id].messagesToPin[2]) {
              guilds[currGuild.id].messagesToPin[2].edit("The next game will be available **" + switchMoment + " and " + hours + " hours** (" + switchDate.substring(0, switchDate.indexOf("T")) + ")");
            }
            /* Uncomment if you want to auto-send info on date change
            sendInfo(guilds[guildKey].setID, channel).then(result => {
              console.log("Task done!");
              guilds[guildKey].operationRunning = result;
              guilds[guildKey].cooldown = cooldownTime;
              guilds[guildKey].systemMessageClearTimer = clearTime;
              guilds[guildKey].clearSystemMessages = true;
              guilds[guildKey].onCooldown = true;
            });
            */
          }
        }
      }

    }

    lastMoment = moment().dayOfYear();

    if (moment(switchDate).diff(moment(), 'hours') < alertHours) {
      alertUsers();
    } else if (moment(switchDate).diff(moment(), 'days') < 0) {
      resetAlerts();
    }
  }
}

bot.on('ready', () => {
  console.log("Bot online!");
  guildsSetup();
});

bot.on('guildCreate', (guild) => {
  console.log("New guild joined: " + guild.name);
  guildsSetup();
});

bot.on('message', async (message) => {
  if (message.author.bot) return;

  if (message.content === "!set") {
    let guildID = message.guild.id;
    guilds[guildID].setChannel = message.channel.name;
    await message.channel.send("Operating channel set to: **#" + message.channel.name + "**");
    sendInfo(guildID, message.channel);
  }
});

bot.login(token);

setInterval(pollDate, 100);
