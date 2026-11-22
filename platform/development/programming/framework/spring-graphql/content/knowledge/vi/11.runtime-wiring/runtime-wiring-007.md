# Custom scalar wiring

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao khai báo custom scalar trong SDL chưa đủ để GraphQL xử lý giá trị.
- Đăng ký GraphQLScalarType bằng RuntimeWiringConfigurer trong Spring for GraphQL.
- Tận dụng các scalar mở rộng như DateTime, Date, Long và BigDecimal.
- Tự xây dựng scalar bằng Coercing khi ứng dụng cần quy tắc định dạng riêng.
- Phân biệt parse variables, parse literal và serialize kết quả.
- Kiểm thử scalar wiring bằng GraphQlTester và chẩn đoán lỗi thường gặp.

## Custom scalar cần hai phần

GraphQL có năm scalar chuẩn: Int, Float, String, Boolean và ID. Khi API cần biểu diễn giá trị có quy tắc cụ thể hơn, chẳng hạn ngày giờ, mã đơn hàng hoặc số thập phân chính xác, có thể định nghĩa custom scalar.

Để custom scalar hoạt động, ứng dụng cần hai phần:

1. **SDL declaration**: khai báo tên scalar để schema có thể sử dụng nó trong field, argument và input object.
2. **Runtime wiring**: đăng ký một GraphQLScalarType để GraphQL Java biết cách chuyển đổi dữ liệu đầu vào và kết quả đầu ra.

Ví dụ SDL:

~~~graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}

type Query {
  event(id: ID!): Event
}
~~~

Khai báo scalar DateTime chỉ đưa tên kiểu vào schema. Nó chưa mô tả Java type nội bộ, định dạng chuỗi nhận từ client hoặc cách chuyển giá trị resolver thành JSON. Những quy tắc đó được thực hiện bởi scalar implementation được đăng ký trong runtime wiring.

Nếu chỉ khai báo scalar trong SDL mà không đăng ký implementation, schema có thể không xây dựng được hoặc không xử lý giá trị theo cách mong đợi. Tên scalar trong SDL phải khớp với tên của GraphQLScalarType được đăng ký.

## RuntimeWiringConfigurer trong Spring for GraphQL

GraphQL Java cung cấp RuntimeWiring.Builder để đăng ký custom scalar, directive, type resolver và các thành phần thực thi khác. Spring for GraphQL cung cấp RuntimeWiringConfigurer làm extension point để cấu hình builder này.

Trong ứng dụng Spring Boot, các bean RuntimeWiringConfigurer được Boot phát hiện và áp dụng khi xây dựng GraphQlSource. Vì vậy, thông thường bạn chỉ cần khai báo bean trong một lớp Configuration:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.DateTime);
    }
}
~~~

Khi GraphQL runtime được khởi tạo, scalarConfigurer đăng ký scalar DateTime vào RuntimeWiring.Builder. Các controller vẫn có thể dùng @QueryMapping, @MutationMapping và @SchemaMapping như bình thường; custom scalar chỉ chịu trách nhiệm chuyển đổi giá trị.

Không cần tự tạo GraphQlSource hoặc đăng ký DataFetcher thủ công chỉ để thêm một scalar. Hãy dùng RuntimeWiringConfigurer cho phần mở rộng này và để Boot quản lý vòng đời cấu hình GraphQL.

## Dùng thư viện graphql-java-extended-scalars

Trước khi tự viết Coercing, hãy kiểm tra thư viện graphql-java-extended-scalars. Thư viện cung cấp nhiều kiểu mở rộng phổ biến, chẳng hạn:

| Scalar | Kiểu Java runtime thường dùng | Ví dụ |
| --- | --- | --- |
| DateTime | OffsetDateTime | 2025-04-10T09:30:00+07:00 |
| Date | LocalDate | 2025-04-10 |
| Time | OffsetTime | 09:30:00+07:00 |
| Long | Long | 9223372036854775807 |
| BigDecimal | BigDecimal | 12345.6789 |
| UUID | UUID | 550e8400-e29b-41d4-a716-446655440000 |

