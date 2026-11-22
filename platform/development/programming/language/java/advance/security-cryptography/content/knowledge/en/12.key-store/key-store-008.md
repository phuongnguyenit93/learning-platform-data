# 12.8. Tạo, liệt kê, nhập, xuất và chuyển đổi kho bằng `keytool`

## Mục tiêu

`keytool` là tiện ích dòng lệnh đi cùng JDK để **tạo và quản lý khóa, chứng chỉ X.509, certificate signing request (CSR) và Java KeyStore**. Trong thực tế, bạn dùng nó để tạo khóa cho môi trường thử nghiệm, xem loại entry/alias, xuất chứng chỉ **công khai**, nhập một chứng chỉ đáng tin, cập nhật certificate chain, hoặc chuyển kho cũ từ JKS sang PKCS12.

Sau bài học, bạn có thể:

1. Phân biệt `PKCS12`, `JKS`, `PKCS11` và các loại entry `PrivateKeyEntry`, `SecretKeyEntry`, `trustedCertEntry`.
2. Dùng `keytool -genkeypair` hoặc `-genseckey` để tạo kho phù hợp; `-list` để kiểm kê và `-printcert` để kiểm tra chứng chỉ.
3. Dùng đúng `-exportcert`, `-importcert`, `-certreq` và `-importkeystore`; biết thao tác nào **không** đưa private key ra ngoài và thao tác nào có thể **sao chép private key**.
4. Chuyển `JKS → PKCS12` và kiểm tra dữ liệu/alias/chứng chỉ sau chuyển; hiểu các vấn đề password, key password, định dạng, trust và automation.
5. Áp dụng biện pháp an toàn tối thiểu: backup trước thao tác thay đổi, bảo vệ mật khẩu, xác thực fingerprint từ nguồn đáng tin và không chỉnh sửa truststore mặc định tùy tiện.

Mọi ví dụ trong bài hướng đến **JDK 17+**; các lệnh đã được kiểm tra trên JDK có hỗ trợ những thuật toán được dùng. Các tập tin minh họa `*.p12`, `*.jks`, `*.pem` và `*.csr` là **dữ liệu học tập**, không nên coi chứng chỉ tự ký là chứng chỉ được CA công cộng tin cậy. Trong production, dùng CA/KMS/HSM và chính sách certificate/key lifecycle phù hợp.

## 1. Nhận diện đúng mục tiêu trước khi gọi keytool

`keytool` thao tác **alias và entry** của `KeyStore`, theo type/provider và quyền của người vận hành. Khi chạy CLI phải phân biệt ba loại dữ liệu được lưu:

- **PrivateKeyEntry**: private key và certificate chain; thường tạo bằng `-genkeypair`, dùng khi ký hoặc trình danh tính TLS.
- **SecretKeyEntry**: secret key như AES; có thể tạo bằng `-genseckey` nếu store/provider hỗ trợ.
- **trustedCertEntry**: một public certificate đã được quản trị viên **chủ động chấp thuận**; có thể tạo bằng `-importcert` dưới alias mới.

Các thao tác khác nhau về **tác động**: `-list` và `-printcert` đọc metadata; `-exportcert` chỉ xuất certificate công khai; còn `-importcert`, `-importkeystore`, `-changealias`, `-delete` hoặc lệnh tạo khóa **thay đổi kho, có thể thay cả trust policy hoặc sao chép private key**. Vì vậy cần kiểm tra alias, source certificate, password và backup trước khi dùng câu lệnh ghi. Đoạn tiếp theo tập trung thao tác CLI thực tế, không lặp bảng API quản lý entry.

## 2. Các định dạng và lý do chỉ rõ `-storetype`

| Loại kho | Mô tả | Lưu ý |
| --- | --- | --- |
| `PKCS12` | Định dạng cross-platform thường dùng cho private key, certificate và trong provider JDK hiện đại có thể chứa secret key | **Mặc định từ JDK 9** trong cấu hình OpenJDK/Oracle JDK thông thường; file thường mang đuôi `.p12` hoặc `.pfx` |
| `JKS` | Định dạng kho Java lịch sử, riêng của Java | Gặp nhiều ở ứng dụng cũ; thường nên đánh giá migration sang PKCS12 |
| `JCEKS` | Định dạng Java legacy hỗ trợ secret key | Tính tương thích và cơ chế bảo vệ khác PKCS12; không chọn chỉ vì tên quen thuộc |
| `PKCS11` | API đến token/HSM thông qua provider, không mặc định là một file kho có thể copy | Có thể dùng `-storetype PKCS11 -keystore NONE` với provider/config đã được thiết lập; quyền và khả năng xuất key phụ thuộc thiết bị |
| `Windows-MY`/provider khác | Keystore gắn với hệ điều hành/provider nếu được hỗ trợ | Không giả định mọi Java runtime/provider đều có |

Java 17 thường có `KeyStore.getDefaultType()` là `pkcs12`. Tuy nhiên **đừng suy loại kho chỉ từ đuôi file**: đặt tên `legacy.jks` không tự biến nội dung thành JKS nếu `-storetype` để mặc định. Trong bài này mọi thao tác quan trọng đều ghi rõ `-storetype` để hạn chế mơ hồ.

Tên `PKCS12`/`JKS` có thể được nhận dạng không phân biệt hoa thường. Một số JDK/provider có khả năng tự phát hiện định dạng và đọc tương thích; điều đó **không** có nghĩa file được chuyển format. Việc chuyển format thực sự dùng `-importkeystore` và **xác minh kho đích** sau thao tác.

