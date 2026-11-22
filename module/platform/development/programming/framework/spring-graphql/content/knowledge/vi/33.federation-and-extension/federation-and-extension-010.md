# Spring GraphQL trong kiến trúc nhiều service

Spring for GraphQL có thể được dùng để xây dựng một GraphQL API trong một ứng dụng đơn khối, một GraphQL endpoint ở lớp BFF/API gateway, hoặc nhiều GraphQL subgraph trong kiến trúc microservices. Framework cung cấp hạ tầng GraphQL cho từng service; nó không tự chia hệ thống thành microservices, không tự định tuyến request giữa các service và cũng không tự tạo distributed transaction.

Khi đưa GraphQL vào hệ thống nhiều service, cần quyết định service nào sở hữu dữ liệu và field, client đi vào endpoint nào, cách các service phối hợp để trả một response, cách truyền identity qua các ranh giới mạng và cách xử lý khi một dependency chậm hoặc lỗi. Apollo Federation là một cách phổ biến để hợp nhất nhiều GraphQL subgraph thành một supergraph. Một lựa chọn khác là xây dựng GraphQL BFF hoặc API composition service dùng GraphQlClient/HTTP client gọi các backend hiện có.

Bài này tập trung vào cách chọn kiến trúc, triển khai service boundary bằng Spring GraphQL, tránh gọi mạng theo từng field, bảo vệ request xuyên service, xử lý lỗi và vận hành hệ thống.

## 1. GraphQL và microservices giải quyết hai vấn đề khác nhau

Microservices chia hệ thống theo ranh giới nghiệp vụ và quyền sở hữu dữ liệu. Mỗi service có thể triển khai, mở rộng và phát hành độc lập. GraphQL cung cấp một contract truy vấn dữ liệu theo field, cho phép client chọn cấu trúc response cần thiết.

Hai khái niệm bổ trợ nhau:

- Microservice quyết định ai sở hữu capability và dữ liệu.
- GraphQL schema mô tả client có thể yêu cầu dữ liệu nào.
- Resolver kết nối field trong schema với use case hoặc nguồn dữ liệu.
- Gateway/BFF/Federation router điều phối request qua nhiều service nếu một response cần nhiều domain.

GraphQL không thay thế service boundary. Nếu một GraphQL resolver đọc trực tiếp database của service khác, hệ thống đã tạo phụ thuộc dữ liệu xuyên service dù endpoint vẫn là GraphQL. Hãy gọi API do service sở hữu dữ liệu công bố, hoặc dùng federation để gateway định tuyến đến đúng subgraph.

## 2. Các kiểu tổ chức GraphQL trong hệ thống nhiều service

Có ba kiểu thường gặp:

| Kiểu kiến trúc | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Một GraphQL gateway/BFF | Một GraphQL server gọi REST, gRPC hoặc GraphQL API của các backend | Đã có nhiều backend và muốn một API được thiết kế theo nhu cầu từng client |
| Apollo Federation | Nhiều GraphQL subgraph công bố schema riêng; router composition thành supergraph và lập query plan | Nhiều domain team sở hữu GraphQL schema/field và cần phát triển độc lập |
| GraphQL theo từng service, client chọn endpoint | Client gọi trực tiếp nhiều GraphQL API | Số service ít, client nội bộ có thể quản lý nhiều API và không cần một graph thống nhất |

Kiến trúc thường gặp là client chỉ biết một endpoint ở gateway/router. Gateway có thể là BFF do tổ chức tự xây dựng hoặc Federation router. Mỗi Spring GraphQL service tiếp tục chịu trách nhiệm schema, resolver, authorization và dữ liệu của domain mình.

Không có yêu cầu mọi microservice đều phải expose GraphQL. Một số service có thể chỉ cung cấp REST, gRPC hoặc message-based API. GraphQL gateway có thể gọi các API đó và chuyển dữ liệu thành GraphQL response.

## 3. Kiến trúc BFF/API composition

