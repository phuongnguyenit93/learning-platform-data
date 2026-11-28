# Xử lý mật khẩu an toàn khi dùng keytool và jarsigner

keytool và jarsigner cần đọc keystore hoặc private key để tạo, quản lý và kiểm tra chữ ký số. Mật khẩu truyền sai cách có thể bị lưu trong shell history, danh sách tiến trình, log CI hoặc file cấu hình. Vì vậy, cần chọn nguồn cung cấp mật khẩu phù hợp: nhập tại prompt khi thao tác thủ công, dùng biến môi trường hoặc file secret có quyền truy cập hạn chế trong automation, hoặc dùng protected authentication path khi làm việc với token phần cứng.

JDK 26 hỗ trợ các dạng tùy chọn mật khẩu **-storepass:env**, **-storepass:file**, **-keypass:env** và **-keypass:file**. Phần sau dấu hai chấm là tên biến môi trường hoặc đường dẫn file, không phải giá trị mật khẩu. Cách viết này giúp tránh đặt mật khẩu trực tiếp trong đối số command line. Tuy nhiên, biến môi trường và file vẫn là nơi chứa bí mật; chúng cần được cấp phát, giới hạn quyền đọc và thu hồi đúng cách.

Bài học tập trung vào hai công cụ hiện hành trong JDK 26, cách phân biệt mật khẩu keystore với mật khẩu private key, cách ký và xác minh JAR, cũng như cách tránh làm lộ bí mật trong máy cá nhân và pipeline CI/CD.

keytool và jarsigner là các công cụ dòng lệnh tiêu chuẩn đi kèm JDK, không phải preview hoặc incubator API. Các tùy chọn password source được mô tả trong tài liệu công cụ JDK 26; không cần bật --enable-preview để sử dụng.

## 1. Phân biệt store password và key password

Một keystore có thể chứa nhiều loại entry. Hai loại thường gặp nhất là trusted certificate entry và key entry. Key entry có thể chứa private key kèm certificate chain hoặc secret key.

| Mật khẩu | Tên tùy chọn | Vai trò |
|---|---|---|
| Keystore password | **-storepass** | Mở keystore và kiểm tra tính toàn vẹn của nội dung keystore theo định dạng/provider |
| Private key password | **-keypass** | Mở khóa private key hoặc secret key trong entry được chỉ định bằng alias |
| Source keystore password | **-srcstorepass** | Mở keystore nguồn khi import |
| Destination keystore password | **-deststorepass** | Bảo vệ keystore đích khi import |
| Source key password | **-srckeypass** | Mở private/secret key trong entry nguồn |
| Destination key password | **-destkeypass** | Bảo vệ key entry được tạo ở keystore đích |

Hai mật khẩu này có thể khác nhau, tùy định dạng keystore và provider. Đừng giả định **-storepass** luôn mở được private key hoặc **-keypass** luôn thay thế được **-storepass**.

JDK 26 mặc định dùng loại keystore PKCS12. PKCS12 được hỗ trợ rộng rãi và phù hợp cho trao đổi giữa các công cụ. Tuy nhiên, một số công cụ bên thứ ba yêu cầu store password và key password trong PKCS12 phải giống nhau. Khi cần tương thích liên công cụ, hãy kiểm tra yêu cầu của hệ thống đích và dùng cùng một giá trị nếu cần.

Nếu keystore nằm trên HSM hoặc token PKCS#11, **-storepass** có thể là PIN của token. Với thiết bị có protected authentication path như PIN pad hoặc xác thực sinh trắc học, dùng cơ chế **-protected** theo hướng dẫn của provider thay vì truyền PIN như mật khẩu thông thường.

## 2. Vì sao không truyền mật khẩu trực tiếp trên command line?

Cách viết sau không an toàn cho môi trường dùng chung:

~~~sh
keytool -list -keystore release.p12 -storepass MySecretPassword
~~~

Giá trị mật khẩu có thể xuất hiện trong:

- Shell history hoặc file script.
- Danh sách đối số tiến trình mà người dùng khác có quyền quan sát.
- Log của CI/CD, wrapper script hoặc công cụ giám sát.
- Báo cáo lỗi và bản ghi terminal được lưu lại.
- Cấu hình build, Dockerfile, file YAML hoặc source repository.

