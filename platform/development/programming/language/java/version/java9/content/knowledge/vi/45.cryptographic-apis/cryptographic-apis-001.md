# Chọn thuật toán và provider qua API JCA được hỗ trợ

## 1. Vì sao phải chọn cả thuật toán lẫn provider?

**Java Cryptography Architecture (JCA)** là bộ API mật mã chuẩn của nền tảng Java, bao gồm các lớp thuộc `java.security` và `javax.crypto` (phần mã hóa đối xứng thường được gọi là JCE). Ứng dụng yêu cầu một **dịch vụ mật mã** và **thuật toán** bằng API chung; một **security provider** được cài đặt trong môi trường Java cung cấp phần triển khai.

Ví dụ, lời gọi:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
```

đề nghị dịch vụ `MessageDigest` với thuật toán `SHA-256`. JCA tìm một provider thích hợp trong cấu hình runtime; ứng dụng không cần biết lớp triển khai nội bộ. Cơ chế này vẫn là cách làm chuẩn trên Java hiện đại; đây **không phải tính năng riêng mới xuất hiện từ Java 9**.

Cần phân biệt ba khái niệm:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Engine/API** | `MessageDigest`, `Cipher`, `Signature`, `KeyPairGenerator` | Loại thao tác mà ứng dụng yêu cầu |
| **Tên thuật toán/transformation** | `SHA-256`, `AES/GCM/NoPadding`, `Ed25519` | Hành vi mật mã mà thao tác phải thực hiện |
| **Provider** | Một đối tượng `java.security.Provider` đang khả dụng | Triển khai cụ thể của dịch vụ và thuật toán trên runtime |

Một tên có trong đặc tả **Java Security Standard Algorithm Names** chưa bảo đảm mọi provider đều hỗ trợ nó, mọi khóa/độ dài khóa đều hoạt động hay thuật toán đó phù hợp cho hệ thống mới. Hãy xem **tên chuẩn + khả năng của runtime + yêu cầu bảo mật** là ba bước kiểm chứng riêng biệt.

### Các engine hay dùng

| Nhu cầu | API chuẩn | Ví dụ tên được dùng hiện nay |
| --- | --- | --- |
| Tạo mã băm thông điệp | `MessageDigest.getInstance(algorithm)` | `SHA-256`, `SHA3-256` |
| Kiểm tra toàn vẹn/xác thực với khóa bí mật | `Mac.getInstance(algorithm)` | `HmacSHA256` |
| Mã hóa/giải mã | `Cipher.getInstance(transformation)` | `AES/GCM/NoPadding`, `ChaCha20-Poly1305` |
| Tạo khóa đối xứng | `KeyGenerator.getInstance(algorithm)` | `AES` |
| Tạo cặp khóa công khai/bí mật | `KeyPairGenerator.getInstance(algorithm)` | `Ed25519`, `EC`, `RSA` |
| Ký/xác minh chữ ký số | `Signature.getInstance(algorithm)` | `Ed25519`, `RSASSA-PSS`, `SHA256withECDSA` |
| Chuyển đổi khóa và đặc tả khóa | `KeyFactory.getInstance(algorithm)` | `RSA`, `EC`, `Ed25519` |
| Sinh khóa từ mật khẩu | `SecretKeyFactory.getInstance(algorithm)` | `PBKDF2WithHmacSHA256` |
| Thỏa thuận khóa | `KeyAgreement.getInstance(algorithm)` | `X25519`, `ECDH` |
| Kho khóa/chứng chỉ | `KeyStore.getInstance(type)`, `CertificateFactory.getInstance(type)` | `PKCS12`, `X.509` |

Lưu ý: `MessageDigest` chỉ tạo hàm băm, **không** thay thế MAC hoặc chữ ký số; `Cipher` mã hóa nhưng mức bảo đảm toàn vẹn phụ thuộc mode (AEAD như GCM có kiểm tra xác thực); `SecureRandom` cung cấp byte ngẫu nhiên có tính mật mã, không phải hàm băm hay bộ tạo khóa tương đương.

## 2. Ba cách chọn provider bằng `getInstance`

Đa số engine JCA có các overload tương tự:

```java
// 1. Để JCA chọn theo cấu hình runtime.
MessageDigest automatic = MessageDigest.getInstance("SHA-256");

