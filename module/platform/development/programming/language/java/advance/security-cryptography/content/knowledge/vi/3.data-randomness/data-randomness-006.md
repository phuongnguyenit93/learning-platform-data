# 3.6 getInstanceStrong, DRBG và khả năng chặn của nguồn ngẫu nhiên

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **entropy source**, **seed**, **CSPRNG/DRBG** và API `SecureRandom`; giải thích vì sao thuật toán sinh chuỗi giả ngẫu nhiên vẫn bảo mật khi được khởi tạo đúng.
2. Hiểu `SecureRandom.getInstanceStrong()` thực sự lựa chọn gì thông qua `securerandom.strongAlgorithms` và vì sao chữ “strong” không đồng nghĩa “không chặn” hoặc “phù hợp mọi tác vụ”.
3. Sử dụng `SecureRandom.getInstance("DRBG", DrbgParameters.instantiation(...))`, đọc strength/capability hiệu lực, phân biệt reseed với prediction resistance.
4. Xác định những lời gọi có thể **block** khi cần entropy, đo thời gian tạo và sinh byte đúng cách, lựa chọn giải pháp phù hợp cho hệ thống có yêu cầu latency.
5. Tránh các lỗi bảo mật thường gặp: seed dự đoán được, dùng `Random` cho token, cấu hình provider theo giả định, yêu cầu reseed/strong ở mọi request.

## 1. Nền tảng tối thiểu: entropy source, seed và DRBG

`SecureRandom` là engine API của JCA; provider quyết định cách triển khai và lấy entropy. **Entropy source** cung cấp tính bất định từ hệ điều hành/phần cứng; **seed/trạng thái** là bí mật khởi tạo; **CSPRNG/DRBG** mở rộng trạng thái bằng thuật toán mật mã thành byte khó dự đoán. “Deterministic” của DRBG mô tả phép sinh từ trạng thái, **không** đồng nghĩa đối thủ có thể đoán được trạng thái.

```text
Entropy source -> instantiate/reseed -> DRBG state -> nextBytes(...)
```

Sinh 32 byte không đồng nghĩa bảo đảm security strength 256 bit. `nextBytes` phát sinh byte dùng trong ứng dụng; `generateSeed` tạo seed material; `reseed` có thể bổ sung entropy từ provider; `setSeed` nhận dữ liệu caller và **không tạo entropy mới** từ timestamp hay PID. Trong bài này, trọng tâm riêng là **chọn strong/DRBG theo policy, đọc capability hiệu lực và đo được độ trễ do provider/entropy source**.

## 2. Ba cách lấy `SecureRandom` và ý nghĩa thực tế

| Cách lấy instance | Ai chọn triển khai? | Khi nên dùng | Điểm cần kiểm tra |
| --- | --- | --- | --- |
| `new SecureRandom()` | Provider mặc định theo cấu hình runtime | Hầu hết nhu cầu sinh byte ngẫu nhiên bảo mật trong ứng dụng | Thuật toán/provider thực tế và đặc tính latency trên môi trường đích |
| `SecureRandom.getInstanceStrong()` | Danh sách `securerandom.strongAlgorithms` trong **security properties** | Yêu cầu chính sách/ứng dụng cần triển khai được nền tảng đánh dấu strong | Thuật toán, provider, entropy source, startup/first-call latency và khả năng chặn |
| `SecureRandom.getInstance("DRBG", params)` | JCA tìm provider hỗ trợ service `SecureRandom.DRBG` và tham số tối thiểu | Cần khai báo strength, reseed hoặc prediction resistance có chủ đích | Runtime có provider DRBG không, capability thực tế có đáp ứng không |

Cả ba đều đưa về **API `SecureRandom`**. Sự khác biệt nằm ở cơ chế chọn implementation và các ràng buộc bổ sung; không nên mặc định rằng `getInstanceStrong()` mạnh hơn mọi DRBG, hoặc một DRBG nhất thiết không bao giờ block.

### 2.1 `getInstanceStrong()` không phải tên thuật toán

