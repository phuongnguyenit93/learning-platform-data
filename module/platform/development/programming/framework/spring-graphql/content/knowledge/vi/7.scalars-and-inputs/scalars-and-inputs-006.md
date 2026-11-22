# GraphQLScalarType

GraphQL có các kiểu scalar tích hợp như `String`, `Int`, `Float`, `Boolean` và `ID`. Chúng biểu diễn những giá trị đơn giản, không có field con. Tuy nhiên, API thực tế thường cần các kiểu nguyên tử có quy tắc riêng: UUID, ngày giờ, tiền tệ, email hoặc mã định danh theo định dạng của hệ thống.

GraphQL cho phép định nghĩa **custom scalar** để mở rộng tập kiểu dữ liệu đó. Trong GraphQL Java, `GraphQLScalarType` là đối tượng mô tả scalar ở runtime; `Coercing` quy định cách chuyển đổi giữa giá trị Java và giá trị GraphQL. Spring for GraphQL kết nối custom scalar với schema SDL thông qua `RuntimeWiringConfigurer`.

Bài học này giải thích vai trò của `GraphQLScalarType`, ba hướng coercion `serialize`, `parseValue`, `parseLiteral`, cách đăng ký scalar trong Spring và cách kiểm thử dữ liệu hợp lệ cũng như không hợp lệ.

## 1. Scalar là gì và khi nào cần custom scalar?

Scalar là kiểu dữ liệu ở mức lá của GraphQL. Client chọn scalar trực tiếp mà không cần selection set con:

```graphql
type Book {
  id: ID!
  title: String!
  publishedYear: Int
  available: Boolean!
}
```

`String`, `ID`, `Int` và `Boolean` đều là scalar tích hợp. Chúng phù hợp với những giá trị có biểu diễn đơn giản và quy tắc chuẩn.

Custom scalar phù hợp khi một giá trị đơn cần có định dạng hoặc quy tắc parse/serialize rõ ràng. Ví dụ:

- `UUID` biểu diễn mã định danh theo định dạng UUID.
- `Date` biểu diễn ngày lịch, không có thời gian trong ngày.
- `DateTime` biểu diễn thời điểm kèm múi giờ hoặc offset.
- `Decimal` biểu diễn số thập phân chính xác cho tiền tệ hoặc số đo.
- `EmailAddress` biểu diễn địa chỉ email theo quy tắc của ứng dụng.

Không nên tạo scalar cho dữ liệu có cấu trúc nhiều field. Nếu một giá trị có `street`, `city`, `postalCode`, hãy cân nhắc object type hoặc input object. Nếu miền giá trị là một tập hữu hạn có tên, enum thường phù hợp hơn scalar. Custom scalar nên đại diện cho một giá trị nguyên tử có quy tắc nhất quán.

## 2. GraphQLScalarType trong GraphQL Java

Trong GraphQL Java, `GraphQLScalarType` mô tả tên scalar, description, coercing và metadata liên quan. Có thể tạo đối tượng bằng builder:

```java
GraphQLScalarType scalar = GraphQLScalarType.newScalar()
        .name("UUID")
        .description("Mã định danh UUID ở dạng chuỗi chuẩn.")
        .coercing(uuidCoercing)
        .build();
```

Các phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `name` | Tên scalar được tham chiếu trong SDL, ví dụ `UUID` |
| `description` | Mô tả scalar trong schema và introspection |
| `coercing` | Quy tắc chuyển đổi, kiểm tra input và serialize output |
| `specifiedByUrl` (nếu phiên bản hỗ trợ) | Liên kết đến đặc tả định dạng scalar |

Trong SDL, custom scalar phải được khai báo bằng từ khóa `scalar`:

```graphql
scalar UUID

type Query {
  book(id: UUID!): Book
}

type Book {
  id: UUID!
  title: String!
}
```

Khai báo `scalar UUID` chỉ thông báo cho schema rằng có một scalar tên `UUID`. Nó không tự định nghĩa cách đọc chuỗi JSON thành `java.util.UUID`, cũng không kiểm tra định dạng. Phần coercing trong runtime wiring mới cung cấp hành vi đó.

## 3. Coercing có ba hướng chuyển đổi

`Coercing` là hợp đồng giữa GraphQL và kiểu Java mà ứng dụng sử dụng. Ba phương thức quan trọng tương ứng với ba tình huống khác nhau:

| Phương thức | Hướng chuyển đổi | Khi nào được gọi? |
| --- | --- | --- |
| `parseValue` | Input bên ngoài → kiểu Java | Khi client truyền biến trong JSON `variables` |
| `parseLiteral` | GraphQL AST literal → kiểu Java | Khi client ghi giá trị trực tiếp trong GraphQL document |
| `serialize` | Giá trị Java → giá trị trả về GraphQL | Khi resolver trả kết quả cho client |

Ví dụ cùng một UUID có thể được truyền theo hai cách:

```graphql
# Literal trực tiếp: đi qua parseLiteral.
query {
  book(id: "550e8400-e29b-41d4-a716-446655440000") {
    id
    title
  }
}
```

Hoặc dùng variables:

```graphql
query FindBook($id: UUID!) {
  book(id: $id) {
    id
    title
  }
}
```

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Trong request thứ hai, GraphQL gọi `parseValue` để chuyển chuỗi JSON thành kiểu Java. Trong response, nếu resolver trả về một `UUID`, GraphQL gọi `serialize` để tạo chuỗi mà client có thể đọc.

### parseValue: xử lý variables

`parseValue` nhận dữ liệu bên ngoài thường đến từ JSON. Phương thức cần kiểm tra cả kiểu dữ liệu lẫn nội dung. Nếu scalar yêu cầu chuỗi, không nên âm thầm chuyển số hoặc object thành chuỗi.

### parseLiteral: xử lý literal trong document

`parseLiteral` nhận node AST của GraphQL, ví dụ `StringValue`, `IntValue` hoặc `ObjectValue`. Scalar UUID chỉ chấp nhận `StringValue`. Nếu client viết `book(id: 123)`, parser không nên tự biến số thành UUID.

### serialize: trả dữ liệu về client

`serialize` xử lý giá trị do data fetcher/resolver trả về. Nó phải tạo một giá trị GraphQL hợp lệ, ổn định và có thể được biểu diễn trong response. Không nên trả trực tiếp một object Java tùy ý nếu scalar được công bố là chuỗi.

## 4. Ví dụ xây dựng custom UUID scalar

Giả sử domain model dùng `java.util.UUID`, còn GraphQL client gửi và nhận UUID dưới dạng chuỗi chuẩn. Ta tạo `GraphQLScalarType` có kiểu Java nội bộ là `UUID` và kiểu serialize ra ngoài là `String`.

Ví dụ dưới đây dùng chữ ký `Coercing` hiện đại của GraphQL Java, có `GraphQLContext`, `Locale` và `CoercedVariables`. Chữ ký này thay đổi giữa các thế hệ GraphQL Java; hãy dùng phiên bản GraphQL Java do Spring Boot quản lý và đối chiếu API tương ứng khi nâng cấp.

```java
import graphql.GraphQLContext;
import graphql.execution.CoercedVariables;
import graphql.language.StringValue;
import graphql.language.Value;
import graphql.schema.Coercing;
import graphql.schema.CoercingParseLiteralException;
import graphql.schema.CoercingParseValueException;
import graphql.schema.CoercingSerializeException;
import graphql.schema.GraphQLScalarType;

import java.util.Locale;
import java.util.UUID;

public final class UuidScalar {

    private UuidScalar() {
    }

    public static final GraphQLScalarType UUID_SCALAR =
            GraphQLScalarType.newScalar()
                    .name("UUID")
                    .description("Mã định danh UUID ở dạng chuỗi chuẩn.")
                    .coercing(new Coercing<UUID, String>() {

                        @Override
                        public String serialize(
                                Object dataFetcherResult,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (dataFetcherResult instanceof UUID uuid) {
                                return uuid.toString();
                            }
                            if (dataFetcherResult instanceof String value) {
                                try {
                                    return parseCanonical(value).toString();
                                }
                                catch (IllegalArgumentException ex) {
                                    throw new CoercingSerializeException(
                                            "Expected a valid UUID value.");
                                }
                            }
                            throw new CoercingSerializeException(
                                    "Expected UUID or canonical UUID string.");
                        }

                        @Override
                        public UUID parseValue(
                                Object input,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (!(input instanceof String value)) {
                                throw new CoercingParseValueException(
                                        "UUID input must be a string.");
                            }
                            try {
                                return parseCanonical(value);
                            }
                            catch (IllegalArgumentException ex) {
                                throw new CoercingParseValueException(
                                        "UUID input must use canonical UUID format.");
                            }
                        }

                        @Override
                        public UUID parseLiteral(
                                Value<?> input,
                                CoercedVariables variables,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (!(input instanceof StringValue stringValue)) {
                                throw new CoercingParseLiteralException(
                                        "UUID literal must be a string.");
                            }
                            try {
                                return parseCanonical(stringValue.getValue());
                            }
                            catch (IllegalArgumentException ex) {
                                throw new CoercingParseLiteralException(
                                        "UUID literal must use canonical UUID format.");
                            }
                        }
                    })
                    .build();

    private static UUID parseCanonical(String value) {
        UUID uuid = UUID.fromString(value);
        if (!uuid.toString().equalsIgnoreCase(value)) {
            throw new IllegalArgumentException("UUID is not canonical.");
        }
        return uuid;
    }
}
```

