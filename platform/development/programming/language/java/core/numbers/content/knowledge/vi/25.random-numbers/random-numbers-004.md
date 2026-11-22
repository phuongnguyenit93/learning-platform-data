# `ThreadLocalRandom` khi nhiều luồng cùng sinh số ngẫu nhiên

## 1. Bài toán: nhiều tác vụ, nhiều lần sinh số

Một ứng dụng Java có thể đồng thời thực hiện nhiều phép mô phỏng, chọn thời gian chờ ngẫu nhiên (jitter), chia công việc vào các nhóm hoặc sinh dữ liệu thử nghiệm. Nếu mỗi tác vụ liên tục cần giá trị ngẫu nhiên, cách tổ chức bộ sinh có thể ảnh hưởng tới thông lượng và mức tranh chấp giữa các luồng.

Ví dụ một thread pool có bốn luồng, mỗi luồng mô phỏng 10.000 lần tung xúc xắc. Những câu hỏi cần trả lời:

- Làm thế nào để mỗi luồng lấy số từ `1` đến `6` mà không phải cùng cập nhật trạng thái của một đối tượng `Random` dùng chung?
- Làm thế nào để bảo đảm ranh giới khoảng số đúng, tránh truy cập chung một mảng đếm không được đồng bộ?
- Kết quả nào có thể kiểm thử một cách ổn định khi giá trị ngẫu nhiên thay đổi theo từng lần chạy?
- Khi nào không nên dùng `ThreadLocalRandom`, chẳng hạn khi cần seed tái lập chính xác hoặc giá trị bảo mật?

Lớp `java.util.concurrent.ThreadLocalRandom` xuất hiện từ Java 7 và vẫn thích hợp với Java 17+. Đây là **bộ sinh số giả ngẫu nhiên gắn với luồng đang thực thi**, hữu ích khi nhiều luồng cần sinh số thường xuyên.

## 2. `ThreadLocalRandom` hoạt động theo luồng như thế nào?

Sử dụng phổ biến:

```java
import java.util.concurrent.ThreadLocalRandom;

int number = ThreadLocalRandom.current().nextInt(1, 7);
// number thuộc {1, 2, 3, 4, 5, 6}.
```

`current()` trả đối tượng `ThreadLocalRandom` dành cho **luồng đang gọi**. Thông thường, mỗi worker tự gọi `current()` bên trong tác vụ đang chạy. Theo tài liệu API, các phương thức của đối tượng này **chỉ nên được gọi bởi chính luồng đã lấy nó**, không truyền đối tượng đó sang luồng khác.

```java
Runnable task = () -> {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    int sample = rng.nextInt(100); // 0 <= sample < 100
    // Xử lý sample ngay trong worker.
};
```

Mã trên minh họa cách viết một `Runnable`; để thực thi cần gửi `task` vào một `Thread` hoặc `ExecutorService`. Có thể gọi `ThreadLocalRandom.current()` mỗi lần cần số, hoặc giữ biến `rng` *cục bộ trong phạm vi worker* để gọi nhiều lần trong cùng tác vụ.

### Vì sao thường thuận lợi hơn một `Random` dùng chung?

Một đối tượng `java.util.Random` có thể được nhiều luồng sử dụng, nhưng nhiều lời gọi cập nhật trạng thái của **cùng một bộ sinh**, từ đó có thể gây tranh chấp và tăng chi phí khi tải song song cao. `ThreadLocalRandom` tránh việc các luồng cùng cập nhật một bộ sinh `Random` chia sẻ như vậy; điều này thường giảm overhead và contention trong các tác vụ sinh số liên tục.

Đây là lợi ích về **tổ chức trạng thái và hiệu năng tiềm năng**, không phải lời hứa rằng mọi chương trình dùng `ThreadLocalRandom` đều nhanh hơn. Nếu tác vụ chủ yếu làm I/O, phải chờ khóa khác hoặc xử lý rất ít số, sự khác biệt có thể không đáng kể. Đo lường trên tải thực bằng benchmark phù hợp trước khi quyết định tối ưu.

`ThreadLocalRandom` không tự tạo nhiều luồng và cũng không thay thế `ExecutorService`: luồng/tác vụ vẫn phải được tổ chức bởi ứng dụng.

