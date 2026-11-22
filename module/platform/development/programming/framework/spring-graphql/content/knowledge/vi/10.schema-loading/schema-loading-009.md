# Schema thiếu root operation

GraphQL schema không chỉ mô tả các object type và quan hệ dữ liệu. Schema còn phải xác định những operation gốc mà client được phép gọi. Một schema hợp lệ luôn cần có **Query root operation type** để xử lý thao tác đọc dữ liệu. **Mutation** và **Subscription** là hai root operation type tùy chọn, chỉ cần khai báo khi API hỗ trợ ghi dữ liệu hoặc phát sự kiện.

Nếu schema không có Query root, trỏ Query tới một kiểu không tồn tại hoặc dùng một kiểu không phải object làm root, GraphQL không thể xây dựng schema hợp lệ. Với Spring for GraphQL, lỗi thường xuất hiện khi ứng dụng khởi tạo GraphQL runtime, trước khi endpoint có thể xử lý query. Vì vậy, khi thấy lỗi liên quan tới query root hoặc schema validation, cần kiểm tra SDL và cách các file schema được ghép lại.

## Root operation type là gì?

GraphQL có ba loại operation mà client có thể gửi:

| Operation | Root operation type | Mục đích |
| --- | --- | --- |
| Query | Query root | Đọc dữ liệu |
| Mutation | Mutation root | Thay đổi dữ liệu hoặc trạng thái |
| Subscription | Subscription root | Nhận sự kiện theo thời gian |

Root operation type là điểm bắt đầu để GraphQL thực thi operation. Khi client gửi một query, GraphQL bắt đầu phân giải các field được chọn từ Query root. Với mutation, quá trình bắt đầu từ Mutation root; với subscription, GraphQL bắt đầu từ Subscription root và thiết lập luồng phát dữ liệu theo transport được hỗ trợ.

Một schema tối thiểu cần có Query root:

~~~graphql
type Query {
  health: String!
}
~~~

Trong ví dụ, Query là object type gốc và health là field đọc dữ liệu. Field này có thể trả về thông tin trạng thái ứng dụng hoặc phiên bản API. Query root không nên chỉ là một kiểu rỗng: object type trong GraphQL phải có ít nhất một field.

Mutation và Subscription không bắt buộc. Một API chỉ đọc dữ liệu có thể chỉ có Query. Một API có mutation vẫn phải có Query, kể cả khi phần lớn nghiệp vụ của API là ghi dữ liệu. GraphQL không hỗ trợ một schema chỉ có Mutation root mà không có Query root.

## Root operation mặc định theo tên

Nếu SDL không khai báo khối schema tường minh, GraphQL sử dụng các tên root operation theo quy ước:

- Object type tên Query được dùng làm Query root và là bắt buộc.
- Nếu có object type tên Mutation, nó được dùng làm Mutation root.
- Nếu có object type tên Subscription, nó được dùng làm Subscription root.

Ví dụ schema sau hợp lệ mà không cần viết khối schema:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
}

input CreateBookInput {
  title: String!
}
~~~

Trong schema này, GraphQL nhận biết Query và Mutation theo tên. Query là root bắt buộc; Mutation được nhận diện vì object type cùng tên tồn tại. Nếu không khai báo Subscription, schema vẫn hợp lệ và client không thể gửi subscription operation.

Một lỗi phổ biến là chỉ khai báo các kiểu dữ liệu nghiệp vụ nhưng quên Query:

~~~graphql
type Book {
  id: ID!
  title: String!
}

type Author {
  id: ID!
  name: String!
}
~~~

Book và Author là object type hợp lệ, nhưng chúng không tự trở thành root operation. Schema trên thiếu Query nên không thể được dùng như một GraphQL schema hoàn chỉnh. Cần thêm một Query root có ít nhất một field:

~~~graphql
type Query {
  books: [Book!]!
  authors: [Author!]!
}
~~~

## Khai báo root operation tường minh

Khi muốn dùng tên root khác quy ước, hoặc muốn chỉ rõ ánh xạ root, hãy khai báo khối schema:

~~~graphql
schema {
  query: RootQuery
  mutation: RootMutation
}

type RootQuery {
  books: [Book!]!
}

type RootMutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
}

input CreateBookInput {
  title: String!
}
~~~

Ở đây RootQuery là Query root và RootMutation là Mutation root. Tên kiểu không cần phải là Query hoặc Mutation vì khối schema đã khai báo vai trò của chúng.

Khi dùng schema definition tường minh, hãy khai báo đúng Query root. Ví dụ sau không hợp lệ vì không có operation type query:

~~~graphql
schema {
  mutation: RootMutation
}

type RootMutation {
  resetCatalog: Boolean!
}
~~~

Việc có Mutation root không thay thế yêu cầu Query root. Cách sửa là bổ sung một Query root có field đọc dữ liệu:

~~~graphql
schema {
  query: RootQuery
  mutation: RootMutation
}

type RootQuery {
  health: String!
}

type RootMutation {
  resetCatalog: Boolean!
}
~~~

