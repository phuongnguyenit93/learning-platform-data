# GraphQlSourceBuilderCustomizer trong Spring Boot Starter

`GraphQlSourceBuilderCustomizer` là extension point của Spring Boot dành cho ứng dụng cần tùy chỉnh quá trình tạo `GraphQlSource`. Spring Boot dùng `GraphQlSource` để cung cấp GraphQL runtime được cấu hình từ schema SDL, runtime wiring và các thành phần thực thi. Khi khai báo một bean `GraphQlSourceBuilderCustomizer`, ứng dụng có thể bổ sung cấu hình vào builder mà vẫn giữ luồng auto-configuration mặc định của starter.

Customizer thường được dùng để đăng ký custom scalar, cấu hình schema inspection, thay đổi cách tạo schema, bổ sung type visitor hoặc điều chỉnh `GraphQL.Builder`. Bài học này giải thích vị trí của customizer trong quá trình khởi tạo, cách viết bean, cách phối hợp với `RuntimeWiringConfigurer` và những điểm cần kiểm tra khi nâng cấp Spring Boot.

## 1. GraphQlSource là gì?

Spring for GraphQL dùng `GraphQlSource` làm abstraction để cung cấp `graphql.GraphQL` instance và `GraphQLSchema` đã được tạo. Schema mô tả cấu trúc API bằng SDL; runtime wiring nối các field trong schema với data fetcher, custom scalar, type resolver và directive tương ứng.

Trong một ứng dụng Spring Boot dùng `spring-boot-starter-graphql`, auto-configuration thường tạo các thành phần cơ sở:

1. Tìm và đọc các file schema `.graphqls` hoặc `.gqls`.
2. Tạo `GraphQlSource` builder và áp dụng cấu hình từ properties.
3. Phát hiện các bean như `RuntimeWiringConfigurer`, `Instrumentation`, `DataFetcherExceptionResolver` và `SubscriptionExceptionResolver`.
4. Áp dụng các `GraphQlSourceBuilderCustomizer` đã được khai báo.
5. Build `GraphQlSource`, sau đó dùng nó để cấu hình `ExecutionGraphQlService`.

~~~mermaid
flowchart TD
    A[Spring Boot application starts] --> B[GraphQlAutoConfiguration]
    B --> C[Load SDL resources]
    C --> D[Create GraphQlSource builder]
    D --> E[Apply GraphQL properties]
    E --> F[Apply RuntimeWiringConfigurer beans]
    F --> G[Apply GraphQlSourceBuilderCustomizer beans]
    G --> H[Build GraphQlSource]
    H --> I[Create ExecutionGraphQlService]
    I --> J[GraphQL requests can be executed]
~~~

Sơ đồ thể hiện luồng khởi tạo khái quát của auto-configuration. Chi tiết bean và thứ tự áp dụng có thể thay đổi theo phiên bản Spring Boot; cần kiểm tra API của phiên bản đang dùng khi dựa vào thứ tự giữa nhiều customizer.

## 2. GraphQlSourceBuilderCustomizer giải quyết vấn đề gì?

Thông thường, ứng dụng chỉ cần khai báo SDL trong `src/main/resources/graphql` và viết controller với `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping`. Spring Boot tự phát hiện controller và đăng ký handler method thành data fetcher.

Một số yêu cầu cần cấu hình sâu hơn, ví dụ:

- Schema dùng scalar `DateTime` hoặc `Money` do ứng dụng định nghĩa.
- Cần thay đổi cách GraphQL Java tạo execution ID hoặc cấu hình `GraphQL.Builder`.
- Muốn bật schema mapping inspection để tìm field chưa có resolver.
- Cần cấu hình `TypeResolver` mặc định cho interface hoặc union.
- Cần thêm `GraphQLTypeVisitor` để kiểm tra hoặc thay đổi code registry sau khi schema được tạo.
- Cần dùng schema factory riêng, ví dụ khi kết hợp schema từ nhiều nguồn hoặc triển khai federation.

`GraphQlSourceBuilderCustomizer` cung cấp quyền truy cập vào builder trong giai đoạn auto-configuration để thực hiện những tùy chỉnh đó. Nó là callback ở thời điểm ứng dụng khởi động, không phải interceptor chạy cho từng GraphQL request.