`getInstanceStrong()` (có từ Java 8) tra cứu property:

```java
String configured = java.security.Security.getProperty(
        "securerandom.strongAlgorithms");
```

Đoạn trên là **biểu thức minh họa** để dùng trong một phương thức Java; `Security.getProperty` đọc **security property**, không phải `System.getProperty` thông thường.

Property `securerandom.strongAlgorithms` chứa danh sách những thuật toán/provider mà bản phân phối Java xác định là phù hợp để sinh giá trị bảo mật quan trọng, ví dụ khóa tồn tại lâu dài. `getInstanceStrong()` dựa vào danh sách đó để lấy một implementation có sẵn. Đường đi logic:

```text
SecureRandom.getInstanceStrong()
       |
       v
Security.getProperty("securerandom.strongAlgorithms")
       |
       v
Tra danh sách thuật toán/provider được nền tảng cấu hình
       |
       v
SecureRandom engine + provider được chọn
       |
       v
nextBytes / generateSeed / reseed (hành vi tùy provider)
```

Một JDK có thể chọn provider gắn với cơ chế ngẫu nhiên của hệ điều hành; JDK khác có thể chọn thuật toán khác. Tên như `NativePRNGBlocking`, `Windows-PRNG` hay `DRBG` là **đặc thù của runtime**, không phải danh sách bắt buộc chung.

**Ranh giới quan trọng:** phương thức factory có thể trả về nhanh nhưng lần `nextBytes` đầu tiên lại phải lấy entropy. Nó cũng có thể tốn thời gian lúc khởi tạo. Không được dùng tên “Strong” để suy ra latency; phải kiểm tra provider và đo thực tế.

Java SE yêu cầu nền tảng cung cấp ít nhất một triển khai strong, nhưng `getInstanceStrong()` vẫn khai báo `NoSuchAlgorithmException` khi không lấy được thuật toán từ cấu hình/provider hiện có. Trong môi trường cấu hình bất thường, ứng dụng cần xử lý lỗi minh bạch, không âm thầm thay bằng bộ sinh không bảo mật.

### 2.2 `getInstance("DRBG")` yêu cầu một engine cụ thể

`SecureRandom.getInstance("DRBG")` yêu cầu một provider đăng ký thuật toán `DRBG` cho engine `SecureRandom`. Có thể đi xa hơn bằng overload nhận `SecureRandomParameters` để chỉ rõ yêu cầu:

```java
SecureRandom drbg = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                128,
                DrbgParameters.Capability.RESEED_ONLY,
                null));
```

Đây là **đoạn minh họa nhúng**; trong chương trình đầy đủ phải import `SecureRandom` và `DrbgParameters` (xem thực hành 2).

`128` là security strength **tối thiểu yêu cầu**, `RESEED_ONLY` yêu cầu có khả năng reseed, và `null` là không truyền personalization string. Nếu provider không đáp ứng yêu cầu, việc khởi tạo sẽ thất bại; không nên coi “DRBG” là thuật toán luôn có trên mọi Java runtime.

JDK dùng họ cơ chế theo NIST SP 800-90A như Hash_DRBG, HMAC_DRBG hoặc CTR_DRBG tùy provider/configuration. `DRBG` trong lời gọi `getInstance` là tên **SecureRandom service algorithm**, không trực tiếp chọn một cơ chế Hash/HMAC/CTR cụ thể. Muốn biết implementation thực tế, xem tài liệu provider và cấu hình môi trường.

## 3. Vòng đời DRBG: instantiate → generate → reseed

Một DRBG duy trì trạng thái nội bộ theo các pha:

1. **Instantiate:** nhận nguồn entropy và các tham số, thiết lập trạng thái bí mật. Có implementation khởi tạo lười, chỉ lấy entropy khi sinh byte lần đầu.
2. **Generate:** tạo byte từ trạng thái hiện có bằng `nextBytes`, cập nhật trạng thái; nếu không cần truy cập entropy thì thường nhanh hơn đọc entropy mới cho từng lần gọi.
3. **Reseed:** bổ sung entropy mới và làm mới trạng thái khi policy/giới hạn thuật toán hoặc yêu cầu ứng dụng cần. Bước này có thể cần chờ nguồn entropy.
4. **Prediction resistance (PR):** khi được yêu cầu và provider hỗ trợ, thao tác tạo byte có thể cần nguồn entropy mới để bảo vệ tốt hơn trước kịch bản lộ trạng thái trước đó. Không thể có PR thực chất chỉ bằng cách đặt cờ mà không có nguồn entropy đáng tin.

### 3.1 Capability: yêu cầu tối thiểu và tính năng hiệu lực

`DrbgParameters.Capability` có ba mức:

| Capability khi yêu cầu | Bảo đảm tối thiểu | Có thể làm gì? |
| --- | --- | --- |
| `NONE` | Không buộc hỗ trợ reseed hoặc PR | Triển khai vẫn *có thể* có khả năng tốt hơn yêu cầu |
| `RESEED_ONLY` | Hỗ trợ reseed | Có thể gọi `reseed(...)`; không đảm bảo hỗ trợ PR |
| `PR_AND_RESEED` | Hỗ trợ cả reseed và PR | Có thể yêu cầu prediction resistance khi generate/reseed |

**Đừng đồng nhất “requested” và “effective”.** Một provider có thể trả về capability cao hơn yêu cầu tối thiểu. Sau khi lấy instance, xem:

```java
var params = drbg.getParameters();
if (params instanceof DrbgParameters.Instantiation actual) {
    int effectiveStrength = actual.getStrength();
    boolean canReseed = actual.getCapability().supportsReseeding();
    boolean canRequestPR =
            actual.getCapability().supportsPredictionResistance();
}
```

Đây là **đoạn mã nhúng** trong phương thức đã có biến `SecureRandom drbg` và import `DrbgParameters`. Thông tin trả về mô tả thiết lập **thực tế** (theo hợp đồng API), không buộc giống hệt tham số lúc yêu cầu.

### 3.2 Các tham số dùng lúc generate và reseed

- `DrbgParameters.instantiation(strength, capability, personalizationString)`: cấu hình khi tạo DRBG; `strength = -1` có nghĩa dùng strength mặc định khi instantiation.
- `DrbgParameters.nextBytes(strength, predictionResistance, additionalInput)`: tham số cho *một lần* `nextBytes(bytes, params)`; `strength = -1` lấy strength hiệu lực. Cờ `predictionResistance=true` yêu cầu PR cho lần này, chỉ dùng khi implementation hỗ trợ.
- `DrbgParameters.reseed(predictionResistance, additionalInput)`: tham số cho `reseed(params)`; thao tác này đọc entropy theo cơ chế provider.
- `personalizationString` và `additionalInput` phục vụ phân biệt ngữ cảnh/đa dạng hóa trạng thái theo giao diện DRBG, **không thay thế nguồn entropy an toàn** và không phải “khóa bí mật” bắt buộc.

Nếu chỉ yêu cầu `RESEED_ONLY`, không được tự gọi `nextBytes(..., DrbgParameters.nextBytes(-1, true, ...))` rồi giả định provider sẽ hỗ trợ. Tăng yêu cầu capability/strength có thể khiến `getInstance` thất bại. Các thao tác reseed đặc biệt có thể làm tăng latency vì tiếp xúc nguồn entropy.

## 4. Vì sao và khi nào nguồn ngẫu nhiên có thể block?

**Block** nghĩa là thread gọi API phải chờ trước khi phương thức trả về; khác với “sinh byte CPU tốn vài mili giây”. Theo API Java 17, tùy implementation, **`nextBytes`, `generateSeed` và `reseed` đều có thể block trong lúc thu thập entropy**.

Ba tình huống thường gặp:

| Tình huống | Điều có thể diễn ra | Lưu ý |
| --- | --- | --- |
| Lần sử dụng PRNG đầu tiên | Tạo seed từ entropy source, có thể đợi | Thời gian `new SecureRandom()` ngắn chưa chứng minh `nextBytes` đầu tiên nhanh |
| `generateSeed(n)` hoặc explicit `reseed()` | Provider liên hệ nguồn seed/entropy | Không dùng `generateSeed` thay cho `nextBytes` một cách máy móc |
| Yêu cầu PR hoặc provider cần tự reseed | Nhu cầu entropy mới xuất hiện trong thao tác generate | `DRBG` không đồng nghĩa “không chặn”; policy và môi trường quyết định |

Các cơ chế OS được thảo luận phổ biến gồm `/dev/random` và `/dev/urandom` trên Unix-like, API ngẫu nhiên hệ điều hành trên Windows, thiết bị HSM hoặc provider phần mềm. **Không áp đặt quy tắc “`/dev/random` luôn block” hoặc “`/dev/urandom` luôn là cách sửa”**: hành vi đã thay đổi qua phiên bản kernel và cách provider tích hợp. Đọc cấu hình thực tế của JDK/OS rồi kiểm chứng bằng đo lường.

Với ứng dụng web hoặc worker có SLA, cần xét thêm:

- Khi **startup hoặc first use**, ứng dụng có thể đứng đợi entropy trước request đầu tiên.
- Nếu mỗi request tự tạo `getInstanceStrong()` hoặc `reseed()`, lượng truy cập entropy và độ trễ có thể tăng đáng kể.
- Nếu mọi thread dùng một đối tượng `SecureRandom`, Java bảo đảm **an toàn cho truy cập đa luồng**; tuy nhiên provider có thể đồng bộ nội bộ khiến contention, nên throughput/latency vẫn cần đo.
- Trong môi trường VM/container, sự phụ thuộc host, runtime image, provider và entropy source có thể khác hẳn máy phát triển. Quan sát thread dump và thời gian gọi thay vì kết luận dựa vào tên hệ điều hành.

**Không thể đảm bảo một API tạo secret luôn non-blocking trên mọi runtime.** Nếu nghiệp vụ có yêu cầu timeout, isolation và cơ chế backpressure, hãy thiết kế ranh giới xử lý từ đầu; việc hết thời gian chờ ở tầng caller không đảm bảo có thể ngắt ngay một thao tác native đang chờ entropy.

## 5. Thực hành 1: `getInstanceStrong` và token URL-safe

Chương trình tạo một token bằng `new SecureRandom()`, sau đó khám phá provider được chọn bởi `getInstanceStrong()`. **Nó không in giá trị token**, tránh đưa secret vào log.

Lưu file **`StrongRandomDemo.java`** (Java 17+):

```java
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.security.Security;
import java.util.Base64;

public class StrongRandomDemo {
    public static void main(String[] args) {
        String property = Security.getProperty("securerandom.strongAlgorithms");
        System.out.println("strong config present: " +
                (property != null && !property.isBlank()));

        SecureRandom defaultRandom = new SecureRandom();
        byte[] tokenBytes = new byte[32];
        defaultRandom.nextBytes(tokenBytes);
        String token = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(tokenBytes);

        System.out.println("token bytes: " + tokenBytes.length);
        System.out.println("token characters: " + token.length());
        System.out.println("default provider: " +
                defaultRandom.getProvider().getName());

        try {
            SecureRandom strong = SecureRandom.getInstanceStrong();
            byte[] sample = new byte[16];
            strong.nextBytes(sample);
            System.out.println("strong provider: " + strong.getProvider().getName());
            System.out.println("strong algorithm: " + strong.getAlgorithm());
            System.out.println("strong sample bytes: " + sample.length);
        } catch (NoSuchAlgorithmException e) {
            System.out.println("strong implementation unavailable");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StrongRandomDemo.java
java StrongRandomDemo
```

Ví dụ **một lần chạy thực tế** trên Windows/JDK có các provider tương ứng (các dòng provider/algorithm/phần cấu hình **có thể khác**):

```text
strong config present: true
token bytes: 32
token characters: 43
default provider: SUN
strong provider: SunMSCAPI
strong algorithm: Windows-PRNG
strong sample bytes: 16
```

