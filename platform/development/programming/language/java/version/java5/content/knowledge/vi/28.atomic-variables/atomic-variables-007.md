# AtomicIntegerArray, AtomicLongArray và AtomicReferenceArray

## 1. Mảng nguyên tử bảo vệ từng vị trí

Khi nhiều luồng cùng cập nhật số liệu theo nhóm, ta có thể cần nhiều bộ đếm có chỉ số: số yêu cầu cho từng loại, tổng số byte cho từng kênh hoặc bản trạng thái cho từng phân vùng. Ba lớp mảng nguyên tử trong `java.util.concurrent.atomic` cung cấp thao tác nguyên tử **trên một phần tử được chọn bằng chỉ số**.

| Lớp | Giá trị ở mỗi vị trí | Giá trị ban đầu khi tạo theo độ dài |
| --- | --- | --- |
| `AtomicIntegerArray` | `int` | `0` |
| `AtomicLongArray` | `long` | `0L` |
| `AtomicReferenceArray<E>` | Tham chiếu kiểu E | `null` |

Phạm vi bảo đảm là một ô, không phải toàn bộ mảng. Hai ô được cập nhật riêng không tự tạo một giao dịch chung. Những lớp này vẫn được dùng trong Java hiện hành; ví dụ trong bài chạy được trên JDK 17 trở lên. Xem [AtomicIntegerArray](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html), [AtomicLongArray](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicLongArray.html) và [AtomicReferenceArray](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReferenceArray.html).

Một trường `volatile int[]` chỉ làm thao tác với **tham chiếu tới mảng** có ngữ nghĩa volatile; nó không biến mọi `array[i]++` thành phép tăng nguyên tử. Tương tự, đặt cả mảng trong `AtomicReference<int[]>` chỉ quản lý việc đổi tham chiếu, không tự bảo vệ việc sửa từng số bên trong.

## 2. Khởi tạo và truy cập

Có thể tạo bằng độ dài hoặc sao chép từ một mảng thường:

```java
AtomicIntegerArray counts = new AtomicIntegerArray(3);
AtomicLongArray totals = new AtomicLongArray(new long[] {100L, 200L});
AtomicReferenceArray<String> names = new AtomicReferenceArray<>(3);
```

Độ dài cố định sau khi tạo. Dùng `length()` để đọc độ dài, `get(i)` để đọc phần tử và `set(i, value)` để thay giá trị. Không dùng cú pháp `counts[i]` vì đây là đối tượng thư viện, không phải kiểu mảng Java.

Các constructor nhận mảng sao chép phần tử sang vùng lưu trữ riêng. Sửa một phần tử trong mảng nguồn sau đó không thay ô tương ứng trong đối tượng atomic; cập nhật đối tượng atomic cũng không ghi ngược vào mảng nguồn.

Với `AtomicReferenceArray`, đó là **sao chép tham chiếu**, không sao chép sâu đối tượng. Nếu cả mảng nguồn và mảng atomic vẫn trỏ tới cùng một đối tượng có thể sửa, thay nội dung đối tượng ấy vẫn ảnh hưởng những người cùng giữ tham chiếu. Việc thay `source[i]` sang đối tượng khác và việc sửa đối tượng mà `source[i]` đang trỏ tới là hai việc khác nhau.

Chỉ số hợp lệ từ 0 đến `length() - 1`. Truy cập chỉ số âm hoặc vượt giới hạn gây `IndexOutOfBoundsException`. Độ dài 0 là hợp lệ nhưng không có chỉ số nào truy cập được.

## 3. Thao tác nguyên tử trên mảng số

Các phương thức của `AtomicIntegerArray` và `AtomicLongArray` giống họ atomic đơn, nhưng có thêm tham số đầu tiên là chỉ số:

| Phương thức | Ý nghĩa tại vị trí i |
| --- | --- |
| `get(i)` | Đọc giá trị hiện tại |
| `set(i, value)` | Ghi giá trị mới |
| `getAndIncrement(i)` | Tăng 1, trả giá trị cũ |
| `incrementAndGet(i)` | Tăng 1, trả giá trị mới |
| `getAndAdd(i, delta)` | Cộng delta, trả giá trị cũ |
| `addAndGet(i, delta)` | Cộng delta, trả giá trị mới |
| `getAndSet(i, value)` | Thay giá trị và trả giá trị trước đó |
| `compareAndSet(i, expected, next)` | Chỉ thay nếu hiện tại bằng expected |

Ví dụ một nhóm yêu cầu được ánh xạ về vị trí `bucket`:

```java
int totalRequests = counts.incrementAndGet(bucket);
long totalBytes = bytes.addAndGet(bucket, 512L);
```

