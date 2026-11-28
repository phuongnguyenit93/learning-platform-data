# Quản lý khóa, mật khẩu và cấu hình bí mật ngoài mã nguồn

Ứng dụng Java thường phải dùng mật khẩu kết nối cơ sở dữ liệu, token gọi API, khóa mã hóa, private key để ký số hoặc chứng chỉ TLS. Nếu đưa những giá trị này trực tiếp vào source, tài nguyên build hoặc cấu hình công khai, một lần lộ repository, artifact hay log có thể dẫn đến việc kẻ tấn công chiếm quyền truy cập vào nhiều hệ thống.

Giải pháp không đơn giản là “đổi chỗ đặt chuỗi bí mật”. Quản lý secrets đúng nghĩa đòi hỏi **tạo và cấp phát an toàn, lưu trữ riêng, cấp quyền tối thiểu, truy cập khi cần, giám sát, hết hạn, xoay vòng và thu hồi**. Đối với khóa mã hóa, còn phải giữ được khả năng giải mã dữ liệu cũ trong giai đoạn chuyển đổi; đối với mật khẩu **người dùng**, nguyên tắc lưu trữ lại là **băm thích ứng có salt**, không phải giữ mật khẩu để giải mã sau.

Bài học thuộc chương **Bảo mật ứng dụng Java** trong module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung tập trung vào các khả năng Java SE 27 đang được hỗ trợ (`java.security.KeyStore`, `javax.crypto`, `java.security.SecureRandom`, `SecretKeyFactory`, `PBEKeySpec`, `System.getenv`, `java.nio.file`) và các phương án vận hành hiện đại. Không sử dụng API mã hóa lỗi thời, thuật toán yếu, secret hardcoded hay cơ chế Java Security Manager cũ như lựa chọn thiết kế mới.

## 1. Phân loại đúng dữ liệu bí mật trước khi chọn cách bảo vệ

Những giá trị sau đều nhạy cảm nhưng **không thể xử lý giống nhau**:

| Loại dữ liệu | Ví dụ | Cách quản lý phù hợp |
| --- | --- | --- |
| **Mật khẩu người dùng để đăng nhập** | Password tài khoản | Lưu **password verifier** bằng thuật toán băm chậm có salt; không lưu plaintext và không cần giải mã |
| **Mật khẩu hoặc token dịch vụ** | DB password, API token | Secret manager, định danh workload, TTL và rotation; ứng dụng cần lấy plaintext/token tại thời điểm sử dụng |
| **Khóa mã hóa đối xứng** | AES data-encryption key | KMS/HSM hoặc keystore được bảo vệ; có key ID/version và quyền dùng khóa |
| **Private key bất đối xứng** | TLS private key, signing private key | KMS/HSM hoặc `KeyStore`/PKCS#12; hạn chế xuất key material |
| **Public key và chứng chỉ** | CA certificate, certificate public key | Không nhất thiết bí mật, nhưng phải bảo đảm tính xác thực/toàn vẹn và trust đúng nguồn |
| **Thông tin cấu hình không nhạy cảm** | URL dịch vụ, port, tên alias | Có thể đặt trong cấu hình thông thường, nhưng không gộp secret vào URL hoặc log |
| **Mã/token tạm thời** | OAuth access token, temporary database credential | TTL ngắn, phạm vi quyền tối thiểu, bảo vệ trong lưu trữ và truyền tải |

**Phân biệt ba trường hợp dễ nhầm:** Mật khẩu đăng nhập của người dùng phải **không thể khôi phục từ dữ liệu xác minh**; API token phải được gửi lại nguyên giá trị cho bên phát hành trong một số giao thức; private key cần được sử dụng cho phép toán mật mã nhưng lý tưởng không phải xuất thô vào bộ nhớ của ứng dụng.

### 1.1. Ví dụ anti-pattern: có bí mật trong code

```java
// KHÔNG làm như sau trong ứng dụng thực tế:
static final String DATABASE_PASSWORD = "example-password";
static final String PAYMENT_API_TOKEN = "example-api-token";
```

Vấn đề không chỉ là có người đọc được file `.java`. Những giá trị này có thể tồn tại trong Git history, bản sao CI, code review, compiled class, container image, crash dump và bản ghi phân phối. **Xóa một dòng khỏi commit mới không làm secret cũ biến mất khỏi lịch sử hoặc các bản đã sao chép.**

### 1.2. Cấu hình không chứa secret vẫn cần đúng mức tin cậy

Một cấu hình có thể chứa **tên hoặc tham chiếu** đến secret mà không chứa giá trị của nó:

```text
database.host=db.internal
database.user=orders_service
database.password-secret-id=prod/orders/db-password
crypto.active-key-id=orders-data-key-v4
```

Những tên trên là **giá trị minh họa**, không phải ID bí mật đang hoạt động. Secret manager, IAM và mạng thực tế mới quyết định ứng dụng nào được đọc secret tương ứng.

## 2. Mô hình đe dọa và các nguyên tắc nền tảng

Trước khi chọn file, environment variable hay KMS, hãy đặt câu hỏi: **kẻ tấn công có thể lấy secret ở đâu?** Các vị trí đáng quan tâm gồm:

- **Source/repository/history:** hardcoded secrets, pull request, commit cũ và fork.
- **CI/CD:** log, build cache, environment của job, artifact và quyền của runner.
- **Deployment:** container image layer, manifest, cấu hình orchestration và volume.
- **Runtime:** process environment, heap dump, diagnostic endpoints, exception message và profiler.
- **Mạng:** truyền secret thiếu TLS/xác thực máy chủ hoặc gửi tới điểm cuối sai.
- **Backups/replicas:** bản sao secret và key bị giữ lâu hơn chính sách.
- **Nhân sự/hạ tầng:** tài khoản cấp phát có quyền quá rộng hoặc không có audit.

Nguyên tắc thực hành:

1. **Least privilege:** mỗi dịch vụ có quyền đọc/dùng đúng secret cần thiết; database account chỉ có các quyền cần thiết.
2. **Separation of duties:** người được sửa code không tự động có quyền đọc mọi secret production.
3. **Short-lived credentials:** ưu tiên định danh workload và token/credential có vòng đời ngắn nếu hạ tầng hỗ trợ.
4. **Fail closed:** thiếu secret cần thiết thì khởi tạo thất bại có kiểm soát, không tự dùng mật khẩu demo hay tắt TLS.
5. **No plaintext exposure:** không in secret vào logs, metrics labels, stack traces, URL truy vấn hoặc exception messages.
6. **Rotation/revocation:** thiết kế khả năng đổi secret mà không phải sửa source hoặc build lại mã.
7. **Auditability:** ghi nhận **ai/yêu cầu nào đã truy cập phiên bản secret nào**, chứ không ghi secret value.

Tách **bí mật của hệ thống** khỏi **cấu hình hành vi không nhạy cảm** giúp giảm số người/công cụ phải tiếp cận dữ liệu có khả năng gây tổn thất.

## 3. Chọn nguồn cấp secret: từ môi trường tới KMS/HSM

Một số phương án thường gặp:

| Nguồn cấp | Tình huống phù hợp | Giới hạn/rủi ro cần kiểm soát |
| --- | --- | --- |
| **Secret manager** có API và IAM | Ứng dụng production, đa môi trường, rotation và audit | Phải bảo vệ workload identity, quyền truy cập, cache và đường truyền |
| **Workload identity + token ngắn hạn** | Cloud/orchestrator có cơ chế định danh máy chạy | Cần kiểm tra audience, expiry, scope, revocation và chính sách gia hạn |
| **Secret file được mount vào runtime** | Orchestrator/sidecar cấp file qua volume kiểm soát | Quyền file, mount chỉ đọc, cleanup và cập nhật file |
| **Environment variables** | Tích hợp đơn giản hoặc môi trường hạn chế lựa chọn | Dễ bị lộ qua process inspection/log/dump/deployment; thường khó rotate live |
| **PKCS#12 keystore** | File bảo vệ private key/certificate hoặc secret-key entry được provider hỗ trợ | Phải bảo vệ keystore password, filesystem, backup và quyền nạp khóa |
| **KMS/HSM** | Khóa quan trọng, cần audit/use-only/non-exportable | Chi phí, độ trễ, quyền truy cập và thiết kế availability |
| **Cấu hình trong repository** | Chỉ nên chứa **tên secret/reference**, không chứa value | Vẫn rà soát để tránh credential vô tình được nhúng |

**Khuyến nghị:** Với ứng dụng production, ưu tiên secret manager và **identity của workload** thay vì tệp mật khẩu dài hạn. Nếu không có, secret file được bảo vệ và cung cấp tại runtime là một lựa chọn. Environment variable có thể chấp nhận trong những deployment được kiểm soát, nhưng **không được mặc định xem nó là kho bí mật an toàn tuyệt đối**.

### 3.1. Environment variable: không hardcode, nhưng vẫn có rủi ro

```java
String token = System.getenv("APP_API_TOKEN");

if (token == null || token.isEmpty()) {
    throw new IllegalStateException("Required API token is unavailable");
}
```

Điểm tốt: source không có token, ứng dụng có thể được triển khai trong nhiều môi trường với giá trị khác nhau.

Điểm cần nhớ: `System.getenv` trả **`String` không thể chủ động xóa nội dung khỏi heap**; process environment có thể bị công cụ chẩn đoán, lỗi cấu hình hoặc process có quyền truy cập đọc được. Đừng log giá trị `token`, đừng thêm nó vào command-line arguments và đừng truyền môi trường quá rộng tới child processes.

Ví dụ đặt biến trong terminal hoặc secret-injection framework phụ thuộc hệ điều hành/deployment; **không commit lệnh shell kèm token thật** vào repository, lịch sử lệnh hay tài liệu nội bộ.

### 3.2. Secret mount file: để file ngoài image và source

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

static String readInjectedSecret(Path secretPath) throws IOException {
    String value = Files.readString(secretPath);
    if (value.isEmpty()) {
        throw new IOException("Injected secret is empty");
    }
    return value;
}
```

Ví dụ chỉ minh họa API đọc file. Đường dẫn phải do **môi trường đáng tin cậy** cấp, không nhận tự do từ user input; trong production cần giới hạn quyền file, mount, dung lượng và theo dõi sự thay đổi. `Files.readString` tạo một `String` có thể lưu trong heap; không có khả năng xóa chắc chắn như một buffer có thể chỉnh sửa.

**Không tùy tiện gọi `trim()` hoặc `strip()` lên mọi secret.** Một ký tự xuống dòng hoặc khoảng trắng có thể là thành phần có nghĩa của giá trị. Nếu secret file của nhà cung cấp có quy ước newline cuối file, hãy xử lý **đúng định dạng đã xác nhận**, không âm thầm thay đổi mọi whitespace.

### 3.3. Secret manager và workload identity

Một luồng triển khai nên có dạng:

```text
    Java service ở runtime
             |
     Workload identity
             |
      IAM/Policy check
             |
             v
       Secret manager
             |
    Phiên bản/lease/TTL
             |
             v
      Dùng trong phạm vi
      đã được cấp quyền
```

Secret manager không tự trở nên an toàn nếu một service account được cho phép đọc tất cả secrets. Cần giới hạn chính xác tên secret, version, môi trường, namespace và audit events. API SDK dùng để gọi secret manager **không phải một thành phần của Java SE**; mã cụ thể phụ thuộc nhà cung cấp và thư viện đã được đánh giá.

## 4. Thiết kế cấu hình: phân biệt secret reference và secret value

Thay vì cho business code biết nguồn chứa secret:

```java
interface ApiCredentialProvider {
    String currentToken();
}
```

Ứng dụng có thể có implementation lấy token từ secret manager, file hoặc environment. Tuy nhiên, **đừng tạo một abstraction chỉ để che đi vấn đề lifecycle**: cần xác định provider trả giá trị mới khi rotation hay cache giá trị cũ, khi nào refresh, ứng xử khi secret manager tạm lỗi và điều gì xảy ra với request đã bắt đầu.

Một cấu hình non-secret có thể chỉ chứa:

```text
payment.endpoint=https://payments.example.invalid
payment.credential-reference=prod/payments/credential
payment.request-timeout-ms=3000
```

`payment.credential-reference` là **tham chiếu** cho secret manager, không phải token. Các frameworks có thể hỗ trợ cú pháp thay thế biến cấu hình riêng, nhưng **Java SE không tự động mở rộng mọi placeholder** trong file `.properties` hoặc YAML; không dựa vào phép nội suy không tồn tại trong thư viện chuẩn.

### 4.1. Tránh fallback nguy hiểm

Không làm:

```java
// Sai: nếu production thiếu cấu hình sẽ dùng secret demo.
String password = System.getenv().getOrDefault(
        "APP_DB_PASSWORD", "test-password");
```

Thay bằng logic fail closed:

```java
String password = System.getenv("APP_DB_PASSWORD");
if (password == null || password.isEmpty()) {
    throw new IllegalStateException("Database credential not configured");
}
```

Nếu ứng dụng có chế độ development **cố ý không cần database**, hãy biểu diễn bằng **feature flag/test profile rõ ràng** và không tự chuyển chế độ khi thiếu secret.

## 5. Quản lý khóa mã hóa khác quản lý mật khẩu người dùng

**Khóa mã hóa** có nhiệm vụ trực tiếp mã hóa/giải mã hoặc ký/xác minh. Nếu xóa khóa cần thiết khi dữ liệu cũ chưa được chuyển đổi, ứng dụng có thể không còn đọc được dữ liệu. **Mật khẩu người dùng** dùng để xác minh danh tính: hệ thống không nên giữ một bản có thể khôi phục của mật khẩu để so sánh.

| Hoạt động | Khóa mã hóa/signing key | Mật khẩu người dùng |
| --- | --- | --- |
| Dữ liệu được lưu | Key material được bảo vệ, key reference/ID | Salt + password verifier + thuật toán/cost/version |
| Có cần khôi phục plaintext? | Có thể cần **sử dụng khóa** cho decrypt/sign, lý tưởng không xuất khóa | **Không** |
| Rotation | Key mới cho mã hóa/ký mới; hỗ trợ key cũ để giải mã/xác minh cần thiết | Rehash khi login/đổi password; không buộc người dùng đổi mật khẩu định kỳ vô lý |
| Bảo vệ truy cập | KMS/HSM/KeyStore, quyền riêng cho `encrypt`/`decrypt`/`sign` | Database verifier, rate limiting, authentication controls |
| Lộ dữ liệu | Có thể làm lộ plaintext đã mã hóa hoặc cho phép ký giả | Tạo nguy cơ offline guessing nếu verifier bị lấy |

Đừng cố “mã hóa mật khẩu người dùng rồi giải mã để đăng nhập”, hoặc “hash khóa AES rồi dùng hash làm khóa” mà không có thiết kế KDF và key lifecycle phù hợp.

## 6. Tạo khóa ngẫu nhiên đúng cách với JCA/JCE

Java SE cung cấp `java.security.SecureRandom` và các API `javax.crypto`. Với khóa AES được phần mềm quản lý, sử dụng `KeyGenerator` thay vì chọn chuỗi dễ nhớ:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey dataKey = generator.generateKey();

// Không in dataKey.getEncoded(); không commit key material.
```