Trong mô hình BFF, Spring GraphQL chạy ở lớp API dành cho client. Resolver gọi application service, application service phối hợp các backend qua client phù hợp:

~~~mermaid
flowchart TD
    C[Web hoặc Mobile Client] --> G[Spring GraphQL BFF]
    G --> A[Application Service]
    A --> P[Product Service]
    A --> O[Order Service]
    A --> U[User Service]
    P --> PD[(Product DB)]
    O --> OD[(Order DB)]
    U --> UD[(User DB)]
    G --> R[GraphQL Response]
    R --> C
~~~

BFF sở hữu schema được thiết kế cho trải nghiệm client, ví dụ ProductCard, OrderSummary hoặc AccountDashboard. Nó không cần expose nguyên vẹn schema nội bộ của từng backend.

Ví dụ một GraphQL query:

~~~graphql
query Dashboard {
    dashboard {
        displayName
        recentOrders {
            id
            status
        }
        recommendedProducts {
            id
            name
        }
    }
}
~~~

BFF có thể phối hợp User Service, Order Service và Product Service để trả một response. Ưu điểm là client không cần biết nhiều backend và schema có thể được tối ưu theo màn hình. Đổi lại, BFF phải quản lý downstream calls, timeout, partial failure, mapping DTO và contract của các service.

Nếu mỗi resolver gọi một service riêng, BFF có thể trở thành một lớp network orchestration khó kiểm soát. Hãy đặt orchestration ở application service, gom các request độc lập khi phù hợp và dùng batch API cho tập ID.

## 4. Kiến trúc Apollo Federation

Federation tổ chức một graph thống nhất từ nhiều GraphQL subgraph. Mỗi subgraph sở hữu một phần schema và triển khai các field thuộc domain của nó. Router nhận request từ client, lập query plan và gọi subgraph theo dependency của các field.

~~~mermaid
flowchart TD
    C[GraphQL Client] --> R[Federation Router]
    R --> S[Supergraph Query Plan]
    S --> P[Catalog Subgraph]
    S --> O[Order Subgraph]
    S --> U[Customer Subgraph]
    P --> PD[(Catalog DB)]
    O --> OD[(Order DB)]
    U --> UD[(Customer DB)]
    P --> R
    O --> R
    U --> R
    R --> C
~~~

Spring for GraphQL cung cấp integration với federation-jvm. Một subgraph có thể dùng FederationSchemaFactory để tạo federation schema, khai báo entity bằng @key và khôi phục entity qua @EntityMapping. Router sử dụng _service để lấy SDL và _entities để resolve entity representation khi query plan cần đi qua nhiều subgraph.

Ví dụ:

- Catalog subgraph sở hữu Book với id, title và price.
- Review subgraph mở rộng Book với rating và reviews.
- Order subgraph sở hữu Order và tham chiếu Book bằng product ID.
- Router có thể lấy Book từ Catalog rồi gọi Review để bổ sung rating.

Federation cho phép domain team quản lý schema riêng. Nó không tự động bảo đảm service boundary đúng; ownership, entity key, authorization và dependency giữa subgraph vẫn cần được thiết kế.

## 5. Vai trò của Spring GraphQL trong mỗi service

Một Spring GraphQL subgraph thường gồm các lớp:

| Lớp | Trách nhiệm |
| --- | --- |
| SDL | Công bố type, field, input và entity key mà service sở hữu |
| Controller/resolver | Ánh xạ GraphQL field sang use case |
| Application service | Thực thi quy tắc nghiệp vụ và điều phối trong phạm vi service |
| Repository/client | Truy cập database hoặc dependency mà service được phép gọi |
| Security | Xác thực caller và kiểm tra quyền trên từng operation/field |
| GraphQlSource/FederationSchemaFactory | Tạo GraphQL schema, bao gồm subgraph protocol nếu dùng Federation |
| Observation/logging | Theo dõi latency, error và dependency |

