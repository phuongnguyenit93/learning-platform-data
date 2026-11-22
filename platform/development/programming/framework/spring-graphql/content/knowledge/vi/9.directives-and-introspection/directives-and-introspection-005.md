# Custom schema directive

GraphQL schema mô tả kiểu dữ liệu, field và những operation mà client có thể gọi. Trong nhiều ứng dụng, chỉ mô tả kiểu dữ liệu là chưa đủ: một field có thể cần yêu cầu quyền truy cập, áp dụng quy tắc cache, đánh dấu dữ liệu nhạy cảm hoặc biến đổi giá trị trước khi trả về. **Directive** là cú pháp mở rộng của GraphQL để gắn thông tin hoặc hành vi vào schema và operation. Custom schema directive cho phép ứng dụng định nghĩa những quy tắc riêng ngay trong SDL.

Trong Spring for GraphQL, schema directive có thể được xử lý ở thời điểm xây dựng GraphQL runtime bằng GraphQL Java SchemaDirectiveWiring. Spring Boot nhận cấu hình thông qua bean RuntimeWiringConfigurer, nhờ đó directive có thể can thiệp vào field definition hoặc data fetcher tương ứng.

## Directive là gì?

Directive là một chỉ thị bắt đầu bằng ký tự @, theo sau là tên directive và có thể có các argument. Ví dụ, GraphQL đã định nghĩa directive @deprecated để đánh dấu field hoặc enum value không còn được khuyến nghị sử dụng:

~~~graphql
type Book {
  id: ID!
  title: String!
  oldTitle: String @deprecated(reason: "Use title instead")
}
~~~

Directive @deprecated cung cấp metadata cho schema và công cụ phát triển. GraphQL client có thể tra cứu thông tin này qua introspection để hiển thị cảnh báo khi sử dụng field cũ.

Một số directive dựng sẵn khác:

| Directive | Mục đích | Vị trí thường dùng |
| --- | --- | --- |
| **@skip(if: Boolean!)** | Bỏ qua field hoặc fragment khi điều kiện đúng | Query, field, fragment |
| **@include(if: Boolean!)** | Chỉ lấy field hoặc fragment khi điều kiện đúng | Query, field, fragment |
| **@deprecated(reason: String)** | Đánh dấu field hoặc enum value đã lỗi thời | Schema definition |
| **@specifiedBy(url: String!)** | Công bố đặc tả định dạng của custom scalar | Scalar definition |

@skip và @include thường được client đặt trong operation để điều khiển selection set theo biến. @deprecated và @specifiedBy gắn với định nghĩa schema. Custom schema directive cũng được khai báo và áp dụng trên những thành phần của schema như object, field, argument, enum hoặc scalar.

## Định nghĩa custom directive trong SDL

Dùng từ khóa directive để định nghĩa directive. Cú pháp cơ bản gồm tên, danh sách argument tùy chọn và danh sách vị trí được phép áp dụng sau từ khóa on:

~~~graphql
directive @auth(role: String!) on FIELD_DEFINITION
~~~

Định nghĩa trên tạo directive @auth có một argument bắt buộc là role, chỉ được áp dụng trên field definition. Ví dụ:

~~~graphql
type Query {
  publicMessage: String!
  adminReport: String! @auth(role: "ADMIN")
}
~~~

Ở đây, @auth gắn metadata lên field adminReport. Chỉ khai báo directive trong SDL chưa tự động kiểm tra quyền người dùng. Ứng dụng phải đăng ký cách xử lý directive hoặc bảo vệ resolver bằng cơ chế bảo mật tương ứng. Nếu không có phần triển khai ở server, directive chỉ là thông tin trong schema.

Directive có thể có argument với giá trị mặc định:

~~~graphql
enum AccessRole {
  USER
  ADMIN
}

directive @requiresRole(
  role: AccessRole! = USER
) on FIELD_DEFINITION

type Query {
  profile: Profile @requiresRole
  auditLog: [AuditEntry!]! @requiresRole(role: ADMIN)
}
~~~

profile sử dụng giá trị mặc định USER; auditLog yêu cầu ADMIN. Dùng enum thay cho chuỗi tự do giúp schema giới hạn các giá trị hợp lệ và mô tả hợp đồng rõ ràng hơn.

