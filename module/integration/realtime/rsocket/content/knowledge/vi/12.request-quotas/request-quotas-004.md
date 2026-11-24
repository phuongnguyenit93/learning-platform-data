# Quy trình cấp, gia hạn và sử dụng hạn ngạch

Trong một luồng RSocket, bên nhận dữ liệu không nhất thiết phải tiêu thụ mọi phần tử ngay khi bên gửi tạo ra. Reactive Streams giải quyết vấn đề này bằng demand: Subscriber cho Publisher biết nó sẵn sàng nhận thêm bao nhiêu phần tử. Có thể xem demand như một hạn ngạch phần tử đang được cấp cho một stream.

Khi mở request-stream hoặc request-channel, requester cấp demand ban đầu bằng trường initial request N. Khi đã dùng hết hoặc gần hết phần demand đó, requester gửi REQUEST_N để cấp thêm. Responder chỉ được phát số phần tử trong phạm vi demand còn lại. Cơ chế này tạo thành một chu trình cấp, sử dụng và gia hạn hạn ngạch, giúp điều tiết dữ liệu và giới hạn lượng công việc đang chờ ở phía tiêu thụ.

Hạn ngạch demand ở đây là số phần tử được phép phát theo giao thức. Nó khác với quota nghiệp vụ như 100 request mỗi phút, giới hạn số kết nối của một tenant hoặc giới hạn chi phí API. Một ứng dụng có thể cần cả hai: demand để kiểm soát luồng dữ liệu và rate limit để bảo vệ tài nguyên nghiệp vụ.

## 1. Demand và hạn ngạch của một stream

Trong Reactive Streams, Subscriber nhận một <code>Subscription</code> qua <code>onSubscribe</code>. Subscriber dùng <code>request(n)</code> để yêu cầu thêm tối đa <code>n</code> phần tử. Tham số phải là số dương; gọi với 0 hoặc số âm vi phạm giao thức.

Demand là số phần tử mà Subscriber còn quyền nhận theo những yêu cầu đã gửi nhưng chưa được tiêu thụ. Nó không phải số phần tử chắc chắn sẽ được phát: Publisher có thể phát ít hơn, tạm dừng hoặc kết thúc trước khi dùng hết demand.

Ví dụ:

~~~text
Requester                               Responder
    |                                      |
    |--- cấp demand ban đầu: 10 ---------->|
    |                                      |
    |<------------- item 1 ----------------|
    |<------------- item 2 ----------------|
    |<------------- item 3 ----------------|
    |                                      |
    |--- gia hạn thêm: 5 ----------------->|
    |                                      |
    |<------------- item 4 ----------------|
    |<------------- item 5 ----------------|
    |                                      |
~~~

Sau khi cấp 10 phần tử, requester đã cho phép responder phát tối đa 10 phần tử theo demand đó. Nếu responder mới phát 3 phần tử, còn 7 phần tử demand chưa được sử dụng. Khi requester gửi thêm 5, tổng demand còn lại trở thành 12: 7 phần tử cũ cộng 5 phần tử mới.

Vì vậy, yêu cầu bổ sung là cộng dồn. Nếu còn 7 mà requester gửi thêm 10, demand mới là 17, không phải thay thế 7 bằng 10.

## 2. Vòng đời cấp, sử dụng và gia hạn hạn ngạch

Một quy trình điều tiết luồng thường có bốn giai đoạn:

~~~text
       MỞ STREAM
           |
           v
   CẤP DEMAND BAN ĐẦU
       initial N
           |
           v
      NHẬN PHẦN TỬ
       tiêu thụ credit
           |
           v
   KIỂM TRA DEMAND CÒN LẠI
       /           \
   còn đủ        gần cạn
     |              |
     |              v
     |        GỬI REQUEST_N
     |              |
     +<-------------+
           |
           v
   COMPLETE / ERROR / CANCEL
       dừng cấp thêm
~~~

