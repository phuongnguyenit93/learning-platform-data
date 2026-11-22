# DrbgParameters: độ mạnh, khả năng dự báo và tái cấp seed

`java.security.DrbgParameters` được bổ sung trong Java 9 để cấu hình và quan sát một **DRBG** (*Deterministic Random Bit Generator*) thông qua `SecureRandom`. Ba vấn đề chính là: **security strength** (độ mạnh bảo mật), **prediction resistance** (khả năng kháng dự đoán sau nguy cơ lộ trạng thái nhờ entropy mới) và **reseed** (tái cấp entropy cho trạng thái). Các API này vẫn được sử dụng trong Java hiện đại; ví dụ dưới đây chạy trên Java 17+.

Bài tập không xây dựng thuật toán mật mã mới. Ta học cách nói rõ yêu cầu với security provider, kiểm tra những gì provider thực sự cấp, tạo bytes mật mã đúng cách và biết lúc nào cần tái cấp seed.

## 1. DRBG và vai trò của entropy

DRBG sinh ra dãy bit bằng một thuật toán mật mã và **trạng thái nội bộ**. Trạng thái được khởi tạo nhờ seed hình thành từ nguồn **entropy** của provider. “Deterministic” nghĩa là nếu kẻ tấn công biết đầy đủ trạng thái và thuật toán thì quá trình sinh bit có tính xác định; nhờ trạng thái khó đoán và cơ chế mật mã, output vẫn có thể an toàn cho các mục đích như token, khóa hoặc nonce khi được triển khai đúng.

```text
Entropy của provider ──► Instantiate ──► Trạng thái DRBG
                              ▲                 │
               strength / capability            ├──► Generate/nextBytes ──► bytes
               / personalization                │         ▲
                                                │    additional input
                        Reseed ◄── entropy mới ──┘
                           ▲
                      additional input
```

Ba thành phần không tương đương:

- **Entropy**: tính bất định không thể đoán trước của đầu vào từ nguồn ngẫu nhiên đáng tin; chất lượng nguồn do provider/hệ thống quyết định.
- **Seed và trạng thái**: dữ liệu để khởi tạo/cập nhật DRBG; một mảng 32 byte không tự chứng minh có 256 bit entropy.
- **Output**: dãy bytes mà `SecureRandom.nextBytes(...)` yêu cầu. Kích thước output **khác** security strength.

`SecureRandom` là API Java dùng cho ngẫu nhiên có tính bảo mật; DRBG là một kiểu triển khai của API đó. Không phải mọi đối tượng `SecureRandom` đều hỗ trợ `DrbgParameters`.

## 2. Ba factory method của `DrbgParameters`

| Mục đích | Phương thức | Thao tác sử dụng |
| --- | --- | --- |
| Khởi tạo DRBG | `instantiation(int strength, Capability capability, byte[] personalizationString)` | `SecureRandom.getInstance("DRBG", params)` |
| Sinh ngẫu nhiên theo yêu cầu mỗi lần | `nextBytes(int strength, boolean predictionResistance, byte[] additionalInput)` | `random.nextBytes(output, params)` |
| Tái cấp trạng thái từ entropy mới | `reseed(boolean predictionResistance, byte[] additionalInput)` | `random.reseed(params)` |

Chúng lần lượt trả về `DrbgParameters.Instantiation`, `DrbgParameters.NextBytes` và `DrbgParameters.Reseed`, đều thuộc họ `SecureRandomParameters`. Đây là cấu hình cho hoạt động, không phải thuật toán DRBG.

Ví dụ tối giản (đoạn code bên trong phương thức khai báo `throws NoSuchAlgorithmException` và có các import tương ứng):

```java
SecureRandom random = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                128, DrbgParameters.Capability.RESEED_ONLY, null));

byte[] bytes = new byte[32];
random.nextBytes(bytes, DrbgParameters.nextBytes(-1, false, null));
random.reseed(DrbgParameters.reseed(false, null));
```

