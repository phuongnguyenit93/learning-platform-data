# Không an toàn khi dùng collection thường chung nhiều luồng trong Java

Một `ArrayList`, `HashMap` hay `HashSet` hoạt động đúng khi được sử dụng theo hợp đồng API. Tuy nhiên, khi **nhiều thread cùng truy cập một collection có thể thay đổi**, đặc biệt khi ít nhất một thread sửa nội dung hoặc cấu trúc, các collection thông thường trong `java.util` **không tự cung cấp cơ chế đồng bộ cần thiết**. Hậu quả có thể là mất phần tử, đếm sai, đọc dữ liệu cũ, vi phạm bất biến nội bộ hoặc gặp exception ngoài dự đoán. Không phải lỗi nào cũng biểu hiện khi chạy thử vài lần.

Bài này nằm trong nhóm **Race Conditions**, tập trung vào **Java concurrency nói chung**: xác định ranh giới thread safety, phân tích race condition, chọn phương thức bảo vệ và dùng collection thay thế phù hợp. Không bàn về thành phần concurrency riêng của Spring Framework.

## 1. Tại sao collection thông thường không mặc định thread-safe?

Phần lớn collection thông dụng của Java được thiết kế để cung cấp thao tác hiệu quả khi chương trình **quản lý việc truy cập đúng cách**. Ví dụ:

- `ArrayList<E>`: danh sách dựa trên mảng động, có các trường trạng thái nội bộ như số phần tử và vùng lưu trữ.
- `HashMap<K,V>`: bảng băm có bucket và cấu trúc liên kết phục vụ tra cứu/chèn/xóa.
- `HashSet<E>`: set dựa trên một `HashMap` để lưu các phần tử duy nhất.
- `LinkedList<E>`: danh sách liên kết, cập nhật kích thước và các liên kết nút khi thêm/xóa.
- `TreeMap<K,V>`, `TreeSet<E>`: cấu trúc cây phải duy trì thứ tự và invariant khi cập nhật.
- `ArrayDeque<E>`, `PriorityQueue<E>`: duy trì head/tail hoặc heap khi thêm/lấy phần tử.

Các cấu trúc này **không được thiết kế để tự chịu được mọi kiểu sửa đổi concurrent**. Một thao tác `list.add(x)` nhìn ở mức API là một lời gọi, nhưng triển khai có thể phải đọc kích thước hiện tại, kiểm tra dung lượng, ghi phần tử và cập nhật số phần tử. Khi hai thread xen kẽ các bước, không có bảo đảm mặc định rằng cả hai lời gọi tạo ra hiệu ứng như đã chạy tuần tự theo một thứ tự nào đó.

Điều cần phân biệt:

| Tình huống | Nhận định an toàn |
| --- | --- |
| Một thread sở hữu `ArrayList` và chỉ thread đó sửa/đọc | Thông thường an toàn về chia sẻ giữa thread vì không có cạnh tranh |
| Nhiều thread chỉ đọc collection **không bị sửa nữa** và tham chiếu đã được công bố an toàn | Có thể an toàn nếu nội dung được công bố đầy đủ và không có mutable value bị sửa ngoài ý muốn |
| Một thread đang `add/remove`, thread khác đang `get/iterate` | Không an toàn nếu thiếu cơ chế phối hợp |
| Nhiều thread cùng `add/remove` | Không an toàn nếu thiếu cơ chế phối hợp |
| Collection bọc bằng `Collections.synchronizedList` | Các thao tác đơn lẻ qua wrapper được đồng bộ; iteration và chuỗi thao tác vẫn cần xem xét riêng |
| Dùng `ConcurrentHashMap` hoặc `BlockingQueue` đúng hợp đồng | Có bảo đảm concurrent riêng của từng API; không có nghĩa mọi chuỗi nghiệp vụ đều atomic |

**`final` không đồng nghĩa thread-safe.** Ví dụ `private final List<String> tasks = new ArrayList<>();` chỉ ngăn việc gán lại tham chiếu `tasks`. `tasks.add(...)` vẫn thay đổi chính list được chia sẻ.

## 2. Race condition khi hai thread cùng thay đổi collection

**Race condition** là khi tính đúng đắn của chương trình phụ thuộc vào thứ tự thực thi và thời điểm các thao tác từ nhiều thread xen kẽ nhau, trong khi chương trình chưa áp đặt đủ quy tắc phối hợp.

Hình dung hai thread cùng thêm phần tử vào một list. Đây là sơ đồ logic đơn giản hóa, không phải mô tả từng lệnh bytecode của mọi JDK:

```text
Ban đầu: size = 10

Thread A                          Thread B
đọc size = 10
                                  đọc size = 10
ghi phần tử A tại index 10
                                  ghi phần tử B tại index 10
cập nhật size thành 11
                                  cập nhật size thành 11

Tổng cộng đã gọi add() hai lần
nhưng một phần tử có thể bị ghi đè / số đếm bị sai.
```

Sự cố có thể diễn ra theo lịch khác nhau: thỉnh thoảng kết quả đúng, thỉnh thoảng sai hoặc phát sinh exception. Không nên khẳng định sẽ xảy ra chính xác kết quả nào trên một phiên bản JDK cụ thể; đó là điểm nguy hiểm của chương trình có data race.

Một ví dụ dễ mắc:

```java
List<Integer> results = new ArrayList<>();

// Nhiều task chạy cùng lúc:
results.add(result);
```

Đây là đoạn minh họa, không phải chương trình đầy đủ. Nếu `results` là **cùng một instance** và nhiều worker cùng `add`, mỗi lần gọi không tự an toàn chỉ vì các giá trị `result` là immutable.

