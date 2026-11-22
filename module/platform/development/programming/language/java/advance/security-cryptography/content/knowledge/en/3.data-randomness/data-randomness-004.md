# 3.4. Vai trò của entropy; phân biệt SecureRandom với Random và ThreadLocalRandom

## Mục tiêu học tập

Kết thúc bài, bạn sẽ hiểu **entropy** là gì, vì sao một bộ sinh “trông ngẫu nhiên” vẫn có thể bị dự đoán; biết phân biệt `java.util.Random`, `java.util.concurrent.ThreadLocalRandom` và `java.security.SecureRandom`; chọn đúng API cho secret/token, salt, IV/nonce, mô phỏng và tác vụ đa luồng; đồng thời sử dụng Java 17+ để tạo dữ liệu ngẫu nhiên an toàn theo đúng mục đích.

Đây là bài về **dữ liệu và ngẫu nhiên trong Java security-cryptography**. Việc gọi đúng generator là nền móng bảo mật, nhưng không tự thay thế mã hóa, quản lý khóa, xác thực, giới hạn thử hoặc kiểm tra quyền truy cập.

## 1. Tại sao “ngẫu nhiên” chưa chắc “an toàn”?

Một trò chơi cần xúc xắc công bằng. Một máy chủ lại cần reset token mà kẻ tấn công không đoán được, ngay cả khi biết nhiều token khác. Hai bài toán đều muốn phân bố có vẻ ngẫu nhiên, nhưng bài thứ hai có yêu cầu chống dự đoán mang tính đối kháng.

Giả sử một chương trình phát dãy `8, 1, 6, 3, 7, 2`. Chỉ nhìn sáu số, ta không thể biết nó đến từ nguồn vật lý, một PRNG có seed cố định hay danh sách hard-code. **Thống kê bề ngoài không đủ để xác nhận an toàn mật mã.** Khi adversary biết thuật toán hoặc đoán được seed/trạng thái, dãy có thể hoàn toàn dự đoán được dù histogram rất đẹp.

Thuật ngữ:

| Khái niệm | Ý nghĩa | Cạm bẫy |
| --- | --- | --- |
| **Entropy** | Mức bất định của nguồn dữ liệu, liên quan trực tiếp khả năng đoán một giá trị | Số ký tự và kích thước buffer không trực tiếp cho biết entropy |
| **Nguồn entropy** | Nguồn bất định thực sự, thường do hệ điều hành/nền tảng thu thập và xử lý | Timestamp, PID, hostname hoặc `System.nanoTime()` không bảo đảm khó đoán |
| **Seed** | Dữ liệu đầu vào khởi tạo trạng thái bộ sinh | Seed dài 256 bit nhưng lấy từ một timestamp vẫn dễ brute force |
| **PRNG** | Pseudo-random number generator: thuật toán xác định sinh nhiều giá trị từ seed/trạng thái | Phân bố tương đối đều không có nghĩa chống dự đoán |
| **CSPRNG/DRBG** | PRNG thiết kế cho mật mã; các bit đầu ra phải khó dự đoán khi trạng thái bí mật an toàn | Vẫn phụ thuộc cách seed, provider, trạng thái, chính sách reseed |
| **Salt** | Giá trị khác nhau giữa các lần băm/dẫn xuất, thường công khai | Salt không thay thế KDF/password hash có chi phí |
| **Nonce/IV** | Giá trị dùng trong một phép mật mã; yêu cầu uniqueness/unpredictability tùy thuật toán | Với AES-GCM, tái sử dụng nonce cùng khóa là lỗi rất nặng |
| **Secret token** | Giá trị mang quyền/khả năng xác thực | Cần **khó đoán**, giữ kín, có TTL/rotation/revocation |

### 1.1. Min-entropy: cách nhìn phù hợp với đối thủ đoán giá trị

Với biến ngẫu nhiên `X`, min-entropy định nghĩa theo xác suất của **giá trị dễ đoán nhất**:

```text
H_min(X) = -log₂(max_x P[X = x])
```

