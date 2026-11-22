# Theo dõi nhu cầu từ downstream về upstream trong Project Reactor

**Bối cảnh:** Spring Framework – Reactive, chủ đề **Backpressure**. Bài này giải thích cách subscriber thể hiện khả năng tiếp nhận dữ liệu qua `Subscription.request(n)`, cách nhu cầu đi ngược chiều qua các operator Reactor và cách kiểm tra luồng yêu cầu thực tế. Kiến thức áp dụng cho `Flux`, `Mono` và các pipeline được Spring WebFlux sử dụng.

## 1. Tại sao cần theo dõi nhu cầu?

Giả sử nguồn phát 50.000 sự kiện mỗi giây nhưng bộ xử lý phía cuối chỉ xử lý được 1.000 sự kiện mỗi giây. Nếu nguồn cứ gửi không giới hạn, dữ liệu chưa xử lý sẽ tích tụ trong hàng đợi hoặc bộ nhớ. Khi bộ đệm cạn, ứng dụng có thể tăng độ trễ, tiêu thụ quá nhiều RAM, lỗi tràn bộ đệm hoặc bị dừng.

**Backpressure** là cơ chế cho phép phía tiêu thụ (*downstream*) diễn đạt nó đang sẵn sàng nhận thêm bao nhiêu phần tử từ phía cung cấp (*upstream*). Trong Reactive Streams, tín hiệu này chủ yếu được truyền qua phương thức `request(long n)` trên `Subscription`.

Cần phân biệt hai chiều di chuyển:

- **Dữ liệu và tín hiệu kết quả**: từ upstream xuống downstream, gồm `onNext(item)`, `onError(error)`, `onComplete()`.
- **Điều khiển**: từ downstream về upstream, quan trọng nhất là `request(n)` và `cancel()`.

```text
  Hướng dữ liệu:
  Source  ----onNext/onError/onComplete----> Operator ----> Subscriber
    ^                                         ^                |
    |                                         |                |
    +------------ request(n) / cancel --------+----------------+
                Hướng điều khiển ngược dòng
```

**Demand** là lượng phần tử được phép phát thêm ở một ranh giới subscription, không phải số phần tử hiện đang lưu trong bộ nhớ, tốc độ request/giây, số thread, kích thước byte hoặc độ lớn một HTTP request. `request(10)` có nghĩa “tôi cho phép nhận tối đa thêm 10 phần tử theo hợp đồng Reactive Streams”, không có nghĩa “gửi đúng 10 phần tử ngay tức khắc”.

Một nguồn hợp lệ có thể phát **ít hơn** số yêu cầu nếu không còn dữ liệu, có lỗi, bị hủy hoặc chưa sẵn sàng. Một nguồn hữu hạn có thể hoàn thành bình thường dù demand còn dư.

## 2. Các thành phần tạo nên cơ chế request

Reactive Streams định nghĩa các vai trò sau:

| Thành phần | Vai trò | API chính |
| --- | --- | --- |
| `Publisher<T>` | Cung cấp tín hiệu tới subscriber theo nhu cầu đã đăng ký | `subscribe(Subscriber<? super T>)` |
| `Subscriber<T>` | Nhận subscription và tín hiệu từ publisher | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Subscription` | Liên kết một subscriber với publisher cụ thể; điều khiển số phần tử được yêu cầu và hủy | `request(long n)`, `cancel()` |
| Reactor `Flux<T>` | Publisher phát 0 đến nhiều phần tử | Các toán tử như `map`, `buffer`, `flatMap` |
| Reactor `Mono<T>` | Publisher phát tối đa một phần tử rồi hoàn thành hoặc lỗi | `map`, `flatMap`, `then`, ... |
| Operator ở giữa | Vừa tiêu thụ dữ liệu từ upstream, vừa cung cấp cho downstream | Chuyển tiếp hoặc biến đổi `request` và các tín hiệu |

Vòng đời tiêu biểu:

1. Downstream subscribe vào publisher.
2. Downstream nhận `onSubscribe(subscription)` để có quyền `request` hoặc `cancel`.
3. Downstream gọi `subscription.request(n)` với số **dương** khi sẵn sàng.
4. Upstream chỉ phát `onNext` trong lượng demand hợp lệ tại subscription đó; operator truyền tiếp tín hiệu, có thể biến đổi kích thước/yêu cầu.
5. Downstream có thể gọi thêm `request(n)`; khi nguồn hết dữ liệu, phát `onComplete`; khi lỗi, phát `onError`; khi không cần nữa, gọi `cancel()`.

Trong một subscription, chuỗi callback về dữ liệu có hình thức tổng quát `onSubscribe → onNext* → (onComplete | onError)?`. Sau tín hiệu kết thúc, subscription không tiếp tục phát dữ liệu. `cancel()` yêu cầu dừng, nhưng tác động hủy có thể không tức thời và không hoàn tác side effect đã diễn ra.

**Điểm quan trọng:** một operator có thể là subscriber đối với nguồn ngay phía trước và publisher đối với tầng ngay phía sau. Do đó, “downstream” và “upstream” là **quan hệ tương đối theo vị trí trong pipeline**; cùng một operator có thể nhận `request` từ phía sau rồi tạo `request` khác cho phía trước.

## 3. Theo dõi outstanding demand: cộng request, trừ onNext

Giả sử subscriber chưa yêu cầu phần tử nào. Nó gọi:

```text
request(2)       outstanding demand = 2
onNext(A)        outstanding demand = 1
onNext(B)        outstanding demand = 0
request(3)       outstanding demand = 3
onNext(C)        outstanding demand = 2
onNext(D)        outstanding demand = 1
```

Ở đúng **ranh giới subscription đang xét**, công thức trực giác là:

```text
outstanding = tổng số phần tử đã request - tổng số onNext hợp lệ đã nhận
```

Các lần `request(n)` **cộng dồn** với nhu cầu chưa sử dụng. Hai lần `request(2)` và `request(3)` trước khi nhận dữ liệu cho phép tối đa 5 `onNext` ở ranh giới đó. Chúng không thay thế nhau và không tự giới hạn nguồn chỉ còn 3.

Một publisher tuân thủ Reactive Streams không được gửi `onNext` vượt outstanding demand. Tuy nhiên, nó có thể gửi ít hơn vì không có dữ liệu; `onComplete` hoặc `onError` không phải một phần tử `onNext` và không cần “tốn” một đơn vị demand để kết thúc.

### 3.1. `request(n)` phải dương

- `request(1)`: xin thêm một phần tử.
- `request(64)`: cho phép phát thêm tối đa 64 phần tử.
- `request(Long.MAX_VALUE)`: được coi là yêu cầu **không giới hạn thực tế** (*unbounded demand*) trong Reactor.
- `request(0)` hoặc `request(-1)`: **không hợp lệ** theo Reactive Streams. Khi subscription chưa bị hủy, đó là vi phạm và được báo qua `onError` với `IllegalArgumentException`; không dùng `request(0)` làm lệnh “tạm dừng”.

Nếu muốn chưa nhận phần tử, hãy giữ subscription và **chưa gửi request**. Nếu không còn cần dữ liệu, dùng `cancel()`. Nếu muốn giảm nhịp, yêu cầu theo từng đợt đủ nhỏ, xử lý xong rồi xin tiếp. Không yêu cầu “số âm” để hoàn lại demand đã cấp.

Với số lượng rất lớn, demand được xử lý theo hướng bão hòa tại `Long.MAX_VALUE` để tránh overflow số nguyên trong triển khai phù hợp. Khi đã coi là unbounded, upstream có thể phát nhanh hết mức cho phép bởi các ràng buộc còn lại; nguy cơ quá tải ở nguồn không backpressure-aware vẫn tồn tại.

### 3.2. `request` có thể gây phát đồng bộ hoặc bất đồng bộ

Trong `Flux.range(...)`, một `request(2)` có thể làm hai callback `onNext` chạy **ngay trong lần gọi request**. Với nguồn I/O bất đồng bộ như `WebClient`, yêu cầu thể hiện khả năng tiếp nhận nhưng dữ liệu chỉ có sau khi kết nối/nguồn thực sự phát.

Vì vậy không mặc định rằng:

- `request(5)` sẽ chờ cho tới khi nhận đủ 5 phần tử;
- mỗi `request` tạo đúng một đợt network;
- tất cả `request`/`onNext` xảy ra trên cùng một thread;
- số lượng `request` đo gần nguồn bằng số lượng `request` của subscriber cuối.

## 4. Ví dụ Java 17+ chạy được: request từng đợt và quan sát chiều ngược

Ví dụ độc lập sau dùng `Flux.range(...)`, `BaseSubscriber` và `doOnRequest(...)` để thấy rõ khi nào downstream xin thêm phần tử và upstream nhận số lượng nào.

Tạo tệp `src/main/java/demo/DemandFlowDemo.java`:

```java
package demo;

