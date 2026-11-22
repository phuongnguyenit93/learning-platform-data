# Bảo vệ mật khẩu keystore bằng keytool

`keytool` là công cụ quản lý key pair, certificate và keystore đi kèm JDK. Mật khẩu của keystore giúp bảo vệ tính toàn vẹn của kho khóa và kiểm soát quyền truy cập tới private key hoặc secret key. Khi vận hành ứng dụng Java, cần hiểu rõ mật khẩu nào bảo vệ toàn bộ kho, mật khẩu nào bảo vệ riêng một entry, và cách định dạng keystore ảnh hưởng đến việc thay đổi chúng.

Bài này tập trung vào keystore password và key password, cách tạo và kiểm tra keystore, đổi mật khẩu, chuyển JKS sang PKCS12, bảo vệ secret trong ứng dụng/CI và xử lý tình huống quên hoặc lộ mật khẩu.

## 1. Keystore, truststore và entry

Keystore lưu các entry mật mã, mỗi entry được nhận diện bằng một alias.

| Loại entry | Nội dung | Lưu ý bảo mật |
|---|---|---|
| `PrivateKeyEntry` | Private key và certificate chain tương ứng. | Private key rất nhạy cảm, cần bảo vệ. |
| `SecretKeyEntry` | Secret key đối xứng, ví dụ khóa AES. | Khóa có thể dùng để mã hóa hoặc giải mã dữ liệu. |
| `trustedCertEntry` | Certificate được tin cậy, thường là certificate CA hoặc server. | Certificate là dữ liệu công khai; cần bảo vệ tính toàn vẹn của truststore. |

Keystore thường lưu private key của server, ứng dụng hoặc signer. Truststore thường lưu certificate của CA hoặc dịch vụ mà ứng dụng tin cậy. Một file có thể chứa nhiều loại entry; vai trò phụ thuộc cách ứng dụng sử dụng nó.

Mật khẩu truststore không làm certificate công khai trở thành bí mật. Nó chủ yếu bảo vệ tính toàn vẹn của kho và ngăn sửa đổi trái phép. Với private key entry, mật khẩu còn tham gia bảo vệ khóa riêng được lưu trong file.

## 2. Keystore password và key password

Hai loại mật khẩu có phạm vi khác nhau:

| Mật khẩu | Tùy chọn keytool | Phạm vi và tác dụng |
|---|---|---|
| Keystore password | `-storepass` | Mở kho và kiểm tra tính toàn vẹn; với PKCS12, mật khẩu này cũng bảo vệ private key material. |
| Key password | `-keypass` | Mở khóa riêng của một entry khi cần dùng private key hoặc secret key. |

Trong JKS:

- Store password bảo vệ tính toàn vẹn của file keystore.
- Key password bảo vệ riêng private key hoặc secret key entry.
- Hai mật khẩu có thể khác nhau.
- Đổi store password không tự đổi key password của từng entry.

Trong PKCS12 với provider chuẩn của JDK:

- Store password và private-key password phải giống nhau.
- Nếu chỉ định `-keypass` khác `-storepass`, keytool cảnh báo và bỏ qua giá trị riêng đó.
- `keytool -keypasswd` không được hỗ trợ cho PKCS12.
- Đổi store password cũng thay đổi mật khẩu dùng để bảo vệ private key trong kho.

Vì vậy, hãy xác định định dạng keystore trước khi thay đổi credential hoặc viết script vận hành.

## 3. JKS và PKCS12

JKS là định dạng keystore truyền thống của Java. PKCS12 là định dạng tiêu chuẩn được hỗ trợ rộng rãi và là mặc định của các JDK hiện đại.

| Đặc điểm | JKS | PKCS12 |
|---|---|---|
| Định dạng | Định dạng riêng của Java | Định dạng tiêu chuẩn trao đổi khóa/chứng thư |
| Mặc định trên JDK 9+ | Không | Có |
| Store password | Bảo vệ tính toàn vẹn | Bảo vệ kho và private key material |
| Key password riêng | Có thể khác store password | Provider PKCS12 chuẩn dùng chung store password |
| `keytool -keypasswd` | Hỗ trợ | Không hỗ trợ |
| Tương tác với công cụ khác | Hẹp hơn | Rộng hơn |

