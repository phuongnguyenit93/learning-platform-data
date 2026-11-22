# 12.4 Tạo kho mới, `load`, `store` và kiểm tra đúng kiểu entry

## Mục tiêu bài học

`java.security.KeyStore` là API chuẩn của Java Security Architecture (JCA) dùng để quản lý **khóa mật mã và chứng chỉ** theo các `alias`. Một kho có thể chứa khóa đối xứng (`SecretKey`), khóa riêng kèm chuỗi chứng chỉ (`PrivateKey` + certificate chain), hoặc chứng chỉ công khai được tin cậy (`TrustedCertificateEntry`). Nhưng **ba loại entry không được dùng lẫn**: cùng xuất hiện trong KeyStore không đồng nghĩa cùng phương thức lấy, cùng ý nghĩa tin cậy hay cùng cách bảo vệ.

Sau bài này, bạn sẽ thực hiện được toàn bộ vòng đời cơ bản:

1. Chọn type và tạo đối tượng `KeyStore`.
2. Khởi tạo **kho trống** bằng `load(null, password)`; phân biệt với **đọc kho tồn tại** bằng `load(inputStream, password)`.
3. Ghi `KeyStore.Entry` đúng loại bằng `setEntry` / `setCertificateEntry`; phân biệt **store password** và **entry password/protection**.
4. Dùng `store(outputStream, password)` để **serialize/lưu** rồi dùng một đối tượng mới `load` lại.
5. Kiểm tra đúng loại entry trước khi đọc/cast, tránh nhầm `isKeyEntry()` với `SecretKeyEntry` hoặc `PrivateKeyEntry`.
6. Nhận biết lỗi sai mật khẩu, sai type, chưa load, alias không tồn tại và rủi ro ghi đè file thật.
7. Chạy một chương trình **Java 17+** tự tạo kho PKCS12 ở RAM, thêm AES SecretKey, lưu/đọc lại, kiểm tra các kiểu entry và xác minh key không thay đổi.

> **Phạm vi:** Bài tập thao tác KeyStore, không phải hướng dẫn dựng PKI sản xuất. File `.p12` được bảo vệ bằng mật khẩu **không tự thay thế** quyền truy cập file, KMS/HSM, quản lý danh tính, thu hồi chứng chỉ hoặc chính sách sử dụng khóa.

## 1. KeyStore là gì và không phải là gì?

Một KeyStore là kho logic gồm các entry được định danh bằng **alias**. API `KeyStore` tách việc dùng khóa khỏi định dạng lưu trữ cụ thể và triển khai `Provider` của JCA:

```text
Ứng dụng Java
     |
     | KeyStore.getInstance("PKCS12")
     v
JCA KeyStore API ----> Provider hỗ trợ type PKCS12
     |
     +-- alias "api-aes"       -> SecretKeyEntry
     +-- alias "server-tls"    -> PrivateKeyEntry + cert chain
     +-- alias "partner-root"  -> TrustedCertificateEntry
     |
     +-- load(...) / store(...) <--> byte của kho / file / stream
```

**KeyStore không phải map `String → Object` thông thường**: entry có kiểu mật mã, yêu cầu bảo vệ, phương thức tạo/khôi phục và ràng buộc từ provider. Mặc dù API expose các lớp `Entry`, không phải mọi implementation/type của KeyStore hỗ trợ tất cả loại entry hoặc cách bảo vệ giống nhau.

**Phân biệt ba tầng:**

- **`KeyStore` object:** trạng thái ở bộ nhớ sau khi load; gọi `setEntry` chỉ sửa trạng thái này.
- **Keystore bytes:** kết quả `store`, có thể lưu vào file hoặc gửi tới nơi lưu trữ bảo vệ; `load` xây dựng lại trạng thái từ bytes.
- **Key/certificate cryptographic object:** `SecretKey`, `PrivateKey`, `Certificate`; đây là các tài nguyên có yêu cầu bảo mật và ngữ nghĩa riêng.

`getInstance(...)` **không** tương đương `load(...)`; `setEntry(...)` **không** tự cập nhật file; `getKey(...)` không nói rõ đó là secret hay private key nếu không kiểm tra trước.

## 2. Chọn loại kho: `PKCS12` và những khác biệt triển khai

Trong Java SE 17, **`PKCS12`** là keystore type chuẩn mà các implementation Java SE phải hỗ trợ. `KeyStore.getDefaultType()` lấy giá trị mặc định trong cấu hình bảo mật runtime (`keystore.type`); nhiều JDK hiện đại dùng `pkcs12` làm default, nhưng nếu lưu dữ liệu cần tương thích dài hạn, nên chọn **`"PKCS12"` tường minh**.

| Type | Tính chất | Dùng khi nào? |
| --- | --- | --- |
| `PKCS12` | Chuẩn container phổ biến cho key/certificate; được Java SE yêu cầu hỗ trợ | Lựa chọn thực hành cho key/certificate portable, nhưng vẫn phải kiểm tra tính tương thích của từng entry type/provider. |
| `JKS` | Java KeyStore truyền thống | Thường gặp trong hệ thống legacy; không mặc định dùng cho secret keys và không tự coi là tốt hơn PKCS12. |
| `JCEKS` | Legacy Java Cryptography Extension keystore | Có thể gặp ở hệ thống cũ; không ưu tiên để thiết kế mới chỉ vì trước đây lưu được secret key. |
| Provider-specific / token | Có thể đại diện thiết bị HSM, kho hệ điều hành hoặc dịch vụ | Dùng theo chính sách; không giả định `store(OutputStream)` hoặc `getEncoded()` hoạt động như file PKCS12. |

**Không dùng đuôi file làm bằng chứng type tuyệt đối**: `.p12`, `.pfx`, `.jks` là quy ước; dữ liệu bên trong và provider xử lý mới quyết định. Khi tạo hoặc đọc theo định dạng đã biết, gọi `KeyStore.getInstance("PKCS12")`. Một số overload của JDK có thể probe type từ file, nhưng đó là hành vi API khác với cách bài thực hành chọn type tường minh.

