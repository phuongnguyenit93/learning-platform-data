# SecureRandom với cơ chế DRBG trong Java 9 và các JDK hiện hành

## 1. Vì sao ứng dụng cần DRBG?

Khi tạo **token xác thực**, khóa bí mật, nonce hoặc các giá trị không thể đoán trước, ứng dụng cần dữ liệu ngẫu nhiên có tính chất **mật mã học**. Một bộ sinh ngẫu nhiên cho mô phỏng hay trò chơi có thể cho phân bố số tốt nhưng vẫn dễ bị đoán trạng thái hoặc chuỗi đầu ra; tính chất đó không phù hợp với giá trị bảo mật.

Java cung cấp `java.security.SecureRandom` để lấy byte ngẫu nhiên mạnh về mặt mật mã. Từ **Java 9 (JEP 273)**, Java bổ sung cơ chế làm việc tường minh với **DRBG** (*Deterministic Random Bit Generator*) thông qua tên thuật toán chuẩn `"DRBG"` và lớp `java.security.DrbgParameters`. Các API này **vẫn hiện diện trong Java SE 27** và có thể sử dụng với các bản Java được hỗ trợ hiện nay.

Một DRBG tạo chuỗi bit bằng thuật toán xác định **sau khi được khởi tạo từ nguồn entropy**. Tính bảo mật đến từ việc seed/entropy không thể đoán được, thuật toán mật mã được thiết kế phù hợp và trạng thái nội bộ được quản lý đúng. Từ “deterministic” không có nghĩa đầu ra của một `SecureRandom` thực tế sẽ lặp lại trong những lần chạy mới; nó mô tả cách thuật toán phát sinh bit **khi đã cố định trạng thái ban đầu**.

Bài học giải quyết năm việc thiết yếu:

1. Phân biệt `SecureRandom`, DRBG và các bộ sinh số ngẫu nhiên thông thường.
2. Chọn `SecureRandom.getInstance("DRBG")` và yêu cầu khả năng cần thiết qua `DrbgParameters.instantiation`.
3. Đọc **tham số hiệu lực** mà provider thực sự cấp; hiểu strength, reseeding và prediction resistance.
4. Sinh token an toàn bằng Java 17+, bổ sung additional input và reseed khi có lý do.
5. Tránh các lỗi thực tế như seed đoán được, nhầm độ dài token với security strength hay tin rằng mọi provider đều có cùng cơ chế.

**Phạm vi:** API ngẫu nhiên mật mã của Java, đặc biệt là DRBG trong `SecureRandom`. Không đi sâu chứng minh thuật toán NIST hoặc triển khai bộ sinh bit riêng; trong ứng dụng, ta sử dụng JCA/JDK provider đã được kiểm chứng.

## 2. DRBG khác Random và SecureRandom thế nào?

| Khái niệm | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| `java.util.Random` | Mô phỏng, lấy mẫu, logic không có yêu cầu bảo mật | Không sử dụng để tạo token, password-reset link hoặc khóa bí mật |
| `ThreadLocalRandom` / `SplittableRandom` | Phân phối số hiệu quả cho xử lý thông thường | Không có hợp đồng bảo mật của `SecureRandom` |
| `SecureRandom` | Giao diện JCA để lấy dữ liệu ngẫu nhiên mạnh về mật mã | Provider chọn cơ chế cụ thể; không nhất thiết tên thuật toán là DRBG |
| `SecureRandom` với `"DRBG"` | Yêu cầu provider triển khai một DRBG | Có thể yêu cầu strength, khả năng reseed/prediction resistance |
| `DrbgParameters` | Đối tượng tham số cho DRBG trong `getInstance`, `nextBytes` và `reseed` | Không phải thuật toán tạo bit độc lập |

**`new SecureRandom()` vẫn là lựa chọn hợp lệ và an toàn cho rất nhiều trường hợp cần CSPRNG**; nó chọn một thuật toán từ danh sách provider của môi trường chạy. Chỉ chọn `"DRBG"` tường minh nếu ứng dụng cần khả năng của DRBG hoặc có yêu cầu quản trị/đánh giá liên quan đến triển khai đó.

Đừng suy ra rằng `new SecureRandom()` **luôn** là DRBG hay rằng `SecureRandom.getInstanceStrong()` **luôn** là DRBG. Phương thức `getInstanceStrong()` chọn theo thuộc tính bảo mật `securerandom.strongAlgorithms`, có thể lấy thuật toán/provider khác và đôi khi chờ nguồn entropy. Các lựa chọn này phải được kiểm chứng trên JDK, OS và provider thực tế.

### Mô hình ba bước

```text
Nguồn entropy khó đoán (do provider/hệ thống cung cấp)
              |
              v
      Instantiate / khởi tạo DRBG
              |
              v
      Trạng thái nội bộ mật mã
              |
              +---- generate/nextBytes ----> Byte ngẫu nhiên
              |
              +---- reseed (nếu hỗ trợ) <--- Entropy mới
```

