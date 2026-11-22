# Lan truyền cancel khi bên nhận không cần thêm dữ liệu

**Bối cảnh:** Spring Framework – Reactive, chương **Hủy và tài nguyên**. Bài này tập trung vào cơ chế **cancellation** trong Project Reactor: khi subscriber hoặc một operator phía downstream không muốn nhận tiếp dữ liệu, tín hiệu `cancel()` được truyền ngược dòng như thế nào, tại sao không được đồng nhất hủy subscription với dừng ngay mọi công việc, và cách giải phóng tài nguyên đúng trong Spring WebFlux.

## 1. Vì sao cần cancel?

Trong một pipeline reactive, downstream có thể không còn cần dữ liệu trước khi nguồn kết thúc tự nhiên. Ví dụ:

- Người dùng đóng trang đang xem Server-Sent Events (SSE), WebSocket hoặc luồng stream.
- Bộ xử lý chỉ cần ba phần tử đầu tiên của một `Flux` có hàng nghìn phần tử.
- Một truy vấn tìm kiếm mới xuất hiện, khiến kết quả của truy vấn trước không còn hữu ích.
- Một request bị timeout, hoặc subscriber quyết định hủy do người dùng ngắt thao tác.
- Một stream giữ kết nối tới nguồn sự kiện lâu dài và cần dừng khi khách hàng không còn lắng nghe.

Nếu vẫn tiếp tục tải dữ liệu, tạo timer, giữ connection hoặc chạy công việc không ai cần, hệ thống sẽ lãng phí CPU, bộ nhớ, network, thread và tài nguyên upstream. **Cancellation** giúp downstream thông báo: “Tôi không còn cần phần dữ liệu tiếp theo của subscription này; hãy cố gắng dừng công việc liên quan”.

Trong Reactive Streams, tín hiệu hủy được gửi bằng phương thức **`Subscription.cancel()`**. Trong Reactor, nhiều API thuận tiện cuối cùng dẫn tới điều tương tự, ví dụ `Disposable.dispose()` trên subscription được trả về bởi một số overload `subscribe(...)`, `BaseSubscriber.cancel()` hoặc một operator tự hủy nguồn khi đã đạt mục tiêu.

**Điểm cốt lõi:** cancel là **tín hiệu điều khiển trên subscription**, không phải yêu cầu rollback nghiệp vụ có xác nhận, không phải cách làm cho HTTP server hay database bắt buộc ngừng ngay, và cũng không tự phát `onComplete()` cho nguồn đã bị hủy.

## 2. Hai chiều trong pipeline: dữ liệu đi xuống, cancel đi lên

Một pipeline Reactor có thể hình dung:

```text
                       HƯỚNG TÍN HIỆU DỮ LIỆU
Publisher A --> map --> filter --> take(3) --> Subscriber cuối
      |         |          |          |               |
      |       onNext ---- onNext ---- onNext -------> nhận 1, 2, 3
      |                                              |
      +---------------- cancel() <-------------------+
                       HƯỚNG ĐIỀU KHIỂN
```

Nguồn phát `onNext(value)`, `onComplete()` hoặc `onError(error)` về downstream. Ngược lại, downstream dùng `Subscription.request(n)` để xin thêm số phần tử được phép phát, hoặc `Subscription.cancel()` để nói không cần tiếp tục.

Mỗi operator có thể đóng hai vai trò:

1. **Subscriber của upstream:** nhận `onSubscribe`, các `onNext` và tín hiệu kết thúc từ operator phía trước.
2. **Publisher của downstream:** cung cấp subscription cho operator phía sau và nhận `request(n)`/`cancel()` từ phía sau.

Khi nhận `cancel()`, operator thông thường chuyển thông báo hủy tới subscription upstream của nó và làm các bước dọn dẹp cần thiết. Trong chuỗi ghép, một operator có thể đồng thời hủy **nhiều inner subscriptions** hoặc tác vụ đã được lên lịch. Chi tiết phụ thuộc loại operator và trạng thái thực tế.

### 2.1. Cancel khác với hết demand

| Trạng thái | Ý nghĩa | Có thể tiếp tục nhận dữ liệu về sau? |
| --- | --- | --- |
| Đã gọi `request(2)` và nhận đủ hai phần tử, outstanding demand bằng 0 | Hiện chưa cho phép thêm `onNext` | Có, nếu còn subscription và gọi `request(n)` thêm |
| Subscriber gọi `cancel()` | Không còn muốn tiếp tục subscription đó | Không được dựa vào subscription đã hủy để xin thêm |
| Publisher phát `onComplete()` | Nguồn kết thúc thành công | Không, subscription đã kết thúc |
| Publisher phát `onError(error)` | Nguồn kết thúc bằng lỗi | Không, subscription đã kết thúc |
| Một operator `take(3)` nhận đủ ba phần tử | Operator gửi complete xuống downstream và hủy nguồn phía trước nếu còn hoạt động | Downstream hoàn tất; upstream có thể thấy cancel |

**Không gọi `request(0)` như một lệnh cancel hoặc pause.** `request(n)` yêu cầu giá trị dương; request không hợp lệ là lỗi giao thức Reactive Streams. Nếu chỉ tạm thời chưa sẵn sàng, không xin thêm phần tử. Nếu quyết định kết thúc hẳn, dùng `cancel()`.

### 2.2. Cancel là per-subscription

Một `Flux` lạnh có thể được subscribe nhiều lần:

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
Disposable first = ticks.subscribe(System.out::println);
Disposable second = ticks.subscribe(System.out::println);

