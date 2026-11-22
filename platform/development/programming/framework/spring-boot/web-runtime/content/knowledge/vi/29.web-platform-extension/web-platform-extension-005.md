# GraphQL qua HTTP và WebSocket trong ứng dụng Spring Boot

**GraphQL** là ngôn ngữ truy vấn và runtime thực thi API dựa trên **schema**. Client khai báo chính xác các field cần đọc trong một `query`, yêu cầu thay đổi trạng thái bằng `mutation`, hoặc đăng ký nhận các kết quả liên tục bằng `subscription`. **GraphQL không đồng nghĩa với WebSocket**: cùng một schema và resolver có thể phục vụ qua **HTTP POST**, **WebSocket** và trong một số triển khai **Server-Sent Events (SSE)**. Transport quyết định cách các GraphQL operations được đưa tới server và kết quả trả về; schema quyết định cấu trúc dữ liệu và quyền truy cập của ứng dụng.

Trong Spring Boot 3.x, **Spring for GraphQL** xây trên **GraphQL Java**. Với Spring MVC, HTTP GraphQL thường nằm tại `POST /graphql`; WebSocket GraphQL phải bật riêng và cần WebSocket starter. WebSocket đặc biệt phù hợp cho `subscription`; `query`/`mutation` thông thường vẫn rất hợp với HTTP POST, dễ quan sát, cache theo thiết kế và vận hành hơn.

Bài này dùng **Spring Boot 3.3.x, Java 17+, Spring MVC/Servlet, Spring for GraphQL 1.3.x, Project Reactor** để minh họa. Nó chứa dự án có **Query + Mutation qua HTTP**, **Subscription qua WebSocket**, browser client và tests. Cần lưu ý phiên bản Spring Boot 4.x/Spring GraphQL 2.x có thể đổi tên starter/property; không copy cấu hình của major version mới vào dự án 3.x mà không đối chiếu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **GraphQL schema/resolver/operation** với **HTTP và WebSocket transport**.
- Viết schema SDL `type Query`, `type Mutation`, `type Subscription`, khai báo non-null `!`, list và GraphQL input arguments.
- Viết `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` và `@Argument` trong Spring Boot.
- Gửi GraphQL HTTP request bằng `POST /graphql` với JSON `query`, `variables` và tùy chọn `operationName`.
- Đọc response GraphQL gồm `data`, `errors`, `extensions`; hiểu vì sao một response GraphQL có errors không nhất thiết mang HTTP 500.
- Bật `spring.graphql.websocket.path` và triển khai WebSocket subscription với subprotocol `graphql-transport-ws`.
- Phân biệt `connection_init`, `connection_ack`, `subscribe`, `next`, `error`, `complete` và `ping/pong`.
- Chạy thử một ứng dụng Java 17+ có danh mục sách in-memory, subscription phát sự kiện khi thêm sách.
- Kiểm thử bằng `curl`, browser WebSocket API và `@GraphQlTest`/`GraphQlTester`.
- Xử lý security, CSRF/CORS/Origin, rate limits, query depth/complexity, N+1, WebSocket lifetime, reconnect và multi-replica.

## 2. Bức tranh kiến trúc: schema không phụ thuộc transport

```text
                    Clients
               /                  \
     HTTP GraphQL POST          WebSocket GraphQL
        /graphql                  /graphql/ws
           |                           |
           v                           v
    GraphQlHttpHandler        GraphQlWebSocketHandler
           \                           /
            \                         /
              WebGraphQlHandler
                     |
              Interceptor chain
                     |
           GraphQL Java Execution
                     |
             Schema / DataFetchers
                     |
       @QueryMapping / @MutationMapping
                @SubscriptionMapping
                     |
       Business service / DB / event bus
```

Trong Spring Boot 3.3:

- Starter `spring-boot-starter-graphql` tạo hạ tầng schema/runtime.
- Starter `spring-boot-starter-web` cho HTTP GraphQL qua Spring MVC.
- Starter `spring-boot-starter-websocket` bổ sung WebSocket cho Servlet app; **chỉ thêm dependency vẫn chưa bật endpoint GraphQL WebSocket**.
- Property `spring.graphql.websocket.path=/graphql/ws` mới đăng ký đường WebSocket cho GraphQL.
- Nếu chọn `spring-boot-starter-webflux`, HTTP và WebSocket có thể dùng reactive stack mà không cần thêm WebSocket starter riêng; đó là một lựa chọn runtime khác.
- `@Controller` GraphQL không phải `@RestController` tự tạo `@PostMapping("/graphql")`. Spring for GraphQL tự cấu hình HTTP/WS handlers, controller chỉ định các **GraphQL fields** cần resolve.

Điểm quan trọng: bạn không phải viết hai lần logic `books` hay `bookAdded` cho HTTP và WS. Một schema và một nhóm DataFetchers là đủ, transport chuyển GraphQL operation tới runtime.

## 3. GraphQL Query, Mutation và Subscription

| Operation | Mục đích | Kiểu kết quả | Transport hay dùng |
| --- | --- | --- | --- |
| `query` | Đọc dữ liệu theo selection set | Thường một GraphQL execution result | HTTP POST |
| `mutation` | Yêu cầu thay đổi trạng thái | Thường một result, có thể có errors | HTTP POST |
| `subscription` | Đăng ký luồng kết quả thay đổi theo thời gian | Nhiều GraphQL results từ `Publisher` | WebSocket hoặc SSE |
| GraphQL introspection | Tra cứu schema/type metadata | GraphQL query result | HTTP hoặc WS nếu được phép |

**Một mutation không tự gửi sự kiện cho tất cả clients.** Muốn subscription nhận được event, server cần một nguồn sự kiện và cơ chế nối nguồn đó với GraphQL `Publisher`. Demo dùng Reactor `Sinks.Many`; production có thể thay bằng Redis Streams, Kafka, RabbitMQ hoặc một event service phù hợp.

### 3.1. Selection set giúp client chọn dữ liệu

Ví dụ:

```graphql
query {
  books {
    id
    title
  }
}
```

Server chỉ trả các field client yêu cầu theo schema:

```json
{
  "data": {
    "books": [
      {"id": 1, "title": "Spring Boot"},
      {"id": 2, "title": "GraphQL Java"}
    ]
  }
}
```

Đây là kết quả minh họa với dữ liệu mẫu của dự án phía dưới. Nếu client chọn `category`, kết quả có thêm field đó; nếu client chọn field không có trong schema, operation không hợp lệ. Không cần endpoint `/books`, `/books/1`, `/books/list-with-category` cho từng selection set.

### 3.2. Query khác mutation ở ý nghĩa nghiệp vụ

Query được kỳ vọng dùng để đọc và tránh side effect quan sát được; mutation được dùng để thay đổi dữ liệu. Tuy nhiên **GraphQL không tự tạo transaction** cho resolver và không tự bảo đảm idempotency hay rollback toàn bộ nghiệp vụ. Trong ứng dụng, service phải quyết định authorization, validation, transaction, optimistic locking và event emission theo hợp đồng.

### 3.3. Subscription là một chuỗi kết quả

Một subscription:

```graphql
subscription {
  bookAdded {
    id
    title
    category
  }
}
```

có thể phát lần lượt:

```json
{"data":{"bookAdded":{"id":3,"title":"Spring Security","category":"Java"}}}
```

và sau đó một `data.bookAdded` khác cho sách kế tiếp, thay vì trả một mảng JSON duy nhất. **Subscription chỉ là GraphQL operation**, không bắt buộc WebSocket về mặt schema. Mục 10 sẽ phân biệt WebSocket với SSE.

## 4. Schema SDL và mapping sang Java

**Schema Definition Language (SDL)** là hợp đồng public của GraphQL API. Nó mô tả:

- Loại object `Book` và các fields;
- Root `Query`/`Mutation`/`Subscription`;
- Kiểu cơ bản `String`, `Int`, `ID`, `Boolean`, `Float`;
- List `[Book!]!`: danh sách không null, các phần tử không null;
- Arguments `title: String!`: client bắt buộc cung cấp chuỗi không null.

Ví dụ của bài:

```graphql
type Query {
  books: [Book!]!
  bookById(id: Int!): Book
}

type Mutation {
  addBook(title: String!, category: String!): Book!
}

type Subscription {
  bookAdded: Book!
}

type Book {
  id: Int!
  title: String!
  category: String!
}
```

Spring Boot 3.3 mặc định phát hiện các `.graphqls` hoặc `.gqls` ở `src/main/resources/graphql/**`. Nó không tự lấy schema bằng cách quét Java entity classes rồi suy ra mọi field. Schema-first cho phép review API contract độc lập với lưu trữ.

**Tại sao `bookById` có thể null?** Khi không có ID, service trả `null` và GraphQL hợp đồng cho phép field này rỗng. Ngược lại `addBook: Book!` hứa có Book nếu mutation thực thi thành công. Khi lỗi ở một field non-null, cơ chế null propagation của GraphQL có thể làm field cha trở về null; client cần xét cả `data` và `errors`.

## 5. HTTP GraphQL: một URL, nhiều operations

Với Spring MVC, GraphQL POST request thường có:

```http
POST /graphql HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/graphql-response+json

{
  "query": "query ($id: Int!) { bookById(id: $id) { id title } }",
  "variables": {"id": 1},
  "operationName": null
}
```

