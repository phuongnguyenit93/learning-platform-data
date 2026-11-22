# Custom scalar wiring trong Spring for GraphQL

GraphQL có năm scalar mặc định: `Int`, `Float`, `String`, `Boolean` và `ID`. Khi API cần biểu diễn kiểu dữ liệu khác như ngày giờ, số thập phân chính xác, UUID hoặc giá trị nghiệp vụ, ta có thể khai báo **custom scalar** trong SDL và đăng ký cách chuyển đổi dữ liệu trong runtime wiring.

Spring for GraphQL cung cấp `RuntimeWiringConfigurer` để bổ sung scalar vào `RuntimeWiring.Builder`. Với Spring Boot starter, chỉ cần khai báo bean này là auto-configuration sẽ áp dụng nó khi tạo `GraphQlSource`. Custom scalar vì vậy trở thành một phần của hợp đồng schema và được dùng thống nhất khi GraphQL nhận input hoặc trả output.

## 1. Custom scalar giải quyết vấn đề gì?

Scalar là kiểu dữ liệu đơn trị ở cấp GraphQL. Client nhận một giá trị scalar thay vì một object có các field con. Các scalar mặc định đáp ứng nhiều nhu cầu phổ biến, nhưng không mô tả trực tiếp một số kiểu của ứng dụng:

- `DateTime`: thời điểm có offset hoặc múi giờ.
- `UUID`: định danh có định dạng UUID.
- `BigDecimal`: số thập phân cần giữ độ chính xác.
- `Money`: số tiền với quy tắc định dạng và số chữ số thập phân xác định.
- `URL`: địa chỉ tài nguyên theo định dạng URL.

Không nên dùng `String` cho mọi kiểu dữ liệu chỉ vì JSON có thể truyền chuỗi. Nếu mọi field ngày giờ đều là `String`, schema không thể thể hiện rõ quy ước định dạng và runtime không có một nơi thống nhất để kiểm tra dữ liệu. Custom scalar cho phép đặt tên kiểu theo ý nghĩa domain và gom quy tắc parse/serialize vào một implementation.

Custom scalar vẫn là một scalar đơn trị. Nếu dữ liệu cần nhiều thuộc tính có ý nghĩa riêng, chẳng hạn số tiền và loại tiền tệ, hãy cân nhắc dùng object type hoặc input object thay vì nhồi nhiều thông tin vào một chuỗi.

## 2. Khai báo custom scalar trong SDL

SDL dùng từ khóa `scalar` để khai báo một kiểu scalar mới. Ví dụ schema sử dụng `DateTime`:

~~~graphql
scalar DateTime

type Query {
    serverTime: DateTime!
}

type Event {
    id: ID!
    name: String!
    startsAt: DateTime!
}
~~~

Khai báo `scalar DateTime` mới chỉ tạo tên kiểu trong schema. Nó chưa định nghĩa được giá trị Java nào sẽ được sử dụng hoặc cách chuyển đổi dữ liệu giữa GraphQL và Java. Nếu scalar được dùng trong field hoặc argument mà không có implementation tương ứng, GraphQL runtime sẽ không thể xử lý đúng giá trị đó.

Tên scalar trong SDL phải trùng với tên `GraphQLScalarType` được đăng ký. Ví dụ `scalar DateTime` cần runtime wiring đăng ký scalar tên `DateTime`, không phải `OffsetDateTime` hay `Date`.

## 3. Vòng đời chuyển đổi của một scalar

GraphQL scalar có ba hướng chuyển đổi chính:

~~~mermaid
flowchart TD
    A[Client JSON variable] --> B[parseValue]
    C[Inline GraphQL literal] --> D[parseLiteral]
    B --> E[Java value]
    D --> E
    E --> F[Resolver / Service]
    F --> G[Java result]
    G --> H[serialize]
    H --> I[JSON response value]
~~~

| Phương thức | Khi nào được gọi? | Ví dụ |
| --- | --- | --- |
| `parseValue` | Chuyển input từ GraphQL variables, thường đến từ JSON request | Chuỗi `"2026-11-20T10:15:30Z"` thành `OffsetDateTime` |
| `parseLiteral` | Chuyển literal được viết trực tiếp trong GraphQL document | Literal `"2026-11-20T10:15:30Z"` thành `OffsetDateTime` |
| `serialize` | Chuyển giá trị Java từ resolver thành giá trị response GraphQL | `OffsetDateTime` thành chuỗi ISO-8601 |

