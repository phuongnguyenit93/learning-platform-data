# Bất đồng bộ

## Độ trễ, thông lượng và khả năng đáp ứng dưới tải

Trong mô-đun **REACTIVE_PROGRAMMING**, ta xây dựng tư duy reactive quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; ta thực hành với `Mono`, `Flux`, các toán tử kết hợp, scheduler, xử lý lỗi và kiểm thử pipeline. Để thiết kế những pipeline này chạy ổn định, cần hiểu hệ thống phản ứng thế nào khi số sự kiện đến tăng lên. Ba khái niệm cần theo dõi là **độ trễ (latency)**, **thông lượng (throughput)** và **khả năng đáp ứng (responsiveness)**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt độ trễ, thông lượng và khả năng đáp ứng khi tải thay đổi.
- Đọc các phân vị p50, p95, p99 và nhận ra hiện tượng độ trễ đuôi tăng.
- Dùng định luật Little để liên hệ số yêu cầu đang xử lý, thông lượng và thời gian phản hồi.
- Giải thích vì sao hàng đợi tăng làm hệ thống chậm dần, dù từng thao tác xử lý không thay đổi.
- Chọn cách giới hạn đồng thời, điều tiết nhu cầu và xử lý quá tải trong pipeline Reactor.
- Thiết kế phép thử tải và đọc các chỉ số đủ để tìm nút thắt.

## 1. Ba đại lượng mô tả hiệu năng

Ba đại lượng có liên hệ với nhau nhưng trả lời những câu hỏi khác nhau.

| Đại lượng | Câu hỏi | Cách đo thường gặp |
|---|---|---|
| Độ trễ | Một yêu cầu hoặc sự kiện mất bao lâu để có kết quả? | mili giây, giây; p50, p95, p99 |
| Thông lượng | Hệ thống hoàn thành được bao nhiêu công việc trong một đơn vị thời gian? | yêu cầu/giây, sự kiện/giây, bản ghi/giây |
| Khả năng đáp ứng | Hệ thống có tiếp tục phản hồi trong giới hạn thời gian và lỗi đã đặt ra khi tải thay đổi không? | SLO độ trễ, tỷ lệ thành công, timeout, tỷ lệ từ chối |

### Độ trễ

Độ trễ là khoảng thời gian từ một mốc bắt đầu đã xác định đến khi hệ thống tạo ra kết quả tương ứng. Với một API, ta thường đo từ lúc nhận yêu cầu tại biên dịch vụ đến lúc gửi xong phản hồi. Với một pipeline sự kiện, có thể đo từ lúc sự kiện được nhận đến lúc kết quả xử lý được phát ra hoặc xác nhận lưu thành công.

Độ trễ đầu cuối thường gồm nhiều phần:

- Thời gian chờ trong hàng đợi trước khi được xử lý.
- Thời gian thực thi logic ứng dụng.
- Thời gian chờ I/O, kết nối hoặc phản hồi từ dịch vụ phụ thuộc.
- Thời gian truyền dữ liệu và các bước chuyển tiếp giữa scheduler.

Cần chọn cùng một ranh giới đo khi so sánh các lần chạy. Nếu lần đo này bắt đầu ở gateway còn lần đo kia bắt đầu bên trong service, kết quả không thể so sánh trực tiếp.

Không nên chỉ xem độ trễ trung bình. Ví dụ, p95 = 250 ms có nghĩa là 95% mẫu có độ trễ không vượt quá 250 ms; 5% mẫu còn lại chậm hơn. p99 giúp nhìn thấy nhóm yêu cầu chậm nhất. Một hệ thống có trung bình 80 ms nhưng p99 lên tới 3 giây vẫn có thể gây trải nghiệm kém cho một phần người dùng.

- **p50 (median):** mô tả yêu cầu ở giữa phân bố.
- **p95:** cho thấy mức chậm mà khoảng 5% yêu cầu tệ hơn phải chịu.
- **p99:** nhạy với các đợt chậm hiếm gặp, thường hữu ích khi theo dõi tail latency.

