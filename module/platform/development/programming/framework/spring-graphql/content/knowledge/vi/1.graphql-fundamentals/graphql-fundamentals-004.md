# Query, mutation và subscription trong Spring for GraphQL

GraphQL cung cấp ba loại operation chính để client trao đổi dữ liệu với server: **query** để đọc dữ liệu, **mutation** để thay đổi dữ liệu và **subscription** để nhận dữ liệu theo thời gian thực. Spring for GraphQL ánh xạ các operation này vào những method Java thông qua các annotation như `@QueryMapping`, `@MutationMapping` và `@SubscriptionMapping`.

Bài học này xây dựng một API quản lý sách nhỏ để minh họa cách khai báo schema, viết resolver, truyền biến, xử lý kết quả và kiểm thử từng loại operation.

## 1. Vai trò của ba loại operation

Một GraphQL request luôn thực thi operation được khai báo trong schema. Schema định nghĩa những field mà client có thể gọi, kiểu dữ liệu đầu vào và kiểu dữ liệu trả về.

| Operation | Mục đích | Ví dụ trong API sách |
| --- | --- | --- |
| Query | Đọc dữ liệu, không tạo side effect | Tìm một quyển sách theo ID, lấy danh sách sách |
| Mutation | Tạo, cập nhật hoặc xóa dữ liệu | Tạo một quyển sách mới |
| Subscription | Nhận một luồng kết quả khi có sự kiện | Nhận thông báo khi một quyển sách mới được tạo |

GraphQL quy ước ba root type có tên lần lượt là `Query`, `Mutation` và `Subscription`. `Query` là root type bắt buộc; hai root type còn lại chỉ cần khai báo khi API hỗ trợ mutation hoặc subscription.

Các operation được client gửi đến cùng một GraphQL endpoint. Với Spring Boot auto-configuration, HTTP endpoint thường là `/graphql` và có thể thay đổi bằng cấu hình. Tên operation, biến đầu vào và các field được chọn nằm trong nội dung request, vì vậy server không cần tạo một URL riêng cho từng truy vấn.

## 2. Khai báo schema bằng SDL

Trước khi viết Java resolver, cần mô tả API bằng Schema Definition Language (SDL). Ví dụ dưới đây định nghĩa các field đọc sách, tạo sách và theo dõi sách mới:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Subscription {
    bookCreated: Book!
}

type Book {
    id: ID!
    title: String!
    authorId: ID!
}

input CreateBookInput {
    title: String!
    authorId: ID!
}
~~~

Một số điểm cần chú ý:

- `ID!` nghĩa là client phải truyền ID và giá trị đó không được là `null`.
- `book(id: ID!): Book` cho phép kết quả là `null` nếu không tìm thấy sách. Điều này phù hợp với tình huống một ID hợp lệ về cú pháp nhưng không tồn tại trong hệ thống.
- `[Book!]!` nghĩa là danh sách không được `null`, đồng thời từng phần tử trong danh sách cũng không được `null`. Danh sách rỗng vẫn hợp lệ.
- `CreateBookInput` là input object dùng để gom các trường đầu vào của mutation. Input object giúp API dễ mở rộng khi thao tác tạo sách cần thêm thuộc tính.
- `Book` là output object; `CreateBookInput` là input object. GraphQL phân biệt hai loại này vì input object chỉ dùng làm dữ liệu đầu vào, không thể thay thế output object trong kiểu trả về.
- `bookCreated` trả về một `Book` cho mỗi sự kiện được phát ra. Khi triển khai subscription, method Java sẽ trả về một publisher phát nhiều giá trị theo thời gian.

Schema là hợp đồng giữa client và server. Nếu một field chưa được khai báo trong schema, client không thể yêu cầu field đó dù đối tượng Java có thuộc tính tương ứng.

## 3. Query: đọc dữ liệu

### 3.1. Viết query operation

Client chỉ định những field muốn nhận. Ví dụ, truy vấn một quyển sách theo ID:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
        authorId
    }
}
~~~

`FindBook` là tên operation, còn `$id` là biến có kiểu `ID!`. Giá trị biến được gửi riêng trong phần `variables`:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title authorId } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-101"
    }
}
~~~

Tách biến khỏi câu query giúp tái sử dụng cùng một operation với nhiều giá trị khác nhau, đồng thời tránh ghép dữ liệu người dùng trực tiếp vào chuỗi GraphQL.

