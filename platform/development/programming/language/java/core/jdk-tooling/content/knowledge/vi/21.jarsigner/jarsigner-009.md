# Xử lý lỗi xác thực chữ ký JAR bằng jarsigner

`jarsigner -verify` là lệnh của JDK để kiểm tra chữ ký số và tính toàn vẹn của một JAR đã ký. Khi kết quả xác thực lỗi, cần xác định lỗi nằm ở **nội dung JAR**, **cấu trúc chữ ký**, **certificate của người ký**, hay **chính sách bảo mật của JDK**.

Một thông báo `jar verified` chưa đủ để kết luận JAR an toàn. JAR có thể xác minh được chữ ký mật mã nhưng certificate của người ký chưa được tin cậy, hoặc JAR có thêm entry chưa được ký. Với quy trình phát hành và CI, hãy dùng `-strict` để biến các cảnh báo nghiêm trọng thành lỗi có exit code khác 0.

## 1. Chữ ký JAR bảo vệ điều gì?

Khi ký một JAR, `jarsigner` dùng private key của người phát hành để ký dữ liệu liên quan tới manifest. JAR đã ký thường có thêm các tệp trong `META-INF/`:

- `MANIFEST.MF`: chứa digest (hash) của từng entry được ký, chẳng hạn class file hoặc resource.
- Tệp chữ ký `.SF`: chứa digest của manifest hoặc các section của manifest.
- Tệp signature block `.RSA`, `.DSA` hoặc `.EC`: chứa chữ ký của tệp .SF và certificate/certificate chain tương ứng với public key của người ký.

Khi xác minh, công cụ kiểm tra chữ ký của .SF, kiểm tra digest giữa .SF và manifest, rồi tính lại digest của các entry được ký để so sánh với giá trị trong manifest. Nếu nội dung entry thay đổi sau khi ký, digest không còn khớp và xác minh thất bại.

Chữ ký JAR giúp phát hiện nội dung đã bị thay đổi kể từ khi ký và liên kết chữ ký với public key của người ký. Chữ ký không chứng minh phần mềm không có mã độc, không thay thế code review, và không tự chứng minh người sở hữu certificate là một tổ chức đáng tin cậy.

## 2. Chạy lệnh xác minh cơ bản

Cú pháp:

~~~sh
jarsigner -verify <jar-file>
~~~

Ví dụ:

~~~sh
jarsigner -verify app-signed.jar
~~~

Nếu chữ ký và digest của các entry được ký hợp lệ, đầu ra thường có dòng:

~~~text
jar verified.
~~~

Để xem từng entry và certificate của người ký:

~~~sh
jarsigner -verify -verbose -certs app-signed.jar
~~~

Các tùy chọn:

| Tùy chọn | Tác dụng |
|---|---|
| `-verify` | Xác minh chữ ký của JAR |
| `-verbose` | Hiển thị chi tiết quá trình xác minh và từng entry |
| `-certs` | Hiển thị certificate của signer khi dùng cùng -verify và -verbose |
| `-strict` | Coi cảnh báo nghiêm trọng là lỗi và trả exit code khác 0 |
| `-keystore <file>` | Chỉ định keystore dùng để đối chiếu certificate/alias của signer |
| `-storetype <type>` | Chỉ định loại keystore, ví dụ PKCS12 |
| `-revCheck` | Bật kiểm tra trạng thái thu hồi certificate |
| `-verbose:all` | Hiển thị thông tin chi tiết cho tất cả entry |

`-certs` chỉ có ý nghĩa hiển thị certificate trong chế độ verify verbose. Nó giúp xem Subject, Issuer, thời hạn và chain được đóng gói trong chữ ký. Nếu muốn đối chiếu signer với alias cụ thể, có thể cung cấp keystore và alias theo cú pháp verify của `jarsigner`.

## 3. Đọc ký hiệu trong kết quả verbose

Khi chạy `jarsigner -verify -verbose`, mỗi entry có thể có các ký hiệu ở đầu dòng:

| Ký hiệu | Ý nghĩa |
|---|---|
| `s` | Chữ ký của entry đã được xác minh |
| `m` | Entry được liệt kê trong manifest |
| `k` | Có ít nhất một certificate được tìm thấy trong keystore đang dùng để đối chiếu |
| `?` | Entry không được ký (unsigned entry) |

