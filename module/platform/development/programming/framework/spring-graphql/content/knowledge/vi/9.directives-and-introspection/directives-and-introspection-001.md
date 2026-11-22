# Directive là gì trong GraphQL?

Directive là một chỉ thị có tên, có thể nhận argument và được gắn vào những vị trí được GraphQL cho phép. Directive bổ sung ngữ nghĩa cho schema hoặc operation: nó có thể đánh dấu một field đã lỗi thời, mô tả chuẩn serialization của scalar, điều khiển việc chọn field trong một query hoặc kích hoạt logic tùy chỉnh ở server.

Trong GraphQL SDL, directive được nhận diện bằng ký hiệu `@`. GraphQL định nghĩa sẵn một số directive như `@include`, `@skip`, `@deprecated` và `@specifiedBy`. Ứng dụng cũng có thể khai báo directive riêng để mô tả quy tắc nghiệp vụ hoặc mở rộng cách schema hoạt động. Với Spring for GraphQL, custom schema directive thường được triển khai thông qua `RuntimeWiringConfigurer` và `SchemaDirectiveWiring` của GraphQL Java.

Sau bài này, bạn có thể:

- Giải thích directive là gì và nó khác field, argument hoặc resolver như thế nào.
- Phân biệt directive trên executable document với directive trên schema type system.
- Đọc cú pháp khai báo directive, argument, default value, `repeatable` và location.
- Sử dụng các directive chuẩn `@include`, `@skip`, `@deprecated` và `@specifiedBy`.
- Khai báo custom directive trong SDL và hiểu vì sao khai báo chưa tự tạo hành vi.
- Đăng ký `SchemaDirectiveWiring` trong Spring for GraphQL.
- Nhận biết giới hạn bảo mật, kiểm thử và các lỗi thường gặp khi thiết kế directive.

## 1. Directive bổ sung ngữ nghĩa cho GraphQL

Một field trong schema cho biết dữ liệu nào client có thể yêu cầu. Một directive bổ sung thông tin hoặc chỉ thị cho một thành phần của schema hay operation. Ví dụ:

```graphql
type Book {
    id: ID!
    title: String!
    oldTitle: String @deprecated(reason: "Use title instead.")
}
```

`@deprecated` đánh dấu `oldTitle` không còn được khuyến nghị sử dụng. Field vẫn tồn tại trong schema và client cũ vẫn có thể truy vấn nó; công cụ tài liệu hoặc introspection có thể thông báo field này đã lỗi thời.

Một ví dụ khác nằm trong operation:

```graphql
query BookDetails($withAuthor: Boolean!) {
    book(id: "book-42") {
        title
        author @include(if: $withAuthor) {
            name
        }
    }
}
```

`@include` quyết định field `author` có được đưa vào lần thực thi này hay không, dựa trên biến `withAuthor`. Directive không phải một field mới và cũng không phải một resolver. Nó là một chỉ thị gắn vào vị trí được định nghĩa trong GraphQL.

Directive có thể phục vụ nhiều mục đích:

- **Metadata:** mô tả field đã deprecated hoặc custom scalar tuân theo đặc tả nào.
- **Điều khiển operation:** bao gồm hoặc bỏ qua field/fragment theo biến.
- **Runtime behavior:** thay đổi cách một schema field được thực thi, chẳng hạn định dạng giá trị hoặc áp dụng một chính sách đã được triển khai.
- **Quy ước và công cụ:** cung cấp metadata để code generation, validation hoặc tài liệu hóa xử lý.

Không phải directive nào cũng tự làm thay đổi kết quả chạy query. Hành vi phụ thuộc vào directive chuẩn do GraphQL thực thi hoặc phần triển khai custom directive mà ứng dụng đăng ký.

## 2. Hai nhóm vị trí sử dụng directive

GraphQL có hai nhóm vị trí directive quan trọng.

**Executable directive** được gắn vào operation, field, fragment hoặc variable definition trong GraphQL document. Chúng ảnh hưởng đến cách operation được kiểm tra hoặc thực thi. `@include` và `@skip` là hai ví dụ chuẩn.

```graphql
query FindBook($id: ID!, $showAuthor: Boolean!) {
    book(id: $id) {
        id
        title
        author @include(if: $showAuthor) {
            name
        }
    }
}
```

