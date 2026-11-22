# Định nghĩa unary RPC trong Spring gRPC

Trong hệ sinh thái **Spring gRPC**, một phương thức **unary RPC** (Remote Procedure Call đơn yêu cầu, đơn phản hồi) cho phép ứng dụng Java gọi một phương thức trên dịch vụ ở máy khác gần giống gọi một hàm thông thường. Hợp đồng giao tiếp được khai báo bằng **Protocol Buffers (Protobuf)**; công cụ sinh mã tạo các kiểu dữ liệu và lớp client/server cho Java. Spring quản lý vòng đời các thành phần dịch vụ, còn gRPC đảm nhận việc truyền thông điệp, xử lý trạng thái lời gọi và giao tiếp qua HTTP/2.

Bài học tập trung vào cách **định nghĩa, triển khai và sử dụng unary RPC**. Những khái niệm như metadata, deadline, status, interceptor, TLS, kiểm thử và quan sát hệ thống được giới thiệu trong phạm vi cần thiết để sử dụng phương thức unary một cách đúng đắn.

## 1. Unary RPC là gì?

Một unary RPC có dạng logic:

**Một yêu cầu → xử lý ở server → một phản hồi thành công, hoặc một trạng thái lỗi.**

- **Client** gửi đúng một *request message* theo kiểu dữ liệu đã khai báo.
- **Server** xử lý yêu cầu. Nếu thành công, server gửi đúng một *response message* và kết thúc RPC với trạng thái gRPC **OK**.
- Nếu xử lý thất bại, server kết thúc RPC bằng một **gRPC status** khác OK; client có thể nhận lỗi mà không nhận được response message.
- Một request/response Protobuf có thể được vận chuyển qua nhiều frame HTTP/2. Số lượng frame mạng không làm thay đổi quy tắc **một thông điệp yêu cầu, một thông điệp phản hồi thành công** của unary RPC.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant T as gRPC / HTTP/2
    participant S as Spring gRPC server
    C->>T: SayHello(HelloRequest)
    T->>S: Chuyển 1 request
    S->>S: Kiểm tra và xử lý
    alt Thành công
        S-->>T: HelloReply + status OK
        T-->>C: 1 response
    else Thất bại
        S-->>T: gRPC status lỗi
        T-->>C: StatusRuntimeException (blocking stub)
    end
~~~

Ví dụ phù hợp: lấy hồ sơ theo mã, xác thực một yêu cầu, tính phí vận chuyển, tra cứu tồn kho hoặc tạo một đơn hàng. Điểm cần phân biệt là **unary mô tả số lượng message trong một RPC**, chứ không có nghĩa server chỉ được thực hiện một thao tác nội bộ, và cũng không tự bảo đảm việc xử lý nghiệp vụ chỉ xảy ra một lần nếu client gửi lại yêu cầu.

| Kiểu RPC | Yêu cầu từ client | Phản hồi từ server | Cú pháp trong Protobuf |
| --- | --- | --- | --- |
| **Unary** | 1 message | 1 message khi thành công | **rpc SayHello(HelloRequest) returns (HelloReply);** |
| Server streaming | 1 message | Luồng nhiều message | Có **stream** trước kiểu phản hồi |
| Client streaming | Luồng nhiều message | 1 message | Có **stream** trước kiểu yêu cầu |
| Bidirectional streaming | Luồng nhiều message | Luồng nhiều message | Có **stream** ở cả hai phía |

## 2. Khai báo hợp đồng unary RPC bằng Protocol Buffers

Tạo file **src/main/proto/greeting.proto**:

~~~proto
syntax = "proto3";

package demo.greeting.v1;

option java_package = "vn.demo.grpc.greeting.v1";
option java_multiple_files = true;
option java_outer_classname = "GreetingProto";

service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
~~~

Các thành phần quan trọng:

1. **service Greeter** là tên dịch vụ gRPC.
2. **rpc SayHello(HelloRequest) returns (HelloReply)** định nghĩa phương thức nhận một **HelloRequest** và trả về một **HelloReply**. Không có từ khóa **stream**, vì vậy đây là unary RPC.
3. **message** khai báo cấu trúc dữ liệu Protobuf. Con số **1** là *field number* được dùng trong biểu diễn nhị phân, không phải giá trị mặc định.
4. **package demo.greeting.v1** là namespace của dịch vụ trong Protobuf; đường dẫn đầy đủ của RPC là **/demo.greeting.v1.Greeter/SayHello**.
5. **java_package** xác định package mã Java được sinh; **java_multiple_files = true** cho phép các lớp message được sinh riêng.

