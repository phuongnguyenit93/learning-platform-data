# Chia sẻ requester, quản lý kết nối và thời điểm dispose

`RSocketRequester` là facade Spring dùng để gửi nhiều request qua một RSocket connection. Với một server đích và cùng cấu hình kết nối, ứng dụng thường tạo một requester dùng chung rồi inject vào nhiều service. Requester hỗ trợ các lời gọi đồng thời; các request được multiplex trên connection chung. Tạo requester mới cho từng thao tác sẽ làm tăng số connection, chi phí SETUP và tài nguyên mạng.

Vòng đời requester cần có một chủ sở hữu rõ ràng. Bean dùng chung không nên bị một service tùy ý dispose khi service đó hoàn tất công việc. Ứng dụng nên giữ requester trong Spring container, dừng các luồng phát request khi shutdown và gọi `dispose()` khi toàn bộ ứng dụng hoặc thành phần sở hữu connection kết thúc.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao có thể chia sẻ một `RSocketRequester` cho nhiều service.
- Tạo requester dạng Spring bean và inject qua constructor.
- Phân biệt builder, requester, request spec và connection bên dưới.
- Hiểu connection được tạo khi nào và cách các request dùng chung connection.
- Quản lý nhiều requester theo endpoint, cấu hình hoặc danh tính kết nối.
- Phân biệt reconnect với session resumption.
- Chọn đúng thời điểm gọi `dispose()` và kiểm tra trạng thái requester.
- Thiết kế shutdown, kiểm thử và quan sát vòng đời kết nối.

## 1. Vì sao nên chia sẻ requester?

RSocket là giao thức multiplex hai chiều. Một connection có thể mang nhiều stream request đồng thời. Mỗi request có stream ID riêng; các stream độc lập cùng đi qua một transport connection. Vì vậy, một requester có thể phục vụ nhiều lời gọi từ các component trong ứng dụng.

Ví dụ một ứng dụng realtime có `DeviceQueryService`, `DeviceEventPublisher` và `DeviceStreamService`. Cả ba cùng gọi một RSocket server. Nếu mỗi service tự tạo requester, ứng dụng có thể mở ba connection tới cùng endpoint dù chúng dùng cùng MIME type, setup metadata và danh tính kết nối. Một requester singleton giúp các service dùng chung connection và cấu hình.

| Cách tổ chức | Hành vi | Hệ quả |
|---|---|---|
| Một requester dùng chung cho cùng endpoint/cấu hình | Nhiều request đồng thời qua connection chung | Ít connection, dùng multiplexing của RSocket |
| Mỗi service tạo requester riêng | Mỗi requester quản lý connection riêng | Tăng handshake, socket và keepalive |
| Mỗi request tạo requester mới | Connection được tạo lặp lại theo từng thao tác | Tốn tài nguyên, dễ tạo nhiều kết nối ngắn hạn |
| Một requester cho mỗi endpoint hoặc identity khác nhau | Tách connection theo ranh giới cấu hình | Dễ kiểm soát bảo mật và vòng đời |

Spring mô tả requester tạo bởi `tcp(...)` hoặc `webSocket(...)` là có thể dùng đồng thời; các request dùng một connection chung và connection có thể được thiết lập lại khi có request tiếp theo sau khi bị mất. Việc chia sẻ requester là cách dùng tự nhiên của API này.

## 2. Phân biệt Builder, RSocketRequester và request spec

Ba đối tượng có vai trò khác nhau:

| Đối tượng | Vai trò | Nên dùng ở đâu |
|---|---|---|
| `RSocketRequester.Builder` | Tập hợp cấu hình để tạo requester | Lúc khởi tạo bean |
| `RSocketRequester` | Facade sống cùng connection/client | Inject và chia sẻ giữa các service |
| `RequestSpec` / `RetrieveSpec` | Mô tả một request cụ thể: route, data, metadata, kiểu response | Tạo mới trong từng lần gọi |

Không giữ một `RequestSpec` làm đối tượng dùng chung cho nhiều request. Mỗi lần gọi nên bắt đầu bằng `requester.route(...)`, thêm data/metadata cần thiết rồi kết thúc bằng `retrieveMono`, `retrieveFlux` hoặc `send`.

`RSocketRequester.Builder` là đối tượng cấu hình. Hãy hoàn tất cấu hình rồi tạo requester; không dùng builder như một client để gửi request. Nếu cần requester cho endpoint hoặc cấu hình khác, tạo bean/requester riêng từ cấu hình tương ứng.

