# Sinh số nguyên, số thực và phân phối Gaussian trong Java

## 1. Mục tiêu và bản chất của số ngẫu nhiên

Trong ứng dụng Java, “sinh số ngẫu nhiên” có thể có nhiều nghĩa khác nhau:

- **Số nguyên phân phối đều (uniform discrete):** mỗi số nguyên trong một tập hữu hạn có xác suất như nhau, ví dụ mô phỏng xúc xắc có sáu mặt.
- **Số thực phân phối đều (uniform continuous, gần đúng bằng số dấu phẩy động):** tạo giá trị trong một khoảng, với xác suất theo độ dài khoảng; ví dụ mô phỏng tọa độ hoặc tỷ lệ.
- **Số thực phân phối chuẩn (Gaussian/normal):** các giá trị tập trung quanh một trung bình, độ phân tán xác định bằng độ lệch chuẩn; ví dụ mô phỏng nhiễu đo lường.
- **Số ngẫu nhiên phục vụ bảo mật:** yêu cầu khó đoán, phù hợp để tạo mã xác minh, salt, khóa hoặc token. Đây là yêu cầu về **độ an toàn của bộ sinh**, khác với chọn phân phối.

Các generator thông dụng tạo **số giả ngẫu nhiên (pseudorandom)**: trạng thái nội bộ cùng thuật toán sinh ra chuỗi có tính chất thống kê mong muốn. Với cùng seed và cùng trình tự gọi, một thuật toán xác định có thể tái tạo chuỗi. “Ngẫu nhiên” không đồng nghĩa “không thể đoán được”, và phân phối đều không đồng nghĩa phân phối Gaussian.

Trong Java 17+, bạn có thể dùng `java.util.Random`, `java.util.concurrent.ThreadLocalRandom`, `java.util.SplittableRandom`, các generator qua `java.util.random.RandomGenerator`, hoặc `java.security.SecureRandom` tùy nhu cầu.

## 2. Sinh số nguyên phân phối đều

### 2.1. Khoảng nửa mở [0, bound)

Với `Random`:

~~~java
import java.util.Random;

Random rng = new Random();
int index = rng.nextInt(10); // 0, 1, 2, ..., 9
~~~

`nextInt(10)` lấy số nguyên **từ 0 (bao gồm) đến 10 (không bao gồm)**, tương đương ký hiệu toán học `[0, 10)`. Khi generator đủ phù hợp cho mô phỏng, các giá trị 0 đến 9 được chọn gần như đều nhau. `nextInt(0)` hoặc `nextInt` với bound âm ném `IllegalArgumentException`.

Với xúc xắc sáu mặt:

~~~java
int dice = rng.nextInt(6) + 1; // 1..6, hai đầu đều bao gồm
~~~

Đây là cách diễn đạt chính xác cho tập {1, 2, 3, 4, 5, 6}. **Không dùng** `rng.nextInt(6)` rồi cho rằng có thể nhận 6; kết quả gốc chỉ đến 5.

### 2.2. Khoảng [origin, bound) và [min, max]

Trong Java 17, giao diện `RandomGenerator` cung cấp các phương thức nhận cả cận đầu và cận cuối, và `Random` thực hiện giao diện này:

~~~java
int level = rng.nextInt(1, 7);   // 1..6
int score = rng.nextInt(20, 81); // 20..80
~~~

Ở đây `origin` bao gồm, `bound` không bao gồm. Yêu cầu `origin < bound`; nếu ngược lại sẽ có `IllegalArgumentException`.

Một nhu cầu thường gặp là muốn cả hai đầu đều bao gồm, ví dụ `min=10`, `max=20`. Có thể dùng `rng.nextInt(min, max + 1)` **khi chắc chắn `max + 1` không tràn `int`**. Với `max == Integer.MAX_VALUE`, phép cộng 1 bị tràn nên công thức đó không an toàn.

