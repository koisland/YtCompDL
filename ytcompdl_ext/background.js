//async function run_py_comp_dl() {
//    try {
//    }
//    catch (err) {
//    console.error()
//    }
//}

function open_page() {
    browser.tabs.create({
        url: "http://ytcompdl-env.eba-hm7kwxej.us-west-2.elasticbeanstalk.com/"
        });
}

browser.browserAction.onClicked.addListener(open_page);