// 2. Gắn theo tên provider đã đăng ký.
MessageDigest byName =
    MessageDigest.getInstance("SHA-256", "TenProviderDaDuocCaiDat");

// 3. Gắn một đối tượng Provider được cấp chủ động.
Provider chosen = automatic.getProvider();
MessageDigest byObject = MessageDigest.getInstance("SHA-256", chosen);
```

Các dòng trên là **đoạn minh họa API**, không phải chương trình chạy độc lập; `"TenProviderDaDuocCaiDat"` là tên thay thế cần xác định tại runtime, không phải một provider có sẵn.

**Không chỉ định provider — mặc định nên dùng:** `getInstance("SHA-256")` chọn triển khai từ các provider khả dụng. Cách này cho phép JVM dùng provider được cấu hình hay tối ưu cho hệ thống (phần cứng, hệ điều hành, chính sách triển khai). Đây là lựa chọn ưu tiên cho ứng dụng thông thường, phù hợp tính độc lập với nhà cung cấp.

**Chỉ định tên — khi thật sự cần ràng buộc:** `getInstance("...", "TênProvider")` yêu cầu đúng provider đã đăng ký. Nếu không có tên này, phát sinh `NoSuchProviderException` (với các engine hỗ trợ overload); nếu provider có mặt nhưng không hỗ trợ thuật toán, phát sinh `NoSuchAlgorithmException`. Không tự ý đổi sang một thuật toán yếu hơn khi xử lý ngoại lệ.

**Chỉ định đối tượng — khi ứng dụng đã chọn/nhận `Provider`:** `getInstance("...", provider)` dùng chính đối tượng provider đó; tùy engine, đối tượng có thể không cần được đăng ký trong danh sách chung. Đây là cách thích hợp khi một thành phần ứng dụng quản lý provider cụ thể hoặc có quy tắc tuân thủ/thiết bị riêng. Tuy nhiên, không phải engine và provider nào cũng có thể dùng mọi khóa từ provider khác.

> **Quy tắc chọn:** Nếu yêu cầu chỉ là “tính SHA-256”, “mã hóa AES-GCM”, “ký Ed25519”, hãy chỉ định **thuật toán đúng** và để JCA chọn provider. Chỉ khóa provider khi có yêu cầu được kiểm chứng: HSM/PKCS#11, chứng nhận tuân thủ, khóa nằm trong thiết bị, cách lưu khóa hoặc hành vi chuyên biệt bắt buộc.

### Thứ tự provider không hoàn toàn là hợp đồng của ứng dụng

`Security.getProviders()` trả các provider đã đăng ký theo thứ tự ưu tiên chung. Java dùng cấu hình bảo mật runtime, thường tại `$JAVA_HOME/conf/security/java.security`, để quản lý danh sách provider. JDK cũng có cấu hình ưu tiên theo **thuật toán** như `jdk.security.provider.preferred`, nên không nên tự suy luận rằng provider đầu tiên của `Security.getProviders()` chắc chắn xử lý mọi thuật toán.

Đặc biệt, một số engine như `Cipher` có thể trì hoãn quyết định provider cho đến khi biết khóa/`init(...)`. Khi cần quan sát provider thực sự được dùng, hãy kiểm tra `engine.getProvider()` **sau khi khởi tạo thành công** cho thao tác cụ thể; đừng coi kết quả liệt kê provider là bằng chứng rằng cipher đã dùng đúng provider đó.

Thay đổi danh sách toàn JVM bằng `Security.addProvider`, `insertProviderAt` hoặc `removeProvider` làm thay đổi hành vi toàn ứng dụng. Chỉ làm việc đó khi quản lý cấu hình runtime/provider một cách có chủ đích, không lạm dụng ở từng request.

## 3. Cách khám phá thuật toán và provider đang thực sự có

Không cần đoán provider từ tên hệ điều hành hay cấu hình của máy phát triển.

```java
import java.security.Provider;
import java.security.Security;

Provider[] installed = Security.getProviders(); // Thứ tự ưu tiên chung

Provider[] sha256Providers =
    Security.getProviders("MessageDigest.SHA-256");
if (sha256Providers == null || sha256Providers.length == 0) {
    throw new IllegalStateException("Runtime thiếu SHA-256");
}

