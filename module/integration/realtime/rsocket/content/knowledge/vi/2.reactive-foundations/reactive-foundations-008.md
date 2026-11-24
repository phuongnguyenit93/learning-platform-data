# Quan hệ giữa nhu cầu nhận (demand), bộ đệm và tốc độ xử lý

Trong một luồng dữ liệu realtime, bên phát (producer) có thể tạo dữ liệu nhanh hơn khả năng xử lý của bên nhận (consumer). Ví dụ, dịch vụ giá phát 1.000 cập nhật mỗi giây trong khi một consumer chỉ xử lý được 700 cập nhật mỗi giây. Nếu ứng dụng cứ nhận và xếp mọi dữ liệu vào hàng đợi, hàng đợi sẽ tăng dần, độ trễ sẽ lớn hơn và bộ nhớ cuối cùng có thể cạn.

Reactive Streams giải quyết sự mất cân bằng này bằng **demand** (nhu cầu nhận): consumer chủ động cho biết nó sẵn sàng nhận bao nhiêu phần tử. **Backpressure** truyền nhu cầu đó ngược về phía nguồn phát để điều tiết việc phát dữ liệu. **Buffer** hấp thụ những chênh lệch tạm thời giữa tốc độ phát và tốc độ xử lý. Ba khái niệm liên quan chặt chẽ nhưng có vai trò khác nhau: demand quyết định lượng dữ liệu được phép chuyển tiếp, buffer giữ dữ liệu đang chờ, còn tốc độ xử lý quyết định hàng đợi tăng hay giảm theo thời gian.

Bài học này đặt các khái niệm đó trong bối cảnh Java, Reactor và RSocket, nơi một stream có thể kéo dài trong suốt phiên giao tiếp.

## 1. Demand là gì?

Demand là số phần tử mà consumer yêu cầu publisher chuyển đến. Trong Reactive Streams, subscriber gửi yêu cầu thông qua phương thức **Subscription.request(n)**, với **n** là số nguyên dương. Publisher không được phát nhiều phần tử hơn tổng nhu cầu chưa được đáp ứng.

Ví dụ, consumer yêu cầu 5 phần tử:

~~~java
subscription.request(5);
~~~

Publisher có thể phát tối đa 5 phần tử để đáp ứng yêu cầu đó. Nếu consumer xử lý xong và cần thêm dữ liệu, nó tiếp tục yêu cầu:

~~~java
subscription.request(3);
~~~

Nhu cầu có thể được cộng dồn. Nếu consumer đã yêu cầu 5 phần tử nhưng mới nhận 2, rồi yêu cầu thêm 3, publisher có thể phát tối đa 6 phần tử còn lại theo tổng nhu cầu chưa được đáp ứng. Việc yêu cầu thêm không có nghĩa consumer đã xử lý xong dữ liệu cũ; ứng dụng phải quản lý thời điểm phát sinh demand sao cho phù hợp với khả năng xử lý thực tế.

### Demand là số phần tử, không phải tốc độ theo thời gian

**request(100)** có nghĩa là yêu cầu tối đa 100 phần tử, không có nghĩa là 100 phần tử mỗi giây. Consumer có thể yêu cầu theo lô, yêu cầu từng phần tử hoặc yêu cầu một lượng lớn. Tốc độ thực tế còn phụ thuộc vào thời gian xử lý, khả năng phát của producer, lịch thực thi và các giới hạn ở những tầng khác.

Một phần tử cũng có thể rất nhỏ hoặc rất lớn. Vì thế, demand theo số lượng phần tử chưa đủ để giới hạn bộ nhớ theo byte. Nếu payload có kích thước biến động mạnh, hệ thống cần thêm giới hạn kích thước payload, giới hạn bộ nhớ hoặc chính sách xử lý dữ liệu lớn.

### Demand và backpressure

Backpressure là cơ chế truyền tín hiệu về phía upstream khi downstream cần điều tiết lượng dữ liệu. Trong Reactive Streams, demand chính là tín hiệu định lượng cho quá trình này.

