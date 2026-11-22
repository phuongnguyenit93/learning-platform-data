# Decode response trong Spring for GraphQL Client

Spring for GraphQL cung cấp **GraphQlClient** để gửi GraphQL request và giải mã response qua HTTP, WebSocket hoặc RSocket. Sau khi gửi document, client có thể chọn giải mã trực tiếp một field bằng **retrieve(path)** hoặc nhận toàn bộ **ClientGraphQlResponse** bằng **execute()** để tự kiểm tra dữ liệu, lỗi và metadata.

Chọn đúng cách giải mã rất quan trọng vì GraphQL cho phép trả dữ liệu một phần. Một response có thể chứa **data** hợp lệ cùng **errors** của một số field. Nếu client chỉ coi mọi **errors** là request thất bại, ứng dụng có thể bỏ mất dữ liệu vẫn sử dụng được. Ngược lại, nếu chỉ giải mã field mà không kiểm tra lỗi liên quan, client có thể nhầm **null** do lỗi với **null** hợp lệ.

## 1. GraphQlClient và các transport

**GraphQlClient** định nghĩa một workflow chung, độc lập với transport. Các implementation phổ biến gồm:

| Client | Transport | Đặc điểm |
| --- | --- | --- |
| **HttpGraphQlClient** | HTTP qua **WebClient** | Non-blocking, phù hợp ứng dụng reactive. |
| **HttpSyncGraphQlClient** | HTTP qua **RestClient** | Blocking, phù hợp luồng đồng bộ. |
| **WebSocketGraphQlClient** | WebSocket | Kết nối lâu dài, hỗ trợ subscription streaming. |
| **RSocketGraphQlClient** | RSocket | Request-response và streaming qua RSocket. |

Ví dụ tạo HTTP client:

~~~java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.create(webClient);
~~~

Cách gửi request và giải mã response sau khi tạo client là tương tự giữa các transport. Phần khác nhau chủ yếu nằm ở cấu hình kết nối, authentication, timeout và khả năng streaming.

## 2. Cấu trúc GraphQL response

Một GraphQL response thường có ba phần:

- **data**: kết quả của operation, có thể là object, list hoặc **null**.
- **errors**: danh sách lỗi nếu có; có thể tồn tại đồng thời với **data**.
- **extensions**: metadata bổ sung do server hoặc implementation cung cấp.

Ví dụ response thành công:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL"
    }
  }
}
~~~

Ví dụ response có partial data:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải thông tin tác giả",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ],
  "extensions": {
    "traceId": "trace-abc-123"
  }
}
~~~

Trong ví dụ thứ hai, field **author** bị lỗi nhưng thông tin **book.id** và **book.title** vẫn có thể sử dụng. Client cần đọc cả **data** và **errors** để quyết định cách xử lý.

## 3. Hai cách giải mã: retrieve và execute

**GraphQlClient.RequestSpec** cung cấp hai hướng chính:

| Cách gọi | Kết quả | Khi nên dùng |
| --- | --- | --- |
| **retrieve(path)** | **RetrieveSpec**, giải mã một field cụ thể | Chỉ cần một field và muốn code ngắn gọn. |
| **execute()** | **Mono<ClientGraphQlResponse>** | Cần kiểm tra toàn response, partial data, errors hoặc extensions. |
| **retrieveSync(path)** | Giải mã một field theo kiểu blocking | Dùng với client đồng bộ. |
| **executeSync()** | **ClientGraphQlResponse** trực tiếp | Cần toàn response trong luồng blocking. |

**retrieve** là shortcut của **execute**: nó lấy field theo path bên dưới khóa **data**, sau đó giải mã field đó sang kiểu Java mong muốn. Nếu cần quyết định theo từng lỗi hoặc cần giữ lại dữ liệu một phần, hãy dùng **execute**.

## 4. Giải mã một field bằng retrieve

Giả sử schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    isbn: String
}
~~~

Java DTO:

~~~java
public record Book(
        String id,
        String title,
        String isbn) {
}
~~~

Gửi query và giải mã field **book**:

~~~java
String document = """
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
                isbn
            }
        }
        """;

Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "book-10")
        .retrieve("book")
        .toEntity(Book.class);
~~~

**retrieve("book")** chỉ định đường dẫn tương đối với khóa **data** trong response. **toEntity(Book.class)** giải mã giá trị tại path đó thành **Book**.

Có thể tách request thành biến để tái sử dụng:

~~~java
var request = graphQlClient.document(document)
        .variable("id", "book-10");

Mono<Book> result = request
        .retrieve("book")
        .toEntity(Book.class);
~~~

Nếu document có nhiều operation, dùng **operationName(...)** để chọn operation cần chạy:

~~~java
Mono<Book> result = graphQlClient.document(documentWithMultipleOperations)
        .operationName("FindBook")
        .variable("id", "book-10")
        .retrieve("book")
        .toEntity(Book.class);
~~~

## 5. Path của field và alias

Path trong **retrieve** được tính từ **data**, dùng dấu chấm để đi qua field lồng nhau và có thể dùng chỉ số mảng:

~~~java
.retrieve("book")
.retrieve("book.author")
.retrieve("book.reviews[0]")
.retrieve("book.reviews[0].rating")
~~~

Ví dụ response:

~~~json
{
  "data": {
    "catalog": {
      "featured": {
        "id": "book-10",
        "title": "Spring for GraphQL"
      }
    }
  }
}
~~~

Path cần dùng là **catalog.featured**.

Nếu query dùng alias, path phải dùng tên alias xuất hiện trong response:

~~~graphql
query {
    featuredBook: book(id: "book-10") {
        id
        title
    }
}
~~~

Giải mã bằng:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .retrieve("featuredBook")
        .toEntity(Book.class);
~~~

Path không phải tên field trong schema nếu alias đã đổi tên field trong response. Khi xử lý lỗi, **errors.path** cũng sử dụng alias vì nó chỉ đến vị trí trong response.

## 6. Giải mã danh sách với toEntityList

Khi field trả về list, dùng **toEntityList** để giải mã từng phần tử:

~~~graphql
type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

~~~java
Mono<List<Book>> books = graphQlClient.document("""
        query BooksByAuthor($authorId: ID!) {
            booksByAuthor(authorId: $authorId) {
                id
                title
                isbn
            }
        }
        """)
        .variable("authorId", "author-7")
        .retrieve("booksByAuthor")
        .toEntityList(Book.class);
~~~

**toEntityList(Book.class)** trả **Mono<List<Book>>**, không phải **Flux<Book>**. Server trả một GraphQL response chứa một list; client giải mã list đó thành một Java **List**.

Nếu field có giá trị **null** nhưng không có lỗi liên quan, **toEntityList** trả về list rỗng. Nếu field không có trong response hoặc field có lỗi liên quan, thao tác truy cập có thể phát **FieldAccessException**.

## 7. Giải mã kiểu generic bằng ParameterizedTypeReference

Khi kiểu đích chứa generic lồng nhau, **Class<T>** không giữ đủ thông tin kiểu ở runtime. Dùng **ParameterizedTypeReference<T>**:

~~~java
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;

Mono<Map<String, Object>> bookMap = graphQlClient.document(document)
        .retrieve("book")
        .toEntity(new ParameterizedTypeReference<Map<String, Object>>() {});
~~~

Có thể dùng kiểu generic cho list hoặc wrapper:

~~~java
public record PageResult<T>(
        List<T> content,
        int page,
        int totalPages) {
}
~~~

~~~java
Mono<PageResult<Book>> page = graphQlClient.document(pageDocument)
        .retrieve("bookPage")
        .toEntity(new ParameterizedTypeReference<PageResult<Book>>() {});
~~~

