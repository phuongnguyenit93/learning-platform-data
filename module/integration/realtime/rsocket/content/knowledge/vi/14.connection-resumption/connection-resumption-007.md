# Giới hạn dung lượng bộ đệm và thời gian giữ phiên

RSocket Resume cho phép hai peer tiếp tục một logical connection sau khi transport TCP hoặc WebSocket bị gián đoạn trong thời gian ngắn. Để làm được điều đó, mỗi phía cần giữ trạng thái phiên và lưu những frame đã gửi nhưng peer chưa xác nhận đã nhận. Khi transport mới được thiết lập, hai phía trao đổi vị trí đã nhận và phát lại phần dữ liệu còn thiếu.

Khả năng phục hồi phụ thuộc vào hai giới hạn vận hành: **dung lượng resume buffer** và **thời gian giữ phiên**. Buffer phải đủ lớn để giữ dữ liệu trong khoảng mất kết nối; session phải còn tồn tại khi peer quay lại. Nếu một trong hai giới hạn bị vượt, phiên cũ có thể không resume được và ứng dụng phải tạo kết nối mới, sau đó khôi phục trạng thái nghiệp vụ theo cách riêng.

## 1. Resume giữ lại điều gì khi transport bị ngắt?

Khi Resume được bật và hai peer hỗ trợ cơ chế này, kết nối RSocket có một resume token để nhận diện phiên. Mỗi phía giữ các frame outbound chưa được peer xác nhận, cùng vị trí truyền/nhận cần thiết để tiếp tục luồng frame sau khi kết nối lại.

Trình tự khái quát:

1. Client và server thiết lập RSocket session có bật Resume.
2. Trong lúc hoạt động, mỗi phía gửi frame và giữ dữ liệu outbound trong resume buffer cho đến khi biết peer đã nhận tới vị trí tương ứng.
3. Transport bị đứt. Logical session và buffer được giữ lại trong thời hạn cấu hình.
4. Client mở transport mới và gửi `RESUME` cùng token và các vị trí truyền/nhận mà nó biết.
5. Server kiểm tra token, session còn hiệu lực và dữ liệu cần phát lại còn nằm trong buffer.
6. Nếu có thể tiếp tục, server trả `RESUME_OK`; hai phía đồng bộ vị trí và phát lại phần frame chưa được xác nhận.
7. Các stream đang hoạt động tiếp tục trên logical connection đã phục hồi.

```text
Client                                      Server
  |                                            |
  |------ SETUP (Resume enabled, token) ------->|
  |<------------- SETUP response --------------|
  |                                            |
  |------ PAYLOAD ---------------------------->|
  |<----- PAYLOAD ------------------------------|
  |                                            |
  |       transport bị gián đoạn                |
  X                                            X
  |                                            |
  |------ RESUME (token, positions) ----------->|
  |<----- RESUME_OK (peer position) ------------|
  |                                            |
  |------ replay frame còn thiếu ------------->|
  |<----- replay frame còn thiếu --------------|
  |                                            |
  |       các stream tiếp tục                   |
```

Resume phục hồi một logical connection đã có, bao gồm các stream của nó. Nó khác với việc mở một kết nối RSocket hoàn toàn mới bằng SETUP. Nếu session cũ đã hết hạn hoặc buffer không còn phần dữ liệu cần phát lại, peer không thể tiếp tục session đó.

## 2. Resume buffer lưu dữ liệu nào?

Mỗi peer cần giữ các frame mà chính nó đã gửi nhưng chưa được xác nhận là peer đã nhận. Khi nhận được thông tin vị trí đã nhận từ peer, sender có thể loại bỏ phần buffer cũ hơn vị trí đó. Nếu transport đứt, các frame chưa được xác nhận vẫn cần có sẵn để phát lại sau khi resume.

Các điểm cần nhớ:

- Buffer được tính theo **byte**, không phải số lượng object Java hay số lượng payload nghiệp vụ.
- Dung lượng cần tính cả frame header, metadata và data được lưu trong representation của implementation.
- Hai phía giữ dữ liệu outbound của riêng mình; buffer client và buffer server có thể cần dung lượng khác nhau.
- Nhiều stream cùng chia sẻ một logical connection. Một stream phát dữ liệu lớn với tốc độ cao có thể chiếm phần lớn buffer của phiên và ảnh hưởng khả năng resume của các stream khác.
- Buffer phải giữ đúng thứ tự frame để dữ liệu có thể được phát lại theo vị trí truyền.

