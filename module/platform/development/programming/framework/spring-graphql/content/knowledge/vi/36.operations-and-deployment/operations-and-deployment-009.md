# Theo dõi lỗi theo operation

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao cần theo dõi lỗi theo từng GraphQL operation thay vì chỉ nhìn HTTP status.
- Phân biệt lỗi request, lỗi khi thực thi field và lỗi transport.
- Đặt operation name ổn định cho query, mutation và subscription.
- Dùng Micrometer Observation của Spring for GraphQL để đo request và data fetcher.
- Đọc các outcome SUCCESS, REQUEST_ERROR và INTERNAL_ERROR.
- Liên kết lỗi trong trace với execution ID, operation name và field path.
- Phân biệt low-cardinality và high-cardinality key khi thiết kế metric.
- Mở rộng observation bằng ExecutionRequestObservationConvention.
- Thiết kế log có cấu trúc, dashboard và cảnh báo lỗi theo operation.
- Kiểm thử việc ghi nhận lỗi, kể cả trường hợp GraphQL trả partial data.

## Vì sao phải theo dõi theo operation?

Một endpoint GraphQL thường dùng chung một URL cho nhiều chức năng. Ví dụ /graphql có thể nhận:

- Query BookDetails để đọc thông tin sách.
- Query SearchBooks để tìm kiếm.
- Mutation CreateBook để tạo sách.
- Mutation PlaceOrder để đặt hàng.
- Subscription BookEvents để nhận sự kiện.

Nếu chỉ theo dõi HTTP request, tất cả operation có thể xuất hiện dưới cùng một route. Một query đọc sách chậm, mutation thanh toán lỗi và subscription bị ngắt sẽ bị trộn vào một nhóm số liệu.

GraphQL còn có thể trả HTTP 200 dù response chứa errors. Một field có thể thất bại trong khi các field khác vẫn trả dữ liệu. Vì vậy, HTTP status không đủ để xác định request GraphQL thành công hay thất bại.

Theo dõi theo operation giúp trả lời các câu hỏi vận hành:

- Operation nào có tỷ lệ lỗi tăng?
- Lỗi tập trung ở query, mutation hay subscription?
- Operation nào có p95/p99 latency cao?
- Lỗi xuất hiện ở root field hay nested field?
- Lỗi do validation, business rule, database hay dịch vụ bên ngoài?
- Một thay đổi triển khai ảnh hưởng operation nào?

Mục tiêu là liên kết ba lớp thông tin: request tổng thể, field resolver gây lỗi và exception hoặc error code có ý nghĩa nghiệp vụ.

## Đặt operation name ổn định

GraphQL operation có thể được đặt tên:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

Operation name là tên được khai báo sau query, mutation hoặc subscription. Đây là metadata hữu ích để phân biệt các use case dùng chung endpoint.

Hãy dùng tên ổn định và có ý nghĩa:

| Operation name | Mục đích |
| --- | --- |
| BookDetails | Đọc chi tiết một sách |
| SearchBooks | Tìm kiếm sách |
| CreateBook | Tạo sách |
| PlaceOrder | Tạo đơn hàng |
| BookEvents | Theo dõi sự kiện sách |

Không tạo operation name từ user ID, request ID, timestamp hoặc giá trị input. Các giá trị này làm tên operation thay đổi theo request, khiến dashboard khó nhóm và làm tăng cardinality.

Nếu client gửi anonymous operation, server vẫn có thể thực thi nhưng observation không có tên nghiệp vụ rõ ràng. Hãy quy định client SDK và ứng dụng frontend luôn đặt operation name cho các request được phát hành.

Với document chứa nhiều operation, client cần gửi operationName để server biết operation nào được chọn. Operation name cũng cần duy nhất trong cùng document.

## Phân biệt các loại lỗi

GraphQL có nhiều giai đoạn mà lỗi có thể xuất hiện. Phân loại đúng giúp tìm đúng nơi cần điều tra.

