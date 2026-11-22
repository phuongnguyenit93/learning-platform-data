# Định nghĩa bidirectional streaming RPC trong Spring gRPC

**Bidirectional streaming RPC** (RPC truyền luồng hai chiều) cho phép client gửi **nhiều request message** và server gửi **nhiều response message** trong **cùng một lời gọi RPC**. Hai phía có thể gửi và nhận độc lập trong lúc RPC còn mở: server không cần đợi client gửi xong để phản hồi; client cũng có thể tiếp tục gửi khi server đang phát dữ liệu.

Trong hệ sinh thái **Spring gRPC**, hợp đồng RPC được định nghĩa bằng **Protocol Buffers**, công cụ sinh mã tạo các message và stub Java, còn ứng dụng Spring triển khai server và quản lý các thành phần dịch vụ. Bài học này trình bày cách **định nghĩa bidirectional streaming RPC**, vòng đời hai luồng, code server/client, flow control, metadata, deadline, status, TLS, kiểm thử và giám sát độ tin cậy.

## 1. Bidirectional streaming RPC hoạt động như thế nào?

Về mặt hợp đồng, **cả request lẫn response đều có từ khóa stream**:

~~~proto
rpc Chat(stream ChatMessage) returns (stream ChatEvent);
~~~

Ví dụ một phiên trao đổi:

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as Spring gRPC server
    C->>S: Mở Chat RPC
    C->>S: ChatMessage A
    S-->>C: ChatEvent 1
    S-->>C: ChatEvent 2
    C->>S: ChatMessage B
    C->>S: ChatMessage C
    S-->>C: ChatEvent 3
    C->>S: onCompleted() - half-close
    S-->>C: ChatEvent 4
    S-->>C: onCompleted() + status OK
~~~

Trong sơ đồ, server phát hai sự kiện khi client mới gửi một message, client tiếp tục gửi trong lúc các phản hồi có thể đang đến. Đây là **full-duplex**: hai chiều có thể hoạt động đồng thời. Số lượng request và response **không bắt buộc bằng nhau**, và server không bị ràng buộc phải phát đúng một response tương ứng từng request.

| Kiểu RPC | Client gửi | Server trả | Khai báo Protobuf |
| --- | --- | --- | --- |
| Unary | Một message | Một message khi thành công | **rpc Get(Req) returns (Res);** |
| Server streaming | Một message | Một luồng message | **rpc Watch(Req) returns (stream Res);** |
| Client streaming | Một luồng message | Một message khi thành công | **rpc Upload(stream Req) returns (Res);** |
| **Bidirectional streaming** | **Một luồng message** | **Một luồng message** | **rpc Chat(stream Req) returns (stream Res);** |

Mỗi chiều có thứ tự message riêng. Trong một chiều, gRPC giữ thứ tự đã gửi, nhưng **không có thứ tự toàn cục giữa request và response**. Một response có thể đến khi client vẫn còn gửi request. Các vấn đề như một response trả lời cho request nào, ai được phép gửi trước, khi nào dừng phiên đều phải được định nghĩa ở **tầng nghiệp vụ**.

Bidirectional streaming phù hợp với chat thời gian thực, thiết bị IoT vừa gửi số liệu vừa nhận lệnh, cộng tác đa người dùng hoặc trao đổi tín hiệu điều khiển. Nếu client chỉ cần gửi một lô dữ liệu rồi nhận một kết quả tổng hợp, client streaming đơn giản hơn; nếu client gửi một request rồi chỉ nhận cập nhật, server streaming có thể thích hợp hơn.

## 2. Định nghĩa hợp đồng bằng Protocol Buffers

Ví dụ xuyên suốt: client gửi tin nhắn vào một phòng, server trả các sự kiện xác nhận. Đây là **quy tắc của ví dụ**, không phải yêu cầu rằng mọi bidirectional RPC đều phải phản hồi theo từng request.

Tạo file **src/main/proto/chat.proto**:

~~~proto
syntax = "proto3";

package demo.chat.v1;

