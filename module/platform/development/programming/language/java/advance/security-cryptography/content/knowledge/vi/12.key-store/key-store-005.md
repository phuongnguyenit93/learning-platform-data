# 12.5 Phân biệt mật khẩu kho với thông tin bảo vệ từng khóa

Trong Java, `KeyStore` có thể chứa **private key**, **secret key** và **trusted certificate**. Khi dùng một file `.p12`, `.pfx` hoặc `.jks`, lập trình viên thường gặp hai giá trị trông như nhau nhưng có **vai trò khác nhau**:

1. **Mật khẩu kho (keystore password, store password, thường gọi `storepass`):** được cung cấp khi **nạp/lưu kho**, thường dùng để kiểm tra tính toàn vẹn của dữ liệu kho và, tùy định dạng/provider, bảo vệ các phần nội dung của kho.
2. **Thông tin bảo vệ từng khóa (entry/key protection, thường là `keypass`):** được cung cấp khi **đọc/ghi một key entry cụ thể**; nó có thể là một mật khẩu riêng, hoặc một loại `ProtectionParameter` khác như callback/PIN/provider-specific mechanism.

Hai giá trị này **có thể bằng nhau trong một cấu hình**, nhưng **không nên mặc định là một khái niệm**. Có thể mở được keystore, nhìn thấy alias và certificate, nhưng vẫn **không lấy được private/secret key** do thông tin bảo vệ key entry không đúng. Ngược lại, biết key password mà không có đường truy cập hợp lệ vào kho không đồng nghĩa đã mở được file keystore.

Mục tiêu bài: hiểu hai lớp bảo vệ; chọn đúng tham số trong `KeyStore.load/store`, `getKey/setKeyEntry`, `getEntry/setEntry`; phân biệt **JKS, PKCS12, truststore và HSM/PKCS11**; xử lý lỗi đăng nhập TLS/Java; và thiết kế quản lý mật khẩu, xoay vòng, backup một cách an toàn. Các ví dụ dùng Java 17+.

## 1. Mô hình tư duy: chiếc kho và các vật được cất

Hãy tưởng tượng một keystore là một **chiếc hộp có danh mục**. Mật khẩu kho giống một cơ chế kiểm tra/mở hộp; một số vật quan trọng bên trong có thể có **mật khẩu bảo vệ riêng**. Đây chỉ là phép so sánh để nhớ **phạm vi thao tác**; mức bảo vệ mật mã thực tế phụ thuộc vào **keystore type, provider, cách cài đặt và file permissions**.

```text
                    Java KeyStore
           +-----------------------------+
           | store password / protection |
           |  load(...)     store(...)   |
           +-----------------------------+
                     |
           Aliases / Entry metadata
       +-------------+-------------+--------------+
       |             |             |              |
   app-private    data-aes      ca-root       server-cert
   PrivateKey     SecretKey     TrustedCert   chain/public
       |             |             |              |
   entry-level    entry-level   certificate    certificate
   protection     protection    (no private     (public data)
       |             |          key password)
   keypass-A      keypass-B
```

Bên trong cùng một `KeyStore` có thể có nhiều **alias** (tên định danh entry). Nhưng **alias không phải mật khẩu**, không phải cơ chế phân quyền và không tự mang theo tính bí mật. Việc biết tên `app-private` không cấp quyền lấy private key. Mỗi alias trỏ đến một entry thuộc kiểu cụ thể; ứng dụng phải kiểm tra kiểu và dùng đúng protection khi thao tác.

### 1.1. Hai câu hỏi riêng

- **Tôi có thể nạp kho và kiểm tra dữ liệu kho có nguyên vẹn không?** → thường liên quan **store password** trong `KeyStore.load(input, storePassword)`.
- **Tôi có thể khôi phục hoặc sử dụng khóa dưới alias này không?** → liên quan **entry protection** trong `getKey(alias, keyPassword)` hoặc `getEntry(alias, protection)`.

Trả lời “có” cho câu thứ nhất **không tự động** trả lời “có” cho câu thứ hai.

### 1.2. Lưu ý về cơ chế bảo vệ thực tế

Không được giải thích đơn giản rằng mọi keystore “dùng store password để mã hóa toàn bộ file và key password để mã hóa từng entry”. Điều đó **không đúng cho mọi định dạng/provider**.

- **JKS truyền thống:** store password chủ yếu dùng để kiểm tra tính toàn vẹn; các private key entry có cơ chế bảo vệ riêng của format. JKS là định dạng legacy, không nên dùng làm lựa chọn bảo mật mới chỉ vì nó cho phép đặt hai mật khẩu khác nhau.
- **PKCS12:** có cơ chế PBE/MAC bảo vệ nội dung kho/các bag theo cấu hình; chi tiết thuật toán và cách dùng mật khẩu tùy implementation. Nhiều công cụ/ứng dụng yêu cầu hoặc giả định **storepass = keypass** cho tương thích.
- **PKCS11/HSM:** “keystore password” có thể đóng vai trò PIN/đăng nhập token; khóa có thể **không xuất được**, entry protection không nhất thiết là một chuỗi mật khẩu dùng cho `getEncoded()`.
- **Keystore không có password hoặc load với `null`:** hành vi xác minh toàn vẹn/bảo vệ khác nhau theo provider. Không coi khả năng đọc alias hoặc certificate là bằng chứng đã kiểm tra integrity.

## 2. Những entry nào được KeyStore quản lý?

Java `java.security.KeyStore` có các entry quan trọng:

| Entry | Chứa gì? | Có secret/private không? | Thông tin bảo vệ ở mức entry |
| --- | --- | --- | --- |
| `KeyStore.PrivateKeyEntry` | Private key và chuỗi certificate tương ứng | **Có** — private key | Thường được bảo vệ bằng password/PIN/key handle tùy provider |
| `KeyStore.SecretKeyEntry` | Khóa đối xứng, ví dụ AES hoặc HMAC key | **Có** — secret key | Thường có entry protection; hỗ trợ tùy keystore type |
| `KeyStore.TrustedCertificateEntry` | Certificate mà ứng dụng đánh dấu tin cậy | **Không có private/secret key** | Không có “mật khẩu riêng của khóa bí mật” vì không chứa private key |
| Certificate chain gắn với `PrivateKeyEntry` | Certificate public mô tả khóa/danh tính | Certificate là thông tin công khai, **không phải private key** | Có thể đọc certificate qua API mà không khôi phục private key |

Trong Java có các phương thức:

- `keyStore.isKeyEntry(alias)`: entry có chứa **khóa** (private/secret), không kết luận ứng dụng đã mở được khóa.
- `keyStore.isCertificateEntry(alias)`: entry certificate tin cậy độc lập; **khác** certificate chain của `PrivateKeyEntry`.
- `keyStore.getCertificate(alias)`, `getCertificateChain(alias)`: phục vụ phần **certificate/public data**; không phải API lấy private key.
- `keyStore.getKey(alias, keyPassword)`: yêu cầu khôi phục một key theo alias và password đúng của entry/provider.
- `keyStore.getEntry(alias, protection)`: lấy entry dưới một `ProtectionParameter` phù hợp.
- `keyStore.aliases()`: liệt kê alias, không giải mã toàn bộ private key bên trong.

**Truststore** thường là một `KeyStore` được dùng để giữ **trusted certificates** cho quá trình kiểm tra chuỗi chứng chỉ của peer. Nó khác **identity keystore** chứa private key + certificate chain của chính ứng dụng. Sự khác biệt do **vai trò và nội dung**, không phải do class Java riêng; cả hai có thể dùng PKCS12.

## 3. Mật khẩu kho (store password)

### 3.1. API nạp kho: `load`

Ví dụ với file PKCS12:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
char[] storePassword = obtainStorePasswordSecurely();
try (InputStream in = Files.newInputStream(Path.of("service.p12"))) {
    store.load(in, storePassword);
}
```

Đây là **mã minh họa**, chưa phải chương trình hoàn chỉnh: `obtainStorePasswordSecurely()` phải được triển khai bằng secret manager hoặc cơ chế nhập bảo mật; các import nằm trong namespace `java.security`, `java.io` và `java.nio.file`.

Ý nghĩa quan trọng:

- `getInstance("PKCS12")` chọn **keystore type/provider**, chưa nạp file.
- `load(in, storePassword)` đọc cấu trúc keystore, kiểm tra điều kiện load/integrity theo provider và mật khẩu được cung cấp. Nếu sai, thường thất bại với `IOException` hoặc exception phù hợp.
- `storePassword` trong lời gọi `load` **không phải** password mà `getKey` mặc định sẽ dùng cho mọi private/secret key.
- `load(null, password)` thường dùng để **tạo một kho rỗng mới**, không phải nạp file từ disk; trong ví dụ Java ở dưới chúng ta dùng cách này.
- Java API cho phép password `null` ở một số tình huống; theo contract JCA, khi không cung cấp password, **không thực hiện kiểm tra toàn vẹn dựa trên password theo cách thông thường**. Provider cũng có thể có hành vi cụ thể về truy cập nội dung. **Không dùng `null` để né lỗi “sai storepass” trong production.**

### 3.2. API ghi kho: `store`

```java
try (OutputStream out = Files.newOutputStream(Path.of("service-new.p12"))) {
    store.store(out, storePassword);
}
```

Mã trên cũng chỉ minh họa; trong sản phẩm cần ghi file an toàn (tệp tạm, quyền file, atomic move nếu khả dụng), bảo vệ đường dẫn và backup. Tham số `storePassword` được dùng **khi lưu cấu trúc kho** theo format/provider; nó **không phải lệnh đổi mọi keypass**.

**Quan trọng:** việc dùng mật khẩu mới khi lưu có thể thay đổi hình thức bảo vệ phần kho, nhưng bạn không thể giả định mọi entry trong mọi định dạng đều đã được **đổi password bảo vệ** theo đúng mong muốn. Quản lý migration/rotation phải được kiểm tra qua **lưu → nạp → recover từng entry** bằng thông tin mới/cũ tương ứng.

### 3.3. Mật khẩu kho là bảo vệ gì?

Trong API JCA, tham số password của `load` được mô tả chủ yếu là để **kiểm tra tính toàn vẹn** của dữ liệu kho. Một số implementation, đặc biệt PKCS12, còn dùng password trong bảo vệ/encryption những phần dữ liệu theo thiết kế. Vì vậy, mô tả chính xác là:

> **Store password là thông tin bảo vệ/cấp quyền ở phạm vi kho theo định dạng và provider; không được suy ra rằng nó đồng nhất với mọi key entry password hoặc là cơ chế mã hóa toàn bộ nội dung file.**

Nếu bạn mở được danh sách alias bằng một công cụ nhưng không trích được key, đây có thể là hành vi hoàn toàn hợp lý. Ngược lại, không nên dựa vào “alias list hiện ra” làm bằng chứng rằng storepass đã được xác minh hoặc private key đã sẵn sàng.

## 4. Thông tin bảo vệ từng key entry

### 4.1. API cũ `setKeyEntry/getKey`

Khi đặt một khóa vào kho, API có dạng:

```java
// Minh họa: secretKey/keystore đã được tạo đúng kiểu.
keyStore.setKeyEntry("aes-key", secretKey, entryPassword, null);
Key recovered = keyStore.getKey("aes-key", entryPassword);
```

Đoạn mã này là minh họa; `setKeyEntry` hỗ trợ loại key/chain tùy provider. Với **`PrivateKey`**, cần certificate chain phù hợp trong những trường hợp lưu entry chứa private key, còn `SecretKey` không có chuỗi certificate như một TLS private key. Provider/format có thể không nhận `SecretKeyEntry` (ví dụ không áp dụng mẫu này cho JKS legacy chỉ vì class Java có `setKeyEntry`).

Tham số thứ ba `entryPassword` trong `setKeyEntry` có ý nghĩa bảo vệ **key entry cụ thể**. Khi đọc, `getKey(alias, entryPassword)` cần giá trị tương ứng (hoặc cơ chế mà provider yêu cầu).

Nếu alias không tồn tại hoặc không chứa key, kết quả có thể là `null` theo contract của phương thức; nếu mật khẩu để giải mã key không đúng, implementation thường báo `UnrecoverableKeyException`. **Không dùng một vòng lặp thử nhiều mật khẩu tùy ý để “cứu” entry**, dễ làm rộng quyền và tạo dấu hiệu lộ bí mật.

### 4.2. API entry hiện đại `setEntry/getEntry`

Java dùng một abstraction rõ ràng hơn:

```java
// Cần import java.security.KeyStore.
KeyStore.ProtectionParameter protection =
        new KeyStore.PasswordProtection(entryPassword);

keyStore.setEntry("aes-key",
        new KeyStore.SecretKeyEntry(secretKey),
        protection);

KeyStore.SecretKeyEntry entry = (KeyStore.SecretKeyEntry)
        keyStore.getEntry("aes-key", protection);