## 3. Những API cần biết và ý nghĩa khoảng

Các phương thức trả về giá trị **giả ngẫu nhiên**, không bảo đảm các giá trị khác nhau giữa các lần gọi.

| Lời gọi | Khoảng hoặc kết quả |
| --- | --- |
| `nextInt()` | Giá trị `int` trong toàn miền kiểu nguyên |
| `nextInt(10)` | Số nguyên từ `0` đến `9` |
| `nextInt(1, 7)` | Số nguyên từ `1` đến `6` |
| `nextLong(100L)` | Số `long` từ `0` đến `99` |
| `nextLong(10L, 20L)` | Số `long` từ `10` đến `19` |
| `nextDouble()` | `double` từ `0.0` (gồm) đến `1.0` (không gồm) |
| `nextDouble(1.5, 2.5)` | `double` trong khoảng `[1.5, 2.5)` |
| `nextBoolean()` | Giá trị `boolean` giả ngẫu nhiên |

Với các overload có `origin` và `bound`:

- Cận dưới **bao gồm** (`origin`).
- Cận trên **không bao gồm** (`bound`).
- Với `nextInt(origin, bound)` và `nextLong(origin, bound)`, phải có `origin < bound`; vi phạm sẽ ném `IllegalArgumentException`.
- Với `nextInt(bound)` hoặc `nextLong(bound)`, `bound` phải dương.
- Với `nextDouble(origin, bound)`, các cận phải hữu hạn và `origin < bound`; không dùng `NaN` hoặc vô cực làm cận.

Ví dụ muốn chọn chỉ số của một danh sách có `size` phần tử:

```java
int size = items.size();
if (size == 0) {
    throw new IllegalArgumentException("Danh sách không được rỗng");
}
int index = ThreadLocalRandom.current().nextInt(size);
// index thuộc [0, size): có thể dùng items.get(index).
```

Đây là **đoạn mã nhúng** với biến `items` là một `List` đã tồn tại. Nếu danh sách có thể bị sửa đồng thời, ứng dụng vẫn phải xử lý tính an toàn luồng của danh sách; `ThreadLocalRandom` không giải quyết việc đó.

### Tránh dùng phép chia dư để giới hạn ngẫu nhiên

```java
// Không nên dùng để sinh chỉ số [0, 9]:
int bad = ThreadLocalRandom.current().nextInt() % 10;

// Tránh cả Math.abs(nextInt()) % 10:
// Math.abs(Integer.MIN_VALUE) vẫn âm.
int good = ThreadLocalRandom.current().nextInt(10);
```

Giá trị của `bad` có thể âm. Phép `%` thủ công cũng có thể tạo độ lệch phân bố khi chia một miền kết quả không chia đều cho số lượng nhóm; dùng overload nhận `bound`/`origin, bound` để thư viện xử lý miền phù hợp.

`nextInt(1, 7)` thích hợp để mô phỏng một lần tung xúc xắc sáu mặt; đừng viết `nextInt(1, 6)` nếu muốn số `6` xuất hiện.

## 4. Quy tắc sở hữu trong ứng dụng đa luồng

### 4.1. Lấy `current()` bên trong worker

**Nên làm:**

```java
executor.submit(() -> {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    for (int i = 0; i < 1_000; i++) {
        int value = rng.nextInt(100);
        // Xử lý value bằng dữ liệu cục bộ của task.
    }
});
```

Đây là ví dụ *nhúng*; `executor` là một `ExecutorService` được tạo ở nơi gọi.

**Không nên giữ một instance và truyền qua các luồng:**

```java
// Sai ý định sử dụng API khi nhiều thread cùng gọi trên đối tượng này:
static final ThreadLocalRandom SHARED = ThreadLocalRandom.current();
```

`SHARED` được lấy trong luồng khởi tạo lớp; đem tham chiếu đó đi gọi từ các worker khác vi phạm hướng dẫn sở hữu theo luồng. Cũng tránh lấy `ThreadLocalRandom.current()` ở luồng chính rồi truyền biến `rng` vào mọi tác vụ qua lambda.

Đừng đồng bộ hóa thêm một `ThreadLocalRandom` dùng chung để “sửa” cách dùng sai. Cách đúng là **lấy giá trị từ `current()` trong chính luồng thực thi**.