## 3. Tạo một requester singleton trong Spring

Mặc định bean do `@Bean` khai báo có scope singleton. Có thể tạo một requester cho một dịch vụ từ builder Spring Boot cung cấp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
public class RSocketClientConfiguration {

    @Bean(destroyMethod = "dispose")
    RSocketRequester telemetryRequester(
            RSocketRequester.Builder builder) {

        return builder.tcp("rsocket.internal", 7000);
    }
}
~~~

Bean này có hai ý nghĩa:

- Mọi component inject `RSocketRequester` cùng qualifier sẽ nhận cùng một instance.
- Spring gọi `dispose()` khi bean bị hủy trong quá trình đóng application context.

Lời gọi `builder.tcp(...)` tạo requester/client dùng connection chung. Nó không nhất thiết mở socket ngay tại dòng cấu hình. Theo tài liệu Spring, kết nối được thiết lập trong suốt khi có request đầu tiên và được tái sử dụng cho các request sau.

Nếu dùng WebSocket, cách tạo tương tự:

~~~java
@Bean(destroyMethod = "dispose")
RSocketRequester notificationRequester(
        RSocketRequester.Builder builder) {

    return builder.webSocket(
            URI.create("wss://realtime.example.com/rsocket"));
}
~~~

Dùng `wss://` khi WebSocket được bảo vệ bằng TLS. Endpoint, credential và TLS nên lấy từ cấu hình môi trường thay vì hard-code vào source code.

## 4. Inject cùng requester vào nhiều service

Dùng constructor injection để các service nhận requester đã được cấu hình:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

@Service
public class DeviceQueryService {

    private final RSocketRequester requester;

    public DeviceQueryService(
            @Qualifier("telemetryRequester")
            RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<DeviceStatus> findStatus(String deviceId) {
        return requester
                .route("devices.status")
                .data(new DeviceStatusQuery(deviceId))
                .retrieveMono(DeviceStatus.class);
    }
}
~~~

Một service khác có thể dùng chính requester đó:

~~~java
@Service
public class DeviceEventPublisher {

    private final RSocketRequester requester;