Ví dụ một entry có `sm` thường đã được xác minh chữ ký và có mặt trong manifest. Entry có `?` là nội dung chưa được chữ ký bảo vệ. Đừng nhầm `k` với việc certificate đã được CA tin cậy; ký hiệu này cho biết certificate khớp một entry trong keystore được kiểm tra, còn việc xác thực chain và trust policy cần được đánh giá riêng.

Kết quả verbose có thể liệt kê các tệp `META-INF` như manifest, .SF và signature block. Chúng là thành phần của cơ chế ký, không phải các class được chạy trong ứng dụng.

## 4. Phân biệt lỗi digest với lỗi certificate trust

Hai nhóm lỗi này có ý nghĩa khác nhau:

| Nhóm | Điều đang được kiểm tra | Ví dụ |
|---|---|---|
| Integrity/signature | Chữ ký có khớp với dữ liệu đã ký và digest entry có còn nguyên không | `SHA-384 digest error for Hello.class` |
| Certificate validation/trust | Certificate signer có hợp lệ và chain có dẫn tới trust anchor được chấp nhận không | `Invalid certificate chain: PKIX path building failed` |

Nếu một class đã ký bị sửa sau khi ký, xác minh nội dung sẽ thất bại với lỗi digest. Nếu chữ ký mật mã đúng nhưng certificate tự ký hoặc thiếu CA trung gian, công cụ có thể báo `jar verified` kèm cảnh báo chain không hợp lệ. Điều này có nghĩa nội dung đã ký khớp với chữ ký, nhưng danh tính signer chưa được xác thực theo trust policy.

Vì vậy, luôn đọc toàn bộ cảnh báo sau dòng `jar verified`. Không được bỏ qua cảnh báo self-signed, chain invalid, unsigned entry, certificate hết hạn hoặc thuật toán bị vô hiệu hóa chỉ vì dòng tổng kết xuất hiện.

## 5. Các nguyên nhân thường gặp gây lỗi xác thực

### 5.1. Nội dung entry đã bị thay đổi

Nếu một class hoặc resource đã ký bị sửa sau khi ký, digest được lưu trong manifest không còn khớp. Thông báo có thể giống:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-384 digest error for Hello.class
~~~

Nguyên nhân thường gặp:

- File JAR bị chỉnh sửa sau khi ký.
- Pipeline build ghi đè hoặc cập nhật class/resource vào JAR đã ký.
- Một công cụ đóng gói lại JAR nhưng không ký lại.
- Artifact bị hỏng trong quá trình truyền hoặc lưu trữ.

Cách xử lý là lấy lại artifact từ nguồn phát hành đáng tin cậy hoặc build lại từ source, hoàn tất mọi bước đóng gói trước khi ký, sau đó xác minh lại. Không sửa nội dung JAR đã ký rồi tiếp tục phân phối chữ ký cũ.

### 5.2. JAR có entry chưa được ký

Một JAR có thể có chữ ký hợp lệ cho một số entry nhưng vẫn chứa file mới được thêm sau khi ký. Trong chế độ verbose, entry đó có thể xuất hiện với ký hiệu `?`. Công cụ có thể in:

~~~text
This jar contains unsigned entries which have not been integrity-checked.
~~~

Trường hợp này khác với digest mismatch: entry mới không có chữ ký để xác minh. Nếu yêu cầu phát hành là mọi class/resource đều phải được ký, đây vẫn là lỗi cần chặn.

Cách xử lý:

1. Xác định entry chưa được ký từ báo cáo verbose.
2. Kiểm tra entry có được thêm sau bước ký hay do artifact bị ghép từ nhiều nguồn không.
3. Hoàn thiện JAR trước khi ký.
4. Ký lại artifact cuối cùng.
5. Chạy verify strict trước khi phát hành.

Không thêm file vào JAR sau bước ký. Nếu cần cập nhật nội dung, hãy build lại rồi ký lại toàn bộ artifact.

### 5.3. Certificate tự ký hoặc chain không được tin cậy

Các thông báo có thể gồm:

~~~text
The signer's certificate is self-signed.
Invalid certificate chain: PKIX path building failed
~~~