// Khi không cần subscriber thứ nhất nữa:
first.dispose();
```

Đây là **mã minh họa**, cần import `Duration`, `Disposable` và `Flux`; không phải class chạy độc lập. Với `Flux.interval` thông thường, mỗi lần subscribe tạo subscription/lịch phát riêng. Hủy `first` không có nghĩa `second` bị hủy.

Nếu publisher đã được **chia sẻ hoặc cache** (ví dụ có `share()`, `publish().refCount(...)`, `cache()` hoặc hot sink), hủy một downstream subscription có thể không dừng nguồn chung khi subscriber khác vẫn cần dữ liệu. Cần hiểu contract của operator chia sẻ nguồn; **cancel không có nghĩa “đóng tất cả subscriber và mọi tài nguyên toàn cục”**.

## 3. Cancel lan truyền ra sao khi `take(n)` nhận đủ dữ liệu?

Giả sử nguồn có mười phần tử, nhưng downstream chỉ cần ba:

```java
Flux<Integer> firstThree = Flux.range(1, 10)
        .take(3);
```

Khi subscriber thực sự yêu cầu và nhận đủ ba phần tử, `take(3)` không cần thêm phần tử từ upstream:

1. Upstream phát 1, 2, 3 theo demand hợp lệ.
2. `take(3)` chuyển tiếp ba phần tử đó cho downstream.
3. Nó thông báo hủy subscription upstream vì không còn cần 4..10.
4. Phía downstream thấy **kết thúc bình thường** qua `onComplete()` sau ba phần tử.

Diễn tiến khái niệm:

```text
Source                    take(3)                  Subscriber
  | onNext(1) -------------->| onNext(1) ------------->|
  | onNext(2) -------------->| onNext(2) ------------->|
  | onNext(3) -------------->| onNext(3) ------------->|
  |<------------- cancel() ---|                         |
  |                           | onComplete() ---------->|