JDK 26 documentation khuyến cáo không đặt mật khẩu trực tiếp trong command line hoặc script, trừ mục đích thử nghiệm hoặc hệ thống được bảo vệ phù hợp.

Không dùng các cách sau trong pipeline phát hành:

~~~sh
# Không làm: mật khẩu literal nằm trong command.
jarsigner -storepass Secret123 -keypass Secret123 app.jar release

# Không làm: ghi mật khẩu vào script được commit.
SIGNING_PASSWORD=Secret123
~~~

Việc che dấu log bằng ký tự sao không giải quyết được việc secret đã đi qua process arguments hoặc file script. Hãy chọn cơ chế nhập bí mật trước khi tiến trình chạy.

## 3. Ba cách cung cấp mật khẩu

### 3.1. Nhập tại prompt — phù hợp với thao tác thủ công

Nếu bỏ tùy chọn mật khẩu, công cụ có thể yêu cầu nhập tương tác. Ví dụ tạo keystore:

~~~sh
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore release.p12
~~~

keytool sẽ hỏi store password. Với key password, keytool trước tiên thử dùng store password để truy cập key entry; nếu không thành công thì yêu cầu nhập mật khẩu private key.

Ký JAR theo cách tương tác:

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

jarsigner hỏi store password. Nếu password của private key khác store password, công cụ cũng hỏi key password.

Ưu điểm:

- Mật khẩu không nằm trong command line.
- Không cần lưu secret trong script.
- Phù hợp với thao tác quản trị thủ công hoặc quy trình phê duyệt có người vận hành.

Giới hạn:

- Không phù hợp với job CI/CD hoàn toàn không có người tương tác.
- Prompt có thể bị treo nếu job chạy trong môi trường không có terminal.
- Không nên chuyển mật khẩu qua thao tác copy/paste từ tài liệu hoặc ticket.

### 3.2. Lấy mật khẩu từ biến môi trường

Cú pháp trong JDK 26:

~~~sh
-storepass:env TEN_BIEN_MOI_TRUONG
-keypass:env TEN_BIEN_MOI_TRUONG
~~~

Ví dụ ký JAR khi CI runner đã nhận secret qua secret store và đưa chúng vào môi trường của tiến trình:

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:env SIGNING_STOREPASS \
  -keypass:env SIGNING_KEYPASS \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Đối số **SIGNING_STOREPASS** là tên biến môi trường. Mật khẩu thực được đọc từ biến đó khi công cụ chạy; giá trị mật khẩu không xuất hiện trong command line.

Có thể dùng cách tương tự với keytool:

~~~sh
keytool -list \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:env SIGNING_STOREPASS
~~~

Lưu ý khi dùng biến môi trường:

- Để CI secret manager hoặc hệ thống cấp phát bí mật đưa giá trị vào môi trường job; không ghi giá trị thật vào YAML, script hoặc repository.
- Chỉ cấp secret cho job cần ký, không cấp cho toàn bộ pipeline.
- Tránh bật chế độ dump toàn bộ environment trong log chẩn đoán.
- Không dùng biến môi trường làm kho bí mật lâu dài. Tiến trình con có thể kế thừa biến; người có quyền phù hợp trên máy runner có thể đọc environment của tiến trình.
- Xóa hoặc kết thúc phạm vi secret sau khi job hoàn tất; không giữ biến ở cấp máy hoặc tài khoản dùng chung nếu không cần.

### 3.3. Lấy mật khẩu từ file

Cú pháp:

~~~sh
-storepass:file /duong/dan/secret/storepass.txt
-keypass:file /duong/dan/secret/keypass.txt
~~~

Ví dụ trên Linux hoặc môi trường container có secret mount:

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:file /run/secrets/signing-storepass \
  -keypass:file /run/secrets/signing-keypass \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Trên Windows PowerShell, có thể dùng một lệnh trên một dòng:

~~~powershell
jarsigner -keystore release.p12 -storetype PKCS12 -storepass:file C:\secure\signing-storepass.txt -keypass:file C:\secure\signing-keypass.txt -signedjar app-signed.jar app.jar release
~~~

