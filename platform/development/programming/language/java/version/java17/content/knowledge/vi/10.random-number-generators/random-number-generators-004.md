# Liệt kê, tra thuộc tính và chọn thuật toán sinh số giả ngẫu nhiên trong Java 17

## 1. Vì sao cần chọn thuật toán sinh số?

Ứng dụng Java có thể cần số giả ngẫu nhiên cho mô phỏng, trò chơi, lấy mẫu dữ liệu, chia tải, kiểm thử hoặc tạo dữ liệu bảo mật. Các bộ sinh khác nhau về tốc độ, kích thước trạng thái, chu kỳ, khả năng tạo các luồng riêng và mức độ an toàn mật mã. **Không có một thuật toán duy nhất phù hợp cho mọi tình huống.**

Ví dụ:

- Mô phỏng Monte Carlo cần chuỗi giả ngẫu nhiên có đặc tính thống kê tốt và có thể tái lập bằng seed.
- Tính toán song song cần các bộ sinh riêng cho từng tác vụ, tránh chia sẻ trạng thái gây tranh chấp.
- Trò chơi có thể cần số nguyên trong khoảng 1 đến 6.
- Token đăng nhập, mã reset mật khẩu hoặc nonce trong giao thức bảo mật cần nguồn ngẫu nhiên khó dự đoán về mặt mật mã.

Java 17 bổ sung API tổng quát trong package `java.util.random` qua JEP 356. Interface `RandomGenerator` chuẩn hóa cách sử dụng các bộ sinh, còn `RandomGeneratorFactory` cho phép **liệt kê, tra thuộc tính và tạo instance theo tên thuật toán**.

> Cần phân biệt **PRNG** (*pseudo-random number generator*, bộ sinh số giả ngẫu nhiên) và **CSPRNG** (*cryptographically secure PRNG*, bộ sinh giả ngẫu nhiên an toàn về mật mã). PRNG dành cho mô phỏng không tự động phù hợp để tạo bí mật bảo mật. Với dữ liệu nhạy cảm, dùng `SecureRandom`.

## 2. API sinh số trong Java 17

### 2.1. `RandomGenerator` — giao diện chung

`RandomGenerator` là interface chính để lấy các giá trị giả ngẫu nhiên. Nó có các phương thức cho số nguyên, số thực, boolean, phân phối chuẩn, phân phối mũ và stream:

~~~java
import java.util.random.RandomGenerator;

RandomGenerator random = RandomGenerator.getDefault();

int anyInt = random.nextInt();
int dice = random.nextInt(1, 7);       // 1 đến 6
long idPart = random.nextLong();
double unit = random.nextDouble();    // [0.0, 1.0)
boolean enabled = random.nextBoolean();
double normal = random.nextGaussian();
double exponential = random.nextExponential();
~~~

Các khoảng có cận dưới bao gồm và cận trên không bao gồm. Ví dụ `nextInt(1, 7)` có thể trả về 1, 2, 3, 4, 5 hoặc 6; nó không trả về 7. `nextDouble()` trả về giá trị từ 0.0 (bao gồm) đến 1.0 (không bao gồm).

Bạn cũng có thể tạo stream:

~~~java
random.ints(10, 1, 7).forEach(System.out::println);
~~~

Lệnh này tạo 10 số nguyên trong khoảng [1, 7). Hãy giới hạn kích thước stream khi chỉ cần một lượng dữ liệu xác định; các overload không có số lượng có thể tạo stream gần như vô hạn.

### 2.2. `RandomGeneratorFactory` — tìm và tạo thuật toán

`RandomGeneratorFactory<T>` là lớp factory cho một thuật toán cụ thể. Các thao tác quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `RandomGeneratorFactory.all()` | Trả về stream các factory khả dụng trong runtime. |
| `RandomGeneratorFactory.of(name)` | Tìm factory theo tên thuật toán. |
| `factory.create()` | Tạo generator với seed được khởi tạo tự động. |
| `factory.create(seed)` | Tạo generator với seed dạng `long`. |
| `factory.name()` | Tên thuật toán. |
| `factory.group()` | Nhóm thuật toán. |
| `factory.stateBits()` | Số bit trạng thái của thuật toán. |
| `factory.period()` | Chu kỳ, kiểu `BigInteger`. |

Ví dụ chọn một thuật toán có tên rõ ràng:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator random = factory.create(2026L);
System.out.println(random.nextInt(1, 7));
~~~