Danh sách cụ thể phụ thuộc phiên bản thư viện. Hãy xem tài liệu của phiên bản được dự án sử dụng trước khi chọn scalar.

### Thêm dependency

Với Gradle:

~~~groovy
dependencies {
    implementation 'com.graphql-java:graphql-java-extended-scalars:<compatible-version>'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>com.graphql-java</groupId>
    <artifactId>graphql-java-extended-scalars</artifactId>
    <version>compatible-version</version>
</dependency>
~~~

Thay compatible-version bằng phiên bản tương thích với GraphQL Java mà Spring Boot đang quản lý. Không nên chọn phiên bản mới nhất một cách độc lập nếu nó yêu cầu GraphQL Java khác phiên bản của ứng dụng. README của thư viện Extended Scalars công bố các dòng phiên bản tương thích; hãy đối chiếu trước khi nâng cấp.

### Đăng ký DateTime

Sau khi thêm dependency, khai báo scalar trong SDL:

~~~graphql
scalar DateTime
  @specifiedBy(url: "https://scalars.graphql.org/andimarek/date-time.html")

type Event {
  id: ID!
  startsAt: DateTime!
}
~~~

Sau đó đăng ký scalar:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiringBuilder -> wiringBuilder
            .scalar(ExtendedScalars.DateTime);
}
~~~

Scalar DateTime của Extended Scalars tuân theo định dạng RFC 3339 và tạo OffsetDateTime trong Java runtime. Vì vậy, model hoặc service có thể sử dụng kiểu OffsetDateTime:

~~~java
public record Event(
        String id,
        OffsetDateTime startsAt) {
}
~~~

Ví dụ query:

~~~graphql
query {
  event(id: "event-101") {
    id
    startsAt
  }
}
~~~

Response có thể chứa giá trị chuỗi:

~~~json
{
  "data": {
    "event": {
      "id": "event-101",
      "startsAt": "2025-04-10T09:30:00+07:00"
    }
  }
}
~~~

### Đăng ký nhiều scalar

Một RuntimeWiringConfigurer có thể đăng ký nhiều scalar:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiringBuilder -> wiringBuilder
            .scalar(ExtendedScalars.DateTime)
            .scalar(ExtendedScalars.Date)
            .scalar(ExtendedScalars.BigDecimal)
            .scalar(ExtendedScalars.UUID);
}
~~~

SDL phải khai báo những scalar mà schema sử dụng:

~~~graphql
scalar DateTime
scalar Date
scalar BigDecimal
scalar UUID

type Invoice {
  id: ID!
  issuedOn: Date!
  createdAt: DateTime!
  total: BigDecimal!
  reference: UUID!
}
~~~

Chỉ đăng ký scalar thực sự cần dùng. Việc thêm một scalar vào runtime wiring không tự động thêm field vào schema; SDL vẫn quyết định nơi và cách client có thể sử dụng kiểu đó.

## Quy trình coercion của scalar

Một custom scalar có ba hướng chuyển đổi quan trọng:

| Method | Dữ liệu đầu vào | Kết quả |
| --- | --- | --- |
| parseValue | Giá trị từ variables JSON | Giá trị Java nội bộ |
| parseLiteral | Literal trong GraphQL document | Giá trị Java nội bộ |
| serialize | Giá trị resolver trả về | Giá trị scalar trong response JSON |

Ví dụ operation có cả variable và literal:

~~~graphql
query SearchEvents($after: DateTime!) {
  events(after: $after, before: "2025-12-31T23:59:59+07:00") {
    id
    startsAt
  }
}
~~~

Variables:

~~~json
{
  "after": "2025-01-01T00:00:00+07:00"
}
~~~

Trong operation này:

- parseValue xử lý giá trị của $after lấy từ variables.
- parseLiteral xử lý chuỗi ngày giờ được viết trực tiếp trong document cho before.
- serialize chuyển các giá trị startsAt từ resolver thành định dạng scalar gửi về client.

