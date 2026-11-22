# Khi server streaming phù hợp

## 1. Bắt đầu từ nhu cầu nghiệp vụ, không bắt đầu từ từ khóa `stream`

Trong module **SPRING_GRPC**, người học xây dựng dịch vụ gRPC trên hệ sinh thái Spring: khai báo hợp đồng **Protocol Buffers**, sinh mã Java, hiện thực client/server cho unary và streaming RPC, rồi giải quyết metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát độ tin cậy. Ở chương **Server streaming**, câu hỏi thiết kế quan trọng là: **khi nào một yêu cầu nên tạo ra một luồng nhiều phản hồi, thay vì trả đúng một phản hồi?**

**Server streaming RPC** có hướng truyền thông điệp sau:

- Client gửi **một request** để xác định tác vụ, tập dữ liệu hoặc chủ đề cần theo dõi.
- Server gửi **không, một hoặc nhiều response** theo thời gian, trên cùng một RPC.
- Server kết thúc RPC bằng trạng thái thành công, lỗi hoặc RPC dừng do hủy/deadline/kết nối.

Trong protobuf, chữ `stream` đặt ở phía response:

~~~proto
service ReportService {
  rpc WatchReport(WatchReportRequest) returns (stream ReportEvent);
}
~~~

Ví dụ: client gửi một `WatchReportRequest` chứa mã công việc, rồi nhận lần lượt các sự kiện “đã xếp hàng”, “đã xử lý 20%”, “đã xử lý 70%”, “hoàn tất”. Client có thể cập nhật giao diện hay xử lý kết quả ngay khi từng sự kiện đến, thay vì chờ đến lúc toàn bộ công việc hoàn tất.

Điểm làm server streaming có ích không chỉ là **số lượng response**, mà còn là **thời điểm response có giá trị**. Nếu người nhận chỉ sử dụng dữ liệu sau khi đủ toàn bộ kết quả, chuyển thành streaming có thể không đem lại lợi ích.

## 2. Năm dấu hiệu nên chọn server streaming

### 2.1. Một request đủ mô tả trọn phiên làm việc

Sau request mở đầu, server có đủ ngữ cảnh để tự tiếp tục phát dữ liệu: mã công việc cần theo dõi, điều kiện lọc log, khoảng thời gian cần quét, hoặc mã sản phẩm cần nhận cập nhật.

Ví dụ:

~~~text
Client: WatchJob(job_id = "job-731")
Server: QUEUED
Server: RUNNING, 15%
Server: RUNNING, 55%
Server: SUCCEEDED, 100%
Server: End of RPC
~~~

Client không phải gửi thêm thông điệp để server chuyển sang bước tiếp theo. Ngược lại, nếu client phải liên tục gửi lệnh “tạm dừng”, “đổi bộ lọc”, “tiếp tục” trong **cùng một phiên RPC**, bidirectional streaming có thể phù hợp hơn. Một yêu cầu mới độc lập vẫn có thể được gửi bằng RPC khác, nhưng điều đó khác với trao đổi hai chiều liên tục trên cùng một stream.

### 2.2. Dữ liệu xuất hiện từng phần và từng phần có ích ngay

Những trường hợp thường gặp:

- **Theo dõi tiến độ:** số bản ghi đã xử lý, giai đoạn tác vụ, cảnh báo phát sinh.
- **Gửi kết quả theo đợt:** quét nhiều bản ghi và trả dần khi mỗi đợt sẵn sàng.
- **Theo dõi sự kiện:** cập nhật trạng thái đơn hàng, thay đổi tồn kho hoặc log mới.
- **Tính toán dài:** chuyển từng đoạn kết quả đã hoàn thành cho client.

Giả sử server cần 30 giây để xử lý 3.000 bản ghi, nhưng có thể tạo ra 100 bản ghi đầu tiên sau 1 giây. Với unary trả toàn bộ danh sách, client thường chỉ nhận nội dung sau khi server hoàn tất một response. Với server streaming, client có thể bắt đầu xử lý lô đầu tiên sau khoảng 1 giây (thời gian chỉ mang tính minh họa).

Ta cần phân biệt hai thước đo:

| Thước đo | Unary trả toàn bộ | Server streaming |
|---|---|---|
| Thời gian đến dữ liệu đầu tiên | Thường sau khi đủ kết quả | Có thể ngay khi phần đầu sẵn sàng |
| Thời gian có **đầy đủ** kết quả | Sau một response | Sau message cuối và trạng thái kết thúc |
| Dung lượng cần giữ ở server | Có thể lớn nếu phải gom danh sách | Có thể nhỏ khi xử lý và buffer có giới hạn |
| Độ phức tạp quản lý vòng đời | Thấp hơn | Cao hơn: flow control, hủy, timeout, dữ liệu dở dang |

**Streaming không tự bảo đảm nhanh hơn về tổng thời gian.** Server vẫn phải thực hiện cùng khối lượng xử lý; lợi ích thường nằm ở latency của kết quả đầu tiên, khả năng xử lý nối tiếp và giảm nhu cầu gom toàn bộ dữ liệu trong bộ nhớ.

### 2.3. Số message không cố định hoặc kết quả sinh ra trong thời gian dài

Một truy vấn có thể trả 2, 20 hay 2.000 kết quả; hoặc sự kiện mới có thể xuất hiện bất cứ lúc nào. Server streaming giúp client xử lý từng message mà không phải biết trước tổng số message.

Có hai mô hình cần phân biệt:

| Mô hình | Vòng đời | Ví dụ | Điều kiện kết thúc |
|---|---|---|---|
| **Luồng hữu hạn** | Trả dần một tập kết quả đã xác định | Đọc 10.000 bản ghi, gửi các bước xử lý | Hết dữ liệu, tác vụ hoàn thành |
| **Luồng theo dõi** | Chờ sự kiện mới, có thể chạy lâu | Theo dõi log hoặc tiến độ một công việc đang chạy | Client hủy, công việc kết thúc, deadline hoặc server đóng luồng |

Với luồng theo dõi dài, cần tính chi phí kết nối mở và phương án khôi phục. Với tập dữ liệu hữu hạn, cần đánh giá thêm tính nhất quán của snapshot, giới hạn dữ liệu và tính phù hợp của phân trang.

### 2.4. Client thực sự cần nhận liên tục

Một hệ thống backend tiêu thụ sự kiện và cập nhật trạng thái theo thời gian thực có thể tận dụng server streaming. Nhưng nếu giao diện chỉ mở trang báo cáo một lần và chỉ hiển thị khi có đủ số liệu, unary là phương án dễ vận hành hơn.

Ví dụ, hãy hỏi: **“Nếu message đầu tiên đến sớm hơn 10 giây nhưng kết quả cuối vẫn đến cùng thời điểm, người dùng có nhận được lợi ích rõ rệt không?”** Nếu không, đó là dấu hiệu cần cân nhắc lại.

### 2.5. Hạ tầng và client có thể duy trì RPC HTTP/2

gRPC server streaming sử dụng kết nối gRPC và cơ chế HTTP/2, nên các bên liên quan phải hỗ trợ truyền message dần, deadline và hủy. Backend Java giao tiếp Java thường là tình huống thuận lợi. Với trình duyệt, thiết bị di động hoặc mạng đi qua gateway/proxy, cần kiểm tra hỗ trợ **gRPC-Web, proxy streaming, timeout và buffer**; không mặc định mọi client và proxy đều vận hành giống client gRPC Java thuần.

Nếu kênh chính là trình duyệt và yêu cầu chỉ nhận sự kiện một chiều, **Server-Sent Events (SSE)** qua HTTP có thể thuận tiện hơn. Nếu cần trao đổi liên tục hai chiều trong trình duyệt, **WebSocket** là lựa chọn đáng đánh giá.

## 3. Cây quyết định chọn kiểu giao tiếp

~~~mermaid
flowchart TD
    A["Bắt đầu: một nghiệp vụ cần lấy dữ liệu"] --> B{"Client chỉ cần một kết quả cuối?"}
    B -- "Có" --> U["Unary RPC"]
    B -- "Không" --> C{"Client cần gửi nhiều thông điệp trong cùng RPC?"}
    C -- "Có" --> D{"Server cũng cần phản hồi dần?"}
    D -- "Có" --> BI["Bidirectional streaming"]
    D -- "Không" --> CI["Client streaming"]
    C -- "Không" --> E{"Dữ liệu có giá trị khi đến từng phần?"}
    E -- "Không" --> F["Unary / phân trang tùy nhu cầu"]
    E -- "Có" --> G{"Cần lịch sử bền vững và phát lại sau ngắt kết nối?"}
    G -- "Không" --> SS["Server streaming"]
    G -- "Có" --> H["Thiết kế lưu lịch sử/cursor; có thể dùng server streaming làm kênh chuyển"]