Nếu generator luôn trả lại cùng một số, `H_min = 0 bit`. Nếu mã sáu chữ số được chọn đều từ `000000` đến `999999`, không gian là một triệu giá trị và min-entropy tối đa xấp xỉ `log₂(1_000_000) = 19,93 bit`. Điều này giải thích vì sao OTP sáu số phải kết hợp giới hạn thử, thời hạn ngắn, chống replay và bảo vệ kênh truyền.

Một token gồm 32 byte ngẫu nhiên lý tưởng có **256 bit** dữ liệu không thể đoán khi được lấy từ nguồn thích hợp. Nhưng **32 byte đầu ra không chứng minh có 256 bit entropy mới được thu thập mỗi lần gọi**: nhiều CSPRNG sử dụng thuật toán mật mã để mở rộng một seed/trạng thái bí mật thành nhiều byte. Độ an toàn phụ thuộc seed ban đầu, thiết kế DRBG và môi trường.

Băm SHA-256 một timestamp sinh ra 256 bit *output* nhưng không tạo ra 256 bit entropy nếu timestamp dễ đoán. Mã hóa Base64/hex cũng chỉ thay cách hiển thị, không thêm thông tin bất định. Tạo 256 ký tự từ một `Random(42)` vẫn có seed đã biết.

### 1.2. Từ entropy đến số ngẫu nhiên ở ứng dụng

```text
OS/nguồn entropy
      │ đánh giá và xử lý nguồn
      ▼
seed bí mật (sức mạnh phụ thuộc entropy thực)
      │ khởi tạo
      ▼
CSPRNG / DRBG của security provider
      │ sinh nextBytes(...)
      ▼
byte để tạo token, salt, khóa, nonce...
```

Mô hình trên là khái niệm, không phải cam kết rằng JDK nào cũng dùng cùng thuật toán/hệ điều hành. Một DRBG có thể tiếp tục sinh số từ trạng thái mật mã giữa các lần reseed thay vì “đọc 32 byte entropy vật lý” với mỗi `nextBytes(32)`. Điều này **không** tự làm nó kém an toàn.

Phải tách hai câu hỏi: *nguồn entropy có khó đoán không?* và *thuật toán mở rộng seed có được thiết kế cho mật mã không?*. Kiểm tra một dãy bằng vài phép thống kê đơn giản không thể thay thế đánh giá hai lớp này.

## 2. Bảng so sánh ba API chính

| Thuộc tính | `Random` | `ThreadLocalRandom` | `SecureRandom` |
| --- | --- | --- | --- |
| Package | `java.util` | `java.util.concurrent` | `java.security` |
| Mục đích | Mô phỏng, dữ liệu ngẫu nhiên thông thường, test có thể tái lập | Số giả ngẫu nhiên hiệu quả cho công việc đa luồng | Dữ liệu khó dự đoán dùng trong bảo mật |
| Bản chất | Trong Java 17, lớp `Random` có LCG với seed 48 bit | Generator per-thread, triển khai có tối ưu cho concurrency | Engine qua `SecureRandomSpi` của security provider; có thể là DRBG |
| Khởi tạo | `new Random()`, `new Random(42L)` | `ThreadLocalRandom.current()` | `new SecureRandom()` |
| Seed cố định | Cùng seed + cùng chuỗi lời gọi → cùng dãy | Không hỗ trợ tự set seed qua `setSeed` | Không tự dùng seed yếu hoặc cố định trong production |
| Concurrent | Thread-safe nhưng instance chung có thể contention | Thiết kế giảm contention khi nhiều thread | Thread-safe; hiệu năng tùy provider/thuật toán |
| Có chống dự đoán mật mã? | **Không** | **Không** | **Có**, với triển khai và seed an toàn |
| Token/secret/API key | **Không dùng** | **Không dùng** | **Dùng** với độ dài, vòng đời và lưu trữ thích hợp |
| Trường hợp phù hợp | Game, đơn vị test, simulation | Parallel simulation, sampling, jitter không bí mật | Token, salt, IV/nonce, secret material |

**Quy tắc chọn:** nếu ai đó đoán được số tiếp theo sẽ làm mất quyền truy cập, lộ bí mật hoặc phá tính đúng của giao thức, dùng `SecureRandom`/API mật mã phù hợp. Nếu chỉ cần dữ liệu để phân bố tải, trò chơi hoặc test, `Random` và `ThreadLocalRandom` thường thích hợp hơn.

