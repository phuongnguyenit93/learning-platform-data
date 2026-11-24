# Đồng thời và song song: vai trò của luồng thực thi

Trong lập trình bất đồng bộ, nhiều công việc có thể tiến triển mà chương trình không phải chờ từng công việc hoàn tất. Tuy nhiên, việc nhiều tác vụ cùng tồn tại không đồng nghĩa chúng thực sự chạy cùng một thời điểm. Để thiết kế pipeline reactive đúng cách, cần phân biệt **đồng thời (concurrency)** với **song song (parallelism)**, đồng thời hiểu luồng thực thi quyết định tác vụ nào được chạy ở đâu và khi nào.

Chủ đề này thuộc chương **Bất đồng bộ** của REACTIVE_PROGRAMMING. Khi làm việc với các luồng sự kiện, Publisher–Subscriber, Mono và Flux, ta thường mô tả *dòng dữ liệu* bằng các toán tử và điều khiển *nơi thực thi* bằng scheduler. Hai phần đó liên quan chặt chẽ nhưng không phải cùng một khái niệm: một pipeline có thể bất đồng bộ mà không chạy song song, và việc chuyển sang luồng khác không tự động làm cho mọi phép tính nhanh hơn.

## Đồng thời và song song khác nhau thế nào?

**Đồng thời** là khả năng quản lý nhiều tác vụ đang tiến triển trong cùng một khoảng thời gian. Bộ lập lịch có thể luân phiên thực thi chúng: tác vụ A chạy một đoạn, tạm nhường CPU để chờ I/O, rồi tác vụ B được chạy. Các tác vụ có thể chồng lấp về thời gian dù tại một thời điểm chỉ có một tác vụ sử dụng một lõi CPU.

**Song song** là việc thực thi nhiều tác vụ thực sự cùng thời điểm, thường trên nhiều lõi CPU hoặc nhiều bộ xử lý. Song song là một cách triển khai đồng thời, nhưng đồng thời không đòi hỏi song song.

| Khía cạnh | Đồng thời (concurrency) | Song song (parallelism) |
|---|---|---|
| Ý nghĩa | Nhiều tác vụ cùng tiến triển | Nhiều tác vụ thực thi cùng lúc |
| CPU | Có thể luân phiên trên một lõi | Thường dùng nhiều lõi |
| Mục tiêu thường gặp | Tổ chức nhiều công việc, chờ I/O hiệu quả | Tăng thông lượng tính toán |
| Thách thức | Điều phối, trạng thái dùng chung, thứ tự sự kiện | Tranh chấp tài nguyên, đồng bộ và chi phí phối hợp |
| Ví dụ | Một luồng xử lý lần lượt các phản hồi mạng khi từng phản hồi sẵn sàng | Nhiều luồng tính toán các phần độc lập của một tập dữ liệu |

Hãy hình dung một dịch vụ cần gọi ba API độc lập. Nếu gửi yêu cầu thứ hai sau khi yêu cầu thứ nhất trả lời, rồi mới gửi yêu cầu thứ ba, thời gian chờ bị cộng dồn. Nếu gửi cả ba trước và xử lý mỗi phản hồi khi nó đến, các yêu cầu tiến triển đồng thời. Điều đó không bắt buộc cần ba lõi CPU: phần lớn thời gian các tác vụ đang chờ mạng. Ngược lại, nếu cần mã hóa ba khối dữ liệu lớn, chia phép tính thành các phần độc lập và chạy trên nhiều lõi có thể tạo ra song song thực sự.

## Luồng thực thi là gì?

Luồng (thread) là đơn vị thực thi mà hệ điều hành hoặc runtime lập lịch. Một luồng có ngăn xếp lời gọi và luồng điều khiển riêng; nhiều luồng trong cùng tiến trình thường chia sẻ heap và các tài nguyên của tiến trình. Vì vậy, chúng có thể phối hợp qua đối tượng dùng chung, nhưng cũng có thể gây race condition nếu đọc và ghi trạng thái mà không có đồng bộ phù hợp.

Một **luồng** không đồng nghĩa với một **tác vụ**. Tác vụ là công việc logic, chẳng hạn lấy hồ sơ khách hàng hoặc tính tổng đơn hàng. Luồng là nơi công việc đó được thực thi. Một luồng có thể xử lý nhiều tác vụ nối tiếp; một tác vụ cũng có thể được tiếp tục trên luồng khác nếu mô hình thực thi cho phép. Trong các hệ thống reactive, scheduler thường quản lý một nhóm luồng và quyết định nơi các tín hiệu được xử lý.

