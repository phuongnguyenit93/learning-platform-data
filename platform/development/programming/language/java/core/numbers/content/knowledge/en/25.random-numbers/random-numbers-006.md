# RandomGenerator và RandomGeneratorFactory từ Java 17

## 1. Vì sao Java 17 bổ sung API số ngẫu nhiên?

Trước Java 17, nhiều chương trình quen với `java.util.Random`, `ThreadLocalRandom`, `SplittableRandom` hoặc `SecureRandom`. Mỗi lựa chọn có thế mạnh riêng, nhưng việc thay đổi thuật toán và truy vấn đặc điểm của bộ sinh còn thiếu một API thống nhất. **Java 17 giới thiệu `java.util.random.RandomGenerator` và `RandomGeneratorFactory`** như giao diện và cơ chế lựa chọn thuật toán trong `java.base` (JEP 356).

Bài này tập trung vào hai thành phần:

- **`RandomGenerator`**: giao diện chung để **sử dụng** một bộ sinh số ngẫu nhiên, thường là số *giả ngẫu nhiên* (*pseudorandom*).
- **`RandomGeneratorFactory<T extends RandomGenerator>`**: factory để **tìm, lựa chọn, kiểm tra đặc tính và tạo** các instance của một thuật toán cụ thể.

Hai vai trò bổ sung cho nhau: mã nghiệp vụ nên phụ thuộc vào `RandomGenerator` khi chỉ cần phát sinh số; mã cấu hình, khởi tạo hoặc lựa chọn thuật toán mới cần quan tâm đến `RandomGeneratorFactory`.

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");
RandomGenerator rng = factory.create();

int die = rng.nextInt(1, 7); // 1, 2, 3, 4, 5 hoặc 6
```

Đây là **đoạn mã minh họa** để đặt trong một method hoặc lớp Java, chưa phải chương trình độc lập. Ví dụ đầy đủ với lệnh `javac`/`java` ở phần 7.

### Giả ngẫu nhiên có nghĩa là gì?

Một thuật toán giả ngẫu nhiên tạo dãy kết quả từ **trạng thái nội bộ**. Mỗi lần gọi như `nextInt()` thường làm bộ sinh tiến sang trạng thái tiếp theo. Dãy số được thiết kế có đặc tính thống kê hữu ích, nhưng về nguyên tắc xác định bởi thuật toán và trạng thái/seed ban đầu.

Vì vậy, “random” ở đây **không đồng nghĩa với ngẫu nhiên dùng cho bảo mật**. Seed dễ đoán hoặc thuật toán không có khả năng chống dự đoán sẽ không thích hợp cho token đăng nhập, khóa, mã OTP hoặc bí mật phiên. Với yêu cầu bảo mật, dùng `java.security.SecureRandom` và thiết kế bảo mật chuyên biệt; `SecureRandom` cũng thực thi `RandomGenerator` trong Java 17 nhưng không thể thay bằng bất kỳ PRNG nhanh nào.

## 2. Phân biệt giao diện, factory và thuật toán

`RandomGenerator` là một **interface**, không thể dùng `new RandomGenerator()`. Nó cung cấp các phương thức như `nextInt()`, `nextLong()`, `nextDouble()` và stream để ứng dụng tiêu thụ kết quả.

`RandomGeneratorFactory` là một **lớp factory có tham số kiểu**, mỗi factory gắn với một thuật toán nhất định. Ví dụ `RandomGeneratorFactory.of("L64X128MixRandom")` tìm factory cho thuật toán có tên đã chọn; `factory.create()` tạo một instance để dùng.

```text
Tên thuật toán ──→ RandomGeneratorFactory ──create()──→ RandomGenerator
                    │                         │
                    │ name(), stateBits()     └── nextInt(), nextDouble(), ...
                    │ period(), isSplittable()
                    └── thông tin và khả năng của thuật toán