| Loại lỗi | Thời điểm | Ví dụ | Data fetcher đã chạy? |
| --- | --- | --- | --- |
| Parse error | Đọc cú pháp document | Thiếu dấu ngoặc hoặc sai token | Chưa |
| Validation error | Đối chiếu document với schema | Field không tồn tại hoặc argument sai kiểu | Chưa |
| Variable coercion error | Chuyển variables sang kiểu schema | Gửi chuỗi cho argument Int! | Chưa thực thi operation |
| Execution error | Trong khi phân giải field | Database timeout hoặc entity không tồn tại | Có thể đã chạy một hoặc nhiều field |
| Business error | Quy tắc nghiệp vụ từ resolver/service | Hết hàng hoặc trạng thái đơn không hợp lệ | Thường đã chạy field liên quan |
| Transport error | Trước hoặc ngoài GraphQL execution | HTTP timeout, WebSocket disconnect | Không nhất thiết có GraphQL response |

### Request error và execution error

Request error xảy ra trước khi GraphQL có thể thực thi operation hợp lệ. Ví dụ document sai cú pháp, không khớp schema hoặc variables không thể coerce. Không có data fetcher nào cần chạy để tạo response cho operation đó.

Execution error xảy ra trong quá trình phân giải field. GraphQL có thể trả cả data và errors:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải tác giả",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ]
}
~~~

Response này có partial data. Client vẫn nhận được id và title, nhưng field author bị lỗi. Với GraphQL, có errors không đồng nghĩa toàn bộ request không có data.

### Null propagation có thể thay đổi phạm vi lỗi

Nếu field bị lỗi có kiểu non-null, GraphQL truyền null lên parent gần nhất có thể nhận null. Vì vậy, lỗi ở một nested field có thể làm mất một phần lớn hơn của response.

Khi điều tra, cần đọc cả:

- errors.path để biết field phát sinh lỗi.
- data để biết phần nào vẫn còn.
- schema nullability để hiểu vì sao null lan lên parent.
- extensions.code hoặc error type để phân loại nguyên nhân.

Không chỉ đếm errors. Một operation có một lỗi ở field nullable có thể vẫn hữu ích; một lỗi ở field non-null quan trọng có thể làm hỏng toàn bộ nhánh dữ liệu.

## Micrometer Observation trong Spring for GraphQL

Spring for GraphQL tích hợp Micrometer Observation để tạo metrics và traces cho request GraphQL, các data fetcher không trivial và DataLoader. Observation chỉ được phát khi ứng dụng có ObservationRegistry và GraphQL observation instrumentation được cấu hình.

Với Spring Boot, auto-configuration tạo GraphQlObservationInstrumentation khi có ObservationRegistry phù hợp. Khi dùng Boot starter cùng Actuator và observability infrastructure, thường không cần tự tạo instrumentation. Nếu tự xây dựng GraphQlSource hoặc GraphQL instance, cần đăng ký instrumentation tương ứng. [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)

Spring for GraphQL có ba observation chính:

| Observation | Phạm vi | Dùng để tìm |
| --- | --- | --- |
| graphql.request | Toàn bộ GraphQL request | Operation lỗi, request chậm, outcome |
| graphql.datafetcher | Một data fetcher không trivial | Field resolver chậm hoặc lỗi |
| graphql.dataloader | Một batch loader hoặc @BatchMapping | Batch load lỗi, batch size và hiệu quả batching |

Một request có thể tạo một graphql.request observation và nhiều graphql.datafetcher observations. Các data fetcher chạy song song hoặc theo nested selection set vẫn thuộc cùng request context.

### Các key mặc định của graphql.request

Spring for GraphQL dùng DefaultExecutionRequestObservationConvention. Các key mặc định gồm:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| graphql.operation.type | Low | query, mutation, subscription hoặc operation nếu document không parse được |
| graphql.outcome | Low | SUCCESS, REQUEST_ERROR hoặc INTERNAL_ERROR |
| graphql.execution.id | High | ExecutionId của request |
| graphql.operation.name | High | Operation name do client cung cấp |

