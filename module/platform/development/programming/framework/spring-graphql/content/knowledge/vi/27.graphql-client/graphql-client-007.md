# Retrieve một field với Spring GraphQL Client

GraphQL client gửi một operation mô tả các field cần lấy, sau đó đọc dữ liệu từ response theo cấu trúc của selection set. Spring for GraphQL cung cấp API `GraphQlClient` để thực hiện việc đó theo cách không phụ thuộc transport. Khi chỉ cần một field trong response, `retrieve(path)` cho phép chọn đúng field và chuyển nó thành kiểu Java mong muốn mà không cần tự đọc toàn bộ response envelope.

Ví dụ, client có thể yêu cầu `book.title` rồi nhận trực tiếp một `String`, hoặc yêu cầu `book` với một số field con rồi ánh xạ thành DTO. `retrieve` là bước đọc dữ liệu từ response; selection set trong GraphQL document mới quyết định server được yêu cầu trả về những field nào. Hai bước này phải khớp nhau.

Sau bài này, bạn có thể:

- Tạo `GraphQlClient` cho HTTP transport.
- Viết GraphQL document chỉ chọn field cần thiết.
- Dùng variables thay cho nối chuỗi vào query.
- Đọc một scalar hoặc nested field bằng `retrieve(path)`.
- Ánh xạ object và list thành Java DTO.
- Hiểu path khi dùng alias, nested object và list.
- Xử lý field null, field error và partial data.
- Biết khi nào nên dùng `execute()` thay vì `retrieve()`.
- Kiểm thử client bằng Reactor Test.

## 1. GraphQL field và selection set

GraphQL không gửi một lệnh `SELECT` riêng cho từng cột. Client gửi một operation với selection set mô tả field cần lấy. Server trả về đúng cấu trúc field đã chọn, có thể gồm field lồng nhau.

Ví dụ schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    subtitle: String
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Nếu client chỉ cần tiêu đề sách, operation chỉ chọn `title`:

```graphql
query BookTitle($id: ID!) {
    book(id: $id) {
        title
    }
}
```

Response có cấu trúc:

```json
{
  "data": {
    "book": {
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

Nếu cần cả tác giả, client phải khai báo selection set bên trong object `author`:

```graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            name
        }
    }
}
```

Object field cần selection set; scalar field như `title` thì không có block con. Chọn field đúng nhu cầu giúp giảm lượng dữ liệu truyền qua mạng và tránh yêu cầu server phân giải những field không dùng đến.

## 2. GraphQlClient là API client dùng chung

`GraphQlClient` là API client của Spring for GraphQL. Nó cung cấp cách xây dựng request, gắn document/variables, thực thi operation và đọc response. Các transport client có thể triển khai API này, ví dụ:

- `HttpGraphQlClient` gửi request qua HTTP.
- `WebSocketGraphQlClient` dùng WebSocket cho GraphQL message, thường phù hợp với subscription.
- `RSocketGraphQlClient` dùng RSocket khi ứng dụng triển khai transport đó.

Các bước `document(...)`, `variable(...)`, `retrieve(...)` và `execute()` được dùng nhất quán ở mức `GraphQlClient`, còn cấu hình kết nối phụ thuộc transport.

Trong bài này, ví dụ sử dụng HTTP vì query lấy một field thường là request/response thông thường.

## 3. Tạo HttpGraphQlClient

Tạo một `WebClient` trỏ tới endpoint GraphQL rồi dùng nó để xây dựng `HttpGraphQlClient`:

```java
WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
        .build();