Nếu cả hai cận trong một bài toán có thể chạm `Integer.MAX_VALUE`, cân nhắc lấy qua `long`:

~~~java
int min = 10;
int max = Integer.MAX_VALUE;
int sample = (int) rng.nextLong((long) min, (long) max + 1L);
~~~

Đoạn mã trên thực hiện trong Java 17+ vì `Random` kế thừa các phương thức bounded của `RandomGenerator`. Giá trị nằm trong phạm vi `int` đã yêu cầu nên ép kiểu trở lại `int` là hợp lệ. Cần xác thực `min <= max` ở dữ liệu đầu vào. Cách viết này dùng `long` cho phép tính cận trên để tránh tràn khi cộng 1.

### 2.3. Không sinh số nguyên bằng cách làm tròn `nextDouble()`

Các biểu thức sau không có phân phối giống nhau:

~~~java
int good = rng.nextInt(6);                // 0..5, mục tiêu là phân phối đều
int biased = (int) Math.round(rng.nextDouble() * 5); // 0..5, không đều
~~~

Với công thức thứ hai, các giá trị ở hai đầu (0 và 5) nhận những đoạn đầu vào có độ dài xấp xỉ bằng **một nửa** đoạn dành cho các giá trị ở giữa. `Math.round` cũng có quy tắc xử lý đúng nửa riêng, không giải quyết độ lệch xác suất này. Nếu muốn chọn một số nguyên đều nhau, dùng API sinh `int` có cận, thay vì biến đổi số thực bằng `Math.round` hoặc `Math.floor` một cách tùy tiện.

Tương tự, `Math.abs(rng.nextInt()) % n` không phải cách chọn chỉ số tốt: `Math.abs(Integer.MIN_VALUE)` vẫn âm do tràn và phép modulo có thể tạo **modulo bias** khi số đầu vào có số lượng trạng thái không chia hết cho `n`. `nextInt(n)` xử lý phân phối có cận đúng cách cho trường hợp chuẩn.

## 3. Sinh số thực phân phối đều

### 3.1. `nextDouble()` và `nextFloat()`

~~~java
double unit = rng.nextDouble(); // từ 0.0 (gồm) đến 1.0 (không gồm)
float unitFloat = rng.nextFloat(); // cùng dạng khoảng, độ chính xác float
~~~

`nextDouble()` tạo một số `double` giả ngẫu nhiên trong `[0.0, 1.0)`, còn `nextFloat()` tạo `float`. Đây là tập hữu hạn các giá trị có thể biểu diễn bằng dấu phẩy động, **không phải** mọi số thực toán học trong khoảng. Không nên diễn giải đây là độ chính xác tùy ý hoặc số thập phân có số chữ số theo ý muốn.

`Math.random()` là lựa chọn ngắn gọn khi chỉ cần `double` trong `[0.0, 1.0)`:

~~~java
double x = Math.random();
~~~

Tuy nhiên, `Math.random()` không cho truyền seed trực tiếp tại điểm gọi và không phải API dành cho bảo mật. Khi cần tái lập hoặc kiểm soát thuật toán, quản lý generator của mình sẽ rõ ràng hơn.

### 3.2. Khoảng [min, max)

Java 17+ có dạng nhận cận:

~~~java
double temperature = rng.nextDouble(-10.0, 35.0); // [-10.0, 35.0)
float fraction = rng.nextFloat(0.0f, 1.0f);      // [0.0f, 1.0f)
~~~

Với `min < max` hợp lệ, các giá trị được tạo theo phân phối đều gần đúng trên khoảng tương ứng; kết quả nhỏ hơn cận trên. Cách tính cổ điển là:

~~~java
double min = 2.0;
double max = 5.0;
double sample = min + (max - min) * rng.nextDouble();
~~~

