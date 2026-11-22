# Giải phóng phần tử bị loại bỏ với doOnDiscard trong Project Reactor

## 1. Bối cảnh: một phần tử có thể biến mất trước khi tới Subscriber

Trong Spring WebFlux, nhiều phần tử reactive chỉ là giá trị Java bình thường và có thể được garbage collector thu hồi. Tuy nhiên, một số phần tử đang giữ **tài nguyên phải giải phóng chủ động**: vùng nhớ ngoài heap, Netty `ByteBuf` có reference count, Spring `DataBuffer` dùng pooled memory, handle tệp, hoặc đối tượng do ứng dụng quản lý.

Giả sử nguồn phát năm đối tượng, nhưng `filter` chỉ cho qua ba đối tượng. Hai đối tượng bị loại **không bao giờ đến Subscriber**. Nếu chúng đang giữ tài nguyên, callback xử lý ở Subscriber không thể đóng chúng. Tương tự, một toán tử có hàng đợi prefetch có thể giữ các phần tử chưa gửi xuống khi downstream hủy đăng ký hoặc xảy ra lỗi. Nếu không cleanup, tài nguyên còn tồn tại dù luồng đã dừng.

Project Reactor cung cấp `Flux.doOnDiscard(Class<R>, Consumer<? super R>)` và `Mono.doOnDiscard(...)` để đăng ký callback giải phóng khi **toán tử upstream có hỗ trợ discard** loại bỏ phần tử khỏi đường dữ liệu.

Sau bài này, bạn có thể giải thích sự khác nhau giữa discard, terminal và cancellation; đặt `doOnDiscard` đúng vị trí; viết callback an toàn/idempotent; xử lý `DataBuffer` đúng ranh giới ownership; nhận diện khi cần hook khác; và kiểm thử bằng Java 17+ cùng `StepVerifier`.

## 2. Discard là gì?

Trong luồng:

~~~text
Source → filter/skip/queue → Subscriber
              |
              +→ một phần tử không được chuyển tiếp
                    |
                    └→ discard (khi operator hỗ trợ)
                          |
                          └→ doOnDiscard(Resource.class, cleanup)
~~~

Một phần tử bị **discard** khi một toán tử chủ động bỏ nó hoặc dọn phần tử đã được giữ trong cấu trúc nội bộ mà không chuyển cho downstream, ví dụ:

- `filter`: phần tử không thỏa predicate.
- `skip`: phần tử nằm trong đoạn bị bỏ qua.
- Các dạng `buffer` có khoảng trống giữa các cửa sổ: một số phần tử không thuộc buffer nào.
- Một số toán tử có **prefetch queue**: các phần tử đã lấy từ upstream nhưng chưa gửi cho downstream có thể bị dọn khi `cancel` hoặc `onError`.

Theo Reactor Javadoc, **không phải mọi toán tử đều hỗ trợ `doOnDiscard`**. Hãy kiểm tra mục **Discard Support** ở Javadoc của từng toán tử, đặc biệt với chuỗi gồm `flatMap`, `publishOn`, `buffer`, `filterWhen` hoặc operator bên thứ ba.

### 2.1. Discard khác hoàn thành, hủy và lỗi

| Sự kiện | Ý nghĩa | Có tự gọi callback giải phóng mọi phần tử không? |
| --- | --- | --- |
| `onNext(value)` được gửi xuống | Subscriber đã nhận quyền xử lý một giá trị | Không. Bên nhận/owner phải giải phóng theo hợp đồng |
| Một `filter` bỏ `value` | Giá trị không tới downstream | Operator có Discard Support có thể gọi `doOnDiscard` |
| `onComplete` | Nguồn kết thúc thành công | Không tự giải phóng mọi đối tượng đã giao downstream |
| `onError` | Nguồn kết thúc với lỗi | Có thể khiến queue bị dọn nếu operator hỗ trợ discard, nhưng không thay thế mọi cleanup path |
| `cancel()` | Downstream yêu cầu ngừng nhận | Có thể dọn phần tử đang chờ trong queue có hỗ trợ discard; thời điểm phụ thuộc pipeline |
| Một Publisher lỗi giao thức phát `onNext` sau terminal | Tín hiệu đến quá muộn và không có đường downstream hợp lệ | Thuộc `onNextDropped`, không mặc nhiên là discard bình thường |

