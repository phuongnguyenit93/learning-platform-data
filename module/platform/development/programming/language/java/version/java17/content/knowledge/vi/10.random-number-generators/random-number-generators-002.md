# RandomGenerator như hợp đồng chung từ Java 17

Trước Java 17, khi cần sinh số giả ngẫu nhiên, lập trình viên thường phải chọn trực tiếp một lớp như `Random`, `ThreadLocalRandom` hoặc `SplittableRandom`. Các lớp này có mục đích và đặc điểm khác nhau, dù đều cung cấp những thao tác quen thuộc như sinh số nguyên, số thực, boolean hoặc byte.

Từ **Java 17**, package `java.util.random` cung cấp **`RandomGenerator`** làm hợp đồng chung cho các bộ sinh số giả ngẫu nhiên (PRNG). Nhờ interface này, mã ứng dụng có thể nhận một generator qua kiểu trừu tượng, còn việc chọn thuật toán cụ thể được thực hiện riêng bằng `RandomGeneratorFactory` hoặc bằng một implementation phù hợp.

Đây là phần mở rộng chính thức trong Java 17 theo **JEP 356 – Enhanced Pseudo-Random Number Generators**. Bài này tập trung vào API hiện hành của Java 17: cách tạo generator, chọn thuật toán, đặt seed, sinh giá trị có giới hạn, dùng stream, tách generator cho công việc song song và phân biệt PRNG thông thường với `SecureRandom`.

## 1. Vì sao cần một hợp đồng chung?

Trước đây, một phương thức có thể phụ thuộc trực tiếp vào `Random`:

~~~java
import java.util.Random;

static int rollDice(Random random) {
    return random.nextInt(6) + 1;
}
~~~

Nếu sau này muốn chuyển sang `SplittableRandom` hoặc một thuật toán khác, chữ ký phương thức và các điểm gọi có thể phải thay đổi.

`RandomGenerator` cung cấp một kiểu chung:

~~~java
import java.util.random.RandomGenerator;

static int rollDice(RandomGenerator random) {
    return random.nextInt(1, 7);
}
~~~

Bất kỳ implementation nào thực hiện hợp đồng này đều có thể được truyền vào phương thức, miễn là đáp ứng yêu cầu của ứng dụng.

Các lợi ích chính:

- **Tách API khỏi thuật toán:** code nghiệp vụ phụ thuộc vào `RandomGenerator` thay vì một lớp cụ thể.
- **Dễ thay thế implementation:** có thể chọn generator phù hợp với ứng dụng, benchmark hoặc cách chạy song song.
- **Hỗ trợ thuật toán mới:** Java 17 bổ sung nhiều thuật toán PRNG và cơ chế khám phá chúng.
- **Dễ kiểm soát seed:** có thể tạo generator từ seed cố định để tái hiện một chuỗi giá trị trong test hoặc mô phỏng.
- **Có API cho stream và tác vụ song song:** các implementation chuyên dụng có thể hỗ trợ split, jump hoặc các khả năng khác.

`RandomGenerator` là hợp đồng về thao tác sinh giá trị. Nó **không có nghĩa mọi generator đều có cùng thuật toán, cùng chuỗi kết quả, cùng đặc tính an toàn luồng hoặc cùng mức bảo mật**.

## 2. Package và những API chính

Các API nằm trong package:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;
~~~

`RandomGenerator` mô tả những thao tác sinh giá trị phổ biến. `RandomGeneratorFactory` giúp tìm, mô tả và tạo instance của thuật toán.