~~~

Cây quyết định đưa ra **ứng viên**, chưa phải quyết định triển khai cuối cùng. Cần đánh giá thêm tần suất cập nhật, quy mô client đồng thời, khả năng khôi phục, bảo mật và các yêu cầu hạ tầng.

| Lựa chọn | Nên dùng khi | Không nên chọn chỉ vì |
|---|---|---|
| **Unary RPC** | Một yêu cầu, một kết quả cuối; lỗi và hoàn thành tương đối đơn giản | Tất cả phương thức trong hệ thống đều đang dùng unary |
| **Unary có `repeated`** | Một danh sách nhỏ, cần xem/trả cùng lúc | Muốn gọi danh sách là “streaming” dù chỉ có một message |
| **Unary phân trang** | Client điều khiển trang kế tiếp, cần truy cập ngẫu nhiên, cache hoặc resume theo trang | Dữ liệu có nhiều phần tử thì bắt buộc phải streaming |
| **Server streaming** | Một yêu cầu, các kết quả hữu ích được gửi từng phần, client chỉ nhận thêm | Muốn tiết kiệm thời gian mà không có dữ liệu sớm thực tế |
| **Client streaming** | Client gửi nhiều message, server tổng hợp thành một kết quả | Server cần trả nhiều cập nhật cho một request |
| **Bidirectional streaming** | Hai phía chủ động gửi nhiều message trong một RPC | Chỉ cần server gửi các cập nhật một chiều |
| **Message broker + consumer** | Cần lưu bền, phát lại, tách producer-consumer, fan-out lớn | Chỉ cần đẩy vài cập nhật tạm thời trong một RPC |

**So sánh quan trọng:** `repeated ReportEvent events = 1;` trong một message unary *không* giống `returns (stream ReportEvent)`. Trường `repeated` làm client nhận **một** response chứa danh sách; server streaming làm client nhận **nhiều** response riêng biệt theo tiến độ.

## 4. Các tình huống sử dụng thực tế

### Tình huống A — Theo dõi tiến độ một công việc dài

Một hệ thống báo cáo xử lý dữ liệu mất vài chục giây đến vài phút. Client cần biết công việc còn đang chạy, đang lỗi hay đã hoàn tất.

**Phù hợp:** sau khi đã có mã công việc, client có thể gửi một `WatchReport(job_id)`; server phát tiến độ mà không cần client thăm dò liên tục. Dữ liệu từng bước có giá trị ngay cho giao diện, vận hành và theo dõi lỗi.

**Điều cần lưu ý:** nếu công việc phải tiếp tục chạy ngay cả khi người dùng đóng ứng dụng, nên tách **lệnh tạo công việc** (unary) khỏi **luồng theo dõi** (server streaming). Ngắt stream không nên tự động hủy công việc nền nếu sản phẩm không yêu cầu. Đây là quyết định về vòng đời nghiệp vụ.

### Tình huống B — Trả dần các kết quả truy vấn lớn

Một dịch vụ tìm kiếm hoặc quét sự kiện trả về hàng nghìn bản ghi, có thể xử lý từng bản ghi khi chúng xuất hiện.

**Phù hợp:** client tiêu thụ tuần tự và không cần tải cả tập dữ liệu vào bộ nhớ. Streaming có thể cho phép kết quả đầu tiên xuất hiện nhanh và giảm bộ nhớ đệm nếu server đọc dữ liệu theo cursor/chunk thực sự.

**Cân nhắc unary phân trang:** nếu người dùng cần nhảy đến trang 8, quay lại trang 3, chia sẻ liên kết trang hoặc giữ cache theo trang. Phân trang có cursor cũng thường thuận tiện hơn cho retry và resume. Streaming không tự giải quyết bài toán snapshot nhất quán khi dữ liệu nguồn thay đổi trong lúc đọc.

