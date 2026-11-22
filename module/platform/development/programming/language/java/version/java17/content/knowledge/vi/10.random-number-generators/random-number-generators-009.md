# Chia bộ sinh cho các tác vụ song song trong Java 17

Khi nhiều tác vụ cùng cần sinh số giả ngẫu nhiên, một câu hỏi quan trọng là **mỗi tác vụ lấy dãy số từ đâu và có dùng chung trạng thái bộ sinh hay không**. Nếu tất cả luồng cùng gọi một bộ sinh có trạng thái, chương trình có thể gặp tranh chấp, khó kiểm soát thứ tự tiêu thụ số và khó tái lập kết quả. Nếu mỗi tác vụ tự tạo một bộ sinh từ seed tùy tiện, các dãy có thể không được phân tách theo cách có chủ đích.

Java có những lựa chọn dành cho các tình huống khác nhau:

- **SplittableRandom** được thiết kế cho tính toán song song: một bộ sinh cha có thể tách thành các bộ sinh con, mỗi bộ sinh con được dùng độc lập trong một tác vụ.
- **RandomGenerator** và **RandomGeneratorFactory** từ Java 17 cung cấp giao diện thống nhất và cách khám phá/chọn thuật toán.
- **ThreadLocalRandom** phù hợp khi nhiều thread cần sinh số nhanh và không cần tự quản lý seed để tái lập từng tác vụ.
- **Random** vẫn có ích trong một số tình huống tương thích, nhưng chia sẻ một instance có thể gây tranh chấp khi nhiều thread cùng sử dụng.
- **SecureRandom** dành cho mục đích bảo mật; không thay bằng bộ sinh mô phỏng thông thường khi tạo token hoặc bí mật.

Trọng tâm của bài là cách **chia bộ sinh theo tác vụ logic**, tránh chia sẻ trạng thái mutable và giữ được khả năng tái lập khi cần. Ví dụ sử dụng Java 17, không cần tính năng preview.

## 1. Vì sao không nên dùng chung một bộ sinh cho nhiều tác vụ?

Các bộ sinh giả ngẫu nhiên thông thường không tạo ra entropy mới cho mỗi lần gọi. Chúng duy trì trạng thái nội bộ; mỗi lần lấy số, trạng thái được cập nhật để tạo giá trị tiếp theo.

Giả sử có nhiều thread cùng truy cập một biến:

~~~java
Random random = new Random();

IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> {
            int value = random.nextInt();
            process(value);
        });
~~~

Đoạn mã này không nhất thiết sai về mặt an toàn luồng: java.util.Random được thiết kế để dùng từ nhiều thread. Tuy nhiên, tất cả thread cùng cập nhật trạng thái của một instance. Khi tải cao, việc đồng bộ cập nhật trạng thái có thể trở thành điểm tranh chấp. Hơn nữa, số nào được cấp cho tác vụ nào phụ thuộc thứ tự các thread thực hiện lời gọi; việc chạy lại với cùng seed không bảo đảm cùng một tác vụ logic nhận đúng cùng giá trị nếu thứ tự tiêu thụ thay đổi.

Với SplittableRandom, việc dùng chung còn không an toàn:

~~~java
SplittableRandom random = new SplittableRandom(1234L);

IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> process(random.nextInt()));
~~~

**SplittableRandom không thread-safe.** Nhiều thread không được đồng thời gọi các phương thức trên cùng instance. Việc cập nhật trạng thái có thể bị đua và kết quả không còn được bảo đảm.

Một cách sai khác là gọi split() trên cùng bộ sinh cha ngay bên trong tác vụ song song:

~~~java
SplittableRandom root = new SplittableRandom(1234L);

IntStream.range(0, 100)
        .parallel()
        .forEach(i -> {
            SplittableRandom child = root.split(); // Không an toàn
            process(child.nextInt());
        });
~~~

Mặc dù mỗi lambda tạo một child, chính thao tác split() vẫn cùng lúc truy cập root từ nhiều thread. Phải thực hiện việc chia ở một nơi được kiểm soát, sau đó giao từng bộ sinh con cho một tác vụ riêng.

## 2. SplittableRandom: bộ sinh phù hợp cho tính toán song song

