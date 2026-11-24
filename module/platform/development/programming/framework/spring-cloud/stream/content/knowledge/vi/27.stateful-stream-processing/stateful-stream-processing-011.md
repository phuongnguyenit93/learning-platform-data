# Định tuyến truy vấn đến instance giữ state store phù hợp

Kafka Streams chia dữ liệu của một ứng dụng stateful thành nhiều partition. Khi ứng dụng chạy trên nhiều instance, mỗi instance chỉ giữ một phần state store tương ứng với các partition mà nó đang sở hữu. Một truy vấn theo key vì vậy phải đến đúng instance đang giữ partition của key đó. Gọi state store cục bộ trên một instance bất kỳ có thể trả về null hoặc không tìm thấy dữ liệu dù key vẫn tồn tại ở instance khác.

Kafka Streams cung cấp Interactive Queries để đọc state store cục bộ và tra cứu metadata về instance đang giữ một key. Spring Cloud Stream Kafka Streams Binder bọc các API này trong InteractiveQueryService. Ứng dụng dùng metadata để quyết định đọc ngay trong JVM hay chuyển truy vấn qua mạng đến instance sở hữu dữ liệu.

## 1. Vì sao cần định tuyến truy vấn?

Giả sử topology tạo state store order-summary-store từ topic orders.events. Topic có sáu partition và ứng dụng chạy ba instance. Kafka Streams phân phối task và partition cho các instance:

~~~text
Kafka topic: orders.events
Partitions:  0   1   2   3   4   5
             |   |   |   |   |   |
             +---+---+   +---+---+
                 |           |
          Instance A    Instance B    Instance C
          P0, P1        P2, P3         P4, P5
          local store   local store    local store
~~~

Mỗi instance có một phần dữ liệu của state store. Nếu request tra cứu orderId=ORD-2005 được gửi đến Instance A nhưng key đó thuộc partition đang do Instance C quản lý, store cục bộ của A không có kết quả. Ứng dụng cần tìm instance sở hữu key rồi định tuyến truy vấn đến đó.

Có hai phần riêng biệt:

- **Discovery:** tìm instance nào đang giữ key trong một state store.
- **RPC:** gọi instance đó qua HTTP, gRPC hoặc một giao thức nội bộ khác để đọc state store cục bộ.

Kafka Streams hỗ trợ discovery metadata, nhưng không tự tạo REST endpoint hoặc chuyển tiếp request giữa các instance. Ứng dụng phải triển khai lớp giao tiếp mạng phù hợp.

## 2. Interactive Queries chỉ đọc phần state cục bộ

Interactive Queries cho phép ứng dụng truy vấn state store mà topology đã materialize. Với key-value store, API đọc thường dùng ReadOnlyKeyValueStore; với window store hoặc session store, dùng kiểu store tương ứng.

State store phải có tên ổn định để có thể truy vấn. Ví dụ, khi aggregate stream theo key, khai báo tên store bằng Materialized.as(...):

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String status, long amountDeltaMinorUnits) {}

record OrderSummary(long totalMinorUnits, String latestStatus) {
    static OrderSummary empty() {
        return new OrderSummary(0L, "NEW");
    }

    OrderSummary apply(OrderEvent event) {
        return new OrderSummary(
                totalMinorUnits + event.amountDeltaMinorUnits(),
                event.status());
    }
}

@Configuration
class OrderSummaryTopology {

    @Bean
    Function<KStream<String, OrderEvent>, KTable<String, OrderSummary>>
    orderSummary(OrderEventSerde orderEventSerde,
                 OrderSummarySerde orderSummarySerde) {

        return orders -> orders
                .groupByKey(Grouped.with(
                        Serdes.String(),
                        orderEventSerde))
                .aggregate(
                        OrderSummary::empty,
                        (orderId, event, current) -> current.apply(event),
                        Materialized.<String, OrderSummary,
                                KeyValueStore<Bytes, byte[]>>as(
                                        "order-summary-store")
                                .withKeySerde(Serdes.String())
                                .withValueSerde(orderSummarySerde));
    }
}
~~~

OrderEventSerde và OrderSummarySerde là các Serde do ứng dụng cung cấp. Ví dụ tập trung vào tên store và kiểu key/value; cần cấu hình Serde đúng với schema thực tế của topic.

