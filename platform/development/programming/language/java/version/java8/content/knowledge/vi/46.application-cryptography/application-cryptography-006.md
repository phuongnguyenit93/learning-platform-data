# Phân biệt ngẫu nhiên tính toán với ngẫu nhiên mật mã trong Java

**Một dãy số trông có vẻ ngẫu nhiên chưa chắc dùng được cho bảo mật.** Java có nhiều bộ sinh số phục vụ những mục đích khác nhau. `Random`, `ThreadLocalRandom` và `SplittableRandom` phù hợp cho mô phỏng, lấy mẫu, trò chơi, thuật toán và kiểm thử. **`SecureRandom`** được thiết kế cho các giá trị cần khó dự đoán trong bảo mật như token phiên, mã khôi phục, challenge, salt, nonce và vật liệu tạo khóa.

Khác biệt cốt lõi không nằm ở việc đầu ra có “trông rối” hay không. Bộ sinh giả ngẫu nhiên cho tính toán (*PRNG*) ưu tiên chất lượng thống kê, tốc độ và đôi khi khả năng tái lập. Bộ sinh ngẫu nhiên mật mã (*CSPRNG*) phải tạo đầu ra khó dự đoán trước đối với attacker theo mô hình bảo mật, kể cả khi attacker biết thuật toán và quan sát một phần đầu ra.

Một điểm quan trọng: **ngẫu nhiên mật mã không có nghĩa mỗi bit đầu ra đều phải đến trực tiếp từ một phép đo vật lý mới**. Nhiều implementation `SecureRandom` dùng DRBG (*Deterministic Random Bit Generator*) — thuật toán xác định để mở rộng seed có đủ entropy thành chuỗi bit giả ngẫu nhiên có tính chất mật mã. Vì vậy, “pseudo” không đồng nghĩa “không an toàn”; chất lượng seed, thuật toán, trạng thái nội bộ và khả năng chống dự đoán mới quyết định.

Bài thuộc mục **Mật mã ứng dụng**, với đề tài **Phân biệt ngẫu nhiên tính toán với ngẫu nhiên mật mã**. Nội dung chỉ sử dụng API và kiến thức còn áp dụng hiện nay: các lớp từ Java 8 và giao diện `java.util.random` được bổ sung từ Java 17. Ví dụ hoàn chỉnh ở cuối bài đã được biên dịch và chạy trên OpenJDK 24.

## 1. Hai mục tiêu khác nhau

| Tiêu chí | Ngẫu nhiên giả cho tính toán | Ngẫu nhiên mật mã |
| --- | --- | --- |
| Mục tiêu | Phân bố thống kê phù hợp, hiệu năng, khả năng lặp lại | Đầu ra khó dự đoán thực tế |
| Seed cố định | Thường hữu ích để tái lập thí nghiệm | Không dùng seed dễ đoán cho dữ liệu bảo mật |
| Quan sát output trước | Có thể chấp nhận trong mô phỏng | Không được giúp attacker suy ra output tiếp theo |
| Hiệu năng | Thường ưu tiên throughput và chi phí thấp | Có thể tốn chi phí hơn để đạt yêu cầu bảo mật |
| Ứng dụng | Monte Carlo, game, test, simulation, sampling | Token, key material, challenge, salt, nonce |
| Java API thường dùng | `Random`, `ThreadLocalRandom`, `SplittableRandom` | `SecureRandom` |

### 1.1. Một ví dụ trực quan

~~~text
Mô phỏng:
Random(seed = 12345)
-> 251, 80, 241, 828, ...
Chạy lại cùng seed và cùng chuỗi lời gọi:
-> 251, 80, 241, 828, ...

Mã xác nhận:
SecureRandom
-> 583104 (ví dụ)
Lần tiếp theo -> một giá trị mới được sinh từ CSPRNG
~~~

Dãy mô phỏng lặp lại là **một lợi ích**, không phải lỗi. Nhưng nếu dùng cùng kiểu seed dễ đoán để tạo mã xác nhận, attacker có thể thử tái tạo dãy. Ngược lại, nếu dùng `SecureRandom` cho thí nghiệm cần tái lập từng lần, bạn phải thiết kế cơ chế ghi nhận và tái tạo riêng; đừng kỳ vọng nó hoạt động như `Random(seed)`.

### 1.2. Pseudo không đồng nghĩa vô dụng

Một PRNG tốt có thể tạo hàng tỷ giá trị có phân bố và tính độc lập xấp xỉ phù hợp cho mô phỏng. Nó có thể vượt nhiều bộ kiểm tra thống kê. Điều đó **không chứng minh** nó chống được người quan sát có khả năng phân tích trạng thái hoặc đoán seed.

Ngược lại, `SecureRandom` cũng có thể dùng một thuật toán giả ngẫu nhiên bên trong. Nó vẫn là ngẫu nhiên mật mã nếu implementation đáp ứng hợp đồng bảo mật và được khởi tạo bằng entropy phù hợp.

## 2. PRNG hoạt động như thế nào?

PRNG (*Pseudorandom Number Generator*) duy trì một **trạng thái nội bộ**. Từ seed ban đầu, thuật toán cập nhật trạng thái và tạo đầu ra:

~~~text
seed ban đầu
    |
    v
trạng thái s0
    |
    v
thuật toán PRNG ----> output 1
    |
    v
trạng thái s1
    |
    v
thuật toán PRNG ----> output 2
    |
    v
trạng thái s2
    |
    v
output 3 ...
~~~

Ở mức khái niệm:

\[
s_{i+1}=f(s_i), \qquad x_i=g(s_i)
\]

Trong đó `f` cập nhật state và `g` tạo output. Nếu state có hữu hạn bit, dãy cuối cùng có chu kỳ. Seed quyết định trạng thái bắt đầu và vì thế ảnh hưởng đến dãy số.

### 2.1. Seed cố định tạo ra khả năng tái lập

~~~java
Random first = new Random(12345L);
Random second = new Random(12345L);

int a = first.nextInt();
int b = second.nextInt();
// a == b
~~~

Đây là mã minh họa. Hai object có cùng seed và cùng chuỗi method calls sẽ tạo cùng sequence theo hợp đồng của `Random`.

Tính chất này hữu ích cho:

- Tái lập bug trong test.
- Lặp lại thí nghiệm mô phỏng.
- So sánh hai thuật toán trên cùng chuỗi input giả lập.
- Chạy simulation theo seed đã lưu.
- Tạo dữ liệu kiểm thử ổn định cho regression.

**Không dùng seed cố định hoặc seed dễ đoán để tạo secret.** Nếu attacker biết seed hoặc thu hẹp được miền seed, họ có thể tái tạo output của PRNG thông thường.

### 2.2. Random dùng thuật toán xác định

Javadoc của `java.util.Random` mô tả thuật toán LCG (*linear congruential generator*), seed nội bộ 48 bit và chu kỳ \(2^{48}\). Đây là lý do `new Random(seed)` có tính tái lập mạnh: cùng seed và cùng chuỗi lời gọi tạo cùng dãy trên các implementation Java tuân thủ hợp đồng.

Tính tái lập đó **không phải** thuộc tính bảo mật. Nếu attacker đoán hoặc suy ra seed/state, họ có thể tái tạo các giá trị tiếp theo.

### 2.3. Chất lượng thống kê không chứng minh tính khó đoán

Một PRNG có thể có histogram gần đều, tương quan thấp trong nhiều phép đo và chu kỳ dài, nhưng nếu seed nhỏ hoặc state dễ khôi phục thì dãy vẫn có thể dự đoán. **Thống kê tốt và chống dự đoán là hai tiêu chí khác nhau.**

## 3. Entropy, seed và đầu ra

**Entropy** mô tả mức độ không chắc chắn của một giá trị. Trong bảo mật, *min-entropy* là cách đo bảo thủ dựa trên xác suất đoán giá trị có khả năng cao nhất.

Ví dụ:

- Seed là thời gian hiện tại theo mili giây có thể có nhiều chữ số, nhưng attacker thường thu hẹp được khoảng thời gian sinh.
- Seed là PID, counter, user ID hoặc hashCode thường có miền nhỏ và dễ thử.
- Một chuỗi 32 byte đầu ra không tự động chứng minh nó có 256 bit entropy nếu nguồn ban đầu yếu.
- 32 byte được tạo từ `SecureRandom` đúng cách là 32 byte đầu ra của CSPRNG; độ an toàn phụ thuộc implementation và entropy, không chỉ chiều dài mảng.

### 3.1. Nguồn entropy và DRBG

~~~text
Nguồn entropy của hệ thống
        |
        v
seed đủ khó đoán
        |
        v
DRBG / CSPRNG
        |
        v
chuỗi byte giả ngẫu nhiên có tính chất mật mã
        |
        +----> token
        +----> nonce
        +----> salt
        +----> vật liệu khóa
~~~

NIST chia các khía cạnh thành các tài liệu bổ trợ:

- **SP 800-90A:** cơ chế DRBG dựa trên thuật toán mật mã.
- **SP 800-90B:** nguồn entropy và đánh giá chất lượng entropy.
- **SP 800-90C:** cách kết hợp nguồn entropy và DRBG thành random bit generator.

Các chuẩn này cho thấy hệ thống an toàn cần xem xét cả **nguồn seed** lẫn **thuật toán mở rộng bit**. Không tự lấy clock, mouse movement, network timing hoặc counter rồi coi đó là entropy đủ mạnh; hệ điều hành và provider đã có cơ chế thu thập entropy riêng.

### 3.2. Vì sao CSPRNG có thể vẫn deterministic?

Sau khi được khởi tạo từ seed đủ entropy, DRBG tính output bằng thuật toán xác định. Điều đó cho phép sinh nhiều bit mà không cần một phép đo vật lý mới cho từng byte. Nếu trạng thái nội bộ bị lộ, khả năng bảo vệ output trước/sau phụ thuộc thiết kế và cơ chế reseed/backtracking resistance của DRBG.

Vì vậy:
- PRNG thông thường: deterministic sequence phù hợp cho mô phỏng, không cam kết chống dự đoán.
- CSPRNG/DRBG: cũng có thể deterministic bên trong, nhưng được thiết kế và seed để output khó dự đoán theo mô hình mật mã.

**Không phân loại chỉ dựa vào việc thuật toán có deterministic hay không.**

## 4. SecureRandom: API chuẩn cho ngẫu nhiên mật mã

`java.security.SecureRandom` là lớp Java cung cấp bộ sinh số ngẫu nhiên có tính mạnh về mật mã. Nó kế thừa `java.util.Random`, vì vậy có các phương thức như `nextInt`, `nextLong`, `nextBoolean` và `nextBytes`.

~~~java
SecureRandom secureRandom = new SecureRandom();

byte[] randomBytes = new byte[32];
secureRandom.nextBytes(randomBytes);

int challenge = secureRandom.nextInt(1_000_000);
~~~

Đây là mã minh họa, cần import `java.security.SecureRandom`. `nextBytes` lấp đầy mảng bằng byte từ SecureRandom; `nextInt(bound)` trả số trong khoảng từ 0 (bao gồm) đến bound (không bao gồm).

### 4.1. SecureRandom không nhất thiết là true random generator

Oracle mô tả nhiều implementation `SecureRandom` là PRNG/DRBG dùng thuật toán xác định từ seed ngẫu nhiên; một số implementation có thể lấy true random từ nguồn vật lý hoặc kết hợp nhiều kỹ thuật.

Điểm quan trọng là implementation phải cung cấp đầu ra **cryptographically strong** theo hợp đồng. Không yêu cầu mỗi lần gọi `nextBytes` phải đọc trực tiếp một thiết bị vật lý.

### 4.2. Tự seed theo implementation

Với `new SecureRandom()`, Java chọn implementation từ các security providers đã đăng ký. Một PRNG `SecureRandom` có thể tự seed từ entropy source đặc thù của implementation khi lần đầu gọi `nextBytes`. Đây là cách dùng thông thường:

~~~java
SecureRandom random = new SecureRandom();
byte[] keyMaterial = new byte[32];
random.nextBytes(keyMaterial);
~~~

**Không tự gọi `setSeed(System.currentTimeMillis())` để “làm SecureRandom an toàn hơn”.** Javadoc cảnh báo nếu `setSeed` được gọi trước lần `nextBytes` hoặc `reseed` đầu tiên, PRNG SecureRandom sẽ không tự seed theo cách thông thường; caller phải tự bảo đảm seed có đủ entropy. Clock, PID và counter không phải nguồn seed an toàn để tự ghép.

