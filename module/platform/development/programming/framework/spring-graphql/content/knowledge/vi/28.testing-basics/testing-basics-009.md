# Assert data với GraphQlTester trong Spring for GraphQL

`GraphQlTester` cung cấp API fluent để gửi một GraphQL operation, chọn field trong response và kiểm tra dữ liệu nhận được. Thay vì so sánh toàn bộ JSON response bằng chuỗi, test có thể đi đến đúng path cần kiểm tra rồi assert scalar, object, list, giá trị null hoặc GraphQL errors.

`GraphQlTester` dùng chung một workflow cho nhiều transport. Cùng một cách viết assertion có thể chạy với HTTP, WebSocket, RSocket hoặc gọi trực tiếp GraphQL service trong server. Bài này tập trung vào việc assert **data** trả về: dữ liệu có đúng giá trị, đúng cấu trúc, đúng số lượng và đúng hành vi khi một field không có dữ liệu hay phát sinh lỗi.

## 1. Thêm dependency kiểm thử

Thêm module `spring-graphql-test` ở test scope:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

Khi dùng Spring Boot dependency management, để Boot quản lý phiên bản tương thích với Spring GraphQL. Nếu không dùng BOM của Boot, cần khai báo phiên bản `spring-graphql-test` khớp với phiên bản `spring-graphql` của ứng dụng.

Một số assertion JSON yêu cầu thư viện JSONassert trên test classpath. Chỉ thêm dependency này khi dùng `matchesJson(...)` hoặc các assertion JSON cần thiết:

~~~groovy
dependencies {
    testImplementation("org.skyscreamer:jsonassert")
}
~~~

## 2. GraphQlTester cung cấp workflow chung

Một test GraphQL thường có bốn bước:

1. Tạo tester phù hợp với nơi muốn kiểm thử.
2. Tạo request bằng `document(...)` hoặc `documentName(...)`.
3. Thực thi bằng `execute()`.
4. Chọn response path và assert bằng `entity(...)`, `entityList(...)`, `matchesJson(...)` hoặc `valueIsNull()`.

~~~mermaid
flowchart TD
    A[GraphQlTester] --> B[document or documentName]
    B --> C[Set variables and headers]
    C --> D[execute]
    D --> E[Inspect errors if expected]
    E --> F[Select path relative to data]
    F --> G[Assert scalar, object, list or JSON]
~~~

Ví dụ đơn giản nhất:

~~~java
graphQlTester.document("{ greeting }")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, GraphQL!");
~~~

`path("greeting")` là đường dẫn tương đối với phần `data` trong GraphQL response. Không cần viết `data.greeting`.

## 3. Chọn loại GraphQlTester phù hợp

`GraphQlTester` là contract chung. Các builder khác nhau ở transport hoặc tầng server mà test đi qua:

| Tester | Phạm vi kiểm thử | Khi nên dùng |
| --- | --- | --- |
| `HttpGraphQlTester` | Gửi request qua HTTP bằng `WebTestClient` | Kiểm tra GraphQL endpoint và HTTP transport |
| `WebSocketGraphQlTester` | Gửi request qua một WebSocket connection | Kiểm tra WebSocket và subscription |
| `RSocketGraphQlTester` | Gửi request qua RSocket session | Kiểm tra RSocket transport và route |
| `ExecutionGraphQlServiceTester` | Gọi trực tiếp `ExecutionGraphQlService` | Kiểm tra server execution mà không cần transport |
| `WebGraphQlTester` | Đi qua `WebGraphQlHandler` và interceptor chain | Kiểm tra `WebGraphQlInterceptor` cùng GraphQL execution |

Nếu mục tiêu chỉ là assert dữ liệu resolver trả về, có thể dùng tester server-side để test nhanh. Nếu cần xác minh HTTP headers, status, WebSocket hoặc RSocket routing, dùng tester tương ứng với transport.

## 4. Dùng tester trong @GraphQlTest

Spring Boot cung cấp `@GraphQlTest` để tạo test slice cho GraphQL controller và các thành phần liên quan. Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    price: Float!
}
~~~

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookData() {
        given(bookService.findById("book-1"))
                .willReturn(new Book("book-1", "Spring GraphQL", 39.5));

        graphQlTester.document("""
                query BookById($id: ID!) {
                    book(id: $id) {
                        id
                        title
                        price
                    }
                }
                """)
                .variable("id", "book-1")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL");
    }
}
~~~