for (Provider provider : sha256Providers) {
    System.out.println(provider.getName());
}
```

Đây là **đoạn thăm dò môi trường**, tên provider in ra khác nhau theo JDK, hệ điều hành và cấu hình; không có một stdout cố định để ghi nhớ. Chuỗi lọc `"MessageDigest.SHA-256"` có dạng **`<service>.<algorithm>`**, không phải phương pháp đánh giá độ an toàn của thuật toán.

Các cách quan sát bổ sung:

- `Security.getProvider(name)` trả một provider đã đăng ký hoặc `null`.
- `Security.getAlgorithms("MessageDigest")` trả tập tên thuật toán được đăng ký cho engine tương ứng.
- `provider.getServices()` và `provider.getService("MessageDigest", "SHA-256")` giúp xem dịch vụ mà provider công bố.
- `MessageDigest.getInstance("SHA-256").getProvider()` cho biết triển khai được chọn cho engine vừa yêu cầu.
- Với `Cipher`, hãy gọi `getInstance("AES/GCM/NoPadding")`, `init` bằng khóa/tham số hợp lệ rồi mới ghi nhận provider và kết quả thử nghiệm.

**Không áp dụng máy móc bộ lọc `Security.getProviders("Cipher.AES/GCM/NoPadding")`:** provider có thể đăng ký cipher theo thuật toán cơ sở `AES` kết hợp khả năng mode/padding, chứ không đăng ký chuỗi transformation như một dịch vụ độc lập. Để kiểm chứng transformation dùng được, hãy yêu cầu `Cipher.getInstance(...)` và **khởi tạo bằng khóa, nonce, tham số thực tế**.

### Tên chuẩn và tên alias

Dùng cách viết được công bố trong [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html), chẳng hạn `SHA-256`, `HmacSHA256`, `AES/GCM/NoPadding`. Một provider có thể công bố alias thuận tiện, nhưng alias không bảo đảm hoạt động ở provider khác. Tên thuật toán chuẩn thường không phân biệt chữ hoa/thường, song việc dùng đúng cách viết chuẩn giúp dễ đọc và kiểm thử.

Đặc biệt, tham số của `Cipher` là **transformation**:

```text
algorithm/mode/padding
```

Ví dụ `AES/GCM/NoPadding` khác `AES`: nếu chỉ gọi `Cipher.getInstance("AES")`, mode và padding còn phụ thuộc mặc định của provider, có thể dẫn đến ECB không thích hợp khi mã hóa dữ liệu ứng dụng. Hãy ghi rõ transformation và các tham số cần thiết.

## 4. Quy trình quyết định trong ứng dụng thực tế

1. **Xác định mục đích bảo mật.** Cần tính dấu vân tay dữ liệu, xác thực thông điệp, mã hóa có kiểm tra toàn vẹn, chữ ký số, sinh khóa hay lưu khóa? Mỗi mục đích dùng engine khác nhau.
2. **Chọn thuật toán và tham số đã được chấp thuận cho hệ thống mới.** Ví dụ AES-GCM với khóa 128/256 bit và tag 128 bit; HMAC-SHA-256; Ed25519 khi hệ thống và giao thức hỗ trợ. Cân nhắc tính tương thích với bên nhận và chính sách tổ chức.
3. **Dùng tên chuẩn trong `getInstance`**, để JCA tự chọn provider trừ khi có yêu cầu đặc biệt. Không dùng tên provider nội bộ của một bản JDK làm điều kiện bắt buộc nếu không cần.
4. **Khởi tạo với khóa/tham số thực tế** và thử thao tác cần dùng. Việc tìm thấy tên thuật toán không chứng minh provider hỗ trợ kích thước khóa, loại khóa, mode hay đặc tính cần thiết.
5. **Ghi nhận chẩn đoán khi cần:** loại engine, tên thuật toán/transformation, `getProvider().getName()` sau khi khởi tạo, phiên bản runtime; không log khóa, mật khẩu, plaintext, nonce bí mật (nonce GCM không phải bí mật nhưng không cần log hàng loạt), seed hoặc dữ liệu nhạy cảm.
6. **Thất bại rõ ràng khi không đáp ứng yêu cầu.** Không âm thầm fallback từ AES-GCM sang ECB, từ SHA-256 sang SHA-1, hay chuyển khóa HSM sang provider phần mềm nếu quy tắc yêu cầu khóa không rời thiết bị.

Bảng lựa chọn minh họa:

| Mục tiêu | API và lựa chọn phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Băm tài liệu để so khớp byte | `MessageDigest` + `SHA-256` | Băm **không xác thực nguồn gửi** |
| Xác thực thông điệp dùng khóa chung | `Mac` + `HmacSHA256` | Khóa bí mật phải được bảo vệ, hai bên đồng bộ định dạng dữ liệu |
| Mã hóa dữ liệu ứng dụng | `Cipher` + `AES/GCM/NoPadding` | Nonce duy nhất theo khóa, tag xác thực, quản lý khóa và AAD |
| Ký số hiện đại | `Signature` + `Ed25519` hoặc `RSASSA-PSS` | Khóa, định dạng chữ ký, giao thức tương thích, tham số PSS |
| Sinh khóa AES | `KeyGenerator` + `AES` | Kích thước khóa và nguồn ngẫu nhiên mật mã |
| Dẫn xuất từ mật khẩu | `SecretKeyFactory` + `PBKDF2WithHmacSHA256` | Salt riêng, số vòng lặp phù hợp chính sách, chống thử mật khẩu |
| Dùng khóa nằm trong HSM | `KeyStore`/`Signature`/`Cipher` với provider tương ứng | Đăng ký provider, loại khóa không xuất được, chính sách thiết bị |

**Lưu ý:** PBKDF2 là lựa chọn được API chuẩn hỗ trợ nhưng không mặc nhiên là phương án tốt nhất cho mọi hệ thống lưu mật khẩu. Khi thiết kế cơ chế lưu mật khẩu mới, cần đánh giá một KDF chống tấn công phần cứng chuyên dụng theo yêu cầu hiện hành; các lựa chọn như Argon2id không thuộc bộ `getInstance` chuẩn được bảo đảm có sẵn trong mọi JDK. Không dùng `MessageDigest("SHA-256")` trực tiếp làm hàm băm mật khẩu.

## 5. Ví dụ độc lập Java 17+: chọn provider, AES-GCM và chữ ký số

Ví dụ này dùng hoàn toàn API chuẩn có trên JDK 17+:

- Lấy SHA-256 qua provider được JCA tự chọn; truy vấn các provider SHA-256 và chỉ định **đối tượng provider** để chứng minh hai đường chọn cùng cho kết quả.
- Dùng `KeyGenerator` và `SecureRandom`, mã hóa/giải mã AES-GCM với nonce 12 byte và tag 128 bit, thử sửa ciphertext để kiểm tra lỗi xác thực.
- Tạo và kiểm tra chữ ký Ed25519 (thuật toán này có sẵn từ các JDK hiện đại; **không được coi là tính năng chỉ có từ Java 9**).
- Không in tên provider vì tên và số lượng provider phụ thuộc môi trường. Các dòng kết quả bên dưới được thiết kế ổn định với JDK 17+ chuẩn.

Tạo file **`JcaProviderDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Provider;
import java.security.SecureRandom;
import java.security.Security;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class JcaProviderDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        byte[] input = "Java JCA".getBytes(StandardCharsets.UTF_8);

        // Cách 1: không ràng buộc provider.
        MessageDigest automatic = MessageDigest.getInstance("SHA-256");
        byte[] hashAuto = automatic.digest(input);

        // Cách 2: lấy provider có dịch vụ SHA-256 rồi chỉ định rõ nó.
        Provider[] candidates = Security.getProviders("MessageDigest.SHA-256");
        if (candidates == null || candidates.length == 0) {
            throw new IllegalStateException("No SHA-256 provider");
        }
        MessageDigest explicit =
            MessageDigest.getInstance("SHA-256", candidates[0]);
        byte[] hashExplicit = explicit.digest(input);

        System.out.println("SHA-256 length: " + hashAuto.length);
        System.out.println("Explicit provider selected: "
            + explicit.getProvider().getName().equals(candidates[0].getName()));
        System.out.println("Same SHA-256 output: "
            + MessageDigest.isEqual(hashAuto, hashExplicit));

        // KeyGenerator và SecureRandom được chọn qua API chuẩn.
        SecureRandom random = new SecureRandom();
        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(128, random);
        SecretKey key = keyGenerator.generateKey();

        // Với một khóa AES-GCM, tuyệt đối không tái sử dụng nonce để mã hóa.
        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        GCMParameterSpec gcm = new GCMParameterSpec(128, nonce);

        byte[] plaintext = "Hello JCA".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "example:v1".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, gcm);
        encrypt.updateAAD(aad); // AAD phải được cung cấp trước dữ liệu mã hóa.
        byte[] ciphertext = encrypt.doFinal(plaintext);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, gcm);
        decrypt.updateAAD(aad);
        byte[] recovered = decrypt.doFinal(ciphertext);

        System.out.println("AES-GCM round-trip: "
            + Arrays.equals(plaintext, recovered));

        // Kiểm tra tag GCM phát hiện dữ liệu bị thay đổi.
        ciphertext[ciphertext.length - 1] ^= 0x01;
        Cipher check = Cipher.getInstance("AES/GCM/NoPadding");
        check.init(Cipher.DECRYPT_MODE, key, gcm);
        check.updateAAD(aad);
        try {
            check.doFinal(ciphertext);
            System.out.println("Tampering rejected: false");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampering rejected: true");
        }

        // Provider của KeyPairGenerator và Signature có thể khác nhau;
        // chỉ cần khóa và thuật toán hỗ trợ tương thích.
        KeyPairGenerator pairGenerator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = pairGenerator.generateKeyPair();
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(input);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(input);
        System.out.println("Ed25519 verified: " + verifier.verify(signature));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 JcaProviderDemo.java