### 2.1. `Random`: tái lập là tính năng và cũng là giới hạn

JDK 17 quy định `Random` dùng seed 48 bit và công thức tuyến tính đồng dư (LCG). Hai instance được khởi tạo cùng seed, dùng cùng sequence phương thức, sẽ trả kết quả giống nhau. Điều đó giúp **reproducible simulation**, nhưng không chống được đối thủ suy ra trạng thái.

```java
import java.util.Random;

Random a = new Random(2026L);
Random b = new Random(2026L);
boolean same = a.nextInt(1_000) == b.nextInt(1_000);
// same là true vì cùng seed và cùng lời gọi.
```

Đây là đoạn minh họa để đặt trong method; ví dụ chạy độc lập ở mục 6. `new Random()` tự chọn seed nhưng vẫn **không bảo đảm an toàn mật mã**. `Math.random()` cũng không dùng để tạo secret.

`Random` instance thread-safe, tuy vậy nhiều thread dùng chung một instance có thể tranh chấp trạng thái và giảm throughput. Tối ưu hiệu năng thường dẫn đến `ThreadLocalRandom`; tối ưu bảo mật phải chọn `SecureRandom`.

### 2.2. `ThreadLocalRandom`: giảm contention, không tăng bảo mật

Dùng:

```java
import java.util.concurrent.ThreadLocalRandom;

int number = ThreadLocalRandom.current().nextInt(10, 20);
// Số trong [10, 20), giá trị cụ thể không cố định.
```

Mỗi lần cần số trong worker/thread hiện tại, hãy gọi `ThreadLocalRandom.current()` ở chính thread đó. Không giữ generator của thread A rồi chia cho thread B. API `setSeed(long)` của lớp này luôn ném `UnsupportedOperationException`; nếu cần seed reproducible, dùng thiết kế generator khác.

Một hiểu nhầm: property `java.util.secureRandomSeed=true` có thể khiến nguồn seed khởi tạo khác đi, nhưng **không biến thuật toán `ThreadLocalRandom` thành CSPRNG**. Mục đích của lớp vẫn là hiệu năng và phân bố phi mật mã.

Ứng dụng nên dùng lớp này cho mô phỏng song song, random delay/jitter không liên quan bí mật, sampling hoặc tạo dữ liệu giả. Không dùng nó cho reset token, mật khẩu, key, nonce cần bảo mật hay session ID.

### 2.3. `SecureRandom`: engine dành cho mật mã

`SecureRandom` kế thừa `Random` trong hệ phân cấp Java, nhưng **không sử dụng thuật toán LCG 48 bit của `Random` để tạo đầu ra mật mã**. Nó chuyển sang triển khai của security provider:

```java
import java.security.SecureRandom;

SecureRandom secure = new SecureRandom();
byte[] bytes = new byte[32];
secure.nextBytes(bytes);
```

`new SecureRandom()` chọn provider/algorithm dựa trên cấu hình runtime. Có thể in `secure.getAlgorithm()`, `secure.getProvider().getName()` để chẩn đoán nhưng không nên hard-code tên provider trên mọi máy.

`SecureRandom` bảo đảm thread safety ở lớp API: triển khai provider có thể thread-safe nội bộ, hoặc JDK đồng bộ hóa lời gọi. **Thread-safe không có nghĩa throughput luôn như nhau**; tùy provider, reseed và nguồn entropy, chi phí có thể khác nhau.

## 3. Seed và vòng đời `SecureRandom`: chỗ dễ sai nhất

### 3.1. Tự khởi tạo (self-seeding)

Một đối tượng `SecureRandom` sinh bằng constructor mặc định, khi lần đầu được dùng để lấy byte, thường để provider tự lấy nguồn entropy thích hợp. Ứng dụng chỉ cần:

```java
SecureRandom secure = new SecureRandom();
byte[] token = new byte[32];
secure.nextBytes(token);
```