Một implementation chỉ xử lý parseValue có thể chạy với variables nhưng thất bại khi client dùng literal trực tiếp. Một implementation chỉ parse input mà không serialize đúng có thể nhận request thành công nhưng lỗi khi tạo response.

## Tự định nghĩa scalar bằng Coercing

Khi thư viện mở rộng không đáp ứng quy tắc riêng của ứng dụng, có thể tạo GraphQLScalarType và triển khai Coercing.

Giả sử hệ thống dùng mã đơn hàng có định dạng ORD- theo sau bởi đúng sáu chữ số. Ta muốn schema sử dụng scalar OrderCode thay cho String:

~~~graphql
scalar OrderCode

type Order {
  code: OrderCode!
}

type Query {
  order(code: OrderCode!): Order
}
~~~

### Viết scalar implementation

Ví dụ dưới đây dùng chữ ký Coercing hiện đại của GraphQL Java, với GraphQLContext, Locale và CoercedVariables:

~~~java
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
import java.util.regex.Pattern;

public final class OrderCodeScalar {

    private static final Pattern FORMAT =
            Pattern.compile("ORD-[0-9]{6}");

    public static final GraphQLScalarType ORDER_CODE =
            GraphQLScalarType.newScalar()
                    .name("OrderCode")
                    .description("Mã đơn hàng dạng ORD- theo sau bởi sáu chữ số")
                    .coercing(new Coercing<String, String>() {

                        @Override
                        public String serialize(
                                Object dataFetcherResult,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (dataFetcherResult instanceof String value
                                    && FORMAT.matcher(value).matches()) {
                                return value;
                            }
                            throw new CoercingSerializeException(
                                    "OrderCode result has an invalid format");
                        }

                        @Override
                        public String parseValue(
                                Object input,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (input instanceof String value
                                    && FORMAT.matcher(value).matches()) {
                                return value;
                            }
                            throw new CoercingParseValueException(
                                    "OrderCode variable has an invalid format");
                        }

                        @Override
                        public String parseLiteral(
                                Value<?> input,
                                CoercedVariables variables,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (input instanceof StringValue stringValue) {
                                String value = stringValue.getValue();
                                if (FORMAT.matcher(value).matches()) {
                                    return value;
                                }
                            }
                            throw new CoercingParseLiteralException(
                                    "OrderCode literal has an invalid format");
                        }

                        @Override
                        public Value<?> valueToLiteral(
                                Object input,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            String value = serialize(
                                    input, graphQLContext, locale);
                            return StringValue.newStringValue(value).build();
                        }
                    })
                    .build();

    private OrderCodeScalar() {
    }
}
~~~

Implementation có bốn trách nhiệm:

- serialize kiểm tra dữ liệu resolver trả về và chuyển thành giá trị string trên response.
- parseValue kiểm tra variables JSON và chuyển thành giá trị Java.
- parseLiteral chỉ chấp nhận StringValue trong GraphQL AST, sau đó kiểm tra định dạng.
- valueToLiteral chuyển giá trị đầu vào hợp lệ thành AST literal khi GraphQL Java cần biểu diễn giá trị đó dưới dạng literal.

Trong cả ba đường chính, quy tắc định dạng đều giống nhau. Nếu một input hợp lệ qua variables nhưng không hợp lệ qua literal, client sẽ gặp hành vi không nhất quán.

### Đăng ký custom scalar

Đưa scalar vừa tạo vào runtime wiring:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiringBuilder -> wiringBuilder
                .scalar(OrderCodeScalar.ORDER_CODE);
    }
}
~~~

Từ thời điểm schema được xây dựng, GraphQL runtime có thể dùng OrderCode cho argument, input field và output field đã khai báo trong SDL.

## Lỗi coercion và cách xử lý

GraphQL Java quy định mỗi method coercion phải phát sinh đúng loại exception khi không thể chuyển đổi:

| Method | Exception nên dùng | Tình huống |
| --- | --- | --- |
| serialize | CoercingSerializeException | Resolver trả về kiểu hoặc định dạng không thể serialize |
| parseValue | CoercingParseValueException | Variable JSON có kiểu hoặc định dạng sai |
| parseLiteral | CoercingParseLiteralException | Literal có AST node hoặc định dạng không hợp lệ |

Không trả null để biểu thị dữ liệu sai định dạng. null là một giá trị GraphQL có semantics riêng và có thể hợp lệ nếu field nullable. Khi scalar không thể chuyển đổi dữ liệu, hãy ném exception tương ứng để GraphQL tạo lỗi coercion.

Không để RuntimeException tùy ý thoát khỏi method coercion. Hãy bắt lỗi chuyển đổi cần thiết và chuyển thành đúng loại Coercing...Exception. Thông điệp lỗi nên mô tả vấn đề ở mức client cần biết; tránh đưa stack trace, câu truy vấn database hoặc dữ liệu nhạy cảm vào lỗi.

Scalar nên tập trung xác thực định dạng và biểu diễn dữ liệu. Các quy tắc như mã đơn hàng có tồn tại hay người dùng có quyền xem đơn hàng đó không thuộc trách nhiệm của scalar; hãy kiểm tra trong resolver hoặc service.

## Alias scalar và khi nào nên dùng

Đôi khi dữ liệu có thể biểu diễn bằng scalar chuẩn nhưng muốn đặt tên thể hiện ý nghĩa nghiệp vụ. Ví dụ, một liên kết bài viết có thể là string, nhưng ArticleUrl giúp schema dễ đọc hơn:

~~~graphql
scalar ArticleUrl

type Article {
  id: ID!
  url: ArticleUrl!
}
~~~

Extended Scalars hỗ trợ tạo alias scalar từ scalar có sẵn. Ví dụ:

~~~java
import graphql.Scalars;
import graphql.scalars.ExtendedScalars;
import graphql.schema.GraphQLScalarType;

GraphQLScalarType articleUrl =
        ExtendedScalars.newAliasedScalar("ArticleUrl")
                .aliasedScalar(Scalars.GraphQLString)
                .build();
~~~

Sau đó đăng ký alias bằng RuntimeWiringConfigurer:

~~~java
return wiringBuilder -> wiringBuilder.scalar(articleUrl);
~~~

Alias giúp tăng ý nghĩa cho schema nhưng không tự bổ sung validation URL. Nếu cần kiểm tra scheme, host hoặc định dạng URL, hãy dùng scalar chuyên biệt đã có hoặc tự triển khai Coercing với quy tắc được xác định rõ.

Không nên dùng custom scalar cho dữ liệu có nhiều field mà client cần truy vấn riêng. Ví dụ tiền tệ thường có thể mô hình hóa bằng object type Money với amount và currency, thay vì đóng gói cả hai vào một chuỗi không có cấu trúc.

## Kiểm thử custom scalar bằng GraphQlTester

Nên kiểm thử scalar qua GraphQL operation để xác minh cả SDL, runtime wiring, coercion và resolver.

Ví dụ schema echo một OrderCode:

~~~graphql
type Query {
  echoOrderCode(value: OrderCode!): OrderCode!
}
~~~

Controller:

~~~java
@Controller
public class OrderCodeController {

    @QueryMapping
    public String echoOrderCode(@Argument("value") String value) {
        return value;
    }
}
~~~

Test với variables để kiểm tra parseValue và serialize:

~~~java
graphQlTester.document("""
        query Echo($value: OrderCode!) {
            echoOrderCode(value: $value)
        }
        """)
    .variable("value", "ORD-000123")
    .execute()
    .path("echoOrderCode")
    .entity(String.class)
    .isEqualTo("ORD-000123");
~~~

Test với literal để kiểm tra parseLiteral:

~~~java
graphQlTester.document("""
        query {
            echoOrderCode(value: "ORD-000123")
        }
        """)
    .execute()
    .path("echoOrderCode")
    .entity(String.class)
    .isEqualTo("ORD-000123");
~~~

