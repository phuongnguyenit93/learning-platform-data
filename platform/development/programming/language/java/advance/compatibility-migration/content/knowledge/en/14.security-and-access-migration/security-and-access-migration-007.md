# Policy Changes for JNDI, RMI, and Remote Code Loading

When upgrading the JDK, an application using JNDI or Java RMI may fail even though the source code, service names, and Java interfaces have not changed. Mechanisms that previously allowed an application to accept class names, `codebase` addresses, object references, or serialized data from another system have been tightened across multiple security updates. A configuration that worked on an older JDK may be rejected on a newer version, especially when it relies on **loading classes from a URL supplied by the other party** or **reconstructing objects from untrusted data**.

This issue sits at the boundary between **behavioral compatibility** and **system safety**. The JDK blocking a remote code loading path may cause a legacy integration to stop working, yet that is not necessarily a bug requiring the old feature to be re-enabled. When researching migration, understand the mechanism in use, distinguish code loading from object reconstruction/deserialization, check the policies of the exact JDK build, and then move to an explicit, controlled model for distributing code and data.

This lesson covers JNDI, RMI, codebase, key hardening milestones, common configuration properties, runtime error symptoms, and a safe migration testing procedure.

## 1. Distinguishing JNDI, RMI, and Remote Code Loading

Three related concepts, yet not synonymous.

### 1.1. JNDI Is a Name Lookup API

**JNDI (Java Naming and Directory Interface)** provides an API for looking up objects or information in naming/directory systems. An application can use JNDI to retrieve environment configuration, data from LDAP, objects registered in an RMI registry, or resources provided by an application server.

For example, in a Java application server, an application can look up a container-configured `DataSource`:

~~~java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.sql.DataSource;

public class DataSourceLookup {
    public static DataSource lookup() throws Exception {
        Context context = new InitialContext();
        try {
            return (DataSource) context.lookup(
                "java:comp/env/jdbc/Orders"
            );
        } finally {
            context.close();
        }
    }
}
~~~

This is a valid and common JNDI example. It **does not mean the application is loading code over the network**: the resource may be entirely managed locally by the container.

Another application may use `InitialDirContext` to read LDAP attributes. The meaning of a lookup result depends on the provider, object type, factory configuration, and subsequent processing path.

### 1.2. Java RMI Is a Mechanism for Calling Methods Across JVMs

**Java Remote Method Invocation (RMI)** allows an object in one JVM to invoke methods exported by another JVM. RMI defines a `Remote` contract and uses stubs/proxies, networking, and serialization to pass parameters or results according to the communication contract.

Example of a shared interface:

~~~java
package com.example.contract;

import java.rmi.Remote;
import java.rmi.RemoteException;

public interface GreetingService extends Remote {
    String greet(String name) throws RemoteException;
}
~~~

Clients can look up a service registered in the RMI registry and invoke its methods. This lookup/method invocation **does not require loading Java classes from a remote URL**: client and server can distribute the same interface along with necessary data classes via pre-installed artifacts.

### 1.3. Remote Code Loading Is a Distinct Capability

In historical RMI/JNDI designs, reference information could carry a **codebase URL** pointing to where to obtain classes not already present in the receiving JVM. One side of the connection could supply class information and a URL for the other side to consider loading.

The risk point is that an object coming from another system can influence the **source of code loaded into the JVM**. If the URL or class name is controlled by an untrusted party, remote code loading can significantly widen the attack surface.

Conceptual flow:

~~~text
Local application
      |
      | JNDI lookup / RMI exchange
      v
Naming service / RMI peer
      |
      | class name, metadata, object reference,
      | possibly with codebase in legacy designs
      v
Local JVM
      |
      +--> Is the class present in a local artifact?
      |
      +--> Legacy mechanism may consider a remote codebase URL
      |
      v
Construct object / invoke method / process data
~~~

Newer JDK releases have curtailed or removed many remote class loading paths. However, **do not infer that blocking class loading from URLs simultaneously eliminates all risks from JNDI, object factories, serialized data, or RMI**.

| Aspect | JNDI | RMI | Loading Classes from Codebase |
|---|---|---|---|
| Purpose | Looking up names, resources, or directory information | Calling methods across JVMs | Fetching class definitions not locally available |
| Typical APIs | `InitialContext`, `InitialDirContext` | `Remote`, `Registry`, `UnicastRemoteObject` | Class loading/codebase mechanism of the provider or RMI |
| Requires network access? | No; depends on provider | Usually yes, except local configurations | Depends on codebase location |
| Requires remote bytecode loading? | No | No | Yes when that mechanism is used and permitted |
| Primary risks | Lookup inputs, results, object factories, access permissions | Authentication, networking, serialization, class loading | Introducing untrusted code into the JVM |

## 2. Why Have Policies Changed Across JDK Releases?

Previously, Java offered numerous dynamic class distribution capabilities so distributed systems could exchange objects flexibly. Over time, platform developers recognized that letting remote data dictate loading and executing code introduces severe risks, whereas modern deployment models can pre-provision permitted classes.

Changes typically take the following forms:

- Switching a property's default value from allowing to denying a remote code loading path.
- Restricting how JNDI providers use codebase URLs in object references.
- Disallowing deserialization or reconstruction of certain data/object types from LDAP unless explicitly allowed.
- Adding filters to restrict which object factory types can be used.
- Completely removing a remote code downloading path or the property that could re-enable it.
- Removing legacy mechanisms such as RMI Activation or reducing reliance on the Java Security Manager.

Do not fill out a behavior matrix based solely on the **Java feature version number**. Security update releases within the same JDK line, the vendor, and the exact build also matter. Check release notes, `java.naming`/RMI documentation, and the effective configuration of the deployed runtime.

## 3. Key Historical Milestones to Know During Migration

### 3.1. RMI: `java.rmi.server.useCodebaseOnly` Defaults to `true`

In older Java versions, RMI had a mechanism allowing a peer to supply a URL for loading classes. The property:

~~~text
java.rmi.server.useCodebaseOnly
~~~

plays a central role in this policy. Starting in **JDK 7 Update 21**, the default value was changed to `true`; Oracle documentation also notes corresponding changes in certain older update branches such as JDK 6 Update 45 and JDK 5 Update 45.

When set to `true`, RMI does not arbitrarily trust codebase URLs supplied by the other party for loading classes under the legacy mechanism. This reduces the ability for one side to force the other to load code from an unexpected address.

Previously compiled systems that relied on the remote side providing classes may begin encountering errors like:

~~~text
java.rmi.UnmarshalException
    nested exception is:
        java.lang.ClassNotFoundException: ...
~~~

The right action is not to default to flipping the property back to `false`. Setting it to `false` in runtimes that still support the corresponding mechanism increases the risk of loading untrusted code. The sustainable migration path is to **distribute trusted classes/interfaces/DTOs to both ends of the connection** and manage artifact versions.

### 3.2. JNDI LDAP/RMI: Codebase URL Trust Policy Tightened

JDK releases gradually changed how JNDI providers handle references containing codebase URLs. Two historical properties to identify in scripts and configurations are:

~~~text
com.sun.jndi.rmi.object.trustURLCodebase
com.sun.jndi.ldap.object.trustURLCodebase
~~~

These are specific properties for legacy mechanisms of the **JNDI RMI provider** and **JNDI LDAP provider**, not a universal flag governing every Java library that might call `URLClassLoader`.

A legacy system might have enabled them to allow accepting object references and loading classes from a URL outside the deployment environment. Later JDK updates shifted to more cautious defaults.

Do not copy old configuration examples from the Internet and assume they still work on current JDKs. Support and defaults change over time; in JDK 24, these two properties were **removed**.

### 3.3. JDK 15 and JDK 17: Legacy RMI Changes

Two other milestones to distinguish from remote class loading:

- **JDK 15:** the static stub compiler tool `rmic` was removed. Legacy build systems still invoking `rmic` must update their workflow; RMI itself still exists and typically uses dynamic proxies/stubs under the appropriate mechanism.
- **JDK 17:** **RMI Activation** was removed under JEP 407. This does not mean all of Java RMI was removed. Applications using `rmid` or the old activation API must change how remote object lifecycles are managed.

These two changes are real migration issues, but not evidence that ordinary `Registry.lookup` or all RMI applications stop working.

### 3.4. JDK 24: JNDI Remote Code Downloading Is Permanently Disabled

This is a milestone to record very clearly. According to the **JDK 24 Release Notes**, **remote code downloading by the JNDI LDAP and RMI providers is permanently disabled**. At the same time, two system properties:

~~~text
com.sun.jndi.rmi.object.trustURLCodebase
com.sun.jndi.ldap.object.trustURLCodebase
~~~

were removed. Therefore, **those properties can no longer be used to enable remote code downloading for JNDI providers in JDK 24**.

JDK 24 also removed the JNDI environment property `java.naming.rmi.security.manager`, previously used to request installing `RMISecurityManager`. This is part of phasing out the Security Manager's role from the platform; JEP 486 permanently disabled the ability to enable the Java Security Manager in JDK 24.

Boundaries to distinguish:

- JDK 24 **does not remove the JNDI API**; looking up valid resources and directory entries remains a usable feature.
- JDK 24 **does not remove all of RMI**; calling remote methods based on properly distributed classes and valid configuration can still work.
- This milestone speaks specifically about **remote code loading via the JNDI LDAP/RMI providers**, not a claim that every Java library or `ClassLoader` is forbidden from loading data over a network.
- Preventing remote code downloading **does not mean every lookup result or every object factory is automatically trusted**.

If migrating from an older JDK to JDK 24 or later and the application genuinely depends on loading classes from an LDAP/RMI codebase, change the architecture: bundle the needed factories/classes into managed local artifacts or replace the object exchange mechanism.

### 3.5. Summary Table of Milestones