Đường dẫn file xuất hiện trong command line nhưng nội dung mật khẩu không xuất hiện. Hãy bảo vệ file bằng quyền truy cập của hệ điều hành:

- Linux: giới hạn owner và quyền đọc, ví dụ chỉ owner được đọc file secret.
- Windows: dùng ACL chỉ cấp quyền cho service account hoặc người vận hành cần thiết.
- CI/CD: ưu tiên secret mount hoặc file tạm được tạo từ secret store, thay vì file cố định trong workspace.
- Không đưa file secret vào Git, artifact build, Docker image, bản sao lưu không mã hóa hoặc thư mục log.
- Xóa file tạm sau khi job kết thúc theo chính sách của nền tảng; việc xóa file không thay thế quyền truy cập hạn chế và mã hóa lưu trữ.

### 3.4. So sánh các cách cung cấp

| Cách | Secret xuất hiện ở đâu? | Phù hợp |
|---|---|---|
| Prompt tương tác | Bộ nhớ/luồng nhập của tiến trình | Quản trị thủ công |
| **:env** | Environment của tiến trình và tiến trình con có thể kế thừa | CI runner có secret injection |
| **:file** | File được giới hạn quyền đọc | Secret mount hoặc file tạm được bảo vệ |
| Literal trên command line | Process arguments, history, log có thể lưu lại | Chỉ thử nghiệm trong môi trường cô lập; tránh trong vận hành |
| Protected authentication path | Thiết bị hoặc cơ chế xác thực được bảo vệ | HSM/token có PIN pad hoặc cơ chế xác thực phần cứng |

Không có cách nào tự động an toàn chỉ vì tên tùy chọn có chữ env hoặc file. Mức bảo vệ phụ thuộc vào cách hệ điều hành, runner và secret store quản lý nguồn bí mật đó.

## 4. Dùng keytool tạo keystore mà không lộ mật khẩu

Ví dụ tạo cặp khóa và certificate tự ký ban đầu:

~~~sh
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore release.p12
~~~

keytool sẽ hỏi mật khẩu. Khi không chỉ định **-keypass**, công cụ thử dùng store password để bảo vệ key entry; nếu cần mật khẩu khác, nó sẽ hỏi thêm.

Nếu môi trường automation yêu cầu dùng secret được cấp sẵn:

~~~sh
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore release.p12 \
  -storepass:env SIGNING_STOREPASS \
  -keypass:env SIGNING_KEYPASS
~~~

Nếu PKCS12 provider hoặc công cụ đích yêu cầu store password và key password giống nhau, hãy cấp cùng một secret cho hai biến. Không suy luận rằng mọi loại keystore đều có cùng quy tắc.

Trong JDK 26, mặc định key size của RSA khi tạo key pair là 3072 bit. Có thể ghi rõ **-keysize 3072** để command thể hiện ý định; với quy trình dài hạn, vẫn cần kiểm tra chính sách thuật toán và yêu cầu tương thích của tổ chức.

Mật khẩu tối thiểu mà keytool chấp nhận cho các tùy chọn mật khẩu dạng literal không phải là khuyến nghị về độ mạnh. Hãy dùng secret ngẫu nhiên đủ entropy do secret manager tạo, không dùng tên dự án, alias, tên người dùng hoặc mật khẩu dùng lại từ hệ thống khác.

## 5. Kiểm tra keystore và alias

Để liệt kê entry và kiểm tra integrity của keystore, cung cấp store password qua prompt hoặc nguồn secret:

~~~sh
keytool -list -v \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:env SIGNING_STOREPASS
~~~

Lệnh này giúp kiểm tra alias, loại entry, certificate chain và thông tin chứng chỉ. Không đưa private key ra màn hình hoặc export private key chỉ để xác minh alias.

Nếu chỉ xem thông tin keystore mà không cung cấp password, keytool có thể hiển thị thông tin nhưng không xác minh được integrity của nội dung keystore và sẽ cảnh báo. Vì vậy, trong bước kiểm tra phát hành, hãy cung cấp password đúng cách để xác minh integrity.