## 3. Khai báo customizer đầu tiên

Đây là một functional interface, vì vậy có thể triển khai bằng class hoặc lambda. Trong Spring Boot 3.x, package của interface là `org.springframework.boot.autoconfigure.graphql`:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer graphQlSourceBuilderCustomizer() {
        return builder -> {
            // Customize GraphQlSource builder here.
        };
    }
}
~~~

Phương thức `customize(...)` nhận builder mà Spring Boot đang sử dụng để tạo `GraphQlSource`. Ứng dụng chỉ thêm cấu hình cần thiết vào builder này. Không gọi `build()` bên trong customizer, vì Spring Boot còn cần áp dụng các customizer khác trước khi hoàn tất việc tạo `GraphQlSource`.

Với Spring Boot 3.5, kiểu tham số của callback là `GraphQlSource.SchemaResourceBuilder`. Đây là builder đọc các file schema resource và kế thừa các cấu hình chung từ `GraphQlSource.Builder`.

## 4. Đăng ký custom scalar bằng customizer

Một ví dụ dễ gặp là schema cần scalar `DateTime`. GraphQL có các scalar mặc định như `Int`, `Float`, `String`, `Boolean` và `ID`; kiểu ngày giờ không thuộc nhóm scalar mặc định. Ta có thể dùng thư viện GraphQL Java Extended Scalars để cung cấp cách parse và serialize.

### 4.1. Khai báo scalar trong SDL

~~~graphql
scalar DateTime

type Query {
    serverTime: DateTime!
}
~~~

### 4.2. Thêm thư viện Extended Scalars

Thêm dependency `com.graphql-java:graphql-java-extended-scalars` vào project. Nếu project dùng Spring Boot dependency management, nên để BOM quản lý phiên bản tương thích hoặc chọn phiên bản Extended Scalars tương thích với phiên bản GraphQL Java đang được Spring Boot quản lý.

### 4.3. Cấu hình scalar bằng GraphQlSourceBuilderCustomizer

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer dateTimeScalarCustomizer() {
        return builder -> builder.configureRuntimeWiring(runtimeWiring ->
                runtimeWiring.scalar(ExtendedScalars.DateTime)
        );
    }
}
~~~

`configureRuntimeWiring(...)` cho phép cấu hình `RuntimeWiring.Builder`. Lệnh `scalar(...)` đăng ký implementation của scalar để GraphQL Java biết cách chuyển đổi giá trị giữa GraphQL và Java. Tên scalar trong SDL phải khớp với scalar đã đăng ký trong runtime wiring.

Controller có thể trả về kiểu Java mà scalar hỗ trợ, ví dụ `OffsetDateTime` với scalar `DateTime` tương ứng:

~~~java
import java.time.OffsetDateTime;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class TimeController {

    @QueryMapping
    public OffsetDateTime serverTime() {
        return OffsetDateTime.now();
    }
}
~~~

Scalar chịu trách nhiệm serialize giá trị trả về và parse input nếu scalar được dùng làm argument. Nên thống nhất múi giờ và định dạng thời gian trong hợp đồng API; không dựa vào định dạng ngầm định của từng client.

## 5. Các vùng cấu hình có thể truy cập qua builder

Trong Spring for GraphQL 1.2/1.3 và Spring Boot 3.x, customizer nhận `GraphQlSource.SchemaResourceBuilder`. Builder này cung cấp API riêng cho schema resource và kế thừa các API cấu hình chung.

