# Theo dõi số phần tử được phép phát và trường hợp nhu cầu lớn

Trong RSocket, consumer không chỉ nhận dữ liệu thụ động. Nó cấp cho phía phát một lượng **credit** biểu thị số payload mà phía phát được phép gửi trên một stream. Cơ chế này dựa trên demand của Reactive Streams và giúp producer biết khi nào cần chờ yêu cầu bổ sung thay vì liên tục đẩy dữ liệu vào một consumer chưa sẵn sàng.

Để điều tiết đúng, cần theo dõi lượng credit đã cấp, số payload đã phát và phần nhu cầu còn lại. Cũng cần hiểu trường hợp nhu cầu lớn: Reactive Streams cho phép biểu diễn nhu cầu không giới hạn bằng Long.MAX_VALUE, nhưng trường Initial Request N và REQUEST_N của RSocket chỉ có độ rộng 31 bit. Hai tầng có ngữ nghĩa liên quan nhưng không dùng cùng cách biểu diễn số lớn.

## 1. Demand là số phần tử được phép phát

Demand là số phần tử mà subscriber sẵn sàng nhận từ publisher. Với Reactive Streams, subscriber gọi Subscription.request(n) để cấp thêm nhu cầu. Giá trị n là số phần tử bổ sung, không phải tổng số phần tử từ đầu stream và cũng không phải tốc độ theo giây.

Ví dụ:

~~~java
subscription.request(3);
subscription.request(2);
~~~

Hai lần gọi trên cộng dồn thành 5 phần tử được phép phát. Nếu publisher đã phát 2 phần tử, nó còn 3 credit chưa sử dụng. Khi subscriber gọi request(4), tổng credit còn lại tăng thêm 4, thành 7.

Với request-stream RSocket, requester cấp initial request N trong frame REQUEST_STREAM. Sau đó, requester gửi frame REQUEST_N để cấp thêm credit. Responder chỉ được phát số payload nằm trong credit đã nhận.

### Demand không phải là tốc độ

request(100) cho phép publisher phát thêm tối đa 100 phần tử. Nó không có nghĩa là phát 100 phần tử mỗi giây. Producer có thể phát nhanh hết 100 credit nếu nguồn dữ liệu sẵn sàng; hoặc phát chậm hơn tùy tốc độ xử lý, lịch thực thi và nguồn dữ liệu.

Nếu cần giới hạn tốc độ theo thời gian, chẳng hạn 100 sự kiện/giây, phải dùng rate limiter hoặc cơ chế lấy mẫu/điều tiết theo thời gian. Demand kiểm soát số lượng phần tử được phép chuyển tiếp, không trực tiếp kiểm soát nhịp phát.

## 2. Theo dõi credit còn lại

Có thể mô hình hóa nhu cầu của một hướng stream bằng ba giá trị:

- **Granted:** tổng số credit đã được cấp.
- **Emitted:** số payload đã được phát để tiêu thụ credit.
- **Outstanding:** số payload còn được phép phát nhưng chưa sử dụng.

Với nhu cầu hữu hạn:

\[
Outstanding = Granted - Emitted
\]

Ví dụ, requester cấp initial request N = 4. Responder phát 3 payload thì còn 1 credit. Requester gửi REQUEST_N = 2, tổng credit được cấp là 6; sau 3 payload đã phát, còn 3 credit.

| Sự kiện | Credit được cấp thêm | Payload đã phát | Credit còn lại |
|---|---:|---:|---:|
| REQUEST_STREAM initial N = 4 | 4 | 0 | 4 |
| Responder gửi PAYLOAD | 0 | 1 | 3 |
| Responder gửi PAYLOAD | 0 | 1 | 2 |
| Responder gửi PAYLOAD | 0 | 1 | 1 |
| REQUEST_N N = 2 | 2 | 0 | 3 |
| Responder gửi PAYLOAD | 0 | 1 | 2 |

Credit là cộng dồn và không thể thu hồi sau khi đã cấp. Nếu requester cấp thêm 100 credit rồi nhận ra consumer đang chậm, nó không thể gửi một lệnh để rút lại 100 credit đã cấp. Vì vậy, nên chọn kích thước lô hợp lý và chỉ cấp thêm khi consumer có khả năng xử lý.

