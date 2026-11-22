# Phân biệt nguồn ngẫu nhiên mô phỏng với SecureRandom cho bảo mật

Java có nhiều nguồn sinh số ngẫu nhiên, nhưng chúng phục vụ những mục đích khác nhau. Một mô phỏng Monte Carlo cần chuỗi số có phân bố phù hợp và có thể tái lập khi dùng cùng seed. Một token đặt lại mật khẩu lại cần giá trị khó đoán đối với kẻ tấn công. Dùng cùng một bộ sinh cho cả hai trường hợp dễ dẫn đến kết quả mô phỏng khó tái lập hoặc làm lộ bí mật bảo mật.

Java 21 cung cấp hệ API `RandomGenerator` cho các bộ sinh giả ngẫu nhiên thông thường và `SecureRandom` cho nhu cầu mật mã. Việc chọn đúng loại, quản lý seed, chia sẻ generator giữa các thread và tạo giá trị trong một khoảng xác định là những phần quan trọng của thiết kế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt PRNG phục vụ mô phỏng với CSPRNG phục vụ bảo mật.
- Chọn `RandomGenerator`, `ThreadLocalRandom`, `SplittableRandom` hoặc `SecureRandom` theo yêu cầu.
- Dùng seed để tái lập kết quả mô phỏng và hiểu vì sao không tự seed `SecureRandom` bằng dữ liệu dễ đoán.
- Tạo token, nonce và mã xác minh bằng `SecureRandom`.
- Sinh số trong khoảng đúng cách, tránh modulo bias và lỗi biên.
- Quản lý generator khi chạy nhiều thread và kiểm thử logic ngẫu nhiên.

## 1. Hai mục tiêu khác nhau của tính ngẫu nhiên

### 1.1. Ngẫu nhiên cho mô phỏng và tính toán

Trong mô phỏng, kiểm thử thống kê hoặc thuật toán cần lựa chọn ngẫu nhiên, ta thường cần một chuỗi giả ngẫu nhiên có các đặc tính:

- Phân bố phù hợp với bài toán.
- Tốc độ sinh đủ tốt cho số lượng phép thử lớn.
- Có thể tái tạo chuỗi bằng cùng thuật toán và seed.
- Có thể chia nhỏ luồng sinh số để xử lý song song.

Một PRNG (Pseudo-Random Number Generator) dùng trạng thái nội bộ và thuật toán xác định để sinh chuỗi số. Khi thuật toán và trạng thái khởi đầu giống nhau, chuỗi kết quả có thể lặp lại. Tính tái lập này rất hữu ích khi debug một mô phỏng hoặc so sánh hai phiên bản thuật toán.

### 1.2. Ngẫu nhiên cho bảo mật

Trong bảo mật, yêu cầu quan trọng là kẻ tấn công không thể dự đoán giá trị tiếp theo dựa trên các giá trị đã quan sát hoặc thông tin công khai. Nguồn cần có tính chất của CSPRNG (Cryptographically Secure Pseudo-Random Number Generator), được thiết kế để chống dự đoán và khôi phục trạng thái trong mô hình đe dọa phù hợp.

Các giá trị thường cần nguồn ngẫu nhiên mật mã:

- Session ID và token xác thực.
- Token đặt lại mật khẩu hoặc liên kết xác minh email.
- Nonce, challenge và giá trị ngẫu nhiên dùng trong giao thức bảo mật.
- Salt ngẫu nhiên cho quy trình băm mật khẩu.
- Khóa hoặc vật liệu khóa khi API mật mã yêu cầu nguồn ngẫu nhiên.

Không dùng PRNG thông thường chỉ vì kết quả “trông có vẻ ngẫu nhiên”. `Random`, `ThreadLocalRandom` và `SplittableRandom` không được thiết kế để chống kẻ tấn công dự đoán trạng thái.