Các phân vị cần được tính từ histogram hoặc tập mẫu đủ lớn trong một cửa sổ thời gian phù hợp. Không nên lấy trung bình của các p95 theo từng máy để suy ra p95 toàn hệ thống.

### Thông lượng

Thông lượng là số đơn vị công việc hoàn tất trong một khoảng thời gian. Với API, đơn vị có thể là phản hồi thành công mỗi giây; với consumer, có thể là sự kiện được xử lý và xác nhận mỗi giây.

Cần phân biệt:

- **Offered load:** tốc độ nguồn gửi công việc đến.
- **Accepted load:** tốc độ hệ thống chấp nhận công việc.
- **Completed throughput:** tốc độ công việc hoàn tất.
- **Successful throughput:** tốc độ công việc hoàn tất thành công.

Khi hệ thống còn dư năng lực, thông lượng hoàn tất thường tăng theo tải đầu vào. Khi một tài nguyên đạt giới hạn, thông lượng có thể chững lại dù offered load tiếp tục tăng. Phần chênh lệch khi đó thường tích tụ thành hàng đợi, timeout hoặc lỗi từ chối.

### Khả năng đáp ứng

Khả năng đáp ứng thể hiện việc hệ thống có thể tiếp nhận, xử lý và phản hồi trong giới hạn thời gian đã cam kết hay không. Nó không chỉ là tốc độ tối đa. Một dịch vụ có thể đạt thông lượng cao nhưng vẫn thiếu khả năng đáp ứng nếu nhiều yêu cầu phải đợi quá lâu hoặc thường xuyên timeout.

Một SLO minh họa có thể là: 99% yêu cầu đọc hoàn tất trong 500 ms trong cửa sổ 10 phút, đồng thời tỷ lệ lỗi dưới một ngưỡng đã chọn. Giá trị thực tế phải dựa trên nhu cầu sản phẩm và đặc tính nghiệp vụ.

## 2. Điều gì xảy ra khi tải tăng?

Một yêu cầu thường đi qua nhiều thành phần: bộ nhận dữ liệu, hàng đợi, worker, scheduler, connection pool và dịch vụ phụ thuộc. Mỗi thành phần có năng lực hữu hạn. Nút thắt có thể là CPU, bộ nhớ, số kết nối, giới hạn của dịch vụ bên ngoài, khóa tranh chấp hoặc một scheduler bị chiếm bởi tác vụ blocking.

Khi tải còn thấp, phần lớn yêu cầu được xử lý ngay nên hàng đợi ngắn. Khi tốc độ đến gần năng lực xử lý, thời gian chờ bắt đầu tăng nhanh. Sau khi nút thắt bão hòa, thêm yêu cầu thường làm hàng đợi dài hơn thay vì làm hệ thống hoàn thành nhiều việc hơn.

Ví dụ, một consumer xử lý ổn định khoảng 200 sự kiện mỗi giây. Nếu nguồn gửi 150 sự kiện mỗi giây, consumer có thể theo kịp. Nếu nguồn tăng lên 300 sự kiện mỗi giây trong khi năng lực xử lý vẫn là 200, khoảng 100 sự kiện mỗi giây sẽ tích tụ hoặc phải bị từ chối. Nếu hàng đợi chứa tối đa 1.000 sự kiện, hàng đợi có thể đầy sau khoảng 10 giây trong điều kiện đơn giản này. Khi đó hệ thống cần một chính sách rõ ràng: giảm tốc nguồn, từ chối sớm, bỏ sự kiện theo quy tắc nghiệp vụ, hoặc chuyển phần việc sang một cơ chế lưu trữ bền vững.

Hàng đợi không làm tăng năng lực xử lý. Nó chỉ hấp thụ chênh lệch tạm thời giữa tốc độ đến và tốc độ xử lý. Hàng đợi không giới hạn có thể khiến heap tăng, thời gian GC kéo dài và độ trễ tăng đến mức yêu cầu hết hạn trước khi được xử lý.

## 3. Định luật Little: liên hệ tải đang xử lý và độ trễ