**Type-system directive** được gắn vào định nghĩa schema trong SDL, ví dụ object, field definition, enum value hoặc scalar. `@deprecated` và `@specifiedBy` là các ví dụ chuẩn.

```graphql
scalar DateTime @specifiedBy(url: "https://example.org/date-time-format")

type Book {
    id: ID!
    oldTitle: String @deprecated(reason: "Use title instead.")
    title: String!
}
```

Hai nhóm có thể cùng dùng cú pháp `@name`, nhưng được xử lý ở các giai đoạn khác nhau. `SchemaDirectiveWiring` của GraphQL Java được thiết kế để xử lý directive được gắn trên các thành phần SDL của schema. Nó không tự động triển khai custom directive xuất hiện trong executable document.

## 3. Cú pháp khai báo directive

Directive riêng được khai báo bằng từ khóa `directive`, theo sau là tên directive, danh sách argument tùy chọn và các location được phép sử dụng:

```graphql
directive @uppercase on FIELD_DEFINITION
```

Khai báo trên tạo directive tên `uppercase`, chỉ được gắn vào vị trí định nghĩa field trong schema. Có thể dùng nó như sau:

```graphql
type Book {
    title: String! @uppercase
}
```

Directive có thể nhận argument:

```graphql
directive @formatDate(pattern: String = "yyyy-MM-dd") on FIELD_DEFINITION

type AuditEvent {
    occurredAt: String! @formatDate(pattern: "dd/MM/yyyy")
}
```

`pattern` là argument của directive và có default value nếu không được truyền. Directive argument dùng các kiểu input của GraphQL như scalar, enum, list hoặc input object; không dùng output object type.

Directive cũng có thể được khai báo là `repeatable` nếu muốn cho phép gắn nhiều lần tại cùng một vị trí:

```graphql
directive @tag(name: String!) repeatable on FIELD_DEFINITION

type Book {
    title: String! @tag(name: "searchable") @tag(name: "public")
}
```

Nếu không có từ khóa `repeatable`, cùng một directive không được lặp lại nhiều lần tại cùng vị trí. `repeatable` chỉ cho phép lặp; ý nghĩa của nhiều lần áp dụng và cách kết hợp argument vẫn do phần triển khai directive xác định.

## 4. Directive location

Phần `on` trong khai báo xác định directive có thể được đặt ở đâu. Tên location là các giá trị phân biệt chữ hoa/chữ thường. Các location thường gặp gồm:

| Nhóm | Location | Vị trí áp dụng |
| --- | --- | --- |
| Executable | `QUERY` | Operation query |
| Executable | `MUTATION` | Operation mutation |
| Executable | `SUBSCRIPTION` | Operation subscription |
| Executable | `FIELD` | Field trong operation |
| Executable | `FRAGMENT_DEFINITION` | Định nghĩa named fragment |
| Executable | `FRAGMENT_SPREAD` | Nơi spread named fragment |
| Executable | `INLINE_FRAGMENT` | Inline fragment |
| Executable | `VARIABLE_DEFINITION` | Khai báo variable trong operation |
| Type system | `SCHEMA` | Định nghĩa schema |
| Type system | `SCALAR` | Định nghĩa scalar |
| Type system | `OBJECT` | Định nghĩa object type |
| Type system | `FIELD_DEFINITION` | Field của object hoặc interface |
| Type system | `ARGUMENT_DEFINITION` | Argument của field hoặc directive |
| Type system | `INTERFACE` | Định nghĩa interface |
| Type system | `UNION` | Định nghĩa union |
| Type system | `ENUM` | Định nghĩa enum |
| Type system | `ENUM_VALUE` | Một enum value |
| Type system | `INPUT_OBJECT` | Định nghĩa input object |
| Type system | `INPUT_FIELD_DEFINITION` | Field của input object |

Ví dụ directive cho phép dùng ở object và field:

```graphql
directive @requiresAuthentication on OBJECT | FIELD_DEFINITION
```

Khai báo location không tự áp dụng directive cho mọi object hoặc field. Nó chỉ quy định vị trí hợp lệ khi directive được sử dụng. Nếu client hoặc schema đặt directive ở vị trí không được cho phép, schema/document sẽ không hợp lệ.

## 5. Các directive chuẩn thường gặp

