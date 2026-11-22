# Tạo bộ sinh bằng RandomGenerator.of và RandomGeneratorFactory

## 1. Bối cảnh: API sinh số ngẫu nhiên trong Java 17

Java 17 đưa vào gói `java.util.random` một API thống nhất cho các bộ sinh số ngẫu nhiên. Thành phần trung tâm là interface **`RandomGenerator`**: code sử dụng có thể gọi một hợp đồng chung để lấy `int`, `long`, `float`, `double`, `boolean` hoặc các stream số giả ngẫu nhiên mà không phải phụ thuộc trực tiếp vào một class generator cụ thể.

Để tạo generator, Java cung cấp hai cách thường dùng:

- **`RandomGenerator.of(String name)`:** chọn một thuật toán theo tên và tạo ngay một instance.
- **`RandomGeneratorFactory.of(String name)`:** lấy factory cho một thuật toán. Factory có thể tạo nhiều instance, nhận seed, cung cấp metadata và hỗ trợ chọn thuật toán dựa trên đặc tính.

Hai API có chung mục tiêu chọn thuật toán, nhưng phục vụ các nhu cầu khác nhau:

~~~text
Chỉ cần một generator
    RandomGenerator.of("L64X128MixRandom")
                |
                v
        RandomGenerator instance

Cần factory để tạo nhiều instance / seed / xem metadata
    RandomGeneratorFactory.of("L64X128MixRandom")
                |
                v
        RandomGeneratorFactory
                |
       +--------+---------+
       |        |         |
    create() create(seed) metadata
       |        |
       v        v
    RandomGenerator instance
~~~

Đây là API phù hợp cho các bài toán mô phỏng, game, kiểm thử, lấy mẫu dữ liệu, tạo dữ liệu thử và tính toán cần số giả ngẫu nhiên. **Không được mặc định mọi thuật toán trong `RandomGenerator` đều an toàn về mật mã.** Nếu cần token xác thực, reset password, khóa hoặc nonce bảo mật, hãy sử dụng `SecureRandom`.

## 2. RandomGenerator: hợp đồng chung để sinh giá trị

### 2.1. Tạo instance nhanh bằng `RandomGenerator.of`

Ví dụ:

~~~java
import java.util.random.RandomGenerator;

public class RandomGeneratorQuickStart {
    public static void main(String[] args) {
        RandomGenerator random =
                RandomGenerator.of("L64X128MixRandom");

        int dice = random.nextInt(1, 7);
        double ratio = random.nextDouble(0.0, 1.0);
        boolean accepted = random.nextBoolean();

        System.out.println("Dice: " + dice);
        System.out.println("Ratio: " + ratio);
        System.out.println("Accepted: " + accepted);
    }
}
~~~

`RandomGenerator.of(name)` trả về một instance sử dụng thuật toán được chỉ định. Nó tương đương ý tưởng chọn implementation bằng tên và tạo generator bằng cách khởi tạo không tham số.

Các điểm cần nhớ:

- `name` là tên thuật toán, ví dụ `"L64X128MixRandom"`.
- Nếu `name == null`, phương thức ném `NullPointerException`.
- Nếu không tìm thấy thuật toán có tên đó, phương thức ném `IllegalArgumentException`.
- Phương thức này **không nhận seed**. Nếu cần seed tường minh, dùng `RandomGeneratorFactory`.

### 2.2. Những phương thức sinh số thường dùng

Sau khi có một `RandomGenerator`, có thể gọi các phương thức:

| Phương thức | Kết quả |
|---|---|
| `nextInt()` | Một `int` giả ngẫu nhiên trong miền của kiểu |
| `nextInt(bound)` | `int` từ 0 inclusive đến `bound` exclusive |
| `nextInt(origin, bound)` | `int` từ `origin` inclusive đến `bound` exclusive |
| `nextLong()` | Một `long` giả ngẫu nhiên |
| `nextLong(origin, bound)` | `long` trong khoảng nửa mở |
| `nextFloat()` | `float` từ 0.0 inclusive đến 1.0 exclusive |
| `nextDouble()` | `double` từ 0.0 inclusive đến 1.0 exclusive |
| `nextDouble(origin, bound)` | `double` trong khoảng nửa mở |
| `nextBoolean()` | Một giá trị boolean |
| `nextBytes(byte[] bytes)` | Điền byte giả ngẫu nhiên vào mảng |
| `nextGaussian()` | Một giá trị theo phân phối chuẩn, trung bình 0 và độ lệch chuẩn 1 |
| `nextExponential()` | Một giá trị không âm theo phân phối mũ, trung bình 1 |

Ví dụ:

~~~java
RandomGenerator random =
        RandomGenerator.of("L64X128MixRandom");

int index = random.nextInt(0, 100);
long orderNumber = random.nextLong(1_000_000L, 9_000_000L);
double probability = random.nextDouble(0.0, 1.0);
double normalValue = random.nextGaussian();
~~~

Với các overload có `origin` và `bound`, biên dưới được bao gồm, biên trên bị loại trừ. Ví dụ `nextInt(1, 7)` tạo số từ 1 đến 6, thích hợp mô phỏng một viên xúc xắc sáu mặt.

Các khoảng không hợp lệ (ví dụ `origin >= bound`, hoặc một số giới hạn không hữu hạn đối với API floating point) có thể làm phương thức ném `IllegalArgumentException`. Hãy xác định rõ miền đầu vào thay vì tự tính bằng phép modulo.

### 2.3. Tạo stream số giả ngẫu nhiên

