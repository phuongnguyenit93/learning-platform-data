# @ConnectMapping và xử lý dữ liệu thiết lập kết nối

## 1. Vị trí của SETUP trong vòng đời RSocket

RSocket bắt đầu bằng việc thiết lập một kết nối qua transport như TCP hoặc WebSocket. Khi transport đã sẵn sàng, requester gửi frame **SETUP** để hai phía thống nhất các thông tin cấp kết nối. Frame này có thể chứa data, metadata, MIME type và các tham số giao thức. Data và metadata trong SETUP là tùy chọn.

Sau khi responder chấp nhận SETUP, hai phía mới bắt đầu trao đổi các request thông thường như Request-Response, Request-Stream, Channel hoặc Fire-and-Forget. Vì vậy, dữ liệu trong SETUP có ý nghĩa ở cấp kết nối, còn payload gửi bằng một request sau đó thuộc về request riêng lẻ.

Spring cung cấp **RSocketRequester.Builder** để khai báo dữ liệu ban đầu:

| API | Vai trò |
|---|---|
| setupData(Object) | Data gửi trong frame SETUP |
| setupRoute(String, Object...) | Route metadata của frame SETUP |
| setupMetadata(Object, MimeType) | Metadata bổ sung trong SETUP |
| dataMimeType(MimeType) | MIME type cho data trên kết nối |
| metadataMimeType(MimeType) | MIME type cho metadata trên kết nối |

Ví dụ, client có thể gửi route nhận diện loại kết nối và mã thiết bị ngay khi thiết lập:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("device.connect")
    .setupData("device-001")
    .tcp("localhost", 7000);
~~~

Trong ví dụ này, device-001 là data của SETUP; device.connect là route nằm trong metadata của SETUP. Chúng không phải dữ liệu và route của một request thông thường.

Việc gọi tcp(...) tạo requester và cấu hình transport. Kết nối thực tế có thể được thiết lập trễ khi requester bắt đầu sử dụng kết nối. Khi kết nối được mở, SETUP data và metadata đã cấu hình sẽ được gửi trong quá trình handshake.

## 2. @ConnectMapping là gì?

**org.springframework.messaging.rsocket.annotation.ConnectMapping** là annotation để ánh xạ các sự kiện ở cấp kết nối vào một phương thức xử lý. Annotation này xử lý hai loại frame:

- **SETUP:** frame đầu tiên khi một kết nối RSocket mới được thiết lập.
- **METADATA_PUSH:** thông báo metadata được gửi sau đó, không gắn với một request cụ thể.

Đây là method-level annotation. Các phương thức @ConnectMapping nhận những loại tham số tương tự @MessageMapping, nhưng dữ liệu được lấy từ SETUP hoặc METADATA_PUSH. Những tham số thường gặp gồm:

- **@Payload:** data của frame, ví dụ chuỗi định danh client hoặc DTO cấu hình kết nối.
- **RSocketRequester:** requester đại diện cho kết nối hiện tại, dùng để gửi request về phía bên kia.
- **@DestinationVariable:** biến được trích xuất từ route nếu route pattern có biến.
- **@Header** và **@Headers:** metadata đã được MetadataExtractor giải mã và đưa vào message headers.

@ConnectMapping có thể khai báo route pattern. Ví dụ, @ConnectMapping("device.connect") chỉ nhận các sự kiện có route metadata phù hợp. Nếu không khai báo pattern, phương thức khớp với mọi kết nối và metadata push.

Khác với @MessageMapping, phương thức @ConnectMapping **không được trả dữ liệu phản hồi**. Kiểu trả về phải là void hoặc Mono<Void>. Ở phía server, nếu dùng Mono<Void>, kết nối được chấp nhận khi publisher hoàn tất thành công; nếu xử lý trả lỗi thì kết nối mới sẽ bị từ chối. Ở phía client, phương thức chỉ đóng vai trò callback và không quyết định việc thiết lập kết nối.

## 3. Đọc setupData bằng @Payload

Client đã gửi route device.connect và data dạng String ở ví dụ trước. Phía server có thể nhận data đó như sau:

~~~java
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Mono;

@Controller
public class DeviceConnectionController {