Outcome được xác định từ GraphQL response:

- SUCCESS: response hợp lệ và không chứa errors.
- REQUEST_ERROR: request không parse được hoặc response có errors, nhưng không có error nào thuộc ErrorType.INTERNAL_ERROR.
- INTERNAL_ERROR: không tạo được GraphQL response hợp lệ hoặc response có ít nhất một error thuộc ErrorType.INTERNAL_ERROR.

Tên REQUEST_ERROR có thể gây hiểu nhầm: outcome này không chỉ bao gồm parse/validation error. Nó còn có thể bao gồm business error hoặc execution error được phân loại bằng error type khác INTERNAL_ERROR.

Nếu response có cả data và errors, outcome vẫn là REQUEST_ERROR hoặc INTERNAL_ERROR tùy ErrorType của các lỗi. Do đó, dashboard nên hiển thị outcome cùng error details thay vì diễn giải REQUEST_ERROR là request bị từ chối trước execution.

Spring for GraphQL cũng ghi các GraphQL errors trong response thành Observation Events. Những event này thường xuất hiện như span annotations trong trace, gồm error type và contextual name dựa trên error message. Điều này hữu ích để đi từ operation bị lỗi tới thông tin cụ thể trong trace.

### Các key mặc định của graphql.datafetcher

Observation graphql.datafetcher chỉ được tạo cho data fetching operation không trivial. Đọc property trực tiếp từ Java object thường được xem là trivial và không tạo observation riêng.

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| graphql.field.name | Low | Tên field đang được phân giải |
| graphql.outcome | Low | SUCCESS hoặc ERROR |
| graphql.error.type | Low | Class name của lỗi data fetching |
| graphql.field.path | High | Đường dẫn field trong response, ví dụ /book/author |

Data fetcher observation giúp tìm field cụ thể có lỗi hoặc thời gian xử lý cao. Với list, field path có thể chứa index; hãy dùng nó trong trace để điều tra một lần thực thi, không đưa path đầy đủ vào metric tag nếu path có cardinality lớn.

### Các key mặc định của graphql.dataloader

Observation graphql.dataloader theo dõi @BatchMapping và các DataLoader được đăng ký thủ công:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| graphql.loader.name | Low | Tên DataLoader |
| graphql.outcome | Low | SUCCESS hoặc ERROR |
| graphql.error.type | Low | Class name của lỗi batch loading |
| graphql.loader.size | High | Số phần tử được tải trong batch |

Nếu graphql.request có latency cao nhưng graphql.datafetcher không chỉ ra một field đơn lẻ, hãy kiểm tra DataLoader, truy vấn database và downstream client trong cùng trace.

## Bật quan sát trong Spring Boot

Với Spring Boot, thêm Actuator và registry phù hợp với hệ thống metrics. Ví dụ dùng Prometheus:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Cấu hình endpoint metrics:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        "graphql.request": true
        "graphql.datafetcher": true
~~~

Actuator cung cấp ObservationRegistry và Micrometer infrastructure theo cấu hình của ứng dụng. GraphQL observation auto-configuration chỉ hoạt động khi ObservationRegistry có mặt và các điều kiện classpath tương ứng được đáp ứng.

Nếu dùng tracing, thêm Micrometer Tracing bridge và exporter phù hợp với hệ thống đang vận hành. Metrics phù hợp để tổng hợp tỷ lệ lỗi, throughput và latency; trace phù hợp để điều tra một request cụ thể.

Để kiểm tra metrics trong môi trường local, có thể xem:

- /actuator/metrics/graphql.request
- /actuator/metrics/graphql.datafetcher
- /actuator/metrics/graphql.dataloader
- /actuator/prometheus

Tên endpoint và metric có thể được chuẩn hóa theo registry. Kiểm tra output thực tế của registry thay vì giả định mọi hệ thống export đều dùng cùng cách đặt tên.