**Đừng tự “giúp” nó bằng timestamp hay hằng số.** Theo tài liệu Java 17, với một `SecureRandom` dạng PRNG, gọi `setSeed` **trước lần `nextBytes` hoặc `reseed` đầu tiên** có thể khiến bước self-seeding không diễn ra. Lúc đó ứng dụng tự chịu trách nhiệm seed phải có đủ entropy.

```java
// SAI trong production: timestamp có thể bị đoán!
SecureRandom insecure = new SecureRandom();
insecure.setSeed(System.currentTimeMillis());
byte[] secret = new byte[32];
insecure.nextBytes(secret);
```

Đoạn trên là ví dụ **để nhận diện lỗi**, không phải hướng dẫn khởi tạo. Tương tự, `new SecureRandom(new byte[] {1, 2, 3})` với seed cố định không phải cách tạo token an toàn.

### 3.2. Các API liên quan và ranh giới sử dụng

Với dữ liệu bí mật thông thường, tạo một `SecureRandom` để provider tự seed và gọi `nextBytes(byte[])`. `generateSeed(int)` cung cấp seed material theo cơ chế của provider, không phải bước bắt buộc trước `nextBytes`. `setSeed(...)` nhận dữ liệu do caller cung cấp; nếu gọi bằng timestamp/seed yếu trước lần tự seed, kết quả có thể mất tính khó đoán. `reseed()` yêu cầu entropy mới nhưng có thể không được hỗ trợ hoặc phải chờ nguồn entropy.

`getInstanceStrong()` chọn theo security property `securerandom.strongAlgorithms`, còn `getInstance("DRBG")` yêu cầu engine DRBG nếu có provider hỗ trợ. Chúng không tự đồng nghĩa với tốc độ tốt hơn hoặc hoạt động không chặn. Bài 3.5 đào sâu seed/reseed và Bài 3.6 phân tích DRBG, cấu hình strong cùng phép đo độ trễ; ở đây chỉ cần nhớ **chọn `SecureRandom` cho secret, kiểm soát entropy, không tự seed bằng giá trị đoán được**.

### 3.3. Dùng chung và đo hiệu năng

`SecureRandom` hỗ trợ sử dụng từ nhiều thread; có thể chia sẻ instance được khởi tạo đúng. Không nên liên tục tạo instance chỉ vì nghĩ “mỗi constructor sẽ thêm entropy”. Nếu ứng dụng sinh số lượng token cực lớn, đo latency/throughput trên provider và OS thực, xác định chi phí initialization/locking trước khi quyết định tối ưu.

**Không** thay `SecureRandom` bằng `ThreadLocalRandom` chỉ để cải thiện tốc độ khi output phải giữ bí mật. Cũng không nhầm “nhiều thread” với “nhiều nguồn entropy độc lập”: thread confinement là vấn đề hiệu năng, còn cryptographic unpredictability là vấn đề bảo mật.

## 4. Ứng dụng entropy: token, key, salt, nonce và OTP

| Nhu cầu | Chọn gì | Lý do và điều kiện kèm theo |
| --- | --- | --- |
| Session ID, API key, reset token, bearer token | `SecureRandom.nextBytes`, encode Base64URL/hex | Cần chống đoán, bảo quản bí mật, TTL, rotation, revoke, kiểm quyền |
| CSRF token ngẫu nhiên | `SecureRandom`/framework bảo mật chuẩn | Không chỉ một số pseudo-random dễ đoán |
| AES/HMAC secret key | `KeyGenerator` hoặc cơ chế sinh khóa mật mã phù hợp | Phải quản lý lưu trữ, vòng đời, rotation và quyền truy cập |
| Password hashing salt | `SecureRandom`, salt riêng cho mỗi bản ghi | Salt thường công khai; phải dùng KDF/password hashing chuẩn và cost phù hợp |
| AES-GCM nonce/IV | Quy trình bảo đảm **không tái sử dụng cặp khóa–nonce** | Nonce có thể sinh ngẫu nhiên 12 byte trong giới hạn cho phép hoặc dùng counter được quản lý |
| OTP 6 chữ số | `SecureRandom.nextInt(1_000_000)` | Chỉ 1 triệu khả năng: cần TTL, rate limit, chống replay, khóa thử |
| Simulation/game/test | `Random(seed)` nếu cần lặp lại | Không yêu cầu secrecy |
| Parallel simulation/backoff | `ThreadLocalRandom.current()` | Tối ưu contention, không dùng cho secret |
| ID công khai | Chiến lược ID đáp ứng uniqueness, collision và quy mô | Public ID không tự mang quyền; không lấy bí mật của ID thay authorization |