import java.util.List;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class DemandFlowDemo {

    public static void main(String[] args) {
        System.out.println("=== Demand tung dot ===");

        Flux<Integer> numbers = Flux.range(1, 5)
                .doOnRequest(n ->
                        System.out.println("source request(" + n + ")"));

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("onSubscribe, chua yeu cau du lieu");
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("onNext " + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("onComplete");
            }
        };

        numbers.subscribe(subscriber);
        System.out.println("sau subscribe");

        System.out.println("subscriber request(2)");
        subscriber.request(2);

        System.out.println("subscriber request(1)");
        subscriber.request(1);

        System.out.println("subscriber request(2)");
        subscriber.request(2);

        System.out.println("=== Buffer ba phan tu ===");

        Flux.range(1, 6)
                .doOnRequest(n ->
                        System.out.println("source-stage request(" + n + ")"))
                .buffer(3)
                .doOnRequest(n ->
                        System.out.println("buffer-stage request(" + n + ")"))
                .subscribe(new BaseSubscriber<List<Integer>>() {
                    @Override
                    protected void hookOnSubscribe(Subscription subscription) {
                        System.out.println("subscriber yeu cau 2 buffer");
                        request(2);
                    }

                    @Override
                    protected void hookOnNext(List<Integer> values) {
                        System.out.println("onNext buffer " + values);
                    }

                    @Override
                    protected void hookOnComplete() {
                        System.out.println("onComplete buffer");
                    }
                });
    }
}
```

**Cách chạy:** cần Java 17+, thư viện `reactor-core` và dependency `reactive-streams` tương thích. Trong Spring Boot có `spring-boot-starter-webflux`, các thư viện cần thiết thường đã có và bạn có thể chạy `main` từ IDE. Nếu biên dịch thủ công, đặt các JAR cần thiết vào thư mục `lib/` và tạo thư mục output:

```bash
# Linux / macOS; chạy tại thư mục gốc dự án
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/DemandFlowDemo.java
java -cp "out:lib/*" demo.DemandFlowDemo
```

```powershell
# Windows PowerShell; chạy tại thư mục gốc dự án
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/DemandFlowDemo.java
java -cp "out;lib/*" demo.DemandFlowDemo
```

**Stdout chính xác** với publisher đồng bộ trong ví dụ:

```text
=== Demand tung dot ===
onSubscribe, chua yeu cau du lieu
sau subscribe
subscriber request(2)
source request(2)
onNext 1
onNext 2
subscriber request(1)
source request(1)
onNext 3
subscriber request(2)
source request(2)
onNext 4
onNext 5
onComplete
=== Buffer ba phan tu ===
subscriber yeu cau 2 buffer
buffer-stage request(2)
source-stage request(6)
onNext buffer [1, 2, 3]
onNext buffer [4, 5, 6]
onComplete buffer
```

Giải thích:

1. `BaseSubscriber` cho phép tự quyết định demand. Việc override `hookOnSubscribe` trong ví dụ **không gọi request** nên sau khi `numbers.subscribe(subscriber)`, nguồn chưa phát `onNext`; dòng `sau subscribe` được in trước.
2. `subscriber.request(2)` gửi hai đơn vị nhu cầu tới nguồn `Flux.range`. `doOnRequest` log ở gần nguồn, rồi nguồn phát 1 và 2. Sau đó hết demand nên tạm dừng.
3. Khi xin thêm 1, nguồn chỉ phát 3. Khi xin thêm 2 nữa, nguồn phát 4 và 5, sau đó hoàn thành.
4. Phần `buffer(3)` biến **3 số nguyên thành một danh sách**. Subscriber cuối yêu cầu 2 **danh sách**, nên tầng `buffer` cần lấy **6 số nguyên** từ nguồn. Vì vậy log ở hai vị trí có số request khác nhau: `2` ở phía sau `buffer`, `6` ở phía trước.
5. Code không tạo scheduler hoặc I/O bất đồng bộ; nguồn đồng bộ nên thứ tự log trên là xác định. Với `publishOn`/`flatMap` hay nguồn network, log từ nhiều luồng có thể xen kẽ và không nên suy đoán thứ tự bằng ví dụ đồng bộ này.

**Cảnh báo khi tự viết subscriber:** `BaseSubscriber` mặc định yêu cầu unbounded nếu không override `hookOnSubscribe`. Override mà quên gọi request hoặc quên tổ chức cơ chế xin thêm có thể làm một `Flux` đứng chờ mãi. Ví dụ cố ý xin từ `main` để làm rõ lượng demand, không đại diện cho vòng đời subscriber trong WebFlux production.

## 5. Vì sao demand có thể thay đổi khi đi qua operator?

Nhu cầu downstream không nhất thiết đi thẳng về upstream bằng cùng một con số. Mỗi operator biết cách nó biến đổi phần tử và có thể điều chỉnh request để cung cấp đủ dữ liệu đầu ra, thực hiện prefetch hoặc quản lý buffer.

Xét pipeline:

```java
Flux<List<Integer>> batches = Flux.range(1, 100)
        .doOnRequest(n -> System.out.println("near source: " + n))
        .buffer(5)
        .doOnRequest(n -> System.out.println("near subscriber: " + n));
```

Nếu downstream muốn **2 phần tử kiểu `List<Integer>`**, `buffer(5)` cần tối đa **10 phần tử `Integer`** phía trước. Kết quả của ví dụ này là request(2) ở gần subscriber nhưng request(10) ở gần nguồn. Đây là chuyển đổi hợp đồng **đơn vị phần tử theo từng ranh giới**.

| Operator | Ý nghĩa nhu cầu downstream | Điều có thể xảy ra ở upstream |
| --- | --- | --- |
| `map` | Một phần tử đầu ra ứng với một phần tử đầu vào | Thường giữ quan hệ 1:1 về số lượng; vẫn có thể có bất đồng bộ ở nơi khác |
| `filter` | Chỉ những phần tử đạt điều kiện mới đi tiếp | Có thể yêu cầu thêm để bù phần tử bị loại |
| `buffer(k)` | Một `onNext` downstream chứa tối đa `k` phần tử upstream | Có thể nhân nhu cầu; ví dụ 2 buffer x 5 phần tử = 10 đầu vào |
| `flatMap` | Một phần tử outer tạo publisher bên trong có thể phát nhiều phần tử | Có thể có nhiều inner subscription và prefetch; số request không nhất thiết 1:1 |
| `concatMap` | Theo dõi các inner theo thứ tự | Có cơ chế yêu cầu và đệm tùy operator/phiên bản |
| `publishOn` | Đưa xử lý downstream sang scheduler khác | Dùng queue và prefetch để tách thời điểm upstream phát/downstream xử lý |
| `take(k)` | Chỉ cần tối đa `k` phần tử downstream | Có thể giới hạn phát và hủy upstream sau khi đã đủ |
| `limitRate(highTide, lowTide)` | Chia request lớn thành các lô nhỏ phía upstream | Yêu cầu tăng theo lô và bổ sung dần, có thể đổi hình dạng log request |

Không nên học thuộc “mỗi request của subscriber tương ứng một request upstream”. Cần **đặt điểm đo quanh từng operator** để biết chính xác chỗ nào biến đổi demand.

### 5.1. `buffer`: đổi đơn vị phần tử

`buffer(5)` không tạo thêm dữ liệu nghiệp vụ, nhưng biến năm phần tử riêng lẻ thành một danh sách. Downstream xin 2 đơn vị thì đó là **2 danh sách**, tương ứng nhu cầu nhiều phần tử gốc hơn.

Còn `window(5)` tạo các publisher con, khiến cả subscription của window và mức tiêu thụ bên trong ảnh hưởng hành vi; không được coi nó luôn tương đương với `buffer(5)` về thời điểm và bộ nhớ. `groupBy` cũng tạo các group publisher, yêu cầu quản lý tiêu thụ từng group để tránh tích tụ.

### 5.2. `filter`: bù các phần tử bị bỏ

Nếu nguồn là `Flux.range(1, 10).filter(n -> n % 2 == 0)`, downstream yêu cầu ba giá trị chẵn; nguồn có thể phải đọc nhiều hơn ba số nguyên vì các số lẻ không được chuyển xuống. Reactor có thể điều chỉnh demand nhằm bù dữ liệu bị loại. Vì vậy log số request trước và sau `filter` không nhất thiết giống nhau, đặc biệt khi kết hợp các operator hoặc chế độ fusion.

### 5.3. `flatMap`, `concatMap` và prefetch

Các operator ghép publisher con có thể yêu cầu trước một lượng dữ liệu từ inner hoặc outer để giữ pipeline hoạt động hiệu quả. Tham số **prefetch** là số lượng phần tử dự kiến yêu cầu trước ở ranh giới tương ứng, và nhiều operator có chiến lược **replenishment**: đã tiêu thụ một phần lô thì xin thêm trước khi lô cạn hẳn.

Ví dụ:

```java
Flux<String> result = ids.flatMap(
        id -> remoteClient.fetchOne(id),
        8   // Giới hạn số inner publisher đồng thời
);
```

Đoạn trên chỉ là **mã minh họa**; `ids` và `remoteClient` cần do ứng dụng cung cấp. Giới hạn `concurrency=8` giúp kiểm soát số inner active trong phạm vi `flatMap`, nhưng không tự đồng nghĩa có tối đa tám HTTP connection cho toàn ứng dụng. Số request từ inner, số connection pool, queue scheduler và tải phía dịch vụ khác vẫn cần đo riêng.

Với một số overload của `flatMap`, `concatMap` và `publishOn`, có thể cấu hình `prefetch`. **Đừng cố đoán một giá trị mặc định cố định cho mọi operator hoặc mọi phiên bản Reactor**. Kiểm tra API phiên bản thực dùng, đặt giá trị theo mục tiêu bộ nhớ/throughput và đo lại trong tải thật.

## 6. Công cụ quan sát demand trong Reactor

### 6.1. `doOnRequest`: đo request tại một ranh giới

`doOnRequest(LongConsumer)` là điểm quan sát hữu ích nhất cho bài toán này. Callback chạy khi operator **nhận** yêu cầu từ downstream, trước khi truyền yêu cầu đó tới upstream. Đây là log cho **demand đến ranh giới đang đặt operator**, không phải số phần tử chắc chắn sẽ được phát và cũng không nhất thiết là demand ban đầu của subscriber cuối.

```java
Flux<Integer> pipeline = Flux.range(1, 50)
        .doOnRequest(n -> System.out.println("A near source: " + n))
        .buffer(5)
        .flatMapIterable(list -> list)
        .doOnRequest(n -> System.out.println("B near consumer: " + n));