Điểm đáng chú ý:

- `parseValue` chỉ nhận `String`, sau đó parse thành `UUID`.
- `parseLiteral` chỉ nhận `StringValue`, không nhận số hay object literal.
- `serialize` chấp nhận `UUID` trong domain model và trả về chuỗi chuẩn.
- Các lỗi input và output dùng loại exception riêng để GraphQL phân biệt lỗi parse với lỗi serialize.
- Hàm `parseCanonical` kiểm tra chuỗi có đúng dạng chuẩn thay vì dựa hoàn toàn vào việc `UUID.fromString` có parse được hay không.

Đây là ví dụ scalar định dạng UUID; một ứng dụng thực tế có thể đơn giản hóa việc kiểm tra hoặc dùng implementation đã được thư viện chuẩn hóa. Không nên sao chép một regex kiểm tra email hoặc ngày giờ ngắn rồi xem nó là validator hoàn chỉnh nếu domain yêu cầu quy tắc phức tạp.

## 5. Đăng ký GraphQLScalarType trong Spring for GraphQL

Sau khi tạo scalar, cần kết nối nó với GraphQL schema runtime. Spring for GraphQL cung cấp `RuntimeWiringConfigurer` để bổ sung scalar vào GraphQL Java runtime wiring.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer uuidScalarConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(UuidScalar.UUID_SCALAR);
    }
}
```

Spring Boot thu thập các bean `RuntimeWiringConfigurer` khi xây dựng `GraphQlSource`. Scalar được đăng ký vào runtime wiring và có thể được dùng bởi những field khai báo `UUID` trong SDL.

Schema:

```graphql
scalar UUID

type Query {
  book(id: UUID!): Book
}

type Book {
  id: UUID!
  title: String!
}
```

Resolver có thể nhận kiểu Java `UUID` sau khi `parseValue` hoặc `parseLiteral` hoàn tất:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument UUID id) {
        return bookService.findById(id);
    }
}
```

Nếu `Book.id` là `UUID`, `serialize` của custom scalar sẽ chuyển nó thành chuỗi trong response. Nhờ đó domain layer có thể dùng kiểu mạnh `UUID`, trong khi GraphQL contract dùng biểu diễn chuỗi dễ trao đổi qua JSON.

## 6. Dùng scalar có sẵn từ thư viện mở rộng

Không phải lúc nào cũng cần tự viết `Coercing`. GraphQL Java Extended Scalars cung cấp một số scalar phổ biến như `Date`, `DateTime`, `Time`, `Url`, `Email`, `BigDecimal` và các kiểu khác tùy phiên bản thư viện.

Ví dụ dùng `ExtendedScalars.Date`:

```gradle
dependencies {
    implementation("com.graphql-java:graphql-java-extended-scalars")
}
```

Hãy chọn phiên bản thư viện tương thích với GraphQL Java đang được Spring Boot quản lý; không nên nâng riêng GraphQL Java chỉ để khớp một bản Extended Scalars.

Đăng ký scalar:

```java
@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiring -> wiring.scalar(ExtendedScalars.Date);
    }
}
```

SDL:

```graphql
scalar Date

type Book {
  publishedOn: Date
}
```

Extended Scalars giúp giảm code coercion và tận dụng quy tắc định dạng đã có. Tuy nhiên, hãy kiểm tra tài liệu của phiên bản thư viện đang dùng: định dạng đầu vào, kiểu Java được parse ra, quy tắc timezone và cách serialize có thể khác điều mà hệ thống mong đợi.

Không nên đăng ký đồng thời nhiều scalar cùng tên hoặc thay thế scalar tích hợp như `String` bằng custom scalar. Tên scalar trong SDL phải khớp với tên scalar đã đăng ký.