Các file `.crt`/`.cer`/`.pem` thường chứa **certificate công khai** hoặc chuỗi PEM, không phải kho private key chỉ nhờ tên đuôi. Còn file `.p12` là container có thể mang **private key**: đối xử như dữ liệu nhạy cảm ngay cả khi có mật khẩu.

## 3. Danh sách lệnh cần biết

| Lệnh | Mục đích | Tác động điển hình |
| --- | --- | --- |
| `keytool -genkeypair` | Tạo private/public key pair và self-signed certificate ban đầu | **Ghi** `PrivateKeyEntry` vào keystore |
| `keytool -genseckey` | Tạo khóa bí mật đối xứng | **Ghi** `SecretKeyEntry` |
| `keytool -list` / `-list -v` | Liệt kê alias, entry type, certificate chain và fingerprint | **Đọc** metadata |
| `keytool -exportcert` | Xuất certificate của alias ra DER hoặc PEM (`-rfc`) | **Không xuất private key** |
| `keytool -printcert` | Đọc thông tin certificate từ file/nguồn | **Đọc** certificate, không tự chứng minh trust |
| `keytool -certreq` | Tạo CSR cho alias có private key | Tạo yêu cầu chứng chỉ; **chưa** phải certificate CA cấp |
| `keytool -printcertreq` | Xem CSR | **Đọc** CSR |
| `keytool -importcert` | Import trusted certificate hoặc CA reply | **Thay đổi truststore/certificate chain** theo alias |
| `keytool -importkeystore` | Copy một hoặc nhiều entry sang kho đích; có thể chuyển type | **Có thể sao chép private/secret key**, cần xử lý như bí mật |
| `keytool -changealias` | Đổi alias entry | Metadata có thể ảnh hưởng cấu hình ứng dụng |
| `keytool -storepasswd` / `-keypasswd` | Đổi mật khẩu kho hoặc entry ở type/provider được hỗ trợ | Có thể làm ứng dụng không mở được kho nếu config chưa cập nhật |
| `keytool -delete` | Xóa alias/entry | Có thể làm mất khả năng phục vụ/giải mã nếu chưa có backup |
| `keytool -list -cacerts` | Xem truststore CA mặc định do JDK quản lý | Chỉ nên **đọc** khi điều tra |

Kiểm tra danh sách tùy JDK đang dùng:

```bash
java -version
keytool -help
keytool -genkeypair -help
keytool -importkeystore -help
```

`keytool` từ JDK được chọn trên `PATH` có thể **khác phiên bản `java` chạy ứng dụng**. Hãy xác định `JAVA_HOME`/PATH và loại provider thực tế; khi cần chỉ rõ đường dẫn `$JAVA_HOME/bin/keytool` hoặc `%JAVA_HOME%\\bin\\keytool.exe` tương ứng hệ điều hành.

## 4. Chuẩn bị phòng thí nghiệm an toàn

Thực hành trong một thư mục mới, **không dùng file keystore production**:

```bash
mkdir keytool-lab
cd keytool-lab
```

Mọi thao tác ở dưới giả định `keytool` đã có trên PATH, và người học có quyền tạo file trong thư mục này. Hãy chọn một mật khẩu riêng đủ dài cho lab; không dùng mật khẩu thật của cơ sở hạ tầng.

### Nhập password mà không ghi trực tiếp vào command line

JDK 17 `keytool` hỗ trợ modifier **`:env`** hoặc **`:file`** sau các tùy chọn password:

```text
-storepass:env LAB_PASS
-keypass:env LAB_PASS
-srcstorepass:env LAB_PASS
-deststorepass:env LAB_PASS
```

**`LAB_PASS` là tên biến môi trường**, không phải mật khẩu literal. Các ví dụ ở dưới giả định biến này đã được tạo. Nếu không muốn dùng env, có thể **bỏ hẳn** `-storepass:env LAB_PASS` ở nhiều lệnh để `keytool` hỏi password tương tác; việc này phù hợp hơn khi vận hành thủ công.

Một cách nhập password tạm **không hiển thị ký tự** trên PowerShell:

```powershell
$secret = Read-Host "Lab keystore password" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $env:LAB_PASS =
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
# Sau khi hoàn tất lab:
# Remove-Item Env:LAB_PASS
```

Hoặc trên **Bash** (không chạy block này trong PowerShell):

```bash
read -r -s -p "Lab keystore password: " LAB_PASS
echo
export LAB_PASS
# Sau khi hoàn tất lab:
# unset LAB_PASS
```

**Lưu ý bảo mật:** biến môi trường vẫn có thể bị đọc trong một số bối cảnh (process inspection, crash dumps, child processes, môi trường CI). `:env` chỉ giúp tránh chèn password trực tiếp vào câu lệnh và shell history; **không phải secret vault**. Trong production, sử dụng cơ chế secret manager/credential provider phù hợp, đặt ACL cho file, kiểm soát thời gian sống của credential; không in env hoặc paste password vào log. Không chèn mật khẩu thật qua `-storepass plaintext` hoặc `-keypass plaintext` trong tài liệu/pipeline.

Với lab, chọn password ít nhất 6 ký tự theo yêu cầu của `keytool`; các môi trường thực nên đặt chính sách mạnh hơn, không dùng lại password nơi khác.

## 5. Tạo kho PKCS12 chứa private key và certificate

