# Mô phỏng số ngẫu nhiên có thể tái lập bằng seed trong Java

## 1. Tình huống thực hành và mục tiêu

Giả sử ta mô phỏng việc tung xúc xắc, tạo dữ liệu kiểm thử hoặc ước lượng π bằng phương pháp Monte Carlo. Ta muốn có ngẫu nhiên để thử nhiều tình huống, nhưng khi phát hiện lỗi, cần **chạy lại đúng các giá trị ngẫu nhiên đã dùng** để tái hiện và chẩn đoán.

Đó là mục tiêu của **mô phỏng có thể tái lập bằng seed** (*reproducible seeded simulation*). Một seed là trạng thái khởi tạo hoặc đầu vào khởi tạo cho bộ sinh số giả ngẫu nhiên (*pseudorandom number generator, PRNG*). Với cùng thuật toán, cùng seed, cùng chuỗi lời gọi và cùng điều kiện thực thi liên quan, ta có thể tạo lại cùng chuỗi đầu ra.

Ví dụ đơn giản:

```java
Random first = new Random(2026L);
Random again = new Random(2026L);

System.out.println(first.nextInt(100) == again.nextInt(100)); // true
```

Đây không phải “ngẫu nhiên thực sự” từ môi trường; dãy đầu ra được tính theo thuật toán xác định. Seed cho phép chuyển một ca kiểm thử vốn khó tái hiện thành **một ca có thể phát lại**.

Mục tiêu bài học:
- Biết dùng `java.util.Random`, `SplittableRandom` và các API Java 17 thích hợp để điều khiển seed.
- Hiểu điều kiện **cùng seed chưa đủ** để có cùng kết quả khi cách gọi hoặc phân phối khác nhau.
- Xây dựng mô phỏng Monte Carlo tính xấp xỉ π và một ví dụ tung xúc xắc.
- Kiểm tra sự tái lập, so sánh nhiều seed và tránh nhầm tính tái lập với tính đúng về thống kê.
- Biết cách lưu seed, số bước, phiên bản thuật toán, tham số và chiến lược song song để tái hiện khi lỗi xảy ra.
- Phân biệt PRNG cho mô phỏng với bộ sinh ngẫu nhiên cần bảo mật.

## 2. Seed, PRNG và trạng thái thay đổi như thế nào?

PRNG duy trì **trạng thái nội bộ**. Mỗi lần gọi phương thức sinh số, nó dựa vào trạng thái hiện tại để tạo một kết quả và cập nhật trạng thái cho lần tiếp theo.

Một mô hình khái niệm:

```text
                seed cố định
                     |
                     v
                 khởi tạo PRNG
                     |
              trạng thái S0
                     |
            nextInt / nextDouble
                     v
         đầu ra R0, trạng thái S1
                     |
            nextInt / nextDouble
                     v
         đầu ra R1, trạng thái S2
                     |
                    ...
```

Nếu hai PRNG độc lập bắt đầu từ cùng seed và thực hiện **cùng chuỗi phương thức với cùng đối số**, chúng tạo cùng kết quả theo thuật toán xác định tương ứng. Ngược lại, nếu luồng A gọi `nextInt()` ba lần còn luồng B gọi thêm một lần ở giữa, chuỗi giá trị gắn với từng bước nghiệp vụ có thể lệch dù seed giống nhau.

**Không có cam kết** rằng “cùng seed” sẽ cho cùng chuỗi khi bạn đổi từ `Random` sang `SplittableRandom`, đổi thuật toán, thay trình tự gọi, thay cách chia luồng hoặc đổi một thành phần làm tiêu thụ RNG.

Một seed **không quyết định độ chính xác thống kê** của mô phỏng: nó quyết định điểm bắt đầu của một chuỗi giả ngẫu nhiên. Kết quả một seed có thể gần giá trị lý thuyết hoặc lệch đáng kể, đặc biệt khi số mẫu nhỏ.

## 3. Chọn API phù hợp trong Java

| API | Cách dùng seed | Phạm vi phù hợp | Lưu ý |
| --- | --- | --- | --- |
| `java.util.Random` | `new Random(longSeed)` | Ví dụ, kiểm thử và mô phỏng tuần tự | Thuật toán lõi và cách cập nhật trạng thái được Java mô tả; nhiều phương thức có khả năng sinh dãy lặp lại khi cùng seed/call sequence |
| `java.util.SplittableRandom` | `new SplittableRandom(longSeed)` | Mô phỏng phân luồng/cần tách bộ sinh | Có `split()` để sinh bộ sinh con; không dùng chung một đối tượng với nhiều luồng mà không có chiến lược phù hợp |
| `java.util.random.RandomGenerator` (Java 17+) | Giao diện chung; chọn implementation thích hợp | Thiết kế API không gắn với một lớp cụ thể | Cần ghi lại **tên thuật toán/implementation**, không chỉ seed |
| `java.util.random.RandomGeneratorFactory` (Java 17+) | Chọn thuật toán có tên, tạo generator từ seed | Thí nghiệm có yêu cầu quản lý thuật toán | Không tự suy rằng hai thuật toán khác nhau cho cùng kết quả |
| `ThreadLocalRandom` | Không cho ứng dụng đặt seed bằng `setSeed` | Sinh số thuận tiện theo từng luồng khi không cần phát lại dãy bằng seed được điều khiển | Không phải lựa chọn phù hợp cho ca cần seed cụ thể |
| `SecureRandom` | Thiết kế theo nhu cầu an ninh, không coi như một PRNG mô phỏng thông thường | Token, khóa, nonce và yêu cầu mật mã | Không dùng một seed công khai cố định để sinh dữ liệu bí mật |

