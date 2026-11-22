# Một request một response không đồng nghĩa không có stream

Trong gRPC, **unary RPC** có nghĩa là một lời gọi nhận **một request message** và trả **một response message khi thành công**. Điều đó không có nghĩa lời gọi không sử dụng stream. Khi chạy trên HTTP/2, **mỗi RPC, kể cả unary, được vận chuyển trên một HTTP/2 stream riêng**.

Sự nhầm lẫn thường xuất hiện vì từ *stream* được dùng ở hai tầng khác nhau:

- **HTTP/2 stream** là kênh truyền hai chiều ở tầng transport. gRPC dùng nó để chuyển headers, data frames và trailers cho một RPC.
- **Streaming trong hợp đồng Protobuf** mô tả số lượng message mà một phía được phép gửi trong một RPC. Từ khóa **stream** trong file **.proto** quyết định cardinality này.

Vì vậy, unary không có từ khóa **stream** trong khai báo method Protobuf, nhưng vẫn có HTTP/2 stream bên dưới. Đây là khác biệt quan trọng khi đọc hợp đồng, thiết kế API, quan sát lưu lượng mạng và chẩn đoán lỗi trong **Spring gRPC**.

## 1. Phân biệt ba khái niệm

| Khái niệm | Nằm ở tầng nào? | Trả lời câu hỏi nào? |
| --- | --- | --- |
| **RPC method** | API gRPC | Client gọi chức năng nào trên server? |
| **Protobuf message cardinality** | Hợp đồng **.proto** / API ứng dụng | Mỗi phía gửi một hay nhiều message trong một RPC? |
| **HTTP/2 stream** | Transport | Các frame của một RPC được truyền qua kênh logic nào? |

Một HTTP/2 connection có thể mang nhiều HTTP/2 stream đồng thời. Mỗi gRPC RPC sử dụng một stream trong connection đó; nhiều RPC có thể chạy đồng thời mà không cần mở một TCP connection mới cho từng lời gọi. HTTP/2 đánh số stream bằng **stream ID** để phân biệt chúng trên cùng connection.

**Từ khóa stream trong .proto không tạo ra HTTP/2 stream.** HTTP/2 stream đã tồn tại để vận chuyển mọi loại RPC. Từ khóa này chỉ cho biết phía client hoặc server có thể gửi nhiều Protobuf message trong cùng lời gọi hay không.

## 2. Unary RPC vẫn chạy trên một HTTP/2 stream

Ví dụ khai báo unary:

~~~proto
syntax = "proto3";

package demo.catalog.v1;

option java_package = "vn.demo.grpc.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string item_id = 1;
}

message GetItemResponse {
  string item_id = 1;
  string name = 2;
  int64 available_quantity = 3;
}
~~~

Trong method **GetItem**, không có từ khóa **stream** ở request hoặc response. Điều đó quy định:

- Client gửi một **GetItemRequest**.
- Server trả một **GetItemResponse** khi lời gọi thành công.
- Server kết thúc RPC bằng trạng thái gRPC, thường là **OK** nếu xử lý thành công.

Nhưng khi gửi lời gọi, gRPC vẫn tạo một **HTTP/2 stream**. Dòng trao đổi ở mức transport có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant H as HTTP/2 connection
    participant S as gRPC server
    C->>H: HEADERS (POST /demo.catalog.v1.CatalogService/GetItem)
    H->>S: Mở HTTP/2 stream cho RPC
    C->>H: DATA (1 gRPC message chứa GetItemRequest)
    Note over C,H: Client kết thúc chiều gửi request
    H->>S: Request message
    S-->>H: HEADERS (response)
    S-->>H: DATA (1 gRPC message chứa GetItemResponse)
    S-->>H: Trailers (grpc-status: 0, END_STREAM)
    H-->>C: Response và trạng thái OK
~~~

Sơ đồ thể hiện các thành phần chính, không phải một quy định rằng mỗi message phải nằm trong đúng một DATA frame. Trong thực tế, gRPC message có thể được chia qua nhiều HTTP/2 DATA frame; ranh giới frame không nhất thiết trùng với ranh giới message Protobuf.

### Một RPC, một HTTP/2 stream, hai message ứng dụng

Đối với unary thành công, có thể đếm ở hai tầng:

| Tầng | Số lượng trong ví dụ GetItem |
| --- | --- |
| RPC | 1 lời gọi **GetItem** |
| HTTP/2 | 1 stream dành cho lời gọi đó |
| Protobuf request | 1 message **GetItemRequest** |
| Protobuf response | 1 message **GetItemResponse** |
| gRPC status | 1 trạng thái kết thúc, ví dụ **OK** |

Không nên đếm số DATA frame để suy ra số request/response. Một message có thể đi qua nhiều frame do kích thước hoặc cách phân mảnh của transport.

## 3. Từ khóa stream trong .proto có ý nghĩa gì?

Hãy so sánh bốn khai báo:

~~~proto
// Unary: một request, một response.
rpc GetItem(GetItemRequest) returns (GetItemResponse);

// Server streaming: một request, nhiều response.
rpc WatchItem(GetItemRequest) returns (stream ItemUpdate);

// Client streaming: nhiều request, một response.
rpc UploadItems(stream ItemChunk) returns (UploadSummary);

// Bidirectional streaming: nhiều request, nhiều response.
rpc Synchronize(stream SyncRequest) returns (stream SyncEvent);
~~~

Tất cả bốn method đều được vận chuyển trên HTTP/2 stream. Khác biệt là **số lượng message ứng dụng trong từng chiều**:

| Loại method | HTTP/2 stream cho RPC | Request message | Response message khi thành công |
| --- | --- | --- | --- |
| Unary | Có, một stream | 1 | 1 |
| Server streaming | Có, một stream | 1 | 0..N |
| Client streaming | Có, một stream | 0..N | 1 |
| Bidirectional streaming | Có, một stream | 0..N | 0..N |

**stream** trước kiểu request chỉ bật khả năng gửi nhiều request message. **stream** trước kiểu response chỉ bật khả năng gửi nhiều response message. Nếu cả hai vị trí đều không có từ khóa này, method vẫn chạy trên HTTP/2 stream nhưng có cardinality unary.

Một điểm dễ nhầm khác: message có trường **repeated** vẫn chỉ là **một message** nếu method nhận hoặc trả kiểu message đó:

~~~proto
message ItemBatch {
  repeated GetItemRequest items = 1;
}

service CatalogService {
  rpc GetItems(ItemBatch) returns (ItemBatch);
}
~~~

**GetItems** vẫn là unary: một **ItemBatch** request và một **ItemBatch** response. Số phần tử trong trường **items** không thay đổi cardinality của RPC. Nếu muốn gửi từng phần theo thời gian trong cùng một lời gọi, khi đó mới cân nhắc streaming.

## 4. Gọi unary trong Java/Spring: API đơn giản, transport vẫn có stream

Sau khi cấu hình sinh mã Protobuf và gRPC Java, server có thể triển khai method unary bằng cách kế thừa service base class:

~~~java
package vn.demo.catalog;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.demo.grpc.catalog.v1.CatalogServiceGrpc;
import vn.demo.grpc.catalog.v1.GetItemRequest;
import vn.demo.grpc.catalog.v1.GetItemResponse;

@Service
public class CatalogServiceImpl
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        if (request.getItemId().isBlank()) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                .withDescription("item_id is required")
                .asRuntimeException());
            return;
        }

        GetItemResponse response = GetItemResponse.newBuilder()
            .setItemId(request.getItemId())
            .setName("Bàn phím cơ")
            .setAvailableQuantity(12)
            .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

Đây là API server ở tầng ứng dụng: method nhận **một request object** và dùng **responseObserver** để gửi **một response object**. Lớp gRPC bên dưới quản lý HTTP/2 stream, framing message và trạng thái kết thúc. Người viết service không cần tự tạo HTTP/2 stream hay thao tác trực tiếp với DATA frame.

Client có thể gọi bằng blocking stub:

~~~java
GetItemRequest request = GetItemRequest.newBuilder()
    .setItemId("keyboard-01")
    .build();

GetItemResponse response = blockingStub
    .withDeadlineAfter(2, TimeUnit.SECONDS)
    .getItem(request);

System.out.println(response.getName());
~~~

Ở đây Java API nhận một request và trả trực tiếp một response. Stub ẩn chi tiết transport khỏi code nghiệp vụ; nó không loại bỏ HTTP/2 stream. Mỗi lần gọi **getItem(request)** là một RPC riêng và được gRPC vận chuyển trên một HTTP/2 stream.