    public DeviceEventPublisher(
            @Qualifier("telemetryRequester")
            RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<Void> publish(DeviceEvent event) {
        return requester
                .route("devices.events")
                .data(event)
                .send();
    }
}
~~~

Cả hai service không cần biết service còn lại đang dùng connection. Chúng chỉ tạo request spec độc lập từ requester đã inject. Không lưu route/data của request trước vào biến mutable dùng chung.

### Không tạo requester trong mỗi method

Mẫu sau tạo một requester mới mỗi lần gọi và thường là thiết kế không phù hợp:

~~~java
public Mono<DeviceStatus> findStatus(String deviceId) {
    RSocketRequester requester =
            RSocketRequester.builder().tcp("rsocket.internal", 7000);

    return requester.route("devices.status")
            .data(new DeviceStatusQuery(deviceId))
            .retrieveMono(DeviceStatus.class);
}
~~~

Requester vừa tạo không có chủ sở hữu vòng đời rõ ràng. Nếu method được gọi thường xuyên, ứng dụng sẽ tạo nhiều client/connection và khó đóng chúng đúng thời điểm. Hãy tạo requester trong cấu hình Spring rồi inject vào service.

## 5. Nhiều request đồng thời trên một connection

Requester dùng chung có thể phục vụ các lời gọi đồng thời. Mỗi request có route và payload riêng; RSocket multiplex chúng trên connection.

~~~java
public Mono<Tuple2<DeviceStatus, DeviceStatus>> compareDevices(
        String firstId, String secondId) {

    Mono<DeviceStatus> first = requester.route("devices.status")
            .data(new DeviceStatusQuery(firstId))
            .retrieveMono(DeviceStatus.class);

    Mono<DeviceStatus> second = requester.route("devices.status")
            .data(new DeviceStatusQuery(secondId))
            .retrieveMono(DeviceStatus.class);

    return Mono.zip(first, second);
}
~~~

`Mono.zip` subscribe hai publisher và chờ cả hai kết quả. Hai request có thể chạy đồng thời trên cùng requester. Không cần mở hai TCP connection chỉ để thực hiện hai truy vấn độc lập.

Với stream, mỗi lần gọi `retrieveFlux(...)` tạo một interaction riêng. Demand và cancellation của stream được xử lý theo semantics của interaction đó. Chia sẻ requester không có nghĩa các subscriber dùng chung một `Flux` hoặc chia sẻ dữ liệu với nhau; hãy tạo publisher theo từng request.

### Chia sẻ requester không có nghĩa chia sẻ trạng thái request

Mỗi lời gọi nên tự khai báo:

- Route và route variables.
- Data payload.
- Metadata theo request như correlation ID hoặc thông tin xác thực theo thiết kế.
- Kiểu response mong muốn.
- Timeout, retry và chính sách xử lý lỗi của nghiệp vụ đó.

Không giữ một đối tượng request spec rồi thay đổi route hoặc data trước mỗi lần subscribe. Việc này có thể khiến các lời gọi cạnh tranh nhau và làm rò rỉ dữ liệu giữa request.

## 6. Khi nào cần nhiều requester?

Chia sẻ một requester phù hợp khi các lời gọi có cùng endpoint và cùng cấu hình connection. Tạo requester riêng khi có một ranh giới thực sự khác biệt:

| Khác biệt | Cách tổ chức phù hợp |
|---|---|
| Server đích khác nhau | Một requester cho mỗi endpoint hoặc nhóm endpoint |
| TCP và WebSocket tới các dịch vụ khác nhau | Requester riêng theo transport |
| MIME type hoặc codec khác nhau | Requester riêng với `RSocketStrategies` tương ứng |
| TLS/client certificate khác nhau | Requester riêng theo cấu hình bảo mật |
| Danh tính được xác thực ở SETUP | Requester/connection riêng theo identity |
| Tenant có connection-level context riêng | Tách connection theo tenant, có giới hạn số lượng |
| Chỉ khác route hoặc payload | Dùng chung requester, tạo request spec mới |

Không tạo một requester cho từng người dùng nếu thông tin người dùng chỉ cần truyền ở phạm vi request. Có thể dùng metadata theo request khi giao thức bảo mật và server cho phép. Nhưng nếu danh tính được xác lập trong `SETUP`, bằng client certificate hoặc setup metadata, connection mang danh tính đó; không chia sẻ connection giữa các principal khác nhau.

Một pool requester theo tenant có thể hữu ích trong một số hệ thống, nhưng phải giới hạn số connection, có chính sách idle eviction và đóng requester khi tenant không còn hoạt động. Tránh giữ một map requester không giới hạn theo tenant hoặc user.

## 7. SETUP metadata và request metadata có phạm vi khác nhau

Thông tin trong frame `SETUP` được dùng khi khởi tạo connection. Data MIME type và metadata MIME type được chọn ở cấp connection; setup data/metadata cũng thuộc phạm vi này. Chúng không phải chỗ phù hợp để thay đổi user token hoặc correlation ID cho từng lời gọi.

Metadata theo request được khai báo khi tạo request spec:

~~~java
public Mono<DeviceStatus> findStatus(
        String deviceId, String correlationId) {

    return requester.route("devices.status")
            .metadata(correlationId, CORRELATION_ID_MIME_TYPE)
            .data(new DeviceStatusQuery(deviceId))
            .retrieveMono(DeviceStatus.class);
}
~~~

`CORRELATION_ID_MIME_TYPE` là MIME type metadata do ứng dụng định nghĩa và phải được hai phía thống nhất. Ví dụ này chỉ minh họa metadata theo request; không dùng correlation ID như credential.

Khi dùng composite metadata, mỗi entry có MIME type riêng. Dữ liệu định danh, tenant hoặc authorization phải được xác thực và kiểm tra ở server. Không tin metadata chỉ vì nó được gửi qua RSocket connection.

## 8. Connection được tạo và tái sử dụng khi nào?

Với cách tạo requester từ `RSocketRequester.Builder.tcp(...)` hoặc `webSocket(...)`, Spring quản lý một RSocket client dùng connection chung. Việc tạo requester không nhất thiết đồng nghĩa TCP/WebSocket đã mở ngay lúc đó. Khi request đầu tiên được thực hiện, connection được thiết lập và dùng cho các request tiếp theo.

Một vòng đời đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> Configured: builder.tcp / webSocket
    Configured --> Connected: request đầu tiên cần gửi
    Connected --> Connected: nhiều request multiplex
    Connected --> Disconnected: transport bị mất
    Disconnected --> Connected: connection được thiết lập lại
    Connected --> Disposed: dispose()
    Configured --> Disposed: dispose() trước request
    Disposed --> [*]
~~~

Khi connection bị mất, những request đang chạy có thể kết thúc bằng lỗi tùy thời điểm và cấu hình. Connection được thiết lập lại cho những request tiếp theo theo cơ chế của client. Không suy ra rằng mọi request đang dở sẽ tự động được phát lại.

## 9. Phân biệt reconnect và session resumption

Reconnect và resumption giải quyết hai vấn đề liên quan nhưng khác nhau:

| Cơ chế | Kết quả | Tác động tới stream đang chạy |
|---|---|---|
| Reconnect | Tạo lại transport/connection để request tiếp theo có thể chạy | Request đang dở có thể lỗi; ứng dụng có thể phải mở lại interaction |
| Session resumption | Nối lại session protocol cũ nếu cả hai peer giữ đủ state và resume buffer | Có thể tiếp tục các stream còn hiệu lực theo trạng thái protocol |
| Tạo requester mới | Tạo một client/connection lifecycle mới | Không tự khôi phục request hoặc subscription của requester cũ |

Có thể cấu hình RSocket connector bên dưới thông qua callback của builder nếu cần keepalive, resume hoặc interceptor:

~~~java
RSocketRequester requester = builder
        .rsocketConnector(connector -> connector
                .resume(new Resume()
                        .sessionDuration(Duration.ofMinutes(2))))
        .tcp("rsocket.internal", 7000);
~~~

Đây là ví dụ cấu hình ở mức rsocket-java; constructor và các tùy chọn của `Resume` có thể khác theo phiên bản dependency. Cần kiểm tra API của phiên bản đang dùng và cấu hình tương ứng ở server.

Nếu ứng dụng chỉ cần connection mới cho các request sau, reconnect có thể đủ. Nếu cần tiếp tục stream đang chạy sau mất mạng, phải thiết kế và kiểm thử resumption. Cả hai cơ chế đều không thay thế idempotency của nghiệp vụ: timeout hoặc mất kết nối có thể xảy ra sau khi server đã thực hiện side effect.

## 10. dispose() làm gì?

`RSocketRequester` triển khai `reactor.core.Disposable`. Phương thức `dispose()` là shortcut để dispose `RSocketClient` bên dưới, đóng connection transport và thông báo cho các subscriber. `isDisposed()` cho biết requester đã bị dispose hay chưa.

Hai phương thức `dispose()` và `isDisposed()` có từ Spring Framework 5.3.7. Nếu dự án dùng baseline cũ hơn, hãy kiểm tra API của phiên bản đó và quản lý vòng đời qua client/connector mà ứng dụng đang sở hữu.

~~~java
requester.dispose();

if (requester.isDisposed()) {
    log.info("RSocket requester has been disposed");
}
~~~

`dispose()` kết thúc vòng đời client dùng chung. Các service đang giữ cùng instance requester sẽ cùng bị ảnh hưởng. Sau khi dispose, không tiếp tục dùng requester đó để gửi request mới; hãy tạo một requester mới trong một lifecycle mới nếu cần kết nối lại.

### Không dispose sau mỗi request

Không làm như sau với requester singleton:

~~~java
public Mono<DeviceStatus> findStatus(String deviceId) {
    return requester.route("devices.status")
            .data(new DeviceStatusQuery(deviceId))
            .retrieveMono(DeviceStatus.class)
            .doFinally(signal -> requester.dispose());
}
~~~

Mỗi request hoàn tất sẽ đóng connection dùng chung. Các service khác có thể đang có request hoặc stream hoạt động trên cùng connection. `dispose()` thuộc quyền sở hữu vòng đời của bean/connection, không thuộc vòng đời của một request riêng lẻ.

### dispose không phải business acknowledgement

Đóng requester chỉ là thao tác vòng đời transport/client. Nó không xác nhận các nghiệp vụ trước đó đã commit hoặc các event đã được xử lý xong. Nếu cần shutdown an toàn, ứng dụng phải dừng producer, chờ các công việc quan trọng hoàn tất theo chính sách của mình, sau đó mới dispose requester.

## 11. Đóng requester cùng Spring ApplicationContext

Cách đơn giản là khai báo `destroyMethod = "dispose"` trên bean:

~~~java
@Bean(destroyMethod = "dispose")
RSocketRequester telemetryRequester(
        RSocketRequester.Builder builder) {
    return builder.tcp("rsocket.internal", 7000);
}
~~~

Spring gọi destroy method khi application context đóng và bean bị hủy. Đây là lựa chọn rõ ràng cho requester do Spring container sở hữu.

Nếu requester được tạo thủ công ngoài Spring, component tạo nó phải giữ quyền sở hữu và gọi `dispose()` khi kết thúc:

~~~java
public final class RSocketClientOwner implements AutoCloseable {