### 4.2. Vòng đời theo worker thread, không theo task

`ExecutorService` thường tái sử dụng các luồng. Nếu 100 tác vụ chạy trên pool có 4 worker, nhiều tác vụ sẽ chạy nối tiếp trên cùng một worker, và mỗi tác vụ gọi `ThreadLocalRandom.current()` sẽ dùng bộ sinh của luồng đó. Vì vậy:

- Không khẳng định mỗi task có một seed độc lập hoặc một chuỗi ngẫu nhiên cố định.
- Không suy ra số bộ sinh từ số task.
- Lịch chạy task có thể thay đổi giữa các lần chạy.
- Không cần tự gọi `new ThreadLocalRandom()`; cách sử dụng thông thường là qua `current()`.

Nếu yêu cầu chính là **mỗi task có chuỗi giả ngẫu nhiên tái lập**, hãy thiết kế RNG và seed theo **định danh task** (xem mục 8); cơ chế thread-local không tương đương task-local.

### 4.3. RNG không làm dữ liệu chia sẻ trở nên an toàn

Ví dụ nhiều worker cùng cập nhật:

```java
long[] counts = new long[6];
executor.submit(() -> {
    int face = ThreadLocalRandom.current().nextInt(1, 7);
    counts[face - 1]++; // Có race nếu worker khác cũng cập nhật counts.
});
```

Phép tăng `counts[i]++` không phải thao tác nguyên tử. Nhiều luồng có thể mất lượt tăng dù chúng lấy số từ các bộ sinh độc lập. Có ba hướng xử lý thường gặp: mỗi task ghi vào bộ đếm **cục bộ rồi gộp khi hoàn tất**; hoặc dùng `AtomicLongArray` / `LongAdder` đúng vị trí nếu cần chia sẻ; hoặc đồng bộ hóa phù hợp. Ví dụ đầy đủ ở mục tiếp theo chọn cách đếm cục bộ.

Đừng nhầm **thread-safe RNG usage** với **thread-safe business data**.

## 5. Chương trình Java 17+ hoàn chỉnh: mô phỏng 40.000 lần tung xúc xắc

Tạo file **`ThreadLocalRandomDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;

public class ThreadLocalRandomDemo {
    // Một worker sở hữu mảng counts, rồi chuyển kết quả về luồng tổng hợp.
    record Result(long[] counts, long outOfRange) {}

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        int workers = 4;
        int drawsPerWorker = 10_000;
        ExecutorService executor = Executors.newFixedThreadPool(workers);

        try {
            List<Future<Result>> futures = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    // Phải lấy RNG ngay trong luồng chạy tác vụ.
                    ThreadLocalRandom rng = ThreadLocalRandom.current();
                    long[] counts = new long[6];
                    long outOfRange = 0;

                    for (int j = 0; j < drawsPerWorker; j++) {
                        int face = rng.nextInt(1, 7);
                        if (face >= 1 && face <= 6) {
                            counts[face - 1]++;
                        } else {
                            outOfRange++;
                        }
                    }
                    return new Result(counts, outOfRange);
                }));
            }

            // Main chỉ gộp sau khi nhận kết quả từng Future.
            long[] totals = new long[6];
            long invalid = 0;
            for (Future<Result> future : futures) {
                Result result = future.get();
                invalid += result.outOfRange();
                for (int i = 0; i < totals.length; i++) {
                    totals[i] += result.counts()[i];
                }
            }

            long counted = Arrays.stream(totals).sum() + invalid;
            System.out.println("workers=" + workers);
            System.out.println("draws=" + counted);
            System.out.println("outOfRange=" + invalid);
            System.out.println("buckets=" + totals.length);
            System.out.println("countMatches="
                    + (counted == (long) workers * drawsPerWorker));

        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadLocalRandomDemo.java
java ThreadLocalRandomDemo
```

**Stdout có thể kiểm chứng chính xác** (với giả định các tác vụ hoàn tất bình thường và API tuân thủ hợp đồng):

```text
workers=4
draws=40000
outOfRange=0
buckets=6
countMatches=true
```

Kết quả cụ thể của từng mặt xúc xắc sẽ thay đổi giữa các lần chạy nên ví dụ cố ý chỉ in các **bất biến**: số lượt sinh, tính hợp lệ của miền và số nhóm.

