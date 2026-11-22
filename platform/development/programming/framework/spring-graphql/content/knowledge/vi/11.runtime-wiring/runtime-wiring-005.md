# GraphQlSourceBuilderCustomizer trong runtime wiring

`GraphQlSourceBuilderCustomizer` là extension point của Spring Boot cho phép bổ sung cấu hình vào `GraphQlSource` builder trong lúc ứng dụng khởi động. Trong phạm vi runtime wiring, customizer hữu ích khi cần đăng ký scalar, type resolver, data fetcher hoặc schema inspection mà vẫn để Spring Boot quản lý việc tạo `GraphQlSource`.

Điểm cần phân biệt là customizer chạy ở giai đoạn xây dựng GraphQL runtime, không chạy cho từng request. Nó điều chỉnh builder trước khi schema và runtime được build. Khi chỉ cần cấu hình `RuntimeWiring`, `RuntimeWiringConfigurer` thường là extension point trực tiếp hơn; customizer phù hợp khi cấu hình đó cần kết hợp với các khả năng khác của `GraphQlSource.Builder`.

## 1. Runtime wiring nằm ở đâu trong quá trình khởi tạo?

GraphQL SDL mô tả kiểu, field, argument và quan hệ giữa các type. Nhưng SDL không chứa implementation Java để xử lý field. Runtime wiring nối schema với các thành phần thực thi như data fetcher, custom scalar, directive wiring và type resolver.

Khi dùng Spring Boot starter, luồng khởi tạo có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Spring Boot starts] --> B[GraphQl auto-configuration]
    B --> C[Load SDL resources]
    C --> D[Create GraphQlSource builder]
    D --> E[Apply RuntimeWiringConfigurer beans]
    E --> F[Apply GraphQlSourceBuilderCustomizer beans]
    F --> G[Build GraphQlSource]
    G --> H[Create ExecutionGraphQlService]
    H --> I[Handle GraphQL operations]
~~~

Sơ đồ mô tả luồng tổng quát. Các bean wiring và customizer được Spring Boot thu thập trong application context, áp dụng lên builder trước khi source được build. `GraphQlSourceBuilderCustomizer` cho phép tác động đến builder ở giai đoạn này mà không cần tự viết lại toàn bộ auto-configuration.

## 2. GraphQlSourceBuilderCustomizer là gì?

Đây là một functional interface của Spring Boot. Method callback nhận `GraphQlSource.SchemaResourceBuilder`, là builder chuyên đọc schema resource và kế thừa các cấu hình chung của `GraphQlSource.Builder`.

Với Spring Boot 3.x, import interface từ package:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
~~~

Ví dụ bean tối thiểu:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlRuntimeConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer runtimeWiringCustomizer() {
        return builder -> {
            // Add builder-level runtime configuration here.
        };
    }
}
~~~

Với Spring Boot 4.x, package của interface thay đổi thành:

~~~java
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
~~~

Hãy dùng package tương ứng với phiên bản Spring Boot trong dự án. API callback vẫn làm việc với builder của Spring for GraphQL, nhưng không nên copy import Boot 3 vào project Boot 4 hoặc ngược lại.

Customizer chỉ nên cấu hình builder trong callback. Không gọi `build()` bên trong callback, không giữ builder để thay đổi sau khi application context đã khởi tạo và không thực hiện công việc theo từng request ở đây.

## 3. Cấu hình runtime wiring bằng customizer

`GraphQlSource.Builder` cung cấp `configureRuntimeWiring(...)` để bổ sung một `RuntimeWiringConfigurer`. Có thể dùng API này từ customizer:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlRuntimeConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer runtimeWiringCustomizer() {
        return builder -> builder.configureRuntimeWiring(wiring -> {
            // Configure scalar, type resolver, or data fetcher.
        });
    }
}
~~~

Callback `wiring` là `RuntimeWiring.Builder` của GraphQL Java. Tại đây có thể đăng ký scalar, type resolver, data fetcher và các thành phần runtime khác. Các type và field được tham chiếu phải tồn tại trong schema SDL cuối cùng.