`query` là GraphQL document string. `variables` là JSON object chứa các biến typed; `operationName` dùng khi document chứa nhiều operations hoặc khi client muốn chọn một operation được đặt tên. Với trường hợp một query đơn giản, có thể bỏ `operationName`. Lưu ý HTTP GET GraphQL không phải yêu cầu mặc định của server Boot 3.3; ví dụ và hợp đồng chuẩn dùng **POST**.

### 5.1. Trả response với data và errors

Một response hợp lệ có thể là:

```json
{
  "data": {
    "bookById": {"id": 1, "title": "Spring Boot"}
  }
}
```

Khi một field resolver thất bại, GraphQL có thể trả **partial data** cùng mảng `errors`:

```json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "Internal error",
      "path": ["bookById"]
    }
  ]
}
```

Đây là **ví dụ hình dạng**, không phải lời hứa thông điệp lỗi đúng y như vậy ở runtime. GraphQL HTTP status phụ thuộc media type và loại lỗi:

- Request không đúng HTTP/JSON hoặc authentication failure có thể nhận 4xx/5xx.
- Response `application/graphql-response+json` có semantics HTTP status khác với mode legacy `application/json`; GraphQL document parse/validation failure có thể trả 4xx theo đặc tả.
- Một resolver error trong execution có thể nằm trong `errors` dù HTTP status là 200.

**Không coi `response.ok` là bằng chứng mọi GraphQL field thành công.** Client cần kiểm tra `errors` và policy hiển thị partial data của mình. Cũng không tự trả HTTP 500 cho mọi GraphQL validation error.

### 5.2. Vì sao variables tốt hơn nối chuỗi?

Tránh:

```javascript
const query = '{ bookById(id: ' + userInput + ') { title } }';
```

Giá trị đầu vào được nối trực tiếp vào GraphQL syntax có thể gây lỗi parse và thay đổi cấu trúc truy vấn. Dùng query document đã định nghĩa và `variables`:

```json
{
  "query": "query Book($id: Int!) { bookById(id: $id) { title } }",
  "variables": {"id": 1}
}
```

Variables không thay authorization hoặc input validation, nhưng giúp tách cú pháp và dữ liệu, dễ cache/monitor/persisted operations hơn.

## 6. WebSocket GraphQL: protocol khác raw WebSocket

Khi dùng Spring for GraphQL WebSocket, client không gửi ngay một text frame `"hello"` rồi mong resolver thực thi. Nó phải nói **GraphQL over WebSocket protocol**. Spring GraphQL sử dụng protocol được thư viện **graphql-ws** định nghĩa với subprotocol:

```text
graphql-transport-ws
```

Đừng nhầm với thư viện cũ **subscriptions-transport-ws**, từng sử dụng subprotocol string `graphql-ws`. Tên rất dễ gây nhầm:

| Thư viện/protocol | WebSocket subprotocol thực tế | Tình trạng |
| --- | --- | --- |
| `graphql-ws` hiện đại | `graphql-transport-ws` | Nên dùng với Spring GraphQL |
| `subscriptions-transport-ws` cũ | `graphql-ws` | Dự án legacy, không còn là lựa chọn ưu tiên |
| Raw `WebSocket` text echo | Không có GraphQL subprotocol | Không tự chạy GraphQL operations |

GraphQL WebSocket có thể chở query/mutation với một kết quả và subscription với nhiều kết quả. Nhưng HTTP POST thường tiện hơn cho query/mutation thông thường; WebSocket chủ yếu giải bài toán stream events, multiplex subscriptions và giảm round-trip setup khi kênh đang sống.

### 6.1. Handshake WebSocket

Client browser kết nối:

```javascript
const ws = new WebSocket(
  "ws://localhost:8080/graphql/ws",
  "graphql-transport-ws"
);
```

Với production HTTPS, sử dụng `wss://`. Khi HTTP/1.1 handshake thành công, status thường là `101 Switching Protocols` và server chọn đúng `Sec-WebSocket-Protocol: graphql-transport-ws`. Khi đã upgrade, các message GraphQL được truyền bằng WebSocket frames, không còn tạo một HTTP response mới cho mỗi event.

### 6.2. Các message cốt lõi

```text
Client                                     Server
  |                                            |
  | WebSocket handshake graphql-transport-ws  |
  |------------------------------------------->|
  |<-------------------------------------------|
  |                                            |
  | {"type":"connection_init"}                 |
  |------------------------------------------->|
  | {"type":"connection_ack"}                  |
  |<-------------------------------------------|
  |                                            |
  | {"id":"sub-1","type":"subscribe",            |
  |  "payload":{"query":"subscription {...}"}} |
  |------------------------------------------->|
  |                                            |
  | {"id":"sub-1","type":"next",                 |
  |  "payload":{"data":{...}}}                  |
  |<-------------------------------------------|
  | {"id":"sub-1","type":"next", ...}            |
  |<-------------------------------------------|
  |                                            |
  | {"id":"sub-1","type":"complete"}             |
  |------------------------------------------->|
  |                                            |
  | close WebSocket khi không còn sử dụng      |
```

Ý nghĩa:

- `connection_init`: khởi tạo **GraphQL protocol connection** trên socket đã mở. Có thể mang payload authentication theo ứng dụng, nhưng không được tự tin payload chưa xác thực.
- `connection_ack`: server chấp nhận phiên GraphQL trên socket; client chỉ `subscribe` sau ACK.
- `subscribe`: đăng ký operation với `id` riêng và `payload.query`/`variables`/`operationName`.
- `next`: một GraphQL execution result của operation tương ứng; `payload.data` và `payload.errors` có thể xuất hiện.
- `error`: operation-level error trước/khi thực thi theo protocol; không phải một HTTP 500.
- `complete`: kết thúc operation. Client có thể chủ động hủy một subscription; server cũng có thể gửi complete khi luồng kết thúc.
- `ping`/`pong`: keepalive tại **GraphQL WebSocket message layer**, khác WebSocket control frame Ping/Pong ở protocol tầng thấp.

**Operation `id` không phải session ID hoặc user ID.** Một socket có thể multiplex nhiều subscriptions cùng lúc bằng các ID khác nhau; response messages dùng `id` để định tuyến đến đúng operation. Không tái sử dụng ID khi operation cũ vẫn hoạt động.

### 6.3. WebSocket transport không tự bảo đảm event delivery

Nếu client mất mạng, những event phát trong lúc disconnected không được tự động replay. Khi reconnect, client phải tạo lại socket, `connection_init`, re-authenticate và gửi `subscribe` mới. Muốn khôi phục event đã lỡ, schema cần cursor/sequence và một durable event store. `graphql-transport-ws` không tự xây database replay hoặc exactly-once guarantee.

## 7. Dự án hoàn chỉnh: Spring Boot MVC + GraphQL HTTP + WebSocket

Demo quản lý danh mục sách đơn giản:

- Hai sách có sẵn trong memory.
- `books` trả danh sách theo ID.
- `bookById` tìm một sách.
- `addBook` thêm sách và phát một event.
- `bookAdded` stream những sách được thêm **sau khi client subscribe**.
- Một HTML client dùng `fetch` cho Query/Mutation và WebSocket cho Subscription.

Dữ liệu in-memory sẽ **mất khi JVM restart**. Event sink **best effort, không replay**, không phù hợp cho thông báo phải được đảm bảo giao hàng. Đây là chủ đích để bài học tập trung vào GraphQL transports.

### 7.1. Khởi tạo từ Spring Initializr

Chọn Java 17+, Spring Boot **3.3.x**, Gradle/Groovy, dependencies **Spring for GraphQL**, **Spring Web**, **WebSocket**.

Khối dependencies của `build.gradle` do Initializr tạo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

Đây là **đoạn dependencies**; để chạy cần cả Gradle plugins, repositories, Boot version/dependency management và wrapper do Initializr sinh ra. Không tự gắn một version GraphQL Java hoặc Reactor khác với BOM khi chưa có lý do. `spring-boot-starter-graphql` đã mang hạ tầng GraphQL/Reactor cần thiết cho `Flux`/`Sinks` trong demo; không thêm `spring-boot-starter-webflux` chỉ để có WebSocket nếu dự án đang dùng Servlet MVC.

Cấu trúc:

```text
src/
  main/
    java/demo/
      GraphQlTransportApplication.java
      Book.java
      CatalogStore.java
      CatalogGraphQlController.java
    resources/
      graphql/schema.graphqls
      application.properties
      static/index.html
  test/
    java/demo/
      CatalogGraphQlTest.java
```

### 7.2. SDL: schema.graphqls

Tạo `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
  books: [Book!]!
  bookById(id: Int!): Book
}

type Mutation {
  addBook(title: String!, category: String!): Book!
}

type Subscription {
  bookAdded: Book!
}

type Book {
  id: Int!
  title: String!
  category: String!
}
```

Spring Boot tìm schema trong `classpath:graphql/**/` và dùng `.graphqls`/`.gqls` theo defaults. Nếu đổi file thành `schema.txt` hoặc để ngoài resources không cấu hình locations, schema không được tìm tự động. Schema dùng `Int` cho ID của demo, giới hạn trong số nguyên GraphQL 32-bit; production thường cân nhắc `ID` hoặc UUID string vì identity của database không nhất thiết là Int.