### 4.3. Không nhầm setSeed với seed cố định của Random

Đối với `Random`, `setSeed` là cách reset trạng thái seed theo hợp đồng của class, hữu ích cho simulation. Với `SecureRandom`, `setSeed` là thao tác **bổ sung seed** cho trạng thái và có quy tắc riêng; nó không phải cơ chế tạo sequence tái lập như `new Random(seed)`.

Trong ứng dụng thông thường:
- Không tự seed `SecureRandom` bằng giá trị có thể đoán.
- Dùng `new SecureRandom()` và để implementation tự khởi tạo.
- Chỉ cấu hình seed/DRBG parameters khi có thiết kế mật mã, provider và entropy rõ ràng.
- Không log seed hoặc state nội bộ.

### 4.4. SecureRandom thread-safe

Javadoc quy định object `SecureRandom` an toàn khi dùng từ nhiều thread. Provider có thể tự quảng bá khả năng thread-safe; nếu không, lớp SecureRandom sẽ đồng bộ hóa các lời gọi cần thiết tới SPI.

Có thể giữ một instance dùng chung:

~~~java
private static final SecureRandom SECURE_RANDOM =
        new SecureRandom();
~~~

Đây là mẫu minh họa. Không tạo instance mới cho mỗi byte hoặc mỗi request nếu không có lý do cụ thể; tái sử dụng thường giảm chi phí khởi tạo. Với workload lớn, vẫn cần đo performance và hiểu provider đang dùng.

### 4.5. getInstanceStrong()

`SecureRandom.getInstanceStrong()` chọn implementation từ danh sách `securerandom.strongAlgorithms` trong security properties. Nó hữu ích khi ứng dụng có yêu cầu cụ thể về implementation strong, ví dụ sinh secret có giá trị cao hoặc tồn tại lâu dài.

~~~java
SecureRandom strong = SecureRandom.getInstanceStrong();
byte[] material = new byte[32];
strong.nextBytes(material);
~~~

Đây là đoạn minh họa; method có thể ném `NoSuchAlgorithmException` nếu không tìm thấy thuật toán trong cấu hình. Không có quy tắc “mọi ứng dụng đều phải dùng getInstanceStrong thay cho new SecureRandom”. Việc thu thập entropy ở một số implementation có thể block; cần kiểm tra provider, cấu hình và yêu cầu latency.

### 4.6. Chọn tên thuật toán/provider

Chỉ chỉ định `SecureRandom.getInstance("DRBG")` hoặc tên provider khi bạn có yêu cầu tương thích/compliance rõ và đã kiểm tra implementation trên runtime mục tiêu. Tên thuật toán, provider và tham số có thể khác theo JDK/distribution. Đừng hard-code một tên legacy hoặc provider-specific chỉ vì tìm thấy trong ví dụ cũ.

## 5. So sánh các bộ sinh số trong Java

| API | Có từ | Mục đích | Seed/reproducibility | Thread behavior | An toàn mật mã? |
| --- | --- | --- | --- | --- | --- |
| `java.util.Random` | Java 1.0 | PRNG đa dụng, mô phỏng/test | Seed cố định tái tạo sequence theo hợp đồng | Thread-safe nhưng có thể contention khi chia sẻ | **Không** |
| `ThreadLocalRandom` | Java 7 | PRNG cho tác vụ đa luồng | Seed nội bộ, không cho caller tự setSeed | Mỗi thread có generator riêng | **Không** |
| `SplittableRandom` | Java 8 | PRNG cho tính toán song song | Có constructor seed; dùng split để tách state | Không thread-safe; thiết kế để split | **Không** |
| `RandomGenerator` | Java 17 | Giao diện chung cho nhiều generator | Tùy implementation/algorithm | Không mặc định thread-safe | **Không mặc định** |
| `RandomGeneratorFactory` | Java 17 | Chọn implementation theo tên | Có thể tạo bằng seed | Tùy generator được chọn | **Không mặc định** |
| `SecureRandom` | Java 1.1 | CSPRNG cho ứng dụng bảo mật | Không dùng như seeded simulation PRNG | Thread-safe theo hợp đồng | **Có** |

**Điểm cần nhớ:** `SecureRandom` cũng triển khai `RandomGenerator` trong Java 17+. Vì thế việc một object có kiểu `RandomGenerator` không cho biết nó có an toàn mật mã hay không. Cần chọn implementation cụ thể theo yêu cầu.

## 6. Random: khi nào phù hợp?

`Random` phù hợp khi bạn cần dãy giả ngẫu nhiên có thể lặp lại:

~~~java
Random random = new Random(2026L);

int die = random.nextInt(6) + 1;
double probabilitySample = random.nextDouble();
boolean coin = random.nextBoolean();
~~~

- `nextInt(6)` trả số từ 0 đến 5; cộng 1 để ra xúc xắc từ 1 đến 6.
- `nextDouble()` trả giá trị trong [0.0, 1.0).
- `nextBoolean()` tạo giá trị boolean giả ngẫu nhiên.

**Không dùng Random cho token, session ID, password reset link, OTP, API key, key material hoặc nonce cần yêu cầu mật mã.** Cùng seed tạo cùng dãy, và thuật toán được thiết kế cho tái lập chứ không phải chống attacker.

### 6.1. Thread-safe không đồng nghĩa nhanh khi chia sẻ

`Random` là thread-safe, nhưng nhiều thread cùng cập nhật một instance có thể tranh chấp state và giảm throughput. Với code đa luồng, `ThreadLocalRandom` hoặc generator có thể split thường phù hợp hơn cho mô phỏng.

### 6.2. Math.random()

`Math.random()` là tiện ích trả double giả ngẫu nhiên trong [0.0, 1.0). Nó phù hợp cho một số thao tác đơn giản không nhạy cảm, nhưng không phải API mật mã. Nếu mục đích là security, dùng `SecureRandom`.

## 7. ThreadLocalRandom: cho nhiều thread tính toán độc lập

~~~java
int index = ThreadLocalRandom.current().nextInt(0, items.size());
~~~

Đây là mã minh họa. `ThreadLocalRandom.current()` trả generator của thread hiện tại; khoảng [origin, bound) giúp tránh chia sẻ một instance `Random` toàn cục.