Client cũng có thể lấy danh sách:

~~~graphql
query ListBooks {
    books {
        id
        title
    }
}
~~~

Server chỉ cần trả về dữ liệu cho các field được chọn. Nếu client không yêu cầu `authorId`, response không chứa field này. Cơ chế chọn field giúp client mô tả chính xác hình dạng dữ liệu cần nhận.

### 3.2. Ánh xạ query vào Spring for GraphQL

Spring for GraphQL sử dụng `@QueryMapping` để ánh xạ một method trong controller vào field của root type `Query`. Ví dụ model và input object có thể được biểu diễn bằng Java record:

~~~java
public record Book(
        String id,
        String title,
        String authorId
) {}

public record CreateBookInput(
        String title,
        String authorId
) {}
~~~

Controller xử lý hai field query như sau:

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

Trong ví dụ này:

- `@Controller` đăng ký class làm controller cho Spring for GraphQL.
- `@QueryMapping` ánh xạ method theo tên method vào field cùng tên của root type `Query`. Có thể truyền tên field vào annotation nếu tên method khác tên field.
- `@Argument("id")` lấy giá trị argument `id` từ query và chuyển đổi sang kiểu Java tương ứng.
- `bookService` giữ trách nhiệm truy cập dữ liệu và xử lý nghiệp vụ. Resolver nên điều phối lời gọi đến service thay vì chứa toàn bộ logic lưu trữ trong controller.

`@QueryMapping` là dạng rút gọn của `@SchemaMapping` với type name là `Query`. Khi cần ánh xạ field thuộc một object type khác, chẳng hạn field `author` của `Book`, có thể dùng `@SchemaMapping(typeName = "Book", field = "author")`.

### 3.3. Kết quả và nullability

Với query `book`, schema cho phép trả về `Book` hoặc `null`. Vì vậy, khi không tìm thấy ID, resolver có thể trả về `null` và response có dạng:

~~~json
{
    "data": {
        "book": null
    }
}
~~~

Nếu schema đổi thành `book(id: ID!): Book!`, kết quả `null` vi phạm hợp đồng non-null. GraphQL sẽ tạo lỗi thực thi và đẩy giá trị `null` lên field cha gần nhất có thể nhận `null`. Hiện tượng này thường được gọi là **null propagation** hoặc **null bubbling**.

Do đó, cần chọn dấu `!` theo cam kết thực tế của API. Chỉ khai báo non-null khi server có thể bảo đảm trả về giá trị trong mọi trường hợp hợp lệ; nếu không, hãy dùng kiểu nullable và xác định rõ cách client xử lý trường hợp không có dữ liệu.

Query nên chỉ phục vụ đọc dữ liệu. Không nên dùng query để tạo đơn hàng, cập nhật trạng thái hoặc thực hiện hành động có side effect. Các field query có thể được thực thi song song, nên việc đặt thay đổi trạng thái bên trong query có thể gây hành vi khó dự đoán.

## 4. Mutation: thay đổi dữ liệu

### 4.1. Thiết kế input và mutation

Mutation dùng cho thao tác làm thay đổi trạng thái hệ thống. Với API sách, thao tác tạo sách nhận một input object và trả về quyển sách vừa được tạo:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        authorId
    }
}
~~~

Biến đầu vào:

~~~json
{
    "input": {
        "title": "GraphQL thực hành",
        "authorId": "author-12"
    }
}
~~~

Dùng input object thay cho nhiều argument rời rạc giúp chữ ký mutation ổn định hơn. Khi cần thêm thuộc tính như `description` hoặc `publishedAt`, có thể mở rộng input theo chính sách tương thích của API.

### 4.2. Ánh xạ mutation trong Spring

`@MutationMapping` ánh xạ method vào field của root type `Mutation`. Có thể tiếp tục sử dụng controller ở phần query:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input
) {
    return bookService.create(input.title(), input.authorId());
}
~~~

`@Argument("input")` yêu cầu Spring chuyển input object của GraphQL thành `CreateBookInput`. `@Valid` kích hoạt Bean Validation nếu ứng dụng đã cấu hình Jakarta Bean Validation và input có các constraint phù hợp. Ví dụ có thể khai báo `@NotBlank` trên `title` để từ chối chuỗi rỗng hoặc chỉ chứa khoảng trắng.