Công thức này mô tả ý tưởng `U(min, max)` từ `U(0, 1)`. Tuy nhiên phép nhân và cộng kiểu `double` có thể làm tròn; với một số cận, kết quả trung gian có thể tràn hoặc giá trị sau làm tròn chạm cận trên. Vì vậy, khi có API bounded trực tiếp, nên ưu tiên `nextDouble(min, max)` và truyền đầu vào hữu hạn có cận hợp lệ. Tránh kỳ vọng phép biến đổi dấu phẩy động tự bảo đảm mọi tính chất toán học ở mép khoảng.

### 3.3. Độ chính xác và các chữ số thập phân

`double` không lưu số thập phân một cách chính xác nói chung; ví dụ nhiều số như `0.1` không thể có biểu diễn nhị phân hữu hạn. Đừng nhầm kết quả từ `nextDouble()` với một “số tiền ngẫu nhiên” chính xác đến từng cent.

Nếu muốn chọn một số tiền nằm trong số nguyên các đơn vị nhỏ nhất (như cent), cách đơn giản là **lấy số nguyên có cận trước** rồi quy đổi:

~~~java
int cents = rng.nextInt(100, 501); // 100..500 cent
java.math.BigDecimal amount =
        java.math.BigDecimal.valueOf(cents, 2); // 1.00..5.00
~~~

`BigDecimal.valueOf(cents, 2)` dùng `cents × 10^-2`, giữ chính xác đơn vị cent. Đây là lựa chọn cho mô phỏng giá trị tiền rời rạc; không thay thế `SecureRandom` nếu mục đích là tạo bí mật.

## 4. Phân phối Gaussian (phân phối chuẩn)

### 4.1. Khác gì với phân phối đều?

Với phân phối đều, các phần có cùng độ dài trong khoảng có xác suất xấp xỉ bằng nhau. Với phân phối Gaussian, mật độ xác suất tạo đường cong hình chuông, tập trung quanh trung bình `μ` và thưa dần ở hai phía.

Phân phối chuẩn ký hiệu `X ~ N(μ, σ²)`, trong đó:

- `μ`: trung bình (mean), xác định tâm của phân phối.
- `σ`: độ lệch chuẩn (standard deviation), phải không âm. `σ²` là phương sai (variance). `σ` lớn hơn làm phân phối rộng hơn.
- **Phân phối chuẩn tắc** `Z ~ N(0, 1)` có trung bình 0 và độ lệch chuẩn 1.

Công thức mật độ với `σ > 0`:

\[
f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^2}{2\sigma^2}\right).
\]

`f(x)` là **mật độ**, không phải xác suất tại đúng điểm `x`; xác suất trên khoảng được tính bằng diện tích dưới đường cong ở khoảng đó. Các số thực đầu ra của PRNG được lấy rời rạc bằng dấu phẩy động nhưng mô hình xác suất mục tiêu là phân phối liên tục.

Ước lượng quen thuộc cho Gaussian lý tưởng: khoảng 68% nằm trong `μ ± σ`, khoảng 95% trong `μ ± 2σ`, khoảng 99.7% trong `μ ± 3σ`. Đây là tỷ lệ lý thuyết gần đúng, không phải cam kết mỗi tập 100 giá trị tạo ra đều có đúng tỷ lệ ấy.

### 4.2. Sinh Gaussian chuẩn tắc với `nextGaussian()`

~~~java
Random rng = new Random();

double z = rng.nextGaussian(); // N(0, 1), gần đúng theo phân phối chuẩn
~~~

Khác với `nextDouble()`, `nextGaussian()` **không nằm trong [0,1)**. Nó có thể âm, dương, lớn hơn 1 hoặc nhỏ hơn -1. Phân phối chuẩn lý tưởng có hai đuôi kéo dài vô hạn, mặc dù triển khai trên máy tính chỉ trả các giá trị `double` hữu hạn từ tập giá trị máy có thể tạo ra.

