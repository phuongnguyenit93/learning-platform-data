# Nhiều schema resource

Một GraphQL schema có thể chứa nhiều object type, input type, enum, scalar, interface, union và các root operation. Khi schema lớn dần, đặt toàn bộ SDL trong một file sẽ khiến việc tìm kiếm, review và phối hợp thay đổi trở nên khó khăn. Spring for GraphQL cho phép tổ chức schema thành nhiều resource SDL, sau đó Spring Boot tìm và kết hợp chúng thành một schema có thể thực thi.

Điều quan trọng là hiểu rằng việc chia file chỉ là cách tổ chức resource. GraphQL server vẫn sử dụng một schema thống nhất khi kiểm tra và thực thi operation. Các type và field phải hợp lệ khi xét trên toàn bộ tập resource đã nạp. Trong Spring Boot, vị trí resource và phần mở rộng file được cấu hình qua các thuộc tính **spring.graphql.schema.***.

Bài này trình bày cách chia SDL theo domain, cách định nghĩa và mở rộng type giữa các file, cách Spring Boot tìm nhiều schema resource, cách kiểm tra classpath và đóng gói, cùng các lỗi thường gặp khi hợp nhất schema.

## 1. Vì sao chia schema thành nhiều resource?

Một schema nhỏ có thể bắt đầu trong một file:

~~~graphql
type Query {
  book(id: ID!): Book
  authors: [Author!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
~~~

Khi API phát triển, schema có thể bổ sung hàng chục hoặc hàng trăm type và field. Một file duy nhất dễ gặp các vấn đề:

- Khó tìm định nghĩa của một domain type.
- Nhiều người cùng sửa một file và dễ tạo xung đột khi merge.
- Khó review thay đổi vì các nghiệp vụ không liên quan nằm cạnh nhau.
- File schema dài làm việc đọc và bảo trì kém thuận tiện.
- Khó tách phần dùng chung với phần đặc thù của từng domain.

Có thể chia schema theo nhóm nghiệp vụ:

~~~text
src/main/resources/
└── graphql/
    ├── common.graphqls
    ├── book/
    │   ├── book.graphqls
    │   ├── book-query.graphqls
    │   └── book-relations.graphqls
    ├── author/
    │   ├── author.graphqls
    │   └── author-query.graphqls
    └── order/
        ├── order.graphqls
        └── order-mutation.graphqls
~~~

Mỗi file có thể tập trung vào một nhóm type hoặc một phần mở rộng. Spring Boot nạp các resource phù hợp với location pattern và kết hợp định nghĩa của chúng.

Chia file giúp tổ chức source code, nhưng không tạo ra nhiều GraphQL endpoint hoặc nhiều schema độc lập. Nếu client gọi cùng một GraphQL server, operation vẫn được kiểm tra trên schema tổng hợp.

## 2. Spring Boot tìm schema resource ở đâu?

Với Spring Boot và Spring for GraphQL, các file SDL thường được đặt trong resource directory:

~~~text
src/main/resources/graphql/
~~~

Vị trí mặc định thường được biểu diễn bằng resource pattern:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
~~~

Spring Boot tìm các file schema trong vị trí đã cấu hình. Các phần mở rộng thường được hỗ trợ mặc định là:

~~~properties
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

Có thể ghi rõ các thuộc tính trong **application.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

Hoặc dùng YAML:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
      file-extensions:
        - .graphqls
        - .gqls
~~~

Các giá trị trên làm rõ resource pattern và loại file được tìm kiếm. Nếu dùng cấu hình mặc định của phiên bản Spring Boot đang chạy, không nhất thiết phải khai báo lại chúng.

### Ý nghĩa của classpath resource

Tiền tố **classpath:** chỉ resource được tìm trên classpath của ứng dụng. Khi chạy trong IDE, resource thường được copy vào output directory. Khi đóng gói JAR, resource nằm bên trong artifact và được đọc từ classpath lúc runtime.

Do đó, không nên đặt schema trong một đường dẫn máy cá nhân rồi kỳ vọng ứng dụng production tự tìm thấy file. Một đường dẫn tương đối theo working directory có thể hoạt động trên máy phát triển nhưng thất bại trong container hoặc khi chạy từ thư mục khác.

Nếu schema được phân phối từ nhiều module hoặc dependency JAR, cần kiểm tra resource pattern có tìm được các resource ở mọi vị trí classpath mong muốn hay không. Có thể cần pattern dạng **classpath*:** tùy cách đóng gói và cơ chế resource resolution của ứng dụng. Hãy xác minh trên artifact thực tế thay vì chỉ kiểm tra khi chạy từ IDE.

## 3. Cách Spring kết hợp nhiều SDL file

Spring Boot tìm các schema resource theo cấu hình rồi chuyển chúng tới quá trình xây dựng GraphQL schema. GraphQL Java phân tích các định nghĩa SDL đã nạp và xây dựng một schema tổng hợp.

Ví dụ file **book.graphqls**:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

File **author.graphqls**:

~~~graphql
type Author {
  id: ID!
  name: String!
}

extend type Query {
  authors: [Author!]!
}
~~~

Sau khi các resource được nạp, schema tổng hợp có root Query với cả field **book** và **authors**, cùng hai object type **Book** và **Author**.

Việc kết hợp không có nghĩa nội dung các file được nối thành văn bản tùy ý rồi bỏ qua quy tắc GraphQL. Tập định nghĩa cuối cùng vẫn phải hợp lệ:

- Mọi type được tham chiếu phải tồn tại.
- Mỗi type phải có định nghĩa hợp lệ.
- Field không được định nghĩa trùng gây xung đột.
- Các phần mở rộng phải phù hợp với type gốc.
- Root operation type phải được xác định đúng.
- Interface, union, input và enum phải tuân thủ quy tắc type system.

Nếu một file không hợp lệ, schema có thể không được tạo và ứng dụng thường thất bại trong quá trình khởi động. Đây là hành vi hữu ích vì lỗi schema được phát hiện sớm, thay vì đợi đến khi client gọi field có vấn đề.

## 4. Dùng type và extend type giữa các file

Khi chia SDL, một file thường định nghĩa type gốc; các file khác có thể mở rộng type đó bằng **extend type**.

Ví dụ file **book.graphqls** định nghĩa:

~~~graphql
type Book {
  id: ID!
  title: String!
}

type Query {
  book(id: ID!): Book
}
~~~

File **book-relations.graphqls** bổ sung quan hệ:

~~~graphql
type Author {
  id: ID!
  name: String!
}

extend type Book {
  author: Author!
}
~~~

File **book-search.graphqls** mở rộng root Query:

~~~graphql
extend type Query {
  booksByTitle(prefix: String!): [Book!]!
}
~~~

Schema tổng hợp có các field:

- **Query.book**
- **Query.booksByTitle**
- **Book.id**
- **Book.title**
- **Book.author**
- **Author.id**
- **Author.name**

**extend type** giúp phân chia trách nhiệm giữa các file. Tuy nhiên, type được mở rộng phải có định nghĩa trong schema tổng hợp. Không thể mở rộng một type không tồn tại chỉ vì file mở rộng được nạp cùng thư mục.

### Chỉ định nghĩa type gốc một lần

Nên có một nơi định nghĩa type gốc và dùng extension ở các file còn lại. Ví dụ:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Ở file khác:

~~~graphql
extend type Query {
  authors: [Author!]!
}
~~~

Không nên lặp lại **type Query** trong nhiều file với mục đích bổ sung field. GraphQL SDL có cú pháp extension dành cho việc đó. Dùng nhiều định nghĩa type gốc cùng tên có thể tạo lỗi schema khi parser hợp nhất.

Mutation và Subscription cũng có thể được mở rộng theo cách tương tự:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

File khác:

~~~graphql
extend type Mutation {
  archiveBook(id: ID!): Book!
}
~~~

Root Mutation và Subscription là tùy chọn. Nếu schema có dùng chúng, hãy định nghĩa root type gốc trước khi các file khác mở rộng.

## 5. Một cách tổ chức schema theo domain

Với một ứng dụng catalog, có thể tổ chức file theo domain và loại khai báo:

~~~text
graphql/
├── common/
│   ├── scalars.graphqls
│   └── pagination.graphqls
├── book/
│   ├── book-types.graphqls
│   ├── book-inputs.graphqls
│   ├── book-queries.graphqls
│   ├── book-mutations.graphqls
│   └── book-relations.graphqls
├── author/
│   ├── author-types.graphqls
│   ├── author-queries.graphqls
│   └── author-relations.graphqls
└── order/
    ├── order-types.graphqls
    ├── order-inputs.graphqls
    └── order-mutations.graphqls
~~~

Ví dụ **common/scalars.graphqls**:

~~~graphql
scalar DateTime
scalar Money
~~~

Ví dụ **book/book-types.graphqls**:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  title: String!
  status: BookStatus!
}
~~~

Ví dụ **book/book-queries.graphqls**:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Ví dụ **author/author-queries.graphqls**:

~~~graphql
type Author {
  id: ID!
  name: String!
}

extend type Query {
  author(id: ID!): Author
}
~~~

Ví dụ **book/book-relations.graphqls**:

~~~graphql
extend type Book {
  author: Author
}
~~~

Cách chia này giúp developer tìm được định nghĩa theo domain. Một nhóm thích file theo feature có thể đặt type, input và field liên quan cùng thư mục; nhóm khác thích tách type/input/query/mutation thành các file riêng. Cả hai đều hợp lệ nếu cấu trúc rõ ràng và không tạo trùng lặp.

### Không chia file quá nhỏ một cách máy móc

Mỗi file nên có một lý do tồn tại. Một file cho mỗi field có thể làm việc điều hướng khó hơn và tạo nhiều extension rải rác. Ngược lại, một file khổng lồ cho mọi domain cũng làm giảm lợi ích của việc phân chia.

Hãy chọn ranh giới theo:

- Domain hoặc bounded context.
- Nhóm type và quan hệ có liên quan.
- Quyền sở hữu của team.
- Tần suất thay đổi và cách review.
- Khả năng tái sử dụng giữa các phần schema.

## 6. Nhiều resource không phải là cơ chế import SDL

GraphQL SDL tiêu chuẩn không có câu lệnh **import** hoặc **include** phổ quát để một file tự nạp file khác. Trong Spring Boot, việc tìm nhiều file là trách nhiệm của cấu hình resource loading và schema builder.

Ví dụ, không nên tự giả định cú pháp sau được GraphQL Java hiểu:

~~~graphql
import "book.graphqls"
~~~

Đây không phải cú pháp import chuẩn của GraphQL SDL. Thay vào đó, đặt các file trong resource location được cấu hình để Spring Boot nạp tất cả, hoặc tùy biến schema resource builder khi có yêu cầu đặc biệt.

Tương tự, **extend type** không phải là import file. Nó là cú pháp GraphQL để mở rộng một type đã tồn tại trong schema tổng hợp.

Phân biệt ba khái niệm:

| Khái niệm | Trách nhiệm |
|---|---|
| Resource location/pattern | Chỉ ra nơi Spring tìm file SDL |
| Nạp nhiều schema resource | Thu thập các file và đưa vào schema builder |
| **extend type** | Mở rộng định nghĩa GraphQL type trong schema |

Hiểu đúng ba lớp này giúp tránh tìm kiếm một cú pháp import không tồn tại trong SDL tiêu chuẩn.

## 7. Cấu hình vị trí schema theo môi trường

Thông thường, schema là một phần của ứng dụng và được đóng gói cùng artifact. Nếu có lý do cần thay đổi resource location, có thể cấu hình qua profile.

**application.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

**application-test.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql-test/
~~~

**application-prod.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql/
~~~

Kích hoạt profile bằng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=test
~~~

Tuy nhiên, dùng schema khác nhau giữa test và production có thể khiến test không phản ánh đúng hợp đồng được triển khai. Với phần lớn dự án, nên dùng cùng schema resource và thay đổi dữ liệu, service hoặc cấu hình runtime theo môi trường. Chỉ tách schema location khi có yêu cầu cụ thể và có kiểm tra để bảo đảm hai schema không lệch nhau ngoài ý muốn.

Nếu schema được cung cấp từ một thư mục ngoài artifact, cần xác định cách đóng gói, mount volume và quyền đọc file của process. Không nên dùng đường dẫn local của developer làm cấu hình production.

## 8. Mở rộng schema bằng Java khi cần

Trong trường hợp cấu hình resource đơn giản không đáp ứng yêu cầu, Spring Boot cho phép tùy biến quá trình tạo GraphQlSource thông qua các extension point như **GraphQlSourceBuilderCustomizer** hoặc cấu hình GraphQlSource phù hợp với phiên bản đang dùng.

Các tình huống có thể cần tùy biến:

- Resource schema được cung cấp động từ một nguồn đã được kiểm soát.
- Cần đăng ký custom scalar hoặc TypeResolver.
- Cần thêm runtime wiring cho data fetcher, directive hoặc instrumentation.
- Cần kiểm soát việc xây dựng schema ngoài auto-configuration mặc định.

Với phần lớn ứng dụng, nên bắt đầu bằng **spring.graphql.schema.locations** và các resource SDL tĩnh. Chỉ dùng Java customization khi có nhu cầu cụ thể, vì tự tạo GraphQlSource hoặc thay thế bean mặc định có thể khiến một phần auto-configuration không còn được áp dụng.

Ví dụ về runtime wiring thường được đăng ký qua bean **RuntimeWiringConfigurer**:

~~~java
@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> {
            // Đăng ký custom scalar, TypeResolver hoặc data fetcher
            // phù hợp với schema đã nạp.
        };
    }
}
~~~