Kích hoạt function và ánh xạ các binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSummary
    stream:
      bindings:
        orderSummary-in-0:
          destination: orders.events
        orderSummary-out-0:
          destination: orders.summary
~~~

Binder tạo input binding orderSummary-in-0 cho topic đầu vào. Materialized.as("order-summary-store") đặt tên state store có thể truy vấn. Khi ứng dụng khởi động, Kafka Streams xây dựng store và cập nhật nó từ các record của topology.

Đọc một key trên instance hiện tại:

~~~java
import org.apache.kafka.streams.state.QueryableStoreTypes;
import org.apache.kafka.streams.state.ReadOnlyKeyValueStore;

ReadOnlyKeyValueStore<String, OrderSummary> store =
        interactiveQueryService.getQueryableStoreType(
                "order-summary-store",
                QueryableStoreTypes.keyValueStore());

OrderSummary summary = store.get("ORD-2005");
~~~

Đây là truy vấn cục bộ. API không tự tìm dữ liệu ở instance khác. State store được truy vấn ở chế độ read-only; thay đổi dữ liệu phải đi qua topology và các input topic, không ghi trực tiếp vào store từ REST controller.

## 3. InteractiveQueryService của Kafka Streams Binder

Spring Cloud Stream Kafka Streams Binder cung cấp InteractiveQueryService dưới dạng Spring bean. Ứng dụng có thể inject service này để:

- Lấy store cục bộ bằng getQueryableStoreType(...).
- Tìm host đang giữ key bằng getHostInfo(store, key, serializer).
- Lấy host của instance hiện tại bằng getCurrentHostInfo().
- Lấy KeyQueryMetadata bằng getKeyQueryMetadata(store, key, serializer).
- Lấy đối tượng KafkaStreams tương ứng bằng getKafkaStreams(store, key, serializer).

Ví dụ inject qua constructor:

~~~java
import org.springframework.cloud.stream.binder.kafka.streams.InteractiveQueryService;
import org.springframework.stereotype.Service;

@Service
class OrderQueryMetadata {

    private final InteractiveQueryService interactiveQueryService;

    OrderQueryMetadata(InteractiveQueryService interactiveQueryService) {
        this.interactiveQueryService = interactiveQueryService;
    }
}
~~~

Không nhầm InteractiveQueryService của Kafka Streams Binder với KafkaStreamsInteractiveQueryService của Spring for Apache Kafka. Hai lớp thuộc hai integration khác nhau; trong ứng dụng đang dùng Spring Cloud Stream Kafka Streams Binder, dùng API mà binder cung cấp.

## 4. Khai báo application.server trên từng instance

Kafka Streams cần biết địa chỉ mạng mà mỗi instance dùng để nhận truy vấn từ instance khác. Cấu hình application.server công bố một cặp host/port cho endpoint RPC của instance:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: order-summary-v1
            brokers: localhost:9092
            configuration:
              application.server: ${QUERY_HOST:localhost}:${QUERY_PORT:8080}
~~~

Trong môi trường chạy nhiều instance:

- applicationId phải giống nhau giữa các replica của cùng một Kafka Streams application để chúng thuộc cùng một ứng dụng logic.
- application.server phải khác nhau theo từng instance đang chạy, trỏ đến địa chỉ có thể truy cập trực tiếp từ các instance còn lại.
- HTTP server hoặc RPC server của ứng dụng phải thực sự lắng nghe tại địa chỉ/port được công bố.
- Hostname phải phân giải được trong mạng nội bộ; port phải được mở qua network policy, security group hoặc cấu hình hạ tầng tương ứng.

Ví dụ, ba pod có thể công bố lần lượt order-stream-0.internal:8080, order-stream-1.internal:8080 và order-stream-2.internal:8080. Cùng port là bình thường nếu mỗi pod có hostname/IP riêng.

Giá trị localhost trong placeholder chỉ dành cho chạy một instance ở máy phát triển. Production phải cấp QUERY_HOST và QUERY_PORT riêng cho từng replica; nếu mọi instance cùng công bố localhost, metadata sẽ trỏ đến sai tiến trình.

