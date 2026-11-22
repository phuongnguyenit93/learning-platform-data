# Thực thi nhiều nhất một lần và tính an toàn khi gọi đồng thời với Cleaner

## Mục tiêu

`java.lang.ref.Cleaner` được giới thiệu trong Java 9 để đăng ký một hành động dọn dẹp khi một object trở nên phantom-reachable, tức là không còn được chương trình sử dụng và đã đi đến mức tham chiếu cuối cùng trong chu trình reachability.

Cleaner cũng cho phép gọi dọn dẹp tường minh qua `Cleaner.Cleanable.clean()`. API bảo đảm hành động dọn dẹp của một đăng ký được thực thi **nhiều nhất một lần**, kể cả khi nhiều thread cùng gọi `clean()` hoặc khi lời gọi tường minh cạnh tranh với quá trình dọn dẹp do Cleaner thread thực hiện.

Các điểm cốt lõi:

- Một đăng ký có một cleaning action; action chạy tối đa một lần.
- Nhiều lời gọi `Cleanable.clean()` là an toàn và có tính idempotent đối với đăng ký đó.
- Nếu GC phát hiện referent đã phantom-reachable, Cleaner thread có thể thực thi action.
- Nếu ứng dụng gọi `clean()` trước, action được thực thi ngay trong thread gọi.
- Action không được giữ tham chiếu mạnh đến object được đăng ký.
- Cleaner là cơ chế dự phòng cho việc thu hồi tài nguyên; `AutoCloseable` và try-with-resources vẫn là cách chính để giải phóng tài nguyên đúng thời điểm.

## 1. Cleaner và Cleanable

Cleaner quản lý các object đã đăng ký và hành động cần chạy khi chúng không còn được sử dụng.

Tạo một Cleaner:

~~~java
Cleaner cleaner = Cleaner.create();
~~~

Đăng ký object cùng một Runnable:

~~~java
Cleaner.Cleanable cleanable =
        cleaner.register(resource, cleanupAction);
~~~

Có hai thành phần cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| `Cleaner` | Quản lý các đăng ký và thread thực thi action khi referent đủ điều kiện được dọn dẹp |
| `Cleaner.Cleanable` | Handle đại diện cho một đăng ký cụ thể; cho phép ứng dụng yêu cầu dọn dẹp tường minh bằng `clean()` |

Object truyền vào `register` là referent. Runnable là cleaning action. Khi referent trở nên phantom-reachable, Cleaner có thể chạy action. Nếu ứng dụng gọi `cleanable.clean()` trước, action được chạy ngay và đăng ký được loại bỏ khỏi quá trình chờ GC.

Cleaner sử dụng cơ chế phantom reference để phát hiện reachability. Ứng dụng không cần tự tạo hoặc quản lý PhantomReference cho trường hợp thông thường.

## 2. Bảo đảm thực thi nhiều nhất một lần

Với một `Cleanable`, action được thực thi tối đa một lần. Điều này áp dụng cho các trường hợp:

- Một thread gọi `clean()` nhiều lần.
- Nhiều thread đồng thời gọi `clean()`.
- Cleaner thread bắt đầu thực thi action cùng lúc ứng dụng gọi `clean()`.
- Ứng dụng gọi `clean()` trước khi referent trở nên phantom-reachable.

Sau khi action đã được thực thi, các lời gọi `clean()` tiếp theo không chạy action lần nữa.

Có thể hình dung trạng thái đăng ký như sau:

~~~text
                 register(referent, action)
                            |
                            v
                     Đang chờ cleanup
                       /          \
                      /            \
          GC phát hiện referent   Ứng dụng gọi clean()
             phantom-reachable        tường minh
                    \                 /
                     \               /
                      v             v
                     Một action được thực thi
                               |
                               v
                         Đã hoàn tất
                               |
                               v
                 Mọi lần clean() sau đều không chạy lại
~~~

Bảo đảm này là *at-most-once*, không phải *exactly-once*. Nếu action không bao giờ được kích hoạt vì referent vẫn còn reachable và ứng dụng không gọi `clean()`, action có thể không chạy. Cleaner không bảo đảm một thời điểm cụ thể mà GC phải thu hồi object.

## 3. Vì sao clean() an toàn khi nhiều thread gọi đồng thời?

`Cleaner.Cleanable.clean()` được thiết kế để có thể gọi đồng thời. Cơ chế nội bộ bảo đảm chỉ một lần thực thi action thắng cuộc; các lời gọi còn lại thấy đăng ký đã được xử lý và không thực thi lại action.

Ví dụ:

~~~java
Cleaner.Cleanable cleanable = cleaner.register(
        referent,
        () -> releaseNativeResource()
);

Thread first = new Thread(cleanable::clean);
Thread second = new Thread(cleanable::clean);

first.start();
second.start();

first.join();
second.join();
~~~

Dù hai thread gọi gần như cùng lúc, action của đăng ký chỉ chạy tối đa một lần.

Nếu một thread khác đang thực thi cleaning action, lời gọi `clean()` từ thread hiện tại có thể phải chờ action đó hoàn tất. Vì vậy, không nên xem `clean()` luôn là thao tác không chặn.

Tính an toàn đồng thời của Cleanable chỉ bảo đảm việc kích hoạt action một lần. Nó không tự bảo vệ mọi dữ liệu khác của ứng dụng, cũng không làm cho thao tác sử dụng tài nguyên và thao tác đóng tài nguyên trở nên an toàn đồng thời. Nếu một object vừa được dùng vừa có thể bị đóng từ thread khác, phần API sử dụng tài nguyên vẫn cần đồng bộ hoặc một giao thức trạng thái riêng.

## 4. Action chạy trên thread nào?

Cleaning action có thể chạy trên hai loại thread:

- **Cleaner thread:** khi referent trở nên phantom-reachable và Cleaner xử lý đăng ký.
- **Thread gọi clean():** khi ứng dụng gọi `Cleanable.clean()` tường minh.

Do đó, không giả định action luôn chạy trên một thread nền riêng. Khi gọi `clean()`, action có thể chạy đồng bộ ngay trong thread của caller và làm caller phải chờ.

Khi cleanup do GC kích hoạt, action chạy trên thread quản lý của Cleaner. Nếu action chặn lâu, ném lỗi hoặc thực hiện công việc nặng, nó có thể làm chậm các cleanup khác được quản lý bởi cùng Cleaner.

Một cleaning action tốt nên:

- Ngắn, có thời gian thực thi dễ dự đoán.
- Không chờ vô hạn hoặc thực hiện I/O blocking kéo dài.
- Không phụ thuộc vào thread-local hoặc ngữ cảnh của thread đã tạo object.
- Không ném exception ra ngoài; tự xử lý và ghi nhận lỗi cần thiết.
- Chỉ giải phóng đúng tài nguyên mà state của action sở hữu.

Nếu việc đóng tài nguyên có thể blocking, hãy cung cấp phương thức `close()` tường minh để ứng dụng kiểm soát thời điểm và thread thực thi. Cleaner chỉ nên là đường dự phòng.

## 5. Không để cleaning action giữ referent

Đây là quy tắc quan trọng nhất khi sử dụng Cleaner.

Cleaner chỉ có thể chạy action sau khi object được đăng ký trở nên phantom-reachable. Nếu action giữ một tham chiếu mạnh đến chính object đó, object không bao giờ trở nên phantom-reachable và action không được kích hoạt bởi GC.

Ví dụ không nên dùng:

~~~java
class Resource {
    private final Cleaner.Cleanable cleanable;

    Resource(Cleaner cleaner) {
        // Lambda capture this: action giữ Resource sống.
        cleanable = cleaner.register(this, () -> release(this));
    }
}
~~~

Lambda trên capture `this`. Cleaner giữ action; action giữ Resource; Resource vì thế vẫn reachable và không thể được GC dọn dẹp.

Cách đúng là tách trạng thái cần giải phóng ra một lớp lồng tĩnh:

~~~java
private static final class State implements Runnable {
    private final AtomicBoolean released = new AtomicBoolean();

    @Override
    public void run() {
        if (released.compareAndSet(false, true)) {
            releaseNativeResource();
        }
    }
}
~~~

Đăng ký:

~~~java
private final State state = new State();
private final Cleaner.Cleanable cleanable =
        CLEANER.register(this, state);
~~~

`State` không có tham chiếu ngược đến Resource. Không dùng non-static inner class cho action nếu nó vô tình giữ outer object. Cũng cần kiểm tra các field, lambda, callback và object được State tham chiếu để bảo đảm không có đường tham chiếu mạnh quay lại referent.

## 6. Kết hợp Cleaner với AutoCloseable

Với tài nguyên cần giải phóng đúng thời điểm như file, socket, native handle hoặc lock, nên triển khai `AutoCloseable` và cung cấp `close()`.

Phương thức `close()` gọi `cleanable.clean()` để tái sử dụng cùng cleaning action. Nhờ bảo đảm at-most-once, nếu GC đã chạy action trước hoặc một thread khác đã gọi close, lời gọi tiếp theo không giải phóng tài nguyên lần nữa.