Cơ chế từng bước:

1. `newFixedThreadPool(4)` tạo executor với tối đa bốn worker để xử lý tác vụ. Bốn `Callable<Result>` được gửi vào executor.
2. Mỗi callable gọi `ThreadLocalRandom.current()` **khi đang chạy trong worker**, sau đó sinh 10.000 lần `nextInt(1, 7)`.
3. Mỗi tác vụ sử dụng mảng đếm riêng, không có phép tăng chia sẻ giữa các worker.
4. `Future.get()` chờ task hoàn tất hoặc báo lỗi; việc thu kết quả theo thứ tự submit **không buộc các tác vụ chạy theo thứ tự**.
5. Main gộp dữ liệu đã hoàn tất để tính tổng, rồi đóng executor bằng `shutdown()` trong `finally`.

`ExecutorService` ở Java 17 chưa nên được giả định là dùng được với `try-with-resources` trong tất cả môi trường biên dịch mục tiêu. Mẫu trên dùng `try/finally` rõ ràng; trong ứng dụng cần chính sách hủy/chờ kết thúc theo đặc thù hệ thống.

Nếu mỗi lần chạy in số lần xuất hiện của mặt 1..6 thì các con số sẽ không giống nhau hoàn toàn, và điều đó **không phải lỗi**. Một RNG tốt cũng không bảo đảm các nhóm bằng nhau chính xác trong một mẫu hữu hạn.

## 6. Hiệu năng: lợi ích và giới hạn thực tế

Trong chương trình nhiều luồng cùng sinh số với tần suất cao, dùng `ThreadLocalRandom` thường giảm tranh chấp so với việc chia sẻ một `Random` duy nhất. Tuy nhiên một phép đo đúng còn phụ thuộc vào:

- **Khối lượng công việc:** sinh vài số cho mỗi request thường có chi phí thấp hơn mạng, DB, log và các phép đồng bộ khác.
- **Cách ghi kết quả:** nếu mọi thread vẫn ghi vào một biến/cấu trúc có khóa chung thì contention có thể chỉ chuyển vị trí, không biến mất.
- **Số thread và kích thước pool:** thêm thread vượt khả năng xử lý CPU có thể làm tăng context switching; một pool hợp lý tùy tải, không mặc định càng lớn càng nhanh.
- **Warmup JVM/JIT, GC, phân phối lịch chạy:** benchmark một lần bằng `System.nanoTime()` khó chứng minh sự chênh lệch có ý nghĩa.
- **Yêu cầu kết quả:** nếu cần xác định đầu ra theo seed hoặc bảo mật, ưu tiên tiêu chuẩn đúng của bài toán trước việc giảm overhead.

Khi benchmark các bộ sinh, dùng JMH hoặc phương pháp đo nghiêm túc: chạy warmup, đo nhiều mẫu, dùng đủ thread, bảo đảm kết quả không bị compiler bỏ qua và xem cả throughput lẫn latency. Không tuyên bố một hệ số tăng tốc cố định cho mọi JDK/phần cứng.

### Điều gì xảy ra với `parallelStream()`?

Dùng RNG theo luồng xử lý *thực tế* của phần tử:

```java
long count = java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .filter(i -> ThreadLocalRandom.current().nextInt(10) == 0)
        .count();
```

Đoạn này có số lần “trúng” biến thiên; chỉ có giới hạn `0 <= count <= 10_000` là bất biến. Trên pool và khi phân hoạch workload thay đổi, kết quả cũng thay đổi. Không giữ một `ThreadLocalRandom.current()` lấy ở main rồi bắt tất cả nhánh của parallel stream sử dụng lại tham chiếu đó.

Không giả định một stream song song luôn mở riêng một thread cho mỗi phần tử. Việc song song hóa, độ lớn lô xử lý và thread pool do runtime quyết định.

