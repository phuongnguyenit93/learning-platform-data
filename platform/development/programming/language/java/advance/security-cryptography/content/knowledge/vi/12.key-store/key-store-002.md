# 12.2 PrivateKeyEntry, SecretKeyEntry, TrustedCertificateEntry và alias

**Java KeyStore** (`java.security.KeyStore`) là một API quản lý các **entry mật mã có tên** trong một kho khóa: khóa riêng cùng chuỗi chứng chỉ, khóa bí mật đối xứng, hoặc chứng chỉ công khai được lưu riêng để làm điểm tin cậy. Mỗi entry được tìm qua **alias**. Việc hiểu sai loại entry thường gây lỗi TLS, không đọc được private key, ghi đè alias, hoặc nhầm một certificate đơn lẻ với một danh tính có private key.

Bài học này phân biệt rõ **`KeyStore.PrivateKeyEntry`**, **`KeyStore.SecretKeyEntry`**, **`KeyStore.TrustedCertificateEntry`** và các phương thức quản lý alias. Ví dụ Java 17+ tạo đủ ba loại trong một **PKCS#12** (`.p12`), lưu ra file, mở lại và kiểm loại entry một cách thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt nội dung và mục đích của ba loại `KeyStore.Entry`: **khóa riêng kèm certificate chain**, **khóa đối xứng**, **chứng chỉ tin cậy độc lập**.
2. Giải thích **alias** là gì, phạm vi duy nhất và các thao tác `aliases`, `containsAlias`, `isKeyEntry`, `isCertificateEntry`, `entryInstanceOf`.
3. Dùng đúng `setEntry` / `getEntry` với `KeyStore.PasswordProtection`; hiểu khác nhau giữa **store password** và **entry password**.
4. Phân biệt **keystore danh tính** với **truststore của các chứng chỉ CA/peer được tin**, và hiểu vì sao lưu một certificate không tự xác minh được nguồn gốc của nó.
5. Triển khai và chạy chương trình Java 17+ dùng **PKCS12**, `keytool`, `KeyGenerator` và `KeyStore`; kiểm tra tất cả các loại entry sau khi lưu/nạp lại.
6. Tránh lỗi ghi đè alias, sai certificate chain, dùng JKS khi cần secret key, lộ password và cập nhật file không an toàn.

## 2. Mô hình tổng thể: KeyStore chứa những gì?

Một KeyStore có thể được hiểu như bản đồ **alias → entry** (thực tế mỗi provider/type có cách lưu trữ riêng):

~~~text
KeyStore: demo.p12  (type = PKCS12)
│
├── alias "identity-demo"
│    └── PrivateKeyEntry
│         ├── PrivateKey         [BÍ MẬT]
│         └── Certificate[]      [công khai, chain cho key này]
│
├── alias "api-aes"
│    └── SecretKeyEntry
│         └── SecretKey (AES)    [BÍ MẬT]
│
└── alias "trust-demo"
     └── TrustedCertificateEntry
          └── Certificate       [chỉ chứng chỉ công khai]
~~~

Một entry có **một loại cụ thể**, không phải một “object mơ hồ vừa chứa cert vừa chứa AES key”. Một `PrivateKeyEntry` có thể có certificate chain, nhưng nó **khác** `TrustedCertificateEntry`. Chứng chỉ X.509 mang **public key và thông tin định danh do issuer ký**, không chứa **private key**.

**Bảng đối chiếu:**

| Thuộc tính | `PrivateKeyEntry` | `SecretKeyEntry` | `TrustedCertificateEntry` |
| --- | --- | --- | --- |
| Chứa | Private key và certificate chain tương ứng | Secret key, ví dụ AES/HMAC key | Một certificate công khai |
| Có secret cần bảo vệ | **Có: private key** | **Có: secret key** | **Không có private key** |
| Có certificate chain | **Có**, bắt buộc khi tạo entry | Không | Chỉ chứa certificate đơn lẻ, không phải private-key chain |
| Tình huống chính | Server TLS identity, client TLS identity, ký số | AES-GCM data key, HMAC key, key-encryption key | CA certificate hoặc peer certificate đã được xác thực và chủ đích tin cậy |
| API get chuyên biệt | `getPrivateKey()`, `getCertificateChain()` | `getSecretKey()` | `getTrustedCertificate()` |
| `isKeyEntry(alias)` | `true` | `true` | `false` |
| `isCertificateEntry(alias)` | `false` | `false` | `true` |
| Entry protection | Thường `PasswordProtection` hoặc cơ chế provider | Thường `PasswordProtection`/provider | Thường `null` cho `getEntry/setEntry` kiểu certificate |
| Có thể dùng như identity có private key | Có, nếu certificate chain/identity/key đã được kiểm đúng | Không | Không |

**Ý nghĩa quan trọng:** `isKeyEntry` **không phân biệt private key và secret key**: cả hai đều là “key entry”. `isCertificateEntry` chỉ nhận loại certificate **đứng độc lập**; một `PrivateKeyEntry` có chứng chỉ đi kèm vẫn có thể trả `isCertificateEntry=false`.

## 3. Ba loại Entry trong Java

### 3.1. `KeyStore.PrivateKeyEntry`

`PrivateKeyEntry` bao gồm:

- Một `java.security.PrivateKey`: vật liệu khóa riêng để ký hoặc giải mã theo thuật toán phù hợp; không bao giờ in log hoặc xuất ra nơi công khai.
- Một mảng `java.security.cert.Certificate[]` thể hiện certificate chain. Phần tử **đầu tiên** là certificate end-entity tương ứng với private key, tiếp theo thường là các certificate cấp trên theo đường đi phát hành. Số lượng/tính hợp lệ chain phụ thuộc cấu hình.
- Có thể có các thuộc tính entry (`Attribute`) tùy provider/định dạng, nhưng không nên dùng để thay thế metadata ứng dụng đã quy định.

Ví dụ khái niệm:

~~~java
KeyStore.PrivateKeyEntry identity =
        (KeyStore.PrivateKeyEntry) store.getEntry(
                "identity-demo",
                new KeyStore.PasswordProtection(keyPassword));

PrivateKey signingKey = identity.getPrivateKey();
Certificate[] chain = identity.getCertificateChain();
~~~

Đoạn này **chỉ là trích đoạn**, cần khởi tạo `store`, biến `keyPassword` và xử lý exception; chương trình hoàn chỉnh ở phần 9.

Đặc điểm:

1. Nếu chỉ lưu `Certificate` mà **không có private key**, không thể dùng alias đó làm identity để ký hoặc chứng minh sở hữu khóa trong TLS.
2. Certificate chain phải phản ánh đúng private/public key của entity và cơ chế phát hành. Không trộn chain của domain/khóa khác.
3. **Có chain không đồng nghĩa certificate được tin**. Phía đối tác vẫn phải xác minh chữ ký, đường dẫn tin cậy, hạn dùng, tên host/SAN, key usage và chính sách liên quan khi sử dụng.
4. Nếu bạn dùng `KeyStore.setKeyEntry(alias, privateKey, password, chain)`, tham số `chain` là cần thiết cho private key. Với `setEntry`, tạo `new PrivateKeyEntry(privateKey, chain)`.
5. Private key có thể là **non-extractable** nếu nằm trong HSM/PKCS#11 hoặc provider đặc biệt. Đừng giả định `privateKey.getEncoded()` luôn trả byte hay có thể export.

**Thường dùng ở đâu?** TLS server identity thường dùng một `PrivateKeyEntry` để lấy private key và certificate chain; mutual TLS (mTLS) phía client cũng có thể dùng entry kiểu này. Private key phải tương ứng với public key trong certificate leaf; alias chỉ giúp tìm nó, không chứng minh sự tương ứng nếu dữ liệu được ghép sai.

### 3.2. `KeyStore.SecretKeyEntry`

`SecretKeyEntry` chứa `javax.crypto.SecretKey`, thường là khóa **đối xứng** hoặc khóa HMAC. Ví dụ:

~~~java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(128);
SecretKey aesKey = generator.generateKey();

store.setEntry(
        "api-aes",
        new KeyStore.SecretKeyEntry(aesKey),
        new KeyStore.PasswordProtection(password));
~~~

Đây cũng là **trích đoạn minh họa**, chưa phải class độc lập. Một `SecretKeyEntry` **không có X.509 certificate chain**, vì AES key là secret dùng cho thuật toán đối xứng, không phải key pair public/private để phát hành certificate.

Ứng dụng:

- Lưu **AES key** dùng encrypt/decrypt hoặc key-encryption key (KEK) nếu provider/storage policy cho phép.
- Lưu HMAC key dùng `Mac`, tùy provider và định dạng.
- Tránh nhầm `SecretKeyEntry` với khóa riêng RSA/EC hoặc chứng chỉ công khai.

Lưu ý:

- `JKS` theo provider truyền thống không hỗ trợ mọi kiểu secret key entry; nếu cần khóa đối xứng, dùng **PKCS12 hỗ trợ tương ứng**, HSM/PKCS#11 hoặc giải pháp quản lý khóa được kiểm chứng thay vì giả định một loại KeyStore nào cũng hỗ trợ.
- `JCEKS` từng được dùng để cất secret key trong các hệ thống cũ, nhưng không nên mặc định là lựa chọn mới vì các khác biệt lịch sử về thuật toán bảo vệ và interoperability. Ưu tiên loại/provider hiện đại phù hợp chính sách.
- Không lưu plaintext secret trong alias hay property file. Alias **không phải** mật khẩu; nó chỉ là chuỗi định danh entry.
- Với non-extractable key trong KMS/HSM, bản thân API/provider và vòng đời key có thể khác ví dụ file-based PKCS12.

### 3.3. `KeyStore.TrustedCertificateEntry`

`TrustedCertificateEntry` chứa một certificate (thường X.509) **không có private key**. Ví dụ:

~~~java
Certificate verifiedCaCertificate = /* certificate đã được kiểm bằng kênh tin cậy */;
store.setEntry(
        "corp-ca",
        new KeyStore.TrustedCertificateEntry(verifiedCaCertificate),
        null);
~~~

Đoạn này giải thích API, **không phải code Java hoàn chỉnh**: biến `verifiedCaCertificate` đại diện cho certificate đã có từ nguồn đáng tin, không được lấy tùy ý từ Internet rồi tự đánh dấu “trusted”.

Ứng dụng thực tế:

- Lưu **trust anchor** của một CA nội bộ hoặc CA được quản lý theo chính sách.
- Lưu peer certificate đã được xác minh ngoài băng để thực hiện chính sách pinning/trust cụ thể.
- Làm nguồn certificate cho `TrustManagerFactory` khi ứng dụng quyết định sử dụng **KeyStore này làm truststore**.

**Cảnh báo lớn:** Gọi `setCertificateEntry` hoặc tạo `TrustedCertificateEntry` **không phải hành động kiểm chứng certificate**. Nó biểu thị bạn chủ động đặt certificate trong một tập tin cậy khi cấu hình trust manager đọc store đó. Nếu certificate lấy từ đối thủ hoặc nhầm nguồn, việc “trust” có thể tạo ra lỗ hổng MITM. Với TLS, trust manager vẫn cần thực hiện các bước validation liên quan; chỉ có cert trên disk không bảo đảm endpoint hợp lệ.

**Phân biệt certificate trong `PrivateKeyEntry` và certificate đứng độc lập:**

~~~text
"identity-demo" --> PrivateKeyEntry [private key + leaf + chain]
"trust-demo"    --> TrustedCertificateEntry [một certificate, không có private key]
~~~

Một certificate có thể xuất hiện trong chain của `PrivateKeyEntry` và trong một trusted entry độc lập. **Không suy ra hai alias là cùng một loại entry** hoặc có cùng quyền sử dụng. Chương trình demo chủ động lưu bản sao cert self-signed dưới alias trusted để học API; **không được dùng chứng chỉ self-signed demo đó làm CA tin cậy trong sản phẩm**.

## 4. Alias: định danh logic, không phải khóa/mật khẩu/quyền truy cập

**Alias** là chuỗi ký tự để truy vấn entry trong **một KeyStore cụ thể**. Các API thiết yếu:

| API | Hành vi |
| --- | --- |
| `store.aliases()` | Liệt kê các alias hiện có; **không có cam kết thứ tự** |
| `store.size()` | Số lượng entry trong store |
| `store.containsAlias(name)` | Kiểm alias có tồn tại không |
| `store.isKeyEntry(name)` | Có phải key entry (private **hoặc** secret) không |
| `store.isCertificateEntry(name)` | Có phải certificate entry độc lập không |
| `store.entryInstanceOf(name, EntryType.class)` | Kiểm loại entry cụ thể, ví dụ `PrivateKeyEntry.class` |
| `store.getEntry(name, protection)` | Lấy entry theo alias và tham số bảo vệ tương ứng |
| `store.setEntry(name, entry, protection)` | Tạo hoặc **thay entry** gắn với alias |
| `store.deleteEntry(name)` | Xóa entry được chỉ định |
| `store.getCertificate(name)` | Trả certificate cho trusted entry hoặc certificate đầu của private-key entry khi có |
| `store.getCertificateChain(name)` | Trả chain của private-key entry nếu có; loại khác thường không có |
| `store.getKey(name, password)` | Có thể trả key cho key entry; dùng `getEntry` khi cần kiểm loại chính xác |
| `store.getCertificateAlias(cert)` | Tìm một alias cho certificate tương ứng, **không** bảo đảm là alias mục đích mà bạn mong đợi |

**Bốn quy tắc quan trọng về alias:**

