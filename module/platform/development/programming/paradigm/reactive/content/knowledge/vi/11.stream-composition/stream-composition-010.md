# Giới hạn đồng thời, nạp trước và ảnh hưởng của nguồn con chậm

Trong **REACTIVE_PROGRAMMING**, ta thường ghép nhiều Publisher bất đồng bộ thành một pipeline bằng các toán tử như `flatMap`, `flatMapSequential` và `concatMap`. Mỗi phần tử đầu vào có thể tạo ra một Publisher con (inner Publisher), chẳng hạn một lời gọi HTTP hoặc truy vấn cơ sở dữ liệu. Khi có nhiều Publisher con cùng hoạt động, hai tham số cần quan tâm là **giới hạn đồng thời (concurrency)** và **số phần tử nạp trước (prefetch)**.

Hai tham số này ảnh hưởng đến số tác vụ đang chạy, lượng dữ liệu được yêu cầu và số phần tử có thể phải chờ trong bộ đệm. Một Publisher con chậm có thể chiếm một vị trí đồng thời, làm các phần tử đầu vào tiếp theo phải chờ; với toán tử giữ thứ tự, kết quả hoàn tất sớm cũng có thể phải nằm trong buffer để đợi kết quả trước đó. Hiểu các tương tác này giúp chọn toán tử phù hợp và tránh tạo tải quá lớn lên dịch vụ downstream.

## 1. Ghép luồng bất đồng bộ tạo ra nhiều công việc đang hoạt động

Giả sử ứng dụng đọc một luồng gồm nhiều đơn hàng. Với mỗi đơn, ứng dụng gọi một dịch vụ từ xa để lấy thông tin giao hàng:

```java
Flux<DeliveryInfo> deliveries = orderIds
    .flatMap(id -> deliveryClient.findByOrderId(id));
```

`flatMap` nhận từng `id`, gọi hàm ánh xạ để tạo một Publisher con, rồi hợp nhất các phần tử phát ra từ những Publisher con đó vào một luồng kết quả. Vì các lời gọi có thể chạy đồng thời, kết quả có thể đến theo thứ tự hoàn tất thay vì thứ tự đầu vào.

Nếu upstream phát nhiều `id` nhanh hơn các lời gọi từ xa hoàn tất, toán tử cần kiểm soát số Publisher con được subscribe cùng lúc và cách yêu cầu dữ liệu từ chúng. Nếu không giới hạn concurrency, một đợt đầu vào lớn có thể tạo quá nhiều lời gọi đồng thời, chiếm connection pool hoặc vượt quota của dịch vụ.

## 2. Concurrency giới hạn số Publisher con đang được subscribe

Reactor cung cấp overload của `flatMap` nhận tham số concurrency:

```java
Flux<DeliveryInfo> deliveries = orderIds
    .flatMap(id -> deliveryClient.findByOrderId(id), 8);
```

Tham số `8` đặt giới hạn tối đa tám inner Publisher đang được xử lý đồng thời tại toán tử này. Khi một inner Publisher kết thúc, vị trí đó được giải phóng và toán tử có thể subscribe vào Publisher con tiếp theo.

Concurrency có tác dụng như một van điều tiết số công việc đang hoạt động:

```text
Nguồn ID đơn hàng
       |
       v
    flatMap (concurrency = 3)
       |
       +---- Inner A: đang chậm -----------+
       +---- Inner B: hoàn tất nhanh ------+----> Kết quả hợp nhất
       +---- Inner C: đang xử lý ----------+
       |
       +---- Inner D: chờ một vị trí trống
```

Khi A, B, C chiếm đủ ba vị trí, D chưa được bắt đầu tại toán tử đó. Khi B hoàn tất, một vị trí được giải phóng và toán tử có thể tiếp tục với D.

Concurrency không nhất thiết bằng số request mạng đang chạy trong mọi implementation. Một inner Publisher có thể trì hoãn việc tạo request, phát nhiều phần tử hoặc đại diện cho một quy trình nhiều bước. Tuy vậy, với mẫu phổ biến mỗi inner Publisher thực hiện một request bất đồng bộ, concurrency là cách trực tiếp để giới hạn số request đang hoạt động.