Với ứng dụng không dùng Spring Boot, tạo GraphQlObservationInstrumentation với ObservationRegistry rồi đăng ký vào GraphQL builder. Nếu đã có instrumentation khác, kết hợp chúng bằng ChainedInstrumentation hoặc cơ chế tương ứng; không ghi đè tracing, metrics hay instrumentation đang được sử dụng.

## Theo dõi lỗi theo operation bằng metrics

Metrics cần có cardinality thấp và nhóm được qua thời gian. Mặc định, graphql.request cho biết loại operation và outcome. Operation name mặc định là high-cardinality key, phù hợp để truy vết trong trace nhưng không nên tự động biến thành metric tag.

Ví dụ các operation cố định của ứng dụng:

- BookDetails và SearchBooks thuộc nhóm catalog-read.
- CreateBook và UpdateBook thuộc nhóm catalog-write.
- PlaceOrder thuộc nhóm order-write.

Có thể mở rộng low-cardinality keys bằng ExecutionRequestObservationConvention:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class GraphQlOperationObservationConfig {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                String operationName =
                        context.getExecutionInput().getOperationName();

                String operationGroup = switch (
                        operationName == null ? "" : operationName) {
                    case "BookDetails", "SearchBooks" -> "catalog-read";
                    case "CreateBook", "UpdateBook" -> "catalog-write";
                    case "PlaceOrder" -> "order-write";
                    default -> "other";
                };

                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of(
                                "graphql.operation.group", operationGroup));
            }
        };
    }
}
~~~

Spring Boot nhận bean ExecutionRequestObservationConvention và dùng nó để tùy biến request observation. Ví dụ giữ nguyên các key mặc định rồi thêm operation group với tập giá trị hữu hạn.

Không đưa raw operation name vào low-cardinality key nếu client có thể gửi tên tùy ý. Một client lỗi hoặc độc hại có thể tạo vô số operation name khác nhau và làm tăng số time series. Nếu ứng dụng có allowlist operation cố định, có thể ánh xạ operation name sang nhóm ổn định như ví dụ.

### Metrics nên theo dõi

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Request rate theo operation group | Operation nào có lưu lượng tăng hoặc giảm bất thường? |
| Error rate theo operation group và outcome | Nhóm operation nào có tỷ lệ lỗi tăng? |
| p50, p95, p99 latency | Operation nào chậm hơn baseline? |
| Data fetcher error count theo field name | Field nào thường xuyên thất bại? |
| DataLoader error và batch size | Batch nào lỗi hoặc hoạt động không hiệu quả? |
| Request count có errors | Có bao nhiêu request trả partial data hoặc GraphQL errors? |

Ví dụ PromQL nếu registry xuất timer graphql.request theo quy ước Prometheus:

~~~promql
sum by (graphql_operation_group, graphql_outcome) (
  rate(graphql_request_seconds_count[5m])
)
~~~

Tỷ lệ request có lỗi theo operation group:

~~~promql
sum by (graphql_operation_group) (
  rate(graphql_request_seconds_count{
    graphql_outcome=~"REQUEST_ERROR|INTERNAL_ERROR"
  }[5m])
)
/
sum by (graphql_operation_group) (
  rate(graphql_request_seconds_count[5m])
)
~~~

Tên metric và label cuối cùng phụ thuộc registry naming convention và cấu hình exporter. Hãy kiểm tra dữ liệu scrape thực tế trước khi đưa query vào dashboard.

Không tạo alert chỉ dựa trên số lượng lỗi tuyệt đối. Một operation có lưu lượng lớn có thể có nhiều lỗi hơn operation ít được gọi. Hãy theo dõi tỷ lệ lỗi, số request tối thiểu và khoảng thời gian ổn định để tránh alert do một vài request đơn lẻ.

## Dùng trace để tìm nguyên nhân

Metrics cho biết operation nào đang gặp vấn đề. Trace giúp xác định request cụ thể và nơi thời gian hoặc lỗi xuất hiện.

Một trace GraphQL thường có thể liên kết:

1. HTTP server span hoặc transport observation.
2. graphql.request observation cho toàn operation.
3. graphql.datafetcher observations cho các resolver không trivial.
4. graphql.dataloader observations cho batch loading.
5. HTTP client hoặc database spans phát sinh bên trong resolver.

Spring for GraphQL ghi GraphQL errors trong response thành Observation Events của request. Khi mở trace, kiểm tra:

- Operation name và operation type.
- Execution ID.
- Outcome của request.
- Error event type và message.
- Field path ở data fetcher span.
- Các span downstream như SQL hoặc HTTP client.

Execution ID là mã riêng cho GraphQL execution. Trace ID liên kết nhiều span xuyên qua các thành phần. Hai giá trị có mục đích khác nhau: execution ID giúp tìm đúng request trong GraphQL logs; trace ID liên kết toàn bộ distributed trace.

Nếu trace HTTP và GraphQL không liên kết, kiểm tra transport instrumentation và context propagation. GraphQL request observation giả định parent observation đã được đặt vào GraphQL context bằng key micrometer.observation; HTTP transport instrumentation chịu trách nhiệm truyền trace context qua ranh giới mạng.

## Log có cấu trúc theo operation

Metrics không nên chứa message lỗi hoặc dữ liệu đầu vào có cardinality cao. Khi cần chi tiết, ghi log có cấu trúc với các trường được kiểm soát:

| Trường log | Ví dụ | Mục đích |
| --- | --- | --- |
| operationName | PlaceOrder | Xác định use case |
| operationType | mutation | Phân biệt loại operation |
| executionId | mã execution của request | Tra cứu GraphQL request |
| traceId | mã distributed trace | Mở trace xuyên dịch vụ |
| outcome | REQUEST_ERROR | Kết quả tổng thể |
| errorCode | INVENTORY_UNAVAILABLE | Phân loại lỗi ổn định |
| errorType | InventoryException | Nhận diện nhóm exception |
| fieldPath | placeOrder.items | Xác định field lỗi |
| durationMs | 184 | Phân tích latency |

Hãy log một record tổng kết khi operation kết thúc có lỗi và log exception tại nơi có đủ ngữ cảnh. Với request có nhiều lỗi, có thể ghi số lượng lỗi và danh sách error code đã chuẩn hóa; tránh lặp lại toàn bộ message dài trong mỗi log record.

Không ghi raw GraphQL query, variables, access token, password, email, địa chỉ hoặc thông tin thanh toán vào log mặc định. GraphQL query có thể chứa literal input và error message có thể chứa dữ liệu từ backend. Nếu cần debug payload, dùng chế độ lấy mẫu có thời hạn, quyền truy cập hạn chế và cơ chế redact.

Ưu tiên extensions.code ổn định cho error code. Không dùng message tự do làm khóa phân nhóm vì message có thể thay đổi theo ngôn ngữ, dữ liệu hoặc phiên bản service.

## Phân biệt GraphQL outcome và HTTP status

HTTP status mô tả kết quả ở tầng transport. GraphQL outcome mô tả kết quả xử lý GraphQL request. Hai giá trị này không thay thế nhau.

| HTTP response | GraphQL response | Cách hiểu |
| --- | --- | --- |
| 200 | data đầy đủ, không errors | GraphQL thành công |
| 200 | data một phần và errors | Một hoặc nhiều field thất bại |
| 200 | errors do execution | Operation có thể đã gọi resolver |
| 4xx | Không có GraphQL response hợp lệ | Transport hoặc request handling từ chối request |
| 5xx | Không có response hợp lệ hoặc server lỗi trước khi GraphQL trả kết quả | Điều tra transport/server |

Quy tắc status cụ thể còn phụ thuộc transport, content negotiation và phiên bản Spring for GraphQL. Vì vậy, dashboard không nên suy ra GraphQL success chỉ từ HTTP 2xx hoặc GraphQL failure chỉ từ HTTP 5xx.

