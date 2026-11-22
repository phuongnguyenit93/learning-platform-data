# Field `volatile`: đọc/ghi và cập nhật nguyên tử trong Java Reflection

## 1. Vấn đề: `volatile` không có nghĩa là `++` nguyên tử

Với một trường Java khai báo `volatile`, Java Memory Model bảo đảm **ngữ nghĩa đọc/ghi volatile**: khả năng nhìn thấy thay đổi giữa các luồng (*visibility*), một số ràng buộc thứ tự (*ordering*), và tính nguyên tử của **một lần đọc hoặc một lần ghi**. Nhưng `volatile` không biến **chuỗi nhiều thao tác** thành một giao dịch nguyên tử (*atomic transaction*).

Điều đó vẫn đúng khi đọc/ghi trường bằng Reflection:

~~~java
Field field = Counter.class.getDeclaredField("value");
int before = field.getInt(counter);
field.setInt(counter, before + 1);
~~~

Đây chỉ là đoạn minh họa, cần đặt trong phương thức có quyền truy cập thích hợp và xử lý/khai báo checked exceptions. Nếu `Counter.value` là `volatile int`, `getInt` là một lần đọc volatile và `setInt` là một lần ghi volatile. **Hai lời gọi tách rời không tạo thành một phép tăng nguyên tử.**

Hai luồng có thể cùng đọc `0` rồi cùng ghi `1`, khiến một lần tăng bị mất (*lost update*).

> **Phân biệt:** *Atomic read/write* của một field khác với *atomic read–modify–write* (RMW) như `incrementAndGet`, `getAndAdd` hoặc `compareAndSet`.

## 2. Đọc metadata và giá trị của Field volatile

Cho lớp sau:

~~~java
class Counter {
    public volatile int value;
}
~~~

Ta có thể xem modifier và thao tác với instance:

~~~java
Field field = Counter.class.getDeclaredField("value");
boolean declaredVolatile = Modifier.isVolatile(field.getModifiers());

int value = field.getInt(counter);
field.setInt(counter, 5);
~~~

Các ví dụ này là đoạn trích Java, không phải chương trình độc lập; cần import `java.lang.reflect.Field`, `java.lang.reflect.Modifier`, có biến `counter`, và xử lý ngoại lệ phù hợp.

- `getDeclaredField("value")` tìm trường được khai báo tại lớp, kể cả private; `getField` chỉ tìm trường public đủ điều kiện. Tra cứu được metadata **không đồng nghĩa** có quyền đọc/ghi.
- `Modifier.isVolatile(field.getModifiers())` kiểm tra field được khai báo `volatile`. `volatile` là modifier của field, không phải “chế độ bật” cho từng đối tượng `Field`.
- `getInt(counter)` và `setInt(counter, number)` đọc/ghi trường kiểu `int`. Các accessor `get`/`set` tổng quát cũng truy cập trường nền; chúng không làm mất ngữ nghĩa volatile vốn có.
- Với field **instance**, receiver phải có kiểu phù hợp với lớp khai báo; field **static** có thể được truy cập bằng receiver `null` (`Field.get/set` bỏ qua giá trị receiver cho static field).
- Field private có thể cần `trySetAccessible()` hay `setAccessible(true)`; quyền deep reflection còn chịu giới hạn module. **Mở quyền truy cập không biến read–modify–write thành nguyên tử.**
- `Field` cung cấp các phép đọc/ghi đơn lẻ, không có `Field.incrementAndGet()` hoặc `Field.compareAndSet()`.

Nếu field volatile nhưng bạn thực hiện `field.getInt(...)`, tính toán, rồi `field.setInt(...)`, không có gì ngăn luồng khác xen vào giữa hai lời gọi.

## 3. `volatile` thực sự bảo đảm điều gì?

### 3.1. Visibility và happens-before

Một lần đọc/ghi volatile là *synchronization action*. Theo Java Memory Model, một lần ghi vào biến volatile *synchronizes-with* các lần đọc cùng biến volatile về sau trong synchronization order, tạo quan hệ *happens-before*. Điều đó cho phép truyền trạng thái qua một cờ báo:

~~~java
class Message {
    int data;
    volatile boolean ready;
}

// Luồng gửi:
message.data = 42;
message.ready = true;

// Luồng nhận:
if (message.ready) {
    System.out.println(message.data);
}
~~~

Đoạn trên mô tả hai luồng, không phải chương trình Java độc lập. Khi luồng nhận thấy `ready == true` từ lần ghi của luồng gửi, các ghi trước đó như `data = 42` được công bố tới những lần đọc sau của luồng nhận. Đây là giao thức *publication* đơn giản; nếu có các ghi cạnh tranh khác, phải xem lại bất biến và thứ tự của toàn bộ chương trình.

