# Adding `spring-boot-starter-data-rest` with Maven and Gradle

Spring Data REST exposes Spring Data repositories as hypermedia-driven REST resources. When you add the starter to a Spring Boot application with Spring MVC, Boot configures this integration automatically. You can create basic CRUD APIs from repositories without writing a controller for every operation.

The examples in this lesson use Spring Boot 4.1.2 and Java 17. These are illustrative versions; if your project already uses a different Spring Boot line, keep your project's current version and let that version's dependency management handle the Spring libraries.

## 1. Understanding the Starter's Role

Dependency coordinates:

- Group: `org.springframework.boot`
- Artifact: `spring-boot-starter-data-rest`

This starter provides Spring Data REST integration with Spring MVC and Spring Boot auto-configuration. It does not automatically create domain models, repositories, or a database management system. You still need an appropriate Spring Data module for your data store, such as:

- JPA: `spring-boot-starter-data-jpa` along with a JDBC driver.
- MongoDB: `spring-boot-starter-data-mongodb`.
- JDBC: `spring-boot-starter-data-jdbc`.

In the hands-on example below, JPA and H2 serve merely as the storage layer for demonstration. The dependency required to expose repositories over REST remains `spring-boot-starter-data-rest`.

Spring Data REST is built on Spring MVC. If your existing application is an MVC application, the starter already supplies the necessary web integration; do not add another web starter just to create Spring Data REST endpoints. If your application uses WebFlux exclusively, consider designing reactive endpoints with WebFlux instead of treating this starter as a reactive REST solution.

## 2. Adding the Dependency with Maven

If your project uses `spring-boot-starter-parent`, declare the Spring Boot version in the parent. Maven will pull compatible starter versions from the dependency management provided by the parent.

Example of the relevant section in `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>people-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Expose Spring Data repositories as REST resources -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>

        <!-- Storage backend used in the example -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

In an existing project that already has a parent and other dependencies, do not replace the parent just to add Spring Data REST. Simply add the following dependency inside `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
~~~

If your project does not inherit from `spring-boot-starter-parent`, you can import the `org.springframework.boot:spring-boot-dependencies` BOM inside `<dependencyManagement>`. Once the BOM is imported, starter dependencies also do not need individual version declarations. This keeps Spring Boot and Spring Data versions compatible with each other.

## 3. Adding the Dependency with Gradle

With Gradle Groovy DSL, declare the Spring Boot plugin and import the BOM so Gradle manages dependency versions:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    // Expose Spring Data repositories as REST resources
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'

    // Storage backend used in the example
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If your project already applies the `io.spring.dependency-management` plugin and it imports the Spring Boot BOM, you do not need to declare `implementation platform(...)` again. Simply add the dependencies to the existing `dependencies` block.

With Gradle Kotlin DSL in `build.gradle.kts`, the equivalent dependencies block is:

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.2"))
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("com.h2database:h2")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

In both DSLs, `implementation` places the library on the application's compile and runtime classpaths; `runtimeOnly` is suitable for JDBC drivers needed only at runtime. Do not declare an independent version for individual starters when the BOM already manages them.

## 4. Creating a Repository for Spring Data REST to Expose Endpoints

Simply adding the dependency will not expose any endpoints if the application has no repositories. You need a domain type, a corresponding repository, and a valid storage configuration.

The minimal example below uses JPA and H2. Place the classes in the same package or subpackages of the application class annotated with `@SpringBootApplication` so component/repository scanning finds them.

**Application entry point — `DemoApplication.java`:**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**Entity — `Person.java`:**