```

Các lựa chọn tạo bộ sinh:

| Cách tạo | Tác dụng | Khi nào dùng |
| --- | --- | --- |
| `RandomGenerator.getDefault()` | Tạo một bộ sinh với thuật toán mặc định của runtime. | Không yêu cầu cụ thể về danh tính thuật toán. |
| `RandomGenerator.of("L64X128MixRandom")` | Tạo bộ sinh theo tên thuật toán. | Muốn thuật toán có tên xác định, không cần quản lý factory. |
| `RandomGeneratorFactory.getDefault().create()` | Lấy factory mặc định rồi tạo bộ sinh. | Cần thêm metadata từ factory hoặc muốn tạo nhiều instance. |
| `RandomGeneratorFactory.of(name).create()` | Tạo bộ sinh từ thuật toán được chọn. | Khởi tạo có cấu hình tên thuật toán. |
| `RandomGeneratorFactory.of(name).create(seed)` | Yêu cầu tạo bộ sinh từ seed `long`. | Thí nghiệm, tái lập kết quả và kiểm thử theo thuật toán cố định. |
| `RandomGeneratorFactory.all()` | Stream các factory khả dụng, không gồm thuật toán bị đánh dấu deprecated. | Khám phá/lọc thuật toán theo khả năng, metadata. |

**Đừng giả định thuật toán mặc định bất biến theo JDK hoặc phiên bản.** Đặc tả `getDefault()` cho phép lựa chọn thuật toán thay đổi theo thời gian. Nếu cần tái hiện dãy từ một thuật toán cụ thể, hãy chọn **tên thuật toán**, kiểm soát seed và thứ tự các lời gọi.

Với `RandomGeneratorFactory.of(name)`, tên không tồn tại sẽ gây `IllegalArgumentException`; không nên tự nhận mọi thuật toán có trong một runtime khác đều hiện diện ở runtime của mình.

## 3. Cách lấy và sử dụng bộ sinh trong Java 17

### 3.1. Lựa chọn mặc định

```java
RandomGenerator rng = RandomGenerator.getDefault();

int anyInt = rng.nextInt();
long anyLong = rng.nextLong();
double unit = rng.nextDouble(); // [0.0, 1.0)
boolean flag = rng.nextBoolean();
```

Các lời gọi trên cung cấp các kiểu cơ bản. `nextInt()` không truyền phạm vi có thể tạo bất kỳ giá trị `int` nào; `nextDouble()` tạo một giá trị không âm, nhỏ hơn 1.0. Giá trị thực tế **thay đổi theo trạng thái bộ sinh**. Không nên ghi một dãy stdout cụ thể cho bộ sinh không có seed được kiểm soát.

### 3.2. Chọn thuật toán theo tên

```java
RandomGenerator rng = RandomGenerator.of("L64X128MixRandom");
System.out.println(rng.nextInt(100)); // một số nguyên từ 0 đến 99
```

Tên `L64X128MixRandom` là một thuật toán thuộc nhóm **LXM** có trong Java 17. Tên thuật toán là cấu hình kỹ thuật, không nên nhầm với tên lớp triển khai có thể thay đổi hay định danh của một instance.

### 3.3. Factory và seed

```java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator first = factory.create(12345L);
RandomGenerator second = factory.create(12345L);

