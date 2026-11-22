# Kiểm thử tính đúng đắn và khả năng mở rộng theo số luồng

## 1. Hai câu hỏi cần bằng chứng khác nhau

Với skip list đồng thời, cần trả lời riêng:

- **Đúng đắn:** thao tác có giữ được dữ liệu và các bất biến của ứng dụng khi nhiều luồng đan xen không?
- **Khả năng mở rộng:** khi tăng số luồng, thông lượng và độ trễ thay đổi như thế nào với cùng một khối lượng công việc được định nghĩa rõ?

Một chương trình chạy nhanh nhưng làm mất cập nhật không phải kết quả tốt. Một kiểm thử đúng đắn chạy qua với tám luồng cũng chưa chứng minh cấu trúc nhanh hơn khi tăng từ bốn lên tám luồng.

Bài dùng `ConcurrentSkipListMap` để minh họa. Các API hiện còn áp dụng trong Java hiện đại; chương trình kiểm tra độc lập dùng Java 17 trở lên. Phần đo hiệu năng dùng JMH trong một dự án benchmark riêng.

## 2. Định nghĩa bất biến trước khi tạo luồng

Giả sử T luồng cùng cố đăng ký 1.000 khóa, mỗi luồng thử đủ các khóa từ 0 đến 999. Không có thao tác xóa trong kịch bản này.

Các điều kiện có thể kiểm tra sau khi mọi luồng hoàn tất:

1. Map chứa đúng 1.000 khóa, không bị thiếu hoặc có khóa ngoài miền.
2. Mỗi khóa có đúng một lần `putIfAbsent` thành công khi khóa còn vắng.
3. Tổng số lần đăng ký thành công trên tất cả luồng bằng 1.000.
4. Giá trị của mỗi khóa là một mã luồng hợp lệ, nhưng không cố định luồng nào phải thắng.
5. Thứ tự khóa sau khi kết thúc là 0, 1, 2, ..., 999.

Để kiểm tra cập nhật có tranh chấp, thêm một map bộ đếm gồm 16 nhóm. Mỗi lần xử lý khóa k, luồng tăng nhóm `k % 16` bằng `merge`. Tổng số tăng phải bằng `T × 1.000`, và từng nhóm có giá trị kỳ vọng xác định.