Đặc biệt, nếu client chỉ retry khi HTTP status là 5xx, nó có thể bỏ qua lỗi nghiệp vụ nằm trong GraphQL response 200. Retry cần dựa trên error code và tính idempotent của operation.

## Theo dõi lỗi của subscription

Subscription có vòng đời khác query và mutation vì một operation có thể phát nhiều event theo thời gian.

- Lỗi trước khi subscription được thiết lập có thể là request/validation error.
- Lỗi trong publisher sau khi subscription bắt đầu có thể được chuyển thành GraphQL subscription error.
- WebSocket disconnect là lỗi transport và có thể xảy ra khi stream đang hoạt động.
- Một event lỗi không nhất thiết có nghĩa toàn bộ kết nối WebSocket đã đóng.

Theo dõi subscription cần tách operation registration, event delivery và connection lifecycle. Ghi nhận operation name, execution/trace context, số event phát thành công, lỗi publisher và cancellation. Không coi một WebSocket connection dài hạn là một request HTTP thông thường có thời gian xử lý ngắn.

Với subscription có lưu lượng lớn, không tạo metric label từ event ID, user ID hoặc subscription ID. Dùng những giá trị đó trong trace/log có kiểm soát; metrics chỉ nên chứa operation group, outcome và loại lỗi có tập giá trị hữu hạn.

## Kiểm thử theo dõi lỗi

Test cần xác minh cả GraphQL response và telemetry được phát.

Các trường hợp nên có:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Operation hợp lệ | graphql.request có outcome SUCCESS |
| Document sai cú pháp | graphql.request có outcome REQUEST_ERROR; không có data fetcher observation |
| Field validation error | Request bị từ chối trước khi resolver chạy |
| Resolver ném business exception đã được map | Response có error code ổn định; request outcome theo ErrorType |
| Resolver ném lỗi nội bộ | Request outcome INTERNAL_ERROR nếu error được map thành ErrorType.INTERNAL_ERROR |
| Partial data | Response giữ phần data thành công và có errors; telemetry không đánh dấu SUCCESS |
| Nested resolver lỗi | graphql.datafetcher xác định field name/path và error type |
| Batch loader lỗi | graphql.dataloader ghi outcome ERROR |
| Anonymous operation | Không có operation name; vẫn có operation type và execution ID |
| Subscription disconnect | Ghi nhận transport failure riêng với GraphQL execution outcome |

Có thể dùng GraphQlTester để gửi operation và kiểm tra response errors, path và extensions.code. Với observation, dùng Micrometer ObservationRegistry test hoặc test handler để xác minh observation name và key values. Không chỉ assert log text; kiểm tra key có cấu trúc để tránh test phụ thuộc định dạng log.

Ví dụ GraphQlTester kiểm tra error contract:

~~~java
@Test
void recordsInventoryErrorForPlaceOrder() {
    graphQlTester.document("""
            mutation PlaceOrder($input: PlaceOrderInput!) {
                placeOrder(input: $input) {
                    orderId
                }
            }
            """)
            .variable("input", Map.of(
                    "customerId", "customer-101",
                    "productId", "book-101",
                    "quantity", 2))
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).hasSize(1);
                assertThat(errors.get(0).getPath())
                        .contains("placeOrder");
                assertThat(errors.get(0).getExtensions())
                        .containsEntry("code", "INVENTORY_UNAVAILABLE");
            });
}
~~~