**Lựa chọn thực hành:** Với bài mô phỏng tuần tự và test tái lập đơn giản, `Random` với seed ghi rõ thường là lựa chọn dễ hiểu. Với mô phỏng có nhiều nhánh độc lập, `SplittableRandom` hỗ trợ tách generator, nhưng vẫn cần kiểm soát **thứ tự tách**, phần việc của từng nhánh và cấu hình chạy.

### Tạo Random từ seed

```java
long seed = 2026L;
Random rng = new Random(seed);

int die = rng.nextInt(6) + 1; // 1..6, gồm cả 1 và 6
double u = rng.nextDouble(); // [0.0, 1.0)
```

`Random.nextInt(6)` sinh các số nguyên từ 0 đến 5 với phân phối đều theo hợp đồng của API; cộng 1 để mô phỏng một xúc xắc sáu mặt. Cận trên 6 **không được bao gồm**.

Với `SplittableRandom` Java 17, có thể gọi:

```java
SplittableRandom rng = new SplittableRandom(2026L);
int die = rng.nextInt(1, 7);           // 1..6
double x = rng.nextDouble(-1.0, 1.0); // [-1.0, 1.0)
```

Các câu lệnh trên là đoạn minh họa dùng trong phương thức, cần import lớp tương ứng.

## 4. Nguyên tắc tái lập: cùng seed + cùng thao tác + cùng ngữ cảnh

Có ba cấp độ thường gặp:

**Cấp độ A — Phát lại đúng chuỗi trên một generator tuần tự.** Giữ nguyên seed, thuật toán và lời gọi. Ví dụ cùng gọi `nextInt(6)` tám lần với `Random(2026L)` cho cùng dãy tám kết quả.

**Cấp độ B — Phát lại một mô phỏng.** Ngoài generator, giữ nguyên dữ liệu đầu vào, số lần lặp, quy tắc chuyển đổi từ giá trị ngẫu nhiên sang tình huống, cách làm tròn, thứ tự các phép toán và nhánh điều kiện. Một thay đổi nhỏ, chẳng hạn thêm lần gọi RNG để mô phỏng thời tiết, có thể làm toàn bộ lượt tiếp theo khác nhau.

**Cấp độ C — Phát lại giữa môi trường/phiên bản hoặc qua nhiều luồng.** Cần kiểm soát thêm implementation, tên thuật toán, phiên bản chương trình/JDK nếu dựa vào chi tiết triển khai, cách chia luồng, số luồng, thứ tự gộp kết quả và chính sách về phép toán dấu chấm động.

Một lỗi thiết kế thường gặp:

```java
Random rng = new Random(2026L);
int first = rng.nextInt(100);
int second = rng.nextInt(100);

// Ở lần chạy khác, mã gọi thêm rng.nextInt(100) trước khi tính second.
// Giá trị gắn với "second" sẽ không còn như trước.
```

**Tính tái lập của nguồn RNG** không bảo đảm **tính tái lập của toàn bộ hệ thống** nếu ứng dụng có I/O, thời gian thực, dữ liệu bên ngoài, race condition hoặc thuật toán không xác định.

## 5. Bài thực hành 1: tung xúc xắc và phát lại kết quả

Tạo một hàm nhận seed và số lần tung. Không truyền generator dùng chung từ bên ngoài vào các ca mà bạn muốn hoàn toàn độc lập; tạo generator mới từ seed cho mỗi lượt phát lại:

```java
static int[] rollDice(long seed, int rolls) {
    if (rolls < 0) {
        throw new IllegalArgumentException("rolls must be >= 0");
    }
    Random generator = new Random(seed);
    int[] result = new int[rolls];
    for (int i = 0; i < rolls; i++) {
        result[i] = generator.nextInt(6) + 1;
    }
    return result;
}
```

Đây là một **phương thức** để đặt trong lớp Java, kèm `import java.util.Random;`. Mỗi lời gọi mới với cùng `seed` và `rolls` sẽ thực hiện cùng số lần `nextInt(6)` theo cùng thứ tự.

```java
int[] a = rollDice(2026L, 8);
int[] b = rollDice(2026L, 8);

System.out.println(Arrays.equals(a, b)); // true
```

