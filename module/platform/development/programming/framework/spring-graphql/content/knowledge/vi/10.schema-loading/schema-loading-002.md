# Schema file trong classpath

Spring for GraphQL thường sử dụng cách tiếp cận **schema-first**: API được mô tả bằng GraphQL SDL trong các file tài nguyên, còn controller và resolver Java cung cấp dữ liệu cho những field đã khai báo. Với Spring Boot, bạn không cần tự đọc từng file SDL hay ghép chúng thành một chuỗi. Auto-configuration tìm schema resources trên classpath, nạp chúng và xây dựng schema runtime cho GraphQL Java.

Vị trí mặc định là `classpath:graphql/**/`; các file có phần mở rộng `.graphqls` hoặc `.gqls` được nhận diện theo cấu hình mặc định. Có thể chia schema thành nhiều file và thư mục theo domain, miễn là các định nghĩa kết hợp lại tạo thành một schema hợp lệ.

Bài học này giải thích classpath resource, vị trí và phần mở rộng mặc định, cách tổ chức nhiều file SDL, cách cấu hình vị trí tùy chỉnh, ảnh hưởng của quá trình đóng gói ứng dụng và cách chẩn đoán khi Spring không tìm thấy schema.

## 1. Classpath resource là gì?

Classpath là tập hợp thư mục và thư viện mà JVM sử dụng để tìm class cùng tài nguyên khi ứng dụng chạy. Trong dự án Spring Boot, tài nguyên đặt trong `src/main/resources` thường được sao chép vào classpath khi build.

Ví dụ cấu trúc dự án:

```text
src/
└── main/
    ├── java/
    │   └── com/example/library/
    │       ├── LibraryApplication.java
    │       └── graphql/
    │           └── BookController.java
    └── resources/
        ├── application.yml
        └── graphql/
            ├── book.graphqls
            ├── author.graphqls
            └── review/
                └── review.graphqls
```

Sau khi build, resource thường nằm trong thư mục output của build tool, chẳng hạn `build/resources/main` với Gradle hoặc `target/classes` với Maven. Khi đóng gói Spring Boot executable JAR, các resource ứng dụng được đưa vào phần classpath của JAR, thường dưới `BOOT-INF/classes/`.

Điều này có nghĩa ứng dụng chạy từ IDE, từ thư mục build hoặc từ executable JAR vẫn có thể tìm schema bằng cùng một classpath location. Không nên phụ thuộc vào đường dẫn tương đối của máy phát triển như `C:/project/src/main/resources/graphql` vì đường dẫn đó không tồn tại trong môi trường triển khai.

## 2. Vị trí schema mặc định của Spring Boot

Khi dùng `spring-boot-starter-graphql`, Spring Boot tự cấu hình `GraphQlSource` để tìm SDL resources. Vị trí mặc định là:

```text
classpath:graphql/**/
```

Pattern này tìm tài nguyên trong thư mục `graphql` ở classpath, bao gồm các thư mục con. Vì vậy cả hai vị trí sau đều được tìm:

```text
src/main/resources/graphql/book.graphqls
src/main/resources/graphql/review/review.graphqls
```

Theo mặc định, Spring Boot nhận các phần mở rộng:

| Phần mở rộng | Mục đích |
| --- | --- |
| `.graphqls` | File GraphQL SDL |
| `.gqls` | Phần mở rộng ngắn cho GraphQL SDL |

Tên file không quyết định tên GraphQL type. Ví dụ `book.graphqls` có thể khai báo `Book`, `Query`, `Mutation` hoặc các type khác. Tên file và thư mục chủ yếu giúp nhóm tài nguyên để nhóm phát triển dễ quản lý.

Các file `.graphql` hoặc `.txt` không thuộc danh sách phần mở rộng mặc định. Nếu dùng phần mở rộng khác, cần cấu hình `spring.graphql.schema.file-extensions` tương ứng.

## 3. Tạo schema file đầu tiên

