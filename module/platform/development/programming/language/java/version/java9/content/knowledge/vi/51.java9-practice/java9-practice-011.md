# Kiểm chứng cập nhật VarHandle và vòng đời Cleaner (Java 9+, thực hành Java 17+)

## 1. Mục tiêu và tiêu chí đạt

**`VarHandle`** và **`Cleaner`** đều xuất hiện từ Java 9 và tiếp tục có giá trị trên JDK hiện đại, nhưng giải quyết **hai vấn đề độc lập**:

- `java.lang.invoke.VarHandle`: truy cập một biến với các mức bảo đảm khác nhau về **tính nguyên tử (atomicity)** và **thứ tự bộ nhớ (memory ordering)**. Nó hữu ích cho bộ đếm, cờ trạng thái, cấu trúc dữ liệu concurrent và các thư viện cấp thấp.
- `java.lang.ref.Cleaner`: đăng ký một tác vụ **dọn dẹp tài nguyên** để có thể chạy khi đối tượng được GC xác định là **phantom-reachable**, hoặc **chạy ngay khi gọi `Cleanable.clean()`**. Với tài nguyên cần đóng đúng hạn, vẫn phải ưu tiên `AutoCloseable` và `try-with-resources`.

Bài thực hành sẽ **kiểm chứng bằng kết quả đo được**, không chỉ đọc Javadoc:

1. Tạo một `VarHandle` cho field `int`, chạy 4 luồng đồng thời. Dùng **CAS loop** và **`getAndAdd`** để thực hiện đúng 10.000 lượt tăng, không mất cập nhật.
2. Thử CAS với một giá trị `expected` sai để xác nhận kết quả `false`, không ghi đè giá trị hiện có.
3. Dùng `setRelease`/`getAcquire` làm tín hiệu giữa hai luồng, kiểm chứng dữ liệu được công bố đúng thứ tự.
4. Đăng ký một tài nguyên giả lập với `Cleaner`, gọi `close()` lặp lại và kiểm tra tác vụ cleanup chỉ được thực hiện **một lần**.
5. Dùng `try-with-resources` cho tài nguyên thứ hai, kiểm tra việc đóng chủ động. **Không yêu cầu GC phải chạy để test đạt** vì thời điểm GC và cleaning thread không được bảo đảm.

Ví dụ dùng **Java 17+** với API chuẩn, không cần dependency ngoài và không mở file/socket thật. Nếu áp dụng vào tài nguyên native/OS thực tế, phần cleanup phải được thay bằng logic giải phóng tương ứng và tuân thủ hợp đồng tài nguyên đó.

## 2. Hai loại vòng đời: biến chia sẻ và tài nguyên cần giải phóng

```text
        VarHandle / nhiều luồng                  Cleaner / vòng đời tài nguyên
        ──────────────────────                   ───────────────────────────
        Thread 1 ──CAS─────────┐                 new TrackedResource()
        Thread 2 ──getAndAdd───┼──> int value       |
        Thread 3 ──CAS─────────┤                   +── cleaner.register(referent, action)
        Thread 4 ──getAndAdd───┘                   |
                    |                             +── close()/clean() được gọi?
             getVolatile()                        |         |
             đọc đúng 10.000?                     |         +── Có → action tối đa 1 lần
                    |                             |
             assertion PASS                       +── Không → nếu GC thấy phantom-reachable,
                                                         Cleaner *có thể* chạy action về sau,
                                                         nhưng không có deadline bảo đảm
```

**Không nhầm hai cơ chế:**

- Atomic update là **bảo đảm về thao tác trên biến** giữa các thread; nó không tự quản lý file descriptor, native memory hoặc khóa OS.
- GC tự thu hồi **bộ nhớ Java heap**; `Cleaner` không phải lựa chọn để “giải phóng heap nhanh hơn”. Nó chỉ hỗ trợ cleanup cho **tài nguyên ngoài heap/hành vi giải phóng đặc biệt** do ứng dụng đăng ký.
- Một tác vụ cleanup dùng `AtomicInteger` để đếm số lần chạy, nhưng `AtomicInteger` ở đây là **dụng cụ kiểm chứng**, không phải chứng minh GC chạy.

## 3. VarHandle: truy cập biến và các access mode

### 3.1. Lấy handle với MethodHandles.Lookup

`VarHandle` là tham chiếu có kiểu mạnh đến một biến hoặc một nhóm biến: field của instance, static field, phần tử mảng, một số vùng dữ liệu có bố cục xác định. Cách phổ biến với instance field:

```java
private int value;

private static final VarHandle VALUE;
static {
    try {
        VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
    } catch (ReflectiveOperationException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

Đây là **mảnh mã bên trong class `Counter`** (mẫu đầy đủ ở mục 6). `MethodHandles.lookup()` kiểm tra quyền truy cập theo **lookup context**. Trong class này, nó được phép tìm chính field `private int value` của class. Ở class/module bên ngoài, phải xét access rights và JPMS module boundary; không được giả định tìm thấy mọi private field.

Một `VarHandle` có **variable type** và **coordinate types**:

| Đối tượng biến | Cách lấy handle | Tọa độ khi truy cập |
| --- | --- | --- |
| Instance field `Counter.value` | `lookup.findVarHandle(Counter.class, "value", int.class)` | `Counter` instance |
| Static field | `lookup.findStaticVarHandle(SomeClass.class, "flag", boolean.class)` | Không cần instance coordinate |
| Phần tử `int[]` | `MethodHandles.arrayElementVarHandle(int[].class)` | Mảng `int[]` và chỉ số `int` |

Ví dụ với instance field: `VALUE.getVolatile(counter)`, `VALUE.compareAndSet(counter, expected, next)`. Với mảng: `handle.getAndAdd(array, index, 1)`. Dùng sai coordinate hoặc kiểu tham số ở call site có thể gây `WrongMethodTypeException` khi thực thi.

`VarHandle` là một đối tượng không đổi; có thể chia sẻ một handle phù hợp giữa các thread. **Đừng đồng nhất bất biến của handle với thread-safety của mọi thao tác**: bảo đảm nằm ở **access mode** mà bạn chọn.

### 3.2. Mỗi access mode mang bảo đảm bộ nhớ khác nhau

| Nhóm | Phương thức thường dùng | Ý nghĩa |
| --- | --- | --- |
| Plain | `get`, `set` | Đọc/ghi thông thường, **không cung cấp ràng buộc thứ tự giữa các thread như volatile** |
| Opaque | `getOpaque`, `setOpaque` | Đảm bảo mức truy cập/coherence opaque, yếu hơn acquire/release |
| Acquire/Release | `getAcquire`, `setRelease` | Dùng để công bố dữ liệu trước khi bật cờ và quan sát dữ liệu sau khi nhận cờ đúng cách |
| Volatile | `getVolatile`, `setVolatile` | Cung cấp ngữ nghĩa volatile của Java Memory Model |
| CAS | `compareAndSet` | Cập nhật **nguyên tử** nếu giá trị bằng `expected`; trả `boolean` |
| Compare-and-exchange | `compareAndExchange` | Trả giá trị thực tế quan sát được trong phép so sánh/đổi |
| Atomic read-modify-write | `getAndAdd`, `getAndSet` | Cập nhật nguyên tử; trả **giá trị cũ** |
| Weak CAS | `weakCompareAndSet...` | Có thể thất bại giả (`spurious failure`); cần retry phù hợp |
| Fences | `fullFence`, `acquireFence`, `releaseFence` | Điều khiển thứ tự bộ nhớ ở mức thấp; chỉ dùng khi đã chứng minh cần thiết |

Đọc thật kỹ access mode: `setRelease` và `getAcquire` thích hợp cho một **giao thức công bố** được thiết kế đúng; `getVolatile` và `compareAndSet` có ngữ nghĩa đủ mạnh cho ví dụ bộ đếm. **Không trộn get/set plain với CAS/volatile tùy tiện** rồi suy ra tất cả các lời đọc/ghi đều được đồng bộ.

Các phép cập nhật có thể không hỗ trợ trên một số loại handle/kiểu biến. Ví dụ handle của field `final` không hỗ trợ ghi/atomic update. Có thể kiểm tra bằng:

```java
boolean supported = VALUE.isAccessModeSupported(
        VarHandle.AccessMode.GET_AND_ADD);
```

Đây là mảnh mã trong scope có `VarHandle VALUE`; nếu access mode không hỗ trợ mà vẫn gọi, có thể ném `UnsupportedOperationException`. Đừng coi `getAndAdd` là phép toán hợp lệ với mọi kiểu object hoặc mọi vùng nhớ.

### 3.3. Vì sao `value++` có thể mất lượt cập nhật?

Một biểu thức `value++` thông thường gồm các hành động logic đọc giá trị → cộng 1 → ghi lại; không tự trở thành một phép tăng nguyên tử chỉ vì field `volatile`. Hai thread có thể cùng đọc 7 và cùng ghi 8, khiến một lượt tăng bị **lost update**.

`VarHandle` cung cấp hai cách sửa phù hợp:

**CAS loop:**

```java
int oldValue;
do {
    oldValue = (int) VALUE.getVolatile(this);
} while (!VALUE.compareAndSet(this, oldValue, oldValue + 1));
```

- `getVolatile` đọc giá trị mới nhất theo ngữ nghĩa volatile.
- `compareAndSet(receiver, expected, update)` chỉ ghi khi giá trị hiện tại bằng `expected`. Nếu thread khác thắng trước, CAS trả `false`; loop đọc lại và thử lần nữa.
- **Chỉ thử một lần** là không đủ nếu nghiệp vụ yêu cầu mỗi lượt gọi phải làm tăng bộ đếm; cần loop hoặc xử lý thất bại riêng.
- Với kiểu `int`, khi đạt giới hạn lớn nhất, cộng 1 có thể tràn số; code sản xuất phải kiểm soát phạm vi hoặc dùng `long`/quy tắc khác tùy mục đích.

**Atomic get-and-add:**

```java
VALUE.getAndAdd(this, 1);
```

Lời gọi này thực hiện tăng nguyên tử trên biến có kiểu hỗ trợ. Nếu cần giá trị cũ:

```java
int previous = (int) VALUE.getAndAdd(this, 1);
```

`previous` là giá trị **trước khi tăng**, không phải giá trị cuối cùng của tất cả các thread. Trong ví dụ bộ đếm, ta **chỉ đối chiếu tổng sau khi mọi thread kết thúc**.

### 3.4. Kiểm chứng kết quả cạnh tranh phải có tiêu chí rõ

Bài thực hành dùng:

- 4 thread làm việc độc lập.
- Mỗi thread thực hiện 2.500 lượt tăng.
- Kỳ vọng chính xác: `4 × 2500 = 10000`.
- Chờ toàn bộ thread kết thúc bằng `Thread.join()` rồi mới đọc tổng.
- **Ném `AssertionError` nếu sai**, không chỉ in một con số để người đọc tự đoán đúng/sai.

Nếu test không có `join`/completion barrier, có thể đọc lúc thread chưa chạy xong, cho kết quả nhỏ hơn kỳ vọng **dù phép cập nhật nguyên tử hoàn toàn đúng**. Ngược lại, test chạy một lần đúng là bằng chứng cho case test đó; không phải chứng minh mọi thiết kế concurrent đều an toàn. Nên chạy test nhiều lần và dùng thêm concurrency testing phù hợp khi xây thư viện cấp thấp.

## 4. Kiểm chứng thứ tự bộ nhớ: `setRelease` và `getAcquire`

Một lỗi concurrent không nhất thiết liên quan việc tăng số. Khi một thread xây dữ liệu rồi báo “đã sẵn sàng”, thread đọc cần thấy dữ liệu được công bố **theo đúng thứ tự**.

Mẫu **single publication** dùng `Mailbox`:

```java
// Thread producer:
mailbox.payload = 42;
Mailbox.READY.setRelease(mailbox, true);