Trong ứng dụng chỉ cần runtime wiring, bean `RuntimeWiringConfigurer` thường dễ đọc và đúng trách nhiệm hơn. Customizer có giá trị khi cần kết hợp wiring với schema factory, instrumentation, exception resolver, schema inspection hoặc các cấu hình builder khác.

## 4. Đăng ký custom scalar

Một ví dụ thực tế là scalar `DateTime`. GraphQL không có scalar ngày giờ trong nhóm built-in, vì vậy SDL cần khai báo scalar và runtime wiring phải cung cấp implementation coercing tương ứng.

SDL:

~~~graphql
scalar DateTime

type Query {
    serverTime: DateTime!
}
~~~

Dùng GraphQL Java Extended Scalars để cung cấp implementation:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer dateTimeScalarCustomizer() {
    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.scalar(ExtendedScalars.DateTime)
    );
}
~~~

Khi client gửi hoặc nhận giá trị `DateTime`, scalar implementation chịu trách nhiệm parse input và serialize output. Tên scalar trong SDL phải trùng với tên scalar đã đăng ký. Với scalar do ứng dụng tự định nghĩa, cần triển khai `GraphQLScalarType` và `Coercing` với đủ `parseValue`, `parseLiteral` và `serialize`.

Nếu ứng dụng chỉ cần đăng ký scalar, có thể dùng `RuntimeWiringConfigurer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
RuntimeWiringConfigurer dateTimeRuntimeWiringConfigurer() {
    return wiring -> wiring.scalar(ExtendedScalars.DateTime);
}
~~~

Không đăng ký cùng scalar ở cả hai nơi. Việc khai báo trùng hoặc cấu hình hai implementation khác nhau cho cùng tên có thể dẫn đến xung đột hoặc hành vi khó đoán khi build schema.

## 5. Cấu hình TypeResolver cho interface và union

Khi field trong schema trả về interface hoặc union, GraphQL runtime cần biết object type cụ thể của giá trị Java để thực thi inline fragment. Nếu quy tắc suy luận mặc định không đủ, có thể đăng ký `TypeResolver` trong runtime wiring.

Ví dụ SDL:

~~~graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
}

type Query {
    search: [SearchResult!]!
}
~~~

Giả sử Java model dùng các lớp `BookView` và `ArticleView`, không trùng tên GraphQL object type. Có thể ánh xạ rõ ràng bằng `ClassNameTypeResolver`:

~~~java
public record BookView(String id, String title, String isbn) {}

public record ArticleView(String id, String title, String source) {}
~~~

~~~java
import graphql.schema.TypeRuntimeWiring;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.graphql.execution.ClassNameTypeResolver;

@Bean
GraphQlSourceBuilderCustomizer searchTypeResolverCustomizer() {
    ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
    typeResolver.addMapping(BookView.class, "Book");
    typeResolver.addMapping(ArticleView.class, "Article");

    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.type(TypeRuntimeWiring.newTypeWiring("SearchResult")
                    .typeResolver(typeResolver))
    );
}
~~~

Nếu Java class đã trùng tên với GraphQL object type và resolver mặc định của Spring for GraphQL xác định được concrete type, không cần cấu hình mapping riêng. Với union, đăng ký type resolver cho tên union tương tự như với interface.

## 6. Đăng ký data fetcher cho field cụ thể

Runtime wiring cũng cho phép gắn một data fetcher trực tiếp vào field. Điều này hữu ích với field được tính toán hoặc field không cần một annotated controller method riêng.

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    displayLabel: String!
}
~~~

Data fetcher cho `Book.displayLabel`:

~~~java
import graphql.schema.DataFetcher;
import graphql.schema.TypeRuntimeWiring;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer bookDisplayLabelCustomizer() {
    DataFetcher<String> displayLabelFetcher = environment -> {
        BookView book = environment.getSource();
        return book.title() + " (" + book.id() + ")";
    };

    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.type(TypeRuntimeWiring.newTypeWiring("Book")
                    .dataFetcher("displayLabel", displayLabelFetcher))
    );
}
~~~

Data fetcher nhận `DataFetchingEnvironment`; `getSource()` trả về object cha đang được resolve. Hãy bảo đảm source thực tế có kiểu mà fetcher mong đợi. Nếu field có logic nghiệp vụ, truy cập dữ liệu hoặc phân quyền phức tạp, nên gọi service chuyên trách thay vì đặt toàn bộ logic trong lambda.

Không nên đăng ký cùng một field data fetcher ở nhiều nơi, ví dụ vừa dùng `@SchemaMapping` vừa wiring thủ công cho cùng `Book.displayLabel`. Hãy chọn một cơ chế sở hữu field để tránh cấu hình sau ghi đè cấu hình trước.

## 7. Kết hợp customizer với schema inspection

Khi schema mở rộng, một số field có thể chưa có resolver hoặc data fetcher đăng ký sai tên. `inspectSchemaMappings(...)` giúp kiểm tra quan hệ giữa schema và mapping trong lúc tạo `GraphQlSource`.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer schemaInspectionCustomizer() {
    Logger logger = LoggerFactory.getLogger("GraphQlSchemaInspection");
    return builder -> builder.inspectSchemaMappings(report ->
            logger.info("GraphQL schema mapping report: {}", report)
    );
}
~~~

Schema inspection có thể chỉ ra field chưa map hoặc các registration không khớp schema. Đây là công cụ hỗ trợ phát hiện vấn đề cấu hình; nó không thay thế test nghiệp vụ, kiểm tra quyền truy cập hay đo hiệu năng request.

## 8. Cấu hình GraphQL runtime ngoài runtime wiring

`GraphQlSourceBuilderCustomizer` nhận builder rộng hơn `RuntimeWiring.Builder`. Vì vậy, ngoài wiring, có thể kết hợp các cấu hình khác của GraphQL runtime khi cần.

| Nhu cầu | Vùng cấu hình phù hợp |
| --- | --- |
| Scalar, directive, type resolver, data fetcher | `configureRuntimeWiring(...)` |
| GraphQL Java instrumentation | `instrumentation(...)` hoặc cấu hình tương ứng trên builder |
| Thay đổi cách tạo GraphQL schema | `schemaFactory(...)` |
| Điều chỉnh `GraphQL.Builder` | `configureGraphQl(...)` |
| Xử lý exception từ data fetcher | `exceptionResolvers(...)` |
| Xử lý exception từ subscription publisher | `subscriptionExceptionResolvers(...)` |
| Kiểm tra schema và data fetcher mapping | `inspectSchemaMappings(...)` |

Ví dụ, nếu cần gắn instrumentation để quan sát execution, có thể cấu hình trên builder thay vì nhét logic đo thời gian vào từng resolver. Instrumentation cần được thiết kế phù hợp với phiên bản GraphQL Java mà Spring Boot quản lý.

## 9. Thứ tự nhiều customizer và xung đột wiring

Một ứng dụng có thể khai báo nhiều `GraphQlSourceBuilderCustomizer` bean. Spring Boot thu thập chúng theo thứ tự bean và áp dụng lên builder trước khi build `GraphQlSource`. Nếu một customizer phụ thuộc customizer khác, hãy thể hiện thứ tự bằng `@Order` hoặc `Ordered`.

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.core.annotation.Order;

@Bean
@Order(10)
GraphQlSourceBuilderCustomizer scalarCustomizer() {
    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.scalar(ExtendedScalars.DateTime)
    );
}

@Bean
@Order(20)
GraphQlSourceBuilderCustomizer inspectionCustomizer() {
    return builder -> builder.inspectSchemaMappings(report ->
            logger.info("Schema report: {}", report)
    );
}
~~~

Các customizer nên độc lập nếu có thể. `@Order` chỉ nên dùng khi thứ tự thực sự có ý nghĩa; nó không giải quyết xung đột nếu hai callback cùng đăng ký hoặc ghi đè một scalar/data fetcher. Với các bean `RuntimeWiringConfigurer` riêng, cũng cần xác định rõ thứ tự và tránh phụ thuộc ngầm vào thứ tự đăng ký.

Nếu một cấu hình được đăng ký cả dưới dạng `RuntimeWiringConfigurer` bean và trong customizer, hãy kiểm tra xem có bị lặp hay không. Spring Boot đã thu thập các bean configurer theo cơ chế auto-configuration; không cần tự đăng ký lại chúng trong customizer trừ khi bạn đang chủ động kiểm soát source builder.

## 10. So sánh RuntimeWiringConfigurer và GraphQlSourceBuilderCustomizer

Hai extension point có thể cùng tác động đến runtime wiring, nhưng phạm vi và mục đích khác nhau:

| Tiêu chí | `RuntimeWiringConfigurer` | `GraphQlSourceBuilderCustomizer` |
| --- | --- | --- |
| Mục tiêu | Cấu hình `RuntimeWiring.Builder` | Tùy chỉnh `GraphQlSource` builder |
| Phạm vi | Scalar, data fetcher, directive, type resolver | Runtime wiring cùng schema factory, instrumentation, GraphQL builder, schema inspection và cấu hình khác |
| Độ tập trung | Chỉ tập trung vào wiring | Tập trung vào quá trình tạo GraphQlSource |
| Khi nên dùng | Cần đăng ký resolver hoặc scalar | Cần kết hợp nhiều vùng cấu hình của GraphQlSource |
| Với Boot starter | Khai báo bean để auto-configuration thu thập | Khai báo bean để auto-configuration gọi trong lúc build source |

Ví dụ chỉ đăng ký scalar nên dùng `RuntimeWiringConfigurer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
RuntimeWiringConfigurer dateTimeConfigurer() {
    return wiring -> wiring.scalar(ExtendedScalars.DateTime);
}
~~~

