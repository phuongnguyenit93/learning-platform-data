# Không dùng wrapper làm khóa đồng bộ trong Java

**Nguyên tắc:** Không dùng các đối tượng wrapper như `Integer`, `Long`, `Boolean`, `Double`, `Character` làm đối tượng khóa cho `synchronized`. Khi cần bảo vệ dữ liệu chia sẻ giữa các luồng, hãy dùng một **đối tượng khóa chuyên dụng, ổn định về danh tính**, chẳng hạn `private final Object lock = new Object()`, hoặc dùng công cụ đồng thời phù hợp như `AtomicInteger`, `ReentrantLock`.

Wrapper có mục đích **biểu diễn giá trị primitive dưới dạng đối tượng**, không phải đại diện cho một tài nguyên dùng chung có danh tính ổn định để đồng bộ. Việc boxing, cache đối tượng và tính bất biến của wrapper khiến khóa trên nó dễ tạo lỗi tinh vi.

Ví dụ **không nên dùng trong ứng dụng**:

~~~java
Integer count = 0;

// KHÔNG NÊN: có thể khóa trên đối tượng wrapper được cache.
synchronized (count) {
    count++; // Unboxing -> cộng -> boxing lại; count trỏ sang đối tượng khác.
}
~~~

Đây là **đoạn minh họa mã sai**, không phải chương trình chạy độc lập. Trên JDK hiện đại, trình biên dịch có thể phát cảnh báo khi `synchronized` trực tiếp trên lớp value-based. Việc đoạn mã có thể biên dịch không có nghĩa đồng bộ đúng.

## 1. Monitor của synchronized gắn với đối tượng, không gắn với giá trị số

Trong Java, khối:

~~~java
synchronized (lock) {
    // Vùng tới hạn.
}
~~~

sử dụng **monitor** của đối tượng mà biểu thức `lock` đánh giá ra tại thời điểm đi vào khối. Hai luồng chỉ loại trừ nhau khi chúng cố gắng giữ **cùng một monitor của cùng một đối tượng**.

- Hai tham chiếu trỏ đến **cùng đối tượng**: dùng cùng monitor, có thể chặn nhau.
- Hai đối tượng **khác nhau**, dù nội dung số học bằng nhau: có hai monitor khác nhau, **không** loại trừ nhau.
- Biến tham chiếu `lock` bị gán lại: lần `synchronized(lock)` sau có thể khóa một đối tượng khác. Monitor của lần trước không tự chuyển sang đối tượng mới.

Đồng bộ không dựa vào `equals()`, `hashCode()`, giá trị số hoặc kiểu `int` được unbox. Nó dựa vào **danh tính tham chiếu** của đối tượng mà JVM khóa. Đồng thời, quan hệ *happens-before* giữa lần mở khóa và lần khóa tiếp theo được thiết lập khi làm việc trên **cùng monitor**, chứ không trên hai đối tượng chỉ có cùng giá trị.

Đây chính là lý do wrapper, vốn được tạo để đại diện cho **giá trị**, không phải là lựa chọn khóa an toàn.

## 2. Boxing, unboxing và vòng đời đối tượng wrapper

Các wrapper phổ biến của primitive:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Với boxing, một primitive trở thành một đối tượng wrapper; unboxing lấy giá trị primitive ra.

~~~java
Integer n = 42;       // Autoboxing: int -> Integer
int rawValue = n;     // Unboxing: Integer -> int
n = n + 1;            // Unbox n, cộng int, box 43, rồi gán lại n
~~~

Các wrapper là **immutable**: giá trị số bên trong một đối tượng `Integer` không được sửa. Khi dùng `n++`, Java không tăng “tại chỗ” giá trị của đối tượng Integer; thay vào đó, nó tính ra giá trị primitive mới và cập nhật **tham chiếu** của biến `n` sau boxing.

Điều này đặc biệt nguy hiểm nếu chính biến wrapper đó được dùng làm lock. Mỗi lần cập nhật số có thể đổi đối tượng mà các lần khóa sau sử dụng.

### 2.1. Cached wrapper có thể chia sẻ danh tính