Tên thuật toán truyền cho `of` phải có trong runtime. Nếu không tìm thấy, phương thức ném `IllegalArgumentException`. `create(long)` sử dụng seed đã cung cấp nếu thuật toán hỗ trợ; theo hợp đồng API, nếu thuật toán không hỗ trợ kiểu seed đó thì factory có thể dùng cách tạo không tham số.

### 2.3. Các lớp quen thuộc vẫn dùng được

Java 17 vẫn hỗ trợ các lớp `Random`, `ThreadLocalRandom`, `SplittableRandom` và `SecureRandom`. Các lớp này tương thích với giao diện `RandomGenerator` trong Java 17. Mã mới có thể nhận `RandomGenerator` làm kiểu tham số để không phụ thuộc vào một hiện thực cụ thể.

~~~java
static int roll(RandomGenerator random) {
    return random.nextInt(1, 7);
}
~~~

Phương thức `roll` có thể dùng với generator được tạo từ factory, `Random`, `SplittableRandom` hoặc `SecureRandom` tùy yêu cầu. Việc chọn kiểu cụ thể nên diễn ra ở nơi khởi tạo phụ thuộc, thay vì rải tên thuật toán khắp logic nghiệp vụ.

## 3. Liệt kê các thuật toán đang có trong runtime

Không nên đoán thuật toán nào có sẵn trên máy người dùng. `RandomGeneratorFactory.all()` cung cấp danh sách factory được runtime đăng ký. Theo Java SE 17, stream này không bao gồm các thuật toán đã được đánh dấu deprecated; JDK hoặc provider cụ thể cũng có thể bổ sung thuật toán riêng.

Tạo file `RandomInventory.java`:

~~~java
import java.util.random.RandomGeneratorFactory;

public final class RandomInventory {
    private RandomInventory() {
    }

