# Mô phỏng có thể tái hiện bằng RandomGenerator trong Java 17

## 1. Vì sao mô phỏng cần tái hiện được?

Mô phỏng thường dùng số ngẫu nhiên để biểu diễn những yếu tố không chắc chắn: thời gian đến của khách hàng, thời gian phục vụ, nhu cầu mua hàng, lỗi thiết bị, kết quả thí nghiệm hoặc vị trí điểm trong một không gian. Một lần chạy tạo ra một kịch bản; lần chạy khác có thể tạo ra kịch bản khác.

Trong phát triển phần mềm, việc có thể **tái hiện đúng một lần chạy** rất quan trọng:

- Khi một mô phỏng cho kết quả bất thường, nhóm phát triển cần chạy lại đúng kịch bản để tìm nguyên nhân.
- Khi sửa thuật toán, cần so sánh phiên bản cũ và mới trên cùng dữ liệu ngẫu nhiên.
- Khi chạy benchmark, cần tách ảnh hưởng của thay đổi mã khỏi biến động do dữ liệu đầu vào.
- Khi chia mô phỏng thành nhiều tác vụ song song, cần biết mỗi tác vụ dùng chuỗi số ngẫu nhiên nào.
- Khi lưu kết quả nghiên cứu hoặc báo cáo, cần ghi đủ thông tin để người khác tái tạo thí nghiệm.

Một bộ sinh số giả ngẫu nhiên (*pseudorandom number generator*, PRNG) có trạng thái nội bộ và thuật toán xác định. Nếu tạo generator với cùng thuật toán, cùng seed và gọi các phương thức theo cùng thứ tự, chương trình có thể tạo lại cùng chuỗi kết quả.

Java 17 cung cấp API mới trong package `java.util.random`, với interface trung tâm là `RandomGenerator`. API này cho phép viết mô phỏng độc lập với lớp generator cụ thể, đồng thời chọn thuật toán thông qua `RandomGeneratorFactory`.

## 2. RandomGenerator trong Java 17

### 2.1. Interface thống nhất cho nhiều bộ sinh

`RandomGenerator` là interface mô tả các thao tác sinh giá trị ngẫu nhiên. Nhiều lớp có sẵn trong Java triển khai interface này, bao gồm:

| Generator | Đặc điểm |
|---|---|
| `java.util.Random` | Generator lâu đời, có hợp đồng chuỗi số được xác định rõ theo seed. |
| `java.util.SplittableRandom` | Phù hợp với các tác vụ tính toán cần tách generator cho từng nhánh hoặc tác vụ. |
| Các generator LXM | Nhóm thuật toán hiện đại được cung cấp qua RandomGeneratorFactory. |
| `java.util.concurrent.ThreadLocalRandom` | Generator gắn với thread, hữu ích cho tính toán đồng thời nhưng không phù hợp làm nguồn seed tái hiện theo cách thông thường. |
| `java.security.SecureRandom` | Dành cho mục đích bảo mật; không phải lựa chọn mặc định cho mô phỏng khoa học hoặc benchmark. |

Thay vì viết phương thức chỉ nhận `Random`, hãy nhận `RandomGenerator` nếu mã chỉ cần các thao tác chung:

~~~java
static double estimateSomething(RandomGenerator random) {
    return random.nextDouble();
}
~~~

Nhờ đó, cùng một thuật toán mô phỏng có thể dùng `Random`, `SplittableRandom` hoặc một generator LXM mà không cần thay đổi logic mô phỏng.

### 2.2. Các phương thức thường dùng

| Phương thức | Miền giá trị hoặc phân phối |
|---|---|
| `nextBoolean()` | Boolean ngẫu nhiên. |
| `nextInt()` | Số nguyên 32 bit. |
| `nextInt(bound)` | Số nguyên trong khoảng từ 0 đến bound, không gồm bound. |
| `nextInt(origin, bound)` | Số nguyên từ origin, gồm origin, tới bound, không gồm bound. |
| `nextLong()` | Số nguyên 64 bit. |
| `nextLong(bound)` | Số nguyên từ 0 đến bound, không gồm bound. |
| `nextDouble()` | Số thực trong khoảng [0, 1). |
| `nextDouble(origin, bound)` | Số thực trong khoảng [origin, bound). |
| `nextGaussian()` | Giá trị theo phân phối chuẩn có trung bình 0 và độ lệch chuẩn 1. |
| `nextGaussian(mean, stddev)` | Giá trị theo phân phối chuẩn với trung bình và độ lệch chuẩn chỉ định. |
| `nextExponential()` | Giá trị theo phân phối mũ với trung bình 1. |

Các phương thức có khoảng giới hạn giúp tránh tự viết phép chia dư hoặc cộng trừ thủ công dễ gây sai lệch. Ví dụ, dùng `nextInt(10, 21)` để sinh số nguyên từ 10 đến 20.

### 2.3. Chọn generator qua RandomGeneratorFactory

`RandomGeneratorFactory` cho phép tìm và tạo generator theo tên thuật toán:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

String algorithm = "L64X128MixRandom";
long seed = 20250317L;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of(algorithm);

RandomGenerator random = factory.create(seed);

System.out.println(random.nextInt());
System.out.println(random.nextDouble());
~~~

Tên thuật toán là một phần của cấu hình mô phỏng. Khi cần tái hiện kết quả, hãy lưu cả tên thuật toán và seed; chỉ lưu seed là chưa đủ nếu lần chạy sau chọn generator khác.