Một service nên giữ quyền sở hữu dữ liệu của mình. Service khác không truy vấn trực tiếp database của service đó để tiết kiệm một HTTP call. Dùng API hoặc event contract do owner công bố; nếu cần dữ liệu read-heavy từ nhiều domain, cân nhắc read model/materialized view được xây dựng có chủ đích.

## 6. Thiết kế service boundary và schema ownership

Schema nên phản ánh domain capability, không nhất thiết phản ánh cấu trúc bảng database. Ví dụ Order Service sở hữu Order, trạng thái thanh toán và lịch sử đơn hàng. Catalog Service sở hữu Product, giá niêm yết và mô tả sản phẩm.

Khi một field thuộc domain khác, có hai lựa chọn:

1. Gateway/BFF gọi API của domain sở hữu field và ghép response.
2. Trong Federation, subgraph sở hữu entity có thể được mở rộng bởi subgraph khác theo key.

Tránh để nhiều service cùng ghi một nguồn dữ liệu hoặc cùng nhận ownership của một field mà không có quy tắc rõ. Trong Federation, dùng directive ownership phù hợp với phiên bản federation và composition rules. Ngoài Federation, công bố rõ service nào là source of truth.

Không thiết kế một subgraph cho mỗi bảng. Hãy nhóm field theo capability và ngôn ngữ nghiệp vụ để thay đổi một use case không phải phối hợp quá nhiều service.

## 7. Gọi GraphQL service khác bằng GraphQlClient

Spring for GraphQL cung cấp GraphQlClient với workflow thống nhất cho HTTP, WebSocket và RSocket. Một BFF có thể dùng HttpGraphQlClient để gọi GraphQL API của backend.

Ví dụ tạo client qua WebClient:

~~~java
@Configuration
public class DownstreamGraphQlConfig {

    @Bean
    HttpGraphQlClient catalogGraphQlClient(
            WebClient.Builder webClientBuilder) {

        WebClient webClient = webClientBuilder
            .baseUrl("http://catalog-service/graphql")
            .build();

        return HttpGraphQlClient.builder(webClient).build();
    }
}
~~~

Service gọi operation:

~~~java
@Service
public class CatalogClient {

    private final HttpGraphQlClient graphQlClient;

    public CatalogClient(HttpGraphQlClient graphQlClient) {
        this.graphQlClient = graphQlClient;
    }

    public Mono<ProductView> findProduct(String id) {
        return graphQlClient.document("""
                query ProductById($id: ID!) {
                    product(id: $id) {
                        id
                        name
                        price
                    }
                }
                """)
            .variable("id", id)
            .retrieve("product")
            .toEntity(ProductView.class);
    }
}
~~~

Đây là ví dụ WebFlux/reactive. Nếu ứng dụng dùng Spring MVC và blocking I/O, có thể chọn HttpSyncGraphQlClient dựa trên RestClient. Không gọi block() tùy tiện trong WebFlux event-loop.

GraphQlClient giúp BFF gọi GraphQL backend bằng operation và variables có kiểu dữ liệu rõ ràng. Nó không phải Federation router và không tự lập query plan cho nhiều subgraph.

## 8. Gọi song song các service độc lập

Nếu dashboard cần dữ liệu từ ba service độc lập, có thể gọi song song thay vì tuần tự:

~~~java
public Mono<Dashboard> loadDashboard(String customerId) {
    Mono<CustomerView> customer =
        customerClient.findCustomer(customerId);
    Mono<List<OrderView>> orders =
        orderClient.findRecentOrders(customerId);
    Mono<List<ProductView>> recommendations =
        catalogClient.findRecommendations(customerId);

    return Mono.zip(customer, orders, recommendations)
        .map(tuple -> new Dashboard(
            tuple.getT1(),
            tuple.getT2(),
            tuple.getT3()));
}
~~~

Chỉ chạy song song khi các lời gọi không phụ thuộc kết quả của nhau và hệ thống downstream chịu được mức concurrency đó. Nếu một lời gọi phụ thuộc ID trả về từ lời gọi trước, cần giữ thứ tự hoặc thiết kế endpoint batch/aggregate phù hợp.