Một điểm quan trọng: **hỗ trợ type `PKCS12` không có nghĩa mọi provider đều hỗ trợ mọi tổ hợp entry type, cipher, password hoặc thuộc tính file**. Demo bên dưới dựa trên JDK 17+ thông dụng có hỗ trợ `SecretKeyEntry` trong PKCS12; khi triển khai cross-provider phải kiểm tra thực tế.

## 3. Ba loại `KeyStore.Entry` bắt buộc phải phân biệt

### 3.1 `SecretKeyEntry` — khóa bí mật đối xứng

Đây là một `SecretKey` như khóa AES hoặc HMAC. Nó có thể dùng cho `Cipher`, `Mac` theo thuật toán của key, **không có public-key certificate chain**.

```java
// Minh họa trong phương thức có xử lý checked exceptions:
KeyStore.SecretKeyEntry item = new KeyStore.SecretKeyEntry(aesKey);
keyStore.setEntry("api-aes", item,
        new KeyStore.PasswordProtection(entryPassword));
```

- `aesKey` là **bí mật**, không log hay chép vào certificate.
- `entryPassword` bảo vệ việc lưu/khôi phục entry theo khả năng type/provider.
- Dùng `getEntry(...)` và kiểm tra `instanceof KeyStore.SecretKeyEntry` hoặc `entryInstanceOf(...)` trước cast.
- Với `SecretKeyEntry`, `getCertificateChain(alias)` thường `null`, vì không có chứng chỉ kèm theo.

### 3.2 `PrivateKeyEntry` — khóa riêng và certificate chain

Là **`PrivateKey` + chuỗi `Certificate[]`** tương ứng. Ví dụ: khóa riêng RSA/ECDSA để ký hoặc xác thực TLS và chứng chỉ công khai của chủ sở hữu.

```java
// Minh họa khi privateKey và certificateChain đã có, được kiểm tra:
KeyStore.PrivateKeyEntry item =
        new KeyStore.PrivateKeyEntry(privateKey, certificateChain);
keyStore.setEntry("server-tls", item,
        new KeyStore.PasswordProtection(entryPassword));
```

**`PrivateKeyEntry` khác `SecretKeyEntry`:** private key thuộc hệ mật khóa công khai, phải có certificate chain theo hợp đồng của KeyStore; `PrivateKeyEntry.getCertificateChain()` dùng để lấy chuỗi đó. **Không tự tạo `PrivateKeyEntry` với chain rỗng/null** chỉ để lưu private key; ví dụ tự cấp chứng chỉ bằng API nội bộ `sun.security.x509` không phù hợp cho hướng dẫn portable Java SE.

Certificate chain đi kèm giúp bên ngoài kiểm tra public key/danh tính theo hệ thống tin cậy, nhưng **sự hiện diện của certificate chain trong KeyStore không có nghĩa chuỗi đã được xác thực/trusted**. Việc validate PKIX, hostname, validity/revocation và key usage là trách nhiệm của TLS/PKI hoặc ứng dụng.

### 3.3 `TrustedCertificateEntry` — một chứng chỉ tin cậy, **không có khóa riêng**

Là một `java.security.cert.Certificate` (thường `X509Certificate`) được kho xem là **trust anchor hoặc chứng chỉ được tin cậy theo chính sách**. Không thể ký hoặc giải mã bằng nó vì **nó không chứa private key**.

```java
// Minh họa với Certificate đã được xác minh qua kênh đáng tin:
keyStore.setCertificateEntry("partner-root", trustedCertificate);
// Tương đương về loại entry:
// keyStore.setEntry("partner-root",
//         new KeyStore.TrustedCertificateEntry(trustedCertificate), null);
```

**Cảnh báo:** chỉ chạy `setCertificateEntry` không làm một chứng chỉ bên ngoài **trở nên đáng tin về mặt nghiệp vụ**; thao tác này đang *cấp quyền tin cậy* theo chính sách của kho/ứng dụng. Phải kiểm tra nguồn, fingerprint, thuộc tính/chủ thể, mục đích và quy trình phê duyệt trước khi import certificate thật.

### 3.4 Bảng chọn API đúng loại

| Câu hỏi / API | `SecretKeyEntry` | `PrivateKeyEntry` | `TrustedCertificateEntry` |
| --- | --- | --- | --- |
| Chứa | `SecretKey` | `PrivateKey` + certificate chain | Một `Certificate` |
| `isKeyEntry(alias)` | `true` | `true` | `false` |
| `isCertificateEntry(alias)` | `false` | `false` | `true` |
| `entryInstanceOf(alias, SecretKeyEntry.class)` | `true` | `false` | `false` |
| `entryInstanceOf(alias, PrivateKeyEntry.class)` | `false` | `true` | `false` |
| `entryInstanceOf(alias, TrustedCertificateEntry.class)` | `false` | `false` | `true` |
| `getKey(alias, password)` | Trả `SecretKey` | Trả `PrivateKey` | `null` |
| `getCertificate(alias)` | Thường `null` | Trả **leaf certificate** đầu chuỗi | Trả chứng chỉ tin cậy |
| `getCertificateChain(alias)` | `null` | Trả certificate chain | `null` |
| Thao tác ứng dụng | AES/HMAC theo key | Ký, giải mã, TLS identity theo key | Xác minh/đánh giá trust theo PKI policy |

**Bẫy phổ biến:** `isKeyEntry(alias) == true` **không xác định** đó là `SecretKeyEntry` hay `PrivateKeyEntry`. `getCertificate(alias) != null` cũng **không chứng minh đó là `TrustedCertificateEntry`**, vì với `PrivateKeyEntry` phương thức này trả leaf certificate. Khi cần **đúng kiểu entry**, sử dụng `entryInstanceOf(...)` hoặc kiểm tra kiểu trên `getEntry(...)`, không suy đoán từ tên alias hoặc `getCertificate`.