Đầu ra `nextBytes` thông thường được tính từ trạng thái nội bộ của DRBG. `reseed` bổ sung entropy mới để làm mới trạng thái theo cơ chế do provider triển khai. **Không** tự tạo “seed” từ đồng hồ, số PID, mã người dùng hay chuỗi cố định rồi nghĩ rằng DRBG đã an toàn.

## 3. Các cơ chế DRBG và phần nào thuộc provider

NIST SP 800-90A mô tả nhiều cơ chế DRBG. Ba họ thường được nhắc tới:

- **Hash_DRBG:** phát sinh bit dựa trên hàm băm mật mã.
- **HMAC_DRBG:** sử dụng HMAC làm thành phần mật mã cốt lõi.
- **CTR_DRBG:** sử dụng block cipher ở chế độ counter, thường là AES.

Đây là **các họ cơ chế**; ví dụ `Hash_DRBG` đi với `SHA-256` hoặc `CTR_DRBG` đi với `AES-256` còn phụ thuộc triển khai. Còn **`"DRBG"` trong `SecureRandom.getInstance("DRBG")` là tên thuật toán JCA để chọn dịch vụ RNG**, không phải tên của riêng Hash_DRBG hay HMAC_DRBG.

Các lựa chọn về nguồn entropy, cơ chế DRBG, thuật toán băm/AES và giới hạn triển khai là trách nhiệm của **provider**. API `DrbgParameters` cho phép ứng dụng yêu cầu các tính chất như security strength, personalization và khả năng prediction resistance, **không** cung cấp một tham số Java portable để ép mọi provider chọn Hash_DRBG hoặc CTR_DRBG.

Trong **provider SUN của JDK tham chiếu**, `DRBG` hỗ trợ Hash_DRBG, HMAC_DRBG và CTR_DRBG; cấu hình cơ chế/thuật toán được kiểm soát qua **thuộc tính bảo mật** `securerandom.drbg.config`. Khi không cấu hình khác, tài liệu Java SE 27 mô tả lựa chọn mặc định của provider này là **Hash_DRBG với SHA-256**. Đây là ghi chú về **SUN provider**, không phải lời hứa cho mọi runtime.

**Phân biệt thuộc tính:** `securerandom.drbg.config` là Java **security property** (đọc bằng `Security.getProperty(...)`), không được coi là system property thông thường chỉ bằng cách thêm `-Dsecurerandom.drbg.config=...`. Muốn thay cấu hình của một JDK cụ thể phải tuân theo cách quản trị file `java.security` hoặc cơ chế nạp security properties được JDK đó hỗ trợ; nên đánh giá tác động trên toàn ứng dụng trước khi thay.

## 4. Tạo SecureRandom bằng DRBG

Cách ngắn nhất:

```java
SecureRandom drbg = SecureRandom.getInstance("DRBG");
byte[] data = new byte[32];
drbg.nextBytes(data);
```

Đoạn này **là trích đoạn dùng trong phương thức**, cần `import java.security.SecureRandom;`, ngoại lệ `NoSuchAlgorithmException` và context chương trình. Nó yêu cầu một provider có thuật toán `"DRBG"`. Nếu không có, `getInstance` ném `NoSuchAlgorithmException`: không được âm thầm thay bằng `Random`.

Khi cần yêu cầu rõ strength và khả năng, dùng overload có `SecureRandomParameters`:

```java
SecureRandom drbg = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                128,
                DrbgParameters.Capability.RESEED_ONLY,
                null));
```

Overload từ Java 9 nhận một `DrbgParameters.Instantiation`. Khi thành công, provider phải đáp ứng **ít nhất** mức strength và capability đã yêu cầu. Nếu không có provider phù hợp, có thể nhận `NoSuchAlgorithmException`. Provider **được phép cấp cao hơn** yêu cầu, do đó phải xem kết quả `getParameters()` để biết đặc tính thực tế.

**Lựa chọn strength:** số `128` là yêu cầu tối thiểu *security strength* theo bit, **không** phải yêu cầu tạo 128 bit đầu ra hay kích thước seed tự cấp. `256` yêu cầu sức mạnh tối thiểu 256 bit và có thể không được một số provider/cấu hình đáp ứng. Giá trị `-1` có nghĩa là để provider chọn strength mặc định, **không** có nghĩa là 0 bit bảo mật.

## 5. Hiểu đúng DrbgParameters và Capability

`DrbgParameters` có ba factory methods được dùng thường xuyên:

| Factory | Sử dụng ở đâu | Ý nghĩa tham số |
| --- | --- | --- |
| `instantiation(int strength, Capability cap, byte[] personalization)` | `SecureRandom.getInstance("DRBG", ...)` | Yêu cầu tối thiểu khi khởi tạo |
| `nextBytes(int strength, boolean pr, byte[] additionalInput)` | `SecureRandom.nextBytes(bytes, ...)` | Yêu cầu cho lần sinh byte cụ thể |
| `reseed(boolean pr, byte[] additionalInput)` | `SecureRandom.reseed(...)` | Tham số cho lần làm mới bằng entropy |

### 5.1. Ba mức Capability

| Capability yêu cầu | Cam kết tối thiểu khi `getInstance` thành công | Capability thực tế có thể nhận |
| --- | --- | --- |
| `NONE` | Không đòi reseeding hay prediction resistance | `NONE`, `RESEED_ONLY` hoặc `PR_AND_RESEED` |
| `RESEED_ONLY` | Có hỗ trợ reseeding | `RESEED_ONLY` hoặc `PR_AND_RESEED` |
| `PR_AND_RESEED` | Có cả reseeding và prediction resistance | `PR_AND_RESEED` |

Hai phương thức kiểm tra ý nghĩa này là:

```java
capability.supportsReseeding();
capability.supportsPredictionResistance();
```

- **Reseeding:** cho phép DRBG hấp thụ entropy mới để cập nhật trạng thái. Khả năng này hữu ích cho hệ thống chạy lâu hoặc theo chính sách bảo mật cần làm mới trạng thái.
- **Prediction resistance (PR):** yêu cầu cơ chế cung cấp entropy mới ở mức cần thiết khi sinh dữ liệu, nhằm hạn chế khả năng đoán đầu ra tiếp theo từ một trạng thái cũ bị lộ, theo mô hình bảo mật/khả năng của provider. Có thể tốn chi phí entropy và gây chờ; **không** nên tự động bật PR cho mọi lời gọi nếu không có yêu cầu.
- `NONE` là **mức khả năng yêu cầu tối thiểu**, không phải khẳng định đầu ra của DRBG không an toàn.

Hãy phân biệt “**provider hỗ trợ PR**” với “**lần gọi cụ thể có yêu cầu PR hay không**”. Một instance `PR_AND_RESEED` có thể gọi `nextBytes(bytes, DrbgParameters.nextBytes(-1, false, null))` để **không yêu cầu PR ở lời gọi đó**. Trái lại, instance chỉ hỗ trợ `RESEED_ONLY` không đáp ứng được `nextBytes(..., nextBytes(-1, true, ...))`.

### 5.2. Strength, personalization và additional input

- **Strength:** mức sức mạnh mật mã tính bằng bit, do cơ chế/provider cho phép. **Không đồng nhất** với độ dài `byte[]` đầu ra. Bạn có thể yêu cầu DRBG strength 128 bit rồi sinh chuỗi 32 byte; điều này **không** biến DRBG thành strength 256 bit.
- **Personalization string:** byte[] tùy chọn truyền lúc instantiate để phân biệt ngữ cảnh sử dụng (ví dụ `"password-reset/v1"` và `"session-token/v1"`). Nó **không thay thế nguồn entropy**, không cần phải bí mật và nên được mã hóa ổn định (thí dụ UTF-8).
- **Additional input:** byte[] tùy chọn truyền trong lúc generate/reseed để tăng tính phân biệt ngữ cảnh. Nó cũng **không thay thế seed/entropy an toàn**. Không dựa vào additional input để sửa một nguồn ngẫu nhiên yếu.
- `-1` trong `DrbgParameters.nextBytes(-1, ..., ...)` có nghĩa là dùng strength hiệu lực của instance; đây không phải yêu cầu một mức strength âm.

Các mảng byte trong đối tượng tham số được sao chép theo hợp đồng API. Khi cần xử lý dữ liệu bí mật trong luồng riêng, vẫn phải quản lý vòng đời của dữ liệu trong bộ nhớ ở mức ứng dụng.

## 6. Ví dụ hoàn chỉnh: sinh token ngẫu nhiên an toàn với DRBG

Ví dụ sau chạy với **JDK 17+** nếu provider có thuật toán `DRBG` đáp ứng yêu cầu tối thiểu. JDK tham chiếu thường cung cấp `SUN/DRBG`.

Tạo tệp **`DrbgTokenDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.DrbgParameters;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public class DrbgTokenDemo {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {

        SecureRandom random = SecureRandom.getInstance(
                "DRBG",
                DrbgParameters.instantiation(
                        128,
                        DrbgParameters.Capability.RESEED_ONLY,
                        "session-token/v1".getBytes(StandardCharsets.UTF_8)));

        byte[] secret = new byte[32];
        random.nextBytes(secret);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);

        DrbgParameters.Instantiation actual =
                (DrbgParameters.Instantiation) random.getParameters();

        System.out.println("algorithm=" + random.getAlgorithm());
        System.out.println("bytes=" + secret.length);
        System.out.println("tokenChars=" + token.length());
        System.out.println("strength>=128="
                + (actual.getStrength() >= 128));
        System.out.println("reseedSupported="
                + actual.getCapability().supportsReseeding());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 DrbgTokenDemo.java
java DrbgTokenDemo
```