option java_package = "vn.demo.grpc.chat.v1";
option java_multiple_files = true;
option java_outer_classname = "ChatProto";

service ChatService {
  rpc Chat(stream ChatMessage) returns (stream ChatEvent);
}

message ChatMessage {
  string room_id = 1;
  string sender = 2;
  string text = 3;
  int64 client_sequence = 4;
}

message ChatEvent {
  string room_id = 1;
  string sender = 2;
  string text = 3;
  int64 client_sequence = 4;
}
~~~

**Giải thích hợp đồng:**

1. **service ChatService** là định nghĩa dịch vụ gRPC, chứa phương thức **Chat**.
2. **stream ChatMessage** biểu diễn chiều client có thể gửi từ 0 đến nhiều message.
3. **stream ChatEvent** biểu diễn chiều server có thể gửi từ 0 đến nhiều message.
4. Đường dẫn tên đầy đủ của phương thức là **/demo.chat.v1.ChatService/Chat**.
5. **package demo.chat.v1** là namespace của Protobuf; **java_package** quyết định package của lớp Java được sinh.
6. **client_sequence** hỗ trợ tương quan response với request; bản thân trường này chưa bảo đảm xác nhận lưu bền hoặc chống xử lý trùng.

Các con số **1**, **2**, **3**, **4** là *field number* trên wire. Trong proto3, scalar không được gửi có giá trị mặc định, chẳng hạn chuỗi rỗng hay số 0. Vì vậy server phải kiểm tra các ràng buộc bắt buộc ở tầng nghiệp vụ. Sau khi schema được phát hành, cần giữ tương thích bằng cách không thay đổi ý nghĩa số field đã dùng; đánh dấu **reserved** khi loại bỏ field để tránh tái sử dụng nhầm.

Khi build đã cấu hình **protoc** và plugin **gRPC Java**, mã sinh thường có:

- **ChatMessage**, **ChatEvent** và các lớp Protobuf liên quan.
- **ChatServiceGrpc.ChatServiceImplBase** để triển khai server.
- **ChatServiceGrpc.ChatServiceStub** để gọi RPC bất đồng bộ từ Java client.

Client bidirectional streaming sử dụng **async stub** trong API gRPC Java thông dụng. Các lớp sinh mã không nên sửa thủ công; thay đổi hợp đồng trong file **.proto** và sinh mã lại.

## 3. Hai StreamObserver trong một RPC

Chữ ký phương thức streaming hai chiều trên server Java:

~~~java
public StreamObserver<ChatMessage> chat(
    StreamObserver<ChatEvent> responseObserver);
~~~

**Observer tham số** dùng để server gửi các **ChatEvent** xuống client; **observer trả về** dùng để server nhận các **ChatMessage** từ client. Hai chiều có callback riêng nhưng chia sẻ vòng đời một RPC, gồm metadata, deadline, trạng thái kết thúc và khả năng hủy.

| Vị trí | Observer | Vai trò |
| --- | --- | --- |
| Server nhận | **StreamObserver<ChatMessage>** trả về | **onNext** nhận request; **onCompleted** biết client đã gửi xong; **onError** biết chiều nhận kết thúc bất thường |
| Server gửi | **StreamObserver<ChatEvent>** được truyền vào | **onNext** gửi response; **onCompleted** kết thúc phản hồi thành công; **onError** báo lỗi RPC |
| Client gửi | Observer trả về từ **stub.chat(...)** | **onNext** gửi request; **onCompleted** half-close; **onError** dừng/hủy chiều gửi |
| Client nhận | Observer truyền vào **stub.chat(...)** | **onNext** nhận response; **onCompleted** RPC hoàn tất thành công; **onError** RPC lỗi |

**Half-close** là hành động một phía ngừng gửi dữ liệu nhưng vẫn có thể nhận dữ liệu từ phía còn lại. Khi client gọi **requestObserver.onCompleted()**, server có thể tiếp tục gửi response trước khi gọi **responseObserver.onCompleted()**. Server cũng có thể quyết định kết thúc sớm theo quy tắc nghiệp vụ.

