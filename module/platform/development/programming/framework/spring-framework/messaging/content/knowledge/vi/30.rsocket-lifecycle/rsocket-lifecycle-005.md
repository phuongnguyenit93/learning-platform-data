# Reconnect và giới hạn khôi phục yêu cầu đang chạy

## Mục tiêu

Sau bài này, bạn có thể phân biệt việc mở lại kết nối RSocket với việc tiếp tục một phiên RSocket đã bị ngắt; cấu hình retry ở đúng tầng; giải thích điều gì xảy ra với request đang chạy; và thiết kế cơ chế phục hồi an toàn khi server đã xử lý request nhưng client chưa nhận được phản hồi.

## 1. Phân biệt transport connection, session và stream

RSocket chạy trên một transport như TCP hoặc WebSocket. Khi transport được thiết lập, hai phía trao đổi frame `SETUP` để tạo ngữ cảnh giao tiếp. Sau đó, mỗi tương tác tạo một stream riêng, có thể là:

- **Request-Response:** một request và tối đa một response.
- **Request-Stream:** một request mở đầu cho một luồng response.
- **Channel:** hai phía trao đổi các luồng dữ liệu hai chiều.
- **Fire-and-Forget:** gửi một thông điệp mà không chờ response.

Ba khái niệm cần tách biệt:

- **Transport connection** là đường truyền vật lý hoặc logic hiện tại, ví dụ một kết nối TCP.
- **RSocket session** là ngữ cảnh giao thức gắn với một phiên kết nối. Khi bật resumption, session có thể tồn tại qua nhiều transport connection.
- **Stream** là một tương tác cụ thể bên trong session. Stream có trạng thái, số thứ tự và vòng đời riêng.

Mất TCP/WebSocket không tự động có nghĩa là nghiệp vụ trên server đã dừng. Server có thể đã nhận request, đang xử lý, đã ghi dữ liệu, hoặc đã gửi response nhưng response chưa tới client. Vì vậy, việc client nhìn thấy lỗi kết nối không cho biết chắc chắn request đã được thực thi đến đâu.

## 2. Ba cơ chế thường bị nhầm lẫn

| Cơ chế | Phạm vi phục hồi | Điều nó làm | Điều nó không bảo đảm |
|---|---|---|---|
| Reconnect | Transport connection | Tạo một kết nối RSocket mới sau khi kết nối cũ mất | Không tự khôi phục stream cũ hoặc gửi lại request đang chạy |
| Protocol resumption | RSocket session và các stream còn trạng thái | Nối lại session và phát lại các frame còn được lưu để stream tiếp tục | Không bảo đảm session luôn được chấp nhận, không tạo exactly-once cho nghiệp vụ |
| Retry ở tầng request | Một thao tác ứng dụng | Đăng ký lại publisher và gửi lại thao tác theo chính sách retry | Có thể thực thi nghiệp vụ lần hai nếu lần đầu đã chạy nhưng response bị mất |

**Reconnect và retry request là hai việc khác nhau.** Reconnect cung cấp một kết nối mới. Ứng dụng vẫn phải quyết định request nào cần được gửi lại, gửi lại bao nhiêu lần và khi nào dừng.

**Resumption khác reconnect thông thường.** Resumption cố gắng giữ nguyên session và các stream đang hoạt động bằng cách trao đổi trạng thái và phát lại frame. Đây là tính năng tùy chọn của giao thức, không phải mặc định mà mọi RSocket server đều hỗ trợ.

Trong RSocket Java, `RSocketConnector.reconnect(Retry)` và `RSocketConnector.resume(Resume)` là hai chế độ loại trừ lẫn nhau. Nếu cấu hình cả hai, chế độ `resume` được ưu tiên. Hãy chọn một chiến lược rõ ràng dựa trên khả năng của server và yêu cầu nghiệp vụ.

## 3. Reconnect: mở kết nối mới

