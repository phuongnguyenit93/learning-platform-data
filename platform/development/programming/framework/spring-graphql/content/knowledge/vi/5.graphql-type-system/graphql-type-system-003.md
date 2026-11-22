# Enum type trong GraphQL

Enum type (kiểu liệt kê) biểu diễn một tập giá trị hữu hạn mà GraphQL API cho phép. Thay vì nhận một chuỗi tùy ý như `"published"`, schema có thể khai báo rõ các trạng thái hợp lệ như `DRAFT`, `IN_REVIEW` và `PUBLISHED`. GraphQL dùng tập giá trị này để kiểm tra input, mô tả output và giúp client hiểu chính xác những lựa chọn mà server hỗ trợ.

Trong Spring for GraphQL, enum được khai báo trong SDL và có thể ánh xạ với Java `enum` để resolver nhận, xử lý và trả về kiểu dữ liệu an toàn. Khi tên enum ở API khác tên hằng Java hoặc giá trị lưu trữ trong database, GraphQL Java cho phép cấu hình ánh xạ thông qua `RuntimeWiringConfigurer`.

Sau bài này, bạn có thể:

- Khai báo enum và enum value trong GraphQL SDL.
- Dùng enum ở output field, argument và input object.
- Truyền enum trong GraphQL document và JSON variables đúng cú pháp.
- Ánh xạ GraphQL enum với Java enum trong Spring for GraphQL.
- Tách tên công khai của enum khỏi mã lưu trữ nội bộ.
- Thiết kế nullability, deprecation, kiểm thử và thay đổi enum an toàn.

## 1. Enum là kiểu scalar có tập giá trị hữu hạn

GraphQL enum là một leaf type, tương tự scalar ở chỗ client nhận một giá trị đơn và không thể chọn field con bên trong nó. Điểm khác biệt là scalar thường biểu diễn một miền giá trị rộng, còn enum chỉ chấp nhận những tên đã được định nghĩa trong schema.

Ví dụ, một cuốn sách có thể ở một trong bốn trạng thái:

```graphql
enum BookStatus {
    DRAFT
    IN_REVIEW
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
}
```

`BookStatus` là tên enum type. `DRAFT`, `IN_REVIEW`, `PUBLISHED` và `ARCHIVED` là các enum value. Field `Book.status` chỉ có thể mang một trong những giá trị này và không thể trả về một chuỗi tùy ý như `"WAITING"` nếu giá trị đó chưa được khai báo.

Enum value là tên GraphQL, phân biệt chữ hoa/chữ thường. Tên phải tuân theo quy tắc tên GraphQL; không dùng các literal dành riêng `true`, `false` hoặc `null` làm enum value. Một enum phải có ít nhất một value và các value trong cùng enum phải có tên duy nhất.

## 2. Khai báo enum trong SDL

Cú pháp cơ bản:

```graphql
enum EnumTypeName {
    VALUE_ONE
    VALUE_TWO
    VALUE_THREE
}
```

Ví dụ enum cho đơn hàng:

```graphql
enum OrderStatus {
    PENDING
    CONFIRMED
    SHIPPING
    DELIVERED
    CANCELLED
}
```

Mỗi enum value có thể có description để giải thích ý nghĩa nghiệp vụ:

```graphql
"""Trạng thái xử lý của đơn hàng."""
enum OrderStatus {
    """Đơn hàng đã được tạo và đang chờ xác nhận."""
    PENDING

    """Đơn hàng đã được xác nhận."""
    CONFIRMED

    """Đơn hàng đang được vận chuyển."""
    SHIPPING

    """Đơn hàng đã được giao thành công."""
    DELIVERED

    """Đơn hàng đã bị hủy."""
    CANCELLED
}
```

Description giúp schema tự tài liệu hóa và có thể được đọc qua introspection. Nếu quy tắc nghiệp vụ phức tạp, nên giải thích thêm trong tài liệu API thay vì đặt tên enum quá dài hoặc trông chờ tên value tự diễn giải toàn bộ ý nghĩa.