// Thread consumer:
while (!(boolean) Mailbox.READY.getAcquire(mailbox)) {
    Thread.onSpinWait();
}
int seen = mailbox.payload;
```

Đây là **mảnh mã minh họa**; cần có class `Mailbox` và handle `READY` như trong chương trình hoàn chỉnh. Khi consumer quan sát `ready=true` qua `getAcquire` tương ứng với `setRelease` của producer, các thao tác trước phép ghi release được công bố cho những thao tác sau phép đọc acquire; do đó consumer có thể đọc `payload=42` theo giao thức này.

- `Thread.onSpinWait()` chỉ là **gợi ý tối ưu spin loop** cho JVM/CPU, không cấp khóa, không thay vai trò của acquire/release.
- Spin không thời hạn có thể chiếm CPU và làm test treo. Demo có **deadline 5 giây** và ném lỗi khi timeout; trong hệ thống thật, ưu tiên `CountDownLatch`, `BlockingQueue`, `Future` hay primitive synchronization cấp cao khi có thể.
- Cờ trong mẫu là **one-shot**. Nếu tái sử dụng cho nhiều vòng gửi/nhận, phải thiết kế giao thức trạng thái/race/ABA khác; không đơn giản reset `ready=false` theo plain mode.
- Nếu cần quản lý lifecycle/locking phức tạp, `synchronized` và các API `java.util.concurrent` thường dễ kiểm tra hơn tự xây protocol bằng memory mode thấp.

## 5. Cleaner: những gì thực sự được bảo đảm

### 5.1. Đăng ký referent và cleanup action

`Cleaner.create()` tạo một cleaner có cơ chế theo dõi tham chiếu; `Cleaner.register(referent, action)` đăng ký `Runnable` cleanup cho một đối tượng cần theo dõi và trả `Cleaner.Cleanable`.

```java
private static final Cleaner CLEANER = Cleaner.create();
private final Cleaner.Cleanable cleanable;

TrackedResource(AtomicInteger releaseCount) {
    cleanable = CLEANER.register(
            this, new ReleaseAction(releaseCount));
}

@Override
public void close() {
    cleanable.clean();
}
```

Đây là mảnh mã thuộc class `TrackedResource` ở mục 6. Cách dùng thông thường: **tái sử dụng một Cleaner phù hợp** trong library/component, không nhất thiết tạo một cleaner thread cho mỗi resource instance.

Khi gọi `cleanable.clean()`:

1. Tác vụ cleanup được kích hoạt chủ động; không phải chờ GC.
2. Registration được hủy đối với cleanable đó.
3. **Cleaning action chạy nhiều nhất một lần** cho registration, kể cả khi `clean()` được gọi nhiều lần.
4. Vì vậy, `close()` có thể gọi `clean()` và thực hiện hợp đồng đóng idempotent đối với registration. Tuy nhiên, logic cleanup tự xây vẫn nên chịu được trạng thái nguồn lực thay đổi và tránh race ngoài phạm vi registration.

Nếu không gọi `close()`, chỉ khi đối tượng đã đủ điều kiện về **reachability** và Cleaner được thông báo, action mới có cơ hội chạy về sau. Không có bảo đảm **thời điểm** action được lên lịch hay kịp chạy trước khi JVM kết thúc.

### 5.2. Vì sao `Cleaner` không phải cách đóng file đúng hạn?

Các tài nguyên như file descriptor, socket, native handle, vùng native memory cần được giải phóng **ngay sau khi không còn dùng** để tránh cạn tài nguyên. GC quan tâm áp lực bộ nhớ của heap Java, **không chạy theo deadline của file descriptor**. Cleaner là tuyến dự phòng, không nên là cơ chế cleanup chính cho hoạt động có yêu cầu thời gian giải phóng rõ ràng.

Mẫu ưu tiên:

```java
try (TrackedResource resource = new TrackedResource(counter)) {
    // Sử dụng tài nguyên trong scope.
} // Java tự gọi resource.close() kể cả khi thoát scope do ngoại lệ.
```

Đây là mảnh mã minh họa. `TrackedResource` implement `AutoCloseable` và `close()` gọi `Cleanable.clean()`. Với IO thông thường, hãy dùng `FileInputStream`, `Socket`, `Files.newInputStream`... qua `try-with-resources`; không bọc tất cả bằng Cleaner nếu API đã có cơ chế đóng đúng hạn.

### 5.3. Tác vụ cleanup tuyệt đối không giữ tham chiếu mạnh tới referent

Đây là lỗi thiết kế Cleaner quan trọng nhất. Nếu `action` là lambda chụp `this` hoặc một inner class (không static) trỏ ngược tới object được đăng ký, Cleaner giữ action → action giữ referent → referent không trở thành phantom-reachable. **Cleanup dự phòng có thể không bao giờ chạy.**

Mẫu đúng:

```java
private static final class ReleaseAction implements Runnable {
    private final AtomicInteger releaseCount;

