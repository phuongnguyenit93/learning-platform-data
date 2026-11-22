# 2.8 Xử lý `NoSuchAlgorithmException`, `NoSuchProviderException` và lỗi tham số trong JCA

Trong Java Cryptography Architecture (JCA), một phép toán mật mã thường đi qua ba giai đoạn: **chọn loại dịch vụ/thuật toán và provider**, **khởi tạo bằng khóa/tham số**, rồi **thực hiện phép toán**. Lỗi xuất hiện ở giai đoạn nào cho biết cách sửa đúng: sửa cấu hình, sửa dữ liệu/khóa đầu vào, hay xử lý kết quả xác thực. Không nên gom tất cả thành “lỗi mã hóa” và thử một thuật toán yếu hơn.

Bài này tập trung vào các ngoại lệ của JCA/JCE khi dùng các engine như `MessageDigest`, `Signature`, `KeyGenerator`, `KeyPairGenerator`, `Mac` và `Cipher`. Ví dụ chạy với **Java 17+**; thuật toán, provider và quy tắc vận hành cụ thể vẫn chịu ảnh hưởng của JDK, security policy và provider được cài đặt.

## 1. Ngoại lệ nằm ở đâu trong luồng thực thi?

```text
Cấu hình ứng dụng: engine + tên thuật toán/transformation + provider (tùy chọn)
        |
        v
getInstance(...)  --> Không có thuật toán?     NoSuchAlgorithmException
        |           --> Provider tên chỉ định? NoSuchProviderException
        |           --> Padding không hỗ trợ?  NoSuchPaddingException (Cipher)
        v
init(...)         --> Khóa không phù hợp?      InvalidKeyException
        |           --> Tham số không phù hợp? InvalidAlgorithmParameterException
        |           --> Kích thước/giá trị sai? InvalidParameterException (tùy API)
        v
update/doFinal    --> Giải mã AEAD không xác thực? AEADBadTagException
        |           --> Lỗi vận hành khác?      Các ngoại lệ API cụ thể
        v
Kết quả đã được kiểm tra
```

Ở `getInstance(...)`, JCA tìm **implementation của đúng loại engine** từ security provider. Cùng một chuỗi tên có thể hợp lệ với engine này nhưng vô nghĩa với engine khác: `SHA-256` là tên `MessageDigest`, `HmacSHA256` là tên `Mac`, `AES` là tên thuật toán cho `KeyGenerator`, còn `AES/GCM/NoPadding` là transformation của `Cipher`.

| Ngoại lệ | Checked? | Thường phát sinh tại | Ý nghĩa và cách xử lý |
| --- | --- | --- | --- |
| `NoSuchAlgorithmException` | Có | `getInstance(...)` | Không có implementation cho **engine + algorithm/transformation + provider** đang yêu cầu; kiểm tra tên, loại engine, phiên bản JDK và khả năng provider. |
| `NoSuchProviderException` | Có | `getInstance(algorithm, String providerName)` | Tên provider chỉ định **không được đăng ký** trong JVM; kiểm tra cấu hình/đăng ký provider trước khi chọn thuật toán khác. |
| `NoSuchPaddingException` | Có | `Cipher.getInstance(...)` | Padding của transformation không được hỗ trợ; rà lại toàn bộ `algorithm/mode/padding`, không tự đổi padding. |
| `InvalidKeyException` | Có | `Cipher.init(...)`, `Mac.init(...)`, `Signature.initSign/initVerify(...)` | Khóa sai loại, kích thước, encoding hoặc không được provider chấp nhận. |
| `InvalidAlgorithmParameterException` | Có | `Cipher.init(..., AlgorithmParameterSpec)`, `KeyPairGenerator.initialize(AlgorithmParameterSpec)` | Cấu trúc/tham số thuật toán không phù hợp (ví dụ thông số GCM hoặc nhóm/curve không được hỗ trợ). |
| `InvalidParameterException` | Không | Một số overload `initialize(int)`, `Cipher.init` với `opmode` sai | Giá trị tham số dạng số/chế độ không hợp lệ theo contract API; là `RuntimeException`. |
| `IllegalArgumentException` / `NullPointerException` | Không | Kiểm tra đầu vào và một số factory/constructor | Thường do đầu vào chương trình null, rỗng hoặc sai dạng; chi tiết phụ thuộc **overload**, không được suy luận rằng mọi API ném cùng loại. |
| `InvalidKeySpecException` | Có | `KeyFactory.generatePrivate/generatePublic`, `SecretKeyFactory.generateSecret` | Biểu diễn khóa (`KeySpec`) không phù hợp hoặc không thể chuyển thành khóa theo thuật toán. |
| `AEADBadTagException` | Có | `Cipher.doFinal(...)` khi giải mã AEAD | Xác thực bản tin thất bại: có thể do bản mã, khóa, IV/nonce, tag hoặc AAD không khớp. Không trả về plaintext, không bỏ xác thực để “cứu” dữ liệu. |
| `ProviderException` | Không | Bên trong provider | Lỗi runtime của provider/thiết bị; cần chẩn đoán môi trường, không coi là input validation thông thường. |

