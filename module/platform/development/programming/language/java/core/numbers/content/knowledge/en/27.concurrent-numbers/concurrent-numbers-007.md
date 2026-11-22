# sum() của adder không phải snapshot nguyên tử trong lúc đang cập nhật

`LongAdder` và `DoubleAdder` trong `java.util.concurrent.atomic` được thiết kế cho trường hợp **nhiều luồng cùng cập nhật một tổng hoặc bộ đếm**, đặc biệt để giảm tranh chấp khi tần suất cập nhật cao. Chúng có thể cho thông lượng cập nhật tốt hơn `AtomicLong` trong một số tình huống contention cao, đổi lại cách đọc tổng bằng `sum()` có hợp đồng yếu hơn một thao tác đọc nguyên tử.

Điểm cốt lõi của bài: **mỗi lời gọi `increment()`/`add()` có thể cập nhật trạng thái chia sẻ một cách an toàn giữa các luồng, nhưng `sum()` không bảo đảm lấy toàn bộ tổng tại một thời điểm nguyên tử duy nhất khi có cập nhật đồng thời.** Bài học thuộc nhóm *Số và đồng thời*, tập trung giải thích cơ chế này, hậu quả khi dùng `sum()` làm điều kiện đúng/sai, thời điểm nào kết quả đáng tin cậy và khi nào cần chọn cơ chế khác.

## 1. Ba khái niệm khác nhau: cập nhật an toàn, đọc tổng và snapshot nguyên tử

Cần phân biệt:

1. **Cập nhật an toàn giữa các luồng (thread-safe update):** nhiều luồng gọi `adder.increment()` hoặc `adder.add(delta)` mà không phải dùng một biến `long` thông thường với `count++` gây mất cập nhật do data race.
2. **Giá trị tổng được đọc (aggregate read):** `adder.sum()` cộng những thành phần đang giữ tổng và trả về một `long`. Giá trị này hữu ích để quan sát số liệu hoạt động.
3. **Snapshot nguyên tử (atomic snapshot):** một thao tác đọc được bảo đảm có thể xem như đọc toàn bộ trạng thái ở **một thời điểm logic duy nhất** giữa lúc bắt đầu và kết thúc thao tác, dù các luồng khác vẫn cập nhật.

`LongAdder.sum()` đáp ứng mục đích (2) nhưng tài liệu API **không hứa điều (3)**. Trong lúc nó lấy số liệu từ các thành phần, một số cập nhật khác có thể diễn ra. Do vậy, kết quả có thể **không chứa tất cả cập nhật trùng với khoảng thời gian đọc**. Khi không còn cập nhật đồng thời, `sum()` trả tổng chính xác của các cập nhật đã hoàn tất, giả sử không có vấn đề tràn số hoặc thao tác reset làm thay đổi trạng thái.

Không nên nhầm **snapshot không nguyên tử** với **mọi phép cộng đều sai**. Các lời gọi cập nhật của `LongAdder` vẫn phục vụ đếm đồng thời; thiếu bảo đảm nằm ở thao tác *quan sát tập hợp các thành phần tại cùng một thời điểm*, không phải việc `LongAdder` biến thành một biến `long` không đồng bộ.

## 2. Vì sao LongAdder có tổng gồm nhiều phần?

`AtomicLong` giữ một giá trị nguyên tử duy nhất. Khi nhiều luồng cập nhật cùng giá trị bằng CAS hoặc các thao tác atomic, chúng có thể tranh chấp trên cùng điểm cập nhật.

`LongAdder` giải quyết bài toán khác: giữ một **giá trị nền** và có thể mở rộng thêm các **ô thành phần (cells/stripes)** khi có tranh chấp. Nhiều luồng được phân tán giữa các ô để giảm contention khi thêm vào tổng. Mô hình khái niệm:

~~~text
Writers:
Thread A --add(1)--> base / cell[0]
Thread B --add(1)-->        cell[1]
Thread C --add(1)-->        cell[2]
                                 |
Reader: sum() ------------------+--> cộng base + các cell
                                      theo từng lượt đọc
~~~

