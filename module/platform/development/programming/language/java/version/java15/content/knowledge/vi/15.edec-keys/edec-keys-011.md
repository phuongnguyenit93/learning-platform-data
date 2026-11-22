# Lưu khóa EdEC bằng cơ chế phù hợp và kiểm soát truy cập trong Java 15+

## 1. Mục tiêu

Một cặp khóa **EdEC** (Edwards-Curve) dùng cho **EdDSA** gồm **private key** và **public key**. Với Java 15+, hai lựa chọn thông dụng được JCA hỗ trợ là **Ed25519** và **Ed448**. Private key tạo chữ ký số; public key xác minh chữ ký. Sinh được cặp khóa bằng `KeyPairGenerator` mới là bước đầu: với một hệ thống thật, bạn phải quyết định **khóa được lưu ở đâu, ai được dùng nó, có được xuất khóa gốc không, khóa được xoay vòng và thu hồi thế nào**.

Bài học tập trung vào **lưu trữ và kiểm soát truy cập khóa EdEC** — không nhầm việc viết một file `.key` với quản lý khóa an toàn. Sau bài này, bạn có thể:

1. Phân biệt **private key, public key, certificate, key alias/key ID** và bản mã hóa khóa.
2. Chọn cơ chế lưu phù hợp: **Java `KeyStore` với `PKCS12`**, kho khóa của hệ điều hành, **HSM/PKCS#11** hoặc **KMS** được vận hành có kiểm soát.
3. Biết vì sao `KeyStore.PrivateKeyEntry` cần **private key đi kèm certificate chain**, và vì sao một chứng chỉ tự ký trong ví dụ không tự tạo sự tin cậy.
4. Đọc một khóa Ed25519 từ PKCS12, ký và xác minh bằng **JCA `Signature`**, không ghi private key vào log.
5. Thiết kế chính sách quyền truy cập tối thiểu, quản lý mật khẩu, audit, sao lưu, xoay vòng, thu hồi và ứng phó lộ khóa.
6. Tránh lỗi nguy hiểm: ghi PKCS#8 chưa mã hóa vào repository, nhầm public key với private key, dùng mật khẩu trong source/CLI hoặc xem `verify()==true` là bằng chứng danh tính tuyệt đối.

**Phạm vi:** sử dụng Java SE 15+ và các cơ chế vẫn có giá trị trong JDK hiện đại. Không khuyên áp dụng các cơ chế nội bộ/lỗi thời hoặc triển khai dự án mới trên một runtime Java 15 đã hết hỗ trợ. Hãy dùng JDK còn được nhà cung cấp bảo trì và chọn API tương thích theo môi trường.

## 2. Hiểu đúng dữ liệu khóa EdEC trước khi lưu

### 2.1. Private key và public key có vai trò khác nhau

| Đối tượng | Vai trò | Có cần bí mật? | Cách xử lý thường gặp |
| --- | --- | --- | --- |
| `PrivateKey` Ed25519/Ed448 | **Ký** một thông điệp | **Có** | Lưu trong keystore/KMS/HSM; giới hạn ai có thể dùng; không xuất/log khi không cần |
| `PublicKey` Ed25519/Ed448 | **Xác minh** chữ ký | Không phải bí mật | Phân phối có xác thực nguồn gốc, pinning hoặc certificate chain đáng tin cậy |
| `Certificate` X.509 | Liên kết public key với thông tin chủ thể và chữ ký cấp phát | Thường công khai | Cần xác minh chuỗi tin cậy, thời hạn, policy và danh tính thích hợp |
| `alias` / `keyId` | Định danh một entry/phiên bản khóa | Không phải private key | Đặt tên ổn định, ghi metadata, dùng khi chọn khóa ký/xác minh |

**EdEC/EdDSA là chữ ký số, không phải mã hóa dữ liệu.** Một chữ ký đúng bảo đảm sự khớp giữa dữ liệu, chữ ký và public key dùng để xác minh; việc gán public key ấy cho một người/tổ chức vẫn phải dựa vào **hệ thống tin cậy** của bạn.

**Ed25519 không đồng nghĩa X25519; Ed448 không đồng nghĩa X448.** `Ed25519`/`Ed448` thuộc EdDSA; `X25519`/`X448` thuộc XDH (trao đổi khóa). Không tự dùng một private key EdDSA như khóa XDH hoặc ngược lại. Khi protocol yêu cầu Ed25519, chọn `Signature.getInstance("Ed25519")`, không dùng tên `"EC"`/ECDSA.

### 2.2. `getEncoded()` không đồng nghĩa “đã được bảo vệ”

Một khóa JCA có thể cung cấp `getEncoded()`, nhưng **định dạng encoding** và **bảo mật của nơi lưu** là hai vấn đề khác nhau.

- `PublicKey.getEncoded()` thường trả về DER **SubjectPublicKeyInfo**, và `getFormat()` thường là `"X.509"`. Đó là dữ liệu khóa công khai **không phải** một chứng chỉ X.509.
- `PrivateKey.getEncoded()` thường trả về DER **PKCS#8 PrivateKeyInfo** (hoặc `"PKCS#8"` trong `getFormat()`). Nếu dữ liệu ở dạng `PrivateKeyInfo` không mã hóa, file chứa nó là **private key xuất trực tiếp** dù có đuôi `.der`, `.key` hay được bọc Base64/PEM.
- Một PEM block chứa `-----BEGIN PRIVATE KEY-----` có thể chỉ là Base64 của khóa chưa mã hóa. **Base64 không phải encryption**. Ngay cả `-----BEGIN ENCRYPTED PRIVATE KEY-----` cũng cần mật khẩu mạnh, thuật toán mã hóa phù hợp và chính sách giữ bí mật.
- Với HSM hoặc khóa không xuất được, `getEncoded()` có thể trả về **`null`**; điều đó không làm khóa vô dụng. Ta vẫn có thể ký qua provider nếu provider cho phép.