### Sơ đồ vòng đời credit

~~~mermaid
flowchart TD
    A[Requester cấp initial N] --> B[Responder nhận credit]
    B --> C{Còn credit không?}
    C -->|Có| D[Phát một PAYLOAD]
    D --> E[Trừ một credit]
    E --> C
    C -->|Không| F[Chờ REQUEST_N tiếp theo]
    F --> G[Requester cấp thêm N]
    G --> B
~~~

Mỗi payload phát đi tiêu thụ một credit trong hướng stream tương ứng. Khi không còn credit, responder phải đợi REQUEST_N tiếp theo trước khi phát payload khác. Các frame điều khiển như ERROR không phải là payload dữ liệu thông thường và không nên được tính như một phần tử onNext.

## 3. Quy tắc request(n) trong Reactive Streams

Reactive Streams quy định:

- n phải lớn hơn 0.
- Nhu cầu từ nhiều lần request được cộng dồn.
- Publisher không được phát nhiều onNext hơn tổng demand đã được yêu cầu.
- Subscriber có thể gọi request thêm trong khi stream đang hoạt động.
- Khi demand đã được đáp ứng hết, publisher phải chờ demand mới trước khi phát onNext tiếp theo.

Gọi request(0) hoặc request số âm là vi phạm hợp đồng. Publisher tuân thủ Reactive Streams phải báo lỗi cho subscription theo quy tắc tương ứng, thường là IllegalArgumentException.

### Cộng dồn mà không tràn số

Nếu cộng nhu cầu bằng kiểu số nguyên có giới hạn mà không kiểm tra overflow, phép cộng có thể quay vòng thành số âm. Khi đó publisher có thể tính sai credit và phát quá số lượng được phép.

Reactive Streams sử dụng Long.MAX_VALUE làm giá trị đặc biệt biểu thị nhu cầu không giới hạn. Khi phép cộng nhu cầu hữu hạn vượt giới hạn long, việc cộng dồn phải bão hòa ở Long.MAX_VALUE thay vì quay vòng.

Ví dụ minh họa bộ đếm demand ở tầng ứng dụng:

~~~java
final class DemandCounter {
    private long outstanding;

    synchronized void request(long n) {
        if (n <= 0) {
            throw new IllegalArgumentException("n must be positive");
        }

        if (outstanding == Long.MAX_VALUE) {
            return;
        }

        if (n >= Long.MAX_VALUE - outstanding) {
            outstanding = Long.MAX_VALUE;
        } else {
            outstanding += n;
        }
    }

    synchronized boolean tryConsume() {
        if (outstanding == Long.MAX_VALUE) {
            return true;
        }

        if (outstanding == 0) {
            return false;
        }

        outstanding--;
        return true;
    }
}
~~~

Đây là mô hình minh họa cách cộng dồn có kiểm tra và tiêu thụ credit. Publisher thực tế còn phải bảo đảm tuần tự hóa tín hiệu, xử lý concurrency và tuân thủ toàn bộ Reactive Streams Specification; không nên thay Subscription của thư viện bằng bộ đếm tự viết.

## 4. Nhu cầu không giới hạn và Long.MAX_VALUE

Trong Reactive Streams, subscriber có thể gọi:

~~~java
subscription.request(Long.MAX_VALUE);
~~~

Long.MAX_VALUE là giá trị đặc biệt mang nghĩa **unbounded demand**: publisher không cần tiếp tục theo dõi một giới hạn hữu hạn cho số phần tử được phát. Đây không phải lời yêu cầu phát ngay một số lượng khổng lồ trong một lần; publisher vẫn phát theo khả năng của nguồn và lịch thực thi.

Một số API tiện ích có thể yêu cầu unbounded demand khi subscribe, ví dụ các cách subscribe đơn giản không kiểm soát demand thủ công. Điều này thuận tiện cho luồng nhỏ hoặc consumer luôn sẵn sàng, nhưng làm giảm khả năng điều tiết nếu producer có thể phát nhanh.

Cần phân biệt:

- **Unbounded demand:** subscriber không đặt giới hạn số phần tử ở tầng Reactive Streams.
- **Producer phát không giới hạn ngay lập tức:** không được suy ra từ unbounded demand; tốc độ còn phụ thuộc publisher và nguồn.
- **Buffer không giới hạn:** là chính sách lưu trữ riêng, không tự động đồng nghĩa với unbounded demand.
- **Không giới hạn tài nguyên:** hoàn toàn không được bảo đảm. Payload lớn, concurrency cao và queue nội bộ vẫn có thể làm cạn bộ nhớ.

Unbounded demand tiện lợi nhưng nên được dùng có chủ đích. Với stream dài hạn hoặc producer có tốc độ cao, yêu cầu theo lô thường giúp kiểm soát backlog tốt hơn.

## 5. Giới hạn biểu diễn demand trong giao thức RSocket

Một điểm quan trọng khi chuyển từ Reactive Streams sang RSocket là cách mã hóa số lượng credit.

Trong RSocket Protocol:

- Initial Request N trong frame REQUEST_STREAM là số nguyên unsigned 31-bit.
- Request N trong frame REQUEST_N cũng là số nguyên unsigned 31-bit.
- Giá trị của hai trường này phải lớn hơn 0.
- Giá trị lớn nhất của một trường là \(2^{31}-1\), tức 2.147.483.647.

Reactive Streams có thể biểu diễn demand đến \(2^{63}-1\) và dùng Long.MAX_VALUE làm sentinel cho unbounded demand. RSocket dùng trường 4 byte cho Request N, nên không có chỗ để mã hóa sentinel 64-bit đó. Không được giả định rằng gửi Long.MAX_VALUE ở tầng ứng dụng sẽ được truyền nguyên dạng thành một REQUEST_N duy nhất.

Nếu ứng dụng hoặc adapter cần biểu diễn lượng demand lớn, implementation phải chuyển đổi sang các increment hợp lệ theo trường giao thức và quản lý credit tương ứng. Cách ánh xạ cụ thể phụ thuộc driver RSocket và phiên bản thư viện; hãy kiểm tra hành vi của implementation đang dùng thay vì dựa vào giả định rằng mọi driver xử lý unbounded demand giống nhau.

### Một REQUEST_N lớn không phải một lệnh phát tức thì

Giả sử requester gửi REQUEST_N với giá trị 10.000. Điều đó cấp quyền phát tối đa thêm 10.000 payload trong stream. Nó không yêu cầu responder phải tạo ngay 10.000 payload, cũng không bảo đảm consumer xử lý xong chúng ngay.

Tuy nhiên, responder có thể sử dụng toàn bộ credit đã cấp mà không phải chờ thêm yêu cầu. Nếu requester cấp một lượng quá lớn, khoảng đệm giữa tốc độ phát và tốc độ xử lý có thể tăng. Vì credit đã cấp không thể thu hồi, việc cấp quá nhiều làm giảm khả năng điều tiết trong khoảng thời gian đó.

## 6. Vì sao không nên cấp demand quá lớn?

Cấp một lô lớn giúp giảm số lần gửi REQUEST_N và giảm độ trễ do phải chờ cấp credit mới. Nhưng nó cũng làm producer có thể phát nhiều phần tử hơn trước khi consumer có cơ hội điều chỉnh.

| Cấp ít credit | Cấp rất nhiều credit |
|---|---|
| Kiểm soát backlog tốt hơn | Producer có thể phát burst lớn |
| Consumer có cơ hội điều chỉnh thường xuyên | Ít lần phải gửi REQUEST_N hơn |
| Có thể tăng số lần trao đổi điều khiển | Giảm overhead của các lần cấp credit |
| Có thể làm producer chờ thường xuyên | Có thể tăng queue và bộ nhớ nếu consumer chậm |

Kích thước lô nên dựa trên:

- Tốc độ xử lý ổn định của consumer.
- Số phần tử consumer có thể giữ đồng thời.
- Kích thước trung bình và kích thước tối đa của payload.
- Độ trễ mạng và chi phí gửi frame điều khiển.
- Số stream đang chia sẻ cùng kết nối.
- Mức độ quan trọng của từng phần tử và khả năng xử lý lại.