SecretKey restored = entry.getSecretKey();
```

Đây là trích đoạn minh họa, không phải chương trình độc lập. Trong code thật nên kiểm tra alias/type, xử lý exception và gọi `PasswordProtection.destroy()` khi dùng xong.

Các kiểu chính:

- **`KeyStore.PasswordProtection`:** giữ password bảo vệ entry; có `destroy()` để hủy thông tin trong object (theo khả năng implementation).
- **`KeyStore.CallbackHandlerProtection`:** cho provider gọi callback để lấy credential/đăng nhập phù hợp; thường liên quan UI/token hoặc login flow đặc thù.
- **`KeyStore.ProtectionParameter`:** interface chung để provider hỗ trợ hình thức bảo vệ khác nhau.
- **`KeyStore.LoadStoreParameter`:** một loại tham số khác phục vụ nạp/lưu kho, không đồng nhất với `ProtectionParameter` của từng entry.

Không phải mọi provider hỗ trợ mọi loại protection hoặc mọi entry type. API Java là **hợp đồng chung**, implementation quyết định các cơ chế có thể dùng.

### 4.3. Các mật khẩu có thể độc lập

Ví dụ keystore có ba bí mật logic:

```text
Keystore file: app-keys.p12
    store password = STORE_P

Alias "tls-server":
    PrivateKeyEntry
    entry protection = ENTRY_TLS

Alias "finance":
    SecretKeyEntry
    entry protection = ENTRY_FINANCE

Alias "audit":
    SecretKeyEntry
    entry protection = ENTRY_AUDIT
```

Một hệ thống/provider hỗ trợ các password độc lập sẽ yêu cầu:

- `load(file, STORE_P)` để nạp kho;
- `getKey("finance", ENTRY_FINANCE)` để recover finance key;
- `getKey("audit", ENTRY_AUDIT)` để recover audit key.

`STORE_P` không tự mở khóa finance hoặc audit nếu hai entry được bảo vệ khác. `ENTRY_FINANCE` không được quyền mở audit chỉ vì cùng file. **Tuy nhiên**, nếu application đã nắm tất cả password, thì ranh giới phân quyền thực tế phụ thuộc cách application giữ credential, file access và provider — không phải bản thân tên alias.

### 4.4. Cùng password cho store và key có sai không?

**Không phải lỗi cú pháp**, nhưng làm giảm mức phân tách credential nếu thiết kế dựa vào hai lớp quyền độc lập. Trong thực tế **một số provider hoặc công cụ** chỉ hỗ trợ/đảm bảo tương thích khi **storepass = keypass** (đặc biệt một số quy trình PKCS12). Khi đó:

- Hãy ghi rõ rằng ứng dụng đang dùng **cùng một credential cho hai vai trò**, không được mô tả chúng là hai bí mật độc lập.
- Giới hạn truy cập file và secret, dùng workload identity/IAM, nguyên tắc quyền tối thiểu và rotation phù hợp.
- Nếu cần tách quyền mạnh giữa nhiều khóa hoặc nhiều tenant, **đừng mặc định một file PKCS12 cộng nhiều mật khẩu là cơ chế isolation đủ mạnh**. Cân nhắc HSM/KMS/secret manager, phân tách keystore hoặc key handles/provider permission.

## 5. Java 17+: chứng minh hai lớp bảo vệ bằng hai secret key độc lập

Chương trình **KeyStoreProtectionDemo.java** sau tạo **PKCS12 in-memory**, thêm **hai AES key** bảo vệ bằng **hai entry password khác nhau**, rồi lưu cấu trúc kho bằng **store password thứ ba**. Khi load lại:

- Store password đúng cho phép nạp kho.
- Đúng entry password phục hồi đúng key.
- Dùng store password để đọc entry có password khác sẽ thất bại.
- Dùng password của finance để đọc audit sẽ thất bại.
- Dùng store password sai để nạp file sẽ thất bại ở provider JDK của ví dụ.

**Chú ý:** Các password dạng literal trong bài là **giá trị demo cố ý**, không sử dụng trong production; trong phần mềm thật phải đọc từ secret manager/kênh bảo mật, tránh để trong source/historical commits. Mã không in raw password hoặc key material. JDK/provider có thể khác nhau; ví dụ đã được chạy trên JDK hỗ trợ `PKCS12` và Java API nêu dưới đây.

### 5.1. File `KeyStoreProtectionDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.security.KeyStore;
import java.security.UnrecoverableKeyException;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class KeyStoreProtectionDemo {
    static SecretKey aesKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        return generator.generateKey();
    }

    public static void main(String[] args) throws Exception {
        // Demo only: không hardcode các password này trong sản phẩm.
        char[] storePassword = "sample-store-phrase-01".toCharArray();
        char[] financePassword = "sample-finance-phrase-02".toCharArray();
        char[] auditPassword = "sample-audit-phrase-03".toCharArray();

        try {
            KeyStore created = KeyStore.getInstance("PKCS12");
            created.load(null, storePassword); // Khởi tạo keystore rỗng.

            SecretKey financeKey = aesKey();
            SecretKey auditKey = aesKey();

            created.setEntry("finance",
                    new KeyStore.SecretKeyEntry(financeKey),
                    new KeyStore.PasswordProtection(financePassword));
            created.setEntry("audit",
                    new KeyStore.SecretKeyEntry(auditKey),
                    new KeyStore.PasswordProtection(auditPassword));

            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            created.store(bytes, storePassword);
            byte[] blob = bytes.toByteArray();

            KeyStore loaded = KeyStore.getInstance("PKCS12");
            loaded.load(new ByteArrayInputStream(blob), storePassword);

            boolean financeRestored = Arrays.equals(
                    financeKey.getEncoded(),
                    loaded.getKey("finance", financePassword).getEncoded());
            boolean auditRestored = Arrays.equals(
                    auditKey.getEncoded(),
                    loaded.getKey("audit", auditPassword).getEncoded());

            boolean storeCannotUnlockFinance = false;
            try {
                loaded.getKey("finance", storePassword);
            } catch (UnrecoverableKeyException expected) {
                storeCannotUnlockFinance = true;
            }

            boolean financeCannotUnlockAudit = false;
            try {
                loaded.getKey("audit", financePassword);
            } catch (UnrecoverableKeyException expected) {
                financeCannotUnlockAudit = true;
            }

            boolean wrongStoreRejected = false;
            try {
                KeyStore wrongStore = KeyStore.getInstance("PKCS12");
                wrongStore.load(new ByteArrayInputStream(blob),
                        "wrong-store-phrase".toCharArray());
            } catch (IOException expected) {
                wrongStoreRejected = true;
            }

            System.out.println("store type: " + loaded.getType());
            System.out.println("aliases: " + loaded.size());
            System.out.println("finance key restored: " + financeRestored);
            System.out.println("audit key restored: " + auditRestored);
            System.out.println("store password cannot recover finance key: "
                    + storeCannotUnlockFinance);
            System.out.println("finance password cannot recover audit key: "
                    + financeCannotUnlockAudit);
            System.out.println("wrong store password rejected: "
                    + wrongStoreRejected);

            Arrays.fill(blob, (byte) 0);
        } finally {
            // Chỉ là dọn mảng tạm theo khả năng, không bảo đảm xóa mọi bản sao.
            Arrays.fill(storePassword, '\0');
            Arrays.fill(financePassword, '\0');
            Arrays.fill(auditPassword, '\0');
        }
    }
}
```

Biên dịch và chạy với **Java 17+**:

```bash
javac -encoding UTF-8 KeyStoreProtectionDemo.java
java KeyStoreProtectionDemo
```

Stdout kỳ vọng ở provider PKCS12 phổ biến trên JDK (đã thực nghiệm, không phụ thuộc các byte khóa AES ngẫu nhiên):

```text
store type: PKCS12
aliases: 2
finance key restored: true
audit key restored: true
store password cannot recover finance key: true
finance password cannot recover audit key: true
wrong store password rejected: true
```

### 5.2. Phân tích kết quả và giới hạn

1. **`KeyStore.getInstance("PKCS12")`:** chọn kho chuẩn PKCS12. Không cần file thật vì dữ liệu được lưu vào `ByteArrayOutputStream` và nạp lại qua `ByteArrayInputStream`.
2. **`created.load(null, storePassword)`:** khởi tạo kho mới. Mật khẩu kho được dùng khi `store` và `load` lại.
3. **`setEntry`:** hai entry dùng `KeyStore.SecretKeyEntry` và các `PasswordProtection` **khác nhau**, không phải hai alias chỉ đổi tên.
4. **`store(bytes, storePassword)`:** xuất kho dưới định dạng PKCS12. Không thấy finance/audit raw keys trong stdout.
5. **`load(blob, storePassword)`:** nạp thành công chứng minh store password đúng cho file và provider trong demo, nhưng **chưa chứng minh recover được hai key**.
6. **`getKey(alias, entryPassword)`:** mỗi entry được đọc bằng password riêng. `Arrays.equals` chỉ chứng minh byte khóa vừa đọc tương ứng với byte khóa được tạo; nó không đo độ mạnh cryptographic của password.
7. **`getKey("finance", storePassword)`:** ném `UnrecoverableKeyException` vì finance entry được bảo vệ bằng password riêng.
8. **`getKey("audit", financePassword)`:** thất bại vì finance password không phải audit password.
9. **`load(blob, wrongStorePassword)`:** kho có kiểm tra password/integrity nên bị provider từ chối với `IOException`.
10. **`Arrays.fill`:** chỉ dọn những mảng còn truy cập được, không bảo đảm JVM/provider không còn bản sao. `String` literal chứa password demo vẫn có thể tồn tại trong memory; vì vậy production không dùng cách tạo literal trong source.

**Độ chính xác của kết luận:** minh họa này phản ánh **cấu hình PKCS12/JDK đã kiểm tra**, chứ không chứng minh mọi tool PKCS12 và provider đều hỗ trợ password khác nhau cho các entry. Cần kiểm chứng định dạng và provider đích khi triển khai.

### 5.3. Nếu muốn dùng `getEntry` thay `getKey`

Khi đã có `KeyStore loaded` và password của finance:

```java
// Mã minh họa, tiếp nối loaded/financePassword từ chương trình trên.
KeyStore.PasswordProtection p =
        new KeyStore.PasswordProtection(financePassword);
