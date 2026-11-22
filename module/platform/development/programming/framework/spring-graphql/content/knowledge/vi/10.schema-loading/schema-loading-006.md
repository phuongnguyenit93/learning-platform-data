# Schema parse lỗi

Spring for GraphQL cần nạp schema SDL để xây dựng GraphQL runtime trước khi xử lý operation của client. Nếu schema sai cú pháp, khai báo type không hợp lệ hoặc thiếu tài nguyên schema, ứng dụng có thể không khởi động được. Khi gặp thông báo “schema parse error”, cần xác định lỗi xảy ra ở bước tìm file, phân tích cú pháp, kiểm tra tính hợp lệ của schema hay cấu hình resolver.

Bốn nhóm lỗi này có thời điểm và cách sửa khác nhau. Bài học tập trung vào cách Spring Boot nạp schema, các nguyên nhân phổ biến khiến schema không được xây dựng, cách đọc thông báo lỗi và quy trình chẩn đoán trong một ứng dụng Spring for GraphQL.

## 1. Schema được nạp ở thời điểm nào?

Trong ứng dụng Spring Boot, Spring for GraphQL tạo GraphQL runtime từ schema SDL và cấu hình thực thi. Theo cấu hình mặc định của Spring Boot, schema thường được tìm trong classpath dưới thư mục graphql/, bao gồm cả thư mục con. Các file schema thường dùng phần mở rộng .graphqls hoặc .gqls.

Ví dụ cấu trúc tài nguyên:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            ├── book.graphqls
            └── author/
                └── author.graphqls
~~~

Spring Boot thu thập các tài nguyên schema được cấu hình, sau đó Spring for GraphQL và GraphQL Java phân tích, hợp nhất và xây dựng schema thực thi. Ứng dụng thường hoàn thành bước này trong quá trình khởi tạo ApplicationContext.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Spring Boot khởi động"] --> B["Tìm tài nguyên SDL theo schema locations"]
    B --> C{"Có tìm thấy file schema?"}
    C -->|Không| D["Kiểm tra classpath và cấu hình locations"]
    C -->|Có| E["Đọc và parse SDL"]
    E --> F{"Cú pháp hợp lệ?"}
    F -->|Không| G["Parse error"]
    F -->|Có| H["Xây dựng và validate GraphQL schema"]
    H --> I{"Schema hợp lệ?"}
    I -->|Không| J["Schema validation / generation error"]
    I -->|Có| K["Áp dụng runtime wiring"]
    K --> L["GraphQL runtime sẵn sàng"]
~~~

Nếu lỗi xảy ra khi xây dựng GraphQL runtime, Spring có thể báo lỗi trong quá trình khởi động và ApplicationContext không được tạo thành công. Vì vậy, một lỗi SDL thường xuất hiện ngay cả khi chưa có client nào gửi GraphQL request.

## 2. Phân biệt parse error và các lỗi liên quan

Trong thực tế, mọi lỗi khi nạp schema đôi khi được gọi chung là “schema parse lỗi”. Tuy nhiên, cần phân biệt các giai đoạn:

| Giai đoạn | Kiểm tra điều gì? | Ví dụ lỗi |
| --- | --- | --- |
| Tìm tài nguyên | File SDL có nằm đúng classpath và được cấu hình để nạp không? | Không tìm thấy schema hoặc bỏ sót file trong thư mục con. |
| Parse SDL | Cú pháp GraphQL SDL có đúng không? | Thiếu dấu ngoặc nhọn, thiếu dấu hai chấm, khai báo field sai cú pháp. |
| Schema validation/generation | Các type và quan hệ trong schema có hợp lệ không? | Type không tồn tại, dùng input type làm output type, định nghĩa trùng. |
| Runtime wiring | Các thành phần thực thi có được cấu hình tương thích không? | Custom scalar chưa có implementation hoặc wiring không phù hợp. |
| Request validation | Operation client gửi có hợp lệ với schema đã nạp không? | Client gọi field không tồn tại hoặc thiếu selection set. |
| Field execution | Resolver có thực thi thành công không? | Repository ném exception hoặc service không tìm thấy dữ liệu. |