`RandomGenerator` còn cung cấp `ints()`, `longs()` và `doubles()`:

~~~java
import java.util.random.RandomGenerator;
import java.util.List;

public class RandomStreams {
    public static void main(String[] args) {
        RandomGenerator random =
                RandomGenerator.of("L64X128MixRandom");

        List<Integer> sample = random.ints(10, 1, 7)
                .boxed()
                .toList();

        System.out.println(sample);

        double average = random.doubles(1_000, 0.0, 1.0)
                .average()
                .orElseThrow();

        System.out.println("Average: " + average);
    }
}
~~~

Trong ví dụ:

- `ints(10, 1, 7)` tạo stream có 10 số nguyên, mỗi số nằm trong `[1, 7)`.
- `boxed()` chuyển `IntStream` thành `Stream<Integer>` để thu thập vào danh sách.
- `doubles(1_000, 0.0, 1.0)` tạo 1.000 số double trong khoảng `[0.0, 1.0)`.
- `average()` trả về `OptionalDouble`, vì một stream rỗng không có trung bình.

Stream được tạo từ generator có thể dùng với pipeline Stream API. Tuy nhiên, stream số và stream các **generator instance** là hai khái niệm khác nhau: `ints()` tạo số nguyên, còn `rngs()`/`splits()` ở các interface chuyên biệt tạo ra những bộ sinh mới.

## 3. RandomGeneratorFactory: tạo nhiều generator cùng thuật toán

### 3.1. Lấy factory bằng `of(String name)`

`RandomGeneratorFactory<T>` là factory class dành cho một thuật toán. Ví dụ:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class FactoryQuickStart {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create();
        RandomGenerator second = factory.create();

        System.out.println(first.nextInt(1, 101));
        System.out.println(second.nextInt(1, 101));
    }
}
~~~

Factory không phải là generator đang có state của chuỗi số. Nó là đối tượng mô tả/khởi tạo **một loại generator**. Mỗi lần gọi `create()` sẽ tạo một instance mới của thuật toán đã chọn.

Điều này hữu ích khi:

- Một ứng dụng cần nhiều generator cùng thuật toán.
- Mỗi worker/thread cần instance riêng.
- Cần tạo generator có seed để kiểm thử tái lập.
- Cần xem metadata trước khi chọn thuật toán.
- Muốn thay đổi thuật toán tại cấu hình mà không sửa logic sử dụng `RandomGenerator`.

### 3.2. Ba cách tạo instance của factory

Java 17 có ba overload:

| Cách tạo | Ý nghĩa |
|---|---|
| `factory.create()` | Tạo generator bằng cách khởi tạo không tham số, dùng cơ chế seed của implementation |
| `factory.create(long seed)` | Yêu cầu tạo generator từ seed kiểu `long` |
| `factory.create(byte[] seed)` | Yêu cầu tạo generator từ mảng byte seed |

Ví dụ:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator randomA = factory.create();
RandomGenerator randomB = factory.create(20261115L);
RandomGenerator randomC = factory.create(
        new byte[] { 10, 20, 30, 40, 50, 60, 70, 80 }
);
~~~

Không phải thuật toán nào cũng hỗ trợ mọi dạng seed. Theo hợp đồng của API, nếu thuật toán không hỗ trợ `long` seed hoặc `byte[]` seed tương ứng, phương thức `create(seed)` có thể chuyển sang hành vi của `create()`. Vì vậy **không được mặc định rằng truyền seed luôn tạo được chuỗi tái lập**.

Với các thuật toán PRNG xác định có hỗ trợ seed (chẳng hạn LXM được chọn tường minh), cùng thuật toán, cùng seed và cùng chuỗi lời gọi sẽ cho chuỗi kết quả tái lập trong cùng hợp đồng implementation. Nếu cần kết quả bit-for-bit lâu dài qua các môi trường, hãy cố định thuật toán, phiên bản runtime/provider và trình tự lời gọi; đừng dựa vào một lựa chọn default có thể thay đổi.

### 3.3. Phân biệt `RandomGenerator.of` và `RandomGeneratorFactory.of`

| Tiêu chí | `RandomGenerator.of(name)` | `RandomGeneratorFactory.of(name)` |
|---|---|---|
| Giá trị trả về | Một `RandomGenerator` | Một `RandomGeneratorFactory` |
| Tạo instance | Tạo ngay một instance | Gọi `create()` hoặc `create(seed)` |
| Chỉ định seed | Không có tham số seed | Có overload `long` và `byte[]` |
| Tạo nhiều instance | Gọi lại `of(name)` | Tái sử dụng factory và gọi `create` nhiều lần |
| Đọc metadata thuật toán | Không trực tiếp qua factory | Có `name()`, `group()`, `period()`, `stateBits()`... |
| Dò thuật toán theo thuộc tính | Không | Kết hợp `all()` với metadata |
| Khi nên dùng | Cần generator nhanh, code đơn giản | Cần cấu hình, seed, nhiều instance hoặc chọn thuật toán |

Một quy tắc thực tế: nếu bạn chỉ cần một generator để dùng trong một method, `RandomGenerator.of` thường đủ. Nếu ứng dụng cần seed, cấu hình thuật toán hoặc quản lý nhiều generator, dùng `RandomGeneratorFactory`.

## 4. Liệt kê các thuật toán khả dụng với `RandomGeneratorFactory.all()`

### 4.1. API `all()`

`RandomGeneratorFactory.all()` trả về một stream các factory khả dụng. Đây là cách phù hợp để khám phá thuật toán được runtime hiện tại cung cấp:

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