**Ghi nhớ:** `GeneralSecurityException` là lớp cha của nhiều checked exceptions ở trên, nhưng **không bao trùm** `InvalidParameterException`, `IllegalArgumentException` hoặc `ProviderException`. Bắt `GeneralSecurityException` quá sớm sẽ làm mất nhánh xử lý cụ thể; bắt `Exception` rồi im lặng sẽ che nguyên nhân.

## 2. Phân biệt chính xác “thiếu thuật toán” và “thiếu provider”

Lấy `MessageDigest` làm ví dụ:

```java
MessageDigest.getInstance("SHA-256");
// Tự tìm provider hỗ trợ MessageDigest/SHA-256 trong cấu hình JVM.

MessageDigest.getInstance("SHA-256", providerName);
// Yêu cầu đúng provider đã đăng ký có tên providerName.

MessageDigest.getInstance("SHA-256", providerObject);
// Dùng đối tượng Provider cụ thể; đối tượng này không nhất thiết đã đăng ký.
```

Ba overload trên có contract khác nhau:

1. **Không chỉ định provider:** `NoSuchAlgorithmException` khi không provider nào được phép/sẵn có cung cấp implementation tương ứng. Không có `NoSuchProviderException` vì không yêu cầu tên provider.
2. **Chỉ định tên `String`:** `NoSuchProviderException` khi tên không được đăng ký; `NoSuchAlgorithmException` khi provider có tồn tại nhưng không cung cấp `MessageDigest/SHA-256`. Với `MessageDigest.getInstance(String, String)`, tên provider null/rỗng gây `IllegalArgumentException`, thuật toán null gây `NullPointerException`.
3. **Chỉ định đối tượng `Provider`:** không có `NoSuchProviderException` trong chữ ký; một provider có thể được truyền trực tiếp dù chưa đăng ký. Nếu implementation thiếu, vẫn là `NoSuchAlgorithmException`; đối tượng provider null gây `IllegalArgumentException`.

Không nên kiểm tra provider bằng tên rồi kết luận rằng nó hỗ trợ mọi thuật toán. `Security.getProvider(name) != null` **chỉ chứng minh tên provider đã được đăng ký**; lời gọi `getInstance` của đúng engine mới là kiểm chứng khả năng thực tế. Với `Cipher`, còn cần kiểm chứng transformation và `init` vì việc lựa chọn implementation/provider có thể tiếp tục trong quá trình khởi tạo.

### 2.1 Lỗi thường bị nhầm

- `MessageDigest.getInstance("AES")` không đúng engine: `AES` là cipher/key algorithm, không phải digest.
- `Cipher.getInstance("SHA-256")` không đúng engine: `SHA-256` dùng để băm, không phải transformation mã hóa.
- `Cipher.getInstance("AES")` không mô tả mode và padding, nên có thể dùng mặc định phụ thuộc provider và không đạt yêu cầu an toàn. Hãy cấu hình transformation đầy đủ như `AES/GCM/NoPadding` khi phù hợp thiết kế.
- Tên provider như `SunJCE`, `SUN` hoặc provider HSM/PKCS#11 không được giả định luôn có trên mọi JVM. **Tên provider khác với tên thuật toán**.
- “Không có provider tên X” và “provider X có nhưng không hỗ trợ thuật toán Y” cần hai hướng sửa khác nhau.

## 3. Ví dụ chạy được: chẩn đoán lỗi lookup