Một certificate tự ký có thể được dùng để tạo chữ ký mật mã hợp lệ, nhưng hệ thống không có căn cứ CA đáng tin cậy để xác thực danh tính signer. Chain không hợp lệ cũng có thể do thiếu intermediate CA hoặc truststore không chứa root CA phù hợp.

Cách xử lý:

- Dùng certificate code-signing do CA hoặc PKI nội bộ được tổ chức tin cậy cấp.
- Đảm bảo chain cần thiết được đóng gói đúng trong signature block.
- Cấu hình trust anchor theo chính sách của môi trường xác minh.
- Kiểm tra certificate chain và fingerprint qua một kênh độc lập.
- Chỉ dùng self-signed certificate cho thử nghiệm hoặc khi trust được phân phối và quản lý rõ ràng.

Không import certificate không rõ nguồn gốc vào truststore chỉ để làm cho lệnh verify hết cảnh báo. Việc thêm trust anchor là một quyết định tin cậy, không phải thao tác sửa lỗi kỹ thuật đơn thuần.

### 5.4. Certificate hết hạn hoặc chưa có hiệu lực

Nếu signer certificate hết hạn hoặc chưa tới ngày bắt đầu hiệu lực, `jarsigner` có thể phát cảnh báo nghiêm trọng. Kiểm tra `Valid from`, `Valid until` và thời gian hệ thống.

Nếu JAR được ký khi certificate còn hiệu lực, timestamp hợp lệ có thể giúp chứng minh thời điểm ký. Timestamp không làm certificate mới có hiệu lực và không sửa được chữ ký sai; nó cung cấp bằng chứng về thời điểm chữ ký được tạo.

Nếu certificate đã hết hạn trước thời điểm ký hoặc timestamp không hợp lệ, cần cấp certificate phù hợp và ký lại artifact theo chính sách.

### 5.5. Chữ ký không có timestamp

Khi ký mà không dùng timestamp authority, kết quả có thể cảnh báo:

~~~text
This jar contains signatures that do not include a timestamp.
~~~

Không có timestamp, người xác minh có thể không chứng minh được JAR đã được ký khi signer certificate còn hiệu lực sau khi certificate hết hạn hoặc bị thu hồi trong tương lai.

Khi tổ chức có Timestamping Authority (TSA), có thể tạo chữ ký có timestamp bằng tùy chọn `-tsa` lúc ký:

~~~sh
jarsigner -keystore signer.p12 -storetype PKCS12 -tsa <tsa-url> -signedjar app-signed.jar app.jar release
~~~

`-tsa` là URL của TSA hỗ trợ Time-Stamp Protocol. Chỉ dùng endpoint do tổ chức hoặc nhà cung cấp tin cậy chỉ định. Timestamp cần được xác minh theo chain của TSA; một timestamp có chain không hợp lệ vẫn có thể tạo cảnh báo.

### 5.6. Certificate bị thu hồi hoặc không kiểm tra được trạng thái thu hồi

Có thể bật kiểm tra thu hồi certificate bằng:

~~~sh
jarsigner -verify -revCheck -verbose -certs app-signed.jar
~~~

`-revCheck` bật truy vấn trạng thái thu hồi, thường thông qua OCSP hoặc CRL. Việc kiểm tra có thể cần kết nối mạng, proxy và endpoint PKI hoạt động. Lỗi mạng hoặc máy chủ OCSP/CRL không truy cập được cần được phân tích riêng với lỗi digest của JAR.

Theo cấu hình JDK hiện hành, kiểm tra revocation không được bật nếu không chỉ định `-revCheck`. Hãy áp dụng tùy chọn này theo chính sách bảo mật của tổ chức và môi trường CI.

### 5.7. Thuật toán chữ ký hoặc digest yếu/bị vô hiệu hóa

JDK áp dụng security property để kiểm soát thuật toán không còn an toàn. Nếu JAR dùng thuật toán đã bị vô hiệu hóa, `jarsigner` có thể coi JAR như unsigned hoặc phát cảnh báo về thuật toán.

Kiểm tra cấu hình `jdk.jar.disabledAlgorithms` và `jdk.security.legacyAlgorithms` trong file security của JDK khi cần chẩn đoán. Hướng xử lý bền vững là ký lại bằng thuật toán và khóa phù hợp với chính sách hiện tại.