| Thành phần | Vai trò |
| --- | --- |
| `RandomGenerator` | Interface chung cho bộ sinh số giả ngẫu nhiên |
| `RandomGeneratorFactory` | Khám phá thuật toán và tạo generator |
| `Random` | Implementation quen thuộc, tương thích với hợp đồng chung |
| `SplittableRandom` | Generator có khả năng tách thành generator con |
| `ThreadLocalRandom` | Generator gắn với thread hiện tại |
| `SecureRandom` | Bộ sinh số ngẫu nhiên phục vụ mục đích bảo mật, đồng thời có thể dùng qua hợp đồng generator |
| `Math.random()` | API tiện ích trả về `double` trong khoảng từ 0.0 (bao gồm) đến 1.0 (không bao gồm) |

Một số phương thức thường dùng của `RandomGenerator`:

| Phương thức | Ý nghĩa |
| --- | --- |
| `nextInt()` | Sinh `int` bất kỳ |
| `nextInt(bound)` | Sinh `int` trong khoảng `[0, bound)` |
| `nextInt(origin, bound)` | Sinh `int` trong khoảng `[origin, bound)` |
| `nextLong()` | Sinh `long` |
| `nextLong(bound)` | Sinh `long` trong khoảng `[0, bound)` |
| `nextDouble()` | Sinh `double` trong khoảng `[0.0, 1.0)` |
| `nextDouble(bound)` | Sinh `double` trong khoảng `[0.0, bound)` |
| `nextDouble(origin, bound)` | Sinh `double` trong khoảng `[origin, bound)` |
| `nextBoolean()` | Sinh boolean |
| `nextBytes(bytes)` | Điền dữ liệu byte giả ngẫu nhiên vào mảng |
| `nextGaussian()` | Sinh giá trị theo phân phối chuẩn Gaussian |
| `ints()`, `longs()`, `doubles()` | Tạo stream giá trị giả ngẫu nhiên |

Với các phương thức có giới hạn, cận dưới được tính và cận trên không được tính. Ví dụ `nextInt(1, 7)` có thể trả về 1, 2, 3, 4, 5 hoặc 6; không trả về 7. Cận phải hợp lệ và cận trên phải lớn hơn cận dưới; nếu không, phương thức ném `IllegalArgumentException`.

## 3. Tạo generator theo cách đơn giản

### 3.1. Dùng generator mặc định

`RandomGenerator.getDefault()` tạo generator mặc định mà JDK cung cấp:

~~~java
import java.util.random.RandomGenerator;

public class DefaultGeneratorDemo {
    public static void main(String[] args) {
        RandomGenerator random = RandomGenerator.getDefault();

        int dice = random.nextInt(1, 7);
        double ratio = random.nextDouble();
        boolean enabled = random.nextBoolean();

        System.out.println("dice = " + dice);
        System.out.println("ratio = " + ratio);
        System.out.println("enabled = " + enabled);
    }
}
~~~

Cách này thuận tiện khi ứng dụng chỉ cần một generator tổng quát và không cần ràng buộc vào thuật toán cụ thể.

Tuy nhiên, nếu thuật toán là một phần của yêu cầu kỹ thuật (ví dụ tái hiện mô phỏng, đồng bộ chuỗi kết quả giữa các thành phần hoặc benchmark), không nên mặc định rằng lựa chọn mặc định luôn là hợp đồng thuật toán của ứng dụng. Hãy chọn tên thuật toán rõ ràng qua factory.

### 3.2. Tạo bằng phương thức tĩnh `of`

Có thể tạo generator theo tên thuật toán:

~~~java
RandomGenerator random =
        RandomGenerator.of("L64X128MixRandom");
~~~

Tên thuật toán phải có trong runtime đang sử dụng. Nếu tên không được hỗ trợ, phương thức ném `IllegalArgumentException`. Có thể kiểm tra danh sách factory khả dụng trước khi chọn.

### 3.3. Dùng `RandomGeneratorFactory` khi cần seed hoặc metadata

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class FactoryDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(12345L);
        RandomGenerator second = factory.create(12345L);

        System.out.println(first.nextInt());
        System.out.println(second.nextInt());
    }
}
~~~

