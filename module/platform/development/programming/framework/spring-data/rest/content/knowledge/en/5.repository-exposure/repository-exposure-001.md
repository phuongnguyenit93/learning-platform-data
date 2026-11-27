# @RepositoryRestResource and Properties Controlling Resource Exposure

## Objectives

After this lesson, you will be able to:

- Explain how Spring Data REST exposes a Spring Data repository as a REST resource.
- Customize collection URLs and hypermedia relation names using **path**, **collectionResourceRel**, and **itemResourceRel**.
- Enable or hide a repository and individual query methods using **exported**.
- Configure excerpt projections and resource descriptions.
- Distinguish the responsibilities of **@RepositoryRestResource** and **@RestResource**, while recognizing the security limitations of these two annotations.

## 1. Spring Data REST Exposes Repositories

Spring Data REST can automatically generate HTTP endpoints from Spring Data repositories detected by the application. For a repository managing **Member**, the framework can provide a collection endpoint, an item endpoint, and search endpoints for eligible query methods.

Example:

~~~java
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

This repository can be exposed as a REST resource without writing a dedicated CRUD controller. If the application configures the base path as **/api**, the endpoints typically take the following form:

| HTTP | Endpoint | Meaning |
|---|---|---|
| GET | /api/members | Read the collection; may support paging and sorting |
| POST | /api/members | Create a member |
| GET | /api/members/{id} | Read a member |
| PUT / PATCH | /api/members/{id} | Update a member |
| DELETE | /api/members/{id} | Delete a member |
| GET | /api/members/search/... | Invoke an exposed query method |

The exact endpoints depend on the repository type, available repository methods, and application configuration. Spring Data REST typically returns representations in HAL format, where the **_links** field describes related resources and available next actions.

**@RepositoryRestResource** is used to control how a repository is exposed. This annotation is placed on the repository interface. You do not need this annotation just for Spring Data REST to detect the repository; it is useful when you need to name, change the path, hide, or add metadata to the resource.

## 2. @RepositoryRestResource and Its Main Properties

Import the annotation:

~~~java
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
~~~

Example:

~~~java
@RepositoryRestResource(
    path = "members",
    collectionResourceRel = "members",
    itemResourceRel = "member"
)
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

With base path **/api**, the collection is accessed at **/api/members**. The three properties above have distinct roles:

| Property | Controls | Example |
|---|---|---|
| **path** | URL path segment of the repository resource | **members** |
| **collectionResourceRel** | Hypermedia relation name pointing to the collection | **members** |
| **itemResourceRel** | Hypermedia relation name used for an item | **member** |

### path: HTTP Path Segment

**path** determines the URL segment that clients use to access the resource. Changing **path** from the default name to **members** makes the collection URL **/api/members**.

This is the repository's path configuration. It does not change the Java interface name, the database table name, or entity property names. Nor does it replace the application-wide base path.

### collectionResourceRel and itemResourceRel: HAL Relation Names

Spring Data REST provides hypermedia links so clients can discover resources. The **collectionResourceRel** and **itemResourceRel** properties control the relation names of those links.

Distinguish between them:

- **path** answers the question: which URL does the client call?
- **collectionResourceRel** and **itemResourceRel** answer the question: under which relation name does the client see the link in the representation?

Relation names are part of the hypermedia contract. If clients rely on these relation names, choose stable and consistent names. Changing a relation name can affect clients even when the URL stays the same.

### exported: Whether to Expose the Repository

By default, a repository is exposed. Set **exported = false** to keep a repository out of the REST API:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
~~~

The repository remains a Spring Data repository and can still be injected, called from services, or used in Java code. This setting only controls whether Spring Data REST publishes the resource.

This is a suitable choice for internal repositories, operational data, or repositories intended strictly for server-side processing flows.

### excerptProjection: Summary Representation for Collections

A collection can contain many entities with numerous properties. If clients only need a few basic fields, you can set an excerpt projection:

~~~java
@RepositoryRestResource(
    path = "members",
    excerptProjection = MemberSummary.class
)
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

Projection:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "memberSummary", types = Member.class)
public interface MemberSummary {
    String getName();
    String getEmailAddress();
}
~~~

The projection describes the properties that appear in the summary representation. With an excerpt projection, Spring Data REST uses this projection for items embedded inside the collection resource. Clients can still access individual item resources according to the API's projection rules.

Excerpt projections help limit payload size and create convenient representations for list views. They do not replace DTO/service mapping for complex business logic, nor are they an authorization mechanism for hiding sensitive data.

### Describing Collections and Items

You can provide descriptions for collection and item resources using **Description**:

~~~java
import org.springframework.data.rest.core.annotation.Description;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "members",
    collectionResourceDescription = @Description("Member list"),
    itemResourceDescription = @Description("Details of a member")
)
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

These descriptions are Spring Data REST metadata that help document resources in hypermedia/ALPS metadata. They do not automatically generate OpenAPI documentation or replace the API documentation used by the project.

## 3. Customizing Query Methods with @RestResource

**@RepositoryRestResource** controls the repository resource at the interface level. **@RestResource** controls how an individual method is exposed.

Import:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;
~~~

Query method example:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-email", rel = "by-email")
    List<Member> findByEmailAddress(@Param("email") String email);
}
~~~

Spring Data REST exposes query methods under the search resource. With base path **/api**, clients can call:

~~~http
GET /api/members/search/by-email?email=lan%40example.com
~~~

