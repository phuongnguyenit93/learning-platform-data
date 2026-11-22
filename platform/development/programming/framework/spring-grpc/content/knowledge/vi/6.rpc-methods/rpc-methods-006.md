# Chọn loại RPC theo luồng dữ liệu trong Spring gRPC

Trong **Spring gRPC**, trước khi viết một phương thức dịch vụ, cần trả lời câu hỏi: **Dữ liệu sẽ đi qua client và server như thế nào trong một lần gọi?** Câu trả lời quyết định nên dùng **unary**, **server streaming**, **client streaming** hay **bidirectional streaming RPC**. Lựa chọn này ảnh hưởng đến hợp đồng **Protocol Buffers**, mã Java do gRPC sinh ra, vòng đời client/server, cách kiểm thử, deadline, xử lý lỗi và chi phí vận hành.

Không nên chọn streaming chỉ vì muốn xử lý nhiều bản ghi hoặc vì dữ liệu có kích thước lớn. Một message Protobuf có thể chứa nhiều phần tử; ngược lại, streaming hữu ích khi các message cần xuất hiện **theo thời gian**, có thể được xử lý **từng phần**, hoặc khi **hai phía cần tương tác liên tục**. Bài này đưa ra cách quyết định dựa trên luồng dữ liệu và các yêu cầu nghiệp vụ, kèm ví dụ triển khai trong Java/Spring.

## 1. Bắt đầu từ hình dạng luồng dữ liệu

Mỗi method gRPC có hai hướng:

- **Request:** client → server.
- **Response:** server → client.

Với mỗi hướng, xác định bên gửi cần phát **một message** hay **một chuỗi message**. Từ đó có bốn hình dạng:

| Loại RPC | Luồng request | Luồng response khi thành công | Đặc điểm quyết định |
| --- | --- | --- | --- |
| **Unary** | 1 message | 1 message | Một lần hỏi/ra lệnh, một kết quả |
| **Server streaming** | 1 message | 0..N message | Client hỏi/đăng ký một lần; server phát kết quả dần dần |
| **Client streaming** | 0..N message | 1 message | Client gửi dữ liệu dần dần; server trả kết quả tổng hợp/cuối cùng |
| **Bidirectional streaming** | 0..N message | 0..N message | Hai bên trao đổi nhiều message và có thể hoạt động đồng thời |

Các con số là **số lượng Protobuf message trong một RPC**, không phải số TCP packet hay HTTP/2 frame. Với streaming, trường hợp 0 message có thể hợp lệ ở mức giao thức; server có thể yêu cầu ít nhất một message theo quy tắc nghiệp vụ. Với unary, một lời gọi thành công có đúng một request và một response; lời gọi lỗi có thể không có response ứng dụng.

~~~mermaid
flowchart TD
    A["Nhu cầu trao đổi dữ liệu"] --> B{"Client có cần gửi nhiều message trong cùng RPC?"}
    B -->|"Không"| C{"Server có cần phát nhiều message theo thời gian?"}
    B -->|"Có"| D{"Server có cần gửi nhiều phản hồi?"}
    C -->|"Không"| E["Unary"]
    C -->|"Có"| F["Server streaming"]
    D -->|"Không"| G["Client streaming"]
    D -->|"Có"| H["Bidirectional streaming"]
~~~

Sơ đồ là bước lọc đầu tiên. Sau đó cần hỏi thêm: dữ liệu có thực sự cần **truyền liên tục** không, kết quả có cần đến **trước khi gửi hết** không, client có thể **tái kết nối** như thế nào, và mức độ phức tạp thêm của streaming có đem lại lợi ích đo được không.

## 2. Năm câu hỏi chọn loại RPC

### Câu hỏi 1: Có cần trả kết quả trước khi hoàn tất toàn bộ công việc?

Ví dụ truy vấn **trạng thái hiện tại của một thiết bị** trả về một đối tượng nhỏ: **unary**. Truy vấn cần **theo dõi những thay đổi trạng thái trong 30 giây**, server có thể gửi update khi xuất hiện: **server streaming**.

Nếu dữ liệu có 100 phần tử nhưng dễ tạo xong và đóng gói gọn trong một message có trường **repeated**, unary có thể phù hợp. Nếu muốn nhận hàng triệu phần tử dần dần, tránh đợi toàn bộ kết quả và tránh giữ toàn bộ danh sách trong RAM, ưu tiên server streaming hoặc unary có phân trang theo từng trang.

### Câu hỏi 2: Client tạo dữ liệu một lần hay tạo liên tục?