1. **Duy nhất trong một store**, không phải duy nhất toàn hệ thống. Hai file khác nhau có thể có cùng alias với nội dung hoàn toàn khác.
2. **Không có namespace riêng theo entry type**: một alias không nên cùng lúc đại diện cả private key và trusted cert. `setEntry` với alias đang tồn tại có thể **thay thế** dữ liệu cũ; phải kiểm và backup trước.
3. **Case-sensitivity và normalization phụ thuộc provider/type.** Một số triển khai PKCS12 có thể canonicalize alias/không phân biệt hoa thường; **không dựa vào `"AppKey"` và `"appkey"` để tạo hai entry khác nhau**. Chọn quy ước alias ASCII thường, nhất quán và test trên provider mục tiêu.
4. **Alias không phải bí mật và không phải Access Control List**: biết alias không cấp quyền đọc key nếu không có quyền truy cập keystore/provider và bảo vệ entry; ngược lại đặt alias khó đoán cũng không làm store an toàn hơn.

Ví dụ sơ đồ đặt tên hữu ích cho vận hành:

~~~text
server-tls-prod-2026-10
client-mtls-backup-v2
payments-data-aes-v3
corp-root-ca-v1
~~~

Đây là **ví dụ cấu trúc tên**, không phải alias tự được Java hiểu đặc biệt. Có thể bổ sung key ID/version vào metadata ứng dụng; **không phân tích alias như bằng chứng quyền sở hữu hoặc độ tin cậy**.

### 4.1. Alias có phải tên Common Name/SAN trong certificate không?

**Không.** Alias là nhãn cục bộ của KeyStore; `CN` và `subjectAltName` (SAN) là các trường trong X.509 certificate. TLS hostname validation căn cứ tên được phép trong certificate/SAN và chain trust theo chính sách, **không** dựa vào tên alias bạn đặt.

Một TLS server có thể dùng alias `"identity-demo"` trong store chứa certificate `CN=Learning Demo`; alias đó không làm certificate hợp lệ cho `api.example.com`. Java `KeyManager` chọn private-key entry qua cơ chế riêng, còn `TrustManager` xử lý tin cậy certificate của peer.

### 4.2. `getCertificateAlias(cert)` không xác định mục đích entry

Nếu cùng certificate xuất hiện trong private-key chain và trusted entry, `getCertificateAlias(cert)` có thể tìm alias không như dự đoán. Đừng dùng kết quả đó để suy luận “đây là trusted root” hoặc “đây là signing key”. Thay vào đó, bạn nên lưu **đúng alias được cấu hình** và kiểm entry type, issuer/trust source, fingerprint, mục đích và policy.

## 5. Các loại KeyStore: PKCS12, JKS, JCEKS và PKCS11

`KeyStore` là **API trừu tượng**. `KeyStore.getInstance("PKCS12")` hoặc `"JKS"` chọn một **type/provider**, không quyết định mọi cấu trúc file giống nhau.

| Type / provider | Dùng khi | Lưu ý |
| --- | --- | --- |
| **PKCS12** | Định dạng file phổ biến cho private keys, certificates và (với provider phù hợp) secret keys; chọn làm demo | Khả năng tương tác có thể khác giữa Java/OpenSSL/thiết bị, nhất là secret key và cách bảo vệ/password |
| **JKS** | Hệ thống Java cũ và file truststore lâu đời | Provider JKS truyền thống chủ yếu phục vụ private-key/certificate entries, không nên giả định có SecretKeyEntry |
| **JCEKS** | Một số ứng dụng Java legacy lưu secret key | Quy tắc/mức bảo vệ và tương thích khác; cân nhắc migration có kiểm soát thay vì mặc định dùng cho hệ thống mới |
| **PKCS11** | Liên kết tới token/HSM/thiết bị bảo mật qua provider | Alias, mật khẩu/PIN, khả năng export key và lưu trữ phụ thuộc HSM; không nhất thiết có file `.p12` |
| **Provider tùy biến/KMS integration** | Hệ thống phân quyền/rotation/audit chuyên dụng | Kiểm `getEntry/setEntry`, supported key types và nghiệp vụ theo tài liệu provider |

Trên nhiều JDK hiện đại, `KeyStore.getDefaultType()` thường là `"pkcs12"`, nhưng **có thể bị cấu hình hoặc thay đổi theo môi trường**. Nếu định dạng cần tương thích, hãy chỉ rõ type và kiểm cấu hình thay vì dựa vào default.

**Cùng đuôi `.p12` không chứng minh file là PKCS12 hợp lệ**, và cùng type PKCS12 không bảo đảm secret keys được mọi công cụ bên ngoài đọc như nhau. Khi chuyển qua OpenSSL, HSM, hệ điều hành khác hoặc runtime khác, phải kiểm danh sách entry, certificate chain, policy encryption/password và khả năng import/export.

## 6. Store password, entry password và ProtectionParameter

Hai khái niệm cần phân biệt:

- **Store password**: đưa vào `store.load(input, storePassword)` để mở/kiểm bảo vệ kho theo provider; và `store.store(output, storePassword)` khi ghi lại.
- **Entry password**: dùng trong `KeyStore.PasswordProtection(entryPassword)` khi đọc/ghi **key entry** nếu provider/type hỗ trợ password riêng. Có thể khác store password ở một số type/provider.

`TrustedCertificateEntry` thường lấy bằng:

~~~java
KeyStore.TrustedCertificateEntry trusted =
        (KeyStore.TrustedCertificateEntry)
                store.getEntry("corp-ca", null);
~~~

`PrivateKeyEntry` hoặc `SecretKeyEntry` thường cần bảo vệ phù hợp:

~~~java
KeyStore.Entry entry = store.getEntry(
        "identity-demo",
        new KeyStore.PasswordProtection(entryPassword));
~~~

Đây là hai **trích đoạn** chứ không phải chương trình độc lập.

**Quan trọng với PKCS12:** Không áp đặt rằng mọi provider hỗ trợ mật khẩu riêng cho từng entry. Một số provider Java triển khai PKCS12 đặt ràng buộc rằng key password phải trùng store password. Ví dụ chạy dùng **cùng một password demo** để tránh nhầm tương thích.

`KeyStore.PasswordProtection` giữ password trong vùng nhớ có thể yêu cầu `destroy()`; `char[]` của bạn nên được xóa bằng `Arrays.fill(password, '\0')` sau sử dụng. Việc xóa mảng không bảo đảm JVM/provider xóa mọi bản sao hoặc snapshot RAM. Tránh lưu password trong `String` lâu dài; riêng chương trình demo dùng chuỗi literal chỉ để dễ tái hiện và **không được sao chép cách này vào production**.

Cơ chế bảo vệ có thể khác khi dùng HSM/PKCS#11: `ProtectionParameter` có thể đại diện PIN/callback hoặc cơ chế provider. Đừng tự đặt password mặc định trong code khi triển khai thật.

### 6.1. Lỗi mật khẩu và lỗi định dạng

