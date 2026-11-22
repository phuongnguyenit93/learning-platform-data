# Định nghĩa client streaming RPC trong Spring gRPC

**Client streaming RPC** là phương thức gRPC cho phép client gửi **một luồng gồm nhiều message** đến server trong **một RPC**, sau đó server gửi **một message phản hồi khi thành công**. Đây là một trong bốn kiểu RPC mà Protocol Buffers hỗ trợ định nghĩa. Trong hệ sinh thái **Spring gRPC**, hợp đồng được khai báo bằng file **.proto**, mã Java client/server được sinh tự động, còn Spring quản lý các thành phần triển khai dịch vụ.

Bài học này giải thích cách định nghĩa client streaming RPC, triển khai gRPC Java server trong Spring, gửi luồng từ Java client và xử lý các vấn đề thực tế: kết thúc luồng, trạng thái lỗi, deadline, metadata, xác thực, TLS, kiểm thử và giám sát độ tin cậy.

## 1. Client streaming RPC hoạt động như thế nào?

Với client streaming, client tạo **một lời gọi RPC**, lần lượt gửi các request message, báo rằng mình đã gửi xong (*half-close*), rồi nhận một response message từ server. Server thường xử lý/tổng hợp các message đến trước khi tạo kết quả cuối.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant S as Spring gRPC server
    C->>S: UploadReadings() - mở RPC
    loop 0..N request messages
        C->>S: Reading
        S->>S: Kiểm tra và tích lũy
    end
    C->>S: onCompleted() - ngừng gửi
    S->>S: Hoàn tất tổng hợp
    S-->>C: UploadSummary (một response)
    S-->>C: status OK - kết thúc
~~~

Điểm quan trọng: **0..N message** ở chiều client chỉ là số lượng message trong **một RPC**, không có nghĩa là N lời gọi độc lập. Trường hợp luồng rỗng có hợp lệ hay không phụ thuộc vào quy tắc nghiệp vụ. Server cũng có thể kết thúc sớm bằng **status lỗi** mà không chờ client gửi hết message.

| Kiểu RPC | Client gửi | Server trả về | Định nghĩa trong .proto |
| --- | --- | --- | --- |
| Unary | Một message | Một message | **rpc Get(Request) returns (Response);** |
| Server streaming | Một message | Một luồng message | **rpc List(Request) returns (stream Response);** |
| **Client streaming** | **Một luồng message** | **Một message** | **rpc Upload(stream Request) returns (Response);** |
| Bidirectional streaming | Một luồng message | Một luồng message | **rpc Chat(stream Request) returns (stream Response);** |

Một số tình huống phù hợp: gửi hàng loạt bản ghi đo lường IoT, tổng hợp số liệu từ agent, tải dữ liệu chia thành nhiều phần hoặc gửi các sự kiện để server trả về một kết quả kiểm tra cuối. Nếu ứng dụng cần phản hồi xác nhận riêng cho **từng message**, client streaming thuần túy chưa đáp ứng điều đó; nên cân nhắc bidirectional streaming hoặc nhiều unary RPC.

## 2. Định nghĩa hợp đồng Protobuf

Ví dụ: một thiết bị gửi nhiều giá trị đo trong cùng RPC, server phản hồi tổng số mẫu đã chấp nhận và tổng các giá trị.

Tạo file **src/main/proto/telemetry.proto**:

~~~proto
syntax = "proto3";

package demo.telemetry.v1;

option java_package = "vn.demo.grpc.telemetry.v1";
option java_multiple_files = true;
option java_outer_classname = "TelemetryProto";

service Telemetry {
  rpc UploadReadings(stream Reading) returns (UploadSummary);
}

message Reading {
  string device_id = 1;
  int64 sequence = 2;
  double value = 3;
}

message UploadSummary {
  int64 accepted_count = 1;
  double total = 2;
}
~~~

Phân tích dòng định nghĩa phương thức:

~~~proto
rpc UploadReadings(stream Reading) returns (UploadSummary);
~~~

- **UploadReadings** là tên RPC.
- Từ khóa **stream** nằm trước **Reading**: client có thể gửi nhiều message **Reading** theo thứ tự trong cùng một RPC.
- **UploadSummary** không có **stream**: server trả **đúng một response message khi RPC thành công**.
- RPC được định danh đầy đủ là **/demo.telemetry.v1.Telemetry/UploadReadings**.
- **java_package** là package Java của các lớp được sinh; nó độc lập với namespace Protobuf **package**.

Trong message, các số **1**, **2**, **3** là mã field dùng cho biểu diễn nhị phân Protobuf. Sau khi hợp đồng đã được sử dụng, không được tùy tiện thay đổi ý nghĩa hoặc tái sử dụng số field cũ; khi xóa field nên dùng **reserved**. Đối với proto3, các scalar thông thường có giá trị mặc định (chẳng hạn chuỗi rỗng, số 0) nếu không được gửi; cần chủ động xác định yêu cầu nào bắt buộc ở tầng nghiệp vụ.

Khi build đã cấu hình **protoc** và plugin sinh mã **gRPC Java**, các lớp quan trọng thường có:

- **Reading** và **UploadSummary**: kiểu Protobuf dùng để tạo và đọc message.
- **TelemetryGrpc.TelemetryImplBase**: lớp nền cho server.
- **TelemetryGrpc.TelemetryStub**: asynchronous stub; hỗ trợ client streaming qua **StreamObserver**.

**Blocking stub** được sinh chủ yếu dành cho unary và server streaming; để **gửi client stream** trong API gRPC Java thông dụng, dùng **async stub**. Không tự sửa các file Java do protoc sinh ra.

## 3. Triển khai server bằng gRPC Java và Spring

Với client streaming, phương thức server **không nhận một request message đơn lẻ** như unary. Thay vào đó, nó **nhận observer để gửi phản hồi và trả về một observer để nhận các message từ client**.

Chữ ký tổng quát:

~~~java
public StreamObserver<Reading> uploadReadings(
    StreamObserver<UploadSummary> responseObserver)
~~~

Giả sử dự án Spring gRPC đã được cấu hình sinh mã từ Protobuf và tự đăng ký các Spring bean triển khai **BindableService**. Khi đó có thể viết:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.telemetry.v1.Reading;
import vn.demo.grpc.telemetry.v1.TelemetryGrpc;
import vn.demo.grpc.telemetry.v1.UploadSummary;

@Service
public class TelemetryService extends TelemetryGrpc.TelemetryImplBase {

    private static final long MAX_READINGS = 10_000;

