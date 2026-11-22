# 2.3 Tra cứu tên thuật toán chuẩn, alias và phạm vi hỗ trợ của từng provider

## Mục tiêu

Sau bài này, bạn có thể (1) chọn đúng **service type** và **tên thuật toán chuẩn** khi gọi JCA/JCE, (2) phân biệt tên chuẩn với **alias** mà một provider tự đăng ký, (3) tra cứu các dịch vụ của từng provider, và (4) kiểm tra khả năng dùng thực tế thay vì suy đoán từ danh sách tên.

Trong Java Cryptography Architecture (JCA), ứng dụng yêu cầu một dịch vụ bằng cặp **loại dịch vụ + tên thuật toán**. Ví dụ, `MessageDigest.getInstance("SHA-256")` yêu cầu dịch vụ `MessageDigest` với thuật toán `SHA-256`. JCA tìm một `Provider` có implementation tương ứng (SPI); JCE là phần API cho các chức năng như `Cipher`, `Mac`, `KeyAgreement`. Hai hệ API dùng chung cơ chế provider.

## 1. Phân biệt service type, tên chuẩn, alias và transformation

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Service type / engine** | Nhóm chức năng API; tên thuật toán chỉ có ý nghĩa trong nhóm này | `MessageDigest`, `Signature`, `Mac`, `Cipher`, `KeyFactory` |
| **Standard algorithm name** | Tên quy ước trong *Java Security Standard Algorithm Names*; dùng để viết mã dễ chuyển giữa provider | `SHA-256`, `SHA256withRSA`, `HmacSHA256`, `PBKDF2WithHmacSHA256` |
| **Provider service name** | Tên chính mà provider đăng ký cho một `Provider.Service`; có thể là tên chuẩn hoặc phần mở rộng của provider | `SHA-256` trong một dịch vụ `MessageDigest` |
| **Alias** | Tên thay thế trỏ đến cùng dịch vụ trong **một provider cụ thể**; không được mặc định mọi provider đều hỗ trợ | `SHA256` có thể là alias của `SHA-256` |
| **Cipher transformation** | Tên thuật toán mã hóa kèm mode/padding, có dạng `algorithm/mode/padding` | `AES/GCM/NoPadding` |
| **OID** | Định danh số của thuật toán trong một số chuẩn ASN.1/X.509; khả năng nhận OID làm tên JCA tùy engine/provider | `1.2.840.113549.1.1.11` chỉ là một OID, không phải cú pháp thay thế phổ quát |

Một số cặp engine và tên thường gặp:

| API gọi | Service type | Tên truyền vào |
| --- | --- | --- |
| `MessageDigest.getInstance("SHA-256")` | `MessageDigest` | `SHA-256` |
| `Mac.getInstance("HmacSHA256")` | `Mac` | `HmacSHA256` |
| `Signature.getInstance("SHA256withRSA")` | `Signature` | `SHA256withRSA` |
| `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` | `SecretKeyFactory` | `PBKDF2WithHmacSHA256` |
| `Cipher.getInstance("AES/GCM/NoPadding")` | `Cipher` | transformation đầy đủ |
| `CertificateFactory.getInstance("X.509")` | `CertificateFactory` | `X.509` |

**Không tráo đổi tên giữa các engine:** `SHA-256` là digest, `HmacSHA256` là MAC dùng khóa, còn `SHA256withRSA` là tên thuật toán chữ ký. `AES` cũng không đồng nghĩa với một cấu hình mã hóa có mode và padding đã xác định.

**Tên chuẩn không đồng nghĩa với “chắc chắn được cài”.** Specification quy định cách gọi tên, còn phạm vi implementation đến từ JDK, provider được đăng ký và môi trường vận hành. Tên chuẩn không phân biệt hoa/thường, nhưng một alias như `SHA256` không tự xuất hiện chỉ vì tên `SHA-256` hợp lệ; nên viết đúng dạng chuẩn trong mã ứng dụng.

## 2. JCA phân giải tên thuật toán qua provider thế nào?

Luồng khái quát:

`engine.getInstance(tên [, provider])` → tìm service đúng engine → xét tên chính/alias → tạo implementation → (nếu cần) khởi tạo bằng khóa/tham số → thực hiện thao tác.