Tạo file `src/main/resources/graphql/book.graphqls`:

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
```

File này khai báo root query type và object type `Book`. Sau khi ứng dụng khởi động, GraphQL schema runtime sẽ có các field `Query.book`, `Query.books` và các field của `Book`.

Controller Java cung cấp giá trị cho root field:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

File SDL và controller có trách nhiệm khác nhau:

- SDL định nghĩa field có thể được client gọi, arguments, kiểu trả về và nullability.
- `@QueryMapping` ánh xạ một method Java vào field của root `Query`.
- Service và repository quyết định dữ liệu được tải như thế nào.

Đặt file đúng classpath location chỉ làm schema được nạp. Nó không tự tạo resolver cho field. Nếu schema có `Query.book` nhưng không có data fetcher hoặc property fetcher phù hợp, query có thể trả `null` hoặc lỗi tùy kiểu field và cách thực thi.

## 4. Chia schema thành nhiều file theo domain

Một schema nhỏ có thể nằm trong một file. Khi API phát triển, nên chia SDL theo domain hoặc nhóm type để mỗi file có phạm vi dễ hiểu.

Ví dụ:

```text
src/main/resources/graphql/
├── common/
│   └── scalars.graphqls
├── book/
│   └── book.graphqls
├── author/
│   └── author.graphqls
└── review/
    └── review.graphqls
```

File `book.graphqls` định nghĩa root query và kiểu sách:

```graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author
}
```

File `author.graphqls` bổ sung truy vấn tác giả:

```graphql
extend type Query {
  author(id: ID!): Author
  authors: [Author!]!
}

type Author {
  id: ID!
  name: String!
  biography: String
}
```

File `review.graphqls` khai báo review và mở rộng type `Book`:

```graphql
extend type Book {
  reviews: [Review!]!
}

type Review {
  id: ID!
  rating: Int!
  comment: String
}
```

Spring Boot nạp các SDL resource theo schema locations rồi GraphQL Java xây dựng một schema thống nhất từ các type definition và type extension. Client nhìn thấy một API GraphQL duy nhất; các file riêng chỉ là cách tổ chức source schema.

### Dùng type extension khi bổ sung field

Nếu `Query` đã được định nghĩa trong `book.graphqls`, file khác muốn bổ sung field nên dùng:

```graphql
extend type Query {
  author(id: ID!): Author
}
```

Tương tự, muốn thêm field cho `Book` đã tồn tại thì dùng `extend type Book`.

Không khai báo lại `type Query` hoặc `type Book` trong file thứ hai chỉ để thêm field. Một schema không thể có hai định nghĩa type độc lập cùng tên. Type extension được thiết kế để bổ sung field hoặc directive vào type đã có.

Type được mở rộng phải tồn tại trong schema sau khi các resource được nạp. Nếu dùng `extend type Review` nhưng không có file nào định nghĩa `type Review`, schema validation sẽ thất bại khi xây dựng schema.

## 5. Thứ tự nạp file không phải cơ chế phụ thuộc

Không nên thiết kế schema với giả định file `book.graphqls` luôn được nạp trước `author.graphqls` chỉ vì tên file hoặc thứ tự thư mục. Các SDL resources được tổng hợp để tạo schema; hãy để quan hệ type được thể hiện bằng định nghĩa và extension hợp lệ.

Ví dụ, `Book` tham chiếu `Author` dù `Author` được định nghĩa trong file khác:

```graphql
type Book {
  id: ID!
  author: Author
}
```

Điều này hợp lệ khi toàn bộ schema resources có định nghĩa `Author`. Nếu resource đó không nằm trong các schema locations hoặc không có trong classpath, schema không thể resolve type tham chiếu.

Các nguyên tắc khi chia file:

- Mỗi GraphQL type chỉ có một định nghĩa gốc.
- Các file khác dùng `extend type` để bổ sung field.
- Tên type, field, argument và enum value phải nhất quán.
- Custom scalar phải có khai báo SDL và runtime wiring tương ứng.
- Không dùng tên file làm namespace; `Book` ở hai thư mục khác nhau vẫn là cùng một GraphQL type name.

## 6. Cấu hình schema locations

Có thể đổi vị trí mặc định bằng thuộc tính `spring.graphql.schema.locations`.

Ví dụ dùng một thư mục riêng:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:api-schema/**/
```

Khi đó, đặt các file SDL trong:

```text
src/main/resources/api-schema/
├── query.graphqls
└── book/
    └── book.graphqls
```