Đây là **sơ đồ giải thích cơ chế**, không phải cam kết về số lượng ô, cách ánh xạ thread sang ô hoặc thuật toán từng dòng trong mọi JDK. Tùy mức contention, cấu trúc có thể khác nhau.

Nếu một phép đọc tổng phải truy cập nhiều ô liên tiếp, nó không thể mặc nhiên coi các giá trị vừa đọc là **một bản chụp chung bất biến**. Trong khi reader đọc ô thứ nhất, writer có thể cập nhật ô thứ hai; trước khi reader đọc ô tiếp theo, writer khác cũng có thể cập nhật ô thứ nhất. Các lần đọc thành phần xảy ra vào những thời điểm khác nhau.

JavaDoc mô tả rõ hợp đồng của `LongAdder.sum()`: **không phải atomic snapshot**; nếu không có cập nhật đồng thời, kết quả chính xác, còn các cập nhật xảy ra trong khi tính tổng có thể không được tính vào kết quả trả về.

Điều này không có nghĩa `sum()` nhất thiết trả kết quả sai hoặc thiếu trong mỗi lần chạy. Trên workload đơn giản, một lần đo có thể tình cờ khớp tổng ở thời điểm nào đó. **Không thể chứng minh tính nguyên tử chỉ bằng việc chạy thử nhiều lần mà luôn thấy con số hợp lý.**

## 3. LongAdder có những API nào liên quan?

| API | Ý nghĩa | Cần lưu ý khi dùng đồng thời |
|---|---|---|
| `new LongAdder()` | Tạo tổng ban đầu bằng 0 | Chia sẻ đúng một instance giữa các writer khi cùng một bộ đếm |
| `add(long x)` | Cộng giá trị `x` (có thể âm) | An toàn cho cập nhật đồng thời |
| `increment()` | Tương đương `add(1)` | Hợp lý cho bộ đếm sự kiện |
| `decrement()` | Tương đương `add(-1)` | Có cập nhật giảm; không suy đoán tổng luôn tăng |
| `sum()` | Đọc tổng từ các thành phần | **Không phải atomic snapshot** khi có writer đồng thời |
| `longValue()` | Tương đương `sum()` | Không mạnh hơn `sum()` |
| `toString()` | Chuyển kết quả `sum()` thành chuỗi | Không phải một snapshot mạnh hơn |
| `reset()` | Đặt các phần giữ tổng về 0 | Chỉ dùng khi biết không có writer đồng thời |
| `sumThenReset()` | Đọc tổng rồi reset về 0 | Không phải thao tác nguyên tử đọc-và-xóa khi writer vẫn chạy |

Đặc biệt, `sumThenReset()` **không tương đương** với thao tác nguyên tử `AtomicLong.getAndSet(0)` về độ bảo đảm dưới contention. Các phần giữ tổng được xử lý lần lượt; nếu writer cập nhật trong lúc reset, API không bảo đảm giá trị trả về chính là toàn bộ dữ liệu trước ranh giới reset. Không dùng `sumThenReset()` như một công cụ tự động chia số liệu thành các cửa sổ **không mất hoặc đếm nhầm cập nhật** khi các writer vẫn hoạt động.

## 4. Ví dụ Java 17+ chạy độc lập, kết quả có thể kiểm chứng

