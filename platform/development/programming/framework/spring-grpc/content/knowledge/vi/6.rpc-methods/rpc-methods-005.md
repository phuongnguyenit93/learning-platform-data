# Request và response của từng loại method trong Spring gRPC

Một phương thức **RPC** (Remote Procedure Call) định nghĩa cách client gọi chức năng chạy trên server. Với **Spring gRPC**, hợp đồng giao tiếp được khai báo bằng **Protocol Buffers (.proto)**, sau đó công cụ sinh mã tạo các message Java, service base class và client stub. Bốn loại RPC của gRPC khác nhau chủ yếu ở **số lượng request message** mà client được gửi và **số lượng response message** mà server được trả về trong **một lần gọi RPC**.

Bài học này làm rõ request/response của **unary**, **server streaming**, **client streaming** và **bidirectional streaming**, cách biểu diễn bằng Protobuf, cách dùng các API gRPC Java trong ứng dụng Spring, và cách xử lý deadline, metadata, status, bảo mật, kiểm thử cùng các rủi ro khi triển khai.

## 1. Phân biệt RPC, message và luồng truyền

Trong một RPC, **request message** là dữ liệu ứng dụng gửi từ client sang server; **response message** là dữ liệu ứng dụng gửi từ server về client. Dữ liệu thường là đối tượng Protobuf đã được mã hóa nhị phân.

**Một RPC không tương đương một gói tin mạng.** gRPC thường dùng HTTP/2: một message có thể được chia thành nhiều frame, còn nhiều message có thể đi trong cùng một HTTP/2 stream. Vì vậy số request/response bên dưới là **số Protobuf message ở cấp gRPC**, không phải số packet hay frame.

| Loại method | Request trong một RPC | Response khi thành công | Cú pháp Protobuf |
| --- | --- | --- | --- |
| **Unary** | Chính xác 1 | Chính xác 1 | **rpc Get(Req) returns (Res);** |
| **Server streaming** | Chính xác 1 | 0 đến nhiều | **rpc Watch(Req) returns (stream Res);** |
| **Client streaming** | 0 đến nhiều | Chính xác 1 | **rpc Upload(stream Req) returns (Res);** |
| **Bidirectional streaming** | 0 đến nhiều | 0 đến nhiều | **rpc Exchange(stream Req) returns (stream Res);** |

**Lưu ý về thất bại:** số response trong bảng mô tả **lời gọi thành công**. Nếu RPC kết thúc bằng status lỗi (khác **OK**), client có thể không nhận được response thành công nào, hoặc với streaming có thể đã nhận **một phần** response trước khi lỗi xảy ra. Khi streaming request, một luồng rỗng có thể hợp lệ về mặt giao thức; tầng nghiệp vụ có thể yêu cầu ít nhất một message.

~~~mermaid
flowchart TD
    A["Một lời gọi gRPC"] --> B{"Client gửi một hay nhiều request?"}
    B -->|"Một"| C{"Server trả một hay nhiều response?"}
    B -->|"Nhiều"| D{"Server trả một hay nhiều response?"}
    C -->|"Một"| E["Unary"]
    C -->|"Nhiều"| F["Server streaming"]
    D -->|"Một"| G["Client streaming"]
    D -->|"Nhiều"| H["Bidirectional streaming"]
~~~

## 2. Ví dụ hợp đồng Protobuf có đủ bốn loại method

Giả sử ứng dụng theo dõi thiết bị. Client có thể xem mẫu đo mới nhất, theo dõi cập nhật, tải lên một lô mẫu hoặc trao đổi tín hiệu điều khiển hai chiều. File **src/main/proto/telemetry.proto**:

~~~proto
syntax = "proto3";

package demo.telemetry.v1;

option java_package = "vn.demo.grpc.telemetry.v1";
option java_multiple_files = true;
option java_outer_classname = "TelemetryProto";

service TelemetryService {
  // Một request -> một response.
  rpc GetLatest(ReadingQuery) returns (Reading);

  // Một request -> luồng response.
  rpc Watch(ReadingQuery) returns (stream Reading);

  // Luồng request -> một response.
  rpc Upload(stream Reading) returns (UploadSummary);

  // Luồng request <-> luồng response.
  rpc Exchange(stream ClientSignal) returns (stream ServerSignal);
}

