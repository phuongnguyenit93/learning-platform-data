# AtomicIntegerArray, AtomicLongArray và AtomicReferenceArray: cập nhật từng phần tử trong Java

> **Ý chính:** Ba lớp thuộc `java.util.concurrent.atomic` cho phép nhiều thread **đọc, ghi, trao đổi, tăng/cộng hoặc compare-and-set (CAS) nguyên tử tại một chỉ số cụ thể** mà không cần tự khóa cả mảng cho từng thao tác. Nhưng **atomic trên từng phần tử không có nghĩa toàn bộ mảng hay một nhóm phần tử là một transaction**. Đối với `AtomicReferenceArray<E>`, atomicity thuộc về **tham chiếu ở một ô**, không tự bảo vệ trạng thái mutable bên trong object.

Bài thuộc nhóm **Atomic & CAS** của Java concurrency nói chung. Các ví dụ ưu tiên Java 17+ và API Java SE; không bàn đến Spring.

## 1. Vấn đề: các phần tử trong mảng dùng chung có thể bị cập nhật cạnh tranh

Giả sử nhiều thread thống kê số lượt truy cập theo loại sự kiện. Một mảng thường có thể biểu diễn các bộ đếm:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
int[] counts = new int[4];

void record(int bucket) {
    counts[bucket]++; // Không atomic khi nhiều thread cập nhật cùng bucket.
}
~~~

`counts[bucket]++` có ba bước logic: **đọc → cộng → ghi**. Hai thread cùng đọc `10`, cùng tính `11` rồi cùng ghi `11` sẽ làm mất một cập nhật. Đối với các phần tử khác chỉ số, một update ở phần tử A không nhất thiết xung đột dữ liệu với phần tử B, nhưng toàn bộ thuật toán vẫn phải xem xét invariant và cách công bố mảng.

Một số cách giải quyết là đặt `synchronized` quanh mọi cập nhật, dùng một dãy `AtomicInteger`, hoặc dùng các lớp **atomic array** có API thống nhất cho từng slot. Atomic array thường giúp mô tả các bộ đếm/trạng thái độc lập được truy cập theo index mà không phải tạo một đối tượng atomic riêng cho mỗi phần tử.

### Ba lớp và kiểu dữ liệu

| Lớp | Mỗi phần tử lưu | Ví dụ phù hợp |
| --- | --- | --- |
| `AtomicIntegerArray` | `int` | Histogram, số lần retry theo nhóm, trạng thái số nguyên độc lập |
| `AtomicLongArray` | `long` | Bộ đếm 64-bit, sequence theo partition, tích lũy số lượng lớn |
| `AtomicReferenceArray<E>` | Tham chiếu kiểu `E` | Các slot giữ immutable snapshot, object handle, state machine theo ô |

Cả ba đều có **độ dài cố định sau khi tạo**. API không phải `List` có thể thêm/xóa phần tử. Một phần tử là một vị trí do `index` xác định, thường `0 <= index < length()`; dùng index không hợp lệ sẽ gây lỗi giới hạn chỉ số theo API.

### Hình dung phạm vi atomicity

~~~text
AtomicIntegerArray:  [slot 0] [slot 1] [slot 2] [slot 3]
                        ^         ^
                        |         |
                   CAS/getAndAdd  incrementAndGet

Mỗi operation nguyên tử cho CHÍNH SLOT tương ứng.
Không có "transaction tự động" bao trùm slot 0 + slot 1.
~~~

Không nên đọc câu “atomic array” thành “mọi phép đọc toàn mảng là atomic”. Tên lớp biểu đạt một **tập hợp các phần tử có thao tác atomic**, không biến một vòng `for` đọc 100 phần tử thành snapshot đồng thời.

## 2. Các phương thức quan trọng

### Nhóm thao tác chung

| API | Ý nghĩa | Phạm vi atomic |
| --- | --- | --- |
| `length()` | Số phần tử cố định của atomic array | Thuộc tính cấu trúc, không phải cập nhật |
| `get(i)` | Đọc giá trị một phần tử với ngữ nghĩa volatile của API | Một slot |
| `set(i, value)` | Ghi giá trị một phần tử với ngữ nghĩa volatile của API | Một slot |
| `lazySet(i, value)` | Ghi theo release semantics (ở Java hiện đại) | Một slot; không thay cho CAS |
| `getAndSet(i, value)` | Trao đổi, trả giá trị cũ | Một slot |
| `compareAndSet(i, expected, update)` | Ghi có điều kiện khi giá trị hiện tại khớp expected, trả boolean | Một slot |
| `getAndUpdate(i, function)` | Biến đổi nguyên tử, trả giá trị cũ | Một slot, hàm có thể chạy lại |
| `updateAndGet(i, function)` | Biến đổi nguyên tử, trả giá trị mới | Một slot, hàm có thể chạy lại |

`AtomicIntegerArray` và `AtomicLongArray` có thêm các API số học như `getAndIncrement(i)`, `incrementAndGet(i)`, `getAndDecrement(i)`, `decrementAndGet(i)`, `getAndAdd(i, delta)` và `addAndGet(i, delta)`. Chúng còn có `getAndAccumulate`/`accumulateAndGet` để kết hợp giá trị cũ và một giá trị đầu vào.

