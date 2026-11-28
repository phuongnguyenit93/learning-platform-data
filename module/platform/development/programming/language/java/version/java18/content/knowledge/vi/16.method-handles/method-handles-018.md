# Handle immutable và việc chia sẻ giữa nhiều luồng không làm receiver hoặc dữ liệu tự an toàn

## 1. Vấn đề: cùng một MethodHandle được gọi bởi nhiều thread

`java.lang.invoke.MethodHandle` là một tham chiếu có kiểu đến method, constructor, field hoặc một phép biến đổi lời gọi. Trong các thư viện serialization, routing, DI, mapper hoặc xử lý sự kiện, một handle có thể được tạo một lần rồi dùng lại trên nhiều thread nhằm tránh lặp công việc lookup.

Javadoc Java SE hiện hành nêu rõ: **method handles là immutable và không có visible state**. Với Java Memory Model (JMM), các trường nội bộ của handle có hành vi như các trường `final`, nên một handle được công bố đến ứng dụng luôn là đối tượng đã được tạo hoàn chỉnh, ngay cả khi tham chiếu handle được trao đổi qua một shared variable có data race.

Nhưng phát biểu trên chỉ áp dụng cho **cấu trúc của handle**. Một handle có thể trỏ đến method cập nhật biến instance, có thể gắn chặt một receiver bằng `bindTo`, hoặc giữ một tham chiếu đến mảng, collection, object có thể thay đổi. Không có điều khoản nào khiến các object đó tự động thread-safe.

```text
Thread A                               Thread B
   |                                      |
   +----- cùng tham chiếu MethodHandle ---+
                       |
                       v
              Handle immutable
                       |
                       v
             receiver / dữ liệu
                       |
            +----------+----------+
            |                     |
      có đồng bộ            không đồng bộ
            |                     |
     kết quả theo hợp đồng   có thể có data race
```

Bài này tập trung vào ranh giới đó, để sử dụng `MethodHandle` đúng trong JDK hiện đại và tránh suy luận rằng handle an toàn tức là logic được gọi cũng an toàn.

## 2. Ba đối tượng khác nhau: handle, receiver và trạng thái nghiệp vụ

| Thành phần | Ví dụ | Điều được bảo đảm |
| --- | --- | --- |
| `MethodHandle` | Handle tới `Counter.increment()` | Bản thân cấu trúc handle không thay đổi sau khi tạo |
| Receiver | Một `Counter` được truyền vào hoặc gắn bằng `bindTo` | Có thể mutable; thread safety phụ thuộc cách thiết kế `Counter` |
| Dữ liệu phụ thuộc | `int[]`, `List`, `Map`, các object trong receiver | Không tự được khóa, copy hay làm immutable bởi handle |

Một handle có thể được dùng cùng lúc để gọi method trên **nhiều receiver độc lập**. Trường hợp đó khác với việc **nhiều thread cùng gọi trên một receiver duy nhất**.

Ví dụ:

```text
Một MethodHandle: Counter.increment()

Thread A -> counterA.increment()  (receiver A)
Thread B -> counterB.increment()  (receiver B)

So với:

Thread A ----+
             +--> counterShared.increment()
Thread B ----+
```

Trường hợp thứ hai cần kiểm tra tính nguyên tử, khả năng quan sát cập nhật và các invariant của `counterShared`. Điều này không thay đổi chỉ vì lời gọi sử dụng `MethodHandle.invokeExact` thay cho `counterShared.increment()`.

## 3. Ví dụ cơ bản: một handle duy nhất, receiver vẫn mutable