Có thể cấu hình nhiều locations:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
        - classpath:shared-graphql/**/
```

Điều này hữu ích khi schema được chia thành phần dùng chung và phần riêng của ứng dụng. Mọi location phải trỏ tới resource có mặt trên classpath hoặc resource location hợp lệ mà Spring có thể đọc.

### Cấu hình phần mở rộng file

Mặc định Spring Boot tìm `.graphqls` và `.gqls`. Nếu dự án muốn dùng một phần mở rộng khác, có thể khai báo:

```yaml
spring:
  graphql:
    schema:
      file-extensions:
        - .graphqls
        - .gqls
        - .graphql
```

Khi thêm `.graphql`, các file có phần mở rộng đó trong locations được cấu hình cũng có thể được nhận diện là schema resources. Nên thống nhất một hoặc hai phần mở rộng trong dự án để người phát triển dễ nhận biết file SDL.

### Cấu hình đầy đủ trong application.yml

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
      file-extensions:
        - .graphqls
        - .gqls
    path: /graphql
```

`spring.graphql.path` là HTTP endpoint của GraphQL. Nó độc lập với `spring.graphql.schema.locations`: một thuộc tính xác định nơi tìm SDL, thuộc tính còn lại xác định URL nhận request.

## 7. Resource trong main và test classpath

Tài nguyên trong `src/main/resources` được đóng gói cùng ứng dụng và dùng khi chạy thật. Tài nguyên trong `src/test/resources` được thêm vào classpath khi chạy test.

Ví dụ:

```text
src/
├── main/resources/graphql/
│   └── book.graphqls
└── test/resources/graphql/
    └── test-fixture.graphqls
```

Trong test, classpath thường chứa cả resource main và resource test. Với schema locations mặc định có thể quét `graphql/**/`, file test đặt cùng pattern có thể được nạp cùng schema chính trong test context. Điều này có thể hữu ích nếu file fixture là một phần schema test, nhưng gây lỗi duplicate type nếu nó định nghĩa lại type đã có.

Nếu cần schema riêng cho test, hãy cấu hình schema locations cho test một cách tường minh hoặc đặt fixture ngoài pattern được ứng dụng quét mặc định. Không nên vô tình đặt một schema hoàn chỉnh thứ hai vào `src/test/resources/graphql/` rồi mong nó thay thế schema chính.

Tương tự, không đặt schema cần chạy production chỉ trong `src/test/resources`; resource đó không được đóng gói vào artifact ứng dụng.

## 8. Kiểm tra schema có thực sự nằm trong artifact

Một lỗi phổ biến là ứng dụng chạy được trong IDE nhưng không tìm thấy schema khi triển khai. Nguyên nhân thường nằm ở cấu hình resource của build tool hoặc tên file không khớp phần mở rộng được tìm kiếm.

Với Gradle, tài nguyên trong `src/main/resources` được xử lý bởi source set `main` và đưa vào output resources. Với Maven, `src/main/resources` là thư mục resource mặc định. Nếu đã tùy chỉnh `sourceSets`, `processResources` hoặc `resources` trong build, hãy kiểm tra schema có được copy vào output hay không.

Khi đóng gói JAR, có thể kiểm tra nội dung artifact bằng công cụ `jar`:

```bash
jar tf build/libs/library-api.jar
```

Với Maven, thay bằng đường dẫn JAR trong `target/`. Trong danh sách entry, kiểm tra có các file dạng:

```text
BOOT-INF/classes/graphql/book.graphqls
BOOT-INF/classes/graphql/author/author.graphqls
```

Nếu không có các entry đó, lỗi nằm ở quá trình đóng gói resource trước khi Spring GraphQL được khởi tạo. Nếu file có trong JAR nhưng schema vẫn không được nạp, hãy kiểm tra lại `spring.graphql.schema.locations` và `file-extensions`.

## 9. Nạp schema bằng cấu hình Java khi cần tùy biến

Với ứng dụng thông thường, nên dùng `spring.graphql.schema.locations` để Spring Boot tự nạp classpath resources. Chỉ cân nhắc tự khai báo `GraphQlSource` khi cần kiểm soát cách tạo schema, runtime wiring hoặc nguồn tài nguyên.