| Tiêu chí | PRNG cho mô phỏng | CSPRNG cho bảo mật |
|---|---|---|
| Mục tiêu | Tốc độ, phân bố, tái lập | Khó dự đoán trước đối thủ |
| Seed | Có thể cố định để tái lập | Phải được tạo và quản lý an toàn |
| Chọn thuật toán | Theo chất lượng thống kê, hiệu năng và khả năng chia luồng | Dùng `SecureRandom` và provider/algorithm phù hợp |
| Chia sẻ giữa thread | Tùy implementation | `SecureRandom` an toàn khi dùng đồng thời theo hợp đồng API |
| Ví dụ | Mô phỏng, game, randomized testing | Token, nonce, salt, challenge |

## 2. Hệ API RandomGenerator trong Java 21

Từ Java 17, Java có package `java.util.random` với interface `RandomGenerator` và các factory để lựa chọn thuật toán. Java 21 tiếp tục hỗ trợ API này.

`RandomGenerator` cung cấp các phương thức sinh số như:

- `nextInt()` và `nextLong()`.
- `nextInt(bound)` và `nextLong(bound)`.
- `nextDouble()` và `nextFloat()`.
- Các phương thức tạo giá trị theo khoảng hoặc phân bố được API hỗ trợ.

Một số implementation hiện hành:

| Implementation | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| `Random` | PRNG tổng quát, seed có thể đặt, an toàn luồng nhưng có thể contention khi chia sẻ | Tương thích API và nhu cầu đơn giản |
| `ThreadLocalRandom` | Generator gắn với thread hiện tại, giảm contention khi nhiều thread sinh số | Tác vụ đồng thời không cần tái lập theo seed riêng |
| `SplittableRandom` | Có thể `split()` thành generator con, không thiết kế để nhiều thread cùng sửa một instance | Mô phỏng hoặc tính toán song song |
| Các implementation được `RandomGeneratorFactory` cung cấp | Lựa chọn thuật toán PRNG theo đặc tính và seed | Khi cần chọn rõ thuật toán cho workload |
| `SecureRandom` | Bộ sinh ngẫu nhiên mật mã | Giá trị bí mật và giao thức bảo mật |

Việc một class triển khai `RandomGenerator` không có nghĩa nó có tính bảo mật mật mã. Hãy chọn theo hợp đồng của implementation, không chỉ theo interface chung.

## 3. Dùng RandomGenerator cho mô phỏng có thể tái lập

Với một mô phỏng, có thể tạo `SplittableRandom` bằng seed cố định:

```java
import java.util.SplittableRandom;

SplittableRandom random = new SplittableRandom(2026L);

for (int i = 0; i < 5; i++) {
    System.out.println(random.nextDouble());
}
```

Chạy lại cùng chương trình với cùng seed và cùng chuỗi lời gọi sẽ tái tạo chuỗi kết quả. Đây là đặc tính hữu ích khi cần điều tra một trường hợp mô phỏng thất bại.

Nếu thuật toán chỉ cần abstraction chung, khai báo biến bằng `RandomGenerator`:

```java
import java.util.random.RandomGenerator;
import java.util.SplittableRandom;

static double estimate(RandomGenerator random, int samples) {
    int inside = 0;

    for (int i = 0; i < samples; i++) {
        double x = random.nextDouble(-1.0, 1.0);
        double y = random.nextDouble(-1.0, 1.0);
        if (x * x + y * y <= 1.0) {
            inside++;
        }
    }

    return 4.0 * inside / samples;
}

double estimate = estimate(new SplittableRandom(2026L), 1_000_000);
```

Trong ví dụ này, `RandomGenerator` chỉ là abstraction của nguồn số giả ngẫu nhiên. Hàm `estimate` không được dùng cho mục đích bảo mật.

### 3.1. Chọn thuật toán tường minh bằng RandomGeneratorFactory

Nếu cần kiểm soát thuật toán PRNG, có thể dùng `RandomGeneratorFactory`:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
    RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator random = factory.create(2026L);
```

Tên thuật toán phải được hỗ trợ bởi runtime đang triển khai. Có thể liệt kê các factory khả dụng:

```java
RandomGeneratorFactory.all()
    .map(RandomGeneratorFactory::name)
    .sorted()
    .forEach(System.out::println);