Dùng trong:
- Chọn mẫu trong tác vụ nền.
- Simulation chạy trên thread pool.
- Randomized backoff trong thuật toán không liên quan bảo mật.
- Game hoặc logic không nhạy cảm với dự đoán.

Không dùng trong:
- Token đăng nhập.
- Mã OTP/reset.
- Secret challenge.
- Nonce/IV yêu cầu chống dự đoán.
- Tạo khóa.

**Không được nhầm “seed nội bộ do runtime tạo” với “cryptographically secure seed”.** Javadoc xác nhận `ThreadLocalRandom` không an toàn mật mã.

## 8. SplittableRandom: tách generator cho xử lý song song

`SplittableRandom` được thiết kế để tạo chuỗi giả ngẫu nhiên cho tính toán độc lập và có phương thức `split()`:

~~~java
SplittableRandom root = new SplittableRandom(2026L);

SplittableRandom taskA = root.split();
SplittableRandom taskB = root.split();

int a = taskA.nextInt(1_000);
int b = taskB.nextInt(1_000);
~~~

Đây là mã minh họa. `split()` tạo generator mới với state riêng, phù hợp cho fork/join hoặc parallel computation. Không chia sẻ cùng một `SplittableRandom` object cho nhiều thread.

### 8.1. Vì sao split hữu ích?

Nếu nhiều task cùng dùng một generator mutable, chúng có thể tranh chấp hoặc làm kết quả phụ thuộc lịch thực thi. Tách generator giúp từng task có state riêng và giảm chia sẻ mutable state.

### 8.2. Split không tạo CSPRNG

`SplittableRandom` có chất lượng thống kê cho mục đích tính toán, nhưng Javadoc xác nhận nó **không cryptographically secure**. Một chuỗi split nhiều lần vẫn không phải nguồn token/secret.

## 9. RandomGenerator từ Java 17

Java 17 giới thiệu package `java.util.random` với interface `RandomGenerator`, cung cấp giao thức chung cho generator số và stream số.

~~~java
RandomGenerator generator =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(2026L);

int value = generator.nextInt(100);
long largeValue = generator.nextLong();
double probability = generator.nextDouble();
~~~

Đây là ví dụ Java 17+. `RandomGeneratorFactory` cho phép chọn một thuật toán có tên và tạo instance với seed. Nó giúp code không phụ thuộc trực tiếp vào một class cụ thể khi chỉ cần phương thức sinh số chung.

### 9.1. Interface chung không tự bảo đảm security

Các class triển khai `RandomGenerator` bao gồm `Random`, `SecureRandom`, `SplittableRandom` và `ThreadLocalRandom`. Chúng có đặc tính khác nhau. Không được nhận `RandomGenerator` từ một dependency rồi giả định nó là CSPRNG chỉ vì method tên `nextBytes` hoặc `nextInt`.

Nếu security-sensitive, hãy yêu cầu rõ `SecureRandom` hoặc một abstraction mà hợp đồng quy định nguồn ngẫu nhiên mật mã.

### 9.2. RandomGeneratorFactory

`RandomGeneratorFactory.of(name)` chọn generator theo tên thuật toán. `all()` cho phép xem các implementation có sẵn. Có thể dùng factory để pin một thuật toán cho simulation có yêu cầu reproducibility.

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator first = factory.create(1234L);
RandomGenerator second = factory.create(1234L);
~~~

Tên thuật toán phải có trên runtime; nếu không, `of` có thể ném `IllegalArgumentException`.

### 9.3. Không dựa vào getDefault() nếu cần sequence ổn định lâu dài

`RandomGenerator.getDefault()` trả implementation đáp ứng mức yêu cầu tối thiểu. Javadoc nói thuật toán mặc định có thể thay đổi theo thời gian khi thuật toán được cải thiện.

Nếu cần tái lập thí nghiệm qua nhiều lần chạy hoặc phiên bản JDK:
- Lưu seed.
- Chọn tên thuật toán rõ ràng.
- Lưu phiên bản runtime/implementation.
- Giữ nguyên chuỗi lời gọi và cách phân phối task.
- Kiểm thử lại khi nâng JDK hoặc thay thuật toán.

Đối với `Random`, Java có cam kết cụ thể về sequence cho cùng seed và cùng lời gọi; với generator khác, cần đọc hợp đồng của thuật toán đó thay vì tự suy rộng.

### 9.4. Splittable/Jumpable generator trong parallel streams

`RandomGenerator.SplittableGenerator` và `JumpableGenerator` là các giao diện cho phép tách hoặc nhảy trạng thái generator, hữu ích khi chia workload. Chúng giải quyết vấn đề phân luồng/tạo stream độc lập cho tính toán; **không phải một lớp bảo mật**.

## 10. Chọn API theo công việc

| Bài toán | API phù hợp | Lý do |
| --- | --- | --- |
| Unit test cần dãy cố định | `new Random(seed)` | Cùng seed và cùng calls tái tạo dãy |
| Monte Carlo tuần tự | `Random` hoặc generator phù hợp | Đủ cho mô phỏng, dễ tái lập |
| Mô phỏng đa luồng đơn giản | `ThreadLocalRandom.current()` | Giảm contention giữa threads |
| Fork/join cần tách sequence | `SplittableRandom.split()` hoặc `SplittableGenerator` | Mỗi task có state riêng |
| Game không có tài sản bảo mật | `Random`/`ThreadLocalRandom` | Tốc độ và phân bố là chính |
| Chọn phần tử trong bài toán bảo mật | `SecureRandom.nextInt(bound)` | Cần không thể đoán |
| Session token/reset token | `SecureRandom.nextBytes` | Cần entropy và khó dự đoán |
| Sinh key/secret material | JCA key generator dùng `SecureRandom` | Dùng primitive quản lý key đúng |
| Salt cho password KDF | `SecureRandom` | Salt cần unique/ngẫu nhiên, không cần bí mật |
| Nonce cho AEAD | `SecureRandom` hoặc cơ chế unique counter phù hợp | Phải thỏa uniqueness và yêu cầu protocol |
| Lottery/audit tài chính | CSPRNG + protocol fairness/audit | RNG tốt không tự giải quyết minh bạch hệ thống |

