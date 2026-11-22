# Spring GraphQL: Kiểm tra data path, GraphQL errors và nullability

## 1. Vì sao GraphQL phải kiểm cả data và errors?

Trong REST, một bài kiểm thử thường bắt đầu bằng HTTP status và response body. Với GraphQL, điều này **chưa đủ**: nhiều lỗi phát sinh **trong lúc thực thi một field** vẫn được trả về bằng HTTP 200, kèm **`data` một phần** và mảng **`errors`**. Nếu chỉ kiểm `status=200`, test có thể bỏ qua lỗi resolver, trả thiếu dữ liệu hoặc vi phạm ràng buộc Non-Null.

Ví dụ một query:

~~~graphql
query {
  book(id: "B-1") {
    id
    title
    note
  }
  status
}
~~~

Khi tất cả thành công, response có thể là:

~~~json
{
  "data": {
    "book": {
      "id": "B-1",
      "title": "Spring GraphQL",
      "note": "Bản in 2026"
    },
    "status": "READY"
  }
}
~~~

Nếu resolver cho `book.note` gặp lỗi nhưng `note` là một field **nullable**, GraphQL có thể trả **partial data**:

~~~json
{
  "data": {
    "book": {
      "id": "B-1",
      "title": "Spring GraphQL",
      "note": null
    },
    "status": "READY"
  },
  "errors": [
    {
      "message": "Internal error",
      "locations": [{"line": 5, "column": 5}],
      "path": ["book", "note"]
    }
  ]
}
~~~

Đây là **minh họa cấu trúc**, không cam kết thông điệp lỗi hay vị trí dòng/cột của một Spring GraphQL version cụ thể. Điều mang tính hợp đồng là **vị trí lỗi**, dữ liệu còn giữ được, cách `null` lan truyền theo schema, và những mã lỗi nghiệp vụ mà ứng dụng tự định nghĩa.

Bài học tập trung vào **kiểm thử ứng dụng Spring Boot dùng Spring for GraphQL** qua `GraphQlTester` và HTTP thật. Phần SOAP chỉ được so sánh ngắn để tránh nhầm `errors.path` của GraphQL với XPath hoặc SOAP Fault.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết assertion cho field lồng nhau, alias, list index và object đã decode từ `data`.
2. Phân biệt **field không xuất hiện**, **field có giá trị null hợp lệ**, **field bị null do lỗi**.
3. Đọc `errors.message`, `errors.locations`, `errors.path`, `errors.extensions`; không viết test phụ thuộc thông điệp nội bộ.
4. Hiểu cơ chế **Non-Null propagation/bubbling** của `T!`, `[T]`, `[T!]`, `[T]!` và `[T!]!`.
5. Sử dụng `GraphQlTester.path(...)`, `valueIsNull()`, `pathDoesNotExist()`, `errors().expect(...)`, `errors().satisfy(...)` và `errors().verify()`.
6. Viết ví dụ Java 17+/Spring Boot 3.5.x với `@GraphQlTest` và `@MockitoBean`, cộng với HTTP integration test bằng JDK `HttpClient` kiểm raw JSON `data: null`.
7. Test đúng request errors, execution errors, nullability và partial data mà không đồng nhất chúng với HTTP 4xx/5xx.

## 2. Hình dạng một GraphQL response

Một response GraphQL thông thường có những thành phần sau:

| Key | Ý nghĩa | Có luôn không? |
| --- | --- | --- |
| `data` | Dữ liệu của operation đã được thực thi | Có khi operation được thực thi; giá trị có thể là `null` |
| `errors` | Danh sách lỗi parse/validation/execution hoặc field resolver | Chỉ có khi có lỗi; mỗi error có `message` |
| `extensions` cấp root | Metadata bổ sung theo implementation | Không bắt buộc |
| `errors[].path` | Đường dẫn response field nơi lỗi execution xảy ra | Có đối với lỗi gắn với một response position; request error có thể không có |
| `errors[].locations` | Vị trí trong tài liệu query, bắt đầu đếm từ 1 | Có khi xác định được vị trí |
| `errors[].extensions` | Error code/classification/custom metadata | Tùy implementation và application |

Cần phân biệt **hai nhóm lỗi** của GraphQL:

**Request error:** cú pháp query sai, field không tồn tại trong schema, type argument sai, variable không hợp lệ. Operation có thể bị từ chối **trước khi thực thi**; response có `errors` nhưng **không có key `data`**.

**Execution error:** field resolver lỗi, không thể chuyển đổi output hoặc trả `null` khi schema yêu cầu Non-Null. Operation đã được thực thi; response chứa `data`, có thể là **object một phần** hoặc **`null`**, đồng thời có `errors`. Một lỗi ở field không nhất thiết làm mất toàn bộ kết quả query.

Không nên cố định “GraphQL error = HTTP 500”. GraphQL-over-HTTP quy định status khác nhau theo loại lỗi, media type `Accept` và cách triển khai. Với execution error, HTTP 200 là trường hợp phổ biến và hợp lệ. HTTP test cần assert **body GraphQL** cùng với status theo contract transport cụ thể.

### 2.1 Các trường hợp nhìn giống nhau nhưng khác ý nghĩa

~~~json
{"data":{"book":{"id":"B-1","note":null}}}
~~~

`note` đã được chọn và **đang null**, **không có errors**: có thể là null hợp lệ theo schema.

~~~json
{"data":{"book":{"id":"B-1"}}}
~~~

`note` **không xuất hiện** vì operation không yêu cầu field đó (hoặc response bị thay đổi bất thường). Đây **không phải** `note: null`.

~~~json
{
  "data":{"book":{"id":"B-1","note":null}},
  "errors":[{"message":"...","path":["book","note"]}]
}
~~~

`note` null **do lỗi thực thi** (khi lỗi gắn chính đường dẫn đó). Không thể chỉ nhìn `data.book.note` để phân biệt với null hợp lệ; phải kiểm `errors`.

~~~json
{
  "data":{"book":null,"status":"READY"},
  "errors":[{"message":"...","path":["book","title"]}]
}
~~~

Lỗi ở `book.title` có thể làm **cả `book` thành null** nếu `title: String!`, dù lỗi vẫn trỏ tới field `title` sâu hơn.

~~~json
{
  "data":null,
  "errors":[{"message":"...","path":["strictBook","title"]}]
}
~~~

Nếu `strictBook: Book!` và `title: String!` lỗi, `null` có thể lan tận **root `data`**. Đây vẫn là execution result, **khác** response request validation không có key `data`.

## 3. Data path và error path không phải một thứ

**Data path** là cách test chọn giá trị bên trong `data`. Với Spring `GraphQlTester`, `path("book.title")` bắt đầu từ **root của `data`**, không cần viết `path("data.book.title")`.

**Error path** là một **mảng các segment** trong `errors[*].path` theo đặc tả GraphQL, ví dụ:

~~~json
["books", 1, "title"]
~~~

- `"books"`: tên field trong response.
- `1`: chỉ số **0-based** của phần tử thứ hai.
- `"title"`: tên field con gây lỗi.

Spring `ResponseError.getParsedPath()` cho giá trị tương đương `List.of("books", 1, "title")`; `getPath()` là biểu diễn chuỗi như `books[1].title`. **Không nhầm số 1 với string `"1"`**.

### 3.1 Alias thay đổi error path

Operation:

~~~graphql
query {
  chosen: book(id: "B-1") {
    id
    title
  }
}
~~~

Response sử dụng key `chosen` thay cho `book`. Nếu `title` lỗi, `errors[*].path` là:

~~~json
["chosen", "title"]
~~~

Đây là đường dẫn **trong response**, không phải tên field gốc trong schema hay tên method Java. Test phải assert alias đúng. Khi chọn data, dùng `path("chosen.id")`, không dùng `path("book.id")`.

### 3.2 Khi lỗi bubbles, error path vẫn sâu

Nếu `Book.title: String!` trả null và `Query.book: Book` là nullable, dữ liệu có thể trở thành `{"book":null}`. Nhưng lỗi vẫn ghi `["book","title"]`. Nó xác định **nguồn gốc** lỗi, không phải field tồn tại cuối cùng trong `data`.

Vì vậy hai assertion cần đi cùng nhau:

1. `errors.path` nêu chính xác field hỏng.
2. `data` nêu đúng phần bị null theo schema và những sibling nào còn nguyên.

