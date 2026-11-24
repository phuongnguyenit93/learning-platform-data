# Migrating a Project from a Custom Parent to BOM-Based Dependency Management

A Maven project often uses a **custom parent POM** to share dependency versions, properties, compiler settings, plugins, repositories, and build conventions across multiple modules. When multiple applications need to share dependency versions without inheriting an entire set of build conventions, the dependency management part can be extracted into a **BOM (Bill of Materials)**.

A BOM is a POM dedicated to managing dependency versions through **dependencyManagement**. A consuming project imports the BOM using a dependency with **type=pom** and **scope=import** inside its own dependencyManagement.

The migration must preserve existing build behavior. **A BOM replaces dependency version management; it does not replace all inheritance capabilities of a parent POM.** If the custom parent configures the Java compiler, plugin executions, Spring Boot packaging, repositories, or properties, those parts must either remain in a separate build parent or be moved into the project's own POM.

## 1. Parent POM and BOM Solve Two Different Problems

### 1.1. Parent POM: project configuration inheritance

A Maven project can declare one direct parent:

~~~xml
<parent>
    <groupId>com.acme.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>5.2.0</version>
</parent>
~~~

A parent POM has packaging pom and can provide many kinds of configuration to a child:

- Shared groupId, version, and metadata.
- Properties such as Java release, encoding, and plugin versions.
- DependencyManagement to manage versions/scopes of project dependencies.
- Dependencies inherited as actual dependencies of the child.
- Repositories and pluginRepositories.
- Build, plugins, pluginManagement, executions, and plugin configuration.
- Reporting, SCM, issue management, and other project metadata.
- Profiles and profile configuration effects activated by Maven rules.