Code sau dùng `findVirtual` để tạo handle đến method instance `increment`. Chú ý receiver xuất hiện như tham số **đầu tiên** trong `MethodType` của virtual method handle.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HandleBasics {
    public static final class Counter {
        private int count;

        public int increment() {
            return ++count;
        }

        public int value() {
            return count;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle increment = MethodHandles.lookup().findVirtual(
                Counter.class,
                "increment",
                MethodType.methodType(int.class));

        Counter first = new Counter();
        Counter second = new Counter();

        // Type của virtual handle: (Counter)int.
        System.out.println(increment.type());

        int a = (int) increment.invokeExact(first);
        int b = (int) increment.invokeExact(second);

        System.out.println(a); // 1
        System.out.println(b); // 1
    }
}
```

`increment` là handle immutable, nhưng method đích thực hiện `++count`. Đoạn mã trên tuần tự, nên hai receiver riêng biệt đều có giá trị 1.

**Không suy ra** rằng có thể dùng một `Counter` với `++count` đồng thời từ nhiều thread. `++count` gồm nhiều hành động đọc, tính và ghi; nó không trở thành atomic khi đi qua một method handle.

## 4. Immutability của MethodHandle thực sự có nghĩa gì?

Một `MethodHandle` chứa thông tin kiểu (`MethodType`), thao tác nền và có thể chứa các adapter hoặc giá trị đã bind. Khi tạo xong, không có phương thức công khai để đổi đích hoặc chữ ký **ngay trong cùng instance handle**.

Các thao tác như sau tạo một adapter hoặc trả về handle phù hợp mà không sửa handle gốc:

- `asType(MethodType)` chuyển đổi kiểu lời gọi trong giới hạn hợp lệ.
- `bindTo(Object)` gắn giá trị vào tham số reference đầu tiên.
- `MethodHandles.insertArguments(...)` gắn các tham số ở vị trí chỉ định.
- `filterArguments`, `filterReturnValue`, `guardWithTest` và nhiều combinator khác tạo cấu trúc lời gọi mới.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandle identity = MethodHandles.identity(String.class);
MethodHandle adapted = identity.asType(
        MethodType.methodType(Object.class, Object.class));

System.out.println(identity.type()); // (String)String
System.out.println(adapted.type());  // (Object)Object
```

`identity` không bị sửa thành `(Object)Object`. Nếu kiểu adapter yêu cầu trùng sẵn với kiểu cũ, API có thể trả lại chính handle gốc. Immutability không có nghĩa mọi lần dùng combinator đều phân bổ một object khác.

### 4.1. An toàn cấu trúc không phải deep immutability

Một handle được bind với `String` không có vấn đề thay đổi nội dung `String`. Nhưng một handle được bind với `StringBuilder`, `ArrayList`, `int[]` hoặc một receiver mutable chỉ giữ **tham chiếu** tới object đó. Nó không biến object thành immutable, cũng không sao chép sâu trạng thái.

Vì vậy, hãy đánh giá object graph mà handle có thể chạm đến, không chỉ đánh giá kiểu `MethodHandle`.

## 5. invokeExact và invoke không tạo synchronization

`MethodHandle.invokeExact` đòi hỏi kiểu tại call site khớp đúng `MethodType` của handle. `invoke` có thể thực hiện một số chuyển đổi kiểu tương đương với adapter `asType`. Cả hai thực hiện thao tác đích, chứ không mang ý nghĩa khóa hoặc đồng bộ hóa.

```java
MethodHandle increment = MethodHandles.lookup().findVirtual(
        HandleBasics.Counter.class,
        "increment",
        MethodType.methodType(int.class));

HandleBasics.Counter counter = new HandleBasics.Counter();

int result = (int) increment.invokeExact(counter);
```

Nếu kiểu call site không khớp, có thể nhận `WrongMethodTypeException`. Lỗi kiểu này **độc lập** với việc receiver có thread-safe hay không.

Các lưu ý:

- `invokeExact` không tự tạo monitor lock.
- `invoke` không tự biến các field mà target sử dụng thành `volatile`.
- Adapter `asType` không tự bảo vệ một collection được truyền vào.
- Method đích chạy với những thuộc tính concurrency vốn có của method và object được gọi.

Một `synchronized` method vẫn có cơ chế monitor như bình thường khi gọi qua handle. Một method chỉ làm `++value` trên trường thường thì vẫn có vấn đề lost update khi nhiều thread gọi.

## 6. bindTo: gắn receiver không làm receiver bất biến

`bindTo(receiver)` tạo handle có tham số reference đầu tiên được gắn với object `receiver`.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

HandleBasics.Counter counter = new HandleBasics.Counter();

MethodHandle unbound = MethodHandles.lookup().findVirtual(
        HandleBasics.Counter.class,
        "increment",
        MethodType.methodType(int.class));

MethodHandle bound = unbound.bindTo(counter);

System.out.println(unbound.type()); // (Counter)int
System.out.println(bound.type());   // ()int

int value = (int) bound.invokeExact();
System.out.println(value); // 1
```

`bound` không chứa bản sao của `counter`. Nó tham chiếu đến đúng instance đã bind. Nếu thread A và B cùng gọi `bound.invokeExact()` thì cả hai thao tác cùng cập nhật `counter.count`.

```text
             MethodHandle bound (()int)
                       |
                   bindTo(counter)
                       |
              một Counter duy nhất
                   count: int
               /               \
           Thread A           Thread B
```

Bản thân `bound` là immutable và có thể chia sẻ. **Trạng thái `counter.count` không tự trở thành an toàn.**

### 6.1. bindTo không có nghĩa đóng băng một snapshot

Khi bind receiver, handle giữ lại danh tính object. Những lần gọi sau sẽ nhìn thấy hành vi của object ở thời điểm thực thi, tùy theo quy tắc visibility và synchronization của chính object đó.

Nếu cần một snapshot bất biến, tạo dữ liệu snapshot trước, ví dụ record chỉ chứa các giá trị immutable đã sao chép. Bind tới một receiver mutable không phải là snapshot.

## 7. Data race: ví dụ mất cập nhật

Giả sử `Counter.increment()` là:

```java
private int count;

public int increment() {
    return ++count;
}
```

Ở mức khái niệm, hai thread có thể xen nhau như sau:

```text
Giá trị ban đầu count = 0

Thread A              Thread B
read count -> 0
                      read count -> 0
compute 0 + 1
                      compute 0 + 1
write count = 1
                      write count = 1

Hai lần gọi increment nhưng kết quả cuối là 1.
```

Đây là vấn đề *lost update*. Nếu việc đọc và ghi biến dùng chung không được bảo vệ bởi quan hệ happens-before phù hợp, chương trình có data race theo JMM. Cùng một method handle được chia sẻ hoàn toàn không thay đổi chuỗi thao tác này.

Không nên viết test kiểu:

```java
// Sai mục tiêu: race không bắt buộc lộ ra trong mỗi lần chạy.
assertTrue(counter.value() < numberOfCalls);
```

Có lần chạy mất cập nhật, cũng có lần chạy tình cờ nhận đủ số lần tăng. Stress test chỉ có thể giúp phát hiện vấn đề, không chứng minh một chương trình không có data race.

## 8. Java Memory Model: tách việc công bố handle và chia sẻ state

Javadoc `MethodHandle` bảo đảm các trường nội bộ của handle có hiệu ứng như `final`. Vì vậy, một handle mà ứng dụng nhìn thấy luôn có cấu trúc hoàn chỉnh, ngay cả khi biến dùng để trao tham chiếu handle bị data race.

Điều này **không** có nghĩa:

- Việc gán lại một biến thường chứa handle sẽ lập tức được các thread khác nhìn thấy.
- Những lần ghi vào field mutable của receiver có `happens-before` với lần đọc của thread khác.
- Các thao tác trên mảng/collection đã bind sẽ được thực hiện nguyên tử.
- Một luồng công bố handle đồng thời công bố mọi cập nhật tương lai của tất cả object mà handle tham chiếu.

JLS §17.4.5 định nghĩa quan hệ **happens-before** để xác định thứ tự và khả năng quan sát giữa các hành động truy cập bộ nhớ. Các cơ chế phổ biến:

| Cơ chế | Ý nghĩa chính |
| --- | --- |
| `synchronized` | Unlock trên monitor happens-before lock tiếp theo trên cùng monitor |
| `volatile` | Write happens-before read tiếp theo trên cùng biến volatile |
| `Thread.start()` | Các hành động trước start happens-before hành động của thread được start |
| `Thread.join()` | Hoạt động của thread kết thúc happens-before thread join thành công |
| `Future.get()` | Hoạt động của task happens-before việc quan sát kết quả sau `get()` |
| `AtomicInteger`, `AtomicReference` | Có thao tác atomic và quy tắc memory consistency của atomic API |

Việc gọi qua `MethodHandle` không tạo một hàng mới trong bảng. Hãy chọn cơ chế đồng bộ dựa trên dữ liệu và invariant của method đích.

### 8.1. Kiểu an toàn khác với visibility

`MethodHandle` giữ kiểu lời gọi và access capability đã được xác lập khi tạo. Điều đó không bảo đảm các giá trị mutable được nhìn thấy nhất quán giữa thread.

Đừng nhầm ba khái niệm:

- **Type safety:** lời gọi và tham số tương thích với `MethodType`.
- **Visibility:** thread đọc thấy những write nào.
- **Atomicity:** một thao tác nghiệp vụ có thể bị xen giữa bởi thread khác hay không.

Một chương trình có thể đúng về type, thấy dữ liệu cập nhật, nhưng vẫn lost update vì `count++` không atomic.

## 9. Cách sửa 1: receiver dùng AtomicInteger

Khi invariant chỉ là một bộ đếm số nguyên, `AtomicInteger` là giải pháp rõ ràng. Thay receiver của ví dụ thành:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int value() {
        return count.get();
    }
}
```

Handle và receiver:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

AtomicCounter counter = new AtomicCounter();

MethodHandle increment = MethodHandles.lookup().findVirtual(
        AtomicCounter.class,
        "increment",
        MethodType.methodType(int.class));

MethodHandle bound = increment.bindTo(counter);

// Bound handle có MethodType: ()int.
int n = (int) bound.invokeExact();
```

Tính atomic đến từ `AtomicInteger.incrementAndGet()`, không phải từ `bindTo()` hoặc `invokeExact()`.

Khi nhiều thread cùng gọi handle bound trên một `AtomicCounter`, mỗi lần tăng được thực hiện theo hợp đồng atomic của counter. Bộ đếm có thể dùng lại an toàn, miễn là các invariant khác (nếu có) cũng được xử lý đúng.

## 10. Kiểm thử JUnit: chia sẻ một handle với receiver an toàn

Đây là kiểm thử **điều được bảo đảm**: sau nhiều task đồng thời, bộ đếm atomic có đúng tổng số lần tăng.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class SharedMethodHandleTest {
    static int invokeIncrement(MethodHandle bound) {
        try {
            return (int) bound.invokeExact();
        } catch (Throwable cause) {
            throw new AssertionError("MethodHandle invocation failed", cause);
        }
    }

    @Test
    void sharesHandleButAtomicReceiverControlsState() throws Exception {
        AtomicCounter counter = new AtomicCounter();
        MethodHandle unbound = MethodHandles.lookup().findVirtual(
                AtomicCounter.class, "increment",
                MethodType.methodType(int.class));
        MethodHandle bound = unbound.bindTo(counter);

        int threads = 4;
        int iterations = 10_000;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < threads; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();
                    for (int j = 0; j < iterations; j++) {
                        invokeIncrement(bound);
                    }
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> task : tasks) {
                task.get(10, TimeUnit.SECONDS);
            }

            assertEquals(threads * iterations, counter.value());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Một `MethodHandle` được dùng từ nhiều thread nhưng bộ đếm đúng vì receiver dùng atomic update. `Future.get` với timeout giúp caller quan sát task đã hoàn tất trước khi kiểm tra kết quả và không treo vô hạn nếu task bị kẹt. `shutdownNow()` trong `finally` tránh bỏ lại executor khi assertion hoặc task gặp lỗi; trong hệ thống thực tế, có thể bổ sung `awaitTermination` để quan sát dọn thread hoàn chỉnh.

Không nên lấy việc stress test chạy pass làm chứng minh tổng quát về JMM. Ở đây, tính đúng đến từ hợp đồng `AtomicInteger`; test chỉ kiểm tra tích hợp và bắt lỗi triển khai.

## 11. Cách sửa 2: synchronized bảo vệ invariant nhiều trường

Khi object phải cập nhật đồng thời nhiều field có quan hệ ràng buộc, `AtomicInteger` cho từng field riêng lẻ không đủ để bảo vệ **toàn bộ invariant**.

Ví dụ một tài khoản có số dư:

```java
public final class Account {
    private long balance;

    public Account(long openingBalance) {
        this.balance = openingBalance;
    }

    public synchronized void deposit(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        balance = Math.addExact(balance, amount);
    }

    public synchronized boolean withdraw(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        if (balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    public synchronized long balance() {
        return balance;
    }
}
```

Nếu cache handle tới `deposit`, nhiều thread vẫn có thể gọi qua một handle chung:

```java
MethodHandle deposit = MethodHandles.lookup().findVirtual(
        Account.class, "deposit",
        MethodType.methodType(void.class, long.class));

Account account = new Account(100);
deposit.invokeExact(account, 20L);
```

Chính monitor của `Account` trong `synchronized` method bảo vệ cập nhật `balance`. Method handle không thay đổi cơ chế đó.

Với nghiệp vụ chuyển tiền giữa hai tài khoản, cần thiết kế lock ordering hoặc transaction riêng để giữ invariant tổng thể và tránh deadlock. `synchronized` trên từng method không mặc nhiên làm mọi thao tác liên quan nhiều object thành atomic.

## 12. volatile tạo visibility nhưng không biến count++ thành atomic

Một cách sửa chưa đủ là đổi field thành `volatile int count` rồi giữ method `++count`:

```java
public final class VolatileCounter {
    private volatile int count;

    public int increment() {
        return ++count; // Vẫn không atomic.
    }
}
```

`volatile` giúp các lần đọc/ghi thuộc quy tắc visibility và ordering của biến volatile. Nhưng `++count` vẫn là thao tác đọc–tính–ghi, nên nhiều thread có thể mất cập nhật.

| Mục tiêu | Biện pháp thông dụng |
| --- | --- |
| Một cờ trạng thái được cập nhật và đọc giữa thread | `volatile boolean`, `AtomicBoolean` |
| Bộ đếm cần tăng atomic | `AtomicInteger.incrementAndGet()` |
| Đọc-sửa-ghi một giá trị theo điều kiện | `AtomicReference.compareAndSet()` hoặc lock |
| Invariant gồm nhiều field | `synchronized`, lock hoặc thiết kế immutable/transaction |
| Dữ liệu chỉ đọc sau khi xây dựng | Immutable object và công bố an toàn |

Đừng dùng `volatile` chỉ để làm chương trình “trông thread-safe”; phải xác định chính xác thao tác cần atomic và dữ liệu nào cần quan sát cùng nhau.

## 13. Cách sửa 3: VarHandle cho field với access mode rõ ràng

`VarHandle` là API khác trong `java.lang.invoke`, cung cấp những access mode như `getVolatile`, `setVolatile`, `compareAndSet` và `getAndAdd` khi kiểu field hỗ trợ.

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class VarCounter {
    private int count;

    private static final VarHandle COUNT;

    static {
        try {
            COUNT = MethodHandles.lookup().findVarHandle(
                    VarCounter.class, "count", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int increment() {
        int oldValue = (int) COUNT.getAndAdd(this, 1);
        return oldValue + 1;
    }

    public int value() {
        return (int) COUNT.getVolatile(this);
    }
}
```

`getAndAdd` thực hiện phép cập nhật atomic theo access mode của VarHandle. Nếu tạo một `MethodHandle` gọi `VarCounter.increment()`, thread safety đến từ `VarHandle.getAndAdd`, không phải từ việc wrapper là một method handle immutable.

Không trộn các truy cập plain vào field với atomic/volatile accesses một cách tùy tiện. Chính sách đọc/ghi field phải nhất quán với JMM và các invariant của ứng dụng.

## 14. insertArguments cũng có thể giữ dữ liệu mutable

Không chỉ `bindTo` mới giữ tham chiếu đến mutable object. `MethodHandles.insertArguments` có thể gắn tham số, gồm reference tới mảng hoặc collection.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BoundArrayDemo {
    public static int readAt(int[] values, int index) {
        return values[index];
    }

    public static void main(String[] args) throws Throwable {
        int[] values = {10, 20};

        MethodHandle read = MethodHandles.lookup().findStatic(
                BoundArrayDemo.class,
                "readAt",
                MethodType.methodType(int.class, int[].class, int.class));

        MethodHandle bound = MethodHandles.insertArguments(
                read, 0, (Object) values);

        System.out.println(bound.type()); // (int)int
        int before = (int) bound.invokeExact(0);
        values[0] = 99;
        int after = (int) bound.invokeExact(0);

        System.out.println(before); // 10
        System.out.println(after);  // 99
    }
}
```

Lời gọi `(Object) values` ở đây bảo đảm mảng `int[]` được truyền như **một giá trị tham số** của varargs `Object...`, thay vì giả định API có thể tự đóng băng nội dung mảng.

Handle `bound` không đổi, nhưng kết quả thay đổi vì dữ liệu `values` được sửa. Nếu cùng lúc nhiều thread ghi/đọc mảng này mà thiếu đồng bộ, có thể có data race hoặc snapshot không nhất quán.

Nếu dữ liệu phải cố định theo thời điểm tạo handle, hãy sao chép trước rồi không để mã khác sửa bản sao:

```java
int[] snapshot = values.clone();
MethodHandle boundToSnapshot = MethodHandles.insertArguments(
        read, 0, (Object) snapshot);
```

`clone()` ở đây tạo bản sao mảng primitive. Không để lộ `snapshot` cho code có thể sửa nó. Đối với object graph có cấu trúc phức tạp, `clone` nông hoặc `List.copyOf` chưa chắc tạo ra deep immutability.

## 15. MethodHandle gọi collection không bảo vệ collection

Ví dụ một handle tới `List.add(Object)` có thể được chia sẻ, nhưng `ArrayList` không an toàn cho các thao tác cấu trúc đồng thời:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.ArrayList;
import java.util.List;

List<String> list = new ArrayList<>();

MethodHandle add = MethodHandles.publicLookup().findVirtual(
        List.class, "add",
        MethodType.methodType(boolean.class, Object.class));

MethodHandle boundAdd = add.bindTo(list);
boolean accepted = (boolean) boundAdd.invokeExact((Object) "A");
```

Không có gì trong `boundAdd` bảo vệ array backing, `size` hoặc cơ chế thay đổi cấu trúc của `ArrayList`.

Nếu cần nhiều thread thêm phần tử, chọn cấu trúc và hợp đồng phù hợp, ví dụ `ConcurrentLinkedQueue`, `CopyOnWriteArrayList` cho workload nhiều đọc/ít ghi, hoặc collection có khóa. Nếu dùng `Collections.synchronizedList`, thao tác lặp qua iterator vẫn cần tuân thủ hướng dẫn đồng bộ bên ngoài khi phù hợp.

Thay data structure hoặc cách truy cập là giải pháp cho concurrency; thay `invokeExact` bằng `invoke` thì không.

## 16. Dữ liệu immutable giúp dùng chung handle dễ hơn

Một hướng khác là tránh thay đổi trạng thái sau khi tạo. Ví dụ record dùng thành phần immutable:

```java
public record Price(String currency, long minorUnits) {
    public Price {
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Missing currency");
        }
    }

    public long withTaxIncluded(long taxMinorUnits) {
        return Math.addExact(minorUnits, taxMinorUnits);
    }
}
```

`Price` có các thành phần `String` và `long`, không có collection mutable. Nhiều thread có thể đọc cùng một `Price` đã được tạo đúng cách mà không cần đồng bộ hóa cho việc đọc trạng thái immutable.

Có thể tạo một handle đến method:

```java
MethodHandle calculate = MethodHandles.lookup().findVirtual(
        Price.class, "withTaxIncluded",
        MethodType.methodType(long.class, long.class));

Price price = new Price("VND", 100_000);
MethodHandle bound = calculate.bindTo(price);

long result = (long) bound.invokeExact(10_000L);
```

Ở đây method không sửa receiver. Khi dùng nhiều thread, sự đơn giản đến từ **thiết kế bất biến của dữ liệu và phép tính**, không phải vì handle đã tự thay đổi tính chất method.

Một `record` chứa `List` hoặc mảng vẫn có thể bị thay đổi thông qua tham chiếu tới thành phần đó. Record mặc định không deep-copy các object mutable; nếu cần immutable thực sự, hãy copy và đóng đường sửa ở biên construction.

## 17. Chia sẻ một handle qua static final, volatile hoặc AtomicReference

### 17.1. Một handle cố định

Đối với một handle không thay đổi trong suốt vòng đời chương trình, `static final` là cách đơn giản:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public final class IntOperations {
    public static final MethodHandle IDENTITY = MethodHandles.identity(int.class);

    private IntOperations() {
    }
}
```

Trường `static final` được khởi tạo theo cơ chế class initialization của JVM. Đây là cách công bố handle rõ ràng, nhưng receiver và dữ liệu truyền vào khi gọi vẫn phải có chiến lược concurrency riêng.

### 17.2. Thay handle đang dùng ở runtime

Bản thân mỗi handle immutable, nhưng một biến có thể được cập nhật để trỏ sang handle khác. Nếu thay đổi từ thread A và đọc từ thread B, hãy công bố việc đổi tham chiếu bằng `volatile` hoặc atomic reference:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;
import java.util.Objects;

public final class SwappableIntFunction {
    private static final MethodType EXPECTED =
            MethodType.methodType(int.class, int.class);

    private volatile MethodHandle current;

    public SwappableIntFunction(MethodHandle initial) {
        update(initial);
    }

    public void update(MethodHandle next) {
        Objects.requireNonNull(next, "next");
        if (!next.type().equals(EXPECTED)) {
            throw new IllegalArgumentException("Expected (int)int handle");
        }
        current = next;
    }

    public int apply(int input) throws Throwable {
        MethodHandle snapshot = current;
        return (int) snapshot.invokeExact(input);
    }
}
```

Có thể tạo hai đích hợp lệ:

```java
import java.lang.invoke.MethodHandles;

MethodHandle identity = MethodHandles.identity(int.class);
MethodHandle always42 = MethodHandles.dropArguments(
        MethodHandles.constant(int.class, 42), 0, int.class);

SwappableIntFunction function = new SwappableIntFunction(identity);
int first = function.apply(7); // 7
function.update(always42);
int second = function.apply(7); // 42
```

`volatile` bảo đảm các thread có thể quan sát việc thay **tham chiếu handle** theo JMM. Nó không tự bảo vệ bất kỳ receiver mutable nào được handle mới tham chiếu tới.

Lấy `snapshot = current` một lần cho mỗi lời gọi giúp lần gọi đó sử dụng một handle xác định. Nó không ngăn một thread khác thay handle giữa hai lần gọi khác nhau.

### 17.3. Nếu cần thay đổi có điều kiện

`AtomicReference<MethodHandle>` hỗ trợ compare-and-set để cập nhật có điều kiện:

```java
import java.lang.invoke.MethodHandle;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<MethodHandle> active = new AtomicReference<>(identity);
boolean updated = active.compareAndSet(identity, always42);
```

Một lần nữa: atomic update cho **tham chiếu** không có nghĩa các thao tác được thực hiện bởi handle là atomic.

## 18. Phân biệt MethodHandle với MutableCallSite và VolatileCallSite

`MethodHandle` là immutable, nhưng JDK còn có các đối tượng `CallSite` chứa **target handle** có thể được đổi theo quy tắc riêng.

| Loại | Target có đổi được? | Visibility của thay đổi |
| --- | --- | --- |
| `ConstantCallSite` | Không sau khi được tạo hoàn chỉnh | Target cố định |
| `MutableCallSite` | Có, qua `setTarget` | Đọc/ghi như field thường; cần `syncAll` hoặc đồng bộ thích hợp |
| `VolatileCallSite` | Có, qua `setTarget` | Target có semantics như field `volatile` |

Ví dụ cập nhật đích có tính visibility kiểu volatile:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VolatileCallSite;

MethodHandle hello = MethodHandles.constant(String.class, "Hello");
MethodHandle bye = MethodHandles.constant(String.class, "Goodbye");

VolatileCallSite callSite = new VolatileCallSite(hello);
MethodHandle invoker = callSite.dynamicInvoker();

String before = (String) invoker.invokeExact();
callSite.setTarget(bye);
String after = (String) invoker.invokeExact();
```

`invoker` là một method handle với cấu trúc không đổi, nhưng khi gọi nó, đích mà `VolatileCallSite` trỏ tới có thể đã được cập nhật. Điều này **không mâu thuẫn** với immutability của `MethodHandle`: thay đổi nằm trong object `CallSite`.

Với `MutableCallSite`, `setTarget` không buộc các thread khác nhìn thấy target mới ngay. `MutableCallSite.syncAll(...)` là cơ chế để các thread nhận cập nhật theo hợp đồng của API, và có thể tốn chi phí. `VolatileCallSite` có visibility thường xuyên hơn nhưng có thể đánh đổi hiệu năng.

Không nhầm visibility của target call site với thread safety của dữ liệu mà target xử lý. Một `VolatileCallSite` trỏ đến `UnsafeCounter.increment()` vẫn có nguy cơ lost update nếu nhiều thread dùng chung receiver không đồng bộ.

### 18.1. In-flight invocation

Nếu thread đã bắt đầu gọi target cũ trước khi call site được cập nhật, thay đổi target không hoàn tác lần gọi đang thực hiện. Thiết kế cần chấp nhận rằng các request đang chạy có thể được xử lý bởi phiên bản cũ trong lúc cập nhật.

Nếu yêu cầu thay đổi atomic cho cả một nghiệp vụ gồm nhiều bước, cần protocol chuyển phiên bản, barrier hoặc locking thích hợp ở tầng ứng dụng.

## 19. MethodHandle có thể giữ mạnh receiver hoặc class loader

Một handle đã bind giữ reference đến receiver. Nếu đặt handle đó trong static cache sống lâu, receiver, class của receiver và defining class loader cũng có thể bị giữ lại lâu hơn vòng đời mong muốn.

```text
Static registry của framework
          |
          v
   bound MethodHandle
          |
          v
    receiver plugin
          |
          v
      plugin class
          |
          v
  defining ClassLoader
```

Do đó:

- Không cache một bound handle gắn với object plugin trong global static map nếu plugin cần unload.
- Với metadata dùng chung theo class, cân nhắc cache **unbound handle** để truyền receiver khi invoke.
- Có thể sử dụng `ClassValue` cho metadata per-class khi phù hợp với vòng đời class loader.
- Khi plugin dừng, xóa listener, task, thread context class loader và registry còn giữ handle/receiver.
- Không cho rằng immutable handle có nghĩa không giữ reference hoặc không gây class-loader leak.

Đây là vấn đề lifecycle độc lập với data race. Một hệ thống có thể hoàn toàn thread-safe nhưng vẫn leak class loader nếu giữ các handle bound trong registry toàn cục.

## 20. Phân biệt handle công khai và capability truy cập private member

Một method handle chứa quyền truy cập đã được kiểm tra khi tạo bằng `MethodHandles.Lookup`. Nếu lookup đủ quyền để tạo handle tới một member non-public, người nhận handle có thể sử dụng capability đó theo hợp đồng method handles.

Không công bố handle tới private method hoặc private field cho code không đáng tin chỉ vì `MethodHandle` là immutable. Immutability bảo đảm cấu trúc handle, **không giới hạn** người có tham chiếu được dùng capability.

Đồng thời, access permission không liên quan đến synchronization. Một handle hợp lệ để gọi private method vẫn không tự biến phương thức đó thành thread-safe.

Trong named modules, hãy tuân thủ `exports`, `opens`, `privateLookupIn` và các quy tắc lookup phù hợp thay vì dùng reflection để cố phá encapsulation.

## 21. Context Java 18: JEP 416 không đổi luật concurrency của receiver

JEP 416 từ Java 18 triển khai lại core reflection (`Method`, `Constructor`, `Field`) trên nền method handles. Mục tiêu chính là đơn giản hóa và thống nhất phần triển khai reflection, không phải thay đổi Java Memory Model hay bảo đảm phương thức đích an toàn đồng thời.

Điểm cần giữ đúng:

- `Method.invoke` và `MethodHandle.invokeExact` cuối cùng đều thực thi logic đích.
- Khi logic đích đọc/ghi state mutable không đồng bộ, vấn đề concurrency vẫn tồn tại.
- Thay API gọi không tự khắc phục data race.
- Hiệu năng phụ thuộc call site, JIT, cách handle được giữ và workload; đừng khẳng định một cách gọi luôn nhanh hơn cách khác.
- Nếu cache handle, lưu ý receiver binding, class-loader lifecycle và quyền truy cập.

Một thư viện tốt phải làm rõ ba hợp đồng riêng: **khả năng truy cập**, **hiệu năng**, và **concurrency**.

## 22. Kiểm thử concurrency theo hợp đồng, không dựa vào kết quả ngẫu nhiên

Một ma trận kiểm thử hữu ích:

| Kịch bản | Điều cần assert |
| --- | --- |
| Một handle, receiver immutable | Các thread nhận kết quả đúng theo input |
| Một handle, mỗi thread một receiver | State của từng receiver được giữ riêng |
| Một handle, một `AtomicCounter` chung | Tổng lần tăng bằng số lời gọi đã hoàn tất |
| Một handle, receiver có `synchronized` method | Invariant được bảo vệ |
| Một handle, một `UnsafeCounter` chung | Không viết assertion phụ thuộc việc race phải xuất hiện |
| `bindTo` mảng mutable | Thay mảng có thể làm kết quả handle khác đi |
| Thay handle qua `volatile` | Caller đọc snapshot phù hợp với phiên bản đã được công bố |
| `VolatileCallSite` thay target | Các lời gọi sau quan sát target theo volatile semantics |
| `MutableCallSite` thay target | Kiểm tra hợp đồng `syncAll`, không giả định setTarget đủ |
| Bound handle bị giữ trong registry | Kiểm tra cleanup và class-loader lifetime |

### 22.1. Dùng CountDownLatch để tạo tranh chấp có kiểm soát

`CountDownLatch` giúp nhiều worker bắt đầu cùng một thời điểm gần nhau. Nó hữu ích để tăng khả năng lộ lỗi và kiểm tra race, nhưng không tạo ra bằng chứng rằng code không có data race.

`Future.get()` hoặc `Thread.join()` giúp test quan sát công việc đã kết thúc. Nếu không chờ task hoàn tất mà kiểm tra counter ngay, test có thể fail đơn giản vì còn task đang chạy, không phải do handle hoặc receiver sai.

### 22.2. Kiểm thử cả trạng thái và khả năng nhìn thấy

Nếu test liên tục đọc một field từ thread khác, cần thiết lập happens-before hoặc dùng access mode rõ ràng cho dữ liệu được kỳ vọng. Một vòng lặp bận chờ trên field thường có thể bị JIT tối ưu theo cách khiến test không có tiến triển như mong đợi.

Không chẩn đoán một vòng lặp bận chờ bằng cách đổi `invokeExact` thành `invoke`. Phải sửa dữ liệu chia sẻ: volatile, atomic, lock, queue hoặc message passing.

### 22.3. Kiểm thử vòng đời của bound receiver

Nếu framework hỗ trợ plugin, thêm test hoặc soak test tạo receiver, bind handle, dùng handle rồi gỡ registration. Không assert GC bắt buộc unload class tại một thời điểm cố định. Theo dõi weak references và strong reference paths trong heap dump để chẩn đoán leak, đồng thời kiểm tra logic dọn registry.

## 23. Checklist cho code review

- [ ] Phân biệt `MethodHandle` immutable với receiver/data mutable.
- [ ] Kiểm tra từng target method có thread-safe theo hợp đồng hay không.
- [ ] Xác định handle unbound được chia sẻ với receiver nào.
- [ ] Xác định `bindTo`/`insertArguments` có giữ tham chiếu mutable không.
- [ ] Không gọi `count++` trên receiver chung mà chưa có đồng bộ.
- [ ] Không nghĩ `volatile` tự làm read-modify-write trở thành atomic.
- [ ] Dùng `AtomicInteger`, VarHandle atomic access hoặc lock theo invariant.
- [ ] Dùng dữ liệu immutable thực sự; không coi record hoặc `List.copyOf` là deep-copy mặc định.
- [ ] Việc cập nhật biến chứa handle có `volatile`/atomic/lock nếu các thread cần thấy phiên bản mới.
- [ ] Phân biệt `MethodHandle`, `MutableCallSite` và `VolatileCallSite`.
- [ ] Không dùng `MutableCallSite.setTarget` một mình như một bảo đảm thấy cập nhật giữa các thread.
- [ ] Kiểm tra callback hoặc handle bound trong static registry có giữ plugin loader không.
- [ ] Không xuất private-access handle cho code không đáng tin.
- [ ] Kiểm tra `MethodType` và xử lý `WrongMethodTypeException` theo đúng chữ ký.
- [ ] Test concurrency dựa trên invariant được bảo đảm, không dựa vào race xuất hiện ngẫu nhiên.
- [ ] Không suy hiệu năng hoặc thread safety từ riêng JEP 416.

## 24. Những ngộ nhận thường gặp

- **“MethodHandle immutable nên mọi method gọi qua nó đều thread-safe.”** Sai. Handle immutable, method đích vẫn có thể thao tác state mutable.
- **“Gọi chung một handle có nghĩa mỗi thread có bản sao receiver.”** Sai. `bindTo` giữ đúng receiver đã gắn; nếu cùng một object, state cũng được chia sẻ.
- **“bindTo tạo snapshot của object.”** Sai. Nó bind tham chiếu, không deep-copy.
- **“insertArguments chỉ gắn giá trị immutable.”** Sai. Có thể gắn mảng hoặc object mutable.
- **“invokeExact tự đồng bộ để bảo đảm tốc độ và tính đúng.”** Sai. Nó kiểm tra kiểu chính xác tại call site, không khóa state của target.
- **“Adapter asType đổi method gốc hoặc sửa handle gốc.”** Sai. Nó tạo hoặc trả về một handle thích hợp mà không mutate handle gốc.
- **“Data race lúc công bố handle làm cấu trúc handle không hoàn chỉnh.”** Javadoc nói các trường nội bộ handle có semantics như final; tuy nhiên đây không phải giấy phép tạo data race cho receiver hoặc các biến được cập nhật.
- **“volatile int đủ cho ++.”** Sai. Visibility không làm thao tác đọc–tính–ghi thành atomic.
- **“Dùng VolatileCallSite thì target method sẽ thread-safe.”** Sai. Volatile semantics áp dụng cho target reference của call site.
- **“MutableCallSite.setTarget luôn được thấy ngay.”** Sai. API quy định cần synchronization như `syncAll` khi muốn các thread chấp nhận cập nhật.
- **“Bất cứ handle immutable nào cũng có thể giữ mãi trong static cache.”** Sai. Bound handle có thể giữ receiver và class loader.
- **“JEP 416 khiến reflection tự xử lý concurrency.”** Sai. Thay đổi implementation không thay JMM của method đích.

## 25. Tài liệu tham khảo chính thức

- [MethodHandle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): immutability, final-field semantics, typed invocation, `bindTo`, `asType` và access capability.
- [MethodHandles — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookup, adapter, `insertArguments` và combinators.
- [MutableCallSite — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MutableCallSite.html): `setTarget`, `syncAll` và quy tắc visibility.
- [VolatileCallSite — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): volatile target semantics.
- [VarHandle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html): access modes, `getAndAdd`, compare-and-set và memory ordering.
- [java.util.concurrent — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/package-summary.html): memory consistency properties của executor, Future, locks và atomic classes.
- [JLS §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html): happens-before, data race, `synchronized`, `volatile` và các quy tắc JMM.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh từ Java 18 và giới hạn thay đổi của core reflection.