```

Đây là ví dụ minh họa về chỗ đặt log. `flatMapIterable` có thể thay đổi cách yêu cầu phía trước, vì vậy **không suy đoán trước chuỗi log chính xác** cho pipeline này; dùng nó để quan sát số request thực khi chạy với subscriber có demand đã biết.

Một sơ đồ vị trí:

```text
Flux source
   |
doOnRequest("A")   <- request ngay trước source
   |
buffer(5)
   |
flatMapIterable(...)
   |
doOnRequest("B")   <- request tại output
   |
Subscriber
```

Khi subscriber gọi `request(2)`, `B` quan sát nhu cầu ở output. `A` có thể nhận một số khác vì các operator ở giữa. Theo chiều tín hiệu, **onNext đi A → B** còn **request đi B → A**.

### 6.2. `doOnNext`, `doOnCancel`, `doFinally` và `log()`

Để hiểu *đã yêu cầu bao nhiêu* và *đã nhận bao nhiêu*, có thể đặt cặp quan sát:

```java
return source
        .doOnRequest(n -> metrics.recordRequest(n))
        .doOnNext(value -> metrics.recordReceived())
        .doOnCancel(metrics::recordCancel)
        .doFinally(signal -> metrics.recordEnd(signal));
```

Đây là đoạn **minh họa trong service**, với `source` và `metrics` do hệ thống định nghĩa. `doOnRequest` là callback cho mỗi lần request, `doOnNext` chạy mỗi lần có phần tử, `doOnCancel` quan sát cancellation, `doFinally` cho biết kết thúc bằng completion/error/cancel.

Lưu ý kỹ:

- Tổng các con số nhận được qua `doOnRequest` là **demand tín hiệu** ở điểm đặt log, không phải hàng đợi thực tế, không đo được lượng buffer bên trong một cách trực tiếp.
- `doOnNext` cho biết phần tử đã đi qua điểm đo, không xác nhận business logic cuối đã commit.
- Một nguồn có thể yêu cầu nhiều nhưng phát ít do hoàn thành sớm. Ngược lại, nguồn nóng không tuân thủ demand có thể yêu cầu chính sách drop/buffer riêng.
- `doFinally` có thể chạy sau khi tín hiệu kết thúc đã đi xuống subscriber; đừng dùng thứ tự log giữa các thread làm chứng cứ duy nhất.
- `log()` của Reactor có thể giúp xem các tín hiệu `request`, `onNext`, `cancel` và terminal trong môi trường phát triển. Dưới tải lớn, log từng phần tử tốn chi phí và có nguy cơ lộ dữ liệu; chọn phạm vi và mức log phù hợp.

Với chỉ số trong production, đo **độ sâu queue/buffer**, số publisher/subscription đang active, số phần tử đã phát/đã nhận/đã drop, overflow, thời gian chờ pool, heap, GC, p95/p99 latency và tỷ lệ lỗi. Các số này trả lời câu hỏi backpressure có kiểm soát được tài nguyên không, thay vì chỉ nhìn một request(n) đơn lẻ.

### 6.3. Tại sao `subscribe(value -> ...)` thường log demand rất lớn?

Nhiều overload `subscribe()` dạng lambda và các lời gọi chặn như `block()`/`blockLast()` mặc định **yêu cầu unbounded** (tương đương `Long.MAX_VALUE` đối với Reactor). Đây là tiện ích để tiêu thụ chuỗi đơn giản, nhưng không thích hợp nếu mục tiêu là tự điều khiển từng đợt request.

Nếu muốn thấy các đợt nhỏ, dùng `BaseSubscriber` và chủ động `request(n)`, hoặc công cụ test `StepVerifier.create(publisher, initialRequest)`. Việc dùng `Mono` có tối đa một giá trị không tự chứng minh nguồn có backpressure end-to-end; cách subscription và I/O phía dưới vẫn quan trọng.

## 7. Điều tiết request upstream với `limitRate`

Reactor cung cấp `limitRate(...)` để chia một request lớn từ downstream thành các lô nhỏ hơn khi đẩy lên upstream. Ví dụ:

```java
Flux<Integer> boundedRequests = Flux.range(1, 1000)
        .doOnRequest(n -> System.out.println("near source: " + n))
        .limitRate(10, 0);
