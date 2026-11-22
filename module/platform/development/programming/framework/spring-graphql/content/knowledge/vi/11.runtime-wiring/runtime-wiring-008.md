# Directive wiring

Directive là một thành phần của GraphQL dùng để bổ sung chỉ dẫn hoặc metadata cho schema và operation. Một directive có tên bắt đầu bằng ký tự **@**, có thể nhận argument và chỉ được đặt tại những vị trí mà nó cho phép. Ví dụ, **@deprecated** đánh dấu field đã lỗi thời; **@skip** và **@include** điều khiển việc đưa field vào response theo điều kiện.

Với directive tùy chỉnh, việc khai báo trong SDL mới chỉ mô tả tên, argument và vị trí sử dụng. Muốn directive tạo ra hành vi khi server thực thi, ứng dụng cần nối nó với runtime wiring. Trong Spring for GraphQL, có thể đăng ký logic đó thông qua **RuntimeWiringConfigurer** và **SchemaDirectiveWiring** của GraphQL Java.

Bài này tập trung vào cách khai báo directive, phân biệt directive tích hợp và directive tùy chỉnh, hiểu vị trí áp dụng, triển khai schema directive bằng **SchemaDirectiveWiring**, tích hợp vào Spring Boot, và kiểm thử hành vi sau khi wiring.

## 1. Directive là gì?

Directive là một chỉ dẫn được gắn vào một thành phần GraphQL. Cú pháp tổng quát:

~~~graphql
@directiveName
~~~

Directive có thể nhận argument:

~~~graphql
@directiveName(argument: value)
~~~

Ví dụ, GraphQL có directive chuẩn **@deprecated**:

~~~graphql
type Book {
  id: ID!
  title: String!
  legacyCode: String @deprecated(reason: "Sử dụng id")
}
~~~

Directive **@deprecated** gắn metadata vào field **legacyCode**, cho biết client nên chuyển sang field khác. Công cụ introspection và IDE có thể hiển thị lý do deprecated để hỗ trợ quá trình chuyển đổi.

Directive có thể được dùng ở hai nhóm vị trí:

- **Schema locations:** gắn vào schema definition, object type, field definition, argument definition, enum value, scalar, input object hoặc các thành phần schema khác.
- **Executable locations:** gắn vào operation, field selection, fragment, variable definition và các thành phần của GraphQL document được gửi từ client.

Hai nhóm vị trí có vòng đời khác nhau. Directive trên schema thường được xử lý khi xây dựng schema hoặc được đọc như metadata. Directive trên operation được xử lý trong quá trình parse/validation/execution của operation.

## 2. Định nghĩa custom directive trong SDL

Muốn khai báo directive tùy chỉnh, dùng từ khóa **directive**:

~~~graphql
directive @uppercase on FIELD_DEFINITION
~~~

Khai báo này tạo directive tên **uppercase**, chỉ được gắn vào field definition trong schema.

Có thể sử dụng directive trên field:

~~~graphql
type Book {
  id: ID!
  title: String! @uppercase
}
~~~

Directive có thể nhận argument:

~~~graphql
directive @format(pattern: String!) on FIELD_DEFINITION

type Book {
  publishedAt: String @format(pattern: "yyyy-MM-dd")
}
~~~

Argument của directive cũng có kiểu GraphQL. Có thể dùng scalar, enum hoặc input type hợp lệ tùy vị trí và quy tắc của directive.

### Chọn directive location

Sau từ khóa **on**, khai báo những vị trí mà directive được phép sử dụng. Một directive có thể hỗ trợ nhiều location, phân cách bằng dấu **|**:

~~~graphql
directive @audit on FIELD_DEFINITION | OBJECT
~~~

Một số schema locations thường gặp:

| Location | Vị trí áp dụng |
|---|---|
| **SCHEMA** | Schema definition |
| **SCALAR** | Scalar type |
| **OBJECT** | Object type |
| **FIELD_DEFINITION** | Field của object hoặc interface |
| **ARGUMENT_DEFINITION** | Argument của field hoặc directive |
| **INTERFACE** | Interface type |
| **UNION** | Union type |
| **ENUM** | Enum type |
| **ENUM_VALUE** | Enum value |
| **INPUT_OBJECT** | Input object |
| **INPUT_FIELD_DEFINITION** | Field của input object |

Executable locations gồm **QUERY**, **MUTATION**, **SUBSCRIPTION**, **FIELD**, **FRAGMENT_DEFINITION**, **FRAGMENT_SPREAD**, **INLINE_FRAGMENT** và **VARIABLE_DEFINITION**.

Nếu directive cần được áp dụng nhiều lần trên cùng một vị trí, khai báo **repeatable**:

~~~graphql
directive @tag(name: String!) repeatable on FIELD_DEFINITION

type Book {
  title: String! @tag(name: "searchable") @tag(name: "display")
}
~~~

Nếu không có từ khóa **repeatable**, directive không được lặp lại nhiều lần trên cùng một vị trí.

## 3. Built-in directive và custom directive

GraphQL đã định nghĩa một số directive chuẩn. Những directive này được GraphQL engine hiểu theo ý nghĩa đã quy định:

| Directive | Location tiêu biểu | Mục đích |
|---|---|---|
| **@skip(if: Boolean!)** | FIELD, fragment | Bỏ qua selection khi điều kiện đúng |
| **@include(if: Boolean!)** | FIELD, fragment | Chỉ đưa selection vào khi điều kiện đúng |
| **@deprecated(reason: String)** | FIELD_DEFINITION, ENUM_VALUE | Đánh dấu thành phần schema đã lỗi thời |
| **@specifiedBy(url: String!)** | SCALAR | Liên kết scalar với tài liệu đặc tả |

Ví dụ directive thực thi trên operation:

~~~graphql
query BookDetails($showDescription: Boolean!) {
  book(id: "book-01") {
    id
    title
    description @include(if: $showDescription)
  }
}
~~~

Nếu biến **showDescription** là false, field **description** bị bỏ qua trong response. Client có thể điều khiển selection set mà không cần tạo hai query khác nhau.

Ví dụ directive metadata trên schema:

~~~graphql
type Book {
  id: ID!
  oldTitle: String @deprecated(reason: "Sử dụng title")
  title: String!
}
~~~

Custom directive có thể mô tả metadata hoặc tạo hành vi riêng, ví dụ chuyển chữ hoa, ghi audit, định dạng giá trị hay áp dụng một policy nhất định. GraphQL không tự suy ra hành vi cho directive tùy chỉnh chỉ từ tên của nó.

### Khai báo directive không đồng nghĩa với thực thi

Ví dụ:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  title: String! @uppercase
}
~~~

SDL trên chỉ cho biết **@uppercase** tồn tại và được dùng trên field. Nếu server không đăng ký logic xử lý directive, giá trị **title** không tự động chuyển thành chữ hoa.

Đây là ranh giới quan trọng:

- **SDL definition:** định nghĩa tên, argument, repeatability và location.
- **Applied directive:** nơi directive được gắn vào một type hoặc field.
- **Runtime wiring:** logic mà server dùng để áp dụng hành vi của directive.

## 4. SchemaDirectiveWiring trong GraphQL Java

GraphQL Java cung cấp interface **SchemaDirectiveWiring** để xử lý directive gắn trên schema element. Khi schema được xây dựng, GraphQL Java gọi callback tương ứng với loại element được directive áp dụng.

Một số callback thường gặp:

| Callback | Schema element |
|---|---|
| **onField** | GraphQLFieldDefinition |
| **onArgument** | GraphQLArgument |
| **onObject** | GraphQLObjectType |
| **onInterface** | GraphQLInterfaceType |
| **onUnion** | GraphQLUnionType |
| **onEnum** | GraphQLEnumType |
| **onEnumValue** | GraphQLEnumValueDefinition |
| **onScalar** | GraphQLScalarType |
| **onInputObjectType** | GraphQLInputObjectType |
| **onInputObjectField** | GraphQLInputObjectField |