| Milestone | Related Change | Items to Check |
|---|---|---|
| JDK 7u21 and corresponding earlier updates | `java.rmi.server.useCodebaseOnly` defaults to `true` | Do RMI client/server rely on codebase URLs from peers? |
| JNDI hardening waves in subsequent updates | JNDI LDAP/RMI codebase URL trust restricted | Do scripts contain `trustURLCodebase`; does the app need remote class loading? |
| JDK 15 | Removal of `rmic` | Does the build still generate static stubs with the old tool? |
| JDK 17 | Removal of RMI Activation | Is `rmid` or the activation API used? |
| JDK 24 | JNDI LDAP/RMI remote code downloading permanently disabled; two `trustURLCodebase` properties removed | Replace URL class loading dependencies with pre-installed classes/factories |
| JDK 24 | Removal of `java.naming.rmi.security.manager`; Security Manager cannot be re-enabled | Remove sandbox configurations relying on the legacy mechanism |

This table lists focal milestones for investigation and does not replace official documentation for the **exact JDK release, update, and vendor**.

## 4. JNDI Lookup Is Not the Same as Remote Code Loading

A JNDI lookup can return many kinds of results depending on the provider. For example, reading an LDAP attribute differs from asking JNDI to reconstruct a Java object based on a `Reference`.

### 4.1. Querying LDAP as Directory Data

Illustrative example with an LDAPS connection to a directory managed by the organization:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

public class DirectoryReader {
    public Attributes readEntry(
            String ldapUrl,
            String bindDn,
            String password) throws Exception {

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL, ldapUrl);
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL, bindDn);
        env.put(Context.SECURITY_CREDENTIALS, password);
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        DirContext context = new InitialDirContext(env);
        try {
            return context.getAttributes(
                "uid=test-user,ou=people,dc=internal,dc=example",
                new String[] { "cn", "mail" }
            );
        } finally {
            context.close();
        }
    }
}
~~~

The `ldapUrl` value in deployment must be controlled, such as `ldaps://directory.internal.example:636`, with proper TLS validation. The example only illustrates reading directory attributes; it does not attempt to construct Java objects from unknown references or load classes from external URLs.

In production, avoid hardcoding passwords, prefer secure credential management mechanisms, and verify the directory server's identity. Using `ldaps://` does not replace truststore and certificate identity validation.

### 4.2. Reference and Object Factories

JNDI has a `Reference` and `ObjectFactory` mechanism. A reference can represent information for a factory to reconstruct an object according to a known contract. A suitable factory can already reside on the **local classpath/module path**.

This is a distinct capability from remote code downloading:

~~~text
JNDI lookup receives Reference
        |
        v
Provider/JNDI checks whether factory is suitable
        |
        +--> Is factory available locally and allowed by policy?
        |           |
        |           v
        |       Construct object
        |
        +--> Legacy mechanism wants to load factory from an external URL?
                    |
                    v
               Restricted / disabled
               by JDK and provider
~~~

When JDK 24 blocks remote code downloading, an application can still use **pre-installed and permitted** object factories, depending on the JNDI provider's policy. This means controlling factory classes remains important: an untrusted directory server could try returning data that causes the application to invoke an unintended local factory.

### 4.3. Factory Classes Chosen from External Data Are a Trust Boundary

It is a design flaw to treat any reference returned by a naming server as trustworthy enough to instantiate a Java object. In a secure architecture, the application should restrict:

- Which naming/directory servers may be connected to.
- Which names or DNs are queried.
- Which result types are accepted.
- Which factories are allowed to construct objects.
- Which classes are allowed to be deserialized, if any.
- What permissions and network access the application process may use.

A policy blocking class loading from URLs addresses only **one** link in this chain.

## 5. Controlling Object Construction and Deserialization in JNDI LDAP

### 5.1. `com.sun.jndi.ldap.object.trustSerialData`

In JDKs that include this property, `com.sun.jndi.ldap.object.trustSerialData` controls certain **object reconstruction** paths in the JNDI LDAP provider. JDK 24 documentation describes its scope as including serialized data in `javaSerializedData`, reconstructing RMI references from `javaRemoteLocation`, and certain binary reference addresses in `javaReferenceAddress`.

In JDK 24, when the property is unset, those documented reconstruction/deserialization paths are **disallowed** by default. Setting it to `true` relaxes this behavior; it is not a setting to enable merely "to get the app running again."

An important misconception: `trustSerialData` is **not the same property** as `trustURLCodebase`.

| Property/Mechanism | What Is Controlled? | What to Understand Accurately |
|---|---|---|
| `com.sun.jndi.ldap.object.trustURLCodebase` (historical) | Trusting codebase URLs for JNDI LDAP remote class loading | Removed in JDK 24; cannot be used to re-enable this mechanism |
| `com.sun.jndi.rmi.object.trustURLCodebase` (historical) | Trusting codebase URLs for JNDI RMI remote class loading | Removed in JDK 24 |
| `com.sun.jndi.ldap.object.trustSerialData` | Certain deserialization/reconstruction paths from LDAP attributes | Data and object reconstruction risks; distinct from loading classes from URLs |
| `jdk.jndi.object.factoriesFilter` | Filtering object factories allowed to construct objects from JNDI references | Can block unpermitted local factories |
| `jdk.jndi.ldap.object.factoriesFilter` | Additional factory filtering in the LDAP provider | Default settings should not be treated as an application allowlist policy |

Do not relax a filter to compensate for a missing local library, nor set properties based solely on a stack trace without identifying which provider the data actually traverses.