~~~mermaid
flowchart LR
    P[Producer] -->|Phát tối đa theo demand| S[Pipeline / operator]
    S -->|Phần tử đã được cấp nhu cầu| C[Consumer]
    C -.->|request(n): cần thêm n phần tử| S
    S -.->|Demand được truyền upstream| P
~~~

Khi consumer xử lý chậm, nó có thể giảm hoặc tạm ngừng yêu cầu. Một publisher tuân thủ Reactive Streams sẽ không tự ý phát vượt quá nhu cầu đã nhận. Nhờ vậy, áp lực được truyền ngược qua pipeline thay vì để mọi phần tử tiếp tục dồn vào consumer.

Backpressure chỉ có tác dụng đầy đủ khi các thành phần trong đường đi hỗ trợ và tôn trọng giao thức demand. Một nguồn phát bên ngoài không thể tạm dừng, chẳng hạn cảm biến hoặc callback từ thư viện không reactive, có thể cần một hàng đợi biên, cơ chế lấy mẫu hoặc chính sách loại bỏ dữ liệu.

## 2. Buffer giữ vai trò gì?

Buffer là vùng lưu tạm các phần tử đã được nhận nhưng chưa được xử lý hoặc chuyển tiếp. Nó giúp pipeline chịu được những đợt tăng tải ngắn, chênh lệch tốc độ do lịch thực thi hoặc thời gian chờ I/O.

Ví dụ, consumer thường xử lý 800 sự kiện mỗi giây. Trong vài giây, producer tăng lên 1.000 sự kiện mỗi giây. Một buffer hữu hạn có thể giữ phần sự kiện dư trong thời gian consumer bắt kịp.

Buffer không làm tăng năng lực xử lý bền vững của consumer. Nếu producer liên tục phát nhanh hơn consumer, hàng đợi sẽ tiếp tục tăng cho đến khi đầy. Buffer lớn hơn chỉ kéo dài thời gian trước khi đầy và có thể làm tăng độ trễ.

### Buffer hữu hạn và buffer không giới hạn

| Loại buffer | Đặc điểm | Hệ quả |
|---|---|---|
| Hữu hạn (bounded) | Có sức chứa tối đa | Bộ nhớ có giới hạn; cần chính sách khi đầy |
| Không giới hạn (unbounded) | Tiếp tục giữ phần tử khi chưa xử lý | Có thể tăng bộ nhớ không kiểm soát nếu consumer chậm kéo dài |

Trong hệ thống production, buffer hữu hạn thường dễ vận hành hơn vì có giới hạn tài nguyên rõ ràng. Khi buffer đầy, ứng dụng phải chọn hành vi phù hợp với ý nghĩa dữ liệu:

- **Báo lỗi:** dừng luồng hoặc báo overload để hệ thống xử lý sự cố rõ ràng.
- **Loại phần tử mới:** giữ dữ liệu cũ, bỏ dữ liệu đến sau khi hàng đợi đã đầy.
- **Loại phần tử cũ:** bỏ dữ liệu chờ lâu nhất để giữ dữ liệu mới hơn.
- **Chỉ giữ phần tử mới nhất:** phù hợp với trạng thái hiện tại, nơi dữ liệu trung gian không còn giá trị.
- **Chặn hoặc giảm tốc nguồn phát:** chỉ khả thi khi nguồn phát có thể tôn trọng backpressure hoặc có cơ chế điều khiển tương đương.

Chính sách bỏ dữ liệu chỉ phù hợp khi nghiệp vụ cho phép. Với sự kiện kế toán, lệnh giao dịch hoặc audit log, việc bỏ một phần tử có thể làm sai trạng thái hệ thống. Với màn hình hiển thị giá hiện tại, giữ giá mới nhất có thể hợp lý hơn việc hiển thị một chuỗi giá cũ đang chờ.

## 3. Quan hệ giữa tốc độ phát, tốc độ xử lý và kích thước buffer

Gọi:

- \(\lambda\): tốc độ producer phát dữ liệu, tính bằng phần tử/giây.
- \(\mu\): tốc độ consumer xử lý dữ liệu, tính bằng phần tử/giây.
- \(Q(t)\): số phần tử đang chờ trong buffer tại thời điểm \(t\).
- \(B\): sức chứa tối đa của buffer, tính bằng phần tử.

Trong một khoảng thời gian ngắn \(\Delta t\), nếu tốc độ gần như ổn định và chưa có phần tử bị loại bỏ, lượng dữ liệu chờ thay đổi xấp xỉ:

\[
Q(t+\Delta t) = \max(0,\ Q(t) + (\lambda-\mu)\Delta t)
\]

Từ quan hệ này có ba trường hợp:

1. **\(\lambda < \mu\):** consumer xử lý nhanh hơn producer. Buffer có xu hướng giảm hoặc trở về rỗng.
2. **\(\lambda = \mu\):** hai bên cân bằng ở mức trung bình. Buffer vẫn cần thiết để hấp thụ dao động và burst ngắn.
3. **\(\lambda > \mu\):** producer phát nhanh hơn consumer. Buffer tăng theo thời gian nếu không có backpressure hiệu quả, giới hạn tốc độ hoặc loại bỏ dữ liệu.

### Ví dụ tính thời gian buffer đầy

Giả sử producer phát 1.000 sự kiện/giây, consumer xử lý 800 sự kiện/giây và buffer có sức chứa 2.000 sự kiện. Nếu buffer bắt đầu rỗng và hai tốc độ giữ ổn định, lượng tồn tăng:

\[
1000 - 800 = 200 \text{ sự kiện/giây}
\]

Thời gian để buffer đầy xấp xỉ:

\[
t = \frac{B}{\lambda-\mu}
  = \frac{2000}{200}
  = 10 \text{ giây}
\]

| Thời gian | Số sự kiện đang chờ |
|---:|---:|
| 0 giây | 0 |
| 2 giây | 400 |
| 4 giây | 800 |
| 6 giây | 1.200 |
| 8 giây | 1.600 |
| 10 giây | 2.000 (đầy) |

Đây là mô hình đơn giản để ước lượng. Hệ thống thực tế có burst, độ trễ mạng, thời gian xử lý không đồng đều, kích thước phần tử khác nhau và các buffer ở nhiều tầng. Vì vậy, không nên lấy một phép tính trung bình làm giới hạn an toàn duy nhất.

### Buffer ảnh hưởng đến độ trễ

Khi có nhiều phần tử đang chờ, dữ liệu mới có thể phải đợi lâu hơn trước khi được xử lý. Trong điều kiện ổn định, định luật Little thường được dùng để liên hệ số phần tử trung bình trong hệ thống, thông lượng và thời gian chờ:

\[
L = \lambda W
\]

Trong đó \(L\) là số phần tử trung bình đang ở trong hệ thống, \(\lambda\) là thông lượng trung bình và \(W\) là thời gian trung bình một phần tử ở trong hệ thống. Khi thông lượng không đổi, số phần tử tồn đọng càng lớn thì thời gian chờ trung bình càng cao.

Vì vậy, chọn buffer lớn chỉ để tránh lỗi tràn có thể khiến ứng dụng tiếp tục hoạt động nhưng dữ liệu đã quá cũ. Với realtime, độ trễ thường quan trọng không kém thông lượng.

## 4. RSocket dùng demand để điều tiết stream như thế nào?

RSocket định nghĩa cơ chế flow control cho các tương tác dạng stream. Khi khởi tạo **REQUEST_STREAM**, requester gửi kèm lượng response ban đầu mà nó sẵn sàng nhận. Khi cần thêm dữ liệu, requester gửi frame **REQUEST_N** với số phần tử bổ sung.

Trong **REQUEST_CHANNEL**, hai phía có thể gửi stream dữ liệu. Nhu cầu cho hướng dữ liệu nhận và hướng dữ liệu gửi được quản lý theo từng hướng, cho phép mỗi bên điều tiết lượng phần tử mà bên kia gửi đến.