try {
    KeyStore.Entry entry = loaded.getEntry("finance", p);
    if (entry instanceof KeyStore.SecretKeyEntry secretEntry) {
        SecretKey key = secretEntry.getSecretKey();
        // Chỉ đưa key vào hoạt động mật mã được ủy quyền; không log key.
    }
} finally {
    p.destroy();
}
```

`KeyStore.getEntry` trả một `Entry`, còn kiểu của entry phải được nhận diện. Cũng không có cơ chế “lấy được key vì đã biết alias”. Nếu dùng sai protection, provider có thể ném `UnrecoverableEntryException` hoặc exception tương ứng.

## 6. JKS và PKCS12: đừng đánh đồng tính năng hoặc kỳ vọng mật khẩu

Java hỗ trợ một số keystore type, mỗi loại khác nhau về cách lưu dữ liệu và thuật toán bảo vệ. **`KeyStore.getDefaultType()` thường là `"pkcs12"` trên các JDK hiện đại**, nhưng vẫn có thể được cấu hình lại. Hãy chọn type rõ ràng khi cần tính tương thích và xác định file.

### 6.1. Bảng so sánh thực hành

| Tiêu chí | JKS | PKCS12 |
| --- | --- | --- |
| Mục tiêu lịch sử | Định dạng keystore truyền thống của Java | Định dạng trao đổi khóa/certificate phổ biến giữa hệ sinh thái |
| Dùng cho ứng dụng mới | Nên cân nhắc tránh nếu không có ràng buộc legacy; tính năng/bảo vệ cũ | Thường là lựa chọn file keystore phổ biến hơn; thuật toán/provider vẫn cần kiểm tra |
| Mật khẩu kho | Kiểm tra integrity của file JKS theo cơ chế legacy | Dùng cho cơ chế integrity/PBE theo implementation |
| Bảo vệ private key entry | Có key password riêng trong nhiều luồng JKS/keytool | API Java có thể hỗ trợ per-entry password; CLI/third-party có thể yêu cầu trùng storepass |
| SecretKeyEntry | JKS thông thường **không hỗ trợ lưu secret keys** | PKCS12 Sun provider có thể hỗ trợ secret key entry (đã minh họa ở trên) |
| TrustedCertificateEntry | Có | Có |
| Tính tương thích | Chủ yếu Java và công cụ tương thích JKS | Phổ biến hơn nhưng không phải mọi công cụ xử lý PBE/MAC/per-entry password giống nhau |

Đừng xem file extension `.jks` hoặc `.p12` là bằng chứng tuyệt đối về type: **type do dữ liệu và provider quyết định**. Một file đặt tên `.p12` nhưng không có nội dung đúng format không thể nạp hợp lệ.

### 6.2. `keytool` và hai password

Công cụ `keytool` có các tùy chọn:

- `-storetype`: định dạng keystore (ví dụ `JKS` hoặc `PKCS12`).
- `-keystore`: đường dẫn file.
- `-storepass`: password của keystore; khi không chỉ định, công cụ thường hỏi tương tác.
- `-keypass`: password bảo vệ private key entry cho lệnh/keystore có hỗ trợ.
- `-alias`: định danh entry.
- `-keypasswd`: lệnh đổi password của **key entry** với type/command hỗ trợ, không phải đổi store password.

**Điểm đặc biệt quan trọng:** trên nhiều bản `keytool` của JDK, khi tạo **PKCS12** và cung cấp `-keypass` khác `-storepass`, công cụ có thể **cảnh báo và bỏ qua** password riêng. Một số công cụ PKCS12 khác cũng yêu cầu hai password **bằng nhau**. Tuy nhiên **API Java `KeyStore` không buộc mọi provider/luồng tạo PKCS12 đều phải dùng cùng mật khẩu**, như ví dụ `setEntry` cho thấy. Hai điều này không mâu thuẫn: **giới hạn của công cụ và khả năng của API/provider là hai lớp khác nhau**.

### 6.3. Thử nhập mật khẩu khi tạo JKS bằng `keytool`

Ví dụ thực hành trong **môi trường test riêng**, không đưa private key production vào lệnh học tập. Để công cụ **hỏi mật khẩu tương tác** (thay vì viết mật khẩu trong lịch sử shell), chạy:

```bash
keytool -genkeypair \
  -alias local-test \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -dname "CN=Local Test" \
  -storetype JKS \
  -keystore local-demo.jks