### Tình huống C — Theo dõi log, audit hoặc trạng thái thay đổi

Một công cụ nội bộ yêu cầu theo dõi log của một dịch vụ trong lúc điều tra sự cố.

**Phù hợp:** request ban đầu chứa bộ lọc và server gửi từng bản ghi khi xuất hiện. Client có thể hiển thị ngay, thay vì gọi polling hàng giây.

**Cân nhắc thiết kế khác:** nếu yêu cầu là truy xuất log từ nhiều tháng trước, có tìm kiếm và lưu trữ bền, cần một hệ thống truy vấn/log storage. Streaming chỉ là đường chuyển kết quả đến người xem; bản thân RPC không phải kho log.

### Tình huống D — Cập nhật trạng thái theo thời gian thực

Ứng dụng backend cần nhận cập nhật đơn hàng, số lượng tồn kho hoặc thông số thiết bị.

**Phù hợp:** một subscription có bộ lọc rõ ràng, mỗi update độc lập có ích và độ trễ quan trọng.

**Cần cân nhắc lại:** hàng triệu subscriber, nhu cầu gửi lại mọi sự kiện sau khi offline hoặc tiêu thụ từ nhiều hệ thống khác nhau. Lúc này có thể cần pub/sub hay broker có retention, sau đó dùng gRPC streaming làm lớp giao tiếp cho một số client.

### Tình huống E — Phản hồi do máy chủ sinh dần

Một engine suy luận hay xử lý văn bản tạo các đoạn kết quả theo thời gian. Client muốn trình bày khi từng đoạn được tạo.

**Phù hợp:** người dùng thấy nội dung sớm và có thể phản hồi/hủy ngay, trong khi client không cần gửi thêm thông điệp trong cùng RPC.

**Không đương nhiên phù hợp:** kết quả bắt buộc được kiểm chứng toàn bộ trước khi sử dụng (chẳng hạn nghiệp vụ chuyển tiền, phê duyệt hoặc dữ liệu cần tính nguyên tử). Với các thao tác đó, server nên trả quyết định cuối cùng có trạng thái rõ ràng; cập nhật tiến độ nếu cần là luồng thông tin phụ.

## 5. Ví dụ thiết kế: theo dõi tác vụ tạo báo cáo

Giả sử dịch vụ Spring gRPC cho phép khởi tạo báo cáo dài và theo dõi tiến độ. Chọn hai RPC riêng:

1. `StartReport` dạng unary: khởi động công việc nền và trả `job_id`.
2. `WatchReport` dạng server streaming: nhận `job_id` và gửi các trạng thái theo thứ tự cho đến khi công việc kết thúc hoặc subscription bị đóng.

Thiết kế này cho phép công việc sống độc lập với tuổi thọ một kết nối quan sát.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant G as Spring gRPC service
    participant J as Report job worker
    C->>G: StartReport(input)
    G->>J: Tạo job, lưu job_id
    G-->>C: StartReportReply(job_id)
    C->>G: WatchReport(job_id, after_sequence)
    G-->>C: ReportEvent(1, QUEUED, 0%)
    J-->>G: Tiến độ 25%
    G-->>C: ReportEvent(2, RUNNING, 25%)
    J-->>G: Hoàn thành
    G-->>C: ReportEvent(3, SUCCEEDED, 100%)
    G-->>C: onCompleted / gRPC OK
~~~

### 5.1. Định nghĩa hợp đồng

~~~proto
syntax = "proto3";

package report.v1;

option java_multiple_files = true;
option java_package = "example.report.rpc";

service ReportService {
  rpc StartReport(StartReportRequest) returns (StartReportReply);
  rpc WatchReport(WatchReportRequest) returns (stream ReportEvent);
}

message StartReportRequest {
  string report_type = 1;
}

message StartReportReply {
  string job_id = 1;
}

message WatchReportRequest {
  string job_id = 1;
  // Chỉ lấy event có sequence lớn hơn giá trị này.
  // Server PHẢI hỗ trợ lưu/truy hồi lịch sử nếu công bố khả năng resume.
  int64 after_sequence = 2;
}

enum ReportPhase {
  REPORT_PHASE_UNSPECIFIED = 0;
  QUEUED = 1;
  RUNNING = 2;
  SUCCEEDED = 3;
  FAILED = 4;
}