Các luồng nền tảng (platform threads) của Java thường gắn với tài nguyên hệ điều hành tương đối tốn kém. Vì thế, tạo một luồng mới cho mỗi sự kiện hoặc mỗi yêu cầu có thể gây áp lực lên bộ nhớ, bộ lập lịch và khả năng chuyển ngữ cảnh. Pool luồng tái sử dụng một số luồng hữu hạn để xử lý nhiều tác vụ. Với I/O có thời gian chờ dài, mô hình non-blocking cho phép một luồng phục vụ nhiều luồng công việc đang chờ mà không bị giữ lại trong lời gọi blocking.

Java cũng có virtual threads từ Java 21, là luồng nhẹ do JVM quản lý. Chúng giúp viết mã theo phong cách blocking dễ mở rộng hơn cho nhiều tác vụ I/O đồng thời. Virtual thread không làm một phép tính đơn luồng tự nhiên chạy song song; khả năng song song vẫn phụ thuộc số lõi và cách phân chia công việc. Chúng cũng không thay thế việc quản lý giới hạn kết nối, giới hạn dịch vụ ngoài hay các tài nguyên có dung lượng hữu hạn.

## Đồng thời trong pipeline reactive

Trong Reactive Streams, Publisher phát tín hiệu đến Subscriber theo hợp đồng; Mono và Flux của Project Reactor cung cấp các kiểu Publisher quen thuộc. Việc khai báo một chuỗi toán tử không có nghĩa mỗi toán tử sẽ tự tạo một luồng riêng. Nếu không có ranh giới chuyển scheduler, các bước thường tiếp tục trên luồng đang phát tín hiệu. Luồng đó có thể là luồng gọi `subscribe`, luồng phát dữ liệu của nguồn, hoặc luồng do toán tử upstream sử dụng.

Điều này có hai hệ quả thực tế:

- Một thao tác blocking trong pipeline có thể chiếm giữ luồng đang phát tín hiệu. Nếu đó là luồng sự kiện dùng chung, các tác vụ khác cũng có thể bị chậm.
- Thêm luồng và chuyển scheduler có chi phí. Chỉ nên chuyển khi có lý do rõ ràng, chẳng hạn cô lập I/O blocking hoặc thực hiện phép tính độc lập có thể hưởng lợi từ nhiều lõi.

### Ví dụ: một chuỗi chạy đồng bộ trên luồng gọi

```java
import reactor.core.publisher.Flux;

public class ConcurrencyExample {
    public static void main(String[] args) {
        Flux.range(1, 3)
            .map(number -> {
                System.out.println(
                    "value=" + number + ", thread=" + Thread.currentThread().getName()
                );
                return number * 10;
            })
            .subscribe(value -> System.out.println("result=" + value));
    }
}
```

Với nguồn `Flux.range` đồng bộ và không có toán tử đổi scheduler, các phép `map` và consumer thường chạy trên luồng gọi `subscribe`. Tên luồng cụ thể phụ thuộc cách chạy chương trình, nhưng các bước của ví dụ không tự chuyển sang pool khác chỉ vì chúng nằm trong Flux.

### Ví dụ: cô lập thao tác blocking

Khi phải gọi một API blocking hoặc thư viện cũ không hỗ trợ reactive, có thể chuyển phần công việc đó sang `boundedElastic`:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> profile = Mono.fromCallable(() -> legacyClient.loadProfile("user-42"))
    .subscribeOn(Schedulers.boundedElastic());

profile.subscribe(
    value -> System.out.println("Loaded: " + value),
    error -> System.err.println("Load failed: " + error.getMessage())
);
```

`fromCallable` trì hoãn lời gọi cho đến khi có subscription. `subscribeOn` chỉ định scheduler dùng để bắt đầu thực thi phần nguồn của chuỗi; ở đây lời gọi blocking được chạy trên scheduler có giới hạn dành cho công việc có thể chặn. Cách này giúp tránh giữ luồng sự kiện nhạy cảm, nhưng không biến API blocking thành non-blocking. Cần đặt timeout, giới hạn concurrency và xử lý lỗi theo đặc tính của dịch vụ được gọi.

### Ví dụ: xử lý các phần tử trên scheduler song song

Với phép tính CPU-bound độc lập, `parallel` kết hợp `runOn` có thể phân phối các rail trên scheduler song song:

```java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux.range(1, 8)
    .parallel()
    .runOn(Schedulers.parallel())
    .map(ConcurrencyExample::cpuIntensiveCalculation)
    .sequential()
    .subscribe(System.out::println);