Một số lệnh keytool thường dùng:

| Nhu cầu | Lệnh | Mật khẩu cần thiết |
|---|---|---|
| Tạo key pair | **-genkeypair** | Store password; key password nếu khác |
| Tạo CSR | **-certreq** | Store password và key password nếu khác |
| Import certificate reply | **-importcert** | Store password; key password nếu cần cập nhật key entry |
| Liệt kê keystore | **-list** | Store password để xác minh integrity |
| Import keystore khác | **-importkeystore** | Source/destination store và key passwords tùy entry |
| Đổi store password | **-storepasswd** | Store password hiện tại và password mới |
| Đổi key entry password | **-keypasswd** | Key password hiện tại và password mới, tùy hỗ trợ của keystore type/provider |

Với importkeystore, các tùy chọn **-srcstorepass**, **-deststorepass**, **-srckeypass** và **-destkeypass** cũng hỗ trợ modifier **:env** và **:file**. Kiểm tra quy tắc của keystore đích: một số công cụ yêu cầu storepass và keypass của PKCS12 phải giống nhau.

## 6. Đổi mật khẩu keystore và key entry

Đổi mật khẩu là thao tác quản trị riêng. Không nên đưa password mới vào **-new** dưới dạng literal trong script. Với thao tác thủ công, để công cụ hỏi các giá trị:

~~~sh
keytool -storepasswd \
  -keystore release.p12 \
  -storetype PKCS12
~~~

Công cụ yêu cầu store password hiện tại và password mới. Nếu muốn dùng nguồn secret tự động cho mật khẩu hiện tại, **-storepass:env** hoặc **-storepass:file** có thể được dùng theo cú pháp chung. Tuy nhiên, không mặc định rằng mọi tùy chọn nhập password mới như **-new** đều hỗ trợ modifier **:env** hoặc **:file**; hãy kiểm tra đúng phần mô tả lệnh của JDK đang chạy.

Đổi password của key entry bằng **-keypasswd** phụ thuộc keystore type và provider. Một số định dạng có giới hạn về việc dùng password riêng cho từng key entry. Trước khi thay đổi keystore phát hành, hãy sao lưu an toàn, thử trên bản sao và kiểm tra lại bằng keytool cùng jarsigner.

Quy trình thay đổi mật khẩu an toàn:

1. Xác định keystore, alias và định dạng thực tế.
2. Xác nhận có backup được bảo vệ và có thể khôi phục.
3. Dùng prompt hoặc quy trình secret management được phê duyệt để nhập password mới.
4. Kiểm tra lại bằng **keytool -list** với store password mới.
5. Kiểm tra private key entry và thực hiện ký thử trên JAR thử nghiệm.
6. Cập nhật secret trong secret manager và thu hồi bản cũ theo quy trình.
7. Xóa file tạm hoặc secret cũ khỏi runner theo chính sách lưu trữ.

Không đổi mật khẩu keystore đang được nhiều pipeline sử dụng mà chưa cập nhật secret đồng bộ. Điều đó có thể làm các job phát hành thất bại hoặc khiến bản build mới không thể truy cập private key.

## 7. Ký JAR bằng jarsigner

jarsigner sử dụng private key trong keystore để tạo chữ ký cho các entry của JAR. Chữ ký giúp phát hiện nội dung bị thay đổi và xác minh chữ ký bằng public key trong certificate. Chữ ký số không mã hóa nội dung JAR và không che giấu mã nguồn hoặc tài nguyên bên trong.

Cách ký tương tác:

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

jarsigner hỏi store password. Nếu password của private key khác store password, công cụ yêu cầu nhập thêm key password.

Cách ký trong CI với secret được inject qua environment:

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:env SIGNING_STOREPASS \
  -keypass:env SIGNING_KEYPASS \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Cách dùng file secret:

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:file /run/secrets/signing-storepass \
  -keypass:file /run/secrets/signing-keypass \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Nên chỉ định **-signedjar** để tạo file đầu ra riêng và giữ nguyên artifact đầu vào. Nếu bỏ **-signedjar**, jarsigner ghi đè JAR gốc bằng bản đã ký.