Chỉ assert `book == null` không chứng minh lý do null; chỉ assert `errors.path` không chứng minh việc null propagate đúng hợp đồng.

## 4. Nullability trong GraphQL SDL

GraphQL SDL dùng `!` để chỉ kiểu Non-Null.

| SDL type | List có thể null? | Item có thể null? | Ví dụ hợp lệ |
| --- | --- | --- | --- |
| `Book` | Không phải list; field có thể null | — | `null` hoặc object Book |
| `Book!` | Không phải list; field **không được null** | — | Book hợp lệ; null gây execution error |
| `[Book]` | Có | Có | `null`, `[]`, `[book,null]` |
| `[Book!]` | Có | Không | `null`, `[]`, `[book]` |
| `[Book]!` | Không | Có | `[]`, `[book,null]` |
| `[Book!]!` | Không | Không | `[]` hoặc list toàn Book hợp lệ |

**`!` không phải Java `@NotNull` và cũng không ngăn method Java trả null.** GraphQL executor kiểm kiểu dữ liệu đã resolve sau đó áp dụng coercion và null propagation.

Giả sử schema:

~~~graphql
type Query {
  book(id: ID!): Book
  strictBook(id: ID!): Book!
  optionalBooks: [Book]
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  note: String
}
~~~

Các hệ quả khi `title` null:

- `book: Book` có thể trở thành `null`, trong khi các root sibling nullable/valid vẫn trả dữ liệu.
- `strictBook: Book!` khiến lỗi lan từ `Book.title` lên `strictBook` và tiếp tục đến root `data: null`.
- `optionalBooks: [Book]` với phần tử thứ hai title null sẽ có `optionalBooks: [validBook, null]`; list vẫn tồn tại.
- `books: [Book!]!` với một phần tử hỏng sẽ làm cả list null, rồi lan lên root data vì list cũng Non-Null.
- `[Book!]` (list nullable, item Non-Null) sẽ làm **toàn list null**, nhưng có thể giữ các root siblings.
- `[Book]!` (list Non-Null, item nullable) sẽ giữ list và thay riêng item bằng null.

### 4.1 Vì sao null được lan lên cha?

Quy tắc bắt buộc: một field khai báo Non-Null **không thể** nhận null trong dữ liệu thành công. Khi resolver trả null hoặc bị lỗi ở field Non-Null, GraphQL xem đó là execution error và gán **giá trị null cho parent response position**. Nếu parent cũng Non-Null, tiếp tục lan lên cho tới khi gặp một field nullable hoặc root data.

Ví dụ:

~~~text
Query.book: Book          (nullable)
    |
    +-- Book.id: ID!      = "B-1"
    |
    +-- Book.title:String! = null  <-- vi phạm Non-Null
             |
             v
Query.book becomes null           <-- điểm dừng
Query.status remains "READY"      <-- root sibling vẫn có thể tồn tại
errors.path = ["book","title"]     <-- lỗi vẫn chỉ field gốc
~~~

**Một error, không nhất thiết một error mới ở mọi cấp bubble.** Việc null lan lên cha không có nghĩa phải thêm một bản ghi lỗi mới cho mỗi parent. Test không nên kỳ vọng mảng errors chứa cả `book.title`, `book` và `data` cho cùng một vi phạm.

### 4.2 Null của object khác null của list element

Với `optionalBooks: [Book]`:

~~~json
{
  "data": {
    "optionalBooks": [
      {"id":"B-1","title":"Spring GraphQL"},
      null
    ]
  },
  "errors": [
    {"message":"...","path":["optionalBooks",1,"title"]}
  ]
}
~~~

Phần tử có `title` hỏng trở thành null, nhưng index vẫn được giữ. Không tự động lọc phần tử lỗi hoặc dịch phần tử sau lên index 1. Đây là lý do `errors.path` cần chỉ số list.

### 4.3 Empty list không phải null

`[]` là **list hợp lệ, không có phần tử** và có thể xuất hiện trong bất cứ kiểu list nào phía trên, kể cả `[Book!]!`. Nó khác `null`. `GraphQlTester.path(...).hasValue()` có ngữ nghĩa non-null **hoặc list không rỗng**; do đó khi kỳ vọng một list rỗng, nên dùng `entityList(...).hasSize(0)` thay vì `hasValue()`.

## 5. GraphQlTester: DSL cho data path

Spring for GraphQL có artifact `spring-graphql-test`, cung cấp `GraphQlTester` độc lập với transport. Một test chọn operation bằng `document(...)`, tùy chọn variables, gọi `execute()` rồi assert.

~~~java
GraphQlTester.Response response = tester.document("""
        query BookById($id: ID!) {
          book(id: $id) {
            id
            title
            note
          }
        }
        """)
        .variable("id", "B-1")
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("B-1");

response.path("book.title").hasValue();
~~~

Đây là **đoạn trong test có `GraphQlTester tester` và import tương ứng**, chưa phải file độc lập. `GraphQlTester.Response` là object trả về từ `execute()`; có thể dùng để kiểm nhiều paths của **cùng response** thay vì chạy lại query nhiều lần.

### 5.1 Các assertion quan trọng

| Method | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `path("book.title").entity(String.class).isEqualTo("...")` | Decode scalar và so sánh chính xác | Field string bắt buộc |
| `path("book").hasValue()` | Field tồn tại với non-null value hoặc non-empty list | Object mong có |
| `path("book.note").valueIsNull()` | Field tồn tại với giá trị JSON null | Nullable note không có |
| `path("book.note").pathDoesNotExist()` | Không có đường dẫn này trong `data` | Query không chọn note |
| `path("books").entityList(BookView.class).hasSize(2)` | Decode list và kiểm số item | Danh sách hữu hạn |
| `path("book").entity(BookView.class).isEqualTo(expected)` | Decode object và so sánh dữ liệu | DTO/record có equals |
| `path("book").matchesJson("{...}")` | So sánh cấu trúc JSON | Nhiều field ổn định |

**Tên method Spring GraphQL 1.x cần ghi đúng:** `valueIsNull()` và `pathDoesNotExist()`, **không phải** `isNull()` / `doesNotExist()`. Đây là khác biệt dễ gặp khi học từ các ví dụ milestone hoặc từ DSL khác.

### 5.2 Data path không mở đầu bằng data

Với response:

~~~json
{"data":{"book":{"id":"B-1"}}}
~~~

Đúng:

~~~java
response.path("book.id").entity(String.class).isEqualTo("B-1");
~~~

Không đúng về scope:

~~~java
// Không dùng tiền tố "data." khi gọi GraphQlTester.path(...).
response.path("data.book.id");
~~~

`GraphQlTester` tự đi vào root `data`. Phần `errors` được kiểm qua `response.errors()`, không dùng `path("errors[0].path")` như thể errors là data field.

### 5.3 Path của array và alias

Nếu schema/query trả `books` là array:

~~~java
response.path("books[0].title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Nếu query đặt alias `chosen: book(...)`:

~~~java
response.path("chosen.id")
        .entity(String.class)
        .isEqualTo("B-1");
~~~

JSONPath hỗ trợ các biểu thức khác như `books[*].id`; khi kiểm list, dùng `entityList(...)` hoặc các assertions phù hợp. Đừng hardcode index từ một query có ordering không xác định; khi cần vị trí ổn định, hãy có contract sắp xếp.

## 6. GraphQlTester: DSL cho errors

Theo mặc định, nếu gọi `path(...)` vào response có **GraphQL errors chưa được xử lý/kiểm**, `GraphQlTester` sẽ fail. Đây là cơ chế hữu ích: một test happy path không được vô tình PASS khi query trả partial data kèm lỗi.

### 6.1 Không mong lỗi: verify không có errors

~~~java
GraphQlTester.Response response = tester.document("""
        query { book(id: "B-1") { id title } }
        """).execute();

response.errors().verify();
response.path("book.id").entity(String.class).isEqualTo("B-1");
~~~

`errors().verify()` khẳng định không có unexpected GraphQL errors. Nếu operation không trả errors, việc đi trực tiếp tới `response.path(...)` cũng có kiểm soát errors mặc định, nhưng gọi explicit `verify()` làm ý định rõ.

### 6.2 Mong đúng một lỗi theo path

~~~java
GraphQlTester.Traversable data = tester.document("""
        query {
          book(id: "BROKEN-NOTE") { id title note }
          status
        }
        """)
        .execute()
        .errors()
        .expect(error -> error.getPath().equals("book.note"))
        .verify();

data.path("book.id")
        .entity(String.class)
        .isEqualTo("BROKEN-NOTE");
data.path("book.note").valueIsNull();
data.path("status").entity(String.class).isEqualTo("READY");
~~~

`expect(predicate)` khác `filter(predicate)`:

- `expect` yêu cầu **tồn tại ít nhất một error khớp** predicate, nếu không sẽ fail; error được dự kiến sẽ không cản trở bước kiểm data tiếp theo.
- `filter` chỉ bỏ qua error nếu xuất hiện, **không yêu cầu** error thực sự có. Vì vậy dùng `filter` để kiểm nhánh bắt buộc lỗi là sai mục đích.
- `verify` fail nếu còn unexpected errors chưa được xử lý.
- Nếu cần kiểm **chính xác số lượng, path, message/code và metadata**, dùng `satisfy(...)` rồi assert nội dung danh sách.

### 6.3 Kiểm chính xác mảng lỗi, kể cả list index

~~~java
GraphQlTester.Traversable data = tester.document("""
        query {
          optionalBooks { id title }
          status
        }
        """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertEquals(1, errors.size());
            assertEquals(
                    List.of("optionalBooks", 1, "title"),
                    errors.get(0).getParsedPath());
        });

