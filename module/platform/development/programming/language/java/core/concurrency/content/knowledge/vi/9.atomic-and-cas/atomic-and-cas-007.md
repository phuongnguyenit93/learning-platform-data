# AtomicIntegerFieldUpdater và điều kiện áp dụng trong Java

## 1. Vấn đề: cần phép cập nhật atomic cho một trường của object

Trong Java concurrency, phép tăng `counter++` trên một trường `int` thông thường không nguyên tử: hai thread có thể cùng đọc giá trị cũ rồi ghi đè kết quả của nhau. Một cách giải quyết quen thuộc là giữ một `AtomicInteger` trong mỗi object:

~~~java
// Minh họa trong một class, không phải chương trình độc lập.
private final AtomicInteger counter = new AtomicInteger();

void increment() {
    counter.incrementAndGet();
}
~~~

Cách này đơn giản và thường là lựa chọn đầu tiên. Nhưng nếu chương trình có **rất nhiều đối tượng**, mỗi object cần một bộ đếm nhỏ, việc đặt một object `AtomicInteger` riêng trong từng instance có thể phát sinh thêm allocation, tham chiếu và chi phí bộ nhớ.

`java.util.concurrent.atomic.AtomicIntegerFieldUpdater<T>` cho phép thao tác atomic lên **một trường `volatile int` nằm trực tiếp trong một object có kiểu T**:

~~~java
// Minh họa trong chính class khai báo trường, không phải chương trình độc lập.
private volatile int count;

private static final AtomicIntegerFieldUpdater<MyCounter> COUNT =
    AtomicIntegerFieldUpdater.newUpdater(MyCounter.class, "count");
~~~

Sau đó có thể gọi `COUNT.incrementAndGet(this)`, `COUNT.compareAndSet(this, expected, update)` hoặc `COUNT.get(this)`. **Một updater có thể được chia sẻ** để cập nhật trường tương ứng của nhiều instance, không cần mỗi instance chứa một object `AtomicInteger`.

**Điều cần nhớ ngay từ đầu:** Field updater là công cụ cấp thấp cho một trường cụ thể, **không thay thế** việc thiết kế ownership, bảo vệ bất biến nhiều biến và bảo đảm mọi đường cập nhật tuân thủ cùng một giao thức.

Bài tập trung vào API JDK và Java Memory Model của **Java nói chung**, không đi vào cấu hình của framework.

### Mục tiêu học tập

Sau bài, bạn cần hiểu:

1. Tại sao field updater khác với `AtomicInteger` và khi nào có lợi.
2. Các điều kiện bắt buộc: trường **instance**, kiểu chính xác **primitive `int`**, có modifier **`volatile`**, truy cập hợp lệ tại điểm tạo updater.
3. Cách tạo `AtomicIntegerFieldUpdater.newUpdater(...)`, cập nhật bằng CAS và lấy kết quả trả về đúng ý nghĩa.
4. Tại sao trộn updater với phép ghi trực tiếp hoặc `count++` có thể làm hỏng protocol atomic.
5. Phạm vi bảo đảm visibility/ordering của updater, các giới hạn với nhiều trường, contention và retry.
6. Cách chọn giữa updater, `AtomicInteger`, `AtomicLongFieldUpdater`, `AtomicReferenceFieldUpdater` và `VarHandle` trên Java 17+.

## 2. Khái niệm và chữ ký API

Một updater là một đối tượng mô tả **cách truy cập nguyên tử** một trường `int` cụ thể của một kiểu đối tượng.

~~~java
// Cú pháp API ở mức minh họa, không phải chương trình độc lập.
AtomicIntegerFieldUpdater<Worker> updater =
    AtomicIntegerFieldUpdater.newUpdater(Worker.class, "progress");

// target phải là một Worker hợp lệ.
updater.get(target);
updater.incrementAndGet(target);
updater.compareAndSet(target, 10, 11);
~~~

Phương thức tạo:

~~~java
// Chữ ký tổng quát, không phải đoạn chương trình độc lập.
public static <U> AtomicIntegerFieldUpdater<U> newUpdater(
    Class<U> tclass,
    String fieldName
);
~~~

Trong đó:

- `tclass` là class khai báo trường mục tiêu; ở ví dụ là `Worker.class`.
- `fieldName` là **tên trường thật** dưới dạng string, chẳng hạn `"progress"`. Nó không phải tên getter và compiler không kiểm tra sự tồn tại của chuỗi này.
- `U` là kiểu của đối tượng mục tiêu; mỗi thao tác updater nhận một **instance** chứa trường.
- Đối tượng updater thường được tạo một lần và lưu vào `private static final` để nhiều instance dùng chung.

Phần lớn các phép toán quen thuộc của `AtomicInteger` cũng có trên updater, nhưng nhận thêm **đối tượng đích**:

| Updater API | Ý nghĩa |
| --- | --- |
| `get(obj)` | Đọc trường có ngữ nghĩa volatile |
| `set(obj, newValue)` | Ghi trường có ngữ nghĩa volatile |
| `lazySet(obj, newValue)` | Ghi với ngữ nghĩa release/lazy set, yếu hơn một volatile set toàn phần |
| `compareAndSet(obj, expected, update)` | CAS: đổi giá trị nếu hiện tại bằng `expected`, trả boolean |
| `getAndSet(obj, update)` | Gán giá trị mới và trả giá trị cũ |
| `getAndIncrement(obj)` | Tăng nguyên tử, trả **giá trị trước khi tăng** |
| `incrementAndGet(obj)` | Tăng nguyên tử, trả **giá trị sau khi tăng** |
| `getAndAdd(obj, delta)` | Cộng nguyên tử, trả giá trị cũ |
| `addAndGet(obj, delta)` | Cộng nguyên tử, trả giá trị mới |
| `updateAndGet(obj, function)` | Cập nhật nguyên tử bằng hàm biến đổi, trả giá trị mới |

Một updater áp dụng được cho **nhiều instance của cùng class**, nhưng lần gọi trên instance A không tự động cập nhật instance B. Field updater quản lý **vị trí trường trong từng đối tượng**, không quản lý một biến toàn cục dùng chung.

## 3. Điều kiện bắt buộc khi khai báo trường

### 3.1. Phải là field instance, không phải static

`AtomicIntegerFieldUpdater` cập nhật một trường cụ thể của một **đối tượng nhận vào**. Field được khai báo `static` không phù hợp vì nó thuộc về class, không thuộc từng instance.

~~~java
// Hợp lệ về hình dạng trường, khi updater tạo trong phạm vi truy cập phù hợp:
private volatile int attempts;

// Không hợp lệ làm target cho AtomicIntegerFieldUpdater:
private static volatile int globalAttempts;
~~~

Với bộ đếm toàn cục, có thể dùng một `static final AtomicInteger`, hoặc chọn một cơ chế field/handle khác nếu có lý do rõ ràng.

### 3.2. Kiểu phải chính xác là primitive int

Field target phải có kiểu nguyên thủy `int`. Những kiểu sau **không** dùng với `AtomicIntegerFieldUpdater`:

- `Integer`: object wrapper, không phải primitive `int`.
- `long`: dùng `AtomicLongFieldUpdater` nếu có cùng nhu cầu.
- `boolean`: không phải target của integer field updater; có thể dùng `AtomicBoolean` hoặc biểu diễn trạng thái bằng `int` khi thật sự cần.
- `Object` hoặc một reference bất kỳ: cân nhắc `AtomicReferenceFieldUpdater<T,V>`.

Một `Integer` được boxing/unboxing tự động trong biểu thức Java không làm một trường `Integer` trở thành trường `int` về mặt reflection và API.

### 3.3. Bắt buộc có volatile

Field phải được khai báo `volatile`:

~~~java
// Điều kiện hợp lệ.
private volatile int state;

// Không hợp lệ để tạo updater.
private int stateWithoutVolatile;
~~~

`volatile` thiết lập ngữ nghĩa visibility/ordering liên luồng theo Java Memory Model, còn updater bổ sung các phép **read–modify–write atomic** như CAS và `incrementAndGet`.

Không nên bỏ `volatile` với lý do “đã gọi updater rồi”: constructor/factory updater kiểm tra loại trường và modifier, một field không volatile sẽ bị từ chối.

### 3.4. Quyền truy cập phải hợp lệ tại nơi gọi newUpdater

Mỗi updater được tạo bằng reflection và thực hiện các kiểm tra truy cập theo ngữ cảnh của caller. Một cách đóng gói đơn giản, chắc chắn là **đặt factory updater bên trong chính class khai báo field**:

~~~java
// Đoạn minh họa hợp lệ trong class Worker, không phải chương trình độc lập.
private volatile int progress;

private static final AtomicIntegerFieldUpdater<Worker> PROGRESS =
    AtomicIntegerFieldUpdater.newUpdater(Worker.class, "progress");
~~~

`private volatile` vẫn **hoàn toàn có thể dùng được** nếu updater được tạo từ ngữ cảnh có quyền truy cập private đó. Vì vậy quy tắc “field phải public” là **sai**.

Ngược lại, một class bên ngoài tự tạo updater cho field private của class khác có thể bị từ chối truy cập. Với package-private/protected field, package, quan hệ kế thừa và receiver thực tế cũng có thể ảnh hưởng đến quyền. Trong ứng dụng có Java module, các ranh giới truy cập/module càng cần được xem xét.

Không tìm cách chữa một lỗi access bằng cách tùy tiện mở mọi field public. Ưu tiên factory nằm trong class sở hữu trường và cung cấp các method nghiệp vụ phù hợp.

### 3.5. Không được gán lại ý nghĩa của field