java JcaProviderDemo
```

Đầu ra chuẩn trên JDK 17+ cung cấp các thuật toán chuẩn nêu trên:

```text
SHA-256 length: 32
Explicit provider selected: true
Same SHA-256 output: true
AES-GCM round-trip: true
Tampering rejected: true
Ed25519 verified: true
```

Trong ví dụ, gọi `MessageDigest.getInstance("SHA-256")` và `MessageDigest.getInstance("SHA-256", provider)` có thể dùng hai provider khác nhau nhưng tạo cùng 32 byte SHA-256 cho cùng input. AES-GCM cho bản mã **và tag xác thực**; khi thay đổi tag, `doFinal` ở chế độ giải mã ném `AEADBadTagException`. Chữ ký Ed25519 xác minh được bằng khóa công khai tương ứng.

**Giới hạn của ví dụ:** dữ liệu và khóa chỉ tồn tại trong lần chạy; muốn lưu bản mã phải lưu nonce cùng bản mã/tag theo định dạng có phiên bản và bảo vệ vòng đời khóa. Nếu mã hóa nhiều thông điệp với cùng khóa, mỗi lần phải tạo nonce **duy nhất**; xác suất va chạm của nonce ngẫu nhiên tăng theo số lần mã hóa, vì vậy hệ thống lớn cần thiết kế chiến lược nonce và giới hạn lượng mã hóa theo khóa. Không tái sử dụng nonce vì sẽ phá vỡ bảo đảm bảo mật của GCM.

### Khi muốn xem provider thực tế mà không làm thay đổi kết quả mẫu

Thêm các dòng chẩn đoán **sau `init(...)`** của engine đang cần quan sát:

```java
System.err.println("Cipher provider = " + encrypt.getProvider().getName());
System.err.println("Signature provider = " + signer.getProvider().getName());
```

Tên in ra thay đổi theo môi trường và không phải giá trị cần hardcode. Với `Signature`, hãy kiểm tra sau `initSign(...)` hoặc `initVerify(...)` khi thao tác có thể ảnh hưởng lựa chọn triển khai. Không được kết luận một provider cung cấp mọi engine chỉ vì nó hỗ trợ một dịch vụ như `MessageDigest.SHA-256`.

## 6. Khi nào thực sự cần khóa provider?

### Tình huống A: ứng dụng thông thường

Ứng dụng cần tính hash SHA-256 hoặc dùng AES-GCM với khóa phần mềm, trên nhiều JDK/hệ điều hành:

```java
MessageDigest md = MessageDigest.getInstance("SHA-256");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