Khi `getInstance` thành công theo đúng hợp đồng `DrbgParameters`, đầu ra của chương trình là:

```text
algorithm=DRBG
bytes=32
tokenChars=43
strength>=128=true
reseedSupported=true
```

**Giải thích kết quả:**

1. Bộ sinh được tạo với yêu cầu tối thiểu **128-bit security strength** và **phải hỗ trợ reseeding**. Provider có thể cung cấp strength/capability cao hơn.
2. `nextBytes(secret)` điền **32 byte**. Số byte là 256 bit dữ liệu biểu diễn; không nên nhầm với strength của cơ chế DRBG.
3. Base64 URL-safe bỏ padding chuyển 32 byte thành **43 ký tự**, thuận tiện đặt trong URL hoặc header. Token thật **khác nhau theo các lần chạy** trong hoạt động bình thường, nên ví dụ không in chuỗi token cố định.
4. `getParameters()` trả về các tham số **hiệu lực**; ở đây đã yêu cầu một DRBG có parameters hợp lệ nên có thể ép kiểu về `Instantiation`.
5. Với bài toán thực tế, chỉ gửi token qua kênh phù hợp và quản lý thời hạn, lưu trữ, so sánh theo chính sách ứng dụng. **Randomness tốt không tự giải quyết việc lộ token qua log, URL, database hay telemetry**.

Không “thêm bí mật” bằng cách gọi `random.setSeed("test".getBytes(...))` trước `nextBytes`. Việc tự seed bằng dữ liệu đoán được có thể phá mục đích tạo ngẫu nhiên không thể đoán trước. Tốt nhất để provider tự lấy entropy từ hệ thống.

## 7. Kiểm tra provider và tham số hiệu lực

### 7.1. Provider và thuật toán không cố định giữa các máy

`new SecureRandom()` chọn thuật toán theo thứ tự provider; trên một JDK/OS có thể là `NativePRNG`, trên hệ thống khác có thể là `DRBG`. Với `getInstance("DRBG")`, provider cụ thể vẫn phụ thuộc danh sách đăng ký và khả năng của môi trường.

Đoạn mã sau (đặt trong chương trình đã import `SecureRandom`, `DrbgParameters` và xử lý ngoại lệ) giúp quan sát:

```java
SecureRandom random = SecureRandom.getInstance("DRBG");
System.out.println(random.getProvider().getName());
System.out.println(random.getAlgorithm());

if (random.getParameters() instanceof DrbgParameters.Instantiation p) {
    System.out.println("Strength: " + p.getStrength());
    System.out.println("Capability: " + p.getCapability());
}
```

**Không có stdout cố định cho toàn bộ đoạn này** vì tên provider, effective strength và capability phụ thuộc runtime/cấu hình. Khác biệt môi trường **không tự chứng minh cấu hình nào yếu**: cần xem yêu cầu ứng dụng và tài liệu provider.

### 7.2. Không nhầm requested và effective

Ví dụ ứng dụng yêu cầu:

```java
DrbgParameters.instantiation(
        128, DrbgParameters.Capability.NONE, null);
```

Sau khi tạo thành công, `getParameters()` có thể cho kết quả capability là `RESEED_ONLY` hoặc `PR_AND_RESEED` vì provider cung cấp nhiều khả năng hơn tối thiểu. Tương tự, strength hiệu lực có thể cao hơn 128.

Nếu cần kiểm toán cấu hình, ghi lại **tên provider, tên thuật toán, effective strength và capability**; không đưa seed, token, private key hay trạng thái DRBG vào log.

### 7.3. Khi thiếu DRBG

`SecureRandom.getInstance("DRBG", parameters)` ném `NoSuchAlgorithmException` nếu không tìm thấy provider đáp ứng tên thuật toán **và** tham số. Phân biệt hai tình huống:

- Nếu chỉ cần **CSPRNG cho token** mà không bắt buộc một DRBG cụ thể, `new SecureRandom()` vẫn là API chuẩn thích hợp; hãy kiểm tra chính sách bảo mật của môi trường.
- Nếu yêu cầu triển khai **đúng DRBG với strength/capability xác định**, phải báo lỗi cấu hình hoặc triển khai provider đáp ứng. Không hạ strength hoặc âm thầm đổi sang `Random` để “cho chạy được”.

Mã khả chuyển thường nhận `NoSuchAlgorithmException` ở tầng khởi tạo, báo lỗi rõ ràng và không tạo giá trị bảo mật khi nguồn RNG mong muốn không khả dụng.

## 8. Sinh byte với tham số riêng: additional input

Để ảnh hưởng đến một lần sinh cụ thể, dùng overload:

```java
random.nextBytes(
        byteArray,
        DrbgParameters.nextBytes(
                -1,                  // Dùng effective strength
                false,               // Không yêu cầu PR cho lần này
                additionalInput));
```

`additionalInput` giúp phân biệt ngữ cảnh và hỗ trợ thiết kế DRBG, nhưng không nên dùng để lưu mật khẩu/thông tin nhạy cảm hay tin rằng các byte đó sẽ “sửa” entropy nguồn. Nếu cần ngẫu nhiên độc lập giữa nhiều miền nghiệp vụ, kết hợp phân vùng key/secret rõ ràng với cách tổ chức ứng dụng thay vì dựa hoàn toàn vào additional input.

### Ví dụ hoàn chỉnh: sinh, reseed và sinh lại

Tạo **`DrbgReseedDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.DrbgParameters;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;

public class DrbgReseedDemo {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {

        SecureRandom random = SecureRandom.getInstance(
                "DRBG",
                DrbgParameters.instantiation(
                        128,
                        DrbgParameters.Capability.RESEED_ONLY,
                        null));

        byte[] output = new byte[24];
        random.nextBytes(
                output,
                DrbgParameters.nextBytes(
                        -1, false,
                        "batch-A".getBytes(StandardCharsets.UTF_8)));

        DrbgParameters.Instantiation actual =
                (DrbgParameters.Instantiation) random.getParameters();

        if (actual.getCapability().supportsReseeding()) {
            random.reseed(
                    DrbgParameters.reseed(
                            false,
                            "rotation-1".getBytes(StandardCharsets.UTF_8)));
        }

        random.nextBytes(output);
        System.out.println("outputBytes=" + output.length);
        System.out.println("reseedSupported="
                + actual.getCapability().supportsReseeding());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DrbgReseedDemo.java
java DrbgReseedDemo
```

Kết quả, khi provider đáp ứng yêu cầu DRBG:

```text
outputBytes=24
reseedSupported=true
```

**Điểm cần lưu ý:** chương trình không in byte ngẫu nhiên vì nội dung chúng không có kết quả cố định. `reseed(...)` lấy entropy từ **entropy source của provider**; chuỗi `"rotation-1"` chỉ là additional input. Không cần gọi `reseed()` bằng tay cho mỗi token: provider có thể tự reseed theo tuổi thọ seed; nếu ứng dụng có chính sách reseed thủ công, dùng thời điểm phù hợp, kiểm tra capability và đo ảnh hưởng hiệu năng.

## 9. Prediction resistance: khi nào đáng yêu cầu?

Với DRBG, khái niệm **prediction resistance** liên quan đến khả năng hạn chế kẻ tấn công dự đoán đầu ra sau khi trạng thái từng bị lộ, nhờ việc sử dụng entropy mới theo cơ chế được triển khai. Nó không có nghĩa là dữ liệu ngẫu nhiên đã bị lộ có thể trở lại bí mật, cũng không thay thế việc bảo vệ bộ nhớ/secret.

Để **yêu cầu khả năng PR ngay khi tạo**, dùng:

```java
SecureRandom random = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                256,
                DrbgParameters.Capability.PR_AND_RESEED,
                null));
```

Đây là đoạn mã minh họa trong một phương thức đã import `java.security.SecureRandom` và `java.security.DrbgParameters`, xử lý `NoSuchAlgorithmException`. Nó yêu cầu tối thiểu 256-bit strength và cả PR/reseed; **provider có thể từ chối nếu không đáp ứng**.

Nếu một instance đã hỗ trợ PR, có thể yêu cầu **cho riêng một lần sinh**:

```java
byte[] bytes = new byte[32];
random.nextBytes(
        bytes,
        DrbgParameters.nextBytes(
                -1,
                true,   // Yêu cầu prediction resistance cho lần này
                null));
```

Điều kiện là `((DrbgParameters.Instantiation) random.getParameters()).getCapability().supportsPredictionResistance()` trả về `true`. Nếu không, provider có thể từ chối yêu cầu `nextBytes` với tham số không hỗ trợ bằng `IllegalArgumentException`; không coi PR là khả năng mặc định của mọi `SecureRandom`.

**Cân nhắc vận hành:** việc phải lấy entropy mới có thể làm chậm hoặc chặn luồng gọi. Dùng PR khi yêu cầu bảo mật có căn cứ và provider đã được xác minh đáp ứng; đừng tự động bật `PR_AND_RESEED` hoặc `true` ở mọi truy vấn chỉ vì tên nghe mạnh hơn.

## 10. Đọc đúng các API quan trọng