    @Override
    public StreamObserver<Reading> uploadReadings(
            StreamObserver<UploadSummary> responseObserver) {

        // Mỗi lần gọi RPC tạo một observer và trạng thái tổng hợp riêng.
        return new StreamObserver<>() {
            private long acceptedCount;
            private double total;
            private boolean terminated;

            @Override
            public void onNext(Reading reading) {
                if (terminated) {
                    return;
                }

                if (reading.getDeviceId().isBlank()
                        || !Double.isFinite(reading.getValue())) {
                    fail(Status.INVALID_ARGUMENT
                        .withDescription("invalid reading"));
                    return;
                }

                if (acceptedCount >= MAX_READINGS) {
                    fail(Status.RESOURCE_EXHAUSTED
                        .withDescription("too many readings"));
                    return;
                }

                acceptedCount++;
                total += reading.getValue();
            }

            @Override
            public void onError(Throwable error) {
                // Client hủy RPC hoặc transport gặp lỗi:
                // bỏ trạng thái đang tổng hợp, không gửi response thành công.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) {
                    return;
                }

                terminated = true;
                UploadSummary summary = UploadSummary.newBuilder()
                    .setAcceptedCount(acceptedCount)
                    .setTotal(total)
                    .build();

                responseObserver.onNext(summary);
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

Ví dụ trên nhận **0..10.000** message hợp lệ; nếu client gửi luồng rỗng rồi kết thúc, server trả summary có **accepted_count = 0**, **total = 0**. Đây là một **quy tắc nghiệp vụ được chọn cho ví dụ**, không phải yêu cầu bắt buộc của client streaming. Nếu nghiệp vụ cần ít nhất một message, hãy kiểm tra **acceptedCount == 0** trong **onCompleted()** và kết thúc bằng **INVALID_ARGUMENT**.

### Vòng đời của request observer trên server

| Callback của observer nhận request | Khi nào được gọi? | Trách nhiệm |
| --- | --- | --- |
| **onNext(Reading)** | Mỗi khi nhận thêm một message | Kiểm tra hợp lệ, tích lũy hoặc xử lý dữ liệu |
| **onCompleted()** | Client đã half-close thành công | Kết thúc tổng hợp, gửi **một** summary và hoàn tất phản hồi |
| **onError(Throwable)** | Request stream kết thúc bất thường | Dọn tài nguyên, không coi dữ liệu chưa hoàn tất là thành công |

Để phản hồi thành công, server gửi **responseObserver.onNext(summary)** một lần rồi **responseObserver.onCompleted()**. Khi không thể xử lý tiếp, gửi **responseObserver.onError(statusException)**. Sau khi observer phản hồi đã kết thúc, tuyệt đối không gọi thêm **onNext**, **onCompleted** hoặc **onError** trên observer đó.

State **acceptedCount**, **total** và **terminated** đặt **bên trong observer của từng RPC** để các lời gọi đồng thời không dùng chung dữ liệu. Nếu triển khai xử lý bất đồng bộ hoặc chuyển dữ liệu sang nhiều thread, phải bảo đảm truy cập state và lời gọi đến observer được đồng bộ/tuần tự hóa phù hợp. gRPC Java không cam kết các lần gọi vào một **StreamObserver** từ nhiều thread là an toàn.

Việc hoàn thành stream **không tự tạo giao dịch cơ sở dữ liệu**. Nếu mỗi **onNext** lập tức lưu dữ liệu xuống DB, một lỗi giữa chừng có thể để lại một phần dữ liệu. Nếu cần tính tất cả hoặc không có gì, server phải xây dựng cơ chế transaction, vùng đệm, staging hoặc commit có kiểm soát.

## 4. Java client gửi nhiều message bằng asynchronous stub

Trong gRPC Java, client gọi **uploadReadings(responseObserver)** trên **async stub** để nhận về **requestObserver**. Sau đó client gửi lần lượt từng **Reading** bằng **onNext** và gọi **onCompleted** đúng một lần để báo đã gửi xong.

Ví dụ chương trình Java đơn giản, giả định server đang chạy tại **localhost:9090**:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import vn.demo.grpc.telemetry.v1.Reading;
import vn.demo.grpc.telemetry.v1.TelemetryGrpc;
import vn.demo.grpc.telemetry.v1.UploadSummary;

public class TelemetryClientDemo {

    public static void main(String[] args) throws InterruptedException {
        // Plaintext chỉ phù hợp với ví dụ local/dev.
        ManagedChannel channel = ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();

        try {
            var stub = TelemetryGrpc.newStub(channel)
                .withDeadlineAfter(5, TimeUnit.SECONDS);

            CountDownLatch finished = new CountDownLatch(1);
            AtomicReference<UploadSummary> response =
                new AtomicReference<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();

            StreamObserver<Reading> requests = stub.uploadReadings(
                new StreamObserver<UploadSummary>() {
                    @Override
                    public void onNext(UploadSummary summary) {
                        response.set(summary);
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

            requests.onNext(Reading.newBuilder()
                .setDeviceId("sensor-01")
                .setSequence(1)
                .setValue(2.5)
                .build());

            requests.onNext(Reading.newBuilder()
                .setDeviceId("sensor-01")
                .setSequence(2)
                .setValue(3.0)
                .build());

            // Client đã gửi hết các Reading trong RPC này.
            requests.onCompleted();

            if (!finished.await(6, TimeUnit.SECONDS)) {
                throw new IllegalStateException("RPC callback timeout");
            }
            if (failure.get() != null) {
                throw new IllegalStateException(
                    "UploadReadings failed", failure.get());
            }

            UploadSummary summary = response.get();
            if (summary == null) {
                throw new IllegalStateException("Missing response");
            }

            System.out.println(
                "Accepted: " + summary.getAcceptedCount()
                    + ", total: " + summary.getTotal());
            // Accepted: 2, total: 5.5
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

Trong ứng dụng Spring, channel hoặc stub thường được cấu hình thành bean do Spring quản lý, và địa chỉ server nên lấy từ cấu hình. Với các starter/phiên bản Spring gRPC khác nhau, cách khai báo channel bean và đăng ký dịch vụ có thể khác; **định nghĩa Protobuf** và **giao thức StreamObserver** vẫn giữ nguyên.

Lưu ý về hành vi:

1. **stub.uploadReadings(...)** mở một RPC client streaming và trả về observer để ghi request; đây không phải lời gọi đồng bộ trả ngay **UploadSummary**.
2. **requests.onNext(...)** gửi thêm một message vào luồng. Gọi phương thức này không bảo đảm message đã được server xử lý hoặc ghi bền.
3. **requests.onCompleted()** là hành động *half-close* ở phía client. Client ngừng gửi request nhưng vẫn chờ server trả lời; không đóng channel ngay trước khi nhận callback.
4. **response observer** bên client được gọi **onNext** tối đa một lần khi server phản hồi thành công, sau đó **onCompleted**. Trường hợp thất bại, client nhận **onError**.
5. Đối với tác vụ gửi dữ liệu đồng thời từ nhiều thread, hãy tuần tự hóa các lời gọi **onNext/onCompleted/onError** trên cùng request observer. Không ghi vào observer sau khi nó đã kết thúc.

Đoạn mã dùng **CountDownLatch** để quan sát kết quả rõ ràng trong chương trình minh họa. Ứng dụng event-driven thường xử lý kết quả qua callback hoặc cơ chế bất đồng bộ của mình thay vì chặn thread. Với client streaming, channel nên được **tái sử dụng** giữa các RPC và đóng trong vòng đời ứng dụng, không tạo và đóng một channel cho mỗi Reading.

## 5. Xử lý lỗi, deadline và hủy stream

Không phải mọi luồng đều kết thúc bình thường. Các tình huống đáng chú ý:

| Sự kiện | Hành vi mong đợi |
| --- | --- |
| Một Reading không hợp lệ | Server kết thúc bằng **INVALID_ARGUMENT** |
| Vượt giới hạn số Reading | Server kết thúc bằng **RESOURCE_EXHAUSTED** |
| Client báo đã gửi xong | Server trả một summary và **OK** nếu xử lý thành công |
| Client chủ động hủy | RPC kết thúc; server cần ngừng công việc và giải phóng tài nguyên |
| Deadline của RPC bị vượt quá | Client thường nhận **DEADLINE_EXCEEDED**; server có thể được thông báo hủy |
| Kết nối hoặc dịch vụ không khả dụng | Có thể nhận **UNAVAILABLE** hoặc lỗi vận chuyển tương ứng |

Client thiết lập deadline bằng **withDeadlineAfter(5, TimeUnit.SECONDS)** trong ví dụ. Deadline tính cho **toàn bộ RPC**, bao gồm thời gian gửi nhiều message, thời gian server xử lý và chờ response; nó không tự được làm mới mỗi khi gửi một Reading mới. Khi deadline hết, client có thể thấy lỗi dù server đã xử lý một phần dữ liệu.

Trong code xử lý lỗi phía client, có thể trích xuất gRPC status:

~~~java
import io.grpc.Status;

@Override
public void onError(Throwable error) {
    Status.Code code = Status.fromThrowable(error).getCode();
    // Ví dụ: INVALID_ARGUMENT, DEADLINE_EXCEEDED, UNAVAILABLE.
    // Ghi log hoặc ánh xạ sang lỗi phù hợp ở tầng ứng dụng.
    finished.countDown();
}
~~~

Đoạn trên minh họa cách đọc status trong callback; khi áp dụng vào client ở mục trước, vẫn cần giữ thao tác lưu **failure** nếu code phía sau muốn xử lý lỗi đó.

Nếu client quyết định hủy trước khi hoàn tất gửi, có thể gọi **requests.onError(...)** một lần để kết thúc luồng gửi phía client; cũng có thể hủy qua API gRPC phù hợp với kiểu call/stub đang dùng. Không gọi **requests.onCompleted()** tiếp sau hành động hủy.

**Retry** yêu cầu đặc biệt thận trọng: nếu kết nối đứt giữa luồng, client không mặc nhiên biết server đã nhận và lưu những message nào. Việc phát lại toàn bộ stream có thể gây ghi trùng. Để hỗ trợ truyền dữ liệu tin cậy, cần một thiết kế bổ sung: **upload ID / idempotency key** dùng chung cho RPC, số thứ tự message, cơ chế loại bỏ bản ghi trùng, kiểm tra kết quả trước khi gửi lại, hoặc API xác nhận/checkpoint riêng. gRPC client streaming không tự cung cấp giao dịch exactly-once cho nghiệp vụ.

## 6. Flow control, giới hạn tài nguyên và tính thứ tự

Client streaming hữu ích khi có nhiều message, nhưng không nên hiểu rằng ứng dụng có thể gửi một luồng vô hạn mà không quan tâm tài nguyên.

- gRPC chạy trên HTTP/2 với cơ chế **flow control**; API async **onNext** có thể ghi vào bộ đệm thay vì chờ message thực sự được vận chuyển. Khi stream lớn, client cần kiểm soát tốc độ gửi và kích thước hàng đợi.
- Với gRPC Java, **ClientCallStreamObserver.isReady()** và **setOnReadyHandler(...)** là các công cụ có thể dùng để phát dữ liệu theo khả năng nhận của transport. Việc sử dụng đúng cần cấu hình callback ở giai đoạn bắt đầu call (thường qua **ClientResponseObserver.beforeStart**). **isReady()** không phải là xác nhận server đã xử lý hoặc lưu bền message.
- Trong cùng một stream, gRPC duy trì **thứ tự message** đã được gửi theo trình tự. Nếu nhiều thread cùng ghi vào observer, ứng dụng phải tự xác lập thứ tự trước khi gửi.
- Server nên giới hạn **số message**, **kích thước mỗi message**, **thời gian xử lý** và **bộ nhớ sử dụng**. Ví dụ đã giới hạn số Reading; việc đặt giới hạn kích thước message thường được cấu hình ở server/channel hoặc tầng xử lý chung.
- Với tập dữ liệu lớn, nên xử lý tuần tự theo batch hoặc dùng staging, thay vì giữ toàn bộ message trong một **List** vô hạn.

Nếu mỗi Reading là một khoản tiền, không nên cộng bằng **double** như ví dụ đo lường: cần biểu diễn số tiền bằng đơn vị nhỏ nhất dạng số nguyên, hoặc kiểu thập phân phù hợp ở tầng nghiệp vụ.

## 7. Metadata, interceptor và TLS trong Spring gRPC

**Metadata** là thông tin ở cấp RPC, có thể dùng để mang request ID, tenant ID, upload ID hoặc thông tin xác thực. Nó được gửi cùng lời gọi, không phải dưới dạng một Reading mới cho mỗi message. Dữ liệu cảm biến và thứ tự đo nên nằm trong message Protobuf; thông tin chung của toàn luồng có thể đặt trong metadata hoặc một message bao dữ liệu được thiết kế rõ ràng.

**Client interceptor** có thể tự động gắn metadata và ghi nhận thời gian gửi; **server interceptor** có thể kiểm tra xác thực, phân quyền, tạo trace span và đo các chỉ số ở cấp RPC. Việc chỉ đếm số RPC thành công chưa đủ với client streaming: một RPC có thể chứa hàng nghìn Reading, vì vậy nên theo dõi thêm số message được nhận và kích thước dữ liệu.

Đối với hệ thống triển khai thực tế:

- Bảo vệ kết nối bằng **TLS**; dùng **mTLS** nếu cần xác thực dịch vụ hai chiều.
- Áp dụng xác thực và phân quyền tại ranh giới phù hợp, không tin tưởng **device_id** chỉ vì nó xuất hiện trong payload.
- Không ghi token, thông tin nhạy cảm hoặc toàn bộ dữ liệu lớn của stream vào log.
- Giới hạn số stream đồng thời và tổng tài nguyên theo client/tenant; kết hợp deadline để tránh các stream mở lâu không cần thiết.

**usePlaintext()** ở ví dụ client chỉ dành cho môi trường phát triển tin cậy. Tích hợp TLS, interceptor và policy cụ thể tùy starter Spring gRPC cùng cấu hình triển khai.

## 8. Kiểm thử tích hợp client streaming ở mức gRPC

Thay vì gọi trực tiếp từng callback trên server rồi giả lập thành công, có thể dùng **in-process server/channel** của gRPC Java. Cách này thực hiện đúng lời gọi qua stub, kiểm tra server nhận nhiều message và client nhận một response sau khi kết thúc request stream.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.telemetry.v1.Reading;
import vn.demo.grpc.telemetry.v1.TelemetryGrpc;
import vn.demo.grpc.telemetry.v1.UploadSummary;

class TelemetryServiceTest {

    @Test
    void clientStreamProducesOneAggregatedResponse() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new TelemetryService())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            CountDownLatch done = new CountDownLatch(1);
            AtomicReference<UploadSummary> summary =
                new AtomicReference<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();
            AtomicInteger replyCount = new AtomicInteger();

            var stub = TelemetryGrpc.newStub(channel)
                .withDeadlineAfter(3, TimeUnit.SECONDS);
            StreamObserver<Reading> requests = stub.uploadReadings(
                new StreamObserver<UploadSummary>() {
                    @Override
                    public void onNext(UploadSummary response) {
                        replyCount.incrementAndGet();
                        summary.set(response);
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

            requests.onNext(Reading.newBuilder()
                .setDeviceId("d1").setSequence(1).setValue(2.5).build());
            requests.onNext(Reading.newBuilder()
                .setDeviceId("d1").setSequence(2).setValue(3.0).build());
            requests.onCompleted();

            assertTrue(done.await(4, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(1, replyCount.get());
            assertNotNull(summary.get());
            assertEquals(2L, summary.get().getAcceptedCount());
            assertEquals(5.5, summary.get().getTotal(), 0.000001);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Test này cần **gRPC in-process** và JUnit phù hợp với các dependency của dự án. Để kiểm tra vòng đời Spring thật, bổ sung integration test khởi động Spring context và gRPC server, xác nhận bean service được đăng ký, interceptor chạy đúng và client nhận được phản hồi.

Các trường hợp kiểm thử nên bổ sung:

1. Gửi **0** Reading rồi kết thúc: nhận summary **0/0** theo quy tắc ví dụ.
2. Gửi Reading có **device_id** rỗng hoặc **value** không hợp lệ: client nhận **INVALID_ARGUMENT**, không có summary thành công.
3. Gửi **10.001** Reading: nhận **RESOURCE_EXHAUSTED**.
4. Hủy giữa chừng hoặc đặt deadline ngắn: server giải phóng trạng thái; không phát response thành công cho phần dữ liệu chưa hoàn tất.
5. Hai client stream chạy đồng thời: kết quả tổng hợp riêng, không bị lẫn state.
6. Với môi trường sản xuất: kiểm thử TLS, xác thực, chính sách retry/idempotency, giới hạn bộ nhớ và hành vi khi kết nối bị ngắt.

Giám sát nên thu thập **latency của toàn RPC**, **tỷ lệ thành công/lỗi theo status**, **số stream đang mở**, **message/bytes trên mỗi RPC**, độ trễ xử lý và **số lần bị hủy hoặc quá deadline**. Sự tăng đột biến của số stream mở lâu có thể cho thấy client quên kết thúc luồng hoặc server bị nghẽn xử lý.

## 9. Sai sót thường gặp và cách tránh

| Sai sót | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Quên **requests.onCompleted()** | Server có thể tiếp tục chờ luồng kết thúc; client không nhận summary đúng hạn | Half-close khi đã gửi hết message |
| Server gọi **responseObserver.onNext** cho mỗi Reading | Vi phạm hợp đồng một response của client streaming | Tổng hợp dữ liệu, trả đúng một summary |
| Dùng blocking stub để gửi client stream | Không có API gửi nhiều request message như mong muốn | Dùng async stub và request observer |
| Chia sẻ bộ đếm giữa các RPC | Dữ liệu của các client bị trộn | Lưu state trong observer riêng của từng lời gọi |
| Ghi observer từ nhiều thread không điều phối | Có thể phát sinh race hoặc sai thứ tự | Tuần tự hóa thao tác gửi |
| Không đặt deadline/giới hạn dung lượng | Stream có thể chiếm tài nguyên quá lâu | Deadline, quota, flow control |
| Tự retry từ đầu mà không chống trùng | Dữ liệu có thể được ghi nhiều lần | Upload ID, sequence, deduplication, checkpoint |
| Coi **onNext** là xác nhận lưu thành công | Tưởng dữ liệu đã bền vững khi nó mới được gửi/đệm | Chỉ xác nhận theo giao thức nghiệp vụ phù hợp |

## 10. Ghi nhớ và tự kiểm tra

**Cú pháp cốt lõi** của client streaming là:

~~~proto
rpc Upload(stream RequestMessage) returns (ResponseMessage);
~~~

Phía client, **async stub** trả về **StreamObserver<RequestMessage>** để gửi lần lượt nhiều message và kết thúc bằng **onCompleted()**. Phía server, phương thức triển khai trả về **StreamObserver<RequestMessage>** để nhận các message, xử lý state theo từng RPC và trả **một ResponseMessage** khi hoàn tất thành công. Khi có lỗi hoặc bị hủy, sử dụng cơ chế **gRPC status** và giải phóng tài nguyên hợp lý.

Tự kiểm tra bằng bốn câu hỏi:

1. Vì sao cần đặt **stream** trước kiểu **request** mà không đặt trước **response** khi định nghĩa client streaming?
2. Điều gì xảy ra nếu client gửi đủ 50 message nhưng không bao giờ gọi **onCompleted()**?
3. Nếu server lưu 20 message rồi kết nối đứt, tại sao retry nguyên luồng 50 message có thể gây trùng dữ liệu?
4. Khi nào nên chọn client streaming, khi nào nên chuyển sang bidirectional streaming để phản hồi theo từng message?

Khi hiểu rõ **hợp đồng Protobuf**, **vòng đời của hai observer** và **ngữ nghĩa hoàn tất/lỗi**, người học có thể triển khai client streaming RPC đáng tin cậy trong Spring gRPC và tiếp tục mở rộng sang streaming hai chiều, bảo mật và quan sát hệ thống.
