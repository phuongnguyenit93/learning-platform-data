# ThreadLocalRandom.current(): tránh tranh chấp, khả năng tái lập và giới hạn bảo mật

## 1. Bài toán trong chương trình đồng thời

Nhiều tác vụ Java chạy song song cần số giả ngẫu nhiên để phân bổ bucket, tạo dữ liệu mô phỏng, lấy mẫu hoặc chọn thời gian jitter khi retry. Một cách viết quen thuộc là tạo `java.util.Random` dùng chung rồi để các luồng cùng gọi `nextInt()`. Cách đó **đúng về an toàn luồng**, nhưng các lời gọi phải cập nhật cùng trạng thái sinh số. Trong đoạn mã chạy với số luồng lớn và gọi PRNG rất thường xuyên, sự phối hợp này có thể trở thành điểm tranh chấp.

`java.util.concurrent.ThreadLocalRandom` phục vụ tình huống nhiều luồng cần tạo số giả ngẫu nhiên mục đích chung:

~~~java
int bucket = java.util.concurrent.ThreadLocalRandom.current().nextInt(10);
~~~

Điểm cốt lõi của bài học gồm ba yêu cầu **khác nhau**:

- **Giảm contention:** tránh dùng chung trạng thái phát số giữa nhiều thread khi công việc gọi PRNG thường xuyên.
- **Tái lập:** nếu muốn lặp lại chính xác một phép mô phỏng hay ca kiểm thử, cần seed và cách gán generator ổn định cho từng task.
- **Bảo mật:** nếu giá trị phải khó đoán đối với kẻ tấn công, cần CSPRNG; `ThreadLocalRandom` không có cam kết bảo mật mật mã.

Bài tập trung vào **Java concurrency thuộc JDK**, không sử dụng framework.

## 2. Shared Random và trạng thái riêng theo luồng

### Tại sao `Random` dùng chung có thể tạo contention?

Đoạn minh họa (không phải chương trình chạy độc lập):

~~~java
import java.util.Random;

final class SharedRandomSource {
    static final Random RANDOM = new Random();

    static int bucket() {
        return RANDOM.nextInt(100);
    }
}
~~~

`Random` cho phép nhiều luồng dùng cùng đối tượng mà không phá vỡ trạng thái. Trên các triển khai JDK quen thuộc, việc cập nhật seed nội bộ của một `Random` chung dùng thao tác atomic/CAS; nhiều luồng cùng cập nhật có thể phải thử lại do cạnh tranh. **Thread-safe không đồng nghĩa không tranh chấp.** Tuy nhiên, nếu tần suất sinh số rất thấp hoặc phần lớn thời gian dành cho I/O, đây có thể không phải nút thắt đáng kể.

`ThreadLocalRandom.current()` dùng trạng thái PRNG gắn với **luồng hiện tại**, giúp tránh việc các luồng cùng đụng vào *một* trạng thái phát số. Mô hình tư duy:

~~~text
Một Random chung                     ThreadLocalRandom
Producer A ──┐                        Worker A ──> trạng thái RNG A
Producer B ──┼──> trạng thái RNG X    Worker B ──> trạng thái RNG B
Producer C ──┘                        Worker C ──> trạng thái RNG C
       có thể tranh chấp              không tranh chấp seed chung đó
~~~

Không có nghĩa mọi lần gọi tự lấy entropy mới từ hệ điều hành. Đây vẫn là **pseudorandom**: đầu ra được tính từ trạng thái nội bộ. Hai thread vẫn có thể sinh cùng một số; phát số không tự bảo đảm tính duy nhất của ID, không đồng bộ dữ liệu ứng dụng và không ngăn race condition ở nơi khác.

### Dùng `current()` ở đúng nơi

Viết `ThreadLocalRandom.current().nextInt(...)` tại **luồng đang cần số**. Trong một task chạy trên thread pool, gọi `current()` bên trong phần việc đó. Nếu gọi nhiều lần trên cùng luồng, giữ tham chiếu cục bộ `ThreadLocalRandom random = ThreadLocalRandom.current();` cũng được.

