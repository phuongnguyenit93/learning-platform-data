# jarsigner, chữ ký và module path

## 1. Mục tiêu

Một modular JAR là gói JAR có chứa module descriptor **module-info.class** ở thư mục gốc. Khi đưa gói này lên module path, Java nhận diện nó là một explicit module và dùng module descriptor để xác định tên module, dependency, package được export, service được sử dụng và provider được cung cấp.

JAR có thể được ký số bằng công cụ **jarsigner**. Chữ ký giúp người nhận kiểm tra tính toàn vẹn của các entry trong gói và xác định certificate chứa public key của bên ký. Chủ đề này giải thích cấu trúc chữ ký, cách tạo keystore, ký và xác minh một JAR, cũng như mối quan hệ giữa chữ ký và module path.

Sau bài học, bạn có thể:
- Giải thích chữ ký JAR bảo vệ dữ liệu nào và không giải quyết vấn đề nào.
- Nhận biết các file manifest, signature file và signature block trong META-INF.
- Dùng keytool để tạo hoặc kiểm tra keystore và dùng jarsigner để ký, xác minh.
- Phân biệt xác minh chữ ký mật mã với việc tin cậy certificate của người ký.
- Đóng gói, ký, kiểm tra và chạy modular JAR trên module path.

## 2. Chữ ký số của JAR dùng để làm gì?

JAR là một archive dựa trên ZIP, có thể chứa class, resource, cấu hình và metadata. Chữ ký số gắn với nội dung của các entry trong archive. Bên phát hành dùng private key để ký; bên nhận dùng public key tương ứng để kiểm tra chữ ký.

Chữ ký JAR hỗ trợ hai mục tiêu chính:

1. **Tính toàn vẹn (integrity):** phát hiện nội dung đã ký bị thay đổi sau khi ký. Nếu byte của một entry được bảo vệ thay đổi, digest không còn khớp và việc xác minh thất bại.
2. **Xác thực nguồn ký (authenticity):** chữ ký gắn với public key nằm trong certificate của người ký. Khi certificate chain được xác thực tới một trust anchor mà bên nhận tin cậy, bên nhận có cơ sở liên hệ artifact với chủ thể được nêu trong certificate.

Chữ ký số **không mã hóa JAR**. Người nhận vẫn có thể mở archive và đọc class/resource. Chữ ký cũng không tự cấp quyền truy cập package, không thay thế quy tắc readability/export của JPMS, và không biến một module thành module có quyền đặc biệt. Module path xử lý cấu trúc và quan hệ module; chữ ký xử lý việc kiểm tra nội dung và danh tính khóa ký.

Một modular JAR có thể không được ký. Một JAR được ký cũng không nhất thiết là modular JAR. Đây là hai đặc tính độc lập có thể cùng xuất hiện trên một artifact.

## 3. Các thành phần chữ ký nằm ở đâu?

Khi **jarsigner** ký một JAR, công cụ cập nhật manifest và thêm các file chữ ký vào thư mục **META-INF**. Với một signer RSA, bạn thường thấy các file dạng:

~~~text
META-INF/
  MANIFEST.MF
  RELEASE.SF
  RELEASE.RSA
~~~

Tên **RELEASE** được lấy từ alias hoặc từ tùy chọn **-sigfile**. Phần mở rộng của signature block phụ thuộc loại khóa/chữ ký; các dạng thường gặp là **.RSA**, **.DSA** và **.EC**.

Ba thành phần có vai trò khác nhau:

- **MANIFEST.MF:** chứa metadata và các digest của từng entry được ký. Digest là giá trị băm của nội dung entry, không phải bản mã hóa của nội dung.
- **File .SF (signature file):** chứa digest của manifest hoặc các section tương ứng. Nó mô tả dữ liệu mà signer muốn ký.
- **File signature block (.RSA, .DSA hoặc .EC):** chứa chữ ký mật mã của signature file cùng certificate hoặc certificate chain dùng để xác thực public key.