`SecureRandom` là nguồn ngẫu nhiên dành cho mục đích mật mã. `java.util.Random` và `Math.random()` **không** thích hợp để tạo token bí mật, khóa hoặc salt an toàn.

**Cần phân biệt:** Khóa do phần mềm tạo trong JVM có thể xuất hiện trong bộ nhớ tiến trình; không thể gọi nó là *non-exportable*. Khi yêu cầu bảo vệ cao, dùng KMS/HSM hoặc provider có thể tạo và sử dụng khóa mà không cần trả raw key material cho ứng dụng.

### 6.1. Key ID, key purpose và metadata

Mỗi khóa nên có metadata để chọn đúng:

- **Purpose:** encrypt/decrypt, sign/verify, MAC; không tái sử dụng khóa cho mọi mục đích.
- **Owner/scope:** dịch vụ, tenant, môi trường, loại dữ liệu.
- **Key ID/version:** ví dụ `orders-data-v4`, không phải key material.
- **Created/activated/deactivated/retired:** lịch vòng đời.
- **Access policy:** ai có quyền dùng từng thao tác, không chỉ đọc toàn bộ khóa.

**Key ID có thể lưu cùng ciphertext** để chọn bản khóa đúng khi giải mã; key material phải ở khu vực được bảo vệ riêng.

## 7. `KeyStore` và PKCS#12: lưu private key, certificate và secret key

`java.security.KeyStore` là abstraction để quản lý các entries có tên (**alias**). Một keystore có thể giữ:

| Entry | Dữ liệu |
| --- | --- |
| `KeyStore.PrivateKeyEntry` | Private key và certificate chain |
| `KeyStore.SecretKeyEntry` | Một secret key được provider hỗ trợ |
| `KeyStore.TrustedCertificateEntry` | Chứng chỉ được tin cậy |

Kiểu **`PKCS12`** được yêu cầu hỗ trợ bởi nền tảng Java hiện đại. Với hệ thống mới cần file keystore tương thích, ưu tiên PKCS#12 thay vì mặc định các định dạng cũ chỉ vì ví dụ lịch sử dùng chúng.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

static KeyStore openPkcs12(
        Path path, char[] storePassword) throws Exception {

    KeyStore store = KeyStore.getInstance("PKCS12");
    try (InputStream in = Files.newInputStream(path)) {
        store.load(in, storePassword);
    }
    return store;
}
```

Đoạn code cần được đặt trong môi trường có **file keystore thật** và mật khẩu được cấp từ kênh bảo vệ. Với dữ liệu nhạy cảm, API production nên khai báo các exception cụ thể, tránh bắt rồi in nguyên stack trace có thể chứa thông tin triển khai.

### 7.1. Không đặt keystore và mật khẩu cùng chỗ không được bảo vệ

Nếu file `application.p12` được commit vào repository và password của nó cũng nằm trong `application.properties` trong cùng repository, việc “bọc khóa bằng PKCS#12” **không mang lại ranh giới bảo vệ hữu ích trước người có quyền đọc cả hai**.

Keystore cần quyền filesystem/mount chặt chẽ, bản sao lưu và cơ chế lấy mật khẩu độc lập (secret manager, protected runtime input, HSM/provider). Một PKCS#12 file không tự đem lại audit/rotation/least privilege như một KMS quản lý tập trung.

### 7.2. Đọc khóa theo alias, không in key material

```java
import java.security.Key;
import java.security.KeyStore;

Key key = store.getKey("orders-data-v4", keyPassword);
if (key == null) {
    throw new IllegalStateException("Required key alias is missing");
}
```

`store` và `keyPassword` là biến đã được cung cấp từ bước trước. `KeyStore.getKey` truy xuất khóa theo alias và thông tin bảo vệ entry. Đừng gọi `key.getEncoded()` để debug/log; nhiều loại key trong HSM/KMS có thể không cho phép xuất key material.

Với `KeyStore.PasswordProtection`, nên gọi `destroy()` khi hoàn tất nếu dùng object bảo vệ có khả năng hủy. Đối với `char[]`, có thể xóa buffer đầu vào do ứng dụng sở hữu sau khi sử dụng, nhưng điều đó **không đảm bảo xóa mọi bản sao** có thể tồn tại trong JVM/provider.

## 8. KMS/HSM và envelope encryption

Khi mã hóa dữ liệu quan trọng ở quy mô dịch vụ, một thiết kế thường dùng **envelope encryption**:

```text
                  Key Management Service
                    Master/KEK key
                          |
                wrap/unwrap data key
                          |
                          v
                Encrypted data key
                          |
      +-------------------+------------------+
      |                                      |
      v                                      v
   Ciphertext                           Key version
   + nonce/tag                           / key ID
      |
      v
   Database / object storage
```

- **KEK (Key Encryption Key):** khóa chính được bảo vệ trong KMS/HSM; policy quy định ai có quyền wrap/unwrap.
- **DEK (Data Encryption Key):** khóa mã hóa dữ liệu; có thể được tạo theo đối tượng/batch và được wrap bởi KEK.
- **Ciphertext envelope:** lưu ciphertext, tham số cần giải mã (nonce, tag), wrapped DEK, key ID/version và định dạng phiên bản.

Khi dùng một thuật toán mã hóa có xác thực như **AES-GCM**, mỗi lần mã hóa phải dùng **nonce/IV không trùng với cùng một khóa** theo quy tắc của thuật toán. Việc tái sử dụng nonce với cùng AES-GCM key có thể phá nghiêm trọng tính bảo mật và tính xác thực; không tạo nonce bằng hằng số cố định hoặc reset counter không có chiến lược.

Đừng tự viết thư viện mã hóa hoặc giao thức envelope từ đầu khi SDK KMS/provider đã có implementation được đánh giá. **Base64 chỉ mã hóa biểu diễn**, không phải mã hóa bảo mật; một wrapped key cũng không thay thế việc kiểm tra quyền sử dụng master key.

## 9. Mật khẩu người dùng: băm thích ứng có salt, không mã hóa để giải mã

Mật khẩu của một người dùng được nhập vào để **xác minh**, không phải để hệ thống gửi lại nguyên văn. Với mỗi tài khoản, lưu một **password verifier** được tạo bằng thuật toán băm mật khẩu có chi phí tính toán/memory đủ lớn và **salt ngẫu nhiên riêng**.

```text
Đăng ký:

  Password nhập qua kênh được bảo vệ
                  |
          Salt riêng, ngẫu nhiên
                  |
   Password hashing algorithm + cost
                  |
                  v
       [algorithm, cost, salt, hash]
                  |
               Database

Đăng nhập:

  Candidate password + salt + cost đã lưu
                  |
          Tính verifier mới
                  |
     So sánh hash có kiểm soát
                  |
           Xác minh đúng/sai
