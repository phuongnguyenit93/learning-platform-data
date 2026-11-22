# ExecutionStrategy trong Spring for GraphQL

GraphQL Java dùng **ExecutionStrategy** để quyết định cách lấy dữ liệu và hoàn tất các field trong một operation. Strategy điều phối việc gọi DataFetcher, chờ kết quả bất đồng bộ, xử lý lỗi và ghép kết quả theo cấu trúc GraphQL.

Ba strategy mặc định có vai trò khác nhau:

- **AsyncExecutionStrategy** cho Query: cho phép các field cùng cấp được thực thi bất đồng bộ và có thể chạy song song.
- **AsyncSerialExecutionStrategy** cho Mutation: thực thi các root field của mutation lần lượt theo thứ tự xuất hiện trong document.
- **SubscriptionExecutionStrategy** cho Subscription: xử lý publisher theo Reactive Streams và tạo một GraphQL response cho từng event.

Spring for GraphQL sử dụng các strategy của GraphQL Java. Khi cần tùy biến, ứng dụng có thể cấu hình qua GraphQlSource hoặc GraphQlSourceBuilderCustomizer. Việc thay strategy phải giữ đúng semantics của từng operation và tiếp tục dùng DataFetcherExceptionHandler do Spring cấu hình để các exception resolver hoạt động như mong đợi.

## 1. ExecutionStrategy là gì?

ExecutionStrategy là thành phần của GraphQL Java chịu trách nhiệm điều phối quá trình thực thi selection set. Một selection set là tập hợp các field client yêu cầu tại một object.

Ví dụ:

~~~graphql
query Dashboard {
    dashboard {
        profile {
            displayName
        }
        notifications {
            id
            message
        }
        recommendations {
            id
            title
        }
    }
}
~~~

GraphQL Java phải giải quyết field dashboard trước để có object cha. Khi object dashboard đã có, các field profile, notifications và recommendations có thể được xử lý theo strategy đang dùng. Khi một field trả về object hoặc list object, engine tiếp tục hoàn tất các field con được chọn.

ExecutionStrategy phối hợp hai công đoạn chính:

1. **Fetch**: gọi DataFetcher của field để lấy giá trị Java.
2. **Complete**: chuyển giá trị đó thành dạng GraphQL phù hợp, chẳng hạn scalar, enum, list hoặc object; với object, engine tiếp tục resolve các field con.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[ExecutionStrategy.execute]
    B --> C[Collect selection set]
    C --> D[Fetch field qua DataFetcher]
    D --> E[Complete field value]
    E --> F{Kiểu kết quả}
    F -->|Scalar / Enum| G[Coerce value]
    F -->|List| H[Complete từng phần tử]
    F -->|Object| I[Resolve selection set con]
    H --> J[Build ExecutionResult]
    G --> J
    I --> J
~~~

ExecutionStrategy không chứa nghiệp vụ đọc database hoặc gọi service. Những việc đó thuộc DataFetcher, controller hoặc application service. Strategy quyết định engine phối hợp các DataFetcher và kết quả của chúng như thế nào.

## 2. Ba strategy mặc định

GraphQL Java sử dụng strategy khác nhau cho từng operation type:

| Operation | Strategy mặc định | Hành vi |
| --- | --- | --- |
| Query | AsyncExecutionStrategy | Các field cùng cấp có thể được dispatch bất đồng bộ; kết quả được ghép theo thứ tự field trong document. |
| Mutation | AsyncSerialExecutionStrategy | Các root field chạy lần lượt; field tiếp theo chỉ được dispatch sau khi field trước hoàn tất. |
| Subscription | SubscriptionExecutionStrategy | DataFetcher của subscription tạo publisher; mỗi event được chuyển thành một GraphQL response. |

Có thể cấu hình trực tiếp trên GraphQL.Builder:

~~~java
import graphql.GraphQL;
import graphql.execution.AsyncExecutionStrategy;
import graphql.execution.AsyncSerialExecutionStrategy;
import graphql.execution.SubscriptionExecutionStrategy;

GraphQL graphQL = GraphQL.newGraphQL(schema)
        .queryExecutionStrategy(new AsyncExecutionStrategy())
        .mutationExecutionStrategy(new AsyncSerialExecutionStrategy())
        .subscriptionExecutionStrategy(new SubscriptionExecutionStrategy())
        .build();
~~~

Đây là các strategy tiêu chuẩn của GraphQL Java và tương ứng với lựa chọn mặc định thông dụng. Trong ứng dụng Spring for GraphQL, thông thường không cần tự tạo GraphQL instance; hãy cấu hình strategy qua GraphQlSource.