Trong `java.util.Random`, `nextGaussian()` dùng biến đổi polar kiểu Box–Muller/Marsaglia từ các giá trị đều và lưu một giá trị Gaussian thứ hai để dùng cho lần gọi tiếp theo. Vì một lần gọi có thể tiêu thụ nhiều giá trị nền do cơ chế thử lại, **không nên suy luận rằng mỗi lần gọi Gaussian luôn chỉ tiêu thụ một lần gọi `nextDouble()`**. Những lần gọi `nextInt`, `nextDouble` hoặc `nextGaussian` xen kẽ cũng làm thay đổi trạng thái và chuỗi kết quả về sau.

### 4.3. Gaussian có trung bình và độ lệch chuẩn tùy chọn

Nếu `Z ~ N(0,1)` thì phép biến đổi:

\[
X = \mu + \sigma Z
\]

cho phân phối `X ~ N(μ, σ²)` khi `σ > 0`. Ví dụ mô phỏng sai số đo quanh 100 với độ lệch chuẩn 15:

~~~java
double mean = 100.0;
double standardDeviation = 15.0;

double measurement = mean + standardDeviation * rng.nextGaussian();
~~~

Java 17+ cũng định nghĩa phương thức trên `RandomGenerator` nhận mean và standard deviation:

~~~java
double measurement2 = rng.nextGaussian(100.0, 15.0);
~~~

Hai cách biểu diễn cùng mô hình phân phối mục tiêu, nhưng **không nên mặc định kết quả bit-for-bit giống nhau với cùng seed** vì các hiện thực có thể sử dụng thuật toán khác nhau hoặc số lượng bước sinh khác nhau. Nếu cần kết quả tái lập chính xác, lưu cả tên thuật toán/kiểu generator, seed và trình tự gọi.

**Lưu ý về tham số:** `15.0` là **độ lệch chuẩn** chứ không phải phương sai. `N(100, 225)` có `σ = 15`. Nhầm phương sai 225 với độ lệch chuẩn làm mô phỏng rộng hơn dự kiến 15 lần.

### 4.4. Gaussian không có giới hạn cứng

Nếu yêu cầu “mô phỏng điểm thi từ 0 đến 100 quanh mức 70”, Gaussian với `μ = 70` và `σ = 15` **vẫn có thể tạo số âm hoặc lớn hơn 100**. Không được giả định Gaussian tự tuân thủ giới hạn chỉ vì phần lớn giá trị gần mean.

Có ít nhất ba hướng xử lý tùy mô hình:

- **Chấp nhận giá trị vượt miền** nếu đại lượng vật lý hoặc phép thử cho phép.
- **Từ chối và sinh lại** giá trị ngoài khoảng; tạo **phân phối chuẩn bị cắt (truncated normal)** trong khoảng, không còn là Gaussian không bị cắt ban đầu. Cần giới hạn số lần thử nếu khoảng rất hẹp hoặc gần đuôi phân phối.
- **Kẹp vào cận** bằng `Math.max(lower, Math.min(upper, sample))`; thao tác này dồn xác suất vào chính hai cận và tạo các khối xác suất ở cận, **không tương đương truncated normal**.

Ví dụ dùng kẹp khi có chủ đích:

~~~java
double raw = 70.0 + 15.0 * rng.nextGaussian();
double bounded = Math.max(0.0, Math.min(100.0, raw));
~~~

Đây là **đoạn mã minh họa trong một phương thức**, không phải chương trình độc lập. Chọn cách xử lý dựa trên ý nghĩa dữ liệu; đừng sửa phân phối âm thầm trong lớp dùng chung.

## 5. Chương trình Java 17+ chạy được

Ví dụ dùng seed cố định để học và kiểm thử. Lưu toàn bộ vào file `RandomDistributionsDemo.java`:

~~~java
import java.util.Locale;
import java.util.Random;