Khi ứng dụng tự khai báo bean `GraphQlSource`, auto-configuration mặc định có thể lùi lại vì đã có bean cùng loại. Khi đó ứng dụng chịu trách nhiệm cấu hình đầy đủ schema resources và runtime wiring cần thiết. Không nên thêm một `GraphQlSource` tùy biến chỉ để đổi thư mục SDL nếu thuộc tính cấu hình đã đáp ứng được yêu cầu.

Một cấu hình programmatic có thể sử dụng `GraphQlSource.schemaResourceBuilder()` và cung cấp danh sách `Resource` tường minh. Cú pháp chi tiết phụ thuộc phiên bản Spring for GraphQL; hãy đối chiếu Javadoc đúng phiên bản trước khi tùy biến builder. Sau khi tự tạo `GraphQlSource`, cần kiểm tra cả schema, runtime wiring, scalar, type resolver và các thành phần khác vốn được cấu hình tự động.

## 10. Schema file và controller là hai cơ chế discovery riêng

Spring Boot tìm SDL resources trên classpath. Spring for GraphQL cũng cần phát hiện các controller có annotation như `@Controller`, `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` và `@SchemaMapping`.

Hai quá trình này độc lập:

| Thành phần | Được tìm ở đâu? | Vai trò |
| --- | --- | --- |
| SDL schema | Classpath resources theo schema locations và extensions | Định nghĩa contract GraphQL |
| Controller/resolver | Spring application context qua component scanning hoặc cấu hình bean | Cung cấp dữ liệu cho field |
| Runtime wiring | Bean `RuntimeWiringConfigurer` và cấu hình GraphQL | Đăng ký scalar, type resolver hoặc data fetcher tùy biến |

Có file `book.graphqls` không có nghĩa `BookController` tự động được phát hiện nếu controller nằm ngoài component scan. Ngược lại, controller có `@QueryMapping` cũng không thể làm cho field xuất hiện trong schema nếu SDL không khai báo field đó.

Khi một field được khai báo trong schema nhưng không có resolver tùy biến, GraphQL có thể dùng property data fetcher mặc định để đọc property/getter tương ứng trên source object. Nếu không có property phù hợp, kết quả có thể là null; với field non-null, điều này có thể dẫn đến execution error.

## 11. Kiểm thử schema file được nạp

Nên có test xác nhận schema resources được tìm thấy và operation đại diện có thể thực thi. `GraphQlTester` kiểm tra document và response ở tầng GraphQL:

```java
@GraphQlTest(BookController.class)
class BookSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void bookQueryIsAvailableInLoadedSchema() {
        graphQlTester.document("""
                query {
                    __type(name: "Query") {
                        fields {
                            name
                        }
                    }
                }
                """)
                .execute()
                .path("__type.fields[*].name")
                .entityList(String.class)
                .contains("book");
    }
}
```

Ví dụ này dùng introspection để kiểm tra field `book` có trong schema runtime. Nếu ứng dụng chủ động tắt introspection trong test profile, hãy kiểm tra bằng cách thực thi operation thực tế thay vì truy vấn `__type`.

Có thể kiểm tra trực tiếp operation:

```java
graphQlTester.document("""
        query {
            book(id: "book-1") {
                id
                title
            }
        }
        """)
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-1");
```

Test đầy đủ cần mock hoặc seed dữ liệu phù hợp với `BookService`. Mục tiêu là xác nhận cả SDL được nạp lẫn resolver được kết nối với field.

`@GraphQlTest` phù hợp với test slice cho GraphQL controller và schema. `@SpringBootTest` hữu ích khi muốn kiểm tra cấu hình ứng dụng đầy đủ, bao gồm resource locations, component scanning và các bean runtime wiring.