Lệnh tạo private/public RSA key pair, alias `service` và self-signed X.509 certificate 30 ngày dùng cho bài học:

```bash
keytool -genkeypair -alias service -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 30 -dname "CN=demo.example.invalid, OU=Training, O=Example, C=VN" -keystore service.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS
```

**Giải thích từng tham số:**

- `-genkeypair`: tạo key pair và self-signed certificate ban đầu. Certificate tự ký **chưa tự động được tin cậy bởi browser/client**; chỉ là điểm bắt đầu học CSR hoặc kiểm tra API.
- `-alias service`: tên entry; việc trùng alias trong cùng kho có thể gây lỗi hoặc cần xử lý theo loại thao tác. Dùng tên alias ổn định gắn với cấu hình ứng dụng.
- `-keyalg RSA -keysize 2048`: chọn thuật toán/kích thước key cho lab. Hệ thống mới cần tuân theo policy bảo mật và hạn sử dụng key; RSA-2048 là thông số minh họa phù hợp cho nhiều test, không bảo đảm ứng dụng phù hợp mọi tiêu chuẩn/cryptoperiod.
- `-sigalg SHA256withRSA`: thuật toán ký self-signed certificate trong lệnh này. Đừng nhầm với `RSASSA-PSS`; đây chỉ là cách ký chứng chỉ test.
- `-validity 30`: số ngày hiệu lực của self-signed certificate lab, **không** đặt thời hạn bảo mật của private key hay chính sách key rotation.
- `-dname ...`: subject distinguished name. `CN` không thay thế SAN và việc CA phát hành khi dùng TLS thật.
- `-keystore service.p12 -storetype PKCS12`: tạo kho đúng type, không dựa vào extension.
- `-storepass:env LAB_PASS -keypass:env LAB_PASS`: đọc password từ env. Dùng cùng password giúp tương thích phổ biến của PKCS12; không có nghĩa hai lớp bảo vệ hoàn toàn đồng nhất về chức năng.

Kỳ vọng **không phụ thuộc nội dung key ngẫu nhiên**: file `service.p12` xuất hiện; entry `service` có loại **`PrivateKeyEntry`** và chứa một certificate chain ban đầu (thường là self-signed certificate duy nhất). Thời điểm tạo, serial/fingerprint và phần chi tiết public key khác nhau giữa các lần chạy; **không** sao chép fingerprint mẫu như hằng số.

**Nếu muốn SAN trong chứng chỉ lab**, có thể tạo kho mới với `-ext "SAN=dns:demo.example.invalid"` trong lệnh `-genkeypair`. Đừng sửa trực tiếp `service.p12` đang tồn tại bằng cách lặp lại `-genkeypair` cùng alias nếu chưa hiểu tác động; hãy tạo test store mới hoặc backup có kiểm soát.

## 6. Liệt kê kho, alias và loại entry

Liệt kê tổng quan:

```bash
keytool -list -keystore service.p12 -storetype PKCS12 -storepass:env LAB_PASS
```

Liệt kê chi tiết đúng alias:

```bash
keytool -list -v -alias service -keystore service.p12 -storetype PKCS12 -storepass:env LAB_PASS
```

Trong kết quả chi tiết, chú ý các trường:

```text
Alias name: service
Entry type: PrivateKeyEntry
Certificate chain length: 1
Owner: CN=demo.example.invalid, ...
Issuer: CN=demo.example.invalid, ...
...
SHA256: <fingerprint thay đổi theo certificate>
```

Đây là **mẫu trường/nhãn tham khảo**, **không phải stdout chính xác**: nhãn có thể thay đổi theo locale/JDK, và chain/fingerprint phụ thuộc certificate thực tế.

- `PrivateKeyEntry`: có private key gắn với certificate chain; **`-list` không in private key**.
- `trustedCertEntry`: chỉ certificate công khai được đặt làm trust anchor trong kho tương ứng.
- `SecretKeyEntry`: một khóa đối xứng; không xuất raw key bytes khi liệt kê.

Có thể chạy `keytool -list -v -keystore service.p12 ...` không có `-alias` để xem tất cả entry. Khi có nhiều alias, `-alias` giúp xác định chính xác object đang điều tra. Không mặc định coi cùng alias trong hai file khác nhau là cùng key.

**Truy vấn không có password:** một số thao tác `-list` có thể cho phép hiển thị thông tin mà chưa xác minh integrity của keystore, đồng thời in cảnh báo. Đừng dùng dữ liệu từ một kho chưa được xác minh integrity như cơ sở ra quyết định trust/migration. Hãy cung cấp credential thích hợp khi cần xác minh.

## 7. Xuất certificate công khai bằng `-exportcert`

Xuất certificate đang gắn với alias `service` sang file PEM:

```bash
keytool -exportcert -rfc -alias service -file service.pem -keystore service.p12 -storetype PKCS12 -storepass:env LAB_PASS
```

- `-exportcert` **chỉ xuất X.509 certificate**, không xuất private key.
- `-rfc` tạo bản mã hóa Base64 PEM dạng `-----BEGIN CERTIFICATE-----` ... `-----END CERTIFICATE-----`. Nếu không có `-rfc`, mặc định xuất dạng DER binary.
- `-alias service` khi trỏ vào `PrivateKeyEntry` sẽ xuất certificate đầu của chain, tương ứng public key của private key đó. Để sao chép cả private key, `-exportcert` **không làm được**.
- `-file service.pem` tạo file certificate công khai; dù PEM có thể chia sẻ theo quy tắc trust, **không nên** xem nội dung PEM tự động chứng minh identity.