```

Trong nhiều shell Windows, dấu `\` dùng để xuống dòng của Bash không áp dụng; có thể gõ **một dòng** tương đương. Khi được hỏi, nhập store password rồi nhập **password của private key entry** khác với store password nếu công cụ/format cho phép. Nếu nhấn Enter ở prompt key password, `keytool` thường có thể dùng cùng store password.

Liệt kê metadata và certificate bằng store password:

```bash
keytool -list -v -storetype JKS -keystore local-demo.jks
```

Sau khi liệt kê được alias/certificate, **chưa chắc** service đã khôi phục private key: bước dùng private key vẫn cần key password đúng hoặc cơ chế bảo vệ của provider.

Nếu muốn thử thay key password cho JKS, xem các tùy chọn tương ứng của `keytool -keypasswd` trên JDK đang chạy; **không giả định `-keypasswd` hỗ trợ PKCS12 tương tự JKS**. Thao tác đổi password thật nên backup, thử nghiệm và có rollback/recovery trước.

### 6.4. Di chuyển từ JKS sang PKCS12

Một quy trình import/export có thể có **storepass nguồn**, **keypass nguồn**, **storepass đích** và **keypass đích**. Chúng khác vai trò; nếu bỏ sót keypass nguồn, công cụ có thể thử storepass nguồn rồi yêu cầu nhập đúng password. Nếu đích là PKCS12, cần xét giới hạn của công cụ nhận và các hệ thống thứ ba về việc dùng cùng password.

**Không coi import thành công là đã bảo đảm ứng dụng khởi động được.** Sau khi di chuyển, kiểm tra:

- Alias và entry type có đúng không?
- Certificate chain gắn với private key có đủ và đúng thứ tự không?
- Ứng dụng load keystore bằng storepass mới được không?
- TLS/crypto runtime recover private key bằng credential mà provider yêu cầu được không?
- Provider/JDK đích có đọc được thuật toán bảo vệ/PBE/MAC trong file PKCS12 không?
- Backup cũ, quyền truy cập và rotation policy có được cập nhật không?

## 7. Trong TLS/SSL Java: chỗ nào dùng store password, chỗ nào dùng key password?

Một ứng dụng HTTPS server thường có **identity keystore** chứa private key và certificate chain; `KeyManagerFactory` cần truy cập private key đó để thực hiện chứng minh quyền sở hữu khóa trong handshake.

Mô hình API phổ biến:

```java
// Minh họa ranh giới; cần thêm imports và cấu hình provider thật.
KeyStore identity = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
    identity.load(in, storePassword);
}

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, privateKeyPassword);
```

- `identity.load(..., storePassword)`: mở/kiểm tra **keystore**.
- `kmf.init(identity, privateKeyPassword)`: cung cấp thông tin để **khôi phục private key** mà key manager cần trong các provider thông thường.
- Nếu `privateKeyPassword` khác `storePassword` mà bạn truyền nhầm storePassword vào `kmf.init`, có thể nạp file thành công nhưng khởi tạo KeyManagerFactory thất bại với `UnrecoverableKeyException` hoặc wrapped exception.
- `KeyManagerFactory.init(KeyStore, char[])` nhận một password phục vụ khôi phục các khóa; nếu keystore có **nhiều private key entry với các password độc lập**, không mặc định rằng overload đơn giản này xử lý được mọi entry. Cân nhắc cấu hình chọn alias/provider, `KeyStore.Builder`/`KeyStoreBuilderParameters` hoặc thiết kế kho/key manager phù hợp với thư viện/runtime.
- Không suy ra **mọi** framework TLS và mọi provider đều nhận cùng hai biến cấu hình; phải đọc contract cụ thể của ứng dụng.

### 7.1. Truststore dùng thế nào?

Một TLS client/server thường có truststore gồm **trusted CA certificates** để kiểm tra peer. Cơ chế:

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("trust.p12"))) {
    trust.load(in, trustStorePassword);
}
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);
```

Truststore chứa trusted certificates **không cần private-key password để giải mã một private key**, vì thường **không chứa private key**. Việc đọc certificate truststore không đồng nghĩa hoàn tất xác thực peer; trust manager còn phải kiểm tra chain, thời hạn, mục đích, hostname (ở lớp TLS endpoint identification), trạng thái trust/policy tùy môi trường.

**Đừng nhầm:** đặt một keystore password cho truststore không biến certificate trong đó thành bí mật. Certificate thường là dữ liệu public. Store password có thể dùng kiểm tra integrity theo provider; thay đổi tập trusted anchors là thay đổi **trust policy**, không phải đổi private key.

### 7.2. Hệ thống config thường có hai trường

Nhiều framework cung cấp một giá trị tương đương **`key-store-password`** và một giá trị **`key-password`**. Trường đầu để nạp kho; trường thứ hai để khôi phục key entry. Một số framework mặc định key password theo store password khi key password bỏ trống, nhưng **đó là hành vi framework/tool, không phải quy luật universal của `KeyStore` API**.

Nếu nhận lỗi “đã đọc được `.p12` nhưng TLS không khởi động”, hãy kiểm tra **alias, key type, key password và certificate chain**, thay vì chỉ thay store password rồi thử lại.

## 8. Nếu không có password: HSM, PKCS11 và non-exportable key

