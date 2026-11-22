# 3.5. Tạo byte ngẫu nhiên, seed, reseed và tác động của seed có thể dự đoán

Trong module **Java Advance – Security & Cryptography**, “ngẫu nhiên” thường là thành phần an ninh: token phiên đăng nhập, mã khôi phục, khóa, salt, nonce/IV hoặc challenge. Một chương trình có thể tạo đủ 32 byte và trông rất ngẫu nhiên, nhưng nếu trạng thái ban đầu đến từ **seed có thể đoán**, đối thủ có thể thu hẹp số khả năng đến mức dò được. Bài học dùng **Java 21** để phân biệt nguồn entropy, trạng thái PRNG, seed ban đầu và reseed, sau đó thực hành `SecureRandom` đúng cách.

## Mục tiêu

Sau bài này, bạn có thể:

1. Tạo các mảng byte khó dự đoán bằng `java.security.SecureRandom` và mã hóa chúng thành chuỗi khi cần.
2. Giải thích **entropy → seed/state → quá trình sinh byte → reseed** mà không nhầm “độ dài output” với “độ bí mật thực”.
3. Hiểu khi nào `SecureRandom` tự seed, tác động của `SecureRandom(byte[])`, `setSeed(...)`, `generateSeed(...)` và `reseed()`.
4. Chỉ ra vì sao timestamp, số tuần tự, PID, username, seed hard-code hay seed quá nhỏ đều nguy hiểm nếu được dùng làm nguồn duy nhất cho bí mật.
5. Nhận diện giới hạn provider, dùng DRBG trong Java 21 khi cần chính sách reseed rõ ràng, và phân biệt random **token**, **salt**, **nonce** với sinh **khóa**.
6. Kiểm thử đúng: xác minh độ dài, định dạng, khả năng vận hành và nguồn entropy; không đánh đồng vài mẫu “khác nhau” với bằng chứng an toàn mật mã.

## 1. Bản chất của random trong ứng dụng bảo mật

Một máy tính thực hiện nhiều phép tính hoàn toàn xác định. Vì vậy, nhiều bộ sinh số ngẫu nhiên được xây dựng dưới dạng **pseudorandom generator**: thuật toán mở rộng một trạng thái ban đầu thành chuỗi byte trông ngẫu nhiên. Nếu biết đủ trạng thái và thuật toán, có thể tái tạo chuỗi đó; mức an toàn phụ thuộc trước hết vào **độ khó đoán trạng thái ban đầu** và chất lượng bộ sinh.

Sơ đồ khái niệm:

```text
Nguồn entropy của hệ điều hành / thiết bị
                    |
             Seed ban đầu đủ mạnh
                    |
        PRNG/DRBG có thiết kế mật mã
                    |
         nextBytes(...) -> byte[]
                    |
       Reseed định kỳ/khi chính sách yêu cầu
       bằng entropy mới (nếu được hỗ trợ)
```

**Khái niệm cần phân biệt:**

| Khái niệm | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| Random bytes | Mảng byte đầu ra từ bộ sinh | Byte ngẫu nhiên có thể chứa `0x00`, byte âm khi đọc kiểu `byte` có dấu; không phải chuỗi UTF-8. |
| Seed | Dữ liệu khởi tạo hoặc bổ sung trạng thái của PRNG | Độ dài seed không tự nói lên entropy của nó. |
| Entropy | Mức bất định của thông tin đối với đối thủ | Một giá trị có 256 bit biểu diễn vẫn có thể chỉ có vài bit khó đoán. |
| CSPRNG | Bộ sinh giả ngẫu nhiên phù hợp mật mã | Kết quả phải khó dự đoán dù đối thủ biết thuật toán. |
| DRBG | Một lớp CSPRNG dựa trên thuật toán xác định và entropy ban đầu | Có thể hỗ trợ giới hạn số lần sinh, reseed, prediction resistance. |
| Reseed | Làm mới/bổ sung trạng thái từ nguồn entropy mới theo cơ chế provider | Không phải cùng thao tác với việc cố định seed để tái lập output. |
| Token/salt/nonce | Các giá trị có yêu cầu khác nhau | Token cần khó đoán; salt thường cần độc nhất và đủ ngẫu nhiên; nonce của AEAD yêu cầu **không tái sử dụng cùng khóa**. |