In thông tin certificate:

```bash
keytool -printcert -file service.pem
```

Thông tin cần xem trước khi dùng: Subject, Issuer, validity, serial, signature algorithm, public key algorithm/key size, SHA-256 fingerprint, SAN và các extension liên quan (nếu có). Certificate tự ký lab có `Issuer==Subject`; điều đó **không chứng minh** certificate đã được bên độc lập xác thực.

**Phân biệt PEM certificate với private key:** việc file có phần đuôi `.pem` không bảo đảm nó chỉ chứa certificate; nhiều công cụ cũng lưu private key ở PEM. Hãy xem nhãn BEGIN/END và kiểm soát dữ liệu trước khi chia sẻ. File `service.pem` ở quy trình này là certificate công khai vì do `keytool -exportcert` tạo.

## 8. Nhập trusted certificate vào kho tin cậy

Một truststore mẫu mới, tách biệt với `service.p12`:

```bash
keytool -importcert -alias service-demo -file service.pem -keystore trust.p12 -storetype PKCS12 -storepass:env LAB_PASS
```

Với alias **chưa tồn tại**, `-importcert` thêm một **`trustedCertEntry`**. Khi cần hỏi có tin certificate hay không, **không tự động bấm yes cho chứng chỉ chưa xác thực**. Trong lab, ta tự tạo certificate và có thể chủ động quan sát quy trình; trong thực tế, việc import phải đi sau **xác minh fingerprint qua một kênh độc lập đáng tin**, certificate chain và identity policy.

Kiểm tra sau import:

```bash
keytool -list -v -alias service-demo -keystore trust.p12 -storetype PKCS12 -storepass:env LAB_PASS
```

Kết quả được kỳ vọng có **`Entry type: trustedCertEntry`**, không có private key. Nếu đang điều tra truststore, hãy kiểm chứng đúng fingerprint được đối tác/CA xác nhận bên ngoài, không chỉ so fingerprint của hai file **cùng nhận từ một nguồn không tin cậy**.

### Vì sao không dùng `-noprompt` tùy tiện?

`-noprompt` có tác dụng bỏ qua tương tác ở một số lệnh, kể cả nhập trusted certificate. Trong automation có policy được kiểm chứng từ trước, nó có thể hữu ích; nhưng trên input không tin cậy, lệnh này có thể biến certificate attacker gửi thành trust anchor **mà không có bước xác nhận**. Trong bài học, cố ý **không gắn `-noprompt`** vào lệnh nhập truststore.

**Không thực hành trên `cacerts` hệ thống:** `keytool -list -cacerts` chỉ giúp xem các CA mặc định. Thêm hoặc xóa CA khỏi JDK-wide truststore ảnh hưởng nhiều ứng dụng cùng JDK, làm phát sinh drift khi nâng cấp JDK và có thể mở rộng trust quá mức. Dùng truststore riêng của ứng dụng khi thích hợp.

## 9. Tạo CSR và nhập certificate reply từ CA

Đối với private key đã có ở `service.p12`, tạo CSR:

```bash
keytool -certreq -alias service -file service.csr -keystore service.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS -ext "SAN=dns:demo.example.invalid"
```

Xem CSR:

```bash
keytool -printcertreq -file service.csr
```

`service.csr` chứa thông tin và public key cần CA xét duyệt, **không phải certificate đã được CA cấp**. Không đưa private key vào CSR. CA sẽ kiểm tra thông tin/identity theo chính sách của CA rồi trả certificate hoặc chain tương ứng. Trong sản phẩm thật, SAN và EKU/KeyUsage cần theo giao thức (TLS server/client, code signing...), không chỉ nhìn subject CN.

Nếu CA trả certificate chain hợp lệ trong file ví dụ `signed-chain.pem` và đã kiểm chứng nguồn/chuỗi CA, **nhập certificate reply về đúng alias private key `service`**:

```bash
keytool -importcert -alias service -file signed-chain.pem -keystore service.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS
```

**Lệnh nhập reply này chỉ chạy khi bạn thực sự đã nhận được `signed-chain.pem` hợp lệ từ CA**; nó không chạy trong lab tự ký mặc định vì file đó chưa có.

Cách `-importcert` hoạt động phụ thuộc alias:

- **Alias chưa tồn tại:** tạo trusted certificate entry, tức **thêm tin cậy**, không tạo private key.
- **Alias đang là `PrivateKeyEntry`:** xử lý **certificate reply/chain**, kiểm tra public key khớp với private key tương ứng và cập nhật chain khi đủ điều kiện. Đây là thao tác khác hoàn toàn với thêm trust anchor.
- Nếu certificate chain không tạo được đường tin cậy hoặc reply không tương ứng key, có thể thất bại. Kiểm tra CA roots/intermediates, chain order, file encoding và `-trustcacerts` **chỉ khi** chính sách tin cậy cho phép xem CA mặc định.

**Tránh tạo thêm alias mới để “nhập” CA reply** nếu mục tiêu là thay self-signed certificate gắn với private key ở `service`: alias mới chỉ tạo trustedCertEntry, không đưa chain vào private key entry cũ. Sau nhập, dùng `-list -v -alias service` để xem lại chain length, subject, issuer, validity và fingerprint.