```

Không làm:

```java
// Không dùng SHA-256 đơn thuần để lưu mật khẩu người dùng:
// MessageDigest.getInstance("SHA-256").digest(passwordBytes);
```

Hash nhanh thông thường như SHA-256 không có cơ chế tăng chi phí thử mật khẩu phù hợp chống offline brute force. Dùng **Argon2id** cho hệ thống mới khi có implementation đáng tin cậy; cân nhắc **scrypt** nếu phù hợp. Nếu cần giải pháp chỉ với provider JDK hoặc yêu cầu tương thích/FIPS thích hợp, **PBKDF2-HMAC-SHA256** là lựa chọn vẫn được hỗ trợ, với thông số đủ mạnh.

### 9.1. Những thuật toán nào có sẵn trong Java SE 27?

| Thuật toán | Trong Java SE 27/JDK | Ghi chú |
| --- | --- | --- |
| `PBKDF2WithHmacSHA256` | Dùng qua `SecretKeyFactory` với provider hỗ trợ | Hướng đi thực tế cho ví dụ thuần JDK; cần salt và work factor |
| `Argon2id` | **Không phải API/algorithm chuẩn có sẵn mặc định trong Java SE** | Dùng thư viện/provider được kiểm định và bảo trì |
| `scrypt` | **Không phải JCA standard name được mọi JVM Java SE bảo đảm hỗ trợ** | Kiểm tra provider/thư viện cụ thể |
| `SHA-256` đơn thuần | Có trong JDK, nhưng **không thích hợp** để lưu password | Quá nhanh cho bài toán chống offline guessing |
| `MD5`/`SHA-1` đơn thuần | Không chọn cho password verifier mới | Thuật toán/ứng dụng không đáp ứng yêu cầu hiện đại |

Theo OWASP Password Storage Cheat Sheet tại thời điểm viết, tham số tối thiểu được hướng dẫn cho `PBKDF2-HMAC-SHA256` là **600.000 iterations**. Đây không phải một con số vĩnh viễn: cần theo dõi cập nhật OWASP, benchmark trên phần cứng/traffic thực tế và tăng cost khi hợp lý. Với `Argon2id`, cần cấu hình cả memory/time/parallelism, không chỉ một số iterations.

### 9.2. Tại sao salt không cần giấu?

Salt phải:

- Được tạo bằng `SecureRandom`.
- Đủ dài, ví dụ **16 byte** cho bản ghi mới.
- Khác nhau giữa các password records với xác suất va chạm rất thấp.
- Được lưu **cùng metadata verifier** để xác minh sau này.

Salt không phải “mật khẩu thứ hai” và không có nhiệm vụ bí mật. Một **pepper** nếu triển khai là secret bổ sung **phải được bảo vệ ngoài database** (thường bằng KMS/HSM/secret manager) và kéo theo bài toán rotation/khôi phục riêng; không chỉ thêm một chuỗi hardcoded vào trước mật khẩu rồi gọi đó là giải pháp toàn diện.

### 9.3. Verifier phải có phiên bản và work factor

Thay vì chỉ lưu `hash`, bản ghi nên chứa:

```text
algorithm | version | cost parameters | salt | derived hash
```

Khi nâng cost hoặc thay thuật toán, ứng dụng có thể nhận diện bản ghi cũ và **rehash sau lần xác thực thành công** (hoặc qua quy trình cập nhật phù hợp). Không cần yêu cầu tất cả người dùng đổi mật khẩu chỉ vì nâng cost nếu có cơ chế rehash thích hợp.

## 10. Ví dụ PBKDF2 với `PBEKeySpec`, `SecretKeyFactory` và `SecureRandom`

Đây là một implementation **minh họa cơ chế băm mật khẩu**, không phải toàn bộ hệ thống authentication. Nó dùng `PBKDF2WithHmacSHA256`, salt riêng và số iterations được định nghĩa rõ:

```java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

final class PasswordDerivation {
    private static final SecureRandom RNG = new SecureRandom();
    static final int ITERATIONS = 600_000; // Xem lại theo chính sách hiện hành.
    static final int KEY_BITS = 256;

    static byte[] newSalt() {
        byte[] salt = new byte[16];
        RNG.nextBytes(salt);
        return salt;
    }