Sau khi cấu hình trình sinh mã Protobuf và plugin gRPC Java trong bản build của dự án, mã sinh thường bao gồm:

- **HelloRequest**, **HelloReply** và lớp hỗ trợ Protobuf.
- **GreeterGrpc** với lớp cơ sở **GreeterGrpc.GreeterImplBase** để triển khai server.
- Các loại client stub như **GreeterGrpc.GreeterBlockingStub**, **GreeterGrpc.GreeterFutureStub** và **GreeterGrpc.GreeterStub**.

Đây là mã **được sinh từ hợp đồng**; không nên sửa thủ công. Khi phát triển phiên bản mới của message, giữ nguyên ý nghĩa và số field đã phát hành; thêm field mới bằng số chưa sử dụng và dùng **reserved** cho số hoặc tên bị loại bỏ để tránh tái sử dụng gây mất tương thích.

## 3. Triển khai unary RPC ở Spring server

Giả sử dự án Spring Boot đã có thành phần Spring gRPC server và bước sinh mã Java từ file Protobuf. Ta có thể triển khai dịch vụ bằng cách kế thừa lớp cơ sở được sinh, sau đó khai báo lớp triển khai là Spring bean:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.greeting.v1.GreeterGrpc;
import vn.demo.grpc.greeting.v1.HelloReply;
import vn.demo.grpc.greeting.v1.HelloRequest;

@Service
public class GreeterService extends GreeterGrpc.GreeterImplBase {

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {

        String name = request.getName().trim();
        if (name.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name must not be blank")
                    .asRuntimeException()
            );
            return;
        }

        HelloReply reply = HelloReply.newBuilder()
            .setMessage("Xin chào, " + name + "!")
            .build();

        responseObserver.onNext(reply);
        responseObserver.onCompleted();
    }
}
~~~

Trong cấu hình Spring gRPC tự động đăng ký các bean triển khai **BindableService**, bean **GreeterService** sẽ được đăng ký với gRPC server. Nếu dự án sử dụng một starter hoặc phiên bản tích hợp khác, cần đối chiếu cách đăng ký dịch vụ tương ứng; bản thân hợp đồng unary và cách sử dụng **StreamObserver** không đổi.

Phương thức Java **sayHello** có tên theo quy ước mã sinh từ **SayHello** trong Protobuf. Đối tượng **responseObserver** là kênh để server kết thúc lời gọi:

- **Thành công:** gọi **onNext(reply)** đúng một lần, sau đó gọi **onCompleted()** đúng một lần.
- **Thất bại:** gọi **onError(exception)** và kết thúc; không tiếp tục gọi **onNext** hoặc **onCompleted**.
- **Không được** gọi **onNext** hai lần để mô phỏng danh sách kết quả. Nếu cần nhiều bản ghi trong một unary response, đặt chúng trong một message có trường **repeated**; nếu cần phát lần lượt các bản ghi, hãy định nghĩa streaming RPC.

Đừng để lỗi nghiệp vụ được báo bằng một message thành công chứa chuỗi như “ERROR” nếu chúng thực chất là lỗi RPC. Sử dụng mã gRPC status phù hợp giúp client xử lý có cấu trúc.

## 4. Gọi unary RPC từ Java client

Với unary RPC, cách đơn giản nhất là **blocking stub**: lời gọi Java chờ phản hồi hoặc ném ngoại lệ khi RPC thất bại. Ví dụ sau minh họa một client được Spring quản lý, dùng gRPC Java để tự tạo channel:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import vn.demo.grpc.greeting.v1.GreeterGrpc;

@Configuration
public class GreetingClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel greetingChannel() {
        // Chỉ dùng plaintext trong môi trường phát triển tin cậy.
        return ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(
            ManagedChannel greetingChannel) {
        return GreeterGrpc.newBlockingStub(greetingChannel);
    }
}
~~~

~~~java
package vn.demo.app;

import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import vn.demo.grpc.greeting.v1.GreeterGrpc;
import vn.demo.grpc.greeting.v1.HelloReply;
import vn.demo.grpc.greeting.v1.HelloRequest;

@Service
public class GreetingClient {
    private final GreeterGrpc.GreeterBlockingStub stub;

    public GreetingClient(GreeterGrpc.GreeterBlockingStub stub) {
        this.stub = stub;
    }

    public String greet(String name) {
        HelloRequest request = HelloRequest.newBuilder()
            .setName(name)
            .build();

        try {
            HelloReply reply = stub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .sayHello(request);
            return reply.getMessage();
        } catch (StatusRuntimeException ex) {
            // Ở đây ứng dụng có thể ánh xạ mã lỗi sang lỗi nghiệp vụ.
            throw new IllegalStateException(
                "gRPC SayHello failed: " + ex.getStatus().getCode(), ex);
        }
    }
}
~~~