Nếu client có sẵn một payload nhỏ và chỉ muốn server xử lý rồi phản hồi: **unary**. Nếu client tạo nhiều bản ghi theo thời gian, muốn gửi dần để server kiểm tra/tổng hợp và chỉ cần một kết quả sau cùng: **client streaming**.

Ví dụ: agent ghi nhận 10.000 giá trị nhiệt độ rồi gửi cho server. Nếu các giá trị đã có sẵn và gộp vào một message nhỏ là hợp lý, unary batch đơn giản hơn. Nếu giá trị được sinh liên tục hoặc không muốn giữ hết trong bộ nhớ, client streaming có lợi hơn.

### Câu hỏi 3: Client có cần điều chỉnh hành vi dựa trên phản hồi đến ngay?

Một thiết bị vừa gửi số đo, vừa cần nhận lệnh giảm tần suất lấy mẫu ngay trong cùng phiên: **bidirectional streaming**. Client có thể gửi message mới trong lúc nhận phản hồi từ server.

Nếu server chỉ cần gửi **một kết luận cuối** sau khi nhận đủ request, hãy dùng **client streaming**. Nếu client chỉ cần gửi **một điều kiện đăng ký ban đầu** và nhận cập nhật, dùng **server streaming**.

### Câu hỏi 4: Việc giữ RPC mở có đáng giá?

Mỗi stream đang mở tiêu tốn tài nguyên kết nối, state và khả năng theo dõi/hủy. Nếu cập nhật ít, client có thể dùng **unary polling** có giới hạn. Nếu cần push theo thời gian thực, server streaming giảm polling. Nếu tương tác hai chiều liên tục, bidirectional streaming có thể giảm nhu cầu thiết lập nhiều RPC và giảm độ trễ trao đổi.

Không có một loại RPC luôn nhanh hơn trong mọi tình huống. Hiệu năng phụ thuộc kích thước message, tần suất, độ trễ mạng, serialization, áp lực bộ nhớ, backpressure và số stream đồng thời.

### Câu hỏi 5: Khi lỗi giữa chừng, cần khôi phục ở mức nào?

Unary thường dễ gắn **idempotency key** và retry từng thao tác. Với streaming, lỗi có thể xảy ra **sau khi một phần request đã được xử lý hoặc một phần response đã đến client**. Cần thiết kế **message ID**, **sequence**, checkpoint hoặc resume token nếu muốn tiếp tục an toàn.

Sự đơn giản của việc phục hồi dữ liệu cũng là một tiêu chí chọn phương thức. Khi không có khả năng khôi phục stream dài, đôi khi chia thành **nhiều unary RPC có idempotency và phân trang** là phương án bền vững hơn.

## 3. Ma trận quyết định theo bài toán thực tế

| Bài toán | Loại thường phù hợp | Lý do | Điều kiện khiến lựa chọn thay đổi |
| --- | --- | --- | --- |
| Lấy hồ sơ người dùng theo ID | **Unary** | Một yêu cầu, một kết quả | Cần nhận nhiều cập nhật liên tục → server streaming |
| Tính tổng phí của một giỏ hàng | **Unary** | Toàn bộ dữ liệu đầu vào sẵn có, kết quả đơn | Giỏ hàng được gửi từng phần liên tục → cân nhắc client streaming |
| Theo dõi trạng thái đơn hàng | **Server streaming** | Một subscription, nhiều sự kiện trạng thái | Cập nhật rất thưa và polling đủ tốt → unary |
| Tải nhiều log lên và nhận một báo cáo | **Client streaming** | Nhiều chunk gửi dần, một kết quả tổng hợp | Cần xác nhận/checkpoint sau từng chunk → bidi hoặc API bổ trợ |
| Thiết bị gửi telemetry đồng thời nhận lệnh | **Bidirectional streaming** | Cả hai chiều hoạt động độc lập | Thiết bị chỉ gửi log → client streaming |
| Phân trang danh sách hàng triệu bản ghi | **Nhiều unary** hoặc **server streaming** | Chọn theo nhu cầu ngắt/tiếp tục và xử lý từng phần | Cần trang độc lập, cache hoặc resume → unary pagination |
| Gửi một file nhỏ đã nằm trong RAM | **Unary** | Ít code quản lý stream | File lớn hoặc được tạo dần → client streaming |
| Phiên trò chuyện tương tác | **Bidirectional streaming** | Hai phía phát message bất kỳ lúc nào | Chỉ nhận thông báo sau đăng ký → server streaming |

