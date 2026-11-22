# Method không có payload bằng Empty

Một số RPC chỉ cần client yêu cầu server thực hiện một hành động, hoặc chỉ cần xác nhận rằng thao tác đã hoàn tất. Trong trường hợp đó, request hay response có thể không cần trường dữ liệu nào. **Protocol Buffers** cung cấp kiểu chuẩn **google.protobuf.Empty** cho message rỗng.

**Empty** vẫn là một **message Protobuf**. Dùng nó không có nghĩa bỏ request/response khỏi hợp đồng, bỏ qua lời gọi gRPC hay không có dữ liệu truyền ở tầng transport. Nó biểu thị rằng phía tương ứng không cần payload nghiệp vụ ở dạng field. Đây là cách khai báo rõ ràng cho method không cần dữ liệu đầu vào, không cần dữ liệu đầu ra hoặc không cần cả hai trong **Spring gRPC**.

## 1. Khai báo RPC với google.protobuf.Empty

Để dùng kiểu chuẩn này, import file **google/protobuf/empty.proto**:

~~~proto
syntax = "proto3";

package demo.maintenance.v1;

option java_package = "vn.demo.grpc.maintenance.v1";
option java_multiple_files = true;

import "google/protobuf/empty.proto";

service MaintenanceService {
  // Client không cần gửi dữ liệu nghiệp vụ.
  rpc RefreshCatalog(google.protobuf.Empty)
      returns (RefreshResult);

  // Server chỉ cần xác nhận hoàn tất, không trả payload nghiệp vụ.
  rpc AcknowledgeStartup(StartupSignal)
      returns (google.protobuf.Empty);

  // Cả hai phía đều không cần payload.
  rpc Ping(google.protobuf.Empty)
      returns (google.protobuf.Empty);
}

message RefreshResult {
  int64 refreshed_items = 1;
}

message StartupSignal {
  string instance_id = 1;
}
~~~

Ba method thể hiện ba trường hợp:

| Method | Request | Response | Ý nghĩa |
| --- | --- | --- | --- |
| **RefreshCatalog** | **Empty** | **RefreshResult** | Không cần tham số nghiệp vụ; server trả kết quả có dữ liệu |
| **AcknowledgeStartup** | **StartupSignal** | **Empty** | Client gửi thông tin; server chỉ cần xác nhận thành công |
| **Ping** | **Empty** | **Empty** | Không có payload nghiệp vụ ở cả hai chiều |

Trong một khai báo RPC, Protobuf vẫn yêu cầu kiểu request và response. **google.protobuf.Empty** đáp ứng yêu cầu kiểu message khi không có field nào cần trao đổi. Không nên dùng một chuỗi rỗng, **null** hoặc bỏ hẳn phần kiểu trả về để biểu diễn trường hợp này.

## 2. Empty là message rỗng, không phải không có RPC

**google.protobuf.Empty** là một **well-known type** do Protobuf định nghĩa. Message này không có field. Khi serialize, payload Protobuf của một instance Empty có độ dài **0 byte**.

Tuy nhiên, lời gọi gRPC vẫn có:

- Một RPC với full method name và metadata như các method khác.
- Một HTTP/2 stream để vận chuyển lời gọi.
- Một gRPC message ở chiều request và/hoặc response tương ứng với kiểu Empty.
- Trạng thái kết thúc gRPC, ví dụ **OK** hoặc **INVALID_ARGUMENT**.

Ở tầng gRPC framing, message vẫn có phần header gồm cờ nén và độ dài payload. Với Empty, độ dài payload là 0; điều đó không làm biến mất message hay HTTP/2 stream. Vì vậy, khi quan sát network trace, không nên kết luận rằng method không được gọi chỉ vì không thấy field nghiệp vụ trong payload.

## 3. Triển khai server trong Spring gRPC

Sau khi cấu hình sinh mã từ .proto, Java dùng lớp **com.google.protobuf.Empty**. Ví dụ triển khai Ping và RefreshCatalog:

~~~java
package vn.demo.maintenance;

import com.google.protobuf.Empty;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.maintenance.v1.MaintenanceServiceGrpc;
import vn.demo.grpc.maintenance.v1.RefreshResult;