Không nên đoán định dạng chỉ từ phần mở rộng file. Một file tên `.jks` vẫn có thể chứa định dạng khác nếu được tạo như vậy. Dùng `-storetype` rõ ràng khi cần build tái lập.

Kiểm tra loại keystore:

~~~bash
keytool -list -keystore service.p12
~~~

Keytool hiển thị thông tin tương tự:

~~~text
Keystore type: PKCS12
Keystore provider: SUN
~~~

Có thể chỉ định tường minh:

~~~bash
keytool -list -keystore service.p12 -storetype PKCS12
keytool -list -keystore legacy.jks -storetype JKS
~~~

Khi tạo keystore mới, nên ưu tiên PKCS12 trừ khi hệ thống cũ hoặc provider cụ thể yêu cầu JKS.

## 4. Tạo keystore có mật khẩu

Ví dụ tạo key pair RSA và certificate tự ký cho môi trường thử nghiệm:

~~~bash
keytool -genkeypair \
  -alias service-signing \
  -keyalg RSA \
  -keysize 3072 \
  -dname "CN=Example Service" \
  -validity 365 \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Khi không truyền `-storepass`, keytool yêu cầu nhập mật khẩu trên terminal. Với PKCS12, dùng cùng mật khẩu cho private key entry; nếu keytool hỏi mật khẩu riêng của alias, nhấn Enter để dùng mật khẩu keystore khi được yêu cầu.

Keytool yêu cầu mật khẩu keystore tối thiểu sáu ký tự khi tạo file. Đây chỉ là điều kiện tối thiểu, không phải khuyến nghị bảo mật. Hãy dùng mật khẩu dài, ngẫu nhiên, duy nhất và lưu trong password manager hoặc secret manager.

`-genkeypair` tạo key pair và certificate tự ký. Certificate tự ký không tự động được client hoặc trình duyệt tin cậy. Môi trường production thường cần tạo CSR, nhận certificate do CA phù hợp cấp và quản lý private key theo quy trình riêng.

## 5. Kiểm tra keystore và alias

Liệt kê entry:

~~~bash
keytool -list -keystore service.p12 -storetype PKCS12
~~~

Xem chi tiết:

~~~bash
keytool -list -v -keystore service.p12 -storetype PKCS12
~~~

Kết quả có thể chứa:

~~~text
Your keystore contains 1 entry

service-signing, ..., PrivateKeyEntry,
Certificate fingerprint (SHA-256): ...
~~~

`PrivateKeyEntry` cho biết alias chứa private key và certificate chain. `trustedCertEntry` cho biết entry là certificate tin cậy, không phải private key.

`-list -v` hiển thị thông tin entry và certificate; nó không chứng minh private key có thể được mở và sử dụng. Để kiểm tra quyền truy cập private key, có thể tạo certificate signing request (CSR):

~~~bash
keytool -certreq \
  -alias service-signing \
  -keystore service.p12 \
  -storetype PKCS12 \
  -file service.csr
~~~

Lệnh yêu cầu mật khẩu phù hợp và tạo CSR từ private key. Đây là phép kiểm tra hữu ích sau khi đổi mật khẩu hoặc chuyển định dạng.

## 6. Nhập mật khẩu an toàn

Khi thao tác thủ công, ưu tiên bỏ tham số mật khẩu để keytool hỏi trực tiếp trên terminal:

~~~bash
keytool -list -keystore service.p12 -storetype PKCS12
~~~

Tránh viết mật khẩu thật ngay trên command line:

~~~bash
keytool -list -keystore service.p12 -storepass MyRealPassword123
~~~

Giá trị truyền qua `-storepass`, `-keypass`, `-new`, `-srcstorepass` hoặc `-deststorepass` có thể xuất hiện trong shell history, log CI hoặc danh sách tham số tiến trình tùy môi trường. Việc terminal không hiển thị mật khẩu khi nhập tương tác không có nghĩa là giá trị truyền trên command line được bảo vệ khỏi các nơi này.

Nguyên tắc nên áp dụng:

- Không commit keystore hoặc mật khẩu vào Git.
- Không đặt mật khẩu thật trong script, file cấu hình công khai hoặc tài liệu.
- Không in command line có chứa secret vào log.
- Dùng mật khẩu ngẫu nhiên, đủ dài và không tái sử dụng giữa các môi trường.
- Giới hạn quyền đọc file keystore và quyền truy cập secret.
- Dùng secret manager hoặc cơ chế cấp credential được tổ chức phê duyệt cho CI.
- Xóa file tạm chứa secret theo quy trình an toàn sau khi sử dụng.