data.path("optionalBooks[1]").valueIsNull();
data.path("status").entity(String.class).isEqualTo("READY");
~~~

Đoạn trên cần `java.util.List` và `assertEquals` trong test. `satisfy` cho phép xem **toàn bộ** errors và được coi như đã xử lý chúng; vì vậy **nhất thiết assert số lượng/nội dung** trong lambda. Nếu chỉ dùng `satisfy(errors -> {})`, test có thể bỏ qua mọi lỗi không mong muốn.

### 6.4 Không phụ thuộc message nội bộ

GraphQL Java/Spring GraphQL có thể che lỗi chưa được xử lý thành thông điệp kiểu “Internal error…” và kèm execution ID. Nội dung error message cụ thể, error classification cho exception không được xử lý, locations và cách format có thể thay đổi giữa versions.

Ưu tiên assert:

1. `getParsedPath()` hoặc `getPath()` chính xác.
2. Số lượng error mong đợi, khi contract quy định.
3. `extensions.code` **nếu chính API của bạn định nghĩa code ổn định**, không phải enum/string ngẫu nhiên do framework nội bộ tạo.
4. Không để raw stacktrace, SQL query hay token bị lộ trong `message`/`extensions`.

Nếu ứng dụng đã có `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler` ánh xạ domain error thành mã như `BOOK_NOT_FOUND`, test thêm `errors[].extensions.code` bằng cách đọc `getExtensions()`. Cần tách “null do bản ghi không tồn tại” hợp lệ với “exception chưa xử lý” để thiết kế API không mâu thuẫn.

## 7. Một schema nhỏ để test cả nullable và Non-Null

Trong phần thực hành, schema SDL ở `src/main/resources/graphql/schema.graphqls`:

~~~graphql
type Query {
  book(id: ID!): Book
  strictBook(id: ID!): Book!
  books: [Book!]!
  optionalBooks: [Book]
  status: String!
}

type Book {
  id: ID!
  title: String!
  note: String
}
~~~

Đây là **schema hoàn chỉnh** cho ví dụ, không có mutation/subscription. Chọn chủ đích:

- `book` nullable → cho phép không tìm thấy sách mà không phải báo lỗi.
- `strictBook` Non-Null → nếu không có sách hoặc một child Non-Null hỏng, có thể làm `data: null`.
- `books` cả list và item Non-Null → lỗi của một item làm null lan qua list đến root.
- `optionalBooks` list và item nullable → lỗi một item không hủy cả list.
- `title` Non-Null → tạo được trường hợp bắt buộc bubble khi getter trả null.
- `note` nullable → cho phép null tự nhiên hoặc null do resolver lỗi nhưng giữ các field khác.
- `status` sibling Non-Null trả `READY` → giúp test thấy partial data vẫn giữ sibling khi lỗi dừng ở một field nullable.

Trong một API production, schema nullability là **hợp đồng với client**. Thay `Book` thành `Book!` hoặc `[Book]` thành `[Book!]!` là một thay đổi có thể làm client đổ vỡ nghiêm trọng khi dữ liệu sai hoặc lỗi hạ tầng xuất hiện.

## 8. Ví dụ chạy được Java 17+ / Spring Boot 3.5.x

Bài thực hành gồm các file production, GraphQL SDL và hai test classes:

- **`@GraphQlTest`**: kiểm data paths/errors/nullability trực tiếp trên GraphQL execution engine **không mở server HTTP**, với catalog là Mockito mock.
- **`@SpringBootTest(RANDOM_PORT)`**: kiểm raw JSON qua **HTTP thật** để xác nhận có `data:null` hay không, error path với index và sự sống còn của sibling fields.

Không dùng database, Kafka, Redis, Docker hay dịch vụ bên ngoài. Test live sử dụng **JDK `java.net.http.HttpClient`** thay vì WebClient, để kiểm JSON wire format rõ ràng và không cần một GraphQL HTTP test transport riêng.

### 8.1 Cây thư mục

~~~text
src/
  main/
    java/
      example/graphqltest/
        GraphQlDemoApplication.java
        Book.java
        BookCatalog.java
        InMemoryBookCatalog.java
        BookGraphQlController.java
    resources/
      graphql/
        schema.graphqls
  test/
    java/
      example/graphqltest/
        BookGraphQlSliceTest.java
        BookGraphQlHttpTest.java
~~~

Mọi Java source dùng package `example.graphqltest`. Đặt tests cùng hoặc bên dưới package của primary `@SpringBootApplication` để Spring Boot tìm được cấu hình gốc. Java 17 hỗ trợ text blocks cho GraphQL documents.

### 8.2 GraphQlDemoApplication.java

~~~java
package example.graphqltest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlDemoApplication.class, args);
    }
}
~~~

Boot component-scan controller và catalog production; khởi tạo GraphQL schema từ `classpath:graphql/**/` theo cấu hình mặc định của Spring Boot.

### 8.3 Book.java — POJO có getters rõ ràng

~~~java
package example.graphqltest;

public final class Book {
    private final String id;
    private final String title;
    private final String note;

    public Book(String id, String title, String note) {
        this.id = id;
        this.title = title;
        this.note = note;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getNote() {
        return note;
    }
}
~~~

Dùng getter JavaBean giúp `graphql-java PropertyDataFetcher` đọc `Book.id` và `Book.title` một cách rõ ràng. Trường `note` cũng có getter, nhưng ở ví dụ controller sẽ khai báo một `@SchemaMapping` tường minh cho nó để mô phỏng lỗi resolver.

**Quan trọng:** constructor cho phép `title == null` là **có chủ đích để test lỗi Non-Null**. Không lấy đây làm khuyến nghị thiết kế domain production; bình thường nên validate invariant sớm để dữ liệu không vi phạm GraphQL schema.

### 8.4 BookCatalog.java — dependency interface

~~~java
package example.graphqltest;

import java.util.List;

public interface BookCatalog {
    Book findById(String id);
    List<Book> findAll();
}
~~~

Interface không trả reactive types vì ví dụ tập trung vào **GraphQL execution semantics**, không phải `Mono`/`Flux`. Spring GraphQL vẫn xử lý resolver trả đối tượng đồng bộ; một ứng dụng thực có thể dùng `Mono<Book>`/`Flux<Book>` và test tương đương.

### 8.5 InMemoryBookCatalog.java — dữ liệu cố định

~~~java
package example.graphqltest;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class InMemoryBookCatalog implements BookCatalog {

    @Override
    public Book findById(String id) {
        return switch (id) {
            case "B-1" ->
                    new Book("B-1", "Spring GraphQL", "Bản in 2026");
            case "NO-NOTE" ->
                    new Book("NO-NOTE", "Optional Field", null);
            case "BROKEN-NOTE" ->
                    new Book("BROKEN-NOTE", "Readable Title", "ignored");
            case "BAD-TITLE" ->
                    new Book("BAD-TITLE", null, "Note still exists");
            default -> null;
        };
    }

    @Override
    public List<Book> findAll() {
        return List.of(
                findById("B-1"),
                findById("BAD-TITLE"));
    }
}
~~~

Giải thích fixture:

- `B-1`: mọi field hợp lệ.
- `NO-NOTE`: `note == null` là giá trị nullable bình thường, **không cần error**.
- `BROKEN-NOTE`: controller sẽ ném exception ở `@SchemaMapping` của `note`; mặc dù Book object có note string, GraphQL data fetcher riêng quyết định field.
- `BAD-TITLE`: getter `getTitle()` trả null, cố ý vi phạm `Book.title: String!`, gây Non-Null propagation.
- `findAll()`: hai phần tử, phần tử thứ hai có title null, giúp test list index error.

Tất cả dữ liệu là fixture in-memory có thứ tự ổn định. Không có database hay network ngoài.

### 8.6 BookGraphQlController.java — resolver thực

~~~java
package example.graphqltest;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {
    private final BookCatalog catalog;

    public BookGraphQlController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return catalog.findById(id);
    }