Các API có thể ném `IOException`, `UnrecoverableKeyException`, `UnrecoverableEntryException`, `KeyStoreException` hoặc các lỗi đặc thù provider khi:

- Store password sai hoặc file bị hỏng;
- Alias không tồn tại hoặc loại entry không đúng;
- Password của entry sai, key không giải bọc được;
- Kiểu store/file thực tế không phù hợp provider;
- Provider thiếu hỗ trợ `SecretKeyEntry` hoặc định dạng bảo vệ yêu cầu.

**Không cố đoán thêm password hoặc bỏ kiểm tính toàn vẹn khi đọc lỗi**; phải xử lý chính sách, giám sát và khôi phục từ bản backup an toàn. Không đưa password hoặc secret ra error messages/logs.

## 7. Phân biệt KeyStore danh tính và truststore

Cả hai có thể cùng được biểu diễn bằng `java.security.KeyStore`, nhưng **vai trò vận hành khác nhau**.

| Khái niệm | Identity keystore | Truststore |
| --- | --- | --- |
| Chứa trọng tâm | Private key + certificate chain cho chính ứng dụng | CA/peer certificates mà ứng dụng **chủ đích** chấp nhận làm trust anchors |
| Kiểu entry quan trọng | `PrivateKeyEntry` | `TrustedCertificateEntry` |
| Ai tiêu thụ trong JSSE/TLS | `KeyManagerFactory` chọn danh tính/certificate chain để xuất trình | `TrustManagerFactory` kiểm certificate của đối tác theo chính sách |
| Thao tác kiểm tra | Đúng private key, chain, hạn dùng và mục đích | Nguồn trust anchor đúng, chính sách certificate path và hostname validation |
| Rủi ro nhập nhằng | Chỉ có certificate nhưng tưởng có private key | Tự import certificate từ nguồn không tin cậy và coi là CA đáng tin |

Trong thực tế, một PKCS12 có thể chứa cả hai loại entry, **nhưng tách keystore và truststore** thường dễ quản trị quyền, backup, rotation và kiểm toán hơn.

### 7.1. Giao thức TLS dùng chúng thế nào?

~~~text
TLS Server / Client (mTLS)
  Identity KeyStore:
    PrivateKeyEntry(alias = server-identity)
        -> private key + end-entity certificate + chain

  TrustStore:
    TrustedCertificateEntry(alias = authorized-ca)
        -> trust anchor

KeyManagerFactory -> chọn/đưa identity certificate và ký chứng minh private key
TrustManagerFactory -> đánh giá certificate chain đối phương
~~~

**Có certificate trong truststore chưa đủ để TLS client tự động bỏ qua hostname verification hoặc bỏ qua mọi ràng buộc.** Cần dùng TLS stack an toàn, xác minh hostname khi truy cập HTTPS, kiểm certificate path, key usage, hiệu lực, revocation policy khi yêu cầu. Nếu bạn tự cấu hình `SSLContext`/`TrustManager`, đừng tạo trust-all manager.

**Đừng đưa private key vào truststore để “tin” đối tác**: chứng chỉ công khai là đủ cho trust anchor, còn private key của đối tác tuyệt đối không phải thứ ứng dụng cần biết.

## 8. Chuẩn bị ví dụ với `keytool`

Trong JDK có công cụ `keytool` để tạo, xem và quản lý KeyStore. Ta tạo **PKCS12 mới gồm một private key RSA và certificate self-signed** để làm dữ liệu mẫu. Chương trình Java sẽ thêm **AES SecretKeyEntry** và một **TrustedCertificateEntry** (cùng certificate tự ký của demo), sau đó ghi và mở lại.

**Điều kiện:** JDK 17+; chạy các lệnh trong **thư mục thử nghiệm trống** và không dùng cùng tên file dữ liệu production. Chọn password cố định chỉ để bài tập có thể tái hiện.

~~~bash
keytool -genkeypair -alias identity-demo -keyalg RSA -keysize 2048 -dname "CN=Learning Demo" -validity 7 -storetype PKCS12 -keystore demo.p12 -storepass demochangeit -keypass demochangeit -noprompt
~~~

Giải thích:

- `-genkeypair`: sinh private/public key pair và certificate self-signed demo (không phải certificate được CA thực xác minh).
- `-alias identity-demo`: tên entry để code tìm.
- `-keyalg RSA -keysize 2048`: chỉ để chạy demo phổ biến; production chọn thuật toán/cỡ khóa theo chính sách hiện hành và nhu cầu ứng dụng.
- `-dname`: Subject DN; **không** liên quan tới alias.
- `-validity 7`: certificate sống 7 ngày để demo; hết hạn sẽ không phù hợp TLS thực.
- `-storetype PKCS12 -keystore demo.p12`: ghi file PKCS12.
- `-storepass -keypass`: cùng password demo; đưa password trên dòng lệnh **có thể lộ qua history/process listing**, chỉ chấp nhận trong môi trường thử nghiệm cô lập.

Sau bước này, file `demo.p12` có **một** entry `identity-demo`. Chỉ sau khi chương trình Java chạy xong mới có thêm hai alias khác.

Bạn có thể xem nội dung entry **mà không xuất private key** bằng:

~~~bash
keytool -list -v -keystore demo.p12 -storetype PKCS12 -storepass demochangeit
~~~

Đầu ra `keytool -list` chứa alias, loại entry và thông tin certificate/fingerprint; một số trường có thể phụ thuộc provider/JDK. **Không đưa fingerprint hoặc certificate subject hiển thị vào logic authorization bằng cách đoán string**; nếu phải pinning thì quy định chính xác certificate/public-key fingerprint và cách xác minh.

**Cảnh báo:** Alias `"trust-demo"` được tạo từ certificate self-signed `identity-demo` trong cùng file **chỉ để thực nghiệm khác biệt API**. Việc thêm certificate này vào một truststore thật có thể khiến ứng dụng tin một nguồn không nên tin. Với CA/peer thật phải xác minh fingerprint/nguồn cấp qua kênh độc lập đã kiểm định trước khi import.

## 9. Ví dụ Java 17+ hoàn chỉnh, có thể biên dịch và chạy