    ReleaseAction(AtomicInteger releaseCount) {
        this.releaseCount = releaseCount;
    }

    @Override
    public void run() {
        releaseCount.incrementAndGet();
    }
}
```

`ReleaseAction` là **static nested class**, chứa trạng thái độc lập cần cho cleanup. Nó không giữ `TrackedResource` và không truy cập các field của chính referent thông qua `this`. Trong resource thật, `State` độc lập có thể giữ native handle hoặc đối tượng quản lý tài nguyên phù hợp; không được chứa tham chiếu tới referent theo đường nào khác.

**Trong demo này**, `AtomicInteger` chỉ **đếm lần cleanup** để kiểm thử. Nó **không phải** native handle và demo không nói rằng file/socket nào đã được giải phóng.

### 5.4. Một lần cleanup không đồng nghĩa cleanup luôn xảy ra

`Cleaner.Cleanable.clean()` chỉ đảm bảo action của registration được thực thi **tối đa một lần**, không đảm bảo tuyến GC tự động sẽ luôn thực thi **đúng một lần trước một mốc thời gian**. Với resource còn được tham chiếu hoặc khi JVM thoát, cleanup dựa vào GC có thể không chạy. Các ngoại lệ phát sinh trong action khi chạy trên cleaner thread không được dùng làm kênh báo lỗi đáng tin; action nên ngắn, an toàn và không chặn lâu.

Vì vậy:

- **Unit test deterministic:** gọi `close()`/`clean()` chủ động, kiểm tra count bằng assertions; test có thể chạy ổn định trong CI.
- **Test hành vi GC (tùy chọn):** có thể dùng `WeakReference`, `ReferenceQueue` hoặc count/latch để quan sát sự kiện trong một khoảng thời gian có kiểm soát, nhưng **không được coi `System.gc()` là lời hứa sẽ dọn ngay**. Tránh tạo CI test mà chỉ PASS khi GC tình cờ lên lịch đúng lúc.
- **Production:** dùng explicit cleanup, metrics và resource ownership. Cleaner chỉ hỗ trợ dự phòng cho tình huống người dùng thư viện quên đóng.

## 6. Chương trình Java 17+ hoàn chỉnh cho VarHandle và Cleaner

Chương trình duy nhất bên dưới có cả kiểm thử cập nhật nguyên tử, tín hiệu acquire/release và vòng đời Cleaner. Nó không cần thư viện ngoài, không dùng API lỗi thời và không trông cậy vào GC chạy theo thời gian.

**Lưu thành file `VarHandleCleanerDemo.java`:**

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.ref.Cleaner;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class VarHandleCleanerDemo {
    private static final int THREADS = 4;
    private static final int UPDATES = 2500;

    private static final class Counter {
        private int value;
        private static final VarHandle VALUE;

        static {
            try {
                VALUE = MethodHandles.lookup()
                        .findVarHandle(Counter.class, "value", int.class);
            } catch (ReflectiveOperationException e) {
                throw new ExceptionInInitializerError(e);
            }
        }

        int read() {
            return (int) VALUE.getVolatile(this);
        }

        void incrementCas() {
            int oldValue;
            do {
                oldValue = (int) VALUE.getVolatile(this);
            } while (!VALUE.compareAndSet(this, oldValue, oldValue + 1));
        }

        void incrementAtomic() {
            VALUE.getAndAdd(this, 1);
        }

        boolean tryStaleUpdate() {
            return VALUE.compareAndSet(this, -1, 999);
        }
    }

    private static void runWorkers(Runnable task) throws InterruptedException {
        Thread[] threads = new Thread[THREADS];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(task, "worker-" + i);
        }
        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }
    }

    private static final class Mailbox {
        int payload;
        boolean ready;
        static final VarHandle READY;

        static {
            try {
                READY = MethodHandles.lookup()
                        .findVarHandle(Mailbox.class, "ready", boolean.class);
            } catch (ReflectiveOperationException e) {
                throw new ExceptionInInitializerError(e);
            }
        }
    }

    private static final class TrackedResource implements AutoCloseable {
        private static final Cleaner CLEANER = Cleaner.create();
        private final Cleaner.Cleanable cleanable;

        private static final class ReleaseAction implements Runnable {
            private final AtomicInteger releaseCount;

            ReleaseAction(AtomicInteger releaseCount) {
                this.releaseCount = releaseCount;
            }

            @Override
            public void run() {
                // Chỉ đếm sự kiện: ví dụ không giữ native handle.
                releaseCount.incrementAndGet();
            }
        }

        TrackedResource(AtomicInteger releaseCount) {
            cleanable = CLEANER.register(this, new ReleaseAction(releaseCount));
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter cas = new Counter();
        runWorkers(() -> {
            for (int i = 0; i < UPDATES; i++) {
                cas.incrementCas();
            }
        });

        Counter atomic = new Counter();
        runWorkers(() -> {
            for (int i = 0; i < UPDATES; i++) {
                atomic.incrementAtomic();
            }
        });

        int expected = THREADS * UPDATES;
        if (cas.read() != expected || atomic.read() != expected) {
            throw new AssertionError("Lost updates");
        }
        System.out.println("CAS updates: " + cas.read());
        System.out.println("getAndAdd updates: " + atomic.read());
        System.out.println("CAS with stale expected: " + cas.tryStaleUpdate());

        Mailbox mailbox = new Mailbox();
        Thread producer = new Thread(() -> {
            mailbox.payload = 42;
            Mailbox.READY.setRelease(mailbox, true);
        });
        producer.start();

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!(boolean) Mailbox.READY.getAcquire(mailbox)) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError("Mailbox timed out");
            }
            Thread.onSpinWait();
        }
        producer.join();
        System.out.println("Acquire/Release payload: " + mailbox.payload);

        AtomicInteger cleanupCount = new AtomicInteger();
        System.out.println("Cleaner before close: " + cleanupCount.get());
        try (TrackedResource resource = new TrackedResource(cleanupCount)) {
            resource.close();
            resource.close();
        }
        System.out.println("Cleaner after repeated close: " + cleanupCount.get());

        try (TrackedResource another = new TrackedResource(cleanupCount)) {
            // try-with-resources gọi close() khi kết thúc.
        }
        System.out.println("Cleaner after second resource: " + cleanupCount.get());

        if (cleanupCount.get() != 2) {
            throw new AssertionError("Cleanup count differs from 2");
        }
        System.out.println("Checks: PASS");
    }
}
```