    @QueryMapping
    public Book strictBook(@Argument String id) {
        return catalog.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return catalog.findAll();
    }

    @QueryMapping
    public List<Book> optionalBooks() {
        return catalog.findAll();
    }

    @QueryMapping
    public String status() {
        return "READY";
    }

    @SchemaMapping(typeName = "Book", field = "note")
    public String note(Book book) {
        if ("BROKEN-NOTE".equals(book.getId())) {
            throw new IllegalStateException("note provider unavailable");
        }
        return book.getNote();
    }
}
~~~

`@QueryMapping` gắn method với field của type `Query` theo tên method. `@SchemaMapping(typeName="Book", field="note")` định nghĩa resolver riêng cho `Book.note`; các field `id` và `title` được graphql-java lấy từ POJO getters.

Đối với `BROKEN-NOTE`, exception ở `note` là **execution error gắn field**. Spring GraphQL/GraphQL Java có thể trả thông điệp lỗi đã được che để không lộ implementation. Bài test **không assert message exception gốc**, chỉ assert path và partial data.

Đối với `BAD-TITLE`, controller không ném exception: chính **GraphQL output coercion/Non-Null rule** phát hiện getter `title == null` và lan lỗi. Đây là hai nguồn lỗi khác nhau, rất hữu ích để học phân biệt.

### 8.7 Test slice — BookGraphQlSliceTest.java

~~~java
package example.graphqltest;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.when;

@GraphQlTest(BookGraphQlController.class)
@DisplayName("GraphQlTester data path, errors, nullability")
class BookGraphQlSliceTest {

    @Autowired
    GraphQlTester tester;

    @MockitoBean
    BookCatalog catalog;

    private static Book good() {
        return new Book("B-1", "Spring GraphQL", "Bản in 2026");
    }

    private static Book badTitle() {
        return new Book("BAD-TITLE", null, "Note still exists");
    }

    @Test
    @DisplayName("Query variable, nested data paths và scalar decode")
    void readsNestedDataPaths() {
        when(catalog.findById("B-1")).thenReturn(good());

        GraphQlTester.Response response = tester.document("""
                query BookById($id: ID!) {
                  book(id: $id) { id title note }
                }
                """)
                .variable("id", "B-1")
                .execute();

        response.errors().verify();
        response.path("book").hasValue();
        response.path("book.id")
                .entity(String.class).isEqualTo("B-1");
        response.path("book.title")
                .entity(String.class).isEqualTo("Spring GraphQL");
        response.path("book.note")
                .entity(String.class).isEqualTo("Bản in 2026");
    }

    @Test
    @DisplayName("Field được chọn và null hợp lệ, không có error")
    void acceptsNullableFieldWithoutError() {
        when(catalog.findById("NO-NOTE")).thenReturn(
                new Book("NO-NOTE", "Optional Field", null));

        GraphQlTester.Response response = tester.document("""
                { book(id: "NO-NOTE") { id note } }
                """).execute();

        response.errors().verify();
        response.path("book.id")
                .entity(String.class).isEqualTo("NO-NOTE");
        response.path("book.note").valueIsNull();
    }

    @Test
    @DisplayName("Field không được select khác với field null")
    void distinguishesOmittedField() {
        when(catalog.findById("B-1")).thenReturn(good());

        GraphQlTester.Response response = tester.document("""
                { book(id: "B-1") { id } }
                """).execute();

        response.errors().verify();
        response.path("book.id")
                .entity(String.class).isEqualTo("B-1");
        response.path("book.note").pathDoesNotExist();
    }