Kết quả cụ thể phụ thuộc JDK/provider đang chạy. `all()` trả các factory khả dụng và **không bao gồm generator đã bị đánh dấu deprecated**. Một JDK implementation hoặc provider có thể cung cấp thêm thuật toán ngoài danh sách bắt buộc của Java SE.

Không nên hardcode một danh sách tự suy đoán rồi coi đó là đầy đủ. Nếu chương trình cho phép cấu hình thuật toán, hãy kiểm tra tên bằng factory và xử lý lỗi rõ ràng.

### 4.2. Các nhóm thuật toán được cung cấp trong Java SE 17

Tài liệu Java SE 17 mô tả ba nhóm thuật toán chính:

| Nhóm | Ví dụ tên | Đặc điểm khái quát |
|---|---|---|
| Legacy | `Random`, `SplittableRandom`, `ThreadLocalRandom` | Các API/implementation tồn tại trước Java 17; vẫn có thể được dùng qua những hợp đồng phù hợp |
| LXM | `L64X128MixRandom`, `L64X256MixRandom`, `L128X256MixRandom` | Kết hợp Linear Congruential Generator (LCG), Xor-Based Generator (XBG) và hàm mixing |
| Xoroshiro/Xoshiro | `Xoroshiro128PlusPlus`, `Xoshiro256PlusPlus` | Nhóm thuật toán XBG có trạng thái và chu kỳ lớn, hỗ trợ jump/leap theo implementation |

Các tên thuật toán Java SE 17 quy định có thể tra cứu trong tài liệu package `java.util.random`. Một số tên LXM khác gồm:

- `L32X64MixRandom`
- `L64X128StarStarRandom`
- `L64X1024MixRandom`
- `L128X128MixRandom`
- `L128X1024MixRandom`

Danh sách thuật toán và trạng thái deprecated có thể thay đổi trong các phiên bản Java về sau. Vì thế, khi viết ứng dụng cần chạy trên nhiều JDK/provider, hãy dùng `all()` hoặc xử lý `IllegalArgumentException` khi gọi `of(name)`.

**Ngoại lệ cần nhớ:** `ThreadLocalRandom` có trong hệ sinh thái `RandomGenerator`, nhưng chỉ được truy cập qua `ThreadLocalRandom.current()`; không coi nó như một thuật toán thông thường có thể tự tạo instance bằng constructor/factory tùy ý.

### 4.3. Chọn thuật toán theo mục tiêu

Không có một thuật toán tốt nhất cho tất cả tình huống. Những đặc tính thường phải cân nhắc:

- Tốc độ sinh giá trị.
- Kích thước state và bộ nhớ.
- Chu kỳ (period).
- Khả năng phân phối đều các tuple liên tiếp (equidistribution).
- Khả năng split hoặc jump để tổ chức nhiều luồng.
- Mức độ phù hợp với workload và yêu cầu thống kê.

Với ứng dụng không có yêu cầu đặc biệt, tài liệu Java 17 đề xuất `L64X128MixRandom` như một lựa chọn cân bằng giữa tốc độ, không gian và chu kỳ. Với ứng dụng đơn luồng cần kích thước nhỏ/tốc độ cao, `Xoroshiro128PlusPlus` có thể phù hợp. Với nhiều tác vụ được tạo động, các thuật toán LXM splittable như `L64X128MixRandom` hoặc `L64X256MixRandom` là lựa chọn đáng cân nhắc.

Đây là hướng dẫn lựa chọn theo loại workload, không phải cam kết benchmark cho mọi máy. Hãy đo trên workload thực tế nếu hiệu năng là tiêu chí quan trọng.

## 5. Dùng seed để tái lập chuỗi số

### 5.1. Seed là gì?

Đối với một PRNG xác định, seed là dữ liệu khởi tạo trạng thái ban đầu. Từ trạng thái đó, thuật toán tính ra chuỗi giá trị tiếp theo.

Ví dụ:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SeededGenerator {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(123456789L);
        RandomGenerator second = factory.create(123456789L);

        for (int i = 0; i < 5; i++) {
            System.out.println(
                    first.nextInt() + " | " + second.nextInt()
            );
        }
    }
}
~~~

Hai generator được khởi tạo bằng cùng thuật toán LXM và cùng seed. Khi chúng nhận cùng chuỗi lời gọi, các giá trị tương ứng được tạo ra theo cùng chuỗi giả ngẫu nhiên của implementation.

### 5.2. Khi nào cần seed cố định?

Seed cố định hữu ích khi:

- Tái hiện một lỗi xuất hiện trong một lần mô phỏng.
- Làm cho dữ liệu test có thể lặp lại.
- So sánh hai phiên bản thuật toán với cùng đầu vào.
- Debug một tình huống hiếm trong game hoặc mô phỏng.
- Ghi lại trạng thái thí nghiệm để nhóm khác tái chạy.

Trong hệ thống thử nghiệm, nên ghi cùng seed với thuật toán, phiên bản JDK và cấu hình liên quan. Chỉ lưu seed mà không lưu tên thuật toán có thể không đủ để tái tạo chuỗi.

### 5.3. Cùng seed không có nghĩa mọi lời gọi trả cùng kết quả

Trạng thái generator thay đổi sau khi sinh giá trị. Nếu hai đoạn code gọi method theo thứ tự khác nhau, chúng tiêu thụ chuỗi khác nhau:

~~~java
RandomGenerator a =
        RandomGeneratorFactory.of("L64X128MixRandom").create(42L);