Lưu đúng tên tệp **`JcaLookupDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.NoSuchProviderException;
import java.security.Security;
import java.util.HexFormat;

public final class JcaLookupDemo {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        try {
            MessageDigest.getInstance("NO_SUCH_DIGEST_FOR_DEMO_2026");
        } catch (NoSuchAlgorithmException ex) {
            System.out.println("1. Khong co thuat toan MessageDigest");
        }

        String missingProvider = "TRAINING_PROVIDER_NOT_INSTALLED";
        while (Security.getProvider(missingProvider) != null) {
            missingProvider += "_";
        }

        try {
            MessageDigest.getInstance("SHA-256", missingProvider);
        } catch (NoSuchProviderException ex) {
            System.out.println("2. Provider chua duoc dang ky");
        }

        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        byte[] bytes = sha256.digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.println("3. SHA-256(abc): " + HexFormat.of().formatHex(bytes));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 JcaLookupDemo.java
java JcaLookupDemo
```

Kết quả trên JDK Java 17+ thông thường (không có custom provider cố tình đăng ký tên thuật toán demo):

```text
1. Khong co thuat toan MessageDigest
2. Provider chua duoc dang ky
3. SHA-256(abc): ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

**Giải thích:**

- Lần gọi thứ nhất yêu cầu một thuật toán digest không được cài đặt. Ngoại lệ xuất hiện **trước** khi băm dữ liệu.
- Lần gọi thứ hai dùng thuật toán có sẵn `SHA-256` nhưng yêu cầu tên provider không được đăng ký; vòng `while` tránh trùng tên ngẫu nhiên với một provider hiện có.
- Lần cuối để JCA tự chọn provider hỗ trợ `SHA-256` và băm `abc`. `HexFormat` có từ Java 17 nên không cần thư viện ngoài.

Đây là minh họa để **phân biệt hai ngoại lệ**, không phải cơ chế thử tuần tự tên provider trong production. Ứng dụng nên cấu hình thuật toán đã kiểm duyệt và chỉ pin provider khi có yêu cầu kỹ thuật hoặc tuân thủ cụ thể.

## 4. “Lỗi tham số” phát sinh ở giai đoạn nào?

**(a) Tham số đầu vào của Java/API:** `null`, tên rỗng, chế độ hoạt động sai, kích thước âm. Nên kiểm tra sớm bằng `Objects.requireNonNull`, kiểm tra tập giá trị cho phép và độ dài, sau đó dùng lỗi lập trình/cấu hình phù hợp. Không dựa vào một loại ngoại lệ giống nhau cho mọi engine.

**(b) Tham số thuật toán:** `GCMParameterSpec`, `PBEParameterSpec`, `ECGenParameterSpec`, `AlgorithmParameterSpec` khác. Một object có thể tạo được nhưng vẫn bị provider từ chối tại `init`, thường bằng `InvalidAlgorithmParameterException`. Việc hỗ trợ cỡ tag, key, curve hoặc parameter set có thể phụ thuộc provider và security policy.

**(c) Khóa:** `SecretKey`, `PrivateKey`, `PublicKey` có thể sai thuật toán, độ dài hoặc không tương thích với thao tác. `InvalidKeyException` xuất hiện khi khởi tạo `Cipher`, `Mac`, `Signature`; không nên biến nó thành `NoSuchAlgorithmException` hoặc thử khóa khác một cách âm thầm. Nếu lỗi xảy ra lúc chuyển đổi `KeySpec`, hãy xem `InvalidKeySpecException`.

**(d) Bản tin đầu vào sau khởi tạo:** với authenticated encryption (AEAD) như AES-GCM, `AEADBadTagException` là **thất bại xác thực**, không đồng nghĩa provider bị thiếu và cũng không nhất thiết là “tham số đầu vào sai”. Tất cả khóa, nonce/IV, tag và AAD phải khớp giữa hai đầu.

Ví dụ ký hiệu:

```java
// Chọn transformation: lỗi lookup có thể là NoSuchAlgorithmException
// hoặc NoSuchPaddingException.
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");

// Khởi tạo: key sai có thể là InvalidKeyException;
// thông số GCM không phù hợp có thể là InvalidAlgorithmParameterException.
cipher.init(Cipher.ENCRYPT_MODE, aesKey, new GCMParameterSpec(128, iv));