GraphQL định nghĩa một số directive chuẩn. Các directive này đã có ý nghĩa trong GraphQL runtime; ứng dụng không cần tự viết `SchemaDirectiveWiring` để chúng hoạt động.

### `@include`

`@include(if: Boolean!)` chỉ đưa field hoặc fragment vào lần thực thi khi argument `if` là `true`:

```graphql
query Book($id: ID!, $withReviews: Boolean!) {
    book(id: $id) {
        title
        reviews @include(if: $withReviews) {
            rating
            comment
        }
    }
}
```

Nếu `$withReviews` là `false`, field `reviews` bị bỏ qua trong lần thực thi đó.

### `@skip`

`@skip(if: Boolean!)` bỏ qua field hoặc fragment khi `if` là `true`:

```graphql
query Book($id: ID!, $hideInternal: Boolean!) {
    book(id: $id) {
        title
        internalNotes @skip(if: $hideInternal)
    }
}
```

Nếu `$hideInternal` là `true`, field `internalNotes` không được chọn trong operation.

`@include` và `@skip` có thể dùng trên field, fragment spread và inline fragment. Nếu cùng một vị trí có cả hai directive, field chỉ được thực thi khi điều kiện include là true và điều kiện skip là false. Chúng không phải cơ chế authorization: client vẫn có thể tự gửi operation yêu cầu field nhạy cảm.

### `@deprecated`

`@deprecated` đánh dấu field hoặc enum value trong schema không còn được khuyến nghị:

```graphql
enum PaymentMethod {
    CARD
    BANK_TRANSFER
    CASH @deprecated(reason: "Use an electronic payment method.")
}

type Book {
    id: ID!
    authorName: String @deprecated(reason: "Use author { name } instead.")
    author: Author
}
```

Argument `reason` có default value nếu không truyền. Directive này cung cấp metadata cho introspection và công cụ phát triển; nó không tự động chặn query hoặc mutation sử dụng field/value đã deprecated. Nếu muốn ngừng hỗ trợ, cần có kế hoạch tương thích và triển khai chính sách loại bỏ phù hợp.

### `@specifiedBy`

`@specifiedBy(url: String!)` gắn URL đặc tả cho custom scalar:

```graphql
scalar DateTime @specifiedBy(url: "https://example.org/specs/date-time")
```

Directive giúp client và công cụ hiểu scalar tuân theo định dạng nào. Nó không tự parse, validate hoặc serialize giá trị `DateTime`; ứng dụng vẫn cần đăng ký custom scalar với coercing logic tương ứng.

## 6. Khai báo custom directive cho schema

Custom directive cho phép biểu diễn quy ước riêng của ứng dụng trong SDL. Ví dụ, schema muốn đánh dấu một field cần vai trò `ADMIN`:

```graphql
enum Role {
    USER
    EDITOR
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicBooks: [Book!]!
    moderationQueue: [Book!]! @requiresRole(role: ADMIN)
}
```

SDL mô tả rằng `moderationQueue` có directive `requiresRole` với argument `role` là `ADMIN`. Nhưng chỉ khai báo directive và gắn nó vào field không tự kiểm tra quyền. Nếu không có runtime wiring hoặc cơ chế khác đọc directive và áp dụng chính sách, annotation này chỉ là metadata.

Custom directive có thể dùng cho:

- Quy tắc authorization hoặc policy metadata.
- Định dạng, chuẩn hóa hoặc biến đổi giá trị field.
- Cache hint hoặc thông tin điều khiển cho gateway.
- Validation metadata, chẳng hạn giới hạn hoặc định dạng.
- Tích hợp công cụ sinh tài liệu hoặc code generation.

Chỉ nên tạo directive khi nó biểu đạt một quy tắc có ý nghĩa và có nơi thực thi hoặc tiêu thụ rõ ràng. Nếu directive chỉ làm schema khó đọc hơn mà không có consumer nào xử lý, nó không đem lại hành vi hữu ích.

## 7. Triển khai schema directive trong Spring for GraphQL

Spring for GraphQL dùng GraphQL Java để xây dựng executable schema. Có thể đăng ký custom directive bằng `RuntimeWiringConfigurer`; Spring Boot tự phát hiện bean này và đưa nó vào quá trình cấu hình `GraphQlSource`.

