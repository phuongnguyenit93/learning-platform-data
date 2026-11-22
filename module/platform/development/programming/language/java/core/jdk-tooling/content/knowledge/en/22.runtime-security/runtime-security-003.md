# Security Properties in Java

A **security property** is a security configuration property stored by Java in a global property store managed by the `java.security.Security` class. These properties control several security behaviors of the JDK, such as the order of security providers, restricted algorithms in TLS or certificate paths, the default keystore type, and cryptographic random source configuration.

Security properties are typically declared in the JDK's `java.security` file. Applications can read them with `Security.getProperty()` and, where appropriate, modify them in-process with `Security.setProperty()`. They have their own mechanism, distinct from system properties read with `System.getProperty()`.

Understanding security properties is essential when configuring TLS, certificate validation, cryptographic providers, keystores, and JDK upgrades. An incorrect configuration value can cause secure connections to fail, allow weak algorithms to be accepted, or prevent an application from finding the required provider.

## 1. What is a security property?

Java has multiple configuration layers. Security properties are part of the platform security configuration, centralized in the `java.security.Security` class.

Some common security properties:

| Security property | Role |
|---|---|
| `security.provider.n` | Registers providers and determines their priority order |
| `keystore.type` | Default keystore type |
| `jdk.tls.disabledAlgorithms` | Algorithms/protocols disabled in TLS |
| `jdk.certpath.disabledAlgorithms` | Algorithms or key sizes restricted during certificate path validation |
| `jdk.jar.disabledAlgorithms` | Algorithms restricted when verifying JAR signatures |
| `crypto.policy` | JDK cryptographic jurisdiction policy |
| `securerandom.source` | Seed source for SecureRandom depending on configuration/provider |
| `ssl.KeyManagerFactory.algorithm` | Default algorithm for JSSE KeyManagerFactory |
| `ssl.TrustManagerFactory.algorithm` | Default algorithm for JSSE TrustManagerFactory |

These properties are typically read by the JDK or security providers to decide how cryptographic services are provided. Not every key in the file is used by every application; a property only takes effect when the corresponding component understands and reads it.

A security property can contain a list of algorithms, a provider name, a keystore type name, or another configuration value. Property names are case-sensitive according to `Properties` rules; copy the exact name from the JDK documentation rather than inventing variations.

## 2. Distinguishing security properties and system properties

This is the most common source of confusion. The two types of properties have different reading APIs and are loaded from different configuration sources.

| Aspect | Security property | System property |
|---|---|---|
| Reading API | `Security.getProperty(name)` | `System.getProperty(name)` |
| Runtime setter API | `Security.setProperty(name, value)` | `System.setProperty(name, value)` |
| Primary configuration source | `java.security` and supplemental security files | `-Dname=value` arguments, launcher environment, or code |
| Scope | JVM-wide security configuration | Process system configuration |
| Examples | `keystore.type`, `jdk.tls.disabledAlgorithms` | `javax.net.ssl.trustStore`, `https.protocols` |

For example, `keystore.type` is a security property, whereas `javax.net.ssl.trustStore` is a system property used to specify the truststore for JSSE.

Some common system properties when configuring TLS:

- `javax.net.ssl.keyStore`: path to the keystore used for the application's key material.
- `javax.net.ssl.trustStore`: path to the truststore.
- `javax.net.ssl.keyStoreType` and `javax.net.ssl.trustStoreType`: keystore/truststore types.
- `javax.net.ssl.keyStorePassword` and `javax.net.ssl.trustStorePassword`: corresponding passwords; secrets should not be passed directly on the command line.
- `https.protocols` and `jdk.tls.client.protocols`: configure TLS protocols in the respective JSSE contexts.
- `java.security.properties`: system property used to specify a supplemental or replacement security properties file.
- `java.security.debug`: system property that enables security diagnostic logging.

You cannot use `System.setProperty("keystore.type", "JKS")` to change the `keystore.type` security property. Similarly, `Security.setProperty("javax.net.ssl.trustStore", "...")` does not replace the system property that JSSE uses to locate the truststore.

## 3. Where is the java.security file located?