## 3. Prefetch điều khiển lượng dữ liệu được yêu cầu trước

`prefetch` là số phần tử mà một toán tử yêu cầu trước từ một Publisher liên quan đến nó. Nó giúp toán tử có dữ liệu sẵn để xử lý, giảm thời gian chờ giữa các phần tử. Đổi lại, prefetch lớn có thể làm tăng lượng dữ liệu đang được giữ trong buffer.

Với `flatMap`, có thể cấu hình cả concurrency và prefetch:

```java
Flux<DeliveryInfo> deliveries = orderIds
    .flatMap(
        id -> deliveryClient.findByOrderId(id),
        8,   // maxConcurrency: số inner Publisher hoạt động đồng thời
        16   // prefetch: lượng phần tử yêu cầu trước từ mỗi inner Publisher
    );
```

Hai tham số giải quyết hai vấn đề khác nhau:

- `maxConcurrency` giới hạn số inner Publisher được subscribe đồng thời.
- `prefetch` điều chỉnh lượng phần tử được yêu cầu trước từ mỗi inner Publisher để toán tử có thể tiêu thụ chúng.

Trong trường hợp mỗi inner Publisher là `Mono` chỉ phát tối đa một phần tử, prefetch lớn hơn một thường không tạo thêm nhiều lợi ích cho chính inner Publisher đó. Với inner `Flux` phát nhiều phần tử, prefetch có thể ảnh hưởng rõ đến lượng dữ liệu được lấy trước và buffer.

Với `concatMap`, prefetch có ý nghĩa khác ở vị trí ghép luồng: nó điều khiển số phần tử outer được yêu cầu trước để chờ được ánh xạ tuần tự. `concatMap` chỉ subscribe một inner Publisher tại một thời điểm, nhưng vẫn có thể lấy trước các phần tử outer trong giới hạn prefetch.

## 4. Nguồn con chậm chiếm vị trí đồng thời

Giả sử `flatMap` có concurrency bằng 4. Ba inner Publisher hoàn tất nhanh, nhưng inner Publisher thứ tư mất 10 giây mới phát kết quả. Vị trí của inner chậm vẫn bị chiếm trong suốt thời gian đó. Nếu các vị trí còn lại tiếp tục được giải phóng, toán tử vẫn có thể xử lý các phần tử mới; một inner chậm không tự động chặn tất cả các inner khác trong `flatMap`.

Tuy nhiên, nếu tất cả vị trí đồng thời đều bị chiếm bởi các Publisher con chậm, các phần tử outer mới phải chờ. Khi outer source tiếp tục phát hoặc có buffer ở các tầng trước, dữ liệu có thể tích tụ ở đó. Giới hạn concurrency bảo vệ downstream khỏi quá nhiều tác vụ đồng thời, nhưng không loại bỏ độ trễ của các tác vụ đang chạy.

Một ví dụ với hai lời gọi có thời gian hoàn tất khác nhau:

```java
Flux<Integer> results = Flux.just(1, 2, 3)
    .flatMap(id -> {
        Duration delay = (id == 1)
            ? Duration.ofMillis(300)
            : Duration.ofMillis(100);

        return Mono.delay(delay).thenReturn(id);
    }, 2);
```

Hai inner Publisher đầu tiên được bắt đầu. Publisher cho `2` hoàn tất sau 100 ms, giải phóng một vị trí để Publisher cho `3` bắt đầu. Publisher cho `3` có thể hoàn tất trước Publisher cho `1`. Vì vậy, `flatMap` có thể phát kết quả theo thứ tự `2`, `3`, `1`.

Đây là hành vi phù hợp khi throughput quan trọng hơn thứ tự đầu vào. Nếu kết quả cần giữ thứ tự, phải chọn toán tử khác và chấp nhận chi phí buffer hoặc xử lý tuần tự.

