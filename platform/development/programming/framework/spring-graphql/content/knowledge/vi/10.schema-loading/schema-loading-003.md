# schema.graphqls

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của file schema.graphqls trong ứng dụng Spring for GraphQL.
- Đặt file SDL đúng vị trí để Spring Boot tự động phát hiện và nạp schema.
- Hiểu cách Spring Boot ghép nhiều file GraphQL schema thành một schema hoàn chỉnh.
- Tổ chức schema theo type hoặc miền nghiệp vụ bằng type extension.
- Nhận biết lỗi thường gặp khi đặt tên, khai báo hoặc nạp schema.
- Kiểm thử schema đã nạp cùng resolver trong ứng dụng Spring Boot.

## schema.graphqls là gì?

schema.graphqls là tên thường dùng cho file chứa GraphQL Schema Definition Language (SDL). File này mô tả contract của GraphQL API: root operation, object type, input type, scalar, enum, interface, union, field, argument và nullability.

Spring for GraphQL sử dụng schema SDL để xây dựng GraphQL schema lúc ứng dụng khởi động. Các annotated controller như @QueryMapping, @MutationMapping và @SchemaMapping cung cấp logic xử lý field đã khai báo trong schema. Controller không tự tạo ra toàn bộ contract GraphQL từ tên method Java.

Một file schema.graphqls tối thiểu có thể khai báo:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Trong ví dụ này:

- Query là root object type cho các thao tác đọc.
- bookById là root field mà client có thể gọi.
- id là argument bắt buộc, có kiểu ID!.
- Book là object type được trả về.
- id và title là các field mà client có thể lựa chọn trong selection set.

Khi client gửi query bookById, GraphQL engine kiểm tra operation theo schema rồi tìm resolver phù hợp để thực thi field. Nếu schema không khai báo field hoặc kiểu được dùng không hợp lệ, operation sẽ không qua được bước validation.

## Vị trí mặc định trong Spring Boot

Với Spring Boot và Spring for GraphQL, vị trí mặc định để đặt schema resources là thư mục graphql trên classpath. Trong một dự án Gradle hoặc Maven, cấu trúc thường dùng là:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            └── schema.graphqls
~~~

Khi build ứng dụng, file trong src/main/resources được đưa vào classpath. Spring Boot GraphQL auto-configuration tìm schema ở vị trí mặc định và tạo GraphQlSource từ các định nghĩa được nạp.

Tên schema.graphqls là quy ước dễ nhận biết, không phải tên file duy nhất mà framework bắt buộc. Điều quan trọng là file nằm trong schema location được cấu hình và có phần mở rộng được loader nhận diện.

Các phần mở rộng thường được Spring Boot hỗ trợ mặc định là .graphqls và .graphql. Dùng .graphqls cho file SDL giúp người đọc nhận ra đây là GraphQL schema. Nếu dự án cấu hình danh sách phần mở rộng riêng, hãy bảo đảm file dùng extension nằm trong danh sách đó.

## Cấu hình schema location

Nếu giữ cấu trúc mặc định, thường không cần khai báo thêm cấu hình. Khi schema nằm ở vị trí khác, có thể thay đổi schema location bằng thuộc tính spring.graphql.schema.locations.

Ví dụ trong application.properties khi schema được đặt trong thư mục api-schema:

~~~properties
spring.graphql.schema.locations=classpath:api-schema/**/
~~~

Với cấu trúc mặc định graphql và các thư mục con theo miền nghiệp vụ, có thể dùng:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
~~~

Có thể cấu hình phần mở rộng file được nhận diện:

~~~properties
spring.graphql.schema.file-extensions=.graphqls,.graphql
~~~

Các giá trị cấu hình phải phù hợp với phiên bản Spring Boot mà dự án đang sử dụng. Hãy kiểm tra metadata cấu hình của phiên bản đó nếu dự án override danh sách location hoặc extension. Khi thay đổi location, hãy xác minh tài nguyên thực sự được copy vào classpath sau build.

Nếu dùng YAML:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:api-schema/**/
      file-extensions:
        - .graphqls
        - .graphql