**Bước 1 — Cấp demand ban đầu.** Khi requester mở một stream, nó xác định lượng dữ liệu có thể tiếp nhận ngay và gửi số lượng đó trong initial request N. Giá trị này nên dựa trên khả năng xử lý, bộ nhớ và số tác vụ đang chờ của client.

**Bước 2 — Sử dụng hạn ngạch.** Mỗi phần tử được responder phát và requester nhận sẽ tiêu thụ một đơn vị demand. Nếu đã cấp 10 và nhận 4, demand còn lại là 6.

**Bước 3 — Gia hạn.** Khi demand còn lại chạm ngưỡng thấp, requester gửi REQUEST_N với số lượng bổ sung. Việc gia hạn có thể thực hiện từng phần tử hoặc theo lô. Gia hạn theo lô thường giảm số frame điều khiển và giúp responder duy trì luồng dữ liệu ổn định.

**Bước 4 — Kết thúc.** Khi stream hoàn tất, phát lỗi hoặc bị hủy, không tiếp tục cấp demand cho stream đó. Nếu cần nhận dữ liệu lại sau cancellation hoặc lỗi, ứng dụng thường mở một stream mới theo chính sách của mình.

## 3. Initial request N và REQUEST_N trong RSocket

RSocket ánh xạ demand thành các trường của giao thức:

| Cơ chế | Frame | Vai trò |
| --- | --- | --- |
| Demand ban đầu | REQUEST_STREAM hoặc REQUEST_CHANNEL | Cấp số phần tử phản hồi ban đầu khi mở tương tác. |
| Gia hạn demand | REQUEST_N | Cấp thêm số phần tử cho một stream đang hoạt động. |
| Hủy demand | CANCEL | Dừng việc nhận dữ liệu trên stream tương ứng. |
| Kết thúc bình thường | PAYLOAD với COMPLETE hoặc tín hiệu hoàn tất tương ứng | Đóng chiều dữ liệu sau khi hoàn thành. |
| Kết thúc do lỗi | ERROR | Báo lỗi và kết thúc stream hoặc connection tùy phạm vi lỗi. |

Initial request N và REQUEST_N là hạn ngạch theo stream. Chúng không phải một ngân sách chung cho toàn bộ connection. Một connection có thể mang nhiều stream, mỗi stream có demand riêng. Do đó, client có thể yêu cầu nhiều phần tử cho stream telemetry quan trọng và ít phần tử hơn cho stream cập nhật giao diện.

Đối với request-channel, hai phía có thể phát dữ liệu theo hai chiều. Demand cho chiều phản hồi và demand cho chiều request là hai luồng điều tiết riêng; việc cấp demand cho dữ liệu server gửi về không tự động cấp quyền cho client phát thêm dữ liệu lên server.

Request-response chỉ có tối đa một phản hồi nên không cần chu trình gia hạn nhiều phần tử như request-stream. Fire-and-forget không có luồng phản hồi nghiệp vụ, vì vậy không sử dụng demand phản hồi theo cách của request-stream.

Ở tầng Java, Reactive Streams biểu diễn demand bằng kiểu <code>long</code>. Trên dây, RSocket dùng trường số nguyên theo định dạng giao thức cho REQUEST_N và initial request N; thư viện chịu trách nhiệm ánh xạ demand từ API Java sang các frame hợp lệ. Ứng dụng nên dùng API <code>Subscription.request</code> hoặc Reactor thay vì tự đóng gói byte của frame.

## 4. Cách tính demand còn lại

Để quản lý hạn ngạch, có thể dùng công thức:

\[
\text{demand còn lại} =
\text{tổng demand đã cấp} -
\text{số phần tử đã nhận}
\]

Khi cấp thêm một lượng <code>n</code>:

\[
\text{demand mới} =
\text{demand còn lại} + n
\]

Ví dụ, client đặt cửa sổ demand là 20 phần tử và ngưỡng gia hạn là 5:

| Thời điểm | Demand còn lại trước hành động | Hành động | Demand còn lại sau hành động |
| --- | ---: | --- | ---: |
| Mở stream | 0 | Cấp ban đầu 20 | 20 |
| Nhận 8 phần tử | 20 | Tiêu thụ 8 | 12 |
| Nhận thêm 7 | 12 | Tiêu thụ 7 | 5 |
| Chạm ngưỡng | 5 | Cấp thêm 15 | 20 |
| Nhận thêm 12 | 20 | Tiêu thụ 12 | 8 |

Khi demand còn 5, client cấp thêm 15 để đưa cửa sổ trở lại 20. Nếu client cấp thêm 20 ở thời điểm này, demand sẽ tăng lên 25 và có thể vượt khả năng xử lý dự kiến.

Trong code, phải tránh demand âm do bộ đếm bị trừ quá số phần tử đã được cấp. Cần bảo đảm mỗi phần tử chỉ được tính tiêu thụ một lần và chỉ gia hạn khi stream còn hoạt động.

## 5. Chọn kích thước cửa sổ và ngưỡng gia hạn

Kích thước cửa sổ là số phần tử tối đa mà client cho phép đang được phát theo demand đã cấp nhưng chưa nhận. Cửa sổ lớn giúp giảm tần suất gửi REQUEST_N và có thể cải thiện throughput trên đường truyền có độ trễ cao. Tuy nhiên, cửa sổ quá lớn có thể làm tăng bộ nhớ đệm và số phần tử chờ xử lý.

Ngưỡng gia hạn quyết định khi nào client gửi thêm demand. Nếu chỉ gia hạn khi demand bằng 0, responder có thể phải chờ frame REQUEST_N mới tiếp tục phát. Nếu gia hạn sớm hơn, client có thể duy trì luồng ổn định hơn nhưng cần kiểm soát tổng số phần tử đang chờ.

Các yếu tố cần cân nhắc:

- Thời gian trung bình để xử lý một phần tử.
- Kích thước trung bình của payload.
- Bộ nhớ dành cho hàng đợi và buffer.
- Độ trễ round-trip giữa requester và responder.
- Số stream đồng thời trên một connection.
- Khả năng điều tiết của nguồn dữ liệu phía server.

Ví dụ, nếu mỗi payload trung bình 4 KB và ứng dụng cho phép tối đa 500 phần tử đang chờ trên một stream, lượng dữ liệu thô có thể lên tới khoảng 2 MB cho stream đó, chưa tính object overhead, buffer của serializer và dữ liệu trong các scheduler. Nếu có 100 stream cùng cấu hình như vậy, tổng bộ nhớ tiềm năng tăng đáng kể.

Không có một cửa sổ tối ưu cho mọi ứng dụng. Hãy bắt đầu với giá trị nhỏ, đo throughput, độ trễ và bộ nhớ, sau đó điều chỉnh theo tải thực tế.

## 6. Gia hạn theo lô bằng Reactor

Nếu ứng dụng không cần tự quản lý từng lần gọi <code>request(n)</code>, Reactor cung cấp toán tử <code>limitRate</code> để điều tiết lượng demand truyền upstream theo từng lô.

~~~java
Flux<PriceUpdate> prices = requester
    .route("prices.watch")
    .data(new PriceWatchRequest("ACME"))
    .retrieveFlux(PriceUpdate.class)
    .limitRate(32, 8);
~~~

Ví dụ trên giới hạn demand upstream theo lô có high-tide là 32 và low-tide là 8. Khi demand được tiêu thụ tới ngưỡng phù hợp, Reactor yêu cầu thêm phần tử để duy trì cửa sổ. Cần đọc semantics của phiên bản Reactor đang dùng khi chọn tham số, vì toán tử này điều chỉnh demand chứ không giới hạn số request theo giây.