### 6.1. Biên dịch và chạy

Dùng **JDK 17+**, tại thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 VarHandleCleanerDemo.java
java VarHandleCleanerDemo
```

Trong chương trình này, stdout được kiểm chứng là:

```text
CAS updates: 10000
getAndAdd updates: 10000
CAS with stale expected: false
Acquire/Release payload: 42
Cleaner before close: 0
Cleaner after repeated close: 1
Cleaner after second resource: 2
Checks: PASS
```

Mã đã được **biên dịch với `javac --release 17` và chạy thành công trên JDK 24**. Nếu môi trường tải CPU đến mức producer không được lên lịch trong 5 giây, test acquire/release sẽ cố ý thất bại bằng timeout thay vì treo vô hạn; khi đó hãy đánh giá môi trường test, không suy diễn ngay rằng ngữ nghĩa acquire/release sai.

Không cần tùy chọn JVM đặc biệt, module ngoài `java.base` hoặc thư viện Maven/Gradle. Nếu dùng named module, các API trong bài thuộc `java.base`, module được đọc mặc định.

### 6.2. Mỗi dòng output chứng minh điều gì?

| Dòng | Kết quả cần đạt | Bằng chứng trong demo |
| --- | --- | --- |
| `CAS updates: 10000` | Không mất cập nhật dù tranh chấp | `compareAndSet` lặp lại đến khi thành công, rồi `join` |
| `getAndAdd updates: 10000` | Atomic read-modify-write đúng số lượt | `getAndAdd(this,1)` được gọi từ 4 thread |
| `CAS with stale expected: false` | Không ghi đè khi `expected` sai | Giá trị hiện tại 10.000, expected `-1` |
| `Acquire/Release payload: 42` | Consumer quan sát dữ liệu được công bố | Producer ghi payload rồi `setRelease`; consumer chờ `getAcquire` |
| `Cleaner before close: 0` | Chưa cleanup resource nào | Bộ đếm `AtomicInteger` khởi tạo bằng 0 |
| `Cleaner after repeated close: 1` | Một registration chỉ cleanup một lần | Gọi `close` trong scope hai lần và thêm lần tự động khi kết thúc `try` |
| `Cleaner after second resource: 2` | Tài nguyên thứ hai được đóng qua `try-with-resources` | Thêm một registration được cleanup một lần |
| `Checks: PASS` | Assertions cuối cùng không thất bại | So khớp tổng bộ đếm và count cleanup |

**Giới hạn của kết quả:** chương trình kiểm chứng một bộ điều kiện test cụ thể. Nó **không chứng minh** rằng mọi thuật toán lock-free viết với VarHandle đều tuyến tính hóa đúng, không có ABA, không deadlock/livelock, hay mọi Cleaner đều tự chạy khi GC. Đó là các thuộc tính cần thiết kế và kiểm thử riêng.

## 7. Phân tích sâu các phép cập nhật VarHandle

### 7.1. CAS mạnh, CAS yếu và retry loop

`compareAndSet` là CAS mạnh: nếu phép so sánh không thành công, lý do theo ngữ nghĩa method là giá trị quan sát được không bằng `expected` tại thời điểm phép so sánh/đổi. Nó là một lựa chọn thích hợp để viết retry loop như demo.

Các phương thức `weakCompareAndSet...` có thể thất bại giả (`spurious failure`) ngay cả khi expected bằng giá trị hiện tại. Khi dùng weak CAS, **luôn thiết kế retry hoặc nhánh xử lý phù hợp**; không diễn giải một lần `false` là bằng chứng có thread khác đổi giá trị. Các biến thể khác nhau về memory ordering, nên chọn theo hợp đồng cụ thể chứ không thay lẫn tên method.

CAS không tự tránh **ABA** khi trạng thái có thể đổi từ A sang B rồi lại A giữa hai lần quan sát. Với bộ đếm chỉ tăng trong phạm vi test này, ABA không phải mục tiêu; với danh sách liên kết/concurrent stack, cần version tagging hoặc thiết kế khác khi phù hợp.

### 7.2. `getAndAdd` và xử lý tràn số

`getAndAdd` phù hợp khi muốn **một phép cộng nguyên tử không cần tự viết CAS loop**. Trên biến `int`, giá trị có thể wrap-around theo ngữ nghĩa `int`. Một bộ đếm event không được phép âm/tràn phải có chính sách xử lý; ví dụ dùng `long`, phát hiện biên hoặc chỉ ghi metrics không yêu cầu tăng vô hạn.

Vì `getAndAdd` trả giá trị **cũ**, nếu logic cần một sequence number mới thì phải dùng quy tắc chuyển đổi phù hợp và đánh giá tràn số. Không in `previous+1` như thể đó là tổng hiện tại của mọi thread sau khi thao tác kết thúc; trong môi trường cạnh tranh, các update khác có thể đã diễn ra.

### 7.3. Visibility và atomicity khác nhau

Một trường `volatile int` với `value++` vẫn có thể mất cập nhật. `volatile` kiểm soát visibility/ordering của từng truy cập, không biến chuỗi đọc-cộng-ghi thành atomic transaction. CAS/getAndAdd giải quyết chính xác phép đọc-sửa-ghi của field.

Khi dùng `VarHandle` trên field không khai báo volatile như trong demo, **access mode** quyết định mức bảo đảm của lời gọi. `VALUE.getVolatile(this)` là volatile read; `VALUE.get(this)` là plain read. Việc field không khai báo `volatile` không làm `getVolatile` biến thành plain read. Ngược lại, với field khai báo `volatile`, việc cố tình dùng `VarHandle.get` có thể tạo hành vi ordering khó hiểu nếu thiết kế trộn mode tùy tiện.

### 7.4. Các kiểu lỗi khi lấy/gọi handle

- `findVarHandle` có thể ném `NoSuchFieldException` hoặc `IllegalAccessException`; trong demo, bọc thành `ExceptionInInitializerError` để thất bại rõ ràng lúc khởi tạo class.
- Nếu truyền sai kiểu receiver/expected/newValue ở call site, có thể ném `WrongMethodTypeException` vì các access-mode methods là **signature polymorphic**.
- Nếu access mode không được hỗ trợ, ví dụ atomic write trên final field, có thể ném `UnsupportedOperationException`; dùng `isAccessModeSupported` khi triển khai generic utility.
- Nếu triển khai trong module khác, access control và JPMS boundary vẫn áp dụng. Không dùng hack truy cập private field xuyên module khi API có cách thiết kế rõ ràng hơn.
- Đừng coi một số thread chạy thử không gây lỗi là bảo đảm thuật toán memory ordering đúng trong mọi kiến trúc CPU/JVM; dùng thiết kế happens-before có thể chứng minh, hoặc primitive concurrency cao hơn.

## 8. Phân tích sâu vòng đời Cleaner

### 8.1. Trạng thái phải độc lập với đối tượng được theo dõi

Trong `TrackedResource`, `ReleaseAction` chỉ chứa `AtomicInteger` độc lập. Nó **không chứa `TrackedResource`** và không tham chiếu `this` của resource. Điều này giữ khả năng referent trở thành phantom-reachable nếu caller quên đóng.

**Sai về bản chất** (không khuyến nghị sử dụng):

```java
// Ví dụ phản diện, chỉ để hiểu lỗi tham chiếu:
cleanable = CLEANER.register(this, () -> this.releaseNative());
```

Lambda chụp `this` khiến action giữ mạnh referent, có thể chặn cơ chế cleanup dự phòng. Thay bằng một `static nested class State implements Runnable` chứa **handle độc lập**, tương tự mẫu ở mục 6. Đừng gọi method instance của referent từ action.

### 8.2. Action cần an toàn khi chạy bất đồng bộ

Khi Cleaner chạy action do GC, công việc có thể diễn ra trên thread riêng. Vì vậy:

- Action nên **ngắn, không blocking lâu**, không phụ thuộc GUI hoặc thread hiện hành.
- Không dùng thread-local của request hoặc context class loader như thể cleanup luôn chạy trên request thread.
- Bảo đảm dữ liệu mà action cần **đủ và độc lập**, đồng thời thread-safe nếu có thể bị truy cập/cập nhật ở nơi khác.
- Không dựa vào việc exception phát ra từ background cleanup sẽ làm request chính nhận lỗi; lỗi cần logging/metrics phù hợp và phải tuân theo quy tắc cleanup.
- Không giả định mọi action tự động chạy khi JVM tắt, kể cả có gọi `System.exit`.

Nếu một native handle phải đóng đúng hạn và cần báo lỗi cho caller, **explicit `close()` mới là giao diện đúng**; Cleaner chỉ giảm tác hại của trường hợp quên đóng khi JVM có cơ hội chạy.

### 8.3. Vì sao không kiểm thử bằng `System.gc()` + sleep cố định?

`System.gc()` là **lời đề nghị GC**, không cam kết sẽ lập tức xác định referent phantom-reachable, không cam kết cleaner thread sẽ được chạy trước timeout. Một test như sau là **không đáng tin cậy**:

```java
// KHÔNG dùng để kết luận Cleaner chắc chắn đã chạy:
System.gc();
Thread.sleep(100);
if (cleanupCount.get() != 1) {
    throw new AssertionError("GC did not run quickly enough");
}
```

Kết quả có thể khác theo GC, heap pressure, optimization, thread scheduling và thời gian JVM kết thúc. Thay thế là kiểm thử **đường đóng chủ động** với `Cleanable.clean()`, nơi hành vi tối đa một lần được API quy định và có thể assertion. Muốn quan sát fallback GC như integration experiment, phải công bố rõ đây là kiểm thử **nondeterministic**, giới hạn thời gian, không dùng làm SLA.

### 8.4. Tham chiếu reachabilityFence khi dùng native resource

Trong những wrapper có thể bị compiler/JIT coi là không còn cần tới object dù native handle của nó vẫn đang được dùng, `Reference.reachabilityFence(resource)` có thể giúp giữ **referent còn strongly reachable** cho đến vị trí đó trong chương trình. Đây là công cụ chuyên biệt, không tự gọi GC và không thay `close()`.

Mảnh mã minh họa khái niệm:

```java
try {
    // nativeUse(handle); // Lời gọi native thật trong ứng dụng chuyên biệt.
} finally {
    Reference.reachabilityFence(resource);
}
```

Cần import `java.lang.ref.Reference`; `resource` phải là tham chiếu của wrapper quản lý handle trong ứng dụng. Đây **không phải chương trình chạy độc lập** và không cần thiết với ví dụ đếm cleanup thuần Java ở mục 6. Chỉ thêm reachability fence khi phân tích lifetime của tài nguyên thực sự cho thấy cần thiết.

## 9. Kiểm thử có hệ thống: tách deterministic và nondeterministic

| Nội dung kiểm thử | Cách tổ chức | Điều có thể khẳng định |
| --- | --- | --- |
| 4 luồng CAS, mỗi luồng 2.500 lượt | Start, `join`, assert tổng 10.000 | Không mất lượt trong lần test và bài toán đó |
| 4 luồng getAndAdd | Tương tự | Atomic update đạt tổng kỳ vọng |
| CAS giá trị kỳ vọng sai | Gọi `compareAndSet(counter, -1, 999)` sau khi tổng là 10.000 | Trả `false`, không ghi 999 |
| Truyền payload theo release/acquire | Ghi payload trước release, consumer đọc sau acquire, có timeout | Message-passing test theo protocol one-shot |
| Cleaner gọi `close` ba lần | Đếm action qua `AtomicInteger` | Registration được dọn **một lần** |
| Resource thứ hai qua try-with-resources | Kiểm tra tổng cleanup tăng thêm 1 | Đóng chủ động được Java gọi khi thoát scope |
| Không gọi `close`, chờ GC | Có thể quan sát trong test riêng, kết quả không cố định | **Không dùng để khẳng định deadline hay tính chắc chắn** của auto-cleanup |
| Race giữa `close()` và Cleaner thread | Thiết kế state/action thread-safe, test concurrency khi có resource thật | Cần thêm chứng minh theo sở hữu tài nguyên và trạng thái thực tế |

**Kiểm chứng âm tính:** để tránh test “xanh giả”, có thể cố tình sửa thuật toán trong một bản thử riêng (ví dụ thay atomic update bằng read-then-write không bảo vệ), chạy nhiều lần và quan sát nguy cơ mất lượt. Tuy vậy, **một lần không xuất hiện race không chứng minh mã sai đã trở nên đúng**, và không nên để phiên bản cố tình sai trong source sản xuất.

Có thể chạy bài demo nhiều lần từ shell để kiểm tra stress, thay số luồng/lượt tăng có kiểm soát và dùng profiler/concurrency test tools phù hợp. Khi đánh giá performance, tách correctness test khỏi benchmark: độ trễ của atomic primitives phụ thuộc CPU, contention, tiered compilation và kiến trúc máy; đo thời gian bằng một lượt `System.nanoTime()` đơn lẻ không đủ đưa ra kết luận tốc độ.

## 10. Khi nào nên dùng API đơn giản hơn?

`VarHandle` mạnh nhưng là **API cấp thấp**. Nên lựa chọn theo nhu cầu:

| Mục đích | Lựa chọn dễ bảo trì hơn khi đủ yêu cầu |
| --- | --- |
| Bộ đếm số nguyên độc lập | `AtomicInteger` hoặc `AtomicLong` |
| Bộ đếm có tranh chấp cao, không cần tổng tuyến tính hóa ở mọi thời điểm | `LongAdder`, với việc hiểu semantics của `sum()` khi concurrent updates |
| Chờ một sự kiện producer hoàn tất | `CountDownLatch`, `CompletableFuture`, `BlockingQueue` |
| Trạng thái phức tạp cần bất biến nhiều field | `synchronized`, `ReentrantLock` hoặc mô hình immutable phù hợp |
| Đóng file, socket, stream, JDBC connection | `try-with-resources` và `AutoCloseable` có sẵn |
| Quản lý native handle do library tạo | Explicit `close()`, có thể bổ sung `Cleaner` làm safety net nếu thiết kế lifetime cho phép |

Không tạo `VarHandle` chỉ vì nó “mới từ Java 9” nếu `AtomicInteger.incrementAndGet()` đã đáp ứng bài toán. Không tự thêm `Cleaner` cho một object chỉ chứa `String`/`List` mà không quản lý tài nguyên đặc biệt: GC vốn đã dọn bộ nhớ Java heap.

## 11. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tổng lượt tăng nhỏ hơn 10.000 | Dùng `value++` không atomic hoặc đọc tổng trước khi thread hoàn tất | Dùng CAS loop/`getAndAdd` và `join`/completion barrier |
| CAS trả `false` dưới contention | Giá trị thay đổi trước khi thread đổi | Retry với giá trị đọc mới nếu nghiệp vụ cần tăng một lượt |
| `getAndAdd` trả giá trị “cũ” khiến hiểu nhầm | Hợp đồng method trả previous value | Phân biệt return của operation với tổng sau khi mọi thread xong |
| `WrongMethodTypeException` khi gọi VarHandle | Sai variable/coordinate type hoặc cast tại signature-polymorphic call site | Kiểm tra `varType()`, `coordinateTypes()`, kiểu `int`/`long` và receiver |
| `UnsupportedOperationException` ở field final | Access mode ghi/atomic không được hỗ trợ | Kiểm tra `isAccessModeSupported`; chọn đúng biến có quyền ghi |
| Consumer thấy cờ nhưng thấy payload sai | Thiết kế publication/happens-before thiếu đồng bộ, có thể trộn mode yếu sai | Dùng cặp release/acquire đúng hoặc primitive cao hơn |
| Busy spin gây CPU cao | Vòng `getAcquire` liên tục không chờ/chặn | Dùng `CountDownLatch`/`BlockingQueue` hoặc backoff phù hợp |
| Cleaner không bao giờ dọn resource quên close | Cleaning action giữ mạnh `this`/referent, hoặc referent vẫn sống | Dùng `static State` độc lập, loại đường giữ mạnh |
| Cleaner chạy muộn hơn mong đợi | Thời điểm GC/cleaning không được bảo đảm | Explicit `close()` + try-with-resources |
| Close lặp làm giải phóng hai lần | Cleanup tự xây chưa idempotent hoặc nhiều đường giải phóng song song | Dùng `Cleanable.clean()` và state giải phóng đúng cách, kiểm thử |
| Có Cleaner nhưng process exit vẫn rò rỉ tài nguyên trước lúc thoát | Cleaner không phải shutdown hook hay deadline mechanism | Có lifecycle shutdown/close chủ động |
| Test `System.gc()` lúc PASS lúc FAIL | Test ràng buộc timing GC không được bảo đảm | Test deterministic đường `clean()`; ghi rõ GC test chỉ quan sát |
| Code cleanup ném lỗi không thấy ở luồng chính | Cleanup do Cleaner thread thực thi không phải request call stack | Logging/metrics, logic an toàn và explicit close khi cần báo lỗi |
| Test demo PASS nhưng native resource thật vẫn lỗi | Demo chỉ đếm `AtomicInteger`, không giải phóng OS handle | Tích hợp native implementation và test đúng OS/điều kiện |

## 12. Bài tập mở rộng có tiêu chí cụ thể

1. **Mảng và VarHandle:** dùng `MethodHandles.arrayElementVarHandle(int[].class)` cho phần tử `array[0]`, cập nhật từ nhiều thread bằng `getAndAdd(array, 0, 1)`. Sau `join`, assert tổng bằng `threads × updates`. Lưu ý mảng `int[]` có tọa độ khác field handle.
2. **So sánh hai cách cập nhật:** chạy riêng CAS loop và `getAndAdd` nhiều lần với cùng workload; kiểm tra **đúng kết quả trước**, sau đó mới đo hiệu năng bằng công cụ benchmark chuẩn. Đừng coi stdout của một run là benchmark.
3. **Kiểm thử chống “đóng hai lần”:** tạo 10 `TrackedResource` riêng, gọi `close()` lặp với số lần khác nhau, assert cleanup count bằng 10 (nếu tất cả được đóng), không bằng tổng số lần gọi close.
4. **Tách State độc lập:** thay `AtomicInteger` đếm lượt trong `ReleaseAction` bằng một state mô phỏng ID handle và trạng thái “released”; bảo đảm action không giữ referent và việc cleanup vẫn tối đa một lần.
5. **Tương tác close và dùng tài nguyên:** xây API có `use()`, `close()` và chính sách từ chối `use()` sau close; kiểm thử race bằng synchronization rõ ràng. Không dùng mỗi Cleaner để kiểm soát trạng thái open/closed của resource.
6. **GC observation thử nghiệm:** tạo một resource mà caller cố ý không close, bỏ tham chiếu mạnh và quan sát cleanup bằng count/latch. Ghi rõ “có thể xảy ra sau một thời gian, không đảm bảo”; tuyệt đối không đòi test chạy đúng trong 100 ms hoặc tương đương.

## 13. Checklist ứng dụng thực tế

1. Xác định biến chia sẻ, invariant và memory-ordering yêu cầu trước khi lấy `VarHandle`.
2. Chọn access mode đúng: CAS/getAndAdd cho atomic updates; release/acquire cho publication protocol có thể chứng minh; tránh trộn mode tùy tiện.
3. Có tiêu chí deterministic trong test: số thread × số updates, completion barrier, assertions, timeout hợp lý.
4. Xử lý `WrongMethodTypeException`/access mode support theo thiết kế library; không giả định mọi handle có cùng coordinate/signature.
5. Kiểm tra giới hạn `int`/`long`, ABA và contention nếu use case là cấu trúc dữ liệu lock-free phức tạp.
6. Với tài nguyên cần đóng: **`AutoCloseable` + try-with-resources trước**, `Cleaner` chỉ fallback.
7. `Cleaner` action không tham chiếu referent; nên dùng static nested state. Cleanup ngắn, độc lập và thread-safe.
8. Kiểm chứng explicit `clean()` tối đa một lần bằng test; không dựa `System.gc()`/sleep để tuyên bố lifecycle bảo đảm.
9. Đối chiếu tài liệu API của JDK đang dùng; thử thực tế trên JDK/OS triển khai khi có native resources hoặc concurrency cấp thấp.
10. Với API chuẩn trên Java 17+ này, không cần kỹ thuật finalizer/unsafe nội bộ để giải quyết bài toán.

## 14. Tài liệu Java chính thống còn áp dụng

- Oracle Java SE 25: [`VarHandle` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/VarHandle.html) — variable/coordinate types, access modes, atomicity và memory ordering; API xuất hiện từ Java 9.
- Oracle Java SE 25: [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) — tìm `findVarHandle` và kiểm tra quyền truy cập field.
- Oracle Java SE 25: [`Cleaner` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Cleaner.html) — register, phantom reachability, action không tham chiếu referent và giới hạn khi JVM thoát.
- Oracle Java SE 25: [`Cleaner.Cleanable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Cleaner.Cleanable.html) — `clean()` unregister và thực thi cleanup action tối đa một lần.
- Oracle Java SE 25: [`Reference.reachabilityFence`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)) — giữ mạnh referent đến một thời điểm xác định trong code.
- Oracle Java SE 25: [`AtomicInteger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html) và [`AutoCloseable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html) — lựa chọn cấp cao hơn cho bộ đếm và đóng tài nguyên.