```

Nếu subscriber cuối yêu cầu rất nhiều phần tử, `limitRate(10, 0)` cho phép operator yêu cầu upstream theo **các lô tối đa 10**. `lowTide=0` chọn chế độ lô chặt (*strict batching*): sau khi tiêu thụ lô sẽ yêu cầu lô tiếp theo theo nhu cầu còn lại; không dùng chiến lược nạp bù sớm như chế độ mặc định.

Với `limitRate(10)`, operator có thể bổ sung trước một phần demand khi đã tiêu thụ đủ lượng trong lô, thay vì bắt buộc chờ cạn rồi mới yêu cầu đợt mới. Overload `limitRate(highTide, lowTide)` cho phép điều chỉnh ngưỡng lô ban đầu và ngưỡng nạp bù; phải kiểm tra semantics theo phiên bản Reactor đang sử dụng.

**Không nhầm `limitRate(10)` với “10 phần tử/giây”.** Nó chia số lượng request theo **kích thước lô**, không thêm đồng hồ để khống chế throughput theo thời gian. Một publisher đồng bộ rất nhanh vẫn có thể phát hàng nghìn phần tử mỗi giây qua các lô 10.

Cũng không suy ra giới hạn heap bằng đúng 10 phần tử: những operator khác, bộ đệm trong HTTP/Netty, dữ liệu nội bộ, inner publishers và quá trình serialization có thể cần thêm bộ nhớ. Khi dùng `limitRate` cần đo cả luồng dữ liệu thực tế.

Với yêu cầu dừng sau một số phần tử, `take(n)` có contract khác: nó **giới hạn số phần tử đầu ra và có thể hủy upstream khi đủ**. `limitRate` không tự làm ngắn tổng số phần tử của nguồn.

## 8. Nguồn không giảm tốc theo request: khi backpressure chỉ có thể đệm, bỏ hoặc lỗi

Reactive Streams yêu cầu publisher tuân thủ demand tại ranh giới tới subscriber, nhưng không phải nguồn dữ liệu bên ngoài nào cũng có khả năng thực sự **giảm tốc độ phát sinh**. Ví dụ: thiết bị đo đạc, luồng callback nóng, các sự kiện UI liên tục, message broker gửi sẵn, UDP hoặc một dịch vụ HTTP đã bắt đầu tính toán. Hủy/không xin thêm ở đầu nhận không đảm bảo nguồn thực tế ngừng tạo dữ liệu.

Trong trường hợp này, adapter có thể chọn chính sách:

| Chính sách | Ý nghĩa | Điều phải chấp nhận |
| --- | --- | --- |
| **Giới hạn nguồn** | Tạm ngừng producer, giới hạn concurrency hoặc điều khiển nguồn bằng demand nếu giao thức cho phép | Cần API hỗ trợ thực sự; có thể giảm throughput |
| **Buffer có giới hạn** | Giữ tạm một số phần tử để downstream xử lý sau | Tốn bộ nhớ; khi đầy phải có chính sách overflow |
| **Drop** | Bỏ các phần tử không thể tiếp nhận | Mất dữ liệu; chỉ hợp với telemetry/preview có thể bỏ |
| **Latest** | Giữ phần tử mới nhất khi phía nhận chậm | Mất các giá trị trung gian, không phù hợp ghi giao dịch |
| **Error/Reject** | Báo lỗi khi không theo kịp | Downstream phải xử lý thất bại và phục hồi |
| **Queue bền vững** | Tách tiếp nhận và xử lý qua broker/hàng đợi lưu trữ | Có giới hạn, chi phí vận hành, yêu cầu ack/retry/idempotency |

Một số toán tử Reactor liên quan:

- `onBackpressureBuffer(...)`: đệm phần tử khi downstream chưa đáp ứng; ưu tiên cấu hình **dung lượng hữu hạn** và overflow policy phù hợp; một buffer không giới hạn có thể dẫn đến cạn bộ nhớ.
- `onBackpressureDrop(...)`: có thể bỏ phần tử khi không còn demand.
- `onBackpressureLatest()`: giữ giá trị mới nhất trong một số tình huống downstream chậm; **không bảo toàn từng event**.
- `onBackpressureError()`: báo lỗi khi dòng dữ liệu vượt khả năng demand.
- `Flux.create(...)` và `Sinks.Many`: phải xem chiến lược overflow/backpressure của adapter hoặc sink, đặc biệt khi nguồn nóng đẩy dữ liệu bất chấp request.

Các chính sách trên **không làm sai hợp đồng dữ liệu một cách vô điều kiện**. Nếu nghiệp vụ yêu cầu không được bỏ bất kỳ thanh toán/đơn hàng/sự kiện kiểm toán nào, không chọn drop/latest chỉ để hết cảnh báo quá tải; cần queue đáng tin, kiểm soát nguồn và xử lý idempotent.

### 8.1. Một ví dụ quyết định sai

Một `Flux<PaymentCommand>` phát 500 lệnh/giây trong khi downstream xử lý được 100 lệnh/giây. Gắn `onBackpressureLatest()` có thể khiến hệ thống “ổn định” về bộ nhớ nhưng **bỏ mất lệnh thanh toán**. Đây là lỗi nghiệp vụ nghiêm trọng.

Ngược lại, `Flux<MousePosition>` dùng để vẽ con trỏ trên màn hình có thể bỏ các vị trí trung gian và chỉ giữ vị trí mới nhất, nếu đó là UX mong muốn. Cùng một kỹ thuật điều tiết nhưng tính đúng đắn phụ thuộc vào **ý nghĩa từng phần tử**.

## 9. Liên hệ trực tiếp với Spring WebFlux

Trong Spring WebFlux, handler thường **trả về `Mono` hoặc `Flux`**. Framework subscribe vào publisher theo vòng đời HTTP để ghi response và xử lý completion/error/cancellation. Service/controller thường không nên tự `subscribe()` để đẩy response bằng side effect ngoài luồng.

Một endpoint Server-Sent Events (SSE) sau đây minh họa chỗ đặt điểm đo demand ở tầng controller:

Tệp `src/main/java/demo/ItemStreamController.java`, trong dự án Spring Boot có `spring-boot-starter-webflux`:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class ItemStreamController {

    @GetMapping(value = "/stream/items",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Integer>> stream() {
        return Flux.range(1, 20)
                .doOnRequest(n ->
                        System.out.println("source sees request(" + n + ")"))
                .map(i -> ServerSentEvent.<Integer>builder()
                        .data(i)
                        .build());
    }
}
```