Một implementation đúng cần xử lý cả ba phương thức. Chỉ triển khai `parseValue` có thể khiến request dùng variables hoạt động nhưng inline literal thất bại. Chỉ triển khai parse mà serialize sai có thể khiến mutation nhận input được nhưng response không chuyển đổi được.

## 4. Đăng ký scalar có sẵn bằng Extended Scalars

Không phải lúc nào cũng cần tự viết `Coercing`. Thư viện GraphQL Java Extended Scalars cung cấp nhiều implementation đã được sử dụng phổ biến, ví dụ `DateTime`, `Date`, `Time`, `URL`, `UUID` và `BigDecimal`.

Thêm dependency `com.graphql-java:graphql-java-extended-scalars` vào project. Hãy chọn phiên bản tương thích với GraphQL Java mà Spring Boot dependency management đang quản lý; tránh nâng riêng GraphQL Java lên một phiên bản không tương thích với Spring for GraphQL.

### 4.1. Khai báo SDL

~~~graphql
scalar DateTime
scalar UUID
scalar BigDecimal

type Query {
    serverTime: DateTime!
}

type Product {
    id: UUID!
    price: BigDecimal!
}
~~~

### 4.2. Tạo RuntimeWiringConfigurer bean

Trong Spring Boot, có thể đăng ký các scalar bằng bean `RuntimeWiringConfigurer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiring -> wiring
                .scalar(ExtendedScalars.DateTime)
                .scalar(ExtendedScalars.UUID)
                .scalar(ExtendedScalars.GraphQLBigDecimal);
    }
}
~~~

Spring Boot phát hiện bean `RuntimeWiringConfigurer` và áp dụng callback khi tạo GraphQL runtime. Không cần tự tạo `GraphQlSource` chỉ để đăng ký scalar. Nếu ứng dụng không dùng auto-configuration, có thể gọi `configureRuntimeWiring(...)` trên `GraphQlSource` builder để đăng ký cùng cấu hình.

### 4.3. Kiểu Java tương ứng

Resolver có thể dùng kiểu Java phù hợp với scalar implementation:

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

public record Product(UUID id, BigDecimal price) {}

public interface ProductService {
    Product findById(UUID id);
}

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public OffsetDateTime serverTime() {
        return OffsetDateTime.now();
    }

    @QueryMapping
    public Product product(@Argument UUID id) {
        return productService.findById(id);
    }
}
~~~

Trong ví dụ này, scalar `DateTime` được dùng với `OffsetDateTime`, `UUID` với `java.util.UUID` và `BigDecimal` với `java.math.BigDecimal`. Cần kiểm tra tài liệu của scalar implementation để biết chính xác kiểu Java đầu vào và đầu ra mà nó hỗ trợ; tên scalar không tự quyết định kiểu Java.

## 5. Tự định nghĩa scalar Money

Khi quy tắc dữ liệu thuộc domain riêng, ứng dụng có thể tạo `GraphQLScalarType` với `Coercing` do mình triển khai. Ví dụ `Money` được biểu diễn nội bộ bằng `BigDecimal`, còn trên GraphQL wire format là chuỗi thập phân có tối đa hai chữ số sau dấu chấm.

Quy ước của ví dụ:

- Client gửi giá trị dưới dạng chuỗi, ví dụ `"125.50"`.
- Không chấp nhận dấu phân cách hàng nghìn hoặc ký hiệu tiền tệ.
- Cho phép tối đa hai chữ số thập phân.
- Java sử dụng `BigDecimal`, không dùng `double` để giữ độ chính xác.
- Response được serialize thành chuỗi có đúng hai chữ số thập phân.

### 5.1. Khai báo scalar trong schema

~~~graphql
scalar Money

type Product {
    id: ID!
    price: Money!
}

type Query {
    product(id: ID!): Product
    echoMoney(value: Money!): Money!
}
~~~

### 5.2. Viết Coercing

`Coercing` xác định cách parse input variables, parse literal và serialize kết quả. Ví dụ dưới đây dùng API `Coercing` hiện đại của GraphQL Java với `GraphQLContext`, `CoercedVariables` và `Locale`:

~~~java
import graphql.GraphQLContext;
import graphql.execution.CoercedVariables;
import graphql.language.StringValue;
import graphql.language.Value;
import graphql.schema.Coercing;
import graphql.schema.CoercingParseLiteralException;
import graphql.schema.CoercingParseValueException;
import graphql.schema.CoercingSerializeException;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.regex.Pattern;

public final class MoneyCoercing implements Coercing<BigDecimal, String> {

    private static final Pattern FORMAT =
            Pattern.compile("-?(?:0|[1-9]\\d*)(?:\\.\\d{1,2})?");

    @Override
    public String serialize(
            Object dataFetcherResult,
            GraphQLContext graphQLContext,
            Locale locale
    ) {
        if (!(dataFetcherResult instanceof BigDecimal amount)) {
            throw new CoercingSerializeException(
                    "Money result must be represented as BigDecimal"
            );
        }

        try {
            return amount.setScale(2, RoundingMode.UNNECESSARY).toPlainString();
        }
        catch (ArithmeticException ex) {
            throw new CoercingSerializeException(
                    "Money supports at most two fractional digits"
            );
        }
    }

    @Override
    public BigDecimal parseValue(
            Object input,
            GraphQLContext graphQLContext,
            Locale locale
    ) {
        if (!(input instanceof String text)) {
            throw new CoercingParseValueException(
                    "Money variable must be a decimal string"
            );
        }

        try {
            return parseMoney(text);
        }
        catch (IllegalArgumentException ex) {
            throw new CoercingParseValueException("Invalid Money variable");
        }
    }

    @Override
    public BigDecimal parseLiteral(
            Value<?> input,
            CoercedVariables variables,
            GraphQLContext graphQLContext,
            Locale locale
    ) {
        if (!(input instanceof StringValue stringValue)) {
            throw new CoercingParseLiteralException(
                    "Money literal must be a string"
            );
        }

        try {
            return parseMoney(stringValue.getValue());
        }
        catch (IllegalArgumentException ex) {
            throw new CoercingParseLiteralException("Invalid Money literal");
        }
    }

    private static BigDecimal parseMoney(String text) {
        if (!FORMAT.matcher(text).matches()) {
            throw new IllegalArgumentException("Unsupported Money format");
        }
        return new BigDecimal(text).setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Điểm quan trọng trong implementation:

- `serialize` chỉ chấp nhận `BigDecimal`. Nếu resolver trả nhầm `Double`, `String` hoặc object khác, scalar báo lỗi serialize thay vì âm thầm chuyển đổi.
- `parseValue` chỉ chấp nhận JSON string. Điều này tránh việc client gửi JSON floating-point number đã có thể mất độ chính xác trước khi đến Java.
- `parseLiteral` chỉ chấp nhận GraphQL `StringValue`, vì hợp đồng wire format của scalar là chuỗi.
- `setScale(2, RoundingMode.UNNECESSARY)` không làm tròn âm thầm. Giá trị có nhiều hơn hai chữ số thập phân sẽ bị từ chối.
- `toPlainString()` giữ cách biểu diễn thập phân thông thường, tránh dạng scientific notation.

Các method có `GraphQLContext` và `Locale` là chữ ký của các phiên bản GraphQL Java mới. Spring Boot quản lý phiên bản GraphQL Java qua dependency management; nếu project đang dùng phiên bản cũ hơn, hãy đối chiếu chữ ký `Coercing` trong Javadoc đúng phiên bản trước khi copy implementation.

### 5.3. Đăng ký GraphQLScalarType vào runtime wiring

Tạo `GraphQLScalarType` có tên trùng với SDL và đưa nó vào `RuntimeWiring`:

~~~java
import graphql.schema.GraphQLScalarType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class MoneyScalarConfiguration {

    @Bean
    GraphQLScalarType moneyScalar() {
        return GraphQLScalarType.newScalar()
                .name("Money")
                .description("Decimal amount with at most two fractional digits")
                .coercing(new MoneyCoercing())
                .build();
    }

    @Bean
    RuntimeWiringConfigurer moneyScalarConfigurer(
            GraphQLScalarType moneyScalar
    ) {
        return wiring -> wiring.scalar(moneyScalar);
    }
}
~~~

Sau khi đăng ký, resolver có thể nhận hoặc trả về `BigDecimal`:

~~~java
import java.math.BigDecimal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MoneyController {

    @QueryMapping
    public BigDecimal echoMoney(@Argument("value") BigDecimal value) {
        return value;
    }
}
~~~

Request inline literal:

~~~graphql
query {
    echoMoney(value: "125.5")
}
~~~

Response có giá trị `"125.50"`. Nếu dùng variables, giá trị cũng phải là chuỗi JSON:

~~~json
{
    "query": "query Echo($value: Money!) { echoMoney(value: $value) }",
    "variables": {
        "value": "125.50"
    }
}
~~~

Không gửi `125.50` dưới dạng JSON number theo hợp đồng scalar này. Cũng không gửi `"$125.50"` hoặc `"125,50"`, vì format đã chọn không chấp nhận ký hiệu tiền tệ hay dấu phẩy thập phân.

## 6. Đăng ký scalar qua RuntimeWiringConfigurer hay GraphQlSourceBuilderCustomizer?

Spring for GraphQL có nhiều extension point để cấu hình GraphQL runtime. Với nhu cầu chỉ đăng ký scalar, `RuntimeWiringConfigurer` là lựa chọn tập trung và đơn giản.

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiring -> wiring.scalar(ExtendedScalars.DateTime);
}
~~~

Nếu cần tùy chỉnh sâu hơn builder tạo `GraphQlSource`, có thể dùng `GraphQlSourceBuilderCustomizer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer graphQlSourceCustomizer() {
    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.scalar(ExtendedScalars.DateTime)
    );
}
~~~

