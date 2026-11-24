# Thời gian

## Kiểm thử hành vi thời gian bằng đồng hồ ảo

Pipeline reactive thường phụ thuộc vào thời gian: một phần tử chỉ được phát sau một khoảng trễ, một luồng định kỳ phát dữ liệu mỗi giây, một yêu cầu bị timeout nếu phản hồi đến quá muộn, hoặc một nhóm sự kiện được gom trong một cửa sổ thời gian. Nếu kiểm thử các hành vi này bằng cách chờ đồng hồ thật, bài kiểm thử sẽ chậm, dễ dao động theo tải máy và khó kiểm soát chính xác thời điểm tín hiệu xuất hiện.

Project Reactor cung cấp cơ chế kiểm thử thời gian ảo (virtual time). Thay vì chờ thời gian thực trôi qua, bài kiểm thử điều khiển một đồng hồ mô phỏng và chủ động tiến đồng hồ đến mốc cần kiểm tra. Kết hợp **StepVerifier.withVirtualTime** với các bước như **thenAwait** và **expectNoEvent**, ta có thể xác minh thời điểm phát tín hiệu, timeout và hoàn tất một cách nhanh, xác định.

### 1. Vì sao cần đồng hồ ảo?

Giả sử một pipeline phát một giá trị sau 30 giây:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;

Mono<Long> delayed =
    Mono.delay(Duration.ofSeconds(30));
~~~

Nếu kiểm thử dùng đồng hồ thật, mỗi lần chạy có thể phải chờ 30 giây. Khi có nhiều bài kiểm thử cho **delay**, **interval**, **timeout** hoặc retry có khoảng chờ, tổng thời gian kiểm thử sẽ tăng đáng kể.

Đồng hồ ảo cho phép bài kiểm thử tiến 30 giây mô phỏng gần như tức thời. Nó không làm thay đổi logic nghiệp vụ của pipeline; nó thay thế cơ chế lập lịch thời gian được sử dụng trong kiểm thử. Vì vậy, ta có thể kiểm tra các mốc thời gian mà không phải dùng **Thread.sleep**.

| Chờ đồng hồ thật | Dùng đồng hồ ảo |
| --- | --- |
| Bài kiểm thử phải chờ thời gian thực | Bài kiểm thử chủ động tiến thời gian mô phỏng |
| Dễ bị ảnh hưởng bởi tải máy và lập lịch thread | Có thể kiểm tra các mốc thời gian xác định |
| Kiểm thử 30 giây có thể mất ít nhất 30 giây | Tiến 30 giây mô phỏng mà không phải chờ 30 giây thực |
| **Thread.sleep** có thể làm bài kiểm thử mong manh | Dùng các bước thời gian của StepVerifier |

### 2. StepVerifier.withVirtualTime tạo đồng hồ ảo

Với Reactor Test, **StepVerifier.withVirtualTime** tạo một StepVerifier có đồng hồ ảo. Nó nhận một supplier trả về Publisher:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
~~~

Trình tự kiểm thử:

1. StepVerifier tạo môi trường thời gian ảo và gọi supplier để lấy Publisher.
2. Subscriber đăng ký vào Mono.
3. **thenAwait(Duration.ofSeconds(5))** tiến đồng hồ mô phỏng thêm năm giây.
4. Mono phát giá trị **0L**.
5. **verifyComplete()** xác nhận luồng kết thúc bình thường.

**Mono.delay** phát một giá trị kiểu **Long** sau khoảng thời gian đã cấu hình. Giá trị đầu tiên là **0L**; nó biểu thị lần phát đầu tiên, không phải số giây đã trôi qua.

### 3. Phải tạo Publisher bên trong supplier

Một quy tắc quan trọng là tạo pipeline có sử dụng scheduler thời gian bên trong supplier truyền cho **withVirtualTime**:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
    Flux.interval(Duration.ofSeconds(1))
        .take(3)
)
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Supplier giúp StepVerifier cài đặt scheduler ảo trước khi pipeline được tạo và đăng ký. Nếu tạo Publisher trước rồi truyền biến đã tạo vào một supplier, các toán tử thời gian có thể đã lấy scheduler thật ở assembly time:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

// Không nên dùng cách này để kiểm thử virtual time.
Flux<Long> ticks =
    Flux.interval(Duration.ofSeconds(1)).take(3);

StepVerifier.withVirtualTime(() -> ticks)
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Ở ví dụ không nên dùng, **ticks** đã được lắp ghép trước khi StepVerifier thiết lập đồng hồ ảo. Các tác vụ có thể vẫn dựa vào scheduler thật, khiến bài kiểm thử chờ lâu hoặc không hoạt động như mong đợi. Hãy đặt toàn bộ phần tạo nguồn và các toán tử phụ thuộc thời gian trong supplier.

### 4. Tiến đồng hồ và xác minh không có tín hiệu

Hai bước thường dùng để điều khiển thời gian:

- **thenAwait(duration):** tiến đồng hồ ảo thêm khoảng thời gian đã chỉ định rồi tiếp tục kiểm tra. Bước này không tự xác nhận rằng trong khoảng đó không có tín hiệu.
- **expectNoEvent(duration):** tiến đồng hồ ảo trong khoảng thời gian và xác nhận không có tín hiệu nào xuất hiện.

Ví dụ kiểm tra một luồng định kỳ chưa phát trước giây đầu tiên:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(2)
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(999))
    .thenAwait(Duration.ofMillis(1))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .verifyComplete();
~~~

**expectSubscription()** được đặt trước **expectNoEvent** vì sự kiện đăng ký cũng là một tín hiệu trong kịch bản kiểm thử. Sau 999 ms mô phỏng, chưa có phần tử nào được phát. Khi tiến thêm 1 ms, phần tử đầu tiên xuất hiện ở mốc một giây. Tiến thêm một giây nữa sẽ nhận phần tử thứ hai và luồng hoàn tất do **take(2)**.

Nếu chỉ muốn kiểm tra trạng thái cuối sau một khoảng thời gian, **thenAwait** thường ngắn gọn hơn. Nếu muốn chứng minh một khoảng thời gian không phát dữ liệu, dùng **expectNoEvent**.

### 5. Kiểm thử delaySubscription

**delaySubscription** trì hoãn thời điểm bắt đầu đăng ký upstream. Có thể dùng virtual time để xác minh nguồn chưa được tiêu thụ trước mốc quy định:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.just("ready")
            .delaySubscription(Duration.ofSeconds(2))
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(1999))
    .thenAwait(Duration.ofMillis(1))
    .expectNext("ready")
    .verifyComplete();
~~~

Trong hai giây đầu, Mono nguồn chưa được subscribe nên chưa phát giá trị. Khi đồng hồ ảo đến mốc hai giây, subscription upstream bắt đầu và giá trị **ready** được phát. Đây là hành vi khác với **delayElements**, vốn trì hoãn các tín hiệu phần tử sau khi nguồn đã được đăng ký; còn **Mono.delay** tự tạo một tín hiệu sau khoảng thời gian cấu hình.

### 6. Kiểm thử timeout

**timeout(duration)** phát lỗi nếu Publisher không phát tín hiệu phù hợp trong khoảng thời gian quy định. Virtual time cho phép kiểm tra ranh giới timeout mà không phải chờ đồng hồ thật:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
            .timeout(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
~~~

Mono nguồn dự kiến phát sau mười giây, nhưng timeout được đặt ở năm giây. Khi đồng hồ ảo tiến đến mốc năm giây, timeout phát lỗi và StepVerifier xác nhận kiểu lỗi. Subscriber không nhận giá trị từ Mono nguồn vì nó chưa phát trước thời hạn.

Nếu pipeline có giá trị dự phòng:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
            .timeout(
                Duration.ofSeconds(5),
                Mono.just(-1L)
            )
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectNext(-1L)
    .verifyComplete();
~~~

Overload này chuyển timeout thành publisher dự phòng. Khi timeout xảy ra, downstream nhận **-1L** rồi hoàn tất bình thường. Đây là một hành vi khác với timeout không có fallback, vốn kết thúc bằng lỗi.

### 7. Kiểm thử luồng bị giới hạn bởi thời lượng

Toán tử **take(Duration)** kết thúc luồng sau khoảng thời gian quy định. Kết hợp với **interval**, ta có thể xác minh những phần tử xuất hiện trước hạn chót:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(200))
            .take(Duration.ofMillis(550))
    )
    .thenAwait(Duration.ofMillis(550))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

Nguồn phát phần tử ở các mốc 200 ms và 400 ms. Luồng kết thúc ở mốc 550 ms, trước lần phát kế tiếp tại 600 ms. Bài kiểm thử xác nhận hai phần tử được phát rồi nhận completion.

Với **buffer(Duration)** hoặc **window(Duration)**, hãy kiểm tra riêng các ranh giới mở và đóng cửa sổ. Nếu một phần tử và timer đóng cửa sổ được lập lịch tại cùng một mốc, thứ tự xử lý có thể ảnh hưởng phần tử thuộc cửa sổ nào. Chia bài kiểm thử thành các bước thời gian nhỏ giúp làm rõ hành vi ở từng ranh giới.

### 8. Dùng VirtualTimeScheduler khi cần scheduler tường minh

**withVirtualTime** thay thế scheduler thời gian mặc định mà Reactor sử dụng cho các toán tử phù hợp. Nếu pipeline truyền một scheduler tường minh vào toán tử, scheduler đó không tự động bị thay thế. Khi muốn kiểm soát scheduler cụ thể, có thể tạo **VirtualTimeScheduler** và truyền trực tiếp vào nguồn:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

VirtualTimeScheduler clock = VirtualTimeScheduler.create();

Flux<Long> ticks =
    Flux.interval(Duration.ofSeconds(1), clock).take(2);

StepVerifier.create(ticks)
    .expectSubscription()
    .then(() -> clock.advanceTimeBy(Duration.ofSeconds(1)))
    .expectNext(0L)
    .then(() -> clock.advanceTimeBy(Duration.ofSeconds(1)))
    .expectNext(1L)
    .verifyComplete();