Điều kiện để ví dụ hoạt động: server đang lắng nghe trên host/port tương ứng; client và server sử dụng các lớp sinh từ hợp đồng tương thích; môi trường phát triển đã cấu hình dependency gRPC Java, Spring gRPC và sinh mã Protobuf. Trong ứng dụng thực tế, nên lấy địa chỉ từ cấu hình thay vì cố định **localhost:9090**, đồng thời ưu tiên cơ chế quản lý channel/client do phiên bản Spring gRPC của dự án cung cấp.

**Blocking stub** phù hợp với luồng xử lý đồng bộ. **Future stub** cung cấp kết quả bất đồng bộ, còn **async stub** hỗ trợ callback qua observer; cả hai vẫn tuân thủ hợp đồng một request, một response của unary RPC. Không nên chặn một luồng xử lý bất đồng bộ chỉ để đợi blocking stub nếu kiến trúc đang yêu cầu non-blocking.

## 5. Deadline, status, metadata và interceptor

### Deadline và hủy lời gọi

**Deadline** là giới hạn thời gian client chấp nhận chờ RPC hoàn tất. Trong ví dụ, **withDeadlineAfter(2, TimeUnit.SECONDS)** tạo một stub được cấu hình hạn chót cho lời gọi, không chỉnh sửa stub gốc. Khi hết hạn, client thường nhận **DEADLINE_EXCEEDED**. Server cũng có thể quan sát việc hủy để dừng công việc không còn cần thiết.

Deadline cần xuất phát từ ngân sách thời gian của toàn bộ request, kể cả các RPC phụ thuộc. Việc client nhận lỗi hết hạn **không chứng minh** rằng server chưa thực hiện thay đổi dữ liệu. Khi unary RPC tạo tác dụng phụ như thanh toán hoặc tạo đơn, cần thiết kế **idempotency key** hoặc cơ chế chống thực hiện trùng.

### Các mã trạng thái thường gặp

| gRPC status | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| **OK** | RPC kết thúc thành công | Đọc response |
| **INVALID_ARGUMENT** | Dữ liệu yêu cầu không hợp lệ | Sửa đầu vào; không retry y nguyên |
| **NOT_FOUND** | Không tồn tại tài nguyên được hỏi | Xử lý kết quả không tìm thấy |
| **UNAUTHENTICATED** | Thiếu hoặc sai thông tin xác thực | Cấp lại/xử lý thông tin xác thực |
| **PERMISSION_DENIED** | Đã xác định danh tính nhưng không có quyền | Kiểm tra phân quyền |
| **DEADLINE_EXCEEDED** | Hết thời gian cho phép | Đánh giá timeout và trạng thái thao tác |
| **UNAVAILABLE** | Dịch vụ/kết nối tạm thời không sẵn sàng | Có thể retry có kiểm soát nếu an toàn |
| **INTERNAL** | Lỗi nội bộ phía dịch vụ | Ghi nhận để điều tra, tránh lộ chi tiết nhạy cảm |

Phía **blocking stub**, lỗi RPC được biểu diễn bằng **StatusRuntimeException**, cho phép đọc **ex.getStatus().getCode()** và, khi có, trailer metadata. Lỗi Java thông thường ở server không nên được để trôi ra ngoài như chi tiết gỡ lỗi cho client; hãy chuyển các lỗi dự kiến thành status phù hợp và log phần chẩn đoán ở phía server.

### Metadata, interceptor và TLS

**Metadata** là thông tin bổ sung ở header hoặc trailer của lời gọi gRPC, chẳng hạn bearer token, request ID hoặc thông tin truy vết. Dữ liệu nghiệp vụ chính nên nằm trong Protobuf message. **Client/server interceptor** thích hợp cho các xử lý chung như xác thực, ghi log thời gian, gắn trace ID và đo số lượng lời gọi; tránh nhân bản các thao tác này trong từng phương thức **sayHello**.

Ví dụ, client có thể gửi **x-request-id** trong metadata; server interceptor đọc giá trị này để gắn vào log. Metadata không tự cung cấp bảo mật: với môi trường sản xuất phải bảo vệ kênh bằng **TLS**, cân nhắc **mTLS** khi hai dịch vụ cần xác thực lẫn nhau, và cấu hình quy tắc kiểm tra quyền phù hợp. Lệnh **usePlaintext()** trong ví dụ chỉ dành cho local/dev.

## 6. Kiểm thử unary RPC