Trong hệ thống có HSM hoặc token, private key có thể nằm **trong thiết bị** và không bao giờ được xuất ra file dạng byte. `KeyStore` là một interface để tham chiếu/điều khiển key entry, nhưng semantics khác file JKS/PKCS12.

- **Token PIN/credential** có thể được dùng khi đăng nhập provider. Nó không tự có một file password để mở file `.p12`.
- Việc gọi `KeyStore.load(null, pin)` ở một số PKCS11 provider có thể là cách đăng nhập/khởi tạo keystore của token, nhưng phải theo provider docs; không dùng quy tắc này cho mọi format.
- `getKey` có thể trả key handle mà `getEncoded()` trả **`null`**. Không coi `null` đồng nghĩa key không hợp lệ hoặc phải “tải private key ra”.
- Quyền sử dụng khóa có thể do **token ACL, partition, IAM, mechanism flags, PIN policy** hoặc cơ chế khác quyết định. Per-entry password không nhất thiết tồn tại.
- Nếu ứng dụng cần ký số bằng private key trong HSM, hãy dùng `Signature` với key handle/provider tương ứng; tránh ép secret ra ứng dụng bằng một “đường vòng” gây mất lợi ích bảo vệ.

**Bài học:** “Thông tin bảo vệ từng khóa” là khái niệm **rộng hơn keypass**. Trong ví dụ file đơn giản nó là một `char[]`; ở HSM có thể là một chính sách sử dụng khóa mà ứng dụng chỉ có quyền gọi operation, không có quyền xuất raw key.

## 9. Tình huống lỗi và cách phân biệt phạm vi thất bại

### 9.1. Matrix chẩn đoán

| Hiện tượng | Khả năng thường gặp | Nên kiểm tra |
| --- | --- | --- |
| `KeyStore.load(...)` thất bại vì password/integrity | Storepass không đúng, file lỗi/corrupt, provider hoặc format không tương thích | File/type/provider, store password được cấp phát, integrity và backup |
| `load(...)` thành công nhưng `getKey(alias, pass)` ném `UnrecoverableKeyException` | Keypass sai hoặc không khớp bảo vệ entry | Alias, kiểu entry, key protection, provider |
| `getKey(...)` trả `null` | Alias không có hoặc alias không phải key entry theo contract | `containsAlias`, `isKeyEntry`, danh sách alias |
| `getEntry(...)` không recover được | ProtectionParameter sai/không được hỗ trợ, entry corrupt | Entry type, `PasswordProtection`/provider, error cause |
| `keytool -list` hiển thị chứng chỉ nhưng service TLS lỗi | Có thể chưa recover được private key, key alias sai, chain thiếu, key manager config sai | `KeyManagerFactory.init`, alias, type, keypass, chain |
| `getCertificate(alias)` hoạt động nhưng private key thất bại | Certificate public có thể đọc, key entry còn bị bảo vệ riêng | Keypass và quyền sử dụng key |
| Chuyển PKCS12 sang công cụ khác thất bại | Khác biệt provider/PBE/MAC/cách áp dụng mật khẩu | Format compatibility và export profile được hỗ trợ |
| Provider trả `getEncoded() == null` | Key non-exportable hoặc policy provider | Dùng crypto operation qua provider, không ép dump secret |
| KeyManagerFactory dùng một password cho nhiều key entries | Các entry có thể có keypass khác nhau | Builder/provider hoặc phân chia keystore theo cấu hình |

Lưu ý **exception không phải bằng chứng tuyệt đối** về nguyên nhân. Một `IOException` khi `load` cũng có thể do file lỗi, stream hỏng hoặc thuật toán không được hỗ trợ. Không ghi thông điệp chi tiết chứa secret trong log hoặc trả về client. Khi chẩn đoán cần xem root cause từ provider, JDK, type, permissions và điều kiện file.

### 9.2. Chiến lược chẩn đoán có kiểm soát

1. Xác nhận file path, permissions, format/type và provider đang dùng. **Không thử sửa password liên tục** trên file production.
2. Xác minh storepass bằng công cụ/API trong môi trường có thẩm quyền, không in password.
3. Kiểm tra alias tồn tại và kiểu entry trước khi gọi `getKey`. Danh sách alias là metadata, cần bảo vệ nếu chứa thông tin hệ thống nhạy cảm.
4. Chỉ dùng **entry password đúng phạm vi** đã được provision. Đừng thử mọi mật khẩu khác nhau theo danh sách; quy trình cứu hộ phải có phê duyệt.
5. Kiểm tra private key certificate chain (TLS) hoặc thuật toán secret key tương ứng (ứng dụng crypto).
6. Nếu provider/format khác nhau, kiểm chứng trên bản **backup cô lập**, không chỉnh file đang hoạt động trực tiếp.
7. Sau thay đổi config, chạy test thật: load keystore, recover key theo nhu cầu, ký/giải mã hoặc khởi tạo TLS; **không dừng ở `keytool -list`**.

## 10. Quản lý bí mật: password kho và password từng key

### 10.1. Nên bảo vệ hai loại password như thế nào?

Cả store password và entry password đều là **secret** khi chúng được dùng trong hệ thống thật:

- Lưu trong **secret manager/KMS/HSM** hoặc kênh cấu hình bí mật có kiểm soát; không commit vào repo, cấu hình public, ví dụ Markdown, issue tracker, chat hoặc CI log.
- Dùng **workload identity/least privilege**: service chỉ nên đọc secret nó thực sự cần.
- Tránh `-storepass actualSecret` hoặc `-keypass actualSecret` trong command line của production vì process list, shell history và log có thể ghi lại đối số. Với `keytool`, prefer prompt hoặc cơ chế secret loading phù hợp và hạn chế truy cập.
- Bảo vệ **file keystore** bằng file permission, storage encryption, backup protection và access control. Một mật khẩu mạnh không thay thế việc giữ private key material khỏi người trái phép.
- Định kỳ đánh giá password strength, KDF/PBE format support, JDK/provider version và chính sách rotation. Đừng đặt mật khẩu demo ngắn hay mặc định `"changeit"` cho tài sản nhạy cảm.
- Không log `String.valueOf(passwordCharArray)`, raw byte key, certificate private components hay stack trace chứa thông tin cấu hình bí mật.

### 10.2. Thay store password khác thay key password

Có hai thao tác độc lập về **ý định quản trị**:

| Thay đổi | Thao tác được nhắm tới | Phải kiểm chứng sau đó |
| --- | --- | --- |
| **Đổi store password** | Bảo vệ cấu trúc kho ở mức file/keystore | Có load/store bằng password mới được không? File cũ/backup có còn chứa password cũ không? |
| **Đổi entry password của một key** | Thay protection cho alias/key cụ thể | `getKey` bằng password mới có thành công? Bằng password cũ có còn được provider chấp nhận không? |
| **Rotate private/secret key material** | Tạo **khóa mật mã mới** chứ không chỉ đổi password bảo vệ | Ứng dụng có dùng khóa mới? Chứng chỉ, wrapped data, token, handshake và dữ liệu cũ có được migrate không? |
| **Chuyển keystore type/provider** | Đổi cơ chế lưu trữ, mật mã và interoperability | Toàn bộ alias, key, certificate chain, PBE/MAC, API/TLS đều hoạt động đúng? |

**Đổi password bảo vệ không tự biến khóa AES/RSA cũ thành khóa mới.** Mức độ ảnh hưởng khi lộ **mật khẩu** và khi lộ **private key raw bytes** khác nhau. Nếu key bytes bị lộ, chỉ thay password kho/keypass là **không đủ**: cần rotate vật liệu khóa và xử lý dữ liệu/chữ ký/certificate bị ảnh hưởng theo chính sách.

### 10.3. Sao lưu và khả năng khôi phục

Khi mất password bảo vệ khóa, có thể **không thể recover key**, kể cả còn file keystore. Nếu mất private key, ciphertext cũ hoặc danh tính TLS có thể không còn dùng được. Cần:

- Sao lưu file keystore an toàn và **backup credential/key metadata** theo chính sách tách quyền.
- Ghi phiên bản file, keystore type, provider, alias, purpose, thuật toán, cert chain và chính sách rotation.
- Kiểm tra khôi phục định kỳ trong **môi trường cô lập** bằng load + operation thật, không chỉ kiểm tra file tồn tại.
- Với PKCS12 tạo bởi tool/provider đặc thù, lưu thông tin **tương thích phiên bản/phương thức bảo vệ** để tránh không mở được sau nâng cấp hoặc chuyển vendor.
- Khi rotate, giữ bản cũ cho thời gian cần thiết (ví dụ decrypt dữ liệu lịch sử), giới hạn phạm vi sử dụng và có kế hoạch hủy an toàn.

### 10.4. Mật khẩu khác nhau chưa chắc có phân quyền mạnh

Nếu cả storepass và mọi entrypass đều được inject vào **cùng một process** có quyền đọc file keystore, process bị compromise có thể lấy được mọi key mà nó được quyền recover. Alias và password riêng **không** tạo ranh giới giữa các service/tenant nếu runtime đều giữ cùng quyền và tất cả credential.

Muốn tách biệt mạnh hơn, hãy xem xét:

- Keystore/secret riêng theo service, workload hoặc tenant.
- HSM/KMS có IAM và audit ở mức thao tác/khoá.
- Khóa **non-exportable** và API chỉ cho phép ký/giải mã theo policy.
- Không để service có quyền một thao tác tự tải toàn bộ file, tất cả keypass và raw private keys.

## 11. Ba kịch bản áp dụng trong dự án Java

### 11.1. HTTPS server: kho nạp được nhưng handshake không chạy

Giả sử `server.p12` chứa alias `https-key` là `PrivateKeyEntry`. App có biến `STORE_PASS` và `KEY_PASS`. Nếu `STORE_PASS` đúng nhưng `KEY_PASS` sai:

- `KeyStore.load` có thể thành công;
- `KeyManagerFactory.init` hoặc phép dùng private key có thể thất bại;
- Certificate public có thể vẫn liệt kê được.

Hướng sửa: xác định type/provider, alias và entry protection; cập nhật đúng credential của key entry hoặc cấu hình provider, không đổi certificate ngẫu nhiên và không bỏ password.

### 11.2. Hai khóa AES trong cùng PKCS12

Cấu hình có `finance` và `audit`; finance service không nên có `auditPassword`. Demo ở trên cho thấy hai entry có thể được bảo vệ bằng các password riêng dưới provider hỗ trợ. Tuy vậy, nếu cả file và hai secret đều nằm trong cùng tiến trình, phạm vi bí mật không thực sự được tách. Với yêu cầu tuân thủ/tenant separation, cân nhắc thiết kế khác thay vì chỉ đổi alias/keypass.

### 11.3. Truststore chứa CA, không chứa TLS private key

`trust.p12` có trusted certificates, được nạp bằng truststore password để kiểm tra cấu trúc/trust anchors. Khi khởi tạo `TrustManagerFactory` từ truststore, **không có private-key password cần cung cấp** cho các `TrustedCertificateEntry`. Nếu mTLS client còn phải gửi certificate của chính nó, đó là **identity keystore** và cần private key tương ứng, không thể chỉ dùng truststore.

## 12. Lỗi thường gặp và cách sửa

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “`load(storepass)` thành công nghĩa là đã giải mã hết private keys.” | Nạp kho và recover key là hai thao tác khác | Dùng `getKey/getEntry` hoặc khởi tạo crypto/TLS để kiểm tra entry |
| “`storepass` luôn bằng `keypass`.” | API có thể cho password riêng, tùy provider/tool | Ghi rõ policy thực tế, không đồng nhất về khái niệm |
| “`keypass` có thể mở cả file keystore.” | Keypass bảo vệ một entry; không phải credential của kho | Cung cấp storepass cho `load` và đúng entry protection cho key |
| “Đổi tên alias là đổi key password.” | Alias chỉ là tên định danh | Dùng API/tool thay protection thực tế |
| “Certificate có private-key password.” | Public certificate không chứa private key | Phân biệt certificate/truststore với `PrivateKeyEntry` |
| “`keytool -list` chứng minh TLS private key hoạt động.” | Chỉ cho biết một phần cấu trúc/certificate | Kiểm tra key recovery và TLS handshake phù hợp |
| “PKCS12 từ mọi tool đều hỗ trợ keypass riêng.” | Interoperability/tool limitations | Test provider và công cụ đích, xét yêu cầu storepass = keypass |
| “JKS có hai password nên bảo mật hiện đại hơn PKCS12.” | JKS legacy có cơ chế bảo vệ khác | Chọn format theo bảo mật và tương thích thực tế |
| “`getEncoded() == null` nghĩa key hỏng.” | Non-exportable key có thể trả null | Dùng provider/key handle thao tác trực tiếp |
| “Đổi storepass là rotate RSA key.” | Vẫn là cùng private/public key material | Rotate key pair, cert và dữ liệu liên quan khi cần |
| “`String` password trong source là an toàn vì không in ra.” | Source/heap/history/decompiler có thể lộ secret | Secret manager, char[] khi phù hợp, hạn chế lifetime |
| “Dùng storepass null để bỏ lỗi integrity.” | Có thể bỏ xác thực toàn vẹn hoặc có hành vi khác | Giải quyết password/provider/corruption đúng cách |
| “Có nhiều entrypass là đã cô lập mọi service.” | Còn phụ thuộc quyền đọc file và secret injection | Least privilege, tách workload/KMS/HSM khi cần |
| “Chỉ backup `.p12` là đủ.” | Mất password/provider info có thể không recover | Backup an toàn credential, version, type, alias và test restore |

