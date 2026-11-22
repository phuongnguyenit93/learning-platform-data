# Xử lý lỗi Subscription trong Spring for GraphQL

GraphQL subscription duy trì một luồng sự kiện sau khi client đăng ký thành công. Vì luồng có thể chạy trong thời gian dài, lỗi có thể xuất hiện ở nhiều thời điểm: khi kiểm tra request, khi tạo publisher, trong lúc resolve một event hoặc khi publisher kết thúc bằng tín hiệu lỗi.

Điểm quan trọng trong Spring for GraphQL là phân biệt lỗi của một lần thực thi field với lỗi kết thúc subscription publisher. DataFetcherExceptionResolver xử lý exception từ data fetcher trong quá trình GraphQL thực thi. Khi publisher của subscription đã được trả về và transport bắt đầu subscribe, nếu publisher phát onError, cần dùng SubscriptionExceptionResolver để chuyển exception thành danh sách GraphQLError gửi về client.

## 1. Vòng đời Subscription và các điểm có thể phát sinh lỗi

Ví dụ schema theo dõi thay đổi đơn hàng:

~~~graphql
type Query {
    order(id: ID!): Order
}

type Subscription {
    orderUpdated(orderId: ID!): OrderEvent!
}

type Order {
    id: ID!
    status: String!
}

type OrderEvent {
    orderId: ID!
    status: String!
    occurredAt: String!
}
~~~

Client đăng ký:

~~~graphql
subscription TrackOrder {
    orderUpdated(orderId: "order-10") {
        orderId
        status
        occurredAt
    }
}
~~~

Sau khi subscription được thiết lập, server phát một GraphQL response cho mỗi event. Luồng có thể tiếp tục cho đến khi client hủy, publisher complete hoặc publisher kết thúc bằng lỗi.

~~~mermaid
flowchart TD
    A[Client gửi Subscription] --> B[Parse và validate document]
    B -->|Request không hợp lệ| C[Request-level GraphQL errors]
    B -->|Hợp lệ| D[Chạy @SubscriptionMapping]
    D -->|Method ném lỗi trước khi trả Publisher| E[DataFetcherExceptionResolver]
    D -->|Trả Publisher| F[Transport subscribe]
    F --> G[Publisher phát event]
    G --> H[GraphQL resolve selection set]
    H -->|Lỗi field của event| I[DataFetcherExceptionResolver]
    I --> J[Response của event có data/errors]
    H -->|Thành công| J
    J --> G
    F -->|Publisher onError| K[SubscriptionExceptionResolver]
    K --> L[Transport gửi thông báo lỗi cuối]
    F -->|Complete hoặc client cancel| M[Kết thúc subscription]
~~~

Sơ đồ thể hiện các điểm xử lý lỗi khác nhau. Một lỗi field trong event có thể được ghi vào response của event đó, trong khi lỗi terminal của publisher kết thúc toàn bộ subscription.

## 2. Phân biệt các loại lỗi Subscription

| Thời điểm | Ví dụ | Cơ chế xử lý phù hợp |
| --- | --- | --- |
| Trước execution | GraphQL document sai cú pháp, field không tồn tại, argument sai kiểu | Request-level GraphQL errors; chưa có data fetcher để xử lý. |
| Khi gọi method @SubscriptionMapping | Không tìm thấy stream hoặc không thể khởi tạo publisher | DataFetcherExceptionResolver như exception từ data fetcher ban đầu. |
| Khi resolve field của một event | Resolver của OrderEvent.customer gặp lỗi | DataFetcherExceptionResolver; lỗi thuộc response của event đó. |
| Publisher đã chạy rồi phát onError | Broker mất kết nối, event source timeout, stream hỏng | SubscriptionExceptionResolver; transport gửi lỗi kết thúc subscription. |
| Client mất kết nối transport | WebSocket bị đóng hoặc mạng gián đoạn | Client xử lý GraphQlTransportException và chính sách kết nối lại. |

Không phải mọi lỗi xảy ra trong lúc client đang dùng subscription đều là publisher error. Ví dụ, nếu một event được phát ra nhưng resolver của field con thất bại, GraphQL có thể trả event đó với data một phần và errors; publisher nguồn vẫn có thể phát event tiếp theo.

## 3. Vì sao DataFetcherExceptionResolver không xử lý publisher error?