## 4. Chu trình tạo kho mới, đọc kho cũ và lưu kho

### 4.1 `getInstance` chỉ chọn một implementation

```java
// Đoạn minh họa:
KeyStore ks = KeyStore.getInstance("PKCS12");
```

`ks` lúc này chưa có nội dung được khởi tạo theo `load`; nhiều thao tác như `size()`, `getKey`, `setEntry` khi chưa load có thể ném `KeyStoreException` (*uninitialized keystore*).

**Không dùng `getInstance("PKCS12")` xong là `setEntry(...)` ngay**.

### 4.2 Tạo **mới**: `load(null, password)`

```java
KeyStore fresh = KeyStore.getInstance("PKCS12");
fresh.load(null, storePassword);  // khởi tạo kho trống
```

`load(null, password)` nói với provider khởi tạo **một keystore rỗng**, không phải "hãy đọc file trống". Có thể dùng password được yêu cầu ở thời điểm khởi tạo, sau đó dùng `store` để serialize theo format. **File đích chưa được tạo bởi `load(null, ...)`.**

Phải phân biệt `load(null, password)` với `load((InputStream) null, password)` ở các overload khác hoặc `load(LoadStoreParameter)`: khi cần thể hiện rõ ý nghĩa, dùng overload `load(InputStream, char[])` như ví dụ trên. Nếu gọi `load(null,...)` lần nữa trên cùng object đã có entries, việc load lại sẽ **reinitialize** và làm mất các thay đổi chưa lưu trong object đó.

### 4.3 Đọc **tồn tại**: `load(inputStream, password)`

```java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    KeyStore restored = KeyStore.getInstance("PKCS12");
    restored.load(in, storePassword);
    // Đọc alias/entry ở đây.
}
```

Khác biệt:

- `inputStream != null`: **parse keystore bytes**, kiểm tra password/integrity theo cơ chế type/provider và tạo entries.
- `inputStream == null`: tạo kho mới rỗng theo API contract (không phát hiện file cũ).
- Mật khẩu store bị sai hoặc dữ liệu lỗi có thể gây `IOException`, với cause như `UnrecoverableKeyException` trong một số trường hợp.
- `load(in, null)` trên một số keystore không thực hiện kiểm tra tính toàn vẹn của store, theo Java API; **không dùng nó như cách bỏ qua lỗi mật khẩu** cho dữ liệu cần tin cậy.
- Sau khi `load(...)` thành công, mới dùng `containsAlias`, `size`, `getEntry`, `entryInstanceOf`.

### 4.4 Ghi entry vào object chưa đủ: phải `store(...)`

```java
ks.setEntry(alias, entry, protection);

try (java.io.OutputStream out =
        java.nio.file.Files.newOutputStream(path)) {
    ks.store(out, storePassword);
}
```

`setEntry` **sửa KeyStore trong RAM**. `store` mới viết bytes xuống output. Nếu chương trình dừng sau `setEntry` mà không `store`, file cũ không có thay đổi. Ngược lại, `store` **không tự thay đổi khóa** thành một cặp khóa khác; nó serialize trạng thái hiện có theo type và provider.

`store(out, password)` bảo vệ tính toàn vẹn của kho theo khả năng/type, nhưng **không phải cam kết file an toàn trước mọi tấn công**. Các cấu hình PKCS12 thường dùng bảo vệ dựa trên mật khẩu; cần đủ entropy cho password, giới hạn quyền truy cập file và quản lý khóa riêng.

**Không viết trực tiếp đè file keystore đang hoạt động nếu cần khôi phục an toàn.** `Files.newOutputStream(path)` theo cách trên có thể truncate/overwrite file. Trong production, tạo file tạm **cùng filesystem** với quyền truy cập hạn chế, `store` vào file tạm, flush/fsync nếu cần tính bền vững, sau đó rename/move atomically nếu hệ thống hỗ trợ, và lưu bản backup/version hợp lệ. `ATOMIC_MOVE` không được mọi filesystem hỗ trợ; phải xử lý `AtomicMoveNotSupportedException` theo chính sách, không tự động ghi đè bừa. Khi có nhiều writer, thêm lock/transaction hoặc external key-management service; `KeyStore` object không phải một database có concurrency control.

## 5. Hai loại mật khẩu/protection khác nhau

| Thành phần | Dùng ở đâu? | Ý nghĩa |
| --- | --- | --- |
| **Store password** | `load(in, storePassword)` / `store(out, storePassword)` | Dùng để kiểm tra/bảo vệ kho theo implementation, bao gồm integrity protection. |
| **Entry password/protection** | `setEntry(alias, entry, new PasswordProtection(...))`, `getEntry(alias, ...)` | Dùng bảo vệ/khôi phục một key entry cụ thể, nếu type/provider hỗ trợ. |
| **Trusted certificate entry** | `setCertificateEntry(...)` hoặc `getEntry(alias, null)` | Không có secret/private key để "mở"; việc tin cậy certificate là chính sách, không phải một mật khẩu cho private key. |

Ví dụ nhỏ:

```java
KeyStore.ProtectionParameter protection =
        new KeyStore.PasswordProtection(entryPassword);
ks.setEntry("api-aes",
        new KeyStore.SecretKeyEntry(aesKey),
        protection);

KeyStore.Entry loaded = ks.getEntry("api-aes",
        new KeyStore.PasswordProtection(entryPassword));
```

**Trong nhiều triển khai PKCS12**, cách dùng một password chung cho store và key entries là cấu hình tương thích thực tế, và một số tool/implementation có ràng buộc về password khác nhau. Demo dùng cùng password để chắc chắn tương tác trên JDK phổ biến; **không kết luận Java API cấm mọi entry password riêng**.