public class RandomDistributionsDemo {
    public static void main(String[] args) {
        Random rng = new Random(12345L);

        System.out.println("int [0,10): " + rng.nextInt(10));
        System.out.println("dice [1,6]: " + (rng.nextInt(6) + 1));

        System.out.printf(Locale.ROOT,
                "double [0,1): %.6f%n", rng.nextDouble());
        System.out.printf(Locale.ROOT,
                "scaled [2,5): %.6f%n",
                2.0 + 3.0 * rng.nextDouble());

        System.out.printf(Locale.ROOT,
                "gaussian Z: %.6f%n", rng.nextGaussian());
        System.out.printf(Locale.ROOT,
                "gaussian N(100,15^2): %.6f%n",
                100.0 + 15.0 * rng.nextGaussian());
    }
}
~~~

Chạy từ terminal:

~~~bash
javac RandomDistributionsDemo.java
java RandomDistributionsDemo
~~~

Output (với `java.util.Random`, seed `12345L` và đúng thứ tự gọi trong chương trình):

~~~text
int [0,10): 1
dice [1,6]: 5
double [0,1): 0.932993
scaled [2,5): 4.499274
gaussian Z: -0.742381
gaussian N(100,15^2): 83.027545
~~~

`Locale.ROOT` giúp dùng dấu chấm thập phân trong `printf`, tránh phụ thuộc locale máy chạy. `%.6f` chỉ định **sáu chữ số sau dấu phẩy khi hiển thị**, không thay đổi dữ liệu ngẫu nhiên bên trong generator. Các giá trị Gaussian không phải “số đẹp” cố định theo phân phối: chúng chính là sáu giá trị cụ thể của một chuỗi giả ngẫu nhiên với seed và thứ tự gọi đã chọn.

Đặc tả `Random` yêu cầu hai đối tượng cùng seed, cùng trình tự method call sinh cùng chuỗi theo thuật toán chuẩn của lớp. Nếu bạn chèn thêm một lần gọi `rng.nextInt(...)` giữa các dòng, những số phía sau có thể thay đổi; điều đó không phải lỗi. Các generator khác có thể cho chuỗi khác dù cùng giá trị seed.

## 6. Sinh nhiều phần tử và kiểm chứng thống kê

### 6.1. Streams cho số nguyên và số thực

`Random` có các phương thức stream tiện dùng khi cần một tập mẫu:

~~~java
Random rng = new Random(42L);

// Tạo đúng 10 số nguyên, mỗi số trong [1, 7).
int[] diceRolls = rng.ints(10, 1, 7).toArray();

// Tạo đúng 5 double, mỗi số trong [2.0, 5.0).
double[] points = rng.doubles(5, 2.0, 5.0).toArray();
~~~

Hai dòng nằm trong ngữ cảnh phương thức với import `java.util.Random`. Nếu yêu cầu rất nhiều phần tử, hãy cân nhắc xử lý dạng stream thay vì luôn tải toàn bộ vào mảng. Khi truyền stream qua pipeline song song, thứ tự tiêu thụ và cách generator được sử dụng có thể ảnh hưởng đến tính tái lập; xem xét generator có hỗ trợ split và tránh chia sẻ mutable state không kiểm soát.

### 6.2. Thử histogram thay vì suy luận bằng vài lần gọi

Bạn có thể tạo nhiều lượt xúc xắc và đếm số lần xuất hiện mỗi mặt:

~~~java
import java.util.Random;

Random rng = new Random(2026L);
int[] counts = new int[6];

for (int i = 0; i < 60_000; i++) {
    int die = rng.nextInt(6) + 1;
    counts[die - 1]++;
}

// counts[0] đếm mặt 1, ..., counts[5] đếm mặt 6.
// Mỗi mặt kỳ vọng khoảng 10_000 lần, không bắt buộc bằng nhau.
~~~

Đây là đoạn mã trong phương thức, không độc lập. Với mô hình đều lý tưởng, kỳ vọng mỗi mặt là `60000/6 = 10000`, nhưng số đếm thực tế dao động. Không nên viết test như `counts[0] == 10000`; ngay cả generator tốt vẫn thường không cho đúng 10000.