### 7.3. Lớp ứng dụng

`src/main/java/demo/GraphQlTransportApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlTransportApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlTransportApplication.class, args);
    }
}
```

Ứng dụng quét package `demo`; không cần tự viết một `@PostMapping("/graphql")`. Spring Boot + Spring for GraphQL đăng ký handler transport và gắn các `@Controller` resolvers.

### 7.4. Book record

`src/main/java/demo/Book.java`:

```java
package demo;

public record Book(int id, String title, String category) {
}
```

GraphQL Java có thể lấy các field từ Java record accessor (`id()`, `title()`, `category()`) theo property fetcher. Class Java và GraphQL type không bắt buộc trùng tên trong mọi ứng dụng, nhưng đồng nhất ở demo để dễ hiểu. Không cần ghi DTO/entity JPA ngay khi mới học GraphQL resolver mapping.

### 7.5. CatalogStore: dữ liệu và event sink

`src/main/java/demo/CatalogStore.java`:

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Service
public class CatalogStore {

    private final ConcurrentMap<Integer, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicInteger sequence = new AtomicInteger(2);

    private final Sinks.Many<Book> addedEvents =
            Sinks.many().multicast().directBestEffort();

    public CatalogStore() {
        books.put(1, new Book(1, "Spring Boot", "Java"));
        books.put(2, new Book(2, "GraphQL Java", "API"));
    }

    public List<Book> list() {
        return books.values().stream()
                .sorted(Comparator.comparingInt(Book::id))
                .toList();
    }

    public Book find(int id) {
        return books.get(id);
    }

    public Book add(String title, String category) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }
        if (category == null || category.isBlank()) {
            throw new IllegalArgumentException("category must not be blank");
        }

        Book created = new Book(
                sequence.incrementAndGet(),
                title.strip(),
                category.strip());

        books.put(created.id(), created);

        // Best effort: event không được lưu để replay.
        addedEvents.tryEmitNext(created);

        return created;
    }

    public Flux<Book> subscribeToAdditions() {
        return addedEvents.asFlux();
    }
}
```

**Giải thích kỹ:**

1. `ConcurrentHashMap` và `AtomicInteger` giúp demo tránh những race cơ bản ở nhiều request. Chúng **không thay transaction, uniqueness constraint hay database**.
2. `list()` sort theo ID để kết quả query có thứ tự ổn định; Java Map không tự đảm bảo thứ tự danh sách.
3. `addedEvents` là `Sinks.Many` dạng multicast cho nhiều subscribers. `directBestEffort()` **không replay** events cho người subscribe muộn; nếu không có subscriber, `tryEmitNext` không phát event. Nếu subscriber quá chậm, một số events có thể bị bỏ qua. Đây là mô hình **best effort** minh họa chứ không có delivery SLA.
4. `add()` lưu Book rồi thử phát event. Một mutation có thể thành công dù chẳng có client WebSocket nào; điều đó đúng về mặt nghiệp vụ lưu sách. Tuy nhiên nó cũng có thể tạo **race** khi client vừa subscribe chưa kịp đăng ký và mutation đã xảy ra.
5. Trong production, khi cần event bền vững, cân nhắc **transactional outbox** hoặc event log/broker cùng cơ chế dedup/replay; không chỉ đổi `Sinks.Many` sang một queue mà bỏ qua vấn đề transaction-then-publish.
6. Không lưu `WebSocketSession` trực tiếp trong service này: GraphQL runtime quản lý transport; service chỉ trả `Flux<Book>`.

`tryEmitNext` có thể trả `FAIL_ZERO_SUBSCRIBER` hoặc `FAIL_OVERFLOW`. Trong demo, kết quả bị bỏ qua vì “thêm sách” không phụ thuộc có ai đang nghe. Trong hệ thống phải bảo đảm giao event, **không được bỏ qua kết quả này**; thiết kế durable delivery khác.

### 7.6. CatalogGraphQlController: một resolver cho nhiều transports

`src/main/java/demo/CatalogGraphQlController.java`:

```java
package demo;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;

@Controller
public class CatalogGraphQlController {

    private final CatalogStore store;

    public CatalogGraphQlController(CatalogStore store) {
        this.store = store;
    }

    @QueryMapping
    public List<Book> books() {
        return store.list();
    }

    @QueryMapping
    public Book bookById(@Argument("id") int id) {
        return store.find(id);
    }

    @MutationMapping
    public Book addBook(
            @Argument("title") String title,
            @Argument("category") String category) {

        return store.add(title, category);
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return store.subscribeToAdditions();
    }
}
```

Các method names khớp fields trong schema:

| Java annotation/method | GraphQL field | Ý nghĩa |
| --- | --- | --- |
| `@QueryMapping books()` | `Query.books` | Resolver danh sách |
| `@QueryMapping bookById(...)` | `Query.bookById` | Resolver theo ID |
| `@MutationMapping addBook(...)` | `Mutation.addBook` | Tạo mới + thử phát event |
| `@SubscriptionMapping bookAdded()` | `Subscription.bookAdded` | Trả `Publisher`/`Flux` cho events |

`@Argument("title")` lấy GraphQL argument và bind vào kiểu Java. Dùng tên tường minh giúp không phụ thuộc compiler parameter name metadata. Nếu schema field `addBook` đổi thành `createBook` nhưng Java method giữ tên cũ, cần chỉnh `@MutationMapping(name="createBook")` hoặc đổi method để mapping đúng.

**Không dùng `@GetMapping("/graphql")`**, cũng không trả `ResponseEntity<Book>` ở `@QueryMapping` như một REST endpoint. GraphQL execution engine chịu trách nhiệm gọi DataFetcher, chọn fields, trả `data/errors` và xử lý GraphQL types.

### 7.7. application.properties

`src/main/resources/application.properties`:

```properties
server.port=8080

# Spring Boot 3.3 HTTP GraphQL: mặc định /graphql.
spring.graphql.path=/graphql

# WebSocket GraphQL mặc định TẮT; phải khai báo path mới bật.
spring.graphql.websocket.path=/graphql/ws

# Yêu cầu client khởi tạo protocol kịp thời.
spring.graphql.websocket.connection-init-timeout=20s

# Ping GraphQL WebSocket nếu kênh idle đủ lâu.
spring.graphql.websocket.keep-alive=20s

# Chỉ phục vụ học local. Bật GraphiQL trong môi trường dev.
spring.graphql.graphiql.enabled=true

# Không xuất schema printer endpoint trong ví dụ.
spring.graphql.schema.printer.enabled=false
```

Lưu ý:

- **`spring.graphql.path`** là property của HTTP endpoint trong **Boot 3.3**. Ở một số major versions mới, đường property có thể đổi; không dùng tài liệu Boot 4 thay trực tiếp.
- **`spring.graphql.websocket.path`** không được tự tạo mặc định; khi đã có `spring-boot-starter-websocket` và property, Boot mới expose GraphQL WS endpoint.
- **GraphiQL** là công cụ dev giúp nhập query/mutation; ở production, thường tắt, hoặc bảo vệ bằng authentication/mạng. Nó **không thay security** của GraphQL API.
- **`keep-alive`** tạo ping định kỳ khi idle theo Spring GraphQL 1.3/Boot 3.3; NGINX/CDN còn timeout của riêng mình. Không có cấu hình nào bảo đảm giữ socket qua JVM restart.

### 7.8. Browser client đơn giản, không dùng thư viện JS ngoài

Tạo `src/main/resources/static/index.html`. Trang này kết nối cùng origin, nên demo không phải cấu hình CORS hoặc cookie cross-site. Nó dùng browser `WebSocket` cơ bản và tự gửi messages của `graphql-transport-ws`, giúp thấy rõ protocol. Ở ứng dụng lớn, nên dùng client tương thích chính thức như `graphql-ws` để hỗ trợ reconnect, ping/pong, multiplexing và error handling hoàn chỉnh.

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>GraphQL HTTP va WebSocket</title>
</head>
<body>
  <h1>Danh muc sach GraphQL</h1>

  <button id="query">Tai danh sach (HTTP)</button>
  <button id="subscribe">Dang ky bookAdded (WS)</button>

  <input id="title" value="Spring Security" aria-label="Ten sach">
  <input id="category" value="Java" aria-label="Nhom sach">

  <button id="mutate">Them sach (HTTP)</button>
  <button id="disconnect">Ngat WebSocket</button>

  <pre id="log"></pre>

  <script>
    const logElement = document.querySelector("#log");
    const log = (text) => {
      logElement.textContent += text + "\n";
    };

    let socket = null;
    const operationId = "books-live-1";

    async function graphql(query, variables = {}) {
      const response = await fetch("/graphql", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/graphql-response+json"
        },
        body: JSON.stringify({query, variables}),
        cache: "no-store"
      });

      const result = await response.json();

      if (!response.ok || result.errors?.length) {
        throw new Error(
          JSON.stringify({
            status: response.status,
            errors: result.errors || []
          })
        );
      }
      return result.data;
    }

    document.querySelector("#query").onclick = async () => {
      try {
        const data = await graphql(
          "{ books { id title category } }"
        );
        log("QUERY: " + JSON.stringify(data));
      } catch (error) {
        log("QUERY ERROR: " + error.message);
      }
    };

    document.querySelector("#mutate").onclick = async () => {
      try {
        const title = document.querySelector("#title").value;
        const category = document.querySelector("#category").value;

        const data = await graphql(
          "mutation CreateBook($title: String!, " +
          "$category: String!) { " +
          "addBook(title: $title, category: $category) " +
          "{ id title category } }",
          {title, category}
        );

        log("MUTATION: " + JSON.stringify(data));
      } catch (error) {
        log("MUTATION ERROR: " + error.message);
      }
    };

    document.querySelector("#subscribe").onclick = () => {
      if (socket && socket.readyState !== WebSocket.CLOSED) {
        log("WebSocket da ton tai; ngat truoc khi mo moi");
        return;
      }

      const scheme =
        location.protocol === "https:" ? "wss:" : "ws:";
      const url = scheme + "//" + location.host + "/graphql/ws";

      socket = new WebSocket(url, "graphql-transport-ws");

      socket.onopen = () => {
        log("WS OPEN: " + socket.protocol);
        socket.send(JSON.stringify({
          type: "connection_init"
        }));
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);

        if (message.type === "connection_ack") {
          log("WS connection_ack");
          socket.send(JSON.stringify({
            id: operationId,
            type: "subscribe",
            payload: {
              query:
                "subscription { bookAdded " +
                "{ id title category } }"
            }
          }));
          log("WS subscribe sent");
        } else if (message.type === "next") {
          log("WS NEXT: " +
              JSON.stringify(message.payload));
        } else if (message.type === "error") {
          log("WS operation ERROR: " +
              JSON.stringify(message.payload));
        } else if (message.type === "complete") {
          log("WS operation complete: " + message.id);
        } else if (message.type === "ping") {
          socket.send(JSON.stringify({
            type: "pong",
            payload: message.payload
          }));
        } else if (message.type === "pong") {
          log("WS pong");
        }
      };

      socket.onerror = () => log("WS transport error");
      socket.onclose = (event) => {
        log("WS CLOSED code=" + event.code);
      };
    };

    document.querySelector("#disconnect").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          id: operationId,
          type: "complete"
        }));
        socket.close(1000, "user closed");
      }
    };
  </script>
</body>
</html>
```

