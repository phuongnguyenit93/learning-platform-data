# DocumentSource

Khi dùng Spring for GraphQL client, ứng dụng thường gửi đi nhiều GraphQL document lặp lại: query lấy chi tiết một quyển sách, mutation cập nhật hồ sơ hoặc subscription theo dõi trạng thái đơn hàng. Viết trực tiếp document trong từng lời gọi Java khiến code khó tái sử dụng, khó quản lý và khó kiểm tra thay đổi schema.

**DocumentSource** là abstraction để Spring GraphQL client tra cứu nội dung GraphQL document bằng một tên do ứng dụng đặt. Kết hợp với phương thức **documentName(...)**, client có thể tham chiếu một document theo tên, còn phần triển khai DocumentSource chịu trách nhiệm tìm nội dung tương ứng từ map, classpath hoặc một nguồn lưu trữ phù hợp.

Bài này trình bày vai trò và contract của DocumentSource, cách cấu hình nó với GraphQlClient, cách tổ chức document trong resource, cách dùng documentName cùng variables, phân biệt document name với operation name và persisted query, cách xử lý document không tồn tại, cache, bảo mật, kiểm thử và các lỗi thường gặp.

## 1. DocumentSource giải quyết vấn đề gì?

Một lời gọi GraphQL client có thể viết trực tiếp document:

~~~java
Mono<Book> book = graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .retrieve("book")
    .toEntity(Book.class);
~~~

Với document ngắn, cách này rõ ràng. Nhưng khi một ứng dụng có nhiều query và mutation, nội dung GraphQL có thể chiếm phần lớn code client và bị lặp lại ở nhiều service.

DocumentSource cho phép tách nội dung document ra khỏi nơi thực thi:

- Code gọi client chỉ tham chiếu tên document.
- Nguồn tài liệu chịu trách nhiệm tìm nội dung GraphQL tương ứng.
- Document có thể được lưu thành resource riêng, dễ review và tái sử dụng.
- Ứng dụng có thể thay đổi cách lưu document mà không cần sửa mọi lời gọi client.

Ví dụ:

~~~java
Mono<Book> book = graphQlClient.documentName("bookById")
        .variable("id", "book-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Ở đây bookById là tên tra cứu document do ứng dụng quy ước. DocumentSource chuyển tên đó thành chuỗi GraphQL document để client gửi tới server.

## 2. DocumentSource nằm ở đâu trong kiến trúc client?

Luồng xử lý cơ bản:

~~~mermaid
flowchart TD
    A[Application service] --> B[GraphQlClient.documentName]
    B --> C[DocumentSource]
    C --> D[GraphQL document text]
    D --> E[GraphQlClient RequestSpec]
    E --> F[Variables và operation]
    F --> G[HTTP / WebSocket / RSocket transport]
    G --> H[GraphQL server]
    H --> I[Client response]
~~~

DocumentSource hoạt động ở phía client, trước bước gửi request qua transport. Nó giải quyết câu hỏi: “Với tên document này, nội dung GraphQL cần gửi là gì?”

Các thành phần có vai trò riêng:

- **DocumentSource**: tra cứu document text theo tên.
- **documentName(...)**: yêu cầu GraphQlClient sử dụng document có tên tương ứng.
- **RequestSpec**: gắn variables, headers hoặc các tùy chọn request khác.
- **GraphQlClient transport**: gửi GraphQL request qua HTTP, WebSocket hoặc RSocket.
- **GraphQL server**: parse, validate và thực thi document nhận được.

DocumentSource không thực thi query và không phân tích kết quả. Nó chỉ cung cấp nội dung document cho client.

## 3. Contract của DocumentSource

DocumentSource là một strategy interface trong package org.springframework.graphql.client. Nó cho phép client yêu cầu nội dung document bằng một tên.

Có thể hình dung contract qua method:

~~~java
public interface DocumentSource {
    String getDocument(String documentName);
}
~~~

Ứng dụng có thể cung cấp implementation riêng để lấy document từ:

- Java Map được nạp khi khởi động.
- File resource trên classpath.
- Một thư mục document được đóng gói cùng ứng dụng.
- Một registry hoặc kho lưu trữ nội bộ đã được ứng dụng kiểm soát.

Đối với document tĩnh, classpath hoặc map thường là lựa chọn đơn giản và dễ kiểm soát. Không nên gọi database hoặc dịch vụ mạng đồng bộ trong mỗi lần getDocument nếu có thể nạp trước và cache nội dung.

Nếu tên document không được tìm thấy, implementation nên báo lỗi rõ ràng. Không trả chuỗi rỗng hoặc một document mặc định vì điều đó có thể khiến client gửi nhầm operation và tạo lỗi khó chẩn đoán.

## 4. Cấu hình DocumentSource với GraphQlClient

GraphQlClient builder cho phép cấu hình DocumentSource dùng khi request gọi documentName(...).

Ví dụ tạo một nguồn document từ map:

~~~java
Map<String, String> documents = Map.of(
        "bookById", """
                query BookById($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """,
        "books", """
                query Books {
                    books {
                        id
                        title
                    }
                }
                """
);

DocumentSource documentSource = documentName -> {
    String document = documents.get(documentName);
    if (document == null) {
        throw new IllegalArgumentException(
                "Không tìm thấy GraphQL document: " + documentName);
    }
    return document;
};

GraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
        .documentSource(documentSource)
        .build();
~~~

Trong ví dụ:

- Map lưu document text theo key.
- DocumentSource tra cứu nội dung từ map.
- documentSource(...) gắn strategy vào builder.
- Client sử dụng cùng nguồn document cho các request có tên.

Nếu ứng dụng dùng WebSocketGraphQlClient hoặc RSocketGraphQlClient, nguyên tắc cấu hình DocumentSource ở GraphQlClient builder vẫn tương tự; transport chỉ thay đổi cách gửi request và nhận response.

### Đặt DocumentSource ở đâu?

Với ứng dụng Spring, có thể khai báo GraphQlClient như một bean:

~~~java
@Configuration
public class GraphQlClientConfiguration {

    @Bean
    GraphQlClient graphQlClient(
            WebClient webClient,
            DocumentSource documentSource) {

        return HttpGraphQlClient.builder(webClient)
                .documentSource(documentSource)
                .build();
    }
}
~~~

Ví dụ giả định ứng dụng đã cấu hình WebClient và cung cấp bean DocumentSource. Dùng một client được cấu hình tập trung giúp các service thống nhất transport, interceptor, timeout và nguồn document.

Không cần tạo một GraphQlClient mới cho mỗi query. Hãy tái sử dụng client bean và tạo RequestSpec riêng cho từng operation.

## 5. Tổ chức GraphQL document trên classpath

Một cách tổ chức phổ biến là lưu document trong src/main/resources:

~~~text
src/
  main/
    resources/
      graphql/
        bookById.graphql
        books.graphql
        createBook.graphql
        updateBook.graphql
~~~

Ví dụ file bookById.graphql:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

DocumentSource tùy chỉnh có thể đọc file từ classpath:

~~~java
@Component
public class ClasspathDocumentSource implements DocumentSource {

    private static final Pattern NAME_PATTERN =
            Pattern.compile("[A-Za-z0-9_-]+");

    private final ResourceLoader resourceLoader;

    public ClasspathDocumentSource(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    @Override
    public String getDocument(String documentName) {
        if (!NAME_PATTERN.matcher(documentName).matches()) {
            throw new IllegalArgumentException(
                    "Tên GraphQL document không hợp lệ");
        }

        Resource resource = resourceLoader.getResource(
                "classpath:graphql/" + documentName + ".graphql");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
        catch (IOException exception) {
            throw new IllegalArgumentException(
                    "Không thể đọc GraphQL document: " + documentName,
                    exception);
        }
    }
}
~~~

Các import cần thiết trong ví dụ gồm java.io.IOException, java.io.InputStream, java.nio.charset.StandardCharsets, java.util.regex.Pattern, org.springframework.core.io.Resource, org.springframework.core.io.ResourceLoader, org.springframework.stereotype.Component và org.springframework.graphql.client.DocumentSource.

Pattern giới hạn tên document vào một tập ký tự đơn giản. Điều này ngăn tên đầu vào chứa path segment như ../ khi implementation ghép tên vào classpath location.

Ví dụ này đọc resource mỗi lần được yêu cầu. Với document tĩnh, có thể nạp nội dung một lần khi khởi động và lưu trong map để tránh lặp thao tác I/O. Nếu dùng ClassPathResource trực tiếp, vẫn cần xử lý trường hợp resource không tồn tại và lỗi đọc file.

## 6. Dùng documentName trong request

Sau khi cấu hình DocumentSource, gọi documentName(...) thay cho document(...).

Ví dụ:

~~~java
Mono<Book> result = graphQlClient.documentName("bookById")
        .variable("id", "book-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Các bước:

1. documentName("bookById") yêu cầu client tra cứu document.
2. DocumentSource trả nội dung GraphQL document.
3. variable("id", "book-01") gắn giá trị variable.
4. retrieve("book") chọn field book trong response.
5. toEntity(Book.class) chuyển kết quả field thành Java object.

DocumentSource không thay đổi cách sử dụng variables hoặc response mapping. RequestSpec sau khi có document vẫn hỗ trợ các thao tác của GraphQlClient như request viết trực tiếp bằng document text.

### Tái sử dụng cùng document với nhiều variables

Một document có thể được dùng cho nhiều request:

~~~java
Mono<Book> first = graphQlClient.documentName("bookById")
        .variable("id", "book-01")
        .retrieve("book")
        .toEntity(Book.class);

Mono<Book> second = graphQlClient.documentName("bookById")
        .variable("id", "book-02")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Document text giữ nguyên, còn variables thay đổi theo request. Không nên nối trực tiếp giá trị người dùng vào GraphQL document. Dùng variables giúp tách cấu trúc operation khỏi dữ liệu đầu vào và tránh lỗi escaping.

## 7. Phân biệt document name và operation name

Hai khái niệm thường bị nhầm:

- **Document name**: tên nội bộ mà ứng dụng dùng để tra cứu document qua DocumentSource.
- **Operation name**: tên được khai báo bên trong GraphQL document sau từ khóa query, mutation hoặc subscription.

Ví dụ file được tra cứu bằng tên bookById:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

Ở đây:

| Giá trị | Vai trò |
|---|---|
| bookById | Document name dùng trong documentName("bookById") |
| BookById | Operation name trong GraphQL document |
| book | Root field được chọn trong operation |
| id | Variable của operation |

Document name có thể khác operation name. DocumentSource không tự đổi tên operation bên trong document.

Một document có thể chứa nhiều operation. Khi gửi document đó, client và GraphQL server cần biết operation nào được chọn theo quy tắc GraphQL request. Để đơn giản và dễ quản lý, mỗi file document dùng với documentName thường nên chứa một operation được đặt tên rõ ràng.

## 8. DocumentSource khác persisted query như thế nào?

DocumentSource là cơ chế tra cứu nội dung ở phía client. Khi client gọi documentName("bookById"), DocumentSource thường trả chuỗi GraphQL đầy đủ để GraphQlClient gửi trong request.

Persisted query là một cơ chế khác: client và server phối hợp nhận diện operation đã được đăng ký hoặc lưu trước, thường thông qua hash hoặc identifier. Server có thể không cần nhận toàn bộ query text trong mỗi request nếu protocol persisted-query được triển khai.

| Tiêu chí | DocumentSource | Persisted query |
|---|---|---|
| Nơi tra cứu chính | Client application | Server hoặc hệ thống registry dùng chung |
| Input tra cứu | Document name do client quy ước | ID/hash theo protocol |
| Kết quả tra cứu | GraphQL document text cho client | Query đã đăng ký hoặc được nhận diện ở server |
| Có tự động giảm payload request? | Không | Có thể, tùy protocol |
| Có tự tạo allowlist phía server? | Không | Chỉ khi server thực thi chính sách allowlist |
| Mục đích chính | Tổ chức và tái sử dụng document trong client | Quản lý/nhận diện query ở phía server |

DocumentSource không tự bật Automatic Persisted Queries, không tạo hash và không đăng ký query trên server. Nếu hệ thống cần persisted query hoặc allowlist operation, cần triển khai protocol và server-side enforcement riêng.

## 9. DocumentSource không phải operation registry bảo mật

Việc client chỉ gọi các tên document đã biết có thể giúp code client có tổ chức. Nhưng nó không ngăn một client khác gửi query tùy ý tới GraphQL endpoint.

Ví dụ:

- Ứng dụng mobile có thể chỉ dùng documentName từ danh sách đã đóng gói.
- Một công cụ khác vẫn có thể gửi raw GraphQL document qua HTTP.
- GraphQL server vẫn phải kiểm tra authentication, authorization, validation và query limits.

Nếu muốn giới hạn operation, server cần kiểm tra persisted query ID hoặc allowlist đã được triển khai và cấu hình đúng. Không dùng DocumentSource như ranh giới bảo mật.

## 10. Xử lý document không tồn tại

Một tên document sai có thể do:

- Gõ sai key khi gọi documentName.
- File resource chưa được đóng gói vào classpath.
- Tên file khác với convention của DocumentSource.
- Resource bị đổi tên hoặc xóa nhưng code client chưa cập nhật.
- DocumentSource chưa được cấu hình trên GraphQlClient builder.

Nên phát hiện lỗi này sớm và cung cấp message có tên document:

~~~java
String document = documents.get(documentName);
if (document == null) {
    throw new IllegalArgumentException(
            "Không tìm thấy GraphQL document: " + documentName);
}
~~~

Không trả về document rỗng để request tiếp tục. Nếu document không tồn tại, đây là lỗi cấu hình hoặc lập trình phía client; không phải GraphQL execution error từ server.

Nếu implementation đọc classpath resource, hãy phân biệt:

- Resource không tồn tại.
- Resource tồn tại nhưng không đọc được.
- Resource có nội dung rỗng.
- Document text có cú pháp GraphQL sai.

DocumentSource chỉ có trách nhiệm đọc nội dung. Parse và validate GraphQL vẫn do server thực hiện khi nhận request, trừ khi client tự bổ sung bước kiểm tra riêng.

## 11. Cache và vòng đời document

GraphQL document thường là nội dung tĩnh, vì vậy không cần đọc file từ disk cho mỗi request.

Một số chiến lược:

| Cách lưu | Khi phù hợp | Lưu ý |
|---|---|---|
| Map bất biến | Số document ít và đã biết khi build | Dễ kiểm soát và nhanh |
| Nạp classpath khi khởi động | Document nằm trong resources | Phát hiện file thiếu khi startup |
| Cache theo tên | Nguồn đọc có chi phí nhưng document có thể thay đổi | Cần chính sách invalidation |
| Registry ngoài ứng dụng | Nhiều client dùng chung catalog | Cần xử lý availability và version |

Với classpath resources, có thể nạp document vào map trong constructor hoặc bean initialization. Sau đó DocumentSource chỉ tra cứu map.

Không nên truy vấn database hoặc gọi remote registry đồng bộ trên mỗi request nếu document đã có thể cache. Nếu document có thể thay đổi trong runtime, hãy xác định rõ:

- Cache TTL hoặc invalidation.
- Version của document.
- Cách triển khai rollback khi document mới không tương thích server.
- Hành vi khi registry tạm thời không khả dụng.

## 12. Versioning và tổ chức document

Document thường phụ thuộc schema server. Khi server đổi field hoặc argument, client document có thể cần cập nhật.

Một số cách tổ chức:

~~~text
graphql/
  book/
    bookById.graphql
    books.graphql
    createBook.graphql
  author/
    authorById.graphql
  order/
    orderStatus.graphql
~~~

DocumentSource có thể dùng key có namespace, ví dụ book.bookById hoặc map key theo quy ước của dự án.

Không nên để nhiều document có cùng key vì một request có thể vô tình dùng nội dung khác theo thứ tự nạp. Tên document cần duy nhất trong phạm vi nguồn tra cứu.

Khi thay đổi document:

1. Review thay đổi GraphQL document cùng với thay đổi schema.
2. Kiểm tra variable type và field selection.
3. Kiểm tra Java response mapping.
4. Chạy contract/integration test với server tương ứng.
5. Triển khai client/server theo thứ tự tương thích.

## 13. Bảo mật khi xây dựng DocumentSource

DocumentSource có thể đọc file hoặc truy cập registry, vì vậy tên document cần được kiểm soát.

Các nguyên tắc:

- Nếu backend dùng DocumentSource thay mặt caller bên ngoài, không cho caller tự do truyền document name để ứng dụng đọc file theo path; hãy ánh xạ tên qua danh sách cho phép.
- Không ghép tên chưa kiểm tra vào filesystem path hoặc classpath location.
- Dùng allowlist tên document nếu tên đến từ input không tin cậy.
- Không tải GraphQL document từ URL tùy ý do user cung cấp.
- Không lưu token hoặc secret trong GraphQL document.
- Không log toàn bộ document nếu document chứa literal nhạy cảm.
- Dùng GraphQL variables cho dữ liệu runtime thay vì nhúng trực tiếp vào document.

Trong kiến trúc thông thường, documentName là giá trị do code client đặt. Nếu ứng dụng mở API cho người dùng chọn tên document, hãy kiểm tra tên đó trong danh sách cho phép.

Một GraphQL document có thể được chia sẻ hoặc đóng gói trong ứng dụng, nhưng bản thân document không phải credential. Quyền truy cập dữ liệu vẫn phải được kiểm tra ở server.

## 14. Kết hợp DocumentSource với các loại GraphQlClient

GraphQlClient cung cấp abstraction chung cho các transport:

- **HttpGraphQlClient**: gửi request qua HTTP.
- **WebSocketGraphQlClient**: gửi request qua WebSocket.
- **RSocketGraphQlClient**: gửi request qua RSocket.

DocumentSource giải quyết việc lấy document trước khi transport gửi request. Vì vậy, cùng một nguồn document có thể dùng cho nhiều client nếu các client cùng hỗ trợ cấu hình DocumentSource.

Ví dụ HTTP:

~~~java
HttpGraphQlClient httpClient =
        HttpGraphQlClient.builder(webClient)
                .documentSource(documentSource)
                .build();
~~~

Ví dụ WebSocket:

~~~java
WebSocketGraphQlClient websocketClient =
        WebSocketGraphQlClient.builder(webSocketClient)
                .documentSource(documentSource)
                .build();
~~~

Tên builder và các cấu hình transport cụ thể phụ thuộc client implementation và phiên bản Spring for GraphQL. Điểm chung là document text được resolve trước khi request đi qua transport.

Một document chỉ có thể chạy trên transport phù hợp với loại operation và server endpoint. Ví dụ, Subscription cần transport có hỗ trợ streaming; DocumentSource không làm một HTTP JSON request thông thường trở thành subscription transport.

## 15. Kiểm thử DocumentSource

DocumentSource là thành phần nhỏ nên có thể unit test độc lập.

Ví dụ:

~~~java
class MapDocumentSource implements DocumentSource {

    private final Map<String, String> documents;

    MapDocumentSource(Map<String, String> documents) {
        this.documents = Map.copyOf(documents);
    }

    @Override
    public String getDocument(String documentName) {
        String document = documents.get(documentName);
        if (document == null) {
            throw new IllegalArgumentException(
                    "Không tìm thấy GraphQL document: " + documentName);
        }
        return document;
    }
}
~~~

Unit test:

~~~java
class MapDocumentSourceTest {

    private final DocumentSource source = new MapDocumentSource(
            Map.of("bookById", "query BookById { book { id } }"));

    @Test
    void shouldResolveDocumentByName() {
        assertThat(source.getDocument("bookById"))
                .contains("query BookById");
    }

    @Test
    void shouldFailForUnknownDocument() {
        assertThatThrownBy(() -> source.getDocument("missing"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("missing");
    }
}
~~~

Ngoài unit test cho source, nên kiểm thử GraphQlClient thực sự dùng document được resolve:

1. Cấu hình client với DocumentSource test.
2. Gọi documentName("bookById").
3. Gắn variables.
4. Kiểm tra transport nhận đúng GraphQL document text và variables.
5. Xác minh response được map đúng field.
6. Kiểm tra lỗi khi document name không tồn tại.

Có thể dùng mock HTTP server hoặc transport test double để xác minh request body. Test DocumentSource đơn lẻ chỉ xác nhận lookup; nó không xác nhận GraphQlClient builder đã sử dụng nguồn đó.

## 16. Những lỗi thường gặp khi dùng DocumentSource

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| documentName không tìm thấy document | Key không tồn tại hoặc sai convention | Kiểm tra tên và map/resource |
| Document classpath không đọc được | File chưa được đóng gói hoặc sai path | Kiểm tra resources và classpath location |
| Client gửi document rỗng | Source trả chuỗi rỗng khi lookup thất bại | Ném lỗi rõ ràng khi không tìm thấy |
| Request dùng operation khác mong muốn | Nhầm document name với operation name | Kiểm tra tên tra cứu và tên operation trong file |
| Variables không khớp | Document thay đổi nhưng code client chưa cập nhật | Đồng bộ document và request variables |
| Nhiều client dùng nội dung khác nhau | DocumentSource không được cấu hình thống nhất | Dùng bean/configuration chung |
| Mỗi request đều đọc file | Source thực hiện I/O mỗi lần lookup | Nạp trước hoặc cache document |
| Có thể đọc path ngoài thư mục | Ghép tên chưa kiểm tra vào resource path | Validate key hoặc dùng map allowlist |
| Nghĩ server đã bật persisted query | Nhầm lookup phía client với protocol server | Triển khai persisted-query/allowlist riêng |
| Query text lộ trong log | Log request body đầy đủ | Log metadata đã chọn lọc và không chứa secret |

## 17. Quy trình triển khai DocumentSource

Khi tổ chức GraphQL document cho client:

1. Xác định các query, mutation và subscription được tái sử dụng.
2. Tách document text thành resource hoặc map có tên ổn định.
3. Đặt operation name rõ ràng trong từng GraphQL document.
4. Tạo DocumentSource để tra cứu document theo tên.
5. Kiểm tra tên đầu vào và xử lý rõ trường hợp document không tồn tại.
6. Cấu hình DocumentSource trên GraphQlClient builder.
7. Dùng documentName(...) để tạo request.
8. Gắn variables riêng cho từng lần gọi.
9. Tái sử dụng GraphQlClient bean thay vì tạo client mới cho mỗi operation.
10. Cache document tĩnh và quản lý version khi schema thay đổi.
11. Không nhầm DocumentSource với persisted query hoặc server-side allowlist.
12. Kiểm thử lookup, missing document, request body và response mapping.

DocumentSource tách việc tìm nội dung GraphQL document khỏi code gửi request. Ứng dụng có thể dùng documentName để tham chiếu tài liệu theo tên và cung cấp nội dung từ map, classpath hoặc registry đã kiểm soát. Document name khác operation name bên trong GraphQL document; DocumentSource cũng không tự triển khai persisted query hay allowlist ở server. Hãy tổ chức document có version, dùng variables cho dữ liệu runtime, kiểm soát tên tra cứu, cache tài liệu tĩnh và kiểm thử cả bước lookup lẫn request thực tế để client luôn gửi đúng operation.