RandomGenerator b =
        RandomGeneratorFactory.of("L64X128MixRandom").create(42L);

int a1 = a.nextInt();
int a2 = a.nextInt();

int b1 = b.nextInt();
double extra = b.nextDouble(); // tiêu thụ trạng thái trước lời gọi tiếp theo
int b2 = b.nextInt();
~~~

`a1` và `b1` tương ứng cùng vị trí chuỗi. Nhưng `a2` và `b2` không còn là hai lời gọi ở cùng vị trí vì generator `b` đã được gọi thêm `nextDouble()`.

Một thay đổi tưởng nhỏ như thêm lời gọi random trong logging, nhánh điều kiện hoặc một helper có thể làm thay đổi toàn bộ kết quả phía sau. Nếu cần tái lập thí nghiệm, hãy kiểm soát thứ tự tiêu thụ random và tránh dùng chung một generator cho nhiều phần logic không liên quan.

### 5.4. Không coi seed là cơ chế bảo mật

Seed cố định giúp tái lập, đồng thời khiến chuỗi có thể dự đoán nếu người khác biết thuật toán và seed. Không dùng seed cố định, timestamp, ID đơn hàng hoặc dữ liệu công khai làm nguồn tạo token bảo mật.

Với mã xác thực, session secret, reset token hoặc khóa, hãy dùng `SecureRandom` và quản lý entropy theo yêu cầu bảo mật. `RandomGenerator` là một giao diện chung, **không phải chứng nhận cryptographic security**.

## 6. Đọc metadata của thuật toán

`RandomGeneratorFactory` không chỉ tạo instance. Nó còn cung cấp thông tin giúp đánh giá thuật toán.

| Method | Ý nghĩa |
|---|---|
| `name()` | Tên thuật toán |
| `group()` | Nhóm thuật toán |
| `stateBits()` | Số bit được thuật toán sử dụng để duy trì trạng thái |
| `period()` | Chu kỳ của thuật toán, trả về `BigInteger`; có thể là zero nếu không xác định |
| `equidistribution()` | Mức equidistribution được mô tả cho thuật toán |
| `isStatistical()` | Generator được tính bằng thuật toán số học và có tính xác định thống kê |
| `isStochastic()` | Generator sử dụng nguồn bên ngoài/entropy làm đầu vào |
| `isHardware()` | Generator sử dụng thiết bị phần cứng tạo entropy |
| `isSplittable()` | Có thể tạo generator riêng bằng cơ chế split |
| `isJumpable()` | Có thể nhảy đến vị trí xa hơn trong chu kỳ theo cơ chế jump |
| `isLeapable()` | Có khả năng leap xa hơn jump |
| `isArbitrarilyJumpable()` | Có thể jump một khoảng do người dùng chỉ định |
| `isStreamable()` | Có thể tạo stream các generator |
| `isDeprecated()` | Thuật toán đã được đánh dấu deprecated hay chưa |

### 6.1. Phân biệt state bits, period và equidistribution

Ba thông tin này không đồng nghĩa:

- **State bits** là số bit được dùng để duy trì trạng thái. Nhiều bit trạng thái thường cho phép không gian trạng thái lớn hơn, nhưng không đủ để kết luận chất lượng thuật toán.
- **Period** là số trạng thái/độ dài chu kỳ trước khi chuỗi lặp lại. Đây là số rất lớn nên API trả `BigInteger`.
- **Equidistribution** mô tả tính phân phối đều của các tuple liên tiếp ở một số chiều nhất định. Ví dụ, generator 4-equidistributed có tính chất được chứng minh về các tuple gồm bốn giá trị liên tiếp theo định nghĩa thuật toán.

Đừng chọn generator chỉ dựa trên một con số. Chu kỳ rất dài không tự động chứng minh thuật toán phù hợp với yêu cầu thống kê, và state bits lớn không tự động có nghĩa tốc độ cao.

### 6.2. In metadata để khảo sát

~~~java
import java.util.random.RandomGeneratorFactory;

public class GeneratorMetadata {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
                .filter(factory -> factory.isSplittable())
                .sorted((left, right) ->
                        left.name().compareTo(right.name()))
                .forEach(factory -> {
                    System.out.println("Name: " + factory.name());
                    System.out.println("Group: " + factory.group());
                    System.out.println("State bits: " + factory.stateBits());
                    System.out.println("Period: " + factory.period());
                    System.out.println(
                            "Equidistribution: " +
                                    factory.equidistribution()
                    );
                    System.out.println();
                });
    }
}
~~~

Ví dụ này lọc các factory có khả năng split và in một số thuộc tính. Danh sách thực tế tùy thuộc các factory khả dụng trong runtime.

## 7. Chọn factory bằng đặc tính thay vì hardcode tên

### 7.1. Chọn generator có period lớn nhất trong nhóm splittable

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SelectByPeriod {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> selected =
                RandomGeneratorFactory.all()
                        .filter(factory -> factory.isSplittable())
                        .max((left, right) ->
                                left.period().compareTo(right.period()))
                        .orElseThrow(() ->
                                new IllegalStateException(
                                        "Không có generator splittable"
                                ));

        System.out.println("Selected: " + selected.name());
        System.out.println("Period: " + selected.period());

        RandomGenerator random = selected.create();
        System.out.println(random.nextLong());
    }
}
~~~