Một số runtime/provider không hỗ trợ thuật toán `"DRBG"` hoặc tổ hợp tham số đó; lúc này khởi tạo có thể thất bại với `NoSuchAlgorithmException`. Đó là một điều kiện triển khai cần xử lý, không phải cớ để tự động hạ chính sách an toàn.

## 3. Security strength: 128 bit không phải 128 byte

Độ mạnh bảo mật biểu thị cấp bảo vệ mật mã mà DRBG có thể cung cấp, tính bằng **bit**. Nó không phải độ dài output hay độ dài khóa thành phẩm.

```java
DrbgParameters.Instantiation request =
        DrbgParameters.instantiation(
                128, DrbgParameters.Capability.RESEED_ONLY, null);
```

Lệnh trên yêu cầu **ít nhất 128 bit strength**. Provider có thể trả DRBG mạnh hơn yêu cầu (ví dụ 256 bit), nhưng không được âm thầm trả thấp hơn mức tối thiểu nếu lệnh khởi tạo có tham số thành công.

Ý nghĩa của `-1` phụ thuộc thao tác:

| Vị trí | Giá trị `-1` |
| --- | --- |
| `instantiation(-1, ...)` | Không yêu cầu mức cụ thể; chọn mặc định của provider |
| `nextBytes(-1, ...)` | Dùng strength hiệu lực đã khởi tạo |
| `reseed(...)` | Không có đối số strength |

Giá trị nhỏ hơn `-1` không hợp lệ. `nextBytes(new byte[32])` chỉ khẳng định cần **32 bytes output**, không chứng minh DRBG có strength 256 bit. Nếu nghiệp vụ yêu cầu 256-bit security, hãy yêu cầu và kiểm tra mức tương ứng tại khởi tạo; đừng suy luận từ mảng byte.

Mức nên chọn dựa trên chính sách và mô hình đe dọa của hệ thống. Không cần cố chọn 256 cho mọi ứng dụng nếu provider/chính sách đã được xác định ở 128; cũng không được giảm xuống 128 khi hợp đồng bảo mật bắt buộc 256.

## 4. `Capability`: ba mức yêu cầu

`DrbgParameters.Capability` có ba giá trị:

| Capability | Bảo đảm reseed? | Bảo đảm prediction resistance? |
| --- | --- | --- |
| `NONE` | Không | Không |
| `RESEED_ONLY` | Có | Không |
| `PR_AND_RESEED` | Có | Có |

**Điểm tinh tế:** đây là **mức tối thiểu lúc yêu cầu**, không phải danh sách tính năng bị giới hạn. Provider có thể đáp ứng cao hơn mức yêu cầu.

```text
Yêu cầu NONE          ⇒ hiệu lực NONE / RESEED_ONLY / PR_AND_RESEED
Yêu cầu RESEED_ONLY   ⇒ hiệu lực RESEED_ONLY / PR_AND_RESEED
Yêu cầu PR_AND_RESEED ⇒ hiệu lực PR_AND_RESEED
```

Cơ chế hỗ trợ prediction resistance phải đồng thời hỗ trợ reseed. Để kiểm tra kết quả, dùng hai phương thức rõ nghĩa:

```java
DrbgParameters.Capability capability = effective.getCapability();

boolean reseedSupported = capability.supportsReseeding();
boolean prSupported = capability.supportsPredictionResistance();
```

`effective` ở đây là `DrbgParameters.Instantiation` lấy từ instance thực tế, xem phần 5. Không kiểm tra reseed bằng điều kiện `capability == RESEED_ONLY` vì `PR_AND_RESEED` cũng hỗ trợ reseed.

## 5. Yêu cầu đầu vào và thuộc tính hiệu lực

Khi khởi tạo:

```java
DrbgParameters.Instantiation request = DrbgParameters.instantiation(
        128, DrbgParameters.Capability.RESEED_ONLY, null);
SecureRandom random = SecureRandom.getInstance("DRBG", request);
```

`request` chứa **điều kiện tối thiểu**. `random.getParameters()` trả về **tham số hiệu lực** mà provider đã chọn và thường có thể khác `request`:

```java
SecureRandomParameters params = random.getParameters();

if (!(params instanceof DrbgParameters.Instantiation effective)) {
    throw new IllegalStateException("DRBG effective parameters missing");
}
if (effective.getStrength() < 128) {
    throw new IllegalStateException("Strength requirement not met");
}
if (!effective.getCapability().supportsReseeding()) {
    throw new IllegalStateException("Reseed requirement not met");
}
```

Đây là đoạn minh họa trong phương thức, cần import `java.security` tương ứng. Java 17 hỗ trợ cú pháp `instanceof` với biến `effective`. `getParameters()` có thể trả `null` với `SecureRandom` khác, vì thế không ép kiểu vô điều kiện.

Thuộc tính hiệu lực được xác định theo instance; có thể mạnh hơn điều kiện yêu cầu. Việc đòi `effective.getStrength() == 128` sẽ sai về ý nghĩa nếu provider cấp 256. Hãy so theo **ngưỡng tối thiểu**.

## 6. Prediction resistance là gì?

Theo mô hình DRBG trong NIST SP 800-90A, **prediction resistance** nhằm hạn chế khả năng dự đoán output tương lai khi trước đó trạng thái sinh ngẫu nhiên có nguy cơ bị lộ, bằng cơ chế đưa entropy mới vào thời điểm thích hợp. Mức bảo vệ thực tế còn phụ thuộc chất lượng entropy, cơ chế triển khai và mô hình tấn công. Không thể suy ra một DRBG an toàn tuyệt đối chỉ vì `Capability.PR_AND_RESEED` xuất hiện.

- `Capability.PR_AND_RESEED` lúc khởi tạo yêu cầu provider **có hỗ trợ** prediction resistance.
- `DrbgParameters.nextBytes(strength, true, additionalInput)` yêu cầu **prediction resistance cho lần sinh cụ thể**.
- Nếu instance chỉ hỗ trợ `RESEED_ONLY`, không thể giả định gọi với `true` sẽ được chấp nhận. Tham số vượt quá khả năng có thể bị từ chối.
- Yêu cầu PR có thể khiến provider phải đọc entropy mới cho thao tác đó, tăng độ trễ hoặc phụ thuộc nguồn entropy. Dùng theo chính sách an toàn thay vì mặc định bật ở mọi lời gọi.

**Khác với reseed thủ công:** gọi `reseed()` một lần không có nghĩa các lần sinh sau đó đều đang được yêu cầu PR riêng. PR mang ý nghĩa cho thao tác phát sinh output khi cờ tương ứng được đặt; reseed là một hoạt động cập nhật trạng thái.

Đối với DRBG, `nextBytes(byte[])` không truyền tham số sẽ dùng strength và cờ prediction resistance hiệu lực của lần khởi tạo. Muốn kiểm soát cờ ở **mỗi lần gọi**, hãy dùng overload có `DrbgParameters.NextBytes`.

## 7. Reseed cập nhật trạng thái như thế nào?

`SecureRandom.reseed()` yêu cầu provider lấy **entropy mới** và cập nhật trạng thái DRBG. Bản có tham số:

```java
random.reseed(
        DrbgParameters.reseed(
                false,
                "phase:rotate".getBytes(StandardCharsets.UTF_8)));
```

Đây là đoạn minh họa, đặt sau khi khởi tạo một DRBG có `supportsReseeding() == true`; cần import `StandardCharsets`. Giá trị `false` nghĩa là **không yêu cầu prediction resistance** cho hoạt động reseed đó. Mảng `"phase:rotate"` là **additional input** để phân biệt ngữ cảnh, không thay entropy provider.

Provider có thể tự reseed khi đạt giới hạn hoặc khi cơ chế DRBG yêu cầu. Chính sách reseed thủ công nên xuất phát từ mô hình đe dọa, đặc điểm nguồn entropy và vận hành, chứ không tự đặt quy tắc “sau mỗi 10 request” cho mọi ứng dụng. Lấy entropy có chi phí và trong một số môi trường có thể làm chậm thao tác.