```

**Một pipeline có thể đồng thời có hai kiểu kết thúc ở hai vị trí khác nhau:**

- **Trước `take(3)`:** upstream nhận `cancel()`, nên hook đặt trước `take` có thể quan sát `SignalType.CANCEL`.
- **Sau `take(3)`:** downstream nhận `onComplete()`, nên hook đặt sau `take` có thể quan sát `SignalType.ON_COMPLETE`.

Đây không phải mâu thuẫn: `take` chủ động kết thúc output của chính nó sau khi đạt đủ số lượng và không còn cần input.

**Lưu ý:** việc giới hạn kết quả bằng `take(n)` không nhất thiết làm mọi upstream operator chỉ yêu cầu đúng `n` phần tử trong mọi cấu hình. Prefetch, queue và các operator trung gian có thể thay đổi request; cancellation vẫn nhằm chặn công việc không cần tiếp tục. Nếu nguồn đã phát một số tín hiệu vào buffer, chúng có thể bị loại bỏ khi hủy.

### 3.1. Các operator có thể kích hoạt hủy nguồn

| Nguyên nhân | Cơ chế điển hình | Downstream thấy điều gì? |
| --- | --- | --- |
| `take(n)` đã nhận đủ `n` phần tử | Hủy upstream đang active | Nhận `n` phần tử rồi hoàn thành bình thường |
| `next()` áp dụng cho `Flux<T>` | Lấy phần tử đầu và bỏ phần còn lại bằng cách hủy upstream | `Mono<T>` có tối đa một phần tử, rồi complete |
| `switchMap(...)` có outer item mới | Hủy inner publisher cũ, subscribe inner mới | Stream chính tiếp tục, chỉ inner mới được theo dõi |
| Downstream gọi `cancel()` hoặc `dispose()` | Truyền hủy ngược qua operator chain | Không đòi hỏi upstream gửi `onComplete`/`onError` sau hủy |
| `timeout(...)` hết thời gian | Hủy nguồn đang chờ; có thể chuyển sang error hoặc fallback | Thường là `onError` timeout hoặc dữ liệu fallback, tùy cấu hình |
| HTTP/SSE client disconnect | WebFlux/adapter có thể hủy publisher response | Nguồn cố dừng theo lifecycle subscription; thời điểm phụ thuộc transport |
| Một `flatMap` bên ngoài bị hủy | Operator thường hủy những inner subscriptions còn active | Không dùng thêm kết quả của các công việc bị hủy |

Khi một operator hoàn thành bình thường trước khi nguồn đã kết thúc, tín hiệu mà **source** quan sát có thể khác tín hiệu mà **consumer cuối** nhìn thấy. Hãy đặt log ở cả hai phía operator quan trọng thay vì đoán.

## 4. Ví dụ Java 17+ chạy độc lập: downstream hủy và tài nguyên được đóng

Ví dụ có hai phần:

- **Hủy chủ động:** `BaseSubscriber` xin từng phần tử của `Flux.range(1,10)`, sau khi nhận 3 giá trị thì gọi `cancel()`.
- **Hủy do operator:** `take(2)` nhận hai giá trị từ một source gắn với resource; `Flux.using(...)` đóng resource khi không cần nữa.

Chương trình không có scheduler, HTTP hoặc network, vì vậy kết quả không phụ thuộc thời gian xử lý.

Tạo tệp `src/main/java/demo/CancellationPropagationDemo.java`:

```java
package demo;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class CancellationPropagationDemo {

    static final class FakeCursor implements AutoCloseable {
        private final AtomicInteger closeCount;

        FakeCursor(AtomicInteger closeCount) {
            this.closeCount = closeCount;
        }

        @Override
        public void close() {
            closeCount.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        AtomicInteger cancelCalls = new AtomicInteger();
        AtomicInteger sourceCompletes = new AtomicInteger();
        List<Integer> received = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 10)
                .doOnCancel(() -> cancelCalls.incrementAndGet())
                .doOnComplete(() -> sourceCompletes.incrementAndGet());

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                received.add(value);
                if (received.size() == 3) {
                    cancel();
                } else {
                    request(1);
                }
            }
        };

        source.subscribe(subscriber);

        System.out.println("received = " + received);
        System.out.println("source cancel calls = " + cancelCalls.get());
        System.out.println("source completes = " + sourceCompletes.get());

        AtomicInteger closeCount = new AtomicInteger();

        List<Integer> firstTwo = Flux.using(
                    () -> new FakeCursor(closeCount),
                    resource -> Flux.range(10, 5),
                    FakeCursor::close
                )
                .take(2)
                .collectList()
                .block(Duration.ofSeconds(3));

        System.out.println("take values = " + firstTwo);
        System.out.println("cursor closes = " + closeCount.get());
    }
}
```

**Điều kiện chạy:** Java 17+, `io.projectreactor:reactor-core` cùng `org.reactivestreams:reactive-streams` tương thích. Dự án Spring Boot có `spring-boot-starter-webflux` thông thường đã có các dependency liên quan. Nếu đã có dự án, chạy trực tiếp hàm `main` từ IDE.

Để biên dịch thủ công, đặt hai thư viện cần thiết vào `lib/` rồi chạy từ thư mục chứa `src/`:

```bash
# Linux/macOS
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/CancellationPropagationDemo.java
java -cp "out:lib/*" demo.CancellationPropagationDemo
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/CancellationPropagationDemo.java
java -cp "out;lib/*" demo.CancellationPropagationDemo
```

**Stdout chính xác của ví dụ đồng bộ này:**

```text
received = [1, 2, 3]
source cancel calls = 1
source completes = 0
take values = [10, 11]
cursor closes = 1
```

Phân tích:

1. Khi subscribe, `BaseSubscriber` gửi `request(1)`. Sau mỗi phần tử đầu, nó gửi thêm một request. Sau phần tử thứ ba, nó gọi `cancel()` thay vì xin tiếp.
2. `doOnCancel(...)` đặt **trước subscriber, gần source** nhận đúng một tín hiệu cancel; `doOnComplete(...)` không chạy vì nguồn chưa hoàn thành tự nhiên.
3. Sau khi subscribe của nguồn đồng bộ kết thúc, danh sách chỉ có 1, 2, 3. Không có nhu cầu tiếp nên nguồn không tiếp tục phát 4..10.
4. `Flux.using(...)` tạo `FakeCursor` **cho subscription** và đăng ký cleanup `FakeCursor::close`. `take(2)` nhận 10 và 11, hủy upstream, nên resource được đóng.
5. `collectList().block(...)` chỉ được dùng ở **ranh giới chương trình dòng lệnh** để chờ dữ liệu và in kết quả. Trong WebFlux controller/event-loop không dùng `block()` để lấy dữ liệu đồng bộ.

Ví dụ trên chứng minh **cancellation ở cấp subscription** và cleanup khi nguồn được cắt ngắn. Nó không chứng minh một HTTP request xa, truy vấn JDBC hoặc tác vụ CPU đang chạy có thể bị buộc dừng ngay.

## 5. Chú ý thời điểm thực sự xảy ra hủy

### 5.1. Hủy là yêu cầu dừng, không phải xác nhận dừng tức thì

Reactive Streams yêu cầu `cancel()` là tín hiệu dừng subscription, nhưng việc thực thi có thể đang diễn ra trên thread khác. Tùy nguồn, một phần tử đã được tính toán hoặc đang trên đường chuyển tới downstream vào đúng lúc hủy. Một số nguồn đồng bộ còn có thể hoàn tất rất nhanh trước khi người gọi có cơ hội hủy.

Các trường hợp điển hình:

- Nguồn synchronous `Flux.range(...)` có thể dừng sớm dễ dàng khi nhận cancel trong vòng phát dữ liệu.
- `Flux.interval(...)` có thể hủy lịch phát/timer của subscription còn active.
- `WebClient` có thể hủy việc chờ response và hỗ trợ giải phóng tài nguyên client tùy HTTP connector.
- JDBC/SDK blocking có thể không đáp ứng cancellation ngay, hoặc không thể dừng đoạn code đang chờ.
- HTTP server nhận request từ trước có thể đã xử lý xong việc ghi dù client không còn chờ response.
- Hot source hoặc `Sinks.Many` có thể tiếp tục sinh sự kiện cho subscriber khác; hủy một người nhận không buộc nguồn toàn cục ngừng.

Do đó cần phân biệt **đã phát tín hiệu cancel**, **đã nhận cancel tại upstream subscription**, **đã giải phóng tài nguyên cục bộ**, và **công việc phía hệ thống ngoài thực sự dừng**. Đó là bốn sự kiện có thể xảy ra ở các thời điểm khác nhau.

### 5.2. Cancel không tự tạo `onError` hay `onComplete` tại upstream

Một subscription bị cancel không bắt buộc phát tín hiệu kết thúc để xác nhận. `onErrorResume(...)` cũng không phải hook mặc định cho cancellation, vì cancel **không phải một `onError`**.

Ví dụ về vị trí quan sát:

```java
Flux<Integer> output = Flux.range(1, 10)
        .doFinally(signal ->
                System.out.println("upstream: " + signal))
        .take(3)
        .doFinally(signal ->
                System.out.println("downstream: " + signal));
