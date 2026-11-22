# Lựa chọn nguồn ngẫu nhiên cho kiểm thử có thể lặp lại

Kiểm thử có thể lặp lại cần tạo cùng dữ liệu ngẫu nhiên khi chạy lại với cùng cấu hình. Trong Java 21, có thể dùng API `RandomGenerator` để truyền nguồn ngẫu nhiên vào mã cần kiểm thử, và dùng `RandomGeneratorFactory` để chọn thuật toán cụ thể. Khi kết hợp thuật toán được chọn rõ ràng với seed được ghi nhận, nhóm phát triển có thể tái tạo một tình huống lỗi thay vì phải đoán dữ liệu đã xuất hiện trong lần chạy trước.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), mục tiêu không chỉ là tạo số ngẫu nhiên mà còn kiểm soát được nguồn tạo số, seed, thứ tự gọi và cách chia nguồn cho các tác vụ song song. Một nguồn ngẫu nhiên ẩn trong `Math.random()` hoặc `ThreadLocalRandom.current()` không phù hợp khi cần tái hiện chính xác dữ liệu kiểm thử.

## RandomGenerator và RandomGeneratorFactory

Java 17 đã bổ sung package `java.util.random`; Java 21 tiếp tục hỗ trợ các API này. `RandomGenerator` là interface chung cho các bộ sinh giá trị giả ngẫu nhiên. Nó cung cấp các phương thức như `nextInt()`, `nextLong()`, `nextDouble()` và các overload nhận khoảng giá trị.

`RandomGeneratorFactory` giúp chọn và tạo generator theo tên thuật toán. Ví dụ, JDK 21 cung cấp thuật toán `L64X128MixRandom` thuộc nhóm LXM:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

long seed = 0x5EED_2021L;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator random = factory.create(seed);

System.out.println(random.nextInt(1, 101));
System.out.println(random.nextDouble(0.0, 1.0));
```

`factory.create(seed)` tạo generator bắt đầu từ seed đã chọn. Với `nextInt(origin, bound)`, cận dưới được bao gồm còn cận trên bị loại trừ; vì vậy `nextInt(1, 101)` tạo số từ 1 đến 100. Cách gọi có khoảng giúp thể hiện rõ miền dữ liệu cần kiểm thử.

Nếu tên thuật toán không có trong runtime đang dùng, `RandomGeneratorFactory.of()` sẽ báo lỗi thay vì âm thầm chọn một thuật toán khác. Có thể liệt kê những thuật toán runtime cung cấp:

```java
RandomGeneratorFactory.all()
        .map(RandomGeneratorFactory::name)
        .sorted()
        .forEach(System.out::println);
```

Việc chọn tên tường minh giúp tránh phụ thuộc vào generator mặc định của runtime. `RandomGenerator.getDefault()` tiện cho trường hợp không cần kiểm soát thuật toán, nhưng không phải lựa chọn tốt khi cần tái hiện chuỗi số qua nhiều lần chạy.

## Seed, thuật toán và thứ tự gọi quyết định chuỗi số

Với một generator giả ngẫu nhiên, seed khởi tạo trạng thái ban đầu. Khi dùng cùng thuật toán, cùng seed và cùng thứ tự gọi các phương thức sinh số, generator tạo lại cùng chuỗi kết quả theo hợp đồng của thuật toán và implementation đó.

```java
static void printScenario(long seed) {
    RandomGenerator random = RandomGeneratorFactory
            .<RandomGenerator>of("L64X128MixRandom")
            .create(seed);

    int quantity = random.nextInt(1, 101);
    double discount = random.nextDouble(0.0, 0.30);
    boolean express = random.nextBoolean();

    System.out.printf("quantity=%d, discount=%.4f, express=%s%n",
            quantity, discount, express);
}