**Điểm quan trọng:** `doOnDiscard` xử lý **phần tử bị loại trước khi tới downstream** theo các nhánh được operator hỗ trợ. Nó không thay quyền sở hữu tài nguyên của đối tượng đã được giao thành công cho Subscriber.

## 3. Cú pháp, loại đối tượng và phạm vi tác dụng

Chữ ký giản lược:

~~~java
<R> Flux<T> doOnDiscard(
        Class<R> type,
        Consumer<? super R> discardHook
);
~~~

`Mono` có phương thức tương tự. `type` dùng để chọn phần tử phù hợp kiểu ở thời điểm discard, theo phép kiểm tra runtime tương tự `instanceof`. `discardHook` là hàm nhận chính đối tượng bị loại và thực hiện cleanup.

Ví dụ:

~~~java
Flux<Packet> filtered = packets
        .filter(packet -> packet.id() % 2 == 1)
        .doOnDiscard(Packet.class, Packet::release);
~~~

Đây là **đoạn minh họa**: `Packet` có phương thức `id()` và `release()`, `packets` là một `Flux<Packet>` của ứng dụng. Hook chỉ được gọi khi toán tử upstream thực sự loại bỏ một `Packet` và có hỗ trợ discard.

Với chuỗi trên, nếu `filter` loại `Packet(2)`, hook có cơ hội giải phóng nó. Nhưng nếu `Packet(1)` đi tới Subscriber, `doOnDiscard` **không** giải phóng `Packet(1)` chỉ vì pipeline kết thúc sau đó.

### 3.1. Đặt hook sau toán tử có thể discard

`doOnDiscard` có tính **local đối với pipeline** và các callback được truyền **về các toán tử upstream** phù hợp. Vì vậy vị trí thay đổi hiệu quả:

~~~java
// ĐÚNG: filter nằm upstream của doOnDiscard.
Flux<Packet> a = packets
        .filter(Packet::valid)
        .doOnDiscard(Packet.class, Packet::release);

// SAI nếu mục tiêu là dọn phần tử do filter ở dưới loại:
// filter ở downstream, nên không nhìn thấy hook này.
Flux<Packet> b = packets
        .doOnDiscard(Packet.class, Packet::release)
        .filter(Packet::valid);
~~~

Điểm đặt hook thường hợp lý là **ngay sau đoạn operator cần discard**, đủ downstream để tác động tới các operator upstream liên quan. Nếu sau đó có thêm toán tử downstream có thể loại bỏ phần tử, cần bảo đảm có hook phù hợp ở **sau cả toán tử đó**.

### 3.2. Hook ghép được và thứ tự callback

Theo Javadoc Reactor, nhiều `doOnDiscard` trên cùng đường xử lý là **additive**; hook được gọi theo thứ tự khai báo cho các phần tử phù hợp kiểu:

~~~java
Flux<Integer> result = Flux.range(1, 3)
        .filter(n -> n == 2)
        .doOnDiscard(Integer.class, n -> audit("first", n))
        .doOnDiscard(Number.class, n -> audit("second", n));
~~~

`audit` là hàm ứng dụng minh họa. Với 1 và 3 bị filter loại, cả callback `Integer.class` và `Number.class` đều phù hợp. **Không đăng ký hai callback cùng release một tài nguyên** nếu việc gọi hai lần không được thiết kế an toàn; dùng một callback cleanup và một callback chỉ ghi metric/log nếu có nhu cầu.

### 3.3. Tính đúng loại đối tượng ở vị trí discard

Nếu pipeline đổi kiểu phần tử, cần chọn kiểu **tại thời điểm nó bị loại**:

~~~java
Flux<String> labels = packets
        .filter(Packet::valid) // loại đối tượng Packet
        .map(Packet::label)    // chỉ những Packet còn lại mới thành String
        .doOnDiscard(Packet.class, Packet::release);
~~~