Data fetcher của root subscription chỉ có nhiệm vụ tạo và trả publisher ban đầu. Sau đó transport subscribe vào publisher để nhận event. Nếu publisher phát tín hiệu onError sau thời điểm đó, lỗi không còn phát sinh trong lần gọi data fetcher ban đầu.

Vì vậy, DataFetcherExceptionResolver không thể xử lý exception kết thúc subscription publisher. Spring for GraphQL cung cấp contract riêng là SubscriptionExceptionResolver cho trường hợp này.

Hãy nhớ ba quy tắc:

- Method @SubscriptionMapping ném exception trước khi trả publisher: xử lý như exception của data fetcher.
- Data fetcher của field trong từng event ném exception: xử lý bằng DataFetcherExceptionResolver.
- Publisher nguồn phát onError sau khi subscription đã được thiết lập: xử lý bằng SubscriptionExceptionResolver.

## 4. Tạo Subscription resolver bằng SubscriptionExceptionResolverAdapter

SubscriptionExceptionResolverAdapter là lớp tiện ích của Spring for GraphQL, nằm trong package org.springframework.graphql.execution. Adapter triển khai phần reactive contract và cho phép override resolveToSingleError hoặc resolveToMultipleErrors.

Ví dụ ánh xạ lỗi event source thành GraphQL error an toàn:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.execution.SubscriptionExceptionResolverAdapter;
import org.springframework.stereotype.Component;

@Component
public class OrderSubscriptionExceptionResolver
        extends SubscriptionExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(Throwable exception) {
        if (exception instanceof OrderEventSourceException) {
            return GraphqlErrorBuilder.newError()
                    .message("Không thể tiếp tục nhận cập nhật đơn hàng")
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .extensions(Map.of("code", "ORDER_EVENT_SOURCE_UNAVAILABLE"))
                    .build();
        }

        return null;
    }
}
~~~

Trong ví dụ:

- Chỉ OrderEventSourceException được resolver này xử lý.
- resolveToSingleError trả một GraphQLError có message tổng quát và mã lỗi ổn định.
- Trả null có nghĩa resolver này không nhận xử lý exception đó; resolver tiếp theo có thể thử.
- Không đưa stack trace, thông tin broker, địa chỉ server hoặc dữ liệu nhạy cảm vào message trả về client.

Adapter cũng hỗ trợ resolveToMultipleErrors nếu một exception cần được biểu diễn thành nhiều GraphQL errors. Thông thường một lỗi terminal của stream chỉ cần một error có mã rõ ràng.

## 5. Đăng ký SubscriptionExceptionResolver

Với Spring Boot GraphQL starter, các bean triển khai SubscriptionExceptionResolver được tự động phát hiện và thêm vào GraphQlSource theo thứ tự. Vì vậy, ví dụ @Component ở phần trước có thể được đăng ký tự động.

Nếu ứng dụng tự xây dựng GraphQlSource, hãy thêm resolver vào builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResource)
        .subscriptionExceptionResolvers(List.of(orderSubscriptionExceptionResolver))
        .build();
~~~

Đoạn code giả định schemaResource và orderSubscriptionExceptionResolver đã được tạo hoặc inject. Khi tự cấu hình GraphQlSource, cần bảo đảm danh sách resolver thực sự được gắn vào source mà ExecutionGraphQlService đang sử dụng.

Có thể đăng ký nhiều SubscriptionExceptionResolver. Spring gọi chúng theo thứ tự cho đến khi một resolver trả về danh sách errors. Hãy sắp xếp resolver chuyên biệt trước resolver tổng quát để lỗi domain được ánh xạ đúng.

## 6. Resolver trả về rỗng có hai ý nghĩa khác nhau

Contract SubscriptionExceptionResolver trả về Mono<List<GraphQLError>>:

| Kết quả | Ý nghĩa |
| --- | --- |
| Mono.just(List.of(error)) | Đã xử lý exception và có error gửi client. |
| Mono.just(List.of()) | Đã xử lý exception nhưng chủ ý không gửi GraphQL error. |
| Mono.empty() | Resolver không xử lý; cho phép resolver tiếp theo thử. |