Đây là **controller hoàn chỉnh bên trong một ứng dụng đang chạy**, không phải ứng dụng độc lập có hàm `main`. Khởi động Spring Boot và gọi `curl -N http://localhost:8080/stream/items` khi server chạy cổng 8080 để xem luồng sự kiện. Dữ liệu có thể được gửi dưới dạng SSE `data:1`, `data:2`, ...; không có stdout console cố định cho các dòng `request(...)` vì lượng request phụ thuộc HTTP adapter, runtime và trạng thái kết nối.

Ý nghĩa chính:

1. WebFlux subscribe vào publisher được return để ghi response; publisher không cần tự subscribe trong controller.
2. `doOnRequest` quan sát demand mà **phần chain phía sau nó** gửi lên, sau khi đã chịu tác động của HTTP bridge và các operator phía downstream.
3. Một HTTP client nhận chậm không có nghĩa ứng dụng sẽ nhận lần lượt đúng `request(1)` cho từng sự kiện. Framework, Netty, TCP, decoder, scheduler và các buffer ở mỗi lớp có cơ chế riêng.
4. Trên hệ thống thật, nguồn có thể là dữ liệu từ repository reactive, broker hoặc thiết bị. Chỉ khi các lớp trên đường đi có khả năng phối hợp, demand mới thực sự giúp **giảm lượng công việc được tạo** thay vì chỉ đẩy chỗ đệm sang tầng khác.
5. Nếu client hủy kết nối, hệ thống thường cần hủy subscription và giải phóng tài nguyên, nhưng phải kiểm tra adapter cụ thể; một tác vụ blocking hoặc xử lý từ xa có thể không dừng ngay.

**Không khẳng định “WebFlux tự đảm bảo backpressure end-to-end cho mọi HTTP API”.** Reactive Streams quản lý các publisher/subscriber **tuân thủ giao thức trong pipeline**; việc truyền áp lực qua network, HTTP body, database client, broker và thiết bị là vấn đề tích hợp. Một endpoint JSON dùng `collectList()` còn có thể gom toàn bộ kết quả vào bộ nhớ trước khi serialization, khiến lợi ích streaming không còn như mong đợi.

### 9.1. WebClient và database reactive có thể chịu tác động nào?

Khi dùng `WebClient.bodyToFlux(...)`, downstream request có thể ảnh hưởng tiến độ đọc/giải mã body tùy HTTP connector, codec và buffering. Nhưng số `request(n)` không thể coi là số TCP packet hoặc số hàng database mà server trả về. Một số máy chủ đã tạo data, một số driver đọc theo batch và một số giao thức không hỗ trợ pause tương ứng.

Với R2DBC hoặc reactive messaging, phải đọc contract driver và adapter cụ thể: các implementation có thể dùng fetch size, cursor, prefetch hoặc bộ đệm nội bộ. Theo dõi demand giúp đánh giá pipeline Reactor, nhưng cần thêm metrics tại **connection pool, driver, broker, upstream service** để biết áp lực có được truyền qua ranh giới hệ thống hay không.

## 10. Kiểm thử demand có kiểm soát với StepVerifier

Tại sao chỉ chạy `subscribe(System.out::println)` chưa đủ? Vì cách subscribe dạng lambda thường **xin unbounded**. Nó không chứng minh rằng publisher tôn trọng các yêu cầu nhỏ hoặc rằng operator biến đổi demand đúng như dự kiến.

`reactor-test` cung cấp `StepVerifier.create(publisher, initialRequest)` để khởi tạo demand và xin thêm theo từng bước. Test sau xác nhận `buffer(3)` cần sáu phần tử đầu vào để phát hai danh sách đầu ra.

