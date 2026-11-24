# Ảnh hưởng của khởi động lại máy chủ đến khả năng resume

RSocket Resume cho phép hai peer tiếp tục một phiên giao tiếp sau khi transport bị gián đoạn tạm thời. Client có thể mở transport mới và yêu cầu tiếp tục session cũ bằng resume token cùng thông tin vị trí frame đã nhận. Cơ chế này chỉ hoạt động khi trạng thái cần thiết của session vẫn còn và peer nhận yêu cầu có thể khôi phục đúng trạng thái đó.

Khởi động lại server làm thay đổi điều kiện quan trọng này. Nếu trạng thái resume chỉ được giữ trong bộ nhớ của tiến trình, khi tiến trình dừng thì token, vị trí frame, buffer phát lại và trạng thái stream có thể mất. Client vẫn có thể gửi yêu cầu Resume, nhưng server mới không còn đủ dữ liệu để tiếp tục session cũ. Khi đó, ứng dụng phải tạo session mới và khôi phục các luồng nghiệp vụ theo cơ chế riêng.

Vì vậy, cần phân biệt mất kết nối tạm thời với mất tiến trình server. Resume thường xử lý tốt trường hợp đầu; trường hợp server restart đòi hỏi thiết kế lưu giữ hoặc tái tạo trạng thái ở cấp triển khai và ứng dụng.

## 1. Resume phục hồi điều gì?

Trong một session RSocket, hai peer trao đổi frame trên các stream có ID riêng. Khi transport bị ngắt, một số frame có thể đã được gửi nhưng chưa được peer xác nhận nhận thành công. Resume giúp hai peer xác định vị trí giao tiếp đã được xác nhận và truyền lại phần frame còn thiếu.

Để thực hiện điều đó, hai phía cần duy trì thông tin phiên, thường gồm:

- Resume token dùng để nhận diện session cần tiếp tục.
- Vị trí frame đã nhận hoặc đã xác nhận ở mỗi chiều.
- Buffer chứa các frame đã gửi nhưng còn cần giữ để phát lại.
- Thông tin session và trạng thái giao thức cần thiết để tiếp tục các stream đang hoạt động.
- Thời hạn lưu giữ trạng thái và các tham số resume đã thỏa thuận.

Resume không đơn giản là mở lại socket cũ. Client tạo một transport mới rồi gửi yêu cầu Resume với thông tin nhận diện session và trạng thái vị trí. Nếu server còn session tương ứng, nó có thể chấp nhận và hai phía tiếp tục trao đổi từ vị trí phù hợp.

~~~text
Client                                      Server
  |                                           |
  |------ session đang hoạt động ------------|
  |<------------- các frame -----------------|
  |                                           |
  X  transport bị đứt                         |
  |                                           |
  |------ mở transport mới ----------------->|
  |------ RESUME(token, positions) ---------->|
  |<------------- RESUME_OK ------------------|  nếu session còn hợp lệ
  |<------ phát lại frame còn thiếu ----------|
  |------ tiếp tục trao đổi ----------------->|
~~~

Nếu server không còn trạng thái phiên hoặc không thể cung cấp các frame cần phát lại, nó không thể tiếp tục session cũ. Client phải xử lý việc Resume bị từ chối hoặc thất bại.

## 2. Vì sao server restart có thể làm Resume thất bại?

Nhiều triển khai RSocket lưu session state và replay buffer trong bộ nhớ của tiến trình. Khi server đang chạy, trạng thái này vẫn tồn tại dù TCP hoặc WebSocket transport bị ngắt trong thời gian ngắn. Nhưng khi tiến trình server dừng, vùng nhớ đó bị giải phóng.

Ví dụ:

1. Client và server thiết lập session có bật Resume.
2. Server gửi một số frame cho client và giữ frame cần thiết trong replay buffer.
3. Mạng bị ngắt trước khi hai phía đồng bộ được toàn bộ vị trí nhận.
4. Server restart.
5. Tiến trình mới khởi động nhưng không có session state cũ.
6. Client gửi RESUME với token cũ.
7. Server mới không tìm được session hoặc buffer tương ứng và từ chối tiếp tục.