```

`parallel()` chia luồng thành các rail; `runOn` chỉ định scheduler thực thi các rail; `sequential()` hợp nhất kết quả trở lại thành Flux. Thứ tự phát kết quả sau khi hợp nhất không nên được giả định là thứ tự đầu vào. Nếu từng phép tính phụ thuộc kết quả trước đó hoặc cập nhật trạng thái dùng chung, việc chia rail có thể làm thay đổi hành vi hoặc tạo lỗi đồng bộ. Chỉ dùng cách này khi công việc đủ độc lập và chi phí chia/hợp luồng nhỏ hơn lợi ích thu được.

## `subscribeOn` và `publishOn` điều khiển luồng ở những điểm khác nhau

Hai toán tử thường gặp trong Reactor là `subscribeOn` và `publishOn`:

| Toán tử | Tác động chính | Cách hiểu khi đọc pipeline |
|---|---|---|
| `subscribeOn(scheduler)` | Điều khiển scheduler dùng cho quá trình subscription và việc bắt đầu phát từ nguồn | Đặt gần nguồn để chỉ rõ nguồn nên bắt đầu chạy ở đâu |
| `publishOn(scheduler)` | Chuyển việc xử lý các tín hiệu downstream kể từ vị trí toán tử | Tạo ranh giới chuyển luồng cho các bước phía sau |

Ví dụ sau minh họa ranh giới đó:

```java
Mono.just("order-17")
    .doOnNext(id -> log("source", id))
    .publishOn(Schedulers.parallel())
    .map(id -> enrichOrder(id))
    .doOnNext(id -> log("after publishOn", id))
    .subscribe();
