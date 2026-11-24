# Khoảng gửi KEEPALIVE và thời gian sống tối đa của kết nối

RSocket chạy trên một transport hướng kết nối như TCP hoặc WebSocket. Một kết nối có thể vẫn còn tồn tại ở phía ứng dụng trong khi đường truyền bên dưới đã bị đứt, thiết bị chuyển mạng hoặc một proxy đã loại bỏ kết nối nhàn rỗi. Nếu không có dữ liệu ứng dụng được gửi trong một khoảng thời gian dài, hai bên có thể không nhận ra ngay peer đã mất kết nối.

RSocket giải quyết việc kiểm tra tình trạng kết nối bằng **KEEPALIVE frame**. Khi thiết lập phiên, client gửi hai tham số trong SETUP: khoảng thời gian giữa các frame KEEPALIVE và thời gian tối đa client chờ server phản hồi trước khi coi server không còn hoạt động. Chọn hai giá trị này ảnh hưởng trực tiếp đến tốc độ phát hiện kết nối lỗi, tải mạng, pin thiết bị di động và độ ổn định khi mạng có độ trễ biến động.

## 1. KEEPALIVE kiểm tra điều gì?

KEEPALIVE là frame ở cấp giao thức RSocket, dùng để xác nhận một kết nối vẫn có thể trao đổi frame với peer. Nó không phải một request nghiệp vụ và cũng không thuộc riêng một stream.

Các đặc điểm chính:

- KEEPALIVE luôn dùng **Stream ID = 0**, vì nó áp dụng cho toàn bộ kết nối.
- Client phải gửi KEEPALIVE định kỳ với cờ **R (Respond) = 1**.
- Khi nhận KEEPALIVE có `R = 1`, peer phải gửi lại KEEPALIVE có `R = 0` và echo lại phần data đã nhận.
- Server có thể chủ động gửi KEEPALIVE có `R = 1` khi ứng dụng yêu cầu; client nhận được cũng phải phản hồi theo quy tắc trên.
- Nhận KEEPALIVE từ client cho server biết client còn hoạt động; nhận KEEPALIVE từ server cho client biết server còn hoạt động.

Hai phía có thể dùng KEEPALIVE để phát hiện đường truyền không còn hoạt động. Tuy nhiên, theo đặc tả, client là phía phải chủ động gửi định kỳ. Server có thể gửi chủ động theo yêu cầu ứng dụng, còn mọi peer nhận frame với `R = 1` đều phải phản hồi.

## 2. Hai tham số trong SETUP

Client truyền hai tham số trong SETUP frame (Stream ID bằng `0`):

| Tham số | Ý nghĩa | Đơn vị và ràng buộc |
|---|---|---|
| `Time Between KEEPALIVE Frames` | Khoảng thời gian client dự kiến giữa hai lần gửi KEEPALIVE định kỳ. | Millisecond, số unsigned 31-bit, MUST lớn hơn `0`. |
| `Max Lifetime` | Khoảng thời gian client cho phép server không phản hồi KEEPALIVE trước khi client coi server đã chết hoặc không còn truy cập được. | Millisecond, số unsigned 31-bit, MUST lớn hơn `0`. |

Hai giá trị đều được mã hóa trong SETUP dưới dạng số 31-bit. Phạm vi biểu diễn tối đa là `2^31 - 1` millisecond. Đây là tham số của phiên được client công bố lúc thiết lập kết nối, không phải giá trị cấu hình cho từng request hoặc từng stream.

### 2.1. Time Between KEEPALIVE Frames

Tham số này là chu kỳ gửi KEEPALIVE của client. Ví dụ, nếu đặt `20.000 ms`, client sẽ gửi KEEPALIVE định kỳ với khoảng cách xấp xỉ 20 giây.

Chu kỳ ngắn giúp peer sớm nhận ra kết nối đã mất, đồng thời tạo lưu lượng kiểm tra thường xuyên hơn. Chu kỳ dài giảm số frame và mức tiêu thụ năng lượng, nhưng làm chậm khả năng phát hiện sự cố. Chu kỳ cần phù hợp với loại mạng, thiết bị và thời gian nhàn rỗi mà proxy hoặc load balancer cho phép.