## 3. Query: AsyncExecutionStrategy

Query là operation dùng để đọc dữ liệu. Theo GraphQL specification, các field trong một selection set của Query có thể được thực thi theo thứ tự bất kỳ, thường là song song, vì việc resolve field của Query cần không tạo side effect làm thay đổi trạng thái nghiệp vụ.

Giả sử query:

~~~graphql
query {
    dashboard {
        profile {
            displayName
        }
        notifications {
            id
        }
        recommendations {
            id
        }
    }
}
~~~

Field dashboard phải trả về object trước. Sau đó, các field con profile, notifications và recommendations có thể được dispatch mà không phải chờ nhau. Nếu mỗi DataFetcher trả về CompletionStage, GraphQL Java có thể ghép các future để hoàn tất response.

~~~mermaid
flowchart TD
    A[Fetch dashboard] --> B[Dashboard object available]
    B --> C[Fetch profile]
    B --> D[Fetch notifications]
    B --> E[Fetch recommendations]
    C --> F[Wait for all results]
    D --> F
    E --> F
    F --> G[Assemble response in document field order]
~~~

Một điểm dễ nhầm: **thứ tự fetch không nhất thiết là thứ tự xuất hiện trong JSON**. Các DataFetcher có thể hoàn tất theo thứ tự khác nhau, nhưng GraphQL Java vẫn lắp ráp object response theo thứ tự field của document.

### Query không có nghĩa mọi field đều chạy trên thread riêng

AsyncExecutionStrategy cho phép engine phối hợp kết quả bất đồng bộ. Nó không tự biến một DataFetcher blocking thành non-blocking và cũng không có nghĩa mỗi field luôn được chạy trên một thread riêng.

Nếu DataFetcher gọi JDBC blocking trực tiếp rồi mới trả về, lời gọi đó vẫn chiếm thread hiện tại. Muốn có I/O bất đồng bộ, hãy dùng API non-blocking hoặc trả về CompletionStage/Publisher phù hợp với stack ứng dụng.

Không dựa vào việc Query có thể chạy song song để thực hiện các thao tác ghi dữ liệu. Field của Query phải được thiết kế như thao tác đọc, side-effect-free và idempotent.

## 4. Mutation: AsyncSerialExecutionStrategy

GraphQL specification yêu cầu các root field của một Mutation operation được thực thi tuần tự theo thứ tự xuất hiện trong document.

Ví dụ:

~~~graphql
mutation Checkout {
    reserveInventory(orderId: "order-10") {
        reservationId
    }
    chargePayment(orderId: "order-10") {
        paymentId
    }
    confirmOrder(orderId: "order-10") {
        id
        status
    }
}
~~~

GraphQL Java phải hoàn tất reserveInventory trước khi dispatch chargePayment, rồi hoàn tất chargePayment trước khi dispatch confirmOrder.

~~~mermaid
flowchart TD
    A[Mutation operation] --> B[reserveInventory]
    B --> C[Wait for field completion]
    C --> D[chargePayment]
    D --> E[Wait for field completion]
    E --> F[confirmOrder]
    F --> G[Build mutation response]
~~~

AsyncSerialExecutionStrategy vẫn hỗ trợ kết quả bất đồng bộ. Từ Async trong tên strategy không có nghĩa các root mutation field được chạy song song. Nó có nghĩa strategy có thể chờ CompletionStage mà không phải block thread trong lúc chờ; việc dispatch root field tiếp theo vẫn diễn ra tuần tự.

### Phạm vi tuần tự của Mutation

Quy tắc tuần tự áp dụng cho các root field của cùng một Mutation operation. Nó không có nghĩa:

- Tất cả field con trong mọi object đều phải chạy tuần tự.
- Mọi mutation request trên toàn hệ thống đều bị khóa theo một thứ tự chung.
- Các request từ hai client khác nhau được xử lý tuần tự.
- Các root field trong một operation tự động nằm trong cùng database transaction.
- Một mutation operation tự động trở thành một use case atomic ở tầng nghiệp vụ.

Nếu client gửi hai HTTP request mutation đồng thời, server vẫn có thể xử lý chúng song song. Nếu cần bảo vệ dữ liệu trước các request cạnh tranh, hãy dùng transaction, locking, optimistic version hoặc cơ chế đồng bộ phù hợp ở tầng nghiệp vụ.

### Tuần tự không đồng nghĩa atomic

Ví dụ operation có hai root field:

~~~graphql
mutation {
    createOrder(input: { customerId: "c-1" }) {
        id
    }
    reserveInventory(orderId: "order-10") {
        reservationId
    }
}
~~~