### 4.1. Token dài không đồng nghĩa entropy cao

32 byte ngẫu nhiên lý tưởng = 256 bit dữ liệu, khi encode **Base64URL không padding** sẽ có 43 ký tự. **43 ký tự không tạo 43 × 6 bit entropy mới**. Nếu seed yếu hoặc token bị rò qua log, URL, cookie/storage hoặc analytics, string dài cũng không cứu được.

Token thực tế phải dùng HTTPS; thường cần thời hạn, bảo vệ trước replay và thu hồi. Trong hệ thống kiểm tra bearer token, bảo quản/lưu token an toàn (có thể lưu dạng digest phù hợp để giảm rủi ro lộ plaintext token trên server) và giới hạn thử khi cần. Không xem token chỉ là một “random integer”.

### 4.2. Salt và nonce khác secret key

**Salt**: tạo khác nhau giữa các tài khoản/lần dẫn xuất để chống bảng tính sẵn và tránh tình trạng hai user có cùng password tạo cùng hash với cùng tham số. Salt không cần bí mật; có thể lưu cạnh password hash. Nhưng không tự viết `SHA256(password + salt)` để thay KDF mạnh.

**Nonce/IV**: ràng buộc phụ thuộc thuật toán. Với AES-GCM, nonce 96 bit được dùng phổ biến; dữ liệu mã hóa cần nonce **duy nhất dưới cùng khóa**. Nếu sinh bằng 12 byte `SecureRandom`, vẫn có xác suất trùng khi số lượt tăng; phải kiểm giới hạn sử dụng hoặc dùng cơ chế quản lý nonce phù hợp với lượng dữ liệu. **`SecureRandom` không phải chứng minh nonce tuyệt đối không lặp**.

**Khóa**: bí mật, có độ mạnh theo thuật toán và được lưu/rotation đúng chính sách. Không biến timestamp hoặc mật khẩu người dùng thành raw AES key bằng hash rồi xem như có 256 bit entropy. Nếu đầu vào là password, dùng password-based KDF chuẩn và salt/cost.

### 4.3. Vì sao `nextInt(bound)` tốt hơn tự lấy modulo?

Khi lấy số giới hạn, dùng `secure.nextInt(1_000_000)` để lấy trong khoảng 0..999999. Tránh `secure.nextInt() % 1_000_000` vì có thể âm và phân bố lệch. Cách lấy range của JDK xử lý vấn đề chọn giá trị bounded theo API.

Ví dụ OTP sáu chữ số:

```java
import java.security.SecureRandom;
import java.util.Locale;

SecureRandom secure = new SecureRandom();
int number = secure.nextInt(1_000_000);
String otp = String.format(Locale.ROOT, "%06d", number);
```

Đây là **đoạn minh họa trong một method**, không phải chương trình đầy đủ. OTP có thể bắt đầu bằng `0`; cần giữ định dạng chuỗi và bổ sung TTL, số lần thử tối đa, một lần sử dụng.

## 5. Chọn đúng API trong các tình huống thường gặp

**A. Kiểm thử Monte Carlo phải tái lập.** Dùng `Random` với seed cố định và điều khiển thứ tự lời gọi; không dùng `SecureRandom` chỉ để làm test kết quả bất định khó tái hiện. Với simulation hiện đại có thể xét các PRNG khác của `java.util.random` (Java 17), nhưng **interface `RandomGenerator` không tự đảm bảo an toàn mật mã**.

**B. Nhiều worker xử lý sampling không bảo mật.** Dùng `ThreadLocalRandom.current()` ngay trong worker để giảm contention. Không ép `ThreadLocalRandom.setSeed`; nếu test song song cần lặp lại chính xác, thiết kế luồng PRNG có seed/stream phân chia rõ ràng.