application.server không phải bootstrap.servers và cũng không tự khởi động web server. bootstrap.servers là địa chỉ Kafka broker; application.server là địa chỉ RPC mà instance dùng để phục vụ truy vấn state. Không đặt một load balancer chung cho tất cả instance nếu load balancer có thể chuyển request đến pod bất kỳ: metadata cần xác định chính xác instance sở hữu partition.

## 5. Luồng định tuyến truy vấn theo key

Một endpoint nhận truy vấn có thể thực hiện các bước:

1. Nhận key và tên state store cần đọc.
2. Dùng getHostInfo(...) để tìm host sở hữu key.
3. Lấy getCurrentHostInfo() để biết instance hiện tại.
4. Nếu hai host giống nhau, đọc trực tiếp local state store.
5. Nếu host khác, gọi endpoint nội bộ trên host đó.
6. Nếu metadata chưa sẵn sàng hoặc host không còn truy cập được, trả lỗi có thể thử lại hoặc làm mới metadata theo giới hạn.

~~~mermaid
flowchart TD
    A[Request: orderId] --> B[InteractiveQueryService.getHostInfo]
    B --> C{Có owner metadata?}
    C -->|Không| D[Retry có giới hạn hoặc trả 503]
    C -->|Có| E{Owner là instance hiện tại?}
    E -->|Có| F[Đọc local state store]
    E -->|Không| G[Gọi RPC đến owner]
    G --> H{Owner còn giữ partition?}
    H -->|Có| I[Trả kết quả]
    H -->|Không| J[Làm mới metadata và thử lại một lần]
    F --> I
~~~

Không nên phát tán một truy vấn đến tất cả instance rồi lấy kết quả đầu tiên. Cách đó tăng tải mạng, làm nhiều instance phải đọc store không sở hữu key và che giấu lỗi định tuyến. Dùng metadata theo key để chọn đúng owner trước khi query.

## 6. Tìm host đang giữ một key

Với key kiểu String, có thể dùng serializer tương ứng:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.state.HostInfo;

HostInfo owner = interactiveQueryService.getHostInfo(
        "order-summary-store",
        "ORD-2005",
        Serdes.String().serializer());

HostInfo current = interactiveQueryService.getCurrentHostInfo();
~~~

owner là host đang quản lý key theo metadata của Kafka Streams; current là host của instance đang xử lý request. Nếu hai giá trị bằng nhau, có thể đọc local store. Nếu khác nhau, cần gửi truy vấn đến địa chỉ owner.host() và owner.port().

Serializer phải khớp với kiểu key và cách key được serialize trong topology. Ví dụ key là Long thì dùng Serdes.Long().serializer(). Không dùng serializer String cho key Long hoặc thay đổi cách chuẩn hóa key giữa producer và query service.

Metadata được tính dựa trên partitioning strategy của Kafka Streams. Nếu topology dùng partitioner tùy chỉnh, cần bảo đảm phép xác định partition cho truy vấn khớp với partitioner thực tế. Kafka Streams có API metadataForKey nhận StreamPartitioner trong trường hợp cần chỉ định thuật toán phân vùng; không giả định serializer mặc định luôn mô tả được một partitioner tùy chỉnh.

## 7. Phân biệt active host, standby host và partition

API getKeyQueryMetadata(...) trả về KeyQueryMetadata, chứa:

- activeHost: instance hiện giữ partition và có quyền xử lý dữ liệu của key.
- standbyHosts: các instance có standby replica của state store nếu ứng dụng đã cấu hình standby task.
- partition: partition tương ứng với key trong state store.

Đây là ảnh chụp metadata tại thời điểm truy vấn. Khi rebalance hoặc instance dừng, active host có thể thay đổi. Đường đọc thông thường nên định tuyến đến activeHost.

Ở API Kafka Streams cấp thấp, KeyQueryMetadata.NOT_AVAILABLE là dấu hiệu metadata hiện chưa thể xác định, thường trong lúc rebalance. Khi gặp trạng thái này, không đọc activeHost; hãy retry có giới hạn hoặc trả trạng thái tạm thời cho caller.