    private final RSocketRequester requester;

    public RSocketClientOwner(RSocketRequester requester) {
        this.requester = requester;
    }

    @Override
    public void close() {
        requester.dispose();
    }
}
~~~

Không để nhiều component cùng nghĩ rằng mình sở hữu requester. Chọn một nơi duy nhất chịu trách nhiệm đóng connection; các service khác chỉ sử dụng instance được inject.

### Thứ tự shutdown

Một trình tự shutdown thực tế:

1. Ngừng nhận công việc mới từ scheduler, message listener hoặc API tạo request.
2. Ngừng producer phát thêm request/stream mới.
3. Chờ các tác vụ cần hoàn tất trong khoảng drain time do ứng dụng quy định.
4. Hủy các stream còn lại theo chính sách shutdown.
5. Dispose requester và giải phóng tài nguyên liên quan.
6. Để Spring đóng application context và các bean còn lại.

`dispose()` không tự thực hiện toàn bộ quy trình drain nghiệp vụ. Nếu hệ thống cần hoàn tất một số giao dịch trước khi đóng, hãy điều phối chúng ở tầng ứng dụng trước khi gọi dispose.

## 12. Quản lý requester nhận từ server connection

Spring cũng cho phép handler server nhận `RSocketRequester` đại diện cho một client connection, ví dụ trong `@ConnectMapping` hoặc `@MessageMapping`. Requester này thuộc về connection cụ thể đó, khác với requester singleton mà ứng dụng tạo để gọi một server từ phía client.

~~~java
@Controller
public class ClientConnectionController {