Nếu cần điều khiển trực tiếp, có thể dùng <code>BaseSubscriber</code>. Ví dụ dưới đây cấp ban đầu 20 phần tử và gia hạn khi demand còn 5:

~~~java
final class WindowedSubscriber<T> extends BaseSubscriber<T> {

    private static final long WINDOW = 20;
    private static final long LOW_WATERMARK = 5;

    private long outstanding;

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        outstanding = WINDOW;
        request(WINDOW);
    }

    @Override
    protected void hookOnNext(T value) {
        outstanding--;
        process(value);

        if (outstanding <= LOW_WATERMARK) {
            long additional = WINDOW - outstanding;
            outstanding += additional;
            request(additional);
        }
    }

    @Override
    protected void hookOnError(Throwable error) {
        log.error("Stream failed", error);
    }

    @Override
    protected void hookOnComplete() {
        log.info("Stream completed");
    }

    private void process(T value) {
        // Xử lý một phần tử trước khi tiếp tục.
    }
}
~~~

Trong ví dụ này, <code>outstanding</code> là demand đã cấp nhưng chưa được sử dụng. Sau mỗi phần tử, bộ đếm giảm một. Khi còn 5 hoặc ít hơn, Subscriber yêu cầu đúng lượng cần thiết để khôi phục cửa sổ về 20.

Đây là ví dụ minh họa cho xử lý tuần tự. Nếu <code>process</code> chỉ đưa công việc vào một executor rồi trả về ngay, demand có thể được gia hạn trước khi công việc thực sự hoàn tất. Khi đó, cần tính cả số tác vụ đang chạy và đang chờ, hoặc dùng pipeline có concurrency và prefetch được giới hạn để cửa sổ demand phản ánh đúng năng lực xử lý.

## 7. Cấp hạn ngạch theo khả năng xử lý

Một cách chọn demand thực tế là gắn nó với số tác vụ mà client có thể xử lý đồng thời. Giả sử client cho phép tối đa 8 tác vụ đang chạy và mỗi tác vụ chiếm một slot. Khi một tác vụ hoàn tất, slot được giải phóng và client có thể cấp thêm một demand.

~~~text
Giới hạn xử lý đồng thời: 4

Ban đầu:
  demand = 4
  đang xử lý = 0

Nhận 4 phần tử:
  demand còn = 0
  đang xử lý = 4

Một tác vụ hoàn tất:
  đang xử lý = 3
  cấp thêm demand = 1

Nhận phần tử mới:
  demand còn = 0
  đang xử lý = 4
~~~

Trong mô hình này, client gia hạn sau khi xử lý xong phần tử thay vì ngay khi nhận được nó. Nhờ vậy, tổng số tác vụ đang chạy không vượt quá giới hạn dự kiến. Nếu xử lý bất đồng bộ, việc cập nhật số slot và yêu cầu thêm demand phải an toàn khi nhiều tác vụ hoàn tất gần như đồng thời.

Với Reactor, có thể dùng <code>flatMap</code> với concurrency giới hạn:

~~~java
Flux<Result> results = source
    .flatMap(this::processAsync, 4);
~~~

Tham số concurrency giới hạn số inner Publisher được subscribe đồng thời. Toán tử cũng có prefetch riêng; khi cần kiểm soát bộ nhớ chặt chẽ, hãy xem xét cả concurrency, prefetch và buffer của các nguồn upstream.

## 8. Khi nào nên dừng cấp hạn ngạch?

Không tiếp tục cấp demand trong các trường hợp:

- Stream đã nhận <code>onComplete</code>.
- Stream đã nhận <code>onError</code>.
- Client đã gọi cancel hoặc dispose subscription.
- Ứng dụng bắt đầu shutdown và không nhận công việc mới.
- Tenant hoặc người dùng bị thu hồi quyền sử dụng stream.
- Bộ nhớ, hàng đợi hoặc số tác vụ đang chạy đã chạm giới hạn vận hành.