Trong một hệ thống ổn định, định luật Little mô tả quan hệ:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\) là số lượng công việc trung bình đang ở trong hệ thống, bao gồm công việc đang xử lý và đang chờ.
- \(\lambda\) là thông lượng trung bình, tính bằng công việc mỗi giây.
- \(W\) là thời gian trung bình một công việc ở trong hệ thống, tính bằng giây.

Ví dụ, một dịch vụ hoàn tất trung bình 200 yêu cầu mỗi giây và mỗi yêu cầu mất trung bình 0,25 giây từ lúc vào đến lúc ra:

\[
L = 200 \times 0{,}25 = 50
\]

Như vậy, trung bình có khoảng 50 yêu cầu đang nằm trong hệ thống. Nếu cùng thông lượng 200 yêu cầu/giây nhưng thời gian trong hệ thống tăng lên 2 giây, số yêu cầu đang tồn tại trung bình tăng thành 400.

Đây là lý do độ trễ tăng có thể kéo theo nhiều yêu cầu đồng thời hơn, tiêu thụ thêm bộ nhớ và kết nối, rồi làm độ trễ tăng tiếp. Vòng lặp này có thể dẫn đến quá tải dây chuyền.

Định luật Little áp dụng cho hệ thống ổn định và các đại lượng phải dùng cùng một ranh giới đo. Khi hàng đợi đang tăng liên tục vì đầu vào vượt năng lực, hệ thống chưa ở trạng thái ổn định; không nên dùng công thức này để khẳng định năng lực tối đa.

## 4. Backpressure giúp pipeline reactive đối phó với tải

Trong Reactive Streams, Subscriber thể hiện nhu cầu bằng `request(n)`. Publisher chỉ phát tối đa số phần tử đã được yêu cầu theo hợp đồng. Nhu cầu đi ngược chiều dữ liệu, giúp áp lực từ phía tiêu thụ có thể truyền về phía phát dữ liệu.

~~~mermaid
flowchart LR
    P[Publisher] --> O[Toán tử trong pipeline]
    O --> S[Subscriber]
    S -. request(n) .-> O
    O -. request(n) .-> P
~~~

Backpressure giúp các thành phần phối hợp theo nhu cầu thực tế, nhưng không tự tạo thêm năng lực CPU, I/O hay kết nối. Nó cũng không thể tự điều khiển một nguồn nóng (hot source) vốn không thể tạm dừng. Với loại nguồn này, adapter phải chọn chính sách cụ thể như buffer có giới hạn, bỏ phần tử cũ/mới, giữ phần tử mới nhất hoặc báo lỗi khi tràn.

Một số toán tử Reactor có vai trò khác nhau:

- `limitRate(n)` chia nhỏ các yêu cầu upstream thành những đợt có kích thước được kiểm soát. Nó điều tiết nhu cầu theo lô, không phải bộ giới hạn số yêu cầu mỗi giây.
- `flatMap(mapper, concurrency)` giới hạn số Publisher con được subscribe đồng thời. Đây là cách kiểm soát số thao tác bất đồng bộ đang chạy cùng lúc.
- `concatMap(mapper)` xử lý Publisher con tuần tự, giữ thứ tự nhưng có thể giảm thông lượng nếu mỗi thao tác chờ I/O lâu.
- `flatMapSequential(mapper, concurrency)` cho phép xử lý đồng thời nhưng phát kết quả theo thứ tự nguồn; kết quả hoàn tất sớm có thể phải chờ kết quả trước đó.
- Buffer cần có giới hạn và chính sách khi đầy. Buffer không giới hạn chỉ trì hoãn thời điểm quá tải xuất hiện.

### Giới hạn đồng thời cho lời gọi bất đồng bộ

Giả sử mỗi sự kiện cần gọi một dịch vụ từ xa và hàm `remoteClient.call(event)` trả về `Mono<Result>`. Ta có thể giới hạn số lời gọi đang hoạt động:

~~~java
Flux<Result> results = incomingEvents
    .flatMap(event ->
        remoteClient.call(event)
            .timeout(Duration.ofSeconds(2)),
        32
    )
    .doOnNext(metrics::recordSuccess)
    .doOnError(metrics::recordFailure);