**C. API server phát reset token.** Dùng `SecureRandom.nextBytes` với độ dài đủ lớn; encode truyền tải; lưu và so sánh an toàn; hết hạn sau khoảng thời gian phù hợp, dùng một lần và tránh log token.

**D. Sinh IV khi dùng AES-GCM.** Có thể dùng `SecureRandom` 12 byte trong chính sách giới hạn số bản mã; thiết kế chống reuse với cùng khóa. Randomness không thay thế invariant uniqueness.

**E. Phát mã PIN/OTP sáu chữ số.** Chọn `SecureRandom`, nhưng vì số lượng khả năng hữu hạn nhỏ cần rate limit, TTL, retry count, lockout/risk controls và chống replay. Không coi generator an toàn là đủ.

**F. Sinh UUID.** `UUID.randomUUID()` của Java dùng nguồn ngẫu nhiên mạnh cho UUID v4, có 122 bit ngẫu nhiên sau các bit version/variant. Nó phù hợp nhiều nhu cầu ID nhưng không mặc nhiên đáp ứng yêu cầu token 256 bit hoặc thay cơ chế phân quyền.

## 6. Chương trình Java 17+ chạy độc lập

Tạo file **`EntropyRandomDemo.java`**. Chương trình minh họa ba API, đồng thời **chỉ in kết quả có thể xác minh ổn định**, không in token/salt bí mật.

```java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;

public final class EntropyRandomDemo {
    private static final SecureRandom SECURE = new SecureRandom();

    private EntropyRandomDemo() {
        // Utility class for the example.
    }

    private static String newToken() {
        byte[] bytes = new byte[32];
        SECURE.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static void main(String[] args) {
        // Same Random seed and calls -> reproducible sequence.
        Random first = new Random(2026L);
        Random second = new Random(2026L);
        boolean sameSequence = true;
        for (int i = 0; i < 10; i++) {
            if (first.nextInt(1_000) != second.nextInt(1_000)) {
                sameSequence = false;
            }
        }

        // Efficient per-thread generator for non-security tasks.
        int sample = ThreadLocalRandom.current().nextInt(10, 20);
        boolean validRange = sample >= 10 && sample < 20;

        // Cryptographic generator for sensitive random bytes.
        byte[] salt = new byte[16];
        SECURE.nextBytes(salt);
        String token = newToken();
        byte[] decoded = Base64.getUrlDecoder().decode(token);

        System.out.println("randomRepeatable=" + sameSequence);
        System.out.println("threadLocalRangeValid=" + validRange);
        System.out.println("saltBytes=" + salt.length);
        System.out.println("tokenBytes=" + decoded.length);
        System.out.println("tokenChars=" + token.length());
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```shell
javac EntropyRandomDemo.java
java EntropyRandomDemo
```

Stdout kỳ vọng:

```text
randomRepeatable=true
threadLocalRangeValid=true
saltBytes=16
tokenBytes=32
tokenChars=43
```

Giải thích:

- `randomRepeatable=true` vì hai `Random` cùng seed và được gọi cùng chuỗi lệnh; không có giá trị int cụ thể được hard-code vào bài.
- `threadLocalRangeValid=true` vì `nextInt(10,20)` trả số trong `[10,20)`; chương trình không yêu cầu kết quả của generator là cố định.
- Salt thực tế dài 16 byte, token gốc dài 32 byte; Base64URL 32 byte không padding tạo chuỗi 43 ký tự.
- `SecureRandom` sinh byte mới mà không có caller-supplied seed. Không in byte bí mật và không dùng các kết quả ngẫu nhiên làm stdout cố định.
- Ví dụ mới mô tả cách tạo dữ liệu; nó chưa bao gồm password hashing, AES-GCM encryption hay hệ thống xác thực hoàn chỉnh.

## 7. Kết hợp `SecureRandom` với API mật mã chuẩn

Khi cần **khóa AES**, ưu tiên `KeyGenerator` của Java Cryptography Architecture thay vì tự phát minh cách ghép số:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

SecureRandom secure = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, secure);
SecretKey key = generator.generateKey();
```