Có thể hình dung chuỗi kiểm tra như sau:

1. Người nhận kiểm tra chữ ký trong signature block đối với file .SF bằng public key trong certificate.
2. Người nhận đối chiếu digest trong .SF với manifest.
3. Người nhận tính lại digest của từng entry và so sánh với giá trị trong manifest.
4. Công cụ xác minh cũng kiểm tra certificate theo chính sách và trust store đang sử dụng, rồi báo các cảnh báo nếu certificate không hợp lệ hoặc không được tin cậy.

Các file chữ ký liên quan nằm trực tiếp trong META-INF. Khi dùng jarsigner, các entry thông thường của archive được đưa vào quá trình ký; các file chữ ký chuyên biệt được loại khỏi việc tự ký lẫn nhau. Không nên tự sửa nội dung manifest hay các file chữ ký bằng trình soạn thảo ZIP.

## 4. Keystore, private key và certificate

**Keystore** là nơi lưu private key và certificate chain gắn với khóa đó. Mỗi mục trong keystore có một **alias** để gọi tên. Công cụ **keytool** đi kèm JDK dùng để tạo khóa, tạo certificate, nhập certificate và xem nội dung keystore.

Khi ký, jarsigner cần private key. Khi xác minh, người nhận dùng public key trong certificate đi kèm chữ ký; trust store hoặc keystore được chỉ định có thể giúp kiểm tra certificate có nằm trong tập chứng thư được tin cậy hay không.

Ví dụ tạo một cặp khóa RSA dùng cho môi trường thực hành:

~~~bash
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -storetype PKCS12 \
  -keystore release.p12 \
  -dname "CN=Example Release, O=Example, C=VN"
~~~

Lệnh tạo keystore PKCS12 tên **release.p12**, chứa alias **release**, private key và certificate tự ký. Keytool sẽ yêu cầu nhập mật khẩu keystore và có thể yêu cầu mật khẩu khóa riêng.

Certificate tự ký phù hợp để học hoặc thử nghiệm trong môi trường kiểm soát. Nó không tự trở thành một certificate đáng tin cậy đối với máy của người dùng. Khi phát hành sản phẩm, tổ chức thường dùng certificate code-signing từ một CA phù hợp hoặc một cơ chế phân phối trust nội bộ đã được quản trị.

Có thể xem nội dung keystore:

~~~bash
keytool -list -v -keystore release.p12 -storetype PKCS12
~~~

Kiểm tra alias, loại entry, thời hạn certificate, subject, issuer, fingerprint và certificate chain. Private key phải được bảo vệ; không commit keystore chứa private key hoặc mật khẩu vào source control, không chia sẻ khóa phát hành qua kênh không an toàn, và chỉ cấp quyền ký cho quy trình/người được ủy quyền.

## 5. Ký một JAR

Giả sử đã có artifact **app.jar** và keystore **release.p12** với alias **release**. Có thể tạo một bản đã ký riêng:

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Jarsigner sẽ yêu cầu mật khẩu khi cần. Tùy chọn quan trọng:

- **-keystore:** đường dẫn keystore chứa private key.
- **-storetype:** loại keystore, ví dụ PKCS12.
- **-signedjar:** tên file đầu ra đã ký. Nếu bỏ tùy chọn này, jarsigner ghi kết quả đè lên JAR đầu vào.
- **-sigfile:** tên cơ sở tùy chọn cho các file .SF và signature block.
- **-digestalg:** thuật toán digest cho entry.
- **-sigalg:** thuật toán chữ ký tương thích với private key.
- **-tsa:** URL của Time Stamping Authority nếu muốn gắn timestamp.