// Khi giải mã GCM: doFinal(...) có thể ném AEADBadTagException
// nếu dữ liệu không xác thực. Đừng bỏ qua kiểm tra này.
```

Đoạn trên là **mã minh họa từng API**, chưa phải chương trình độc lập: cần định nghĩa `aesKey`, `iv` và ngữ cảnh gọi. Ví dụ chạy đầy đủ ở mục kế tiếp.

### 4.1 Checklist tham số an toàn cho AES-GCM

- Chỉ sử dụng khóa AES hợp lệ, thông thường **128/192/256 bit** theo chính sách. Không lấy mật khẩu thô hoặc chuỗi UTF-8 tùy ý làm khóa AES; dùng KDF thích hợp nếu xuất phát từ mật khẩu.
- Trong ví dụ, dùng IV dài **12 byte (96 bit)** và tag **128 bit**. Đó là cấu hình khuyến nghị phổ biến, không phải khẳng định mọi provider chấp nhận mọi tổ hợp kích thước.
- **Không bao giờ dùng lại cùng cặp (key, IV/nonce) khi mã hóa GCM.** Với lưu lượng lớn, cần thiết kế quản lý nonce để kiểm soát va chạm; chỉ tạo IV ngẫu nhiên trong ví dụ đơn giản không thay thế thiết kế đó.
- Có thể công khai IV cùng bản mã; IV không phải khóa bí mật. Tag thường nằm ở cuối byte array trả về từ `Cipher.doFinal` của GCM.
- AAD, nếu sử dụng, phải giống hệt lúc mã hóa/giải mã và được đưa qua `updateAAD(...)` **trước** phần dữ liệu.
- Không phát tán plaintext chưa được xác thực và không tự bỏ tag, đổi mode hay đổi thuật toán để qua lỗi `AEADBadTagException`.

## 5. Ví dụ chạy được: tách lỗi khởi tạo và lỗi xác thực AES-GCM

Ví dụ này dùng provider mặc định có hỗ trợ `AES/GCM/NoPadding`, đóng gói `IV(12 byte) || ciphertext+tag`, mã hóa/giải mã thành công và cố ý sửa tag để thấy nhánh lỗi. Lưu đúng tên **`GcmFailureDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.InvalidAlgorithmParameterException;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.NoSuchPaddingException;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class GcmFailureDemo {
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;

    public static void main(String[] args) {
        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128);
            SecretKey key = generator.generateKey();

            byte[] payload = encrypt("Hello JCA".getBytes(StandardCharsets.UTF_8), key);
            byte[] recovered = decrypt(payload, key);
            System.out.println("Giai ma: " + new String(recovered, StandardCharsets.UTF_8));

            byte[] tampered = payload.clone();
            tampered[tampered.length - 1] ^= 1; // Sua mot bit cua tag.
            try {
                decrypt(tampered, key);
                throw new AssertionError("Tag da sua ma van duoc chap nhan");
            } catch (AEADBadTagException ex) {
                System.out.println("Tag bi sua: xac thuc that bai");
            }

        } catch (NoSuchAlgorithmException | NoSuchPaddingException ex) {
            throw new IllegalStateException("Algorithm/transformation khong kha dung", ex);
        } catch (InvalidKeyException | InvalidAlgorithmParameterException ex) {
            throw new IllegalArgumentException("Key hoac tham so khong hop le", ex);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("Loi xu ly mat ma", ex);
        }
    }

    private static byte[] encrypt(byte[] plain, SecretKey key)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_BYTES];
        new SecureRandom().nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        byte[] ciphertextWithTag = cipher.doFinal(plain);

        byte[] payload = new byte[IV_BYTES + ciphertextWithTag.length];
        System.arraycopy(iv, 0, payload, 0, IV_BYTES);
        System.arraycopy(ciphertextWithTag, 0, payload, IV_BYTES,
                ciphertextWithTag.length);
        return payload;
    }

    private static byte[] decrypt(byte[] payload, SecretKey key)
            throws GeneralSecurityException {
        if (payload == null || payload.length < IV_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Payload thieu IV hoac tag");
        }

        byte[] iv = Arrays.copyOfRange(payload, 0, IV_BYTES);
        byte[] ciphertextWithTag = Arrays.copyOfRange(payload, IV_BYTES,
                payload.length);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        return cipher.doFinal(ciphertextWithTag);
    }
}
```

```bash
javac -encoding UTF-8 GcmFailureDemo.java
java GcmFailureDemo
```

Kết quả với provider JDK thông thường hỗ trợ AES-GCM:

```text
Giai ma: Hello JCA
Tag bi sua: xac thuc that bai
```

Ý nghĩa các nhánh:

- `NoSuchAlgorithmException` / `NoSuchPaddingException`: engine hoặc transformation không khả dụng ở môi trường này. Đây thường là lỗi **khả năng/cấu hình**, nên phát hiện khi khởi động.
- `InvalidKeyException` / `InvalidAlgorithmParameterException`: kiểm tra nguồn khóa, loại khóa, size, transformation, IV/tag/AAD và provider. **Không** chuyển sang cipher/mode yếu hơn.
- `AEADBadTagException`: xử lý như **bản tin không xác thực**, trả thông báo thích hợp cho bên gọi nhưng không tiết lộ khóa, plaintext hoặc chi tiết mật mã nhạy cảm.
- `IllegalArgumentException` do payload thiếu cấu trúc hợp lệ là lỗi **kiểm tra đầu vào của chương trình**; nó khác với ngoại lệ checked do provider ném.
- `GeneralSecurityException` cuối cùng chỉ dành cho các trường hợp chưa được phân loại; vẫn phải giữ `cause` để điều tra trong hệ thống tin cậy.

Việc sửa một bit trong tag tạo lỗi xác thực trên provider GCM bình thường; nguyên tắc an toàn là **từ chối** dữ liệu khi kiểm tra tag thất bại. Ví dụ không hướng dẫn lưu khóa lâu dài, xoay khóa hoặc format dữ liệu liên phiên bản; các phần đó cần thiết kế riêng trong hệ thống thực tế.

## 6. Chiến lược xử lý lỗi đúng trong ứng dụng

### 6.1 Phân loại theo nguyên nhân và thời điểm

| Nhóm | Ví dụ | Hành động khuyến nghị |
| --- | --- | --- |
| **Cấu hình/khả năng không hợp lệ** | Sai algorithm, sai transformation, provider chưa cài, thiếu HSM provider | Kiểm tra ngay lúc startup; ghi log đã lọc thông tin về engine, tên thuật toán, tên provider và môi trường; **fail fast** thay vì vận hành âm thầm với thuật toán khác. |
| **Dữ liệu/khóa/tham số không hợp lệ** | Key sai độ dài, `AlgorithmParameterSpec` không được chấp nhận, payload thiếu IV/tag | Kiểm tra nguồn dữ liệu; phân biệt lỗi client với lỗi cấu hình nội bộ; xử lý theo contract của API. |
| **Xác thực thất bại** | `AEADBadTagException` | Từ chối bản tin; không trả plaintext; không thử chế độ không xác thực để khôi phục. |
| **Provider/runtime lỗi** | `ProviderException`, lỗi thiết bị mật mã, khả năng provider thay đổi | Thu thập telemetry có kiểm soát, cảnh báo và điều tra môi trường; chỉ retry khi operation thực sự an toàn/idempotent và chính sách cho phép. |

Hãy xác định rõ **ai sở hữu cấu hình** trước khi quyết định phản hồi. Nếu ứng dụng cấu hình `AES/GCM/NoPadding` cố định mà JVM không hỗ trợ, lỗi đó thường phải được sửa ở triển khai, không được quy thành lỗi nhập liệu của người dùng. Nếu API nhận payload từ client và thiếu IV, ứng dụng có thể từ chối đầu vào theo contract. Với payload mã hóa sai tag, không tiết lộ chi tiết đủ để tạo oracle phân biệt nhiều dạng thất bại.

### 6.2 Mẫu kiểm tra cấu hình lúc khởi động

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.NoSuchProviderException;
import java.security.Security;
import java.util.Set;

public final class DigestFactory {
    private static final Set<String> ALLOWED = Set.of("SHA-256", "SHA-384", "SHA-512");

    public static MessageDigest create(String algorithm, String providerName)
            throws NoSuchAlgorithmException, NoSuchProviderException {
        if (algorithm == null || !ALLOWED.contains(algorithm)) {
            throw new IllegalArgumentException("Digest algorithm ngoai allowlist");
        }

        // null/rong mang nghia la de JCA tu chon provider.
        if (providerName == null || providerName.isBlank()) {
            return MessageDigest.getInstance(algorithm);
        }

        if (Security.getProvider(providerName) == null) {
            throw new NoSuchProviderException("Provider khong duoc dang ky: "
                    + providerName);
        }
        return MessageDigest.getInstance(algorithm, providerName);
    }
}
```