Cần import `java.util.Arrays` khi sử dụng `Arrays.equals`. Thay seed thành 2027L có thể tạo dãy khác. Không nên ghi điều kiện cứng rằng **hai seed khác nhau luôn** sinh dãy kết quả khác nhau: đầu ra hữu hạn có thể trùng do ngẫu nhiên, nhất là khi số mẫu nhỏ hoặc miền kết quả nhỏ.

### Vì sao không tạo lại Random bên trong từng lần tung?

Đoạn code sau cho kết quả ít đa dạng hơn dự định:

```java
for (int i = 0; i < 8; i++) {
    Random rng = new Random(2026L); // Reset cùng seed ở mỗi lượt!
    int die = rng.nextInt(6) + 1;
    // die lặp lại cùng giá trị đầu tiên của generator.
}
```

Muốn tám lượt liên tiếp, **tạo một generator trước vòng lặp** và gọi nó tám lần. Nếu muốn tám kịch bản độc lập, có thể sử dụng tám seed được quản lý riêng nhưng không nên chỉ “lặp lại cùng seed” cho mỗi kịch bản.

## 6. Bài thực hành 2: mô phỏng Monte Carlo ước lượng π

Một điểm `(x, y)` được sinh đều trong hình vuông `[-1,1) × [-1,1)`. Điểm nằm trong hình tròn bán kính 1 khi:

```text
x² + y² <= 1
```

Tỉ lệ diện tích hình tròn so với hình vuông bằng `π / 4`. Nếu sinh `N` điểm đều và đếm `inside` điểm nằm trong hình tròn, ta tính:

```text
piEstimate = 4 × inside / N
```

Khi `N` lớn hơn, sai số lấy mẫu thường giảm về mặt thống kê; nhưng **một seed cố định không làm ước lượng tự trở thành giá trị π chính xác**, và không bảo đảm lần tăng `N` nào cũng cải thiện kết quả.

### Cài đặt an toàn, dễ phát lại

```java
record Estimate(long inside, int trials, double pi) {}

static Estimate estimatePi(long seed, int trials) {
    if (trials <= 0) {
        throw new IllegalArgumentException("trials must be > 0");
    }
    SplittableRandom generator = new SplittableRandom(seed);
    long inside = 0;
    for (int i = 0; i < trials; i++) {
        double x = generator.nextDouble(-1.0, 1.0);
        double y = generator.nextDouble(-1.0, 1.0);
        if (x * x + y * y <= 1.0) {
            inside++;
        }
    }
    return new Estimate(inside, trials, 4.0 * inside / trials);
}
```

Đây là **đoạn phương thức và record** cần đặt trong lớp/chương trình Java 17, có import `java.util.SplittableRandom`.

Các điểm thiết kế:
- `trials > 0` để không có chia cho 0.
- `SplittableRandom(seed)` mới được khởi tạo **ở đầu mỗi mô phỏng**, tránh nhận một generator đã bị tiêu thụ ở lời gọi trước.
- Mỗi lượt dùng chính xác **hai lần `nextDouble(-1.0,1.0)`**, theo thứ tự x rồi y.
- `inside` kiểu `long` để dễ thích nghi nếu mở rộng vòng lặp; với `int trials`, bộ đếm này không tràn trong phạm vi đã cho.
- `4.0 * inside / trials` là phép toán `double`, không phải phép chia số nguyên bị cắt phần lẻ.
- Khi chạy lại với cùng seed, trial count và cùng implementation/call order, cặp `inside`/`pi` tái hiện được.

### Đánh giá chất lượng thống kê

Trong mô phỏng này, xác suất điểm nằm trong hình tròn là `p = π / 4`. Nếu các mẫu độc lập như mô hình giả định, tỉ lệ `inside / N` có độ lệch chuẩn xấp xỉ:

\[
\sqrt{\frac{p(1-p)}{N}}
\]

Độ lệch chuẩn của `piEstimate = 4 × inside/N` xấp xỉ bốn lần giá trị trên. Đây là ước lượng **sai số lấy mẫu**, không phải bảo đảm một lượt phải nằm trong một khoảng chặt. Không kiểm thử rằng kết quả với một seed cụ thể phải “gần π hơn” kết quả seed khác. Cần nhiều seed độc lập, thống kê và kiểm định thích hợp nếu muốn đánh giá chất lượng phân phối.

## 7. Chương trình Java 17 hoàn chỉnh và kết quả đã chạy