Tệp `AdderSnapshotDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.LongAdder;

public class AdderSnapshotDemo {
    public static void main(String[] args) throws InterruptedException {
        final int workers = 4;
        final int iterations = 50_000;
        LongAdder counter = new LongAdder();
        CountDownLatch go = new CountDownLatch(1);
        Thread[] threads = new Thread[workers];

        for (int i = 0; i < workers; i++) {
            threads[i] = new Thread(() -> {
                try {
                    go.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                for (int j = 0; j < iterations; j++) {
                    counter.increment();
                }
            });
            threads[i].start();
        }

        System.out.println("before release = " + counter.sum());
        go.countDown();

        // Chỉ quan sát: KHÔNG khẳng định đây là snapshot nguyên tử.
        long during = counter.sum();
        System.out.println("during within range = " +
                (during >= 0 && during <= workers * iterations));

        // Sau join(): không còn writer cập nhật counter.
        for (Thread thread : threads) {
            thread.join();
        }
        System.out.println("after join = " + counter.sum());

        // sumThenReset được dùng khi hoàn toàn không có writer.
        LongAdder batch = new LongAdder();
        batch.add(3);
        batch.add(4);
        System.out.println("quiescent batch = " + batch.sumThenReset());
        System.out.println("after reset = " + batch.sum());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AdderSnapshotDemo.java
java AdderSnapshotDemo
~~~

Kết quả mong đợi (khi không có gián đoạn từ bên ngoài):

~~~text
before release = 0
during within range = true
after join = 200000
quiescent batch = 7
after reset = 0
~~~

Giải thích:

- Trước `go.countDown()`, mọi worker đang đợi cổng `CountDownLatch`, nên chưa có `increment()`: kết quả 0 là ổn định.
- Sau khi mở cổng, `during` có thể là 0, vài nghìn, 200.000 hoặc một giá trị khác trong miền kiểm tra; chương trình **không in số cụ thể của `during`** vì nó phụ thuộc lịch thực thi.
- Trong ví dụ chỉ có **tăng 1**, không reset/giảm/tràn `long` và tổng các lần tăng tối đa 200.000. Kiểm tra miền giá trị là hợp lý cho ví dụ này, **nhưng không chứng minh `sum()` là snapshot nguyên tử**.
- `Thread.join()` đợi cả bốn worker kết thúc. Mỗi worker thực hiện 50.000 cập nhật, nên sau `join()` không còn writer, `sum()` cho chính xác `4 × 50.000 = 200.000`. `join()` cũng thiết lập quan hệ happens-before để thread chính quan sát kết quả công việc đã hoàn tất.
- `batch.sumThenReset()` trả 7 và reset về 0 **vì ở đoạn này không có cập nhật đồng thời**.

Mã trên là ví dụ học về hợp đồng API, **không phải phép thử race có mục tiêu ép JVM lộ ra một kết quả sai**. Hành vi quan sát giữa chừng không mang tính xác định; nếu muốn kiểm chứng đúng/sai cần dựa vào hợp đồng và phân tích cơ chế, không viết unit test đòi một giá trị `during` cụ thể.

## 5. Diễn tiến thời gian: vì sao không có một thời điểm chụp chung?

Giả sử nội bộ đang giữ hai thành phần tương ứng với các nhóm writer. Diễn tiến minh họa:

| Mốc | Writer | Reader gọi `sum()` |
|---|---|---|
| t0 | Các ô đang chứa cập nhật đã hoàn tất | Bắt đầu tính tổng |
| t1 | Writer A cập nhật thành phần thứ nhất | Reader đã hoặc đang đọc thành phần thứ nhất |
| t2 | Writer B cập nhật thành phần thứ hai | Reader đọc thành phần thứ hai |
| t3 | Các cập nhật khác tiếp tục | Reader cộng những giá trị nó đã đọc |
| t4 | Writer vẫn có thể chạy | `sum()` trả một số |

Không có một "điểm đóng băng" chung cho tất cả thành phần. Một số cập nhật đồng thời có thể được bao gồm, một số không; không thể nói `sum()` nhất thiết phản ánh tổng **tại chính thời điểm gọi**, **thời điểm trả về**, hay **toàn bộ cập nhật đã xảy ra trong khi đọc**.

**Chú ý sự khác nhau giữa hai phát biểu:**
- **Đúng:** `sum()` không bảo đảm snapshot nguyên tử khi đang có cập nhật.
- **Sai nếu nói chung:** Mọi kết quả `sum()` trong lúc cập nhật đều là "số rác" hoặc tất cả đều không chính xác.

Với bộ đếm chỉ tăng từ 0, không reset, không overflow, việc đọc giữa chừng thường đủ để vẽ đồ thị số sự kiện tăng dần theo thời gian. Nhưng một biểu đồ cho mục đích quan sát **khác về yêu cầu** với số liệu phải đóng sổ chính xác tại một mốc nghiệp vụ.

## 6. So sánh LongAdder với AtomicLong

| Tiêu chí | `LongAdder` | `AtomicLong` |
|---|---|---|
| Trạng thái cộng dồn | Có thể gồm nhiều thành phần | Một giá trị `long` nguyên tử |
| Cập nhật `+1` | `increment()` | `incrementAndGet()` hoặc `getAndIncrement()` |
| Đọc | `sum()`: không atomic snapshot khi update đồng thời | `get()`: đọc nguyên tử một giá trị |
| Đọc rồi đặt 0 | `sumThenReset()`: không an toàn như một ranh giới nguyên tử khi còn writer | `getAndSet(0)`: thao tác trao đổi nguyên tử trên **một** giá trị |
| Contention tăng cao | Thường giảm tranh chấp cho workload nhiều cập nhật | Có thể tranh chấp trên một biến |
| Tài nguyên | Có thể dùng thêm bộ nhớ cho các ô | Một biến trạng thái chính |
| Phù hợp | Metric, histogram, thống kê cập nhật thường xuyên và đọc để quan sát | Bộ đếm cần quyết định dựa trên giá trị nguyên tử, thứ tự cập nhật, CAS/giới hạn |

`AtomicLong.get()` có tính nguyên tử ở cấp **một giá trị**; điều này không tạo snapshot nguyên tử của **nhiều** `AtomicLong` hoặc các cấu trúc dữ liệu khác. Muốn giữ bất biến giữa nhiều trường, vẫn cần cơ chế phối hợp thích hợp (ví dụ khóa chung hoặc trạng thái bất biến được công bố bằng một tham chiếu nguyên tử).

Không nên coi bảng là khẳng định `LongAdder` lúc nào cũng nhanh hơn. Hiệu năng phụ thuộc số luồng, mức tranh chấp, số lần đọc, CPU, cách sử dụng bộ đếm và JVM. Nếu cần tối ưu, đo workload thực bằng công cụ benchmark thích hợp, không suy từ một vòng lặp nhỏ in ra thời gian.

## 7. Trường hợp dùng LongAdder đúng: metric và thống kê

Một ví dụ phổ biến là **bộ đếm số yêu cầu xử lý**:

~~~java
import java.util.concurrent.atomic.LongAdder;

public class RequestMetrics {
    private final LongAdder processed = new LongAdder();

    public void onProcessed() {
        processed.increment();
    }

    public long reportApproximate() {
        return processed.sum();
    }
}
~~~

Mã này là một lớp dùng lại được; khi nhiều thread gọi `onProcessed()`, thao tác tăng an toàn. `reportApproximate()` dùng trong lúc worker tiếp tục chạy là phép đọc quan sát, có thể không chứa mọi cập nhật đồng thời. Đặt tên/đặc tả API rõ như `estimate`, `observedTotal` hoặc mô tả "giá trị tại lần scrape" để người tiêu thụ không nhầm với số đã đóng sổ.

Dùng trong hệ thống metric có thể chấp nhận chênh lệch quan sát ngắn hạn vì lần thu thập sau sẽ thấy các cập nhật đã hoàn tất (trừ trường hợp ứng dụng reset hoặc overflow). Không suy rộng điều này sang mọi cách thu thập/chia cửa sổ: nếu dùng `sumThenReset()` trong lúc writer cập nhật, không có bảo đảm phân bổ chính xác mỗi sự kiện vào đúng cửa sổ.

Một cách lập histogram có nhiều khóa:

~~~java
ConcurrentHashMap<String, LongAdder> frequencies =
        new ConcurrentHashMap<>();

frequencies.computeIfAbsent("OK", key -> new LongAdder()).increment();
frequencies.computeIfAbsent("ERROR", key -> new LongAdder()).increment();

long ok = frequencies.get("OK").sum();
~~~

Đoạn mã cần `import java.util.concurrent.ConcurrentHashMap;` và `LongAdder`, đặt trong một phương thức. `computeIfAbsent` bảo đảm tạo/công bố giá trị cho khóa theo cơ chế của `ConcurrentHashMap`, còn mỗi `LongAdder` giữ thống kê từng khóa. Nhưng việc đọc **nhiều khóa** thành một báo cáo không tạo ra snapshot nhất quán của toàn bản đồ hoặc của mọi `LongAdder` tại cùng một thời điểm.

## 8. Trường hợp không nên dùng sum() để ra quyết định nghiêm ngặt

### A. Không dùng làm bộ cấp ID duy nhất

~~~java
long next = adder.sum() + 1;
// Không an toàn để cấp ID duy nhất rồi mới gọi increment().
~~~

Hai thread có thể quan sát cùng tổng và tạo cùng ID; ngay cả khi `sum()` có một snapshot lý tưởng, phép **đọc rồi tăng** là hai bước tách rời, nên vẫn xảy ra race. Dùng `AtomicLong.incrementAndGet()` hoặc bộ cấp ID chuyên dụng khi cần một thao tác nguyên tử cấp số kế tiếp.

### B. Không dùng để kiểm soát hạn mức cứng

~~~java
if (adder.sum() < capacity) {
    adder.increment();
    // Không bảo đảm tổng cuối không vượt capacity.
}
~~~

Có hai vấn đề: `sum()` không là snapshot nguyên tử của `LongAdder` và tổ hợp **kiểm tra điều kiện rồi tăng** cũng không được thực hiện như một giao dịch nguyên tử. Nhiều thread có thể đồng thời thấy chỗ trống và cùng tăng.

Với hạn mức dạng một số nguyên duy nhất, dùng một trạng thái `AtomicLong` với vòng CAS, hoặc cơ chế đồng bộ dành riêng cho việc phân bổ tài nguyên:

~~~java
import java.util.concurrent.atomic.AtomicLong;

static boolean reserveOne(AtomicLong used, long capacity) {
    while (true) {
        long current = used.get();
        if (current >= capacity) {
            return false;
        }
        if (used.compareAndSet(current, current + 1)) {
            return true;
        }
    }
}
~~~

Đoạn phương thức ở trên cần đặt trong một lớp Java. Giả định `capacity` là một số không âm hợp lệ và không yêu cầu vượt miền `long`. Nếu CAS thất bại, thread khác đã thay đổi giá trị, nên thử lại từ trạng thái mới. Đây là thao tác **kiểm tra + tăng được tuyến tính hóa trên cùng một biến**, phù hợp hơn `if (sum < capacity) increment`.

### C. Không dùng để đóng sổ tiền hoặc số liệu kiểm toán

Một phép đọc `sum()` khi giao dịch đang chạy không tự bảo đảm toàn bộ nghiệp vụ đã cam kết được tính đúng ở ranh giới chốt. Cần mô hình giao dịch, ledger, nguồn sự kiện, đồng bộ hoặc checkpoint đúng semantics. `LongAdder` chỉ là bộ tích lũy số `long`, không thay thế tính nhất quán nghiệp vụ.

Nếu xử lý giá trị tiền có phần lẻ, càng không nên dùng `DoubleAdder` như cơ chế ghi sổ: kiểu `double` còn có sai số dấu phẩy động và thay đổi kết quả theo thứ tự cộng. Có thể biểu diễn số đơn vị nhỏ nhất dưới dạng `long` khi miền giá trị đủ, hoặc dùng kiểu số thập phân/chế độ lưu trữ phù hợp với hợp đồng hệ thống.

## 9. Muốn tổng cuối chính xác thì làm thế nào?

**Nguyên tắc:** đọc sau khi biết tất cả writer đã kết thúc và không ai còn cập nhật adder đó nữa. Một cách là đợi bằng `Thread.join()` như chương trình ở mục 4. Với tác vụ đưa vào `ExecutorService`, có thể đợi các `Future.get()` hoặc cơ chế completion thích hợp trước khi đọc tổng. Nếu còn writer ngoài nhóm đã đợi, kết quả vẫn là phép quan sát đồng thời.

Điểm quan trọng không nằm ở việc tự chọn một khoảng `Thread.sleep(...)` đủ dài. Ngủ 100 ms hoặc 1 giây **không chứng minh** writer đã xong và cũng không tạo ra snapshot nguyên tử. Cần tín hiệu hoàn thành có ràng buộc rõ ràng.

Một hệ thống luôn tiếp nhận sự kiện có thể không có "thời điểm tất cả writer dừng". Khi cần tổng chính xác cho mốc thời gian `T`, thiết kế phải xác định ranh giới sự kiện và có cơ chế phối hợp để tất cả cập nhật thuộc mốc đó được hoàn tất trước khi kết sổ. Có thể dùng cơ chế khóa/epoch/checkpoint thích hợp hoặc tổng chính xác từ nguồn dữ liệu bền vững. Đổi adder tham chiếu rồi gọi `sum()` trên instance cũ **chưa đủ** nếu những writer vẫn giữ tham chiếu cũ và tiếp tục cập nhật sau khi đổi.

**Đừng nhầm** việc `sum()` trả chính xác khi hệ thống yên lặng với việc `sum()` tự tạo ra sự yên lặng. Reader không chặn writer và không áp đặt một ranh giới cắt dữ liệu.

## 10. reset() và sumThenReset(): rủi ro khi dùng sai

`LongAdder.reset()` xóa giá trị tích lũy. `sumThenReset()` kết hợp đọc và reset về mặt hiệu ứng, nhưng tài liệu API nêu rõ các phương thức này **chỉ hiệu quả chính xác khi không có cập nhật đồng thời**.

Trong trường hợp writer vẫn đang thêm số:
- Một cập nhật có thể rơi vào thời điểm reader đã đọc một phần trạng thái nhưng chưa reset phần đó.
- Số đọc ra và tổng còn lại sau reset có thể không phân chia các cập nhật thành hai tập chính xác theo cùng một ranh giới nguyên tử.
- Một lần `sumThenReset()` không đảm bảo bao trọn mọi cập nhật hoàn tất trước một mốc thời gian nghiệp vụ do bạn tự đặt.

Đoạn sau **an toàn theo giả định không có writer khác**:

~~~java
LongAdder window = new LongAdder();
window.add(8);
window.add(2);

long completedWindow = window.sumThenReset(); // 10
long nextWindow = window.sum();               // 0
~~~

Đoạn này cần `import java.util.concurrent.atomic.LongAdder;` và nằm trong một phương thức Java. Nếu có writer chạy đồng thời, không thể dùng kết quả 10/0 như hợp đồng tổng quát.

Nếu cần cửa sổ metric với độ chính xác ở ranh giới, cần thiết kế một quy trình đóng cửa sổ: ngăn/chuyển tiếp writer theo một giao thức có xác nhận hoàn tất, sau đó đọc tổng phiên cũ. Các phương thức của `LongAdder` không tự cung cấp giao thức này.

## 11. DoubleAdder có cùng giới hạn snapshot và thêm giới hạn số học

`DoubleAdder` hoạt động tương tự nhưng cộng `double`. `DoubleAdder.sum()` cũng **không phải snapshot nguyên tử** khi có cập nhật đồng thời. Ngoài ra, thứ tự các phép cộng trong/giữa thread không được bảo đảm, và `double` không có tính kết hợp tuyệt đối về mặt số học máy tính:

~~~text
(a + b) + c  có thể khác  a + (b + c)
trong phép tính dấu phẩy động vì làm tròn.
~~~

Vì vậy, ngay cả sau khi mọi writer kết thúc, `DoubleAdder.sum()` có thể khác từng bit so với kết quả cộng tuần tự cùng các giá trị theo một thứ tự cố định. Đây là khác biệt **về tính ổn định số học**, tách biệt với vấn đề snapshot đồng thời. Nếu số lượng/biên độ giá trị quá khác nhau hoặc yêu cầu độ chính xác cao, phải chọn thiết kế tính tổng phù hợp.

Ví dụ:

~~~java
import java.util.concurrent.atomic.DoubleAdder;

DoubleAdder total = new DoubleAdder();
total.add(0.1);
total.add(0.2);

double result = total.sum();
System.out.println(result); // 0.30000000000000004 (với IEEE 754 double)
~~~

Đoạn này chỉ minh họa phép cộng số `double` thông thường trong cùng một thread. Không dùng `DoubleAdder` để kỳ vọng số tiền thập phân chính xác tuyệt đối. Với hệ thống cần tính tổng double ổn định hoặc có ràng buộc sai số, xem xét thuật toán cộng bù/sắp xếp dữ liệu và cách phối hợp các luồng, không giả định một bộ tích lũy concurrent tự giải quyết vấn đề.

## 12. Những ngộ nhận và lỗi phổ biến

1. **"LongAdder thread-safe thì sum() phải nguyên tử."** Cập nhật từng phần và đọc đồng thời nhiều phần là hai hợp đồng khác nhau.
2. **"Nếu thử nhiều lần sum() luôn đúng, API bảo đảm đúng."** Lịch chạy có thể không lộ khác biệt trong test; hợp đồng JavaDoc mới quyết định điều gì được bảo đảm.
3. **"volatile bao quanh adder sẽ làm sum nguyên tử."** `volatile` trên tham chiếu không khóa đồng thời quá trình đọc tất cả thành phần bên trong.
4. **"synchronized (adder) { return adder.sum(); } là đủ."** Khóa chỉ bảo vệ thao tác nếu **mọi writer** tuân thủ cùng khóa hoặc một cơ chế phối hợp tương đương. `increment()` mặc định không tự lấy monitor của đối tượng adder.
5. **"sumThenReset() giống AtomicLong.getAndSet(0)."** Khi cập nhật đồng thời, `sumThenReset()` không có ranh giới nguyên tử như `getAndSet` trên một `AtomicLong`.
6. **"Lấy tổng rồi tăng để cấp số thứ tự là an toàn."** Đây là read-modify-write không nguyên tử, bất kể cách cài bộ đếm.
7. **"AtomicLong giải quyết luôn snapshot nhiều chỉ số."** Nó chỉ bảo đảm thao tác trên một giá trị riêng lẻ; nhiều biến vẫn cần một giao thức đồng bộ chung nếu yêu cầu trạng thái nhất quán.
8. **"Có thể dừng writer bằng sleep."** `sleep()` không đợi hoàn thành một cách có ràng buộc; dùng `join()`, `Future.get()`, latch hoặc barrier theo cấu trúc công việc.
9. **"Một LongAdder dùng sumThenReset trong metric theo phút là luôn chính xác từng phút."** Không có bảo đảm ranh giới chính xác nếu các sự kiện vẫn được cập nhật trong lúc reset.
10. **"LongAdder không bao giờ tràn."** Nó cộng theo `long`; tổng vượt miền `long` vẫn có thể overflow/wrap như phép toán số nguyên Java. Chọn miền dữ liệu và cơ chế phát hiện/giới hạn phù hợp khi độ lớn có thể vượt ngưỡng.
11. **"DoubleAdder là phép cộng thập phân chính xác."** Nó dùng `double` và thứ tự cộng không cố định giữa thread; cần tính sai số nếu ứng dụng nhạy cảm với độ chính xác.
12. **"Nhiều LongAdder đọc từng cái rồi ghép sẽ thành ảnh chụp toàn hệ thống."** Các giá trị được đọc ở thời điểm khác nhau; nếu cần invariant liên quan nhiều thống kê, phải phối hợp thêm.

## 13. Chọn kiểu nào cho yêu cầu cụ thể?

| Nhu cầu | Lựa chọn phù hợp | Giải thích |
|---|---|---|
| Đếm số lần truy cập, log event, metric dưới contention cao | `LongAdder` | Cập nhật hiệu quả; chấp nhận `sum()` là quan sát không atomic snapshot |
| Số thứ tự tăng nguyên tử, quota một biến, CAS theo trạng thái hiện tại | `AtomicLong` | Có `get()` và read-modify-write atomic |
| Thống kê nhiều khóa với update liên tục | `ConcurrentHashMap<K, LongAdder>` | Bộ đếm độc lập theo khóa, nhưng ảnh chụp toàn map không tự nguyên tử |
| Tổng số chính xác sau khi toàn bộ tác vụ kết thúc | `LongAdder` + đồng bộ hoàn thành | `sum()` chính xác khi không còn cập nhật, trong miền số hợp lệ |
| Tổng chính xác tại một mốc thời gian trong hệ thống luôn chạy | Giao thức đóng mốc/checkpoint có đồng bộ | `sum()`/`sumThenReset()` đơn lẻ không xác định ranh giới |
| Tổng `double` thống kê chấp nhận sai số | `DoubleAdder` | Chú ý rounding và thứ tự cộng |
| Ghi sổ tiền/thông tin phải kiểm toán | Dữ liệu giao dịch và kiểu số đúng hợp đồng | Một bộ đếm in-memory không thay thế tính nhất quán và độ bền |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai thread liên tục gọi `LongAdder.increment()`. Một thread khác gọi `sum()` trong lúc đó. Có thể coi giá trị là toàn bộ cập nhật đã diễn ra đúng lúc gọi hàm không?

**Đáp án:** Không. `sum()` có thể không bao gồm các cập nhật diễn ra trong khoảng tính tổng; JavaDoc không bảo đảm atomic snapshot trong tình huống này.

**Câu 2.** Sau khi cả hai worker đã `join()` và không thread nào khác cập nhật, mỗi worker đã thực hiện 1.000 lần `increment()`, `sum()` phải bằng bao nhiêu?

**Đáp án:** 2.000, giả sử ban đầu bằng 0, không reset/giảm/tràn số và worker đã hoàn tất thật. Lúc đọc không còn cập nhật đồng thời.

**Câu 3.** `if (adder.sum() < 10) adder.increment();` có giữ tổng không quá 10 dưới nhiều thread không?

**Đáp án:** Không. Đọc tổng và tăng không tạo một hành động kiểm tra-và-cập nhật nguyên tử. Dùng `AtomicLong.compareAndSet` trong vòng lặp hoặc đồng bộ/thuật toán quota phù hợp.

**Câu 4.** `sumThenReset()` có thể dùng để chốt chính xác cửa sổ 1 phút khi writer vẫn cập nhật vào cùng instance không?

**Đáp án:** Không có bảo đảm đó. Cần cơ chế xác định khi nào writer của cửa sổ cũ đã hoàn tất trước khi đọc/reset hoặc thay thiết kế thu thập số liệu.

**Câu 5.** Nếu đổi `LongAdder` sang `AtomicLong`, một lần gọi `get()` có đủ để lấy snapshot nhất quán của cả năm bộ đếm khác nhau không?

**Đáp án:** Không. Một `AtomicLong.get()` đọc nguyên tử **một** giá trị, không tạo giao dịch nguyên tử cho năm biến.

**Câu 6.** Sau khi dừng toàn bộ writer của `DoubleAdder`, `sum()` có chắc bằng kết quả cộng tuần tự trong một thứ tự cố định tới từng bit không?

**Đáp án:** Không. Không còn contention giúp lấy tổng các thành phần ổn định, nhưng dấu phẩy động có thể làm tròn khác nhau khi đổi thứ tự cộng.

## 15. Ghi nhớ và nguồn chuẩn

- **`LongAdder.add()/increment()`:** phục vụ cập nhật đồng thời an toàn, tối ưu cho thống kê dưới contention.
- **`LongAdder.sum()`:** đọc tổng để quan sát; **không phải atomic snapshot khi các writer còn chạy**.
- **Sau khi đồng bộ hoàn tất mọi writer:** `sum()` trả tổng đúng của các cập nhật đã hoàn tất, trong giới hạn số học và nếu không reset.
- **`sumThenReset()`/`reset()`:** chỉ dùng với ranh giới quiescent hoặc giao thức đồng bộ loại trừ cập nhật đồng thời.
- **`AtomicLong.get()/incrementAndGet()/compareAndSet()/getAndSet()`:** phù hợp cho trạng thái `long` đơn có yêu cầu nguyên tử hoặc read-modify-write.
- **`DoubleAdder.sum()`:** cùng giới hạn snapshot và thêm lưu ý về `double` không kết hợp tuyệt đối.

Tài liệu API chính thức để đối chiếu:
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): `sum`, `reset`, `sumThenReset` và mục đích sử dụng trong thống kê đồng thời.
- [`DoubleAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html): snapshot đồng thời và thứ tự cộng `double`.
- [`AtomicLong` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): các thao tác atomic trên một giá trị `long`.
- [`Thread.join` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): đợi một thread kết thúc; các quy tắc happens-before liên quan nằm trong tài liệu `java.util.concurrent` và Java Memory Model.