Ví dụ giới hạn entropy: nếu seed chỉ là một trong **1.000 giá trị timestamp** mà đối thủ có thể khoanh vùng, không thể xem nó là “256 bit bí mật” chỉ vì chương trình băm timestamp bằng SHA-256 rồi lấy 32 byte. Một giá trị được tính xác định từ 1.000 khả năng vẫn chỉ có tối đa 1.000 trạng thái, tương ứng dưới 10 bit bất định. **Hash hay PRNG không tạo thêm entropy bí mật từ đầu vào có thể đoán.**

## 2. Chọn API đúng trước khi bàn tới seed

Nếu dữ liệu không có yêu cầu bảo mật, `Random(seed)` hữu ích để tái lập phép thử, `ThreadLocalRandom.current()` giảm tranh chấp giữa các thread và `SplittableRandom` phục vụ tính toán/mô phỏng. Các API đó **không bảo đảm chống dự đoán**; `Math.random()` cũng không thích hợp cho token hay khóa.

Khi cần token, salt, nonce hoặc vật liệu bí mật, dùng `java.security.SecureRandom` đã được cấu hình phù hợp; với **khóa** nên ưu tiên `KeyGenerator`/`KeyPairGenerator` theo thuật toán. Mẫu sử dụng thông thường là:

```java
SecureRandom random = new SecureRandom();
byte[] bytes = new byte[32];
random.nextBytes(bytes);
```

Đoạn minh họa cần `import java.security.SecureRandom;`. Trọng tâm còn lại của bài này không phải so sánh lại cả họ bộ sinh, mà là giải thích **self-seeding, tác động của seed do caller cung cấp, và reseed đúng khi provider hỗ trợ**.

## 3. Thực hành đầy đủ: tạo 32 byte cho token

Tạo file **`SecureBytesDemo.java`**:

```java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureBytesDemo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();

        byte[] token = new byte[32];
        random.nextBytes(token);

        // Chuyển byte nhị phân sang chuỗi phù hợp URL/cookie.
        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(token);

        // Chỉ in kích thước: không ghi token bí mật vào log.
        System.out.println("Byte count: " + token.length);
        System.out.println("Bit count: " + token.length * 8);
        System.out.println("Base64url chars: " + encoded.length());
    }
}
```

Kiểm tra JDK 21 bằng `java -version` và `javac -version`; trong thư mục chứa file, chạy:

```text
mkdir out
javac --release 21 -encoding UTF-8 -d out SecureBytesDemo.java
java -cp out SecureBytesDemo
```

Kết quả với ứng dụng trên:

```text
Byte count: 32
Bit count: 256
Base64url chars: 43
```

**Vì sao?** `nextBytes(byte[])` điền 32 byte nhị phân. 32 × 8 = 256 **bit dữ liệu đầu ra**; mức an toàn thực còn phụ thuộc seed và provider. Base64url bỏ padding mã hóa đúng 32 byte thành 43 ký tự; bản thân Base64 **không mã hóa bí mật**, chỉ chuyển biểu diễn. Giá trị token khác nhau giữa các lần chạy và không có một stdout token cố định.

**Không làm các việc sau:**

- Không tạo `new String(token, UTF_8)` để “chuyển byte ngẫu nhiên thành text”: nhiều chuỗi byte không phải UTF-8 hợp lệ và có thể bị thay thế byte khi giải mã.
- Không công khai token thực trong log, exception, metric label, URL không bảo vệ hoặc ảnh chụp debug.
- Không dùng `Random.nextBytes` hay `UUID.randomUUID()` để thay mọi loại secret theo cảm tính. UUID phiên bản 4 có định dạng và lượng bit ngẫu nhiên khác token 32 byte; chọn token theo mô hình đe dọa, độ dài, cách lưu và giao thức.
- Không dùng việc in ra “hai token khác nhau” làm bài kiểm định mật mã. Một nguồn yếu cũng có thể tạo các chuỗi nhìn rất khác nhau.

Một đối tượng `SecureRandom` có thể được **tái sử dụng**; Java 21 tài liệu hóa rằng API này an toàn khi gọi từ nhiều thread (provider được dùng trực tiếp nếu khai báo thread-safe, hoặc lớp bao đồng bộ truy cập engine). Tuy vậy, hiệu năng và khả năng chặn khi chờ entropy vẫn phụ thuộc implementation; cần đo trong môi trường triển khai nếu tải lớn.

## 4. Seed ban đầu được tạo như thế nào?

Đối với một `SecureRandom` sử dụng PRNG, Javadoc Java 21 mô tả:

- Tạo bằng `new SecureRandom()` hoặc `SecureRandom.getInstance(...)` thường **chưa lập tức lấy đủ seed**. Lần gọi `nextBytes(...)` đầu tiên sẽ khiến PRNG tự seed từ nguồn entropy do implementation xác định, **trừ khi trước đó đã gọi `setSeed(...)`**.
- `new SecureRandom(byte[] seed)` tạo đối tượng với seed do người gọi cung cấp. Nếu seed đó là nguồn duy nhất và có thể đoán, tính khó dự đoán của output có thể bị phá vỡ. Hành vi chi tiết phụ thuộc provider.
- `random.setSeed(byte[])` hoặc `random.setSeed(long)` cung cấp seed đầu vào từ caller. Theo tài liệu Java, với trạng thái đã tồn tại, seed mới **bổ sung** chứ không thay thế seed trước đó. Tuy nhiên, nếu gọi trước lần tự seed đầu tiên, không thể dựa vào cơ chế tự lấy entropy mặc định.
- `setSeed(long)` chỉ nhận một số `long` 64 bit; việc truyền số thời gian, bộ đếm, PID hoặc hằng số càng làm số trạng thái tiềm năng bị giới hạn.

### So sánh bốn kiểu khởi tạo

| Mẫu | Đánh giá | Vì sao |
| --- | --- | --- |
| `new SecureRandom(); random.nextBytes(out);` | **Khuyến nghị mặc định** | Provider tự dùng nguồn entropy phù hợp. |
| `SecureRandom.getInstance("DRBG"); ...` | Hợp lý nếu runtime có DRBG và bạn cần cấu hình/kiểm tra DRBG | Cần xác minh service/provider. |
| `new SecureRandom("known".getBytes(UTF_8));` | **Nguy hiểm** nếu seed đoán được là nguồn entropy duy nhất | Seed đã biết hoặc có không gian tìm kiếm nhỏ. |
| `SecureRandom r = new SecureRandom(); r.setSeed(System.currentTimeMillis()); r.nextBytes(out);` | **Tránh sử dụng** | Timestamp dự đoán được; gọi `setSeed` trước khi tự seed có thể bỏ qua bước lấy entropy mặc định. |

Một seed dài 32 byte lấy từ chuỗi lặp/zero vẫn yếu. Ngược lại, sau khi provider **đã tự seed an toàn**, `setSeed(123)` không có nghĩa toàn bộ trạng thái chắc chắn trở nên đoán được: phương thức bổ sung vào trạng thái hiện hữu. Nhưng việc này **không đem lại lợi ích bảo mật có thể tin cậy** và gây nhầm lẫn trong audit; nên tránh seed thủ công nếu không có lý do đã được thiết kế và đánh giá.

**Điểm nhạy cảm về thứ tự:** `new SecureRandom(); setSeed(weak); nextBytes(out)` khác với `new SecureRandom(); nextBytes(out); setSeed(weak)` về thời điểm self-seeding. Không suy diễn rằng mọi provider đều có cùng thuật toán hoặc cùng kết quả byte cho một seed, nhưng **không giao an ninh của secret cho nguồn seed có thể dự đoán**.

### Phân biệt `nextBytes`, `generateSeed` và `getSeed`

| Phương thức | Nguồn và mục đích |
| --- | --- |
| `nextBytes(byte[])` | Lấy byte random từ bộ sinh hiện tại để dùng trong ứng dụng. Đây là lựa chọn thường dùng. |
| `generateSeed(int)` | Lấy byte seed theo seed-generation algorithm của implementation; hữu ích để seed một bộ sinh **khác** khi có yêu cầu rõ ràng. Có thể tốn tài nguyên hoặc chặn. |
| `SecureRandom.getSeed(int)` | Phương thức static nhận byte seed theo cơ chế seed generation; hiếm khi cần cho ứng dụng thông thường. |
| `setSeed(byte[])` / `setSeed(long)` | Caller đưa entropy đầu vào; **không bắt buộc** khi dùng `new SecureRandom()`. |
| `reseed()` / `reseed(params)` | Yêu cầu provider lấy entropy mới để reseed; **có thể không được hỗ trợ**. |

Không cần và không nên theo một “nghi thức” kiểu `generateSeed(32)` → `setSeed(...)` → `nextBytes(...)` mỗi khi lấy token. Với cấu hình thông thường, `nextBytes` đã đáp ứng nhu cầu và provider có chính sách lấy seed thích hợp.