JDK hiện đại có lựa chọn thuật toán mặc định dựa trên loại và kích thước khóa cùng các security properties. Nên dùng mặc định an toàn của JDK đang triển khai, trừ khi có yêu cầu tương thích cụ thể cần ghim thuật toán. Tránh thuật toán yếu hoặc đã bị vô hiệu hóa như MD5 hay SHA-1 cho quy trình phát hành mới.

Sau khi ký, có thể liệt kê nội dung archive:

~~~bash
jar --list --file app-signed.jar
~~~

Bạn sẽ thấy manifest và các file chữ ký mới trong META-INF. Các class và resource gốc vẫn có trong JAR. Chữ ký không làm nội dung trở nên bí mật.

## 6. Xác minh chữ ký

Lệnh cơ bản:

~~~bash
jarsigner -verify app-signed.jar
~~~

Để xem từng entry và thông tin certificate:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Tùy chọn **-verbose** hiển thị tiến trình xác minh; **-certs** bổ sung thông tin certificate của signer. Có thể yêu cầu kiểm tra nghiêm ngặt:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

**-strict** khiến các severe warning được phản ánh thành exit code khác 0. Điều này hữu ích trong CI/CD vì pipeline có thể dừng nếu artifact có cảnh báo nghiêm trọng. Không nên chỉ nhìn một dòng **jar verified** rồi kết luận certificate đã được tổ chức tin cậy: hãy đọc toàn bộ cảnh báo và kết quả kiểm tra trust.

Nếu muốn đối chiếu signer với một alias trong keystore, chỉ định keystore và alias khi xác minh:

~~~bash
jarsigner \
  -verify \
  -verbose \
  -certs \
  -strict \
  -keystore release.p12 \
  -storetype PKCS12 \
  app-signed.jar \
  release
~~~

Khi truyền alias, jarsigner kiểm tra certificate dùng xác minh các entry có khớp alias được yêu cầu hay không. Keystore không bắt buộc cho mọi lần verify; nếu không chỉ định, công cụ có thể dùng keystore mặc định nếu có. Một keystore dùng để đối chiếu signer không tự động chứng minh rằng mọi máy nhận đều tin cậy signer đó.

Cần phân biệt:

- **Chữ ký hợp lệ:** chữ ký mật mã khớp với dữ liệu đã ký và digest của các entry.
- **Certificate hợp lệ:** certificate còn trong thời hạn, đúng mục đích sử dụng, chain có thể được xác thực và không gặp lỗi kiểm tra liên quan.
- **Signer được tin cậy:** certificate chain kết thúc ở trust anchor mà môi trường nhận đã cấu hình tin cậy, hoặc certificate được tin cậy theo chính sách nội bộ.

Một JAR có thể có digest và chữ ký khớp nhưng vẫn phát cảnh báo vì certificate tự ký, chain chưa được xác thực, certificate hết hạn hoặc thuật toán không còn được chấp nhận. Trong môi trường phát hành, cần xử lý các cảnh báo đó theo chính sách bảo mật thay vì bỏ qua.

## 7. Timestamp và thời hạn certificate

Certificate code-signing có thời hạn. Nếu chỉ ký mà không có timestamp, sau khi certificate hết hạn, người nhận có thể không còn đủ dữ liệu để xác định chữ ký được tạo khi certificate còn hiệu lực hay không.

Có thể yêu cầu timestamp khi ký bằng một TSA hỗ trợ RFC 3161:

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -tsa https://tsa.example.com \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

**https://tsa.example.com** chỉ là địa chỉ minh họa; cần thay bằng URL TSA thật do tổ chức hoặc nhà cung cấp tin cậy chỉ định. Khi thành công, timestamp token được lưu cùng signature block. TSA xác nhận thời điểm ký theo dịch vụ timestamp, giúp việc đánh giá chữ ký sau khi certificate signer hết hạn có thêm căn cứ.

Timestamp không sửa nội dung JAR và không thay thế certificate chain đáng tin cậy. Nếu timestamp server không truy cập được hoặc certificate TSA không xác thực được, quy trình ký/xác minh có thể báo lỗi hoặc cảnh báo. Hãy lưu lại log của lần ký và kiểm tra timestamp trong kết quả xác minh.

