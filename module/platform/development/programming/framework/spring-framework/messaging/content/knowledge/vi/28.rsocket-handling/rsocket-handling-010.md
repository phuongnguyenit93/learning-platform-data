# Tách xử lý nghiệp vụ khỏi thao tác transport và phiên kết nối

## Mục tiêu

Sau bài này, bạn có thể thiết kế ứng dụng Spring RSocket sao cho use case và quy tắc nghiệp vụ không phụ thuộc vào `RSocketRequester`, route, payload, TCP/WebSocket hay vòng đời của một kết nối. Bạn cũng biết đặt xử lý kết nối ở đúng adapter, quản lý client đang kết nối an toàn và kiểm thử nghiệp vụ mà không cần mở socket.

## 1. Vì sao cần tách?

RSocket là giao thức truyền thông hai chiều, hỗ trợ Request-Response, Request-Stream, Request-Channel và Fire-and-Forget. Spring cung cấp `@MessageMapping`, `@ConnectMapping` và `RSocketRequester` để nhận và gửi message. Những API này giải quyết cách message đi qua mạng; chúng không nên quyết định một nghiệp vụ như tạo đơn, ghi nhận số đo, tính hạn mức hay cấp quyền.

Nếu đặt toàn bộ xử lý vào controller RSocket, một phương thức có thể vừa đọc payload, kiểm tra route, lấy thông tin kết nối, kiểm tra điều kiện nghiệp vụ, ghi database, gửi message ngược lại client và xử lý lỗi transport. Khi đó thay TCP bằng WebSocket, thêm HTTP API, chạy tác vụ nền hoặc viết unit test đều trở nên khó khăn vì nghiệp vụ bị buộc vào chi tiết giao tiếp.

Mục tiêu của việc tách lớp là để cùng một use case có thể được gọi từ nhiều adapter. Ví dụ, `RecordMeasurementUseCase` có thể được gọi bởi RSocket, REST, một message broker hoặc một tác vụ theo lịch. Mỗi adapter chỉ chuyển dữ liệu đầu vào thành command, gọi use case và chuyển kết quả thành định dạng phản hồi tương ứng.

## 2. Phân biệt dữ liệu nghiệp vụ, request và connection

Ba loại dữ liệu sau có vòng đời khác nhau và cần được quản lý ở nơi phù hợp:

| Loại | Ví dụ | Vòng đời và nơi quản lý |
| --- | --- | --- |
| Trạng thái nghiệp vụ | Đơn hàng, số dư, trạng thái thiết bị, quyền sở hữu | Thuộc domain/application; lưu qua repository hoặc hệ thống lưu trữ phù hợp |
| Trạng thái request | Payload, route, correlation ID, metadata của một lệnh | Chỉ phục vụ một request; được adapter trích xuất và chuyển thành command |
| Trạng thái connection | `RSocketRequester`, kết nối TCP/WebSocket, keepalive, trạng thái đóng/mở | Thuộc infrastructure/transport; tồn tại trong thời gian kết nối |

**Một RSocket connection không đồng nghĩa với một tài khoản, một người dùng hay một phiên đăng nhập của ứng dụng.** Một người dùng có thể mở nhiều kết nối; một kết nối cũng có thể được chia sẻ bởi một gateway đại diện cho nhiều người dùng. Kết nối có thể bị ngắt rồi tạo lại trong khi dữ liệu nghiệp vụ vẫn phải còn nguyên.

Không lưu dữ liệu quan trọng duy nhất trong map gắn với connection. Nếu server khởi động lại hoặc client reconnect, dữ liệu đó có thể mất. Registry kết nối chỉ nên giữ tham chiếu tạm thời tới các peer đang hoạt động và thông tin cần để gửi message.