**Đừng coi kích thước `getEncoded()` là kích thước raw seed.** Ed25519 có raw private seed theo RFC 8032, nhưng PKCS#8 mang thêm cấu trúc/metadata. Public key Ed25519 dạng encoded point và `X509EncodedKeySpec` cũng không phải cùng định dạng. Không chuyển đổi bằng cách cắt đầu/cuối byte array theo con số đoán trước.

### 2.3. Các API có liên quan

- `KeyPairGenerator.getInstance("Ed25519")` hoặc `"Ed448"`: tạo khóa.
- `java.security.interfaces.EdECPrivateKey` / `EdECPublicKey`: giao diện EdEC. Một số khóa có thể không cho xuất byte bí mật.
- `KeyFactory.getInstance("Ed25519")`: xây dựng khóa từ `PKCS8EncodedKeySpec` / `X509EncodedKeySpec` hoặc spec EdEC phù hợp.
- `KeyStore.getInstance("PKCS12")`: làm việc với kho khóa theo format PKCS#12.
- `Signature.getInstance("Ed25519")` / `"Ed448"`: ký và xác minh.
- `java.security.cert.Certificate`, `CertPathValidator` hoặc bộ quản lý trust tương ứng: xử lý danh tính/chứng chỉ khi mô hình tin cậy cần chứng chỉ.

**Lưu ý:** một `PublicKey` trong DER SPKI không tự chứng minh mình thuộc về ai; một `Certificate` tự ký cũng không tự chứng minh ai đó đã xác thực danh tính của chủ thể.

## 3. Bắt đầu bằng mô hình đe dọa

Trước khi quyết định format file, hãy trả lời:

1. **Khóa dùng làm gì?** Ký nội bộ cho service, ký release, xác thực tài liệu, chứng thực danh tính, hay khóa thử nghiệm?
2. **Ai có quyền ký?** Chỉ một service account, nhiều replica, một nhân sự vận hành hay một thiết bị phần cứng?
3. **Khóa có cần xuất ra ngoài hay không?** Nếu không, ưu tiên cơ chế **non-exportable** có thể thao tác ký ngay trong KMS/HSM.
4. **Thời gian tồn tại?** Khóa tạm cho test, khóa hoạt động nhiều tháng, hay khóa gốc dùng dài hạn?
5. **Giới hạn rủi ro?** Điều gì xảy ra nếu file keystore, password, máy chủ ứng dụng, tài khoản cloud hoặc log bị đọc trộm?
6. **Cần audit, revoke, rotate và recover tới mức nào?** Có cần biết chính xác người/service đã sử dụng một phiên bản khóa?

### Không có một kiểu lưu trữ tốt cho mọi ứng dụng

| Cơ chế | Khi phù hợp | Ưu điểm | Giới hạn cần biết |
| --- | --- | --- | --- |
| `KeyStore` file `PKCS12` | Ứng dụng Java, môi trường có filesystem được kiểm soát, phân phối có quy trình | Chuẩn, JCA hỗ trợ sẵn, private-key entry có thể được bảo vệ bằng mật khẩu | Nếu kẻ tấn công lấy được **file + password**, họ có thể giải mã/xuất khóa; phải có ACL, backup và quản lý password |
| OS key store / credential store | Ứng dụng desktop/service có tích hợp bảo mật OS | Có thể gắn quyền với account/device | API/provider và khả năng hỗ trợ EdEC khác nhau theo hệ điều hành; không giả định portable |
| HSM / token + PKCS#11 provider | Giá trị khóa cao, cần chính sách **non-exportable**, ký trong thiết bị và audit | Khóa gốc có thể không rời thiết bị; kiểm soát bằng token/PIN/role | Cần phần cứng/provider, vận hành, backup/HA, policy và hỗ trợ Ed25519/Ed448 thực tế |
| Managed KMS / cloud HSM | Dịch vụ nhiều node, cần IAM, audit tập trung, rotation và availability | Chính sách quyền, lifecycle, logging tập trung; nhiều giải pháp cho ký **không xuất private bytes** | Chỉ dùng nếu provider/dịch vụ hỗ trợ đúng **Ed25519/Ed448, thuật toán, chữ ký và định dạng** mà giao thức yêu cầu; có độ trễ/chi phí/phụ thuộc mạng |
| Raw `PKCS#8` file đã mã hóa phù hợp | Một số hệ thống cần trao đổi khóa chuẩn và có giải pháp bảo vệ riêng | Dễ tương tác với hệ thống bên ngoài | Phải lựa chọn encryption/KDF phù hợp, kiểm soát file và password; **không** coi PKCS#8 hoặc PEM thường là mã hóa sẵn |

Trong một ứng dụng production ký các thông điệp quan trọng, **KMS/HSM có quyền gọi ký tách biệt** thường là thiết kế đáng cân nhắc. Trong ứng dụng Java nhỏ cần keystore local, `PKCS12` với secret delivery, ACL và quy trình xoay vòng rõ ràng là cách tiếp cận hợp lý. Cần kiểm tra **tính sẵn có của EdDSA trong provider**; một kho khóa có tên PKCS12 hoặc PKCS11 chưa bảo đảm thuật toán ký được hỗ trợ.

