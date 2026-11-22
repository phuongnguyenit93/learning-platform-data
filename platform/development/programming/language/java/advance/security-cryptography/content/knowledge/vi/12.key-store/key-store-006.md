# 12.6. Đọc khóa cùng chuỗi chứng thư và kiểm tra alias hoặc mật khẩu sai

Java `KeyStore` là một **kho chứa các entry khóa và chứng thư** được truy cập qua `java.security.KeyStore`. Một tệp PKCS#12 (`.p12`/`.pfx`) có thể chứa **private key** và **certificate chain** của khóa đó, hoặc các entry khác. Để sử dụng đúng, ứng dụng phải phân biệt **mở kho bằng store password**, **chọn entry bằng alias**, **mở khóa entry bằng key password**, và **kiểm tra chain/chứng thư có phù hợp mục đích và đáng tin hay không**.

Trong bài **12.6** thuộc chủ đề **“12. KeyStore”**, chúng ta dùng Java 21 và `keytool` để tạo một PKCS#12 thử nghiệm, đọc private key cùng chuỗi gồm hai chứng thư, kiểm tra alias tồn tại/sai, mô phỏng hai loại mật khẩu sai và phân tích exception. Một chương trình Java chạy được giúp bạn nhìn thấy kết quả thực tế, sau đó bài học chỉ ra giới hạn của demo và các bước cần có trong sản phẩm.

## Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt `KeyStore`, **PKCS12/JKS**, `PrivateKeyEntry`, `SecretKeyEntry`, `TrustedCertificateEntry` và alias.
2. Sử dụng `KeyStore.getInstance("PKCS12")` và `load(InputStream, char[])` để mở kho; hiểu khác biệt giữa **store password** và **entry/key password**.
3. Dùng `containsAlias`, `isKeyEntry`, `isCertificateEntry`, `getKey`, `getCertificate`, `getCertificateChain` và `getEntry` đúng trường hợp.
4. Đọc và kiểm tra chuỗi chứng thư theo thứ tự **leaf → issuer → ...**, nhưng không nhầm **đọc được chain** với **chain đáng tin theo PKIX**.
5. Phân biệt tình huống **alias không tồn tại**, alias có sai loại entry, **store password sai**, **key password sai**, file lỗi/không đúng định dạng và provider thiếu thuật toán.
6. Biên dịch/chạy Java 21 trên fixture có chain hai phần tử; hiểu cách bảo vệ file, password, private key, log và cấu hình TLS/JSSE sau bước đọc.

## 1. Mô hình KeyStore và những thứ thực sự được lưu

`KeyStore` là một **API trừu tượng**: cách lưu trữ và hành vi cụ thể do `KeyStoreSpi` của provider quyết định. Trong ví dụ chúng ta chỉ rõ `PKCS12` để không phụ thuộc `KeyStore.getDefaultType()` hoặc cấu hình môi trường.

Một cấu trúc khái niệm:

```text
demo.p12 (PKCS12)
|
+-- alias: service-signing
|     type: PrivateKeyEntry
|     privateKey: RSA private key (bảo vệ bằng password theo provider)
|     chain[0]: chứng thư leaf CN=service.example.test
|     chain[1]: chứng thư issuer CN=Demo CA
|
+-- alias: demo-ca
      type: PrivateKeyEntry (lab CA có private key riêng)
      privateKey: khóa ký CA dùng để tạo leaf certificate
      chain[0]: chứng thư CA tự ký
```

*Lưu ý:* Hai alias ở đây đều là **PrivateKeyEntry** vì tạo bằng `keytool -genkeypair`. Một CA certificate được import riêng vào truststore (không kèm private key) mới thường là **TrustedCertificateEntry**. Trong hệ thống thật, **không** nên đặt private key CA vào cùng tệp ứng dụng cần triển khai trên server; nó chỉ nằm chung ở đây để bài lab tạo chuỗi chứng thư dễ kiểm tra.

| Khái niệm | Ý nghĩa | API nhận diện |
| --- | --- | --- |
| `alias` | Tên entry nội bộ, ví dụ `service-signing`; **không phải danh tính đã được xác thực** | `containsAlias(alias)`, `aliases()` |
| `PrivateKeyEntry` | Private key + **certificate chain** tương ứng, dùng cho ký hoặc xác thực TLS tùy mục đích | `isKeyEntry`, `getEntry`, `getKey`, `getCertificateChain` |
| `SecretKeyEntry` | Khóa đối xứng, ví dụ AES; không có X.509 chain theo nghĩa private-key entry | `isKeyEntry`, `getEntry` |
| `TrustedCertificateEntry` | Một chứng thư được lưu theo chính sách tin cậy (không chứa private key) | `isCertificateEntry`, `getCertificate` |
| `store password` | Dùng lúc `load` để mở và/hoặc kiểm tra tính toàn vẹn file | `load(input, storePassword)` |
| `key/entry password` | Dùng khi lấy protected key từ entry | `getKey(alias, keyPassword)`, `getEntry(alias, ProtectionParameter)` |
| Certificate chain | Chứng thư leaf và các chứng thư issuer để hỗ trợ xây dựng đường dẫn chứng thực | `getCertificateChain(alias)` |
| Trust anchor | CA/public key được tin **độc lập với dữ liệu do peer gửi** | `TrustAnchor`, PKIX validator/truststore policy |