Java thường tái sử dụng wrapper cho một số giá trị nhất định. Ví dụ, `Integer.valueOf(int)` có bảo đảm cache ít nhất các giá trị từ **-128 đến 127**:

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);

System.out.println(a == b);       // true: cùng đối tượng trong miền cache
System.out.println(a.equals(b));  // true: cùng giá trị số
~~~

Vì vậy:

~~~java
// KHÔNG NÊN: hai đoạn chương trình không liên quan có thể dùng cùng monitor!
synchronized (Integer.valueOf(42)) {
    // ...
}
~~~

Hai thành phần không liên quan cùng khóa `Integer.valueOf(42)` có thể vô tình **chặn nhau**. Nếu chúng giữ thêm khóa khác theo những thứ tự khác nhau, việc chia sẻ lock không chủ ý còn góp phần tạo tình huống deadlock. Cũng có nguy cơ một thành phần bên ngoài can thiệp vào lịch thực thi của thành phần kia, vì đối tượng cache không thuộc quyền sở hữu riêng của bạn.

**Không được đảo ngược kết luận:** wrapper nằm *ngoài* miền cache không có nghĩa JVM chắc chắn trả đối tượng mới. Ví dụ, đừng dựa vào kết quả của `Integer.valueOf(1000) == Integer.valueOf(1000)` để xác định an toàn khóa; khả năng tái sử dụng đối tượng là chi tiết không phù hợp làm hợp đồng đồng bộ.

Các loại wrapper khác cũng có quy tắc boxing/cache riêng, và một số wrapper có thể được tái sử dụng. Bài học cốt lõi không phụ thuộc cache cụ thể: **wrapper được thiết kế theo ngữ nghĩa giá trị, không theo ngữ nghĩa danh tính khóa ổn định**.

### 2.2. Tạo wrapper mới không phải lời giải đúng

Từng có thể viết `new Integer(42)` để cố tạo đối tượng riêng. Nhưng constructor wrapper kiểu này đã bị **deprecated for removal**, và bản thân wrapper được coi là **value-based**. Việc dùng chúng làm lock vẫn sai về mục đích, khó đọc và không phù hợp hướng phát triển của Java.

Muốn có monitor riêng, hãy tạo hẳn:

~~~java
private final Object lock = new Object();
~~~

Đây là đối tượng có chức năng làm khóa, không mang ý nghĩa số học và không bị vô tình tái tạo bởi phép tăng giá trị.

## 3. Lỗi số một: khóa thay đổi khi tăng biến wrapper

Xem mã **không an toàn** sau (ví dụ minh họa, không áp dụng):

~~~java
class UnsafeCounter {
    private Integer count = 0;

    void increment() {
        synchronized (count) { // Khóa đối tượng count tại thời điểm này
            count++;           // count được unbox, tăng, box, gán lại
        }
    }

    int get() {
        return count;          // Đọc chưa có chính sách đồng bộ nhất quán
    }
}
~~~

Phân tích:

1. Ban đầu `count` tham chiếu tới wrapper cho số 0; luồng A vào `synchronized(count)` và giữ monitor của **đối tượng 0**.
2. Phép `count++` tạo giá trị số 1 và khiến `count` tham chiếu một wrapper đại diện cho 1.
3. Luồng B có thể vào `synchronized(count)` lúc này và giữ monitor của **đối tượng 1**, trong khi A vẫn chưa thoát khỏi vùng tới hạn được bảo vệ bởi monitor số 0.
4. Hai luồng không nhất thiết loại trừ nhau vì đang khóa **hai đối tượng khác nhau**. Phép tăng dự định an toàn có thể bị race, mất lượt tăng; việc đọc `get()` cũng không được bảo vệ.
5. Việc cache các wrapper không sửa lỗi này: cache có thể khiến hai đối tượng với **cùng** giá trị chia sẻ monitor, nhưng khi giá trị thay đổi, đối tượng khóa thường cũng thay đổi.

Lưu ý: mã có thể đồng thời kích hoạt cảnh báo của compiler về đồng bộ trên đối tượng value-based. **Race không phải lúc nào cũng xuất hiện trong một lần chạy**; lỗi là không có bảo đảm tương tranh đúng theo Java Memory Model.

### 3.1. final đặt lên wrapper chứa khóa cũng không giải quyết tận gốc

