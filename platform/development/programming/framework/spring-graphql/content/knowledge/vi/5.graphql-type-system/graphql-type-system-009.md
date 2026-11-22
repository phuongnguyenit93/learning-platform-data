# Schema directive trong GraphQL

**Directive** là một thành phần của GraphQL dùng để bổ sung chỉ dẫn hoặc metadata cho schema và operation. Directive có tên bắt đầu bằng ký tự `@`, có thể nhận argument và chỉ được đặt tại những vị trí mà directive đó cho phép. Ví dụ quen thuộc là `@include`, `@skip` trong query và `@deprecated` trong schema.

Với Spring for GraphQL, directive thuộc GraphQL type system và được khai báo bằng SDL. GraphQL Java thực thi các directive tích hợp sẵn; directive tùy chỉnh cần được ứng dụng đăng ký cách xử lý thông qua cơ chế xây dựng schema, chẳng hạn `RuntimeWiringConfigurer` và `SchemaDirectiveWiring`.

## 1. Cấu trúc của một directive

Một directive có ba thành phần chính:

- **Tên:** định danh bắt đầu bằng `@`, ví dụ `@deprecated` hoặc `@requiresRole`.
- **Argument:** dữ liệu cấu hình cho directive, ví dụ `if: Boolean!` hoặc `role: Role!`.
- **Location:** vị trí mà directive được phép xuất hiện, ví dụ `FIELD`, `OBJECT` hoặc `FIELD_DEFINITION`.

Directive tích hợp sẵn và directive tùy chỉnh đều tuân theo cấu trúc này. Trong SDL, directive tùy chỉnh cần được định nghĩa trước khi áp dụng:

```graphql
enum Role {
    USER
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicMessage: String
    adminReport: String @requiresRole(role: ADMIN)
}
```

Khai báo `directive @requiresRole...` mô tả tên, argument và location hợp lệ. Việc gắn `@requiresRole(role: ADMIN)` lên `adminReport` truyền metadata cho schema. Bản thân dòng SDL này chưa tự xác thực người dùng; ứng dụng phải triển khai hành vi tương ứng.

## 2. Directive location

Location xác định nơi directive có thể được áp dụng. Hai nhóm vị trí thường gặp là:

| Nhóm | Location tiêu biểu | Ý nghĩa |
|---|---|---|
| Schema/type system | `SCHEMA`, `SCALAR`, `OBJECT`, `FIELD_DEFINITION`, `ARGUMENT_DEFINITION`, `INTERFACE`, `UNION`, `ENUM`, `ENUM_VALUE`, `INPUT_OBJECT`, `INPUT_FIELD_DEFINITION` | Gắn chỉ dẫn hoặc metadata vào định nghĩa schema. |
| Executable document | `QUERY`, `MUTATION`, `SUBSCRIPTION`, `FIELD`, `FRAGMENT_DEFINITION`, `FRAGMENT_SPREAD`, `INLINE_FRAGMENT`, `VARIABLE_DEFINITION` | Gắn chỉ dẫn vào operation, field, fragment hoặc variable trong request. |

Ví dụ directive chỉ áp dụng cho field trong schema:

```graphql
directive @upperCase on FIELD_DEFINITION
```

Directive này có thể được dùng như sau:

```graphql
type Product {
    name: String @upperCase
}
```

Không thể tùy ý đặt `@upperCase` lên một query field nếu directive chỉ khai báo `FIELD_DEFINITION`. Nếu muốn directive được dùng trong operation, phải khai báo location tương ứng, chẳng hạn `FIELD`.

## 3. Directive tích hợp sẵn trong operation

### `@include`

`@include(if: Boolean!)` yêu cầu GraphQL chỉ đưa field hoặc fragment vào kết quả nếu biểu thức `if` là `true`.

```graphql
query ProductDetail($showDescription: Boolean!) {
    product(id: "p-100") {
        id
        name
        description @include(if: $showDescription)
    }
}
```

Nếu `$showDescription` là `false`, field `description` bị bỏ qua khi thực thi. Client có thể dùng directive này để chọn field theo nhu cầu của màn hình.

### `@skip`

`@skip(if: Boolean!)` có tác dụng ngược lại: bỏ qua field hoặc fragment khi `if` là `true`.

```graphql
query ProductDetail($hidePrice: Boolean!) {
    product(id: "p-100") {
        id
        name
        price @skip(if: $hidePrice)
    }
}
```