```

`HttpGraphQlClient` sử dụng `WebClient` để gửi GraphQL request qua HTTP. Có thể cấu hình timeout, TLS, proxy, authentication và các filter trên `WebClient` theo yêu cầu của ứng dụng.

Nếu ứng dụng đã có một `WebClient` được cấu hình chung, có thể tái sử dụng builder/client đó thay vì tạo thêm một cấu hình kết nối không đồng nhất. Với endpoint yêu cầu bearer token, hãy gắn credential từ nguồn đáng tin cậy bằng cơ chế phù hợp của ứng dụng; không hard-code token vào source code hoặc GraphQL document.

## 4. Retrieve một scalar field

Khi operation chỉ lấy một scalar field, `retrieve(path)` chọn field đó trong response và `toEntity(...)` chuyển giá trị sang kiểu Java:

```java
Mono<String> title = graphQlClient.document("""
        query BookTitle($id: ID!) {
            book(id: $id) {
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.title")
    .toEntity(String.class);
```

Ở đây:

- `document(...)` cung cấp GraphQL operation.
- `variable("id", "book-42")` gắn giá trị cho `$id`.
- `retrieve("book.title")` chọn field `title` nằm bên trong response key `book`.
- `toEntity(String.class)` yêu cầu chuyển giá trị field thành `String`.

Kết quả là `Mono<String>` vì `GraphQlClient` dùng kiểu reactive. Client có thể subscribe để nhận kết quả hoặc kết hợp với pipeline Reactor.

Không cần deserialize toàn bộ response thành một class chỉ để lấy một chuỗi. `retrieve` là cách ngắn gọn khi caller chỉ quan tâm một field và không cần kiểm tra những phần khác của GraphQL response.

## 5. Retrieve nested object thành DTO

Nếu cần nhiều field con, hãy chọn object ở path tương ứng và ánh xạ thành DTO:

```java
public record BookSummary(
        String id,
        String title) {
}
```

Operation:

```java
Mono<BookSummary> book = graphQlClient.document("""
        query BookSummary($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book")
    .toEntity(BookSummary.class);
```

Selection set trong document cần cung cấp những property mà DTO cần ánh xạ. Nếu DTO có field `subtitle` nhưng query không chọn `subtitle`, client không thể mong đợi server tự trả field đó.

Tên property và kiểu dữ liệu trong DTO nên tương thích với JSON response. Có thể dùng DTO riêng cho từng use case thay vì ánh xạ toàn bộ domain entity vào response client.

## 6. Retrieve một field từ object có nhiều cấp

Path có thể đi qua nhiều cấp object:

```graphql
query BookAuthor($id: ID!) {
    book(id: $id) {
        author {
            name
        }
    }
}
```

Lấy riêng tên tác giả:

```java
Mono<String> authorName = graphQlClient.document("""
        query BookAuthor($id: ID!) {
            book(id: $id) {
                author {
                    name
                }
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.author.name")
    .toEntity(String.class);
```

Path `book.author.name` phản ánh cấu trúc response JSON. Mỗi segment string là một response key ở cấp tương ứng. Không thể yêu cầu `book.author.name` nếu document chỉ chọn `book { id }`; path phải trỏ đến field mà operation thực sự chọn.

Nếu một parent object là null, field con phía dưới không có giá trị để đọc. Với field nullable, client cần xác định semantics phù hợp: dữ liệu không có, resource không tồn tại hay field bị lỗi. Khi cần phân biệt những tình huống này, hãy đọc full response thay vì chỉ dùng shortcut `retrieve`.

## 7. Retrieve field có alias

Alias đổi response key nhưng không đổi tên field trong schema. Vì `retrieve(path)` đọc response tree, path phải dùng alias.

Operation:

```graphql
query {
    featuredBook: book(id: "book-42") {
        displayTitle: title
    }
}
```

Path cần dùng:

```java
Mono<String> title = graphQlClient.document("""
        query {
            featuredBook: book(id: "book-42") {
                displayTitle: title
            }
        }
        """)
    .retrieve("featuredBook.displayTitle")
    .toEntity(String.class);
```

Không dùng `book.title` trong trường hợp này vì response không có key `book` hoặc `title`; response key là `featuredBook` và `displayTitle`.

Alias đặc biệt hữu ích khi một operation truy vấn cùng field nhiều lần với argument khác nhau:

```graphql
query Compare {
    newest: books(sort: NEWEST) {
        title
    }
    popular: books(sort: POPULAR) {
        title
    }
}
```

Client có thể retrieve `newest` hoặc `popular` riêng, hoặc dùng `execute()` để đọc cả hai nhánh.

## 8. Retrieve một field có argument

Argument là dữ liệu đầu vào của field, còn path là vị trí response cần đọc. Hãy dùng variables để truyền argument:

```java
Mono<BookSummary> book = graphQlClient.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", bookId)
    .retrieve("book")
    .toEntity(BookSummary.class);
```

Không nối trực tiếp `bookId` vào GraphQL document bằng string concatenation. Variables giữ document ổn định, giúp tránh lỗi escape chuỗi, giảm nguy cơ injection do tạo document sai cách và làm request dễ cache/quan sát hơn.

Nếu field có nhiều argument, mỗi argument có thể được truyền bằng `.variable(...)` nếu operation khai báo variable tương ứng:

```graphql
query SearchBooks($keyword: String!, $limit: Int!) {
    searchBooks(keyword: $keyword, limit: $limit) {
        id
        title
    }
}
```

```java
Mono<List<BookSummary>> books = graphQlClient.document("""
        query SearchBooks($keyword: String!, $limit: Int!) {
            searchBooks(keyword: $keyword, limit: $limit) {
                id
                title
            }
        }
        """)
    .variable("keyword", "spring")
    .variable("limit", 10)
    .retrieve("searchBooks")
    .toEntityList(BookSummary.class);
```

## 9. Retrieve một phần tử hoặc danh sách

Nếu path trỏ đến một list, có thể ánh xạ các phần tử thành list DTO:

```java
Mono<List<BookSummary>> books = graphQlClient.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .retrieve("books")
    .toEntityList(BookSummary.class);
```

`toEntityList(BookSummary.class)` ánh xạ từng phần tử trong list. Nếu response list rỗng, kết quả là một list rỗng theo semantics của collection mapping; không cần tự tạo một DTO giả để biểu diễn không có phần tử.

Nếu chỉ muốn lấy phần tử ở một vị trí cụ thể, path có thể dùng cú pháp truy cập phần tử được hỗ trợ bởi field path của Spring GraphQL, nhưng thường nên retrieve cả list rồi chọn phần tử trong Java để code rõ ràng và tránh phụ thuộc index có thể thay đổi.

Ví dụ lấy list rồi chọn phần tử đầu tiên:

```java
Mono<BookSummary> firstBook = books
        .flatMapMany(Flux::fromIterable)
        .next();
```

Hoặc xử lý list trong pipeline:

```java
Mono<List<String>> titles = books.map(items ->
        items.stream().map(BookSummary::title).toList());
```

## 10. Path là response path, không phải schema coordinate

`retrieve(path)` chọn field theo response structure. Path chịu ảnh hưởng bởi alias và nested selection set, tương tự `errors[].path` trong GraphQL response.

| GraphQL document | Retrieve path |
| --- | --- |
| `book { title }` | `book.title` |
| `featured: book { title }` | `featured.title` |
| `book { writer: author { name } }` | `book.writer.name` |
| `books { id title }` | `books` |
| `newest: books { title }` | `newest` |

Không dùng tên Java method resolver hoặc tên class làm path. Path không phải `Book.author` hay `Query.book`; nó là đường dẫn key trong JSON response.

Nếu query có alias, hãy đọc đúng alias trong path. Nếu đổi alias trong document mà quên đổi path, client có thể không tìm thấy field dù server đã trả dữ liệu đúng.

## 11. Retrieve và GraphQL errors

`retrieve(path)` là shortcut cho trường hợp caller cần một field cụ thể. Nếu field đó có lỗi GraphQL liên quan, quá trình chuyển field thành entity có thể ném `FieldAccessException`. Exception cung cấp thông tin về response field và các GraphQL error liên quan.

Ví dụ xử lý lỗi field:

```java
Mono<String> title = graphQlClient.document("""
        query {
            book(id: "missing") {
                title
            }
        }
        """)
    .retrieve("book.title")
    .toEntity(String.class)
    .onErrorMap(FieldAccessException.class, exception ->
            new BookQueryException("Could not retrieve book title", exception));
```

Đừng giả định mọi lỗi GraphQL đều làm mọi field thất bại. Một operation có thể trả partial data: field `book.title` thành công trong khi field khác có lỗi. `retrieve("book.title")` tập trung vào field được chọn; nếu cần quyết định dựa trên toàn bộ `errors`, hãy dùng `execute()`.

Không bắt `RuntimeException` chung rồi chuyển thành giá trị mặc định mà không phân biệt lỗi transport, lỗi GraphQL và lỗi mapping. Cách đó có thể che mất sự cố server hoặc lỗi hợp đồng dữ liệu.

## 12. Khi nào dùng execute() thay vì retrieve()?

`retrieve(path)` phù hợp khi caller cần một field và muốn ánh xạ trực tiếp. `execute()` phù hợp khi cần kiểm soát toàn bộ GraphQL response:

```java
Mono<ClientGraphQlResponse> responseMono = graphQlClient.document("""
        query BookAndRecommendations($id: ID!) {
            book(id: $id) {
                id
                title
            }
            recommendations {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .execute();
```

Có thể đọc nhiều field và kiểm tra errors:

```java
public record BookDashboard(
        BookSummary book,
        List<BookSummary> recommendations,
        List<?> errors) {
}

Mono<BookDashboard> dashboard = responseMono.map(response -> {
    ClientResponseField bookField = response.field("book");
    ClientResponseField recommendationsField = response.field("recommendations");

    BookSummary book = bookField.hasErrors()
            ? null
            : bookField.toEntity(BookSummary.class);
    List<BookSummary> recommendations = recommendationsField.hasErrors()
            ? List.of()
            : recommendationsField.toEntityList(BookSummary.class);

    return new BookDashboard(book, recommendations, response.getErrors());
});
```

Đoạn code minh họa việc đọc các field độc lập và giữ danh sách lỗi ở cấp response. Ứng dụng thực tế có thể chọn kiểu kết quả riêng cho từng field lỗi; điểm quan trọng là kiểm tra `hasErrors()` trước khi gọi `toEntity` nếu muốn giữ partial data. Có thể kiểm tra `response.getErrors()` để xem toàn bộ lỗi của operation.

Chọn `execute()` khi:

- Cần đọc nhiều field trong cùng response.
- Cần kiểm tra toàn bộ `errors` hoặc `extensions`.
- Cần giữ partial data khi một nhánh khác lỗi.
- Cần phân biệt field bị omitted, null và lỗi.
- Cần truy cập metadata response hoặc viết logic xử lý lỗi riêng.

## 13. Phân biệt field null, omitted và field error

Một field có thể không có giá trị vì nhiều lý do:

- Server trả `null` theo schema và dữ liệu nghiệp vụ.
- Parent object là null nên nested field không xuất hiện.
- Field bị bỏ qua do directive hoặc selection set không yêu cầu nó.
- Field phát sinh execution error và GraphQL áp dụng null propagation.

Với `execute()`, có thể kiểm tra trạng thái của response field:

```java
Mono<Void> inspect = graphQlClient.document("""
        query {
            book(id: "book-42") {
                subtitle
            }
        }
        """)
    .execute()
    .doOnNext(response -> {
        ClientResponseField subtitle = response.field("book.subtitle");

        if (subtitle.isOmitted()) {
            // Field không có trong response selection/result.
        }
        else if (subtitle.hasErrors()) {
            // Field có GraphQL error liên quan.
        }
        else if (subtitle.getValue() == null) {
            // Field được trả về với giá trị null.
        }
        else {
            String value = subtitle.toEntity(String.class);
        }
    })
    .then();
```

Các trạng thái cần được hiểu theo response thực tế. Nếu field không được chọn trong document, đó không phải là yêu cầu dữ liệu bị server từ chối; nếu field nullable trả null, client không nên tự suy diễn rằng có lỗi. Nếu field có error, hãy đọc error path và code thay vì chỉ nhìn null.

## 14. Retrieve một field nullable

Giả sử schema khai báo:

```graphql
type Book {
    subtitle: String
}
```

`subtitle` có thể null. Với reactive API, `Mono` không thể phát một giá trị Java null. Tùy API mapping, giá trị null có thể được biểu diễn bằng `Mono.empty()` hoặc cần được kiểm tra trực tiếp qua response field.

Nếu ứng dụng cần phân biệt “subtitle không có” với “field bị lỗi”, dùng `execute()` và kiểm tra `ClientResponseField` thay vì chỉ dựa vào việc `Mono` không phát phần tử. Nếu chỉ cần một giá trị tùy chọn, có thể chuyển kết quả thành `Optional` ở boundary của ứng dụng sau khi đã xác định semantics.

Ví dụ kiểm tra trực tiếp:

```java
Mono<Optional<String>> subtitle = graphQlClient.document("""
        query {
            book(id: "book-42") {
                subtitle
            }
        }
        """)
    .execute()
    .map(response -> {
        ClientResponseField field = response.field("book.subtitle");
        if (field.hasErrors()) {
            throw new IllegalStateException("Could not retrieve book subtitle");
        }
        return Optional.ofNullable((String) field.getValue());
    });
```

Ví dụ trên minh họa cách chuyển một field nullable thành `Optional`. Trong code thực tế, có thể thay `IllegalStateException` bằng exception nghiệp vụ riêng và đính kèm các lỗi từ `field.getErrors()` để giữ thông tin chẩn đoán cần thiết.

## 15. Document inline và document đặt tên

Có thể truyền GraphQL document trực tiếp bằng `.document(...)`, phù hợp với query ngắn hoặc ví dụ đơn giản:

```java
graphQlClient.document("""
        query BookTitle($id: ID!) {
            book(id: $id) {
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.title")
    .toEntity(String.class);
```

Với operation được dùng lại nhiều lần, có thể lưu document trong resource và gọi `.documentName(...)`:

```java
graphQlClient.documentName("book-title")
        .variable("id", "book-42")
        .retrieve("book.title")
        .toEntity(String.class);
```

Document đặt tên giúp tách query khỏi Java code, dễ review và tái sử dụng. Cần bảo đảm resource được đặt ở vị trí mà cấu hình `GraphQlClient` có thể tìm thấy và tên document khớp với resource. Dù document inline hay đặt tên, path retrieve vẫn phải khớp response key của operation.

## 16. Kết hợp retrieve với Reactor pipeline

Vì client trả về `Mono` hoặc `Flux`, có thể kết hợp việc retrieve field với các operator Reactor:

```java
Mono<String> normalizedTitle = graphQlClient.document("""
        query BookTitle($id: ID!) {
            book(id: $id) {
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.title")
    .toEntity(String.class)
    .map(String::trim)
    .filter(title -> !title.isBlank());
```

Không gọi `.block()` trong WebFlux controller hoặc trong một reactive service đang xử lý request. Hãy trả `Mono` cho caller hoặc compose tiếp pipeline. Trong command-line tool, test đồng bộ hoặc ranh giới imperative, `block()` có thể được dùng có chủ đích với timeout phù hợp.

Nếu cần gọi nhiều operation độc lập, có thể kết hợp bằng `Mono.zip`, nhưng cần cân nhắc tải đồng thời và giới hạn request đến server. Không chạy hàng trăm query song song chỉ vì API client trả reactive type.

## 17. Authentication và header của client

HTTP GraphQL client thường cần gửi credential để server xác thực caller. Header có thể được cấu hình ở `WebClient`:

```java
WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.test/graphql")
        .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
        .build();
```

Ví dụ chỉ minh họa cơ chế header; trong ứng dụng thực tế, token cần được lấy từ OAuth2 client, token relay hoặc credential provider phù hợp. Không dùng `defaultHeader` với token người dùng thay đổi theo từng request trên một singleton client dùng chung, vì request của người dùng khác có thể bị gửi nhầm credential. Khi token khác nhau theo caller, hãy dùng cơ chế gắn header theo request hoặc tạo client có phạm vi phù hợp.

Không truyền access token trong GraphQL variables hoặc query string. HTTP authorization header và cơ chế bảo vệ secret cần được quản lý riêng với GraphQL document.

## 18. Kiểm thử retrieve field

Một integration test có thể gọi `GraphQlClient` tới server test và xác nhận field được ánh xạ đúng:

```java
@Test
void retrievesBookTitle() {
    StepVerifier.create(graphQlClient.document("""
            query BookTitle($id: ID!) {
                book(id: $id) {
                    title
                }
            }
            """)
        .variable("id", "book-42")
        .retrieve("book.title")
        .toEntity(String.class))
        .expectNext("Spring GraphQL in Practice")
        .verifyComplete();
}
```

Test này giả định `graphQlClient` đã được cấu hình trỏ tới ứng dụng test và fixture có sách `book-42`. `StepVerifier` kiểm tra kết quả reactive mà không cần gọi `.block()`.

Các trường hợp nên kiểm thử:

1. Retrieve một scalar field.
2. Retrieve nested object thành DTO.
3. Retrieve alias bằng response key đã đổi tên.
4. Retrieve list bằng `toEntityList`.
5. Truyền argument qua variables.
6. Field nullable trả null.
7. Field phát sinh GraphQL error và client nhận `FieldAccessException` hoặc error handling đã thiết kế.
8. Field khác có partial data trong khi một nhánh lỗi; dùng `execute()` để kiểm tra.
9. Request không hợp lệ và response errors.
10. Authorization header được gửi đúng theo request/caller.

Nếu mục tiêu là kiểm thử server resolver, dùng `GraphQlTester` phù hợp với server test. Nếu mục tiêu là kiểm thử `GraphQlClient`, hãy gọi qua client transport thực tế hoặc một HTTP test server để xác nhận cả request serialization và response mapping.

## 19. Những lỗi thường gặp

- **Chọn field trong retrieve nhưng quên chọn trong document:** server không trả field mà selection set không yêu cầu.
- **Dùng schema field name thay alias:** path không khớp response key.
- **Nhầm retrieve path với Java property path:** path là cấu trúc JSON GraphQL response.
- **Dùng `toEntity` cho list:** dùng `toEntityList` khi path trả về một mảng.
- **Dùng object DTO nhưng query chỉ chọn một vài field:** các property không được chọn sẽ không có dữ liệu.
- **Nối argument vào chuỗi query:** dễ sai escaping; dùng variables.
- **Bỏ qua field errors:** null có thể do dữ liệu vắng mặt hoặc do execution error.
- **Dùng `retrieve` khi cần nhiều nhánh/partial data:** dùng `execute()` để kiểm tra toàn response.
- **Gọi `.block()` trong reactive request flow:** có thể chặn thread và làm giảm lợi ích reactive.
- **Dùng token cố định trên singleton WebClient cho nhiều caller:** có nguy cơ gửi nhầm credential giữa người dùng.
- **Kiểm thử server bằng client API hoặc ngược lại:** chọn tester đúng tầng cần xác minh.
- **Giả định HTTP 200 nghĩa là mọi field thành công:** vẫn cần đọc GraphQL errors khi xử lý full response.

## 20. Quy trình retrieve một field

Khi cần đọc một field từ GraphQL server bằng Spring GraphQL Client, hãy thực hiện:

1. Xác định field và các argument cần thiết trong schema.
2. Viết operation với selection set chỉ gồm field cần dùng và các field con cần ánh xạ.
3. Khai báo variables cho argument thay vì nối chuỗi giá trị vào document.
4. Xác định response key; nếu dùng alias, path phải dùng alias.
5. Dùng `retrieve(path)` để chọn field trong response.
6. Dùng `toEntity(...)` cho scalar/object hoặc `toEntityList(...)` cho list.
7. Nếu cần xử lý partial data, nhiều field, null/omitted hoặc toàn bộ errors, dùng `execute()`.
8. Xử lý lỗi field bằng `FieldAccessException` hoặc policy riêng; không nuốt mọi exception.
9. Compose `Mono`/`Flux` mà không block trong reactive flow.
10. Kiểm thử request, variables, path, DTO mapping, errors và authentication qua transport thực tế.

`retrieve(path)` là cách ngắn gọn để lấy một field cụ thể từ GraphQL response bằng Spring GraphQL Client. Selection set quyết định server trả field nào, còn path chọn response key cần ánh xạ thành scalar, object hoặc list Java. Khi dùng variables cho argument, lưu ý alias trong path và chuyển sang `execute()` khi cần kiểm soát partial data hoặc errors, client có thể đọc dữ liệu chính xác mà vẫn giữ được semantics của GraphQL response.

## Tài liệu tham khảo

- [Spring for GraphQL — GraphQL Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — GraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.html)
- [Spring for GraphQL — HttpGraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/HttpGraphQlClient.html)
- [Spring for GraphQL — ClientGraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientGraphQlResponse.html)
- [Project Reactor — Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/)