@Service
public class MaintenanceServiceImpl
        extends MaintenanceServiceGrpc.MaintenanceServiceImplBase {

    @Override
    public void ping(
            Empty request,
            StreamObserver<Empty> responseObserver) {
        // Không có payload cần xử lý.
        responseObserver.onNext(Empty.getDefaultInstance());
        responseObserver.onCompleted();
    }

    @Override
    public void refreshCatalog(
            Empty request,
            StreamObserver<RefreshResult> responseObserver) {
        try {
            long refreshed = catalogRefresher.refresh();

            responseObserver.onNext(RefreshResult.newBuilder()
                .setRefreshedItems(refreshed)
                .build());
            responseObserver.onCompleted();
        } catch (CatalogRefreshException ex) {
            responseObserver.onError(Status.INTERNAL
                .withDescription("catalog refresh failed")
                .withCause(ex)
                .asRuntimeException());
        }
    }
}
~~~

**catalogRefresher** là thành phần nghiệp vụ được inject vào service; phần khai báo dependency được lược bỏ để tập trung vào chữ ký RPC. Khi dùng Empty, server vẫn phải kết thúc observer đúng quy tắc:

- Thành công: phát một response message (nếu response type là Empty, dùng **Empty.getDefaultInstance()**), rồi gọi **onCompleted()**.
- Thất bại: gọi **onError(...)** với gRPC status phù hợp; không phát response thành công sau đó.

Ngay cả khi response là Empty, **không được bỏ onNext()** trong triển khai unary thành công. **onCompleted()** chỉ báo kết thúc luồng phản hồi; nó không thay thế response message theo contract unary.

## 4. Gọi RPC từ Java client

Với blocking stub, lời gọi Ping vẫn nhận về một instance Empty, dù không có field để đọc:

~~~java
import com.google.protobuf.Empty;
import java.util.concurrent.TimeUnit;

Empty response = blockingStub
    .withDeadlineAfter(2, TimeUnit.SECONDS)
    .ping(Empty.getDefaultInstance());

// Không có field nghiệp vụ để đọc từ response.
System.out.println("Ping completed");
~~~

Đối với RefreshCatalog, client cũng gửi Empty nhưng nhận kết quả có dữ liệu:

~~~java
RefreshResult result = blockingStub
    .withDeadlineAfter(10, TimeUnit.SECONDS)
    .refreshCatalog(Empty.getDefaultInstance());

System.out.println("Refreshed: " + result.getRefreshedItems());
~~~

Trong ứng dụng Spring, stub/channel nên được cấu hình và quản lý vòng đời bằng cơ chế tích hợp của phiên bản Spring gRPC đang dùng. **withDeadlineAfter(...)** đặt giới hạn cho lời gọi; việc request không có field không làm mất nhu cầu deadline hoặc xử lý lỗi.

## 5. Khi nào nên dùng Empty?

Dùng google.protobuf.Empty khi phía tương ứng thực sự **không cần dữ liệu nghiệp vụ**:

- **Request rỗng:** client yêu cầu thao tác toàn cục không cần tham số, ví dụ **RefreshCatalog(Empty)**.
- **Response rỗng:** server chỉ cần báo thao tác thành công qua gRPC status, ví dụ **AcknowledgeStartup(StartupSignal) returns (Empty)**.
- **Cả hai rỗng:** thao tác kiểm tra kết nối đơn giản như **Ping(Empty) returns (Empty)**.

Không dùng Empty chỉ để tránh thiết kế schema khi thực tế đã có dữ liệu cần truyền. Ví dụ, RefreshCatalog nếu cần chọn tenant, vùng dữ liệu hoặc chế độ chạy thì nên nhận một request message có các field đó.

### Empty hay message riêng không có field?

Có thể khai báo:

~~~proto
message RefreshCatalogRequest {}

rpc RefreshCatalog(RefreshCatalogRequest)
    returns (RefreshResult);
~~~

Nhưng nếu message không có ý nghĩa riêng và chắc chắn không cần field, **google.protobuf.Empty** là kiểu chuẩn, dễ nhận diện và không phải tạo thêm message chỉ để biểu diễn rỗng.

Ngược lại, nếu dự kiến contract sẽ cần mở rộng với field như **tenant_id**, **force_refresh** hoặc **scope**, cân nhắc tạo **RefreshCatalogRequest** ngay từ đầu. Thay kiểu request của method đã phát hành từ google.protobuf.Empty sang message riêng là thay đổi contract, có thể làm client cũ không tương thích. Không thể thêm field nghiệp vụ vào kiểu chuẩn google.protobuf.Empty.

## 6. Empty không thay thế metadata hoặc status