`SchemaDirectiveWiring` cung cấp callback cho các thành phần schema như object, field, argument, scalar, enum và input object. Khi directive được gắn vào một field, `onField` có thể đọc định nghĩa field và thay đổi runtime behavior, chẳng hạn bọc `DataFetcher` hiện tại.

Ví dụ, directive `@uppercase` chuyển chuỗi trả về thành chữ hoa.

SDL:

```graphql
directive @uppercase on FIELD_DEFINITION

type Query {
    greeting: String!
}
```

Java implementation:

```java
public class UppercaseDirective implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        GraphQLFieldDefinition field = environment.getElement();
        GraphQLFieldsContainer parentType = environment.getFieldsContainer();

        DataFetcher<?> originalFetcher = environment.getCodeRegistry()
                .getDataFetcher(parentType, field);

        DataFetcher<?> wrappedFetcher = DataFetcherFactories.wrapDataFetcher(
                originalFetcher,
                (dataFetchingEnvironment, value) -> {
                    if (value instanceof String text) {
                        return text.toUpperCase(Locale.ROOT);
                    }
                    return value;
                });

        FieldCoordinates coordinates = FieldCoordinates.coordinates(parentType, field);
        environment.getCodeRegistry().dataFetcher(coordinates, wrappedFetcher);

        return field;
    }
}
```

Đăng ký directive trong Spring configuration:

```java
@Configuration
public class GraphQlConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return builder -> builder.directive(
                "uppercase",
                new UppercaseDirective());
    }
}
```

Đặt directive trên field cần biến đổi:

```graphql
type Query {
    greeting: String! @uppercase
}
```

Resolver Spring tương ứng có thể rất đơn giản:

```java
@Controller
public class GreetingController {

    @QueryMapping
    public String greeting() {
        return "hello graphql";
    }
}
```

Nếu resolver trả về `"hello graphql"`, response field `greeting` sẽ là `"HELLO GRAPHQL"`. `DataFetcherFactories.wrapDataFetcher` giúp bọc data fetcher hiện tại và xử lý cả giá trị đồng bộ lẫn `CompletionStage` mà data fetcher trả về.

Ví dụ này minh họa custom behavior cho schema field. Trong ứng dụng thực tế, nên đặt logic biến đổi ở đúng lớp, kiểm tra kiểu trả về và tránh dùng directive để che giấu quy tắc nghiệp vụ phức tạp. Nếu có nhiều directive cùng bọc một field, cần xác định thứ tự và cách chúng kết hợp.

## 8. Đọc argument của custom directive

Directive argument có thể cấu hình hành vi cho từng field. Ví dụ `@dateFormat` nhận pattern:

```graphql
directive @dateFormat(pattern: String = "yyyy-MM-dd") on FIELD_DEFINITION

type AuditEvent {
    occurredAt: String! @dateFormat(pattern: "dd/MM/yyyy")
}
```

Trong `SchemaDirectiveWiring`, có thể đọc directive đã áp dụng trên schema element thông qua environment và dùng argument đó để cấu hình wrapper hoặc metadata runtime. GraphQL Java cung cấp các API applied directive tương ứng; tên API chi tiết có thể khác theo phiên bản GraphQL Java đang dùng.

Một directive như `@dateFormat` có thể làm một trong hai việc:

1. Chỉ cung cấp metadata cho một lớp khác đọc và sử dụng.
2. Thay đổi schema/runtime behavior bằng cách bọc hoặc thay data fetcher, thêm argument hoặc áp dụng một cơ chế xử lý khác.

Chỉ định nghĩa `pattern` trong SDL không tự định dạng ngày. Phần wiring phải đọc giá trị và áp dụng formatter; nếu không, response vẫn giữ cách serialize mặc định của field.

## 9. Schema directive và executable directive trong ứng dụng

Một điểm dễ nhầm là cùng cú pháp directive nhưng hai loại được xử lý ở hai nơi:

| Nội dung | Schema directive | Executable directive |
| --- | --- | --- |
| Được đặt ở đâu | SDL schema definition | Query, mutation, subscription, field hoặc fragment trong operation |
| Ví dụ | `@deprecated`, `@specifiedBy`, `@requiresRole` | `@include`, `@skip` |
| Mục tiêu | Bổ sung metadata hoặc thay đổi runtime schema | Điều khiển operation cụ thể của client |
| Cơ chế thường dùng | `SchemaDirectiveWiring`, `RuntimeWiringConfigurer` | GraphQL execution engine; custom behavior cần tích hợp vào pipeline thực thi |
| Có tự chạy khi chỉ khai báo không? | Custom directive cần implementation | Custom executable directive cần implementation; directive chuẩn được runtime hỗ trợ |