Trong khi kết nối bình thường, thông tin vị trí đã nhận được cập nhật theo cơ chế Resume của giao thức, bao gồm trường vị trí trong KEEPALIVE. Khi transport mất, sender chưa nhận được xác nhận mới có thể phải giữ lại nhiều frame hơn thực tế cần thiết; vì vậy cần dự trù phần đệm an toàn.

Resume buffer là bộ đệm phục vụ phát lại giao thức. Nó không phải hàng đợi message bền vững thay thế broker, database hoặc transactional outbox. Không nên xem buffer trong bộ nhớ là nơi lưu sự kiện dài hạn.

## 3. Tính dung lượng buffer theo lưu lượng và thời gian gián đoạn

Dung lượng buffer cần thiết phụ thuộc vào tốc độ byte outbound và khoảng thời gian mà peer có thể không nhận hoặc chưa xác nhận dữ liệu. Một công thức ước lượng thực tế:

\[
B_{required} = (R_{peak} \times T_{outage} + B_{burst}) \times S
\]

Trong đó:

- `R_peak`: tốc độ dữ liệu outbound đỉnh, tính bằng byte/giây.
- `T_outage`: khoảng thời gian cần chịu được khi transport bị gián đoạn hoặc chưa thể xác nhận frame.
- `B_burst`: dung lượng dự phòng cho burst dữ liệu ngắn.
- `S`: hệ số an toàn để bù overhead, biến động lưu lượng và sai số đo.

Đo theo byte frame thực tế mà resume store giữ nếu có thể. Nếu chỉ có số liệu payload ở tầng ứng dụng, hãy cộng thêm overhead frame/metadata và dùng hệ số an toàn đủ lớn. Tính riêng cho chiều client → server và server → client; chiều có tốc độ cao hơn thường cần buffer lớn hơn.

### 3.1. Ví dụ ước lượng

Giả sử một phiên có lưu lượng outbound đỉnh `1,5 MiB/s`, cần chịu gián đoạn `20 giây`, có burst dự phòng `10 MiB` và dùng hệ số an toàn `1,5`:

\[
B = (1.5 \times 20 + 10) \times 1.5 = 60\ MiB
\]

Vậy cần khoảng `60 MiB` buffer cho chiều outbound đó của một session. Nếu có 100 session đồng thời với mức sử dụng tương tự, chỉ riêng phần buffer này đã có thể cần khoảng `6.000 MiB` (xấp xỉ `5,9 GiB`) trên mỗi phía đang lưu các frame outbound tương ứng, chưa tính object overhead, session metadata và bộ nhớ của ứng dụng.

Ví dụ này là capacity estimate, không phải giá trị mặc định của RSocket. Hãy đo throughput theo percentile cao và theo từng loại kết nối thực tế; dùng trung bình toàn hệ thống có thể đánh giá thấp những session phát dữ liệu lớn.

### 3.2. Công cụ tính đơn giản bằng Java

Có thể đặt phép tính vào cấu hình ứng dụng để so sánh các kịch bản trước khi chọn giới hạn cho resume store:

```java
import java.time.Duration;

record ResumeBufferBudget(
    long peakBytesPerSecond,
    Duration outageWindow,
    long burstBytes,
    double safetyFactor
) {
    long requiredBytes() {
        if (peakBytesPerSecond < 0 || burstBytes < 0
                || outageWindow.isNegative() || safetyFactor < 1.0) {
            throw new IllegalArgumentException("Invalid resume buffer budget");
        }

        double trafficBytes = peakBytesPerSecond
            * (outageWindow.toMillis() / 1000.0);
        return (long) Math.ceil((trafficBytes + burstBytes) * safetyFactor);
    }
}

var budget = new ResumeBufferBudget(
    1_572_864L,              // 1.5 MiB/s
    Duration.ofSeconds(20),
    10L * 1024 * 1024,       // burst 10 MiB
    1.5
);

long bufferBytes = budget.requiredBytes();
```