    private final ConcurrentMap<String, Instant> connectedDevices =
        new ConcurrentHashMap<>();

    @ConnectMapping("device.connect")
    public Mono<Void> onConnect(@Payload String deviceId) {
        if (deviceId == null || deviceId.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("deviceId is required")
            );
        }

        return Mono.fromRunnable(
            () -> connectedDevices.put(deviceId, Instant.now())
        );
    }
}
~~~

Khi client gửi SETUP có route device.connect, Spring tìm phương thức @ConnectMapping khớp route và giải mã data thành String để truyền vào tham số deviceId. Phương thức kiểm tra dữ liệu rồi ghi nhận thời điểm kết nối. Mono.fromRunnable thực hiện thao tác khi được subscribe và hoàn tất mà không tạo response payload.

Đây là ví dụ minh họa phần xử lý. Ứng dụng thực tế cần xác định cách quản lý vòng đời kết nối, xử lý client trùng định danh và xóa trạng thái khi kết nối đóng. Không nên dùng riêng deviceId làm định danh duy nhất cho một kết nối nếu cùng một thiết bị có thể mở nhiều kết nối đồng thời.

Các bean có @ConnectMapping cần được phát hiện bởi **RSocketMessageHandler** và đăng ký làm responder. Trong Spring Boot, cấu hình RSocket server phù hợp sẽ tích hợp handler qua auto-configuration. Với cấu hình Spring thuần, cần tạo RSocketMessageHandler và gắn responder của nó vào RSocket server.

## 4. Gửi DTO thay vì chuỗi đơn giản

Data trong SETUP không giới hạn ở String. Client có thể gửi một DTO chứa nhiều thông tin:

~~~java
public record DeviceSetup(
    String deviceId,
    String applicationVersion,
    String platform
) {}
~~~

Client cấu hình:

~~~java
DeviceSetup setup = new DeviceSetup(
    "device-001",
    "2.4.0",
    "desktop"
);

RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("device.connect")
    .setupData(setup)
    .tcp("localhost", 7000);
~~~

Server nhận cùng cấu trúc:

~~~java
@ConnectMapping("device.connect")
Mono<Void> onConnect(@Payload DeviceSetup setup) {
    if (setup.deviceId() == null || setup.deviceId().isBlank()) {
        return Mono.error(new IllegalArgumentException("deviceId is required"));
    }

    return connectionService.register(setup);
}
~~~

Đoạn handler trên giả định ứng dụng đã có connectionService.register(DeviceSetup) trả về Mono<Void>. Khi sử dụng DTO, hai phía phải có encoder và decoder tương thích với MIME type đã khai báo. Codec mặc định của Spring Core chỉ hỗ trợ các kiểu cơ bản như String, byte[] và ByteBuffer. Để truyền object, có thể bổ sung codec JSON hoặc CBOR từ spring-web, ví dụ Jackson2JsonEncoder/Jackson2JsonDecoder hoặc JacksonCborEncoder/JacksonCborDecoder, rồi cấu hình chúng trong RSocketStrategies ở client và server.

Ví dụ cấu hình chiến lược với CBOR:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
    .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
    .build();
~~~

Client truyền strategies vào builder bằng rsocketStrategies(strategies). Server cũng phải dùng cấu hình tương thích thông qua RSocketMessageHandler. Nếu MIME type hoặc codec không khớp, payload có thể không giải mã được thành DTO mong muốn.

## 5. Phân biệt data và metadata trong SETUP

RSocket phân biệt data và metadata. Data thường chứa nội dung nghiệp vụ như mã thiết bị, phiên bản ứng dụng hoặc thông tin cấu hình. Metadata có thể chứa route, thông tin bảo mật hoặc dữ liệu điều khiển cấp kết nối.

- **setupData(...)** đưa object vào phần data của SETUP.
- **setupRoute(...)** thêm route metadata để responder có thể chọn handler.
- **setupMetadata(...)** thêm metadata theo MIME type cụ thể.
- **dataMimeType(...)** và **metadataMimeType(...)** khai báo cách diễn giải nội dung tương ứng.