boolean sameSequence = true;
for (int i = 0; i < 10; i++) {
    sameSequence &= first.nextInt() == second.nextInt();
}
System.out.println(sameSequence); // true
```

Với **cùng thuật toán hỗ trợ seed `long`**, cùng seed và cùng **chuỗi lời gọi**, hai bộ sinh bắt đầu từ cùng trạng thái và cho các giá trị tương ứng giống nhau. Điều này có ích khi tái tạo một phép mô phỏng hoặc lỗi kiểm thử.

Phải hiểu đúng giới hạn của factory: API có ba overload `create()`, `create(long seed)` và `create(byte[] seed)`. Đặc tả cho phép `create(long)` **quay về hành vi tương tự `create()` nếu thuật toán không hỗ trợ seed kiểu `long`**; overload nhận `byte[]` cũng có điều kiện hỗ trợ riêng. Vì vậy, muốn có reproducibility đáng tin cậy, chọn thuật toán đã xác minh hỗ trợ kiểu seed sử dụng thay vì giả định mọi provider đều giống nhau.

## 4. Phạm vi số, kiểu dữ liệu và stream

Điểm mạnh của interface chung là API nhất quán cho các kiểu số và nhiều dạng phân phối:

| Lời gọi | Miền kết quả / ý nghĩa |
| --- | --- |
| `rng.nextInt()` | Giá trị `int` được sinh từ toàn bộ miền giá trị `int`. |
| `rng.nextInt(10)` | Số nguyên từ **0 đến 9**, chặn trên 10 **không** nằm trong miền. |
| `rng.nextInt(5, 10)` | Số nguyên từ **5 đến 9**, tức `[5, 10)`. |
| `rng.nextLong(100L, 200L)` | Giá trị `long` thuộc `[100, 200)`. |
| `rng.nextDouble()` | Giá trị `double` trong `[0.0, 1.0)`. |
| `rng.nextDouble(2.0, 5.0)` | Giá trị `double` thuộc `[2.0, 5.0)`. |
| `rng.nextBoolean()` | Giá trị logic `true` hoặc `false`. |
| `rng.nextGaussian()` | Giá trị theo phân phối chuẩn với kỳ vọng 0, độ lệch chuẩn 1. |
| `rng.nextExponential()` | Giá trị không âm theo phân phối mũ với kỳ vọng 1. |
| `rng.ints(5, 1, 7)` | `IntStream` **gồm 5 giá trị**, mỗi giá trị trong `[1, 7)`. |
| `rng.longs(...)`, `rng.doubles(...)` | Các biến thể stream cho `long` và `double`. |

**Chặn trái inclusive, chặn phải exclusive** đối với các overload nhận `origin` và `bound`. Đây là cách thiết kế thuận tiện: sinh mặt xúc xắc sáu mặt bằng `nextInt(1, 7)`, thay vì `nextInt(1, 6)` khiến mặt 6 không bao giờ xuất hiện.

```java
int die = rng.nextInt(1, 7);
int zeroToNine = rng.nextInt(10);

int[] fiveDice = rng.ints(5, 1, 7).toArray();
double[] tenFractions = rng.doubles(10).toArray();
```

Các overload stream nhận `streamSize` có số phần tử hữu hạn. Các overload không truyền kích thước tạo stream có thể hoạt động gần như vô hạn, cần giới hạn bằng `limit(n)` hoặc short-circuit operation. **Đừng thu thập stream vô hạn vào một danh sách/array**.

Tham số không hợp lệ có thể dẫn đến `IllegalArgumentException`: `rng.nextInt(0)` có bound không dương; `rng.nextInt(10, 10)` có origin không nhỏ hơn bound; `rng.ints(-1)` có số phần tử âm. Xác thực dữ liệu đầu vào trước khi gọi.

Số được sinh từ `nextDouble()` không phải số thập phân chính xác dành cho kế toán; việc nhân với 100 và chuyển sang `BigDecimal` cũng không tự biến nó thành nguồn số ngẫu nhiên có thể kiểm toán hoặc tài chính an toàn.

## 5. RandomGeneratorFactory: khám phá và đánh giá thuật toán

Factory cung cấp metadata giúp chọn thuật toán dựa theo **yêu cầu sử dụng**.

```java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

System.out.println(factory.name());       // L64X128MixRandom
System.out.println(factory.isSplittable()); // true
```

Các phương thức metadata quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `name()` | Tên định danh thuật toán mà factory tạo ra. |
| `group()` | Nhóm thuật toán, chẳng hạn LXM hay Legacy. |
| `stateBits()` | Số bit biểu diễn trạng thái của thuật toán; **không đồng nghĩa số bit entropy của seed**. |
| `period()` | Chu kỳ thuật toán dưới dạng `BigInteger`; trả `BigInteger.ZERO` nếu không xác định được. |
| `equidistribution()` | Thông tin mức `k`-equidistribution của thuật toán. |
| `isSplittable()` | Có hỗ trợ tạo bộ sinh mới qua cơ chế `split` không. |
| `isJumpable()` | Có hỗ trợ nhảy xa trong chu kỳ không. |
| `isLeapable()` | Có hỗ trợ bước nhảy rất xa không. |
| `isArbitrarilyJumpable()` | Có hỗ trợ nhảy tùy khoảng không. |
| `isStreamable()` | Có hỗ trợ stream các **generator** mới qua giao diện chuyên biệt không. |
| `isDeprecated()` | Thuật toán đã bị đánh dấu không nên tiếp tục dùng hay chưa. |
| `isStatistical()`, `isStochastic()`, `isHardware()` | Các thuộc tính phân loại nguồn hoặc cách tạo số. |

**Metadata không phải thang điểm chất lượng toàn diện.** Một `period` dài hoặc `stateBits()` lớn không chứng minh an toàn mật mã, phù hợp mọi mô phỏng hay bảo đảm dãy độc lập tuyệt đối giữa các seed.

### Lọc các factory thay vì đoán thuật toán

Ví dụ chọn một factory không deprecated, hỗ trợ split và có ít nhất 128 bit trạng thái:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> chosen = RandomGeneratorFactory.all()
        .filter(f -> !f.isDeprecated())
        .filter(RandomGeneratorFactory::isSplittable)
        .filter(f -> f.stateBits() >= 128)
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "Không tìm thấy thuật toán phù hợp"));

System.out.println(chosen.name());
RandomGenerator generator = chosen.create();
```