**Chọn theo threat model và hợp đồng dữ liệu.** Không phải mọi bài toán “cần random” đều là bài toán mật mã; cũng không được tối ưu performance bằng cách thay SecureRandom bằng Random trong luồng tạo token.

## 11. Dùng SecureRandom để tạo token

Một token bearer cần khó đoán. Ví dụ tạo 32 byte rồi biểu diễn dưới dạng Base64url:

~~~java
SecureRandom random = new SecureRandom();

byte[] tokenBytes = new byte[32];
random.nextBytes(tokenBytes);

String token = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(tokenBytes);
~~~

Đây là mã minh họa, cần import `java.util.Base64` và `java.security.SecureRandom`.

- 32 byte là 256 bit **độ dài đầu ra**.
- Base64url không padding biến 32 byte thành 43 ký tự.
- Base64url chỉ thay cách biểu diễn để phù hợp URL; nó **không tạo thêm entropy**.
- Tính khó đoán đến từ `SecureRandom` và seed/provider phù hợp.

### 11.1. Lưu token thế nào?

Với bearer token, ai sở hữu token có thể được quyền truy cập trong phạm vi token. Một thiết kế thường gặp:
1. Sinh token ngẫu nhiên bằng CSPRNG.
2. Gửi token cho client đúng một lần qua kênh TLS.
3. Server lưu digest/hash của token hoặc định danh đã được bảo vệ, tùy thiết kế.
4. Khi client gửi token, server xác minh trạng thái, expiry, scope, user/session và revocation.
5. Thu hồi/rotate token khi cần.
6. Không log token nguyên văn.

Randomness là một phần của bảo mật; authorization, transport, storage, expiry và revocation vẫn cần.

## 12. OTP và số ngẫu nhiên trong một miền

Ví dụ sinh mã 6 chữ số:

~~~java
SecureRandom random = new SecureRandom();
int code = random.nextInt(1_000_000);
String otp = String.format(Locale.ROOT, "%06d", code);
~~~

`nextInt(1_000_000)` tạo giá trị từ 0 đến 999999. `%06d` giữ số 0 ở đầu, ví dụ `004281`. Dùng `Locale.ROOT` để định dạng mã ổn định.

Có 1.000.000 khả năng, tương đương khoảng:

\[
\log_2(1{,}000{,}000) \approx 19.93 \text{ bits}
\]

Vì vậy OTP ngắn phải được bảo vệ thêm bằng thời hạn hết hạn ngắn, giới hạn số lần thử, rate limiting, one-time use, chống replay và trạng thái xác minh phía server. SecureRandom giúp mã khó đoán hơn, nhưng không biến không gian 6 chữ số thành không gian 256 bit.

## 13. Không dùng modulo tùy tiện để chọn số có giới hạn

Một lỗi phổ biến:

~~~java
int value = Math.abs(random.nextInt()) % 10;
~~~

Cách này có hai vấn đề:
1. `Math.abs(Integer.MIN_VALUE)` vẫn là số âm do overflow.
2. Modulo trên miền đầu vào không chia hết cho 10 có thể tạo **modulo bias**: một số giá trị có nhiều đầu vào ánh xạ tới hơn các giá trị khác.

Dùng API có bound:

~~~java
int value = secureRandom.nextInt(10);
~~~

Hoặc với generator cho mô phỏng:

~~~java
int value = random.nextInt(10);
~~~

Các API bounded được thiết kế để chọn theo hợp đồng phân bố. Nếu tự tạo alphabet/token, hãy chọn bằng `nextInt(alphabet.length())` chứ không dùng `% alphabet.length()` trên byte ngẫu nhiên tùy tiện.

## 14. Keys, salt và nonce: ba loại dữ liệu không giống nhau

| Giá trị | Mục đích | Có cần bí mật? | Có cần không trùng? | Cần khó đoán? |
| --- | --- | --- | --- | --- |
| Cryptographic key | Quyền mã hóa/giải mã hoặc ký/xác minh | **Có** với secret/private key | Theo thuật toán/lifecycle | Thường có khi sinh |
| Password salt | Làm mỗi password hash có đầu vào riêng | **Không** | Cần unique/ngẫu nhiên theo policy | Không cần bí mật |
| AEAD nonce/IV | Đảm bảo mỗi lần dùng cipher thỏa điều kiện mode | Thường **không** | AES-GCM yêu cầu không lặp dưới cùng key | Tùy mode/protocol |
| Session token | Bearer credential | **Có** | Cần xác suất không trùng đủ thấp | **Có** |
| Challenge | Chứng minh một phiên/tác vụ đang diễn ra | Có thể công khai sau khi gửi | Thường cần one-time | **Có** |
| Request ID | Correlation/trace | Không | Có thể cần uniqueness | Không nhất thiết |

### 14.1. Sinh key

Đối với AES/RSA/EC hoặc key JCA khác, thường dùng `KeyGenerator` hoặc `KeyPairGenerator` cùng provider/parameters phù hợp, thay vì tự ghép byte bằng `Random`.

~~~java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey key = generator.generateKey();
~~~

Đây là ví dụ JCA; khả năng key size và provider phụ thuộc runtime/policy. Với thuật toán asymmetric, dùng `KeyPairGenerator` và tham số phù hợp. Key còn cần lưu, phân quyền, rotate, backup và xóa đúng cách.

### 14.2. Sinh salt cho password hashing

Salt thường được lưu cùng password verifier; nó **không phải secret key**. Mục đích là đảm bảo mỗi password hash có salt riêng, làm precomputation/rainbow-table khó dùng chung.

~~~java
byte[] salt = new byte[16];
new SecureRandom().nextBytes(salt);
~~~

Đây là cách tạo bytes ngẫu nhiên; việc hash password phải dùng KDF chuyên dụng như Argon2id, scrypt hoặc PBKDF2 theo hướng dẫn bảo mật hiện hành. Không dùng `Random` để tạo salt cho hệ thống bảo mật và không tự thiết kế password hash.

### 14.3. Nonce của AES-GCM cần uniqueness theo key

`SecureRandom` có thể tạo nonce 96-bit ngẫu nhiên, nhưng nó **không tự bảo đảm không có collision**. Với một key dùng rất nhiều lần, xác suất trùng nonce tăng theo số lần sử dụng. AES-GCM yêu cầu nonce không được lặp lại với cùng key; nếu vi phạm có thể phá tính bảo mật nghiêm trọng.

