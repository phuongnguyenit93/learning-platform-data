
# Security provider, PKCS#11 và khác biệt giữa các bản phân phối

Khi nâng cấp Java, một ứng dụng có thể **biên dịch hoàn toàn thành công** nhưng thất bại lúc ký số, tạo kết nối TLS, mở keystore, tải private key hoặc truy cập HSM. Nguyên nhân không nhất thiết nằm ở mã nguồn: Java Security Architecture sử dụng các **security provider** có thể khác nhau theo phiên bản JDK, nhà phân phối, chính sách bảo mật, hệ điều hành, thư viện native và cấu hình triển khai.

Đặc biệt, hệ thống dùng **PKCS#11** thường có một chuỗi tích hợp dài: ứng dụng Java → JCA/JCE → provider cầu nối → thư viện native PKCS#11 → token hoặc HSM. Một bản cập nhật nhỏ ở bất kỳ mắt xích nào cũng có thể thay đổi thuật toán khả dụng, thứ tự chọn provider, cơ chế đăng nhập, tên key alias hoặc khả năng sử dụng khóa.

Bài học thuộc chủ đề *Java Advance Compatibility Migration*, phần *Bảo mật và quyền truy cập*. Mục tiêu là hiểu rõ hợp đồng API, phân biệt lỗi provider với lỗi PKCS#11, và thiết kế quy trình kiểm chứng tương thích giữa các bản JDK và môi trường triển khai.

## 1. Security provider là gì?

**Java Cryptography Architecture (JCA)** cung cấp các API trừu tượng cho thao tác bảo mật, chẳng hạn:

- `MessageDigest`: tính giá trị băm.
- `Signature`: ký số và kiểm tra chữ ký.
- `KeyPairGenerator` và `KeyGenerator`: sinh khóa.
- `KeyFactory` và `SecretKeyFactory`: xử lý dạng biểu diễn khóa.
- `SecureRandom`: cung cấp số ngẫu nhiên dùng cho mật mã.
- `KeyStore`: quản lý tham chiếu khóa và chứng chỉ.
- `CertificateFactory` và `CertPathValidator`: xử lý chứng chỉ và chuỗi tin cậy.

**Java Cryptography Extension (JCE)** là tập khả năng mật mã như `Cipher`, `Mac`, `KeyAgreement`. Trong JDK hiện đại, các API liên quan được phân phối như một phần của nền tảng Java.

Các API trên chủ yếu là **engine classes**. Chúng định nghĩa cách ứng dụng gọi một chức năng; **provider** cung cấp implementation cho những thuật toán hoặc dịch vụ được đăng ký.

Ví dụ:

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

public class DigestExample {
    public static void main(String[] args) throws Exception {
        MessageDigest digest =
                MessageDigest.getInstance("SHA-256");

        byte[] output =
                digest.digest("hello".getBytes(
                        java.nio.charset.StandardCharsets.UTF_8));

        System.out.println(HexFormat.of().formatHex(output));
        System.out.println(
                "Provider: " + digest.getProvider().getName());
    }
}
~~~

Code chỉ yêu cầu `SHA-256`. JVM chọn một provider hỗ trợ dịch vụ đó theo quy tắc lựa chọn đang áp dụng. Nhà cung cấp được chọn có thể khác trên runtime khác, dù `MessageDigest.getInstance("SHA-256")` vẫn hoạt động.

### 1.1. API trừu tượng và provider thực thi

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> B["JCA/JCE engine: Signature, Cipher, KeyStore"]
    B --> C{"Lựa chọn provider"}
    C --> D["Provider phần mềm"]
    C --> E["Provider PKCS#11"]
    C --> F["Provider bên thứ ba"]
    E --> G["Native PKCS#11 library"]
    G --> H["Token / HSM"]
~~~

Provider không phải một thuật toán đơn lẻ. Một provider có thể đăng ký nhiều **service types** và **algorithm names**, chẳng hạn:

| Service type | Ví dụ algorithm/service name | Chức năng |
|---|---|---|
| `MessageDigest` | `SHA-256` | Hash |
| `Signature` | `SHA256withRSA` | Chữ ký số |
| `Cipher` | `AES/GCM/NoPadding` | Mã hóa có xác thực |
| `KeyStore` | `PKCS12`, `PKCS11` | Quản lý khóa/chứng chỉ |
| `KeyPairGenerator` | `RSA`, `EC` | Sinh cặp khóa |
| `SecureRandom` | Tùy provider | Randomness |

Cần phân biệt **algorithm family** với **transformation** và **provider-specific alias**. Ví dụ `AES/GCM/NoPadding` là một transformation cho `Cipher`; hỗ trợ thực tế còn phụ thuộc key size, parameters, cơ chế của provider và thiết bị.

### 1.2. Một số provider thường thấy

Tùy JDK, có thể gặp các tên như:

- `SUN`: một số dịch vụ Java Security cơ bản.
- `SunRsaSign`: các dịch vụ chữ ký và xử lý khóa RSA.
- `SunEC`: dịch vụ mật mã đường cong elliptic.
- `SunJCE`: các dịch vụ mật mã đối xứng và những engine liên quan.
- `SunJSSE`: triển khai TLS/JSSE và các thành phần liên quan.
- `SunPKCS11`: cầu nối tới PKCS#11, khi có module và cấu hình phù hợp.
- Các provider bên thứ ba hoặc nhà cung cấp JDK/HSM.

**Không xem danh sách trên là hợp đồng bắt buộc của mọi JDK.** Tên provider, thứ tự, thuật toán và cấu hình có thể khác giữa OpenJDK-based distributions, JDK tùy biến, runtime tối giản, phiên bản phát hành và provider được đăng ký thêm.

## 2. Khi ứng dụng không chỉ định provider, điều gì xảy ra?

Ví dụ:

~~~java
Signature signature =
        Signature.getInstance("SHA256withRSA");
~~~

Ứng dụng yêu cầu thuật toán nhưng **không khóa chặt provider**. Java Security framework lựa chọn implementation phù hợp từ các provider đã đăng ký, có xét đến khả năng của provider và bối cảnh engine/key.

Trong một số trường hợp, implementation thực tế có thể bị ràng buộc bởi loại key hoặc cơ chế lựa chọn trì hoãn. Vì vậy, không nên đơn giản hóa thành “luôn chọn provider đầu tiên cho mọi lời gọi” mà không quan sát engine thực tế.

Nếu ứng dụng chỉ định provider:

~~~java
Signature signature =
        Signature.getInstance("SHA256withRSA", "ExampleProvider");
~~~

thì nó phụ thuộc vào tên provider và dịch vụ đã đăng ký. Nếu provider không có hoặc không hỗ trợ thuật toán, lời gọi sẽ thất bại.

Đối với hệ thống phải sử dụng **khóa nằm trong HSM**, lựa chọn provider có thể là một phần của chính sách bảo mật: không được âm thầm chuyển sang private key phần mềm chỉ để test xanh. Mặt khác, pin cứng tên provider trong các đường code không yêu cầu phần cứng có thể làm ứng dụng khó di chuyển giữa các JDK.

### 2.1. Xem provider ở runtime

Ví dụ Java:

~~~java
import java.security.Provider;
import java.security.Security;

public final class ListSecurityProviders {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                    "%s | version=%s | info=%s%n",
                    provider.getName(),
                    provider.getVersionStr(),
                    provider.getInfo());

            for (Provider.Service service : provider.getServices()) {
                if ("Signature".equals(service.getType())
                        || "KeyStore".equals(service.getType())) {
                    System.out.printf(
                            "  %s : %s%n",
                            service.getType(),
                            service.getAlgorithm());
                }
            }
        }
    }
}
~~~

Kết quả cho biết provider và những service **được đăng ký** tại runtime. Nhưng một service được liệt kê **không bảo đảm** mọi kiểu khóa, tham số, cơ chế token hoặc thao tác đều thành công. PKCS#11 provider có thể quảng bá một algorithm trong khi token cụ thể chỉ chấp nhận một số key attribute hoặc mechanism.

Để quan sát provider của một instance cụ thể:

~~~java
import java.security.Signature;

Signature signer = Signature.getInstance("SHA256withRSA");
System.out.println(signer.getProvider().getName());
~~~

Với một số engine có lựa chọn provider trì hoãn, chỉ in provider trước khi khởi tạo với key chưa đủ để kết luận đường thực thi cuối cùng. Kiểm tra thêm sau `initSign`/`initVerify` và một operation thực tế khi cần xác nhận chính sách.

### 2.2. Thứ tự provider và những gì không nên giả định

Provider có thứ tự ưu tiên; Java cho phép đăng ký qua:

~~~java
Security.addProvider(provider);
Security.insertProviderAt(provider, 1);
~~~

Nhưng thay thứ tự toàn cục có thể ảnh hưởng đến TLS, certificate validation, key generation và những luồng bảo mật khác trong cùng tiến trình. Không nên tự động đưa một provider HSM lên đầu mọi dịch vụ chỉ vì muốn sử dụng token để ký một loại chứng từ.

Ưu tiên:

1. Chỉ định provider ở call site mà thiết kế yêu cầu.
2. Dùng key có nguồn gốc và cơ chế kiểm soát rõ.
3. Cấu hình toàn cục khi có lý do và đã đánh giá ảnh hưởng.
4. Kiểm thử các service khác sau khi thay provider order.

## 3. PKCS#11 là gì?

**PKCS#11**, còn gọi là **Cryptoki**, là một giao diện tiêu chuẩn để phần mềm tương tác với thiết bị hoặc dịch vụ cung cấp chức năng mật mã, thường là smart card, USB token hoặc **Hardware Security Module (HSM)**.

Trong kiến trúc thông dụng:

- Java gọi JCA/JCE như `Signature`, `KeyStore` hoặc `KeyPairGenerator`.
- Provider hỗ trợ PKCS#11 chuyển yêu cầu JCA sang lời gọi PKCS#11.
- Thư viện native do nhà cung cấp thiết bị phân phối nói chuyện với token/HSM.
- Thiết bị quản lý slot, session, object, mechanism và chính sách key usage.

~~~mermaid
flowchart LR
    A["Business service"] --> B["Java Signature / KeyStore"]
    B --> C["PKCS#11 JCA provider"]
    C --> D["JNI/native bridge"]
    D --> E["Vendor PKCS#11 library"]
    E --> F["Slot / token / session"]
    F --> G["Private key trong HSM"]
~~~

PKCS#11 khác với **PKCS#12**:

| Tên | Bản chất | Dạng thường gặp |
|---|---|---|
| PKCS#11 | Giao diện API tới token/HSM qua provider/native library | `KeyStore` loại `PKCS11`, HSM session |
| PKCS#12 | Định dạng lưu key/certificate có thể nằm trong file | `KeyStore` loại `PKCS12`, file `.p12`/`.pfx` |

Việc ứng dụng có thể mở một file PKCS#12 không chứng minh nó đã tích hợp PKCS#11 hoặc đang giữ private key bên trong HSM.

### 3.1. Các khái niệm thường gặp trong PKCS#11

| Khái niệm | Ý nghĩa |
|---|---|
| Module/library | Thư viện native PKCS#11 cung cấp giao diện Cryptoki |
| Slot | Vị trí logic thiết bị/token có thể dùng |
| Token | Thiết bị hay đối tượng logic cung cấp keys và crypto operations |
| Session | Phiên giao tiếp với token |
| Object | Key, certificate hoặc dữ liệu lưu trong token |
| Mechanism | Phương thức/thuật toán phần cứng có thể thực hiện |
| PIN/login | Cơ chế xác thực để dùng các đối tượng được bảo vệ |
| Label/ID | Thuộc tính giúp tìm object, không nhất thiết là alias Java ổn định |
| Key attributes | Quy định key được ký, giải mã, xuất, sử dụng ra sao |

Một token có thể chứa private key **không thể xuất ra**. Khi đó Java có thể nhận một đối tượng `PrivateKey` biểu diễn tham chiếu, không có nghĩa ứng dụng nhận được bytes của khóa bí mật.

### 3.2. Native dependency là một phần của hợp đồng runtime

Các yếu tố có thể làm PKCS#11 không hoạt động sau migration:

- File `.so`/`.dll`/`.dylib` không tồn tại ở đường dẫn cấu hình.
- CPU architecture không khớp (x86-64/ARM64).
- Native library phụ thuộc libc hoặc thư viện hệ thống khác.
- Quyền file/device và policy container bị hạn chế.
- Driver/daemon của nhà cung cấp HSM chưa chạy hoặc không kết nối.
- Token/slot thay đổi sau khi reboot hoặc khi thêm thiết bị.
- Phiên bản vendor PKCS#11 không hỗ trợ JDK/OS mới.
- Thư viện dùng cơ chế native không được provider cho phép.
- Token yêu cầu login hoặc đã hết session.