Nên kiểm tra thêm các trường hợp:

| Đầu vào/đầu ra | Kết quả mong đợi |
| --- | --- |
| ORD-000123 qua variable | Parse và serialize thành công |
| ORD-000123 qua literal | Parse literal và serialize thành công |
| ORD-123 | Bị từ chối vì không đủ sáu chữ số |
| ord-000123 | Bị từ chối nếu contract phân biệt chữ hoa/thường |
| Số 123 thay cho string | Bị từ chối |
| Resolver trả về chuỗi sai định dạng | Serialize thất bại |
| Giá trị null cho field non-null | GraphQL từ chối theo nullability trước khi scalar xử lý giá trị |

Với DateTime, hãy test cả offset múi giờ, giá trị không có offset, định dạng sai và độ chính xác phần giây theo contract đã chọn. Nếu scalar được dùng trong input object, thêm test binding vào DTO hoặc method argument.

## Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Schema không khởi động | SDL có scalar nhưng runtime wiring chưa đăng ký | Thêm bean RuntimeWiringConfigurer |
| Không nhận diện scalar | Tên trong SDL khác tên GraphQLScalarType | Đồng bộ tên scalar |
| Variables hợp lệ nhưng literal thất bại | Chỉ triển khai hoặc kiểm thử parseValue | Triển khai và test parseLiteral |
| Input hợp lệ nhưng response lỗi | serialize không chấp nhận kiểu resolver trả về | Kiểm tra Java runtime type và quy tắc serialize |
| Scalar hoạt động sau khi nâng thư viện nhưng lỗi ở runtime khác | Phiên bản Extended Scalars không tương thích GraphQL Java | Đối chiếu dependency version và dependency tree |
| Giá trị sai định dạng trả về null | Coercing dùng null để báo lỗi | Ném exception coercion đúng loại |
| Scalar kiểm tra cả quyền truy cập dữ liệu | Trộn validation format với business authorization | Chuyển kiểm tra tồn tại và quyền vào service/resolver |

## Thực hành tổng hợp

Trong API quản lý hóa đơn, hãy triển khai các scalar:

1. Dùng Date cho ngày phát hành hóa đơn.
2. Dùng DateTime cho thời điểm tạo bản ghi.
3. Dùng BigDecimal cho tổng tiền nếu thư viện scalar và contract đáp ứng yêu cầu chính xác.
4. Tự tạo InvoiceCode theo định dạng INV- cộng tám chữ số.

Thực hiện theo trình tự:

- Khai báo scalar trong SDL và mô tả format bằng @specifiedBy khi có đặc tả ổn định.
- Thêm dependency Extended Scalars với phiên bản tương thích.
- Đăng ký scalar có sẵn qua RuntimeWiringConfigurer.
- Viết GraphQLScalarType và Coercing cho InvoiceCode.
- Kiểm thử variables, literal và output serialization bằng GraphQlTester.
- Xác minh lỗi coercion không làm lộ dữ liệu nội bộ và service vẫn chịu trách nhiệm kiểm tra nghiệp vụ.

## Ghi nhớ

Custom scalar phải được khai báo trong SDL và đăng ký trong runtime wiring. Spring Boot phát hiện các bean RuntimeWiringConfigurer và áp dụng chúng khi xây dựng GraphQlSource. Hãy ưu tiên Extended Scalars cho những định dạng phổ biến; chỉ tự viết GraphQLScalarType khi cần contract riêng. Một scalar cần xử lý parseValue, parseLiteral và serialize nhất quán, đồng thời phát sinh đúng exception khi coercion thất bại. Kiểm thử cả variables, literal và output bằng GraphQlTester; để validation nghiệp vụ và phân quyền ở service hoặc resolver.

## Tài liệu tham khảo

- [Spring Boot – GraphQL RuntimeWiring](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL – Request Execution và RuntimeWiringConfigurer](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java – Scalars](https://graphql-java.com/documentation/scalars/)
- [graphql-java-extended-scalars](https://github.com/graphql-java/graphql-java-extended-scalars)