Với Gaussian, có thể lấy nhiều mẫu để đo mean và độ lệch chuẩn thực nghiệm; với số lượng mẫu hữu hạn, kết quả sẽ **gần**, chứ không **bằng chính xác**, các tham số lý thuyết. Khi test dữ liệu ngẫu nhiên, nên kiểm tra thuộc tính cận, dạng giá trị, phân phối theo ngưỡng dung sai thống kê có thiết kế, thay vì một vài mẫu cố định rồi khẳng định “đã chứng minh ngẫu nhiên”.

## 7. Chọn generator: Random, ThreadLocalRandom, SplittableRandom, RandomGenerator và SecureRandom

| API | Phù hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| `Random` | Học tập, ví dụ, test có seed, mã cũ cần tái lập chuỗi | Thread-safe nhưng dùng chung một instance giữa nhiều luồng có thể bị tranh chấp; **không an toàn mật mã**. |
| `ThreadLocalRandom.current()` | Chương trình nhiều luồng cần sinh số trong mỗi luồng | Generator riêng theo luồng, giảm tranh chấp; không chủ động đặt seed bằng `setSeed` theo cách thường dùng; không an toàn mật mã. |
| `SplittableRandom` | Mô phỏng và tác vụ chia nhánh; cần tách generator cho tác vụ độc lập | Không dùng chung instance giữa luồng khi chưa đồng bộ; dùng `split()` để tạo generator độc lập cho nhánh. |
| `RandomGenerator` và `RandomGeneratorFactory` (Java 17+) | Muốn trừu tượng qua giao diện, chọn thuật toán PRNG phù hợp | Có nhiều thuật toán với đặc tính khác nhau; tên thuật toán và cách quản lý seed ảnh hưởng tái lập. |
| `SecureRandom` | Token, salt, nonce, giá trị bảo mật khó đoán | Lấy tính bảo mật từ bộ sinh mật mã/provider; có chi phí và đặc tính tạo seed khác; không nên thay thế bằng `Random` chỉ vì nhanh hơn. |

Ví dụ `ThreadLocalRandom`:

~~~java
import java.util.concurrent.ThreadLocalRandom;

int index = ThreadLocalRandom.current().nextInt(0, 100);
double u = ThreadLocalRandom.current().nextDouble(0.0, 1.0);
double z = ThreadLocalRandom.current().nextGaussian();
~~~

Ví dụ `SplittableRandom` và chia tác vụ:

~~~java
import java.util.SplittableRandom;

SplittableRandom parent = new SplittableRandom(2026L);
SplittableRandom child = parent.split();

int parentRoll = parent.nextInt(1, 7);
int childRoll = child.nextInt(1, 7);
~~~

Ví dụ giao diện `RandomGenerator` trong Java 17:

~~~java
import java.util.random.RandomGenerator;

RandomGenerator generator =
        RandomGenerator.of("L64X128MixRandom");
int integer = generator.nextInt(1, 7);
double real = generator.nextDouble(0.0, 1.0);
double gaussian = generator.nextGaussian();
~~~

Các đoạn này minh họa bên trong phương thức/lớp với import tương ứng; không cam kết output cố định vì một số ví dụ không gắn seed. Việc dùng `RandomGenerator.of` chọn thuật toán theo tên, không tự biến generator thành an toàn mật mã. Java 17 đưa vào nhiều họ thuật toán PRNG mới; khi chọn cho ứng dụng thực, cân nhắc tính chất thống kê, khả năng chia luồng và yêu cầu tái lập.

Với dữ liệu bảo mật, ví dụ:

~~~java
import java.security.SecureRandom;

SecureRandom secure = new SecureRandom();
byte[] tokenBytes = new byte[32];
secure.nextBytes(tokenBytes);
~~~