Với hệ thống volume lớn, cần policy nonce rõ:
- Dùng random nonce với giới hạn số lần encrypt theo key và rotation phù hợp.
- Hoặc dùng counter/unique allocator được đồng bộ để bảo đảm uniqueness.
- Gắn nonce đúng với ciphertext/tag và lưu đủ metadata.
- Không dùng nonce cố định hoặc timestamp đơn giản.
- Không dùng cùng một key/nonce pair cho nhiều message.

**Không đồng nhất “không thể đoán” và “không trùng”.** Một giá trị có thể khó đoán nhưng vẫn có thể trùng; một counter có thể không trùng nhưng không bí mật. Yêu cầu của từng protocol quyết định cách tạo.

## 15. Reproducibility cho simulation và test

Đối với mô phỏng, điều quan trọng thường là:
- Có thể tái tạo dãy số.
- Biết seed đã dùng.
- Biết thuật toán và phiên bản runtime.
- Chia sequence giữa các task có quy tắc.
- Không phụ thuộc lịch chạy không xác định nếu muốn kết quả tái lập.

~~~java
long seed = 2026L;
RandomGenerator generator =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(seed);

double sample = generator.nextDouble();
~~~

Đây là ví dụ Java 17+. Ghi seed và algorithm name vào metadata của simulation. Đừng chỉ ghi “random seed”; nếu thuật toán mặc định thay đổi giữa các phiên bản, kết quả có thể không tái lập.

### 15.1. Lưu ý khi chạy parallel

Nếu chia một generator thành các task, thứ tự schedule có thể ảnh hưởng generator chia sẻ. Dùng `SplittableRandom.split()` hoặc `RandomGenerator.SplittableGenerator` để tạo các stream riêng theo cấu trúc task.

Với simulation cần reproducibility tuyệt đối, phải kiểm soát cả seed gốc, cách split/đánh số task, algorithm/version, thứ tự tổng hợp kết quả và các nguồn ngẫu nhiên phụ từ thư viện khác.

### 15.2. Không dùng SecureRandom làm random seed tái lập cho test

Nếu cần test deterministic, inject một generator có seed cố định qua dependency injection. Nếu code production cần CSPRNG, inject `SecureRandom` theo abstraction riêng và test bằng fake/stub phù hợp. **Không thay SecureRandom bằng Random trong production chỉ để test dễ hơn**; hãy tách dependency và kiểm tra hành vi đúng theo interface.

## 16. Statistical testing và security testing

Một bài kiểm tra phân bố có thể phát hiện một số lỗi: dãy toàn số 0, range sai, lệch phân bố rõ rệt, chu kỳ quá ngắn hoặc correlation bất thường.

Nhưng test thống kê **không chứng minh CSPRNG chống dự đoán**. RFC 4086 nhấn mạnh dữ liệu có vẻ thống kê ngẫu nhiên vẫn có thể dự đoán nếu thuật toán/seed yếu. Ngược lại, một mẫu ngắn có phân bố không đều không nhất thiết chứng minh generator sai; cần xét sample size và kiểm định thống kê đúng.

### 16.1. Kiểm thử PRNG

- Cùng seed và cùng calls cho cùng output khi API cam kết.
- Bound luôn nằm trong [origin, bound).
- Generator không vô tình dùng chung state giữa task.
- Seed được ghi lại và test có thể tái lập.
- Chạy kiểm thử thống kê đủ lớn cho mục tiêu simulation.
- Không dựa vào một histogram nhỏ để khẳng định chất lượng.

### 16.2. Kiểm thử SecureRandom

Không nên viết:

~~~java
assertNotEquals(firstToken, secondToken);
~~~

Hai output của CSPRNG **có thể trùng nhau về mặt xác suất**; với không gian đủ lớn xác suất rất thấp nhưng không phải zero. Test không nên dựa vào giả định “mọi lần luôn khác nhau”.

Nên kiểm tra:
- Byte array có đúng độ dài.
- Token encoding đúng alphabet và độ dài.
- Giá trị bounded nằm đúng range.
- Integration test không thể đoán token từ user ID, timestamp hoặc counter.
- Key/nonce protocol được áp dụng đúng, không reuse theo cách cấm.
- Security provider và thuật toán đáp ứng policy môi trường.
- Không log secret, seed, token hoặc key material.

**Không có unit test nhỏ nào thay thế được việc chọn implementation, seed source và protocol đúng.** Với hệ thống mật mã, đánh giá theo chuẩn, provider, cấu hình và threat model.

## 17. Những lỗi nghiêm trọng cần tránh

1. **Dùng Random tạo session ID.** Random không cryptographically secure; dùng SecureRandom cho token.
2. **Seed bằng currentTimeMillis.** Thời gian có thể bị đoán trong một khoảng hẹp; nhiều chữ số không đồng nghĩa nhiều entropy.
3. **Seed bằng PID, counter, user ID hoặc hashCode.** Các giá trị này thường công khai, lặp lại hoặc có miền nhỏ.
4. **Gọi setSeed trên SecureRandom bằng seed yếu.** Gọi trước nextBytes/reseed đầu tiên có thể ngăn cơ chế self-seeding thông thường.
5. **Dùng ThreadLocalRandom vì “mỗi thread có seed riêng”.** Seed riêng không đồng nghĩa khó đoán.
6. **Dùng SplittableRandom cho token.** Split state phục vụ parallel computation, không tạo tính an toàn mật mã.
7. **Nghĩ mọi RandomGenerator đều an toàn.** Đây là giao diện chung; phải xem implementation cụ thể.
8. **Dùng modulo để tạo số có giới hạn.** Có thể tạo bias và lỗi overflow; dùng nextInt(bound).
9. **Dùng output length làm thước đo entropy.** 32 byte không chứng minh 256 bit entropy nếu seed yếu.
10. **In token/seed ra log.** Log có thể trở thành nơi rò bearer credential hoặc seed.
11. **Tự viết CSPRNG từ Random + SHA-256.** Vòng hash tự chế không tự động đạt chuẩn DRBG.
12. **Gọi getInstanceStrong ở mọi request.** Có thể tăng overhead hoặc block; tái sử dụng instance và chỉ chọn khi policy yêu cầu.
13. **Nghĩ SecureRandom luôn là true random.** Nhiều implementation là DRBG; điều cần là cryptographic strength.
14. **Nghĩ SecureRandom không bao giờ block.** Một số provider có thể block khi thu thập entropy.
15. **Dùng cùng nonce AES-GCM cho nhiều message với một key.** Đây là vi phạm nghiêm trọng điều kiện nonce uniqueness.
16. **Dùng salt như secret key.** Salt thường công khai; password verifier vẫn cần KDF phù hợp.
17. **Dùng SecureRandom rồi vẫn để OTP không hết hạn.** RNG không thay expiry, one-time use, attempt limit và replay prevention.
18. **Dùng token ngắn rồi tin SecureRandom đủ bù.** Không gian nhỏ vẫn dễ brute force; cần tăng độ dài và rate limit.
19. **Dùng một instance SplittableRandom cho nhiều thread.** Lớp này không thread-safe; dùng split để cấp generator riêng.
20. **Chia sẻ Random toàn cục cho workload song song lớn.** Có thể contention; chọn ThreadLocalRandom hoặc split generator cho tính toán.
21. **Dùng getDefault khi cần tái lập lâu dài.** Thuật toán mặc định có thể thay đổi; pin tên thuật toán và seed.
22. **Cho rằng statistical test pass là chứng nhận mật mã.** Test thống kê không chứng minh unpredictability.