## 10. Tạo khóa đối xứng trong kho với `-genseckey`

Một số ứng dụng cần `SecretKeyEntry` thay vì private/public key pair. Với JDK/provider hỗ trợ secret key trong PKCS12, có thể tạo AES key:

```bash
keytool -genseckey -alias aes-demo -keyalg AES -keysize 256 -keystore secrets.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS
```

Kiểm tra:

```bash
keytool -list -v -alias aes-demo -keystore secrets.p12 -storetype PKCS12 -storepass:env LAB_PASS
```

Kỳ vọng entry **`SecretKeyEntry`**. `-genseckey` không tạo X.509 certificate chain, nên không thể dùng `-exportcert` trên alias secret key để “lấy public certificate AES”; **AES là thuật toán đối xứng và không có public key/certificate tương ứng**.

**Bảo mật:** đây là ví dụ key dạng phần mềm và keystore file. Trong production, hệ thống yêu cầu non-exportable keys, policy wrap/unwrap, audit hoặc separation of duties có thể nên đặt key ở KMS/HSM. Đừng giả định PKCS12, JKS và PKCS11 hỗ trợ cùng một loại entry với cùng khả năng export. Việc `keytool -genseckey` thành công **không** đồng nghĩa ứng dụng đã gán quyền sử dụng key đúng mục đích.

## 11. Chuyển kho JKS sang PKCS12 bằng `-importkeystore`

Đây là thao tác **chuyển format sao chép entry**, khác việc chỉ đổi tên file. Trong lab, tạo **một kho JKS legacy riêng** để có nguồn an toàn:

```bash
keytool -genkeypair -alias legacy -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 30 -dname "CN=legacy.example.invalid" -keystore legacy.jks -storetype JKS -storepass:env LAB_PASS -keypass:env LAB_PASS
```

`JKS` ở đây dùng **chỉ để minh họa conversion**, không phải khuyến nghị tạo kho mới bằng JKS. Kiểm tra nguồn:

```bash
keytool -list -v -alias legacy -keystore legacy.jks -storetype JKS -storepass:env LAB_PASS
```

Sao chép alias `legacy` vào kho PKCS12 mới, có thể đổi alias đích thành `migrated`:

```bash
keytool -importkeystore -srckeystore legacy.jks -srcstoretype JKS -srcstorepass:env LAB_PASS -srcalias legacy -srckeypass:env LAB_PASS -destkeystore migrated.p12 -deststoretype PKCS12 -deststorepass:env LAB_PASS -destalias migrated -destkeypass:env LAB_PASS
```

Giải thích:

- `-srckeystore` và `-srcstoretype` chỉ **kho nguồn**; `-destkeystore` và `-deststoretype` chỉ **kho đích**.
- `-srcalias legacy` nhập **một entry**; `-destalias migrated` đặt alias ở đích. Nếu **bỏ `-srcalias`**, lệnh sẽ cố nhập **toàn bộ các entry** từ nguồn; cần kiểm tra va chạm alias và entry type.
- `-srcstorepass`, `-srckeypass` và các phiên bản `dest...` dùng để mở kho và key. Trong lab cùng `LAB_PASS`, nhưng production có thể khác. Khi chuyển sang PKCS12 cho công cụ thứ ba, nhiều phần mềm yêu cầu **key password = store password**; đặt `-destkeypass` phù hợp hoặc đối chiếu yêu cầu của công cụ đích.
- Khi alias đích đã có, `keytool` có thể hỏi có ghi đè hoặc đổi tên; **không tự động chọn ghi đè** trên kho production. Không dùng `-noprompt` nếu chưa có thiết kế backup/collision handling, vì có thể overwrite entry.
- `-importkeystore` **có thể mang cả private key hoặc secret key qua kho mới**. File đích `migrated.p12` phải được bảo vệ như một bản sao private key, khác hoàn toàn file certificate công khai `service.pem`.
- Lệnh sao chép không đảm bảo mọi provider/entry/algorithm có thể nhập sang mọi storetype: trường hợp unsupported hoặc password sai có thể bị bỏ qua/nhắc tương tác/thất bại. Phải kiểm kê và đối chiếu từng entry.

Kiểm tra đích:

```bash
keytool -list -v -alias migrated -keystore migrated.p12 -storetype PKCS12 -storepass:env LAB_PASS
```

Mong đợi `Entry type: PrivateKeyEntry`, certificate/public key metadata tương ứng với alias nguồn. Vì đây là **chuyển cùng key pair**, certificate fingerprint của nguồn và đích **phải khớp**, dù tên alias thay đổi. Nếu sau chuyển fingerprint/key type/chain length bất ngờ khác, không đưa kho mới vào production trước khi giải thích được.

### Checklist migration không mất dữ liệu