Cấu trúc Java phải tương thích với dữ liệu JSON mà GraphQL trả về. Nếu DTO có constructor, record component hoặc property không phù hợp, quá trình decode có thể thất bại dù GraphQL response hợp lệ.

## 8. Giải mã theo kiểu đồng bộ

Với **HttpSyncGraphQlClient**, có thể dùng **retrieveSync**:

~~~java
import org.springframework.graphql.client.HttpSyncGraphQlClient;
import org.springframework.web.client.RestClient;

RestClient restClient = RestClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpSyncGraphQlClient syncClient =
        HttpSyncGraphQlClient.create(restClient);

Book book = syncClient.document(document)
        .variable("id", "book-10")
        .retrieveSync("book")
        .toEntity(Book.class);
~~~

**retrieveSync** trả kết quả trực tiếp và có thể ném exception ngay tại chỗ nếu field không thể truy cập hoặc decode.

Với **HttpGraphQlClient**, **retrieve(...).toEntity(...)** trả **Mono<T>**. Không gọi **block()** trong WebFlux event-loop hoặc trong một pipeline reactive chỉ để lấy giá trị đồng bộ. Hãy tiếp tục compose bằng các operator Reactor.

## 9. Khi nào cần execute()?

**retrieve** tiện lợi khi chỉ cần một field. Tuy nhiên, nó không cung cấp cách kiểm tra toàn bộ response trước khi giải mã. Dùng **execute()** khi cần:

- Kiểm tra request có hợp lệ hay không.
- Phân biệt request errors với field errors.
- Giữ lại partial data khi một field con thất bại.
- Đọc **extensions** hoặc nhiều field khác nhau trong cùng response.
- Tự quyết định field nào có thể fallback và field nào phải dừng.
- Xử lý **null** có chủ đích khác với **null** do lỗi.

Ví dụ:

~~~java
Mono<ClientGraphQlResponse> responseMono = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute();
~~~

**execute()** trả **Mono<ClientGraphQlResponse>**. Với client đồng bộ, dùng **executeSync()** để nhận response trực tiếp.

## 10. Kiểm tra isValid()

**ClientGraphQlResponse** kế thừa **GraphQlResponse**, trong đó có **isValid()**.

Response được xem là không hợp lệ nếu:

- Không có khóa **data**, thường là lỗi trước execution như parse hoặc validation error.
- Có khóa **data** nhưng giá trị **data** là **null**, ví dụ lỗi execution khiến toàn bộ data bị null do null propagation.

Response hợp lệ có khóa **data** với giá trị khác null. Response vẫn có thể chứa **errors** và một số field có giá trị null do field resolver thất bại.

| Response | isValid() | Ý nghĩa |
| --- | --- | --- |
| Không có **data**, chỉ có **errors** | **false** | Request error trước khi có kết quả data. |
| **data: null** và có errors | **false** | Execution không tạo được data hợp lệ. |
| **data** là object/list, không có errors | **true** | Kết quả không có lỗi GraphQL. |
| **data** là object/list, có field errors | **true** | Có partial data và lỗi ở một hoặc nhiều field. |

**Không dùng isValid() như cờ “không có lỗi”.** Nếu cần biết response có lỗi hay không, kiểm tra thêm **getErrors()**.

Ví dụ:

~~~java
Mono<String> title = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute()
        .map(response -> {
            if (!response.isValid()) {
                throw new IllegalStateException(
                        "GraphQL request không tạo được data hợp lệ: "
                                + response.getErrors());
            }

            if (!response.getErrors().isEmpty()) {
                // Response có partial data và field errors.
                // Có thể ghi nhận mã lỗi hoặc xử lý theo path.
            }

            // Chỉ giải mã title; lỗi ở field khác không làm mất title.
            return response.field("book.title").toEntity(String.class);
        });
~~~

Đoạn code minh họa việc kiểm tra trạng thái. Trong ứng dụng thực tế, nên dùng exception domain riêng hoặc trả về kết quả bao gồm cả data và errors thay vì ném **IllegalStateException** cho mọi trường hợp.

