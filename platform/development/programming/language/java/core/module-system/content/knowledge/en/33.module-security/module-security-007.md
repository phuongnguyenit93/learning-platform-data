# Signed JAR, certificate và xác minh artifact

## 1. Mục tiêu

Một JAR có thể chứa class, resource và cả module descriptor. Khi phát hành thư viện hoặc ứng dụng, người nhận cần biết hai điều: nội dung artifact có bị thay đổi sau khi được ký hay không, và certificate dùng để ký có thuộc về nhà phát hành mà họ tin cậy hay không.

Java hỗ trợ ký và xác minh JAR bằng `jarsigner`, quản lý key pair và certificate bằng `keytool`. Hai công cụ này thường được dùng cùng nhau trong quy trình phát hành:

1. Tạo hoặc nhận certificate gắn với public key của nhà phát hành.
2. Dùng private key tương ứng để ký JAR.
3. Phát hành JAR đã ký cùng thông tin certificate và checksum cần thiết.
4. Người nhận xác minh chữ ký, certificate chain, danh tính signer và checksum trước khi đưa artifact vào môi trường sử dụng.

Chữ ký JAR cung cấp bằng chứng toàn vẹn cho các entry được ký và liên kết chữ ký với signer certificate. Chữ ký không mã hóa nội dung JAR và không tự chứng minh phần mềm an toàn.

Sau bài này, bạn có thể:

- Phân biệt private key, public key, certificate và keystore.
- Tạo key pair cho môi trường thử nghiệm và hiểu quy trình certificate do CA cấp.
- Ký JAR bằng `jarsigner`.
- Xác minh chữ ký và xem thông tin certificate bằng `jarsigner` và `keytool`.
- Đối chiếu SHA-256 và phân biệt checksum, chữ ký và artifact provenance.
- Kiểm tra module descriptor của một modular JAR đã ký.

## 2. Các thành phần trong quy trình ký

| Thành phần | Vai trò |
| --- | --- |
| Private key | Bí mật của nhà phát hành, dùng để tạo chữ ký. Phải được bảo vệ trong keystore hoặc hệ thống quản lý khóa. |
| Public key | Phần khóa công khai dùng để kiểm tra chữ ký. |
| Certificate | Tài liệu số liên kết public key với danh tính hoặc tổ chức, được ký bởi CA hoặc tự ký. |
| Keystore | Kho lưu key pair và certificate chain; ví dụ định dạng PKCS12. |
| JAR signature | Dữ liệu chữ ký và digest cho các entry trong archive. |
| Checksum | Giá trị hash của toàn bộ file artifact, dùng để so sánh hai bản byte-for-byte. |

Certificate không chứa private key. Người nhận có thể phân phối certificate và public key, nhưng private key ký phát hành phải được giữ kín.

Một certificate do CA đáng tin cậy cấp giúp người nhận kiểm tra chuỗi tin cậy và danh tính signer theo chính sách của họ. Certificate tự ký vẫn có thể dùng để thử nghiệm và kiểm tra tính toàn vẹn, nhưng người nhận phải có cách độc lập để xác nhận public key đó thực sự thuộc về nhà phát hành.

## 3. Chuẩn bị keystore và certificate

### Tạo key pair cho thử nghiệm

Có thể dùng `keytool` để tạo RSA key pair và certificate tự ký trong keystore PKCS12:

~~~bash
keytool -genkeypair \
    -alias release \
    -keyalg RSA \
    -keysize 3072 \
    -sigalg SHA256withRSA \
    -validity 365 \
    -storetype PKCS12 \
    -keystore release.p12 \
    -dname "CN=Example Release, O=Example, C=VN"
~~~

Giải thích:

- `-alias release`: tên định danh entry trong keystore.
- `-keyalg RSA` và `-keysize 3072`: tạo RSA key pair với kích thước khóa được chỉ định.
- `-sigalg SHA256withRSA`: thuật toán chữ ký dùng cho certificate.
- `-validity 365`: thời hạn certificate tính theo ngày.
- `-storetype PKCS12`: dùng định dạng keystore PKCS12.
- `-keystore release.p12`: file lưu private key và certificate.
- `-dname`: Distinguished Name của chủ thể certificate.

Lệnh sẽ hỏi mật khẩu keystore và mật khẩu private key. Không đặt mật khẩu thật trực tiếp trong script, command history hoặc tài liệu dự án.

Đây là certificate tự ký phù hợp cho lab. Trong production, certificate phải được cấp và xác minh theo chính sách của tổ chức hoặc CA mà người nhận tin cậy.

### Quy trình certificate do CA cấp