### 5.2. Object Factory Filters

Properties such as `jdk.jndi.object.factoriesFilter` and `jdk.jndi.ldap.object.factoriesFilter` help restrict which object factories can be used to instantiate objects from references.

They can apply filter expressions using pattern syntax similar to serialization filtering, yet are **not completely identical** to object-graph deserialization filters. For the LDAP provider, both provider-specific policy and the global filter may participate in the decision.

A conceptual policy illustration:

~~~text
Allow factories in inventoried internal packages
Reject factories outside that list
Do not automatically re-enable any remote codebase download
~~~

In real implementations, consult the specific documentation of the JDK in use to write the filter syntax and verify results with integration tests. Avoid copying a filter that looks strict yet inadvertently blocks valid factories or permits factories not in your inventory.

### 5.3. Serialization Filtering for RMI and Other Object Streams

RMI typically uses serialization to transmit parameters or return values. Risks do not lie solely in whether the JVM loads classes from the network: serialized data can trigger logic during object reconstruction or build huge object graphs affecting resources.

The JDK supports `ObjectInputFilter` mechanisms and the `jdk.serialFilter` configuration to restrict which classes, depth, reference count, and object graph byte size are accepted in appropriate deserialization paths.

Illustrative policy string example:

~~~text
maxdepth=20;maxrefs=1000;maxbytes=1048576;com.example.dto.*;!*
~~~

This is **not** a configuration to paste mechanically into every system: inventory all data types genuinely serialized, verify permitted classes, and test both allowed and rejected flows. An overly narrow filter can prevent valid data from deserializing; an overly broad filter fails to mitigate the risk.

## 6. RMI Codebase and Class Distribution Models

### 6.1. Historical Role of `java.rmi.server.codebase`

In some older RMI designs, the `java.rmi.server.codebase` property held a URL related to referencing remote objects and locating class definitions. The codebase mechanism could tell the recipient where to fetch classes absent from its own environment.

However, modern deployments can avoid relying on that mechanism by distributing:

- Shared remote interfaces.
- DTOs or serializable value types used by both sides.
- Framework/proxy JARs needed by the runtime.
- A tested set of versions with explicitly locked dependencies.

With `java.rmi.server.useCodebaseOnly=true`, do not design applications expecting a peer to arbitrarily dictate class-loading URLs. Do not set `useCodebaseOnly=false` as a default workaround; Oracle documentation warns this increases remote code loading risks in runtimes that still support it.

### 6.2. Example of an RMI Client Without Remote Code Loading

Suppose both client and server are pre-provisioned with the same `GreetingService` interface in controlled artifacts:

~~~java
package com.example.client;

import com.example.contract.GreetingService;
import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

public class GreetingClient {
    public static void main(String[] args) throws Exception {
        Registry registry = LocateRegistry.getRegistry(
            "rmi.internal.example", 1099
        );

        GreetingService service =
            (GreetingService) registry.lookup("GreetingService");

        System.out.println(service.greet("Java"));
    }
}
~~~

The illustrative code assumes the server and registry are already configured by an administrator. RMI connections may require a different port from the registry port depending on how the remote object is exported. Using a host in the `.example` domain is solely illustrative, not a live endpoint.

In real deployments, RMI across untrusted hosts must have appropriate authentication, encryption, and network controls. The protocol should not be exposed publicly simply so clients can call `Registry.lookup`.

### 6.3. RMI Works Yet Fails Due to DTO Changes

A system might not load code remotely yet still encounter compatibility errors if sender and receiver use different DTO versions. Cases include:

- The class is absent from the receiver's runtime classpath.
- Changed `serialVersionUID` or incompatible serialized form.
- A field holds a dependent type not yet installed on the receiver.
- Interface or method signature changed.
- Serialization filter rejected the type or object graph size.
- Modules or class loaders prevent accessing/casting the type.

Do not lump all of these under "JDK blocked RMI." Inspect the specific exception class and underlying cause in the stack trace.

## 7. Common Failure Patterns After Upgrading the JDK

| Symptom | Possible Context | Investigation Direction |
|---|---|---|
| `ClassNotFoundException` nested in `UnmarshalException` | RMI received data referencing a class not present locally | Receiver classpath, DTO/stub version, codebase expectation |
| `NamingException` / `ConfigurationException` | JNDI provider or resource misconfigured | Provider URL, factory, DNS/network, JNDI configuration |
| `NameNotFoundException` | Lookup name does not exist in naming directory | Namespace, DN, context, environment |
| `ServiceConfigurationError` or factory error | Selected provider/factory invalid or failed to create object | Metadata, local factory class, filters, and versions |
| `ClassCastException` | Lookup returned an object differing from expected contract | Runtime type, class loader, and API version |
| `InvalidClassException` | Incompatible serialized form or rejected by filter per policy | `serialVersionUID`, DTO, filter, cause |
| `ClassNotFoundException` during object reconstruction | Provider tried to instantiate a class missing locally | Check JNDI factory/reference and packaging |
| `NoSuchMethodException` / `IllegalAccessException` | Local factory missing constructor/method or lacking permissions | API, reflection, module `exports`/`opens` |
| Lookup result rejected while LDAP connection succeeds | Provider policy blocked reconstruction/factory | Distinguish successful directory query from failed object construction |
| `rmid`/`rmic` startup error | Legacy application depends on removed tool/mechanism | JDK 15/17 milestones, build/lifecycle migration |
| `SSLHandshakeException` | TLS/certificate/hostname mismatch | Truststore, cipher suites, certificate chain |