Ưu điểm là mã độc lập provider và tận dụng cấu hình runtime. Vẫn phải tự kiểm tra thuật toán/tham số và runtime triển khai đạt yêu cầu bảo mật.

### Tình huống B: khóa lưu tại HSM hoặc dịch vụ bảo mật được kiểm duyệt

Một tổ chức yêu cầu thao tác chữ ký diễn ra bên trong HSM qua provider PKCS#11 hay nhà cung cấp cụ thể:

```java
// Đoạn minh họa: provider và privateKey phải được cấp
// từ cấu hình/keystore đã kiểm chứng của hệ thống.
Signature signature = Signature.getInstance("SHA256withRSA", approvedProvider);
signature.initSign(privateKey);
signature.update(message);
byte[] result = signature.sign();
```

Đoạn trên **không chạy độc lập** vì `approvedProvider`, `privateKey` và `message` là các đối tượng đầu vào do hệ thống cấp. Với hệ thống mới sử dụng RSA-PSS, chọn `Signature.getInstance("RSASSA-PSS", approvedProvider)` rồi đặt `PSSParameterSpec` phù hợp giao thức và kiểm tra hỗ trợ của provider. Ví dụ minh họa `SHA256withRSA` ở đây chỉ để giải thích cơ chế API, không có nghĩa nó phải được ưu tiên hơn RSA-PSS trong thiết kế mới.