Standby host có thể hữu ích cho mục tiêu giảm thời gian phục vụ khi active host gặp sự cố, nhưng dữ liệu standby có thể chưa cập nhật đến record mới nhất. Chỉ đọc từ standby nếu nghiệp vụ chấp nhận stale read và ứng dụng đã cấu hình chính sách truy vấn cho stale store. Không tự động chọn standby thay active host rồi coi kết quả là mới nhất.

## 8. Cấu hình endpoint nội bộ cho truy vấn từ xa

Kafka Streams chỉ cung cấp metadata về host. Ứng dụng cần tạo endpoint mạng để instance khác gọi vào. Một thiết kế đơn giản có hai loại endpoint:

- Endpoint công khai nhận truy vấn từ API client và thực hiện discovery/routing.
- Endpoint nội bộ chỉ đọc local state store trên instance được gọi.

Ví dụ interface cho phần giao tiếp mạng:

~~~java
import org.apache.kafka.streams.state.HostInfo;

interface RemoteOrderStateClient {
    OrderSummary fetch(HostInfo owner, String orderId);
}
~~~

Triển khai interface bằng HTTP client, gRPC client hoặc RPC nội bộ của hệ thống. Địa chỉ đích lấy từ HostInfo; không tự dựng host từ tên pod hoặc chọn một replica ngẫu nhiên.

Ví dụ triển khai HTTP client bằng RestClient của Spring Framework 6.1 trở lên:

~~~java
import org.apache.kafka.streams.state.HostInfo;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class HttpRemoteOrderStateClient implements RemoteOrderStateClient {

    private final RestClient restClient;

    HttpRemoteOrderStateClient(RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    @Override
    public OrderSummary fetch(HostInfo owner, String orderId) {
        return restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .scheme("http")
                        .host(owner.host())
                        .port(owner.port())
                        .path("/internal/state/orders/{orderId}")
                        .build(orderId))
                .retrieve()
                .body(OrderSummary.class);
    }
}
~~~

Nếu phiên bản Spring Framework chưa có RestClient, có thể dùng RestTemplate hoặc WebClient với cùng nguyên tắc: host và port lấy từ HostInfo, request có timeout và xác thực service-to-service.

Ví dụ controller chỉ phục vụ local store:

~~~java
import java.util.Optional;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

interface OrderStateStoreReader {
    Optional<OrderSummary> readLocalOnly(String orderId);
}

@RestController
@RequestMapping("/internal/state/orders")
class LocalOrderStateController {

    private final OrderStateStoreReader storeReader;

    LocalOrderStateController(OrderStateStoreReader storeReader) {
        this.storeReader = storeReader;
    }

    @GetMapping("/{orderId}")
    OrderSummary getLocal(@PathVariable String orderId) {
        return storeReader.readLocalOnly(orderId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));
    }
}
~~~

readLocalOnly chỉ truy vấn store cục bộ. Endpoint nội bộ không gọi lại router, nếu không có thể tạo vòng lặp giữa các instance. Trong triển khai thực tế, nên kiểm tra instance vẫn là owner trước khi trả dữ liệu; nếu partition đã chuyển đi, trả mã trạng thái cho biết metadata đã cũ để caller tra cứu lại.

Một triển khai local reader cần xác minh ownership ngay trước khi đọc:

~~~java
import java.util.Optional;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.errors.InvalidStateStoreException;
import org.apache.kafka.streams.state.HostInfo;
import org.apache.kafka.streams.state.QueryableStoreTypes;
import org.apache.kafka.streams.state.ReadOnlyKeyValueStore;
import org.springframework.cloud.stream.binder.kafka.streams.InteractiveQueryService;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class BinderOrderStateStoreReader implements OrderStateStoreReader {

    private static final String STORE_NAME = "order-summary-store";
    private final InteractiveQueryService interactiveQueryService;

    BinderOrderStateStoreReader(InteractiveQueryService interactiveQueryService) {
        this.interactiveQueryService = interactiveQueryService;
    }

    @Override
    public Optional<OrderSummary> readLocalOnly(String orderId) {
        HostInfo owner = interactiveQueryService.getHostInfo(
                STORE_NAME, orderId, Serdes.String().serializer());
        HostInfo current = interactiveQueryService.getCurrentHostInfo();

        if (owner == null || current == null || !current.equals(owner)) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "This instance no longer owns the key");
        }

        ReadOnlyKeyValueStore<String, OrderSummary> store =
                interactiveQueryService.getQueryableStoreType(
                        STORE_NAME, QueryableStoreTypes.keyValueStore());
        try {
            return Optional.ofNullable(store.get(orderId));
        }
        catch (InvalidStateStoreException ex) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "The local store is changing ownership", ex);
        }
    }
}
~~~