Spring cung cấp `RSocketRequester.Builder.rsocketConnector(...)` để tùy chỉnh `io.rsocket.core.RSocketConnector`. Ví dụ dưới đây dùng API `tcp(...)` của Spring Framework hiện hành. Kết nối được tạo lười khi có request đầu tiên.

~~~java
import java.time.Duration;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.reconnect(
        Retry.backoff(3, Duration.ofMillis(500))
            .maxBackoff(Duration.ofSeconds(5))))
    .tcp("localhost", 7000);
~~~

Ý nghĩa của cấu hình:

1. `reconnect(...)` yêu cầu connector quản lý một RSocket dùng chung cho các subscriber.
2. Khi connection hiện tại mất, lần đăng ký tiếp theo có thể kích hoạt việc tạo connection mới.
3. `Retry.backoff(3, ...)` giới hạn số lần thử và tăng dần thời gian chờ; `maxBackoff` đặt trần cho khoảng chờ.
4. Đây là chính sách tạo lại connection, không phải chính sách phát lại mọi request đã thất bại.

Tài liệu RSocket Java nêu rõ subscriber của từng request vẫn cần retry riêng nếu muốn gửi lại request. Ví dụ:

~~~java
import java.time.Duration;

import io.rsocket.exceptions.ConnectionErrorException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<OrderStatus> status = requester.route("orders.status")
    .data(orderId)
    .retrieveMono(OrderStatus.class)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(250))
        .filter(ConnectionErrorException.class::isInstance));
~~~

Đây là đoạn mã minh họa bên trong service đã có `requester`, `orderId` và kiểu `OrderStatus`. Bộ lọc chỉ là ví dụ cho lỗi kết nối; trong ứng dụng thực tế, hãy phân loại lỗi theo phiên bản RSocket, transport và quy tắc nghiệp vụ của hệ thống. Không retry lỗi validation, lỗi quyền truy cập hoặc lỗi nghiệp vụ không thể khắc phục bằng cách gửi lại.

Khi publisher được đăng ký lại, thao tác request được tạo và gửi lại. Điều đó có thể đúng với một truy vấn đọc, nhưng nguy hiểm với thao tác ghi dữ liệu. Nếu server đã tạo đơn hàng rồi mà response bị mất, lần retry có thể tạo thêm đơn hàng thứ hai.

## 4. Protocol resumption: tiếp tục session và stream

Resumption là phần mở rộng tùy chọn của giao thức RSocket. Cả requester lẫn responder phải hỗ trợ và bật tính năng này. Khi transport bị ngắt, client mở transport mới và gửi frame `RESUME` cùng token nhận diện session và vị trí frame đã nhận. Server chỉ tiếp tục nếu còn nhận diện được session và còn đủ trạng thái/frame cần thiết; khi chấp nhận, server trả `RESUME_OK`. Hai phía sau đó tiếp tục trao đổi từ các vị trí đã thống nhất và có thể phát lại những frame còn thiếu trong bộ lưu trữ.

Với Spring, có thể cấu hình connector cấp thấp qua `rsocketConnector`. Ví dụ dưới đây minh họa cấu hình ở client:

~~~java
import java.time.Duration;

import io.rsocket.core.Resume;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

Resume clientResume = new Resume()
    .sessionDuration(Duration.ofMinutes(5))
    .retry(Retry.backoff(10, Duration.ofSeconds(1)));

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.resume(clientResume))
    .tcp("localhost", 7000);
~~~

Phía server cũng phải bật resumption cho cùng loại kết nối. Với server được tạo bằng RSocket Java và handler từ Spring:

~~~java
import java.time.Duration;

import io.rsocket.core.Resume;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import reactor.util.retry.Retry;

// handler là RSocketMessageHandler đã được cấu hình trong Spring.
Resume serverResume = new Resume()
    .sessionDuration(Duration.ofMinutes(5))
    .retry(Retry.backoff(10, Duration.ofSeconds(1)));

