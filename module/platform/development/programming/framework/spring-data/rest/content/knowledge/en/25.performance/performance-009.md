# Trade-offs Between Embedding Data, Link Traversal, and HTTP Round Trips

## 1. Two Ways to Represent Relationships in REST

A resource often relates to other resources—for instance, Person has an Address, Order has a Customer, Product has a Category. When a client reads a Person, the API can provide Address data directly in the response or provide a link for the client to fetch Address separately.

Two primary choices:

- **Embedding:** the parent resource's response includes data from related resources, typically in HAL under _embedded or as an inline object property in the representation.
- **Link traversal:** the parent response provides only a link inside _links; the client sends a subsequent request to that URI to retrieve the related resource.

Embedding example:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "address": {
    "city": "Hanoi",
    "country": "Vietnam"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~~

Link example:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~~

With the second approach, the client makes another GET to the address link when it actually needs that data.

Neither approach is universally best for every relationship. The decision depends on how often clients need related data, data size, stability, caching, access control, and the cost of an HTTP round trip.

## 2. HAL and How Spring Data REST Represents Associations

Spring Data REST uses HAL by default to render responses. HAL places links inside the _links property, keyed by relation name. Collection resources can hold item representations inside _embedded.

Collection example:

~~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "next": {
      "href": "http://localhost:8080/people?page=1"
    }
  },
  "_embedded": {
    "people": [
      {
        "name": "Alice",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/42"
          }
        }
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 100,
    "totalPages": 5,
    "number": 0
  }
}
~~~~

In Spring Data REST, an association pointing to a domain type with its own repository is usually represented by a link to the association resource. Clients can follow the link to fetch the related resource.

If the related object has no repository of its own, Spring Data REST can render its fields inline within the parent's representation. Exact behavior depends on domain mappings, repository exposure, and any active projections.

Hence, embedding versus linking is not purely a frontend choice. Spring Data REST's repository structure and projections also shape the generated representation.

## 3. Advantages of Embedding Data

Embedding enables the client to receive a cohesive bundle of information in one response.

It fits well when:

- Related data is small and nearly always displayed alongside the parent resource.
- Clients need the data immediately on a list screen.
- The relationship naturally forms part of the parent representation.
- Minimizing request count is critical, especially over high-latency networks.
- Related data does not require independent caching or refreshing.

For example, an order list typically displays the customer's name and the order total. If each item embeds a small CustomerSummary, the frontend avoids issuing an extra GET per customer just to display a name.

A response might include:

~~~~json
{
  "id": 9001,
  "total": 125.50,
  "customer": {
    "id": 42,
    "displayName": "Alice"
  }
}
~~~~

The client can render the order immediately without calling a separate customer resource.

Embedding also reduces client complexity when the required fields always appear together and deep navigation is unnecessary.

## 4. Disadvantages of Embedding Data

Embedding too much data inflates responses and tightly couples the parent representation to the child's structure.

Common costs include:

- **Large payloads:** child data can dominate the response even when the screen needs only a couple of fields.
- **Overfetching:** clients receive unused data.
- **Data duplication:** the same Customer appears across many Orders and is transmitted repeatedly.
- **Harder caching:** changes to a child resource can stale the representations of many parent resources.
- **Coupling:** structural changes in the child object can break clients relying on the parent representation.
- **Complex authorization:** embedded data must undergo permission checks inside the parent's response.
- **Difficult response pagination:** a page of many parents, each embedding large collections, can yield massive payloads.

For instance, an Order embedding the entire Customer, Address, PaymentHistory, and hundreds of OrderLines can make order-detail requests heavy even when the frontend needs only summary details.

Do not embed an entire object graph just because the ORM can navigate those associations.

## 5. Advantages of Link Traversal

Link traversal lets clients fetch related resources only when needed.

It fits well when:

- Child resources are large or contain many fields.
- Not all clients need the child data.
- Child data is reused across multiple screens or workflows.
- Child resources have independent lifecycles and caching rules.
- Clients require distinct access permissions per resource.
- Relationships can be navigated in multiple directions or change independently.