Đây là **đoạn đặt trong thân phương thức**, không phải chương trình độc lập. `all()` đã loại các thuật toán deprecated theo đặc tả Java 17, nên điều kiện `!f.isDeprecated()` ở đây chỉ thể hiện rõ yêu cầu. Không cam kết thuật toán được chọn là gì: danh sách thuật toán khả dụng có thể khác giữa JDK/provider, và thứ tự stream không nên dùng để xác lập một lựa chọn có tính lâu dài.

Nếu **tái lập kết quả** quan trọng, hãy lưu **tên thuật toán + seed + phiên bản/thông số cần thiết + lịch trình gọi API**. Không nên lọc rồi gọi `findFirst()` tại mỗi lần chạy và mặc định lựa chọn luôn giống nhau.

### Factory mặc định

`RandomGeneratorFactory.getDefault()` trả factory của thuật toán thỏa tối thiểu **`stateBits() >= 64`**, nhưng không cam kết tên thuật toán giữ nguyên qua các phiên bản. `RandomGenerator.getDefault()` có chủ đích tương tự ở mức instance. Đừng hardcode stdout các giá trị từ bộ sinh mặc định.

## 6. Các nhóm thuật toán và cách chọn trong thực tế

Java 17 mô tả các nhóm chính:

- **Legacy**: các bộ sinh lâu đời như `Random`, `ThreadLocalRandom`, `SplittableRandom` và `SecureRandom` trong hệ sinh thái Java. Một phần vẫn thích hợp do yêu cầu tương thích hoặc trường hợp chuyên biệt.
- **LXM**: kết hợp ý tưởng *linear congruential generator* và *xor-based generator*, với biến thể như `L64X128MixRandom`, `L64X256MixRandom`. Phù hợp nhiều workload mô phỏng và hỗ trợ splitting ở các biến thể tương ứng.
- **Xoroshiro/Xoshiro**: gồm các thuật toán như `Xoroshiro128PlusPlus` và `Xoshiro256PlusPlus`, cung cấp đặc tính hiệu suất và hỗ trợ jumping trong các implementation Java 17 tương ứng.

Chọn theo vấn đề:

| Nhu cầu | Hướng lựa chọn |
| --- | --- |
| Code thông thường, không ràng buộc thuật toán | `RandomGenerator.getDefault()` hoặc factory mặc định. |
| Phép mô phỏng cần tái lập dãy | Tên thuật toán cố định + seed cố định + trật tự gọi được kiểm soát. |
| Nhiều tác vụ song song cần các bộ sinh riêng | Thuật toán hỗ trợ `SplittableGenerator` hoặc `JumpableGenerator`; thiết kế phân bổ generator theo worker/task. |
| Cần tương thích chuỗi số cũ của `java.util.Random` | Giữ `Random`/thuật toán tương thích, thử lại các trường hợp quan trọng. |
| Token, mã xác thực, khóa, nonce nhạy cảm bảo mật | `SecureRandom`; không chọn LXM/Xoshiro chỉ vì tốc độ hoặc chu kỳ lớn. |

Trong phần lớn bài tập số học, nên bắt đầu với interface `RandomGenerator`, sau đó mới bổ sung yêu cầu về seed, thuật toán và splitting nếu bài toán thực sự cần. Một thuật toán phức tạp không tự động làm phần mềm “random hơn” theo mọi ý nghĩa.

## 7. Chương trình Java 17+ hoàn chỉnh và đầu ra có thể kiểm tra