## 3. Dùng enum trong output field

Enum thường được dùng làm kiểu trả về cho field của object:

```graphql
type Product {
    id: ID!
    name: String!
    availability: Availability!
}

enum Availability {
    IN_STOCK
    OUT_OF_STOCK
    PREORDER
}
```

Client có thể chọn enum như một field bình thường:

```graphql
query {
    product(id: "p-100") {
        id
        name
        availability
    }
}
```

Response có dạng:

```json
{
  "data": {
    "product": {
      "id": "p-100",
      "name": "Mechanical Keyboard",
      "availability": "IN_STOCK"
    }
  }
}
```

Trong response JSON, enum được biểu diễn bằng chuỗi tên value. Tuy nhiên, ở GraphQL operation document, enum literal là token không có dấu nháy kép. Client không thể yêu cầu các field con của enum như `availability { code }`, vì enum là leaf type.

Resolver phải trả về một giá trị có thể được GraphQL enum type serialize thành một trong các value đã khai báo. Nếu server trả về một giá trị không ánh xạ được, GraphQL tạo execution error cho field đó. Với field non-null, lỗi có thể lan lên field cha theo quy tắc null propagation.

## 4. Dùng enum làm argument để lọc dữ liệu

Enum rất hữu ích cho filter có số lựa chọn xác định:

```graphql
enum BookStatus {
    DRAFT
    IN_REVIEW
    PUBLISHED
    ARCHIVED
}

type Query {
    books(status: BookStatus): [Book!]!
}
```

Client có thể truyền enum literal trực tiếp:

```graphql
query {
    books(status: PUBLISHED) {
        id
        title
    }
}
```

Không đặt enum literal trong dấu nháy kép. `PUBLISHED` là enum value; `"PUBLISHED"` là string literal và không hợp lệ ở vị trí yêu cầu kiểu enum.

Nếu muốn lọc theo nhiều trạng thái, dùng list enum:

```graphql
type Query {
    booksByStatuses(statuses: [BookStatus!]!): [Book!]!
}
```

Operation:

```graphql
query {
    booksByStatuses(statuses: [DRAFT, IN_REVIEW]) {
        id
        title
    }
}
```

`[BookStatus!]!` yêu cầu argument là một list khác null và từng phần tử cũng khác null. List có thể rỗng trừ khi resolver hoặc validation nghiệp vụ quy định phải có ít nhất một phần tử; SDL không có cú pháp chuẩn để yêu cầu list chứa tối thiểu một item.

## 5. Enum trong input object và mutation

Enum có thể là field của input object, nhờ đó mutation nhận dữ liệu có cấu trúc:

```graphql
enum BookStatus {
    DRAFT
    IN_REVIEW
    PUBLISHED
    ARCHIVED
}

input UpdateBookInput {
    title: String
    status: BookStatus
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

Client có thể cập nhật trạng thái:

```graphql
mutation {
    updateBook(
        id: "book-42"
        input: { status: PUBLISHED }
    ) {
        id
        status
    }
}
```

Schema kiểm tra rằng `status` là một enum value hợp lệ trước khi resolver được thực thi. Nếu client gửi một tên không tồn tại, request bị từ chối ở bước coercion/validation input; resolver không cần tự viết lại danh sách hợp lệ.

Với mutation cập nhật từng phần, field enum nullable có thể có ba trạng thái cần phân biệt: client bỏ qua field, client gửi `null`, hoặc client gửi một enum value. Nếu nghiệp vụ cần phân biệt “không thay đổi trạng thái” với “xóa giá trị trạng thái”, hãy dùng `ArgumentValue<T>` của Spring for GraphQL hoặc một input model phù hợp để nhận biết field bị bỏ qua so với được truyền null.

## 6. Enum literal và JSON variables

GraphQL document và JSON variables có cú pháp biểu diễn enum khác nhau.

Trong GraphQL document, enum là literal không có dấu nháy kép:

```graphql
query FindBooks($status: BookStatus!) {
    books(status: $status) {
        id
        title
    }
}
```

Khi truyền variables qua JSON, giá trị enum được gửi dưới dạng JSON string chứa đúng tên enum:

```json
{
  "status": "PUBLISHED"
}
```

Điểm này không có nghĩa enum và String là cùng một kiểu. JSON không có kiểu enum riêng, nên giá trị biến được mã hóa bằng chuỗi; GraphQL vẫn dùng khai báo `$status: BookStatus!` để kiểm tra tên đó có thuộc enum hay không.

Một số ví dụ không hợp lệ:

```graphql
# Sai: string literal không phải enum literal
books(status: "PUBLISHED")

