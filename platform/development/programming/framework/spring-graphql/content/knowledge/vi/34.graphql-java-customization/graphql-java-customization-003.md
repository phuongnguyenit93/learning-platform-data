# Instrumentation chain trong Spring for GraphQL

GraphQL Java cung cấp **Instrumentation** như một điểm mở rộng để quan sát và điều chỉnh vòng đời xử lý GraphQL operation. Một instrumentation có thể đo thời gian request, ghi nhận lỗi, theo dõi việc gọi DataFetcher, kiểm tra query trước khi chạy hoặc bổ sung metadata vào kết quả.

Trong ứng dụng thực tế, thường có nhiều nhu cầu cùng lúc: metrics, tracing, audit, giới hạn độ phức tạp query và quy tắc kiểm tra riêng. **Instrumentation chain** cho phép kết hợp nhiều instrumentation theo một thứ tự xác định thay vì viết tất cả vào một class lớn.

Spring for GraphQL tích hợp cơ chế này qua **GraphQlSource.Builder**. Với Spring Boot GraphQL starter, có thể khai báo từng instrumentation thành bean; Boot tự thu thập các bean theo thứ tự Spring và đăng ký chúng khi xây dựng GraphQlSource.

## 1. Instrumentation nằm ở đâu trong vòng đời GraphQL?

Một request đi qua transport trước khi tới GraphQL Java:

~~~mermaid
flowchart TD
    A[HTTP / WebSocket / RSocket request] --> B[Transport handler]
    B --> C[WebGraphQlInterceptor chain]
    C --> D[ExecutionGraphQlService]
    D --> E[GraphQL Java]
    E --> F[Parse document]
    F --> G[Validate document]
    G --> H[Execute operation]
    H --> I[Resolve fields / DataFetcher]
    I --> J[Build ExecutionResult]
    J --> K[Transport response]
~~~

**WebGraphQlInterceptor** hoạt động ở tầng Spring transport, có thể đọc headers, bổ sung GraphQLContext hoặc xử lý request/response trước khi gửi qua transport.

**Instrumentation** hoạt động bên trong GraphQL Java. Nó có thể quan sát các giai đoạn parse, validation, execution, field fetching và kết quả thực thi. Vì vậy, instrumentation phù hợp với các nhu cầu gắn trực tiếp vào GraphQL engine như đo thời gian resolver, giới hạn query depth hoặc bổ sung execution metadata.

Một số extension point khác có phạm vi riêng:

| Extension point | Phạm vi | Dùng khi |
| --- | --- | --- |
| WebGraphQlInterceptor | Request/response ở tầng Spring transport | Authentication context, HTTP headers, correlation ID, biến đổi response ở tầng web. |
| Instrumentation | Vòng đời GraphQL Java execution | Metrics, tracing, query validation, theo dõi field fetch, sửa execution result. |
| RuntimeWiringConfigurer | Khởi tạo schema và runtime wiring | Đăng ký scalar, directive, DataFetcher hoặc wiring factory. |
| DataFetcherExceptionResolver | Exception phát sinh trong DataFetcher | Ánh xạ exception thành GraphQL errors. |
| GraphQlSourceBuilderCustomizer | Tùy biến GraphQlSource builder trong Spring Boot | Cấu hình GraphQL Java builder hoặc schema builder nâng cao. |

Không dùng instrumentation thay thế authentication hoặc authorization trong service. Instrumentation có thể quan sát hay bọc DataFetcher, nhưng kiểm tra quyền truy cập tài nguyên vẫn nên được thực hiện ở security layer, service hoặc resolver có trách nhiệm nghiệp vụ.

## 2. Instrumentation có thể quan sát những bước nào?

GraphQL Java định nghĩa nhiều hook trong interface **Instrumentation**. Một instrumentation chỉ cần override các hook liên quan đến mục tiêu của nó; các hook còn lại có implementation mặc định.