Một `KeyStore` có thể làm **identity keystore** (có private key của server/client) hoặc **truststore** (chứa các certificate được tổ chức cho phép tin), nhưng hai vai trò này không nên gộp theo cách khó kiểm soát.

## 2. Quy trình đọc: bốn bước khác nhau

Giả sử bạn cần private key và chain dưới alias `service-signing`:

```text
[Path demo.p12]
    |
    v
KeyStore.getInstance("PKCS12")
    |
    v
load(InputStream, storePassword)    <-- sai password/file -> lỗi load
    |
    v
containsAlias("service-signing")    <-- false nếu alias không có
    |
    v
isKeyEntry(alias) / getEntry type   <-- sai loại entry -> không dùng làm private key
    |
    +--> getKey(alias, keyPassword)        <-- password mở khóa entry
    |
    +--> getCertificateChain(alias)        <-- leaf ở [0], tiếp issuer...
                  |
                  v
    Kiểm tra key phù hợp chứng thư, mục đích, PKIX trust/policy
```

Những thao tác này trả lời các câu hỏi **khác nhau**:

- **`load` thành công:** provider đã đọc/khởi tạo KeyStore và dùng tham số được cấp theo cơ chế hỗ trợ. Điều đó không chứng minh tất cả alias bạn muốn đều tồn tại, cũng không xác thực một chứng thư bên trong với CA tin cậy.
- **`containsAlias == true`:** có entry mang tên ấy; không nói nó là private key, chứng thư trusted hay secret key.
- **`getKey` thành công:** entry cung cấp khóa và password phù hợp. Khóa có thể là `PrivateKey` hoặc `SecretKey`; phải kiểm tra kiểu, algorithm và quyền sử dụng trước khi dùng.
- **`getCertificateChain` có giá trị:** tệp lưu một chuỗi chứng thư. Nó **không phải** lệnh kiểm tra tin cậy CA, hostname, thời hạn, EKU, key usage, revocation hoặc path constraints.
- **Private key và leaf public key phù hợp:** có thể kiểm tra bằng phép ký/xác minh thử với scheme phù hợp. Đây vẫn chưa phải kết luận chain thuộc một tổ chức đáng tin.

**Đừng coi alias là username.** Alias giúp tìm entry trong file; danh tính và quyền sử dụng phải dựa vào nguồn tin cậy và chính sách ứng dụng.

## 3. Khởi tạo fixture PKCS#12 có chain hai chứng thư

Bài lab dùng **JDK 21** hoặc JDK mới hơn có `keytool` hỗ trợ `-signer`. Bạn cần một thư mục trống để chứa `demo.p12` và file Java. Dưới đây dùng **RSA 3072 bit**, chữ ký `SHA256withRSA` và thời hạn chứng thư **30 ngày**. CA tự ký là **chứng thư thử nghiệm**, không được hệ điều hành/trình duyệt tự tin cậy.

### 3.1 Đặt password chỉ dùng cho lab

`keytool` hỗ trợ modifier `:env` để lấy password từ biến môi trường. Để tái lập bài học, hai lệnh dưới đặt **password giả**. Không dùng chuỗi này trong hệ thống thật; tránh đặt secret thật trong source, lịch sử shell hoặc log.

**Windows PowerShell:**

```powershell
$env:DEMO_KS_PASS = 'DemoOnly-ChangeMe42'
```

**Linux/macOS (Bash):**

```bash
export DEMO_KS_PASS='DemoOnly-ChangeMe42'
```

Trong production, lấy secrets từ secret manager/KMS, protected input hoặc cơ chế triển khai được kiểm soát. Biến môi trường vẫn có rủi ro bị lộ bởi cấu hình/process/debugging; `:env` chỉ tránh **trực tiếp đưa password vào tham số** `-storepass value` trên command line.

### 3.2 Tạo một CA tạm để ký chứng thư dịch vụ

Chạy từ thư mục demo:

```text
keytool -genkeypair -alias demo-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Demo CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -validity 30 -keystore demo.p12 -storetype PKCS12 -storepass:env DEMO_KS_PASS -keypass:env DEMO_KS_PASS -noprompt
```

Đây là cặp khóa CA thử nghiệm; `BC=ca:true` và `keyCertSign` diễn tả mục đích ký certificate. `keytool` tạo chứng thư CA tự ký, nên **chain của `demo-ca` chỉ có một phần tử**.

### 3.3 Tạo khóa dịch vụ và chứng thư được CA thử nghiệm ký

```text
keytool -genkeypair -alias service-signing -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=service.example.test,O=Training,C=VN" -ext "SAN=dns:service.example.test" -ext "KU:critical=digitalSignature" -signer demo-ca -signerkeypass:env DEMO_KS_PASS -validity 30 -keystore demo.p12 -storetype PKCS12 -storepass:env DEMO_KS_PASS -keypass:env DEMO_KS_PASS -noprompt
```