Hook `Packet.class` vẫn hữu ích cho `filter` upstream nếu có support, dù giá trị output cuối cùng là `String`. Đăng ký chỉ `doOnDiscard(String.class, ...)` không thể giải phóng `Packet` bị loại trước bước `map`. Luôn phân biệt kiểu đầu vào của operator với kiểu sau biến đổi.

## 4. Quy tắc quan trọng: callback phải idempotent và an toàn

Javadoc của `doOnDiscard` yêu cầu hook **idempotent** và an toàn khi gọi với bất kỳ instance phù hợp kiểu nào. *Idempotent* nghĩa là dù có nhiều đường cleanup hoặc hook được kích hoạt nhiều lần cho cùng đối tượng, kết quả giải phóng tài nguyên vẫn đúng và không gây double-free.

Một cách đơn giản để quản lý tài nguyên tự tạo là cờ nguyên tử:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

final class TrackedResource {
    private final AtomicBoolean released = new AtomicBoolean();

    void release() {
        if (released.compareAndSet(false, true)) {
            // Thực hiện cleanup đúng một lần.
        }
    }

    boolean isReleased() {
        return released.get();
    }
}
~~~

`AtomicBoolean.compareAndSet` bảo đảm một thread giành được quyền thực hiện cleanup. Nếu `release` ở thư viện ngoài **không idempotent** (ví dụ bộ đệm đếm tham chiếu), phải phân tích *ownership*: chỉ release một lần cho **mỗi reference thực sự sở hữu**, hoặc dùng wrapper/cơ chế kiểm soát phù hợp; không mù quáng gọi release hai lần rồi bắt lỗi để bỏ qua.

Hook nên **nhanh, không blocking, không phát sinh exception**. Nó có thể chạy trên thread xử lý tín hiệu hoặc thread dọn queue do cancel/error; công việc blocking trong hook có thể làm chậm pipeline. Nếu cleanup cần bất đồng bộ, `doOnDiscard` không cung cấp API `Mono<Void>` để chờ kết quả; hãy thiết kế vòng đời resource bằng `usingWhen` hoặc workflow có ownership rõ ràng.

### 4.1. Tại sao không dùng doFinally để release mọi phần tử?

`doFinally(signalType -> ...)` quan sát subscription kết thúc, gồm complete/error/cancel. Nó phù hợp cho cleanup **tài nguyên cấp subscription** (nếu có ownership và cơ chế rõ ràng), nhưng không nhận từng phần tử đã bị filter/prefetch queue loại bỏ.

Ngược lại, `doOnDiscard` nhận **đối tượng phần tử cụ thể** cần cleanup. Hai hook có mục đích khác nhau và có thể cùng hiện diện khi quản lý cả tài nguyên cấp subscription lẫn tài nguyên cấp phần tử, với điều kiện không release trùng.

## 5. Ví dụ Java 17+ chạy được: dọn cả phần tử giữ lại và bị loại

Ví dụ xây một mô hình `Packet` có `AtomicBoolean` để mỗi đối tượng chỉ được giải phóng một lần. Các `Packet` số chẵn bị `filter` bỏ sẽ do `doOnDiscard` giải phóng; các `Packet` số lẻ đi tới Subscriber được **chính Subscriber** giải phóng sau khi sử dụng.

Tạo dự án Gradle:

~~~text
reactor-discard-demo/
├── build.gradle
└── src/main/java/DiscardDemo.java
~~~

Nội dung `build.gradle` (Java 17, Reactor Core):

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DiscardDemo'
}
~~~