Example where Person returns only an address link:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~~

A screen needing only Person's name stops after the first request. An address detail screen follows the address link to load that resource.

Links also allow clients to discover the API from relation names instead of assembling URLs from internal conventions. That is a core hypermedia advantage: the server advertises where the client can go next.

## 6. Disadvantages of Link Traversal

Each link traversal typically requires a separate HTTP request. This increases round trips and can make the UI sluggish when clients must chain multiple resource fetches sequentially.

Example:

1. GET /orders/9001.
2. GET the customer link.
3. GET the customer's address link.
4. GET the payment link.
5. GET the items link.

If each request must wait for the previous response to learn the next link, total latency can approach the sum of all individual requests. On mobile networks or across multiple gateways, round-trip overhead can exceed JSON processing cost.

Link traversal also adds client complexity:

- Must parse relations and follow returned URIs.
- Must handle request failures at every step.
- Must manage loading states for each slice of data.
- May need to cache and deduplicate requests to shared resources.
- Must handle per-resource authorization errors when following links.

HTTP/2 or HTTP/3 can reduce some connection setup overhead and enable multiplexing, yet they do not eliminate network latency, server processing cost, or sequential client wait dependencies.

## 7. Count Round Trips Rather Than Counting Only Resources

The number of resources in a response does not equal the number of HTTP round trips. One response embedding several objects may take a single request, whereas the same data represented via links can take many requests.

Example of a page with 20 Orders, where each Order needs Customer:

**Embed Customer summary**

- 1 GET to fetch the Order collection.
- Each Order includes CustomerSummary.
- Total of 1 round trip for this data.

**Separate Customer link**

- 1 GET to fetch the Order collection.
- Up to 20 GETs to fetch Customer if the client loads sequentially without deduplication.
- Potentially fewer if multiple Orders share the same Customer and the client caches responses.

Do not assume the client will always fire exactly N requests. When many parents share a child resource, the client can load it once and reuse the result. If the server provides a batch endpoint or suitable projection, request count can also drop.

When designing APIs, model the real workflow: how many data types a screen needs, how many items appear per page, and how many child resources are shared.

## 8. Projections and Excerpts in Spring Data REST

Spring Data REST provides projections to alter the view of domain objects returned by the API. A projection can select specific fields, omit unneeded fields, or expose derived values.

Example:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Clients can request a projection via query parameter:

~~~http
GET /people/42?projection=personSummary
~~~

Projections reduce payload size and avoid returning the full domain object. They can also expose associations if the projection declares matching getters.

An excerpt is a projection automatically applied to item resources embedded within collections or related resources. Example:

~~~java
@RepositoryRestResource(excerptProjection = PersonSummary.class)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

The excerpt projection serves as the default preview inside collections. It is not automatically applied to single-item resources; clients must explicitly request the desired projection when fetching an item.

Remember that projections do not guarantee performance by themselves. If a projection getter accesses a lazy association, the server may still have to execute queries to load that data. Projections trim serialized fields, while fetch plans and query counts still require deliberate design.

## 9. Combining Embedding and Links

You do not have to pick a single style for the entire API. A representation can embed a compact summary while still providing a link to the full resource.

