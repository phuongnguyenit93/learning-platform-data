# Flux cho subscription

GraphQL Subscription cho phép client nhận dữ liệu khi một sự kiện mới xảy ra, thay vì gửi query lặp đi lặp lại để hỏi trạng thái hiện tại. Ví dụ, client có thể theo dõi tồn kho của một sản phẩm, trạng thái xử lý đơn hàng hoặc cập nhật trực tiếp của một phiên đấu giá.

Trong Spring for GraphQL, một phương thức được đánh dấu **@SubscriptionMapping** thường trả về **Flux<T>** của Project Reactor. Mỗi phần tử được phát ra từ Flux trở thành một lần thực thi kết quả cho subscription field. Client nhận nhiều GraphQL response payload trong suốt thời gian subscription còn hoạt động.

Flux biểu diễn một luồng dữ liệu có thể phát ra nhiều phần tử theo thời gian, kết thúc bình thường hoặc kết thúc bằng lỗi. Vì vậy, khi xây dựng subscription, cần hiểu cả kiểu trả về, vòng đời publisher, transport, cancellation, backpressure và cách xử lý lỗi sau khi luồng đã bắt đầu.

## Subscription khác Query như thế nào?

Query lấy trạng thái dữ liệu tại thời điểm thực thi. Subscription đăng ký nhận những thay đổi trong tương lai:

| Đặc điểm | Query | Subscription |
| --- | --- | --- |
| Mục đích | Đọc dữ liệu hiện tại | Nhận sự kiện theo thời gian |
| Kiểu kết quả thường gặp | Object hoặc collection | Publisher như Flux |
| Vòng đời | Hoàn tất sau một response | Có thể kéo dài đến khi complete, error hoặc cancel |
| Transport | Thường dùng HTTP | Thường dùng WebSocket hoặc RSocket |
| Số response | Một response GraphQL | Nhiều response payload trong một operation |

Ví dụ Query trả tồn kho hiện tại:

~~~graphql
type Query {
  stock(productId: ID!): Stock
}
~~~

Subscription theo dõi thay đổi tồn kho:

~~~graphql
type Subscription {
  stockChanged(productId: ID!): StockEvent!
}
~~~

Query trả về snapshot hiện tại. Subscription phát ra các StockEvent khi có thay đổi sau khi client đăng ký.

## Khai báo Subscription field trong SDL

GraphQL định nghĩa root type tên Subscription:

~~~graphql
type Subscription {
  stockChanged(productId: ID!): StockEvent!
}

type StockEvent {
  eventId: ID!
  productId: ID!
  availableQuantity: Int!
  occurredAt: String!
}
~~~

DTO Java tương ứng có thể dùng String cho occurredAt vì schema đang khai báo String:

~~~java
public record StockEvent(
        String eventId,
        String productId,
        int availableQuantity,
        String occurredAt) {
}
~~~

Argument productId xác định sản phẩm client muốn theo dõi. Kiểu trả về StockEvent! mô tả một event trong mỗi payload. Dấu ! yêu cầu mỗi lần phát ra phải có một StockEvent khác null.

Một Subscription operation theo đặc tả GraphQL có đúng một root field. Client có thể chọn nhiều field con trong payload của root field đó:

~~~graphql
subscription WatchStock($productId: ID!) {
  stockChanged(productId: $productId) {
    eventId
    productId
    availableQuantity
    occurredAt
  }
}
~~~

Variables được gửi cùng operation:

~~~json
{
  "productId": "product-42"
}
~~~

Mỗi event được phát ra tạo một response có dạng:

~~~json
{
  "data": {
    "stockChanged": {
      "eventId": "evt-1001",
      "productId": "product-42",
      "availableQuantity": 18,
      "occurredAt": "2026-11-20T10:15:30Z"
    }
  }
}
~~~

Nếu Flux phát ra ba event, client nhận ba payload riêng biệt. GraphQL runtime phân giải selection set cho từng event, vì vậy client có thể chọn nested fields giống như khi truy vấn object từ Query.

## Ánh xạ Subscription bằng @SubscriptionMapping