## 8. Modular JAR và module path

Một modular JAR có file **module-info.class** ở thư mục gốc của archive. Ví dụ module descriptor:

~~~java
module com.example.app {
    requires com.example.codec;
    exports com.example.api;
}
~~~

Đóng gói các class đã biên dịch, bao gồm module-info.class:

~~~bash
jar --create --file app.jar -C out .
~~~

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file app.jar
~~~

Nếu JAR được đặt trên classpath, module descriptor không khiến nó hoạt động như một named module; nó được xử lý như một JAR thông thường trong unnamed module. Khi đặt modular JAR lên module path, runtime nhận diện nó là explicit module và đọc descriptor để phân giải module.

Có thể ký JAR sau khi đã đóng gói:

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 app.jar release
~~~

Hoặc dùng **-signedjar** để xuất ra một file riêng như ví dụ trước. Sau khi ký, **module-info.class** vẫn ở vị trí gốc, nên JAR vẫn là modular JAR. Các file chữ ký nằm trong META-INF và không thay thế module descriptor.

Chạy ứng dụng bằng module path:

~~~bash
java --module-path mods \
  --module com.example.app/com.example.Main
~~~

Thư mục **mods** có thể chứa modular JAR của ứng dụng và các module phụ thuộc. Tên module và dependency vẫn được quyết định bởi module descriptor; alias ký và certificate không tham gia vào quá trình đặt tên module hoặc xác định **requires**, **exports**, **opens**, **uses**, **provides**.

**Chữ ký và module path giải quyết hai câu hỏi khác nhau:**

- Module system hỏi: module nào đang có mặt, module phụ thuộc vào module nào, package nào được export, service nào được dùng hoặc cung cấp?
- Chữ ký JAR hỏi: dữ liệu đã ký có còn nguyên vẹn không, chữ ký được tạo bằng public/private key nào, và certificate của signer có được xác thực/tin cậy theo môi trường không?

Vì vậy, **java --module-path** phân giải module không đồng nghĩa rằng bạn đã kiểm tra trust của signer. Nếu chính sách triển khai yêu cầu chỉ chạy artifact do nhà phát hành được phê duyệt ký, hãy xác minh JAR trước khi đưa nó vào thư mục triển khai hoặc trước bước khởi chạy.

## 9. Quy trình đóng gói và phát hành

Một pipeline phát hành modular JAR thường đi theo thứ tự:

1. Biên dịch module và dependency bằng cùng phiên bản API/JDK mục tiêu đã chọn.
2. Tạo JAR, bảo đảm **module-info.class** nằm ở thư mục gốc.
3. Kiểm tra module descriptor bằng **jar --describe-module --file app.jar**.
4. Ký artifact cuối cùng bằng jarsigner và khóa phát hành được quản lý an toàn.
5. Xác minh chữ ký bằng **jarsigner -verify -strict -verbose -certs**.
6. Nếu dùng timestamp, xác nhận timestamp xuất hiện và certificate chain của TSA có thể xác thực.
7. Đưa đúng file đã xác minh vào kho artifact hoặc thư mục triển khai.
8. Thử phân giải và chạy module bằng module path trên môi trường gần với production.

Nên ký sau khi build và đóng gói hoàn tất. Nếu chỉnh sửa nội dung entry đã ký, digest không còn khớp. Nếu thêm entry sau khi ký, entry mới có thể không có chữ ký bảo vệ và jarsigner có thể cảnh báo **unsigned entries**. Khi thay đổi artifact, hãy build lại và ký lại bản phát hành mới; đừng chỉnh sửa JAR đã ký bằng cách thêm/xóa file thủ công.