Hai generator được tạo cùng thuật toán và cùng seed bắt đầu từ cùng trạng thái khởi tạo; khi gọi cùng chuỗi phương thức theo cùng thứ tự, chúng có thể tái hiện chuỗi kết quả tương ứng của thuật toán đó.

Factory còn cung cấp thông tin mô tả implementation như tên, số bit trạng thái và các khả năng hỗ trợ. Đây là cách để ứng dụng tách **lựa chọn thuật toán** khỏi **logic sử dụng generator**.

## 4. Khám phá thuật toán bằng RandomGeneratorFactory

Java 17 cung cấp nhiều thuật toán PRNG mới. Không nên giả định mọi JDK hoặc provider đều có chính xác cùng danh sách; hãy khám phá những factory runtime thực sự cung cấp.

~~~java
import java.util.random.RandomGeneratorFactory;

public class ListGenerators {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
                .map(RandomGeneratorFactory::name)
                .sorted()
                .forEach(System.out::println);
    }
}
~~~

`RandomGeneratorFactory.all()` trả về stream các factory khả dụng. Từ đó có thể lấy tên thuật toán, sắp xếp hoặc hiển thị cho mục đích cấu hình.

Một số tên thuật toán có thể gặp trong JDK 17 gồm:

- `L32X64MixRandom`
- `L64X128MixRandom`
- `L64X128StarStarRandom`
- `L64X256MixRandom`
- `L64X1024MixRandom`
- `L128X128MixRandom`
- `L128X256MixRandom`
- `L128X1024MixRandom`
- `Xoshiro256PlusPlus`
- `Xoroshiro128PlusPlus`

Danh sách cụ thể nên được lấy từ `RandomGeneratorFactory.all()` tại runtime. Đừng chép một danh sách từ môi trường khác rồi mặc định tên nào cũng có ở mọi JDK/provider.

### 4.1. Xem metadata của factory

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

System.out.println("name = " + factory.name());
System.out.println("stateBits = " + factory.stateBits());
System.out.println("isSplittable = " + factory.isSplittable());
System.out.println("isJumpable = " + factory.isJumpable());
System.out.println("isLeapable = " + factory.isLeapable());
~~~

Các thuộc tính khả năng như `isSplittable()`, `isJumpable()` và `isLeapable()` cho biết implementation có hỗ trợ những giao diện/hành vi chuyên biệt tương ứng hay không. Không phải thuật toán nào cũng hỗ trợ mọi khả năng.

Factory cũng cung cấp các thông tin thống kê/đặc tính thuật toán như `isStatistical()`, `isStochastic()`, `isHardware()`, `isStreamable()` và các thuộc tính liên quan chu kỳ/equidistribution. Đây là metadata mô tả bộ sinh, không phải lời đảm bảo rằng một thuật toán phù hợp cho mọi bài toán.

### 4.2. Chọn thuật toán theo tên cấu hình

Nếu ứng dụng cho phép cấu hình thuật toán, nên kiểm tra tên và báo lỗi rõ ràng:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

static RandomGenerator createGenerator(String algorithm, long seed) {
    RandomGeneratorFactory<RandomGenerator> factory =
            RandomGeneratorFactory.of(algorithm);
    return factory.create(seed);
}
~~~

Không nên âm thầm thay bằng generator mặc định nếu tên được cấu hình không tồn tại. Việc fallback có thể làm thay đổi chuỗi kết quả, đặc tính hiệu năng và khả năng tái hiện của ứng dụng.

## 5. Seed và khả năng tái hiện kết quả

**Seed** là giá trị khởi tạo trạng thái của một bộ sinh giả ngẫu nhiên. PRNG là thuật toán xác định: cùng thuật toán, cùng trạng thái ban đầu và cùng chuỗi lời gọi sẽ tạo ra cùng chuỗi kết quả.

Ví dụ:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SeedDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator a = factory.create(2026L);
        RandomGenerator b = factory.create(2026L);

        for (int i = 0; i < 5; i++) {
            System.out.println(a.nextInt() + " == " + b.nextInt());
        }
    }
}
~~~