**Cách thử trong browser:**

1. Mở `http://localhost:8080/`.
2. Chọn **Tải danh sách**: browser POST `/graphql`, nhận hai sách ban đầu.
3. Chọn **Đăng ký bookAdded**: browser mở `ws://localhost:8080/graphql/ws` với subprotocol chính xác, gửi `connection_init`, chờ `connection_ack` rồi gửi `subscribe`.
4. Khi log hiển thị `WS subscribe sent`, chờ subscription được server xử lý (thường rất nhanh), rồi chọn **Thêm sách**.
5. HTTP mutation thêm sách, trong khi WebSocket có thể nhận `next` kèm dữ liệu Book mới.
6. Chọn **Ngắt WebSocket** để hủy subscription và đóng socket.

**Vì event sink best effort, không có delivery guarantee:** nếu mutation xảy ra trước khi subscriber được đăng ký thật, hoặc subscriber quá chậm, `WS NEXT` có thể không xuất hiện. Kiểm tra bằng cách mở subscribe trước, chờ một chút rồi mutate. Đây là cơ hội hiểu khác biệt giữa event stream trực tiếp và durable event log.

Trang dùng `textContent` thay `innerHTML` để không render HTML do server/user trả về thành mã thực thi. Trong production, vẫn phải validate input, kiểm tra quyền và chống XSS theo toàn bộ ứng dụng.

### 7.9. Chạy dự án

Từ thư mục chứa Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Không thể compile các file Spring bằng riêng `javac CatalogStore.java` nếu không có dependency classpath. Gradle Wrapper + Spring Boot plugins mới tải và biên dịch GraphQL/Spring/Reactor đúng phiên bản.

Sau khi app khởi động, mở:

```text
http://localhost:8080/
http://localhost:8080/graphiql
```

`/graphiql` được bật chỉ phục vụ dev theo property. Nếu app không khởi động, kiểm tra lỗi schema parse, mapping field mismatch, dependency không tương thích, port 8080 bị chiếm hoặc thiếu starter WebSocket.

## 8. Kiểm thử Query qua HTTP

### 8.1. Query danh sách

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/graphql-response+json' \
  --data '{"query":"{ books { id title category } }"}'
```

Body dự kiến khi chưa có mutation:

```json
{
  "data": {
    "books": [
      {"id": 1, "title": "Spring Boot", "category": "Java"},
      {"id": 2, "title": "GraphQL Java", "category": "API"}
    ]
  }
}
```

Whitespace và thứ tự JSON object properties không được đảm bảo; dữ liệu và thứ tự sách theo sort của service là điểm cần đối chiếu.

### 8.2. Query theo biến

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"query FindBook($id:Int!){bookById(id:$id){id title}}","variables":{"id":1}}'
```

Kết quả tương đương:

```json
{"data":{"bookById":{"id":1,"title":"Spring Boot"}}}
```

Khi `id` không tồn tại, resolver trả `null`, phù hợp SDL `bookById(...): Book`:

```json
{"data":{"bookById":null}}
```

Phần này không yêu cầu HTTP 404 riêng cho ID không tồn tại; trong GraphQL, “không tìm thấy entity” thường được thể hiện qua field null và contract của schema. Nếu nghiệp vụ muốn error code cụ thể, dùng `GraphQLError`/`DataFetcherExceptionResolver` và thống nhất với clients.

### 8.3. Trên PowerShell

PowerShell có thể dùng `curl.exe` và double quoting khác shell Bash. Một cách không phụ thuộc escaping dài là tạo file `query.json` chứa:

```json
{
  "query": "query FindBook($id:Int!) { bookById(id:$id) { id title } }",
  "variables": {"id": 1}
}
```

Sau đó:

```powershell
curl.exe -sS -X POST http://localhost:8080/graphql -H "Content-Type: application/json" --data-binary "@query.json"
```

Tạo file request JSON không bắt buộc trong ứng dụng Java; đây là cách kiểm tra riêng ở terminal. Khi gửi Bearer token hoặc cookie thật, không đưa credential vào file đang được commit.

## 9. Kiểm thử Mutation qua HTTP

### 9.1. Thêm một cuốn sách

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"mutation Add($title:String!,$category:String!){addBook(title:$title,category:$category){id title category}}","variables":{"title":"Spring Security","category":"Java"}}'
```

Nếu chưa có mutation trước đó, response thường là:

```json
{
  "data": {
    "addBook": {
      "id": 3,
      "title": "Spring Security",
      "category": "Java"
    }
  }
}
```

GraphQL mutation qua HTTP gửi một request và nhận một response JSON. Nếu có WebSocket subscriber đang hoạt động, service đồng thời thử phát `Book` mới tới sink. **Một mutation thành công không có nghĩa mọi subscribers đã nhận được event**.

### 9.2. Sau mutation, Query trả thêm phần tử

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ books { id title } }"}'
```

Bây giờ danh sách có thêm sách vừa tạo, vì data nằm trong memory của cùng JVM. Khi restart, store constructor chỉ tạo lại hai sách ban đầu; đây không phải database durable.

### 9.3. GraphQL validation lỗi

Nếu client yêu cầu field không có trong SDL:

```bash
curl -i -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/graphql-response+json' \
  --data '{"query":"{ books { unknownField } }"}'
```

GraphQL engine phải báo validation error thay vì tự ý trả `unknownField`. Trong GraphQL over HTTP với media type `application/graphql-response+json`, loại lỗi có thể ảnh hưởng HTTP status. Hãy quan sát **cả status và mảng errors**, không cố định một hình dạng body/error message cho mọi Spring GraphQL version.

### 9.4. Những kiểu lỗi khác nhau

- Request body không phải JSON: lỗi ở HTTP transport.
- Query field không có trong schema: GraphQL parse/validation error.
- `title` null trong schema `String!`: validation/coercion error trước khi gọi resolver.
- `title` rỗng/whitespace: GraphQL `String!` **không tự cấm chuỗi rỗng**; demo `CatalogStore` ném `IllegalArgumentException` và Spring GraphQL có thể chuyển thành GraphQL error.
- Không đủ quyền đọc một sách: lỗi authorization/field policy do ứng dụng thiết kế.
- Database hoặc downstream timeout: lỗi service, cần handler/mapping an toàn.

Không trả raw SQL exception, stacktrace, token hoặc internal host cho client. Spring GraphQL có `DataFetcherExceptionResolver` để kiểm soát GraphQL errors từ resolver.

## 10. Kiểm thử Subscription qua WebSocket

### 10.1. Thứ tự thao tác

1. Mở trang HTML demo.
2. Click đăng ký WebSocket và chờ `connection_ack`.
3. Server nhận `subscribe` cho `bookAdded` và tạo GraphQL subscription execution.
4. Trong cùng tab hoặc tab khác, gửi HTTP mutation thêm sách.
5. Subscriber nhận một `next` với `payload.data.bookAdded` nếu sự kiện xảy ra sau subscription đã thực sự được đăng ký.
6. Đóng connection hoặc gửi `complete` khi không cần.