Bean này bổ sung runtime wiring cho schema. Nó không tự thay thế việc tìm và nạp SDL resource. Hai trách nhiệm cần được phân biệt: schema resource mô tả type và field; runtime wiring cung cấp cách thực thi các field hoặc cách chuyển đổi giá trị.

## 9. Kiểm tra resource đã được đóng gói

Một lỗi thường gặp là schema hoạt động trong IDE nhưng không được tìm thấy khi chạy JAR. Nguyên nhân thường nằm ở resource path, file extension hoặc quá trình build artifact.

Hãy kiểm tra:

1. File SDL nằm trong **src/main/resources** hoặc resource source set được cấu hình đúng.
2. File có phần mở rộng nằm trong **spring.graphql.schema.file-extensions**.
3. Resource pattern bao phủ đúng thư mục con.
4. Profile đang chạy không ghi đè location thành một đường dẫn không tồn tại.
5. File SDL thực sự được đóng gói trong JAR.
6. Nếu resource đến từ dependency khác, classpath pattern có tìm thấy resource đó không.

Có thể dùng lệnh JDK để liệt kê nội dung JAR:

~~~bash
jar tf build/libs/book-catalog.jar
~~~

Tìm các đường dẫn như:

~~~text
BOOT-INF/classes/graphql/book/book-types.graphqls
BOOT-INF/classes/graphql/author/author-types.graphqls
~~~