Tạo tệp **`SeededSimulationDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Random;
import java.util.SplittableRandom;

public class SeededSimulationDemo {
    record Estimate(long inside, int trials, double pi) {}

    static int[] rollDice(long seed, int rolls) {
        if (rolls < 0) throw new IllegalArgumentException("rolls must be >= 0");
        Random generator = new Random(seed);
        int[] result = new int[rolls];
        for (int i = 0; i < rolls; i++) {
            result[i] = generator.nextInt(6) + 1;
        }
        return result;
    }

    static Estimate estimatePi(long seed, int trials) {
        if (trials <= 0) throw new IllegalArgumentException("trials must be > 0");
        SplittableRandom generator = new SplittableRandom(seed);
        long inside = 0;
        for (int i = 0; i < trials; i++) {
            double x = generator.nextDouble(-1.0, 1.0);
            double y = generator.nextDouble(-1.0, 1.0);
            if (x * x + y * y <= 1.0) inside++;
        }
        return new Estimate(inside, trials, 4.0 * inside / trials);
    }

    public static void main(String[] args) {
        long seed = 2026L;
        int[] first = rollDice(seed, 8);
        int[] replay = rollDice(seed, 8);
        int[] other = rollDice(seed + 1, 8);
        System.out.println("dice=" + Arrays.toString(first));
        System.out.println("sameSeedSameDice=" + Arrays.equals(first, replay));
        System.out.println("otherSeedDice=" + Arrays.toString(other));

        Random a = new Random(seed);
        Random b = new Random(seed);
        int a0 = a.nextInt(100);
        int a1 = a.nextInt(100);
        int b0 = b.nextInt(100);
        System.out.println("sameFirstDraw=" + (a0 == b0));
        System.out.println("differentDrawPosition=" + (a1 != b0));
        System.out.println("draws=" + a0 + "," + a1 + "," + b0);

        Estimate m1 = estimatePi(seed, 10_000);
        Estimate m2 = estimatePi(seed, 10_000);
        Estimate m3 = estimatePi(seed + 1, 10_000);
        System.out.println("sameSimulation=" + m1.equals(m2));
        System.out.println("piSeed2026=" + String.format(Locale.ROOT,
                "inside=%d,trials=%d,pi=%.6f", m1.inside(), m1.trials(), m1.pi()));
        System.out.println("piSeed2027=" + String.format(Locale.ROOT,
                "inside=%d,trials=%d,pi=%.6f", m3.inside(), m3.trials(), m3.pi()));

        SplittableRandom parent1 = new SplittableRandom(seed);
        SplittableRandom parent2 = new SplittableRandom(seed);
        int child1 = parent1.split().nextInt(1, 101);
        int child2 = parent2.split().nextInt(1, 101);
        System.out.println("reproducibleSplit=" + (child1 == child2));
        System.out.println("childDraw=" + child1);

        try {
            estimatePi(seed, 0);
            throw new AssertionError("Expected invalid trial count");
        } catch (IllegalArgumentException expected) {
            System.out.println("zeroTrialsRejected=true");
        }
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac SeededSimulationDemo.java
java SeededSimulationDemo
```

Kết quả đã kiểm chứng bằng biên dịch `javac --release 17` và chạy chương trình:

```text
dice=[6, 5, 2, 1, 4, 5, 6, 5]
sameSeedSameDice=true
otherSeedDice=[4, 1, 1, 1, 1, 6, 3, 5]
sameFirstDraw=true
differentDrawPosition=true
draws=99,50,99
sameSimulation=true
piSeed2026=inside=7850,trials=10000,pi=3.140000
piSeed2027=inside=7877,trials=10000,pi=3.150800
reproducibleSplit=true
childDraw=72
zeroTrialsRejected=true
```

**Giải thích quan trọng:**

1. Hai lời gọi `rollDice(2026L, 8)` xây hai generator độc lập nhưng cùng seed; vì quy trình giống nhau, mảng bằng nhau.
2. `otherSeedDice` khác trong ví dụ cụ thể khi seed = 2027L. Đây là dữ liệu quan sát từ chương trình, không phải một định lý rằng mọi seed khác đều cho chuỗi khác.
3. `a` và `b` cùng seed: lượt bốc thứ nhất của mỗi generator đều ra 99. Lượt thứ hai của `a` ra 50; so sánh `a1` với lượt thứ nhất `b0` minh họa tác động của **vị trí trong dãy**.
4. Với 10.000 điểm, seed 2026L tạo 7.850 điểm trong hình tròn → π ước lượng 3.14; seed 2027L tạo 7.877 điểm → 3.1508. Hai kết quả là **mẫu mô phỏng**, không phải độ chính xác đảm bảo cho mọi seed.
5. Hai `SplittableRandom` độc lập có cùng seed và đều gọi `split()` đúng một lần, nên generator con tạo cùng kết quả (72) trong môi trường đã kiểm chứng.
6. `estimatePi(...,0)` bị từ chối bằng `IllegalArgumentException`; đây là kiểm tra đầu vào, không phải lỗi ngẫu nhiên.

## 8. Vì sao cùng seed đôi khi vẫn không cùng kết quả?

### 8.1. Khác thứ tự hoặc số lần gọi

Các lệnh sinh số tiêu thụ trạng thái. Ví dụ:

```java
Random x = new Random(123L);
Random y = new Random(123L);

int firstX = x.nextInt(100);
int secondX = x.nextInt(100);
int firstY = y.nextInt(100);
// firstX == firstY, nhưng secondX không buộc bằng firstY.
```

Nếu nhánh điều kiện phụ thuộc dữ liệu khác, hai lần chạy có thể gọi RNG số lần khác nhau. Để phát lại, cố định cả dữ liệu và **thứ tự các sự kiện**.

### 8.2. Khác thuật toán sinh số

`Random`, `SplittableRandom` và các implementation trong `java.util.random` là **các bộ sinh khác nhau**. Không so sánh kết quả seed 42 giữa hai lớp rồi kết luận một lớp có lỗi vì không trùng.

Nếu bạn muốn test hợp đồng ứng dụng độc lập thuật toán, kiểm tra các tính chất như:
- kết quả xúc xắc thuộc 1..6;
- cùng cấu hình tái lập trong thuật toán đã chọn;
- không có index vượt phạm vi;
- phân phối có tính chất thống kê phù hợp qua nhiều seed (với test được thiết kế chuẩn).

Nếu muốn tái hiện **từng giá trị chính xác xuyên phiên bản và máy**, lưu tên thuật toán, phiên bản JDK/implementation và đầu ra mẫu để kiểm soát thay đổi; nếu yêu cầu nghiêm ngặt, định nghĩa hoặc đóng băng thuật toán PRNG trong giao thức ứng dụng thay vì mặc định mọi API đều có cam kết bit-for-bit trên mọi runtime.

### 8.3. Khác tham số phân phối hoặc phương thức

`nextInt(100)` và `nextInt(200)` có cách ánh xạ đầu ra khác nhau. Ngay cả khi dùng cùng generator và seed, thay bound, thay số lần gọi `nextDouble`, chuyển sang phân phối Gaussian, hoặc chèn `nextGaussian()` cũng có thể thay chuỗi giá trị xuất hiện trong nghiệp vụ. Các API có thể tiêu thụ trạng thái nội bộ với số bước khác nhau; không tự giả định một lời gọi nghĩa là một bước PRNG chuẩn.

### 8.4. Tính không xác định bên ngoài RNG

Nếu dữ liệu nguồn được lấy theo thứ tự thay đổi (ví dụ đọc các event đến bất định, duyệt collection không có thứ tự được bảo đảm, số luồng thay đổi), luồng logic có thể tiêu thụ RNG khác thứ tự. Nếu kết quả được tổng hợp bằng `double` ở các thứ tự khác, phép cộng dấu chấm động cũng có thể tạo kết quả chữ số cuối khác.

**Seed cần thiết, nhưng không đủ** để kiểm soát mọi nguồn không xác định trong hệ thống.

## 9. Nhiều luồng: chia generator thay vì chia sẻ tùy tiện

### 9.1. Tránh phụ thuộc lịch chạy luồng

Chia sẻ một generator cho nhiều worker có thể khiến **số nào thuộc worker nào** phụ thuộc thứ tự thực thi. `Random` hỗ trợ sử dụng từ nhiều luồng theo đặc điểm API nhưng điều đó không tạo kết quả có thể dự báo cho từng task; `SplittableRandom` không được thiết kế để nhiều luồng đồng thời gọi trên cùng instance.

Một cách tốt hơn là cấp **một generator riêng cho mỗi nhánh công việc**, và xác định ánh xạ nhánh ↔ seed hoặc generator con một cách cố định.

### 9.2. Tách với SplittableRandom

```java
long rootSeed = 2026L;
SplittableRandom root = new SplittableRandom(rootSeed);

SplittableRandom taskA = root.split();
SplittableRandom taskB = root.split();

// Chuyển mỗi generator con tới đúng một task.
int a = taskA.nextInt(100);
int b = taskB.nextInt(100);
```

Mã trên là đoạn minh họa bên trong một phương thức. Để tái lập:
1. Tạo `root` từ cùng seed.
2. Gọi `split()` theo **cùng thứ tự xác định**, ví dụ tạo sẵn danh sách generator cho các task có ID cố định.
3. Gán mỗi generator con cho đúng task; **không chia sẻ** một instance giữa nhiều task.
4. Duy trì thuật toán và số lần gọi ổn định trong mỗi task.
5. Thu thập kết quả theo thứ tự xác định nếu thao tác gộp phụ thuộc thứ tự, đặc biệt với `double`.

Nếu số worker hoặc thứ tự split thay đổi, kết quả gắn với các task có thể thay đổi dù root seed không đổi. Khi cần task ID độc lập thứ tự scheduling, hãy dùng chiến lược dẫn xuất seed ổn định từ root seed và ID (với hàm mixing có thiết kế/kiểm chứng phù hợp), hoặc generator theo counter/index do ứng dụng quản lý.