Đặc tả đưa ra các mốc tham khảo theo loại kết nối: khoảng `500 ms` có thể hợp lý cho kết nối giữa các server; với kết nối từ thiết bị di động đến server, khoảng gửi thường lớn hơn `30.000 ms`. Đây là ví dụ định hướng theo bối cảnh, không phải một giá trị bắt buộc cho mọi hệ thống.

### 2.2. Max Lifetime

Max Lifetime là giới hạn chờ phản hồi mà client dùng để đánh giá server. Khi client gửi KEEPALIVE có `R = 1`, server phải phản hồi bằng KEEPALIVE có `R = 0`. Nếu server không phản hồi trong khoảng Max Lifetime, client có thể kết luận peer đã mất kết nối.

Đây là giới hạn chờ theo chiều client đánh giá server được mô tả trong SETUP. Nếu server cần một chính sách timeout riêng để phát hiện client ngừng gửi KEEPALIVE, implementation hoặc ứng dụng phía server phải quản lý chính sách đó; không nên mặc định rằng Max Lifetime trong SETUP cũng là timeout đối xứng cho server.

Giá trị này cần đủ rộng để chịu được nhiều lần KEEPALIVE bị trễ hoặc thất lạc, độ trễ mạng tăng đột biến, scheduler tạm dừng và các khoảng dừng của runtime. Nếu đặt quá ngắn, client có thể đánh dấu một kết nối vẫn khỏe mạnh thành lỗi. Nếu đặt quá dài, ứng dụng phải chờ lâu mới nhận ra server đã mất.

Max Lifetime không phải tuổi thọ tối đa của TCP socket, không phải thời hạn của một stream, cũng không phải thời gian sống của session khi dùng Resume. Nó là ngưỡng chờ phản hồi KEEPALIVE mà client sử dụng cho việc phát hiện peer không còn hoạt động.

## 3. Trình tự trao đổi KEEPALIVE

Một kết nối bình thường có trình tự khái quát như sau:

```text
Client                                      Server
  |                                            |
  |--------------- SETUP --------------------->|
  |       interval, maxLifetime, MIME types    |
  |                                            |
  |<-------------- SETUP response -------------|
  |                                            |
  |---- KEEPALIVE (R=1, data=D) --------------->|
  |                                            |
  |<--- KEEPALIVE (R=0, data=D) ---------------|
  |                                            |
  |       ... chờ đến chu kỳ tiếp theo ...     |
  |                                            |
  |---- KEEPALIVE (R=1, data=E) --------------->|
  |                                            |
  |<--- KEEPALIVE (R=0, data=E) ---------------|
  |                                            |
```

Quy tắc echo data giúp bên gửi ghép phản hồi với KEEPALIVE đã phát. Peer phản hồi phải giữ nguyên data nhận được. Frame phản hồi có `R = 0`, do đó không kích hoạt thêm một vòng phản hồi mới.

Nếu server chủ động gửi KEEPALIVE với `R = 1`, client cũng phải trả KEEPALIVE `R = 0` và echo data. Điều này cho phép server chủ động kiểm tra client khi ứng dụng cần, dù chu kỳ gửi định kỳ trong SETUP là trách nhiệm của client.

### 3.1. Các trường trong KEEPALIVE frame

KEEPALIVE có Frame Type `0x03` và Stream ID bằng `0`. Phần nội dung gồm:

- Cờ `R` (Respond): yêu cầu peer phản hồi bằng KEEPALIVE hay không.
- `Last Received Position`: vị trí đã nhận gần nhất, có thể dùng trong cơ chế Resume. Nếu implementation không hỗ trợ trường vị trí thì đặt bằng `0`.
- `Data`: dữ liệu tùy chọn được peer echo lại trong frame phản hồi.

`Last Received Position` phục vụ theo dõi tiến trình truyền khi có resumability. Nó không phải số thứ tự của request nghiệp vụ và không thay thế cờ `R` hoặc hai tham số thời gian trong SETUP.

## 4. Chọn interval và max lifetime

Hai tham số giải quyết hai câu hỏi khác nhau: interval xác định tần suất gửi tín hiệu; max lifetime xác định thời gian chờ trước khi kết luận peer không phản hồi. Trong vận hành, max lifetime thường phải lớn hơn interval và đủ chứa một số chu kỳ bị trễ hoặc bỏ lỡ.