**Quy tắc thực dụng:** ưu tiên kiểu đơn giản nhất vẫn đáp ứng **ngữ nghĩa luồng dữ liệu**. Số lượng bản ghi lớn, bản thân nó, chưa đủ để kết luận phải dùng streaming.

## 4. Thiết kế hợp đồng .proto cho bốn lựa chọn

Giả sử ta xây dựng dịch vụ **FleetTelemetry** cho đội thiết bị. Một thiết bị có thể yêu cầu trạng thái hiện tại, đăng ký nhận thay đổi, gửi lô dữ liệu và tham gia phiên điều khiển hai chiều.

File **src/main/proto/fleet_telemetry.proto**:

~~~proto
syntax = "proto3";

package demo.fleet.v1;

option java_package = "vn.demo.grpc.fleet.v1";
option java_multiple_files = true;
option java_outer_classname = "FleetTelemetryProto";

service FleetTelemetry {
  // Một yêu cầu -> một phản hồi.
  rpc GetCurrentState(DeviceQuery) returns (DeviceState);

  // Một yêu cầu -> nhiều phản hồi được phát dần.
  rpc WatchState(DeviceQuery) returns (stream DeviceState);

  // Nhiều bản ghi được gửi dần -> một kết quả cuối.
  rpc UploadReadings(stream Reading) returns (UploadReport);

  // Nhiều tín hiệu hai chiều -> phiên tương tác.
  rpc ControlSession(stream DeviceSignal) returns (stream ControlEvent);
}

message DeviceQuery {
  string device_id = 1;
}

message DeviceState {
  string device_id = 1;
  bool online = 2;
  int64 version = 3;
}

message Reading {
  string device_id = 1;
  int64 sequence = 2;
  double temperature = 3;
}

message UploadReport {
  int64 accepted_count = 1;
  double average_temperature = 2;
}

message DeviceSignal {
  string device_id = 1;
  int64 sequence = 2;
  string payload = 3;
}

message ControlEvent {
  int64 related_sequence = 1;
  string command = 2;
}
~~~

Đọc bốn dòng **rpc** theo vị trí của từ khóa **stream**:

~~~proto
rpc GetCurrentState(DeviceQuery) returns (DeviceState);
rpc WatchState(DeviceQuery) returns (stream DeviceState);
rpc UploadReadings(stream Reading) returns (UploadReport);
rpc ControlSession(stream DeviceSignal) returns (stream ControlEvent);
~~~

Điều này xác định **cardinality** của message. Nó không bắt buộc WatchState phát mỗi giây, UploadReadings chỉ chứa một thiết bị, hay ControlSession phải có một response cho từng request. Các quy tắc đó cần được mô tả riêng trong hợp đồng nghiệp vụ.

Trong Protobuf, một message cũng có thể chứa **repeated** để biểu diễn danh sách:

~~~proto
message ReadingBatch {
  repeated Reading items = 1;
}

rpc UploadBatch(ReadingBatch) returns (UploadReport);
~~~

**UploadBatch** vẫn là **unary RPC**, dù message chứa nhiều Reading. Giữa **UploadBatch** và **UploadReadings**, hãy chọn theo cách dữ liệu được sinh ra, kích thước giới hạn, nhu cầu xử lý từng phần và chi phí phục hồi khi lỗi. Bảo đảm message không vượt giới hạn kích thước của client/server; với payload rất lớn, việc chỉ tăng giới hạn message có thể làm tăng bộ nhớ đột biến.

## 5. API Java thay đổi thế nào theo lựa chọn RPC?

Sau khi chạy **protoc** và plugin gRPC Java, các phương thức sinh mã có chữ ký tương ứng. Với Java server:

~~~java
// Unary: nhận một request.
public void getCurrentState(
    DeviceQuery request,
    StreamObserver<DeviceState> responseObserver);

// Server streaming: nhận một request, phát nhiều response.
public void watchState(
    DeviceQuery request,
    StreamObserver<DeviceState> responseObserver);

// Client streaming: nhận observer để phát phản hồi,
// trả observer để nhận request lần lượt.
public StreamObserver<Reading> uploadReadings(
    StreamObserver<UploadReport> responseObserver);

// Bidirectional: một observer nhận và một observer gửi.
public StreamObserver<DeviceSignal> controlSession(
    StreamObserver<ControlEvent> responseObserver);
~~~

Đây là **chữ ký minh họa** trong lớp kế thừa **FleetTelemetryGrpc.FleetTelemetryImplBase**. Từ loại RPC đã chọn, việc viết service trong Spring sẽ có hai dạng chính:

- **Unary/server streaming:** server nhận trực tiếp một request và một **responseObserver**.
- **Client/bidirectional streaming:** server nhận **responseObserver** và trả về một **request observer** để nhận lần lượt các request.