## 12. Lỗi thường gặp khi nạp schema từ classpath

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy schema | File nằm ngoài `classpath:graphql/**/` | Kiểm tra vị trí trong `src/main/resources` và `spring.graphql.schema.locations` |
| File không được nạp | Phần mở rộng không thuộc danh sách được cấu hình | Kiểm tra `.graphqls`, `.gqls` và `spring.graphql.schema.file-extensions` |
| Chạy IDE được nhưng chạy JAR lỗi | Build không đóng gói file SDL | Kiểm tra `build/resources/main`, `target/classes` và nội dung JAR |
| `There is no type ...` hoặc lỗi type reference | Một type được tham chiếu nhưng không có định nghĩa trong schema resources | Kiểm tra các file SDL được nạp và type extension |
| Duplicate type definition | Nhiều file khai báo lại cùng type thay vì dùng `extend type` | Giữ một định nghĩa gốc và chuyển phần bổ sung sang extension |
| Field không tồn tại khi query | SDL không khai báo field hoặc file chứa field không được nạp | Kiểm tra schema runtime bằng introspection hoặc test operation |
| Field trả null dù SDL hợp lệ | Chưa có resolver hoặc source object không có property tương ứng | Kiểm tra controller mapping và property fetcher |
| Test context lỗi duplicate schema | File trong `src/test/resources/graphql` được nạp cùng file main | Kiểm tra test resources và schema locations của test |
| Custom scalar không dùng được | SDL có `scalar X` nhưng runtime wiring chưa đăng ký scalar | Kiểm tra `RuntimeWiringConfigurer` |

Khi schema parse hoặc validation thất bại, Spring Boot thường không thể tạo GraphQL runtime hợp lệ và ứng dụng có thể dừng ngay khi khởi động. Hãy đọc lỗi đầu tiên trong log vì lỗi đó thường chỉ ra file, type hoặc field gây ra vấn đề.

## 13. Nguyên tắc tổ chức schema resources

- Đặt schema dùng trong production dưới `src/main/resources`.
- Dùng thư mục `graphql` mặc định nếu không có yêu cầu đặc biệt; giữ cấu hình đơn giản giúp người mới dễ tìm file.
- Chia file theo domain hoặc nhóm type, ví dụ book, author, review.
- Dùng `.graphqls` hoặc `.gqls` nhất quán.
- Chỉ định nghĩa mỗi type một lần; dùng `extend type` để bổ sung field từ file khác.
- Không dựa vào thứ tự file hoặc tên thư mục để biểu diễn phụ thuộc.
- Giữ schema SDL gần với domain API và review schema như source code.
- Kiểm tra resource đã được đóng gói trong artifact triển khai.
- Tránh đưa schema test fixture vào cùng pattern classpath với schema production nếu không chủ ý.
- Dùng `GraphQlSource` tùy biến chỉ khi property cấu hình không đủ.
- Kiểm thử schema runtime trong CI để phát hiện lỗi type reference, duplicate definition và resolver mapping sớm.

## 14. Bài tập thực hành

Tạo schema cho ứng dụng thư viện bằng nhiều file:

1. Tạo `src/main/resources/graphql/book.graphqls` chứa `Query.book`, `Query.books` và type `Book`.
2. Tạo `author/author.graphqls` định nghĩa `Author` và dùng `extend type Query` để bổ sung truy vấn tác giả.
3. Tạo `review/review.graphqls` định nghĩa `Review` và dùng `extend type Book` để thêm field `reviews`.
4. Viết controller cho các root query và resolver field lồng nhau.
5. Chạy ứng dụng và kiểm tra query trả về dữ liệu từ nhiều type.
6. Đổi schema location sang `classpath:api-schema/**/` và chuyển các file SDL sang thư mục mới.
7. Đóng gói ứng dụng và kiểm tra các file SDL có trong executable JAR.
8. Viết test `GraphQlTester` xác nhận field từ file author và review đều có trong schema runtime.

Khi hoàn thành, hãy giải thích được vì sao file SDL phải nằm trên classpath, Spring Boot tìm file theo location và extension nào, cách nhiều file trở thành một schema duy nhất, khi nào dùng `extend type` và cách phân biệt lỗi không tìm thấy resource với lỗi schema không hợp lệ.

## 15. Tài liệu tham khảo

- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Schema Resources](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot API — GraphQlProperties.Schema](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlProperties.Schema.html)

Các property và package auto-configuration có thể thay đổi giữa các phiên bản Spring Boot. Khi dự án nâng cấp, hãy kiểm tra reference documentation và Javadoc đúng phiên bản đang được dependency management sử dụng.
