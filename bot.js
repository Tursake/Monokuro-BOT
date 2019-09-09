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

//HTML scraping
const rp = require('request-promise');
const cheerio = require('cheerio');
const imgdownloader = require('image-downloader');
const imgresize = require('sharp');

var currentGame;
var currentImgUrl;
var nextGame;
var nextImgUrl;
var imgDir = __dirname + "/img/";
var imgPath = ["",""];
var imgPathFull = ["",""];
var imgPath1Full = "";
var imgPath2Full = "";
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

async function getInfo(msg){
	
	const parsedBody = await rp(urlOptions);
	
	console.log(imgPath[0]);
	console.log(imgPath[1]);
	
	currentGame = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[0].title);
	nextGame = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].title);
	currentImgUrl = getUrlFromJSON(0, parsedBody);
	//currentImgUrl = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[0].keyImages[3].url);
	//currentImgUrl = currentImgUrl.substring(1,currentImgUrl.length -1);
	nextImgUrl = getUrlFromJSON(1, parsedBody);
	//nextImgUrl = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].keyImages[0].url);
	//nextImgUrl = nextImgUrl.substring(1,nextImgUrl.length -1);
	
	switchDate = JSON.stringify(parsedBody.data.Catalog.catalogOffers.elements[1].
				promotions.upcomingPromotionalOffers[0].promotionalOffers[0].startDate);
	switchDate = switchDate.substring(1,switchDate.length -2);
	switchMoment = moment(switchDate).fromNow();
		
	const imgOptions1 = {
		url: currentImgUrl,
		dest: imgDir
	};

	const imgOptions2 = {
		url: nextImgUrl,
		dest: imgDir
	};

	if(currentImgUrl.substring(currentImgUrl.lastIndexOf("/") +1) != imgPath[0]){
		console.log("Downloading/replacing Current Image");
		
		removeImage(imgPathFull[0]);
		imgPath[0] = "";
		imgPathFull[0] = "";
		
		filenameObj = await imgdownloader.image(imgOptions1);
		filename = filenameObj.filename;
		
		console.log('Saved to', filename)
				imgPathFull[0] = filename;
				imgPath[0] = filename.substring(filename.lastIndexOf("\\") +1);
				resizeImage(imgPathFull[0]);
				
	} else {
		console.log("Correct Current Image exists already!");
	}
  
	if(nextImgUrl.substring(nextImgUrl.lastIndexOf("/") +1) != imgPath[1]){
		console.log("Downloading/replacing Next Image");
		
		removeImage(imgPathFull[1]);
		imgPath[1] = "";
		imgPathFull[1] = "";
		
		filenameObj = await imgdownloader.image(imgOptions2);
		filename = filenameObj.filename;
		
		console.log('Saved to', filename)
				imgPathFull[1] = filename;
				imgPath[1] = filename.substring(filename.lastIndexOf("\\") +1);
				resizeImage(imgPathFull[1]);
				
	} else {
		console.log("Correct Next Image exists already!");
	}
	
	var attachment = new Attachment("./img/" + imgPath[0]);
	msg.channel.send("The current free game on Epic Store is: **" + currentGame + "**", attachment);
	var attachment = new Attachment("./img/" + imgPath[1]);
	msg.channel.send("The next free game is: **" + nextGame +
	"**", attachment);
	msg.channel.send("The next game will be available **" +
	switchMoment + "** (" + switchDate.substring(0,switchDate.indexOf("T")) + ")");
};

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
	
	if(filePath != ""){
		console.log("Deleting image from :" + filePath);
		
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

function resizeImage(filePath){
	console.log("Resizing from path: " + filePath);
	imgresize.cache(false);
	try{
		imgresize(filePath).resize(350).toBuffer(function(err, buffer){
			fs.writeFile(filePath, buffer, function(e){
				console.log("File resized!");
			});
		});
	} catch(err){
		console.error(err);
	}
}

//getInfo();

bot.on('ready', () =>{
	console.log("Bot online!");
});

bot.on('message', msg=>{
	if(msg.content === "!epic"){
		getInfo(msg);
	}
});

bot.login(token);