### Client: cách đọc và ghi message

~~~java
// Giả sử channel đã được cấu hình và quản lý vòng đời.
var blocking = FleetTelemetryGrpc.newBlockingStub(channel);
var async = FleetTelemetryGrpc.newStub(channel);

// Unary: nhận một kết quả.
DeviceState state = blocking.getCurrentState(query);

// Server streaming: duyệt nhiều kết quả từ một query.
Iterator<DeviceState> states = blocking.watchState(query);
while (states.hasNext()) {
    DeviceState nextState = states.next();
    // Xử lý từng trạng thái.
}

// Client streaming: async stub nhận observer phản hồi cuối,
// và trả observer để client gửi nhiều Reading.
StreamObserver<Reading> uploadRequests =
    async.uploadReadings(uploadResponseObserver);
uploadRequests.onNext(firstReading);
uploadRequests.onNext(secondReading);
uploadRequests.onCompleted();

// Bidi: đồng thời có observer nhận và observer gửi.
StreamObserver<DeviceSignal> controlRequests =
    async.controlSession(controlResponseObserver);
controlRequests.onNext(firstSignal);
// Client còn có thể nhận ControlEvent khi vẫn đang gửi.
controlRequests.onCompleted();
~~~

Các biến **query**, **firstReading**, **secondReading**, **firstSignal** và hai response observer ở đây là dữ liệu/đối tượng giả định đã được tạo theo message Protobuf; đoạn code nhấn mạnh sự khác biệt API giữa bốn kiểu. Với streaming, **onNext()** phía gửi không tự bảo đảm server đã nhận, xử lý hoặc ghi bền dữ liệu.

## 6. Minh họa Spring server: một thiết kế theo nhu cầu luồng

Đoạn code sau thể hiện hai method có cùng dữ liệu đầu vào nhưng lựa chọn khác nhau về cách truyền: **GetCurrentState** trả một trạng thái và **WatchState** phát ba cập nhật. Đây là ví dụ hữu hạn để quan sát sự khác biệt; ở ứng dụng thật, cập nhật thường đến từ nguồn sự kiện:

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.fleet.v1.DeviceQuery;
import vn.demo.grpc.fleet.v1.DeviceState;
import vn.demo.grpc.fleet.v1.FleetTelemetryGrpc;

@Service
public class FleetTelemetryService
        extends FleetTelemetryGrpc.FleetTelemetryImplBase {

    @Override
    public void getCurrentState(
            DeviceQuery request,
            StreamObserver<DeviceState> responseObserver) {
        if (request.getDeviceId().isBlank()) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                .withDescription("device_id is required")
                .asRuntimeException());
            return;
        }

        responseObserver.onNext(DeviceState.newBuilder()
            .setDeviceId(request.getDeviceId())
            .setOnline(true)
            .setVersion(1)
            .build());
        responseObserver.onCompleted();
    }

    @Override
    public void watchState(
            DeviceQuery request,
            StreamObserver<DeviceState> responseObserver) {
        if (request.getDeviceId().isBlank()) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                .withDescription("device_id is required")
                .asRuntimeException());
            return;
        }

        for (int version = 1; version <= 3; version++) {
            responseObserver.onNext(DeviceState.newBuilder()
                .setDeviceId(request.getDeviceId())
                .setOnline(true)
                .setVersion(version)
                .build());
        }
        responseObserver.onCompleted();
    }
}
~~~

Khi cấu hình Spring gRPC tự động đăng ký các bean triển khai **BindableService**, **@Service** giúp Spring quản lý triển khai dịch vụ. Cách đăng ký có thể khác theo phiên bản Spring gRPC hoặc starter được dùng. Hai phương thức trong ví dụ đều nhận một **DeviceQuery**; **sự khác biệt nằm ở số response message** mà server được phép gửi.

Không sao chép vòng **for** trên vào luồng cập nhật vô hạn. Với server streaming thật, cần cơ chế đăng ký/hủy subscription, kiểm soát flow control, đồng bộ khi nhiều nguồn phát và dọn tài nguyên khi client ngắt kết nối.

### Ví dụ server cần state theo từng luồng request

Với **UploadReadings**, server phải xử lý nhiều Reading trên **cùng một RPC**. Đặt bộ đếm trong **request observer mới tạo cho từng lần gọi**:

~~~java
@Override
public StreamObserver<Reading> uploadReadings(
        StreamObserver<UploadReport> responseObserver) {
    return new StreamObserver<>() {
        private long count;
        private double sum;
        private boolean ended;

        @Override
        public void onNext(Reading reading) {
            if (ended) return;
            if (reading.getDeviceId().isBlank()
                    || !Double.isFinite(reading.getTemperature())) {
                ended = true;
                responseObserver.onError(Status.INVALID_ARGUMENT
                    .withDescription("invalid reading")
                    .asRuntimeException());
                return;
            }
            count++;
            sum += reading.getTemperature();
        }

        @Override
        public void onError(Throwable error) {
            ended = true; // Hủy phần tổng hợp chưa hoàn tất.
        }

        @Override
        public void onCompleted() {
            if (ended) return;
            ended = true;
            responseObserver.onNext(UploadReport.newBuilder()
                .setAcceptedCount(count)
                .setAverageTemperature(count == 0 ? 0 : sum / count)
                .build());
            responseObserver.onCompleted();
        }
    };
}
~~~

Đoạn method này là **phần bổ sung cho FleetTelemetryService** ở trên (cần import **Reading** và **UploadReport** tương ứng). Tổng hợp trong RAM giúp dễ thấy ngữ nghĩa **nhiều request → một response**. Trong production cần giới hạn số message, kích thước và thời gian xử lý, cũng như quyết định dữ liệu được commit lúc nào.

Nếu client cần xác nhận **ngay sau từng Reading** và điều chỉnh tốc độ tiếp theo theo yêu cầu server, hãy cân nhắc **ControlSession** kiểu bidirectional hoặc một API riêng cho xác nhận. Không cố phát nhiều **UploadReport** trong một client streaming RPC vốn chỉ khai báo một response.

## 7. Những đánh đổi khó thấy khi chọn streaming

### 7.1. Kích thước payload và bộ nhớ

**Unary batch** có thể dễ cache, dễ retry và đơn giản về API, nhưng thường cần tạo message đủ lớn trước khi gửi. **Streaming** cho phép xử lý từng phần, giảm nhu cầu gom toàn bộ dữ liệu trong bộ nhớ, nhưng **không tự ngăn** ứng dụng tạo hàng đợi vô hạn.

Với file lớn hoặc log sinh liên tục, client streaming thường có lợi hơn. Nếu dữ liệu đã có sẵn, kích thước vừa phải, cần một kết quả duy nhất và ít rủi ro giới hạn message, unary batch có thể đủ.

### 7.2. Độ trễ, số lần gọi và khả năng cache

**Server streaming** có thể trả bản ghi đầu tiên sớm hơn thay vì chờ toàn bộ tập kết quả. **Bidirectional streaming** có thể giảm chờ đợi khi cần trao đổi liên tục. Ngược lại, các service có nhiều thao tác rời rạc, ngắn và cần retry độc lập có thể phù hợp với unary hơn.

Cache kết quả từng unary request hoặc từng trang thường đơn giản hơn cache một stream đang thay đổi. Tuy nhiên không nên chọn loại RPC chỉ theo giả định hiệu năng: cần đo **latency p50/p95/p99**, throughput, sử dụng CPU/bộ nhớ và số stream đồng thời dưới tải thực tế.

### 7.3. Flow control và backpressure

Streaming có thể gặp trường hợp **bên gửi nhanh hơn bên nhận**. HTTP/2 và gRPC có flow control ở tầng truyền tải, nhưng ứng dụng vẫn cần bảo vệ các hàng đợi dữ liệu.

Trong gRPC Java:

- **ClientCallStreamObserver** và **ServerCallStreamObserver** cung cấp **isReady()** và **setOnReadyHandler(...)** để phối hợp tốc độ gửi.
- Với async client streaming, có thể thiết lập callback gửi trong **ClientResponseObserver.beforeStart(...)**.
- **isReady()** biểu thị khả năng ghi tương ứng với flow control/bộ đệm; **không có nghĩa server đã xử lý hoặc lưu dữ liệu bền vững**.
- **StreamObserver không mặc định thread-safe**. Khi nhiều thread gửi vào cùng một observer, phải tuần tự hóa các lệnh **onNext**, **onCompleted** và **onError**.

Ngoài ra, cần đặt giới hạn **message size**, **số message/batch**, **stream đồng thời**, **dung lượng hàng đợi** và **thời gian sống**. Không giữ một stream mở mãi chỉ vì giao thức cho phép.

### 7.4. Thứ tự và tính độc lập hai chiều

Trong một stream, gRPC giữ **thứ tự message của từng chiều**. Với bidirectional, không có thứ tự toàn cục giữa request và response; một request có thể tạo 0, 1 hoặc nhiều sự kiện phản hồi.