### 7.1. Mật khẩu không thay thế quy trình quản lý khóa ký

Người có store password và key password phù hợp có thể sử dụng private key để ký. Vì vậy, chỉ job phát hành cần có quyền truy cập signing secret.

Một số nguyên tắc:

- Không lưu keystore chứa private key trong repository.
- Không đưa keystore vào JAR ứng dụng hoặc Docker image runtime.
- Tách khóa ký production khỏi khóa test và staging.
- Dùng alias rõ ràng và quản lý certificate chain đầy đủ.
- Hạn chế quyền đọc file keystore và secret.
- Ưu tiên HSM hoặc dịch vụ ký tập trung khi tổ chức cần kiểm soát khóa nghiêm ngặt.
- Có quy trình rotate, thu hồi và thay certificate khi khóa bị lộ.

Nếu sử dụng certificate code signing, xác nhận certificate có mục đích sử dụng phù hợp và được bên nhận tin cậy. Không dùng certificate tự ký cho phát hành công khai chỉ vì jarsigner có thể tạo chữ ký thành công.

### 7.2. Dùng timestamp khi ký

Có thể yêu cầu TSA đóng dấu thời gian cho chữ ký:

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:env SIGNING_STOREPASS \
  -keypass:env SIGNING_KEYPASS \
  -tsa https://tsa.example.org \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Thay URL minh họa bằng dịch vụ TSA được tổ chức tin cậy và cho phép sử dụng. Timestamp giúp bên xác minh kiểm tra chữ ký được tạo trong thời gian certificate ký còn hiệu lực, với điều kiện timestamp token và chuỗi certificate TSA hợp lệ.

Timestamp không làm cho một chữ ký yếu trở nên an toàn, không khắc phục certificate bị thu hồi trước thời điểm ký và không thay thế việc bảo vệ private key.

## 8. Xác minh JAR đã ký

Xác minh chữ ký không cần password của private key hoặc password dùng để ký:

~~~sh
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

- **-verify** yêu cầu kiểm tra chữ ký và integrity.
- **-strict** coi các cảnh báo nghiêm trọng là lỗi.
- **-verbose** hiển thị tiến trình và entry.
- **-certs** hiển thị thông tin certificate của signer.

Không truyền **-storepass** hoặc **-keypass** khi chỉ xác minh chữ ký. Các password này liên quan đến thao tác ký; việc xác minh sử dụng public key/certificate trong signature block.

Cần đọc toàn bộ cảnh báo. Kết quả xác minh chữ ký mật mã thành công không tự động chứng minh certificate signer thuộc tổ chức mà ứng dụng mong đợi. Hãy kiểm tra:

- Danh tính signer và fingerprint certificate.
- Certificate chain và trust anchor.
- Thời hạn certificate và timestamp.
- KeyUsage/ExtendedKeyUsage phù hợp với code signing.
- Thuật toán có bị vô hiệu hóa hoặc đánh dấu legacy không.
- JAR có entry chưa ký hoặc entry được thêm sau khi ký không.

JDK 26 dùng các security properties như **jdk.jar.disabledAlgorithms** và **jdk.security.legacyAlgorithms** để đánh giá thuật toán ký. Thuật toán bị disabled có thể khiến JAR bị xem như unsigned; thuật toán legacy tạo cảnh báo. Không hạ chính sách bảo mật chỉ để chấp nhận một chữ ký cũ.

## 9. Dùng keytool và jarsigner với PKCS#11/HSM

Nếu private key nằm trong HSM hoặc smart card, ứng dụng ký có thể dùng key handle do provider cung cấp thay vì export private key ra file. Với SunPKCS11 đã được cấu hình, keytool và jarsigner có thể truy cập token bằng:

~~~sh
keytool -keystore NONE -storetype PKCS11 -list
~~~

Để ký JAR với token:

~~~sh
jarsigner \
  -keystore NONE \
  -storetype PKCS11 \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Nếu token yêu cầu protected authentication path, dùng tùy chọn **-protected** theo đúng cú pháp của công cụ và cấu hình thiết bị. Trong trường hợp này không cung cấp password option; PIN được nhập qua thiết bị xác thực được bảo vệ.