Điểm có thể kiểm tra ổn định khi chương trình chạy thành công:

- `32` byte cho token; Base64URL không padding sinh **43 ký tự** từ 32 byte, bất kể giá trị byte thực tế.
- `strong.sample` dùng 16 byte nhưng không in byte mật mã.
- `default provider`, `strong provider` và `strong algorithm` **là dữ liệu runtime**, không nên đưa tên mẫu vào assertion portable.
- `NoSuchAlgorithmException` được xử lý riêng; nếu cấu hình strong thiếu, nhánh báo unavailable chạy thay vì chương trình bí mật chuyển sang `java.util.Random`.

Token 32 byte có **độ rộng 256 bit**, nhưng mức an toàn thực tế còn phụ thuộc chất lượng RNG/entropy và cách quản lý token. Với token phiên, cần thêm thời hạn, cơ chế thu hồi, bảo vệ khi truyền/lưu trữ và không log token.

**Đối chiếu:** `getInstanceStrong()` không bắt buộc để sinh mọi token. Một `SecureRandom` mặc định của môi trường đã được kiểm chứng là lựa chọn thông dụng; nếu chính sách yêu cầu provider cụ thể, hãy quy định rõ và thử nghiệm trên môi trường thật.

## 6. Thực hành 2: yêu cầu DRBG strength/reseed, đọc cấu hình hiệu lực

Chương trình này dùng **DRBG có hỗ trợ reseed**, phát sinh 32 byte, rồi chủ động reseed để thể hiện API. Trong sản phẩm thực tế, **không cần reseed thủ công ở mỗi request**; đây là thao tác dạy vòng đời.

Lưu file **`DrbgParametersDemo.java`** (Java 17+):

```java
import java.nio.charset.StandardCharsets;
import java.security.DrbgParameters;
import java.security.SecureRandom;

public class DrbgParametersDemo {
    public static void main(String[] args) throws Exception {
        DrbgParameters.Instantiation requested =
                DrbgParameters.instantiation(
                        128,
                        DrbgParameters.Capability.RESEED_ONLY,
                        "lesson-3.6-v1".getBytes(StandardCharsets.UTF_8));

        SecureRandom random = SecureRandom.getInstance("DRBG", requested);
        if (!(random.getParameters() instanceof DrbgParameters.Instantiation actual)) {
            throw new IllegalStateException("No effective DRBG parameters");
        }

        byte[] bytes = new byte[32];
        random.nextBytes(
                bytes,
                DrbgParameters.nextBytes(
                        -1, false, "operation-1".getBytes(StandardCharsets.UTF_8)));

        System.out.println("algorithm: " + random.getAlgorithm());
        System.out.println("strength >= 128: " + (actual.getStrength() >= 128));
        System.out.println("reseed supported: " +
                actual.getCapability().supportsReseeding());
        System.out.println("generated bytes: " + bytes.length);

        random.reseed(DrbgParameters.reseed(false, null));
        System.out.println("reseed: OK");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 DrbgParametersDemo.java
java DrbgParametersDemo
```

Khi runtime có provider `DRBG` đáp ứng strength và capability yêu cầu, ví dụ đầu ra đã kiểm tra:

```text
algorithm: DRBG
strength >= 128: true
reseed supported: true
generated bytes: 32
reseed: OK
```

**Vì sao các kết quả boolean bằng `true`?** Factory chỉ tạo thành công khi request tối thiểu được đáp ứng; `getParameters()` báo thiết lập hiệu lực. Ví dụ không giả định chính xác strength là 128 hoặc capability là `RESEED_ONLY`: provider có quyền báo mức cao hơn.

Giải mã từng tham số:

1. `128`: strength tối thiểu theo cơ chế DRBG, không phải “phát sinh đúng 128 bit”.
2. `RESEED_ONLY`: bảo đảm API reseed khả dụng; **không** xin prediction resistance.
3. `"lesson-3.6-v1"`: personalization string để tách ngữ cảnh, không phải secret seed.
4. `nextBytes(-1, false, "operation-1"... )`: dùng strength hiệu lực, không xin PR cho lần phát sinh; chuỗi additional input không tạo entropy mới.
5. `reseed(false, null)`: yêu cầu lấy entropy mới để cập nhật trạng thái; có thể block tùy nguồn entropy/provider.