| Hook | Thời điểm | Ví dụ mục đích |
| --- | --- | --- |
| createState | Bắt đầu một lần execution | Tạo state riêng cho request. |
| beginExecution | Bắt đầu execution | Đo tổng thời gian GraphQL execution. |
| beginParse | Trước khi parse document | Theo dõi thời gian parse hoặc parse failure. |
| beginValidation | Trước khi validate document | Theo dõi validation hoặc áp dụng kiểm tra bổ sung. |
| instrumentDocumentAndVariables | Trước khi document và variables được dùng | Điều chỉnh document/variables khi có lý do rõ ràng. |
| beginExecutionStrategy | Mỗi lần execution strategy được gọi | Quan sát các nhánh xử lý field. |
| beginFieldExecution | Trước khi field được thực thi | Đo thời gian field execution. |
| beginFieldFetching | Trước khi DataFetcher lấy giá trị | Quan sát việc fetch dữ liệu. |
| instrumentDataFetcher | Trước khi DataFetcher được sử dụng | Bọc DataFetcher để thêm hành vi quan sát hoặc điều chỉnh. |
| instrumentExecutionResult | Khi đã có ExecutionResult | Bổ sung hoặc biến đổi metadata kết quả. |

Một request có thể gọi hook nhiều lần. Ví dụ, beginExecutionStrategy được gọi khi GraphQL Java đi qua các execution strategy; beginFieldFetching có thể chạy cho nhiều field và nhiều phần tử list.

Instrumentation nên chỉ làm công việc cần thiết. Một hook ở cấp field có thể chạy hàng chục hoặc hàng trăm lần trong một request lớn.

## 3. Ba thành phần quan trọng của Instrumentation

### Instrumentation

**Instrumentation** là contract chính mà GraphQL Java gọi trong vòng đời operation. Có thể triển khai trực tiếp interface này, nhưng thường nên kế thừa **SimplePerformantInstrumentation** để chỉ override các hook cần thiết.

SimplePerformantInstrumentation cung cấp các implementation mặc định nhẹ cho những hook không được sử dụng. Trong các ví dụ hiện đại, nên ưu tiên lớp này thay vì SimpleInstrumentation đã bị deprecated trong các phiên bản GraphQL Java mới.

### InstrumentationContext

Các hook dạng begin thường trả về một **InstrumentationContext**. GraphQL Java gọi callback của context khi bước tương ứng hoàn tất.

Hai callback quan trọng:

- onDispatched: bước bất đồng bộ đã được dispatch.
- onCompleted: bước hoàn tất, kèm kết quả hoặc Throwable nếu có lỗi.

Điều này cho phép đo thời gian mà không cần giữ thread đang xử lý request. Callback hoàn tất có thể được gọi trên thread khác với thread bắt đầu.

### InstrumentationState

**InstrumentationState** chứa dữ liệu riêng của một lần GraphQL execution. Ví dụ có thể lưu thời điểm bắt đầu, số field fetch hoặc thông tin thống kê của request.

Không nên lưu state của request trong static field hoặc instance field dùng chung cho mọi request. GraphQL Java có thể thực thi các field song song, vì vậy state dùng trong một request cần được quản lý theo execution và an toàn khi nhiều thread truy cập.

## 4. Viết instrumentation đo thời gian execution

Ví dụ dưới đây đo thời gian từ lúc GraphQL execution bắt đầu đến khi hoàn tất. Nó ghi nhận request có lỗi hay không mà không log query hoặc variables:

~~~java
import graphql.ExecutionResult;
import graphql.execution.instrumentation.InstrumentationContext;
import graphql.execution.instrumentation.InstrumentationState;
import graphql.execution.instrumentation.SimpleInstrumentationContext;
import graphql.execution.instrumentation.SimplePerformantInstrumentation;
import graphql.execution.instrumentation.parameters.InstrumentationExecutionParameters;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RequestTimingInstrumentation extends SimplePerformantInstrumentation {

    private static final Logger log =
            LoggerFactory.getLogger(RequestTimingInstrumentation.class);

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        long startedAt = System.nanoTime();

        return new SimpleInstrumentationContext<>() {
            @Override
            public void onCompleted(ExecutionResult result, Throwable throwable) {
                long elapsedNanos = System.nanoTime() - startedAt;

                boolean failed = throwable != null
                        || (result != null && !result.getErrors().isEmpty());

                log.debug(
                        "GraphQL execution completed in {} ns, failed={}",
                        elapsedNanos,
                        failed);
            }
        };
    }
}
~~~

Ở ví dụ này:

- beginExecution được gọi khi GraphQL execution bắt đầu.
- System.nanoTime dùng để đo khoảng thời gian đã trôi qua; không dùng currentTimeMillis để đo duration.
- SimpleInstrumentationContext nhận callback khi execution hoàn tất.
- Throwable cho biết lỗi ở bước execution; ExecutionResult có thể chứa GraphQL errors dù không có Throwable.
- Không ghi query, variables, authorization header hoặc dữ liệu nghiệp vụ vào log.