Route trong SETUP có thể dùng để phân loại kết nối, ví dụ device.connect, admin.connect hoặc monitoring.connect. Nó không thay thế route của các request sau này. Một request thông thường vẫn chọn route riêng bằng requester.route("...").

Với metadata tùy chỉnh, phía nhận cần cấu hình giải mã. **MetadataExtractor** chuyển metadata đã mã hóa thành các giá trị có tên để handler truy cập như message headers. DefaultMetadataExtractor có hỗ trợ sẵn routing metadata; với MIME type khác, cần đăng ký decoder và ánh xạ kiểu dữ liệu vào một tên header.

Ví dụ đăng ký metadata tùy chỉnh trong RSocketStrategies:

~~~java
MimeType clientMetadataMimeType =
    MimeType.valueOf("application/vnd.example.client-metadata");

RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
    .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
    .metadataExtractorRegistry(registry ->
        registry.metadataToExtract(
            clientMetadataMimeType,
            ClientMetadata.class,
            "clientMetadata"
        )
    )
    .build();
~~~

Sau khi encoder, decoder và MetadataExtractor được cấu hình tương ứng, client có thể gọi setupMetadata(value, clientMetadataMimeType). Handler có thể nhận giá trị đã giải mã qua @Header("clientMetadata") ClientMetadata metadata. Kiểu ClientMetadata là DTO do ứng dụng định nghĩa.

Không phải mọi metadata đều tự động trở thành header. Nếu MIME type chưa được hỗ trợ hoặc chưa đăng ký decoder và mapping phù hợp, @Header sẽ không nhận được giá trị như mong đợi.

## 6. Lọc kết nối bằng route pattern

Nếu ứng dụng có nhiều nhóm client, route của SETUP có thể giúp chọn handler phù hợp:

~~~java
@Controller
public class TenantConnectionController {

    @ConnectMapping("tenant.{tenantId}.connect")
    Mono<Void> onConnect(
        @DestinationVariable("tenantId") String tenantId,
        @Payload String clientId
    ) {
        return connectionService.register(tenantId, clientId);
    }
}
~~~

Client cần gửi route khớp với pattern, ví dụ tenant.acme.connect. Spring trích xuất acme và truyền vào tenantId. Route pattern được so khớp theo RouteMatcher đang cấu hình trong RSocketMessageHandler; khi có spring-web, có thể sử dụng PathPatternRouteMatcher.

Nếu không cần phân loại theo route, có thể dùng @ConnectMapping không có giá trị. Tuy nhiên, handler mặc định khi đó nhận mọi SETUP và metadata push. Trong ứng dụng có nhiều loại kết nối, khai báo route cụ thể giúp tránh một handler xử lý nhầm các nhóm client khác nhau.

## 7. Dùng RSocketRequester trong handler

Một phương thức @ConnectMapping có thể nhận tham số RSocketRequester. Đây là requester gắn với kết nối hiện tại, cho phép server gửi request ngược về client. Điều này hữu ích trong mô hình hai phía đều có thể khởi tạo request.

Cần lưu ý rằng @ConnectMapping xử lý SETUP và SETUP phải hoàn tất trước khi các request thông thường bắt đầu. Vì thế, không được giữ quá trình xử lý SETUP chờ một request mới gửi qua chính RSocketRequester của kết nối đó. Nếu cần chủ động gửi request về client ngay khi kết nối mở, hãy khởi chạy công việc đó độc lập với luồng xử lý SETUP, chẳng hạn chuyển sang scheduler khác và subscribe riêng. Phần xử lý SETUP vẫn phải trả về void hoặc Mono<Void> để kết nối được chấp nhận.

Không dùng block() trong handler reactive. Với công việc truy cập cơ sở dữ liệu hoặc dịch vụ khác, ưu tiên API reactive và giới hạn thời gian xử lý. Nếu handler hoàn tất quá chậm, quá trình thiết lập kết nối cũng bị trì hoãn.

## 8. @ConnectMapping và @MessageMapping khác nhau thế nào?