Tệp `src/test/java/demo/DemandFlowTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DemandFlowTest {

    @Test
    void requestsTravelUpstreamInBufferUnits() {
        AtomicLong upstreamRequested = new AtomicLong();

        Flux<List<Integer>> batches = Flux.range(1, 6)
                .doOnRequest(upstreamRequested::addAndGet)
                .buffer(3);

        StepVerifier.create(batches, 0L)
                .expectSubscription()
                .thenRequest(1)
                .expectNext(List.of(1, 2, 3))
                .thenRequest(1)
                .expectNext(List.of(4, 5, 6))
                .verifyComplete();

        assertEquals(6L, upstreamRequested.get());
    }
}
```

Test yêu cầu dependency `io.projectreactor:reactor-test` và JUnit Jupiter. Với dự án Gradle dùng Spring Boot BOM, nên để BOM quản lý version phù hợp; chạy `./gradlew test` (Linux/macOS), `.\gradlew.bat test` (Windows) hoặc từ IDE. Nếu có Maven, cấu hình test dependencies tương ứng rồi chạy `mvn test`.

Giải thích test:

1. `initialRequest=0L` là tham số **nội bộ StepVerifier để chưa tự xin phần tử lúc đăng ký**, **không phải** gọi `Subscription.request(0)` (hành vi bị cấm).
2. Lần `thenRequest(1)` xin một **danh sách**; `buffer(3)` yêu cầu ba số từ nguồn để tạo danh sách đầu tiên.
3. Lần `thenRequest(1)` thứ hai xin danh sách còn lại; tổng số được yêu cầu ở nguồn là sáu.
4. `verifyComplete()` xác nhận publisher hoàn thành bình thường và không phát thừa. `assertEquals` kiểm tra số demand đã quan sát gần nguồn.

Với nguồn bất đồng bộ, có thể bổ sung `expectNoEvent(...)` để xác nhận chưa phát trước khi có request, dùng virtual time cho timer, và dùng publisher kiểm thử biết ghi nhận request/cancel. Không viết test chỉ dựa vào `Thread.sleep(...)` để đo event loop.

### 10.1. Những giả thiết cần test riêng

Tùy use case, hãy bổ sung test cho các yêu cầu sau:

- **Không có demand ban đầu:** publisher không phát `onNext` khi subscriber chưa xin phần tử.
- **Demand cộng dồn:** hai lần xin lần lượt `2` và `3` cho phép tối đa thêm năm phần tử.
- **Giới hạn sau operator:** `buffer`, `filter`, `flatMap` hoặc `publishOn` có thể làm request ở upstream khác downstream.
- **Cancellation:** subscriber cancel thì nguồn nhận tín hiệu hủy; công việc bên ngoài có thực sự dừng hay không phải test tích hợp riêng.
- **Nguồn nóng:** khi producer nhanh hơn consumer, đúng chính sách overflow/drop/latest/error được áp dụng và không mất dữ liệu ngoài contract.
- **Độ lớn dữ liệu:** dù số phần tử bounded, một phần tử là danh sách/hình ảnh lớn vẫn có thể ngốn bộ nhớ; kiểm tra cả byte và heap.

## 11. Phân tích tình huống thực tế

### Tình huống A: xử lý record từ cơ sở dữ liệu

Một service đọc từng record và kiểm tra dữ liệu. Downstream chỉ xử lý được một nhóm nhỏ cùng lúc. Nếu driver và adapter hỗ trợ, giới hạn demand/prefetch có thể giảm số record đang chờ trong JVM. Nhưng nếu query phía database luôn materialize toàn bộ kết quả trước khi trả, Reactor chỉ giảm áp lực ở đoạn **sau khi đã materialize**, không loại bỏ chi phí bộ nhớ ở driver hoặc database.

Nên quan sát: số row đọc và buffer, fetch size/cursor, thời gian query, active connections, hàng đợi xử lý, tốc độ commit và thời gian giữ transaction.

### Tình huống B: stream sự kiện phục vụ dashboard

Một dashboard chỉ cần giá trị cảm biến gần nhất. Nguồn phát nhanh hơn browser vẽ được. `onBackpressureLatest()` hoặc chiến lược sampling có thể phù hợp nếu **việc mất điểm trung gian được chấp nhận**. Nếu dashboard hiển thị dữ liệu kiểm toán cần đủ mọi sự kiện, chiến lược drop/latest sẽ sai; nên dùng kho lưu trữ/queue có replay và tiến trình tiêu thụ có kiểm soát.

Nên quan sát: lag giữa timestamp nguồn và hiển thị, số event bị drop, bộ nhớ đệm, thời gian ngắt kết nối và khả năng đồng bộ lại sau reconnect.

### Tình huống C: gom batch trước khi gọi API

Service phải gom 50 item thành một lô. Downstream xin 2 batch thì upstream có thể cần tới 100 item; số “2” trong log downstream không tương đương đã hạn chế sản xuất hai record gốc. Nếu backend chỉ chịu được 10 request đồng thời, cần kiểm soát thêm concurrency và pool, chứ không chỉ giảm số buffer được xin.

Nên quan sát: số item trong batch, thời gian chờ batch đầy, số batch in-flight, số HTTP call, timeout và sự khác nhau giữa demand theo **batch** và demand theo **item**.

### Tình huống D: subscriber chậm đột biến

