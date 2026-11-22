# Chọn deadline theo loại RPC

Không nên dùng cùng một deadline cho mọi RPC. Một lời gọi unary thường hoàn tất sau một request và một response; client streaming có thể tải nhiều chunk; server streaming có thể phát một tập kết quả lớn hoặc giữ subscription lâu; bidirectional streaming có thể duy trì một phiên trao đổi hai chiều. Mỗi loại có thời gian sống, tốc độ dữ liệu và cách phục hồi khác nhau.

Trong **Spring gRPC**, deadline được đặt trên stub gRPC Java và áp dụng cho **toàn bộ RPC**. Cách chọn phù hợp là bắt đầu từ SLA hoặc thời gian người dùng chấp nhận, đo latency/throughput thực tế, sau đó phân bổ ngân sách theo loại RPC và các service downstream. Với stream dài hạn, cần xác định rõ thời gian sống phiên và chính sách reconnect; không để stream chờ vô hạn chỉ vì quên đặt deadline.

## 1. Nguyên tắc chung: ngân sách theo hành vi của lời gọi

Deadline là mốc kết thúc của toàn bộ RPC, không phải thời gian xử lý riêng ở server. Ngân sách có thể bị tiêu thụ bởi chờ channel/tài nguyên, truyền request, hàng đợi, xử lý nghiệp vụ, downstream và truyền response.

Có thể bắt đầu bằng công thức phân bổ:

\[
D_{\text{rpc}} \leq D_{\text{caller}} - D_{\text{overhead}}
\]

Trong đó:

- **D_rpc** là ngân sách dành cho RPC đang thiết kế.
- **D_caller** là thời gian caller hoặc SLA cấp cho thao tác tổng thể.
- **D_overhead** là phần dự phòng cho gateway, queue, xử lý sau RPC và trả kết quả cho caller.

Nếu service gọi downstream, ngân sách con phải nằm trong thời gian còn lại của request cha. Không cấp lại toàn bộ timeout ban đầu ở mỗi hop.

Không chọn deadline chỉ dựa trên latency trung bình. Hãy xem p95/p99 dưới tải hợp lệ, độ biến thiên khi tải cao, kích thước request/response, thời gian chờ queue và phần dự phòng cần thiết. Deadline quá ngắn gây lỗi giả; deadline quá dài giữ tài nguyên lâu khi hệ thống gặp sự cố.

## 2. Bảng chọn deadline theo loại RPC

| Loại RPC | Đặc điểm thời gian | Cách chọn deadline |
| --- | --- | --- |
| **Unary** | Một request, một response; thường có thời gian xử lý tương đối ngắn | Dựa trên latency p95/p99, queue/network và SLA của thao tác |
| **Client streaming** | Nhiều request message, một response cuối | Tính thời gian truyền toàn bộ dữ liệu, xử lý, ghi bền và trả acknowledgement |
| **Server streaming hữu hạn** | Một request, nhiều response rồi kết thúc | Tính thời gian truy vấn, phát toàn bộ kết quả và tốc độ tiêu thụ của client |
| **Server streaming subscription** | Một request đăng ký, stream có thể kéo dài | Dùng thời gian sống phiên hữu hạn hoặc ngoại lệ có chủ đích kèm reconnect/cursor |
| **Bidirectional streaming** | Hai chiều gửi/nhận đan xen trong một phiên | Xác định giới hạn phiên, idle timeout, heartbeat và khả năng resume |

Cardinality không tự quyết định RPC phải sống bao lâu. Một server streaming export vài nghìn dòng có thể kết thúc trong vài giây; một server streaming event subscription có thể cần chạy nhiều giờ. Phải dựa vào **nghiệp vụ và vòng đời phiên**, không chỉ dựa vào từ khóa stream.

## 3. Unary: ngân sách ngắn, rõ và đo được

Unary phù hợp với truy vấn hoặc command có một kết quả. Thời gian RPC thường gồm:

1. Client gửi request và chờ server tiếp nhận.
2. Server xác thực, kiểm tra điều kiện và xử lý nghiệp vụ.
3. Server gọi database hoặc downstream nếu cần.
4. Server serialize và trả response.

Chọn deadline theo SLA của thao tác và phân vị latency thực tế. Ví dụ:

~~~java
GetCustomerResponse response = customerStub
    .withDeadlineAfter(450, TimeUnit.MILLISECONDS)
    .getCustomer(request);