Message rỗng chỉ nói rằng không có **field payload** ở chiều đó. Nó không có nghĩa lời gọi không cần:

- **Authentication/authorization:** server vẫn phải xác định ai gọi và có quyền thực hiện hành động hay không.
- **Metadata:** request ID, tenant context hoặc trace context vẫn có thể được truyền ở metadata của RPC theo chính sách hệ thống.
- **Deadline/cancellation:** thao tác không có payload vẫn có thể chạy lâu, bị hủy hoặc vượt thời gian.
- **gRPC status:** client dựa vào **OK**, **UNAUTHENTICATED**, **PERMISSION_DENIED**, **DEADLINE_EXCEEDED**, **INTERNAL**... để biết kết quả lời gọi.

Ví dụ, **RefreshCatalog(Empty)** có thể yêu cầu quyền quản trị. Nếu caller không có quyền, server trả **PERMISSION_DENIED**; không gửi Empty như thể thao tác thành công.

## 7. Kiểm thử method dùng Empty

Kiểm thử cần xác nhận cả hai điều: client gửi đúng Empty và server trả đúng response/status. Ví dụ với gRPC in-process:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.google.protobuf.Empty;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.maintenance.v1.MaintenanceServiceGrpc;

class MaintenanceServiceTest {

    @Test
    void pingAcceptsAndReturnsEmptyMessage() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new MaintenanceServiceImpl())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(serverName)
            .directExecutor()
            .build();

        try {
            var stub = MaintenanceServiceGrpc.newBlockingStub(channel);
            Empty response = stub.ping(Empty.getDefaultInstance());
            assertNotNull(response);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Test này cần JUnit và dependency **gRPC in-process** tương thích với phiên bản gRPC Java của dự án. Để xác nhận Spring tự đăng ký bean service, interceptor và security policy, bổ sung integration test khởi động Spring context theo cấu hình test. Với method có tác dụng phụ như refresh dữ liệu, cần kiểm thử quyền truy cập, deadline, status lỗi và việc thao tác có thực sự hoàn tất.

## 8. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ Empty nghĩa là không có request/response | Hiểu sai contract và vòng đời RPC | Xem Empty là một message không có field |
| Bỏ onNext() vì response không có dữ liệu | Unary server không phát response message như contract | Gửi **Empty.getDefaultInstance()** rồi **onCompleted()** |
| Dùng Empty khi cần tenant hoặc chế độ chạy | Không thể truyền tham số nghiệp vụ | Tạo request message có field rõ ràng |
| Dùng chuỗi rỗng hoặc null thay Empty | Không đúng kiểu message Protobuf | Dùng **google.protobuf.Empty** |
| Cho rằng method Empty không cần bảo mật | Có thể mở thao tác nhạy cảm cho caller không đủ quyền | Vẫn xác thực và phân quyền |
| Đổi Empty sang message riêng sau khi phát hành mà không migration | Client cũ có thể không tương thích | Phát hành contract mới hoặc kế hoạch chuyển đổi |

## 9. Ghi nhớ và tự kiểm tra

Khai báo chuẩn:

~~~proto
import "google/protobuf/empty.proto";

rpc Ping(google.protobuf.Empty)
    returns (google.protobuf.Empty);
~~~

**google.protobuf.Empty** là **message Protobuf không có field**, dùng khi một chiều của RPC không cần payload nghiệp vụ. RPC vẫn có request/response message, HTTP/2 stream, metadata và gRPC status. Trong Java, dùng **Empty.getDefaultInstance()** để tạo message rỗng; server unary thành công vẫn gửi response bằng **onNext()** rồi **onCompleted()**.

Tự kiểm tra:

1. **Ping(Empty) returns (Empty)** có phải là lời gọi không có HTTP/2 stream không? Giải thích.
2. Vì sao server vẫn phải gọi **onNext(Empty.getDefaultInstance())** khi trả response Empty?
3. Khi nào nên dùng google.protobuf.Empty, khi nào nên tạo request message riêng chưa có field?
4. Method nhận Empty có cần authentication, metadata và deadline không? Vì sao?
5. Vì sao đổi request type từ Empty sang message riêng có thể ảnh hưởng client đã phát hành?

Chọn Empty đúng lúc giúp contract thể hiện rõ rằng một thao tác không cần payload ở chiều tương ứng, đồng thời giữ API Protobuf và Java gọn, nhất quán trong Spring gRPC.