Nên giữ mật khẩu trong `char[]` thay vì `String` bất biến khi có thể và xóa mảng bằng `Arrays.fill` sau khi không cần nữa. Tuy vậy đây **không bảo đảm xóa mọi bản sao bí mật** bên trong JDK, provider hoặc heap; không hard-code password production, không đưa password vào command-line có thể bị lộ qua process list/shell history. Ưu tiên secret manager/HSM/KMS và quyền truy cập phù hợp.

**Sai mật khẩu ở hai điểm cho hành vi khác nhau:**

- Mật khẩu `load()` sai: thường không đọc được keystore, xuất hiện `IOException` / vấn đề integrity hoặc định dạng.
- Mật khẩu của `getEntry()` sai: có thể `UnrecoverableEntryException` / `UnrecoverableKeyException`; dùng store password thành công **không bảo đảm** luôn giải mã được mọi private/secret entry nếu entry dùng protection riêng.

Cần xử lý lỗi rõ ràng; không trả về `null` tự tạo như thể không có alias khi thực chất đã sai password.

## 6. Java 17 chạy độc lập: tạo kho, store/load lại, nhận diện đúng entry

Chương trình sau không cần certificate tự ký hay thư viện nội bộ `sun.*`. Nó dùng `KeyGenerator` để tạo AES-128 secret key, đưa vào `PKCS12 SecretKeyEntry`, **store keystore vào `ByteArrayOutputStream` ở RAM**, rồi khởi tạo một KeyStore mới và `load` byte array đó. Với `store(...)` thành công, thao tác này kiểm tra **cùng encoding/persistence path** mà file I/O sẽ dùng, nhưng không tạo hoặc sửa file trên máy.

Tạo file **`KeyStoreLifecycleDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyStoreLifecycleDemo {
    public static void main(String[] args) throws Exception {
        char[] password = "demo-password-123".toCharArray(); // demo only
        String alias = "api-aes";

        KeyStore store = KeyStore.getInstance("PKCS12");
        store.load(null, password); // create a NEW empty keystore
        System.out.println("Type: " + store.getType());
        System.out.println("Empty at start: " + (store.size() == 0));

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey original = generator.generateKey();
        store.setEntry(alias, new KeyStore.SecretKeyEntry(original),
                new KeyStore.PasswordProtection(password));

        System.out.println("Is key entry: " + store.isKeyEntry(alias));
        System.out.println("Is certificate entry: " +
                store.isCertificateEntry(alias));

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        store.store(output, password);
        byte[] encodedStore = output.toByteArray(); // persist in memory only

        KeyStore restored = KeyStore.getInstance("PKCS12");
        restored.load(new ByteArrayInputStream(encodedStore), password);
        System.out.println("Restored entries: " + restored.size());
        System.out.println("Secret-key kind: " + restored.entryInstanceOf(
                alias, KeyStore.SecretKeyEntry.class));
        System.out.println("Private-key kind: " + restored.entryInstanceOf(
                alias, KeyStore.PrivateKeyEntry.class));
        System.out.println("Trusted-cert kind: " + restored.entryInstanceOf(
                alias, KeyStore.TrustedCertificateEntry.class));

        if (!restored.entryInstanceOf(alias, KeyStore.SecretKeyEntry.class)) {
            throw new IllegalStateException("Wrong entry type");
        }
        KeyStore.Entry entry = restored.getEntry(
                alias, new KeyStore.PasswordProtection(password));
        SecretKey recovered = ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        System.out.println("Recovered key matches: " +
                MessageDigest.isEqual(
                        original.getEncoded(), recovered.getEncoded()));
        System.out.println("Missing entry is null: " +
                (restored.getEntry("missing",
                        new KeyStore.PasswordProtection(password)) == null));

        boolean wrongPasswordRejected = false;
        try {
            KeyStore invalid = KeyStore.getInstance("PKCS12");
            invalid.load(new ByteArrayInputStream(encodedStore),
                    "wrong-password".toCharArray());
        } catch (IOException expected) {
            wrongPasswordRejected = true;
        }
        System.out.println("Wrong store password rejected: " +
                wrongPasswordRejected);
        Arrays.fill(password, '\0');
    }
}
```

Chạy trên JDK 17+ hỗ trợ AES và PKCS12 SecretKeyEntry:

```bash
javac --release 17 KeyStoreLifecycleDemo.java
java KeyStoreLifecycleDemo
```

Stdout của chương trình trên JDK hỗ trợ tính năng như môi trường thử nghiệm:

```text
Type: PKCS12
Empty at start: true
Is key entry: true
Is certificate entry: false
Restored entries: 1
Secret-key kind: true
Private-key kind: false
Trusted-cert kind: false
Recovered key matches: true
Missing entry is null: true
Wrong store password rejected: true
```

### 6.1 Giải thích từng phần và tại sao output đáng tin

- **`getInstance("PKCS12")` + `load(null, password)`:** tạo kho mới rỗng, nên `size() == 0`. Nếu quên `load`, các thao tác đọc/ghi entries sẽ báo chưa khởi tạo.
- **`KeyGenerator.getInstance("AES")` + `init(128)`:** tạo một secret key 16 byte ngẫu nhiên. Chúng ta **không in key bytes**; test chỉ so sánh nội bộ.
- **`setEntry("api-aes", new SecretKeyEntry(...), PasswordProtection)`:** thêm key entry. `isKeyEntry == true` vì đây là key; `isCertificateEntry == false` vì không phải certificate-only trust entry.
- **`store(output, password)`:** serialize toàn bộ kho vào byte array ở bộ nhớ. **Không tự ghi một file** và không làm khóa mới xuất hiện nếu không gọi `setEntry`.
- **`restored.load(new ByteArrayInputStream(encodedStore), password)`:** đọc lại bytes như một kho lưu trữ; `size()` vẫn `1`.
- **`entryInstanceOf(alias, SecretKeyEntry.class)`:** `true`. Hai phép kiểm tra class còn lại `false`; đây là ý nghĩa của yêu cầu “kiểm tra đúng kiểu entry”.
- **`getEntry(...)` rồi cast:** thực hiện **sau khi đã xác định loại**. `getSecretKey()` lấy lại secret key, so sánh thông qua `MessageDigest.isEqual` để không cần in khóa.
- **`getEntry("missing", ...)`:** `null` vì alias không tồn tại; không tương đương “đã có alias nhưng nhập password sai”.
- **`load` với mật khẩu sai:** với kho PKCS12 vừa được ghi và bảo vệ, JDK demo ném `IOException`, ta in `true`. Không dựa vào **exact exception message**, vì nó phụ thuộc provider/JDK.
- **`Arrays.fill(password, '\0')`:** hạn chế thời gian mảng password demo còn trong RAM, không bảo đảm xóa được các copy khác; trong production nên có quy trình secret management.