## 5. So sánh flatMap, flatMapSequential và concatMap

Ba toán tử thường gặp có cách phối hợp inner Publisher khác nhau:

| Toán tử | Số inner Publisher đồng thời | Thứ tự phát kết quả | Ảnh hưởng của inner Publisher chậm |
|---|---:|---|---|
| `flatMap` | Có thể nhiều, giới hạn bởi concurrency | Theo thời điểm kết quả sẵn sàng; có thể xen kẽ | Inner chậm giữ một slot; inner khác vẫn có thể phát kết quả |
| `flatMapSequential` | Có thể nhiều, giới hạn bởi concurrency | Giữ thứ tự theo phần tử outer | Kết quả inner sau nếu hoàn tất sớm có thể phải chờ trong buffer phía sau inner chậm |
| `concatMap` | Một inner Publisher tại một thời điểm | Giữ thứ tự | Inner hiện tại chậm sẽ trì hoãn việc subscribe và xử lý inner tiếp theo |

### `flatMap`: ưu tiên tiến độ hoàn tất

Chọn `flatMap` khi các kết quả độc lập và downstream chấp nhận thứ tự hoàn tất. Một inner Publisher chậm không ngăn các inner khác đang hoạt động phát dữ liệu.

### `flatMapSequential`: đồng thời nhưng giữ thứ tự

`flatMapSequential` subscribe nhiều inner Publisher cùng lúc nhưng phát kết quả theo thứ tự tương ứng với đầu vào. Nếu inner đầu tiên chậm, kết quả từ inner thứ hai hoặc thứ ba có thể đã sẵn sàng nhưng phải đợi. Chúng được giữ trong buffer cho đến khi các kết quả trước đó được phát.

Hiện tượng này được gọi là head-of-line blocking: một phần tử ở đầu hàng chờ làm chậm việc phát các phần tử phía sau, dù những phần tử đó đã hoàn tất.

### `concatMap`: tuần tự hóa công việc

`concatMap` chỉ subscribe inner Publisher tiếp theo sau khi inner hiện tại kết thúc. Nó giữ thứ tự và tránh nhiều inner Publisher chạy cùng lúc, nhưng một inner chậm sẽ trực tiếp kéo dài thời gian chờ của tất cả phần tử sau nó.

## 6. Buffer và head-of-line blocking trong flatMapSequential

Giả sử có ba inner Publisher theo thứ tự đầu vào:

```text
Inner 1: ----------------------> kết quả 1
Inner 2: ----> kết quả 2
Inner 3: ------> kết quả 3

Thời điểm kết quả sẵn sàng: 2, 3, 1
Thứ tự downstream cần nhận: 1, 2, 3
```

Với `flatMap`, downstream có thể nhận `2`, `3`, `1`. Với `flatMapSequential`, kết quả `2` và `3` phải chờ kết quả `1`; buffer chứa các kết quả đã hoàn tất nhưng chưa đến lượt phát.

Nếu inner đầu tiên chậm kéo dài và nhiều inner phía sau hoàn tất, buffer có thể tăng. Concurrency và prefetch đặt giới hạn cho các phần của quá trình, nhưng vẫn cần cân nhắc số phần tử đã được lấy trước và kích thước của chúng. Giữ thứ tự có chi phí tài nguyên khi thời gian hoàn tất giữa các inner Publisher chênh lệch lớn.

## 7. Ước lượng lượng dữ liệu có thể được giữ

Một cách ước lượng sơ bộ cho phần dữ liệu được nạp trước từ các inner Publisher của `flatMap` là:

\[
\text{Số phần tử inner được prefetch} \approx C \times P
\]

Trong đó:

- \(C\) là concurrency tối đa.
- \(P\) là prefetch cho mỗi inner Publisher.

Ví dụ, concurrency bằng 8 và prefetch bằng 16 có thể cho phép toán tử yêu cầu trước lượng dữ liệu cỡ 128 phần tử từ các inner Publisher, tùy ngữ nghĩa nguồn và cách toán tử tiêu thụ/phát dữ liệu.