Nếu cùng lúc cần đăng ký scalar và bật schema inspection, có thể dùng customizer:

~~~java
@Bean
GraphQlSourceBuilderCustomizer graphQlSourceCustomizer() {
    return builder -> {
        builder.configureRuntimeWiring(wiring ->
                wiring.scalar(ExtendedScalars.DateTime)
        );
        builder.inspectSchemaMappings(report -> logger.info("{}", report));
    };
}
~~~

Chọn extension point theo phạm vi cấu hình giúp application context dễ hiểu và giảm khả năng một cấu hình bị đăng ký ở nhiều nơi.

## 11. Tương tác với Spring Boot auto-configuration

Spring Boot tạo `GraphQlSource` mặc định khi chưa có bean cùng loại. Khi khai báo `GraphQlSourceBuilderCustomizer`, ứng dụng vẫn để Boot tạo source và customizer được gọi trong quá trình chuẩn bị builder.

Nếu tự khai báo một `GraphQlSource` bean, auto-configuration mặc định có thể lùi lại. Khi đó, customizer dành cho builder của source mặc định không tự động thay thế trách nhiệm cấu hình của source tự tạo. Ứng dụng phải bảo đảm source riêng có đầy đủ schema resource, runtime wiring, controller configurer, scalar, type resolver và các thành phần cần thiết.