Kết quả random của AES key và byte serialized PKCS12 thay đổi giữa các lần chạy; chương trình chỉ in các trạng thái có ý nghĩa **ổn định**.

### 6.2 Vì sao không dùng `instanceof` rồi cast ngay ở mọi trường hợp?

Có hai cách hợp lệ:

```java
// Cách A: kiểm tra loại trước, hữu ích khi muốn tránh giải mã key sai loại.
if (store.entryInstanceOf("api-aes", KeyStore.SecretKeyEntry.class)) {
    KeyStore.SecretKeyEntry secret = (KeyStore.SecretKeyEntry)
            store.getEntry("api-aes",
                    new KeyStore.PasswordProtection(entryPassword));
}

// Cách B: lấy Entry rồi pattern-match an toàn theo Java 17:
KeyStore.Entry item = store.getEntry("api-aes",
        new KeyStore.PasswordProtection(entryPassword));
if (item instanceof KeyStore.SecretKeyEntry secretEntry) {
    SecretKey aes = secretEntry.getSecretKey();
} else if (item instanceof KeyStore.PrivateKeyEntry privateEntry) {
    // privateEntry.getPrivateKey(), privateEntry.getCertificateChain()
} else if (item instanceof KeyStore.TrustedCertificateEntry trustEntry) {
    // trustEntry.getTrustedCertificate()
} else if (item == null) {
    // Alias không tồn tại.
}
```

Các đoạn trên là **minh họa** dùng biến `store`, `entryPassword` được khởi tạo từ ngữ cảnh chương trình (không phải lớp Java độc lập). Nếu dùng nhánh `getEntry` cho cả ba loại thì **`TrustedCertificateEntry` thường truy xuất với `null` protection**, còn key entries cần `PasswordProtection`. Vì vậy trong code production, hãy phân loại trước rồi gọi `getEntry` với **protection phù hợp**, thay vì luôn đưa password vào cả `TrustedCertificateEntry` và mong mọi provider đều chấp nhận.

Cần kiểm tra `containsAlias(alias)` nếu muốn xử lý riêng chuyện alias không tồn tại, nhưng `containsAlias == true` **không bảo đảm** entry thuộc loại/thuật toán/mục đích được mong đợi. Khi alias thuộc type không mong muốn, fail closed thay vì ép cast.

## 7. Thực hành bổ sung với `keytool`: PrivateKeyEntry và TrustedCertificateEntry

Vì Java SE **không cung cấp API public đơn giản để tự phát hành self-signed X.509 certificate**, bài code chính dùng SecretKeyEntry để chạy thuần Java, không đưa `sun.security.x509`/reflection/third-party library vào một ví dụ portable. Tuy nhiên, JDK có công cụ **`keytool`** giúp tạo và xem đúng các entry type khác.

Các lệnh sau là **bài thực hành riêng**, chạy trong **thư mục lab có quyền ghi**, không dùng tên file sản xuất. Không đưa password vào command line; `keytool` sẽ hỏi tương tác.

### 7.1 Tạo cặp khóa riêng kèm certificate chain

```bash
keytool -genkeypair -alias lab-signer -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 30 -dname "CN=Local Lab Only" -storetype PKCS12 -keystore lab-identity.p12
```

Lệnh này tạo private-key entry với cặp RSA mới và **self-signed certificate** dành cho lab. Xem metadata:

```bash
keytool -list -v -storetype PKCS12 -keystore lab-identity.p12
```

Trong mô hình keytool phổ biến, alias `lab-signer` có:

```text
Entry type: PrivateKeyEntry
Certificate chain length: 1
```

**Không sao chép private key ra file text** hoặc coi certificate tự ký này là chứng chỉ production. PKCS12 private-key entry chứa key và certificate chain, khác secret-key-only entry trong Java demo.

### 7.2 Export public certificate rồi import vào truststore

```bash
keytool -exportcert -rfc -alias lab-signer -file lab-signer.cer -storetype PKCS12 -keystore lab-identity.p12
keytool -importcert -alias lab-signer-trusted -file lab-signer.cer -storetype PKCS12 -keystore lab-trust.p12
keytool -list -v -storetype PKCS12 -keystore lab-trust.p12
```

Sau khi bạn **chủ ý xác minh certificate** và chấp nhận import trong lab, file `lab-trust.p12` có **trustedCertEntry**, chứ không chứa private key của `lab-signer`. Nếu keytool hỏi xác nhận tin cậy, chỉ xác nhận vì bạn vừa tự sinh certificate **trong môi trường lab**; không bỏ kiểm tra fingerprint ở môi trường thực.

`keytool -exportcert` export **chứng chỉ công khai**, không phải private key. Lưu một certificate ở truststore không cho phép ứng dụng ký thay chủ thể certificate đó. Đây là cách trực quan phân biệt một bên **identity keystore** (`PrivateKeyEntry`) với **truststore** (`TrustedCertificateEntry`). Cả hai đều có thể dùng file `.p12`, nhưng **ý nghĩa security khác nhau**.

### 7.3 Thêm secret key bằng `keytool` (tuỳ JDK/provider)

```bash
keytool -genseckey -alias lab-aes -keyalg AES -keysize 128 -storetype PKCS12 -keystore lab-secrets.p12
keytool -list -v -storetype PKCS12 -keystore lab-secrets.p12
```