Nếu tổ chức cần nhiều bên cùng ký, một JAR có thể chứa nhiều bộ file .SF và signature block, mỗi bộ tương ứng một signer. Khi xác minh, có thể chỉ định alias cần có để kiểm tra các chữ ký của signer mong đợi. Điều này hữu ích trong quy trình phê duyệt nhiều bên, nhưng phải thống nhất chính sách signer nào là bắt buộc.

## 10. Những cảnh báo thường gặp

| Cảnh báo hoặc lỗi | Ý nghĩa có thể có | Việc cần kiểm tra |
|---|---|---|
| **jar is unsigned** hoặc không có signature file | JAR chưa được ký, hoặc chữ ký không được nhận diện | Kiểm tra file META-INF và đúng artifact đầu vào |
| **Invalid signature file digest** | Digest của manifest không khớp signature file | Có thể manifest đã bị sửa sau khi ký; build và ký lại |
| **digest error** hoặc entry digest không khớp | Nội dung entry đã ký thay đổi hoặc archive bị hỏng | So sánh artifact, tránh cập nhật JAR sau khi ký |
| **unsigned entries** | Có entry không được signer bảo vệ | Kiểm tra file được thêm sau khi ký hoặc entry bị bỏ sót |
| **signer certificate is self-signed** | Certificate tự ký, không có chain CA được tin cậy mặc định | Dùng certificate phát hành phù hợp hoặc cấu hình trust nội bộ |
| **certificate chain not validated** | Không xác thực được chain tới trust anchor | Kiểm tra chain, trust store và thời hạn certificate |
| **certificate expired** | Certificate signer đã hết hạn | Xem timestamp, thời điểm ký và quy trình gia hạn |
| **disabled algorithm** | Thuật toán bị security policy của JDK vô hiệu hóa | Ký lại bằng thuật toán/key strength hiện được chấp nhận |
| **not signed by alias** | Chữ ký không khớp signer alias được yêu cầu | Xác minh đúng keystore, alias và nguồn artifact |
| **no timestamp** | Chữ ký không có timestamp | Xem chính sách phát hành và cân nhắc dùng TSA |

Cảnh báo không phải lúc nào cũng đồng nghĩa byte của JAR đã bị thay đổi. Ví dụ certificate tự ký có thể đi kèm chữ ký mật mã hợp lệ nhưng không có trust chain mặc định. Hãy phân loại lỗi digest, lỗi chữ ký và lỗi certificate/trust trước khi quyết định phát hành.

## 11. Cách điều tra một modular JAR bị từ chối

Khi nhận được một JAR mà ứng dụng không thể sử dụng, hãy kiểm tra theo thứ tự:

1. **Xác định artifact thực tế.** Ghi lại đường dẫn, tên file, phiên bản và checksum của file nhận được. Đảm bảo bạn đang kiểm tra đúng bản được triển khai.
2. **Kiểm tra module descriptor.** Dùng **jar --describe-module --file app.jar**; xác nhận tên module và descriptor có đúng không.
3. **Kiểm tra chữ ký.** Dùng **jarsigner -verify -verbose -certs app.jar**; tìm entry lỗi, signer và cảnh báo certificate.
4. **Kiểm tra chế độ nghiêm ngặt.** Chạy lại với **-strict** trong môi trường CI hoặc phát hành để lấy exit code phản ánh severe warnings.
5. **Đối chiếu signer.** Kiểm tra certificate fingerprint, subject, issuer và alias với thông tin do bên phát hành công bố qua kênh độc lập.
6. **Kiểm tra module resolution.** Nếu chữ ký hợp lệ, tiếp tục xem **requires**, **exports**, **opens**, **uses**, **provides**, module path và dependency. Chữ ký hợp lệ không sửa được lỗi module resolution.
7. **Chạy lại trên JDK mục tiêu.** Security properties và thuật toán được chấp nhận có thể khác giữa các bản JDK. Kết quả xác minh trên một máy không tự động đại diện cho mọi môi trường.