Tùy chọn `-protected` dùng cơ chế protected authentication path do provider hỗ trợ, thường liên quan thiết bị hoặc token mật mã. Nó không phải tùy chọn chung để đọc mật khẩu từ biến môi trường và không tự động làm mọi lệnh keytool an toàn hơn.

## 7. Đổi mật khẩu keystore bằng -storepasswd

Lệnh `-storepasswd` thay đổi mật khẩu của toàn bộ keystore:

~~~bash
keytool -storepasswd \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Keytool yêu cầu mật khẩu hiện tại và mật khẩu mới khi chạy tương tác. Sau khi đổi, kiểm tra lại:

~~~bash
keytool -list -keystore service.p12 -storetype PKCS12
~~~

Với JKS, lệnh cũng đổi store password:

~~~bash
keytool -storepasswd \
  -keystore legacy.jks \
  -storetype JKS
~~~

Trong JKS, đổi store password không đổi key password riêng của entry. Nếu ứng dụng dùng cả store password và key password, hãy cập nhật đúng secret tương ứng trong cấu hình vận hành.

Trong PKCS12 chuẩn của JDK, store password và key password dùng chung. Đổi store password là đổi mật khẩu bảo vệ private key trong file PKCS12. Sau khi đổi, kiểm tra cả việc mở keystore và khả năng truy cập private key, chẳng hạn bằng `keytool -certreq`.

Đổi mật khẩu không thay đổi public key, private key hoặc certificate. Nó chỉ thay đổi cách bảo vệ dữ liệu khóa trong keystore.

## 8. Đổi mật khẩu riêng của private key trong JKS

Với JKS, có thể thay đổi mật khẩu của một key entry bằng `-keypasswd`:

~~~bash
keytool -keypasswd \
  -alias service-signing \
  -keystore legacy.jks \
  -storetype JKS
~~~

Keytool sẽ yêu cầu mật khẩu keystore, mật khẩu hiện tại của private key entry và mật khẩu mới cho entry.

Sau khi đổi, xác minh bằng CSR:

~~~bash
keytool -certreq \
  -alias service-signing \
  -keystore legacy.jks \
  -storetype JKS \
  -file service.csr
~~~

Trong lần chạy xác minh, nhập store password và key password mới khi được yêu cầu.

`-keypasswd` áp dụng cho alias chứa private key hoặc secret key phù hợp. Không thể đổi mật khẩu của `trustedCertEntry` vì entry đó không chứa khóa bí mật được bảo vệ bằng key password.

Nếu key password khác store password, phải quản lý hai secret riêng. Việc chỉ đổi một mật khẩu không cập nhật mật khẩu còn lại.

## 9. Giới hạn mật khẩu của PKCS12

Với PKCS12 provider chuẩn của JDK 24.0.2, mật khẩu private key không thể khác mật khẩu keystore.

Nếu chỉ định hai mật khẩu khác nhau khi tạo PKCS12, keytool cảnh báo tương tự:

~~~text
Warning: Different store and key passwords not supported for PKCS12 KeyStores.
Ignoring user-specified -keypass value.
~~~

Lệnh:

~~~bash
keytool -keypasswd \
  -alias service-signing \
  -keystore service.p12 \
  -storetype PKCS12
~~~

không được hỗ trợ và kết thúc với lỗi:

~~~text
java.lang.UnsupportedOperationException:
-keypasswd commands not supported if -storetype is PKCS12
~~~

Đây là hành vi của provider chuẩn được kiểm thử. Provider khác có thể có hành vi riêng; hãy kiểm tra tài liệu provider trước khi xây dựng quy trình phụ thuộc vào nó.

Nếu dùng PKCS12, bảo vệ store password như secret có quyền truy cập private key. Đừng giả định rằng có thể đặt thêm một key password riêng như khi dùng JKS.

## 10. Chuyển JKS sang PKCS12

Khi chuyển keystore JKS cũ sang PKCS12, hãy tạo file đích riêng. Không chuyển đổi đè lên file nguồn trong bước đầu tiên.

Ví dụ chuyển một alias:

~~~bash
keytool -importkeystore \
  -srckeystore legacy.jks \
  -srcstoretype JKS \
  -srcalias service-signing \
  -destkeystore migrated.p12 \
  -deststoretype PKCS12 \
  -destalias service-signing
~~~

Keytool yêu cầu mật khẩu source store, mật khẩu key entry nguồn nếu cần và mật khẩu destination store. PKCS12 dùng destination store password để bảo vệ private key entry.

Có thể chuyển toàn bộ entry bằng cách bỏ `-srcalias` và `-destalias`:

~~~bash
keytool -importkeystore \
  -srckeystore legacy.jks \
  -srcstoretype JKS \
  -destkeystore migrated.p12 \
  -deststoretype PKCS12
~~~

Khi chuyển nhiều entry, keytool có thể cần mật khẩu của từng private key. Hãy làm theo prompt và kiểm tra mọi alias sau khi nhập.

Sau khi chuyển:

~~~bash
keytool -list -v -keystore migrated.p12 -storetype PKCS12
~~~

Kiểm tra alias quan trọng và thử tạo CSR từ private key:

~~~bash
keytool -certreq \
  -alias service-signing \
  -keystore migrated.p12 \
  -storetype PKCS12 \
  -file migrated-check.csr
~~~

Chỉ thay cấu hình ứng dụng sang file mới sau khi đã kiểm tra entry, certificate chain, private key access và thao tác ký/xác thực thực tế. Giữ bản sao lưu JKS nguồn trong thời gian chuyển đổi theo chính sách lưu trữ của tổ chức.

## 11. Bảo vệ truststore

Truststore thường chứa certificate công khai của CA hoặc dịch vụ mà ứng dụng tin cậy. Certificate không phải private key, nhưng việc sửa truststore có thể khiến ứng dụng tin nhầm một endpoint hoặc từ chối kết nối hợp lệ.

Liệt kê truststore:

~~~bash
keytool -list -v \
  -keystore truststore.p12 \
  -storetype PKCS12
~~~

Khi import certificate tin cậy:

~~~bash
keytool -importcert \
  -alias internal-ca \
  -file internal-ca.cer \
  -keystore truststore.p12 \
  -storetype PKCS12
~~~

Trước khi chấp nhận certificate, xác minh fingerprint qua một kênh đáng tin cậy. Không đồng ý import certificate chỉ vì keytool hỏi xác nhận; certificate giả có thể bị thêm thành trust anchor trái phép.

Password truststore giúp bảo vệ tính toàn vẹn của kho, không làm certificate công khai trở thành dữ liệu bí mật. Cần kiểm soát quyền ghi truststore chặt chẽ vì thay đổi nội dung có thể thay đổi quyết định tin cậy TLS của ứng dụng.

## 12. Quản lý mật khẩu trong ứng dụng và CI

Ứng dụng Java thường nạp keystore bằng API `KeyStore`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

char[] password = obtainPasswordFromApprovedSecretSource();

KeyStore keyStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(Path.of("service.p12"))) {
    keyStore.load(input, password);
}
~~~

`obtainPasswordFromApprovedSecretSource()` là phần tích hợp của ứng dụng với secret manager hoặc cơ chế cấp secret của môi trường; đây không phải API JDK có sẵn. Ví dụ minh họa cách truyền `char[]` cho `KeyStore.load`, không phải chương trình độc lập có thể biên dịch nguyên trạng.

Khi xử lý mật khẩu trong Java:

- Ưu tiên `char[]` thay cho `String` khi API cho phép, vì mảng có thể được ghi đè sau khi dùng.
- Gọi `Arrays.fill(password, (char) 0)` trong khối `finally` khi không còn cần mật khẩu.
- Không ghi mật khẩu vào log, exception message hoặc telemetry.
- Không giữ secret lâu hơn thời gian cần thiết.
- Kiểm soát quyền đọc keystore và secret theo nguyên tắc least privilege.

Ví dụ xóa mảng sau khi sử dụng:

~~~java
try {
    keyStore.load(input, password);
} finally {
    java.util.Arrays.fill(password, (char) 0);
}
~~~

Đây là biện pháp giảm thời gian secret tồn tại trong bộ nhớ; nó không bảo đảm mọi bản sao nội bộ của provider hoặc JVM đã bị xóa.