Đây là instrumentation ở cấp toàn request. Nếu cần biết field nào chậm, có thể override hook ở cấp field fetch, nhưng cần cân nhắc chi phí vì số callback tăng theo số field được resolve.

## 5. Ghép nhiều instrumentation bằng ChainedInstrumentation

GraphQL Java cung cấp **ChainedInstrumentation** để ghép nhiều implementation. Constructor nhận một List hoặc danh sách varargs và gọi các instrumentation theo thứ tự được cung cấp.

Ví dụ tạo chain trực tiếp với GraphQL Java:

~~~java
import graphql.GraphQL;
import graphql.execution.instrumentation.ChainedInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

import java.util.List;

Instrumentation chain = new ChainedInstrumentation(List.of(
        new RequestTimingInstrumentation(),
        new QueryAuditInstrumentation(),
        new QueryLimitInstrumentation()
));

GraphQL graphQL = GraphQL.newGraphQL(schema)
        .instrumentation(chain)
        .build();
~~~

Ví dụ giả định QueryAuditInstrumentation và QueryLimitInstrumentation là các implementation do ứng dụng cung cấp.

Thứ tự trong list được bảo đảm. Khi một hook được gọi, các instrumentation trong chain được gọi theo thứ tự đó. State do từng instrumentation tạo ra được chuyển lại cho đúng instrumentation tương ứng; mỗi component vẫn quản lý state riêng của mình.

Có thể hình dung:

~~~mermaid
flowchart TD
    A[GraphQL execution] --> B[RequestTimingInstrumentation]
    B --> C[QueryAuditInstrumentation]
    C --> D[QueryLimitInstrumentation]
    D --> E[GraphQL engine tiếp tục]
    E --> F[InstrumentationContext callbacks]
~~~

Không nên mặc định thứ tự callback hoàn tất phải giống thứ tự bắt đầu ở mọi hook. Hãy dựa vào contract callback của từng hook và kiểm thử chain nếu một instrumentation phụ thuộc kết quả do instrumentation khác tạo ra.

## 6. Đăng ký Instrumentation trong Spring Boot

Với Spring Boot GraphQL starter, có thể khai báo từng instrumentation như một bean:

~~~java
import graphql.execution.instrumentation.Instrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class GraphQlInstrumentationConfiguration {

    @Bean
    @Order(10)
    Instrumentation requestTimingInstrumentation() {
        return new RequestTimingInstrumentation();
    }

    @Bean
    @Order(20)
    Instrumentation queryAuditInstrumentation() {
        return new QueryAuditInstrumentation();
    }

    @Bean
    @Order(30)
    Instrumentation queryLimitInstrumentation() {
        return new QueryLimitInstrumentation();
    }
}
~~~

Spring Boot GraphQL starter tự phát hiện các bean kiểu **Instrumentation** và đưa chúng vào **GraphQlSource.Builder**. Các bean được lấy theo thứ tự Spring, vì vậy có thể dùng @Order hoặc Ordered để kiểm soát thứ tự.

Với cách này:

- Không cần tự tạo GraphQL instance.
- Không cần khai báo một bean ChainedInstrumentation bao quanh các instrumentation component.
- Mỗi instrumentation là một bean độc lập, dễ kiểm thử và thay thế.
- Spring Boot tích hợp các instrumentation đó khi tạo GraphQlSource.

Nếu ứng dụng đã tự khai báo GraphQlSource bean, auto-configuration mặc định có thể không còn tạo GraphQlSource nữa. Khi đó ứng dụng phải tự đăng ký instrumentation vào builder của mình.

## 7. Đăng ký bằng GraphQlSource.Builder khi không dùng Boot auto-configuration

Spring for GraphQL cung cấp method **instrumentation(List<Instrumentation>)** trên GraphQlSource.Builder.

Ví dụ tự tạo GraphQlSource:

~~~java
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

import java.util.List;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .instrumentation(List.of(
                new RequestTimingInstrumentation(),
                new QueryAuditInstrumentation(),
                new QueryLimitInstrumentation()))
        .build();
~~~

Đoạn code minh họa phần cấu hình instrumentation; trong ứng dụng thực tế cần thêm RuntimeWiringConfigurer, exception resolvers và các cấu hình schema khác nếu có.