## 9. Ví dụ router: local hoặc remote

Phần dưới đây thể hiện quyết định định tuyến. OrderStateStoreReader đọc local store; RemoteOrderStateClient gọi endpoint nội bộ trên host được Kafka Streams công bố.

~~~java
import java.util.Optional;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.state.HostInfo;
import org.springframework.cloud.stream.binder.kafka.streams.InteractiveQueryService;
import org.springframework.stereotype.Service;

@Service
class OrderStateQueryRouter {

    private static final String STORE_NAME = "order-summary-store";

    private final InteractiveQueryService interactiveQueryService;
    private final OrderStateStoreReader localReader;
    private final RemoteOrderStateClient remoteClient;

    OrderStateQueryRouter(
            InteractiveQueryService interactiveQueryService,
            OrderStateStoreReader localReader,
            RemoteOrderStateClient remoteClient) {
        this.interactiveQueryService = interactiveQueryService;
        this.localReader = localReader;
        this.remoteClient = remoteClient;
    }

    Optional<OrderSummary> find(String orderId) {
        HostInfo owner = interactiveQueryService.getHostInfo(
                STORE_NAME,
                orderId,
                Serdes.String().serializer());

        HostInfo current = interactiveQueryService.getCurrentHostInfo();

        if (owner == null || current == null) {
            throw new IllegalStateException(
                    "Kafka Streams host metadata is not available");
        }

        if (current.equals(owner)) {
            return localReader.readLocalOnly(orderId);
        }

        return Optional.ofNullable(remoteClient.fetch(owner, orderId));
    }
}
~~~

Trong ứng dụng thực tế, tách logic đọc cục bộ thành service riêng để endpoint nội bộ có thể gọi trực tiếp mà không kích hoạt định tuyến từ xa. Ví dụ rút gọn ở trên thể hiện điểm quyết định: chỉ khi current trùng owner mới đọc local store.

getHostInfo hoặc truy vấn store có thể thất bại khi Kafka Streams chưa khởi tạo xong, state store đang restore, hoặc metadata đang thay đổi. Không coi mọi exception là “không tìm thấy key”; cần phân biệt key không tồn tại với store chưa sẵn sàng hoặc metadata chưa có.

## 10. Xử lý startup và state store chưa sẵn sàng

Trong thời gian khởi động, Kafka Streams cần tạo topology, tham gia group, nhận partition và restore state store. Một request đến quá sớm có thể gặp tình huống store chưa queryable.

Kafka Streams Binder có retry cho thao tác lấy store và tìm host. Có thể cấu hình số lần thử và khoảng nghỉ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            stateStoreRetry:
              maxAttempts: 5
              backOffInterval: 1000
~~~

Giá trị mặc định của binder được tài liệu hiện hành mô tả là một lần thử và khoảng nghỉ một giây. Tăng số lần thử giúp xử lý lỗi khởi động tạm thời, nhưng không thay thế readiness check hoặc timeout của HTTP request. Chọn tổng thời gian retry nhỏ hơn ngân sách thời gian của request và cân nhắc trả 503 Service Unavailable khi state chưa sẵn sàng.

Có thể kết hợp readiness indicator để instance chỉ nhận lưu lượng truy vấn sau khi Kafka Streams đã vào trạng thái phù hợp và state store cần thiết đã được khôi phục. Không dùng liveness check để restart liên tục chỉ vì một store đang restore bình thường.

## 11. Xử lý metadata cũ khi rebalance

Metadata định tuyến là dữ liệu tại một thời điểm. Trong lúc request đang được gửi, Kafka Streams có thể rebalance do:

- Instance mới tham gia hoặc instance hiện tại dừng.
- Consumer bị mất kết nối hoặc vượt giới hạn heartbeat/poll.
- Partition assignment thay đổi sau khi scale ứng dụng.
- Task được chuyển sang instance khác để phục hồi.