Khi kế thừa SubscriptionExceptionResolverAdapter, trả null từ resolveToSingleError hoặc resolveToMultipleErrors biểu thị chưa xử lý. Không nhầm Mono.empty() với Mono.just(List.of()): một trường hợp nhường cho resolver khác, trường hợp còn lại xác nhận đã xử lý mà không gửi lỗi.

Không nên trả danh sách rỗng chỉ để che giấu mọi lỗi. Nếu stream kết thúc mà client không nhận được thông tin lỗi, giao diện có thể nghĩ subscription đã kết thúc bình thường hoặc không biết vì sao không còn event.

## 7. Ánh xạ lỗi trong @SubscriptionMapping

Controller nên tập trung tạo publisher và chuyển lỗi kỹ thuật thành exception domain có ý nghĩa. Resolver chuyên trách sẽ quyết định cách chuyển exception đó thành GraphQL error.

~~~java
import java.time.Duration;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

@Controller
public class OrderSubscriptionController {

    private final OrderEventService eventService;

    public OrderSubscriptionController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderUpdated(@Argument("orderId") String orderId) {
        return eventService.events(orderId)
                .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                        .filter(this::isTransientFailure))
                .onErrorMap(error -> new OrderEventSourceException(error));
    }

    private boolean isTransientFailure(Throwable error) {
        return error instanceof EventBrokerUnavailableException
                || error instanceof EventSourceTimeoutException;
    }
}
~~~

Ví dụ giả định eventService.events trả về Flux<OrderEvent>. Publisher thử lại tối đa ba lần với backoff cho lỗi tạm thời; nếu vẫn thất bại, onErrorMap chuyển lỗi thành OrderEventSourceException. Khi publisher cuối cùng phát onError, OrderSubscriptionExceptionResolver có thể ánh xạ lỗi đó thành GraphQL error.

Không retry vô hạn mọi exception. Lỗi validation, quyền truy cập hoặc lỗi nghiệp vụ không thể khắc phục bằng retry cần kết thúc sớm. Retry có thể khiến event được phát lại hoặc bỏ sót event quanh thời điểm reconnect; với stream cần độ tin cậy cao, nên có event ID/cursor và cơ chế resume.

## 8. Lỗi của một event khác với lỗi kết thúc stream

Giả sử publisher đã phát một OrderEvent, nhưng resolver của field customer trong event đó thất bại. Đây là lỗi khi GraphQL hoàn tất selection set của event. Nó được xử lý như lỗi data fetcher thông thường và xuất hiện trong response của event đó.

~~~json
{
  "data": {
    "orderUpdated": {
      "orderId": "order-10",
      "status": "SHIPPED",
      "customer": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải thông tin khách hàng",
      "path": ["orderUpdated", "customer"]
    }
  ]
}
~~~

Response minh họa này có thể được phát ra cho một event, trong khi publisher tiếp tục phát event tiếp theo nếu nguồn vẫn hoạt động. Null propagation còn phụ thuộc nullability trong SDL.

Ngược lại, nếu event broker ngắt kết nối và publisher phát onError, subscription không còn event tiếp theo. Spring gọi SubscriptionExceptionResolver, rồi transport gửi thông báo lỗi cuối cho client.

## 9. Muốn tiếp tục stream sau lỗi thì phải phục hồi publisher

SubscriptionExceptionResolver chỉ chuyển exception terminal thành GraphQL errors. Nó không khởi động lại publisher, không phát event thay thế và không giữ subscription sống.

Nếu lỗi có thể phục hồi và nghiệp vụ muốn subscription tiếp tục, hãy xử lý ngay trong Reactor pipeline trước khi publisher kết thúc:

~~~java
return eventService.events(orderId)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                .filter(this::isTransientFailure));
~~~

Hoặc dùng onErrorResume để chuyển sang một publisher dự phòng khi điều đó có ý nghĩa:

~~~java
return eventService.events(orderId)
        .onErrorResume(CacheUnavailableException.class,
                error -> fallbackEventService.events(orderId));
~~~

Chỉ dùng fallback nếu nguồn thay thế có thể cung cấp dữ liệu đúng contract và bảo đảm quyền truy cập tương đương. Không chuyển một lỗi bảo mật hoặc lỗi dữ liệu thành stream rỗng để che giấu vấn đề.

Nếu cần báo cho client một cảnh báo nhưng vẫn tiếp tục stream, mô hình hóa cảnh báo như một event trong schema thay vì phát terminal GraphQL error.