Example where Person embeds AddressSummary while keeping the address link:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "address": {
    "city": "Hanoi",
    "country": "Vietnam"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~~

The client has enough data to render the summary. When the user opens the address page, the client follows the link to retrieve the full representation.

This is a practical balance when a few fields are needed constantly while the child resource still requires independent navigation and management.

Spring Data REST can produce this style of representation using a projection/excerpt that defines association getters while preserving association links. Inspect the actual HAL response after configuration.

## 10. Excerpt Projections for Collection Resources

An excerpt projection works well when a collection needs a compact preview of each item.

Example:

~~~java
@Projection(name = "orderListItem", types = Order.class)
public interface OrderListItem {

    String getOrderNumber();

    BigDecimal getTotal();

    CustomerSummary getCustomer();
}

@Projection(name = "customerSummary", types = Customer.class)
public interface CustomerSummary {

    String getDisplayName();
}

@RepositoryRestResource(excerptProjection = OrderListItem.class)
public interface OrderRepository
        extends CrudRepository<Order, Long> {
}
~~~

The collection can show order number, total, and customer display name without embedding the full Customer resource.

When a client opens a specific Order, it can request a dedicated detail projection or follow the customer link. As a result, collection responses maintain a more stable size as the domain model evolves.

Treat an excerpt as the collection's preview contract. Changing an excerpt after an API is published can affect clients relying on the existing embedded structure.

## 11. Pagination and Large Collections

For large collections, paginate the parent resource first. Spring Data REST provides links such as self, next, and prev alongside page metadata.

Example:

~~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/orders?page=1&size=20"
    }
  },
  "_embedded": {
    "orders": [
      {
        "orderNumber": "A-1001",
        "total": 125.50
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 1000,
    "totalPages": 50,
    "number": 0
  }
}
~~~~

If each Order embedded all OrderLines, Customer, Address, and Payment details, a single page's size would balloon rapidly.

Use a small excerpt for collections, and provide links for clients to retrieve full details on demand. For large child collections such as order lines, consider a separate paginated resource instead of embedding everything.

## 12. Caching and Data Freshness

Links and embedding affect caching differently.

**When embedding:**

- The parent representation contains a copy of child data as of when the response was generated.
- Parent caches can become stale when a child resource changes.
- If the server uses ETags for parents, changes to embedded data must be reflected in the parent representation's validator.
- A child resource embedded in many parents can invalidate numerous cache entries at once.

**When using links:**

- Parent and child can maintain independent ETags, Last-Modified headers, and cache policies.
- Clients can revalidate child resources independently.
- A change to a child does not necessarily alter the parent representation if the parent holds only a link.
- Clients must make additional requests to obtain updated data.

If a screen requires a consistent snapshot of parent and child, embedding or a read-model endpoint may be preferable. If child data mutates independently and benefits from separate caching, link traversal is often more convenient.

## 13. Security and Access Control

Embedding exposes child data inside the parent's response. Consequently, permission to read the parent does not automatically mean the caller may view every child property.

Verify:

- Does the user have permission to view the child resource?
- Are any sensitive fields accidentally embedded?
- Does a projection inadvertently re-expose fields hidden with JsonIgnore?
- Do association links advertise resources the caller is unauthorized to read?
- Could collection responses leak another tenant's data through embedded objects?

Links are not an authorization mechanism either. Knowing a URI does not mean a GET request is permitted. The server must still enforce authorization on every resource and association operation.

Never use projections or excerpts as the sole security boundary. Enforce authorization on the server at both the resource and field levels as appropriate.

## 14. Impact on Consistency and Coupling

Embedding builds a composite representation. Child data is captured alongside the parent response, allowing clients to render a screen with fewer requests. However, the parent's structure becomes more coupled to the child schema.

Link traversal keeps resources looser and more independent. Clients fetch children at the moment they follow the link; that data may be fresher or reflect a different snapshot than what was read earlier on the parent.

For example, a client GETs Order at 10:00, then GETs Customer at 10:01. Customer may have changed between the two requests. If Order embedded CustomerSummary in the first response, the client sees the summary snapshot captured at 10:00.

Neither option is inherently more consistent. When business consistency is required, provide an appropriate read model/snapshot or version metadata; do not infer consistency from fewer or more requests.

## 15. Choosing a Strategy by Use Case

| Use case | Typical suitable approach | Reason |
|---|---|---|
| Order list needing only customer name | Embed CustomerSummary | Avoids one GET per customer |
| Customer detail page with large order history | Link to orders collection | Data is large and needs pagination |
| Product list needing only category name | Embed category name or summary | Small field, frequently displayed |
| Category page needing all products | Link to products collection | Collection can be large |
| Sensitive audit or payment data | Link with separate authorization | Access control needs isolation |
| Small Address always displayed with Person | Embed Address | Small relationship, frequently needed |
| Customer with profile, orders, payments, contacts | Links and per-screen projections | Avoids huge object graphs |
| Collection with many parents and children | Small excerpt + links | Keeps payload and queries under control |

These are guiding principles. Measure request counts, payloads, query counts, and latency on real workflows before finalizing representations.

## 16. Comparing Two Workflows by Example

Suppose an Order list page displays order number, total, and customer name.

### Option A — Embed Summary

The server returns the collection with CustomerSummary inside each Order. The client makes one GET for the page and renders immediately.

Advantages:

- Fewer round trips.
- No separate Customer-fetching logic needed.
- Easy to render lists.

Costs:

- Slightly larger payload.
- Changes to CustomerSummary can affect the Order representation.
- The server must fetch summaries efficiently to avoid N+1 database queries.

### Option B — Link Customer

The server returns a customer link for each Order. The client follows the link to retrieve Customer.

Advantages:

- The Customer resource is independent and separately cacheable.
- Clients fetch Customer only when needed.
- Multiple Orders referencing the same Customer can share a cached response.

Costs:

- Can trigger many GET requests.
- The client needs deduplication and loading-state management.
- If loaded sequentially, total latency can rise significantly.

### Option C — Hybrid

The server embeds displayName and retains the customer link. The list renders immediately; when the user opens customer details, the client follows the link.

This is often the balanced choice when a small summary is needed frequently while the child resource still requires independent access.

## 17. Measure Performance Before Deciding

Measure on both client and server:

**Client side**

- Number of HTTP requests for a screen.
- Total round trips and wait time.
- Total bytes downloaded.
- Number of duplicate requests to the same URI.
- Cache hit rate and revalidation time.

**Server side**

- SQL query count per request.
- Query and response serialization time.
- Response body size.
- CPU and memory spent building representations.
- Impact of page size and embedded association count.

A response taking only one HTTP request can still execute hundreds of SQL queries due to lazy loading. Conversely, multiple small HTTP requests can leverage caching well and fetch only genuinely needed data. Measure both layers rather than counting HTTP requests alone.

## 18. Common Pitfalls

| Symptom | Possible cause | Remedy |
|---|---|---|
| Every item triggers an extra GET association | Client follows links sequentially for every item | Embed a summary or use a suitable batch/read endpoint |
| Collection response is oversized | Excerpt embeds too many fields or nested collections | Slim down the excerpt and turn large collections into links |
| SQL queries grow with item count | Projection accesses lazy associations causing N+1 | Optimize EntityGraph, queries, or batch fetching |
| Client builds URLs manually | Not using HAL relation links | Follow hrefs inside _links |
| Excerpt does not apply to item resources | Excerpts mainly target collection/related resources | Use an explicit projection query for items |
| Child data is duplicated across many parents | Embedding the same resource repeatedly | Use link traversal or embed a small summary |
| Parent cache goes stale after child changes | Child data embedded in parent representation | Revalidate parent or separate child into its own resource |
| Client sees unauthorized child data | Projection/excerpt exposes sensitive fields | Enforce authorization and review field exposure |
| Pagination slows down when embedding large collections | Each parent pulls in many children | Paginate children separately or use excerpts |
| Request count rises and UI remains slow | Sequential round trips and network latency | Combine frequently used data, caching, and bounded parallel fetching |

## 19. Conclusion

Embedding reduces round trips and lets clients render quickly when related data is small, stable, and consistently used with the parent resource. Link traversal keeps resources independent, supports caching, and loads on demand, though it can increase HTTP request counts and client complexity.

Spring Data REST defaults to HAL with _links for navigation. Projections and excerpts can produce slim representations or embed related data; excerpts apply automatically to collection/related resources, not automatically to single items. When choosing representations, weigh payload size, pagination, caching, authorization, consistency, and SQL query counts. A response taking a single HTTP request can still trigger N+1 queries; a link-based response is not inherently slow if clients cache and reuse resources effectively. Practice often favors a hybrid approach: embed small summaries, keep links to full resources, and tailor projections per screen.

## References

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository Resources and HAL](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