message ReportEvent {
  string job_id = 1;
  int64 sequence = 2;   // Tăng đơn điệu theo từng job.
  ReportPhase phase = 3;
  int32 percent = 4;    // 0..100 nếu có thể ước tính.
  string message = 5;
}
~~~

Khi dùng Protocol Buffers, lớp `ReportServiceGrpc` và các message được sinh từ proto thông qua `protoc` cùng gRPC Java plugin của bản build. Phần triển khai service được tích hợp với Spring theo cách đăng ký bean/service của thư viện Spring gRPC đang dùng.

Ý nghĩa của các quyết định hợp đồng:

- `job_id` giúp việc quan sát tách khỏi việc khởi chạy, đồng thời cung cấp khóa kiểm tra quyền truy cập.
- `sequence` giúp client phát hiện bản ghi trùng, sắp xếp và nhận biết khoảng thiếu sau khi kết nối lại.
- `after_sequence` là **cam kết cần triển khai**, không phải khả năng tự có của gRPC. Server cần lưu lịch sử đủ lâu, đọc các bản ghi sau checkpoint và nối với luồng sự kiện trực tiếp mà không tạo lỗ hổng chuyển tiếp.
- `FAILED` là **trạng thái nghiệp vụ** của job. Nếu server truyền được thông báo job thất bại một cách bình thường, có thể gửi event `FAILED` rồi kết thúc RPC bằng gRPC `OK`. Ngược lại, nếu bản thân RPC hỏng (không kết nối được kho dữ liệu, không có quyền xem job, lỗi hệ thống), dùng gRPC status thích hợp như `UNAVAILABLE`, `PERMISSION_DENIED` hoặc `INTERNAL`.

### 5.2. Tiêu thụ stream từ client Java

Đoạn dưới giả định ứng dụng đã có `ManagedChannel channel` và `jobId`, các lớp Java đã được sinh từ proto. Ví dụ dùng blocking stub để tập trung vào ý nghĩa của luồng:

~~~java
long lastProcessedSequence = 0L; // Khôi phục từ checkpoint đã lưu nếu có.

WatchReportRequest request = WatchReportRequest.newBuilder()
        .setJobId(jobId)
        .setAfterSequence(lastProcessedSequence)
        .build();

var updates = ReportServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(60, TimeUnit.SECONDS)
        .watchReport(request);

try {
    while (updates.hasNext()) {
        ReportEvent event = updates.next();

        if (event.getSequence() <= lastProcessedSequence) {
            continue; // Loại bản ghi trùng khi được phát lại.
        }

        System.out.printf("[%s] #%d: %s (%d%%)%n",
                event.getJobId(),
                event.getSequence(),
                event.getPhase(),
                event.getPercent());

        // Với hệ thống thật, ghi checkpoint sau khi đã xử lý thành công.
        lastProcessedSequence = event.getSequence();
    }
} catch (StatusRuntimeException error) {
    System.err.println("WatchReport failed: " + error.getStatus());
    // Sau lỗi, có thể retry từ checkpoint nếu hợp đồng hỗ trợ replay.
}
~~~

Các kiểu cần import trong ngữ cảnh này: `WatchReportRequest`, `ReportEvent`, `ReportServiceGrpc`, `TimeUnit` và `StatusRuntimeException`. Channel nên được Spring quản lý/tái sử dụng, nhất là khi nhiều RPC dùng chung kết nối.

**Quan trọng:** deadline 60 giây ở ví dụ áp dụng cho **toàn bộ RPC**, không được đặt lại sau mỗi event. Job chạy lâu hơn có thể cần thời hạn phù hợp, cơ chế reconnect từ checkpoint và giới hạn retry có backoff. Nếu client cần điều khiển việc hủy giữa chừng, dùng API cancellation của gRPC; hủy `WatchReport` không đồng nghĩa với xóa job trong thiết kế này.

### 5.3. Trách nhiệm của Spring gRPC server

Server cần thực hiện các bước sau theo thứ tự nghiệp vụ phù hợp:

1. Kiểm tra `job_id`, xác thực caller qua metadata/interceptor và phân quyền truy cập công việc.
2. Kiểm tra job có tồn tại và kho lịch sử còn đủ để đáp ứng `after_sequence` hay không; nếu không, trả status hoặc cung cấp đường lấy snapshot theo hợp đồng.
3. Kết nối được phần **đọc lịch sử** với **đăng ký sự kiện mới**, tránh bỏ sót event trong khoảng giữa hai thao tác.
4. Gửi message bằng `StreamObserver.onNext(...)` theo đúng thứ tự, không ghi đồng thời lên cùng observer từ nhiều thread không được điều phối.
5. Khi job đến trạng thái cuối, gửi event kết thúc nghiệp vụ và `onCompleted()` một lần. Khi server gặp lỗi RPC, gọi `onError(...)` với `Status` thích hợp.
6. Khi client hủy, deadline hết hoặc mất kết nối, hủy subscription, timer và buffer dành riêng cho RPC; quyết định tiếp tục hoặc hủy **job nền** dựa trên chính sách nghiệp vụ đã thiết kế.

Khi nhiều worker cùng sinh sự kiện, cần một cơ chế thứ tự/chốt sequence ở tầng dữ liệu. Một gRPC stream giữ **thứ tự message được gửi trên stream đó**, nhưng không tự đặt một thứ tự toàn cục cho sự kiện đến từ nhiều nguồn và cũng không tự lưu lại những message đã mất khi kết nối gián đoạn.

## 6. Khi nào **không** nên chọn server streaming?

### 6.1. Chỉ có một kết quả ngắn, cần trả trọn vẹn

Ví dụ `GetProductById`, xác minh quyền truy cập, tính thuế cho một đơn hàng hoặc tra cứu một cấu hình. Unary có hợp đồng đơn giản và dễ gọi, xử lý retry, cache và lỗi.

### 6.2. Người dùng quyết định từng lần lấy dữ liệu

Ví dụ lưới dữ liệu có nút “Trang tiếp”, bộ lọc thay đổi thường xuyên và yêu cầu chia sẻ URL của từng trang. Unary phân trang với page token/cursor thường phù hợp hơn luồng dài. Client kiểm soát kích thước kết quả, ngữ cảnh cache và điểm tiếp tục.

### 6.3. Cần lịch sử bền vững, phát lại cho nhiều nhóm tiêu thụ

RPC streaming chỉ duy trì đường truyền trong thời gian kết nối tồn tại. Nếu bắt buộc lưu hàng triệu event, replay theo offset, nhiều consumer group, xử lý khi client offline và quy định thời hạn retention, nên dùng hạ tầng lưu trữ/broker phù hợp. Server streaming vẫn có thể là API đọc từ hạ tầng đó, nhưng không thay thế cơ chế lưu bền.

### 6.4. Client thường xuyên gửi thay đổi trong cùng phiên

Ví dụ liên tục gửi vị trí thiết bị, cập nhật cấu hình lọc trong phiên hoặc điều khiển streaming hai chiều. Nếu phía client cũng tạo nhiều message trên cùng RPC, cân nhắc bidirectional streaming. Nếu chỉ client gửi nhiều message và server trả một kết quả tổng hợp, cân nhắc client streaming.

### 6.5. Không thể chấp nhận kết quả dở dang hoặc không có chiến lược khôi phục

Server streaming có thể đã gửi 9 message rồi kết thúc với `UNAVAILABLE` ở message thứ 10. Client phải phân biệt **đã xử lý một phần** với **RPC hoàn tất thành công**. Nếu nghiệp vụ yêu cầu tính nguyên tử, toàn bộ kết quả cần được kiểm chứng trước khi áp dụng, hoặc việc lặp lại có hậu quả, chỉ dùng streaming khi đã thiết kế checkpoint, idempotency, transaction boundary và cách thông báo kết quả cuối rõ ràng.

## 7. Đánh đổi kỹ thuật phải xác định trước khi triển khai

### Flow control và backpressure

gRPC trên HTTP/2 có flow control, nhưng đây không phải cơ chế tự động bảo vệ mọi hàng đợi ứng dụng. Client đọc chậm vẫn có thể khiến buffer server tăng nếu producer ghi nhanh hơn tốc độ truyền.