## 10. Mô hình hóa cảnh báo thành event nếu stream cần tiếp tục

GraphQL error terminal phù hợp khi subscription không thể tiếp tục. Nếu một cảnh báo là một phần hợp lệ của luồng nghiệp vụ, có thể biểu diễn nó bằng union:

~~~graphql
type OrderChanged {
    orderId: ID!
    status: String!
}

type OrderStreamWarning {
    code: String!
    message: String!
}

union OrderSubscriptionEvent = OrderChanged | OrderStreamWarning

type Subscription {
    orderEvents(orderId: ID!): OrderSubscriptionEvent!
}
~~~

Client có thể phân biệt event cập nhật với cảnh báo:

~~~graphql
subscription {
    orderEvents(orderId: "order-10") {
        __typename
        ... on OrderChanged {
            orderId
            status
        }
        ... on OrderStreamWarning {
            code
            message
        }
    }
}
~~~

Với mô hình này, cảnh báo là dữ liệu trong một event và publisher có thể tiếp tục. Không đưa stack trace hoặc chi tiết hạ tầng vào message; payload cảnh báo vẫn phải tuân theo chính sách bảo mật của API.

## 11. Client nhận Subscription error như thế nào?

Với WebSocketGraphQlClient, nếu server gửi thông báo error cuối cùng cho subscription, Flux phía client kết thúc bằng SubscriptionErrorException. Exception cung cấp getErrors() để đọc danh sách GraphQL errors trong payload.

Ví dụ:

~~~java
import org.springframework.graphql.client.SubscriptionErrorException;
import reactor.core.publisher.Flux;

Flux<OrderEvent> updates = graphQlClient.document("""
        subscription TrackOrder {
            orderUpdated(orderId: "order-10") {
                orderId
                status
            }
        }
        """)
        .retrieveSubscription("orderUpdated")
        .toEntity(OrderEvent.class);

updates.doOnError(error -> {
    if (error instanceof SubscriptionErrorException subscriptionError) {
        subscriptionError.getErrors().forEach(item ->
                log.warn("Subscription ended with GraphQL error: {}", item.getMessage()));
    }
}).subscribe(this::handleOrderEvent);
~~~

Đoạn code giả định graphQlClient là WebSocketGraphQlClient, log và handleOrderEvent đã được định nghĩa. retrieveSubscription giải mã một field từ mỗi response. Khi server kết thúc subscription bằng error message, stream phát lỗi thay vì tiếp tục phát OrderEvent.

## 12. Phân biệt SubscriptionErrorException và lỗi transport

Không phải mọi lỗi phía client đều do server chủ động kết thúc subscription:

| Lỗi client | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| SubscriptionErrorException | Server gửi thông báo lỗi GraphQL cuối cùng cho subscription | Đọc getErrors(), phân loại mã lỗi và quyết định có thể đăng ký lại không. |
| WebSocketDisconnectedException | Kết nối WebSocket bị đóng hoặc mất | Kiểm tra kết nối và chính sách reconnect. |
| GraphQlTransportException | Lỗi ở tầng transport | Phân loại theo nguyên nhân cụ thể; không coi tất cả là lỗi nghiệp vụ. |
| GraphQL errors trong một event response | Một field của event bị lỗi nhưng response event vẫn được phát | Đọc errors theo field và quyết định hiển thị dữ liệu một phần. |

SubscriptionErrorException là một loại GraphQlTransportException, nhưng mang danh sách GraphQL errors từ thông báo error của WebSocket. Lỗi mất kết nối là tình huống khác và có thể cần chiến lược reconnect riêng.

## 13. Retry ở client và khả năng nhận event trùng

Client có thể dùng Reactor retryWhen để đăng ký lại sau lỗi transport hoặc lỗi subscription có thể phục hồi. Tuy nhiên, reconnect không đồng nghĩa khôi phục chính xác vị trí stream trước đó.

Ví dụ đơn giản:

~~~java
updates.retryWhen(Retry.backoff(3, Duration.ofSeconds(2))
        .filter(this::isRetryableSubscriptionFailure));
~~~

Chỉ retry các lỗi được xác định là tạm thời. Không retry liên tục lỗi FORBIDDEN, UNAUTHORIZED, lỗi request hoặc subscription bị từ chối vì trạng thái nghiệp vụ.

