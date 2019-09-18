const fs = require('fs');
const tokenJSON = require('./token.json');
const token = tokenJSON.token;
const moment = require('moment');
moment().format();

//Bot setup
const {Client, Attachment} = require('discord.js');
const bot = new Client();
/*const token = fs.readFileSync('token.txt', 'utf8', function(err, data) {
		if (err) throw err;
		console.log(data);
		return data;
	});*/
	
var lastMoment;
var alertHours = 24;
var cooldownTime = 600;				// 100ms per tick
var clearTime = 60;					// 100ms per tick

//Guild specifics
var guilds = {};
function guildsSetup(){
	console.log("Parsing bot guild list");
	
	bot.guilds.forEach((guild, index) => {
		if(guilds[guild.id] == null){
			var curr = guild.id
			guilds[curr] = {};
			guilds[curr].setChannel = "";
			guilds[curr].setGuild = guild.name;
			guilds[curr].setID = curr;
			guilds[curr].messagesToPin = ["","",""];
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

//HTML scraping
const rp = require('request-promise');
const cheerio = require('cheerio');
const imgdownloader = require('image-downloader');
const imgresize = require('sharp');

var gameUrls = ["",""];				// Indexes for games
var gameTitles = ["",""];			// 0 = current game on offer
var imgPath = ["",""];				// 1 = upcoming offer

var imgDir = __dirname + "/img/";
var switchMoment = "";
var switchDate = "";

const urlOptions = {
	method: "POST",
	url: "https://graphql.epicgames.com/graphql",
	body:{
		"query":"\n          query promotionsQuery($namespace: String!, $country: String!) {\n            Catalog {\n              catalogOffers(namespace: $namespace, params: {category: \"freegames\", country: $country, sortBy: \"effectiveDate\", sortDir: \"asc\"}) {\n                elements {\n                  title\n                  keyImages {\n                    type\n                    url\n                  }\n                  promotions {\n                    promotionalOffers {\n                      promotionalOffers {\n                        startDate\n                        endDate\n                      }\n                    }\n                    upcomingPromotionalOffers {\n                      promotionalOffers {\n                        startDate\n                        endDate\n                      }\n                    }\n                  }\n                }\n              }\n            }\n          }\n        ",
		"variables":{"namespace":"epic","country":"US"}
	},
	json:true
};

async function getInfo(){
	try{
		const parsedBody = await rp(urlOptions);
		
		if(JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[0].title) != gameTitles[0]){
			clearImageFolder();
		}
		
		gameTitles[0] = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[0].title);
		gameTitles[1] = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].title);
		gameUrls[0] = getUrlFromJSON(0, parsedBody);
		gameUrls[1] = getUrlFromJSON(1, parsedBody);
		
		getSwitchDate(parsedBody);
	}catch(err) {
		console.error(err);
	}
}

async function sendInfo(ID, channel){
	/*let processID = process.hrtime();
	processID = Math.trunc((processID[0] + processID[1])/10000);*/
	
	if(!guilds[ID].operationRunning){
		guilds[ID].operationRunning = true;
		console.log("Task started for server: " + guilds[ID].setGuild + " - #" + guilds[ID].setChannel);
		
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
		
		var attachment = new Attachment("./img/" + imgPath[0]);
		var attachment2 = new Attachment("./img/" + imgPath[1]);
		
		await unpinMessages(guilds[ID].messagesToPin);
		
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
		+ switchMoment + "** (" + switchDate.substring(0,switchDate.indexOf("T")) + ")"))
		.then(toPin => {
			guilds[ID].messagesToPin[2] = toPin;
			pinMessages(guilds[ID].messagesToPin);
		})
		.catch(error => {
			console.error(error);
		});
		
		return false;
	}
};

function pinMessages(messages){
	for(var i = messages.length -1; i >= 0; i--){
		if(messages[i] != ""){
			messages[i].pin();
		}
	}
}

function unpinMessages(messages){
	for(var i = 0; i < messages.length; i++){
		if(messages[i] != ""){
			messages[i].unpin();
		}
	}
}

function clearMessages(guild){
	/*bot.guilds.forEach(guild => {
		let channels = guild.channels.filter(chan => chan.type == "text").array();
		for(let current of channels){
			current.fetchPinnedMessages()
			.then(messages => {
				botMessages = messages.filter(msg => msg.author.bot);
				current.bulkDelete(botMessages);
				console.log("Deleted " + botMessages.length + " messages");
			});
		}
	});*/
	
	let currGuild = bot.guilds.find(foundGuild => foundGuild.name === guild);
	let channels = currGuild.channels.filter(chan => chan.type == "text").array();
	for(let current of channels){
		current.fetchPinnedMessages()
		.then(messages => {
			botMessages = messages.filter(msg => msg.author.name == bot.name);
			current.bulkDelete(botMessages, true);
		});
	}
}