### 9.3. Hai yêu cầu khác nhau: tái lập và tính độc lập thống kê

Hai generator dùng **cùng seed** và cùng thuật toán sẽ cho **cùng chuỗi**, không phải hai chuỗi mẫu độc lập. Nếu dùng cùng seed để mô phỏng 1.000 phiên chạy, bạn có thể đang lặp lại một phiên 1.000 lần.

Để đánh giá độ biến thiên giữa các phiên, dùng các luồng sinh khác nhau theo phương án được thiết kế, ví dụ quản lý seed theo ID phiên, hoặc split từ một root generator theo thứ tự xác định. Không mặc định rằng chỉ thay seed bằng `seed + i` chứng minh các luồng hoàn toàn độc lập về mọi tính chất thống kê; với mô phỏng nhạy cảm, cần cân nhắc chất lượng generator và cách chia stream.

## 10. Xây dựng test kiểm chứng sự tái lập

### 10.1. Kiểm tra phát lại byte-for-byte hoặc value-for-value

Ví dụ với mảng xúc xắc:

```java
int[] first = rollDice(2026L, 100);
int[] second = rollDice(2026L, 100);
if (!Arrays.equals(first, second)) {
    throw new AssertionError("Reproducibility violated");
}
```

Trong chương trình Java 17, cần import `java.util.Arrays`. Nếu so sánh `double` yêu cầu đúng bit, có thể dùng `Double.doubleToLongBits()` hoặc `Double.doubleToRawLongBits()` theo hợp đồng, thay vì so với epsilon khi mục tiêu là **phát lại chính xác**. Với Monte Carlo record chứa cùng `inside`/`trials` và cùng phép tính, `equals()` của record là kiểm tra phù hợp trong ví dụ.

### 10.2. Kiểm tra tính hợp lệ của phân phối

Không nhầm **reproducible** với **statistically correct**. Với xúc xắc, tối thiểu cần kiểm tra:

```text
Với mọi kết quả die trong mô phỏng:
    1 <= die <= 6
```

Muốn kiểm tra xác suất gần đồng đều, phải dùng đủ số mẫu và kiểm định thống kê phù hợp (ví dụ kiểm định chi-bình-phương với mức ý nghĩa được định nghĩa), không khẳng định sáu mặt xuất hiện đúng bằng nhau trong một dãy ngắn.

Với mô phỏng π:
- `inside` phải nằm trong `[0, trials]`.
- `piEstimate` phải nằm trong `[0,4]`.
- Với cùng seed, trials và môi trường thuật toán, kết quả phải tái hiện được.
- Để đánh giá sai số ước lượng, chạy **nhiều phiên với seed/stream khác nhau** và phân tích phân phối kết quả; không dùng một seed duy nhất để kết luận độ chính xác thống kê.

### 10.3. Test đầu vào lỗi

Kiểm thử cả:
- số lần tung âm: phải từ chối;
- số mẫu Monte Carlo bằng 0 hoặc âm: phải từ chối;
- các bound không hợp lệ khi gọi `nextInt(bound)` hoặc `nextDouble(origin,bound)`;
- số lượng mẫu đủ lớn làm tràn `int` hoặc làm cạn bộ nhớ khi thiết kế mảng chứa toàn bộ kết quả;
- seed được lưu dưới dạng văn bản: phải parse chính xác, tránh mất bit do chuyển qua `double`/định dạng số không lossless.

Không thử phân bổ mảng hàng tỷ phần tử chỉ để chứng minh cấu hình không hợp lệ; kiểm tra miền và ngân sách tài nguyên trước.

## 11. Ghi lại dữ liệu để phát lại lỗi

Trong báo cáo lỗi hoặc kết quả thí nghiệm, nên ghi:

| Thông tin | Ví dụ | Vì sao cần |
| --- | --- | --- |
| Tên bài toán/thuật toán | Monte Carlo π | Biết quy trình nào sử dụng RNG |
| Seed | `2026` | Khởi tạo lại bộ sinh |
| PRNG | `SplittableRandom` | Cùng seed nhưng khác thuật toán cho chuỗi khác |
| Mô hình và tham số | `trials = 10000`; khoảng `[-1,1)` | Bảo toàn số bước và cách ánh xạ mẫu |
| Phiên bản chương trình | commit/build/version | Tránh thay code làm lệch số lần gọi |
| JDK và môi trường (khi cần) | JDK 17, vendor | Gắn chi tiết runtime ảnh hưởng tính nhất quán |
| Chiến lược song song | task ID, seed con, thứ tự split | Phát lại đúng luồng |
| Dữ liệu đầu vào ngoài RNG | tập dữ liệu, config | Không bỏ sót nguồn không xác định |
| Kết quả/checksum | `inside = 7850` | Đối chiếu nhanh khi phát lại |

Lưu seed theo kiểu `long` hoặc chuỗi số nguyên thập phân chính xác. Không serialize seed 64 bit qua một đường trung gian chuyển thành `double` nếu có thể làm mất độ chính xác số nguyên lớn.