Đoạn này **chưa độc lập**, cần đặt trong method có `throws Exception` hoặc xử lý checked exception và nhập các class đã nêu. Java 17 chuẩn hỗ trợ khóa AES 256 bit; provider/policy cụ thể vẫn có thể áp dụng điều kiện khác. Không xuất khóa ra log và phải có nơi lưu/rotation an toàn.

Với AES-GCM, có thể tạo nonce ví dụ:

```java
byte[] nonce = new byte[12];
secure.nextBytes(nonce);
// Chỉ dùng nonce một lần dưới cùng key khi mã hóa AES-GCM.
```

Dòng trên dùng biến `secure` của đoạn trước. Việc quản lý uniqueness, giới hạn số lượt và bảo vệ key không được thay bằng suy luận “nonce random nên chắc chắn không bao giờ trùng”.

Lưu ý: `SecureRandom` là nguồn dữ liệu; `KeyGenerator`, `Cipher`, `Mac`, `Signature` là các engine dùng dữ liệu đó theo giao thức/thuật toán tương ứng. Không dùng một generator thường cho các security engine cần độ khó đoán.

## 8. Vấn đề vận hành: provider, blocking và quan sát đúng

Để biết runtime sử dụng gì, có thể tạo file độc lập **`SecureRandomInfo.java`**:

```java
import java.security.SecureRandom;
import java.security.Security;

public class SecureRandomInfo {
    public static void main(String[] args) {
        SecureRandom rng = new SecureRandom();
        System.out.println("Algorithm: " + rng.getAlgorithm());
        System.out.println("Provider: " + rng.getProvider().getName());
        System.out.println("Strong candidates: " +
                Security.getProperty("securerandom.strongAlgorithms"));
    }
}
```

Chạy:

```shell
javac SecureRandomInfo.java
java SecureRandomInfo
```

**Stdout thay đổi theo JDK, hệ điều hành và cấu hình provider**, nên không bịa một tên thuật toán/provider cố định. Hãy kiểm việc sử dụng JDK được cập nhật, chính sách entropy, provider, yêu cầu compliance và latency/throughput đo trên môi trường thật.

Với container/VM snapshot, deployment nhiều bản sao và quy định HSM, cần threat model đối với nguồn entropy và trạng thái generator. Không tự thay bằng seed là container ID, hostname hoặc timestamp. Provider có thể giới hạn thuật toán, kiểm soát reseed và locking; đánh giá chúng dựa trên tài liệu và đo đạc, không dựa vào giả định rằng `getInstanceStrong()` luôn tốt hơn.

## 9. Lỗi thường gặp cần tránh

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `new Random(System.currentTimeMillis())` để làm reset token | Seed/time dễ suy đoán, thuật toán không chống dự đoán | Dùng `SecureRandom` |
| `Math.random()` rồi chuyển thành hex để làm API key | Không có cam kết cryptographic security | Sinh đủ random bytes bằng CSPRNG và encode |
| `ThreadLocalRandom` để tạo session ID | Per-thread và nhanh không đồng nghĩa an toàn | Dùng `SecureRandom`/framework bảo mật |
| `SecureRandom.setSeed(42L)` trước `nextBytes` | Seed yếu, có thể ngăn self-seeding | Để provider tự seed |
| `new SecureRandom(new byte[]{1,2,3})` | Seed biết trước, không đủ entropy | Dùng constructor mặc định và nguồn entropy chuẩn |
| Dùng `getInstanceStrong()` cho từng request | Có thể overhead/blocking, không chứng minh tốt hơn | Chọn provider theo chính sách và đo |
| Tự áp `x % n` | Có thể làm lệch phân bố và có kết quả âm | Dùng `nextInt(n)` với `n > 0` |
| Cắt token 256 bit còn vài ký tự | Làm giảm không gian đoán | Giữ đủ bytes/bit theo thiết kế |
| Kiểm “hai token bất kỳ phải khác” như một phép chứng minh entropy | Va chạm có xác suất > 0, test ngắn không chứng minh bảo mật | Test shape/contract và đánh giá RNG bằng phương pháp phù hợp |
| Dùng random nonce AES-GCM vô hạn với cùng khóa | Xác suất collision tăng theo số lần mã hóa | Quản lý nonce duy nhất và giới hạn/rotation khóa |
| Log token, key, seed hoặc salt kèm mật khẩu | Lộ dữ liệu nhạy cảm, vô hiệu hóa tính khó đoán | Log metadata tối thiểu, bảo vệ credential |
| Coi public ID như token phân quyền | ID đoán được không có nghĩa người đoán được quyền | Có authorization độc lập; token phải khó đoán nếu là bearer |