**Data race và visibility:** Không chỉ thao tác sửa gặp vấn đề. Nếu thread A sửa list còn thread B đọc kích thước mà không có quan hệ happens-before, B không có bảo đảm thấy cập nhật tại thời điểm mong muốn. Việc đọc một trường sau `Thread.sleep(...)` không tự thiết lập quan hệ đồng bộ với thread ghi.

### Một ví dụ cố ý không an toàn để nhận diện lỗi

Đoạn sau thể hiện **anti-pattern**, không dùng làm lời khẳng định stdout:

```java
import java.util.ArrayList;
import java.util.List;

final class UnsafeListExample {
    private final List<Integer> results = new ArrayList<>();

    void record(int value) {
        results.add(value); // Không an toàn nếu gọi đồng thời từ nhiều thread.
    }

    int count() {
        return results.size(); // Cũng có vấn đề nếu thread khác đang sửa.
    }
}
```

Không nên cố gắng tái hiện lỗi bằng cách thêm nhiều `Thread.sleep` hoặc phụ thuộc một giá trị in ra. Sự không an toàn nằm ở việc **hợp đồng `ArrayList` không bảo đảm các thao tác concurrent này**, dù có lần thử tình cờ trả về đủ phần tử.

## 3. Các kiểu lỗi điển hình theo collection

### `ArrayList` và `LinkedList`: ghi đè, kích thước sai, iteration không ổn định

Khi nhiều thread cùng `add`/`remove`, các cập nhật số phần tử và cấu trúc lưu trữ có thể đua nhau. Đọc theo chỉ số có thể không tương ứng với trạng thái mong đợi. Iteration trong lúc thread khác sửa cấu trúc có thể gặp `ConcurrentModificationException`, bỏ qua/quan sát không ổn định hoặc có hành vi khác không được bảo đảm.

Với `LinkedList`, thay đổi liên kết nút và kích thước cũng phải giữ invariant; chia sẻ không đồng bộ không giải quyết được vấn đề.

### `HashMap` và `HashSet`: mất update, kết quả truy vấn không đáng tin

`HashMap` cần duy trì bucket và các phần tử tương ứng. Trong lúc resize, put hoặc remove, việc một thread khác đọc/sửa cùng map thiếu đồng bộ có thể thấy dữ liệu không như mong đợi. `HashSet` dựa trên map nên cũng không miễn nhiễm.

Tránh lưu truyền các khẳng định tuyệt đối như "`HashMap` luôn rơi vào vòng lặp vô hạn khi resize": cách triển khai khác giữa các phiên bản Java và lỗi cụ thể không phải điều API bảo đảm. Kết luận đủ chắc chắn là **không được dựa vào thao tác concurrent thiếu đồng bộ trên `HashMap`**.

### `TreeMap`, `TreeSet`, `PriorityQueue` và `ArrayDeque`

Mỗi cấu trúc đều giữ một số bất biến nội bộ (cây cân bằng, heap, vị trí đầu/cuối). Khi nhiều thread thay đổi, bảo đảm đó phụ thuộc cách truy cập được phối hợp. Sử dụng chúng mà không bảo vệ không trở nên an toàn chỉ vì API `add` hoặc `put` ngắn gọn.

Nếu cần queue producer–consumer đa luồng, cân nhắc `BlockingQueue` hoặc `ConcurrentLinkedQueue` thay vì `ArrayDeque` dùng chung.

### Collection chứa đối tượng mutable

Ngay cả khi dùng collection có cơ chế đồng bộ, **đối tượng bên trong vẫn là vấn đề riêng**:

```java
ConcurrentHashMap<String, ArrayList<String>> map = new ConcurrentHashMap<>();
// ... các thread cùng lấy một value và gọi value.add(...)
```

`ConcurrentHashMap` bảo vệ cấu trúc map theo hợp đồng của nó; một `ArrayList` lưu trong map không nhờ vậy trở thành thread-safe. Nếu có nhiều writer, phải bảo vệ value, đổi cách lưu hoặc thay cấu trúc sở hữu.

## 4. `ConcurrentModificationException` không phải bộ phát hiện data race

Collection thường có các iterator **fail-fast**: nếu phát hiện sửa đổi cấu trúc ngoài ý iterator trong quá trình duyệt, chúng có thể ném `ConcurrentModificationException`.

Ví dụ **ngay cả một thread** cũng có thể gặp exception:

Lưu thành `FailFastDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class FailFastDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("A", "B"));
        Iterator<String> iterator = names.iterator();

        names.add("C"); // Sửa cấu trúc ngoài iterator.

        try {
            iterator.next();
            System.out.println("Unexpected");
        } catch (java.util.ConcurrentModificationException e) {
            System.out.println("Detected a structural modification");
        }
    }
}
```

```bash
javac FailFastDemo.java
java FailFastDemo
```

Stdout của ví dụ:

```text
Detected a structural modification
```

Tình huống này diễn ra trong **một thread**, cho thấy exception liên quan đến cách sử dụng iterator, không phải luôn chứng minh có truy cập nhiều thread.

Trong môi trường concurrent:

- Fail-fast **best effort**, không bảo đảm ném exception cho mọi sửa đổi từ thread khác.
- **Không ném exception cũng không chứng minh chương trình thread-safe**.
- Catch `ConcurrentModificationException` để bỏ qua và tiếp tục **không sửa** sự thiếu đồng bộ.
- Nếu cần xóa phần tử khi đang duyệt trong một thread, `Iterator.remove()` (nếu iterator hỗ trợ) là cách hợp lệ hơn việc dùng `list.remove(...)` bên ngoài iterator. Nếu có nhiều thread, vẫn cần chính sách đồng bộ hoặc collection thích hợp.

Không sử dụng exception này như cơ chế điều khiển luồng hoặc cách "thử xem collection có an toàn hay không".

## 5. Ba yếu tố cần bảo đảm: atomicity, visibility và invariant

Khi bảo vệ một collection dùng chung, phải xác định **những gì cần nhất quán**, không chỉ "thêm lock cho mọi chỗ".