## 11. Phân biệt request errors và field errors

**getErrors()** trả về danh sách **ResponseError**. Có thể phân biệt theo **path**:

- Request errors áp dụng cho toàn operation và thường có path rỗng.
- Field errors gắn với một vị trí cụ thể trong response; path chứa tên field và có thể chứa chỉ số list.

Ví dụ request error:

~~~json
{
  "errors": [
    {
      "message": "Cannot query field 'unknownField' on type 'Query'."
    }
  ]
}
~~~

Không có **data**, nên response không hợp lệ.

Ví dụ field error:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ]
}
~~~

Có **data** khác null nên response vẫn hợp lệ. Lỗi chỉ gắn với **book.author**; các field khác vẫn có thể dùng được.

Có thể đọc error metadata:

~~~java
import java.util.Map;

response.getErrors().forEach(error -> {
    String message = error.getMessage();
    String path = error.getPath();
    Map<String, Object> extensions = error.getExtensions();

    log.warn("GraphQL field error path={} message={} extensions={}",
            path, message, extensions);
});
~~~

**ResponseError.getParsedPath()** trả các segment của path, gồm tên field và chỉ số list dạng số nguyên. **getLocations()** trả vị trí trong GraphQL document nếu có. **getExtensions()** chứa metadata riêng của server hoặc GraphQL implementation; không nên giả định mọi server đều trả cùng một cấu trúc.

## 12. Phân biệt field null hợp lệ và field null do lỗi

Một field nullable có thể trả **null** hợp lệ mà không có lỗi. Ví dụ một sách chưa được gán tác giả:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "author": null
    }
  }
}
~~~

Trường hợp khác, resolver lỗi khiến field trở thành null:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"]
    }
  ]
}
~~~

Nếu chỉ kiểm tra **getValue() == null**, client không phân biệt được hai trường hợp. Hãy kiểm tra cả **getErrors()**:

~~~java
ClientResponseField authorField = response.field("book.author");

if (authorField.getValue() == null) {
    if (authorField.getErrors().isEmpty()) {
        // Null là kết quả hợp lệ theo schema/nghiệp vụ.
    }
    else {
        // Field null do lỗi; xử lý error hoặc fallback.
    }
}
else {
    Author author = authorField.toEntity(Author.class);
}
~~~

Đây là một trong những lý do quan trọng để dùng **execute()** khi ứng dụng cần kiểm soát partial response.

## 13. ClientResponseField và giải mã từng phần

**response.field(path)** trả về **ClientResponseField**, cho phép đọc và giải mã field cụ thể.

Các method hữu ích:

| Method | Mục đích |
| --- | --- |
| **getValue()** | Lấy raw value của field. |
| **getPath()** | Lấy path dạng chuỗi. |
| **getParsedPath()** | Lấy path dưới dạng các segment. |
| **getErrors()** | Lấy các errors gắn với field. |
| **toEntity(Class<T>)** | Giải mã field thành một object. |
| **toEntity(ParameterizedTypeReference<T>)** | Giải mã field thành kiểu generic. |
| **toEntityList(Class<T>)** | Giải mã field thành list object. |

Ví dụ đọc nhiều field trong một response:

~~~java
public record BookSummary(String id, String title) {
}
~~~

~~~java
Mono<BookSummary> summary = graphQlClient.document("""
        query {
            book(id: "book-10") {
                id
                title
                author {
                    id
                    name
                }
            }
        }
        """)
        .execute()
        .map(response -> {
            if (!response.isValid()) {
                throw new IllegalStateException("GraphQL request failed");
            }

            String id = response.field("book.id").toEntity(String.class);
            String title = response.field("book.title").toEntity(String.class);

            return new BookSummary(id, title);
        });
~~~