Spring for GraphQL cung cấp annotation @SubscriptionMapping để ánh xạ field của root Subscription vào một phương thức controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class StockSubscriptionController {

    private final InventoryEventService eventService;

    public StockSubscriptionController(InventoryEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<StockEvent> stockChanged(@Argument String productId) {
        return eventService.eventsFor(productId);
    }
}
~~~

Tên phương thức stockChanged được dùng làm tên field mặc định. Nếu tên Java khác tên field trong SDL, có thể khai báo tường minh:

~~~java
@SubscriptionMapping("stockChanged")
public Flux<StockEvent> watchProduct(@Argument String productId) {
    return eventService.eventsFor(productId);
}
~~~

Phương thức nhận argument giống các annotated controller khác. Spring bind productId từ GraphQL operation rồi gọi resolver để lấy publisher. Publisher được GraphQL runtime subscribe và các phần tử của nó được phân giải thành payload.

Không trả về một List nếu mục tiêu là phát dữ liệu theo thời gian. List là một collection đã có sẵn; Flux biểu diễn một publisher có thể phát nhiều phần tử bất đồng bộ.

## Xây dựng Flux từ service

Controller nên giữ vai trò ánh xạ GraphQL field và chuyển argument xuống service. Service chịu trách nhiệm lấy event từ nguồn dữ liệu:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class InventoryEventService {

    private final InventoryEventSource eventSource;

    public InventoryEventService(InventoryEventSource eventSource) {
        this.eventSource = eventSource;
    }

    public Flux<StockEvent> eventsFor(String productId) {
        return Flux.defer(() -> eventSource.eventsFor(productId));
    }
}
~~~

InventoryEventSource là abstraction đại diện cho nguồn event, chẳng hạn message broker, event bus nội bộ hoặc một publisher được quản lý. Flux.defer trì hoãn lời gọi eventsFor cho tới khi có subscriber. Nó không tự biến một nguồn hot thành cold; cold hay hot vẫn phụ thuộc implementation mà eventSource trả về.

Ví dụ interface:

~~~java
public interface InventoryEventSource {
    Flux<StockEvent> eventsFor(String productId);
}
~~~

Trong hệ thống thực tế, nguồn event nên lọc theo topic, partition, routing key hoặc consumer filter để tránh đọc mọi sự kiện rồi mới lọc trong ứng dụng. Nếu nguồn không hỗ trợ lọc, service có thể dùng filter như một lớp bảo vệ bổ sung. Implementation cụ thể phụ thuộc broker và cách phân phối event của hệ thống.

## Flux cold và hot

Reactor có hai nhóm publisher thường gặp:

- **Cold publisher:** bắt đầu tạo hoặc đọc dữ liệu khi có subscriber. Mỗi subscriber thường có một quá trình thực thi riêng.
- **Hot publisher:** phát dữ liệu độc lập với subscriber. Subscriber mới có thể bỏ lỡ những event đã phát trước khi đăng ký.

Ví dụ cold publisher:

~~~java
Flux<StockEvent> events = Flux.defer(() ->
        eventRepository.streamEventsFor("product-42"));
~~~

Nếu eventRepository tạo một truy vấn hoặc subscription mới mỗi lần được gọi, mỗi subscriber sẽ kích hoạt một lần đăng ký nguồn dữ liệu mới. Chỉ bọc một Flux hot có sẵn trong Flux.defer không làm nó trở thành cold.

Ví dụ hot publisher:

~~~java
import reactor.core.publisher.Sinks;

Sinks.Many<StockEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<StockEvent> events = sink.asFlux();
~~~

Một thành phần khác phát event:

~~~java
import java.time.Instant;

StockEvent stockEvent = new StockEvent(
        "evt-1001", "product-42", 18, Instant.now().toString());

Sinks.EmitResult result = sink.tryEmitNext(stockEvent);
if (result.isFailure()) {
    // Ghi nhận lỗi phát event và áp dụng chính sách phù hợp
}
~~~

Sinks là cách tạo publisher hot hữu ích cho demo hoặc event bus trong bộ nhớ. Với ứng dụng nhiều instance, event quan trọng hoặc cần replay, nên dùng broker hoặc event store có khả năng lưu trữ và phân phối phù hợp. Không giả định một Sinks trong bộ nhớ có thể thay thế message broker bền vững.

Nếu dùng hot publisher, hãy quyết định rõ:

- Subscriber mới có cần nhận event cũ không?
- Event bị bỏ lỡ có thể được tải lại bằng Query hoặc cursor không?
- Có cần replay một số event gần nhất không?
- Điều gì xảy ra khi chưa có subscriber hoặc khi subscriber xử lý chậm?
- Nhiều instance server có cần nhìn thấy cùng một event không?

Flux không tự bảo đảm lưu lịch sử. Muốn hỗ trợ resume sau khi mất kết nối, schema thường cần cursor hoặc event ID và service cần nguồn dữ liệu có thể đọc lại từ vị trí đó.

## Mỗi subscription có một vòng đời riêng

Khi client gửi operation subscription, Spring for GraphQL gọi resolver và lấy publisher. Khi publisher được subscribe, luồng event bắt đầu. Luồng có thể kết thúc theo ba cách:

1. **Complete:** nguồn dữ liệu hoàn tất bình thường.
2. **Error:** nguồn dữ liệu phát sinh lỗi và stream kết thúc.
3. **Cancel:** client unsubscribe, kết nối bị đóng hoặc subscription bị hủy.

Không nên tạo một vòng lặp vô hạn trong controller rồi tự quản lý socket. Hãy trả về Flux và để GraphQL transport quản lý việc subscribe, gửi payload và hủy publisher khi operation kết thúc.

Có thể quan sát vòng đời bằng doFinally:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger log =
        LoggerFactory.getLogger(StockSubscriptionController.class);

@SubscriptionMapping
public Flux<StockEvent> stockChanged(@Argument String productId) {
    return eventService.eventsFor(productId)
            .doFinally(signalType ->
                    log.info("Subscription kết thúc: {}", signalType));
}
~~~

doFinally phù hợp cho metric hoặc log lifecycle. Nếu cần giải phóng tài nguyên bất đồng bộ như đăng ký consumer, cursor hoặc connection, hãy dùng cơ chế quản lý resource phù hợp như Flux.usingWhen để cleanup khi complete, error hoặc cancel.

Cancellation cần được truyền ngược tới nguồn event. Nếu client đã unsubscribe nhưng consumer hoặc database cursor vẫn tiếp tục chạy, server có thể lãng phí tài nguyên và giữ những đăng ký không còn người nhận.

## WebSocket transport cho Subscription

GraphQL over HTTP thường xử lý Query và Mutation. Subscription cần một transport có thể giữ kết nối và gửi nhiều payload, phổ biến nhất là WebSocket. Spring for GraphQL hỗ trợ WebSocket transport; Spring Boot có thể cấu hình endpoint bằng thuộc tính spring.graphql.websocket.path.

Dependency thường dùng trong ứng dụng Spring Boot:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-websocket")
}
~~~