Không thể giải quyết những lỗi này chỉ bằng chỉnh Java source hoặc compiler target.

## 4. SunPKCS11 và khác biệt giữa các JDK

Trong nhiều bản phân phối dựa trên OpenJDK, **SunPKCS11** là provider cầu nối JCA/JCE tới thư viện native PKCS#11. Trên các JDK module hóa, implementation tương ứng được phân phối qua module `jdk.crypto.cryptoki` khi runtime có module đó.

Điều cần hiểu:

- Một JDK có thể cung cấp provider `SunPKCS11` nhưng **chưa có cấu hình token/HSM**.
- Runtime được tạo bằng `jlink` có thể đã loại module cần thiết.
- Bản phân phối khác có thể cung cấp provider khác hoặc một cách tích hợp PKCS#11 khác.
- Tên và thứ tự provider không phải API portable bảo đảm mọi vendor.
- Native library và token vẫn phải được cài đặt, cấp quyền và kiểm tra riêng.

Đừng viết hướng dẫn “mọi Java 17 đều có SunPKCS11 hoạt động ngay” nếu chưa xác nhận runtime cụ thể.

### 4.1. Kiểm tra module trong runtime

Ví dụ:

~~~bash
java --list-modules
~~~

Có thể lọc theo shell:

~~~bash
java --list-modules | grep 'jdk.crypto.cryptoki'
~~~

Trên PowerShell:

~~~powershell
java --list-modules | Select-String 'jdk.crypto.cryptoki'
~~~

Khi xây dựng custom runtime image bằng `jlink`, cần xác định provider module được bao gồm, chẳng hạn dựa trên các module ứng dụng cần và `jdk.crypto.cryptoki`. Danh sách module đầy đủ phụ thuộc ứng dụng; không nên chỉ thêm một module rồi giả định image đủ chức năng.

### 4.2. Kiểm tra provider hiện diện

~~~java
import java.security.Provider;
import java.security.Security;

public class CheckPkcs11 {
    public static void main(String[] args) {
        Provider provider =
                Security.getProvider("SunPKCS11");

        if (provider == null) {
            System.out.println("SunPKCS11 not available");
        } else {
            System.out.println(provider.getName());
        }
    }
}
~~~

`null` có thể do provider không được cài/đăng ký trong runtime đó, cấu hình custom image hoặc lựa chọn phân phối. Không lập tức kết luận token/HSM bị lỗi nếu ngay cả provider bridge chưa có.

## 5. Cấu hình PKCS#11 và tạo provider

Một cấu hình SunPKCS11 minh họa:

~~~properties
name = InvoiceToken
library = /opt/vendor/pkcs11/libvendorpkcs11.so
slotListIndex = 0
~~~

Ý nghĩa:

- `name`: tên phân biệt instance cấu hình.
- `library`: đường dẫn tới thư viện native PKCS#11.
- `slotListIndex`: chọn vị trí trong danh sách slot mà native library trả về, **không nhất thiết là slot ID cố định**.

Đường dẫn là ví dụ; phải thay bằng thư viện và cấu hình hợp lệ do vendor cung cấp. Trên Windows có thể là đường dẫn tới file `.dll`; trên macOS có thể là `.dylib`. Nếu vendor dùng virtual HSM/network HSM, library vẫn có thể là native client kết nối tới service đó.

### 5.1. slot và slotListIndex khác nhau

Một cấu hình có thể chọn bằng `slot` hoặc `slotListIndex` tùy provider, nhưng hai cách **không đồng nghĩa**:

- `slot` thường chỉ slot ID do PKCS#11 module cung cấp.
- `slotListIndex` là chỉ số vị trí trong danh sách slot.

Thứ tự slot có thể đổi khi bổ sung token, thay driver hoặc khởi động lại. Vì vậy không nên xem `slotListIndex = 0` là định danh nghiệp vụ bền vững.

Cần lấy thông tin token/slot từ công cụ vendor hoặc tài liệu quản trị và kiểm tra hành vi sau thay đổi thiết bị. Nếu hệ thống HA có nhiều slot, thiết kế cơ chế chọn và failover rõ ràng thay vì dựa vào giả định “slot đầu tiên”.

### 5.2. Cấu hình provider trên JDK hiện đại

Ví dụ Java dùng phương thức `Provider.configure` (có từ Java 9):

~~~java
import java.security.Provider;
import java.security.Security;

public class Pkcs11ProviderFactory {
    public static Provider configure(String configFile) {
        Provider base =
                Security.getProvider("SunPKCS11");

        if (base == null) {
            throw new IllegalStateException(
                    "SunPKCS11 provider is unavailable");
        }

        Provider configured = base.configure(configFile);

        // Chỉ đăng ký toàn cục nếu kiến trúc thật sự yêu cầu.
        Security.addProvider(configured);
        return configured;
    }
}
~~~

Instance cấu hình thường có tên như `SunPKCS11-InvoiceToken` trong triển khai tương ứng. Tuy nhiên, ứng dụng không nên đoán tên bằng nối chuỗi khi có thể giữ trực tiếp đối tượng `Provider` trả về.

Chú ý:

- Đường dẫn config có thể chứa thông tin đường dẫn hệ thống nhưng không nên chứa PIN hoặc secret.
- Không gọi cấu hình lặp thiếu kiểm soát trong từng request; provider và session có vòng đời riêng.
- Một số phiên bản JDK, runtime tùy biến hoặc provider khác có API cấu hình khác.
- Nếu dùng provider ngoài SunPKCS11, hãy làm theo tài liệu của provider đó thay vì giả định `configure` nhận cùng định dạng.
- Không thêm provider vào đầu danh sách toàn cục nếu không có lý do bảo mật và compatibility.

### 5.3. Khi cần đăng ký ở cấu hình Java security

Provider cũng có thể được đăng ký qua cấu hình Java security của runtime hoặc cơ chế provider của sản phẩm. Những cách đăng ký này là một phần của môi trường triển khai và cần được version hóa.

Cần xác định:

1. Provider được cài sẵn, khai báo trong security properties hay thêm bằng code?
2. Có nhiều instance HSM hay nhiều vendor provider không?
3. Thứ tự provider có ảnh hưởng Cipher/Signature/JSSE không?
4. Cấu hình có thay đổi giữa test, staging và production không?
5. Có custom runtime image hoặc Java agent can thiệp provider không?