`-signer demo-ca` sử dụng private key tại alias CA để ký chứng thư cho `service-signing`. Vì vậy entry mới có **chuỗi hai chứng thư**: leaf rồi CA. Điều này giúp kiểm tra `getCertificateChain`, **không cấp trust** cho CA tự ký.

Trong ví dụ, store password và key password cùng dùng `DEMO_KS_PASS` vì nhiều implementation/tích hợp PKCS#12 yêu cầu hoặc ưu tiên cùng password. **Về API, store password và entry password vẫn là hai đầu vào khác nhau**, dù có thể cùng giá trị trong fixture. JKS và một số provider/store khác có quy ước khác; không mặc định mọi PKCS#12 trên mọi JDK hỗ trợ hai password độc lập.

### 3.4 Dùng `keytool` kiểm tra cấu trúc trước khi viết Java

```text
keytool -list -v -alias service-signing -keystore demo.p12 -storetype PKCS12 -storepass:env DEMO_KS_PASS
```

Các dòng quan trọng (khác biệt nhỏ về cách in tùy JDK):

```text
Alias name: service-signing
Entry type: PrivateKeyEntry
Certificate chain length: 2
Owner: CN=service.example.test, O=Training, C=VN
Issuer: CN=Demo CA, O=Training, C=VN
...
Owner: CN=Demo CA, O=Training, C=VN
Issuer: CN=Demo CA, O=Training, C=VN
```

Trên Java có thể chọn các key provider khác nhau, nhưng **alias, entry type và chain length** nói lên cấu trúc cần kiểm tra. `-list -v` chỉ mô tả metadata/chain và **không xuất private key**.

Nếu chạy lệnh `-genkeypair` lần hai trên cùng file/alias đã tồn tại, `keytool` sẽ từ chối trùng alias. Bài lab nên làm trên thư mục riêng, không thao tác với truststore/cacerts thực tế hoặc kho khóa sản xuất.

## 4. Java 21: đọc private key + certificate chain và kiểm tra lỗi

Tạo file đúng tên **`KeyStoreReadDemo.java`** trong cùng thư mục với `demo.p12`. Chương trình nhận **đường dẫn** và **alias** ở command line; đọc password lab từ `DEMO_KS_PASS`. Nó in các boolean và độ dài chain, **không in private key, password hay nội dung bản mã bí mật**.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.UnrecoverableKeyException;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Arrays;

