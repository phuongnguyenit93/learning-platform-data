# Test UNAVAILABLE khi server dừng

Trong gRPC, **UNAVAILABLE** cho biết RPC không thể được thực hiện tại thời điểm hiện tại, thường do server không nhận kết nối, transport bị đóng hoặc service tạm thời không phục vụ. Với Spring gRPC, kiểm thử tình huống server dừng cần xác minh client nhận đúng status, channel vẫn được quản lý đúng vòng đời và ứng dụng phân biệt lỗi kết nối với lỗi nghiệp vụ.

Server dừng không đồng nghĩa ManagedChannel của client phải bị đóng. Channel là tài nguyên dài hạn, có thể thử kết nối lại khi endpoint hoạt động trở lại. Vì vậy, test cần giữ channel mở, dừng server, rồi gửi một RPC mới qua chính channel đó. Không đóng channel trước khi gọi, vì khi đó test chỉ xác minh client đã tự shutdown.

## 1. Khi nào client nhận UNAVAILABLE?

UNAVAILABLE thường xuất hiện khi:

- Client không thể thiết lập kết nối tới địa chỉ server.
- Server đã dừng và không còn listener nhận kết nối mới.
- Kết nối HTTP/2 bị đóng hoặc reset trong lúc call đang chạy.
- Load balancer không còn backend đủ điều kiện.
- Một service tạm thời từ chối phục vụ theo chính sách availability.

Status này không chỉ có một nguyên nhân. Nếu server chủ động trả UNAVAILABLE từ service handler, client cũng nhận cùng status. Khi chẩn đoán cần kết hợp status code với cause, channel state, server log và telemetry; không phụ thuộc vào chuỗi error message cụ thể của Netty.

Phân biệt với các status gần nghĩa:

| Status | Ý nghĩa thường gặp | Cách phân biệt |
| --- | --- | --- |
| UNAVAILABLE | Không thể kết nối hoặc service tạm không sẵn sàng | Kiểm tra server/transport/backend |
| DEADLINE_EXCEEDED | Deadline của RPC đã hết | Xác minh ngân sách thời gian và thời gian xử lý |
| CANCELLED | Caller hoặc call cha đã hủy RPC | Kiểm tra cancellation từ phía gọi |
| NOT_FOUND | Service xử lý được request nhưng resource không tồn tại | Lỗi nghiệp vụ/resource |
| UNAUTHENTICATED | Credential không được xác minh | Kiểm tra token/certificate |

## 2. Hợp đồng RPC dùng trong ví dụ

Giả sử client đọc tồn kho từ InventoryService:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_multiple_files = true;
option java_package = "com.acme.inventory.v1";

service InventoryService {
  rpc GetStock(GetStockRequest) returns (GetStockResponse);
}

message GetStockRequest {
  string sku = 1;
}

message GetStockResponse {
  string sku = 1;
  int32 available_quantity = 2;
}
~~~

Server test trả về tồn kho cho request hợp lệ:

~~~java
import io.grpc.stub.StreamObserver;

public final class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    @Override
    public void getStock(
            GetStockRequest request,
            StreamObserver<GetStockResponse> responseObserver) {

        responseObserver.onNext(GetStockResponse.newBuilder()
            .setSku(request.getSku())
            .setAvailableQuantity(12)
            .build());
        responseObserver.onCompleted();
    }
}
~~~

Service này chỉ nhằm tạo một endpoint có thể gọi thành công trước khi server dừng. Trong ứng dụng Spring, service được đăng ký theo cơ chế của Spring gRPC starter; server lifecycle do starter quản lý.

## 3. Dừng server graceful và forced shutdown

gRPC Java cung cấp hai cách dừng server:

- server.shutdown() ngừng nhận RPC mới và cho các RPC đang chạy có cơ hội hoàn tất. Đây là lựa chọn ưu tiên khi deploy hoặc scale down.
- server.shutdownNow() yêu cầu dừng ngay và hủy các RPC còn hoạt động. Dùng khi hết grace period hoặc cần kết thúc cưỡng bức.