Không chỉnh sửa `java.security` của hệ thống production thủ công rồi bỏ qua quản lý cấu hình. Một thay đổi âm thầm có thể khiến môi trường và CI sử dụng hai provider sets khác nhau.

## 6. Sử dụng KeyStore PKCS11

Với provider đã được cấu hình, có thể truy cập token qua `KeyStore` loại `PKCS11` nếu provider và thiết bị hỗ trợ.

~~~java
import java.io.Console;
import java.security.KeyStore;
import java.security.Provider;
import java.security.Security;
import java.util.Arrays;
import java.util.Enumeration;

public class ListTokenAliases {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Expected path to SunPKCS11 configuration");
        }

        Provider base = Security.getProvider("SunPKCS11");
        if (base == null) {
            throw new IllegalStateException(
                    "SunPKCS11 not found in this runtime");
        }

        Provider tokenProvider = base.configure(args[0]);
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Use an approved noninteractive secret mechanism");
        }

        char[] pin = console.readPassword("Token PIN: ");
        try {
            KeyStore keyStore =
                    KeyStore.getInstance("PKCS11", tokenProvider);

            keyStore.load(null, pin);

            Enumeration<String> aliases = keyStore.aliases();
            while (aliases.hasMoreElements()) {
                String alias = aliases.nextElement();
                System.out.println(
                        "Alias available: " + alias);
            }
        } finally {
            Arrays.fill(pin, '\0');
        }
    }
}
~~~

Đây là **ví dụ minh họa kiến trúc**, không phải mã vận hành production hoàn chỉnh:

- Token có thể yêu cầu login riêng, cơ chế PIN riêng hoặc vendor-specific configuration.
- `System.console()` thường không khả dụng trong CI, service hoặc container.
- `KeyStore.load(null, pin)` là cách thường dùng với SunPKCS11 nhưng phải xác minh với provider/token thực tế.
- Alias được hiển thị là metadata và có thể mang thông tin định danh nội bộ; chỉ log trong môi trường được phép.
- Xóa `char[]` giảm thời gian PIN tồn tại trong mảng đó, nhưng không bảo đảm mọi bản sao hoặc bộ nhớ native đã được xóa.
- Không ghi PIN vào source code, command line, Git, log hoặc file cấu hình PKCS#11.
- Trong production, lấy secret từ cơ chế quản lý đã được phê duyệt và kiểm soát quyền truy cập.

### 6.1. KeyStore type không bảo đảm private key export được

Token/HSM có thể đưa ra `PrivateKey` dưới dạng một đối tượng chỉ chứa reference/handle, và khóa thực không bao giờ rời thiết bị.

Vì vậy, không được giả định:

~~~java
privateKey.getEncoded()
~~~

sẽ trả về bytes của private key. Với key không thể export, kết quả có thể là `null`. Thiết kế đúng là yêu cầu provider thực hiện **ký hoặc giải mã trên thiết bị** thông qua JCA/JCE, tuân thủ chính sách và mechanism của token.

### 6.2. Alias có thể khác giữa provider và thiết bị

Alias trong Java KeyStore không nhất thiết trùng với label hiển thị trong công cụ vendor hay `CKA_LABEL` của object. Một token có thể có certificate, public key và private key với nhiều thuộc tính khác nhau.

Khi migration:

- Đối chiếu alias trên đúng token.
- Kiểm tra certificate chain, key usage và identifier.
- Không chọn alias bằng vị trí đầu tiên trong `aliases()`.
- Không lấy key chỉ vì alias trùng nếu certificate/public key không đúng.
- Dùng key ID, certificate fingerprint hoặc mapping chính thức nếu kiến trúc yêu cầu.
- Xác nhận cơ chế lấy key không bắt ứng dụng export private key.

Nếu vendor thay đổi quy tắc alias sau update, cần cập nhật mapping có kiểm soát.

## 7. Ký số bằng khóa HSM qua JCA

Một mô hình tiêu biểu: lấy `PrivateKey` handle từ keystore PKCS11, rồi gọi `Signature` với provider phù hợp.

~~~java
import java.security.PrivateKey;
import java.security.Provider;
import java.security.Signature;
import java.nio.charset.StandardCharsets;

public final class TokenSigner {
    public static byte[] sign(
            String data,
            PrivateKey key,
            Provider tokenProvider) throws Exception {

        Signature signature =
                Signature.getInstance(
                        "SHA256withRSA", tokenProvider);

        signature.initSign(key);
        signature.update(
                data.getBytes(StandardCharsets.UTF_8));
        return signature.sign();
    }
}
~~~

Ví dụ giả định:

- Key là RSA private key thích hợp với SHA-256/RSA signature.
- Token/provider hỗ trợ service và mechanism tương ứng.
- Key có các attribute cần thiết để thực hiện chữ ký.
- Session, login và quyền truy cập đã sẵn sàng.

Nếu thiết bị chỉ hỗ trợ một cơ chế khác, hoặc khóa có hạn chế sử dụng, `Signature.getInstance(...)` hoặc `initSign`/`sign` có thể thất bại. Một provider tuy đăng ký thuật toán vẫn có thể từ chối thao tác với key hoặc parameters cụ thể.

### 7.1. Cần phân biệt provider được chọn với nơi khóa được lưu

Khi gọi:

~~~java
Signature.getInstance("SHA256withRSA")
~~~

nền tảng có thể lựa chọn implementation phần mềm hoặc PKCS#11 tùy cấu hình, key và provider. Với HSM có yêu cầu “private key không rời thiết bị”, thiết kế cần chứng minh operation thực sự được thực hiện qua token.

Bằng chứng có thể gồm:

- Provider instance được sử dụng ở thao tác ký.
- Key object xuất phát từ PKCS11 KeyStore đúng token.
- Log/audit của HSM trong môi trường test.
- Kiểm tra thuộc tính non-extractable của key qua cơ chế quản lý được phép.
- Test ngắt quyền hoặc ngắt token có kiểm soát để xem thao tác ký có thất bại như mong đợi.

Không chứng minh “đã dùng HSM” chỉ bằng sự tồn tại của `SunPKCS11` trong `Security.getProviders()`.

### 7.2. Chọn thuật toán ký phù hợp chính sách