public final class KeyStoreReadDemo {
    private static KeyStore open(Path file, char[] storePassword)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(file)) {
            store.load(input, storePassword);
        }
        return store;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java KeyStoreReadDemo <file.p12> <alias>");
        }
        String passwordFromEnvironment = System.getenv("DEMO_KS_PASS");
        if (passwordFromEnvironment == null
                || passwordFromEnvironment.isEmpty()) {
            throw new IllegalStateException("Missing DEMO_KS_PASS");
        }

        Path path = Path.of(args[0]);
        String alias = args[1];
        char[] password = passwordFromEnvironment.toCharArray();
        char[] incorrect = "intentionally-wrong".toCharArray();
        try {
            KeyStore store = open(path, password);

            System.out.println("keystore type: " + store.getType());
            System.out.println("alias present: " + store.containsAlias(alias));
            System.out.println("is key entry: " + store.isKeyEntry(alias));
            System.out.println("missing alias: " +
                    !store.containsAlias("not-present"));
            System.out.println("missing key is null: " +
                    (store.getKey("not-present", password) == null));
            System.out.println("missing chain is null: " +
                    (store.getCertificateChain("not-present") == null));

            if (!store.containsAlias(alias) || !store.isKeyEntry(alias)) {
                throw new IllegalStateException("Missing/private key alias");
            }
            Key key = store.getKey(alias, password);
            if (!(key instanceof java.security.PrivateKey privateKey)) {
                throw new IllegalStateException("Not a private key entry");
            }
            Certificate[] chain = store.getCertificateChain(alias);
            if (chain == null || chain.length < 2) {
                throw new IllegalStateException(
                        "Expected leaf and issuer certificates");
            }
            X509Certificate leaf = (X509Certificate) chain[0];
            X509Certificate issuer = (X509Certificate) chain[1];
            System.out.println("certificate chain length: " + chain.length);
            System.out.println("leaf first: " +
                    leaf.equals(store.getCertificate(alias)));
            System.out.println("issuer name linked: " +
                    leaf.getIssuerX500Principal().equals(
                            issuer.getSubjectX500Principal()));
            leaf.verify(issuer.getPublicKey()); // Signature link only.
            System.out.println("issuer signature verifies: true");

            byte[] message = "certificate-key match".getBytes(
                    StandardCharsets.UTF_8);
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(privateKey);
            signer.update(message);
            byte[] signature = signer.sign();
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(leaf.getPublicKey());
            verifier.update(message);
            System.out.println("private key matches leaf: " +
                    verifier.verify(signature));

            boolean wrongStoreRejected = false;
            try {
                open(path, incorrect);
            } catch (IOException expected) {
                wrongStoreRejected = true;
            }
            System.out.println("wrong store password rejected: " +
                    wrongStoreRejected);

            boolean wrongKeyRejected = false;
            try {
                store.getKey(alias, incorrect);
            } catch (UnrecoverableKeyException expected) {
                wrongKeyRejected = true;
            }
            System.out.println("wrong key password rejected: " +
                    wrongKeyRejected);
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(incorrect, '\0');
        }
    }
}
```

**Biên dịch và chạy:**

```text
javac -version
javac --release 21 -encoding UTF-8 KeyStoreReadDemo.java
java KeyStoreReadDemo demo.p12 service-signing
```

Khi file được tạo đúng bằng các lệnh ở trên, stdout từ chương trình Java:

```text
keystore type: PKCS12
alias present: true
is key entry: true
missing alias: true
missing key is null: true
missing chain is null: true
certificate chain length: 2
leaf first: true
issuer name linked: true
issuer signature verifies: true
private key matches leaf: true
wrong store password rejected: true
wrong key password rejected: true
```

Các chương trình đã được kiểm tra với compiler hỗ trợ `--release 21` và JDK provider tiêu chuẩn; chi tiết thông báo lỗi của `keytool`/JDK khác nhau theo nhà cung cấp/bản vá, nhưng **dòng stdout Java nêu trên phản ánh đúng fixture đã tạo và điều kiện chương trình**. Nếu bạn chọn alias khác, chain khác, password khác hay provider khác thì kết quả hoặc loại lỗi có thể khác; đừng “sửa” expected output bằng cách bỏ kiểm tra.

### 4.1 Phân tích điểm then chốt

- `KeyStore.getInstance("PKCS12")` chọn định dạng xác định. `load(InputStream, storePassword)` đọc bytes và dùng password theo chính sách provider; `try-with-resources` đóng luồng file kể cả khi load lỗi.
- `containsAlias(alias)` và `isKeyEntry(alias)` kiểm tra cấu trúc trước khi truy xuất. `getKey` trả về kiểu `java.security.Key` chung, nên `instanceof PrivateKey` mới giúp xác nhận có private key cho thao tác ký.
- `getCertificateChain(alias)` trả chuỗi hoặc `null`. Với `PrivateKeyEntry` fixture, chain dài 2, phần tử **0** là leaf, phần tử **1** là issuer. Với root tự ký hoặc một fixture khác, chain có thể chỉ dài 1; đó không phải lỗi Java API.
- `getCertificate(alias)` trả leaf certificate cho private-key entry. `leaf.equals(store.getCertificate(alias))` giúp xác nhận chúng tương ứng trong fixture.
- `leaf.getIssuerX500Principal() == issuer.getSubjectX500Principal()` trong code dùng `equals` để kiểm tra liên kết tên; sau đó `leaf.verify(issuer.getPublicKey())` kiểm chữ ký leaf bằng public key của issuer. **Không dòng nào trong hai bước tự tạo trust anchor!**
- Chương trình thử ký bytes mới bằng private key, rồi xác minh bằng **leaf public key**. Kết quả `true` xác nhận cặp khóa phù hợp cho `SHA256withRSA` trong fixture; để dùng production còn phải kiểm tra policy, key usages, validity, trust.
- Alias `not-present` không có: `containsAlias` trả `false`, `getKey` và `getCertificateChain` trả `null`. Đó là trường hợp tra cứu bình thường, **không mặc định ném exception**.
- Store password sai được thử bằng `open(path, incorrect)` → `IOException`; key password sai được thử **sau khi kho đã load thành công** bằng `getKey(alias, incorrect)` → `UnrecoverableKeyException`. Hai phép kiểm nằm ở **hai giai đoạn khác nhau**.

**Cần phân biệt:** chương trình chỉ thử mật khẩu không đúng trong một fixture tự tạo. Không xử lý "sai password" bằng cách thử vô hạn nhiều giá trị hoặc ghi toàn bộ password/stacktrace ra log API. Trong thực tế, việc kiểm tra password ở endpoint/CLI cần hạn chế retry, thông tin lỗi cho người dùng và quản lý tài nguyên phù hợp.

## 5. `KeyStore.getEntry`: cách đọc entry theo đúng loại

Ngoài `getKey` và `getCertificateChain`, có thể đọc qua `KeyStore.getEntry(alias, new KeyStore.PasswordProtection(keyPassword))` rồi kiểm tra loại entry.

Đoạn sau **minh họa**, được dùng **bên trong chương trình có biến `store` đã load**, `alias` và `keyPassword` phù hợp (không phải class độc lập):

```java
KeyStore.Entry entry = store.getEntry(
        alias, new KeyStore.PasswordProtection(keyPassword));