**Lưu ý phiên bản:** Các API memory-ordering như `getPlain`, `setPlain`, `getAcquire`, `setRelease`, `compareAndExchange` có các phiên bản tương ứng trong Java hiện đại. Bài này tập trung `get/set` và phép cập nhật RMW chuẩn Java 17; khi tối ưu memory ordering ở mức thấp, phải đọc đúng contract riêng từng phương thức trong JDK API.

### Không ghép `get` và `set` rồi tưởng là nguyên tử

~~~java
// Sai về compound update nếu nhiều writer cùng chỉ số.
int previous = counts.get(2);
counts.set(2, previous + 1);
~~~

Dù `get` và `set` **từng cái** có bảo đảm atomic/visibility, giữa hai lời gọi có khoảng trống để thread khác cập nhật slot 2. Muốn tăng nguyên tử, dùng `incrementAndGet(2)` hoặc một CAS loop đúng.

Tương tự, `volatile int[] shared` chỉ làm **tham chiếu mảng** có volatile semantics, không biến `shared[i]++` thành atomic. Các phần tử của `int[]` cũng không tự trở thành volatile chỉ vì biến trỏ đến mảng là volatile.

## 3. Cấu tạo và khởi tạo mảng atomic

Có hai cách thường dùng:

~~~java
// Snippet API, không phải chương trình độc lập.
AtomicIntegerArray ints = new AtomicIntegerArray(4);
AtomicLongArray longs = new AtomicLongArray(new long[]{2L, 4L, 6L});
AtomicReferenceArray<String> names =
        new AtomicReferenceArray<>(new String[]{"a", "b"});
~~~

Dùng constructor độ dài tạo các slot ban đầu bằng **giá trị mặc định**: `0` cho `int`/`long`, `null` cho tham chiếu. Dùng constructor nhận mảng thì giá trị từng slot ban đầu được **sao chép** vào storage của atomic array.

Điểm quan trọng:

- `new AtomicIntegerArray(sourceIntArray)` **không** bọc trực tiếp mảng `sourceIntArray`. Sửa mảng nguồn về sau không làm atomic array đổi theo.
- `new AtomicLongArray(sourceLongArray)` cũng sao chép giá trị primitive.
- `new AtomicReferenceArray<>(sourceRefs)` sao chép **các tham chiếu**, không clone các object được tham chiếu. Nếu object mutable được sửa từ nguồn, cùng object vẫn có thể bị nhìn thấy qua cả hai đường.
- `length()` không đổi; cần một cấu trúc thay kích cỡ động thì phải thiết kế lại (ví dụ publication một reference mới tới toàn cấu trúc hoặc container concurrent khác).

### Ví dụ 1 — kiểm tra việc sao chép mảng nguồn

Tạo tệp `AtomicArrayCopy.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicIntegerArray;
import java.util.concurrent.atomic.AtomicReferenceArray;

public class AtomicArrayCopy {
    public static void main(String[] args) {
        int[] original = {1, 2};
        AtomicIntegerArray values = new AtomicIntegerArray(original);

        original[0] = 100;
        values.incrementAndGet(1);

        System.out.println("original = " + original[0] + "," + original[1]);
        System.out.println("atomic = " + values.get(0) + "," + values.get(1));

        StringBuilder mutable = new StringBuilder("start");
        StringBuilder[] references = {mutable};
        AtomicReferenceArray<StringBuilder> refs =
                new AtomicReferenceArray<>(references);
        references[0] = new StringBuilder("other");
        mutable.append("-changed");

        System.out.println("reference array slot = " + references[0]);
        System.out.println("atomic ref slot = " + refs.get(0));
    }
}
~~~

Chạy:

~~~bash
javac AtomicArrayCopy.java
java AtomicArrayCopy
~~~

Đầu ra:

~~~text
original = 100,2
atomic = 1,3
reference array slot = other
atomic ref slot = start-changed
~~~

Phần primitive chứng minh hai mảng **có storage riêng**. Phần reference cho thấy việc gán lại `references[0]` **không** thay đổi slot trong atomic array, nhưng object `mutable` còn được cả bên lưu tham chiếu tới nó; mutate `StringBuilder` bằng alias vẫn làm nội dung object thay đổi. **AtomicReferenceArray không làm StringBuilder thread-safe.**

Các thao tác lên `StringBuilder` trong ví dụ chạy tuần tự để đầu ra xác định; nếu nhiều thread đồng thời sửa cùng `StringBuilder` mà không có synchronization riêng, vẫn có nguy cơ data race.

## 4. AtomicIntegerArray — tăng từng bucket một cách nguyên tử

Mỗi slot của `AtomicIntegerArray` giống một bộ đếm `int` có các API RMW. Thay vì thao tác `int[]` dùng chung, thread gọi `incrementAndGet(index)` để tăng một slot nguyên tử. Các thread cập nhật slot **khác nhau** không cần một exclusive lock bảo vệ toàn bộ mảng ở tầng ứng dụng.

### Ví dụ 2 — nhiều thread tăng vào cùng một index

Tạo `AtomicIntegerBuckets.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicIntegerArray;