Việc giữ nguyên địa chỉ IP, hostname, port hoặc resume token không đủ để khôi phục phiên. Token chỉ giúp nhận diện session; nó không chứa toàn bộ trạng thái cần thiết để phát lại frame và phục hồi các stream.

| Trạng thái trước restart | Trạng thái sau restart | Khả năng Resume |
| --- | --- | --- |
| Session và buffer chỉ ở RAM | Tiến trình mới, RAM trống | Thường không thể Resume session cũ. |
| Token được lưu bền vững nhưng buffer và vị trí frame mất | Chỉ còn token | Không đủ dữ liệu để tiếp tục an toàn. |
| Session state, vị trí và replay buffer được lưu nhất quán, có thể khôi phục | Tiến trình mới khôi phục được toàn bộ trạng thái | Có thể Resume nếu implementation hỗ trợ và session còn hạn. |
| Client reconnect tới node khác không có session state dùng chung | Node đích không nhận diện token | Resume thường bị từ chối. |
| Session đã hết thời hạn lưu giữ | Trạng thái đã bị xóa | Phải tạo session mới. |

Resume là extension tùy chọn của RSocket. Cả client và server phải hỗ trợ và bật extension này. Ngay cả khi hai phía đều bật Resume, khả năng phục hồi sau restart vẫn phụ thuộc vào nơi lưu trạng thái và khả năng khôi phục của implementation.

## 3. Phân biệt gián đoạn transport và khởi động lại tiến trình

Hai tình huống có biểu hiện giống nhau ở client — connection bị mất — nhưng hậu quả đối với session khác nhau:

| Tình huống | Server còn chạy? | Session state trong RAM | Kết quả có thể xảy ra |
| --- | --- | --- | --- |
| Wi-Fi hoặc mạng di động chập chờn | Có | Còn | Client có thể Resume trong thời hạn lưu giữ. |
| Proxy đóng idle connection | Có | Còn | Có thể Resume nếu trạng thái và buffer vẫn còn. |
| TCP connection bị reset | Có | Còn | Có thể Resume qua transport mới. |
| Server process bị crash | Không | Mất khi process kết thúc | Resume thất bại nếu không có state bền vững hoặc bản sao hợp lệ. |
| Server được triển khai lại trên node khác | Node cũ dừng | Tùy kiến trúc | Resume chỉ hoạt động nếu node mới truy cập được session state cần thiết. |
| Server restart sau khi session hết TTL | Có thể đã chạy lại | Session đã hết hạn | Client phải tạo session mới. |

Với lỗi mạng tạm thời, server vẫn có thể giữ session và buffer trong bộ nhớ. Khi server restart, bộ nhớ của tiến trình cũ không còn. Đây là khác biệt cốt lõi khi thiết kế chiến lược phục hồi.

## 4. Những trạng thái cần được lưu giữ để Resume sau restart

Để một session có thể tiếp tục sau khi tiến trình server thay thế, việc lưu mỗi resume token là chưa đủ. Hệ thống cần bảo đảm trạng thái giao thức và dữ liệu phát lại nhất quán.

### Resume token và nhận diện session

Token liên kết yêu cầu Resume với session đã được thiết lập trước đó. Token cần được tạo và quản lý theo cơ chế của implementation, tránh đoán được hoặc bị lộ. Nếu token chỉ được lưu ở RAM, server mới không thể tra cứu session. Nếu token được lưu ở database nhưng session state không còn, tra cứu thành công vẫn không giúp phát lại frame.

### Vị trí frame

Hai peer cần biết frame nào đã được nhận và frame nào còn cần phát lại. Nếu vị trí bị lùi hoặc tiến sai sau restart, hệ thống có thể bỏ sót hoặc phát trùng frame. Vì vậy, cập nhật vị trí và buffer cần có tính nhất quán; không thể chỉ lưu một con số vị trí mà không lưu dữ liệu tương ứng.

### Replay buffer