Với certificate phát hành thực tế, quy trình thường là:

1. Tạo key pair trong keystore hoặc hệ thống quản lý khóa.
2. Tạo Certificate Signing Request (CSR) từ public key và thông tin tổ chức.
3. Gửi CSR tới CA theo quy trình xác minh danh tính.
4. Nhận certificate signer cùng intermediate/root certificate chain.
5. Import certificate reply vào đúng alias chứa private key tương ứng.
6. Kiểm tra subject, issuer, thời hạn, key usage và chain trước khi ký artifact.

Có thể tạo CSR bằng:

~~~bash
keytool -certreq \
    -alias release \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release.csr
~~~

CA trả về certificate cho public key trong CSR. Khi import certificate reply, phải dùng đúng alias/key pair đã tạo CSR và bảo đảm certificate chain được thiết lập hợp lệ.

### Xem certificate trong keystore

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release
~~~

Kết quả giúp kiểm tra alias, loại entry, subject, issuer, serial number, thời hạn và certificate chain. Với entry chứa private key, keystore sẽ quản lý private key cùng certificate chain tương ứng.

## 4. Ký JAR bằng jarsigner

Giả sử đã build artifact:

~~~text
build/
└── app.jar
~~~

Dùng alias `release` để ký và tạo file đầu ra riêng:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -signedjar app-signed.jar \
    app.jar release
~~~

Trong đó:

- `-keystore`: chỉ định kho chứa private key và certificate.
- `-storetype`: định dạng kho khóa.
- `-signedjar`: tên JAR đầu ra đã ký.
- `app.jar`: artifact đầu vào.
- `release`: alias của private key dùng ký.

Công cụ có thể yêu cầu mật khẩu keystore và private key. Hãy lấy mật khẩu từ cơ chế quản lý secret phù hợp, không ghi vào Git hoặc log CI.

Nếu bỏ `-signedjar`, jarsigner có thể cập nhật chữ ký trực tiếp vào JAR đầu vào. Trong quy trình phát hành, tạo file đầu ra riêng giúp giữ lại artifact chưa ký để đối chiếu và dễ truy vết hơn.

### Chuyện gì được ghi vào JAR?

JAR đã ký thường có các file trong `META-INF/`, ví dụ:

~~~text
META-INF/
├── MANIFEST.MF
├── RELEASE.SF
└── RELEASE.RSA
~~~

Tên file cụ thể phụ thuộc signer và thuật toán. File manifest lưu digest của các entry; file `.SF` chứa digest liên quan đến manifest; file signature block như `.RSA`, `.DSA` hoặc `.EC` chứa chữ ký và certificate cần thiết để xác minh.

Khi người nhận xác minh, công cụ kiểm tra chữ ký và digest để phát hiện nội dung entry đã bị thay đổi so với nội dung được ký.

## 5. Xác minh chữ ký JAR

Lệnh cơ bản:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Ý nghĩa:

- `-verify`: xác minh chữ ký trong JAR.
- `-verbose`: hiển thị thông tin chi tiết theo entry.
- `-certs`: hiển thị thông tin certificate liên quan tới signer.

Kết quả thành công có thể kết thúc bằng thông báo:

~~~text
jar verified.
~~~

Tuy nhiên, không nên chỉ nhìn dòng này rồi kết luận artifact đã được một nhà phát hành đáng tin cậy ký. Kết quả còn có thể kèm cảnh báo về certificate tự ký, certificate chưa được tin cậy, hết hạn, thiếu timestamp hoặc thuật toán không còn được khuyến nghị.

Có thể dùng chế độ strict:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

`-strict` làm cho các cảnh báo liên quan tới certificate và chữ ký được xử lý nghiêm ngặt hơn và có thể khiến lệnh trả về mã lỗi. Trong CI, hãy kiểm tra exit code và lưu output xác minh làm bằng chứng cho bước phát hành.

Khi đọc output verbose, chú ý từng entry:

- Entry được ký phải có trạng thái xác minh phù hợp.
- Entry không được ký có thể xuất hiện như unsigned.
- Entry bị thay đổi sau khi ký sẽ không vượt qua kiểm tra digest.
- Nếu JAR có nhiều signer, cần xác định signer nào đã ký từng entry.

Một JAR có thể chứa cả entry đã ký và chưa ký. Nếu chính sách phát hành yêu cầu mọi class/resource đều được bảo vệ, cần xác nhận không có entry ứng dụng quan trọng nào bị bỏ sót.

## 6. Kiểm tra certificate được dùng để ký

Có thể trích thông tin certificate trực tiếp từ JAR:

~~~bash
keytool -printcert -jarfile app-signed.jar
~~~

Lệnh này hiển thị certificate signer trong JAR, thường gồm subject, issuer, serial number, thời hạn hiệu lực, fingerprint và thông tin thuật toán.

Nếu có file certificate riêng:

~~~bash
keytool -printcert -file signer.cer
~~~

Khi xác minh signer, cần kiểm tra:

- **Subject:** danh tính được ghi trong certificate có đúng nhà phát hành mong đợi không.
- **Issuer:** certificate được cấp bởi CA nào.
- **Validity:** thời điểm ký có nằm trong thời hạn certificate hay không.
- **Certificate chain:** có xây dựng được chuỗi tới trust anchor được chấp nhận không.
- **Fingerprint:** fingerprint có khớp giá trị được nhà phát hành công bố qua kênh độc lập không.
- **Key usage và thuật toán:** certificate và thuật toán có phù hợp chính sách ký code của tổ chức không.

Certificate tự ký có thể cho phép kiểm tra chữ ký mật mã nhưng không tự tạo ra niềm tin về danh tính. Muốn tin certificate tự ký, người nhận phải xác minh fingerprint qua một kênh đáng tin cậy rồi chủ động thiết lập trust theo chính sách của mình.

## 7. Checksum và chữ ký trả lời hai câu hỏi khác nhau

Checksum SHA-256 cho biết hai file có cùng nội dung byte hay không. Chữ ký JAR kiểm tra các entry được ký và gắn chúng với signer certificate.

Tính checksum của artifact đã ký:

Trên Linux/macOS:

~~~bash
sha256sum app-signed.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\app-signed.jar -Algorithm SHA256
~~~

Đối chiếu hash với giá trị được công bố qua một kênh tin cậy. Nếu file tải về có hash khác giá trị tham chiếu, file không phải bản byte-for-byte được công bố.

Không nên coi checksum tải cùng từ chính máy chủ đang phân phối artifact là bằng chứng độc lập: nếu cả artifact và file checksum đều bị thay thế, hai giá trị vẫn có thể khớp nhau.

| Cơ chế | Điều được kiểm tra | Điều không tự chứng minh |
| --- | --- | --- |
| SHA-256 checksum | Toàn bộ bytes của file có khớp giá trị tham chiếu không. | Ai tạo file hoặc file có an toàn không. |
| JAR signature | Digest của entry được ký có hợp lệ và chữ ký có khớp public key signer không. | Certificate đó có thuộc nhà phát hành mà người nhận tin cậy không. |
| Certificate chain validation | Certificate có liên kết tới trust anchor được chấp nhận theo chính sách hay không. | Mã nguồn không có lỗ hổng hoặc artifact không độc hại. |
| Build provenance/attestation | Artifact được tạo từ nguồn, quy trình và môi trường build nào theo bằng chứng được cung cấp. | Chất lượng hoặc tính an toàn tuyệt đối của source và dependency. |

Một quy trình phát hành tốt có thể dùng cả chữ ký, checksum và provenance. Mỗi cơ chế bổ sung một loại bằng chứng khác nhau.

## 8. Timestamp và thời hạn certificate

Certificate có thời hạn hiệu lực. Nếu signer certificate hết hạn sau khi phát hành, người nhận vẫn cần bằng chứng đáng tin cậy rằng artifact đã được ký khi certificate còn hợp lệ.

JAR signing hỗ trợ timestamp từ Time Stamping Authority (TSA). Khi ký, có thể cung cấp endpoint TSA:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -tsa <tsa-url> \
    -signedjar app-signed.jar \
    app.jar release
~~~

Thay `<tsa-url>` bằng endpoint TSA được tổ chức phê duyệt. TSA cấp timestamp token gắn thời điểm ký với bằng chứng của TSA.

Timestamp đáng tin cậy giúp đánh giá thời điểm chữ ký được tạo so với thời hạn certificate. Nó không biến certificate không đáng tin thành certificate đáng tin; người nhận vẫn cần kiểm tra chain, chính sách TSA và trạng thái certificate theo yêu cầu của mình.

## 9. Điều gì làm chữ ký mất hiệu lực?

Sau khi ký, không được chỉnh sửa tùy tiện nội dung các entry đã ký.

Ví dụ, các thao tác sau có thể làm xác minh thất bại:

- Thay đổi class hoặc resource đã ký.
- Sửa manifest sau khi ký.
- Repack JAR làm thay đổi bytes của entry.
- Thay module descriptor sau khi ký.
- Chạy công cụ đóng gói lại và vô tình loại bỏ hoặc làm hỏng dữ liệu chữ ký.