```

Khi kết quả mô phỏng cần tái lập lâu dài, ghi nhận cả thuật toán, seed và phiên bản môi trường cùng cấu hình đầu vào. Chỉ lưu seed nhưng để thuật toán mặc định thay đổi có thể làm kết quả khác đi khi triển khai ở môi trường khác.

## 4. Chọn generator cho ứng dụng nhiều thread

Không phải implementation `RandomGenerator` nào cũng có cùng hợp đồng thread-safety.

### 4.1. ThreadLocalRandom

`ThreadLocalRandom.current()` trả về generator gắn với thread hiện tại. Nó phù hợp khi nhiều thread độc lập cần sinh số cho các quyết định không liên quan đến bảo mật, ví dụ jitter cho retry hoặc chọn dữ liệu thử nghiệm.

```java
import java.util.concurrent.ThreadLocalRandom;

int delayMillis = ThreadLocalRandom.current().nextInt(100, 501);
```

Khoảng trên bao gồm 100 và không bao gồm 501, tức giá trị có thể từ 100 đến 500. `ThreadLocalRandom` giảm contention so với việc nhiều thread chia sẻ một generator chung.

Không dùng `ThreadLocalRandom` cho token, session ID, OTP hoặc nonce bảo mật. Nó không cung cấp cam kết chống dự đoán.

### 4.2. SplittableRandom

`SplittableRandom` được thiết kế để tạo các generator con cho tính toán song song. Không chia sẻ cùng một instance cho nhiều thread đồng thời; hãy tách generator cho từng nhánh công việc:

```java
SplittableRandom root = new SplittableRandom(2026L);

SplittableRandom firstTaskRandom = root.split();
SplittableRandom secondTaskRandom = root.split();
```

Mỗi tác vụ dùng generator riêng. Điều này giảm tranh chấp và cho phép cấu trúc hóa luồng ngẫu nhiên theo nhánh tính toán.

Để kết quả song song có thể tái lập, cần kiểm soát cách phân chia generator và cách gán generator cho task. Nếu thứ tự task phụ thuộc lịch chạy, không nên giả định kết quả toàn cục vẫn giống nhau chỉ vì root seed không đổi. Có thể gán seed theo task ID ổn định hoặc lưu lại cấu trúc phân chia.

### 4.3. Random dùng chung

`java.util.Random` vẫn là API hiện hành và an toàn khi nhiều thread gọi đồng thời, nhưng việc chia sẻ một instance có thể tạo contention. Nếu cần tương thích với API nhận `Random`, có thể dùng nó; với mã mới, hãy cân nhắc `RandomGenerator`, `ThreadLocalRandom` hoặc `SplittableRandom` tùy workload.

Không nên dùng `new Random()` cho dữ liệu bí mật. Seed mặc định không biến `Random` thành CSPRNG.

## 5. SecureRandom cho dữ liệu bảo mật

`SecureRandom` là bộ sinh ngẫu nhiên mật mã trong `java.security`. Nó cung cấp các phương thức sinh dữ liệu như `nextBytes()`, `nextInt()` và `nextLong()` với mục tiêu chống dự đoán trong mô hình bảo mật mà provider hỗ trợ.

Thông thường, tạo một instance và tái sử dụng:

```java
import java.security.SecureRandom;

private static final SecureRandom SECURE_RANDOM = new SecureRandom();
```

`SecureRandom` được thiết kế an toàn khi nhiều thread sử dụng đồng thời. Không cần tạo một instance mới cho từng request; tái sử dụng instance do ứng dụng quản lý thường tránh chi phí khởi tạo và seed lặp lại.

Không tự seed `SecureRandom` bằng timestamp, số thứ tự, user ID hoặc dữ liệu dễ đoán. Provider chịu trách nhiệm khởi tạo nguồn ngẫu nhiên phù hợp. Gọi `setSeed()` với giá trị yếu không làm nguồn trở nên an toàn hơn và có thể ảnh hưởng cơ chế tự seed của implementation.

### 5.1. Sinh token ngẫu nhiên

Ví dụ tạo token có 32 byte ngẫu nhiên, sau đó mã hóa Base64 URL-safe:

```java
import java.security.SecureRandom;
import java.util.Base64;