Với provider hỗ trợ `SecretKeyEntry` cho type này, entry type sẽ hiện secret-key entry. Nếu provider không hỗ trợ, phải xử lý theo thiết kế được phép, không ép chuyển sang JKS rồi tưởng mọi type đều chứa được secret key.

**Lưu ý bảo mật đối với keytool:** dùng các file và passwords dành riêng cho học tập; tool có thể lưu password-derived protected key material trong file, nên bảo vệ quyền file và xóa dữ liệu lab theo chính sách. Output `keytool -list -v` không nên chứa raw secret/private key.

## 8. Phân biệt KeyStore và truststore trong TLS

`KeyStore` là API/type, còn “keystore” và “truststore” trong cấu hình TLS thường là **vai trò ứng dụng**:

- **Identity keystore:** chứa `PrivateKeyEntry` + certificate chain của service/client để **trình chứng chỉ và dùng private key khi xác thực/ký**.
- **Truststore:** chứa `TrustedCertificateEntry` (CA roots hoặc certificate được pin) để **đánh giá chứng chỉ của peer** theo policy.
- **Secret-key keystore:** chứa `SecretKeyEntry` cho AES/HMAC hoặc secret key khác, **không thay certificate identity**.

Một file keystore có thể hỗn hợp nhiều loại entry, nhưng việc đặt tên file `truststore.p12` **không tự** bảo đảm chỉ chứa trusted cert. Đừng chỉ nhìn đuôi `.p12` hoặc alias để quyết định một kho có an toàn dùng làm TLS truststore hay không.

Khi cấu hình TLS, còn cần chọn algorithm policy, `KeyManager`/`TrustManager`, chứng chỉ được phép sử dụng, hostname/identity validation, chain validation và revocation theo hệ thống. `KeyStore` chỉ cung cấp nguồn entry; **không tự chạy validation PKIX** khi bạn thêm một chứng chỉ bất kỳ bằng `setCertificateEntry`.

## 9. Những sai lầm thường gặp trong code và vận hành

| Lỗi/nhận định | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `getInstance("PKCS12")` rồi `setEntry` không gọi `load` | Keystore chưa được initialized | `load(null, pass)` khi tạo mới, hoặc `load(in, pass)` khi đọc cũ. |
| Dùng `load(null, pass)` để “mở file cũ” | Tạo kho mới rỗng; có thể dẫn tới xóa nội dung cũ nếu `store` đè vào cùng file | Đọc file cũ bằng `InputStream`. |
| Gọi `setEntry(...)` rồi thoát | Mới đổi trạng thái RAM, chưa persist | `store` ra output sau khi sửa. |
| Gọi `store` trực tiếp lên file đang dùng không backup | Có thể truncate file nếu lỗi/crash giữa chừng | Temp file + kiểm tra + atomic replace/backup khi hỗ trợ, quyền file chặt. |
| `isKeyEntry(alias)` rồi cast thẳng `SecretKeyEntry` | Cũng `true` cho `PrivateKeyEntry` | `entryInstanceOf(alias, SecretKeyEntry.class)` trước cast. |
| `getCertificate(alias) != null` tức trusted cert | PrivateKeyEntry cũng có leaf certificate | `isCertificateEntry(alias)` hoặc `entryInstanceOf(... TrustedCertificateEntry.class)`. |
| Tin certificate đã `setCertificateEntry` là hợp lệ | App vừa tự **chỉ định trust**, không hề chứng thực từ nguồn ngoài | Xác minh nguồn, fingerprint, PKIX/identity/usage. |
| Store password đúng thì mọi entry đều mở được | Entry password/protection có thể khác | Gọi `getEntry` với đúng `ProtectionParameter`, xử lý lỗi riêng. |
| Alias không tồn tại nên `getEntry` ném lỗi | API trả `null` nếu thiếu alias | Kiểm tra `containsAlias`, `null`, báo missing riêng. |
| Password sai thì coi như không có alias | Thất bại bảo vệ key, không phải bản ghi thiếu | Phân biệt `UnrecoverableEntryException`/lỗi load. |
| Đặt entry mới với alias đã tồn tại | `setEntry` có thể **ghi đè** entry cũ | Check alias, policy replace/migration và backup. |
| Gọi `load(null,pass)` lần 2 để “refresh” | Có thể reinitialize và làm mất state hiện tại | Reload từ file/stream thực hoặc tạo object mới. |
| Cho rằng `getDefaultType()` luôn là PKCS12 | Mặc định runtime cấu hình được | Chọn type tường minh với format được yêu cầu. |
| Lưu private key trong repo/với password nằm trong source | Lộ vật liệu khóa khi repo/log bị lộ | Secret manager/HSM/permissions/rotation. |
| Tin PKCS12 giải quyết mọi backup/concurrency | KeyStore không phải DB transactional hoặc HSM | Thiết kế atomic update, lock/backup, quản lý key lifecycle. |
| `getKey` trả `Key` rồi cast tùy ý thành `PrivateKey` | Alias có thể là `SecretKey` | Kiểm tra loại key/entry trước cast; dùng API đích phù hợp. |

## 10. Lỗi ngoại lệ và cách phát hiện chính xác