Vì vậy, host vừa được discovery có thể không còn sở hữu key khi request đến nơi. Endpoint nội bộ nên kiểm tra trạng thái ownership hoặc khả năng query local store và trả lỗi có thể nhận biết, chẳng hạn 409 Conflict hoặc 503 Service Unavailable.

Caller có thể làm mới metadata rồi thử lại một lần với giới hạn thời gian. Tránh retry vô hạn hoặc tự chuyển tiếp qua lại giữa hai host. Nếu lần định tuyến thứ hai vẫn thất bại, trả lỗi có thể retry cho caller và ghi log gồm store name, key, host cũ, host mới và partition nếu có.

## 12. HostInfo không phải địa chỉ của Kafka broker

HostInfo chứa host và port của endpoint truy vấn của một Kafka Streams instance. Nó không phải địa chỉ broker và không phải địa chỉ của topic partition trên Kafka.

| Giá trị | Mục đích |
|---|---|
| bootstrap.servers | Kết nối đến Kafka broker |
| application.id | Nhận diện nhóm Kafka Streams application |
| application.server | Công bố endpoint RPC của từng instance |
| HostInfo | Metadata host/port để định tuyến truy vấn state store |
| partition trong metadata | Partition chứa key của state store |

Không gửi truy vấn REST đến broker. Cũng không giả định Kafka broker sẽ chuyển HTTP request đến instance đang giữ partition. Discovery và RPC là hai phần do ứng dụng phối hợp.

## 13. Bảo mật endpoint truy vấn nội bộ

Endpoint nội bộ có thể trả dữ liệu nghiệp vụ từ state store. Vì vậy, không nên mở endpoint này trực tiếp ra Internet hoặc để bất kỳ service nào trong mạng đều có thể truy cập.

Các biện pháp cần xem xét:

- Chỉ cho phép traffic từ các instance cùng ứng dụng hoặc service gateway được tin cậy.
- Dùng TLS/mTLS hoặc cơ chế xác thực service-to-service.
- Kiểm tra quyền truy cập theo tenant, user và phạm vi dữ liệu trước khi định tuyến.
- Giới hạn request rate, timeout và kích thước response.
- Không cho client truyền tùy ý hostname/port để tránh SSRF; host đích phải đến từ metadata Kafka Streams đã xác thực.
- Ghi audit cho truy vấn nhạy cảm nhưng tránh log payload hoặc dữ liệu cá nhân không cần thiết.
- Không để endpoint nội bộ trở thành đường bypass authorization của API công khai.

Nếu dùng service mesh hoặc gateway, cần bảo đảm đường gọi nội bộ vẫn đến đúng instance. Một load balancer round-robin có thể phá vỡ định tuyến theo HostInfo nếu nó thay host đích bằng một địa chỉ chung.

## 14. Truy vấn từ một API gateway hoặc ứng dụng khác

Không nhất thiết request ban đầu phải đến một Kafka Streams instance. Một API gateway hoặc service truy vấn riêng có thể giữ logic discovery:

1. Nhận orderId từ client.
2. Gọi một endpoint điều phối trong Kafka Streams application để tìm owner.
3. Đọc trực tiếp local nếu endpoint điều phối nằm trên owner.
4. Nếu không, gọi RPC đến endpoint được HostInfo chỉ ra.
5. Trả kết quả về client.

Một lựa chọn khác là để mọi instance đều expose cùng API và tự định tuyến. Khi request đến nhầm instance, instance đó tra metadata rồi forward đến owner. Cách này đơn giản cho client, nhưng cần bảo đảm endpoint forward và endpoint local tách biệt để tránh vòng lặp.

Nếu dùng gateway, hãy giữ discovery trong service tin cậy thay vì đưa danh sách HostInfo nội bộ ra cho client bên ngoài. Địa chỉ instance có thể thay đổi khi scale hoặc triển khai lại.

## 15. Cân nhắc standby store và stale read

Kafka Streams có thể cấu hình standby replica để một instance phụ giữ bản sao state store. Standby giúp giảm thời gian phục hồi khi active instance gặp sự cố, nhưng dữ liệu của standby có thể chưa theo kịp active store.