Không hạ thấp chính sách bảo mật toàn cục hoặc bật lại thuật toán yếu chỉ để vượt qua bước verify.

## 6. Dùng -strict để phát hiện cảnh báo nghiêm trọng

Mặc định, `jarsigner -verify` có thể trả exit code 0 khi chữ ký mật mã và digest của các entry được ký hợp lệ, dù vẫn in cảnh báo về certificate chain, signer self-signed hoặc entry chưa được ký. Đây là lý do lệnh verify thông thường chưa đủ làm điều kiện phát hành nghiêm ngặt.

Dùng:

~~~sh
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Tùy chọn `-strict` biến các cảnh báo nghiêm trọng thành lỗi và làm exit code phản ánh những cảnh báo đó. Một số mã thường gặp theo tài liệu JDK:

| Mã cảnh báo | Ý nghĩa |
|---:|---|
| 1 | Xác minh thất bại, ví dụ chữ ký hoặc digest không hợp lệ |
| 4 | Certificate hết hạn/chưa có hiệu lực, chain không được xác thực, self-signed hoặc thuật toán bị vô hiệu hóa |
| 8 | Key Usage hoặc Extended Key Usage không cho phép ký code |
| 16 | JAR chứa entry chưa được ký |
| 32 | Chữ ký không khớp alias được chỉ định hoặc alias không có trong keystore |
| 64 | Chain certificate của TSA không hợp lệ |

Một số cảnh báo nghiêm trọng có thể xuất hiện cùng lúc; exit code strict có thể là phép OR các mã cảnh báo. Vì vậy, không nên hardcode một số duy nhất cho mọi lỗi. Trong CI, quy tắc đơn giản và an toàn là yêu cầu lệnh kết thúc với exit code 0; nếu khác 0, dừng pipeline và lưu toàn bộ output để điều tra.

Cảnh báo thông tin như không có timestamp có thể không tạo mã lỗi strict, nhưng vẫn cần đánh giá theo chính sách phát hành. `-strict` không thay thế việc đọc nội dung cảnh báo.

## 7. Ví dụ thực hành: tạo, ký và xác minh JAR

Ví dụ sau dùng JDK 17+ và tạo một JAR nhỏ để minh họa. Certificate tự ký chỉ dùng cho môi trường học tập, không đại diện cho signer được CA tin cậy.

Tạo file `src/Hello.java`:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from signed JAR!");
    }
}
~~~

Biên dịch và tạo JAR:

~~~sh
mkdir -p classes
javac -d classes src/Hello.java
jar --create --file app.jar -C classes .
~~~

Tạo PKCS#12 keystore và key pair thử nghiệm:

~~~sh
keytool -genkeypair -alias signer -keyalg RSA -keysize 2048 -validity 365 -dname "CN=Example Signer" -keystore signer.p12 -storetype PKCS12
~~~

Keytool sẽ hỏi mật khẩu keystore. Không dùng mật khẩu thật trong ví dụ học tập hoặc commit keystore vào repository.

Ký JAR và ghi ra file mới:

~~~sh
jarsigner -keystore signer.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar signer
~~~

Keytool/jarsigner sẽ hỏi mật khẩu cần thiết khi chạy tương tác. Có thể kiểm tra nội dung chữ ký:

~~~sh
jar --list --file app-signed.jar
~~~

Trong `META-INF`, sẽ có manifest và các file chữ ký, ví dụ `SIGNER.SF` và `SIGNER.RSA` với RSA key.

Xác minh:

~~~sh
jarsigner -verify -verbose -certs app-signed.jar
~~~

Chạy class từ JAR:

~~~sh
java -cp app-signed.jar Hello
~~~

Kết quả stdout:

~~~text
Hello from signed JAR!
~~~

Vì certificate demo là self-signed, lệnh verify có thể báo chain invalid hoặc self-signed dù digest/chữ ký mật mã khớp. Đây là cảnh báo trust có chủ đích của ví dụ; không coi nó là một certificate phát hành production.

Chạy strict để thấy cảnh báo nghiêm trọng được phản ánh vào exit code:

~~~sh
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Với certificate tự ký không được tin cậy, lệnh strict dự kiến trả exit code khác 0. Khi dùng certificate code-signing có chain được trust policy chấp nhận và không có cảnh báo nghiêm trọng, lệnh mới có thể kết thúc với exit code 0.