Một lô 1.000 phần tử có thể nhỏ với payload vài byte nhưng rất lớn nếu mỗi payload chứa nhiều megabyte. Demand đếm phần tử, không đếm byte. Vì thế cần giới hạn kích thước payload riêng với giới hạn số lượng.

## 7. Chọn kích thước lô bằng Reactor

Trong Reactor, operator limitRate có thể chia demand downstream thành những lô nhỏ hơn khi truyền upstream.

~~~java
Flux<Quote> quotes = requester
    .route("quotes.stream")
    .data("ACME")
    .retrieveFlux(Quote.class)
    .limitRate(64);
~~~

Ví dụ này giới hạn các đợt request upstream ở mức phù hợp với cấu hình operator. Nó giúp downstream không chuyển một yêu cầu rất lớn thành một lần cấp demand lớn duy nhất.

Có thể kết hợp với xử lý tuần tự hoặc concurrency giới hạn:

~~~java
Flux<Receipt> receipts = requester
    .route("events.stream")
    .retrieveFlux(Event.class)
    .limitRate(64)
    .concatMap(event -> receiptService.persist(event), 16);
~~~

concatMap giữ thứ tự xử lý bằng cách chờ tác vụ con hiện tại hoàn tất trước khi chuyển sang tác vụ tiếp theo. Prefetch điều khiển lượng phần tử được lấy trước để chờ. Nếu nghiệp vụ cho phép xử lý song song, có thể dùng flatMap với concurrency và prefetch được giới hạn.

limitRate không phải rate limiter theo thời gian và không trực tiếp đặt kích thước buffer cho mọi tầng. Hãy kiểm tra thêm queue do scheduler, flatMap, database client và transport tạo ra.

## 8. Theo dõi nhu cầu trong request-channel

Request-channel có dữ liệu đi theo cả hai hướng. Mỗi bên vừa có thể phát payload vừa nhận payload từ peer. Vì vậy, cần theo dõi nhu cầu độc lập cho từng hướng:

- Requester gửi REQUEST_CHANNEL với initial request N để chỉ định số response payload ban đầu nó sẵn sàng nhận.
- Responder phải cấp REQUEST_N cho requester để cho phép requester gửi các payload tiếp theo.
- Requester và responder có thể gửi REQUEST_N bổ sung khi consumer ở hướng tương ứng cần thêm dữ liệu.
- COMPLETE ở một phía kết thúc hướng gửi của phía đó; hướng kia có thể vẫn tiếp tục.

Không nên dùng một bộ đếm demand chung cho cả hai hướng. Mỗi hướng có consumer, producer và credit riêng. Khi debug, hãy ghi rõ Stream ID, peer gửi REQUEST_N, số credit cấp thêm và số payload được phát theo hướng đó.

## 9. Phân biệt request-n với LEASE

RSocket còn có cơ chế LEASE, nhưng mục đích khác với REQUEST_N:

| Cơ chế | Kiểm soát điều gì? | Phạm vi |
|---|---|---|
| REQUEST_N | Số payload mà peer được phép phát | Một hướng của một stream |
| LEASE | Số request mới mà requester được phép khởi tạo trong một khoảng thời gian | Các request trên kết nối theo lease được cấp |

REQUEST_N điều tiết các phần tử trong một tương tác đang hoạt động. LEASE điều tiết việc bắt đầu request mới theo số lượng và thời hạn. Một stream có nhiều payload không tiêu thụ một lease riêng cho từng payload; nó tiêu thụ credit theo request-n.

Hai cơ chế có thể bổ sung cho nhau: LEASE kiểm soát số tương tác mới, còn request-n kiểm soát số phần tử trong stream.

## 10. Đo lường và kiểm thử demand lớn

Để biết kích thước demand có phù hợp hay không, nên theo dõi:

- Initial Request N và các giá trị REQUEST_N được gửi.
- Tổng credit đã cấp và số payload đã phát.
- Credit còn lại hoặc số lần producer phải chờ demand mới, nếu implementation cung cấp số liệu này.
- Throughput producer/consumer và độ trễ xử lý.
- Queue depth, buffer overflow và kích thước payload.
- Số stream đồng thời và mức sử dụng bộ nhớ.
- Số lần hủy stream và lỗi do vi phạm giao thức.