Frame chưa được xác nhận cần được giữ cho đến khi có thể loại bỏ an toàn. Nếu buffer mất trong lúc restart, server không có nội dung để phát lại dù token và vị trí vẫn còn. Kích thước buffer, thời gian lưu giữ và tốc độ phát dữ liệu ảnh hưởng trực tiếp tới khoảng gián đoạn mà Resume có thể chịu được.

### Trạng thái stream và xử lý ứng dụng

Session còn cần trạng thái giao thức để biết stream nào đang hoạt động và cách tiếp tục trao đổi. Tuy nhiên, các đối tượng Java trong bộ nhớ như callback, Publisher, subscription tới message broker, transaction hoặc listener của thiết bị không tự động được khôi phục chỉ bằng cách lưu frame.

Ngay cả khi tầng giao thức có thể phục hồi vị trí frame, ứng dụng vẫn cần một cách tái tạo nguồn dữ liệu và tài nguyên nghiệp vụ sau khi process restart. Ví dụ, stream theo dõi giá cần đăng ký lại với nguồn giá; stream tiến độ job cần đọc lại trạng thái job từ kho dữ liệu bền vững.

## 5. Server restart có kiểm soát (graceful restart)

Graceful restart cho phép server dừng nhận công việc mới, chờ các tương tác đang chạy hoàn tất trong một khoảng thời gian, rồi đóng session và transport. Nếu tất cả stream hoàn tất trước khi process dừng, ứng dụng có thể không cần Resume cho các stream đó.

Một quy trình shutdown có kiểm soát thường gồm:

1. Đưa instance vào trạng thái draining để load balancer hoặc service discovery ngừng chuyển request mới tới instance.
2. Ngừng nhận các tương tác mới theo chính sách của ứng dụng.
3. Cho các request-response và stream hữu hạn thời gian hoàn tất trong giới hạn shutdown timeout.
4. Gửi thông báo đóng hoặc đóng các session còn lại theo chính sách đã công bố.
5. Lưu checkpoint nghiệp vụ cần thiết trước khi dừng process.
6. Kết thúc tiến trình sau khi đã giải phóng tài nguyên.

Graceful restart không tự động bảo đảm Resume sau khi process mới khởi động. Nếu session bị đóng có chủ đích, client nên coi đó là kết thúc phiên và tạo session mới. Nếu server dừng khi còn session đang cần tiếp tục, trạng thái Resume vẫn phải được chuyển giao hoặc lưu bền vững trước khi process cũ thoát.

Với rolling deployment, cần xác định rõ session đang gắn với node nào, node mới có thể tiếp cận trạng thái cũ hay không và thời gian draining có đủ cho các stream dài hạn hay không. Sticky session chỉ giúp định tuyến client trở lại đúng node khi node đó còn tồn tại; nó không phục hồi bộ nhớ đã mất khi node bị restart.

## 6. Server restart đột ngột (crash hoặc mất máy)

Khi server crash, mất điện hoặc bị hệ điều hành kết thúc cưỡng bức, không có cơ hội chạy quy trình draining. Client thường phát hiện sự cố qua lỗi transport, keepalive timeout hoặc timeout của request.

Nếu session state chỉ nằm trong RAM, client sẽ không Resume được session cũ sau khi server khởi động lại. Ứng dụng cần:

- Nhận biết Resume thất bại hoặc session không còn tồn tại.
- Đóng bỏ tham chiếu tới session cũ.
- Thiết lập RSocket session mới bằng SETUP.
- Đăng ký lại các stream còn cần thiết.
- Gửi cursor, sequence number hoặc timestamp để tiếp tục dữ liệu từ vị trí nghiệp vụ phù hợp.
- Khử trùng lặp nếu server có thể phát lại sự kiện đã xử lý trước khi crash.

Không nên để client lặp đi lặp lại yêu cầu Resume với cùng token khi server đã xác nhận session không tồn tại. Sau khi Resume bị từ chối dứt khoát, hãy chuyển sang quy trình tạo session mới theo chính sách retry có giới hạn.

## 7. Khôi phục Resume trong môi trường nhiều instance