Ví dụ, nếu server gửi tín hiệu điều khiển độc lập, cần có **event type** và có thể thêm **related_sequence** để xác định phản hồi gắn với thông điệp nào. Từ khóa **stream** không tạo ra cơ chế tự động ghép cặp request-response.

### 7.5. Giới hạn của tính đúng đắn giao dịch

Client streaming và bidirectional streaming có thể bị lỗi sau khi server đã lưu **một phần** dữ liệu. **onCompleted()** chỉ cho biết luồng message đã hoàn tất theo giao thức; nó không bảo đảm commit nghiệp vụ kiểu tất cả hoặc không có gì.

Nếu cần giao dịch nguyên tử, thiết kế vùng tạm (**staging**), transaction/commit riêng hoặc cơ chế xác nhận cuối được mô tả rõ trong message. Nếu cần tiếp tục sau lỗi, dùng **upload ID**, sequence/checkpoint và chống trùng. Chỉ tự động gửi lại toàn bộ stream mà không có cơ chế này có thể gây tác dụng phụ lặp lại.

## 8. Deadline, cancel và status ảnh hưởng tới lựa chọn

**Deadline** là giới hạn thời gian cho **toàn bộ RPC**, kể cả khi nó có hàng nghìn message. Với unary ngắn, thường dùng deadline tương đối ngắn; với stream theo dõi sự kiện, deadline phải phù hợp thời gian sử dụng hoặc chính sách tái kết nối.

~~~java
var stub = FleetTelemetryGrpc.newStub(channel)
    .withDeadlineAfter(30, TimeUnit.SECONDS);
~~~

Ví dụ đặt deadline 30 giây cho một stub; việc gửi thêm message **không tự gia hạn** deadline. Với stream có thể kéo dài lâu, cần quy định thời gian sống và cách khôi phục sau deadline hoặc gián đoạn.

| Trạng thái | Ý nghĩa | Hành động thường gặp |
| --- | --- | --- |
| **OK** | RPC kết thúc thành công | Dùng kết quả cuối |
| **INVALID_ARGUMENT** | Request/message không hợp lệ | Kiểm tra input; không retry nguyên trạng |
| **NOT_FOUND** | Tài nguyên không tồn tại | Xử lý kết quả không tìm thấy |
| **UNAUTHENTICATED** | Thiếu hoặc sai xác thực | Xử lý credential |
| **PERMISSION_DENIED** | Không đủ quyền | Kiểm tra phân quyền |
| **RESOURCE_EXHAUSTED** | Quota/bộ nhớ/giới hạn bị vượt | Giảm tải, xem lại batch/stream |
| **DEADLINE_EXCEEDED** | Vượt ngân sách thời gian | Kiểm tra phần việc đã thực hiện |
| **CANCELLED** | Lời gọi bị hủy | Dọn tài nguyên, ngừng tác vụ |
| **UNAVAILABLE** | Dịch vụ/kết nối tạm thời không sẵn sàng | Retry có kiểm soát khi an toàn |

Trên client dùng blocking stub, lỗi thường xuất hiện dưới dạng **StatusRuntimeException**; với async stub, lỗi đi vào callback **onError(Throwable)**. Trên server, có thể dùng **responseObserver.onError(Status.INVALID_ARGUMENT.withDescription("...").asRuntimeException())**.

Với **server streaming**, client có thể nhận vài message rồi gặp lỗi. Các message đã đọc không làm RPC được coi là hoàn tất thành công. Với **client streaming/bidi**, server có thể đã nhận/lưu một phần message dù client gặp **DEADLINE_EXCEEDED** hoặc **UNAVAILABLE**.

Phân biệt **kết thúc bình thường** bằng **onCompleted()** với **hủy** RPC. Client streaming/bidi cần half-close chiều gửi khi đã gửi hết request, nhưng vẫn có thể chờ response. Hủy có thể khiến công việc trên server bị dừng, nhưng không tự rollback thao tác đã commit.

## 9. Metadata, interceptor và TLS đối với mọi kiểu RPC

**Metadata** gRPC mang thông tin chung của lời gọi như authorization token, request ID, tenant ID hoặc trace context. Trong streaming, metadata không tự lặp lại theo từng message; các dữ liệu đổi theo message nên đặt trong payload Protobuf.

**Client/server interceptor** phù hợp để xử lý xác thực, truy vết, đo thời gian và thống kê status. Với **streaming**, một RPC có thể bao gồm nhiều message và sống rất lâu, vì thế cần quan sát thêm **số stream mở**, **số message/byte theo chiều**, **độ dài stream**, lượng backlog và các lần bị hủy.

