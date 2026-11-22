# Type compatibility khi mapping Java

## Mục tiêu

Sau bài học này, bạn có thể:

- Chọn kiểu Java phù hợp với các scalar và kiểu dữ liệu trong GraphQL SDL.
- Phân biệt nullability của GraphQL với khả năng nhận null trong Java.
- Mapping danh sách, enum, input object, object type, interface và union.
- Dùng @Argument, @QueryMapping, @SchemaMapping để kết nối schema với phương thức Java.
- Nhận biết các trường hợp cần custom scalar hoặc type resolver.
- Phát hiện lỗi không tương thích giữa schema và chữ ký Java trước khi chạy query.

## 1. Vì sao cần quan tâm đến type compatibility?

GraphQL schema là hợp đồng kiểu dữ liệu mà client nhìn thấy. Java là ngôn ngữ server dùng để nhận argument, gọi nghiệp vụ và trả kết quả. Hai phía cần thống nhất về kiểu, cấu trúc và khả năng có giá trị rỗng.

Ví dụ SDL khai báo:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  pageCount: Int
  rating: Float
}
~~~

Một controller Java có thể nhận id dưới dạng String và trả về một đối tượng Book. Nếu Java trả null cho field title trong khi schema khai báo String!, GraphQL sẽ phát sinh lỗi thực thi và áp dụng quy tắc null propagation.

Tương tự, nếu schema khai báo pageCount: Int nhưng Java dùng một giá trị Long vượt phạm vi số nguyên 32-bit, dữ liệu không còn phù hợp với hợp đồng GraphQL.

Type compatibility vì vậy bao gồm nhiều khía cạnh:

- Kiểu scalar có thể serialize và parse đúng.
- Cấu trúc object và danh sách khớp với schema.
- Nullability được giữ đúng ở cả cấp field và phần tử danh sách.
- Input argument có thể bind vào tham số Java.
- Kiểu Java cụ thể có thể được GraphQL xác định thành object type tương ứng.
- Các enum và custom scalar có quy tắc chuyển đổi nhất quán.

## 2. Mapping GraphQL scalar sang Java

GraphQL định nghĩa năm scalar cơ bản: Int, Float, String, Boolean và ID. Khi triển khai bằng Java, nên chọn kiểu biểu diễn phù hợp với phạm vi và ý nghĩa của từng scalar.

| GraphQL scalar | Kiểu Java thường dùng | Lưu ý |
|---|---|---|
| String | String | Chuỗi Unicode |
| Boolean | Boolean hoặc boolean | Dùng wrapper nếu field có thể null |
| Int | Integer hoặc int | Số nguyên có dấu 32-bit |
| Float | Double hoặc double | Số dấu phẩy động độ chính xác kép |
| ID | String | Nên xem ID là định danh opaque, không mặc định là số |

### Int không đồng nghĩa với mọi kiểu số nguyên Java

GraphQL Int có phạm vi số nguyên có dấu 32-bit, từ -2.147.483.648 đến 2.147.483.647. Java Integer có cùng phạm vi nên là lựa chọn tự nhiên.

Java Long có phạm vi lớn hơn. Không nên dùng Long để biểu diễn một trường GraphQL Int nếu giá trị có thể vượt giới hạn 32-bit. Nếu nghiệp vụ cần số nguyên lớn, hãy chọn một hướng có chủ đích:

- Dùng custom scalar có quy tắc serialize/parse rõ ràng.
- Dùng ID nếu giá trị chỉ là định danh.
- Dùng String nếu cần truyền số lớn dưới dạng văn bản và client xử lý theo hợp đồng riêng.

Không nên đổi một trường số lượng hoặc số tiền sang ID chỉ để tránh giới hạn số nguyên. Kiểu GraphQL cần phản ánh ý nghĩa nghiệp vụ.

### Float và độ chính xác

GraphQL Float là số dấu phẩy động độ chính xác kép. Java Double là kiểu phù hợp phổ biến. Java BigDecimal có thể biểu diễn số thập phân với độ chính xác cao hơn, nhưng không đồng nghĩa với scalar Float.

Với giá tiền hoặc dữ liệu tài chính cần giữ chính xác thập phân, hãy cân nhắc custom scalar như Decimal và định nghĩa cách parse, serialize cũng như định dạng truyền qua JSON. Không nên dựa vào Double nếu sai số dấu phẩy động có thể ảnh hưởng kết quả nghiệp vụ.