## 4. `KeyStore` và `PKCS12`: hiểu đúng entry và quyền bảo vệ

### 4.1. Vì sao chọn PKCS12?

`java.security.KeyStore` là API trừu tượng để lưu/đọc các entry mật mã. **`PKCS12`** là type chuẩn được Java SE yêu cầu hỗ trợ, có tính tương tác tốt hơn các format keystore riêng biệt. Dùng tường minh:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
```

Đây là **dòng minh họa**, cần import `java.security.KeyStore` và đặt trong method có xử lý exception. Type `PKCS12` xác định cơ chế/định dạng keystore; nó **không tự tạo role, file permissions hay network isolation**.

### 4.2. `PrivateKeyEntry` chứa private key **và certificate chain**

`KeyStore.PrivateKeyEntry` lưu một private key và **chuỗi certificate** đi kèm. Để gọi `KeyStore.setKeyEntry(alias, privateKey, password, chain)` với `PrivateKey`, thông thường cần cung cấp **certificate chain tương ứng**, không phải `null`. Bạn không thể giả định API PKCS12 sẽ chấp nhận một bare Ed25519 private key không có certificate như một `PrivateKeyEntry` bình thường.

Một `KeyStore.TrustedCertificateEntry` lưu **chứng chỉ tin cậy**, **không** chứa private key để ký. `KeyStore.SecretKeyEntry` dùng cho `SecretKey` đối xứng, **không** dùng để đưa trực tiếp private key Ed25519 vào thay cho `PrivateKeyEntry`.

Có ba lớp cần phân biệt:

- **Keystore password:** dùng để mở/kiểm tra tính toàn vẹn và bảo vệ keystore tùy provider.
- **Key entry protection:** dùng khi truy cập key entry, ví dụ `KeyStore.PasswordProtection`; với một số provider PKCS12 thường dùng cùng password cho store và key.
- **File/host permissions:** quyết định **ai có thể đọc file bytes**, không được sinh tự động chỉ vì bạn gọi `KeyStore.store`.

Mật khẩu keystore **không thay thế** file ACL, IAM, backup security hoặc khả năng phát hiện một chương trình có đặc quyền đang chạy trong cùng account.

### 4.3. Chứng chỉ tự ký trong bài lab **không** phải chứng chỉ production

`keytool -genkeypair` có thể tạo một cặp Ed25519 và chứng chỉ **self-signed** X.509 chỉ để làm đầy một `PrivateKeyEntry` phục vụ thí nghiệm. Chứng chỉ này không được một CA đáng tin xác minh danh tính; do đó:

- `entry.getCertificate().getPublicKey()` cung cấp đúng public key để kiểm tra **chữ ký vừa tạo trong bài lab**.
- `Signature.verify(...) == true` chỉ chứng minh chữ ký khớp **public key đang đưa vào** và bytes thông điệp đã ký.
- Nó **không tự xác nhận** tên CN, chủ sở hữu, vai trò hay bất kỳ danh tính bên ngoài nào.
- Với production, phải có **trust model**: certificate path validation (khi dùng PKI), key pinning có phân phối tin cậy, hoặc key registry ánh xạ `keyId` tới public key hợp lệ. Khi sử dụng certificate, cần xem validity, key usage/policy phù hợp và tình trạng thu hồi theo yêu cầu giao thức.

**Đừng tự động import bất kỳ self-signed certificate nào vào truststore chung rồi xem như đã đáng tin.**

## 5. Ví dụ Java 15+ chạy được: tạo PKCS12 Ed25519, mở và ký

Ví dụ sử dụng **chỉ công cụ `keytool` của JDK và thư viện chuẩn Java SE**. Nó tạo keystore file cho mục đích học, dùng `Console.readPassword` để tránh để mật khẩu trong **mã nguồn** hoặc đối số command-line, lấy `PrivateKeyEntry` và ký/xác minh một thông điệp. Không in private key, password hay dữ liệu chữ ký.

### 5.1. Tạo keystore dùng `keytool`

Tại một **thư mục thử nghiệm riêng**, chạy bằng JDK có hỗ trợ Ed25519 (Java 15+):

```bash
keytool -genkeypair -alias app-signing -keyalg Ed25519 -sigalg Ed25519 -storetype PKCS12 -keystore demo-ed25519.p12 -dname "CN=Learning Only" -validity 30
```

`keytool` yêu cầu nhập mật khẩu keystore **tương tác**; hãy dùng mật khẩu thử nghiệm riêng, đủ mạnh để công cụ chấp nhận. **Đừng chèn `-storepass YOUR_REAL_PASSWORD` hoặc `-keypass YOUR_REAL_PASSWORD` vào command line/script**: mật khẩu có thể lộ trong shell history, process listing, bản ghi CI và log.

Lệnh trên tạo một `PKCS12` chứa entry alias `app-signing` với:

- Một **private key Ed25519**.
- Một **chứng chỉ X.509 tự ký** tương ứng, hợp lệ theo thời gian ví dụ 30 ngày.
- Các thông số bảo vệ do provider/`keytool` hiện hành chọn. Cần kiểm tra tính tương thích/thuật toán nếu đem file sang một runtime khác.

**Không dùng chính file thử nghiệm này làm danh tính production.** Mục đích của certificate trong bài là để có một `PrivateKeyEntry` và public key tương ứng phục vụ xác minh trực tiếp.

Sau khi tạo, chỉ người dùng/tiến trình phù hợp mới nên có quyền đọc file. Trên hệ Unix, có thể kiểm tra quyền và giới hạn cho user sở hữu:

```bash
chmod 600 demo-ed25519.p12
```

`chmod` chỉ áp dụng trên hệ thống/volume có ngữ nghĩa quyền POSIX phù hợp. Trên Windows, hãy cấu hình **NTFS ACL** theo account chạy ứng dụng. File permissions **là một lớp bảo vệ**, không thay thế mật khẩu hay ngăn một process đã có đặc quyền tương đương.

### 5.2. File `EdECKeyStoreDemo.java`

Tạo file cùng thư mục với `demo-ed25519.p12`:

```java
import java.io.Console;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.Signature;
import java.util.Arrays;