`max` so sánh `BigInteger` từ `period()`. Đây là ví dụ minh họa lựa chọn theo metadata; trong ứng dụng thật, nên xác định yêu cầu trước, chẳng hạn cần splittable, chu kỳ tối thiểu hoặc equidistribution phù hợp.

Nếu một factory có `period() == BigInteger.ZERO`, nghĩa là period không xác định theo API. Không nên diễn giải zero thành chu kỳ bằng không hoặc coi nó là period ngắn nhất theo nghĩa thuật toán.

### 7.2. Chọn theo capability

Ví dụ muốn tạo generator cho workload có nhiều tác vụ được tạo động:

~~~java
RandomGeneratorFactory<RandomGenerator> selected =
        RandomGeneratorFactory.all()
                .filter(RandomGeneratorFactory::isSplittable)
                .filter(factory -> factory.stateBits() >= 128)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException(
                                "Không tìm thấy generator phù hợp"
                        ));
~~~

Điều kiện `stateBits() >= 128` ở đây chỉ là một tiêu chí cấu hình ví dụ, không phải ngưỡng tối ưu phổ quát. Nên xác định capability thực sự cần thiết và kiểm tra thuật toán đã chọn trên JDK/provider triển khai.

### 7.3. Factory có thể được kiểm tra trước khi tạo

`of(name)` ném `IllegalArgumentException` khi không có thuật toán tương ứng:

~~~java
static RandomGeneratorFactory<RandomGenerator> findFactory(
        String algorithmName
) {
    try {
        return RandomGeneratorFactory.of(algorithmName);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Thuật toán RNG không khả dụng: " + algorithmName,
                ex
        );
    }
}
~~~

Nếu tên thuật toán đến từ file cấu hình, API quản trị hoặc biến môi trường, nên validate lúc khởi động ứng dụng để lỗi cấu hình được phát hiện sớm.

Không bắt `RuntimeException` chung chung rồi âm thầm chuyển sang một thuật toán bất kỳ. Việc fallback có thể làm thay đổi tính tái lập, đặc tính thống kê hoặc yêu cầu vận hành.

## 8. Chọn thuật toán LXM trong các ứng dụng thông thường

### 8.1. Cấu trúc tên LXM

Những tên dạng:

```text
L64X128MixRandom
L64X256MixRandom
L128X128MixRandom
```

thể hiện các tham số chính của thuật toán:

- `L` là thành phần Linear Congruential Generator (LCG).
- `X` là thành phần Xor-Based Generator (XBG).
- Số sau `L` cho biết số bit trạng thái của LCG subgenerator.
- Số sau `X` cho biết số bit trạng thái của XBG subgenerator.
- `Mix` biểu thị việc sử dụng hàm mixing; `StarStar` biểu thị cách scrambler tương ứng.

LXM kết hợp trạng thái của hai subgenerator để tạo output và cập nhật state. Mục tiêu là cải thiện chất lượng thống kê, chu kỳ và khả năng mở rộng so với việc chỉ dựa trên một LCG đơn giản.

### 8.2. Một số gợi ý theo workload

| Workload | Thuật toán/nhóm có thể cân nhắc | Lý do |
|---|---|---|
| Ứng dụng thông thường, chưa có yêu cầu đặc biệt | `L64X128MixRandom` | Cân bằng tốc độ, bộ nhớ và chu kỳ theo tài liệu Java 17 |
| Một luồng, cần kích thước nhỏ và tốc độ cao | `Xoroshiro128PlusPlus` | State nhỏ và tốc độ cao trong hướng dẫn chọn thuật toán |
| Môi trường phần cứng 32-bit, một hoặc ít thread | `L32X64MixRandom` | Cấu hình state phù hợp hơn cho môi trường này |
| Nhiều thread đã xác định trước | Jumpable hoặc splittable generator | Có cơ chế tách các vùng/instance generator |
| Nhiều tác vụ được tạo động | LXM splittable như `L64X128MixRandom` | Có thể split để tạo generator con |
| Tạo rất nhiều generator, hàng triệu instance | Cân nhắc LXM có LCG subgenerator 128-bit như `L128X128MixRandom` | Giảm khả năng nhiều instance dùng cùng state cycle |
| Sinh tuple liên tiếp có yêu cầu equidistribution | Chọn theo giá trị `equidistribution()` | Cần tính chất phân phối phù hợp với tuple dimension |
| Mật mã, token, secret | `SecureRandom` | Cần generator có đặc tính bảo mật mật mã |

Đây là hướng dẫn chọn ban đầu, không thay thế kiểm thử thống kê, đo hiệu năng hoặc đánh giá an ninh theo yêu cầu ứng dụng.

## 9. Generator trong môi trường đa luồng

### 9.1. Không mặc định một instance là thread-safe

Các đối tượng triển khai `RandomGenerator` **không bắt buộc phải thread-safe**. Nhiều implementation không được thiết kế để nhiều thread cùng gọi trên một instance.

Không nên mặc định viết:

~~~java
private static final RandomGenerator RANDOM =
        RandomGenerator.of("L64X128MixRandom");

// Nhiều thread cùng gọi RANDOM.nextInt() mà không có chiến lược riêng.
~~~

Các hướng thường dùng:

- Mỗi thread có generator riêng.
- Dùng generator hỗ trợ split để tạo instance con.
- Với generator hỗ trợ jump/leap, phân chia vùng chu kỳ theo mô hình phù hợp.
- Dùng `ThreadLocalRandom.current()` trong những trường hợp phù hợp với API đó.

### 9.2. SplittableGenerator