## 5. Minh họa seed đoán được bằng bộ sinh xác định

Ví dụ dưới đây **cố ý sử dụng `java.util.Random` không an toàn cho mật mã** để có output được Java bảo đảm tái lập. Mục đích là nhìn thấy tác động của **cùng seed**; nó **không phải mã tạo token sản xuất**.

Tạo file **`RepeatableSeedDemo.java`**:

```java
import java.util.Arrays;
import java.util.Random;

public class RepeatableSeedDemo {
    public static void main(String[] args) {
        byte[] first = new byte[16];
        byte[] second = new byte[16];

        new Random(123L).nextBytes(first);
        new Random(123L).nextBytes(second);

        System.out.println("Same bytes: " + Arrays.equals(first, second));
        System.out.println("Bytes generated: " + first.length);
    }
}
```

Chạy:

```text
javac --release 21 -encoding UTF-8 -d out RepeatableSeedDemo.java
java -cp out RepeatableSeedDemo
```

Stdout chính xác:

```text
Same bytes: true
Bytes generated: 16
```

Hai bộ sinh `Random` độc lập nhưng có **seed 123** giống nhau sẽ phát sinh **cùng chuỗi byte**. Nếu ứng dụng dùng chuỗi đó làm token, người biết seed có thể đoán được token. Ngay cả khi seed “thay đổi mỗi lần” nhưng chỉ chọn trong một khoảng nhỏ, đối thủ có thể thử tất cả seed khả dĩ.

Đối với `SecureRandom`, **không dựa vào giả định “cùng seed luôn cho cùng output” hoặc “cùng seed chắc chắn cho output khác nhau”**: thuật toán, việc bổ sung entropy, thời điểm self-seeding và provider có thể khác. Bài học về bảo mật ở đây là: nếu thiết kế dựa **duy nhất** trên seed có thể đoán và không có entropy thật bổ sung thì đầu ra không có bí mật đủ mạnh, bất kể nhìn như ngẫu nhiên.

### Kịch bản rủi ro thực tế

Giả sử backend làm việc sau để tạo token:

```java
// Ví dụ phản diện: KHÔNG dùng để tạo token bảo mật.
SecureRandom random = new SecureRandom();
random.setSeed(System.currentTimeMillis());
byte[] token = new byte[32];
random.nextBytes(token);
```

- Đối thủ thấy thời điểm tài khoản được tạo/xác thực và có thể ước lượng clock máy chủ trong một khoảng ngắn.
- Nếu seed do timestamp cung cấp là entropy duy nhất, số giá trị có thể thử rất nhỏ so với 2^256; kích thước token 32 byte **không cứu được thiết kế**.
- Việc tái tạo byte cụ thể phụ thuộc provider, trạng thái và thứ tự gọi API; đây là phân tích **nguy cơ**, không phải cam kết mọi provider tự động tạo đúng cùng token từ cùng timestamp.
- Nếu hệ thống chạy nhiều container/VM được clone từ snapshot có cùng trạng thái PRNG và thiếu reseed đúng cách, khả năng tái lập/đụng độ output là một rủi ro vận hành khác. Cần cấu hình entropy tốt, khởi tạo đúng và kiểm thử mô hình clone/restore của nền tảng.

Các seed sai thường gặp: `System.currentTimeMillis()`, `System.nanoTime()`, `Thread.currentThread().getId()`, process ID, username, email, số thứ tự tăng, một chuỗi cố định trong config, hash của các giá trị này. **Băm seed yếu hoặc nối thêm dữ liệu công khai không tự tạo entropy mới**.

## 6. Reseed là gì và khi nào cần?

**Seed lần đầu** giúp PRNG xây dựng trạng thái bí mật. **Reseed** là cập nhật trạng thái sau đó, thường với entropy mới, nhằm tuân thủ vòng đời của DRBG, giảm thời gian phụ thuộc vào một trạng thái và hỗ trợ các yêu cầu về prediction resistance trong những thiết kế có bảo đảm tương ứng.

Trong Java 21:

- `SecureRandom.reseed()` yêu cầu engine lấy entropy từ nguồn của nó. Không phải mọi provider/algorithm đều hỗ trợ; API có thể ném `UnsupportedOperationException`.
- `SecureRandom.reseed(SecureRandomParameters)` cho phép truyền cấu hình cụ thể nếu implementation chấp nhận.
- `SecureRandom.setSeed(...)` nhận input do **caller** cung cấp; không tương đương việc provider tự lấy entropy mới. Một lần `setSeed(0L)` không được coi là reseed an toàn.
- Một số DRBG tự reseed khi vượt ngưỡng tuổi seed/số lần sinh theo cơ chế riêng; không nên giả định tự động hay thủ công trên **mọi** implementation.
- `nextBytes`, `generateSeed` và `reseed` đều **có thể chặn** khi chờ entropy, tùy provider và hệ điều hành.

Đối với ứng dụng Java bình thường, **không cần tự gọi `reseed()` trước mỗi lần tạo token**. Nếu tổ chức có chính sách cụ thể về vòng đời DRBG, thời điểm khôi phục snapshot, thiết bị HSM/FIPS hoặc prediction resistance, hãy chọn provider hỗ trợ, đọc tài liệu cấu hình rồi kiểm thử. Gọi thủ công liên tục có thể làm tăng độ trễ mà không giúp ích theo cách tưởng tượng.

### Trường hợp cần phân biệt

| Tình huống | Cách tiếp cận |
| --- | --- |
| Tạo token đăng nhập trong một dịch vụ Java 21 thông thường | Một `SecureRandom` được khởi tạo mặc định và `nextBytes` thường phù hợp. |
| Dịch vụ chạy nhiều tháng | Xác minh chính sách reseed/entropy của provider nếu yêu cầu an ninh đặc thù; không tự tạo seed bằng timestamp. |
| VM/container phục hồi snapshot | Đánh giá nguy cơ trùng trạng thái, bảo đảm entropy và cơ chế khởi tạo/reseed đúng sau restore. |
| Phải chứng minh reseed/prediction resistance theo chính sách | Sử dụng DRBG/provider có capability tương ứng và kiểm tra `getParameters()`. |
| Unit test cần kết quả lặp lại | Dùng test double hoặc `Random` cố định **chỉ trong kiểm thử phi bảo mật**; production vẫn dùng CSPRNG. |

## 7. Java 21 DRBG và ví dụ kiểm tra khả năng reseed

Java có API `java.security.DrbgParameters` từ Java 9. Java 21 cung cấp cơ chế để yêu cầu thuộc tính DRBG và truy vấn **effective parameters**; thuật toán `"DRBG"` tùy provider. Ba khả năng chính:

- `DrbgParameters.Capability.NONE`: không bảo đảm hỗ trợ reseed/prediction resistance.
- `DrbgParameters.Capability.RESEED_ONLY`: có reseed, không yêu cầu prediction resistance trong mỗi lần sinh.
- `DrbgParameters.Capability.PR_AND_RESEED`: có cả reseed và khả năng prediction resistance.

**Prediction resistance** trong ngữ cảnh DRBG không có nghĩa “gọi `new SecureRandom()` một lần là bất khả xâm phạm”. Đó là thuộc tính/đòi hỏi cụ thể của cơ chế DRBG và nguồn entropy, cần được provider hỗ trợ.

Tạo file **`DrbgReseedDemo.java`**:

```java
import java.security.DrbgParameters;
import java.security.SecureRandom;
import java.security.SecureRandomParameters;

public class DrbgReseedDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom drbg = SecureRandom.getInstance("DRBG");
        SecureRandomParameters params = drbg.getParameters();

        boolean canReseed =
                params instanceof DrbgParameters.Instantiation actual
                && actual.getCapability().supportsReseeding();

        System.out.println("Algorithm: " + drbg.getAlgorithm());
        System.out.println("Reseed supported: " + canReseed);

        if (canReseed) {
            drbg.reseed(); // Provider tự lấy entropy mới.
        }

        byte[] randomBytes = new byte[16];
        drbg.nextBytes(randomBytes);
        System.out.println("Generated: " + randomBytes.length + " bytes");
    }
}
```

Chạy:

```text
javac --release 21 -encoding UTF-8 -d out DrbgReseedDemo.java
java -cp out DrbgReseedDemo
```

Trên một JDK 21 có provider `DRBG`, output có dạng:

```text
Algorithm: DRBG
Reseed supported: true
Generated: 16 bytes
```

Dòng `Reseed supported` **phụ thuộc provider và cấu hình** (cũng có thể là `false`); ví dụ tránh gọi `reseed()` nếu provider không công bố hỗ trợ. Nếu không cài provider cho `DRBG`, `getInstance("DRBG")` có thể ném `NoSuchAlgorithmException`; khi đó hãy kiểm tra danh sách provider hoặc dùng `new SecureRandom()` cho mục tiêu tạo byte ngẫu nhiên thông thường.