Trong HSM, khóa riêng có thể **không xuất ra được**, do đó không thể giả định `privateKey` dùng được ở provider phần mềm bất kỳ. Việc chỉ định provider là một phần của quy tắc sử dụng khóa, và phải có kiểm tra tích hợp thực tế với thiết bị.

### Tình huống C: khả năng tương tác cần ổn định

Nếu hệ thống giao tiếp với một đối tác hoặc lưu bản mã/chữ ký lâu dài, hãy chốt rõ thuật toán, tham số, kích thước khóa, encoding, cách đóng gói nonce/AAD/tag, định dạng khóa và phiên bản giao thức. **Khóa provider không thay thế được đặc tả giao thức.** Hai provider cùng hỗ trợ `AES/GCM/NoPadding` vẫn cần được cấp cùng khóa, nonce và AAD để giải mã đúng; hai `Signature` cùng thuật toán vẫn phải thống nhất định dạng chữ ký hoặc quy tắc mã hóa.

## 7. Khả năng được hỗ trợ khác với tính an toàn

JCA có thể định danh và một số provider vẫn có thể triển khai thuật toán chỉ phù hợp với việc đọc dữ liệu cũ. **Đừng dùng sự tồn tại của tên để suy ra rằng thuật toán phù hợp cho mã hóa hoặc chữ ký mới.** Khi lựa chọn mới:

- Ưu tiên chế độ mã hóa **có xác thực** như `AES/GCM/NoPadding`; chỉ định đầy đủ transformation, kích thước khóa, nonce và tag. Tránh mặc định `AES` và ECB cho dữ liệu ứng dụng.
- Với integrity/authenticity dùng khóa chung, dùng `HmacSHA256` thay cho `SHA-256` không có khóa. Chữ ký số dùng `Signature`, không tự tạo bằng cách “mã hóa hash bằng private key”.
- Với mật khẩu, dùng một KDF mật khẩu được chấp thuận cùng salt và cấu hình cost phù hợp. Phân biệt mã băm thông điệp, MAC, KDF và mã hóa.
- Với chữ ký số mới, lựa chọn theo yêu cầu giao thức và kiểm thử thực tế: `Ed25519`, `RSASSA-PSS` có tham số chuẩn hoặc `SHA256withECDSA` với khóa/đường cong phù hợp. Không lựa chọn chỉ dựa trên provider có tên dễ nhớ.
- Với random cryptographic, `new SecureRandom()` thường là điểm khởi đầu phù hợp để sinh khóa/nonce ngẫu nhiên; `SecureRandom.getInstanceStrong()` dành cho nhu cầu cần cấu hình “strong” cụ thể và có thể có đặc tính chờ/nguồn entropy khác nhau theo môi trường. Không dùng `java.util.Random` cho khóa.
- Chỉ chọn thuật toán sau khi xét khả năng đáp ứng của bản JDK đang chạy, chính sách runtime, hỗ trợ phần cứng, yêu cầu compliance và độ an toàn hiện tại. Tránh dùng MD5, SHA-1 cho chữ ký mới, DES/3DES, RC4 hoặc các mode mã hóa không xác thực làm mặc định cho sản phẩm mới.

Lưu ý về phiên bản: **Java 9** đã có kiến trúc provider và JCA engine API tiêu chuẩn, nhưng tập thuật toán JDK tiếp tục phát triển theo phiên bản. Ví dụ `Ed25519` được đưa vào các JDK về sau, nên bài thực hành chủ động yêu cầu **Java 17+**. Không suy từ một thuật toán hoạt động trên JDK 17+ rằng thuật toán đó đã có trong mọi JDK 9.