Không phải mọi RSocket driver đều công khai bộ đếm outstanding credit cho ứng dụng. Nếu không có metric trực tiếp, có thể instrument ở tầng publisher hoặc thu thập trace frame trong môi trường kiểm thử.

### Kiểm thử demand theo từng lô

StepVerifier cho phép kiểm tra publisher với demand ban đầu bằng 0:

~~~java
StepVerifier.create(Flux.range(1, 5), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify();
~~~

Bài kiểm thử xác nhận publisher không phát trước khi được yêu cầu, phát hai phần tử sau request(2), rồi phát thêm một phần tử sau request(1). Đây là kiểm thử Reactive Streams ở tầng publisher; cần thêm kiểm thử tích hợp để xác nhận REQUEST_N được mã hóa và xử lý đúng qua RSocket transport.

### Các trường hợp biên nên kiểm tra

1. request(1) và nhiều lần request nhỏ được cộng dồn đúng.
2. request(0) và request số âm bị từ chối theo hợp đồng Reactive Streams.
3. Nhu cầu tăng gần Long.MAX_VALUE không làm bộ đếm bị tràn số.
4. Unbounded demand ở tầng Reactive Streams không bị giả định là một giá trị sentinel có thể mã hóa trực tiếp vào REQUEST_N.
5. Initial Request N và REQUEST_N không vượt giới hạn trường unsigned 31-bit của protocol.
6. Producer dừng phát khi hết credit và tiếp tục khi nhận REQUEST_N mới.
7. Consumer hủy stream khi vẫn còn credit chưa sử dụng.
8. Payload lớn không làm bộ nhớ tăng ngoài giới hạn dù số credit còn nhiều.

## 11. Quy trình chọn và cấp demand

Có thể áp dụng quy trình sau khi thiết kế request-stream:

1. **Đo consumer:** xác định thông lượng xử lý ổn định và số phần tử có thể giữ đồng thời.
2. **Đặt kích thước lô ban đầu:** chọn initial request N vừa đủ để producer bắt đầu làm việc.
3. **Cấp thêm theo tiến độ:** gửi REQUEST_N khi consumer xử lý gần hết lượng credit hiện tại.
4. **Giới hạn tài nguyên:** kết hợp giới hạn payload bytes, buffer, concurrency và số stream.
5. **Xử lý nhu cầu lớn:** tránh unbounded demand nếu không cần; xác minh cách driver ánh xạ demand lớn sang các trường 31-bit.
6. **Đo và điều chỉnh:** quan sát throughput, queue, latency và thời gian producer phải chờ credit.

Nếu consumer xử lý nhanh và payload nhỏ, có thể tăng kích thước lô để giảm overhead. Nếu payload lớn hoặc consumer chậm, nên giảm lô và cấp thêm theo tiến độ. Vì credit không thể thu hồi, quyết định cấp demand cần dựa trên khả năng tiêu thụ thực tế.

## 12. Kết luận

Demand biểu thị số payload consumer cho phép producer phát. Credit được cộng dồn và mỗi payload phát đi tiêu thụ một credit. Khi credit đã dùng hết, producer phải chờ REQUEST_N tiếp theo. Cơ chế này giúp kiểm soát luồng dữ liệu theo từng stream và tránh gửi vượt quá khả năng tiếp nhận đã công bố.

Khi xử lý nhu cầu lớn, cần phân biệt Reactive Streams với biểu diễn trên dây của RSocket. Reactive Streams dùng Long.MAX_VALUE làm sentinel cho unbounded demand; RSocket dùng trường unsigned 31-bit cho Initial Request N và REQUEST_N, nên không thể mã hóa sentinel đó nguyên dạng. Hãy chọn lô demand vừa đủ, theo dõi credit và backlog, đồng thời giới hạn byte, buffer và concurrency để stream realtime duy trì thông lượng mà không làm consumer quá tải.

Tài liệu tham khảo: [RSocket Protocol – Flow Control](https://rsocket.io/about/protocol/) và [RSocket FAQ – Request-N Flow Control](https://rsocket.io/about/faq/).