### Khi cần yêu cầu capability ngay từ khởi tạo

Đoạn sau là **snippet** để nhúng vào chương trình Java, không phải một file chạy độc lập:

```java
import java.security.DrbgParameters;
import java.security.SecureRandom;

SecureRandom drbg = SecureRandom.getInstance(
        "DRBG",
        DrbgParameters.instantiation(
                128,
                DrbgParameters.Capability.RESEED_ONLY,
                null));
```

Đối số `128` là **security strength yêu cầu tính bằng bit** của DRBG, không phải số byte sẽ lấy. `RESEED_ONLY` đặt yêu cầu tối thiểu về capability; lời gọi có thể thất bại nếu không có implementation đáp ứng. Thực tế phải đọc `drbg.getParameters()` để biết tham số hiệu lực, vì chúng có thể mạnh hơn yêu cầu.

`DrbgParameters.nextBytes(strength, predictionResistance, additionalInput)` và `DrbgParameters.reseed(predictionResistance, additionalInput)` dành cho use case có cấu hình DRBG cụ thể. **Additional input** hoặc **personalization string** không thay thế nguồn entropy bí mật; đừng dùng tên người dùng/public data như “seed bổ sung” rồi cho rằng mức an ninh tăng lên.

## 8. Đặt random bytes vào đúng ngữ cảnh: token, salt, nonce, khóa

Cùng gọi `nextBytes` nhưng từng trường hợp có điều kiện bảo mật riêng.

| Dùng vào việc gì | Yêu cầu chính | Ví dụ điển hình |
| --- | --- | --- |
| Token phiên / reset token | Khó đoán, đủ dài, truyền/lưu an toàn, hạn sử dụng/thu hồi | 32 byte từ CSPRNG → Base64url (43 ký tự). |
| Salt cho password KDF | Độc nhất trên mỗi mật khẩu và đủ ngẫu nhiên; **không cần giữ bí mật** | 16 byte từ CSPRNG; lưu cạnh thông số KDF và password hash. |
| Nonce/IV cho AES-GCM | **Tuyệt đối không lặp với cùng một khóa**; phải theo giới hạn và quy ước của GCM | Thường dùng 12 byte cho GCM; nguồn random tốt giảm xác suất đụng, nhưng không bảo đảm toán học không lặp. |
| Secret key | Đúng thuật toán, kích thước và vòng đời khóa | Ưu tiên `KeyGenerator` hoặc API key management/HSM phù hợp, thường dựa CSPRNG. |
| Mã OTP ngắn | Random đúng phân bố nhưng **không gian rất nhỏ** | Mã 6 chữ số chỉ 1.000.000 khả năng; bắt buộc có TTL, rate limit, chống replay. |
| Mã định danh công khai | Có thể cần tính duy nhất hơn là bí mật | Chọn thiết kế ID theo yêu cầu; không tự suy ID = secret. |

**Nonce ≠ seed ≠ secret key.** Một nonce có thể công khai nhưng lặp nonce trong GCM với cùng khóa có thể phá an toàn. Seed là dữ liệu dùng để lập/trộn trạng thái bộ sinh; token/key là đầu ra phải bảo vệ. Không được tái sử dụng chính seed của một instance như thể nó là nonce duy nhất cho mọi bản mã.

Ví dụ chọn số từ `0` đến `999_999` có giới hạn:

```java
SecureRandom random = new SecureRandom();
int code = random.nextInt(1_000_000);
String sixDigits = String.format(java.util.Locale.ROOT, "%06d", code);
```

`nextInt(bound)` tránh thao tác chia dư thô như `(randomByte & 0xff) % 10`, vốn cho phân bố lệch nếu 256 không chia hết cho 10. Đoạn này chỉ minh họa tạo mã 6 chữ số; không phải một hệ thống OTP an toàn nếu thiếu thời hạn, xác minh server-side, giới hạn số lần thử và chống sử dụng lại.

### Gợi ý sử dụng byte dữ liệu có trách nhiệm