Trình tự graceful shutdown điển hình:

~~~java
server.shutdown();
if (!server.awaitTermination(10, TimeUnit.SECONDS)) {
    server.shutdownNow();
    server.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

Sau shutdown(), server không nhận call mới. Các call đã được nhận trước thời điểm shutdown có thể hoàn tất. Với shutdownNow(), call đang chạy có thể bị cancel hoặc kết thúc do transport đóng; status quan sát ở client phụ thuộc thời điểm và trạng thái call.

Không nên viết test yêu cầu mọi RPC đang chạy phải nhận UNAVAILABLE khi server dừng. Một RPC đã được server nhận có thể hoàn tất thành công trong graceful shutdown. Để kiểm tra UNAVAILABLE ổn định, hãy đợi server đã terminate rồi mới gửi RPC mới.

## 4. Test transport thực với Netty và cổng động

In-process transport phù hợp cho test logic handler, nhưng không mô phỏng đầy đủ socket, HTTP/2 connection và listener bị đóng. Để kiểm tra server dừng, dùng Netty loopback server với port 0; hệ điều hành cấp cổng khả dụng và test đọc cổng thực qua server.getPort().

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class InventoryServerUnavailableTest {

    private Server server;
    private ManagedChannel channel;
    private InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        server = NettyServerBuilder.forPort(0)
            .addService(new InventoryGrpcService())
            .build()
            .start();

        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", server.getPort())
            .usePlaintext()
            .build();

        stub = InventoryServiceGrpc.newBlockingStub(channel);

        // Warm up để chắc chắn channel đã thực hiện được RPC tới server.
        GetStockResponse response = stub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getStock(GetStockRequest.newBuilder()
                .setSku("SKU-42")
                .build());
        assertEquals("SKU-42", response.getSku());
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null && !server.isShutdown()) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void newCallAfterServerTerminatesReturnsUnavailable()
            throws InterruptedException {
        server.shutdown();
        assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));

        GetStockRequest request = GetStockRequest.newBuilder()
            .setSku("SKU-42")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                .getStock(request));

        assertEquals(
            Status.Code.UNAVAILABLE,
            error.getStatus().getCode());
    }
}
~~~

Test thực hiện RPC thành công để xác nhận channel đã kết nối, sau đó graceful shutdown server và chờ server terminate. RPC mới được gửi qua channel cũ, channel vẫn còn mở. Vì server không còn nhận kết nối, client quan sát UNAVAILABLE.

usePlaintext() chỉ phù hợp cho loopback test này. Integration test production-like cần cấu hình TLS, trust chain và hostname tương ứng. Nếu dự án dùng grpc-netty-shaded, import Netty builder từ package shaded thay vì trộn class unshaded và shaded.

## 5. Vì sao cần warm up channel trước khi dừng server?

ManagedChannel có thể kết nối lazy. Nếu dừng server ngay sau khi tạo channel, test chưa chứng minh một kết nối đang hoạt động đã bị ảnh hưởng; nó chỉ kiểm tra client không thể kết nối lần đầu.

Warm-up RPC giúp xác nhận:

1. Server thực sự đã start và đăng ký service.
2. Client target đúng port do server cấp.
3. Channel có thể gửi/nhận một RPC trước khi shutdown.
4. Lỗi ở RPC tiếp theo xảy ra sau khi server đã terminate.

Không dùng Thread.sleep() để đoán channel đã READY. Một RPC warm-up thành công là đồng bộ hóa trực tiếp với khả năng phục vụ thực tế và ổn định hơn.

## 6. Không bật wait-for-ready trong test cần UNAVAILABLE

Mặc định, call không bật wait-for-ready sẽ thất bại khi channel không thể chọn transport sẵn sàng, thường với UNAVAILABLE. Nếu bật withWaitForReady(), gRPC có thể xếp call chờ cho tới khi channel phục hồi hoặc deadline hết.

Ví dụ:

~~~java
var waitingStub = stub.withWaitForReady()
    .withDeadlineAfter(500, TimeUnit.MILLISECONDS);
~~~