- **Không chỉ định provider:** JCA/JCE tìm implementation trong các provider đã cấu hình. `Security.getProviders()` hiển thị danh sách provider đã đăng ký và thứ tự ưu tiên chung; lựa chọn thực tế còn có thể chịu cấu hình ưu tiên riêng theo thuật toán và cơ chế chọn provider khi khởi tạo.
- **Chỉ định provider:** `MessageDigest.getInstance("SHA-256", provider)` hoặc `Cipher.getInstance("AES/GCM/NoPadding", provider)` thử đúng provider được cung cấp; điều này giúp kiểm chứng phạm vi từng provider.
- **Alias có phạm vi cục bộ:** một provider có thể đăng ký `Alg.Alias.MessageDigest.SHA256` trỏ đến `SHA-256`; provider khác có thể không đăng ký alias đó. Cách đăng ký cụ thể là chi tiết của provider.
- **Phân biệt tên trả về:** `Provider.Service.getAlgorithm()` là tên đăng ký của service; `MessageDigest.getAlgorithm()` có thể giữ nguyên tên bạn đã yêu cầu, kể cả alias. Không dùng giá trị trả về từ engine làm bằng chứng tên chuẩn của specification.

Ví dụ, nếu `p.getService("MessageDigest", "SHA256")` trả về service với `getAlgorithm()` bằng `SHA-256`, bạn đã có bằng chứng **provider `p`** nhận `SHA256` làm tên thay thế của dịch vụ đó. Không được suy rộng kết quả sang một provider khác hoặc một bản JDK khác.

## 3. Các API tra cứu và giới hạn của chúng

| Cách tra cứu | Bạn biết được | Điều chưa được chứng minh |
| --- | --- | --- |
| `Security.getProviders()` | Provider đã đăng ký trong JVM đang chạy, thứ tự danh sách và tên/phiên bản của chúng | Một provider có hỗ trợ thuật toán cụ thể hay không |
| `Security.getAlgorithms("MessageDigest")` | Tập tên thuật toán được môi trường quảng bá cho engine đó | Provider cụ thể, alias đầy đủ, hay thao tác với khóa/tham số có thành công không |
| `p.getServices()` | Các service mà provider `p` công bố; mỗi service có `getType()`, `getAlgorithm()`, `getClassName()` | Mọi tên alias có thể dùng và mọi biến thể transformation |
| `p.getService(type, name)` | Service của **provider đó** cho tên chính **hoặc alias**; `null` nếu không tìm thấy | Khởi tạo/thao tác với khóa, mode, padding, phần cứng có thành công không |
| `Security.getProviders("MessageDigest.SHA-256")` | Các provider khớp điều kiện filter đăng ký (có thể trả `null`) | Provider nào được engine chọn ở thời điểm thực thi |
| `MessageDigest.getInstance(name, p)` | Provider `p` có thể cung cấp instance cho tên digest đã hỏi | Mọi API khác hoặc mọi biến thể cùng họ thuật toán đều hoạt động |
| `Cipher.getInstance(transformation, p)` | Provider `p` chấp nhận yêu cầu tạo cipher với transformation cụ thể | Khóa, IV/nonce, độ dài khóa, policy, thiết bị và `doFinal` sẽ thành công |

Không có API công khai `Provider.Service.getAliases()`. Bạn có thể kiểm tra **một alias ứng viên** bằng `getService(type, alias)` hoặc `getInstance(alias, provider)`. Các thuộc tính cũ dạng `Alg.Alias.<type>.<alias>` (nếu có) hữu ích để chẩn đoán, nhưng không nên coi việc duyệt chúng là cách chuẩn, đầy đủ và portable để liệt kê mọi alias.

Với `Cipher`, `p.getService("Cipher", "AES/GCM/NoPadding") == null` **không có nghĩa** provider không làm được AES-GCM: provider có thể đăng ký dịch vụ `Cipher.AES` rồi xử lý mode/padding khi `Cipher.getInstance` phân giải transformation. Vì vậy hãy kiểm tra bằng transformation đầy đủ qua **chính API `Cipher.getInstance`**.

## 4. Chương trình Java 17: tra cứu provider, alias và transformation

Tạo tệp `JcaProviderLookup.java`:

```java
import javax.crypto.Cipher;
import javax.crypto.NoSuchPaddingException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Provider;
import java.security.Security;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;

public class JcaProviderLookup {
    public static void main(String[] args) throws Exception {
        Set<String> digests = Security.getAlgorithms("MessageDigest");
        System.out.println("Registered MessageDigest names: " + digests.size());

        System.out.println("Providers exposing SHA-256 MessageDigest:");
        for (Provider provider : Security.getProviders()) {
            Provider.Service service = provider.getService("MessageDigest", "SHA-256");
            if (service != null) {
                System.out.printf("  %s -> %s%n",
                        provider.getName(), service.getAlgorithm());
            }
        }

        System.out.println("Lookup canonical name and possible alias:");
        for (String name : List.of("SHA-256", "SHA256")) {
            try {
                MessageDigest digest = MessageDigest.getInstance(name);
                System.out.printf("  %s -> algorithm=%s, provider=%s%n",
                        name, digest.getAlgorithm(), digest.getProvider().getName());
            } catch (NoSuchAlgorithmException e) {
                System.out.println("  " + name + " -> unsupported");
            }
        }

        System.out.println("Providers accepting AES/GCM/NoPadding factory:");
        for (Provider provider : Security.getProviders()) {
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", provider);
                System.out.println("  " + provider.getName() + " -> " + cipher.getAlgorithm());
            } catch (NoSuchAlgorithmException | NoSuchPaddingException e) {
                // Provider này không cung cấp transformation được yêu cầu.
            }
        }

        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.println("SHA-256(abc): " + HexFormat.of().formatHex(hash));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac --release 17 JcaProviderLookup.java
java JcaProviderLookup
```