Lưu chương trình sau vào **`RandomGeneratorDemo.java`**:

```java
import java.util.Arrays;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(2026L);
        RandomGenerator second = factory.create(2026L);

        boolean repeatable = true;
        for (int i = 0; i < 20; i++) {
            repeatable &= first.nextInt() == second.nextInt();
        }

        RandomGenerator rng = factory.create(42L);
        int die = rng.nextInt(1, 7);
        long sampleLong = rng.nextLong(100L, 200L);
        double fraction = rng.nextDouble();

        int[] fiveDice = rng.ints(5, 1, 7).toArray();
        boolean validDice = Arrays.stream(fiveDice)
                .allMatch(n -> n >= 1 && n < 7);

        RandomGeneratorFactory<RandomGenerator> defaultFactory =
                RandomGeneratorFactory.getDefault();

        System.out.println("algorithm = " + factory.name());
        System.out.println("same seed and calls = " + repeatable);
        System.out.println("splittable = " + factory.isSplittable());
        System.out.println("die in [1, 7) = " + (die >= 1 && die < 7));
        System.out.println("long in [100, 200) = "
                + (sampleLong >= 100 && sampleLong < 200));
        System.out.println("double in [0, 1) = "
                + (fraction >= 0.0 && fraction < 1.0));
        System.out.println("stream size = " + fiveDice.length);
        System.out.println("stream bounds valid = " + validDice);
        System.out.println("default state bits >= 64 = "
                + (defaultFactory.stateBits() >= 64));
    }
}
```

Biên dịch và chạy trong thư mục chứa file, với **JDK 17 trở lên**:

```bash
javac RandomGeneratorDemo.java
java RandomGeneratorDemo
```

Đầu ra kỳ vọng với API và thuật toán được chỉ định:

```text
algorithm = L64X128MixRandom
same seed and calls = true
splittable = true
die in [1, 7) = true
long in [100, 200) = true
double in [0, 1) = true
stream size = 5
stream bounds valid = true
default state bits >= 64 = true
```

Ví dụ cố tình in **tên thuật toán và các điều kiện đúng/sai** thay cho giá trị cụ thể của từng lần rút. Giá trị random vẫn khác nhau giữa các lần gọi hoặc seed, nhưng mọi lần rút trong đoạn mã đều phải thỏa miền đã khai báo. Hai instance có cùng thuật toán và seed `2026L`, lại được gọi cùng số lần theo cùng thứ tự, cho dãy khớp nhau.

Nếu thay bằng `getDefault()` hoặc để factory chọn thuật toán động qua `all()`, không được dựa vào danh tính thuật toán hay chuỗi số mặc định như một hợp đồng cố định của ứng dụng.

## 8. Splittable và Jumpable: tạo luồng số cho tính toán song song

Khi nhiều tác vụ cùng dùng bộ sinh giả ngẫu nhiên, **một `RandomGenerator` dùng chung có thể không thread-safe**. Giao diện cơ sở không bảo đảm đồng bộ. Sử dụng một generator riêng cho mỗi worker hoặc một chiến lược phân bổ phù hợp là cách tiếp cận thường gặp.

Java 17 giới thiệu các giao diện lồng trong `RandomGenerator` để mô tả khả năng đặc biệt:

- `RandomGenerator.SplittableGenerator`: tạo một generator mới thông qua `split()`, phục vụ việc phân nhánh công việc.
- `RandomGenerator.JumpableGenerator`: có thao tác `jump()` để tiến tới một vị trí cách xa trong dãy trạng thái.
- `RandomGenerator.LeapableGenerator` và `ArbitrarilyJumpableGenerator`: các biến thể bổ sung về khoảng nhảy.
- `RandomGenerator.StreamableGenerator`: cung cấp cách tạo stream gồm nhiều generator.

Các khả năng này là **tùy thuật toán**, không có trên mọi `RandomGenerator`. Chỉ ép kiểu khi đã xác thực loại hoặc biết chắc thuật toán.

### Ví dụ split() với thuật toán LXM