Các thuật toán chữ ký có thể khác nhau về padding, hash, curve và cách chuẩn hóa dữ liệu. Ví dụ RSA-PSS không hoàn toàn tương đương `SHA256withRSA` (thường là kiểu RSA PKCS#1 v1.5), và có các yêu cầu parameters riêng.

Đối với hệ thống thanh toán, chữ ký tài liệu, chứng từ hoặc kết nối đối tác, phải chọn thuật toán theo **protocol và chính sách bảo mật**, không theo việc provider đầu tiên hỗ trợ tên nào.

Tập algorithm names do một provider đăng ký cũng không bảo đảm token có mọi mechanism cần dùng. PKCS#11 mechanism mapping có thể khác theo vendor và runtime.

## 8. Cipher, TLS, chứng chỉ và provider: các lớp dễ bị nhầm

### 8.1. Cipher provider không nhất thiết là TLS provider

JCA/JCE cung cấp `Cipher`. **JSSE (Java Secure Socket Extension)** cung cấp các API như `SSLContext`, `SSLSocket` và `TrustManagerFactory` để thiết lập TLS.

Một ứng dụng có thể sử dụng:

- Provider HSM cho chữ ký với private key.
- Provider khác cho ciphers hoặc hash.
- JSSE implementation để chạy TLS handshake.
- Truststore riêng để kiểm chứng certificate chain.

Đổi provider thứ tự hoặc policy có thể tác động gián tiếp đến TLS, nhưng **hỗ trợ một Cipher algorithm không đồng nghĩa hỗ trợ toàn bộ TLS protocol**.

### 8.2. HSM có thể bảo vệ private key cho mutual TLS

Với mutual TLS (mTLS), client cần trình bày certificate và dùng private key ký trong handshake. Key có thể nằm trong token, còn `KeyManagerFactory` hoặc tích hợp JSSE dùng KeyStore thích hợp.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant JSSE as JSSE/TLS
    participant JCA as JCA PKCS#11 provider
    participant HSM as Token/HSM
    participant Server as TLS peer
    App->>JSSE: Tạo TLS connection với key manager
    JSSE->>JCA: Yêu cầu thao tác private-key
    JCA->>HSM: Ký challenge/handshake data
    HSM-->>JCA: Signature
    JCA-->>JSSE: Signature result
    JSSE->>Server: TLS handshake messages
~~~

Việc cấu hình `KeyManagerFactory` và `SSLContext` cụ thể phụ thuộc JSSE implementation, provider, loại key/certificate và chính sách ứng dụng. Không được mặc định `KeyStore.getInstance("PKCS11")` tự động làm mTLS hoạt động mà không cần thiết lập key manager và trust manager.

### 8.3. KeyStore cho key khác TrustStore cho trust

**Keystore** chứa hoặc tham chiếu key/certificate của chủ thể. **Truststore** chứa các trust anchor/certificate được hệ thống dùng khi xác thực bên kia.

Trong một ứng dụng, private key từ HSM có thể dùng để ký, trong khi truststore nằm trong file `PKCS12` hoặc dữ liệu do hệ thống quản lý. Việc thay HSM provider không nhất thiết yêu cầu chuyển mọi certificate sang HSM.

### 8.4. Chính sách algorithm restrictions của JDK

Nâng JDK có thể thay đổi các security properties như:

~~~text
jdk.tls.disabledAlgorithms
jdk.certpath.disabledAlgorithms
jdk.jar.disabledAlgorithms
~~~

Một certificate chain hoặc protocol trước đây được chấp nhận có thể bị từ chối do khóa yếu, thuật toán chữ ký yếu hoặc chính sách mới, **ngay cả khi PKCS#11 provider vẫn hoạt động**.

Hãy kiểm tra lỗi TLS, certificate path validation và thuật toán của key/cert riêng với lỗi tải provider/token. Không nới rộng toàn bộ policy chỉ để làm một hệ thống cũ kết nối được nếu chưa đánh giá bảo mật.

## 9. Khác biệt giữa các bản phân phối JDK

Không phải mọi bản Java cùng major version đều có trải nghiệm bảo mật giống hệt nhau. Ngoài khác biệt theo vendor, bản cập nhật cùng dòng JDK còn có thể thay đổi dữ liệu chứng chỉ, algorithm policy và lỗi đã được sửa.

Các khía cạnh cần kiểm tra:

| Khía cạnh | Điều có thể khác | Tác động |
|---|---|---|
| Provider set | Provider có/không, tên hoặc implementation | `getInstance` thất bại/chọn provider khác |
| Provider order | Thứ tự security providers | Engine chọn implementation khác |
| PKCS#11 bridge | Có/không có `jdk.crypto.cryptoki` hoặc adapter khác | Không cấu hình được token |
| Root CA/truststore | Nội dung và policy của `cacerts` | TLS/cert validation khác |
| Algorithm restrictions | Thuật toán/độ dài khóa bị hạn chế | Handshake hoặc chữ ký bị từ chối |
| FIPS/validated configuration | Provider và policy được cấu hình riêng | Algorithm availability, key operations thay đổi |
| Native ABI | OS/CPU/libc/vendor client | Không load được PKCS#11 library |
| HSM vendor support | Driver/module version có hỗ trợ JDK/OS không | Session, slot, mechanism lỗi |
| Build update | Patches của JDK/provider | Hành vi lỗi và chính sách mới |
| Custom runtime image | Modules bị lược bớt | Thiếu PKCS#11 bridge hoặc engine khác |

**Không nên dùng mỗi `java -version` như bằng chứng đầy đủ.** Cần thêm provider inventory, security properties liên quan, module list, native library version và kết quả hoạt động thực tế.

### 9.1. JDK vendor vs native HSM vendor

Một lỗi có thể xuất hiện ở bốn cấp khác nhau:

1. **JDK distribution:** module/provider không tồn tại hoặc có khác biệt implementation.
2. **JCA bridge:** provider được tải nhưng service mapping/configuration không phù hợp.
3. **PKCS#11 native module:** DLL/SO không load được, session/token/slot lỗi.
4. **HSM/token:** key attributes, PIN, mechanism, quotas hoặc policy không cho phép thao tác.

Hãy ghi cấp xảy ra lỗi; tránh “lỗi Java 21” khi thực tế là vendor library được build cho ABI khác.

### 9.2. FIPS không phải một cờ bật tùy ý

Một hệ thống có yêu cầu FIPS cần kiểm tra **module mật mã được thẩm định, phiên bản, cấu hình, ranh giới bảo vệ và quy trình vận hành đúng yêu cầu**. Chỉ dùng HSM hoặc thêm `SunPKCS11` không tự chứng minh toàn bộ ứng dụng đạt FIPS.

Trong môi trường có policy đặc biệt:

- Xác nhận nhà cung cấp module, mode vận hành và certificate/validation applicability.
- Xác nhận thuật toán được cho phép ở mode đó.
- Xác nhận cơ chế tạo, lưu, sử dụng và hủy key.
- Đảm bảo provider fallback không vi phạm chính sách.
- Tách kiểm thử tương thích kỹ thuật khỏi kiểm chứng tuân thủ chính thức.

Không tự động giảm chính sách TLS/algorithm của JDK để “tăng compatibility”.

## 10. Các lỗi thường gặp và cách phân loại

| Lỗi hoặc triệu chứng | Nguyên nhân có thể | Cách khoanh vùng |
|---|---|---|
| `NoSuchProviderException` | Tên provider không có trong registry | In `Security.getProviders()`, kiểm tra module và cấu hình |
| `NoSuchAlgorithmException` | Service/algorithm không được provider cung cấp | Kiểm tra services, transformation và token mechanism |
| `ProviderException` khi init | Lỗi bridge/native/token | Đọc cause chain và log provider/HSM |
| `UnsatisfiedLinkError` | Không load được native library/ABI | Đường dẫn, dependency native, OS/CPU, permission |
| `IOException` khi mở keystore | Login/token/keystore hoặc cấu hình lỗi | Kiểm tra cause, driver, slot, PIN procedure |
| `UnrecoverableKeyException` | Không lấy được key, xác thực hoặc quyền hạn | Alias, login, key attributes và provider |
| `InvalidKeyException` | Key không dùng được cho thuật toán/provider | Key type, allowed usage và mechanism |
| `InvalidAlgorithmParameterException` | Parameters không được chấp nhận | IV, padding, PSS params hoặc mechanism |
| `KeyStoreException` | Loại keystore/service hoặc trạng thái không hợp lệ | `PKCS11` provider configuration |
| TLS handshake failure | Certificate, policy, trust, protocol hoặc signing problem | JSSE logs, truststore, key manager và HSM operation |
| `CKR_TOKEN_NOT_PRESENT` | Token không hiện diện trong slot | Vendor diagnostics và slot mapping |
| `CKR_PIN_INCORRECT` | PIN sai theo token | Quy trình secret management; tránh thử lặp vô hạn |
| `CKR_MECHANISM_INVALID` | Token không chấp nhận mechanism | Danh sách mechanism và mapping algorithm |
| `CKR_SESSION_COUNT` | Quá giới hạn session | Pooling, concurrency, giới hạn token |
| Key alias không thấy | Mapping/object filter/permission khác | Enumerate aliases, kiểm tra token object attributes |

Các mã `CKR_*` là ví dụ từ PKCS#11; không phải mọi provider đều hiển thị nguyên văn mã này trên exception. Stack trace có thể bọc lỗi ở nhiều tầng.

### 10.1. Khởi tạo provider thành công chưa đủ

Một số provider chỉ tương tác với token khi tạo `KeyStore`, thực hiện `load`, khởi tạo `Signature` hoặc gọi `sign`. Vì vậy:

~~~java
Provider p = Security.getProvider("SunPKCS11");
~~~

chỉ xác nhận được phần registry, không chứng minh session/login/private-key operation sẽ thành công.

Ngay cả khi `KeyStore.aliases()` đọc được certificate, signing operation vẫn có thể thất bại vì key không cho phép mechanism tương ứng.

### 10.2. Cần kiểm tra root cause, không chỉ exception ngoài cùng

Ví dụ một lỗi nghiệp vụ:

~~~text
SigningServiceException
  caused by java.security.ProviderException
    caused by PKCS11Exception: CKR_MECHANISM_INVALID
~~~

Nếu chỉ thấy `SigningServiceException`, có thể nhầm với lỗi code ứng dụng. Cần lưu cause chain đã loại thông tin nhạy cảm, correlating request ID và sự kiện audit từ HSM nếu có.

### 10.3. Chú ý khóa PIN hoặc session

Nhiều thiết bị có chính sách khóa PIN sau một số lần sai và giới hạn login/session. Test tự động không nên thử PIN sai hàng loạt hoặc tạo session vô hạn. Dùng token test được quản trị riêng và quy trình kiểm thử đã phê duyệt.

## 11. Chẩn đoán ở runtime và bảo vệ thông tin nhạy cảm

Để so sánh môi trường, cần ghi metadata có ý nghĩa:

~~~java
import java.security.Provider;
import java.security.Security;

public class SecurityDiagnostics {
    public static void main(String[] args) {
        System.out.println(
                System.getProperty("java.runtime.version"));
        System.out.println(
                System.getProperty("java.vendor"));

        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                    "%s : %s%n",
                    provider.getName(),
                    provider.getVersionStr());
        }

        System.out.println(
                "TLS restrictions configured: " +
                (Security.getProperty(
                        "jdk.tls.disabledAlgorithms") != null));
    }
}
~~~