`RandomGenerator.SplittableGenerator` là sub-interface dành cho generator có khả năng **split** thành các generator khác. Instance mới được tách từ instance nguồn; mục tiêu là các chuỗi tạo ra có tính độc lập thống kê ở mức gần đúng theo thiết kế thuật toán.

Một số LXM generator triển khai interface này, ví dụ `L64X128MixRandom`.

~~~java
import java.util.random.RandomGenerator;

public class SplitExample {
    public static void main(String[] args) {
        RandomGenerator generator =
                RandomGenerator.of("L64X128MixRandom");

        if (!(generator instanceof
                RandomGenerator.SplittableGenerator root)) {
            throw new IllegalStateException(
                    "Generator không hỗ trợ split"
            );
        }

        RandomGenerator workerA = root.split();
        RandomGenerator workerB = root.split();

        System.out.println(workerA.nextInt());
        System.out.println(workerB.nextInt());
    }
}
~~~

Việc kiểm tra `instanceof` giúp code không giả định rằng mọi thuật toán được chọn đều splittable. Nếu tên thuật toán là hằng số đã biết và tài liệu đảm bảo capability, có thể thiết kế cấu hình cụ thể hơn.

### 9.3. Tạo stream các generator con

Vì `SplittableGenerator` cũng là `StreamableGenerator`, có thể tạo nhiều generator:

~~~java
import java.util.random.RandomGenerator;

public class SplitStreamExample {
    public static void main(String[] args) {
        RandomGenerator candidate =
                RandomGenerator.of("L64X128MixRandom");

        if (!(candidate instanceof
                RandomGenerator.SplittableGenerator root)) {
            throw new IllegalStateException("Cần generator splittable");
        }

        long[] totals = root.splits(4)
                .parallel()
                .mapToLong(workerRandom ->
                        workerRandom.ints(1_000, 0, 100).sum())
                .toArray();

        for (long total : totals) {
            System.out.println(total);
        }
    }
}
~~~

Mỗi tác vụ nhận một generator riêng; không có nhiều worker cùng gọi trên một instance generator duy nhất. Đây là mô hình phù hợp với công việc có thể chia thành các phần độc lập như mô phỏng Monte Carlo.

Không được nhầm rằng split bảo đảm độc lập toán học tuyệt đối trong mọi tình huống. API nói đến kỳ vọng độc lập thống kê; chất lượng thực tế phụ thuộc thuật toán và cách sử dụng.

### 9.4. Jumpable và Leapable

Một số thuật toán cung cấp các capability:

- **JumpableGenerator:** nhảy đến vị trí xa hơn trong chu kỳ, thường theo khoảng cách lớn được xác định bởi thuật toán.
- **LeapableGenerator:** có khả năng leap xa hơn jump.
- **ArbitrarilyJumpableGenerator:** cho phép nhảy theo khoảng cách do người dùng chỉ định.

Các capability này hữu ích khi muốn phân chia một chuỗi thành các vùng riêng cho nhiều worker được xác định trước. Chúng khác với `split()`: jump/leap di chuyển vị trí trên chu kỳ của một thuật toán, còn split tạo instance mới theo cơ chế của generator.

Hãy kiểm tra `factory.isJumpable()`, `isLeapable()`, `isArbitrarilyJumpable()` trước khi phụ thuộc vào capability. Không ép kiểu một generator tùy ý sang sub-interface nếu chưa xác nhận implementation.

## 10. Lựa chọn seed và tính tái lập trong hệ thống thực tế

### 10.1. Ghi lại cấu hình generator

Khi chạy một thí nghiệm hoặc mô phỏng cần tái lập, có thể ghi lại:

~~~text
algorithm = L64X128MixRandom
seed = 20261115
jdk = 17
call-sequence-version = simulation-v3
~~~

Thông tin này hữu ích hơn việc chỉ ghi một giá trị seed. Nếu đổi thuật toán nhưng giữ nguyên seed, chuỗi sẽ khác. Nếu thêm một lời gọi random giữa pipeline, các giá trị phía sau cũng thay đổi.

### 10.2. Đừng nhầm `getDefault()` với lựa chọn thuật toán cố định

Có hai API mặc định:

~~~java
RandomGenerator random = RandomGenerator.getDefault();

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.getDefault();
RandomGenerator another = factory.create();
~~~

`getDefault()` chọn generator đáp ứng yêu cầu tối thiểu về số state bits (ít nhất 64). Tài liệu nêu rõ **không có bảo đảm phương thức sẽ trả cùng thuật toán qua các phiên bản Java** vì thuật toán có thể được cải thiện.

Do đó:

- Dùng default khi không có yêu cầu gắn với tên thuật toán cụ thể.
- Chọn tên tường minh bằng `of(name)` khi cần kiểm soát thuật toán.
- Dùng `create(seed)` với thuật toán hỗ trợ seed nếu cần tái lập.
- Không ghi kết quả default generator vào golden file rồi giả định mọi JDK tương lai tạo đúng chuỗi cũ.

### 10.3. Tạo generator theo cấu hình

Ví dụ:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class ConfiguredRandom {
    static RandomGenerator create(String algorithm, long seed) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of(algorithm);
        return factory.create(seed);
    }

    public static void main(String[] args) {
        String algorithm = "L64X128MixRandom";
        long seed = 12345L;

        RandomGenerator random = create(algorithm, seed);
        System.out.println(random.nextLong());
    }
}
~~~