Cách này cho thấy **Query/Mutation dùng HTTP, Subscription dùng WebSocket nhưng cùng gọi service/resolvers**.

### 10.2. Dạng messages thật

Client gửi ngay sau WebSocket handshake:

```json
{"type":"connection_init"}
```

Server trả:

```json
{"type":"connection_ack"}
```

Client gửi subscription:

```json
{
  "id": "books-live-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { bookAdded { id title category } }"
  }
}
```

Sau khi mutation được tạo và sink emit thành công, server trả message **tương đương**:

```json
{
  "id": "books-live-1",
  "type": "next",
  "payload": {
    "data": {
      "bookAdded": {
        "id": 3,
        "title": "Spring Security",
        "category": "Java"
      }
    }
  }
}
```

Đây là mô hình format GraphQL WS protocol. Thông tin `extensions`, ordering JSON keys và các trường bổ sung có thể khác; không hardcode nguyên chuỗi để parse. Operation dài hạn có thể có **nhiều `next`** và chỉ kết thúc bằng `complete` khi unsubscribe hoặc stream hoàn thành.

### 10.3. Chỉ dùng curl không đủ

`curl -i http://localhost:8080/graphql/ws` không phải một WebSocket GraphQL client hợp lệ. WebSocket cần handshake/subprotocol, sau đó JSON protocol messages bên trong WebSocket frames. Dùng HTML `new WebSocket(url, "graphql-transport-ws")` ở demo hoặc thư viện/CLI hỗ trợ subprotocol. Một WebSocket tool generic không tự gửi `connection_init`/`subscribe` nếu bạn không yêu cầu.

### 10.4. Tại sao có 101 nhưng không có event?

Có thể handshake WebSocket thành công nhưng:

- Client không chọn `graphql-transport-ws`.
- Không gửi `connection_init` hoặc gửi quá muộn, bị connection-init timeout.
- Không chờ `connection_ack` trước khi `subscribe`.
- `payload.query` không phải GraphQL subscription hợp lệ.
- Mutation xảy ra **trước** khi subscriber thực sự kết nối.
- Không có client nào/slow subscriber khiến `Sinks.directBestEffort` bỏ event.
- Proxy bị cắt do idle timeout hoặc auth token hết hạn.
- Bạn dùng protocol cũ `subscriptions-transport-ws` với messages `GQL_START` mà Spring GraphQL hiện đại không hỗ trợ theo cách đó.

Kiểm tra Network → WS Messages/Frames trong browser DevTools và server logs; không chỉ xem HTTP 101.

## 11. Subscription qua SSE: lựa chọn HTTP không cần WebSocket

Spring for GraphQL 1.3 hỗ trợ **GraphQL subscriptions qua Server-Sent Events** trên HTTP endpoint. Khi client gửi GraphQL subscription bằng **HTTP POST** với JSON request body và header `Accept: text/event-stream`, HTTP GraphQL transport có thể trả một stream SSE.

Ví dụ gọi ở terminal thứ nhất:

```bash
curl -N -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  --data '{"query":"subscription { bookAdded { id title category } }"}'
```

Giữ lệnh chạy rồi ở terminal thứ hai gửi mutation như mục 9.1. Khi có event, response đầu tiên có header `Content-Type: text/event-stream`, tiếp theo là các SSE records chứa kết quả GraphQL theo cơ chế GraphQL-over-SSE. **Không đoán chính xác từng dòng raw SSE serialization của Spring GraphQL version**; hãy xác nhận client đọc được result GraphQL tương đương.

**Quan trọng:** native browser `EventSource` thường mở **GET** và không tùy ý gửi POST body hay Authorization headers. Vì Spring GraphQL server SSE trong ví dụ dựa trên **POST + JSON request body + Accept**, không thể thay `curl` trên bằng mỗi dòng:

```javascript
new EventSource("/graphql");
```

Muốn client browser dùng GraphQL over SSE POST, dùng `fetch` streaming reader phù hợp hoặc thư viện GraphQL SSE client hỗ trợ “distinct connections” và đúng media type. Đừng nhầm GraphQL-over-SSE với một SSE endpoint tùy ý `GET /events`.

### 11.1. Khi chọn SSE hay WebSocket cho subscription?

| Nhu cầu | SSE/HTTP POST | WebSocket |
| --- | --- | --- |
| Chỉ nhận events từ server | Phù hợp | Phù hợp |
| Client gửi lệnh thường xuyên trên cùng channel | Cần HTTP requests khác | Có thể multiplex messages/operations |
| Proxy quen HTTP | Thường đơn giản hơn | Phải hỗ trợ WS handshake và idle |
| Browser native API không cần thư viện | Cần `fetch` streaming cho GraphQL POST SSE | Có `WebSocket`, nhưng phải triển khai GraphQL WS messages |
| Nhiều subscriptions/channels | Nhiều HTTP streams có thể tốn resources | Một socket có thể multiplex operations |
| Reconnect/replay | Không tự bảo đảm; ứng dụng phải thiết kế | Không tự bảo đảm; ứng dụng phải thiết kế |
| Auth qua custom headers | HTTP POST client có thể thêm headers | Browser WebSocket không cho đặt tùy ý Authorization header trong handshake |
| Độ phức tạp kết nối | Thường ít state hơn | Cần init/ack/ping/complete/reconnect |

Spring GraphQL hỗ trợ nhiều transport không có nghĩa phải bật tất cả trong production. Chọn theo client library, hạ tầng, nhu cầu và khả năng vận hành.

## 12. Kiểm thử với @GraphQlTest và GraphQlTester

Spring Boot 3.3 có `@GraphQlTest` cho tests **schema/resolvers** mà không khởi động HTTP server hoặc WebSocket listener. Thêm dependency:

```groovy
testImplementation 'org.springframework.graphql:spring-graphql-test'
```

Đã nằm trong `build.gradle` ở mục 7.1. Đặt test file `src/test/java/demo/CatalogGraphQlTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(CatalogGraphQlController.class)
@Import(CatalogStore.class)
class CatalogGraphQlTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void readsBookById() {
        graphQlTester
                .document("{ bookById(id: 1) { title } }")
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Spring Boot");
    }

    @Test
    void addsBookThroughMutation() {
        graphQlTester
                .document("""
                    mutation Add($title:String!,$category:String!) {
                      addBook(title:$title,category:$category) {
                        title
                        category
                      }
                    }
                    """)
                .variable("title", "Spring Security")
                .variable("category", "Java")
                .execute()
                .path("addBook.title")
                .entity(String.class)
                .isEqualTo("Spring Security");
    }

    @Test
    void missingBookIsNull() {
        graphQlTester
                .document("{ bookById(id: 9999) { title } }")
                .execute()
                .path("bookById")
                .valueIsNull();
    }
}
```

**Tại sao cần `@Import(CatalogStore.class)`?** `@GraphQlTest` thường chỉ quét GraphQL controller và các thành phần cấu hình liên quan, không tự quét mọi `@Service` như full `@SpringBootTest`. Import service in-memory cho demo giúp constructor của controller nhận dependency. Với production, có thể dùng mock service và assert resolver gọi đúng methods.

**Vì sao test không kiểm tra WebSocket handshake?** `@GraphQlTest` chạy GraphQL execution layer mà không có live transport. Nó xác minh schema/resolvers/arguments/GraphQL errors ở cấp phù hợp; WebSocket subprotocol, TLS/proxy, Origin, connection_init, auth và reconnect cần integration tests khác.

Chạy:

```bash
./gradlew test
```

Kết quả test thành công theo logic là ba JUnit tests pass; không khẳng định stdout Gradle cụ thể vì phụ thuộc version/console/output settings.

### 12.1. HTTP integration test

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot có thể auto-configure `HttpGraphQlTester` cho live server, tùy test dependencies. Một test HTTP end-to-end nên kiểm tra:

- `POST /graphql` với query/variables.
- JSON response `data/errors` và media type.
- Authorization headers/cookies/CSRF policy như deployment.
- Request body limit, parser errors, invalid operations.
- Query complexity/rate limit.
- Một mutation chỉ thay đổi dữ liệu hợp lệ và không lộ data sai quyền.

`GraphQlTester` là abstraction chung; `HttpGraphQlTester` và `WebSocketGraphQlTester` bổ sung đặc thù transport. Không coi một unit test resolver `@GraphQlTest` là bằng chứng rằng CDN/NGINX WebSocket path đã hoạt động.

### 12.2. WebSocket integration test

`WebSocketGraphQlTester` kết nối tới GraphQL WS transport và dùng chung WebSocket connection, có thể test subscription Flux kết quả và cancellation. Cần một WebSocket client implementation và boot server thật. Khi thiết kế test:

1. Tạo WebSocket tester tới `ws://localhost:<port>/graphql/ws` theo URL/port thực.
2. Start `subscription { bookAdded { id title } }` trước.
3. Chờ subscription thực sự active hoặc dùng synchronization hook trong test.
4. Gửi mutation HTTP.
5. Assert một `bookAdded` event đúng, hủy subscription và đóng tester.
6. Test permission failure khi không có credentials/Origin.
7. Test reconnect/disconnect và cleanup; đừng viết test dựa trên sleep cố định nhiều giây vì dễ flaky.

Trong production, cần test qua reverse proxy nữa; WebSocket test nối localhost tới app có thể pass dù ingress không forward `Upgrade`.