Đây là ví dụ ghi nhận thận trọng; báo cáo production có thể cần chi tiết policy để đối chiếu, nhưng phải tuân thủ quy tắc bảo vệ thông tin cấu hình. Không tự động dump mọi security property, alias hoặc key metadata vào log công khai.

### 11.1. Debug logging

Một số JDK hỗ trợ các tùy chọn debug bảo mật kiểu:

~~~bash
java -Djava.security.debug=help
~~~

Lệnh trên giúp xem các tùy chọn debug hỗ trợ trên runtime cụ thể; cú pháp gọi để hiển thị trợ giúp có thể khác theo launcher/JDK. Khi cần theo dõi JSSE, có thể dùng `javax.net.debug` theo tài liệu JDK tương ứng.

Ví dụ có điều kiện trong môi trường test:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

Log TLS/debug PKCS#11 có thể chứa chi tiết certificate, endpoint, mechanism hoặc metadata hệ thống. Phải giới hạn ở môi trường được phép, lọc bí mật, không bật debug tràn lan ở production và không chia sẻ nguyên bản log chứa dữ liệu nhạy cảm.

### 11.2. Thu thập thông tin native/HSM

Khi provider đã tồn tại nhưng token không làm việc, thường cần công cụ chẩn đoán do nhà cung cấp HSM cấp để xác minh:

- Native library version, bitness và dependency.
- Daemon/network access tới HSM (nếu cần).
- Slot và token label.
- Login status.
- Cơ chế/algorithm được hỗ trợ.
- Quyền truy cập key và số lượng session.
- Audit event và giới hạn concurrency.