## Directive locations

Directive location quy định directive được phép xuất hiện ở đâu. Nếu áp dụng directive sai vị trí, schema không hợp lệ. Các vị trí trong nhóm type system thường gặp gồm:

| Location | Thành phần được áp dụng |
| --- | --- |
| **SCHEMA** | Toàn bộ schema |
| **SCALAR** | Scalar type |
| **OBJECT** | Object type |
| **FIELD_DEFINITION** | Field được khai báo trong type |
| **ARGUMENT_DEFINITION** | Argument của field hoặc directive |
| **INTERFACE** | Interface type |
| **UNION** | Union type |
| **ENUM** | Enum type |
| **ENUM_VALUE** | Một giá trị enum |
| **INPUT_OBJECT** | Input object type |
| **INPUT_FIELD_DEFINITION** | Field bên trong input object |

Ví dụ một directive đánh dấu dữ liệu cần che trong response có thể chỉ cho phép áp dụng trên field:

~~~graphql
directive @sensitive on FIELD_DEFINITION

type User {
  id: ID!
  displayName: String!
  email: String! @sensitive
}
~~~

Nếu directive cần áp dụng trên cả object và field, khai báo nhiều location:

~~~graphql
directive @audit(event: String!) on OBJECT | FIELD_DEFINITION
~~~

OBJECT | FIELD_DEFINITION có nghĩa directive có thể gắn lên object type hoặc một field cụ thể. Danh sách location là một phần của hợp đồng directive, không phải danh sách gợi ý.

## Directive có thể repeatable

Mặc định, một directive không được lặp nhiều lần tại cùng một vị trí. Nếu có trường hợp cần gắn nhiều giá trị, khai báo từ khóa repeatable:

~~~graphql
directive @tag(name: String!) repeatable on OBJECT | FIELD_DEFINITION

type Book
  @tag(name: "catalog")
  @tag(name: "searchable") {
  id: ID!
  title: String! @tag(name: "display")
}
~~~

Trong ví dụ, object Book nhận hai tag. Nếu không có repeatable, việc đặt cùng directive @tag nhiều lần trên Book sẽ vi phạm quy tắc schema. Directive repeatable phù hợp với metadata có thể có nhiều giá trị như tag, category hoặc nhãn phân loại.

Directive có thể được định nghĩa với nhiều argument:

~~~graphql
enum CacheScope {
  PUBLIC
  PRIVATE
}

directive @cacheControl(
  maxAge: Int! = 60
  scope: CacheScope! = PUBLIC
) on OBJECT | FIELD_DEFINITION

type Query {
  publicCatalog: [Book!]!
    @cacheControl(maxAge: 300, scope: PUBLIC)
  myProfile: Profile!
    @cacheControl(maxAge: 0, scope: PRIVATE)
}
~~~

Directive @cacheControl trong ví dụ biểu diễn metadata cache. Server hoặc gateway phải đọc metadata và áp dụng chính sách cache tương ứng; GraphQL không tự thay đổi HTTP cache chỉ vì SDL có directive này.

## Phân biệt schema directive và executable directive

GraphQL có thể đặt directive trên hai nhóm vị trí:

- **Schema/type-system directive** được gắn vào định nghĩa schema như OBJECT, FIELD_DEFINITION, SCALAR hoặc ENUM_VALUE. Chúng thường được xử lý khi xây dựng schema và runtime wiring.
- **Executable directive** được đặt trong operation của client như QUERY, FIELD, FRAGMENT_SPREAD hoặc INLINE_FRAGMENT. Chúng tác động đến cách operation được kiểm tra hoặc thực thi.

Ví dụ schema directive:

~~~graphql
type User {
  email: String! @sensitive
}
~~~

Ví dụ executable directive:

~~~graphql
query UserDetails($includeEmail: Boolean!) {
  user(id: "user-10") {
    id
    displayName
    email @include(if: $includeEmail)
  }
}
~~~

Hai loại directive có thể cùng dùng cú pháp @, nhưng được xử lý ở các giai đoạn khác nhau. SchemaDirectiveWiring trong GraphQL Java dành cho việc wiring directive trên schema element. Nếu muốn định nghĩa directive riêng trong operation của client, cần cơ chế xử lý ở execution layer, chẳng hạn instrumentation hoặc một phần mở rộng phù hợp; đăng ký SchemaDirectiveWiring không tự làm cho executable directive chạy.