SplittableRandom có từ Java 8 và vẫn được hỗ trợ trong Java 17. Nó được thiết kế để tách một bộ sinh thành các bộ sinh con có trạng thái độc lập. Mỗi bộ sinh con có thể được dùng bởi một thread hoặc tác vụ mà không cần đồng bộ với bộ sinh cha hay các bộ sinh con khác.

~~~java
import java.util.SplittableRandom;

SplittableRandom parent = new SplittableRandom(2026L);

SplittableRandom firstTask = parent.split();
SplittableRandom secondTask = parent.split();

int firstValue = firstTask.nextInt();
int secondValue = secondTask.nextInt();
~~~

Ý nghĩa:

1. Tạo bộ sinh gốc với seed đã chọn.
2. Gọi split() ở luồng đang sở hữu parent để tạo một bộ sinh con.
3. Tiếp tục split() để tạo các bộ sinh khác khi cần.
4. Chuyển từng bộ sinh con cho một tác vụ và chỉ tác vụ đó sử dụng nó.

Các bộ sinh được tách không chia sẻ trạng thái mutable. API mô tả các dãy sinh ra có tính độc lập thống kê phù hợp cho tính toán song song; điều này **không phải cam kết độc lập toán học tuyệt đối hoặc bảo mật mật mã**.

### Tạo bộ sinh có seed và không có seed

Có thể khởi tạo với seed:

~~~java
SplittableRandom reproducible = new SplittableRandom(987654321L);
~~~

Hoặc để thư viện chọn seed ban đầu:

~~~java
SplittableRandom automaticallySeeded = new SplittableRandom();
~~~

Seed cố định hữu ích cho mô phỏng, kiểm thử và điều tra lỗi vì cùng seed, cùng cách gọi và cùng cách chia có thể tái tạo chuỗi kết quả trên cùng cách triển khai. Seed tự động hữu ích khi không cần tái lập một lần chạy cụ thể.

Không nên coi seed là bí mật hoặc cơ chế bảo mật. Người biết seed và thuật toán có thể tái tạo dãy số. Không dùng SplittableRandom để tạo mật khẩu, token phiên, mã reset, khóa hoặc nonce bảo mật.

### Một bộ sinh con nên thuộc về một tác vụ logic

Mẫu an toàn:

~~~java
SplittableRandom root = new SplittableRandom(2026L);

SplittableRandom taskA = root.split();
SplittableRandom taskB = root.split();

// Task A chỉ dùng taskA.
// Task B chỉ dùng taskB.
~~~

Mẫu không an toàn:

~~~java
SplittableRandom shared = new SplittableRandom(2026L);

// Không đưa shared vào nhiều tác vụ đồng thời.
~~~

Đừng nhầm **một bộ sinh cho mỗi thread** với **một bộ sinh cho mỗi tác vụ**. Một thread có thể thực hiện nhiều tác vụ theo thời gian; một tác vụ có thể được chuyển sang thread khác trong ForkJoinPool. Khi cần kết quả tái lập theo đơn vị công việc, gắn generator với **task/chunk có định danh ổn định**, thay vì gắn với thread vật lý.

## 3. Chia bộ sinh trước khi chạy song song

Với một số lượng tác vụ cố định, có thể tạo bộ sinh con tuần tự trước, sau đó mỗi tác vụ song song nhận đúng một bộ sinh.

~~~java
import java.util.SplittableRandom;
import java.util.stream.IntStream;

public class SplitBeforeParallel {

    static int simulate(SplittableRandom random) {
        return random.nextInt(1_000);
    }