### ID nên được xem là định danh

GraphQL ID được serialize dưới dạng chuỗi. Giá trị đầu vào có thể được truyền theo dạng chuỗi hoặc số nguyên, nhưng API nên coi ID là định danh, không phải phép đo số học.

Ví dụ:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Dùng String giúp Java không phụ thuộc vào việc ID được tạo từ số tự tăng, UUID hay một định dạng opaque khác.

## 3. Nullability: GraphQL ! và Java primitive/wrapper

GraphQL dùng dấu ! để khai báo một giá trị không được null. Java có hai nhóm kiểu liên quan:

- Primitive như int, long, boolean: luôn có giá trị mặc định, không thể biểu diễn null.
- Reference type như Integer, Long, Boolean, String và object: có thể nhận null.

Vì vậy, nên chọn kiểu Java theo nullability trong SDL:

| GraphQL | Java thường dùng | Ý nghĩa |
|---|---|---|
| String | String | Có thể trả về null |
| String! | String | Ứng dụng phải bảo đảm có giá trị |
| Int | Integer | Có thể trả về null |
| Int! | int hoặc Integer | Không được trả null |
| Boolean | Boolean | Có thể trả về null |
| Boolean! | boolean hoặc Boolean | Không được trả null |

Primitive không tự bảo đảm logic nghiệp vụ đúng. Ví dụ, nếu dùng int pageCount cho một field nullable, Java sẽ không thể biểu diễn trường hợp không có số trang; giá trị mặc định 0 có thể bị hiểu nhầm là dữ liệu thật. Dùng Integer nếu trường có thể thiếu.

### Null propagation trong GraphQL

Giả sử schema:

~~~graphql
type Book {
  title: String!
  subtitle: String
}
~~~

Nếu resolver trả về null cho subtitle, response vẫn hợp lệ vì field này nullable. Nếu resolver trả về null cho title, GraphQL tạo lỗi và đẩy giá trị null lên field cha gần nhất cho phép null.

Nếu field cha cũng non-null, quá trình lan truyền tiếp tục lên cấp cao hơn. Do đó, một giá trị null ở field con có thể khiến cả object hoặc một phần lớn response trở thành null.

Không nên đánh dấu mọi field là non-null chỉ để schema trông chặt chẽ. Hãy dùng ! khi dữ liệu và quy tắc nghiệp vụ thực sự bảo đảm giá trị luôn tồn tại.

## 4. Mapping list và collection

GraphQL dùng cú pháp ngoặc vuông để khai báo danh sách. Java thường biểu diễn các field này bằng List<T>, Collection<T>, mảng hoặc kiểu collection phù hợp.

Ví dụ:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

Một số biến thể nullability cần phân biệt:

| SDL | Danh sách có thể null? | Phần tử có thể null? |
|---|---:|---:|
| [Book] | Có | Có |
| [Book!] | Có | Không |
| [Book]! | Không | Có |
| [Book!]! | Không | Không |

Java generic như List<Book> mô tả kiểu phần tử ở mức compile-time, nhưng không tự mã hóa đầy đủ hai cấp nullability này. GraphQL engine vẫn áp dụng quy tắc nullability theo schema khi serialize kết quả.

Ví dụ, với [Book!]!, resolver phải trả về một danh sách không null và không có phần tử null. Nếu một phần tử null xuất hiện, GraphQL sẽ phát sinh lỗi và áp dụng null propagation theo cấu trúc schema.

### Collection reactive

Spring for GraphQL hỗ trợ kiểu trả về reactive. Một số dạng thường gặp:

- Mono<Book>: một kết quả hoặc không có kết quả.
- Flux<Book>: luồng nhiều kết quả, thường dùng cho field danh sách hoặc Subscription.
- List<Book>: danh sách đồng bộ.

Ví dụ Subscription:

~~~graphql
type Subscription {
  bookEvents: BookEvent!
}
~~~

~~~java
@SubscriptionMapping
public Flux<BookEvent> bookEvents() {
    return bookService.events();
}
~~~

Subscription cần publisher để phát nhiều giá trị theo thời gian. Query hoặc Mutation có thể dùng kiểu đồng bộ hoặc reactive tùy kiến trúc service.

## 5. Mapping object type sang Java class

GraphQL object type thường được biểu diễn bằng POJO, record hoặc object domain ở phía Java. GraphQL Java mặc định có thể dùng PropertyDataFetcher để đọc dữ liệu từ source object dựa trên tên field.