```

Đây là **đoạn mã minh họa**, chỉ có ý nghĩa sau khi một subscriber yêu cầu đủ phần tử. Phía trước `take` thường thấy `SignalType.CANCEL`, còn phía sau `take` thấy `SignalType.ON_COMPLETE`. Không cố định **thứ tự xuất hiện của log doFinally**: Reactor có thể thực hiện callback cuối sau khi terminal signal đã đi xuống downstream, và khi có scheduling nhiều thread các log còn xen kẽ.

Nếu một nguồn phát tự nhiên hết mười phần tử trước khi bị hủy, nó sẽ đi theo đường completion thay vì cancellation. Nếu có lỗi trước thời điểm hủy, pipeline có thể nhận error. Tình trạng thực tế phụ thuộc thứ tự các sự kiện.

## 6. Chọn hook phù hợp để quan sát cancellation

Reactor cung cấp nhiều toán tử quan sát lifecycle. Chúng có công dụng khác nhau:

| Hook | Thời điểm quan sát | Có chạy khi cancel? | Lưu ý |
| --- | --- | --- | --- |
| `doOnSubscribe(...)` | Subscription mới được gắn | Không phải hook kết thúc | Để ghi nhận bắt đầu vòng đời |
| `doOnRequest(...)` | Downstream gửi demand | Không thay thế cancel | Theo dõi số lượng yêu cầu tại đúng điểm đặt |
| `doOnNext(...)` | Có phần tử được phát qua điểm đo | Không nhất thiết | Không chạy nếu chưa có phần tử |
| `doOnCancel(...)` | Subscription tại điểm đó bị cancel | Có | Không đồng nghĩa upstream đã đóng tài nguyên xa |
| `doFinally(signal -> ...)` | Sau complete/error/cancel của subscription | Có, với `SignalType.CANCEL` | Phù hợp metrics, logging và phân loại kết thúc |
| `doOnComplete(...)` | Upstream hoàn thành bình thường | Không cho cancel thuần túy | Có thể chạy ở downstream sau `take` nhưng không chạy ở source bị cancel |
| `doOnError(...)` | Upstream phát error | Không cho cancel thuần túy | Không dùng để bắt hành vi người dùng rời trang |
| `doOnTerminate(...)` | Complete hoặc error | Không | Khác với `doFinally` |
| `doOnDiscard(...)` | Operator có hỗ trợ bỏ phần tử khỏi buffer | Hữu ích trong một số đường hủy | Chỉ có hiệu lực ở các operator có discard support, không phải hook chung mọi phần tử |

**Vị trí đặt hook quan trọng ngang với loại hook.** Nếu muốn biết nguồn HTTP, database hoặc timer **được yêu cầu hủy**, đặt `doOnCancel` gần publisher nguồn; nếu muốn biết request WebFlux kết thúc theo lý do nào, đặt `doFinally` ở ranh giới response.

Ví dụ logging trong service:

```java
return source
        .doOnSubscribe(s -> metrics.streamStarted())
        .doOnCancel(() -> metrics.sourceCancelled())
        .doFinally(signal -> metrics.streamFinished(signal));
```

Đây là mã **minh họa**; `source` và `metrics` do ứng dụng định nghĩa. `doFinally` có thể thực thi **sau khi downstream đã nhận terminal signal**. Nếu đo bằng counter rồi gọi `block()` và kiểm tra ngay sau đó, callback `doFinally` có thể chưa được quan sát; hãy dùng đồng bộ/test phù hợp, không khẳng định thứ tự không được bảo đảm.

### 6.1. `doOnCancel` và `doFinally` không phải cơ chế quản lý tài nguyên đầy đủ

Dùng `doFinally` để đóng resource có thể làm logic cleanup phụ thuộc thứ tự callbacks, lỗi trong callback hoặc khả năng truy cập resource được chia sẻ bởi nhiều subscriber. Nếu một resource được **mở lúc assembly** rồi gắn chung cho nhiều subscription, cancel ở một subscriber có thể đóng nhầm resource mà người khác đang sử dụng.

Với resource có vòng đời gắn với **mỗi subscription**, nên ưu tiên `Flux.using(...)` hoặc `Mono.using(...)` cho cleanup đồng bộ, và `usingWhen(...)` cho cleanup bất đồng bộ. Các toán tử này biểu đạt rõ “mở resource → tạo publisher dùng resource → đóng khi hoàn thành, lỗi hoặc cancel”.

## 7. Giải phóng tài nguyên bằng `using` và `usingWhen`

### 7.1. Vì sao `try/finally` quanh việc return publisher có thể sai?

Đoạn sau **sai về lifecycle** nếu pipeline thực thi lazy:

```java
Reader reader = openReader();
try {
    return Flux.fromStream(reader.lines());
} finally {
    reader.close();
}
```

Đây là mã minh họa: `openReader()` và xử lý checked exceptions chưa được định nghĩa. Vấn đề là code Java xây dựng publisher và **đóng reader ngay khi return**, trong khi subscriber thường chỉ đọc dữ liệu **về sau**. Publisher có thể bị subscribe khi resource đã đóng.

Thay vì vậy, hãy để tài nguyên được tạo **mỗi lần subscribe** và cleanup gắn với đúng subscription:

```java
return Flux.using(
        () -> openReader(),
        reader -> Flux.fromStream(reader.lines()),
        reader -> closeReader(reader));