Cấu hình endpoint:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

Sau khi bật WebSocket transport, client kết nối tới endpoint WebSocket và gửi GraphQL subscription operation theo WebSocket subprotocol mà Spring GraphQL hỗ trợ. Cần cấu hình reverse proxy, load balancer và timeout để giữ kết nối lâu dài phù hợp.

HTTP endpoint và WebSocket endpoint có thể dùng chung đường dẫn tùy cấu hình ứng dụng, nhưng client phải dùng đúng scheme và giao thức: HTTP(S) cho query/mutation, WS(S) cho WebSocket subscription.

## Flux phát ra giá trị, GraphQL tạo từng payload

Một điểm quan trọng: Flux phát ra object domain hoặc DTO; nó không phát sẵn GraphQL JSON response. Với mỗi phần tử, GraphQL runtime phân giải root subscription field và selection set của client.

Ví dụ Flux:

~~~java
import java.time.Instant;

Flux<StockEvent> events = Flux.just(
        new StockEvent("evt-1", "product-42", 20, Instant.now().toString()),
        new StockEvent("evt-2", "product-42", 18, Instant.now().toString()),
        new StockEvent("evt-3", "product-42", 15, Instant.now().toString()));
~~~

Nếu client chọn:

~~~graphql
subscription {
  stockChanged(productId: "product-42") {
    eventId
    availableQuantity
  }
}
~~~

Mỗi StockEvent được phân giải thành một response payload. Client không cần gửi lại operation cho từng event; subscription đang mở nhận các payload liên tiếp.

Nếu StockEvent có nested field được resolve bằng @SchemaMapping, resolver field con vẫn được thực thi cho từng event. Nếu những field con truy cập database, cần chú ý chi phí truy vấn và có thể dùng projection, fetch strategy hoặc DataLoader phù hợp.

## Xử lý lỗi trước và sau khi stream bắt đầu

Có hai giai đoạn lỗi cần phân biệt:

**Lỗi khi thiết lập subscription**