In this configuration:

- **path = "by-email"** sets the URL segment of the query method.
- **rel = "by-email"** sets the relation name of the search link.
- **@Param("email")** specifies the query parameter name sent by the client.

**@Param** is especially useful so that the HTTP parameter name does not depend on whether the compiler preserves Java parameter names.

You can also hide a query method from the REST API:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-email", rel = "by-email")
    List<Member> findByEmailAddress(@Param("email") String email);

    @RestResource(exported = false)
    List<Member> findByInternalFlagTrue();
}
~~~

**findByInternalFlagTrue()** can still be called by server-side code through the repository. Spring Data REST does not expose this method as a search endpoint.

You can use **path**, **rel**, **exported**, and description metadata on **@RestResource** to control each method. Ensure that query method paths within the same resource do not conflict.

## 4. Combined Example

Suppose an application has a **Member** entity and needs to expose a member list to clients. Clients need to:

1. Access the collection via the URL **/api/members**.
2. Receive clear relation names in HAL.
3. See a summary representation in the list.
4. Search by email.
5. Not access a query method intended only for internal use.

The repository can be declared as follows:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.Description;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "members",
    collectionResourceRel = "members",
    itemResourceRel = "member",
    excerptProjection = MemberSummary.class,
    collectionResourceDescription =
        @Description("Member list"),
    itemResourceDescription =
        @Description("Details of a member")
)
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-email", rel = "by-email")
    List<Member> findByEmailAddress(@Param("email") String email);

    @RestResource(exported = false)
    List<Member> findByInternalFlagTrue();
}
~~~

Projection:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "memberSummary", types = Member.class)
public interface MemberSummary {
    String getName();
    String getEmailAddress();
}
~~~

The imports/packages of **Member**, **MemberSummary**, and the repository must be within the component/repository/projection scanning scope configured by the application. The example uses **JpaRepository** for illustration; **@RepositoryRestResource** applies to Spring Data repositories managed by Spring Data REST, not just JPA.

## 5. Base Path Is an Application-Level Configuration

**path** on **@RepositoryRestResource** only sets the path for a single repository. If you want all REST repositories to reside under **/api**, configure the base path at the Spring Data REST level:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

After this configuration, a repository with **path = "members"** is accessed under **/api/members**.

Do not confuse base path with **path**:

- Base path applies to the entire Spring Data REST API.
- **path** sets the URL name for a single repository resource.
- **collectionResourceRel** and **itemResourceRel** set hypermedia relation names.

If the project already has a **RepositoryRestConfigurer**, add this setting to the existing mechanism rather than creating multiple places that modify the base path.

## 6. Testing Endpoints

After the application starts, you can inspect the API root and collection:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/members
~~~

Test the query method:

~~~bash
curl -i -G -H "Accept: application/hal+json" --data-urlencode "email=lan@example.com" http://localhost:8080/api/members/search/by-email
~~~

Observe the status code, response body, and **_links**. The API root helps identify exposed resources; the collection shows the actual representation and relation names; the search link shows whether the query method is published.

When testing write operations, use test data and verify that the request body matches the entity/associations managed by the repository.

## 7. Boundaries and Common Pitfalls

### Hiding a Resource Is Not Access Security

**exported = false** controls whether Spring Data REST publishes an endpoint. It is not an authorization rule and does not replace Spring Security.

For exposed resources, configure authentication, authorization by HTTP method/resource, and data access checks at the appropriate layer. Projections are also not a mechanism for protecting sensitive data: if a field must not be disclosed, control representations and access permissions through the application's security design.

### Changing path Without Changing Relation Names

If the URL changes while the relation name stays the same, HAL clients can continue discovering the link by the old relation name. Conversely, changing a relation name does not necessarily change the URL. When designing APIs for hypermedia clients, manage both parts as a single contract.

### Repository Does Not Appear

Check the Spring Data REST dependency, repository scanning scope, base path, and the **exported** value. Ensure the repository is a valid Spring Data interface and is configured for the persistence module in use.

### Search Endpoint Does Not Appear

Check whether the method is a query method supported by Spring Data, whether it is hidden by **@RestResource(exported = false)**, and whether its path conflicts with another method. Verify query parameter names with **@Param**.

### Projection Is Not Applied

Verify that the projection references the correct domain type, that getters exist, and that the projection is discovered by Spring Data REST according to the application's configuration/packages. Confirm you are inspecting the collection representation, because an excerpt projection is used for items embedded in a collection.

### Using Spring Data REST for Complex Business Flows

Spring Data REST is suitable when the API can directly reflect repository operations. If an endpoint needs to coordinate multiple repositories, apply business rules, call external systems, orchestrate transactions, or return use-case-specific DTOs, consider a dedicated service and controller. Repository exposure annotations do not replace a business orchestration layer.

## 8. Key Takeaways

- Use **@RepositoryRestResource** to configure a resource at the repository level.
- Use **path** for the URL; use **collectionResourceRel** and **itemResourceRel** for hypermedia relation names.
- Use **exported = false** to prevent exposing a repository.
- Use **excerptProjection** to select a summary representation for collections.
- Use **collectionResourceDescription** and **itemResourceDescription** to add descriptive metadata.
- Use **@RestResource** to customize or hide individual query methods.
- Use **RepositoryRestConfigurer** when a shared base path is needed.
- Use Spring Security and separate authorization design to protect data and operations.