```

Đây cũng là mã minh họa, cần định nghĩa `openReader`/`closeReader`, xử lý IOException và chọn scheduler phù hợp. Với reader blocking, chỉ dùng khi đã cân nhắc cô lập I/O khỏi Netty event-loop, ví dụ tại ranh giới legacy dùng `Schedulers.boundedElastic()`. **Sự hiện diện của `Flux.using` không tự biến File I/O/JDBC thành non-blocking.**

Khi subscriber cancel giữa chừng, `using` thực hiện disposer theo contract để không giữ reader/cursor/socket vĩnh viễn. Trong ví dụ hoàn chỉnh ở mục 4, `FakeCursor` được đóng đúng một lần dù `Flux.range` gốc chưa phát hết.

### 7.2. `usingWhen` cho cleanup bất đồng bộ

Khi resource được mở/đóng qua publisher bất đồng bộ (ví dụ một kết nối reactive), `Flux.usingWhen(...)`/`Mono.usingWhen(...)` giúp quản lý resource theo đường kết thúc:

```java
Flux<Result> stream = Flux.usingWhen(
        acquireResource(),
        resource -> readResults(resource),
        resource -> asyncClose(resource),                  // complete
        (resource, error) -> asyncCleanupOnError(resource), // error
        resource -> asyncCleanupOnCancel(resource)          // cancel
);
```

Đây là **mã minh họa có kiểu và hàm giả định**, không phải class Java độc lập. Các hàm cleanup phải trả `Publisher<?>`, và từng path cần quyết định hành vi của resource thực tế.

Ý nghĩa:

- **Complete:** công việc bình thường kết thúc, cleanup theo nhánh hoàn tất.
- **Error:** nguồn lỗi, cleanup theo nhánh lỗi (có thể cần rollback giao dịch hoặc đóng kết nối tùy contract).
- **Cancel:** downstream không cần nữa, **nhánh cleanup riêng** có thể trả về publisher để giải phóng resource hoặc hủy transaction theo API được hỗ trợ.

Cần thiết kế cleanup idempotent, giới hạn timeout và log/metrics cho lỗi dọn dẹp. Trong môi trường process crash hoặc kết nối mạng bị cắt hoàn toàn, không thể hứa mọi cleanup publisher sẽ luôn chạy đến cùng. Với dữ liệu giao dịch, đòi hỏi recovery, timeout phía server, transaction semantics và cơ chế bảo đảm bổ sung.

**Không đồng nhất cancel với rollback.** Cancel ở tầng Reactor không thể tự hoàn tác lệnh ghi database đã commit hoặc lệnh HTTP tạo resource đã được server nhận và thực hiện.

### 7.3. Callback-based source với `Flux.create`

Một nguồn push từ callback có thể không biết gì về Reactive Streams. Adapter viết bằng `Flux.create(sink -> ...)` cần cân nhắc:

- Dùng `sink.onCancel(...)` để yêu cầu hủy đăng ký listener hoặc ngừng nhận callback khi downstream cancel.
- Dùng `sink.onDispose(...)` cho cleanup khi complete/error/cancel; khi đã dùng cả hai, tránh dọn tài nguyên hai lần và đảm bảo cleanup an toàn.
- Kiểm soát nguồn đẩy nhanh bằng overflow strategy, buffer giới hạn, drop/error hoặc cơ chế dừng producer thực sự nếu API cho phép.
- Không tiếp tục đẩy event vô hạn vào sink đã hủy, không giữ closure tham chiếu tới request và tài nguyên đã hết vòng đời.

Trong Reactor, `onCancel` của sink chạy riêng cho trường hợp hủy; `onDispose` dùng cho nhiều kiểu kết thúc. Nếu dùng cả hai, callback cancel diễn ra trước dispose. Khi nguồn không thể pause, cleanup chỉ dừng delivery về subscriber, còn producer bên ngoài vẫn cần được quản lý riêng.

## 8. Cancel trong Spring WebFlux: khách hàng đóng SSE/HTTP stream

Spring WebFlux thường nhận một `Mono`/`Flux` được **return từ handler**, rồi framework subscribe vào publisher theo vòng đời HTTP. Một ví dụ SSE:

Tệp `src/main/java/demo/HeartbeatController.java`, dùng Java 17+ trong ứng dụng Spring Boot có `spring-boot-starter-webflux`:

```java
package demo;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@RestController
public class HeartbeatController {

    @GetMapping(value = "/heartbeat",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> heartbeat() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(n -> ServerSentEvent.<String>builder()
                        .id(Long.toString(n))
                        .event("heartbeat")
                        .data("tick-" + n)
                        .build())
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        System.out.println("SSE subscription cancelled");
                    }
                });
    }
}
```

**Cách sử dụng:** đặt controller trong package được Spring Boot component scan, chạy server và gọi `curl -N http://localhost:8080/heartbeat` (giả sử server cổng 8080). Mỗi giây, publisher có thể phát một event với dữ liệu tương ứng. Dùng Ctrl+C để ngắt client.

**Không có stdout hủy bảo đảm ở một thời điểm chính xác**: phát hiện disconnect còn phụ thuộc server, Netty, TCP, flush và scheduler. Khi WebFlux phát hiện response subscription không còn được sử dụng, nó thường cancel subscription; `doFinally(SignalType.CANCEL)` có thể ghi log. Việc đóng trình duyệt không phải lời gọi đồng bộ ngay vào Java method của controller.

Một số chi tiết quan trọng:

1. **Mỗi HTTP request có một subscription:** `Flux.interval(...)` tạo timer tương ứng; hủy một response thường dọn timer subscription ấy mà không tự hủy response của người khác.
2. **Controller return publisher:** đừng tự gọi `.subscribe()` ở đây rồi return `Mono.just("ok")`, vì làm mất sự liên kết giữa vòng đời HTTP và tác vụ.
3. **Cancel từ transport không phải cancel nghiệp vụ:** nếu event stream đã kích hoạt ghi dữ liệu ở hệ thống ngoài, việc client disconnect không bảo đảm ghi đó bị dừng.
4. **Buffer và flush:** event có thể đã được serialize/queued dù subscriber hủy; không khẳng định mọi byte còn ở network sẽ biến mất tức thì.
5. **Lỗi và complete khác cancel:** trên một SSE stream không giới hạn, việc người dùng ngắt thường liên quan tới cancellation; nhưng timeout, exception hoặc policy server có thể tạo các loại termination khác.

### 8.1. Tại sao HTTP endpoint độc lập không tự cancel lẫn nhau?

Nếu frontend gọi lần lượt `GET /search?q=a` và `GET /search?q=ab`, chúng thường là **hai HTTP requests với hai subscription độc lập**. Server không tự biết kết quả của lần trước đã lỗi thời, nên lần thứ hai không tự gửi cancel cho lần đầu.

Muốn hành vi **latest wins**, tầng điều phối phải chủ động hủy request/subscription cũ hoặc dùng một stream sự kiện chung với operator như `switchMap`. Khi `switchMap` nhận item mới, nó cancel **inner subscription trước đó**, nhưng không phải một rollback đảm bảo cho backend đã nhận request. Cần phân biệt hủy xử lý client, hủy subscribe HTTP và hủy công việc tại server.