Đây là chương trình Java 17+ độc lập, lưu thành `SplitDemo.java`:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SplitDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator.SplittableGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator.SplittableGenerator parent =
                factory.create(2026L);
        RandomGenerator.SplittableGenerator child = parent.split();

        int parentValue = parent.nextInt(1, 7);
        int childValue = child.nextInt(1, 7);

        System.out.println("parent valid = "
                + (parentValue >= 1 && parentValue < 7));
        System.out.println("child valid = "
                + (childValue >= 1 && childValue < 7));
        System.out.println("different objects = " + (parent != child));
    }
}
```

Biên dịch và chạy:

```bash
javac SplitDemo.java
java SplitDemo
```

Kết quả:

```text
parent valid = true
child valid = true
different objects = true
```

`split()` trả về một generator riêng có thể được chuyển cho tác vụ khác. **Không hiểu `split()` là chứng minh toán học tuyệt đối rằng mọi dãy sinh ra đều độc lập trong mọi tình huống.** Ý tưởng của thuật toán là hạn chế chồng lặp và hỗ trợ chia công việc. Khi cần tính tái lập của mô phỏng chạy song song, phải kiểm soát cả **thứ tự tách generator, ánh xạ generator vào task và lịch gọi**, vì thay đổi lịch xử lý có thể đổi phần dãy được từng task sử dụng.

Tương tự, nếu cần `jump()`, hãy chọn thuật toán có `factory.isJumpable() == true` rồi sử dụng giao diện `RandomGenerator.JumpableGenerator`. Gọi `jump()` không phải “xin số ngẫu nhiên mạnh hơn”; nó thay đổi vị trí generator trong chu trình theo quy tắc thuật toán, hỗ trợ phân hoạch công việc.

### ThreadLocalRandom liên quan thế nào?

`ThreadLocalRandom.current()` vẫn hữu ích trong code nhiều luồng khi mỗi luồng cần truy cập bộ sinh của chính luồng đó. Nó là API lâu đời và triển khai `RandomGenerator`. Với kiến trúc chia tác vụ linh hoạt hoặc fork/join, các generator hỗ trợ `split()` có thể thích hợp hơn. Việc chia sẻ một instance bất kỳ không được mặc định an toàn chỉ vì biến có kiểu `RandomGenerator`.

## 9. Seed, tính tái lập và giới hạn cần hiểu

### 9.1. Tại sao seed quan trọng?

Seed giúp khởi tạo trạng thái ban đầu của generator. Cùng thuật toán và seed phù hợp, kết hợp cùng lịch gọi hàm, thường cho cùng dãy số, rất hữu ích khi tái hiện lỗi. Ví dụ:

```java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator a = factory.create(1234L);
RandomGenerator b = factory.create(1234L);