## 8. Mô phỏng hai lỗi thường gặp

### Sửa một entry đã ký

Tạo một phiên bản khác của `Hello.java` với nội dung in ra `tampered`, rồi biên dịch vào thư mục riêng:

~~~sh
mkdir -p changed
javac -d changed src-tampered/Hello.java
~~~

Thay entry class trong JAR đã ký:

~~~sh
jar --update --file app-signed.jar -C changed Hello.class
~~~

Xác minh lại:

~~~sh
jarsigner -verify -verbose app-signed.jar
~~~

Kết quả có thể là:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-384 digest error for Hello.class
~~~

Tên digest phụ thuộc thuật toán được dùng khi ký. Lỗi cho biết byte của entry không còn khớp digest đã ký. Hãy bỏ artifact đã bị sửa và build/ký lại từ nguồn đáng tin cậy.

### Thêm một entry mới sau khi ký

Trên một bản sao khác của JAR đã ký, thêm resource mới sau bước ký:

~~~sh
mkdir -p extra
jar --update --file app-signed.jar -C extra info.txt
jarsigner -verify -verbose app-signed.jar
~~~

Entry mới có thể xuất hiện với ký hiệu `?` và cảnh báo unsigned entry. Lệnh verify thông thường có thể vẫn in `jar verified` và trả exit code 0 vì các entry đã ký không bị thay đổi. Với `-strict`, unsigned entry là cảnh báo nghiêm trọng và pipeline sẽ nhận exit code khác 0.

Hai tình huống cần cách xử lý khác nhau: digest mismatch nghĩa là dữ liệu đã ký bị thay đổi; unsigned entry nghĩa là một phần nội dung không nằm trong phạm vi chữ ký.

## 9. Tích hợp xác minh vào CI

Với pipeline build, nên chạy verify trên **artifact cuối cùng** sau khi đã đóng gói và ký. Không chạy bước cập nhật JAR sau xác minh, vì mọi thay đổi tiếp theo có thể làm chữ ký không còn đúng.

Lệnh kiểm tra:

~~~sh
jarsigner -verify -strict -verbose -certs build/libs/app-signed.jar
~~~

Trên PowerShell:

~~~powershell
jarsigner -verify -strict -verbose -certs build/libs/app-signed.jar
if ($LASTEXITCODE -ne 0) {
    throw "JAR signature verification failed"
}
~~~

Trên Bash:

~~~sh
jarsigner -verify -strict -verbose -certs build/libs/app-signed.jar
status=$?
if [ "$status" -ne 0 ]; then
  echo "JAR signature verification failed" >&2
  exit "$status"
fi
~~~

Nếu pipeline cần xác minh chữ ký thuộc một alias cụ thể, chỉ định keystore và alias theo cú pháp `jarsigner -verify`. Keystore xác minh cần được cung cấp an toàn; không đưa private key hoặc mật khẩu ký vào bước verify nếu không cần thiết.

Nên lưu output của `-verbose -certs` khi pipeline thất bại. Output này giúp phân biệt digest mismatch, unsigned entry, certificate chain invalid, certificate hết hạn, alias mismatch và thuật toán không được chấp nhận.

## 10. Quy trình điều tra lỗi theo thứ tự

Khi gặp lỗi xác thực chữ ký, hãy làm theo thứ tự:

1. **Xác định artifact**: kiểm tra đúng JAR đang được pipeline hoặc runtime sử dụng; so sánh tên, kích thước và nguồn tải.
2. **Chạy verify verbose**: dùng `jarsigner -verify -verbose -certs app.jar` để biết entry nào có vấn đề và xem certificate.
3. **Đọc lỗi đầu tiên**: digest error thường chỉ ra entry đã thay đổi; `?` chỉ ra entry chưa ký.
4. **Kiểm tra signature files**: xác nhận các file .SF và signature block trong `META-INF` còn nguyên và tương ứng.
5. **Kiểm tra signer certificate**: xem Subject, Issuer, validity, Key Usage, Extended Key Usage và chain.
6. **Kiểm tra trust**: xác nhận trust anchor và intermediate CA theo truststore/policy của môi trường.
7. **Kiểm tra timestamp**: xác định chữ ký có timestamp hay không và chain của TSA có hợp lệ không.
8. **Kiểm tra revocation**: nếu chính sách yêu cầu, chạy với `-revCheck` và xác minh OCSP/CRL có thể truy cập.
9. **Kiểm tra thuật toán**: xem cảnh báo thuật toán yếu hoặc bị vô hiệu hóa trong security policy của JDK.
10. **Chạy strict**: dùng `jarsigner -verify -strict` trước khi phát hành và yêu cầu exit code 0.