- `byte[]` có thể chứa số âm nếu log dưới dạng giá trị `byte` Java (`-128..127`); đó chỉ là biểu diễn signed byte, không phải “random lỗi”.
- Nếu phải lưu/truyền byte, dùng Base64url/hex đúng định dạng và lưu ý encoding không tăng entropy.
- Giữ secret trong memory tối thiểu, đừng đưa seed/raw key vào log; xóa mảng byte nhạy cảm khi thích hợp và khả thi (`Arrays.fill`), dù việc xóa không được bảo đảm toàn bộ bản sao hoặc bộ nhớ do runtime/GC quản lý.
- Không suy ra rằng `getInstanceStrong()` luôn tốt hơn `new SecureRandom()` trong mọi ứng dụng. Nó chọn thuật toán theo `securerandom.strongAlgorithms` và có thể chặn/tốn tài nguyên, cần benchmark và đánh giá môi trường cụ thể.
- Không cố định tên provider/thuật toán theo máy lập trình khi chưa có yêu cầu tương thích rõ ràng.

## 9. Kiểm tra môi trường và provider trên Java 21

Nên báo cáo **runtime thật**, provider và thuật toán khi xem xét lỗi sản xuất.

Có thể chạy đoạn snippet trong `jshell`:

```java
import java.security.SecureRandom;
SecureRandom random = new SecureRandom();
System.out.println(Runtime.version());
System.out.println(random.getAlgorithm());
System.out.println(random.getProvider().getName());
System.out.println(random.getParameters());
```

Output ở đây **không cố định**: bản JDK, nhà phân phối, security properties, provider cấu hình và hệ điều hành đều có thể ảnh hưởng. `getParameters()` có thể trả về `null` cho provider không công bố effective DRBG parameters. Các phương thức hữu ích khác: `SecureRandom.getInstance("DRBG")` (nếu provider hỗ trợ), `SecureRandom.getInstanceStrong()` (nếu chính sách yêu cầu), `Security.getProviders()` để liệt kê provider.

Khi tự kiểm tra:

1. `java -version`, `javac -version` và `Runtime.version()` phải phù hợp runtime mục tiêu.
2. Nhận diện provider và thuật toán thực tế bằng `getProvider()`/`getAlgorithm()`.
3. Kiểm tra startup/entropy source, policy reseed, giới hạn provider trong container/VM/HSM.
4. Ghi nhận lỗi và metadata không nhạy cảm; **không log seed, random token, private key**.
5. Dùng test tích hợp và security review đúng threat model, đừng coi vài sample output là chứng minh CSPRNG.

## 10. Các lỗi nhận thức và vận hành hay gặp

| Triệu chứng/khẳng định | Sai ở đâu | Cách xử lý |
| --- | --- | --- |
| “Tạo 32 byte nghĩa là có 256 bit entropy” | Output có thể được mở rộng từ seed rất yếu | Kiểm tra nguồn seed/entropy và provider. |
| “Thêm timestamp giúp SecureRandom mạnh hơn” | Timestamp thường dự đoán được; gọi `setSeed` trước `nextBytes` có thể ngăn self-seeding | Bỏ seed tự chế; dùng entropy từ provider. |
| “Cùng seed trên SecureRandom luôn ra cùng byte” | Provider và việc lấy/thêm entropy khác nhau | Không dùng `SecureRandom` làm cách tái lập dữ liệu kiểm thử. |
| “Gọi reseed mỗi request mới bảo mật” | Có thể không hỗ trợ, có thể block, tốn tài nguyên; provider có policy riêng | Chỉ dùng theo yêu cầu thiết kế và tài liệu provider. |
| `UnsupportedOperationException` từ `reseed()` | Provider/engine không hỗ trợ reseed | Dùng capability check khi là DRBG hoặc chọn provider đáp ứng yêu cầu. |
| `NoSuchAlgorithmException: DRBG` | Không có service DRBG trong provider hiện hành | Xem JDK, cấu hình provider, hoặc dùng `new SecureRandom()` cho nhu cầu chung. |
| Nhiều token trùng trong thử nghiệm | Có thể có seed cố định, clone state, lỗi tái sử dụng dữ liệu/caching hoặc bug hệ thống | Kiểm tra quy trình khởi tạo, triển khai, tính duy nhất và dữ liệu lưu; điều tra toàn đường đi. |
| Token dài nhưng vẫn bị brute-force online | Secret bị lộ hoặc logic cho phép thử tùy ý; token ngắn có entropy thấp | Kiểm tra TTL, giới hạn thử, phân quyền, lưu token và mã hóa đường truyền. |
| Token byte bị mất ký tự khi chuyển `new String(bytes)` | Byte tùy ý không phải văn bản UTF-8 hợp lệ | Dùng Base64url/hex để biểu diễn binary. |
| Dùng random IV cho GCM rồi mặc nhiên bảo đảm không trùng | Random chỉ làm xác suất đụng thấp, không biến uniqueness thành tuyệt đối | Thiết kế quản lý nonce, giới hạn số lần mã hóa mỗi khóa và giám sát nguy cơ lặp. |

