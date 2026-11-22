# GraphQlTester cho query, mutation và biến đầu vào trong Spring Boot

## Mục tiêu

Trong Spring Boot, GraphQL cho phép client gửi một **document** gồm operation `query`, `mutation` (hoặc `subscription`) và chọn chính xác các field cần đọc. Khi kiểm thử, việc gửi HTTP POST đến `/graphql` rồi chỉ kiểm status 200 là chưa đủ: một response GraphQL có thể mang **`errors` ngay cả khi HTTP transport thành công**, và một mutation trả dữ liệu đúng chưa chắc đã tạo đúng side effect.

`GraphQlTester` từ thư viện **Spring for GraphQL Test** là một API kiểm thử thống nhất: gửi GraphQL document, truyền variables, chạy operation, kiểm **`data` bằng JSONPath**, xác minh `errors` và kiểm kết quả của query/mutation. Cùng một cách viết assertion có thể dùng với GraphQL engine nội bộ hoặc HTTP client khi chọn tester phù hợp.

Sau bài học, bạn có thể:

- Phân biệt `query`, `mutation`, `variables`, `operationName`, GraphQL schema và selection set.
- Viết test `GraphQlTester.document(...).variable(...).execute().path(...).entity(...).isEqualTo(...)`.
- Tái sử dụng document qua `documentName(...)` và `src/test/resources/graphql-test/*.graphql`.
- Truyền scalar `ID!`, `String!`, `Int!` và input object `BookInput!` bằng `variable`/`variables(Map)`.
- Kiểm nested object, danh sách, field `null`, field không tồn tại và số lượng/thứ tự kết quả.
- Kiểm mutation **cả response lẫn thay đổi trạng thái** qua một query tiếp theo hoặc tầng lưu trữ phù hợp.
- Phân biệt lỗi **GraphQL request/validation/execution** với lỗi HTTP transport; dùng `errors().expect/filter/satisfy`.
- Chọn `@GraphQlTest`/`ExecutionGraphQlServiceTester` cho GraphQL slice, hay `@SpringBootTest(RANDOM_PORT)`/`HttpGraphQlTester` cho HTTP integration.
- Chạy ví dụ Java 17 + Spring Boot 3.3.5 + JUnit Jupiter + Gradle gồm schema, controller, service in-memory, query, mutation và tests độc lập.

Bài viết nằm trong module **Spring Boot – testing**, nhánh **GraphQL và SOAP**. Nội dung tập trung vào **GraphQL**: SOAP là protocol/message model khác, không dùng GraphQlTester để kiểm SOAP envelope, WSDL hay SOAP Fault.

## 1. Từ HTTP request đến GraphQL response

Một GraphQL request thông thường có các thành phần:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
    pages
  }
}
~~~

Đây là **GraphQL document** với một operation tên `FindBook`. Dấu `$id` khai báo biến có kiểu `ID!` (không chấp nhận null), còn `book(id: $id)` đưa giá trị biến vào tham số resolver. Client phải gửi kèm variables, ví dụ:

~~~json
{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title pages } }",
  "variables": {
    "id": "b1"
  },
  "operationName": "FindBook"
}
~~~

Với HTTP GraphQL thường dùng `POST /graphql`, Content-Type `application/json`. HTTP body này là **GraphQL-over-HTTP request**, không phải REST endpoint `GET /api/books/b1`.

Nếu có book, GraphQL response minh họa:

~~~json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Java 17",
      "pages": 300
    }
  }
}
~~~

Nếu ID không tồn tại và schema khai báo `book(...): Book` (nullable), phản hồi hợp lệ có thể là:

~~~json
{
  "data": {
    "book": null
  }
}
~~~

Nếu lỗi validation hoặc execution, response có thể chứa:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "Lỗi GraphQL được mô tả tại đây"
    }
  ]
}
~~~

Response này chỉ là **minh họa cấu trúc**, không phải message chính xác của một phiên bản Spring GraphQL. Các error còn có thể có `locations`, `path`, `extensions` và kiểu phân loại. Có lỗi khiến một phần `data` vẫn tồn tại; không được đồng nhất “có errors” với “data chắc chắn null”.

### Query và mutation có ý nghĩa gì?

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `query` | Đọc dữ liệu; server thường thiết kế không tạo tác dụng phụ | `book(id: "b1")`, `books` |
| `mutation` | Yêu cầu thay đổi trạng thái | `addBook(input: ...)` |
| `subscription` | Luồng sự kiện theo thời gian | `bookAdded` |
| `variables` | Giá trị truyền riêng khỏi document | `id`, `input` |
| `selection set` | Các field client muốn trong response | `{ id title pages }` |
| `operationName` | Chọn operation khi document có nhiều operation | `FindBook` |
| `schema` | Hợp đồng type/field/argument của server | `type Query`, `input BookInput` |

GraphQL **không bảo đảm mutation tự động nằm trong một transaction DB**. Mutation là một operation có ý định thay đổi; việc commit, rollback và dọn dữ liệu test phải được kiểm ở tầng dữ liệu nếu hệ thống có side effects.

## 2. Vì sao dùng `GraphQlTester` thay vì so chuỗi JSON?

Nếu dùng HTTP client thuần, test có thể viết:

~~~java
assertEquals(200, response.statusCode());
~~~

Assertion này chỉ nói HTTP transport trả status 200. GraphQL engine có thể trả 200 cùng `errors` hoặc `data` sai. So sánh nguyên chuỗi JSON cũng giòn: thứ tự property/whitespace không phải lúc nào là yêu cầu.