Actual messages may vary by vendor, provider, and code path. What matters is reading the **`Caused by` chain** and identifying the failing step: connecting, name lookup, factory selection, class loading, deserialization, method invocation, or business logic.

### 7.1. Example Distinguishing Lookup Errors from Object Construction Errors

~~~text
Step 1: Connect to LDAP server
        |
        +-- Cannot connect / TLS error --> network/SSL
        |
        v
Step 2: Look up DN and read attributes
        |
        +-- Name does not exist --> NameNotFoundException
        |
        v
Step 3: Interpret result as a Java object
        |
        +-- Local factory missing --> factory/classpath
        +-- Rejected by filter --> JNDI policy
        +-- Remote codebase blocked --> change architecture
        +-- Serialized data rejected --> trustSerialData/filter
        |
        v
Step 4: Use object
        |
        +-- ClassCast/API mismatch --> type/version contract
        v
Success
~~~

If you only see `NamingException` at the outer layer, inspect the root cause so you do not confuse a policy error with a network error.

## 8. Common Migration Cases

### 8.1. Legacy JNDI Applications Previously Constructing Objects from Codebase URLs

**Before upgrade:** a naming service returned a reference containing factory class info and a URL; the old JVM was configured to permit a remote code loading mechanism.

**After upgrade:** the URL trust property may have changed defaults or, in JDK 24, been removed. Lookups are no longer allowed to load factories via JNDI remote code downloading, so a flow that worked previously may be rejected.

**Sustainable fix:** identify the factory's developer, verify trustworthiness, bundle it into local artifacts, apply factory filters, and test lookups with known data. If the directory server could be externally controlled, restrict object creation paths and data sources.

Do not propose re-enabling `trustURLCodebase=true` on JDK 24, as it is no longer a supported mechanism for restoring remote code loading.

### 8.2. RMI Server/Client Sharing Incomplete Object Types

**Before upgrade:** an old environment might have relied on a remote codebase to supply missing classes to the client.

**After upgrade:** the receiver no longer accepts peer-supplied codebases under default policy, or switched to a stricter configuration; unmarshalling fails.

**Resolution:** publish compatible contract JARs and DTO JARs, install them on both ends of the connection, check serialized forms, and run the same integration test suite on the target runtime. Do not use peer URLs as an implicit artifact distribution system.

### 8.3. Upgrading the JDK Without Changing the Application Server

An old application server or middleware library may contain code depending on RMI Activation, the static stub compiler, Security Manager, or internal JNDI properties. When the JDK changes, the issue may reside in the **underlying packaged framework** rather than business source code.

The solution is to read the server/framework support matrix, upgrade to a vendor-supported version, and test resource lookup/RMI on the exact target runtime. Tweaking JVM flags alone cannot bring back a removed API or tool.

### 8.4. LDAP Lookup Still Returns Data Yet Object Factory Fails

A directory query returning attributes successfully does not prove the application can still construct every Java object from those attributes. The JDK may restrict certain reconstruction paths or filter factories.

If the actual purpose is only retrieving user information, the team should consider switching to **explicitly reading and mapping LDAP data** rather than letting directory entries dictate arbitrary classes/factories.

### 8.5. Applications Using JMX Over RMI

JMX remote connectors can use RMI at the transport layer. When upgrading the JDK, distinguish issues involving JMX, TLS, authentication, serialization, and deprecated/removed management components from loading JNDI code via LDAP/RMI codebases.

Do not expose RMI or JMX to uncontrolled public networks. For remote administration, restrict interfaces/ports, authentication, and TLS according to the supported stack's capabilities.

## 9. Appropriate Security Policies for Modern Applications

### 9.1. Do Not Load Classes from Arbitrary Peer-Provided Sources

Replace receiving codebase URLs and loading classes with distributing versioned artifacts, signature/provenance checks, dependency locks, and release pipelines. If the product genuinely needs dynamic plugins, use a trusted plugin registry, artifact verification, allowlists, privilege limits, and a dedicated testing workflow.

Loading classes from an untrusted URL is not a feature to re-enable merely to achieve behavioral compatibility with an older JDK.

### 9.2. Do Not Treat JNDI Results as Unrestricted Code Execution Inputs

JNDI inputs such as provider URLs, lookup names, DNs, attributes, and references should be controlled according to purpose. In particular, never pass arbitrary user-supplied URLs or names directly into lookup flows capable of constructing objects, invoking factories, or connecting to arbitrary hosts.

Recommended practices:

- Use a list of trusted naming/directory endpoints.
- Restrict network egress to required endpoints.
- Enforce TLS validation for LDAP and related protocols.
- Use least-privilege access for lookup accounts.
- Read only the object types/attributes truly needed.
- Apply appropriate object factory filters/serialization filters.
- Log sufficiently for investigation without exposing credentials, tokens, or sensitive data.