public class AtomicIntegerBuckets {
    public static void main(String[] args) throws InterruptedException {
        AtomicIntegerArray buckets = new AtomicIntegerArray(2);
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final int bucket = i % 2;
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    buckets.incrementAndGet(bucket);
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("bucket 0 = " + buckets.get(0));
        System.out.println("bucket 1 = " + buckets.get(1));
        System.out.println("total = "
                + (buckets.get(0) + buckets.get(1)));
    }
}
~~~

Chạy:

~~~bash
javac AtomicIntegerBuckets.java
java AtomicIntegerBuckets
~~~

Đầu ra xác định nếu không có lỗi bên ngoài:

~~~text
bucket 0 = 20000
bucket 1 = 20000
total = 40000
~~~

Hai worker cùng cập nhật bucket 0; hai worker còn lại cùng cập nhật bucket 1. `incrementAndGet(bucket)` tránh mất cập nhật trên từng bucket. Main `join()` tất cả worker **trước khi** tổng kết nên mọi lần tăng đã hoàn tất.

Nếu main vừa đọc slot 0 vừa đọc slot 1 **trong khi worker còn cập nhật**, tổng từ hai lần `get` không phải một snapshot atomic cùng thời điểm. Ở ví dụ, `join` khiến dữ liệu ổn định nên tổng sau đó chính xác.

### Khác biệt các phép tăng

~~~java
AtomicIntegerArray counters = new AtomicIntegerArray(new int[]{7});

int old = counters.getAndIncrement(0); // old = 7; slot = 8
int now = counters.incrementAndGet(0); // now = 9; slot = 9
int beforeAdd = counters.getAndAdd(0, 5); // beforeAdd = 9; slot = 14
~~~

Đây là snippet minh họa. `getAndX` trả **giá trị trước cập nhật**, `XAndGet` trả **giá trị sau cập nhật**. Khi code logic dựa vào số vé/sequence, nhầm hai kiểu return value có thể gây off-by-one.

**Overflow:** phép cộng `int`/`long` của API arithmetic tuân theo ngữ nghĩa số nguyên Java (có thể wrap khi tràn), không tự ném exception chỉ vì quá giới hạn. Nếu cần giới hạn/cấm overflow, có thể dùng CAS loop với `Math.addExact` trong hàm tính thuần hoặc lock và xử lý ngoại lệ theo yêu cầu nghiệp vụ.

## 5. AtomicLongArray — bộ đếm 64-bit theo slot

`AtomicLongArray` có API số học tương tự nhưng mỗi ô là `long`. Nó phù hợp khi phạm vi số lớn hơn `int`, ví dụ thống kê bytes theo partition hoặc tổng đơn vị tiền nhỏ nhất (với policy overflow phù hợp).

### Ví dụ 3 — tổng bytes từ các worker

Tạo `AtomicLongPartitions.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicLongArray;

public class AtomicLongPartitions {
    public static void main(String[] args) throws InterruptedException {
        AtomicLongArray bytes = new AtomicLongArray(2);

        Thread a = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                bytes.getAndAdd(0, 100L);
            }
        });
        Thread b = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                bytes.addAndGet(0, 200L);
            }
        });
        Thread c = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                bytes.incrementAndGet(1);
            }
        });

        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        System.out.println("partition 0 = " + bytes.get(0));
        System.out.println("partition 1 = " + bytes.get(1));
    }
}
~~~

Chạy:

~~~bash
javac AtomicLongPartitions.java
java AtomicLongPartitions
~~~

Đầu ra:

~~~text
partition 0 = 3000000
partition 1 = 10000
~~~

Hai worker cạnh tranh cùng slot 0 nhưng cập nhật atomic bằng `getAndAdd` và `addAndGet`; worker thứ ba cập nhật slot 1. Cả hai API “getAndAdd” và “addAndGet” đều **cập nhật nguyên tử**, chỉ khác giá trị trả về.

Từng phần tử là `long`; không nên xem cả `AtomicLongArray` là một bộ đếm 128-bit hoặc một kết quả “tổng nhiều slot” atomic. Nếu chỉ có **một** số duy nhất, `AtomicLong` có thể đơn giản hơn. Nếu chỉ đếm thống kê dưới contention cao và không cần snapshot chính xác giữa lúc update, `LongAdder` cũng là ứng viên, nhưng `sum()` của nó không phải snapshot atomic khi đang có writer.

## 6. CAS trên một index: tránh cập nhật dựa trên giá trị đã cũ

`compareAndSet(index, expected, update)` kiểm tra và cập nhật **trong một operation**. Với primitive array, so sánh theo **giá trị primitive**; với reference array, CAS so sánh theo **identity của tham chiếu**, không gọi `equals`.

Mô hình:

~~~text
old = array.get(i)            // Đọc snapshot của slot i
new = f(old)                  // Tính candidate
if array.compareAndSet(i, old, new):
    success                   // Chỉ ghi nếu slot i vẫn bằng old
else:
    retry from current value  // Không ghi đè dựa trên snapshot cũ
~~~

Một CAS loop phù hợp khi phép biến đổi không có API chuyên dụng hoặc cần ràng buộc điều kiện. Với phép tăng thuần, `incrementAndGet` thường ngắn và ít lỗi hơn tự viết vòng CAS.

### Ví dụ 4 — CAS loop cho giá trị không vượt trần

Tạo `BoundedAtomicSlot.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicIntegerArray;

