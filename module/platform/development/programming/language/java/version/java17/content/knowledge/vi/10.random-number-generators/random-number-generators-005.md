# Các họ thuật toán LXM, Xoshiro và Xoroshiro trong Java 17

**Chủ đề:** Java 17 → Sinh số giả ngẫu nhiên  
**Trọng tâm:** Hiểu cách phân nhóm các thuật toán LXM, Xoshiro và Xoroshiro được cung cấp qua API sinh số giả ngẫu nhiên của Java 17; đọc tên thuật toán, so sánh trạng thái và chu kỳ, chọn đúng cơ chế split/jump và dùng chúng qua RandomGenerator.

Từ Java 17, JDK cung cấp API chung `RandomGenerator` trong package `java.util.random` cùng nhiều thuật toán giả ngẫu nhiên hiện đại theo JEP 356. Ba nhóm cần nhận biết là **LXM**, **Xoroshiro** và **Xoshiro**. Các thuật toán này phục vụ những nhu cầu khác nhau về tốc độ, bộ nhớ trạng thái, chu kỳ, khả năng chia luồng sinh số và đặc tính thống kê.

Các ví dụ trong bài dùng API tiêu chuẩn Java SE 17, không cần thư viện ngoài, module incubator hay cờ preview. Một điểm cần phân biệt ngay từ đầu: **các thuật toán này là PRNG (pseudorandom number generator), không phải bộ sinh số ngẫu nhiên mật mã**. Nếu cần tạo khóa, token, nonce hoặc dữ liệu bảo mật, hãy dùng `SecureRandom`.

## 1. API sinh số giả ngẫu nhiên mới từ Java 17

Trước Java 17, ứng dụng thường gắn với một lớp cụ thể như `java.util.Random`, `ThreadLocalRandom` hoặc `SplittableRandom`. Java 17 đưa ra giao diện chung `RandomGenerator` để mã sử dụng có thể làm việc với nhiều thuật toán mà không phụ thuộc vào lớp triển khai.

Các kiểu quan trọng:

| API | Vai trò |
| --- | --- |
| `RandomGenerator` | Giao diện chung để lấy `int`, `long`, `float`, `double`, boolean và các stream số giả ngẫu nhiên. |
| `RandomGeneratorFactory` | Tra cứu, chọn và tạo generator theo tên thuật toán; cung cấp metadata như state bits, period và khả năng split/jump. |
| `RandomGenerator.SplittableGenerator` | Generator có thể tạo generator con bằng `split()`, thích hợp với công việc phân nhánh hoặc tạo tác vụ động. |
| `RandomGenerator.JumpableGenerator` | Generator có thể nhảy tiến một khoảng lớn trong chu kỳ trạng thái bằng `jump()`, thích hợp chia các vùng chuỗi cho nhiều luồng đã xác định. |
| `RandomGenerator.LeapableGenerator` | Mở rộng jump với khả năng leap một khoảng rất lớn. |
| `RandomGenerator.ArbitrarilyJumpableGenerator` | Hỗ trợ nhảy một khoảng do chương trình chỉ định. |