Ví dụ SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  pageCount: Int
}
~~~

Java class:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final Integer pageCount;

    public Book(String id, String title, Integer pageCount) {
        this.id = id;
        this.title = title;
        this.pageCount = pageCount;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Integer getPageCount() {
        return pageCount;
    }
}
~~~

Nếu Query trả về một đối tượng Book, GraphQL có thể đọc các field id, title và pageCount từ getter tương ứng.

~~~java
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

Tên field GraphQL và tên property Java cần có quy tắc tương ứng. Nếu tên khác nhau hoặc cần tính toán dữ liệu, hãy khai báo mapping tường minh:

~~~java
@SchemaMapping(typeName = "Book", field = "displayTitle")
public String displayTitle(Book book) {
    return book.getTitle().toUpperCase();
}
~~~

@SchemaMapping liên kết phương thức với field của một GraphQL type. Tham số source Book được lấy từ object cha đang được phân giải. Kiểu trả về của phương thức cần phù hợp với kiểu field displayTitle trong SDL.

Không cần viết resolver riêng cho mọi property đơn giản. Hãy tận dụng property mapping mặc định khi tên và cấu trúc tương thích; dùng @SchemaMapping khi field cần logic hoặc nguồn dữ liệu riêng.

## 6. Mapping input object sang Java DTO

GraphQL dùng input type để mô tả dữ liệu client được phép gửi vào. Input object là kiểu đầu vào, không thể thay thế trực tiếp bằng GraphQL object type.

Ví dụ SDL:

~~~graphql
input UpdateBookInput {
  title: String!
  pageCount: Int
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book
}
~~~

Java DTO:

~~~java
public record UpdateBookInput(
        String title,
        Integer pageCount) {
}
~~~

Controller:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {

    return bookService.update(
            id,
            input.title(),
            input.pageCount());
}
~~~

Spring for GraphQL dùng GraphQlArgumentBinder để bind dữ liệu argument từ GraphQL vào tham số Java. Binder hỗ trợ cấu trúc lồng nhau và có thể tạo object thông qua constructor hoặc cập nhật property phù hợp. Java record là lựa chọn gọn cho DTO bất biến có constructor tương ứng.

Tên field trong input object cần khớp với tên property hoặc constructor parameter mà binder có thể sử dụng. Nếu cấu trúc phức tạp, hãy kiểm tra DTO và kiểu dữ liệu lồng nhau để tránh lỗi binding lúc thực thi.

### Phân biệt omitted và explicit null

Trong GraphQL, một input field có thể bị bỏ qua hoặc được gửi rõ ràng với giá trị null. Hai trường hợp này có thể mang ý nghĩa nghiệp vụ khác nhau, ví dụ:

- Bỏ qua subtitle: giữ nguyên subtitle hiện tại.
- Gửi subtitle: null: xóa subtitle.

Ví dụ schema cho thao tác patch:

~~~graphql
type Mutation {
  patchBook(id: ID!, subtitle: String): Book
}
~~~

Một tham số Java kiểu String thông thường không đủ để phân biệt chắc chắn hai trạng thái này sau binding. Spring for GraphQL cung cấp ArgumentValue<T> để biểu diễn giá trị argument có phân biệt trường hợp không được truyền và trường hợp được truyền với null.

Ví dụ:

~~~java
@MutationMapping
public Book patchBook(
        @Argument("id") String id,
        @Argument("subtitle") ArgumentValue<String> subtitle) {

    if (!subtitle.isOmitted()) {
        return bookService.updateSubtitle(id, subtitle.value());
    }

    return bookService.findById(id);
}
~~~

Cách này hữu ích với mutation dạng patch. Cần thiết kế schema, DTO và logic cập nhật thống nhất để không vô tình biến thao tác bỏ qua thành thao tác xóa dữ liệu.

## 7. Mapping enum

GraphQL enum giới hạn giá trị của một field vào một tập tên đã định nghĩa.

SDL:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  status: BookStatus!
}
~~~

Java:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

Khi tên enum value trong SDL tương ứng với tên Java enum constant, GraphQL Java có thể ánh xạ theo tên mặc định.

Nếu hệ thống dùng tên khác nhau, chẳng hạn Java có IN_REVIEW nhưng schema công bố PENDING_REVIEW, cần cấu hình enum value mapping trong RuntimeWiring thay vì giả định hai tên tự động tương thích.