### 9.3. Protecting RMI with Networking, Authentication, and TLS

RMI does not automatically become a secure protocol just because remote code loading is restricted. Evaluate:

- Which objects are exported and who can invoke them.
- From where the remote registry and service ports are reachable.
- Whether TLS and mutual authentication or an appropriate authentication mechanism are needed.
- Whether deserialized data types are controlled.
- Whether size, depth, and resource limits are enforced.
- Whether unmarshalling errors and connection anomalies are monitored.

Java provides `SslRMIClientSocketFactory` and `SslRMIServerSocketFactory` for certain RMI configurations using SSL/TLS. Properly design truststores/keystores and connectivity on both client and server, rather than merely adding factory names to source code and assuming communication is secure.

### 9.4. Do Not Rely on the Security Manager as a Modern Security Boundary

The Security Manager is a legacy mechanism; in JDK 24 it cannot be re-enabled. If a system previously relied on policy files and the Security Manager to run remotely loaded code inside a "sandbox," do not view migrating the JDK as merely translating the corresponding properties.

Replace it with architecturally appropriate protection boundaries: separate processes, containers, OS sandboxes, network policies, least-privilege permissions, and artifact provenance controls. These protective layers must also be tested against the system's threat model.

## 10. Inventorying Dependencies Before Changing the JDK

### 10.1. Searching Source, Configs, and Scripts

You can start with the following keywords in the repository and deployment configurations:

~~~text
javax.naming
InitialContext
InitialDirContext
Context.PROVIDER_URL
ObjectFactory
Reference
ServiceLoader
Registry.lookup
LocateRegistry
UnicastRemoteObject
RMISecurityManager
java.rmi.server.codebase
java.rmi.server.useCodebaseOnly
trustURLCodebase
trustSerialData
jdk.jndi.object.factoriesFilter
jdk.jndi.ldap.object.factoriesFilter
jdk.serialFilter
rmic
rmid
java.security.manager
~~~

Run text searches across source code, resources, Dockerfiles, shell scripts, YAML/Helm values, runtime configuration files, and deployment management apps. Dependencies outside the repository can also bring in JNDI/RMI configurations.

Do not conclude "unused" merely because application source does not import `javax.naming` or `java.rmi`; application servers, frameworks, and monitoring connectors may invoke them indirectly.

### 10.2. Using Dependency Inventories and Bytecode Analysis

`jdeps` helps find static dependencies on Java APIs/modules, yet does not fully detect class names, URLs, or factories residing only in configuration strings. Therefore, combine:

- Build tool dependency trees.
- Actual JAR analysis with `jdeps` and `jar --list`.
- Searches in properties, XML, YAML, JSON, and service descriptors.
- Inventories of container images and middleware.
- Runtime logs when code actually performs lookups or calls remote objects.

The purpose is not merely removing a JVM flag, but mapping **trust paths**: where data originates, which JVM receives it, and which mechanism turns that data into Java objects.

### 10.3. Categorizing by Risk Level and Impact

| Detected Dependency | Classification | Priority Action |
|---|---|---|
| JNDI lookup of container-registered local resources | Standard mechanism | Check provider/resources on the new server |
| LDAP query reading only defined attributes | Directory integration | Test TLS, authentication, queries, and data |
| JNDI object reference using local factory | Constructing objects from references | Inventory factories, filter, test lookups |
| JNDI loading factory from codebase URL | High-risk legacy dependency | Remove remote downloading, bundle local factory |
| RMI using pre-installed contract/DTO JARs | Distributed RPC | Test APIs, versions, TLS, serialization |
| RMI expecting peer to supply class-loading URL | High-risk legacy dependency | Distribute trusted contract JARs |
| RMI Activation or `rmic` | Legacy API/tool changed or removed | Upgrade middleware, fix lifecycle/build |
| JNDI LDAP permitting deserialization/reconstruction from external directory | Sensitive data path | Evaluate trust boundaries, filters, and alternatives |
| JMX/RMI remote management | Remote administration | Check authentication, TLS, network exposure |

## 11. Building a Migration Test Plan

Do not test only whether the application starts up successfully. Features such as JNDI factories, LDAP mapping, or RMI DTOs may only trigger in rarely used business branches.

### Step 1: Document Source and Target Environments

Collect:

- JDK feature/update/build and vendor on both ends of RMI.
- Versions of the application server, framework, and directory provider.
- Runtime JVM arguments and system/security properties.
- Deployed contract, factory, DTO, and plugin JARs.
- Module path/classpath, class loaders, and container images.
- Network configuration, TLS, credentials, and naming endpoints.

Different JDK patch levels may apply different security defaults; when necessary, test directly on the exact build to be deployed.

### Step 2: Check Effective Policies

Read the corresponding JDK release notes, migration guide, and `java.naming` module documentation. Determine whether the properties remain supported and what their defaults are.

You can review declared system properties by inspecting startup scripts or vetted configuration logs. Knowing a property appears on the command line does not prove the current JDK still honors it.