Nếu muốn làm việc trực tiếp với GraphQL Java Builder, có thể dùng configureGraphQl:

~~~java
builder.configureGraphQl(graphQLBuilder ->
        graphQLBuilder.instrumentation(
                new ChainedInstrumentation(List.of(
                        new RequestTimingInstrumentation(),
                        new QueryAuditInstrumentation()))));
~~~

Chọn một cách đăng ký phù hợp với cách tạo GraphQlSource của ứng dụng. Không thêm cùng một instrumentation vừa qua danh sách instrumentation của GraphQlSource.Builder, vừa qua một ChainedInstrumentation tùy chỉnh nếu điều đó khiến component bị chạy hai lần.

## 8. Thứ tự trong chain ảnh hưởng điều gì?

Thứ tự quan trọng khi các instrumentation cùng quan sát hoặc điều chỉnh execution.

Ví dụ:

| Thứ tự | Instrumentation | Mục tiêu |
| --- | --- | --- |
| 1 | RequestTimingInstrumentation | Bắt đầu đo thời gian tổng request. |
| 2 | QueryAuditInstrumentation | Ghi nhận metadata an toàn của operation. |
| 3 | QueryLimitInstrumentation | Kiểm tra giới hạn query trước khi resolver thực thi. |
| 4 | GraphQL engine | Tiếp tục execution nếu request được chấp nhận. |

Các nguyên tắc khi sắp xếp:

- Đặt các kiểm tra cần từ chối request trước khi công việc tốn tài nguyên bắt đầu.
- Đặt instrumentation đo thời gian ở vị trí bao phủ toàn bộ phạm vi cần đo.
- Nếu instrumentation sửa GraphQL document hoặc variables, cần hiểu component phía sau sẽ nhận dữ liệu đã sửa.
- Không dựa vào thứ tự mặc định của bean discovery; khai báo @Order khi thứ tự có ý nghĩa.
- Không tạo vòng phụ thuộc giữa các instrumentation thông qua shared mutable state.

Instrumentation chain không phải một pipeline message broker. Các component được gọi qua các hook GraphQL Java; mỗi hook có lifecycle riêng và có thể được gọi nhiều lần.

## 9. Dùng instrumentation có sẵn để giới hạn query

GraphQL Java có một số instrumentation hữu ích cho validation và giới hạn tài nguyên:

| Instrumentation | Mục đích |
| --- | --- |
| FieldValidationInstrumentation | Kiểm tra field và arguments trước khi query được thực thi. |
| MaxQueryDepthInstrumentation | Từ chối query vượt độ sâu tối đa. |
| MaxQueryComplexityInstrumentation | Từ chối query vượt giới hạn complexity được tính. |

Ví dụ GraphQL Java:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.ChainedInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

import java.util.List;

Instrumentation queryProtection = new ChainedInstrumentation(List.of(
        new MaxQueryDepthInstrumentation(8),
        new MaxQueryComplexityInstrumentation(200)));
~~~

Giới hạn độ sâu và complexity cần được hiệu chỉnh dựa trên schema và chi phí thực tế của DataFetcher. Một field có thể rất tốn kém dù query nông; ngược lại, một query sâu nhưng chỉ đọc dữ liệu nhẹ có thể không quá tốn tài nguyên.

Nếu ứng dụng dùng custom complexity calculator, hãy gán trọng số phù hợp cho các field có truy vấn database, gọi dịch vụ ngoài hoặc trả về danh sách lớn. Giới hạn query không thay thế pagination, rate limit, timeout hoặc authorization.

## 10. Tích hợp Micrometer Observation

Spring for GraphQL có **GraphQlObservationInstrumentation** để phát observations cho request và các hoạt động DataFetcher/DataLoader được theo dõi.

Một số observation phổ biến:

| Observation | Phạm vi |
| --- | --- |
| graphql.request | Toàn bộ GraphQL request. |
| graphql.datafetcher | Hoạt động DataFetcher không tầm thường. |
| graphql.dataloader | Hoạt động DataLoader, gồm @BatchMapping và DataLoader đăng ký thủ công. |

Observations chỉ được phát khi ứng dụng có ObservationRegistry phù hợp. Có thể tùy biến metadata thông qua các observation convention tương ứng.