Nếu `$hidePrice` là `true`, GraphQL không thực thi lựa chọn `price` trong operation đó. Cả `@include` và `@skip` đều được GraphQL xử lý sẵn; không cần viết resolver hay đăng ký directive tùy chỉnh trong Spring.

Các directive này có thể dùng trên `FIELD`, `FRAGMENT_SPREAD` và `INLINE_FRAGMENT`. Nếu một lựa chọn đồng thời có `@include` và `@skip`, field chỉ được đưa vào thực thi khi điều kiện include đúng và điều kiện skip sai.

## 4. Directive tích hợp sẵn trong schema

### `@deprecated`

`@deprecated` đánh dấu một field hoặc enum value đã cũ và khuyến nghị client chuyển sang API thay thế. Directive nhận argument `reason`; nếu không truyền, lý do mặc định là `No longer supported`.

```graphql
type Product {
    id: ID!
    oldCode: String @deprecated(reason: "Use sku instead")
    sku: String!
}

enum OrderStatus {
    NEW
    PROCESSING
    OLD_DONE @deprecated(reason: "Use COMPLETED")
    COMPLETED
}
```

`@deprecated` không tự xóa field khỏi schema và cũng không chặn client gọi field đó. Nó công bố trạng thái ngừng khuyến nghị để công cụ GraphQL, tài liệu API và client có thể cảnh báo hoặc hỗ trợ migration. Có thể truy vấn metadata này qua introspection, ví dụ `isDeprecated` và `deprecationReason` trên field hoặc enum value; khi lấy danh sách cần yêu cầu cả phần tử deprecated bằng các tham số introspection tương ứng.

Một số phiên bản GraphQL hỗ trợ đánh dấu deprecated thêm ở argument hoặc input field. Hãy kiểm tra phiên bản GraphQL Java đang dùng trước khi áp dụng directive tại những location này.

### `@specifiedBy`

`@specifiedBy(url: String!)` gắn đường dẫn đến đặc tả của một custom scalar. Ví dụ:

```graphql
scalar DateTime @specifiedBy(url: "https://scalars.graphql.org/andimarek/date-time")
```

Directive cung cấp tài liệu để người dùng schema hiểu định dạng và quy tắc của scalar `DateTime`. Nó không tự triển khai parser hoặc serializer cho scalar. Ứng dụng vẫn phải cấu hình scalar tương ứng để chuyển đổi dữ liệu giữa biểu diễn GraphQL và kiểu Java.

## 5. Định nghĩa directive tùy chỉnh

Directive tùy chỉnh phù hợp khi cần gắn metadata hoặc một hành vi dùng chung lên nhiều phần của schema. Cú pháp tổng quát:

```graphql
directive @directiveName(argument: Type) on LOCATION
```

Ví dụ directive dùng để mô tả dữ liệu cần che trong log:

```graphql
directive @sensitive on FIELD_DEFINITION

type Customer {
    id: ID!
    name: String!
    email: String @sensitive
    phone: String @sensitive
}
```

Schema cho biết `email` và `phone` là những field nhạy cảm. Ứng dụng có thể đọc metadata đó trong một cơ chế logging hoặc instrumentation để tránh ghi giá trị thật vào log. Nếu không có phần triển khai đọc và sử dụng directive, `@sensitive` chỉ là metadata trong schema.

### Directive có argument

Argument cho phép một directive được cấu hình khác nhau ở từng vị trí:

```graphql
directive @mask(visibleCharacters: Int! = 2) on FIELD_DEFINITION

type Customer {
    email: String @mask(visibleCharacters: 3)
    phone: String @mask(visibleCharacters: 2)
}
```

Giá trị argument có thể có default. Ở ví dụ này, `visibleCharacters` mặc định là `2`, nhưng field `email` ghi đè thành `3`. Kiểu dữ liệu và giá trị argument vẫn phải hợp lệ theo quy tắc GraphQL.

### Directive `repeatable`

Mặc định, một directive không được lặp nhiều lần trên cùng một vị trí. Thêm từ khóa `repeatable` khi cần áp dụng nhiều lần:

```graphql
directive @tag(name: String!) repeatable on OBJECT | FIELD_DEFINITION

type Product @tag(name: "catalog") @tag(name: "searchable") {
    name: String @tag(name: "display")
}
```

`repeatable` cho phép có nhiều lần xuất hiện của cùng directive tại một location. Nếu directive không khai báo `repeatable`, việc áp dụng nó nhiều lần tại cùng vị trí là lỗi xác thực schema hoặc document.