**Atomicity:** Một thao tác hoặc một chuỗi thao tác nghiệp vụ có thể được quan sát như một hành động không bị xen ngang tại điểm cần thiết hay không? Ví dụ `if (!set.contains(x)) set.add(x)` là check-then-act: nếu hai thread cùng kiểm tra trước khi thêm, điều kiện "chỉ một thread nhận quyền xử lý x" có thể bị phá, kể cả khi từng thao tác `contains` và `add` riêng lẻ đều an toàn.

**Visibility:** Sau khi thread A cập nhật collection, thread B có cách nhìn thấy cập nhật ấy được Java Memory Model bảo đảm không? Quan hệ happens-before có thể đến từ cùng monitor lock, các thao tác concurrent collection theo hợp đồng, `Thread.start/join`, `Future.get` hoặc cơ chế đồng bộ thích hợp.

**Invariant:** Dữ liệu có quan hệ phải được duy trì tại thời điểm bên ngoài được phép quan sát. Ví dụ một nghiệp vụ phải đảm bảo tổng số phần tử trong hai collection bằng N; khóa riêng từng collection có thể chưa đủ để biến việc chuyển phần tử giữa hai collection thành một giao dịch atomic.

Mục tiêu không phải luôn khóa toàn cục mọi thứ, mà là **xác định ranh giới thao tác logic cần atomic và đường công bố dữ liệu đúng**.

## 6. Cách 1: không chia sẻ collection mutable nếu không cần

Đây là cách thường dễ chứng minh đúng nhất: mỗi task tạo collection của riêng mình và trả về một kết quả hoàn chỉnh.

```java
static List<String> transform(List<String> input) {
    List<String> local = new ArrayList<>();

    for (String value : input) {
        local.add(value.toUpperCase());
    }

    return List.copyOf(local);
}
```

Đây là đoạn minh họa phương thức, yêu cầu import `java.util.List` và `java.util.ArrayList` nếu đặt trong class độc lập.

Ở đây worker là chủ sở hữu `local` trong lúc xây dựng. Kết quả được công bố là một list không cho sửa qua API; với các `String` immutable thì dữ liệu bên trong cũng không bị sửa. **Điều kiện:** `input` phải được dùng theo một giao thức phù hợp; nếu thread khác đồng thời sửa `input` trong lúc transform, vấn đề đầu vào vẫn tồn tại. `List.copyOf` cũng không làm an toàn một bản copy đang đua với writer bên ngoài.

Một dạng thiết kế khác là **single-writer ownership**: nhiều producer gửi công việc/giá trị qua queue, chỉ một consumer sở hữu và cập nhật collection tích lũy. Khi đó collection không cần bảo vệ cho nhiều writer vì chỉ một thread được chạm vào nó. Nếu consumer muốn chia sẻ kết quả, tạo snapshot immutable hoặc công bố bằng cơ chế đồng bộ phù hợp.

## 7. Cách 2: bảo vệ collection bằng cùng một khóa

Nếu bắt buộc nhiều thread cùng sử dụng một `ArrayList` hay `HashMap` và muốn giữ invariant qua nhiều thao tác, cách trực tiếp là bảo vệ tất cả các đường truy cập liên quan bằng **cùng monitor** hoặc **cùng lock**.

Ví dụ Java 17+ chạy được, không phụ thuộc thứ tự worker:

Lưu thành `LockedListDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedListDemo {
    private static final class SharedResults {
        private final List<Integer> values = new ArrayList<>();

        synchronized void add(int value) {
            values.add(value);
        }

        synchronized List<Integer> snapshot() {
            return List.copyOf(values);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SharedResults shared = new SharedResults();

        Runnable work = () -> {
            for (int i = 0; i < 1_000; i++) {
                shared.add(i);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        List<Integer> result = new ArrayList<>(shared.snapshot());
        Collections.sort(result);

        System.out.println("Size: " + result.size());
        System.out.println("Zeros: " + Collections.frequency(result, 0));
        System.out.println("Last: " + result.get(result.size() - 1));
    }
}
```

```bash
javac LockedListDemo.java
java LockedListDemo
```

Stdout chính xác:

```text
Size: 2000
Zeros: 2
Last: 999
```

Phân tích:

- Cả hai worker gọi `shared.add` nhưng **cùng phải giữ monitor của instance `SharedResults`**. Trong vùng khóa, `ArrayList` chỉ được một thread sửa tại một thời điểm.
- `snapshot()` dùng cùng monitor để copy dữ liệu; không đọc list đang bị thread khác cập nhật. `List.copyOf` trả về list không cho sửa qua API, phù hợp cho kết quả gồm `Integer` immutable.
- `join()` đảm bảo main đợi hai worker hoàn tất. Sắp xếp bản sao sau đó giúp stdout không phụ thuộc lịch chạy xen kẽ.
- Để thật sự giữ quyền kiểm soát, `values` là `private` và không có getter trả trực tiếp mutable list. Nếu để tham chiếu nội bộ thoát ra rồi client tự gọi `add`, client có thể bỏ qua khóa và phá thiết kế.

### Khóa cho từng thao tác chưa chắc bảo vệ phép toán tổng hợp

Ví dụ sau **vẫn có race logic**, dù cả `size()` và `add()` đã được đồng bộ:

```java
if (shared.size() < limit) {
    shared.add(item);
}
```

Hai thread có thể cùng thấy dung lượng chưa đầy rồi cùng thêm. Nếu yêu cầu là "chỉ thêm khi chưa vượt giới hạn", phải đặt cả kiểm tra và thêm **trong cùng critical section**, chẳng hạn cung cấp phương thức `tryAddWithinLimit(item, limit)` được `synchronized`. Một API thread-safe về thao tác đơn lẻ chưa tự làm một chuỗi check-then-act thành atomic.