## 13. Security: một URL GraphQL không có nghĩa chỉ có một quyền

REST có thể authorize đường `/orders/**` theo URL. GraphQL thường gom rất nhiều operations/fields sau `/graphql`, nên **URL authorization chỉ là lớp ngoài**:

```text
POST /graphql
    |
    +-- Query.books                 public hoặc user
    +-- Query.bookById             kiểm tra tenant/permission
    +-- Mutation.addBook           role EDITOR/ADMIN
    +-- Subscription.bookAdded     role SUBSCRIBER và filter scope
```

Nếu security config chỉ có `/graphql authenticated()`, một user đã login có thể vẫn không được phép chạy mọi mutation/query. Phải authorize **field/resolver/service và dữ liệu từng bản ghi**.

### 13.1. Spring Security cho HTTP GraphQL

Trong ứng dụng Servlet có Spring Security, có thể yêu cầu authentication cho HTTP GraphQL:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/graphql").authenticated()
    .requestMatchers("/graphql/ws").authenticated()
    .anyRequest().denyAll()
);
```

Đây là **snippet policy**, không phải `SecurityFilterChain` hoàn chỉnh. Nó giả định đúng URL và muốn khóa các đường khác; trong ứng dụng có trang public/static, cần rules riêng phù hợp trước fallback. Với WebSocket path, security filter trên handshake có thể yêu cầu session/cookie hoặc authentication, nhưng **sau khi upgrade** phải kiểm tra quyền mỗi GraphQL operation, không dựa chỉ vào việc socket đã mở.

### 13.2. Phân quyền trong resolver/service

Spring Security method security có thể dùng `@EnableMethodSecurity` và `@PreAuthorize`:

```java
@MutationMapping
@PreAuthorize("hasRole('EDITOR')")
public Book addBook(
        @Argument("title") String title,
        @Argument("category") String category) {
    return store.add(title, category);
}
```

Đây là **snippet thay thế** cho method demo khi app có Spring Security dependency và được cấu hình đúng. Nó không chạy độc lập. Trong production, thêm authorization ở service/data layer để ngăn user đọc/ghi dữ liệu của tenant khác ngay cả khi biết ID. Các subscriptions có thể sống lâu hơn thời hạn token/role; cần chính sách revalidate/close khi quyền thay đổi.

### 13.3. WebSocket authentication không đồng nghĩa HTTP

Browser `new WebSocket()` không cho JavaScript đặt arbitrary HTTP Authorization header theo cách `fetch` làm. Thường có các lựa chọn:

- Cookie session từ cùng origin với TLS và CSRF/Origin protections phù hợp.
- Token được chuyển trong `connection_init.payload` và xử lý bằng `WebSocketGraphQlInterceptor`/`AuthenticationWebSocketInterceptor` của Spring GraphQL khi có tích hợp security.
- Credential qua subprotocol hoặc query string **chỉ khi có thiết kế an toàn rõ**, tránh lộ token trong URL logs, referrer và proxy analytics.

Spring for GraphQL 1.3 cung cấp hỗ trợ tích hợp authentication trong `connection_init` bằng interceptors cho Servlet/WebFlux. Nhưng gửi payload `{"Authorization":"Bearer ..."}` **không tự biến** nó thành authenticated Principal nếu chưa đăng ký/thiết lập interceptor thích hợp.

Phải tránh hai lỗ hổng:
1. Socket đã handshake với role nào thì được tin mãi dù role/token bị thu hồi.
2. Message subscription được mở tới topic/tenant khác chỉ bằng sửa `variables`.

### 13.4. CORS khác WebSocket Origin

`spring.graphql.cors.*` của Boot giúp cấu hình CORS cho HTTP GraphQL browser requests. Ví dụ cho frontend khác origin:

```properties
spring.graphql.cors.allowed-origins=https://ui.example.test
spring.graphql.cors.allowed-methods=POST
spring.graphql.cors.max-age=1800s
```

Đây là **mẫu khi thực sự cross-origin**, không cần cho browser demo same-origin. Với cookie credentials, còn cần CORS allow-credentials policy theo server, cookie `SameSite`/`Secure`, CSRF; không dùng wildcard Origin cùng credentials.

WebSocket handshake dùng `Origin`, không được bảo vệ chỉ bằng HTTP CORS rules. Browser WebSocket có thể tạo kết nối cross-site; nếu cookie xác thực được tự gửi, không kiểm tra Origin có nguy cơ **Cross-Site WebSocket Hijacking**. Cần Origin allowlist, authentication, per-operation permission và network policy phù hợp. Client không phải browser có thể tự đặt Origin, nên Origin không thay authentication.

### 13.5. CSRF với cookie/session và HTTP mutation

Nếu Spring Security dùng session/cookie authentication, POST GraphQL mutation có thể bị CSRF protection từ chối nếu thiếu CSRF token. Query cũng thường dùng POST tại `/graphql`, nên không thể chỉ nói “GET an toàn, POST thay đổi trạng thái” rồi tắt CSRF chung cho mọi POST. Tùy ứng dụng:

- Chuyển các browser GraphQL POST requests mang cookie sang CSRF token flow phù hợp.
- Với API bearer-token stateless không dùng cookies, xây security chain và CSRF policy theo threat model.
- Xem xét tách endpoints/methods/authorization hoặc persisted query approach khi cần.
- Không tắt `csrf.disable()` cho toàn ứng dụng chỉ để “GraphQL gửi POST được”.

Trong demo không thêm security starter để tập trung vào transport; **không triển khai nó trên public Internet mà không bổ sung bảo vệ**.

## 14. Giới hạn độ sâu, độ phức tạp và N+1

GraphQL linh hoạt cho client nhưng nếu không giới hạn, một query có thể gây tải cực lớn:

```graphql
query {
  teams {
    members {
      projects {
        tasks {
          comments {
            author {
              name
            }
          }
        }
      }
    }
  }
}
```

Ngay cả khi mỗi field đơn giản, fan-out theo danh sách nhân nhiều tầng có thể tạo rất nhiều DB queries/CPU/memory. Phải đặt các giới hạn:

- **Max query depth**: không cho chọn quá nhiều tầng lồng nhau.
- **Max query complexity/cost**: tính chi phí dự kiến theo field, list size và arguments.
- **Pagination**: yêu cầu `first/after` hoặc offset/limit có maximum.
- **Rate limiting/quotas**: theo user/tenant/token và cả connection/subscription.
- **Request body/document size**: chống tài liệu GraphQL rất lớn.
- **Execution timeout/cancellation**: dừng query downstream chậm, không giữ worker/thread vô hạn.
- **Persisted queries/allowlist** cho clients chính thức nếu phù hợp.
- **Introspection policy** tùy môi trường. Tắt introspection không thay authentication.

GraphQL Java có các instrumentation như `MaxQueryDepthInstrumentation` và `MaxQueryComplexityInstrumentation`; Spring Boot có hook `GraphQlSourceBuilderCustomizer` để cấu hình GraphQL runtime. Cần benchmark/tune theo schema thật thay vì áp một giá trị không căn cứ. Với một query có pagination lỏng, depth thấp vẫn có thể tốn rất nhiều tài nguyên.

### 14.1. N+1 query khi resolver tải quan hệ

Ví dụ `books { author { name } }`, một resolver `author` có thể query database riêng cho mỗi cuốn sách, tạo 1 + N queries. Spring for GraphQL hỗ trợ `DataLoader`/`@BatchMapping`:

```java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    // Query toàn bộ authors liên quan trong một lần,
    // trả Map<Book, Author> để GraphQL map về từng parent.
    return authorService.loadAuthorsFor(books);
}
```

Đây là **snippet**, có `Author`/`authorService` giả định và schema phải định nghĩa Book.author. Không nằm trong chương trình runnable ở mục 7. Với JPA, cần tính đến N+1 cả ở ORM fetch plan và tenant authorization; `DataLoader` giúp batching nhưng không tự sửa mọi query chậm.

### 14.2. Chỉ trường nào có trong schema mới có thể được hỏi?

GraphQL schema đóng vai trò allowlist các field ở tầng API. Nhưng một field tồn tại trong schema vẫn **không có nghĩa bất kỳ người dùng nào được quyền xem nó**. Nếu `User.email` hoặc `Admin.auditLog` có trong schema, service phải authorize theo role/owner/tenant. Introspection có thể làm schema dễ khám phá nhưng kẻ tấn công vẫn có thể đoán field names; **tắt introspection không thay authorization**.

## 15. Error handling và quan sát

Spring for GraphQL có `DataFetcherExceptionResolver` để ánh xạ exception từ DataFetchers thành GraphQL errors an toàn, có `extensions.classification` hoặc error codes phù hợp. Ví dụ một mutation thất bại do permission nên trả error type mà client hiểu, không đưa stacktrace/SQL messages ra ngoài.

Đừng ném exception Java tùy ý và đợi HTTP status 500 như REST mọi lúc: GraphQL execution có thể chứa lỗi trong `errors` cùng partial data. Cần có một contract:

- Thông điệp user-facing ngắn, không tiết lộ nội bộ.
- Error code ổn định cho client khi cần.
- Correlation/request ID liên kết logs/traces.
- Retryable hay non-retryable được phân loại.
- Các lỗi transaction được rollback đúng.
- Field-level authorization không làm lộ tên tài nguyên của tenant khác khi không cần.

### 15.1. Observability

Theo dõi:

- `graphql.operation`/operation name (cẩn thận cardinality), loại query/mutation/subscription.
- Execution time p50/p95/p99 và số GraphQL errors.
- Field resolver latency và số DB queries/request, N+1 patterns.
- WebSocket active connections, active subscriptions, connection_init failures.
- Protocol close codes, reconnect rate, client disconnect/cancel.
- CPU, heap, connection buffers, Reactor sink dropped events.
- Broker lag/queue depth/replay gaps nếu dùng durable event source.
- 401/403 HTTP, subscription authorization denials, CORS/Origin failures.
- HTTP status và GraphQL `errors` **cùng lúc**; chỉ metric HTTP 200 có thể che field errors.

Không log raw GraphQL variables nếu chúng có password/token/PII; không gắn user ID/operation document đầy đủ làm metric labels. Tránh trả stacktrace ở production hoặc mở GraphiQL/schema printer không kiểm soát.

## 16. NGINX và ingress: HTTP + WebSocket cùng một ứng dụng

Một reverse proxy có thể cho public clients POST `/graphql` và mở WebSocket `/graphql/ws`. Với HTTP/1.1 WebSocket, cần forward Upgrade/Connection headers; GET HTTP `/graphql/ws` thông thường không đủ.

Snippet NGINX dùng trong môi trường test; `map` đặt ở ngữ cảnh `http`, `server` cũng dưới `http`:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 8081;
    server_name localhost;

    location = /graphql/ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 90s;
        proxy_send_timeout 90s;
    }

    location = /graphql {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Nếu dùng GraphQL SSE, cần kiểm thử buffering.
        proxy_buffering off;
        proxy_read_timeout 90s;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

Đây là **server block minh họa**, không phải production NGINX config hoàn chỉnh. Nếu NGINX chạy trong container khác, `127.0.0.1:8080` trỏ tới chính NGINX container; cần thay upstream bằng service DNS thích hợp. Với public HTTPS, phải cấu hình TLS, truyền Host/Forwarded headers đúng và dùng `wss://` ở browser. Không triển khai snippet HTTP này làm production endpoint công khai.