Đây là **lớp hỗ trợ biên dịch độc lập nhưng không có `main`**: gọi `DigestFactory.create(...)` ở bước khởi tạo cấu hình ứng dụng. Tên thuật toán được giới hạn bằng allowlist; `providerName` chỉ là tùy chọn khi chính sách cho phép chạy độc lập provider. Nếu chính sách **bắt buộc HSM/provider cụ thể**, không được đổi sang provider mặc định khi gặp `NoSuchProviderException`.

Không nên dùng dữ liệu request không đáng tin cậy để quyết định thuật toán/provider. Nếu cần hỗ trợ migration, hãy thiết kế **phiên bản định dạng + allowlist thuật toán đã phê duyệt**; chỉ chuyển giữa các cấu hình tương đương đáp ứng chính sách, không fallback từ thuật toán hiện đại sang MD5, SHA-1 cho chức năng bảo mật, DES, ECB hoặc mode không xác thực.

### 6.3 Chẩn đoán có thứ tự

1. **Xác định API vừa ném lỗi:** `MessageDigest`, `Cipher`, `KeyPairGenerator` hay `Signature`? Ghi nhận đúng `getInstance`, `init`, `doFinal` thay vì đoán chỉ từ thông điệp ngoại lệ.
2. **Kiểm tra tên chính xác và loại engine:** `SHA-256` khác `HmacSHA256`; `AES/GCM/NoPadding` là transformation của `Cipher`; không chỉ sửa chữ hoa/thường theo cảm tính.
3. **Nếu chỉ định provider theo tên:** `Security.getProvider(providerName)` có `null` không? Nếu có provider, gọi đúng `getInstance` để xác minh dịch vụ/thuật toán. Có thể liệt kê `Security.getProviders()` và `Security.getAlgorithms("MessageDigest")` để khám phá môi trường, nhưng danh sách không thay thế việc khởi tạo thực tế.
4. **Xác nhận runtime:** version/vendor JDK, security properties, provider priority, module/dependency của provider ngoài JDK, HSM/PKCS#11 và khác biệt dev/test/prod. Một implementation có trên laptop không bảo đảm có trong container production.
5. **Nếu lỗi tại `init`:** so sánh thuật toán của `Key`, kích thước khóa, mode, `AlgorithmParameterSpec`, tag/IV/nonce, policy và API overload đã dùng.
6. **Nếu lỗi tại `doFinal`:** kiểm tra định dạng payload, tính toàn vẹn và AAD. Với AEAD, phân loại thất bại xác thực; không ghi khóa, plaintext hay vật liệu mật mã nhạy cảm vào log.
7. **Ghi nguyên nhân có kiểm soát:** ở log nội bộ lưu loại ngoại lệ, vị trí giai đoạn, thuật toán/provider không nhạy cảm, mã tương quan và `cause`; phản hồi công khai dùng thông báo an toàn, không đưa stack trace/provider internals ra client.