// Dãy nextLong() của a và b sẽ khớp nếu thứ tự lời gọi tương ứng như nhau.
```

Nếu một bên gọi thêm `nextInt()` trước, trạng thái có thể tiến khác; các giá trị tiếp theo không còn khớp cặp theo kỳ vọng. Tương tự, gọi stream và gọi đơn lẻ với cùng số lượng mẫu không luôn được đặc tả phải cho **cùng dãy giá trị theo từng vị trí**; Java chỉ bảo đảm các giá trị tuân theo cùng kiểu chọn phân phối/phạm vi. Không dùng sự tương đương giữa phương thức stream và vòng lặp đơn lẻ làm hợp đồng tái lập nếu chưa được thuật toán/implementation bảo đảm.

### 9.2. Seed cố định có an toàn không?

**Không.** Seed cố định làm dãy dễ tái hiện và có thể dễ đoán. Ngay cả seed từ đồng hồ hiện tại cũng không bảo đảm đủ entropy cho bảo mật. Dùng seed cố định cho kiểm thử/mô phỏng có chủ đích; không dùng để sinh session token, mật khẩu, mã khôi phục hoặc khóa.

`RandomGeneratorFactory.create()` không truyền seed thường phù hợp khi không yêu cầu lặp lại cùng dãy, nhưng **không biến thuật toán thường thành CSPRNG**. Bảo mật dựa vào thuật toán và nguồn entropy được thiết kế cho mục đích đó; dùng `SecureRandom`.

### 9.3. Ghi chép gì để tái hiện kết quả?

Nếu một phép mô phỏng phải chạy lại để so sánh, nên ghi:

1. Tên thuật toán, ví dụ `L64X128MixRandom`.
2. Giá trị và kiểu seed đã dùng.
3. Phiên bản JDK/provider khi khả năng tái hiện chéo môi trường là yêu cầu.
4. Trình tự gọi phương thức, số lượng giá trị, các tham số bound/origin.
5. Với chương trình song song, sơ đồ `split()`, số worker và cách phân phối task.

**Seed không phải bản snapshot đầy đủ của trạng thái sau nhiều lần rút**. Nó mô tả cách khởi tạo; muốn quay lại giữa dãy phải tái thực hiện đúng các bước hoặc có cơ chế lưu trạng thái được cung cấp/kiểm chứng. Không tự giả định mọi implementation cho phép serialization, hoặc có API khôi phục trạng thái.

## 10. Những lỗi thường gặp khi chuyển từ Random sang API Java 17

1. **Nhập nhầm package.** `RandomGenerator` và `RandomGeneratorFactory` nằm trong `java.util.random`, khác `java.util.Random`.
2. **Cố gọi `new RandomGenerator()`.** Đây là interface; tạo bằng `getDefault()`, `of(name)` hoặc factory.
3. **Nhầm chặn trên của range.** `nextInt(1, 7)` sinh 1–6, không sinh 7; `nextInt(6)` sinh 0–5.
4. **Dùng `getDefault()` rồi kỳ vọng cùng thuật toán ở mọi JDK.** Thuật toán mặc định có thể thay đổi. Cố định `name` khi cần.
5. **Dùng cùng seed nhưng thay đổi chuỗi gọi.** Khả năng tái hiện phụ thuộc thuật toán và thứ tự tiêu thụ dãy.
6. **Cho rằng mọi thuật toán hỗ trợ seed `long` giống nhau.** Factory có cơ chế fallback nếu thuật toán không hỗ trợ kiểu seed yêu cầu. Chọn thuật toán cụ thể đã kiểm chứng.
7. **Gọi `factory.isSplittable()` và hiểu rằng interface cơ sở có `split()`.** `split()` thuộc `RandomGenerator.SplittableGenerator`; cần kiểu phù hợp.
8. **Chia sẻ generator giữa nhiều thread mà không biết thread safety.** `RandomGenerator` không cam kết thread-safe; tổ chức một generator riêng cho worker hoặc dùng cơ chế chuyên dụng.
9. **Dùng PRNG thông thường cho bảo mật.** Chọn `SecureRandom` cho token/khóa/bí mật nhạy cảm, bất kể chu kỳ PRNG dài ra sao.
10. **Tạo stream vô hạn rồi thu thập toàn bộ.** Với `ints()`/`doubles()` không kích thước, dùng `limit(n)` hoặc quá trình tiêu thụ có điểm dừng.
11. **Cho rằng `stateBits` = entropy của seed hoặc “mức an toàn”.** Đây là kích thước trạng thái, không phải thước đo chống dự đoán mật mã.
12. **Kiểm thử bằng giá trị ngẫu nhiên hardcode.** Với code không dùng named algorithm + seed và thứ tự lời gọi cố định, hãy kiểm tra bất biến như range, độ dài stream, uniqueness theo yêu cầu thống kê phù hợp; tránh test chỉ vì “hôm nay số này khác số kia”.

## 11. Ứng dụng: mô phỏng xúc xắc có thể tái lập

Trong bài kiểm thử hoặc mô phỏng, có thể truyền `RandomGenerator` vào hàm thay vì khởi tạo trực tiếp, giúp test kiểm soát đầu vào ngẫu nhiên.

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class DiceSimulation {
    static int roll(RandomGenerator generator) {
        return generator.nextInt(1, 7);
    }

    static int totalOfThreeRolls(RandomGenerator generator) {
        return roll(generator) + roll(generator) + roll(generator);
    }

    public static void main(String[] args) {
        var factory = RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(17L);
        RandomGenerator again = factory.create(17L);

        int result1 = totalOfThreeRolls(first);
        int result2 = totalOfThreeRolls(again);

        System.out.println("same total = " + (result1 == result2));
        System.out.println("total in [3, 18] = "
                + (result1 >= 3 && result1 <= 18));
    }
}
```

Lưu `DiceSimulation.java` rồi chạy:

```bash
javac DiceSimulation.java
java DiceSimulation
```

Đầu ra:

```text
same total = true
total in [3, 18] = true
```