Strategy bảo đảm field createOrder được thực thi trước reserveInventory. Nhưng GraphQL không tự mở một database transaction chung cho hai field. Nếu createOrder đã commit rồi reserveInventory thất bại, dữ liệu tạo đơn có thể vẫn tồn tại.

Nếu hai bước phải thành công hoặc rollback cùng nhau, hãy thiết kế một mutation duy nhất gọi application service thực hiện toàn bộ use case trong một transaction.

## 5. Subscription: SubscriptionExecutionStrategy

Subscription khác Query và Mutation ở chỗ DataFetcher của root subscription thường trả về một Publisher thay vì một giá trị đơn.

Ví dụ schema:

~~~graphql
type Subscription {
    orderUpdated(orderId: ID!): OrderEvent!
}

type OrderEvent {
    orderId: ID!
    status: String!
    occurredAt: String!
}
~~~

Controller Spring for GraphQL:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class OrderSubscriptionController {

    private final OrderEventService eventService;

    public OrderSubscriptionController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderUpdated(@Argument String orderId) {
        return eventService.events(orderId);
    }
}
~~~

SubscriptionExecutionStrategy thiết lập subscription source và xử lý các event được phát ra. Mỗi event object được hoàn tất theo selection set của subscription để tạo một GraphQL response.

~~~mermaid
flowchart TD
    A[Client subscribes] --> B[Execute subscription root field]
    B --> C[DataFetcher returns Publisher]
    C --> D[Transport subscribes]
    D --> E[Publisher emits event]
    E --> F[Resolve selected fields for event]
    F --> G[Send GraphQL event response]
    G --> E
    E -->|Publisher complete| H[End stream]
    E -->|Publisher error| I[Terminal subscription error]
~~~

Không thay SubscriptionExecutionStrategy bằng AsyncExecutionStrategy chỉ để thống nhất cấu hình. Strategy subscription cần giữ behavior Reactive Streams và cách GraphQL Java biến event thành response. Nếu tùy biến subscription strategy, hãy kế thừa hoặc giữ nguyên semantics của SubscriptionExecutionStrategy.

Lỗi ở field của một event và lỗi terminal của Publisher là hai tình huống khác nhau. DataFetcherExceptionResolver xử lý lỗi trong lúc resolve field; SubscriptionExceptionResolver xử lý lỗi khi publisher của subscription phát tín hiệu onError sau khi stream đã được thiết lập.

## 6. DataFetcher và ExecutionStrategy phối hợp thế nào?

DataFetcher chịu trách nhiệm lấy dữ liệu cho một field. ExecutionStrategy gọi DataFetcher, nhận giá trị trả về và hoàn tất giá trị đó theo GraphQL type.

DataFetcher có thể trả:

- Một giá trị đồng bộ, ví dụ Book hoặc List<Book>.
- Một CompletionStage, ví dụ CompletableFuture<Book>.
- DataFetcherResult để trả dữ liệu cùng GraphQL errors/local context.
- Với Spring for GraphQL, controller có thể trả các reactive type được hỗ trợ như Mono hoặc Flux tùy loại mapping.

Ví dụ DataFetcher trả CompletionStage:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return bookService.findByIdAsync(id);
};
~~~

Nếu service trả CompletionStage<Book>, AsyncExecutionStrategy có thể phối hợp kết quả đó với các field khác. Không cần tự gọi join() hoặc get() để chờ future hoàn tất.

Ví dụ sử dụng executor có giới hạn khi phải bọc một API blocking:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return CompletableFuture.supplyAsync(
            () -> legacyBookService.findById(id),
            bookLookupExecutor);
};
~~~

Executor bookLookupExecutor cần được cấu hình với số thread và queue phù hợp tải hệ thống. Không dùng một executor không giới hạn hoặc lạm dụng ForkJoinPool.commonPool cho mọi tác vụ blocking.

Trong ứng dụng WebFlux, ưu tiên API non-blocking như WebClient và reactive repository thay vì chuyển mọi lời gọi blocking sang CompletableFuture.

## 7. AsyncExecutionStrategy không tạo concurrency miễn phí

Có ba lớp cần phân biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| ExecutionStrategy | Quyết định cách dispatch, phối hợp và hoàn tất các field. |
| DataFetcher | Lấy dữ liệu cho field; có thể đồng bộ hoặc bất đồng bộ. |
| Executor / reactive runtime | Thực thi công việc bất đồng bộ trên tài nguyên thread/event loop cụ thể. |

AsyncExecutionStrategy cho phép các field độc lập tiến hành mà không phải chờ kết quả từng field trước. Tuy nhiên, nếu tất cả DataFetcher đều gọi JDBC blocking trên cùng thread, thời gian chờ I/O vẫn làm thread bị giữ.