## 8. Cách 3: dùng `Collections.synchronizedXxx` đúng cách

Các wrapper như:

- `Collections.synchronizedList(new ArrayList<>())`
- `Collections.synchronizedMap(new HashMap<>())`
- `Collections.synchronizedSet(new HashSet<>())`

đồng bộ các thao tác qua wrapper theo hợp đồng. Thích hợp khi cần tiếp tục dùng API collection truyền thống nhưng muốn một mức bảo vệ đơn giản.

**Bẫy quan trọng: duyệt iterator vẫn phải đồng bộ thủ công** trên chính wrapper trong suốt quá trình duyệt. Nếu không, thread khác có thể sửa collection giữa các bước duyệt.

Lưu thành `SynchronizedIterationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SynchronizedIterationDemo {
    public static void main(String[] args) {
        List<String> items =
                Collections.synchronizedList(new ArrayList<>());

        items.add("Java");
        items.add("Concurrency");

        synchronized (items) {
            for (String item : items) {
                System.out.println(item);
            }
        }
    }
}
```

```bash
javac SynchronizedIterationDemo.java
java SynchronizedIterationDemo
```

Stdout chính xác:

```text
Java
Concurrency
```

Trong bài toán có nhiều thread, tất cả code phải **truy cập qua wrapper**, không giữ và sửa trực tiếp underlying `ArrayList`/`HashMap` sau khi bọc. Khi dùng iterator, spliterator, stream hoặc các chuỗi thao tác cần một góc nhìn nhất quán, phải dựa vào hướng dẫn đồng bộ của wrapper và khóa đúng đối tượng. Không nên giữ khóa khi chạy tác vụ I/O lâu hoặc callback không kiểm soát vì sẽ chặn các thao tác khác.

### Vì sao chỉ bọc `synchronizedList` chưa đủ?

Ví dụ:

```java
List<String> items =
        Collections.synchronizedList(new ArrayList<>());

if (!items.contains("A")) {
    items.add("A");
}
```

Hai lời gọi `contains` và `add` đơn lẻ đều được wrapper bảo vệ, nhưng **giữa hai lần gọi** thread khác có thể thay đổi list. Nếu yêu cầu là "A chỉ xuất hiện một lần", dùng một vùng:

```java
synchronized (items) {
    if (!items.contains("A")) {
        items.add("A");
    }
}
```

hoặc chọn `Set` thích hợp và sử dụng thao tác nguyên tử mà API của cấu trúc concurrent đó cung cấp.

## 9. Cách 4: dùng collection được thiết kế cho concurrency

`java.util.concurrent` cung cấp nhiều cấu trúc với các đặc tính riêng. Chọn theo **bài toán và kiểu thao tác**, không chỉ theo chữ "concurrent".

| Nhu cầu | API thường phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| Map cập nhật và đọc từ nhiều thread | `ConcurrentHashMap<K,V>` | Có API atomic theo key, iterator weakly consistent, không cho khóa/value `null` |
| Set cần thao tác concurrent | `ConcurrentHashMap.newKeySet()` | Dùng cho membership, thêm/xóa an toàn qua API set |
| Queue nhiều producer/consumer, không chờ khi rỗng | `ConcurrentLinkedQueue<E>` | Non-blocking queue, `poll()` có thể trả `null` |
| Queue cần producer/consumer chờ và có thể giới hạn dung lượng | `ArrayBlockingQueue<E>` | `put` chờ khi đầy, `take` chờ khi rỗng |
| Queue chờ với cấu hình dung lượng | `LinkedBlockingQueue<E>` | Nên cân nhắc capacity hữu hạn, tránh tăng hàng đợi không kiểm soát |
| Danh sách chủ yếu đọc, ghi hiếm | `CopyOnWriteArrayList<E>` | Iterator snapshot, mỗi mutation thường phải sao chép mảng; ghi nhiều sẽ đắt |
| Map cần duy trì thứ tự khóa có concurrent access | `ConcurrentSkipListMap<K,V>` | Cấu trúc sorted concurrent, chi phí khác `ConcurrentHashMap` |
| Set cần duy trì thứ tự | `ConcurrentSkipListSet<E>` | Sorted set concurrent, không phải `HashSet` |
| Tích lũy số liệu với contention cao | `LongAdder` hoặc `LongAccumulator` | Không phải collection; hỗ trợ thống kê nhưng `sum()` dưới concurrent updates không là snapshot atomic |

Không có một collection duy nhất thay thế tối ưu mọi trường hợp. Cần cân nhắc thứ tự dữ liệu, chi phí ghi, backpressure, memory footprint và tính atomic của thao tác nghiệp vụ.

### `ConcurrentHashMap`: dùng `merge` cho cập nhật theo key

Một race phổ biến là:

```java
Integer old = map.get(key);
map.put(key, old == null ? 1 : old + 1);
```

Ngay cả khi `map` là `ConcurrentHashMap`, **chuỗi get rồi put không tự atomic**: hai worker có thể cùng lấy số cũ rồi ghi cùng số mới.

Hãy dùng API update atomic theo key, ví dụ `merge`. Lưu thành `ConcurrentMapCounterDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentMapCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                counts.merge("done", 1, Integer::sum);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Done: " + counts.get("done"));
    }
}
```

```bash
javac ConcurrentMapCounterDemo.java
java ConcurrentMapCounterDemo
```

Stdout chính xác:

```text
Done: 20000
```

`merge("done", 1, Integer::sum)` cập nhật giá trị **theo key** bằng một operation của `ConcurrentHashMap`, tránh lost update của cặp `get/put` trong ví dụ. Hai `join()` đảm bảo việc đọc số cuối xảy ra sau khi cả hai worker hoàn tất.