In JDK 9 and later, the master security properties file is typically located at:

```text
$JAVA_HOME/conf/security/java.security
```

On Windows, the corresponding path is typically:

```text
%JAVA_HOME%/conf/security/java.security
```

Older JDKs may use the location:

```text
$JAVA_HOME/lib/security/java.security
```

The master file contains the JDK's default configuration, including providers, algorithm constraints, the default keystore type, and several other security settings.

You can determine the Java home directory currently running with:

```sh
java -XshowSettings:properties -version
```

Look for the `java.home` value in the system properties section. Note that `java.home` is a system property, not a security property.

The `java.security` file typically uses properties-style syntax:

```properties
# Comment explaining the configuration
property.name=value
another.property=another-value
```

- Lines starting with `#` are comments.
- Each configuration line has the form `name=value`.
- Values may be algorithm names, lists, paths, or strings depending on the property.
- Some properties use comma-separated lists; preserve the exact syntax required by that property.

Avoid modifying the master file directly whenever possible. JDK updates may alter or overwrite this file. For application-specific configuration, manage a separate supplemental file, store it in your configuration management system, and apply it in a reproducible manner.

## 4. When are security properties loaded?

The JDK reads the master security properties file when the `java.security.Security` class is initialized. The values are placed into the process's global security properties store.

This has two consequences:

1. The configuration file must be provided before the application and security providers initialize components that depend on the property.
2. Editing the file while the application is running does not automatically cause the current JVM to reload the entire configuration.

When changing `java.security` or a supplemental file, restart the application to confirm the new configuration is applied. In multi-instance systems, deploy consistently and verify each process after restart.

Some components read a property and cache its value at initialization time. Therefore, changing a property after the corresponding TLS context, provider, or service has been created may not affect existing objects.

## 5. Reading security properties with Security.getProperty()

The `Security.getProperty(String key)` API returns the security property value by name. If the key does not exist, the result is `null`.

Example reading several properties:

```java
import java.security.Security;

public class ReadSecurityProperties {
    public static void main(String[] args) {
        String[] keys = {
            "keystore.type",
            "jdk.tls.disabledAlgorithms",
            "jdk.certpath.disabledAlgorithms",
            "crypto.policy"
        };

        for (String key : keys) {
            System.out.println(
                key + " = " + Security.getProperty(key));
        }
    }
}
```

Compile and run on JDK 17+:

```sh
javac ReadSecurityProperties.java
java ReadSecurityProperties
```

The displayed output depends on the JDK, vendor, version, and loaded configuration file. Some values such as `jdk.tls.disabledAlgorithms` can be very long because they contain many algorithms or restriction conditions.

Do not copy an entire algorithm list from one JDK to another without checking the documentation and default values of the target version.

## 6. Example comparing Security.getProperty and System.getProperty

Create the file `SecurityPropertyDemo.java`:

```java
import java.security.Security;

public class SecurityPropertyDemo {
    public static void main(String[] args) {
        String key = "example.application.securityProfile";

        Security.setProperty(key, "production");

        System.out.println(
            "Security property: " + Security.getProperty(key));
        System.out.println(
            "System property: " + System.getProperty(key));
    }
}
```

Compile and run:

```sh
javac SecurityPropertyDemo.java
java SecurityPropertyDemo
```

Exact stdout:

```text
Security property: production
System property: null
```

This example sets a custom security property in-process. Because the program does not call `System.setProperty()` and does not pass `-Dexample.application.securityProfile=...`, the system property of the same name remains `null`.

This custom property is only meaningful if application code or a provider actually reads it. Adding a key to the security property map does not automatically cause the JDK to change its behavior.

## 7. Changing security properties at runtime with Security.setProperty()

API:

```java
Security.setProperty("property.name", "property.value");
```

Example:

```java
Security.setProperty("keystore.type", "PKCS12");
System.out.println(Security.getProperty("keystore.type"));
```

`Security.setProperty()` updates the value in the current JVM's security property map. It does not write changes back to the `java.security` file and does not alter the configuration of other JVM processes.