Mono.zip mặc định yêu cầu các nguồn phát giá trị. Nếu một dependency có thể không trả dữ liệu, định nghĩa fallback hoặc kiểu kết quả rõ ràng cho trường hợp đó; đừng biến lỗi thành object rỗng mà client không thể phân biệt với dữ liệu thật.

## 9. Tránh chatty calls và N+1 qua network

N+1 không chỉ xảy ra với SQL. Một resolver gọi HTTP cho từng parent object có thể tạo network N+1:

~~~java
@SchemaMapping(typeName = "Order", field = "customer")
public Mono<CustomerView> customer(Order order) {
    return customerClient.findCustomer(order.customerId());
}
~~~

Nếu query trả 100 Order, resolver có thể phát 100 HTTP request đến Customer Service. DataLoader trong GraphQL không tự động biến một client HTTP đơn lẻ thành batch API; batch loader phải thực sự gom key và gọi downstream theo lô.

Giải pháp:

- Cung cấp endpoint batch ở service sở hữu dữ liệu, ví dụ customersByIds(ids).
- Dùng DataLoader hoặc @BatchMapping để gom customer ID từ nhiều Order.
- Cache dữ liệu bất biến hoặc ít thay đổi theo policy có TTL rõ ràng.
- Tránh resolver gọi service tuần tự qua nhiều tầng.
- Chỉ fetch field khi client chọn và có authorization phù hợp.

Ví dụ batch loader:

~~~java
@Component
public class CustomerBatchLoader {

    public CustomerBatchLoader(
            BatchLoaderRegistry registry,
            CustomerClient customerClient) {

        registry.forTypePair(String.class, CustomerView.class)
            .registerMappedBatchLoader((ids, environment) ->
                customerClient.findCustomers(ids));
    }
}
~~~

CustomerClient.findCustomers(ids) phải gọi một API batch thực sự và trả Map từ ID sang CustomerView. Nếu method này vẫn lặp từng ID rồi gọi findCustomer(), N+1 chỉ được chuyển từ resolver xuống service client.

## 10. DataLoader và ranh giới request

DataLoader thường cache và gom các lần load trong phạm vi một GraphQL execution. Nó hữu ích cho nhiều resolver cùng cần một key hoặc nhiều parent cùng cần một loại association.

Khi dùng DataLoader với downstream service:

- Batch key cần có type rõ và ổn định.
- Batch function phải trả đúng kết quả cho từng key.
- Nếu dùng mapped batch loader, Map key-value phải khớp ID được yêu cầu.
- Không chia sẻ DataLoader cache giữa request hoặc user nếu dữ liệu phụ thuộc quyền.
- Đưa tenant/security scope vào downstream query, không tin ID do client cung cấp.
- Đặt giới hạn kích thước batch để không tạo request quá lớn.

DataLoader không thay thế cache phân tán. Cache của loader thường phục vụ một execution; nếu cần cache liên request, hãy thiết kế riêng TTL, invalidation và isolation.

## 11. Truyền authentication và request context

Trong kiến trúc nhiều service, gateway hoặc BFF cần truyền identity phù hợp đến service downstream. Có thể dùng OAuth2 token relay, service-to-service credential hoặc một mô hình token exchange tùy yêu cầu bảo mật.

Không chuyển tiếp mọi header một cách mù quáng. Chỉ forward các header đã được allowlist, không tin X-User-Id hoặc X-Tenant-Id do client tự gửi nếu gateway chưa xác thực và tạo lại chúng.

Ở phía Spring GraphQL server, WebGraphQlInterceptor có thể đọc thông tin từ HTTP request và đưa giá trị cần thiết vào GraphQLContext:

~~~java
@Component
public class RequestContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId =
            request.getHeaders().getFirst("X-Correlation-Id");

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context -> {
                if (correlationId != null) {
                    context.put("correlationId", correlationId);
                }
            }).build());

        return chain.next(request);
    }
}
~~~