Nếu hệ thống đã sử dụng GraphQlObservationInstrumentation, hãy kiểm tra dữ liệu metrics/traces hiện có trước khi tự viết instrumentation đo cùng một phạm vi. Instrumentation tùy chỉnh nên bổ sung thông tin còn thiếu thay vì tạo metric trùng lặp.

Cẩn thận với cardinality:

- Operation type và outcome thường là low-cardinality tags.
- Operation name, field path hoặc query text có thể có cardinality cao.
- Không đưa variables, token, email, user ID hoặc raw query vào metric tags.
- Chỉ ghi metadata đã được phân loại và phê duyệt.

## 11. Khác biệt giữa Instrumentation và WebGraphQlInterceptor

Hai extension point này thường bị nhầm lẫn vì đều chạy quanh GraphQL request.

| Nhu cầu | Nên dùng |
| --- | --- |
| Đọc HTTP Authorization header | WebGraphQlInterceptor hoặc Spring Security. |
| Đưa tenant ID vào GraphQLContext từ transport | WebGraphQlInterceptor. |
| Đo thời gian GraphQL execution | Instrumentation. |
| Đo thời gian một field DataFetcher | Instrumentation. |
| Kiểm tra query depth/complexity trước execution | Instrumentation phù hợp. |
| Chuyển exception từ resolver thành GraphQL error | DataFetcherExceptionResolver. |
| Đăng ký scalar hoặc directive | RuntimeWiringConfigurer. |
| Thay đổi HTTP response headers | Transport handler/interceptor. |
| Thêm metadata vào ExecutionResult | Instrumentation hoặc cơ chế GraphQL result phù hợp. |

WebGraphQlInterceptor có thể xử lý cả request và response ở tầng Spring. Instrumentation tập trung vào GraphQL Java execution, nên không phải nơi thích hợp để đọc hoặc sửa HTTP response headers.

## 12. Dùng InstrumentationState an toàn khi có xử lý song song

GraphQL Java thường sử dụng AsyncExecutionStrategy để cho phép các field lồng nhau được resolve đồng thời. Vì vậy instrumentation không được giả định tất cả callback đều chạy trên cùng một thread.

Nếu cần đếm số field fetch trong một request, state có thể sử dụng AtomicInteger:

~~~java
import graphql.execution.instrumentation.InstrumentationState;

import java.util.concurrent.atomic.AtomicInteger;

public class RequestInstrumentationState implements InstrumentationState {

    private final AtomicInteger fieldFetchCount = new AtomicInteger();

    public void recordFieldFetch() {
        fieldFetchCount.incrementAndGet();
    }

    public int getFieldFetchCount() {
        return fieldFetchCount.get();
    }
}
~~~

State này phải được tạo cho từng execution, không dùng singleton dùng chung cho mọi request. Khi hook được gọi từ nhiều thread, sử dụng cấu trúc thread-safe hoặc đồng bộ hóa phù hợp.

Không nên:

- Lưu request-specific state vào static mutable field.
- Dùng một HashMap không đồng bộ để nhiều field resolver ghi đồng thời.
- Dựa vào ThreadLocal mà không xử lý việc chuyển thread.
- Chặn thread để chờ một CompletableFuture hoặc Publisher hoàn tất.
- Giữ reference tới DataFetchingEnvironment hoặc request object lâu hơn vòng đời cần thiết.

## 13. Cẩn thận khi bọc DataFetcher

Hook **instrumentDataFetcher** cho phép trả về một DataFetcher khác thay thế DataFetcher ban đầu. Đây là một khả năng mạnh, nhưng cần cẩn trọng.

Một wrapper phải giữ nguyên behavior của DataFetcher gốc:

- Trả lại đúng kết quả hoặc CompletionStage mà resolver tạo ra.
- Không block để chờ future hoàn tất.
- Giữ nguyên exception semantics để DataFetcherExceptionHandler xử lý.
- Không làm mất metadata hoặc context cần thiết.
- Không thực hiện side effect nhiều lần nếu wrapper được tạo hoặc gọi lại.

Ví dụ một wrapper chỉ ghi nhận thời điểm gọi DataFetcher có thể cần xử lý cả synchronous return value, CompletionStage và exception. Với mục tiêu metrics đơn giản, hook beginFieldFetching thường dễ kiểm soát hơn việc viết wrapper tùy chỉnh.

## 14. Instrumentation và GraphQLContext

Instrumentation có thể đọc hoặc bổ sung dữ liệu vào GraphQLContext thông qua các execution parameters. Spring for GraphQL cũng hỗ trợ truyền context từ transport qua GraphQL Java tới DataFetcher.