| API | Mục đích |
| --- | --- |
| `schemaResources(...)` | Thêm các schema resource để parse và merge |
| `configureTypeDefinitions(...)` | Bổ sung hoặc điều chỉnh type definition trước khi tạo `GraphQLSchema` |
| `configureRuntimeWiring(...)` | Đăng ký scalar, data fetcher, directive wiring và type resolver |
| `defaultTypeResolver(...)` | Cấu hình type resolver mặc định cho interface và union |
| `inspectSchemaMappings(...)` | Kiểm tra field chưa được map, registration không khớp và một số vấn đề mapping |
| `schemaFactory(...)` | Tự cung cấp cách tạo `GraphQLSchema` từ type definition registry và runtime wiring |
| `configureGraphQl(...)` | Cấu hình `GraphQL.Builder` trước khi tạo GraphQL runtime |
| `instrumentation(...)` | Đăng ký GraphQL Java instrumentation |
| `exceptionResolvers(...)` | Bổ sung resolver xử lý exception của data fetcher |
| `subscriptionExceptionResolvers(...)` | Bổ sung resolver xử lý lỗi của subscription publisher |
| `typeVisitors(...)` | Duyệt schema để điều chỉnh `GraphQLCodeRegistry` |
| `typeVisitorsToTransformSchema(...)` | Dùng visitor có khả năng biến đổi chính schema |

Không phải ứng dụng nào cũng cần dùng tất cả API. Hãy chọn điểm mở rộng gần nhất với yêu cầu. Ví dụ, đăng ký custom scalar nên thực hiện qua `configureRuntimeWiring`; thay đổi execution ID nên dùng `configureGraphQl`; kiểm tra resolver đã map đầy đủ nên dùng `inspectSchemaMappings`.

### 5.1. Bật schema mapping inspection

Khi schema phát triển, một field có thể được khai báo trong SDL nhưng chưa có resolver hoặc một data fetcher có thể đăng ký nhầm tên field. Schema inspection giúp phát hiện những tình huống này trong lúc khởi động.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlInspectionConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlInspectionConfiguration.class);

    @Bean
    GraphQlSourceBuilderCustomizer schemaInspectionCustomizer() {
        return builder -> builder.inspectSchemaMappings(
                report -> log.info("GraphQL schema mapping report: {}", report)
        );
    }
}
~~~

Schema inspection được bổ sung trong Spring for GraphQL 1.2. Báo cáo có thể giúp tìm unmapped fields, data fetcher registration không tồn tại trong schema, argument không khớp và một số khác biệt nullability có thể phát hiện từ chữ ký Java. Đây là công cụ kiểm tra mapping, không thay thế kiểm thử nghiệp vụ hoặc kiểm thử quyền truy cập.

### 5.2. Cấu hình GraphQL Java runtime

`configureGraphQl(...)` cho phép truy cập `graphql.GraphQL.Builder`. Chẳng hạn, có thể cấu hình execution ID provider để mỗi lần thực thi có mã định danh theo quy tắc của hệ thống:

~~~java
@Bean
GraphQlSourceBuilderCustomizer executionIdCustomizer(
        CustomExecutionIdProvider executionIdProvider
) {
    return builder -> builder.configureGraphQl(graphQlBuilder ->
            graphQlBuilder.executionIdProvider(executionIdProvider)
    );
}
~~~

`CustomExecutionIdProvider` trong ví dụ là implementation do ứng dụng cung cấp theo interface `graphql.execution.ExecutionIdProvider`. Việc có execution ID riêng hữu ích khi liên kết log, trace và metric của cùng một GraphQL operation. Không nên đưa dữ liệu cá nhân hoặc bí mật vào execution ID.

### 5.3. Phân biệt type visitor và schema transformation

`typeVisitors(...)` dùng `SchemaTraverser` để duyệt các thành phần của schema và điều chỉnh `GraphQLCodeRegistry`; visitor theo cách này không thay đổi cấu trúc schema.

`typeVisitorsToTransformSchema(...)` dùng cơ chế transformation, cho phép thay đổi chính `GraphQLSchema`. Việc transformation tốn chi phí cao hơn nên chỉ dùng khi thật sự cần thay đổi cấu trúc schema. Nếu mục tiêu chỉ là gắn hoặc thay đổi data fetcher, hãy cân nhắc runtime wiring hoặc type visitor thông thường trước.

## 6. GraphQlSourceBuilderCustomizer và RuntimeWiringConfigurer

Hai extension point này có liên quan nhưng phạm vi khác nhau. Cả hai đều được Spring Boot phát hiện trong quá trình cấu hình GraphQL, tuy nhiên chúng phục vụ hai mức tùy chỉnh khác nhau.