**Không suy diễn tính bảo mật từ thống kê nhỏ.** Ví dụ hai lần tạo token khác nhau chỉ cho biết hai lần output khác nhau; bộ sinh không an toàn vẫn đạt điều đó. Ngược lại, xác suất trùng hợp tự nhiên của một CSPRNG không bằng 0; một phép thử tính uniqueness riêng lẻ cũng không chứng minh RNG hỏng.

**Không ép đầu ra random thành mật khẩu hoặc key bằng thao tác tùy tiện.** Nếu cần khóa AES, chọn `KeyGenerator.getInstance("AES")` cùng độ dài chính sách cho phép và hệ quản trị khóa phù hợp. Nếu cần hash mật khẩu, dùng password KDF được thiết kế riêng với salt, cost và quản lý tham số, thay vì “sha256(password + random)” tự chế.

## 11. Bài tập thực hành và tiêu chí đánh giá

**Bài 1 – Tạo token:** Chạy `SecureBytesDemo` trên Java 21 nhiều lần. Giải thích vì sao output chỉ in **32/256/43** thay vì in token thật. Nếu thay 32 byte bằng 16 byte, hãy tự tính chiều dài Base64url không padding và kiểm tra lại.

**Bài 2 – Phân tích entropy:** Một hệ thống lấy seed từ giờ phút gần đúng có thể nằm trong 2.000 mili giây khả dĩ. Nếu đó là entropy duy nhất, có tối đa bao nhiêu seed mà đối thủ cần kiểm tra? Vì sao băm seed bằng SHA-256 không làm tăng số trường hợp? *Gợi ý: 2.000 khả năng nhỏ hơn 2^11.*

**Bài 3 – Seed và tái lập:** Chạy `RepeatableSeedDemo`. Thử đổi một trong hai seed từ `123L` sang `124L`, giải thích vì sao output có thể khác. Sau đó nêu lý do không dùng mẫu `Random(seed)` để tạo reset token.

**Bài 4 – Reseed:** Chạy `DrbgReseedDemo`. Ghi lại algorithm, provider, `getParameters()` và kết quả capability; nêu lý do không được gọi `reseed()` bừa bãi nếu không kiểm tra hỗ trợ.

**Bài 5 – Review một thiết kế:** Cho ba dòng `SecureRandom r = new SecureRandom(); r.setSeed(System.currentTimeMillis()); r.nextBytes(token);`, hãy mô tả khi nào initial self-seeding bị thay thế, rủi ro timestamp và phiên bản sửa đúng bằng `new SecureRandom()` + `nextBytes(token)`. Đừng khẳng định mọi provider sinh cùng byte với cùng timestamp.

**Bài 6 – Chọn random cho mục đích:** Phân biệt một token bí mật 32 byte, salt 16 byte, nonce AES-GCM 12 byte và OTP 6 chữ số. Với mỗi loại, cho biết điều kiện về bí mật, tính duy nhất, chống replay/rate-limit và lưu trữ.

Hoàn thành bài khi có thể trả lời chính xác: **“Byte được tạo từ đâu? Seed ban đầu có khó đoán không? Khi nào provider tự seed hoặc reseed? Tôi đang dùng provider/DRBG nào và loại dữ liệu này đòi hỏi tính bí mật hay tính duy nhất?”**

## Tài liệu tham khảo chính thức

- [Java SE 21: `SecureRandom` Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html) — constructor, `nextBytes`, `setSeed`, `generateSeed`, `reseed` và provider.
- [Java SE 21: `DrbgParameters` Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/DrbgParameters.html) — reseed/prediction-resistance capability và ví dụ sử dụng.
- [Java SE 21: `SecureRandomParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandomParameters.html).
- [JDK 21: Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html) — RNG/provider và entropy.
- [JDK 21: JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html) — các thuật toán/provider đi kèm Oracle JDK.
- [JDK 21: Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html) — tên thuật toán và service bảo mật.
- [NIST SP 800-90A Revision 1](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final) — các mô hình DRBG và reseed.