**Lưu ý:** hàm truyền vào `compute/merge` nên ngắn, rõ ràng và không gọi các cập nhật map khác theo kiểu có thể gây tái nhập hoặc phụ thuộc chéo. Hợp đồng mỗi phương thức quyết định loại bảo đảm; đừng suy từ "map thread-safe" rằng toàn bộ giao dịch nhiều key hoặc thao tác trên mutable value cũng atomic.

### Trường hợp set unique

Thay cho chuỗi `if (!set.contains(id)) set.add(id)` để quyết định "chỉ một worker xử lý id", dùng kết quả của chính thao tác `add` trên một set concurrent:

```java
Set<String> seen = ConcurrentHashMap.newKeySet();

if (seen.add(id)) {
    // Chỉ thread có lần add thành công cho id mới xử lý nhánh này.
}
```

Đây là đoạn minh họa: cần import `java.util.Set`, `java.util.concurrent.ConcurrentHashMap` và cung cấp `id`. Điều kiện `add` là một bước atomic theo hợp đồng của set concurrent, nhưng logic "chỉ chạy business action một lần trong toàn hệ thống" còn phụ thuộc việc lỗi, retry và trạng thái bên ngoài được thiết kế ra sao.

## 10. Queue cho nhiều producer: chuyển quyền thay vì sửa chung một list

Khi nhiều thread tạo kết quả và một thread tổng hợp, thay vì cho tất cả thread `list.add(...)` vào cùng một `ArrayList`, có thể dùng **producer–consumer**:

```text
Producer A --+
             +--> BlockingQueue --> Consumer sở hữu ArrayList tổng hợp
Producer B --+                          |
                                        +--> kết quả cuối sau khi hoàn tất
```

Producer chỉ gửi message; consumer duy nhất quản lý list. `BlockingQueue` đảm nhiệm đồng bộ và chuyển giao dữ liệu giữa thread. Dùng queue có capacity hữu hạn giúp **backpressure** khi producer nhanh hơn consumer.

Ví dụ độc lập Java 17+; hai producer gửi các số và một consumer tính tổng. Mỗi producer gửi đúng 1.000 phần tử, caller dùng `Future.get()` đợi cả hai producer hoàn thành rồi đưa sentinel `-1` để consumer dừng.

Lưu thành `ProducerConsumerDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ProducerConsumerDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(32);
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            Future<?> first = pool.submit(() -> {
                for (int i = 0; i < 1_000; i++) {
                    queue.put(1);
                }
                return null;
            });

            Future<?> second = pool.submit(() -> {
                for (int i = 0; i < 1_000; i++) {
                    queue.put(1);
                }
                return null;
            });

            Future<Integer> consumer = pool.submit(() -> {
                int sum = 0;

                while (true) {
                    int item = queue.take();
                    if (item == -1) {
                        return sum;
                    }
                    sum += item;
                }
            });

            first.get();
            second.get();
            queue.put(-1); // Chỉ gửi sau khi cả hai producer xong.

            System.out.println("Total: " + consumer.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac ProducerConsumerDemo.java
java ProducerConsumerDemo
```

Stdout chính xác trên đường chạy thành công:

```text
Total: 2000
```

Hai producer có thể cùng cập nhật **queue được thiết kế thread-safe**, còn biến `sum` chỉ thuộc consumer, nên không cần mutex quanh `sum`. `Future.get()` xác nhận cả hai producer hoàn thành thành công trước khi main đặt sentinel. Queue FIFO bảo đảm sentinel được lấy sau các phần tử đã `put` thành công trước đó; ví dụ có đúng một consumer và dữ liệu chỉ là số `1` nên `-1` không trùng dữ liệu.

Đây là mô hình thành công đơn giản. Trong ứng dụng thực, nếu một producer thất bại trong lúc consumer đang `take()`, code điều phối phải có giao thức xử lý lỗi/hủy và đánh thức consumer phù hợp; `shutdownNow()` chỉ yêu cầu interruption, không phải biện pháp cưỡng bức dừng mọi thao tác. Không nên copy nguyên mẫu sentinel này sang hệ thống nhiều consumer mà không sửa giao thức kết thúc.

### Queue không tự khiến object bên trong immutable

Nếu producer gửi một `ArrayList` rồi **tiếp tục sửa cùng instance** trong khi consumer đọc, data race vẫn tồn tại. Quy tắc an toàn là **chuyển quyền sở hữu** cho consumer và producer ngừng sử dụng object, hoặc gửi một bản sao bất biến như `List.copyOf(...)` (sau khi việc tạo snapshot được bảo vệ phù hợp).

## 11. `CopyOnWriteArrayList`: an toàn khi chủ yếu đọc

`CopyOnWriteArrayList` thích hợp cho cấu hình dạng tập listeners hoặc danh sách nhỏ được đọc/duyệt thường xuyên, cập nhật hiếm. Mỗi thay đổi cấu trúc thường tạo mảng lưu trữ mới, còn iterator giữ **ảnh chụp tại thời điểm tạo iterator**.

Lưu thành `CopyOnWriteDemo.java`:

```java
import java.util.Iterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>();

        listeners.add("A");
        listeners.add("B");

        Iterator<String> snapshot = listeners.iterator();
        listeners.add("C");

        while (snapshot.hasNext()) {
            System.out.println("Snapshot: " + snapshot.next());
        }

        System.out.println("Current size: " + listeners.size());
    }
}
```

```bash
javac CopyOnWriteDemo.java
java CopyOnWriteDemo
```

Stdout:

```text
Snapshot: A
Snapshot: B
Current size: 3
```

Đây là hành vi snapshot được API thiết kế, không phải lỗi mất dữ liệu. Iterator của `CopyOnWriteArrayList` không dùng cơ chế fail-fast theo cách iterator của `ArrayList` làm và không hỗ trợ `remove()` trên iterator. Người dùng cần hiểu **snapshot không thấy các thay đổi xảy ra sau khi tạo iterator**.