private static final SecureRandom SECURE_RANDOM = new SecureRandom();

static String newResetToken() {
    byte[] bytes = new byte[32];
    SECURE_RANDOM.nextBytes(bytes);

    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);
}
```

32 byte tương ứng 256 bit dữ liệu ngẫu nhiên trước khi mã hóa. Base64 URL-safe giúp token thuận tiện khi đưa vào URL. Khi dùng token trong production, cần kết hợp với:

- Thời hạn hiệu lực ngắn và mục đích sử dụng cụ thể.
- Cơ chế chỉ sử dụng một lần đối với token đặt lại mật khẩu hoặc xác minh.
- Giới hạn số lần thử và bảo vệ endpoint khỏi brute force.
- Lưu hash của token ở phía server nếu thiết kế yêu cầu tra cứu token mà không lưu nguyên bí mật.
- Không ghi token đầy đủ vào log, analytics hoặc thông báo lỗi.

Nguồn ngẫu nhiên tốt không thay thế việc quản lý vòng đời và lưu trữ token an toàn.

### 5.2. Sinh mã xác minh có độ dài cố định

Nếu cần mã số sáu chữ số:

```java
import java.security.SecureRandom;
import java.util.Locale;

private static final SecureRandom SECURE_RANDOM = new SecureRandom();

static String newVerificationCode() {
    int value = SECURE_RANDOM.nextInt(1_000_000);
    return String.format(Locale.ROOT, "%06d", value);
}
```

`nextInt(1_000_000)` sinh đều trong khoảng từ 0 đến 999.999; định dạng `%06d` giữ các số 0 ở đầu. Mã sáu chữ số có không gian tìm kiếm nhỏ, vì vậy phải có rate limit, thời hạn ngắn, giới hạn số lần thử và ràng buộc mã với đúng tài khoản hoặc phiên xác minh.

### 5.3. Sinh byte cho nonce hoặc salt

```java
static byte[] randomBytes(int length) {
    if (length <= 0) {
        throw new IllegalArgumentException("length must be positive");
    }

    byte[] bytes = new byte[length];
    SECURE_RANDOM.nextBytes(bytes);
    return bytes;
}
```

`nextBytes()` tạo dữ liệu ngẫu nhiên để ứng dụng dùng làm vật liệu đầu vào. Với nonce của thuật toán mã hóa, ngoài tính khó đoán còn phải đáp ứng yêu cầu duy nhất hoặc quy tắc không tái sử dụng theo thuật toán và khóa cụ thể. Chỉ dùng random bytes không thay thế việc quản lý nonce theo hợp đồng của chế độ mã hóa.

Salt cho password hashing thường không cần bí mật, nhưng cần ngẫu nhiên và khác nhau giữa các bản ghi. Hãy dùng `SecureRandom` để tạo salt và một password hashing/KDF phù hợp; không dùng `Random` hoặc hash nhanh thông thường để thay thế password hashing.

## 6. Chọn SecureRandom provider và algorithm

`new SecureRandom()` yêu cầu provider bảo mật mặc định cung cấp implementation phù hợp. Nếu hệ thống cần chỉ định algorithm hoặc provider, có thể dùng `SecureRandom.getInstance(...)`:

```java
SecureRandom random = SecureRandom.getInstance("DRBG");
```

Tên algorithm và khả năng hỗ trợ phụ thuộc provider/runtime. Trước khi chọn algorithm tường minh, kiểm tra tài liệu của JDK, provider và yêu cầu triển khai trên các môi trường đích.

Có thể xem implementation được chọn:

```java
System.out.println(random.getAlgorithm());
System.out.println(random.getProvider().getName());
```

### 6.1. `getInstanceStrong()` không phải lựa chọn mặc định cho mọi trường hợp

Java cung cấp `SecureRandom.getInstanceStrong()` để lấy implementation được cấu hình là strong theo thuộc tính bảo mật `securerandom.strongAlgorithms`.

```java
SecureRandom strong = SecureRandom.getInstanceStrong();
```

Phương thức này có thể chọn implementation có hành vi blocking trong một số môi trường, đặc biệt khi cần chờ entropy từ nguồn hệ thống. “Strong” không có nghĩa là mọi ứng dụng đều nên gọi phương thức này cho từng request. Hãy dùng default `SecureRandom` hoặc algorithm/provider được tổ chức phê duyệt, rồi kiểm thử latency và cấu hình entropy trên môi trường triển khai.

Không chuyển sang một algorithm cũ hoặc provider không được hỗ trợ chỉ để tránh blocking. Nếu khởi tạo hoặc sinh dữ liệu bị chậm, hãy xác định provider, entropy source và cách ứng dụng tạo instance trước khi thay đổi cấu hình bảo mật.

## 7. Vì sao không dùng Random hoặc ThreadLocalRandom cho token?

PRNG thông thường tối ưu cho mô phỏng hoặc tính toán, không cho khả năng chống dự đoán. Nếu seed hoặc trạng thái nội bộ có thể suy ra, kẻ tấn công có thể dự đoán các giá trị tiếp theo hoặc thu hẹp không gian tìm kiếm.

Các mẫu không an toàn:

```java
// Không dùng cho token hoặc session ID.
Random random = new Random();
int token = random.nextInt();