Resolver có thể đọc context:

~~~java
@QueryMapping
public Dashboard dashboard(
        @ContextValue("correlationId") String correlationId,
        Principal principal) {
    return dashboardService.load(principal, correlationId);
}
~~~

GraphQLContext chỉ là nơi chia sẻ dữ liệu trong execution; nó không tự truyền context qua HTTP. Outbound GraphQlClient/WebClient cần cấu hình header/token riêng, tốt nhất thông qua interceptor hoặc filter tập trung. Dùng Spring Security context và OAuth2 client support để lấy credential theo policy, không tự ghép token vào chuỗi query.

## 12. Authorization ở gateway và subgraph

Gateway có thể xác thực người dùng trước khi nhận query, nhưng mỗi subgraph vẫn phải bảo vệ dữ liệu mà nó sở hữu. Không giả định request đến từ gateway là luôn hợp lệ hoặc mọi field đều được phép đọc.

Một mô hình có thể gồm:

1. Gateway xác thực access token của end user.
2. Gateway truyền token đã xác minh hoặc token được exchange cho audience của subgraph.
3. Subgraph xác thực token và tạo SecurityContext.
4. Resolver/service kiểm tra quyền theo resource, tenant và action.
5. Batch loader áp dụng cùng authorization scope như resolver đơn lẻ.

Với service credential chung, cần một cơ chế tin cậy để chuyển user identity hoặc authorization context đã được ký. Không tin header identity không được bảo vệ.

Field-level authorization cần nằm gần domain logic hoặc method security. Ẩn field trong gateway không đủ nếu subgraph vẫn có thể bị gọi trực tiếp hoặc được một query plan khác truy cập.

## 13. GraphQL error và partial data qua nhiều service

Một GraphQL response có thể chứa cả data và errors. Nếu Product Service thành công nhưng Recommendation Service lỗi, BFF có thể trả phần product data còn dùng được cùng GraphQL error ở field recommendations, tùy schema nullability và error mapping.

Không nên biến mọi lỗi downstream thành empty list hoặc null mà không có semantics. Client cần biết field nào không có dữ liệu thật, field nào bị lỗi và có thể thử lại hay không.

Ví dụ phân loại:

| Lỗi downstream | Cách xử lý có thể phù hợp |
| --- | --- |
| Resource không tồn tại | Trả NOT_FOUND hoặc null theo contract |
| Không có quyền | Trả FORBIDDEN/UNAUTHORIZED theo policy |
| Timeout một field không bắt buộc | Có thể trả partial data và error có mã ổn định |
| Dependency bắt buộc không khả dụng | Có thể fail operation hoặc trả error tại field bắt buộc |
| Request downstream sai do BFF gửi | Ghi lỗi nội bộ, không đổ lỗi cho client cuối |

GraphQL null propagation có thể làm null lan lên parent nếu field được khai báo non-null. Thiết kế schema cần cân nhắc khả năng dependency độc lập bị lỗi. Không đặt non-null cho field phụ thuộc service khác chỉ vì dữ liệu thường có mặt nếu hệ thống cần partial response khi dependency gián đoạn.

Khi dùng GraphQlClient, có thể dùng execute() để quan sát response và errors thay vì chỉ retrieve một path nếu cần xử lý partial data. Error từ transport (timeout, connection refused) khác với GraphQL error do downstream trả về.

## 14. Timeout, retry và circuit breaker

Mỗi network call cần timeout hữu hạn. Nếu BFF chờ nhiều service theo chuỗi, latency tổng có thể là tổng latency của từng dependency. Gọi song song giúp giảm latency trong trường hợp độc lập, nhưng vẫn cần deadline tổng cho request.

Nguyên tắc:

- Đặt connect timeout và response timeout cho HTTP client.
- Có deadline ngân sách ở cấp operation/BFF.
- Dùng circuit breaker để ngừng gọi dependency đang lỗi kéo dài.
- Dùng bulkhead hoặc giới hạn concurrency để một service chậm không chiếm hết tài nguyên.
- Retry có giới hạn, jitter và chỉ áp dụng khi operation an toàn để lặp.
- Không tự động retry mutation không idempotent.
- Tránh retry ở mọi tầng cùng lúc vì có thể khuếch đại tải.

Với query đọc, retry có thể phù hợp nếu lỗi tạm thời và còn ngân sách thời gian. Với mutation, dùng idempotency key hoặc command ID nếu nghiệp vụ cho phép retry an toàn.

Fallback phải có ý nghĩa nghiệp vụ. Cache stale hoặc dữ liệu mặc định chỉ được dùng khi contract cho phép; không trả dữ liệu cũ như dữ liệu mới mà không biểu thị freshness.

## 15. Mutation xuyên nhiều service và tính nhất quán

GraphQL mutation chỉ bảo đảm thứ tự thực thi của các top-level mutation field trong một operation theo quy tắc GraphQL. Nó không tạo một transaction ACID bao trùm nhiều microservice.

Ví dụ tạo đơn hàng có thể cần:

1. Order Service tạo đơn ở trạng thái PENDING.
2. Inventory Service giữ hàng.
3. Payment Service thực hiện thanh toán.
4. Order Service chuyển trạng thái CONFIRMED hoặc FAILED.

Không mở một database transaction trong BFF rồi mong nó rollback database của Inventory và Payment. Mỗi service có transaction cục bộ của nó.

Các pattern thường dùng:

- **Saga:** điều phối các bước và compensating action khi một bước thất bại.
- **Transactional outbox:** ghi domain change và event vào cùng transaction cục bộ, sau đó publish event.
- **Idempotency:** dùng command ID/idempotency key để xử lý retry và message trùng.
- **Process manager:** theo dõi tiến trình nghiệp vụ dài qua nhiều service.

GraphQL mutation nên gọi một application use case có ý nghĩa nghiệp vụ, ví dụ placeOrder, thay vì để gateway tự thực hiện hàng loạt thao tác ghi database của nhiều domain.

## 16. Subscription và streaming trong hệ thống nhiều service

Spring for GraphQL hỗ trợ HTTP, WebSocket, Server-Sent Events và RSocket theo transport/configuration phù hợp. Subscription thường cần một nguồn event như broker hoặc reactive publisher.

Một service có thể phát domain event qua Kafka/RabbitMQ, còn GraphQL API subscribe vào event stream và chuyển thành GraphQL response. Khi triển khai nhiều instance, cần tính đến consumer group, event fan-out, replay, backpressure, connection lifecycle và quyền của từng subscriber.

Không dùng một WebSocket subscription nội bộ thay cho message broker khi cần giao tiếp bền vững giữa service. GraphQL subscription phục vụ client stream; broker/event contract thường phù hợp hơn cho service-to-service event delivery.

## 17. Truyền trace và correlation xuyên service

Một GraphQL request có thể đi qua router, BFF và nhiều subgraph. Nếu mỗi service chỉ ghi log riêng mà không truyền trace context, khó xác định latency phát sinh ở đâu.

Nên:

- Dùng Micrometer Observation/Tracing hoặc OpenTelemetry instrumentation tương thích.
- Propagate trace context qua HTTP client và server instrumentation.
- Ghi operation name, service name và correlation ID trong log.
- Đo latency, error rate và timeout của từng downstream dependency.
- Theo dõi GraphQL request, DataFetcher, DataLoader và outbound HTTP span.
- Không đưa token, PII, raw query variables hoặc toàn bộ query vào metric labels.

Một trace tốt có thể thể hiện BFF operation chờ Catalog 30 ms, Order 180 ms và Customer 20 ms; từ đó nhận ra Order Service là dependency chi phối latency. Metrics cho xu hướng, trace cho một request cụ thể và log cung cấp ngữ cảnh chẩn đoán.