Nếu provider thiếu `DRBG` hoặc không đáp ứng capability, `getInstance` có thể ném `NoSuchAlgorithmException`. Khi bài toán có chính sách bảo mật ràng buộc, **không im lặng giảm strength hoặc đổi qua RNG không mật mã** để chạy tiếp.

### 6.1 Khi thực sự yêu cầu prediction resistance

Một ứng dụng có thể yêu cầu:

```java
DrbgParameters.Instantiation strongRequest =
        DrbgParameters.instantiation(
                256,
                DrbgParameters.Capability.PR_AND_RESEED,
                null);
SecureRandom prDrbg = SecureRandom.getInstance("DRBG", strongRequest);

byte[] output = new byte[32];
prDrbg.nextBytes(output, DrbgParameters.nextBytes(-1, true, null));
```

Đây là **đoạn mã minh họa trong phương thức có import `SecureRandom`/`DrbgParameters`**, không phải file chạy độc lập. Nó **có thể thất bại** nếu provider không hỗ trợ strength 256/PR; khi thành công, cờ `true` yêu cầu prediction resistance cho lần generate này. Provider có thể phải lấy entropy mới và chặn thread trong quá trình thực hiện. Đừng tự suy ra PR được bảo đảm chỉ vì dữ liệu có 256 bit.

## 7. Thực hành 3: đo riêng thời gian tạo instance và phát sinh byte

Đo **constructor/factory**, **lần `nextBytes` đầu** và **lần kế** riêng biệt vì nhiều triển khai seed theo nhu cầu. Chương trình cho phép chạy mặc định hoặc thêm đối số `strong` để quan sát lựa chọn `getInstanceStrong()`.

Lưu file **`RandomLatencyProbe.java`**:

```java
import java.security.SecureRandom;

public class RandomLatencyProbe {
    public static void main(String[] args) throws Exception {
        long start = System.nanoTime();
        SecureRandom random =
                args.length > 0 && args[0].equals("strong")
                ? SecureRandom.getInstanceStrong()
                : new SecureRandom();
        long constructed = System.nanoTime();

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        long first = System.nanoTime();

        random.nextBytes(bytes);
        long second = System.nanoTime();

        System.out.println("algorithm: " + random.getAlgorithm());
        System.out.println("provider: " + random.getProvider().getName());
        System.out.printf("construct: %.3f ms%n",
                (constructed - start) / 1_000_000.0);
        System.out.printf("first nextBytes: %.3f ms%n",
                (first - constructed) / 1_000_000.0);
        System.out.printf("second nextBytes: %.3f ms%n",
                (second - first) / 1_000_000.0);
    }
}
```

Biên dịch và chạy (chạy `strong` **chỉ trên môi trường đã được phép thử và có thể chịu latency**):

```bash
javac --release 17 RandomLatencyProbe.java
java RandomLatencyProbe
java RandomLatencyProbe strong
```

Một lần chạy chế độ mặc định trên môi trường thử cho kết quả:

```text
algorithm: DRBG
provider: SUN
construct: 38.408 ms
first nextBytes: 18.310 ms
second nextBytes: 0.059 ms
```

**Tất cả tên provider và giá trị đo thay đổi theo JVM, OS, tải máy, JIT, entropy source và lần khởi động**. Đây là dữ liệu minh họa đã đo, tuyệt đối không phải benchmark hoặc ngưỡng bảo đảm. Lần thứ nhất chậm hơn có thể do seeding, class loading hoặc yếu tố khởi động khác; một phép đo **không chứng minh** nguồn entropy bị thiếu.

Khi chẩn đoán hệ thống thực, ghi lại:

- JVM/vendor/version, hệ điều hành và môi trường VM/container;
- `getAlgorithm()`, `getProvider().getName()` và security property liên quan;
- thời gian khởi tạo, lần phát sinh đầu tiên, các lần tiếp theo; nếu có reseed, đo riêng;
- tần suất, phân vị p95/p99, thread dump/điểm call stack lúc treo và tương quan với startup hoặc load.

Không dùng việc thay `/dev/random` bằng một đường dẫn khác hoặc thay đổi `java.security.egd` như “thuốc chữa” phổ quát: ý nghĩa cấu hình phụ thuộc implementation và có thể làm lệch chính sách entropy của hệ thống. Kiểm tra tài liệu provider/JDK và đánh giá bảo mật trước khi thay đổi.

## 8. Lựa chọn thực tế trong ứng dụng

| Nhu cầu | Điểm khởi đầu hợp lý | Điều phải tránh |
| --- | --- | --- |
| Session token, CSRF token, mã bí mật dùng một lần | `SecureRandom` của môi trường đã kiểm chứng; `nextBytes` đủ dài, encode an toàn | `Math.random()`, `java.util.Random`, seed từ thời gian, ghi secret vào log |
| Khóa có giá trị cao/tồn tại lâu dài | API sinh khóa chuyên dụng và chính sách RNG/provider rõ ràng; cân nhắc `getInstanceStrong()` nếu chính sách cần | Mặc định strong sẽ nhanh hoặc mọi runtime chọn giống nhau |
| Cần strength/capability DRBG cụ thể | `getInstance("DRBG", DrbgParameters.instantiation(...))`, kiểm tra effective parameters | Xin `PR_AND_RESEED` mà không đánh giá chi phí entropy/độ trễ |
| API latency thấp hoặc khởi động số lượng lớn | Đo trên runtime đích, khởi tạo có kiểm soát, tránh reseed/factory không cần thiết trong hot path | Hứa “non-blocking” chỉ vì thuật toán tên DRBG |
| HSM/FIPS/chính sách provider | Chọn provider được thẩm định qua cấu hình/overload, kiểm thử lỗi và lifecycle | Dựa vào tên provider chỉ xuất hiện trên máy phát triển |

### 8.1 Quản lý vòng đời và concurrency

Một đối tượng `SecureRandom` **an toàn khi được nhiều thread gọi** theo hợp đồng Java 17. Tuy nhiên nó có thể được provider đồng bộ bên trong, nên ứng dụng có throughput cao vẫn cần đo tranh chấp. Khởi tạo riêng ở mỗi request không tự tăng tính an toàn và có thể gây tăng chi phí khởi tạo/entropy.

Một pattern thông dụng là giữ `SecureRandom` thích hợp trong thành phần chuyên cấp random bytes, tiêm phụ thuộc vào những nơi cần; bảo đảm cấu hình RNG được kiểm thử sớm khi ứng dụng khởi động. Nếu chính sách yêu cầu strong/HSM, xử lý việc không khởi tạo được như một lỗi cấu hình/bảo mật có thể quan sát, thay vì tự fallback sang RNG không thích hợp.

### 8.2 Test thế nào khi đầu ra ngẫu nhiên?

- Unit test tập trung vào **định dạng, độ dài, điều kiện hợp lệ và cách xử lý lỗi**, không assert token có giá trị byte cố định.
- Có thể inject một nguồn byte giả lập trong kiểm thử thuần logic (không đi qua đường sinh secret thật); production luôn sử dụng `SecureRandom` phù hợp.
- Hai lần sinh byte có xác suất trùng rất nhỏ nhưng không **bảo đảm tuyệt đối khác nhau**; dùng test xác suất đơn lẻ như `assertNotEquals(a, b)` là không cần thiết cho hợp đồng API.
- Không gửi raw token, seed hoặc trạng thái RNG vào log/trace/test report. Nếu cần quan sát, ghi thông tin cấu hình và độ trễ, không ghi bí mật.

## 9. Lỗi thường gặp và cách sửa