## 8. Lỗi thường gặp khi chọn thuật toán/provider

| Triệu chứng | Khả năng xảy ra | Hướng xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Không provider nào hỗ trợ service+algorithm, tên không chuẩn, hoặc provider cụ thể thiếu triển khai | Kiểm tra tên chuẩn, tập provider khả dụng và runtime được hỗ trợ; đừng tự fallback sang thuật toán yếu |
| `NoSuchProviderException` | Tên provider chỉ định không có trong danh sách đăng ký | Kiểm tra `Security.getProvider(name)` và cấu hình triển khai |
| `NoSuchPaddingException` với `Cipher` | Transformation yêu cầu padding không được cung cấp | Dùng transformation chuẩn, kiểm chứng provider thực tế |
| `InvalidKeyException` | Khóa sai loại/kích thước, thiếu quyền hoặc khóa thuộc token/provider khác | Xác minh nguồn khóa, `KeyGenerator`/`KeyPairGenerator` và khả năng tương thích của provider |
| `InvalidAlgorithmParameterException` | Sai nonce/IV, tham số PSS/GCM hoặc provider không hỗ trợ | Khởi tạo tham số chuẩn, kiểm thử với kích thước và giao thức thật |
| `AEADBadTagException` | Ciphertext, tag, AAD, nonce hay khóa không khớp | Coi là lỗi xác thực; không trả plaintext và không bỏ qua kiểm tra tag |
| Provider có dịch vụ nhưng `init` thất bại | Tên được đăng ký nhưng khóa/tham số cụ thể không hợp lệ | Thử thao tác thật ngay khi khởi động/kiểm tra cấu hình |
| Chạy được máy A nhưng hỏng máy B | Đã hardcode tên provider, dùng alias hoặc dựa vào default mode | Dùng tên chuẩn, cấu hình rõ và thử trên các JDK được hỗ trợ |
| Provider thay đổi sau cập nhật JDK | Runtime ưu tiên lại nhà cung cấp hoặc phần cứng mới | Xác định yêu cầu thực sự phải cố định, lưu thông tin chẩn đoán và chạy kiểm thử tương thích |
| “Mã hóa được” nhưng thiếu bảo vệ sửa dữ liệu | Dùng mode không có xác thực hoặc tự xử lý tag sai | Chuyển sang AEAD và kiểm tra xác thực trước khi sử dụng plaintext |

### Cách kiểm thử đủ tin cậy

Kiểm tra tối thiểu gồm: (1) `getInstance` tạo được engine đúng tên; (2) `init` chấp nhận **khóa và tham số thật**; (3) một vòng encrypt/decrypt hoặc sign/verify thành công; (4) dữ liệu bị sửa làm kiểm tra xác thực thất bại; (5) định dạng đã mã hóa/ký tương thích khi đổi provider hợp lệ; (6) chế độ bắt buộc provider cụ thể phải **fail closed** khi provider không sẵn có.

Nếu có yêu cầu hiệu năng/FIPS/HSM, hãy kiểm chứng trực tiếp trên môi trường mục tiêu. Tên provider hoặc kết quả kiểm tra dịch vụ **không phải bằng chứng** về chứng nhận, đặc tính phần cứng hay đường thực thi đã đạt yêu cầu.

## 9. Tài liệu chính thức để tra cứu

- [Oracle Java SE 25: JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html) — kiến trúc provider, engine, `getInstance`, cách đăng ký và ưu tiên.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html) — tên thuật toán, transformation, kiểu keystore, tên chuẩn theo engine.
- [`java.security.Security` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Security.html) — `getProviders`, `getProvider` và truy vấn dịch vụ.
- [`java.security.Provider` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Provider.html) — thông tin provider và `Provider.Service`.
- [`javax.crypto.Cipher` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/Cipher.html) — transformation, `getInstance`, `init` và các lưu ý về nonce GCM.
- [`java.security.Signature` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html) — chọn provider và quy trình ký/xác minh.

Các API và thực hành trên vẫn áp dụng cho JDK hiện hành. Hãy đối chiếu phiên bản runtime triển khai để biết thuật toán nào có sẵn; không sao chép ngầm cấu hình cũ hoặc mặc định của một nhà cung cấp sang tất cả môi trường.