Với directive trên field, callback **onField** thường được dùng để đọc metadata và điều chỉnh data fetcher của field. Có thể bọc data fetcher hiện tại để bổ sung hành vi trước hoặc sau khi giá trị được lấy.

Điểm cần nhớ: **SchemaDirectiveWiring** thường được áp dụng trong quá trình xây dựng schema. Nó không phải một resolver thay thế cho toàn bộ field và cũng không tự chạy như một interceptor HTTP cho mọi request.

## 5. Ví dụ: directive chuyển giá trị String thành chữ hoa

Giả sử muốn khai báo directive **@uppercase** để chuyển giá trị String trả về của field thành chữ hoa.

SDL:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  id: ID!
  title: String! @uppercase
}

type Query {
  book(id: ID!): Book
}
~~~

Resolver hiện tại trả về một Book có title là **Spring GraphQL**. Directive sẽ bọc data fetcher của field **Book.title** và chuyển giá trị sau khi fetch.

Triển khai:

~~~java
import graphql.schema.DataFetcher;
import graphql.schema.DataFetcherFactories;
import graphql.schema.GraphQLFieldDefinition;
import graphql.schema.idl.SchemaDirectiveWiring;
import graphql.schema.idl.SchemaDirectiveWiringEnvironment;

import java.util.Locale;

public class UppercaseDirective implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        GraphQLFieldDefinition field = environment.getElement();

        DataFetcher<?> originalDataFetcher =
                environment.getCodeRegistry().getDataFetcher(
                        environment.getFieldsContainer(), field);

        DataFetcher<?> wrappedDataFetcher =
                DataFetcherFactories.wrapDataFetcher(
                        originalDataFetcher,
                        (dataFetchingEnvironment, value) -> {
                            if (value instanceof String text) {
                                return text.toUpperCase(Locale.ROOT);
                            }
                            return value;
                        });

        environment.getCodeRegistry().dataFetcher(
                environment.getFieldsContainer(),
                field,
                wrappedDataFetcher);

        return field;
    }
}
~~~

Directive lấy data fetcher hiện tại từ code registry, bọc nó bằng **DataFetcherFactories.wrapDataFetcher**, sau đó đăng ký lại data fetcher đã bọc cho field. Giá trị được chuyển đổi sau khi data fetcher gốc trả về.

**Locale.ROOT** được dùng để chuyển chữ hoa theo quy tắc locale ổn định, tránh kết quả phụ thuộc ngôn ngữ của máy chủ. Ví dụ này giả định field được đánh dấu directive trả về String; trong ứng dụng thực tế nên xác định rõ kiểu dữ liệu được hỗ trợ và không áp dụng directive cho field không tương thích.

Nếu field có data fetcher riêng do **@SchemaMapping** hoặc **@QueryMapping** cung cấp, wiring cần bọc data fetcher đã đăng ký cho field đó. Cần kiểm tra cấu hình runtime để bảo đảm directive được áp dụng sau khi data fetcher gốc đã được xác định.

## 6. Đăng ký directive qua RuntimeWiringConfigurer

Trong Spring for GraphQL, có thể đăng ký custom schema directive thông qua bean **RuntimeWiringConfigurer**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlDirectiveConfiguration {

    @Bean
    RuntimeWiringConfigurer directiveWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.directive(
                        "uppercase",
                        new UppercaseDirective());
    }
}
~~~

Tên **uppercase** phải khớp với tên directive được khai báo trong SDL. Spring Boot thu thập các **RuntimeWiringConfigurer** và áp dụng chúng khi xây dựng runtime wiring cho GraphQL schema.

Khi ứng dụng khởi động:

1. Spring Boot tìm các SDL resource theo cấu hình schema locations.
2. SDL được phân tích thành các định nghĩa schema.
3. Spring Boot áp dụng các bean **RuntimeWiringConfigurer**, bao gồm đăng ký directive wiring.
4. GraphQL Java xây dựng executable schema và gọi **SchemaDirectiveWiring** trên schema element có directive tương ứng.
5. Schema hoàn chỉnh được sử dụng để thực thi operation.

Nếu directive được khai báo nhưng chưa đăng ký wiring, schema vẫn có thể được parse như metadata tùy cấu hình engine, nhưng hành vi tùy chỉnh sẽ không xuất hiện. Hãy kiểm thử cả việc khởi động schema lẫn kết quả thực thi.

## 7. Directive có argument

Directive có thể nhận argument để điều chỉnh hành vi. Ví dụ directive định dạng:

~~~graphql
directive @formatDate(pattern: String! = "yyyy-MM-dd") on FIELD_DEFINITION

type Book {
  publishedAt: String @formatDate(pattern: "dd/MM/yyyy")
}
~~~

Argument **pattern** là metadata cấu hình cho field. Khi triển khai wiring, có thể đọc applied directive trên schema element và lấy giá trị argument tương ứng để cấu hình formatter.

Với GraphQL Java, các API để đọc directive argument có thể khác nhau giữa directive representation cũ và applied directive API ở các phiên bản. Khi triển khai thực tế, nên dùng API phù hợp với phiên bản GraphQL Java mà Spring Boot quản lý, ưu tiên applied directive representation hiện hành. Không nên sao chép một đoạn code đọc directive argument từ phiên bản khác mà chưa kiểm tra dependency.

Hãy xác định trước:

- Argument nào bắt buộc và argument nào có default.
- Giá trị có cần validate khi schema được xây dựng không.
- Directive có thể được lặp lại không.
- Nếu argument sai, ứng dụng nên fail startup hay báo lỗi runtime.
- Directive tác động lên schema metadata hay thay đổi giá trị lúc execution.

Nếu directive cấu hình formatter, regex hoặc policy, nên validate cấu hình một lần khi schema được xây dựng để tránh phát hiện lỗi lặp đi lặp lại trên từng request.

## 8. Directive trên object, argument và input field

Directive không chỉ áp dụng cho output field. Tùy location đã khai báo, có thể gắn directive vào object, argument hoặc input field.

Ví dụ:

~~~graphql
directive @sensitive on FIELD_DEFINITION
directive @requiredInput on INPUT_FIELD_DEFINITION
directive @audit on OBJECT

type Customer @audit {
  id: ID!
  email: String! @sensitive
}

input CreateCustomerInput {
  email: String! @requiredInput
}
~~~

Các directive trên mô tả metadata về audit, độ nhạy cảm và yêu cầu của input. Tuy nhiên, tên directive không tự tạo ra cơ chế audit, che giấu dữ liệu hoặc validation. Runtime wiring hoặc một thành phần khác của ứng dụng phải đọc metadata và thực thi chính sách tương ứng.

Với directive trên input field, callback **onInputObjectField** có thể được dùng để kiểm tra hoặc điều chỉnh schema element khi xây dựng schema. Nhưng kiểm tra giá trị đầu vào thực tế thường cần được thực hiện bằng GraphQL coercion, custom scalar, Bean Validation hoặc logic của ứng dụng.

Không nên xem directive metadata là một lớp bảo mật tự động. Nếu field **email** nhạy cảm, server vẫn phải kiểm tra quyền đọc field đó ở runtime.

## 9. Directive cho authorization: thiết kế có chủ đích

Có thể thiết kế directive để mô tả yêu cầu role:

~~~graphql
directive @requiresRole(role: String!) on FIELD_DEFINITION

type Query {
  adminReport: AdminReport @requiresRole(role: "ADMIN")
}
~~~

Directive này giúp policy được thể hiện ngay trong schema. Tuy nhiên, để thực sự bảo vệ field, runtime wiring phải kết hợp với authentication context và kiểm tra quyền đáng tin cậy.

Một hướng triển khai là bọc data fetcher:

1. Lấy principal hoặc authentication đã được xác thực từ GraphQL context.
2. Đọc role yêu cầu từ applied directive.
3. Kiểm tra principal có quyền phù hợp không.
4. Nếu không đủ quyền, trả lỗi authorization theo chính sách của ứng dụng.
5. Nếu đủ quyền, gọi data fetcher gốc.

Không lấy role từ argument do client tự gửi. Quyền phải được suy ra từ principal đã xác thực ở server. Ngoài ra, một directive authorization tùy chỉnh không thay thế Spring Security; cần cân nhắc method security, kiểm tra quyền trong service và bảo vệ mọi đường truy cập tới cùng nghiệp vụ.

Với hệ thống cần phân quyền phức tạp theo tenant, owner hoặc resource, service layer thường là nơi phù hợp để thực thi quy tắc cuối cùng. Directive có thể đóng vai trò metadata hoặc lớp tích hợp, nhưng không nên là nơi duy nhất bảo vệ dữ liệu.

## 10. Schema directive và executable directive khác nhau

Một nhầm lẫn phổ biến là cho rằng mọi directive đều được xử lý bằng **SchemaDirectiveWiring**. Trên thực tế:

| Loại | Ví dụ | Thời điểm xử lý |
|---|---|---|
| Schema directive | **@uppercase**, **@requiresRole** trên field definition | Khi xây dựng schema hoặc khi runtime đọc metadata |
| Executable directive | **@skip**, **@include** trên field trong query | Khi xử lý GraphQL operation |

**SchemaDirectiveWiring** xử lý directive gắn trên schema element. Với directive gắn trong operation, cần dùng cơ chế thực thi hoặc extension point phù hợp của GraphQL Java, chẳng hạn instrumentation hoặc logic xử lý operation. Không nên kỳ vọng **SchemaDirectiveWiring** tự được gọi cho mọi directive mà client gửi trong query.

Ví dụ:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  title: String! @uppercase
}
~~~

Đây là schema directive.

Trong query:

~~~graphql
query {
  book(id: "book-01") {
    title @skip(if: false)
  }
}
~~~

**@skip** là executable directive trên field selection. Nó được GraphQL engine xử lý theo semantics chuẩn.

## 11. Directive và các cơ chế khác trong Spring for GraphQL

Không phải mọi yêu cầu đều cần custom directive. Hãy chọn extension point theo trách nhiệm:

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Đánh dấu field cũ | **@deprecated** |
| Bỏ qua hoặc bao gồm field trong operation | **@skip**, **@include** |
| Bổ sung metadata hoặc hành vi cho schema element | **SchemaDirectiveWiring** |
| Lấy dữ liệu cho field | **@SchemaMapping**, **@QueryMapping**, DataFetcher |
| Xác định object type cho interface/union | **TypeResolver** |
| Chuyển đổi scalar | Custom **GraphQLScalarType** và coercing |
| Xử lý lỗi resolver | **DataFetcherExceptionResolver** hoặc **@GraphQlExceptionHandler** |
| Đo lường execution | GraphQL Java Instrumentation |
| Phân quyền nghiệp vụ | Spring Security và service authorization |

Directive phù hợp khi hành vi hoặc metadata có thể được gắn khai báo vào schema element. Nếu logic chỉ là truy vấn dữ liệu, nên dùng resolver. Nếu logic là authorization phức tạp, cần bảo đảm service layer vẫn thực thi chính sách dù request đến từ GraphQL hay một adapter khác.

## 12. Kiểm thử directive wiring

Kiểm thử cần xác nhận directive thực sự ảnh hưởng đến schema hoặc response. Chỉ kiểm tra SDL có chứa tên directive là chưa đủ.

Ví dụ với directive **@uppercase**, giả sử resolver trả về title gốc là **Spring GraphQL**. Test có thể kiểm tra giá trị cuối cùng:

~~~java
@SpringBootTest
class UppercaseDirectiveTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldApplyUppercaseDirective() {
        graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        title
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("SPRING GRAPHQL");
    }
}
~~~