| Tiêu chí | @ConnectMapping | @MessageMapping |
|---|---|---|
| Thời điểm | Khi nhận SETUP hoặc METADATA_PUSH | Khi nhận request riêng lẻ |
| Phạm vi | Cấp kết nối | Cấp request |
| Route | Route trong metadata của SETUP hoặc metadata push | Route của request |
| Payload | Data của SETUP; metadata push chủ yếu mang metadata | Data của request |
| Kiểu trả về | void hoặc Mono<Void> | Có thể trả object, Mono, Flux, void hoặc Mono<Void> |
| Mục đích | Khởi tạo, kiểm tra, ghi nhận hoặc cập nhật trạng thái kết nối | Xử lý nghiệp vụ và trả kết quả cho request |

Ví dụ: client gửi device.connect cùng deviceId trong SETUP. @ConnectMapping nhận và kiểm tra deviceId một lần khi kết nối được thiết lập. Sau đó client gửi request route device.status; request này được xử lý bởi một phương thức @MessageMapping tương ứng. Hai phương thức phục vụ hai giai đoạn khác nhau.

## 9. Kiểm tra dữ liệu, bảo mật và lỗi thường gặp

Dữ liệu do client gửi trong SETUP vẫn là dữ liệu đầu vào không đáng tin cậy. Không nên coi tenantId, userId hoặc role do client tự khai báo là danh tính đã được xác thực. Nếu metadata mang token hoặc thông tin xác thực, server phải xác minh bằng cơ chế bảo mật phù hợp, chẳng hạn Spring Security RSocket, trước khi cấp quyền. Không ghi token hoặc thông tin bí mật vào log.

Một số lỗi phổ biến:

- **Handler không được gọi:** kiểm tra controller có được phát hiện và RSocketMessageHandler đã được đăng ký làm responder hay chưa.
- **Route không khớp:** đối chiếu setupRoute(...) của client với giá trị/pattern trong @ConnectMapping.
- **Handler nhận payload rỗng:** kiểm tra client có gọi setupData(...) hay không và đúng data của SETUP đang được gửi.
- **Không giải mã được DTO:** kiểm tra encoder, decoder và MIME type ở cả hai phía; String hoạt động không có nghĩa DTO cũng tự giải mã được.
- **Không đọc được metadata tùy chỉnh:** kiểm tra composite metadata, MIME type, decoder và MetadataExtractor registration.
- **Kết nối bị từ chối:** kiểm tra lỗi phát sinh từ handler. Với server, lỗi trong Mono<Void> của @ConnectMapping làm SETUP thất bại.
- **Kết nối bị treo:** tránh block(), thao tác đồng bộ kéo dài và việc chờ request mới qua RSocketRequester ngay trong quá trình xử lý SETUP.
- **Handler chạy nhiều lần:** ngoài SETUP ban đầu, @ConnectMapping còn xử lý METADATA_PUSH. Không giả định mọi lần gọi đều là một kết nối mới.

Khi kiểm thử, nên dùng RSocket client và server thật để xác nhận route, payload, metadata và kết quả chấp nhận/từ chối kết nối. Kiểm tra riêng trường hợp thiếu setupData, sai route, sai MIME type và handler trả lỗi. Nếu có metadata push, kiểm tra rằng logic phân biệt sự kiện thiết lập kết nối với thông báo metadata sau khi kết nối đã mở.

## 10. Ghi nhớ

@ConnectMapping là điểm tiếp nhận sự kiện cấp kết nối của RSocket trong Spring. Client khai báo dữ liệu ban đầu bằng setupData(...), route bằng setupRoute(...) và metadata tùy chỉnh bằng setupMetadata(...). Server dùng @ConnectMapping để đọc data qua @Payload, lấy metadata đã giải mã qua header và thực hiện kiểm tra hoặc khởi tạo trạng thái kết nối.

Phương thức chỉ trả void hoặc Mono<Void>; server chấp nhận kết nối khi xử lý hoàn tất thành công và từ chối khi xử lý lỗi. Sau khi kết nối mở, các request nghiệp vụ tiếp tục đi qua @MessageMapping. Hãy giữ rõ ranh giới giữa dữ liệu SETUP và payload của từng request, cấu hình codec/metadata extractor tương thích, đồng thời xác thực mọi dữ liệu do client cung cấp.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [ConnectMapping Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