## 7. Những ngoại lệ và sai lầm phổ biến

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `nextInt(0)` hoặc `nextInt(-1)` | `bound` không dương | Kiểm tra bound và trường hợp tập đầu vào rỗng |
| `nextInt(10, 10)` | `origin >= bound` | Dùng cận trên lớn hơn cận dưới |
| Chọn xúc xắc bằng `nextInt(1, 6)` | Bound trên là *exclusive* | Dùng `nextInt(1, 7)` |
| Dùng `Math.abs(nextInt()) % bound` | `MIN_VALUE` vẫn âm; `%` có thể gây lệch | Dùng `nextInt(bound)` |
| Lưu RNG vào biến `static final` để mọi worker dùng | Lấy instance trong một luồng rồi gọi ở luồng khác | Gọi `current()` ngay trong worker |
| Gọi `setSeed(...)` | `ThreadLocalRandom.setSeed(long)` luôn ném `UnsupportedOperationException` | Dùng RNG có seed công khai nếu cần tái lập |
| Tin `ThreadLocalRandom` bảo mật | Đây là PRNG không dùng cho mục đích mã hóa | Dùng `SecureRandom` cho token, khóa, mã xác minh |
| Dùng RNG riêng nhưng ghi `counts[i]++` lên mảng chung | Race condition trên dữ liệu dùng chung | Dùng bộ đếm cục bộ hoặc cấu trúc đồng bộ |
| Test chờ dãy số cố định / mọi bucket bằng nhau | Kết quả phụ thuộc seed, thread và ngẫu nhiên | Test miền giá trị, số lần, các bất biến, hoặc dùng RNG seeded |
| Mong một task có luồng/seed cố định trong thread pool | Executor tái sử dụng worker và có thể thay đổi lịch chạy | Ánh xạ RNG/seed theo task nếu cần tái lập |

Một lỗi nữa là dùng ngẫu nhiên để sinh **ID bắt buộc duy nhất**. PRNG có thể sinh cùng số nhiều lần. Nếu yêu cầu ID duy nhất, dùng chính sách đảm bảo duy nhất phù hợp (chẳng hạn cấp phát ID, UUID với hiểu biết về xác suất va chạm, hoặc ràng buộc duy nhất của kho dữ liệu); `ThreadLocalRandom` không bảo đảm uniqueness.

## 8. Khi cần tái lập kết quả hoặc bảo mật

### 8.1. Test xác định bằng seed

`ThreadLocalRandom` được khởi tạo với seed do runtime quản lý; API `setSeed(long)` không hỗ trợ. Vì vậy nó không phù hợp khi muốn cùng một phép thử luôn sinh lại đúng dãy số qua các lần chạy.

Trong Java 17 có thể dùng `SplittableRandom` để tạo các bộ sinh riêng cho mỗi tác vụ từ một seed gốc. Mỗi instance **không được chia sẻ giữa các luồng**; chia chúng trước khi gửi task:

```java
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(2026L);
SplittableRandom firstTaskRng = root.split();
SplittableRandom secondTaskRng = root.split();

// Giao firstTaskRng và secondTaskRng cho hai task riêng,
// mỗi instance chỉ được dùng trong một task.
```

Đây là mã minh họa cách chia bộ sinh, không phải toàn bộ chương trình chạy. Khi mỗi task nhận bộ sinh riêng, thực hiện cùng thứ tự lời gọi với cùng thuật toán/seed, kết quả của task có thể tái lập thuận tiện hơn, độc lập với việc task được xếp lên worker thread nào. Cần kiểm soát thứ tự cấp phát RNG, số lần rút và phiên bản/thuật toán nếu hợp đồng cần tính tái lập xuyên môi trường. Không dùng chung `SplittableRandom` giữa hai worker mà không thiết kế đồng bộ thích hợp.

`java.util.random.RandomGenerator` (Java 17) còn định nghĩa abstraction cho nhiều thuật toán RNG; chọn implementation theo yêu cầu hiệu năng, phân phối và khả năng tái lập, thay vì mặc định mọi bộ sinh giống nhau.

Đối với unit test có đầu ra cố định, lựa chọn khác là inject một `RandomGenerator` hoặc một interface tạo số vào thành phần đang kiểm thử, rồi dùng một fake/deterministic generator trong test.

### 8.2. Giá trị nhạy cảm về bảo mật

`ThreadLocalRandom` **không cryptographically secure**. Không dùng nó để sinh mật khẩu tạm, mã OTP, session token, API secret, nonce phải không dự đoán được hoặc khóa bảo mật. Những trường hợp này dùng `java.security.SecureRandom` và thiết kế quy trình an toàn phù hợp. Việc nhiều luồng cần tạo token không biến `ThreadLocalRandom` thành lựa chọn bảo mật; kiến trúc chia sẻ/tạo instance `SecureRandom` phải được đánh giá riêng theo yêu cầu thông lượng và provider.