public static void main(String[] args) {
    long seed = 0x5EED_2021L;
    printScenario(seed);
    printScenario(seed); // Cùng thuật toán, seed và thứ tự gọi nên cho cùng kết quả.
}
```

Nếu thêm một lời gọi `nextInt()` ở đầu phương thức, các giá trị được sinh sau đó sẽ dịch chuyển trong chuỗi. Vì vậy, khi tái hiện lỗi, cần giữ cả seed lẫn phiên bản logic tạo dữ liệu hoặc ghi lại input đã sinh. Seed một mình không đủ nếu thứ tự gọi đã thay đổi.

Đối với các bài kiểm thử cần tái hiện qua nhiều môi trường, hãy ghi nhận tối thiểu:

- Tên thuật toán, ví dụ `L64X128MixRandom`.
- Seed đầy đủ, không cắt ngắn hoặc chỉ ghi một phần.
- Phiên bản JDK và môi trường chạy khi cần tái hiện chính xác giữa các runtime.
- Phiên bản hoặc commit của mã tạo dữ liệu và thứ tự các thao tác sinh số.
- Input thực tế đã gây lỗi nếu chi phí lưu trữ cho phép.

Tên thuật toán tường minh tránh việc thay đổi generator mặc định, nhưng không nên mặc định rằng mọi provider hoặc mọi phiên bản JDK đều có cùng tập thuật toán. Nếu yêu cầu tái hiện bit-for-bit qua các bản runtime, cần cố định môi trường đã xác nhận hoặc chọn API có bảo đảm chuỗi được đặc tả phù hợp với yêu cầu. `java.util.Random` có cam kết đặc tả về chuỗi kết quả khi dùng cùng seed và cùng chuỗi lời gọi, nên vẫn là lựa chọn hợp lệ khi đặc tính đó quan trọng hơn các đặc điểm của generator mới.

## Truyền generator vào mã cần kiểm thử

Không nên để hàm nghiệp vụ tự gọi `Math.random()` hoặc tự tạo generator mới ở bên trong. Hãy nhận `RandomGenerator` qua tham số để test có thể kiểm soát nguồn ngẫu nhiên:

```java
import java.util.random.RandomGenerator;

record OrderInput(int quantity, double discount) {}

static OrderInput generateOrderInput(RandomGenerator random) {
    int quantity = random.nextInt(1, 101);
    double discount = random.nextDouble(0.0, 0.30);
    return new OrderInput(quantity, discount);
}
```

Test quyết định thuật toán và seed ở ranh giới tạo dữ liệu:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

long seed = 2021L;
RandomGenerator random = RandomGeneratorFactory
        .<RandomGenerator>of("L64X128MixRandom")
        .create(seed);

OrderInput input = generateOrderInput(random);
// Gọi logic cần kiểm thử với input đã được tạo có thể lặp lại.
```

Cách truyền dependency này có một số lợi ích:

- Test có thể tái tạo dữ liệu bằng seed đã biết.
- Cùng logic nghiệp vụ có thể được kiểm thử với nhiều seed khác nhau.
- Có thể dùng generator giả hoặc generator chuyên biệt trong các test cần kiểm soát chặt.
- Mã nghiệp vụ không phụ thuộc vào một nguồn ngẫu nhiên toàn cục.

Với test đơn vị, nên tạo generator mới cho từng test case hoặc từng kịch bản để thứ tự chạy test không làm thay đổi dữ liệu của test khác. Nếu chia sẻ một generator mutable toàn cục, một test chạy trước có thể tiêu thụ một số giá trị và làm test chạy sau nhận chuỗi khác.

## Ghi lại seed để tái hiện lỗi

Khi chạy nhiều kịch bản ngẫu nhiên, hãy ghi seed cùng thông tin test. Nếu một input làm test thất bại, có thể chạy lại đúng kịch bản đó:

```java
static void runScenario(long seed) {
    RandomGenerator random = RandomGeneratorFactory
            .<RandomGenerator>of("L64X128MixRandom")
            .create(seed);

    OrderInput input = generateOrderInput(random);
    verifyOrder(input);
}

public static void main(String[] args) {
    long seed = Long.parseLong(System.getProperty("test.seed", "2021"));
    System.out.println("test.seed=" + seed);
    runScenario(seed);
}
```

Khi CI báo lỗi, lưu giá trị `test.seed` trong log. Có thể chạy lại bằng tham số JVM tương ứng, chẳng hạn `-Dtest.seed=2021`. Với test framework, nên đưa seed vào message của assertion hoặc report để người phát triển có thể copy lại kịch bản.

Seed cố định làm cho một kịch bản có thể lặp lại, nhưng không tự động bảo đảm test bao phủ đủ trường hợp. Nên chạy một seed mặc định ổn định trong CI để phát hiện regression, đồng thời có thể chạy thêm một tập seed thay đổi theo lịch hoặc theo job riêng để mở rộng phạm vi dữ liệu. Khi job ngẫu nhiên thất bại, luôn lưu seed để biến lỗi ngẫu nhiên thành test tái hiện được.

## Dùng SplittableRandom khi cần các luồng ngẫu nhiên độc lập

`SplittableRandom` triển khai `RandomGenerator.SplittableGenerator` và hỗ trợ tạo generator con bằng `split()`. Cách này hữu ích khi cần chia dữ liệu ngẫu nhiên cho nhiều nhánh xử lý hoặc worker mà không chia sẻ một generator mutable giữa các thread.