### Cách test đúng

Với `Random(seed)` dùng trong simulation, test có thể assert output sequence và seed ổn định. Với `SecureRandom`, nên kiểm contract: kích thước raw byte, Base64URL roundtrip, loại ký tự, quy trình hết hạn/thu hồi và bảo vệ secret. Không assert một token cố định và không coi vài phép đếm bit là chứng minh chất lượng nguồn entropy.

Nếu cần reproducible test cho logic phát token, thiết kế interface/adapter đầu vào cho test, nhưng đường production phải dùng `SecureRandom` được khởi tạo an toàn. Đặc biệt không đưa “seed test” vào production qua biến cấu hình nhầm lẫn.

## 10. Tổng kết thành quyết định thực hành

- **Cần ngẫu nhiên để mô phỏng và tái lập?** `Random(seed)`.
- **Cần tốc độ và ít contention trong xử lý song song không bảo mật?** `ThreadLocalRandom.current()`.
- **Cần ngẫu nhiên mà người khác không đoán được?** `SecureRandom` hoặc API mật mã tiêu chuẩn dùng CSPRNG.
- **Cần khóa, salt, token, nonce?** Chọn đúng primitive và ràng buộc cụ thể: khóa phải bí mật, salt nên riêng từng bản ghi, token cần TTL/anti-replay, nonce cần uniqueness theo thuật toán.
- **Cần tăng “entropy”?** Xem **nguồn**, seed và cách provider khởi tạo; không băm timestamp, không thêm Base64, không gọi `setSeed` bằng hằng số.
- **Cần đo độ mạnh?** Dùng threat model, bảo đảm nguồn entropy và thuật toán; kiểm tra thống kê trên output không đủ để chứng minh an toàn mật mã.

Bốn câu hỏi tự kiểm tra:

1. Vì sao `new Random(123L)` cho chuỗi giống nhau sau mỗi lần chạy, và tại sao điều đó tốt cho test nhưng xấu cho token? **Đáp:** Thuật toán xác định theo seed; tái lập test có lợi, nhưng kẻ tấn công có thể dự đoán output.
2. Một OTP sáu chữ số sinh bởi `SecureRandom` đã an toàn tuyệt đối chưa? **Đáp:** Chưa, vì chỉ có một triệu khả năng; phải giới hạn thử, thời hạn, chống replay và bảo vệ kênh.
3. Vì sao `SecureRandom.setSeed(System.nanoTime())` trước lần `nextBytes` là nguy hiểm? **Đáp:** Thời gian dễ suy đoán và có thể ngăn cơ chế tự lấy seed phù hợp.
4. Vì sao dùng `ThreadLocalRandom` trong 100 thread không tương đương có 100 CSPRNG? **Đáp:** Thiết kế per-thread giải quyết contention, không tạo cam kết chống dự đoán mật mã.

## Nguồn tham khảo

- [Java SE 17 – SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): self-seeding, `setSeed`, `reseed`, `getInstanceStrong`, thread safety và khả năng blocking.
- [Java SE 17 – Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): seed 48 bit, LCG, tái lập và cảnh báo không bảo mật.
- [Java SE 17 – ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): per-thread, `setSeed` không hỗ trợ và trường hợp sử dụng.
- [Java SE 17 – RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): giao diện chung từ Java 17; một implementation không mặc nhiên là CSPRNG.
- [NIST – Full Entropy Assumption of SP 800-90](https://www.nist.gov/publications/discussion-full-entropy-assumption-sp-800-90-series): vai trò của entropy và min-entropy trong việc đánh giá bộ sinh số ngẫu nhiên.