# Sai: value không được khai báo trong BookStatus
books(status: WAITING_FOR_REVIEW)
```

Tên enum phải khớp chính xác với SDL. `published`, `Published` và `PUBLISHED` là ba tên khác nhau.

## 7. Ánh xạ enum với Java enum trong Spring for GraphQL

Trong Java, enum thường được biểu diễn bằng `enum`:

```java
public enum BookStatus {
    DRAFT,
    IN_REVIEW,
    PUBLISHED,
    ARCHIVED
}
```

Với enum Java có hằng trùng tên GraphQL, có thể dùng `NaturalEnumValuesProvider` để ánh xạ từng GraphQL enum value sang Java enum constant tương ứng:

```java
@Configuration
public class GraphQlEnumConfiguration {

    @Bean
    RuntimeWiringConfigurer bookStatusEnumWiring() {
        return wiringBuilder -> wiringBuilder.type(
                "BookStatus",
                typeWiring -> typeWiring.enumValues(
                        new NaturalEnumValuesProvider<>(BookStatus.class)));
    }
}
```

Spring Boot tự phát hiện bean `RuntimeWiringConfigurer` và đưa cấu hình này vào quá trình tạo GraphQL schema. `NaturalEnumValuesProvider` ánh xạ tên enum trong SDL sang Java enum constant có cùng tên. Cách này giúp resolver nhận và trả về `BookStatus` thay vì phải xử lý chuỗi ở nhiều nơi.

Resolver có thể dùng enum trực tiếp:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument("status") BookStatus status) {
        return status == null
                ? bookService.findAll()
                : bookService.findByStatus(status);
    }

    @MutationMapping
    public Book publishBook(@Argument("id") String id) {
        return bookService.changeStatus(id, BookStatus.PUBLISHED);
    }
}
```

`@Argument("status")` bind argument GraphQL vào tham số Java. Việc bind input được Spring for GraphQL thực hiện qua `GraphQlArgumentBinder`; các kiểu đơn giản có thể được chuyển đổi bằng conversion service, còn input object được bind vào constructor hoặc thuộc tính của target object.

Nếu không cấu hình enum provider, GraphQL Java thường biểu diễn enum value theo tên GraphQL trong runtime. Khi muốn resolver và model dùng Java enum trực tiếp ở cả chiều input/output, cấu hình provider tường minh giúp hợp đồng ánh xạ rõ ràng và tránh lỗi serialize do hai phía dùng kiểu giá trị nội bộ khác nhau.

## 8. Ánh xạ khi tên GraphQL khác tên Java

Tên công khai trong schema không nhất thiết phải giống tên hằng Java. Ví dụ API muốn dùng `UNDER_REVIEW`, trong khi domain model đang có `REVIEW`:

```graphql
enum BookStatus {
    DRAFT
    UNDER_REVIEW
    PUBLISHED
}
```

```java
public enum BookStatus {
    DRAFT,
    REVIEW,
    PUBLISHED
}
```

Khi đó, cung cấp mapping riêng bằng `enumValues`:

```java
@Configuration
public class GraphQlEnumConfiguration {

    @Bean
    RuntimeWiringConfigurer bookStatusEnumWiring() {
        return wiringBuilder -> wiringBuilder.type(
                "BookStatus",
                typeWiring -> typeWiring.enumValues(graphQlValue -> switch (graphQlValue) {
                    case "DRAFT" -> BookStatus.DRAFT;
                    case "UNDER_REVIEW" -> BookStatus.REVIEW;
                    case "PUBLISHED" -> BookStatus.PUBLISHED;
                    default -> throw new IllegalArgumentException(
                            "Unsupported BookStatus: " + graphQlValue);
                }));
    }
}
```

Mapping này được dùng khi schema được tạo, để mỗi GraphQL enum value có một runtime value tương ứng. Khi serialize output, GraphQL Java dựa trên mapping đã đăng ký để chuyển runtime value về tên công khai trong SDL. Hãy khai báo đầy đủ mọi enum value; không để một value thiếu mapping hoặc nhiều value vô tình dùng chung một runtime value nếu chúng phải được phân biệt.

Khi tên trùng nhau, `NaturalEnumValuesProvider` gọn hơn. Khi tên khác nhau hoặc cần ánh xạ sang một đối tượng nội bộ khác, dùng `EnumValuesProvider` tùy chỉnh qua `enumValues`.

## 9. Tách enum công khai khỏi mã lưu trữ

Không nên để chi tiết lưu trữ database quyết định trực tiếp tên enum công khai. Ví dụ, hệ thống cũ lưu trạng thái bằng mã `D`, `R`, `P`:

```java
public enum BookStatus {
    DRAFT("D"),
    REVIEW("R"),
    PUBLISHED("P");

    private final String databaseCode;

    BookStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }
}
```

GraphQL vẫn có thể công bố tên dễ hiểu:

```graphql
enum BookStatus {
    DRAFT
    UNDER_REVIEW
    PUBLISHED
}
```

Resolver làm việc với `BookStatus`; service hoặc repository chuyển enum thành mã lưu trữ. Với JPA, có thể dùng `AttributeConverter`:

```java
@Converter
public class BookStatusConverter
        implements AttributeConverter<BookStatus, String> {

    @Override
    public String convertToDatabaseColumn(BookStatus status) {
        return status == null ? null : status.databaseCode();
    }

    @Override
    public BookStatus convertToEntityAttribute(String code) {
        if (code == null) {
            return null;
        }

        return Arrays.stream(BookStatus.values())
                .filter(status -> status.databaseCode().equals(code))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown BookStatus database code: " + code));
    }
}
```

```java
@Entity
public class BookEntity {

    @Convert(converter = BookStatusConverter.class)
    private BookStatus status;
}
```

Như vậy, đổi tên một enum value công khai không nhất thiết buộc phải đổi mã database. Ngược lại, thay đổi mã lưu trữ cũng có thể được xử lý ở converter mà không làm client GraphQL biết chi tiết đó.

Nếu dùng `@Enumerated(EnumType.STRING)`, JPA lưu tên hằng Java; đổi tên hằng có thể cần migration dữ liệu. Tránh `EnumType.ORDINAL` cho dữ liệu lâu dài vì database lưu vị trí số của hằng; thêm hoặc sắp xếp lại hằng có thể làm ý nghĩa dữ liệu cũ thay đổi.

## 10. Nullability và default value của enum

Enum tuân theo quy tắc nullability như các kiểu GraphQL khác:

```graphql
type Book {
    status: BookStatus
    requiredStatus: BookStatus!
}

type Query {
    books(status: BookStatus = PUBLISHED): [Book!]!
}
```

- `status: BookStatus` có thể trả về `null`.
- `requiredStatus: BookStatus!` phải trả về một enum value hợp lệ.
- `status: BookStatus = PUBLISHED` dùng `PUBLISHED` khi argument bị bỏ qua.