```java
import java.util.SplittableRandom;

long masterSeed = 42L;
SplittableRandom root = new SplittableRandom(masterSeed);

SplittableRandom workerA = root.split();
SplittableRandom workerB = root.split();

int valueA = workerA.nextInt(1, 1_001);
int valueB = workerB.nextInt(1, 1_001);
```

Nếu tạo các generator con theo cùng một thứ tự từ cùng master seed, cây chia generator có thể được tái tạo. Mỗi worker có trạng thái riêng, nên thứ tự scheduler chạy worker A hay B không làm thay đổi chuỗi số nội bộ của worker còn lại.

Điều kiện quan trọng là việc phân chia phải ổn định. Nếu các worker tự cạnh tranh gọi `split()` trên cùng root theo thứ tự không xác định, generator con nào nhận nhánh nào có thể thay đổi theo lịch thực thi. Hãy tạo hoặc gán generator con theo thứ tự xác định trước khi chạy song song, hoặc dùng seed riêng được tính từ ID ổn định của từng test case.

`SplittableRandom` không được thiết kế để nhiều thread cùng gọi trên một instance. Không chia sẻ `root`, `workerA` hoặc `workerB` cho nhiều thread cùng sửa trạng thái. Mỗi worker nên sở hữu generator riêng.

## Tái hiện test song song mà không phụ thuộc lịch chạy

Một nguồn ngẫu nhiên dùng chung cho nhiều worker có thể làm kết quả phụ thuộc thứ tự gọi. Ví dụ, nếu worker A và B cùng gọi `nextInt()` trên một generator chia sẻ, worker nào lấy giá trị trước phụ thuộc scheduler. Dù seed ban đầu giống nhau, dữ liệu gán cho từng worker có thể khác giữa các lần chạy.

Hãy cấp generator riêng cho từng test case theo một quy tắc ổn định:

```java
long masterSeed = 2021L;

SplittableRandom root = new SplittableRandom(masterSeed);
SplittableRandom[] randoms = new SplittableRandom[3];

// Tạo và gán generator theo thứ tự cố định trước khi chạy song song.
for (int i = 0; i < randoms.length; i++) {
    randoms[i] = root.split();
}

// Mỗi worker chỉ sử dụng generator đã được cấp riêng.
```

Nếu test case được nhận diện bằng ID ổn định, có thể thiết kế hàm chuyển ID thành seed riêng bằng một phép trộn số nguyên được định nghĩa và kiểm thử rõ ràng. Tránh dùng `String.hashCode()` như một định danh duy nhất vì có thể xảy ra collision. Dù dùng splitting hay seed riêng, cần giữ ổn định cách ánh xạ test case sang generator để có thể tái hiện đúng lỗi.

## So sánh các nguồn ngẫu nhiên thường gặp

| Nguồn | Có kiểm soát seed cho test không? | Phù hợp với kiểm thử có thể lặp lại? | Ghi chú |
| --- | --- | --- | --- |
| `RandomGenerator` được tạo từ `RandomGeneratorFactory` với thuật toán và seed rõ ràng | Có | Có | Phù hợp khi muốn chọn thuật toán cụ thể và inject qua interface |
| `Random` | Có | Có | Chuỗi được đặc tả ổn định với cùng seed và cùng chuỗi lời gọi; vẫn là API hợp lệ |
| `SplittableRandom` | Có | Có | Hữu ích khi chia generator cho các nhánh hoặc worker độc lập; không dùng chung một instance đồng thời |
| `ThreadLocalRandom.current()` | Không có API seed được hỗ trợ cho ứng dụng | Không phù hợp | Tối ưu cho random theo thread, không dành cho replay bằng seed |
| `Math.random()` | Không có seed được truyền từ ứng dụng | Không phù hợp | Nguồn toàn cục tiện dụng, khó kiểm soát trong test |
| `SecureRandom` | Có thể cấu hình provider/seed, nhưng mục tiêu là bảo mật | Thường không phù hợp | Dành cho giá trị bảo mật; không biến nó thành generator test xác định bằng cách tự seed tùy tiện |

Không dùng generator giả ngẫu nhiên như `Random`, LXM hoặc `SplittableRandom` để tạo token bảo mật, mật khẩu, khóa hoặc nonce cần tính không thể đoán. Với mục đích bảo mật, dùng `SecureRandom` và không cố làm chuỗi của nó có thể dự đoán để tiện kiểm thử. Test nên mock hoặc inject ranh giới tạo giá trị bảo mật thay vì làm yếu nguồn entropy của production.

## Vì sao ThreadLocalRandom và Math.random không phù hợp cho replay?