Đây là bộ tính dung lượng ở tầng ứng dụng, không phải API cấu hình chuẩn của Spring Boot hoặc RSocket. Hãy chuyển kết quả vào resume store/buffer của implementation đang dùng và xác minh đơn vị mà API đó yêu cầu. Một số thư viện cấu hình giới hạn theo byte, một số cho phép cung cấp store tùy chỉnh.

## 4. Giới hạn buffer và hành vi khi buffer đầy

Resume chỉ thành công nếu sender vẫn còn dữ liệu bắt đầu từ vị trí mà peer yêu cầu phát lại. Nếu frame cũ đã bị loại bỏ hoặc buffer không đủ chỗ để giữ frame mới, implementation không còn đủ dữ liệu để tiếp tục đúng phiên.

Không nên giả định khi buffer đầy thì thư viện sẽ tự bỏ frame cũ và tiếp tục an toàn. Hành vi cụ thể phụ thuộc implementation và resume store; có thể phát sinh lỗi gửi, đóng session hoặc làm lần resume sau thất bại. Cần đọc hợp đồng của phiên bản RSocket Java đang triển khai và kiểm thử đúng nhánh overflow.

Các biện pháp kiểm soát:

- Đặt giới hạn byte cho buffer của từng session và giới hạn tổng bộ nhớ cho tất cả session.
- Đo tốc độ outbound, occupancy, high-water mark và tốc độ peer xác nhận frame.
- Giới hạn tốc độ producer hoặc giảm tần suất dữ liệu khi buffer tiến gần ngưỡng.
- Với telemetry có thể mất mẫu, cân nhắc sampling, aggregation hoặc chỉ giữ giá trị mới nhất ở tầng ứng dụng trước khi phát frame.
- Với dữ liệu không thể mất, dùng durable queue/outbox để giữ sự kiện; không tăng vô hạn resume buffer trong heap.
- Khi buffer không thể đáp ứng, kết thúc phiên theo chính sách rõ ràng và cho ứng dụng khôi phục từ checkpoint hoặc trạng thái đã lưu.

`REQUEST_N` điều tiết số payload ứng dụng mà subscriber muốn nhận trên stream. Nó có ích để tránh producer phát nhanh hơn consumer, nhưng không thay thế giới hạn byte của resume buffer. Một payload có thể rất lớn; nhiều stream cũng có thể đồng thời phát dữ liệu trên cùng session.

## 5. Thời gian giữ phiên (session retention)

Session retention là khoảng thời gian một peer giữ state của logical session sau khi transport bị mất, để peer còn lại có cơ hội kết nối lại và gửi RESUME. Đây là chính sách cục bộ của implementation/resume store; không nên giả định rằng hai peer tự động thương lượng cùng một giá trị retention qua SETUP.

Retention phải đủ dài để bao phủ toàn bộ thời gian cần cho:

1. Phát hiện transport bị mất.
2. Chờ mạng phục hồi hoặc thiết bị chuyển mạng.
3. Thực hiện các lần reconnect theo backoff.
4. Mở transport mới và hoàn thành handshake RESUME.
5. Đồng bộ vị trí và phát lại dữ liệu còn thiếu.

Có thể dùng công thức lập kế hoạch:

\[
T_{retention} \ge T_{detect} + T_{reconnect} + T_{resume} + T_{replay} + T_{margin}
\]

Đây là ngân sách thời gian để thiết kế, không phải công thức bắt buộc của wire protocol. Ví dụ, nếu ứng dụng cần tối đa 45 giây để phát hiện và reconnect, 5 giây cho handshake, 10 giây cho replay và 20 giây dự phòng, retention nên ít nhất khoảng 80 giây. Sau đó cần kiểm tra với phân phối thời gian gián đoạn thực tế.

### 5.1. Retention quá ngắn

Nếu session hết hạn trước khi client reconnect, server có thể đã xóa token/session state và buffer. Client không thể resume session cũ dù transport mới đã mở thành công. Ứng dụng phải tạo session mới, khôi phục subscription và đồng bộ lại trạng thái nghiệp vụ.

### 5.2. Retention quá dài