## 7. Kiểm thử scalar với variables, literals và output

Custom scalar cần được kiểm thử theo cả ba hướng coercion. Chỉ kiểm tra `parseValue` chưa đủ vì literal inline đi qua `parseLiteral`, còn giá trị resolver trả về đi qua `serialize`.

### Kiểm thử variables hợp lệ

Với schema `book(id: UUID!): Book`, gửi variables:

```java
graphQlTester.document("""
        query FindBook($id: UUID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "550e8400-e29b-41d4-a716-446655440000")
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("550e8400-e29b-41d4-a716-446655440000");
```

Test này đi qua `parseValue`, gọi resolver với kiểu Java `UUID`, sau đó đi qua `serialize` để tạo response string.

### Kiểm thử literal hợp lệ

```java
graphQlTester.document("""
        query {
            book(id: "550e8400-e29b-41d4-a716-446655440000") {
                id
            }
        }
        """)
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("550e8400-e29b-41d4-a716-446655440000");
```

Test này kiểm tra `parseLiteral`.

### Kiểm thử input không hợp lệ

Có thể gửi UUID sai định dạng hoặc sai kiểu JSON:

```java
graphQlTester.document("""
        query FindBook($id: UUID!) {
            book(id: $id) {
                id
            }
        }
        """)
    .variable("id", "not-a-uuid")
    .execute()
    .errors()
    .expect(error -> error.getMessage()
            .contains("UUID input must use canonical UUID format"))
    .verify();
```

Với scalar UUID, cần kiểm tra rằng giá trị sai bị từ chối trước khi resolver xử lý. Trong test đầy đủ, có thể verify service mock không được gọi.

### Kiểm thử serialization

Cho resolver trả về một `UUID`, kiểm tra response là chuỗi chuẩn. Đồng thời thử trả về một object sai kiểu để xác nhận scalar tạo serialization error. Không nên chỉ test trường hợp đầu vào vì lỗi serialize có thể xảy ra khi dữ liệu database hoặc domain object không tuân thủ contract.

## 8. Cách GraphQL biểu diễn lỗi coercion

Các lỗi scalar thường xuất hiện ở những thời điểm khác nhau:

| Lỗi | Phương thức | Hệ quả thường gặp |
| --- | --- | --- |
| Variable không parse được | `parseValue` | Request bị từ chối ở giai đoạn coercion variables; resolver tương ứng không được gọi |
| Literal sai kiểu hoặc sai định dạng | `parseLiteral` | Document không vượt qua validation/coercion; field không được thực thi |
| Resolver trả giá trị không serialize được | `serialize` | Lỗi xảy ra trong quá trình thực thi field và được đưa vào `errors`; null propagation tuân theo nullability của schema |

Ví dụ, schema khai báo `id: UUID!` nhưng resolver trả về chuỗi `"invalid"`. `serialize` không thể tạo giá trị hợp lệ. GraphQL báo lỗi cho field đó; do field non-null, null có thể lan truyền lên object cha gần nhất có thể nhận null. Vì vậy custom scalar cần kiểm tra cả input và output.

Không nên ném `RuntimeException` chung chung từ mọi nhánh coercion. Dùng `CoercingParseValueException`, `CoercingParseLiteralException` và `CoercingSerializeException` giúp mô tả đúng loại lỗi và hỗ trợ GraphQL tạo error response phù hợp.

## 9. Thiết kế custom scalar an toàn

Custom scalar là ranh giới giữa dữ liệu client gửi và kiểu dữ liệu mà domain layer tin cậy. Hãy tuân thủ một số nguyên tắc:

- **Kiểm tra kiểu nghiêm ngặt:** nếu scalar công bố là chuỗi, không tự chuyển số hoặc object thành chuỗi.
- **Có định dạng chuẩn:** nếu có nhiều biểu diễn tương đương, quyết định có chấp nhận tất cả hay chỉ một dạng canonical.
- **Parse và serialize đối xứng:** dữ liệu server serialize ra nên có thể được parse lại theo contract, trong phạm vi định dạng cho phép.
- **Không phụ thuộc trạng thái request:** coercing nên là phép chuyển đổi xác định, không đọc database hoặc gọi network.
- **Giới hạn kích thước:** scalar dạng chuỗi cần giới hạn độ dài để tránh input quá lớn.
- **Thông báo lỗi vừa đủ:** nói rõ định dạng mong đợi nhưng không tiết lộ thông tin nội bộ hoặc dữ liệu nhạy cảm.
- **Không thay thế authorization:** UUID hợp lệ không chứng minh người dùng có quyền truy cập tài nguyên mang UUID đó.
- **Không nhầm validation cú pháp với validation nghiệp vụ:** email có cú pháp hợp lệ chưa chắc tồn tại; currency code hợp lệ chưa chắc được phép dùng trong giao dịch cụ thể.