Để có lợi ích thực tế:

- Dùng CompletionStage hoặc reactive return type khi nguồn dữ liệu hỗ trợ.
- Dùng bounded executor nếu buộc phải gọi API blocking.
- Đặt timeout cho lời gọi service/database.
- Giới hạn concurrency để không làm cạn connection pool hoặc downstream.
- Không gọi block(), join() hoặc get() trên event-loop thread.
- Theo dõi latency theo operation và field để tìm bottleneck thực tế.

## 8. DataLoader và batching dưới các strategy

DataLoader gom nhiều yêu cầu đọc cùng loại thành một batch. ExecutionStrategy phối hợp thời điểm DataLoader được dispatch trong quá trình resolve field.

Ví dụ query lấy nhiều order và customer:

~~~graphql
query {
    orders {
        id
        customer {
            id
            name
        }
    }
}
~~~

Nếu mỗi field customer gọi database riêng, ứng dụng có thể tạo N+1 queries. DataLoader giúp gom customer IDs và đọc theo batch.

ExecutionStrategy không thay thế DataLoader. Strategy điều phối field execution; DataLoader gom các lần load có cùng loader key trong một execution context. Khi tùy biến strategy, phải kiểm thử lại dispatch behavior để bảo đảm batching vẫn hoạt động.

Đặc biệt, việc chuyển Query từ async sang serial có thể thay đổi thời điểm các field được dispatch và ảnh hưởng kích thước batch. Không nên đổi strategy chỉ để kiểm soát thứ tự mà chưa đo tác động tới DataLoader và latency.

## 9. Exception handling gắn với ExecutionStrategy

ExecutionStrategy cần một DataFetcherExceptionHandler để xử lý exception phát sinh trong DataFetcher.

GraphQL Java mặc định dùng SimpleDataFetcherExceptionHandler. Handler này chuyển exception thành GraphQL error, gắn path/location và đưa lỗi vào response. GraphQL cho phép partial data cùng errors; một field lỗi không nhất thiết làm toàn operation thất bại.

Spring for GraphQL có contract DataFetcherExceptionResolver và các @GraphQlExceptionHandler để ánh xạ exception theo quy tắc ứng dụng. Spring tạo DataFetcherExceptionHandler từ danh sách resolver và gắn handler đó vào GraphQL.Builder.

Khi tạo custom ExecutionStrategy, cần truyền handler được dựng từ Spring resolver list. Nếu dùng constructor mặc định của strategy, strategy mới có thể dùng SimpleDataFetcherExceptionHandler của GraphQL Java và bỏ qua mapping lỗi mà Spring đã cấu hình.

## 10. Tùy biến ExecutionStrategy trong Spring Boot

Spring for GraphQL cung cấp GraphQlSourceBuilderCustomizer để tùy biến GraphQL.Builder mà vẫn giữ cơ chế auto-configuration của Boot.

Ví dụ sau tạo strategy riêng cho Query, đồng thời giữ Mutation tuần tự và dùng chung exception handler của Spring:

~~~java
import graphql.ExecutionResult;
import graphql.execution.AsyncExecutionStrategy;
import graphql.execution.AsyncSerialExecutionStrategy;
import graphql.execution.DataFetcherExceptionHandler;
import graphql.execution.ExecutionContext;
import graphql.execution.ExecutionStrategyParameters;
import graphql.execution.NonNullableFieldWasNullException;

import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.DataFetcherExceptionResolver;
// Spring Boot 3.x; với Spring Boot 4.x, dùng package org.springframework.boot.graphql.autoconfigure.
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutionStrategyConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer executionStrategyCustomizer(
            ObjectProvider<DataFetcherExceptionResolver> resolvers) {

        DataFetcherExceptionHandler exceptionHandler =
                DataFetcherExceptionResolver.createExceptionHandler(
                        resolvers.orderedStream().toList());

        AsyncExecutionStrategy queryStrategy =
                new TimedQueryExecutionStrategy(exceptionHandler);

        AsyncSerialExecutionStrategy mutationStrategy =
                new AsyncSerialExecutionStrategy(exceptionHandler);

        return builder -> builder.configureGraphQl(graphQLBuilder ->
                graphQLBuilder
                        .queryExecutionStrategy(queryStrategy)
                        .mutationExecutionStrategy(mutationStrategy));
    }

    static class TimedQueryExecutionStrategy extends AsyncExecutionStrategy {

        private static final Logger log =
                LoggerFactory.getLogger(TimedQueryExecutionStrategy.class);

        TimedQueryExecutionStrategy(DataFetcherExceptionHandler exceptionHandler) {
            super(exceptionHandler);
        }

        @Override
        public CompletableFuture<ExecutionResult> execute(
                ExecutionContext executionContext,
                ExecutionStrategyParameters parameters)
                throws NonNullableFieldWasNullException {

            long startedAt = System.nanoTime();

            return super.execute(executionContext, parameters)
                    .whenComplete((result, error) ->
                            log.debug("Query execution completed in {} ms, failed={}",
                                    (System.nanoTime() - startedAt) / 1_000_000,
                                    error != null
                                            || (result != null && !result.getErrors().isEmpty())));
        }
    }
}
~~~