## 3. Phân chia trách nhiệm

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| Domain và application service | Thực thi quy tắc, điều phối repository và các port nghiệp vụ | Đọc `RSocketRequester`, route hoặc payload |
| Inbound RSocket adapter (`@MessageMapping`) | Nhận message, kiểm tra/ánh xạ DTO, gọi use case, trả kết quả | Chứa toàn bộ quy tắc nghiệp vụ |
| Connection adapter (`@ConnectMapping`) | Xử lý SETUP, xác thực/ngữ cảnh kết nối, đăng ký và theo dõi connection | Thực thi một nghiệp vụ dài chỉ vì client vừa kết nối |
| Outbound RSocket adapter | Gửi message qua requester, chuyển lỗi giao tiếp về dạng phù hợp | Để application service tự tạo route hoặc tự quản lý socket |
| Connection registry | Tra cứu các peer đang kết nối và loại bỏ entry khi connection đóng | Là nơi lưu trạng thái domain lâu dài |

Luồng request đi vào:

```text
RSocket frame
    -> @MessageMapping (inbound adapter)
    -> Command / application use case
    -> Domain + repository / outbound ports
    -> Kết quả use case
    -> RSocket response
```

Luồng gửi thông báo chủ động tới client:

```text
Application use case
    -> ClientNotificationPort
    -> RSocket outbound adapter
    -> Connection registry
    -> RSocketRequester của peer đang kết nối
    -> RSocket frame
```

Hai luồng có thể dùng chung domain/application service nhưng chỉ adapter biết route, payload, metadata và API của RSocket.

## 4. Đặt nghiệp vụ trong application service

Ví dụ: client gửi một số đo và hệ thống cần lưu lại. Command và use case mô tả ý nghĩa nghiệp vụ, không mô tả giao thức đã dùng để gửi lệnh.

```java
// RecordMeasurementCommand.java
public record RecordMeasurementCommand(String sensorId, double value) {}

// MeasurementReceipt.java
public record MeasurementReceipt(String measurementId, String sensorId) {}

// RecordMeasurementUseCase.java
public interface RecordMeasurementUseCase {
    Mono<MeasurementReceipt> execute(RecordMeasurementCommand command);
}

// RecordMeasurementService.java
@Service
public class RecordMeasurementService implements RecordMeasurementUseCase {

    private final MeasurementRepository repository;

    public RecordMeasurementService(MeasurementRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<MeasurementReceipt> execute(RecordMeasurementCommand command) {
        Measurement measurement = new Measurement(command.sensorId(), command.value());
        return repository.save(measurement)
            .map(saved -> new MeasurementReceipt(saved.id(), saved.sensorId()));
    }
}
```

`MeasurementRepository`, `Measurement` và kiểu trả về được định nghĩa ở application/domain theo quy ước của dự án. Điểm quan trọng là use case không import `org.springframework.messaging.rsocket.*`, không nhận `RSocketRequester`, không biết client đang dùng TCP hay WebSocket và không cần biết route là `measurements.record`.

Ví dụ vẫn dùng `Mono` của Project Reactor để thể hiện xử lý bất đồng bộ. `Mono` không phải API riêng của RSocket, nhưng nó tạo phụ thuộc vào Reactor. Nếu kiến trúc yêu cầu application layer độc lập cả với Reactor, có thể thiết kế port bằng kiểu đồng bộ hoặc một abstraction bất đồng bộ khác. Hãy cân nhắc chi phí chuyển đổi và cách xử lý backpressure; không cần loại bỏ `Mono` chỉ để đạt một mức tách lớp hình thức.

## 5. Dùng `@MessageMapping` làm inbound adapter

Controller RSocket nhận DTO của wire protocol, ánh xạ sang command và chuyển tiếp cho use case:

```java
public record MeasurementRequest(String sensorId, double value) {}

@Controller
public class MeasurementRSocketController {

    private final RecordMeasurementUseCase recordMeasurement;

    public MeasurementRSocketController(RecordMeasurementUseCase recordMeasurement) {
        this.recordMeasurement = recordMeasurement;
    }

    @MessageMapping("measurements.record")
    public Mono<MeasurementReceipt> record(@Payload MeasurementRequest request) {
        RecordMeasurementCommand command =
            new RecordMeasurementCommand(request.sensorId(), request.value());
        return recordMeasurement.execute(command);
    }
}
```