Nên kiểm tra ít nhất ba trường hợp: yêu cầu hợp lệ trả **một** phản hồi, yêu cầu không hợp lệ trả đúng status, và client xử lý timeout/lỗi kết nối theo chính sách. Với gRPC Java, có thể tạo server và channel **in-process** để kiểm tra giao thức mà không chiếm cổng mạng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.greeting.v1.GreeterGrpc;
import vn.demo.grpc.greeting.v1.HelloRequest;

class GreeterServiceTest {

    @Test
    void unaryReturnsReplyOrValidationStatus() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new GreeterService())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(serverName)
            .directExecutor()
            .build();

        try {
            var stub = GreeterGrpc.newBlockingStub(channel);
            var reply = stub.sayHello(
                HelloRequest.newBuilder().setName("An").build());
            assertEquals("Xin chào, An!", reply.getMessage());

            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.sayHello(
                    HelloRequest.newBuilder().setName("  ").build()));
            assertEquals(
                Status.Code.INVALID_ARGUMENT,
                error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Test trên yêu cầu thư viện **gRPC in-process** và JUnit tương ứng, kiểm tra logic RPC và giao thức gRPC Java. Để xác nhận Spring thực sự đăng ký bean dịch vụ, nên bổ sung **integration test khởi động Spring context/gRPC server**, thực hiện lời gọi qua channel cấu hình cho môi trường test. Với TLS hoặc interceptor, cần có bài kiểm thử tích hợp riêng cho đường truyền và metadata.

Trong vận hành, theo dõi **tỷ lệ thành công/lỗi theo status**, **độ trễ theo phương thức và các phân vị p95/p99**, **số RPC đang xử lý** và **deadline vượt quá**. Dùng trace ID để nối một unary RPC với các hoạt động downstream, nhưng tránh ghi token xác thực hoặc dữ liệu nhạy cảm vào log.

## 7. Các lỗi thiết kế thường gặp

1. **Nhầm unary với stream:** gọi **onNext** nhiều lần ở server unary hoặc khai báo **stream** khi chỉ cần một response. Hãy chọn cardinality ngay từ hợp đồng Protobuf.
2. **Quên kết thúc observer:** có **onNext** nhưng thiếu **onCompleted**, khiến RPC chưa được kết thúc đúng cách. Mỗi nhánh xử lý phải kết thúc bằng **onCompleted** hoặc **onError**.
3. **Thiếu deadline:** client có thể chờ quá lâu khi hệ thống phụ thuộc bị treo. Đặt ngân sách thời gian có chủ đích ở ranh giới lời gọi.
4. **Retry thao tác không idempotent:** request đã được server xử lý nhưng client chưa nhận phản hồi; gửi lại có thể tạo dữ liệu trùng. Thiết kế khóa idempotency hoặc xác minh kết quả trước khi retry.
5. **Thay đổi số field Protobuf đã phát hành:** có thể khiến dữ liệu cũ bị diễn giải sai. Giữ số field ổn định và quản lý tương thích hợp đồng.
6. **Dùng plaintext hoặc lộ thông tin lỗi trong production:** cấu hình TLS, xác thực và ánh xạ lỗi phù hợp với ranh giới tin cậy.

## 8. Ghi nhớ và tự kiểm tra

Để định nghĩa unary RPC, chỉ cần khai báo một phương thức **rpc Method(Request) returns (Response)** trong **service** Protobuf mà không có từ khóa **stream**. Trên server Java, triển khai phương thức tương ứng từ **GreeterGrpc.GreeterImplBase** và bảo đảm mỗi lời gọi được kết thúc đúng quy tắc **một response khi thành công hoặc một status lỗi**. Trên client, dùng stub được sinh và đặt deadline theo ngân sách thời gian của ứng dụng.

Tự trả lời các câu hỏi sau để kiểm tra mức độ hiểu:

- Nếu cần trả về 100 sản phẩm trong một unary RPC, nên mô hình hóa response như thế nào? Khi nào chuyển sang server streaming?
- Vì sao **onNext(reply)** mà không gọi **onCompleted()** là một lỗi?
- Nếu client nhận **DEADLINE_EXCEEDED** sau khi gửi yêu cầu tạo đơn hàng, có được phép kết luận đơn hàng chưa được tạo không?
- Trong trường hợp dữ liệu đầu vào sai, server nên trả **INVALID_ARGUMENT** hay **INTERNAL**? Client nên xử lý khác nhau ra sao?

Nắm vững các quy tắc này là nền tảng để triển khai các dịch vụ gRPC bằng Spring và mở rộng sang streaming RPC, interceptor nâng cao, bảo mật và kiểm thử độ tin cậy.