~~~java
// Không nên dùng làm lock, kể cả khi tham chiếu final:
private final Integer lock = Integer.valueOf(42);
~~~

`final` giúp không gán lại tham chiếu `lock` trong instance, nhưng **không khiến đối tượng Integer đó trở thành tài nguyên độc quyền**. Nó có thể là đối tượng cache dùng chung với mã khác. Và quy tắc không khóa trên value-based wrapper vẫn áp dụng.

## 4. Wrapper là value-based class: cảnh báo từ Java hiện đại

Các primitive wrapper của JDK được mô tả là **value-based classes**. Các lớp này đại diện cho giá trị; lập trình viên không được dựa vào danh tính đối tượng của chúng để phối hợp hệ thống. Tài liệu nền tảng Java cảnh báo rõ việc dùng đối tượng value-based để đồng bộ.

Từ JDK 16, qua JEP 390, công cụ biên dịch có hỗ trợ **cảnh báo cho phép đồng bộ trên đối tượng value-based**. Khi viết:

~~~java
Integer guard = Integer.valueOf(42);
// synchronized (guard) { /* Không nên */ }
~~~

Nếu bỏ comment ở dòng `synchronized`, `javac` trên JDK hiện đại có thể cảnh báo kiểu “attempt to synchronize on an instance of a value-based class”; có thể quan sát bằng tùy chọn kiểm tra liên quan `-Xlint:synchronization`. Nội dung cảnh báo cụ thể thay đổi theo phiên bản/cấu hình biên dịch.

Cảnh báo không đơn thuần là gợi ý phong cách: nó phản ánh vấn đề tương thích với cách Java phát triển các lớp định hướng giá trị. Một số chế độ JVM chẩn đoán nâng cao có thể cảnh báo hoặc xử lý nghiêm ngặt hơn khi bắt đồng bộ trên value-based instance. **Không lấy việc hiện tại code vẫn chạy làm bằng chứng có thể dùng wrapper làm khóa lâu dài**.

Nên phân biệt các khái niệm:

- `wrapper.equals(other)`: so sánh nội dung theo hợp đồng của lớp cụ thể.
- `wrapper == otherWrapper` khi cả hai là tham chiếu: so sánh **danh tính đối tượng**; cache làm kết quả có thể gây bất ngờ.
- `synchronized(wrapper)`: khóa monitor của **đối tượng wrapper**, không dùng giá trị số học.
- `synchronized(lockObject)` với lock chuyên dụng: khóa monitor được tạo để phục vụ bảo vệ trạng thái chia sẻ.

Nếu mục tiêu là bảo vệ một counter hoặc trạng thái, định danh của counter được bảo vệ không phải là chính giá trị số của nó.

## 5. Cách đúng: private final Object lock

Mẫu thông thường:

~~~java
class SafeCounter {
    private final Object lock = new Object();
    private int value;

    void increment() {
        synchronized (lock) {
            value++;
        }
    }

    int get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Đây là **đoạn lớp minh họa** có thể đặt trong tệp Java. Vì `lock` được tạo bằng `new Object()` và giữ ở trường `private final`, các phương thức của **cùng một instance** sử dụng monitor ổn định. Không có code khác lấy được tham chiếu `lock` qua API công khai, nên việc chặn nhau diễn ra trong phạm vi dự kiến.

Phải đảm bảo **mọi truy cập liên quan đến cùng invariant dữ liệu đều tuân theo giao thức khóa**. Việc chỉ khóa ở phương thức ghi nhưng đọc ở nơi khác không theo một cơ chế visibility phù hợp có thể làm mất bảo đảm bộ nhớ.

Với trạng thái `static` được chia sẻ giữa nhiều instance, khóa cũng cần thuộc về trạng thái `static` đó:

~~~java
class GlobalCounter {
    private static final Object LOCK = new Object();
    private static int value;

    static void increment() {
        synchronized (LOCK) {
            value++;
        }
    }