public class EdECKeyStoreDemo {
    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Run this program from an interactive terminal");
        }

        char[] password = console.readPassword("PKCS12 password: ");
        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("Password is required");
        }

        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            try (InputStream in = Files.newInputStream(
                    Path.of("demo-ed25519.p12"))) {
                store.load(in, password);
            }

            if (!store.entryInstanceOf(
                    "app-signing", KeyStore.PrivateKeyEntry.class)) {
                throw new IllegalStateException("Missing private-key entry");
            }

            KeyStore.PasswordProtection protection =
                    new KeyStore.PasswordProtection(password);
            KeyStore.PrivateKeyEntry entry;
            try {
                entry = (KeyStore.PrivateKeyEntry) store.getEntry(
                        "app-signing", protection);
            } finally {
                protection.destroy();
            }

            byte[] data = "Hello EdEC".getBytes(StandardCharsets.UTF_8);
            Signature signer = Signature.getInstance("Ed25519");
            signer.initSign(entry.getPrivateKey());
            signer.update(data);
            byte[] signature = signer.sign();

            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(entry.getCertificate().getPublicKey());
            verifier.update(data);
            boolean verified = verifier.verify(signature);

            verifier.initVerify(entry.getCertificate().getPublicKey());
            verifier.update("tampered".getBytes(StandardCharsets.UTF_8));
            boolean tamperedVerified = verifier.verify(signature);

            System.out.println("entryPresent=true");
            System.out.println("certificatePresent="
                    + (entry.getCertificate() != null));
            System.out.println("signatureLength=" + signature.length);
            System.out.println("verified=" + verified);
            System.out.println("tamperedVerified=" + tamperedVerified);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 5.3. Biên dịch và chạy

Dùng JDK hiện đại hỗ trợ `--release 15`, ví dụ JDK 21 hoặc mới hơn có hỗ trợ target này:

```bash
javac --release 15 -encoding UTF-8 EdECKeyStoreDemo.java
java EdECKeyStoreDemo
```

Khi Java hiện dấu nhắc `PKCS12 password:`, nhập **đúng mật khẩu đã chọn khi chạy `keytool`**. Password input không cần echo ra màn hình.

**Sau dấu nhắc mật khẩu**, với JDK/provider hỗ trợ Ed25519, chương trình in chính xác:

```text
entryPresent=true
certificatePresent=true
signatureLength=64
verified=true
tamperedVerified=false
```

Đây là output đã được kiểm tra với một keystore Ed25519 tạo bằng `keytool` và mã biên dịch ở mức `--release 15`. Không in giá trị khóa hoặc chữ ký vì chúng không cần thiết để xác định sự thành công và không nên được đưa vào log. Độ dài chữ ký Ed25519 thuần là **64 byte**.

Nếu chạy từ IDE hoặc môi trường không có **interactive console**, `System.console()` có thể trả `null`. Khi đó ví dụ chủ động báo lỗi; hãy chạy từ một terminal có hỗ trợ console. Trong ứng dụng server/CI, **không dùng dấu nhắc tương tác**: tích hợp một nguồn secret an toàn có chính sách truy cập, chẳng hạn secret manager/KMS, callback bảo mật của provider hoặc cơ chế cấp bí mật được tổ chức phê duyệt.

### 5.4. Từng bước trong code

1. `Console.readPassword` nhận password dưới dạng `char[]`, tránh viết password literal vào file source và tránh truyền qua CLI arguments. `char[]` có thể được xóa sau dùng, nhưng **không bảo đảm xóa sạch mọi bản sao bí mật trong memory/native provider**.
2. `KeyStore.getInstance("PKCS12")` chọn keystore format chuẩn; `store.load(in, password)` mở file. Mật khẩu sai hoặc file lỗi sẽ được báo qua exception thích hợp.
3. `entryInstanceOf(..., PrivateKeyEntry.class)` xác nhận alias chính xác là private-key entry, không phải certificate-only entry hoặc alias không tồn tại.
4. `PasswordProtection` cung cấp password khi gọi `getEntry`. `protection.destroy()` xóa bản sao password thuộc protection object trong `finally`.
5. `entry.getPrivateKey()` cung cấp `PrivateKey` cho provider `Signature`. Code **không** gọi `getEncoded()` để xuất private bytes, và không lưu private key vào file/log khác.
6. `entry.getCertificate().getPublicKey()` lấy public key tương ứng từ certificate của entry; dùng để verify, **không** tự đánh giá tính tin cậy của certificate.
7. `Signature.getInstance("Ed25519")` ký đúng bytes `"Hello EdEC"` được mã hóa UTF-8; cùng public key xác minh thành công.
8. Khi đổi dữ liệu sang `"tampered"` mà giữ chữ ký cũ, `verify` là `false`. Đây là kiểm tra cơ bản về tính toàn vẹn.
9. `Arrays.fill(password, '\0')` giảm thời gian password nằm trong mảng Java do ứng dụng kiểm soát, nhưng không thay thế mã hóa, ACL hoặc bí mật ở cấp hệ điều hành.