Ví dụ, một client-to-server nội bộ có thể bắt đầu với interval 20 giây và max lifetime 90 giây. Với hai giá trị này, client phát KEEPALIVE khoảng mỗi 20 giây và có khoảng chờ tối đa 90 giây cho phản hồi từ server trước khi xem kết nối là không còn hoạt động. Cần đo thực tế để điều chỉnh theo RTT, jitter, thời gian tạm dừng của JVM và chính sách timeout của hạ tầng.

| Bối cảnh | Hướng chọn interval | Lưu ý khi chọn max lifetime |
|---|---|---|
| Server-to-server trong mạng ổn định | Có thể ngắn; đặc tả nêu 500 ms là một mốc hợp lý. | Tính đến RTT, tải và thời gian scheduler có thể bị trễ; tránh timeout giả. |
| Mobile-to-server | Thường dài hơn 30 giây theo ví dụ trong đặc tả. | Dự trù độ trễ và thời gian thiết bị chuyển mạng hoặc tạm ngủ; cân bằng với thời gian phát hiện lỗi. |
| Qua proxy/load balancer có idle timeout | Chọn interval ngắn hơn ngưỡng nhàn rỗi của hạ tầng với khoảng an toàn. | Đủ lớn để chịu jitter, nhưng không vượt quá mục tiêu phát hiện lỗi của ứng dụng. |
| Kết nối có lưu lượng thấp, nhưng cần phát hiện peer mất | Giữ chu kỳ đều theo yêu cầu phát hiện lỗi. | Đặt theo thời gian chờ lỗi mà sản phẩm chấp nhận được. |

Không có một cặp giá trị phù hợp với mọi ứng dụng. Trước khi chọn, hãy tìm hiểu idle timeout của load balancer, reverse proxy, NAT và firewall trên đường đi. Nếu interval dài hơn thời gian hạ tầng cho phép kết nối nhàn rỗi, transport có thể bị đóng trước khi RSocket kịp gửi KEEPALIVE tiếp theo.

## 5. Ví dụ cấu hình trong Java

Với RSocket Java, client có thể cấu hình hai tham số thông qua `RSocketConnector.keepAlive(interval, maxLifeTime)`. Ví dụ dưới đây chọn chu kỳ 20 giây và ngưỡng chờ 90 giây:

```java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    ))
    .tcp("localhost", 7000);
```

`RSocketRequester.Builder.rsocketConnector(...)` cho phép tùy chỉnh `RSocketConnector` bên dưới. `keepAlive` nhận hai `Duration` theo thứ tự: khoảng gửi và thời gian tối đa chờ peer phản hồi. Hai giá trị này được đưa vào SETUP khi client mở kết nối. Ví dụ sử dụng TCP; nếu dùng WebSocket, có thể thay `.tcp("localhost", 7000)` bằng `.websocket(uri)`, còn nguyên tắc KEEPALIVE ở tầng RSocket vẫn giữ nguyên.

Trong RSocket Java, mặc định của `RSocketConnector` là interval 20 giây và max lifetime 90 giây. Đây là mặc định của implementation Java, không phải giá trị mặc định bắt buộc của đặc tả giao thức. Hãy kiểm tra phiên bản thư viện đang dùng và cấu hình tường minh nếu ứng dụng có yêu cầu vận hành riêng.

## 6. Timeout, đóng kết nối và phục hồi

Khi không nhận được phản hồi trong Max Lifetime, client có thể xem server là không còn hoạt động. Ứng dụng thường cần xử lý tiếp theo, ví dụ:

1. Đánh dấu kết nối hiện tại không còn sẵn sàng và ngừng gửi request mới qua kết nối đó.
2. Ghi nhận nguyên nhân, thời điểm KEEPALIVE cuối cùng và thời gian timeout để quan sát.
3. Đóng hoặc loại bỏ kết nối theo hành vi của implementation.
4. Nếu chính sách ứng dụng cho phép, tạo kết nối mới và thực hiện lại bước thiết lập phiên.
5. Nếu sử dụng Resume, thử khôi phục session theo cấu hình Resume và trạng thái còn lưu; nếu không thể resume, ứng dụng cần có chiến lược kết nối mới và khôi phục trạng thái nghiệp vụ.

KEEPALIVE chỉ phát hiện peer hoặc đường truyền không phản hồi. Nó không tự định nghĩa retry request nghiệp vụ, không bảo đảm một lệnh chưa được xử lý, và không tự khôi phục stream sau khi kết nối đứt. Với request làm thay đổi dữ liệu, cần thiết kế idempotency key hoặc cơ chế truy vấn trạng thái để tránh thực hiện lặp khi client không biết server đã xử lý đến đâu.