Mỗi dòng thể hiện hai generator cùng seed và cùng cách sử dụng tạo ra giá trị tương ứng giống nhau.

### 5.1. Seed cố định hữu ích trong test và mô phỏng

Seed cố định giúp:

- Tái hiện một tình huống test có yếu tố ngẫu nhiên.
- So sánh hai phiên bản thuật toán trên cùng chuỗi đầu vào.
- Tạo dữ liệu mô phỏng lặp lại để phân tích.
- Debug một lỗi xuất hiện ở một lần chạy cụ thể.

Ví dụ test có thể tạo generator riêng cho mỗi trường hợp:

~~~java
RandomGenerator random =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(123456L);

int sample = random.nextInt(0, 100);
~~~

Khi test thất bại, ghi lại thuật toán, seed và chuỗi thao tác cần thiết để tái hiện. Chỉ ghi seed có thể chưa đủ nếu test còn phụ thuộc vào thứ tự chạy, trạng thái dùng chung hoặc các lời gọi random khác.

### 5.2. Seed không làm PRNG thành ngẫu nhiên thực

Nếu seed được cố định, chuỗi kết quả có thể tái hiện. Nếu seed lấy từ thời gian hoặc nguồn biến thiên, chuỗi khởi tạo thay đổi, nhưng điều đó **không biến thuật toán PRNG thông thường thành bộ sinh an toàn mật mã**.

Không dùng seed dễ đoán hoặc generator mặc định để tạo mật khẩu, token phiên, mã khôi phục hay khóa bí mật.

### 5.3. Không chia sẻ một generator có trạng thái giữa test độc lập

Nếu nhiều test dùng chung một instance và cùng gọi phương thức sinh giá trị, thứ tự thực thi sẽ ảnh hưởng trạng thái. Một test chạy trước có thể làm test sau nhận chuỗi khác.

Nên tạo generator riêng với seed rõ ràng trong từng test, hoặc truyền generator vào đối tượng cần kiểm thử để kiểm soát phụ thuộc.

## 6. Sinh giá trị có giới hạn đúng cách

### 6.1. Số nguyên trong khoảng

~~~java
RandomGenerator random = RandomGenerator.getDefault();

int value = random.nextInt(10, 21);
~~~

Giá trị nằm trong `[10, 21)`, tức từ 10 đến 20.

Để mô phỏng xúc xắc sáu mặt:

~~~java
int dice = random.nextInt(1, 7);
~~~

Không cần viết `random.nextInt() % 6 + 1`. Dùng overload có bound để tránh phân phối lệch do phép modulo khi số lượng giá trị đầu vào không chia hết cho số mặt.

### 6.2. Số thực trong khoảng

~~~java
double ratio = random.nextDouble();          // [0.0, 1.0)
double priceFactor = random.nextDouble(0.8, 1.2); // [0.8, 1.2)
~~~

Cận trên không được tính. Nếu cần ánh xạ sang một khoảng, dùng overload origin/bound thay vì tự cộng/trừ mà không kiểm tra miền.

### 6.3. Tránh tự viết modulo

Ví dụ không nên dùng:

~~~java
int dice = Math.abs(random.nextInt()) % 6 + 1;
~~~

Có hai vấn đề:

- Phân phối modulo có thể không đồng đều khi miền nguồn không chia hết cho 6.
- `Math.abs(Integer.MIN_VALUE)` vẫn âm vì giá trị dương tương ứng không biểu diễn được trong `int`.

Hãy dùng:

~~~java
int dice = random.nextInt(1, 7);
~~~

API bound được thiết kế để tạo kết quả trong miền hợp lệ mà không cần mẹo modulo.

## 7. Sinh dữ liệu bằng Stream API

`RandomGenerator` có các phương thức tạo stream số giả ngẫu nhiên.