`32` byte tạo vật liệu ngẫu nhiên cho token; cách mã hóa/lưu trữ/so sánh token phải phù hợp với giao thức. Không dùng `new Random(System.currentTimeMillis())` để tạo bí mật: kẻ tấn công có thể đoán seed hoặc chuỗi dễ hơn. `SecureRandom` cũng có `nextInt(bound)` khi cần chọn giá trị bảo mật trong một miền; tuy nhiên số lượng giá trị khả dĩ trong miền phải đủ lớn để đạt entropy theo yêu cầu. Phân phối Gaussian thường **không thích hợp** để sinh token vì tập giá trị không đồng đều và có thể rò rỉ cấu trúc.

## 8. Seed, tái lập và thread safety

**Seed** là đầu vào khởi tạo trạng thái generator, không phải bằng chứng generator “ngẫu nhiên hơn”. Với hai `new Random(12345L)` và cùng chuỗi lời gọi, kết quả giống nhau. Điều này hữu ích cho unit test, mô phỏng có khả năng tái lập và gỡ lỗi. Nếu thay thứ tự gọi hoặc thay generator, cần kỳ vọng chuỗi thay đổi.

~~~java
Random first = new Random(123L);
Random second = new Random(123L);

System.out.println(first.nextInt(100) == second.nextInt(100)); // true
System.out.println(first.nextDouble() == second.nextDouble()); // true
~~~

Seed cố định trong test là tính năng. Seed có thể đoán trong hệ thống xác thực lại là một rủi ro. Nếu làm việc song song, chia mỗi task một generator có seed được quản lý đúng cách (hoặc một họ generator hỗ trợ split); **không dùng cùng một `Random` vừa để lập báo cáo test hoàn toàn tái lập vừa để phát hành token bí mật**.

`Random` thread-safe, nhưng khi nhiều thread gọi chung, thứ tự xen kẽ có thể không xác định nên việc tái lập theo từng thread khó đạt. `ThreadLocalRandom` giảm tranh chấp nhưng không mang ý nghĩa dễ dàng tái tạo toàn bộ workload bằng một seed người dùng cấp. `SplittableRandom` hỗ trợ tách generator và có ích khi xây dựng mô phỏng song song có cấu trúc rõ ràng.

## 9. Các lỗi thực tế thường gặp

1. **Sai cận trên:** `nextInt(10)` không bao giờ ra `10`; muốn chọn `1..10` thì dùng `nextInt(1, 11)` (Java 17+) hoặc `nextInt(10)+1`.
2. **Giả định cận của số thực là hai đầu đều gồm:** `nextDouble()` nhắm đến `[0,1)`; không diễn giải xác suất lấy đúng 1 là như các điểm nằm bên trong.
3. **Nhầm Gaussian với uniform:** `nextGaussian()` có thể âm hoặc vượt `1`; chỉ `nextDouble()` mới có cận `[0,1)`.
4. **Nhầm phương sai với độ lệch chuẩn:** Trong `N(50, 9)`, `σ = 3`, không phải `9`. Khi viết `mean + sd * nextGaussian()` phải dùng `sd`.
5. **Cho rằng Gaussian tự tuân thủ miền nghiệp vụ:** Nó không có cận cứng; dùng truncate, clamp hoặc lựa chọn mô hình khác một cách có chủ đích.
6. **Dùng `Math.round(rng.nextDouble()*n)` để chia số nguyên đều:** Các điểm biên thường có xác suất khác các điểm giữa; dùng `nextInt(n)`.
7. **Dùng `Math.abs(nextInt()) % bound`:** Vướng `Integer.MIN_VALUE` và nguy cơ modulo bias; dùng phương thức có cận sẵn.
8. **Khởi tạo `new Random()` liên tục trong vòng lặp:** Làm việc với một generator được quản lý hợp lý sẽ rõ trạng thái, rẻ hơn và dễ tái lập hơn. Với ứng dụng đa luồng, cân nhắc generator theo luồng hoặc split.
9. **Giả định seed giống nhau đủ để khẳng định mọi kết quả giống nhau:** Thuật toán và **thứ tự mọi lời gọi** cũng phải tương ứng; `nextGaussian()` có thể tiêu thụ lượng trạng thái khác phép sinh số đều.
10. **Dùng `Random` hoặc `Math.random()` để tạo token bảo mật:** Chúng không phải CSPRNG; dùng `SecureRandom`, đồng thời đánh giá số bit entropy cần thiết.
11. **Kiểm thử xác suất bằng đúng một giá trị cố định:** Một lần sinh không chứng minh phân phối. Dùng seed để xác minh tính tái lập, dùng số lượng mẫu và tiêu chí thống kê phù hợp khi kiểm tra phân phối.
12. **Quên vấn đề dấu phẩy động và overflow cận:** `bound + 1` có thể tràn `int`, và `min + (max-min)*u` có thể phát sinh hiệu ứng làm tròn hoặc tràn. Ưu tiên API bounded khi phù hợp.