Vì vậy, nếu mục tiêu chỉ là thêm runtime wiring, hãy ưu tiên bean `RuntimeWiringConfigurer` hoặc `GraphQlSourceBuilderCustomizer` trong luồng auto-configuration. Chỉ tự tạo `GraphQlSource` khi thật sự cần kiểm soát toàn bộ bước build.

## 12. Kiểm thử customizer

Customizer được chạy lúc application context khởi tạo. Kiểm thử tốt nhất là xác nhận cấu hình cuối cùng có mặt trong schema/runtime và operation thực tế hoạt động.

Ví dụ kiểm tra custom scalar được đăng ký:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.execution.GraphQlSource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GraphQlRuntimeCustomizerTests {

    @Autowired
    GraphQlSource graphQlSource;

    @Test
    void registersDateTimeScalar() {
        assertThat(graphQlSource.schema().getType("DateTime"))
                .isNotNull();
    }
}
~~~

Test cần có `scalar DateTime` trong SDL và bean customizer hoặc configurer đăng ký `ExtendedScalars.DateTime`. Kiểm tra schema chỉ xác nhận type đã tồn tại; nên bổ sung `GraphQlTester` để kiểm tra parse variables, parse literal và serialize response.

Với data fetcher hoặc type resolver, hãy thực thi query chứa field tương ứng và xác nhận kết quả theo concrete type. Khi cần kiểm tra thứ tự customizer, có thể dùng test context với các bean có `@Order` khác nhau và xác minh cấu hình cuối cùng.