Nếu chạy nhiều phiên mô phỏng, ghi **seed riêng của từng phiên**, hoặc root seed cộng với cách dẫn xuất seed đã được định nghĩa. Thông tin “seed 2026” không đủ nếu số lượng task và thứ tự cấp generator chưa được ghi lại.

## 12. Thiết kế mô phỏng có thể kiểm thử và bảo trì

Một mẫu thiết kế thuận tiện là đưa seed thành tham số đầu vào rõ ràng:

```java
// Phương thức minh họa bên trong một lớp Java.
static SimulationResult simulate(long seed, SimulationConfig config) {
    Random rng = new Random(seed);
    // Sử dụng rng chỉ trong lượt simulate này.
    // Kết quả trả về chứa thống kê và, nếu cần, seed để chẩn đoán.
    throw new UnsupportedOperationException("Ví dụ thiết kế API");
}
```

Đoạn trên **chỉ minh họa hình dạng API**, không phải chương trình đầy đủ (`SimulationResult` và `SimulationConfig` là kiểu do ứng dụng phải tự định nghĩa). Trong phần code chạy độc lập phía trên, `estimatePi(seed,trials)` chính là triển khai cụ thể của ý tưởng này.

Các nguyên tắc:
1. **Seed là đầu vào**, không giấu trong `System.currentTimeMillis()` hoặc một singleton không ai biết trạng thái.
2. Generator thuộc vòng đời của **một lượt mô phỏng**; không tái sử dụng ngoài ý muốn giữa các ca test.
3. Hàm mô phỏng cố gắng không có I/O hoặc tác dụng phụ ngoài, giúp dễ chạy lại và đối chiếu.
4. Mọi quy tắc chuyển đầu ra PRNG thành dữ liệu nghiệp vụ nên được định nghĩa rõ.
5. Nếu cần phân luồng, quản lý seed/nhánh trước khi submit task và ghi mapping ID.
6. Có test **tính xác định**, **giá trị hợp lệ** và **kiểm thử thống kê** tách biệt.

Với bài thực hành hoặc CI, cố định seed để một lỗi không xuất hiện ngẫu nhiên hôm nay rồi biến mất ngày mai. Để tìm thêm lỗi trong hệ thống sản xuất, có thể chạy thêm các seed khác nhau, nhưng **luôn ghi seed gây thất bại**.

## 13. Sai lầm phổ biến và cách phòng tránh

1. **Tạo `new Random()` không truyền seed rồi nghĩ có thể tái hiện.** Có thể mỗi lần khởi tạo nhận seed khác; truyền seed rõ ràng và log seed.
2. **Tạo `new Random(sameSeed)` trong mỗi vòng lặp.** Bạn cứ lấy lại kết quả đầu của cùng dãy; giữ một generator cho toàn bộ mô phỏng.
3. **Tưởng cùng seed luôn cho cùng kết quả khi đổi RNG.** Thuật toán có thể khác; ghi lại tên lớp/thuật toán.
4. **Thêm một lời gọi ngẫu nhiên vào nhánh phụ mà không cập nhật golden test.** Vị trí tiêu thụ thay đổi sẽ làm các mẫu sau lệch; cần kiểm soát flow hoặc thiết kế các stream độc lập.
5. **Chia sẻ một generator cho nhiều luồng và mong từng task luôn nhận cùng mẫu.** Scheduling có thể đổi thứ tự gọi; cấp generator theo task và cấu trúc split xác định.
6. **Cho rằng hai seed khác nhau nhất thiết tạo dữ liệu khác nhau.** Dãy hữu hạn có thể trùng; không dùng bất đẳng thức giữa hai seed làm invariant bắt buộc.
7. **Lấy một seed cố định làm bằng chứng chất lượng mô phỏng.** Nó chỉ đảm bảo phát lại; phải đánh giá nhiều phiên/mẫu để kiểm tra thống kê.
8. **Dùng `SecureRandom` với seed cố định để tạo token có thể phát lại.** Điều này trái với mục đích bảo mật; dùng `SecureRandom` đúng ngữ cảnh bảo mật và không làm lộ entropy.
9. **Không lưu phiên bản/thuật toán và thay cách chạy song song.** Seed đơn lẻ không đủ để tái hiện hệ thống đã thay đổi.
10. **Không ghi bound/đơn vị của mẫu.** `nextInt(6)` cho 0..5, không phải 1..6; `nextDouble(-1,1)` không bao gồm cận trên.
11. **Giữ tất cả kết quả trong mảng khổng lồ dù chỉ cần thống kê.** Có thể tính streaming như bộ đếm `inside` để tiết kiệm bộ nhớ và phòng tràn chỉ số.
12. **Nhầm “ngẫu nhiên khó dự đoán” với PRNG seeded.** PRNG dùng để mô phỏng có thể phát lại, không phải mặc định phù hợp cho mục tiêu mật mã.