~~~

450 ms chỉ là con số minh họa. Với truy vấn đọc nhanh, ngân sách có thể ngắn; command có transaction cần đủ thời gian kiểm tra, commit và trả kết quả. Không đặt timeout riêng cho server bằng toàn bộ deadline client nếu request đã tiêu thụ một phần ngân sách trên đường truyền hoặc ở queue.

Với command có tác dụng phụ, timeout không chứng minh server chưa commit. Dùng idempotency key hoặc operation ID để client có thể retry/truy vấn trạng thái an toàn.

## 4. Client streaming: tính cả thời gian upload và xử lý

Client streaming thường dùng khi client gửi nhiều message, ví dụ upload file theo chunk, nhập batch hoặc gửi dữ liệu cảm biến. Deadline bao phủ **toàn bộ stream**, từ lúc bắt đầu RPC đến khi server trả response cuối.

Ngân sách cần tính:

- Thời gian thiết lập RPC và gửi chunk.
- Tổng kích thước payload và throughput tối thiểu chấp nhận được.
- Thời gian server validate và xử lý mỗi chunk.
- Thời gian ghi dữ liệu bền vững hoặc commit.
- Thời gian tạo và gửi acknowledgement cuối.

Ước lượng ban đầu cho thời gian truyền:

\[
T_{\text{upload}} \approx
\frac{\text{payload bytes}}{\text{minimum acceptable bytes/second}}
\]

Sau đó cộng thời gian xử lý và phần dự phòng. Ví dụ client gửi file 80 MB qua đường truyền có throughput tối thiểu 8 MB/s thì riêng thời gian truyền đã xấp xỉ 10 giây; deadline 2 giây là không thực tế.

~~~java
var uploadStub = fileServiceStub
    .withDeadlineAfter(30, TimeUnit.SECONDS);

StreamObserver<FileChunk> requestObserver =
    uploadStub.uploadFile(uploadResponseObserver);
~~~

30 giây chỉ là ví dụ. Cần giới hạn cả kích thước file, kích thước chunk, tốc độ gửi, queue và thời gian xử lý. Không gia hạn deadline sau mỗi chunk; nếu upload cần lâu hơn, thiết kế upload session có ID, sequence và resume để client tiếp tục từ chunk cuối đã được xác nhận.

Nếu deadline hết giữa upload, server có thể đã nhận và lưu một phần dữ liệu. Dùng upload ID, chunk sequence và cơ chế deduplication để retry không ghi trùng hoặc làm hỏng trạng thái upload.

## 5. Server streaming hữu hạn: tính thời gian phát hết kết quả

Server streaming có thể trả một tập kết quả lớn theo từng message, chẳng hạn export báo cáo hoặc tải danh sách bản ghi. Dù response có nhiều message, RPC vẫn có một deadline tổng.

Thời gian hoàn tất phụ thuộc vào:

- Thời gian truy vấn hoặc chuẩn bị dữ liệu.
- Số lượng và kích thước response message.
- Tốc độ server phát và khả năng nhận của client.
- Backpressure, network và thời gian xử lý ở client.

~~~java
var exportStub = reportServiceStub
    .withDeadlineAfter(45, TimeUnit.SECONDS);

exportStub.exportReport(
    exportRequest,
    reportResponseObserver);
~~~

45 giây là ví dụ cho một export hữu hạn, không phải giá trị mặc định. Nếu tập kết quả không có giới hạn hoặc client có thể nhận rất chậm, deadline dài hơn không giải quyết gốc rễ. Cần phân trang, giới hạn số record/byte, backpressure và giới hạn thời gian xử lý từng batch.

Client có thể đã nhận một phần kết quả trước khi deadline hết. Nếu kết quả cần tiếp tục sau lỗi, response nên có sequence/cursor hoặc export ID để client biết phần nào đã nhận và cách resume.

## 6. Server streaming subscription: giới hạn phiên và reconnect

Một subscription event có thể được thiết kế để mở lâu. Nếu đặt deadline ngắn như unary, client phải reconnect thường xuyên; nếu không có deadline và không có giới hạn vòng đời, stream có thể giữ subscription, queue và tài nguyên server vô thời hạn.

Chính sách phù hợp thường gồm:

- **Session lifetime:** thời gian tối đa cho một phiên stream, ví dụ một khoảng thời gian được chọn theo khả năng reconnect của client.
- **Idle timeout:** thời gian tối đa không có message hoặc hoạt động có ý nghĩa trước khi đóng stream.
- **Heartbeat:** tín hiệu phát hiện kết nối/consumer không còn hoạt động, có giới hạn tần suất.
- **Cursor/sequence:** vị trí cuối client đã nhận để reconnect và tiếp tục.
- **Cancellation cleanup:** dừng producer, đóng subscription và giải phóng queue.

Nếu nghiệp vụ thật sự yêu cầu một subscription không có thời hạn tuyệt đối, đó phải là ngoại lệ được cấu hình và giám sát rõ ràng. Khi ấy idle timeout, giới hạn stream đồng thời, backpressure, lease hoặc reconnect vẫn phải kiểm soát vòng đời.

## 7. Bidirectional streaming: quản lý một phiên hai chiều

Bidirectional streaming phù hợp với phiên tương tác, ví dụ client gửi lệnh và server trả kết quả/event đan xen. Cả hai chiều thuộc cùng một RPC và cùng chịu deadline tổng.

Khi chọn deadline, cần xác định:

1. Phiên có thời gian sống tối đa hay có thể kéo dài theo lease?
2. Bao lâu không có message thì phiên được xem là idle?
3. Heartbeat có cần thiết để phát hiện peer mất kết nối không?
4. Client có thể resume bằng session ID và sequence nào?
5. Khi deadline hết, trạng thái các command đã gửi được xác định ra sao?

~~~java
var sessionStub = collaborationServiceStub
    .withDeadlineAfter(10, TimeUnit.MINUTES);

StreamObserver<ClientMessage> outbound =
    sessionStub.openSession(inboundObserver);
~~~

10 phút chỉ minh họa một phiên có giới hạn. Không nên kéo dài deadline vô hạn chỉ để tránh reconnect. Với phiên lâu dài, có thể chia thành các session hữu hạn, lưu session ID/cursor và reconnect khi phiên kết thúc. Idle timeout vẫn cần riêng vì một phiên có thể không gửi message nhưng deadline tổng chưa hết.

## 8. Phân biệt deadline, idle timeout và keepalive

Ba cơ chế giải quyết ba vấn đề khác nhau:

| Cơ chế | Giới hạn điều gì? | Ví dụ mục đích |
| --- | --- | --- |
| **RPC deadline** | Tổng thời gian sống của một RPC | Unary phải trả kết quả trong ngân sách |
| **Idle timeout** | Khoảng không hoạt động của phiên | Đóng subscription không còn nhận/gửi dữ liệu |
| **HTTP/2 keepalive** | Tính sống của kết nối transport | Phát hiện connection/peer không phản hồi |

Keepalive không thay thế deadline RPC; một connection còn sống không có nghĩa request nghiệp vụ đang tiến triển. Idle timeout cũng không thay thế deadline tổng: một stream có thể liên tục gửi heartbeat nhưng vẫn tồn tại lâu hơn giới hạn nghiệp vụ. Cần phối hợp chúng theo mục đích.

## 9. Đặt deadline con theo ngân sách còn lại

Trong nested call, deadline của downstream không được vượt deadline còn lại của RPC cha. Có thể đặt một giới hạn con ngắn hơn và dành phần dự phòng cho service cha:

~~~java
Deadline parent = Context.current().getDeadline();
long childLimit = TimeUnit.MILLISECONDS.toNanos(250);
long responseReserve = TimeUnit.MILLISECONDS.toNanos(40);

if (parent != null) {
    long remaining = parent.timeRemaining(TimeUnit.NANOSECONDS);
    childLimit = Math.min(childLimit, remaining - responseReserve);
}

if (childLimit <= 0) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("insufficient downstream budget")
        .asRuntimeException();
}

var boundedStub = inventoryStub.withDeadlineAfter(
    childLimit, TimeUnit.NANOSECONDS);
InventoryResponse result =
    boundedStub.checkAvailability(request);
~~~

250 ms và 40 ms là ví dụ. Với streaming downstream, cần tính thêm thời gian sống phiên hoặc chuyển sang mô hình session có cursor; không áp dụng máy móc ngân sách unary ngắn cho một stream cần nhận dữ liệu liên tục.

## 10. Xử lý timeout và retry theo loại RPC