if (entry instanceof KeyStore.PrivateKeyEntry privateEntry) {
    java.security.PrivateKey key = privateEntry.getPrivateKey();
    java.security.cert.Certificate[] chain =
            privateEntry.getCertificateChain();
    // Áp policy trước khi dùng key; không log private key.
} else if (entry instanceof KeyStore.SecretKeyEntry) {
    throw new IllegalArgumentException("Alias contains a secret key");
} else if (entry instanceof KeyStore.TrustedCertificateEntry) {
    throw new IllegalArgumentException("Alias is certificate only");
} else if (entry == null) {
    throw new IllegalArgumentException("Alias not found");
}
```

`KeyStore.PrivateKeyEntry` biểu diễn khóa riêng + chain; `SecretKeyEntry` không có chain X.509 như private key; `TrustedCertificateEntry` có certificate nhưng không có private key. `KeyStore.PasswordProtection` chứa password phục vụ truy xuất entry, nên phải có vòng đời bí mật phù hợp (có thể gọi `destroy()` khi dùng xong).

**Ngoại lệ:** `getEntry` có thể ném `UnrecoverableEntryException` nếu tham số bảo vệ không đủ/không hợp lệ, bao gồm password không đúng. Khi dùng `getKey` trực tiếp, thường gặp `UnrecoverableKeyException`. Đây là hai cách gọi API với exception được khai báo khác nhau.

### 5.1 `isKeyEntry` chưa đủ để khẳng định “là private key”

`isKeyEntry(alias)` có thể đúng cho cả private-key entry và secret-key entry. Nếu ứng dụng cần chứng thư TLS cho server, cần **PrivateKeyEntry + chain + phù hợp keyUsage/purpose**; một `SecretKey` AES trong KeyStore không thể thay thế chỉ vì `isKeyEntry` trả `true`.

Ngược lại, `isCertificateEntry(alias)` đúng cho alias là **TrustedCertificateEntry**. Với alias leaf có private key, nó thường trả `false` dù `getCertificate(alias)` trả một leaf certificate. Đây là điểm hay bị nhầm khi kiểm tra keystore bằng các boolean.

## 6. Khi alias hoặc password sai, Java xử lý thế nào?

| Tình huống | API | Hành vi thường thấy/được tài liệu quy định | Cách xử lý |
| --- | --- | --- | --- |
| Alias không tồn tại | `containsAlias("missing")` | `false` | Báo cấu hình alias không hợp lệ; có thể liệt kê alias nội bộ một cách an toàn. |
| Alias không có key | `getKey(alias, keyPass)` | `null` nếu alias không tồn tại hoặc không đại diện key | Kiểm tra `containsAlias` và loại entry; không dereference `null`. |
| Alias không có chain | `getCertificateChain(alias)` | `null` nếu alias thiếu/không có chain | Kiểm tra đúng `PrivateKeyEntry` và yêu cầu nghiệp vụ về chain. |
| Alias là certificate-only | `isCertificateEntry(alias)` | Có thể `true`, `isKeyEntry` là `false` | Không dùng làm signing private key. |
| Store password sai | `load(input, storePass)` | Thường `IOException` với nguyên nhân liên quan password/integrity | Dừng load, phân biệt với file/format lỗi ở logging nội bộ; không giả định loại lỗi chi tiết luôn giống nhau. |
| Key password sai | `getKey(alias, keyPass)` | `UnrecoverableKeyException` | Không coi là alias thiếu; kiểm tra secret reference và chính sách provider. |
| Entry password sai | `getEntry(alias, protection)` | `UnrecoverableEntryException` / subclass phù hợp | Kiểm tra `PasswordProtection`, không bỏ qua lỗi và tiếp tục với key null. |
| File không tồn tại/không đọc được | `Files.newInputStream(path)` | `NoSuchFileException`/`AccessDeniedException` hoặc `IOException` khác | Kiểm tra path, permission, mount, working directory. |
| Store type/provider/algorithm không hỗ trợ | `KeyStore.getInstance`/`load`/`getKey` | `KeyStoreException` / `NoSuchAlgorithmException` hoặc lỗi liên quan | Kiểm tra JDK/provider, format, thuật toán bảo vệ. |
| Chứng thư không parse được | `load` | Có thể `CertificateException` | Kiểm tra dữ liệu, provider, bản mã hóa và trust configuration. |
| Chưa `load` nhưng dùng store | `getKey`/`aliases` | `KeyStoreException` | Gọi `load` đúng trước khi truy xuất. |
| Mật khẩu đúng nhưng chain không đáng tin | `getCertificateChain` | Vẫn có thể trả chuỗi | Phải làm path validation và identity checks riêng. |

### 6.1 Hai password có thể cùng một chuỗi nhưng không đồng nghĩa

Có hai điểm bảo vệ khác nhau:

```text
demo.p12
   +-- load(storePassword) -----------------> integrity/open
   +-- getKey("service-signing", keyPassword) -> recover private key