~~~

Trong ví dụ, `flatMap` cho phép tối đa 32 Publisher con hoạt động đồng thời. Timeout đặt giới hạn thời gian chờ cho từng lời gọi. Pipeline được trả về để thành phần gọi quyết định cách subscribe hoặc ghép tiếp với luồng xử lý.

Con số 32 chỉ là giá trị minh họa. Nếu đặt quá thấp, tài nguyên có thể bị bỏ phí và thông lượng giảm. Nếu đặt quá cao, ứng dụng có thể tạo quá nhiều kết nối đồng thời, gây áp lực lên dịch vụ phụ thuộc hoặc làm tăng số yêu cầu đang chờ. Hãy chọn giới hạn dựa trên thử nghiệm tải, giới hạn connection pool và năng lực của hệ thống phía sau.

Nếu cần điều tiết tốc độ theo yêu cầu mỗi giây, hãy dùng cơ chế rate limiting phù hợp ở ranh giới tiếp nhận. `limitRate` điều khiển lượng demand theo đợt, còn `flatMap` với concurrency giới hạn số tác vụ đồng thời; hai cơ chế này không thay thế nhau.

### Scheduler và tác động của tác vụ blocking

Một pipeline reactive có thể bị chậm dù dùng API bất đồng bộ nếu một đoạn xử lý blocking chiếm thread cần thiết cho các tín hiệu khác. Tác vụ blocking nên được cô lập trên scheduler phù hợp, thường là `Schedulers.boundedElastic()`, đồng thời cần đặt giới hạn tài nguyên và timeout cho I/O. Không nên chuyển mọi đoạn xử lý sang scheduler khác theo thói quen: chuyển thread có chi phí và không làm một dịch vụ phụ thuộc chậm trở nên nhanh hơn.

## 5. Nhận biết và xử lý quá tải

Khi độ trễ tăng, hãy kiểm tra cả hàng đợi và tài nguyên thay vì chỉ tăng số thread hoặc concurrency. Một số tín hiệu hữu ích:

| Nhóm | Chỉ số cần quan sát | Dấu hiệu cần điều tra |
|---|---|---|
| Lưu lượng | offered, accepted và completed requests/s | Đầu vào tăng nhưng hoàn tất không tăng |
| Độ trễ | p50, p95, p99; thời gian chờ hàng đợi | p95/p99 tăng nhanh hơn p50 |
| Đồng thời | số yêu cầu in-flight, số inner subscription | Công việc đang tồn tại tăng liên tục |
| Hàng đợi | queue depth, tuổi phần tử cũ nhất | Hàng đợi tăng hoặc phần tử chờ quá hạn |
| Tài nguyên | CPU, heap, GC, thread, connection pool | Một tài nguyên chạm giới hạn |
| Chất lượng | tỷ lệ lỗi, timeout, retry, dropped event | Retry hoặc timeout tăng cùng lúc với tải |

Một số biện pháp thường phối hợp với nhau:

1. **Đặt giới hạn cho công việc đang chờ và đang chạy.** Giới hạn concurrency, buffer và connection pool để hệ thống không nhận nhiều việc hơn khả năng kiểm soát.
2. **Áp dụng timeout theo ngân sách thời gian.** Một yêu cầu không nên chờ lâu hơn thời hạn nghiệp vụ. Cần tính cả thời gian chờ hàng đợi và thời gian gọi dịch vụ phụ thuộc.
3. **Từ chối hoặc giảm tải sớm.** Khi đã chạm ngưỡng, phản hồi quá tải có kiểm soát thường tốt hơn việc giữ yêu cầu trong hàng đợi đến khi tất cả cùng timeout.
4. **Dùng bulkhead và circuit breaker khi phù hợp.** Cô lập một dịch vụ phụ thuộc đang chậm để nó không chiếm hết tài nguyên của các luồng khác.
5. **Giới hạn retry.** Retry có thể hữu ích với lỗi tạm thời, nhưng retry dồn dập khi hệ thống đang quá tải sẽ nhân số lời gọi và làm sự cố nặng hơn. Dùng backoff, jitter và ngân sách retry.
6. **Đặt chính sách cho sự kiện không thể phát chậm lại.** Chọn lưu bền vững, bỏ theo quy tắc nghiệp vụ, hoặc báo lỗi khi buffer đầy; ghi nhận số sự kiện bị bỏ hay từ chối.