## 9. Cancel liên quan đến `flatMap`, `switchMap` và publisher con

Một pipeline có thể gồm nhiều publisher hoạt động đồng thời. Downstream cancel không chỉ dừng nguồn outer; các operator ghép publisher thường phải chuyển cancel tới những **inner subscriptions còn active**.

### 9.1. `flatMap`

Với `ids.flatMap(id -> remoteClient.fetch(id), concurrency)`, nhiều inner request có thể chạy song song trong giới hạn cho phép. Khi subscriber cuối cancel, `flatMap` không còn cần kết quả nên yêu cầu hủy các inner còn active và ngừng nhận thêm dữ liệu.

Nhưng một request đã đến server có thể tiếp tục tiêu thụ CPU/database; vì vậy vẫn cần timeout, connection pool, giới hạn concurrency và cơ chế idempotency. Không dùng cancellation để thay thế capacity planning.

### 9.2. `switchMap`

Khi `switchMap` nhận giá trị outer mới, nó hủy **inner cũ** để ưu tiên inner mới. Đây là hủy theo **ý định mới**, khác với downstream hủy toàn bộ stream. Outer subscription vẫn có thể tiếp tục nhận những lần thay đổi sau.

Ví dụ tìm kiếm trực tiếp: từ khóa mới khiến HTTP request cũ không còn đáng chờ. Tuy nhiên mọi kết quả **đã phát xuống trước thời điểm switch** không thể bị rút lại; và server từ xa có thể vẫn xử lý truy vấn cũ dù client ngừng chờ.

### 9.3. `timeout`

Nếu một nguồn chờ quá lâu, `timeout(Duration)` có thể hủy subscription nguồn ban đầu. Ở phía sau operator, người nhận thường thấy một lỗi timeout, hoặc một fallback publisher nếu được cấu hình. Nói cách khác:

- **Nguồn trước timeout:** nhận cancel vì không còn chờ nữa.
- **Downstream sau timeout:** có thể nhận `onError(TimeoutException)` hoặc kết quả fallback.

Không suy luận “timeout luôn tương đương khách hàng chủ động cancel”; đó là **chính sách operator** và tín hiệu downstream có thể khác.

### 9.4. `retry` và `repeat`

Retry thường tái đăng ký vào publisher lạnh sau lỗi; repeat thường tái đăng ký sau complete theo contract. Cancellation ngăn pipeline tiếp tục công việc không còn cần thiết, nhưng không hoàn tác các lần subscription trước đã gửi HTTP/DB request. Với side effect, phải có idempotency, audit và số lần retry được giới hạn.

## 10. Backpressure khác cancellation như thế nào?

Cả `request(n)` và `cancel()` đi từ downstream về upstream, nhưng chúng trả lời hai câu hỏi khác nhau:

- `request(n)`: **“Tôi còn muốn dữ liệu; hiện có khả năng nhận thêm n phần tử.”**
- `cancel()`: **“Tôi không muốn dữ liệu của subscription này nữa.”**

Nếu subscriber chỉ hết outstanding demand, nguồn tuân thủ Reactive Streams ngừng phát thêm `onNext` cho tới khi có request mới. Nhưng **subscription vẫn sống**, resource hoặc timer có thể tiếp tục tồn tại, một thao tác remote có thể vẫn đang chờ. Cancel mới diễn đạt quyết định chấm dứt việc tiêu thụ subscription.

Ví dụ một consumer chỉ cần ảnh đại diện đầu tiên từ `Flux<Image>`: dùng `next()` hoặc `take(1)` để hủy phần còn lại khi có ảnh phù hợp. Nếu consumer cần đọc toàn bộ danh sách nhưng làm chậm để xử lý từng lô, dùng demand/backpressure, không cancel sau mỗi lô rồi subscribe lại nếu việc tái đăng ký gây tốn kém hoặc mất vị trí.

**Không dùng `onBackpressureDrop()` thay cho cancel.** Drop là chính sách bỏ bớt phần tử khi không theo kịp demand; cancel là dừng subscription. Trong xử lý giao dịch, drop có thể làm mất nghiệp vụ còn cancellation của một request có thể chỉ là dừng chờ response.

## 11. Tài nguyên đặc biệt: bộ đệm, I/O, transaction và công việc bên ngoài

### 11.1. Bộ đệm có reference count

Spring WebFlux/Netty có thể làm việc với `DataBuffer` được cấp từ vùng nhớ dùng reference counting. Khi cancel khiến các phần tử đã được tạo nhưng chưa chuyển tới downstream bị bỏ, cần bảo đảm buffer được release theo contract của operator/adapter. Trong những pipeline tùy chỉnh, có thể cân nhắc `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` tại vị trí hỗ trợ discard, nhưng **không được tự giải phóng một buffer vẫn đang được sở hữu hoặc đã release**.

Quy tắc quan trọng: không mặc định mọi operator tự động release mọi buffer do ứng dụng tạo, cũng không gắn `release` tùy tiện gây double-release. Kiểm tra contract của `DataBufferUtils`, Reactor discard support và HTTP codec tương ứng với version đang sử dụng.

### 11.2. Blocking I/O và virtual threads

Nếu pipeline chứa `Mono.fromCallable(() -> legacyJdbcCall())` chạy trên `Schedulers.boundedElastic()`, tín hiệu cancel tới subscription không bảo đảm JDBC/driver đang chặn sẽ dừng ngay. Chạy trên virtual thread cũng không thay đổi đặc tính nghiệp vụ đó: thread nhẹ hơn trong nhiều tình huống I/O waiting, nhưng SQL đã gửi tới DB vẫn có lifecycle của DB và connection pool.