RSocketServer.create(handler.responder())
    .resume(serverResume)
    .bind(TcpServerTransport.create("localhost", 7000))
    .block();
~~~

Đây là các mảnh cấu hình, không phải ứng dụng độc lập. Cần có dependency RSocket transport phù hợp, một `RSocketMessageHandler` đã cấu hình, server đang lắng nghe và phiên bản Spring/RSocket Java tương thích. API kết nối có thể khác ở các phiên bản Spring cũ; hãy kiểm tra Javadoc đúng phiên bản trong dự án trước khi sao chép cấu hình.

### Những điều kiện để resumption thành công

- Hai đầu đều hỗ trợ và bật Resume; server không hỗ trợ có thể từ chối `SETUP` hoặc `RESUME`.
- Client phải giữ token của session cũ và gửi yêu cầu resume trong thời gian session còn hiệu lực.
- Server phải giữ session, trạng thái stream và các frame chưa được xác nhận đủ lâu để phát lại.
- Bộ lưu frame phải còn liên tục từ vị trí cần khôi phục. Nếu frame cần thiết đã bị loại bỏ hoặc bộ lưu không còn đủ dữ liệu, server có thể từ chối resume.
- Client phải kết nối tới đúng trạng thái session. Trong hệ thống nhiều node, load balancer có thể đưa client sang node khác; node đó phải truy cập được trạng thái dùng chung hoặc hệ thống phải định tuyến về node đang giữ session.
- Các tham số phiên như định dạng data/metadata phải tương thích với session ban đầu.

`sessionDuration` giới hạn khoảng thời gian lưu trạng thái session sau khi mất kết nối; `retry` điều khiển việc thử kết nối lại để resume. Cấu hình retry dài hơn thời gian server giữ session không giúp khôi phục được session đã hết hạn.

Resumption chỉ là nỗ lực phục hồi lạc quan. Nó có thể thất bại khi server restart, session/token bị mất, thời gian gián đoạn vượt quá thời hạn, buffer không còn frame cần thiết, hoặc server chủ động từ chối. Nếu dùng bộ lưu trong bộ nhớ, trạng thái đó mất khi tiến trình bị dừng; muốn hỗ trợ failover hoặc restart cần thiết kế lưu trữ và định tuyến phù hợp với triển khai thực tế.

## 5. Giới hạn quan trọng với request đang chạy

### Không có bảo đảm exactly-once cho nghiệp vụ

RSocket resumption theo dõi và phát lại frame ở tầng giao thức. Nó không biết một transaction cơ sở dữ liệu đã commit hay chưa, cũng không biết một email đã được gửi hay một khoản thanh toán đã được ghi nhận hay chưa. Đặc tả giao thức không đưa ra bảo đảm atomicity hoặc transactionality cho các frame đã được xử lý.

Ví dụ với Request-Response:

1. Client gửi `createOrder`.
2. Server nhận request và ghi đơn hàng thành công.
3. Server gửi response.
4. Mạng bị ngắt trước khi client nhận response.
5. Client chỉ thấy lỗi kết nối; client không thể suy ra đơn hàng đã được tạo hay chưa.

Nếu client gửi lại request như một thao tác mới, server có thể tạo đơn hàng trùng. Resumption có thể giúp tiếp tục stream và phát lại frame, nhưng không thay thế tính idempotent của nghiệp vụ.

### Cách bảo vệ thao tác có side effect

Với thao tác tạo, cập nhật, thanh toán hoặc gửi thông báo:

1. Client tạo một `requestId` hoặc idempotency key ổn định cho một ý định nghiệp vụ.
2. Client gửi key đó cùng payload; mọi lần retry của cùng ý định phải dùng lại key, không tạo key mới.
3. Server lưu key và kết quả xử lý theo cách nguyên tử với side effect (ví dụ cùng transaction cơ sở dữ liệu).
4. Khi nhận lại key đã xử lý, server trả kết quả đã lưu thay vì thực hiện side effect lần nữa.
5. Có thời hạn lưu key phù hợp với thời gian retry và khả năng client gửi lại muộn.