Có thể liệt kê các factory mà runtime cung cấp:

~~~java
RandomGeneratorFactory.all()
        .sorted((left, right) -> left.name().compareTo(right.name()))
        .forEach(factory -> System.out.printf(
                "%s | group=%s | stateBits=%d | splittable=%s%n",
                factory.name(),
                factory.group(),
                factory.stateBits(),
                factory.isSplittable()));
~~~

Danh sách thuật toán phụ thuộc JDK/runtime đang chạy. Hãy dùng `RandomGeneratorFactory.all()` hoặc `factory.name()` để khám phá thay vì giả định mọi vendor đều cung cấp cùng một tập thuật toán.

### 2.4. Không phụ thuộc vào generator mặc định

`RandomGenerator.getDefault()` cung cấp generator mặc định của runtime. Cách này tiện cho ứng dụng không cần kiểm soát thuật toán, nhưng không phù hợp khi kết quả mô phỏng phải được tái hiện lâu dài.

Nếu runtime thay đổi lựa chọn generator mặc định giữa các phiên bản, cùng một seed có thể tạo chuỗi khác. Khi cần reproducibility, hãy chọn tên thuật toán rõ ràng bằng `RandomGeneratorFactory.of(name)`.

## 3. Seed và khả năng tái hiện

### 3.1. Seed là điểm bắt đầu của chuỗi giả ngẫu nhiên

Seed là giá trị khởi tạo trạng thái của generator. Với một thuật toán xác định, seed cố định tạo ra chuỗi số có thể tái tạo:

~~~java
RandomGenerator first =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(123456789L);

RandomGenerator second =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(123456789L);

System.out.println(first.nextInt() == second.nextInt());
System.out.println(first.nextDouble() == second.nextDouble());
~~~

Hai generator bắt đầu từ cùng trạng thái. Vì các lời gọi được thực hiện cùng thứ tự, hai phép so sánh sẽ cho kết quả `true`.

Nếu thay seed của generator thứ hai hoặc đổi thuật toán, chuỗi có thể khác.

### 3.2. Ghi seed vào kết quả mô phỏng

Một kết quả mô phỏng nên lưu metadata đủ để chạy lại:

| Metadata | Vì sao cần |
|---|---|
| Algorithm name | Xác định loại PRNG. |
| Seed | Tái tạo trạng thái ban đầu. |
| JDK vendor/version/build | Xác định runtime và implementation đã dùng. |
| Simulation version hoặc commit | Xác định logic mô phỏng. |
| Input parameters | Xác định kích thước mẫu, phân phối, hệ số và điều kiện ban đầu. |
| Input data version | Đảm bảo dữ liệu nền không thay đổi. |
| Parallelism/stream assignment | Xác định cách chia chuỗi ngẫu nhiên giữa các tác vụ. |

Ví dụ metadata có thể lưu trong JSON, CSV header hoặc log:

~~~text
algorithm=L64X128MixRandom
seed=20250317
jdk=17.0.x
simulation=queue-model-v3
arrivalRate=2.0
serviceRate=3.0
warmupCustomers=10000
measuredCustomers=200000
~~~

Không nên ghi một chuỗi chung như `random=true`. Nó không cho biết cách tạo lại kịch bản.

### 3.3. Seed cố định và seed được tạo mới

Trong phát triển và kiểm thử, dùng seed cố định:

~~~java
long seed = 20250317L;
~~~

Trong một lần chạy production cần tạo kịch bản mới, có thể tạo seed ngẫu nhiên một lần, sau đó ghi seed ra log hoặc metadata:

~~~java
long seed = new java.security.SecureRandom().nextLong();
System.out.println("simulationSeed=" + seed);
~~~

`SecureRandom` ở đây chỉ được dùng để chọn seed ban đầu. Generator mô phỏng vẫn là PRNG được chọn qua `RandomGeneratorFactory`. Nếu kết quả có vấn đề, lấy seed đã ghi để chạy lại.

Không dùng `System.nanoTime()` làm seed mà không lưu lại. Seed không được ghi nhận sẽ làm mất khả năng tái hiện.

### 3.4. Cùng seed chưa đủ nếu thứ tự lời gọi thay đổi

Generator tạo chuỗi tuần tự. Mỗi lần gọi phương thức sẽ tiêu thụ một phần trạng thái. Vì vậy, hai phiên bản mô phỏng có thể khác kết quả dù dùng cùng thuật toán và seed nếu:

- Một phiên bản thêm lời gọi `nextDouble()` để log hoặc kiểm tra.
- Thứ tự sinh biến ngẫu nhiên bị thay đổi.
- Một nhánh điều kiện tiêu thụ số ngẫu nhiên khác trước.
- Số lượng vòng lặp hoặc thứ tự xử lý input thay đổi.
- Một phép tính song song làm thay đổi cách phân phối generator cho tác vụ.

Hãy coi thứ tự tiêu thụ chuỗi ngẫu nhiên là một phần của cấu hình thí nghiệm.

### 3.5. Tái hiện qua nhiều phiên bản JDK

API `RandomGenerator` cung cấp cách chọn thuật toán, nhưng không nên tự giả định mọi thuật toán đều có cam kết giống hệt `java.util.Random` về chuỗi bit qua mọi phiên bản và vendor tương lai. Với kết quả cần lưu trữ lâu dài:

- Ghi chính xác tên thuật toán.
- Ghi JDK vendor, version và build.
- Giữ lại cấu hình và phiên bản code mô phỏng.
- Nếu cần tái hiện chính xác trong tương lai xa, cân nhắc lưu input random đã sinh hoặc lưu checkpoint/state theo cơ chế do ứng dụng quản lý.

`java.util.Random` có hợp đồng tương thích chuỗi được xác định rõ cho cùng seed và cùng chuỗi lời gọi. Các generator mới nên được dùng với runtime đã được pin và kiểm chứng khi yêu cầu tái hiện vượt qua ranh giới phiên bản.

## 4. Sinh các phân phối thường gặp

Mô phỏng không chỉ cần số ngẫu nhiên đều. Mỗi đại lượng cần dùng một phân phối phù hợp với mô hình.

### 4.1. Phân phối đều trên số nguyên

Để chọn ngẫu nhiên một chỉ số từ 0 đến n-1:

~~~java
int index = random.nextInt(n);
~~~

Để chọn số nguyên trong khoảng [min, max]:

~~~java
int value = random.nextInt(min, max + 1);
~~~

Ví dụ thứ hai chỉ an toàn nếu `max + 1` không tràn số nguyên và khoảng hợp lệ. Nếu làm việc gần giới hạn kiểu dữ liệu, dùng `long` hoặc kiểm tra biên trước.

Không dùng:

~~~java
int value = Math.abs(random.nextInt()) % n;
~~~

Cách này có hai vấn đề: `Math.abs(Integer.MIN_VALUE)` vẫn âm và phép modulo có thể tạo phân phối lệch khi số lượng giá trị nguồn không chia hết cho n. Hãy dùng `nextInt(bound)`.

### 4.2. Phân phối đều trên số thực

`nextDouble()` trả về số trong [0, 1):

~~~java
double u = random.nextDouble();
double x = min + (max - min) * u;
~~~

Có thể dùng trực tiếp:

~~~java
double x = random.nextDouble(min, max);
~~~

Giá trị max không được bao gồm. Khi xây dựng mô hình, hãy xác định rõ khoảng đóng/mở để tránh sai lệch ở biên.

### 4.3. Bernoulli: sự kiện có xác suất p

Ví dụ mô phỏng một request bị lỗi với xác suất p:

~~~java
static boolean failed(RandomGenerator random, double probability) {
    if (!Double.isFinite(probability)
            || probability < 0.0
            || probability > 1.0) {
        throw new IllegalArgumentException(
                "probability must be in [0, 1]");
    }
    return random.nextDouble() < probability;
}
~~~

Khi p bằng 0, sự kiện không bao giờ xảy ra; khi p bằng 1, sự kiện luôn xảy ra. Với p ở giữa, số lần xảy ra trong một mẫu chỉ tiến gần tỷ lệ kỳ vọng khi kích thước mẫu đủ lớn; không nên yêu cầu số lần chính xác bằng p nhân số mẫu trong mọi lần chạy.

### 4.4. Phân phối chuẩn

Dùng `nextGaussian(mean, stddev)`:

~~~java
double temperature = random.nextGaussian(25.0, 2.5);
~~~

Giá trị được sinh theo phân phối chuẩn với trung bình 25 và độ lệch chuẩn 2,5. Phân phối chuẩn không bị chặn; nếu đại lượng thực tế không thể âm hoặc không thể vượt một ngưỡng, hãy chọn mô hình phù hợp hơn hoặc áp dụng phép biến đổi có cơ sở thống kê.

### 4.5. Phân phối mũ

`nextExponential()` sinh giá trị theo phân phối mũ có trung bình 1. Nếu sự kiện có tốc độ trung bình λ sự kiện trên một đơn vị thời gian, thời gian giữa hai sự kiện có thể mô hình hóa bằng:

~~~java
double interArrivalTime = random.nextExponential() / lambda;
~~~

Giá trị kỳ vọng là 1/λ. Tham số λ phải dương và hữu hạn. Phân phối mũ thường dùng để mô hình hóa thời gian giữa các sự kiện trong quá trình Poisson hoặc thời gian phục vụ trong mô hình M/M/1 đơn giản.

### 4.6. Chọn phần tử theo trọng số

Giả sử có ba loại request với trọng số 0,6; 0,3; 0,1. Có thể dùng cumulative weight:

~~~java
static int chooseWeighted(
        RandomGenerator random, double[] weights) {

    double total = 0.0;
    for (double weight : weights) {
        if (!Double.isFinite(weight) || weight < 0.0) {
            throw new IllegalArgumentException(
                    "weights must be finite and non-negative");
        }
        total += weight;
    }
    if (!(total > 0.0) || !Double.isFinite(total)) {
        throw new IllegalArgumentException(
                "sum of weights must be positive and finite");
    }

    double target = random.nextDouble() * total;
    double cumulative = 0.0;
    for (int i = 0; i < weights.length; i++) {
        cumulative += weights[i];
        if (target < cumulative) {
            return i;
        }
    }
    return weights.length - 1;
}
~~~

Các trọng số không bắt buộc phải cộng thành 1; hàm chuẩn hóa bằng tổng trọng số. Phần tử có trọng số 0 sẽ không được chọn nếu tổng hợp lệ.