## 18. Chương trình Java hoàn chỉnh: so sánh các loại generator

Chương trình **`RandomnessKindsDemo.java`** minh họa:

1. `Random(seed)` tạo dãy tái lập.
2. `SplittableRandom(seed)` tạo dãy tái lập trong cùng implementation.
3. `RandomGeneratorFactory` chọn tên thuật toán LXM và seed rõ ràng trên Java 17+.
4. `ThreadLocalRandom` tạo số trong khoảng giới hạn cho tác vụ tính toán.
5. `SecureRandom` tạo 32 byte token, không in token ra màn hình.
6. Base64url không padding biểu diễn 32 byte thành 43 ký tự.
7. `SecureRandom` cũng implement `RandomGenerator`, nhưng không suy ra các generator khác đều an toàn.
8. `SecureRandom.nextInt(bound)` tạo giá trị có giới hạn phù hợp cho challenge/OTP.

Lưu thành **`RandomnessKindsDemo.java`**. Đây là chương trình độc lập, dùng API Java 17+ và đã được biên dịch/chạy trên OpenJDK 24.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.Random;
import java.util.SplittableRandom;
import java.util.concurrent.ThreadLocalRandom;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public final class RandomnessKindsDemo {
    private RandomnessKindsDemo() {
    }

    private static int[] draw(RandomGenerator generator) {
        int[] values = new int[8];
        for (int i = 0; i < values.length; i++) {
            values[i] = generator.nextInt(1_000_000);
        }
        return values;
    }

    public static void main(String[] args) {
        Random randomA = new Random(12345L);
        Random randomB = new Random(12345L);
        System.out.println("randomSeedReproducible="
                + Arrays.equals(draw(randomA), draw(randomB)));

        SplittableRandom splitA = new SplittableRandom(2026L);
        SplittableRandom splitB = new SplittableRandom(2026L);
        System.out.println("splittableSeedReproducible="
                + Arrays.equals(draw(splitA), draw(splitB)));

        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");
        RandomGenerator modernA = factory.create(77L);
        RandomGenerator modernB = factory.create(77L);
        System.out.println("namedGeneratorReproducible="
                + Arrays.equals(draw(modernA), draw(modernB)));

        int simulationValue =
                ThreadLocalRandom.current().nextInt(10, 20);
        System.out.println("threadLocalRangeValid="
                + (simulationValue >= 10 && simulationValue < 20));

        SecureRandom secureRandom = new SecureRandom();
        byte[] tokenBytes = new byte[32];
        secureRandom.nextBytes(tokenBytes);
        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(tokenBytes);

        System.out.println("secureRandomImplementsRandomGenerator="
                + (secureRandom instanceof RandomGenerator));
        System.out.println("tokenByteLength=" + tokenBytes.length);
        System.out.println("tokenBase64UrlLength=" + token.length());
        System.out.println("tokenAlphabetValid="
                + token.matches("[A-Za-z0-9_-]{43}"));

        int challenge = secureRandom.nextInt(1_000_000);
        System.out.println("secureBoundedRangeValid="
                + (challenge >= 0 && challenge < 1_000_000));
    }
}
~~~

### 18.1. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 RandomnessKindsDemo.java
java RandomnessKindsDemo
~~~

### 18.2. Đầu ra đã kiểm tra

~~~text
randomSeedReproducible=true
splittableSeedReproducible=true
namedGeneratorReproducible=true
threadLocalRangeValid=true
secureRandomImplementsRandomGenerator=true
tokenByteLength=32
tokenBase64UrlLength=43
tokenAlphabetValid=true
secureBoundedRangeValid=true
~~~

### 18.3. Giải thích kết quả

- Ba dòng `...Reproducible=true` chứng minh hai object cùng seed và cùng chuỗi calls trong ví dụ tạo cùng dãy trên runtime đang chạy. Đây là hành vi hữu ích cho simulation.
- `threadLocalRangeValid=true` chỉ kiểm tra giá trị nằm trong [10,20); chương trình không in giá trị ngẫu nhiên cụ thể nên stdout ổn định.
- `secureRandomImplementsRandomGenerator=true` cho thấy SecureRandom có thể dùng qua giao diện chung Java 17. Điều này không làm Random trở nên secure.
- `tokenByteLength=32` là 32 byte đầu ra. Không có token cụ thể bị ghi vào console.
- `tokenBase64UrlLength=43` là chiều dài biểu diễn của 32 byte Base64url không padding.
- `tokenAlphabetValid=true` xác nhận text chỉ có ký tự thuộc alphabet URL-safe.
- `secureBoundedRangeValid=true` xác nhận challenge nằm trong miền hợp lệ; nó không khẳng định một lần chạy nào đó sẽ không trùng lần khác.

Chương trình cố ý không in seed nhạy cảm, token, byte ngẫu nhiên, thuật toán/provider runtime hoặc challenge thực. Vì thế các dòng stdout được kiểm tra có tính ổn định, không phụ thuộc giá trị CSPRNG.