Giữ session lâu hơn làm tăng số session nhàn rỗi, resume store và metadata cần duy trì. Nếu số client lớn, thiết bị thường xuyên offline hoặc có nhiều session bỏ quên, thời gian giữ quá dài có thể làm tăng bộ nhớ, file descriptor và chi phí quản lý state.

Chọn retention dựa trên mục tiêu phục hồi và phân phối thời gian mất kết nối, đồng thời đặt giới hạn tổng số session và chính sách dọn session hết hạn.

## 6. Phân biệt session retention với KEEPALIVE và timeout khác

Các timeout trong RSocket giải quyết những câu hỏi khác nhau:

| Tham số | Câu hỏi được trả lời | Ảnh hưởng |
|---|---|---|
| KEEPALIVE interval | Bao lâu client gửi tín hiệu kiểm tra? | Tần suất phát KEEPALIVE và lưu lượng điều khiển. |
| KEEPALIVE Max Lifetime | Client chờ phản hồi KEEPALIVE tối đa bao lâu trước khi coi peer không còn hoạt động? | Thời gian phát hiện peer không phản hồi theo chính sách client. |
| Session retention | Sau khi transport đứt, state Resume được giữ trong bao lâu? | Cửa sổ thời gian để khôi phục logical session. |
| Stream/request timeout | Một tương tác nghiệp vụ được phép chạy trong bao lâu? | Có thể kết thúc một stream dù connection vẫn hoạt động. |
| TCP/proxy idle timeout | Hạ tầng giữ transport nhàn rỗi trong bao lâu? | Có thể đóng transport độc lập với session retention. |

Không đặt tất cả timeout bằng một giá trị. KEEPALIVE giúp phát hiện peer không phản hồi; session retention giữ state sau khi mất transport; timeout nghiệp vụ giới hạn thời gian xử lý request. Khi lập ngân sách retention, tính đến thời gian phát hiện lỗi theo cấu hình KEEPALIVE nhưng vẫn giữ các mục tiêu độc lập.

## 7. Cấu hình và quản lý trong Java/Spring

Trong RSocket Java, Resume được cấu hình ở tầng `RSocketConnector` cùng cơ chế lưu trạng thái/resume store. Ứng dụng Spring có thể tùy chỉnh connector thông qua builder của `RSocketRequester` hoặc cấu hình transport tương ứng. Tên API và khả năng cấu hình buffer phụ thuộc phiên bản thư viện; hãy kiểm tra đúng version đang dùng thay vì sao chép một property không được Spring Boot chuẩn hóa.

Khi triển khai, cần xác định rõ các mục sau trong cấu hình của ứng dụng:

| Mục cấu hình | Giá trị cần quyết định |
|---|---|
| Resume enabled | Client và server có hỗ trợ, bật và chấp nhận Resume hay không. |
| Resume token | Cách tạo token ngẫu nhiên, duy nhất và gắn với session. |
| Resume store | Lưu frame outbound chưa xác nhận ở memory hay store tùy chỉnh. |
| Max buffer bytes | Giới hạn byte cho mỗi session/chiều outbound theo khả năng API. |
| Session retention | Thời gian giữ session state sau khi transport đứt. |
| Reconnect retry | Số lần thử, backoff, jitter và tổng reconnect window. |
| Overflow policy | Hành vi khi buffer đầy hoặc peer resume quá muộn. |

Không có một cặp `buffer size` và `session duration` mặc định phù hợp cho mọi ứng dụng. Mặc định của một phiên bản thư viện chỉ là điểm bắt đầu; phải đo tải, kiểm tra giới hạn store và thử lỗi mạng trước khi dùng production.

## 8. Bảo mật và khả năng phục hồi sau restart

Resume token giúp peer nhận diện session và có thể cho phép tiếp tục session đó. Hãy xem token là dữ liệu nhạy cảm:

- Sinh token đủ khó đoán và không tái sử dụng giữa các session.
- Không ghi token đầy đủ vào log, trace hoặc metric label.
- Bảo vệ transport bằng TLS khi phù hợp và xác thực peer trước khi chấp nhận resume.
- Ràng buộc session với danh tính đã xác thực/tenant; token không thay thế cơ chế authentication và authorization.
- Xóa token và state khi session hết hạn hoặc bị đóng có chủ đích.