Nguồn được lập trình đúng có thể dừng phát `onNext` tại ranh giới thiếu demand. Nhưng một producer không thể tạm dừng có thể tiếp tục phát vào buffer trung gian; hàng đợi sẽ đầy. Cần quyết định rõ: cho producer dừng, đệm hữu hạn rồi báo lỗi, hay bỏ phần tử có thể mất. Cấu hình retry tự động sau overflow có thể làm áp lực còn lớn hơn nếu không có backoff và giới hạn.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật cần nhớ |
| --- | --- |
| “`subscribe()` luôn tự giới hạn lượng dữ liệu” | Nhiều overload subscribe theo lambda của Reactor xin `Long.MAX_VALUE`; muốn bounded request phải tự điều khiển |
| “`request(0)` sẽ tạm dừng luồng” | `request(0)` không hợp lệ; chỉ **không gọi request** để giữ demand ở 0 |
| “`request(5)` bắt buộc có đúng 5 item” | Publisher có thể phát ít hơn nếu hoàn thành/lỗi; `request` là giới hạn tối đa được phép phát |
| “Đã request rồi thì `onNext` phải tới ngay” | Nguồn async có thể còn đang chờ I/O hoặc dữ liệu mới |
| “Mỗi request của subscriber là một request giống hệt tới nguồn” | `buffer`, `filter`, `flatMap`, `publishOn` và prefetch có thể biến đổi request |
| “`doOnRequest` hiển thị số phần tử đang nằm trong queue” | Nó chỉ log tín hiệu nhu cầu ở vị trí operator |
| “`Long.MAX_VALUE` nghĩa là JVM có đủ bộ nhớ cho vô hạn phần tử” | Đây là demand không giới hạn, không phải cam kết về tài nguyên |
| “`limitRate(10)` giới hạn 10 phần tử/giây” | Nó chia kích thước các lô request, không đặt đồng hồ điều tốc |
| “Có backpressure ở Flux thì TCP/DB/broker cũng dừng ngay” | Backpressure chỉ lan được đến nơi adapter/giao thức hỗ trợ; những tầng khác có buffer hoặc vẫn hoạt động |
| “`onBackpressureBuffer()` luôn an toàn” | Buffer không giới hạn có thể hết bộ nhớ; cần dung lượng và overflow policy |
| “Có thể drop sự kiện để giảm tải mà không ảnh hưởng kết quả” | Chỉ đúng với loại dữ liệu được phép mất; sai với giao dịch/bản ghi cần đủ |
| “Hủy subscription là rollback nghiệp vụ” | Cancellation không tự hoàn tác công việc hoặc side effect bên ngoài đã diễn ra |

## 13. Checklist để theo dõi demand trong một pipeline thực tế

1. **Xác định ranh giới subscriber cuối.** Ai subscribe: WebFlux framework, Reactor Test, message consumer hay code tự viết? Nó có tự xin unbounded không?
2. **Vẽ đường đi của `request`.** Đặt `doOnRequest` tại downstream và gần upstream, ghi rõ kiểu phần tử tại từng điểm: item, list, window, inner publisher.
3. **Tìm operator đổi demand.** Kiểm tra `buffer`, `filter`, `flatMap`, `concatMap`, `publishOn`, `take`, `limitRate` và cấu hình prefetch.
4. **Kiểm tra nguồn.** Nguồn cold demand-aware như `Flux.range`, driver reactive, callback nóng, sink chia sẻ hay SDK blocking được bọc thành publisher? Nó có khả năng dừng phát?
5. **Đặt giới hạn tài nguyên.** Số inner active, kích thước queue/buffer, connection pool, heap, thời gian chờ và chiến lược khi quá tải.
6. **Quan sát outcome.** So sánh số phần tử được xin, phát, xử lý, bỏ, lỗi; không chỉ lấy một con số `request(n)` làm kết luận.
7. **Test bằng demand nhỏ.** Dùng `StepVerifier.create(source, 0L)`, `thenRequest(n)`, xác nhận không vượt số lượng và hủy đúng.
8. **Test tải thực tế.** Tăng concurrency và làm chậm downstream có kiểm soát; đo p95/p99, heap, GC, queue length và thời gian phục hồi.
9. **Giữ đúng nghiệp vụ.** Nếu tất cả event đều cần xử lý, dùng cơ chế nhận/đệm có độ bền và idempotency phù hợp; không chọn drop/latest vì tiện.

## 14. Nguồn tham khảo chính thống

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): định nghĩa `Publisher`, `Subscriber`, `Subscription.request(n)`, cancellation và giới hạn demand.
- [Project Reactor Reference – On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): cách demand đi ngược dòng, `BaseSubscriber`, `buffer`, prefetch và `limitRate`.
- [Project Reactor API – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): tra cứu chữ ký/toán tử `doOnRequest`, `limitRate` và họ toán tử backpressure theo phiên bản đang dùng.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP runtime, request/response publisher và tích hợp non-blocking.

## 15. Kết luận

Trong Project Reactor, **backpressure bắt đầu từ nhu cầu của downstream**. Subscriber nhận `Subscription` rồi yêu cầu một lượng phần tử bằng `request(n)`; tín hiệu nhu cầu đi **ngược dòng** qua các operator và có thể được điều chỉnh trước khi tới nguồn. Dữ liệu `onNext` di chuyển theo chiều ngược lại và phải tuân thủ demand tại từng subscription.

Hai bài học thực hành quan trọng nhất là:

1. **Theo dõi ở nhiều điểm:** `doOnRequest` cạnh subscriber và cạnh nguồn có thể cho số khác nhau, vì `buffer`, `filter`, prefetch và những toán tử ghép luồng thay đổi demand.
2. **Đừng nhầm tín hiệu request với khả năng điều khiển toàn hệ thống:** Reactor có thể quản lý demand của những publisher tương thích, nhưng nguồn nóng, HTTP, database, broker và công việc blocking còn phụ thuộc adapter, buffer và giới hạn riêng.

Khi gặp pipeline quá tải, hãy đo **demand → lượng phát → lượng đã xử lý → lượng đang chờ → lỗi/drop**, rồi chọn nơi giới hạn concurrency, queue hoặc nguồn phát. Đó là cách dùng backpressure để giữ hệ thống ổn định và vẫn đúng nghĩa vụ nghiệp vụ.