~~~

Không nhầm schema location với HTTP endpoint. spring.graphql.schema.locations quyết định nơi server đọc SDL khi khởi động; spring.graphql.path quyết định URL HTTP mà client gọi. Hai cấu hình phục vụ hai tầng khác nhau.

## Nội dung cơ bản của schema.graphqls

Một schema thường khai báo root operation type và các type của miền nghiệp vụ. Ví dụ API thư viện:

~~~graphql
type Query {
  bookById(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  pageCount: Int
  author: Author
}

type Author {
  id: ID!
  name: String!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  pageCount: Int
}
~~~

Schema trên mô tả:

- Query field để lấy một sách hoặc danh sách sách.
- Mutation field để tạo sách.
- Object type Book và Author cho response.
- Input object CreateBookInput cho dữ liệu client gửi lên.
- Scalar chuẩn ID, String và Int.
- Nullability và default value cho từng field, argument.

Schema là hợp đồng độc lập với cách lưu trữ. Không cần khai báo tên bảng hoặc tên cột database trong SDL. Controller và service sẽ ánh xạ contract này sang mô hình nghiệp vụ của ứng dụng.

## Có thể chia schema thành nhiều file

Một ứng dụng nhỏ có thể để toàn bộ SDL trong schema.graphqls. Khi schema lớn dần, việc giữ mọi type trong một file khiến khó tìm kiếm và dễ tạo xung đột khi nhiều người cùng sửa.

Spring Boot cho phép nạp nhiều schema resources từ schema locations đã cấu hình. Ví dụ:

~~~text
src/main/resources/graphql/
├── schema.graphqls
├── book.graphqls
├── author.graphqls
└── order.graphqls
~~~

Các file được ghép thành một schema GraphQL trong quá trình khởi tạo. Tên file không tự tạo namespace hoặc module riêng. Các type và field trong các file vẫn thuộc cùng một schema, nên tên type phải nhất quán và không được định nghĩa trùng lặp theo cách không hợp lệ.

Một cách tổ chức là giữ root type và các type dùng chung trong schema.graphqls, sau đó mở rộng từng root type trong file miền nghiệp vụ:

~~~graphql
# schema.graphqls
type Query {
  health: String!
}

type Mutation {
  noop: Boolean
}
~~~

~~~graphql
# book.graphqls
type Book {
  id: ID!
  title: String!
}

extend type Query {
  bookById(id: ID!): Book
  books: [Book!]!
}
~~~

~~~graphql
# author.graphqls
type Author {
  id: ID!
  name: String!
}

extend type Query {
  authorById(id: ID!): Author
}
~~~

Type extension cho phép thêm field vào type đã được khai báo. Trong ví dụ, Query được định nghĩa một lần ở schema.graphqls; các file book.graphqls và author.graphqls bổ sung field bằng extend type Query.

Không nên khai báo lại type Query trong nhiều file như thể mỗi file có một root Query riêng. Nếu một type đã được định nghĩa, dùng type extension để bổ sung field. Các file SDL được ghép trước khi schema được xây dựng và kiểm tra tính hợp lệ.

## Quy tắc tổ chức nhiều file

Khi chia schema, hãy giữ một số quy tắc:

1. Mỗi object type hoặc input type nên có một nơi định nghĩa chính để dễ tìm nguồn contract.
2. Root type Query, Mutation và Subscription nên có một định nghĩa nền rõ ràng.
3. File miền nghiệp vụ dùng extend type để thêm field vào root type hoặc type được chia sẻ.
4. Không tạo hai định nghĩa độc lập cùng tên cho một type.
5. Tên type, field, argument và enum phải nhất quán giữa các file.
6. Đặt custom scalar trong một file dùng chung và bảo đảm runtime wiring đăng ký scalar tương ứng.
7. Dùng thư mục con theo miền nếu schema location pattern có thể tìm đệ quy các tài nguyên đó.

Ví dụ cấu trúc lớn hơn:

~~~text
src/main/resources/graphql/
├── schema.graphqls
├── common/
│   ├── scalars.graphqls
│   └── pagination.graphqls
├── catalog/
│   ├── book.graphqls
│   └── author.graphqls
└── sales/
    ├── order.graphqls
    └── customer.graphqls
~~~

Các thư mục chỉ giúp tổ chức tài nguyên. Chúng không tạo boundary bảo mật hay module GraphQL độc lập. Mọi file được tìm thấy theo schema location đều góp phần vào cùng schema runtime.

## Root operation type và schema declaration

GraphQL dùng các tên mặc định Query, Mutation và Subscription cho root operation type. Nếu dùng đúng tên mặc định, schema thường không cần khai báo schema block tường minh.

~~~graphql
type Query {
  books: [Book!]!
}
~~~

Nếu muốn dùng tên root type khác, cần khai báo schema definition:

~~~graphql
schema {
  query: ReadOperations
  mutation: WriteOperations
}

type ReadOperations {
  books: [Book!]!
}

type WriteOperations {
  createBook(input: CreateBookInput!): Book!
}
~~~

Không nên đổi tên root type chỉ vì muốn đặt tên Java controller khác. Root type là một phần schema contract; nếu thay đổi, client và các file schema liên quan cần được cập nhật đồng bộ.

## Liên kết schema với annotated controller

Sau khi SDL được nạp, Spring for GraphQL liên kết field với controller method thông qua annotation mapping.

Với schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

Controller có thể viết:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

Tên method bookById được dùng làm tên field mặc định của Query. @QueryMapping là shortcut cho mapping trên root type Query. Nếu method hoặc field có tên khác, có thể chỉ định tên tường minh trong annotation.

Điều cần nhớ:

- SDL khai báo field bookById và argument id.
- @QueryMapping cung cấp resolver cho field đó.
- @Argument bind giá trị id từ request vào tham số Java.
- Book là kiểu response; GraphQL tiếp tục phân giải các field được client chọn.

Nếu controller có mapping cho field không tồn tại trong schema, việc có method Java không làm field đó tự xuất hiện trong GraphQL API. Ngược lại, field được khai báo trong schema nhưng không có resolver hoặc property data fetcher phù hợp có thể trả về null hoặc gây lỗi tùy nullability.

## Custom scalar cần cả khai báo và runtime wiring

Khai báo scalar trong SDL chỉ định tên kiểu trong contract:

~~~graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}
~~~