Mẫu thiết kế:

~~~java
public final class NativeResource implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicBoolean released = new AtomicBoolean();

        @Override
        public void run() {
            if (released.compareAndSet(false, true)) {
                releaseNativeResource();
            }
        }
    }

    private final State state = new State();
    private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, state);

    @Override
    public void close() {
        cleanable.clean();
    }

    private static void releaseNativeResource() {
        // Đóng native handle hoặc giải phóng tài nguyên thực tế.
    }
}
~~~

Dùng try-with-resources:

~~~java
try (NativeResource resource = new NativeResource()) {
    resource.use();
}
~~~

Khi ra khỏi khối try, Java gọi `close()` một cách xác định. Nếu người gọi quên close, Cleaner có thể thực hiện action khi object đủ điều kiện được GC, nhưng thời điểm đó không được bảo đảm.

Không dùng Cleaner để thay thế try-with-resources cho tài nguyên cần đóng theo một thời hạn hoặc ranh giới nghiệp vụ cụ thể.

## 7. State cần idempotent và an toàn với trạng thái tài nguyên

Bảo đảm action chạy tối đa một lần giúp tránh gọi lại cùng action thông qua Cleanable. Tuy nhiên, State vẫn nên quản lý việc giải phóng tài nguyên theo cách idempotent, đặc biệt khi tài nguyên còn có đường đóng khác hoặc nhiều lớp wrapper.

Có thể dùng `AtomicBoolean.compareAndSet`:

~~~java
if (released.compareAndSet(false, true)) {
    nativeHandle.close();
}
~~~

Chỉ thread chuyển trạng thái từ false sang true mới thực hiện thao tác giải phóng.

Nếu cleanup gồm nhiều bước, cần xác định rõ trạng thái khi một bước thất bại. Không đặt cờ released sau khi giải phóng nếu điều đó cho phép hai thread cùng bắt đầu giải phóng. Ngược lại, nếu đặt cờ trước rồi thao tác đóng thất bại, cần quyết định liệu có retry hay ghi nhận trạng thái lỗi; Cleaner không tự quyết định chính sách phục hồi này.

Nếu `use()` có thể chạy đồng thời với `close()`, hãy đồng bộ việc truy cập handle và đóng handle. AtomicBoolean chỉ bảo vệ chuyển trạng thái, không tự làm cho mọi thao tác trên native handle trở nên thread-safe.

## 8. Cleaner thread và reachabilityFence

Java 9 cung cấp `Reference.reachabilityFence(Object)` để bảo đảm một object vẫn được xem là strongly reachable đến vị trí gọi fence.

API này hữu ích khi wrapper đang dùng một tài nguyên gắn với object khác, nhưng JIT có thể xác định rằng biến tham chiếu không còn được sử dụng và coi object là không còn reachable sớm hơn vị trí mà lập trình viên trực giác mong đợi.

Ví dụ khái niệm:

~~~java
try {
    useNativeResource(resource);
} finally {
    Reference.reachabilityFence(resource);
}
~~~

Fence không khóa thread, không giữ object vĩnh viễn và không thay thế quản lý vòng đời. Nó chỉ đảm bảo reachability đến điểm fence trong lần thực thi đó.

Nếu một thao tác native phụ thuộc vào wrapper còn sống trong toàn bộ thời gian thực thi, đặt fence sau thao tác cuối cùng cần wrapper. Không dùng fence như cách trì hoãn cleanup tùy ý.

## 9. Ví dụ hoàn chỉnh: close tường minh và clean() đồng thời

Tệp `CleanerConcurrencyDemo.java`:

~~~java
import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CleanerConcurrencyDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicBoolean released = new AtomicBoolean();

        @Override
        public void run() {
            if (released.compareAndSet(false, true)) {
                System.out.println("release resource");
            }
        }

        boolean isReleased() {
            return released.get();
        }
    }

    private static final class Resource implements AutoCloseable {
        private final State state = new State();
        private final Cleaner.Cleanable cleanable =
                CLEANER.register(this, state);

        void use() {
            if (state.isReleased()) {
                throw new IllegalStateException("Resource is closed");
            }
            System.out.println("use resource");
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) throws Exception {
        try (Resource resource = new Resource()) {
            resource.use();
        }

        Object referent = new Object();
        AtomicInteger actionRuns = new AtomicInteger();
        Cleaner.Cleanable cleanable =
                CLEANER.register(referent, actionRuns::incrementAndGet);

        int threadCount = 4;
        ExecutorService executor =
                Executors.newFixedThreadPool(threadCount);
        CountDownLatch ready = new CountDownLatch(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < threadCount; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    cleanable.clean();
                    return null;
                }));
            }

            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not become ready");
            }

            start.countDown();

            for (Future<?> future : futures) {
                future.get();
            }
        } finally {
            start.countDown();
            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } finally {
                Reference.reachabilityFence(referent);
            }
        }

        System.out.println("concurrent cleanup count: " + actionRuns.get());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all CleanerConcurrencyDemo.java
