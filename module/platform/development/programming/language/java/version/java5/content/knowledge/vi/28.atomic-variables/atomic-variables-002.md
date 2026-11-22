# AtomicBoolean, AtomicInteger và AtomicLong

## 1. Ba kiểu giá trị, cùng nhu cầu cập nhật an toàn

Trong chương trình nhiều luồng, ta thường có một trạng thái nhỏ dùng chung: một cờ đã có người nhận việc, số tác vụ hoàn tất hoặc số thứ tự tiếp theo. Các lớp `AtomicBoolean`, `AtomicInteger` và `AtomicLong` đặt một giá trị như vậy trong một đối tượng và cung cấp phép cập nhật nguyên tử phù hợp.

**Nguyên tử** nghĩa là một phép cập nhật do API bảo đảm không bị tách thành các phần để một cập nhật cạnh tranh chen vào giữa. Điều này đặc biệt hữu ích với thao tác dựa trên giá trị cũ, chẳng hạn tăng bộ đếm hoặc chỉ đổi cờ khi nó còn `false`.

| Lớp | Kiểu giá trị | Mặc định khi dùng constructor không tham số | Nhu cầu điển hình |
| --- | --- | --- | --- |
| `AtomicBoolean` | `boolean` | `false` | Một luồng giành quyền thực hiện hành động |
| `AtomicInteger` | `int` | `0` | Đếm tác vụ, số lượng trong miền int |
| `AtomicLong` | `long` | `0L` | Số thứ tự, bộ đếm có miền lớn hơn int |

Đây vẫn là các API đang dùng trong Java hiện hành. Chúng không thay thế tùy ý cho `Boolean`, `Integer`, `Long`: wrapper biểu diễn giá trị, còn các đối tượng atomic có trạng thái thay đổi và phép đồng bộ. Xem [tổng quan atomic](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/package-summary.html).

Ví dụ khai báo thành viên trong một lớp:

```java
private final AtomicBoolean claimed = new AtomicBoolean(false);
private final AtomicInteger completed = new AtomicInteger(0);
private final AtomicLong nextNumber = new AtomicLong(1_000L);
```

Các luồng phải nhận cùng một đối tượng chứa những trường này. `final` ngăn gán lại tham chiếu, còn phương thức của đối tượng atomic vẫn thay đổi được giá trị bên trong.

## 2. AtomicBoolean: phân biệt đọc cờ và giành quyền

`get()` chỉ đọc. Cặp `get()` rồi `set()` không phải một quyết định nguyên tử:

```java
// Minh họa sai khi nhiều luồng cùng tranh quyền.
if (!claimed.get()) {
    claimed.set(true);
    doWork();
}
```

Hai luồng có thể cùng thấy `false` rồi cùng thực hiện `doWork()`. Thay bằng **`compareAndSet(false, true)`**: chỉ ghi `true` nếu hiện tại còn `false`; trả `true` khi chuyển trạng thái thành công.

```java
// Minh họa trong phương thức đã có claimed và doWork().
if (claimed.compareAndSet(false, true)) {
    doWork();
}
```

Khi cờ ban đầu là `false` và không ai đặt lại nó, chỉ một lần chuyển `false` → `true` thành công. `getAndSet(v)` là lựa chọn khác: nó đổi giá trị không điều kiện và trả giá trị trước đó. Ví dụ `if (!claimed.getAndSet(true))` nhận ra người đầu tiên đổi cờ từ `false`, nhưng vẫn ghi `true` trong mọi lần gọi. Xem [AtomicBoolean](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html).

### “Đã nhận việc” khác “đã hoàn thành”

Trong đoạn trên, `claimed` trở thành `true` **trước** `doWork()`. Luồng khác thấy `true` chỉ biết đã có người nhận việc; nó không biết công việc đã kết thúc hay kết quả đã sẵn sàng. Nếu `doWork()` ném ngoại lệ, cờ vẫn là `true`.

Do đó, đặt tên theo ý nghĩa thật: `claimed`, `started`, `closed` hay `ready` không đồng nghĩa nhau. Nếu người đến sau phải chờ kết quả hoàn tất, cần một cơ chế biểu diễn hoàn tất như `Future` hoặc một thiết kế trạng thái rõ ràng. Cờ đơn lẻ không tự cung cấp chờ, lưu ngoại lệ hay khởi tạo có thể thử lại.

Cũng không tùy tiện đặt cờ lại `false`: việc đó tạo thêm cơ hội giành quyền và thay đổi bảo đảm từ “một lần nhận việc” thành một quy trình khác. Hãy quyết định rõ hành vi khi thất bại trước khi thêm thao tác đặt lại.

## 3. AtomicInteger: bộ đếm và phép tính nguyên tử

`AtomicInteger` quản lý một số `int`. Những phương thức thường gặp:

| Phương thức | Giá trị trả về |
| --- | --- |
| `get()` | Giá trị hiện tại |
| `getAndIncrement()` | Giá trị cũ, rồi tăng 1 |
| `incrementAndGet()` | Giá trị mới sau khi tăng 1 |
| `getAndDecrement()` | Giá trị cũ, rồi giảm 1 |
| `decrementAndGet()` | Giá trị mới sau khi giảm 1 |
| `getAndAdd(delta)` | Giá trị cũ, rồi cộng delta |
| `addAndGet(delta)` | Giá trị mới sau khi cộng delta |
| `getAndSet(value)` | Giá trị cũ trước khi thay |

Với `n` ban đầu bằng 10, `n.getAndAdd(3)` trả 10 và để lại 13. Tiếp đó, `n.addAndGet(2)` trả 15 và để lại 15. Chọn đúng kết quả cần dùng sẽ tránh một lần `get()` bổ sung có thể quan sát một cập nhật khác.

Đừng viết `n.set(n.get() + 1)` để thay phép tăng: giữa `get()` và `set()`, người ghi khác có thể cập nhật. Tương tự, `if (n.get() < limit) n.incrementAndGet()` không bảo đảm không vượt giới hạn. Từng phép tăng là nguyên tử, nhưng điều kiện kiểm tra và hành động chưa được gắn thành một bước.

`compareAndSet(expected, update)` hoặc một phép cập nhật có điều kiện được thiết kế đúng có thể xử lý trường hợp cần dựa trên trạng thái trước đó. Xem [AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).

## 4. AtomicLong: miền số lớn hơn, cùng quy tắc cập nhật

`AtomicLong` có họ phương thức số học tương tự `AtomicInteger`, nhưng nhận và trả `long`. Chẳng hạn `nextNumber.getAndIncrement()` cấp giá trị hiện tại rồi tăng, phù hợp khi muốn lần cấp đầu trả 1.000.

Tính duy nhất của một dãy số như vậy có phạm vi cụ thể: cùng một đối tượng bộ đếm, không đặt lại, chưa tràn miền số. Nó không tự tạo mã duy nhất toàn hệ thống, không lưu giá trị qua lần khởi động lại và không phối hợp giữa nhiều JVM.

Cả hai lớp vẫn chịu giới hạn kiểu số. `AtomicInteger` không tự ném lỗi khi tăng vượt `Integer.MAX_VALUE`; `AtomicLong` cũng không làm miền số trở thành vô hạn. Với số thứ tự không được lặp, cần định nghĩa chính sách khi hết miền. Xem [AtomicLong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html).

## 5. Ví dụ đầy đủ: một người nhận việc, nhiều người đếm và cấp số

Chương trình sau khởi chạy bốn tác vụ. Mỗi tác vụ thử nhận một quyền duy nhất, rồi thực hiện 1.000 lần tăng bộ đếm và lấy số thứ tự. Quyền nhận việc chỉ là phép thử cơ chế CAS; ví dụ không tuyên bố khởi tạo một tài nguyên dùng chung đã hoàn tất.

Mỗi tác vụ trả mảng số của riêng nó. Luồng `main` chờ kết quả rồi đưa các số vào `TreeSet`; không có nhiều luồng cùng sửa `TreeSet`. Cách này tách việc kiểm tra trùng số khỏi bộ đếm đang thử.