Trong CI, nên lấy secret từ kho bí mật của nền tảng và hạn chế job nào được phép truy cập. Một số thao tác keytool không có giao diện nhập secret không tương tác an toàn cho mọi môi trường; đừng tự động đưa mật khẩu vào tham số dòng lệnh mà không đánh giá rủi ro lộ qua process list và log.

## 13. Hardware token và protected authentication path

Với khóa có giá trị cao, tổ chức có thể lưu private key trong HSM hoặc thiết bị PKCS#11 thay vì file keystore thông thường. Private key có thể không rời khỏi thiết bị; thao tác ký được thực hiện bởi provider kết nối thiết bị.

Keytool có các tùy chọn provider như `-addprovider`, `-providerarg`, `-providerclass` và `-providerpath`. Một số lệnh/provider cũng hỗ trợ `-protected`.

`-protected` yêu cầu cơ chế xác thực được bảo vệ của provider. Cách nhập PIN, xác nhận thao tác và bảo vệ credential phụ thuộc thiết bị, driver và provider.

Không dùng `-protected` như cách thay thế chung cho password manager hoặc biến môi trường. Hãy theo tài liệu của HSM/provider, kiểm tra lệnh nào hỗ trợ tùy chọn này và thử nghiệm quy trình khôi phục thiết bị trước khi đưa vào production.

## 14. Quên mật khẩu hoặc nghi ngờ mật khẩu bị lộ

Keytool không có lệnh bỏ qua hoặc khôi phục mật khẩu keystore đã quên. Không thể đơn giản đọc private key từ file nếu không có credential hợp lệ.

Nếu quên mật khẩu:

1. Kiểm tra password manager hoặc secret manager được tổ chức phê duyệt.
2. Tìm bản backup hợp lệ cùng thông tin credential được lưu theo chính sách.
3. Xác định hệ thống còn bản key/certificate nguồn hoặc bản sao keystore khác hay không.
4. Nếu không thể truy cập private key, tạo key pair mới và thực hiện quy trình cấp certificate lại khi cần.
5. Cập nhật ứng dụng, certificate chain, trust và quy trình triển khai tương ứng.

Nếu nghi ngờ mật khẩu bị lộ:

1. Xác định keystore và alias bị ảnh hưởng.
2. Thu hồi quyền truy cập secret cũ và kiểm tra log truy cập.
3. Nếu private key có nguy cơ bị sao chép, coi khóa đã bị xâm phạm; chỉ đổi mật khẩu file không làm khóa cũ an toàn trở lại.
4. Tạo key pair mới, yêu cầu certificate mới và thu hồi certificate cũ theo chính sách CA.
5. Cập nhật dịch vụ, client, truststore và hệ thống phụ thuộc.
6. Xóa hoặc lưu giữ bản cũ theo quy trình ứng phó sự cố.

Đổi mật khẩu keystore là rotation của credential bảo vệ file, không phải rotation của key material. Khi private key đã lộ, cần thay khóa chứ không chỉ thay password.

## 15. Backup và quyền truy cập file

Mật khẩu mạnh không đủ nếu file keystore có quyền đọc quá rộng hoặc không có backup đáng tin cậy.

Thực hành vận hành:

- Đặt file keystore trong thư mục chỉ tài khoản dịch vụ cần thiết mới đọc được.
- Giới hạn quyền ghi để ngăn thay thế certificate hoặc private key trái phép.
- Mã hóa backup theo chính sách lưu trữ của tổ chức.
- Lưu mật khẩu backup tách khỏi file backup.
- Kiểm tra khả năng khôi phục định kỳ trong môi trường kiểm thử.
- Ghi lại alias, loại keystore, provider, certificate fingerprint và ngày hết hạn.
- Không gửi keystore qua email/chat hoặc lưu trong repository công khai.
- Xác định người chịu trách nhiệm rotation và quy trình bàn giao credential.

Trên Linux, quyền file có thể được giới hạn bằng `chmod 600 service.p12` nếu user chạy ứng dụng là chủ sở hữu. Trên Windows, dùng ACL để chỉ cấp quyền đọc cho tài khoản dịch vụ và nhóm quản trị cần thiết.