java CleanerConcurrencyDemo
~~~

Stdout chính xác:

~~~text
use resource
release resource
concurrent cleanup count: 1
~~~

Phần đầu cho thấy try-with-resources gọi close tường minh và cleaning action chỉ giải phóng tài nguyên một lần. Phần sau cho bốn thread cùng gọi `clean()` trên một Cleanable; action chỉ tăng bộ đếm một lần.

Ví dụ giữ referent sống bằng `Reference.reachabilityFence` cho đến khi các lời gọi tường minh hoàn tất. Nhờ đó, kết quả kiểm tra không phụ thuộc vào thời điểm GC chạy.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ action chắc chắn chạy đúng lúc object không còn dùng | Cleaner phụ thuộc vào GC và không có deadline | Dùng close/try-with-resources cho giải phóng xác định |
| Gọi clean() nhiều lần và lo tài nguyên bị đóng lặp | Cleanable bảo đảm action chạy tối đa một lần | Dùng cùng Cleanable cho close và fallback cleanup |
| Dùng lambda capture this làm action | Action giữ referent reachable | Tách State thành static nested class |
| Dùng non-static inner class làm State | Inner class ngầm giữ tham chiếu outer object | Dùng static nested class hoặc object state độc lập |
| Cho rằng clean() luôn chạy trên Cleaner thread | Lời gọi tường minh chạy action trong caller thread | Thiết kế action an toàn với cả hai ngữ cảnh |
| Chặn lâu trong cleaning action | Có thể giữ Cleaner thread bận và làm chậm cleanup khác | Giữ action ngắn, tránh blocking |
| Nghĩ at-most-once đồng nghĩa exactly-once | Action có thể không bao giờ được kích hoạt nếu object còn reachable | Chủ động close; Cleaner chỉ là fallback |
| Cho rằng Cleanable bảo vệ mọi thao tác tài nguyên | API chỉ bảo đảm một lần chạy action | Đồng bộ use/close và trạng thái tài nguyên riêng |
| Quên giữ Cleaner sống | Cleaner không còn được tham chiếu có thể không thực hiện cleanup dự kiến | Quản lý Cleaner ở field static hoặc lifecycle cấp ứng dụng |
| Không xử lý lỗi trong action | Lỗi cleanup có thể làm mất thông tin hoặc ảnh hưởng thread thực thi | Bắt/ghi nhận lỗi phù hợp trong action |
| Dùng Cleaner thay AutoCloseable | Không kiểm soát được thời điểm GC | Cung cấp close và try-with-resources |

## 11. Checklist triển khai

- Tạo Cleaner có vòng đời đủ dài, thường ở cấp class hoặc service.
- Đăng ký referent cùng một action độc lập.
- Đảm bảo action và mọi object nó giữ không tham chiếu mạnh ngược về referent.
- Ưu tiên static nested State để tránh implicit outer reference.
- Dùng `Cleanable.clean()` trong close để giải phóng tường minh.
- Dựa vào at-most-once khi nhiều thread cùng gọi clean.
- Dùng AtomicBoolean hoặc trạng thái đồng bộ phù hợp cho việc giải phóng handle.
- Không giả định action luôn chạy trên Cleaner thread.
- Không để action blocking hoặc làm công việc nặng kéo dài.
- Không dựa vào Cleaner cho deadline hoặc tính đúng đắn của nghiệp vụ.
- Đồng bộ riêng thao tác sử dụng tài nguyên với thao tác đóng nếu chúng có thể cạnh tranh.
- Dùng `Reference.reachabilityFence` khi cần bảo đảm reachability đến một điểm cụ thể.

## 12. Tài liệu tham khảo

- [Cleaner — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Cleaner.Cleanable — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.Cleanable.html)
- [Reference.reachabilityFence — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object))
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)

Cleaner hỗ trợ chạy cleanup tối đa một lần ngay cả khi GC và nhiều thread cạnh tranh gọi clean. Để quản lý tài nguyên đúng thời điểm, hãy kết hợp Cleaner với AutoCloseable: close giải phóng tường minh, còn Cleaner là lớp dự phòng khi caller quên đóng.