    static int get() {
        synchronized (LOCK) {
            return value;
        }
    }
}
~~~

Một lock instance bảo vệ trạng thái instance; lock static bảo vệ trạng thái static. Không nên dùng `synchronized(this)` hoặc `synchronized(SomeClass.class)` một cách tùy tiện nếu đối tượng monitor đó có thể được mã bên ngoài sử dụng và gây tranh chấp không mong muốn. Khóa chuyên dụng với phạm vi `private` thường rõ ràng hơn.

## 6. Cách đúng khác: AtomicInteger, AtomicLong và LongAdder

Nếu chỉ cần một counter độc lập, thay vì `Integer` và `synchronized` có thể dùng `AtomicInteger`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

`AtomicInteger.incrementAndGet()` thực hiện cập nhật nguyên tử và cung cấp các bảo đảm visibility theo hợp đồng của lớp. Nó không yêu cầu người gọi tự chọn monitor. `AtomicLong` phù hợp nếu cần miền `long`, nhưng vẫn có tràn số khi vượt miền.

Với counter thống kê được cập nhật rất thường xuyên và tranh chấp cao, `LongAdder` thường là lựa chọn đáng cân nhắc. Tuy nhiên `LongAdder.sum()` không tạo snapshot nguyên tử trong lúc các luồng khác cập nhật. Vì vậy:

- `AtomicInteger`/`AtomicLong`: thích hợp khi cần thao tác nguyên tử trên **một biến** và giá trị đọc nhất quán với các cập nhật nguyên tử đó.
- `LongAdder`: thường tối ưu cho thống kê/cộng dồn nhiều luồng, không thay thế mọi giao thức đồng bộ cần snapshot tức thời.
- Một `Object lock` chuyên dụng hoặc `ReentrantLock`: phù hợp khi cần bảo vệ **nhiều trường/điều kiện liên quan** trong cùng một giao dịch logic.

Dùng atomic counter cũng không có nghĩa mọi tổ hợp nhiều thao tác riêng rẽ đều tự động nguyên tử. Ví dụ, kiểm tra `get()` rồi quyết định cập nhật bằng một lệnh riêng có thể race; cần xem `compareAndSet` hoặc thiết kế khóa phù hợp.

## 7. Cách đúng khác: ReentrantLock

Khi cần kiểm soát cấp cao hơn như `tryLock()`, khóa có timeout hay khả năng ngắt khi chờ khóa, JDK cung cấp `java.util.concurrent.locks.ReentrantLock`.

~~~java
import java.util.concurrent.locks.ReentrantLock;

class LockBasedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock(); // Quan trọng: luôn giải phóng, kể cả khi có lỗi.
        }
    }

    int get() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Đây là lớp minh họa độc lập về API; muốn chạy, đặt trong một tệp Java và gọi các phương thức từ chương trình có `main`. Với `ReentrantLock`, tuyệt đối không quên `unlock()` trong `finally`. `synchronized` tự giải phóng monitor khi thoát block, kể cả khi có exception.

Không cần chuyển toàn bộ `synchronized` sang `ReentrantLock` nếu không có nhu cầu. Một `private final Object` đơn giản thường là giải pháp đủ tốt và dễ kiểm toán.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo tệp `WrapperLockDemo.java`. Ví dụ **không đồng bộ trực tiếp trên wrapper**; chỉ chứng minh boxing/caching rồi cho bốn luồng cập nhật bằng hai cách an toàn.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class WrapperLockDemo {
    static final class SafeCounter {
        private final Object lock = new Object();
        private int value;

        void increment() {
            synchronized (lock) {
                value++;
            }
        }

        int get() {
            synchronized (lock) {
                return value;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Integer a = Integer.valueOf(42);
        Integer b = Integer.valueOf(42);
        System.out.println("cached identity: " + (a == b));
        System.out.println("numeric equality: " + a.equals(b));

        Integer boxed = 42;
        Integer before = boxed;
        boxed++;
        System.out.println("after increment: " + boxed);
        System.out.println("same boxed object: " + (before == boxed));

        SafeCounter counter = new SafeCounter();
        AtomicInteger atomic = new AtomicInteger();

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counter.increment();
                    atomic.incrementAndGet();
                }
            });
        }

        for (Thread worker : workers) {
            worker.start();
        }
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("lock counter: " + counter.get());
        System.out.println("atomic counter: " + atomic.get());
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac WrapperLockDemo.java
java WrapperLockDemo
~~~