```

Các bước trước `publishOn` xử lý tín hiệu trên luồng phát upstream; các bước sau nó được lên lịch trên scheduler đã chọn. `publishOn` không buộc mỗi phần tử có một luồng riêng, cũng không đảm bảo một phần tử luôn dùng một luồng mới. Scheduler thường tái sử dụng luồng trong pool.

Nếu đặt `subscribeOn` ở nhiều vị trí, cần nhớ rằng nó tác động đến subscription của nguồn và không tạo ra một ranh giới downstream giống `publishOn`. Trong đa số pipeline, một `subscribeOn` gần nguồn đủ diễn đạt ý định. Có thể kết hợp hai toán tử khi cần điều khiển nơi nguồn bắt đầu và nơi phần downstream tiếp tục, nhưng mỗi ranh giới cần có lý do cụ thể.

## Chọn mô hình thực thi theo loại công việc

| Loại công việc | Đặc điểm | Hướng lựa chọn |
|---|---|---|
| I/O non-blocking | Chờ socket hoặc sự kiện mà không giữ luồng trong lúc chờ | Giữ mô hình event-driven; tránh chuyển scheduler không cần thiết |
| I/O blocking | Lời gọi giữ luồng cho đến khi hoàn tất | Cô lập bằng `boundedElastic` hoặc cân nhắc virtual threads ở kiến trúc phù hợp |
| CPU-bound | Tiêu thụ CPU liên tục, có thể chia thành phần độc lập | Cân nhắc `Schedulers.parallel()` hoặc executor giới hạn theo năng lực CPU |
| Tuần tự theo khóa hoặc trạng thái | Các thao tác phải theo thứ tự hoặc cùng cập nhật một trạng thái | Giữ tuần tự tại ranh giới cần thiết; thiết kế đồng bộ rõ ràng nếu chia sẻ trạng thái |

Đừng chọn scheduler chỉ dựa trên tên. Cần xem tác vụ có blocking không, có tiêu thụ CPU không, có cần giữ thứ tự không và tài nguyên downstream có giới hạn nào. Ví dụ, chuyển hàng nghìn lời gọi blocking sang một pool không giới hạn có thể làm cạn kết nối cơ sở dữ liệu dù số luồng tăng lên. Scheduler chỉ điều phối thực thi; nó không tự cung cấp backpressure ở mọi ranh giới và không thay thế giới hạn concurrency của ứng dụng.

## Các lỗi thiết kế thường gặp

**Đồng nhất bất đồng bộ với song song.** Một API trả về `Mono` hoặc `Flux` không có nghĩa công việc được chạy trên nhiều luồng. Hãy xác định nguồn phát tín hiệu và các ranh giới scheduler trước khi kết luận về luồng thực thi.

**Chặn luồng event loop.** Gọi `block()`, `Thread.sleep()` hoặc thư viện blocking trong một callback chạy trên luồng sự kiện có thể làm đình trệ nhiều yêu cầu. Hãy ưu tiên API non-blocking; nếu phải dùng thư viện blocking, cô lập đúng đoạn gọi và giới hạn số tác vụ đang chạy.

**Tạo quá nhiều luồng hoặc pool.** Mỗi pool có chi phí và giới hạn riêng. Tạo scheduler mới cho từng request khiến việc quản lý vòng đời khó khăn và tiêu tốn tài nguyên. Dùng scheduler dùng chung phù hợp, và quản lý việc dispose nếu ứng dụng tự tạo scheduler.

**Giả định thứ tự khi xử lý song song.** Các phần tử có thể hoàn tất theo thứ tự khác đầu vào. Nếu yêu cầu nghiệp vụ cần thứ tự, chọn toán tử và chiến lược xử lý bảo toàn thứ tự hoặc thiết kế bước sắp xếp/hợp nhất có chủ đích.

**Chia sẻ trạng thái có thể thay đổi.** Nhiều rail hoặc nhiều luồng cùng ghi một `ArrayList`, bộ đếm hay đối tượng mutable có thể gây race condition. Ưu tiên phép biến đổi bất biến, gom kết quả theo pipeline, hoặc dùng cơ chế đồng bộ phù hợp khi thực sự cần chia sẻ.

**Tăng concurrency mà không giới hạn tải.** Nhiều tác vụ đồng thời có thể làm quá tải dịch vụ bên ngoài. Dùng giới hạn concurrency, timeout, retry có kiểm soát và backpressure ở các ranh giới hỗ trợ Reactive Streams.

## Cách quan sát và kiểm chứng

Khi điều tra một pipeline, hãy ghi lại tên luồng tại các điểm quan trọng bằng `Thread.currentThread().getName()` hoặc `doOnNext` kết hợp logging. Đặt log trước và sau `publishOn`, trong nguồn, và trong callback subscription để nhận ra ranh giới chuyển luồng. Với bài toán hiệu năng, đo thời gian chờ, CPU, số tác vụ đang hoạt động, độ dài hàng đợi và độ trễ đầu cuối; chỉ nhìn số luồng không đủ để kết luận hệ thống đang hoạt động tốt.

Một cách kiểm chứng thiết kế hữu ích là bắt đầu từ câu hỏi nghiệp vụ: tác vụ có thể chạy độc lập không, có cần giữ thứ tự không, có blocking không, và tài nguyên bị giới hạn là gì? Sau đó chọn scheduler hoặc giữ nguyên luồng hiện tại, rồi đo hành vi dưới tải đại diện. Kết quả đo mới cho biết việc chuyển scheduler có cải thiện thông lượng hay chỉ tăng chi phí chuyển ngữ cảnh.

## Tự kiểm tra

1. Một ứng dụng gửi đồng thời 100 yêu cầu HTTP non-blocking trên một event loop. Đây có phải là song song không? Giải thích dựa trên số luồng và thời gian chờ.
2. Một phép tính ảnh độc lập được chia thành bốn phần và chạy trên bốn lõi. Đặc điểm nào khiến đây là song song?
3. Vì sao lời gọi JDBC blocking cần được cô lập khỏi luồng sự kiện trong một pipeline reactive?
4. Trong pipeline có `publishOn`, những toán tử downstream chịu ảnh hưởng như thế nào? `subscribeOn` giải quyết điểm nào khác?
5. Khi dùng `parallel()` và `runOn`, vì sao không nên giả định kết quả sẽ phát theo đúng thứ tự đầu vào?

Nếu phân biệt được tác vụ logic với luồng thực thi, đồng thời nhận diện được nơi pipeline chuyển scheduler, bạn có thể chọn mô hình phù hợp cho I/O và tính toán CPU, tránh chặn luồng xử lý sự kiện và kiểm soát tải tốt hơn.
