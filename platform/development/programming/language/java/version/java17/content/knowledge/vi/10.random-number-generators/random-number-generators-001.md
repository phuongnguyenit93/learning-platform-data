# Vai trò của seed, trạng thái và thuật toán PRNG trong Java 17

Khi gọi `nextInt()`, `nextDouble()` hoặc các phương thức sinh số ngẫu nhiên trong Java, chương trình thường không nhận một giá trị được tạo ra hoàn toàn ngẫu nhiên từ đầu. Thay vào đó, một **bộ sinh số giả ngẫu nhiên** (*Pseudo-Random Number Generator — PRNG*) tính toán dãy giá trị bằng một thuật toán xác định, bắt đầu từ một trạng thái ban đầu.

Ba khái niệm cần phân biệt:

- **Seed:** dữ liệu dùng để khởi tạo trạng thái ban đầu của bộ sinh.
- **State:** trạng thái nội bộ thay đổi sau mỗi lần sinh số hoặc mỗi bước của thuật toán.
- **Algorithm:** quy tắc biến trạng thái hiện tại thành trạng thái tiếp theo và tạo ra giá trị đầu ra.

Hiểu ba khái niệm này giúp bạn tái lập kết quả khi kiểm thử, tạo dãy số khác nhau cho các lần chạy, sử dụng PRNG đúng trong môi trường đa luồng và chọn đúng công cụ khi cần bảo mật.

## 1. PRNG hoạt động như thế nào?

Một PRNG có thể được hình dung qua mô hình:

\[
S_{n+1} = f(S_n)
\]

\[
X_n = g(S_n)
\]

Trong đó:

- \(S_n\) là trạng thái nội bộ ở bước \(n\).
- \(f\) là hàm chuyển trạng thái do thuật toán xác định.
- \(g\) là quy tắc tạo giá trị đầu ra từ trạng thái.
- \(X_n\) là giá trị giả ngẫu nhiên mà chương trình nhận được.

Seed được dùng để khởi tạo \(S_0\). Sau đó, mỗi lần yêu cầu một giá trị, bộ sinh cập nhật trạng thái và tạo ra kết quả tiếp theo.

```text
seed
  |
  v
Khởi tạo trạng thái S0
  |
  v
Thuật toán PRNG
  |
  +----> tạo X0
  |
  v
Cập nhật trạng thái S1
  |
  +----> tạo X1
  |
  v
Cập nhật trạng thái S2
  |
  +----> tạo X2
  |
  v
...
```

Vì thuật toán xác định, **cùng thuật toán, cùng seed và cùng trình tự lời gọi sẽ tạo lại cùng dãy kết quả** trong điều kiện các quy tắc tương thích của bộ sinh được giữ nguyên. Đây là tính chất rất hữu ích cho kiểm thử và mô phỏng.

PRNG không phải bộ sinh số ngẫu nhiên thực (*true random number generator*). Nó tạo ra một dãy có vẻ ngẫu nhiên theo đặc tính thống kê của thuật toán, nhưng dãy đó được quyết định bởi trạng thái và thuật toán.

## 2. Seed: điểm khởi đầu của dãy số

Seed là đầu vào dùng để khởi tạo bộ sinh. Với một PRNG xác định:

- Cùng seed thường tạo cùng trạng thái ban đầu.
- Khác seed thường tạo dãy khác nhau.
- Seed không phải là giá trị duy nhất được phát ra; nó là dữ liệu khởi tạo.
- Seed không đảm bảo dãy có chất lượng thống kê tốt nếu thuật toán PRNG yếu.

### 2.1. Ví dụ với java.util.Random

`java.util.Random` là PRNG quen thuộc trong Java:

```java
import java.util.Random;

public class SeedDemo {
    public static void main(String[] args) {
        Random first = new Random(12345L);
        Random second = new Random(12345L);

        for (int i = 0; i < 5; i++) {
            int a = first.nextInt(100);
            int b = second.nextInt(100);

            System.out.println(a + " == " + b + " ? " + (a == b));
        }
    }
}
```