Trong executor, một worker thread có thể xử lý nhiều task liên tiếp. Trạng thái PRNG được gắn với **thread**, không phải task/request. Việc task nào chạy trên worker nào phụ thuộc scheduler. Vì thế, cùng một tập task chạy hai lần chưa chắc nhận cùng dãy số.

Không khởi tạo bằng `new ThreadLocalRandom()` và không xem object `ThreadLocalRandom` như một generator độc lập có seed riêng để chuyển từ thread này sang thread khác. Cách dùng điển hình và rõ nhất là `current()` trên luồng đang thực thi.

## 3. API và quy tắc khoảng giá trị

| API | Giá trị trả về và điều kiện |
| --- | --- |
| `ThreadLocalRandom.current().nextInt()` | Một `int` trong toàn miền số nguyên có dấu, bao gồm giá trị âm. |
| `nextInt(bound)` | Số nguyên từ `0` đến `bound - 1`; `bound > 0`. |
| `nextInt(origin, bound)` | Số nguyên trong `[origin, bound)`; bắt buộc `origin < bound`. |
| `nextLong(origin, bound)` | Số `long` trong khoảng nửa mở `[origin, bound)`. |
| `nextDouble(origin, bound)` | Số `double` từ origin (bao gồm) đến bound (không bao gồm), với giới hạn hợp lệ. |
| `nextBoolean()` | Giá trị boolean giả ngẫu nhiên. |

Ví dụ chọn mặt xúc xắc từ **1 đến 6**, có cả hai đầu: `nextInt(1, 7)`. Chọn jitter từ **50 đến 150 ms**: `nextLong(50, 151)`. Đối số không hợp lệ như `nextInt(0)` hoặc `nextInt(7, 7)` ném `IllegalArgumentException`.

Không tự tính `Math.abs(nextInt()) % n` thay cho bound API. `Math.abs(Integer.MIN_VALUE)` vẫn là số âm do tràn kiểu `int`; phép chia dư còn có thể tạo phân phối lệch nếu số đầu vào không chia đều cho `n`. Dùng thẳng `nextInt(n)` hoặc `nextInt(origin, bound)`.

Các API tạo stream như `ints(...)`, `longs(...)` hữu ích, nhưng không suy ra rằng thứ tự cấp số trong **parallel stream** sẽ ổn định qua mọi lịch chạy. Muốn tái lập, cần quản lý generator và lịch sử lời gọi ở mức task.

## 4. Ví dụ Java 17: nhiều worker, không tranh chấp Random chung

Chương trình dưới đây tạo 4 callable, mỗi callable gọi `ThreadLocalRandom.current()` trên chính worker đang chạy, sinh 1.000 giá trị trong `[10, 20)` rồi kiểm tra bound. Chúng ta **không** in ra các giá trị ngẫu nhiên vì các giá trị đó thay đổi giữa các lần chạy; chỉ kiểm tra một bất biến có kết quả xác định.