    @Test
    @DisplayName("Query field nullable không tìm thấy là null hợp lệ")
    void missingNullableBookIsNotAnError() {
        when(catalog.findById("MISSING")).thenReturn(null);

        GraphQlTester.Response response = tester.document("""
                { book(id: "MISSING") { id title } status }
                """).execute();

        response.errors().verify();
        response.path("book").valueIsNull();
        response.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("Exception ở field nullable tạo partial data và error path")
    void nullableResolverFailureKeepsSiblingData() {
        when(catalog.findById("BROKEN-NOTE")).thenReturn(
                new Book("BROKEN-NOTE", "Readable Title", "ignored"));

        GraphQlTester.Traversable data = tester.document("""
                {
                  book(id: "BROKEN-NOTE") { id title note }
                  status
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> {
                    assertEquals(1, errors.size());
                    assertEquals(
                            List.of("book", "note"),
                            errors.get(0).getParsedPath());
                    assertFalse(errors.get(0).getMessage().isBlank());
                });

        data.path("book.id")
                .entity(String.class).isEqualTo("BROKEN-NOTE");
        data.path("book.title")
                .entity(String.class).isEqualTo("Readable Title");
        data.path("book.note").valueIsNull();
        data.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("Title Non-Null sai làm book null, status vẫn còn")
    void nonNullChildBubblesToNullableParent() {
        when(catalog.findById("BAD-TITLE")).thenReturn(badTitle());

        GraphQlTester.Traversable data = tester.document("""
                {
                  book(id: "BAD-TITLE") { id title }
                  status
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getParsedPath().equals(
                                List.of("book", "title")))
                .verify();

        data.path("book").valueIsNull();
        data.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("List chứa nullable item giữ index lỗi")
    void nullableListElementBecomesNull() {
        when(catalog.findAll()).thenReturn(
                List.of(good(), badTitle()));

        GraphQlTester.Traversable data = tester.document("""
                {
                  optionalBooks { id title }
                  status
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getParsedPath().equals(
                                List.of("optionalBooks", 1, "title")))
                .verify();

        data.path("optionalBooks[0].title")
                .entity(String.class).isEqualTo("Spring GraphQL");
        data.path("optionalBooks[1]").valueIsNull();
        data.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("Alias là tên thật trong errors.path")
    void errorPathUsesResponseAlias() {
        when(catalog.findById("BAD-TITLE")).thenReturn(badTitle());

        GraphQlTester.Traversable data = tester.document("""
                {
                  selected: book(id: "BAD-TITLE") { id title }
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getPath().equals("selected.title"))
                .verify();

        data.path("selected").valueIsNull();
    }

    @Test
    @DisplayName("Empty list vẫn hợp lệ dù hasValue không phù hợp")
    void verifiesEmptyListExplicitly() {
        when(catalog.findAll()).thenReturn(List.of());

        GraphQlTester.Response response = tester.document("""
                { optionalBooks { id title } }
                """).execute();

        response.errors().verify();
        response.path("optionalBooks")
                .entityList(Map.class).hasSize(0);
    }

    @Test
    @DisplayName("Unknown schema field là request validation error")
    void invalidFieldIsARequestError() {
        tester.document("""
                { book(id: "B-1") { fieldNotInSchema } }
                """)
                .execute()
                .errors()
                .expect(error -> error.getParsedPath().isEmpty())
                .verify();
    }
}
~~~

**Có 10 phương thức JUnit Jupiter `@Test`.** Bài slice không tải HTTP server và không cần database; `@MockitoBean` đưa `BookCatalog` mock vào chính Spring test context, còn resolver, schema, nullability, GraphQL engine và `GraphQlTester` là **thật**.

### 8.8 Phân tích bằng chứng của từng test slice

| Test | Assertion chính | Điều được chứng minh |
| --- | --- | --- |
| `readsNestedDataPaths` | Variable ID, `book.id/title/note` | GraphQL resolver + response path + scalar decode |
| `acceptsNullableFieldWithoutError` | `note.valueIsNull()` và `errors().verify()` | Null hợp lệ, không phải execution failure |
| `distinguishesOmittedField` | `pathDoesNotExist()` | Field không được query khác field null |
| `missingNullableBookIsNotAnError` | `book == null`, sibling status còn | Nullable root field có thể không tìm thấy không báo lỗi |
| `nullableResolverFailureKeepsSiblingData` | Error path `book.note`, note null, id/title/status còn | Partial data với resolver exception ở field nullable |
| `nonNullChildBubblesToNullableParent` | Error path `book.title`, book null, status còn | Non-Null child làm parent nullable bị null |
| `nullableListElementBecomesNull` | Error path gồm index `1`, phần tử 1 null | `[Book]` giữ vị trí lỗi, không null cả list |
| `errorPathUsesResponseAlias` | `selected.title` thay `book.title` | Error path sử dụng tên alias trong response |
| `verifiesEmptyListExplicitly` | `entityList(...).hasSize(0)` | Empty list khác null; không lạm dụng `hasValue()` |
| `invalidFieldIsARequestError` | Error không có response field path | Validation error trước execution, không có resolver result |

**Các điểm không được suy diễn:**

- Vì catalog là mock, test không xác minh persistence hoặc mapping SQL production.
- Test `invalidFieldIsARequestError` không assert HTTP status vì nó chạy trong GraphQL execution test **không có HTTP transport**.
- Test `nullableResolverFailureKeepsSiblingData` không phụ thuộc error message nội bộ; `satisfy` assert count, parsed path và thông điệp không trống.
- `entityList(Map.class).hasSize(0)` chỉ kiểm rỗng, không cần object mapper xây một `Book` từ array đang rỗng.
- Tất cả test mỗi method tự stub collaborator, tránh phụ thuộc thứ tự chạy hoặc state của Mockito giữa các test methods.

## 9. HTTP integration test: kiểm chính xác data:null và path indexes

Một số trạng thái cần kiểm **raw GraphQL response** thay vì chỉ test một data path. Đặc biệt:

- `data:null` là một **key có mặt** và giá trị null, không phải object chứa field null.
- Request error có thể khiến key `data` **không có mặt**.
- Error path là JSON array kết hợp strings và integers.
- HTTP status là tầng transport, **khác** số lượng GraphQL execution errors.

Trong ví dụ, ta dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` để khởi động server thật, rồi JDK `HttpClient` gửi JSON POST đến `/graphql`. Endpoint mặc định của Spring for GraphQL trên Spring Boot MVC là `/graphql`; nếu dự án đặt `spring.graphql.http.path` khác, phải điều chỉnh đường dẫn.

### 9.1 BookGraphQlHttpTest.java

~~~java
package example.graphqltest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("GraphQL HTTP thật: data null, errors.path")
class BookGraphQlHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Test
    @DisplayName("Non-Null root khiến data là JSON null")
    void strictRootBubblesErrorToDataNull() throws Exception {
        JsonNode body = execute("""
                {
                  strictBook(id: "BAD-TITLE") { id title }
                  status
                }
                """);

        assertTrue(body.has("data"));
        assertTrue(body.get("data").isNull());
        assertEquals(1, body.path("errors").size());
        assertEquals("strictBook",
                body.path("errors").get(0)
                        .path("path").get(0).asText());
        assertEquals("title",
                body.path("errors").get(0)
                        .path("path").get(1).asText());
    }

    @Test
    @DisplayName("[Book!]! làm data null khi phần tử thứ hai lỗi")
    void strictListBubblesErrorToDataNull() throws Exception {
        JsonNode body = execute("""
                {
                  books { id title }
                  status
                }
                """);

        assertTrue(body.has("data"));
        assertTrue(body.get("data").isNull());

        JsonNode errors = body.path("errors");
        assertEquals(1, errors.size());

        JsonNode path = errors.get(0).path("path");
        assertEquals("books", path.get(0).asText());
        assertEquals(1, path.get(1).asInt());
        assertEquals("title", path.get(2).asText());
    }

    @Test
    @DisplayName("[Book] giữ sibling và chỉ item lỗi thành null")
    void nullableListKeepsPartialData() throws Exception {
        JsonNode body = execute("""
                {
                  optionalBooks { id title }
                  status
                }
                """);

        assertTrue(body.path("data").isObject());
        assertEquals("READY",
                body.path("data").path("status").asText());

        JsonNode books = body.path("data").path("optionalBooks");
        assertTrue(books.isArray());
        assertEquals(2, books.size());
        assertEquals("B-1", books.get(0).path("id").asText());
        assertTrue(books.get(1).isNull());

        JsonNode errors = body.path("errors");
        assertEquals(1, errors.size());
        JsonNode path = errors.get(0).path("path");
        assertEquals("optionalBooks", path.get(0).asText());
        assertEquals(1, path.get(1).asInt());
        assertEquals("title", path.get(2).asText());
    }

    @Test
    @DisplayName("HTTP happy path có data và không có errors")
    void successReturnsNestedDataWithoutErrors() throws Exception {
        JsonNode body = execute("""
                {
                  selected: book(id: "B-1") { id title }
                  status
                }
                """);

        assertTrue(body.path("data").isObject());
        assertEquals("B-1",
                body.path("data").path("selected")
                        .path("id").asText());
        assertEquals("Spring GraphQL",
                body.path("data").path("selected")
                        .path("title").asText());
        assertEquals("READY",
                body.path("data").path("status").asText());
        assertFalse(body.has("errors"));
    }

    private JsonNode execute(String document) throws Exception {
        String requestJson = mapper.writeValueAsString(
                Map.of("query", document));

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:"
                                + port + "/graphql"))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.ofString(
                        requestJson, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        // Các truy vấn ở class này đều được thực thi;
        // execution errors bên trong thường trả HTTP 200.
        assertEquals(200, response.statusCode());

        return mapper.readTree(response.body());
    }
}
~~~

**Có 4 phương thức JUnit Jupiter `@Test`**. Các test không dựa vào thứ tự xử lý GraphQL root fields, không assert error message chứa execution ID hay nội dung của exception. Chúng kiểm chính xác **key data**, kiểu null, phần tử array, alias và `errors.path`.

### 9.2 Tại sao kiểm raw JSON thay vì chỉ GraphQlTester?

`GraphQlTester` là lựa chọn tốt nhất cho đa số data/error assertions. Nhưng lúc lỗi lan đến **root `data: null`**, việc xem response JSON có thể dễ hiểu hơn so với đi qua một data path không còn tồn tại.

Qua HTTP thật, ta đồng thời kiểm:

- Client encode GraphQL request dưới dạng JSON.
- Endpoint `/graphql` thực sự nhận POST.
- GraphQL execution trả error path đúng.
- Server encode kết quả JSON có `data:null` hoặc partial data.
- HTTP status theo setup của dự án (ở đây `Accept: application/json` và execution errors được kỳ vọng HTTP 200).

**Không chứng minh** database, authorization production, network proxy hoặc WebSocket subscriptions, vì ví dụ không sử dụng chúng.

## 10. Phân biệt GraphQL execution error và request validation error ở mức raw JSON

Ví dụ query không hợp lệ:

~~~graphql
query {
  book(id: "B-1") {
    fieldNotInSchema
  }
}
~~~

Theo đặc tả, đây là **request error**: validator phát hiện field không tồn tại, **không chạy resolver `book`** và không trả `data`.

Một response minh họa:

~~~json
{
  "errors": [
    {
      "message": "Validation error...",
      "locations": [{"line": 3, "column": 5}]
    }
  ]
}
~~~

Không có `data` là khác hẳn:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "...",
      "path": ["strictBook", "title"]
    }
  ]
}
~~~

Tại tầng transport, **HTTP status của request errors không nên bị hardcode theo một quy tắc chung**. Nếu dùng media type `application/graphql-response+json` theo GraphQL-over-HTTP, lỗi request không thực thi có thể dẫn tới HTTP 400; với `application/json` và các implementation/version khác nhau có thể có hành vi tương thích khác. Test theo **contract transport** của dự án, còn để kiểm nullability hãy dùng response execution thật.

### 10.1 Một helper kiểm data có mặt hay không

Mẫu Java trong test HTTP có `JsonNode body`:

~~~java
// Request error: không có entry "data" ở root.
assertFalse(body.has("data"));
assertTrue(body.path("errors").isArray());

// Execution error bubble: key "data" có mặt và là JSON null.
assertTrue(body.has("data"));
assertTrue(body.get("data").isNull());

// Nullable field: data object có field với JSON null.
assertTrue(body.path("data").path("book").isNull());
~~~

Đây là **ba mẫu cho ba response khác nhau**, không phải ba assertion cùng áp dụng một `body`. Jackson `path(...)` trả `MissingNode` nếu key không có; `get(...)` trả null Java reference khi không có. Dùng `has("data")` kết hợp `get("data").isNull()` để phân biệt **missing** và **JSON null**.

### 10.2 Khi operation có nhiều root fields

GraphQL query có thể chọn:

~~~graphql
query {
  book(id: "BAD-TITLE") { id title }
  status
}
~~~

`book` nullable nhưng child `title` Non-Null, nên `data.book = null`; `data.status = "READY"` vẫn có thể hiện diện. Ngược lại, nếu dùng `strictBook: Book!` và child title hỏng, `data: null` làm mất cả sibling data trong payload, dù resolver của sibling có thể đã chạy.

**Không suy luận “nếu sibling không xuất hiện thì chắc chắn nó không được thực thi”.** GraphQL có thể bắt đầu giải các field trước khi phát hiện null bubbling; test nên assert **response contract**, không phụ thuộc internal scheduling.

## 11. Chạy ví dụ bằng Gradle

Với dự án Spring Boot **3.5.x** đã có plugin và dependency management thích hợp, Java toolchain 17+, phần phụ thuộc tối thiểu trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình bổ sung**, không phải `build.gradle` hoàn chỉnh có plugin/version/toolchain. Spring Boot BOM phải quản lý phiên bản `spring-graphql-test` tương ứng, tránh khai báo một version GraphQL Java không tương thích.

**Vì sao không thêm `spring-boot-starter-webflux` ở đây?** Bài slice dùng `GraphQlTester` thực thi trực tiếp và bài HTTP dùng **JDK `HttpClient`**, không dùng `HttpGraphQlTester` có client dựa trên WebFlux. Nếu muốn sử dụng Spring `HttpGraphQlTester` trong test HTTP, theo tài liệu Boot cần thêm `spring-graphql-test` và WebFlux test dependencies khi chưa có.

Chạy hai class:

~~~bash
./gradlew test --tests example.graphqltest.BookGraphQlSliceTest --tests example.graphqltest.BookGraphQlHttpTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.graphqltest.BookGraphQlSliceTest --tests example.graphqltest.BookGraphQlHttpTest
~~~

**Kết quả kỳ vọng:** **14 phương thức `@Test`** (10 slice + 4 HTTP integration) được JUnit Jupiter phát hiện và **PASS** trong môi trường Boot 3.5.x được cấu hình như mô tả. Test không tự in stdout; Gradle có thể ghi `BUILD SUCCESSFUL` và báo cáo test trong `build/reports/tests/test/index.html`. Đây là **kết quả dự kiến từ thiết kế**, không phải log của một lần chạy build đã xác minh.

Nếu dự án đang ở Spring Boot 4.x, package của một số test helpers, modules và cấu hình starter có thay đổi. Hãy đối chiếu migration guide/API theo version; ví dụ `@GraphQlTest` import ở đây được viết **cụ thể cho Boot 3.5.x**.

## 12. Data path: kiểu dữ liệu, nested object, list và alias

GraphQL response có thể chứa một graph phức tạp, chẳng hạn:

~~~graphql
query {
  viewer {
    id
    orders {
      id
      lines {
        sku
        quantity
      }
    }
  }
}
~~~

Data path của một dòng hàng có thể là:

~~~text
viewer.orders[0].lines[2].sku
~~~

Với `GraphQlTester`:

~~~java
tester.document(document)
        .execute()
        .path("viewer.orders[0].lines[2].sku")
        .entity(String.class)
        .isEqualTo("BOOK-1");
~~~

Đây là **mẫu minh họa**, cần schema và `document` tương ứng; không phải endpoint trong project mẫu. Đường dẫn này bắt đầu tại **`data.viewer`**.

Khi một operation có list không được sắp xếp cố định, không nên assert `orders[0]` là order cụ thể. Hãy yêu cầu schema/resolver có sort ổn định hoặc decode list rồi tìm theo ID. Nếu contract không bảo đảm order, test phụ thuộc index sẽ flaky dù service đúng.

### 12.1 Decode object theo type thay vì nhiều JSONPath assertions

Có thể dùng Java record:

~~~java
public record BookView(String id, String title, String note) {
}
~~~

Trong test:

~~~java
BookView book = tester.document("""
        { book(id: "B-1") { id title note } }
        """)
        .execute()
        .path("book")
        .entity(BookView.class)
        .get();

assertEquals("B-1", book.id());
~~~

Đây là **đoạn minh họa mở rộng**, cần `BookView`, imports và mock service trả sách phù hợp. Nếu phiên bản API `GraphQlTester.Entity` của dự án hỗ trợ `get()` (Spring GraphQL 1.x có), decode object có thể thuận tiện hơn kiểm nhiều paths. Đối với nullable field/bubbled parent, phải **kiểm lỗi và null trước** thay vì ép decode một object không tồn tại.

**Không dùng direct JSON deserialization làm cách duy nhất để kiểm errors.** Một object được decode thành công có thể tồn tại cùng `errors` ở field sibling; GraphQlTester mặc định giúp bắt unexpected errors.

### 12.2 GraphQL null so với Java Optional

Một `Optional<Book>` hay `Mono<Book>` rỗng ở backend có thể được map thành nullable GraphQL field `null`, nhưng điều đó **không tự sinh GraphQL error**. Muốn client biết sự khác biệt giữa “không tìm thấy” và “upstream thất bại”, hãy định nghĩa schema/domain error policy rõ ràng.

Tương tự, `@Argument` nhận argument `ID!` sẽ bị GraphQL input validation chặn khi client gửi null/thiếu argument bắt buộc; không cần đợi controller Java tự phát hiện. Trong test, một request thiếu required variable là **request error**, không phải nonnull bubbling của output.

## 13. Kiểm nhiều GraphQL errors và không phụ thuộc thứ tự

Một query có thể trả hơn một execution error, ví dụ hai nullable root fields độc lập cùng lỗi. GraphQL không bắt buộc application phải ổn định **thứ tự mảng errors** theo thời điểm các resolver hoàn tất, đặc biệt khi có concurrency/batching.

Thay vì:

~~~java
// Dễ giòn nếu thứ tự errors thay đổi:
assertEquals("first.title", errors.get(0).getPath());
assertEquals("second.note", errors.get(1).getPath());
~~~

Hãy kiểm **tập các error paths** khi contract chỉ yêu cầu tập:

~~~java
Set<String> paths = errors.stream()
        .map(error -> error.getPath())
        .collect(Collectors.toSet());

assertEquals(
        Set.of("first.title", "second.note"),
        paths);
~~~

Đây là **mẫu trong lambda `errors().satisfy(errors -> {...})`**; cần import `java.util.Set`, `java.util.stream.Collectors` và `assertEquals`. Nếu cần chắc chắn không có duplicate/extra errors, assert thêm `errors.size() == 2`.

Không assert tất cả messages có đúng punctuation/version-specific IDs. Nếu application có error codes ổn định trong `extensions`, so sánh theo cặp **path + business code** để phân biệt chính xác nguồn lỗi.

## 14. GraphQL @ControllerAdvice và DataFetcherExceptionResolver

Spring for GraphQL có `DataFetcherExceptionResolver` và hỗ trợ `@GraphQlExceptionHandler` trong `@ControllerAdvice` để biến exception thành GraphQL error có chủ đích.

Một ứng dụng production có thể đặt policy:

- `BookNotFoundException` → mã nghiệp vụ `BOOK_NOT_FOUND`.
- `AccessDeniedException` → mã `FORBIDDEN`, không tiết lộ chi tiết quyền hoặc owner.
- Validation exception → mã `BAD_REQUEST` với metadata an toàn.
- Unexpected exception → lỗi nội bộ được che, có correlation ID dùng trong log riêng, không lộ stacktrace/query SQL/token.

Test nên kiểm:

~~~text
data field affected  -> null đúng theo SDL
errors[].path         -> field gây lỗi đúng
errors[].extensions   -> code ổn định của domain
errors[].message      -> không rò dữ liệu nhạy cảm
siblings              -> được giữ hoặc bị null bubble đúng kiểu
~~~

Ví dụ assertion khi **API đã định nghĩa** `extensions.code = "BOOK_NOT_FOUND"`:

~~~java
tester.document(document)
        .execute()
        .errors()
        .expect(error ->
                "book".equals(error.getPath())
                && "BOOK_NOT_FOUND".equals(
                        error.getExtensions().get("code")))
        .verify();
~~~

Đây là **mẫu minh họa cho policy riêng của dự án**, không áp dụng cho ví dụ in-memory mặc định vì nó không cài một error resolver custom. Nếu không thiết lập code này, không nên ghi test mong framework tự tạo `BOOK_NOT_FOUND`.

**Lưu ý security:** `errors.extensions` có thể bị client nhìn thấy; không trả Java class names, SQL, hostnames, file paths, tokens hoặc IDs nội bộ không cần thiết. Correlation ID dùng trong response nên không phải secret và phải có chính sách tracing/logging nhất quán.

## 15. DataLoader, batching và paths của list

Khi GraphQL dùng DataLoader, resolver có thể batch nhiều ID và trả kết quả ở thời điểm khác nhau. Error path vẫn mô tả **vị trí trong response**, không phụ thuộc bean DataLoader nào hoặc thứ tự request gửi xuống database.

Với list:

~~~graphql
query {
  orders {
    id
    customer {
      name
    }
  }
}
~~~

Nếu `orders[2].customer.name` lỗi, response path thông thường là:

~~~json
["orders", 2, "customer", "name"]
~~~

Nếu `Customer.name` Non-Null, `customer` nullable, null có thể dừng ở `orders[2].customer`. Nếu `customer: Customer!` và `orders: [Order!]!`, lỗi có thể lan qua order, list tới root data. **Schema quyết định điểm dừng**, không phải DataLoader.

Khi test DataLoader, nên tạo fixture có ID/ordering xác định; ngoài kiểm data/error path, có thể kiểm số batch calls, cache, N+1 và context propagation trong bài test chuyên trách. Không suy ra batching chạy tối ưu chỉ vì response GraphQL đúng.

## 16. GraphQL error và HTTP status: kiểm hai tầng riêng

Đây là bảng gợi ý diễn giải, **không phải bảng ánh xạ cố định** cho mọi GraphQL server:

| Tình huống | GraphQL response | HTTP status |
| --- | --- | --- |
| Operation hợp lệ, dữ liệu thành công | `data`, không errors | Thường 200 |
| Resolver lỗi ở nullable field | `data` partial, `errors` có `path` | Thường 200 |
| Non-Null bubble đến root | `data: null`, `errors` có `path` | Thường 200 |
| Query syntax/validation error | `errors`, không `data` | Tùy media type/version/spec transport; thường có 400 hoặc tương thích 200 |
| Auth thất bại trước GraphQL handler | Có thể không có GraphQL JSON | HTTP 401/403 từ security layer |
| Transport/network/server unavailable | Không có response GraphQL hợp lệ | HTTP 5xx/timeout/network exception |

### 16.1 Không coi HTTP 200 là thành công nghiệp vụ

Một test kiểu:

~~~java
assertEquals(200, response.statusCode());
~~~

chỉ xác minh HTTP transport. Cần thêm:

~~~java
JsonNode body = mapper.readTree(response.body());
assertFalse(body.has("errors"));
assertEquals("B-1",
        body.path("data").path("book").path("id").asText());
~~~

Ngược lại, khi **mong lỗi thực thi**, không assert `errors` rỗng; hãy assert số lỗi, path, data partial/null phù hợp.

### 16.2 Lỗi auth khác lỗi GraphQL resolver

Nếu Spring Security chặn request trước khi vào GraphQL HTTP handler, client có thể nhận HTTP 401/403 với body không tuân GraphQL response format. Đừng ép Jackson đọc `data/errors` ở mọi HTTP status.

Nếu GraphQL resolver tự kiểm authorization và trả một GraphQL error có `path`, đó là execution error hoặc custom domain behavior, cần test theo policy. Cần có security integration tests với user/roles thật trong test context, không vô hiệu hóa filters chỉ để query PASS.

## 17. Khi nào dùng @GraphQlTest, @SpringBootTest hoặc GraphQlTester variant?

| Kiểu test | Công cụ | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Resolver/controller + schema/nullability | `@GraphQlTest` + `GraphQlTester` + `@MockitoBean` | Nhanh, không HTTP server; tập trung data/errors | Không kiểm network/transport và service thật |
| Toàn bộ app không HTTP | `ExecutionGraphQlServiceTester` / GraphQL execution service | Kiểm GraphQL engine + context của test | Không kiểm TCP, HTTP headers |
| Boot HTTP mock context | `@SpringBootTest(MOCK)` + `@AutoConfigureHttpGraphQlTester` | Kiểm HTTP handler trên mock web client | Không chứng minh embedded server port/TCP |
| HTTP thật | `@SpringBootTest(RANDOM_PORT)` + `HttpGraphQlTester` hoặc JDK HttpClient | Kiểm raw request/response và server | Chậm hơn; vẫn không phải production topology |
| Business logic dưới resolver | JUnit/Mockito hoặc repository slice | Test quy tắc, data access, transaction phù hợp | Không kiểm GraphQL schema/error path |
| Subscription | WebSocketGraphQlTester/ExecutionGraphQlServiceTester + StepVerifier | Kiểm stream GraphQL | Khác một query response đơn; cần subscription test riêng |

**Trong Spring Boot 3.5.x**, `@GraphQlTest` auto-configure GraphQL execution infrastructure và `GraphQlTester`; không scan mọi `@Service`/`@Repository`. Vì vậy `BookCatalog` production không có trong slice, và `@MockitoBean` cung cấp collaborator.

Với `RANDOM_PORT`, Spring Boot có thể cung cấp `HttpGraphQlTester` nếu test dependencies phù hợp; bài ví dụ dùng JDK `HttpClient` để thấy raw JSON và không cần thêm một WebFlux HTTP tester. Không nên kết luận `@GraphQlTest` đã kiểm Spring Security filters hoặc HTTP status thật.

## 18. GraphQL và SOAP: tránh lẫn path/error semantics

Tên nhóm kiến thức có cả GraphQL và SOAP, nhưng **bài này là GraphQL-specific**:

| Chủ đề | GraphQL | SOAP |
| --- | --- | --- |
| Dữ liệu | JSON `data` theo selection set | XML `Envelope` / `Body` |
| Chọn đường dẫn trong test | `GraphQlTester.path("book.title")`, JSONPath | XPath, XML namespaces |
| Lỗi ứng dụng | `errors[]` với `message`, `path`, `extensions` | `soap:Fault` với `Code`/`Reason`/`Detail` |
| Partial data | Có thể cùng lúc có `data` và `errors` | Tùy WSDL/operation, không có cơ chế null bubbling như GraphQL |
| Non-Null propagation | Do SDL `!` và executor GraphQL | Không tương đương trực tiếp với XSD `nillable` |
| Transport | GraphQL có thể trả execution errors với HTTP 200 | SOAP Fault có quy tắc transport/binding riêng |

Đừng dùng `GraphQlTester.errors().expect(...)` để kiểm SOAP Fault; dùng Spring Web Services test support như `MockWebServiceClient`, XPath và kiểm SOAP Fault cho SOAP. Ngược lại, không áp dụng quy tắc HTTP status của SOAP để suy đoán GraphQL errors.

## 19. Lỗi thường gặp khi test GraphQL data/errors/nullability

**1. Chỉ assert HTTP status 200.**  
Resolver có thể lỗi và trả `data` partial với `errors`. Assert cả error list và data.

**2. Dùng `path("data.book.id")` trong GraphQlTester.**  
`GraphQlTester.path` bắt đầu tại `data`, nên dùng `path("book.id")`.

**3. Lẫn tên `isNull()` với `valueIsNull()`.**  
Spring GraphQL 1.x `GraphQlTester.Path` dùng `valueIsNull()` và `pathDoesNotExist()`. Kiểm API đúng version.

**4. Đồng nhất missing field với JSON null.**  
Một field không được select sẽ không có trong response; một field được select và nullable có thể là null. Test cả hai khi schema contract quan trọng.

**5. Thấy `book:null` rồi kết luận bản ghi không tồn tại.**  
`book` cũng có thể bị null do child Non-Null lỗi. Đọc `errors.path` để phân biệt.

**6. Thấy `errors.path=["book","title"]` nhưng mong `data.book.title` vẫn có null.**  
Khi `title:String!` lỗi, `book` nullable sẽ bị null cả object; field title không còn tồn tại dưới book.

**7. Kiểm `[Book!]!` như `[Book]`.**  
Với `[Book!]!` một item hỏng có thể làm `data:null`; với `[Book]` chỉ phần tử đó null.

**8. Hardcode thứ tự errors array.**  
Một query có nhiều field có thể resolve song song. So tập path/code và assert count, không tùy tiện dựa vào error index.

**9. Assert message lỗi nội bộ chính xác.**  
Spring GraphQL có thể che exception. Test domain error codes tự định nghĩa và path, không assert stacktrace hoặc execution ID.

**10. Dùng `filter(...)` để chứng minh một lỗi bắt buộc tồn tại.**  
`filter` cho phép không có lỗi nào. Dùng `expect(...)` hoặc `satisfy(...)` với count/path assertions.

**11. Dùng `satisfy(errors -> {})` rỗng.**  
Nó đánh dấu mọi error đã xử lý mà không chứng minh gì. Luôn assert số lượng và đặc điểm cần có.

**12. Quên GraphQlTester từ chối unexpected errors khi truy cập data path.**  
Với partial data lỗi có chủ đích, kiểm `errors` trước rồi mới `path(...)`. Với happy path, gọi `errors().verify()` minh bạch.

**13. Assert `hasValue()` cho empty list.**  
`hasValue()` yêu cầu non-null value hoặc list không rỗng. `[]` là hợp lệ; dùng `entityList(...).hasSize(0)`.

**14. Lẫn GraphQL ID với Java kiểu số.**  
GraphQL `ID` thường serialize thành string, kể cả nếu backend lưu number. Test theo GraphQL schema/response representation, không theo DB column type.

**15. Dùng mock cho chính resolver đang kiểm.**  
Mock controller/GraphQL source khiến test không chạy mapping. Mock collaborator `BookCatalog` trong slice, giữ `BookGraphQlController` thật.

**16. Kỳ vọng @GraphQlTest tự nạp mọi @Service.**  
Test slice có filters. Dùng `@MockitoBean`, test bean hoặc `@Import` có chủ đích; dùng integration test nếu cần service/repository thật.

**17. Nhầm request validation error với output Non-Null error.**  
Query không hợp lệ không chạy resolver và không có `data`; output Non-Null lỗi sau execution có thể trả `data:null`.

**18. Tưởng HTTP 4xx/5xx luôn là GraphQL error.**  
Security gateway, proxy và transport có thể trả HTML/text. Kiểm Content-Type/status trước khi deserialize như GraphQL response.

**19. Dựa vào message Java exception như public API.**  
Không nên lộ SQL, stacktrace, credentials. Error message/code phải có policy rõ; test tránh khẳng định message kỹ thuật riêng framework.

**20. Tin rằng test SDL nullability đủ bảo đảm dữ liệu sạch ở DB.**  
GraphQL executor có thể phát hiện vi phạm lúc request, nhưng bug dữ liệu vẫn có thể tồn tại. Thêm validation/domain persistence tests để ngăn dữ liệu invalid sớm.

## 20. Quy trình kiểm thử một GraphQL query có độ tin cậy cao

1. **Đọc SDL trước:** xác định field nào nullable/Non-Null và list items có thể null không.
2. **Định nghĩa operation thật:** gồm query name, variables, alias, selection set.
3. **Chọn tầng test:** `@GraphQlTest` cho resolver/schema; HTTP integration cho protocol và raw response.
4. **Chuẩn bị fixture:** happy path, not found, nullable null, resolver error, Non-Null violation, list item lỗi.
5. **Assert no-error path:** data fields + `errors().verify()`.
6. **Assert null hợp lệ:** `valueIsNull()` + không có errors.
7. **Assert omitted field:** `pathDoesNotExist()` khi field không được select.
8. **Assert error execution:** `errors().expect(...)` hoặc `satisfy(...)` với path chính xác và số lỗi.
9. **Assert bubbling:** parent/list/root là null **ở đúng mức** theo SDL; sibling có còn không?
10. **Assert alias/list index:** parsed path với alias và integer index 0-based.
11. **Kiểm request validation error riêng:** không có `data`, resolver không bị gọi, transport status theo contract.
12. **Không phụ thuộc internal messages/order:** ưu tiên domain error codes, parsed path, non-leakage.
13. **Kiểm HTTP thật khi cần:** Content-Type, status, JSON `data`/`errors`; đảm bảo test không phụ thuộc DB production.
14. **Kiểm DataLoader/transaction/security ở tầng riêng:** không suy luận từ một GraphQlTester slice test.
15. **Chạy CI ổn định:** version tương thích, dữ liệu deterministic, random port/timeout hợp lý.

### Checklist trước khi commit

- [ ] Đã phân biệt `data:null` với thiếu key `data`.
- [ ] Đã phân biệt field absent với field có JSON null.
- [ ] Data path dùng `GraphQlTester.path` không có tiền tố `data.`.
- [ ] Error path dùng `getParsedPath()` để kiểm strings và integer index.
- [ ] Alias làm thay đổi tên root field trong error path.
- [ ] Khi có intentional execution error, test kiểm errors trước khi đi vào data.
- [ ] Khi không mong lỗi, test khẳng định không có unexpected errors.
- [ ] SDL `T!`, `[T]`, `[T!]`, `[T]!`, `[T!]!` được hiểu và test đúng mức null propagation.
- [ ] List rỗng `[]` không bị coi là null hoặc error.
- [ ] Request errors, resolver errors, Non-Null errors có test riêng.
- [ ] Test không hardcode message/internal error IDs hoặc thứ tự lỗi không được cam kết.
- [ ] Mã lỗi nghiệp vụ trong `extensions` chỉ assert khi API thật có policy đó.
- [ ] Spring test slice giữ resolver thật và mock đúng collaborator.
- [ ] HTTP integration test kiểm cả transport lẫn raw JSON GraphQL.
- [ ] Không log secrets, tokens, SQL hoặc dữ liệu nhạy cảm trong GraphQL errors.
- [ ] Có test ở domain/DB/security layer nếu rủi ro nằm ngoài GraphQL schema.

**Ghi nhớ:** trong GraphQL, một field trả `null` **không đủ** để biết nó bị lỗi hay không; phải đặt nó cạnh **SDL nullability** và **`errors.path`**. Khi field Non-Null lỗi, `null` có thể lan tới object, list hoặc toàn bộ `data`, nhưng `errors.path` vẫn chỉ vị trí sâu nơi lỗi bắt đầu. `GraphQlTester` giúp kiểm data paths và expected errors rõ ràng; HTTP integration test xác nhận chính xác JSON response khi phần dữ liệu bị hủy bởi null propagation.

### Tài liệu tham khảo chính thức

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html): `GraphQlTester`, `errors().expect/filter/satisfy/verify` và các transports.
- [Spring for GraphQL 1.3.x — GraphQlTester.Path API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html): `hasValue`, `valueIsNull`, `pathDoesNotExist`, `entity` và `entityList`.
- [Spring for GraphQL 1.3.x — GraphQlTester.Errors API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html): `expect` vs `filter`, `satisfy`, `verify`.
- [Spring GraphQL ResponseError API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/ResponseError.html): `getPath`, `getParsedPath`, `getExtensions`, `getLocations`.
- [Spring Boot 3.5 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@GraphQlTest`, dependency injection và `HttpGraphQlTester`.
- [GraphQL Specification — Response](https://spec.graphql.org/September2025/#sec-Response): `data`/`errors`, field errors, error paths và request errors.
- [GraphQL Specification — Handling Execution Errors](https://spec.graphql.org/September2025/#sec-Handling-Execution-Errors): Non-Null bubbling qua object/list/root.
- [GraphQL Java — Data Fetching](https://graphql-java.com/documentation/data-fetching/): default PropertyDataFetcher và cách lấy POJO fields.
- [GraphQL.org — Response](https://graphql.org/learn/response/): partial data, execution errors và top-level response keys.