Trong ứng dụng Spring, bean service thường được đăng ký với gRPC server qua cơ chế tích hợp của starter đang dùng. Cấu hình cụ thể có thể khác giữa các phiên bản Spring gRPC; điều đó không làm thay đổi quan hệ giữa cardinality Protobuf và HTTP/2 stream.

## 5. HTTP/2 stream mang những gì?

Một gRPC RPC trên HTTP/2 thường có ba nhóm thành phần:

1. **Initial headers:** nhận diện method, content type và metadata của lời gọi.
2. **DATA frames:** mang các gRPC message đã được đóng khung và mã hóa.
3. **Trailers:** mang trạng thái kết thúc gRPC, thường gồm **grpc-status** và có thể có **grpc-message** hoặc metadata bổ sung.

Với unary thành công, client gửi một request message trong DATA; server gửi một response message trong DATA; server kết thúc bằng trailers có **grpc-status: 0** (**OK**). Với lỗi, server có thể trả status lỗi trong trailers mà không có response message ứng dụng.

### Framing của một gRPC message

Trên transport HTTP/2, một gRPC message có framing gồm:

| Thành phần | Kích thước | Ý nghĩa |
| --- | --- | --- |
| Compressed flag | 1 byte | Cho biết message có được nén hay không |
| Message length | 4 byte | Độ dài payload tiếp theo |
| Message payload | Theo độ dài | Dữ liệu Protobuf đã serialize |

Năm byte đầu là phần header framing của message gRPC, không phải HTTP/2 header. Payload chứa message Protobuf. Nếu bật compression, cờ nén và payload phải được diễn giải theo cấu hình gRPC tương ứng.

Một message gRPC có thể trải qua nhiều DATA frame; phía nhận ghép dữ liệu theo framing để khôi phục message hoàn chỉnh. Vì thế:

- Một HTTP/2 DATA frame không đồng nghĩa một Protobuf message.
- Một Protobuf message không nhất thiết vừa đúng một DATA frame.
- Số HTTP/2 frame không xác định method là unary hay streaming.

## 6. HTTP/2 connection multiplex nhiều RPC

HTTP/2 hỗ trợ **multiplexing**: nhiều stream độc lập có thể cùng tồn tại trên một connection. Ví dụ cùng một client có thể gọi **GetItem** cho hai mã sản phẩm và gọi một method khác gần như đồng thời. Các RPC đó dùng những HTTP/2 stream ID khác nhau nhưng có thể dùng chung TCP connection.

~~~mermaid
flowchart TB
    C["Một HTTP/2 connection"] --> S1["Stream 1: unary GetItem"]
    C --> S3["Stream 3: unary GetItem"]
    C --> S5["Stream 5: server streaming WatchItem"]
    S1 --> R1["1 request / 1 response"]
    S3 --> R3["1 request / 1 response"]
    S5 --> R5["1 request / nhiều response"]
~~~

Các stream là độc lập ở tầng HTTP/2, nhưng vẫn chia sẻ tài nguyên connection và mạng. Multiplexing không có nghĩa tất cả RPC phải là streaming ở tầng Protobuf; hai unary RPC đồng thời vẫn là hai lời gọi unary, mỗi lời gọi có một HTTP/2 stream.

HTTP/2 stream cũng có trạng thái đóng một chiều. Client gửi xong request có thể kết thúc chiều gửi, trong khi server vẫn đang trả response. Với unary, điều này diễn ra tự nhiên sau request đơn; server tiếp tục gửi response và trailers để hoàn tất RPC.

## 7. Trạng thái kết thúc: HTTP/2 END_STREAM và gRPC status

Hai tín hiệu này liên quan nhưng không đồng nghĩa:

- **HTTP/2 END_STREAM** đánh dấu phía gửi đã kết thúc việc gửi frame trên chiều tương ứng của HTTP/2 stream.
- **gRPC status** biểu thị kết quả của lời gọi ở tầng gRPC, ví dụ **OK**, **INVALID_ARGUMENT** hoặc **UNAVAILABLE**.

Thông thường, gRPC server gửi status trong **trailers** và kết thúc stream HTTP/2. Do đó, nhìn thấy request đã kết thúc chiều gửi không có nghĩa RPC đã hoàn thành; client vẫn có thể đang đợi response và trailers từ server.