Không chỉ lưu key ở client. Việc chống trùng phải được thực thi ở phía sở hữu dữ liệu hoặc side effect.

### Khôi phục theo từng interaction model

- **Request-Response:** retry có thể gửi lại toàn bộ thao tác. Dùng được cho truy vấn đọc hoặc command có idempotency key. Không xem timeout là bằng chứng server chưa xử lý.
- **Request-Stream:** nếu resumption thành công, stream có thể tiếp tục. Nếu phải tạo request mới, hãy gửi cursor/offset hoặc số thứ tự cuối cùng đã xử lý để server phát tiếp từ checkpoint; client nên loại trùng theo sequence.
- **Channel:** đây là luồng hai chiều. Khi mất session và phải tạo session mới, ứng dụng cần khôi phục cả trạng thái gửi lẫn trạng thái nhận, ví dụ sequence number, acknowledgement và checkpoint.
- **Fire-and-Forget:** không có response để xác nhận server đã nhận hoặc xử lý. Nếu cần biết kết quả giao nhận, dùng Request-Response có acknowledgement hoặc một cơ chế outbox/durable messaging ở tầng ứng dụng.

## 6. Thiết kế retry có kiểm soát

Một chính sách retry an toàn nên có các đặc điểm sau:

- **Có giới hạn:** đặt số lần thử tối đa hoặc deadline tổng thể. Không retry vô hạn mà không có cơ chế dừng và cảnh báo.
- **Có backoff và jitter:** tăng thời gian chờ giữa các lần thử, thêm độ lệch ngẫu nhiên để nhiều client không đồng loạt dồn tải vào server vừa phục hồi.
- **Phân loại lỗi:** retry lỗi transport tạm thời; không retry lỗi dữ liệu, xác thực, phân quyền hoặc lỗi nghiệp vụ không thể tự hết.
- **Có timeout:** giới hạn thời gian chờ cho một request và tổng thời gian phục hồi. Không để request treo lâu hơn thời hạn nghiệp vụ.
- **Có giới hạn tải:** cân nhắc circuit breaker, bulkhead và giới hạn số request đang chờ để tránh retry storm.
- **Giữ nguyên định danh nghiệp vụ:** mọi lần thử của cùng một thao tác phải mang cùng idempotency key.
- **Có fallback:** khi resume bị từ chối hoặc retry hết lượt, tạo session mới và phục hồi ở tầng ứng dụng bằng requestId, cursor hoặc checkpoint.

Keepalive giúp phát hiện peer hoặc connection đã mất dựa trên heartbeat và thời gian chờ. Nó không gửi lại request và không tự khôi phục stream. Giảm khoảng keepalive có thể phát hiện lỗi nhanh hơn nhưng làm tăng lưu lượng và nguy cơ kết luận nhầm khi mạng chập chờn.

## 7. Chọn chiến lược theo tình huống

| Tình huống | Chiến lược nên cân nhắc |
|---|---|
| Server không hỗ trợ Resume; request đọc ngắn | Reconnect kết hợp retry có giới hạn ở tầng request |
| Request ghi có thể được gửi lại | Retry có idempotency key và chống trùng ở server |
| Stream dài, mất mạng ngắn, hai phía giữ session | Protocol resumption |
| Stream dài nhưng session có thể mất hoặc hết hạn | Resumption kết hợp cursor/checkpoint ở tầng ứng dụng |
| Triển khai nhiều node hoặc rolling restart | Kiểm tra nơi lưu session/frame và cách định tuyến; luôn có đường phục hồi bằng requestId/cursor |
| Fire-and-Forget cần bảo đảm giao nhận | Bổ sung acknowledgement hoặc durable messaging; không dựa vào reconnect đơn thuần |

Không có lựa chọn nào thay thế việc xác định yêu cầu nghiệp vụ: có thể mất dữ liệu đến mức nào, chấp nhận trễ bao lâu, có được phép xử lý trùng hay không và client có thể tiếp tục từ checkpoint nào.