When a child inherits from a parent, Maven constructs the effective POM from the child, parent, and Super POM. Therefore, removing a parent can change many behaviors beyond dependency versions. [Maven POM Reference: Inheritance](https://maven.apache.org/pom.html).

### 1.2. BOM: centralizing dependency versions

A BOM is also a Maven POM, typically with packaging pom, whose primary purpose is declaring dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>4.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

When a project imports a BOM, Maven merges the managed dependency entries from the BOM into the project's dependencyManagement. As a result, the project can declare dependencies without repeating versions.

**A BOM does not automatically add libraries to the classpath.** It only manages information for a dependency if that dependency is declared directly or appears through the dependency graph. The project must still declare the libraries it uses in dependencies. [Maven Dependency Mechanism: BOMs](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

### 1.3. Quick comparison

| Capability | Parent POM | Imported BOM |
| --- | --- | --- |
| Manage dependency versions | Yes | Yes |
| Manage transitive dependency versions | Yes, via dependencyManagement | Yes, via imported dependencyManagement |
| Provide actual dependencies to child | Possible via inherited dependencies | No |
| Inherit POM properties | Yes | No |
| Inherit build/plugin configuration | Yes | No |
| Inherit pluginManagement | Yes | No |
| Inherit repositories/reporting | Yes | No |
| Use alongside another parent | No, only one direct parent | Multiple BOMs can be imported |
| Standardize versions across build systems | Maven inheritance | Both Maven and Gradle can consume a BOM |

### 1.4. When should you extract a BOM?

Extracting dependency management into a BOM is useful when:

- Multiple applications need the same set of Spring, Jackson, logging, test libraries, or internal SDK versions.
- Applications use different parents yet still need synchronized dependencies.
- One team wants to keep its own build conventions without forcing other teams to inherit the entire custom parent.
- An internal library publishes multiple artifacts that must be consumed on the same release train.
- Gradle projects also need to consume dependency versions standardized in a Maven BOM.

If you only have one small project and the custom parent works well, creating a separate BOM may increase the number of POMs to maintain without commensurate benefit. Extract it when you need to share dependency policy independently from build policy.

## 2. BOM Import Mechanism in Maven

### 2.1. Required import structure

Maven only supports scope import for a dependency with type pom inside dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-dependencies-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Rules:

- type must be pom.
- scope must be import.
- The entry must be placed inside dependencyManagement.
- The BOM must be resolvable from the reactor/local/remote repository according to the build setup.
- Do not place a BOM import inside the application's dependencies block.

Importing is a mechanism that replaces the import entry with the list of managed dependencies from the imported POM. It does not create a runtime dependency on the BOM and does not add the libraries listed in the BOM to the classpath. [Maven Dependency Mechanism: Importing Dependencies](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

### 2.2. A managed dependency does not mean an added dependency

For example, the BOM manages a version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

A project needing that library still declares:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
~~~

Maven takes the version from dependencyManagement when the dependency does not specify its own version. If the project does not declare the dependency and it does not appear transitively either, Maven will not download the library just because the BOM has an entry for it.

### 2.3. A BOM manages both direct and transitive dependencies

Dependency management does not only let you omit versions on direct dependencies. It can also control the version of an artifact appearing as a transitive dependency.

~~~text
orders-api
   |
   +--> library-a
   |       |
   |       +--> jackson-core:2.17.x
   |
   +--> library-b
           |
           +--> jackson-core:2.18.x

Imported BOM:
   jackson-core:2.18.2
~~~

If the BOM manages jackson-core, Maven can use the managed version instead of the versions declared in the dependency POMs. This helps with alignment, but can also cause a dependent library to fail if its version is forced too low. Always inspect the dependency tree after changing a BOM. [Maven POM Reference: Dependency Management](https://maven.apache.org/pom.html).

### 2.4. A BOM does not manage transitive dependencies of Maven plugins

The Maven project dependency graph and the Maven plugin dependency graph are two separate scopes.

dependencyManagement manages project dependencies. It does not automatically apply to transitive dependencies of plugins within the same effective POM. If the custom parent previously pinned plugin versions or plugin dependencies, move those parts into build/plugins or build/pluginManagement. [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

## 3. Designing an Internal BOM

An internal BOM should have coordinates and a version independent of application artifacts:

~~~text
com.acme.platform:acme-dependencies-bom:2.4.0
~~~

It can import a framework BOM and add versions of internal libraries.

### 3.1. Project structure

~~~text
platform-dependencies/
└── pom.xml

orders-api/
└── pom.xml

billing-api/
└── pom.xml
~~~

platform-dependencies/pom.xml is the BOM. Applications can import the same BOM without having to inherit a single custom build parent.

### 3.2. Complete platform-dependencies/pom.xml example

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>acme-dependencies-bom</artifactId>
    <version>2.4.0</version>
    <packaging>pom</packaging>

    <name>Acme Dependencies BOM</name>
    <description>Managed dependency versions for Acme applications</description>

    <properties>
        <spring-boot.version>4.0.0</spring-boot.version>
        <observability.version>2.4.0</observability.version>
        <http-client.version>3.1.0</http-client.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <!-- Import the Spring Boot dependency catalog -->
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>

            <!-- Manage Acme internal libraries -->
            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>acme-observability-starter</artifactId>
                <version>${observability.version}</version>
            </dependency>

            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>acme-http-client</artifactId>
                <version>${http-client.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

In this example:

- packaging=pom defines the artifact as a POM package, not a JAR containing code.
- The Spring Boot BOM provides a set of versions tested together by the framework.
- The internal BOM adds coordinates for Acme libraries.
- The internal BOM version is 2.4.0; each library's version is managed separately.
- dependencies is not declared at the root because the goal is to provide version policy, not to automatically add libraries to applications.

Versions 4.0.0, 2.4.0, and 3.1.0 are illustrative only. In a real project, choose releases compatible with Java, Spring Boot, internal SDKs, and your organization's repository policy.

### 3.3. Multiple BOMs can be imported

A BOM can import multiple other BOMs:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.18.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This is a syntax example; do not arbitrarily combine BOMs with incompatible release trains. If the Spring Boot BOM already manages Jackson, importing an additional Jackson BOM may cause version conflicts. Only add a second BOM when there is a clear technical reason and you have inspected the dependency graph.

### 3.4. BOM properties are not exported like parent properties

When importing a BOM, Maven imports the BOM's managed dependency entries. It does not make all properties of the BOM directly referenceable in the consumer POM.

For example, a consumer should not assume it can use the spring-boot.version property simply because the internal BOM declared that property. If you need that version to configure a Maven plugin, declare the corresponding property in the consumer or inherit it from a build parent.

The versions already resolved inside the BOM are still used in the imported managed dependency entries.

## 4. Migrating a Child Project from a Custom Parent to a BOM

Suppose the project previously used this structure:

~~~text
company-parent
├── dependencyManagement
├── properties
├── build/pluginManagement
└── repositories

orders-api
└── inherits company-parent
~~~

The parent currently manages both Spring dependencies and build settings.

### 4.1. Before migration: child inherits custom parent

Old POM example:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.build</groupId>
        <artifactId>company-parent</artifactId>
        <version>5.2.0</version>
    </parent>

    <artifactId>orders-api</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-observability-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

The child does not need to declare versions because the parent provides dependencyManagement. It may also rely on the parent for groupId/version, Java compiler configuration, Spring Boot repackage execution, Surefire/Failsafe settings, or other plugins.

### 4.2. After migration: declare coordinates and import BOM

When removing the parent, the child needs to redeclare the information previously inherited. Example:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.orders</groupId>
    <artifactId>orders-api</artifactId>
    <version>1.8.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-boot.version>4.0.0</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>acme-dependencies-bom</artifactId>
                <version>2.4.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-observability-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Key changes:

- The child has its own groupId/version because it no longer inherits them from the parent.
- The BOM is imported in dependencyManagement.
- Dependencies remain in dependencies without repeating versions.
- Java release and source encoding are explicitly declared.
- Plugin versions and execution are configured directly because the BOM does not manage them.
- The Spring Boot Maven plugin has an explicit version and the repackage goal to create an executable Boot JAR when not inheriting spring-boot-starter-parent.

Plugin versions in the example should be verified against your Maven/JDK and Spring Boot release. If the project had configurations for compiler, Surefire, Failsafe, Checkstyle, JaCoCo, or other plugins in the custom parent, migrate the necessary configurations accordingly.

### 4.3. If you only want to separate dependency management while keeping a build parent

Removing the custom parent is not mandatory. A commonly suitable option is:

~~~text
company-build-parent
  ├── properties
  ├── build/plugins
  ├── pluginManagement
  └── imports acme-dependencies-bom

orders-api
  └── inherits company-build-parent
~~~

In this setup, the custom parent still provides the compiler, plugins, repositories, and build conventions; the BOM serves as the source for managing dependency versions.

In company-build-parent/pom.xml:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-dependencies-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The child continues declaring the parent as before. This allows different projects to share the BOM even if they do not share the build parent. It separates the two responsibilities without copying all plugin configurations into every application.

### 4.4. If you need to keep a custom parent and use the Spring Boot BOM

Maven allows only one direct parent. If a project already has a custom parent, it cannot simultaneously declare spring-boot-starter-parent as a second parent.

Instead:

1. Keep the custom parent if you need its build conventions.
2. Import the spring-boot-dependencies BOM in the dependencyManagement of the custom parent or child.
3. Check Java/compiler properties and encoding.
4. Configure spring-boot-maven-plugin and the repackage goal if the current parent does not provide them.
5. Check resource filtering defaults and plugin executions that the Spring Boot parent usually sets up.

The Spring Boot starter parent provides many defaults beyond dependency versions, including compiler level, encoding, parameter metadata, resource filtering, and plugin configuration. Importing the BOM alone only provides dependency management; it does not include all those defaults. [Spring Boot Maven: Using the Plugin and Parent](https://docs.spring.io/spring-boot/maven-plugin/using.html).

## 5. Moving Custom Parent Contents to the Appropriate Places

Before removing the parent, make an inventory table. Do not move everything from the parent into the BOM.

| Content in custom parent | Appropriate destination |
| --- | --- |
| Dependency versions in dependencyManagement | BOM |
| Importing framework BOMs | BOM or build parent |
| Java/compiler version | Build parent or child properties/plugin config |
| Source encoding | Build parent or child |
| Plugin versions | pluginManagement or build/plugins |
| Plugin executions/configuration | Build parent or build/plugins |
| Dependencies declared directly in parent | Child dependencies or a starter/library artifact |
| Repositories/pluginRepositories | Build parent, child, or settings/repository policy |
| Profiles affecting the build | Build parent or child POM |
| Reporting configuration | Build parent or child |
| Default groupId/version | Parent or declared explicitly in each project |
| SCM, organization, license metadata | Parent or project POM |
| distributionManagement | Build/release parent or separate release config |

### 5.1. Watch out for dependencies inherited from the parent

There are two very different sections in a POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Only manages version/scope/configuration -->
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- Actually adds the dependency to the project -->
</dependencies>
~~~

If the custom parent had a dependencies block, the child inherited them as project dependencies. When replacing the parent with a BOM, those dependencies will no longer appear automatically.

Check each dependency:

- If every application genuinely needs the library, create an internal starter/library or declare it explicitly in consumers.
- If only some applications need it, declare it in each application that uses it.
- If you only want to manage the version, move the entry to the BOM while still declaring the dependency in the consumer.
- Do not add all dependencies to the BOM expecting them to be downloaded automatically.

### 5.2. Watch out for properties

Common properties in a parent:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven-surefire-plugin.version>3.5.2</maven-surefire-plugin.version>
</properties>
~~~

This is build configuration, not a dependency catalog. Keep them in a build parent or move them to the consumer POM.

A BOM can use its own properties to declare versions for managed dependencies. However, a consumer importing the BOM does not inherit those properties the way it does when inheriting from a parent.

### 5.3. Watch out for pluginManagement and plugins

pluginManagement provides default plugin versions/configurations for plugins used in the build. build/plugins declares the plugins used and may contain executions bound to the lifecycle.

A BOM does not import these two sections. When removing the parent, check at least:

- Compiler plugin and Java release.
- Surefire/Failsafe test execution.
- Spring Boot repackage.
- Resource filtering.
- Annotation processors.
- JaCoCo, Checkstyle, Spotless, PMD, or Sonar integration.
- Packaging, source/Javadoc attachment, and signing plugins.
- Plugin versions to avoid relying on implicit default versions.

Do not confuse dependencyManagement with pluginManagement. Managing the version of spring-boot-starter-web does not manage the version of spring-boot-maven-plugin.

## 6. Precedence Rules When Multiple BOMs Manage the Same Dependency

When importing multiple BOMs, order and overrides must be controlled explicitly.

### 6.1. A direct entry in the consuming POM can override an imported BOM

For example, the project wants to use a specific version for Jackson:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>acme-dependencies-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

A direct entry in the current POM can override an entry imported from a BOM. Only override when there is a clear reason, such as a security fix, compatibility requirement, or a separately tested release train.

Local overrides reduce consistency across consumers. If multiple projects need the same override, updating the BOM and releasing a new BOM version is easier to control.

### 6.2. The earlier imported BOM takes precedence when two BOMs share an entry

Suppose BOM X manages library-a version 1.1 and BOM Y manages the same artifact version 1.2. If the consumer imports X before Y and does not declare a direct entry, Maven picks version 1.1 in this conflict case.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>bom-x</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>bom-y</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Maven docs illustrate that the first imported BOM wins when two imported BOMs manage the same dependency and the consuming POM has no direct entry. [Maven: Import order and dependency management precedence](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

Do not rely on import order as an implicit conflict-resolution mechanism. Choose one BOM as the primary source, then declare explicit overrides in the internal BOM or consumer if genuinely necessary.

### 6.3. Parent dependencyManagement and local dependencyManagement

If the project still inherits from a build parent, dependencyManagement declared directly in the child can override management from the parent. Imported BOM entries are also merged into dependencyManagement according to Maven rules.

To avoid unpredictable results:

- Do not manage the same artifact in multiple places unless necessary.
- If an override is needed, declare a direct entry with an explicit version and clear rationale.
- Inspect the effective POM after changing BOM order.
- Inspect the dependency tree, especially important transitive dependencies.

### 6.4. Dependencies declaring their own version

When the goal is to use the version from the BOM, dependencies in the dependencies block should omit the version:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>acme-http-client</artifactId>
</dependency>
~~~

If a direct dependency still declares its own version, that acts as a local override and should be reviewed. Do not let scattered versions in child POMs accidentally deviate from BOM policy.

### 6.5. Maven matches dependencies by full coordinates

dependencyManagement matching is not based solely on groupId and artifactId in all cases. The management key includes:

- groupId
- artifactId
- type
- classifier

For a JAR without a classifier, the default type is jar, so usually only groupId/artifactId is needed. For a test-jar, WAR, or artifact with a classifier, declare the appropriate type/classifier so Maven matches the entry properly. [Maven Dependency Management: Matching Coordinates](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

## 7. Pitfalls When Designing and Publishing a BOM

### 7.1. Placing the BOM in the same reactor and importing it from a submodule

Maven docs warn against importing a POM defined in a submodule of the current project in a way that requires resolving the BOM before the artifact can be resolved. The safe approach is to publish/install the BOM beforehand, or organize dependency management via parent inheritance within the same reactor when appropriate.

Example of a structure prone to issues:

~~~text
root/
├── pom.xml
├── bom/
│   └── pom.xml
└── app/
    └── pom.xml  (imports bom module)
~~~

If app needs to import bom as an external BOM, ensure the BOM has already been installed in the local repository or published to a repository accessible to the build before resolving the consumer POM. Do not assume Maven automatically resolves every BOM import from a sibling module just because the root POM aggregates them. [Maven BOM import restrictions](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

### 7.2. Circular imports

Do not create cycles:

~~~text
BOM A imports BOM B
BOM B imports BOM A
~~~

Nor should you design a POM that imports a BOM while that BOM inherits back from the POM importing it. Maven cannot construct an effective model when there is a cycle.

Design the dependency catalog as a one-way flow: platform BOM → internal BOM → application consumers.

### 7.3. A BOM does not automatically become a transitive dependency of a library

If library A imports BOM X in A's POM, application B depending on A should not assume all dependency management from BOM X is automatically passed to B like a parent. Dependency management is not a transitive runtime dependency.

If B needs the same version policy, B should import the BOM directly or inherit from a parent/build platform that imports that BOM.

### 7.4. Do not treat a BOM version as a mutable release

Do not overwrite the contents of an already released BOM under the same version. If you change dependency versions, exclusions, or managed metadata, release a new BOM version, such as 2.4.1.

A BOM is part of the build contract. The same BOM coordinates must have stable contents so developers and CI resolve the same effective dependency management.

### 7.5. Do not blindly force an older dependency version

Dependency management can override transitive versions. If a library requires a newer minimum version, a BOM managing an older version may allow the build to succeed while failing at runtime.

Check release notes, compatibility matrices, CVE fixes, and the dependency tree before upgrading/downgrading versions.

### 7.6. Do not manage everything in one giant BOM

A BOM can become hard to upgrade if it contains many unrelated groups of dependencies. Consider splitting:

- Framework BOM: Spring Boot, Jackson, Netty.
- Internal platform BOM: organization's SDKs, starters, clients.
- Test BOM: JUnit, Mockito, Testcontainers.
- Data/observability BOM if they have separate release trains.

Only split when groups have different lifecycles and compatibility policies. Too many BOMs increase import-order conflicts and make tracing versions harder.

## 8. Spring Boot: Using the BOM Without Inheriting Starter Parent

Spring Boot provides two important artifacts:

- spring-boot-starter-parent: parent POM with build defaults and dependency management.
- spring-boot-dependencies: BOM containing dependency versions managed by Spring Boot.

If a project cannot use spring-boot-starter-parent because it already has a custom parent, it can import spring-boot-dependencies in dependencyManagement. You must then configure the plugin/build defaults previously provided by the parent yourself.

### 8.1. Configuring direct import of the Spring Boot BOM

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare the Spring Boot starters the project actually uses without versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The Spring Boot BOM manages versions of dependencies curated in the release train. The specific version must match the Boot release the project uses. [Spring Boot Build Systems: Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html).

### 8.2. Configuring the plugin without starter parent

When not inheriting the starter parent, add the plugin and explicit execution:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>4.0.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Without the repackage execution, the project may produce a regular Maven JAR instead of the desired executable Spring Boot JAR. You also need to migrate Java release, encoding, resource filtering, and required plugin versions from the old parent.

### 8.3. Do not arbitrarily mix Spring Boot versions

Keep the versions of:

- spring-boot-dependencies BOM.
- spring-boot-maven-plugin.
- Spring Boot starters.
- Other Spring Boot build plugins.

within the same compatible release train. Do not import a 4.x BOM while running a 3.x plugin or overriding certain Spring Framework artifacts without a compatibility review.

## 9. Gradle Can Consume a Maven BOM

Although this lesson focuses on Maven, a BOM is also useful when some projects use Gradle. Gradle supports Maven BOMs through platform() and enforcedPlatform().

### 9.1. Importing a BOM with platform()

Groovy DSL:

~~~groovy
dependencies {
    implementation platform(
        'com.acme.platform:acme-dependencies-bom:2.4.0'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.acme.platform:acme-observability-starter'
}
~~~

Kotlin DSL:

~~~kotlin
dependencies {
    implementation(
        platform("com.acme.platform:acme-dependencies-bom:2.4.0")
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("com.acme.platform:acme-observability-starter")
}
~~~

Dependencies receive versions provided by the BOM. platform() feeds dependency constraints from the BOM into Gradle resolution. Gradle can resolve final versions based on constraints and its graph. [Gradle Platforms: Importing a BOM](https://docs.gradle.org/current/userguide/platforms.html).

### 9.2. platform() and enforcedPlatform()

| Usage | Meaning |
| --- | --- |
| platform(bom) | Applies dependency constraints as version recommendations/constraints in Gradle resolution |
| enforcedPlatform(bom) | Applies versions in a stricter, enforced manner that can override other versions in the graph |

Do not choose enforcedPlatform() just to "ensure synchronization." It can impose versions on unintended consumers and make the dependency graph hard to coordinate. Use platform() by default; only use an enforced platform when policy truly requires it and you have inspected the graph. [Spring Boot Gradle Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html).

### 9.3. Gradle BOM does not replace plugin management

A BOM does not manage Gradle plugins. Versions of the Spring Boot Gradle plugin, Java toolchain, and build plugins still need to be managed via the plugins DSL, version catalogs, or convention plugins.

If the goal is sharing dependency versions between Maven and Gradle, a BOM is a useful common interface. If the goal is sharing all build conventions, each build system still needs its own mechanism.

## 10. Controlled Migration Process

Do not remove the parent and change dependency versions all at once without a baseline. Break the migration into verifiable steps.

### Step 1 — create a baseline before changes

Run on the current branch:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom-before.xml
~~~

Record the dependency tree:

~~~bash
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree-before.txt
~~~

Save test/package results and the following information:

- Java/Maven versions.
- GroupId/artifactId/version of direct dependencies.
- Important transitive versions.
- Compiler release and encoding.
- Plugin versions, executions, and configuration.
- Spring Boot repackage output.
- Active profiles.
- Repositories and release behavior.

The Effective POM helps inspect the configuration after Maven merges parent and child. The dependency tree shows which dependencies actually appear and which versions are selected.

### Step 2 — inventory the custom parent

Read the custom parent and categorize each section into:

1. Dependency management to move to the BOM.
2. Build configuration to keep in parent/plugin management.
3. Actually inherited dependencies.
4. Metadata and release configuration.
5. Profiles or properties used by the child.

Do not delete the parent before knowing which parts of the parent the child depends on.

### Step 3 — create the BOM

Create a new POM with packaging pom. Move managed dependency versions into dependencyManagement, import framework BOMs if appropriate, add internal managed dependencies, and verify coordinates.

Do not move build/plugins, pluginManagement, compiler configuration, or application dependencies into the BOM expecting them to be inherited.

### Step 4 — publish or install the BOM

In local development, you can install the BOM to the local repository:

~~~bash
mvn -f platform-dependencies/pom.xml clean install
~~~

In CI/release, publish the BOM to an internal Maven repository or an appropriate managed repository. Consumers must be able to resolve the BOM coordinates before building.

Use an immutable release version with appropriate write permissions. Do not use a snapshot/mutable release BOM for production without an explicit policy.

### Step 5 — update a pilot consumer

Import the BOM into one application first. Remove versions from dependencies managed by the BOM. Keep intentional version overrides and document the reason.

If removing the parent, add required groupId/version, properties, and build plugin configuration. If build conventions are still needed, keep the parent or create a thin build parent that imports the BOM.

### Step 6 — compare effective POM and dependency tree

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom-after.xml
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree-after.txt
~~~

Compare before/after:

- Are direct dependencies still complete?
- Did transitive versions change unexpectedly?
- Are test/runtime scopes preserved?
- Were any exclusions lost?
- Are plugin versions and executions still correct?
- Are Java compiler release/encoding still accurate?
- Does Spring Boot repackage produce an executable JAR?

### Step 7 — run full validation

~~~bash
mvn clean verify
~~~

If the project has integration tests or required profiles, run those exact profiles. Check package outputs, reports, and plugin executions.

### Step 8 — roll out to remaining consumers

Once the first application passes, update other consumers to the same BOM. Avoid simultaneously changing the BOM version, Spring Boot version, Java release, and plugin major versions unless necessary; changing one group at a time makes regressions easier to pinpoint.

### Step 9 — retire the old parent when no consumers remain

Only stop publishing/maintaining the custom parent when:

- No project still needs the build conventions of that parent.
- All previously inherited dependencies have been categorized.
- All necessary plugin executions/configurations have been migrated.
- Consumers have imported the BOM and build successfully.
- Release, CI, and rollback paths have been verified.

If the parent still provides value for build conventions, keep it and let the BOM act as an independent source of dependency management.

## 11. Useful Maven Commands During Migration

| Command | Purpose |
| --- | --- |
| mvn help:effective-pom | View the effective POM after inheritance/imports |
| mvn dependency:tree | View the dependency graph and selected versions |
| mvn dependency:tree -Dverbose | Show additional conflict/omitted node details |
| mvn dependency:analyze | Help detect used/undeclared/unused dependencies |
| mvn clean verify | Run lifecycle through verify, including tests/package |
| mvn -U clean verify | Force checking snapshot/release metadata updates per Maven behavior |
| mvn help:effective-settings | View effective settings to diagnose repositories/mirrors |

Example saving outputs for comparison:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree.txt
mvn dependency:analyze
mvn clean verify
~~~

If the dependency tree differs from before migration, identify exactly which artifact/version changed. Do not rely solely on the build passing: a dependency downgrade can still cause runtime errors or compatibility issues not covered by unit tests.

## 12. Checking Dependency Convergence and Version Conflicts

When a BOM manages many libraries, intentional and unintentional version conflicts should be checked.

### 12.1. Dependency tree

~~~bash
mvn dependency:tree -Dverbose
~~~

A dependency tree can reveal selected versions or versions omitted due to mediation. Pay special attention to:

- Logging APIs and implementations.
- Jackson modules.
- Netty components.
- Spring Framework modules.
- Database drivers.
- HTTP clients.
- Test frameworks.
- Internal SDKs.

### 12.2. Maven Enforcer

You can use the Maven Enforcer Plugin with the dependency convergence rule to fail the build when multiple paths request inconsistent versions:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

This rule detects version conflicts that need attention, though not every conflict is automatically an error. Some libraries have compatibility policies allowing multiple versions on separate branches. Review intentional exceptions and do not disable the rule broadly just to pass the build.

### 12.3. Do not use dependencyManagement to hide missing dependency declarations

If source code directly uses a library, declare it directly in dependencies rather than relying on another dependency pulling it in transitively.

This ensures the POM accurately reflects source code dependencies and reduces the risk of broken builds when an upstream library changes its dependency graph. Maven also recommends explicitly declaring dependencies directly used by the project. [Maven: Transitive Dependency Best Practices](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

## 13. Common Errors When Migrating from Parent to BOM

| Symptom | Cause | Fix |
| --- | --- | --- |
| Maven reports missing version | Dependency not in BOM or wrong import | Check coordinates, type/classifier, and effective POM |
| BOM cannot be resolved | BOM not published/installed or missing repo permissions | Install locally to test or publish BOM before consumer |
| BOM import reports scope/type error | Import not in dependencyManagement or missing type pom | Fix import structure |
| Build passes but library missing from classpath | Entry only added in dependencyManagement | Declare dependency in dependencies |
| After removing parent, many dependencies vanish | Parent had actually inherited dependencies | Move needed dependencies to consumer/starter |
| Java compiler uses wrong version | Parent previously configured compiler/toolchain | Declare maven.compiler.release and compiler plugin |
| Spring Boot JAR is not executable | Lost repackage execution from starter/custom parent | Add spring-boot-maven-plugin and repackage goal |
| Plugin version changes unexpectedly | pluginManagement lost when removing parent | Move plugin versions/config to build parent or child |
| Maven picks version from another BOM | Duplicate artifact across BOM imports, different import order | Standardize primary BOM and declare overrides explicitly |
| Transitive dependency downgraded | BOM manages lower version than required by dependency | Inspect dependency tree and update BOM/override |
| Plugin still pulls old version | dependencyManagement does not apply to plugin transitive deps | Manage plugins separately in pluginManagement |
| Consumer does not see BOM properties | BOM import does not inherit properties like a parent | Declare properties in consumer/build parent |
| Local passes but CI fails | BOM unpublished, different repository/mirror or credentials | Check repository resolution in CI |
| Module in reactor cannot resolve sibling BOM | Imported BOM is in a submodule of the same reactor | Publish/install BOM first or reorganize model |
| Effective POM has dependency but dependency tree does not | Entry is only managed, not declared/transitive | Check actual dependencies |
| Dependency convergence fails | Graph branches require inconsistent versions | Inspect conflict, choose compatible version, document override |

## 14. Migration Completion Checklist

### BOM

- [ ] BOM has clear groupId/artifactId/version coordinates.
- [ ] packaging is set to pom.
- [ ] Shared dependency versions are inside dependencyManagement.
- [ ] External BOMs are imported with type pom and scope import.
- [ ] BOM only manages needed dependencies without unintended actual dependencies.
- [ ] BOM version is an immutable release.
- [ ] Imported BOMs have no cycles and conflicts are resolved.

### Consumer POM

- [ ] Correct BOM version is imported.
- [ ] Used dependencies remain declared in dependencies.
- [ ] Versions removed from BOM-managed dependencies, except intentional overrides.
- [ ] groupId/version declared if no longer provided by a parent.
- [ ] Required compiler/encoding properties migrated.
- [ ] Plugin versions, executions, and configurations preserved.
- [ ] Parent dependencies categorized and migrated properly.
- [ ] Repositories, profiles, reporting, and release configuration checked.

### Spring Boot

- [ ] Spring Boot BOM and plugin use compatible versions.
- [ ] If not using starter parent, compiler/encoding configured.
- [ ] spring-boot-maven-plugin has an explicit version.
- [ ] Goal repackage runs when an executable Boot JAR is needed.
- [ ] Resource filtering and important plugin defaults verified.

### CI and release

- [ ] BOM published prior to consumer builds.
- [ ] Before/after effective POM compared.
- [ ] Before/after dependency tree reviewed.
- [ ] Dependency convergence/conflicts addressed.
- [ ] mvn clean verify passes.
- [ ] Artifact packaging and runtime smoke test pass.
- [ ] Repository credentials/mirrors work in CI.
- [ ] BOM version recorded in release record for traceability.

## 15. Self-Check Questions

**Question 1.** What is a BOM in Maven?

**Answer:** A POM, typically with packaging pom, that provides a list of managed dependencies so consumers share a common version policy.

**Question 2.** Why must a BOM import be placed inside dependencyManagement?

**Answer:** Because scope import is only valid for dependencies of type pom inside dependencyManagement; Maven replaces that entry with the managed dependencies from the BOM.

**Question 3.** Does importing a BOM automatically add all libraries to the classpath?

**Answer:** No. A BOM only manages versions/configuration. The project still declares actual dependencies in dependencies.

**Question 4.** Can multiple BOMs be used in one POM?

**Answer:** Yes. When BOMs manage the same dependency, import order affects the result; the BOM imported earlier wins if the consumer does not declare a direct override entry.

**Question 5.** Can a direct dependencyManagement entry in the consumer override an imported BOM?

**Answer:** Yes. Use a direct override when there is a clear rationale and compatibility has been verified.

**Question 6.** Does importing a BOM inherit properties and pluginManagement from the imported POM?

**Answer:** No. It imports dependencyManagement entries. Properties, build/plugin configuration, and reporting are not inherited like parent inheritance.

**Question 7.** If a custom parent has dependencies in its dependencies section, what happens when the parent is removed?

**Answer:** Those inherited dependencies do not appear automatically via BOM import. You must declare them in the consumer or provide them via an appropriate starter/library.

**Question 8.** Why doesn't Maven dependencyManagement manage transitive dependencies of Maven plugins?

**Answer:** The plugin dependency graph is processed separately. Plugin versions/configurations must be managed in build/plugins or pluginManagement.

**Question 9.** When not inheriting the Spring Boot starter parent, what needs attention?

**Answer:** Import the spring-boot-dependencies BOM to manage library versions, while also configuring the Java compiler, encoding, plugin versions, and required Spring Boot repackage execution yourself.

**Question 10.** How do you prove the migration did not introduce unintended dependency graph changes?

**Answer:** Compare before/after effective POM and dependency trees, run dependency analysis/convergence checks, then run clean verify and smoke-test the artifact.

**Question 11.** Can a BOM be imported from a submodule of the same reactor?

**Answer:** Maven docs warn against importing a BOM defined in a submodule of the current project in a way that requires resolving the POM before that module is built. Publish/install the BOM first or choose an appropriate parent/inheritance structure.

**Question 12.** How does Gradle consume a Maven BOM?

**Answer:** Use platform(bom) to apply dependency constraints; enforcedPlatform(bom) applies stricter constraints and should be used cautiously.

## 16. Official References

- Apache Maven — [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependencyManagement, import scope, BOM, conflict resolution, and transitive dependencies.
- Apache Maven — [POM Reference](https://maven.apache.org/pom.html): parent inheritance, properties, build, pluginManagement, and dependencyManagement.
- Apache Maven — [Maven Help Plugin: effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): inspecting effective POM after inheritance and imports.
- Apache Maven — [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): dependency tree and dependency analysis.
- Spring Boot — [Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): dependency management and Spring Boot BOM.
- Spring Boot — [Using the Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html): differences between starter parent and dependency BOM, plugin defaults.
- Gradle — [Platforms](https://docs.gradle.org/current/userguide/platforms.html): importing Maven BOMs via platform/enforcedPlatform.
- Gradle — [Centralizing Dependencies](https://docs.gradle.org/current/userguide/centralizing_dependencies.html): centralized dependency version management.

**Remember:** A Parent POM is a mechanism for inheriting project configuration; a BOM is a dependency catalog imported into dependencyManagement. Move dependency versions to the BOM, keep build conventions in an appropriate parent/build configuration, declare actual dependencies in consumers, and verify both effective POM and dependency tree before releasing the migration.