**Proxy/WebSocket cần chú ý:**

- `Upgrade` và `Connection` là hop-by-hop HTTP/1.1 headers; proxy phải forward chúng cho handshake.
- `proxy_read_timeout` giới hạn thời gian không có dữ liệu từ upstream, không phải bảo đảm WebSocket sống 90 giây bất kể traffic.
- GraphQL WS keep-alive ping và WebSocket control ping/pong là những tầng khác nhau; phải đo tương thích toàn chuỗi proxy.
- Khi dùng CDN/load balancer, xác nhận hỗ trợ WebSocket và idle timeout; không phải mọi CDN cache policy áp dụng cho WS.
- Nếu dùng HTTP/2/H3 giữa browser và edge, WebSocket có thể dùng cơ chế protocol/extended CONNECT tùy stack; đừng giả định mọi hop hỗ trợ như HTTP/1.1 Upgrade.
- GraphQL SSE là stream qua HTTP; buffering/compression có thể làm events tới client trễ hoặc bị gom.
- Không cache shared GraphQL responses chứa dữ liệu cá nhân. POST thường không được cache mặc định, nhưng CDN/custom gateway có thể cấu hình khác; bảo vệ cache policy theo user/tenant.

## 17. Subscription ở nhiều replicas: không chỉ bật WebSocket là xong

Giả sử 2 Spring Boot instances A và B:

```text
              Browser 1              Browser 2
                 |                       |
            WS subscribed           WS subscribed
                 |                       |
               Pod A                   Pod B
                 \                       /
                  \                     /
                   Shared Event Broker
                  /                     \
           Business producer        Business producer
```

Trong demo `CatalogStore` tạo một `Sinks.Many` **ở mỗi JVM riêng**. Mutation vào pod A chỉ phát events tới subscribers đang theo dõi pod A. Nếu browser WebSocket nối pod B, nó **không** tự nhận event tạo ở A. Vấn đề tương tự xảy ra khi app restart, autoscale và rolling deploy.

Để scale, cần:

1. Business changes được commit trong database đúng transaction.
2. Event được phát qua shared bus/broker; muốn bền vững dùng outbox/event log.
3. Mỗi pod nhận event và đẩy đến GraphQL subscription clients đang kết nối ở pod đó.
4. Kiểm tra user/tenant/room filters trước khi emit.
5. Định nghĩa ordering, at-least-once vs best effort, idempotency, dedup và replay.
6. Giới hạn số subscribers/queues và cách xử lý slow clients.
7. Khi WebSocket reconnect tới pod khác, client gửi lại cursor hoặc query snapshot rồi subscribe.

Sticky sessions chỉ giữ client đi cùng một pod khi pod còn sống; **không sao chép bộ nhớ và không cứu một socket sau pod restart**.

### 17.1. GraphQL subscriptions không phải database change feed tự động

Chỉ thêm `@SubscriptionMapping` không khiến Spring Data/JPA tự phát events khi một table thay đổi. Bạn cần nối nguồn sự kiện vào `Flux`/`Publisher`. Với Redis Pub/Sub, subscriber rớt mạng có thể bỏ lỡ events; với Kafka/Redis Streams, cần cursor và retention/consumer offset phù hợp. Chọn dựa trên yêu cầu sản phẩm chứ không phải chỉ để “có GraphQL WS”.

### 17.2. Slow subscribers và backpressure

WebSocket GraphQL có thể multiplex nhiều operations, nhưng không có nghĩa browser luôn tiêu thụ đủ nhanh. Khi events đến 1.000/s mà client render 10/s, buffers có thể tăng. Trong Spring MVC, writes có thể blocking trên async executor; WebFlux có non-blocking I/O và Reactor backpressure trong pipeline, nhưng vẫn phải xét network buffers, queue, browser limitations.

Với sink `directBestEffort` trong demo, slow subscribers có thể bị bỏ event để tránh buffer vô hạn. Nếu cần mọi event, phải có durable queue/cursor và replay, không đổi sang một `onBackpressureBuffer()` không giới hạn vì dễ OOM.

## 18. WebFlux và RSocket: cùng schema, runtime vận chuyển khác

Spring Boot cho phép chọn:

| Stack | Dependencies | HTTP GraphQL | GraphQL WS |
| --- | --- | --- | --- |
| Servlet MVC | graphql + web + websocket | Có | Có, sau khi đặt websocket path |
| WebFlux | graphql + webflux | Có | Có, sau khi đặt websocket path |
| RSocket | graphql + rsocket | Theo RSocket request-response/stream | Khác GraphQL-over-WebSocket HTTP handler |

Nếu ứng dụng **chỉ** dùng WebFlux, không cần `spring-boot-starter-websocket` Servlet; Spring GraphQL có WebFlux WS handler. Nhưng `GraphQlWebSocketHandler` reactive không đồng nghĩa raw Spring MVC `TextWebSocketHandler`. Tương tự, GraphQL-over-RSocket là transport khác với GraphQL-over-WebSocket dựa trên `graphql-transport-ws`.

Đừng trộn `spring-boot-starter-web` và `spring-boot-starter-webflux` mà giả định ứng dụng tự chuyển sang reactive: Boot có quy tắc ưu tiên web application type; cần chọn stack rõ.

### 18.1. Resolver blocking và non-blocking

Một `@QueryMapping` trả `List<Book>`/JPA call có thể block thread; `@SubscriptionMapping` trả `Flux<Book>` cho kết quả nhiều phần tử. WebFlux event loop không nên chạy JDBC/blocking I/O trực tiếp; offload sang executor/scheduler phù hợp hoặc dùng reactive persistence thực sự.

Spring GraphQL 1.3 có khả năng cấu hình executor cho blocking controller methods, gồm virtual threads khi Java 21+ và Spring Boot property tương ứng. Bài mẫu vẫn dùng **Java 17** và in-memory operations nên không đòi virtual threads.

### 18.2. Reactive streams không thay business replay

GraphQL subscriptions dùng Reactive Streams `Publisher`, `Flux` phát nhiều results, nhưng khi client/người dùng mất kết nối, dữ liệu không được tự lưu. Backpressure là vấn đề tốc độ phát/tiêu thụ; replay/durability là vấn đề lưu trữ và business semantics khác. Đừng coi có `Flux` là đã bảo đảm “không mất event”.