Specifically with JDK 24, do not treat `trustURLCodebase` as a mechanism to restore JNDI remote code downloading.

### Step 3: Run JNDI Tests by Result Type

| Test | Result to Confirm |
|---|---|
| Lookup of pre-existing local resource | Correct result type, no external code loaded |
| Ordinary LDAP attribute lookup | Secure connection, accurate data |
| JNDI reference using permitted local factory | Object successfully created from pre-installed class |
| Reference relying only on non-local class | Rejected by design, does not automatically load external URL |
| Factory outside allowlist | Rejected by filter; appropriate error logged |
| Untrusted serialized/reconstruction data | Not reconstructed when prohibited by policy |
| Wrong/missing naming entry | Error handled without cascading impact |

Rejected cases should be tested in an **isolated environment with benign sample data**, without needing exploits or real untrusted endpoints.

### Step 4: Run RMI Tests on the Proper Classpath

Use the contract/DTO artifacts that client and server plan to deploy. Run tests for:

1. Registry lookup.
2. Basic remote method invocation.
3. Sending and receiving actual DTOs in use.
4. Timeout or connection loss error handling.
5. TLS/authentication verification.
6. Serialization filter verification.
7. Confirming the client does not need to load code from peer-specified URLs.

If multiple JDK versions must be supported, test runtime pairs in the support matrix, not only the developer machine's Java version.

### Step 5: Test in a Production-Like Environment

A local test may miss failures caused by firewalls, RMI ports exported separately from the registry port, truststores, DNS URLs, or application server class loaders. Use production-equivalent images, startup flags, and topology; input configurations must be managed and controlled.

### Step 6: Record Evidence

A report should include:

| Field | Example Information |
|---|---|
| Feature | JNDI LDAP user lookup |
| Source runtime | Old JDK + vendor + build |
| Target runtime | New JDK + vendor + build |
| Provider | LDAP / JNDI RMI / application server |
| Trust boundary | Directory endpoint or RMI peer |
| Legacy behavior | Whether it depended on remote codebase |
| Security config | Factory filter, serial filter, TLS |
| Observed result | Succeeded, blocked per policy, or failed |
| Mitigation | Install local factory, update DTOs, upgrade framework |
| Owner | Integration management team |
| Evidence | Stack trace, test report, sanitized logs |

The goal is to confirm that **valid mechanisms still work** and **unsafe code loading mechanisms are not inadvertently re-enabled**.

## 12. Migration Example: Removing Dependencies on Remote Factories

Suppose a service uses LDAP as a configuration store. The old design returned a Java object reference pointing to a factory class not installed in the application, accompanied by a remote codebase location.

Before migration:

~~~text
Directory entry
    |
    +--> Factory class name
    +--> Remote codebase info
    |
    v
JNDI provider (old runtime / legacy config)
    |
    v
May need to load class from an external URL
~~~

After migration, replace the contract with one of two clear approaches:

**Approach A – Use LDAP as a data source.** Directory entries contain schema-defined attributes, and the application maps them into DTOs via local code. Do not let LDAP dictate classes or where code is loaded from.

**Approach B – Use pre-installed factories.** If an `ObjectFactory` is genuinely needed, the factory belongs to an inventoried JAR distributed with the application. The naming service returns reference data only within permitted bounds; a filter restricts allowed factories.

~~~text
Controlled artifact
    |
    +--> Contract JAR
    +--> Local factory JAR
    +--> DTO / schema
    |
    v
JVM runtime
    |
    | JNDI lookup to permitted directory
    v
Reference / attributes validated
    |
    | No class loading from remote URL
    v
Permitted local factory
    |
    v
DTO / resource matching contract
~~~

Both approaches require testing business logic and access permissions. The benefit is eliminating implicit dependence on a URL hosting bytecode controlled by another system.

## 13. Migration Example: Retaining RMI While Removing Dynamic Codebases

Suppose a system has two JVMs: service A provides remote methods and service B calls them. The old design previously let B receive missing classes from A's codebase.

New model:

- Create a dedicated contract module/JAR containing the `Remote` interface and DTOs.
- Both client and server depend on a compatible contract version.
- Package artifacts into trusted images or installation environments.
- Maintain `java.rmi.server.useCodebaseOnly=true` as recommended by supporting JDKs.
- Protect RMI with TLS, authentication, and network segmentation.
- Apply appropriate serialization filtering.
- Run data send/receive tests across supported JDK pairs.

If an interface or DTO changes incompatibly, omitting remote code loading will not fix API or serialized-form errors. Manage contract versioning just like any other distributed contract.

## 14. Common Misconceptions

**"JNDI is dangerous and must be deleted entirely."** No. JNDI lookups of local resources or LDAP attributes still have valid uses. Risk lies in how endpoints are chosen, results are trusted, Java objects are constructed, or code is loaded.

**"If the JDK no longer loads classes from URLs, every lookup is safe."** No. Local factories, deserialization, query inputs, credentials, and network trust still require separate policies.

**"JNDI and RMI are the same protocol."** No. JNDI is a naming/directory API; RMI is an inter-JVM method invocation mechanism. JNDI can use an RMI provider, yet the two concepts are not equivalent.