clock.dispose();
~~~

Ở đây, nguồn nhận trực tiếp đối tượng **clock**, nên bài kiểm thử điều khiển scheduler đó bằng **advanceTimeBy**. Sau khi kiểm thử kết thúc, gọi **dispose()** để giải phóng scheduler ảo.

Cách này phù hợp khi scheduler là một phần rõ ràng của thiết kế và cần được inject để kiểm thử. Trong mã ứng dụng, việc truyền scheduler qua constructor hoặc cấu hình giúp tách logic thời gian khỏi lựa chọn thực thi, đồng thời làm bài kiểm thử dễ điều khiển hơn.

### 9. Những giới hạn cần nhớ

Virtual time rất hữu ích, nhưng không phải mọi hoạt động đều tự động chạy theo đồng hồ ảo:

- Các toán tử thời gian phải sử dụng scheduler được StepVerifier thay thế hoặc scheduler ảo được truyền trực tiếp.
- Nếu truyền **Schedulers.parallel()**, **Schedulers.boundedElastic()** hoặc một scheduler thật vào toán tử, thời gian của scheduler đó không tự động bị tua.
- **Thread.sleep**, lời gọi blocking và tác vụ ngoài Reactor không được tăng tốc bởi virtual time.
- Một API bên ngoài có đồng hồ riêng, timer riêng hoặc thread riêng cần được giả lập hoặc điều khiển độc lập.
- Pipeline cần được tạo trong supplier của **withVirtualTime** nếu dựa vào scheduler mặc định.

Ví dụ, bọc một lời gọi blocking trong **Mono.fromCallable** không khiến nó trở thành tác vụ thời gian ảo. Virtual time điều khiển các tác vụ được lập lịch qua scheduler ảo; nó không tua thời gian hệ điều hành hoặc làm một phương thức blocking kết thúc sớm hơn.

Nếu cần kiểm thử logic dựa vào **Instant.now()** hoặc **System.currentTimeMillis()**, hãy trừu tượng hóa đồng hồ ứng dụng bằng **Clock** của Java và inject một **Clock** cố định trong bài kiểm thử. Reactor virtual time và Java Clock giải quyết hai lớp khác nhau: một bên điều khiển scheduler của pipeline, bên kia điều khiển cách mã nghiệp vụ đọc thời điểm hiện tại.

### 10. Tránh các bài kiểm thử thời gian mong manh

Một số lỗi thường gặp:

| Lỗi | Vì sao có vấn đề? | Cách khắc phục |
| --- | --- | --- |
| Dùng **Thread.sleep** để đợi phần tử | Chậm và phụ thuộc tải máy | Dùng **withVirtualTime** và **thenAwait** |
| Tạo Publisher trước supplier | Toán tử có thể đã giữ scheduler thật | Tạo pipeline bên trong supplier |
| Dùng **expectNoEvent** ngay sau khi bắt đầu | Subscription cũng được xem là một tín hiệu | Gọi **expectSubscription()** trước |
| Nghĩ **thenAwait** xác nhận không có tín hiệu | Bước này chỉ tiến thời gian | Dùng **expectNoEvent** khi cần khẳng định im lặng |
| Truyền scheduler thật tường minh | Scheduler đó không tự được thay thế | Truyền **VirtualTimeScheduler** hoặc dùng scheduler mặc định phù hợp |
| Tăng thời gian quá xa trong một bước | Khó xác định mốc phát hoặc timeout sai | Chia thành các bước thời gian nhỏ và kiểm tra tín hiệu tại từng mốc |
| Dùng virtual time cho API blocking | Đồng hồ ảo không điều khiển lời gọi blocking | Mock API hoặc tách đồng hồ ứng dụng khỏi thao tác I/O |

### 11. Quy trình kiểm thử thời gian

Khi viết một bài kiểm thử cho pipeline có yếu tố thời gian, hãy thực hiện theo trình tự:

1. Xác định toán tử nào tạo timer hoặc dùng scheduler, chẳng hạn **delay**, **interval**, **timeout**, **buffer** hoặc **window**.
2. Xác định scheduler được chọn mặc định hay được truyền tường minh.
3. Tạo Publisher bên trong supplier của **StepVerifier.withVirtualTime** hoặc inject một **VirtualTimeScheduler** cụ thể.
4. Xác nhận subscription trước khi dùng **expectNoEvent**.
5. Tiến đồng hồ theo từng mốc bằng **thenAwait** hoặc **advanceTimeBy**.
6. Kiểm tra phần tử, lỗi và tín hiệu hoàn tất tại đúng mốc.
7. Giải phóng scheduler được tạo thủ công sau kiểm thử.

Trong module REACTIVE_PROGRAMMING, kiểm thử bằng đồng hồ ảo giúp xác minh các pipeline thời gian mà không phụ thuộc thời gian chờ thực. Khi kết hợp đúng với StepVerifier, scheduler và cách lắp ghép Publisher, ta có thể kiểm tra delay, interval, timeout và các cửa sổ thời gian nhanh, ổn định và dễ đọc.