Nếu resume store chỉ ở memory, process restart thường làm mất buffer và session state. Khi đó, dù client có token và reconnect trong retention window, server mới không có đủ dữ liệu để resume. Muốn chịu được restart hoặc failover sang node khác, cần store có khả năng chia sẻ/lưu bền vững và cơ chế định tuyến session tới nơi giữ state. Không phải implementation nào cũng hỗ trợ điều này; phải kiểm tra khả năng của thư viện và kiến trúc triển khai.

Ngay cả khi Resume hoạt động, nó phục hồi luồng frame của session, không thay thế lưu trạng thái nghiệp vụ. Các giao dịch đã commit, job nền, event log và checkpoint cần cơ chế lưu trữ riêng. Nếu resume thất bại và ứng dụng tạo session mới, event ID, sequence number và idempotency giúp đồng bộ lại an toàn.

## 9. Chỉ số cần theo dõi

Để điều chỉnh buffer và retention, nên thu thập các chỉ số theo session và tổng hệ thống:

- Resume buffer occupancy theo byte, dung lượng tối đa và high-water mark.
- Tốc độ frame/byte outbound, tốc độ peer xác nhận và tuổi của frame chưa được xác nhận lâu nhất.
- Số lần transport disconnect, resume attempt, resume success và resume failure.
- Nguyên nhân resume thất bại: token không hợp lệ, session hết hạn, buffer thiếu vị trí cần replay hoặc lỗi transport.
- Số session đang được giữ, tuổi session, số session hết hạn và số session bị dọn.
- Số byte được replay, thời gian replay và thời gian từ disconnect tới khi stream hoạt động lại.
- Số lần buffer overflow, số sự kiện bị sampling/drop ở tầng ứng dụng và số lần chuyển sang kết nối mới.

Không đưa resume token hoặc dữ liệu định danh nhạy cảm vào nhãn metric. Dùng correlation ID không nhạy cảm để ghép log và trace của một lần disconnect/reconnect.

## 10. Kiểm thử buffer và retention

Các ca kiểm thử nên mô phỏng cả lỗi ngắn và lỗi vượt giới hạn:

1. Ngắt transport trong thời gian ngắn, reconnect trước khi session hết hạn và xác nhận cùng logical session được resume.
2. Gửi dữ liệu ở hai hướng trước khi ngắt; xác nhận frame chưa được xác nhận được replay theo đúng thứ tự.
3. Tạo throughput cao hoặc burst lớn; xác nhận buffer occupancy tăng đúng dự kiến và không vượt ngân sách bộ nhớ.
4. Làm buffer đầy; xác nhận implementation báo lỗi hoặc từ chối resume theo hợp đồng, không âm thầm bỏ dữ liệu chưa xác nhận.
5. Reconnect sau khi session retention hết hạn; xác nhận resume thất bại rõ ràng và ứng dụng có thể tạo session mới.
6. Dùng token sai hoặc token của principal khác; xác nhận server từ chối resume.
7. Restart process khi dùng in-memory store; xác nhận session cũ không được giả định là còn phục hồi được.
8. Chạy nhiều session đồng thời; đo tổng memory, session cleanup và tác động của một stream có lưu lượng lớn lên các stream cùng connection.
9. Kiểm tra KEEPALIVE timeout, proxy idle timeout và retention cùng nhau để tránh khoảng reconnect lớn hơn cửa sổ giữ session.

Trong kiểm thử tích hợp, cần xác minh không chỉ việc transport mới mở thành công mà cả stream cũ, vị trí frame, dữ liệu replay, buffer cleanup và trạng thái ứng dụng sau resume.

## 11. Kết luận

Resume buffer phải đủ byte để giữ các frame outbound chưa được xác nhận trong khoảng gián đoạn dự kiến; session retention phải đủ dài để peer phát hiện lỗi, reconnect, hoàn tất RESUME và nhận lại dữ liệu. Tính buffer theo throughput đỉnh, thời gian outage và burst; tính retention theo toàn bộ reconnect/replay window. Theo dõi occupancy và thời gian giữ session, kiểm thử overflow/expiry, bảo vệ resume token và chuẩn bị phương án khôi phục nghiệp vụ khi session cũ không thể tiếp tục.