## 10. Tự kiểm tra

**Câu 1.** Trong `rng.nextInt(4)`, các giá trị hợp lệ là gì?  
**Đáp án:** `0,1,2,3`. Không có `4`.

**Câu 2.** Cách nào sinh đều số nguyên từ `5` đến `9`, bao gồm hai đầu?  
**Đáp án:** `rng.nextInt(5, 10)` (Java 17+) hoặc `rng.nextInt(5) + 5`.

**Câu 3.** `rng.nextGaussian()` có thể trả `-2.3` không?  
**Đáp án:** Có. Gaussian chuẩn tắc không bị giới hạn trong `[0,1)`.

**Câu 4.** Muốn tạo `X ~ N(80, 25)`, viết thế nào?  
**Đáp án:** `80.0 + 5.0 * rng.nextGaussian()` vì phương sai 25 nghĩa là độ lệch chuẩn 5.

**Câu 5.** Vì sao không nên sinh xúc xắc bằng `Math.round(rng.nextDouble() * 5) + 1`?  
**Đáp án:** Hai mặt đầu và cuối nhận ít độ dài khoảng hơn các mặt ở giữa, làm lệch phân phối.

**Câu 6.** Một ứng dụng cần test có thể chạy lại cùng kết quả, còn một ứng dụng khác cần phát hành token bí mật. Dùng cùng `new Random(12345L)` cho cả hai được không?  
**Đáp án:** Không. Seed cố định hữu ích trong test; token bí mật phải sử dụng bộ sinh an toàn mật mã như `SecureRandom`, với thiết kế token đủ entropy.

**Câu 7.** Kẹp `Gaussian` vào `[0,100]` có tạo đúng phân phối Gaussian bị cắt trong đoạn đó không?  
**Đáp án:** Không. Kẹp đặt mọi mẫu ngoài miền đúng vào 0 hoặc 100, tạo thêm xác suất tại hai điểm biên. Phân phối bị cắt bằng cách từ chối và sinh lại có tính chất khác.

## 11. Tài liệu chính thức

- [`java.util.Random` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): các phương thức `nextInt`, `nextDouble`, `nextGaussian`, seed và khả năng tái lập.
- [`java.util.random` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): các họ thuật toán PRNG và lưu ý chọn generator.
- [`ThreadLocalRandom` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator riêng theo luồng.
- [`SecureRandom` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generator dành cho dữ liệu cần khó dự đoán.

**Ghi nhớ:** Muốn **số nguyên đều**, dùng `nextInt` có cận; muốn **số thực đều**, dùng `nextDouble`/`nextFloat`; muốn **Gaussian**, dùng `nextGaussian` rồi áp dụng `μ + σZ`. Xác định rõ tính chất phân phối, miền giá trị, khả năng tái lập và yêu cầu bảo mật trước khi chọn bộ sinh.