    public static void main(String[] args) {
        int taskCount = 8;
        SplittableRandom seedSource = new SplittableRandom(2026L);
        SplittableRandom[] generators = new SplittableRandom[taskCount];

        // Chỉ thread hiện tại truy cập seedSource trong vòng lặp này.
        for (int task = 0; task < taskCount; task++) {
            generators[task] = seedSource.split();
        }

        int[] results = new int[taskCount];

        IntStream.range(0, taskCount)
                .parallel()
                .forEach(task -> {
                    // Mỗi task có generator riêng.
                    results[task] = simulate(generators[task]);
                });

        for (int task = 0; task < taskCount; task++) {
            System.out.println("Task " + task + ": " + results[task]);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~bash
javac --release 17 SplitBeforeParallel.java
java SplitBeforeParallel
~~~

Vì mỗi task ghi vào một vị trí mảng riêng, không có hai task cùng ghi một phần tử. Các generator đã được tạo xong trước khi bắt đầu stream song song và chỉ một task sử dụng từng generator. Việc kết thúc terminal operation của stream cũng bảo đảm các tác vụ đã hoàn thành trước khi đọc mảng kết quả.

Mẫu này có các đặc tính:

- Thứ tự tạo generator được xác định bởi vòng lặp tuần tự.
- Việc task nào chạy trên worker thread nào không ảnh hưởng đến generator được gắn với task index.
- Cùng seed, cùng số task, cùng thứ tự split và cùng logic sinh số có thể tái lập kết quả theo task trên cùng triển khai.
- Nếu thay đổi cách chia dữ liệu, số task hoặc số lần gọi generator, kết quả có thể thay đổi.

Không gọi split() trong lambda song song trên một root dùng chung. Chia trước giúp việc sở hữu trạng thái rõ ràng.

## 4. Ví dụ mô phỏng Monte Carlo với các generator riêng

Monte Carlo thường cần lặp lại một phép thử ngẫu nhiên rất nhiều lần. Đây là ví dụ phù hợp để chia công việc thành các chunk cố định và cấp một generator cho mỗi chunk.

Ta ước lượng π bằng cách lấy điểm ngẫu nhiên trong hình vuông [-1, 1] × [-1, 1]. Tỷ lệ điểm nằm trong đường tròn đơn vị xấp xỉ diện tích hình tròn chia diện tích hình vuông, tức π/4.

~~~java
import java.util.SplittableRandom;
import java.util.stream.IntStream;

public class ParallelMonteCarloPi {

    static long countInsideCircle(int samples, SplittableRandom random) {
        long inside = 0;

        for (int i = 0; i < samples; i++) {
            double x = 2.0 * random.nextDouble() - 1.0;
            double y = 2.0 * random.nextDouble() - 1.0;

            if (x * x + y * y <= 1.0) {
                inside++;
            }
        }

        return inside;
    }

    public static void main(String[] args) {
        long seed = 2026L;
        int taskCount = 8;
        int samplesPerTask = 250_000;

        SplittableRandom seedSource = new SplittableRandom(seed);
        SplittableRandom[] generators = new SplittableRandom[taskCount];

        for (int task = 0; task < taskCount; task++) {
            generators[task] = seedSource.split();
        }

        long[] hits = new long[taskCount];

        IntStream.range(0, taskCount)
                .parallel()
                .forEach(task -> {
                    hits[task] = countInsideCircle(
                            samplesPerTask,
                            generators[task]);
                });

        long totalHits = 0;
        for (long taskHits : hits) {
            totalHits += taskHits;
        }

        long totalSamples = (long) taskCount * samplesPerTask;
        double estimate = 4.0 * totalHits / totalSamples;

        System.out.println("Seed: " + seed);
        System.out.println("Samples: " + totalSamples);
        System.out.println("Estimated pi: " + estimate);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ParallelMonteCarloPi.java
java ParallelMonteCarloPi
~~~

Kết quả ước lượng thay đổi khi thay seed hoặc cách chia tác vụ. Với cùng seed, số tác vụ, số mẫu mỗi tác vụ và cùng cách triển khai, kết quả có thể lặp lại. Không nên mong đợi giá trị ước lượng bằng π chính xác; sai số thống kê là đặc trưng của mô phỏng Monte Carlo.

Điểm quan trọng của ví dụ không phải công thức π, mà là:

1. Root generator chỉ được dùng tuần tự để tạo generator con.
2. Mỗi chunk có một generator riêng.
3. Mỗi chunk có số mẫu xác định.
4. Mỗi chunk ghi kết quả vào vị trí riêng.
5. Việc cộng số lượng điểm bên trong đường tròn được thực hiện bằng số nguyên, tránh thêm một phép reduction double song song không cần thiết.

Nếu số task thay đổi, kết quả theo từng task cũng thay đổi vì cây split thay đổi. Nếu cần một kết quả mô phỏng tái lập xuyên nhiều mức parallelism, hãy thiết kế đơn vị công việc logic cố định, hoặc lưu seed/ID của từng chunk, không chỉ lưu số thread của máy.

## 5. Chia đệ quy trong ForkJoinTask

Với công việc chia đôi liên tục, có thể truyền generator vào từng node của cây Fork/Join. Mỗi node sở hữu generator riêng; khi tách node, nó tạo generator cho các nhánh con trước khi fork.

~~~java
import java.util.SplittableRandom;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.ForkJoinPool;

public class SplitForkJoinSum {

    static final class RandomSumTask extends RecursiveTask<Long> {
        private final int count;
        private final int threshold;
        private final SplittableRandom random;

        RandomSumTask(int count, int threshold, SplittableRandom random) {
            this.count = count;
            this.threshold = threshold;
            this.random = random;
        }

        @Override
        protected Long compute() {
            if (count <= threshold) {
                long sum = 0;
                for (int i = 0; i < count; i++) {
                    sum += random.nextInt(100);
                }
                return sum;
            }

            int leftCount = count / 2;
            int rightCount = count - leftCount;

            // Node hiện tại tạo generator cho hai node con.
            SplittableRandom leftRandom = random.split();
            SplittableRandom rightRandom = random.split();

            RandomSumTask left =
                    new RandomSumTask(leftCount, threshold, leftRandom);
            RandomSumTask right =
                    new RandomSumTask(rightCount, threshold, rightRandom);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();

            return leftResult + rightResult;
        }
    }

    public static void main(String[] args) {
        int count = 1_000_000;
        SplittableRandom root = new SplittableRandom(42L);

        long result = ForkJoinPool.commonPool().invoke(
                new RandomSumTask(count, 10_000, root));

        System.out.println(result);
    }
}
~~~

Trong ví dụ:

- Mỗi task nhận generator qua constructor.
- Một task chỉ dùng generator của chính nó.
- Trước khi tạo hai nhánh con, task cha gọi split() tuần tự để tạo hai generator.
- Sau khi đã giao generator cho child, cha không sử dụng các generator con.
- Việc worker nào chạy task nào không làm hai task chia sẻ generator.

Kết quả số nguyên ở ví dụ này phụ thuộc seed và cấu trúc chia task. Nếu thay threshold hoặc cách chia nhánh, thứ tự sinh số thay đổi và tổng cũng có thể khác. Đây là ví dụ về cách quản lý trạng thái ngẫu nhiên; không phải thuật toán tối ưu cho mọi workload. Việc tạo quá nhiều task nhỏ có overhead, nên threshold cần được chọn theo chi phí công việc.

### Quy tắc sở hữu khi chia đệ quy

~~~text
Parent task sở hữu generator P
        |
        +-- P.split() --> Generator L --> chỉ child L sử dụng
        |
        +-- P.split() --> Generator R --> chỉ child R sử dụng
~~~

Các lời gọi split() diễn ra khi parent đang sở hữu P. Sau khi chuyển L và R cho các child, không truyền cùng một generator cho hai nhánh hoặc tiếp tục sử dụng một generator ở nhiều thread.

## 6. Tái lập kết quả trong chương trình song song

Khả năng tái lập là một yêu cầu riêng, không tự động xuất hiện chỉ vì dùng seed cố định.

Để có thể tái lập một lần chạy, cần cố định ít nhất:

- Seed gốc.
- Thuật toán/bộ sinh được chọn.
- Thứ tự gọi split() và cấu trúc cây chia.
- Định danh và số lượng tác vụ logic.
- Số lần gọi generator trong mỗi tác vụ.
- Luồng điều khiển và thứ tự tiêu thụ số trong mỗi tác vụ.
- Phiên bản môi trường nếu kết quả cần so khớp qua nhiều bản JDK hoặc nhiều triển khai.

### Tái lập theo tác vụ thay vì theo thread

Giả sử có 8 chunk dữ liệu. Hãy tạo 8 generator con theo index 0 đến 7 rồi giao generator thứ i cho chunk i. Nếu ForkJoinPool chạy chunk 3 trên worker-1 hôm nay và worker-5 vào lần sau, chunk 3 vẫn dùng generator thứ 3.

Ngược lại, nếu mỗi worker thread tự giữ một generator và xử lý các chunk được scheduler giao đến, chunk nào nhận dãy nào có thể thay đổi theo lịch chạy. Cách đó có thể phù hợp khi chỉ cần throughput, nhưng không thích hợp nếu cần tái lập theo ID công việc.

### Seed gốc và seed cho từng tác vụ

Một cách dễ nhưng không nên áp dụng máy móc là tạo seed bằng phép cộng:

~~~java
long taskSeed = rootSeed + taskId;
SplittableRandom random = new SplittableRandom(taskSeed);
~~~

Cách này có thể dùng trong một số thiết kế đơn giản nếu thuật toán và miền seed được phân tích, nhưng nó không biểu đạt rõ việc chia một dòng trạng thái thành các dòng con và có thể tạo ra các quan hệ seed không mong muốn khi thiết kế mở rộng.

Nếu mục tiêu là phân chia một nguồn giả ngẫu nhiên cho các nhánh song song, hãy dùng split() của SplittableRandom hoặc một generator có khả năng split được chọn qua RandomGeneratorFactory. Không tự xây thuật toán seed-splitting nếu không có cơ sở chuyên môn và kiểm thử thống kê.

### Ghi seed để điều tra lỗi

Với mô phỏng hoặc tác vụ có thể tái chạy, ghi lại metadata cần thiết:

~~~text
algorithm = SplittableRandom
rootSeed = 2026
taskCount = 8
samplesPerTask = 250000
partitionVersion = 1
~~~

Nếu cấu trúc chia hoặc thuật toán thay đổi, tăng phiên bản partition hoặc ghi thêm thông tin để biết lần chạy nào có thể so sánh. Không ghi seed như một bí mật bảo mật; seed của mô phỏng không phải credential.

## 7. RandomGenerator trong Java 17

Java 17 bổ sung package java.util.random với giao diện RandomGenerator và hệ thống factory để làm việc với nhiều thuật toán giả ngẫu nhiên theo một API thống nhất. Các lớp Random, SplittableRandom, ThreadLocalRandom và một số bộ sinh khác có thể được dùng qua giao diện này.

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class GeneratorFactoryDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator random = factory.create(2026L);
        System.out.println(random.nextInt(100));
        System.out.println(random.nextDouble());
    }
}
~~~

Factory cho phép chọn thuật toán theo tên và khởi tạo với seed. Tên thuật toán cần tồn tại trong runtime mục tiêu. Không nên giả định mọi tên thuật toán của mọi JDK/vendor đều giống nhau ngoài những thuật toán được đặc tả bảo đảm; có thể liệt kê thuật toán đang có:

~~~java
RandomGeneratorFactory.all()
        .map(RandomGeneratorFactory::name)
        .sorted()
        .forEach(System.out::println);
~~~

### Chọn generator có khả năng split

Nếu muốn dùng một thuật toán khác SplittableRandom cho công việc song song, kiểm tra factory có hỗ trợ split trước khi dùng:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

if (!factory.isSplittable()) {
    throw new IllegalStateException("Selected generator cannot be split");
}

RandomGenerator generator = factory.create(2026L);
if (!(generator instanceof RandomGenerator.Splittable splittable)) {
    throw new IllegalStateException("Generator does not implement Splittable");
}

RandomGenerator.Splittable child = splittable.split();
int value = child.nextInt();
~~~

Pattern matching cho instanceof được hỗ trợ chính thức từ Java 16 nên ví dụ này hợp lệ trên Java 17. Kiểm tra khả năng split quan trọng vì không phải mọi RandomGenerator đều cung cấp hợp đồng tách bộ sinh. Khi viết thư viện tổng quát, nên nhận kiểu RandomGenerator.Splittable hoặc kiểm tra capability rõ ràng thay vì ép kiểu tùy tiện.

### Tách API sinh số khỏi thuật toán

Khi một phương thức chỉ cần lấy số ngẫu nhiên, có thể nhận RandomGenerator thay vì phụ thuộc trực tiếp vào một class cụ thể:

~~~java
import java.util.random.RandomGenerator;

static int chooseIndex(RandomGenerator random, int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }
    return random.nextInt(size);
}
~~~

Thiết kế này giúp test truyền generator có seed cố định và ứng dụng có thể chọn thuật toán theo yêu cầu. Nếu phương thức cần tự chia generator, kiểu tham số phải thể hiện capability đó, ví dụ RandomGenerator.Splittable.

## 8. So sánh Random, ThreadLocalRandom, SplittableRandom và RandomGenerator

| Bộ sinh / API | Sở hữu và dùng trong đa luồng | Có thể kiểm soát seed | Phù hợp |
| --- | --- | --- | --- |
| Random | Thread-safe; chia sẻ nhiều thread có thể tạo tranh chấp | Có constructor seed | Tương thích API cũ, tác vụ đơn giản hoặc chia sẻ với tải vừa phải |
| ThreadLocalRandom | Generator riêng theo thread, không cần khóa chia sẻ | Không cho ứng dụng đặt seed qua setSeed; không phù hợp tái lập theo tác vụ | Tác vụ song song cần số ngẫu nhiên nhanh và không yêu cầu seed theo job |
| SplittableRandom | Không thread-safe; tách generator rồi giao mỗi instance cho một tác vụ | Có constructor seed | Mô phỏng và tính toán song song có cấu trúc chia rõ |
| RandomGenerator | Giao diện thống nhất; đặc tính thread-safety tùy implementation | Tùy implementation/factory | Viết API không phụ thuộc một thuật toán cụ thể |
| RandomGeneratorFactory | Chọn và tạo implementation; không phải generator dùng trực tiếp | Factory hỗ trợ create(seed) | Khám phá thuật toán, kiểm tra capability và chọn generator |
| SecureRandom | Được thiết kế cho mục đích mật mã; có hợp đồng riêng | Có seed/reseed theo API/provider, nhưng không nên tự seed bằng giá trị dễ đoán | Token, nonce, khóa và dữ liệu cần tính không thể dự đoán |

### Random

Random có trạng thái và hỗ trợ dùng từ nhiều thread. Điều này giúp tránh race condition trong việc cập nhật seed, nhưng một instance dùng chung có thể bị contention. Nếu các thread cần luồng giả ngẫu nhiên độc lập cho tác vụ lớn, chia generator theo task thường rõ hơn.

### ThreadLocalRandom

ThreadLocalRandom.current() trả về bộ sinh gắn với thread hiện tại. Nó hữu ích khi tác vụ không cần truyền generator riêng và không cần tái lập chuỗi theo job. Không thể đặt seed tùy ý cho ThreadLocalRandom bằng setSeed; phương thức này không hỗ trợ việc đó.

ThreadLocalRandom gắn với thread, vì vậy cùng một tác vụ có thể nhận các giá trị khác nếu được thực thi trên thread khác hoặc thứ tự thực hiện thay đổi. Không dùng nó khi cần ánh xạ một seed cố định vào từng chunk công việc.

### SecureRandom

SecureRandom được dùng cho dữ liệu cần khó dự đoán như token xác thực hoặc giá trị mật mã. Nó không phải lựa chọn thay thế SplittableRandom cho mô phỏng song song. Không tự tạo token bằng Random, ThreadLocalRandom hoặc SplittableRandom chỉ vì các API này nhanh hơn.

## 9. Parallel stream: những mẫu nên dùng và nên tránh

### Tránh chia sẻ generator không thread-safe

~~~java
SplittableRandom shared = new SplittableRandom(10L);

IntStream.range(0, 1000)
        .parallel()
        .map(i -> shared.nextInt())
        .sum();
~~~

Không an toàn vì nhiều worker truy cập shared cùng lúc.

### Tránh split root trong lambda song song

~~~java
SplittableRandom root = new SplittableRandom(10L);

IntStream.range(0, 1000)
        .parallel()
        .map(i -> root.split().nextInt())
        .sum();
~~~

Cũng không an toàn vì root.split() được gọi đồng thời.

### Chia trước, sử dụng sau

~~~java
int taskCount = 16;
SplittableRandom root = new SplittableRandom(10L);
SplittableRandom[] randoms = new SplittableRandom[taskCount];

for (int i = 0; i < taskCount; i++) {
    randoms[i] = root.split();
}

int[] values = new int[taskCount];
IntStream.range(0, taskCount).parallel().forEach(i -> {
    values[i] = randoms[i].nextInt(100);
});
~~~

Mỗi generator được một task index sở hữu. Nếu mỗi task cần nhiều lần gọi, có thể thực hiện tất cả trong cùng lambda/task, không chia sẻ generator sang task khác.

### Khi nào ThreadLocalRandom là đủ?

Nếu chỉ cần xử lý mỗi phần tử bằng một giá trị ngẫu nhiên, không cần tái lập theo phần tử hoặc chunk:

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.IntStream;

IntStream.range(0, 100_000)
        .parallel()
        .forEach(i -> {
            int sample = ThreadLocalRandom.current().nextInt(100);
            process(i, sample);
        });
~~~

ThreadLocalRandom là lựa chọn thuận tiện cho kiểu công việc này. Tuy nhiên, không thể chỉ truyền seed rồi mong mỗi lần chạy tạo đúng cùng sample cho từng i. Nếu tính tái lập theo ID tác vụ là yêu cầu, hãy cấp generator theo ID thay vì thread.

## 10. Thứ tự gộp kết quả cũng có thể ảnh hưởng đến tính tái lập

Chia generator đúng mới giải quyết phần sinh số. Phần tổng hợp kết quả cũng cần xem xét.

Nếu mỗi task tạo số nguyên đếm được, cộng các kết quả long thường có tính kết hợp về mặt số học trong miền không overflow. Nếu mỗi task tạo tổng double, cách gộp kết quả có thể khác theo cấu trúc reduction và làm thay đổi các bit cuối.

Ví dụ:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Với mô phỏng, có thể lưu số lượng hit dưới dạng long rồi cộng tuần tự hoặc dùng một cách tổng hợp có thứ tự cố định. Nếu phải tổng hợp các giá trị double, hãy xác định sai số chấp nhận và thuật toán cộng phù hợp. Tái lập chuỗi random không đồng nghĩa với kết quả số học cuối cùng luôn giống nhau nếu phép reduction thay đổi thứ tự.

## 11. Kiểm thử chiến lược chia generator

Kiểm thử nên xác nhận **cấu trúc sở hữu và khả năng tái lập**, không cố chứng minh tính độc lập thống kê bằng một vài lần chạy.

### Kiểm tra tái lập với cùng seed và cùng thứ tự split

~~~java
import java.util.SplittableRandom;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SplitRandomTest {
    @Test
    void sameSeedAndSameSplitOrderReproduceTaskSequences() {
        long seed = 2026L;
        int taskCount = 4;
        int valuesPerTask = 10;

        SplittableRandom rootA = new SplittableRandom(seed);
        SplittableRandom rootB = new SplittableRandom(seed);

        for (int task = 0; task < taskCount; task++) {
            SplittableRandom a = rootA.split();
            SplittableRandom b = rootB.split();

            for (int i = 0; i < valuesPerTask; i++) {
                assertEquals(a.nextInt(), b.nextInt());
            }
        }
    }
}
~~~

Test này xác nhận hai lần khởi tạo cùng seed, cùng thứ tự split và cùng số lần gọi tạo chuỗi giống nhau trên implementation đang chạy. Nó không chứng minh các stream độc lập về mặt thống kê.

### Kiểm tra kết quả theo task index

Có thể viết một hàm chạy cố định số task, cấp generator theo index và trả mảng kết quả. Chạy hàm hai lần với cùng seed và cấu hình rồi so sánh mảng. Điều này giúp phát hiện việc vô tình dùng chung generator hoặc thay đổi thứ tự cấp phát.

### Kiểm tra phân phối thống kê

Nếu thuật toán được dùng cho mô phỏng, cần xem xét:

- Trung bình, phương sai và tỷ lệ xuất hiện trong khoảng dự kiến.
- Các bucket/nhóm giá trị có phân phối hợp lý.
- Tính tương quan giữa các dãy con trong những workload đại diện.
- Các kiểm thử thống kê phù hợp với thuật toán và ứng dụng.

Một test kiểu assertNotEquals(sequenceA, sequenceB) không chứng minh chất lượng ngẫu nhiên. Hai chuỗi khác nhau vẫn có thể có phân phối kém, tương quan cao hoặc lộ quy luật. Kiểm thử thống kê có ý nghĩa hơn khi có tiêu chí, kích thước mẫu và mức chấp nhận được xác định trước.

### Không dùng test ngẫu nhiên không có seed khi cần tái hiện lỗi

Khi test phát hiện lỗi ở một lần chạy, hãy ghi lại seed và metadata chia task. Một test không lưu seed có thể khó tái hiện lỗi khi chạy lại. Ngược lại, test với seed cố định chỉ kiểm tra một đường dữ liệu; vẫn cần nhiều seed hoặc dữ liệu biên khi mục tiêu là khảo sát độ bền.

## 12. Các lỗi thường gặp khi chia bộ sinh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chia sẻ một SplittableRandom giữa nhiều thread | Race condition vì class không thread-safe | Split trước khi chạy song song; một child cho một task |
| Gọi split() trên root trong parallel lambda | Nhiều thread cùng truy cập root | Chia ở thread sở hữu root rồi giao child |
| Tạo generator theo worker thread khi cần tái lập theo task | Chunk có thể nhận dãy khác khi scheduler thay đổi | Gắn generator với task/chunk ID ổn định |
| Dùng seed + taskId một cách tùy tiện | Không có thiết kế phân tách stream rõ ràng | Dùng split hoặc thuật toán được thiết kế cho mục đích |
| Tưởng cùng seed đảm bảo cùng kết quả khi đổi partition | Cây split và số lần tiêu thụ thay đổi | Cố định task graph hoặc lưu seed theo chunk |
| Dùng SplittableRandom cho token bảo mật | Dãy có thể dự đoán nếu biết seed/trạng thái | Dùng SecureRandom |
| Dùng ThreadLocalRandom khi cần replay | Không kiểm soát seed theo tác vụ | Dùng SplittableRandom hoặc generator seeded |
| Chỉ kiểm tra hai chuỗi khác nhau để kết luận độc lập | Không kiểm chứng chất lượng thống kê | Dùng đánh giá thống kê phù hợp |
| Dùng Random dùng chung cho workload lớn | Contention trên trạng thái chung | Chọn generator per-task hoặc per-thread theo yêu cầu |
| Tạo quá nhiều task và generator nhỏ | Overhead tạo task/split lớn hơn phần tính toán | Chọn chunk size/threshold phù hợp |
| Gộp double song song rồi kỳ vọng bit giống nhau | Thứ tự reduction có thể thay đổi kết quả | Cố định thứ tự hoặc chọn thuật toán sai số phù hợp |

## 13. Hướng dẫn lựa chọn theo yêu cầu

| Nhu cầu | Lựa chọn gợi ý |
| --- | --- |
| Mô phỏng song song, muốn seed và chia dãy rõ ràng | SplittableRandom, một child cho mỗi task |
| Công việc Fork/Join chia đệ quy | Truyền generator vào task; split tại node cha trước khi fork |
| Parallel stream, cần kết quả theo chunk có thể tái lập | Chia generator tuần tự theo chunk ID, rồi chạy các chunk song song |
| Parallel stream, chỉ cần số ngẫu nhiên nhanh, không cần replay theo task | ThreadLocalRandom.current() |
| API thư viện muốn nhận nhiều thuật toán | RandomGenerator |
| Chọn thuật toán theo tên/capability ở Java 17 | RandomGeneratorFactory |
| Token, nonce hoặc bí mật cần khó dự đoán | SecureRandom |

## 14. Nguyên tắc thiết kế

Khi chia bộ sinh cho tác vụ song song trong Java 17:

1. Chọn bộ sinh phù hợp với mục tiêu: mô phỏng, throughput hay bảo mật.
2. Không chia sẻ một SplittableRandom giữa nhiều thread.
3. Thực hiện split() khi generator cha đang được một luồng sở hữu; sau đó giao mỗi child cho một task riêng.
4. Gắn generator với **đơn vị công việc logic** nếu cần tái lập theo task, không chỉ với worker thread.
5. Cố định seed, cấu trúc chia, số lần gọi và partition nếu cần tái hiện kết quả.
6. Dùng RandomGenerator để trừu tượng hóa API; kiểm tra capability trước khi yêu cầu split.
7. Kiểm thử tái lập và chất lượng thống kê theo tiêu chí riêng; hai việc này không thay thế nhau.
8. Xem xét thứ tự tổng hợp kết quả, nhất là khi reduction dùng float/double.

SplittableRandom giải quyết tốt bài toán phân chia trạng thái giả ngẫu nhiên cho tính toán song song khi mỗi tác vụ được sở hữu một generator riêng. RandomGenerator và RandomGeneratorFactory giúp thiết kế linh hoạt hơn trên Java 17. Quan trọng nhất là xác định rõ **ai sở hữu generator, khi nào generator được split và đơn vị nào tiêu thụ dãy số**; từ đó chương trình vừa tránh tranh chấp vừa dễ kiểm soát tính tái lập.