Ví dụ input có validation:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId
) {}
~~~

Validation ở tầng input giúp phát hiện dữ liệu sai định dạng sớm. Service vẫn cần kiểm tra các quy tắc nghiệp vụ như author có tồn tại hay người dùng hiện tại có quyền tạo sách hay không. Không nên xem validation từ client là ranh giới bảo vệ dữ liệu.

### 4.3. Đặc điểm thực thi mutation

Các field cấp cao nhất trong cùng một mutation operation được GraphQL thực thi tuần tự theo thứ tự xuất hiện. Điều này hữu ích khi một request cần thực hiện nhiều thao tác ghi có quan hệ thứ tự. Tuy vậy, tính tuần tự của GraphQL không tự động tạo transaction cơ sở dữ liệu. Nếu nhiều thay đổi phải thành công hoặc thất bại cùng nhau, cần dùng transaction ở tầng service hoặc repository.

Mutation nên trả về dữ liệu đủ để client cập nhật giao diện sau thao tác. Ví dụ `createBook` trả về `Book` vừa tạo để client nhận ID do server cấp và các giá trị đã được chuẩn hóa.

Một mutation có thể thất bại do dữ liệu đầu vào không hợp lệ, tài nguyên không tồn tại, vi phạm quy tắc nghiệp vụ hoặc lỗi hạ tầng. Nên phân biệt lỗi validation, lỗi nghiệp vụ và lỗi hệ thống; không đưa stack trace hoặc thông tin nội bộ nhạy cảm vào response cho client. Có thể dùng cơ chế xử lý exception của Spring for GraphQL, chẳng hạn `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`, để chuẩn hóa lỗi.

## 5. Subscription: nhận dữ liệu theo thời gian thực

### 5.1. Subscription operation hoạt động thế nào?

Query và mutation thường trả về một kết quả cho một lần thực thi. Subscription tạo một luồng kết quả: server phát một response mỗi khi có sự kiện tương ứng, cho đến khi client hủy đăng ký hoặc kết nối kết thúc.

Client có thể đăng ký theo dõi sách mới:

~~~graphql
subscription WatchNewBooks {
    bookCreated {
        id
        title
        authorId
    }
}
~~~

Mỗi khi server phát một sự kiện `bookCreated`, client nhận một payload theo selection set đã yêu cầu. Một subscription operation chỉ có một field cấp cao nhất để xác định luồng sự kiện cần theo dõi.

GraphQL định nghĩa cách mô tả subscription nhưng không bắt buộc một giao thức truyền tải duy nhất. Ứng dụng Spring for GraphQL thường dùng WebSocket cho kết nối hai chiều lâu dài; Spring for GraphQL cũng hỗ trợ các lựa chọn truyền tải khác như RSocket khi ứng dụng được cấu hình tương ứng. Với WebSocket, client và server cần thống nhất giao thức GraphQL WebSocket, thường là `graphql-transport-ws`.

### 5.2. Ánh xạ subscription bằng `@SubscriptionMapping`

Spring for GraphQL hỗ trợ kiểu trả về reactive như `Flux<T>` để biểu diễn luồng sự kiện. Resolver có thể được viết như sau:

~~~java
@SubscriptionMapping
public Flux<Book> bookCreated() {
    return bookService.bookCreatedEvents();
}
~~~

`bookCreatedEvents()` cần trả về một publisher phát ra từng quyển sách mới. Publisher có thể được xây dựng từ Reactor Sinks, message broker hoặc một nguồn sự kiện khác. Ví dụ về hợp đồng service:

~~~java
public interface BookService {

    Optional<Book> findById(String id);

    List<Book> findAll();

    Book create(String title, String authorId);

    Flux<Book> bookCreatedEvents();
}
~~~

Khi `create()` tạo sách thành công, tầng service có thể phát sự kiện tương ứng vào publisher hoặc gửi sự kiện đến broker. Subscription resolver chỉ cung cấp luồng đó cho GraphQL engine; nó không nên tự thực hiện việc ghi dữ liệu.

### 5.3. Cấu hình transport và vận hành

Để client thực sự nhận được subscription, ứng dụng phải bật và cấu hình transport hỗ trợ subscription. Với WebSocket trong Spring Boot, có thể cấu hình endpoint bằng thuộc tính:

~~~properties
spring.graphql.websocket.path=/graphql
~~~

Đồng thời cần có WebSocket support phù hợp với stack Servlet hoặc WebFlux đang sử dụng. HTTP endpoint và WebSocket endpoint có thể dùng cùng đường dẫn hoặc được cấu hình riêng theo kiến trúc triển khai. Hãy kiểm tra cấu hình thực tế của ứng dụng và URL mà client sử dụng.

Một số vấn đề cần xử lý khi đưa subscription vào môi trường thực tế:

- **Quản lý vòng đời:** khi client ngắt kết nối hoặc hủy subscription, publisher và tài nguyên liên quan cần được giải phóng phù hợp.
- **Backpressure và tốc độ phát sự kiện:** nếu server phát nhanh hơn khả năng tiêu thụ của client, cần chọn chiến lược buffer, giới hạn hoặc loại bỏ sự kiện phù hợp. Không nên để buffer tăng không giới hạn.
- **Nhiều instance ứng dụng:** một luồng sự kiện trong bộ nhớ của một instance không tự động được chia sẻ sang instance khác. Hệ thống chạy nhiều instance thường cần message broker hoặc hạ tầng pub/sub dùng chung.
- **Xác thực và phân quyền:** cần xác thực kết nối và kiểm tra quyền xem từng luồng sự kiện. Người dùng chỉ nên nhận những sự kiện mà họ được phép truy cập.
- **Khả năng kết nối lại:** client có thể mất mạng hoặc kết nối WebSocket bị đóng. Nếu cần khôi phục sự kiện đã bỏ lỡ, thiết kế cần có event ID, cursor hoặc cơ chế replay ở tầng sự kiện; subscription cơ bản không tự bảo đảm phát lại dữ liệu cũ.

Subscription phù hợp với thông báo trạng thái, tiến trình xử lý, cập nhật dashboard hoặc sự kiện nghiệp vụ cần đẩy đến client. Với dữ liệu không cần cập nhật liên tục, query có cơ chế polling đơn giản hơn và thường dễ vận hành hơn.

## 6. Luồng xử lý trong Spring for GraphQL

Các operation đều đi qua schema và GraphQL engine. Sau khi xác thực operation, engine gọi resolver tương ứng; resolver chuyển tiếp đến service và trả kết quả về cho engine để tạo response.

~~~mermaid
sequenceDiagram
    participant Client
    participant GraphQL as Spring for GraphQL
    participant Resolver as Controller method
    participant Service
    participant Store as Data store / Event source

    Client->>GraphQL: Gửi operation và variables
    GraphQL->>GraphQL: Parse và validate theo schema
    GraphQL->>Resolver: Gọi @QueryMapping hoặc @MutationMapping
    Resolver->>Service: Gọi nghiệp vụ
    Service->>Store: Đọc hoặc thay đổi dữ liệu
    Store-->>Service: Trả kết quả
    Service-->>Resolver: Trả domain result
    Resolver-->>GraphQL: Trả field result
    GraphQL-->>Client: Response theo selection set
~~~

Với subscription, phần thực thi sau khi đăng ký khác ở chỗ resolver trả về publisher. GraphQL engine tiếp tục chuyển từng phần tử của publisher thành response gửi qua transport cho đến khi luồng kết thúc hoặc bị hủy.

Trong Spring for GraphQL, các annotation thường gặp có vai trò như sau:

| Annotation | Vai trò |
| --- | --- |
| `@QueryMapping` | Ánh xạ method vào field của root type `Query` |
| `@MutationMapping` | Ánh xạ method vào field của root type `Mutation` |
| `@SubscriptionMapping` | Ánh xạ method vào field của root type `Subscription` |
| `@Argument` | Đọc argument của field GraphQL và bind sang tham số Java |
| `@SchemaMapping` | Ánh xạ method vào một field của object type bất kỳ |

Các annotation mapping là cách viết thuận tiện trên nền cơ chế `@SchemaMapping`. Có thể dùng `@SchemaMapping` trực tiếp khi muốn chỉ rõ type hoặc field name.

## 7. Kiểm thử query và mutation

Không nên chỉ kiểm tra method Java riêng lẻ. Cần kiểm tra cả schema, argument binding và kết quả GraphQL mà client thực sự nhìn thấy. Spring for GraphQL cung cấp `GraphQlTester` và các biến thể phù hợp với kiểu kiểm thử khác nhau.