## 13. Checklist kiểm tra trước khi triển khai

1. **Đúng file/type/provider:** biết rõ JKS hay PKCS12 hay PKCS11? Đừng suy ra từ extension.
2. **Store password:** được cấp từ secret manager, đúng cho `load/store`, không log hoặc hardcode?
3. **Entry type:** alias cần dùng là `PrivateKeyEntry`, `SecretKeyEntry` hay `TrustedCertificateEntry`? Có chuỗi certificate khi cần TLS không?
4. **Key protection:** entry keypass/`ProtectionParameter` đã được xác định, provider hỗ trợ và đúng trong thao tác recover?
5. **Không đồng nhất khái niệm:** nếu storepass = keypass, có ghi rõ đây là quyết định cấu hình/tương thích, không gọi là hai bí mật độc lập?
6. **PKCS12 interoperability:** Java API, `keytool`, ứng dụng khác và version JDK có đồng ý cách bảo vệ entry không?
7. **TLS integration:** `KeyStore.load` và `KeyManagerFactory.init` nhận đúng password theo vai trò; `TrustManagerFactory` dùng đúng trust anchors?
8. **File/secret access:** IAM, file permissions, backup encryption và secret log/heap dump policy có hợp lý?
9. **Rotation:** tách đổi storepass, đổi entrypass và **rotate key material**; mỗi thao tác có test/rollback/backup?
10. **HSM/non-exportable:** đã dùng API provider phù hợp thay vì ép export key chưa?
11. **Negative tests:** thử sai storepass, sai keypass, alias sai, type sai, file corrupt, provider khác trong môi trường test?
12. **Recovery:** có thể khôi phục backup và thực hiện crypto/TLS operation thật với credentials được bảo quản hợp lệ?

## 14. Bài tập tự kiểm tra

**Câu 1.** `KeyStore.load(input, storePassword)` đã thành công. Có chắc `getKey("server", storePassword)` cũng thành công không?  
**Đáp án:** **Không**. Entry `server` có thể có keypass khác, không phải key entry, hoặc provider yêu cầu protection khác.

**Câu 2.** Hai AES keys `finance` và `audit` trong một PKCS12 có cùng storepass nhưng khác entrypass. Người chỉ biết finance password có thể luôn lấy audit key không?  
**Đáp án:** Không theo mô hình/provider bảo vệ entry riêng đã nêu. Nhưng khả năng cô lập thực tế còn phụ thuộc file access, quyền/provider và việc ai đang nắm các credentials.

**Câu 3.** `keytool -list` cho thấy certificate của server. Đó có phải bằng chứng private key đã recover được không?  
**Đáp án:** **Không.** Cần thử recover private key hoặc khởi tạo TLS key manager/handshake với đúng entry protection.

**Câu 4.** Một `TrustedCertificateEntry` có cần password riêng để đọc private key không?  
**Đáp án:** **Không**, bởi entry này không chứa private key. Truststore password phục vụ bảo vệ kho theo provider.

**Câu 5.** Tại sao có thể chạy code Java `setEntry(..., PasswordProtection(entryPass))` cho PKCS12 nhưng `keytool` lại cảnh báo khác storepass?  
**Đáp án:** Java `KeyStore` là API trừu tượng; implementation và từng luồng tool có giới hạn riêng. Không suy ra mọi tool hỗ trợ cùng cách per-entry protection.

**Câu 6.** Đổi store password nhưng không thay private key material. Certificate công khai phải đổi vì keypair đã khác chưa?  
**Đáp án:** **Không tự động.** Khóa mật mã chưa đổi; chỉ cơ chế bảo vệ kho được thay theo định dạng/provider. Nếu bị lộ private key thật, cần rotate keypair và certificate theo quy trình.

**Câu 7.** `KeyStore.getKey(alias, password)` trả `null`. Có nên thử thêm 1.000 password khác không?  
**Đáp án:** **Không.** Trước hết kiểm tra alias có tồn tại, `isKeyEntry` hay không; xử lý theo workflow được ủy quyền.

**Câu 8.** Trong HSM, `PrivateKey.getEncoded()` trả `null`. Điều đó có chứng minh khóa không hợp lệ không?  
**Đáp án:** **Không.** Khóa non-exportable có thể vẫn thực hiện `Signature`/`Cipher` qua provider/key handle được phép.

**Câu 9.** Một TLS server khai báo đúng storepass, nhưng `KeyManagerFactory.init` dùng nhầm storepass thay cho keypass. Triệu chứng?  
**Đáp án:** Có thể nạp kho được nhưng không khôi phục private key, khiến key manager/TLS không hoạt động. Phải sửa credential entry hoặc provider configuration.

**Câu 10.** Nếu storepass và keypass cùng một giá trị vì hệ thống yêu cầu tương thích, cần làm gì để giảm rủi ro?  
**Đáp án:** Quản lý credential đó như bí mật có quyền truy cập cao, giới hạn IAM/file access, rotate và backup an toàn; không giả vờ có hai ranh giới độc lập.

### Tài liệu tham khảo

- [Java SE 21 — KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): `load`, `store`, `getKey`, `setKeyEntry`, `getEntry`, `setEntry` và phạm vi password.
- [Java SE 21 — KeyStore.PasswordProtection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.PasswordProtection.html): bảo vệ entry bằng password và `destroy()`.
- [Java SE 21 — KeyStore.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.Builder.html): chọn provider/keystore, lấy protection parameter.
- [Java SE 21 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html): KeyStore, entry type, integrity và các API bảo mật.
- [Java SE 21 — keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): `-storepass`, `-keypass`, key migration và giới hạn công cụ.

### Ghi nhớ

**Store password phục vụ cấp độ kho; entry/key protection phục vụ một khóa cụ thể.** Cùng chuỗi password có thể được tái sử dụng trong một cấu hình, nhưng không biến hai vai trò thành một. Muốn chẩn đoán chính xác, hãy tách **`KeyStore.load/store`** khỏi **`getKey/getEntry/KeyManagerFactory`**, xác định **JKS/PKCS12/PKCS11 và provider**, rồi quản lý đúng secret, alias, key material và vòng đời của chúng.
