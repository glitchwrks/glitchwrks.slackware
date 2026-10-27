# glitchwrks\.slackware Release Notes

**Topics**

- <a href="#v0-1-0">v0\.1\.0</a>
    - <a href="#release-summary">Release Summary</a>
    - <a href="#new-plugins">New Plugins</a>
        - <a href="#lookup">Lookup</a>
    - <a href="#new-modules">New Modules</a>

<a id="v0-1-0"></a>
## v0\.1\.0

<a id="release-summary"></a>
### Release Summary

Initial release\. Dependency\-resolving package installs from repositories that publish <code>PACKAGE REQUIRED\:</code> metadata\, such as those built by slackrepo\, and rc\.d service management\. The plugins were previously maintained internally at Glitch Works\, LLC\.

<a id="new-plugins"></a>
### New Plugins

<a id="lookup"></a>
#### Lookup

* glitchwrks\.slackware\.slackdeps \- Expand Slackware packages to their full dependency set\.

<a id="new-modules"></a>
### New Modules

* glitchwrks\.slackware\.slackpkg \- Install Slackware packages with dependencies resolved from repository metadata\.
* glitchwrks\.slackware\.slackware\_service \- Manage Slackware services controlled by /etc/rc\.d scripts\.