Mã ứng dụng thường chỉ cần tham chiếu kiểu `RandomGenerator`:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorIntro {
    public static void main(String[] args) {
        RandomGenerator random =
            RandomGeneratorFactory.of("L64X128MixRandom").create(2025L);

        int die = random.nextInt(1, 7); // 1 đến 6; cận trên không bao gồm.
        double sample = random.nextDouble();

        System.out.println("Die: " + die);
        System.out.println("Sample: " + sample);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~shell
javac --release 17 RandomGeneratorIntro.java
java RandomGeneratorIntro
~~~

`RandomGeneratorFactory.of(name)` tìm factory có tên tương ứng. `create(2025L)` tạo generator với seed được chỉ định; cùng thuật toán và cùng seed sẽ cho chuỗi kết quả có tính xác định trong cùng cách triển khai thuật toán. Với bài kiểm thử hoặc mô phỏng cần lặp lại, hãy chỉ định rõ tên thuật toán và seed thay vì dựa vào một thuật toán mặc định có thể thay đổi theo phiên bản.

## 2. Danh sách thuật toán tiêu chuẩn trong Java SE 17

Java SE 17 yêu cầu các thuật toán sau phải có. Một JDK hoặc provider có thể cung cấp thêm thuật toán khác; vì vậy, danh sách runtime tìm được bằng `RandomGeneratorFactory.all()` có thể rộng hơn bảng này.

### 2.1. Nhóm LXM

| Tên thuật toán | State bits | Chu kỳ |
| --- | ---: | --- |
| `L32X64MixRandom` | 96 | \(2^{32}(2^{64}-1)\) |
| `L64X128MixRandom` | 192 | \(2^{64}(2^{128}-1)\) |
| `L64X128StarStarRandom` | 192 | \(2^{64}(2^{128}-1)\) |
| `L64X256MixRandom` | 320 | \(2^{64}(2^{256}-1)\) |
| `L64X1024MixRandom` | 1088 | \(2^{64}(2^{1024}-1)\) |
| `L128X128MixRandom` | 256 | \(2^{128}(2^{128}-1)\) |
| `L128X256MixRandom` | 384 | \(2^{128}(2^{256}-1)\) |
| `L128X1024MixRandom` | 1152 | \(2^{128}(2^{1024}-1)\) |

### 2.2. Nhóm Xoroshiro/Xoshiro

| Tên thuật toán | State bits | Chu kỳ |
| --- | ---: | --- |
| `Xoroshiro128PlusPlus` | 128 | \(2^{128}-1\) |
| `Xoshiro256PlusPlus` | 256 | \(2^{256}-1\) |

Đây là danh sách thuật toán được Java SE 17 yêu cầu. Không nên tự động coi một tên thuật toán tìm thấy trong bài viết về thư viện khác hoặc phiên bản Java khác là tên chuẩn của Java 17. Hãy tra cứu JDK đang dùng hoặc hỏi factory bằng API.

## 3. Họ LXM: kết hợp LCG, XBG và mixer

Tên **LXM** là viết tắt của ba thành phần:

- **L — Linear Congruential Generator (LCG):** bộ sinh đồng dư tuyến tính.
- **X — Xor-Based Generator (XBG):** bộ sinh dựa trên các phép XOR, dịch bit và quay bit.
- **M — Mixer:** hàm trộn kết hợp trạng thái đầu ra của hai bộ sinh thành kết quả.

Thay vì chỉ dùng một bộ sinh đơn lẻ, LXM kết hợp một LCG và một XBG. Mỗi lần tạo kết quả, thuật toán kết hợp trạng thái của hai thành phần qua mixer, sau đó cập nhật trạng thái của cả hai.

### 3.1. LCG bên trong LXM

Một bước cập nhật LCG có dạng khái quát:

\[
s' = m \times s + a \pmod {2^p}
\]

Trong đó:

- `s` là trạng thái hiện tại.
- `m` là hệ số nhân cố định của thuật toán.
- `a` là tham số cộng của generator instance.
- `p` là số bit trạng thái LCG, thể hiện qua phần `L` trong tên thuật toán.

LXM chọn tham số để LCG có chu kỳ dài. Thành phần LCG cung cấp một chuỗi trạng thái có đặc tính riêng, còn XBG bổ sung một chuỗi khác để mixer kết hợp.

### 3.2. XBG bên trong LXM

XBG là một bộ sinh dựa trên thao tác bit. Trong các LXM của Java 17, XBG có thể dùng các họ `xoroshiro64`, `xoroshiro128`, `xoshiro256` hoặc `xoroshiro1024`, tùy cấu hình.

Số bit trạng thái của XBG là phần `X` trong tên:

- `L32X64MixRandom`: LCG 32 bit, XBG 64 bit.
- `L64X128MixRandom`: LCG 64 bit, XBG 128 bit.
- `L64X256MixRandom`: LCG 64 bit, XBG 256 bit.
- `L64X1024MixRandom`: LCG 64 bit, XBG 1024 bit.
- `L128X256MixRandom`: LCG 128 bit, XBG 256 bit.

Vì thế, tổng `stateBits()` thường bằng tổng số bit trạng thái LCG và XBG. Đây là bộ nhớ trạng thái thuật toán, không phải kích thước object Java chính xác trong heap.

### 3.3. Đọc phần hậu tố Mix và StarStar

Trong tên LXM:

- `Mix` chỉ biến thể dùng hàm trộn mạnh hơn, có đặc tính avalanche tốt.
- `StarStar` chỉ biến thể dùng scrambler ngắn hơn và nhanh hơn, nhưng yếu hơn về mức độ trộn so với biến thể `Mix`.

Ví dụ, `L64X128MixRandom` và `L64X128StarStarRandom` có cùng số bit trạng thái và cùng chu kỳ, nhưng dùng hàm xử lý đầu ra khác nhau. Không nên suy luận rằng hai thuật toán sẽ tạo cùng chuỗi số chỉ vì phần `L64X128` giống nhau.

### 3.4. Chu kỳ của LXM

Nếu LCG có chu kỳ \(2^p\), còn XBG có chu kỳ \(2^q-1\), hai chu kỳ này nguyên tố cùng nhau. Chu kỳ của LXM là tích:

\[
P = 2^p(2^q-1)
\]

Ví dụ:

\[
P_{\text{L64X128}} = 2^{64}(2^{128}-1)
\]

Chu kỳ dài có nghĩa chuỗi trạng thái cần rất nhiều bước mới lặp lại. Tuy nhiên, **chu kỳ dài không đồng nghĩa với bảo mật mật mã**, và cũng không tự đảm bảo mọi ứng dụng dùng generator đúng cách.

### 3.5. Một số thuộc tính thống kê

Các thuật toán LXM trong JDK 17 được thiết kế để có phân phối đầu ra tốt. Một số cấu hình có đặc tính *k-equidistribution* đối với các nhóm giá trị liên tiếp:

| Thuật toán | Đặc tính `nextLong()` được tài liệu hóa |
| --- | --- |
| `L64X128MixRandom` | 2-equidistributed |
| `L64X256MixRandom` | 4-equidistributed |
| `L64X1024MixRandom` | 16-equidistributed |

Hiểu khái quát, k-equidistribution mô tả tính phân bố của các bộ k giá trị liên tiếp trong chu kỳ. Đây là thuộc tính thống kê hữu ích cho một số mô phỏng và xử lý tuple; nó không phải tiêu chí duy nhất để chọn generator.

## 4. Họ Xoroshiro và Xoshiro

Xoroshiro và Xoshiro là các họ PRNG truyền thống dựa trên thao tác bit, thường kết hợp:

- XOR giữa các phần trạng thái.
- Dịch trái hoặc dịch phải (*shift*).
- Quay vòng bit (*rotate*).
- Hàm biến đổi đầu ra (*scrambler/output function*).

Tên gọi gợi ý cách kết hợp XOR, shift và rotate. Số trong tên thuật toán cho biết kích thước trạng thái:

- `Xoroshiro128PlusPlus`: trạng thái 128 bit.
- `Xoshiro256PlusPlus`: trạng thái 256 bit.

Trong Java SE 17, hai thuật toán này được cung cấp với biến thể `PlusPlus`. Phần `PlusPlus` là tên của biến thể hàm đầu ra, không phải toán tử cộng trong mã Java và cũng không phải một số phiên bản Java.

### 4.1. Xoroshiro128PlusPlus

`Xoroshiro128PlusPlus` dùng trạng thái 128 bit và có chu kỳ \(2^{128}-1\). Nó có kích thước trạng thái nhỏ, phù hợp khi cần generator gọn và tốc độ cao, chẳng hạn ứng dụng đơn luồng.

### 4.2. Xoshiro256PlusPlus

`Xoshiro256PlusPlus` dùng trạng thái 256 bit và có chu kỳ \(2^{256}-1\). Nó có trạng thái lớn hơn, chu kỳ dài hơn và cũng hỗ trợ cơ chế jump để tạo các điểm bắt đầu khác nhau trong chu kỳ.

### 4.3. So sánh hai họ

| Đặc điểm | Xoroshiro128PlusPlus | Xoshiro256PlusPlus |
| --- | --- | --- |
| Số bit trạng thái | 128 | 256 |
| Chu kỳ | \(2^{128}-1\) | \(2^{256}-1\) |
| Cơ chế phân luồng | `JumpableGenerator` | `JumpableGenerator` |
| Ưu điểm điển hình | Trạng thái nhỏ, tốc độ cao | Chu kỳ và trạng thái lớn hơn |
| Lựa chọn khi | Một luồng hoặc ít luồng, cần footprint nhỏ | Nhiều chuỗi jump hoặc cần chu kỳ lớn hơn |

Không nên chọn chỉ dựa vào số bit trạng thái. Cần xem số lượng generator được tạo, số lượng giá trị mỗi generator sẽ sinh, yêu cầu thống kê và mô hình xử lý song song.

## 5. So sánh ba họ thuật toán

| Tiêu chí | LXM | Xoroshiro | Xoshiro |
| --- | --- | --- | --- |
| Cấu trúc | Kết hợp LCG + XBG + mixer | Bộ sinh XOR/shift/rotate | Bộ sinh XOR/shift/rotate |
| Biến thể chuẩn Java 17 | Nhiều cấu hình `L...X...MixRandom` và một cấu hình `StarStar` | `Xoroshiro128PlusPlus` | `Xoshiro256PlusPlus` |
| Trạng thái | Từ 96 đến 1152 bit trong danh sách chuẩn | 128 bit | 256 bit |
| Cơ chế tạo luồng | Các LXM chuẩn triển khai `SplittableGenerator` | `JumpableGenerator` | `JumpableGenerator` |
| Đặc điểm đáng chú ý | Cân bằng chất lượng, chu kỳ, split và quy mô trạng thái | Gọn, nhanh, hỗ trợ jump | Trạng thái và chu kỳ lớn hơn, hỗ trợ jump |
| Ví dụ lựa chọn | `L64X128MixRandom` cho nhu cầu chung | `Xoroshiro128PlusPlus` khi cần trạng thái nhỏ | `Xoshiro256PlusPlus` khi cần chu kỳ lớn hơn |

LXM vẫn dùng XBG có nguồn gốc từ các họ xoroshiro/xoshiro bên trong. Vì vậy, ba nhóm này không phải ba cách tiếp cận hoàn toàn không liên quan; điểm khác nhau là **LXM kết hợp LCG với XBG và mixer**, còn Xoroshiro/Xoshiro dùng trực tiếp một bộ sinh XOR-based cùng biến thể đầu ra của nó.

## 6. Chọn generator qua RandomGeneratorFactory

`RandomGeneratorFactory` là cách linh hoạt để chọn thuật toán theo tên và xem thuộc tính của nó.

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class ListRandomAlgorithms {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
            .sorted((a, b) -> a.name().compareTo(b.name()))
            .forEach(factory -> System.out.printf(
                "%-26s group=%-12s state=%4d period=%s split=%s jump=%s%n",
                factory.name(),
                factory.group(),
                factory.stateBits(),
                factory.period(),
                factory.isSplittable(),
                factory.isJumpable()
            ));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 ListRandomAlgorithms.java
java ListRandomAlgorithms
~~~

Kết quả phụ thuộc vào các implementation/provider có trong JDK đang chạy. Bảng trên có thể bao gồm cả các generator legacy như `Random`, `SplittableRandom` và `ThreadLocalRandom`, cùng các thuật toán mới. Không nên hard-code giả định rằng mọi JDK hoặc provider chỉ có đúng mười tên ở phần danh sách thuật toán chuẩn.

### 6.1. Các thuộc tính factory quan trọng

| Phương thức | Ý nghĩa |
| --- | --- |
| `name()` | Tên thuật toán. |
| `group()` | Nhóm thuật toán, ví dụ `LXM`, `Xoroshiro`, `Xoshiro` hoặc `Legacy`. |
| `stateBits()` | Số bit trạng thái mà thuật toán sử dụng. |
| `period()` | Chu kỳ, trả về `BigInteger`; có thể là `BigInteger.ZERO` nếu không xác định được. |
| `equidistribution()` | Số chiều equidistribution được tài liệu hóa. |
| `isSplittable()` | Generator có khả năng split hay không. |
| `isJumpable()` | Generator có khả năng jump hay không. |
| `isLeapable()` | Generator có hỗ trợ leap hay không. |
| `isArbitrarilyJumpable()` | Generator có thể nhảy khoảng tùy ý hay không. |
| `isDeprecated()` | Thuật toán có bị đánh dấu deprecated hay không. |

Các thuộc tính này hữu ích khi viết thư viện muốn chọn generator theo năng lực thay vì chỉ theo tên.

## 7. Tạo generator LXM với seed rõ ràng

Ví dụ dùng `L64X128MixRandom`:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class LxmDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
            RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator random = factory.create(123456789L);

        System.out.println(random.nextLong());
        System.out.println(random.nextInt(100));
        System.out.println(random.nextDouble(10.0, 20.0));
    }
}
~~~

`create(seed)` cho phép đặt seed rõ ràng. Điều này có ích cho:

- Kiểm thử có thể tái lập.
- Mô phỏng khoa học cần ghi lại cấu hình đầu vào.
- Debug một chuỗi hành vi phụ thuộc vào số ngẫu nhiên.
- So sánh thuật toán trong một benchmark có điều kiện nhất quán.

Nếu muốn tạo seed tự khởi tạo, có thể gọi `create()` không tham số. Với thí nghiệm cần tái lập, nên lưu cả tên thuật toán, seed, phiên bản runtime và cấu hình mô phỏng. Không nên dựa vào `RandomGeneratorFactory.getDefault()` cho một định dạng dữ liệu dài hạn vì thuật toán mặc định có thể thay đổi theo thời gian.

## 8. Dùng split với LXM

Các LXM chuẩn của Java 17 triển khai `RandomGenerator.SplittableGenerator`. Phương thức `split()` tạo một generator mới tách ra từ generator hiện tại. Mô hình này phù hợp với tác vụ phân nhánh động, chẳng hạn một tác vụ chia thành hai tác vụ con.

~~~java
import java.util.random.RandomGenerator;

public class SplitDemo {
    public static void main(String[] args) {
        RandomGenerator.SplittableGenerator parent =
            RandomGenerator.SplittableGenerator.of("L64X128MixRandom");

        RandomGenerator.SplittableGenerator child = parent.split();

        System.out.println("Parent: " + parent.nextLong());
        System.out.println("Child:  " + child.nextLong());
    }
}
~~~

Mỗi generator nên được sở hữu riêng bởi một luồng xử lý. Không nên chia sẻ một instance PRNG thông thường cho nhiều thread rồi gọi đồng thời nếu implementation không cam kết thread-safe.

### 8.1. Ví dụ chia generator cho các tác vụ con

~~~java
import java.util.random.RandomGenerator;
import java.util.stream.IntStream;

public class SplitTasksDemo {
    public static void main(String[] args) {
        RandomGenerator.SplittableGenerator root =
            RandomGenerator.SplittableGenerator.of("L64X128MixRandom");

        IntStream.range(0, 4).forEach(task -> {
            RandomGenerator.SplittableGenerator child = root.split();
            System.out.println(
                "Task " + task + ": " + child.nextLong()
            );
        });
    }
}
~~~

Ví dụ này tạo generator con riêng cho từng tác vụ. Khi dùng trong ứng dụng song song thật, hãy chuyển từng generator con vào tác vụ tương ứng và bảo đảm một generator không bị nhiều thread sử dụng đồng thời.

Độc lập thống kê giữa các generator con là mục tiêu thiết kế; tài liệu API diễn đạt nó theo kỳ vọng hoặc xấp xỉ thống kê, không phải lời hứa toán học tuyệt đối rằng mọi chuỗi đều độc lập hoàn toàn.

## 9. Dùng jump với Xoroshiro và Xoshiro

`Xoroshiro128PlusPlus` và `Xoshiro256PlusPlus` trong Java 17 triển khai `RandomGenerator.JumpableGenerator`. Phương thức `jump()` di chuyển trạng thái của generator tiến một khoảng lớn, cố định trong chu kỳ.

Khác với `split()`, jump không tạo một cây generator bằng cách lấy bit từ parent; nó phân phối các điểm bắt đầu cách xa nhau trên chu kỳ của cùng một thuật toán.

~~~java
import java.util.random.RandomGenerator;

public class JumpDemo {
    public static void main(String[] args) {
        RandomGenerator.JumpableGenerator source =
            RandomGenerator.JumpableGenerator.of("Xoshiro256PlusPlus");

        // Lấy một bản sao ở vị trí hiện tại, rồi tiến source.
        RandomGenerator first = source.copyAndJump();

        // Lấy bản sao tại vị trí mới, rồi tiếp tục tiến source.
        RandomGenerator second = source.copyAndJump();

        System.out.println("First stream:  " + first.nextLong());
        System.out.println("Second stream: " + second.nextLong());
    }
}
~~~

`copyAndJump()` sao chép trạng thái hiện tại, nhảy generator gốc về phía trước, rồi trả về bản sao ở trạng thái trước bước nhảy. Gọi lặp lại trên cùng generator gốc sẽ tạo các điểm bắt đầu cách nhau bởi jump distance của implementation.

Không nên tự suy diễn rằng một khoảng jump cụ thể luôn bằng \(2^{64}\) hoặc \(2^{128}\) cho mọi thuật toán. Hãy đọc `jumpDistance()` và tài liệu của implementation nếu khoảng cách này là một phần quan trọng của thiết kế.

### 9.1. Khi nào nên split, khi nào nên jump?

| Tình huống | Cơ chế phù hợp |
| --- | --- |
| Một tác vụ sinh số đơn luồng | Một `RandomGenerator` là đủ. |
| Tác vụ chia nhánh hoặc tạo worker động | Dùng `SplittableGenerator.split()` nếu thuật toán hỗ trợ. |
| Biết trước một số lượng lớn luồng cần các đoạn chuỗi cách xa nhau | Dùng `JumpableGenerator` và các thao tác jump/jumps nếu thuật toán hỗ trợ. |
| Chọn generator từ nhiều implementation | Kiểm tra `isSplittable()` hoặc `isJumpable()` trước khi ép kiểu. |

Split và jump là các giao thức khác nhau. Không ép một generator bất kỳ sang `SplittableGenerator` hoặc `JumpableGenerator` nếu chưa xác nhận nó triển khai interface đó.

## 10. Kiểm tra khả năng trước khi ép kiểu

Không phải mọi `RandomGenerator` đều hỗ trợ split hoặc jump. Có thể kiểm tra qua factory:

~~~java
import java.util.random.RandomGeneratorFactory;

public class GeneratorCapabilities {
    public static void main(String[] args) {
        var lxm = RandomGeneratorFactory.of("L64X128MixRandom");
        var xoshiro = RandomGeneratorFactory.of("Xoshiro256PlusPlus");

        System.out.println(lxm.name());
        System.out.println("Splittable: " + lxm.isSplittable());
        System.out.println("Jumpable:   " + lxm.isJumpable());

        System.out.println(xoshiro.name());
        System.out.println("Splittable: " + xoshiro.isSplittable());
        System.out.println("Jumpable:   " + xoshiro.isJumpable());
    }
}
~~~

Với các thuật toán chuẩn của Java 17, LXM là nhóm splittable; `Xoroshiro128PlusPlus` và `Xoshiro256PlusPlus` là các lựa chọn jumpable. Nếu dùng provider bổ sung, hãy kiểm tra thuộc tính thực tế thay vì suy luận từ tên.

## 11. Chọn thuật toán theo bài toán

Tài liệu Java SE 17 đưa ra một số định hướng thực tế:

| Nhu cầu | Lựa chọn có thể cân nhắc | Lý do |
| --- | --- | --- |
| Ứng dụng thông thường, không có yêu cầu đặc biệt | `L64X128MixRandom` | Cân bằng tốt giữa tốc độ, bộ nhớ trạng thái và chu kỳ. |
| Chỉ một luồng, muốn generator nhỏ và nhanh | `Xoroshiro128PlusPlus` | Trạng thái 128 bit, chu kỳ đủ dài cho nhiều ứng dụng. |
| Môi trường phần cứng 32 bit, một hoặc ít luồng | `L32X64MixRandom` | Có trạng thái nhỏ hơn các cấu hình LXM lớn. |
| Tạo nhiều luồng đã biết trước | `Xoroshiro128PlusPlus` hoặc `Xoshiro256PlusPlus` với jump; hoặc LXM với split | Có cơ chế tạo các điểm bắt đầu/generator riêng. |
| Tạo tác vụ động, ví dụ fork/join | `L64X128MixRandom` hoặc `L64X256MixRandom` | Có khả năng split đệ quy. |
| Số lượng generator động cực lớn | `L128X128MixRandom` hoặc `L128X256MixRandom` | LCG có tham số 128 bit, làm giảm khả năng các instance dùng cùng chu kỳ trạng thái. |
| Cần chuỗi tuple liên tiếp có tính phân bố cao | Xem `L64X256MixRandom` hoặc `L64X1024MixRandom` | Có các bảo đảm 4- hoặc 16-equidistribution được tài liệu hóa. |
| Cần sinh khóa, token hoặc nonce bảo mật | `java.security.SecureRandom` | Cần bộ sinh giả ngẫu nhiên có tính bảo mật mật mã. |

Đây là hướng dẫn lựa chọn theo đặc tính thuật toán, không phải bảng xếp hạng hiệu năng cho mọi CPU hoặc mọi workload. Nếu hiệu năng là yếu tố quyết định, hãy benchmark với dữ liệu và cách sử dụng thực tế.

## 12. Chu kỳ dài không đồng nghĩa bảo mật

Các thuật toán LXM, Xoroshiro và Xoshiro là PRNG có trạng thái xác định. Khi biết trạng thái và thuật toán, chuỗi đầu ra có thể được dự đoán. Chúng được thiết kế cho mô phỏng, trò chơi, tính toán và các tác vụ thống kê, **không dùng để bảo vệ bí mật**.

Ví dụ, không nên dùng:

~~~java
RandomGenerator tokenGenerator =
    RandomGeneratorFactory.of("L64X128MixRandom").create();

String resetToken = Long.toHexString(tokenGenerator.nextLong());
~~~

để tạo token đặt lại mật khẩu hoặc mã xác thực. Dùng `SecureRandom`:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();
        byte[] tokenBytes = new byte[32];
        secureRandom.nextBytes(tokenBytes);

        String token = HexFormat.of().formatHex(tokenBytes);
        System.out.println(token);
    }
}
~~~