Spring ánh xạ route `measurements.record` tới handler. Một payload đơn và một kết quả đơn như trên tương ứng Request-Response. Nếu use case trả `Flux<T>`, Spring có thể ánh xạ thành Request-Stream; interaction type được suy ra từ cardinality của input và output.

Adapter là nơi phù hợp để kiểm tra cấu trúc DTO, chuyển kiểu dữ liệu, đọc metadata cần thiết và chuyển lỗi kỹ thuật thành lỗi giao thức phù hợp. Kiểm tra nghiệp vụ như sensor có thuộc khách hàng hay giá trị có nằm trong giới hạn hợp lệ phải được thực hiện ở use case/domain để mọi adapter đều áp dụng cùng quy tắc.

## 6. Đặt quản lý kết nối trong connection adapter

`@ConnectMapping` xử lý frame `SETUP` khi connection bắt đầu và các thông báo `METADATA_PUSH` ở cấp connection. Nó phù hợp cho việc kiểm tra thông tin thiết lập, xác định peer, đăng ký connection hoặc khởi tạo tài nguyên gắn với connection. Nó không thay thế `@MessageMapping` cho các lệnh nghiệp vụ.

Ví dụ client gửi route và dữ liệu thiết lập trong SETUP:

```java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("clients.connect")
    .setupData(new ClientHello(clientId))
    .tcp(host, port);
```

Đoạn trên thuộc component quản lý kết nối phía client. `tcp()` chuẩn bị requester; theo Spring reference, kết nối dùng chung được thiết lập khi request được thực thi. Có thể dùng WebSocket nếu transport được chọn là WebSocket. Application service không nên tự tạo requester cho từng lệnh nghiệp vụ.

Ở phía responder, controller connection có thể đăng ký requester đang đại diện cho peer:

```java
@Controller
public class ClientConnectionController {

    private final RSocketConnectionRegistry registry;

    public ClientConnectionController(RSocketConnectionRegistry registry) {
        this.registry = registry;
    }

    @ConnectMapping("clients.connect")
    public Mono<Void> connected(
            RSocketRequester requester, @Payload ClientHello hello) {

        registry.register(hello.clientId(), requester);

        requester.rsocketClient().onClose()
            .doFinally(signal -> registry.remove(hello.clientId(), requester))
            .subscribe();

        return Mono.empty();
    }
}
```

Đây là ví dụ cho Spring Framework có `RSocketRequester.rsocketClient()` và RSocket Java có `onClose()`. Hãy kiểm tra API theo phiên bản Spring Framework/RSocket Java đang dùng. `onClose()` là tín hiệu vòng đời của connection; `doFinally` chạy khi tín hiệu kết thúc, lỗi hoặc bị hủy. Subscription ở đây chỉ để adapter quan sát sự kiện đóng connection. Không dùng cách `subscribe()` nội bộ này để âm thầm chạy nghiệp vụ; các luồng nghiệp vụ nên được trả về cho caller quản lý.

`RSocketConnectionRegistry` là thành phần infrastructure, ví dụ có thể dùng `ConcurrentHashMap<String, RSocketRequester>` nếu quy ước mỗi client chỉ có một connection đang hoạt động. Phương thức `remove(clientId, requester)` nên xóa theo cả key và đúng instance. Nếu một connection cũ đóng sau khi connection mới đã thay thế nó, thao tác xóa có điều kiện sẽ không xóa nhầm connection mới.

Khi một client có thể mở nhiều connection đồng thời, không dùng một requester duy nhất cho mỗi `clientId`. Hãy lưu theo connection ID hoặc một tập các connection cho mỗi client, rồi xác định chính sách gửi tới một peer, tất cả peer hay peer gần nhất. Khi đóng connection, chỉ loại bỏ đúng entry tương ứng.