~~~java
RandomGenerator random = RandomGenerator.getDefault();

int[] values = random.ints(10, 0, 100).toArray();
long[] ids = random.longs(5, 1_000L, 10_000L).toArray();
double[] ratios = random.doubles(4, 0.0, 1.0).toArray();
~~~

Các overload có số lượng phần tử cho stream hữu hạn:

- `ints(streamSize, origin, bound)`
- `longs(streamSize, origin, bound)`
- `doubles(streamSize, origin, bound)`

Các overload không có `streamSize` tạo stream không giới hạn; khi dùng chúng, cần có thao tác giới hạn như `limit(n)` để tránh pipeline chạy vô tận.

~~~java
random.ints(0, 100)
        .limit(5)
        .forEach(System.out::println);
~~~

Stream random là lazy: generator được tiêu thụ khi pipeline được thực thi. Không nên gọi song song hoặc tái sử dụng stream theo cách khiến thứ tự tiêu thụ trạng thái không rõ ràng nếu kết quả cần tái hiện chính xác.

## 8. Chọn implementation: Random, ThreadLocalRandom, SplittableRandom

`RandomGenerator` là hợp đồng chung; trong thực tế vẫn cần chọn implementation theo cách sử dụng.

| Implementation | Điểm phù hợp | Lưu ý |
| --- | --- | --- |
| `Random` | Tương thích code cũ, cần API quen thuộc và seed | Có thể tranh chấp trạng thái khi nhiều thread cùng dùng |
| `ThreadLocalRandom` | Nhiều thread độc lập cần random nhanh | Lấy qua `current()`; không thiết kế để đặt seed thủ công từ code ứng dụng |
| `SplittableRandom` | Mô phỏng hoặc tính toán chia thành tác vụ con | Có `split()`; instance không được thiết kế để nhiều thread cùng sửa trạng thái |
| Thuật toán LXM/Xoroshiro/Xoshiro qua factory | Muốn chọn thuật toán cụ thể và khai thác API mới | Kiểm tra khả năng và tên algorithm trong runtime |
| `SecureRandom` | Dữ liệu cần độ khó dự đoán và mục đích bảo mật | Chọn rõ API bảo mật; không thay thế bằng PRNG thống kê thông thường |

### 8.1. Random

`Random` là lớp có từ các phiên bản Java cũ và thực hiện `RandomGenerator`:

~~~java
import java.util.Random;

Random random = new Random(1234L);
int value = random.nextInt(1, 7);
~~~

Có thể giữ `Random` trong API cũ và truyền vào nơi nhận `RandomGenerator`. Khi viết code mới, việc phụ thuộc interface giúp dễ thay implementation hơn nếu cần.

### 8.2. ThreadLocalRandom

~~~java
import java.util.concurrent.ThreadLocalRandom;

int value = ThreadLocalRandom.current().nextInt(1, 7);
~~~

`ThreadLocalRandom.current()` trả về generator gắn với thread hiện tại. Đây là lựa chọn thuận tiện trong xử lý nhiều thread độc lập, giảm tranh chấp so với nhiều thread cùng truy cập một instance `Random`.

Không nên cố gọi `setSeed` trên `ThreadLocalRandom` để tái hiện chuỗi; cơ chế này không được thiết kế cho việc đặt seed thủ công từ phía ứng dụng.

### 8.3. SplittableRandom và chia generator

`SplittableRandom` được thiết kế cho những tình huống một luồng công việc chia thành nhiều nhánh cần các generator riêng. Có thể tạo generator con bằng `split()`:

~~~java
import java.util.SplittableRandom;

public class SplitDemo {
    public static void main(String[] args) {
        SplittableRandom parent = new SplittableRandom(2026L);

        SplittableRandom taskA = parent.split();
        SplittableRandom taskB = parent.split();

        System.out.println(taskA.nextInt(1, 7));
        System.out.println(taskB.nextInt(1, 7));
    }
}
~~~