Đặc tả cũng phân biệt phát hiện transport chết với quyết định đóng do nhàn rỗi: thiếu KEEPALIVE có thể giúp phát hiện TCP half-open hoặc WebSocket chết, nhưng chính sách đóng kết nối vì không hoạt động thuộc về ứng dụng. Request keepalive và timeout semantics cũng là trách nhiệm của ứng dụng/implementation. Do đó, không nên xem KEEPALIVE là một chính sách quản lý vòng đời hoàn chỉnh.

## 7. Những lỗi cấu hình thường gặp

- **Interval quá dài so với idle timeout của hạ tầng:** proxy hoặc NAT có thể đóng kết nối trước khi frame KEEPALIVE tiếp theo được gửi.
- **Interval quá ngắn:** tạo nhiều frame điều khiển, tăng tải CPU và mạng; trên thiết bị di động còn làm tăng tiêu thụ pin.
- **Max Lifetime quá sát interval:** một chút jitter hoặc pause của JVM có thể tạo timeout giả.
- **Max Lifetime quá lớn:** phát hiện kết nối chết chậm, khiến request mới có thể bị gửi vào một kết nối không còn hữu dụng.
- **Nhầm Max Lifetime với tuổi thọ session:** Resume có thể duy trì session qua nhiều transport connection; Max Lifetime chỉ là ngưỡng chờ phản hồi KEEPALIVE theo SETUP.
- **Cho rằng KEEPALIVE xác nhận nghiệp vụ:** KEEPALIVE chỉ kiểm tra kết nối. Nó không xác nhận một request đã được xử lý hoặc dữ liệu đã được commit.
- **Phản hồi KEEPALIVE với `R = 1`:** peer nhận phải trả `R = 0`; nếu hai bên cứ yêu cầu phản hồi, có thể tạo vòng ping-pong không cần thiết.

## 8. Kiểm thử và quan sát

Nên kiểm thử các tình huống sau trên đúng transport mà ứng dụng triển khai:

1. Kết nối bình thường: client gửi KEEPALIVE định kỳ và server phản hồi đúng với `R = 0`, data được echo.
2. Server chủ động gửi KEEPALIVE: client phản hồi đúng một lần và không tạo vòng phản hồi liên tục.
3. Server không phản hồi: client phát hiện quá thời gian Max Lifetime theo hành vi của implementation.
4. Mất gói hoặc tăng độ trễ: xác nhận cấu hình không tạo timeout giả trong mức jitter dự kiến.
5. Kết nối nhàn rỗi qua proxy/NAT: xác nhận interval đủ ngắn để duy trì kết nối theo chính sách hạ tầng.
6. Mạng di động chuyển từ Wi-Fi sang cellular hoặc thiết bị tạm ngủ: kiểm tra phát hiện lỗi, reconnect và Resume nếu có bật.
7. Giá trị `0` hoặc vượt phạm vi trường 31-bit: xác nhận cấu hình bị từ chối hoặc được validate trước khi tạo SETUP.

Trong môi trường production, nên theo dõi số KEEPALIVE gửi/nhận, thời điểm nhận gần nhất, số lần timeout, số lần reconnect, thời gian thiết lập lại kết nối và nguyên nhân đóng transport. Các chỉ số này giúp phân biệt server quá tải, mạng không ổn định và cấu hình timeout quá nhạy.

## 9. Kết luận

`Time Between KEEPALIVE Frames` quy định chu kỳ client gửi tín hiệu kiểm tra kết nối; `Max Lifetime` quy định khoảng client chờ server phản hồi trước khi xem peer là không còn hoạt động. Client gửi KEEPALIVE định kỳ với `R = 1`, peer phản hồi bằng `R = 0` và echo data. Hãy chọn interval dựa trên loại mạng và idle timeout của hạ tầng, chọn max lifetime đủ chịu nhiều lần trễ hoặc mất phản hồi, rồi kiểm thử cùng chính sách reconnect/Resume của ứng dụng.

Tài liệu tham khảo:

- [RSocket Protocol – SETUP Frame và KEEPALIVE Frame](https://rsocket.io/about/protocol/)
- [RSocket Java – RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [Spring Framework – RSocketRequester và cấu hình RSocketConnector](https://docs.spring.io/spring-framework/reference/rsocket.html)