## Triển khai custom schema directive với GraphQL Java

Ví dụ sau tạo directive @uppercase, dùng để chuyển chuỗi do field trả về thành chữ hoa. Đây là ví dụ minh họa cách directive bọc data fetcher hiện có:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Query {
  greeting: String! @uppercase
}
~~~

Triển khai SchemaDirectiveWiring:

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

        DataFetcher<?> originalFetcher =
                environment.getCodeRegistry().getDataFetcher(
                        environment.getFieldsContainer(), field);

        DataFetcher<?> wrappedFetcher = DataFetcherFactories.wrapDataFetcher(
                originalFetcher,
                (dataFetchingEnvironment, value) -> {
                    if (value instanceof String text) {
                        return text.toUpperCase(Locale.ROOT);
                    }
                    return value;
                });

        environment.getCodeRegistry().dataFetcher(
                environment.getFieldsContainer(), field, wrappedFetcher);

        return field;
    }
}
~~~

onField được gọi khi GraphQL Java xử lý directive gắn trên field definition. Implementation lấy data fetcher hiện tại, bọc nó bằng một hàm chuyển đổi kết quả rồi đăng ký data fetcher mới vào code registry. Nhờ vậy, logic resolver gốc vẫn được thực thi; directive chỉ xử lý giá trị sau khi resolver trả về.

Locale.ROOT được dùng để chuyển chữ hoa theo quy tắc ổn định, không phụ thuộc locale của máy chủ. Ví dụ này chỉ chuyển đổi giá trị kiểu String; các kiểu khác được trả nguyên trạng.

## Đăng ký directive trong Spring for GraphQL

Spring for GraphQL cho phép bổ sung schema wiring thông qua bean RuntimeWiringConfigurer. Đăng ký directive uppercase như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlDirectiveConfiguration {

    @Bean
    RuntimeWiringConfigurer directiveWiringConfigurer() {
        return builder -> builder.directive(
                "uppercase",
                new UppercaseDirective()
        );
    }
}
~~~

Spring Boot phát hiện bean này khi tạo GraphQL runtime. Tên truyền vào builder.directive phải trùng với tên directive được khai báo trong SDL. Khi schema có field được gắn @uppercase, GraphQL Java gọi UppercaseDirective trong quá trình wiring.

Resolver có thể trả về chuỗi bình thường:

~~~java
@Controller
public class GreetingController {

    @QueryMapping
    public String greeting() {
        return "hello from spring graphql";
    }
}
~~~

Khi client gửi:

~~~graphql
query {
  greeting
}
~~~

Response nhận được:

~~~json
{
  "data": {
    "greeting": "HELLO FROM SPRING GRAPHQL"
  }
}
~~~

Quy tắc chuyển chữ hoa nằm trong directive wiring, không nằm trong controller. Cách tổ chức này hữu ích cho những hành vi trình bày hoặc metadata thực sự dùng chung. Với logic nghiệp vụ quan trọng, cần cân nhắc đặt trong service hoặc resolver để hành vi dễ kiểm thử và quan sát hơn.

## Dùng directive cho metadata bảo mật

Một directive có thể diễn đạt yêu cầu quyền truy cập ngay trong schema:

~~~graphql
enum Role {
  USER
  ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
  profile: Profile! @requiresRole(role: USER)
  auditLog: [AuditEntry!]! @requiresRole(role: ADMIN)
}
~~~

Định nghĩa này giúp người đọc schema nhận ra field nào có yêu cầu role. Nhưng @requiresRole không tự xác thực người dùng và không tự chặn request. Server phải triển khai enforcement. Trong ứng dụng Spring, có thể bảo vệ resolver bằng Spring Security method security:

~~~java
@Controller
public class AdminController {

    @PreAuthorize("hasRole('ADMIN')")
    @QueryMapping
    public List<AuditEntry> auditLog() {
        return auditService.findRecentEntries();
    }
}
~~~