message ReadingQuery {
  string device_id = 1;
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

message ClientSignal {
  string device_id = 1;
  int64 client_sequence = 2;
  string payload = 3;
}

message ServerSignal {
  int64 client_sequence = 1;
  string payload = 2;
}
~~~

Từ khóa **stream** đặt trước kiểu request hay response **quyết định chiều nào nhận nhiều message**. Phương thức không có từ khóa đó ở cả hai phía là unary. Các kiểu như **Reading** hay **UploadSummary** chỉ mô tả **cấu trúc của một message**; bản thân message không quyết định số lần nó xuất hiện trong RPC.

Sau khi cấu hình **protoc** và plugin gRPC Java cho bản build, mã sinh thường chứa:

- **ReadingQuery**, **Reading**, **UploadSummary**, **ClientSignal**, **ServerSignal**: các lớp Protobuf.
- **TelemetryServiceGrpc.TelemetryServiceImplBase**: lớp nền triển khai service phía server.
- **TelemetryServiceGrpc.TelemetryServiceBlockingStub**: tiện cho unary và server streaming đồng bộ.
- **TelemetryServiceGrpc.TelemetryServiceStub**: async stub sử dụng **StreamObserver**, hỗ trợ cả bốn loại method, đặc biệt là client/bidirectional streaming.
- **TelemetryServiceGrpc.TelemetryServiceFutureStub**: hỗ trợ lời gọi unary trả kết quả dạng future; không phải API gửi luồng request.

Tất cả ví dụ trong bài giả định ứng dụng Spring đã có dependency Spring gRPC, cấu hình sinh mã Protobuf và khả năng đăng ký các bean triển khai **BindableService**. Tên cấu hình, cách tạo channel hoặc đăng ký service có thể thay đổi theo phiên bản starter; ý nghĩa contract và API gRPC Java là các khái niệm cốt lõi.

## 3. Unary: một request và một response

Khai báo:

~~~proto
rpc GetLatest(ReadingQuery) returns (Reading);
~~~

Trong một lời gọi **GetLatest**, client gửi **đúng một ReadingQuery**; server trả **đúng một Reading** nếu thành công. Không có stream request/response ở cấp API ứng dụng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: GetLatest(ReadingQuery)
    S-->>C: Reading
    S-->>C: status OK
~~~

Ví dụ sử dụng **blocking stub**:

~~~java
ReadingQuery query = ReadingQuery.newBuilder()
    .setDeviceId("sensor-01")
    .build();

Reading response = blockingStub.getLatest(query);
System.out.println(response.getValue());
~~~

Phương thức server được sinh có dạng:

~~~java
public void getLatest(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);
~~~

Server triển khai đúng một lời gọi **responseObserver.onNext(reading)**, sau đó **responseObserver.onCompleted()**. Nếu không thể trả kết quả, server dùng **onError(Status...asRuntimeException())** thay vì trả một Reading giả có thông báo lỗi nằm trong trường giá trị.

Unary phù hợp với truy vấn một bản ghi, tính giá hoặc yêu cầu thao tác ngắn có một kết quả cuối. Một response unary vẫn có thể chứa nhiều phần tử nếu message có trường **repeated**; số phần tử bên trong một message **khác** số response message của RPC.

## 4. Server streaming: một request và nhiều response

Khai báo:

~~~proto
rpc Watch(ReadingQuery) returns (stream Reading);
~~~

Client gửi **một ReadingQuery** để đăng ký theo dõi; server phát **0 đến N Reading** theo thời gian rồi kết thúc stream. Server có thể gửi message ngay khi dữ liệu xuất hiện; không cần chờ đủ một danh sách trước khi phản hồi.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Watch(ReadingQuery)
    S-->>C: Reading(sequence=1)
    S-->>C: Reading(sequence=2)
    S-->>C: Reading(sequence=3)
    S-->>C: status OK sau onCompleted
~~~

Với **blocking stub**, gRPC Java thường trả về **Iterator<Reading>**:

~~~java
ReadingQuery query = ReadingQuery.newBuilder()
    .setDeviceId("sensor-01")
    .build();

Iterator<Reading> stream = blockingStub.watch(query);
while (stream.hasNext()) {
    Reading reading = stream.next();
    System.out.println(reading.getSequence() + ": " +
        reading.getValue());
}
~~~

**hasNext()** và **next()** có thể chặn để đợi dữ liệu. Nếu server kết thúc bằng lỗi ở giữa luồng, việc duyệt iterator có thể ném **StatusRuntimeException**; cần bắt lỗi xung quanh cả vòng lặp, không chỉ lúc tạo iterator.

Chữ ký server:

~~~java
public void watch(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);
~~~

Server có thể gọi **responseObserver.onNext(reading)** nhiều lần, cuối cùng gọi **onCompleted()**, hoặc gọi **onError(...)** nếu thất bại. Client không có API gửi request tiếp theo trong cùng method Watch vì chiều request không được khai báo **stream**. Nếu cần thay đổi bộ lọc liên tục trong lúc nhận dữ liệu, cân nhắc bidirectional streaming.

## 5. Client streaming: nhiều request và một response

Khai báo:

~~~proto
rpc Upload(stream Reading) returns (UploadSummary);
~~~

Client gửi **một chuỗi Reading** trong cùng một RPC; server tổng hợp và trả **một UploadSummary** khi xử lý thành công.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Mở Upload
    C->>S: Reading 1
    C->>S: Reading 2
    C->>S: Reading 3
    C->>S: requestObserver.onCompleted()
    S-->>C: UploadSummary
    S-->>C: status OK
~~~

Phía Java client, **async stub** nhận observer xử lý response và **trả về request observer**:

~~~java
StreamObserver<Reading> requests = asyncStub.upload(
    new StreamObserver<UploadSummary>() {
        @Override
        public void onNext(UploadSummary summary) {
            System.out.println(
                "Accepted: " + summary.getAcceptedCount());
        }

        @Override
        public void onError(Throwable error) {
            System.err.println(
                Status.fromThrowable(error).getCode());
        }

        @Override
        public void onCompleted() {
            System.out.println("Upload finished");
        }
    });

requests.onNext(Reading.newBuilder()
    .setDeviceId("sensor-01")
    .setSequence(1)
    .setValue(10.5)
    .build());
requests.onNext(Reading.newBuilder()
    .setDeviceId("sensor-01")
    .setSequence(2)
    .setValue(11.5)
    .build());
requests.onCompleted();
~~~

Trên server, method có dạng:

~~~java
public StreamObserver<Reading> upload(
    StreamObserver<UploadSummary> responseObserver);
~~~

Server **trả về observer** có **onNext(Reading)** để nhận từng request. Khi **onCompleted()** được gọi trên observer nhận request, server thường hoàn thành tổng hợp, gửi một **UploadSummary** và gọi **responseObserver.onCompleted()**. Nếu có lỗi, server kết thúc bằng **responseObserver.onError(...)**.

Hành động **requests.onCompleted()** phía client là **half-close** chiều gửi: client không gửi message tiếp nhưng vẫn tiếp tục **nhận** phản hồi. Trong ví dụ server đợi client half-close rồi tổng hợp; về mặt API server có thể kết thúc lỗi trước khi nhận xong mọi request.

**Lưu ý:** một luồng request rỗng có thể hợp lệ về mặt gRPC. Nếu Upload yêu cầu ít nhất một Reading, server phải chủ động kiểm tra số lượng và trả **INVALID_ARGUMENT** khi không có message; Protobuf không tự áp đặt quy tắc đó.

## 6. Bidirectional streaming: nhiều request và nhiều response

Khai báo:

~~~proto
rpc Exchange(stream ClientSignal) returns (stream ServerSignal);
~~~

Client và server đều có thể gửi **0 đến N message** trong một RPC. Server có thể phản hồi giữa lúc client vẫn gửi; hai chiều độc lập về nhịp độ và số lượng message.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: Mở Exchange
    C->>S: ClientSignal 1
    S-->>C: ServerSignal A
    S-->>C: ServerSignal B
    C->>S: ClientSignal 2
    C->>S: ClientSignal 3
    S-->>C: ServerSignal C
    C->>S: requestObserver.onCompleted()
    S-->>C: ServerSignal D
    S-->>C: status OK
~~~

Giống client streaming, **async stub** trả request observer và nhận response observer:

~~~java
StreamObserver<ClientSignal> requests = asyncStub.exchange(
    new StreamObserver<ServerSignal>() {
        @Override
        public void onNext(ServerSignal response) {
            System.out.println(
                response.getClientSequence() + ": " +
                response.getPayload());
        }

        @Override
        public void onError(Throwable error) {
            System.err.println(
                Status.fromThrowable(error).getCode());
        }

        @Override
        public void onCompleted() {
            System.out.println("Exchange finished");
        }
    });

requests.onNext(ClientSignal.newBuilder()
    .setDeviceId("sensor-01")
    .setClientSequence(1)
    .setPayload("request-calibration")
    .build());

// Có thể tiếp tục nhận response trước khi kết thúc chiều gửi.
requests.onCompleted();
~~~

Phía server, method có dạng:

~~~java
public StreamObserver<ClientSignal> exchange(
    StreamObserver<ServerSignal> responseObserver);
~~~

Trong **onNext(ClientSignal)** của request observer, server có thể phát **0, 1 hoặc nhiều ServerSignal** qua **responseObserver.onNext(...)**. Khi client half-close, server có thể gửi nốt dữ liệu còn lại rồi **onCompleted()**, hoặc kết thúc bằng **onError(...)** nếu xảy ra lỗi.

**Không được suy ra response thứ N tương ứng request thứ N.** Nếu nghiệp vụ cần ghép cặp, hãy thiết kế **correlation ID** hoặc **client_sequence**. Mỗi chiều giữ thứ tự của riêng mình, nhưng không có thứ tự toàn cục giữa hai chiều. Khi cần xác nhận server đã lưu bền dữ liệu, phải quy định rõ ý nghĩa của một response xác nhận; việc gọi hoặc nhận **onNext** không tự đồng nghĩa lưu bền.

## 7. Tổng hợp chữ ký Java và callback của từng kiểu

Phía server gRPC Java sinh phương thức theo hai mẫu:

- **Unary và server streaming:** nhận **một request object** cộng một **response StreamObserver**, trả **void**.
- **Client và bidirectional streaming:** nhận **response StreamObserver**, trả về **request StreamObserver** để tiếp nhận nhiều request.

Ví dụ bốn chữ ký trong **TelemetryServiceGrpc.TelemetryServiceImplBase**:

~~~java
// Unary: 1 request -> 1 response.
public void getLatest(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);

// Server streaming: 1 request -> nhiều response.
public void watch(
    ReadingQuery request,
    StreamObserver<Reading> responseObserver);

// Client streaming: nhiều request -> 1 response.
public StreamObserver<Reading> upload(
    StreamObserver<UploadSummary> responseObserver);

// Bidirectional streaming: nhiều request -> nhiều response.
public StreamObserver<ClientSignal> exchange(
    StreamObserver<ServerSignal> responseObserver);
~~~

Mẫu **response StreamObserver** xuất hiện ở cả bốn kiểu RPC, nhưng cách dùng khác nhau:

| Method | Server gọi **response.onNext(...)** | Server gọi **response.onCompleted()** |
| --- | --- | --- |
| Unary | Đúng một lần khi thành công | Sau response đơn |
| Server streaming | 0 đến nhiều lần | Khi không còn response |
| Client streaming | Đúng một lần khi thành công | Sau summary đơn |
| Bidirectional streaming | 0 đến nhiều lần | Khi kết thúc chiều phản hồi |

Phía client, có thể ghi nhớ cách sử dụng stub:

| Method | Blocking stub | Async stub |
| --- | --- | --- |
| **GetLatest** | Trả trực tiếp **Reading** | Nhận **StreamObserver<Reading>** để nhận một kết quả |
| **Watch** | Trả **Iterator<Reading>** | Nhận **StreamObserver<Reading>** để nhận nhiều kết quả |
| **Upload** | Không có API blocking để phát nhiều request theo cách này | Trả **StreamObserver<Reading>** để client gửi request |
| **Exchange** | Không có API blocking hai chiều tương ứng trong blocking stub thông dụng | Trả **StreamObserver<ClientSignal>** để client gửi, và dùng callback để nhận |

Các đoạn code phía trên dùng biến **blockingStub** và **asyncStub** đã được tạo từ channel, ví dụ:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("localhost", 9090)
    .usePlaintext()
    .build();

var blockingStub = TelemetryServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(3, TimeUnit.SECONDS);
var asyncStub = TelemetryServiceGrpc.newStub(channel)
    .withDeadlineAfter(3, TimeUnit.SECONDS);

// Tái sử dụng channel cho nhiều RPC.
// Đóng channel khi kết thúc vòng đời ứng dụng.
~~~

Trong ứng dụng Spring thực tế, nên lấy địa chỉ từ cấu hình và dùng bean/channel/stub được quản lý phù hợp phiên bản Spring gRPC đang sử dụng. **usePlaintext()** chỉ phù hợp môi trường local/dev tin cậy; hệ thống sản xuất cần cấu hình **TLS** và xác thực thích hợp.

## 8. Một service server minh họa đủ bốn phương thức

Ví dụ đơn giản sau cho thấy **sự khác nhau trong cách server xử lý request và phát response**. Dữ liệu được tạo tại chỗ để tập trung vào luồng RPC; trong dự án thật, thay thế bằng dịch vụ nghiệp vụ, xác thực và lưu trữ phù hợp:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.telemetry.v1.*;

@Service
public class TelemetryServiceImpl
        extends TelemetryServiceGrpc.TelemetryServiceImplBase {

    @Override
    public void getLatest(
            ReadingQuery query,
            StreamObserver<Reading> responses) {
        if (query.getDeviceId().isBlank()) {
            responses.onError(Status.INVALID_ARGUMENT
                .withDescription("device_id is required")
                .asRuntimeException());
            return;
        }

        responses.onNext(Reading.newBuilder()
            .setDeviceId(query.getDeviceId())
            .setSequence(3)
            .setValue(12.5)
            .build());
        responses.onCompleted();
    }

    @Override
    public void watch(
            ReadingQuery query,
            StreamObserver<Reading> responses) {
        if (query.getDeviceId().isBlank()) {
            responses.onError(Status.INVALID_ARGUMENT
                .withDescription("device_id is required")
                .asRuntimeException());
            return;
        }

        for (int seq = 1; seq <= 3; seq++) {
            responses.onNext(Reading.newBuilder()
                .setDeviceId(query.getDeviceId())
                .setSequence(seq)
                .setValue(seq * 1.5)
                .build());
        }
        responses.onCompleted();
    }

    @Override
    public StreamObserver<Reading> upload(
            StreamObserver<UploadSummary> responses) {
        return new StreamObserver<>() {
            private long count;
            private double total;
            private boolean ended;

            @Override
            public void onNext(Reading reading) {
                if (ended) return;
                if (reading.getDeviceId().isBlank()
                        || !Double.isFinite(reading.getValue())) {
                    ended = true;
                    responses.onError(Status.INVALID_ARGUMENT
                        .withDescription("invalid reading")
                        .asRuntimeException());
                    return;
                }
                count++;
                total += reading.getValue();
            }

            @Override
            public void onError(Throwable error) {
                ended = true; // Bỏ dữ liệu tổng hợp chưa hoàn tất.
            }

            @Override
            public void onCompleted() {
                if (ended) return;
                ended = true;
                responses.onNext(UploadSummary.newBuilder()
                    .setAcceptedCount(count)
                    .setTotal(total)
                    .build());
                responses.onCompleted();
            }
        };
    }

    @Override
    public StreamObserver<ClientSignal> exchange(
            StreamObserver<ServerSignal> responses) {
        return new StreamObserver<>() {
            private boolean ended;

            @Override
            public void onNext(ClientSignal signal) {
                if (ended) return;
                if (signal.getDeviceId().isBlank()) {
                    ended = true;
                    responses.onError(Status.INVALID_ARGUMENT
                        .withDescription("device_id is required")
                        .asRuntimeException());
                    return;
                }
                // Ví dụ trả một phản hồi cho mỗi tín hiệu.
                responses.onNext(ServerSignal.newBuilder()
                    .setClientSequence(signal.getClientSequence())
                    .setPayload("received: " + signal.getPayload())
                    .build());
            }

            @Override
            public void onError(Throwable error) {
                ended = true;
            }

            @Override
            public void onCompleted() {
                if (ended) return;
                ended = true;
                responses.onCompleted();
            }
        };
    }
}
~~~

Mỗi lời gọi **Upload** hoặc **Exchange** tạo **request observer và trạng thái riêng**. Không đặt các bộ đếm của một stream trong field mutable của service singleton, vì nhiều RPC đồng thời có thể trộn dữ liệu.

Phương thức **Watch** ở đây gửi ba kết quả rồi hoàn tất; nếu dữ liệu đến liên tục, server cần gửi theo sự kiện và xử lý cancel/flow control. Đừng chạy vòng lặp vô hạn phát **onNext** liên tục. Mã minh họa không thực hiện cơ sở dữ liệu hay I/O ngoài nên chưa giải quyết toàn bộ vấn đề concurrency, transaction và shutdown trong production.

## 9. Kết thúc bình thường, lỗi và deadline

### Khi nào một RPC thật sự hoàn thành?

- Với **unary**, server gửi một response rồi kết thúc bằng **onCompleted()**.
- Với **server streaming**, server gửi 0 đến nhiều response rồi gọi **onCompleted()**.
- Với **client streaming**, client phải báo **requestObserver.onCompleted()** để half-close khi đã gửi hết request; server sau đó có thể trả một kết quả tổng hợp và hoàn thành.
- Với **bidirectional streaming**, client có thể half-close chiều request, nhưng vẫn nhận các response cho đến khi server kết thúc chiều phản hồi. Server cũng có thể kết thúc sớm theo giao thức nghiệp vụ.

**onCompleted()** trên observer nhận/gửi là sự kiện ở cấp **message stream**; status gRPC **OK** được gửi khi server kết thúc lời gọi thành công. Khi có lỗi, bên kết thúc RPC dùng **onError(...)**, phía kia có thể nhận **StatusRuntimeException** hoặc callback **onError(Throwable)**. Sau callback kết thúc, không được phát thêm message vào observer đó.

### Trạng thái lỗi thường dùng

| Status | Ví dụ áp dụng | Hướng xử lý |
| --- | --- | --- |
| **INVALID_ARGUMENT** | Query thiếu device ID; Reading sai giá trị | Sửa input, không retry nguyên trạng |
| **NOT_FOUND** | Unary GetLatest không tìm thấy thiết bị | Xử lý không tồn tại |
| **UNAUTHENTICATED** | Thiếu credential | Xác thực lại |
| **PERMISSION_DENIED** | Không có quyền đọc/gửi dữ liệu thiết bị | Kiểm tra quyền |
| **RESOURCE_EXHAUSTED** | Stream vượt quota/bộ đệm | Giảm tải, xem giới hạn |
| **DEADLINE_EXCEEDED** | RPC không kết thúc trước hạn | Kiểm tra trạng thái tác vụ và ngân sách thời gian |
| **CANCELLED** | Lời gọi bị hủy | Giải phóng tài nguyên |
| **UNAVAILABLE** | Không thể kết nối hoặc dịch vụ tạm ngưng | Retry có kiểm soát nếu an toàn |
| **INTERNAL** | Lỗi nội bộ server | Ghi log/trace an toàn để điều tra |

**Deadline** áp dụng cho **cả RPC**, không phải từng message. Nếu client streaming gửi 100 Reading trong 5 giây, thời gian chờ phản hồi cũng nằm trong chính deadline đó. Nếu server streaming mở lâu, deadline có thể hết trước khi server gửi đủ dữ liệu. Client có thể dùng:

~~~java
var timedStub = TelemetryServiceGrpc.newStub(channel)
    .withDeadlineAfter(5, TimeUnit.SECONDS);
~~~

Khi client nhận **DEADLINE_EXCEEDED** hoặc mất kết nối, **không thể mặc định rằng server chưa xử lý message nào**. Đặc biệt với các RPC ghi dữ liệu, retry có thể làm trùng tác động. Hãy bổ sung **idempotency key / upload ID**, mã message và cơ chế chống trùng nếu cần khôi phục.

## 10. Metadata, thứ tự, flow control và bảo mật

### Metadata thuộc một RPC, không phải một message

**Metadata** thường mang authorization token, request ID, tenant ID hoặc trace context. Nó là thông tin của **lời gọi** và được gửi qua header/trailer của gRPC, không tự động thay đổi theo từng message trong luồng. Các dữ liệu nghiệp vụ khác nhau theo message nên thuộc các field Protobuf.

**Interceptor** client/server có thể thêm/đọc metadata, xác thực, tạo trace và thống kê status/latency theo method. Với streaming, cần theo dõi cả **số message/byte** và **số stream đang mở** vì một RPC có thể truyền hàng nghìn message.

### Thứ tự và tương quan request/response

gRPC duy trì thứ tự message **trong cùng một chiều stream**. Tuy vậy:

- **Unary:** chỉ một request và một response, dễ tương quan qua chính lời gọi.
- **Server streaming:** nhiều response đều thuộc một request mở stream, nhưng có thể mang nhiều bản ghi/timestamp.
- **Client streaming:** nhiều request cùng đóng góp một response tổng hợp; không có xác nhận độc lập cho từng request trừ khi nghiệp vụ thiết kế thêm.
- **Bidirectional:** hai chiều có thứ tự riêng; một request có thể tạo 0, 1 hoặc nhiều response. Dùng **correlation ID/sequence** khi cần ghép cặp.

Không xem lời gọi **onNext()** trả về là xác nhận dữ liệu đã được ghi bền. Nếu có yêu cầu giao dịch, deduplication hoặc xác nhận từng message, phải thiết kế cơ chế này ở tầng ứng dụng.

### Flow control và giới hạn tài nguyên

HTTP/2 và gRPC có **flow control**, nhưng ứng dụng vẫn cần giới hạn số lượng message, kích thước message, bộ nhớ đệm và số stream đồng thời. Trong gRPC Java, **ClientCallStreamObserver** và **ServerCallStreamObserver** có **isReady()** và **setOnReadyHandler(...)**; callback **ClientResponseObserver.beforeStart(...)** hỗ trợ cài đặt cơ chế gửi theo readiness cho async client streaming.

**StreamObserver không mặc nhiên thread-safe**: nếu nhiều thread cùng phát message vào một observer, cần tuần tự hóa các lệnh **onNext/onCompleted/onError**. Khi xử lý bất đồng bộ, tránh các callback chặn lâu và không duy trì hàng đợi vô hạn. **isReady()** chỉ cho biết trạng thái có thể ghi theo transport, không phải xác nhận server đã xử lý nghiệp vụ.

### TLS và phân quyền

Trong production cần **TLS** cho kênh truyền; cân nhắc **mTLS** giữa các dịch vụ. Xác thực/ủy quyền phải được kiểm tra tại ranh giới tin cậy, không dựa vào chuỗi **device_id** do client tự khai. Không ghi token, dữ liệu nhạy cảm hoặc toàn bộ payload stream vào log.

## 11. Kiểm thử request/response đúng theo từng method

Thay vì chỉ gọi trực tiếp phương thức Java, nên dùng gRPC **in-process server/channel** hoặc một integration test chạy Spring context để xác nhận kiểu request/response qua stub sinh mã. Bảng test tối thiểu:

| Method | Test thành công | Test lỗi quan trọng |
| --- | --- | --- |
| **GetLatest** | Một query trả đúng một Reading | device ID rỗng → INVALID_ARGUMENT |
| **Watch** | Một query nhận đúng 3 Reading và kết thúc | Query sai → INVALID_ARGUMENT; lỗi giữa stream |
| **Upload** | Hai Reading cho summary count=2, total đúng | Reading sai → INVALID_ARGUMENT; stream rỗng theo chính sách |
| **Exchange** | Hai ClientSignal nhận nhiều ServerSignal, chiều nhận hoạt động trước half-close | Tín hiệu sai; client hủy hoặc hết deadline |

Một ví dụ kiểm thử hai chiều đơn giản bằng gRPC in-process:

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
import vn.demo.grpc.telemetry.v1.*;

class TelemetryRpcContractTest {

    @Test
    void exchangeAcceptsMultipleRequestsAndResponses()
            throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new TelemetryServiceImpl())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(name)
            .directExecutor()
            .build();
        try {
            List<ServerSignal> responses =
                new CopyOnWriteArrayList<>();
            AtomicReference<Throwable> failure =
                new AtomicReference<>();
            CountDownLatch finished = new CountDownLatch(1);

            var stub = TelemetryServiceGrpc.newStub(channel)
                .withDeadlineAfter(3, TimeUnit.SECONDS);
            StreamObserver<ClientSignal> requests = stub.exchange(
                new StreamObserver<ServerSignal>() {
                    @Override
                    public void onNext(ServerSignal response) {
                        responses.add(response);
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
                });

            requests.onNext(ClientSignal.newBuilder()
                .setDeviceId("sensor-01")
                .setClientSequence(1)
                .setPayload("ping")
                .build());
            requests.onNext(ClientSignal.newBuilder()
                .setDeviceId("sensor-01")
                .setClientSequence(2)
                .setPayload("status")
                .build());
            requests.onCompleted();

            assertTrue(finished.await(4, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(2, responses.size());
            assertEquals(1L, responses.get(0).getClientSequence());
            assertEquals("received: status",
                responses.get(1).getPayload());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Đoạn test cần JUnit và dependency **gRPC in-process** tương ứng. Nó xác minh luồng message qua gRPC Java, chưa chứng minh Spring tự động đăng ký bean hoặc TLS/interceptor được cấu hình chính xác. Để kiểm tra tích hợp Spring gRPC thật, nên có integration test khởi động Spring context và server theo cấu hình test.

Khi cần kiểm thử hiệu năng, theo dõi **latency theo method**, tỷ lệ **status OK/lỗi**, p95/p99, message/byte theo chiều, thời gian sống của stream, luồng đang mở, tình trạng hủy và deadline. Đặc biệt, một method streaming có ít RPC nhưng rất nhiều message, vì vậy chỉ đếm số RPC sẽ bỏ sót tải thực tế.

## 12. Cách chọn loại method và những sai lầm cần tránh

| Nhu cầu | Chọn method | Vì sao |
| --- | --- | --- |
| Lấy số đo mới nhất theo ID | **Unary** | Một truy vấn, một kết quả |
| Theo dõi số đo được cập nhật liên tục | **Server streaming** | Một yêu cầu đăng ký, nhiều phản hồi |
| Gửi lô mẫu đo và nhận số lượng đã chấp nhận | **Client streaming** | Nhiều request, một phản hồi tổng hợp |
| Thiết bị gửi tín hiệu và đồng thời nhận lệnh | **Bidirectional streaming** | Cả hai phía cần phát dữ liệu liên tục |

Những sai sót dễ gặp:

1. **Nhầm số field trong message với số message của RPC.** Một unary response có thể chứa trường **repeated**, nhưng vẫn chỉ là một response message.
2. **Quên từ khóa stream.** Thiếu **stream** ở một chiều làm thay đổi loại RPC và chữ ký Java được sinh.
3. **Chọn streaming cho mọi thao tác.** Streaming mang thêm trách nhiệm quản lý vòng đời, flow control và timeout; unary thường dễ kiểm thử hơn cho thao tác ngắn.
4. **Gọi onCompleted quá sớm hoặc không gọi.** Client streaming có thể chờ vô hạn nếu client không half-close; đóng quá sớm làm mất dữ liệu chưa gửi.
5. **Giả định mỗi request streaming có một response tương ứng.** Với bidirectional, cần quy tắc tương quan rõ; với client streaming, kết quả thường tổng hợp toàn luồng.
6. **Không xử lý lỗi giữa stream.** Streaming có thể trả một phần dữ liệu rồi thất bại; client cần phân biệt phần đã nhận với trạng thái RPC cuối cùng.
7. **Retry không kiểm soát.** RPC lỗi có thể đã tạo tác dụng phụ; phải thiết kế chống trùng và cơ chế khôi phục theo nghiệp vụ.
8. **Không đặt giới hạn bộ nhớ và độ dài stream.** Một stream dài có thể làm cạn tài nguyên server/client.

## 13. Ghi nhớ và tự kiểm tra

Quy tắc đọc hợp đồng Protobuf rất ngắn gọn:

~~~proto
rpc Unary(Request) returns (Response);
rpc ServerStream(Request) returns (stream Response);
rpc ClientStream(stream Request) returns (Response);
rpc BidiStream(stream Request) returns (stream Response);
~~~

Hãy nhìn **vị trí của từ khóa stream** để biết ai được gửi nhiều message. Các dữ liệu được gửi đều là **Protobuf message**; server/client trong gRPC Java tương tác thông qua stub, **StreamObserver** và callback kết thúc. Với mỗi RPC, cần xử lý đúng status, deadline, hủy, bảo mật và giới hạn tài nguyên.

Tự trả lời các câu hỏi sau:

1. Nếu unary response chứa một trường **repeated Reading** với 100 phần tử, đó là một response hay 100 response message?
2. Vì sao server streaming không cho phép client gửi thêm bộ lọc sau khi mở RPC, trừ khi thiết kế một lời gọi khác?
3. Trong client streaming, tại sao client phải gọi **requests.onCompleted()** sau khi gửi xong các Reading?
4. Với bidirectional streaming, điều gì bảo đảm một response tương ứng đúng một request? Nếu chưa có, cần bổ sung gì trong schema?
5. Nếu client đã nhận vài response rồi gặp **UNAVAILABLE**, có nên coi RPC hoàn tất thành công không? Nếu muốn retry, cần kiểm tra điều gì?

Phân biệt đúng **số lượng và chiều của request/response trong mỗi method** là nền tảng để thiết kế hợp đồng Protocol Buffers hợp lý, triển khai client/server Spring gRPC hiệu quả và vận hành dịch vụ ổn định.