Không đặt secret/PIN vào output diagnostic. Trong nhiều hệ thống, chỉ team HSM được phép chạy công cụ quản trị; ứng dụng cần phối hợp qua quy trình vận hành.

## 12. Thiết kế kiểm thử PKCS#11 cho migration

Các unit test chỉ dùng provider phần mềm không thể thay thế end-to-end integration test với PKCS#11 nếu production phải ký trong HSM.

Một ma trận nên kiểm soát:

| Trục | Giá trị thử nghiệm | Mục đích |
|---|---|---|
| JDK | Baseline và target JDK/update | Bắt thay đổi provider/policy |
| Distribution | Những vendor được sản phẩm hỗ trợ | Tìm khác biệt implementation |
| OS/CPU | Linux/Windows/ARM64 v.v. | Kiểm tra ABI/native library |
| PKCS#11 library | Vendor version hiện tại và bản nâng | Tìm regression của driver |
| Token type | Test token, hardware model | Kiểm tra mechanism/key attributes |
| Key type | RSA, EC, kiểu khác nếu dùng | Đảm bảo đúng thuật toán |
| Algorithm | Thuật toán ký/mã hóa trong contract | Kiểm tra transformation/parameters |
| Login mode | Interactive, service/managed secret | Kiểm tra secret lifecycle |
| Concurrency | 1, nhiều request, peak | Kiểm tra session limit |
| Failure mode | Token offline, session timeout | Kiểm tra lỗi/khôi phục có kiểm soát |

### 12.1. Các mức kiểm thử

**Mức 1 — Provider availability**

- JDK có module/bridge cần thiết không?
- Provider được đăng ký hoặc cấu hình thành công không?
- Service/algorithm name có xuất hiện không?

**Mức 2 — Token access**

- Native library load được không?
- Token/slot đúng không?
- Login hoạt động trong môi trường test không?
- KeyStore liệt kê được alias/certificate mong đợi không?

**Mức 3 — Cryptographic operation**

- Ký dữ liệu bằng private key trong token.
- Kiểm tra chữ ký bằng public key/certificate tương ứng.
- Kiểm thử key size và parameters production sử dụng.
- Không yêu cầu export private key.
- Đối chiếu operation với audit log thiết bị nếu chính sách yêu cầu.

**Mức 4 — Application integration**

- mTLS hoặc business-signing flow hoàn chỉnh.
- Certificate chain và trust validation.
- Exception handling, timeouts và retry strategy.
- Concurrency, session pooling và failover.
- Monitoring không làm lộ PIN hoặc key data.

### 12.2. SoftHSM hoặc token mô phỏng

Có thể dùng một phần mềm mô phỏng PKCS#11 như SoftHSM trong CI để kiểm tra luồng API và packaging, nhưng kết quả không chứng minh tính tương thích với tất cả HSM phần cứng.

Khác biệt có thể nằm ở:

- Mechanism được hỗ trợ.
- Session concurrency.
- Key attributes.
- PIN policy.
- Latency và thông số HA.
- Vendor-specific behavior.

Nên kết hợp **CI với token test phần mềm** và **integration tests trên thiết bị/vendor environment gần production** trước release quan trọng.

### 12.3. Kiểm tra không có fallback sai chính sách

Nếu ký bắt buộc sử dụng HSM, hãy kiểm tra việc token vắng mặt sẽ tạo ra **failure rõ ràng**, không âm thầm đổi sang private key file hoặc provider phần mềm. Đổi provider vì “tìm được algorithm” chưa đủ để bảo toàn boundary của private key.

Các test về fail-closed phải được thiết kế có kiểm soát trên môi trường test, không cố tình ngắt HSM production.

## 13. Kịch bản nâng JDK: từ provider phần mềm sang token

Giả sử một dịch vụ ký số đang dùng file PKCS12, nay cần chuyển private key sang HSM:

**Trước migration:**

~~~java
KeyStore ks = KeyStore.getInstance("PKCS12");
try (var in = java.nio.file.Files.newInputStream(path)) {
    ks.load(in, password);
}
~~~

**Sau migration — luồng khái niệm:**

1. Cài PKCS#11 vendor client trên OS/container phù hợp.
2. Kiểm tra HSM/token, slot, login và key attributes.
3. Cấu hình PKCS#11 provider.
4. Mở `KeyStore` kiểu `PKCS11` bằng provider đó.
5. Chọn đúng certificate/private key trong token.
6. Gọi `Signature` với algorithm và provider được duyệt.
7. Xác minh chữ ký bằng certificate/public key.
8. Kiểm thử end-to-end, không export private key.

Việc chuyển từ PKCS12 sang PKCS11 không chỉ là đổi chuỗi `"PKCS12"` thành `"PKCS11"`. Nó thay **nguồn gốc khóa**, quy trình provisioning, quyền truy cập, secret management, khả năng khôi phục và vận hành.

### 13.1. Giữ môi trường có thể tái hiện

Khi nhận báo cáo “ký thất bại trên JDK mới”, cần bản ghi có các trường:

~~~yaml
runtime:
  java_version: "Target JDK release and update"
  distribution: "Approved vendor"
  os_arch: "Linux-x86_64"
security:
  configured_providers:
    - "Provider names and versions"
  provider_for_signature: "Expected HSM provider"
pkcs11:
  library_version: "Vendor client version"
  token_model: "Test model"
  slot_selection: "Documented configuration"
  mechanism: "Expected signing mechanism"
application:
  artifact_sha256: "Hash of tested artifact"
  key_identity: "Non-secret stable identifier"
tests:
  provider_load: "PASS/FAIL"
  keystore_open: "PASS/FAIL"
  sign_and_verify: "PASS/FAIL"
  mTLS_flow: "PASS/FAIL/NOT_APPLICABLE"
~~~

Không ghi token PIN, private key, secret config hoặc thông tin nhạy cảm vào hồ sơ.

### 13.2. Rollout nhiều môi trường

Một trình tự triển khai có thể là:

1. Kiểm kê JDK/provider/native library của production hiện tại.
2. Dựng môi trường test với JDK đích và HSM client tương ứng.
3. Kiểm thử đơn luồng và concurrency với key test.
4. Xác minh certificate và key mapping.
5. Chạy regression test của business signing/mTLS.
6. Triển khai canary với audit/monitoring.
7. Theo dõi lỗi PKCS#11, latency ký và session usage.
8. Mở rộng rollout theo ngưỡng đã định, có phương án rollback.
9. Sau rollout, khóa lại baseline provider và tài liệu vận hành.