Hai đối tượng được tạo với cùng seed và nhận cùng chuỗi lời gọi `nextInt(100)`, nên từng cặp kết quả tương ứng bằng nhau.

Ví dụ đầu ra:

```text
51 == 51 ? true
80 == 80 ? true
41 == 41 ? true
28 == 28 ? true
55 == 55 ? true
```

Đặc tính quan trọng không nằm ở việc con số cụ thể là 51 hay 80, mà ở khả năng **tái tạo dãy** khi khởi tạo cùng bộ sinh và lặp lại cùng cách sử dụng.

### 2.2. Khác seed, khác dãy

```java
Random a = new Random(100L);
Random b = new Random(200L);

System.out.println(a.nextInt());
System.out.println(b.nextInt());
```

Hai seed khác nhau thường tạo hai dãy khác nhau. Tuy nhiên, không nên hiểu rằng **mọi seed khác nhau luôn tạo một dãy hoàn toàn không liên quan hoặc độc lập về mặt thống kê**. Điều đó phụ thuộc vào không gian trạng thái và chất lượng thuật toán.

Một thuật toán có trạng thái hữu hạn chỉ có hữu hạn trạng thái khởi đầu. Nhiều seed có thể ánh xạ vào cùng trạng thái nội bộ, hoặc tạo những dãy có quan hệ nhất định.

### 2.3. Không seed tường minh: bộ sinh tự khởi tạo

Bạn có thể viết:

```java
Random random = new Random();
```

Trong trường hợp này, `Random` tự khởi tạo seed theo cơ chế của implementation Java. Dùng constructor không tham số phù hợp khi bạn không cần tái tạo chính xác một dãy đã biết.

Để kiểm thử có thể lặp lại, thường nên cung cấp seed tường minh:

```java
Random random = new Random(202617L);
```

Ghi seed vào log khi chạy mô phỏng hoặc kiểm thử ngẫu nhiên cũng giúp tái hiện lỗi về sau.

## 3. State: trạng thái thay đổi sau mỗi lần sinh số

Seed chỉ khởi tạo bộ sinh. Sau khi bắt đầu sinh số, PRNG duy trì **state** riêng và cập nhật state qua các bước của thuật toán.

Ví dụ khái niệm:

```text
Seed = 42
  |
  v
State S0
  | nextInt()
  v
State S1 ----> output 1
  | nextDouble()
  v
State S2 ----> output 2
  | nextInt()
  v
State S3 ----> output 3
```

Với cùng seed nhưng số lần gọi hoặc thứ tự gọi khác nhau, chương trình có thể nhận các giá trị khác nhau ở những vị trí tương ứng.

### 3.1. Cùng seed nhưng trình tự gọi khác nhau

```java
import java.util.Random;

public class CallOrderDemo {
    public static void main(String[] args) {
        Random first = new Random(42L);
        Random second = new Random(42L);

        int firstA = first.nextInt();
        int firstB = first.nextInt();

        int secondA = second.nextInt();
        double extra = second.nextDouble();
        int secondB = second.nextInt();

        System.out.println(firstA == secondA); // true
        System.out.println(firstB == secondB); // thường false
        System.out.println(extra);
    }
}
```

Lời gọi `nextDouble()` ở bộ sinh thứ hai đã tiêu thụ trạng thái theo cách của thuật toán, nên giá trị `nextInt()` tiếp theo không còn tương ứng với lần gọi thứ hai của bộ sinh đầu tiên.

Với các phương thức có thể cần nhiều bước nội bộ, ví dụ `nextInt(bound)` dùng cơ chế loại bỏ một số giá trị để tránh phân phối lệch, số lần cập nhật trạng thái có thể không cố định cho mọi đầu vào. Vì vậy, muốn tái lập kết quả, cần giữ **cả trình tự lời gọi**, không chỉ giữ seed.

### 3.2. State không đồng nghĩa với seed