`ConcurrentSkipListMap` hỗ trợ các thao tác cập nhật đồng thời, nhưng hàm tính lại của `merge` không được bảo đảm chỉ gọi một lần. Dùng hàm không gây tác động phụ như `Integer::sum`; không đặt việc gửi thông báo hoặc tăng một bộ đếm bên ngoài trong hàm đó. Xem [ConcurrentSkipListMap.merge](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html#merge(K,V,java.util.function.BiFunction)).

## 3. Chương trình kiểm thử đúng đắn với 1, 2, 4 và 8 luồng

Ví dụ dùng một cổng bắt đầu chung, chờ toàn bộ future và kiểm tra dữ liệu sau khi các tác vụ hoàn tất. Timeout giúp phát hiện công việc không tiến triển; nó không phải tiêu chuẩn so tốc độ giữa các cấu hình.

Lưu tệp `SkipListCorrectnessDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SkipListCorrectnessDemo {
    static final int KEYS = 1000;
    static final int BUCKETS = 16;

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void runCase(int threadCount) throws Exception {
        ConcurrentSkipListMap<Integer, Integer> owners =
                new ConcurrentSkipListMap<>();
        ConcurrentSkipListMap<Integer, Integer> counts =
                new ConcurrentSkipListMap<>();

        ExecutorService pool = Executors.newFixedThreadPool(threadCount);
        CountDownLatch ready = new CountDownLatch(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < threadCount; worker++) {
                final int ownerId = worker;
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();
                    int wins = 0;
                    for (int key = 0; key < KEYS; key++) {
                        if (owners.putIfAbsent(key, ownerId) == null) {
                            wins++;
                        }
                        counts.merge(key % BUCKETS, 1, Integer::sum);
                    }
                    return wins;
                }));
            }

            check(ready.await(10, TimeUnit.SECONDS), "Workers not ready");
            start.countDown();

            int totalWins = 0;
            for (Future<Integer> future : futures) {
                totalWins += future.get(30, TimeUnit.SECONDS);
            }

            check(owners.size() == KEYS, "Wrong key count");
            check(totalWins == KEYS, "Wrong successful insert count");

            int expectedKey = 0;
            for (Map.Entry<Integer, Integer> entry : owners.entrySet()) {
                check(entry.getKey() == expectedKey, "Missing or unordered key");
                int owner = entry.getValue();
                check(owner >= 0 && owner < threadCount, "Invalid owner");
                expectedKey++;
            }
            check(expectedKey == KEYS, "Incomplete traversal");

            check(counts.size() == BUCKETS, "Wrong bucket count");
            int totalUpdates = 0;
            for (int bucket = 0; bucket < BUCKETS; bucket++) {
                int perWorker = KEYS / BUCKETS
                        + (bucket < KEYS % BUCKETS ? 1 : 0);
                int expected = perWorker * threadCount;
                Integer actual = counts.get(bucket);
                check(actual != null && actual == expected,
                        "Lost update in bucket " + bucket);
                totalUpdates += actual;
            }
            check(totalUpdates == threadCount * KEYS, "Wrong total updates");

            System.out.println("threads=" + threadCount
                    + " keys=" + owners.size()
                    + " successful.inserts=" + totalWins
                    + " updates=" + totalUpdates
                    + " PASS");
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        for (int threadCount : new int[] {1, 2, 4, 8}) {
            runCase(threadCount);
        }
        System.out.println("ALL PASS");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SkipListCorrectnessDemo.java
java SkipListCorrectnessDemo
```

Stdout khi các kiểm tra đều thành công:

```text
threads=1 keys=1000 successful.inserts=1000 updates=1000 PASS
threads=2 keys=1000 successful.inserts=1000 updates=2000 PASS
threads=4 keys=1000 successful.inserts=1000 updates=4000 PASS
threads=8 keys=1000 successful.inserts=1000 updates=8000 PASS
ALL PASS
```

Luồng nào thắng ở từng khóa có thể khác nhau giữa các lần chạy. Chương trình kiểm tra các giá trị chủ sở hữu nằm trong miền hợp lệ, không ép một lịch chạy cố định.

`Future.get` đưa lỗi từ tác vụ về luồng chính. Việc kiểm tra kích thước, thứ tự và tổng bộ đếm diễn ra sau khi tất cả tác vụ kết thúc, nên không áp đặt yêu cầu ảnh chụp lên iterator đang chịu cập nhật.

## 4. Giới hạn của kiểm thử đúng đắn này

Chương trình kiểm tra những bất biến cụ thể trong một khối lượng công việc hữu hạn. Nó chưa kiểm tra mọi thao tác, mọi comparator hay mọi cách đan xen.

Nên thêm các kịch bản theo ứng dụng:

- Thêm và xóa trên các miền khóa tách rời, để trạng thái cuối có đáp án đơn giản.
- Tranh chấp trên một số ít khóa nóng.
- `replace(key, oldValue, newValue)` và `remove(key, value)` với kiểm tra giá trị trả về.
- Truy vấn khoảng khi writer hoạt động, kiểm tra biên và thứ tự theo hợp đồng nhất quán yếu.
- Khóa ghép, khóa biên và comparator tùy chỉnh.

Nếu thử đọc giá trị rồi tăng bằng `get` và `put` riêng rẽ, có thể mất cập nhật. Một lần chạy không gặp lỗi không làm chuỗi đó trở thành nguyên tử.

Đối với lịch sử thao tác ngắn cần phân loại những kết quả được phép/cấm, có thể dùng [jcstress của OpenJDK](https://github.com/openjdk/jcstress), công cụ phục vụ nghiên cứu tính đúng đắn của hỗ trợ đồng thời trong JVM, thư viện và phần cứng. Một bài stress test không thay thế việc phát biểu hợp đồng đúng đắn của ứng dụng.

## 5. Xác định phép đo khả năng mở rộng

Trước khi đo, ghi rõ một thao tác trong phép đo là gì và các biến được giữ cố định:

| Biến | Vì sao cần kiểm soát |
| --- | --- |
| Số luồng T | Biến chính đang khảo sát |
| Số khóa đang lưu | Ảnh hưởng kích thước cấu trúc và đường tìm |
| Tỉ lệ đọc/ghi | Làm thay đổi tranh chấp và công việc cập nhật |
| Phân bố khóa | Phân tán rộng khác với tập trung vào khóa nóng |
| Loại thao tác | get, cập nhật khóa có sẵn, chèn mới, xóa và quét khoảng có chi phí khác nhau |
| Kích thước khoảng đọc | Một lần quét 1.000 phần tử khác một lần get |
| JDK/JVM và phần cứng | Ảnh hưởng tối ưu hóa, bộ nhớ và tài nguyên xử lý |

Cần để các luồng thực sự dùng chung một map nếu mục tiêu là đo tranh chấp trên cấu trúc dùng chung. Một map riêng cho mỗi luồng trả lời câu hỏi khác.

Không để số khóa tăng mãi trong một phép đo cập nhật ổn định mà vẫn gọi đó là “cùng khối lượng công việc”. Nếu đo chèn mới và tăng kích thước, hãy khai báo đó là kịch bản riêng.

## 6. Ví dụ JMH có map dùng chung và kích thước ổn định

[JMH của OpenJDK](https://github.com/openjdk/jmh) cung cấp hạ tầng benchmark trên JVM. Dùng dự án được cấu hình annotation processor, giai đoạn làm nóng, nhiều vòng đo và nhiều tiến trình JVM độc lập.

Tạo dự án riêng bằng Maven trong một thư mục làm việc dành cho thí nghiệm. Ví dụ chốt phiên bản JMH 1.37 để tái lập cấu hình, không ngụ ý đây là phiên bản mới nhất:

```shell
mvn archetype:generate "-DinteractiveMode=false" "-DarchetypeGroupId=org.openjdk.jmh" "-DarchetypeArtifactId=jmh-java-benchmark-archetype" "-DarchetypeVersion=1.37" "-DgroupId=demo" "-DartifactId=skiplist-bench" "-Dversion=1.0"
```

Tạo tệp `skiplist-bench/src/main/java/demo/SkipListBench.java` với nội dung sau. Đây là mã benchmark phụ thuộc JMH và build Maven đã tạo, không phải chương trình chỉ chạy bằng `javac`:

```java
package demo;

import java.util.SplittableRandom;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.ThreadParams;

@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SkipListBench {
    @State(Scope.Benchmark)
    public static class Shared {
        @Param({"65536", "64"})
        public int keySpace;

        @Param({"0", "10", "50"})
        public int writePercent;

        public ConcurrentSkipListMap<Integer, Integer> map;

        @Setup(Level.Trial)
        public void setup() {
            map = new ConcurrentSkipListMap<>();
            for (int key = 0; key < 65536; key++) {
                map.put(key, key);
            }
        }
    }

    @State(Scope.Thread)
    public static class Access {
        public SplittableRandom random;
        public int nextValue;

        @Setup(Level.Iteration)
        public void setup(ThreadParams params) {
            random = new SplittableRandom(12345L + params.getThreadIndex());
            nextValue = params.getThreadIndex();
        }
    }

    @Benchmark
    public Integer access(Shared shared, Access access) {
        int key = access.random.nextInt(shared.keySpace);
        if (access.random.nextInt(100) < shared.writePercent) {
            return shared.map.put(key, access.nextValue++);
        }
        return shared.map.get(key);
    }
}
```

Giải thích cấu hình:

- `Scope.Benchmark`: một trạng thái map được chia sẻ giữa các luồng đo trong cùng lần chạy.
- `Scope.Thread`: mỗi luồng có bộ sinh khóa và bộ đếm giá trị riêng, không vô tình tạo một điểm tranh chấp ở bộ sinh số dùng chung.
- Map được nạp 65.536 khóa ngoài phần đo; mọi lần put chỉ cập nhật khóa đã có, nên kích thước không tăng.
- `keySpace=65536` truy cập phân tán trên toàn miền; `keySpace=64` tập trung trên một vùng nhỏ của cùng map.
- `writePercent` là xác suất chọn put cho mỗi lần gọi; tỉ lệ thực tế dao động quanh cấu hình.
- Trả kết quả của thao tác cho JMH giúp kết quả được sử dụng bởi hạ tầng đo.

Phép đo có cả chi phí sinh khóa, rẽ nhánh và đóng hộp số nguyên (boxing) của ví dụ. Nếu cần tách chi phí này, thiết kế thêm phép đo nền hoặc cách cấp khóa khác; không mặc định mọi thời gian thu được chỉ đến từ skip list.

Cách dựng và chạy dự án theo Maven archetype được mô tả trong [hướng dẫn JMH chính thức](https://github.com/openjdk/jmh#preferred-usage-command-line).

## 7. Chạy cùng một cấu hình với số luồng khác nhau

Trong thư mục `skiplist-bench`, build bằng:

```shell
mvn clean verify
```

Sau đó chạy cùng miền khóa và tỉ lệ ghi, chỉ thay số luồng:

```shell
java -jar target/benchmarks.jar demo.SkipListBench.access -t 1 -p writePercent=10 -p keySpace=65536 -rf json -rff t1.json
java -jar target/benchmarks.jar demo.SkipListBench.access -t 2 -p writePercent=10 -p keySpace=65536 -rf json -rff t2.json
java -jar target/benchmarks.jar demo.SkipListBench.access -t 4 -p writePercent=10 -p keySpace=65536 -rf json -rff t4.json
java -jar target/benchmarks.jar demo.SkipListBench.access -t 8 -p writePercent=10 -p keySpace=65536 -rf json -rff t8.json
```

Từ thư mục cha có thể chuyển bằng `cd skiplist-bench`. JDK và Maven cần sẵn sàng; lần tạo/build đầu cần tải phụ thuộc.

Các lệnh tạo kết quả hiệu năng phụ thuộc máy và JVM. Không có một bảng số ops/s cố định để coi là stdout đúng cho mọi môi trường.

Sau bộ đo trên, lặp lại với `keySpace=64` để khảo sát tranh chấp khóa nóng, hoặc đổi `writePercent` theo kịch bản đã định. So sánh từng nhóm có cùng tham số thay vì trộn kết quả của các khối lượng công việc khác nhau.

Nếu cần đo truy vấn khoảng, tạo benchmark riêng với một số khóa kết quả được kiểm soát và sử dụng kết quả đọc được. Không đặt một get và một lượt quét dài ngang nhau rồi so số lần gọi mỗi giây mà quên khác biệt lượng công việc.

## 8. Đọc thông lượng và độ trễ cho đúng

Gọi Q(T) là tổng thông lượng đo được với T luồng trên cùng cấu hình:

```text
Hệ số tăng tốc: S(T) = Q(T) / Q(1)
Hiệu suất theo số luồng: E(T) = Q(T) / (T * Q(1))
```

Nếu tăng số luồng mà Q(T) gần như không tăng, có thể đã gặp giới hạn tài nguyên, tranh chấp hoặc chi phí phối hợp. Cần dữ liệu thêm để xác định nguyên nhân; đường thông lượng phẳng không tự chứng minh một chi tiết nội bộ cụ thể.

Thông lượng cao cũng không tự bảo đảm độ trễ tốt. Muốn khảo sát phân bố độ trễ, dùng chế độ đo thích hợp như `SampleTime` và ghi rõ đơn vị, cấu hình, cách diễn giải mẫu. Độ trễ của benchmark cũng chưa tự đại diện cho độ trễ toàn bộ dịch vụ.

Khi báo cáo kết quả, giữ lại:

- JDK, JVM flags, hệ điều hành, CPU và giới hạn CPU thực tế.
- Kích thước map, miền khóa, tỉ lệ thao tác và hướng duyệt nếu có.
- Số luồng, số tiến trình đo, số vòng làm nóng/đo.
- Kết quả thô, độ dao động và thông tin về cấp phát và thu gom rác (GC) khi cần.
- Mọi thay đổi cấu hình giữa hai lượt so sánh.

Không loại bỏ các lần chạy bất lợi chỉ vì không khớp kỳ vọng. Nếu phải loại kết quả do nhiễu môi trường đã xác định, ghi rõ lý do và chạy lại theo cùng quy trình.

## 9. Những lỗi khiến kết luận sai

### Đo cả tạo luồng rồi gọi đó là tốc độ của map

Thời gian khởi tạo executor, nạp dữ liệu và in log có thể lấn át thao tác cần đo. Chương trình kiểm thử ở đầu bài cố ý không đưa ra kết luận tốc độ từ thời gian chạy của nó.

### Chia map theo từng luồng khi định đo dữ liệu dùng chung

Kết quả khi đó thiếu tranh chấp cần khảo sát. Trong JMH phải xem phạm vi `@State`, không chỉ xem `-t`.

### So cấu trúc không cùng bảo đảm đúng đắn

Một `TreeMap` bị nhiều luồng sửa không đồng bộ không phải đối chứng hợp lệ cho map đồng thời. Nếu so với phiên bản có khóa ngoài, phải mô tả cơ chế bảo vệ đó và áp dụng đúng cho mọi đường truy cập.

### Đếm tác động phụ trong hàm tính lại

Nếu hàm merge có thể được áp dụng lại, số lần gọi hàm không tương đương số cập nhật đã được chấp nhận. Ví dụ dùng phép cộng thuần để kiểm tra giá trị cuối thay vì đếm số lần callback chạy.

### Dùng một lần chạy để kết luận mọi lịch đều đúng

Cần kết hợp phát biểu bất biến, kiểm thử có kiểm soát và các thí nghiệm stress phù hợp. Nhiều lần PASS tăng bằng chứng cho kịch bản đã thử, không biến một số lần chạy hữu hạn thành chứng minh toàn bộ hành vi.

## 10. Thực hành

1. Tại sao chương trình kiểm thử không yêu cầu luồng 0 phải thắng ở mọi khóa?
2. Vì sao tổng successful.inserts là 1.000 với mọi T trong khi tổng updates tăng theo T?
3. Nếu thay merge bằng get rồi put, cần thận trọng với kết luận nào khi một lần thử vẫn PASS?
4. Trong benchmark, vì sao map thuộc Scope.Benchmark nhưng bộ sinh khóa thuộc Scope.Thread?
5. Khi so 4 và 8 luồng, những tham số nào phải được giữ nguyên?
6. Nếu keySpace giảm từ 65.536 xuống 64, câu hỏi thí nghiệm đã thay đổi thế nào?

Định hướng: (1) lịch tranh chấp không cố định; (2) mỗi khóa chỉ được đăng ký lần đầu một lần, còn mỗi luồng đều tăng bộ đếm; (3) chưa chứng minh chuỗi cập nhật đã nguyên tử; (4) cần dữ liệu dùng chung nhưng tránh tranh chấp ngoài ý muốn ở bộ sinh khóa; (5) cùng cấu trúc, lượng dữ liệu, phân bố khóa, tỉ lệ thao tác và môi trường; (6) đang tăng mức tập trung truy cập vào vùng khóa nóng.

Một kết luận có giá trị cần nêu rõ điều đã được kiểm tra đúng và khối lượng công việc đã được đo. Số luồng chỉ là một tham số trong hai quá trình đó.