## 19. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| POST `/graphql` 404 | Thiếu web starter/đổi path hoặc app chưa khởi động | Kiểm tra Boot dependencies, `spring.graphql.path` |
| App startup báo schema error | SDL sai/thiếu file `graphql/*.graphqls` hoặc mapping mismatch | Kiểm tra SDL parse và schema inspection |
| Query HTTP trả `errors` | Field/argument sai, resolver lỗi, thiếu auth | Xem cả HTTP status, `data`, `errors` |
| Field trả null | Không có dữ liệu hoặc resolver lỗi/permission | Đối chiếu nullable field và errors |
| `bookAdded` không có event | Chưa subscribe, mutation đến quá sớm, sink best effort | Subscribe trước, đo sink emission và source |
| WS handshake 404 | WebSocket starter thiếu hoặc chưa cấu hình path | Bật `spring.graphql.websocket.path` + starter |
| WS handshake 400/403 | Subprotocol/Origin/handshake security sai | Dùng `graphql-transport-ws` và đúng policy |
| WS open rồi bị đóng | Không gửi connection_init, timeout hoặc proxy idle | Xem connection-init protocol, keepalive, logs |
| WS có ACK nhưng không ra next | Chưa gửi subscribe, wrong operation/query, no source events | Kiểm tra WS frames và resolver/sink |
| Client dùng `graphql-ws` subprotocol cũ | Nhầm với `subscriptions-transport-ws` | Chọn `graphql-transport-ws` của thư viện graphql-ws mới |
| SSE POST không chạy với EventSource | Native EventSource dùng GET không có body | Dùng fetch-stream/GraphQL SSE client |
| Client chỉ xét HTTP status 200 | GraphQL errors nằm trong response JSON | Xét cả `errors`/partial data |
| Query cực chậm sau thêm quan hệ | N+1 và truy vấn lồng sâu | `@BatchMapping`/DataLoader, depth/cost/pagination |
| CPU tăng vì subscriptions | Quá nhiều active connections/expensive resolver/slow consumer | Limits, throttling, fanout architecture |
| Một pod thấy event, pod khác không | Local in-memory sink, không có shared broker | Pub/Sub/outbox/broker và subscription routing |
| Mutation chạy nhưng client không nhận event | Event loss/race hoặc listener ở pod khác | Durable replay khi cần, test multi-replica |
| GraphiQL mở công khai | Dev property để lại ở production | Tắt/bảo vệ GraphiQL và introspection theo policy |
| POST mutation bị 403 khi có Spring Security | CSRF token hoặc role/policy thiếu | Định nghĩa auth/CSRF flow; không tắt bừa bãi |
| WebSocket dùng ws trên trang HTTPS | Mixed content/TLS termination | Dùng `wss://` và proxy HTTPS đúng |
| Reconnect tạo duplicate dữ liệu | At-least-once replay không dedup | Event ID, unique constraints/idempotency |
| WS request qua NGINX chỉ là 400 | Proxy không chuyển Upgrade/Connection | Cấu hình WebSocket hop đúng |
| Response cá nhân bị cache | CDN/gateway cache policy sai | Private/no-store/authorization và cache key |

## 20. Bài tập tự kiểm tra

**1.** Có `type Query { books: [Book!]! }` và method `@QueryMapping books()`. Có cần viết `@PostMapping("/graphql")` không?  
**Đáp án:** Không. Spring Boot/Spring for GraphQL tự tạo GraphQL HTTP handler; resolver method chỉ ánh xạ field trong schema.

**2.** Dự án chỉ thêm `spring-boot-starter-graphql` và `spring-boot-starter-web`. WebSocket GraphQL đã hoạt động chưa?  
**Đáp án:** Chưa. Với Servlet cần WebSocket starter và `spring.graphql.websocket.path`. HTTP POST có thể hoạt động mà WS chưa expose.

**3.** Browser mở WS subprotocol `graphql-ws` từ thư viện cũ rồi gửi `GQL_START`, server Spring GraphQL mong `graphql-transport-ws`. Điều gì xảy ra?  
**Đáp án:** Không tương thích protocol. Phải dùng client mới `graphql-ws` với subprotocol string `graphql-transport-ws` và messages `connection_init/subscribe/next`.

**4.** Mutation `addBook` trả HTTP 200 nhưng response chứa `errors`. Có thể coi thành công hoàn toàn?  
**Đáp án:** Không. Client cần kiểm tra `errors` và `data` theo GraphQL response semantics; HTTP status một mình không đủ.

**5.** GraphQL `String!` có chặn chuỗi `""` không?  
**Đáp án:** Không, non-null không có nghĩa non-blank. Cần validation nghiệp vụ như service kiểm tra `isBlank()`.

**6.** Subscription client đã nhận `connection_ack` nhưng không thấy sự kiện mới. Các bước kiểm tra?  
**Đáp án:** Đã gửi `subscribe` đúng `id/payload/query` chưa, subscription đã active chưa, mutation có phát event không, sink có subscriber/overflow không, có proxy/permissions hay multi-pod routing không.

**7.** Sau restart JVM, browser WS tự kết nối lại và nhận sự kiện bị lỡ?  
**Đáp án:** Không. WebSocket browser không tự reconnect và GraphQL protocol không tự replay; cần client reconnect + durable event cursor/replay nếu sản phẩm đòi hỏi.

**8.** `GraphQlTester` của `@GraphQlTest` pass có đủ chứng minh WS qua NGINX hoạt động?  
**Đáp án:** Không. Nó test GraphQL execution mà không khởi động transport; cần live WebSocket integration test và kiểm thử proxy.

**9.** Query GraphQL có depth 8, mỗi danh sách chứa hàng nghìn phần tử. Có thể quá tải dù depth không lớn?  
**Đáp án:** Có. Cần complexity/cost, pagination, quota, DataLoader và timeout, không chỉ max depth.

**10.** Một user authenticated chạy GraphQL query có field chứa email của user khác. URL `/graphql` đã `authenticated()` có đủ chưa?  
**Đáp án:** Không. Phải kiểm tra quyền ở resolver/service và object-level authorization.

**11.** Native `EventSource("/graphql")` có gửi GraphQL subscription POST JSON body theo Spring GraphQL SSE trong bài không?  
**Đáp án:** Không. Native EventSource dùng GET; cần client SSE GraphQL phù hợp hoặc fetch streaming POST.

**12.** Vì sao trên 3 pods không nên dùng một `Sinks.Many` local để bảo đảm tất cả subscribers nhận mutation?  
**Đáp án:** Sink chỉ trong JVM, các pods không chia sẻ. Cần shared event bus và, nếu muốn bền, event store/outbox/replay.

## 21. Checklist production

- [ ] GraphQL schema SDL được version/control/review, có tests chống breaking changes.
- [ ] Query/Mutation và Subscription có giới hạn riêng, không xem tất cả GraphQL operations như nhau.
- [ ] Spring Boot starter đúng stack; WS path được bật có chủ đích, không phải tự có sẵn.
- [ ] Client và server đồng ý **`graphql-transport-ws`**; không nhầm protocol cũ.
- [ ] GraphQL HTTP clients gửi JSON `query/variables/operationName` và xử lý `data/errors` đúng.
- [ ] WebSocket client gửi connection_init, chờ ACK rồi subscribe, hủy/đóng khi không dùng.
- [ ] Subscription source thực sự phát events; event reliability được xác định rõ (best effort/durable).
- [ ] AuthN/AuthZ được kiểm tra ở HTTP, WS handshake, operations và object/tenant fields.
- [ ] Browser CORS/Origin, cookies/CSRF và TLS/WSS có chính sách đúng.
- [ ] Query depth, cost/complexity, pagination, request size, rate limit và execution timeouts được đặt.
- [ ] Resolver N+1 được đo và xử lý bằng batching/DataLoader khi cần.
- [ ] Introspection, GraphiQL, schema printer và logging nhạy cảm được giới hạn production.
- [ ] WS keepalive, proxy Upgrade/idle timeout, SSE buffering và reconnect được thử qua edge thật.
- [ ] WS connection/subscription counts, queue size, dropped events và error rates có metrics.
- [ ] Nhiều replicas có shared broker; không dựa vào sink in-memory hoặc sticky session để đảm bảo giao event.
- [ ] Có tests cho GraphQL schema/resolvers, HTTP status/errors, WS handshake và subscriptions qua network.
- [ ] Có kế hoạch reconnect/backoff/resubscribe/cursor/replay khi client hoặc node mất kết nối.
- [ ] Mutation thay đổi dữ liệu dùng transaction/idempotency khi cần và event emission nhất quán với commit.
- [ ] Rollout có rollback, log redaction và quyền truy cập diagnostic phù hợp.

## Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Spring for GraphQL](https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html)
2. [Spring Boot 3.3 — Application Properties: spring.graphql.*](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
3. [Spring Boot 3.3 — Testing Spring GraphQL](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
4. [Spring for GraphQL — Annotated Controllers, @QueryMapping, @MutationMapping, @SubscriptionMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
5. [Spring for GraphQL — HTTP, WebSocket và SSE Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
6. [Spring for GraphQL — GraphQlTester Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
7. [graphql-ws — GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
8. [GraphQL over HTTP Working Draft](https://graphql.github.io/graphql-over-http/draft/)
9. [GraphQL Specification](https://spec.graphql.org/)
10. [Project Reactor — Sinks.MulticastSpec directBestEffort](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html)
11. [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
12. [Spring Security — Method Security and Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)

**Điều cần nhớ:** GraphQL mô tả **schema và operation**; HTTP POST và WebSocket là các **đường vận chuyển** cùng operation tới Spring for GraphQL. Query/mutation thường đi HTTP, subscription thường dùng WebSocket với `graphql-transport-ws` (hoặc SSE khi client/hạ tầng phù hợp). Chọn đúng transport chỉ là bước đầu; **authorization cấp field, query cost, lifecycle kết nối, replay và scale nhiều nodes** mới quyết định một GraphQL API có vận hành an toàn, tin cậy hay không.