Ví dụ Spring for GraphQL dùng custom instrumentation để bật chế độ giữ thứ tự event của subscription:

~~~java
import graphql.ExecutionResult;
import graphql.execution.SubscriptionExecutionStrategy;
import graphql.execution.instrumentation.InstrumentationContext;
import graphql.execution.instrumentation.InstrumentationState;
import graphql.execution.instrumentation.SimpleInstrumentationContext;
import graphql.execution.instrumentation.SimplePerformantInstrumentation;
import graphql.execution.instrumentation.parameters.InstrumentationExecutionParameters;

public class SubscriptionOrderInstrumentation extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        parameters.getGraphQLContext().put(
                SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED,
                true);

        return SimpleInstrumentationContext.noOp();
    }
}
~~~

Đây là cấu hình hành vi execution ở GraphQL Java. Nó không tự đảm bảo thứ tự message trên mọi transport hoặc giữa nhiều instance; nó điều khiển cách GraphQL Java xử lý event của subscription trong phạm vi execution.

## 15. Instrumentation không phải nơi thích hợp để giữ transaction dài cho mọi request

Có thể dùng instrumentation để mở transaction trước khi DataFetcher đầu tiên chạy và kết thúc transaction sau khi execution hoàn tất. Tuy nhiên, đây là kỹ thuật nâng cao và có ràng buộc quan trọng.

Với synchronous transaction management, Spring thường dùng ThreadLocal để gắn transaction với thread. Trong khi đó, GraphQL Java thường resolve các field đồng thời bằng AsyncExecutionStrategy và có thể chuyển qua nhiều thread.

Nếu muốn giữ một transaction đồng bộ xuyên suốt toàn bộ GraphQL execution, phải bảo đảm DataFetcher được thực thi tuần tự trên cùng thread, ví dụ dùng AsyncSerialExecutionStrategy. Điều này làm mất lợi ích thực thi song song và có thể ảnh hưởng đáng kể tới throughput.

Vì vậy:

- Ưu tiên transaction ở application service hoặc mutation method.
- Chỉ dùng transactional instrumentation khi thực sự cần transaction scope toàn request.
- Nếu dùng reactive transaction, phải tuân theo Reactor Context và ReactiveTransactionManager; không dựa vào ThreadLocal.
- Đảm bảo commit/rollback và cleanup transaction khi execution hoàn tất, kể cả khi có exception hoặc cancellation.
- Kiểm thử trường hợp nested field lỗi, subscription, timeout và async DataFetcher.

## 16. Kiểm thử Instrumentation chain

Nên kiểm thử riêng từng instrumentation và kiểm thử cả chain.

### Kiểm thử instrumentation đơn lẻ

Với RequestTimingInstrumentation, có thể kiểm tra:

- beginExecution được gọi khi GraphQL execution bắt đầu.
- Callback onCompleted được gọi khi execution hoàn tất.
- Request có GraphQL errors được ghi nhận outcome phù hợp.
- Throwable được xử lý khi execution kết thúc bất thường.
- Instrumentation không làm thay đổi data hoặc errors của response.

### Kiểm thử thứ tự chain

Tạo hai instrumentation test ghi tên hook vào một List thread-safe, sau đó chạy GraphQL operation và xác nhận thứ tự gọi theo danh sách chain.

Nếu kiểm thử callback bất đồng bộ hoặc nhiều field, không dùng ArrayList chia sẻ giữa các thread; dùng synchronized collection hoặc queue thread-safe.

### Kiểm thử tích hợp Spring GraphQL