Không nên dùng chuỗi tùy ý cho một field enum nếu có thể dùng Java enum. Kiểu enum giúp giới hạn giá trị hợp lệ trong code và giảm lỗi chính tả.

## 8. Mapping interface và union

GraphQL interface và union là các kiểu abstract. Một field có thể trả về nhiều object type cụ thể. Khi đó, GraphQL cần xác định kiểu thực tế của object để biết field nào được phép trả về.

SDL:

~~~graphql
interface SearchResult {
  id: ID!
}

type Book implements SearchResult {
  id: ID!
  title: String!
}

type Author implements SearchResult {
  id: ID!
  name: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

Java có thể dùng một interface chung:

~~~java
public interface SearchResult {
    String getId();
}

public class BookResult implements SearchResult {
    private final String id;
    private final String title;

    public BookResult(String id, String title) {
        this.id = id;
        this.title = title;
    }

    @Override
    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}

public class AuthorResult implements SearchResult {
    private final String id;
    private final String name;

    public AuthorResult(String id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Khi object Java không đủ thông tin để GraphQL tự xác định concrete type, cần cấu hình TypeResolver. Spring for GraphQL có thể dùng ClassNameTypeResolver để suy ra GraphQL type từ tên lớp theo quy ước. Nếu tên lớp và tên GraphQL type không khớp hoặc nhiều lớp không có quan hệ kế thừa, hãy dùng type resolver tùy chỉnh.

Ví dụ cấu hình resolver:

~~~java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return wiringBuilder -> wiringBuilder.type("SearchResult", typeBuilder ->
        typeBuilder.typeResolver(environment -> {
            Object value = environment.getObject();

            if (value instanceof BookResult) {
                return environment.getSchema()
                        .getObjectType("Book");
            }

            if (value instanceof AuthorResult) {
                return environment.getSchema()
                        .getObjectType("Author");
            }

            throw new IllegalStateException(
                    "Unsupported SearchResult type: " + value.getClass().getName());
        })
    );
}
~~~

Với union, cách tiếp cận tương tự: GraphQL cần xác định object type cụ thể trong các thành viên đã khai báo của union. Kết quả từ resolver phải là một GraphQL object type hợp lệ theo schema.

## 9. Custom scalar cho kiểu Java đặc thù

Các scalar tích hợp sẵn không thể biểu diễn mọi kiểu dữ liệu nghiệp vụ. Ví dụ:

- LocalDate hoặc OffsetDateTime.
- UUID.
- Decimal có yêu cầu chính xác.
- Giá trị tiền tệ hoặc mã định danh theo định dạng riêng.

Khi đó, có thể khai báo scalar trong SDL:

~~~graphql
scalar DateTime
scalar Decimal

type Invoice {
  id: ID!
  issuedAt: DateTime!
  total: Decimal!
}
~~~

Và đăng ký coercing tương ứng trong runtime wiring:

~~~java
@Bean
RuntimeWiringConfigurer customScalars() {
    return wiringBuilder -> wiringBuilder
            .scalar(dateTimeScalar())
            .scalar(decimalScalar());
}
~~~

Mỗi custom scalar cần quy định rõ:

- Cách parse giá trị từ biến JSON.
- Cách parse literal trong GraphQL document nếu được hỗ trợ.
- Cách serialize giá trị Java thành JSON response.
- Cách xử lý input không hợp lệ và thông báo lỗi.

Không nên chỉ đổi tên một scalar thành DateTime mà không đăng ký cách chuyển đổi. Nếu thiếu coercing phù hợp, GraphQL không biết cách chuyển giữa giá trị truyền qua wire và kiểu Java của ứng dụng.

## 10. Schema mapping inspection và kiểm tra compatibility

Một SDL hợp lệ về cú pháp không bảo đảm mọi phương thức Java đều mapping đúng. Ví dụ:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Nhưng controller lại khai báo:

~~~java
@QueryMapping
public List<Book> book(@Argument("id") String id) {
    return bookService.findRelatedBooks(id);
}
~~~

Field book trong schema trả về một Book, còn phương thức Java trả về danh sách. Đây là mismatch về cấu trúc kết quả.

Spring for GraphQL hỗ trợ schema mapping inspection để tìm một số điểm không tương thích giữa schema và data fetcher, ví dụ field chưa có mapping phù hợp hoặc chữ ký Java không khớp kiểu GraphQL mà inspection có thể suy luận.

Có thể bật inspection khi tạo source:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .inspectSchemaMappings(System.out::println)
        .build();
~~~

Inspection hữu ích nhưng không thay thế kiểm thử runtime. Nó không thể biết chắc giá trị thật mà repository trả về trong mọi tình huống, cũng không thể chứng minh rằng dữ liệu luôn thỏa mãn quy tắc nghiệp vụ.

Nên kết hợp các cách kiểm tra:

1. **Schema validation:** kiểm tra SDL và query theo GraphQL schema.
2. **Schema mapping inspection:** tìm các field và chữ ký Java không tương thích mà công cụ có thể phát hiện.
3. **Controller test:** kiểm tra argument binding và kiểu kết quả của resolver.
4. **Integration test:** chạy operation thực tế với dữ liệu đại diện, bao gồm null, danh sách rỗng và lỗi nghiệp vụ.

## 11. Các lỗi mapping thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Field non-null gây lỗi khi response | Java trả về null | Kiểm tra dữ liệu, resolver và hợp đồng nullability |
| GraphQL Int không serialize được | Giá trị vượt phạm vi 32-bit hoặc kiểu không phù hợp | Dùng Integer trong phạm vi; thiết kế custom scalar nếu cần |
| Field object trả về null | Getter/property không khớp tên field | Kiểm tra tên property hoặc khai báo @SchemaMapping |
| Input binding thất bại | DTO thiếu constructor/property phù hợp hoặc kiểu lồng không tương thích | Kiểm tra cấu trúc input và Java DTO |
| Enum không chuyển đổi | Tên enum value khác tên Java constant | Cấu hình enum value mapping |
| Interface/union không xác định được kiểu | Thiếu hoặc sai TypeResolver | Cấu hình type resolver theo object thực tế |
| Decimal bị sai số | Dùng Float/Double cho dữ liệu cần độ chính xác | Dùng custom scalar và BigDecimal |
| List vi phạm nullability | Có phần tử null hoặc cả danh sách null | Đảm bảo dữ liệu phù hợp [T], [T!], [T]! hoặc [T!]! |

## 12. Nguyên tắc thiết kế Java model tương thích với GraphQL

Khi thiết kế model và resolver, hãy áp dụng một số nguyên tắc:

- Chọn Java wrapper type cho field GraphQL nullable.
- Chỉ dùng primitive khi nghiệp vụ bảo đảm giá trị không thể null.
- Dùng String cho ID opaque, không giả định ID luôn là số.
- Dùng Integer cho GraphQL Int và kiểm soát giới hạn 32-bit.
- Dùng custom scalar khi cần biểu diễn kiểu nghiệp vụ không tương ứng trực tiếp với scalar chuẩn.
- Dùng DTO riêng cho input object khi cấu trúc request khác với domain model.
- Dùng enum Java khi schema giới hạn tập giá trị.
- Dùng @SchemaMapping khi property mapping mặc định không đủ.
- Cấu hình TypeResolver khi GraphQL trả về interface hoặc union.
- Kiểm tra nullability và collection ở cả cấp danh sách lẫn phần tử.

Schema nên mô tả hợp đồng API ổn định, còn Java model nên phản ánh nhu cầu của ứng dụng. Không nhất thiết phải dùng trực tiếp entity persistence làm GraphQL output hoặc input. DTO giúp tránh để cấu trúc database chi phối schema công khai và giúp kiểm soát dữ liệu được expose.

## Kết luận

Type compatibility khi mapping Java là sự tương thích giữa kiểu GraphQL trong SDL và dữ liệu mà Java nhận hoặc trả về. Các điểm quan trọng gồm scalar, nullability, collection, enum, input binding, object property mapping và abstract type resolution.

Spring for GraphQL cung cấp @Argument, @QueryMapping, @SchemaMapping, GraphQlArgumentBinder, RuntimeWiringConfigurer và schema mapping inspection để kết nối hai phía. Khi chọn đúng kiểu Java, thiết kế nullability rõ ràng và kiểm thử cả schema lẫn resolver, API sẽ giảm được lỗi chuyển đổi và giữ hợp đồng GraphQL nhất quán.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Schema Mapping Inspection](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Specification — Type System](https://spec.graphql.org/October2021/#sec-Type-System)
- [GraphQL Java — Documentation](https://www.graphql-java.com/documentation/)