Không nên dùng `CopyOnWriteArrayList` cho workload ghi rất nhiều hoặc danh sách lớn bị thay đổi liên tục, vì chi phí sao chép và cấp phát mảng có thể cao. Nó cũng không biến đối tượng mutable được lưu làm phần tử thành immutable.

## 12. Immutable collection, unmodifiable view và safe publication

Ba khái niệm rất dễ bị nhầm:

1. **Mutable collection:** nội dung có thể thay đổi qua API (ví dụ `ArrayList`).
2. **Unmodifiable view:** caller không sửa qua view được, **nhưng underlying collection có thể vẫn đổi**.
3. **Immutable snapshot:** bản sao không cho phép sửa cấu trúc qua API và tách khỏi những thay đổi sau này của collection đầu vào; phần tử mutable vẫn là trách nhiệm riêng.

Xem ví dụ Java 17+:

Lưu thành `SnapshotVsViewDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SnapshotVsViewDemo {
    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>(List.of("A"));

        List<String> view = Collections.unmodifiableList(mutable);
        List<String> snapshot = List.copyOf(mutable);

        mutable.add("B");

        System.out.println("View: " + view);
        System.out.println("Snapshot: " + snapshot);
    }
}
```

```bash
javac SnapshotVsViewDemo.java
java SnapshotVsViewDemo
```

Stdout chính xác:

```text
View: [A, B]
Snapshot: [A]
```

`Collections.unmodifiableList(mutable)` là **view**, nên nó phản ánh thay đổi được thực hiện qua `mutable`. `List.copyOf(mutable)` tạo một list unmodifiable không phản ánh lần `add` sau trong trường hợp đầu vào mutable như ví dụ.

Nhưng chú ý:

- `List.copyOf` **không hợp thức hóa việc copy trong lúc thread khác đang sửa list không an toàn**. Cần ngừng writer, giữ lock khi chụp, hoặc dùng protocol publication phù hợp.
- Collection unmodifiable có thể chứa **phần tử mutable**: nếu là `List<Account>` và các `Account` vẫn bị sửa, không thể gọi toàn bộ object graph là deep-immutable.
- `List.of(...)` và `List.copyOf(...)` từ chối phần tử `null`; `List.copyOf` có thể tái sử dụng một instance unmodifiable phù hợp, nên không được dựa vào identity của snapshot.
- Sau khi xây xong dữ liệu, vẫn cần **safe publication** để thread khác nhìn thấy trạng thái đầy đủ theo Java Memory Model, ví dụ qua lời gọi `Thread.start()` đúng thứ tự, queue đồng bộ, volatile reference hoặc monitor lock.

Thay một tham chiếu trỏ tới **immutable snapshot** đôi khi đơn giản hơn cố đồng bộ từng lần đọc và ghi nhiều field trong một mutable collection.

## 13. Parallel streams: tránh side effect trên collection dùng chung

Một lỗi phổ biến trong Java là viết:

```java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 100_000)
        .parallel()
        .forEach(output::add);
```

Đây là **anti-pattern** khi `output` là `ArrayList` dùng chung. `parallel()` có thể khiến nhiều worker cùng gọi `add`, trong khi `ArrayList` không an toàn với nhiều writer. Thứ tự phần tử không được bảo đảm, và chương trình còn có nguy cơ thiếu phần tử hoặc lỗi.

Một cách đúng là dùng phép **collect** được thư viện hỗ trợ thay vì sửa side effect vào list chung. Lưu thành `ParallelCollectDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelCollectDemo {
    public static void main(String[] args) {
        List<Integer> result = IntStream.range(0, 10_000)
                .parallel()
                .boxed()
                .toList();

        long sum = result.stream()
                .mapToLong(Integer::longValue)
                .sum();

        System.out.println("Size: " + result.size());
        System.out.println("First: " + result.get(0));
        System.out.println("Sum: " + sum);
    }
}
```

```bash
javac ParallelCollectDemo.java
java ParallelCollectDemo
```

Stdout chính xác:

```text
Size: 10000
First: 0
Sum: 49995000
```

`IntStream.range` có encounter order, và `Stream.toList()` giữ encounter order khi có, kể cả pipeline có `parallel()`. Kết quả `toList()` là list unmodifiable. Bản thân pipeline chịu trách nhiệm thu thập đúng, không yêu cầu người viết tự gọi `add` từ nhiều thread vào cùng `ArrayList`.

**Đừng suy diễn rằng tất cả thao tác stream đều tự bảo vệ side effect.** Nếu callback `map/forEach/peek` vẫn sửa một object ngoài pipeline, thread safety của object đó vẫn phải được xử lý. Muốn tổng hợp theo key dưới concurrency, cân nhắc `Collectors.groupingByConcurrent` theo yêu cầu về thứ tự và kiểu kết quả; đọc hợp đồng collector thay vì tự tạo map và cập nhật không đồng bộ.

## 14. Trường hợp read-only: nhiều thread đọc có an toàn không?

Nếu collection được **khởi tạo hoàn chỉnh trước khi công bố**, sau đó không còn thread nào thay đổi cấu trúc hoặc nội dung được đọc, nhiều thread đọc song song thường không cần lock quanh mỗi lần đọc.

Tuy nhiên, phải đồng thời đáp ứng:

- Không có writer concurrent (kể cả writer "ẩn" giữ alias tới cùng instance).
- Tham chiếu được chuyển tới reader bằng cơ chế **safe publication** theo Java Memory Model. Chỉ gán tham chiếu vào một field ordinary trong lúc các thread khác đang chạy, rồi hy vọng các reader tự thấy ngay, không phải giao thức publication đầy đủ.
- Những value hoặc phần tử mutable bên trong không bị thay đổi theo cách xung đột khi reader đang dùng.
- Không giả định một **unmodifiable view** đồng nghĩa underlying collection bất biến.