Trong cluster, client có thể reconnect tới một instance khác với instance đã tạo session. Nếu session state chỉ tồn tại cục bộ trên node ban đầu, node mới không thể tiếp tục session đó.

Có ba cách tổ chức thường gặp:

| Kiến trúc | Cách hoạt động | Giới hạn |
| --- | --- | --- |
| Sticky routing | Đưa client trở lại node đã tạo session. | Không giúp nếu node đó restart hoặc mất hẳn. |
| Shared/replicated session state | Các node có thể đọc và khôi phục session state cùng replay buffer. | Cần cơ chế lưu trữ nhất quán, đồng bộ vị trí và xử lý ownership. |
| Reconnect ở tầng ứng dụng | Tạo session mới trên node bất kỳ rồi đăng ký lại các stream bằng cursor nghiệp vụ. | Không tiếp tục chính xác session giao thức cũ; cần logic phục hồi và deduplication. |

Muốn Resume xuyên node hoặc sau restart, kho dùng chung phải lưu đủ dữ liệu và implementation phải hỗ trợ khôi phục từ kho đó. Việc thêm Redis hoặc database vào hệ thống không tự biến RSocket Resume thành cơ chế phân tán. Cần kiểm tra rõ thư viện đang dùng có hỗ trợ persistence/replication cho session và replay buffer hay không.

Nếu không có hỗ trợ state transfer bền vững, lựa chọn an toàn và thực tế thường là reconnect session mới rồi khôi phục stream ở tầng ứng dụng. Với nhiều hệ thống realtime, cursor và event log bền vững dễ vận hành hơn việc cố gắng serialize toàn bộ trạng thái reactive của một process.

## 8. Resume timeout, buffer và giới hạn thời gian gián đoạn

Resume chỉ có thể thành công khi trạng thái phiên còn được lưu giữ. Cấu hình timeout quá ngắn làm client mất cơ hội phục hồi sau một lần mạng chập chờn. Timeout quá dài làm server phải giữ session và replay buffer lâu hơn, tiêu tốn bộ nhớ hoặc dung lượng lưu trữ.

Các tham số cần cân nhắc:

- Session duration: thời gian server giữ trạng thái phiên sau khi transport mất.
- Replay buffer size: lượng frame hoặc byte được giữ để phát lại.
- Tốc độ phát dữ liệu: stream càng nhanh thì buffer càng nhanh đầy.
- Thời gian gián đoạn: client cần reconnect trước khi trạng thái hết hạn hoặc buffer không còn frame cần thiết.
- Số session đồng thời: tổng dung lượng cần lưu tăng theo số client và số stream.

Ví dụ, nếu một session phát trung bình 200 KB dữ liệu mỗi giây và cần giữ dữ liệu cho khoảng gián đoạn 30 giây, buffer lý thuyết có thể cần khoảng 6 MB cho session đó, chưa tính overhead. Với 500 session cùng mức tải, dung lượng tổng có thể lên tới khoảng 3 GB. Đây chỉ là phép ước lượng dung lượng payload; cần đo thêm chi phí frame, metadata, cấu trúc bộ nhớ và cách implementation lưu buffer.

Nếu replay buffer đầy hoặc frame cần thiết đã bị loại bỏ, Resume có thể không thành công dù session token vẫn còn trong thời hạn. Vì vậy, TTL và buffer phải được thiết kế cùng nhau.

## 9. Resume và khôi phục nghiệp vụ là hai lớp khác nhau

Resume phục hồi việc truyền frame của một session RSocket. Khôi phục nghiệp vụ phục hồi ý nghĩa của dữ liệu và công việc mà ứng dụng đang thực hiện. Hai lớp này có liên quan nhưng không thay thế nhau.

Ví dụ, một client theo dõi tiến độ job:

- Resume thành công có thể giúp tiếp tục trao đổi frame trong session cũ nếu trạng thái protocol còn đầy đủ.
- Nếu server process restart và không thể Resume, client mở session mới.
- Client gửi <code>jobId</code> và <code>lastSeenSequence</code> để yêu cầu server phát lại tiến độ từ vị trí đã nhận.
- Server đọc event log bền vững, phát các event có sequence lớn hơn cursor.
- Client bỏ qua event có sequence đã xử lý để tránh cập nhật trùng.