Mỗi observer gửi phải được kết thúc đúng một lần bằng **onCompleted** hoặc **onError**. Sau khi kết thúc, không gọi thêm **onNext** trên observer đó. Nếu RPC bị hủy, cần ngừng công việc còn lại và giải phóng tài nguyên; không tiếp tục xử lý như một phiên thành công.

## 4. Triển khai server trong Spring gRPC

Giả sử ứng dụng Spring Boot đã cấu hình dependency Spring gRPC và sinh mã Protobuf, đồng thời tự đăng ký Spring bean triển khai **BindableService** lên gRPC server. Khi đó có thể triển khai:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.chat.v1.ChatEvent;
import vn.demo.grpc.chat.v1.ChatMessage;
import vn.demo.grpc.chat.v1.ChatServiceGrpc;

@Service
public class ChatServiceImpl extends ChatServiceGrpc.ChatServiceImplBase {

    private static final long MAX_MESSAGES = 1000;

    @Override
    public StreamObserver<ChatMessage> chat(
            StreamObserver<ChatEvent> responseObserver) {

        // Observer và state mới cho từng RPC.
        return new StreamObserver<>() {
            private String roomId;
            private long receivedCount;
            private boolean terminated;

            @Override
            public void onNext(ChatMessage request) {
                if (terminated) {
                    return;
                }

                if (request.getRoomId().isBlank()
                        || request.getSender().isBlank()
                        || request.getText().isBlank()
                        || request.getClientSequence() <= 0) {
                    fail(Status.INVALID_ARGUMENT
                        .withDescription("invalid chat message"));
                    return;
                }

                if (roomId == null) {
                    roomId = request.getRoomId();
                } else if (!roomId.equals(request.getRoomId())) {
                    fail(Status.INVALID_ARGUMENT
                        .withDescription("room cannot change in this RPC"));
                    return;
                }

                if (receivedCount >= MAX_MESSAGES) {
                    fail(Status.RESOURCE_EXHAUSTED
                        .withDescription("too many messages"));
                    return;
                }
                receivedCount++;

                ChatEvent event = ChatEvent.newBuilder()
                    .setRoomId(roomId)
                    .setSender("server")
                    .setText("Đã nhận: " + request.getText())
                    .setClientSequence(request.getClientSequence())
                    .build();

                // Có thể phản hồi trong lúc client tiếp tục gửi.
                responseObserver.onNext(event);
            }

            @Override
            public void onError(Throwable error) {
                // Client hủy/stream lỗi: dọn tài nguyên nếu có.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) {
                    return;
                }
                terminated = true;
                responseObserver.onCompleted();
            }

            private void fail(Status status) {
                terminated = true;
                responseObserver.onError(status.asRuntimeException());
            }
        };
    }
}
~~~

Trong ví dụ này, server gửi một **ChatEvent** ngay sau mỗi **ChatMessage** hợp lệ. Dịch vụ giữ **roomId**, **receivedCount**, **terminated** trong observer được tạo mới cho từng RPC nên hai lời gọi đồng thời không trộn trạng thái. Dù Spring thường quản lý service bean theo singleton, state của phiên vẫn cần tách riêng.

Server trả **INVALID_ARGUMENT** nếu message thiếu dữ liệu quan trọng, thay đổi room giữa phiên hoặc có sequence không hợp lệ; trả **RESOURCE_EXHAUSTED** khi vượt giới hạn số message. Sau khi client half-close hợp lệ, server kết thúc chiều phản hồi bằng **onCompleted()**.

**Giới hạn của ví dụ:** server chỉ gửi xác nhận cho chính client gọi RPC, chưa phát tán tin nhắn tới các client khác. Ứng dụng chat nhiều người cần quản lý thành viên phòng, đăng ký stream phản hồi, hàng đợi hữu hạn, cơ chế phát tán và trạng thái kết nối. Nếu nhiều thread cùng tạo sự kiện cho một phiên, phải **tuần tự hóa** mọi lần gọi vào cùng response observer và điều phối flow control.