Deadline hết thường dẫn tới **DEADLINE_EXCEEDED**, nhưng không chứng minh server chưa xử lý dữ liệu:

- **Unary read:** thường có thể retry có kiểm soát nếu thao tác an toàn.
- **Unary command:** dùng idempotency key hoặc truy vấn operation ID trước khi gửi lại.
- **Client streaming:** dùng upload ID, sequence và acknowledgement theo chunk; không gửi lại mù quáng toàn bộ upload.
- **Server streaming:** lưu cursor/sequence cuối đã xử lý để resume; chấp nhận xử lý trùng an toàn nếu delivery có thể lặp.
- **Bidirectional streaming:** dùng session ID, message ID và trạng thái xác nhận cho từng command/event.

Retry phải nằm trong deadline tổng của caller. Không bắt đầu một lần retry có ngân sách dài hơn thời gian còn lại.

## 11. Kiểm thử deadline theo cardinality và vòng đời

Mỗi kiểu RPC cần test các tình huống riêng:

| Loại | Tình huống cần xác minh |
| --- | --- |
| Unary | Hoàn tất trước hạn; xử lý chậm; status khi deadline hết |
| Client streaming | Upload đủ dữ liệu; hết hạn giữa chunk; resume không ghi trùng |
| Server streaming hữu hạn | Phát đủ kết quả; client chậm; hết hạn sau một phần response |
| Server streaming subscription | Idle timeout; session lifetime; reconnect theo cursor; cleanup khi cancel |
| Bidirectional streaming | Hai chiều hoạt động; một phía im lặng; session hết hạn; reconnect và deduplicate |

Dùng in-process test hoặc server giả lập có thể điều khiển để kiểm tra deadline và cancellation. Với stream, dùng latch/future để tạo consumer chậm hoặc dừng ở chunk xác định thay vì phụ thuộc vào sleep dài. Integration test Spring cần xác nhận deadline policy thực sự được áp dụng trên stub/channel của ứng dụng.

## 12. Chọn và hiệu chỉnh deadline trong production

Theo dõi theo full method name và loại RPC:

- Latency p50/p95/p99 và tỷ lệ **DEADLINE_EXCEEDED**.
- Thời gian queue, xử lý server và downstream.
- Với client streaming: byte đã nhận, throughput, thời gian xử lý chunk và upload bị dở.
- Với server streaming: số message/byte đã phát, thời gian chờ readiness và tuổi stream.
- Với bidirectional: thời gian sống phiên, idle duration, heartbeat và số lần reconnect.
- Số tác vụ còn chạy sau cancellation và thời gian cleanup.

Khi timeout tăng, tìm tầng tiêu thụ ngân sách trước khi tăng deadline. Khi stream dài bị ngắt thường xuyên, kiểm tra session lifetime và reconnect. Khi stream không kết thúc và tài nguyên tăng, xem idle timeout, backpressure và cancellation cleanup.

## 13. Ghi nhớ và tự kiểm tra

Chọn deadline theo **thời gian sống và cách trao đổi dữ liệu của từng loại RPC**:

- Unary: ngân sách ngắn, dựa trên latency và SLA.
- Client streaming: tính cả upload, xử lý và acknowledgement cuối.
- Server streaming hữu hạn: tính thời gian phát hết kết quả; subscription dài cần session lifetime và resume.
- Bidirectional streaming: quản lý thời gian sống phiên, idle timeout, heartbeat và reconnect.

Deadline là giới hạn tổng của RPC; idle timeout giới hạn khoảng không hoạt động; keepalive kiểm tra transport. Chúng bổ sung cho nhau và không thể thay thế lẫn nhau.

Tự kiểm tra:

1. Vì sao deadline của client streaming phải tính cả thời gian upload và xử lý chunk?
2. Một server streaming export hữu hạn khác subscription event dài hạn ở điểm nào khi chọn deadline?
3. Vì sao gửi heartbeat liên tục không thay thế session lifetime?
4. Khi bidirectional stream hết deadline, cần những ID/sequence nào để reconnect an toàn?
5. Vì sao nested call phải dùng ngân sách còn lại của request cha?

Deadline phù hợp theo từng loại RPC giúp Spring gRPC cân bằng trải nghiệm phản hồi, độ tin cậy và tài nguyên server, đồng thời tạo cơ sở rõ ràng cho cancellation, retry và reconnect.