`SecureRandom` là lựa chọn dành cho mục đích bảo mật; không đánh đồng nó với các thuật toán LXM/Xoroshiro/Xoshiro chỉ vì tất cả đều có thể tạo ra giá trị trông có vẻ ngẫu nhiên.

## 13. Thread safety và sử dụng song song

Phần lớn implementation `RandomGenerator` không thread-safe. Nếu nhiều thread gọi đồng thời trên cùng một instance, kết quả và hiệu năng có thể không như mong đợi; một số implementation có thể có cơ chế đồng bộ riêng nhưng không nên giả định điều đó.

Nguyên tắc:

1. Mỗi thread hoặc tác vụ độc lập nên sở hữu generator riêng.
2. Nếu thuật toán hỗ trợ, tạo generator con bằng split hoặc tạo các điểm bắt đầu bằng jump.
3. Không dùng cùng một generator vừa trong thread cha vừa trong các thread con.
4. Không coi seed khác nhau là bảo đảm tuyệt đối cho các chuỗi độc lập; dùng cơ chế được thiết kế cho việc phân chia luồng.
5. Với parallel stream hoặc fork/join, hãy cân nhắc cách generator được truyền và sở hữu bởi từng tác vụ.

API `RandomGenerator.StreamableGenerator` còn cung cấp `rngs()` để tạo stream các generator. `SplittableGenerator` có `splits()` để tạo stream các generator con; `JumpableGenerator` có `jumps()` để tạo stream các generator từ những điểm nhảy. Các API này giúp mô hình hóa việc phân phối generator, nhưng vẫn cần thiết kế vòng đời và quyền sở hữu thread rõ ràng.