| Tiêu chí | `RuntimeWiringConfigurer` | `GraphQlSourceBuilderCustomizer` |
| --- | --- | --- |
| Phạm vi | Cấu hình `RuntimeWiring.Builder` | Cấu hình `GraphQlSource.SchemaResourceBuilder` và các builder API kế thừa |
| Dùng cho | Scalar, directive, type resolver, data fetcher | Runtime wiring và các tùy chỉnh rộng hơn như schema factory, schema inspection, instrumentation, GraphQL builder, type visitor |
| Mức độ tập trung | Hẹp, đúng vào runtime wiring | Rộng, bao quát quá trình tạo GraphQlSource |
| Khi nên chọn | Chỉ cần thêm wiring | Cần điều chỉnh quá trình tạo GraphQL source hoặc nhiều khía cạnh của runtime |

Ví dụ chỉ cần đăng ký scalar thì có thể dùng `RuntimeWiringConfigurer`:

~~~java
@Bean
RuntimeWiringConfigurer dateTimeRuntimeWiringConfigurer() {
    return runtimeWiring -> runtimeWiring.scalar(ExtendedScalars.DateTime);
}
~~~

Nếu cần kết hợp scalar với schema inspection hoặc cấu hình GraphQL runtime trong cùng một callback, có thể dùng `GraphQlSourceBuilderCustomizer`. Không nên tạo customizer chỉ để bọc lại một `RuntimeWiringConfigurer` mà không có nhu cầu cấu hình builder rộng hơn.

## 7. Thứ tự thực thi và nhiều customizer

Một ứng dụng có thể khai báo nhiều `GraphQlSourceBuilderCustomizer`. Spring Boot thu thập các bean này theo thứ tự của Spring và áp dụng từng customizer lên builder trước khi hoàn thành `GraphQlSource`.

Khi một tùy chỉnh phụ thuộc vào tùy chỉnh khác, hãy khai báo thứ tự rõ ràng bằng `@Order` hoặc implement `Ordered`:

~~~java
import org.springframework.core.annotation.Order;

@Bean
@Order(10)
GraphQlSourceBuilderCustomizer scalarCustomizer() {
    return builder -> builder.configureRuntimeWiring(runtimeWiring ->
            runtimeWiring.scalar(ExtendedScalars.DateTime)
    );
}

@Bean
@Order(20)
GraphQlSourceBuilderCustomizer inspectionCustomizer() {
    return builder -> builder.inspectSchemaMappings(report ->
            log.info("GraphQL schema mapping report: {}", report)
    );
}
~~~

Các customizer thường được thiết kế độc lập để không phụ thuộc vào thứ tự nếu không cần thiết. `@Order` giúp thể hiện thứ tự khi có phụ thuộc, nhưng không nên dùng nó để che giấu việc nhiều customizer đang ghi đè cùng một cấu hình.

Không nên sửa builder từ một thread khác hoặc lưu builder để tiếp tục thay đổi sau khi callback kết thúc. Đây là builder trong quá trình khởi tạo; hãy hoàn tất các thay đổi đồng bộ trong `customize(...)` để Spring Boot có thể build source nhất quán.

## 8. Cấu hình nào nên dùng properties, bean hay customizer?

Không phải thay đổi nào cũng cần `GraphQlSourceBuilderCustomizer`. Spring Boot đã cung cấp nhiều properties và bean extension point chuyên biệt:

| Nhu cầu | Cách cấu hình nên xem xét đầu tiên |
| --- | --- |
| Đổi vị trí schema | `spring.graphql.schema.locations` |
| Đổi extension của schema file | `spring.graphql.schema.file-extensions` |
| Đăng ký custom scalar hoặc directive | `RuntimeWiringConfigurer` |
| Tự xử lý lỗi data fetcher | `DataFetcherExceptionResolver` bean |
| Xử lý lỗi từ subscription publisher | `SubscriptionExceptionResolver` bean |
| Thêm GraphQL Java instrumentation | `Instrumentation` bean hoặc customizer nếu cần cấu hình kết hợp |
| Tùy chỉnh GraphQL builder hoặc schema factory | `GraphQlSourceBuilderCustomizer` |
| Thay thế hoàn toàn nguồn GraphQL | Tự khai báo `GraphQlSource` bean và chịu trách nhiệm cấu hình đầy đủ |