```

Trong bài lab, cả hai đều lấy từ `DEMO_KS_PASS`. Với nhiều tệp PKCS#12, việc đặt hai giá trị khác nhau **không** tương thích rộng; một số JDK/provider chuẩn hóa key password = store password. Với JKS hoặc HSM, quy tắc có thể khác. Do đó API nên **phân biệt hai trường cấu hình**, nhưng quy trình tạo kho phải phù hợp khả năng của định dạng/provider thực tế.

**Tránh mẹo nguy hiểm:** gọi `load(input, null)` chỉ để “đọc được file khi không biết password”. Theo hợp đồng `KeyStore`, khi không cung cấp password kiểm tra toàn vẹn, **integrity checking có thể không được thực hiện**; provider khác có thể có ràng buộc riêng. Đây không phải giải pháp xử lý password sai và không thay thế kiểm tra integrity.

### 6.2 Không tự đoán alias từ tên file hoặc `CN`

Alias `service-signing` không bắt buộc bằng `CN=service.example.test`. Alias do người tạo kho chọn; `CN`/SAN nằm trong certificate subject/extension; định danh server phải được xác thực từ certificate **theo policy TLS/ứng dụng**, không phải từ alias.

Một số provider có quy tắc chuẩn hóa alias (ví dụ lower-case) hoặc phân biệt hoa/thường khác nhau. **Không dựa vào giả định alias luôn case-sensitive hay case-insensitive.** Với kho thực tế, dùng `keytool -list -keystore ...` hoặc `store.aliases()` để kiểm tra những alias được provider trả về, rồi cấu hình tên chính xác.

Ví dụ code rà soát alias **dùng trong nội bộ công cụ vận hành** (không in thông tin đó cho client công khai):

```java
java.util.Enumeration<String> names = store.aliases();
while (names.hasMoreElements()) {
    String name = names.nextElement();
    System.out.println(name + ": key=" + store.isKeyEntry(name)
            + ", trustedCert=" + store.isCertificateEntry(name));
}
```

Không in `key.getEncoded()`, `password` hoặc toàn bộ chứng thư/private key nếu không có yêu cầu rõ ràng. Metadata và alias cũng có thể tiết lộ cấu trúc hệ thống, nên hạn chế log.

## 7. Đọc certificate chain không có nghĩa là xác minh trust

`getCertificateChain(alias)` trả các chứng thư đã lưu theo thứ tự **leaf first**; nguồn có thể là chính PKCS#12 hoặc bên gửi cung cấp. Một chuỗi tự ký/xây dựng sai vẫn có thể parse và được trả về.

Trong demo:

```text
service-signing:
  [0] CN=service.example.test    ← leaf; public key tương ứng private key
  [1] CN=Demo CA                 ← issuer certificate (tự ký thử nghiệm)
```

`leaf.verify(issuer.getPublicKey())` chỉ kiểm tra **chữ ký của leaf bằng public key issuer được cấp**, chưa xác nhận issuer được tin. `leaf.checkValidity()` (nếu gọi) kiểm tra thời hạn ở một thời điểm, nhưng cũng không kiểm hostname, key usage, revocation hoặc trust anchor.

### 7.1 Các bước kiểm tra thực sự đối với chain

Nếu bạn nhận một chain và cần biết nó có được **tổ chức của bạn chấp nhận** không, phải xác định mục đích và trust policy, ví dụ:

1. **Tin một trust anchor độc lập:** có truststore/CA root/pinned key do tổ chức cấu hình và bảo vệ, không lấy trust anchor từ chính chain chưa xác thực của peer.
2. **Xây dựng và xác minh PKIX path:** kiểm chữ ký từng certificate, giới hạn basic constraints/path length, tính hợp lệ theo thời gian, thuật toán/key strength, các constraints và chính sách phù hợp.
3. **Kiểm tra tên đích/identity:** ví dụ TLS HTTPS cần DNS SAN khớp hostname sau khi xác minh chain; việc `CN` “có vẻ đúng” không phải đủ trong các profile hiện đại.
4. **Kiểm tra mục đích sử dụng:** key usage, extended key usage khi applicable, policy ứng dụng và quyền signer/tenant.
5. **Thu hồi:** khi threat model/chính sách yêu cầu, cấu hình OCSP/CRL hoặc cơ chế revocation thích hợp; không mặc định mọi call `CertPathValidator` tự bật và hoàn tất revocation.
6. **Quản lý pin/truststore vòng đời:** expiration, rotation, removal, thay CA, kiểm soát quyền cập nhật và audit.

Java có `CertPathValidator`, `CertPathBuilder`, `PKIXParameters` và `TrustAnchor` cho các trường hợp phải tự xử lý PKIX. Tuy nhiên, với TLS, tốt hơn để **JSSE TrustManager/`SSLContext`** thực thi validation theo profile và hostname verification của client, tránh viết bộ xác minh certificate ad hoc.

**Không nhập CA của demo vào truststore production.** Đó là CA tự ký chỉ có ý nghĩa lab; việc chữ ký chain kiểm được hoàn toàn không xác nhận nó thuộc một tổ chức tin cậy thực tế.

### 7.2 Private key có khớp certificate leaf không?

Một keystore entry đúng cấu trúc nên có private key phù hợp với public key ở leaf. Chương trình dùng `SHA256withRSA` để ký message thử bằng private key rồi xác minh với leaf public key. Nếu `verify` trả `true`, cặp khóa phù hợp **theo thuật toán RSA signature đã chọn**.

Kiểm tra này không thay thế kiểm certificate chain, không xác minh thẩm quyền cấp certificate, và không phải loại key nào cũng dùng RSA/`SHA256withRSA`. Nếu thực tế là EC hoặc Ed25519, phải chọn scheme tương ứng và policy hợp lệ; đừng dùng `Signature.getInstance("SHA256withRSA")` trên mọi private key vì code lab đang giả định RSA.

## 8. PKCS#12 và KeyStore khi cấu hình TLS/JSSE

Khi một Java server cần trình ra chứng thư TLS kèm private key, cấu hình thường dùng:

```text
PKCS12 (private key + certificate chain)
    |
    v