Không nên tắt kiểm tra chữ ký hoặc hạ security policy chỉ để làm một JAR cũ chạy được. Hãy xác định lý do bị từ chối và yêu cầu nhà phát hành cung cấp artifact được ký bằng thuật toán/certificate phù hợp.

## 12. Những nhầm lẫn cần tránh

- **Cho rằng ký JAR là mã hóa:** chữ ký bảo vệ tính toàn vẹn và thông tin nguồn ký; nội dung archive vẫn đọc được.
- **Cho rằng mọi JAR trên module path đều phải ký:** JPMS không yêu cầu tất cả module phải có chữ ký. Yêu cầu ký đến từ chính sách phát hành hoặc triển khai.
- **Cho rằng chữ ký quyết định tên module:** tên module của explicit module nằm trong module descriptor; alias chỉ là tên entry trong keystore.
- **Cho rằng module descriptor được miễn chữ ký:** **module-info.class** là một entry trong JAR và được bảo vệ bởi digest nếu nó được ký cùng các entry còn lại.
- **Cho rằng jar --describe-module xác minh chữ ký:** lệnh này đọc module descriptor; dùng jarsigner để kiểm tra chữ ký.
- **Cho rằng jar verified luôn có nghĩa signer đáng tin:** cần đọc cảnh báo certificate và kiểm tra trust theo môi trường nhận.
- **Sửa JAR sau khi ký:** sửa entry đã ký sẽ làm digest sai; thêm entry có thể tạo unsigned entry. Hãy ký artifact sau cùng.
- **Dùng certificate tự ký như certificate công khai:** certificate tự ký cần được phân phối và tin cậy có chủ đích; nó không tự tạo niềm tin trên máy khác.

## 13. Tự kiểm tra

**1. JAR có module-info.class nhưng chưa ký có phải modular JAR không?**

Có. **module-info.class** ở thư mục gốc tạo nên modular JAR. Chữ ký là đặc tính riêng, không phải điều kiện để module path nhận diện module.

**2. Ký một modular JAR có làm thay đổi tên module hoặc directive requires không?**

Không. Jarsigner thêm metadata/chữ ký trong META-INF và digest trong manifest. Module descriptor vẫn xác định tên module, dependency và các directive JPMS.

**3. Vì sao jarsigner -verify có thể báo certificate self-signed dù digest hợp lệ?**

Vì kiểm tra chữ ký mật mã và kiểm tra trust của certificate là hai phần khác nhau. Certificate tự ký có thể xác minh được bằng public key của chính nó nhưng không có chain tới trust anchor mà máy nhận tin cậy.

**4. Vì sao phải ký sau khi build xong?**

Vì chữ ký gắn với digest của nội dung entry. Thay đổi entry đã ký làm digest không khớp; thêm entry sau khi ký có thể khiến entry mới không được bảo vệ.

**5. jar --describe-module và jarsigner -verify có thể thay thế nhau không?**

Không. Lệnh thứ nhất đọc descriptor để mô tả module; lệnh thứ hai kiểm tra chữ ký và tính toàn vẹn của JAR.

## 14. Ghi nhớ

JAR signing và JPMS bổ sung cho nhau nhưng giải quyết các lớp vấn đề khác nhau. Module descriptor xác định cấu trúc module; jarsigner dùng private key, certificate và digest để ký, rồi xác minh nội dung archive. Một modular JAR vẫn là modular JAR sau khi ký, miễn là module descriptor còn nguyên ở thư mục gốc.

Trong quy trình phát hành, hãy build và đóng gói trước, ký artifact cuối cùng, xác minh chữ ký và certificate, rồi mới đưa đúng artifact đó lên module path. Luôn đọc cảnh báo của jarsigner và kiểm tra trust của signer theo chính sách triển khai.

## Tài liệu tham khảo

- [The jarsigner Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [JAR File Specification — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html)
- [keytool Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)