Với unary:

1. Client gửi request message rồi kết thúc chiều gửi.
2. Server xử lý request.
3. Server gửi response message nếu thành công.
4. Server gửi trailers chứa **grpc-status**, sau đó kết thúc stream.

Nếu server trả **INVALID_ARGUMENT**, có thể không có response message. Client nhận lỗi qua API gRPC, ví dụ **StatusRuntimeException** đối với blocking stub. Không nên chỉ dựa vào việc có DATA frame hay HTTP status để kết luận nghiệp vụ thành công; cần đọc **gRPC status**.

## 8. Quan sát và chẩn đoán đúng tầng

Khi debug một unary RPC, hãy phân biệt các câu hỏi:

| Câu hỏi | Nơi cần quan sát |
| --- | --- |
| Client gọi method nào? | RPC path, ví dụ **/demo.catalog.v1.CatalogService/GetItem** |
| Lời gọi có tạo transport stream không? | HTTP/2 stream ID và trạng thái connection |
| Có bao nhiêu request/response ứng dụng? | gRPC message cardinality, log/interceptor ở mức method |
| Lời gọi kết thúc thành công không? | gRPC trailers và **grpc-status** |
| Vì sao lời gọi chậm? | Deadline, latency, server processing, network và queue |

**Metadata** và **interceptor** thường hoạt động ở mức RPC, có thể dùng để gắn request ID, xác thực, trace và đo thời gian. Đối với unary, ghi nhận method, status và latency thường đủ để theo dõi cardinality. Khi xem trace/network capture, cần tránh diễn giải một HTTP/2 stream thành một streaming RPC theo nghĩa Protobuf.

Trong production, bảo vệ transport bằng **TLS**; không ghi token hoặc dữ liệu nhạy cảm vào log. Deadline giúp giới hạn thời gian chờ, còn gRPC status giúp client phân loại kết quả. Các yếu tố này không thay đổi việc method là unary hay streaming.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu chính xác |
| --- | --- |
| Unary không có stream | Unary vẫn dùng một HTTP/2 stream để truyền RPC |
| Không có **stream** trong .proto thì không dùng HTTP/2 stream | Từ khóa Protobuf quyết định số message ứng dụng; HTTP/2 stream vẫn tồn tại |
| Một HTTP/2 stream luôn chứa nhiều message | Unary thường có một request và một response message trên stream đó |
| Một DATA frame là một Protobuf message | Message có thể được chia qua nhiều DATA frame |
| **repeated** nghĩa là streaming | **repeated** là nhiều phần tử trong một message; streaming là nhiều message trong một RPC |
| Client gửi xong request thì RPC đã hoàn thành | RPC còn chờ server response và gRPC status |
| HTTP status 200 đồng nghĩa nghiệp vụ thành công | Cần kiểm tra gRPC status trong trailers |

## 10. Ghi nhớ và tự kiểm tra

Khai báo unary:

~~~proto
rpc GetItem(GetItemRequest) returns (GetItemResponse);
~~~

Không có từ khóa **stream** ở hai phía nên method có cardinality **một request, một response**. Tuy vậy, gRPC vẫn sử dụng **một HTTP/2 stream cho RPC đó**. HTTP/2 stream là cơ chế vận chuyển; từ khóa **stream** trong **.proto** quyết định một phía của API có thể gửi nhiều message hay không.

Tự kiểm tra:

1. Một unary RPC có thể được gửi trên HTTP/2 stream không? Vì sao?
2. Hai unary RPC chạy đồng thời trên cùng HTTP/2 connection sẽ dùng một hay hai HTTP/2 stream?
3. Một message Protobuf chứa trường **repeated** với 500 phần tử có làm method unary thành streaming không?
4. Vì sao một gRPC message có thể chiếm nhiều HTTP/2 DATA frame?
5. Khi client đã gửi xong request nhưng chưa nhận trailers, RPC đã hoàn tất chưa?

Nếu phân biệt đúng **cardinality của message ở tầng gRPC** với **stream vận chuyển ở tầng HTTP/2**, người học sẽ đọc hợp đồng Protobuf chính xác hơn, hiểu API Java do gRPC sinh ra và chẩn đoán lưu lượng mạng mà không nhầm unary với streaming.
