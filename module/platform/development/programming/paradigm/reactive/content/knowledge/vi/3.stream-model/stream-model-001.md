# Biểu diễn một chuỗi giá trị theo thời gian

Trong lập trình reactive, dữ liệu thường đến dần theo thời gian: một cảm biến gửi số đo, một dịch vụ nhận thông báo đơn hàng, hoặc một ứng dụng nhận từng phần kết quả từ một nguồn bên ngoài. Thay vì đợi gom tất cả giá trị thành một tập hợp rồi mới xử lý, ta có thể biểu diễn chúng thành một **luồng (stream)** và xử lý mỗi giá trị khi nó được phát ra.

Đây là nền tảng của mô hình luồng trong REACTIVE_PROGRAMMING. Module này học cách làm việc với các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, sau đó thực hành Mono, Flux, các toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong Java. Để hiểu những cơ chế đó, trước tiên cần xác định một luồng biểu diễn điều gì, các giá trị xuất hiện theo thứ tự nào và thời gian được gắn với chúng ra sao.

## Luồng là một chuỗi giá trị có thứ tự theo thời gian

Một luồng có thể được hình dung là một dãy các lần phát giá trị:

```text
Thời gian:   t0       t1       t2       t3       --- tiếp tục ---
              |        |        |        |
Giá trị:     v0       v1       v2       v3       ...
```

Mỗi lần phát thường được gọi là một phần tử hoặc một sự kiện. Ta có thể mô hình hóa một luồng quan sát được như các cặp `(thời điểm, giá trị)`: `(t0, v0)`, `(t1, v1)`, `(t2, v2)`. Cách biểu diễn này nhấn mạnh hai thành phần:

- **Giá trị** cho biết điều gì đã được phát, chẳng hạn nhiệt độ `25.4`, trạng thái đơn hàng `SHIPPED` hoặc một thông điệp.
- **Thời điểm** cho biết giá trị gắn với lúc nào. Đây có thể là thời điểm sự kiện xảy ra, thời điểm hệ thống nhận sự kiện hoặc thời điểm pipeline xử lý nó.

Luồng thường có thứ tự quan sát: Subscriber nhận các tín hiệu theo một trình tự. Tuy nhiên, thứ tự nhận không tự động chứng minh thứ tự xảy ra trong nghiệp vụ. Ví dụ, một thông điệp có thể đến muộn do mạng, nên sự kiện xảy ra lúc 10:02 có thể được nhận sau sự kiện xảy ra lúc 10:03. Ta cần giữ lại timestamp nghiệp vụ nếu thứ tự theo thời gian sự kiện có ý nghĩa.

Luồng cũng không nhất thiết phải chứa toàn bộ dữ liệu trong bộ nhớ. Nó có thể phát từng phần tử khi dữ liệu sẵn sàng, tiếp tục trong thời gian dài, hoặc không có điểm kết thúc tự nhiên. Vì vậy, nên xem luồng là một quá trình phát dữ liệu theo thời gian thay vì mặc định xem nó như một `List` đã có sẵn.

## Các đặc điểm quan trọng của một luồng

Khi mô tả một nguồn dữ liệu, hãy xác định những đặc điểm sau:

| Đặc điểm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Kiểu giá trị | Mỗi phần tử có kiểu và ý nghĩa gì? | `Reading`, `OrderEvent`, `Long` |
| Thứ tự | Thứ tự nào có ý nghĩa với người tiêu thụ? | Thứ tự phát, số thứ tự sự kiện hoặc timestamp nghiệp vụ |
| Nhịp phát | Giá trị xuất hiện đều đặn hay theo sự kiện? | Mỗi giây một số đo hoặc khi trạng thái đơn hàng thay đổi |
| Số lượng | Luồng hữu hạn hay có thể kéo dài vô hạn? | Kết quả của một truy vấn hoặc dữ liệu cảm biến liên tục |
| Kết thúc | Điều gì khiến nguồn hoàn tất hoặc thất bại? | Đọc hết tệp, thiết bị ngắt kết nối, lỗi truy cập |
| Nhu cầu tiêu thụ | Người nhận có thể xử lý bao nhiêu phần tử? | Tối đa 20 phần tử đang được yêu cầu hoặc xử lý |