Không có một con số concurrency tối ưu cho mọi môi trường. Mức phù hợp phụ thuộc thời gian I/O, kích thước dữ liệu, số kết nối, năng lực dịch vụ phụ thuộc và mục tiêu độ trễ.

## 6. Kiểm thử hiệu năng dưới tải

Một phép thử có ích phải tái tạo gần đúng cách hệ thống nhận và xử lý công việc trong thực tế. Hãy dùng dữ liệu, kích thước payload, tỷ lệ cache hit, thời gian phản hồi của dịch vụ phụ thuộc và cấu hình connection pool tương tự môi trường dự kiến.

Các kiểu thử nghiệm thường dùng:

- **Smoke test:** gửi tải nhỏ để xác nhận pipeline hoạt động và số liệu được ghi nhận đúng.
- **Ramp-up test:** tăng dần tốc độ gửi để quan sát điểm độ trễ bắt đầu tăng nhanh và thông lượng bắt đầu chững.
- **Sustained/soak test:** giữ tải ổn định trong thời gian dài để phát hiện rò rỉ bộ nhớ, tăng trưởng hàng đợi hoặc suy giảm dần.
- **Spike test:** tăng tải đột ngột để kiểm tra khả năng hấp thụ biến động và phục hồi.
- **Stress test:** tiếp tục tăng tải đến khi hệ thống không còn đáp ứng SLO, nhằm xác định hành vi tại giới hạn và chính sách quá tải.

Cần phân biệt hai cách tạo tải:

- **Open-loop:** bộ tạo tải phát yêu cầu theo tốc độ định trước, ít phụ thuộc vào thời gian phản hồi. Cách này phù hợp để kiểm tra hệ thống có đáp ứng được một arrival rate mục tiêu hay không.
- **Closed-loop:** mỗi virtual user đợi phản hồi rồi mới gửi yêu cầu tiếp theo. Khi hệ thống chậm, tốc độ gửi tự giảm; vì vậy kết quả có thể che khuất mức tải mà hệ thống thực sự phải chịu.

Trong mỗi lần chạy, ghi lại tốc độ gửi, tốc độ hoàn tất, p50/p95/p99, tỷ lệ lỗi, số yêu cầu đang chạy, queue depth và tài nguyên. Thử nhiều mức concurrency và arrival rate, thay đổi từng yếu tố một, rồi so sánh với SLO. Đừng chỉ ghi nhận thông lượng cực đại: mức tải có ý nghĩa vận hành là mức hệ thống duy trì được chất lượng phản hồi và tỷ lệ thành công trong thời gian đủ dài.

### Cách đọc một kết quả thử tải

Giả sử khi tăng tải từ 100 lên 200 yêu cầu/giây, thông lượng thành công tăng gần tương ứng và p95 gần như ổn định. Khi tăng tiếp lên 300 yêu cầu/giây, thông lượng chỉ tăng rất ít nhưng p95 tăng từ 180 ms lên 1,4 giây, queue depth tăng liên tục và timeout xuất hiện. Điều này cho thấy hệ thống đã tiến gần hoặc vượt năng lực của một thành phần.

Bước tiếp theo là xác định thành phần bão hòa bằng các chỉ số: CPU có đầy không, connection pool có hết kết nối không, dịch vụ phụ thuộc có tăng thời gian phản hồi không, hay scheduler có bị chặn bởi tác vụ blocking không. Sau khi xác định nút thắt, điều chỉnh giới hạn concurrency, giảm công việc không cần thiết, cải thiện thành phần phụ thuộc hoặc thay đổi chính sách tiếp nhận. Chạy lại cùng kịch bản để xác nhận p95/p99, thông lượng và tỷ lệ lỗi cùng cải thiện.