| API | Tác dụng | Điểm dễ nhầm |
| --- | --- | --- |
| `new SecureRandom()` | Lấy CSPRNG theo provider mặc định | Không khẳng định là `"DRBG"` |
| `SecureRandom.getInstance("DRBG")` | Yêu cầu một DRBG | Cơ chế nội bộ và default strength phụ thuộc provider |
| `getInstance("DRBG", instantiation(...))` | Yêu cầu mức strength/capability tối thiểu | Nếu không đáp ứng có thể ném `NoSuchAlgorithmException` |
| `getParameters()` | Lấy parameters hiệu lực hoặc `null` với RNG không cung cấp | Không đồng nhất với tham số đã truyền |
| `nextBytes(byte[])` | Lấy các byte ngẫu nhiên | Không chỉ định strength = `length * 8` |
| `nextBytes(byte[], params)` | Lấy byte với yêu cầu thêm của provider | Không áp dụng cho mọi RNG/params |
| `reseed()` / `reseed(params)` | Lấy entropy nguồn để làm mới DRBG nếu hỗ trợ | Không đồng nghĩa với `setSeed(...)` |
| `setSeed(byte[])` | Cấp seed **do caller kiểm soát** | Seed yếu có thể làm kết quả dễ đoán; không dùng cho token thật |
| `generateSeed(int)` | Lấy byte seed bằng cơ chế của provider | Không phải API bắt buộc gọi trước `nextBytes` |
| `getInstanceStrong()` | Chọn theo danh sách strong algorithms của runtime | Không bảo đảm là DRBG và có thể chặn vì entropy |

**Phương thức `SecureRandom.nextBytes(byte[])` thường đủ** khi bạn đã chọn `SecureRandom` phù hợp. Các overload có `DrbgParameters` dành cho nhu cầu thực sự muốn quản lý yêu cầu DRBG.

## 11. Những vấn đề entropy và vòng đời cần hiểu

### 11.1. Seed tự động và lỗi setSeed yếu

Tài liệu `SecureRandom` nêu rằng với PRNG mới tạo mà chưa được seed bởi caller, lần `nextBytes` đầu tiên kích hoạt việc tự seed từ nguồn entropy do implementation cung cấp. Nếu dùng `SecureRandom(byte[] seed)` hoặc cấp `setSeed(...)` trước lúc tự seed, bạn có thể làm thay đổi cơ chế này.

Đây là mẫu **không dùng trong production**:

```java
// SAI cho token/khóa mật mã: seed có thể đoán được.
SecureRandom random = new SecureRandom(
        Long.toString(System.currentTimeMillis()).getBytes());
```

Ví dụ trên là **minh họa mã không an toàn**, không cần chạy. Nếu có yêu cầu thử nghiệm tái lập kết quả, dùng dependency injection và một bộ sinh deterministic chỉ cho test; không tráo cùng cấu hình vào đường tạo secret thật.

### 11.2. Reseeding tự động

Một DRBG có giới hạn số lần/khối bit được sinh trước khi phải làm mới trạng thái. Một số provider có thể reseed tự động để tuân theo cơ chế. Ứng dụng không nên tự đặt “cứ mỗi N token phải `reseed`” dựa trên suy đoán; hãy đọc tài liệu provider, chính sách bảo mật và kiểm thử thời gian đáp ứng thực tế.

### 11.3. Tái sử dụng và đa luồng

`SecureRandom` được tài liệu Java SE bảo đảm **an toàn khi nhiều luồng cùng truy cập**; nếu provider không khai báo thread-safe, lớp bao ngoài thực hiện đồng bộ cho những thao tác SPI tương ứng. Vì vậy bạn có thể giữ instance trong service thay vì tạo mới mỗi lần gọi. Tuy nhiên, một instance dùng chung có thể trở thành điểm tranh chấp trong tải cao: đo lường rồi mới quyết định sử dụng nhiều instance hay cơ chế cấp phát phù hợp.

**Không** serialize trạng thái nội bộ DRBG rồi coi đó là cách sao lưu nguồn ngẫu nhiên: tài liệu DRBG yêu cầu trạng thái nội bộ không được serialize như dữ liệu dùng lại; khi cần khởi tạo lại, để provider xử lý entropy.

### 11.4. Blocking và vận hành

`nextBytes`, `generateSeed` và `reseed` **có thể chặn** khi provider cần chờ entropy. Thời gian trễ tùy nguồn entropy và hệ thống; không dự đoán từ mỗi chữ `DRBG`. Nếu có sự cố trên môi trường server/container, ghi lại provider, algorithm, security settings, phân tích stack trace và latency; tránh tự sửa bằng seed từ thời gian hệ thống.

## 12. Ứng dụng thực tế: token, key và nonce

**Token phiên hoặc liên kết khôi phục:** dùng `SecureRandom` tạo đủ byte không thể đoán trước, mã hóa Base64URL, có thời gian hết hạn và chính sách lưu/thu hồi. 32 byte ngẫu nhiên là một mức kích thước thường được dùng cho token; độ an toàn thực tế còn phụ thuộc toàn bộ thiết kế xác thực, khả năng quản lý secret và giới hạn truy cập. Không suy từ 32 byte rằng DRBG luôn đạt 256-bit security strength.