Lưu thành `AtomicTypesDemo.java`, dùng JDK 17 trở lên:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicTypesDemo {
    public static void main(String[] args) throws Exception {
        int workers = 4;
        int repetitions = 1_000;
        AtomicBoolean claimed = new AtomicBoolean(false);
        AtomicInteger claimCount = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();
        AtomicLong nextNumber = new AtomicLong(1_000L);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        List<Future<long[]>> results = new ArrayList<>();

        try {
            for (int w = 0; w < workers; w++) {
                results.add(pool.submit(() -> {
                    start.await();
                    if (claimed.compareAndSet(false, true)) {
                        claimCount.incrementAndGet();
                    }
                    long[] numbers = new long[repetitions];
                    for (int i = 0; i < repetitions; i++) {
                        numbers[i] = nextNumber.getAndIncrement();
                        completed.incrementAndGet();
                    }
                    return numbers;
                }));
            }
            start.countDown();

            TreeSet<Long> unique = new TreeSet<>();
            for (Future<long[]> result : results) {
                for (long number : result.get()) {
                    unique.add(number);
                }
            }

            System.out.println("claims=" + claimCount.get());
            System.out.println("completed=" + completed.get());
            System.out.println("unique=" + unique.size());
            System.out.println("range=" + unique.first() + ".." + unique.last());
            System.out.println("next=" + nextNumber.get());

            AtomicInteger sample = new AtomicInteger(10);
            int before = sample.getAndAdd(3);
            int after = sample.addAndGet(2);
            System.out.println("before=" + before + ", after=" + after);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac AtomicTypesDemo.java
java AtomicTypesDemo
```

Stdout:

```text
claims=1
completed=4000
unique=4000
range=1000..4999
next=5000
before=10, after=15
```

Ai giành quyền hoặc nhận một số cụ thể phụ thuộc lịch chạy, nhưng tổng số quyền thành công là 1. Có 4.000 phép tăng bộ đếm và 4.000 số được cấp khác nhau. Vì dãy bắt đầu 1.000, số cuối đã cấp là 4.999 và giá trị chuẩn bị cho lần sau là 5.000.

Các dòng tổng được đọc sau khi toàn bộ `Future.get()` đã hoàn tất. Nếu in ngay lúc tác vụ còn chạy, tổng chỉ phản ánh thời điểm quan sát, không phải kết quả cuối. `CountDownLatch` dùng để cho phép các tác vụ bắt đầu làm việc sau khi đã được gửi; nó không bảo đảm chúng chạy trên CPU đúng cùng một nhịp.

## 6. Đọc, ghi và công bố dữ liệu

Các thao tác thông thường như `get()` và `set()` có hiệu ứng bộ nhớ tương ứng với đọc/ghi `volatile`. CAS thông thường cũng có hiệu ứng bộ nhớ được API quy định. Do đó các lớp này hỗ trợ trao đổi trạng thái giữa luồng, không chỉ tránh mất phép cộng.

Tuy nhiên, thứ tự chương trình vẫn quan trọng. Nếu muốn công bố kết quả bằng cờ `ready`, phải hoàn thành việc ghi dữ liệu **trước** khi công bố `ready=true`; bên đọc chỉ sử dụng dữ liệu sau khi quan sát cờ theo đúng giao thức. Việc đặt `started=true` rồi mới tính kết quả không công bố các thao tác chưa xảy ra.

Không cần thêm `volatile` vào một trường `final AtomicInteger` chỉ để các phương thức atomic hoạt động. Nếu chương trình cho phép thay luôn đối tượng bộ đếm, cần xem xét riêng việc chia sẻ tham chiếu; đơn giản hơn thường là giữ nguyên đối tượng và chỉ cập nhật giá trị bên trong.

Bài này dùng các phương thức thông thường. Các biến thể có hậu tố `Plain`, `Opaque`, `Acquire`, `Release` có bảo đảm khác; không thay vào chỉ vì chúng có vẻ gần giống tên.

## 7. Phép cập nhật bằng hàm và phạm vi bảo đảm

Hai lớp số có `updateAndGet`, `getAndUpdate`, `accumulateAndGet` và `getAndAccumulate`. Với `AtomicLong total`, ví dụ minh họa cộng bằng hàm là:

```java
long value = total.updateAndGet(current -> current + 20L);
```

Hàm có thể được đánh giá lại do tranh chấp, nên chỉ nên tính kết quả mới từ đầu vào. Không thực hiện gửi thông báo, trừ tài khoản ngoài hoặc ghi nhật ký nghiệp vụ trong hàm đó rồi giả định nó chạy đúng một lần.

Những bảo đảm atomic cũng có ranh giới:

- Hai bộ đếm riêng không có bản chụp chung nguyên tử. Đọc `accepted.get()` rồi `finished.get()` có thể lấy số liệu ở hai thời điểm khác nhau.
- Đổi cờ và tăng bộ đếm là hai bước; không biến thành một giao dịch chỉ vì cả hai dùng atomic.
- `synchronized` trên đối tượng atomic không tự chặn luồng khác gọi trực tiếp `incrementAndGet()`; muốn bảo vệ thao tác ghép bằng khóa, mọi bên phải tuân thủ cùng quy tắc khóa.
- Một lần CAS có thể thất bại khi có người cập nhật khác. Thuật toán lặp thử lại không tự hứa công bằng hay số vòng cố định cho một luồng.
- Hiệu năng cần đo theo tải và mức tranh chấp thực tế; thay mọi biến bằng atomic không tự cải thiện thiết kế.

## 8. Chọn lớp theo ý nghĩa trạng thái

Chọn `AtomicBoolean` khi cần chuyển trạng thái hai giá trị có điều kiện, chẳng hạn giành quyền một lần. Chọn `AtomicInteger` khi cần phép tính nguyên tử trên miền int. Chọn `AtomicLong` khi cần miền long hoặc một chuỗi số dài hơn. Với trạng thái gồm nhiều trường phải thay cùng nhau, hãy thiết kế một ranh giới đồng bộ bao phủ toàn bộ bất biến thay vì chỉ đổi từng trường sang một lớp atomic.

Tự kiểm tra hai câu hỏi khi đọc mã: **phép nào thực sự được API làm nguyên tử, và kết quả trả về là trước hay sau phép cập nhật?** Hai câu trả lời này giúp phát hiện phần lớn nhầm lẫn khi sử dụng ba lớp.