## 14. Bài tập tự kiểm tra

**Bài 1 — phát lại xúc xắc.** Tại sao `rollDice(2026L,8)` chạy hai lần trả cùng dãy?  
**Đáp án:** mỗi lần tạo một `Random` từ cùng seed và gọi `nextInt(6)` đúng tám lần, theo cùng thứ tự.

**Bài 2 — hai seed khác nhau.** Có thể khẳng định hai seed khác nhau không bao giờ cho cùng một lần tung xúc xắc không?  
**Đáp án:** không. Dù trạng thái khởi tạo khác, đầu ra có sáu khả năng nên nhiều seed có thể cùng tạo một kết quả (hoặc một chuỗi ngắn).

**Bài 3 — thay đổi vị trí gọi.** Hai generator cùng seed nhưng một bên gọi `nextInt(100)` thêm một lần trước bước quan trọng. Giá trị bước đó có nhất thiết trùng không?  
**Đáp án:** không. Hai chương trình đang lấy đầu ra từ các vị trí khác nhau trong dãy.

**Bài 4 — kiểm tra π.** Mô phỏng 10.000 điểm, có 7.850 điểm trong hình tròn. Ước lượng π bao nhiêu?  
**Đáp án:** `4.0 × 7850 / 10000 = 3.14`.

**Bài 5 — kết quả giống nhau không chứng minh chất lượng.** Nếu 100 lần chạy với cùng seed đều ra π = 3.14, đó có phải 100 mẫu độc lập để đánh giá độ tin cậy?  
**Đáp án:** không. Đó chỉ là 100 lần phát lại cùng một mẫu mô phỏng.

**Bài 6 — đồng thời.** Hai task nhận generator con từ cùng root seed nhưng thứ tự gọi `split()` được đảo ở lần chạy sau. Kết quả từng task có bắt buộc trùng không?  
**Đáp án:** không. Generator gắn với mỗi task đã đổi; cần gán nhánh bằng thứ tự hoặc ID xác định.

**Bài 7 — kiểm thử đúng.** Một test tính tái lập và một test thống kê khác nhau thế nào?  
**Đáp án:** test tái lập kiểm tra cùng seed/cấu hình cho cùng kết quả; test thống kê đánh giá đặc điểm phân phối qua đủ nhiều mẫu hoặc các luồng độc lập.

## 15. Checklist trước khi nộp bài mô phỏng

- [ ] Hàm mô phỏng nhận **seed** và số lượng mẫu rõ ràng.
- [ ] Generator được tạo **một lần cho mỗi phiên**, không reset mỗi mẫu.
- [ ] Các bound ngẫu nhiên đúng quy tắc, ví dụ xúc xắc 1..6 và tọa độ `[-1,1)`.
- [ ] Mỗi phiên kiểm soát thứ tự gọi RNG và kiểm tra tham số đầu vào.
- [ ] Chạy lại cùng seed/cấu hình tạo kết quả giống nhau trong môi trường đã kiểm chứng.
- [ ] Có ít nhất một seed khác để quan sát độ biến thiên; không ép kết quả hai seed phải khác tuyệt đối.
- [ ] Có kiểm tra invariant nghiệp vụ, ví dụ `0 <= inside <= trials`.
- [ ] Nếu chạy song song, chiến lược seed/split/task ID không phụ thuộc scheduling.
- [ ] Ghi seed, thuật toán, tham số, phiên bản chương trình và kết quả vào thông tin chẩn đoán.
- [ ] Không dùng PRNG seeded cho token, mật khẩu hoặc dữ liệu cần bí mật.

## 16. Kết luận

- **Seed tạo khả năng tái lập một chuỗi giả ngẫu nhiên**, với điều kiện thuật toán, các lời gọi và ngữ cảnh được giữ nhất quán.
- Với Java 17, dùng `Random(seed)` cho ví dụ đơn giản; dùng `SplittableRandom(seed)` khi cần bộ sinh có thể tách thành các luồng độc lập theo một kế hoạch xác định.
- **Cùng seed không đảm bảo cùng kết quả toàn chương trình** nếu thay cách tiêu thụ random, dữ liệu, số luồng hoặc thuật toán.
- Mô phỏng Monte Carlo có thể được test **về tính tái lập** bằng cùng seed, đồng thời cần nhiều seed/mẫu để kiểm tra **đặc tính thống kê**.
- Khi cần phát lại lỗi, lưu **seed + tên thuật toán + tham số + phiên bản + thứ tự/chiến lược phân luồng**; không chỉ ghi một con số seed.
- PRNG để mô phỏng và RNG phục vụ bảo mật là **hai mục tiêu khác nhau**.

Tài liệu chính thức Java SE 17:
- [`Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html)
- [`SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html)
- [`RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html)
- [`RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html)
- [`ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [`SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