Với event quan trọng, thiết kế thêm:

- Event ID duy nhất để client loại bỏ event trùng.
- Cursor hoặc offset để client yêu cầu tiếp tục từ vị trí đã xử lý.
- Quy tắc lưu checkpoint sau khi event được xử lý thành công.
- Cơ chế server replay event trong một khoảng thời gian xác định.

Nếu không có cursor/replay, client có thể bỏ lỡ event trong khoảng thời gian kết nối bị ngắt. Nếu server gửi lại event cũ khi reconnect, client có thể nhận trùng. Đây là yêu cầu thiết kế dữ liệu/transport, không được giải quyết chỉ bằng SubscriptionExceptionResolver.

## 14. Bảo mật thông tin trong subscription errors

Subscription thường chạy lâu và có thể chứa dữ liệu theo user hoặc tenant. Khi ánh xạ lỗi:

1. Không trả exception message thô từ database, broker hoặc HTTP client.
2. Không đưa token, header xác thực, SQL, host nội bộ hoặc stack trace vào extensions.
3. Dùng mã lỗi ổn định để client phân loại, ví dụ ORDER_EVENT_SOURCE_UNAVAILABLE.
4. Chỉ trả thông tin đủ để client quyết định hiển thị lỗi hoặc yêu cầu đăng ký lại.
5. Ghi log nguyên nhân ở server với correlation ID/execution metadata phù hợp.
6. Không ghi payload event hoặc dữ liệu cá nhân nhạy cảm nếu không cần thiết.

Nếu quyền truy cập bị thu hồi giữa lúc stream đang chạy, cần có chính sách kết thúc subscription hoặc ngừng phát event. Đừng giả định authorization chỉ cần kiểm tra một lần khi đăng ký nếu nghiệp vụ yêu cầu quyền được cập nhật liên tục.

## 15. Logging và quan sát lỗi

Khi xử lý publisher error, nên ghi nhận:

- Tên subscription field hoặc operation name.
- Mã lỗi GraphQL được gửi về client.
- Correlation ID hoặc execution ID nếu có.
- Thời điểm stream bắt đầu và kết thúc.
- Số event đã phát trước khi lỗi.
- Nguyên nhân nội bộ đã được phân loại.
- Số lần retry và kết quả reconnect nếu có.

Không dùng doOnError để thay thế SubscriptionExceptionResolver. doOnError chỉ quan sát lỗi trong publisher; resolver chịu trách nhiệm ánh xạ lỗi terminal thành GraphQL errors. Có thể dùng cả hai: Reactor operator ghi metrics/correlation, còn resolver chuẩn hóa lỗi cho transport.

## 16. Kiểm thử Subscription error

Nên có kiểm thử ở nhiều tầng.

### Kiểm thử SubscriptionExceptionResolver

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void mapsOrderEventSourceException() {
    OrderSubscriptionExceptionResolver resolver =
            new OrderSubscriptionExceptionResolver();

    StepVerifier.create(resolver.resolveException(
                    new OrderEventSourceException(new RuntimeException("broker down"))))
            .assertNext(errors -> {
                assertThat(errors).hasSize(1);
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Không thể tiếp tục nhận cập nhật đơn hàng");
            })
            .verifyComplete();
}
~~~

Test này kiểm tra resolver ánh xạ exception thành một GraphQL error và không để message nội bộ broker down lọt ra ngoài.

### Kiểm thử stream phát event rồi kết thúc bằng lỗi

Với tester hỗ trợ subscription, có thể kiểm tra event trước lỗi và tín hiệu lỗi cuối:

~~~java
Flux<String> statuses = graphQlTester.document("""
        subscription {
            orderUpdated(orderId: "order-10") {
                status
            }
        }
        """)
        .executeSubscription()
        .toFlux("orderUpdated.status", String.class);

StepVerifier.create(statuses)
        .expectNext("CREATED")
        .expectError()
        .verify();
~~~

Đây là ví dụ khung: test fixture cần tạo publisher phát CREATED rồi phát lỗi OrderEventSourceException, và GraphQL source phải được cấu hình với SubscriptionExceptionResolver. Nếu cần kiểm tra chính xác lỗi đã được gửi qua WebSocket, dùng WebSocketGraphQlTester hoặc WebSocketGraphQlClient trong integration test và xác nhận SubscriptionErrorException.getErrors().