Đoạn test giả định fixture khiến inventory service trả lỗi và exception resolver ánh xạ nó thành error code INVENTORY_UNAVAILABLE. Test response này chưa tự chứng minh metrics đã được phát; hãy có test riêng cho ObservationConvention hoặc ObservationRegistry.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Dashboard chỉ có một route /graphql | Chỉ dùng HTTP request metrics | Bổ sung graphql.request và operation metadata |
| Request HTTP 200 nhưng dashboard báo thành công | Chỉ dựa vào HTTP status | Theo dõi graphql.outcome và response errors |
| Không thấy datafetcher observation cho validation error | Resolver chưa chạy | Dùng graphql.request observation để theo dõi request error |
| Không thấy nested property trong trace | Property fetcher được xem là trivial | Tập trung vào non-trivial resolver và service spans |
| Operation name làm tăng time series | Đưa tên tùy ý vào low-cardinality tag | Dùng operation group có tập giá trị hữu hạn |
| Không tìm được nguyên nhân từ metric | Metric chỉ cho biết outcome và latency | Mở trace theo execution ID/trace ID |
| Lỗi bị nhóm sai thành client error | Business error và validation error dùng cùng ErrorType | Chuẩn hóa ErrorType và extensions.code theo nhóm lỗi |
| Log có quá nhiều dữ liệu nhạy cảm | Ghi raw query, variables hoặc exception message | Redact và chỉ log metadata cần thiết |
| Alert nhảy do một vài request | Dùng error count tuyệt đối | Dùng error ratio, minimum traffic và cửa sổ thời gian |
| Lỗi subscription bị xem như HTTP request error | Không tách transport và event stream | Theo dõi publisher, operation và connection lifecycle |
| Instrumentation không phát observation | Thiếu ObservationRegistry hoặc GraphQL instrumentation | Kiểm tra Boot auto-configuration hoặc đăng ký thủ công |

## Thực hành tổng hợp

Thiết lập theo dõi lỗi cho API thư viện:

1. Đặt operation name ổn định cho BookDetails, SearchBooks, CreateBook và PlaceOrder.
2. Thêm Spring Boot Actuator và Micrometer registry.
3. Xác minh graphql.request, graphql.datafetcher và graphql.dataloader xuất hiện.
4. Gửi một query hợp lệ và kiểm tra outcome SUCCESS.
5. Gửi document sai cú pháp và kiểm tra REQUEST_ERROR, không có resolver observation.
6. Làm BookDetails trả partial data với lỗi ở author; kiểm tra response data/errors và request outcome.
7. Làm PlaceOrder thất bại do inventory; kiểm tra error code và field path.
8. Kiểm tra lỗi nội bộ được map thành ErrorType.INTERNAL_ERROR.
9. Thêm ExecutionRequestObservationConvention để gắn operation group có cardinality thấp.
10. Xuất metrics và tạo dashboard theo operation group, outcome và latency.
11. Mở trace của một request lỗi để xem error event và datafetcher span.
12. Tạo structured log gồm operation name, execution ID, trace ID, error code và field path.
13. Thử subscription bị publisher error và WebSocket disconnect; xác minh hai loại lỗi được phân biệt.
14. Thiết lập alert theo tỷ lệ lỗi và p95 latency, có ngưỡng lưu lượng tối thiểu.

Sau khi hoàn thành, hãy giải thích vì sao HTTP 200 không đồng nghĩa GraphQL operation thành công, vì sao operation name mặc định là high-cardinality key và cách đi từ metric tới trace để tìm field lỗi.

## Ghi nhớ

Theo dõi lỗi theo operation bắt đầu từ operation name ổn định. Spring for GraphQL cung cấp graphql.request cho toàn request, graphql.datafetcher cho resolver không trivial và graphql.dataloader cho batch loading. graphql.outcome có ba giá trị SUCCESS, REQUEST_ERROR và INTERNAL_ERROR; REQUEST_ERROR có thể bao gồm response partial data với errors. Operation name và execution ID là high-cardinality keys phù hợp cho trace, không nên tự động đưa vào metric tags. Dùng ExecutionRequestObservationConvention để ánh xạ operation vào nhóm hữu hạn, metrics để phát hiện xu hướng, trace để tìm field và downstream span, log có cấu trúc để lưu error code và correlation ID. Luôn phân biệt GraphQL outcome với HTTP status và bảo vệ dữ liệu nhạy cảm trong log/trace.

## Tài liệu tham khảo

- [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [ExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/ExecutionRequestObservationConvention.html)
- [DefaultExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DefaultExecutionRequestObservationConvention.html)
- [GraphQL Java – Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [Spring Boot – Metrics and Observability](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