Import trong ví dụ dùng Spring Boot 3.x. Với Spring Boot 4.x, package của interface chuyển thành `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer`; hãy dùng package tương ứng với phiên bản dự án.

Hai cách đều đưa scalar vào runtime wiring, nhưng khác phạm vi:

| Extension point | Khi nên dùng |
| --- | --- |
| `RuntimeWiringConfigurer` | Đăng ký scalar, directive, data fetcher hoặc type resolver |
| `GraphQlSourceBuilderCustomizer` | Cần thêm cấu hình builder rộng hơn như schema factory, schema inspection, instrumentation hoặc GraphQL builder |

Không đăng ký cùng một scalar lặp lại trong nhiều configurer/customizer. Nếu có nhiều bean cùng cấu hình một scalar, việc ghi đè hoặc xung đột có thể gây lỗi khi tạo schema. Hãy chọn một nơi sở hữu implementation và registration.

## 7. Quy tắc thiết kế custom scalar

Một scalar là một phần của public API. Trước khi viết implementation, hãy xác định rõ hợp đồng dữ liệu.

### 7.1. Chọn wire format ổn định

Ví dụ với ngày giờ, có thể chọn ISO-8601 có offset như `2026-11-20T10:15:30+07:00`. Với số tiền, có thể chọn chuỗi thập phân như `125.50`. Tránh để format phụ thuộc locale của máy chủ hoặc client.