## 18. Bảo vệ GraphQL endpoint khỏi query quá đắt

Một client có thể yêu cầu nhiều field lồng nhau hoặc alias cùng field nhiều lần. Khi resolver gọi service khác, query rộng có thể tạo fan-out lớn.

Các biện pháp cần cân nhắc:

- Depth limit và query complexity/cost limit.
- Page size tối đa cho connection/list.
- Giới hạn số lượng alias hoặc số operation tùy policy.
- Request rate limit theo user/client.
- Giới hạn concurrency và batch size.
- Persisted query/allowlist cho client tin cậy nếu phù hợp.
- Field-level authorization và timeout cho downstream.

DataLoader giảm số lần gọi lặp theo key nhưng không loại bỏ chi phí của một query có hàng nghìn node hoặc field đắt. Cần đo cả số lượng key trong batch, tổng downstream request và response size.

## 19. Quản lý schema và triển khai độc lập

Trong hệ thống nhiều service, schema là contract giữa service và client/gateway. Thay đổi schema cần tương thích ngược:

- Thêm field nullable thường an toàn hơn thay đổi field hiện có.
- Không đổi kiểu hoặc ý nghĩa field đang được client dùng.
- Deprecate field trước khi xóa.
- Thay đổi entity key phải phối hợp với router và các subgraph liên quan.
- Kiểm tra composition trước khi deploy schema mới.
- Giữ backward compatibility trong giai đoạn gateway và subgraph deploy lệch thời điểm.

Với Federation, pipeline CI nên lấy SDL của các subgraph và chạy composition check trước khi phát hành. Nếu composition thất bại, không publish một subgraph schema phá vỡ supergraph.

Triển khai theo hướng expand-and-contract: thêm field/key hoặc endpoint mới, cập nhật consumer/gateway, quan sát traffic, sau đó mới loại bỏ contract cũ. Không giả định tất cả service được deploy đồng thời.

## 20. Kiểm thử hệ thống nhiều service

Nên kiểm thử ở nhiều ranh giới:

| Loại test | Mục tiêu |
| --- | --- |
| Unit test application service | Business rule và mapping dữ liệu |
| GraphQlTester | SDL, resolver, error mapping, nullability và authorization |
| GraphQlClient contract test | Operation/variables và response contract của downstream |
| Subgraph entity test | _service, _entities, @EntityMapping và representation |
| Federation composition test | SDL các subgraph kết hợp thành supergraph hợp lệ |
| Integration test | Gateway/BFF gọi nhiều service qua network thật hoặc test container |
| Failure test | Timeout, unavailable service, partial data, retry và circuit breaker |
| Security test | Token relay, tenant isolation và direct subgraph access |

GraphQlTester kiểm tra GraphQL execution trong một service nhưng không tự kiểm tra router query plan hoặc toàn bộ network. Cần test ở gateway/router để xác nhận query thật được phân rã và các subgraph trả dữ liệu đúng.

Test nên bao gồm cả trường hợp một subgraph lỗi trong khi subgraph khác thành công, entity không tìm thấy, batch result thiếu key, authorization từ chối và mutation bị retry.

## 21. Ví dụ luồng request hoàn chỉnh

Giả sử client cần một trang đơn hàng:

~~~graphql
query CustomerOrders($customerId: ID!) {
    customer(id: $customerId) {
        displayName
        orders(first: 10) {
            edges {
                node {
                    id
                    status
                    total
                    items {
                        product {
                            id
                            name
                        }
                    }
                }
            }
        }
    }
}
~~~

Trong BFF architecture:

1. GraphQL resolver gọi Customer application service.
2. Service lấy customer từ Customer Service.
3. Order Service trả trang order theo customer ID.
4. Product Service cung cấp product data qua batch endpoint cho toàn bộ product ID trong các order item.
5. BFF ghép DTO và GraphQL thực thi selection set.

Trong Federation architecture:

1. Router nhận query và lập query plan.
2. Customer subgraph resolve customer.
3. Order subgraph mở rộng customer hoặc resolve orders theo entity key/field ownership.
4. Product subgraph resolve Product entities từ representations.
5. Router ghép kết quả và trả response cho client.

Hai mô hình có thể tạo response giống nhau nhưng trách nhiệm orchestration khác nhau. Chọn mô hình theo ownership, số domain team, khả năng vận hành router và nhu cầu client; không chọn chỉ vì một mô hình có nhiều annotation hơn.

## 22. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Mọi service cùng truy cập một database | Coupling schema dữ liệu và triển khai | Mỗi service sở hữu dữ liệu; giao tiếp qua contract |
| Mỗi resolver gọi HTTP riêng cho từng parent | Network N+1 và latency tăng theo số node | Batch API và DataLoader/@BatchMapping |
| Nghĩ DataLoader tự batch HTTP | Loader vẫn phát một request cho mỗi key | Batch function phải gọi downstream batch endpoint |
| BFF tự trở thành domain service | Logic nghiệp vụ và ownership bị trộn | Giữ BFF ở orchestration/presentation, domain ở service owner |
| Coi Federation router là Spring GraphQL server | Nhầm trách nhiệm composition và subgraph execution | Tách router/gateway khỏi Spring GraphQL subgraph |
| Chỉ xác thực tại gateway | Subgraph bị gọi trực tiếp có thể không được bảo vệ | Xác thực và authorization ở từng service |
| Forward mọi header từ client | Identity spoofing hoặc lộ credential | Allowlist và tạo context từ thông tin đã xác minh |
| Dùng một transaction cho nhiều database service | Không có atomic rollback xuyên service | Saga, outbox và idempotency |
| Retry mọi mutation | Tạo đơn/thanh toán trùng | Idempotency key và retry policy theo operation |
| Che lỗi dependency bằng empty data | Client không biết dữ liệu bị thiếu do lỗi | Trả GraphQL error/partial data theo contract |
| Không giới hạn query complexity | Fan-out và tải downstream không kiểm soát | Depth/cost limit, page cap, rate limit |
| Không propagate trace | Không xác định được service gây latency | Instrument HTTP client/server và truyền trace context |
| Deploy subgraph không kiểm tra composition | Supergraph có thể không build được | Chạy schema composition trong CI |

## 23. Nguyên tắc thiết kế Spring GraphQL trong nhiều service

Đặt Spring for GraphQL tại ranh giới API mà service thực sự sở hữu. Nếu cần một API cho client, dùng BFF/API composition để gọi backend bằng client phù hợp; nếu nhiều domain team cùng sở hữu một graph, cân nhắc Apollo Federation với router và các Spring GraphQL subgraph. Không để resolver đọc trực tiếp database của service khác.

Giữ resolver mỏng, đặt orchestration trong application service, gom downstream calls theo batch và không gọi mạng một lần cho mỗi parent object. Truyền identity qua cơ chế được xác thực, kiểm tra quyền ở từng subgraph và giữ transaction trong phạm vi service. Dùng Saga/outbox/idempotency cho workflow ghi xuyên nhiều domain.

Đặt timeout và giới hạn concurrency cho dependency, phân biệt GraphQL errors với transport errors, cho phép partial data khi contract phù hợp và không retry mutation thiếu idempotency. Theo dõi trace xuyên service, kiểm soát query complexity, kiểm thử composition và triển khai schema theo hướng tương thích ngược.

Spring GraphQL cung cấp nền tảng để mỗi service xây dựng GraphQL endpoint và tích hợp Federation hoặc GraphQlClient. Chất lượng của kiến trúc nhiều service vẫn phụ thuộc vào domain ownership, contract, security, resilience và khả năng vận hành toàn hệ thống.

## Tài liệu tham khảo

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — GraphQlClient](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — Request Execution and Schema Creation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring GraphQL support](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Apollo Federation — Introduction](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/federation)