Ví dụ này chỉ đọc các field cần thiết. Nếu query còn có field con lỗi nhưng **book.id** và **book.title** không bị ảnh hưởng, client vẫn có thể sử dụng chúng. Nếu muốn giải mã cả object **book**, cần xem xét lỗi gắn với **book** hoặc các field con của nó.

## 14. Giải mã toàn bộ response

**ClientGraphQlResponse.toEntity(...)** giải mã toàn bộ response map sang kiểu đích. Cách này hữu ích khi cần giữ cả wrapper **data**, **errors** hoặc **extensions**.

Ví dụ lấy response thành map:

~~~java
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;

Mono<Map<String, Object>> rawResponse = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute()
        .map(response -> response.toEntity(
                new ParameterizedTypeReference<Map<String, Object>>() {}));
~~~

Nếu chỉ cần phần **data**, dùng **getData()**:

~~~java
Mono<Map<String, Object>> data = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute()
        .map(ClientGraphQlResponse::getData);
~~~

**getData()** trả null khi response không hợp lệ theo định nghĩa **isValid()**. Khi cần xử lý lỗi, không nên bỏ qua **getErrors()** trước khi chỉ lấy data.

## 15. Đọc response extensions

GraphQL response có thể chứa **extensions** ở cấp response, ví dụ trace ID, query cost hoặc metadata riêng của server:

~~~json
{
  "data": {
    "books": []
  },
  "extensions": {
    "traceId": "trace-123",
    "queryCost": 18
  }
}
~~~

Đọc bằng:

~~~java
Mono<Map<Object, Object>> extensions = graphQlClient.document(document)
        .execute()
        .map(ClientGraphQlResponse::getExtensions);
~~~

Cần phân biệt:

- **response.getExtensions()** là metadata ở cấp response.
- **response.getErrors().get(i).getExtensions()** là metadata của một error cụ thể.

Các extension phụ thuộc server và protocol. Hãy kiểm tra key có tồn tại, kiểu dữ liệu có phù hợp và không gắn logic nghiệp vụ cốt lõi vào extension riêng nếu client cần tương thích với nhiều GraphQL server.

## 16. Các exception khi decode response

Không phải mọi lỗi đều có cùng nguyên nhân. **GraphQlClient** có các exception chính:

| Exception | Khi nào xảy ra | Cách xử lý |
| --- | --- | --- |
| **FieldAccessException** | Path không có trong response, response invalid hoặc field path có lỗi liên quan | Đọc **getResponse()** và **getField()** để xem response/error cụ thể. |
| **GraphQlClientException** | Lỗi client chung, bao gồm decode không chuyển được sang kiểu đích | Kiểm tra DTO, JSON shape và kiểu dữ liệu. |
| **GraphQlTransportException** | Lỗi transport hoặc lỗi trong encode/decode request/response ở transport | Kiểm tra network, HTTP status, media type và payload. |

Nếu field có mặt nhưng không thể decode sang kiểu Java yêu cầu, Spring for GraphQL ném **GraphQlClientException** thay vì **FieldAccessException**.

Ví dụ xử lý **FieldAccessException** trong pipeline reactive:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "book-10")
        .retrieve("book")
        .toEntity(Book.class)
        .onErrorResume(FieldAccessException.class, exception -> {
            ClientGraphQlResponse response = exception.getResponse();
            ClientResponseField field = exception.getField();

            log.warn("Cannot decode field path={} errors={}",
                    field.getPath(), field.getErrors());

            return Mono.empty();
        });
~~~

Ví dụ này chọn trả **Mono.empty()** khi field không thể truy cập. Trong ứng dụng thật, hãy chỉ fallback khi lỗi có thể chấp nhận; không nên biến mọi lỗi thành kết quả rỗng vì client sẽ khó phân biệt “không có dữ liệu” với “server trả lỗi”.

Với **execute()**, lỗi GraphQL nằm trong **ClientGraphQlResponse** không tự động trở thành reactive exception. Nhưng lỗi transport có thể làm **Mono** kết thúc bằng **GraphQlTransportException**.