**"`java.rmi.server.useCodebaseOnly` and `trustURLCodebase` are the same flag."** No. They belong to different mechanisms and scopes; do not equate the RMI codebase policy with JNDI LDAP/RMI providers.

**"Setting `trustURLCodebase=true` still enables JNDI remote code downloading in JDK 24."** No. Both JNDI LDAP/RMI `trustURLCodebase` properties were removed at that milestone.

**"If an RMI application fails on JDK 17, RMI was removed."** No. RMI Activation was removed; regular RMI still exists.

**"`rmic` was removed so RMI stubs cannot be created."** No. RMI uses appropriate stub/proxy mechanisms in modern versions; update builds and avoid depending on the old tool.

**"Enabling `trustSerialData` only lets LDAP read a few more attributes."** No. The property governs Java object reconstruction paths from LDAP data; relaxing it requires serious risk evaluation.

**"Without the Security Manager, reusing an equivalent policy file suffices."** No. JDK 24 does not allow re-enabling the Security Manager; design protection boundaries using modern mechanisms.

**"Having all JARs on the classpath guarantees integration."** No. Serialization compatibility, factory filters, module access, authentication, TLS, and runtime logic can all cause failures.

**"Testing startup is enough."** No. Many JNDI lookups and RMI calls occur only when users open a feature, enter a fallback branch, or execute a rarely used workflow.

## 15. Checklist When Upgrading Systems Using JNDI/RMI

- [ ] Identified source/target JDKs, vendor, and full build numbers.
- [ ] Identified which JNDI providers are in use: local, LDAP, RMI, or custom.
- [ ] Inventoried `InitialContext`, object factories, reference data, and configuration sources.
- [ ] Confirmed whether there is any dependency on remote codebase URLs.
- [ ] Checked historical `useCodebaseOnly` and `trustURLCodebase` properties for the exact versions.
- [ ] If targeting JDK 24 or later, eliminated assumptions that JNDI LDAP/RMI remote code downloading can be re-enabled.
- [ ] Checked `trustSerialData` and object factory filters per provider documentation.
- [ ] Evaluated serialization filters for RMI/related deserialization streams.
- [ ] Removed dependencies on `rmic` or RMI Activation if upgrading past their removal milestones.
- [ ] Evaluated all legacy assumptions regarding the Security Manager.
- [ ] Pre-installed required contract JARs, DTOs, and factories from trusted sources.
- [ ] Checked TLS, credentials, truststores, registry/service ports, and network policies.
- [ ] Tested successful lookups, rejected factory cases, and invalid data.
- [ ] Tested RMI DTO marshalling/unmarshalling between target runtimes.
- [ ] Tested in an environment with the same class loader/module path as production.
- [ ] Recorded accepted behavioral changes and how to roll back or remediate.

## 16. Official Reference Documentation

The following sources provide the basis for the milestones and principles presented:

- [Oracle JDK 24 Release Notes](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html): the `JNDI Remote Code Downloading Is Permanently Disabled` change, removal of the `java.naming.rmi.security.manager` property, and related security items.
- [JDK 24 Migration Guide – Removed Tools and Components](https://docs.oracle.com/en/java/javase/24/migrate/removed-tools-and-components.html): list of removed features and compatibility issues when upgrading.
- [Java SE 24 `java.naming` module](https://docs.oracle.com/en/java/javase/24/docs/api/java.naming/module-summary.html): documented properties, object factory filters, and LDAP provider policies.
- [Java RMI Guide – JDK 21](https://docs.oracle.com/en/java/javase/21/rmi/): principles for securing RMI, serialization filtering, `useCodebaseOnly`, and TLS.
- [Oracle RMI Enhancements in JDK 7](https://docs.oracle.com/javase/7/docs/technotes/guides/rmi/enhancements-7.html): rationale and impact of defaulting `useCodebaseOnly=true`.
- [JEP 407 – Remove RMI Activation](https://openjdk.org/jeps/407): scope of removing RMI Activation without removing all of RMI.
- [JEP 486 – Permanently Disable the Security Manager](https://openjdk.org/jeps/486): explanation of disabling the Security Manager mechanism in JDK 24.

When migrating on another JDK, consult the release notes and Javadoc matching the exact feature/update/vendor release running in production. Do not extrapolate one JDK's defaults to every other JDK.

## 17. Conclusion

JNDI, RMI, and remote code loading are related mechanisms serving different purposes. JNDI supports name and directory lookups; RMI enables remote method calls; loading classes via codebase is a historical capability for supplying code not present in the runtime. JDK security changes have restricted or removed many external code-loading paths, notably **JDK 24 permanently disabling JNDI LDAP/RMI remote code downloading and removing the corresponding `trustURLCodebase` properties**.

To migrate successfully, do not try to restore an insecure mechanism merely because a legacy application used it. Identify actual JNDI/RMI sources, distribute contracts and factories as trusted local artifacts, control object reconstruction/deserialization, apply TLS and network restrictions, and test both allowed and rejected flows. The desired outcome is not merely "the app runs again," but **new behavior that upholds contracts without weakening the system's trust boundaries**.
