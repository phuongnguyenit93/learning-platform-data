# Scalar type

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích scalar type là kiểu dữ liệu lá trong GraphQL và cách nó xuất hiện trong schema.
- Phân biệt năm scalar tích hợp sẵn: `Int`, `Float`, `String`, `Boolean` và `ID`.
- Hiểu cách GraphQL chuyển đổi dữ liệu đầu vào và kết quả đầu ra.
- Thiết kế custom scalar cho các giá trị miền nghiệp vụ như ngày giờ hoặc mã định danh chuyên biệt.
- Đăng ký scalar với Spring for GraphQL thông qua `RuntimeWiringConfigurer` và kiểm thử việc parse, serialize.

## Scalar type là gì?

Scalar là kiểu dữ liệu cơ bản mà GraphQL xem như một giá trị đơn. Khi client truy vấn một field scalar, client nhận trực tiếp giá trị đó và không viết selection set con cho nó.

Ví dụ, `Book` có các field `id`, `title` và `published`:

```graphql
type Book {
  id: ID!
  title: String!
  published: Boolean!
}
```

Client có thể chọn cả ba field:

```graphql
query {
  bookById(id: "book-101") {
    id
    title
    published
  }
}
```

Response chứa các giá trị lá:

```json
{
  "data": {
    "bookById": {
      "id": "book-101",
      "title": "Spring in Practice",
      "published": true
    }
  }
}
```

Field `id`, `title` và `published` không có các field con. Ngược lại, nếu `Book` có field `author: Author`, client cần viết selection set cho `author` vì `Author` là object type.

Scalar được dùng ở cả vị trí đầu ra và đầu vào: kiểu trả về của field, argument của field và field trong input object. Một scalar có thể xuất hiện ở cả hai phía, ví dụ `String` dùng để trả về tên sách hoặc nhận từ khóa tìm kiếm.

## Năm scalar tích hợp sẵn

GraphQL định nghĩa năm scalar chuẩn mà mọi implementation cần hỗ trợ:

| Scalar | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Int` | Số nguyên có dấu 32 bit | `42`, `-7` |
| `Float` | Số thực dấu phẩy động | `19.95`, `-0.5` |
| `String` | Chuỗi ký tự Unicode | `"GraphQL"` |
| `Boolean` | Giá trị đúng hoặc sai | `true`, `false` |
| `ID` | Định danh của object, được truyền dưới dạng chuỗi | `"book-101"` |

Các scalar này có quy tắc coercion riêng. Việc Java có một kiểu dữ liệu tương tự không có nghĩa mọi giá trị Java đều tự động hợp lệ với scalar GraphQL.

### `Int`

`Int` là số nguyên có dấu 32 bit, trong khoảng từ -2.147.483.648 đến 2.147.483.647. Nó phù hợp với số lượng, thứ tự hoặc bộ đếm có giới hạn trong miền nghiệp vụ.

```graphql
type Inventory {
  availableQuantity: Int!
}
```

Không dùng `Int` cho số nguyên lớn vượt phạm vi 32 bit. Nếu nghiệp vụ cần số lớn hơn, hãy cân nhắc custom scalar như `Long` hoặc `BigInteger` từ thư viện scalar mở rộng, đồng thời thống nhất cách biểu diễn với client.

### `Float`

`Float` biểu diễn số thực theo quy tắc số dấu phẩy động của GraphQL. Ví dụ:

```graphql
type Product {
  rating: Float
  weight: Float
}
```

Kiểu số thực dấu phẩy động có thể có sai số biểu diễn. Không nên dùng `Float` để lưu hoặc truyền tiền tệ nếu nghiệp vụ yêu cầu tính toán thập phân chính xác. Hãy cân nhắc `BigDecimal` ở tầng Java và một scalar thập phân được định nghĩa rõ về cách serialize, parse và độ chính xác.

### `String`

`String` dùng cho văn bản. Giá trị string trong GraphQL literal được đặt trong dấu nháy kép:

```graphql
query {
  searchBooks(keyword: "Spring") {
    title
  }
}
```

Với dữ liệu đầu vào từ client, server vẫn cần kiểm tra độ dài, định dạng và nội dung theo yêu cầu nghiệp vụ. Kiểu `String` chỉ xác nhận dữ liệu là chuỗi, không tự kiểm tra email, URL, mã sản phẩm hoặc các quy tắc riêng của ứng dụng.

### `Boolean`

`Boolean` chỉ nhận hai giá trị `true` và `false`:

```graphql
type Book {
  archived: Boolean!
}
```

Không nhầm `false` với `null`. `false` là một giá trị xác định; `null` thể hiện field không có giá trị hoặc được phép thiếu theo schema và kết quả thực thi.

### `ID`

`ID` biểu diễn định danh và thường dùng cho khóa của object:

```graphql
type Query {
  bookById(id: ID!): Book
}
```

`ID` được serialize thành chuỗi trong response. Khi truyền input, GraphQL cho phép giá trị string hoặc integer theo quy tắc của scalar này, dù giá trị được viết trực tiếp trong document hay truyền qua variables; dù vậy, nên dùng chuỗi để thể hiện rõ định danh trong query và variables.

`ID` không có nghĩa server tự kiểm tra sự tồn tại, tính duy nhất hoặc quyền truy cập vào object. Nó cũng không bắt buộc phải là UUID hay khóa chính database. Đó là quy ước mà ứng dụng cần xác định.

## Scalar trong input và output

Scalar xuất hiện trong khai báo kiểu trả về:

```graphql
type Book {
  id: ID!
  title: String!
  pageCount: Int
}
```

Scalar cũng xuất hiện trong argument và input object:

```graphql
input CreateBookInput {
  title: String!
  pageCount: Int
  published: Boolean = false
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

Trong ví dụ này, `String`, `Int` và `Boolean` là kiểu của dữ liệu client gửi lên. Server cần kiểm tra giá trị trước khi dùng trong nghiệp vụ. `published` có giá trị mặc định `false` khi client không cung cấp field này theo quy tắc default value của GraphQL.

Scalar là kiểu hợp lệ cho cả input và output. Object type chỉ dùng cho output; input object chỉ dùng cho input. Nếu cần truyền một cấu trúc dữ liệu lồng nhau vào mutation, hãy khai báo `input` type thay vì dùng object type.

## Nullability và list không phải scalar mới

Dấu `!` và cặp dấu ngoặc vuông là type modifier của GraphQL. Chúng có thể bọc scalar hoặc các kiểu hợp lệ khác:

| Khai báo | Ý nghĩa |
| --- | --- |
| `String` | Một chuỗi hoặc `null` |
| `String!` | Bắt buộc có chuỗi, không được `null` |
| `[String]` | Một list có thể `null`, từng phần tử có thể `null` |
| `[String!]` | List có thể `null`, từng phần tử không được `null` |
| `[String]!` | List không được `null`, phần tử có thể `null` |
| `[String!]!` | List và mọi phần tử đều không được `null` |

Ví dụ:

```graphql
type Author {
  nicknames: [String!]!
}
```

Field `nicknames` luôn trả về một list; list có thể rỗng nhưng không thể `null`, và mỗi phần tử phải là một string khác `null`. Nullability ảnh hưởng trực tiếp đến cách GraphQL lan truyền lỗi khi một resolver trả về `null` cho field non-null.

## GraphQL coercion: parse input và serialize output

GraphQL không chỉ chuyển JSON thành object Java. GraphQL engine thực hiện coercion để bảo đảm dữ liệu phù hợp với scalar được khai báo.

Có ba thao tác quan trọng khi làm việc với scalar:

| Thao tác | Hướng dữ liệu | Ý nghĩa |
| --- | --- | --- |
| Parse value | Client variables → giá trị nội bộ | Chuyển đổi và kiểm tra input lấy từ biến JSON |
| Parse literal | GraphQL document → giá trị nội bộ | Chuyển đổi và kiểm tra giá trị viết trực tiếp trong query |
| Serialize | Giá trị resolver → response JSON | Chuyển đổi giá trị nội bộ thành định dạng client nhận được |

Ví dụ query sử dụng variables:

```graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}
```

```json
{
  "id": "book-101"
}
```

Trong trường hợp này, GraphQL parse variable theo kiểu `ID!`. Nếu client viết trực tiếp `bookById(id: "book-101")`, GraphQL parse literal trong document. Khi resolver trả về một object `Book`, các scalar field như `id` và `title` được serialize trước khi tạo JSON response.

Một giá trị có thể hợp lệ ở tầng Java nhưng không serialize được theo scalar đã khai báo. Ví dụ, nếu resolver trả về object không tương thích với scalar `String`, GraphQL có thể tạo execution error. Vì vậy, khi tạo custom scalar, cần định nghĩa rõ cả ba hướng chuyển đổi, không chỉ kiểm tra input.

## Khi nào cần custom scalar?

Năm scalar chuẩn bao phủ các kiểu dữ liệu cơ bản, nhưng API thực tế thường có các giá trị mang ý nghĩa cụ thể:

- Ngày giờ có múi giờ, ví dụ thời điểm tạo đơn hàng.
- Số thập phân chính xác, ví dụ số tiền hoặc tỷ lệ.
- UUID, URL, email hoặc mã định danh theo định dạng riêng.
- Số nguyên lớn vượt giới hạn của `Int`.

Có thể biểu diễn các giá trị này bằng `String` hoặc `Float`, nhưng khi đó schema không mô tả rõ quy tắc của dữ liệu. Custom scalar giúp đặt tên kiểu có ý nghĩa, tập trung validation và quy định định dạng truyền qua API.

Ví dụ schema khai báo một scalar `DateTime`:

```graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}

type Query {
  event(id: ID!): Event
}
```

Tên `DateTime` cho client biết field là một giá trị ngày giờ. Tuy nhiên, SDL tự nó không quy định chuỗi phải theo ISO-8601, có bắt buộc múi giờ hay không, hoặc Java nên dùng `Instant`, `OffsetDateTime` hay kiểu khác. Những quy tắc đó phải được xác định bởi implementation scalar và tài liệu API.

## Dùng scalar mở rộng có sẵn

Trước khi tự viết `Coercing`, hãy kiểm tra thư viện scalar mở rộng. Dự án GraphQL Java có thư viện `graphql-java-extended-scalars`, cung cấp các scalar phổ biến như `DateTime`, `Date`, `Long`, `BigDecimal`, `UUID` và một số kiểu khác.

Thêm dependency tương thích với phiên bản GraphQL Java mà Spring Boot đang quản lý. Ví dụ Gradle:

```groovy
dependencies {
    implementation 'com.graphql-java:graphql-java-extended-scalars:<compatible-version>'
}
```

Placeholder `<compatible-version>` cần được thay bằng phiên bản phù hợp với GraphQL Java trong dependency management của ứng dụng. Tránh nâng GraphQL Java độc lập chỉ để lấy một scalar nếu việc đó làm lệch phiên bản mà Spring for GraphQL hỗ trợ.

Sau khi thêm dependency, đăng ký scalar với `RuntimeWiringConfigurer`:

```java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.DateTime);
    }
}
```

SDL có thể dùng scalar đó:

```graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}
```

Spring Boot GraphQL thu thập bean `RuntimeWiringConfigurer` và áp dụng khi xây dựng runtime wiring. Scalar phải được đăng ký với đúng tên mà schema sử dụng. Hãy đọc tài liệu của phiên bản thư viện đang dùng để xác nhận kiểu Java được scalar hỗ trợ và định dạng dữ liệu mà nó chấp nhận.

## Tự định nghĩa custom scalar

Khi kiểu dữ liệu có quy tắc riêng của hệ thống, bạn có thể định nghĩa một `GraphQLScalarType` bằng GraphQL Java. Thành phần quan trọng là `Coercing`, nơi triển khai parse input và serialize output.

Ví dụ, hệ thống thư viện dùng mã đơn hàng theo định dạng `ORD-` cộng sáu chữ số. SDL khai báo:

```graphql
scalar OrderCode

type Order {
  code: OrderCode!
}

type Query {
  order(code: OrderCode!): Order
}
```

Scalar implementation có thể biểu diễn giá trị nội bộ bằng Java `String`. Ví dụ dưới đây minh họa các điểm mở rộng; chữ ký method cụ thể của `Coercing` có thể khác nhau giữa các phiên bản GraphQL Java, vì vậy cần điều chỉnh theo dependency của dự án:

```java
private static final Pattern ORDER_CODE_PATTERN =
        Pattern.compile("ORD-[0-9]{6}");

private static boolean isValidOrderCode(String value) {
    return ORDER_CODE_PATTERN.matcher(value).matches();
}

private static final GraphQLScalarType ORDER_CODE =
        GraphQLScalarType.newScalar()
            .name("OrderCode")
            .description("Mã đơn hàng có dạng ORD- theo sau bởi sáu chữ số")
            .coercing(new Coercing<String, String>() {
                // serialize: kiểm tra giá trị resolver trả về và chuyển thành String.
                // parseValue: kiểm tra input lấy từ variables.
                // parseLiteral: kiểm tra literal trong GraphQL document.
            })
            .build();
```

Đoạn code trên tập trung vào cấu trúc scalar; phần thân ba method cần triển khai theo API `Coercing` của phiên bản GraphQL Java đang dùng. Mỗi method nên từ chối dữ liệu sai định dạng bằng exception tương ứng (`CoercingSerializeException`, `CoercingParseValueException` hoặc `CoercingParseLiteralException`). Không nên trả `null` để che giấu input không hợp lệ.

Đăng ký scalar giống cách đăng ký scalar mở rộng:

```java
@Bean
RuntimeWiringConfigurer runtimeWiringConfigurer() {
    return wiringBuilder -> wiringBuilder.scalar(ORDER_CODE);
}
```

Với `parseLiteral`, cần kiểm tra đúng kiểu AST node mà scalar chấp nhận, chẳng hạn string literal. Với `parseValue`, cần kiểm tra kiểu Java của dữ liệu variables. Với `serialize`, cần bảo đảm giá trị resolver trả về có thể chuyển thành định dạng wire ổn định. Ba đường này phải áp dụng cùng một quy tắc nghiệp vụ để query dùng variables và query dùng literal không có hành vi khác nhau.

## Mô tả contract của custom scalar

Tên scalar giúp schema rõ hơn, nhưng client không tự biết toàn bộ định dạng chỉ từ tên. Hãy ghi mô tả SDL và công bố đặc tả nếu scalar dùng một chuẩn bên ngoài:

```graphql
"""Mã đơn hàng theo định dạng ORD- cộng sáu chữ số."""
scalar OrderCode
```

GraphQL cũng hỗ trợ directive `@specifiedBy` trên scalar để liên kết đến tài liệu mô tả đặc tả của scalar:

```graphql
scalar DateTime @specifiedBy(url: "https://example.com/api/date-time-format")
```

URL trên chỉ là ví dụ minh họa; trong API thực tế, hãy dùng một tài liệu ổn định do tổ chức sở hữu hoặc một đặc tả công khai phù hợp. Tài liệu nên mô tả định dạng literal, định dạng variables, định dạng response, timezone, độ chính xác và các giới hạn dữ liệu.

## Kiểm thử scalar trong Spring for GraphQL

Scalar cần được kiểm thử độc lập và qua operation GraphQL. Với `GraphQlTester`, có thể gửi variables để xác minh parse value và kiểm tra response để xác minh serialize.

Ví dụ kiểm thử query nhận `OrderCode`:

```java
graphQlTester.document("""
        query FindOrder($code: OrderCode!) {
            order(code: $code) {
                code
            }
        }
        """)
    .variable("code", "ORD-000123")
    .execute()
    .path("order.code")
    .entity(String.class)
    .isEqualTo("ORD-000123");
```

Nên kiểm tra cả trường hợp hợp lệ và không hợp lệ:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `ORD-000123` | Parse thành công |
| `ORD-12` | Bị từ chối do sai định dạng |
| `ord-000123` | Bị từ chối nếu quy ước phân biệt chữ hoa/thường |
| Giá trị không phải chuỗi | Bị từ chối khi scalar yêu cầu string |
| Resolver trả mã không hợp lệ | Serialize thất bại và tạo execution error |
| Query truyền literal thay vì variable | `parseLiteral` áp dụng cùng quy tắc validation |

Khi kiểm thử lỗi, hãy xác minh response có error phù hợp và không để lộ chi tiết nội bộ như stack trace hoặc dữ liệu nhạy cảm. Với custom scalar ngày giờ, bổ sung test cho timezone, offset, độ chính xác phần giây và các giá trị biên.

## Những lỗi thiết kế scalar thường gặp

**Dùng `Float` cho tiền tệ.** Số dấu phẩy động có thể tạo sai số khi tính toán. Hãy chọn biểu diễn thập phân chính xác và thống nhất scale, rounding, currency.

**Coi `ID` là cơ chế bảo mật.** `ID` chỉ mô tả định danh. Server vẫn phải kiểm tra object tồn tại và người dùng có quyền truy cập hay không.

**Chỉ validate variables.** Query có thể truyền literal trực tiếp. Custom scalar cần xử lý cả `parseValue` và `parseLiteral`.

**Chỉ parse input mà quên serialize.** Resolver có thể trả về dữ liệu không đúng định dạng scalar. Cần kiểm tra cả giá trị đầu ra.

**Định nghĩa scalar quá chung chung.** Một scalar tên `Date` nhưng không nói rõ timezone, format hoặc độ chính xác sẽ khiến client phải đoán. Hãy mô tả contract và kiểm thử định dạng.

**Dùng custom scalar để thay thế object type.** Scalar phù hợp với một giá trị đơn. Nếu dữ liệu có nhiều thuộc tính mà client cần chọn riêng, hãy dùng object type. Ví dụ `Money { amount, currency }` thường linh hoạt hơn một chuỗi tiền tệ không có cấu trúc.

**Bỏ qua giới hạn dữ liệu.** Scalar chuỗi có thể nhận payload rất dài nếu server không giới hạn. Hãy đặt giới hạn kích thước, kiểm tra định dạng và tránh xử lý tốn tài nguyên trên input không đáng tin cậy.

## Thực hành tổng hợp

Trong API quản lý đơn hàng, hãy thiết kế schema có các field:

1. `Order.id` dùng `ID!`.
2. `Order.totalAmount` dùng kiểu thập phân phù hợp với yêu cầu chính xác của tiền tệ.
3. `Order.createdAt` dùng custom scalar `DateTime`.
4. `Query.order(code: OrderCode!)` nhận mã đơn hàng theo định dạng do hệ thống quy định.

Triển khai theo các bước:

- Chọn scalar tích hợp sẵn khi kiểu dữ liệu phù hợp.
- Thêm thư viện scalar mở rộng nếu có scalar đáp ứng đúng contract.
- Chỉ tự viết `Coercing` khi cần quy tắc riêng.
- Đăng ký scalar với `RuntimeWiringConfigurer`.
- Viết test cho literal, variables, output serialization và input sai định dạng.
- Viết tài liệu về format, nullability, độ chính xác và giới hạn của từng scalar.

## Ghi nhớ

Scalar là kiểu dữ liệu lá của GraphQL. Năm scalar chuẩn gồm `Int`, `Float`, `String`, `Boolean` và `ID`; chúng có quy tắc coercion và giới hạn riêng. Dấu `!` và list là type modifier, không phải scalar mới. Khi cần kiểu ngày giờ, số thập phân hoặc định danh chuyên biệt, có thể dùng thư viện scalar mở rộng hoặc tự định nghĩa `GraphQLScalarType` với `Coercing`. Trong Spring for GraphQL, đăng ký scalar qua `RuntimeWiringConfigurer`; kiểm thử cả parse variables, parse literal và serialize output để bảo đảm contract nhất quán.