## 5. Ví dụ Monte Carlo: ước lượng số Pi

Monte Carlo dùng lấy mẫu ngẫu nhiên để ước lượng một đại lượng. Ta chọn ngẫu nhiên các điểm trong hình vuông [-1, 1] × [-1, 1]. Tỷ lệ điểm nằm trong đường tròn bán kính 1 xấp xỉ diện tích hình tròn chia cho diện tích hình vuông:

~~~text
N_inside / N_total ≈ π / 4
π ≈ 4 * N_inside / N_total
~~~

Mã Java:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public final class PiSimulation {
    private PiSimulation() {
    }

    record Result(
            String algorithm,
            long seed,
            long samples,
            long inside,
            double estimate) {
    }

    static Result estimate(long seed, long samples) {
        if (samples <= 0) {
            throw new IllegalArgumentException(
                    "samples must be positive");
        }

        String algorithm = "L64X128MixRandom";
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of(algorithm);
        RandomGenerator random = factory.create(seed);

        long inside = 0;
        for (long i = 0; i < samples; i++) {
            double x = random.nextDouble(-1.0, 1.0);
            double y = random.nextDouble(-1.0, 1.0);
            if (x * x + y * y <= 1.0) {
                inside++;
            }
        }

        double estimate = 4.0 * inside / samples;
        return new Result(
                algorithm, seed, samples, inside, estimate);
    }

    public static void main(String[] args) {
        long seed = 20250317L;
        long samples = 1_000_000L;

        Result result = estimate(seed, samples);
        System.out.println("algorithm=" + result.algorithm());
        System.out.println("seed=" + result.seed());
        System.out.println("samples=" + result.samples());
        System.out.println("inside=" + result.inside());
        System.out.println("piEstimate=" + result.estimate());
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~text
javac --release 17 -encoding UTF-8 PiSimulation.java
java PiSimulation
~~~

Chạy lại cùng chương trình với cùng seed và số mẫu sẽ tái tạo cùng kết quả trong cùng môi trường thuật toán/runtime. Thay seed tạo một lần lấy mẫu khác. Tăng số mẫu thường làm giảm sai số thống kê, nhưng không bảo đảm mọi lần chạy đều gần π hơn một cách đơn điệu.

### 5.1. Vì sao lưu cả số mẫu?

Seed xác định chuỗi PRNG ban đầu, nhưng số mẫu quyết định bao nhiêu phần tử của chuỗi được dùng. Hai lần chạy cùng seed nhưng một lần dùng 100.000 mẫu và lần kia dùng 1.000.000 mẫu sẽ có kết quả khác.

Khi lưu kết quả, hãy ghi seed, algorithm và số mẫu. Nếu có thêm warm-up hoặc bỏ mẫu đầu, cũng cần lưu các tham số đó.

## 6. Ví dụ mô phỏng hàng đợi M/M/1

Một ví dụ thực tế hơn là mô phỏng một quầy phục vụ:

- Khách đến theo quá trình Poisson với tốc độ λ khách mỗi đơn vị thời gian.
- Thời gian phục vụ tuân theo phân phối mũ với tốc độ μ.
- Chỉ có một nhân viên phục vụ.
- Nếu nhân viên bận, khách chờ trong hàng đợi.

Để hàng đợi ổn định về mặt lý thuyết, cần λ < μ. Với mô hình M/M/1, thời gian chờ trung bình trong hàng đợi ở trạng thái ổn định có giá trị lý thuyết:

~~~text
Wq = λ / (μ * (μ - λ))
W  = 1 / (μ - λ)
~~~

Mô phỏng không nên bắt đầu đo ngay từ khách đầu tiên vì hệ thống ban đầu rỗng. Ta dùng một số khách warm-up để đưa trạng thái hàng đợi gần trạng thái ổn định, sau đó mới thu thập thống kê.

~~~java
import java.util.random.RandomGenerator;
import java.util.SplittableRandom;

public final class QueueSimulation {
    private QueueSimulation() {
    }

    record Result(
            long customers,
            double averageWait,
            double averageTimeInSystem) {
    }

    static Result simulate(
            RandomGenerator arrivals,
            RandomGenerator services,
            long warmupCustomers,
            long measuredCustomers,
            double arrivalRate,
            double serviceRate) {

        if (warmupCustomers < 0 || measuredCustomers <= 0) {
            throw new IllegalArgumentException(
                    "invalid customer counts");
        }
        if (!Double.isFinite(arrivalRate)
                || !Double.isFinite(serviceRate)
                || arrivalRate <= 0.0
                || serviceRate <= arrivalRate) {
            throw new IllegalArgumentException(
                    "require 0 < arrivalRate < serviceRate");
        }

        long totalCustomers =
                Math.addExact(warmupCustomers, measuredCustomers);
        double arrivalTime = 0.0;
        double serverAvailableAt = 0.0;
        double totalWait = 0.0;
        double totalTimeInSystem = 0.0;

        for (long i = 0; i < totalCustomers; i++) {
            arrivalTime += arrivals.nextExponential() / arrivalRate;
            double serviceTime =
                    services.nextExponential() / serviceRate;

            double serviceStartsAt =
                    Math.max(arrivalTime, serverAvailableAt);
            double departsAt = serviceStartsAt + serviceTime;

            if (i >= warmupCustomers) {
                totalWait += serviceStartsAt - arrivalTime;
                totalTimeInSystem += departsAt - arrivalTime;
            }

            serverAvailableAt = departsAt;
        }

        return new Result(
                measuredCustomers,
                totalWait / measuredCustomers,
                totalTimeInSystem / measuredCustomers);
    }

    public static void main(String[] args) {
        long seed = 987654321L;

        // Hai stream riêng giúp tách chuỗi arrival và service.
        SplittableRandom root = new SplittableRandom(seed);
        RandomGenerator arrivalRandom = root.split();
        RandomGenerator serviceRandom = root.split();

        double lambda = 2.0;
        double mu = 3.0;

        Result result = simulate(
                arrivalRandom,
                serviceRandom,
                10_000,
                200_000,
                lambda,
                mu);

        double theoreticalWait =
                lambda / (mu * (mu - lambda));
        double theoreticalSystemTime =
                1.0 / (mu - lambda);

        System.out.println("seed=" + seed);
        System.out.println("customers=" + result.customers());
        System.out.println("averageWait=" + result.averageWait());
        System.out.println("theoreticalWait=" + theoreticalWait);
        System.out.println("averageTimeInSystem="
                + result.averageTimeInSystem());
        System.out.println("theoreticalTimeInSystem="
                + theoreticalSystemTime);
    }
}
~~~

Hai generator con được tạo theo thứ tự cố định từ root `SplittableRandom`. Một stream sinh thời gian đến, stream còn lại sinh thời gian phục vụ. Điều này giúp tách hai nguồn biến ngẫu nhiên: nếu thay đổi số lần lấy mẫu thời gian đến, chuỗi thời gian phục vụ không bị dịch chuyển theo.

Với cùng seed, cùng thứ tự split, cùng số khách và cùng tham số, mô phỏng có thể được tái hiện. Kết quả thực nghiệm chỉ tiến gần công thức lý thuyết khi số mẫu đủ lớn; sai khác nhỏ là bình thường.

## 7. Tách generator cho mô phỏng song song

### 7.1. Vì sao không nên chia sẻ một generator tùy ý giữa nhiều thread?

Một generator có trạng thái thay đổi sau mỗi lần gọi. Nếu nhiều thread cùng truy cập một generator:

- Thứ tự gọi có thể phụ thuộc lịch lập lịch thread.
- Chuỗi số được tiêu thụ bởi từng tác vụ có thể thay đổi giữa các lần chạy.
- Một số generator không được thiết kế để chia sẻ đồng thời.
- Chi phí đồng bộ hoặc contention có thể làm giảm hiệu năng.

Với mô phỏng song song, nên tạo một generator cho từng tác vụ hoặc từng replication. Khi mỗi tác vụ có stream riêng, lịch chạy thread không quyết định task nào tiêu thụ số ngẫu nhiên tiếp theo của task khác.

### 7.2. SplittableGenerator

`RandomGenerator.SplittableGenerator` là subinterface dành cho generator có thể tách thành các generator con:

~~~java
SplittableRandom root = new SplittableRandom(12345L);

RandomGenerator firstTask = root.split();
RandomGenerator secondTask = root.split();
~~~

Mỗi lời gọi `split()` tạo generator con có chuỗi riêng. Đây là cách phù hợp để phân phối stream cho các tác vụ độc lập, đặc biệt khi dùng parallel stream hoặc executor.

Không phải mọi `RandomGenerator` đều splittable. Có thể kiểm tra khả năng này bằng `RandomGeneratorFactory.isSplittable()` trước khi ép kiểu sang `SplittableGenerator`.

### 7.3. Gán stream theo ID tác vụ, không theo thread

Một lỗi thường gặp là tạo generator mới bên trong mỗi thread bằng seed phụ thuộc thứ tự thread được tạo. Thứ tự thread có thể thay đổi, làm kết quả mô phỏng không tái hiện.

Hãy gán generator cho **logical task ID** trước khi đưa tác vụ vào executor:

1. Tạo root generator bằng seed đã ghi.
2. Tạo các generator con theo thứ tự replication cố định.
3. Gắn generator con thứ i với replication i.
4. Chạy replication trên executor/parallel stream.
5. Lưu kết quả theo task ID, sau đó tổng hợp theo thứ tự cố định.

### 7.4. Ví dụ chạy các replication song song nhưng có thể tái hiện

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;
import java.util.stream.IntStream;

public final class ParallelMonteCarlo {
    private ParallelMonteCarlo() {
    }

    static long countInside(
            RandomGenerator random, long samples) {
        long inside = 0;
        for (long i = 0; i < samples; i++) {
            double x = random.nextDouble(-1.0, 1.0);
            double y = random.nextDouble(-1.0, 1.0);
            if (x * x + y * y <= 1.0) {
                inside++;
            }
        }
        return inside;
    }

    public static void main(String[] args) {
        long seed = 445566L;
        int replications = 8;
        long samplesPerReplication = 500_000L;

        SplittableRandom root = new SplittableRandom(seed);
        List<RandomGenerator> streams =
                new ArrayList<>(replications);

        // Tạo stream tuần tự trước khi chạy song song.
        for (int i = 0; i < replications; i++) {
            streams.add(root.split());
        }

        long[] counts = new long[replications];
        IntStream.range(0, replications).parallel().forEach(index -> {
            counts[index] = countInside(
                    streams.get(index), samplesPerReplication);
        });

        // Tổng hợp tuần tự theo index cố định.
        long totalInside = 0;
        long totalSamples = 0;
        for (int i = 0; i < replications; i++) {
            totalInside += counts[i];
            totalSamples += samplesPerReplication;
        }

        double pi = 4.0 * totalInside / totalSamples;
        System.out.println("seed=" + seed);
        System.out.println("replications=" + replications);
        System.out.println("piEstimate=" + pi);
    }
}
~~~

Mỗi replication chỉ ghi vào một phần tử riêng của mảng `counts`; kết quả được tổng hợp sau khi parallel stream hoàn tất. Việc tạo stream trước và gắn theo index giúp kết quả không phụ thuộc thứ tự thread nhận tác vụ.

Với số nguyên trong ví dụ, tổng theo thứ tự khác nhau không đổi nếu không tràn. Với tổng số thực, thứ tự cộng có thể làm thay đổi vài bit do sai số dấu phẩy động. Hãy lưu kết quả từng replication rồi cộng tuần tự nếu cần tái hiện chặt chẽ.

### 7.5. Reproducibility song song có điều kiện

Việc tách generator giúp ổn định chuỗi ngẫu nhiên theo task, nhưng vẫn cần cố định:

- Số lượng replication.
- Thứ tự tạo/split stream.
- Cách gán stream cho task ID.
- Số mẫu trong từng replication.
- Thuật toán và seed của root.
- Cách tổng hợp kết quả.

Nếu thay đổi số worker thread nhưng vẫn giữ mapping task ID → stream và logic mỗi task không đổi, kết quả từng replication có thể giữ nguyên. Nếu tạo stream theo worker thread hoặc thay đổi cách chia batch, kết quả có thể khác.

## 8. Jumpable và Leapable generator

Ngoài generator có thể split, Java 17 mô tả các khả năng điều khiển stream khác qua những subinterface:

- `RandomGenerator.JumpableGenerator` hỗ trợ nhảy tiến trong chuỗi trạng thái.
- `RandomGenerator.LeapableGenerator` hỗ trợ bước nhảy lớn hơn, hữu ích khi cần phân vùng chuỗi.
- `RandomGenerator.ArbitrarilyJumpableGenerator` hỗ trợ các bước nhảy với khoảng cách được chọn theo API.

Các khả năng này phục vụ những cách phân chia stream khác nhau. Chúng không phải yêu cầu bắt buộc cho mọi mô phỏng. Nếu mô phỏng chỉ cần một chuỗi tuần tự, dùng `RandomGenerator` là đủ. Nếu cần chạy song song, `SplittableGenerator` thường dễ áp dụng hơn cho việc tạo các stream con theo tác vụ.

Trước khi dùng, kiểm tra khả năng của factory:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

System.out.println("splittable=" + factory.isSplittable());
System.out.println("jumpable=" + factory.isJumpable());
System.out.println("leapable=" + factory.isLeapable());
~~~

Không ép kiểu một generator sang subinterface khi factory không xác nhận khả năng tương ứng. Một thuật toán có thể hỗ trợ split nhưng không hỗ trợ jump, hoặc ngược lại.

## 9. Kiểm thử mô phỏng có thể tái hiện

Kiểm thử mô phỏng nên xác minh cả tính xác định và tính hợp lý thống kê.

### 9.1. Kiểm thử tái hiện

Với cùng thuật toán, seed, tham số và thứ tự gọi, chạy mô phỏng hai lần rồi so sánh kết quả:

~~~java
Result first = estimate(20250317L, 100_000L);
Result second = estimate(20250317L, 100_000L);

if (!first.equals(second)) {
    throw new AssertionError("Simulation is not reproducible");
}
~~~

Nếu kết quả là record gồm các trường nguyên và số thực được tính theo cùng thứ tự, phép so sánh record có thể dùng để kiểm tra bằng nhau chính xác trong cùng runtime.

### 9.2. Kiểm thử biên và tham số

Kiểm tra:

- Seed âm, seed bằng 0 và seed dương đều được xử lý theo hợp đồng generator.
- Số mẫu phải dương.
- Xác suất nằm trong [0, 1].
- Rate và standard deviation phải hữu hạn, hợp lệ và không âm/dương theo mô hình.
- Tổng trọng số phải dương và hữu hạn.
- Không có phép cộng số lượng mẫu bị tràn.

Không nên để một mô phỏng tiếp tục với tham số NaN hoặc vô cực rồi chỉ phát hiện kết quả vô nghĩa ở cuối.

### 9.3. Kiểm thử thống kê

Kiểm thử tái hiện không chứng minh phân phối đúng. Một generator có thể tạo cùng chuỗi mỗi lần nhưng mô hình sử dụng sai phân phối.

Ví dụ với Bernoulli(p), sau N lần thử, số lần thành công kỳ vọng là:

~~~text
E[X] = Np
Var(X) = Np(1-p)
~~~

Có thể kiểm tra tỷ lệ thực tế nằm trong một khoảng tolerance thống kê phù hợp. Không nên viết test yêu cầu tỷ lệ chính xác bằng p vì mẫu hữu hạn luôn có biến động.

Với phân phối chuẩn, kiểm tra trung bình và phương sai mẫu gần tham số mong đợi khi N đủ lớn. Với phân phối mũ, kiểm tra trung bình mẫu gần giá trị 1/λ. Những test này cần tolerance được thiết kế theo kích thước mẫu, tránh ngưỡng quá chặt làm test chập chờn.

### 9.4. Không hardcode một chuỗi số làm chuẩn cho mọi runtime

Nếu test chỉ nhằm kiểm tra logic mô phỏng, nên so sánh hai lần chạy cùng seed trên cùng runtime hoặc kiểm tra invariant. Không nên hardcode một chuỗi số từ generator LXM rồi giả định nó luôn là chuẩn cho mọi vendor và phiên bản JDK nếu hợp đồng không cam kết điều đó.

Nếu ứng dụng cần bảo toàn output đã công bố qua nhiều năm, hãy pin runtime và algorithm hoặc lưu lại dữ liệu ngẫu nhiên đã sinh như một phần input của thí nghiệm.

## 10. Checkpoint và tiếp tục một mô phỏng

Lưu seed giúp chạy lại từ đầu. Nó không tự động cho phép tiếp tục từ giữa mô phỏng.

Giả sử mô phỏng đã chạy 10 triệu bước rồi dừng. Muốn tiếp tục đúng chuỗi, có thể:

1. Lưu checkpoint trạng thái mô hình.
2. Lưu seed, algorithm và số lượng lời gọi đã tiêu thụ.
3. Khởi tạo generator mới từ cùng seed.
4. Replay đúng số lượng lời gọi theo cùng thứ tự để đưa generator về trạng thái trước checkpoint.
5. Tiếp tục mô phỏng.

Replay có thể tốn thời gian và dễ sai nếu code thay đổi thứ tự gọi. Một số generator có thể cung cấp cơ chế jump hoặc state riêng, nhưng không nên giả định mọi implementation đều có API serialize trạng thái PRNG.

Một thiết kế khác là chia mô phỏng thành các batch độc lập với seed/stream riêng theo batch ID. Khi checkpoint, chỉ cần lưu kết quả các batch hoàn thành và metadata để chạy lại batch chưa hoàn thành. Đây thường là cách dễ vận hành hơn cho Monte Carlo phân tán.

## 11. Các lỗi thường gặp

| Lỗi | Vì sao gây vấn đề | Cách xử lý |
|---|---|---|
| Chỉ lưu seed | Thuật toán khác có thể tạo chuỗi khác. | Lưu cả tên algorithm và runtime. |
| Dùng generator mặc định | Lựa chọn mặc định có thể thay đổi. | Chọn tên generator bằng factory. |
| Dùng `Math.random()` | Khó kiểm soát generator và seed trong thiết kế mô phỏng. | Truyền `RandomGenerator` vào hàm mô phỏng. |
| Dùng `ThreadLocalRandom` cho kịch bản cần tái hiện | Không có workflow seed/stream theo tác vụ như mô hình mô phỏng cần. | Dùng generator có seed rõ ràng hoặc splittable streams. |
| Chia sẻ một generator giữa nhiều thread | Thứ tự tiêu thụ số có thể phụ thuộc lịch chạy. | Tách generator theo logical task. |
| Seed task từ thread ID | Thread assignment có thể thay đổi giữa các lần chạy. | Gán stream theo replication/task ID cố định. |
| Dùng `% bound` | Có thể tạo phân phối lệch. | Dùng `nextInt(bound)` hoặc `nextLong(bound)`. |
| Thêm lời gọi random để log | Làm dịch chuyển phần còn lại của chuỗi. | Không dùng chung stream cho logging; lưu giá trị đã sinh hoặc dùng stream riêng. |
| Chỉ test seed giống nhau | Không chứng minh phân phối hoặc mô hình đúng. | Kết hợp test deterministic, invariant và thống kê. |
| So sánh tổng số thực song song theo thứ tự hoàn tất | Thứ tự cộng floating-point có thể khác. | Lưu kết quả từng task rồi tổng hợp theo thứ tự cố định. |
| Coi seed là checkpoint | Seed chỉ tái tạo từ đầu. | Lưu trạng thái mô hình và replay hoặc chia batch độc lập. |
| Dùng PRNG cho mục đích bảo mật | PRNG mô phỏng không được thiết kế chống dự đoán. | Dùng `SecureRandom` cho token/secret; tách khỏi mô phỏng. |

## 12. Quy trình xây dựng một mô phỏng tái hiện được

Một quy trình có thể dùng trong dự án:

1. **Mô tả mô hình.** Xác định trạng thái, biến đầu vào, phân phối và điều kiện dừng.
2. **Chọn generator.** Chọn thuật toán có tên phù hợp; nếu cần parallel, kiểm tra khả năng splittable.
3. **Quản lý seed.** Nhận seed từ cấu hình hoặc tạo một lần rồi ghi lại.
4. **Tiêm RandomGenerator.** Truyền generator vào hàm mô phỏng thay vì tạo generator ẩn bên trong nhiều lớp.
5. **Tách stream theo nguồn hoặc tác vụ.** Dùng generator riêng cho arrivals, services, replication hoặc logical task.
6. **Lưu metadata.** Ghi algorithm, seed, JDK build, parameters, input data và version mô hình.
7. **Kiểm thử tái hiện.** Chạy lại cùng cấu hình và xác nhận kết quả giống nhau trong môi trường đã pin.
8. **Kiểm thử thống kê.** Kiểm tra phân phối, kỳ vọng, phương sai và invariant.
9. **Đo hiệu năng.** So sánh throughput và chi phí generator trên workload đại diện.
10. **Lưu checkpoint hoặc batch.** Thiết kế cách tiếp tục thí nghiệm mà không phụ thuộc vào seed đơn lẻ.

## 13. Chọn generator theo mục tiêu

| Mục tiêu | Lựa chọn phù hợp |
|---|---|
| Cần API chung để viết mô phỏng | Nhận `RandomGenerator` trong các phương thức. |
| Cần chỉ định thuật toán và seed | `RandomGeneratorFactory.of(name).create(seed)`. |
| Cần generator dễ chia cho task song song | `SplittableRandom` hoặc factory có `isSplittable() == true`. |
| Cần thuật toán có hợp đồng chuỗi lâu đời | `java.util.Random` khi tính tương thích chuỗi theo hợp đồng của nó quan trọng hơn tính năng mới. |
| Cần số ngẫu nhiên cho bảo mật | `SecureRandom`, không dùng generator mô phỏng thông thường. |
| Chỉ cần tiện lợi, không cần tái hiện | Generator mặc định có thể phù hợp, nhưng không nên dùng cho thí nghiệm cần tái lập. |

Không có một thuật toán tốt nhất cho mọi mô phỏng. Hãy cân nhắc chất lượng thống kê, tốc độ, khả năng split/jump, nhu cầu tương thích và cách triển khai của runtime.

## 14. Bài tập thực hành

### Bài tập 1 — Tái hiện Monte Carlo

Chạy `PiSimulation` hai lần với cùng seed và số mẫu. So sánh toàn bộ record kết quả. Sau đó đổi seed và quan sát kết quả thay đổi.

### Bài tập 2 — Chọn thuật toán bằng factory

Dùng `RandomGeneratorFactory.all()` để in tên generator, nhóm thuật toán, state bits và khả năng splittable. Chọn một generator LXM có sẵn trên JDK 17, tạo hai instance cùng seed và so sánh chuỗi số.

### Bài tập 3 — Mô phỏng Bernoulli

Mô phỏng 100.000 request với xác suất lỗi 0,02. Ghi seed, số request và số request lỗi. Chạy lại cùng seed và kiểm tra kết quả. Sau đó kiểm tra tỷ lệ lỗi có nằm trong khoảng thống kê hợp lý không.

### Bài tập 4 — Mô phỏng hàng đợi

Chạy `QueueSimulation` với λ = 2 và μ = 3. So sánh thời gian chờ trung bình với công thức lý thuyết M/M/1. Thay số khách warm-up và measured customers để quan sát ảnh hưởng của kích thước mẫu.

### Bài tập 5 — Tách stream

Tạo một root `SplittableRandom`, split thành hai generator cho arrivals và services. Thêm một lần lấy mẫu ở stream arrivals. Kiểm tra xem chuỗi service có thay đổi không.

### Bài tập 6 — Parallel replication

Dùng `ParallelMonteCarlo` để chạy 8 replication song song. Chạy lại với cùng seed và so sánh từng replication. Sau đó thay số worker của executor nhưng giữ số replication và mapping stream.

### Bài tập 7 — Kiểm tra lỗi modulo bias

Viết hai cách chọn số nguyên trong [0, 6]: dùng `nextInt(7)` và dùng `Math.abs(nextInt()) % 7`. Chạy số lượng mẫu lớn, so sánh tần suất và giải thích vì sao phép modulo có thể lệch.

### Bài tập 8 — Thiết kế metadata

Tạo một file metadata cho lần chạy mô phỏng, gồm algorithm, seed, JDK build, phiên bản mô hình, tham số phân phối, số mẫu và số replication. Viết chương trình đọc metadata và chạy lại cùng cấu hình.

## 15. Các nguyên tắc cần ghi nhớ

- `RandomGenerator` là abstraction chung cho các PRNG trong Java 17.
- Dùng `RandomGeneratorFactory` để chọn generator theo tên và tạo instance bằng seed cụ thể.
- Không dựa vào `RandomGenerator.getDefault()` nếu cần tái hiện kết quả lâu dài.
- Cùng thuật toán, seed, thứ tự lời gọi và tham số tạo chuỗi giả ngẫu nhiên có thể tái hiện.
- Lưu algorithm, seed, JDK build, version mô hình, input data và tham số mô phỏng.
- Dùng `nextInt(bound)` và `nextDouble(origin, bound)` thay cho modulo thủ công.
- Chọn phân phối theo mô hình: Bernoulli, uniform, Gaussian, exponential hoặc categorical có trọng số.
- Dùng `SplittableGenerator` để tách stream theo logical task; không gán stream theo thread ID hoặc lịch chạy.
- Tạo các stream song song theo thứ tự cố định và tổng hợp kết quả theo thứ tự xác định.
- Seed giúp chạy lại từ đầu; checkpoint giữa chừng cần lưu trạng thái mô hình và cơ chế khôi phục PRNG phù hợp.
- Reproducibility không thay thế kiểm thử thống kê; cần kiểm tra cả tính xác định lẫn tính hợp lý của phân phối.
- PRNG mô phỏng không phải nguồn số ngẫu nhiên bảo mật; dùng `SecureRandom` cho secret và token.

### Tài liệu tham khảo

- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html).
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html).
- [Java SE 17 API — RandomGenerator.SplittableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.SplittableGenerator.html).
- [Java SE 17 API — SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html).
- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356).