Đừng diễn giải thành “mọi field trong object đều volatile”. Nếu `volatile List<String> items`, phép đọc/ghi **tham chiếu `items`** có ngữ nghĩa volatile; nhưng `items.add(x)` vẫn phụ thuộc vào an toàn luồng của chính collection. `ArrayList` không trở thành thread-safe vì biến tham chiếu được khai báo volatile.

### 3.2. Nguyên tử cho một lần đọc hoặc một lần ghi

Một lần đọc/ghi giá trị của **chính biến volatile** có tính nguyên tử tương ứng với kiểu của nó. `volatile long` và `volatile double` được bảo đảm không bị chia thành hai nửa giá trị không nhất quán. Điều này khác bảo đảm cho chuỗi **đọc → tính toán → ghi**.

Với `volatile int count`, một lệnh `count = 7` là một ghi volatile; `int x = count` là một đọc volatile; nhưng `count++` vẫn gồm đọc giá trị cũ, tính giá trị mới, ghi lại.

### 3.3. Không phải khóa

`volatile` không cung cấp *mutual exclusion*. Nó không tự bảo vệ bất biến gồm nhiều biến, chẳng hạn “`available + reserved == total`”. Nếu cần cập nhật hai trường như một transaction, hãy xét `synchronized`/`Lock` hoặc một trạng thái bất biến thay thế nguyên tử.

## 4. Timeline của một lần tăng bị mất

Ban đầu `value = 0`. Hai luồng A, B cùng thực hiện:

~~~java
int oldValue = field.getInt(counter);       // volatile read
field.setInt(counter, oldValue + 1);        // volatile write
~~~

Một cách sắp xen kẽ hợp lệ:

| Bước | Luồng A | Luồng B | Giá trị chung |
| --- | --- | --- | --- |
| 1 | Đọc `0` | — | 0 |
| 2 | — | Đọc `0` | 0 |
| 3 | Ghi `1` | — | 1 |
| 4 | — | Ghi `1` | 1 |

Kết quả cuối là **1**, dù có hai yêu cầu tăng; mỗi đọc/ghi volatile đơn lẻ đều đúng quy tắc JMM. Dù mã là `x++`, `x += 1`, `getInt`/`setInt` hay `getVolatile`/`setVolatile`, nếu không có CAS, thao tác atomic RMW hoặc khóa, *lost update* vẫn có thể xảy ra.

## 5. Chương trình Java 17+ tái hiện lỗi một cách xác định