Hàm `roll()` chỉ phụ thuộc giao diện `RandomGenerator`, nên dễ đổi thuật toán hoặc truyền generator đã được cấu hình từ ngoài. Trong ứng dụng lớn hơn, đây cũng là cách tách **logic nghiệp vụ mô phỏng** khỏi **chính sách chọn thuật toán và quản lý seed**.

## 12. Câu hỏi tự kiểm tra

**Câu 1. `RandomGenerator` và `RandomGeneratorFactory` khác nhau ở đâu?**

`RandomGenerator` cung cấp phương thức sinh giá trị; `RandomGeneratorFactory` lựa chọn thuật toán, truy vấn metadata và tạo instance.

**Câu 2. Tại sao `rng.nextInt(1, 7)` phù hợp để mô phỏng xúc xắc?**

Vì giá trị thuộc miền `[1, 7)`, tức 1 đến 6, mỗi giá trị khả dĩ thuộc tập sáu mặt.

**Câu 3. Nếu dùng `RandomGenerator.getDefault()` với seed ngầm, có thể kiểm thử bằng một dãy cố định bất biến không?**

Không nên. Thuật toán mặc định có thể thay đổi và trạng thái khởi tạo cũng không được cố định qua các lần chạy.

**Câu 4. Muốn tái hiện dãy trong test cần gì?**

Ít nhất phải kiểm soát thuật toán hỗ trợ seed, giá trị seed và **đúng thứ tự gọi các phương thức**; nếu chạy song song, cần thêm chính sách chia và phân phối dãy.

**Câu 5. `factory.isSplittable()` dùng để làm gì?**

Để xác định factory tạo thuật toán hỗ trợ khả năng tách thành các generator phục vụ phân nhánh công việc; lời gọi `split()` thuộc `RandomGenerator.SplittableGenerator`.

**Câu 6. Một thuật toán có `period()` rất lớn có dùng sinh khóa bảo mật được không?**

Không thể kết luận như vậy. Period lớn và stateBits nhiều không bảo đảm khả năng chống dự đoán; dùng `SecureRandom` theo tiêu chuẩn bảo mật.

**Câu 7. `factory.create(123L)` có đảm bảo seed được áp dụng cho mọi thuật toán không?**

Không. Theo hợp đồng factory, khi thuật toán không hỗ trợ kiểu `long`, lời gọi có thể fallback sang `create()` không tham số.

**Câu 8. `RandomGeneratorFactory.all()` trả về gì?**

Một `Stream<RandomGeneratorFactory<RandomGenerator>>` của các thuật toán khả dụng (không gồm thuật toán bị đánh dấu deprecated trong Java 17), dùng để lọc hoặc xem metadata; tập hợp thực tế có thể khác theo JDK/provider.

**Câu 9. Vì sao không nên dùng chung một generator bất kỳ giữa nhiều tác vụ?**

Vì `RandomGenerator` không cam kết thread-safe; concurrent use có thể dẫn tới race hoặc lịch tiêu thụ dãy không tái hiện được. Tùy workload, dùng generator riêng, `split()`/`jump()` hoặc `ThreadLocalRandom`.

**Câu 10. Khi nào nên truyền `RandomGenerator` làm tham số hàm?**

Khi muốn tách logic sử dụng số ngẫu nhiên khỏi logic chọn thuật toán/seed, giúp dễ thay implementation và tái hiện test.

## 13. Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): giao diện, giới hạn phạm vi, phương thức sinh số và stream.
- [Oracle Java SE 17 — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): factory, `all()`, `of()`, `create()`, thông tin thuật toán và giới hạn seed.
- [Oracle Java SE 17 — java.util.random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): nhóm thuật toán và gợi ý lựa chọn.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): mục tiêu thay đổi API trong Java 17.

**Ghi nhớ:** Từ Java 17, **`RandomGenerator` là hợp đồng sinh số**, còn **`RandomGeneratorFactory` là cơ chế chọn và tạo thuật toán**. Hãy chọn rõ seed/thuật toán khi cần tái lập, chọn `SplittableGenerator` hoặc `JumpableGenerator` cho workload có yêu cầu tương ứng, chú ý miền `[origin, bound)` và **luôn dùng `SecureRandom` cho dữ liệu nhạy cảm bảo mật**.