Không nhầm **-keystore NONE** với một keystore rỗng. Nó báo cho KeyStore API rằng dữ liệu nằm trong token/provider không dùng file stream. Provider PKCS#11, thư viện native, token slot và alias phải được cấu hình đúng trước khi gọi công cụ.

HSM giảm nguy cơ private key bị export, nhưng không tự bảo vệ PIN hoặc quyền gọi thao tác ký. Hãy giới hạn tài khoản dịch vụ, quyền sử dụng key object, audit log và cơ chế phê duyệt ký.

## 10. Mật khẩu trong CI/CD và môi trường build

Một pipeline ký JAR nên tách rõ ba loại dữ liệu:

- Artifact đầu vào cần ký.
- Keystore hoặc kết nối tới HSM chứa private key.
- Secret dùng để mở keystore/private key hoặc xác thực token.

Không đóng gói hai loại cuối vào artifact phát hành.

Quy trình gợi ý:

~~~text
Build JAR
   |
   v
Resolve release signing identity
   |
   v
Inject short-lived secret into signing job
   |
   v
keytool/jarsigner reads secret from env or file
   |
   v
Sign JAR and create timestamp
   |
   v
Verify signature with strict mode
   |
   v
Publish signed artifact
   |
   v
Expire secret and clean temporary files
~~~

Checklist cho CI:

- Chỉ cấp secret ở job ký, không cấp cho job compile/test không cần quyền ký.
- Dùng protected branch, environment approval hoặc policy phát hành của nền tảng.
- Không in command có giá trị secret ra log.
- Không bật trace shell hoặc debug environment trong job chứa secret.
- Không lưu secret vào cache, artifact, workspace lâu dài hoặc file report.
- Dùng file secret có quyền đọc giới hạn hoặc env được cấp theo phạm vi job.
- Xác minh chữ ký ngay sau khi ký.
- Chỉ publish artifact đã xác minh.
- Thu hồi hoặc rotate secret khi runner bị xâm nhập hoặc log có thể đã lộ bí mật.

Không dùng biến **ARG** hoặc **ENV** trong Dockerfile để đóng gói password ký vào image. Không đưa keystore production vào image build hoặc image runtime. Nếu ký trong container, mount secret tạm từ hệ thống quản lý bí mật và giới hạn quyền của user trong container.

## 11. Lỗi thường gặp khi truyền password

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Password xuất hiện trong log CI | Secret được truyền dưới dạng literal hoặc lệnh bị echo | Dùng **:env**/**:file**, tắt trace và không in giá trị |
| **-storepass:env** báo không tìm thấy mật khẩu | Tên biến không tồn tại trong environment của tiến trình | Kiểm tra tên biến và phạm vi secret injection, không in giá trị |
| **-storepass:file** không đọc được | Đường dẫn sai hoặc user chạy tool không có quyền đọc | Kiểm tra mount và ACL/quyền file |
| Mở được keystore nhưng không ký được | Store password đúng nhưng key password sai hoặc alias không có private key | Kiểm tra alias và cung cấp key password đúng |
| keytool hỏi key password dù đã nhập store password | Key entry dùng password khác hoặc provider không dùng store password để mở key | Nhập key password riêng hoặc kiểm tra provider/keystore type |
| jarsigner ký được nhưng verify báo warning | Certificate chain, timestamp, usage hoặc thuật toán có vấn đề | Đọc warning, kiểm tra trust chain và policy |
| **-verify** bị lỗi vì cố truyền password | Nhầm password ký với bước xác minh | Bỏ **-storepass**/**-keypass** khỏi lệnh verify |
| PKCS12 không chấp nhận key password riêng | Provider hoặc công cụ đích yêu cầu storepass và keypass giống nhau | Kiểm tra tương thích và thống nhất password nếu cần |
| Job CI bị treo ở prompt | Password bị bỏ trống trong job không có terminal | Cấp secret bằng env/file hoặc dùng protected authentication path |
| Importkeystore thất bại với alias nguồn | Source key password khác source store password | Cung cấp **-srckeypass** riêng đúng cách |
| Lệnh đổi password lộ secret mới | Đặt password mới trực tiếp trong **-new** hoặc script | Dùng prompt tương tác; xác minh tùy chọn của đúng JDK trước khi tự động hóa |