public class BoundedAtomicSlot {
    private static boolean reserve(
            AtomicIntegerArray used, int index, int capacity) {
        while (true) {
            int current = used.get(index);

            if (current >= capacity) {
                return false;
            }
            if (used.compareAndSet(index, current, current + 1)) {
                return true;
            }
            // Có contention; đọc lại slot để quyết định từ dữ liệu mới.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicIntegerArray used = new AtomicIntegerArray(1);
        Thread[] workers = new Thread[4];
        AtomicIntegerArray accepted = new AtomicIntegerArray(1);

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 100; j++) {
                    if (reserve(used, 0, 250)) {
                        accepted.incrementAndGet(0);
                    }
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("used = " + used.get(0));
        System.out.println("accepted = " + accepted.get(0));
    }
}
~~~

Chạy:

~~~bash
javac BoundedAtomicSlot.java
java BoundedAtomicSlot
~~~

Đầu ra:

~~~text
used = 250
accepted = 250
~~~

Bốn thread cố đặt tổng cộng 400 chỗ vào một slot có capacity 250. Chỉ thread CAS thành công mới tăng `used`, và lần kiểm tra `current >= capacity` ngăn vượt trần. Mỗi phép reserve thành công tăng đúng 1; không có lost update.

**Chú ý:** Việc cập nhật `accepted` ở ví dụ chỉ để kiểm nghiệm, **không** là một transaction nguyên tử cùng với `used` nếu có reader khác quan sát khi worker vẫn chạy. Sau `join`, hai giá trị đều bằng số lần thành công. Khi cần invariant giữa hai biến luôn đúng ở thời điểm bất kỳ, dùng một state nguyên tử chung hoặc khóa đúng phạm vi.

## 7. AtomicReferenceArray<E> — thay nguyên tử **tham chiếu** của từng ô

`AtomicReferenceArray<E>` phù hợp nếu mỗi slot giữ một object/handle hoặc snapshot. Các thao tác như `get(i)`, `set(i, newRef)`, `getAndSet(i, newRef)`, `compareAndSet(i, expectedRef, newRef)` cập nhật **tham chiếu ở ô i**, không sâu bên trong object.

Giả sử mỗi slot là một immutable state:

~~~java
record Slot(String owner, int version) {}
AtomicReferenceArray<Slot> slots = new AtomicReferenceArray<>(2);
slots.set(0, new Slot("worker-a", 1));
~~~

Snippet trên chưa độc lập vì cần import và một phương thức/class chứa nó. Nếu nhiều thread thay slot 0 qua CAS, mỗi cập nhật reference là nguyên tử và reader có thể nhận một phiên bản snapshot, không nhận “nửa tham chiếu”.

### CAS reference sử dụng `==`, không sử dụng `equals()`

Hai object có nội dung bằng nhau nhưng **khác identity** sẽ không khớp trong `compareAndSet` nếu expected là object khác.

Tạo `ReferenceCasIdentity.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicReferenceArray;

public class ReferenceCasIdentity {
    public static void main(String[] args) {
        String initial = new String("same");
        AtomicReferenceArray<String> slots =
                new AtomicReferenceArray<>(new String[]{initial});
        String equalButDistinct = new String("same");

        System.out.println("equals = " + initial.equals(equalButDistinct));
        System.out.println("same identity = " + (initial == equalButDistinct));

        boolean failed = slots.compareAndSet(0, equalButDistinct, "new");
        boolean succeeded = slots.compareAndSet(0, initial, "new");

        System.out.println("CAS different ref = " + failed);
        System.out.println("CAS original ref = " + succeeded);
        System.out.println("current = " + slots.get(0));
    }
}
~~~

Chạy:

~~~bash
javac ReferenceCasIdentity.java
java ReferenceCasIdentity
~~~

Đầu ra:

~~~text
equals = true
same identity = false
CAS different ref = false
CAS original ref = true
current = new
~~~

`new String("same")` được dùng riêng để minh họa hai object có `equals` true nhưng `==` false; không phải khuyến nghị tạo String bằng constructor trong nghiệp vụ. Khi muốn CAS trên trạng thái immutable, thường lấy **chính reference hiện tại** bằng `get(i)` rồi tính new state từ reference đó; không dựng một object “equal” và mong CAS thành công.

## 8. AtomicReferenceArray + immutable snapshot + updateAndGet

Với mỗi slot giữ một immutable object, `updateAndGet(i, f)` có thể tạo ra một state mới **từ state hiện tại của đúng ô i**. Phương thức tự retry khi bị tranh chấp, nên có thể tránh việc tự viết CAS loop. Nhưng **hàm f có thể được gọi nhiều lần**.

### Ví dụ 6 — phiên bản hóa state độc lập theo index

Tạo `ReferenceArrayUpdate.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicReferenceArray;

public class ReferenceArrayUpdate {
    record CounterState(long count, int version) {}