// Không dùng cho OTP hoặc reset code.
int code = ThreadLocalRandom.current().nextInt(1_000_000);
```

Các mẫu này có thể phù hợp cho mô phỏng, lựa chọn ngẫu nhiên không nhạy cảm hoặc test data, nhưng không đáp ứng yêu cầu CSPRNG.

Không tự xây CSPRNG bằng cách hash timestamp, nối UUID với counter hoặc lấy `Math.abs(random.nextInt())`. Hãy dùng `SecureRandom` và API mật mã chuẩn của Java.

## 8. Sinh số trong khoảng đúng cách

Các phương thức nhận bound của Java thường giúp tránh modulo bias:

```java
int dice = SECURE_RANDOM.nextInt(6) + 1; // 1..6
long index = SECURE_RANDOM.nextLong(100); // 0..99
double ratio = SECURE_RANDOM.nextDouble(0.0, 1.0); // [0.0, 1.0)
```

Với `nextInt(bound)`, bound phải lớn hơn 0 và giá trị trả về nằm trong `[0, bound)`. Với `nextInt(origin, bound)`, origin được bao gồm và bound bị loại trừ. Các overload tương ứng của `RandomGenerator` và `SecureRandom` cho phép chọn khoảng mà không cần tự lấy modulo.

### 8.1. Tránh modulo bias

Không nên viết:

```java
int value = random.nextInt() % 10;
```

Phép modulo không tạo phân bố đều nếu số lượng giá trị đầu vào không chia hết cho 10; kết quả còn có thể âm. Dùng:

```java
int value = random.nextInt(10);
```

Đối với token hoặc mã xác minh, hãy gọi bound method trên `SecureRandom`, không phải generator thông thường.

### 8.2. Tránh lỗi với Math.abs

Không dùng `Math.abs(random.nextInt()) % bound` để tạo số không âm. `Math.abs(Integer.MIN_VALUE)` vẫn là số âm do giới hạn biểu diễn của `int`. Dùng `nextInt(bound)` hoặc `nextInt(origin, bound)` để thể hiện rõ khoảng cần lấy.

## 9. Seed và khả năng tái lập

Seed xác định trạng thái khởi đầu của PRNG. Với generator phục vụ mô phỏng, seed cố định giúp tái tạo kết quả:

```java
SplittableRandom first = new SplittableRandom(12345L);
SplittableRandom second = new SplittableRandom(12345L);