### 7.2. Kiểu Java nội bộ phải rõ ràng

Chọn một kiểu Java nhất quán cho scalar. Ví dụ:

| Scalar | Kiểu Java gợi ý |
| --- | --- |
| `DateTime` | `OffsetDateTime` hoặc kiểu thời gian đã thống nhất |
| `UUID` | `java.util.UUID` |
| `BigDecimal` | `java.math.BigDecimal` |
| `Money` trong ví dụ | `java.math.BigDecimal` |

Không dùng `double` hoặc `float` để lưu tiền hoặc dữ liệu cần độ chính xác thập phân. Binary floating-point không biểu diễn chính xác nhiều số thập phân thông thường.

### 7.3. Validate cả input và output

`parseValue` và `parseLiteral` bảo vệ dữ liệu đi vào resolver. `serialize` bảo vệ hợp đồng response khi resolver trả dữ liệu. Đừng chỉ kiểm tra input rồi giả định mọi giá trị Java trả về đều hợp lệ.

### 7.4. Không làm tròn âm thầm

Nếu domain yêu cầu tối đa hai chữ số thập phân, cần quyết định rõ giá trị `12.345` sẽ bị từ chối hay làm tròn theo một quy tắc cụ thể. Ví dụ `RoundingMode.UNNECESSARY` từ chối việc phải làm tròn; nếu nghiệp vụ cho phép làm tròn, hãy chọn rounding mode và đặt quy tắc ở domain/service một cách nhất quán.

### 7.5. Thông báo lỗi không tiết lộ dữ liệu nhạy cảm

Thông báo lỗi scalar nên mô tả format mong đợi và vị trí lỗi đủ để client sửa request. Không đưa dữ liệu nhạy cảm, stack trace hoặc thông tin nội bộ vào lỗi trả về client.

## 8. Kiểm thử custom scalar

Nên kiểm tra cả ba hướng chuyển đổi: parse literal, parse variable và serialize response. Có thể dùng `GraphQlTester` để thực thi operation qua GraphQL runtime.