## 9. Thiết kế kiểm thử cho tính đúng đắn trong đa luồng

**Thử nghiệm bảo đảm (deterministic assertions):**

- Với `rng.nextInt(1, 7)`, kiểm tra từng kết quả nằm từ 1 đến 6.
- Với `workers × drawsPerWorker`, tổng số mẫu đếm được phải bằng số lượt yêu cầu (nếu không có lỗi task).
- Số mẫu không hợp lệ phải bằng 0.
- Kết quả từ các worker chỉ được gộp sau khi hoàn tất, hoặc dùng cơ chế đồng bộ đúng.
- Nếu task ném ngoại lệ, `Future.get()` cho biết thất bại thay vì báo thành công.

**Không nên kiểm thử:**

- “Mặt số 6 nhất định sẽ xuất hiện trong 100 lần.”
- “Tổng các mặt chẵn bằng tổng các mặt lẻ.”
- “Hai lần chạy phải cho cùng dãy số.”
- “Mỗi thread luôn sinh giá trị khác thread khác.”

Các khẳng định này không được API bảo đảm. Nếu cần kiểm tra thống kê phân bố, dùng số lượng mẫu và phương pháp phân tích thống kê phù hợp, chấp nhận xác suất thất bại được lượng hóa. Kiểm tra thống kê không thay thế kiểm tra cận và race condition.

Có thể dùng công cụ kiểm tra concurrency để đánh giá cập nhật trạng thái chia sẻ, nhưng việc `nextInt` tạo kết quả trong miền hợp lệ chỉ chứng minh RNG; không chứng minh phần còn lại của workflow thread-safe.

## 10. Bài tập vận dụng

1. Mười task dùng thread pool bốn worker. Có nên lưu một `ThreadLocalRandom` ở main và truyền vào tất cả task không? Vì sao gọi `ThreadLocalRandom.current()` trong từng task đúng hơn?
2. Viết một hàm chọn ngẫu nhiên chỉ số của `List<String>`, từ chối danh sách rỗng. Xác định cận dưới và cận trên chính xác.
3. Thay chương trình xúc xắc bằng mô phỏng tung đồng xu 100.000 lần trên nhiều worker; giữ bộ đếm cục bộ và chỉ in `total == 100000`, `invalid == 0`.
4. Nếu product manager yêu cầu test mô phỏng chạy lặp lại đúng kết quả trên cùng seed, có phù hợp dùng `ThreadLocalRandom` không? Đề xuất thiết kế dùng RNG theo task và seed rõ ràng.
5. Một hệ thống sinh mã xác thực đăng nhập đang dùng `nextInt(100000, 1000000)`. Vì sao miền giá trị đúng vẫn **chưa đủ** để phương pháp trở nên an toàn?

**Đáp án gợi ý:** (1) Không truyền instance lấy từ luồng khác; lấy `current()` tại worker. (2) `nextInt(list.size())` cho `[0, size)` sau khi kiểm tra `size > 0`. (3) Mỗi task trả bộ đếm riêng, main gộp bằng `Future.get()`. (4) Dùng `SplittableRandom`/bộ sinh có seed theo task và cố định thứ tự sử dụng. (5) `ThreadLocalRandom` không có tính chất bảo mật chống dự đoán, dù đầu ra là số sáu chữ số.

## 11. Tóm tắt quyết định kỹ thuật

Dùng `ThreadLocalRandom.current().nextX(...)` **ngay trong luồng đang làm việc** khi nhiều worker phải sinh số giả ngẫu nhiên thường xuyên và không cần dãy kết quả tái lập theo seed. Dùng đúng cận trên loại trừ và giữ dữ liệu tích lũy cục bộ hoặc đồng bộ đúng cách. Nếu phải tái lập dãy số theo task, chọn bộ sinh có seed và lifecycle rõ ràng; nếu đầu ra cần chống dự đoán, chuyển sang `SecureRandom`.

Tài liệu tham chiếu (Java SE 17): [ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html), [SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html), [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html).