Ví dụ productId không hợp lệ, người dùng không có quyền đăng ký hoặc sản phẩm không tồn tại. Resolver có thể kiểm tra trước khi trả Flux và phát exception. GraphQL xử lý đây là lỗi khi thực thi subscription operation; stream chưa bắt đầu phát event.

**Lỗi sau khi stream đã bắt đầu**

Ví dụ message broker mất kết nối hoặc nguồn event phát lỗi. Publisher phát onError và stream kết thúc. Client nhận lỗi cho subscription và cần quyết định có kết nối lại hoặc hiển thị trạng thái mất dữ liệu hay không.

Có thể chuyển lỗi nguồn dữ liệu sang exception có ngữ nghĩa:

~~~java
public Flux<StockEvent> eventsFor(String productId) {
    return eventSource.eventsFor(productId)
            .onErrorMap(
                    BrokerUnavailableException.class,
                    error -> new SubscriptionUnavailableException(
                            "Nguồn sự kiện hiện không khả dụng", error));
}
~~~

Không nên dùng onErrorResume(error -> Flux.empty()) một cách máy móc. Cách này biến lỗi hệ thống thành complete bình thường, khiến client tưởng rằng không còn event mới. Nếu cần fallback, hãy xác định rõ semantics và thông báo trạng thái cho client.

Retry chỉ phù hợp với lỗi tạm thời và nguồn có thể đăng ký lại an toàn. Retry không giới hạn có thể tạo kết nối lặp, tăng tải hoặc phát lại event trùng. Khi retry, hãy cân nhắc event ID, cursor, idempotency và chính sách backoff.

## Backpressure và tốc độ phát event

Reactor Flux hỗ trợ backpressure giữa các thành phần reactive: subscriber có thể điều tiết số phần tử yêu cầu từ upstream. Tuy nhiên, nguồn event bên ngoài như broker hoặc callback API có thể có cơ chế buffer riêng và không nhất thiết tuân theo demand của Reactor.

Nếu producer phát nhanh hơn khả năng xử lý hoặc gửi payload, queue có thể tăng và tiêu thụ nhiều bộ nhớ. Hãy chọn chính sách phù hợp:

| Chiến lược | Hành vi | Phù hợp với |
| --- | --- | --- |
| Buffer có giới hạn | Giữ event trong giới hạn; xử lý overflow theo chính sách | Event cần được xử lý nhưng có giới hạn tài nguyên |
| Drop | Bỏ event khi downstream không theo kịp | Metric hoặc cập nhật trung gian có thể bỏ |
| Latest | Giữ giá trị mới nhất, bỏ các giá trị cũ chưa xử lý | Dashboard chỉ cần trạng thái hiện tại |
| Sample/throttle | Giảm tần suất phát | Biểu đồ hoặc telemetry tần suất cao |
| Fail | Kết thúc khi vượt ngưỡng | Cần báo rõ stream không thể đáp ứng tải |

Ví dụ giới hạn buffer:

~~~java
public Flux<StockEvent> eventsFor(String productId) {
    return eventSource.eventsFor(productId)
            .onBackpressureBuffer(500);
}
~~~

Ví dụ trên đặt giới hạn 500 phần tử cho buffer do operator quản lý; khi vượt giới hạn, stream có thể phát lỗi overflow. Đây không phải giải pháp phổ quát. Với dữ liệu nghiệp vụ không được mất, nên dùng broker có retention, consumer offset và khả năng replay thay vì chỉ dựa vào buffer trong bộ nhớ.

Không tạo queue vô hạn cho mỗi client. Một subscription chậm không được phép làm tăng bộ nhớ không giới hạn hoặc ảnh hưởng tới các subscriber khác.

## Lọc event theo argument và người dùng

Argument của subscription thường xác định phạm vi event:

~~~java
@SubscriptionMapping
public Flux<StockEvent> stockChanged(@Argument String productId) {
    return eventService.eventsFor(productId);
}
~~~

Service cần lọc theo productId ở nguồn dữ liệu nếu có thể. Nếu chỉ dùng filter ở application sau khi nhận tất cả event, server có thể tiêu thụ băng thông và CPU không cần thiết.

Subscription cũng cần kiểm tra quyền ở thời điểm đăng ký:

~~~java
import java.security.Principal;

@SubscriptionMapping
public Flux<StockEvent> stockChanged(
        @Argument String productId,
        Principal principal) {

    authorizationService.checkCanViewStock(principal, productId);
    return eventService.eventsFor(productId);
}
~~~