~~~mermaid
sequenceDiagram
    participant C as Requester / Consumer
    participant S as RSocket Responder / Producer
    C->>S: REQUEST_STREAM (initial request N = 3)
    S-->>C: Payload 1
    S-->>C: Payload 2
    S-->>C: Payload 3
    Note over C: Consumer xử lý dữ liệu
    C->>S: REQUEST_N (N = 2)
    S-->>C: Payload 4
    S-->>C: Payload 5
    C->>S: CANCEL
~~~

Frame **REQUEST_N** biểu đạt số payload bổ sung được phép gửi trên stream. Đây là demand ở cấp giao thức RSocket. Khi ứng dụng dùng Spring Boot và Reactor, lập trình viên thường làm việc với **Flux** và **Mono**; thư viện tích hợp đảm nhiệm việc ánh xạ nhu cầu của subscriber xuống cơ chế flow control của phiên RSocket.

Cần phân biệt các kiểu tương tác:

- **Request-stream:** có một request ban đầu và nhiều response; demand kiểm soát số response được phát.
- **Request-channel:** cả hai phía có thể gửi chuỗi payload; mỗi hướng cần tôn trọng nhu cầu nhận của phía bên kia.
- **Request-response:** chỉ có một response nên không cần chuỗi demand như stream.
- **Fire-and-forget:** không có response stream để requester điều tiết bằng **REQUEST_N**; ứng dụng vẫn phải kiểm soát tốc độ gửi và năng lực tiếp nhận theo cách phù hợp.

Flow control ở RSocket không tự đặt ra giới hạn bộ nhớ cho toàn bộ ứng dụng. Pipeline vẫn có thể tạo queue do scheduler, operator, client SDK hoặc tầng xử lý nghiệp vụ. Cần kiểm tra cả các vùng đệm đó thay vì chỉ nhìn vào demand ở giao thức.

## 5. Điều khiển demand và buffer trong Reactor

Reactor cung cấp các operator để điều tiết request, chuyển luồng thực thi và xác định cách xử lý khi downstream không theo kịp.

### Giới hạn lô request với limitRate

**limitRate(n)** chia các request lớn từ downstream thành những lô nhỏ hơn khi truyền về upstream. Ví dụ:

~~~java
Flux<Quote> quotes = quoteService.stream("ACME")
    .limitRate(128);
~~~

Operator này hữu ích khi muốn kiểm soát kích thước các đợt request được truyền upstream. Nó **không phải bộ giới hạn tốc độ theo giây**. Nếu cần tối đa 100 sự kiện mỗi giây, phải dùng cơ chế điều tiết theo thời gian hoặc ở nguồn phát; **limitRate(100)** chỉ nói về lượng phần tử trong các lô demand.

### Xử lý tuần tự để giới hạn công việc đang chạy

~~~java
Flux<Receipt> receipts = incomingEvents
    .limitRate(64)
    .concatMap(this::persistAsync, 32);
~~~

**concatMap** đăng ký và chờ từng tác vụ con hoàn tất rồi mới xử lý tác vụ tiếp theo. Tham số prefetch giúp xác định số phần tử được lấy trước để chờ xử lý. Cách này phù hợp khi cần giữ thứ tự và giới hạn số thao tác nghiệp vụ đang thực hiện đồng thời.

Nếu nghiệp vụ cho phép xử lý song song, có thể dùng **flatMap** với giới hạn concurrency phù hợp. Cần tính đến tổng số tác vụ đồng thời, lượng dữ liệu mỗi tác vụ giữ trong bộ nhớ và khả năng chịu tải của hệ thống đích.

### Chọn chính sách khi consumer không theo kịp

Khi nguồn phát không thể tạm dừng hoặc ứng dụng muốn chủ động hấp thụ burst, có thể đặt một chính sách backpressure ở ranh giới phù hợp.

Giới hạn buffer và báo lỗi khi đầy:

~~~java
Flux<Quote> bounded = quoteSource
    .onBackpressureBuffer(1_000);
