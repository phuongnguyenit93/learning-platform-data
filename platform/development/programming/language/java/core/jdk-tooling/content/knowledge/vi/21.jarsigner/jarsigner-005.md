# Timestamp chữ ký JAR bằng jarsigner

## Mục tiêu

Sau bài này, bạn có thể giải thích timestamp trong chữ ký JAR; hiểu vai trò của Time Stamping Authority (TSA) và giao thức RFC 3161; phân biệt timestamp với thời điểm trên máy ký; cấu hình \`jarsigner -tsa\`, \`-tsacert\`, \`-tsadigestalg\` và \`-tsapolicyid\`; ký JAR có timestamp; xác minh chữ ký, timestamp và certificate chain; xử lý cảnh báo \`noTimestamp\`, certificate hết hạn hoặc TSA chain không hợp lệ; và đưa timestamp verification vào quy trình phát hành/CI.

## 1. Timestamp chữ ký JAR là gì?

Khi ký một JAR, \`jarsigner\` dùng private key của signer để tạo chữ ký số cho thông tin digest của các entry trong archive. Chữ ký cho phép người nhận kiểm tra tính toàn vẹn của nội dung và xác minh public key tương ứng với certificate của signer.

**Timestamp (dấu thời gian)** là token được một Time Stamping Authority (TSA) ký để cung cấp bằng chứng rằng một giá trị dữ liệu đã tồn tại tại một thời điểm nhất định. Khi ký JAR có timestamp, TSA đóng dấu lên chữ ký số của signer. Token timestamp được lưu cùng chữ ký trong signature block của JAR.

Timestamp đặc biệt hữu ích khi certificate ký code có thời hạn. Nếu JAR được ký khi certificate của signer còn hiệu lực, timestamp đáng tin cậy có thể giúp hệ thống xác định chữ ký được tạo trong khoảng hiệu lực đó, ngay cả khi certificate signer hết hạn về sau.

Không có timestamp, người kiểm tra có thể không xác định được chữ ký được tạo trước hay sau ngày certificate signer hết hạn hoặc trước/sau một mốc thu hồi trong tương lai. JDK cảnh báo \`noTimestamp\` khi chữ ký không có timestamp.

Timestamp không kéo dài thời hạn của certificate, không làm certificate hết hạn trở nên hợp lệ cho một chữ ký mới, và không tự động bỏ qua trạng thái thu hồi. Nó cung cấp bằng chứng thời gian cần được kiểm tra cùng chữ ký, certificate signer, certificate TSA, trust chain, chính sách thuật toán và thông tin revocation.

## 2. Vì sao cần timestamp khi ký JAR?

Giả sử công ty phát hành một thư viện Java vào ngày 10 tháng 3. Certificate code-signing của công ty có hiệu lực đến ngày 30 tháng 6. Người dùng tải JAR vào tháng 8.

Nếu JAR được ký vào tháng 3 và có timestamp hợp lệ từ TSA, verifier có thể kiểm tra rằng chữ ký đã tồn tại trong thời gian certificate signer còn hiệu lực. Nếu không có timestamp, verifier có thể không chứng minh được chữ ký được tạo trước ngày certificate hết hạn; JAR có thể nhận cảnh báo hoặc không còn được chấp nhận theo chính sách của môi trường.

Timestamp hỗ trợ:

- **Bằng chứng thời điểm tồn tại:** xác nhận chữ ký đã tồn tại không muộn hơn thời điểm được TSA xác nhận.
- **Xác minh chữ ký sau khi certificate signer hết hạn:** hỗ trợ kiểm tra rằng chữ ký được tạo khi certificate còn hiệu lực.
- **Quản lý vòng đời phát hành:** giữ bằng chứng thời gian khi phần mềm được lưu trữ, phân phối hoặc kiểm tra nhiều năm sau.
- **Xử lý mốc thu hồi:** giúp đánh giá chữ ký được tạo trước hay sau thời điểm certificate bị thu hồi, khi có đủ dữ liệu revocation và chính sách xác minh phù hợp.
- **Tuân thủ chính sách phát hành:** nhiều quy trình code-signing yêu cầu timestamp để artifact có thể được xác minh lâu dài.

Timestamp không thay thế chữ ký JAR. Chữ ký của signer chứng minh dữ liệu được ký bởi private key tương ứng; timestamp của TSA chứng minh một imprint của chữ ký đã được TSA đóng dấu tại thời điểm xác định.

## 3. Vai trò của Time Stamping Authority

**TSA (Time Stamping Authority)** là dịch vụ tạo và ký timestamp token. TSA phải có nguồn thời gian đáng tin cậy và một key chuyên dùng cho hoạt động timestamp.

Trong RFC 3161:

1. Client tính hash (message imprint) của dữ liệu cần đóng dấu.
2. Client gửi timestamp request tới TSA.
3. TSA kiểm tra request và tạo timestamp token.
4. Token chứa message imprint, thuật toán hash, thời gian \`genTime\`, serial number và policy identifier.
5. TSA ký token bằng private key dành riêng cho timestamp.
6. Client xác minh chữ ký TSA, certificate identifier, message imprint và các trường liên quan.

TSA không cần nhận toàn bộ file JAR hoặc source code để đóng dấu. Giao thức RFC 3161 đóng dấu lên hash đại diện cho dữ liệu. Với \`jarsigner\`, dữ liệu được đóng dấu là chữ ký của signer.

Certificate TSA phải phù hợp mục đích timestamping. Theo RFC 3161, certificate của TSA sử dụng Extended Key Usage (EKU) \`id-kp-timeStamping\`; extension này phải critical và key được dành riêng cho hoạt động timestamp. Certificate signer dùng để ký code và certificate TSA dùng để timestamp là hai vai trò khác nhau.

### Sơ đồ luồng ký

~~~text
JAR entries
    |
    v
jarsigner tính digest các entry
    |
    v
Tạo signature file (.SF)
    |
    v
Signer dùng private key ký .SF
    |
    v
Chữ ký được gửi tới TSA theo RFC 3161
    |
    v
TSA trả timestamp token đã ký
    |
    v
jarsigner lưu token trong signature block
    |
    v
Signed JAR có chữ ký + timestamp
~~~

Timestamp token được lưu trong signature block file (ví dụ \`.RSA\`, \`.DSA\` hoặc \`.EC\`) cùng chữ ký JAR. Người xác minh không cần một file timestamp riêng bên ngoài JAR nếu token đã được nhúng đúng cách.

## 4. RFC 3161 hoạt động như thế nào?

RFC 3161 định nghĩa Time-Stamp Protocol (TSP), gồm định dạng request và response.

### Timestamp request

Request chứa:

- Phiên bản giao thức.
- Message imprint: thuật toán hash và giá trị hash.
- Policy OID tùy chọn.
- Nonce tùy chọn để liên kết response với request.
- Cờ yêu cầu TSA gửi certificate của mình trong response.

Client gửi request đến endpoint TSA qua transport mà dịch vụ hỗ trợ, thường là HTTP(S). RFC 3161 định nghĩa MIME type cho timestamp request và response.

### Timestamp response

Response chứa status và có thể có timestamp token. Token bao gồm thông tin thời gian và chữ ký của TSA. Client phải kiểm tra:

- TSA trả về trạng thái thành công.
- Message imprint trong token khớp dữ liệu đã yêu cầu timestamp.
- Hash algorithm và hash value đúng.
- Chữ ký của TSA hợp lệ.
- Certificate TSA đúng certificate được tham chiếu trong token.
- Thời gian và policy của token phù hợp yêu cầu.
- TSA certificate chain được tin cậy theo chính sách.
- Trạng thái certificate TSA được xử lý theo chính sách revocation.

### Timestamp không phải đồng hồ local

Thời gian do TSA xác nhận khác với thời gian trên máy build. Đồng hồ local có thể sai, bị chỉnh sửa hoặc không đồng bộ. TSA cung cấp một nguồn thời gian độc lập và ký bằng private key riêng.

Tuy vậy, chất lượng timestamp phụ thuộc vào độ tin cậy của TSA, nguồn thời gian, chính sách vận hành, bảo vệ private key và quy trình kiểm tra token. Chỉ có một timestamp token không tự chứng minh TSA đó đáng tin; verifier vẫn cần trust anchor và chính sách chấp nhận TSA.

## 5. Cú pháp timestamp trong jarsigner

Cú pháp tổng quát để ký JAR:

~~~bash
jarsigner [options] jar-file alias
~~~

Các tùy chọn timestamp:

| Tùy chọn | Công dụng |
|---|---|
| \`-tsa url\` | Chỉ định URL của TSA; bật timestamp cho chữ ký |
| \`-tsacert alias\` | Chỉ định certificate TSA trong keystore; URL TSA được đọc từ Subject Information Access extension |
| \`-tsadigestalg algorithm\` | Chọn digest algorithm cho message imprint gửi tới TSA |
| \`-tsapolicyid policyid\` | Gửi policy identifier dạng OID tới TSA |

Các tùy chọn này dùng khi ký JAR. Chúng không phải tùy chọn cấu hình cho lệnh \`jarsigner -verify\`; khi verify, tool đọc timestamp đã được lưu trong signature block.

### -tsa URL

Ví dụ:

~~~bash
jarsigner -tsa https://tsa.example.org app.jar codesign
~~~

URL phải là endpoint timestamp mà nhà cung cấp TSA công bố. \`tsa.example.org\` chỉ là tên minh họa, không phải dịch vụ TSA thực tế. Thay bằng URL được tổ chức hoặc nhà cung cấp TSA cấp.

Khi có \`-tsa\`, \`jarsigner\` gửi request RFC 3161 đến URL đó. Certificate TSA không cần phải có sẵn trong keystore chỉ để gọi tùy chọn \`-tsa\`; quá trình xác minh vẫn cần kiểm tra trust chain của token.

Nếu đồng thời chỉ định \`-tsa\` và \`-tsacert\`, URL trong \`-tsa\` ghi đè URL được tìm thấy từ certificate alias \`-tsacert\`.

### -tsacert alias

Ví dụ:

~~~bash
jarsigner -tsacert tsa-signing-cert -keystore signing.p12 app.jar codesign
~~~

Alias phải xác định certificate public key của TSA trong keystore đang sử dụng. \`jarsigner\` đọc Subject Information Access (SIA) extension trong certificate để tìm URL của TSA.

Certificate TSA phải có trong keystore khi dùng \`-tsacert\`. Nếu certificate không chứa URL TSA cần thiết trong SIA, tùy chọn này không đủ thông tin để tìm endpoint.

### -tsadigestalg

Ví dụ:

~~~bash
jarsigner -tsa https://tsa.example.org -tsadigestalg SHA-384 app.jar codesign
~~~

Tùy chọn này chọn thuật toán hash để tạo message imprint gửi TSA. Trong JDK 26, nếu không chỉ định, mặc định là SHA-384.

Đây là digest cho timestamp request, không phải tùy chọn \`-digestalg\` dùng để hash các entry JAR và cũng không phải \`-sigalg\` dùng để ký signature file.

| Tùy chọn | Dữ liệu/hoạt động |
|---|---|
| \`-digestalg\` | Digest của các entry trong JAR |
| \`-sigalg\` | Thuật toán chữ ký dùng private key signer |
| \`-tsadigestalg\` | Digest của message imprint gửi TSA |

Không chọn thuật toán chỉ vì nó tương thích với hệ thống cũ. Hãy tuân thủ thuật toán được TSA hỗ trợ và chính sách bảo mật của JDK/đơn vị phát hành.

### -tsapolicyid

Ví dụ:

~~~bash
jarsigner -tsa https://tsa.example.org -tsapolicyid 1.2.3.4 app.jar codesign
~~~

Giá trị phải là OID do TSA công bố hoặc tổ chức yêu cầu. Nếu không chỉ định, request không gửi policy OID và TSA chọn policy mặc định.

Không tự đặt OID tùy ý rồi mong TSA chấp nhận. Dùng đúng policy identifier do nhà cung cấp TSA cấp.

## 6. Chuẩn bị keystore và JAR trước khi ký

Để ký JAR, cần có private key cùng certificate chain trong keystore. Alias truyền cho \`jarsigner\` phải là alias của private-key entry.

Kiểm tra alias:

~~~bash
keytool -list -v -keystore signing.p12 -storetype PKCS12 -alias codesign
~~~

Xác nhận entry type là \`PrivateKeyEntry\`, certificate còn hiệu lực và có key usage/extended key usage phù hợp cho code signing theo chính sách của CA.

Nếu chưa có JAR, tạo một chương trình Java đơn giản:

~~~text
project/
├── src/
│   └── com/example/Main.java
└── classes/
~~~

File \`src/com/example/Main.java\`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("signed-jar-ok");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d classes src/com/example/Main.java
~~~

Tạo JAR executable:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

Chạy thử trước khi ký:

~~~bash
java -jar app.jar
~~~

Output chính xác:

~~~text
signed-jar-ok
~~~

Không thay đổi nội dung JAR sau khi ký. Nếu thêm, xóa hoặc sửa entry đã được ký, digest verification sẽ thất bại. Nếu cần sửa artifact, hãy build lại JAR rồi ký lại.

## 7. Ký JAR có timestamp bằng TSA URL

Giả sử:

- File đầu vào là \`app.jar\`.
- Keystore là \`signing.p12\`.
- Alias private key là \`codesign\`.
- TSA cung cấp endpoint thực tế qua biến môi trường \`TSA_URL\`.

Trên Linux/macOS, đặt endpoint theo hướng dẫn của nhà cung cấp:

~~~bash
export TSA_URL="https://tsa.your-provider.example/rfc3161"
~~~

Sau đó ký:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -tsa "$TSA_URL" -tsadigestalg SHA-384 -signedjar app-signed.jar app.jar codesign
~~~

Trên Windows PowerShell:

~~~powershell
$env:TSA_URL = "https://tsa.your-provider.example/rfc3161"
jarsigner -keystore signing.p12 -storetype PKCS12 -tsa $env:TSA_URL -tsadigestalg SHA-384 -signedjar app-signed.jar app.jar codesign
~~~

Thay URL minh họa bằng endpoint thật của TSA. Khi chạy, keytool/jarsigner có thể yêu cầu store password và private-key password nếu chưa được cung cấp.

Giải thích:

- \`-keystore signing.p12\`: chọn keystore chứa private key.
- \`-storetype PKCS12\`: chỉ định định dạng keystore.
- \`-tsa "$TSA_URL"\`: yêu cầu TSA cấp timestamp.
- \`-tsadigestalg SHA-384\`: chọn hash cho timestamp imprint.
- \`-signedjar app-signed.jar\`: ghi kết quả vào file mới.
- \`app.jar codesign\`: JAR đầu vào và alias signer.

Lệnh chỉ thành công khi signer key hợp lệ, TSA endpoint truy cập được, request/response tương thích và token được xác minh, nhúng vào signature block. Không nên coi việc tạo file output là đủ; phải chạy bước verify sau khi ký.

### Ký trực tiếp lên file gốc

Nếu bỏ \`-signedjar\`, jarsigner ghi signed JAR đè lên file đầu vào:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -tsa "$TSA_URL" -tsadigestalg SHA-384 app.jar codesign
~~~

Trong quy trình phát hành, dùng file output riêng thường dễ kiểm soát hơn vì có thể giữ artifact unsigned để so sánh và chỉ phát hành file đã xác minh.

## 8. Ký với -tsacert thay vì -tsa

Nếu certificate TSA đã có trong keystore và SIA extension chứa URL timestamp, có thể dùng:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -tsacert tsa-signing-cert -signedjar app-signed.jar app.jar codesign
~~~

Ở đây:

- \`codesign\` là alias private key của người phát hành JAR.
- \`tsa-signing-cert\` là alias certificate public key của TSA.
- URL được lấy từ Subject Information Access extension của TSA certificate.

Không nhầm alias TSA với alias signer. Hai certificate phục vụ hai vai trò khác nhau.

Nếu endpoint TSA được chỉ định bằng \`-tsa\`, URL đó sẽ ghi đè URL được tìm thấy từ \`-tsacert\`. Dùng một cách cấu hình rõ ràng để tránh nhầm lẫn giữa certificate và endpoint.

## 9. Xác minh JAR có timestamp

Sau khi ký, xác minh chữ ký:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Kết quả cần xem:

- Từng entry được ký và digest xác minh thành công.
- Signature file và signature block hợp lệ.
- Certificate signer và chain được hiển thị.
- Thông tin timestamp xuất hiện trong output chi tiết nếu token có mặt.
- Không có cảnh báo timestamp invalid hoặc TSA chain không hợp lệ.
- Không có cảnh báo về thuật toán bị vô hiệu hóa hoặc chữ ký lỗi.

Để biến severe warnings thành lỗi có exit code khác 0:

~~~bash
jarsigner -verify -verbose -certs -strict app-signed.jar
~~~

Tùy chọn \`-strict\` rất hữu ích trong CI vì nếu chỉ có severe warning mà không dùng \`-strict\`, jarsigner có thể trả exit code 0. Khi dùng strict, warning nghiêm trọng được phản ánh trong exit code.

### Đọc cảnh báo noTimestamp

Nếu JAR không có timestamp, jarsigner có thể đưa ra cảnh báo:

~~~text
This JAR contains signatures that doesn't include a timestamp.
~~~

Cảnh báo này có nghĩa verifier có thể không xác minh được JAR sau ngày certificate signer hết hạn hoặc sau một mốc thu hồi trong tương lai. Với quy trình phát hành yêu cầu timestamp, đây nên là điều kiện phải xử lý.

### Kiểm tra chi tiết certificate

~~~bash
jarsigner -verify -verbose -certs -strict app-signed.jar
~~~

Đọc thông tin signer certificate, TSA certificate và chain. Không chỉ dựa vào dòng \`jar verified\`. Tài liệu JDK yêu cầu xem các warning và nội dung certificate để quyết định chữ ký có đáng tin hay không.

### Xác minh signer theo alias

Nếu cần kiểm tra chữ ký được tạo bởi một alias cụ thể trong keystore:

~~~bash
jarsigner -verify -keystore trusted-signers.p12 -storetype PKCS12 -verbose -certs -strict app-signed.jar codesign
~~~

Alias sau tên JAR được dùng để đối chiếu certificate signer. Đây là kiểm tra signer identity theo keystore được chỉ định, không thay thế việc kiểm tra trust policy của TSA.

## 10. Timestamp certificate và signer certificate là hai chain khác nhau

Khi xác minh một JAR có timestamp, cần phân biệt ít nhất hai vai trò:

| Thành phần | Chức năng |
|---|---|
| Signer certificate | Xác thực public key đã ký JAR |
| Signer certificate chain | Nối signer certificate tới trust anchor được chấp nhận |
| TSA certificate | Xác thực chữ ký của timestamp token |
| TSA certificate chain | Nối TSA certificate tới trust anchor TSA |
| Timestamp token | Gắn message imprint của chữ ký với thời điểm do TSA xác nhận |

Một JAR có thể có chữ ký signer hợp lệ nhưng timestamp token không hợp lệ, hoặc timestamp token hợp lệ nhưng signer certificate chain không được tin cậy.

JDK báo severe warning \`tsaChainNotValidated\` khi TSA certificate chain không hợp lệ. Cũng có thể có cảnh báo \`hasExpiredTsaCert\` nếu timestamp đã hết hạn theo validation hiện tại.

Vì vậy, kiểm tra chữ ký JAR không chỉ là kiểm tra một public key. Cần đánh giá cả chữ ký signer và timestamp token cùng certificate chain tương ứng.

## 11. Certificate hết hạn, revocation và ý nghĩa của timestamp

Timestamp giúp chứng minh chữ ký được tạo tại một thời điểm, nhưng việc xác minh lâu dài còn phụ thuộc vào nhiều yếu tố.

### Signer certificate hết hạn

Nếu timestamp token hợp lệ và thời gian TSA xác nhận nằm trong validity period của signer certificate, verifier có thể đánh giá chữ ký được tạo khi certificate còn hiệu lực.

Điều đó không có nghĩa certificate signer vẫn còn hiệu lực để ký một JAR mới sau ngày hết hạn. Timestamp chỉ hỗ trợ đánh giá chữ ký cũ.

### Signer certificate bị thu hồi

Timestamp có thể hỗ trợ xác định chữ ký có trước hay sau thời điểm thu hồi. Tuy nhiên, phải có thông tin revocation phù hợp và chính sách xác minh xác định cách xử lý certificate bị thu hồi.

Nếu private key đã bị lộ trước thời điểm timestamp, chỉ timestamp không thể chứng minh người ký hợp pháp đã tạo chữ ký. Cần điều tra thời điểm compromise, revocation và bằng chứng PKI.

### TSA certificate hết hạn hoặc bị thu hồi

TSA certificate cũng có validity period và trạng thái revocation riêng. Timestamp token không tự trở nên đáng tin chỉ vì nó đã được nhúng vào JAR. Verifier cần kiểm tra TSA certificate chain, EKU, chữ ký token, thời gian và policy.

### Thuật toán bị suy yếu hoặc vô hiệu hóa

JDK sử dụng security properties như \`jdk.jar.disabledAlgorithms\` và \`jdk.security.legacyAlgorithms\` để đánh giá thuật toán ký/digest. Một thuật toán đã bị disabled có thể khiến chữ ký được coi như unsigned; thuật toán legacy có thể tạo informational warning.

Timestamp không biến một thuật toán đã bị vô hiệu hóa thành an toàn. Hãy dùng thuật toán hiện đại được JDK, TSA và chính sách tổ chức hỗ trợ.

## 12. Cấu hình policy và thuật toán timestamp

### Chọn digest algorithm

JDK 26 dùng SHA-384 mặc định cho timestamp message imprint nếu không chỉ định \`-tsadigestalg\`.

Có thể chọn rõ:

~~~bash
jarsigner -tsa "$TSA_URL" -tsadigestalg SHA-384 -signedjar app-signed.jar app.jar codesign
~~~

Chỉ đổi thuật toán khi TSA hỗ trợ và chính sách bảo mật cho phép. Tránh dùng digest yếu hoặc đã bị cấm trong JDK.

### Gửi TSA policy OID

Nếu nhà cung cấp yêu cầu policy cụ thể:

~~~bash
jarsigner -tsa "$TSA_URL" -tsapolicyid 1.2.3.4 -signedjar app-signed.jar app.jar codesign
~~~

OID trong ví dụ là minh họa. Hãy thay bằng policy identifier chính thức do TSA cung cấp.

### Phân biệt digest, signature và timestamp digest

Một lệnh có thể sử dụng ba thuật toán khác nhau:

~~~bash
jarsigner -digestalg SHA-384 -sigalg SHA384withRSA -tsadigestalg SHA-384 -tsa "$TSA_URL" -signedjar app-signed.jar app.jar codesign
~~~

- \`-digestalg\`: hash nội dung các entry JAR.
- \`-sigalg\`: chữ ký của signer trên signature file.
- \`-tsadigestalg\`: hash message imprint gửi TSA.

Các lựa chọn phải tương thích với key, JDK, TSA và chính sách thuật toán. Không cần ép mọi thuật toán giống nhau nếu yêu cầu kỹ thuật không đòi hỏi.

## 13. Tích hợp timestamp vào quy trình CI/CD

Một pipeline ký JAR nên tách các bước build, ký, timestamp và verify:

~~~text
Compile source
      |
      v
Package unsigned JAR
      |
      v
Run unit/integration tests
      |
      v
Sign with code-signing private key
      |
      v
Request RFC 3161 timestamp from TSA
      |
      v
Verify signer signature + timestamp + chains
      |
      v
Run artifact integrity checks
      |
      v
Publish only verified signed JAR
~~~

Các nguyên tắc triển khai:

- Dùng TSA endpoint được tổ chức phê duyệt.
- Lưu signer private key trong secret manager, HSM hoặc signing service.
- Không ghi store password/key password vào source control hoặc log.
- Dùng endpoint TSA ổn định và giám sát khả năng truy cập.
- Cấu hình timeout/retry ở lớp pipeline theo chính sách; không phát hành artifact nếu timestamp request thất bại.
- Lưu JAR unsigned và signed theo quy tắc artifact retention.
- Verify bằng JDK được hỗ trợ trong môi trường phát hành.
- Dùng \`-strict\` để severe warnings làm job thất bại.
- Lưu log ký/verify, certificate fingerprint, TSA policy OID và artifact checksum.
- Không coi timestamp token là bằng chứng duy nhất về danh tính người phát hành.

### Ví dụ bước ký và verify trong CI

Các lệnh sau giả sử CI đã cấp \`TSA_URL\` và keystore signer thông qua secret management:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 \
  -tsa "$TSA_URL" -tsadigestalg SHA-384 \
  -signedjar build/app-signed.jar build/app.jar codesign

jarsigner -verify -verbose -certs -strict build/app-signed.jar
~~~

Pipeline chỉ nên publish \`build/app-signed.jar\` nếu lệnh ký và verify đều thành công, đồng thời mọi policy check khác cũng pass.

Không truyền password thật bằng tham số command line nếu môi trường có thể ghi process arguments hoặc shell history. Dùng prompt, HSM/token hoặc cơ chế secret được CI bảo vệ.

## 14. Timestamp khi JAR có nhiều chữ ký

Một JAR có thể được nhiều signer ký. Mỗi lần ký, jarsigner tạo một cặp signature file và signature block mới cho signer tương ứng.

Nếu mỗi signer dùng timestamp, mỗi chữ ký có thể có timestamp token riêng. Khi verify, kiểm tra từng signer và token tương ứng; không giả định một timestamp áp dụng chung cho tất cả chữ ký.

Ví dụ:

~~~bash
jarsigner -tsa "$TSA_URL" -signedjar signed-by-alice.jar app.jar alice
jarsigner -tsa "$TSA_URL" signed-by-alice.jar bob
~~~

Lệnh thứ hai ký thêm vào JAR đã có chữ ký. Việc thêm chữ ký mới làm thay đổi manifest/signature metadata theo quy tắc JAR signing; chữ ký cũ vẫn có thể verify nếu các entry đã ký trước đó không bị sửa.

Nếu nội dung entry thay đổi, phải build lại artifact và ký lại. Không dùng thao tác chỉnh sửa JAR sau ký như một cách cập nhật nội dung.

## 15. Các lỗi thường gặp và cách xử lý

### TSA URL không truy cập được

**Dấu hiệu:** jarsigner báo lỗi kết nối hoặc không nhận được timestamp response.

**Nguyên nhân:** URL sai, DNS/network/proxy lỗi, TSA ngừng hoạt động hoặc endpoint không hỗ trợ RFC 3161.

**Cách xử lý:** xác minh endpoint từ nhà cung cấp; kiểm tra DNS, proxy, firewall và TLS; thử lại trong môi trường được phép. Không phát hành JAR như thể timestamp đã thành công.

### TSA từ chối request

**Dấu hiệu:** TSA response có trạng thái lỗi hoặc không có token.

**Nguyên nhân:** digest algorithm không được hỗ trợ, policy OID không hợp lệ, request format không phù hợp hoặc client không được cấp quyền sử dụng dịch vụ.

**Cách xử lý:** kiểm tra TSA policy, thuật toán được hỗ trợ, account/entitlement và cấu hình request. Chỉ bỏ -tsapolicyid khi nhà cung cấp xác nhận policy mặc định được chấp nhận.

### Dùng sai -tsacert alias

**Dấu hiệu:** jarsigner không tìm thấy URL TSA hoặc không tìm được certificate alias.

**Nguyên nhân:** alias không tồn tại trong keystore, certificate không có SIA URL phù hợp hoặc alias trỏ nhầm certificate signer.

**Cách xử lý:** kiểm tra alias bằng keytool -list -v; xác minh certificate TSA và Subject Information Access extension; dùng -tsa nếu muốn chỉ định endpoint trực tiếp.

### Timestamp token không hợp lệ

**Dấu hiệu:** verification báo timestamp invalid hoặc TSA chain không được xác minh.

**Nguyên nhân:** token signature không hợp lệ, message imprint không khớp, certificate TSA không tin cậy hoặc TSA chain không hoàn chỉnh.

**Cách xử lý:** ký lại với TSA endpoint được phê duyệt; kiểm tra trust anchors/intermediate certificates của TSA; xác minh certificate TSA có EKU timestamping phù hợp.

### Certificate TSA hết hạn

**Dấu hiệu:** cảnh báo \`hasExpiredTsaCert\`.

**Nguyên nhân:** TSA certificate không còn trong thời hạn hiệu lực theo quá trình kiểm tra.

**Cách xử lý:** kiểm tra timestamp token, TSA chain và chính sách xác minh dài hạn. Không bỏ qua cảnh báo nếu quy trình phát hành yêu cầu timestamp còn hợp lệ; liên hệ nhà cung cấp TSA để xác nhận trạng thái dịch vụ và chứng thư.

### TSA chain không được xác minh

**Dấu hiệu:** severe warning \`tsaChainNotValidated\`.

**Nguyên nhân:** thiếu intermediate/root certificate, TSA certificate không được tin cậy hoặc chain có lỗi.

**Cách xử lý:** kiểm tra trust anchor và certificate chain TSA từ nguồn chính thức; xác minh policy tin cậy của môi trường verify. Không thêm certificate lạ vào truststore chỉ để loại bỏ warning.

### JAR không có timestamp

**Dấu hiệu:** cảnh báo \`noTimestamp\`.

**Nguyên nhân:** JAR được ký mà không chỉ định -tsa hoặc -tsacert, hoặc TSA request thất bại và signature không chứa timestamp hợp lệ.

**Cách xử lý:** kiểm tra lệnh ký và output; ký lại từ JAR unsigned bằng TSA endpoint đã xác minh. Không chỉ thêm timestamp bằng cách chỉnh sửa signature block thủ công.

### JAR verify thành công nhưng CI vẫn không fail

**Dấu hiệu:** log có severe warning nhưng job exit code bằng 0.

**Nguyên nhân:** jarsigner không được gọi với -strict. Nếu không strict, severe warning có thể không làm exit code khác 0.

**Cách xử lý:** thêm -strict vào lệnh verify và kiểm tra exit code trong pipeline.

### Certificate signer hết hạn

**Dấu hiệu:** cảnh báo \`hasExpiredCert\` hoặc chữ ký không được chấp nhận theo policy.

**Nguyên nhân:** certificate signer đã hết hạn và timestamp không có, không hợp lệ hoặc không nằm trong thời gian certificate signer còn hiệu lực.

**Cách xử lý:** xác minh timestamp token, thời điểm TSA và signer chain; kiểm tra revocation information. Nếu chữ ký được tạo sau khi certificate hết hạn, phải cấp certificate mới và ký lại artifact.

### Thuật toán ký bị disabled

**Dấu hiệu:** warning \`disabledAlg\` hoặc chữ ký được xem như unsigned.

**Nguyên nhân:** digest/signature algorithm hoặc key size không còn được security properties của JDK chấp nhận.

**Cách xử lý:** dùng thuật toán và key size hiện đại theo chính sách JDK/TSA; ký lại artifact. Không hạ security policy chỉ để làm verify pass.

## 16. Checklist trước khi phát hành JAR có timestamp

### Trước khi ký

- [ ] JAR đã build/test và không còn thay đổi nội dung.
- [ ] Alias signer trỏ tới PrivateKeyEntry đúng.
- [ ] Signer certificate còn hiệu lực tại thời điểm ký.
- [ ] Signer certificate chain được tổ chức tin cậy.
- [ ] Key usage/extended key usage cho phép code signing.
- [ ] TSA endpoint lấy từ nhà cung cấp đáng tin cậy.
- [ ] TSA policy OID và digest algorithm phù hợp.
- [ ] Private key được bảo vệ bằng HSM/secret manager hoặc cơ chế an toàn.

### Sau khi ký

- [ ] JAR output là artifact dự kiến.
- [ ] Có signature file và signature block trong META-INF.
- [ ] Timestamp token được nhúng trong signature block.
- [ ] \`jarsigner -verify -verbose -certs -strict\` thành công.
- [ ] Signer signature và certificate chain được xác minh.
- [ ] TSA token và TSA certificate chain được xác minh.
- [ ] Không có \`noTimestamp\`, \`tsaChainNotValidated\`, \`hasExpiredTsaCert\` hoặc severe warning chưa xử lý.
- [ ] Revocation policy được đánh giá phù hợp.
- [ ] Checksum artifact, log ký và verify được lưu.
- [ ] Chỉ publish artifact đã verify.

## 17. Tài liệu tham khảo chính thức

- [The jarsigner Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html) — tùy chọn -tsa, -tsacert, -tsadigestalg, -tsapolicyid; cách nhúng timestamp token; verification và warning codes.
- [RFC 3161 — Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161.html) — request/response, message imprint, timestamp token, TSA certificate và yêu cầu bảo mật.
- [Java Security Standard Algorithm Names — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html) — tên chuẩn của digest và signature algorithms.
- [Java KeyStore API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html) — keystore, private-key entry và certificate chain.
- [JAR File Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html) — manifest, signature file và cấu trúc signed JAR.

Timestamp giúp lưu bằng chứng rằng chữ ký JAR đã tồn tại tại một thời điểm do TSA xác nhận. Hãy dùng TSA đáng tin cậy, chọn thuật toán/policy phù hợp và verify cả signer lẫn TSA chain bằng \`jarsigner -strict\` trước khi phát hành.