## 17. Giữ lại partial data thay vì bỏ toàn bộ response

Một response hợp lệ có thể chứa dữ liệu hữu ích cùng field errors. Nếu dùng **retrieve("book")** và path **book** có lỗi ở field con, **FieldAccessException** có thể được phát ra vì lỗi nằm dưới path đang truy cập.

Khi cần giữ partial data, hãy dùng **execute()** và đọc từng field không bị lỗi:

~~~java
public record BookView(String id, String title, String authorName) {
}
~~~

~~~java
Mono<BookView> loadBookView(GraphQlClient client) {
    return client.document("""
            query {
                book(id: "book-10") {
                    id
                    title
                    author {
                        name
                    }
                }
            }
            """)
            .execute()
            .map(response -> {
                if (!response.isValid()) {
                    throw new IllegalStateException(
                            "GraphQL request không có data hợp lệ");
                }

                String id = response.field("book.id").toEntity(String.class);
                String title = response.field("book.title").toEntity(String.class);

                ClientResponseField authorField =
                        response.field("book.author.name");

                String authorName = null;
                if (authorField.getValue() != null
                        && authorField.getErrors().isEmpty()) {
                    authorName = authorField.toEntity(String.class);
                }

                return new BookView(id, title, authorName);
            });
}
~~~

Ở đây, lỗi của **book.author.name** không làm mất **book.id** và **book.title**. Client chủ động tạo view từ các field đọc được.

Ví dụ giả định **book** tồn tại và hai field **id**, **title** không bị lỗi. Nếu **book** có thể null hợp lệ, hãy kiểm tra **response.field("book")** trước khi đọc các field con.

Không nên bỏ qua lỗi một cách tùy tiện. Nếu field bị lỗi là dữ liệu bắt buộc cho nghiệp vụ, hãy trả lỗi domain hoặc yêu cầu retry thay vì tạo object có vẻ hợp lệ nhưng thiếu thông tin quan trọng.

## 18. Subscription response cũng có thể decode

Subscription trả về nhiều GraphQL responses theo thời gian. Với client transport hỗ trợ streaming, dùng **retrieveSubscription(path)** để giải mã một field trong từng response:

~~~java
Flux<BookEvent> events = webSocketGraphQlClient.document("""
        subscription {
            bookAdded {
                id
                title
            }
        }
        """)
        .retrieveSubscription("bookAdded")
        .toEntity(BookEvent.class);
~~~

Nếu cần xem errors và partial data của từng event, dùng **executeSubscription()**:

~~~java
Flux<ClientGraphQlResponse> responses = webSocketGraphQlClient.document("""
        subscription {
            bookAdded {
                id
                title
            }
        }
        """)
        .executeSubscription();
~~~

Mỗi phần tử của **Flux<ClientGraphQlResponse>** là một response event có thể được kiểm tra bằng **isValid()**, **getErrors()** và **field(path)**.

Luồng subscription có thể kết thúc bằng **SubscriptionErrorException** nếu server gửi thông báo lỗi cuối cùng, hoặc **WebSocketDisconnectedException** nếu kết nối bị mất. Đây là lỗi ở vòng đời stream/transport, khác với một event response chứa field errors.