Với truy vấn yêu cầu dữ liệu mới nhất:

- Ưu tiên active host từ metadata.
- Không tự động chuyển sang standby khi active host lỗi nếu chưa xác định semantics.
- Có thể trả 503 hoặc retry discovery sau khi rebalance hoàn tất.

Với truy vấn chấp nhận dữ liệu cũ trong một khoảng cho phép:

- Định nghĩa rõ mức stale tối đa mà nghiệp vụ chấp nhận.
- Cấu hình standby task và store query parameters phù hợp.
- Dùng StoreQueryParametersCustomizer nếu binder version hỗ trợ và ứng dụng cần bật stale stores.
- Trả kèm timestamp hoặc version của state để caller đánh giá độ mới.

Không dùng stale store cho các quyết định tài chính hoặc kiểm soát tồn kho nếu nghiệp vụ yêu cầu đọc trạng thái mới nhất.

## 16. Hiệu năng và khả năng mở rộng

Định tuyến đúng owner tránh fan-out đến mọi instance, nhưng vẫn cần giới hạn chi phí truy vấn:

- Đặt timeout riêng cho truy vấn local và remote.
- Dùng connection pooling cho HTTP client nội bộ.
- Cân nhắc batch query khi cần đọc nhiều key cùng lúc; nhóm key theo owner để giảm số lần gọi mạng.
- Cache metadata ngắn hạn nếu cần, nhưng phải có cách làm mới khi host thay đổi.
- Không cache kết quả state quá lâu nếu caller cần dữ liệu mới.
- Theo dõi tỷ lệ local query/remote query, thời gian discovery, thời gian RPC và lỗi stale metadata.
- Tránh biến state store thành cơ sở dữ liệu truy vấn tùy ý với scan không giới hạn.

Nếu endpoint phục vụ nhiều key, có thể nhóm key theo partition hoặc owner trước khi gọi remote. Việc này giảm số request nhưng cần giữ giới hạn kích thước batch và thời gian phản hồi.

## 17. Quan sát và xử lý sự cố

Các metric hữu ích:

Các tên dưới đây là metric ứng dụng có thể tự instrument; chúng không tự được Kafka Streams Binder tạo ra với đúng các tên này.

| Metric | Ý nghĩa |
|---|---|
| interactive_query.lookup | Số lần tra cứu owner metadata |
| interactive_query.local | Số truy vấn được phục vụ tại instance hiện tại |
| interactive_query.remote | Số truy vấn được forward sang instance khác |
| interactive_query.metadata_unavailable | Metadata chưa sẵn sàng hoặc không tìm thấy owner |
| interactive_query.stale_route | Endpoint đích không còn sở hữu key |
| interactive_query.rpc_latency | Độ trễ gọi remote |
| interactive_query.store_not_ready | State store chưa queryable |

Log nên ghi storeName, partition, HostInfo owner, current host, request ID và kết quả định tuyến. Không ghi giá trị state nhạy cảm.

Khi một truy vấn không có kết quả, cần phân biệt:

- Key không tồn tại trong store.
- Key thuộc partition đang ở instance khác.
- State store chưa restore xong.
- Metadata chưa có trong lúc rebalance.
- Endpoint RPC không thể truy cập.
- Request bị từ chối do authorization.

Chỉ trường hợp đầu tiên mới nên trả 404 Not Found. Các trường hợp còn lại thường cần lỗi vận hành như 503 Service Unavailable, 409 Conflict hoặc 403 Forbidden tùy nguyên nhân.

## 18. Kiểm thử định tuyến truy vấn

Kiểm thử cần bao phủ cả local và remote path:

1. Chạy một instance, query key do instance đó giữ và xác nhận local store trả đúng kết quả.
2. Chạy nhiều instance với application.server khác nhau; query key thuộc instance khác và xác nhận request được forward đến đúng host.
3. Dùng key serializer đúng với topology; kiểm tra owner metadata tương ứng partition mong đợi.
4. Tạm dừng một instance hoặc kích hoạt rebalance trong lúc query; xác nhận stale route được xử lý có giới hạn.
5. Query trong lúc state store đang restore; xác nhận retry/503 thay vì trả kết quả sai.
6. Kiểm tra endpoint nội bộ chỉ đọc local state và không tự forward.
7. Kiểm tra request không được phép truy cập bị chặn trước khi đọc state.
8. Kiểm tra remote timeout và lỗi mạng không làm request retry vô hạn.
9. Nếu dùng standby/stale store, xác nhận response thể hiện đúng mức độ mới của dữ liệu.