async function downloadImage(index, imgOptions){
	if(gameUrls[index].substring(gameUrls[index].lastIndexOf("/") +1) != imgPath[index]){
		
		if(index == 0){
			console.log(" -> Downloading/replacing image for CURRENT OFFER");
		} else if (index == 1){
			console.log(" -> Downloading/replacing image for UPCOMING OFFER");
		}
		
		/*removeImage(imgDir + imgPath[index]);
		imgPath[index] = "";*/
		
		filenameObj = await imgdownloader.image(imgOptions);
		filename = filenameObj.filename;
		
		console.log('   -> Saved to', filename);
		imgPath[index] = filename.substring(filename.lastIndexOf("\\") +1);
		await resizeImage(imgDir + imgPath[index]);
				
	} else {
		if(index == 0){
			console.log(" -> Correct image for CURRENT OFFER already exists!");
		} else if (index == 1){
			console.log(" -> Correct image for UPCOMING OFFER already exists!");
		}
	}
}

function getUrlFromJSON(index, parsedBody){
	var urlFound = "";
	var parsed = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[index].keyImages);
	
	var obj = JSON.parse(parsed);
	var keys = Object.keys(obj);
	for (var i = 0; i < keys.length; i++) {
		var item = obj[keys[i]];
		
		urlFound = item.url;
	}
	
	return urlFound;
}

function clearImageFolder(filePath){
	/*if(filePath.substring(filePath.lastIndexOf("\\")+1) != ""){
		console.log(" -> Clearing existing images from: " + filePath);
		
		try {
		  fs.unlinkSync(filePath)
		  console.log("   -> Deletion success!");
		} catch(err) {
		  console.error(err)
		}
	} else {
		console.log(" -> Couldn't find image. If first time running script, ignore!");
	}*/
	
	console.log("Clearing image folder");
	
	fs.readdir(imgDir,(err,files) => {
		if(err) throw err;
		
		let count = 0;
		
		for (let file of files){
			if(file != ".gitkeep"){
				let path = imgDir + file;
				fs.unlink(path, err => {
					if(err) throw err;
				});
				count++;
			}
		}
		
		if(count > 0){
		console.log(" -> Deleted (" + count + ") files");
		} else {
		console.log(" -> Folder was already empty");
		}
	});
}

async function resizeImage(filePath){
	console.log("    -> Resizing from path: " + filePath);
	imgresize.cache(false);
	try{
		await imgresize(filePath).resize(350).toBuffer().then(buffer => {
			fs.writeFileSync(filePath, buffer);
			console.log("     -> File resized!");
		});
	} catch(err){
		console.error(err);
	}
}

function getSwitchDate(parsedBody){
	switchDate = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].
				promotions.upcomingPromotionalOffers[0].promotionalOffers[0].startDate);
	switchDate = switchDate.substring(1,switchDate.length -2);
	switchMoment = moment(switchDate).fromNow();
}

function alertUsers(){
	for(var i = 0; i < Object.keys(guilds).length; i++){
		if(guilds[Object.keys(guilds)[i]].alert == false && guilds[Object.keys(guilds)[i]].setChannel != ""){
			let currGuild = bot.guilds.find(foundGuild => foundGuild.name === guilds[Object.keys(guilds)[i]].setGuild);
			let channel = currGuild.channels.find(foundChan => foundChan.name === guilds[Object.keys(guilds)[i]].setChannel);
			channel.send("ALERT! Game selection will change in" +
			moment(switchDate).diff(moment(), 'hours') + " hours");
		}
	}
}

function resetAlerts(){
	for(var i = 0; i < Object.keys(guilds).length; i++){
		guilds[Object.keys(guilds)[i]].alert = false;
	}
}

function deleteSystemMessages(guildName,channelName){
	console.log("Deleting pin messages from server: " + guildName + " - #" + channelName);
	
	let currGuild = bot.guilds.find(foundGuild => foundGuild.name === guildName);
	let channel = currGuild.channels.find(foundChan => foundChan.name === channelName);
	
	channel.fetchMessages({limit:10})
	.then(messages => {
		systemMessages = messages.filter(msg => msg.system);
		channel.bulkDelete(systemMessages, true);
	});
}