## 19. Lỗi thường gặp khi decode response

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| **retrieve("book")** không tìm thấy field | Path sai hoặc query không select field đó | So sánh path với response data và alias. |
| **toEntity(Book.class)** phát **FieldAccessException** | Field có error, null do error hoặc response invalid | Dùng **execute()** để kiểm tra response và field errors. |
| Field null nhưng không có error | Null là giá trị hợp lệ hoặc resolver trả null | Kiểm tra **getErrors()** trước khi coi null là lỗi. |
| DTO không decode được | JSON shape hoặc kiểu property không tương thích | Kiểm tra DTO, constructor, generic type và scalar representation. |
| Có HTTP response nhưng client nhận **GraphQlTransportException** | Lỗi transport/HTTP/encode/decode | Kiểm tra status, Content-Type và transport logs. |
| **isValid()** true nhưng vẫn có errors | Response có partial data và field errors | Kiểm tra **getErrors()** riêng; không coi **isValid** là “không lỗi”. |
| **toEntityList** trả list rỗng | Field null nhưng không có error hoặc list thực sự rỗng | Phân biệt null và empty theo contract API nếu cần. |
| Field lỗi làm mất cả object khi dùng retrieve | Error nằm tại, phía trên hoặc bên dưới path được truy cập | Dùng **execute()** và decode từng field độc lập. |
| Subscription dừng đột ngột | Server terminal error hoặc transport mất kết nối | Phân biệt **SubscriptionErrorException** và **WebSocketDisconnectedException**. |

## 20. Kiểm thử decode response

Nên kiểm thử ít nhất các nhóm sau:

1. Field object giải mã đúng sang DTO bằng **retrieve(...).toEntity(...)**.
2. List giải mã đúng bằng **toEntityList(...)**.
3. Generic DTO giải mã đúng bằng **ParameterizedTypeReference**.
4. Alias và nested path được truy cập bằng response path.
5. Field null không lỗi được phân biệt với field null có lỗi.
6. Request errors làm **isValid()** trả false.
7. Partial data cùng field errors vẫn được giữ lại.
8. **FieldAccessException** cung cấp response và field để điều tra.
9. Decode sai kiểu được phân biệt với transport failure.
10. Response extensions được đọc mà không giả định luôn có mặt.
11. Subscription mỗi event được decode đúng và terminal errors được xử lý riêng.

Khi kiểm thử qua mock HTTP server hoặc integration environment, nên tạo các response mẫu có **data** đầy đủ, **data** partial, **errors** không có **data**, field null có/không có error và payload sai kiểu. Điều đó giúp kiểm tra cả behavior của decoder lẫn cách ứng dụng xử lý từng loại kết quả.

## 21. Checklist chọn cách decode

1. Chỉ cần một field và không cần xử lý toàn response: dùng **retrieve(path)**.
2. Cần list: dùng **toEntityList(elementType)**.
3. Cần generic type: dùng **ParameterizedTypeReference**.
4. Cần response metadata, nhiều field hoặc partial data: dùng **execute()**.
5. Cần blocking: dùng **retrieveSync** hoặc **executeSync** với client đồng bộ.
6. Dùng **isValid()** để nhận diện response không có data hợp lệ, không dùng nó như cờ không có errors.
7. Kiểm tra **getErrors()** để phân biệt request errors và field errors.
8. Kiểm tra **ClientResponseField.getErrors()** khi field có giá trị null.
9. Dùng **FieldAccessException.getResponse()** và **getField()** để xử lý lỗi truy cập field.
10. Phân biệt **GraphQlClientException** do decode với **GraphQlTransportException** do transport.
11. Với subscription, dùng **retrieveSubscription** hoặc **executeSubscription**.
12. Chỉ fallback khi dữ liệu thiếu có thể chấp nhận theo nghiệp vụ; không che giấu lỗi bắt buộc.

**retrieve** giúp giải mã nhanh một field theo path; **execute** cho phép kiểm soát toàn bộ response. Hiểu **isValid**, **errors**, **extensions**, field path và các exception của client giúp ứng dụng xử lý chính xác cả kết quả đầy đủ lẫn partial data. Khi chọn cách decode theo nhu cầu và kiểm tra lỗi đúng phạm vi, client Spring for GraphQL có thể tận dụng dữ liệu còn hợp lệ mà vẫn không bỏ qua lỗi thực sự.

Tài liệu tham khảo:
- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [GraphQlClient.RequestSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [GraphQlClient.RetrieveSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RetrieveSpec.html)
- [ClientGraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientGraphQlResponse.html)
- [ClientResponseField API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientResponseField.html)
- [GraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/GraphQlResponse.html)