## 19. Bảng quyết định nhanh cho code review

| Nếu thấy trong code... | Hỏi ngay điều gì? | Hướng xử lý |
| --- | --- | --- |
| `new Random(seed)` | Seed dùng cho simulation/test hay tạo secret? | Chỉ dùng cho mục đích không nhạy cảm |
| `Math.random()` | Giá trị có liên quan quyền truy cập/token không? | Nếu có, thay bằng SecureRandom |
| `ThreadLocalRandom.current()` | Có dùng trong token/OTP/nonce không? | Nếu có, thay bằng SecureRandom |
| `new SplittableRandom()` | Generator có bị chia sẻ nhiều thread không? | Dùng split cho parallel; không dùng cho security |
| `RandomGenerator.getDefault()` | Có yêu cầu tái lập qua phiên bản không? | Pin tên thuật toán và seed |
| `new SecureRandom()` | Dùng cho mục đích bảo mật nào, token dài bao nhiêu? | Xác định entropy/expiry/uniqueness policy |
| `secureRandom.setSeed(clock)` | Vì sao phải tự seed? Nguồn có entropy không? | Bỏ seed yếu, để provider tự seed |
| `Math.abs(nextInt()) % n` | Có bias hoặc overflow không? | Dùng nextInt(bound) |
| `new byte[32]` | Có thật sự được điền bởi CSPRNG không? | Gọi SecureRandom.nextBytes |
| Nonce cố định | Có tái sử dụng cùng key không? | Thiết kế uniqueness theo mode |
| `getInstanceStrong()` | Có policy/provider cụ thể không? | Đo latency, xử lý exception và blocking |
| Token in ra log | Ai có quyền đọc log? | Redact, không log secret |

## 20. Checklist sử dụng đúng trong ứng dụng

- [ ] Đã xác định đây là random cho mô phỏng/tính toán hay random cho bảo mật?
- [ ] Nếu cần tái lập, đã dùng seed cố định và ghi lại algorithm/runtime chưa?
- [ ] Nếu chạy parallel, đã dùng ThreadLocalRandom hoặc split/jump generator thay vì chia sẻ state tùy tiện?
- [ ] Có tránh dùng `Random`, `Math.random`, `ThreadLocalRandom`, `SplittableRandom` cho token và secret?
- [ ] Với security-sensitive values, đã dùng `SecureRandom` hoặc API JCA được provider hỗ trợ?
- [ ] Có để SecureRandom tự seed và tránh setSeed bằng clock/PID/counter?
- [ ] Nếu yêu cầu strong provider cụ thể, đã hiểu `getInstanceStrong` và cấu hình `securerandom.strongAlgorithms`?
- [ ] Đã hiểu một CSPRNG có thể dùng DRBG deterministic bên trong?
- [ ] Có phân biệt độ dài byte đầu ra với entropy thực?
- [ ] Khi cần bounded random, có dùng `nextInt(bound)`/`nextLong(bound)` thay vì modulo?
- [ ] Token có đủ không gian khó đoán, expiry, one-time use, rate limiting và revocation?
- [ ] Password salt được tạo bằng CSPRNG và KDF chuyên dụng được dùng để hash password?
- [ ] Key được tạo bằng JCA KeyGenerator/KeyPairGenerator hoặc KMS phù hợp?
- [ ] Nonce/IV thỏa yêu cầu riêng của encryption mode, nhất là uniqueness với cùng key?
- [ ] Có giới hạn và rotate key theo số lần sử dụng/thuật toán?
- [ ] Không log token, key, seed hoặc byte nhạy cảm?
- [ ] Test CSPRNG không dựa vào giả định hai output liên tiếp chắc chắn khác nhau?
- [ ] Có phân biệt statistical testing với security/unpredictability analysis?
- [ ] Khi nâng JDK/provider, có test lại algorithm availability, startup, performance và security policy?
- [ ] Nếu cần audit, đã có quy trình ghi lại thuật toán/phiên bản/policy mà không lưu secret state?

**Ghi nhớ:** PRNG cho tính toán tối ưu khả năng tái lập, tốc độ và chất lượng thống kê; CSPRNG tối ưu khả năng không thể dự đoán trong mô hình tấn công. `Random`, `ThreadLocalRandom` và `SplittableRandom` phù hợp cho mô phỏng và thuật toán thông thường theo đặc tính riêng. `RandomGenerator` từ Java 17 chỉ là giao diện chung, không phải dấu chứng nhận bảo mật. Với token, key material, OTP, salt và nonce, hãy chọn `SecureRandom` và tuân thủ yêu cầu entropy, uniqueness, lifecycle và protocol tương ứng.

## Tài liệu chính thức và chuẩn

- [Oracle Java SE 26 — SecureRandom: cryptographically strong RNG, tự seed, nextBytes, thread safety](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html)
- [Oracle Java SE 26 — Random: seed 48 bit, LCG, sequence reproducibility và giới hạn bảo mật](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Random.html)
- [Oracle Java SE 26 — ThreadLocalRandom: generator riêng cho thread và không an toàn mật mã](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [Oracle Java SE 26 — SplittableRandom: split state, parallel computation và giới hạn bảo mật](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/SplittableRandom.html)
- [Oracle Java SE 26 — RandomGenerator: giao diện chung từ Java 17, thread-safety và security caveats](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/random/RandomGenerator.html)
- [Oracle Java SE 17 — RandomGeneratorFactory: chọn generator theo tên và seed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html)
- [Oracle Java SE 26 Security Developer's Guide — SecureRandom, DRBG và seed](https://docs.oracle.com/en/java/javase/26/security/security-developer-guide.pdf)
- [NIST SP 800-90A Rev. 1 — Recommendation for Random Number Generation Using Deterministic Random Bit Generators](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final)
- [NIST SP 800-90B — Recommendation for the Entropy Sources Used for Random Bit Generation](https://csrc.nist.gov/pubs/sp/800/90/b/final)
- [NIST SP 800-90C — Recommendation for Random Bit Generator Constructions](https://csrc.nist.gov/pubs/sp/800/90/c/final)
- [RFC 4086 — Randomness Requirements for Security: thống kê tốt không đồng nghĩa khó dự đoán](https://www.rfc-editor.org/rfc/rfc4086)