Boot starter mặc định tìm schema `.graphqls` và `.gqls` dưới `classpath:graphql/**`, thường tương ứng với `src/main/resources/graphql`. Nếu chỉ cần đổi vị trí, dùng property sẽ dễ đọc và dễ quản lý theo môi trường hơn so với viết customizer.

## 9. Tương tác với Spring Boot auto-configuration

`GraphQlSourceBuilderCustomizer` được tiêu thụ bởi auto-configuration tạo `GraphQlSource`. Trong cấu hình mặc định, Spring Boot tạo builder, nạp schema resources, áp dụng properties, phát hiện các bean wiring và instrumentation, sau đó gọi customizer.

Bean `GraphQlSource` mặc định được tạo theo điều kiện thiếu bean cùng loại. Nếu ứng dụng tự khai báo một `GraphQlSource` bean, auto-configuration có thể lùi lại và không tạo source mặc định. Khi đó, customizer dành cho builder của auto-configuration không còn là nơi điều chỉnh source do ứng dụng tự tạo. Cần chuyển cấu hình cần thiết vào nơi tạo `GraphQlSource` của chính ứng dụng.

Điều này đặc biệt quan trọng khi chuyển từ auto-configuration sang cấu hình thủ công. Nếu một customizer đã đăng ký nhưng không thấy tác động, hãy kiểm tra:

1. Ứng dụng có đang dùng `spring-boot-starter-graphql` phù hợp không?
2. Schema có được phát hiện để GraphQL auto-configuration được kích hoạt không?
3. Có bean `GraphQlSource` tự định nghĩa khiến auto-configuration mặc định lùi lại không?
4. Customizer có nằm trong component scan hoặc được import vào application context không?
5. Có lỗi khi parse SDL hoặc validate schema khiến việc tạo source thất bại trước khi ứng dụng sẵn sàng không?
6. Customizer có chạy đúng thứ tự và có customizer khác ghi đè cấu hình hay không?

## 10. Khác biệt package giữa Spring Boot 3 và Spring Boot 4

Khi nâng cấp Spring Boot, cần chú ý package của `GraphQlSourceBuilderCustomizer` đã thay đổi trong Spring Boot 4. API callback vẫn nhận `GraphQlSource.SchemaResourceBuilder`, nhưng import khác nhau:

| Phiên bản | Package |
| --- | --- |
| Spring Boot 3.x | `org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer` |
| Spring Boot 4.x | `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer` |

Ví dụ trong các phần trên dùng package Spring Boot 3.x. Với Spring Boot 4.x, thay import bằng package mới. Không nên copy package của Boot 3 vào project Boot 4 hoặc ngược lại. Đồng thời kiểm tra phiên bản Spring for GraphQL đi kèm để xác nhận các method builder như `inspectSchemaMappings` hoặc `typeVisitorsToTransformSchema` có sẵn trong dependency thực tế.

## 11. Kiểm thử customizer

Customizer chạy trong giai đoạn khởi tạo application context, vì vậy cần kiểm tra rằng cấu hình của nó thực sự xuất hiện trong `GraphQlSource` được Spring Boot tạo ra.

Ví dụ kiểm tra custom scalar đã được đăng ký:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.execution.GraphQlSource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GraphQlSourceCustomizerTests {

    @Autowired
    GraphQlSource graphQlSource;

    @Test
    void registersDateTimeScalar() {
        assertThat(graphQlSource.schema().getType("DateTime"))
                .isNotNull();
    }
}
~~~

Test cần có schema khai báo `scalar DateTime` và dependency Extended Scalars trong test application context. Kiểm tra schema chỉ xác nhận kiểu đã được đăng ký. Để xác nhận parse và serialize, nên thực hiện thêm GraphQL operation có argument hoặc field trả về `DateTime` bằng `GraphQlTester`.

Các trường hợp nên kiểm thử:

1. Customizer được Spring phát hiện và được gọi khi khởi tạo context.
2. Custom scalar, directive hoặc type resolver được đăng ký đúng trong schema runtime.
3. Schema inspection phát hiện mapping không hợp lệ như dự kiến.
4. Các customizer có thứ tự rõ ràng khi cấu hình phụ thuộc lẫn nhau.
5. Khi có `GraphQlSource` bean tự định nghĩa, ứng dụng vẫn cấu hình đầy đủ source theo ý muốn.
6. Schema lỗi hoặc scalar không tương thích khiến context khởi động thất bại với thông báo có thể chẩn đoán.

Không cần kiểm thử riêng lambda chỉ gọi một method builder nếu đã có integration test xác nhận hành vi cấu hình cuối cùng. Tập trung kiểm tra kết quả runtime mà client và resolver thực sự sử dụng.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `GraphQlSourceBuilderCustomizer` không được tìm thấy | Import sai package theo Spring Boot version hoặc thiếu starter | Kiểm tra dependency và package Boot 3/4 |
| SDL báo scalar chưa được khai báo hoặc wiring thiếu | Có `scalar DateTime` nhưng chưa đăng ký scalar implementation | Đăng ký scalar qua `RuntimeWiringConfigurer` hoặc customizer và kiểm tra dependency |
| Customizer không có tác dụng | Ứng dụng đang dùng `GraphQlSource` bean tự định nghĩa | Đưa cấu hình vào builder của source tự tạo hoặc bỏ bean thay thế nếu muốn dùng auto-configuration |
| Schema inspection báo field chưa map | SDL khai báo field nhưng chưa có controller/data fetcher tương ứng | Bổ sung resolver hoặc sửa schema cho đúng hợp đồng |
| Schema khởi động thất bại sau khi thêm customizer | Runtime wiring không tương thích SDL hoặc hai cấu hình xung đột | Kiểm tra schema, scalar, type resolver và thứ tự customizer |
| API builder không tồn tại | Spring for GraphQL version cũ hơn version có API đó | Kiểm tra dependency tree và Javadoc đúng phiên bản |

Khi chẩn đoán, hãy đọc lỗi gốc lúc tạo `GraphQlSource`. Nhiều lỗi schema và runtime wiring được phát hiện ngay lúc application context khởi động, trước khi endpoint nhận request.

## 13. Quy trình áp dụng GraphQlSourceBuilderCustomizer

Khi cần tùy chỉnh GraphQL runtime trong ứng dụng Spring Boot, thực hiện theo các bước:

1. Xác định yêu cầu có thể giải quyết bằng Spring GraphQL properties hoặc một bean extension chuyên biệt hay không.
2. Nếu cần tùy chỉnh rộng hơn quá trình tạo source, khai báo một `GraphQlSourceBuilderCustomizer` bean.
3. Dùng đúng package theo phiên bản Spring Boot; xác nhận method builder có trong phiên bản Spring for GraphQL đang được quản lý.
4. Thực hiện thay đổi trong callback, không gọi `build()` và không giữ builder để thay đổi về sau.
5. Nếu có nhiều customizer phụ thuộc thứ tự, khai báo `@Order` và kiểm thử cấu hình kết hợp.
6. Khởi động application context và kiểm tra `GraphQlSource` hoặc thực thi operation để xác nhận kết quả.

`GraphQlSourceBuilderCustomizer` là điểm mở rộng dành cho những trường hợp cần kiểm soát sâu hơn quá trình tạo GraphQL runtime. Dùng đúng phạm vi của nó giúp ứng dụng tận dụng auto-configuration của Spring Boot, giữ cấu hình tập trung và giảm việc tự tạo lại hạ tầng mà starter đã cung cấp.

## Tài liệu tham khảo

- [Spring Boot 3.5 — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/graphql/GraphQlSourceBuilderCustomizer.html)
- [Spring Boot 4.x — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlSourceBuilderCustomizer.html)
- [Spring for GraphQL — Request Execution và GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQlSource.SchemaResourceBuilder API](https://docs.spring.io/spring-graphql/docs/1.2.x/api/org/springframework/graphql/execution/GraphQlSource.SchemaResourceBuilder.html)