## 8. Kiểm thử và quan sát

Không chỉ kiểm tra trường hợp server tắt rồi bật lại. Hãy mô phỏng các điểm ngắt khác nhau:

1. Ngắt mạng khi không có stream hoạt động; xác minh reconnect tạo connection mới.
2. Ngắt mạng khi Request-Response đang chờ; xác minh request thất bại hay được resume theo cấu hình.
3. Cho server commit side effect rồi mới làm mất response; xác minh retry không tạo bản ghi trùng.
4. Ngắt mạng giữa một Request-Stream; kiểm tra stream tiếp tục, không mất hoặc lặp phần tử.
5. Giữ kết nối ngắt lâu hơn `sessionDuration`; xác minh resume thất bại có kiểm soát và ứng dụng chuyển sang checkpoint.
6. Restart server hoặc chuyển client sang node khác; xác minh đúng hành vi khi session store không còn sẵn.
7. Gửi lỗi nghiệp vụ có chủ đích; xác minh bộ lọc retry không gửi lại request đó.

Nên ghi nhận số lần reconnect, số lần resume thành công/bị từ chối, số lần retry theo route, thời gian phục hồi, số request hết deadline, số stream bị gián đoạn và tỷ lệ request trùng bị idempotency layer chặn. Không ghi payload nhạy cảm hoặc token resume vào log.

## 9. Lỗi thường gặp

- **Chỉ bật reconnect và kỳ vọng stream tự chạy tiếp:** reconnect tạo connection mới; muốn retry request phải đặt chính sách ở publisher của request.
- **Bật resume ở client nhưng quên server:** cả hai phía phải hỗ trợ và bật resumption.
- **Cấu hình reconnect và resume cùng lúc:** hai chế độ loại trừ lẫn nhau; resume được ưu tiên.
- **Retry mọi exception:** có thể lặp lỗi nghiệp vụ và gây tải không cần thiết. Hãy lọc lỗi tạm thời.
- **Tạo idempotency key mới cho mỗi lần retry:** server xem đó là các thao tác khác nhau và không thể chống trùng.
- **Cho rằng resume bảo đảm exactly-once:** giao thức phục hồi frame/stream, không quản lý transaction nghiệp vụ.
- **Không kiểm thử hết hạn session hoặc restart node:** trường hợp mạng ngắt ngắn thường dễ thành công, nhưng không đại diện cho mọi sự cố.
- **Retry không có deadline hoặc backoff:** có thể tạo retry storm và kéo dài request vô hạn.

## 10. Checklist triển khai

- [ ] Đã xác định rõ cần reconnect, resume hay retry request.
- [ ] Đã kiểm tra server và client dùng phiên bản RSocket tương thích.
- [ ] Nếu dùng resume, cả hai phía đều bật và giữ trạng thái đủ lâu.
- [ ] Đã tính dung lượng frame store và cách định tuyến khi chạy nhiều node.
- [ ] Request có side effect dùng idempotency key ổn định và server chống xử lý trùng.
- [ ] Stream có cursor/sequence/checkpoint để tiếp tục khi phải tạo request mới.
- [ ] Retry có bộ lọc lỗi, backoff, giới hạn lần thử và deadline.
- [ ] Đã kiểm thử mất response sau khi server commit, hết hạn session và server restart.
- [ ] Có log/metric để phân biệt reconnect, resume, retry và phục hồi ở tầng nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, cấu hình `RSocketConnector` và mô hình tương tác.
- [RSocket Protocol — Resuming Operation](https://github.com/rsocket/rsocket/blob/master/Protocol.md#resuming-operation): token, vị trí frame, điều kiện chấp nhận/từ chối resume và các giả định của giao thức.
- [RSocket Java — RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): hành vi của `reconnect(Retry)`, `resume(Resume)` và yêu cầu retry riêng ở tầng request.