Ví dụ minh họa các điểm tích hợp chính:

- ObjectProvider lấy các DataFetcherExceptionResolver bean đã được đăng ký.
- createExceptionHandler tạo handler theo resolver list của Spring.
- Query dùng custom strategy kế thừa AsyncExecutionStrategy.
- Mutation vẫn dùng AsyncSerialExecutionStrategy.
- Cả hai strategy đều nhận cùng handler để giữ cách ánh xạ exception của ứng dụng.

Package của GraphQlSourceBuilderCustomizer phụ thuộc Spring Boot major version. Với Spring Boot 3.x, interface nằm trong org.springframework.boot.autoconfigure.graphql. Với Spring Boot 4.x, package là org.springframework.boot.graphql.autoconfigure. Hãy dùng package tương ứng với phiên bản dependency của ứng dụng.

Đoạn code chỉ minh họa đo thời gian ở strategy của Query. Nếu mục tiêu chỉ là metrics/tracing, hãy cân nhắc Micrometer Observation hoặc GraphQlObservationInstrumentation trước khi tự viết strategy.

## 11. Vì sao phải giữ Mutation tuần tự khi tùy biến?

Một custom strategy có thể kế thừa AsyncExecutionStrategy hoặc AsyncSerialExecutionStrategy. Chọn sai lớp cha có thể làm thay đổi semantics của operation.

Ví dụ không phù hợp cho Mutation:

~~~java
AsyncExecutionStrategy strategy = new CustomAsyncExecutionStrategy(handler);

builder.configureGraphQl(graphQLBuilder ->
        graphQLBuilder
                .queryExecutionStrategy(strategy)
                .mutationExecutionStrategy(strategy));
~~~

Nếu CustomAsyncExecutionStrategy thực thi các root field song song, gán nó cho Mutation sẽ phá vỡ thứ tự tuần tự mà GraphQL specification yêu cầu.

Cách an toàn hơn là tách strategy:

~~~java
builder.configureGraphQl(graphQLBuilder ->
        graphQLBuilder
                .queryExecutionStrategy(customQueryStrategy)
                .mutationExecutionStrategy(
                        new AsyncSerialExecutionStrategy(exceptionHandler)));
~~~

Nếu cần tùy biến hành vi riêng của Mutation, hãy kế thừa AsyncSerialExecutionStrategy và bảo toàn cách thực thi tuần tự. Không chọn strategy chỉ dựa trên tên Async hoặc mong muốn tăng tốc.

## 12. Cấu hình trực tiếp GraphQlSource khi không dùng Boot

Nếu ứng dụng tự xây dựng GraphQlSource, có thể cấu hình GraphQL.Builder thông qua configureGraphQl:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .configureGraphQl(graphQLBuilder -> graphQLBuilder
                .queryExecutionStrategy(queryStrategy)
                .mutationExecutionStrategy(mutationStrategy))
        .build();
~~~

Trong ứng dụng thực tế, builder còn cần schema resources, RuntimeWiringConfigurer, exception resolvers và các cấu hình khác. Khi tự xây dựng GraphQlSource, hãy bảo đảm handler exception và các extension point cần thiết được đăng ký đầy đủ.

Nếu dùng Spring Boot auto-configuration, ưu tiên GraphQlSourceBuilderCustomizer để bổ sung cấu hình. Khi tự khai báo GraphQlSource bean, ứng dụng chịu trách nhiệm tự cấu hình các thành phần mà Boot trước đó tự phát hiện.

## 13. Tùy biến Subscription strategy

Subscription sử dụng SubscriptionExecutionStrategy để làm việc với Reactive Streams. Không thay nó bằng AsyncExecutionStrategy hoặc AsyncSerialExecutionStrategy vì hai strategy đó không có cùng behavior subscription.

Nếu thật sự cần custom SubscriptionExecutionStrategy, có thể truyền DataFetcherExceptionHandler tương tự:

~~~java
import graphql.execution.SubscriptionExecutionStrategy;

SubscriptionExecutionStrategy subscriptionStrategy =
        new SubscriptionExecutionStrategy(exceptionHandler);
~~~

Trong Spring for GraphQL, lỗi terminal của publisher được xử lý bằng SubscriptionExceptionResolver. DataFetcherExceptionResolver xử lý exception trong quá trình gọi DataFetcher hoặc resolve field, nhưng không xử lý publisher onError sau khi transport đã subscribe.

Không nên dùng ExecutionStrategy để thay đổi transport protocol, WebSocket lifecycle hoặc chính sách reconnect của client. Những phần đó thuộc transport handler, interceptor và client.

## 14. Error, partial data và null propagation

ExecutionStrategy phối hợp exception handler và quy tắc hoàn tất giá trị GraphQL. Khi một DataFetcher ném exception, GraphQL Java có thể trả field đó thành null và thêm GraphQL error vào response.

Ví dụ:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"]
    }
  ]
}
~~~

Nếu field author nullable, lỗi có thể chỉ làm author thành null. Nếu field hoặc parent được khai báo Non-Null, null propagation có thể làm phần data lớn hơn bị null theo schema.

ExecutionStrategy không quyết định thay nghiệp vụ rằng lỗi nào được bỏ qua. DataFetcherExceptionHandler/Spring exception resolver ánh xạ lỗi; schema nullability xác định cách null lan truyền trong response.

## 15. ExecutionStrategy và Instrumentation khác nhau thế nào?

Instrumentation là điểm mở rộng để quan sát hoặc điều chỉnh lifecycle của GraphQL Java. ExecutionStrategy quyết định cách field được thực thi và phối hợp kết quả.

| Nhu cầu | Extension point phù hợp |
| --- | --- |
| Đo thời gian tổng request hoặc field | Instrumentation / Micrometer Observation |
| Thay đổi cách dispatch field song song hay tuần tự | ExecutionStrategy |
| Ghi log metadata transport, HTTP header | WebGraphQlInterceptor |
| Ánh xạ exception thành GraphQL error | DataFetcherExceptionResolver |
| Lấy dữ liệu từ database/service | DataFetcher, controller hoặc application service |
| Batch nhiều lần load | DataLoader / @BatchMapping |
| Giới hạn query depth/complexity | Instrumentation hoặc validation mechanism phù hợp |

Không tạo custom ExecutionStrategy chỉ để ghi log hoặc đếm số field. Những việc đó thường phù hợp với Instrumentation hơn và không cần thay đổi semantics thực thi.

## 16. Khi nào nên viết custom ExecutionStrategy?

Chỉ nên viết custom strategy khi ứng dụng cần thay đổi cách GraphQL Java điều phối field mà các strategy có sẵn không đáp ứng.

Một số trường hợp có thể cân nhắc:

- Cần scheduling policy riêng cho một loại query.
- Cần giới hạn concurrency của các field theo quy tắc đặc thù.
- Cần điều phối một nhóm field theo một cơ chế phụ thuộc rõ ràng.
- Cần tích hợp execution với một runtime đặc thù.
- Cần mở rộng strategy hiện có nhưng vẫn giữ nguyên semantics của operation.

Trước khi viết custom strategy, hãy kiểm tra có thể giải quyết bằng các cách đơn giản hơn không:

- Dùng CompletionStage hoặc reactive return type trong DataFetcher.
- Dùng DataLoader để batch I/O.
- Dùng bounded executor để giới hạn tác vụ blocking.
- Dùng query depth/complexity limit để giới hạn tài nguyên.
- Dùng Instrumentation để quan sát execution.
- Đặt transaction ở application service thay vì toàn bộ GraphQL execution.

Custom strategy phải xử lý đúng nested object, list completion, nullability, DataLoader dispatch, instrumentation callbacks, exception handling và cancellation. Đây là extension point cấp thấp, không nên triển khai lại từ đầu nếu chỉ cần thay một vài hành vi.

## 17. Hiệu năng và giới hạn concurrency

AsyncExecutionStrategy có thể cải thiện latency khi nhiều field độc lập gọi các nguồn dữ liệu khác nhau. Nhưng concurrency quá cao có thể làm database pool, HTTP connection pool hoặc downstream service bị quá tải.

Các nguyên tắc thực tế:

1. Không dùng blocking I/O trực tiếp trong DataFetcher chạy trên event-loop.
2. Dùng bounded executor nếu phải bọc API blocking.
3. Cấu hình timeout cho database và service ngoài.
4. Giới hạn concurrency ở tầng client hoặc service khi downstream có giới hạn.
5. Dùng DataLoader để giảm số lần truy vấn thay vì tăng số thread.
6. Đo p95/p99 latency và error rate trước khi đổi strategy.
7. Kiểm thử với query có nhiều sibling fields và list lớn.
8. Theo dõi connection pool saturation và queue depth.

Đổi sang AsyncSerialExecutionStrategy cho Query có thể làm latency tăng vì các field độc lập phải chờ nhau. Ngược lại, dùng strategy song song cho Mutation root fields có thể phá vỡ semantics bắt buộc của GraphQL.

## 18. Kiểm thử ExecutionStrategy

Nên kiểm thử cả behavior của operation lẫn cấu hình Spring.

### Kiểm thử thứ tự Mutation

Có thể dùng GraphQlTester và Mockito InOrder để xác nhận các root mutation field được gọi theo thứ tự:

Schema dùng trong test:

~~~graphql
input CreateOrderInput {
    customerId: ID!
}

type Order {
    id: ID!
}

type Mutation {
    createOrder(input: CreateOrderInput!): Order!
    cancelOrder(orderId: ID!): Order!
}
~~~

Các kiểu dưới đây là DTO và service contract mà controller sử dụng trong ví dụ:

~~~java
public record CreateOrderInput(String customerId) {
}

public record Order(String id) {
}