Trong ứng dụng thực tế, nên validate `algorithm` khi nạp cấu hình và thông báo rõ nếu thuật toán không có trong runtime. Nếu seed là dữ liệu đầu vào, cần xác định nguồn, quyền truy cập và cách lưu trữ; seed dùng cho kiểm thử không nên bị nhầm với secret bảo mật.

## 11. Phân biệt PRNG thông thường và SecureRandom

### 11.1. RandomGenerator không đồng nghĩa cryptographically secure

`RandomGenerator` là một giao diện giao tiếp chung. Nhiều implementation được thiết kế cho chất lượng thống kê, hiệu năng, chu kỳ và khả năng split, không nhằm chống lại đối thủ có khả năng quan sát hoặc dự đoán output.

Các mục đích thường phù hợp với PRNG thông thường:

- Sinh dữ liệu mẫu.
- Mô phỏng và game.
- Random hóa thứ tự kiểm thử.
- Monte Carlo và thống kê.
- Tạo số cho thuật toán không có yêu cầu bảo mật.

Các mục đích cần `SecureRandom`:

- Token đặt lại mật khẩu.
- Session ID hoặc bearer token.
- Nonce, challenge, salt hoặc dữ liệu khóa theo yêu cầu bảo mật.
- Các giá trị mà kẻ tấn công không được dự đoán.

### 11.2. Dùng SecureRandom khi cần bảo mật

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenExample {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] tokenBytes = new byte[32];
        secureRandom.nextBytes(tokenBytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(tokenBytes);

        System.out.println(token);
    }
}
~~~

`SecureRandom` cũng triển khai `RandomGenerator`, nhưng việc chọn một thuật toán LXM hoặc Xoshiro không thay thế được yêu cầu bảo mật mật mã. Hãy dùng `SecureRandom` và tuân theo hướng dẫn của nền tảng/provider cho các use case bảo mật.

Không tự seed `SecureRandom` bằng timestamp hoặc giá trị đoán được. Cũng không chuyển seed kiểm thử cố định sang production chỉ để làm output có thể lặp lại.

## 12. Những lỗi thường gặp khi dùng RandomGeneratorFactory

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gõ sai tên thuật toán | `of(name)` ném `IllegalArgumentException` | Dùng tên chính xác, kiểm tra bằng `all()` |
| Truyền tên null | `NullPointerException` | Validate cấu hình trước khi gọi factory |
| Dùng `RandomGenerator.of` rồi kỳ vọng truyền seed | API không có overload seed | Dùng `RandomGeneratorFactory.create(seed)` |
| Nghĩ mọi factory đều hỗ trợ long/byte[] seed | Có thể fallback sang `create()`, không tạo chuỗi seeded như kỳ vọng | Kiểm tra tài liệu algorithm; chọn thuật toán có hỗ trợ seed phù hợp |
| Chia sẻ một instance cho nhiều thread | Race condition hoặc kết quả khó dự đoán nếu implementation không thread-safe | Dùng instance riêng, split hoặc jump |
| Tạo nhiều worker với cùng seed | Các generator xác định có thể phát cùng chuỗi | Dùng split hoặc chiến lược cấp seed/state riêng |
| Dùng default và kỳ vọng thuật toán cố định | Default có thể thay đổi qua phiên bản | Chọn tên thuật toán tường minh khi cần ổn định |
| Chọn generator có period lớn nhất mà không xét workload | Có thể không phù hợp về tốc độ, memory hoặc concurrency | Chọn theo nhiều metadata và đo thực tế |
| Dùng PRNG thống kê cho token bảo mật | Có thể để lộ chuỗi hoặc cho phép dự đoán | Dùng `SecureRandom` |
| Tưởng factory là generator có state | Gọi nhầm nơi sinh số; khó quản lý lifecycle | Phân biệt factory (tạo instance) với generator (duy trì state và sinh số) |
| Tưởng `all()` luôn có cùng danh sách trên mọi JDK | Bỏ lỡ provider hoặc algorithm thay đổi | Khám phá runtime, xử lý tên không có sẵn |

## 13. Ví dụ tổng hợp: cấu hình generator, tạo seed và kiểm tra metadata

Lưu đoạn mã vào file **RandomGeneratorFactoryDemo.java**:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorFactoryDemo {

    private static final String ALGORITHM = "L64X128MixRandom";
    private static final long SEED = 20261115L;

    public static void main(String[] args) {
        // 1. Lấy factory theo tên thuật toán.
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of(ALGORITHM);

        // 2. Xem metadata trước khi tạo generator.
        System.out.println("Algorithm: " + factory.name());
        System.out.println("Group: " + factory.group());
        System.out.println("State bits: " + factory.stateBits());
        System.out.println("Period: " + factory.period());
        System.out.println("Splittable: " + factory.isSplittable());

        // 3. Tạo generator từ seed cố định.
        RandomGenerator random = factory.create(SEED);

        // 4. Sinh các giá trị có miền xác định.
        int dice = random.nextInt(1, 7);
        double probability = random.nextDouble(0.0, 1.0);
        long sampleId = random.nextLong(10_000L, 20_000L);

        System.out.println("Dice: " + dice);
        System.out.println("Probability: " + probability);
        System.out.println("Sample ID: " + sampleId);

        // 5. Tạo stream số để thống kê.
        double average = random.doubles(1_000, 0.0, 1.0)
                .average()
                .orElseThrow();
        System.out.println("Average: " + average);
    }
}
~~~

Biên dịch bằng JDK 17:

~~~shell
java -version
javac --release 17 RandomGeneratorFactoryDemo.java
java RandomGeneratorFactoryDemo
~~~