Chẩn đoán dưới đây chỉ liệt kê **tên** provider/thuật toán, không xuất vật liệu mật mã. Chạy trong môi trường tin cậy khi cần:

```java
import java.security.Provider;
import java.security.Security;

public class JcaEnvironmentInfo {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println("Provider: " + provider.getName());
        }
        System.out.println("Digest algorithms: "
                + Security.getAlgorithms("MessageDigest"));
    }
}
```

Kết quả **phụ thuộc JVM** nên không có một stdout cố định. Không dùng danh sách này để chọn ngẫu nhiên “thuật toán đầu tiên chạy được”.

## 7. Anti-pattern và cách sửa

| Cách làm sai | Vì sao nguy hiểm/khó debug | Cách thay thế |
| --- | --- | --- |
| `catch (Exception e) { return null; }` | Nuốt nguyên nhân, tạo `NullPointerException` ở xa nguồn. | Phân loại ngoại lệ, giữ cause, trả/throw lỗi mang ngữ cảnh. |
| Gặp `NoSuchAlgorithmException` thì thử `MD5`, `SHA-1`, `DES` hoặc `AES/ECB/...`. | Hạ tiêu chuẩn bảo mật âm thầm; có thể thay đổi tính chất dữ liệu. | Kiểm tra cấu hình, dependency và provider; fail fast hoặc migration theo chính sách đã phê duyệt. |
| Bắt `NoSuchProviderException` rồi bỏ tên provider và retry mặc định. | Có thể chuyển thao tác ra ngoài HSM/provider bắt buộc. | Chỉ được fallback provider khi chính sách cho phép một cách rõ ràng; nếu không, dừng và báo lỗi triển khai. |
| Gộp `InvalidKeyException`, `AEADBadTagException`, `NoSuchAlgorithmException` thành “sai mật khẩu”. | Che lỗi hệ thống, rò rỉ logic và làm sai vận hành. | Tách nhóm cấu hình, tham số/khóa và xác thực thất bại. |
| Truyền nguyên chuỗi tự do từ request vào `Cipher.getInstance`. | Người gọi có thể quyết định thuật toán/mode ngoài chính sách. | Cố định cấu hình hoặc ánh xạ mã phiên bản sang allowlist. |
| Dùng lại IV với cùng key GCM hoặc bỏ qua `AEADBadTagException`. | Gây tổn hại tính bảo mật/toàn vẹn dữ liệu. | Bảo đảm nonce duy nhất; từ chối bản tin không xác thực. |
| Ghi key, plaintext, raw secret, stack trace đầy đủ ra log công khai. | Rò rỉ dữ liệu nhạy cảm. | Ghi mã lỗi/correlation ID và thông tin cấu hình phi bí mật ở log được bảo vệ. |