**Cách đọc kết quả:**

- Số lượng digest, tên provider và số dòng từng nhóm **phụ thuộc JDK, provider và cấu hình máy**; không được cố định chúng thành một danh sách “mọi Java đều có”.
- `SHA256` có thể thành công hoặc in `unsupported`. Ngay cả khi thành công, dòng `algorithm=SHA256` không chứng minh đó là tên chuẩn; nó có thể là tên được truyền vào engine.
- Dòng cuối là phần **có kết quả xác định** (khi SHA-256 khả dụng và hoạt động đúng):

```text
SHA-256(abc): ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Mã này dùng `HexFormat` (Java 17+) và không thêm/bớt/thay đổi provider của JVM. Nó kiểm tra khả năng **tạo** `Cipher`, chưa kiểm tra khả năng mã hóa/giải mã thật.

## 5. Kiểm tra alias cho **một provider**, tránh kết luận toàn cục

Đoạn sau minh họa, đặt **bên trong một phương thức có khai báo `throws NoSuchAlgorithmException`** (hoặc xử lý ngoại lệ) và import `java.security.*`:

```java
Provider p = MessageDigest.getInstance("SHA-256").getProvider();
Provider.Service standard = p.getService("MessageDigest", "SHA-256");
Provider.Service candidate = p.getService("MessageDigest", "SHA256");

boolean sameRegisteredService =
        standard != null
        && candidate != null
        && standard.getAlgorithm().equalsIgnoreCase(candidate.getAlgorithm());

System.out.println(p.getName() + " accepts SHA256 alias: "
        + sameRegisteredService);