Nếu file không xuất hiện trong JAR, vấn đề nằm ở resource packaging trước khi Spring GraphQL bắt đầu nạp schema.

## 10. Kiểm tra schema tổng hợp

Một schema được chia thành nhiều file vẫn cần được kiểm tra như một hợp đồng duy nhất. Có thể kiểm tra ở nhiều mức:

### Kiểm tra khi ứng dụng khởi động

Spring Boot tạo GraphQlSource khi application context được khởi tạo. SDL sai cú pháp, type không tồn tại hoặc extension không hợp lệ có thể khiến ứng dụng không khởi động được.

Đây là lý do nên để ứng dụng kiểm tra schema ngay trong test context. Không nên trì hoãn việc phát hiện lỗi cho tới khi triển khai production.

### Kiểm thử operation bằng GraphQlTester

Sau khi schema được nạp, có thể dùng GraphQlTester kiểm tra field được định nghĩa ở các resource khác nhau vẫn hoạt động:

~~~java
@SpringBootTest
class BookSchemaIntegrationTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveBookAndAuthorFields() {
        graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

Test này kiểm tra schema tổng hợp, mapping resolver và dữ liệu test. Nó không chỉ xác nhận một file riêng lẻ được đọc, mà xác nhận các định nghĩa phối hợp được trong một operation.

### Kiểm tra toàn bộ schema trong CI

Trong pipeline, nên khởi tạo Spring application context hoặc chạy integration test có GraphQlSource để phát hiện lỗi schema trước khi đóng gói và triển khai. Nếu dự án có quy tắc tương thích schema, có thể bổ sung kiểm tra breaking change giữa schema hiện tại và schema của phiên bản trước.

## 11. Các lỗi thường gặp khi chia nhiều schema resource

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng không tìm thấy Query | Chưa có root Query hoặc resource chứa Query không được nạp | Kiểm tra root type và location pattern |
| **extend type Query** báo type không tồn tại | File định nghĩa gốc không nằm trong tập resource được nạp | Kiểm tra location, extension và tên type |
| Trùng định nghĩa type | Nhiều file định nghĩa cùng type gốc | Giữ một định nghĩa gốc, dùng **extend type** |
| Field bị khai báo trùng | Nhiều extension cùng thêm một field | Tìm và loại bỏ định nghĩa trùng |
| Type không tồn tại | Tên type sai hoặc resource chứa type bị bỏ sót | Kiểm tra tham chiếu và file packaging |
| SDL chạy trong IDE nhưng lỗi trong JAR | Resource không được đóng gói hoặc path khác | Kiểm tra nội dung artifact và classpath |
| Một file không được đọc | Extension không nằm trong danh sách được tìm | Kiểm tra **.graphqls**/**.gqls** và file-extensions |
| Cấu hình profile không có tác dụng | Profile chưa active hoặc property bị override | Kiểm tra active profile và nguồn cấu hình |
| Nghĩ **extend type** tự tìm file | Nhầm type extension với resource loading | Cấu hình resource locations riêng |
| Schema test khác production | Dùng location khác nhau giữa profile | Kiểm tra cùng schema hoặc quản lý khác biệt có chủ đích |

Khi có lỗi, nên xem thông báo khởi động của GraphQL schema parser. Lỗi thường chỉ ra tên type, field hoặc extension gây xung đột. Hãy sửa đúng định nghĩa gốc hoặc resource pattern, thay vì thêm một type trùng tên để thử khắc phục.

## 12. Nguyên tắc tổ chức nhiều schema resource

Một số nguyên tắc giúp schema dễ bảo trì:

- **Một type gốc, nhiều phần mở rộng có kiểm soát:** tránh nhiều file cùng định nghĩa một type.
- **Chia theo domain:** đặt type, input và field liên quan gần nhau.
- **Tên file có ý nghĩa:** tên file nên giúp developer biết nó chứa loại khai báo nào.
- **Giữ root type rõ ràng:** định nghĩa root Query/Mutation/Subscription ở nơi dễ tìm; dùng extension để bổ sung field.
- **Tránh phụ thuộc thứ tự file:** schema tổng hợp cần hợp lệ bất kể thứ tự resource được tìm thấy.
- **Không dùng import giả định:** để Spring quản lý resource discovery; dùng **extend type** cho type extension.
- **Kiểm tra artifact:** bảo đảm schema resource có trong JAR hoặc image được triển khai.
- **Kiểm thử schema tổng hợp:** chạy test context và operation đại diện trong CI.
- **Review thay đổi như API contract:** thay đổi field, nullability và root operation có thể ảnh hưởng client.

## 13. Quy trình thêm một schema resource mới

Khi bổ sung domain mới vào GraphQL API, có thể thực hiện:

1. Xác định domain và các object/input/enum/scalar cần công khai.
2. Tìm root type và các type hiện có mà domain cần tham chiếu.
3. Đặt file **.graphqls** hoặc **.gqls** trong resource location phù hợp.
4. Định nghĩa type mới; dùng **extend type** khi bổ sung field cho type đã tồn tại.
5. Kiểm tra không có type hoặc field bị định nghĩa trùng.
6. Bổ sung resolver và runtime wiring tương ứng trong Spring for GraphQL.
7. Khởi tạo application context để xác nhận schema được nạp và hợp lệ.
8. Viết GraphQlTester cho operation đi qua các type vừa thêm.
9. Kiểm tra resource xuất hiện trong artifact build.
10. Đưa schema test vào CI để lỗi được phát hiện trước khi triển khai.

Nhiều schema resource giúp chia SDL thành các phần nhỏ theo domain và dễ phối hợp phát triển. Spring Boot tìm resource theo location và phần mở rộng đã cấu hình; GraphQL Java kết hợp các định nghĩa thành một schema thống nhất. **extend type** dùng để mở rộng type đã có, còn resolver và runtime wiring trong Spring for GraphQL cung cấp hành vi thực thi. Khi tổ chức resource rõ ràng, tránh định nghĩa trùng và kiểm tra schema tổng hợp trong CI, ứng dụng có thể mở rộng GraphQL API mà vẫn giữ được hợp đồng nhất quán cho client.