**Không hard-code mật khẩu cho deployment.** Bài dùng nhập thủ công để giữ ví dụ tự chạy được mà không đưa secret vào command line. Trong production, ngay cả password an toàn cũng không đủ nếu account chạy app có khả năng đọc cả keystore và nơi lưu mật khẩu, hoặc mã độc đã chạy trong cùng process.

## 6. PKCS12 không phải khóa không xuất được

Một keystore file PKCS12 mã hóa private key để **bảo vệ khi lưu trữ**. Nhưng sau khi nạp thành công với password, ứng dụng/provider có thể có private key ở memory và có thể xuất nó tùy loại khóa. Vì vậy:

- Một file `.p12` bị sao chép không nhất thiết dẫn ngay đến lộ private key nếu bảo vệ mật khẩu và thuật toán đủ mạnh, nhưng vẫn là **sự kiện phải điều tra**.
- Nếu **cả keystore file và mật khẩu bị lộ**, attacker có thể khôi phục private key và tạo chữ ký trái phép.
- Chỉ giới hạn quyền đọc file là **chưa đủ** nếu bất kỳ process nào trong cùng account cũng có thể yêu cầu ứng dụng ký tùy ý.
- Với nhu cầu **non-exportable**, cân nhắc HSM/KMS cung cấp quyền `sign` mà không xuất private key thô. Lưu ý “không xuất được” không tự ngăn attacker **lạm dụng API ký** khi họ đã chiếm được quyền gọi.

Nếu đang tạo cặp khóa Ed25519 bằng `KeyPairGenerator` ngay trong Java, muốn đưa `PrivateKey` vào `KeyStore.PrivateKeyEntry` cần một **certificate chain tương ứng**; không chỉ gọi `setKeyEntry(alias, privateKey, password, null)` rồi kỳ vọng mọi provider sẽ cho lưu. Nếu hệ thống không dùng PKI/certificates và cần khóa không xuất được, một KMS/HSM hỗ trợ EdDSA hoặc kho khóa chuyên biệt có thể phù hợp hơn.

## 7. Lưu public key và định danh khóa

Public key không phải bí mật như private key nhưng **nguồn gốc của public key cực kỳ quan trọng**. Nếu kẻ tấn công đổi được public key trong cấu hình bên xác minh, họ có thể ký bằng private key khác của họ và khiến `verify` thành công với public key giả.

### 7.1. Public key DER SPKI

Đối với khóa công khai có khả năng export, `PublicKey.getEncoded()` thường cho DER **SubjectPublicKeyInfo**. Khi cần khôi phục từ biểu diễn ấy:

```java
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;

// Đoạn minh họa bên trong method, với spkiBytes là DER hợp lệ:
PublicKey publicKey = KeyFactory.getInstance("Ed25519")
        .generatePublic(new X509EncodedKeySpec(spkiBytes));
```

Đoạn trên **không độc lập** vì `spkiBytes` phải được cấp từ dữ liệu thực tế và đã có ranh giới trust. Nó chỉ chuyển **encoding sang đối tượng khóa**, không xác minh ai là chủ sở hữu.

Để phân phối, có thể chuyển bytes DER sang PEM **public key** dạng Base64 và lưu cùng metadata `keyId`, curve và phiên bản. Không nhầm public key X.509 **SPKI** với **X.509 Certificate**. Nếu dùng chứng chỉ, việc đọc `Certificate.getPublicKey()` cũng **không** tự thực hiện `CertPathValidator` hoặc kiểm tra độ tin cậy.

### 7.2. Key ID, version và rotation

Một chữ ký trong hệ thống nhiều phiên bản khóa nên gắn với định danh phù hợp (ví dụ `keyId="sign-2026-11"`) và metadata của giao thức:

- Khi **ký**, chọn private key đang active; ghi `keyId`/curve/mode vào cấu trúc dữ liệu cần ký hoặc thông điệp theo quy tắc chống thay thế/nhầm khóa của giao thức.
- Khi **verify**, dựa trên `keyId` được kiểm soát để chọn **public key đáng tin** tương ứng, rồi kiểm tra chữ ký trên bytes chính xác.
- Khi **rotate**, tạo khóa mới; chuyển writer sang khóa mới và giữ các public keys cũ đủ lâu để verify dữ liệu cũ theo chính sách.
- Khi **revoke**, ngừng ký bằng khóa nghi ngờ, quyết định cách xử lý chữ ký cũ (thời điểm ký, trust, revocation, audit và yêu cầu pháp lý/nghiệp vụ).
- Nếu cần chữ ký dài hạn, thiết kế thêm bằng chứng về **thời gian ký, danh tính và tình trạng chứng chỉ**; Ed25519 `verify` một mình không cung cấp tính năng ấy.

**Đừng dùng alias cố định `app-signing` để xóa/mặc định ghi đè entry cũ trong production** nếu ứng dụng còn phải xác minh chữ ký đã phát hành bằng khóa cũ. Hãy thiết kế version và chính sách lưu giữ phù hợp.

## 8. HSM, PKCS#11, KMS: khi không nên mang private bytes vào JVM