Parse error theo nghĩa hẹp là lỗi cú pháp khi GraphQL parser đọc SDL. Nếu parser đọc được file nhưng schema không thể xây dựng, đó là lỗi validation hoặc schema generation. Nếu ứng dụng đã khởi động và một operation bị từ chối, đó thường là lỗi request validation hoặc execution.

Phân biệt đúng giai đoạn giúp tránh sửa nhầm controller khi vấn đề thực tế nằm ở SDL, hoặc chỉnh schema khi request của client mới là phần không hợp lệ.

## 3. Lỗi cú pháp SDL thường gặp

SDL có cú pháp riêng. Một field thường được khai báo theo dạng:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

Tên field đứng trước dấu hai chấm, kiểu dữ liệu đứng sau. Một số lỗi thường gặp:

**Thiếu dấu hai chấm sau tên field**

~~~graphql
type Book {
    id ID!
    title: String!
}
~~~

Cách sửa:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

**Thiếu dấu ngoặc nhọn đóng type**

~~~graphql
type Book {
    id: ID!
    title: String!
~~~

Cách sửa là đóng đầy đủ block:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

**Khai báo argument sai cú pháp**

~~~graphql
type Query {
    book id: ID!: Book
}
~~~

Cách viết đúng:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

**Khai báo enum value sai định dạng**

~~~graphql
enum BookStatus {
    IN-PROGRESS
    COMPLETED
}
~~~

Tên enum value không được chứa dấu gạch ngang như một identifier thông thường. Dùng quy ước chữ hoa và dấu gạch dưới:

~~~graphql
enum BookStatus {
    IN_PROGRESS
    COMPLETED
}
~~~

Khi parser báo vị trí dòng và cột, hãy bắt đầu đọc quanh vị trí đó. Lỗi thực sự đôi khi nằm ở dòng trước: một dấu ngoặc nhọn chưa đóng hoặc một dấu hai chấm bị thiếu có thể khiến parser chỉ phát hiện sai cú pháp ở token tiếp theo.

## 4. Lỗi type không tồn tại hoặc dùng sai loại

Một schema có thể đúng cú pháp nhưng không hợp lệ vì tham chiếu đến type chưa được khai báo.

Ví dụ lỗi chính tả tên type:

~~~graphql
type Query {
    book(id: ID!): Bok
}
~~~

Nếu schema không có type Bok, việc xây dựng schema thất bại. Sửa thành đúng tên:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

GraphQL cũng phân biệt input type và output type. Không thể dùng output object làm argument:

~~~graphql
type BookFilter {
    keyword: String
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Nếu BookFilter được khai báo bằng type, nó là output object type. Hãy đổi thành input object:

~~~graphql
input BookFilter {
    keyword: String
}

type Book {
    id: ID!
    title: String!
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Chiều ngược lại cũng sai: input object không thể làm kiểu trả về của field. Output field phải trả về scalar, enum, object, interface, union hoặc list hợp lệ của các kiểu output.

Khi kiểm tra lỗi type, đối chiếu cả định nghĩa gốc và nơi type được tham chiếu. Tên type có thể nằm trong file SDL khác, vì vậy cũng cần xác nhận file đó đã được nạp.

## 5. Định nghĩa trùng và mở rộng type sai cách

Một ứng dụng có thể chia schema thành nhiều file theo domain. Khi nhiều file cùng định nghĩa một type, cần tránh khai báo trùng tên.

Ví dụ file book.graphqls:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

File author.graphqls lại khai báo:

~~~graphql
type Query {
    author(id: ID!): Author
}
~~~

Cả hai file đều định nghĩa type Query. Khi các tài nguyên được hợp nhất, GraphQL không coi đây là hai phần của cùng một type definition. Dùng extend type Query cho file bổ sung:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

~~~graphql
extend type Query {
    author(id: ID!): Author
}
~~~

File có extend type Query cần được nạp cùng schema chứa định nghĩa gốc Query. Nếu file gốc bị bỏ sót, extension có thể tham chiếu đến một type không tồn tại.

Ngoài trùng type, cần tránh:

- Khai báo hai field cùng tên trong cùng một object type.
- Khai báo trùng argument trong cùng một field.
- Khai báo trùng enum value.
- Định nghĩa cùng một type ở nhiều file thay vì mở rộng đúng cách.

Khi chia schema thành nhiều file, nên phân công rõ file nào khai báo type gốc và file nào chỉ mở rộng type. Cách này giúp giảm xung đột khi nhiều người cùng phát triển schema.

## 6. Root operation type không hợp lệ

GraphQL schema cần có query root là một object type. Theo quy ước mặc định, nếu không khai báo schema definition riêng, root query type có tên Query.

Ví dụ hợp lệ:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Nếu dùng tên khác, phải khai báo rõ root operation:

~~~graphql
schema {
    query: CatalogQuery
}

type CatalogQuery {
    book(id: ID!): Book
}
~~~

Một số lỗi có thể gặp:

- Không có query root.
- Root query được trỏ đến type không tồn tại.
- Root query trỏ đến scalar, enum hoặc input object thay vì object type.
- Tên root operation trong schema definition không khớp với type đã khai báo.

Mutation và Subscription là tùy chọn. Nếu ứng dụng có mutation, khai báo root type Mutation và cấu hình mapping tương ứng. Nếu có subscription, khai báo Subscription và cấu hình transport hỗ trợ streaming. Không cần khai báo các root type này nếu API chưa cung cấp operation tương ứng.

## 7. Lỗi quan hệ type và quy tắc schema validation

GraphQL kiểm tra nhiều quy tắc ngoài cú pháp. Ví dụ, một type triển khai interface phải cung cấp các field bắt buộc với kiểu tương thích.

~~~graphql
interface Node {
    id: ID!
}

type Book implements Node {
    title: String!
}
~~~

Schema trên không hợp lệ vì Book thiếu field id mà interface Node yêu cầu.

Cách sửa:

~~~graphql
interface Node {
    id: ID!
}

type Book implements Node {
    id: ID!
    title: String!
}
~~~

Union cũng chỉ được chứa object type hợp lệ:

~~~graphql
union SearchResult = Book | Author
~~~

Nếu một thành viên chưa được khai báo hoặc không phải object type, schema không thể được xây dựng đúng.

Một trường hợp ít gặp hơn là vòng tham chiếu input object bắt buộc. Ví dụ:

~~~graphql
input AInput {
    next: BInput!
}

input BInput {
    previous: AInput!
}
~~~

Hai input object yêu cầu lẫn nhau bằng field non-null đơn. Không có cách tạo giá trị hữu hạn cho một input object mà không cần giá trị của object còn lại. Có thể phá vòng bắt buộc bằng cách cho phép null hoặc dùng list:

~~~graphql
input AInput {
    next: BInput
}

input BInput {
    previous: AInput
}
~~~

Khi schema generation báo lỗi validation nhưng cú pháp nhìn có vẻ đúng, hãy kiểm tra interface implementation, union members, input/output type position, root operation và các chu trình input object.

## 8. Lỗi không tìm thấy hoặc không nạp đủ schema trong Spring Boot

Một SDL đúng cú pháp vẫn không có tác dụng nếu file không được Spring Boot tìm thấy.

Mặc định, Spring Boot tìm schema trong classpath tại thư mục graphql/ và các thư mục con. Nếu đặt schema ở vị trí khác, cấu hình schema locations:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/
~~~

Nếu dự án có cấu hình locations tùy chỉnh, cần bảo đảm mọi file schema cần thiết đều nằm trong các vị trí đó. Khi dùng nhiều location, kiểm tra cách khai báo theo phiên bản Spring Boot đang sử dụng.

Các nguyên nhân phổ biến:

- File nằm ở src/main/java thay vì src/main/resources.
- File được đặt ngoài thư mục schema mặc định nhưng chưa cấu hình locations.
- Tên file không có phần mở rộng được cấu hình hỗ trợ.
- File nằm trong thư mục con nhưng pattern location không bao phủ.
- Tài nguyên không được đóng gói vào artifact khi build.
- Tên đường dẫn hoặc chữ hoa/chữ thường khác nhau giữa máy phát triển và môi trường triển khai.
- Một file chứa extend type được nạp nhưng file định nghĩa type gốc lại bị bỏ sót.

Khi chạy trong IDE, tài nguyên có thể có sẵn từ source tree nhưng bị thiếu trong JAR. Nếu ứng dụng chỉ lỗi sau khi đóng gói, hãy kiểm tra nội dung artifact và xác nhận các file SDL được đưa vào classpath.

## 9. Phân biệt lỗi schema với lỗi RuntimeWiring

Schema SDL mô tả type, field, argument và directive. Runtime wiring kết nối schema với cách thực thi, chẳng hạn data fetcher, custom scalar và type resolver.

Ví dụ schema khai báo custom scalar:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

Nếu ứng dụng dùng custom scalar DateTime, cần đăng ký implementation phù hợp trong GraphQL runtime. Trong Spring for GraphQL, có thể cung cấp RuntimeWiringConfigurer:

~~~java
@Configuration
public class GraphQlConfig {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> {
            // Đăng ký GraphQLScalarType DateTime tại đây.
        };
    }
}
~~~

Đây là ví dụ khung; phần đăng ký thực tế cần một GraphQLScalarType có coercing phù hợp với định dạng Java và wire format của API.

Cần phân biệt:

- SDL không thể parse: lỗi cú pháp.
- SDL parse được nhưng định nghĩa schema không hợp lệ: lỗi schema validation/generation.
- SDL hợp lệ nhưng custom scalar hoặc type resolver chưa được cấu hình: lỗi wiring hoặc lỗi khi thực thi, tùy thành phần và thời điểm kiểm tra.
- Field có schema nhưng không có resolver tùy chỉnh: GraphQL có thể dùng property data fetcher mặc định trên source object. Vì vậy, thiếu một method @SchemaMapping không nhất thiết làm schema parse thất bại; field có thể trả null nếu không tìm được property phù hợp.

Không nên sửa cú pháp SDL để giải quyết lỗi custom scalar hoặc data fetcher. Hãy xác định thành phần runtime đang thiếu và bổ sung wiring tương ứng.

## 10. Lỗi operation của client không phải schema parse error

Sau khi schema được nạp thành công, client vẫn có thể gửi operation không hợp lệ. Đây là lỗi parse hoặc validation của GraphQL document, không phải lỗi nạp schema lúc ứng dụng khởi động.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Client gửi field không tồn tại:

~~~graphql
query {
    book(id: "book-42") {
        id
        unknownField
    }
}
~~~

Schema vẫn hợp lệ; operation của client bị từ chối vì unknownField không thuộc Book.

Một số lỗi request thường gặp:

- Operation document sai cú pháp.
- Field không tồn tại trên type tương ứng.
- Thiếu argument non-null.
- Variable khai báo sai kiểu hoặc không được truyền.
- Object field thiếu selection set.
- Scalar field lại có selection set.
- Operation name không khớp khi document có nhiều operation.

Những lỗi này thường xuất hiện sau khi endpoint đã sẵn sàng. Đọc GraphQL response và log request để chẩn đoán; không cần thay đổi schema nếu schema hiện tại đã đúng hợp đồng.

## 11. Đọc log để tìm vị trí lỗi

Khi ứng dụng không khởi động do schema, log thường có exception gốc được bọc trong một hoặc nhiều exception của Spring. Không nên chỉ đọc dòng cuối cùng kiểu “Application run failed”. Hãy tìm phần Caused by sâu nhất và thông tin parser/schema generator cung cấp.

Các thông tin hữu ích:

| Thông tin | Cách sử dụng |
| --- | --- |
| Tên file hoặc resource | Xác định SDL nào gây lỗi hoặc không được tìm thấy. |
| Dòng và cột | Mở đúng vị trí trong file để kiểm tra token sai. |
| Tên type/field | Đối chiếu định nghĩa và nơi tham chiếu. |
| Thông báo expected token | Kiểm tra dấu ngoặc, colon hoặc cú pháp gần vị trí báo lỗi. |
| Tên scalar/interface/union | Kiểm tra implementation, type definition hoặc wiring. |
| Stack trace lúc khởi động | Xác định lỗi phát sinh khi tạo GraphQlSource hay từ bean cấu hình khác. |

Nếu log chỉ chỉ ra vị trí sau chỗ sai, hãy xem vài dòng trước và sau. Một dấu ngoặc nhọn bị thiếu có thể khiến parser báo lỗi tại khai báo type kế tiếp.

Không nên tắt logging hoặc bắt exception rồi tiếp tục khởi động với schema lỗi. Ứng dụng cần fail fast để tránh công bố một GraphQL API không đúng hợp đồng.

## 12. Quy trình chẩn đoán schema parse lỗi

Có thể đi theo thứ tự sau để khoanh vùng:

1. **Xác nhận tài nguyên được tìm thấy.** Kiểm tra file nằm trong classpath, phần mở rộng được hỗ trợ và schema locations đúng.
2. **Xác định file và vị trí lỗi.** Đọc exception gốc, tên resource, dòng và cột.
3. **Kiểm tra cú pháp SDL.** Đối chiếu block type, dấu hai chấm, argument, list, non-null, enum và directive.
4. **Kiểm tra type reference.** Xác nhận mọi type được tham chiếu đã tồn tại và dùng đúng vị trí input/output.
5. **Kiểm tra schema composition.** Tìm định nghĩa trùng, extension thiếu type gốc và field/argument trùng tên.
6. **Kiểm tra root operation và quan hệ type.** Xác nhận Query root, interface implementation, union members và input object cycles.
7. **Kiểm tra runtime wiring.** Xem custom scalar, type resolver và các thành phần cấu hình GraphQL.
8. **Gửi operation tối thiểu.** Sau khi ứng dụng khởi động, kiểm tra một query đơn giản rồi mở rộng dần đến field lồng nhau và arguments.

Sơ đồ quyết định nhanh:

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động thất bại?"] -->|Có| B["Tìm lỗi gốc trong Caused by"]
    A -->|Không| C["Endpoint đã sẵn sàng"]
    B --> D{"Có tìm thấy SDL?"}
    D -->|Không| E["Sửa classpath / schema locations"]
    D -->|Có| F{"Parser báo cú pháp?"}
    F -->|Có| G["Sửa SDL tại dòng/cột"]
    F -->|Không| H{"Schema validation thất bại?"}
    H -->|Có| I["Sửa type, root, extension, interface hoặc input"]
    H -->|Không| J["Kiểm tra runtime wiring và bean cấu hình"]
    C --> K{"Client operation lỗi?"}
    K -->|Có| L["Kiểm tra document, variables và selection set"]
    K -->|Không| M["Nếu resolver lỗi, kiểm tra service và data access"]
~~~

Khi sửa, chỉ thay đổi nguyên nhân đã xác định rồi khởi động lại và kiểm tra log mới. Nếu có nhiều lỗi, xử lý lỗi đầu tiên trước; một lỗi parse ban đầu có thể che khuất các lỗi schema phía sau.

## 13. Ví dụ tổng hợp: từ SDL lỗi đến schema hợp lệ

Giả sử ứng dụng có file book.graphqls:

~~~graphql
type Book {
    id ID!
    title: String!
}

type Query {
    book(id: ID!): Book
    books(filter: BookFilter): [Book!]!
}

type BookFilter {
    keyword: String
}
~~~

Có ba vấn đề:

1. Field id thiếu dấu hai chấm nên SDL không parse được.
2. BookFilter được khai báo bằng type nhưng dùng làm argument; đây là output object, không phải input type.
3. Nếu một file khác cũng khai báo type Query, schema composition có thể báo định nghĩa trùng.

Một bản sửa:

~~~graphql
input BookFilter {
    keyword: String
}

type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
    books(filter: BookFilter): [Book!]!
}
~~~

Nếu cần chia Query thành nhiều file, giữ định nghĩa gốc ở một file và dùng extension ở file khác:

~~~graphql
extend type Query {
    recentBooks(limit: Int = 10): [Book!]!
}
~~~

Sau khi sửa, khởi động lại ứng dụng và xác nhận GraphQL runtime được tạo thành công. Tiếp đó gửi query đơn giản:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Nếu operation này chạy được, có thể tiếp tục kiểm tra filter, nested mapping và các resolver phức tạp hơn.

## 14. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy schema resource | Sai classpath, vị trí hoặc phần mở rộng. | Kiểm tra src/main/resources/graphql/, schema locations và nội dung JAR. |
| Parser báo lỗi gần dấu ngoặc | Thiếu hoặc thừa {, }, (, ) hoặc dấu :. | Đọc cả các dòng trước vị trí parser báo. |
| Unknown type | Sai tên type hoặc file định nghĩa chưa được nạp. | Kiểm tra chính tả và schema locations. |
| Type dùng sai vị trí | Dùng type thay cho input hoặc ngược lại. | Phân biệt input type và output type. |
| Duplicate type/field | Nhiều file định nghĩa trùng thay vì mở rộng. | Dùng extend type và quản lý type gốc rõ ràng. |
| Query root không hợp lệ | Thiếu root Query hoặc schema definition trỏ sai type. | Khai báo object Query hoặc root operation tương ứng. |
| Interface validation thất bại | Object thiếu field hoặc có kiểu không tương thích. | Đối chiếu đầy đủ field mà interface yêu cầu. |
| Custom scalar không hoạt động | Thiếu hoặc sai scalar wiring/coercing. | Đăng ký GraphQLScalarType qua runtime wiring. |
| Ứng dụng khởi động được nhưng field trả null | Không có resolver phù hợp hoặc source object không có property tương ứng. | Kiểm tra property access và @SchemaMapping. |
| Client báo field không tồn tại | Operation không khớp schema hiện tại. | Sửa operation hoặc cập nhật schema có chủ đích. |

## 15. Những điểm cần ghi nhớ

- Spring Boot nạp SDL từ classpath theo schema locations; vị trí và phần mở rộng của file phải phù hợp cấu hình.
- Parse error là lỗi cú pháp; schema validation/generation error là lỗi trong quan hệ và quy tắc giữa các type.
- Runtime wiring, request validation và resolver execution là các giai đoạn riêng.
- Dùng extend type để mở rộng type đã khai báo khi schema được chia thành nhiều file.
- Kiểm tra root Query, input/output type position, duplicate definitions, interface implementation và union members.
- Đọc exception gốc, tên resource, dòng và cột trước khi sửa.
- Sau khi schema được xây dựng thành công, hãy kiểm tra operation đơn giản trước rồi mới kiểm tra resolver phức tạp.
- Không nhầm @SchemaMapping thiếu với lỗi SDL parse; một field có thể dùng property data fetcher mặc định.

Khi hiểu từng giai đoạn nạp và xây dựng schema, việc xử lý schema parse lỗi trong Spring for GraphQL sẽ có hệ thống hơn. Bắt đầu từ tài nguyên và exception gốc, xác định lớp lỗi, sửa đúng SDL hoặc runtime wiring rồi kiểm tra lại bằng một operation tối thiểu.