So với `reseed()`, `setSeed(...)` nhận dữ liệu seed từ caller. Gọi `setSeed` **trước lần sinh đầu** có thể ảnh hưởng cơ chế tự nạp entropy của PRNG. Không dùng seed cố định hoặc timestamp để làm `SecureRandom` “tái lập được” trong code tạo bí mật. Nếu cần đầu ra xác định cho unit test, inject một test double hoặc abstraction ở tầng ứng dụng.

## 8. Chương trình Java 17+ hoàn chỉnh

Tạo file **`DrbgParametersDemo.java`**, lưu bằng UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.security.DrbgParameters;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.security.SecureRandomParameters;

public final class DrbgParametersDemo {
    private static final int REQUIRED_STRENGTH = 128;

    public static void main(String[] args) throws NoSuchAlgorithmException {
        // Đây là ngữ cảnh của instance, không phải nguồn entropy.
        byte[] personalization =
                "lesson:credentials:v1".getBytes(StandardCharsets.UTF_8);

        DrbgParameters.Instantiation requested =
                DrbgParameters.instantiation(
                        REQUIRED_STRENGTH,
                        DrbgParameters.Capability.RESEED_ONLY,
                        personalization);

        SecureRandom random = SecureRandom.getInstance("DRBG", requested);
        SecureRandomParameters params = random.getParameters();

        if (!(params instanceof DrbgParameters.Instantiation effective)) {
            throw new IllegalStateException("Expected DRBG parameters");
        }
        if (effective.getStrength() < REQUIRED_STRENGTH) {
            throw new IllegalStateException("Insufficient DRBG strength");
        }
        if (!effective.getCapability().supportsReseeding()) {
            throw new IllegalStateException("Reseed is required");
        }

        // -1 sử dụng strength hiệu lực, false không yêu cầu PR lần này.
        byte[] first = new byte[32];
        random.nextBytes(
                first,
                DrbgParameters.nextBytes(
                        -1,
                        false,
                        "issue:token".getBytes(StandardCharsets.UTF_8)));

        // Provider cung cấp entropy mới; additional input chỉ thêm ngữ cảnh.
        random.reseed(
                DrbgParameters.reseed(
                        false,
                        "phase:rotate".getBytes(StandardCharsets.UTF_8)));

        byte[] second = new byte[32];
        random.nextBytes(
                second,
                DrbgParameters.nextBytes(-1, false, null));

        if (first.length != 32 || second.length != 32) {
            throw new AssertionError("Unexpected output length");
        }

        // Không ghi bytes bảo mật vào log.
        System.out.println("PASS: DRBG strength and capability");
        System.out.println("PASS: generation and reseed");
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 DrbgParametersDemo.java
java DrbgParametersDemo
```

Nếu runtime có DRBG đáp ứng mức tối thiểu, stdout:

```text
PASS: DRBG strength and capability
PASS: generation and reseed
```

Mỗi lần chạy tạo ngẫu nhiên thực sự nên bytes ở `first` và `second` không cố định. Hai dòng `PASS` chỉ phản ánh **kiểm tra cấu hình và khả năng gọi API thành công**, không chứng nhận chất lượng entropy hay mức bảo mật của provider.

### Điều gì xảy ra trong từng bước?

1. `instantiation(128, RESEED_ONLY, personalization)` tạo yêu cầu tối thiểu; `"lesson:credentials:v1"` là context public.
2. `getInstance("DRBG", requested)` tìm provider đáp ứng các yêu cầu.
3. `getParameters()` kiểm tra strength và hỗ trợ reseed thực tế, không suy luận từ yêu cầu ban đầu.
4. `nextBytes(-1, false, ...)` sinh mảng 32 byte với strength hiệu lực, không yêu cầu PR cho lượt đó.
5. `reseed(false, ...)` yêu cầu provider tái cấp entropy cho trạng thái.
6. `nextBytes(-1, false, null)` sinh mảng thứ hai; chương trình không in secret và không khẳng định các mảng bắt buộc khác nhau.

**Điều kiện triển khai:** `"DRBG"` là tên thuật toán chuẩn, nhưng provider có thể vắng mặt hoặc không hỗ trợ tham số. `NoSuchAlgorithmException` là tín hiệu thiếu khả năng theo chính sách. Không tự động fallback sang `java.util.Random`.

## 9. Ví dụ khi bắt buộc mức 256 và PR

Đây là **đoạn minh họa bên trong phương thức** (cần import các lớp `java.security` và khai báo `throws NoSuchAlgorithmException`); chủ đích có thể thất bại trên provider không đáp ứng chính sách nghiêm ngặt:

```java
SecureRandom high = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                256, DrbgParameters.Capability.PR_AND_RESEED, null));