Tên thuật toán được chọn tường minh nên có thể đối chiếu metadata và cấu hình. Nếu chạy lại với cùng JDK, cùng thuật toán, cùng seed và cùng trình tự gọi, kết quả PRNG có thể tái lập theo implementation. Các giá trị thống kê như average sẽ là kết quả của chính chuỗi đã tạo.

## 14. Bài tập thực hành

### Bài 1 — Tạo generator bằng tên

Viết chương trình dùng:

~~~java
RandomGenerator random =
        RandomGenerator.of("L64X128MixRandom");
~~~

Sinh 20 số nguyên trong khoảng `[1, 101)`. Giải thích vì sao biên trên 101 không được xuất hiện và điều gì xảy ra nếu tên thuật toán không tồn tại.

### Bài 2 — Tạo factory và tái lập bằng seed

Tạo hai generator bằng cùng factory và cùng seed. Sinh 10 giá trị từ mỗi generator theo cùng thứ tự và so sánh. Sau đó thêm một lời gọi `nextDouble()` ở giữa chuỗi của generator thứ hai; quan sát những giá trị tiếp theo thay đổi ra sao.

### Bài 3 — Khám phá factory khả dụng

Dùng `RandomGeneratorFactory.all()` để in:

- Tên và group.
- State bits và period.
- Có splittable hay jumpable không.
- Equidistribution.

Lọc các factory splittable và giải thích vì sao danh sách có thể khác nhau giữa các runtime/provider.

### Bài 4 — Chọn theo metadata

Tìm một factory có `isSplittable() == true`, sau đó chọn factory có period lớn nhất trong nhóm đó. In tên và period. Giải thích vì sao chỉ chọn period lớn nhất chưa đủ để kết luận nó là lựa chọn tốt nhất cho ứng dụng.

### Bài 5 — Tạo generator con

Tạo `L64X128MixRandom`, xác nhận instance hỗ trợ `RandomGenerator.SplittableGenerator`, gọi `split()` hai lần và sinh giá trị từ từng generator con. Giải thích vì sao không nên dùng cùng một generator instance cho nhiều worker.

### Bài 6 — Phân biệt default và algorithm cố định

So sánh:

~~~java
RandomGenerator.getDefault();
RandomGenerator.of("L64X128MixRandom");
~~~

Giải thích khi nào default là đủ, khi nào cần tên thuật toán tường minh, và vì sao không nên phụ thuộc vào chuỗi output của default qua mọi phiên bản Java.

### Bài 7 — Chọn PRNG hay SecureRandom

Với từng tình huống, quyết định loại generator:

1. Mô phỏng một triệu lần gieo xúc xắc.
2. Tạo dữ liệu giả cho integration test.
3. Tạo token reset password.
4. Chạy Monte Carlo song song.
5. Tạo session identifier khó đoán.

Giải thích rõ yêu cầu thống kê, hiệu năng, khả năng tái lập và bảo mật của mỗi tình huống.

## 15. Câu hỏi tự kiểm tra

1. `RandomGenerator` cung cấp hợp đồng chung nào?
2. Khác nhau giữa `RandomGenerator.of(name)` và `RandomGeneratorFactory.of(name)`?
3. Factory có những overload `create` nào?
4. Vì sao `create(seed)` không phải lúc nào cũng đảm bảo seed được sử dụng?
5. `all()` trả về gì và có bao gồm generator deprecated không?
6. `getDefault()` có bảo đảm cùng thuật toán qua các phiên bản JDK không?
7. `stateBits`, `period` và `equidistribution` mô tả điều gì?
8. LXM là nhóm thuật toán kết hợp những thành phần nào?
9. Vì sao `L64X128MixRandom` thường là lựa chọn khởi đầu hợp lý cho ứng dụng chung?
10. Phân biệt splittable, jumpable và leapable?
11. Tại sao nhiều implementation của `RandomGenerator` không nên được chia sẻ đồng thời giữa các thread?
12. Làm thế nào để tạo generator riêng cho các tác vụ song song?
13. Cùng seed nhưng thứ tự gọi method khác nhau có thể cho kết quả tiếp theo khác nhau như thế nào?
14. Khi nào phải dùng `SecureRandom` thay vì LXM hoặc Xoshiro?

## 16. Tài liệu tham khảo

- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): hợp đồng sinh giá trị, các stream và sub-interface chuyên biệt.
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): `of`, `all`, `getDefault`, `create` và metadata thuật toán.
- [Java SE 17 — java.util.random package summary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): nhóm thuật toán, danh sách generator, lựa chọn theo workload và mô hình đa luồng.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): mục tiêu thống nhất API và bổ sung các loại PRNG trong Java 17.
- [Oracle Java 17 Core Libraries — Pseudorandom Number Generators](https://docs.oracle.com/en/java/javase/17/core/pseudorandom-number-generators.html): hướng dẫn sử dụng, lựa chọn thuật toán, seed và xử lý đa luồng.
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): API dành cho yêu cầu sinh số giả ngẫu nhiên an toàn về mật mã.

Khi xây dựng bộ sinh trong Java 17, hãy chọn **tên thuật toán** nếu cần kiểm soát rõ, dùng **factory** nếu cần tạo nhiều instance, seed hoặc đọc đặc tính, và dùng **capability** như split/jump khi thiết kế xử lý song song. Quan trọng nhất là chọn đúng loại generator cho mục tiêu: PRNG thông thường phục vụ mô phỏng/thống kê, còn dữ liệu cần chống dự đoán phải dựa trên `SecureRandom`.