Server còn phải đăng ký implementation cho scalar đó. Ví dụ dùng extended scalar:

~~~java
@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.DateTime);
    }
}
~~~

Nếu SDL khai báo DateTime nhưng runtime wiring không đăng ký scalar tương ứng, schema có thể không được xây dựng thành công hoặc không thể xử lý kiểu dữ liệu như mong đợi. Tên scalar trong SDL và tên scalar được đăng ký phải khớp nhau.

## Kiểm tra schema khi ứng dụng khởi động

Spring for GraphQL xây dựng GraphQL schema từ các tài nguyên SDL trong giai đoạn khởi tạo application context. Lỗi cú pháp, type không hợp lệ, field tham chiếu đến type chưa khai báo hoặc interface implement không đầy đủ có thể làm ứng dụng không khởi động được.

Khi gặp lỗi schema loading:

- Kiểm tra file có nằm dưới resources/graphql hoặc schema location đã cấu hình không.
- Kiểm tra extension có nằm trong spring.graphql.schema.file-extensions không.
- Kiểm tra file đã được copy vào classpath sau khi build chưa.
- Kiểm tra cú pháp SDL, dấu ngoặc, dấu hai chấm, kiểu tham chiếu và nullability.
- Kiểm tra type extension có target type tồn tại hay chưa.
- Kiểm tra tất cả object type triển khai interface đã cung cấp field cần thiết.
- Kiểm tra custom scalar đã được đăng ký runtime wiring.

Một số lỗi chỉ xuất hiện khi build schema, trước khi HTTP server nhận request. Vì vậy, hãy đọc log khởi động và exception gốc thay vì chỉ kiểm tra URL /graphql.