Ở phía server gRPC Java, `ServerCallStreamObserver.isReady()` và `setOnReadyHandler(...)` giúp ứng dụng quan sát thời điểm đường ghi có thể tiếp nhận thêm dữ liệu. **Không được diễn giải `isReady() == false` thành lệnh bỏ dữ liệu một cách vô điều kiện.** Với log best-effort có thể coalescing hoặc bỏ bản cập nhật cũ theo chính sách rõ ràng; với dòng sự kiện phải đầy đủ cần hàng đợi có giới hạn, backpressure lên upstream hoặc cơ chế phát lại.

### Lifetime, deadline và hủy

Mỗi stream mở chiếm tài nguyên: trạng thái RPC, HTTP/2 stream, callback/subscription, buffer và tài nguyên quan sát. Một client có thể biến mất khi mạng đổi mà ứng dụng chưa kịp thấy sự kiện đóng. Server nên xử lý cancel, deadline và cleanup ở mọi đường kết thúc. Đặt thời hạn tối đa/idle timeout thích hợp với nghiệp vụ, đồng thời tránh một cấu hình proxy cắt mọi luồng sau một thời gian quá ngắn.

### Thông điệp kết thúc và lỗi

Định nghĩa rõ:

- “Hoàn thành nghiệp vụ” là một **sự kiện dữ liệu** hay chỉ là stream `onCompleted()`?
- “Job FAILED” có phải là lỗi nghiệp vụ được báo qua event, hay là gRPC error?
- Khi nhận một số message rồi RPC bị lỗi, client có được phép sử dụng phần dữ liệu đã nhận không?
- Nếu client retry, event cũ có thể được gửi lại và client xử lý trùng thế nào?

Nếu không thống nhất những điều này, hai phía có thể diễn giải cùng một luồng khác nhau mặc dù proto hợp lệ.

### Metadata, interceptor, TLS

Metadata phục vụ danh tính caller, access token, correlation/trace ID và thông tin điều khiển ở cấp RPC; các event thay đổi liên tục thuộc payload protobuf. Với Spring gRPC, interceptor thường thích hợp để xác thực, ghi log mã kết thúc và đo thời lượng gọi. Luồng lâu cần kiểm tra token hết hạn, quyền truy cập bị thu hồi, dữ liệu nhạy cảm và chính sách ngắt phiên.

TLS bảo vệ dữ liệu gRPC trên mạng. Ví dụ dùng plaintext cục bộ trong lúc phát triển không nên được sao chép nguyên xi lên môi trường thật. Cần xác minh chứng chỉ máy chủ; nếu hạ tầng yêu cầu, triển khai mTLS. Quyền xem `job_id` phải được xác minh cho từng caller, không mặc định ai biết ID cũng được xem.

### Hiệu năng và khả năng mở rộng

Server streaming có thể giảm số lần polling nhưng tăng số RPC mở đồng thời. Chi phí phụ thuộc tốc độ event, kích thước message, số client, cơ chế buffer, cách đăng ký sự kiện và hạ tầng mạng. Đừng tạo một thread riêng bận chờ cho mỗi RPC trong hệ thống có hàng nghìn subscription; dùng executor, scheduler hoặc hệ thống publisher phù hợp và giới hạn tài nguyên.

## 8. Đo lường thế nào để biết lựa chọn này hiệu quả?

Để quyết định có nên dùng server streaming, xây dựng một thử nghiệm nhỏ với khối lượng gần thực tế, so sánh unary/polling và server streaming theo cùng mục tiêu nghiệp vụ.

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| **Time to first response** | Client có nhận phần hữu ích đầu tiên sớm hơn không? |
| **End-to-end completion** | Tổng thời gian nhận đủ kết quả có bị kéo dài không? |
| **Thời gian trễ của từng event** | Khi sự kiện phát sinh, mất bao lâu để client thấy? |
| **Active RPC / subscriptions** | Mỗi instance chịu được bao nhiêu luồng mở? |
| **Bộ nhớ / queue depth** | Client chậm có gây tích lũy dữ liệu không? |
| **Tỷ lệ CANCELLED / DEADLINE_EXCEEDED / UNAVAILABLE** | Luồng bị đóng vì người dùng, timeout hay lỗi hạ tầng? |
| **Số message và bytes mỗi RPC** | Tải và chi phí serialization tăng bao nhiêu? |
| **Tỷ lệ retry, gap, duplicate** | Cơ chế tiếp tục và xử lý lặp hoạt động ra sao? |