Lưu thành **`VolatileReflectionDemo.java`**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class VolatileReflectionDemo {
    public static class Counter {
        public volatile int value;
    }

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter();
        Field field = Counter.class.getDeclaredField("value");

        System.out.println("volatile: "
                + Modifier.isVolatile(field.getModifiers()));

        // Buộc cả hai luồng đọc 0 trước khi một luồng được ghi.
        CyclicBarrier bothRead = new CyclicBarrier(2);
        Runnable unsafe = () -> {
            try {
                int snapshot = field.getInt(counter);
                bothRead.await();
                field.setInt(counter, snapshot + 1);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        };

        Thread a = new Thread(unsafe, "unsafe-A");
        Thread b = new Thread(unsafe, "unsafe-B");
        a.start();
        b.start();
        a.join();
        b.join();
        System.out.println("Field get+set: " + field.getInt(counter));

        // Cùng field, nhưng dùng phép tăng nguyên tử.
        counter.value = 0;
        AtomicIntegerFieldUpdater<Counter> updater =
                AtomicIntegerFieldUpdater.newUpdater(
                        Counter.class, "value");

        Runnable safe = () -> {
            for (int i = 0; i < 1000; i++) {
                updater.incrementAndGet(counter);
            }
        };

        Thread c = new Thread(safe, "safe-C");
        Thread d = new Thread(safe, "safe-D");
        c.start();
        d.start();
        c.join();
        d.join();
        System.out.println("AtomicIntegerFieldUpdater: "
                + field.getInt(counter));

        // Một phép RMW nguyên tử qua VarHandle.
        VarHandle handle = MethodHandles.lookup().findVarHandle(
                Counter.class, "value", int.class);

        int oldValue = (int) handle.getAndAdd(counter, 1);
        int newValue = (int) handle.getVolatile(counter);
        System.out.println("VarHandle old=" + oldValue
                + ", new=" + newValue);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VolatileReflectionDemo.java
java VolatileReflectionDemo
~~~

Đầu ra chính xác:

~~~text
volatile: true
Field get+set: 1
AtomicIntegerFieldUpdater: 2000
VarHandle old=2000, new=2001
~~~

**Phần 1 — lost update:** `CyclicBarrier` khiến cả hai luồng đều phải hoàn thành `field.getInt(counter)` trước khi luồng nào gọi `setInt`. Cả hai đều lưu `snapshot = 0`; hai thao tác ghi kế tiếp đều ghi 1. Kết quả **luôn 1 trong thí nghiệm này**; ta không phụ thuộc vào lịch chạy ngẫu nhiên để phát hiện race.

**Phần 2 — cập nhật nguyên tử:** Hai luồng cùng tăng 1000 lần bằng `AtomicIntegerFieldUpdater.incrementAndGet`. Mỗi lần tăng là một read–modify–write nguyên tử trên cùng field, tổng cộng đúng **2000**.

**Phần 3 — VarHandle:** `getAndAdd(counter, 1)` trả giá trị trước cập nhật (2000) và cộng thêm 1 như một thao tác nguyên tử; `getVolatile(counter)` đọc 2001. Cả hai API đều giữ quy tắc kiểu field và quyền truy cập thích hợp.

Không dùng `Thread.sleep` để “thử may rủi”; barrier giúp chứng minh rõ lỗi. Chương trình dùng field public để tách bạch lỗi về concurrency khỏi lỗi Java access control.

## 6. Ba lựa chọn sửa lỗi

### 6.1. `AtomicIntegerFieldUpdater`

Khi muốn giữ một trường instance `volatile int` trong class hiện hữu, sử dụng:

~~~java
AtomicIntegerFieldUpdater<Counter> updater =
        AtomicIntegerFieldUpdater.newUpdater(Counter.class, "value");

int incremented = updater.incrementAndGet(counter);
int previous = updater.getAndIncrement(counter);
boolean swapped = updater.compareAndSet(counter, previous + 1, 50);
~~~

Đoạn code minh họa dùng lớp `Counter` của ví dụ đầy đủ và cần ngữ cảnh Java phù hợp. `compareAndSet` chỉ trả `true` nếu giá trị hiện tại đúng bằng `expected`; ví dụ không khẳng định CAS phải thành công dưới cạnh tranh.

Điều kiện: trường phải là **instance** `volatile int` (không phải static), với quyền truy cập được phép. Có `AtomicLongFieldUpdater` và `AtomicReferenceFieldUpdater` cho các kiểu tương ứng. Factory có thể báo lỗi nếu field không đúng kiểu/không volatile/không truy cập được.

Một updater chỉ giúp các đường cập nhật sử dụng đúng thao tác nguyên tử. Nếu phần còn lại của ứng dụng vẫn đọc rồi tự ghi lại bằng `setInt` mà không phối hợp, dữ liệu vẫn có thể mất cập nhật.

### 6.2. `VarHandle`: tránh nhầm access mode và thao tác nguyên tử

Có thể lấy VarHandle cho trường, nếu `Lookup` có quyền:

~~~java
VarHandle vh = MethodHandles.lookup().findVarHandle(
        Counter.class, "value", int.class);

// Hai thao tác RIÊNG LẺ: không phải increment nguyên tử.
int before = (int) vh.getVolatile(counter);
vh.setVolatile(counter, before + 1);

// Một thao tác RMW nguyên tử:
int previous = (int) vh.getAndAdd(counter, 1);
boolean success = vh.compareAndSet(counter, previous + 1, 10);
~~~

Đây là đoạn minh họa, không phải chương trình chạy độc lập. `compareAndSet` chỉ thành công nếu giá trị hiện tại đúng với `expected`.

`VarHandle` còn có các access mode như `get`/`set` (plain), `getOpaque`/`setOpaque`, `getAcquire`/`setRelease`, `getVolatile`/`setVolatile`, bên cạnh những chế độ atomic RMW. Các mode có memory ordering khác nhau: **đừng cho rằng mọi cách truy cập qua VarHandle tự động có volatile semantics**. Nếu cần đọc/ghi trường volatile và sự phối hợp giữa luồng, chọn access mode có hợp đồng memory ordering phù hợp.

`VarHandle.getAndAdd` hoặc `compareAndSet` là công cụ phù hợp cho một biến; không có nghĩa cả một nghiệp vụ với nhiều field được bảo vệ.

### 6.3. `AtomicInteger` hoặc khóa

Nếu có thể đổi mô hình đối tượng, một trường kiểu `AtomicInteger` diễn đạt mục đích rõ hơn:

~~~java
private final java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger();

void increase() {
    count.incrementAndGet();
}
~~~

Đây là đoạn minh họa bên trong class. Với nhiều biến cần cập nhật nhất quán, một khối `synchronized` hoặc `Lock` có thể thuận tiện hơn CAS trên từng biến đơn lẻ.

## 7. Reflection: quyền truy cập và thread safety là hai trục khác nhau

Một số trường hợp thường gây nhầm:

| Tình huống | Điều thực sự xảy ra |
| --- | --- |
| `Modifier.isVolatile(field.getModifiers()) == true` | Trường được khai báo volatile; không chứng minh được thao tác đọc–tính–ghi là nguyên tử. |
| `field.trySetAccessible() == true` | Được phép bỏ qua kiểm tra truy cập Java trên `Field` đó; không tạo khóa. |
| `field.getInt(target)` rồi `field.setInt(target, x)` | Hai thao tác riêng; có thể bị luồng khác xen giữa. |
| `getVolatile` rồi `setVolatile` trên VarHandle | Từng thao tác có ngữ nghĩa volatile nhưng cặp thao tác vẫn không RMW nguyên tử. |
| `getAndAdd` hoặc `compareAndSet` | Cập nhật nguyên tử đối với biến đích theo hợp đồng API. |
| `volatile List<?> items` | Công bố/đọc tham chiếu với volatile semantics; không bảo đảm các lần sửa collection đều thread-safe. |
| `volatile int x; volatile int y;` | Không tự bảo đảm bất biến chung giữa `x` và `y`. |

Đừng lẫn lỗi truy cập Reflection (`IllegalAccessException`, `IllegalArgumentException` khi receiver không hợp lệ) với race condition. Sửa quyền truy cập bằng `setAccessible` không chữa được *lost update*.

**Giới hạn kiểu:** một field không thể vừa `final` vừa `volatile`; Java cấm kết hợp hai modifier ấy. `AtomicIntegerFieldUpdater` yêu cầu field instance và không áp dụng trực tiếp cho `static volatile int`. Với trường static, có thể dùng `static final AtomicInteger`, khóa, hoặc một `VarHandle` static phù hợp.

## 8. Checklist chọn giải pháp

1. Chỉ cần một luồng thông báo cờ trạng thái cho các luồng khác? `volatile` có thể đủ khi thiết kế giao thức visibility/ordering chuẩn.
2. Cần đọc/ghi **một giá trị riêng lẻ** với visibility giữa luồng? Trường volatile và accessor tương thích là lựa chọn đơn giản.
3. Cần `count++`, `count += delta`, “nếu vẫn bằng X thì đổi thành Y”? Chọn `AtomicInteger`, `AtomicIntegerFieldUpdater`, `VarHandle.getAndAdd`/`compareAndSet`, hoặc khóa.
4. Cần cập nhật nhiều field đồng thời theo một bất biến? Xét khóa hoặc đối tượng trạng thái bất biến được thay nguyên tử.
5. Tên field chỉ biết lúc runtime? Kiểm tra `getType()`, `getModifiers()`, instance/static và quyền truy cập, rồi chọn công cụ phù hợp; `Field.get/set` không có CAS.
6. Viết test concurrency? Cố gắng tạo lịch xen kẽ kiểm soát được như `CyclicBarrier`, thay vì dựa vào một lần chạy stress không thấy lỗi.

### Tự kiểm tra

- Hai luồng thực hiện `volatileCount++` khi ban đầu bằng 0. Kết quả chắc chắn 2? **Không**, có thể 1 vì mất cập nhật.
- `Field.getInt`/`setInt` trên `volatile int` có bỏ qua visibility của volatile? **Không**, nhưng hai lời gọi vẫn độc lập.
- `VarHandle.getVolatile` rồi `setVolatile` có thay được `getAndAdd`? **Không**, vì không phải atomic RMW.
- `AtomicIntegerFieldUpdater` làm việc với `static volatile int`? **Không**, chỉ với instance field thỏa điều kiện.
- `volatile List` có biến `ArrayList.add` thành thread-safe? **Không**, cần an toàn luồng của collection hoặc đồng bộ riêng.

**Kết luận:** `volatile` bảo đảm ngữ nghĩa cho **từng lần đọc/ghi field** và quan hệ visibility/ordering giữa luồng. Reflection vẫn tôn trọng thuộc tính ấy. Muốn cập nhật mà không mất giá trị, phải dùng **atomic read–modify–write** hoặc **đồng bộ hóa** thích hợp.

### Tài liệu chuẩn

- [Java Language Specification 17 — §17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4)
- [JDK 17 — `java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [JDK 17 — `AtomicIntegerFieldUpdater`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerFieldUpdater.html)
- [JDK 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [JDK 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