Vì field là `volatile int` bình thường, Java vẫn cho phép code trong class đọc hoặc ghi trực tiếp. Nhưng nếu đã chọn updater để bảo vệ quy tắc cập nhật, **mọi bên ghi cùng field phải tuân thủ giao thức đã định**. Một setter trực tiếp bất ngờ có thể ghi đè giá trị tính từ CAS hoặc phá bất biến.

Field cũng không thể đồng thời là `final volatile` theo Java language rules. Nó cần được cập nhật trong vòng đời object nên không phải final field.

## 4. Ví dụ 1 — nhiều thread tăng trường bằng updater (Java 17+)

Tạo tệp `FieldUpdaterCounterDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class FieldUpdaterCounterDemo {
    static final class Counter {
        private volatile int value;

        private static final AtomicIntegerFieldUpdater<Counter> VALUE =
            AtomicIntegerFieldUpdater.newUpdater(
                Counter.class, "value"
            );

        void increment() {
            VALUE.incrementAndGet(this);
        }

        int get() {
            return VALUE.get(this);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 5000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(work, "counter-1");
        Thread second = new Thread(work, "counter-2");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("value = " + counter.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FieldUpdaterCounterDemo.java
java FieldUpdaterCounterDemo
~~~

Đầu ra chính xác khi cả hai worker hoàn tất:

~~~text
value = 10000
~~~

Giải thích:

1. `Counter` có trường `private volatile int value`, đúng yêu cầu type/modifier/instance.
2. `VALUE` là `static final` nên cả hai thread cùng dùng **một updater**, nhưng tác động tới trường của cùng đối tượng `counter`.
3. `incrementAndGet(this)` thực hiện tăng nguyên tử, tránh lost update của `value++` thông thường.
4. `join()` chờ hai worker xong trước khi `main` đọc và in; kết quả 2 × 5.000 = 10.000.
5. Việc dùng updater không làm `Counter` tự động bảo vệ **mọi trạng thái khác**; chỉ trường `value` được cập nhật theo giao thức đó.

Nếu class còn các field phụ thuộc `value`, một phép CAS đơn lẻ không tự biến cập nhật nhiều field thành transaction.

## 5. CAS cho trạng thái một chiều: ví dụ 2 (Java 17+)

Một ứng dụng thường có trạng thái như `NEW → RUNNING → DONE`. Nếu hai thread cùng yêu cầu bắt đầu một job, **chỉ một bên** được đổi từ NEW sang RUNNING. `compareAndSet` phù hợp để thực hiện phép chuyển trạng thái này một cách nguyên tử.

Tạo tệp `UpdaterStateMachineDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class UpdaterStateMachineDemo {
    static final class Job {
        private static final int NEW = 0;
        private static final int RUNNING = 1;
        private static final int DONE = 2;

        private volatile int state = NEW;

        private static final AtomicIntegerFieldUpdater<Job> STATE =
            AtomicIntegerFieldUpdater.newUpdater(
                Job.class, "state"
            );

        boolean tryStart() {
            return STATE.compareAndSet(this, NEW, RUNNING);
        }

        boolean finish() {
            return STATE.compareAndSet(this, RUNNING, DONE);
        }

        String stateName() {
            return switch (STATE.get(this)) {
                case NEW -> "NEW";
                case RUNNING -> "RUNNING";
                case DONE -> "DONE";
                default -> "INVALID";
            };
        }
    }

    public static void main(String[] args) {
        Job job = new Job();

        System.out.println("start first = " + job.tryStart());
        System.out.println("start second = " + job.tryStart());
        System.out.println("finish = " + job.finish());
        System.out.println("state = " + job.stateName());
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac UpdaterStateMachineDemo.java
java UpdaterStateMachineDemo
~~~

Đầu ra chính xác:

~~~text
start first = true
start second = false
finish = true
state = DONE
~~~

- CAS thứ nhất thấy `state == NEW` và chuyển sang RUNNING.
- CAS thứ hai đòi `state == NEW` nhưng state đã RUNNING, nên trả `false`.
- `finish` chỉ chuyển RUNNING sang DONE.
- Không dùng `if (state == NEW) state = RUNNING` cho tác vụ này: check-then-act có thể bị thread khác chen vào giữa hai bước.

Nếu hai thread thực sự gọi `tryStart()` cùng lúc, chỉ **một trong hai** có thể thành công, nhưng thứ tự thread nào thắng không cố định. Không dùng output “thread A thắng” như kết quả bắt buộc.

Với state machine nhiều chuyển tiếp, bạn vẫn phải định nghĩa đầy đủ các trạng thái, điều kiện transition và cách xử lý failure. CAS trên một `int` chỉ bảo vệ chính transition đã viết; nó không tự hoàn thành job, rollback side effect hoặc quản lý timeout.

## 6. Trộn updater với ghi trực tiếp: một lỗi quan trọng

### 6.1. Vì sao “field volatile” vẫn có thể lost update?

Một field như `private volatile int value` cho phép phép đọc/ghi riêng có ngữ nghĩa volatile, nhưng **`value++` vẫn gồm nhiều bước**. Nếu một code path gọi `VALUE.incrementAndGet(this)`, trong khi code path khác gọi `value++` hoặc `value = cached + 1`, các thao tác có thể xen nhau gây mất cập nhật.

Đừng trộn:

~~~java
// Minh họa trong class có updater VALUE; KHÔNG an toàn nếu chạy đồng thời.
void incrementWrong() {
    value++;
}

void incrementRight() {
    VALUE.incrementAndGet(this);
}
~~~

Ngay cả khi việc ghi trực tiếp cũng là volatile write và có visibility, phép cập nhật gộp vẫn không có atomicity. Ngoài ra, setter trực tiếp có thể bỏ qua các điều kiện CAS như “chỉ chuyển NEW sang RUNNING một lần”.

Javadoc lưu ý bảo đảm atomicity của field updater phụ thuộc việc các bên thao tác **phù hợp với giao thức atomic**; một updater không thể ngăn các phương thức khác truy cập field theo cách thiếu an toàn. Vì thế nên để field `private` và tạo các method có tên thể hiện rõ transition.

### 6.2. Ví dụ 3 — lost update có kiểm soát (Java 17+)

Thay vì hy vọng scheduler ngẫu nhiên tạo race, ta dùng latch để cả hai thread đọc giá trị cũ rồi mới ghi. Trong cùng lúc, một trường khác được cập nhật bằng updater để đối chiếu.

Tạo tệp `FieldUpdaterRaceDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class FieldUpdaterRaceDemo {
    static final class Counts {
        private volatile int unsafe;
        private volatile int safe;

        private static final AtomicIntegerFieldUpdater<Counts> SAFE =
            AtomicIntegerFieldUpdater.newUpdater(
                Counts.class, "safe"
            );

        void incrementSafe() {
            SAFE.incrementAndGet(this);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counts counts = new Counts();
        CountDownLatch bothRead = new CountDownLatch(2);

        Runnable work = () -> {
            int before = counts.unsafe;
            bothRead.countDown();

            try {
                bothRead.await();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                return;
            }

            counts.unsafe = before + 1;
            counts.incrementSafe();
        };

        Thread a = new Thread(work, "worker-a");
        Thread b = new Thread(work, "worker-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("unsafe = " + counts.unsafe);
        System.out.println("safe = " + Counts.SAFE.get(counts));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FieldUpdaterRaceDemo.java
java FieldUpdaterRaceDemo
~~~

Đầu ra chính xác khi worker không bị interrupt:

~~~text
unsafe = 1
safe = 2
~~~

Cả hai thread lấy cùng `before == 0` rồi được giải phóng qua `bothRead`. Vì vậy hai thao tác `counts.unsafe = before + 1` đều ghi 1, dù trường này có `volatile`. Với trường `safe`, hai lần `SAFE.incrementAndGet(counts)` dùng read–modify–write atomic, nên ra 2.

Thí nghiệm có chủ đích tổ chức thứ tự đọc trước khi ghi, không phải một stress test ngẫu nhiên. Latch dùng để phối hợp ví dụ; nó không biến phép cập nhật `unsafe` thành atomic.

## 7. Cách viết CAS loop đúng và xử lý tranh chấp

Không phải mọi logic cập nhật đều có sẵn một method đơn giản. Ví dụ tăng bộ đếm nhưng **không được vượt quá giới hạn**:

~~~java
// Minh họa trong class có private volatile int value và updater VALUE.
int incrementUnlessAtMax() {
    for (;;) {
        int oldValue = VALUE.get(this);

        if (oldValue == Integer.MAX_VALUE) {
            return oldValue;
        }

        if (VALUE.compareAndSet(this, oldValue, oldValue + 1)) {
            return oldValue + 1;
        }

        // Có cạnh tranh: đọc lại và thử CAS trên trạng thái mới.
    }
}
~~~

Giải thích:

- `get` lấy giá trị cũ với ngữ nghĩa volatile.
- Nếu đã đạt giới hạn, không thay đổi.
- Nếu chưa đạt, CAS chỉ thay đổi khi trường vẫn bằng giá trị đã đọc. Nếu thread khác cập nhật trước, CAS thất bại và vòng lặp thử lại.
- Việc kiểm tra `Integer.MAX_VALUE` ngăn overflow đối với phép tăng này.

**Các điểm cần lưu ý trong CAS loop:**

1. **Side effect:** không gửi email, gọi API, ghi file hoặc trừ tiền bên trong đoạn có thể được lặp lại nhiều lần. Một attempt có thể thất bại sau khi side effect đã thực hiện.
2. **Progress:** CAS không bảo đảm mỗi thread được cấp cơ hội công bằng. Một thread có thể thất bại liên tục dưới contention dù tổng hệ thống vẫn tiến triển.
3. **CPU:** spin quá nhiều gây tốn CPU; đo contention thực tế, cân nhắc backoff, khóa, queue hoặc phân mảnh trạng thái.
4. **Overflow:** toán học `int` của Java có wraparound khi vượt phạm vi; giao thức nghiệp vụ cần quy tắc rõ ràng.
5. **Invariant:** nếu thay đổi cần ảnh hưởng hai biến, CAS trên một trường đơn không giữ được tính nguyên tử của cả hai.
6. **ABA:** trạng thái A → B → A có thể khiến CAS từ A tới C thành công dù trạng thái đã thay đổi giữa lúc đọc và update; nếu lịch sử/phiên bản quan trọng, cần version hoặc biểu diễn state phù hợp.

Các phương thức `updateAndGet` và `getAndUpdate` cũng có thể gọi hàm biến đổi nhiều lần do CAS retry. Hàm nên ngắn, không có side effect và an toàn khi thực thi lặp lại.

## 8. Ví dụ 4 — một updater, nhiều object độc lập (Java 17+)

Điểm có giá trị của field updater là **không tạo một wrapper atomic cho từng instance**. Một updater static được chia sẻ nhưng vẫn thao tác trên các object khác nhau.

Tạo tệp `ManyCountersDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class ManyCountersDemo {
    static final class Bucket {
        private volatile int hits;

        private static final AtomicIntegerFieldUpdater<Bucket> HITS =
            AtomicIntegerFieldUpdater.newUpdater(
                Bucket.class, "hits"
            );

        void addHit() {
            HITS.incrementAndGet(this);
        }

        int hits() {
            return HITS.get(this);
        }
    }

    public static void main(String[] args) {
        Bucket first = new Bucket();
        Bucket second = new Bucket();

        first.addHit();
        first.addHit();
        second.addHit();

        System.out.println("first = " + first.hits());
        System.out.println("second = " + second.hits());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ManyCountersDemo.java
java ManyCountersDemo
~~~

Đầu ra chính xác:

~~~text
first = 2
second = 1
~~~

`Bucket.HITS` không chứa giá trị của riêng nó. Nó biết *trường nào* sẽ được cập nhật. `first` và `second` vẫn có hai trường `hits` độc lập. Nếu mỗi instance tạo updater riêng sẽ bỏ lỡ lợi ích của việc tái sử dụng factory và phát sinh thao tác truy cập reflective không cần thiết.

Tuy vậy, không suy ra rằng updater luôn nhanh hơn `AtomicInteger`. Thời gian thao tác còn phụ thuộc JVM, field layout, cache contention, số thread, chính sách cấp phát và workload. **Lợi ích khả dĩ nổi bật là giảm object wrapper trên mỗi instance**, không phải bảo đảm throughput cao hơn trong mọi trường hợp.

## 9. Java Memory Model: visibility và ordering của updater

### 9.1. Field cần volatile vì lý do gì?

`volatile` không làm `x++` trở thành atomic. Nhưng nó cung cấp các bảo đảm đọc/ghi giữa các thread khi có giao thức công bố phù hợp:

- Ghi volatile và đọc volatile tương ứng được JMM ràng buộc bằng quan hệ **synchronizes-with/happens-before**.
- Một lần đọc/ghi volatile riêng có tính nguyên tử cho trường `int`; updater bổ sung CAS và cập nhật gộp nguyên tử.
- Những hành động trước volatile write có thể được công bố cho thread đọc volatile sau đó theo quan hệ HB thích hợp.

Cần phân biệt **visibility**, **ordering** và **atomicity**. Updater không làm cả object tự thread-safe. Ví dụ nếu có hai trường `processed` và `failed`, hai updater độc lập không tạo snapshot nguyên tử của cặp giá trị.

### 9.2. Các đường đọc trực tiếp có được dùng không?

Một method `get() { return value; }` trong class chứa `private volatile int value` vẫn có ngữ nghĩa volatile read. Nhưng để tập trung giao thức và dễ review, dùng `VALUE.get(this)` thể hiện rõ thao tác thông qua updater.

**Quan trọng:** đọc trực tiếp một volatile field không gây lỗi tự thân; rủi ro chính là những **đường ghi/cập nhật không tuân thủ cùng invariant**, như `value++` hoặc `value = newValue` phá điều kiện CAS. Đừng tuyệt đối hóa rằng mọi truy cập trực tiếp đều “bị cấm bởi JVM”; chúng hợp lệ về ngôn ngữ nhưng có thể sai thiết kế.

### 9.3. Một updater không tạo giao dịch cho nhiều field

Xét hai trường `remaining` và `reserved`. Một phép `getAndDecrement` trên `remaining` rồi `incrementAndGet` trên `reserved` là **hai thao tác atomic riêng**, reader có thể thấy trạng thái giữa hai lần cập nhật.

Nếu invariant phải được giữ ở một thời điểm quan sát, cân nhắc:

- `synchronized` hoặc `Lock` bảo vệ cả hai trường và mọi đường đọc phù hợp.
- Một object immutable chứa cả hai giá trị, được thay thế bằng một `AtomicReference<Snapshot>`.
- Chuyển ownership sang một thread xử lý tuần tự thông điệp, nếu mô hình hệ thống cho phép.

Field updater đặc biệt thích hợp cho **một trạng thái số độc lập**, **counter**, **flag dạng số**, hoặc **transition trên một trường** mà các đường cập nhật đã được kiểm soát.

## 10. Đối chiếu AtomicInteger, updater, VarHandle và updater khác

| Lựa chọn | Trạng thái lưu ở đâu? | Khi nào phù hợp? | Lưu ý |
| --- | --- | --- | --- |
| `AtomicInteger` | Trong một object atomic riêng | Ít instance, code đơn giản, cần API rõ | Có thêm object wrapper nếu mỗi instance giữ một atomic |
| `AtomicIntegerFieldUpdater<T>` | Trường `volatile int` trong `T`; updater được chia sẻ | Rất nhiều object nhỏ, muốn CAS trên field trực tiếp | Yêu cầu tên trường dạng chuỗi, quyền truy cập, volatile int instance |
| `AtomicLongFieldUpdater<T>` | Trường `volatile long` trong `T` | Counter 64-bit trên nhiều instance | Cũng cần xem access, hiệu năng và contention |
| `AtomicReferenceFieldUpdater<T,V>` | Trường `volatile V` trong `T` | Chuyển reference state atomically | Bảo vệ reference, không làm object được trỏ tới immutable |
| `VarHandle` (Java 9+) | Handle tới field/array element/khác | Muốn điều khiển access mode linh hoạt | API cấp thấp, nhiều memory-ordering mode, dễ dùng sai |
| `synchronized` / `Lock` | Trạng thái có thể gồm nhiều trường | Bảo vệ invariant tổng hợp, update phức tạp | Contention và nguy cơ deadlock nếu khóa lồng nhau |
| `LongAdder` | Nội bộ nhiều cell phục vụ tổng cộng | Thống kê đếm với tranh chấp cao | `sum()` không phải snapshot nguyên tử khi update đồng thời |

### 10.1. Khi nào AtomicInteger vẫn là lựa chọn tốt hơn?

Nếu chỉ có một vài object và số lượng worker không lớn, `AtomicInteger` thường:

- Dễ đọc và dùng hơn, không yêu cầu tên field string.
- Có thiết kế đóng gói và thao tác atomic rõ ràng trên chính instance.
- Ít nguy cơ bị một đường setter trực tiếp ghi sai vào trường primitive.
- Dễ chuyển code hoặc refactor field mà không phải duy trì tên chuỗi ở factory.

Đừng chọn updater chỉ để “micro-optimize” một class hiếm khi được tạo. Đo allocation, heap, throughput, tail latency và GC trước khi quyết định.

### 10.2. VarHandle trên Java 17+

`VarHandle` có thể trỏ tới một field và hỗ trợ `getVolatile`, `setVolatile`, `compareAndSet`, `getAndAdd` cùng các access mode khác nhau.

~~~java
// Minh họa về cách tìm VarHandle, không phải chương trình độc lập.
VarHandle handle = MethodHandles.lookup().findVarHandle(
    Counter.class, "value", int.class
);
int old = (int) handle.getAndAdd(counter, 1);
~~~

Đoạn trên giả định code có quyền truy cập field và import `java.lang.invoke.MethodHandles`, `java.lang.invoke.VarHandle`, đồng thời xử lý checked reflection exceptions. Field `value` phải là một instance field kiểu `int`. Khác với updater, `VarHandle` có nhiều access mode; phải hiểu hợp đồng memory ordering của từng mode để tránh chọn thao tác yếu hơn nhu cầu.

`VarHandle` không mặc nhiên an toàn hơn hoặc nhanh hơn updater; việc thay thế cần benchmark, review memory semantics và kiểm tra đúng JDK mục tiêu.

## 11. Những lỗi cấu hình thường gặp

### 11.1. Nhầm field thông thường với volatile field

~~~java
// Minh họa sai: updater sẽ từ chối trường không volatile.
static final class WrongCounter {
    int count;
}
~~~

Một lời gọi `AtomicIntegerFieldUpdater.newUpdater(WrongCounter.class, "count")` không tạo được updater hợp lệ cho field này. Cách sửa không phải cast hay generic khác, mà là thiết kế lại field phù hợp với điều kiện `volatile int` và giao thức cập nhật.

### 11.2. Nhầm Integer với int

~~~java
// Minh họa sai cho AtomicIntegerFieldUpdater:
private volatile Integer count;
~~~

Dù reference được khai báo volatile, field không có kiểu primitive `int`. Dùng `volatile int`, hoặc cấu trúc atomic phù hợp với object reference nếu bài toán thực sự cần reference.

### 11.3. Nhầm static field với instance field

~~~java
// Minh họa sai cho AtomicIntegerFieldUpdater:
private static volatile int count;
~~~

Field updater tác động lên từng đối tượng. Với một global counter, hãy dùng một shared `AtomicInteger` hay một cơ chế global state thích hợp.

### 11.4. Trường private được tạo updater từ class ngoài

Một class không có quyền vào trường private không thể dựa vào `newUpdater(Target.class, "secretCounter")` để tự ý cập nhật field đó. Factory có thể bị từ chối tại runtime. Giải pháp đúng thường là đặt updater **trong class sở hữu** và cung cấp method nghiệp vụ hoặc dùng API công khai có kiểm soát.

### 11.5. Lỗi tên string khi refactor

Nếu đổi field từ `"attempts"` thành `"retries"` nhưng quên đổi literal tại `newUpdater`, code có thể **biên dịch thành công nhưng lỗi khi khởi tạo updater tại runtime**. IDE và test nên kiểm tra tên field trong initializer. Giữ factory tập trung trong class khai báo để refactor dễ hơn.

### 11.6. Trộn updater với setter thường

Một method `reset() { count = 0; }` chạy đồng thời có thể phá hợp đồng counter, dù `count` vẫn volatile. Nếu reset được phép, cần xác định có thể xảy ra trong lúc increment không và cơ chế atomic của reset tương ứng (ví dụ `getAndSet`), cùng ý nghĩa nghiệp vụ của các cập nhật đang chạy.

### 11.7. Cho rằng CAS luôn bảo đảm mọi thread tiến triển

CAS loop có thể thất bại liên tục dưới contention. Không có lời hứa một thread cụ thể sẽ lấy được quyền cập nhật sau một số attempt hữu hạn. Điều đó khác với việc toàn bộ thuật toán có thể tiến triển theo một thuộc tính lock-free được chứng minh riêng.

### 11.8. Dùng updater như một lock tổng thể

Field updater chỉ cập nhật một field. Nó không khóa mọi hành động của caller và không giúp giao dịch nhiều bước trên file, database hoặc nhiều object trở thành atomic.

## 12. Performance: bộ nhớ, contention và chi phí factory

### 12.1. Khi số lượng object lớn, vì sao đáng cân nhắc?

Giả sử một hệ thống có hàng triệu object `Node`, mỗi node có một bộ đếm `visits`. Nếu mỗi node giữ một `AtomicInteger` riêng, JVM có thể phải cấp phát nhiều object wrapper. Một `volatile int visits` cùng **một static updater** có thể giảm lượng object phụ trợ.

Không đưa ra một con số “tiết kiệm X byte mỗi node” chung cho mọi máy: kích thước object phụ thuộc layout JVM, compressed references, alignment, padding và những field khác. Hãy dùng profiler hoặc phép đo allocation trên cấu hình JVM thực tế.

### 12.2. FieldUpdater không đảm bảo throughput tốt hơn

Một updater phải giải quyết field offset/access và có đường gọi tương ứng. JIT có thể tối ưu rất nhiều nhưng kết quả phụ thuộc workload. Trong tranh chấp mạnh, các thread vẫn cùng cạnh tranh CAS trên **một ô nhớ**, có thể làm tăng chi phí cache coherence và số lần retry.

Khi số update vào **cùng một field** cực lớn, việc chuyển sang updater không loại bỏ contention. Xem xét phân tán counter, batching, sharding hoặc `LongAdder` cho thống kê khi không cần snapshot cập nhật chính xác tức thời.

### 12.3. Không tạo updater trên mỗi lần gọi

~~~java
// Minh họa chống chỉ định về thiết kế, không phải chương trình độc lập.
void incrementInefficient() {
    AtomicIntegerFieldUpdater<Counter> updater =
        AtomicIntegerFieldUpdater.newUpdater(Counter.class, "value");
    updater.incrementAndGet(this);
}
~~~

Factory dùng reflection và kiểm tra truy cập; việc tạo lại thường xuyên là thừa. Cấu hình một `private static final` updater tại class sở hữu field sẽ đơn giản hơn và ít chi phí hơn.

Đối với benchmark, phải so sánh cùng logic và mức contention, có warm-up/JIT, nhiều lượt chạy, đo cả throughput lẫn allocation/GC và p95/p99 latency. Một microbenchmark tự viết bằng vài lần `System.nanoTime()` có thể gây hiểu nhầm.

## 13. Kiểm thử và quan sát đúng cách

**Kiểm tra tính hợp lệ của factory:**

- Field đúng là `volatile int` dạng instance.
- Chuỗi tên field chính xác và class khai báo đúng.
- Caller có quyền truy cập; updater được tạo trong nơi sở hữu field.
- Không tạo updater lặp đi lặp lại.

**Kiểm tra correctness đồng thời:**

- Nhiều thread increment cùng một instance rồi join; kết quả bằng tổng dự kiến.
- Nhiều instance dùng chung updater; từng instance phải độc lập.
- Nhiều thread CAS cạnh tranh chuyển state từ NEW: chỉ một thread thành công.
- Không có setter/`++` trực tiếp làm sai protocol.
- Nếu cần retry CAS, hàm tính toán có thể lặp lại mà không tạo side effect.
- Các invariant nhiều field được bảo vệ bằng cơ chế riêng.

**Kiểm tra performance:**

- Số instance và allocation chênh lệch giữa `AtomicInteger` và updater.
- Thời gian chờ, số lần CAS thất bại, CPU trong contention cao.
- Ảnh hưởng của false sharing/cache-line contention và layout trong môi trường thực.
- Độ trễ đuôi và tỉ lệ hoàn tất của các thread; đừng xem tốc độ tổng là bảo đảm công bằng cho từng thread.

Stress test có thể phát hiện bug, nhưng một số lượt chạy thành công không chứng minh giao thức memory đúng cho mọi interleaving. Cần lập luận theo JMM và review toàn bộ đường truy cập field.

## 14. Checklist chọn AtomicIntegerFieldUpdater

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Field mục tiêu là **instance primitive int**? | Không dùng `AtomicIntegerFieldUpdater` |
| Field có modifier **volatile**? | Sửa khai báo hoặc chọn cách khác |
| Updater được tạo trong ngữ cảnh có quyền truy cập? | Đưa factory về class sở hữu hoặc đổi API |
| Có nhiều instance và lý do đo được để giảm object wrapper? | `AtomicInteger` thường đơn giản hơn |
| Mọi đường ghi trường dùng chung một giao thức atomic? | Dễ mất update hoặc phá state machine |
| Một field có đủ để bảo vệ invariant không? | Dùng lock hoặc atomic immutable snapshot |
| CAS retry function không có side effect? | Tách side effect khỏi vòng lặp |
| Có chính sách contention, overflow và liveness? | Bổ sung trước khi dùng sản phẩm |
| Đã đo performance trên workload thật? | Đừng khẳng định updater luôn nhanh hơn |

### Câu hỏi tự kiểm tra

**1.** `private volatile int count` có dùng với field updater được không?

**Có**, nếu updater được tạo trong ngữ cảnh có quyền truy cập private đó, ví dụ static factory nằm trong cùng class. Field **không cần public**.

**2.** Vì sao `private volatile Integer count` không hợp lệ?

Vì `AtomicIntegerFieldUpdater` yêu cầu **primitive `int`**, không phải reference `Integer`. Volatile trên reference không thay đổi kiểu field.

**3.** Hai thread đều gọi `incrementAndGet` lên cùng field updater và cùng object thì có mất update như `count++` không?

Không, với các thao tác updater theo giao thức hợp lệ, phép read–modify–write là nguyên tử. Nếu các đường ghi trực tiếp không an toàn cùng tồn tại, bảo đảm tổng thể có thể bị phá.

**4.** Một updater static có thể dùng cho hai object `Counter` không?

Có. Updater mô tả field target, và mỗi lần gọi nhận object cụ thể. Hai instance vẫn giữ giá trị riêng.

**5.** Dùng CAS cập nhật `state` có giúp cập nhật đồng thời thêm `progress` và `timestamp` như một transaction không?

Không. CAS trên một `int` chỉ bảo vệ chính trường đó. Cần một immutable snapshot chung được thay nguyên tử hoặc dùng khóa cho invariant nhiều trường.

**6.** Vì sao không nên đặt một lời gọi API tạo side effect vào lambda của `updateAndGet`?

Vì lambda có thể được gọi lại khi CAS thất bại do contention. Side effect có thể lặp lại dù chỉ một lần cập nhật cuối cùng thành công.

**7.** Nếu class chỉ có vài instance và không có chứng cứ về chi phí allocation, nên ưu tiên công cụ nào?

Thường bắt đầu với `AtomicInteger` để code dễ hiểu, rồi cân nhắc updater khi thật sự có lợi ích bộ nhớ/thiết kế được đo và kiểm chứng.

**Tóm lại:** `AtomicIntegerFieldUpdater` cho phép cập nhật atomic một **trường `volatile int` dạng instance** thông qua updater có thể chia sẻ. Dùng nó khi điều kiện field/access đáp ứng, giao thức cập nhật được kiểm soát và lợi ích về layout/allocation là đáng kể. Nó không thay thế các quyết định về invariant đa trường, safe publication, side effect, contention và tính đúng đắn của toàn hệ thống.