Với `DateTime`, cần quyết định rõ có bắt buộc offset hay không, có chuẩn hóa về UTC không và độ chính xác đến mili giây hay nano giây. Với `Decimal`, cần xác định precision, scale, cách làm tròn và có cho phép scientific notation không. Các quyết định này nên nằm trong description hoặc đặc tả scalar để client sử dụng thống nhất.

## 10. GraphQLScalarType và các lựa chọn khác

Không phải mọi kiểu dữ liệu đều nên được tạo thành custom scalar:

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Chuỗi, số nguyên, số thực, boolean | Built-in scalar |
| Một tập giá trị hữu hạn có tên | Enum |
| Một giá trị nguyên tử có định dạng riêng | Custom scalar / `GraphQLScalarType` |
| Object có nhiều field trả về | Object type |
| Nhóm dữ liệu client gửi vào | Input object |
| Phân biệt nhiều loại object | Interface hoặc union |

Custom scalar giúp contract gọn và có kiểu Java rõ ràng, nhưng nó cũng ẩn cấu trúc bên trong khỏi GraphQL selection set. Nếu client cần truy vấn một phần dữ liệu, hãy dùng object type thay vì đóng gói mọi thứ vào một scalar JSON tùy biến.

## 11. Lỗi thường gặp khi tích hợp custom scalar

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Unknown type UUID` | SDL tham chiếu scalar nhưng chưa khai báo `scalar UUID` hoặc file schema không được nạp | Kiểm tra SDL và schema locations |
| Scalar đã khai báo nhưng input không parse được | Chưa đăng ký `GraphQLScalarType` trong runtime wiring | Thêm `RuntimeWiringConfigurer` |
| Variables hợp lệ nhưng literal thất bại | `parseValue` đúng nhưng `parseLiteral` chưa xử lý AST tương ứng | Kiểm tra `StringValue`, `IntValue` hoặc AST node cần hỗ trợ |
| Resolver nhận `String` thay vì kiểu domain | Coercing parse ra sai kiểu Java hoặc scalar không được đăng ký đúng | Xem generic type và `parseValue`/`parseLiteral` |
| Response có serialization error | Resolver trả object không tương thích với scalar | Kiểm tra `serialize` và kiểu dữ liệu từ service |
| Scalar name bị trùng | Nhiều config đăng ký các scalar khác nhau cùng tên | Chỉ đăng ký một định nghĩa cho mỗi tên scalar |
| Code không compile sau khi nâng cấp Boot | Chữ ký `Coercing` thay đổi theo GraphQL Java version | Dùng dependency được Boot quản lý và cập nhật override methods |

## 12. Bài tập thực hành

Xây dựng custom scalar `ISBN` cho API quản lý sách:

1. Khai báo `scalar ISBN` trong SDL.
2. Tạo `GraphQLScalarType` tên `ISBN` với description giải thích định dạng được hỗ trợ.
3. Viết `Coercing` để `parseValue` và `parseLiteral` chỉ nhận chuỗi có định dạng ISBN mà ứng dụng cho phép.
4. Viết `serialize` để response luôn có một biểu diễn thống nhất.
5. Đăng ký scalar bằng `RuntimeWiringConfigurer`.
6. Dùng `@Argument ISBN` hoặc kiểu Java tương ứng để nhận giá trị đã parse.
7. Viết test cho variable hợp lệ, literal hợp lệ, chuỗi sai định dạng, sai kiểu JSON và serialization.

Ví dụ schema:

```graphql
scalar ISBN

type Query {
  bookByIsbn(isbn: ISBN!): Book
}

type Book {
  id: ID!
  isbn: ISBN!
  title: String!
}
```

Khi hoàn thành, hãy kiểm tra rằng cùng một quy tắc định dạng được áp dụng cho variables, inline literals và dữ liệu trả về. Đây là tiêu chí quan trọng để custom scalar trở thành hợp đồng dữ liệu đáng tin cậy cho client và các resolver trong Spring for GraphQL.