Trong triển khai production:

1. Bảo vệ đường truyền bằng **TLS**; cân nhắc **mTLS** khi các dịch vụ phải xác thực lẫn nhau.
2. Kiểm tra quyền của thiết bị và tenant ở server, không tin hoàn toàn **device_id** trong payload.
3. Không ghi token, metadata nhạy cảm hoặc toàn bộ nội dung stream vào log.
4. Áp dụng quota theo người dùng/tenant và giới hạn tài nguyên cho những RPC mở lâu.
5. Tách deadline, retry và rate limit theo từng nhóm phương thức thay vì dùng một cấu hình cứng cho tất cả.

Trong local/dev, gRPC Java có thể dùng **ManagedChannelBuilder.forAddress(...).usePlaintext()** để đơn giản hóa ví dụ; môi trường sản xuất cần channel bảo mật phù hợp. Việc cấu hình bean/stub/server cụ thể tùy phiên bản Spring gRPC và starter của dự án.

## 10. Cách kiểm thử quyết định chọn RPC

Kiểm thử cần chứng minh **hành vi luồng dữ liệu mong muốn**, không chỉ rằng code có thể gọi được method.

| Kiểu | Kiểm thử thành công | Kiểm thử lỗi và giới hạn |
| --- | --- | --- |
| Unary | Một request, một response có dữ liệu chính xác | Input sai; deadline; lỗi kết nối |
| Server streaming | Một request, nhận nhiều response đúng thứ tự rồi hoàn tất | Lỗi giữa stream, cancel, consumer chậm |
| Client streaming | Gửi nhiều request, nhận đúng một summary | Stream rỗng theo chính sách; message sai; lỗi giữa lô |
| Bidirectional streaming | Gửi và nhận đan xen, cả hai luồng hoàn tất đúng | Request/response không 1:1; cancel; reconnection; flow control |

Ví dụ kiểm thử hai method đầu tiên bằng **gRPC in-process** để phân biệt rõ unary và server streaming:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.fleet.v1.DeviceQuery;
import vn.demo.grpc.fleet.v1.DeviceState;
import vn.demo.grpc.fleet.v1.FleetTelemetryGrpc;

class FleetTelemetryServiceTest {