Ví dụ payload nghiệp vụ:

~~~java
public record JobProgressRequest(
    String jobId,
    long lastSeenSequence
) {}

public record JobProgressEvent(
    String jobId,
    long sequence,
    String status,
    int percent
) {}
~~~

Handler có thể dùng cursor để tạo stream mới:

~~~java
@MessageMapping("jobs.progress.resume")
public Flux<JobProgressEvent> resumeProgress(JobProgressRequest request) {
    return jobEventStore.readAfter(
        request.jobId(),
        request.lastSeenSequence()
    );
}
~~~

Đây là ví dụ về resume ở tầng nghiệp vụ, không phải frame-level RSocket Resume. Event store cần giữ dữ liệu đủ lâu để client tiếp tục; nếu dữ liệu đã hết hạn, server phải trả một kết quả rõ ràng để client tải snapshot mới hoặc bắt đầu theo dõi từ trạng thái hiện tại.

Với lệnh có side effect như tạo đơn hàng hoặc trừ tiền, việc client gửi lại request sau khi session mất không bảo đảm thao tác chưa được thực hiện. Dùng idempotency key hoặc mã giao dịch duy nhất để server nhận biết lần gửi lặp. Resume giao thức không thay thế bảo đảm exactly-once của nghiệp vụ.

## 10. Quy trình client khi Resume thất bại sau restart

Client nên phân biệt lỗi tạm thời có thể thử Resume với trường hợp session đã mất hoặc không thể khôi phục:

~~~text
Transport bị ngắt
       |
       v
Thử kết nối lại transport
       |
       v
Gửi yêu cầu RESUME
       |
       +---- RESUME_OK ----> Tiếp tục session cũ
       |
       +---- bị từ chối / session không tồn tại
                    |
                    v
             Bỏ session cũ
                    |
                    v
               Gửi SETUP
                    |
                    v
             Session mới READY
                    |
                    v
       Đăng ký lại stream bằng cursor
                    |
                    v
        Khử trùng lặp theo sequence
~~~

Không phải mọi lỗi khi Resume đều có cùng nguyên nhân. Timeout mạng có thể là tạm thời; session token không được nhận diện hoặc replay buffer không còn dữ liệu là dấu hiệu cần chuyển sang session mới. Client nên phân loại lỗi theo mã và trạng thái do implementation cung cấp thay vì chỉ phân tích message text.

Một chính sách phục hồi thường có:

1. Thử Resume trong một khoảng thời gian hữu hạn với backoff và jitter.
2. Nếu peer từ chối Resume vì session không tồn tại hoặc không thể tiếp tục, dừng thử token cũ.
3. Thiết lập session mới bằng SETUP.
4. Khôi phục từng stream theo hợp đồng ứng dụng.
5. Đặt giới hạn retry tổng và timeout cho toàn bộ quá trình phục hồi.

## 11. Kiểm thử ảnh hưởng của server restart

Kiểm thử Resume không nên chỉ mô phỏng việc ngắt socket trong khi server vẫn chạy. Cần có tình huống restart process để xác nhận hệ thống có hoặc không bảo toàn session state như thiết kế.

Ma trận kiểm thử gợi ý:

| Tình huống | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Ngắt transport ngắn | Server process còn chạy, session và buffer còn | Resume thành công trong giới hạn cấu hình. |
| Ngắt transport quá lâu | Session đã hết TTL | Resume thất bại; client tạo session mới. |
| Restart server không persistence | Session state chỉ ở RAM | Resume cũ bị từ chối; client fallback sang SETUP. |
| Restart server có persistence được hỗ trợ | State và replay buffer được khôi phục đầy đủ | Resume có thể thành công theo khả năng implementation. |
| Reconnect sang node khác không có state chung | Node đích không nhận diện session | Resume thất bại; chuyển sang session mới. |
| Replay buffer không còn frame cần thiết | Token còn nhưng dữ liệu phát lại thiếu | Resume không thể bảo đảm tiếp tục; tạo session mới. |
| Stream dài hạn có cursor | Session cũ mất, event store còn dữ liệu | Đăng ký lại và tiếp tục từ cursor. |
| Request có side effect bị gián đoạn | Không biết server đã xử lý hay chưa | Retry an toàn nhờ idempotency key. |