KeyManagerFactory (dùng key password nếu provider yêu cầu)
    |
    v
SSLContext / SSLEngine / SSLSocket (server certificate + private-key proof)
                       |
                 client verifies:
        truststore + PKIX + hostname/service identity
```

Một truststore riêng của client chứa **CA/public key đáng tin** cho xác minh server; `TrustManagerFactory` giúp tạo trust manager. Việc server tải thành công `demo.p12` hoặc lấy `PrivateKey` **không chứng minh TLS handshake thành công** hay client đã tin certificate của server.

Trong TLS, server certificate còn cần **extendedKeyUsage/keyUsage** phù hợp, tên SAN đúng và chuỗi issuer hợp lệ đến trust anchor; cần kiểm protocol version/cipher suites, quản lý khóa, expiration/rotation và error handling. Fixture bài lab dùng `KU=digitalSignature` và SAN dịch vụ để minh họa, nhưng CA tự ký không được tin cậy ngoài lab, nên **không dùng nó làm chứng thư TLS thực tế**.

Nếu có nhiều alias chứa private key, `KeyManager` có thể lựa chọn alias theo thuật toán/certificate request. Cấu hình đúng alias và certificate chain giúp tránh chọn nhầm khóa, nhưng việc lựa chọn cuối cùng do JSSE/provider và chính sách ứng dụng quyết định.

## 9. Quy tắc bảo vệ KeyStore, certificate chain và password

- **Bảo vệ file và backup:** PKCS#12 có thể có password-based encryption/integrity nhưng vẫn chứa key material nhạy cảm; giới hạn OS permissions, ownership, backup access, đường dẫn mount/container và quyền đọc từ service account.
- **Không hardcode secrets production:** dùng KMS/HSM/secret manager hoặc protected input. Tránh password trong source, Git, tham số dòng lệnh, CI output, exception message và logs. Env var tiện cho demo/automation nhưng vẫn có thể bị lộ.
- **Dùng `char[]` khi API hỗ trợ:** sau khi dùng, gọi `Arrays.fill(password, '\0')`. Điều này không bảo đảm xóa mọi bản sao trong JVM/provider; nếu lấy bằng `System.getenv` sẽ tồn tại `String` bất biến không thể dọn hoàn toàn.
- **Không in private key:** `PrivateKey.getEncoded()` (nếu provider cho phép) có thể chứa khóa riêng thực sự. Chỉ log alias/loại key/metadata cần thiết, giới hạn quyền đọc.
- **Đừng tự động thử password liên tiếp:** password sai phải dừng và phân loại rõ; lỗi alias không tồn tại khác với lỗi password, nhưng phản hồi public có thể cần thống nhất để tránh information leak.
- **Tránh password null để bỏ xác minh:** bảo vệ integrity và availability; xử lý exceptions theo chính sách, kiểm tra checksum/signatures khi phù hợp, không tự “recover” bằng cách vô hiệu validation.
- **Luân chuyển khóa:** thay entry alias, private key và certificate chain theo quy trình có rollback, kiểm tra trust chain client trước cutover; không deploy một chain mới thiếu issuer và chờ client tự tải được.
- **Không giả định chain luôn dài 2 hoặc chứa root:** nhiều hệ thống lưu leaf + intermediates, có thể không lưu root; `getCertificateChain` có thể có độ dài 1, nhiều hơn 2 hoặc null. Điều kiện `length >= 2` của demo là **yêu cầu fixture**, không phải kiểm tra PKIX tổng quát.

## 10. Các lỗi thường gặp qua ví dụ

| Hiện tượng | Gốc vấn đề | Bước xử lý hợp lý |
| --- | --- | --- |
| `containsAlias("service-signing") == false` | Sai alias, store khác, alias bị đổi sau import/convert | Liệt kê alias nội bộ; kiểm đúng file/type và cấu hình. |
| `getKey(...) == null` | Alias không tồn tại hoặc không đại diện khóa | Phân biệt với password sai; kiểm `containsAlias`, `isKeyEntry`. |
| `getCertificateChain(...) == null` | Alias không có chain / không phải private-key entry | Kiểm entry type, import chain đầy đủ, policy. |
| `getKey` ném `UnrecoverableKeyException` | Password entry sai hoặc provider không recover được | Kiểm nguồn secret/config; không thử ngẫu nhiên password. |
| `load` ném `IOException` | Store password sai, file lỗi/truncated hoặc format không phù hợp | Kiểm format, path, quyền, password qua kênh bảo mật; xem cause nội bộ. |
| `getEntry` ném `UnrecoverableEntryException` | PasswordProtection sai/không phù hợp | Xem entry type và provider contract. |
| `InvalidKeyException` khi ký | Private key không phù hợp scheme `Signature` | Kiểm `key.getAlgorithm()`, provider, key usage, scheme. |
| Chain len = 1 trong bài | Tạo leaf tự ký thay vì `-signer demo-ca`, hoặc dùng alias CA | Kiểm lệnh tạo fixture và kết quả `keytool -list -v`. |
| Leaf có issuer name nhưng verify fail | Certificate bị thay, sai issuer public key, signature lỗi | Không dùng chain; xây path và kiểm bằng PKIX/trust policy. |
| Leaf verify được nhưng client TLS vẫn không tin | CA chưa là trust anchor, SAN/EKU/validity/policy không đúng | Dùng TLS TrustManager/truststore đúng; không vô hiệu hostname/cert checks. |
| Local chạy đúng, container báo alias/password lỗi | Container mount nhầm file, secret/config khác, dùng JDK/provider khác | Kiểm hash file/cấu hình triển khai một cách an toàn, tránh log secret. |
| Khóa riêng đọc được nhưng chứng thư đã hết hạn | Keystore storage không tự thực thi PKIX policy | Theo dõi expiration, luân chuyển chứng thư và kiểm chứng ở tầng TLS/ứng dụng. |

## 11. Bài tự thực hành

1. **Alias và type:** sau khi tạo `demo.p12`, chạy `keytool -list -v` cho `demo-ca` và `service-signing`. Vì sao cả hai đều là `PrivateKeyEntry` nhưng chain length khác nhau?
2. **Wrong alias:** thay đối số Java thành `unknown-key`. Với code demo hiện tại, những dòng nào chuyển thành `false`, và vì sao chương trình dừng tại guard thay vì thực hiện `getKey` theo alias sai?
3. **Sai store password:** tạo biến môi trường có password khác trước khi chạy Java; dự đoán exception phát sinh tại `load`. Khôi phục password lab đúng sau khi quan sát, tuyệt đối không thay mật khẩu production để thử.
4. **Sai key password:** giữ store password đúng, đưa password sai vào riêng `getKey(alias, wrongPassword)`. Vì sao `containsAlias` vẫn `true` dù không recover được khóa?
5. **Đọc chain:** in **subject/issuer names** của `chain[0]`/`chain[1]` (chỉ trên dữ liệu lab), xác định đâu là leaf và CA; giải thích vì sao `leaf.verify(issuer.getPublicKey())` chưa đủ để tin CA.
6. **Entry types:** thiết kế một truststore có certificate-only entry và thử `isCertificateEntry`, `getCertificate`, `getCertificateChain`, `getKey`; nhận xét kết quả từng API.
7. **Trust:** nếu kẻ tấn công tự tạo CA và ký chứng thư leaf giả nhưng tên giống thật, bước nào trong validation sẽ ngăn client tin chain đó?
8. **Lỗi đóng gói:** đổi tên file, đổi đường dẫn, cấp thiếu quyền đọc; so sánh với lỗi alias sai và password sai để tìm vị trí lỗi trong pipeline.
9. **Chuỗi trung gian:** nếu có root CA → intermediate CA → leaf, `getCertificateChain` nên xếp thứ tự nào? Có nhất thiết phải lưu root certificate trong entry không? Vì sao không?
10. **Thiết kế dịch vụ:** phác thảo cấu hình server TLS với identity PKCS12 và client truststore, quy trình rotate alias/cert và hành vi khi cert hết hạn.

**Tiêu chí hoàn thành:** bạn có thể chỉ ra rõ **file nào đang được mở, store type nào, alias nào, entry type nào, password nào dùng ở giai đoạn nào, khóa có khớp leaf hay không, chain được lưu theo thứ tự nào và cần tin cậy chain bằng cơ chế nào**. Không nhầm “đã đọc được private key + chain” với “đã xác thực chứng thư” hoặc “hệ thống TLS đã an toàn”.

## Tài liệu tham khảo

- [Java SE 21 — `java.security.KeyStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): `load`, `getKey`, `getEntry`, `getCertificateChain`, `containsAlias`, exception và contract của các entry.
- [Java SE 21 — `KeyStore.PrivateKeyEntry`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.PrivateKeyEntry.html): private key, chain, thứ tự và điều kiện entry.
- [Java SE 21 — `java.security.cert.X509Certificate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html): subject, issuer, verify, validity và extensions.
- [JDK 21 — `keytool` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): `-genkeypair`, `-signer`, `-list`, `-storetype`, `-storepass:env`.
- [Java SE 21 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html): xác minh certificate path qua PKIX (cần trust/policy cấu hình).
- [Java SE 21 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors và ràng buộc xác minh.
- [Java 21 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): KeyManager/TrustManager, truststore, SSLContext và TLS certificate validation.