## 14. Những lỗi thường gặp

| Lỗi | Vì sao không nên | Cách làm phù hợp |
| --- | --- | --- |
| Chọn generator theo tên nghe có vẻ mới | Tên không cho biết đầy đủ state, period hoặc khả năng split/jump. | Xem `group()`, `stateBits()`, `period()` và các capability. |
| Nghĩ LXM chỉ là một biến thể Xoshiro | LXM kết hợp LCG, XBG và mixer. | Hiểu cấu trúc kết hợp trước khi so sánh. |
| Nghĩ `L64X128` là 128 bit tổng trạng thái | Phần L và X biểu thị hai thành phần riêng. | Tổng state bits là 64 + 128 = 192 bit. |
| Nghĩ `MixRandom` và `StarStarRandom` tạo cùng chuỗi | Chúng dùng hàm xử lý đầu ra khác nhau. | Chọn đúng tên thuật toán và seed khi cần tái lập. |
| Ép mọi generator sang `SplittableGenerator` | Không phải implementation nào cũng hỗ trợ split. | Kiểm tra `isSplittable()` hoặc dùng API có kiểu phù hợp. |
| Chia sẻ một generator cho mọi thread | Phần lớn implementation không thread-safe. | Mỗi tác vụ dùng generator riêng được split/jump. |
| Dùng seed mặc định cho test cần tái lập | Seed tự khởi tạo khiến chuỗi thay đổi giữa các lần chạy. | Chỉ định seed và tên thuật toán rõ ràng. |
| Dùng `getDefault()` làm một phần giao thức lưu trữ dài hạn | Thuật toán mặc định có thể thay đổi theo thời gian. | Chọn thuật toán tường minh và quản lý version. |
| Dùng LXM/Xoshiro/Xoroshiro tạo bí mật | Chúng không được thiết kế cho bảo mật mật mã. | Dùng `SecureRandom`. |
| Nghĩ chu kỳ lớn bảo đảm có thể sinh mọi hoán vị | Số seed và chu kỳ đều giới hạn tập chuỗi có thể xuất hiện. | So sánh chu kỳ, số seed và không gian kết quả của bài toán. |