Các đặc điểm này ảnh hưởng trực tiếp đến cách xây dựng pipeline. Một luồng hữu hạn có thể hoàn tất bình thường; một luồng liên tục cần chính sách dừng, hủy hoặc giới hạn thời gian. Một nguồn phát nhanh hơn khả năng xử lý của Subscriber cần cơ chế điều tiết phù hợp. Thứ tự nghiệp vụ quan trọng có thể yêu cầu lưu sequence number hoặc sắp xếp theo event time.

## Luồng hữu hạn, luồng liên tục và luồng rỗng

Một luồng **hữu hạn** phát một số lượng phần tử rồi hoàn tất. Ví dụ, danh sách ba mã đơn hàng hoặc kết quả của một truy vấn có giới hạn. Một luồng **liên tục** có thể phát dữ liệu trong thời gian dài mà không có thời điểm hoàn tất được xác định trước, như số đo cảm biến hoặc sự kiện từ hệ thống giao dịch.

Project Reactor cung cấp `Flux<T>` để biểu diễn một Publisher có thể phát từ không đến nhiều phần tử. `Mono<T>` biểu diễn một Publisher có thể phát không hoặc một phần tử. Cả hai đều có thể kết thúc bằng tín hiệu hoàn tất hoặc lỗi; chúng không phải các collection chứa sẵn dữ liệu.

```java
import reactor.core.publisher.Flux;

Flux<String> finite = Flux.just("created", "paid", "shipped");

Flux<String> empty = Flux.empty();

Flux<Long> ongoing = Flux.interval(java.time.Duration.ofSeconds(1));
```

`finite` phát ba giá trị rồi hoàn tất. `empty` không phát giá trị nào và hoàn tất bình thường. `ongoing` phát các số đếm theo nhịp thời gian cho đến khi bị hủy hoặc gặp điều kiện kết thúc do ứng dụng áp dụng. Để biến một nguồn liên tục thành một luồng hữu hạn, có thể giới hạn số phần tử:

```java
Flux<Long> firstThreeTicks = Flux
    .interval(java.time.Duration.ofSeconds(1))
    .take(3);
```

Không nên giả định mọi luồng đều hoàn tất. Với nguồn sự kiện dài hạn, Subscriber có thể đăng ký trong suốt vòng đời của một thành phần; khi thành phần dừng, subscription cần được hủy để ngừng nhận thêm dữ liệu và giải phóng tài nguyên liên quan.

## Giá trị dữ liệu và tín hiệu điều khiển vòng đời

Trong Reactive Streams, Publisher giao tiếp với Subscriber thông qua các tín hiệu. Những tín hiệu quan trọng gồm:

1. `onSubscribe(subscription)`: Publisher cung cấp Subscription để Subscriber yêu cầu dữ liệu hoặc hủy đăng ký.
2. `onNext(value)`: phát một phần tử dữ liệu.
3. `onError(error)`: kết thúc luồng do lỗi.
4. `onComplete()`: kết thúc luồng bình thường.

`onNext` mang dữ liệu của luồng. `onError` và `onComplete` mô tả trạng thái kết thúc. Một luồng có thể phát không có `onNext` nào rồi hoàn tất, hoặc kết thúc bằng lỗi. Sau một tín hiệu kết thúc, Publisher không tiếp tục phát các phần tử cho subscription đó. Subscriber còn có thể gọi `cancel()` thông qua Subscription để báo rằng nó không muốn nhận thêm tín hiệu.

Reactive Streams cũng định nghĩa cơ chế yêu cầu dữ liệu: Subscriber gọi `request(n)` để báo số phần tử nó sẵn sàng tiếp nhận. Đây là cơ sở của backpressure. Nhịp phát theo thời gian và nhu cầu tiêu thụ có liên quan nhưng không giống nhau: nguồn có thể tạo sự kiện theo đồng hồ hoặc theo hoạt động bên ngoài, trong khi Subscriber điều tiết số phần tử nó yêu cầu. Khi thiết kế hệ thống, cần hiểu nguồn và các toán tử trung gian xử lý tình huống tốc độ phát vượt tốc độ tiêu thụ như thế nào.

## Thời điểm sự kiện và thời điểm xử lý

Trong hệ thống phân tán, một sự kiện thường có nhiều mốc thời gian. Hai mốc phổ biến nhất là:

- **Event time (thời điểm sự kiện):** lúc sự việc thực tế xảy ra theo đồng hồ của nguồn nghiệp vụ. Ví dụ, thiết bị đo nhiệt độ lúc 10:00:05.
- **Processing time (thời điểm xử lý):** lúc ứng dụng xử lý phần tử. Ví dụ, dịch vụ nhận và xử lý số đo đó lúc 10:00:08.