Không dùng `SchemaDirectiveWiring` để kỳ vọng xử lý một custom directive gắn trong query document. Callback này hoạt động trên các thành phần của schema SDL. Với custom executable directive, cần chọn cơ chế mở rộng phù hợp của GraphQL Java và kiểm tra khả năng tích hợp của phiên bản Spring for GraphQL đang dùng.

## 10. Directive và bảo mật

Directive có thể mô tả chính sách, nhưng một dòng SDL không phải ranh giới bảo mật. Ví dụ:

```graphql
directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    payrollRecords: [PayrollRecord!]! @requiresRole(role: ADMIN)
}
```

Nếu `@requiresRole` chưa được triển khai và nối với cơ chế xác thực/phân quyền, bất kỳ người dùng nào có thể gọi field đều có thể nhận dữ liệu theo các resolver hiện có. Ngay cả khi directive đã được wiring, cần bảo đảm kiểm tra quyền dựa trên principal và context của request, không dựa vào một giá trị do client tự gửi.

Một số nguyên tắc:

- Bảo vệ field hoặc service bằng Spring Security/method security hoặc cơ chế authorization tương đương.
- Kiểm tra quyền trên bản ghi cụ thể nếu quyền phụ thuộc owner, tenant hoặc quan hệ dữ liệu.
- Không coi `@include` hoặc `@skip` là cơ chế ẩn dữ liệu; client có thể bỏ directive và gửi field trực tiếp.
- Không để thông điệp lỗi tiết lộ thông tin nhạy cảm về policy hoặc dữ liệu nội bộ.
- Kiểm thử cả người dùng được phép và không được phép, bao gồm truy cập qua field lồng nhau.

Nếu directive được dùng làm nguồn metadata cho authorization, hãy bảo đảm mọi đường truy cập field đều được bảo vệ, kể cả resolver được gọi qua fragment, alias hoặc operation khác.

## 11. Khám phá directive bằng introspection

GraphQL introspection cho phép client khám phá các directive được định nghĩa trong schema thông qua `__schema.directives`. Ví dụ:

```graphql
query ListDirectives {
    __schema {
        directives {
            name
            description
            isRepeatable
            locations
            args {
                name
                description
                defaultValue
                type {
                    kind
                    name
                    ofType {
                        kind
                        name
                    }
                }
            }
        }
    }
}
```

Thông tin trả về giúp công cụ biết tên directive, mô tả, location hợp lệ, directive có repeatable hay không và các argument mà nó nhận. Đây là thông tin về định nghĩa directive trong schema. Không nên mặc định rằng introspection tiêu chuẩn sẽ liệt kê đầy đủ mọi nơi một custom directive đã được áp dụng; khả năng khám phá applied directive phụ thuộc phiên bản đặc tả, GraphQL Java và công cụ liên quan.

Với field hoặc enum value được đánh dấu deprecated, introspection có các thông tin như `isDeprecated` và `deprecationReason`. Một số danh sách introspection mặc định ẩn phần tử deprecated; có thể yêu cầu rõ bằng argument `includeDeprecated` khi truy vấn field hoặc enum value, tùy vị trí introspection hỗ trợ.

Trong Spring Boot, introspection thường được bật mặc định để hỗ trợ công cụ như GraphiQL. Có thể cấu hình chính sách introspection theo môi trường. Việc tắt introspection làm giảm khả năng khám phá schema công khai, nhưng không thay thế authorization cho các field dữ liệu.

## 12. Kiểm thử directive

Directive cần được kiểm tra ở cả hai lớp: schema có khai báo đúng directive và runtime có thực thi đúng behavior hay không.

Với directive `@uppercase`, có thể dùng `GraphQlTester` để gửi query:

```java
graphQlTester.document("""
        query {
            greeting
        }
        """)
    .execute()
    .path("greeting")
    .entity(String.class)
    .isEqualTo("HELLO GRAPHQL");
```

Các trường hợp nên kiểm thử:

1. Schema khởi tạo thành công khi directive được khai báo ở đúng location.
2. Schema bị từ chối nếu directive được đặt ở location không được phép.
3. Custom directive wiring được gọi trên đúng field có áp dụng directive.
4. Field không có directive vẫn giữ behavior mặc định.
5. Giá trị đồng bộ và bất đồng bộ được wrapper xử lý đúng.
6. Argument directive và default value được áp dụng chính xác.
7. Directive repeatable được xử lý theo thứ tự/quy tắc mà ứng dụng công bố.
8. Directive dùng cho authorization từ chối người dùng không có quyền.
9. `@include` và `@skip` hoạt động theo variables; chúng không thay đổi quyền truy cập.
10. Introspection trả về định nghĩa directive và deprecation metadata như mong đợi.

## 13. Những lỗi thường gặp

- **Nghĩ rằng khai báo directive tự tạo behavior:** SDL chỉ mô tả tên, argument và location; custom directive cần implementation.
- **Dùng sai location:** directive chỉ được đặt tại các vị trí liệt kê sau `on`.
- **Nhầm schema directive với executable directive:** `SchemaDirectiveWiring` xử lý directive gắn trong SDL, không tự xử lý custom directive trên operation document.
- **Dùng `@deprecated` để chặn field:** directive chỉ đánh dấu metadata, không từ chối request.
- **Dùng `@include` hoặc `@skip` để phân quyền:** client tự kiểm soát variables và có thể bỏ directive.
- **Quên xử lý async DataFetcher:** wrapper tự viết có thể làm mất cách xử lý `CompletionStage`; dùng helper phù hợp như `DataFetcherFactories.wrapDataFetcher`.
- **Không xác định thứ tự nhiều directive:** nhiều wrapper có thể ảnh hưởng lẫn nhau nếu không có quy tắc rõ ràng.
- **Lạm dụng directive cho mọi quy tắc:** logic nghiệp vụ phức tạp thường nên nằm trong service hoặc policy component chuyên trách.
- **Cho rằng introspection liệt kê mọi lần áp dụng directive:** introspection tiêu chuẩn chủ yếu cung cấp định nghĩa directive và metadata được hỗ trợ.

## 14. Quy trình thiết kế custom directive

Khi cần mở rộng GraphQL bằng directive, hãy thực hiện theo trình tự:

1. Xác định directive thuộc executable document hay schema type system.
2. Xác định mục tiêu là metadata hay thay đổi runtime behavior.
3. Khai báo tên, argument, default value, `repeatable` và location trong SDL.
4. Viết mô tả để người dùng schema hiểu ý nghĩa và giới hạn của directive.
5. Với schema directive, triển khai `SchemaDirectiveWiring` và đăng ký qua `RuntimeWiringConfigurer`.
6. Với executable directive tùy chỉnh, chọn cơ chế tích hợp vào execution pipeline phù hợp với GraphQL Java.
7. Kiểm tra tương tác với resolver, async result, lỗi, authorization và các directive khác.
8. Viết test cho schema validation, runtime behavior và introspection.
9. Tài liệu hóa tác động tương thích nếu thay đổi hoặc loại bỏ directive đã công bố.

Directive là cơ chế mở rộng có cấu trúc của GraphQL. Directive chuẩn cung cấp những hành vi và metadata phổ biến; custom directive cho phép ứng dụng diễn đạt thêm quy ước riêng. Trong Spring for GraphQL, hãy nối schema directive với `SchemaDirectiveWiring` qua runtime wiring, kiểm thử hành vi thật và giữ các quy tắc bảo mật ở server. Khi mỗi directive có mục đích và nơi thực thi rõ ràng, schema sẽ giàu ngữ nghĩa hơn mà vẫn dễ hiểu và dễ bảo trì.

## Tài liệu tham khảo

- [GraphQL Specification — Type System Directives](https://spec.graphql.org/October2021/#sec-Type-System.Directives)
- [GraphQL Specification — Executable Directives](https://spec.graphql.org/October2021/#sec-Directives)
- [Spring for GraphQL — Request Execution, RuntimeWiringConfigurer và Directives](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java — SDL Directives](https://graphql-java.com/documentation/directives/)
- [GraphQL Java — SchemaDirectiveWiring API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/idl/SchemaDirectiveWiring.html)