Pay close attention to when it is called. Some properties cannot be changed effectively after they have been read and cached during initialization of the `Security` class or a related component. In that case, calling `setProperty()` may not throw an exception, yet the already-initialized component continues using the old value.

Guidelines:

- Prefer startup configuration for providers, TLS, and algorithm constraints.
- Only use `Security.setProperty()` when the property's documentation confirms it can be changed at that point.
- Set the property before initializing dependent components.
- Do not assume a runtime change will update already-created objects.
- Verify the value via `Security.getProperty()` and test the actual behavior.

## 8. Adding a security properties file with java.security.properties

You can specify a supplemental security properties file when launching the JVM using the `java.security.properties` system property.

Example on Linux/macOS:

```sh
java -Djava.security.properties=file:/opt/app/security-extra.properties -jar app.jar
```

Example on Windows:

```powershell
java -Djava.security.properties=file:/C:/app/config/security-extra.properties -jar app.jar
```

With the single equals sign syntax in the property value, the supplemental file is loaded after the master file. If the same key appears in both files, the value in the supplemental file loaded later replaces the earlier value.

Example `security-extra.properties` file:

```properties
# Only set the default keystore type when the application has an explicit compatibility requirement.
keystore.type=PKCS12
```

Then launch:

```sh
java -Djava.security.properties=file:/opt/app/security-extra.properties -jar app.jar
```

This is a way to supplement or override a few properties without copying the entire master file. Keep the supplemental file in controlled deployment configuration and ensure the JVM has read permission for the file.

## 9. Distinguishing a single equals sign from a double equals sign

The syntax has two different behaviors:

| Syntax | Behavior |
|---|---|
| `-Djava.security.properties=file:/path/extra.security` | Loads the file in addition to the master security properties file |
| `-Djava.security.properties==file:/path/complete.security` | Uses the specified file to completely replace the master file |

A double equals sign can cause default JDK properties to no longer be loaded. If the replacement file does not register required providers or omits important algorithm constraints, the application may fail or reduce its security level.

Only use full replacement mode when you manage the entire file contents, understand every required JDK/provider property, and test on the exact runtime version. For most applications, a supplemental file using a single equals sign is the lower-risk approach.

The ability to use a supplemental file is also governed by the `security.overridePropertiesFile` security property. In standard JDK configurations, this property is typically `true`; if it is set to `false` in the master file, specifying a supplemental file from the command line is disabled.

## 10. Some important security properties

### 10.1. Provider order

Keys of the form `security.provider.1`, `security.provider.2`, ... specify security providers and their priority order when the JDK searches for an implementation of an algorithm.

Providers supply services such as:

- Message digest.
- Signature.
- Cipher.
- Key pair generation.
- KeyStore.
- SecureRandom.

Provider order affects which provider is selected when an application requests an algorithm without specifying a particular provider.

You can list installed providers:

```java
import java.security.Provider;
import java.security.Security;

public class ProviderList {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println(
                provider.getName() + " " + provider.getVersionStr());
        }
    }
}
```

The actual list depends on the JDK and installed providers. Do not arbitrarily change the order or remove providers in production without checking which algorithms and components depend on that provider.

### 10.2. jdk.tls.disabledAlgorithms

`jdk.tls.disabledAlgorithms` specifies algorithms or protocols that are not permitted in TLS under the JDK's algorithm constraints.

Values may include protocol/algorithm names and conditions such as minimum key sizes. The default configuration changes across JDK versions as security standards are updated.

Do not remove an algorithm from the list just to connect to a legacy server. First, upgrade the TLS server/certificate or update the peer's configuration. If a change is unavoidable, assess the risk, limit the scope, and set a deadline to remove the exception.

### 10.3. jdk.certpath.disabledAlgorithms

`jdk.certpath.disabledAlgorithms` applies algorithm constraints during certificate path building and validation.

It can restrict signature algorithms, key types, or key sizes of certificates in the chain. This property differs from `jdk.tls.disabledAlgorithms`: one relates to certificate path validation, while the other applies constraints in TLS.

If a TLS handshake fails because a certificate chain uses an algorithm that is no longer accepted, inspect the chain, signatures, and key sizes before considering policy changes.