TopologyTestDriver hữu ích để kiểm thử phép biến đổi và kết quả state store trong một topology đơn lẻ. Nó không thay thế integration test cho discovery metadata, application.server, network routing, rebalance và RPC giữa nhiều instance. Dùng Kafka broker và nhiều tiến trình/containers trong integration test để xác nhận đường đi thực tế.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| getHostInfo không tìm thấy host | Thiếu application.server hoặc metadata chưa sẵn sàng | Cấu hình endpoint riêng cho từng instance và retry có giới hạn |
| Mọi instance công bố cùng một host | Dùng chung hostname hoặc load balancer cho application.server | Công bố địa chỉ có thể truy cập trực tiếp của từng instance |
| Local store trả null dù key tồn tại | Request đến instance không sở hữu partition | Dùng metadata theo key và forward đến owner |
| Remote endpoint không truy cập được | Port chưa mở, hostname không phân giải hoặc web server không lắng nghe | Kiểm tra network, DNS, listener và port |
| Query lỗi sau rebalance | Host metadata đã cũ | Làm mới metadata và thử lại một lần |
| Query luôn đọc dữ liệu cũ | Đang đọc standby/stale store hoặc state chưa bắt kịp | Định tuyến active host và kiểm tra freshness |
| Query trả 404 khi store chưa sẵn sàng | Gộp lỗi store readiness vào lỗi key không tồn tại | Phân loại exception và trả mã trạng thái phù hợp |
| Truy vấn vòng lặp giữa các instance | Endpoint nội bộ cũng gọi router | Tách endpoint local-only khỏi endpoint định tuyến |
| Host được tìm sai partition | Serializer hoặc partitioning strategy không khớp | Dùng đúng key serializer/partitioner của topology |

## 20. Checklist triển khai

- State store được materialize với tên ổn định và kiểu truy vấn phù hợp.
- Mỗi instance cùng ứng dụng dùng chung applicationId.
- Mỗi instance công bố application.server riêng, có thể truy cập từ các instance còn lại.
- RPC server thực sự lắng nghe tại địa chỉ và port được công bố.
- InteractiveQueryService dùng đúng store name, key và serializer.
- Truy vấn local chỉ thực hiện khi current host trùng owner host.
- Truy vấn remote dùng HTTP/gRPC nội bộ và endpoint local-only.
- Có timeout, xử lý metadata cũ và retry giới hạn khi rebalance.
- Phân biệt active host với standby host và xác định yêu cầu freshness.
- Bảo vệ endpoint nội bộ bằng xác thực, TLS/mTLS và network policy.
- Theo dõi local/remote query, metadata lookup, store readiness và RPC latency.
- Có integration test với nhiều instance và Kafka broker thật.

Định tuyến truy vấn đến đúng instance là phần cần thiết khi state store được phân tán qua nhiều Kafka Streams instance. InteractiveQueryService giúp tìm host đang giữ key và đọc state cục bộ; application.server công bố địa chỉ RPC riêng của từng instance. Ứng dụng phải tự triển khai lớp HTTP/gRPC để chuyển truy vấn từ instance hiện tại đến owner, đồng thời xử lý metadata thay đổi khi rebalance, bảo vệ endpoint nội bộ và phân biệt dữ liệu active với standby. Khi discovery, RPC và local query được phối hợp rõ ràng, API có thể truy vấn toàn bộ state phân tán mà không cần gửi request đến mọi instance.

## Tài liệu tham khảo

- [Spring Cloud Stream — Interactive Queries](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/interactive-queries.html)
- [Apache Kafka — Interactive Queries](https://kafka.apache.org/documentation/streams/developer-guide/interactive-queries.html)
- [Spring for Apache Kafka — Kafka Streams Support](https://docs.spring.io/spring-kafka/reference/streams.html)
- [Apache Kafka — KeyQueryMetadata API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/KeyQueryMetadata.html)