Rollback có thể phụ thuộc việc key đã được provisioning ở HSM và dữ liệu/chứng chỉ đã phát hành. Không giả định khôi phục bằng cách dùng lại bản ứng dụng cũ là đủ; cần kế hoạch tương thích key và certificate.

## 14. Những sai lầm thường gặp

### 14.1. Chỉ kiểm tra Security.getProvider(...)

Provider tồn tại không có nghĩa thư viện native, token, PIN và signing mechanism hoạt động. Cần test thao tác ký thực.

### 14.2. Pin tên provider vào mọi call site

Việc khóa một vendor-specific provider có thể làm các thao tác hash/Cipher không cần HSM mất tính portable. Chỉ ràng buộc provider nơi kiến trúc/chính sách cần.

### 14.3. Thay đổi provider order để xử lý một lỗi cục bộ

Thứ tự toàn cục có thể làm JSSE, SecureRandom và các engine khác chọn implementation mới. Ưu tiên xử lý đúng call site và kiểm tra tác động hệ thống.

### 14.4. Nhầm PKCS#11 với PKCS#12

PKCS12 là định dạng keystore; PKCS11 là giao diện tới token. Không thể dùng một file `.p12` như bằng chứng khóa đang được bảo vệ bởi HSM.

### 14.5. Giả định mọi JDK vendor có cùng native bridge

Custom runtime có thể không có `jdk.crypto.cryptoki`; vendor khác có cơ chế riêng. Xác nhận module, provider và native library trong artifact/runtime mục tiêu.

### 14.6. Hardcode slotListIndex hoặc alias và coi là ID bền vững

Thứ tự slot/alias có thể khác sau update driver hoặc token. Dùng mapping và quy trình xác thực key/cert phù hợp.

### 14.7. Bỏ qua key attributes

Có private key trên token không có nghĩa được phép ký bằng mọi mechanism. Kiểm tra chính sách và attribute key.

### 14.8. Log PIN để debug

PIN và secret phải được bảo vệ. Sử dụng hệ thống secret management, tránh command-line argument và log. Xóa mảng PIN khi thích hợp nhưng đừng xem đây là giải pháp bảo mật hoàn chỉnh.

### 14.9. Nới policy JDK một cách mù quáng

Certificate bị từ chối do thuật toán yếu không nên được “sửa” bằng cách vô hiệu hóa toàn bộ `disabledAlgorithms`. Cần thay certificate, thuật toán hoặc kế hoạch migration có kiểm soát.

### 14.10. Chỉ test với SoftHSM rồi tuyên bố tương thích HSM production

Token mô phỏng không phản ánh đầy đủ native driver, hardware mechanisms và session behavior. Phải xác minh trên thiết bị/vận hành đại diện.

### 14.11. Bỏ qua sự khác biệt build vs runtime

Một ứng dụng compile bằng JDK mới, nhưng chạy trong JRE image đã lược module, hoặc chạy trên OS thiếu vendor PKCS#11 library. Bytecode compatibility không bảo đảm security-provider compatibility.

### 14.12. Không xác minh key được dùng ở thiết bị

Ngay cả khi chữ ký hợp lệ, nó có thể được tạo bằng key khác hoặc provider khác mong đợi. Với hệ thống bắt buộc HSM, cần có cách xác minh key identity và hardware operation.

## 15. Checklist khi nâng cấp

### JDK và provider

- [ ] Đã ghi JDK distribution, version, update và OS/CPU.
- [ ] Đã liệt kê security provider names, order và services quan trọng.
- [ ] Đã xác minh module `jdk.crypto.cryptoki` hoặc bridge tương đương có mặt.
- [ ] Đã phân biệt KeyStore/Cipher/Signature provider với JSSE/TLS provider.
- [ ] Đã xem lại các security property về thuật toán bị hạn chế.
- [ ] Đã ghi rõ nơi provider được đăng ký và cấu hình.

### PKCS#11 và token

- [ ] Đã xác minh đường dẫn native library và dependency OS.
- [ ] Đã xác minh slot/slotListIndex, token identity và key mapping.
- [ ] Đã xác minh PIN/secret management theo chính sách.
- [ ] Đã mở KeyStore PKCS11 và liệt kê alias/certificate phù hợp.
- [ ] Đã thử thao tác ký bằng private key trên thiết bị.
- [ ] Đã xác minh key non-extractable khi chính sách yêu cầu.
- [ ] Đã kiểm tra mechanism, key attributes và certificate chain.
- [ ] Đã thử session concurrency, timeout và failure handling.
- [ ] Đã tránh logging bí mật hoặc thao tác khóa PIN trên production.

### Tương thích đa môi trường

- [ ] Đã thử trên JDK tối thiểu và JDK mục tiêu.
- [ ] Đã thử các JDK distributions thực sự được hỗ trợ.
- [ ] Đã thử với đúng native vendor library và HSM model.
- [ ] Đã kiểm tra custom runtime/jlink không thiếu module.
- [ ] Đã kiểm tra container permission, driver và network kết nối HSM.
- [ ] Đã chạy business signing và mTLS end-to-end nếu sản phẩm dùng.
- [ ] Đã kiểm tra không có fallback sai yêu cầu security.
- [ ] Đã lưu artifact checksum, logs đã redaction và test reports.
- [ ] Đã lập rollout, canary, monitoring và rollback plan.

## Kết luận

Security provider là lớp implementation của nhiều Java cryptography engines; PKCS#11 là giao diện liên kết ứng dụng với token/HSM thông qua provider và thư viện native. Khi nâng JDK, những lớp này có thể thay đổi theo **bản phân phối Java, module được đóng gói, provider order, algorithm policy, OS/CPU, vendor library và HSM mechanism**.

Chiến lược migration đáng tin cậy không dừng ở việc liệt kê `Security.getProviders()` hay compile thành công. Cần xác định **provider nào thực hiện thao tác nào**, **private key nằm ở đâu**, **module/native library nào có hiệu lực** và **lệnh ký/TLS end-to-end có đạt trên môi trường mục tiêu hay không**. Ghi nhận kết quả theo artifact, runtime và HSM cụ thể; chỉ giữ những tùy chọn tương thích và cơ chế fallback phù hợp với chính sách bảo mật đã được phê duyệt.