Ví dụ cần bật method security trong cấu hình Spring Security. Directive có thể được dùng làm metadata cho tooling, tài liệu hoặc cơ chế wiring riêng, nhưng quyền truy cập phải được kiểm tra ở server theo principal hiện tại. Không nên chỉ ẩn field khỏi schema hoặc dựa vào client không gửi field để coi đó là bảo mật.

## Kiểm thử custom schema directive

Nên kiểm tra cả wiring lẫn kết quả operation:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Field có @uppercase trả về String | Giá trị response được chuyển thành chữ hoa |
| Resolver trả về kiểu không phải String | Giá trị giữ nguyên theo implementation ví dụ |
| Field không gắn @uppercase | Kết quả không bị chuyển đổi |
| Directive đặt sai location | Schema không được xây dựng thành công |
| SDL có directive nhưng chưa đăng ký wiring | Server báo lỗi wiring hoặc directive không có hành vi tùy cách xây dựng schema |
| Field có yêu cầu role | Người dùng đúng quyền được phép, người dùng thiếu quyền bị từ chối |

Có thể dùng GraphQlTester để kiểm tra kết quả:

~~~java
graphQlTester.document("""
        query {
            greeting
        }
        """)
    .execute()
    .path("greeting")
    .entity(String.class)
    .isEqualTo("HELLO FROM SPRING GRAPHQL");
~~~

Với directive có argument, cần kiểm tra cả giá trị mặc định và giá trị được truyền tường minh. Với directive repeatable, xác minh cách wiring xử lý nhiều lần xuất hiện và thứ tự áp dụng nếu hành vi phụ thuộc thứ tự. Với directive bảo mật, cần có test cho cả trường hợp được phép và bị từ chối.

## Introspection và khả năng khám phá directive

GraphQL introspection cho phép client hoặc công cụ phát triển khám phá các directive được schema công bố, gồm tên, mô tả, locations, argument và thông tin repeatable nếu phiên bản runtime hỗ trợ. Ví dụ:

~~~graphql
query Directives {
  __schema {
    directives {
      name
      description
      isRepeatable
      locations
      args {
        name
        description
      }
    }
  }
}
~~~

Introspection giúp IDE hoặc tài liệu API hiển thị cách directive được định nghĩa. Nó không chứng minh directive đã được triển khai đúng hoặc chính sách của nó đang được thực thi. Muốn xác nhận hành vi, cần kiểm thử operation và cấu hình runtime thực tế.

## Nguyên tắc thiết kế custom schema directive

Khi tạo directive riêng, nên giữ các nguyên tắc sau:

1. **Chọn location chính xác.** Chỉ cho phép directive xuất hiện ở nơi có ý nghĩa, tránh làm schema khó hiểu.
2. **Đặt tên và mô tả rõ.** Tên directive nên biểu đạt mục đích, argument cần có kiểu và default hợp lý.
3. **Tách metadata và enforcement.** Khai báo directive không đồng nghĩa hành vi đã được triển khai; phải có wiring hoặc lớp thực thi tương ứng.
4. **Giữ logic dùng chung và có phạm vi rõ.** Directive phù hợp với hành vi xuyên suốt nhiều field, nhưng không nên biến nó thành nơi chứa nghiệp vụ phức tạp.
5. **Cẩn thận khi bọc data fetcher.** Giữ nguyên lỗi, context, instrumentation và hành vi bất đồng bộ của fetcher gốc; không tự chặn luồng reactive.
6. **Không coi directive là ranh giới bảo mật duy nhất.** Xác thực và phân quyền cần được thực thi ở server bằng Spring Security hoặc cơ chế tương đương.
7. **Kiểm thử schema lẫn runtime.** Kiểm tra directive location, argument, wiring, kết quả và lỗi.

Custom schema directive mở rộng khả năng biểu đạt của SDL bằng cách gắn metadata hoặc hành vi dùng chung vào các thành phần schema. Trong Spring for GraphQL, SDL định nghĩa directive và nơi được phép áp dụng, GraphQL Java xử lý nó thông qua SchemaDirectiveWiring, còn RuntimeWiringConfigurer đăng ký cơ chế wiring vào runtime. Hiểu rõ ranh giới giữa khai báo và thực thi giúp directive trở thành một phần có kiểm soát của hợp đồng API.