## 6. Xử lý directive tùy chỉnh trong Spring for GraphQL

Spring for GraphQL sử dụng GraphQL Java để xây dựng và thực thi schema. Với schema-first, có thể đăng ký cách xử lý directive thông qua `RuntimeWiringConfigurer` và `SchemaDirectiveWiring`.

Ví dụ, directive `@upperCase` biến giá trị chuỗi do data fetcher trả về thành chữ hoa:

```graphql
directive @upperCase on FIELD_DEFINITION

type Query {
    greeting: String @upperCase
}
```

Resolver thông thường:

```java
@Controller
class GreetingController {

    @QueryMapping
    String greeting() {
        return "hello graphql";
    }
}
```

Đăng ký directive khi cấu hình runtime wiring:

```java
@Configuration
class GraphQlDirectiveConfiguration {

    @Bean
    RuntimeWiringConfigurer directiveConfigurer() {
        return wiringBuilder -> wiringBuilder.directive(
            "upperCase",
            new UpperCaseDirectiveWiring()
        );
    }
}
```

Phần triển khai `SchemaDirectiveWiring` có thể bọc data fetcher hiện tại:

```java
class UpperCaseDirectiveWiring implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        GraphQLFieldDefinition field = environment.getElement();
        DataFetcher<?> originalFetcher = environment.getCodeRegistry()
            .getDataFetcher(environment.getFieldsContainer(), field);

        DataFetcher<?> upperCaseFetcher = DataFetcherFactories.wrapDataFetcher(
            originalFetcher,
            (dataFetchingEnvironment, value) -> {
                if (value instanceof String) {
                    return ((String) value).toUpperCase(Locale.ROOT);
                }
                return value;
            }
        );

        environment.getCodeRegistry().dataFetcher(
            environment.getFieldsContainer(), field, upperCaseFetcher);
        return field;
    }
}
```

Ví dụ tập trung vào ý tưởng bọc data fetcher: directive đọc được từ schema, lấy data fetcher hiện tại, rồi thêm bước xử lý kết quả trước khi GraphQL trả dữ liệu. Các import được lược bỏ để tập trung vào phần chính; API chi tiết có thể thay đổi theo phiên bản GraphQL Java mà Spring for GraphQL quản lý. Hãy dùng đúng phiên bản dependency của dự án khi triển khai.

Một số lưu ý khi áp dụng:

1. Tên truyền vào `wiringBuilder.directive("upperCase", ...)` phải khớp tên directive trong SDL, không có ký tự `@`.
2. Chỉ bọc data fetcher tại location mà directive được khai báo và có xử lý tương ứng.
3. Bảo toàn hành vi của data fetcher gốc, bao gồm exception và kiểu trả về bất đồng bộ.
4. Nếu directive có argument, đọc giá trị argument từ directive trong `SchemaDirectiveWiringEnvironment` và xác thực cấu hình trước khi tạo wrapper.
5. Không đăng ký directive tùy chỉnh cho các directive tích hợp sẵn như `@include` hoặc `@skip`; GraphQL Java đã xử lý chúng.

## 7. Directive và bảo mật

Một directive như `@requiresRole(role: ADMIN)` có thể làm schema dễ đọc và thể hiện ý định bảo mật ngay cạnh field:

```graphql
directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicCatalog: [Product!]!
    adminReport: Report @requiresRole(role: ADMIN)
}
```

Tuy nhiên, khai báo directive không tự kiểm tra quyền truy cập. Nếu ứng dụng chỉ thêm `@requiresRole` vào SDL mà không đăng ký cơ chế thực thi, người dùng vẫn có thể gọi field theo hành vi resolver hiện tại.

Trong ứng dụng Spring, có thể thực thi quyền ở lớp resolver bằng Spring Security, ví dụ. Đoạn mã giả định method security đã được bật bằng `@EnableMethodSecurity` và `ReportService` đã được inject vào controller:

```java
@Controller
class ReportController {

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    Report adminReport() {
        return reportService.loadReport();
    }
}
```

Nếu muốn directive là nguồn metadata để áp dụng policy tập trung, cần viết `SchemaDirectiveWiring` hoặc cơ chế tương đương để nối metadata với kiểm tra quyền thực tế. Khi làm vậy, cần kiểm tra cả nested field, mutation và subscription; không để một đường truy cập khác bỏ qua policy. Cũng cần xác định rõ principal và quyền được lấy từ Spring Security context hay `GraphQLContext`.