`@GraphQlTest` nạp GraphQL test slice và cho phép inject `GraphQlTester`. `@MockitoBean` thay service bằng mock để test tập trung vào việc bind argument, gọi resolver và tạo response. Với Spring Boot cũ chưa có `@MockitoBean`, dùng cơ chế mock bean được hỗ trợ bởi phiên bản Boot đó, chẳng hạn `@MockBean`.

## 5. Assert scalar bằng entity

Sau khi chọn path, dùng `entity(Class)` để decode giá trị sang kiểu Java rồi assert:

~~~java
graphQlTester.document("{ greeting }")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, GraphQL!");
~~~

Một số kiểu scalar thường dùng:

~~~java
response.path("book.id")
        .entity(String.class)
        .isEqualTo("book-1");

response.path("book.price")
        .entity(Double.class)
        .isEqualTo(39.5);

response.path("book.available")
        .entity(Boolean.class)
        .isEqualTo(true);
~~~

Chọn kiểu Java tương thích với scalar và cách mapping của ứng dụng. Ví dụ `Float` trong GraphQL thường được chuyển thành `Double` trong JSON mapping; không nên mặc định mọi số đều là `Integer`.

## 6. Assert object bằng entity

Khi response path là một object, có thể decode sang record hoặc DTO:

~~~java
public record BookView(String id, String title, Double price) {}
~~~

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                id
                title
                price
            }
        }
        """)
        .execute()
        .path("book")
        .entity(BookView.class)
        .satisfies(book -> {
            org.assertj.core.api.Assertions.assertThat(book.id())
                    .isEqualTo("book-1");
            org.assertj.core.api.Assertions.assertThat(book.title())
                    .isEqualTo("Spring GraphQL");
            org.assertj.core.api.Assertions.assertThat(book.price())
                    .isEqualTo(39.5);
        });
~~~

`isEqualTo(expected)` phù hợp khi muốn so sánh toàn bộ object và class có `equals` đúng như mong muốn. `satisfies(...)` phù hợp khi muốn assert một số thuộc tính mà không cần tạo object expected hoàn chỉnh.

`entity(...)` trả về entity assertion object; gọi `get()` nếu cần lấy giá trị đã decode để dùng tiếp trong test. Hạn chế lấy giá trị quá sớm nếu có thể assert trực tiếp trong fluent chain.

## 7. Assert list bằng entityList

Với list scalar, chọn JSONPath có wildcard `[*]` và dùng `entityList`:

~~~java
graphQlTester.document("""
        {
            books {
                title
            }
        }
        """)
        .execute()
        .path("books[*].title")
        .entityList(String.class)
        .containsExactly("Spring GraphQL", "GraphQL in Action");
~~~

`EntityList` hỗ trợ các assertion phổ biến:

~~~java
response.path("books[*].title")
        .entityList(String.class)
        .hasSize(2)
        .contains("Spring GraphQL");

response.path("books[*].title")
        .entityList(String.class)
        .doesNotContain("Unknown Book");
~~~

Một số method hữu ích:

| Method | Ý nghĩa |
| --- | --- |
| `hasSize(n)` | List có đúng `n` phần tử |
| `hasSizeGreaterThan(n)` | Số phần tử lớn hơn `n` |
| `hasSizeLessThan(n)` | Số phần tử nhỏ hơn `n` |
| `contains(...)` | Có chứa các giá trị mong đợi, không yêu cầu thứ tự |
| `containsExactly(...)` | Có đúng các giá trị theo đúng thứ tự |
| `doesNotContain(...)` | Không chứa các giá trị chỉ định |
| `singleElement()` | Assert list có đúng một phần tử rồi tiếp tục assert phần tử đó |

Với list object, decode từng phần tử thành DTO:

~~~java
graphQlTester.document("{ books { id title price } }")
        .execute()
        .path("books")
        .entityList(BookView.class)
        .hasSize(2)
        .satisfies(books -> {
            org.assertj.core.api.Assertions.assertThat(books)
                    .extracting(BookView::title)
                    .containsExactly("Spring GraphQL", "GraphQL in Action");
        });
~~~

## 8. Assert nested path

JSONPath của `GraphQlTester` mặc định bắt đầu từ phần `data`. Có thể chọn path lồng nhau:

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                title
                author {
                    name
                }
            }
        }
        """)
        .execute()
        .path("book.author.name")
        .entity(String.class)
        .isEqualTo("Ada Lovelace");