    public static void main(String[] args) {
        System.out.println("Default factory: "
                + RandomGeneratorFactory.getDefault().name());
        System.out.println();

        System.out.printf(
                "%-25s %-12s %7s %5s %10s %7s %7s %7s %7s%n",
                "NAME", "GROUP", "STATE", "EQ", "PERIOD",
                "SPLIT", "JUMP", "LEAP", "STREAM");

        RandomGeneratorFactory.all().forEach(factory ->
                System.out.printf(
                        "%-25s %-12s %7d %5d %10s %7s %7s %7s %7s%n",
                        factory.name(),
                        factory.group(),
                        factory.stateBits(),
                        factory.equidistribution(),
                        factory.period(),
                        factory.isSplittable(),
                        factory.isJumpable(),
                        factory.isLeapable(),
                        factory.isStreamable()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~text
javac --release 17 -encoding UTF-8 RandomInventory.java
java RandomInventory
~~~

Chương trình hiển thị tên factory mặc định, tên và nhóm của từng thuật toán, số bit trạng thái, mức equidistribution, chu kỳ và các khả năng split/jump/leap/stream. `period` có thể là số rất lớn nên được biểu diễn bằng `BigInteger`. Một số thuật toán hoặc provider không xác định được chu kỳ có thể trả `BigInteger.ZERO`.

Nếu cần sắp xếp theo tên:

~~~java
var factories = RandomGeneratorFactory.all()
        .sorted((left, right) -> left.name().compareTo(right.name()))
        .toList();

factories.forEach(factory -> System.out.println(factory.name()));
~~~

`Stream.toList()` có từ Java 16 nên dùng được trong Java 17. Danh sách trả về là không sửa được; ở đây chỉ duyệt để in tên.

## 4. Danh sách thuật toán được Java SE 17 quy định

Tài liệu Java SE 17 liệt kê các thuật toán sau trong package `java.util.random`. Đây là danh sách thuật toán chuẩn được yêu cầu có; runtime cụ thể có thể cung cấp thêm thông qua provider.

| Nhóm | Tên thuật toán | `stateBits` | Equidistribution |
|---|---|---:|---:|
| LXM | `L32X64MixRandom` | 96 | 1 |
| LXM | `L64X128MixRandom` | 192 | 2 |
| LXM | `L64X128StarStarRandom` | 192 | 2 |
| LXM | `L64X256MixRandom` | 320 | 4 |
| LXM | `L64X1024MixRandom` | 1088 | 16 |
| LXM | `L128X128MixRandom` | 256 | 1 |
| LXM | `L128X256MixRandom` | 384 | 1 |
| LXM | `L128X1024MixRandom` | 1152 | 1 |
| Xoroshiro | `Xoroshiro128PlusPlus` | 128 | 1 |
| Xoshiro | `Xoshiro256PlusPlus` | 256 | 3 |
| Legacy | `Random` | 48 | 0 |
| Legacy | `SplittableRandom` | 64 | 1 |
| Legacy | `ThreadLocalRandom` | 64 | 1 |

Các thuật toán LXM kết hợp bộ sinh tuyến tính đồng dư (LCG), bộ sinh dựa trên XOR (XBG) và hàm trộn đầu ra. Tên thường thể hiện kích thước trạng thái của hai thành phần. `Mix` và `StarStar` mô tả kiểu trộn/scramble đầu ra.

Nhóm Xoroshiro/Xoshiro là các thuật toán dựa trên phép XOR và phép xoay bit. Nhóm Legacy bao gồm các lớp tồn tại trước Java 17. `SecureRandom` là API bảo mật quan trọng nhưng không được liệt kê như một hàng thuật toán cố định trong bảng PRNG này; nó dùng cơ chế provider và thuật toán bảo mật riêng.

### 4.1. Một số chu kỳ tiêu biểu

Chu kỳ (*period*) là số trạng thái trong chu kỳ trước khi một bộ sinh quay lại trạng thái đã gặp. Một vài giá trị trong bảng Java SE 17:

| Thuật toán | Chu kỳ |
|---|---|
| `Random` | \(2^{48}\) |
| `SplittableRandom` | \(2^{64}\) |
| `ThreadLocalRandom` | \(2^{64}\) |
| `Xoroshiro128PlusPlus` | \(2^{128} - 1\) |
| `Xoshiro256PlusPlus` | \(2^{256} - 1\) |
| `L64X128MixRandom` | \(2^{64}(2^{128} - 1)\) |
| `L64X256MixRandom` | \(2^{64}(2^{256} - 1)\) |
| `L64X1024MixRandom` | \(2^{64}(2^{1024} - 1)\) |

Chu kỳ lớn không đồng nghĩa với an toàn mật mã, không bảo đảm mọi ứng dụng sẽ có kết quả tốt hơn, và cũng không có nghĩa chương trình sẽ thực sự tạo ra mọi trạng thái trong thời gian sử dụng. Cần đọc các thuộc tính cùng với đặc điểm tải công việc.

## 5. Tra cứu và hiểu các thuộc tính của factory

`RandomGeneratorFactory` cung cấp nhiều thuộc tính để so sánh thuật toán. Các thuộc tính mô tả đặc điểm kỹ thuật; không nên dùng một chỉ số đơn lẻ như bảng xếp hạng chất lượng tổng quát.

### 5.1. `name()` và `group()`

- `name()` trả về tên thuật toán, ví dụ `L64X128MixRandom`.
- `group()` trả về nhóm thuật toán, ví dụ `LXM`, `Xoroshiro`, `Xoshiro` hoặc `Legacy`.

Tên là giá trị dùng để gọi `RandomGeneratorFactory.of(name)`. Nếu muốn kiểm soát rõ thuật toán trong một thí nghiệm hoặc cấu hình, hãy lưu tên này cùng cấu hình chạy.

### 5.2. `stateBits()`

`stateBits()` cho biết số bit được thuật toán dùng để duy trì trạng thái. Ví dụ `Random` có 48 bit, `Xoroshiro128PlusPlus` có 128 bit và `L64X256MixRandom` có 320 bit trạng thái.

Đây **không phải** số bit entropy chắc chắn nhận được từ seed, cũng không phải lời chứng nhận bảo mật. Nếu khởi tạo generator bằng seed dạng `long` thì đầu vào seed chỉ có 64 bit; trạng thái nội bộ lớn hơn không biến seed đó thành nguồn entropy 320 bit.

### 5.3. `period()`

Chu kỳ là số trạng thái trước khi bộ sinh quay lại trạng thái đã gặp. Factory trả về `BigInteger` vì chu kỳ có thể lớn hơn rất nhiều so với `long`.

Chu kỳ hữu ích khi mô phỏng tạo số lượng rất lớn giá trị, sinh hoán vị lớn hoặc so sánh khả năng lặp. Nhưng chu kỳ lớn không thay thế việc đánh giá chất lượng thống kê, tương quan giữa nhiều instance hoặc yêu cầu bảo mật.

### 5.4. `equidistribution()`

Thuộc tính này cho biết mức *k-equidistribution* mà thuật toán công bố. Nói đơn giản, nó mô tả đặc tính phân bố đều của các nhóm gồm nhiều giá trị liên tiếp trong chu kỳ, theo định nghĩa của thuật toán.

Ví dụ, tài liệu Java 17 nêu `L64X128MixRandom` có mức 2, `L64X256MixRandom` có mức 4 và `L64X1024MixRandom` có mức 16. Mức equidistribution cao có thể hữu ích khi thuật toán được dùng với tuple giá trị liên tiếp. Nó không có nghĩa thuật toán tự động nhanh hơn, tốt hơn trong mọi mô phỏng hoặc an toàn về mật mã hơn.

### 5.5. `isStatistical()`, `isStochastic()` và `isHardware()`

| Thuộc tính | Ý nghĩa |
|---|---|
| `isStatistical()` | Generator được tính bằng thuật toán số học và có tính xác định về mặt thống kê. |
| `isStochastic()` | Generator sử dụng nguồn bên ngoài hoặc entropy làm đầu vào. |
| `isHardware()` | Generator sử dụng thiết bị phần cứng để tạo đầu vào entropy. |

Một PRNG thuần thuật toán thường là statistical: với cùng trạng thái ban đầu và cùng trình tự lời gọi, nó có thể tái tạo chuỗi. Một nguồn stochastic phụ thuộc nguồn entropy bên ngoài nên không có cùng kiểu tái lập.

Các thuộc tính này mô tả cách tạo giá trị, không phải chứng nhận rằng bạn có thể dùng generator làm nguồn khóa hay token. Nếu cần an toàn mật mã, chọn `SecureRandom` và tuân thủ hướng dẫn của API bảo mật.

### 5.6. `isSplittable()`, `isJumpable()`, `isLeapable()` và `isArbitrarilyJumpable()`

- **Splittable:** có thể tách generator thành generator mới, với trạng thái được đặt ở vùng khác trong chu kỳ.
- **Jumpable:** có thể nhảy tới một vị trí cách xa trong chu kỳ theo bước nhảy được thuật toán định nghĩa.
- **Leapable:** hỗ trợ jump và leap với khoảng cách rất lớn.
- **Arbitrarily jumpable:** hỗ trợ nhảy theo khoảng cách do người dùng chỉ định.

Chúng hữu ích khi một phép tính được chia thành nhiều tác vụ và mỗi tác vụ cần một nguồn số giả ngẫu nhiên riêng. Không nên dùng chung một instance không thread-safe giữa nhiều luồng chỉ vì interface có tên `RandomGenerator`.

### 5.7. `isStreamable()` và `isDeprecated()`

- `isStreamable()` cho biết generator có thể tạo stream các giá trị ngẫu nhiên theo interface tương ứng.
- `isDeprecated()` cho biết hiện thực/thuật toán đã được đánh dấu deprecated hay chưa.

`RandomGeneratorFactory.all()` không trả về các factory đã deprecated theo hợp đồng Java 17. Thuộc tính deprecated vẫn hữu ích khi tra một factory theo tên hoặc đọc metadata của một hiện thực cụ thể.

## 6. Dùng factory để lọc theo nhu cầu

Sau khi hiểu thuộc tính, ta có thể tìm thuật toán có đặc điểm phù hợp thay vì chọn tên theo cảm tính.

Liệt kê generator có thể split:

~~~java
RandomGeneratorFactory.all()
        .filter(RandomGeneratorFactory::isSplittable)
        .forEach(factory ->
                System.out.println(factory.name()
                        + " stateBits=" + factory.stateBits()));
~~~

Tìm các thuật toán có trạng thái ít nhất 128 bit:

~~~java
RandomGeneratorFactory.all()
        .filter(factory -> factory.stateBits() >= 128)
        .forEach(factory ->
                System.out.println(factory.name()));
~~~

Lọc như vậy chỉ giúp thu hẹp danh sách. Bạn vẫn cần xem period, equidistribution, khả năng split/jump và mục đích thực tế. Ví dụ một thuật toán có 128 bit trạng thái không mặc nhiên tốt hơn thuật toán 96 bit cho mọi trường hợp.

### 6.1. Chọn theo tên rõ ràng

Nếu yêu cầu ứng dụng đã xác định thuật toán, tạo generator bằng tên:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator generator = factory.create(987654321L);
~~~

Nếu muốn sử dụng generator mặc định:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.getDefault();

System.out.println("Selected: " + factory.name());
RandomGenerator generator = factory.create();
~~~

`getDefault()` chọn factory đáp ứng yêu cầu tối thiểu có ít nhất 64 bit trạng thái. Tên thuật toán mặc định **không được bảo đảm giữ nguyên qua các phiên bản Java**, vì thuật toán có thể được cải thiện. Nếu kết quả cần tái lập theo cấu hình thí nghiệm, hãy chọn tên thuật toán tường minh.

## 7. Chọn thuật toán phù hợp theo tình huống

Tài liệu Java SE 17 đưa ra một số khuyến nghị theo loại công việc. Có thể dùng bảng sau làm điểm bắt đầu:

| Nhu cầu | Lựa chọn có thể cân nhắc | Lý do |
|---|---|---|
| Mục đích chung, mô phỏng hoặc game không cần mật mã | `L64X128MixRandom` | Cân bằng tốt giữa tốc độ, bộ nhớ và chu kỳ theo tài liệu Java 17. |
| Một luồng, ưu tiên nhỏ và nhanh | `Xoroshiro128PlusPlus` | Trạng thái nhỏ hơn và tốc độ tốt cho workload đơn luồng. |
| Thiết bị 32-bit, ít luồng | `L32X64MixRandom` | Có thể phù hợp với môi trường phần cứng 32-bit. |
| Nhiều luồng được tạo theo batch | Generator jumpable như `Xoroshiro128PlusPlus` hoặc `Xoshiro256PlusPlus`; hoặc generator splittable | Tạo vùng trạng thái khác nhau cho các luồng. |
| Nhiều tác vụ/luồng phát sinh động | `L64X128MixRandom` hoặc `L64X256MixRandom` | Thuộc nhóm splittable, phù hợp chia generator theo tác vụ. |
| Tạo số lượng instance rất lớn | `L128X128MixRandom` hoặc `L128X256MixRandom` | LCG parameter 128 bit làm giảm khả năng các instance dùng cùng chu kỳ trạng thái. |
| Cần đặc tính equidistribution cao cho tuple dài | `L64X256MixRandom` hoặc `L64X1024MixRandom` | Có mức 4 hoặc 16 theo tài liệu Java 17. |
| Mã bí mật, token, nonce bảo mật | `SecureRandom` | API được thiết kế cho yêu cầu ngẫu nhiên an toàn về mật mã. |

Đây là khuyến nghị định hướng, không phải kết quả benchmark cho mọi CPU hay ứng dụng. Với workload quan trọng về hiệu năng, hãy benchmark trên môi trường triển khai thật và dùng bộ kiểm tra thống kê phù hợp.

### 7.1. Khi nào dùng `Random`?

`Random` vẫn hợp lệ và hữu ích cho mã cũ cần tương thích hoặc ví dụ đơn giản. Tuy nhiên, thuật toán LCG của nó là thuật toán yếu nhất trong các PRNG được liệt kê trong package Java 17. Với code mới không có ràng buộc tương thích, nên cân nhắc các generator hiện đại trong `java.util.random`.

### 7.2. Khi nào dùng `ThreadLocalRandom`?

`ThreadLocalRandom.current()` cung cấp generator gắn với thread hiện tại, tiện cho các thao tác độc lập trong ứng dụng nhiều luồng:

~~~java
import java.util.concurrent.ThreadLocalRandom;

int portSuffix = ThreadLocalRandom.current().nextInt(1000, 10000);
~~~

Nó giảm tranh chấp khi nhiều thread cần tạo giá trị cùng lúc. Nó không phù hợp khi bạn cần quản lý seed để tái lập một chuỗi mô phỏng cụ thể; không khởi tạo bằng constructor hoặc cố đặt seed thủ công.

### 7.3. Khi nào dùng `SplittableRandom`?

`SplittableRandom` được thiết kế cho tính toán giả ngẫu nhiên có thể chia nhỏ, ví dụ parallel computation. Nó không thread-safe; thông thường mỗi tác vụ dùng một instance riêng:

~~~java
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(2026L);

SplittableRandom workerA = root.split();
SplittableRandom workerB = root.split();

int sampleA = workerA.nextInt(1, 100);
int sampleB = workerB.nextInt(1, 100);
~~~

`split()` tạo một generator mới cùng loại, có trạng thái được tách ra để sử dụng độc lập. Đây là cách phù hợp hơn so với chia sẻ một instance mutable cho nhiều worker.

### 7.4. Khi nào dùng `SecureRandom`?

Khi tạo token reset mật khẩu, khóa phiên, nonce hoặc dữ liệu cần khó đoán, dùng `SecureRandom`:

~~~java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
byte[] token = new byte[32];
secureRandom.nextBytes(token);
~~~

`SecureRandom` là API của Java Security và cũng là một `RandomGenerator` trong Java 17. Nó dùng provider và nguồn entropy của nền tảng. Không thay nó bằng `Random`, `SplittableRandom` hoặc một thuật toán LXM chỉ vì các thuật toán đó có chu kỳ lớn hay tốc độ cao.

## 8. Ví dụ chọn thuật toán theo thuộc tính

Giả sử ứng dụng mô phỏng muốn có generator có khả năng split. Ta có thể lọc factory rồi chọn thuật toán theo một tiêu chí đã thống nhất:

~~~java
import java.util.Comparator;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public final class SelectGenerator {
    private SelectGenerator() {
    }

    public static void main(String[] args) {
        var selected = RandomGeneratorFactory.all()
                .filter(RandomGeneratorFactory::isSplittable)
                .filter(factory -> !factory.isDeprecated())
                .max(Comparator.comparingInt(
                        factory -> factory.stateBits()))
                .orElseThrow(() ->
                        new IllegalStateException(
                                "No splittable generator available"));

        System.out.println("Selected: " + selected.name());
        System.out.println("Group: " + selected.group());
        System.out.println("State bits: " + selected.stateBits());
        System.out.println("Period: " + selected.period());

        RandomGenerator random = selected.create(2026L);
        System.out.println("Sample: " + random.nextDouble());
    }
}
~~~

Ví dụ này chọn factory có nhiều state bits nhất trong số các factory splittable. Đây là **minh họa cách truy vấn metadata**, không phải công thức tối ưu cho mọi ứng dụng. Nếu đã có quyết định thiết kế cụ thể, tên thuật toán tường minh sẽ dễ kiểm soát hơn việc tự chọn "lớn nhất".

`all()` đã loại các thuật toán deprecated theo hợp đồng API, nên bộ lọc `!factory.isDeprecated()` là lớp bảo vệ dễ đọc nhưng trong danh sách đó thường không làm thay đổi kết quả.

## 9. Seed và khả năng tái lập kết quả

Với PRNG xác định, seed là trạng thái khởi đầu hoặc dữ liệu dùng để khởi tạo trạng thái. Khi dùng cùng thuật toán, cùng seed và cùng trình tự gọi, ta có thể tái lập chuỗi giá trị trong cùng môi trường/phiên bản triển khai.

~~~java
RandomGenerator first =
        RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(12345L);

RandomGenerator second =
        RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(12345L);

System.out.println(first.nextInt());
System.out.println(second.nextInt());
~~~

Hai instance được tạo bằng cùng thuật toán và seed sẽ cho cùng giá trị ở lần gọi tương ứng trong một triển khai nhất quán. Khi viết test, seed cố định giúp tái hiện tình huống lỗi.

### 9.1. Ghi lại đủ thông tin để tái hiện

Nếu kết quả mô phỏng cần tái lập lâu dài, hãy ghi lại tên thuật toán, seed, phiên bản JDK và môi trường thực thi, trình tự lời gọi hoặc cách chia stream/tác vụ, cùng các tham số đầu vào của mô phỏng.

Không chỉ lưu mỗi seed nếu chương trình dùng `getDefault()`, vì thuật toán mặc định có thể thay đổi theo phiên bản. API factory cũng không hứa rằng mọi thuật toán/provider sẽ tạo chuỗi giống nhau trên mọi JDK.

### 9.2. Seed không phải mật khẩu

Không dùng seed cố định hoặc seed dễ đoán để tạo token bảo mật. Nếu kẻ tấn công biết thuật toán và seed, họ có thể tái tạo chuỗi PRNG xác định. Với mục đích bảo mật, hãy dùng `SecureRandom` và để provider xử lý việc lấy entropy.

## 10. Tạo số trong khoảng và phân phối

Chọn thuật toán là một quyết định; chọn **phân phối** của dữ liệu là quyết định khác. `RandomGenerator` cung cấp nhiều phương thức:

| Phương thức | Kết quả |
|---|---|
| `nextInt()` | Một `int` giả ngẫu nhiên trong toàn miền kiểu. |
| `nextInt(bound)` | Số nguyên từ 0 (bao gồm) đến bound (không bao gồm). |
| `nextInt(origin, bound)` | Số nguyên trong khoảng [origin, bound). |
| `nextDouble()` | Số thực từ 0.0 đến nhỏ hơn 1.0. |
| `nextDouble(origin, bound)` | Số thực trong khoảng [origin, bound). |
| `nextGaussian()` | Giá trị theo phân phối chuẩn có mean 0, độ lệch chuẩn 1. |
| `nextGaussian(mean, stddev)` | Phân phối chuẩn với mean và độ lệch chuẩn chỉ định. |
| `nextExponential()` | Giá trị theo phân phối mũ có mean 1. |

Để lấy số nguyên trong khoảng, hãy dùng overload có cận thay vì lấy modulo thủ công:

~~~java
int safe = random.nextInt(10, 21); // 10 đến 20
~~~

Tránh:

~~~java
int unsafe = Math.abs(random.nextInt()) % 11 + 10;
~~~

Cách modulo có thể tạo phân bố lệch khi số lượng giá trị nguồn không chia hết cho kích thước khoảng; `Math.abs(Integer.MIN_VALUE)` cũng vẫn là số âm do giới hạn biểu diễn số nguyên. Dùng API có cận giúp tránh hai lỗi này.

Nếu bài toán yêu cầu phân phối chuẩn, hãy dùng `nextGaussian` hoặc một phương pháp lấy mẫu phù hợp với phân phối cần mô phỏng.

## 11. Các sai lầm khi liệt kê và chọn thuật toán

| Sai lầm | Vì sao không đúng? | Cách làm phù hợp |
|---|---|---|
| Cho rằng thuật toán có period lớn nhất luôn tốt nhất. | Period không đo toàn bộ chất lượng, tốc độ, tương quan hoặc bảo mật. | Xem đồng thời workload, state, equidistribution, split/jump và benchmark. |
| Dùng `Random` cho mọi ứng dụng mới. | `Random` dùng LCG và được tài liệu Java 17 đánh giá là yếu nhất trong các PRNG của package. | Cân nhắc LXM hoặc thuật toán khác phù hợp. |
| Dùng LXM/Xoshiro để tạo token bảo mật. | PRNG mô phỏng không được thiết kế làm CSPRNG. | Dùng `SecureRandom`. |
| Dùng `getDefault()` nhưng kỳ vọng thuật toán luôn cố định. | Tên mặc định có thể thay đổi khi thuật toán được cải thiện. | Chọn tên rõ ràng nếu cần tính tái lập. |
| Chia sẻ một generator mutable giữa nhiều thread. | Phần lớn RandomGenerator không thread-safe. | Mỗi thread/task có instance riêng; dùng split hoặc jump khi phù hợp. |
| Dùng seed thời gian làm seed bảo mật. | Seed dễ đoán có thể làm chuỗi PRNG dễ dự đoán. | Dùng `SecureRandom` cho bí mật. |
| Coi `stateBits` là số bit entropy. | Đây là kích thước trạng thái nội bộ, không phải entropy chắc chắn của seed. | Xem seed và state là hai khái niệm riêng. |
| Chỉ nhìn `isSplittable` rồi kết luận các stream độc lập tuyệt đối. | Split hỗ trợ tạo instance khác vùng trạng thái; nó không thay thế đánh giá mô hình tính toán và thống kê. | Dùng theo hướng dẫn thuật toán, seed hợp lý và kiểm tra kết quả. |
| Dùng `nextInt() % bound` để lấy số trong khoảng. | Có thể gây modulo bias và lỗi với giá trị âm. | Dùng `nextInt(origin, bound)` hoặc `nextInt(bound)`. |

## 12. Bài tập thực hành

### Bài tập 1 — Liệt kê generator

Viết chương trình dùng `RandomGeneratorFactory.all()` để in tên và nhóm của mọi factory khả dụng. Sắp xếp kết quả theo tên và bỏ qua factory deprecated.

### Bài tập 2 — Đọc metadata

Với mỗi factory, in `stateBits()`, `period()` và `equidistribution()`. Tìm thuật toán có state bits lớn nhất và thuật toán có equidistribution cao nhất. Giải thích vì sao hai thuật toán này chưa chắc là lựa chọn nhanh nhất.

### Bài tập 3 — Chọn generator có khả năng split

Lọc danh sách factory theo `isSplittable()`. Chọn một tên thuật toán cụ thể, tạo instance với seed cố định và gọi `nextInt(1, 7)` mười lần. Chạy lại chương trình để quan sát tính tái lập.

### Bài tập 4 — Tách luồng cho hai worker

Dùng `SplittableRandom` với seed cố định, gọi `split()` để tạo hai generator cho hai tác vụ. Tạo 5 số từ mỗi generator và lưu kết quả. Giải thích vì sao không nên để hai worker gọi liên tục trên cùng một instance.

### Bài tập 5 — Phân biệt PRNG và CSPRNG

Viết ví dụ tạo 32 byte bằng `SecureRandom` và so sánh mục đích sử dụng với `L64X128MixRandom`. Nêu ví dụ nào phù hợp cho mô phỏng, ví dụ nào phù hợp cho token bảo mật.

### Gợi ý tự đối chiếu

- Bài 1: Dùng `RandomGeneratorFactory.all().sorted((a, b) -> a.name().compareTo(b.name()))` và `forEach`.
- Bài 2: `stateBits` đo trạng thái, `period` đo chu kỳ, `equidistribution` mô tả tính phân bố tuple; không chỉ số nào là benchmark tốc độ.
- Bài 3: Dùng `RandomGeneratorFactory.of("L64X128MixRandom").create(12345L)`.
- Bài 4: Mỗi worker dùng instance được split riêng, không chia sẻ cùng đối tượng mutable.
- Bài 5: `SecureRandom` dùng cho bí mật; LXM dùng cho mô phỏng hoặc workload không yêu cầu mật mã.

## 13. Quy trình chọn thuật toán trong dự án thực tế

Khi bắt đầu một chức năng cần sinh số giả ngẫu nhiên, hãy đi theo trình tự:

1. **Xác định yêu cầu bảo mật.** Nếu giá trị là token, nonce hoặc dữ liệu bí mật, chọn `SecureRandom`.
2. **Xác định kiểu workload.** Đơn luồng, đa luồng tạo theo batch hay nhiều tác vụ phát sinh động sẽ dẫn tới lựa chọn split/jump khác nhau.
3. **Xác định khả năng tái lập.** Nếu cần tái hiện test/mô phỏng, chọn thuật toán và seed tường minh; ghi lại phiên bản runtime.
4. **Liệt kê factory khả dụng.** Dùng `RandomGeneratorFactory.all()` để xem tên và thuộc tính thực tế.
5. **Lọc theo đặc tính cần thiết.** Xem `stateBits`, `period`, `equidistribution`, `isSplittable`, `isJumpable` và các thuộc tính liên quan.
6. **Chọn một vài ứng viên.** Dùng khuyến nghị của tài liệu Java 17 làm điểm xuất phát, sau đó benchmark trên workload thật.
7. **Kiểm tra phân phối đầu ra.** Chọn phương thức `nextInt`, `nextDouble`, `nextGaussian` hoặc thuật toán lấy mẫu phù hợp với mô hình.
8. **Ghi rõ quyết định.** Lưu tên thuật toán, seed và cấu hình để người khác có thể tái hiện kết quả.

Không cần chọn thuật toán phức tạp nhất cho một chức năng đơn giản. Một lựa chọn rõ ràng, phù hợp workload và được kiểm tra trong môi trường triển khai thường có giá trị hơn việc chọn chỉ theo một con số metadata.

## 14. Các điểm cần ghi nhớ

- Java 17 có package `java.util.random` và interface `RandomGenerator` để chuẩn hóa việc sinh giá trị giả ngẫu nhiên.
- `RandomGeneratorFactory.all()` liệt kê các factory khả dụng; `of(name)` tra một thuật toán; `create(seed)` tạo instance.
- Có thể xem `name`, `group`, `stateBits`, `period`, `equidistribution` và các cờ split/jump/leap/stream để hiểu đặc tính thuật toán.
- `getDefault()` chọn generator đáp ứng tối thiểu 64 bit trạng thái; tên thuật toán mặc định có thể thay đổi theo phiên bản.
- LXM và Xoroshiro/Xoshiro là các nhóm PRNG hiện đại có trong Java SE 17; `Random`, `ThreadLocalRandom` và `SplittableRandom` là các lựa chọn legacy vẫn dùng được.
- `SecureRandom` dành cho yêu cầu an toàn mật mã; không thay bằng PRNG mô phỏng.
- Generator thường không thread-safe. Với xử lý song song, cân nhắc mỗi worker một instance, split hoặc jump.
- Dùng overload có cận như `nextInt(origin, bound)` thay cho phép modulo thủ công.
- Period, state bits và equidistribution mô tả những khía cạnh khác nhau; không phải thước đo bảo mật hay tốc độ duy nhất.

### Tài liệu tham khảo

- [Java SE 17 API — Package java.util.random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html).
- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html).
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html).
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html).
- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356).