Vì vậy, "một collection không có ai gọi `add` lúc này" khác với "một snapshot immutable được công bố đúng". Hãy chọn thiết kế dễ giải thích ownership và publication.

## 15. Những thao tác tưởng an toàn nhưng không atomic ở cấp nghiệp vụ

| Mẫu code | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `if (!list.contains(x)) list.add(x)` | Check và add có khoảng xen kẽ | Giữ chung một lock hoặc dùng set concurrent với `add` atomic |
| `map.put(key, map.get(key) + 1)` | Hai worker có thể ghi đè increment | `ConcurrentHashMap.merge/compute` hoặc khóa |
| `if (queue.size() < limit) queue.add(x)` | Kiểm tra dung lượng và thêm không là một giao dịch | Queue bounded với `offer/put` phù hợp |
| `for (x : synchronizedList) ...` không khóa | Iterator có thể race với writer | `synchronized(list)` trong suốt iteration hoặc dùng snapshot |
| `map.get(key).add(value)` khi value là `ArrayList` | Map thread-safe không bảo vệ mutable value | Bảo vệ value, dùng immutable replacement hoặc owner duy nhất |
| `if (map.isEmpty()) launchCleanup()` | Trạng thái có thể đổi ngay sau kiểm tra | Giao thức đồng bộ hóa trạng thái/điểm đóng thích hợp |
| `collection.size()` được đọc trong lúc nhiều writer chạy | Không nhất thiết là snapshot nghiệp vụ | Đợi worker hoàn tất hoặc khóa/thiết kế snapshot phù hợp |

**Thread-safe ở mức method không đồng nghĩa thread-safe ở mức workflow.** Nếu yêu cầu liên quan nhiều bước và nhiều collection, hãy xác định ranh giới atomicity và phương thức phối hợp phù hợp, thay vì chỉ thay `HashMap` bằng `ConcurrentHashMap` rồi cho rằng mọi invariant đã được bảo vệ.

## 16. Lỗi thiết kế thường gặp

### 16.1. Dùng `volatile List<T>` là đủ

`volatile` trên tham chiếu list giúp về visibility/ordering đối với thao tác đọc-ghi chính **tham chiếu** đó. Nó **không biến các thao tác `add/remove` bên trong `ArrayList` thành atomic**. Nếu thiết kế dùng immutable snapshot và thay mới cả tham chiếu qua `volatile`, đó là một phương án khác với việc nhiều worker cùng sửa list hiện tại.

### 16.2. Gọi `Collections.synchronizedList` rồi chuyển tiếp raw list

Nếu nơi khác còn giữ tham chiếu tới underlying `ArrayList` và tự sửa nó, các phép truy cập bên ngoài wrapper không tuân theo khóa của wrapper. Cần kiểm soát alias, encapsulation và chỉ công bố API đã bảo vệ.

### 16.3. Bọc collection nhưng trả iterator ra ngoài lock

Tạo iterator dưới lock rồi duyệt **sau khi đã nhả lock** chưa làm cả quá trình duyệt atomic. Với synchronized wrapper, phải giữ đúng monitor trong quá trình traversal khi cần loại trừ writer. Một giải pháp khác là copy snapshot dưới lock rồi xử lý snapshot bên ngoài.

### 16.4. Sử dụng `ConcurrentModificationException` làm bằng chứng duy nhất

Không có exception không chứng minh thread safety. Có exception không nhất thiết nghĩa là có nhiều thread; một thread sửa trực tiếp list khi đang duyệt cũng đủ.

### 16.5. Tin rằng `ConcurrentHashMap` làm an toàn mọi value

Value mutable cần chính sách riêng. Một `ArrayList` được lấy từ concurrent map vẫn là `ArrayList` thông thường.

### 16.6. Dùng `CopyOnWriteArrayList` cho đường ghi rất nóng

Sao chép mảng mỗi lần mutation khiến workload ghi nhiều có thể tốn thời gian và bộ nhớ. Nó thích hợp cho đọc nhiều/ghi ít, không phải mọi bài toán.

### 16.7. Đợi bằng `Thread.sleep` rồi đọc collection

Sleep không bảo đảm worker đã xong hoặc các write đã được công bố theo yêu cầu. Dùng `join()`, `Future.get()`, latch, queue hoặc phương thức đồng bộ thích hợp.

### 16.8. Biến chung qua static field

Một collection `static` có thể được truy cập từ nhiều phần chương trình và khó kiểm soát ownership. `private static final List<?>` chỉ ngăn thay tham chiếu; không ngăn sửa list. Cân nhắc giới hạn scope, dùng dependency cụ thể và trao immutable snapshot thay vì trạng thái mutable toàn cục.

### 16.9. Không giới hạn queue và công việc đang chờ

Một queue concurrent không blocking có thể không có capacity cố định. Nếu producer chạy nhanh hơn consumer, backlog tăng có thể dẫn đến tiêu thụ bộ nhớ cao. Thread safety chỉ nói về tính đúng của truy cập đồng thời, không bảo đảm quản lý tải hoặc tài nguyên.

### 16.10. Nhầm kiểm thử stress với chứng minh đúng

Chạy 10.000 lần mà chưa thấy lỗi không chứng minh không có race. Dùng đúng hợp đồng API, kiểm tra invariants và quan hệ happens-before. Stress test vẫn hữu ích để phát hiện bug, nhưng không thay thế lý luận về thread safety.

## 17. Hướng dẫn chọn giải pháp cho tình huống thực tế