Root operation type được khai báo phải tồn tại trong schema và phải là object type. Không thể trỏ query tới scalar, enum, interface, union hoặc input object. Nếu tên root được khai báo nhưng kiểu tương ứng bị thiếu, schema validation cũng thất bại.

## Phân biệt root operation với object type thông thường

Không phải object type nào cũng có thể được client gọi trực tiếp. Ví dụ:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Book và Author mô tả dữ liệu, còn Query xác định field đầu vào để client bắt đầu truy vấn. Client không gửi operation trực tiếp lên Book; nó gọi một field trên Query rồi đi tiếp tới Book:

~~~graphql
query {
  book(id: "book-101") {
    id
    title
    author {
      name
    }
  }
}
~~~

Có thể hình dung luồng dữ liệu như sau:

~~~mermaid
flowchart TD
    A["GraphQL client"] --> B["Query root"]
    B --> C["Field book(id)"]
    C --> D["Object Book"]
    D --> E["Field author"]
    E --> F["Object Author"]
    B --> G["Các field Query khác"]
~~~

Root type tạo điểm vào có kiểm soát cho API. Các object type còn lại được truy cập thông qua những field được công bố trên root hoặc các object liên quan.

## Trường hợp chia schema thành nhiều file

Ứng dụng lớn thường chia SDL thành nhiều file theo domain, chẳng hạn book.graphqls, author.graphqls và query.graphqls. Spring Boot có thể nạp nhiều file schema trong vị trí resource đã cấu hình rồi kết hợp chúng thành một schema.

Ví dụ:

~~~text
src/main/resources/graphql/
├── query.graphqls
├── book.graphqls
└── author.graphqls
~~~

File query.graphqls định nghĩa root:

~~~graphql
type Query {
  books: [Book!]!
  authors: [Author!]!
}
~~~

File book.graphqls định nghĩa object:

~~~graphql
type Book {
  id: ID!
  title: String!
}
~~~

File author.graphqls định nghĩa object còn lại:

~~~graphql
type Author {
  id: ID!
  name: String!
}
~~~

Trong mô hình này, chỉ một file cần khai báo type Query ban đầu. Các file khác có thể mở rộng root bằng type extension:

~~~graphql
extend type Query {
  featuredBooks: [Book!]!
}
~~~

Điểm quan trọng là extend type Query chỉ mở rộng một kiểu đã tồn tại. Nó không tạo ra Query root mới. Nếu tất cả file đều chỉ có extend type Query mà không file nào định nghĩa type Query gốc, việc ghép schema sẽ thất bại vì không có kiểu để mở rộng.

Một cách tổ chức khác là đặt toàn bộ root field trong một file query.graphqls, còn các file domain chỉ định nghĩa object type và field liên quan. Dù chọn cách nào, sau khi nạp tất cả SDL vẫn phải có một Query root hợp lệ.

## Cấu hình schema loading trong Spring for GraphQL

Với Spring Boot, dependency GraphQL starter cung cấp phần tự động cấu hình schema và runtime. Schema thường được đặt trong thư mục:

~~~text
src/main/resources/graphql/
~~~

Spring Boot mặc định tìm các file schema trong classpath theo vị trí GraphQL đã cấu hình. Có thể chỉ định vị trí khác trong application.yml:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/
      file-extensions: .graphqls,.gqls
~~~

Khi khởi tạo, Spring for GraphQL kết hợp các tài nguyên schema, xây dựng GraphQL runtime và áp dụng các runtime wiring configurer. Nếu SDL không có Query root hoặc root mapping sai, quá trình xây dựng schema sẽ phát sinh lỗi. Endpoint /graphql có thể chưa sẵn sàng vì ứng dụng chưa khởi tạo xong.

Không nên sửa lỗi thiếu root bằng cách thêm một controller có @QueryMapping mà không bổ sung field tương ứng trong SDL. Controller resolver chỉ ánh xạ vào field đã có trong schema; nó không thay thế việc định nghĩa Query root.

## Ánh xạ root operation vào Spring Controller

Sau khi schema khai báo Query, controller có thể ánh xạ field bằng @QueryMapping:

~~~graphql
type Query {
  health: String!
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public String health() {
        return "UP";
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Tên phương thức mặc định được dùng làm tên field nếu không chỉ định tên khác. @QueryMapping xử lý field thuộc Query root. Tương tự, @MutationMapping ánh xạ field của Mutation root và @SubscriptionMapping ánh xạ field của Subscription root.

Nếu schema khai báo root tùy chỉnh như RootQuery, cần chú ý tên type mà annotation ánh xạ tới. @QueryMapping là cách viết tắt cho mapping vào root type có tên Query theo quy ước. Với RootQuery, hãy dùng @SchemaMapping và chỉ rõ typeName:

~~~java
@Controller
public class CustomRootController {

    @SchemaMapping(typeName = "RootQuery", field = "health")
    public String health() {
        return "UP";
    }
}
~~~

Schema definition vẫn phải khai báo query: RootQuery. Annotation chỉ ánh xạ phương thức Java vào field; nó không thay thế việc khai báo root operation trong SDL.

Ví dụ operation:

~~~graphql
query {
  health
  book(id: "book-101") {
    id
    title
  }
}
~~~

Resolver không thể khiến một schema thiếu Query trở nên hợp lệ. Hãy bảo đảm root type và field tồn tại trước, sau đó mới kiểm tra controller mapping.

## Các nguyên nhân thường gây lỗi thiếu root operation

| Nguyên nhân | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Chưa định nghĩa type Query | Schema chỉ có Book, Author hoặc các object nghiệp vụ | Tạo Query root với ít nhất một field |
| Dùng root tên tùy chỉnh nhưng không khai báo schema | Có RootQuery nhưng GraphQL không nhận diện làm query root | Thêm schema block và ánh xạ query: RootQuery |
| Schema block bỏ sót query | Chỉ khai báo mutation hoặc subscription | Bổ sung query root |
| Root type được tham chiếu nhưng không tồn tại | schema trỏ tới kiểu sai tên hoặc file định nghĩa không được nạp | Sửa tên hoặc vị trí file schema |
| Root type không phải object | Query trỏ tới scalar, interface hoặc input type | Dùng object type làm root |
| Chỉ dùng extend type Query | Không có định nghĩa type Query gốc trong các file đã nạp | Tạo type Query trước khi dùng extension |
| File root không được Spring Boot nạp | SDL có Query nhưng nằm ngoài schema locations | Sửa schema locations hoặc resource path |
| Định nghĩa root trùng lặp | Nhiều file khai báo type Query riêng biệt | Giữ một định nghĩa gốc và dùng extend type Query cho phần bổ sung |

## Cách chẩn đoán trong ứng dụng Spring

Khi ứng dụng khởi động thất bại với lỗi schema validation, hãy kiểm tra theo thứ tự:

1. **Kiểm tra SDL đã nạp.** Xác nhận có file định nghĩa Query root, không chỉ có các object type nghiệp vụ.
2. **Kiểm tra schema block.** Nếu dùng tên root tùy chỉnh, xác nhận có ánh xạ query tới đúng object type.
3. **Kiểm tra vị trí resource.** Bảo đảm file schema nằm trong classpath và khớp cấu hình schema locations.
4. **Kiểm tra type extension.** Không dùng extend type Query khi chưa có type Query gốc trong schema tổng hợp.
5. **Kiểm tra root type.** Root phải là object type hợp lệ và có ít nhất một field.
6. **Kiểm tra wiring sau khi schema hợp lệ.** Sau khi root được nhận diện, mới kiểm tra @QueryMapping và các data fetcher tương ứng.

Không nên xử lý bằng cách bắt exception khởi tạo rồi tiếp tục chạy ứng dụng với schema thiếu Query. Nếu schema không hợp lệ, GraphQL runtime không có điểm vào để thực thi query. Ứng dụng nên thất bại khi khởi động để lỗi cấu hình được phát hiện sớm.

## Kiểm thử schema có root operation

Nên có kiểm thử khởi tạo GraphQL runtime hoặc kiểm thử tích hợp Spring context để xác nhận schema được nạp và Query root tồn tại. Có thể dùng GraphQlTester kiểm tra operation thực tế sau khi context khởi động:

~~~java
graphQlTester.document("""
        query {
            health
        }
        """)
    .execute()
    .path("health")
    .entity(String.class)
    .isEqualTo("UP");
~~~

Ngoài trường hợp thành công, nên có kiểm thử schema lỗi trong test riêng để xác nhận các cấu hình sai như thiếu Query hoặc mở rộng một root chưa tồn tại bị phát hiện. Những test này giúp ngăn lỗi quay lại khi schema được tách thành nhiều file hoặc khi một nhóm phát triển thêm domain mới.

## Checklist khi thêm schema mới

Trước khi hoàn tất một thay đổi SDL, hãy xác nhận:

- Có một Query root operation được chỉ định trong schema tổng hợp.
- Query root được khai báo trực tiếp hoặc được ánh xạ rõ trong schema block.
- Query root là object type và có ít nhất một field.
- Mutation và Subscription chỉ được khai báo khi API thực sự cần.
- Các file dùng extend type Query đều có định nghĩa Query gốc trong schema tổng hợp.
- Spring Boot nạp tất cả file schema từ đúng classpath location.
- Các phương thức @QueryMapping tương ứng với field có thật trong SDL.
- Ứng dụng khởi động thành công và GraphQlTester thực thi được một query cơ bản.

Schema thiếu root operation là lỗi cấu trúc của hợp đồng GraphQL, không phải lỗi truy vấn dữ liệu bên trong resolver. Query root luôn bắt buộc; Mutation và Subscription là tùy chọn. Trong Spring for GraphQL, cần bảo đảm SDL được nạp đầy đủ, root được khai báo đúng và controller chỉ ánh xạ vào những field đã có trong schema. Kiểm tra các điểm này ngay khi xây dựng GraphQL runtime giúp phát hiện lỗi sớm, đặc biệt khi schema được chia nhỏ theo domain.