    public static void main(String[] args) throws InterruptedException {
        AtomicReferenceArray<CounterState> slots =
                new AtomicReferenceArray<>(
                        new CounterState[]{
                                new CounterState(0, 0),
                                new CounterState(0, 0)
                        });

        Runnable updateFirst = () -> {
            for (int i = 0; i < 1_000; i++) {
                slots.updateAndGet(0, old ->
                        new CounterState(old.count() + 1, old.version() + 1));
            }
        };

        Thread a = new Thread(updateFirst);
        Thread b = new Thread(updateFirst);
        Thread c = new Thread(() -> {
            for (int i = 0; i < 500; i++) {
                slots.updateAndGet(1, old ->
                        new CounterState(old.count() + 2, old.version() + 1));
            }
        });

        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        CounterState first = slots.get(0);
        CounterState second = slots.get(1);
        System.out.println("first = " + first.count() + "/" + first.version());
        System.out.println("second = " + second.count() + "/" + second.version());
    }
}
~~~

Chạy:

~~~bash
javac ReferenceArrayUpdate.java
java ReferenceArrayUpdate
~~~

Đầu ra:

~~~text
first = 2000/2000
second = 1000/500
~~~

Trong mỗi slot, cặp `count` và `version` nằm **trong cùng một record bất biến**, và reference được thay bằng một operation atomic. Vì vậy reader `get(slot)` lấy **một snapshot nhất quán của cặp field** thuộc cùng một phiên bản. Hai slot vẫn độc lập: đọc slot 0 rồi slot 1 không tạo một snapshot cùng thời điểm của cả hai.

**Hàm cập nhật phải không có side effect:** hai thread có thể cùng lấy snapshot A; khi CAS của một thread thành công, thread kia cần tính lại từ snapshot mới. Vì vậy lambda có thể được áp dụng nhiều lần. Không gọi API gửi email, trừ tiền ngoài hệ thống, tăng một counter khác hoặc log mà bạn kỳ vọng “đúng một lần” bên trong lambda.

Trong ví dụ, tạo `new CounterState(...)` là tác dụng nội bộ của phép tính candidate; nếu CAS thất bại, object candidate không được publish. Công thức phải có tính thuần và không dựa vào dữ liệu mutable không được đồng bộ ở bên ngoài.

## 9. AtomicReferenceArray không bảo vệ mutation của object được tham chiếu

Đây là lỗi phổ biến:

~~~java
// Mã minh họa không an toàn; không phải chương trình độc lập.
AtomicReferenceArray<MutableCounter> slots =
        new AtomicReferenceArray<>(1);
slots.set(0, new MutableCounter());

void increment() {
    slots.get(0).value++; // Cập nhật field bên trong không atomic.
}
~~~

`slots.get(0)` đọc **reference** nguyên tử/volatile; ngay sau đó, `value++` vẫn là RMW trên shared mutable object. Nếu hai thread cùng cập nhật object đó, chúng có thể lost update. Nếu object còn bị mutate sau khi publish, cần synchronization riêng, atomic fields của chính object, ownership isolation hoặc **thay toàn object bằng immutable snapshot** qua CAS như phần trước.

**Không lẫn lộn:**

- Atomicity của **slot reference**: đọc/ghi/tráo reference không bị xé thành “nửa pointer”.
- Atomicity của **field bên trong**: tùy lớp object và protocol riêng.
- Atomicity của **nhiều slot**: không được ba lớp atomic array cung cấp trực tiếp.

Dùng `AtomicReferenceArray<AtomicInteger>` không làm điều trên sai: nếu mỗi slot chứa `AtomicInteger` và caller gọi `incrementAndGet()` trên object thì phép tăng của object được atomic bởi **AtomicInteger**, không phải bởi tính chất “reference array” ở bên ngoài. Cần cân nhắc chi phí và tính nhất quán khi reference slot có thể bị thay ngay trong lúc caller đang tăng object cũ.

## 10. Không có transaction nhiều phần tử

Giả sử cần chuyển 10 đơn vị từ tài khoản 0 sang tài khoản 1, invariant là **tổng phải luôn bằng 200**. Một mảng atomic cho hai slot có thể cập nhật mỗi slot riêng lẻ, nhưng không bảo vệ cả hai như **một** chuyển khoản:

~~~java
AtomicIntegerArray balances =
        new AtomicIntegerArray(new int[]{100, 100});

balances.addAndGet(0, -10);
balances.addAndGet(1, 10);
~~~

Giữa hai lời gọi, thread khác có thể đọc `90` ở slot 0 và `100` ở slot 1, thấy tổng `190`. Từng lần update atomic nhưng invariant tổng không được giữ tại mọi điểm quan sát.

### Ví dụ 7 — chứng minh khoảng trống giữa hai slot một cách xác định

Tạo `CrossSlotNotAtomic.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class CrossSlotNotAtomic {
    public static void main(String[] args) throws InterruptedException {
        AtomicIntegerArray balances =
                new AtomicIntegerArray(new int[]{100, 100});
        CountDownLatch firstUpdated = new CountDownLatch(1);
        CountDownLatch resume = new CountDownLatch(1);

        Thread transfer = new Thread(() -> {
            balances.addAndGet(0, -10);
            firstUpdated.countDown();
            try {
                resume.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            balances.addAndGet(1, 10);
        });

        transfer.start();
        firstUpdated.await();

        System.out.println("during = "
                + (balances.get(0) + balances.get(1)));

        resume.countDown();
        transfer.join();

        System.out.println("after = "
                + (balances.get(0) + balances.get(1)));
    }
}
~~~

Chạy:

~~~bash
javac CrossSlotNotAtomic.java
java CrossSlotNotAtomic
~~~

Stdout khi không bị ngắt bên ngoài:

~~~text
during = 190
after = 200
~~~

`CountDownLatch` giữ writer lại **giữa hai cập nhật**, nên main thực sự quan sát một trạng thái trung gian; đây không phải kết quả do may rủi scheduler. Thậm chí nếu reader đọc hai slot trong một vòng `for` rất nhanh, cũng không có snapshot nguyên tử giữa các slot.

### Các giải pháp nếu invariant trải trên nhiều phần tử

- **Dùng một lock bao cả writer và reader:** mọi thao tác chuyển khoản, đọc tổng/snapshot và kiểm tra invariant đều dùng **cùng monitor hoặc Lock**. Reader muốn snapshot nhất quán phải tham gia protocol ấy; không đủ nếu chỉ writer khóa.
- **Immutable whole-state + AtomicReference<State>:** nếu state nhỏ và dễ sao chép, giữ cả hai balance trong một record hoặc object bất biến và thay thế **một reference** bằng CAS. Cập nhật toàn state có một linearization point theo reference.
- **Transactional/concurrent data structure chuyên dụng:** khi nghiệp vụ có nhiều giao dịch, lựa chọn cấu trúc/bộ đồng bộ phải phù hợp invariant. Không cố “khóa từng slot độc lập” rồi tuyên bố bảo toàn cả nhóm.
- **Phân biệt metric snapshot và transaction:** với thống kê gần đúng, hai `get` liên tiếp có thể chấp nhận; với tiền, quota tổng, inventory nhiều kho, thường không.

Một ví dụ state nguyên khối đơn giản:

~~~java
// Snippet minh họa; không phải chương trình độc lập.
record Pair(int left, int right) {}
AtomicReference<Pair> state =
        new AtomicReference<>(new Pair(100, 100));

Pair after = state.updateAndGet(old ->
        new Pair(old.left() - 10, old.right() + 10));
~~~

Một phép `updateAndGet` thay toàn reference nên reader `state.get()` lấy một `Pair` nhất quán. Cần xử lý điều kiện số dư, overflow, retry và chính sách nghiệp vụ trong phép tính thuần; không gọi side effect ngoài transaction trong lambda.

## 11. Vấn đề ABA khi CAS tham chiếu

CAS kiểm tra *giá trị hiện tại có bằng expected hay không*, không kiểm tra toàn bộ **lịch sử** của slot. Ví dụ một reference trong slot có thể đổi A → B → A; một thread đang giữ expected A thấy CAS thành công vì slot lại trỏ về đúng A, dù có thay đổi trung gian. Đây là vấn đề **ABA** đối với các thuật toán cần phát hiện mọi thay đổi.

Với object immutable và mỗi version tạo object mới, quay lại **đúng cùng reference A** có thể ít xuất hiện, nhưng không thể lấy xác suất đó làm bảo đảm thuật toán. Khi cần phát hiện version đã đổi, có thể gắn **version/token** trong immutable state và CAS trên **object state chứa cả dữ liệu + version**; hoặc dùng các lớp như `AtomicStampedReference` theo tình huống (lớp này không phải atomic array).

Lưu ý rằng CAS trên primitive `int` cũng có thể gặp A → B → A về **giá trị**. Vấn đề chỉ nguy hiểm khi logic cần biết có thay đổi trung gian; không phải mọi counter CAS đều có lỗi ABA.

## 12. Memory visibility, ordering và hàm update

Atomic arrays cung cấp các bảo đảm bộ nhớ rõ ràng cho từng operation:

- `get(i)` đọc với hiệu ứng **volatile read**, `set(i,v)` ghi với hiệu ứng **volatile write** theo tài liệu Java hiện đại.
- `compareAndSet` và các operation RMW chuẩn có hiệu ứng đồng bộ do API chỉ định; không phải chỉ là một phép so sánh Java thông thường.
- `lazySet`/`setRelease` có **release semantics**, không tương đương `set` ở tất cả các trường hợp; dùng khi thiết kế memory-ordering và giao thức đọc phù hợp.
- `getPlain`/`setPlain`/`getOpaque`/`setOpaque`/`getAcquire`/`setRelease` có contract riêng và **không nên thay tùy ý** chỉ để tối ưu.
- Một phép `get(i)` không cung cấp snapshot nguyên tử cho tất cả các `j != i`.
- Thread dùng `join`/`Future.get` để chờ công việc kết thúc trước khi kiểm chứng kết quả cuối, chứ không đọc dữ liệu đang thay đổi rồi gọi đó là kết quả cuối.

Một hiểu lầm khác: “`updateAndGet` sẽ gọi lambda đúng một lần”. Không đúng. Trong cạnh tranh, hàm có thể được gọi lại. Các hàm `UnaryOperator`/`IntUnaryOperator`/`LongUnaryOperator` hoặc binary operator dùng trong accumulate nên **side-effect-free**, không sửa object đầu vào và không dựa trên số lần gọi.

### Vòng lặp CAS không bảo đảm mọi thread tiến triển công bằng

Atomic operations có thể tránh việc chờ một monitor truyền thống đối với từng slot, nhưng điều đó **không tự bảo đảm** tất cả thread sẽ hoàn tất trong thời gian giới hạn. Một thread dưới contention cao có thể retry nhiều lần; scheduler và chi phí cache coherence vẫn ảnh hưởng latency. Lock-free ở mức thuật toán không đồng nghĩa wait-free hoặc “không có chi phí đồng bộ”.

## 13. Kiểm tra index và chia sẻ trách nhiệm

Các mảng atomic thường được tạo một lần rồi truyền đến worker. Để tránh lỗi:

1. Xác định **mapping index** rõ: mỗi index đại diện loại sự kiện, partition, client hay một state machine nào?
2. Kiểm tra index từ input nếu dữ liệu đến từ bên ngoài; `length()` cố định không bảo vệ trước index âm hoặc vượt giới hạn.
3. Nếu nhiều thread cập nhật **cùng slot**, dùng một atomic RMW như `incrementAndGet`/CAS khi cần.
4. Nếu chỉ một thread ghi một slot và nhiều thread đọc, vẫn cần đánh giá publication và memory visibility; atomic arrays cung cấp API phù hợp.
5. Không giả định mỗi index tương ứng một object độc lập trong `AtomicReferenceArray`: hai slot có thể trỏ tới **cùng mutable object**, và mọi mutation của object đó là bài toán khác.
6. Không cho caller giữ đường tham chiếu tới **mảng nguồn** rồi tưởng đang sửa trực tiếp atomic array; constructor đã sao chép storage/các reference.
7. Với index chứa `null` trong reference array, `get(i)` có thể trả `null`; code `updateAndGet` phải xử lý null khi phù hợp, tránh `NullPointerException`.
8. Không viết logic phụ thuộc vào `toString()` của atomic array là snapshot nguyên tử: việc đọc từng phần tử khi có writer có thể thấy nhiều thời điểm.

### Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Sửa đúng |
| --- | --- | --- |
| `int[] counts` với `counts[i]++` concurrent | Lost updates | `AtomicIntegerArray.incrementAndGet(i)` |
| `AtomicIntegerArray.get(i)` + `set(i,new)` | Compound action vẫn race | `getAndAdd`, `updateAndGet` hoặc CAS |
| `volatile int[]` rồi `array[i]++` | Volatile reference không làm element atomic | Dùng atomic array/lock |
| `AtomicReferenceArray` chứa `ArrayList` rồi sửa list | List mutation không thread-safe | Immutable value, copy, lock hoặc concurrent collection đúng |
| CAS expected mới dựng mà chỉ `equals` với current | CAS thất bại do reference identity khác | Dùng reference actual từ `get(i)` |
| Update lambda gọi API ngoài tiến trình | Có thể thực hiện side effect nhiều lần vì retry | Hàm update thuần; tách side effect |
| Hai slot được cập nhật bằng hai atomic calls, giả định transaction | Reader thấy trạng thái trung gian | Lock nhóm hoặc AtomicReference tới whole-state |
| Đọc nhiều slot rồi tổng kết khi writer đang chạy | Không phải snapshot nguyên tử | Join trước hoặc thiết kế snapshot |
| Coi `LongAdder.sum()` là snapshot strict | Số liệu có thể không bao hết concurrent updates | AtomicLong/lock nếu cần snapshot nhất quán |
| Dùng nhiều atomic slots mà không xác định index ownership | Khó kiểm soát invariants | Document index mapping, encapsulate API |
| Dùng atomic array cho toàn bộ business workflow có IO | Một slot atomic không bảo vệ side effects | State machine/lock/transaction phù hợp |
| Benchmark một lần rồi nói luôn nhanh hơn | JIT, contention, cache layout và scheduling gây nhiễu | Benchmark đại diện, kiểm chứng correctness trước |

## 14. Hiệu năng: atomic theo slot không có nghĩa không còn tranh chấp

Vì nhiều thread có thể cùng CAS một slot, hiệu năng có thể bị chi phối bởi contention và cache coherence:

- **Cùng index “nóng”**: nhiều thread chạy CAS trên một slot, CAS retry và chuyển cache line có thể khiến throughput giảm.
- **Nhiều index độc lập**: thường giảm tranh chấp về mặt logic, nhưng bố cục bộ nhớ có thể khiến các slot gần nhau chia sẻ cache line (*false sharing*), tùy implementation/JVM/CPU. Không nên khẳng định atomic array đã loại bỏ false sharing.
- **Memory footprint**: Atomic*Array khác với tạo một `AtomicInteger`/`AtomicLong` riêng cho mỗi slot; chi phí bộ nhớ và cơ chế layout phải được đo nếu quan trọng.
- **Workload read-heavy vs write-heavy**: Nếu hầu hết đọc, immutable snapshot + volatile hoặc data structure chuyên biệt đôi khi hiệu quả hơn; nếu write rất nhiều, `LongAdder`/sharding theo nhu cầu thống kê có thể đáng thử.
- **Số lượng slot**: array kích cỡ cố định phù hợp khi mapping ổn định; map đồng thời phù hợp khi index/key động.

Đừng suy đoán từ câu “lock-free thì luôn nhanh”. Hãy đo throughput, p95/p99 latency, CAS failure/retry nếu instrument được, allocations và trạng thái hệ thống trên dữ liệu đại diện. Có thể dùng JMH cho microbenchmark được warmup và chạy nhiều lần.

### Khi nào dùng lớp nào?

| Bài toán | Hướng triển khai |
| --- | --- |
| N bộ đếm `int` độc lập, index cố định | `AtomicIntegerArray` |
| N bộ đếm `long` độc lập, giá trị lớn | `AtomicLongArray` |
| N state immutable theo slot, cần đổi reference nguyên tử | `AtomicReferenceArray<State>` |
| Một bộ đếm duy nhất | `AtomicInteger` / `AtomicLong` |
| Tổng thống kê tăng dưới contention cao, đọc approximate | `LongAdder`/`LongAdder[]` có chính sách publication đúng |
| Toàn cấu trúc cần snapshot consistent, update nhiều field/slot | Khóa chung hoặc `AtomicReference<ImmutableWholeState>` |
| Key động, cập nhật độc lập theo key | `ConcurrentHashMap`/atomic methods |
| Nhiều thao tác ngoài hệ thống phải “all-or-nothing” | Cần giao thức transaction/state-machine khác; atomic array không đủ |

## 15. Tự kiểm tra bằng câu hỏi

**Câu 1.** Bốn thread cùng thực hiện `counts.incrementAndGet(0)` mỗi thread 1.000 lần, sau khi tất cả `join`, kết quả ở slot 0 là bao nhiêu?  
**Đáp án:** `4000`, nếu không có cập nhật khác/exception bên ngoài. Mỗi increment trên slot 0 là RMW atomic.

**Câu 2.** `AtomicLongArray` có tự bảo đảm tổng của slot 0 và slot 1 được đọc như một snapshot không?  
**Đáp án:** Không. Hai `get` là hai operation riêng; writer có thể chen giữa.

**Câu 3.** `AtomicReferenceArray<Person>` có làm `person.age++` atomic không?  
**Đáp án:** Không. Atomicity của slot reference không bảo vệ field mutable của object.

**Câu 4.** Hai `String` có cùng nội dung nhưng khác reference; CAS expected là string mới với `equals` true có thành công không?  
**Đáp án:** Không nếu current vẫn là reference cũ; CAS reference dựa trên identity `==`.

**Câu 5.** `updateAndGet(i, f)` có gọi `f` đúng một lần?  
**Đáp án:** Không được giả định. `f` có thể chạy nhiều lần vì retry dưới contention; phải tránh side effects.

**Câu 6.** Khi nhận `int[] a` ở constructor `new AtomicIntegerArray(a)`, cập nhật `a[0]` có thay đổi atomic slot 0 không?  
**Đáp án:** Không. Giá trị mảng nguồn được sao chép lúc khởi tạo.

**Câu 7.** Khi tạo `AtomicReferenceArray<Mutable>` từ mảng nguồn, nó có sao chép sâu tất cả object không?  
**Đáp án:** Không. Nó sao chép reference theo slot; cùng object mutable có thể vẫn được nhiều nơi dùng.

**Câu 8.** Muốn không cho hai balance có tổng khác 200 ngay cả trong lúc chuyển tiền, có đủ gọi `addAndGet(0,-10)` rồi `addAndGet(1,10)` không?  
**Đáp án:** Không. Dùng cùng một lock bảo vệ update và snapshot, hoặc giữ toàn state trong một reference bất biến được cập nhật atomic.

**Câu 9.** Vì sao `getAndIncrement` và `incrementAndGet` khác nhau?  
**Đáp án:** Đều cập nhật nguyên tử, nhưng method đầu trả giá trị cũ, method sau trả giá trị mới.

**Câu 10.** Một ô bị cập nhật cực nhiều bằng CAS. “Không dùng synchronized” đã chắc chắn hết contention chưa?  
**Đáp án:** Chưa. CAS có thể retry, tốn cache coherence và thread có thể bị trì hoãn; cần đo trên workload thật.

## Tài liệu chính thức

- [`AtomicIntegerArray` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html): constructors, per-element arithmetic/CAS, memory ordering.
- [`AtomicLongArray` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLongArray.html): long updates theo index.
- [`AtomicReferenceArray` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReferenceArray.html): reference swaps/CAS/update theo index.
- [`AtomicReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): thay toàn state bằng một reference.
- [`AtomicStampedReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html): tham chiếu kèm stamp cho một số thuật toán cần version.
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): lựa chọn thống kê trong contention cao, `sum` không là snapshot atomic.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): visibility, ordering, happens-before.

**Ghi nhớ:** `AtomicIntegerArray`, `AtomicLongArray` và `AtomicReferenceArray` giúp cập nhật **mỗi slot** bằng API atomic. Phạm vi nguyên tử **không mở rộng tự động** sang nhiều slot, toàn object graph hay side effects. Chọn đúng operation (`incrementAndGet`, `getAndAdd`, `compareAndSet`, `updateAndGet`) và xác định rõ invariant bạn thực sự phải bảo vệ.