`@ConnectMapping` không phải handler tổng quát cho mọi sự kiện nghiệp vụ và không phải nơi lưu trạng thái lâu dài. Nếu cần theo dõi đóng kết nối, hãy dùng tín hiệu close ở tầng RSocket/transport như ví dụ, hoặc cơ chế lifecycle tương ứng của connector. Khi `@ConnectMapping` cần khởi phát request tới peer ngay lúc setup, Spring yêu cầu việc đó được tách khỏi quá trình xử lý setup; không giữ setup chờ chính request qua requester hoàn tất.

## 7. Ẩn `RSocketRequester` sau một outbound port

Khi nghiệp vụ cần gửi thông báo, application layer định nghĩa ý định gửi thông báo. Adapter mới biết cách tìm requester và chọn route:

```java
public interface ClientNotificationPort {
    Mono<Void> notify(String clientId, ClientNotification notification);
}

@Component
public class RSocketClientNotificationAdapter implements ClientNotificationPort {

    private final RSocketConnectionRegistry registry;

    public RSocketClientNotificationAdapter(RSocketConnectionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Mono<Void> notify(String clientId, ClientNotification notification) {
        return Mono.defer(() -> registry.find(clientId)
            .map(requester -> requester.route("clients.notification")
                .data(notification)
                .send())
            .orElseGet(() -> Mono.error(new ClientOfflineException(clientId))));
    }
}
```

Use case chỉ phụ thuộc vào `ClientNotificationPort`; nó không biết `clients.notification` là route RSocket. Adapter cũng có thể được thay bằng implementation ghi notification vào queue, gửi qua WebSocket hoặc lưu thông báo để client lấy sau.

Lưu ý: `send()` trả `Mono<Void>` cho biết thao tác gửi message đã hoàn tất ở phía requester; điều đó không tự chứng minh handler phía nhận đã xử lý nghiệp vụ thành công. Nếu nghiệp vụ cần xác nhận, hãy thiết kế một interaction có response/acknowledgement, chẳng hạn Request-Response, và mô hình hóa kết quả xác nhận rõ ràng.

## 8. Bảo mật: identity không đồng nghĩa với connection ID

Không tin một `clientId`, `userId` hoặc `role` chỉ vì giá trị đó xuất hiện trong payload hay metadata SETUP. Những trường này là dữ liệu do phía gửi cung cấp và cần được xác thực/ủy quyền trước khi dùng để đăng ký connection hoặc gọi nghiệp vụ.

Spring Security hỗ trợ xác thực RSocket ở thời điểm SETUP hoặc tại từng request. Xác thực ở SETUP phù hợp khi một connection được gắn với một người dùng duy nhất. Nếu một gateway chia sẻ connection cho nhiều người dùng, xác thực theo từng request thường phù hợp hơn vì từng request có thể đại diện cho một principal khác nhau. Có tình huống cần cả hai lớp xác thực.

Connection registry nên liên kết requester với danh tính đã được xác thực và chính sách của hệ thống. Use case vẫn phải kiểm tra quyền thực hiện hành động trên tài nguyên cụ thể; việc connection đã được xác thực không đồng nghĩa mọi request đều được phép.

## 9. Kiểm thử theo ranh giới

Việc tách lớp giúp kiểm thử từng trách nhiệm mà không cần dựng cả hệ thống RSocket cho mọi trường hợp:

1. **Unit test use case:** truyền command trực tiếp, dùng fake/mock repository và outbound port; kiểm tra quy tắc nghiệp vụ, kết quả, lỗi và các side effect. Test này không cần `RSocketRequester`, route hay server socket.
2. **Test inbound adapter:** gọi handler với DTO mẫu và use case giả; kiểm tra ánh xạ DTO thành command, validation đầu vào và cách chuyển kết quả/lỗi.
3. **Test connection adapter:** kiểm tra SETUP/`@ConnectMapping`, đăng ký requester, xử lý client trùng ID, cleanup khi `onClose` kết thúc và trường hợp connection cũ đóng sau khi connection mới đã được đăng ký.
4. **Integration test RSocket:** khởi động server/client bằng transport cục bộ hoặc TCP test; xác minh route, codec, metadata, interaction model, security và luồng request thực tế.

Không cần dùng integration test để kiểm tra lại mọi nhánh tính toán nghiệp vụ nếu unit test của use case đã bao phủ. Integration test tập trung vào những rủi ro nằm ở ranh giới transport và cấu hình.

## 10. Lỗi thiết kế thường gặp

- **Đặt nghiệp vụ trong `@ConnectMapping`:** một client kết nối không nhất thiết đồng nghĩa một nghiệp vụ cần được thực hiện. Hãy để connection handler quản lý lifecycle; lệnh nghiệp vụ đi qua request handler.
- **Truyền `RSocketRequester` vào domain service:** làm domain phụ thuộc Spring Messaging và khiến test cần mock transport. Hãy định nghĩa outbound port theo nhu cầu nghiệp vụ.
- **Dùng connection ID làm user ID:** một người dùng có thể có nhiều kết nối, và connection có thể thay đổi khi reconnect. Tách định danh người dùng đã xác thực khỏi định danh connection.
- **Lưu trạng thái nghiệp vụ trong registry kết nối:** registry có thể mất khi server restart hoặc connection đóng. Lưu trạng thái cần tồn tại lâu dài qua repository.
- **Xóa registry chỉ theo client ID:** một connection cũ có thể đóng sau khi connection mới đã đăng ký. Xóa có điều kiện theo đúng instance hoặc connection ID.
- **Chặn thread bằng `block()`:** giữ luồng reactive và trả `Mono`/`Flux` để Spring quản lý subscription. Tránh chặn event-loop.
- **Gọi `subscribe()` trong use case:** caller không còn kiểm soát được vòng đời, lỗi và cancellation. Chỉ adapter sở hữu lifecycle mới nên tự subscribe cho một signal hạ tầng như connection close.
- **Coi `send()` là xác nhận nghiệp vụ:** nếu cần biết phía nhận đã xử lý, hãy dùng response/acknowledgement ở tầng giao thức và mô hình hóa kết quả đó.
- **Tin metadata SETUP là danh tính đã xác thực:** phải kiểm tra authentication và authorization trước khi gắn requester với người dùng hoặc cho phép hành động.

## 11. Quy tắc áp dụng nhanh

- Nếu câu hỏi là “nghiệp vụ này có hợp lệ không?”, đặt quy tắc trong domain/application.
- Nếu câu hỏi là “route nào nhận message và payload giải mã ra sao?”, đặt ở RSocket inbound adapter.
- Nếu câu hỏi là “client nào vừa kết nối, connection nào đã đóng?”, đặt ở connection adapter/registry.
- Nếu câu hỏi là “gửi thông báo tới client đang online bằng cách nào?”, định nghĩa outbound port và triển khai nó bằng RSocket adapter.
- Nếu dữ liệu phải tồn tại sau khi client disconnect hoặc server restart, lưu nó ngoài connection registry.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): requester, annotated responders, `@MessageMapping`, `@ConnectMapping`, interaction model và metadata.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): API requester, `rsocketClient()` và `dispose()`.
- [RSocket Java Javadoc — Closeable](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/Closeable.html): tín hiệu `onClose()` của tài nguyên RSocket.
- [Spring Security Reference — RSocket](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): xác thực tại SETUP so với từng request.
- [Spring Blog — Getting Started With RSocket: Servers Calling Clients](https://spring.io/blog/2020/05/12/getting-started-with-rsocket-servers-calling-clients/): ví dụ quản lý client kết nối và dọn registry khi connection đóng.