### 10.4. jdk.jar.disabledAlgorithms

`jdk.jar.disabledAlgorithms` specifies algorithms restricted when verifying JAR signatures. Changing this property can affect whether JARs signed with older algorithms are accepted.

If an internal JAR can no longer be verified, inspect the signing certificate, signature algorithm, and timestamp. Prefer re-signing with a currently supported algorithm rather than relaxing the entire policy.

### 10.5. keystore.type

`keystore.type` determines the default keystore type when an application calls `KeyStore.getDefaultType()`.

Since JDK 9, `PKCS12` is the default type in standard JDK configurations. Legacy systems or custom security configurations may differ.

If an application needs to read a specific file, specify the type explicitly:

```java
KeyStore store = KeyStore.getInstance("JKS");
```

This avoids depending on the runtime's default type and makes the expected file format explicit.

### 10.6. crypto.policy

`crypto.policy` controls the JDK's cryptographic jurisdiction policy. Since JDK 9, standard configurations typically use the `unlimited` policy, though you should check the actual runtime/provider when upgrading or using a custom JDK.

Do not change this property merely to bypass an algorithm error. Determine which algorithm the application needs, whether the provider supports it, and what organizational policy permits.

### 10.7. securerandom.source

`securerandom.source` relates to the seed source used in the JDK's SecureRandom configuration. Exact behavior depends on the provider and platform.

Do not hardcode an entropy source to an assumed path across all operating systems. If SecureRandom initializes slowly or fails, check the provider, operating system, entropy source, and documentation for the running JDK.

## 11. Inspecting security settings with the java launcher

JDK 17+ supports displaying security configuration via:

```sh
java -XshowSettings:security -version
```

You can narrow the output:

```sh
java -XshowSettings:security:properties -version
```

The information groups include security properties, security providers, and TLS-related configuration. This command is useful for inspecting the effective configuration received by the runtime, rather than only reading files on disk.

To debug property loading:

```sh
java -Djava.security.debug=properties -jar app.jar
```

Debug logs can print extensive details about the final properties and the configuration loading process. Enable this only when investigating, control where logs are stored, and avoid logging sensitive information in production environments.

## 12. Inspecting properties in JShell

You can quickly inspect security property values without writing a separate program:

```text
jshell> import java.security.Security;
jshell> Security.getProperty("keystore.type")
```

The output depends on the running JDK configuration. To inspect other keys:

```text
jshell> Security.getProperty("jdk.tls.disabledAlgorithms")
jshell> Security.getProperty("jdk.certpath.disabledAlgorithms")
jshell> Security.getProperty("security.provider.1")
```

Compare with system properties:

```text
jshell> System.getProperty("keystore.type")
```

Normally, the last command returns `null` if no system property with the same name is set. Security property values do not automatically appear in the system property map.

## 13. Security properties and TLS configuration

When debugging TLS, distinguish at least three configuration layers:

1. **Security properties:** algorithm constraints, providers, and security service defaults.
2. **System properties:** keystore/truststore paths, protocols requested by the application, and certain JSSE options.
3. **Certificate/key material:** private keys, certificate chains, and trusted CAs in the keystore/truststore.

| Issue | Configuration to check |
|---|---|
| Truststore not found | `javax.net.ssl.trustStore` and the actual file |
| Unable to read keystore | `javax.net.ssl.keyStore`, type, and password |
| TLS protocol not supported | JSSE/system property configuration and `jdk.tls.disabledAlgorithms` |
| Certificate chain rejected | `jdk.certpath.disabledAlgorithms`, chain, issuer, and validity period |
| Algorithm not found | Provider order, installed providers, and supported algorithms |
| Unexpected default keystore type | `keystore.type` and `KeyStore.getDefaultType()` |

Do not edit `jdk.tls.disabledAlgorithms` when the actual cause is a truststore missing a CA. Similarly, importing an additional CA will not fix errors caused by incompatible TLS protocols or cipher suites.

## 14. Safe process for changing security properties

Before making changes:

1. Identify the exact property and the component that reads it.
2. Record the current value using `Security.getProperty()` or `-XshowSettings:security`.
3. Read the JDK/provider documentation for the exact release.
4. Determine whether the change affects the entire JVM or only the application.
5. Create a separate supplemental file instead of editing the master file where appropriate.
6. Review the security impact and compatibility with integrated systems.
7. Start a new process with the test configuration.
8. Verify the effective value and loaded providers.
9. Run relevant TLS, certificate validation, signing, or keystore tests.
10. Monitor logs and have a rollback plan ready.

Do not change multiple properties at once if you do not yet know which property causes the new behavior. For algorithm constraints, change one item at a time and test the certificate/protocol types the application must support.

## 15. Common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| `Security.getProperty()` returns `null` | Key does not exist, wrong case, or file not loaded | Verify the property name and actual configuration file |
| `System.getProperty()` returns null while Security API has a value | Reading the wrong property map | Use `Security.getProperty()` for security properties |
| Supplemental file has no effect | Wrong URL/path or `security.overridePropertiesFile=false` | Check the path, read permissions, and the property allowing overrides |
| File changed but application still uses old value | JVM already initialized Security/providers or service cached the value | Restart the process and recheck |
| `Security.setProperty()` does not change behavior | Component already read/cached the property earlier | Configure at startup and recreate components in a new process |
| Double equals sign causes provider errors | File overrides the entire master file and lacks required configuration | Use a single equals sign supplemental file or manage the full replacement file |
| TLS handshake fails after JDK upgrade | Legacy algorithm/protocol/certificate restricted by new policy | Check TLS debug output, certificate chain, and disabled algorithms |
| KeyStore type not found | Provider does not support the type or provider configuration is wrong | Check `KeyStore.getInstance(type)` and providers |
| Unexpected provider selected | `security.provider.n` order or different runtime providers | Inspect `Security.getProviders()` and provider configuration |
| Master file edits lost after JDK update | Update replaced the configuration file | Use a separately managed supplemental file and redeploy |

## 16. Distinguishing java.security from java.policy

`java.security` is the JDK's configuration file for security properties and providers. It is not a permission policy file.

`java.policy` is a different concept, tied to the traditional `SecurityManager` policy/permission model. The two files have different purposes, syntax, and loading mechanisms. Do not place security property lines in a policy file or vice versa.

When reading older guides about `SecurityManager`, check which Java version is being discussed. `SecurityManager` has been deprecated for removal and its support behavior has changed across JDK releases; do not assume that all legacy policy guidance still applies to modern security models.

## 17. Checklist

- [ ] Identified whether the key is a security property or a system property.
- [ ] Read the correct master file `$JAVA_HOME/conf/security/java.security`.
- [ ] Used `Security.getProperty()` to read security properties.
- [ ] Verified effective values with `-XshowSettings:security` when needed.
- [ ] Understood the relevant providers and algorithm constraints.
- [ ] Distinguished TLS algorithm constraints from truststore/certificate configuration.
- [ ] Used a separate supplemental file if overrides are needed.
- [ ] Understood the difference between `java.security.properties` and `java.security.properties==`.
- [ ] Checked `security.overridePropertiesFile` when a supplemental file is not applied.
- [ ] Restarted the JVM after static configuration changes.
- [ ] Checked caching impact when using `Security.setProperty()`.
- [ ] Tested the relevant TLS, certificate path, provider, or keystore behavior.
- [ ] Recorded configuration, before/after values, and a rollback plan.

## 18. References

- Oracle Java Security — The Security Properties File: https://docs.oracle.com/en/java/javase/21/security/security-properties-file.html
- Oracle Java Security — Troubleshooting Security: https://docs.oracle.com/en/java/javase/21/security/troubleshooting-security.html
- Java SE 21 API — `java.security.Security`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Security.html
- Oracle JDK 21 Tool Reference — The `java` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html

Security properties control critical parts of JVM security configuration. Distinguish them from system properties, verify effective values using JDK APIs and tools, prefer controlled supplemental configuration, and test after every change. In particular, do not relax algorithm constraints merely to mask an undiagnosed TLS error.