`ThreadLocalRandom.current()` cung cấp generator gắn với thread hiện tại, hữu ích khi nhiều thread cần số ngẫu nhiên mà không tranh chấp một generator dùng chung. Tuy nhiên, API không cho ứng dụng đặt seed để tái tạo chuỗi theo ý muốn. `setSeed()` không phải cơ chế được hỗ trợ cho `ThreadLocalRandom` và có thể ném `UnsupportedOperationException`.

`Math.random()` trả về một giá trị `double` giả ngẫu nhiên trong khoảng từ 0.0 đến nhỏ hơn 1.0, nhưng không cho phép caller truyền seed hoặc chọn thuật toán. Nó tiện cho ví dụ đơn giản, nhưng che giấu dependency và làm việc tái hiện dữ liệu test khó hơn.

Trong kiểm thử, hãy thay hai nguồn này bằng một `RandomGenerator` được truyền vào từ bên ngoài. Nếu production cần `ThreadLocalRandom` để tối ưu, có thể giữ lựa chọn đó ở composition root hoặc adapter; phần logic tạo dữ liệu nên phụ thuộc vào interface để test có thể cung cấp generator seeded.

## Chọn thuật toán theo mục tiêu

Không phải thuật toán ngẫu nhiên nào cũng có cùng đặc tính. Khi dùng `RandomGeneratorFactory`, hãy cân nhắc:

- **Khả năng tái hiện:** thuật toán phải được chọn rõ, seed phải được lưu và runtime phải cung cấp đúng thuật toán đó.
- **Tốc độ và throughput:** benchmark trong workload thật nếu sinh số là phần đáng kể của thời gian chạy.
- **Chia generator:** chọn generator có khả năng split khi cần tạo nhiều luồng số độc lập cho tác vụ song song.
- **Chất lượng thống kê:** dùng generator được thiết kế cho mục tiêu mô phỏng/kiểm thử; không tự viết thuật toán đơn giản nếu chưa hiểu đặc tính thống kê.
- **Bảo mật:** nếu giá trị cần không thể dự đoán, dùng `SecureRandom`, không dùng PRNG thông thường.

Có thể kiểm tra khả năng của factory trước khi tạo generator:

```java
RandomGeneratorFactory.all().forEach(factory ->
        System.out.printf("%s, stateBits=%d, splittable=%s%n",
                factory.name(),
                factory.stateBits(),
                factory.isSplittable()));
```

Các metadata này giúp khám phá generator do runtime cung cấp. Đừng chọn thuật toán chỉ dựa trên một thuộc tính; hãy đọc tài liệu của thuật toán và benchmark theo nhu cầu.

## Quy trình thiết kế nguồn random cho test

1. **Xác định yêu cầu replay.** Test chỉ cần lặp lại trong cùng lần chạy, qua nhiều lần chạy cùng JDK hay cả qua các môi trường/JDK khác nhau?
2. **Chọn thuật toán tường minh.** Dùng `RandomGeneratorFactory.of(name)` thay vì dựa vào default nếu cần kiểm soát generator.
3. **Cấp seed tại ranh giới test.** Không tạo nguồn ngẫu nhiên ẩn trong logic nghiệp vụ; truyền `RandomGenerator` qua tham số hoặc dependency.
4. **Ghi nhận seed và môi trường.** Lưu thuật toán, seed, phiên bản JDK và mã tạo dữ liệu khi cần replay chính xác.
5. **Giữ thứ tự gọi ổn định.** Cùng seed nhưng thay đổi thứ tự gọi sẽ thay đổi dữ liệu được gán cho từng bước.
6. **Tách generator khi chạy song song.** Dùng `SplittableRandom.split()` hoặc seed riêng được gán theo ID ổn định; không chia sẻ một generator mutable giữa worker.
7. **Lưu input gây lỗi.** Khi test thất bại, lưu seed và tốt nhất là input đã sinh để tái hiện ngay cả khi thuật toán tạo dữ liệu thay đổi về sau.
8. **Tách mục tiêu bảo mật.** Dùng `SecureRandom` cho dữ liệu cần bảo mật; không dùng PRNG xác định để tạo secret production.

Nguồn random có thể lặp lại giúp kiểm thử ngẫu nhiên trở nên có thể tái hiện và dễ điều tra. Trong Java 21, `RandomGenerator` cùng `RandomGeneratorFactory` cho phép chọn thuật toán và seed rõ ràng, còn `SplittableRandom` hỗ trợ chia nguồn cho các worker độc lập. Hãy inject generator, giữ ổn định thứ tự gọi, ghi lại seed và runtime, đồng thời lưu input gây lỗi để việc replay không phụ thuộc hoàn toàn vào cách sinh dữ liệu ở lần chạy sau.