DrbgParameters.Instantiation actual =
        (DrbgParameters.Instantiation) high.getParameters();

if (actual.getStrength() < 256
        || !actual.getCapability().supportsPredictionResistance()) {
    throw new IllegalStateException("Required PR policy not available");
}

byte[] secret = new byte[32];
high.nextBytes(secret, DrbgParameters.nextBytes(256, true, null));
```

Khác với chương trình ở phần 8, ví dụ này yêu cầu 256 bit strength và PR cho thao tác sinh. Provider chỉ có 128/192 bit hoặc không hỗ trợ PR **không thể** được coi là đáp ứng. Nếu `getInstance` hoặc `nextBytes` thất bại, phải xử lý lỗi theo chính sách của hệ thống; không đổi `PR_AND_RESEED` thành `NONE` hoặc `true` thành `false` chỉ để tránh exception.

Một lời gọi có PR có thể lấy entropy mới nhiều hơn và chậm hơn. Đây là quyết định bảo mật/hiệu năng phải được đánh giá trên môi trường chạy thật; mạnh hơn về khai báo không tự chữa các lỗi lưu trữ secret, mất kiểm soát khóa, log nhạy cảm hoặc nguồn entropy yếu.

## 10. Personalization và additional input: khác seed

| Đầu vào | Được sử dụng khi nào? | Vai trò |
| --- | --- | --- |
| Entropy của provider | Instantiate/reseed | Nguồn khó đoán để bảo vệ trạng thái |
| `personalizationString` | Instantiate | Phân biệt ngữ cảnh, dịch vụ, mục đích hoặc instance |
| `additionalInput` | Generate/reseed | Đa dạng hóa trạng thái cho một thao tác |
| `byte[] output` | Generate | Vùng chứa bytes sinh ra, không phải seed |

Hai tham số kiểu mảng byte có thể để `null`. Factory `DrbgParameters` tạo bản sao nội dung mảng đã truyền để tránh thay đổi tham số ngoài ý muốn. Dùng UTF-8 khi chuyển chuỗi context sang bytes.

Tạo chuỗi `"2026-11-07"`, `"user123"`, `"instanceA"` hoặc timestamp làm `personalizationString` hay `additionalInput` **không biến chúng thành entropy bí mật**. Không dùng các chuỗi dễ đoán để thay thế entropy do provider quản lý. Không nhét password, khóa riêng hoặc token nhạy cảm vào tham số chỉ vì tưởng chúng sẽ tăng “strength” của DRBG. Độ mạnh hiệu lực gắn với cấu hình thuật toán và entropy thực tế, không bằng kích thước mảng mà người gọi cung cấp.

Nếu cần nhiều mục đích ngẫu nhiên, định nghĩa domain/context rõ ràng ở tầng ứng dụng; `personalizationString` có thể giúp phân biệt instance, nhưng nó không thay quy trình quản lý khóa và không được dùng làm bằng chứng chống trùng lặp token.

## 11. Lựa chọn provider và thuật toán

`SecureRandom.getInstance("DRBG", params)` yêu cầu **thuật toán SecureRandom** tên `"DRBG"` cộng với các tham số tối thiểu. Cơ chế DRBG bên trong (chẳng hạn Hash_DRBG, HMAC_DRBG hoặc CTR_DRBG), nguồn entropy và giới hạn hoạt động do provider quyết định. Không đồng nhất tên `"DRBG"` với một thuật toán hash, AES, chứng chỉ mật mã hoặc nguồn entropy cụ thể.

Trên JDK tham chiếu, provider SUN có thể điều khiển lựa chọn cơ chế qua security property `securerandom.drbg.config`. Đây là **chi tiết provider**, không phải cách cấu hình portable giữa các JVM. Không ghi cứng giả định provider để dạy API tổng quát.

Các trường hợp lỗi cần biết:

- `NoSuchAlgorithmException`: không có provider hỗ trợ tổ hợp `"DRBG"` và tham số yêu cầu.
- `IllegalArgumentException`: tham số factory không hợp lệ hoặc tham số generate/reseed không được provider chấp nhận.
- `UnsupportedOperationException`: một triển khai `SecureRandom` không hỗ trợ thao tác reseed tương ứng.
- `getParameters()` có thể trả `null` với các triển khai ngoài DRBG; phải kiểm tra kiểu trước khi dùng các accessor DRBG.

Để chẩn đoán môi trường, có thể ghi `random.getAlgorithm()`, `random.getProvider().getName()` và `effective.getStrength()`, `effective.getCapability()`. **Không** log seed, output dùng làm secret hoặc trạng thái DRBG.

`new SecureRandom()` và `SecureRandom.getInstanceStrong()` có thể đáp ứng một số chính sách cần randomness mật mã, nhưng không mặc nhiên trả DRBG có `DrbgParameters`. Nếu hệ thống bắt buộc tính năng DRBG cụ thể, hãy yêu cầu cụ thể và fail khi thiếu. Tuyệt đối không chuyển sang `Random`/`ThreadLocalRandom` cho dữ liệu bí mật.

## 12. Kiểm thử đúng hợp đồng và vận hành trên CI

Một test phù hợp kiểm tra **hành vi tích hợp**: provider thỏa điều kiện, strength hiệu lực đủ, capability phù hợp, thao tác sinh/reseed thực hiện được và đầu ra có kích thước mong muốn. Nó không xác nhận chất lượng mật mã bằng cách đếm số byte ngẫu nhiên hoặc chờ hai kết quả khác nhau.

| Mục tiêu | Assertion nên dùng | Tránh |
| --- | --- | --- |
| Độ mạnh tối thiểu | `effective.getStrength() >= 128` | `== 128` vì provider có thể cấp cao hơn |
| Reseed | `effective.getCapability().supportsReseeding()` | Chỉ so với `RESEED_ONLY` |
| PR | `supportsPredictionResistance()` trước khi yêu cầu `true` | Cố gắng `true` rồi âm thầm hạ về `false` |
| Byte sinh ra | Kiểm tra đủ kích thước và xử lý secret an toàn | So với một mảng byte cố định |
| Provider | Ghi nhận khả năng và xử lý `NoSuchAlgorithmException` | Tự thay provider bằng PRNG yếu |
| Lỗi thiếu entropy | Điều tra cấu hình, provider và nguồn entropy | Tạo seed giả từ timestamp/PID |

Một mô hình kiểm thử tốt có hai lớp:

1. **Unit test nghiệp vụ:** tách mã tạo secret qua interface hoặc thành phần inject được. Test double tạo bytes xác định để kiểm tra format, độ dài, nhánh lỗi mà không cần tác động tới DRBG thật.
2. **Integration/smoke test mật mã:** chạy trên JDK/provider thật của môi trường đích, thương lượng tham số yêu cầu và thực hiện thao tác cần thiết. Kiểm tra thành công hoặc fail rõ; không khẳng định “đạt chuẩn NIST” chỉ từ smoke test.

Đối với service chạy trong container/VM, đánh giá nguồn entropy của hệ điều hành, hành vi sau restore/snapshot, phương án reseed nếu chính sách yêu cầu và thời gian khởi tạo. Đừng giả định một kiểm thử laptop phản ánh chính xác môi trường production. Một provider có thể tự reseed khi giới hạn yêu cầu; không nên phát minh chu kỳ bắt buộc cho mọi provider.

## 13. Lỗi phổ biến và phương án đúng

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “32 byte đầu ra nghĩa là 256 bit strength” | Output length và strength khác nhau |
| “Yêu cầu NONE tức là phải cấm reseed” | NONE chỉ là mức tối thiểu được yêu cầu; effective có thể mạnh hơn |
| “RESEED_ONLY đồng nghĩa có prediction resistance” | Chỉ PR_AND_RESEED đảm bảo PR |
| “Đã reseed một lần thì mọi lượt sinh đều có PR” | PR là yêu cầu riêng theo thao tác, tùy capability |
| “Personalization là seed bảo mật” | Context không thay entropy |
| “Additional input dài 256 bit thì strength tăng 256 bit” | Mảng context không chứng minh entropy |
| “Mọi SecureRandom đều có DrbgParameters” | `getParameters()` có thể là null hoặc kiểu khác |
| “`getInstanceStrong()` chắc chắn là DRBG” | Nó chọn theo cấu hình provider, không bảo đảm cơ chế DRBG |
| “Phải reseed mỗi lần gọi” | Chính sách dựa vào provider, threat model và chi phí entropy |
| “`setSeed(1234)` giúp test DRBG đúng” | Seed cố định có thể ảnh hưởng bảo mật; dùng test double cho logic |
| “Hai token test khác nhau chứng minh RNG an toàn” | Thử vài output không kiểm định entropy/thuật toán |
| “Không có provider thì dùng `new Random()`” | Làm hạ yêu cầu mật mã; báo lỗi hoặc chọn giải pháp đúng chính sách |

## 14. Checklist áp dụng

- [ ] Có lý do rõ ràng để dùng DRBG (thay vì ngẫu nhiên mô phỏng).
- [ ] `strength` tối thiểu được xác định theo chính sách; hiểu `-1` và không nhầm bit với số bytes output.
- [ ] Chọn `Capability.NONE`, `RESEED_ONLY` hoặc `PR_AND_RESEED` theo yêu cầu thực sự.
- [ ] Khởi tạo bằng `SecureRandom.getInstance("DRBG", instantiation(...))` khi chính sách đòi DRBG.
- [ ] Xem `getParameters()` và kiểm tra strength, capability hiệu lực.
- [ ] Yêu cầu `predictionResistance=true` chỉ khi tính năng hỗ trợ và mô hình đe dọa cần.
- [ ] Có chính sách reseed theo provider; không dùng seed cố định, timestamp hay dữ liệu dễ đoán thay entropy.
- [ ] `personalizationString` và `additionalInput` được hiểu là context/diversity, không phải secret seed.
- [ ] Không log bytes bí mật; xử lý token/key theo vòng đời thích hợp.
- [ ] Test nghiệp vụ dùng thành phần thay thế; integration test chạy trên provider thực tế.
- [ ] Xử lý thiếu provider/entropy đúng yêu cầu, không hạ bảo mật âm thầm.

## Tài liệu tham khảo chính thức

- [Java SE 17 — DrbgParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DrbgParameters.html) — ba factory và ý nghĩa tham số.
- [Java SE 17 — Capability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DrbgParameters.Capability.html) — các mức năng lực và phương thức kiểm tra.
- [Java SE 17 — Instantiation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DrbgParameters.Instantiation.html) — tham số yêu cầu so với tham số hiệu lực.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) — `getInstance`, `nextBytes`, `getParameters` và `reseed`.
- [OpenJDK JEP 273](https://openjdk.org/jeps/273) — nền tảng thiết kế DRBG được đưa vào Java 9.
- [NIST SP 800-90A Rev. 1](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final) — thuật ngữ instantiate, generate, reseed và prediction resistance trong API Java.

**Điểm cần nhớ:** `DrbgParameters` cho phép **đàm phán và quan sát mức bảo vệ** của DRBG. Đề xuất tham số tối thiểu rõ ràng, xác nhận giá trị hiệu lực, phân biệt reseed và prediction resistance, rồi để provider xử lý entropy đúng cách. Cách dùng API đúng vẫn cần hạ tầng bảo mật và quản lý secret phù hợp.
