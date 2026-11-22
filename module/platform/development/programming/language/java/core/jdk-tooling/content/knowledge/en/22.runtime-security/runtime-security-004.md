# Runtime Policy in Java

**Runtime policy** is a set of rules that determines which actions a program is allowed to perform while running. In the Java ecosystem, this term was historically used for Java Security Manager policy files: files declaring permissions for reading/writing files, opening network connections, reading system properties, and other sensitive operations that code was permitted to execute.

However, it is important to distinguish between two generations:

- **Security Manager–style policy files**: a mechanism for granting permissions to each code source using permissions such as FilePermission, SocketPermission, and PropertyPermission. This mechanism still works on older JDKs, but has been permanently disabled since JDK 24.
- **Modern JDK security properties**: configuration for cryptographic providers, restricted algorithms, TLS, keystores, and runtime security components. This configuration is still supported in JDK 26, but it is not a sandbox mechanism to restrict file reading or network access for individual classes.

When designing security for modern applications, you need to combine JDK security configuration, application-layer authorization, and operating system or container isolation mechanisms. Do not build new implementations based on Security Manager.

## 1. What problem does a runtime policy solve?

An application can perform many actions at runtime:

- Reading or writing files.
- Opening network connections.
- Reading system properties.
- Creating class loaders.
- Accessing certain sensitive resources.
- Performing operations based on user roles or permissions.

A good runtime policy clearly defines which actions are allowed, who is allowed to perform them, and which resources are within the permitted scope.

For example, a reporting service might need:

| Component | Requirement |
|---|---|
| Report service | Read report data |
| Export worker | Write files to the export directory |
| Notification client | Connect to the mail gateway |
| Non-admin user | Not allowed to delete reports |

In the legacy Security Manager model, certain resource access rights were controlled by JVM permissions. In modern applications, business permissions such as viewing or deleting reports should typically be checked by the application itself; process permissions for files and networks should be restricted using OS/container controls.

## 2. History and status by JDK release

Security Manager was used to enforce access-control policies on code running in the JVM. Oracle began deprecating this mechanism for removal in JDK 17 via JEP 411. JDK 24 took the next step: permanently disabling Security Manager via JEP 486.

| JDK release | Security Manager status | Meaning for policy files |
|---|---|---|
| JDK 8 and earlier | Supported | Policy files can grant permissions when Security Manager is enabled |
| JDK 9–16 | Supported | Policy files and Security Manager can be configured |
| JDK 17–23 | Deprecated for removal | The legacy mechanism can still work, but applications need a migration plan |
| JDK 24 and later | Permanently disabled | Security Manager cannot be enabled; legacy policy files no longer enforce access control |

JDK 24 and later do not allow enabling Security Manager at startup. Commands like the following cause the JVM to fail initialization and exit:

~~~bash
java -Djava.security.manager -jar app.jar
~~~

The following forms are also invalid on JDK 24 and later:

~~~bash
java -Djava.security.manager=allow -jar app.jar
java -Djava.security.manager=default -jar app.jar
java -Djava.security.manager=com.acme.CustomSecurityManager -jar app.jar
~~~

Calling System.setSecurityManager(...) at runtime also throws UnsupportedOperationException. There is no JVM flag to restore this mechanism in JDK 24+.

**Takeaway when reading older documentation:** examples using SecurityManager, java.security.policy, Policy.setPolicy, or permission-based sandboxes must be marked as legacy. Do not copy commands from JDK 8/11/17 into JDK 24/25/26 production configurations without checking support status.

## 3. How did legacy policy files work?

In the legacy model, a Policy implementation determined the set of permissions granted to a CodeSource and could combine it with a Principal. Security Manager checked permissions when code performed certain sensitive operations.

A policy file typically contained the following components:

- **grant**: opens a permission-granting block.
- **codeBase**: URL specifying the location of the code being granted permissions.
- **signedBy**: signer alias used when binding code to a certificate in a keystore.
- **Principal**: identity that can be used in policy-based authorization.
- **permission**: permission type, target resource, and allowed actions.

General structure:

~~~text
grant [signedBy "signer"] [, codeBase "URL"] {
    permission permission.class "target", "actions";
};
~~~

Example policy file for a legacy application:

~~~java
grant codeBase "file:/opt/acme/app.jar" {
    permission java.io.FilePermission
        "/var/acme/data/-", "read,write";

    permission java.net.SocketPermission
        "api.example.com:443", "connect,resolve";

    permission java.util.PropertyPermission
        "user.timezone", "read";
};
~~~

Meaning:

- Code in app.jar is allowed to read and write files in the /var/acme/data directory tree.
- Code is allowed to connect to api.example.com on port 443 and resolve hostnames.
- Code is allowed to read the user.timezone system property.
- Other permissions are not granted by this grant block.

This is the traditional policy file syntax, which is only meaningful when Security Manager and the Policy mechanism are supported. Do not use this file to sandbox applications on JDK 24+.

## 4. Permission types in legacy policy files

Legacy policy files use subclasses of java.security.Permission to represent permission types.

| Permission | Resource or action | Example actions |
|---|---|---|
| java.io.FilePermission | Files and directories | read, write, execute, delete, readlink |
| java.net.SocketPermission | Socket connections | connect, listen, accept, resolve |
| java.util.PropertyPermission | System properties | read, write |
| java.lang.RuntimePermission | Certain sensitive runtime operations | createClassLoader, getClassLoader |
| java.lang.reflect.ReflectPermission | Sensitive reflection operations | suppressAccessChecks |
| java.security.SecurityPermission | Legacy security API administrative operations | getPolicy, setPolicy |

### FilePermission

Example:

~~~java
permission java.io.FilePermission
    "/var/acme/data/report.csv", "read";
~~~

Specifies a concrete file and the read action.

Common path patterns:

| Target | Scope |
|---|---|
| /var/acme/data/report.csv | A single specific file |
| /var/acme/data/* | Files directly inside the directory |
| /var/acme/data/- | Files in the directory and all subdirectories |
| <<ALL FILES>> | All files; very broad permission |

Avoid granting <<ALL FILES>> to regular applications. Restrict paths to the exact data directories required.

### SocketPermission

Example:

~~~java
permission java.net.SocketPermission
    "api.example.com:443", "connect,resolve";
~~~

This permission allows connecting to the specified hostname and port. Do not grant permission to connect to all hosts if the application only needs a few endpoints.

### PropertyPermission

Example:

~~~java
permission java.util.PropertyPermission
    "user.home", "read";
~~~

You can grant read or write access to a system property. Do not grant read/write access to all properties if the application only needs a specific configuration value.

### RuntimePermission

RuntimePermission controls certain special runtime operations in the legacy Security Manager model, such as createClassLoader or setContextClassLoader. These are sensitive permissions; grant them only when the application truly needs them and you understand the impact.

## 5. Configuring policy files in JDK 17–23

This section is only for maintaining or inspecting legacy systems still running JDK 17 through JDK 23. Security Manager was deprecated for removal during this period.

### Enabling Security Manager and loading an additional policy

~~~bash
java -Djava.security.manager -Djava.security.policy=/etc/acme/app.policy -jar app.jar
~~~

With a single equals sign in the java.security.policy value, the specified policy file is loaded in addition to the default policy files configured in java.security.

### Replacing the default policy

~~~bash
java -Djava.security.manager -Djava.security.policy==/etc/acme/app.policy -jar app.jar
~~~

Two equals signs instruct the JVM to use the specified policy file instead of the default configured policy files. This can remove default permissions that the JDK needs, leading to runtime errors. Only use this when you fully understand the entire policy being replaced.

### Default policy locations before JDK 24

In older JDKs that still supported Security Manager, default locations typically included:

| Type | Location |
|---|---|
| System policy | $JAVA_HOME/conf/security/java.policy |
| User policy | ~/.java.policy |
| Policy location configuration | Security properties of the form policy.url.n in java.security |

The system policy is loaded first, and then the user policy is appended. Configuration can be customized via the corresponding JDK's security properties.

Do not confuse the java.policy file with the java.security file. The java.policy file contains grants/permissions for the legacy mechanism; the java.security file contains the JDK's security properties.

## 6. Limitations of legacy policy files

A policy file does not enable Security Manager on its own. In older JDKs, the application had to run with Security Manager installed for permission checks to be enforced.

Some limitations of the legacy model:

- Permissions are only checked at points where the Java Platform or the application performs a security check.
- Incorrect policies or overly broad grants can defeat the purpose of the sandbox.
- Reflection, native code, third-party libraries, and special execution paths require separate evaluation.
- Maintaining permissions becomes complex when an application has many dependencies.
- Security Manager incurs compatibility and operational overhead, which is one of the reasons it was deprecated and then disabled.

The presence of a policy file on disk does not prove that the runtime is enforcing it. You must verify the JDK version, JVM startup flags, and Security Manager status before drawing conclusions.

## 7. What changed in JDK 24+?

JDK 24 permanently disables Security Manager. Changes directly related to runtime policy include:

| Component | Behavior on JDK 24+ |
|---|---|
| java -Djava.security.manager | JVM fails with an error and exits |
| System.setSecurityManager(...) | Throws UnsupportedOperationException |
| System.getSecurityManager() | Always returns null |
| java.security.policy | No longer supported |
| $JAVA_HOME/conf/security/java.policy | System policy file removed |
| java.security.Policy.setPolicy(...) | Throws UnsupportedOperationException |
| java.security.Policy.getPolicy() | Returns a Policy that grants no permissions |
| AccessController.doPrivileged(...) | Executes the action immediately without creating a legacy privilege boundary |
| SecurityManager.check* | Legacy permission enforcement mechanism no longer exists |

The Policy class in java.security was deprecated for removal since 17. The JDK 26 API explicitly states that Policy is only useful when a Security Manager is present; there is no direct replacement for this class.

This means:

- Do not use java.security.policy to restrict file/network access on JDK 24+.
- Do not use Policy.setPolicy to install a custom permission model.
- Do not treat AccessController.doPrivileged as a sandbox boundary.
- Do not rely on SecurityManager.checkPermission to block code actions.
- Do not use the module system or class loaders as an equivalent replacement for Security Manager.

If an application still depends on the legacy mechanism, you must migrate its security design before upgrading the JDK.

## 8. Distinguishing three types of policy in modern Java

The term "policy" can be confusing. In modern Java applications, clearly separate the following three layers:

| Policy type | Where configured | Current role |
|---|---|---|
| Legacy Java permission policy | java.policy and java.security.policy | Only relevant on older JDKs that still have Security Manager |
| JDK security properties | conf/security/java.security | Configures providers, algorithms, TLS, and JDK security components |
| Application authorization policy | Application code, database, or policy service | Determines which user/role is allowed to perform which business action |

Examples:

- FilePermission belongs to the legacy permission policy.
- jdk.tls.disabledAlgorithms belongs to JDK security properties.
- The rule "REPORT_READER can view reports but cannot delete them" belongs to the application authorization policy.

One type of policy does not replace another. Security properties are not a file for granting file read/write permissions; application authorization does not replace OS-level network isolation.

## 9. Modern JDK security properties file

JDK 26 still uses the master security properties file:

~~~text
$JAVA_HOME/conf/security/java.security
~~~

This file configures the security properties that the JDK reads at startup or when the corresponding security component is initialized.

Common configuration groups:

| Group | Example property | Purpose |
|---|---|---|
| Security providers | security.provider.n | Register and order cryptographic providers |
| Certificate path | jdk.certpath.disabledAlgorithms | Restrict algorithms and key sizes when verifying certificate chains |
| TLS/DTLS | jdk.tls.disabledAlgorithms | Restrict TLS protocols, cipher suites, and algorithms |
| Cryptographic services | jdk.crypto.disabledAlgorithms | Restrict algorithms in cryptographic services |
| JSSE | ssl.KeyManagerFactory.algorithm | Select the default implementation for KeyManagerFactory |
| Keystore | keystore.type | Default keystore format |
| SecureRandom | SecureRandom-related properties | Configure random sources and implementations |

These security properties affect how the JDK provides and validates security services. They do not create a sandbox for individual classes or JARs.

### Configuring an additional properties file

You can pass an additional security properties file using a system property:

~~~bash
java -Djava.security.properties=file:/etc/acme/extra.security -jar app.jar
~~~

A single equals sign means the specified file is appended to the master security properties file. Properties with the same name can override previously declared values.

If two equals signs are used:

~~~bash
java -Djava.security.properties==file:/etc/acme/complete.security -jar app.jar
~~~

The specified file completely replaces the master security properties file. This can easily drop providers, algorithm restrictions, or default configurations required by the runtime. Only use this when the replacement file is fully managed and tested on the exact JDK release.

**Note:** java.security.properties is the current mechanism for configuring security properties. It is distinct from java.security.policy, which was the Security Manager policy property disabled since JDK 24.

### Adding custom properties

A security properties file can contain custom properties read by the application itself:

~~~properties
acme.security.profile=production
~~~

Place this file at /etc/acme/extra.security and launch with:

~~~bash
java -Djava.security.properties=file:/etc/acme/extra.security -jar app.jar
~~~

A custom property does not automatically create any permission or restriction. Application code must read the value and implement the corresponding behavior.

## 10. Reading and inspecting security properties

Use the java option to inspect the effective security configuration:

~~~bash
java -XshowSettings:security -version
~~~

View only the properties group:

~~~bash
java -XshowSettings:security:properties -version
~~~

View only the TLS configuration:

~~~bash
java -XshowSettings:security:tls -version
~~~

You can enable debugging to see how the JDK reads security properties:

~~~bash
java -Djava.security.debug=properties -version
~~~

Debug output can contain extensive configuration details; only enable it in controlled diagnostic environments.

In Java code, you can read a security property:

~~~java
String disabledAlgorithms =
        java.security.Security.getProperty("jdk.tls.disabledAlgorithms");

System.out.println(disabledAlgorithms);
~~~

The actual value depends on the JDK distribution, release, and configuration files in use. Do not hardcode an algorithm string copied from another machine as a universal policy for all runtimes.

### When properties are read

Some security properties are read and cached when java.security.Security is initialized or when a provider/TLS component is created. Calling Security.setProperty after that point is not guaranteed to take effect; in some cases, no exception is thrown even though the value is not applied to already-initialized components.

For runtime configuration, set security properties before the JVM starts the application, verify them with -XshowSettings:security, and restart the process after making changes.

## 11. Replacing legacy policies with application authorization

Business permissions should be checked at the appropriate application boundary after the user has been authenticated.

For example: users with the REPORT_READER role can view reports; only ADMIN can delete reports.

Create src/com/acme/security/AuthorizationDemo.java:

~~~java
package com.acme.security;

import java.util.Set;

public class AuthorizationDemo {

    enum Action {
        VIEW_REPORT,
        DELETE_REPORT
    }

    record User(String id, Set<String> roles) {
    }

    static boolean isAllowed(User user, Action action) {
        return switch (action) {
            case VIEW_REPORT ->
                    user.roles().contains("REPORT_READER")
                    || user.roles().contains("ADMIN");
            case DELETE_REPORT ->
                    user.roles().contains("ADMIN");
        };
    }

    public static void main(String[] args) {
        User analyst = new User(
                "user-42",
                Set.of("REPORT_READER"));

        System.out.println(
                "viewReport=" + isAllowed(analyst, Action.VIEW_REPORT));

        System.out.println(
                "deleteReport=" + isAllowed(analyst, Action.DELETE_REPORT));
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -d out src/com/acme/security/AuthorizationDemo.java
~~~

Run:

~~~bash
java -cp out com.acme.security.AuthorizationDemo
~~~

Stdout:

~~~text
viewReport=true
deleteReport=false
~~~

This is an example of application-layer authorization, not a JVM sandbox. In production:

- Users and roles must come from a trusted authentication source.
- Do not take roles from the request body and trust them directly.
- Check permissions per resource, tenant, and action.
- Deny by default when permissions cannot be determined.
- Enforce authorization at the service/API boundary before reading or modifying data.
- Write audit logs for sensitive actions.

## 12. Process isolation with OS and containers

When running plugins, scripts, or untrusted code, a regular Java process should not be treated as a sandbox just because it has its own class loader or module path.

Oracle's migration documentation recommends considering mechanisms outside the JDK such as containers, hypervisors, and operating system protection mechanisms.

Control layers may include:

| Mechanism | Example | Purpose |
|---|---|---|
| Process identity | Dedicated user, dedicated group | Restrict filesystem and process permissions |
| Filesystem | Read-only root filesystem, mount only needed directories | Restrict where data can be read/written |
| Network | Firewall, egress allowlist, network policy | Restrict reachable endpoints |
| Container | Container runtime and security profile | Isolate processes, namespaces, and resources |
| OS sandbox | Linux seccomp, AppArmor, SELinux; macOS App Sandbox | Restrict system calls and resource permissions |
| Virtual machine | Hypervisor and separate guest OS | Provide a stronger isolation boundary between workloads |

Examples of deployment principles:

1. Run the application with a non-privileged service account.
2. Mount only the data directories the application needs.
3. Use a read-only filesystem if the application does not need to write.
4. Limit CPU, memory, processes, and file descriptors.
5. Block outbound network traffic by default, opening only required endpoints.
6. Isolate untrusted workloads into separate processes or containers.
7. Keep base images, JDK, and OS security patches up to date.

A container is not automatically secure simply because an application is packaged inside it. You must configure appropriate permissions, networking, filesystems, and runtime profiles.

## 13. Do the Module system and ClassLoader replace runtime policies?

No. The Java Platform Module System controls readability, exports, opens, and module dependencies. ClassLoader manages class loading. Neither mechanism is a sandbox replacement for Security Manager.

For example:

- exports restricts which packages other modules can access under module rules.
- opens allows reflective access under the corresponding module conditions.
- ClassLoader can organize namespaces and class lifecycles.
- The module path determines which modules are found and resolved.

Those mechanisms do not automatically restrict a process from accessing the filesystem, network, native code, or system resources. Do not run untrusted code in the same JVM assuming that modules or ClassLoaders will prevent all dangerous actions.

If you need to isolate untrusted code, use process boundaries and OS/container isolation.

## 14. Migrating from Security Manager to modern runtime security

When upgrading an application from JDK 17–23 to JDK 24+, inspect startup scripts, source code, and dependencies.

### Step 1: Search for traces of Security Manager

Search in scripts and configurations:

- -Djava.security.manager
- -Djava.security.policy
- .policy or java.policy files
- Custom SecurityManager
- Policy.setPolicy(...)
- System.setSecurityManager(...)
- AccessController.checkPermission(...)
- AccessController.doPrivileged(...)

Libraries may call these APIs on behalf of the application, so you must also check dependencies.

### Step 2: Scan for deprecated APIs

You can use jdeprscan from JDK releases 17–23 to find APIs deprecated for removal in bytecode:

~~~bash
jdeprscan --for-removal app.jar
~~~

Results must be evaluated alongside source code and the dependency tree. Finding no API calls does not prove the application does not rely on a policy file via startup scripts.

### Step 3: Categorize each legacy purpose

| Legacy purpose | Replacement approach to consider |
|---|---|
| Block file read/write | OS user, filesystem permissions, container mounts |
| Block network access | Firewall, egress policy, network namespaces |
| Limit CPU/memory | Container resource limits or process manager |
| User authorization | Application authorization, role/permission service |
| Isolate untrusted plugins | Separate process/container/VM |
| Configure TLS algorithms | JDK security properties and JSSE |
| Control cryptographic providers | security.provider.n in java.security |

There is no one-to-one API replacement for Security Manager. You must redesign security boundaries around actual resources and threats.

### Step 4: Test on the target JDK

- Run on the exact JDK 24/25/26 release planned for production.
- Remove Security Manager flags from startup scripts.
- Check whether libraries use deprecated/disabled APIs.
- Verify filesystem and network permissions at the OS level.
- Verify business authorization.
- Verify security properties, providers, and TLS.
- Run integration tests and test unauthorized access scenarios.

## 15. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| JVM reports Enabling a Security Manager is not supported | Startup script still passes -Djava.security.manager on JDK 24+ | Remove the flag and migrate the sandbox mechanism |
| System.setSecurityManager throws UnsupportedOperationException | API disabled since JDK 24 | Replace designs that depend on Security Manager |
| Policy file has no effect | JDK 24+ no longer supports java.security.policy | Distinguish legacy policy from current security properties |
| Policy.setPolicy throws UnsupportedOperationException | java.security.Policy no longer installs a system-wide policy | Do not use the Policy API as a new permission engine |
| getPolicy does not return expected permissions | JDK 24+ returns a Policy that grants no permissions | Migrate away from legacy APIs |
| java.security.properties overrides too much configuration | Used two equals signs and overwrote the master file | Use one equals sign if only appending; review all properties |
| TLS still allows unwanted algorithms | Security property not loaded or was overridden | Inspect -XshowSettings:security and effective properties |
| Security.setProperty does not change behavior | Property was already read/cached or component already initialized | Configure before startup and restart the process |
| Using modules/ClassLoader to run untrusted plugins | Confusing module isolation with an OS sandbox | Separate into processes/containers and restrict OS resources |
| Authorization works in UI but API still allows access | Permissions checked only in the frontend | Enforce permission checks at the server/service boundary |

## 16. Checklist for building a runtime security policy

- [ ] Identify the exact JDK release running in production.
- [ ] Confirm the application does not enable Security Manager on JDK 24+.
- [ ] Find and remove dependencies on java.security.policy or Policy.setPolicy.
- [ ] Separate business permissions from the legacy permission model.
- [ ] Configure application authorization at the service/API boundary.
- [ ] Run processes with a least-privilege user.
- [ ] Restrict filesystem and network access at the OS/container level.
- [ ] Manage security providers and algorithm constraints via java.security.
- [ ] Use java.security.properties in a controlled manner; avoid unintentionally overwriting the master file.
- [ ] Verify effective configuration with -XshowSettings:security.
- [ ] Run negative tests to confirm unauthorized operations are denied.
- [ ] Document the threat model, required permissions, and owners responsible for policy updates.

## 17. Key takeaways

- A runtime policy describes which actions are permitted while an application is running.
- Legacy Java Policy files used grant, codeBase, Principal, and permission to grant permissions to code when Security Manager was enabled.
- Security Manager was deprecated for removal in JDK 17 and permanently disabled in JDK 24.
- On JDK 24+, Security Manager cannot be enabled; java.security.policy is unsupported and the system java.policy has been removed.
- java.security.Policy is deprecated for removal; setPolicy throws UnsupportedOperationException and getPolicy returns a policy granting no permissions.
- java.security at $JAVA_HOME/conf/security/java.security remains supported for configuring providers, algorithms, and TLS.
- java.security.properties=file appends to the master security properties; java.security.properties==file replaces the entire master file.
- Security properties are not a mechanism for granting file/network permissions to individual classes.
- Business permissions should be checked at the application boundary.
- Isolate untrusted code using processes, containers, OS sandboxes, or VMs; modules and ClassLoaders are not sandboxes.
- Migration requires reviewing startup flags, policy files, deprecated APIs, libraries, and OS/container permissions.

## Official references

- [The Security Manager Is Permanently Disabled — JDK 26](https://docs.oracle.com/en/java/javase/26/security/security-manager-is-permanently-disabled.html)
- [JEP 486: Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- [JEP 411: Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)
- [The Security Properties File — JDK 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html)
- [java.security.Policy API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Policy.html)
- [Security Developer's Guide — JDK 17, Policy File Syntax](https://docs.oracle.com/en/java/javase/17/security/security-developer-guide.pdf)
- [Troubleshooting Security — JDK 26](https://docs.oracle.com/en/java/javase/26/security/troubleshooting-security.html)