1. **“`getInstanceStrong` luôn không chặn vì mạnh.”** Sai: nó chọn theo property, còn hành vi chặn phụ thuộc provider/nguồn entropy; hãy đo riêng creation và generate.
2. **“DRBG deterministic nên không bảo mật.”** Sai: DRBG mật mã cần seed không dự đoán được; “deterministic” mô tả bước sinh từ trạng thái, không đánh giá chất lượng seed.
3. **“Có 32 byte output tức 256-bit strength.”** Sai: phân biệt độ dài byte với strength đã được provider bảo đảm.
4. **“`setSeed(System.nanoTime())` giúp hết block và tăng entropy.”** Sai và có nguy cơ giảm an toàn, nhất là nếu seed được đưa vào trước khi provider tự seed. Để provider dùng entropy tin cậy.
5. **“Cứ yêu cầu PR/reseed mỗi request để an toàn nhất.”** Không đúng chung: nhu cầu entropy/latency có thể rất lớn; cần threat model và chính sách rõ.
6. **“Gọi `generateSeed(32)` thay cho `nextBytes` trong mọi use case.”** Sai: API seed material có thể có hành vi lấy entropy khác và không phải cách tối ưu phổ quát để cấp token.
7. **“Cùng Java 17 thì provider/algorithm/time giống nhau.”** Sai: bản phân phối, OS, cấu hình bảo mật và thiết bị quyết định lựa chọn thực tế.
8. **“Nếu thiếu DRBG/strong cứ fallback về `Random`.”** Không chấp nhận cho secret; cần xử lý lỗi hoặc chọn triển khai bảo mật được chính sách cho phép, có kiểm chứng.
9. **“Không biết code nào chặn thì đặt timeout là đủ.”** Timeout ở lớp gọi không nhất thiết ngắt được thao tác native/entropy đang chờ. Thiết kế thread budget, isolation, retry/backpressure và observability phù hợp.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `getInstanceStrong()` chọn thuật toán dựa vào đâu?  
Dựa vào property `securerandom.strongAlgorithms` và provider/algorithm hiện có của runtime, không phải dựa vào một thuật toán “Strong” chung của Java.

**Câu 2.** `nextBytes` của DRBG có nhất thiết truy cập OS entropy mỗi lần không?  
Không. Nó thường sinh từ trạng thái nội bộ sau instantiate; nhưng có thể truy cập entropy khi instantiate/reseed hoặc khi policy/PR yêu cầu.

**Câu 3.** Yêu cầu `RESEED_ONLY` bảo đảm điều gì?  
Ít nhất khả năng reseed, **không** bắt buộc prediction resistance; kiểm tra `getParameters()` để biết capability hiệu lực.

**Câu 4.** Muốn tìm nguồn của độ trễ `SecureRandom` ở production thì xem gì?  
Algorithm, provider, security property, JVM/OS, thời gian init/first/steady-state, lúc reseed và thread stacks; không kết luận chỉ từ một số đo.

**Câu 5.** Vì sao không tự `setSeed` bằng thời gian?  
Dữ liệu thời gian có entropy thấp/dễ đoán; lời gọi quá sớm còn có thể ngăn cơ chế tự seed của PRNG theo hợp đồng API.

Ghi nhớ mô hình: **entropy source → seed/reseed → trạng thái DRBG → `nextBytes`**, còn **`getInstanceStrong()` là cơ chế chọn triển khai theo chính sách nền tảng**. Một lựa chọn phù hợp cần cả an toàn mật mã, khả năng tương thích provider và độ trễ đã kiểm chứng trên môi trường thực.

## Tài liệu chính thức

- [Java 17 — SecureRandom API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cơ chế chọn instance, seed, thread safety và khả năng block.
- [Java 17 — DrbgParameters API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DrbgParameters.html): instantiate, nextBytes, reseed và cấu hình DRBG.
- [Java 17 — DrbgParameters.Capability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DrbgParameters.Capability.html): NONE, RESEED_ONLY và PR_AND_RESEED.
- [Java 17 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): kiến trúc SecureRandom/provider và cấu hình bảo mật.
- [NIST SP 800-90A Rev. 1](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final): cơ sở khái niệm về deterministic random bit generators.