1. Lập inventory tất cả alias, entry type, certificate chain và những ứng dụng đang tham chiếu từng alias. Với nhiều alias, ghi lại số lượng entry trước/sau.
2. **Backup kho nguồn** bằng cơ chế bảo mật được phê duyệt; xác minh backup có thể phục hồi và đặt quyền truy cập thích hợp. Không commit keystore/key vào Git.
3. Chọn file **đích mới** để không đè kho nguồn, ghi rõ `-srcstoretype` và `-deststoretype`; xác định mật khẩu nguồn/entry/đích có thể mở.
4. Chuyển bằng `-importkeystore`, xử lý từng lỗi/va chạm alias có kiểm soát. Không giả định exit code thành công là đã nhập đủ alias trong mọi tình huống nếu có warning/skip.
5. Chạy `-list -v` ở cả hai kho, đối chiếu alias mapping, entry type, chain length, certificate fingerprint và khả năng truy xuất private key bằng ứng dụng thực tế.
6. Kiểm thử hành vi end-to-end: TLS handshake/mTLS hoặc ký/verify, alias selection và mật khẩu runtime. Private key không được coi là hoạt động chỉ vì `-list` thấy tên alias.
7. Chuyển cấu hình ứng dụng (đường dẫn, type, alias, password/secret reference), triển khai canary và có rollback đã thử.
8. Chỉ retire kho cũ sau khi dữ liệu, backup, đường rollback, retention và dependent services đều đã được rà soát; bảo đảm không còn reader cũ.

### Chuyển toàn bộ entries khi cần

Nếu muốn copy tất cả entry (và đã xử lý va chạm/trust/cert policy), bỏ `-srcalias` và `-destalias`:

```bash
keytool -importkeystore -srckeystore legacy.jks -srcstoretype JKS -srcstorepass:env LAB_PASS -destkeystore migrated-all.p12 -deststoretype PKCS12 -deststorepass:env LAB_PASS
```

Lệnh trên có thể **hỏi thêm mật khẩu từng entry** nếu không thể truy xuất key bằng source store password. Chạy có người giám sát trên lab; đừng vội thêm `-noprompt` để “khắc phục” prompt vì nó có thể khiến entry xung đột bị ghi đè hoặc entry lỗi bị bỏ qua. Đừng dùng nguyên lệnh này để chuyển toàn bộ keystore thật nếu chưa lập danh sách alias và test.

## 12. Đừng nhầm `-exportcert` với “export private key”

Bảng này là trọng tâm khi thao tác với kho có dữ liệu nhạy cảm:

| Nhu cầu | Thao tác phù hợp | Có xuất private/secret key? |
| --- | --- | --- |
| Gửi certificate public key cho bên xác minh, CA hoặc đối tác | `-exportcert -rfc` | **Không** |
| Xem certificate/fingerprint không cần key | `-printcert -file ...` | **Không** |
| Đưa CA/trusted certificate vào truststore | `-importcert` dưới alias mới | **Không** |
| Gắn CA certificate reply vào private key đã tạo | `-importcert` **cùng alias PrivateKeyEntry** | Private key **giữ trong kho**, không được xuất qua cert reply |
| Copy private key entry từ JKS sang PKCS12 | `-importkeystore` | **Có thể**, vì entry đích chứa private key |
| Tạo AES secret key trong kho | `-genseckey` | Sinh key material và lưu `SecretKeyEntry` |
| Chuyển PKCS12 thành file certificate `.pem` bằng cách đổi đuôi | **Sai thao tác** | Không chuyển định dạng; có thể làm lộ kho |

Nếu cần một `.p12` chứa private key cho phần mềm khác, `-importkeystore` là cách đưa **key entry** sang kho đích với credential bảo vệ phù hợp. File PKCS12 **chứa private key**, không an toàn để phát tán như public certificate. `keytool` không phải một công cụ chuyên dụng để xuất private key thô dưới dạng PEM không mã hóa; tránh bổ sung các bước xuất plaintext key trừ khi bài toán, chính sách và môi trường thực sự cho phép.

**Với PKCS11/HSM**, private key có thể **không xuất được**. Việc `-importkeystore` hoặc `-exportcert` có thể xuất public certificate không có nghĩa HSM cho phép copy private key. Cần đọc provider/token policy và sử dụng key handle.

## 13. Liên kết với Java `KeyStore` trong ứng dụng