## Kiểm thử schema đã nạp

GraphQlTester cho phép thực thi operation trên GraphQL runtime trong test. Với Spring Boot, có thể dùng @GraphQlTest để tạo test slice cho các controller GraphQL và cấu hình cần thiết, hoặc dùng integration test với application context đầy đủ khi muốn kiểm tra schema resource loading thực tế.

Ví dụ kiểm thử query:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Guide");
~~~

Khi kiểm thử schema loading, nên có ít nhất một integration test khởi tạo application context từ resources thật. Test đó giúp phát hiện trường hợp file SDL bị đặt sai thư mục, sai extension hoặc không được đưa vào artifact build.

Ngoài operation thành công, hãy kiểm tra:

1. Field trong schema có mapping tương ứng.
2. Argument được bind đúng kiểu.
3. Field được mở rộng từ file SDL khác vẫn xuất hiện trong schema cuối.
4. Interface, union, enum và custom scalar được đăng ký đúng.
5. Schema lỗi khiến context khởi tạo thất bại với thông tin chẩn đoán đủ rõ.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ứng dụng không tìm thấy schema | File nằm ngoài classpath location mặc định | Đặt trong src/main/resources/graphql hoặc cấu hình schema locations |
| File schema bị bỏ qua | Extension không nằm trong danh sách file extensions | Dùng .graphqls/.graphql hoặc cập nhật cấu hình |
| Query field không tồn tại | Field chưa khai báo hoặc file chứa field không được nạp | Kiểm tra SDL và schema location |
| Type bị định nghĩa trùng | Nhiều file cùng khai báo lại một type thay vì dùng extension | Giữ một type definition và dùng extend type |
| Type extension không hợp lệ | Target type chưa được khai báo hoặc field bị trùng | Kiểm tra type gốc và tên field |
| Resolver không được gọi | Mapping name không khớp schema hoặc controller không được scan | Kiểm tra annotation và component scan |
| Custom scalar không hoạt động | Chỉ khai báo scalar trong SDL mà chưa đăng ký runtime wiring | Thêm RuntimeWiringConfigurer |
| Ứng dụng không khởi động | SDL sai cú pháp hoặc schema validation thất bại | Đọc exception gốc và kiểm tra các file schema được ghép |

## Thực hành tổng hợp

Tạo một ứng dụng Spring Boot với Spring for GraphQL và xây dựng schema thư viện theo nhiều file:

1. Tạo src/main/resources/graphql/schema.graphqls chứa root Query và Mutation.
2. Tạo book.graphqls chứa Book, CreateBookInput và extend type Query.
3. Tạo author.graphqls chứa Author và extend type Query.
4. Viết @QueryMapping cho bookById và authorById.
5. Chạy ứng dụng và gửi query đến GraphQL endpoint để kiểm tra dữ liệu.
6. Đổi schema location sang một thư mục khác, cập nhật cấu hình và xác minh file được nạp.
7. Thử khai báo trùng type hoặc bỏ một field bắt buộc để quan sát lỗi schema loading.
8. Viết integration test để xác nhận các file SDL được ghép thành một schema hoàn chỉnh.

Sau khi hoàn thành, hãy giải thích vì sao tên file schema.graphqls chỉ là quy ước, vì sao nhiều file vẫn tạo thành một schema và khi nào cần dùng extend type thay cho khai báo type lần nữa.

## Ghi nhớ

schema.graphqls là tên quy ước cho file GraphQL SDL. Spring Boot thường tự tìm schema trong classpath:graphql/**/ với các extension được hỗ trợ như .graphqls và .graphql. Có thể chia schema thành nhiều file theo miền nghiệp vụ; loader ghép chúng thành một schema chung. Khi bổ sung field cho type đã tồn tại, dùng extend type thay vì định nghĩa trùng type. SDL là contract của API, còn annotated controller và runtime wiring cung cấp resolver cùng implementation cho scalar. Hãy kiểm tra schema ngay khi khởi động và có integration test xác nhận tài nguyên thực sự được nạp.