Với Spring gRPC, có thể tích hợp metrics/tracing qua interceptor và hệ thống quan sát của ứng dụng. Khi báo cáo độ tin cậy, nên tách **job FAILED** khỏi **RPC error**: một công việc nghiệp vụ thất bại nhưng server thông báo chính xác qua stream vẫn có thể là một RPC truyền thông thành công.

## 9. Kiểm thử các giả định quyết định dùng streaming

Ngoài kiểm thử proto, sinh stub Java và kết nối Spring gRPC, hãy kiểm chứng những lợi ích đã dùng để chọn streaming:

1. **Phát dần:** tạo nguồn dữ liệu có khoảng dừng giữa các event; chứng minh client nhận và xử lý event đầu tiên trước khi nguồn sinh event cuối, chứ không đợi gom danh sách.
2. **Thứ tự:** gửi nhiều event và xác nhận `sequence` tăng đúng theo hợp đồng; với nguồn song song, kiểm tra cơ chế tuần tự hóa.
3. **Kết thúc đúng:** test không có event, một event, nhiều event, job `SUCCEEDED` và `FAILED`, `onCompleted()` hoặc `onError(...)` đúng một lần.
4. **Ngắt giữa chừng:** client hủy hoặc deadline hết; xác minh subscription, timer, cursor và bộ nhớ dành cho RPC được giải phóng.
5. **Client chậm:** hạn chế tốc độ đọc; kiểm tra bộ nhớ và giới hạn buffer không tăng vô hạn.
6. **Khôi phục:** ngắt kết nối sau `sequence = 5`, reconnect với `after_sequence = 5`; xác nhận không mất sự kiện cần bảo toàn và client chịu được bản ghi trùng.
7. **Bảo mật:** không được xem job của người khác, metadata xác thực thiếu/sai, các trường hợp TLS và interceptor.
8. **Tải đồng thời:** đo nhiều luồng mở và tốc độ phát; theo dõi CPU, heap, thread, kết nối, độ trễ và tỷ lệ lỗi.

Kiểm thử gRPC **in-process** hữu ích để xác minh stub, serialization, status và thứ tự message. Kiểm thử tích hợp khởi động Spring context giúp xác minh service registration, cấu hình interceptor và dependency. Các tình huống TLS, proxy, hủy mạng và thời gian chờ thực cần được thử trên môi trường có stack truyền thông tương ứng.

## 10. Checklist trước khi quyết định

Trước khi chọn `returns (stream Response)`, hãy trả lời được:

- [ ] Sau request đầu tiên, server có đủ dữ liệu để tự phát các response tiếp theo không?
- [ ] Client được lợi rõ rệt khi nhận thông điệp đầu tiên sớm hoặc nhận cập nhật theo thời gian không?
- [ ] Các response có thể được xử lý riêng lẻ, theo thứ tự và với quy tắc hoàn thành rõ ràng không?
- [ ] Đã xác định khi nào stream kết thúc, hủy, hết deadline và có lỗi chưa?
- [ ] Đã có chiến lược backpressure và giới hạn bộ nhớ/tài nguyên cho client chậm chưa?
- [ ] Nếu cần reconnect/replay, đã có sequence, checkpoint và nguồn dữ liệu lưu bền chưa?
- [ ] Client, gateway và proxy có truyền được gRPC streaming theo yêu cầu không?
- [ ] Đã xét các lựa chọn unary, phân trang, SSE/WebSocket hoặc broker dựa trên nhu cầu thật chưa?
- [ ] Đã có phương án xác thực, phân quyền, TLS, kiểm thử và observability chưa?

**Kết luận:** Server streaming phù hợp nhất khi **một yêu cầu dẫn đến nhiều kết quả có ích theo thời gian**, client chủ yếu nhận, việc hiển thị hoặc xử lý sớm tạo giá trị, và hệ thống quản lý được kết nối kéo dài cùng dữ liệu dở dang. Trong Spring gRPC, lựa chọn đúng không nằm ở việc thêm `stream` vào proto, mà ở thiết kế trọn vẹn hợp đồng, vòng đời RPC, luồng dữ liệu, khôi phục và vận hành.