Với ứng dụng có nhiều quy tắc bảo mật, Spring Security method security hoặc một lớp authorization chuyên biệt thường dễ kiểm thử và audit. Directive có thể bổ sung metadata cho schema, nhưng không nên được xem là cơ chế bảo vệ chỉ vì nó xuất hiện trong SDL.

## 8. Phân biệt directive với argument và annotation Java

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| GraphQL argument | Giá trị client truyền khi gọi field | `product(id: ID!)` |
| GraphQL directive | Chỉ dẫn hoặc metadata gắn vào schema/operation | `email @deprecated` hoặc `field @include(if: $show)` |
| Annotation Java | Metadata/hành vi ở mã nguồn Java, do framework hoặc ứng dụng xử lý | `@QueryMapping`, `@SchemaMapping`, `@PreAuthorize` |

`@SchemaMapping` là annotation của Spring for GraphQL để ánh xạ phương thức Java với một field trong schema. Nó không phải GraphQL directive và không được khai báo trong SDL. Ngược lại, directive `@deprecated` hoặc directive tùy chỉnh được khai báo và áp dụng trong GraphQL SDL.

## 9. Kiểm thử directive

Kiểm thử cần phản ánh đúng vai trò của từng loại directive:

- Với `@include` và `@skip`, gửi operation với cả giá trị biến `true` và `false`, xác minh field có hoặc không xuất hiện trong `data` theo điều kiện.
- Với `@deprecated`, kiểm tra metadata qua schema introspection và xác minh field cũ vẫn hoạt động trong giai đoạn tương thích nếu đó là chính sách của API.
- Với `@specifiedBy`, xác minh scalar được công bố URL đặc tả và parser/serializer của scalar xử lý đúng dữ liệu.
- Với directive tùy chỉnh như `@upperCase`, gửi query đến field được đánh dấu và xác minh data fetcher wrapper tạo ra kết quả mong đợi.
- Với directive mô tả quyền, kiểm tra cả người dùng đủ quyền và không đủ quyền. Đồng thời xác minh resolver không bị gọi khi request bị từ chối.

`GraphQlTester` có thể gửi GraphQL document, truyền variables và kiểm tra response. Khi kiểm thử schema directive hoặc metadata, có thể dùng introspection hoặc kiểm tra trực tiếp schema được cấu hình trong test context. Không nên chỉ kiểm tra rằng SDL có dòng `@requiresRole`; cần kiểm tra hành vi thực tế của lớp thực thi policy.

## 10. Lỗi thường gặp

**Dùng sai location.** Ví dụ khai báo directive chỉ dành cho `FIELD_DEFINITION` nhưng lại áp dụng lên `FIELD` trong query. Hãy kiểm tra location trong định nghĩa directive và nơi sử dụng.

**Quên định nghĩa directive tùy chỉnh.** Một directive chưa được GraphQL biết đến có thể khiến schema không hợp lệ. Hãy khai báo directive trong SDL hoặc cung cấp qua cơ chế schema phù hợp trước khi áp dụng.

**Cho rằng directive tùy chỉnh tự chạy.** SDL chỉ mô tả directive. Ứng dụng cần đăng ký `SchemaDirectiveWiring`, instrumentation hoặc cơ chế đọc metadata phù hợp.

**Đặt tên directive trùng với directive tích hợp sẵn.** Không định nghĩa lại `@skip`, `@include`, `@deprecated` hay `@specifiedBy` theo hành vi riêng của ứng dụng.

**Dùng directive như lớp bảo mật duy nhất.** Metadata không tự ngăn request. Phải có kiểm tra authorization thực sự và kiểm thử các đường truy cập.

**Không kiểm tra tương thích phiên bản.** Một số location hoặc API của GraphQL Java có thể khác nhau theo phiên bản. Kiểm tra dependency mà Spring Boot quản lý trước khi dùng tính năng mới.

## Kết luận

Directive mở rộng khả năng mô tả GraphQL bằng cách gắn chỉ dẫn và metadata vào schema hoặc operation. Directive tích hợp như `@include`, `@skip`, `@deprecated` và `@specifiedBy` có hành vi được GraphQL hỗ trợ sẵn. Directive tùy chỉnh cần định nghĩa location, argument và đăng ký cách xử lý trong ứng dụng. Khi dùng cùng Spring for GraphQL, hãy phân biệt rõ metadata trong SDL với hành vi thực tế của data fetcher, resolver và lớp bảo mật.