~~~

Nếu cần kiểm tra nhiều path dưới cùng một object, dùng callback overload:

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                title
                author { name }
            }
        }
        """)
        .execute()
        .path("book", book -> {
            book.path("title")
                    .entity(String.class)
                    .isEqualTo("Spring GraphQL");
            book.path("author.name")
                    .entity(String.class)
                    .isEqualTo("Ada Lovelace");
        });
~~~

Callback giúp các assertion có cùng base path, tránh lặp lại prefix dài và giúp cấu trúc test gần với cấu trúc response.

## 9. Assert toàn bộ JSON của object

Khi muốn kiểm tra nhiều field cùng lúc, dùng `matchesJson(...)`:

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                id
                title
                price
            }
        }
        """)
        .execute()
        .path("book")
        .matchesJson("""
                {
                    "id": "book-1",
                    "title": "Spring GraphQL",
                    "price": 39.5
                }
                """);
~~~

`matchesJson` so sánh JSON theo quy tắc JSONassert. Nó hữu ích khi muốn kiểm tra cả cấu trúc object mà không cần tạo DTO expected. Thư viện JSONassert phải có trên classpath.

`matchesJsonStrictly(...)` là biến thể strict của JSON comparison. Dùng nó khi test cần kiểm tra chặt chẽ hơn về cấu trúc/array ordering; hãy xác nhận semantics của phiên bản JSONassert đang dùng. Nếu chỉ quan tâm một vài field, `path(...).entity(...)` thường làm test ít giòn hơn khi schema có thêm field mới.

## 10. Assert giá trị null và path không tồn tại

GraphQL phân biệt field có giá trị null với field không xuất hiện trong response. `GraphQlTester` cung cấp assertion riêng:

~~~java
graphQlTester.document("{ book(id: \"missing\") { id title } }")
        .execute()
        .path("book")
        .valueIsNull();
~~~

`valueIsNull()` xác nhận path có giá trị null. `pathDoesNotExist()` xác nhận path không tồn tại:

~~~java
response.path("book.internalNotes")
        .pathDoesNotExist();
~~~

Không dùng hai assertion này thay thế cho nhau. Field nullable có thể xuất hiện với giá trị `null`, trong khi field không được chọn trong selection set thường không xuất hiện trong response.

`hasValue()` kiểm tra path có giá trị khác null hoặc list không rỗng:

~~~java
response.path("book")
        .hasValue();
~~~

## 11. Truyền variables và dùng documentName

Nên dùng GraphQL variables thay vì ghép giá trị trực tiếp vào query string:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-1")
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-1");
~~~

Có thể lưu operation trong `src/test/resources/graphql-test/` với phần mở rộng `.graphql` hoặc `.gql`, rồi dùng `documentName(...)`:

~~~graphql
query BookById($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

~~~java
graphQlTester.documentName("bookById")
        .variable("id", "book-1")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Theo document source mặc định, tester tìm file trong `graphql-test/` trên classpath. Tách query ra file giúp dễ review, tái sử dụng và bật GraphQL syntax highlighting trong IDE.

## 12. Assert mutation không có response data

Nếu mutation chỉ trả về kết quả phụ hoặc không có data cần assert, dùng `executeAndVerify()` để thực thi và xác nhận response không có GraphQL errors:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-1")
        }
        """)
        .executeAndVerify();
~~~

Nếu mutation trả về object hoặc scalar, dùng `execute()` và assert path như query:

~~~java
graphQlTester.document("""
        mutation ArchiveBook($id: ID!) {
            archiveBook(id: $id) {
                id
                archived
            }
        }
        """)
        .variable("id", "book-1")
        .execute()
        .path("archiveBook.archived")
        .entity(Boolean.class)
        .isEqualTo(true);
~~~

## 13. Assert errors cùng partial data

GraphQL có thể trả `data` một phần và `errors` cùng lúc. Khi test mong đợi lỗi, cần khai báo hoặc kiểm tra lỗi trước khi đi đến data path.

**Cách 1: expect lỗi cụ thể**

~~~java
graphQlTester.document("{ book(id: \"book-1\") { title author { name } } }")
        .execute()
        .errors()
        .expect(error -> error.getMessage().contains("Author service unavailable"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

`expect(...)` yêu cầu có ít nhất một error thỏa predicate. Nếu không tìm thấy error phù hợp, assertion thất bại. `verify()` kiểm tra không còn lỗi ngoài dự kiến, sau đó test tiếp tục assert data.

**Cách 2: filter lỗi dự kiến**

~~~java
graphQlTester.document("{ book(id: \"book-1\") { title author { name } } }")
        .execute()
        .errors()
        .filter(error -> error.getMessage().contains("Author service unavailable"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

`filter(...)` cho phép bỏ qua error khớp predicate nhưng không bắt buộc error đó phải xuất hiện. Nếu muốn bảo đảm error có mặt, dùng `expect(...)`.

**Cách 3: kiểm tra toàn bộ errors bằng satisfy**

~~~java
graphQlTester.document("{ book(id: \"book-1\") { title author { name } } }")
        .execute()
        .errors()
        .satisfy(errors -> {
            org.assertj.core.api.Assertions.assertThat(errors)
                    .anyMatch(error -> error.getMessage()
                            .contains("Author service unavailable"));
        });
~~~

`errors().satisfy(...)` đưa toàn bộ errors vào callback và đánh dấu chúng đã được kiểm tra, cho phép tiếp tục truy cập data nếu cần.

Không gọi `path(...)` trước khi xử lý các errors mà test dự kiến. Nếu response có error chưa được kiểm tra, `GraphQlTester` sẽ báo assertion failure khi đi đến data path. Hành vi này giúp test không vô tình bỏ qua lỗi resolver.

## 14. Dùng errorFilter ở cấp tester

Nếu nhiều test đều có một loại error có thể bỏ qua theo chủ đích, có thể đăng ký `errorFilter` khi tạo tester:

~~~java
WebGraphQlTester tester = WebGraphQlTester.builder(handler)
        .errorFilter(error -> error.getMessage().contains("known warning"))
        .build();
~~~

Filter cấp builder áp dụng cho mọi request qua tester đó. Dùng cẩn thận: filter quá rộng có thể che giấu lỗi thật trong nhiều test. Với lỗi chỉ được mong đợi ở một scenario, khai báo `.errors().expect(...)` hoặc `.filter(...)` ngay trong test giúp ý định rõ ràng hơn.

## 15. Assert subscription bằng StepVerifier

`executeSubscription()` trả stream response theo từng event. Dùng `StepVerifier` để kiểm tra giá trị, thứ tự và kết thúc stream:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void receivesGreetingEvents() {
    var greetingFlux = graphQlTester.document("subscription { greetings }")
            .executeSubscription()
            .toFlux("greetings", String.class);

    StepVerifier.create(greetingFlux)
            .expectNext("Hi")
            .expectNext("Bonjour")
            .expectNext("Hola")
            .verifyComplete();
}
~~~

`toFlux(path, type)` chọn một path trong data của từng subscription event và decode thành kiểu Java. Với stream không kết thúc tự nhiên, có thể dùng `thenCancel()` hoặc các bước kiểm tra thời gian phù hợp.

Subscription test được hỗ trợ qua `WebSocketGraphQlTester`, hoặc tester server-side `ExecutionGraphQlServiceTester` và `WebGraphQlTester`. Không nên giả định mọi transport tester đều có cùng khả năng subscription.

## 16. Tạo tester theo transport

**HTTP:** `HttpGraphQlTester` dùng `WebTestClient`, có thể chạy với mock server hoặc live server:

~~~java
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlTester tester = HttpGraphQlTester.create(webTestClient);
~~~

**WebSocket:**

~~~java
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

WebSocketClient webSocketClient = new ReactorNettyWebSocketClient();
WebSocketGraphQlTester tester = WebSocketGraphQlTester
        .builder("ws://localhost:8080/graphql", webSocketClient)
        .build();
~~~

**RSocket:**

~~~java
import java.net.URI;

import io.rsocket.transport.ClientTransport;
import io.rsocket.transport.netty.client.WebsocketClientTransport;
import org.springframework.graphql.test.tester.RSocketGraphQlTester;

URI uri = URI.create("wss://localhost:8080/rsocket");
ClientTransport transport = WebsocketClientTransport.create(uri);

RSocketGraphQlTester tester = RSocketGraphQlTester.builder()
        .clientTransport(transport)
        .route("graphql")
        .build();
~~~

**Server-side execution:**

~~~java
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);
~~~

**Qua interceptor chain:**

~~~java
import org.springframework.graphql.test.tester.WebGraphQlTester;

WebGraphQlTester tester = WebGraphQlTester.create(webGraphQlHandler);
~~~

Các ví dụ trên minh họa cách tạo tester; trong ứng dụng thực tế, inject các handler/service đã được Spring cấu hình. Nếu tester giữ connection/session, đóng nó sau test bằng `stop()` hoặc lifecycle tương ứng để giải phóng tài nguyên.

## 17. Timeout và document source

Có thể cấu hình timeout cho response để test không chờ vô hạn khi resolver hoặc downstream bị treo:

~~~java
import java.time.Duration;

GraphQlTester tester = GraphQlTester.builder(transport)
        .responseTimeout(Duration.ofSeconds(5))
        .build();
~~~

Builder cũng hỗ trợ `documentSource(...)` để thay đổi nơi tìm GraphQL document. Điều này hữu ích khi project lưu test query ở một thư mục classpath riêng hoặc dùng resource source tùy chỉnh.

Đặt timeout theo thời gian hợp lý của test suite. Timeout quá ngắn gây flaky test trên CI; timeout quá dài làm chậm feedback khi request thực sự bị treo.

## 18. Những lỗi thường gặp khi assert data

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy path | Path sai hoặc field không nằm trong selection set | Kiểm tra GraphQL document và dùng path tương đối với `data` |
| Test báo lỗi trước khi assert data | Response có GraphQL errors chưa được kiểm tra | Dùng `errors().expect/filter/satisfy` trước `path(...)` |
| JSONPath list trả rỗng | Thiếu wildcard hoặc sai tên field | Dùng path như `books[*].title` và kiểm tra response thực tế |
| Entity decode thất bại | DTO không tương thích response hoặc scalar mapping | Kiểm tra kiểu Java, constructor/record và selection set |
| So sánh object luôn thất bại | `equals` của DTO không phù hợp hoặc expected thiếu field | Dùng `satisfies(...)` để assert từng thuộc tính |
| JSON assertion không chạy | Thiếu JSONassert trên test classpath | Thêm dependency JSONassert hoặc dùng entity assertions |
| Test không kiểm tra error thật | Filter quá rộng hoặc chỉ gọi `satisfy` mà assertion quá yếu | Dùng `expect(...)` với predicate cụ thể và assert error count/code |
| Mutation không có data làm path lỗi | Mutation không trả field để assert | Dùng `executeAndVerify()` |
| Subscription test treo | Stream không hoàn tất hoặc thiếu cancel condition | Dùng `thenCancel()`, `take(n)` hoặc fixture kết thúc stream |
| Test phụ thuộc server đang chạy | Dùng tester qua transport live mà chưa khởi động server | Dùng server-side tester hoặc cấu hình test server/port rõ ràng |

## 19. Quy trình viết một data assertion tốt

Khi viết test cho GraphQL response:

1. Chọn tester theo phạm vi cần kiểm thử: resolver, interceptor hay transport.
2. Viết operation đúng selection set và dùng variables thay cho nối chuỗi input.
3. Gọi `execute()` để nhận response.
4. Nếu test mong đợi errors, khai báo `expect`, `filter` hoặc `satisfy` trước khi chọn data path.
5. Dùng `path(...)` với JsonPath tương đối với `data`.
6. Dùng `entity(...)` cho scalar/object và `entityList(...)` cho collection.
7. Dùng `matchesJson(...)` khi cần so sánh cấu trúc JSON; dùng `valueIsNull()` hoặc `pathDoesNotExist()` đúng semantics.
8. Với mutation không có data cần assert, dùng `executeAndVerify()`.
9. Với subscription, dùng `executeSubscription()` và `StepVerifier`.
10. Đặt timeout hợp lý và đóng tester giữ connection/session sau test.

`GraphQlTester` giúp test tập trung vào hợp đồng dữ liệu mà client GraphQL thực sự nhìn thấy. Khi chọn đúng path, decode đúng kiểu và kiểm tra cả errors khi cần, test sẽ phát hiện sai lệch trong resolver, schema và cách xử lý response mà không phải phụ thuộc vào một chuỗi JSON cố định.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [Spring for GraphQL — GraphQlTester.Path API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html)
- [Spring Boot — GraphQL testing support](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