### Các tình huống cần kiểm thử

1. Request subscription sai schema bị từ chối trước khi tạo publisher.
2. Method @SubscriptionMapping ném exception khi khởi tạo publisher.
3. Publisher phát một hoặc nhiều event rồi kết thúc bằng onError.
4. SubscriptionExceptionResolver ánh xạ exception domain đúng mã và message.
5. Exception không được resolver hiện tại nhận sẽ được resolver tiếp theo thử.
6. Lỗi resolver của field con chỉ ảnh hưởng response event tương ứng theo nullability.
7. Retry publisher chỉ áp dụng cho lỗi tạm thời và có giới hạn.
8. Client phân biệt SubscriptionErrorException với lỗi mất kết nối transport.
9. Client hủy subscription thì upstream được cancel và giải phóng tài nguyên.
10. Error payload không làm lộ dữ liệu nội bộ.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| DataFetcherExceptionResolver không bắt được lỗi stream | Publisher đã được trả về và lỗi xảy ra sau khi transport subscribe | Đăng ký SubscriptionExceptionResolver. |
| @GraphQlExceptionHandler không xử lý publisher onError | Handler method chỉ xử lý exception trong quá trình data fetcher/controller invocation | Dùng SubscriptionExceptionResolver cho lỗi terminal. |
| Client chỉ nhận thông báo stream kết thúc | Không có resolver ánh xạ lỗi hoặc resolver chưa được đăng ký | Kiểm tra bean discovery hoặc GraphQlSource builder. |
| Stream dừng sau một lỗi tạm thời | Publisher phát onError và không có retry/recovery | Dùng retry/fallback trong publisher nếu nghiệp vụ cho phép. |
| Retry gây event trùng | Server/client reconnect mà không có event ID hoặc cursor | Thiết kế deduplication và resume. |
| Resolver biến mọi lỗi thành cùng một mã | Không phân loại exception hoặc catch-all quá rộng | Ánh xạ lỗi domain cụ thể, để lỗi không biết được xử lý tiếp. |
| Client retry cả lỗi quyền truy cập | Không phân biệt SubscriptionErrorException với lỗi transport hoặc error code | Chỉ retry lỗi có thể phục hồi. |
| Lộ thông tin broker/database | Dùng exception message làm GraphQL message | Dùng message tổng quát và mã lỗi ổn định. |
| Cảnh báo nghiệp vụ làm kết thúc stream | Dùng Flux.error cho điều kiện cần tiếp tục | Mô hình hóa warning thành event dữ liệu. |

## 18. Checklist xử lý Subscription error

1. Phân loại lỗi theo giai đoạn: request, khởi tạo resolver, event field hay publisher terminal.
2. Dùng DataFetcherExceptionResolver cho lỗi data fetcher trong execution.
3. Dùng SubscriptionExceptionResolver cho publisher onError sau khi subscription bắt đầu.
4. Đăng ký resolver qua Spring Boot bean discovery hoặc GraphQlSource.Builder.
5. Trả GraphQL error có mã ổn định, message an toàn và classification phù hợp.
6. Để resolver không phù hợp trả null/unresolved nhằm nhường cho resolver kế tiếp.
7. Dùng retry/fallback bên trong publisher nếu lỗi có thể phục hồi và nghiệp vụ cho phép.
8. Mô hình hóa cảnh báo cần tiếp tục stream thành event dữ liệu.
9. Phân biệt SubscriptionErrorException với lỗi mất kết nối transport ở client.
10. Thiết kế event ID/cursor nếu cần resume và chống event trùng.
11. Kiểm thử lỗi terminal, lỗi từng event, retry, cancellation và bảo mật error payload.

SubscriptionExceptionResolver là extension point dành riêng cho lỗi terminal của publisher subscription. Khi tách đúng lỗi request, lỗi field trong từng event và lỗi onError của stream, ứng dụng có thể trả GraphQL errors nhất quán, giữ được các event hợp lệ và giúp client quyết định đúng giữa hiển thị lỗi, retry hoặc đăng ký lại.

Tài liệu tham khảo: [Spring for GraphQL — Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-exceptions-subscriptions), [SubscriptionExceptionResolver API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/SubscriptionExceptionResolver.html), và [Spring for GraphQL Client — Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html#client.graphqlclient.requests.subscriptions).