Default enum value trong SDL được viết như enum literal, không đặt trong dấu nháy kép. Nếu client chủ động gửi `null` cho argument nullable, default value không được áp dụng; resolver nhận null theo hợp đồng của field.

Đừng dùng một enum value giả như `UNKNOWN` chỉ để thay thế mọi trường hợp null nếu nghiệp vụ cần phân biệt “chưa xác định”, “không áp dụng” và “không có dữ liệu”. Hãy xác định rõ các trạng thái đó có thực sự là những giá trị domain khác nhau hay chỉ là tình trạng thiếu dữ liệu.

## 11. Deprecated enum value

Khi một enum value không còn được khuyến nghị, có thể đánh dấu nó bằng `@deprecated`:

```graphql
enum PaymentMethod {
    CARD
    BANK_TRANSFER
    CASH @deprecated(reason: "Use a supported electronic payment method.")
}
```

Deprecated value vẫn tồn tại trong schema và có thể vẫn được client cũ gửi hoặc nhận. Directive này giúp công cụ introspection và tài liệu nhận biết value nên được thay thế; nó không tự động từ chối request sử dụng value đó.

Nếu muốn ngừng chấp nhận một enum value, cần triển khai chính sách ở resolver/service và có kế hoạch loại bỏ theo phiên bản tương thích. Chỉ xóa value khỏi SDL sẽ làm các operation cũ gửi value đó trở thành không hợp lệ.

## 12. Khi nào nên dùng enum?

Enum phù hợp khi tập giá trị:

- Có số lượng hữu hạn và được server kiểm soát.
- Có ý nghĩa nghiệp vụ ổn định, có thể đặt tên rõ ràng.
- Cần được kiểm tra trước khi resolver xử lý.
- Có thể được client dùng để tạo dropdown, filter hoặc nhánh xử lý.

Ví dụ phù hợp: trạng thái đơn hàng, loại tài khoản, mức ưu tiên, phương thức vận chuyển hoặc hướng sắp xếp.

Enum không phù hợp khi giá trị do người dùng tự tạo, thay đổi liên tục hoặc phụ thuộc dữ liệu runtime. Ví dụ, danh sách quốc gia do hệ thống quản trị cập nhật có thể cần một object `Country` với `code`, `name` thay vì enum, nếu API cần thêm metadata hoặc cho phép cập nhật danh mục mà không phải thay schema.

| Nhu cầu | Kiểu nên cân nhắc | Lý do |
| --- | --- | --- |
| Tập trạng thái cố định | Enum | GraphQL kiểm tra giá trị hợp lệ |
| Chuỗi do người dùng nhập | `String` | Miền giá trị không cố định |
| Danh mục có ID và metadata | Object type | Có thể truy vấn nhiều field |
| Mã định danh duy nhất | `ID` | Biểu diễn identity, không phải tập lựa chọn |
| Số lượng có thể thay đổi theo cấu hình | Object type hoặc scalar phù hợp | Không cần sửa schema mỗi khi danh sách đổi |

Không dùng enum như cơ chế phân quyền. Enum mô tả giá trị hợp lệ trong API; quyền của người dùng phải được kiểm tra ở server theo identity và ngữ cảnh request.

## 13. Kiểm thử enum trong GraphQL

Nên kiểm tra cả input và output của enum qua operation thực tế. Với `GraphQlTester`, có thể gửi query dùng enum literal:

```java
graphQlTester.document("""
        query {
            books(status: PUBLISHED) {
                id
                status
            }
        }
        """)
    .execute()
    .path("books[0].status")
    .entity(String.class)
    .isEqualTo("PUBLISHED");
```

Các trường hợp nên có trong test:

1. Enum literal hợp lệ được bind thành đúng giá trị Java/domain.
2. Enum value không tồn tại bị GraphQL từ chối trước khi gọi resolver.
3. Resolver trả enum được serialize thành đúng tên công khai.
4. Enum trong input object và list enum được bind chính xác.
5. Mapping tùy chỉnh giữa tên SDL và Java enum hoạt động ở cả input và output.
6. Null và default value tuân theo khai báo trong schema.
7. Deprecated enum value vẫn có hành vi tương thích đã định trong giai đoạn chuyển đổi.

Với enum dùng mã database riêng, kiểm thử converter cho từng mã hợp lệ và mã không được hỗ trợ. Điều này giúp phát hiện lỗi dữ liệu cũ trước khi chúng xuất hiện thành serialization error ở GraphQL response.

## 14. Những lỗi thường gặp

- **Đặt enum literal trong dấu nháy kép:** `status: "PUBLISHED"` là string, không phải enum literal trong GraphQL document.
- **Dùng value chưa khai báo:** GraphQL từ chối input trước khi resolver chạy.
- **Sai chữ hoa/chữ thường:** tên enum phải khớp chính xác với SDL.
- **Java enum không khớp mapping:** resolver có thể nhận hoặc trả về giá trị không serialize được nếu không cấu hình provider phù hợp.
- **Dùng ordinal làm mã lưu trữ:** thêm hoặc đổi thứ tự hằng có thể làm dữ liệu cũ mang ý nghĩa khác.
- **Xóa enum value đang được client sử dụng:** operation cũ trở thành không hợp lệ.
- **Dùng enum cho danh mục thay đổi liên tục:** mỗi lần thêm lựa chọn lại phải thay đổi và phát hành schema.
- **Nhầm `@deprecated` với việc vô hiệu hóa:** directive chỉ đánh dấu value không còn khuyến nghị; nó không tự chặn request.

## 15. Quy trình thiết kế và triển khai enum

Khi thêm một enum vào Spring for GraphQL, hãy đi theo các bước sau:

1. Xác định tập lựa chọn có thực sự hữu hạn và ổn định hay không.
2. Đặt tên enum type và enum value theo quy ước thống nhất; viết description cho value dễ gây nhầm lẫn.
3. Dùng enum trong output field, argument hoặc input object theo đúng nghiệp vụ.
4. Quyết định nullability và default value; không dùng `UNKNOWN` để che giấu mọi trường hợp thiếu dữ liệu.
5. Tạo Java enum tương ứng; nếu tên SDL và Java trùng nhau, cân nhắc `NaturalEnumValuesProvider`.
6. Nếu tên khác nhau hoặc database dùng mã riêng, khai báo mapping tường minh và converter ở tầng persistence.
7. Kiểm thử input, output, list, null, default và trường hợp enum value không hợp lệ.
8. Khi thay đổi tập value, đánh giá client đang sử dụng và dùng `@deprecated` cho giai đoạn chuyển tiếp.

Enum làm cho hợp đồng GraphQL rõ ràng hơn bằng cách giới hạn dữ liệu vào một tập lựa chọn có tên. Khi kết hợp SDL với Java enum và mapping phù hợp trong Spring for GraphQL, ứng dụng có thể kiểm tra input sớm, giữ kiểu dữ liệu nhất quán và tách tên công khai khỏi chi tiết lưu trữ. Hãy dùng enum cho những khái niệm nghiệp vụ thực sự hữu hạn và quản lý việc tiến hóa value như một thay đổi của API contract.

## Tài liệu tham khảo

- [GraphQL Specification — Enums](https://spec.graphql.org/October2021/#sec-Enums)
- [GraphQL Java — Data mapping](https://graphql-java.com/documentation/master/data-mapping/)
- [GraphQL Java — NaturalEnumValuesProvider](https://javadoc.io/static/com.graphql-java/graphql-java/19.11/graphql/schema/idl/NaturalEnumValuesProvider.html)
- [Spring for GraphQL — Annotated Controllers và argument binding](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — GraphQL RuntimeWiring](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