for (int i = 0; i < 3; i++) {
    System.out.println(first.nextLong() == second.nextLong());
}
```

Nếu hai generator dùng cùng implementation và seed, đồng thời được gọi theo cùng trình tự, kết quả tương ứng sẽ giống nhau.

Với mô phỏng dài hạn, hãy lưu:

- Tên thuật toán/generator.
- Seed và cách tạo seed.
- Phiên bản JDK hoặc runtime nếu cần tái lập qua nhiều môi trường.
- Cấu trúc chia generator cho các task song song.
- Thứ tự và số lần gọi các phương thức sinh số.

### 9.1. Không dùng seed cố định cho dữ liệu bảo mật

Không khởi tạo `SecureRandom` bằng timestamp, counter, ID người dùng hoặc một seed cố định được commit trong mã nguồn. Điều đó có thể làm giảm khả năng chống dự đoán mà provider cung cấp.

`SecureRandom.setSeed()` có ngữ nghĩa bổ sung seed vào trạng thái của generator; nó không phải API để đặt lại một chuỗi giả ngẫu nhiên có thể tái lập như `SplittableRandom`. Trong mã ứng dụng thông thường, hãy để provider tự khởi tạo nguồn entropy và không gọi `setSeed()` bằng dữ liệu dễ đoán.

## 10. Kiểm thử logic có sử dụng ngẫu nhiên

Tách thuật toán khỏi nguồn sinh số giúp test có thể tái lập. Với logic không bảo mật, nhận `RandomGenerator` qua tham số:

```java
static int chooseBucket(RandomGenerator random, int bucketCount) {
    return random.nextInt(bucketCount);
}
```

Trong test:

```java
RandomGenerator testRandom = new SplittableRandom(1234L);
int bucket = chooseBucket(testRandom, 8);
```

Seed cố định giúp test điều tra lỗi dễ dàng. Nếu cần kiểm tra phân bố, hãy dùng kiểm thử thống kê phù hợp và tránh kỳ vọng một chuỗi kết quả cụ thể cho mọi thuật toán.

Đối với chức năng bảo mật, giữ ranh giới rõ ràng với `SecureRandom`. Không thay `SecureRandom` bằng `SplittableRandom` chỉ để test dễ tái lập trong production. Có thể inject một abstraction riêng trong test, nhưng API production phải bảo đảm không thể vô tình cấu hình nguồn không an toàn.

## 11. Hiệu năng và quản lý vòng đời

Việc chọn generator ảnh hưởng đến throughput và contention:

- `ThreadLocalRandom` phù hợp cho các phép sinh số đơn giản trên nhiều thread độc lập.
- `SplittableRandom` phù hợp với mô hình chia generator cho từng nhánh tính toán.
- `Random` an toàn luồng nhưng một instance dùng chung có thể trở thành điểm contention.
- `SecureRandom` có chi phí phụ thuộc provider, algorithm và nguồn entropy; tái sử dụng instance do ứng dụng quản lý thường hợp lý hơn tạo mới liên tục.

Đừng tối ưu bằng cách thay `SecureRandom` bằng PRNG thông thường ở ranh giới bảo mật. Nếu cần cải thiện hiệu năng, đo đúng workload, kiểm tra provider và cân nhắc cách quản lý instance mà vẫn giữ nguyên yêu cầu bảo mật.

## 12. Ma trận lựa chọn

| Nhu cầu | Lựa chọn phù hợp | Không nên dùng |
|---|---|---|
| Mô phỏng cần seed cố định | `SplittableRandom` hoặc generator được chọn qua `RandomGeneratorFactory` | `SecureRandom` nếu không cần bảo mật và cần tái lập |
| Nhiều thread sinh số cho jitter hoặc lựa chọn thông thường | `ThreadLocalRandom.current()` | Chia sẻ generator không phù hợp giữa mọi thread |
| Tính toán song song cần generator con | `SplittableRandom.split()` | Dùng chung một `SplittableRandom` đồng thời |
| Token, session ID, reset link | `SecureRandom.nextBytes()` | `Random`, `ThreadLocalRandom`, `SplittableRandom` |
| OTP hoặc mã xác minh | `SecureRandom.nextInt(bound)` | Timestamp, counter hoặc modulo từ PRNG thường |
| Salt, nonce hoặc challenge | `SecureRandom` kết hợp quy tắc của thuật toán | Tự tạo seed hoặc dùng `Math.random()` |
| Khóa mật mã | API JCA/JCE như `KeyGenerator` với cấu hình phù hợp | Tự ghép số ngẫu nhiên thành khóa không đúng độ dài/thuật toán |

## 13. Checklist bảo mật

- Xác định giá trị có phải bí mật hoặc có ảnh hưởng đến quyền truy cập không.
- Dùng `SecureRandom` cho token, session ID, OTP, salt, nonce và challenge bảo mật.
- Không dùng `Random`, `ThreadLocalRandom`, `SplittableRandom` hoặc `Math.random()` cho bí mật.
- Không tự seed `SecureRandom` bằng timestamp, counter hoặc giá trị dễ đoán.
- Dùng `nextBytes()` hoặc bound method của `SecureRandom`; tránh modulo bias.
- Chọn độ dài token theo yêu cầu bảo mật và lưu trữ token an toàn.
- Với OTP, bổ sung expiry, rate limit và giới hạn số lần thử.
- Với nonce, tuân thủ yêu cầu uniqueness của thuật toán và khóa đang dùng.
- Không log token, secret hoặc vật liệu khóa.
- Kiểm tra provider/algorithm và đo hành vi trên môi trường triển khai.
- Tái sử dụng generator theo hợp đồng thread-safety; không chia sẻ implementation không thread-safe giữa các thread.

## 14. Nguyên tắc thiết kế

- Dùng `RandomGenerator` và các implementation PRNG cho mô phỏng, test và lựa chọn không nhạy cảm.
- Dùng seed cố định khi cần tái lập, đồng thời ghi nhận thuật toán và cấu hình.
- Dùng `ThreadLocalRandom` cho tác vụ đồng thời không yêu cầu bảo mật hoặc seed riêng.
- Dùng `SplittableRandom` và `split()` khi chia công việc mô phỏng song song.
- Dùng `SecureRandom` cho mọi giá trị cần khó dự đoán trước đối thủ.
- Không suy ra tính bảo mật chỉ từ interface `RandomGenerator` hoặc vẻ ngoài ngẫu nhiên của chuỗi kết quả.
- Dùng bound method để sinh số trong khoảng; không tự modulo hoặc `Math.abs`.
- Không tự seed `SecureRandom` bằng dữ liệu yếu và không gọi `getInstanceStrong()` theo thói quen mà chưa kiểm tra yêu cầu/provider.
- Tách nguồn ngẫu nhiên phục vụ test khỏi nguồn ngẫu nhiên bảo mật trong thiết kế dependency.

Chọn nguồn ngẫu nhiên đúng bắt đầu từ câu hỏi: kết quả có cần tái lập hay phải chống dự đoán? PRNG như `SplittableRandom` và `ThreadLocalRandom` phù hợp cho mô phỏng và tính toán; `SecureRandom` dành cho dữ liệu bảo mật. Phân biệt rõ hai mục tiêu giúp chương trình vừa dễ kiểm thử, vừa không làm suy yếu các giá trị bí mật.

## Tài liệu tham khảo

- [Java SE 21 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGenerator.html): abstraction chung cho các bộ sinh số giả ngẫu nhiên.
- [Java SE 21 API — `RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): lựa chọn và khởi tạo thuật toán RandomGenerator.
- [Java SE 21 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SplittableRandom.html): generator có khả năng split cho tính toán song song.
- [Java SE 21 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator gắn với thread hiện tại.
- [Java SE 21 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): bộ sinh ngẫu nhiên mật mã, provider và strong algorithm.
- [Java SE 21 API — `UUID`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html): `randomUUID()` cho UUID ngẫu nhiên.
- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): hệ API RandomGenerator và các thuật toán PRNG hiện đại.