Ví dụ kiểm thử scalar `Money`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@GraphQlTest(MoneyController.class)
@Import(MoneyScalarConfiguration.class)
class MoneyScalarTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void parsesLiteralAndSerializesResult() {
        graphQlTester.document("""
                query {
                    echoMoney(value: "125.50")
                }
                """)
            .execute()
            .path("echoMoney")
            .entity(String.class)
            .isEqualTo("125.50");
    }

    @Test
    void parsesVariable() {
        graphQlTester.document("""
                query Echo($value: Money!) {
                    echoMoney(value: $value)
                }
                """)
            .variable("value", "125.50")
            .execute()
            .path("echoMoney")
            .entity(String.class)
            .isEqualTo("125.50");
    }

    @Test
    void rejectsMoreThanTwoFractionalDigits() {
        graphQlTester.document("""
                query Echo($value: Money!) {
                    echoMoney(value: $value)
                }
                """)
            .variable("value", "12.345")
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }
}
~~~

Test import `MoneyScalarConfiguration` để đưa custom scalar vào test slice. `MoneyController` trả lại chính giá trị đã parse nên test literal xác nhận `parseLiteral`, test variables xác nhận `parseValue`; cả hai test hợp lệ đều đi qua `serialize` để tạo response. Test giá trị `12.345` xác nhận input sai format bị GraphQL từ chối.

Ngoài ra, nên kiểm tra resolver trả nhầm kiểu Java hoặc trả `BigDecimal` có scale không hợp lệ để xác nhận `serialize` từ chối output sai. Kiểm thử trực tiếp `MoneyCoercing` cũng hữu ích cho các trường hợp biên của regex và precision.

## 9. Lỗi thường gặp khi wiring scalar

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Scalar được khai báo nhưng runtime báo không có coercing | Chỉ viết `scalar DateTime` trong SDL, chưa đăng ký implementation | Đăng ký bằng `RuntimeWiringConfigurer` hoặc customizer |
| Scalar name không khớp | SDL dùng `DateTime` nhưng scalar đăng ký tên khác | Đảm bảo tên `GraphQLScalarType` trùng SDL |
| Variables hoạt động nhưng literal thất bại | `parseLiteral` chưa được triển khai đúng | Xử lý AST node trong `parseLiteral` |
| Input hợp lệ nhưng response lỗi | `serialize` không hỗ trợ kiểu Java resolver trả về | Chuẩn hóa kiểu Java hoặc sửa serialization contract |
| JSON number bị từ chối | Scalar quy định input là string | Gửi biến dưới dạng JSON string theo wire format |
| Lỗi method signature khi compile | API `Coercing` khác giữa các phiên bản GraphQL Java | Kiểm tra phiên bản do Spring Boot quản lý và dùng đúng Javadoc |
| Scalar bị đăng ký trùng | Nhiều configurer/customizer cùng đăng ký scalar | Chỉ giữ một nơi sở hữu registration |

## 10. Quy trình thêm custom scalar mới

Khi bổ sung một scalar cho API, thực hiện theo các bước:

1. Xác định ý nghĩa domain, kiểu Java nội bộ và wire format mà client sẽ gửi/nhận.
2. Khai báo `scalar Name` trong SDL và dùng scalar ở field hoặc argument cần thiết.
3. Chọn implementation có sẵn từ Extended Scalars nếu đáp ứng đúng hợp đồng; nếu không, tạo `GraphQLScalarType` và `Coercing` riêng.
4. Triển khai đầy đủ `parseValue`, `parseLiteral` và `serialize`.
5. Đăng ký scalar bằng một `RuntimeWiringConfigurer` bean; chỉ dùng `GraphQlSourceBuilderCustomizer` khi cần cấu hình builder rộng hơn.
6. Kiểm thử input variables, inline literals, output serialization và các giá trị sai format.
7. Ghi rõ format trong tài liệu API để client không phải suy đoán cách biểu diễn dữ liệu.

Custom scalar giúp schema diễn đạt kiểu dữ liệu theo ngôn ngữ domain và tập trung quy tắc chuyển đổi tại runtime wiring. Khi wire format, kiểu Java và validation được xác định rõ, client và server có thể trao đổi dữ liệu nhất quán hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphqlsource)
- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [GraphQL Java — Custom Scalars](https://www.graphql-java.com/documentation/scalars/)
- [GraphQL Java Extended Scalars](https://github.com/graphql-java/graphql-java-extended-scalars)
- [GraphQL Specification — Scalars](https://spec.graphql.org/October2021/#sec-Scalars)