`keytool` tạo kho trên CLI; ứng dụng Java phải mở **đúng format/password/alias** và chọn đúng mục đích:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(Path.of("service.p12"))) {
    store.load(input, storePassword);
}
boolean signingEntry = store.isKeyEntry("service");
Certificate certificate = store.getCertificate("service");
```

Đây là **snippet minh họa**, không phải một chương trình độc lập. Cần import `java.security.KeyStore`, `java.security.cert.Certificate`, `java.io.InputStream`, `java.nio.file.Files` và `java.nio.file.Path`; `storePassword` phải là `char[]` có được qua secret manager/prompt, không hard-code. Java xử lý checked exceptions cho file, store integrity, provider và password.

Các API hữu ích:

- `KeyStore.getInstance("PKCS12")`: chọn type cụ thể.
- `store.load(input, password)`: mở/kiểm chứng kho bằng credential cần thiết.
- `store.aliases()`, `store.containsAlias(alias)`, `store.size()`: inventory.
- `store.isKeyEntry(alias)` và `store.isCertificateEntry(alias)`: phân loại key entry vs trusted cert entry. `isKeyEntry` đúng cho private/secret key, không nói chính xác loại key.
- `store.getCertificate(alias)`: với `PrivateKeyEntry` trả certificate đầu chuỗi; với `trustedCertEntry` trả certificate; với `SecretKeyEntry` thường không có certificate.
- `store.getCertificateChain(alias)`: dùng với alias có private key và chain.
- `store.getEntry(alias, new KeyStore.PasswordProtection(entryPassword))` hoặc `getKey(alias, entryPassword)`: truy xuất key khi được phép; **không log raw key**.
- Với provider đặc biệt (HSM/PKCS11), cách `load` và `getKey` có thể khác keystore file; cần theo provider API và đừng mặc định `getEncoded()` của key không null.

Một chương trình có thể thấy entry trong `keytool -list` nhưng vẫn lỗi runtime do **chọn sai alias**, khác store type, password entry không khớp, thiếu permission đọc file, certificate chain không được client tin, hoặc thuật toán không được provider hỗ trợ.

## 14. Sự cố thường gặp khi dùng `keytool`

| Triệu chứng/lỗi | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `keytool` không tìm thấy trên terminal | Chưa cài JDK hoặc PATH/JAVA_HOME sai | Kiểm tra `java -version`, `keytool -help` và đường dẫn JDK |
| `Keystore was tampered with, or password was incorrect` hoặc lỗi mở kho | Mật khẩu sai; file/type/provider không đúng; file lỗi | Xác minh path, password và storetype từ nguồn đáng tin; không đổi đuôi để “chữa” |
| `Alias <name> does not exist` | Alias không có trong kho hiện tại | `-list` đúng path/storetype, so chính xác alias và source/dest |
| `alias already exists` khi tạo/import | Đã có entry tên đó | Kiểm kê trước; chọn alias mới hoặc quy trình thay có backup |
| File `.jks` đọc được dù không khai `-storetype JKS` | JDK/provider có thể autodetect format | Đặt type rõ ràng; không suy file đã là PKCS12 |
| `-exportcert` tạo file nhưng không có private key | Đây là hành vi **đúng** | Dùng `-importkeystore` cho entry migration có key, giữ file đích an toàn |
| Import chứng chỉ CA vào alias mới nhưng TLS server vẫn dùng self-signed | Entry mới chỉ là `trustedCertEntry` | Nhập certificate reply vào **alias PrivateKeyEntry hiện có** nếu đúng workflow |
| Certificate không được tin cậy dù `-importcert` thành công | Sai truststore runtime, fingerprint/chain không phù hợp, client khác JDK | Xác định đúng trust configuration, chain và hệ thống xác minh |
| `-certreq` chạy xong nhưng chứng chỉ vẫn tự ký | CSR không tự trở thành CA-signed cert | Gửi CSR tới CA, nhận reply, kiểm chứng và import cùng alias |
| `SecretKeyEntry` không tạo được trong type/provider | Không hỗ trợ secret key hoặc thuật toán/size đó | Kiểm tra `-genseckey -help` và provider; chọn storetype/key management phù hợp |
| `-importkeystore` nhập thiếu entries | Entry type không hỗ trợ, keypass sai, alias collision, skip/warning | Kiểm tra toàn bộ log, inventory và từng entry, không tin chỉ vào exit code |
| Sau conversion ứng dụng lỗi `UnrecoverableKeyException` | Key password và store password không phù hợp runtime | Xác minh credential cho từng entry; kiểm tra tương thích PKCS12 |
| Dùng `-noprompt` trên certificate do người ngoài gửi | Bỏ qua trust verification | Kiểm tra fingerprint qua kênh độc lập; yêu cầu phê duyệt |
| Sửa `cacerts` khiến nhiều ứng dụng thay đổi trust | Shared JDK truststore có phạm vi quá rộng | Sử dụng truststore riêng theo ứng dụng và rollout có kiểm soát |
| Kết quả `-list` hiển thị certificate nhưng không có signing ability | Đó là trustedCertEntry, không phải private key | Kiểm tra `Entry type` và cách cấp private key |
| Backup/copy `.p12` nhầm thành tài liệu công khai | File có thể mang private key | Bảo vệ như credential, giới hạn truy cập và mã hóa backup |

**Không dùng `-delete` để “làm sạch” kho khi chưa hiểu alias**. Xóa `PrivateKeyEntry` có thể làm mất private key không thể khôi phục, xóa `trustedCertEntry` có thể làm ngừng các kết nối TLS/mTLS, và xóa `SecretKeyEntry` có thể khiến dữ liệu đã mã hóa không đọc lại được.

## 15. Quy trình production: bảo mật và trách nhiệm vận hành

1. **Phân loại kho theo vai trò:** tách keystore giữ private key của service khỏi truststore chỉ chứa trusted certificates khi có ích cho least privilege. Không dùng một file chứa toàn bộ private keys của mọi tenant.
2. **Bảo vệ vật lý và logic:** chỉ cấp quyền đọc file và mật khẩu cho đúng principal; đặt filesystem ACL, encryption-at-rest khi phù hợp, secret manager, backup/restore và audit. Không commit `*.p12`, `*.jks` hoặc file password vào source repo.
3. **Dùng keytool đúng môi trường:** luôn xác nhận `java -version`, `keytool -help` và provider. Chọn `-storetype` rõ, tên alias ổn định và phân biệt key password với store password.
4. **Quản lý certificate trust:** không tự import certificate chỉ vì nó có định dạng X.509. Kiểm tra subject/SAN, issuer, key usage, thời hạn, fingerprint/chain theo đúng yêu cầu protocol; xem nguồn trust anchor là gì.
5. **Sao lưu trước khi ghi:** thao tác `-genkeypair`, `-genseckey`, `-importcert`, `-importkeystore`, `-changealias`, `-storepasswd` và `-delete` có thể thay kho. Backup có bảo vệ và phục hồi thử được quan trọng hơn chỉ copy file một lần.
6. **Định nghĩa key lifecycle:** ngày hết hạn certificate không đồng nghĩa private key đã tự xoay; một PKCS12 conversion cũng không phải key rotation. Key rotation cần phát hành key mới, cập nhật certificate/peer trust và kiểm tra migration/rollback.
7. **Hỗ trợ non-exportable keys:** với yêu cầu HSM/KMS/PKCS11, dùng cơ chế token/provider và policy thay vì lén chuyển key ra file PKCS12. Key extraction có thể bị cấm hoặc không hỗ trợ.
8. **Kiểm soát kết quả/telemetry:** ghi alias, entry type, storetype, key ID/serial/fingerprint có kiểm soát và mã lỗi; không ghi storepass/keypass, private key, plaintext key hoặc secret dump.
9. **Tách môi trường:** dev/test/prod dùng keys, CA, truststore, password và policy riêng. Chứng chỉ `CN=*.example.invalid` tự ký trong lab không được đưa làm CA/prod identity.
10. **Tự động hóa an toàn:** tránh dùng `-noprompt` nếu không có bước kiểm tra trước; đặt secret source riêng, đảm bảo file đích mới/alias không xung đột, kiểm tra exit code + cảnh báo và xác minh entry inventory sau write.

Các hệ thống TLS/mTLS thực tế còn cần runtime cấu hình đúng Java `javax.net.ssl.keyStore` / `trustStore` và password/type, hoặc cấu hình TLS của framework. **Không mặc định** việc file đã tồn tại là service sẽ tự nạp file đó; test handshake/cert chain/authorization trước khi phát hành.

## 16. Bài tập thực hành có tiêu chí

1. **Tạo kho:** chạy `-genkeypair` trong thư mục test, nêu khác biệt giữa file `service.p12`, alias `service`, private key và self-signed certificate. Xác minh `PrivateKeyEntry` bằng `-list -v`.
2. **Xuất chứng chỉ:** chạy `-exportcert -rfc`, xem PEM bằng editor và `-printcert`. Giải thích vì sao có thể gửi file certificate nhưng **không được chia sẻ `service.p12`**.
3. **Nhập truststore:** kiểm tra fingerprint của certificate lab rồi `-importcert` vào `trust.p12` dưới alias mới. Chứng minh entry đích là `trustedCertEntry`, không phải `PrivateKeyEntry`.
4. **CSR:** chạy `-certreq` và `-printcertreq`. Chỉ ra public key/subject/extension trong CSR, giải thích vì sao chưa phải certificate CA-signed.
5. **Secret key:** tạo `secrets.p12` với AES-256 bằng `-genseckey`. Kiểm tra `SecretKeyEntry`; thử `-exportcert` trên alias AES và giải thích vì sao không thể lấy X.509 certificate.
6. **Chuyển format:** tạo `legacy.jks` rồi dùng `-importkeystore` sang `migrated.p12`. So sánh entry type, certificate fingerprint và khả năng truy cập alias. Tại sao đổi extension file không tương đương conversion?
7. **Chuyển nhiều entries:** bổ sung một alias vào kho nguồn **lab**, sau đó chuyển toàn bộ sang kho đích mới. Đếm entries trước/sau, xử lý password prompt/alias collision mà không dùng `-noprompt` bừa bãi.
8. **Phân biệt password:** tạo mô hình có source key password khác source store password (nếu JKS provider hỗ trợ), rồi giải thích công dụng của `-srcstorepass` và `-srckeypass` khi import. Kiểm tra chính sách dest keypass/storepass của ứng dụng đích.
9. **Threat modeling:** một file `.p12` đã được đẩy lên repository và bị clone. Tại sao xóa commit hiện tại không đủ? Hãy liệt kê các bước xử lý private-key compromise, thu hồi/reissue và dọn lịch sử/phạm vi tác động theo quy trình bảo mật.
10. **Trust mismatch:** bên gửi một certificate tự ký mới rồi yêu cầu import vào kho trust hệ thống. Những bước xác thực độc lập nào phải xảy ra trước khi chấp nhận?
11. **Runtime:** một service báo lỗi “không tìm thấy alias” dù `keytool -list` từ máy vận hành thấy alias. Kiểm tra PATH/JDK, file path, container mount, storetype, alias case/entry password và quyền truy cập theo thứ tự.
12. **Review migration:** xem xét một script chạy `-importkeystore -noprompt` lên kho đích đã chứa alias quan trọng. Xác định rủi ro overwrite/skip và đề xuất quy trình có backup + inventory + verify.

**Tiêu chí hoàn thành:** tự tạo PKCS12 lab, nhận diện đúng cả ba loại entry, xuất certificate không lộ private key, nhập trusted certificate có xác minh, biết CSR/CA reply cùng alias, chuyển JKS sang PKCS12 mà không mất key/chain, và mô tả rõ những rủi ro password, trust, backup, alias collision và provider.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — The keytool Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): cú pháp, options, import/export/conversion, bảo vệ password `:env`/`:file`.
- [Java SE 17 `KeyStore` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): `PrivateKeyEntry`, `SecretKeyEntry`, `TrustedCertificateEntry`, `load`, `getEntry`.
- [Java SE 17 Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): `PKCS12`, `JKS`, thuật toán hỗ trợ và tên chuẩn.
- [Dev.java — keytool: Managing Your Keystore](https://dev.java/learn/jvm/tool/security/keytool/): hướng dẫn chính thức về lệnh và nhập certificate.
- [Oracle Java SE 17 `KeyStore.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.Builder.html): cách cấu hình tạo và mở `KeyStore` qua builder/provider.