Không giải quyết digest mismatch bằng cách import certificate vào truststore; truststore không thể làm nội dung đã bị sửa trở thành nội dung được ký hợp lệ. Ngược lại, ký lại JAR cũng không tự giải quyết vấn đề trust nếu signer certificate vẫn không được tin cậy.

## 11. Lỗi thường gặp và hướng xử lý

| Thông báo/hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `SHA-384 digest error for <entry>` | Nội dung entry đã thay đổi hoặc JAR bị hỏng | Lấy artifact gốc, build lại và ký lại sau mọi bước đóng gói |
| `This jar contains unsigned entries` | Có file được thêm sau khi ký hoặc JAR chỉ được ký một phần | Kiểm tra ký hiệu `?`, ký lại artifact cuối cùng |
| `signer's certificate is self-signed` | Certificate tự ký, không có CA trust anchor | Dùng certificate được tổ chức/CA tin cậy cấp hoặc trust policy được phê duyệt |
| `PKIX path building failed` | Thiếu intermediate/root CA hoặc chain không được tin cậy | Kiểm tra chain và truststore; xác minh fingerprint qua kênh độc lập |
| Certificate expired/not yet valid | Certificate hết hạn, chưa có hiệu lực hoặc đồng hồ hệ thống sai | Kiểm tra thời gian, validity, timestamp; cấp certificate phù hợp |
| `no timestamp` | Chữ ký không có timestamp từ TSA | Dùng TSA đáng tin cậy khi ký nếu chính sách yêu cầu |
| `disabled algorithm` | JAR dùng digest/signature algorithm bị JDK policy vô hiệu hóa | Ký lại bằng thuật toán hiện hành; không hạ security policy để bỏ qua |
| Revocation status không xác định | OCSP/CRL không truy cập được hoặc cấu hình PKI lỗi | Kiểm tra mạng, proxy, OCSP/CRL và chính sách revocation |
| `jar verified` nhưng CI vẫn nên fail | Verify mặc định có thể trả 0 dù có cảnh báo nghiêm trọng | Dùng `-strict` và kiểm tra exit code |
| Alias không khớp | JAR được ký bởi signer khác alias được yêu cầu | Kiểm tra alias/keystore và chính sách signer được phép |

## 12. Checklist trước khi phát hành

- [ ] Đang xác minh đúng JAR cuối cùng được phát hành.
- [ ] Mọi class/resource cần bảo vệ đều có chữ ký.
- [ ] Không có digest mismatch hoặc signature file hỏng.
- [ ] Không có unsigned entry ngoài chủ đích và được phê duyệt.
- [ ] Signer certificate đúng danh tính và chain được trust policy chấp nhận.
- [ ] Certificate còn hiệu lực tại thời điểm ký; timestamp hợp lệ nếu được yêu cầu.
- [ ] Key Usage/Extended Key Usage cho phép code signing.
- [ ] Thuật toán không bị JDK security policy vô hiệu hóa.
- [ ] Revocation check được bật khi chính sách yêu cầu.
- [ ] `jarsigner -verify -strict` hoàn tất với exit code 0.
- [ ] Không sửa hoặc cập nhật JAR sau khi đã ký và xác minh.
- [ ] Output verify và thông tin signer được lưu cùng hồ sơ phát hành.

`jarsigner -verify` kiểm tra chữ ký và digest của nội dung đã ký; `-strict` giúp CI chặn cả những cảnh báo nghiêm trọng về signer và entry chưa được bảo vệ. Khi tách bạch lỗi toàn vẹn nội dung với lỗi trust certificate, bạn có thể tìm đúng nguyên nhân, khôi phục artifact đáng tin cậy và chỉ phát hành JAR đáp ứng chính sách xác minh.

## Tài liệu tham khảo

- [Oracle JDK 26 — The jarsigner Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [Java Archive (JAR) File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)