async function pollDate(){
	if(switchDate != "" && switchMoment != ""){
		
		for(var i = 0; i < Object.keys(guilds).length; i++){
			if(guilds[Object.keys(guilds)[i]].onCooldown){
				guilds[Object.keys(guilds)[i]].cooldown--;
				if(guilds[Object.keys(guilds)[i]].cooldown <= 0){
					guilds[Object.keys(guilds)[i]].onCooldown = false;
					console.log("Cooldown finished for server: " + guilds[Object.keys(guilds)[i]].setGuild + " - #" + guilds[Object.keys(guilds)[i]].setChannel);
				}
			}
			
			if(guilds[Object.keys(guilds)[i]].clearSystemMessages){
				guilds[Object.keys(guilds)[i]].systemMessageClearTimer--;
				if(guilds[Object.keys(guilds)[i]].systemMessageClearTimer <= 0){
					guilds[Object.keys(guilds)[i]].clearSystemMessages = false;
					if(guilds[Object.keys(guilds)[i]].setChannel != ""){
						deleteSystemMessages(guilds[Object.keys(guilds)[i]].setGuild,guilds[Object.keys(guilds)[i]].setChannel);
					}
				}
			}
			
			if(lastMoment != null){
				if(moment().dayOfYear() > lastMoment || (moment().dayOfYear() == 1 && lastMoment == 365)){
					console.log("Date changed, updating info");
					let currGuild = bot.guilds.find(foundGuild => foundGuild.name === guilds[Object.keys(guilds)[i]].setGuild);
					let channel = currGuild.channels.find(foundChan => foundChan.name === guilds[Object.keys(guilds)[i]].setChannel);
					sendInfo(guilds[Object.keys(guilds)[i]].setID,channel).then(result => {
						console.log("Task done!");
						guilds[Object.keys(guilds)[i]].operationRunning = result;
						guilds[Object.keys(guilds)[i]].cooldown = cooldownTime;
						guilds[Object.keys(guilds)[i]].systemMessageClearTimer = clearTime;
						guilds[Object.keys(guilds)[i]].clearSystemMessages = true;
						onCooldown = true;
					})
				}
			}
			
			lastMoment = moment().dayOfYear();
		}
		
		if(moment(switchDate).diff(moment(), 'hours') < alertHours){
			alertUsers();
		}  else if (moment(switchDate).diff(moment(), 'days') < 0){
			resetAlerts();
		}
	}
}

bot.on('ready', () =>{
	console.log("Bot online!");
	guildsSetup();
});

bot.on('guildCreate', function(guild){
    console.log("The bot joins a guild");
	guildsSetup();
});

bot.on('guildDelete', function(guild){
	delete guilds[guild.id];
    console.log("The bot leaves guild: " + guild.name);
});

bot.on('message', msg=>{
	
	let isAdmin = msg.channel.permissionsFor(msg.member).has("ADMINISTRATOR", true);
	
	if(msg.author.username != "Monokuro"){
		if(msg.content === "!epic" && !guilds[msg.guild.id].operationRunning
		&& msg.channel.name === guilds[msg.guild.id].setChannel){											// Used to manually fetch current and upcoming offers
			if(guilds[msg.guild.id].onCooldown){
				msg.react('❌');
				console.log("Task rejected, another one is already running on the same server!");
			} else {
				msg.react('✅');
				sendInfo(msg.guild.id,msg.channel).then(result => {
					console.log("Task done!");
					guilds[msg.guild.id].operationRunning = result;
					guilds[msg.guild.id].cooldown = cooldownTime;
					guilds[msg.guild.id].systemMessageClearTimer = clearTime;
					guilds[msg.guild.id].clearSystemMessages = true;
					guilds[msg.guild.id].onCooldown = true;
				})
			}
		} else if (msg.content === "!set" && isAdmin && guilds[msg.guild.id] != msg.channel.name){			// Used to set desired channel for bot
			guilds[msg.guild.id].setChannel = msg.channel.name;
			msg.channel.send("Operating channel set to: **#" + guilds[msg.guild.id].setChannel + "**");
			clearMessages(msg.guild.name);
			sendInfo(msg.guild.id,msg.channel).then(result => {
				console.log("Task done!");
				guilds[msg.guild.id].operationRunning = result;
				guilds[msg.guild.id].cooldown = cooldownTime;
				guilds[msg.guild.id].systemMessageClearTimer = clearTime;
				guilds[msg.guild.id].clearSystemMessages = true;
				guilds[msg.guild.id].onCooldown = true;
			})
		} else if(msg.content === "!epic"){
			msg.react('❌');
			console.log("Task rejected, another one is already running or operating channel not set by an admin!");
		}
	}
});

/* MAIN BLOCK */

bot.login(token);
getInfo();
setInterval(pollDate, 100);

/* END MAIN BLOCK */