    @ConnectMapping
    Mono<Void> connected(RSocketRequester requester) {
        connectionRegistry.register(requester);
        return Mono.empty();
    }
}
~~~

Ví dụ chỉ đăng ký requester theo connection; `connectionRegistry` là thành phần do ứng dụng quản lý. `@ConnectMapping` xử lý SETUP nên không nên chờ một request ngược tới client hoàn tất ngay trong pipeline xử lý SETUP. Nếu cần gửi thông báo sau khi kết nối sẵn sàng, hãy kích hoạt nó ở một luồng công việc tách biệt sau khi connection được thiết lập.

Không đưa requester của một client connection vào biến singleton dùng chung cho tất cả client. Nếu cần gửi thông báo ngược tới client đã kết nối, hãy lưu requester theo định danh connection trong một registry có vòng đời rõ ràng, loại bỏ entry khi connection đóng và xử lý trường hợp requester đã disposed.

Requester theo connection không phải tài nguyên toàn cục. Khi client disconnect, các thao tác gửi ngược có thể lỗi và registry cần được dọn dẹp.

## 13. Quan sát và chẩn đoán kết nối

Để quản lý requester dùng chung, nên theo dõi:

- Số requester được tạo theo endpoint và cấu hình.
- Số connection thực tế đang hoạt động.
- Thời điểm kết nối đầu tiên và các lần kết nối lại.
- Số request theo interaction model, latency và error rate.
- Số stream đang chạy, số stream bị cancel và thời gian sống.
- Số lần dispose và lý do đóng connection.
- Số lần timeout hoặc lỗi trong giai đoạn reconnect/resume.

Không gắn token, payload nhạy cảm hoặc dữ liệu cá nhân vào log. Có thể dùng connection ID, endpoint name và correlation ID đã được kiểm soát để liên kết log giữa các service.

`RSocketRequester.isDisposed()` hữu ích để kiểm tra trạng thái dispose cục bộ. Nó không phải health check đầy đủ cho server; một requester chưa disposed vẫn có thể đang chờ kết nối hoặc gặp lỗi transport. Muốn kiểm tra sức khỏe remote service, hãy dùng health request hoặc metric connection riêng.

## 14. Kiểm thử chia sẻ và dispose

Một bộ kiểm thử nên xác minh cả việc dùng chung lẫn quyền sở hữu vòng đời:

| Ca kiểm thử | Điều cần xác minh |
|---|---|
| Hai service inject cùng qualifier | Cả hai nhận cùng bean requester |
| Nhiều request đồng thời | Các request được gửi qua requester dùng chung và nhận kết quả đúng |
| Request đầu tiên | Connection được thiết lập khi có request theo cơ chế lazy của builder |
| Nhiều lần gọi liên tiếp | Requester tái sử dụng connection thay vì tạo client mới mỗi lần |
| Transport bị ngắt | Request đang chạy được xử lý theo lỗi; request tiếp theo có hành vi reconnect đã cấu hình |
| Resume được bật | Chỉ kết luận stream tiếp tục khi kiểm thử thực tế RESUME/RESUME_OK thành công |
| ApplicationContext đóng | Destroy method gọi dispose đúng một lần theo ownership |
| Một request hoàn tất | Requester singleton vẫn hoạt động cho request tiếp theo |
| Requester đã disposed | Không còn được dùng để gửi request mới |
| Nhiều endpoint/identity | Requester không bị dùng nhầm giữa các cấu hình hoặc principal |

Ví dụ kiểm tra bean scope:

~~~java
assertThat(context.getBean("telemetryRequester"))
        .isSameAs(context.getBean("telemetryRequester"));
~~~

Để kiểm thử multiplexing, khởi tạo nhiều lời gọi đồng thời bằng `Mono.zip` hoặc `Flux.flatMap` rồi xác minh mọi response. Đừng chỉ đếm số lần gọi builder; cần quan sát connection thực tế hoặc metric transport nếu muốn chứng minh chỉ có một connection.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Tạo requester trong mỗi method | Tạo nhiều client và connection | Đưa requester vào Spring bean dùng chung |
| Mỗi service tự dispose requester singleton | Các service khác mất connection | Chỉ bean owner đóng requester |
| Dispose sau mỗi request | Request đồng thời và stream khác bị gián đoạn | Dispose khi kết thúc lifecycle |
| Dùng chung requester giữa identity được xác thực ở SETUP khác nhau | Có thể trộn ngữ cảnh bảo mật | Tách requester theo connection identity |
| Đưa token người dùng thay đổi vào setup metadata của singleton | Token không đổi theo từng request | Dùng request metadata hoặc connection riêng |
| Cache RequestSpec để dùng nhiều lần | Trạng thái route/data có thể bị dùng nhầm | Tạo spec mới cho mỗi lời gọi |
| Cho rằng reconnect tự phát lại mọi request đang chạy | Mất kết quả hoặc side effect trùng khi retry | Phân loại lỗi, idempotency và mở lại stream có chủ đích |
| Không dọn requester theo client connection | Registry giữ reference tới client đã ngắt | Theo dõi close và xóa entry |
| Không dispose khi shutdown | Tài nguyên transport/event loop có thể còn sống | Khai báo destroy method hoặc lifecycle owner |

## 16. Checklist triển khai

- [ ] Một requester singleton cho mỗi endpoint và cấu hình connection phù hợp.
- [ ] Builder chỉ được dùng trong giai đoạn cấu hình và tạo requester.
- [ ] Các service inject requester qua constructor.
- [ ] Mỗi request tạo route/data/metadata spec riêng.
- [ ] Không tạo requester mới cho từng message.
- [ ] Không dispose requester từ service tiêu thụ dùng chung.
- [ ] Bean owner có destroy method dispose.
- [ ] Producer được dừng trước khi requester bị dispose.
- [ ] Phân biệt reconnect với session resumption.
- [ ] Identity ở SETUP được tách theo connection; metadata theo request được dùng đúng phạm vi.
- [ ] Có metric connection, request, reconnect, lỗi và dispose.
- [ ] Kiểm thử shutdown, mất mạng, request đồng thời và nhiều endpoint.

## Kết luận

`RSocketRequester` được thiết kế để chia sẻ giữa nhiều component và gửi request đồng thời trên connection chung. Hãy tạo requester một lần trong Spring bean, inject qua constructor và tạo request spec mới cho từng thao tác. Tách requester khi endpoint, cấu hình transport hoặc identity ở cấp connection khác nhau. `dispose()` đóng client/transport dùng chung và thông báo cho subscriber, vì vậy chỉ chủ sở hữu bean nên gọi khi lifecycle kết thúc. Dừng công việc mới và điều phối drain trước khi dispose để shutdown có trật tự.

## Tài liệu tham khảo

- [Spring Framework Reference – RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester Javadoc – Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [RSocketRequester.Builder Javadoc – Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
