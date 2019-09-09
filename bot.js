const fs = require('fs');
const moment = require('moment');
moment().format();

//Bot setup
const {Client, Attachment} = require('discord.js');
const bot = new Client();
const token = fs.readFileSync('token.txt', 'utf8', function(err, data) {
		if (err) throw err;
		console.log(data);
		return data;
	});
	
var operationRunning = false;

//HTML scraping
const rp = require('request-promise');
const cheerio = require('cheerio');
const imgdownloader = require('image-downloader');
const imgresize = require('sharp');

var gameUrls = ["",""];				// Indexes for games
var gameTitles = ["",""];			// 0 = current game on offer
var imgPath = ["",""];				// 1 = upcoming offer

var imgDir = __dirname + "\\img\\";
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

async function getInfo(msg, send){
	
	console.log("Task started!");
	
	const parsedBody = await rp(urlOptions);
	
	console.log(imgPath[0]);
	console.log(imgPath[1]);
	
	gameTitles[0] = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[0].title);
	gameTitles[1] = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].title);
	gameUrls[0] = getUrlFromJSON(0, parsedBody);
	gameUrls[1] = getUrlFromJSON(1, parsedBody);
	
	getSwitchDate(parsedBody);
		
	if(send){
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
		msg.channel.send("The current free game on Epic Store is: **"
		+ gameTitles[0] + "**", attachment).
		then(() => msg.channel.send("The next free game is: **" + gameTitles[1]
		+ "**", attachment2)).
		then(() => msg.channel.send("The next game will be available **"
		+ switchMoment + "** (" + switchDate.substring(0,switchDate.indexOf("T")) + ")"))
		.catch(error => {
			console.error(error);
		});
		
		var running = false;
	}
	
	return running;
};

async function downloadImage(index, imgOptions){
	if(gameUrls[index].substring(gameUrls[index].lastIndexOf("/") +1) != imgPath[index]){
		
		if(index == 1){
			console.log("Downloading/replacing image for CURRENT OFFER");
		} else if (index == 2){
			console.log("Downloading/replacing image for UPCOMING OFFER");
		}
		
		removeImage(imgDir + imgPath[index]);
		imgPath[index] = "";
		
		filenameObj = await imgdownloader.image(imgOptions);
		filename = filenameObj.filename;
		
		console.log('Saved to', filename);
		imgPath[index] = filename.substring(filename.lastIndexOf("\\") +1);
		await resizeImage(imgDir + imgPath[index]);
				
	} else {
		if(index == 1){
			console.log("Correct image for CURRENT OFFER already exists!");
		} else if (index == 2){
			console.log("Correct image for UPCOMING OFFER already exists!");
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
		
		/*if(item.url != ""){
			console.log(item.url);
			urlFound = item.url;
			break;
		}*/
		
		urlFound = item.url;
	}
	
	return urlFound;
}

function removeImage(filePath){
	
	if(filePath.substring(filePath.lastIndexOf("\\")+1) != ""){
		console.log("Deleting image from: " + filePath);
		
		try {
		  fs.unlinkSync(filePath)
		  console.log("Deletion success!");
		} catch(err) {
		  console.error(err)
		}
	} else {
		console.log("Couldn't find image. If first time running script, ignore!");
	}
}

async function resizeImage(filePath){
	console.log("Resizing from path: " + filePath);
	imgresize.cache(false);
	try{
		await imgresize(filePath).resize(350).toBuffer().then(buffer => {
			fs.writeFileSync(filePath, buffer);
			console.log("File resized!");
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

async function pollDate(){
	if(switchDate != "" && switchMoment != ""){
		console.log(moment(switchDate).diff(moment(), 'days', true));
		if(moment(switchDate).diff(moment(), 'days') < 1){
			console.log("ALERT");
		}
	}
}

bot.on('ready', () =>{
	console.log("Bot online!");
});

bot.on('message', msg=>{
	if(msg.author.username != "Monokuro"){
		if(msg.content === "!epic" && !operationRunning){
			operationRunning = true;
			getInfo(msg,1).then(result => {
				console.log("Task done!");
				operationRunning = result;
			})
		} else {
			console.log("Task rejected, another one is already running!");
		}
	}
});

/* MAIN BLOCK */

bot.login(token);
getInfo("",0);
setInterval(pollDate, 1000);

/* END MAIN BLOCK */