Cần sử dụng timeout ở đúng lớp, driver cancellation nếu có, thời gian sống connection và giới hạn concurrency. Nếu API blocking không hỗ trợ interrupt, cleanup cần tính tới trường hợp tác vụ vẫn hoàn tất sau khi downstream rời đi.

### 11.3. Transaction và ghi dữ liệu

Ví dụ nguy hiểm:

1. Client gửi lệnh tạo đơn hàng.
2. Backend bắt đầu transaction, ghi bản ghi hoặc gửi sự kiện.
3. Client đóng tab hoặc network ngắt, subscription bị cancel.
4. Backend có thể đã commit hoặc vẫn tiếp tục xử lý; client không nhận được response.

Không được suy ra “cancel nghĩa là chưa tạo đơn”. Lệnh retry từ client có thể tạo trùng nếu không có **idempotency key**, unique constraint hoặc quy tắc xác nhận trạng thái. Với reactive transaction, cancellation và rollback/cleanup cần kiểm tra contract của transaction manager và publisher, nhất là khi dùng `usingWhen` để quản lý vòng đời resource.

### 11.4. Tài nguyên chia sẻ và nhiều subscriber

Nếu một `Flux` dùng `share()`, `cache()` hoặc một hot sink phục vụ nhiều người nhận, cancel một subscriber có thể chỉ gỡ subscriber đó. Nguồn vẫn chạy vì người khác cần hoặc vì thiết kế nguồn nóng. Việc đóng socket chung khi một subscriber rời đi có thể làm hỏng stream của các subscriber còn lại.

Resource cần **ownership rõ ràng**: per-subscription, per-request, per-user-session hay shared application-wide. Chỉ hủy/đóng tài nguyên thuộc đúng vòng đời cần dừng.

## 12. Test cancellation bằng StepVerifier

Chỉ kiểm kết quả `Flux.range(1,10).take(3)` là chưa đủ để chứng minh upstream thực sự nhận cancel. Có thể gắn counter gần nguồn và dùng `StepVerifier` kiểm soát demand và lúc hủy.