Khi server đã dừng và không có backend thay thế, call wait-for-ready có thể kết thúc bằng DEADLINE_EXCEEDED thay vì UNAVAILABLE, vì client đã chờ hết ngân sách. Do đó, test khẳng định status UNAVAILABLE cần dùng stub không bật wait-for-ready và vẫn đặt deadline hữu hạn để test không treo.

## 7. Phân biệt server shutdown với channel shutdown

Server và client channel là hai lifecycle độc lập:

| Hành động | Ảnh hưởng |
| --- | --- |
| server.shutdown() | Server ngừng nhận call mới, call đang chạy được phép hoàn tất |
| server.shutdownNow() | Server yêu cầu hủy call đang chạy và dừng nhanh |
| channel.shutdown() | Client ngừng tạo call mới qua channel và giải phóng transport sau khi call hiện tại kết thúc |
| channel.shutdownNow() | Client hủy call còn hoạt động và đóng channel nhanh |

Nếu test gọi channel.shutdownNow() trước RPC rồi assert UNAVAILABLE, test không còn kiểm tra server dừng. Hãy giữ channel mở đến khi hoàn tất assertion, sau đó mới shutdown channel trong @AfterEach.

Không tạo channel mới cho từng RPC để né lỗi kết nối. ManagedChannel được thiết kế để tái sử dụng, quản lý reconnect và load balancing trong suốt vòng đời client.

## 8. Hành vi khi có RPC đang chạy

Khi server graceful shutdown, RPC đã được nhận có thể hoàn tất. Khi forced shutdown hoặc kết nối bị mất đột ngột, client có thể thấy UNAVAILABLE, CANCELLED hoặc status khác tùy thời điểm response và transport đóng.

Đối với test in-flight:

- Dùng latch để biết handler đã bắt đầu.
- Gọi server.shutdown() và xác minh handler hiện tại được phép hoàn tất.
- Với server.shutdownNow(), xác minh cancellation signal được nhận và tài nguyên được giải phóng.
- Không gắn một status cố định cho mọi race giữa response, deadline và connection close.

Test mục tiêu “server đã dừng, RPC mới không thể kết nối” nên tách khỏi test “RPC đang chạy bị gián đoạn”. Hai tình huống có lifecycle và kỳ vọng khác nhau.

## 9. Retry UNAVAILABLE có điều kiện

UNAVAILABLE có thể tạm thời và phù hợp với retry trong một số trường hợp, nhưng không phải mọi RPC đều an toàn để gửi lại:

- RPC đọc idempotent thường có thể retry với backoff và deadline tổng.
- RPC ghi cần idempotency key hoặc semantics chống tạo trùng.
- Nếu server đã commit nhưng response bị mất khi server dừng, client không thể suy ra thao tác chưa xảy ra.
- Retry phải giới hạn số attempt, dùng exponential backoff có jitter và tôn trọng deadline của logical operation.
- Không retry dồn dập khi toàn bộ backend đang down; circuit breaker hoặc retry throttling giúp tránh khuếch đại sự cố.

Nếu server restart tại cùng endpoint, ManagedChannel có thể tự kết nối lại khi resolver/transport phát hiện backend mới. Không cần tạo channel mới cho mỗi lần retry; hãy giữ channel sống và để gRPC quản lý reconnect theo policy.

## 10. Spring gRPC và quản lý lifecycle

Trong ứng dụng Spring, server thường do starter quản lý. Không tự gọi shutdownNow() từ một service bean hoặc endpoint nghiệp vụ. Khi application context đóng, integration của starter nên dừng server theo lifecycle đã cấu hình.

Với client channel:

- Đăng ký channel hoặc client stub qua bean/lifecycle của starter.
- Tái sử dụng channel cho nhiều RPC.
- Khi ứng dụng shutdown, ngừng nhận công việc mới rồi đóng channel.
- Dùng deadline cho RPC để call không treo vô hạn trong lúc downstream mất kết nối.
- Nếu tự tạo ManagedChannel bean, khai báo destroy method hoặc lifecycle hook để đóng channel đúng cách.