Cách đăng ký bean gRPC service và cấu hình cổng có thể khác nhau giữa các starter/phiên bản Spring gRPC. Nên dùng cơ chế của phiên bản dự án đang sử dụng; chữ ký **StreamObserver** của gRPC Java vẫn thể hiện cùng hợp đồng hai chiều.

## 5. Java client trao đổi hai chiều với async stub

Client gọi **stub.chat(responseObserver)** và nhận về observer để gửi request. Response callback có thể chạy xen kẽ trong lúc client đang gửi. Ví dụ ứng dụng Java kết nối tới server local:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import vn.demo.grpc.chat.v1.ChatEvent;
import vn.demo.grpc.chat.v1.ChatMessage;
import vn.demo.grpc.chat.v1.ChatServiceGrpc;

public class ChatClientDemo {

    public static void main(String[] args) throws InterruptedException {
        // Plaintext chỉ cho môi trường local/dev có kiểm soát.
        ManagedChannel channel = ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();

        try {
            var stub = ChatServiceGrpc.newStub(channel)
                .withDeadlineAfter(5, TimeUnit.SECONDS);

            CountDownLatch finished = new CountDownLatch(1);
            List<ChatEvent> events = new CopyOnWriteArrayList<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();

            StreamObserver<ChatMessage> requests = stub.chat(
                new StreamObserver<ChatEvent>() {
                    @Override
                    public void onNext(ChatEvent event) {
                        events.add(event);
                        System.out.println("Server: " + event.getText());
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        finished.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        finished.countDown();
                    }
                }
            );

            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("Xin chào!")
                .setClientSequence(1)
                .build());

            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("Hẹn gặp lại.")
                .setClientSequence(2)
                .build());

            // Kết thúc chiều gửi nhưng vẫn chờ response cuối.
            requests.onCompleted();