## 16. Lỗi thường gặp khi dùng mật khẩu keytool

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Keystore was tampered with, or password was incorrect` | Store password sai, file hỏng hoặc định dạng/provider không đúng. | Kiểm tra password manager, `-storetype`, provider và backup; không ghi đè file gốc. |
| `UnrecoverableKeyException` | Key password sai hoặc private key entry không thể giải mã. | Xác minh key password riêng trong JKS; với PKCS12 dùng store password. |
| `Keystore password must be at least 6 characters` | Mật khẩu tạo keystore ngắn hơn mức tối thiểu của keytool. | Dùng mật khẩu dài, ngẫu nhiên và duy nhất. |
| `-keypasswd commands not supported if -storetype is PKCS12` | PKCS12 provider chuẩn không hỗ trợ đổi key password riêng. | Dùng `-storepasswd` để đổi mật khẩu PKCS12; không gọi `-keypasswd`. |
| Cảnh báo different store and key passwords | Đã chỉ định `-keypass` khác `-storepass` khi tạo PKCS12. | Dùng cùng mật khẩu cho PKCS12 hoặc chọn JKS nếu thực sự cần mật khẩu entry riêng. |
| `Alias ... does not exist` | Alias sai hoặc entry nằm trong file khác. | Dùng `keytool -list` để xác định alias chính xác. |
| Đổi store password xong ứng dụng không mở được khóa | Cấu hình ứng dụng vẫn dùng mật khẩu cũ hoặc JKS key password riêng chưa được cập nhật. | Cập nhật secret phù hợp với định dạng và xác minh bằng thao tác dùng private key. |
| CI chạy được ở máy local nhưng thất bại | Secret không được cấp cho job, bị trim/escape hoặc lộ qua tham số. | Kiểm tra cơ chế secret injection, quyền job và log; không in giá trị bí mật. |

Khi chẩn đoán, không thử nhiều mật khẩu bằng script không kiểm soát hoặc tự động ghi lại keystore. Hãy làm việc trên bản sao được bảo vệ và giữ lại file gốc để tránh mất dữ liệu.

## 17. Quy trình bảo vệ mật khẩu khuyến nghị

Một quy trình thực tế cho keystore chứa private key:

1. Chọn định dạng PKCS12 trừ khi có yêu cầu tương thích cụ thể với JKS/provider khác.
2. Tạo keystore bằng `keytool -genkeypair` và nhập password qua prompt tương tác.
3. Lưu password trong password manager hoặc secret manager được phê duyệt.
4. Giới hạn quyền đọc/ghi file keystore ở cấp hệ điều hành.
5. Kiểm tra alias, entry type và certificate fingerprint bằng `keytool -list -v`.
6. Thử thao tác dùng private key, chẳng hạn tạo CSR hoặc ký dữ liệu trong môi trường kiểm thử.
7. Backup file và credential theo hai kênh bảo vệ phù hợp.
8. Định kỳ rà soát quyền truy cập và lịch rotation.
9. Khi đổi password, xác định rõ định dạng JKS/PKCS12 và cập nhật secret của ứng dụng.
10. Khi nghi ngờ private key bị lộ, tạo khóa mới và thay certificate; chỉ đổi password là chưa đủ.

## 18. Checklist trước khi đưa keystore vào production

- Đã xác định chính xác loại keystore và provider.
- Đã phân biệt store password với key password.
- Đã dùng password dài, ngẫu nhiên, duy nhất.
- Không ghi password trong source code, Git hoặc log.
- Keystore có quyền truy cập file phù hợp với tài khoản dịch vụ.
- Truststore chỉ chứa certificate đã được xác minh fingerprint.
- Đã thử mở keystore và sử dụng private key.
- Đã kiểm tra cấu hình password của ứng dụng sau khi rotation.
- Có backup được mã hóa và đã thử khôi phục.
- Có người chịu trách nhiệm quản lý credential và rotation.
- Có quy trình thay key/certificate nếu private key bị xâm phạm.

Bảo vệ mật khẩu bằng keytool đòi hỏi hiểu rõ định dạng keystore và vai trò của từng credential. JKS có thể tách store password và key password; PKCS12 chuẩn của JDK dùng chung mật khẩu cho kho và private key. Hãy nhập secret qua prompt khi thao tác thủ công, lưu credential trong hệ thống quản lý bí mật, kiểm soát quyền truy cập file và xác minh khả năng sử dụng private key sau mỗi lần đổi hoặc chuyển keystore.