Ý tưởng là tách generator trước khi giao các nhánh công việc cho những tác vụ độc lập. Không chia sẻ cùng một instance mutable cho nhiều thread. Nếu cần kết quả tái hiện, phải cố định seed và cấu trúc split/call theo cùng một cách.

`SplittableRandom` cũng thực hiện `RandomGenerator.SplittableGenerator`, nên có thể khai báo biến theo hợp đồng chuyên biệt khi cần gọi `split()`:

~~~java
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;

RandomGenerator.SplittableGenerator generator =
        new SplittableRandom(123L);

RandomGenerator.SplittableGenerator child = generator.split();
~~~

Không phải mọi implementation của `RandomGenerator` đều có khả năng split. Hãy dùng giao diện con hoặc kiểm tra metadata factory thay vì giả định.

## 9. Phân biệt PRNG và SecureRandom

Tên gọi “random” dễ tạo cảm giác mọi generator đều phù hợp cho token hay mã bí mật. Thực tế, **`RandomGenerator` không phải cam kết về bảo mật mật mã**.

PRNG thông thường tối ưu cho việc sinh chuỗi giả ngẫu nhiên có đặc tính thống kê phù hợp. Nếu thuật toán và trạng thái bị biết hoặc dự đoán được, kẻ tấn công có thể dự đoán giá trị tiếp theo.

`SecureRandom` được thiết kế cho nhu cầu mật mã và là lựa chọn phù hợp khi tạo dữ liệu nhạy cảm như token hoặc nonce bảo mật:

~~~java
import java.security.SecureRandom;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] token = new byte[32];
        secureRandom.nextBytes(token);

        for (byte value : token) {
            System.out.printf("%02x", value);
        }
        System.out.println();
    }
}
~~~

`SecureRandom` cũng cung cấp các thao tác tương thích với `RandomGenerator` trong Java 17. Tuy nhiên, nên giữ kiểu `SecureRandom` ở nơi hợp đồng bảo mật là điều quan trọng, để người đọc nhận ra yêu cầu ngay từ chữ ký và tránh thay bằng generator không an toàn.

Không dùng `RandomGenerator.getDefault()`, `Random`, `SplittableRandom` hoặc `ThreadLocalRandom` để sinh:

- Mật khẩu hoặc mã PIN.
- Session ID, reset token hoặc access token.
- Khóa mã hóa hoặc nonce cần tính khó đoán.
- Mã xác thực hoặc giá trị bảo mật khác.

## 10. Tạo một abstraction nhỏ trong ứng dụng

Một dịch vụ nghiệp vụ có thể nhận `RandomGenerator` qua constructor:

~~~java
import java.util.Objects;
import java.util.random.RandomGenerator;

public final class DiceService {
    private final RandomGenerator random;

    public DiceService(RandomGenerator random) {
        this.random = Objects.requireNonNull(random, "random");
    }

    public int roll() {
        return random.nextInt(1, 7);
    }
}
~~~

Code chạy ứng dụng có thể chọn generator mặc định hoặc thuật toán được cấu hình:

~~~java
RandomGenerator random =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(2026L);

DiceService service = new DiceService(random);
System.out.println(service.roll());
~~~

Test có thể inject generator khởi tạo bằng seed cố định:

~~~java
RandomGenerator random =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(1234L);

DiceService service = new DiceService(random);
int firstRoll = service.roll();
~~~

Cách này làm dependency rõ ràng. Nó cũng tránh việc phương thức nghiệp vụ tự gọi `RandomGenerator.getDefault()` ở sâu bên trong, khiến test khó kiểm soát chuỗi kết quả.

Nếu test chỉ cần kiểm tra logic phản ứng với giá trị cụ thể, có thể dùng một implementation giả (fake) hoặc mock `RandomGenerator` thay vì dựa vào một chuỗi ngẫu nhiên thực tế.

