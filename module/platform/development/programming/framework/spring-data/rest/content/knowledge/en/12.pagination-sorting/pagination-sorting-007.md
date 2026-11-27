# Customizing Pagination and Sorting Parameter Names in Spring Data REST

## Objectives

Spring Data REST uses the query parameters **page**, **size**, and **sort** by default to paginate and sort repository data. You can rename these parameters to align with your system's API conventions or avoid conflicts with other parameters.

After this lesson, you will be able to:

- Recognize the meaning of the three default pagination and sorting parameters.
- Rename them using Spring Boot configuration or Java configuration.
- Send requests using the new parameter names.
- Understand the impact of the change on clients and HAL pagination links.

## 1. The Default Parameters

When Spring Data REST exports a repository's collection resource, the endpoint typically supports:

| Default Parameter | Meaning | Example |
|---|---|---|
| **page** | Page index, starting from 0 | **page=0** is the first page |
| **size** | Maximum elements per page | **size=20** |
| **sort** | Property and sort direction | **sort=lastName,asc** |

Example request:

~~~http
GET /people?page=0&size=20&sort=lastName,asc
Accept: application/hal+json
~~~

The request above retrieves the first page, up to 20 elements, sorted by **lastName** ascending.

You can sort by multiple properties by repeating the **sort** parameter:

~~~http
GET /people?page=0&size=20&sort=lastName,asc&sort=firstName,desc
~~~

In this example, **lastName** is the primary sort criterion; if multiple records have the same last name, **firstName** is used as the next criterion.

## 2. Renaming with application.yml

For Spring Boot applications, you can declare the parameter names under **spring.data.rest**:

~~~yaml
spring:
  data:
    rest:
      page-param-name: pageIndex
      limit-param-name: pageSize
      sort-param-name: orderBy
~~~

The three corresponding configuration properties are:

- **page-param-name**: query parameter name replacing **page**.
- **limit-param-name**: query parameter name replacing **size**.
- **sort-param-name**: query parameter name replacing **sort**.

After configuration, requests can be written as:

~~~http
GET /people?pageIndex=0&pageSize=20&orderBy=lastName,asc
Accept: application/hal+json
~~~

Sorting by multiple properties:

~~~http
GET /people?pageIndex=0&pageSize=20&orderBy=lastName,asc&orderBy=firstName,desc
Accept: application/hal+json
~~~

The new parameter names only replace the query parameter names. How values are interpreted remains the same: page indices start at 0, page size determines the number of elements on a page, and the sort value contains the property name together with the sort direction.

## 3. Renaming with RepositoryRestConfigurer

If you want to configure via Java, implement **RepositoryRestConfigurer** and set the parameter names on **RepositoryRestConfiguration**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestConfig
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setPageParamName("pageIndex");
        config.setLimitParamName("pageSize");
        config.setSortParamName("orderBy");
    }
}
~~~

Meaning of the configuration methods:

- **setPageParamName(...)** renames the page-selection parameter.
- **setLimitParamName(...)** renames the parameter limiting elements per page.
- **setSortParamName(...)** renames the sorting parameter.

Place the configuration class in a package scanned by Spring Boot component scanning. When the application starts, Spring Data REST uses these values when handling requests to repository resources.

Choose a single place as the unified source of configuration for all three parameter names. If the same setting is declared in both YAML and Java configuration, check the final resolved application configuration to avoid ambiguity about which values are active.

## 4. Pagination and Sorting After Renaming

Suppose **PersonRepository** is exported by Spring Data REST at **/people** and configured to use **pageIndex**, **pageSize**, and **orderBy**.

Fetch the second page with 10 records:

~~~http
GET /people?pageIndex=1&pageSize=10
Accept: application/hal+json
~~~

Because page indices start at 0, **pageIndex=1** is the second page.

Sort ascending by last name:

~~~http
GET /people?orderBy=lastName,asc
Accept: application/hal+json
~~~

Sort descending by last name and ascending by first name:

~~~http
GET /people?orderBy=lastName,desc&orderBy=firstName,asc
Accept: application/hal+json
~~~

Combine pagination and sorting:

~~~http
GET /people?pageIndex=1&pageSize=10&orderBy=lastName,asc&orderBy=firstName,desc
Accept: application/hal+json
~~~

Spring Data REST still processes requests using Spring Data's pagination and sorting mechanisms. You only change the names of the query parameters sent by clients.

## 5. Pagination Links in HAL

When responses are returned in HAL format, Spring Data REST can provide links such as **self**, **first**, **prev**, **next**, and **last** inside **_links**.

Illustrative example:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people?pageIndex=1&pageSize=10"
    },
    "first": {
      "href": "http://localhost:8080/people?pageIndex=0&pageSize=10"
    },
    "prev": {
      "href": "http://localhost:8080/people?pageIndex=0&pageSize=10"
    },
    "next": {
      "href": "http://localhost:8080/people?pageIndex=2&pageSize=10"
    }
  },
  "page": {
    "size": 10,
    "totalElements": 35,
    "totalPages": 4,
    "number": 1
  }
}
~~~

This is an illustrative response; actual links and metadata depend on the current page, record count, and repository configuration.

Clients should follow the URLs returned by the server in **_links** to switch pages. Avoid hardcoding parameter names or concatenating URLs manually, since the server may change the base path, parameter names, or how resources are exported.

## 6. Scope of Impact and Points to Note

- **Applies to Spring Data REST APIs:** the configured names belong to Repository REST configuration and are used when handling pagination and sorting on exported repository resources.
- **Does not rename response fields:** changing **page-param-name** does not alter the pagination metadata structure in HAL responses, such as **page.number** and **page.size**.
- **Does not rename entity properties:** **orderBy=lastName,asc** still refers to the **lastName** property of the domain object. Query parameter names and sorted property names are two separate concepts.
- **Does not change request body structure:** these settings only affect query parameters; they do not change the JSON representation used to create or update entities.
- **Update clients simultaneously:** frontends, mobile apps, scripts, and API documentation currently sending **page**, **size**, and **sort** must switch to the new names. Old requests may no longer be processed as intended.
- **Distinguish from custom MVC controllers:** controllers using Spring MVC and **Pageable** may be handled by a separate argument resolver mechanism. Do not assume Repository REST configuration automatically renames parameters for every endpoint in the application.
- **Distinguish parameter names from pagination limits:** changing **limit-param-name** only renames the query parameter receiving the page size. The **default-page-size** and **max-page-size** settings control the default size and maximum limit, not parameter names.

## 7. Verifying After Configuration

You can confirm the configuration with an API check pass:

1. Start the application and verify the repository resource is still exported.
2. Send a request with the new parameter names, e.g., **/people?pageIndex=0&pageSize=5&orderBy=lastName,asc**.
3. Check that the response contains the expected element count and ordering by the chosen property.
4. Read the **first**, **prev**, **next**, and **last** links in HAL and confirm the URLs use the configured parameter names.
5. Try sending a request with the old default names to catch any clients or documentation that have not yet been updated.

If the new requests have no effect, check the spelling of the YAML property names, verify whether the **RepositoryRestConfigurer** class is managed by Spring, and ensure the request is hitting the right Spring Data REST repository resource.

## Key Takeaways

Spring Data REST uses **page**, **size**, and **sort** by default. To rename them, configure **page-param-name**, **limit-param-name**, and **sort-param-name** under **spring.data.rest**, or call **setPageParamName**, **setLimitParamName**, and **setSortParamName** respectively in **RepositoryRestConfigurer**. After renaming, update clients and prefer following the HAL pagination links provided by the server.