| Bối cảnh | Thiết kế nên cân nhắc | Vì sao |
| --- | --- | --- |
| Mỗi tác vụ tự xây danh sách kết quả | Local `ArrayList` rồi trả snapshot | Không có shared mutable state trong lúc xây |
| Cần đọc một cấu hình hiếm khi cập nhật | Immutable snapshot và safe publication | Reader không phải tranh lock ở mỗi lần đọc |
| Nhiều worker cập nhật một map theo key | `ConcurrentHashMap.compute/merge` | Hợp đồng hỗ trợ cập nhật atomic theo key |
| Nhiều worker gửi item, một worker tổng hợp | `BlockingQueue` và consumer sở hữu state | Tách producer khỏi mutable accumulator, có thể tạo backpressure |
| Duyệt danh sách listeners thường xuyên, sửa ít | `CopyOnWriteArrayList` | Iterator snapshot, phù hợp tỷ lệ đọc cao |
| Cần duy trì invariant qua hai collection | Một lock bảo vệ toàn bộ transaction hoặc giao thức owner | Chỉ concurrent riêng từng collection chưa đủ |
| Cần danh sách thường nhưng muốn khóa đơn giản | Encapsulated `synchronized` hoặc synchronized wrapper đúng cách | Dễ kiểm soát quyền truy cập nếu discipline thống nhất |
| Cần ordered map concurrent | `ConcurrentSkipListMap` | Có ordering và bảo đảm concurrent theo hợp đồng |

**Câu hỏi quyết định** không phải chỉ "chọn lớp nào", mà là:

1. Bao nhiêu thread thực sự đọc hoặc sửa **cùng một instance**?
2. Có thể tránh chia sẻ mutable data, dùng immutable snapshot hoặc owner duy nhất không?
3. Invariant nghiệp vụ thuộc một thao tác hay nhiều thao tác?
4. API dự kiến có bảo đảm atomic đúng ở ranh giới đó không?
5. Consumer và producer có giao thức hoàn tất, lỗi, timeout/backpressure không?
6. Nếu nhiều thread cùng truy cập, quan hệ happens-before nào bảo đảm visibility?
7. Các value/element mutable có được bảo vệ riêng không?
8. Chọn giải pháp này có phù hợp tỷ lệ đọc/ghi và dung lượng dữ liệu không?

## 18. Tự kiểm tra kiến thức

**Câu 1:** Hai worker đều gọi `list.add(x)` trên cùng một `ArrayList`; có nên dựa vào `list.size()` bằng tổng số lần thêm không?

**Trả lời:** Không nếu không có đồng bộ. Các thao tác cập nhật cấu trúc của `ArrayList` không được bảo đảm an toàn với nhiều writer. Cần một owner, khóa hoặc collection concurrent phù hợp.

**Câu 2:** Nếu dùng `Collections.synchronizedList`, một vòng `for-each` trên list đã đủ an toàn chưa?

**Trả lời:** Chưa chắc. Cần giữ đúng monitor của wrapper trong toàn bộ traversal khi có writer concurrent, hoặc duyệt một snapshot được tạo an toàn.

**Câu 3:** `ConcurrentHashMap` có giải quyết phép `get` rồi `put` để tăng counter atomic không?

**Trả lời:** Không. Dùng `merge`/`compute` theo key, một counter atomic được thiết kế phù hợp hoặc một vùng khóa bao trọn.

**Câu 4:** `List.copyOf` có bảo đảm deep-immutable không?

**Trả lời:** Không. Nó tạo list không sửa được qua API và tách khỏi thay đổi cấu trúc tiếp theo của input mutable trong điều kiện copy hợp lệ, nhưng các phần tử mutable vẫn có thể thay đổi.

**Câu 5:** Có thể kết luận "không có data race" vì không thấy `ConcurrentModificationException` không?

**Trả lời:** Không. Fail-fast có tính best effort, có thể không ném exception. Sự vắng mặt của exception không chứng minh thread safety.

**Câu 6:** Nếu nhiều producer gửi công việc tới một consumer duy nhất, tại sao consumer có thể dùng `ArrayList` thường?

**Trả lời:** Vì consumer là owner duy nhất và không có thread khác sửa/đọc list đó trong lúc mutation. Producer chỉ giao tiếp qua queue an toàn; khi công bố kết quả cho thread khác cần snapshot/publication đúng cách.

**Câu 7:** Một `ConcurrentHashMap<String, ArrayList<Event>>` có an toàn nếu nhiều worker sửa cùng value không?

**Trả lời:** Không tự động. Concurrent map bảo vệ thao tác map; từng value là `ArrayList` thường cần giao thức đồng bộ, immutable replacement hoặc thay đổi ownership.

## 19. Điều cần ghi nhớ

- `ArrayList`, `HashMap`, `HashSet` và nhiều collection thông thường **không tự thread-safe cho truy cập concurrent có mutation**.
- Một race có thể làm sai dữ liệu mà không báo exception; `ConcurrentModificationException` **không** phải bộ xác nhận thread safety.
- `synchronized` hoặc một lock thống nhất có thể bảo vệ **cả chuỗi thao tác** và invariant; synchronized wrapper vẫn cần khóa khi iteration.
- `ConcurrentHashMap`, `BlockingQueue` và `CopyOnWriteArrayList` giải quyết **các nhu cầu khác nhau**; đọc kỹ hợp đồng atomicity, visibility, snapshot và chi phí của từng API.
- **Immutable snapshot**, task-local collection và **single-writer ownership** thường giảm sự phức tạp tốt hơn chia sẻ mutable state tự do.
- Kiểm soát alias của collection, mutable element, safe publication, lifecycle và backpressure cũng là một phần của tính đúng đắn.

Khi thiết kế xử lý đa luồng trong Java, hãy bắt đầu bằng câu hỏi **"Ai sở hữu và có quyền thay đổi collection này?"**. Nếu câu trả lời là nhiều thread, cần chỉ rõ giao thức đồng bộ hoặc chọn đúng concurrent collection **và đúng thao tác atomic**, thay vì mặc định một collection thường sẽ tự xử lý cạnh tranh.