**Khóa mật mã:** tốt nhất sử dụng `KeyGenerator` hoặc API tạo key của thuật toán, với `SecureRandom` phù hợp khi API cho phép. Độ dài key phải tuân theo thuật toán; dữ liệu `nextBytes` không tự trở thành một key hợp lệ cho mọi sơ đồ mật mã.

**Nonce/IV:** nhiều sơ đồ yêu cầu **tính duy nhất** (có thể bên cạnh tính ngẫu nhiên). Chỉ dựa vào ngẫu nhiên mà không hiểu giới hạn trùng lặp hoặc cách quản lý nonce theo từng key có thể không đáp ứng hợp đồng thuật toán. Chọn cách sinh nonce theo yêu cầu của cipher/protocol và kiểm soát vòng đời key.

**Mô phỏng hoặc game:** khi không cần bảo mật, các API ngẫu nhiên thông thường có thể phù hợp hơn; DRBG không nhất thiết cho hiệu năng tốt hơn. Nhu cầu bảo mật là tiêu chí lựa chọn.

## 13. Cấu hình SUN provider: biết đủ để dùng đúng

Khi chạy trên JDK tham chiếu có `SUN/DRBG`, có thể kiểm tra thuộc tính bảo mật:

```java
String value = java.security.Security.getProperty(
        "securerandom.drbg.config");
System.out.println(value == null ? "(not configured)" : value);
```

Đây là **một trích đoạn** để quan sát cấu hình, không phải chương trình standalone. Khi property không cấu hình, provider SUN chọn giá trị mặc định theo tài liệu, hiện là Hash_DRBG/SHA-256. Nếu property được đặt, chuỗi có thể chứa lựa chọn cơ chế (`Hash_DRBG`, `HMAC_DRBG`, `CTR_DRBG`), thuật toán phù hợp, strength và capability được hỗ trợ theo cú pháp của JDK.

Các điểm phải tách biệt:

- **Chọn provider/thuật toán JCA:** `SecureRandom.getInstance("DRBG", ...)`.
- **Chọn tham số tối thiểu của instance:** `DrbgParameters.instantiation(...)`.
- **Chọn cơ chế Hash/HMAC/CTR cụ thể:** cấu hình **provider** `securerandom.drbg.config` khi SUN provider hỗ trợ.
- **Yêu cầu riêng cho một lượt generate/reseed:** `DrbgParameters.nextBytes(...)` và `DrbgParameters.reseed(...)`.

Đừng copy nguyên một cấu hình của nhà cung cấp sang mọi JDK rồi xem kết quả là hợp đồng Java chuẩn. Nếu ứng dụng phải tuân thủ chính sách mật mã cụ thể, hãy kiểm tra provider, phiên bản, yêu cầu của tổ chức và chứng cứ cấu hình hoạt động trong môi trường triển khai.

## 14. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` khi tạo DRBG | Không có provider đáp ứng `"DRBG"` hoặc parameters | Kiểm tra provider, algorithm và mức strength/capability đã yêu cầu |
| `getParameters() == null` | RNG không cung cấp parameters như DRBG chuẩn, hoặc provider khác | Dùng `instanceof DrbgParameters.Instantiation` trước khi ép kiểu khi không kiểm soát lựa chọn |
| `IllegalArgumentException` khi `nextBytes(..., params)` | Tham số không hợp lệ, strength/PR không được hỗ trợ | Xem effective strength/capability rồi điều chỉnh yêu cầu đúng |
| `UnsupportedOperationException` ở `reseed` | Provider không triển khai reseeding cho đối tượng đó | Kiểm tra capability, tài liệu provider; không ép reseed bằng mẹo tự cấp seed yếu |
| Sinh token chậm hoặc treo | Chờ entropy hoặc tranh chấp luồng/thiết bị | Đo latency, đọc cấu hình entropy, hành vi provider, dùng instance hợp lý |
| Token có độ dài sai mong đợi | Nhầm số byte với số ký tự của Base64URL | 32 byte → 43 ký tự Base64URL không padding |
| Đầu ra khác giữa các lần chạy | Đó là mục đích của CSPRNG; test so sánh byte cố định là sai | Kiểm thử độ dài, encoding, cấu hình và hành vi API thay vì so chuỗi |
| Đầu ra dự đoán được trong thiết kế tự seed | Seed do caller cung cấp quá yếu hoặc lặp | Để provider tự seed từ entropy đáng tin cậy; bỏ các seed tự chế |