Ví dụ bean tự quản lý channel:

~~~java
@Configuration
public class InventoryClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel() {
        return ManagedChannelBuilder
            .forAddress("inventory.internal", 9090)
            .useTransportSecurity()
            .build();
    }

    @Bean
    InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub(
            ManagedChannel inventoryChannel) {
        return InventoryServiceGrpc.newBlockingStub(inventoryChannel);
    }
}
~~~

Đây là ví dụ quản lý channel trực tiếp. Nếu starter đã cung cấp channel, hãy dùng channel đó thay vì tạo thêm một channel tới cùng target. Không dùng plaintext trong production.

## 11. Quan sát channel và chẩn đoán UNAVAILABLE

Khi client nhận UNAVAILABLE, cần xác định lỗi ở tầng nào:

1. **DNS/resolver:** target có resolve ra địa chỉ backend đúng không?
2. **TCP/port:** server có listen trên địa chỉ và port đó không?
3. **HTTP/2/TLS:** handshake, certificate, ALPN và proxy có hoạt động không?
4. **Server lifecycle:** instance có đang shutdown, restart hoặc bị drain không?
5. **Load balancer:** còn backend SERVING hay tất cả backend đã bị loại?
6. **Application:** service có chủ động trả UNAVAILABLE do dependency không?

Có thể quan sát channel state như IDLE, CONNECTING, READY, TRANSIENT_FAILURE và SHUTDOWN. State chỉ là tín hiệu chẩn đoán tại một thời điểm, không thay thế status của RPC. Ghi log target, method, status code, elapsed time, deadline remaining và request ID; không ghi credential hoặc payload nhạy cảm.

## 12. Ma trận kiểm thử đề xuất

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Server hoạt động, warm-up RPC | Thành công |
| Server graceful shutdown hoàn tất, channel còn mở | RPC mới trả UNAVAILABLE |
| Server shutdownNow trong khi RPC đang chạy | Cancellation/transport status theo timing; server dừng tác vụ |
| Channel bị shutdown trước khi gọi | Test phải nhận diện đây là client shutdown, không phải server outage |
| Wait-for-ready bật, không có backend | Call chờ đến khi phục hồi hoặc hết deadline |
| Server restart tại cùng target | Channel có thể reconnect; RPC mới thành công sau khi backend ready |
| Nhiều backend, một backend dừng | LB chuyển call sang backend còn healthy nếu policy hỗ trợ |
| RPC ghi timeout sau commit | Idempotency/operation lookup tránh tạo dữ liệu trùng |

Test transport shutdown nên chạy qua Netty loopback hoặc môi trường tương đương. In-process test vẫn hữu ích cho status mapping và service logic, nhưng không thay thế kiểm thử socket, HTTP/2, TLS, DNS hoặc load balancer.

## 13. Ghi nhớ và tự kiểm tra

**Test UNAVAILABLE khi server dừng** cần giữ ManagedChannel mở, warm-up một RPC thành công, dừng server và gửi một RPC mới sau khi server đã terminate. Dùng Netty loopback với port động để kiểm tra transport thực; không bật wait-for-ready nếu mục tiêu là quan sát UNAVAILABLE ngay khi backend không còn. Phân biệt graceful shutdown với forced shutdown, xử lý RPC đang chạy theo timing và chỉ retry khi thao tác an toàn.

Tự kiểm tra:

1. Vì sao phải giữ channel mở sau khi server dừng?
2. server.shutdown() khác server.shutdownNow() như thế nào?
3. Vì sao warm-up RPC đáng tin cậy hơn Thread.sleep()?
4. wait-for-ready có thể làm thay đổi status cuối cùng ra sao?
5. Vì sao không thể kết luận transaction chưa commit chỉ từ UNAVAILABLE?
6. Khi server restart cùng endpoint, vai trò của ManagedChannel là gì?

Kiểm thử đúng tình huống server dừng giúp client Spring gRPC nhận diện lỗi availability, giữ lifecycle channel ổn định và phục hồi có kiểm soát khi backend hoạt động trở lại.