Có thể dùng GraphQlTester để gửi operation qua ExecutionGraphQlService hoặc transport test:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "book-10") {
                id
                title
            }
        }
        """)
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("book-10");
~~~

Bên cạnh việc xác nhận data đúng, test nên kiểm tra instrumentation đã được đăng ký trong GraphQlSource. Nếu dùng Spring Boot, có thể inject test recorder hoặc mock dependency mà instrumentation sử dụng để xác nhận hook đã chạy.

Các tình huống nên có:

1. Request hợp lệ chạy qua toàn bộ chain.
2. Request parse/validation thất bại.
3. DataFetcher ném exception.
4. Query vượt giới hạn depth hoặc complexity.
5. Nhiều instrumentation cùng được gọi theo thứ tự cấu hình.
6. Nhiều request chạy đồng thời nhưng không chia sẻ state.
7. Subscription tạo nhiều event.
8. Instrumentation không làm mất GraphQLContext hoặc thay đổi response ngoài ý muốn.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Instrumentation không chạy | Chưa đăng ký vào GraphQlSource hoặc GraphQL.Builder | Kiểm tra bean discovery và GraphQlSource.Builder.instrumentation. |
| Instrumentation chạy hai lần | Component được đăng ký qua nhiều cách | Chỉ đăng ký một lần trong GraphQlSource đang sử dụng. |
| Thứ tự hook không đúng mong đợi | Không khai báo @Order hoặc list chain sai thứ tự | Dùng @Order/Ordered hoặc list tường minh. |
| Metrics bị đếm chồng | Vừa dùng GraphQlObservationInstrumentation vừa tạo metric cùng mục tiêu | Kiểm tra observation hiện có và chỉ bổ sung metric còn thiếu. |
| Dữ liệu state lẫn giữa các request | Dùng instance field hoặc static field dùng chung | Tạo state riêng cho từng execution. |
| Race condition khi đếm field | Nhiều DataFetcher chạy song song | Dùng AtomicInteger hoặc cấu trúc thread-safe. |
| Request chậm hơn sau khi thêm chain | Hook thực hiện I/O hoặc blocking | Giữ instrumentation nhẹ, không block và giới hạn log. |
| DataFetcher trả lỗi khác trước | Wrapper làm thay đổi exception/future behavior | Bảo toàn return type và exception semantics. |
| Log chứa query hoặc secret | Ghi raw document/variables trong instrumentation | Chỉ ghi metadata allowlist, tránh payload và credential. |
| Transaction bị treo hoặc sai thread | Dùng transaction đồng bộ xuyên execution bất đồng bộ | Chọn transaction per service hoặc execution strategy tuần tự có kiểm soát. |
| Subscription event đổi thứ tự | Các field event được resolve bất đồng bộ | Cấu hình KEEP_SUBSCRIPTION_EVENTS_ORDERED nếu cần giữ thứ tự trong GraphQL Java. |

## 18. Checklist thiết kế Instrumentation chain

1. Xác định hook cần thiết: request, parse, validation, field fetch hay execution result.
2. Dùng SimplePerformantInstrumentation cho implementation tùy chỉnh thông thường.
3. Dùng InstrumentationContext để xử lý callback hoàn tất bất đồng bộ.
4. Dùng InstrumentationState cho dữ liệu riêng của từng execution.
5. Ghép component bằng ChainedInstrumentation khi cấu hình GraphQL Java trực tiếp.
6. Dùng bean Instrumentation và @Order khi tích hợp Spring Boot.
7. Nếu tự tạo GraphQlSource, đăng ký danh sách bằng GraphQlSource.Builder.instrumentation(...).
8. Tránh đăng ký trùng cùng một component qua nhiều đường.
9. Dùng instrumentation có sẵn cho field validation, query depth và query complexity khi phù hợp.
10. Cân nhắc GraphQlObservationInstrumentation trước khi tự viết metrics/tracing.
11. Không dùng instrumentation thay thế authentication, authorization hoặc DataFetcherExceptionResolver.
12. Bảo đảm thread safety và không block trong callback.
13. Không log raw query, variables, headers hoặc dữ liệu nhạy cảm.
14. Kiểm thử thứ tự chain, lỗi, concurrency, subscription và state isolation.
15. Chỉ dùng transactional instrumentation toàn request khi hiểu rõ execution strategy và transaction context.

Instrumentation chain giúp chia nhỏ các cross-cutting concern của GraphQL Java thành những component độc lập. GraphQL Java cung cấp ChainedInstrumentation để ghép chúng theo thứ tự; Spring Boot giúp đăng ký từng component thông qua bean Instrumentation và GraphQlSource.Builder. Khi chọn đúng hook, quản lý state theo request, giữ callback nhẹ và kiểm thử thứ tự/concurrency, instrumentation có thể bổ sung observability và kiểm soát execution mà không làm rối resolver nghiệp vụ.

Tài liệu tham khảo:
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java — ChainedInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/instrumentation/ChainedInstrumentation.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource.Builder API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.Builder.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Data Integration and Transactional Instrumentation](https://docs.spring.io/spring-graphql/reference/data.html)