Đây chỉ là ước lượng cho một phần buffer, không phải giới hạn bộ nhớ tổng thể. Còn có dữ liệu outer đã được yêu cầu, queue của các toán tử khác, phần tử đang được xử lý, object phụ trợ và buffer trong client hoặc driver. Nếu phần tử có kích thước lớn, cùng một số lượng phần tử có thể tiêu thụ bộ nhớ rất khác nhau.

Vì vậy, hãy xem concurrency và prefetch là các nút điều chỉnh demand và hoạt động của pipeline, sau đó đo heap, queue, latency và throughput trong môi trường gần thực tế.

## 8. Cấu hình concurrency và prefetch trong Reactor

Một ví dụ lấy thông tin khách hàng từ dịch vụ bên ngoài:

```java
Flux<CustomerView> customerViews = orderIds
    .flatMap(
        id -> customerClient.findByOrderId(id)
            .map(customer -> CustomerView.from(id, customer)),
        12,
        4
    );
```

Ở đây, tối đa 12 inner Publisher được subscribe đồng thời; mỗi inner Publisher có thể được yêu cầu trước tối đa bốn phần tử theo chính sách prefetch của toán tử. Nếu API chỉ trả về `Mono<Customer>`, mỗi inner chỉ có tối đa một phần tử, nên prefetch 4 không đồng nghĩa mỗi request tạo ra bốn khách hàng.

Với tác vụ tuần tự cần giữ thứ tự:

```java
Flux<Receipt> receipts = orderIds
    .concatMap(
        id -> receiptService.createReceipt(id),
        8
    );
```

Chỉ một inner Publisher được subscribe tại một thời điểm. Prefetch 8 cho phép toán tử lấy trước một số `id` từ nguồn outer để giảm khoảng chờ giữa các lần ánh xạ. Nó không làm tăng số thao tác `createReceipt` đang chạy đồng thời.

## 9. Kiểm thử ảnh hưởng của nguồn con chậm bằng virtual time

`StepVerifier.withVirtualTime` giúp kiểm tra thứ tự phát mà không phải chờ đồng hồ thực. Ví dụ sau mô phỏng inner đầu tiên mất 300 ms, hai inner sau mất 100 ms:

```java
StepVerifier.withVirtualTime(() ->
        Flux.just(1, 2, 3)
            .flatMap(id -> {
                Duration delay = (id == 1)
                    ? Duration.ofMillis(300)
                    : Duration.ofMillis(100);

                return Mono.delay(delay).thenReturn(id);
            }, 2)
    )
    .expectSubscription()
    .thenAwait(Duration.ofMillis(300))
    .expectNext(2, 3, 1)
    .verifyComplete();
```

Với `flatMap`, kết quả hoàn tất sớm được phát trước. Nếu đổi sang `flatMapSequential` với cùng concurrency và độ trễ, downstream vẫn nhận `1`, `2`, `3`, dù `2` và `3` sẵn sàng sớm hơn. Nếu đổi sang `concatMap`, các inner được chạy lần lượt nên tổng thời gian ảo xấp xỉ 500 ms và kết quả cũng là `1`, `2`, `3`.

Khi dùng virtual time, hãy tạo pipeline bên trong supplier truyền cho `withVirtualTime`, để các nguồn thời gian như `Mono.delay` sử dụng scheduler ảo được cài đặt cho bài test. Virtual time không tăng tốc lời gọi blocking tùy ý.

## 10. Chọn concurrency và prefetch theo đặc tính công việc

Không nên chọn concurrency lớn chỉ để tối đa hóa số tác vụ đang chạy. Nếu downstream như database hoặc HTTP service đã gần chạm giới hạn, tăng concurrency có thể làm latency và lỗi tăng thay vì cải thiện throughput.

Một số nguyên tắc lựa chọn:

- **I/O bất đồng bộ độc lập:** có thể dùng `flatMap` với concurrency vừa phải để tận dụng thời gian chờ I/O.
- **Cần giữ thứ tự nhưng vẫn muốn chạy song song:** cân nhắc `flatMapSequential`, đồng thời theo dõi buffer và độ chênh thời gian hoàn tất giữa các inner Publisher.
- **Cần xử lý tuần tự hoặc bảo toàn thứ tự tác dụng phụ:** dùng `concatMap`; chọn prefetch vừa đủ để tránh yêu cầu quá nhiều phần tử outer.
- **Inner Publisher phát nhiều phần tử:** điều chỉnh prefetch dựa trên kích thước phần tử, tốc độ downstream và khả năng buffer.
- **Inner Publisher chỉ phát một phần tử:** tăng prefetch của inner thường không đem lại lợi ích tương ứng; hãy tập trung vào concurrency và giới hạn của dịch vụ ngoài.
- **Có quota theo thời gian:** concurrency không thay thế rate limiter. Cần thêm cơ chế giới hạn request theo giây hoặc theo cửa sổ thời gian.

Nên bắt đầu với giới hạn nhỏ, đo throughput, latency, số inner đang hoạt động và queue, sau đó điều chỉnh dần. Đặt giới hạn phù hợp với năng lực của dependency phía sau thay vì chỉ dựa vào số lõi CPU của ứng dụng.

## 11. Theo dõi dấu hiệu inner Publisher chậm

Trong vận hành, có thể quan sát các chỉ số sau:

1. Số inner Publisher đang hoạt động và thời gian hoạt động của từng inner.
2. Thời gian chờ từ lúc phần tử outer đến đến lúc inner được subscribe.
3. Thời gian hoàn tất của inner Publisher và tỷ lệ timeout.
4. Số phần tử đang chờ trong buffer hoặc queue ở các toán tử giữ thứ tự.
5. Demand được yêu cầu upstream, prefetch và số phần tử thực tế được phát.
6. Throughput đầu vào, throughput đầu ra và độ trễ đầu cuối.
7. Tình trạng connection pool, quota và latency của dịch vụ được gọi.

Nếu concurrency luôn đạt ngưỡng và thời gian inner tăng, các phần tử outer sẽ chờ lâu hơn. Nếu dùng `flatMapSequential` và inner đầu tiên thường xuyên chậm, kết quả phía sau có thể tích tụ trong buffer. Nếu dùng `concatMap`, một inner chậm làm toàn bộ chuỗi phía sau chờ theo thứ tự.

## 12. Checklist trước khi ghép nhiều Publisher con

Trước khi chọn toán tử, hãy xác định:

1. Kết quả có bắt buộc giữ thứ tự đầu vào không?
2. Có bao nhiêu inner Publisher được phép hoạt động đồng thời?
3. Mỗi inner Publisher phát một phần tử hay nhiều phần tử?
4. Prefetch được áp dụng ở ranh giới nào và buffer có thể chứa dữ liệu gì?
5. Nếu một inner Publisher chậm hoặc không bao giờ kết thúc, slot concurrency được giải phóng bằng cách nào? Có cần `timeout` hoặc cancellation không?
6. Nếu giữ thứ tự, kết quả hoàn tất sớm có thể phải chờ bao lâu và chiếm bao nhiêu bộ nhớ?
7. Dependency phía sau chịu được concurrency đã chọn không?
8. Có cần rate limit theo thời gian ngoài backpressure không?

Concurrency kiểm soát số inner Publisher được xử lý đồng thời; prefetch điều chỉnh lượng phần tử được yêu cầu trước. `flatMap` ưu tiên phát kết quả khi sẵn sàng, `flatMapSequential` giữ thứ tự bằng cách có thể buffer kết quả đến sớm, còn `concatMap` tuần tự hóa các inner Publisher. Khi có nguồn con chậm, lựa chọn này quyết định liệu các công việc khác vẫn tiến triển, kết quả có phải chờ theo thứ tự hay toàn bộ chuỗi bị kéo dài. Đặt giới hạn phù hợp và quan sát buffer giúp pipeline cân bằng throughput, thứ tự và tài nguyên.