Ví dụ kiểm thử query bằng `GraphQlTester`:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("GraphQL thực hành");
~~~

Ví dụ kiểm thử mutation:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
        "title", "GraphQL thực hành",
        "authorId", "author-12"
    ))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("GraphQL thực hành");
~~~

Các test nên bao gồm cả trường hợp hợp lệ và lỗi:

1. Query tìm thấy dữ liệu và query không tìm thấy dữ liệu.
2. Query danh sách rỗng và danh sách có phần tử.
3. Mutation nhận input hợp lệ, input thiếu field bắt buộc hoặc vi phạm validation.
4. Mutation gặp lỗi nghiệp vụ, chẳng hạn author không tồn tại hoặc người dùng không có quyền tạo sách.
5. Schema từ chối field hoặc argument không tồn tại.
6. Subscription phát sự kiện, kết thúc luồng và hủy đăng ký đúng cách.

Với subscription, nên kiểm thử qua transport WebSocket bằng công cụ tester tương ứng, chẳng hạn `WebSocketGraphQlTester`, để xác minh cả quá trình đăng ký, nhận sự kiện và hủy đăng ký. Một unit test cho method trả về `Flux` không đủ để xác nhận endpoint WebSocket và giao thức đã được cấu hình đúng.

## 8. Thiết kế API an toàn và dễ bảo trì

Một GraphQL API tốt cần chú ý cả schema lẫn chi phí thực thi:

- **Giới hạn truy vấn:** giới hạn kích thước danh sách, hỗ trợ pagination và cân nhắc độ sâu hoặc độ phức tạp truy vấn. Không nên trả về một danh sách không giới hạn chỉ vì client có thể chọn field.
- **Tránh N+1:** khi một query lấy nhiều object và mỗi object cần tải dữ liệu liên quan, dùng cơ chế batch hoặc DataLoader để gom các lần truy cập dữ liệu. Chọn field ít hơn không tự động loại bỏ N+1.
- **Phân quyền theo dữ liệu:** xác thực request và kiểm tra quyền ở tầng phù hợp. Việc client không chọn một field không có nghĩa dữ liệu đó được phép truy cập; resolver và service vẫn phải bảo vệ tài nguyên.
- **Kiểm tra input ở server:** dùng kiểu scalar phù hợp, constraint validation và kiểm tra quy tắc nghiệp vụ. Không tin dữ liệu client gửi lên.
- **Giữ schema ổn định:** ưu tiên thêm field nullable hoặc input field mới theo cách tương thích. Khi loại bỏ field, nên có lộ trình deprecation và theo dõi client đang sử dụng.
- **Quan sát lỗi và hiệu năng:** ghi log có kiểm soát, theo dõi thời gian resolver, số lần truy cập dữ liệu và lỗi theo operation. Tránh ghi token, thông tin cá nhân hoặc payload nhạy cảm vào log.
- **Bảo vệ subscription:** giới hạn số kết nối và số subscription mỗi người dùng, kiểm tra quyền với từng luồng và đặt giới hạn buffer phù hợp.

## 9. Quy trình thực hiện một operation

Khi bổ sung một chức năng GraphQL mới, có thể đi theo trình tự sau:

1. Xác định chức năng là đọc dữ liệu, thay đổi trạng thái hay theo dõi sự kiện để chọn query, mutation hoặc subscription.
2. Khai báo field, argument, input object và kiểu trả về trong SDL; chọn nullability theo kết quả thực tế có thể xảy ra.
3. Viết resolver trong controller bằng annotation mapping phù hợp và bind argument bằng `@Argument`.
4. Chuyển xử lý nghiệp vụ sang service; bổ sung validation, transaction và authorization khi cần.
5. Với subscription, cung cấp publisher và cấu hình transport tương ứng; kiểm tra vòng đời, backpressure và quyền truy cập.
6. Dùng GraphQlTester hoặc tester theo transport để kiểm tra response, lỗi và các trường hợp biên.

Khi nắm được ba loại operation và cách ánh xạ chúng vào Spring for GraphQL, có thể thiết kế một API có schema rõ ràng, client chủ động chọn dữ liệu cần nhận và server kiểm soát được logic nghiệp vụ ở tầng phù hợp.