Nội dung `src/main/java/DiscardDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;

public class DiscardDemo {

    static final class Packet {
        private final int id;
        private final AtomicBoolean released = new AtomicBoolean();

        Packet(int id) {
            this.id = id;
        }

        int id() {
            return id;
        }

        void release() {
            if (released.compareAndSet(false, true)) {
                System.out.println("release=" + id);
            }
        }
    }

    public static void main(String[] args) {
        Flux.range(1, 5)
            .map(Packet::new)
            .filter(packet -> packet.id() % 2 != 0)
            .doOnDiscard(Packet.class, Packet::release)
            .subscribe(
                packet -> {
                    System.out.println("use=" + packet.id());
                    packet.release();
                },
                error -> System.out.println(
                        "error=" + error.getClass().getSimpleName()),
                () -> System.out.println("complete")
            );
    }
}
~~~

Chạy từ thư mục dự án bằng Gradle đã cài đặt:

~~~bash
gradle -q run
~~~

Nếu dự án có Gradle wrapper, có thể dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

Stdout do **chương trình** phát ra với nguồn `Flux.range` đồng bộ:

~~~text
use=1
release=1
release=2
use=3
release=3
release=4
use=5
release=5
complete
~~~

Giải thích:

1. `Packet(1)` qua `filter`, tới Subscriber, được sử dụng rồi release.
2. `Packet(2)` bị `filter` loại, `doOnDiscard` release trực tiếp; Subscriber không thấy số 2.
3. `Packet(3)` qua filter và được Subscriber release.
4. `Packet(4)` bị discard và release.
5. `Packet(5)` được dùng và release; cuối cùng downstream nhận `onComplete`.

Không có `release` lần hai vì `AtomicBoolean` giữ ngữ nghĩa cleanup một lần. **Ví dụ dùng Packet tự tạo chỉ để minh họa ownership**; `DataBuffer`/`ByteBuf` thực tế có reference count và quy tắc riêng, không thể sao chép nguyên cách dùng cờ nếu có nhiều reference hợp lệ.

## 6. Cancellation và queue: phần tử đã prefetch nhưng chưa chuyển tiếp

Một số toán tử như `publishOn`, `flatMap`, `buffer` có thể giữ phần tử trong queue để điều tiết backpressure. Khi downstream hủy, phần tử đã lấy từ upstream mà chưa được tiêu thụ vẫn cần được giải phóng:

~~~text
Upstream đã phát:    A   B   C   D
Toán tử đang giữ:        [B C D]
Downstream nhận:     A
Downstream cancel
Queue chưa gửi:          B C D → discard nếu operator hỗ trợ
~~~

Do đó, khi dữ liệu có tài nguyên, nên đặt `doOnDiscard` ở phía downstream của các toán tử có thể giữ và dọn phần tử. Ví dụ minh họa:

~~~java
// packetSource là Flux<Packet> do ứng dụng cung cấp.
Flux<Packet> pipeline = packetSource
        .publishOn(scheduler, 16)
        .doOnDiscard(Packet.class, Packet::release)
        .take(1);
~~~

Trong đoạn trên, `scheduler` cũng do ứng dụng cung cấp. **Đây không phải chương trình độc lập.** `publishOn` có thể đã prefetch nhiều `Packet`; nếu downstream nhận một phần tử rồi `take(1)` hủy, những phần tử tồn trong queue có thể được discard. **Không dự đoán số lượng hoặc thứ tự release trong môi trường nhiều thread** khi chưa kiểm soát scheduler và demand; các phần tử có thể chưa được tạo, đang truyền hoặc đã được giao cho downstream.

Đặt hook sau `publishOn` giúp upstream operator nhìn thấy handler, nhưng nếu cần dọn phần tử bị **một toán tử downstream khác** loại bỏ thì phải bố trí thêm hook sau vị trí đó. Với các toán tử ghép nguồn, có thể cần kiểm tra nhiều điểm và nhiều kiểu tài nguyên.

**Hủy không tự đồng nghĩa với lỗi.** `cancel` là tín hiệu điều khiển từ Subscriber đến Subscription, không phải `onError` hay `onComplete`. `doOnCancel` có thể quan sát hành động hủy, còn `doOnDiscard` xử lý **từng phần tử** bị dọn bởi toán tử.

## 7. Ứng dụng Spring WebFlux: DataBuffer và vùng nhớ pooled

Spring `DataBuffer` là abstraction cho bộ đệm dữ liệu. Với loại pooled, dữ liệu có thể nằm trong vùng nhớ ngoài heap do Netty hoặc backend tương tự quản lý; garbage collection của object Java không đủ để bảo đảm resource được release đúng lúc.

Spring hướng dẫn dùng `DataBufferUtils.release(dataBuffer)` khi code đã sử dụng xong bộ đệm và có quyền sở hữu, cũng như dùng:

~~~java
.doOnDiscard(DataBuffer.class, DataBufferUtils::release)
~~~

nếu pipeline có toán tử có thể loại bỏ bộ đệm hoặc hàng đợi có thể bị dọn do hủy/lỗi.

### 7.1. Ví dụ chuyển Flux<DataBuffer> thành byte[] một cách có ownership

Đoạn sau minh họa phương thức trong ứng dụng Spring WebFlux đã có `spring-web`, `spring-core` và Reactor. Nó chuyển từng buffer giữ lại thành `byte[]` độc lập:

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;

public final class BufferReader {

    public static Flux<byte[]> readNonEmpty(Flux<DataBuffer> incoming) {
        return incoming
            .filter(buffer -> buffer.readableByteCount() > 0)
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
            .map(buffer -> {
                try {
                    byte[] bytes = new byte[buffer.readableByteCount()];
                    buffer.read(bytes);
                    return bytes;
                } finally {
                    // Chỉ release buffer đã được chuyển vào map và
                    // thuộc quyền sở hữu của đường xử lý này.
                    DataBufferUtils.release(buffer);
                }
            });
    }
}
~~~

Đây là **đoạn minh họa tích hợp**, không có `main` và giả định `incoming` giao quyền sở hữu các buffer cho phương thức. Nếu source/framework vẫn đang sở hữu bộ đệm hoặc API yêu cầu chuyển giao ownership theo quy tắc riêng, phải điều chỉnh cách release tương ứng.

- Buffer rỗng bị `filter` bỏ: `doOnDiscard` release.
- Buffer có dữ liệu đi qua `map`: được đọc vào `byte[]` và release trong `finally`.
- `finally` xử lý cả trường hợp lỗi trong quá trình đọc/chuyển đổi.
- `byte[]` đã sao chép không còn phụ thuộc vào lifetime của `DataBuffer`.

**Không thêm `doOnNext(DataBufferUtils::release)` trước bước xử lý cần đọc buffer**: release quá sớm làm dữ liệu không còn hợp lệ. Cũng không release cùng một owned reference ở cả `doOnDiscard` và trong một cleanup path khác khi không có biện pháp tránh double-release. Với callback giải phóng thực tế phải tuân thủ reference-count và ownership của từng loại buffer.

### 7.2. Khi dùng WebClient, request body hoặc decoder

Trong Spring WebFlux, codec và HTTP stack có thể quản lý DataBuffer tự động ở một số API tầng cao. Ví dụ `bodyToMono(String.class)` giao String đã decode cho ứng dụng, không yêu cầu tự release `DataBuffer` vốn đã được codec tiêu thụ. Trái lại, nếu làm việc trực tiếp với `Flux<DataBuffer>` ở mức thấp, phải đọc rõ hợp đồng sở hữu/giải phóng.

Với `DataBufferUtils.join`, `DataBufferUtils.write`, `DataBufferUtils.read` hoặc biến thể release consumer, xem Javadoc từng API vì có thể có cơ chế giữ, nối, phát lại hoặc trả ownership khác nhau. Không áp một quy tắc “luôn tự release ngay trong onNext” cho mọi pipeline.

Trong hệ thống có tải lớn, việc không giải phóng `DataBuffer` có thể làm tăng **direct memory usage** dù heap Java không tăng tương ứng. Ngược lại, double release có thể khiến exception hoặc dữ liệu dùng sau khi free. Vì vậy câu hỏi cần trả lời là: **ai tạo, ai giữ, ai chuyển giao và ai phải release buffer này?**

## 8. Những nhánh doOnDiscard không bao phủ

Reactor Reference Guide phân biệt một số loại tình huống cleanup:

| Tình huống | Cơ chế liên quan | Ghi chú |
| --- | --- | --- |
| `filter`/`skip` loại bỏ giá trị hợp lệ theo thiết kế | `doOnDiscard` | Local hook, operator phải hỗ trợ Discard Support |
| Queue prefetch dọn do cancel/error | `doOnDiscard` ở vị trí downstream phù hợp | Không phải mọi operator đều hỗ trợ; xem Javadoc |
| Publisher không tuân thủ giao thức phát `onNext` quá muộn sau terminal | `Hooks.onNextDropped` | Hook toàn cục, không phải đường discard bình thường |
| Toán tử gặp lỗi khi xử lý `onNext` | `Hooks.onOperatorError` và xử lý của operator | Có thể cần cleanup theo đường lỗi riêng |
| Toán tử gom nhóm/giữ key hoặc collection đặc thù | Handler cleanup riêng của operator | Ví dụ state trong một số biến thể `distinct` |
| Resource cấp subscription như session/file/cursor | `using` / `usingWhen` | Dọn khi complete/error/cancel theo hợp đồng resource |
| Phần tử đã được chuyển cho Subscriber | Cleanup ở owner/downstream | `doOnDiscard` không tự release giá trị đã tiêu thụ |

Các hook toàn cục `Hooks.onNextDropped`/`Hooks.onOperatorError` tác động trên phạm vi rộng hơn, cần cấu hình có kiểm soát và đặc biệt chú ý khi chạy nhiều test hoặc nhiều thư viện trong cùng JVM. Không nên đặt hook toàn cục tùy tiện trong mỗi request WebFlux. Với một luồng cụ thể, ưu tiên local hook khi nó giải quyết đúng vấn đề.

### 8.1. Overlapping buffers và ownership phức tạp

Một số toán tử như `bufferWhen` có thể tạo **buffer chồng lấn**, tức cùng một đối tượng phần tử xuất hiện ở nhiều buffer. Khi một buffer bị discard, việc giải phóng ngay đối tượng bên trong có thể khiến buffer còn lại giữ **tham chiếu đã bị free**.

Với cấu trúc này, đừng đặt `doOnDiscard(List.class, list -> list.forEach(DataBufferUtils::release))` một cách máy móc nếu các buffer có thể chia sẻ element. Cần xác định ownership, copy/retain khi cho phép nhiều chủ, hoặc dùng xử lý riêng theo hợp đồng dữ liệu. Cleanup idempotent không phải cách duy nhất giải quyết: một object có **nhiều reference sở hữu hợp lệ** cần được release đúng số lần retain, và không được giải phóng khi vẫn còn owner khác.

### 8.2. Khi cleanup callback tự ném lỗi

Một hook cleanup mà ném exception có thể làm phức tạp đường lỗi của operator và che nguyên nhân gốc. Vì vậy callback nên ổn định, nhanh, có log/metric phù hợp, và kiểm soát ngoại lệ theo quy tắc tài nguyên của ứng dụng. Đừng biến `doOnDiscard` thành nơi gọi API mạng hoặc ghi DB blocking.

## 9. Kiểm thử bằng StepVerifier

Trong dự án Java 17 đã có `reactor-test` và JUnit 5, thêm các dependency test tương ứng với Reactor Core (ví dụ Gradle):

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/test/java/DiscardTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DiscardTest {

    @Test
    void filterDiscardsElementsBeforeSubscriber() {
        List<Integer> discarded = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 5)
                .filter(n -> n % 2 == 1)
                .doOnDiscard(Integer.class, discarded::add);

        StepVerifier.create(source)
                .expectNext(1, 3, 5)
                .verifyComplete();

        assertEquals(List.of(2, 4), discarded);
    }

    @Test
    void discardHookBeforeFilterDoesNotObserveFilterDiscard() {
        List<Integer> discarded = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 4)
                .doOnDiscard(Integer.class, discarded::add)
                .filter(n -> n % 2 == 0);

        StepVerifier.create(source)
                .expectNext(2, 4)
                .verifyComplete();

        assertTrue(discarded.isEmpty());
    }

    @Test
    void matchingHooksAreAdditiveInDeclarationOrder() {
        List<String> calls = new ArrayList<>();

        Flux<Integer> source = Flux.range(1, 3)
                .filter(n -> n == 2)
                .doOnDiscard(Integer.class, n -> calls.add("one:" + n))
                .doOnDiscard(Number.class, n -> calls.add("two:" + n));

        StepVerifier.create(source)
                .expectNext(2)
                .verifyComplete();

        assertEquals(List.of(
                "one:1", "two:1", "one:3", "two:3"), calls);
    }
}
~~~

Ba test này xác minh **đường discard có thể quan sát được**, phạm vi upstream của hook và thứ tự nhiều hook. Dùng `ArrayList` trong test là hợp lệ vì `Flux.range`/`filter` đồng bộ, không đưa scheduler vào. Nếu thay bằng nguồn bất đồng bộ, nên dùng collection concurrent hoặc xác nhận luồng test quan sát sau khi công việc kết thúc; tránh suy luận thứ tự callback giữa nhiều threads.

Test `doOnDiscard` với resource thật cần kiểm tra thêm: mỗi owned resource cuối cùng được release đúng theo quyền sở hữu; các phần tử đến Subscriber vẫn dùng được trước release; cancellation/error không để lại backlog; cleanup không chạy trùng gây double-free. Các test này cần kiểm soát scheduler và nguồn, không dựa trên `Thread.sleep` và timing ngẫu nhiên.

## 10. Thiết kế cleanup theo ownership: checklist nghiệp vụ

Trước khi đưa một loại tài nguyên qua `Flux`/`Mono`, cần xác định:

1. **Tài nguyên nào?** `DataBuffer`, `ByteBuf`, file handle, native memory hay resource application? Object Java thuần như `String`/`Integer` không cần release.
2. **Ai cấp phát?** Source tạo resource và chuyển quyền sử dụng cho downstream hay chỉ cho mượn?
3. **Ai xử lý phần tử thành công?** Bên nhận cuối cùng phải release đúng thời điểm, hoặc chuyển ownership rõ cho tầng tiếp theo.
4. **Operator nào có thể discard?** `filter`, `skip`, `publishOn`, `flatMap`, `take` hoặc toán tử khác; đọc mục Discard Support của phiên bản Reactor đang chạy.
5. **Hook đặt ở đâu?** Sau các toán tử upstream cần áp dụng; nếu nhiều điểm loại bỏ, cân nhắc phạm vi của mỗi hook và kiểu resource ở mỗi đoạn.
6. **Callback có idempotent và thread-safe không?** Không blocking, không mutate shared state không đồng bộ, không double-release.
7. **Khi cancel/error thì sao?** Queue có thể dọn; tài nguyên đã giao cho Subscriber cần chính Subscriber quản lý; resource cấp subscription dùng cơ chế khác.
8. **Có chia sẻ reference giữa nhiều buffer/subscribers không?** Nếu có, phải có retain/release hoặc copy theo ownership đúng.
9. **Đã kiểm thử đường bình thường, bỏ lọc, hủy, lỗi và xử lý đồng thời chưa?** Đặc biệt quan trọng với pooled direct memory và load production.

Bản chất của `doOnDiscard` là một cơ chế **cleanup mang tính cục bộ**, không phải bộ thu gom rác hoặc bảo đảm exactly-once tổng quát cho mọi tài nguyên trong pipeline. Khi có nhiều nhánh sở hữu resource, phải thiết kế vòng đời rõ ràng hơn một callback.

## 11. Lỗi phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ release trong `subscribe(onNext)` | Phần tử bị filter/skip không đến Subscriber, có thể rò rỉ | Đặt `doOnDiscard` sau operator bỏ dữ liệu |
| Đặt `doOnDiscard` trước `filter` cần quan sát | Hook không thấy discard xảy ra ở downstream | Chuyển hook sau filter |
| Tưởng mọi operator đều gọi hook | Một số toán tử không có Discard Support | Đọc Javadoc đúng phiên bản và kiểm thử |
| Gọi release trong `doOnNext` trước khi tầng khác sử dụng dữ liệu | Use-after-release hoặc dữ liệu không hợp lệ | Release tại owner cuối cùng sau khi sử dụng |
| Dùng nhiều hook đều gọi release trên cùng reference | Double-free / reference count âm | Một owner chịu cleanup, hook còn lại chỉ audit/metric |
| Cleanup không idempotent | Cancel/error và nhiều hook có thể dẫn tới cleanup sai | Bảo vệ quyền release, tuân thủ reference count |
| Dùng `doFinally` với một danh sách các phần tử không biết đã chuyển hay chưa | Có thể giải phóng nhầm phần tử thuộc downstream | Dùng `doOnDiscard` cho discard và quản lý ownership riêng cho phần tử đã phát |
| Dùng `Hooks.onNextDropped` thay cho discard bình thường | Global hook không phải cơ chế local cho filter | Dùng `doOnDiscard` với operator hỗ trợ |
| Giữ đối tượng trong overlapping buffers mà release khi một buffer bị bỏ | Buffer khác còn tham chiếu resource đã free | Copy hoặc retain/release theo số owner |
| Callback release gọi I/O blocking | Tắc luồng phát hoặc cleanup | Thiết kế cleanup nhanh; resource async dùng `usingWhen` |
| Nhầm complete với việc mọi phần tử đã release | Những phần tử đã giao downstream vẫn có thể do bên nhận sở hữu | Xác định giao thức ownership |
| Không đo direct memory, chỉ nhìn Java heap | Rò rỉ Netty pooled buffers khó nhận biết | Theo dõi allocator/direct memory, số buffer chưa release và kiểm thử cancel |

## 12. Tự kiểm tra

1. `filter` loại một `DataBuffer` trước khi Subscriber nhận. Ai dọn? **`doOnDiscard(DataBuffer.class, DataBufferUtils::release)` nếu hook được đặt đúng vị trí và quyền sở hữu cho phép release.**
2. Đặt `doOnDiscard` **trước** `filter` có nhìn thấy phần tử do chính filter ở sau loại không? **Không.**
3. `onComplete` có nghĩa mọi tài nguyên đã giao Subscriber đều được giải phóng không? **Không.**
4. `doOnDiscard` có tự dọn mọi phần tử trong mọi toán tử Reactor không? **Không; operator phải hỗ trợ Discard Support.**
5. Khi downstream `cancel`, vì sao doOnDiscard có ích? **Một số toán tử prefetch queue sẽ dọn phần tử đã nhận upstream mà chưa phát xuống.**
6. Vì sao callback phải idempotent? **Có thể có nhiều đường cleanup hoặc hook được áp dụng lại; double release gây lỗi.**
7. `Hooks.onNextDropped` khác `doOnDiscard` ở đâu? **Hook toàn cục dành cho tín hiệu bị drop ngoài luồng bình thường, ví dụ Publisher phát sau terminal; `doOnDiscard` là local cleanup cho những operator hỗ trợ discard.**
8. `DataBuffer` đã đi đến downstream, doOnDiscard có tự release ngay không? **Không; owner của nhánh xử lý thành công phải release đúng thời điểm.**
9. Buffer chồng lấn giữ cùng `ByteBuf` trong hai danh sách. Có được release ngay khi một danh sách bị bỏ không? **Chỉ khi ownership/reference-count cho phép; không làm hỏng owner còn lại.**
10. Vì sao test chỉ nhìn dữ liệu `onNext` là chưa đủ? **Cần kiểm tra các resource không được gửi downstream vẫn được release, kể cả khi cancel/error.**

**Ghi nhớ:** `doOnDiscard` giúp dọn phần tử bị loại bởi **operator upstream có hỗ trợ discard**, kể cả nhiều trường hợp dọn queue khi cancel/error. Đặt hook đúng vị trí, dùng đúng kiểu resource, giữ callback idempotent và nhanh. Với `DataBuffer`/`ByteBuf`, luôn xác định rõ ownership và xử lý riêng phần tử đã giao xuống downstream.

## Tài liệu tham khảo

- [Project Reactor Reference: Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html).
- [Project Reactor Flux Javadoc: doOnDiscard và Discard Support](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor Mono Javadoc: doOnDiscard](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Spring Framework: Data Buffers and Codecs — release và doOnDiscard](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- [Spring DataBufferUtils Javadoc — release, join, read, write](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html).
- [Reactor Reference: Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