## 15. Ví dụ tổng hợp: chọn thuật toán, kiểm tra metadata và tạo giá trị

Tệp **`PrngFamiliesDemo.java`**:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class PrngFamiliesDemo {
    private static void show(String algorithm, long seed) {
        RandomGeneratorFactory<RandomGenerator> factory =
            RandomGeneratorFactory.of(algorithm);

        RandomGenerator random = factory.create(seed);

        System.out.printf(
            "%s | group=%s | state=%d | period=%s | split=%s | jump=%s%n",
            factory.name(),
            factory.group(),
            factory.stateBits(),
            factory.period(),
            factory.isSplittable(),
            factory.isJumpable()
        );

        System.out.println("  nextLong = " + random.nextLong());
        System.out.println("  nextInt  = " + random.nextInt(1, 7));
    }

    public static void main(String[] args) {
        show("L64X128MixRandom", 2025L);
        show("Xoroshiro128PlusPlus", 2025L);
        show("Xoshiro256PlusPlus", 2025L);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 PrngFamiliesDemo.java
java PrngFamiliesDemo
~~~

Ví dụ này cho thấy cùng một giao diện `RandomGenerator` có thể dùng với ba nhóm thuật toán. Metadata của factory cho biết generator thuộc nhóm nào, dùng bao nhiêu bit trạng thái, chu kỳ và có hỗ trợ split/jump hay không. Các số cụ thể được sinh ra phụ thuộc thuật toán và seed; phần quan trọng của ví dụ là cách ứng dụng chọn và sử dụng generator qua API chung.

## 16. Câu hỏi thường gặp

**LXM là viết tắt của gì?**  
LXM là LCG + XBG + Mixer: một bộ sinh đồng dư tuyến tính kết hợp bộ sinh XOR-based, rồi trộn trạng thái để tạo đầu ra.

**Phần L64X128 trong tên L64X128MixRandom có nghĩa là gì?**  
LCG có 64 bit trạng thái, XBG có 128 bit trạng thái; tổng state bits là 192 bit.

**MixRandom và StarStarRandom khác nhau thế nào?**  
Chúng dùng biến thể hàm trộn/scrambler khác nhau. Theo tài liệu Java SE 17, Mix dùng mixer mạnh hơn, còn StarStar dùng scrambler ngắn hơn và nhanh hơn.

**Xoshiro và Xoroshiro có thể split không?**  
Hai thuật toán chuẩn Xoroshiro128PlusPlus và Xoshiro256PlusPlus của Java 17 là jumpable. Dùng jump()/jumps() để phân phối điểm bắt đầu; LXM là nhóm splittable và dùng split()/splits().

**Có thể dùng một thuật toán cho mọi ứng dụng không?**  
Không có lựa chọn tối ưu cho tất cả. L64X128MixRandom là điểm khởi đầu cân bằng cho nhu cầu chung; các workload song song, trạng thái nhỏ, số lượng generator lớn hoặc yêu cầu thống kê đặc thù có thể cần lựa chọn khác.

**Seed có làm PRNG trở thành bộ sinh ngẫu nhiên thật không?**  
Không. Seed khởi tạo trạng thái cho một thuật toán xác định. PRNG vẫn là giả ngẫu nhiên; seed cố định hữu ích cho tái lập kết quả.

**Có thể dùng các họ này cho mật khẩu hoặc token không?**  
Không. Dùng SecureRandom cho dữ liệu cần bảo mật mật mã.

## 17. Tài liệu tham khảo chính thức

- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): thiết kế API RandomGenerator, factory và các thuật toán được bổ sung trong Java 17.
- [Java SE 17 API — Package java.util.random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): danh sách thuật toán, nhóm LXM/Xoroshiro/Xoshiro, thuộc tính và hướng dẫn lựa chọn.
- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): giao diện dùng chung cho các generator.
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): tra cứu thuật toán, tạo generator và xem metadata.
- [Java SE 17 API — RandomGenerator.SplittableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.SplittableGenerator.html): split() và splits().
- [Java SE 17 API — RandomGenerator.JumpableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.JumpableGenerator.html): jump(), copyAndJump() và jumps().
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): bộ sinh giả ngẫu nhiên dùng cho mục đích bảo mật.

**Nguyên tắc lựa chọn:** Dùng RandomGenerator làm kiểu giao tiếp chung; chọn LXM khi cần cơ chế split và sự cân bằng tổng quát; cân nhắc Xoroshiro/Xoshiro khi cần generator jumpable với trạng thái gọn hoặc chu kỳ lớn hơn; và dùng SecureRandom khi yêu cầu là bảo mật mật mã.