Nếu cần sửa artifact, hãy build lại từ source, chạy test, rồi ký lại artifact cuối cùng. Không ký trước rồi mới thêm resource hoặc thay đổi nội dung phát hành.

JAR signature bảo vệ các entry được ký theo digest được lưu trong cấu trúc signature. Vì vậy, cần kiểm tra output xác minh để biết entry nào được ký và có bị thay đổi không, đặc biệt khi artifact có nhiều nguồn đóng góp hoặc được xử lý qua nhiều bước CI.

## 10. Xác minh modular JAR

Một modular JAR có module descriptor `module-info.class`. Chữ ký JAR và module descriptor phục vụ hai mục đích riêng:

- Module descriptor khai báo tên module, dependency, package exports/opens, service uses/provides.
- JAR signature bảo vệ tính toàn vẹn của các entry được ký và gắn nội dung với signer.

Sau khi ký, có thể kiểm tra module descriptor:

~~~bash
jar --describe-module --file app-signed.jar
~~~

Nếu cần liệt kê nội dung archive:

~~~bash
jar --list --file app-signed.jar
~~~

Và xác minh chữ ký:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Việc `jar --describe-module` hiển thị descriptor đúng không thay thế bước xác minh chữ ký. Ngược lại, chữ ký hợp lệ cũng không chứng minh descriptor có dependency hoặc export đúng với kiến trúc mong muốn.

Nếu thay đổi `module-info.java`, hãy biên dịch và đóng gói lại modular JAR, sau đó ký artifact mới. Nếu cần kiểm tra module name, version, requires, exports, uses hoặc provides, hãy đọc descriptor và so sánh với cấu hình phát hành mong đợi.

## 11. Quy trình phát hành và xác minh đề xuất

### Phía nhà phát hành

1. Build artifact từ commit đã xác định.
2. Chạy test và các bước kiểm tra chất lượng.
3. Kiểm tra module descriptor nếu artifact là modular JAR.
4. Ký đúng artifact cuối cùng bằng private key được bảo vệ.
5. Xác minh lại JAR sau khi ký bằng `jarsigner -verify`.
6. Tính SHA-256 của file đã ký.
7. Lưu bằng chứng build, certificate fingerprint, checksum và provenance theo quy trình phát hành.
8. Phân phối artifact cùng thông tin xác minh qua kênh chính thức.

### Phía người nhận

1. Tải artifact và thông tin checksum/signature từ nguồn phân phối.
2. Xác minh SHA-256 với giá trị tham chiếu lấy từ kênh tin cậy.
3. Chạy `jarsigner -verify -strict -verbose -certs`.
4. Kiểm tra subject, issuer, validity, fingerprint và certificate chain.
5. Xác nhận signer đúng nhà phát hành mong đợi theo chính sách trust.
6. Kiểm tra module descriptor và dependency nếu artifact được dùng trên module path.
7. Chỉ đưa artifact vào build hoặc runtime sau khi các bước xác minh bắt buộc đều đạt.

Nếu chữ ký hợp lệ nhưng certificate không được tin cậy, hãy dừng để xác minh danh tính signer. Nếu checksum không khớp, hãy lấy lại artifact từ nguồn chính thức và điều tra sự khác biệt. Không bỏ qua cảnh báo chỉ để làm cho pipeline chạy tiếp.

## 12. Ghi nhớ

- Private key dùng để ký phải được bảo vệ; certificate công khai liên kết public key với danh tính signer.
- `keytool` tạo và quản lý key pair, CSR, certificate và keystore.
- `jarsigner` ký JAR và xác minh chữ ký.
- `jarsigner -verify -strict -verbose -certs` giúp kiểm tra nghiêm ngặt hơn và xem certificate liên quan.
- `keytool -printcert -jarfile` hiển thị certificate được dùng trong JAR.
- Checksum SHA-256 so sánh toàn bộ bytes; JAR signature xác minh các entry được ký và signer.
- Chữ ký hợp lệ không đồng nghĩa certificate đáng tin, và certificate đáng tin không đồng nghĩa phần mềm an toàn.
- Ký sau khi hoàn tất build/package; mọi thay đổi nội dung sau đó cần được ký lại.
- Với modular JAR, kiểm tra riêng module descriptor và chữ ký artifact.

Khi phát hành thư viện hoặc ứng dụng Java, hãy xem xác minh artifact là một phần của quy trình giao nhận: kiểm tra bytes, chữ ký, danh tính signer và cấu trúc module trước khi sử dụng.