## 8. Tự kiểm tra hiểu bài

**Tình huống A.** `MessageDigest.getInstance("AES")` ném `NoSuchAlgorithmException`. Có nên cài thêm provider ngay?  
**Giải:** Trước hết xem lại **engine**; `AES` không phải digest. Dùng `MessageDigest` cho `SHA-256` hoặc engine phù hợp với mục tiêu thực tế. Không mặc định là thiếu provider.

**Tình huống B.** `MessageDigest.getInstance("SHA-256", "MyHsm")` ném `NoSuchProviderException`.  
**Giải:** Tên `MyHsm` chưa được đăng ký trong JVM. Kiểm tra cài đặt/khởi tạo provider, tên và cấu hình runtime. Nếu quy định dùng HSM, dừng thay vì tự đổi provider.

**Tình huống C.** Provider có tên `MyHsm`, nhưng cùng câu lệnh ném `NoSuchAlgorithmException`.  
**Giải:** Provider đã tồn tại nhưng không cung cấp implementation `MessageDigest/SHA-256` theo yêu cầu. Kiểm tra đúng engine, thuật toán, provider capabilities và policy.

**Tình huống D.** `Cipher.getInstance("AES/GCM/NoPadding")` thành công, nhưng `init` thất bại.  
**Giải:** Đây là lúc xét `InvalidKeyException` hoặc `InvalidAlgorithmParameterException`, chứ không mặc nhiên kết luận thiếu thuật toán. Kiểm tra key, tag/nonce và contract provider.

**Tình huống E.** `Cipher.doFinal` lúc giải mã GCM ném `AEADBadTagException`.  
**Giải:** Thất bại xác thực; không trả plaintext và không dùng mode bỏ xác thực. Điều tra nguồn bản mã, key, IV/nonce, tag, AAD và định dạng dữ liệu.

### Tiêu chí hoàn thành

Người học có thể: (1) chỉ ra đúng giai đoạn ném lỗi; (2) phân biệt ba overload `getInstance` với provider; (3) tách `InvalidKeyException`, `InvalidAlgorithmParameterException`, `InvalidParameterException` và lỗi xác thực; (4) khởi tạo JCA/JCE với cấu hình rõ ràng và **không fallback hạ cấp bảo mật**; (5) tái hiện, chẩn đoán, báo lỗi có giữ nguyên nhân mà không lộ secret.

## Tài liệu chính thức

- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): ba overload `getInstance` và các ngoại lệ.
- [Java SE 21 — NoSuchProviderException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/NoSuchProviderException.html): định nghĩa provider được yêu cầu nhưng không khả dụng.
- [Java SE 21 — Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): transformation, `getInstance`, `init`, GCM/AEAD và `doFinal`.
- [Java SE 21 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html): `InvalidParameterException` với keysize và `InvalidAlgorithmParameterException` với `AlgorithmParameterSpec`.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên thuật toán/engine tiêu chuẩn và các transformation.