### 8.1. HSM/PKCS#11

**PKCS#11** là chuẩn giao tiếp với token và module mật mã. JDK có hỗ trợ tích hợp provider cho các tình huống phù hợp, nhưng **không phải mọi thiết bị/token/provider đều hỗ trợ Ed25519 hay Ed448**.

Một số mô hình cấp quyền:

- Private key được **sinh ngay trong thiết bị**, được gắn nhãn **non-extractable** và policy ký.
- Ứng dụng dùng identity/role/token/PIN hoặc cơ chế định danh khác để truy cập.
- JCA `Signature` có thể làm việc với private key object do provider cung cấp **nếu** provider hỗ trợ thuật toán. Với một số nhà cung cấp, cần SDK/API riêng thay vì giả định JCA portable.
- Có cơ chế audit, rate limit, dual control và backup/HA theo nền tảng.

**Không cố gọi `privateKey.getEncoded()` để “sao lưu” khóa non-exportable.** Nếu trả `null`, đó có thể là thiết kế bảo mật. Hãy dùng quy trình backup/replication/key recovery **được chính HSM hỗ trợ** nếu hệ thống cần.

### 8.2. Managed KMS

Trong mô hình **KMS**, ứng dụng thường gửi digest/thông điệp theo định dạng API đã quy định và yêu cầu dịch vụ **ký bằng key ID**, rồi nhận signature. Nhưng không thể khẳng định mọi KMS đều hỗ trợ Ed25519/Ed448, hoặc API nào cũng nhận cùng byte/cho ra cùng encoding. Phải đối chiếu:

- Provider có hỗ trợ **Ed25519/Ed448** thật không? Đó có phải thuật toán được cho phép theo policy/fips mode?
- API ký nhận **raw message** hay **prehashed digest**? EdDSA thuần và prehash **không phải một**.
- Chữ ký xuất ra theo **RFC 8032 raw signature** hay định dạng container khác?
- API verify/trust, public-key format, curve ID và giới hạn kích thước?
- IAM/service identity, key state, rate limit, audit logging, HA, region và policy xóa/rotate?
- Secret/service credentials của ứng dụng có được bảo vệ tốt hơn việc chép private bytes vào file không?

**Quyền gọi KMS Sign là một quyền nhạy cảm:** dù private key không export được, attacker có quyền ký vẫn có thể tạo chữ ký trái phép. Áp dụng least privilege theo workload và giám sát số lượng/kiểu yêu cầu ký.

## 9. Kiểm soát truy cập phải được thiết kế theo nhiều lớp

| Lớp | Cần kiểm soát gì? | Ví dụ thực hành |
| --- | --- | --- |
| **Quản trị khóa** | Ai được tạo/xóa/rotate/disable và thay policy? | Tách nhóm admin khóa khỏi service ký; audit thay đổi cấu hình |
| **Sử dụng khóa** | Ai được gọi `Sign` và trong điều kiện nào? | Role tối thiểu, chỉ workload cần thiết, xác thực mạnh |
| **File/host** | Ai có thể đọc/copy/sửa `.p12`, backup và process memory? | OS ACL, account service riêng, filesystem hardening, hạn chế root/admin |
| **Mật khẩu/secret** | Secret được đưa vào app theo đường nào? | Console cho lab, secret manager/callback an toàn cho server; không hard-code, không để trong source/args |
| **Runtime** | Ai có quyền chạy code trong cùng process hoặc attach/debug? | Giới hạn shell access, debug/heap dump, monitoring agent và deployment privileges |
| **Giao thức** | Ai có thể yêu cầu ký message nào? | Authorization business-level, domain separation, kiểm soát payload, limits/rate limiting |
| **Giám sát** | Có phát hiện lạm dụng/đọc trái phép không? | Audit alias/key ID, actor, thời gian, action, kết quả; không ghi raw secret |
| **Khôi phục** | Khi mất/lộ khóa phải làm gì? | Backup được mã hóa, restore drill, rotation/revocation playbook |

**Tách quyền “đọc file khóa” với “được phép yêu cầu ký”**. Ví dụ một API nội bộ không nên ký bất kỳ bytes nào do client chưa được ủy quyền gửi chỉ vì service có access tới `PrivateKey`.

Với hệ thống nhiều người thuê (*multi-tenant*), nên tách khóa/alias hoặc policy phù hợp từng tenant và kiểm tra authorization trước khi chọn key ID. Không sử dụng một alias do request khách hàng cung cấp mà không kiểm soát/giới hạn danh sách cho phép.

## 10. Quản lý vòng đời: tạo, phân phối, rotate, revoke, backup

### Giai đoạn 1 — tạo khóa

- Dùng nguồn ngẫu nhiên mật mã phù hợp của provider; `KeyPairGenerator.getInstance("Ed25519")` là lựa chọn JCA khi cần khóa export được.
- Ưu tiên tạo khóa **bên trong HSM/KMS** nếu yêu cầu non-exportable.
- Ghi metadata: owner, mục đích, thuật toán, curve, key ID, ngày kích hoạt/hết hạn, hệ thống dùng và policy.

### Giai đoạn 2 — lưu và cấp quyền

- PKCS12: bảo vệ password, quyền file, nơi backup, quyền process và secrets injection.
- HSM/KMS: phân tách role thao tác ký, role quản trị, policy xuất khóa và audit.
- Không phân phối private key cho nhiều server nếu có thể dùng dịch vụ ký tập trung hoặc cơ chế cấp quyền theo workload tốt hơn.