    static byte[] derive(
            char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {

        PBEKeySpec spec = new PBEKeySpec(
                password, salt, iterations, KEY_BITS);
        try {
            SecretKeyFactory factory =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private PasswordDerivation() {}
}
```

Các điểm quan trọng:

- `SecureRandom` tạo salt mới cho **mỗi password record**.
- `PBEKeySpec` nhận `char[]` thay vì phải tạo `String` mới từ mật khẩu; nó sao chép thông tin cần thiết theo contract của API.
- `clearPassword()` xóa bản sao nội bộ của `PBEKeySpec` sau khi sử dụng; caller vẫn phải tự quản lý `char[]` gốc.
- `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` yêu cầu thuật toán hỗ trợ từ provider; cần kiểm thử runtime thực tế.
- `getEncoded()` trả một `byte[]` chứa **password verifier**; nó không phải plaintext password. Vẫn phải bảo vệ database, phân quyền đọc và ngăn offline guessing khi bị rò rỉ.
- `ITERATIONS` phải được **lưu cùng record**. Khi tăng work factor, không được dùng tham số mới để so trực tiếp với hash cũ mà không đọc metadata đã lưu.

**Không dùng cùng salt hoặc derived hash cho hai người dùng** như một “global key”. Không đổi `PBKDF2WithHmacSHA256` thành `PBKDF2WithHmacSHA1` chỉ để tương thích ví dụ cũ; với hệ thống mới, chọn một thuật toán/phương án được hỗ trợ và đáp ứng chính sách bảo mật hiện hành.

### 10.1. So sánh verifier và thời gian thực thi

Khi xác minh:

```java
import java.security.MessageDigest;
import java.util.Arrays;

byte[] candidateHash =
        PasswordDerivation.derive(candidate, savedSalt, savedIterations);
try {
    boolean matches = MessageDigest.isEqual(savedHash, candidateHash);
} finally {
    Arrays.fill(candidateHash, (byte) 0);
}
```

`candidate`, `savedSalt`, `savedIterations`, `savedHash` ở đây là các biến giả định được lấy từ luồng đăng nhập và bản ghi verifier đã lưu. `MessageDigest.isEqual` là lựa chọn so byte arrays có đặc tính thời gian phù hợp hơn việc dừng ngay tại byte khác đầu tiên; **nó không thay thế** rate limiting, phát hiện abuse và kiểm soát sự khác biệt giữa các error paths.

Đối với login endpoint, hashing là công việc tốn tài nguyên. Cần bảo vệ khỏi các yêu cầu xác minh ồ ạt, áp dụng rate limiting/abuse detection và giới hạn định dạng/dung lượng record khi parse. Không cho một hash record do người dùng tùy ý gửi ra quyết định số iterations cực lớn, khiến server bị từ chối dịch vụ.

### 10.2. `char[]` không phải phép xóa bí mật hoàn hảo

Java cho phép:

```java
char[] password = console.readPassword();
try {
    // Xác minh mật khẩu hoặc dùng ngay trong API hỗ trợ char[].
} finally {
    java.util.Arrays.fill(password, '\0');
}
```

Đây là **mảnh minh họa** chỉ hợp lệ khi `console` tồn tại và `readPassword()` không trả `null`. Xóa `char[]` giúp giảm thời gian tồn tại bản gốc trong buffer do ứng dụng quản lý; **không thể bảo đảm** xóa bản sao trong driver/provider, heap dump, JVM string hoặc native memory.

Trong ứng dụng web, framework có thể đã tạo `String` từ request body trước khi gọi code của bạn. Đừng tuyên bố “không dùng `String` là mật khẩu không thể bị đọc”. Điều cần làm là giảm bản sao và phạm vi sống, không in dữ liệu, cấu hình hạn chế heap dump và vận hành bảo mật.

## 11. Chính sách mật khẩu người dùng khác chính sách rotation của service secrets

Mật khẩu **người dùng** là một loại authenticator. Theo hướng dẫn NIST SP 800-63B-4 hiện đại:

- Không tự động bắt người dùng **đổi mật khẩu định kỳ** khi không có dấu hiệu compromise hoặc yêu cầu đặc biệt có cơ sở.
- Không ép các quy tắc thành phần cứng nhắc kiểu “phải có chữ hoa, số và ký tự đặc biệt” mà không xét khả năng dùng mật khẩu dài, passphrase và blocklist.
- Bảo vệ password submission bằng kênh xác thực an toàn; kiểm tra password strength/breached-password theo chính sách của hệ thống.
- Với **password-only authentication**, NIST có các yêu cầu độ dài tối thiểu cao hơn so với xác thực nhiều yếu tố; phải áp dụng theo assurance level và chính sách hiện hành.
- Password verifier phải được lưu bằng scheme có salt và cost phù hợp, không dùng plaintext hay hash nhanh.

Ngược lại, **service credentials**, API tokens và cryptographic keys có thể cần **hết hạn tự động, rotate theo chính sách, revoke ngay khi lộ**. Không áp dụng máy móc quy tắc “không buộc đổi mật khẩu định kỳ” của người dùng vào service API key dài hạn.

### 11.1. Không tạo password reset bằng cách gửi mật khẩu cũ

Vì hệ thống không lưu password có thể giải mã, quy trình reset phải **đặt verifier mới** sau bước xác minh danh tính/authorization thích hợp. Không cung cấp chức năng “xem lại mật khẩu hiện tại” từ database; nếu có khả năng xem lại, hệ thống đang giữ thứ cần loại bỏ.

## 12. Secrets lifecycle: tạo, cấp phát, sử dụng, rotation và thu hồi

Một secret có vòng đời:

```text
Tạo an toàn
    |
    v
Đăng ký metadata / ownership
    |
    v
Cấp phát cho workload được ủy quyền
    |
    v
Đọc/sử dụng trong scope tối thiểu
    |
    +---- Giám sát usage / audit
    |
    v
Rotate / gia hạn lease
    |
    +---- Cập nhật consumer & xác minh
    |
    v
Revoke / ngừng sử dụng / hủy theo retention
```

Các yêu cầu:

1. **Creation:** dùng generator phù hợp, entropy đáp ứng mục đích; không đặt password bằng tên hệ thống + ngày.
2. **Provisioning:** cấp cho workload bằng IAM/secret manager hoặc kênh an toàn được kiểm soát.
3. **Use:** chỉ giữ trong bộ nhớ khi cần; không đưa vào message bus/logs/métrics hay exception.
4. **Rotation:** chuẩn bị secret mới, cho phép consumers chuyển sang, xác nhận hoạt động, rồi vô hiệu hóa secret cũ theo cửa sổ được kiểm soát.
5. **Revocation:** nếu có dấu hiệu compromise, thu hồi nhanh; không chờ chu kỳ rotate bình thường.
6. **Backup/recovery:** lưu ý dữ liệu mã hóa cũ còn phụ thuộc khóa cũ; backup key material phải được bảo vệ ít nhất tương đương dữ liệu.
7. **Auditing:** lưu ai truy cập secret ID/version, kết quả và thời điểm; không lưu secret value.

### 12.1. Rotation của API token với khoảng chuyển tiếp

Với hệ thống cho phép hai phiên bản cùng lúc:

```text
Phase A: v1 active, v2 chưa cấp
Phase B: cấp v2; consumer mới sử dụng v2
Phase C: quan sát consumer còn dùng v1
Phase D: revoke v1 sau khi xác minh chuyển đổi
```

Không phải mọi provider cho phép hai tokens cùng hoạt động. Nếu chỉ cho phép một token, cần kế hoạch cutover phù hợp khả năng của hệ thống, retry an toàn và fallback **không tái sử dụng secret đã bị thu hồi**.

### 12.2. Rotation của khóa mã hóa không giống token

Khi chuyển từ `key-v3` sang `key-v4`:

- **Encrypt mới bằng v4** kể từ thời điểm active.
- **Decrypt dữ liệu cũ bằng v3** trong thời gian cần thiết, dựa vào key ID lưu cùng ciphertext.
- Re-encrypt/migrate dữ liệu cũ nếu chính sách yêu cầu.
- Chỉ vô hiệu hóa/xóa v3 sau khi không còn dữ liệu hợp lệ cần nó và đã kiểm tra backup/recovery.

Đừng xóa key cũ ngay sau khi tạo key mới rồi phát hiện bản sao lưu hoặc dữ liệu cũ không thể giải mã.

### 12.3. Dynamic credentials

Một secret manager có thể phát hành **database credentials có lease ngắn**, sau đó gia hạn/thu hồi. Khi thời hạn thay đổi, ứng dụng phải biết cách refresh secret, tạo kết nối mới và loại bỏ kết nối mang credentials cũ theo cơ chế pool/driver.

Không giả định `System.getenv("DB_PASSWORD")` sẽ tự cập nhật khi secret manager rotate một giá trị mới. Thông thường process environment đã có khi khởi chạy; runtime reload cần được **thiết kế riêng**.

## 13. Thời điểm nạp secret: startup, request-time hay background refresh?

| Cách nạp | Lợi ích | Cần kiểm soát |
| --- | --- | --- |
| **Startup-only** | Đơn giản; fail-fast trước khi nhận traffic | Rotation thường đòi restart/deploy lại |
| **On-demand** | Có thể lấy bản mới khi cần | Tăng latency/dependency availability, tránh gọi secret store cho mọi byte dữ liệu |
| **Cached + refresh** | Cân bằng tốc độ và cập nhật | TTL, stale-cache policy, đồng bộ cạnh tranh, xử lý lỗi refresh |
| **Provider/KMS use-only** | Không cần xuất raw key | Rate limit, latency, quota, IAM, kế hoạch khi KMS không sẵn |

Chọn theo yêu cầu uptime, frequency rotate và mức độ nhạy cảm. Đừng cache plaintext secret **vô hạn**, nhưng cũng đừng gọi secret store hàng nghìn lần cho cùng một request nếu đó là bottleneck và không cần thiết.

### 13.1. Không leak qua log hoặc exception

```java
try {
    String secret = credentialProvider.currentToken();
    sendAuthorizedRequest(secret);
} catch (CredentialUnavailableException ex) {
    // Không in secret value hoặc toàn bộ nội dung cấu hình.
    logger.warn("Credential unavailable for payment integration");
    throw ex;
}
```

Đoạn trên chỉ minh họa pattern; `credentialProvider`, `sendAuthorizedRequest`, `CredentialUnavailableException` và `logger` là thành phần của ứng dụng/framework, không phải API chuẩn để copy chạy nguyên đoạn.

Không dùng:

```java
// Nguy hiểm nếu exception hoặc config có chứa token:
// logger.error("Failed with token {}", token);
// throw new IllegalStateException("Bad credential: " + password);
```

Redaction phải được kiểm thử ở **HTTP clients, logs, tracing, APM, error reporting và crash dumps**; chỉ tự tránh `System.out.println(secret)` là chưa đủ.

## 14. CI/CD, container images và repository

Để secret thật sự **nằm ngoài mã nguồn**, cần kiểm soát cả pipeline:

- Không ghi secret vào `Dockerfile` bằng `ARG`/`ENV` cố định; giá trị có thể xuất hiện trong image layers, build metadata hoặc pipeline logs.
- Không bake `.env`, keystore password hay credentials file vào final container image.
- Với CI jobs, cấp secret theo **job identity** và chỉ cho jobs cần dùng; hạn chế PR/fork không tin cậy tiếp cận production secrets.
- Không echo biến bí mật qua shell tracing hoặc in full HTTP headers.
- Dùng secret scanning trước commit và trong repository, kiểm tra cả artifacts và images nếu hạ tầng hỗ trợ.
- Với file mount, thiết lập permission/ownership, mount read-only khi phù hợp, và giới hạn đường dẫn mà workload có thể đọc.
- Bảo vệ dữ liệu backups, cache, test reports và crash dumps theo cùng mức nhạy cảm.

`.gitignore` chỉ ngăn một file chưa được track được thêm vào Git theo quy tắc; nó **không xóa** nội dung đã commit trước đó và không thay thế secret scanning hoặc IAM. Nếu secret đã xuất hiện trong commit, coi secret đó có nguy cơ bị lộ.

### 14.1. Cấu hình Kubernetes hoặc orchestrator không tự là bảo đảm bảo mật

Một orchestrator có thể cấp secret dưới dạng environment variable hoặc volume. Cơ chế phân phối **không tự có nghĩa** secret được mã hóa an toàn at rest, không xuất hiện trong audit/log hoặc chỉ người phù hợp mới đọc được.

Phải xét encryption at rest của backend, RBAC/identity, quyền mount, segmentation và rotation. Khi thích hợp, tích hợp external secret manager/CSI/sidecar theo khuyến nghị của hạ tầng đang sử dụng.

## 15. Phát hiện lộ secret và ứng phó sự cố

Khi thấy một token/khóa/mật khẩu thật xuất hiện trong Git, logs hoặc ticket:

1. **Khoanh vùng và đánh giá phạm vi lộ:** loại secret, quyền, môi trường, hệ thống bị ảnh hưởng.
2. **Revoke/rotate càng sớm càng tốt** theo quy trình incident response; ngăn sử dụng credential cũ.
3. **Cấp và phân phối secret mới** bằng kênh bảo vệ, cập nhật consumers và xác minh hoạt động.
4. **Kiểm tra audit logs** để nhận diện việc sử dụng bất thường.
5. **Loại bỏ bản sao lộ lọt** trong logs, artifacts, caches, tài liệu và VCS history theo chính sách tổ chức, nhưng **không coi xóa history là thay thế revocation**.
6. **Khôi phục phòng ngừa:** thêm detector, giảm quyền và điều chỉnh vòng đời để ngăn tái diễn.

Với **encryption key** bị lộ, tác động có thể vượt phạm vi future requests: dữ liệu cũ mã hóa bằng key đó có thể cần được đánh giá, tái mã hóa hoặc thay đổi chiến lược bảo vệ. Với signing key, có thể cần vô hiệu hóa hoặc xem xét chữ ký/token đã phát hành.

Đừng tự dán secret bị nghi lộ vào công cụ phân tích công khai, issue tracker hoặc các cuộc chat không được phép; thay vào đó sử dụng kênh incident-response được tổ chức phê duyệt.

## 16. Mẫu triển khai Java: nạp secret từ file được cấp tại runtime

Đối với deployment dùng secret file từ orchestrator hoặc sidecar, business code không nên biết nội dung bí mật ở thời điểm build. Một abstraction đơn giản có thể nhận **đường dẫn được cấp bởi môi trường đáng tin cậy** và chỉ mở file khi cần:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Objects;

final class FileSecretSource {
    private final Path path;

    FileSecretSource(Path path) {
        this.path = Objects.requireNonNull(path);
    }

    byte[] readBytes() throws IOException {
        // Giới hạn minh họa; file thực phải do deployment tin cậy kiểm soát.
        long size = Files.size(path);
        if (size == 0 || size > 64 * 1024) {
            throw new IOException("Invalid secret file size");
        }
        byte[] secret = Files.readAllBytes(path);
        if (secret.length == 0 || secret.length > 64 * 1024) {
            Arrays.fill(secret, (byte) 0);
            throw new IOException("Invalid secret file content size");
        }
        return secret; // Caller sở hữu buffer và phải xóa khi dùng xong.
    }
}
```

Sử dụng:

```java
byte[] secret = source.readBytes();
try {
    // Truyền qua API hỗ trợ byte[], không in/log secret.
    consumeSecret(secret);
} finally {
    Arrays.fill(secret, (byte) 0);
}
```

`source` và `consumeSecret` là các thành phần giả định. Đặc biệt, **đừng biến code kiểm tra kích thước trên thành sandbox bảo mật khi người dùng có thể thay đổi đường dẫn**: kiểm tra bằng `Files.size` rồi đọc có thể gặp race, symlink hoặc thay đổi nội dung; đường dẫn/mount phải được bảo vệ ở lớp deployment.

Nếu một thư viện chỉ nhận `String`, có thể phải giải mã secret bytes thành chuỗi rồi dùng nó. Điều đó tạo thêm bản sao không xóa được chủ động; quản lý scope và thời gian sống, không giả vờ việc xóa `byte[]` bảo đảm xóa mọi representation.

### 16.1. File permissions và secret refresh

Không chỉ quan tâm `readBytes()`:

- Chỉ tiến trình/phần mềm có danh tính phù hợp được quyền đọc file.
- Mount secret vào đường dẫn riêng, không chia sẻ với workloads không liên quan.
- Không đưa file vào backup hoặc artifact công khai; xác định chính sách backup rõ ràng.
- Khi secret được update bằng atomic file replacement hoặc cơ chế riêng của orchestrator, ứng dụng phải **đọc lại/refresh** theo contract đã chọn.
- Nếu secret file bị thiếu hoặc không đọc được, **fail closed**; không tìm một secret mặc định trong source.

## 17. Mẫu PKCS#12: nhận password từ kênh khác, đọc key theo alias

Khi cần một private/secret key được lưu trong file keystore đã được provision, có thể tách **vị trí keystore** (không phải secret) khỏi **mật khẩu mở keystore** và **mật khẩu entry**.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;

static Key readRequiredKey(
        Path keystoreFile,
        char[] storePassword,
        char[] keyPassword,
        String alias) throws Exception {

    KeyStore store = KeyStore.getInstance("PKCS12");
    try (InputStream in = Files.newInputStream(keystoreFile)) {
        store.load(in, storePassword);
    }

    Key key = store.getKey(alias, keyPassword);
    if (key == null) {
        throw new IllegalStateException("Required key alias not found");
    }
    return key;
}
```

Ví dụ **không hardcode** password; caller lấy từ secret manager, console tương tác hoặc kênh cấp phát đã bảo vệ, rồi xóa buffers `char[]` đầu vào khi không cần nữa. Các implementations có thể hỗ trợ hoặc giới hạn việc tách mật khẩu entry khỏi mật khẩu store; cần kiểm thử bằng provider/format thực tế.

**Không làm**:

```java
// Không đọc password thật từ file trong repository:
// char[] password = "changeit".toCharArray();
// KeyStore store = KeyStore.getInstance("JKS");
```

`"changeit"` ở đây chỉ là chuỗi ví dụ để minh họa một anti-pattern, **không phải giá trị mặc định an toàn** cho mọi ứng dụng. Chọn loại keystore phù hợp; trong code mới dựa vào file, PKCS#12 là định dạng được nền tảng bảo đảm hỗ trợ.

### 17.1. TLS keystore khác truststore

Trong kết nối TLS, có thể cần:

- **Keystore của client/server**: chứa private key và certificate chain cho danh tính TLS.
- **Truststore**: chứa các CA/certificate được tin để **xác minh đối tác**.

Truststore không nhất thiết chứa secret, nhưng việc **thay đổi trust anchors** rất nhạy cảm. Không vô hiệu hóa xác minh chứng chỉ hoặc hostname verification để “sửa” lỗi cấu hình; phải sửa trust chain, danh tính certificate và cấu hình TLS đúng nguồn.

Một `KeyStore` chứa private key không tự cấu hình toàn bộ `SSLContext` hoặc quyền truy cập mạng. Thiết lập TLS còn cần `KeyManager`/`TrustManager` phù hợp và chính sách xác thực.

### 17.2. Ưu tiên ký/giải mã ở phía HSM/KMS khi chính sách đòi hỏi

Một private key đặc biệt quan trọng có thể được sử dụng qua provider KMS/HSM mà không cho application lấy `getEncoded()`. Nếu dịch vụ chỉ cần **ký một payload**, có thể cấp quyền `sign` thay vì quyền **đọc/xuất khóa**. Đây là biện pháp giảm blast radius khi application process bị compromise, dù vẫn cần bảo vệ quyền gọi API ký và kiểm soát quota.

## 18. Phân lớp phòng thủ theo môi trường triển khai

| Lớp | Câu hỏi | Biện pháp |
| --- | --- | --- |
| Source/build | Có secret trong Git hoặc image? | Không hardcode, secret scanning, loại khỏi artifacts |
| Identity | Ai được cấp secret? | Workload identity, least-privilege IAM và audit |
| Storage | Secret nằm ở đâu? | KMS/HSM/secret manager/volume bảo vệ, encryption at rest |
| Network | Secret đi tới đâu? | TLS xác thực đúng peer, hạn chế egress |
| Runtime | Khi nào secret được giữ trong bộ nhớ? | Scope ngắn, tránh log/heap dump, giảm bản sao |
| Application | Code làm gì khi secret không có? | Fail closed, không dùng fallback demo |
| Rotation | Khi secret thay đổi, ứng dụng xử lý ra sao? | TTL/cache refresh, versioned credentials và cutover |
| Incident | Nếu lộ secret, có thu hồi được ngay? | Quy trình revoke, rotate, audit và kiểm tra ảnh hưởng |
| Backup | Dữ liệu/khóa trong backup có còn được bảo vệ? | Quyền riêng, key retention và recovery drills |

### 18.1. Ưu tiên identity thay vì static credentials khi có thể

Nếu hạ tầng hỗ trợ managed identity, workload federation hoặc token có hạn, ứng dụng có thể đổi **quyền truy cập thông qua identity** lấy token mà không cần có một DB password tĩnh lưu hàng tháng trong repository hoặc deployment.

Điều này không loại bỏ mọi rủi ro: người chiếm được workload identity hoặc token đang còn hiệu lực vẫn có thể thao tác trong phạm vi được cấp. Vì vậy cần chính sách audience/scope, TTL, audit và egress thích hợp.

### 18.2. Cân bằng availability và security

Khi secret manager gặp lỗi:

- **Không** tự chuyển sang secret hardcoded trong source.
- Có thể sử dụng **bản cache còn hiệu lực** nếu chính sách cho phép, nhưng không gia hạn vô hạn một secret đã hết hạn hoặc bị thu hồi.
- Theo dõi lỗi và tăng khả năng phục hồi của secret provider theo SLO.
- Với KMS, phải thiết kế retry/backoff có giới hạn, tránh storm tới hệ thống quản lý khóa.

Việc fail closed có thể khiến một tính năng tạm dừng, nhưng đôi khi đó là hành vi bắt buộc để tránh truy cập trái phép hoặc dùng khóa không còn hợp lệ.

## 19. Ví dụ `Demo.java` chạy độc lập: không hardcode secret và băm password

Ví dụ sau dùng **chỉ API Java SE 27**. Nó có hai phần độc lập:

1. Nếu có biến môi trường `DEMO_SECRET_FILE`, đọc một secret file bên ngoài source rồi **chỉ thông báo thành công**, tuyệt đối không in giá trị.
2. Nếu chạy trong terminal tương tác, nhập password qua `Console.readPassword`, tạo salt bằng `SecureRandom`, dẫn xuất verifier bằng PBKDF2 và kiểm tra password nhập lần hai.

Nếu không cấu hình file và không có interactive console, chương trình **vẫn chạy được**, nhưng bỏ qua các phần chưa có input. Không có mật khẩu hoặc token mặc định bên trong source.

```java
import java.io.Console;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class Demo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int ITERATIONS = 600_000;
    private static final int KEY_BITS = 256;

    private static byte[] derive(char[] password, byte[] salt)
            throws GeneralSecurityException {

        PBEKeySpec spec = new PBEKeySpec(
                password, salt, ITERATIONS, KEY_BITS);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance(
                    "PBKDF2WithHmacSHA256");
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static void demonstrateExternalFile() throws Exception {
        String name = System.getenv("DEMO_SECRET_FILE");
        if (name == null || name.isBlank()) {
            System.out.println("External secret file not configured.");
            return;
        }

        // Đường dẫn do deployment tin cậy cấp, không lấy từ web request.
        Path path = Path.of(name);
        if (Files.size(path) == 0 || Files.size(path) > 64 * 1024) {
            throw new IllegalStateException("Invalid external secret file");
        }

        byte[] secret = Files.readAllBytes(path);
        try {
            if (secret.length == 0 || secret.length > 64 * 1024) {
                throw new IllegalStateException("Invalid secret size");
            }
            System.out.println("External secret loaded (value withheld).");
        } finally {
            Arrays.fill(secret, (byte) 0);
        }
    }

    private static void demonstratePassword() throws Exception {
        Console console = System.console();
        if (console == null) {
            System.out.println("No interactive console; password demo skipped.");
            return;
        }

        char[] first = console.readPassword("Create demo password: ");
        char[] second = null;
        byte[] storedHash = null;
        byte[] candidateHash = null;

        try {
            if (first == null || first.length == 0) {
                System.out.println("No password provided; demo skipped.");
                return;
            }

            byte[] salt = new byte[16];
            RNG.nextBytes(salt);
            storedHash = derive(first, salt);

            second = console.readPassword("Repeat demo password: ");
            if (second == null) {
                System.out.println("No verification password; skipped.");
                return;
            }

            candidateHash = derive(second, salt);
            boolean matches =
                    MessageDigest.isEqual(storedHash, candidateHash);

            System.out.println("Password verification: " + matches);
            // Demo không persist verifier; production phải lưu
            // algorithm/version/iterations/salt/hash một cách có bảo vệ.
        } finally {
            if (first != null) Arrays.fill(first, '\0');
            if (second != null) Arrays.fill(second, '\0');
            if (storedHash != null) Arrays.fill(storedHash, (byte) 0);
            if (candidateHash != null) Arrays.fill(candidateHash, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        demonstrateExternalFile();
        demonstratePassword();
    }
}
```

Biên dịch và chạy:

```shell
javac Demo.java
java Demo
```

Khi không có biến `DEMO_SECRET_FILE` và chạy trong môi trường không cung cấp console:

```text
External secret file not configured.
No interactive console; password demo skipped.
```

Khi chạy trong terminal thật và nhập password giống nhau hai lần, phần thứ hai in:

```text
Password verification: true
```

Chương trình **không in password, salt hoặc secret value**. Nếu hai lần nhập khác nhau, `Password verification: false`. Việc đo `Files.size` và đọc bytes là minh họa cho **đường dẫn được quản trị**, không phải giải pháp chấp nhận path tùy ý từ người dùng.

**Phạm vi của demo:** không có account database, login throttling, brute-force defense, Argon2id provider, secret manager SDK, lưu verifier, KMS hoặc mã hóa dữ liệu thật. Những thành phần đó cần được bổ sung và kiểm thử theo kiến trúc/security policy của sản phẩm.

## 20. Những lỗi triển khai thường gặp

| Cách làm | Vì sao rủi ro | Cách xử lý |
| --- | --- | --- |
| Đưa password, API key hoặc private key vào `static final String` | Secret nằm trong source/build/Git history | Cấp từ secret manager, KMS hoặc runtime mount |
| Commit file `.env` hay keystore password vào Git | Phân phối secret rộng ngoài ý muốn | Cấu hình runtime được bảo vệ |
| Đưa secret vào `Dockerfile ENV/ARG` cố định | Có thể xuất hiện trong image layers/metadata | Inject tại runtime, không bake vào image |
| Coi environment variable là nơi bí mật tuyệt đối | Có thể lộ qua process/dump/log | Ưu tiên secret manager/mount và giới hạn quyền |
| Bọc secret bằng Base64 rồi ghi vào YAML | Base64 đảo ngược được, không có tính bí mật | Secret storage/encryption thật |
| Lưu file keystore và password của nó cùng repository | Kẻ đọc repo có cả hai thành phần | Bảo vệ độc lập key store và unlock credential |
| Lưu mật khẩu người dùng có thể giải mã | Khi DB/key lộ, plaintext password bị lộ | Băm password chậm có salt |
| Lưu password bằng `SHA-256` đơn thuần | Offline guessing quá nhanh | Argon2id hoặc PBKDF2 có cost phù hợp |
| Dùng cùng salt cố định cho mọi tài khoản | Tăng khả năng phân tích/reuse công sức cracking | Salt ngẫu nhiên riêng mỗi verifier |
| Sử dụng `java.util.Random` để tạo key/token | Không phải nguồn entropy dành cho mật mã | `SecureRandom`/`KeyGenerator` |
| Dùng key AES và IV/nonce cố định cho AES-GCM | Nguy cơ mất bảo mật nghiêm trọng | Nonce duy nhất theo key; dùng thư viện/provider kiểm định |
| Tự thiết kế “mã hóa” XOR/ECB | Thiếu bảo vệ toàn vẹn hoặc dễ phân tích | AEAD hiện đại như AES-GCM qua provider phù hợp |
| Tự động xóa mọi key cũ sau rotation | Dữ liệu mã hóa cũ không giải mã được | Versioned keys, migration và key-retention policy |
| Log nguyên token hoặc exception chứa credential | Lộ qua logging/APM/tracing | Redaction, kiểm soát output và audit |
| Tắt TLS/certificate validation khi truy cập secret store | Dễ bị đánh tráo endpoint hoặc nghe lén | Xác minh đúng peer và trust chain |
| Hardcode fallback `"test-password"` khi thiếu secret | Production có thể khởi động bằng secret yếu | Fail closed |
| Chỉ dùng `.gitignore` để “khắc phục” secret đã commit | Git history và bản sao vẫn tồn tại | Revoke/rotate và xử lý bản sao bị lộ |
| Coi reset password là đọc lại plaintext cũ | Cho thấy verifier được thiết kế sai | Xác minh danh tính rồi tạo verifier mới |
| Chuyển mọi secret sang một IAM role toàn quyền | Tăng blast radius khi một workload bị chiếm | Least privilege theo dịch vụ và mục đích |
| Coi `char[]` xóa mọi dấu vết của password | Provider/heap có thể giữ bản sao | Giảm scope và copies, bảo vệ runtime |

## 21. Checklist review trước khi triển khai

1. **Đã phân biệt mật khẩu người dùng, service credentials và cryptographic keys chưa?** Không áp cùng một cơ chế cho cả ba.
2. **Source, repository, build và container image có hoàn toàn không chứa secret thật không?**
3. **Runtime nhận secret bằng identity được ủy quyền hay kênh được bảo vệ không?** Không dùng secret fallback trong source.
4. **Quyền IAM có giới hạn theo workload, môi trường, secret ID và action không?**
5. **Có cơ chế rotate/revoke, audit và xử lý secret bị lộ không?**
6. **Mật khẩu người dùng có được lưu dạng salted adaptive password verifier không?** Có algorithm/cost/version để nâng cấp?
7. **Có dùng `SecureRandom` và key generation phù hợp không?** Không dùng `Random` hoặc chuỗi dễ đoán.
8. **Khóa quan trọng có được giữ trong KMS/HSM/keystore bảo vệ không?** Có key ID và quyền sử dụng phù hợp?
9. **Với encryption rotation, có giữ khả năng decrypt ciphertext cũ theo chính sách không?**
10. **AES-GCM hoặc AEAD tương đương có chính sách nonce không trùng với cùng key không?**
11. **Keystore password và file keystore có được bảo vệ độc lập không?**
12. **Secret file có permission, mount và đường dẫn từ deployment đáng tin cậy không?**
13. **Có xử lý secret refresh/TTL và failure của secret store không?** Không cache vô hạn secret đã hết hiệu lực.
14. **Logs, traces, metrics, debug endpoints và heap dumps có thể lộ secrets không?** Đã kiểm thử redaction?
15. **Tất cả giao tiếp nhận/trả secret có TLS và xác thực endpoint đúng không?**
16. **CI jobs từ forks/PRs không tin cậy có bị chặn khỏi production secrets không?**
17. **Secrets trong backups/artifacts và quá trình disaster recovery có cùng mức bảo vệ không?**
18. **Có tests cho thiếu secret, quyền bị từ chối, rotation, revoked secret và provider outage không?**
19. **Các lựa chọn mật mã/phương pháp hash có được cập nhật theo OWASP/NIST và policy hiện hành không?**
20. **Mã ứng dụng có thể thay đổi nguồn cấp secret mà không sửa business logic hoặc in secret không?**

## 22. Tổng kết

Trong Java SE 27, **đưa secret ra ngoài mã nguồn** là bước đầu nhưng chưa đủ. Một thiết kế tốt cần phân loại đúng **password verifier**, **service credential** và **cryptographic key**, sau đó cấp phát và sử dụng từng loại bằng đúng kênh đã bảo vệ.

Với ứng dụng production, ưu tiên **workload identity, secret manager và KMS/HSM**; `KeyStore` với PKCS#12 là một abstraction được hỗ trợ cho lưu trữ khóa/chứng chỉ khi cần file hoặc provider cụ thể. Nếu phải dùng environment variable hoặc secret file mount, cần kiểm soát quyền, log, rotation và giới hạn thời gian secret tồn tại trong memory.

Đối với mật khẩu người dùng, dùng **password hashing có salt và work factor**, ưu tiên Argon2id qua implementation được kiểm định hoặc PBKDF2-HMAC-SHA256 với provider JDK khi phù hợp. Không lưu plaintext, không dùng hash nhanh thuần túy và không áp dụng quy tắc đổi password định kỳ máy móc cho người dùng.

Với khóa mã hóa, cần **quản lý key ID/version**, kiểm soát quyền và vòng đời, duy trì khả năng dùng khóa cũ trong thời gian chuyển đổi, đồng thời tránh giải pháp mật mã tự chế. Việc quản lý secrets chỉ hoàn chỉnh khi hệ thống đã có **auditing, rotation, revocation, incident response và kiểm soát CI/CD/runtime**.

## Tài liệu tham khảo

- [Java SE 27 — KeyStore](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/KeyStore.html) — PKCS12, private/secret key entries, load và `getKey`.
- [Java SE 27 — SecureRandom](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/SecureRandom.html) — nguồn ngẫu nhiên mật mã.
- [Java SE 27 — KeyGenerator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/KeyGenerator.html) — sinh khóa đối xứng.
- [Java SE 27 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/SecretKeyFactory.html) — dẫn xuất key/verifier dựa trên password.
- [Java SE 27 — PBEKeySpec](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html) — salt, iterations, `char[]` và `clearPassword`.
- [Java SE 27 — MessageDigest](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/MessageDigest.html) — `isEqual` để so sánh verifier bytes.
- [Java SE 27 — Cipher](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/Cipher.html) và [GCMParameterSpec](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html) — AEAD/AES-GCM và tham số nonce/tag.
- [Java SE 27 — Console](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/Console.html) — `readPassword` trong terminal tương tác.
- [Java SE 27 — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html) — đọc secret file được cấp từ môi trường tin cậy.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — lifecycle, identity, rotation, logging, CI/CD và incident response.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — Argon2id, scrypt, PBKDF2, salt và work factor.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html) — xác minh mật khẩu, độ dài/chính sách authenticator và bảo vệ verifier.