Với bài kiểm thử restart thật, nên chạy server trong process hoặc container có thể dừng và khởi động lại độc lập. Ghi nhận resume token, thời điểm mất transport, trạng thái buffer, kết quả RESUME và số event client nhận được. Nếu kiểm thử persistence, xác nhận dữ liệu đã được ghi bền vững trước khi dừng process.

## 12. Quan sát và vận hành

Để chẩn đoán Resume sau restart, nên theo dõi:

- Số lần client thử Resume và tỷ lệ thành công.
- Số lần Resume bị từ chối vì session không tồn tại hoặc hết hạn.
- Số lần fallback sang SETUP mới.
- Kích thước và mức sử dụng replay buffer.
- Số session đang được giữ sau khi transport mất.
- Tuổi của session tại thời điểm Resume.
- Thời gian phục hồi từ lúc mất transport tới khi stream hoạt động lại.
- Số event phát lại, số event trùng bị loại bỏ và khoảng cursor bị thiếu.

Log nên có session correlation ID hoặc mã tham chiếu không nhạy cảm. Không ghi resume token thô vì token có thể cho phép nhận diện hoặc tiếp tục một session. Cần bảo vệ token tương tự credential: giới hạn quyền truy cập log, không đưa vào metric label và không hiển thị cho người dùng cuối.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ lưu resume token | Server mới nhận diện được token nhưng không có frame/state để tiếp tục. | Lưu hoặc tái tạo toàn bộ trạng thái cần thiết theo khả năng implementation. |
| Giả định bật Resume là đủ cho server restart | Session trong RAM biến mất khi process dừng. | Kiểm thử restart process và xác minh cơ chế persistence. |
| Chỉ dùng sticky session | Client reconnect đúng node nhưng node đã restart. | Dùng state replication/persistence hoặc fallback nghiệp vụ. |
| Chuyển request sang node bất kỳ | Node đích không có session state cũ. | Có shared state được hỗ trợ hoặc tạo session mới. |
| Giữ buffer quá nhỏ | Frame cần phát lại đã bị loại bỏ trước khi Resume. | Tính buffer theo throughput, số session và thời gian gián đoạn. |
| Giữ session quá lâu | Tốn RAM hoặc dung lượng lưu trữ. | Đặt TTL, quota session và cleanup. |
| Cho rằng Resume khôi phục Publisher Java | Subscription tới broker hoặc callback trong process đã mất. | Tái tạo nguồn ứng dụng từ dữ liệu bền vững và cursor. |
| Retry command không idempotent | Side effect có thể chạy hai lần sau fallback session mới. | Dùng idempotency key và deduplication. |

## 14. Ghi nhớ

- Resume tiếp tục một session RSocket sau khi transport bị gián đoạn, dựa trên token, vị trí frame và dữ liệu cần phát lại.
- Nếu session state và replay buffer chỉ nằm trong RAM, server restart thường làm Resume session cũ thất bại.
- Lưu token riêng lẻ không đủ; trạng thái vị trí, buffer và trạng thái giao thức phải được giữ nhất quán.
- Sticky session giúp định tuyến về đúng node nhưng không phục hồi trạng thái đã mất khi node restart.
- Resume xuyên restart hoặc xuyên node chỉ khả thi khi implementation hỗ trợ lưu giữ/khôi phục đầy đủ trạng thái cần thiết.
- Graceful shutdown có thể drain stream; nó không tự bảo đảm session sẽ Resume sau khi process mới khởi động.
- Khi Resume thất bại, client tạo session mới và khôi phục stream bằng cursor hoặc sequence nghiệp vụ.
- Resume ở tầng giao thức không thay thế event store, deduplication hay idempotency cho nghiệp vụ.