Kết quả:

~~~text
cached identity: true
numeric equality: true
after increment: 43
same boxed object: false
lock counter: 4000
atomic counter: 4000
~~~

**Phân tích:**

1. `Integer.valueOf(42)` cho cùng đối tượng wrapper trong miền cache được bảo đảm. Vì vậy biểu thức danh tính `a == b` là `true`; đây chính là lý do đối tượng đó không phải lock riêng.
2. Sau `boxed++`, biến `boxed` đại diện cho 43, còn `before` vẫn trỏ wrapper đại diện cho 42. Hai tham chiếu khác nhau; giá trị wrapper cũ không đổi.
3. `SafeCounter` dùng `private final Object` ổn định. Từng lượt tăng chạy dưới **cùng monitor** cho cùng counter.
4. `AtomicInteger` có `incrementAndGet()` nguyên tử. Bốn luồng tăng 1.000 lần mỗi luồng; sau khi `join()` tất cả, cả hai bộ đếm đều cho 4.000.
5. Ví dụ cố ý không mô phỏng chương trình race bằng `synchronized(Integer)` vì kết quả race có thể khác nhau giữa các lần chạy và tạo thói quen sai.

Lệnh `join()` làm luồng chính chờ các worker kết thúc trước khi đọc kết quả, nên đầu ra bộ đếm có thể dự đoán được. Nó không thay thế nhu cầu bảo vệ các lượt tăng trong chính các worker.

## 9. Sai lầm thường gặp và cách nhận biết

| Cách viết | Vấn đề | Cách thay phù hợp |
| --- | --- | --- |
| `synchronized (Integer.valueOf(1))` | Đối tượng cache dùng chung ngoài ý muốn | `private final Object lock = new Object()` |
| `synchronized (count) { count++; }` với `Integer count` | `count` có thể đổi tham chiếu khi tăng | `int` + lock riêng hoặc `AtomicInteger` |
| `private final Integer lock = 42` | `final` không bảo đảm monitor độc quyền | Tạo `new Object()` cho khóa |
| `synchronized (Boolean.TRUE)` | Đối tượng dùng chung, phạm vi khóa vượt module | Private lock riêng |
| `synchronized (Double.valueOf(x))` | Wrapper value-based; danh tính không nên làm khóa | Private lock riêng |
| `volatile Integer count; count++;` | `volatile` không làm `++` nguyên tử | AtomicInteger hoặc synchronized đúng |
| Chỉ khóa khi ghi nhưng đọc trạng thái không phối hợp | Thiếu bảo đảm visibility/happens-before | Đồng bộ cả đọc và ghi theo một giao thức |
| Dùng `ReentrantLock.lock()` nhưng không `unlock()` an toàn | Có thể giữ khóa mãi khi có exception | `try/finally` |
| Thay `Integer` bằng `new Integer(...)` để làm khóa | Constructor deprecated, sai tinh thần value-based | `new Object()`, không tạo wrapper làm monitor |

### 9.1. Vì sao volatile không cứu được việc tăng wrapper?

~~~java
// VẪN SAI nếu nhiều luồng đồng thời:
private volatile Integer value = 0;

void increment() {
    value++; // Đọc -> unbox -> cộng -> box -> ghi, không nguyên tử.
}
~~~

Đây là đoạn minh họa đặt trong lớp, không phải chương trình chạy độc lập. `volatile` cung cấp các bảo đảm visibility và thứ tự đọc/ghi của chính trường volatile, nhưng **không gộp toàn bộ chuỗi đọc–tính–ghi thành một thao tác nguyên tử**.

### 9.2. Vì sao public lock cũng không lý tưởng?

Nếu dùng một đối tượng monitor mà thành phần bên ngoài có thể truy cập, ví dụ `synchronized(this)` của một object công khai, mã ngoài cũng có thể `synchronized(obj)` và làm chương trình tranh chấp khóa ngoài dự kiến. Do đó, ngay cả khi không dùng wrapper, việc giữ lock ở một trường `private final` thường làm mô hình sở hữu khóa rõ ràng hơn.

### 9.3. Có được đồng bộ trên wrapper nếu chỉ chạy một luồng?