Seed là đầu vào khởi tạo. State là dữ liệu nội bộ sau khi bộ sinh đã tiến triển qua một số bước.

Một số API cho phép đặt lại bộ sinh bằng seed, ví dụ:

```java
Random random = new Random(10L);

int first = random.nextInt();
int second = random.nextInt();

random.setSeed(10L); // Khởi tạo lại chuỗi theo seed đã cho.
int repeatedFirst = random.nextInt();
```

Với `Random`, gọi `setSeed` đặt lại trạng thái của bộ sinh để chuỗi được tạo lại. Nhưng không phải mọi API PRNG đều có phương thức `setSeed`; chẳng hạn `SplittableRandom` không cung cấp cách reseed một instance đang tồn tại.

Không nên giả định có thể đọc, lưu hoặc khôi phục state nội bộ của mọi bộ sinh chỉ bằng cách giữ lại seed. Với một số ứng dụng cần checkpoint mô phỏng, bạn phải chọn API/thiết kế có khả năng lưu trạng thái được hỗ trợ rõ ràng hoặc quản lý tiến trình sinh số theo cách riêng.

## 4. Thuật toán PRNG quyết định đặc tính của dãy

Seed giống nhau nhưng **thuật toán khác nhau** có thể tạo dãy khác nhau. Thuật toán quyết định:

- Cách cập nhật state.
- Kích thước không gian trạng thái.
- Chu kỳ trước khi dãy lặp lại.
- Chất lượng phân phối và tương quan giữa các giá trị.
- Chi phí tính toán.
- Khả năng chạy song song hoặc chia tách luồng sinh số.
- Mức độ phù hợp cho mục đích bảo mật.

Không có thuật toán duy nhất tốt nhất cho mọi trường hợp. Bộ sinh dùng cho mô phỏng có thể ưu tiên tốc độ và khả năng tái lập; bộ sinh dùng cho khóa hoặc token cần đặc tính bảo mật.

### 4.1. Linear Congruential Generator của Random

`java.util.Random` trong Java sử dụng một dạng **Linear Congruential Generator (LCG)** với trạng thái 48 bit. Quy tắc chuyển trạng thái được quy định theo công thức:

\[
S_{n+1} = (S_n \times 0x5DEECE66D + 0xB)
            \bmod 2^{48}
\]

Khi khởi tạo bằng seed, `Random` biến đổi seed đầu vào và giữ trạng thái trong 48 bit. Các phương thức `next(...)` lấy những bit từ state để tạo giá trị.

Ví dụ:

```java
Random random = new Random(123L);
int a = random.nextInt();
double b = random.nextDouble();
long c = random.nextLong();
```

Đặc điểm cần nhớ:

- Thuật toán được đặc tả để các implementation Java tương thích tạo cùng chuỗi khi dùng cùng seed và cùng chuỗi lời gọi.
- Trạng thái chỉ có 48 bit, nên không gian state hữu hạn.
- `Random` phù hợp với nhiều nhu cầu mô phỏng và kiểm thử phổ thông.
- Không dùng `Random` để sinh mật khẩu, token xác thực, khóa hoặc dữ liệu cần chống đoán.

Một hệ quả của state 48 bit là các seed đầu vào khác nhau không đảm bảo tương ứng với trạng thái 48 bit khác nhau; các bit vượt quá phần trạng thái hiệu dụng không thể làm không gian state lớn hơn.

### 4.2. Các PRNG hiện đại trong Java 17

Java 17 giới thiệu gói `java.util.random` thông qua JEP 356 — Enhanced Pseudo-Random Number Generators. API mới cung cấp interface `RandomGenerator` và cơ chế chọn implementation qua `RandomGeneratorFactory`.

Một số họ thuật toán được cung cấp trong JDK 17 gồm:

- **LXM:** kết hợp thành phần LCG với hàm trộn kiểu xor/multiply; có nhiều cấu hình trạng thái khác nhau.
- **Xoroshiro:** họ thuật toán dùng phép toán XOR, dịch bit và quay bit.
- **Xoshiro:** họ thuật toán liên quan, có các biến thể với kích thước trạng thái và đặc tính khác nhau.
- **Legacy generator:** như `Random` và `SplittableRandom` vẫn có thể sử dụng qua API tương thích.

Tên thuật toán cụ thể có thể xem qua `RandomGeneratorFactory`. Không nên tự đoán tên từ họ thuật toán; hãy dùng factory để lấy danh sách các implementation được runtime cung cấp.

## 5. RandomGenerator: API chung của Java 17

Java 17 bổ sung interface `java.util.random.RandomGenerator`. Nó mô tả nhóm thao tác sinh số như `nextInt()`, `nextLong()`, `nextDouble()` và các biến thể có giới hạn.

Nhờ interface chung, code có thể sử dụng nhiều thuật toán mà không phụ thuộc trực tiếp vào một lớp cụ thể.

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorDemo {
    public static void main(String[] args) {
        RandomGenerator generator =
                RandomGeneratorFactory
                        .of("L64X128MixRandom")
                        .create(12345L);

        System.out.println(generator.nextInt(100));
        System.out.println(generator.nextDouble());
        System.out.println(generator.nextLong());
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 RandomGeneratorDemo.java
java RandomGeneratorDemo
```

Trong ví dụ:

1. `RandomGeneratorFactory.of(...)` chọn implementation theo tên thuật toán.
2. `create(12345L)` tạo generator với seed được chỉ định.
3. Biến `generator` chỉ phụ thuộc interface `RandomGenerator`; có thể thay implementation mà không phải đổi cách gọi các phương thức sinh số cơ bản.

Tên `L64X128MixRandom` là một implementation có trong các thuật toán PRNG của JDK 17. Khi cần triển khai trên runtime khác, hãy xác nhận thuật toán được cung cấp ở runtime mục tiêu.

### 5.1. Liệt kê các thuật toán được cung cấp

Bạn có thể khám phá các factory có sẵn:

```java
import java.util.random.RandomGeneratorFactory;

public class ListGenerators {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
                .map(RandomGeneratorFactory::name)
                .sorted()
                .forEach(System.out::println);
    }
}
```

Danh sách phụ thuộc vào các implementation mà runtime cung cấp. Khi viết ứng dụng cần một thuật toán cụ thể, hãy chọn tên rõ ràng và kiểm tra khả năng hỗ trợ trong môi trường triển khai.

### 5.2. Khi nào dùng API chung?

`RandomGenerator` hữu ích khi:

- Muốn chọn thuật toán bằng cấu hình.
- Muốn viết hàm nhận một generator để kiểm thử với seed xác định.
- Muốn dùng chung logic sinh số cho `Random`, `SplittableRandom` hoặc generator khác.
- Muốn khai thác các thuật toán hiện đại trong JDK 17.

Ví dụ tiêm generator vào hàm:

```java
import java.util.random.RandomGenerator;

static int rollDie(RandomGenerator random) {
    return random.nextInt(1, 7);
}
```

Hàm không cần biết generator là lớp nào. Khi kiểm thử, truyền generator có seed cố định; khi chạy mô phỏng, chọn implementation phù hợp.

## 6. Một số bộ sinh phổ biến và cách lựa chọn

| API | Đặc điểm | Trường hợp sử dụng |
| --- | --- | --- |
| `Random` | LCG 48 bit; thread-safe; tương thích lâu đời | Ví dụ, ứng dụng phổ thông và code cần chuỗi có tính tương thích của `Random` |
| `SplittableRandom` | Thiết kế cho việc chia tách generator; không thread-safe | Mô phỏng hoặc tác vụ song song có thể chia nguồn sinh số |
| `ThreadLocalRandom` | Generator gắn với thread hiện tại; giảm tranh chấp khi nhiều thread | Tác vụ đa luồng cần số giả ngẫu nhiên phổ thông, không cần tự quản lý seed |
| `RandomGenerator` + factory | Interface chung và nhiều thuật toán hiện đại trong Java 17 | Ứng dụng muốn lựa chọn thuật toán rõ ràng, tách code khỏi implementation |
| `SecureRandom` | Bộ sinh phục vụ mục đích bảo mật, thường lấy entropy từ provider/hệ điều hành | Token, nonce, salt, khóa và giá trị nhạy cảm |

### 6.1. Random: đơn giản và có tính tái lập

`Random` có thể chia sẻ giữa các thread vì các thao tác cập nhật seed được đồng bộ theo cơ chế thread-safe. Nhưng khi nhiều thread cùng gọi một instance, thứ tự thread nào nhận giá trị nào phụ thuộc lịch thực thi. Dãy toàn cục có thể thay đổi giữa các lần chạy song song dù seed ban đầu giống nhau.

Nếu cần mỗi thread có generator riêng, có thể chọn `ThreadLocalRandom` hoặc tạo các generator riêng với seed được quản lý có chủ đích.

### 6.2. SplittableRandom: chia generator cho tác vụ

`SplittableRandom` được thiết kế để dùng trong thuật toán chia tách công việc. Một generator có thể tạo generator con bằng `split()`:

```java
import java.util.SplittableRandom;

public class SplitDemo {
    public static void main(String[] args) {
        SplittableRandom parent = new SplittableRandom(2026L);

        SplittableRandom firstTask = parent.split();
        SplittableRandom secondTask = parent.split();

        System.out.println(firstTask.nextInt(100));
        System.out.println(secondTask.nextInt(100));
    }
}
```

Mỗi tác vụ dùng generator riêng, tránh việc nhiều thread cập nhật cùng một state. Các luồng sinh được thiết kế để có tính độc lập thống kê tốt cho mục đích sử dụng thông thường, nhưng không nên diễn giải thành bảo đảm toán học tuyệt đối rằng mọi dãy con hoàn toàn độc lập.

`SplittableRandom` **không thread-safe**. Không chia sẻ cùng một instance cho nhiều thread thao tác đồng thời. Hãy chia tách trước hoặc bảo đảm mỗi instance chỉ được một luồng sở hữu tại một thời điểm.

### 6.3. ThreadLocalRandom: generator theo thread

Ví dụ:

```java
import java.util.concurrent.ThreadLocalRandom;

public class ThreadLocalDemo {
    public static void main(String[] args) {
        int value = ThreadLocalRandom.current().nextInt(1, 7);
        System.out.println(value);
    }
}
```

`ThreadLocalRandom.current()` trả generator gắn với thread hiện tại. Đây là lựa chọn thực tế cho nhiều tác vụ đa luồng cần số giả ngẫu nhiên mà không cần tự quản lý seed cho từng thread.

API này không cung cấp cơ chế đặt seed công khai như `Random(long seed)`; không nên chọn nó nếu mục tiêu chính là tái tạo dãy theo seed do ứng dụng chỉ định.

### 6.4. SecureRandom: khi cần tính khó dự đoán

`SecureRandom` là lựa chọn cho dữ liệu liên quan đến bảo mật:

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureRandomDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();
        byte[] token = new byte[32];
        secureRandom.nextBytes(token);

        System.out.println(HexFormat.of().formatHex(token));
    }
}
```

`SecureRandom` thường được khởi tạo với entropy từ provider và nguồn ngẫu nhiên của môi trường. Không dùng seed cố định để mong có tính bảo mật; nếu tự đặt seed yếu hoặc có thể đoán, bạn có thể làm giảm độ khó dự đoán của dữ liệu.

## 7. Tính tái lập: cùng seed chưa đủ nếu cách sử dụng thay đổi

Tính tái lập hữu ích trong:

- Kiểm thử đơn vị.
- Mô phỏng khoa học.
- Benchmark có dữ liệu đầu vào ổn định.
- Phát lại một kịch bản lỗi.
- So sánh hai thuật toán trên cùng bộ dữ liệu.

Để tái lập một phép chạy, cần ghi nhận nhiều hơn seed:

1. **Tên/loại PRNG:** `Random`, `SplittableRandom` hoặc thuật toán cụ thể.
2. **Seed:** giá trị dùng để khởi tạo.
3. **Phiên bản runtime/API:** đặc biệt nếu dùng thuật toán do factory cung cấp và cần tương thích giữa các môi trường.
4. **Trình tự gọi:** loại phương thức, số lần gọi, giới hạn và thứ tự thực thi.
5. **Cấu trúc song song:** cách chia generator, cách gán generator cho tác vụ và thứ tự xử lý.

Ví dụ, chỉ lưu seed nhưng sau này thêm một lời gọi `nextInt()` trước đoạn tạo dữ liệu sẽ làm các giá trị tiếp theo dịch chuyển trong dãy.

### 7.1. Truyền generator vào code thay vì tạo rải rác

Một cách thiết kế thuận tiện cho kiểm thử:

```java
import java.util.random.RandomGenerator;

public class DiceService {
    private final RandomGenerator random;

    public DiceService(RandomGenerator random) {
        this.random = random;
    }

    public int roll() {
        return random.nextInt(1, 7);
    }
}
```

Ở môi trường kiểm thử:

```java
RandomGenerator testGenerator =
        RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(123L);

DiceService service = new DiceService(testGenerator);
```

Ở môi trường chạy thật, có thể cung cấp generator được cấu hình riêng. Cách tiêm dependency này làm rõ nơi tạo seed và giúp test kiểm soát được nguồn số giả ngẫu nhiên.

### 7.2. Tái lập trong xử lý song song

Với tác vụ song song, kết quả còn phụ thuộc cách phân chia công việc. Nếu các thread chia sẻ một `Random`, lịch chạy có thể quyết định thread nào nhận phần tử nào của dãy.

Để tái lập tốt hơn:

- Chia generator theo cấu trúc tác vụ thay vì chia sẻ cùng một instance.
- Dùng `SplittableRandom` hoặc generator có khả năng split khi phù hợp.
- Gán generator con cho từng tác vụ một cách xác định.
- Không để kết quả phụ thuộc vào thứ tự thread hoàn tất nếu thứ tự đó không được kiểm soát.
- Ghi lại cấu hình split/seed và cách phân chia công việc.

Chỉ đặt seed cố định cho một bộ sinh dùng chung không tự động làm toàn bộ chương trình đa luồng tái lập.

## 8. Chất lượng PRNG và giới hạn của seed

Một seed không thể biến thuật toán yếu thành thuật toán tốt. Chất lượng dãy phụ thuộc vào:

- Chu kỳ (*period*) trước khi state lặp lại.
- Phân phối của các bit đầu ra.
- Tương quan giữa các giá trị liên tiếp.
- Tương quan giữa các dãy khi dùng nhiều seed hoặc split.
- Khả năng hoạt động tốt khi chạy song song.
- Độ khó dự đoán, nếu mục tiêu có liên quan đến bảo mật.

Một PRNG có chu kỳ lớn vẫn có thể có cấu trúc thống kê không phù hợp với một số phép mô phỏng. Ngược lại, một generator rất nhanh không nhất thiết an toàn trước kẻ tấn công.

### 8.1. Không tự tạo số trong một khoảng bằng toán tử modulo tùy tiện

Ví dụ:

```java
int value = random.nextInt() % 10;
```

Giá trị có thể âm, và phân phối của phần dư có thể không đều do số lượng giá trị nguồn không chia hết cho 10. Hãy dùng API giới hạn:

```java
int value = random.nextInt(10); // 0 đến 9
int dice = random.nextInt(1, 7); // 1 đến 6
```

Các overload có bound được thiết kế để tạo giá trị trong phạm vi yêu cầu với phân phối phù hợp, tránh lỗi modulo phổ biến.

### 8.2. Seed ít entropy không phù hợp để tạo bí mật

Seed cố định như `12345L` rất tốt cho test nhưng dễ đoán. Nếu một ứng dụng dùng PRNG không bảo mật để tạo token, người biết thuật toán và trạng thái có thể dự đoán những giá trị tiếp theo.

Với dữ liệu bí mật, hãy dùng `SecureRandom`. Không tự thay thế bằng:

```java
new Random(System.currentTimeMillis())
```

Thời gian hiện tại thường có thể đoán trong một khoảng nhất định, và `Random` không được thiết kế để chống dự đoán. Tăng độ phức tạp seed không biến một thuật toán không mật mã thành CSPRNG.

## 9. Chọn PRNG theo tình huống

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Test cần kết quả lặp lại | `Random(seed)` hoặc generator xác định qua factory | Có thể tái lập dãy khi giữ seed, thuật toán và trình tự lời gọi. |
| Mô phỏng tuần tự thông thường | `RandomGenerator` với thuật toán phù hợp hoặc `Random` | Chọn API theo yêu cầu chất lượng và tương thích. |
| Tác vụ song song cần generator con | `SplittableRandom` hoặc generator hỗ trợ split | Mỗi tác vụ có nguồn sinh riêng, tránh chia sẻ state. |
| Ứng dụng đa luồng cần số ngẫu nhiên phổ thông theo thread | `ThreadLocalRandom.current()` | Giảm tranh chấp khi nhiều thread sinh số. |
| Token, nonce, khóa, salt ngẫu nhiên | `SecureRandom` | Hướng tới khả năng chống dự đoán và yêu cầu bảo mật. |
| Cần đổi thuật toán bằng cấu hình trên Java 17 | `RandomGeneratorFactory` | Chọn implementation bằng tên và dùng qua interface chung. |

Không chọn PRNG chỉ dựa trên việc một ví dụ chạy nhanh. Hãy cân nhắc mục tiêu, tính tái lập, cách chạy song song, chất lượng thống kê và yêu cầu bảo mật.

## 10. Ví dụ tổng hợp: mô phỏng có thể tái lập

Giả sử bạn muốn mô phỏng 10.000 lần gieo xúc xắc và đếm số lần xuất hiện từng mặt. Seed cố định giúp các lần chạy kiểm thử có cùng kết quả:

```java
import java.util.Arrays;
import java.util.Random;

public class DiceSimulation {
    static int[] simulate(long seed, int rolls) {
        Random random = new Random(seed);
        int[] counts = new int[6];

        for (int i = 0; i < rolls; i++) {
            int face = random.nextInt(6);
            counts[face]++;
        }

        return counts;
    }

    public static void main(String[] args) {
        int[] first = simulate(2026L, 10_000);
        int[] second = simulate(2026L, 10_000);

        System.out.println(Arrays.toString(first));
        System.out.println(Arrays.equals(first, second));
    }
}
```

Hai lần gọi `simulate` tạo generator mới với cùng seed, cùng số lần gọi `nextInt(6)` và cùng thứ tự. Vì vậy, mảng kết quả được tái lập.

Nếu đổi seed hoặc thêm một lần gọi random ở trước vòng lặp, kết quả mô phỏng thay đổi. Đó là hành vi mong đợi của PRNG.

Khi đánh giá xác suất, một lần chạy với 10.000 lần gieo chỉ là mẫu mô phỏng. Không nên kỳ vọng số lần xuất hiện của sáu mặt phải bằng nhau tuyệt đối; sai lệch ngẫu nhiên là bình thường.

## 11. Những nhầm lẫn thường gặp

**“Seed chính là số ngẫu nhiên đầu tiên.”**  
Không đúng. Seed là dữ liệu khởi tạo trạng thái. Giá trị đầu ra được tính bởi thuật toán từ trạng thái đó.

**“Cùng seed luôn tạo cùng dãy dù đổi loại PRNG.”**  
Không đúng. Thuật toán khác nhau có quy tắc chuyển trạng thái và ánh xạ đầu ra khác nhau.

**“Cùng seed là đủ để tái lập chương trình.”**  
Chưa đủ. Cần cùng thuật toán, cùng trình tự gọi và cấu trúc xử lý tương ứng. Chạy song song còn phụ thuộc cách chia và gán generator.

**“Khác seed thì các dãy chắc chắn độc lập.”**  
Không thể kết luận như vậy. Tính độc lập thống kê phụ thuộc thuật toán và cách khởi tạo.

**“Random thread-safe nên thứ tự kết quả của từng thread luôn ổn định.”**  
Không đúng. Thread-safe bảo vệ tính nhất quán của trạng thái, nhưng thứ tự thread nhận giá trị phụ thuộc lịch thực thi.

**“SplittableRandom dùng chung giữa các thread là an toàn.”**  
Không đúng. `SplittableRandom` không thread-safe; nên split và cấp generator riêng cho tác vụ.

**“Random đủ an toàn để tạo token.”**  
Không đúng. `Random` và PRNG phổ thông không được thiết kế để chống dự đoán. Dùng `SecureRandom` cho dữ liệu nhạy cảm.

**“Thời gian hiện tại là seed bảo mật tốt.”**  
Không đúng. Thời gian có thể đoán được trong một phạm vi; seed dễ đoán làm dãy dễ bị dự đoán hơn.

## 12. Câu hỏi tự kiểm tra

**1. Seed có vai trò gì trong PRNG?**  
Khởi tạo trạng thái ban đầu để thuật toán bắt đầu tạo dãy.

**2. State khác seed ở điểm nào?**  
Seed là đầu vào khởi tạo; state là trạng thái nội bộ thay đổi khi PRNG sinh số.

**3. Vì sao cùng seed nhưng trình tự gọi khác có thể cho kết quả khác?**  
Vì mỗi lời gọi tiêu thụ/cập nhật state; một lời gọi bổ sung làm các giá trị tiếp theo dịch chuyển.

**4. `Random` dùng thuật toán nào trong Java?**  
Một LCG với trạng thái 48 bit, có quy tắc chuyển trạng thái được đặc tả.

**5. API nào được bổ sung trong Java 17 để chuẩn hóa cách dùng nhiều PRNG?**  
Gói `java.util.random`, bao gồm `RandomGenerator` và `RandomGeneratorFactory`.

**6. Vì sao nên dùng `SplittableRandom` trong một số tác vụ song song?**  
Có thể chia tách generator thành các nguồn riêng cho tác vụ, tránh nhiều thread cùng cập nhật một state; mỗi instance vẫn cần được sử dụng theo quy tắc không thread-safe.

**7. Khi nào cần `SecureRandom`?**  
Khi tạo dữ liệu cần khó dự đoán như token, nonce hoặc khóa.

**8. Vì sao không dùng `random.nextInt() % 10` để tạo số từ 0 đến 9?**  
Có thể nhận số âm và phân phối không đều; dùng `nextInt(10)`.

**9. Muốn tái lập lỗi từ một lần chạy ngẫu nhiên cần ghi gì?**  
Seed, loại/thuật toán generator, runtime liên quan, trình tự gọi và cấu trúc chia tác vụ.

**10. PRNG có phải nguồn ngẫu nhiên thực không?**  
Không. PRNG là bộ sinh xác định dựa trên trạng thái và thuật toán; nó tạo dãy giả ngẫu nhiên.

## Tài liệu tham khảo chính thức

- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): API PRNG mới trong Java 17, `RandomGenerator`, factory và các thuật toán.
- [Java SE 17 API — `java.util.random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): tổng quan API generator và factory.
- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): interface sinh số giả ngẫu nhiên.
- [Java SE 17 API — `RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): lựa chọn và khởi tạo implementation theo tên.
- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): thuật toán, seed và tính tương thích của `Random`.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): generator có thể split và quy tắc sử dụng trong môi trường song song.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator gắn với thread hiện tại.
- [Java SE 17 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): bộ sinh số ngẫu nhiên phục vụ mục đích bảo mật.