Tạo tệp `src/test/java/demo/CancellationPropagationTest.java` trong dự án Java có JUnit Jupiter và `reactor-test`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CancellationPropagationTest {

    @Test
    void downstreamCancelReachesSource() {
        AtomicInteger cancellations = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 10)
                .doOnCancel(() -> cancellations.incrementAndGet());

        StepVerifier.create(source, 0L)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertEquals(1, cancellations.get());
    }

    @Test
    void takeCancelsUpstreamAfterEnoughItems() {
        AtomicInteger cancellations = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 10)
                .doOnCancel(() -> cancellations.incrementAndGet());

        StepVerifier.create(source.take(3))
                .expectNext(1, 2, 3)
                .verifyComplete();

        assertEquals(1, cancellations.get());
    }
}
```

**Phụ thuộc:** `io.projectreactor:reactor-test` và JUnit Jupiter phù hợp với Reactor/Spring Boot BOM. Dùng `./gradlew test` hoặc `mvn test` theo dự án. Với ví dụ đồng bộ, các assertions không cần dựa vào `Thread.sleep(...)`.

Giải thích test:

1. `StepVerifier.create(source, 0L)` dùng **initial demand bằng 0 của test subscriber**, hoàn toàn khác việc gọi `Subscription.request(0)` (không hợp lệ).
2. `thenRequest(2)` xin đúng hai phần tử rồi `thenCancel()` gửi cancel.
3. Callback `doOnCancel` đặt ngay sau source nhận tín hiệu này và tăng counter.
4. Test thứ hai cho thấy `take(3)` **complete ở downstream**, nhưng hủy source chưa phát hết.
5. Counter phản ánh hủy Reactor subscription, **không phải** một HTTP server hay database bên ngoài đã dừng hoàn toàn.

Với nguồn async hoặc hot source, mở rộng test bằng virtual time, publisher có thể ghi nhận request/cancel, mock HTTP server và kiểm tra tài nguyên/callback sau khi subscriber rời đi. Không dùng một lần log “cancel” làm bằng chứng rằng giao dịch bên ngoài đã rollback.

### 12.1. Trường hợp test nên có trong production

- Downstream cancel **trước khi nhận phần tử nào**: nguồn phải dọn resource đã mở.
- Downstream cancel **sau vài phần tử**: không gửi tiếp dữ liệu hữu ích vào subscription đã hủy, xử lý phần tử buffer bị discard.
- Cancel **cùng lúc với complete/error**: cleanup không thực hiện trùng hoặc bỏ sót; code phải idempotent.
- Cancel khi **đang có request HTTP/DB**: đo tài nguyên client và server; xem SDK/driver có hỗ trợ hủy.
- Nhiều subscriber cùng chia sẻ publisher: cancel một subscriber không đóng nhầm tài nguyên chung.
- Async cleanup lỗi hoặc timeout: có observability, retry/compensation hợp lệ và không rò tài nguyên.
- Request bị **timeout hoặc client disconnect**: xác định loại tín hiệu ở từng vị trí và các side effect đã xảy ra.
- Callback source phát rất nhanh: kiểm tra overflow, buffer và cancellation race thay vì chỉ dùng source synchronous.

## 13. Các lỗi suy luận phổ biến

| Nhầm lẫn | Điều đúng | Cách xử lý |
| --- | --- | --- |
| “Hết demand tức là đã cancel” | Outstanding demand bằng 0 chỉ có nghĩa chưa xin thêm | Dùng `cancel()` nếu không cần subscription nữa |
| “Gọi `cancel()` làm upstream phát `onComplete()`” | Cancel là tín hiệu điều khiển; không phải terminal signal bắt buộc của source | Quan sát `doOnCancel` hoặc `doFinally(CANCEL)` gần nguồn |
| “`take(3)` chỉ phát ba item thì source cũng complete bình thường” | Output của `take` complete, nguồn còn dữ liệu thường nhận cancel | Đặt hook cả trước và sau `take` |
| “Cancel bảo đảm dừng HTTP server/JDBC ngay” | Cancel cục bộ có thể không dừng việc đã gửi ra ngoài | Timeout, driver support, idempotency và telemetry |
| “`onErrorResume` sẽ bắt cancel” | Cancel không phải error | Theo dõi `doOnCancel`/`doFinally` |
| “`doOnTerminate` xử lý mọi đường kết thúc” | Nó xử lý complete/error, không xử lý cancel thuần túy | Dùng `doFinally` hoặc `using/usingWhen` |
| “Chỉ cần `doFinally(resource::close)` trong mọi trường hợp” | Cleanup có thể cần theo từng subscription hoặc async; callback order quan trọng | Ưu tiên `using/usingWhen` và ownership rõ ràng |
| “Client đóng tab nên DB write chắc chắn chưa commit” | Side effect phía server có thể đã hoàn tất | Kiểm tra trạng thái/idempotency, không suy ra rollback |
| “Cancel một subscriber sẽ dừng hot source chung” | Nguồn vẫn có thể phục vụ subscriber khác | Quản lý resource theo đúng phạm vi sở hữu |
| “Tắt controller bằng `subscribe()` rồi dispose tùy ý vẫn an toàn” | Tự subscribe có thể tách tác vụ khỏi lifecycle HTTP | Return publisher cho framework |
| “Cancel tức thì nên không thể có race” | Work/tín hiệu đã in-flight có thể xảy ra quanh thời điểm cancel | Viết cleanup idempotent, test concurrent race |
| “Retry sau cancel luôn an toàn” | Tác vụ cũ có thể đã ghi dữ liệu dù client bỏ chờ | Thiết kế idempotency và giới hạn retry |

## 14. Quy trình đọc và debug một pipeline có cancel

Khi nghi ngờ hủy không giải phóng tài nguyên, làm theo chuỗi phân tích sau:

1. **Xác định ai là subscriber cuối.** Spring WebFlux, WebClient, message consumer, ứng dụng CLI hay một `BaseSubscriber` tự viết?
2. **Xác định nguyên nhân cancel.** Client disconnect, `take`, `next`, `switchMap`, `timeout`, explicit `dispose` hay shutdown?
3. **Vẽ ranh giới subscription.** Đánh dấu mỗi `flatMap` inner, upstream source, `share/cache` và tài nguyên dùng chung.
4. **Đặt hook đúng vị trí.** `doOnSubscribe`, `doOnCancel`, `doFinally` trước/sau operator có thể cắt nguồn; thêm request correlation ID.
5. **Quan sát cleanup.** Số timer còn active, open connection, queued task, bytes buffered, resource close count, transaction state.
6. **Phân biệt cancellation signal với kết quả ngoài JVM.** Nếu gọi HTTP hoặc DB, hỏi server/driver xem tác vụ thật sự bị dừng, hoàn tất hay đã commit.
7. **Thử tình huống race.** Hủy ngay trước khi có result, sau một phần tử, khi fallback/error và khi hoàn tất đồng thời.
8. **Dùng test có kiểm soát.** `StepVerifier` để xác nhận tín hiệu Reactor; integration test cho network và persistence.
9. **Áp dụng cleanup đúng lifecycle.** `using` cho resource đồng bộ; `usingWhen` cho resource async; `sink.onCancel/onDispose` cho callback bridge; kiểm tra idempotency.
10. **Đo tác động vận hành.** Cùng tải nhưng số subscription, connection, task và heap sau cancel phải trở về mức nền; nếu không, tìm chỗ giữ tài nguyên.

Không cần tạo một thread mới cho mỗi cancel, cũng không cần dùng `block()` để đợi cleanup trong WebFlux controller. Việc chờ hoặc điều phối cleanup phải được biểu diễn theo đúng lifecycle của publisher, đặc biệt khi cleanup bất đồng bộ.

## 15. Tài liệu tham khảo

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): contract của `Publisher`, `Subscriber`, `Subscription.request` và `Subscription.cancel`.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): phần subscription, cancellation, `doFinally`, `using` và resource lifecycle.
- [Project Reactor API – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `doOnCancel`, `take`, `using` và `usingWhen`.
- [Project Reactor API – Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `doFinally` và cleanup cho Mono.
- [Project Reactor Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` và kiểm thử tín hiệu.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): response publisher, streaming và lifecycle HTTP.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): quản lý `DataBuffer`, reference counting và release tài nguyên.

## 16. Ghi nhớ

**Downstream không còn cần dữ liệu thì gửi `cancel()` qua subscription; operator đưa tín hiệu này ngược dòng để upstream ngừng phát và dọn tài nguyên khi có thể.** Một operator như `take(3)` có thể làm downstream complete bình thường trong khi upstream nhận cancel; đây là hành vi có chủ đích.

Cần ghi nhớ bốn điều:

1. **Cancel khác hết demand:** chỉ không request thêm không có nghĩa đã đóng subscription.
2. **Cancel là best-effort về công việc thực tế:** HTTP, JDBC, callback nóng và giao dịch bên ngoài có thể vẫn chạy hoặc đã hoàn thành.
3. **Đặt lifecycle đúng chỗ:** `doOnCancel`/`doFinally` để quan sát, `using`/`usingWhen` để quản lý resource, và return publisher cho Spring WebFlux.
4. **Kiểm thử cả tín hiệu lẫn tài nguyên:** xác nhận upstream nhận cancel, cleanup đúng một lần và không suy luận nhầm rằng side effect đã rollback.

Nhờ hiểu được chiều lan truyền này, bạn có thể xây dựng các luồng dữ liệu tiết kiệm tài nguyên, dừng tác vụ không cần thiết và giữ hành vi đúng khi client rời đi giữa chừng.