Đối với reactive authorization, không block để chờ quyền:

~~~java
import java.security.Principal;
import org.springframework.security.access.AccessDeniedException;

@SubscriptionMapping
public Flux<StockEvent> stockChanged(
        @Argument String productId,
        Principal principal) {

    return authorizationService.canViewStock(principal, productId)
            .flatMapMany(allowed -> allowed
                    ? eventService.eventsFor(productId)
                    : Flux.error(new AccessDeniedException(
                            "Không có quyền theo dõi tồn kho")));
}
~~~

Nếu quyền có thể bị thu hồi trong khi subscription vẫn mở, kiểm tra lúc đăng ký là chưa đủ. Có thể cần kiểm tra quyền theo từng event, kết thúc stream khi quyền bị thu hồi hoặc gắn subscription với một lease có thời hạn. Việc kiểm tra phải cân bằng giữa yêu cầu bảo mật và chi phí xử lý event.

Không lấy tenant hoặc user ID từ argument do client tự khai báo làm bằng chứng xác thực. Hãy dùng Principal/Spring Security và giới hạn truy vấn theo tenant đã được xác thực.

## Tránh blocking trong Flux

Nếu ứng dụng dùng WebFlux và Reactor, tránh gọi block(), Thread.sleep() hoặc JDBC blocking trực tiếp trong pipeline chạy trên event loop. Những thao tác này làm giảm khả năng phục vụ các kết nối subscription đồng thời.

Nếu phải gọi API hoặc thư viện blocking, hãy cô lập rõ bằng scheduler phù hợp:

~~~java
import reactor.core.scheduler.Schedulers;

return Flux.fromIterable(ids)
        .publishOn(Schedulers.boundedElastic())
        .map(blockingClient::loadEvent);
~~~

Ví dụ chỉ minh họa việc chuyển tác vụ blocking sang scheduler chuyên dụng; trong thực tế nên ưu tiên client non-blocking và batch request nếu nguồn dữ liệu hỗ trợ. Không tạo scheduler mới cho từng event hoặc từng subscription mà không có giới hạn.

## Giới hạn tài nguyên và vận hành subscription

Subscription có thể sống lâu hơn HTTP request thông thường. Hãy đặt giới hạn và theo dõi:

- Số subscription đồng thời trên mỗi user, tenant và instance.
- Tốc độ event và số byte payload mỗi giây.
- Thời gian sống tối đa hoặc idle timeout nếu nghiệp vụ yêu cầu.
- Kích thước buffer và hành vi khi overflow.
- Số lần reconnect và retry.
- Thời gian từ khi client unsubscribe tới khi upstream được cleanup.
- Metric số stream đang mở, completed, failed và cancelled.

Chỉ gửi field mà client cần. Payload lớn hoặc quá nhiều nested fields sẽ làm tăng chi phí serialization và băng thông cho mọi event.

Với nhiều instance server, cần xác định event được phân phối tới tất cả subscriber hay chỉ một instance. Một local Flux hoặc Sinks chỉ tồn tại trong process hiện tại; để scale ngang, thường cần broker hoặc event infrastructure dùng chung.

## Kiểm thử Flux subscription

Có thể kiểm thử publisher ở tầng service bằng StepVerifier:

~~~java
StepVerifier.create(eventService.eventsFor("product-42").take(2))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .verifyComplete();
~~~

Để kiểm thử GraphQL operation và transport, dùng WebSocketGraphQlTester. Ví dụ sau giả định biến graphQlTester đã được cấu hình với kiểu WebSocketGraphQlTester và kết nối tới WebSocket endpoint:

~~~java
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<StockEvent> events = graphQlTester.document("""
        subscription WatchStock($productId: ID!) {
            stockChanged(productId: $productId) {
                eventId
                productId
                availableQuantity
            }
        }
        """)
        .variable("productId", "product-42")
        .executeSubscription()
        .toFlux("stockChanged", StockEvent.class);

StepVerifier.create(events.take(2))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .verifyComplete();
~~~

Với subscription thật, có thể dùng thenCancel() để mô phỏng client hủy sau một số event:

~~~java
StepVerifier.create(events)
        .expectNextCount(2)
        .thenCancel()
        .verify();
~~~

Kiểm thử cần xác minh cả kết quả và lifecycle:

- Operation trả về nhiều payload theo đúng thứ tự event.
- Argument lọc đúng sản phẩm hoặc tenant.
- Lỗi lúc thiết lập subscription được trả về đúng dạng.
- Lỗi từ publisher sau khi bắt đầu kết thúc stream theo chính sách.
- Client cancel làm upstream được hủy và tài nguyên được giải phóng.
- Buffer overflow hoặc producer quá nhanh được xử lý có kiểm soát.
- Người dùng không được phép không thể đăng ký hoặc nhận event.
- Event payload và nested fields không làm phát sinh truy vấn N+1 ngoài dự kiến.

Khi test GraphQL subscription, bảo đảm transport test thực sự dùng WebSocketGraphQlTester hoặc test server phù hợp. GraphQlTester dạng HTTP thông thường không mô phỏng được vòng đời một WebSocket subscription.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Subscription chỉ trả một kết quả | Resolver trả object hoặc collection thay vì Publisher | Trả Flux<T> |
| Subscription không kết nối được | WebSocket endpoint hoặc dependency chưa được bật | Kiểm tra starter, path và proxy |
| Client nhận event cũ hoặc bỏ lỡ event | Dùng hot publisher không replay | Dùng cursor/replay hoặc nguồn event có retention |
| Stream kết thúc đột ngột | Publisher phát onError | Ghi log, phân loại lỗi và xác định retry policy |
| Stream im lặng dù event đã phát | Sai filter, routing key hoặc subscriber chưa đăng ký | Kiểm tra productId và lifecycle |
| Bộ nhớ tăng theo thời gian | Buffer không giới hạn hoặc subscriber chậm | Giới hạn buffer và chọn overflow policy |
| Unsubscribe nhưng consumer vẫn chạy | Cancellation không được truyền tới nguồn | Dùng publisher hỗ trợ cancellation và cleanup |
| Người dùng nhận event ngoài phạm vi | Chỉ kiểm tra argument mà không kiểm tra principal/tenant | Áp dụng authorization ở nguồn và theo event khi cần |
| Server quá tải khi nhiều client kết nối | Mỗi subscription tạo tài nguyên không giới hạn | Giới hạn concurrent streams và đo metric |
| Event bị lặp sau reconnect | Retry hoặc replay không dùng cursor/idempotency | Dùng event ID và quy tắc deduplicate |

## Nguyên tắc thiết kế Flux cho subscription

Khi xây dựng GraphQL Subscription trong Spring for GraphQL, hãy áp dụng:

1. **Dùng @SubscriptionMapping cho root field.** Method trả Publisher, thường là Flux<T>.
2. **Một subscription operation có một root field.** Chọn các field con cần thiết trong payload.
3. **Tách controller và event source.** Controller bind argument; service quản lý publisher và lọc event.
4. **Hiểu cold và hot publisher.** Quyết định rõ replay, event bị bỏ lỡ và nhiều subscriber.
5. **Quản lý vòng đời.** Complete, error và cancel đều phải kết thúc tài nguyên đúng cách.
6. **Chọn backpressure policy.** Giới hạn buffer và xác định event nào được phép drop hoặc cần replay.
7. **Phân biệt lỗi setup và lỗi stream.** Không che lỗi nguồn bằng Flux.empty() nếu client cần biết stream đã hỏng.
8. **Bảo vệ từng subscription.** Kiểm tra principal, tenant và quyền nhận event.
9. **Không block reactive pipeline.** Dùng client non-blocking hoặc cô lập tác vụ blocking có giới hạn.
10. **Kiểm thử transport và cancellation.** Dùng WebSocketGraphQlTester và StepVerifier để kiểm tra nhiều payload cùng lifecycle.

Flux là kiểu trả về phù hợp cho subscription vì nó biểu diễn luồng event bất đồng bộ có thể phát nhiều phần tử theo thời gian. Spring for GraphQL ánh xạ Flux từ @SubscriptionMapping thành các GraphQL response payload liên tiếp qua transport subscription. Khi chọn đúng nguồn event, quản lý cold/hot publisher, cancellation, backpressure, lỗi và authorization, ứng dụng có thể cung cấp cập nhật thời gian thực mà vẫn kiểm soát được tài nguyên và tính nhất quán dữ liệu.

## Tài liệu tham khảo

- [Spring for GraphQL - Subscription Support và Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - WebSocket Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Project Reactor - Flux và Backpressure](https://projectreactor.io/docs/core/release/reference/)