Mỗi phép trên an toàn với các cập nhật cạnh tranh vào cùng vị trí. Nhưng chúng là hai phép riêng: ở giữa, có thể đã tăng số yêu cầu mà chưa tăng số byte. Nếu người đọc cần quan hệ nhất quán giữa hai số tại mọi thời điểm, cần thiết kế một trạng thái chung hoặc cơ chế đồng bộ rộng hơn.

Không thay phép tăng bằng `counts.set(i, counts.get(i) + 1)`: người ghi khác có thể chen vào giữa lần đọc và lần ghi. `get()` và `set()` có bảo đảm riêng không có nghĩa cặp đó là một thao tác đọc–sửa–ghi nguyên tử.

## 4. AtomicReferenceArray bảo vệ tham chiếu

Một ô của `AtomicReferenceArray<E>` chứa tham chiếu tới E hoặc `null`. Những thao tác chính là đọc, thay, CAS và cập nhật bằng hàm; nó không có phép cộng số học như hai lớp mảng số.

**CAS so sánh tham chiếu bằng `==`, không gọi `equals()`.** Hai đối tượng biểu diễn cùng một giá trị vẫn là hai tham chiếu khác. Khi viết vòng cập nhật có điều kiện, thường đọc chính tham chiếu hiện tại rồi dùng nó làm `expected`.

Nếu E có thể bị sửa, `items.get(i).changeSomething()` không được tự động bảo vệ bởi mảng. Phương án thường dễ kiểm soát là dùng giá trị bất biến: tạo một phiên bản mới rồi thay cả tham chiếu trong ô. Nếu bản trạng thái có các trường tham chiếu tới đối tượng còn có thể sửa, vẫn phải xử lý tính bất biến của các đối tượng đó.

`updateAndGet(i, function)` có thể tính lại hàm khi tranh chấp. Hàm nên chỉ tạo kết quả mới từ đầu vào; không gửi thông báo hoặc thực hiện tác dụng phụ mang ý nghĩa đã cập nhật thành công bên trong hàm.

## 5. Ví dụ đầy đủ: hai nhóm thống kê và trạng thái bất biến

Chương trình dùng bốn tác vụ; hai tác vụ cập nhật nhóm 0, hai tác vụ cập nhật nhóm 1. Mỗi tác vụ lặp 1.000 lần:

- Tăng bộ đếm yêu cầu trong `AtomicIntegerArray`.
- Cộng 512 byte trong `AtomicLongArray`.
- Thay bản trạng thái `Slot` trong `AtomicReferenceArray` bằng một bản mới.

`Slot` là record chỉ chứa `String` và `int`, không có đối tượng con có thể sửa. Các số liệu được kiểm tra sau khi tất cả tác vụ hoàn tất, nên không đòi hỏi một giao dịch chung giữa ba mảng.

Lưu thành `AtomicArraysDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicIntegerArray;
import java.util.concurrent.atomic.AtomicLongArray;
import java.util.concurrent.atomic.AtomicReferenceArray;

public class AtomicArraysDemo {
    record Slot(String name, int processed) { }

    public static void main(String[] args) throws Exception {
        int[] source = {7, 0};
        AtomicIntegerArray copied = new AtomicIntegerArray(source);
        source[0] = 99;
        copied.set(1, 8);
        System.out.println("source=" + source[0] + "," + source[1]);
        System.out.println("copy=" + copied.get(0) + "," + copied.get(1));

        AtomicIntegerArray counts = new AtomicIntegerArray(2);
        AtomicLongArray bytes = new AtomicLongArray(2);
        AtomicReferenceArray<Slot> states = new AtomicReferenceArray<>(2);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<?>> tasks = new ArrayList<>();
        try {
            for (int worker = 0; worker < 4; worker++) {
                int bucket = worker % 2;
                tasks.add(pool.submit(() -> {
                    for (int n = 0; n < 1_000; n++) {
                        counts.incrementAndGet(bucket);
                        bytes.addAndGet(bucket, 512L);
                        states.updateAndGet(bucket, previous -> new Slot(
                                "bucket-" + bucket,
                                previous == null ? 1 : previous.processed() + 1));
                    }
                }));
            }
            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            pool.shutdownNow();
        }

        for (int i = 0; i < counts.length(); i++) {
            System.out.println("bucket=" + i + ", count=" + counts.get(i)
                    + ", bytes=" + bytes.get(i)
                    + ", state=" + states.get(i).processed());
        }

        Slot actual = states.get(0);
        Slot equalValue = new Slot(actual.name(), actual.processed());
        Slot replacement = new Slot("replaced", 3_000);
        System.out.println("equal value=" + actual.equals(equalValue));
        System.out.println("CAS equal object="
                + states.compareAndSet(0, equalValue, replacement));
        System.out.println("CAS actual reference="
                + states.compareAndSet(0, actual, replacement));
        System.out.println("final name=" + states.get(0).name());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac AtomicArraysDemo.java
java AtomicArraysDemo
```

Stdout:

```text
source=99,0
copy=7,8
bucket=0, count=2000, bytes=1024000, state=2000
bucket=1, count=2000, bytes=1024000, state=2000
equal value=true
CAS equal object=false
CAS actual reference=true
final name=replaced
```

Hai dòng đầu cho thấy mảng số nguồn và bản sao atomic không dùng chung các ô lưu số. Mỗi nhóm có 2.000 lượt cập nhật nên tổng byte bằng `2000 × 512 = 1024000`.

Phần CAS được chạy sau khi các tác vụ hoàn tất. `equalValue` có cùng nội dung với `actual` nhưng là một record được tạo mới, nên CAS dùng nó làm kỳ vọng thất bại. CAS dùng chính tham chiếu `actual` thành công. Phần thay trạng thái cuối là minh chứng riêng cho CAS, không phải một lần xử lý yêu cầu nữa.

## 6. Đọc cả mảng không tạo bản chụp nguyên tử

Một vòng `for` gọi `get(i)` đọc từng vị trí tại từng thời điểm. Nếu các luồng vẫn cập nhật, kết quả có thể trộn trạng thái trước và sau các lần cập nhật khác nhau. `toString()` cũng không phải giao dịch chụp toàn bộ mảng.

Ví dụ có hai vị trí biểu diễn số lượng ở hai kho; một thao tác chuyển hàng trừ vị trí 0 rồi cộng vị trí 1. Dù mỗi lần cộng/trừ là nguyên tử, người đọc tổng ở giữa vẫn có thể thấy tổng giảm tạm thời. Mảng nguyên tử không cung cấp CAS đồng thời cho hai vị trí.

Khi yêu cầu nghiệp vụ cần bất biến liên vị trí, có thể dùng khóa chung mà mọi người đọc/ghi đều tuân theo, hoặc đóng gói toàn bộ trạng thái cần thay cùng nhau thành một giá trị bất biến được quản lý chung. Không chỉ thêm một khóa quanh bên ghi rồi để bên đọc tùy ý đọc từng ô và kỳ vọng có bản chụp nhất quán.

Nếu chỉ cần kết quả cuối như chương trình trên, chờ mọi tác vụ hoàn tất trước khi đọc là đủ cho cách kiểm tra đó. Điều này khác với yêu cầu thống kê nhất quán trong lúc cập nhật vẫn đang diễn ra.

## 7. Các điểm thực hành cần nhớ

- Ánh xạ dữ liệu vào chỉ số ổn định. Một phép cập nhật nguyên tử vào nhầm nhóm vẫn cho kết quả nghiệp vụ sai.
- Dùng cùng đối tượng mảng atomic giữa những luồng cần chia sẻ số liệu; tạo một đối tượng mới cho từng yêu cầu sẽ tách số liệu.
- Hai lớp mảng số vẫn có thể tràn `int` hoặc `long`; tính nguyên tử không tự kiểm tra miền số.
- `get()`/`set()` thông thường có hiệu ứng bộ nhớ tương ứng với đọc/ghi volatile của phần tử. Các biến thể `Plain`, `Opaque`, `Acquire`, `Release` có quy tắc khác, cần hiểu hợp đồng trước khi dùng.
- Không sửa đối tượng có thể thay đổi bên trong hàm cập nhật của `AtomicReferenceArray` rồi trả lại chính nó như thể đó là một phép thay trạng thái nguyên tử.
- Trong vòng CAS, đọc lại và tính lại khi thất bại; không dựa vào tham chiếu kỳ vọng cũ mãi. CAS cũng không chứng minh tham chiếu chưa từng đổi đi rồi quay lại.
- Khi nhiều luồng tranh chấp cùng một ô, có thể phải thử lại khi cập nhật bằng hàm hoặc CAS. Đánh giá hiệu năng từ phép đo phù hợp; không suy rằng chia mảng thành nhiều ô luôn loại bỏ mọi tranh chấp phần cứng.

## 8. Tự kiểm tra

1. `AtomicIntegerArray(5)` có năm đối tượng `AtomicInteger` để truy cập bằng `a[i]` không? **Không**, API thao tác trực tiếp các giá trị qua phương thức có chỉ số.
2. Hai lần cập nhật ở hai chỉ số có phải một giao dịch nguyên tử không? **Không**.
3. `AtomicReferenceArray` chứa `ArrayList` có làm `list.add()` an toàn giữa nhiều luồng không? **Không**, nó bảo vệ ô tham chiếu chứ không tự bảo vệ cấu trúc bên trong danh sách.
4. CAS tham chiếu có chấp nhận một đối tượng khác chỉ vì `equals()` trả `true` không? **Không**, nó yêu cầu khớp tham chiếu.
5. Constructor nhận mảng tham chiếu có sao chép sâu các đối tượng không? **Không**, nó sao chép các tham chiếu vào các ô riêng.