**Cách kiểm chứng hợp lý:** in tên `getAlgorithm()`, `getProvider().getName()` và effective `DrbgParameters.Instantiation` trong môi trường thử nghiệm; sinh một số byte để xác nhận API vận hành; không đưa seed/secret thực vào log. Cần đánh giá hiệu năng hay độ an toàn của provider thì dựa vào hướng dẫn, tài liệu và quy trình kiểm chứng chuyên môn, **không** lấy việc in nhiều chuỗi khác nhau làm bằng chứng mật mã học.

## 15. Nguyên tắc lựa chọn thực hành

1. **Cần byte an toàn cho token/secret thông thường:** `new SecureRandom()`, rồi `nextBytes(...)` là lựa chọn Java chuẩn và gọn.
2. **Cần DRBG theo chính sách hoặc yêu cầu kỹ thuật:** chọn `getInstance("DRBG", DrbgParameters.instantiation(...))`, kiểm tra provider và effective parameters.
3. **Cần reseed có điều kiện:** yêu cầu `RESEED_ONLY` (hoặc hơn) và dùng `reseed(...)` khi có lý do; đừng tự cấp seed yếu.
4. **Cần prediction resistance:** yêu cầu `PR_AND_RESEED`, xác minh hỗ trợ và cân nhắc entropy/latency cho những lần gọi cần PR.
5. **Cần phân biệt ngữ cảnh:** dùng personalization/additional input đúng ý nghĩa, không coi chúng là entropy thay thế.
6. **Cần tính di động giữa Java runtimes:** không hard-code giả định cơ chế Hash_DRBG, provider SUN, mức strength mặc định hay việc một phiên bản JDK chọn cùng thuật toán ở mọi OS.
7. **Cần tính tái lập trong unit test:** mock/inject một nguồn test có kiểm soát và giữ nó hoàn toàn tách khỏi đường tạo bí mật trong production.

## 16. Câu hỏi tự kiểm tra

1. `SecureRandom` có luôn là DRBG không? **Không.** Nó là API CSPRNG, còn thuật toán do provider chọn.
2. `new SecureRandom()` có phải lựa chọn không an toàn? **Không.** Đây vẫn là API ngẫu nhiên mật mã chuẩn; chỉ cần chỉ định `DRBG` khi có yêu cầu cụ thể.
3. `DrbgParameters.instantiation(128, RESEED_ONLY, null)` hứa hẹn chính xác 128-bit strength không? **Không.** Đó là **mức tối thiểu**; provider có thể cấp cao hơn.
4. 32 byte token có chứng minh DRBG sở hữu 256-bit security strength không? **Không.** Độ dài đầu ra khác security strength.
5. `Capability.NONE` nghĩa là DRBG không thể reseed? **Không hẳn.** Nó chỉ không **yêu cầu** khả năng đó; effective capability có thể cao hơn.
6. `setSeed(System.currentTimeMillis()...)` có giúp token khó đoán hơn? **Không.** Seed có thể đoán được, dễ làm suy yếu tính bảo mật.
7. Có nhất thiết phải bật PR cho mọi `nextBytes` không? **Không.** PR có chi phí/điều kiện riêng và chỉ dùng khi yêu cầu rõ ràng.
8. `"DRBG"` có đồng nghĩa `"Hash_DRBG with SHA-256"` ở mọi JVM không? **Không.** Hash_DRBG/SHA-256 là lựa chọn mặc định được mô tả cho **SUN provider**, không phải tiêu chuẩn bắt buộc chung.
9. Personalization string có thể thay nguồn entropy hệ thống không? **Không.** Nó chủ yếu nhằm phân biệt ngữ cảnh.
10. Tại sao `getParameters()` hữu ích? **Nó cho biết strength/capability hiệu lực** của instance khi provider có thể cấp cấu hình mạnh hơn mức yêu cầu.

## Tài liệu chính thức để tra cứu

- OpenJDK JEP 273 — DRBG-Based SecureRandom Implementations (Java 9): https://openjdk.org/jeps/273
- Oracle Java SE 27 — `java.security.SecureRandom`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/SecureRandom.html
- Oracle Java SE 27 — `java.security.DrbgParameters`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/DrbgParameters.html
- Oracle Java SE 27 — `DrbgParameters.Capability`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/DrbgParameters.Capability.html
- Oracle Java SE 27 — JDK Providers documentation: https://docs.oracle.com/en/java/javase/27/security/oracle-providers.html
- NIST SP 800-90A Rev. 1 — Recommendation for Random Number Generation Using Deterministic Random Bit Generators: https://csrc.nist.gov/pubs/sp/800/90/a/r1/final

Điều cần ghi nhớ: **`SecureRandom` cung cấp ngẫu nhiên mật mã; `"DRBG"` chọn một loại triển khai có thể yêu cầu strength/capability; nguồn entropy và hành vi thực tế vẫn do provider quyết định.** Dùng `DrbgParameters` để thể hiện yêu cầu rõ ràng, kiểm tra kết quả cấu hình và giữ đúng vòng đời bảo mật của token/khóa.