Ngoài test response, nên kiểm tra:

1. Ứng dụng khởi động khi directive được khai báo và wiring đã đăng ký.
2. Directive chỉ được phép xuất hiện tại location đã khai báo.
3. Field không gắn directive vẫn giữ nguyên hành vi.
4. Data fetcher gốc vẫn được gọi đúng và lỗi được truyền theo quy tắc GraphQL.
5. Giá trị null hoặc kiểu trả về không phải String được xử lý có chủ đích.
6. Directive có argument nhận đúng giá trị và default.
7. Directive repeatable được xử lý theo đúng semantics đã thiết kế.
8. Authorization directive từ chối principal không đủ quyền và cho phép principal hợp lệ.
9. Directive trên input field hoặc object không bị nhầm với validation tự động.
10. Operation directive như **@skip** và **@include** vẫn hoạt động theo chuẩn GraphQL.

Nếu directive được dùng rộng rãi, nên có test riêng cho class **SchemaDirectiveWiring** và integration test với schema thực tế. Điều này giúp phát hiện lỗi tương thích khi nâng phiên bản GraphQL Java hoặc Spring Boot.

## 13. Những lỗi thường gặp khi wiring directive

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Directive có trong SDL nhưng không có tác dụng | Chưa đăng ký SchemaDirectiveWiring | Đăng ký qua RuntimeWiringConfigurer |
| Directive bị báo sai location | Location trong định nghĩa không bao gồm nơi áp dụng | Sửa location hoặc chuyển directive |
| Tên directive không khớp | Tên trong SDL khác tên đăng ký runtime | Dùng cùng tên ở hai nơi |
| Field trả về giá trị chưa biến đổi | Wrapper chưa được gắn vào data fetcher thực tế | Kiểm tra code registry và thứ tự wiring |
| Resolver gốc không được gọi | Wiring thay thế data fetcher thay vì wrap | Lấy và bọc data fetcher hiện tại |
| Directive authorization không bảo vệ dữ liệu | Chỉ có metadata, không có runtime check | Thực thi policy tại server và service |
| Dùng SchemaDirectiveWiring cho @skip/@include | Nhầm schema directive với executable directive | Dùng semantics operation chuẩn |
| Directive argument sai định dạng | Chưa validate applied directive argument | Validate khi xây dựng schema |
| Nâng phiên bản làm code wiring lỗi | API GraphQL Java thay đổi | Đối chiếu API theo dependency được quản lý |

## 14. Quy trình thêm custom directive

Khi cần thêm directive cho Spring for GraphQL, hãy thực hiện:

1. Xác định directive chỉ là metadata hay phải tạo hành vi runtime.
2. Chọn schema location hoặc executable location phù hợp.
3. Khai báo directive definition trong SDL, bao gồm argument, default và repeatable nếu cần.
4. Gắn directive vào đúng type, field hoặc thành phần schema.
5. Viết **SchemaDirectiveWiring** nếu đó là schema directive cần runtime behavior.
6. Đăng ký wiring qua **RuntimeWiringConfigurer**.
7. Giữ data fetcher gốc và wrap nó nếu chỉ cần bổ sung hành vi.
8. Xác thực directive argument khi schema được xây dựng.
9. Kiểm tra authorization và dữ liệu nhạy cảm ở server/service layer.
10. Viết unit/integration test để xác nhận hành vi thực tế.

Directive giúp đưa metadata và một số chính sách khai báo vào gần định nghĩa schema. Trong Spring for GraphQL, SDL định nghĩa directive và location; **SchemaDirectiveWiring** triển khai hành vi trên schema element; **RuntimeWiringConfigurer** kết nối wiring đó với GraphQL runtime. Khi phân biệt rõ schema directive với executable directive và kiểm thử hành vi sau wiring, directive trở thành một extension point hữu ích mà không làm mờ trách nhiệm của resolver, service và Spring Security.