Các trường hợp nên có:

1. Customizer được phát hiện và được gọi khi context khởi động.
2. Scalar có thể parse input và serialize output.
3. Interface hoặc union được resolve thành đúng GraphQL object type.
4. Data fetcher tùy chỉnh được gọi cho đúng field.
5. Schema inspection phát hiện mapping sai như mong đợi.
6. Nhiều customizer chạy theo thứ tự đã khai báo.
7. Khi có `GraphQlSource` bean riêng, source vẫn có đủ wiring cần thiết.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Customizer không được gọi | Bean không nằm trong application context hoặc dùng sai package Boot | Kiểm tra component scan, `@Bean` và package theo Boot version |
| Scalar có trong SDL nhưng không hoạt động | Chưa đăng ký `GraphQLScalarType` | Thêm implementation qua runtime wiring |
| Interface/union không resolve được | Chưa có type resolver phù hợp | Cấu hình `TypeResolver` và mapping concrete class |
| Resolver annotation không chạy | Controller configurer không có trong runtime wiring | Kiểm tra `AnnotatedControllerConfigurer` và các configurer Boot đã áp dụng |
| Field có hai data fetcher | Cùng field được đăng ký bằng annotation và wiring thủ công | Chỉ định một nơi sở hữu mapping |
| Cấu hình bị ghi đè | Nhiều configurer/customizer cùng sửa một type hoặc field | Loại bỏ registration trùng và khai báo thứ tự rõ ràng |
| Builder method không tồn tại | Phiên bản Spring for GraphQL không hỗ trợ API đang dùng | Kiểm tra dependency management và Javadoc đúng phiên bản |
| Customizer không tác động source tự tạo | Ứng dụng đã thay thế `GraphQlSource` auto-configured | Chuyển cấu hình vào builder của source riêng hoặc dùng auto-configuration |

Khi điều tra, hãy kiểm tra application context có bean customizer hay không, tiếp theo kiểm tra callback có được gọi, sau đó xác minh `GraphQlSource` và operation thực tế. Cách này phân biệt được lỗi đăng ký bean, lỗi builder và lỗi thực thi field.

## 14. Quy trình áp dụng GraphQlSourceBuilderCustomizer

Khi cần tùy chỉnh GraphQL runtime trong Spring Boot:

1. Xác định cấu hình thuộc runtime wiring hay thuộc toàn bộ `GraphQlSource` builder.
2. Nếu chỉ cần scalar, data fetcher, directive hoặc type resolver, cân nhắc `RuntimeWiringConfigurer` trước.
3. Nếu cần kết hợp wiring với schema inspection, instrumentation hoặc GraphQL builder, khai báo `GraphQlSourceBuilderCustomizer` bean.
4. Dùng package tương ứng với Spring Boot 3.x hoặc 4.x.
5. Tránh đăng ký cùng scalar hoặc data fetcher ở nhiều extension point.
6. Khai báo `@Order` nếu các customizer có phụ thuộc thứ tự.
7. Kiểm thử schema/runtime cuối cùng bằng `GraphQlSource` và thực thi operation bằng `GraphQlTester`.

`GraphQlSourceBuilderCustomizer` giúp mở rộng bước tạo GraphQL runtime mà vẫn giữ Spring Boot quản lý vòng đời `GraphQlSource`. Khi dùng đúng phạm vi và phối hợp rõ ràng với `RuntimeWiringConfigurer`, ứng dụng có thể cấu hình schema và resolver tập trung mà không làm controller hoặc service phụ thuộc vào chi tiết khởi tạo GraphQL.

## Tài liệu tham khảo

- [Spring Boot 3.5 — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/graphql/GraphQlSourceBuilderCustomizer.html)
- [Spring Boot 4.x — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlSourceBuilderCustomizer.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [GraphQL Java — Runtime Wiring](https://www.graphql-java.com/documentation/schema/)