## 7. Những nhầm lẫn thường gặp

- **Thông lượng cao đồng nghĩa độ trễ thấp:** không đúng. Hệ thống có thể hoàn tất nhiều yêu cầu mỗi giây nhưng vẫn có một hàng đợi dài khiến từng yêu cầu chờ lâu.
- **Tăng concurrency luôn tăng thông lượng:** chỉ đúng khi còn tài nguyên nhàn rỗi. Sau điểm bão hòa, tăng concurrency có thể làm tăng tranh chấp, context switching và số yêu cầu in-flight.
- **Buffer lớn giải quyết được quá tải:** buffer chỉ trì hoãn thời điểm đầy. Nếu tốc độ đến luôn cao hơn tốc độ xử lý, mọi buffer hữu hạn cuối cùng cũng đầy.
- **Backpressure bảo đảm mọi nguồn đều chậm lại:** chỉ đúng khi nguồn hỗ trợ cơ chế demand. Nguồn nóng hoặc hệ thống bên ngoài không hỗ trợ Reactive Streams cần chính sách adapter riêng.
- **Độ trễ trung bình đủ để đánh giá trải nghiệm:** trung bình có thể che mất nhóm yêu cầu rất chậm. Hãy theo dõi phân vị và tỷ lệ yêu cầu vượt ngưỡng.
- **Retry luôn tăng khả năng thành công:** retry không giới hạn có thể tạo thêm tải đúng lúc hệ thống yếu nhất.

## 8. Bài tập vận dụng

Một pipeline nhận sự kiện đơn hàng. Mỗi sự kiện gọi một dịch vụ kiểm tra tồn kho rồi ghi kết quả. Trong thử nghiệm, nguồn phát 250 sự kiện/giây; consumer hoàn tất 180 sự kiện/giây; queue depth tăng đều; p99 tăng từ 400 ms lên 5 giây.

Hãy trả lời:

1. Offered load và completed throughput đang chênh nhau bao nhiêu sự kiện mỗi giây?
2. Vì sao tăng kích thước buffer chỉ trì hoãn vấn đề?
3. Bạn sẽ kiểm tra những chỉ số nào để xác định dịch vụ kiểm tra tồn kho hay consumer là nút thắt?
4. Nếu dùng Reactor, bạn sẽ chọn giới hạn concurrency cho lời gọi tồn kho như thế nào và dựa vào bằng chứng nào?
5. Khi hàng đợi đầy, nghiệp vụ đơn hàng cho phép những chính sách nào: lưu bền vững, từ chối, retry có giới hạn hay bỏ sự kiện? Vì sao?
6. Bạn sẽ thiết kế ramp-up test ra sao để tìm mức tải mà p95/p99 vẫn đáp ứng SLO?

**Gợi ý:** chênh lệch đầu vào và hoàn tất là 70 sự kiện/giây. Hãy bắt đầu bằng việc xác định năng lực và thời gian phản hồi của dịch vụ kiểm tra tồn kho, quan sát queue depth cùng số lời gọi đang chạy, sau đó thử các giới hạn concurrency khác nhau. Chọn chính sách khi buffer đầy theo yêu cầu đảm bảo không mất đơn hàng của nghiệp vụ.

## Kết luận

Độ trễ cho biết mỗi công việc phải chờ bao lâu, thông lượng cho biết hệ thống hoàn tất được bao nhiêu công việc, còn khả năng đáp ứng cho biết chất lượng phản hồi có được duy trì khi tải thay đổi hay không. Khi xây dựng pipeline reactive, hãy kết hợp đo p95/p99, quan sát hàng đợi và tài nguyên, giới hạn công việc đồng thời, truyền demand bằng backpressure ở nơi nguồn hỗ trợ, và xác định chính sách quá tải rõ ràng. Các phép thử tải lặp lại với cùng ranh giới đo giúp chọn cấu hình `Mono`, `Flux`, scheduler và concurrency dựa trên dữ liệu vận hành.