`GraphQlTester` giúp viết:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
          book(id: $id) {
            id
            title
            pages
          }
        }
        """)
        .variable("id", "b1")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

Đoạn này là snippet nằm trong một Spring GraphQL test đã cấu hình `graphQlTester`. Nó mô tả: thực thi document, gửi biến `id`, sau đó truy cập **`data.book.title`** và kiểm String.

Đáng chú ý: `path("book.title")` **được hiểu tương đối với phần `data`** của GraphQL response. Không viết `path("data.book.title")` như thể path bắt đầu từ root HTTP JSON body.

### Chuỗi thao tác có chủ đích

~~~text
GraphQlTester
    |
    +-- document("query ...") hoặc documentName("findBook")
    |
    +-- variable("id", "b1")
    |
    +-- execute()    -> gửi operation, nhận GraphQL response
    |
    +-- errors()     -> kiểm lỗi nếu đang trông đợi lỗi
    |
    +-- path("book.title")
    |      |
    |      +-- entity(String.class)
    |               |
    |               +-- isEqualTo("Java 17")
    |
    +-- path("books[*].title").entityList(String.class)
~~~

Khác với `StepVerifier` của Reactor, GraphQlTester là API trực tiếp cho **GraphQL request/response**. Không dùng `StepVerifier` để thay những assertion về GraphQL `data`/`errors` nếu phép thử chỉ kiểm một query/mutation thông thường.

## 3. Chọn đúng biến thể tester

Spring for GraphQL có một interface chung là `org.springframework.graphql.test.tester.GraphQlTester`, nhưng các implementation khác nhau ở **nơi thực thi request**.

| Tester/môi trường | Có HTTP server thật? | Kiểm được gì? | Khi nào nên dùng? |
| --- | --- | --- | --- |
| `ExecutionGraphQlServiceTester` | Không | GraphQL execution, schema, resolver/data fetcher | Unit/slice test server-side |
| `WebGraphQlTester` | Không cần HTTP | WebGraphQlHandler và WebGraphQlInterceptor trong một context server-side | Khi test đặc điểm WebGraphQlHandler |
| `HttpGraphQlTester` | Có thể có hoặc không, tùy WebTestClient binding | GraphQL qua HTTP transport, headers, authentication tùy cấu hình | HTTP/GraphQL integration |
| `WebSocketGraphQlTester` | Giao tiếp WebSocket | GraphQL over WebSocket, đặc biệt subscriptions | WebSocket/subscription tests |
| `RSocketGraphQlTester` | RSocket transport | GraphQL qua RSocket | Hệ thống dùng RSocket |

Trong **Spring Boot 3.3.x**:

- `@GraphQlTest(BookGraphQlController.class)` tạo GraphQL test slice **không có transport/server**, cấu hình bean `GraphQlTester` server-side để test controller/resolver.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` có server HTTP thật; với dependencies test thích hợp, Boot có thể cung cấp `HttpGraphQlTester` kết nối tới application server.
- `@SpringBootTest(webEnvironment = MOCK)` không mở cổng thật; nếu muốn HTTP tester trên mock web environment, dùng `@AutoConfigureHttpGraphQlTester` và cấu hình tester phù hợp.
- Nếu tự khởi tạo `HttpGraphQlTester`, cần `WebTestClient` gắn đúng base URL hoặc application context.

**Không gọi `@GraphQlTest` là kiểm HTTP end-to-end.** Nó rất có giá trị vì kiểm GraphQL schema, argument binding và resolver thật mà không cần mở socket, nhưng không chứng minh HTTP route, proxy, authentication filter, CORS, SSL hay network response.

### `@GraphQlTest` không quét toàn bộ ứng dụng

Test slice có phạm vi scan hạn chế, thường tập trung `@Controller`, GraphQL runtime wiring và các thành phần hỗ trợ. Các service/repository thông thường **không tự động có đầy đủ** trong slice. Có thể:

- Dùng `@MockBean` theo Spring Boot 3.3 để mock dependency của controller.
- Dùng `@Import(BookCatalog.class)` để thêm một service/fake thật khi muốn kiểm behavior.
- Dùng `@TestConfiguration` với bean được đăng ký có mục đích.
- Chuyển sang `@SpringBootTest` nếu thực sự cần full application wiring, DB hay infrastructure.

Ví dụ runnable phía dưới dùng `@Import(BookCatalog.class)`: service lưu in-memory và chạy logic thật, không phụ thuộc database/mocking. Điều này cũng giúp mutation có side effect quan sát được.

## 4. Biến `variable` và `variables`: hợp đồng kiểu dữ liệu

Một GraphQL operation có thể khai báo nhiều biến:

~~~graphql
mutation AddBook($input: BookInput!) {
  addBook(input: $input) {
    id
    title
    pages
  }
}
~~~

Ở đây:

- `$input` là **variable** được đặt tên trong document.
- `BookInput` là **input object type** trong GraphQL schema, không phải một type Java được client quyết định tự do.
- Dấu `!` nghĩa **non-null**. Nếu thiếu biến required hoặc truyền null, GraphQL validation/variable coercion có thể từ chối request **trước khi resolver chạy**.
- Các field của `BookInput` cũng có thể đánh dấu `String!`, `Int!` để buộc giá trị hợp lệ về kiểu/non-null.
- GraphQL `Int` thường là số nguyên có dấu 32-bit; Java service cần chọn kiểu và giới hạn phù hợp.

Trong Java test:

~~~java
Map<String, Object> input = Map.of(
        "title", "GraphQL Testing",
        "pages", 180);

graphQlTester.documentName("addBook")
        .variable("input", input)
        .execute()
        .path("addBook.title")
        .entity(String.class)
        .isEqualTo("GraphQL Testing");
~~~

Đây là snippet dựa trên document file `addBook.graphql` ở mục 7. `GraphQlTester` tạo GraphQL request đúng structure khi truyền `Map` làm input object, không cần tự nối JSON bằng String concatenation.

### Truyền nhiều biến

~~~java
graphQlTester.document("""
        query Search($prefix: String!, $limit: Int!) {
          searchBooks(prefix: $prefix, limit: $limit) {
            id
          }
        }
        """)
        .variables(Map.of("prefix", "Sp", "limit", 5))
        .execute();
~~~

Snippet **chỉ minh họa cú pháp** của `variables(Map)`; project runnable không định nghĩa field `searchBooks`. Trong Spring for GraphQL 1.3.x, `variables(Map)` là API dùng để thêm nhiều biến cùng lúc; nếu dùng một API cũ hơn, kiểm Javadoc theo phiên bản.

### `null` khác với biến không được gửi

GraphQL phân biệt ba trường hợp:

1. Biến **không được cung cấp** trong `variables`.
2. Biến được cung cấp với **null**.
3. Biến được cung cấp với giá trị thực.

Với `ID!` hoặc `BookInput!`, hai trường hợp 1 và 2 đều không hợp lệ nếu không có default phù hợp. Với argument nullable, semantics có thể khác nhau: một input field được bỏ qua có thể là lệnh “không thay đổi”, trong khi field đặt null có thể là lệnh “xóa giá trị”.

Java `Map.of(...)` **không chấp nhận null**; nếu cần gửi null:

~~~java
graphQlTester.document("""
        query Optional($id: ID) {
          maybeBook(id: $id) { id }
        }
        """)
        .variable("id", null)
        .execute();
~~~

Đây là snippet minh họa; field `maybeBook` không tồn tại trong project ở mục 7. `variable("id", null)` giúp biểu diễn GraphQL null một cách tường minh. Test đúng cần kiểm cả schema và hợp đồng resolver đối với null/absent, thay vì chỉ thử một trường hợp.

### Tránh nối biến trực tiếp vào GraphQL document

Mẫu yếu:

~~~java
String query =
        "{ book(id: \"" + userSuppliedId + "\") { title } }";
~~~

Nếu ID chứa dấu quote, ký tự đặc biệt hoặc nội dung do user kiểm soát, document có thể hỏng cú pháp hoặc làm thay đổi cấu trúc truy vấn. **Truyền dữ liệu bằng `variable`** giúp tách query document khỏi input, dễ tái sử dụng, kiểm kiểu và bảo trì hơn. Đây là nguyên tắc thiết kế an toàn, dù vẫn cần kiểm quyền, phân trang và giới hạn độ phức tạp query ở server.

## 5. Kiểm `data` bằng `path`, `entity`, `entityList`

### 5.1. Field scalar

~~~java
graphQlTester.document("{ book(id: \"b1\") { title } }")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

`path("book.title")` nhìn vào `data.book.title`. Khi có lỗi GraphQL chưa được xử lý, việc truy cập path thông thường dẫn đến assertion failure thay vì lặng lẽ coi response là thành công.

### 5.2. Nested object và nhiều trường

Nếu document chọn:

~~~graphql
query {
  book(id: "b1") {
    id
    title
    pages
  }
}
~~~

Bạn có thể kiểm các path:

~~~java
var response = graphQlTester.document("""
        { book(id: "b1") { id title pages } }
        """)
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("b1");

response.path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");

response.path("book.pages")
        .entity(Integer.class)
        .isEqualTo(300);
~~~

`response` là `GraphQlTester.Response` và có thể điều hướng nhiều path từ một kết quả thực thi. Đây là một cách giảm việc chạy cùng query ba lần.

### 5.3. Danh sách kết quả

Với schema `books: [Book!]!`, document:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

Test:

~~~java
graphQlTester.document("""
        { books { id title } }
        """)
        .execute()
        .path("books[*].title")
        .entityList(String.class)
        .containsExactly("Java 17", "Spring Boot");
~~~

`containsExactly` kiểm **nội dung và thứ tự** trong API danh sách tương ứng. Nếu schema/backend không cam kết thứ tự, không viết assertion dựa vào thứ tự ngẫu nhiên của database. Thay vào đó, thêm argument sort chính thức hoặc kiểm tập giá trị theo cách không phụ thuộc thứ tự.

`hasSize(2)` chỉ kiểm số phần tử; `containsExactly` mạnh hơn khi biết toàn bộ expected. `contains(...)` chỉ cần chứa những giá trị đã chỉ định, không nhất thiết chứng minh danh sách không có phần tử dư.

### 5.4. Field null, vắng mặt và empty list

Giả sử `book(id: "missing")` trả `null`, không báo lỗi:

~~~java
graphQlTester.document("""
        { book(id: "missing") { id title } }
        """)
        .execute()
        .path("book")
        .valueIsNull();
~~~

`valueIsNull()` kiểm GraphQL response có **giá trị null tại path**. Khác với:

- `pathDoesNotExist()`: path không được biểu diễn trong cây `data`, ví dụ field không được chọn trong selection set.
- `hasValue()`: có giá trị không-null hoặc list không rỗng.
- `entityList(...).hasSize(0)`: field là một list rỗng, **không phải null**.

Với GraphQL, field không có trong selection set thường **không xuất hiện trong `data`**, dù schema có định nghĩa field ấy. Do đó kiểm “vắng path” chỉ đúng khi document không chọn field đó hoặc có lý do response hợp đồng vắng, không phải cách kiểm “không tìm thấy book” nếu resolver trả null.

## 6. GraphQL errors: không đánh đồng HTTP 200 với thành công

GraphQL response có thể chứa `errors` do:

- Document sai cú pháp.
- Selection field không có trong schema.
- Thiếu required variable, kiểu biến sai, input object không hợp lệ.
- Resolver gây exception khi xử lý.
- Lỗi phân quyền trong data fetcher.
- Timeout, database không khả dụng hoặc downstream failure.

Đối với các lỗi **schema validation/variable coercion**, GraphQL engine thường từ chối operation trước resolver. Với **execution error**, có thể có **partial data** và lỗi chỉ tác động đến một nhánh field (tùy GraphQL non-null propagation).

### Mặc định GraphQlTester giúp phát hiện lỗi

Trong các assertion `path(...)` thông thường, GraphQlTester kiểm response không có GraphQL errors **chưa được chấp nhận**. Vì thế test “đúng title nhưng có errors ở field khác” có thể fail; đây thường là một điều tốt.

Đừng sửa bằng cách lọc toàn bộ errors:

~~~java
// MẪU YẾU: filter mọi lỗi, có thể che regression.
response.errors()
        .filter(error -> true)
        .verify();
~~~

Một filter không bắt buộc error phải xuất hiện và có thể che lỗi không mong đợi. Nếu test thật sự trông đợi một lỗi cụ thể, dùng `expect` hoặc `satisfy` với điều kiện rõ ràng.

### `errors().expect(...)` khi lỗi phải xuất hiện

~~~java
graphQlTester.document("""
        query Broken {
          book(id: "b1") { nonExistingField }
        }
        """)
        .execute()
        .errors()
        .expect(error -> error.getMessage() != null
                && !error.getMessage().isBlank())
        .verify();
~~~

Document này **cố ý sai** so với schema của demo, nên engine phải trả ít nhất một GraphQL error. Ví dụ kiểm message không rỗng để không phụ thuộc nguyên văn wording của GraphQL Java; trong hệ thống thật hãy kiểm loại/code/location/path ổn định khi đó là contract. `expect` khác `filter`: nếu không có error thỏa điều kiện, test **fail**.

### `errors().satisfy(...)` để duyệt danh sách lỗi

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
          book(id: $id) { id }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertFalse(errors.isEmpty());
            errors.forEach(error ->
                    assertFalse(error.getMessage().isBlank()));
        });
~~~

Đoạn này nằm trong JUnit method với static import `assertFalse`. Vì không gửi biến `id` bắt buộc, GraphQL variable coercion phải báo lỗi. `satisfy` cho phép kiểm toàn bộ errors; khi sử dụng, hãy thực sự có assertion để không biến nó thành lệnh bỏ qua lỗi.

### `errors().filter(...)` khi cho phép một loại lỗi đã biết

Ví dụ response có một lỗi **được phép** trên field phụ, nhưng test vẫn muốn kiểm phần `data` khác:

~~~java
graphQlTester.document(document)
        .execute()
        .errors()
        .filter(error -> error.getMessage()
                .contains("KNOWN_OPTIONAL_FIELD"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

Đây là snippet **minh họa pattern**, cần `document` hợp lệ và resolver tạo đúng lỗi. Không có field `KNOWN_OPTIONAL_FIELD` trong demo. Chỉ dùng filter khi yêu cầu nghiệp vụ thực sự cho phép partial data và bạn biết rõ lỗi nào được chấp nhận. Global `errorFilter` trong tester builder có tác dụng rộng hơn nữa, nên rất dễ làm mất coverage nếu dùng thiếu kiểm soát.

### HTTP status và GraphQL errors khác hai tầng

- **HTTP transport:** request có đến được GraphQL endpoint? Body Content-Type, auth, timeout, proxy và status là gì?
- **GraphQL request:** document có hợp schema, biến có kiểu đúng, operation có được phép không?
- **GraphQL execution:** data fetcher có trả dữ liệu đúng, lỗi nghiệp vụ được mapping ra sao?

Tùy phiên bản GraphQL-over-HTTP/protocol response và lỗi, HTTP có thể dùng status 200 hoặc status 4xx. **Không hardcode quy tắc “mọi GraphQL error luôn HTTP 200”.** Khi test GraphQlTester nội bộ, ta tập trung vào `data/errors`; khi cần kiểm HTTP status/headers theo deployment, thêm HTTP integration test phù hợp.

## 7. Project đầy đủ Java 17/Spring Boot 3.3.5

Ví dụ chạy không cần database hay Docker. Một `BookCatalog` lưu book trong memory, expose GraphQL operations:

- `Query.book(id: ID!): Book` trả một book hoặc null khi không tìm thấy.
- `Query.books: [Book!]!` trả danh sách book theo ID.
- `Mutation.addBook(input: BookInput!): Book!` thêm book và trả book vừa tạo.
- `BookInput` có `title: String!` và `pages: Int!`.

Test dùng biến scalar, input object `Map`, document file, mutation và query đối chiếu side effect. Với mutable state, test reset fixture trước/sau mỗi method và **không bật parallel methods trên cùng context** nếu không bổ sung isolation.

### 7.1. Cấu trúc project

~~~text
graphql-tester-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/graphql/
    │   │   ├── GraphQlApplication.java
    │   │   ├── BookCatalog.java
    │   │   └── BookGraphQlController.java
    │   └── resources/graphql/
    │       └── schema.graphqls
    └── test/
        ├── java/com/example/graphql/
        │   ├── BookGraphQlSliceTest.java
        │   └── BookGraphQlHttpTest.java
        └── resources/graphql-test/
            ├── bookById.graphql
            └── addBook.graphql
~~~

Dùng đúng tên package, file và resource path. Gradle Wrapper scripts và JAR nhị phân được tạo bằng Gradle hoặc lấy từ repo; ví dụ không bao gồm nội dung nhị phân của `gradle-wrapper.jar`.

**`settings.gradle`**:

~~~groovy
rootProject.name = 'graphql-tester-demo'
~~~

**`build.gradle`** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'

    // HTTP GraphQlTester dùng WebTestClient.
    // Ở demo này app vẫn dùng Servlet MVC do có starter-web.
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:

- `spring-boot-starter-graphql` cung cấp GraphQL server integration.
- `spring-boot-starter-web` cung cấp Spring MVC/Servlet HTTP transport cho endpoint GraphQL. **Starter GraphQL không tự khiến mọi app có HTTP server** nếu thiếu web transport.
- `spring-graphql-test` cung cấp `GraphQlTester`, test variants và APIs.
- `spring-boot-starter-test` cung cấp JUnit Jupiter/Spring TestContext.
- `spring-boot-starter-webflux` ở **testImplementation** cung cấp WebTestClient cho `HttpGraphQlTester`; production app vẫn là Servlet MVC trong cấu hình kết hợp này.
- `useJUnitPlatform()` giúp Gradle phát hiện và chạy `@Test`.
- Hệ thống dependency management của Boot 3.3.5 giữ Spring GraphQL/GraphQL Java tương thích, không tự chèn version độc lập gây lệch API.

Nếu dự án đã là WebFlux application, dependency webflux có thể ở `implementation` và không cần thêm một lần trong test. Trong dự án Boot phiên bản khác, phải xem **đúng tài liệu và package API**; Boot 3.3 dùng `@MockBean` trong test nếu cần mock, còn các dòng mới có cơ chế `@MockitoBean`.

### 7.2. GraphQL schema là hợp đồng nguồn

**`src/main/resources/graphql/schema.graphqls`**:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  addBook(input: BookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  pages: Int!
}

input BookInput {
  title: String!
  pages: Int!
}
~~~

Giải thích:

- Root `Query` có `book` và `books`.
- `book` nullable: khi không tìm thấy trả GraphQL null, không nhất thiết báo lỗi.
- `books` là list không-null của các `Book` không-null. List rỗng `[]` hợp lệ.
- Root `Mutation` có `addBook`.
- `input BookInput` **khác** `type Book`: input type dùng làm argument, output type dùng trong selection set.
- `ID` là scalar GraphQL chuyên định danh; ở Java demo xử lý bằng `String`.
- `Int` là scalar nguyên signed 32-bit; Java `int` phù hợp với demo, không phải arbitrary precision.

Spring Boot 3.3 tự tìm schema dưới classpath `graphql/**` theo cấu hình thông dụng. Nếu bạn đặt schema ở thư mục khác, cần cấu hình `spring.graphql.schema.locations` tương ứng.

### 7.3. Spring Boot main class

**`src/main/java/com/example/graphql/GraphQlApplication.java`**:

~~~java
package com.example.graphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlApplication {

    public static void main(String[] args) {
        SpringApplication.run(GraphQlApplication.class, args);
    }
}
~~~

Đặt main class cùng package cha để Boot component scan tìm `BookCatalog` và `BookGraphQlController`.

### 7.4. Service in-memory với fixture xác định

**`src/main/java/com/example/graphql/BookCatalog.java`**:

~~~java
package com.example.graphql;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {

    private final Map<String, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicInteger sequence =
            new AtomicInteger(2);

    public BookCatalog() {
        reset();
    }

    // Fixture cho demo/test; production nên dùng repository
    // hoặc cơ chế quản lý trạng thái phù hợp.
    public synchronized void reset() {
        books.clear();

        books.put("b1", new Book("b1", "Java 17", 300));
        books.put("b2", new Book("b2", "Spring Boot", 250));

        sequence.set(2);
    }

    public Book findById(String id) {
        return books.get(id);
    }

    public List<Book> findAll() {
        List<Book> result = new ArrayList<>(books.values());
        result.sort(Comparator.comparing(Book::getId));
        return List.copyOf(result);
    }

    public Book addBook(BookInput input) {
        if (input == null
                || input.title() == null
                || input.title().isBlank()
                || input.pages() <= 0) {
            throw new IllegalArgumentException(
                    "invalid book input");
        }

        String id = "b" + sequence.incrementAndGet();

        Book book = new Book(
                id, input.title(), input.pages());

        books.put(id, book);
        return book;
    }

    public record BookInput(String title, int pages) {
    }

    public static final class Book {

        private final String id;
        private final String title;
        private final int pages;

        public Book(String id, String title, int pages) {
            this.id = id;
            this.title = title;
            this.pages = pages;
        }

        public String getId() {
            return id;
        }

        public String getTitle() {
            return title;
        }

        public int getPages() {
            return pages;
        }
    }
}
~~~

**Những điểm có mục đích kiểm thử:**

- `reset()` tạo đúng hai book gốc `b1` và `b2`, nên expected được xác định trước.
- `findAll()` sắp xếp theo ID để test list không phụ thuộc iteration order của `ConcurrentHashMap`.
- `addBook` sinh ID theo sequence; mutation tạo **thay đổi trong state thật**, không chỉ trả một DTO giả.
- `BookInput` là Java record; Spring GraphQL argument binder chuyển input object GraphQL vào record này.
- `Book` dùng getter JavaBean `getId`, `getTitle`, `getPages` để GraphQL data fetcher lấy các field tương ứng.
- Vì service là singleton mutable, các bài test gọi `reset` ở lifecycle hook. **Không chạy song song các test cùng sửa service** nếu chưa tách context/state.

Bộ dữ liệu in-memory được dùng để tập trung vào GraphQL. Nó không chứng minh transaction, JPA, database commit hoặc concurrent mutation consistency của một hệ thống production.

### 7.5. GraphQL controller với `@QueryMapping` và `@MutationMapping`

**`src/main/java/com/example/graphql/BookGraphQlController.java`**:

~~~java
package com.example.graphql;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import com.example.graphql.BookCatalog.Book;
import com.example.graphql.BookCatalog.BookInput;

@Controller
public class BookGraphQlController {

    private final BookCatalog catalog;

    public BookGraphQlController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return catalog.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return catalog.findAll();
    }

    @MutationMapping
    public Book addBook(
            @Argument("input") BookInput input) {
        return catalog.addBook(input);
    }
}
~~~

Annotation này thuộc Spring GraphQL:

- `@QueryMapping` ánh xạ resolver vào field tương ứng trên root `Query` theo tên method.
- `@MutationMapping` ánh xạ resolver vào root `Mutation`.
- `@Argument("id")` lấy argument `id` đã được GraphQL Java xử lý từ document/variables.
- `@Argument("input")` lấy input object và bind vào `BookInput`.
- Đặt tên argument tường minh giúp tránh phụ thuộc metadata tên parameter khi build.

**Lưu ý:** Khi `BookCatalog.addBook` ném `IllegalArgumentException` do business rule, GraphQL execution có thể xuất hiện lỗi generic hoặc được xử lý bởi custom `DataFetcherExceptionResolver`/`@GraphQlExceptionHandler`. Demo tập trung vào **query/mutation hợp lệ** và **lỗi schema/required variables**; nó không khẳng định exception nghiệp vụ luôn được map thành một mã lỗi cố định nếu chưa cấu hình error resolver.

### 7.6. Lưu operation vào `graphql-test/`

**`src/test/resources/graphql-test/bookById.graphql`**:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
    pages
  }
}
~~~

**`src/test/resources/graphql-test/addBook.graphql`**:

~~~graphql
mutation AddBook($input: BookInput!) {
  addBook(input: $input) {
    id
    title
    pages
  }
}
~~~

Với `GraphQlTester.documentName("bookById")`, tester tìm document resource tên `bookById` với extension `.graphql` (hoặc `.gql` khi hỗ trợ) trong classpath **`graphql-test/`** mặc định. Thư mục này không phải `src/main/resources/graphql/`: thư mục main chứa **schema**, còn test resources chứa **client operations**.

Ưu điểm của document file:

- Có thể dùng syntax highlighting/validation trong IDE.
- Dễ tái sử dụng cùng query qua nhiều test.
- Tránh nối String literal dài và lặp selection set.
- Phần `variables` được thay đổi trong test mà không sửa query.

Nếu dùng nhiều operations trong cùng document, cần chọn operation bằng `operationName("...")` cho request đó. Trong ví dụ, mỗi file chỉ có một operation nên không cần gọi `operationName`.

## 8. JUnit GraphQL slice test: query, mutation và variables

**`src/test/java/com/example/graphql/BookGraphQlSliceTest.java`**:

~~~java
package com.example.graphql;

import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@GraphQlTest(BookGraphQlController.class)
@Import(BookCatalog.class)
class BookGraphQlSliceTest {

    @Autowired
    private GraphQlTester tester;

    @Autowired
    private BookCatalog catalog;

    @BeforeEach
    void setUp() {
        catalog.reset();
    }

    @AfterEach
    void cleanUp() {
        catalog.reset();
    }

    @Test
    void queryUsesNamedDocumentAndIdVariable() {
        tester.documentName("bookById")
                .variable("id", "b1")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Java 17");
    }

    @Test
    void queryChecksMultipleSelectedFields() {
        var response = tester.document("""
                query GetBook($id: ID!) {
                  book(id: $id) {
                    id
                    title
                    pages
                  }
                }
                """)
                .variable("id", "b2")
                .execute();

        response.path("book.id")
                .entity(String.class).isEqualTo("b2");

        response.path("book.title")
                .entity(String.class).isEqualTo("Spring Boot");

        response.path("book.pages")
                .entity(Integer.class).isEqualTo(250);
    }

    @Test
    void queryMissingBookReturnsNullNotError() {
        tester.documentName("bookById")
                .variable("id", "missing")
                .execute()
                .path("book")
                .valueIsNull();
    }

    @Test
    void queryListChecksValuesAndOrdering() {
        tester.document("""
                query AllBooks {
                  books { id title }
                }
                """)
                .execute()
                .path("books[*].title")
                .entityList(String.class)
                .containsExactly("Java 17", "Spring Boot");
    }

    @Test
    void queryCanUseVariablesMap() {
        tester.documentName("bookById")
                .variables(Map.of("id", "b1"))
                .execute()
                .path("book.pages")
                .entity(Integer.class)
                .isEqualTo(300);
    }

    @Test
    void mutationAcceptsInputObjectVariable() {
        tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "GraphQL Testing",
                        "pages", 180))
                .execute()
                .path("addBook.title")
                .entity(String.class)
                .isEqualTo("GraphQL Testing");
    }

    @Test
    void mutationChangesStateVisibleToNextQuery() {
        String id = tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "JUnit Jupiter",
                        "pages", 210))
                .execute()
                .path("addBook.id")
                .entity(String.class)
                .get();

        assertNotNull(id);
        assertTrue(id.startsWith("b"));

        tester.documentName("bookById")
                .variable("id", id)
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("JUnit Jupiter");
    }

    @Test
    void mutationResultHasAllExpectedFields() {
        var response = tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "Spring GraphQL",
                        "pages", 150))
                .execute();

        response.path("addBook.id")
                .entity(String.class).isEqualTo("b3");

        response.path("addBook.title")
                .entity(String.class).isEqualTo("Spring GraphQL");

        response.path("addBook.pages")
                .entity(Integer.class).isEqualTo(150);
    }

    @Test
    void missingRequiredQueryVariableProducesErrors() {
        tester.document("""
                query FindBook($id: ID!) {
                  book(id: $id) { id }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> {
                    assertFalse(errors.isEmpty());
                    errors.forEach(error ->
                            assertNotNull(error.getMessage()));
                });
    }

    @Test
    void missingRequiredMutationVariableProducesErrors() {
        tester.documentName("addBook")
                .execute()
                .errors()
                .satisfy(errors ->
                        assertFalse(errors.isEmpty()));
    }

    @Test
    void invalidSelectionIsCaughtByGraphQlValidation() {
        tester.document("""
                query Broken {
                  book(id: "b1") {
                    fieldThatDoesNotExist
                  }
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getMessage() != null
                                && !error.getMessage().isBlank())
                .verify();
    }
}
~~~

### Đọc các assertions trong test slice

Lớp này có **11 method `@Test`**, mỗi method thực thi một kịch bản.

| Method | Mục tiêu |
| --- | --- |
| `queryUsesNamedDocumentAndIdVariable` | Tải `bookById.graphql` và truyền `id` |
| `queryChecksMultipleSelectedFields` | Kiểm ba field từ **một lần execute** |
| `queryMissingBookReturnsNullNotError` | Phân biệt nullable Book với lỗi GraphQL |
| `queryListChecksValuesAndOrdering` | Kiểm list và thứ tự đã được service quy định |
| `queryCanUseVariablesMap` | API `variables(Map)` cho request |
| `mutationAcceptsInputObjectVariable` | Bind Map vào GraphQL `BookInput!` |
| `mutationChangesStateVisibleToNextQuery` | Mutation có side effect thật, query sau nhìn thấy |
| `mutationResultHasAllExpectedFields` | Kiểm đủ ID, title, pages của response mutation |
| `missingRequiredQueryVariableProducesErrors` | Non-null `ID!` không được cung cấp |
| `missingRequiredMutationVariableProducesErrors` | Non-null `BookInput!` không được cung cấp |
| `invalidSelectionIsCaughtByGraphQlValidation` | Field không thuộc schema bị GraphQL validation từ chối |

**Tại sao test được gọi là slice?** `@GraphQlTest` nạp cơ sở hạ tầng GraphQL và controller chỉ định, không mở HTTP server. `@Import(BookCatalog.class)` thêm service thật vào slice. Ta kiểm được schema, argument binding, query/mutation resolver và GraphQL response shape. Nhưng test này chưa chứng minh network endpoint `POST /graphql` hoạt động hoặc security filter cho request HTTP.

### Vì sao reset trước và sau mỗi test?

`BookCatalog` giữ dữ liệu trong singleton bean. Test mutation thêm `b3` vào map; nếu không reset, test sau mong chỉ có `b1`, `b2` có thể fail tùy thứ tự. `@BeforeEach` thiết lập fixture, `@AfterEach` dọn trạng thái ngay cả khi assertion ném exception thông thường. Với dự án thật, state có thể ở DB, cache, queue hoặc external service; phải dùng cleanup tương ứng.

**Không bật test parallel execution trên cùng context mutable** khi không có isolation: `reset()` của test A có thể xóa dữ liệu test B đang kiểm. Để chạy song song, hãy dùng per-test catalog/context, test run IDs, database/schema riêng hoặc fixture được thiết kế cho concurrency.

## 9. HTTP integration: `HttpGraphQlTester` qua server thật

Để kiểm đường HTTP, thêm class riêng. Trong Spring Boot 3.3, khi `@SpringBootTest(webEnvironment = RANDOM_PORT)` bật server và có dependencies thích hợp, Boot cấu hình `HttpGraphQlTester` cho live server. Với demo dùng Spring MVC + test-scope WebFlux client, tester sẽ gửi request GraphQL qua HTTP.

**`src/test/java/com/example/graphql/BookGraphQlHttpTest.java`**:

~~~java
package com.example.graphql;

import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        classes = GraphQlApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookGraphQlHttpTest {

    @Autowired
    private HttpGraphQlTester tester;

    @Autowired
    private BookCatalog catalog;

    @BeforeEach
    void setUp() {
        catalog.reset();
    }

    @AfterEach
    void cleanUp() {
        catalog.reset();
    }

    @Test
    void queryRunsOverRealHttpTransport() {
        tester.documentName("bookById")
                .variable("id", "b1")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Java 17");
    }

    @Test
    void mutationRunsOverHttpAndUpdatesState() {
        String id = tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "HTTP GraphQL",
                        "pages", 190))
                .execute()
                .path("addBook.id")
                .entity(String.class)
                .get();

        assertNotNull(id);

        tester.documentName("bookById")
                .variable("id", id)
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("HTTP GraphQL");
    }

    @Test
    void listQueryWorksOverHttp() {
        tester.document("{ books { title } }")
                .execute()
                .path("books[*].title")
                .entityList(String.class)
                .hasSize(2);
    }
}
~~~

Đây là **3 method `@Test`**. `HttpGraphQlTester` giữ cú pháp `document/variable/execute/path` giống test slice, nhưng có thêm HTTP transport. Nó kiểm được endpoint Spring Boot đã lắng nghe và nhận GraphQL requests, JSON serialization/deserialization, routing theo cấu hình hiện tại.

### Những giới hạn của test HTTP này

- Không có Spring Security dependency, nên chưa kiểm authorization/authentication.
- Không có DB/transaction, nên chỉ kiểm in-memory mutation và state trên cùng app instance.
- Không có proxy/API gateway/CDN, nên chưa kiểm cấu hình production network.
- Không có subscriptions; bài đang tập trung query, mutation, variables.
- Không có load/concurrency test hoặc query complexity limit.
- Không assert status/headers tùy biến qua API thấp vì mục tiêu chính là GraphQL semantics. Với auth, cookies, correlation ID hoặc HTTP response headers, cần dùng transport client phù hợp và assertions ở tầng HTTP.
- Không có API DELETE, nên cleanup mutation in-memory dùng `catalog.reset()`; với DB đã commit, không thể giả định rollback của test thread sẽ xóa dữ liệu từ server.

Để sửa headers theo từng tester, `HttpGraphQlTester` có thể mutate WebTestClient config. Khi app có authentication, nên tạo tester chuyên biệt với credentials test rõ ràng và chỉ kiểm trường hợp hợp lệ/không hợp lệ trong đúng môi trường.

## 10. Chạy Gradle và đọc kết quả

Từ root directory chứa `gradlew`/`gradlew.bat`:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chỉ chạy GraphQL slice:

~~~bash
./gradlew test --tests 'com.example.graphql.BookGraphQlSliceTest'
~~~

Chỉ chạy HTTP integration:

~~~bash
./gradlew test --tests 'com.example.graphql.BookGraphQlHttpTest'
~~~

Với hai class như trên, có **11 + 3 = 14 method `@Test`**, mỗi method một invocation. Khi dùng đúng phiên bản/dependencies/schema và code demo, kỳ vọng **14 test pass**. Đây là kết quả **dự kiến từ source**, không phải một bản ghi chạy test thực tế trong repository người học.

Gradle/JUnit report thông thường ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.graphql.BookGraphQlSliceTest.xml
    └── TEST-com.example.graphql.BookGraphQlHttpTest.xml
~~~

Các test không gọi `System.out.println`, vì vậy **không có stdout nghiệp vụ cố định**. Gradle có thể báo `BUILD SUCCESSFUL` khi tất cả task thành công; chạy lại có thể nhận `UP-TO-DATE` hoặc `FROM-CACHE`. Khi cần buộc thực thi lại để chẩn đoán:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu project mới chưa có Wrapper, cần một Gradle tương thích để bootstrap, ví dụ:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó giữ scripts/Wrapper JAR và `gradle-wrapper.properties` trong repository. Dự án thực nên dùng Gradle Wrapper mà team đang quy định, không đổi phiên bản tùy tiện theo bài học. Java toolchain yêu cầu JDK 17 có sẵn hoặc cơ chế provision phù hợp.

### Gọi thử bằng curl để hiểu HTTP payload

Khi chạy app bằng `./gradlew bootRun` trong một máy local có port 8080 chưa bị chiếm (hoặc chỉnh `server.port` khác), query:

~~~bash
curl -i http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query FindBook($id: ID!) { book(id: $id) { id title } }","variables":{"id":"b1"}}'
~~~

Đây là lệnh minh họa cho shell Linux/macOS. Với Windows PowerShell, cú pháp escape/quote khác; có thể gửi tương đương qua Postman hoặc client code. Dự án thật không nên phụ thuộc cổng 8080 trong integration tests: `HttpGraphQlTester` từ `RANDOM_PORT` được cấu hình theo cổng runtime, tránh conflict.

Mutation qua HTTP raw JSON:

~~~bash
curl -i http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"mutation Add($input: BookInput!) { addBook(input: $input) { id title pages } }","variables":{"input":{"title":"HTTP Book","pages":120}}}'
~~~

Nếu mutation thành công, response có `data.addBook` tương ứng. Ví dụ in-memory demo sinh ID `b3` cho mutation đầu tiên sau reset/service khởi tạo. Nhưng nếu đã tạo book trước đó bằng curl, ID tiếp theo **không cố định**; test không nên hardcode ID trên một server có state tồn tại lâu.

## 11. Phân biệt biến GraphQL với argument trong resolver

Document:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    title
  }
}
~~~

Có hai ký hiệu `id`:

- `$id` là **GraphQL variable** được client gửi qua `variables`.
- `book(id: ...)` là **GraphQL field argument** được định nghĩa trong schema.
- `@Argument("id")` là cách Spring GraphQL đưa giá trị field argument vào tham số Java.
- `BookCatalog.findById(id)` là logic ứng dụng.

Đường dữ liệu:

~~~text
Java test .variable("id", "b1")
       |
       v
GraphQL request variables: {"id":"b1"}
       |
       v
GraphQL variable coercion theo ID!
       |
       v
Schema field Query.book(id: ID!)
       |
       v
@QueryMapping book(@Argument("id") String id)
       |
       v
BookCatalog.findById("b1")
       |
       v
GraphQL data.book.title
       |
       v
GraphQlTester.path("book.title").entity(String.class)
~~~

Nếu tên variable khác tên argument, không có vấn đề miễn document mapping đúng:

~~~graphql
query Lookup($requestedId: ID!) {
  book(id: $requestedId) {
    title
  }
}
~~~

Khi đó test truyền `variable("requestedId", "b1")`, còn resolver vẫn có `@Argument("id")`. Đừng sửa annotation Java theo **tên variable của client**; annotation Java tương ứng với **schema field argument**.

## 12. Mutation: kiểm side effect, không chỉ response

Một mutation có thể trả:

~~~json
{
  "data": {
    "addBook": {
      "id": "b3",
      "title": "HTTP GraphQL",
      "pages": 190
    }
  }
}
~~~

Nhưng nếu controller chỉ dựng DTO rồi **không lưu**, test chỉ kiểm `addBook.title` vẫn có thể pass. Với mutation thay đổi trạng thái, viết:

1. Thực thi mutation với biến input hợp lệ.
2. Assert response ID/field/validation theo contract.
3. Dùng **query mới** hoặc repository read trong transaction khác để kiểm side effect.
4. Cleanup dữ liệu tạo ra sau test, không phụ thuộc test khác.
5. Nếu mutation async, dùng bounded polling theo trạng thái eventual, không sleep tùy tiện.

Project demo có test `mutationChangesStateVisibleToNextQuery` và `mutationRunsOverHttpAndUpdatesState`. Cả hai đọc **query sau mutation** để kiểm trạng thái.

### Nếu mutation có DB transaction

`@SpringBootTest(RANDOM_PORT)` gửi HTTP thực từ test thread sang server thread. Nếu mutation ghi database bằng `@Transactional` trên service, transaction phía server có thể **commit riêng** trước khi response trả về. `@Transactional` ở JUnit test không tự rollback commit phía server. Phải cleanup bằng ID/test marker trong transaction độc lập, API DELETE hoặc DB/schema/container cô lập. **Không lấy reset in-memory của demo để áp dụng trực tiếp cho PostgreSQL production.**

### Có thể mutation trả partial data và errors?

Có. Một mutation có thể chạm nhiều resolver/fields, và lỗi ở một field sau mutation không nhất thiết rollback toàn bộ những gì đã ghi. GraphQL response contract **không tự đồng nhất với transaction semantics**. Test cần quy định idempotency, atomicity, compensation và cách phục hồi phù hợp domain, đặc biệt khi mutation gửi message hoặc gọi external services.

## 13. Field `null` và GraphQL non-null propagation

Dấu `!` trong GraphQL schema áp dụng cả argument và output:

~~~graphql
type Book {
  id: ID!
  title: String!
  pages: Int!
}
~~~

Nếu một resolver trả `null` cho `Book.title` dù schema ghi `String!`, GraphQL execution coi đó là lỗi non-null. Theo quy tắc propagation, null có thể lan tới parent field, thậm chí lên `data` tùy chuỗi non-null của schema.

Điều này khác với `book(id: ID!): Book` (nullable): **không tìm thấy book** có thể trả `book: null` **mà không có error**, đúng như demo.

| Tình huống | Expected nên kiểm |
| --- | --- |
| ID hợp lệ và book tồn tại | `path("book.title").entity(String.class).isEqualTo(...)` |
| ID hợp lệ nhưng không tồn tại | `path("book").valueIsNull()` nếu schema/contract cho phép |
| ID! bị thiếu | `errors()` không rỗng, không expect resolver thành công |
| Selection field không tồn tại | GraphQL validation error |
| Output non-null field trả null | GraphQL execution error và null propagation |
| Document không chọn field `pages` | `pages` không có trong data selection; không suy luận pages trong DB null |

Test tốt không cố so sánh nguyên body JSON khi schema cho phép field selection khác nhau. Hãy kiểm đúng phần của response mà client yêu cầu.

## 14. Query document và fragment có ích trong bộ test lớn

Khi các test dùng lặp nhiều field, fragment giúp giữ selection set nhất quán:

~~~graphql
fragment BookFields on Book {
  id
  title
  pages
}
~~~

Document dùng fragment:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    ...BookFields
  }
}
~~~

Nếu fragment được lưu trong một file riêng dưới `graphql-test/`, Spring GraphQlTester hỗ trợ API như `fragmentName("bookFields")` để ghép fragment khi thực thi theo cấu hình document source. Ví dụ minh họa:

~~~java
tester.documentName("bookByIdWithFragment")
        .fragmentName("bookFields")
        .variable("id", "b1")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

**Đây là snippet mở rộng**, không thuộc project runnable vì chưa tạo hai resource `bookByIdWithFragment.graphql` và `bookFields.graphql`. GraphQL operation phải hợp lệ sau khi fragment được ghép; nếu fragment có tên trùng hoặc type condition sai, GraphQL validation sẽ báo lỗi.

Khi một document chứa **nhiều operation**, ví dụ một query và một mutation cùng file, client cần chọn operation phù hợp bằng `operationName`. Trong project demo, mỗi document chỉ có một operation nên không cần đặt operationName. Với test cases sử dụng chung tên operation khác nhau, đặt operationName rõ ràng giúp người review biết call đang thực thi nhánh nào.

## 15. Authentication, HTTP headers và GraphQlTester

GraphQL path assertions không kiểm thay cho authentication/authorization. Có ba mức dễ nhầm:

- `@GraphQlTest`: kiểm resolver/schema server-side, có thể không đi qua HTTP security filters.
- `HttpGraphQlTester` qua mock web environment: có thể kiểm một phần web stack theo context được cấu hình.
- `HttpGraphQlTester` qua real HTTP server: kiểm route + filters/headers/auth trong môi trường đó, nhưng chưa chắc có proxy/gateway production.

Với Boot 3.3, có thể tạo tester biến thể từ `HttpGraphQlTester.mutate()` để cấu hình WebTestClient headers, ví dụ:

~~~java
HttpGraphQlTester authenticated = tester.mutate()
        .webTestClient(builder ->
                builder.defaultHeaders(headers ->
                        headers.setBearerAuth("test-token")))
        .build();

authenticated.document("{ books { id } }")
        .execute()
        .path("books[*].id")
        .entityList(String.class)
        .hasSize(2);
~~~

Đây là **snippet minh họa** cho môi trường đã cấu hình security và có token test hợp lệ; project runnable không sử dụng Spring Security, và `test-token` không đại diện cho credential thật. Không hardcode token production trong test. Nếu cần verify 401/403/CSRF/CORS, test trực tiếp ở HTTP level hoặc dùng security fixtures tương ứng.

Một `DataFetcherExceptionResolver` có thể ánh xạ lỗi quyền truy cập thành GraphQL `errors` thay vì HTTP 403; cần định nghĩa contract rõ ràng giữa API transport và GraphQL payload. Không mong mọi lỗi phân quyền luôn dùng cùng HTTP status trên mọi transport.

## 16. Độ ổn định và isolation khi chạy mutation tests

Một `GraphQlTester` instance không nhất thiết tạo một application context mới cho từng request. Các test lớp `@GraphQlTest` có thể chia sẻ Spring context cache; `@SpringBootTest` HTTP có thể chia sẻ một application context khác. Nếu service giữ state mutable, mutation của một test có thể ảnh hưởng query trong test sau.

### Mẫu isolation trong demo

~~~java
@BeforeEach
void setUp() {
    catalog.reset();
}

@AfterEach
void cleanUp() {
    catalog.reset();
}
~~~

Mục tiêu: mỗi method bắt đầu với `b1`/`b2` và không để `b3` ảnh hưởng method kế tiếp. Tuy nhiên, cách này chỉ phù hợp với **test không chạy parallel trên cùng singleton mutable**. Với parallel execution:

- Dùng catalog instance riêng cho test hoặc context isolation thích hợp;
- Dùng namespace/testRunId riêng để phân tách state;
- Dùng DB/schema riêng cho từng job/test class;
- Hoặc tổ chức tests thay đổi state không chạy đồng thời.

### Không nên dùng `@DirtiesContext` cho mọi mutation

`@DirtiesContext` loại context khỏi Spring TestContext cache, khiến context phải khởi tạo lại. Nó có thể cần trong một số tình huống state bean không reset được, nhưng **không rollback server-side DB commits** hay xóa mọi side effect ngoài JVM. Với demo in-memory, reset fixture là đủ và nhanh hơn. Với storage thật, áp dụng cleanup tương ứng.

### Đừng dùng `deleteAll()` trên DB chia sẻ

Nếu sau này thay `BookCatalog` bằng JPA repository, một cleanup kiểu `repository.deleteAll()` có thể xóa dữ liệu test khác hoặc dữ liệu không thuộc mình. Hãy tạo book với test marker, theo dõi ID và xóa đúng dữ liệu đã tạo; trong môi trường quan trọng, cấp schema/container riêng. Nếu mutation có outbox message, cache hay file upload, cleanup phải xem cả các side effects đó.

## 17. Những lỗi hay gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: GraphQlTester` | Thiếu `spring-graphql-test` hoặc test context không auto-config tester | Thêm đúng test dependency, dùng `@GraphQlTest` hoặc cấu hình tester rõ ràng |
| `Failed to load ApplicationContext` trong `@GraphQlTest` | Resolver cần service không có trong slice | Dùng `@Import` hoặc `@MockBean` có chủ đích; kiểm root cause |
| `field undefined` trong GraphQL | Schema thiếu field hoặc selection sai | Đối chiếu `schema.graphqls` với document |
| `Variable ... was not provided` | Thiếu biến non-null hoặc tên variable sai | Truyền đúng `variable("id", value)`, phân biệt variable và argument |
| Input object không bind vào record | Tên field/type sai, schema không khớp Java | Kiểm `BookInput` fields, `@Argument("input")`, nullability |
| Query ra null mà test mong data | Không có record, sai ID hoặc resolver trả null | Kiểm fixture và data path, không coi null đồng nghĩa lỗi |
| Test chỉ kiểm HTTP 200 nhưng vẫn có lỗi | GraphQL `errors` trong response | Dùng `GraphQlTester.errors()` và assert data/error đúng contract |
| `path("data.book.title")` không tìm thấy | GraphQlTester path tương đối với `data` | Sử dụng `path("book.title")` |
| `entity(Integer.class)` khác kiểu | GraphQL scalar/JSON decoding không khớp | Chọn kiểu Java phù hợp, không ép String cho Int |
| `containsExactly` fail ngẫu nhiên | Backend list không cam kết ordering | Sort trong resolver hoặc dùng assertion không phụ thuộc thứ tự |
| Mutation test xanh nhưng DB không có data | Chỉ assert response, chưa kiểm side effect | Query/repository read mới sau mutation |
| Test sau thấy book do test trước tạo | Singleton state/cache không reset | `@BeforeEach`/`@AfterEach`, namespace hoặc isolation |
| HTTP tester kết nối sai port | Hardcode 8080 thay vì RANDOM_PORT | Dùng tester Boot auto-config hoặc base URL lấy runtime |
| `HttpGraphQlTester` không được autowire | Thiếu HTTP client test support hoặc boot context sai | Có `spring-graphql-test` và `spring-boot-starter-webflux` test scope khi dùng Boot 3.3 |
| GraphQL error message thay đổi | Test assert exact nội bộ message | Kiểm type/code/semantic phù hợp, giữ expected bền |
| 401/403 nhưng GraphQL query đúng | HTTP filter/auth chặn trước resolver | Dùng test security fixture và tester có credentials |
| Test `@GraphQlTest` xanh, HTTP API hỏng | Slice không kiểm network/filters | Thêm HTTP integration với `HttpGraphQlTester` |
| Test không có dữ liệu vì file `documentName` | File sai folder/extension/tên | Đặt dưới `src/test/resources/graphql-test/` |
| `@MockBean` API không có ở Boot mới | Mẫu code khác major version | Dùng mock annotation đúng theo Boot/Spring Framework version |
| Query độc hại/phức tạp làm server quá tải | Không giới hạn complexity/depth, resolver N+1 | Cấu hình limit, DataLoader, auth và kiểm performance |
| Mutation trả lỗi nhưng vẫn ghi data | Không có transaction/compensation hoặc lỗi sau commit | Kiểm side effect/rollback semantics thực tế |

### Chẩn đoán theo tầng

1. **Classpath:** có `spring-boot-starter-graphql`, `spring-graphql-test`, JUnit và transport client thích hợp chưa?
2. **Schema:** file `*.graphqls` đã được load? Các type/field/argument tên đúng chưa?
3. **Resolver:** `@Controller` được scan? `@QueryMapping`/`@MutationMapping` có khớp schema?
4. **Variables:** tên có dấu `$` trong document nhưng **không có `$`** trong `variable("id", ...)`; kiểu `ID!`, `Int!`, `BookInput!` có hợp lệ?
5. **Response:** xem phần `data` và `errors`, không chỉ HTTP status.
6. **Path:** `path` tương đối với `data`; list có đúng JSONPath/ordering?
7. **State:** test mutation có dữ liệu fixture và cleanup độc lập không?
8. **Transport:** slice hay real HTTP? Nếu lỗi headers/auth/port, kiểm HttpGraphQlTester và network.
9. **Root cause:** đọc stack trace/application logs đã sanitize, tránh lộ credentials và dữ liệu thật.

## 18. Phạm vi GraphQlTester so với kiểm thử SOAP

Vì chủ đề cha là **GraphQL và SOAP**, cần giữ sự phân định:

| GraphQL | SOAP |
| --- | --- |
| GraphQL schema `type Query`, `type Mutation`, `input` | WSDL, XSD và SOAP envelope |
| `GraphQlTester.document(...).variable(...)` | SOAP client/endpoint tester phù hợp với Spring Web Services |
| Response `data` và `errors` | SOAP Body/Header và Fault |
| Selection set, arguments, GraphQL validation | XML namespaces, SOAPAction, XSD validation |
| `@QueryMapping`, `@MutationMapping` | `@Endpoint`, `@PayloadRoot` trong Spring-WS |
| HTTP POST `/graphql` hoặc transport GraphQL khác | SOAP over HTTP hoặc transport tương ứng |

GraphQlTester **không** được thiết kế để kiểm SOAP envelope, XPath trong XML, WS-Security hoặc WSDL contract. Khi dạy bài SOAP, cần dùng SOAP-specific testing APIs và các quy tắc XML/SOAP tương ứng, tránh dùng GraphQlTester vì cả hai cùng có thể chạy trên HTTP.

## 19. Bài tập thực hành

**Bài A — biến ID bắt buộc:** Gửi `bookById.graphql` với `id=b2`, assert title `Spring Boot`. Bỏ biến `id` và assert `errors` không rỗng. Giải thích vì sao schema `ID!` từ chối request trước resolver.

**Bài B — null khác error:** Gửi `id=missing` và assert `path("book").valueIsNull()` nhưng không có GraphQL validation error. Đổi schema field `book` thành non-null thử nghiệm và phân tích tác động khi resolver trả null.

**Bài C — input object mutation:** Tạo book có `title="GraphQL Practice"`, `pages=95` bằng `variable("input", Map.of(...))`. Assert response, sau đó query bằng ID vừa tạo để xác minh state.

**Bài D — đổi tên variable:** Đổi document từ `$id` thành `$bookId`, giữ argument `book(id: $bookId)`. Sửa test dùng `variable("bookId","b1")`. Giải thích vì sao Java controller vẫn giữ `@Argument("id")`.

**Bài E — kiểm list ordering:** Cố tình đảo sorting trong `BookCatalog.findAll()` và chạy `containsExactly`. Test phải fail khi thứ tự là một phần hợp đồng. Nếu product không yêu cầu ordering, thiết kế lại test theo unordered set hoặc thêm `orderBy` trong schema.

**Bài F — chọn operation:** Tạo document có hai query tên `FindBook` và `AllBooks`. Dùng `operationName("FindBook")` để chọn đúng operation; xem điều gì xảy ra nếu không nêu operationName trong request chứa nhiều operations.

**Bài G — lỗi field:** Query một field không tồn tại, dùng `errors().expect(...)` hoặc `satisfy(...)` để assert validation error. Không bỏ qua lỗi bằng global `errorFilter(error -> true)`.

**Bài H — business error mapping:** Khi `pages=0`, service ném `IllegalArgumentException`. Bổ sung `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler` theo version, ánh xạ sang GraphQL error code hợp đồng. Test code/message ổn định, không assert nguyên văn stack trace.

**Bài I — HTTP và security:** Thêm Spring Security, yêu cầu Bearer token cho mutation, cho phép query phù hợp. Kiểm unauthorized và authorized qua HTTP tester có headers. Không dùng token production.

**Bài J — dữ liệu thật:** Thay in-memory service bằng Spring Data JPA và Testcontainers PostgreSQL. Dùng `@SpringBootTest(RANDOM_PORT)` để tạo mutation rồi GET query; cleanup bằng ID trong transaction riêng. Không giả định rollback của test thread xóa commit trên server.

## 20. Checklist trước khi merge GraphQL tests

- [ ] Tôi biết GraphQL schema và tên field/argument chính xác?
- [ ] Document có query/mutation, selection set và operationName đúng khi cần?
- [ ] Biến được truyền qua `variable`/`variables`, không nối raw user text vào document?
- [ ] Kiểu scalar (`ID!`, `String!`, `Int!`) và input object (`BookInput!`) phù hợp?
- [ ] Test query kiểm cả dữ liệu đúng, null khi không tìm thấy, list/ordering khi quan trọng?
- [ ] Test mutation kiểm **response và side effect**, không chỉ payload?
- [ ] Path GraphQlTester tương đối với `data`, không viết prefix `data.` thừa?
- [ ] Tôi phân biệt `GraphQL errors` với lỗi HTTP status/headers?
- [ ] Error tests dùng `expect`/`satisfy`, không lọc tất cả lỗi để giữ test xanh?
- [ ] Tôi đã chọn đúng `@GraphQlTest` hay `@SpringBootTest` theo mục tiêu transport?
- [ ] Dependencies gồm `spring-graphql-test` và WebTestClient support khi dùng HTTP GraphQlTester?
- [ ] Controller's service dependency đã được import/mock đúng phạm vi slice?
- [ ] Mutation tests độc lập, reset fixture hoặc cleanup DB trong transaction commit?
- [ ] Test không dựa vào state mutable chia sẻ khi chạy parallel?
- [ ] Các test không lộ token, thông tin khách hàng hoặc kết nối production?
- [ ] Khi cần kiểm SOAP, tôi không dùng nhầm GraphQlTester?
- [ ] Report Gradle/JUnit xác nhận các method test đã thực sự chạy?

## 21. Tài liệu tham khảo chính thức

Tài liệu tham khảo cho **Spring Boot 3.3.x / Spring for GraphQL 1.3.x** trong ví dụ. Các dòng Boot/Spring GraphQL mới có thể thay packages, default test infrastructure và mock annotations; luôn đối chiếu Javadoc/version đang chạy.

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@GraphQlTest`, test slice, `ExecutionGraphQlServiceTester` và `HttpGraphQlTester`.
- [Spring for GraphQL — Testing Reference](https://docs.spring.io/spring-graphql/reference/testing.html): request documents, variables, error assertions, tester variants.
- [Spring for GraphQL 1.3 — GraphQlTester API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.html): `documentName`, `variable`, `variables`, `execute`, `path`, `errors`.
- [Spring for GraphQL 1.3 — GraphQlTester.Path API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html): `hasValue`, `valueIsNull`, `entity`, `entityList`.
- [Spring — Building a GraphQL Service](https://spring.io/guides/gs/graphql-server): schema, controller mapping, query và GraphQL tester ở slice.
- [GraphQL Specification](https://spec.graphql.org/October2021/): operation, selection set, variables, non-null, input coercion và response errors.

**Ghi nhớ:** `GraphQlTester` kiểm **GraphQL document + variables + data/errors** trên cùng một API bất kể tester chạy server-side hay qua HTTP. Dùng `@GraphQlTest` cho query/mutation resolver nhanh, `HttpGraphQlTester` khi cần xác minh HTTP transport, và luôn kiểm mutation đã thay đổi trạng thái như mong đợi. Một test chỉ thấy HTTP 200 hoặc chỉ thấy `data.addBook.title` đúng **chưa phải bằng chứng đầy đủ** về hành vi GraphQL của hệ thống.