~~~java
package com.example.demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Person() {
        // No-arg constructor for JPA.
    }

    public Person(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

**Repository — `PersonRepository.java`:**

~~~java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

`JpaRepository` provides basic save, find, update, and delete operations. `@RepositoryRestResource(path = "people")` sets the collection path explicitly so the API does not rely on default resource-name derivation from the domain class name.

**Configuration — `src/main/resources/application.properties`:**

~~~properties
spring.datasource.url=jdbc:h2:mem:peopledb
spring.datasource.username=sa
spring.datasource.password=

# Use create-drop only for examples with an in-memory database.
spring.jpa.hibernate.ddl-auto=create-drop

# Set the prefix for Spring Data REST endpoints.
spring.data.rest.base-path=/api
~~~

When the application starts, Spring Boot configures Spring Data REST and Spring Data JPA. Repositories discovered within the scan scope are exported according to Spring Data REST's repository detection rules, unless the repository or configuration marks them as not exported.

With the configuration above, the collection API address is:

~~~text
http://localhost:8080/api/people
~~~

Common operations:

| HTTP request | Meaning |
| --- | --- |
| `GET /api/people` | Retrieve the list of `Person` resources |
| `POST /api/people` | Create a new `Person` |
| `GET /api/people/{id}` | Retrieve a single `Person` |
| `PUT /api/people/{id}` | Replace `Person` data |
| `PATCH /api/people/{id}` | Partially update a `Person` |
| `DELETE /api/people/{id}` | Delete a `Person` |

The specific HTTP methods exposed depend on the methods provided by the repository and the export configuration. The example above uses `JpaRepository`, so all common CRUD operations are available.

## 5. Running and Testing

With the Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`. Without the Maven Wrapper, use `mvn spring-boot:run`.

With the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`.

Once the application is running, send a request to create a record:

~~~bash
curl -i -X POST http://localhost:8080/api/people -H "Content-Type: application/json" -H "Accept: application/hal+json" --data '{"name":"An"}'
~~~

The expected result is HTTP `201 Created`. The response typically includes a `Location` header pointing to the newly created resource and a HAL representation. IDs are generated by the database, so exact values may vary.

Read the created collection:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/people
~~~

The expected result is HTTP `200 OK`. The HAL content includes `_links`; when the collection has data, elements typically appear inside `_embedded`. In PowerShell, invoke `curl.exe` to avoid the Windows PowerShell `curl` alias.

You can open the root endpoint `http://localhost:8080/api` to inspect the resource links published by Spring Data REST. If `spring.data.rest.base-path` is not set, resources are served from the root URI by default.

## 6. Key Considerations for Real Applications

- **Repositories are an API surface:** Spring Data REST can expose repository operations directly as HTTP APIs. Consequently, adding a public repository can expose new endpoints. Only export repositories that clients are actually permitted to access.
- **The starter does not replace a database:** `spring-boot-starter-data-rest` does not provide JPA, MongoDB, JDBC drivers, or connection settings on its own. Choose the appropriate Spring Data store and configure the datasource/connection separately.
- **No controllers needed for default CRUD:** Basic CRUD operations can be handled by exported repositories. When you need business workflows, transaction control, or specialized responses, consider explicit services and controllers rather than forcing all business logic into repository operations.
- **Hypermedia is part of the response:** Spring Data REST uses HAL so clients can navigate via links. Clients should read links from responses rather than assuming all URLs are hardcoded.
- **Control export scope:** You can use `@RepositoryRestResource(exported = false)` to prevent exporting a repository. You can set `path` and `collectionResourceRel` to control resource names and relations.
- **Secure before deploying:** Create, update, and delete endpoints can modify real data. Design authentication, authorization, method restrictions, and serialization controls before exposing the API in shared environments.
- **Do not mix Spring versions manually:** Avoid setting custom versions for Spring Data REST or Spring Framework alone when the Spring Boot BOM manages them. Overriding can produce incompatible library combinations.

## 7. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Maven reports a missing version for the starter | Project does not inherit the Boot parent and has not imported the Boot BOM | Check `<parent>` or `<dependencyManagement>` |
| Gradle cannot resolve dependencies | Missing `mavenCentral()`, BOM, or repository configuration | Check `repositories` and dependency constraints |
| Application starts but endpoints return 404 | Repository is outside the package scan, wrong base path, or repository is not exported | Check `@SpringBootApplication` package, `spring.data.rest.base-path`, and export annotations |
| Application fails on datasource startup | Missing store starter, JDBC driver, or connection settings | Check JPA/store dependency, URL, username, password, and database status |
| POST returns 401 or 403 | Security policy or CSRF policy blocks the request | Check Spring Security configuration and endpoint permissions |
| Client cannot parse the response | Client does not handle HAL media types/representations | Send `Accept: application/hal+json` and read links from the response |

## 8. Completion Checklist

- [ ] Added `spring-boot-starter-data-rest` to the appropriate build file.
- [ ] Starter version is managed by the same Spring Boot parent/BOM as the rest of the dependencies.
- [ ] Added the Spring Data store and database driver suitable for the application.
- [ ] Repository is placed in a package scanned by Spring Boot.
- [ ] Application starts successfully.
- [ ] Verified GET on the collection and POST of a resource.
- [ ] Reviewed which repositories are exported and security policies before deployment.

## Official Documentation

- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/intro.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/how-to/data-access.html)