## 12. Quy trình thực hành hoàn chỉnh

Một quy trình an toàn cho phát hành nội bộ có thể triển khai theo các bước sau.

### Bước 1: Tạo keystore trong môi trường được kiểm soát

Dùng prompt tương tác hoặc secret manager. Chỉ định rõ định dạng và alias:

~~~sh
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore release.p12
~~~

Không tạo keystore production trong thư mục source hoặc đưa password vào command.

### Bước 2: Kiểm tra alias và certificate

~~~sh
keytool -list -v \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:env SIGNING_STOREPASS
~~~

Xác nhận alias là key entry, certificate chain đúng và certificate còn thời hạn. Lưu fingerprint certificate theo quy trình phát hành để người nhận có thể đối chiếu qua kênh tin cậy.

### Bước 3: Ký artifact bằng secret được cấp cho job

~~~sh
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -storepass:env SIGNING_STOREPASS \
  -keypass:env SIGNING_KEYPASS \
  -tsa https://tsa.example.org \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

Dùng URL TSA thật đã được phê duyệt. Không cho các job không liên quan truy cập biến môi trường hoặc file secret.

### Bước 4: Xác minh bằng strict mode

~~~sh
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Đọc cảnh báo về unsigned entries, certificate, timestamp và thuật toán. Không chỉ kiểm tra chuỗi jar verified; cần xác minh danh tính signer theo trust policy.

### Bước 5: Publish và thu hồi secret tạm

Chỉ phát hành file app-signed.jar sau khi kiểm tra thành công. Thu hồi secret tạm, dọn file secret và giữ lại audit record không chứa password hoặc private key.

## 13. Checklist bảo vệ mật khẩu

- [ ] Phân biệt store password với private key password.
- [ ] Dùng PKCS12 làm mặc định trừ khi có yêu cầu tương thích hoặc provider cụ thể.
- [ ] Ưu tiên prompt khi thao tác thủ công.
- [ ] Dùng **-storepass:env** hoặc **-storepass:file** khi automation cần secret không tương tác.
- [ ] Dùng **-keypass:env** hoặc **-keypass:file** khi private key có password riêng.
- [ ] Không đặt mật khẩu literal trong command line, shell history hoặc script.
- [ ] Không đưa secret vào Git, Docker image, build artifact hoặc log.
- [ ] Hạn chế quyền đọc environment/file secret theo job và service account.
- [ ] Kiểm tra quy tắc storepass/keypass của PKCS12 provider và công cụ đích.
- [ ] Khi importkeystore, phân biệt password nguồn, password đích và password key entry.
- [ ] Khi đổi password, dùng prompt và thử khôi phục trên bản sao keystore trước.
- [ ] Dùng HSM/protected authentication path khi tổ chức yêu cầu bảo vệ khóa phần cứng.
- [ ] Không truyền password khi chỉ chạy **jarsigner -verify**.
- [ ] Xác minh JAR với **-strict -verbose -certs** và đọc toàn bộ warning.
- [ ] Kiểm tra certificate chain, fingerprint, timestamp và thuật toán ký.
- [ ] Chỉ publish artifact sau khi chữ ký được xác minh.
- [ ] Có quy trình rotate/revoke secret và certificate khi nghi ngờ lộ lọt.

## 14. Tài liệu tham khảo

- [Java SE 26 — keytool Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): cú pháp **-storepass**, **-keypass**, modifier **:env**/**:file**, prompt, PKCS12, importkeystore và cảnh báo mật khẩu.
- [Java SE 26 — jarsigner Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html): ký/xác minh JAR, **-storepass[:env|:file]**, **-keypass[:env|:file]**, timestamp và strict verification.
- [Java SE 26 — KeyStore API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html): mô hình keystore, entry và thao tác lưu/nạp.
- [Java SE 26 — JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): manifest và cấu trúc chữ ký trong JAR.
- [Java SE 26 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/26/security/): quản lý khóa, provider và chính sách bảo mật của JDK.