Sau khi thực hiện lệnh `keytool` ở phần 8, lưu chương trình sau thành **`KeyStoreEntriesDemo.java`** cùng thư mục với `demo.p12`. Không cần Maven/Gradle hay dependency ngoài JDK.

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.Collections;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class KeyStoreEntriesDemo {
    private static final String TYPE = "PKCS12";
    private static final Path FILE = Path.of("demo.p12");
    private static final String PRIVATE_ALIAS = "identity-demo";
    private static final String SECRET_ALIAS = "api-aes";
    private static final String TRUST_ALIAS = "trust-demo";

    public static void main(String[] args) throws Exception {
        // Chỉ cho demo. Production: mật khẩu từ secret manager.
        char[] password = "demochangeit".toCharArray();
        KeyStore.PasswordProtection entryPassword =
                new KeyStore.PasswordProtection(password);
        try {
            KeyStore store = KeyStore.getInstance(TYPE);
            try (InputStream input = Files.newInputStream(FILE)) {
                store.load(input, password);
            }

            // Entry được tạo bởi keytool: private key + certificate chain.
            KeyStore.PrivateKeyEntry original =
                    (KeyStore.PrivateKeyEntry) store.getEntry(
                            PRIVATE_ALIAS, entryPassword);
            System.out.println("Private found       = " + (original != null));
            System.out.println("Private algorithm   = "
                    + original.getPrivateKey().getAlgorithm());
            System.out.println("Chain length        = "
                    + original.getCertificateChain().length);

            // SecretKeyEntry: AES 128-bit ngẫu nhiên, không có certificate.
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128);
            SecretKey aes = generator.generateKey();
            if (store.containsAlias(SECRET_ALIAS)
                    || store.containsAlias(TRUST_ALIAS)) {
                throw new IllegalStateException("Alias already exists");
            }
            store.setEntry(SECRET_ALIAS,
                    new KeyStore.SecretKeyEntry(aes), entryPassword);

            // Chỉ để phân biệt entry type; KHÔNG phải hành động
            // xác minh trust của certificate thật.
            Certificate demoCertificate = original.getCertificate();
            store.setEntry(TRUST_ALIAS,
                    new KeyStore.TrustedCertificateEntry(demoCertificate),
                    null);

            // Ghi kho ra file. Production cần ghi an toàn/atomic + backup.
            try (OutputStream output = Files.newOutputStream(FILE)) {
                store.store(output, password);
            }

            // Mở lại từ disk và kiểm đúng loại entry.
            KeyStore reopened = KeyStore.getInstance(TYPE);
            try (InputStream input = Files.newInputStream(FILE)) {
                reopened.load(input, password);
            }

            System.out.println("KeyStore type       = " + reopened.getType());
            System.out.println("Alias count         = "
                    + Collections.list(reopened.aliases()).size());
            System.out.println("PrivateKeyEntry     = "
                    + reopened.entryInstanceOf(PRIVATE_ALIAS,
                            KeyStore.PrivateKeyEntry.class));
            System.out.println("SecretKeyEntry      = "
                    + reopened.entryInstanceOf(SECRET_ALIAS,
                            KeyStore.SecretKeyEntry.class));
            System.out.println("TrustedCertEntry    = "
                    + reopened.entryInstanceOf(TRUST_ALIAS,
                            KeyStore.TrustedCertificateEntry.class));

            KeyStore.SecretKeyEntry restoredSecret =
                    (KeyStore.SecretKeyEntry) reopened.getEntry(
                            SECRET_ALIAS, entryPassword);
            KeyStore.TrustedCertificateEntry restoredTrusted =
                    (KeyStore.TrustedCertificateEntry) reopened.getEntry(
                            TRUST_ALIAS, null);
            System.out.println("Secret algorithm    = "
                    + restoredSecret.getSecretKey().getAlgorithm());
            System.out.println("Secret bits         = "
                    + restoredSecret.getSecretKey().getEncoded().length * 8);
            System.out.println("Secret restored     = "
                    + Arrays.equals(aes.getEncoded(),
                            restoredSecret.getSecretKey().getEncoded()));
            System.out.println("Trusted cert type   = "
                    + restoredTrusted.getTrustedCertificate().getType());
            System.out.println("Trusted is key      = "
                    + reopened.isKeyEntry(TRUST_ALIAS));
            System.out.println("Missing alias       = "
                    + reopened.containsAlias("no-such-entry"));
        } finally {
            entryPassword.destroy();
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac KeyStoreEntriesDemo.java
java KeyStoreEntriesDemo
~~~

Đầu ra được kiểm chứng với một PKCS12 mới do `keytool` tạo, theo lệnh trên:

~~~text
Private found       = true
Private algorithm   = RSA
Chain length        = 1
KeyStore type       = PKCS12
Alias count         = 3
PrivateKeyEntry     = true
SecretKeyEntry      = true
TrustedCertEntry    = true
Secret algorithm    = AES
Secret bits         = 128
Secret restored     = true
Trusted cert type   = X.509
Trusted is key      = false
Missing alias       = false
~~~

**Giải thích đầu ra:**

1. `Private found = true`: `keytool` đã thêm `identity-demo`, Java đọc được sau `load` đúng password. `Private algorithm = RSA` do tham số `-keyalg RSA`. Chuỗi một phần tử do certificate self-signed demo; **chain thật có thể dài hơn**.
2. `store.setEntry("api-aes", SecretKeyEntry, entryPassword)` thêm AES key 128 bit. Sau `store.store` và `reopened.load`, `getEntry` đọc được đúng byte AES (chỉ in `true`, không in key).
3. `store.setEntry("trust-demo", TrustedCertificateEntry, null)` lưu certificate demo dưới **alias mới**, không thêm private key. `entryInstanceOf` trả loại cụ thể, còn `isKeyEntry("trust-demo")` trả false.
4. `Alias count = 3` vì file ban đầu có một entry và chương trình thêm hai entry. Nếu chạy chương trình **lần hai trên cùng file**, nhánh kiểm alias sẽ ném lỗi để tránh vô tình ghi đè. Muốn lặp bài tập, tạo thư mục demo mới và sinh keystore mới bằng lệnh `keytool`.
5. `Missing alias = false` chứng minh `containsAlias` không tự tạo entry khi truy vấn, và tên không tồn tại không cung cấp key.
6. `KeyStore.PasswordProtection` được dùng để đọc/ghi key entries, còn certificate entry chỉ cần `null` protection trong provider demo. Phần `finally` cố xóa mật khẩu demo khỏi vùng nhớ có thể quản lý, nhưng **không bảo đảm zeroize mọi bản sao trong JVM**.

**Giới hạn của ví dụ:** Password cố định trên dòng lệnh/trong source, certificate tự ký, RSA demo và **ghi đè file trực tiếp** không phải cấu hình production. Với hệ thống thật: dùng secret manager/KMS/HSM, certificate/CA hợp lệ được kiểm nguồn, chính sách access, audit, backup, và ghi file theo cách crash-safe. `getEncoded()` có thể trả `null` với khóa không exportable; câu lệnh tính độ dài secret trong demo chỉ phù hợp key AES của `KeyGenerator` chuẩn.

## 10. Lấy đúng entry: `getEntry` hay `getKey` / `getCertificate`?

Một bug thường gặp là lấy object theo alias rồi **ép kiểu không kiểm tra**. Dùng `entryInstanceOf` hoặc `isKeyEntry`/`isCertificateEntry` theo nhu cầu, nhưng phải nhớ `isKeyEntry` bao trùm hai loại key.

| Bạn muốn | API nên dùng | Điều cần kiểm |
| --- | --- | --- |
| Private key + cert chain | `getEntry(alias, PasswordProtection)` rồi `PrivateKeyEntry` | Alias tồn tại và đúng loại; password đúng; chain hợp lệ |
| AES/HMAC key | `getEntry(alias, PasswordProtection)` rồi `SecretKeyEntry` | SecretKeyEntry được provider hỗ trợ, algorithm/usage phù hợp |
| Certificate được chọn làm trusted | `getEntry(alias, null)` rồi `TrustedCertificateEntry` | Nguồn tin cậy được xác minh **ngoài** KeyStore |
| Chỉ certificate leaf của identity | `getCertificate(alias)` | Đây có thể là cert trong PrivateKeyEntry, **không có nghĩa trusted** |
| Certificate chain | `getCertificateChain(alias)` | Chỉ có ý nghĩa với entry private key/chain |
| Kiểm loại trước cast | `entryInstanceOf(alias, EntryType.class)` | Kiểm đúng lớp, không chỉ `isKeyEntry` |
| Lấy key bằng API cũ | `getKey(alias, password)` | Có thể trả private hoặc secret key; cần kiểm kiểu/algorithm |

`getEntry` với alias không tồn tại có thể trả `null`. Alias tồn tại nhưng mật khẩu hoặc loại protection không phù hợp có thể ném exception theo provider, **không đồng nhất “null” với sai password**. Không bắt mọi exception rồi giả vờ như thiếu alias, vì có thể che giấu lỗi bảo vệ khóa.

### 10.1. Vì sao `getCertificate(alias) != null` chưa đủ?

Nếu alias trỏ tới `PrivateKeyEntry`, `getCertificate(alias)` thường trả **chứng chỉ đầu tiên** của chain. Nếu alias trỏ tới `TrustedCertificateEntry`, nó trả certificate được lưu riêng. Cùng trả `Certificate` nhưng ngữ nghĩa khác nhau. Khi cần trust anchor, kiểm **entry type**, nguồn certificate, policy và cấu hình trust manager; khi cần ký, kiểm **PrivateKeyEntry** có private key tương ứng.

### 10.2. Vì sao phải phân biệt `PrivateKey` và `SecretKey`?

`PrivateKey` dùng trong hệ mật mã khóa bất đối xứng; `SecretKey` thường dùng cho mã hóa đối xứng/MAC. `Key` là interface chung nên `getKey` có thể trả một trong hai. Nếu chỉ gọi `key.getAlgorithm()` hoặc kiểm “key != null”, ứng dụng có thể lẫn vai trò. Hãy kiểm kiểu đúng, thuật toán/suite và policy sử dụng khi lấy key ra khỏi KeyStore.

## 11. Vòng đời alias: tạo, đọc, thay, xóa, đổi tên

Một KeyStore là **kho lưu trạng thái**, việc thay alias có thể phá ứng dụng trỏ tới tên cũ.

~~~text
START
  |
  +-- containsAlias(name)?
         | YES --> kiểm purpose/type/version, không ghi đè âm thầm
         | NO
         v
      setEntry(name, entry, protection)
         |
         v
      store(output, storePassword)
         |
         v
      reload + verify entry types / aliases
~~~

### 11.1. Tạo alias

- Chọn tên có quy tắc, tránh ký tự nhập nhằng và tên case-fold collision theo provider.
- Kiểm `containsAlias`, backup và xác nhận không dùng tên thuộc mục đích khác.
- `setEntry` cập nhật **trạng thái của object KeyStore trong bộ nhớ**; để lưu với file-backed store, phải gọi `store(...)`. Nếu ứng dụng crash trước khi lưu, thay đổi chưa chắc tồn tại trên disk.
- Alias/metadata không cấp quyền; kiểm quyền theo filesystem, secret manager, HSM/KMS.

### 11.2. Xóa alias

~~~java
// Trích đoạn minh họa; không chạy nếu chưa kiểm backup/phụ thuộc.
if (store.containsAlias("old-identity")) {
    store.deleteEntry("old-identity");
}
~~~

Xóa entry trong bộ nhớ **không tự xóa file**; sau đó cần ghi lại file theo cách an toàn. Xóa private key đang được TLS listener, signing service hoặc job khác sử dụng có thể làm chúng mất khả năng xác thực/ký. Xóa certificate trust anchor có thể khiến kết nối hợp lệ bị từ chối. Xóa key đã dùng mã hóa dữ liệu lưu trữ có thể khiến bản mã **không thể giải mã** nếu không còn key backup.

### 11.3. Đổi alias

`KeyStore` không có một phương thức chuẩn `renameEntry(alias1, alias2)`. Có thể dùng công cụ `keytool -changealias` cho file format/provider hỗ trợ hoặc di chuyển entry bằng logic kiểm soát (copy với protection đúng, xác minh alias đích, lưu an toàn rồi xóa cũ). Khi đổi alias, cần cập nhật cấu hình ứng dụng và xác minh chain/key vẫn đúng; không làm thủ công trong production nếu chưa kiểm backup/rollback.

**Lưu ý:** Một số provider không cho copy/export private key hoặc đổi alias theo cách bạn muốn; trong HSM phải dùng API quản lý khóa của provider.

### 11.4. Rotation và key versions

Không dùng một alias cố định rồi âm thầm **thay nội dung** nếu dữ liệu cũ vẫn cần key cũ hoặc peer cũ đang dùng certificate cũ. Có thể quản lý versioned aliases và key IDs, ví dụ `"payments-data-aes-v3"`, đồng thời có migration/re-encryption/rewrap, thời gian chuyển tiếp và chính sách xóa key cũ.

Với private-key TLS, certificate renewal có thể thay chain dù giữ key cũ (không phải luôn nên giữ key cũ). Với key rotation có thể cần tạo key pair mới, CSR, certificate mới, reload cấu hình và giám sát certificate expiry. Với truststore, thêm CA mới trước khi loại CA cũ phải theo chính sách tin cậy và kết nối thực tế.

## 12. Trạng thái KeyStore và thao tác lưu file an toàn

Thao tác thường gặp:

~~~text
KeyStore.getInstance("PKCS12")
  -> load(InputStream, char[] storePassword)
  -> containsAlias / aliases / getEntry / setEntry / deleteEntry
  -> store(OutputStream, char[] storePassword)
  -> load lại trong instance độc lập để xác minh
~~~

Tạo **store rỗng mới** trong Java có thể dùng `store.load(null, password)` trước khi thêm entries. Ngược lại, `load(input, password)` trên file có sẵn là thao tác đọc dữ liệu; không gọi `load(null, ...)` khi đang muốn mở file cũ vì có thể tạo trạng thái mới rỗng trong bộ nhớ.

### 12.1. Đừng ghi trực tiếp vào file quan trọng nếu có rủi ro crash

Ví dụ ở phần 9 dùng `Files.newOutputStream(FILE)` để minh họa `store`, nhưng có thể **truncate file cũ trước khi ghi xong**. Trong production:

1. Khóa hoặc điều phối thao tác thay đổi để tránh hai process cùng sửa file.
2. Load và kiểm phiên bản/nội dung store hiện tại.
3. Ghi sang **file tạm trong cùng filesystem** với quyền/ACL phù hợp.
4. Flush và đảm bảo dữ liệu đã được ghi ổn định theo yêu cầu hệ thống.
5. Di chuyển/replace một cách **atomic nếu filesystem hỗ trợ** (Java `Files.move` với `ATOMIC_MOVE`; có thể cần fallback an toàn tùy platform).
6. Giữ backup được bảo vệ và kiểm khả năng khôi phục.
7. Mở lại store sau thay đổi và kiểm aliases, types, certificate fingerprints/expiry, chain và khả năng giải bọc key theo test không nhạy cảm.

**Không dùng KeyStore file như database có transaction đa người ghi**. Khi nhiều instance cùng quản lý keys, cân nhắc hệ quản lý secret/key tập trung với phân quyền và audit.

## 13. Công cụ `keytool` và những hành động thường gặp

| Lệnh | Mục đích | Lưu ý |
| --- | --- | --- |
| `keytool -genkeypair` | Tạo private key + certificate demo/CSR workflow | Chọn key algorithm, identity DN, thời hạn, store type |
| `keytool -list -v` | Xem alias, entry type và certificate details | Không dùng output làm bản ghi bí mật; tránh đưa storepass vào lịch sử lệnh thật |
| `keytool -exportcert` | Xuất certificate công khai | **Không** xuất private key; biết đúng alias và format |
| `keytool -importcert` | Thêm certificate đã được xác minh hoặc certificate reply/chain theo ngữ cảnh | Kiểm certificate fingerprint và nguồn từ kênh tin cậy |
| `keytool -delete` | Xóa entry theo alias | Có backup, đánh giá phụ thuộc và cách reload |
| `keytool -changealias` | Đổi alias khi provider hỗ trợ | Kiểm collision, cấu hình và backup trước |
| `keytool -importkeystore` | Di chuyển entries giữa store/type | Kiểm storepass/keypass, certificate chain, secret key support, provider |

**Khi import cert vào trusted entry**, rủi ro lớn nhất không phải lệnh gõ sai mà là việc **tin certificate sai nguồn**. Đừng dùng lựa chọn bỏ qua xác minh fingerprint chỉ để import thành công. Một certificate self-signed được lưu vào truststore có thể có mục đích hợp lệ trong hệ thống riêng nhưng phải đi qua **quy trình kiểm nguồn/out-of-band**.

**Không lấy private key/certificate của môi trường production để chạy bài học.** Tất cả ví dụ dùng khóa thử nghiệm.

## 14. Kịch bản áp dụng

### 14.1. TLS server không khởi động vì chỉ có certificate

Một nhóm triển khai import cert leaf vào store dưới alias `"api-server"` như `TrustedCertificateEntry`, rồi cấu hình `KeyManagerFactory` chọn alias đó. Server không thể ký handshake bằng cert vì **không có private key**. Cách đúng là nạp `PrivateKeyEntry` chứa **đúng private key** và chain tương ứng; nếu khóa nằm trong HSM thì cấu hình provider nhận private key từ HSM.

### 14.2. Thêm AES key vào JKS bị lỗi

Ứng dụng cũ mở `KeyStore.getInstance("JKS")`, gọi `setEntry(..., SecretKeyEntry, ...)` và nhận lỗi provider không hỗ trợ. Không thể sửa bằng đổi file extension sang `.p12`: phải **tạo/import PKCS12 thật** hoặc chọn provider/KMS hỗ trợ secret key, sau đó xác minh đọc lại key. Cũng cần kiểm thuật toán bảo vệ key, quyền file và backup.

### 14.3. Đổi alias mà ứng dụng vẫn trỏ tên cũ

Keystore đã có `"new-tls-v2"` nhưng cấu hình `server.ssl.key-alias` hoặc key manager vẫn chọn `"old-tls"`; kết quả có thể là không tìm thấy key hoặc chọn danh tính sai. Alias là một **giao diện cấu hình**, cần kiểm cross-service deployment, restart/reload, certificate validity và rollback.

### 14.4. Nhầm chứng chỉ identity với trust anchor

`getCertificate("identity-demo")` trả certificate của key pair. Một người dùng certificate ấy để tự xây “trust-all” logic cho server khác. Đây là **vượt qua kiểm nguồn**; chứng chỉ identity của mình không chứng minh CA của đối tác đáng tin. Để xác minh peer, xây truststore từ CA/peer được chấp nhận có kiểm tra nguồn, và dùng trust manager đúng chuẩn.

### 14.5. SecretKeyEntry đã restore nhưng hệ thống vẫn không giải mã được

`Secret restored = true` chứng minh byte key trong ví dụ được lưu/nạp chính xác, nhưng decrypt thực tế còn cần **đúng thuật toán, mode, nonce/IV, tag, AAD, schema và ciphertext**. Alias trỏ đúng key là điều kiện cần, không phải đủ. Với AES-GCM, không bao giờ dùng lại cặp key/nonce cho hai lần encrypt, và phải xác minh tag trước khi xử lý plaintext.

### 14.6. File chứa cả key và trusted certificates

PKCS12 có thể lưu cả ba entry types; điều đó không bắt buộc mọi ứng dụng phải chấp nhận tất cả. Khi cấu hình TLS, nên giữ identity keystore/truststore tách biệt theo trách nhiệm, kể cả khi cùng dùng PKCS12. Việc chuyển format phải kiểm chính sách certificate validation và alias selection.

## 15. Những lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm/sai | Cách khắc phục |
| --- | --- | --- |
| Gọi `isKeyEntry` rồi cast `PrivateKeyEntry` | `isKeyEntry` cũng trả true cho SecretKeyEntry | Dùng `entryInstanceOf(alias, PrivateKeyEntry.class)` |
| Tưởng cert ở `PrivateKeyEntry` là `TrustedCertificateEntry` | Lẫn identity của mình với trust anchor | Phân biệt type và chính sách sử dụng |
| Tưởng TrustedCertificateEntry có private key | Không thể ký/giải mã bằng private key không tồn tại | Dùng PrivateKeyEntry có đúng key + chain |
| Lưu một public key X.509 mà chưa kiểm nguồn rồi gọi là trusted | Mở cửa MITM/trust sai | Xác minh fingerprint, CA/path, quyền đưa vào truststore |
| Ghi `setEntry` trùng alias | Có thể thay entry cũ và làm mất key/cert quan trọng | `containsAlias`, backup, versioned aliases |
| Giả định alias case-sensitive | Collision/nghi vấn khi provider canonicalize alias | Đặt alias ASCII theo quy ước, test provider |
| Dựa vào thứ tự `aliases()` để chọn key | Enumeration order không được cam kết | Chọn alias rõ ràng theo cấu hình |
| Sử dụng JKS để lưu AES SecretKeyEntry | Provider truyền thống không hỗ trợ | PKCS12 tương thích hoặc KMS/HSM phù hợp |
| Dùng store password ở mọi provider mà không kiểm entry protection | Sai keypass/không mở được key | Hiểu Store vs Entry protection theo type/provider |
| Ghi password trong code/command production | Lộ qua source, shell history, process list | Secret manager/callback, kiểm quyền và audit |
| Quên gọi `store` sau `setEntry` | Thay đổi chỉ ở RAM, mất sau restart | Store an toàn rồi reload xác nhận |
| Lưu trực tiếp đè file production | Crash có thể làm hỏng file keystore | Temp file, atomic move khi hỗ trợ, backup |
| Xóa alias của key còn dùng decrypt | Không thể phục hồi dữ liệu cũ | Rotation với key ID, retention/rewrap và backup |
| Coi certificate chain là đã xác minh trust | Peer phải validate chain, name, expiry, usage | Trust manager/certificate validation đúng |
| Dùng `getCertificateAlias` để suy ra entry type | Một cert có thể xuất hiện ở nhiều alias | `entryInstanceOf` + mục đích cấu hình |
| Tưởng KeyStore file thay KMS | Thiếu audit/rotation/ACL tập trung; key có thể xuất RAM | Quản lý file/OS/HSM/KMS theo threat model |

## 16. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Một alias chứa private key RSA và certificate chain. Đây là entry gì? API nào nhận đúng loại?

**Đáp án:** `PrivateKeyEntry`. Dùng `getEntry(alias, PasswordProtection)` kết hợp `entryInstanceOf(alias, PrivateKeyEntry.class)`; private key và chain phải khớp và được bảo vệ.

**Câu 2.** Alias `"api-aes"` chứa khóa AES. `isKeyEntry("api-aes")` trả true. Có thể cast thành `PrivateKeyEntry` không?

**Đáp án:** Không. `SecretKeyEntry` cũng là key entry. Kiểm chính xác `SecretKeyEntry.class` hoặc nhận `SecretKey` theo provider phù hợp.

**Câu 3.** Một certificate được lưu với `setCertificateEntry("corp-ca", cert)`. Nó có chứa private key không?

**Đáp án:** Không, đó là `TrustedCertificateEntry` độc lập. Chỉ certificate công khai; không thể dùng để ký hoặc chứng minh sở hữu private key.

**Câu 4.** Một private key entry có certificate chain, vậy `isCertificateEntry(alias)` có true không?

**Đáp án:** Không theo nghĩa API: đây là **key entry**. `isCertificateEntry` dành cho certificate entry độc lập.

**Câu 5.** Tại sao `getCertificateAlias(cert)` không đủ để biết cert là trust anchor?

**Đáp án:** Một cert có thể nằm trong chain của PrivateKeyEntry và được lưu dưới TrustedCertificateEntry. Alias tìm được không chứng minh nguồn tin cậy hay loại sử dụng; phải xem entry type và chính sách trust.

**Câu 6.** Nhóm vận hành tạo `"MyKey"` và `"mykey"`, nghĩ sẽ có hai entry. Có chắc không?

**Đáp án:** Không. Alias case handling phụ thuộc provider; có thể canonicalize/collision. Dùng tên duy nhất không nhập nhằng theo chuẩn đặt tên và kiểm trước khi ghi.

**Câu 7.** Đã gọi `store.setEntry(...)` trong chương trình nhưng sau restart entry mới biến mất. Vì sao?

**Đáp án:** Vì sửa state trong RAM không tự ghi file. Cần gọi `store(output, password)` và kiểm reload, lưu bằng quy trình an toàn.

**Câu 8.** Có nên lưu chứng chỉ self-signed vừa tải từ website lạ như TrustedCertificateEntry để “khỏi bị báo TLS lỗi”?

**Đáp án:** Không. Không xác minh nguồn/kênh độc lập nghĩa là có thể tin khóa của attacker. Phải đánh giá certificate, identity, fingerprint/CA và trust policy.

**Câu 9.** Một JKS hiện có certificate/key pair nhưng khi thêm AES SecretKeyEntry bị lỗi. Đổi đuôi file sang `.p12` có chữa được không?

**Đáp án:** Không. Type/provider và cấu trúc dữ liệu thực tế mới quyết định support. Cần chuyển đổi/import có kiểm soát hoặc dùng store/provider phù hợp.

**Câu 10.** Vì sao không nên xóa alias của DEK cũ ngay khi tạo DEK v2?

**Đáp án:** Bản mã cũ còn cần key cũ để giải mã/rewrap/re-encrypt. Xóa key trước migration và backup có thể gây mất dữ liệu không thể phục hồi.

## 17. Checklist áp dụng KeyStore

- [ ] Biết rõ store **type/provider** và compatibility (PKCS12/JKS/HSM); không dựa vào phần mở rộng tên file.
- [ ] Phân biệt **PrivateKeyEntry**, **SecretKeyEntry**, **TrustedCertificateEntry** bằng type, không chỉ `isKeyEntry`.
- [ ] Private-key entry có đúng private key và chain; leaf certificate là của key đó, identity/usage/expiry được xác minh theo nhu cầu.
- [ ] Secret key đúng thuật toán, độ dài, usage và provider; không mặc nhiên exportable.
- [ ] Trusted certificate được kiểm **nguồn, fingerprint và chính sách** trước khi đưa vào truststore; không biến cert lạ thành trust anchor.
- [ ] Alias theo quy ước ổn định, unique theo provider; không ghi đè nhầm; không suy ra quyền từ alias.
- [ ] Store password và entry protection được quản lý đúng, không hard-code trong production, có cơ chế rotation/audit.
- [ ] Đã backup và có quy trình **store an toàn/reload verify** trước khi rollout.
- [ ] Identity keystore và truststore có trách nhiệm rõ ràng; KeyManager/TrustManager được cấu hình an toàn.
- [ ] Key ID/alias version và retention phù hợp lifecycle; không xóa key còn dùng đọc dữ liệu cũ.
- [ ] Có kiểm thử trên **JDK/provider/type thật** để xác nhận secret key support, alias behavior, certificate chain và password policy.

**Kết luận:** `KeyStore` là **kho entry được đánh chỉ mục bằng alias**, không phải một kiểu key duy nhất. **`PrivateKeyEntry`** lưu private key với certificate chain; **`SecretKeyEntry`** lưu secret key đối xứng; **`TrustedCertificateEntry`** lưu certificate độc lập được ứng dụng chủ đích chấp nhận làm nguồn tin cậy. Alias chỉ là nhãn tra cứu; sự an toàn còn đến từ đúng provider/format, nguồn certificate, protection, quyền file, quản lý khóa và quy trình cập nhật có kiểm soát.