## 11. Khả năng split, jump và leap

Một số generator cung cấp giao diện con để hỗ trợ cách tiến trạng thái chuyên biệt:

- **Splittable:** tách một generator thành các generator con, phù hợp khi phân chia tác vụ.
- **Jumpable:** nhảy trạng thái tiến một khoảng lớn đã được thuật toán xác định.
- **Leapable:** nhảy xa hơn theo quy tắc của implementation, hữu ích trong một số cách phân vùng chuỗi.

Các khả năng này không có trên mọi generator. Trong Java 17, các giao diện con nằm trong `RandomGenerator`, chẳng hạn `RandomGenerator.SplittableGenerator`, `RandomGenerator.JumpableGenerator` và `RandomGenerator.LeapableGenerator`.

Có thể kiểm tra khả năng trước khi yêu cầu một factory:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

if (factory.isSplittable()) {
    System.out.println("Generator hỗ trợ split");
}
if (factory.isJumpable()) {
    System.out.println("Generator hỗ trợ jump");
}
~~~

Không nên chọn thuật toán chỉ vì nó có tên dễ nhớ. Hãy xác định nhu cầu: sinh dữ liệu độc lập cho các task, tái hiện mô phỏng, hiệu năng, hoặc yêu cầu thống kê. Sau đó kiểm tra metadata và tài liệu của implementation cụ thể.

## 12. Tính thread-safety và cách dùng song song

`RandomGenerator` không tự cam kết mọi implementation là thread-safe. Đặc tính phụ thuộc vào lớp cụ thể.

- `Random` có thể được nhiều thread dùng chung, nhưng contention trên trạng thái có thể ảnh hưởng hiệu năng.
- `ThreadLocalRandom` cung cấp generator riêng cho thread hiện tại.
- `SplittableRandom` phù hợp khi chia generator thành các instance riêng cho từng nhánh; không dùng cùng một instance mutable cho nhiều thread.
- Các implementation khác có hợp đồng và đặc tính riêng; cần đọc tài liệu của thuật toán được chọn.

Ví dụ dùng `ThreadLocalRandom` trong một tác vụ chạy ở nhiều thread:

~~~java
import java.util.concurrent.ThreadLocalRandom;

Runnable task = () -> {
    int sample = ThreadLocalRandom.current().nextInt(0, 100);
    System.out.println(Thread.currentThread().getName() + ": " + sample);
};
~~~

Với tính toán song song cần kết quả tái hiện, cách chia generator và thứ tự phân công task cần được thiết kế rõ ràng. Chỉ dùng seed giống nhau nhưng để lịch thực thi thread tự do có thể khiến thứ tự tiêu thụ số khác nhau giữa các lần chạy.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Code phụ thuộc cứng vào `Random` | Chọn class cụ thể ngay trong API nghiệp vụ | Nhận `RandomGenerator` qua tham số hoặc constructor |
| Tên thuật toán không được hỗ trợ | Runtime không cung cấp factory đó | Khám phá bằng `RandomGeneratorFactory.all()` và xử lý lỗi cấu hình |
| Kết quả test thay đổi mỗi lần | Dùng seed khác hoặc generator dùng chung có trạng thái | Tạo generator riêng với seed cố định |
| Tự tính `nextInt() % bound` | Có thể tạo phân phối lệch; còn có bẫy `Math.abs(MIN_VALUE)` | Dùng `nextInt(bound)` hoặc `nextInt(origin, bound)` |
| Dùng generator mặc định để tạo token | PRNG thống kê không phải cam kết mật mã | Dùng `SecureRandom` |
| Dùng `SplittableRandom` chung cho nhiều thread | Instance có trạng thái và không được thiết kế để chia sẻ đồng thời | Split thành generator con hoặc dùng lựa chọn thread-local |
| Nghĩ mọi generator đều có `split()` | Chỉ generator hỗ trợ giao diện split mới có khả năng đó | Dùng `SplittableGenerator` hoặc kiểm tra factory |
| Seed cố định nhưng test vẫn khác | Lời gọi random hoặc lịch thực thi thay đổi | Cô lập generator, cố định thứ tự và seed |
| Cho rằng `RandomGenerator` đảm bảo cùng chuỗi | Interface chung không xác định mọi thuật toán giống nhau | Chọn thuật toán cụ thể và kiểm soát môi trường cần tái hiện |
| Tạo stream vô hạn mà không giới hạn | Dùng `ints()`/`doubles()` không có stream size | Dùng overload có kích thước hoặc `limit()` |