Khi chỉ có một luồng, `synchronized` thường không giải quyết nhu cầu chia sẻ đồng thời nào. Nhưng dùng wrapper làm lock vẫn là thiết kế không phù hợp; mã có thể được tái sử dụng trong bối cảnh nhiều luồng hoặc thay đổi phiên bản JDK. Hãy sửa sang lock chuyên dụng thay vì phụ thuộc giả định tình cờ hiện tại.

## 10. Bài tập tự kiểm tra

**Câu 1.** Hai module khác nhau đều dùng `synchronized(Integer.valueOf(42))`. Chúng có thể chặn nhau không dù không chia sẻ biến riêng?  
**Đáp án:** Có. `Integer.valueOf(42)` được cache; cả hai có thể khóa cùng một đối tượng. Đây là khóa dùng chung ngoài ý muốn.

**Câu 2.** Tại sao `private final Integer lock = 42` chưa phải lock tốt?  
**Đáp án:** `final` ổn định **tham chiếu của trường**, nhưng đối tượng wrapper có thể là cache dùng chung với nơi khác. Wrapper value-based không được thiết kế làm monitor. Dùng `private final Object lock = new Object()`.

**Câu 3.** Mã `synchronized(count) { count++; }` có bảo vệ được `count++` khi `count` là `Integer` không?  
**Đáp án:** Không đảm bảo. `count++` unbox, cộng, box và gán tham chiếu mới; những luồng sau có thể khóa monitor khác. Các lượt tăng có thể xảy ra đồng thời và mất cập nhật.

**Câu 4.** Có thể thay `Integer count` bằng `volatile Integer count` rồi tăng bằng `count++` cho an toàn không?  
**Đáp án:** Không. `volatile` đảm bảo một số quan hệ visibility nhưng không làm chuỗi đọc–cộng–ghi thành một phép tăng nguyên tử. Dùng `AtomicInteger.incrementAndGet()` hoặc một lock chuyên dụng.

**Câu 5.** Khi nào chọn `private final Object lock` thay vì `AtomicInteger`?  
**Đáp án:** Khi cần bảo vệ nhiều biến cùng lúc, duy trì một invariant liên quan hoặc chạy nhiều bước trong một vùng tới hạn. `AtomicInteger` phù hợp với thao tác nguyên tử trên một biến số nguyên.

**Câu 6.** Có nên chuyển mọi counter sang `LongAdder`?  
**Đáp án:** Không. `LongAdder` có lợi trong nhiều tình huống thống kê tranh chấp cao, nhưng `sum()` không phải snapshot nguyên tử khi có cập nhật đồng thời. Với kiểm tra–cập nhật nhất quán, cần thiết kế khác.

**Câu 7.** Điều kiện quan trọng nhất để `synchronized` loại trừ lẫn nhau là gì?  
**Đáp án:** Các luồng phải cố khóa **cùng monitor trên cùng đối tượng**, và mọi truy cập cần bảo vệ phải tuân theo cùng giao thức khóa. Không đủ nếu chỉ có hai wrapper chứa cùng giá trị số.

## 11. Ghi nhớ

- `Integer`, `Long`, `Boolean`, `Double` và các primitive wrapper là **value-based**, không phải đối tượng được thiết kế để dùng danh tính làm khóa.
- Cache/autoboxing có thể khiến wrapper bị **chia sẻ vô tình**; unboxing rồi boxing khi cập nhật có thể khiến biến wrapper **đổi tham chiếu khóa**.
- `synchronized` khóa **monitor của đối tượng**, không khóa một giá trị `int` hay một biểu thức số học trừu tượng.
- Chọn `private final Object lock = new Object()` cho vùng tới hạn có trạng thái liên quan; dùng `AtomicInteger`/`AtomicLong` cho phép cập nhật nguyên tử trên một biến, cân nhắc `ReentrantLock` cho yêu cầu khóa nâng cao.
- Tránh dùng `volatile` hay `final Integer` như “mẹo chữa” việc khóa bằng wrapper; chúng không giải quyết hợp đồng danh tính monitor.
- Khi thấy cảnh báo “synchronization on an instance of a value-based class”, hãy **thay mô hình khóa**, không chỉ tắt cảnh báo.