### Giai đoạn 3 — sử dụng

- Kiểm tra caller trước khi ký; áp dụng allowlist định dạng hoặc domain separation nếu giao thức yêu cầu.
- Bảo đảm **chính xác message bytes**, encoding UTF-8/canonicalization và EdDSA mode giữa bên ký và verify.
- Không ghi private key, raw private encoding, password, session PIN hoặc dữ liệu nhạy cảm vào log.
- Audit **key ID và quyết định truy cập**, không audit raw secret.

### Giai đoạn 4 — rotate và revoke

- Tạo key ID mới thay vì ghi đè âm thầm khóa active.
- Phân phối public key mới có xác thực; chuyển writer sang key mới.
- Giữ public key cũ để xác minh dữ liệu lịch sử trong khoảng retention theo chính sách.
- Khi nghi lộ private key, **ngừng ký**, vô hiệu hóa/revoke key, điều tra việc sử dụng trái phép, phát hành khóa mới và xem xét chữ ký đã phát hành có còn được tin hay không.

### Giai đoạn 5 — backup, restore và hủy

- Backup phải được mã hóa và có quyền truy cập tối thiểu; restore cần được thử, không chỉ giả định có file backup là đủ.
- Với HSM non-exportable, phải có cơ chế vendor-supported backup/HA hoặc kế hoạch mất khóa; không giả định xuất private bytes.
- Khi xóa khóa, đánh giá cả cache, snapshots, backups, replicas và bản copy đã từng export.
- Xóa một file hoặc ghi đè byte array **không đảm bảo** xóa an toàn mọi bản sao trên SSD, JVM heap, swap hoặc cloud snapshots; xử lý theo chính sách storage và encryption-at-rest.

## 11. Sai lầm thường gặp và cách sửa

| Sai lầm | Rủi ro | Cách đúng |
| --- | --- | --- |
| Lưu `privateKey.getEncoded()` vào `.txt`, Git hoặc database plaintext | Lộ private key đầy đủ | KeyStore mã hóa có ACL hoặc HSM/KMS; không xuất nếu không cần |
| Xem Base64/PEM là encryption | Ai có file cũng có raw secret | Phân biệt encoding và encryption; dùng container được bảo vệ |
| Dùng `-storepass real-password` trong command line của production | Lộ secret qua shell history/log/process args | Prompt, callback bảo mật, secret manager hoặc provider-specific protected path |
| Chỉ đặt mật khẩu file `.p12` nhưng không giới hạn file permissions | Process khác có thể copy dữ liệu để tấn công offline | Giới hạn ACL và bảo vệ password/backup |
| Coi self-signed certificate từ `keytool` là danh tính production | Bất cứ ai cũng có thể tự ký một cert | Xác thực trust chain/pinning/registry theo policy |
| Xem `verify() == true` là đã xác thực người gửi | Chỉ biết chữ ký khớp public key đầu vào | Xác thực nguồn gốc của public key và quyền/key ID |
| Dùng `KeyStore.TrustedCertificateEntry` để lấy private key | Entry đó không có private key | Dùng `PrivateKeyEntry` và certificate chain |
| `setKeyEntry(alias, privateKey, password, null)` | Không có chain phù hợp với private-key entry | Cung cấp certificate chain tương ứng hoặc chọn kho khóa khác |
| Nhầm `X509EncodedKeySpec` là certificate | Không có thông tin CA/chain/trust | Phân biệt SPKI public key với certificate |
| Tin rằng mọi EdEC key có `getEncoded()` | HSM/provider có thể trả `null` | Ký thông qua provider; không dựa vào export |
| Xem KMS non-exportable là không thể bị lạm dụng | Attacker vẫn có thể gọi Sign nếu có quyền | Giới hạn service identity, authorization, audit, rate limits |
| Trộn Ed25519 với X25519 | Thuật toán chữ ký và key agreement khác nhau | Giữ đúng loại key/curve và protocol |
| Ký dữ liệu sau khi phía verify chuẩn hóa khác | Chữ ký không còn khớp | Quy định canonical byte representation duy nhất |
| Chỉ rotate private key mà không cập nhật public keys/ID | Không verify được dữ liệu cũ hoặc nhận nhầm khóa | Version hóa key ID và phát hành public key đáng tin |
| Giữ password trong `String`/heap dump/log | Có nhiều bản sao bí mật khó xóa | Tối thiểu hóa vòng đời, dùng `char[]`/API bí mật khi có thể; harden runtime |

## 12. Lỗi Java/API cần nhận diện