Khi cancel, client cần giải phóng tài nguyên liên quan và truyền cancellation tới nguồn nếu có thể. Nếu stream đã kết thúc, việc gọi request thêm không thể mở lại stream cũ. Muốn nhận tiếp dữ liệu, ứng dụng phải tạo tương tác mới.

## 9. Phân biệt demand credits với quota và rate limit nghiệp vụ

Từ “hạn ngạch” thường được dùng cho nhiều loại giới hạn. Trong RSocket cần phân biệt rõ:

| Cơ chế | Đơn vị | Phạm vi | Ví dụ |
| --- | --- | --- | --- |
| Reactive demand | Số phần tử | Một Subscription hoặc một chiều stream | Cho phép nhận thêm 20 phần tử. |
| RSocket REQUEST_N | Số phần tử trên giao thức | Một stream ID | Gia hạn demand cho stream đang hoạt động. |
| Rate limit | Số thao tác trong khoảng thời gian | Người dùng, tenant, route hoặc service | Tối đa 100 request mỗi phút. |
| Concurrency limit | Số tác vụ đang chạy | Một service, tenant hoặc nhóm tài nguyên | Tối đa 8 tác vụ xử lý đồng thời. |
| Payload/queue limit | Byte hoặc số phần tử buffer | Connection, stream hoặc process | Hàng đợi tối đa 1.000 phần tử hoặc 16 MB. |

REQUEST_N không ngăn client mở hàng nghìn stream mới, cũng không giới hạn số lần gọi request-response trong một phút. Nếu cần bảo vệ hệ thống khỏi việc tạo quá nhiều stream hoặc gọi route quá nhanh, phải bổ sung quota/rate limiter ở tầng ứng dụng hoặc gateway.

Ngược lại, rate limiter không thay thế backpressure. Một client có thể tuân thủ 100 request mỗi phút nhưng vẫn mở một stream phát hàng triệu phần tử vào một Subscriber chậm. Demand và rate limit bảo vệ hai khía cạnh khác nhau.

## 10. Xử lý giới hạn, overflow và nhiều stream

Khi quản lý demand bằng bộ đếm, cần chú ý các trường hợp:

- Không gọi <code>request(0)</code> hoặc request số âm.
- Không cộng demand vượt giới hạn số học của kiểu dữ liệu.
- Không gia hạn sau khi stream kết thúc hoặc bị cancel.
- Không dùng một bộ đếm demand chung cho nhiều stream độc lập.
- Không nhầm số phần tử đã cấp với số phần tử đã nhận hoặc số tác vụ đang xử lý.
- Không coi demand là số phần tử mà server chắc chắn sẽ gửi.

Trong Reactive Streams, demand tích lũy thường được xử lý theo hướng bão hòa ở <code>Long.MAX_VALUE</code> thay vì để số học tràn thành số âm. Các thư viện tuân thủ giao thức chịu trách nhiệm xử lý phép cộng demand ở tầng Subscription. Nếu tự xây dựng bộ đếm cho cửa sổ ứng dụng, vẫn cần kiểm tra overflow và cập nhật đồng bộ.

Nếu có nhiều stream, có thể áp dụng hai lớp giới hạn:

1. Hạn ngạch theo từng stream để điều tiết số phần tử của stream đó.
2. Hạn ngạch tổng của client hoặc tenant để giới hạn tổng số phần tử và tác vụ trên tất cả stream.

Ví dụ, một client có thể có tối đa 4 stream, mỗi stream có cửa sổ 20 phần tử. Giới hạn tổng cần xét tới 80 phần tử tiềm năng cùng buffer và concurrency; nếu mỗi stream tự dùng hết cửa sổ, tổng tài nguyên phải nằm trong ngân sách của client.

## 11. Quan sát và kiểm thử hạn ngạch

Để đánh giá chính sách demand, nên quan sát các số liệu:

| Metric | Ý nghĩa |
| --- | --- |
| Initial demand | Số phần tử được cấp khi mở stream. |
| REQUEST_N count | Số lần gia hạn demand. |
| Requested elements | Tổng số phần tử đã yêu cầu. |
| Received elements | Tổng số phần tử đã nhận. |
| Outstanding demand | Demand còn lại tại một thời điểm. |
| Processing in-flight | Số phần tử đang được xử lý. |
| Buffer size | Số phần tử hoặc byte đang chờ trong buffer. |
| Cancelled streams | Số stream bị client hủy. |

Không nên gắn stream ID hoặc user ID có cardinality cao vào metric label nếu hệ thống metrics không được thiết kế cho việc đó. Có thể dùng log hoặc trace có kiểm soát để chẩn đoán một stream cụ thể.

Dùng <code>StepVerifier</code> để xác nhận Publisher không phát quá demand:

~~~java
StepVerifier.create(Flux.range(1, 5), 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenRequest(2)
    .expectNext(4, 5)
    .verifyComplete();
~~~

Một bài kiểm thử đầy đủ nên xác nhận:

- Stream không phát phần tử trước khi có demand.
- Initial request N cho phép phát đúng số lượng ban đầu.
- REQUEST_N bổ sung demand cộng dồn với demand chưa sử dụng.
- Nhiều lần gia hạn không làm demand vượt cửa sổ ứng dụng dự kiến.
- Cancel dừng việc phát dữ liệu và giải phóng nguồn.
- Complete hoặc error ngăn việc cấp thêm demand.
- Nhiều stream có bộ đếm độc lập và không tiêu thụ nhầm hạn ngạch của nhau.
- Concurrency và buffer không vượt giới hạn cấu hình khi tải tăng.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Stream dừng sau vài phần tử | Demand ban đầu đã hết và client không gửi REQUEST_N. | Kiểm tra chính sách gia hạn và trạng thái Subscription. |
| Server phát quá nhiều phần tử đang chờ | Cửa sổ demand lớn hoặc buffer/concurrency không có giới hạn. | Giảm window, đặt low-watermark và giới hạn buffer. |
| Demand tăng vượt dự kiến | Gia hạn theo cửa sổ đầy thay vì phần demand còn lại. | Tính số bổ sung bằng window trừ outstanding. |
| Client chậm dù demand còn lớn | Callback xử lý blocking hoặc downstream scheduler bị nghẽn. | Tối ưu xử lý, chuyển blocking work đúng scheduler và đo queue. |
| Hạn ngạch bị dùng chung giữa stream | Dùng chung bộ đếm hoặc Subscription. | Quản lý demand theo từng stream; thêm ngân sách tổng riêng nếu cần. |
| Vẫn có công việc sau khi cancel | Nguồn không truyền cancellation hoặc đã tách khỏi Publisher gốc. | Trả Publisher từ handler và nối cancellation tới nguồn. |
| Rate limit không ngăn buffer tăng | Nhầm rate limit với demand. | Kết hợp rate limit, backpressure, concurrency và queue limit. |

## 13. Ghi nhớ

- Demand là số phần tử Subscriber còn quyền nhận; request bổ sung được cộng dồn với demand chưa sử dụng.
- Initial request N cấp hạn ngạch ban đầu khi mở stream; REQUEST_N gia hạn demand cho stream đang chạy.
- Mỗi stream có demand riêng; request-channel có điều tiết riêng cho hai chiều dữ liệu.
- Cửa sổ demand và ngưỡng gia hạn cần dựa trên tốc độ xử lý, độ trễ, kích thước payload và số stream đồng thời.
- Gia hạn theo lô giảm frame điều khiển; gia hạn theo từng phần tử phù hợp khi cần giới hạn tác vụ đang chạy chặt chẽ.
- Cancel, complete và error là các điểm dừng cấp demand cho stream.
- Demand, rate limit, concurrency limit và queue limit là các cơ chế khác nhau; ứng dụng realtime thường cần phối hợp chúng.