~~~

Trong trường hợp buffer vượt giới hạn, luồng phát tín hiệu lỗi overflow. Ứng dụng cần xử lý lỗi và quyết định có retry, từ chối tải, chuyển dữ liệu sang hệ thống khác hay kết thúc phiên.

Với dữ liệu trạng thái mà chỉ giá trị mới nhất quan trọng:

~~~java
Flux<Quote> latest = quoteSource
    .onBackpressureLatest();
~~~

Operator này giữ giá trị mới nhất trong lúc downstream chưa yêu cầu thêm; những giá trị trung gian có thể bị bỏ. Đây là lựa chọn có chủ đích cho UI hoặc snapshot trạng thái, không phù hợp với luồng sự kiện mà mọi phần tử đều phải được xử lý.

Các operator **onBackpressureBuffer**, **onBackpressureDrop** và **onBackpressureLatest** có thể yêu cầu upstream phát không giới hạn rồi xử lý phần tử ở ranh giới operator. Do đó, chúng thay đổi nơi áp lực được hấp thụ và có thể chuyển rủi ro sang buffer hoặc chính sách loại bỏ. Nếu nguồn phát có thể tuân thủ demand, ưu tiên để backpressure truyền ngược thay vì thêm một hàng đợi không giới hạn.

## 6. Những buffer ẩn trong pipeline

Buffer không chỉ xuất hiện khi gọi **onBackpressureBuffer**. Một pipeline reactive có thể chứa nhiều hàng đợi do operator và ranh giới bất đồng bộ tạo ra:

- **publishOn** có hàng đợi để chuyển việc xử lý sang scheduler khác; tham số prefetch ảnh hưởng số phần tử được lấy trước.
- **flatMap** có thể giữ nhiều inner publisher và kết quả đang chờ; concurrency và prefetch ảnh hưởng lượng công việc cùng tồn tại.
- **buffer**, **window** và các operator gom nhóm giữ phần tử cho đến khi đủ kích thước hoặc hết thời gian.
- Client RSocket, transport, socket và tầng mạng có thể có buffer riêng.
- Hàng đợi của executor, database client hoặc message adapter cũng giữ công việc chưa hoàn tất.

Ví dụ, nếu mỗi request đang giữ một payload trung bình 32 KB và có 1.000 payload chờ, riêng dữ liệu payload đã chiếm khoảng 32 MB, chưa tính object overhead, tham chiếu, queue node và bản sao ở các tầng khác. Vì vậy, giới hạn số phần tử nên được kết hợp với đo lường bộ nhớ thực tế.

Khi thiết kế, hãy vẽ đường đi của dữ liệu từ nguồn đến nơi xử lý, đánh dấu các operator bất đồng bộ và các queue. Tổng dung lượng chờ của cả pipeline mới là con số cần quan tâm.

## 7. Cách chọn chính sách theo loại dữ liệu

| Loại dữ liệu | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Giá hiện tại, trạng thái thiết bị | Latest hoặc sample | Giá trị mới có thể thay thế giá trị cũ |
| Sự kiện audit, giao dịch | Backpressure hoặc lưu bền vững; không tự ý drop | Mỗi sự kiện có ý nghĩa nghiệp vụ |
| Telemetry tần suất cao | Batch, window, sample hoặc drop có kiểm soát | Có thể tổng hợp hoặc giảm độ phân giải |
| Lệnh điều khiển | Giới hạn tốc độ, xác nhận và xử lý idempotent | Không nên âm thầm mất lệnh hoặc thực thi trùng |
| Cập nhật UI | Latest, debounce hoặc sample | UI thường chỉ cần trạng thái gần nhất |

Không có một operator phù hợp cho mọi loại dữ liệu. Cần xác định trước liệu phần tử có thể bị bỏ, có cần giữ thứ tự, có được phép xử lý trùng hay không và thời gian chờ tối đa mà nghiệp vụ chấp nhận.

## 8. Đo lường và kiểm thử

Để biết demand và buffer có được cấu hình phù hợp hay không, cần theo dõi ít nhất:

- Tốc độ nhận vào và tốc độ xử lý thành công (phần tử/giây).
- Số phần tử đang chờ, dung lượng buffer và thời gian chờ.
- Số lần buffer overflow, số phần tử bị drop và nguyên nhân.
- Số tác vụ đồng thời, thời gian xử lý từng tác vụ và tỷ lệ lỗi.
- Độ trễ đầu-cuối, đặc biệt là p95/p99.
- Số stream RSocket đang hoạt động, số lần reconnect và số lần hủy stream.

Một bài kiểm thử demand có thể xác nhận publisher không phát dữ liệu trước khi subscriber yêu cầu:

~~~java
StepVerifier.create(quoteService.stream("ACME"), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(firstQuote, secondQuote)
    .thenRequest(1)
    .expectNext(thirdQuote)
    .thenCancel()
    .verify();
~~~

**StepVerifier** bắt đầu với demand bằng 0, sau đó yêu cầu 2 phần tử và tiếp tục yêu cầu thêm 1 phần tử. Bài kiểm thử giúp xác nhận hành vi theo nhu cầu và khả năng hủy stream. Với hệ thống RSocket thực tế, nên bổ sung kiểm thử tích hợp để quan sát việc flow control được duy trì qua transport và khi consumer xử lý chậm.

Một thử nghiệm tải hữu ích là tạo producer có tốc độ cao hơn consumer trong một khoảng thời gian xác định. Quan sát queue tăng ra sao, chính sách overflow có được thực thi, độ trễ thay đổi thế nào và hệ thống có phục hồi khi tốc độ producer giảm xuống hay không.

## 9. Quy trình chọn demand và buffer

Khi thiết kế một luồng realtime, có thể đi theo trình tự sau:

1. **Xác định ngữ nghĩa dữ liệu:** phần tử nào bắt buộc xử lý, phần tử nào có thể gộp hoặc bỏ.
2. **Đo năng lực consumer:** đo tốc độ xử lý ổn định, thời gian xử lý p95/p99 và số tác vụ có thể chạy đồng thời.
3. **Đặt giới hạn demand:** yêu cầu theo lô phù hợp với năng lực xử lý và bộ nhớ của consumer.
4. **Chọn buffer hữu hạn:** dùng buffer để hấp thụ burst ngắn, tính cả kích thước byte chứ không chỉ số phần tử.
5. **Quy định hành vi khi đầy:** backpressure, báo lỗi, drop, latest hoặc chuyển tải sang hệ thống lưu bền vững tùy nghiệp vụ.
6. **Đo và điều chỉnh:** theo dõi queue, latency, throughput và overflow dưới tải thực tế.

Một lỗi thường gặp là tăng buffer mỗi khi thấy overflow. Cách đó có thể trì hoãn sự cố trong khi độ trễ và lượng bộ nhớ tăng lên. Trước khi tăng sức chứa, hãy kiểm tra tốc độ xử lý có thấp hơn tốc độ phát trong thời gian dài hay không, consumer có bị nghẽn I/O hay không và có thể truyền demand ngược về nguồn phát hay không.

## 10. Kết luận

Demand cho biết consumer sẵn sàng nhận bao nhiêu phần tử; backpressure truyền tín hiệu đó về upstream; buffer giữ dữ liệu chờ xử lý trong những khoảng chênh lệch tạm thời. Tốc độ producer và consumer quyết định buffer sẽ giảm, ổn định hay tăng đến giới hạn.

Trong ứng dụng Java với Reactor và RSocket, cần phối hợp demand ở cấp Reactive Streams, flow control của RSocket, prefetch/concurrency của operator và giới hạn các hàng đợi trong pipeline. Hãy chọn chính sách buffer theo ý nghĩa dữ liệu, đo độ trễ cùng thông lượng và kiểm thử tình huống consumer chậm. Một hệ thống realtime ổn định cần kiểm soát được lượng công việc đang chờ, không chỉ tốc độ dữ liệu được phát ra.