| Lỗi | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `IOException` tại `KeyStore.load` | Sai password, dữ liệu keystore lỗi, I/O hoặc integrity check thất bại | Kiểm tra đường dẫn, đúng type/password và backup; không in password |
| `KeyStoreException` | Keystore chưa load, loại entry/provider không hợp lệ, hoặc thao tác thất bại | Kiểm tra `getInstance("PKCS12")`, trạng thái `load`, alias và provider |
| `UnrecoverableKeyException` / `UnrecoverableEntryException` | Password bảo vệ entry sai hoặc entry không thể phục hồi | Xác định cơ chế password riêng và khôi phục qua quy trình hợp lệ |
| `NoSuchAlgorithmException` | Provider thiếu thuật toán EdDSA/Ed25519/Ed448 hoặc cơ chế bảo vệ tương ứng | Kiểm tra JDK/provider/security policy; không âm thầm đổi thuật toán |
| `CertificateException` | Certificate không hợp lệ khi load/store hoặc parse | Kiểm tra certificate chain và định dạng, xử lý qua PKI phù hợp |
| `InvalidKeyException` | Key không phù hợp `Signature` hoặc không có quyền dùng | Dùng đúng Ed25519/Ed448 và provider |
| `SignatureException` | Engine ký/xác minh gặp dữ liệu/trạng thái không hợp lệ | Kiểm tra thứ tự `initSign/initVerify → update → sign/verify` và signature encoding |
| `verify() == false` | Signature/message/public key không khớp | Kiểm tra bytes, curve, key ID, EdDSA parameters và nguồn key |
| `System.console() == null` | Chạy IDE, script/pipe hoặc môi trường không tương tác | Dùng terminal cho ví dụ; dùng secret delivery thích hợp trong server |
| `null` khi gọi `getEncoded()` | Key không thể export theo provider | Không ép xuất; dùng handle/API ký được provider hỗ trợ |
| Alias thiếu, trả `null` | Tên entry sai hoặc keystore không có key | Kiểm tra `containsAlias` / `entryInstanceOf` trước khi dùng |
| Certificate không được trust | File tạo bằng `keytool` là self-signed hoặc chain chưa được xác minh | Thực hiện trust validation phù hợp; không bỏ qua certificate errors |

Nếu ứng dụng thực thi chữ ký, **thất bại khi khôi phục key hoặc xác thực trust phải là lỗi rõ ràng**; đừng bắt mọi `GeneralSecurityException` rồi trả mặc định `true` hoặc tự dùng một private key khác không được ủy quyền.

## 13. Checklist trước khi đưa EdEC key vào môi trường thật

- [ ] Thuật toán và giao thức đã quy định đúng `Ed25519` hay `Ed448` (không nhầm XDH/ECDSA)?
- [ ] Private key cần **non-exportable** hay có thể bảo vệ đủ bằng file PKCS12?
- [ ] Nếu dùng PKCS12, đã lưu dưới dạng `PrivateKeyEntry` có certificate chain phù hợp, password mạnh, ACL và backup được bảo vệ?
- [ ] Nếu dùng HSM/KMS, provider **thực sự hỗ trợ EdDSA curve, signature format và mode** được yêu cầu?
- [ ] Password/credential có được cấp bằng kênh an toàn, không hard-code hoặc đưa vào process args/log?
- [ ] Quyền ký, quyền tạo/xóa khóa, quyền cấp grant và quyền khôi phục được tách rõ?
- [ ] Có authorization business-level trước khi service ký message cho caller không?
- [ ] Public key có được **phân phối và gắn danh tính/key ID theo cơ chế tin cậy**, không chỉ được tải từ nơi khách hàng chọn?
- [ ] Hệ thống có policy rotate, revoke, retention public key cũ và response khi private key bị lộ?
- [ ] Audit có actor/action/key ID và kết quả, nhưng **không** chứa private key/password?
- [ ] Đã thử khôi phục keystore/backup ở môi trường tách biệt và kiểm tra hỗ trợ provider/JVM đích?
- [ ] Có test **ký đúng**, **verify đúng**, **thay thông điệp verify false**, sai alias/password và mất certificate?
- [ ] Có chính sách kiểm soát heap dumps, debug access, snapshots, secret exposure và cleanup?
- [ ] Khi dùng một chứng chỉ tự ký trong bài lab, có phân biệt **test signature validity** với **production identity trust** không?

## 14. Tài liệu chính thức và tiêu chuẩn

- **Java SE 15 — `java.security.KeyStore`**, `PrivateKeyEntry`, `PasswordProtection`, `getEntry`, `load` và `store`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/KeyStore.html
- **Java SE hiện đại — `KeyStore` và bảo vệ private-key entry:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html
- **Java SE 15 — `keytool`**, `-genkeypair`, `-storetype`, certificate chain và password handling: https://docs.oracle.com/en/java/javase/15/docs/specs/man/keytool.html
- **Java SE 15 — Java Security Overview**, cơ chế key/certificate storage: https://docs.oracle.com/en/java/javase/15/security/java-security-overview1.html
- **Java SE hiện đại — JCA Reference Guide**, keystore, provider và lựa chọn API: https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html
- **Java SE 15 — `Signature`**, xác thực chữ ký: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/Signature.html
- **Java SE 15 — `EdECPrivateKey` và `EdECPublicKey`**, giao diện khóa Edwards-Curve: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html và https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/interfaces/EdECPublicKey.html
- **Java SE 15 — `PKCS8EncodedKeySpec` / `X509EncodedKeySpec`**, các định dạng encoding: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html và https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html
- **OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm**, tính năng chính thức từ Java 15: https://openjdk.org/jeps/339
- **RFC 8032 — EdDSA**, thông số của Ed25519 và Ed448: https://www.rfc-editor.org/rfc/rfc8032

**Kết luận:** Lưu khóa EdEC an toàn không chỉ là chọn một file format. `PKCS12` + quyền file + quản lý mật khẩu là một hướng lưu trữ tiêu chuẩn cho ứng dụng Java; khi cần private key không xuất được, kiểm soát ký tập trung và audit mạnh, cân nhắc HSM/KMS thực sự hỗ trợ EdDSA. Dù dùng cơ chế nào, **quyền dùng khóa, danh tính của public key, rotation, backup và kế hoạch ứng phó lộ khóa** phải được thiết kế rõ ràng. Những nguyên tắc và API trong bài đều còn phù hợp với Java hiện đại.