    @Test
    void unaryAndServerStreamingHaveDifferentCardinality()
            throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new FleetTelemetryService())
            .build().start();
        ManagedChannel channel = InProcessChannelBuilder
            .forName(name)
            .directExecutor()
            .build();

        try {
            var stub = FleetTelemetryGrpc.newBlockingStub(channel);
            DeviceQuery query = DeviceQuery.newBuilder()
                .setDeviceId("sensor-01")
                .build();

            DeviceState one = stub.getCurrentState(query);
            assertEquals(1L, one.getVersion());

            List<DeviceState> updates = new ArrayList<>();
            stub.watchState(query).forEachRemaining(updates::add);
            assertEquals(3, updates.size());
            assertEquals(3L, updates.get(2).getVersion());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Để chạy ví dụ, cần JUnit, thư viện **gRPC in-process**, các lớp đã sinh từ **fleet_telemetry.proto** và **FleetTelemetryService**. Bài kiểm thử in-process xác nhận hợp đồng ở mức gRPC Java; chưa xác nhận Spring thực sự đăng ký bean hoặc cấu hình TLS/interceptor. Cần integration test khởi động Spring context và gRPC server cho phần tích hợp này.

Với **client streaming**, kiểm tra gửi nhiều Reading rồi half-close và nhận đúng một UploadReport. Với **bidirectional**, cần một kiểm thử thật sự quan sát được response **trước khi client half-close** nếu đó là yêu cầu của giao thức; không chỉ gửi hết rồi mới kiểm tra danh sách response.

Kiểm thử tải nên đo throughput, p95/p99 latency, CPU, bộ nhớ, quota, số stream đang mở và hành vi khi bên nhận chậm. Quyết định dùng streaming nên dựa trên số liệu, nhất là khi cân nhắc đổi từ nhiều unary call sang một stream dài.

## 11. Tình huống thiết kế: chọn loại RPC cho nền tảng giao hàng

Hãy xem một yêu cầu phát triển có bốn chức năng:

**Chức năng A — Tính phí giao hàng:** Người dùng gửi địa chỉ xuất phát, điểm đến, loại hàng và nhận số tiền cuối. Dữ liệu đã có sẵn, chỉ cần một kết quả. **Chọn unary**, ví dụ **CalculateFee(FeeRequest) returns (FeeReply)**.

**Chức năng B — Theo dõi vị trí tài xế:** Client đăng ký theo mã chuyến đi rồi nhận tọa độ mới trong lúc chuyến đi diễn ra. **Chọn server streaming**, ví dụ **WatchDriver(TripRequest) returns (stream DriverPosition)**. Cần hủy subscription khi người dùng rời trang; cân nhắc resume sequence khi kết nối lại.

**Chức năng C — Đồng bộ hành trình offline:** Ứng dụng tài xế lưu nhiều tọa độ trong lúc mất mạng rồi tải dần lên server, cuối cùng nhận số mẫu được chấp nhận. **Chọn client streaming**, ví dụ **UploadPositions(stream DriverPosition) returns (UploadResult)**. Thiết kế upload ID, giới hạn lô, chống gửi trùng và chính sách commit dữ liệu.

**Chức năng D — Điều phối giao hàng tương tác:** Tài xế gửi tín hiệu online/vị trí/trạng thái; điều phối có thể gửi lệnh đổi tuyến ngay trong phiên. **Chọn bidirectional streaming**, ví dụ **Dispatch(stream DriverSignal) returns (stream DispatcherEvent)**. Cần kiểm soát flow control, session, correlation ID và khả năng khôi phục kết nối.

Nếu chức năng D chỉ yêu cầu một bản cập nhật sau mỗi thao tác rời rạc, **nhiều unary RPC** cũng có thể là thiết kế hợp lý. Chỉ thêm bidirectional stream khi nhu cầu thực sự là **hai chiều liên tục hoặc phản hồi đan xen**.

## 12. Checklist quyết định trước khi chốt contract

Trước khi chọn phương thức, xác nhận:

1. **Cardinality:** client gửi một hay nhiều message; server trả một hay nhiều message?
2. **Thời điểm:** có cần xử lý từng message khi đang truyền hay chờ đầy đủ rồi xử lý?
3. **Tính tương tác:** server có phải phản hồi trước khi client gửi xong, hoặc tự phát event?
4. **Khối lượng:** giới hạn kích thước message, số message, RAM và thời gian sống RPC là gì?
5. **Khôi phục:** khi đứt kết nối giữa stream, dữ liệu nào đã được xử lý và sẽ resume ra sao?
6. **Vận hành:** cần deadline, hủy, flow control, metadata, TLS, interceptor và metric nào?
7. **Kiểm thử:** kịch bản nào chứng minh loại RPC được chọn đúng với nhu cầu thực tế?

Nếu câu trả lời chưa rõ, hãy làm một prototype nhỏ bằng unary hoặc streaming tương ứng rồi **đo tải và mô phỏng lỗi giữa chừng** trước khi khóa hợp đồng lâu dài. Việc đổi cardinality trong định nghĩa method làm thay đổi API stub, cách gọi và tương thích client; thường cần method mới hoặc chiến lược migration khi service đã có người sử dụng.

## 13. Bài tập tự kiểm tra

1. Một API trả 500 sản phẩm đã có sẵn trong DB và client muốn phân trang, cache từng trang. Nên dùng unary pagination hay server streaming? Giải thích theo ngữ nghĩa lỗi và resume.
2. Một client gửi log liên tục trong 10 phút nhưng chỉ muốn báo cáo tổng cuối. Chọn RPC nào? Đặt deadline và giới hạn tài nguyên ra sao?
3. Server phải gửi cảnh báo ngay khi phát hiện một Reading bất thường trong khi client còn đang gửi. Vì sao client streaming với một response cuối có thể chưa đủ?
4. Client đã nhận 200 response của server streaming rồi gặp **UNAVAILABLE**. Tại sao không thể coi RPC là thành công? Nên dùng trường nào để tiếp tục từ mốc đã nhận?
5. Một đội muốn thay 1.000 unary call nhỏ bằng một bidirectional stream. Những chỉ số nào cần đo để quyết định thay đổi này thực sự đem lại lợi ích?

**Ghi nhớ:** Chọn loại RPC theo **hướng dữ liệu, số lượng message và thời điểm từng phía cần gửi/nhận**, rồi mới xem xét hiệu năng và khả năng mở rộng. Trong Spring gRPC, lựa chọn này xuất hiện trực tiếp trong **Protocol Buffers** qua vị trí từ khóa **stream**, đồng thời quyết định cách client/server Java sử dụng **stub** và **StreamObserver**. Thiết kế tốt luôn đi kèm cơ chế **deadline, status, hủy, bảo mật, flow control, kiểm thử và giám sát** phù hợp với vòng đời RPC.