            if (!finished.await(6, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Chat RPC timed out");
            }
            if (failure.get() != null) {
                Status.Code code =
                    Status.fromThrowable(failure.get()).getCode();
                throw new IllegalStateException(
                    "Chat RPC failed: " + code, failure.get());
            }

            System.out.println("Events received: " + events.size());
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

Với server minh họa, hai request hợp lệ dẫn tới hai sự kiện xác nhận. Nhưng số lượng phản hồi là quyết định của **protocol nghiệp vụ**, không phải số lượng cố định của bidirectional streaming. Ngay trong lúc client chưa gọi **requests.onCompleted()**, callback **responseObserver.onNext(...)** đã có thể nhận dữ liệu.

Ví dụ tạo channel trong chương trình console để dễ học. Trong ứng dụng Spring, nên cấu hình endpoint từ thuộc tính ứng dụng, tái sử dụng channel và dùng cơ chế quản lý channel/stub do Spring gRPC cung cấp. Việc gọi **shutdownNow** ở cuối main phù hợp với ví dụ ngắn; ứng dụng lâu dài nên quản lý vòng đời channel cùng ứng dụng.

### Giữ một phiên mở lâu

Client có thể giữ request stream mở để gửi khi người dùng nhập tin nhắn mới, trong khi server cũng phát event bất cứ lúc nào. Khi người dùng kết thúc phiên, client có thể half-close và tiếp tục nhận các event cuối, hoặc hủy hẳn RPC theo quy tắc ứng dụng. Cần xác định rõ khi nào server được phép đóng stream, timeout cho phiên không hoạt động và cơ chế kết nối lại khi mất mạng.

## 6. Thứ tự, tương quan và flow control

**Thứ tự được bảo toàn trong từng chiều của một stream**, nhưng không có thứ tự chung giữa chiều client → server và server → client. Do đó không được suy ra:

- Message request thứ **N** luôn tạo response thứ **N**.
- Nhận response có nghĩa message đã được **ghi bền** vào cơ sở dữ liệu.
- Gọi **onNext(...)** trả về có nghĩa bên kia đã xử lý xong.
- gRPC tự loại trùng sự kiện khi client kết nối lại và gửi lại message.

Khi cần xác định quan hệ giữa request và response, hãy bổ sung **correlation ID** hoặc **sequence** (như **client_sequence**) và mô tả rõ ý nghĩa xác nhận. Nếu server chủ động gửi nhiều loại sự kiện, có thể sử dụng **oneof** Protobuf để phân biệt xác nhận, thông báo, cập nhật trạng thái hoặc lỗi nghiệp vụ.

**Flow control** của HTTP/2/gRPC kiểm soát truyền tải dữ liệu ở mức transport, nhưng không tự giới hạn hàng đợi trong ứng dụng. Một phía gọi **onNext** quá nhanh trong khi phía nhận xử lý chậm có thể làm dữ liệu tích tụ và tăng sử dụng bộ nhớ.

Trong gRPC Java:

1. **ClientCallStreamObserver** và **ServerCallStreamObserver** có **isReady()** và **setOnReadyHandler(...)** để ứng dụng phối hợp tốc độ gửi với khả năng ghi hiện tại.
2. Client streaming async có thể cấu hình điều khiển gửi trong **ClientResponseObserver.beforeStart(...)**, trước khi truyền nhiều message.
3. **isReady()** phản ánh khả năng gửi theo cơ chế flow control, **không phải xác nhận server đã nhận hoặc lưu bền** dữ liệu.
4. Nên có **hàng đợi hữu hạn**, quota số message/kích thước message, giới hạn stream đồng thời và phương án hủy stream khi phía nhận chậm.
5. Các callback gRPC nên tránh xử lý chặn kéo dài. Nếu cần executor riêng, phải điều phối kết quả quay lại observer theo đúng thứ tự và bảo vệ state liên quan.

**StreamObserver không mặc định thread-safe.** Khi nhiều thread muốn phát sự kiện vào cùng một response observer, hãy tuần tự hóa **onNext/onCompleted/onError**, không gọi đồng thời. Tránh để chiều gửi và nhận chờ nhau vô hạn gây deadlock.

## 7. Deadline, hủy, status và phục hồi phiên

Deadline áp dụng cho **toàn bộ RPC**, bao gồm thời gian stream mở, gửi message, server xử lý và trao đổi phản hồi:

~~~java
var stub = ChatServiceGrpc.newStub(channel)
    .withDeadlineAfter(5, TimeUnit.SECONDS);
~~~

Việc gửi một message mới **không tự gia hạn deadline**. Với các phiên có thể duy trì lâu, cần chọn thời gian sống phù hợp và chính sách tái kết nối theo ngữ nghĩa ứng dụng.

| gRPC status | Ý nghĩa thường gặp | Gợi ý xử lý |
| --- | --- | --- |
| **OK** | RPC kết thúc thành công | Chốt phiên |
| **INVALID_ARGUMENT** | Message không hợp lệ | Sửa dữ liệu, không retry y nguyên |
| **UNAUTHENTICATED** | Thiếu hoặc sai thông tin xác thực | Xử lý xác thực |
| **PERMISSION_DENIED** | Không có quyền truy cập tài nguyên | Kiểm tra phân quyền |
| **RESOURCE_EXHAUSTED** | Vượt quota hoặc giới hạn stream | Giảm tải, kiểm tra giới hạn |
| **DEADLINE_EXCEEDED** | RPC quá hạn | Xác định những thao tác đã diễn ra |
| **CANCELLED** | Lời gọi bị hủy | Dọn state và tài nguyên |
| **UNAVAILABLE** | Dịch vụ hoặc kết nối tạm không sẵn sàng | Kết nối lại có kiểm soát |
| **INTERNAL** | Lỗi xử lý nội bộ | Ghi trace/log an toàn, điều tra |

Client có thể đọc mã status từ callback lỗi bằng **Status.fromThrowable(error).getCode()**. Server dùng **responseObserver.onError(Status.INVALID_ARGUMENT.withDescription("...").asRuntimeException())** để báo lỗi có cấu trúc.

Client **onCompleted()** nghĩa là gửi xong bình thường, còn **onError(...)** hoặc API hủy của gRPC được dùng khi muốn kết thúc bất thường/hủy lời gọi. Sau khi kết thúc, không gửi thêm message. Nếu server đã xử lý một phần stream trước khi bị hủy, hành động hủy không tự rollback các tác động nghiệp vụ đó.

Khi mất mạng, client có thể không biết server đã xử lý message nào. Tự phát lại cả stream dễ gây ghi trùng. Một giao thức phục hồi tin cậy thường cần **session ID/resume token**, **message ID/sequence**, cơ chế chống xử lý trùng và checkpoint/xác nhận từ phía ứng dụng. gRPC không tự cung cấp bảo đảm **exactly-once** cho thao tác ghi nghiệp vụ.

## 8. Metadata, interceptor, TLS và giám sát

**Metadata** mang thông tin ở cấp RPC, ví dụ authorization token, request ID, tenant ID, trace context. Nó không thay thế payload thay đổi theo từng message; dữ liệu như **room_id**, **sender**, **client_sequence** nên nằm trong Protobuf, còn thông tin xác thực thường được xử lý ở ranh giới lời gọi.

**Client/server interceptor** có thể bổ sung metadata, xác thực/ủy quyền, ghi trace, thống kê thời gian và mã status. Với stream dài, một RPC có thể chứa hàng nghìn message, nên đo cả **message/byte mỗi chiều** bên cạnh số RPC.

Các nguyên tắc triển khai quan trọng:

- Dùng **TLS** trong production; cân nhắc **mTLS** khi các dịch vụ cần xác thực lẫn nhau.
- Không tin trường **sender** do client gửi là danh tính đã xác thực; xác thực credential và kiểm tra quyền với phòng/tenant.
- Không ghi token, nội dung nhạy cảm hoặc toàn bộ stream lớn vào log.
- Theo dõi **số stream đang mở**, thời gian sống stream, tỷ lệ lỗi theo status, độ trễ, throughput message/byte và số lần hủy hoặc vượt deadline.
- Đặt quota, giới hạn thời gian và giới hạn bộ nhớ để stream dài không chiếm tài nguyên vô hạn.

**usePlaintext()** trong code client chỉ để minh họa khi chạy local/dev tin cậy. Cấu hình TLS/interceptor thực tế tùy phiên bản Spring gRPC, gRPC Java và hạ tầng triển khai.

## 9. Kiểm thử bidirectional streaming RPC

Nên kiểm tra cả hai chiều thực sự trao đổi message. Có thể sử dụng **gRPC in-process server/channel** để chạy lời gọi bằng async stub mà không chiếm cổng mạng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.chat.v1.ChatEvent;
import vn.demo.grpc.chat.v1.ChatMessage;
import vn.demo.grpc.chat.v1.ChatServiceGrpc;

class ChatServiceImplTest {

    @Test
    void bidiStreamExchangesMultipleMessages() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new ChatServiceImpl())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(name)
            .directExecutor()
            .build();

        try {
            List<ChatEvent> replies = new CopyOnWriteArrayList<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();
            CountDownLatch done = new CountDownLatch(1);

            var stub = ChatServiceGrpc.newStub(channel)
                .withDeadlineAfter(3, TimeUnit.SECONDS);
            StreamObserver<ChatMessage> requests = stub.chat(
                new StreamObserver<ChatEvent>() {
                    @Override
                    public void onNext(ChatEvent event) {
                        replies.add(event);
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        done.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        done.countDown();
                    }
                });

            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("Một")
                .setClientSequence(1)
                .build());
            requests.onNext(ChatMessage.newBuilder()
                .setRoomId("general")
                .setSender("an")
                .setText("Hai")
                .setClientSequence(2)
                .build());
            requests.onCompleted();

            assertTrue(done.await(4, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(2, replies.size());
            assertEquals(1L, replies.get(0).getClientSequence());
            assertEquals("Đã nhận: Hai", replies.get(1).getText());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Test cần JUnit và **gRPC in-process** tương thích với gRPC Java của dự án. Nó kiểm tra hợp đồng hai chiều ở mức gRPC, nhưng chưa kiểm tra việc Spring đăng ký bean. Để xác nhận tích hợp Spring gRPC, cần bổ sung integration test khởi động Spring context và server thật theo cấu hình test, xác minh các interceptor và channel nếu có.

Những tình huống nên kiểm thử thêm:

1. Stream rỗng: client half-close ngay, server hoàn thành bình thường theo quy tắc ví dụ.
2. Message sai, như **room_id** rỗng hoặc **client_sequence <= 0**: RPC kết thúc bằng **INVALID_ARGUMENT**.
3. Hai phiên chạy đồng thời: state/response không bị trộn.
4. Client hủy hoặc hết deadline giữa phiên: server dọn tài nguyên, không gửi response thành công sau khi RPC đã hủy.
5. Nhiều request khi phía nhận chậm: hàng đợi và flow control hoạt động trong giới hạn.
6. TLS, phân quyền và tái kết nối: kiểm tra session ID, chống trùng và checkpoint.

## 10. Lỗi thiết kế thường gặp

| Sai sót | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đặt **stream** ở một phía | Thành client/server streaming, không phải hai chiều | Đặt **stream** ở cả request và response |
| Đợi client hoàn tất mới phản hồi trong mọi trường hợp | Mất khả năng trao đổi tức thời, có thể gây chờ nhau | Phát response theo quy tắc nghiệp vụ khi dữ liệu sẵn sàng |
| Giả định luôn một response cho mỗi request | Nhầm lẫn khi server phát sự kiện độc lập | Định nghĩa correlation ID và loại event |
| Dùng biến trạng thái singleton cho từng phiên | Trộn dữ liệu của nhiều RPC | Tạo state trong observer riêng mỗi RPC |
| Phát **onNext** từ nhiều thread không điều phối | Race, sai thứ tự, lỗi callback | Tuần tự hóa việc ghi vào observer |
| Không có giới hạn bộ đệm hoặc thời gian sống | Stream chiếm tài nguyên lâu | Flow control, quota, deadline |
| Đóng channel ngay sau khi gửi | Bỏ lỡ response chưa nhận | Đợi callback hoàn tất, quản lý vòng đời channel |
| Retry cả stream khi mất mạng | Có thể xử lý trùng message | Session ID, sequence, idempotency |
| Dùng plaintext hoặc tin trường **sender** | Lộ dữ liệu, giả mạo danh tính | TLS/mTLS, xác thực và phân quyền |

## 11. Ghi nhớ và tự kiểm tra

Cú pháp cốt lõi để **định nghĩa bidirectional streaming RPC**:

~~~proto
service ExampleService {
  rpc Exchange(stream Request) returns (stream Response);
}
~~~

Phía **server**, phương thức nhận observer để gửi response và trả về observer để nhận request; phía **client**, async stub nhận observer phản hồi và trả observer gửi request. Hai chiều có thể gửi dữ liệu đồng thời, mỗi chiều có thứ tự riêng, cùng chia sẻ metadata/deadline/status của một RPC. Phải xử lý vòng đời, hủy, giới hạn tài nguyên và khôi phục phiên ở tầng ứng dụng.

Tự trả lời:

1. Vì sao phải có từ khóa **stream** ở cả hai phía của **rpc Chat(...)**?
2. Client gọi **requests.onCompleted()** thì có còn nhận **ChatEvent** không?
3. Server có thể gửi ba sự kiện cho một request trong bidirectional streaming không? Vì sao?
4. Vì sao một event xác nhận chưa đủ để kết luận request đã được ghi bền?
5. Khi kết nối bị ngắt giữa phiên, cần thêm thông tin nào để phát lại mà không xử lý trùng?

Hiểu đúng hợp đồng Protobuf, hai **StreamObserver**, cơ chế kết thúc và luồng dữ liệu độc lập là nền tảng để xây dựng dịch vụ bidirectional streaming RPC an toàn, kiểm thử được và dễ giám sát trong Spring gRPC.