Có thể có thêm **ingestion time (thời điểm tiếp nhận)**, tức lúc hệ thống trung gian ghi nhận sự kiện. Ba mốc có thể khác nhau do độ trễ mạng, hàng đợi, đồng hồ thiết bị lệch hoặc tải xử lý. Nếu cần tính toán theo thời gian xảy ra sự kiện, hãy mang event time trong payload thay vì chỉ gắn thời gian hiện tại khi xử lý.

Ví dụ, một bản ghi cảm biến có thể được mô hình hóa như sau:

```java
import java.time.Instant;

record SensorReading(
    long sequence,
    Instant occurredAt,
    double temperature
) {}
```

`sequence` giúp nhận diện thứ tự do nguồn gán; `occurredAt` ghi thời điểm phép đo xảy ra; `temperature` là giá trị đo. Nếu ứng dụng muốn quan sát thời điểm tiếp nhận, có thể thêm trường `receivedAt` khi nhận thông điệp. Việc lưu cả hai giúp phân biệt dữ liệu đến muộn với dữ liệu thực sự được tạo muộn.

Không nên dùng đồng hồ lịch như `Instant.now()` để đo chính xác khoảng thời gian chạy. Đồng hồ hệ thống có thể được điều chỉnh. Với phép đo thời lượng trong một tiến trình, hãy dùng đồng hồ đơn điệu như `System.nanoTime()` hoặc toán tử đo khoảng cách thời gian phù hợp. Timestamp nghiệp vụ vẫn cần kiểu thời gian có thể diễn giải như `Instant`.

## Biểu diễn một nguồn phát theo thời gian bằng Flux

Ví dụ sau tạo ba số đo cách nhau theo nhịp một giây:

```java
import java.time.Duration;
import java.time.Instant;
import reactor.core.publisher.Flux;

record Reading(long sequence, Instant receivedAt, double temperature) {}

class SensorStream {
    Flux<Reading> readings() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .map(tick -> new Reading(
                tick,
                Instant.now(),
                24.0 + tick * 0.1
            ));
    }

    void start() {
        readings().subscribe(System.out::println);
    }
}
```

`Flux.interval` tạo các tick theo thời gian; `take(3)` giới hạn nguồn còn ba phần tử; `map` chuyển mỗi tick thành một đối tượng số đo. `receivedAt` trong ví dụ được tạo tại lúc pipeline xử lý tick, nên nó là thời điểm ghi nhận trong ứng dụng. Trong hệ thống thật, `occurredAt` nên lấy từ payload của thiết bị nếu thiết bị cung cấp thời gian xảy ra phép đo.

Ví dụ này cũng cho thấy một đặc điểm quan trọng: `Flux` mô tả cách phát dữ liệu khi có subscription. Chỉ khai báo biến `readings` hoặc gọi phương thức trả về Flux chưa có nghĩa các giá trị đã được thu thập. Khi gọi `subscribe`, quá trình tiêu thụ mới bắt đầu. Với nguồn theo thời gian, mỗi subscription có thể khởi tạo một lịch phát riêng tùy loại Publisher.

## Quan sát khoảng cách giữa các giá trị

Để hiểu nhịp phát thực tế, có thể quan sát thời gian trôi qua giữa các phần tử. Reactor có toán tử `elapsed()` để phát kèm khoảng thời gian tính bằng mili giây kể từ lần phát trước; với phần tử đầu tiên, khoảng thời gian được tính từ lúc subscription bắt đầu.

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux.just("A", "B", "C")
    .delayElements(Duration.ofMillis(200))
    .elapsed()
    .subscribe(tuple -> System.out.printf(
        "elapsed=%d ms, value=%s%n",
        tuple.getT1(),
        tuple.getT2()
    ));