```

Đây là phép thử với **`p` tại thời điểm hiện tại**. Nó xác định hai tên phân giải đến cùng *tên service đăng ký* trong provider đó; để xác nhận dùng được, hãy gọi thêm `MessageDigest.getInstance("SHA256", p)` rồi thực hiện `digest`. Đừng lấy một danh sách alias của một JDK hoặc một thư viện rồi hardcode với giả định mọi môi trường sẽ nhận.

Một service còn có thể có thuộc tính như `SupportedKeyClasses` hoặc `SupportedKeyFormats` (tùy engine và provider), đọc qua `service.getAttribute(name)`; đây là thông tin hỗ trợ tra cứu, **không thay thế việc khởi tạo bằng khóa thật**.

## 6. “Có hỗ trợ” phải được xác nhận theo từng mức

Ví dụ với `AES/GCM/NoPadding`:

1. **Tên hợp lệ:** tài liệu chuẩn xác nhận các thành phần `AES`, `GCM`, `NoPadding` có ý nghĩa. Điều này chưa chỉ ra provider đang cài.
2. **Đăng ký service:** kiểm tra `p.getServices()` và tên liên quan; không kết luận toàn bộ transformation từ việc nhìn một dòng `Cipher.AES`.
3. **Tạo engine:** thử `Cipher.getInstance("AES/GCM/NoPadding", p)`. Nếu ném `NoSuchAlgorithmException`/`NoSuchPaddingException`, provider đó không đáp ứng yêu cầu factory đã thử.
4. **Khởi tạo và thực thi:** thử `init`, `doFinal` và giải mã/kiểm tra xác thực bằng khóa và tham số đại diện cho môi trường thật. Lỗi `InvalidKeyException`, `InvalidAlgorithmParameterException` hoặc lỗi provider/hardware có thể chỉ xuất hiện ở bước này.

Ví dụ kiểm thử hoạt động thực tế cần tạo khóa AES hợp lệ, nonce 96-bit ngẫu nhiên và `GCMParameterSpec(128, nonce)`; mã hóa bằng `Cipher.ENCRYPT_MODE`, rồi giải mã bằng `Cipher.DECRYPT_MODE` với cùng key/nonce **chỉ để khôi phục đúng một bản mã thử nghiệm** và so sánh plaintext. Với hệ thống thật, **không tái sử dụng cùng nonce cho hai lần mã hóa với cùng khóa GCM**, và phải lưu/truyền nonce tương ứng cùng ciphertext/tag để có thể giải mã. Nếu provider HSM/PKCS#11 yêu cầu khóa nằm trong thiết bị, một `SecretKeySpec` từ RAM có thể bị từ chối dù transformation được hỗ trợ.

Dùng `Cipher.getInstance("AES")` để “kiểm tra AES-GCM” là sai phạm vi: tên `AES` không ấn định mode/padding và có thể chọn giá trị mặc định không an toàn cho ứng dụng. Đối với mật mã khóa đối xứng, luôn nêu rõ transformation được thiết kế.

## 7. Quy trình tra cứu có thể áp dụng trong dự án

1. **Xác định engine và thao tác cần làm.** Ví dụ checksum → `MessageDigest`; MAC có khóa → `Mac`; chữ ký → `Signature`; mã hóa → `Cipher`.
2. **Chọn tên chuẩn đúng phiên bản Java mục tiêu.** Đọc *Java Security Standard Algorithm Names* theo bản Java sẽ triển khai; kiểm tra cả tên mode/padding và yêu cầu tham số.
3. **Chụp thông tin runtime.** Ghi phiên bản Java, tên/phiên bản provider liên quan, `Security.getProviders()`, tên thuật toán đã hỏi và transformation cụ thể.
4. **Lọc provider và kiểm tra alias ứng viên.** Với engine thông thường dùng `p.getService(type, name)` và `getInstance(name, p)`; với `Cipher` kiểm tra trực tiếp transformation trên từng provider.
5. **Xác nhận thao tác.** Với digest: băm test vector; với signature: ký rồi verify; với cipher: round-trip với tham số/khóa thực tế; với provider phần cứng: kiểm tra trên môi trường/slot tương ứng.
6. **Giữ tên chuẩn trong production.** Chỉ dùng alias hoặc tên riêng provider khi có lý do tương thích rõ ràng và test đúng provider/JDK mục tiêu.

### Diễn giải lỗi thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| `NoSuchAlgorithmException` khi gọi `getInstance` | Sai service type/tên, thiếu provider, hoặc provider đã chỉ định không có dịch vụ đó; thử tên chuẩn và tra cứu từng provider |
| `NoSuchPaddingException` | Padding trong transformation không được implementation nhận; kiểm tra đủ `algorithm/mode/padding` |
| `NoSuchProviderException` ở overload dùng tên provider | Tên provider chưa được đăng ký hoặc viết sai; đối chiếu `Security.getProviders()` |
| `getService("Cipher", "AES/GCM/NoPadding") == null` nhưng `Cipher.getInstance` thành công | Provider đăng ký ở mức thuật toán hoặc transformation con; không xem đây là mâu thuẫn |
| Alias chạy trên máy A, lỗi trên máy B | Khác provider, phiên bản JDK, cấu hình bảo mật hoặc module/thiết bị; chuyển sang tên chuẩn và kiểm thử lại |
| `getInstance` thành công, `init` thất bại | Kiểm tra độ dài/loại khóa, tham số, policy, FIPS, quyền HSM và hỗ trợ chế độ cụ thể |
| `getAlgorithms` có tên nhưng thao tác thất bại | Danh sách công bố không cam kết một tổ hợp khóa/params hay trạng thái thiết bị đều hoạt động |

**Lưu ý an toàn:** việc một thuật toán được đăng ký không làm nó phù hợp cho thiết kế mới. MD5, SHA-1 cho chữ ký chống giả mạo, DES và ECB có những hạn chế bảo mật nghiêm trọng; sự hiện diện trong provider có thể nhằm mục đích tương thích. Hãy đánh giá lựa chọn thuật toán, kích thước khóa, mode, xác thực và quản lý nonce theo yêu cầu bảo mật hiện hành.

## 8. Bài tự kiểm tra

- Trên JVM của bạn, những provider nào nhận `MessageDigest/SHA-256`? Mỗi provider công bố tên service nào?
- Với **chính từng provider đó**, `SHA256` có được nhận như alias không? Hãy phân biệt kết quả `getService` với `getInstance`.
- Provider nào chấp nhận `Cipher.getInstance("AES/GCM/NoPadding", p)`? Kết quả có khác với việc tìm `p.getService("Cipher", "AES/GCM/NoPadding")` không? Giải thích lý do.
- Nếu cùng mã chạy khác kết quả ở JDK/máy khác, bạn cần lưu những thông tin nào để tái hiện và kiểm tra vấn đề?

## Tài liệu chính thức

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên chuẩn, engine, mode, padding và các yêu cầu implementation.
- [Java SE 17 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): mô hình engine/provider và cách tìm implementation.
- [Java SE 17 — `Provider` và `Provider.Service`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Provider.html): tra cứu dịch vụ, tên chính và alias.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformation, lựa chọn provider và khởi tạo.