public interface OrderService {
    Order create(CreateOrderInput input);
    Order cancel(String orderId);
}
~~~

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(OrderMutationController.class)
class MutationExecutionOrderTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    OrderService orderService;

    @Test
    void mutationRootFieldsAreExecutedInDocumentOrder() {
        when(orderService.create(any(CreateOrderInput.class)))
                .thenReturn(new Order("order-11"));
        when(orderService.cancel("order-10"))
                .thenReturn(new Order("order-10"));

        graphQlTester.document("""
                mutation {
                    createOrder(input: { customerId: "c-1" }) {
                        id
                    }
                    cancelOrder(orderId: "order-10") {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .verify();

        InOrder order = inOrder(orderService);
        order.verify(orderService).create(any());
        order.verify(orderService).cancel("order-10");
    }
}
~~~

Ví dụ giả định OrderMutationController ánh xạ hai root field sang OrderService.create và OrderService.cancel; schema có hai field tương ứng và cả hai trả về Order không null. @GraphQlTest tự cấu hình GraphQlTester cho execution test không cần HTTP transport. Với Spring Boot 3.x, import GraphQlTest từ org.springframework.boot.test.autoconfigure.graphql; package của Boot 4.x là org.springframework.boot.graphql.test.autoconfigure. Nếu dùng Spring Boot cũ hơn Spring Framework 6.2, thay @MockitoBean bằng @MockBean và import annotation từ package test của Boot.

### Kiểm thử Query có thể chạy bất đồng bộ

Tạo hai DataFetcher trả về CompletableFuture được điều khiển bởi test fixture. Xác nhận cả hai sibling fetch được dispatch trước khi hoàn tất một future, sau đó hoàn tất chúng theo thứ tự ngược và kiểm tra response vẫn giữ thứ tự field trong document.

Không dùng Thread.sleep để chứng minh concurrency. Dùng CountDownLatch, CompletableFuture gate hoặc executor test có kiểm soát để tránh test chập chờn.

### Kiểm thử custom strategy và exception mapping

Khi dùng custom strategy trong Spring:

- Gửi request có DataFetcher ném exception domain.
- Xác nhận DataFetcherExceptionResolver vẫn được gọi.
- Kiểm tra GraphQL error có message/code theo resolver.
- Xác nhận partial data và null propagation không thay đổi ngoài ý muốn.
- Kiểm tra strategy tùy biến không chạy hai lần do cấu hình trùng.

### Kiểm thử Subscription

Với subscription, xác nhận:

- Root DataFetcher trả Publisher.
- Mỗi event tạo một GraphQL response.
- Lỗi field trong một event được thể hiện trong response event.
- Publisher terminal error được chuyển qua SubscriptionExceptionResolver.
- Client cancellation được truyền tới publisher/upstream.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query field chạy tuần tự ngoài dự kiến | DataFetcher blocking hoặc strategy bị đổi sang serial | Dùng non-blocking return type và kiểm tra query strategy. |
| Mutation root fields chạy song song | Đã gán AsyncExecutionStrategy cho Mutation | Dùng AsyncSerialExecutionStrategy hoặc custom strategy giữ semantics serial. |
| Kết quả JSON không theo thứ tự hoàn tất | Field fetch hoàn tất khác thứ tự document | Đây là hành vi bình thường; GraphQL Java ghép kết quả theo thứ tự field. |
| Mutation tuần tự nhưng dữ liệu vẫn race giữa request | Serial strategy chỉ áp dụng trong một operation | Dùng transaction, locking hoặc optimistic concurrency ở service/database. |
| Mutation thứ hai chạy dù mutation đầu thất bại nghiệp vụ | DataFetcher trả kết quả lỗi như GraphQL error nhưng execution vẫn tiếp tục | Thiết kế use case atomic trong một mutation/service nếu bước sau phụ thuộc bước trước. |
| Custom strategy làm mất @GraphQlExceptionHandler | Strategy dùng SimpleDataFetcherExceptionHandler mặc định | Tạo handler từ DataFetcherExceptionResolver list của Spring và truyền vào constructor. |
| Subscription không phát event | Đã thay SubscriptionExecutionStrategy bằng strategy thường | Giữ SubscriptionExecutionStrategy. |
| Query async vẫn chiếm thread lâu | DataFetcher thực hiện blocking I/O trước khi trả future | Dùng non-blocking client hoặc bounded executor. |
| Database bị quá tải sau khi bật parallel query | Concurrency của sibling fields vượt khả năng pool | Giới hạn concurrency và tối ưu DataLoader/query. |
| DataLoader batch nhỏ hoặc không hiệu quả | Thời điểm dispatch thay đổi do strategy hoặc fetch pattern | Kiểm thử batch dispatch và điều chỉnh strategy/loader phù hợp. |
| GraphQL mutation không rollback tất cả field | Nhầm serial execution với transaction | Đặt transaction trong application service bao trọn use case. |
| Metrics trùng lặp | Dùng custom strategy chỉ để đo thời gian trong khi đã có Observation | Ưu tiên Instrumentation/Micrometer và tránh đo hai lần. |

## 20. Checklist chọn và cấu hình ExecutionStrategy

1. Dùng AsyncExecutionStrategy cho Query thông thường.
2. Dùng AsyncSerialExecutionStrategy cho Mutation để giữ thứ tự root field.
3. Dùng SubscriptionExecutionStrategy cho Subscription và Reactive Streams.
4. Nhớ rằng Query field có thể chạy bất đồng bộ nhưng response vẫn theo thứ tự document.
5. Không giả định AsyncExecutionStrategy tự biến DataFetcher blocking thành non-blocking.
6. Dùng CompletionStage/reactive type hoặc bounded executor cho I/O phù hợp.
7. Không nhầm Mutation serial với transaction atomic hoặc global lock.
8. Nếu tùy biến strategy, ưu tiên kế thừa strategy phù hợp thay vì triển khai từ đầu.
9. Khi cấu hình trong Spring, giữ DataFetcherExceptionHandler được tạo từ DataFetcherExceptionResolver.
10. Không gán strategy parallel cho Mutation.
11. Không thay SubscriptionExecutionStrategy bằng strategy Query/Mutation.
12. Dùng Instrumentation/Micrometer cho metrics và tracing nếu không cần thay scheduling.
13. Kiểm thử thứ tự mutation, concurrency query, exception mapping, partial data và subscription.
14. Đo latency, throughput, queue và connection pool trước/sau khi thay strategy.

ExecutionStrategy là cơ chế điều phối việc resolve field của GraphQL Java. AsyncExecutionStrategy phù hợp với Query có các field độc lập; AsyncSerialExecutionStrategy giữ thứ tự bắt buộc cho root field của Mutation; SubscriptionExecutionStrategy xử lý luồng event. Trong Spring for GraphQL, tùy biến strategy qua GraphQlSourceBuilderCustomizer và giữ DataFetcherExceptionHandler của Spring giúp ứng dụng thay đổi cách thực thi mà vẫn duy trì error mapping. Chỉ thay strategy khi thật sự cần đổi scheduling policy; các nhu cầu metrics, batching, transaction và transport nên được giải quyết ở extension point tương ứng.

Tài liệu tham khảo:
- [GraphQL Java — Execution Strategies](https://graphql-java.com/documentation/execution/)
- [GraphQL Java — ExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ExecutionStrategy.html)
- [GraphQL Java — AsyncExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/AsyncExecutionStrategy.html)
- [GraphQL Java — AsyncSerialExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/AsyncSerialExecutionStrategy.html)
- [GraphQL Java — SubscriptionExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/SubscriptionExecutionStrategy.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — DataFetcherExceptionResolver API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/DataFetcherExceptionResolver.html)
- [GraphQL Specification — Normal and Serial Execution](https://spec.graphql.org/October2021/#sec-Normal-and-Serial-Execution)