| Giai đoạn | Lỗi có thể xuất hiện | Hướng kiểm tra |
| --- | --- | --- |
| `KeyStore.getInstance("PKCS12")` | `KeyStoreException` nếu type/provider không được hỗ trợ | Xem Java version, provider registry, policy. |
| `size()`, `getKey`, `setEntry`, `store` trước `load` | `KeyStoreException` vì keystore chưa initialized | Gọi `load` trước. |
| `load(input, wrongPassword)` | `IOException`, có thể chứa cause `UnrecoverableKeyException` | Không tiếp tục; phân biệt mật khẩu sai với file corrupt/type không đúng. |
| `load(input, password)` | `NoSuchAlgorithmException`, `CertificateException`, `IOException` | Thuật toán integrity/cert parsing hoặc stream bytes không hợp lệ. |
| `setEntry` | `KeyStoreException` khi type/provider không hỗ trợ entry, alias/operation sai | Kiểm tra khả năng provider và thiết kế entry. |
| `getEntry(alias, wrongProtection)` | `UnrecoverableEntryException`, `UnrecoverableKeyException` | Entry còn đó nhưng không được mở bằng protection này. |
| `getEntry("missing", protection)` | **`null`** | Không ném lỗi chỉ vì alias thiếu; không cast nếu `null`. |
| `entryInstanceOf(alias, class)` | `false` nếu alias không có/khác loại; có thể `KeyStoreException` khi uninitialized | Dùng như gate trước cast và trước logic dùng key. |
| Cast `KeyStore.Entry` sai kiểu | `ClassCastException` do code | Phân loại bằng `entryInstanceOf` hoặc `instanceof`. |
| `store(output, password)` | `IOException` / `CertificateException` / `NoSuchAlgorithmException` | Có thể output chưa hoàn chỉnh; không thay file thật nếu lưu chưa thành công. |

**Phân biệt lỗi xác thực/integrity với lỗi parse:** Mật khẩu sai, file bị chỉnh sửa hoặc file không cùng type có thể cùng xuất hiện dưới dạng `IOException` ở `load`. Không hiển thị chi tiết nhạy cảm cho người dùng cuối hoặc tự fallback sang `load(..., null)` để “bỏ qua” kiểm tra integrity.

### 10.1 Hệ quả của `null`

Có ba `null` rất khác nhau:

```text
KeyStore.load(null, password)   -> TẠO MỚI kho trống.
KeyStore.getEntry("missing", p)  -> trả null vì alias KHÔNG CÓ.
KeyStore.getKey("cert-only", p)  -> trả null vì entry không chứa key.
```

Với `getEntry` của trusted certificate, protection thường là `null` vì không có private/secret key cần mở. Nhưng `load(in, null)` lại là quyết định khác: có thể bỏ integrity check. **Đừng áp một ý nghĩa chung cho mọi chữ `null` trong API.**

## 11. Thiết kế lưu file an toàn và quản lý khóa production

### 11.1 Tạo file mới không vô tình đè file cũ

Khi tạo kho, trước hết xác định rõ operation là `CREATE_NEW` hay `OPEN_EXISTING`; tránh logic:

```text
Nếu file có lỗi khi load -> load(null, password) -> store đè file cũ
```

Đó là một **lỗi mất dữ liệu nghiêm trọng**: sai password hoặc file corrupt có thể khiến code tạo kho trống rồi ghi đè mọi key/certificate trước đó.

Thay vào đó:

1. **Create new:** kiểm tra file đích chưa tồn tại, dùng thao tác tạo file **không cho phép replace** (chẳng hạn `CREATE_NEW`) và quyền truy cập hạn chế. Nếu tên đã có, báo lỗi rõ.
2. **Open existing:** nếu file không có hoặc password sai, dừng và điều tra; **không tạo kho mới như fallback**.
3. **Change existing:** tải kho thành công, ghi entry, serialize vào temp file, kiểm tra kết quả và bản backup phù hợp trước khi replace.
4. **Multiple processes:** phối hợp lock/transaction ở lớp ứng dụng; tránh lost updates khi hai process cùng đọc-ghi phiên bản khác nhau.
5. **Backup/recovery:** version store, backup an toàn, thử restore; lưu cả cấu hình type, algorithm/provider cần thiết và chính sách thay key.

`Files.move(..., ATOMIC_MOVE)` là công cụ hữu ích khi được filesystem hỗ trợ, nhưng bản thân nó không bảo đảm tự động việc fsync thư mục, backup, khôi phục hay khóa file; thiết kế cần phù hợp môi trường.

### 11.2 Bảo vệ keystore bytes không đồng nghĩa bảo vệ toàn bộ ứng dụng

- Password nên được cấp qua secure config/secret manager, không nằm trong Git, command-line, stdout, log, exception message hoặc test fixture production.
- Phân quyền file, owner, backup, volume/cloud bucket phù hợp; tránh file `.p12` world-readable ngay cả khi có password.
- Không ghi raw `PrivateKey.getEncoded()` hoặc `SecretKey.getEncoded()` lên log để debug. Provider/HSM có thể trả `null` vì khóa không xuất được; đây là đặc điểm an toàn, không tự coi là lỗi.
- Với HSM/PKCS#11 hoặc provider chuyên dụng, khóa có thể không thể export; KeyStore có thể biểu diễn reference/slot, không phải file PKCS12. Không tự sao chép sang file chỉ để thỏa `store`.
- Quản lý **key usage**: secret AES cho mã hóa không phải RSA private key cho chữ ký; certificate public không cho phép ký.
- Rotation, expiry, revocation và trust policy là quy trình **ngoài** `KeyStore.load/store`; có thể có nhiều alias cho key cũ/mới và thời gian chuyển đổi được kiểm soát.
- Nếu cung cấp truststore cho TLS, kiểm tra danh tính host/chain/usage, không chỉ để một CA certificate vào file.

## 12. Kiểm thử và checklist trước khi dùng

| Test | Điều cần chứng minh |
| --- | --- |
| `getInstance` trước `load` | Chưa init, không thể thao tác entry như kho đã mở. |
| `load(null, password)` | Tạo kho rỗng; `size() == 0`. |
| Thêm AES `SecretKeyEntry` | `isKeyEntry=true`; `isCertificateEntry=false`. |
| `store` rồi tạo object mới `load` | `size()` và alias/entry type giữ đúng. |
| `entryInstanceOf` cho ba type | Đúng một loại kỳ vọng trả `true`. |
| `getEntry(alias, protection)` | Đúng loại được lấy; key bytes so khớp nội bộ; không log secret. |
| Alias không tồn tại | `containsAlias=false`, `getEntry` trả `null`. |
| `load` với store password sai | Bị từ chối trên kho protected; không fallback tạo mới. |
| `getEntry` với key password sai | Bị từ chối theo `UnrecoverableEntryException` hoặc provider-specific lỗi. |
| Alias xung đột | Không âm thầm overwrite; có chính sách migration. |
| PKCS12 khác provider/JDK | Các entry types/algorithms và passwords thực sự interoperable. |
| Certificate/trust | Chứng chỉ có nguồn đáng tin, không gán trust chỉ vì import thành công. |
| Crash giữa `store` | File cũ/backup còn khôi phục được; không tạo kho rỗng thay thế. |