Lưu **ThreadLocalRandomDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public class ThreadLocalRandomDemo {
    public static void main(String[] args) throws Exception {
        int workerCount = 4;
        int drawsPerWorker = 1_000;
        ExecutorService pool = Executors.newFixedThreadPool(workerCount);

        try {
            List<Callable<Integer>> jobs = new ArrayList<>();

            for (int i = 0; i < workerCount; i++) {
                jobs.add(() -> {
                    ThreadLocalRandom rng = ThreadLocalRandom.current();
                    int outOfRange = 0;

                    for (int n = 0; n < drawsPerWorker; n++) {
                        int value = rng.nextInt(10, 20);
                        if (value < 10 || value >= 20) {
                            outOfRange++;
                        }
                    }
                    return outOfRange;
                });
            }

            List<Future<Integer>> futures = pool.invokeAll(jobs);
            int outOfRange = 0;

            for (Future<Integer> future : futures) {
                outOfRange += future.get();
            }

            System.out.printf(
                    "tasks=%d, draws=%d, outOfRange=%d%n",
                    workerCount,
                    workerCount * drawsPerWorker,
                    outOfRange);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac ThreadLocalRandomDemo.java
java ThreadLocalRandomDemo
~~~

Stdout kỳ vọng:

~~~text
tasks=4, draws=4000, outOfRange=0
~~~

Tất cả 4.000 giá trị đều do `nextInt(10, 20)` sinh ra nên không có giá trị ngoài khoảng. Mỗi callable chỉ thay đổi biến cục bộ của nó, không tạo shared mutable counter. `Future.get()` đợi tác vụ hoàn thành và cho biết lỗi của callable nếu có; submit hoặc invokeAll xong không có nghĩa mọi phần xử lý nghiệp vụ tự động an toàn.

Bài thử này cho thấy **sử dụng đúng API và bound**, không phải một chứng minh thống kê rằng phân phối hoàn hảo hoặc rằng kết quả không thể dự đoán. Khi muốn chứng minh cải thiện hiệu năng, cần benchmark chuyên biệt với tải thực.

## 5. Tại sao không thể dùng `ThreadLocalRandom` để tái lập dãy số?

`ThreadLocalRandom` kế thừa một số phương thức từ `Random`, nhưng **`setSeed(long)` không được hỗ trợ**. Gọi `ThreadLocalRandom.current().setSeed(42L)` ném `UnsupportedOperationException`. Không có cách dùng thông thường được hỗ trợ để yêu cầu tất cả worker bắt đầu từ một seed người dùng xác định.

Ngay cả khi một generator đơn lẻ cho ra dãy dự đoán được theo seed, nếu nhiều task cùng lấy số từ nó, task nào nhận giá trị thứ 1, thứ 2, thứ 3 vẫn có thể thay đổi theo lịch thực thi. Trong thread pool, trạng thái `ThreadLocalRandom` thuộc worker thread và tiến triển cả qua các task trước đó; chỉ cố định số task hoặc số worker cũng chưa đủ để xác định **mapping task → dãy số**.

Để tái lập có ý nghĩa, phải cố định:

1. Seed ban đầu và thuật toán PRNG.
2. Dữ liệu đầu vào cùng trình tự thao tác phát số của **mỗi task**.
3. Quy tắc ánh xạ task ID ổn định sang generator hoặc seed.
4. Thứ tự kết hợp kết quả nếu phép tính phụ thuộc thứ tự, chẳng hạn cộng số thực song song.

`java.util.SplittableRandom` có constructor nhận seed và thích hợp cho mô phỏng/kiểm thử số giả ngẫu nhiên mục đích chung. Nó **không thread-safe**. Vì thế, tốt nhất cấp **một instance riêng cho từng task** và không dùng chung instance khi các task đồng thời lấy số.

## 6. Ví dụ Java 17: tái lập bất kể thứ tự worker

Mỗi task có ID từ 0 đến 7. Hàm `simulate(taskId)` tạo một `SplittableRandom` mới bằng seed `20261028L + taskId`, sinh 1.000 lần xúc xắc rồi tính tổng. Main thực hiện cùng task theo hai cách: tuần tự và song song. Nếu ánh xạ ID/seed và trình tự gọi cố định thì tổng từng task giống nhau dù executor xếp lịch khác.

Lưu **ReproducibleTasks.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ReproducibleTasks {
    private static int simulate(int taskId) {
        SplittableRandom rng = new SplittableRandom(20261028L + taskId);
        int total = 0;

        for (int n = 0; n < 1_000; n++) {
            total += rng.nextInt(1, 7);
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        int taskCount = 8;
        int[] sequential = new int[taskCount];

        for (int id = 0; id < taskCount; id++) {
            sequential[id] = simulate(id);
        }

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Callable<Integer>> jobs = new ArrayList<>();
            for (int id = 0; id < taskCount; id++) {
                final int taskId = id;
                jobs.add(() -> simulate(taskId));
            }

            List<Future<Integer>> futures = pool.invokeAll(jobs);
            boolean reproducible = true;

            for (int id = 0; id < taskCount; id++) {
                if (futures.get(id).get() != sequential[id]) {
                    reproducible = false;
                }
            }

            System.out.printf(
                    "tasks=%d, reproducible=%b%n",
                    taskCount, reproducible);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

~~~bash
javac ReproducibleTasks.java
java ReproducibleTasks
~~~

Stdout:

~~~text
tasks=8, reproducible=true
~~~

`simulate(3)` tạo một RNG mới với cùng seed, rồi gọi `nextInt(1, 7)` đúng 1.000 lần theo một thứ tự duy nhất. Nó không chia sẻ instance với `simulate(7)`. `invokeAll` trả danh sách `Future` cùng thứ tự danh sách task, nên có thể so sánh theo ID mà không cần biết worker nào kết thúc trước.

**Đừng hiểu quá rộng về tính tái lập:**

- Công thức `baseSeed + taskId` ở đây đơn giản để minh họa. Ứng dụng lớn cần quy ước sinh seed/ID tránh tái sử dụng không mong muốn và có thể dùng hàm trộn seed thích hợp.
- `SplittableRandom.split()` tạo generator mới cho nhánh tính toán. Muốn tái lập, thứ tự split và cây phân chia phải xác định; không để nhiều thread cùng gọi `split()` trên một instance.
- Nếu các task dùng trạng thái mutable chung, chia sẻ số thực cộng dồn theo thứ tự khác nhau hoặc đọc đồng hồ/thời gian thực, seed cố định **không** đảm bảo kết quả nghiệp vụ cố định.
- Với mục tiêu tái lập qua nhiều môi trường hay thời gian dài, ghi lại seed, thuật toán/phiên bản generator, JDK, ID task và input. Không mặc định mọi thuật toán ở các thư viện hoặc phiên bản JVM luôn sinh một chuỗi byte giống nhau mãi mãi.
- Generator có seed phục vụ test **không** được dùng để tạo bí mật chỉ vì test muốn assert giá trị cố định.

Java 17 có họ giao diện `java.util.random.RandomGenerator`. Đây là giao diện thống nhất nhiều generator; tên giao diện không chứng minh mọi implementation đáp ứng yêu cầu mật mã.

## 7. Giới hạn bảo mật: pseudo-random khác cryptographically secure

`ThreadLocalRandom` được thiết kế cho số giả ngẫu nhiên **mục đích chung và hiệu quả khi đa luồng**. Nó **không phải CSPRNG** và không cung cấp đảm bảo đủ khó dự đoán nếu kẻ tấn công quan sát một phần đầu ra hoặc suy đoán trạng thái.

Tuyệt đối không dùng `ThreadLocalRandom` tạo:
- Token đăng nhập, token khôi phục mật khẩu, mã phiên, API key hoặc giá trị đại diện cho quyền truy cập.
- Khóa bí mật, mật khẩu ngẫu nhiên, mã khôi phục hoặc vật liệu mật mã.
- IV/nonce cần tuân thủ tiêu chuẩn bảo mật của thuật toán, hay tên/đường dẫn bí mật mà hệ thống dựa vào khả năng khó đoán để bảo vệ.

Dùng nhiều chữ số không sửa được yếu điểm dự đoán. Một chuỗi 64 ký tự được tạo bằng PRNG không an toàn **không tự động** có 64 ký tự entropy an toàn mật mã.

Trong Java, `java.security.SecureRandom` là nguồn cung cấp số ngẫu nhiên thích hợp cho trường hợp mật mã, thông qua provider được cấu hình của JDK. Nó có tính chất bảo mật phù hợp hơn, nhưng chi phí khởi tạo, lấy entropy và thông lượng phụ thuộc môi trường/provider, không được xem là luôn nhanh như `ThreadLocalRandom`.

### Ví dụ Java 17: 32 byte token từ `SecureRandom`

Lưu **SecureTokenDemo.java**:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secure = new SecureRandom();
        byte[] token = new byte[32];
        secure.nextBytes(token);

        String tokenHex = HexFormat.of().formatHex(token);

        // Chỉ in độ dài, không in giá trị bí mật.
        System.out.printf(
                "bytes=%d, hexChars=%d%n",
                token.length, tokenHex.length());
    }
}
~~~

~~~bash
javac SecureTokenDemo.java
java SecureTokenDemo
~~~

Stdout:

~~~text
bytes=32, hexChars=64
~~~

Nội dung 32 byte thay đổi khi chạy; chỉ độ dài có kết quả cố định. `HexFormat` chuyển mỗi byte thành hai ký tự hex, nên 32 byte tương ứng 64 ký tự. Mã hóa hex/Base64 chỉ đổi **cách biểu diễn**, không tự tạo thêm entropy. Khi xây ứng dụng, bí mật cần được bảo vệ cả lúc lưu, truyền và xác minh; không in ra log.

Lưu ý:
- `new SecureRandom()` thường đủ cho nhu cầu ứng dụng; `SecureRandom.getInstanceStrong()` không phải lựa chọn bắt buộc trong mọi trường hợp và có thể chờ entropy lâu tùy provider.
- Không cố định seed công khai cho token sản xuất. `SecureRandom.setSeed(...)` có semantics phụ thuộc provider và không phải hợp đồng để tái hiện một dãy test.
- `SecureRandom` hỗ trợ sử dụng đồng thời, nhưng provider có thể có đồng bộ nội bộ và chi phí khác nhau; nếu tốc độ quan trọng, benchmark chính xác provider và môi trường sử dụng.
- Khi thiết kế token URL-safe có thể dùng Base64 URL encoder với byte[] từ `SecureRandom`; mọi thuộc tính bảo mật vẫn bắt nguồn từ CSPRNG, không phải encoder.

**Quy tắc:** dữ liệu cần “trông ngẫu nhiên” cho chia tải khác dữ liệu cần “khó đoán trước” để bảo vệ tài khoản. Chọn nguồn theo yêu cầu nghiệp vụ, không theo tốc độ duy nhất.

## 8. Bảng chọn API phù hợp

| Công cụ Java | Bài toán phù hợp | Seed có thể kiểm soát? | An toàn mật mã? | Lưu ý đa luồng |
| --- | --- | --- | --- | --- |
| `Random` | Số giả ngẫu nhiên thông dụng; mô phỏng đơn giản | Có (`new Random(seed)`) | Không | Thread-safe khi dùng chung, nhưng có thể contention. |
| `ThreadLocalRandom.current()` | Nhiều worker cần số thường xuyên và không yêu cầu dãy cố định | Không qua `setSeed` | Không | State phát số gắn với luồng. |
| `SplittableRandom` | Mô phỏng, chia nhánh, test tái lập theo seed/task ID | Có | Không | Không thread-safe; mỗi task/worker một instance. |
| `SecureRandom` | Bí mật, token, vật liệu mật mã theo quy tắc an toàn | Không nên xem seed cố định là hợp đồng test | Có, theo provider/thuật toán | Dùng được đồng thời, chi phí tùy provider. |

Một instance `Random` **riêng** cho từng worker cũng có thể loại bỏ tranh chấp của shared `Random`, nên không thể nói “ThreadLocalRandom nhanh hơn mọi cách dùng Random”. `SplittableRandom` thường hữu ích khi tạo các nhánh độc lập có seed hoặc split rõ ràng; không thay cho CSPRNG.

Nếu mục tiêu là **ID không trùng**, không suy từ PRNG sang tính duy nhất. Cần thiết kế cách cấp ID, kiểm tra trùng hoặc chọn loại ID có xác suất trùng phù hợp với hệ thống; tính khó đoán và tính duy nhất là hai thuộc tính khác nhau.

## 9. Đo hiệu năng đúng cách

Tình huống thường có lợi cho `ThreadLocalRandom`: nhiều luồng liên tục lấy số, trong khi phần xử lý mỗi lần rất ngắn. Một `Random` dùng chung buộc các luồng cùng cập nhật trạng thái. Nhưng không tự kết luận rằng `ThreadLocalRandom` “nhanh hơn N lần”: điều đó thay đổi theo JDK, CPU, mức song song, warmup, loại bound và workload.

Thí nghiệm nên so sánh ít nhất:
1. **Một** `Random` dùng chung cho mọi worker.
2. `ThreadLocalRandom.current()` tại mỗi worker.
3. **Một** `Random` riêng cho từng worker.
4. **Một** `SplittableRandom` riêng cho từng worker/task, nếu bài toán cho phép.

Dùng **JMH** để benchmark JVM với warmup, nhiều fork, chế độ đo throughput hoặc latency và số thread khác nhau. Phải **tiêu thụ đầu ra** để JIT không tối ưu bỏ phép tính. Cần đo CPU/GC và thời gian toàn tác vụ, vì lợi ích microbenchmark có thể biến mất khi phần lớn thời gian bị chiếm bởi I/O hoặc xử lý nghiệp vụ.

Không benchmark bằng một vòng `System.nanoTime()` đơn lẻ rồi coi kết quả là chân lý. JIT compilation, dead-code elimination, cache, GC và scheduling tạo nhiễu. Không cần đưa mọi mục tiêu về throughput: nếu ứng dụng đòi hỏi kết quả phát lại được hoặc phải bảo mật, PRNG nhanh nhất không nhất thiết là lựa chọn đúng.

### ThreadLocalRandom không giải quyết các nút thắt khác

Nó không sửa lock cạnh tranh trên dữ liệu nghiệp vụ, không tăng tốc database, không ngăn deadlock, không bảo đảm fairness và không cung cấp tính đồng bộ cho bất kỳ map/list dùng chung nào. Đo contention ở thành phần nào thì tối ưu thành phần đó.

## 10. Tình huống thực tế: retry jitter

Khi một dịch vụ vừa phục hồi, hàng trăm worker retry đúng cùng một mốc thời gian có thể tiếp tục gây quá tải. Jitter không bảo mật giúp giãn các lần thử:

~~~java
long jitterMillis = java.util.concurrent.ThreadLocalRandom.current()
        .nextLong(50, 151); // 50 đến 150 ms, tính cả 150
~~~

Đây là **đoạn mã minh họa**, không phải chương trình hoàn chỉnh. Retry thực tế cần giới hạn số lần, deadline tổng, backoff, kiểm soát cancel/interrupt và xử lý riêng các thao tác không idempotent. Nếu dùng `Thread.sleep(jitterMillis)`, luồng thực thi bị chiếm trong khi chờ; cân nhắc scheduler nếu có nhiều tác vụ trễ. Jitter chỉ giảm đồng loạt, không bảo đảm thành công hoặc loại bỏ quá tải.

Muốn test được thời gian retry thì **truyền vào nguồn ngẫu nhiên có thể thay thế** hoặc truyền giá trị jitter kiểm thử cố định. Không gọi `setSeed` trên `ThreadLocalRandom`.

## 11. Kiểm thử và các lỗi phổ biến

**Kiểm thử bound:** với `nextInt(5, 12)` hãy assert mọi giá trị đều thuộc `[5, 12)`; đừng assert một dãy cụ thể. **Kiểm thử tái lập:** dùng cùng seed, thuật toán, task ID và trình tự gọi. **Kiểm thử concurrency:** thử các mức thread khác nhau, dùng `CountDownLatch` để phối hợp khi cần, dùng `Future.get(timeout, unit)` để test không treo mãi; không dựa vào `Thread.sleep` để giả định lịch chạy đã đạt một trạng thái race. **Kiểm thử CSPRNG:** kiểm tra format/độ dài và chính sách bảo mật; đừng assert giá trị token cố định.

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi `ThreadLocalRandom.current().setSeed(42L)` | Ném `UnsupportedOperationException`. | Dùng `Random(seed)` hoặc `SplittableRandom(seed)` cho tái lập. |
| Coi thread pool có lịch thực thi cố định | Mỗi task có thể nhận dãy khác. | Gán seed/generator riêng theo task ID ổn định. |
| Chia sẻ `SplittableRandom` giữa các thread | Không thread-safe. | Mỗi task một instance hoặc phân nhánh trước khi chạy. |
| Dùng `ThreadLocalRandom` tạo token đăng nhập | Không bảo đảm chống đoán trong mật mã. | `SecureRandom`. |
| Dùng `Math.abs(nextInt()) % n` | Tràn giá trị và có thể lệch phân phối. | `nextInt(n)`. |
| Coi số ngẫu nhiên là unique | Có thể trùng. | Thiết kế ID và kiểm tra trùng phù hợp. |
| Đo một lần trên vòng lặp rất ngắn | JVM warmup/scheduler/JIT làm lệch. | JMH và benchmark nhiều thread. |
| Assert thứ tự log của các worker | Scheduler không đảm bảo thứ tự. | So sánh kết quả theo task ID hoặc invariant. |
| Thay generator mà bỏ qua contention ở nơi khác | Không cải thiện ứng dụng. | Profile end-to-end trước và sau. |

### Câu hỏi tự kiểm tra

**1.** Có 32 thread chọn ngẫu nhiên bucket để chia tải, không cần tái lập và không phải bí mật. Chọn gì?

**Trả lời:** `ThreadLocalRandom.current().nextInt(bucketCount)` với `bucketCount > 0`; đo nếu đường xử lý rất nóng.

**2.** Test có 16 task, cần kết quả như nhau khi chạy trên pool 2 hoặc 8 worker. Chọn gì?

**Trả lời:** Mỗi task có ID/seed ổn định và một `SplittableRandom` riêng, giữ cùng trình tự lời gọi; kiểm tra kết quả theo ID.

**3.** Sinh token bằng 32 lần `ThreadLocalRandom.current().nextInt(256)` có bảo mật vì được 32 byte không?

**Trả lời:** Không. Độ dài không chứng minh khả năng chống dự đoán. Dùng `SecureRandom.nextBytes(byte[32])` và bảo vệ token.

**4.** Vì sao `Random` dùng chung thread-safe nhưng vẫn có thể chậm?

**Trả lời:** Đúng về cập nhật trạng thái không có nghĩa chi phí phối hợp bằng không; nhiều luồng cạnh tranh một trạng thái, còn ThreadLocalRandom tránh điểm chia sẻ này.

## 12. Checklist áp dụng

1. Xác định **có yêu cầu bảo mật mật mã** không: nếu có, chọn `SecureRandom` và quy tắc mật mã phù hợp.
2. Nếu chỉ giả ngẫu nhiên mục đích chung, xác định **có cần tái lập** không: nếu có, dùng generator có seed cố định và mapping task ID rõ ràng.
3. Nếu nhiều thread cần sinh số nhanh, không cần dãy tái lập: dùng `ThreadLocalRandom.current()` trong luồng thực thi.
4. Kiểm tra bound dạng nửa mở, không tự dùng `abs % n` và không suy rằng kết quả random luôn unique.
5. Đo performance dưới workload thật; đừng dùng tốc độ làm lý do bỏ yêu cầu tái lập hoặc bảo mật.

`ThreadLocalRandom.current()` giải quyết một vấn đề cụ thể: giảm contention khi **nhiều luồng cùng cần số giả ngẫu nhiên**. Nó không có hợp đồng seed để tái lập chính xác và không có cam kết chống dự đoán cho dữ liệu bí mật. Muốn tái lập, gán generator/seed theo task; muốn an toàn mật mã, dùng `SecureRandom`.