```

`delayElements` làm chậm việc phát từng phần tử trong ví dụ; `elapsed` giúp quan sát khoảng thời gian giữa các lần phát. Các con số thực tế có thể lớn hơn giá trị cấu hình do bộ lập lịch, tải CPU và độ trễ của môi trường. Vì vậy, đây là cách quan sát nhịp phát chứ không phải cơ chế bảo đảm thời gian thực chính xác.

## Thứ tự phát và thứ tự thời gian nghiệp vụ

Đối với một subscription, các tín hiệu của Reactive Streams phải được phát tuần tự, không chồng lấn theo cách vi phạm hợp đồng. Tuy vậy, khi kết hợp nhiều Publisher độc lập, các phần tử có thể xen kẽ tùy thời điểm mỗi nguồn phát dữ liệu. Thứ tự đó phản ánh thời điểm các tín hiệu đến pipeline, không nhất thiết là thứ tự nghiệp vụ giữa các nguồn.

Ví dụ, hệ thống nhận sự kiện thanh toán và sự kiện kho từ hai dịch vụ. Sự kiện kho có thể đến trước sự kiện thanh toán dù nghiệp vụ yêu cầu thanh toán được xác nhận trước khi xuất kho. Nếu cần áp dụng quy tắc nghiệp vụ, ứng dụng phải dựa trên mã tương quan, sequence number, timestamp hoặc trạng thái được xác thực; không nên suy ra quan hệ nhân quả chỉ từ thứ tự callback.

Khi cần giữ thứ tự nguồn, hãy chọn cách kết hợp và xử lý phù hợp. Trong Reactor, `concat` đăng ký và tiêu thụ các nguồn lần lượt; `merge` cho phép các nguồn phát xen kẽ theo thời điểm tín hiệu đến. Dù dùng toán tử nào, thứ tự nghiệp vụ xuyên nhiều nguồn vẫn cần được biểu diễn rõ trong dữ liệu hoặc quy tắc xử lý.

## Những nhầm lẫn thường gặp

**Coi luồng như một danh sách.** Danh sách thường đã chứa các phần tử; luồng có thể chưa phát phần tử nào, có thể phát vô hạn và có thể thay đổi theo thời gian. Không nên thu thập một nguồn vô hạn vào bộ nhớ.

**Cho rằng mọi luồng đều bất đồng bộ.** Một `Flux.just(1, 2, 3)` có thể phát đồng bộ ngay trên luồng gọi `subscribe`. Việc dùng kiểu Publisher không tự động tạo luồng nền hoặc chạy song song. Scheduler và đặc tính của nguồn quyết định nơi thực thi.

**Đồng nhất thứ tự nhận với thứ tự xảy ra.** Sự kiện đến muộn có thể mang event time cũ hơn sự kiện đã nhận trước đó. Giữ timestamp và sequence number nếu logic phụ thuộc thứ tự nghiệp vụ.

**Dùng thời điểm xử lý thay cho thời điểm sự kiện.** Gắn `Instant.now()` lúc xử lý chỉ cho biết lúc ứng dụng chạm đến dữ liệu. Nếu cần phân tích theo thời điểm sự kiện, hãy lấy timestamp từ nguồn và lưu riêng thời điểm tiếp nhận.

**Quên vòng đời subscription.** Nguồn liên tục có thể tiếp tục phát cho đến khi bị hủy hoặc gặp lỗi. Ứng dụng cần quản lý Subscription và hủy khi thành phần không còn cần dữ liệu.

**Bỏ qua tốc độ tiêu thụ.** Một luồng phát nhanh có thể tạo áp lực lên các bước sau. Cần hiểu `request(n)`, backpressure, buffering và giới hạn concurrency ở các ranh giới liên quan; không giả định mọi nguồn đều tự điều tiết theo nhu cầu của Subscriber.

## Tự kiểm tra

1. Một `Flux` phát ba trạng thái đơn hàng rồi hoàn tất có đặc điểm nào của luồng hữu hạn?
2. Một cảm biến tạo sự kiện lúc 10:00:05 nhưng dịch vụ chỉ xử lý lúc 10:00:08. Hai timestamp này đại diện cho điều gì?
3. Vì sao `Flux.just("A", "B", "C")` không chứng minh rằng pipeline đang chạy bất đồng bộ?
4. Một nguồn sự kiện liên tục cần được dừng khi ứng dụng đóng. Thành phần nào của hợp đồng Reactive Streams cho phép Subscriber ngừng nhận dữ liệu?
5. Khi kết hợp hai Publisher độc lập bằng `merge`, vì sao thứ tự tín hiệu không thể thay thế quy tắc thứ tự nghiệp vụ?

Khi mô tả được kiểu giá trị, thứ tự, nhịp phát, thời gian sự kiện và vòng đời của nguồn, bạn đã có mô hình đủ rõ để chọn `Flux` hoặc `Mono`, xây dựng pipeline và xử lý dữ liệu đến dần theo thời gian trong hệ sinh thái reactive của Java.