**Checklist code review:**

- [ ] `KeyStore.getInstance("PKCS12")` theo type đã thống nhất; không lệ thuộc `getDefaultType()` bất ngờ.
- [ ] Có đường đi rõ: tạo mới `load(null, pass)` **hoặc** đọc cũ `load(in, pass)`; không fallback destructive.
- [ ] `setEntry` hoặc `setCertificateEntry` đúng loại và bảo vệ key phù hợp.
- [ ] `store` được gọi sau thay đổi; stream được đóng, file update an toàn, không vô tình overwrite bản tốt.
- [ ] Phân biệt `isKeyEntry` với `entryInstanceOf(SecretKeyEntry.class)`/`entryInstanceOf(PrivateKeyEntry.class)`.
- [ ] Không xem `getCertificate != null` là đủ để xác định trusted certificate.
- [ ] Xử lý alias `null`/missing, sai password và sai type riêng; không cast mù.
- [ ] Password/key không nằm trong source/log/CLI; quản lý quyền file và backup.
- [ ] Có kiểm thử reload thực tế và kiểm thử provider/JDK mục tiêu.
- [ ] Truststore/identity keystore được phân biệt về **chính sách**, không chỉ tên file.

## 13. Câu hỏi tự kiểm tra

**1. `getInstance("PKCS12")` có mở hoặc tạo file ngay không?**  
**Không.** Nó chọn implementation, object chưa load. Muốn tạo kho mới cần `load(null, password)` rồi `store(...)` khi cần persist.

**2. `load(null, pass)` có an toàn để thử khi đọc file lỗi không?**  
**Không.** Nó tạo state rỗng, nếu sau đó `store` vào file đang lỗi sẽ **ghi đè và mất nội dung**. Phải điều tra lỗi password/format.

**3. Sau `setEntry`, file đã có key mới chưa?**  
**Chưa.** Phải `store` output rồi mới có bytes lưu trữ mới.

**4. Vì sao `isKeyEntry("x") == true` không đủ để cast thành `SecretKeyEntry`?**  
Vì cả `PrivateKeyEntry` và `SecretKeyEntry` đều là key entries; dùng `entryInstanceOf(..., SecretKeyEntry.class)` để xác nhận.

**5. `getCertificate("x") != null` có chứng minh `TrustedCertificateEntry` không?**  
**Không.** `PrivateKeyEntry` cũng trả leaf certificate qua API này.

**6. Khác biệt giữa `PrivateKeyEntry` và `TrustedCertificateEntry` là gì?**  
`PrivateKeyEntry` chứa **private key + chain** để thực hiện thao tác private-key; `TrustedCertificateEntry` chỉ chứa **public certificate** phục vụ chính sách trust, không có private key.

**7. Store password và key entry password có nhất thiết khác nhau không?**  
**Không.** Java API có hai vai trò khác nhau; khả năng tách password phụ thuộc type/provider. Demo PKCS12 dùng chung một password để tương thích.

**8. Alias không tồn tại và password sai có cùng kết quả không?**  
**Không.** Alias thiếu thường trả `null`; password sai để mở key entry gây lỗi recover, còn password sai khi `load` có thể là `IOException`.

**9. Tại sao demo không sinh self-signed certificate bằng Java public API?**  
Vì JDK không có bộ API public đơn giản dùng cho việc cấp X.509 self-signed. Demo Java thuần tập trung SecretKeyEntry; `keytool` minh họa PrivateKeyEntry và TrustedCertificateEntry.

**10. `PKCS12` có thay thế HSM/KMS và việc xác thực PKI không?**  
**Không.** Nó là định dạng/keystore implementation, không tự cung cấp chính sách enterprise, cách ly phần cứng, kiểm tra chuỗi trust hay quản lý vòng đời.

## Tài liệu chính thức

- [Java SE 17 — `java.security.KeyStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): các entry types, `getInstance`, `load`, `store`, `getEntry`, `setEntry`, `entryInstanceOf`, `isKeyEntry`, `isCertificateEntry` và ngoại lệ.
- [Java SE 17 — `KeyStore.SecretKeyEntry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.SecretKeyEntry.html): lưu và lấy `SecretKey`.
- [Java SE 17 — `KeyStore.PrivateKeyEntry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.PrivateKeyEntry.html): private key và certificate chain.
- [Java SE 17 — `KeyStore.TrustedCertificateEntry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.TrustedCertificateEntry.html): chứng chỉ được tin cậy.
- [Java SE 17 — `KeyStore.PasswordProtection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.PasswordProtection.html): protection parameter cho key entries.
- [Java SE 17 — `keytool` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): `-genkeypair`, `-genseckey`, `-exportcert`, `-importcert`, `-list -v`, keystore type.
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): KeyStore engine và provider SPI.
- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): type `PKCS12` và các tên chuẩn.
- [Java SE 17 — `KeyGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): cách sinh AES `SecretKey` trong ví dụ.

**Ghi nhớ:** `getInstance` chọn KeyStore; `load(null, ...)` tạo kho trống; `load(stream, ...)` đọc kho hiện có; `setEntry` sửa RAM; `store` mới lưu; `entryInstanceOf`/`instanceof` mới chứng minh **đúng kiểu entry**. Khả năng giữ khóa an toàn còn phụ thuộc mật khẩu, provider, quyền file, backup, PKI trust và key-management policy.