## 14. Bài thực hành

### Bài 1 — Dùng hợp đồng chung

Viết phương thức `rollDice(RandomGenerator generator)` trả về giá trị trong `[1, 7)`. Gọi phương thức bằng generator mặc định và bằng một instance `Random`. Giải thích vì sao không phải sửa chữ ký phương thức.

### Bài 2 — Khám phá factory

Dùng `RandomGeneratorFactory.all()` in tên các thuật toán có trong runtime. Chọn một tên, tạo factory và in `name()`, `stateBits()`, `isSplittable()`. Không giả định danh sách trên máy khác giống hệt.

### Bài 3 — Tái hiện bằng seed

Tạo hai generator cùng thuật toán và seed. Sinh 20 giá trị từ mỗi generator rồi so sánh hai mảng kết quả. Thay một seed và giải thích vì sao chuỗi có thể thay đổi.

### Bài 4 — Stream có giới hạn

Tạo stream gồm 10 số nguyên từ 1 đến 100. Chuyển thành mảng, in ra và xác nhận tất cả giá trị thỏa `value >= 1 && value < 100`.

### Bài 5 — Chia generator

Dùng `SplittableRandom` để tạo generator con cho hai tác vụ. Không chia sẻ cùng một instance giữa các tác vụ. Thử seed cố định và ghi lại cách thứ tự split ảnh hưởng kết quả.

### Bài 6 — Chọn generator theo yêu cầu

Đối chiếu ba nhu cầu: mô phỏng Monte Carlo có seed tái hiện, nhiều request độc lập trên thread pool, và tạo token đăng nhập. Chọn implementation phù hợp trong từng trường hợp và giải thích lý do.

## 15. Nguyên tắc sử dụng trong Java 17

`RandomGenerator` tạo ra một **hợp đồng chung** để ứng dụng sử dụng nhiều loại bộ sinh giả ngẫu nhiên mà không phụ thuộc cứng vào một implementation. `RandomGeneratorFactory` bổ sung cách khám phá thuật toán, tạo generator theo tên và seed, đồng thời cung cấp metadata về khả năng của chúng.

Khi thiết kế:

- Dùng `RandomGenerator` làm kiểu phụ thuộc chung trong code nghiệp vụ.
- Chọn generator mặc định khi không cần ràng buộc thuật toán; chọn factory theo tên khi thuật toán là một phần của hợp đồng.
- Dùng seed cố định để tái hiện test và mô phỏng, đồng thời cô lập trạng thái giữa các trường hợp kiểm thử.
- Dùng overload có bound thay vì phép modulo tự viết.
- Chọn `SplittableRandom`/`SplittableGenerator` cho công việc cần tách luồng sinh; chọn `ThreadLocalRandom` cho nhu cầu per-thread phù hợp.
- Dùng `SecureRandom` cho dữ liệu cần khó dự đoán về mặt mật mã; tên interface `RandomGenerator` tự nó không bảo đảm điều đó.

Việc tách **hợp đồng sinh số** khỏi **thuật toán cụ thể** giúp code Java 17 dễ thay đổi, kiểm thử và cấu hình hơn. Tuy nhiên, chất lượng, khả năng split, thread-safety và bảo mật vẫn phải được quyết định theo implementation và yêu cầu thực tế.
