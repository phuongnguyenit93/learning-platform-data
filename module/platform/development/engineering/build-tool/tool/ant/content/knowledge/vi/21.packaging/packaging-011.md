# Ký JAR và kiểm tra chữ ký bằng `signjar` và `verifyjar`

Một file JAR có thể chứa mã bytecode, tài nguyên và thư viện Java. Khi phát hành JAR cho người khác, cần có cách để người nhận kiểm tra nội dung có bị thay đổi sau khi nhà phát hành ký hay không và biết chứng thư nào đã ký artifact. Java cung cấp công cụ `jarsigner`; Apache Ant tích hợp công cụ này qua hai task `<signjar>` và `<verifyjar>`.

Ký JAR tạo chữ ký số dựa trên nội dung archive và khóa riêng của người ký. Chữ ký cho phép kiểm tra tính toàn vẹn của các entry được ký và xác định chứng thư ký. Việc kiểm tra chữ ký không tự động chứng minh nhà phát hành đáng tin cậy: người nhận còn phải tin cậy chứng thư hoặc chuỗi chứng thư đó.

Luồng phát hành thông thường:

```text
Compile và đóng gói JAR
          |
          v
    JAR chưa ký
          |
          v
      <signjar>
          |
          v
       JAR đã ký
          |
          v
     <verifyjar>
          |
          v
  Đưa JAR đã xác minh vào gói phát hành
```

Điểm quan trọng là phải hoàn tất mọi thay đổi đối với JAR trước khi ký. Nếu thêm, xóa hoặc sửa entry sau khi ký, chữ ký có thể không còn hợp lệ.

## 1. Chữ ký số của JAR hoạt động như thế nào?

JAR là archive theo định dạng ZIP. Khi ký, `jarsigner` tạo các file chữ ký trong thư mục `META-INF`, thường gồm:

| File | Vai trò |
|---|---|
| `META-INF/MANIFEST.MF` | Manifest chứa metadata và digest của các entry |
| `META-INF/<SIG>.SF` | File chữ ký chứa digest của manifest hoặc các section trong manifest |
| `META-INF/<SIG>.RSA`, `.DSA` hoặc `.EC` | Signature block chứa chữ ký số và thông tin chứng thư tương ứng |

Tên `<SIG>` được tạo từ alias hoặc tên chữ ký đã cấu hình, thường được chuẩn hóa thành chữ hoa và bị giới hạn theo quy tắc của công cụ ký. Thuật toán digest tính giá trị băm của dữ liệu; thuật toán chữ ký dùng khóa riêng để ký dữ liệu digest. Khi xác minh, công cụ dùng khóa công khai trong chứng thư để kiểm tra chữ ký và tính lại digest của các entry.

Vì chữ ký gắn với nội dung, không nên chỉnh sửa JAR sau khi ký. Nếu cần thay đổi resource, manifest, class hoặc dependency được nhúng, hãy tạo lại JAR từ đầu rồi ký lại. Chỉ đổi tên file JAR ở bên ngoài archive không làm thay đổi các entry bên trong, nhưng việc đóng gói lại hoặc chỉnh sửa nội dung archive có thể làm chữ ký mất hiệu lực.

## 2. Chuẩn bị keystore và key alias

`<signjar>` cần một private key để ký. Private key được lưu trong keystore dưới một alias. Keystore cũng chứa certificate tương ứng để người nhận có thể kiểm tra public key và danh tính được khai báo trong certificate.

Với môi trường phát triển hoặc kiểm thử nội bộ, có thể tạo key pair tự ký bằng `keytool` của JDK:

```shell
keytool -genkeypair \
  -alias release-key \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 825 \
  -storetype PKCS12 \
  -keystore release-signing.p12 \
  -dname "CN=Example Engineering, OU=Release, O=Example, C=VN"
```

`keytool` sẽ yêu cầu nhập mật khẩu keystore và mật khẩu private key nếu cần. Không đưa mật khẩu thật vào lệnh, source code, `build.xml`, file properties được commit hoặc log CI. File `release-signing.p12` chứa private key nên phải được bảo vệ như một secret. Không đặt nó trong thư mục `src`, `lib` hoặc thư mục staging sẽ được đóng gói vào distribution.

Các khái niệm cần phân biệt:

- **Keystore:** file hoặc kho chứa private key và certificate của người ký.
- **Alias:** tên entry chứa key pair mà task sẽ sử dụng, ví dụ `release-key`.
- **Store password (`storepass`):** mật khẩu bảo vệ keystore.
- **Key password (`keypass`):** mật khẩu bảo vệ private key entry; có thể khác store password.
- **Certificate:** phần chứa public key và thông tin định danh của chủ thể ký.
- **Truststore:** kho chứa các certificate hoặc CA mà bên xác minh tin cậy. Nó phục vụ quyết định trust, khác với keystore dùng để giữ private key.

Một certificate tự ký có thể dùng để kiểm thử quy trình ký và phát hiện nội dung bị thay đổi. Với bản phát hành cho người dùng bên ngoài, nên dùng certificate được cấp bởi CA hoặc cơ chế ký được tổ chức và khách hàng chấp nhận. Người nhận phải có cơ sở tin cậy đối với certificate; nếu không, họ có thể xác minh được chữ ký về mặt mật mã nhưng vẫn nhận cảnh báo rằng signer chưa được tin cậy.

## 3. Ký một JAR bằng `<signjar>`

Task `<signjar>` gọi `jarsigner` của JDK để ký JAR. Thuộc tính `jar` chỉ định file nguồn; `alias` chọn key entry; `keystore` và `storetype` xác định nơi lưu key; `storepass` cung cấp mật khẩu keystore. Có thể chỉ định `signedjar` để ghi kết quả sang file khác và giữ nguyên JAR chưa ký.

```xml
<project name="signed-application" default="sign">
    <property file="version.properties"/>
    <property name="build.dir" location="build"/>
    <property name="unsigned.jar"
              location="${build.dir}/libs/${app.name}-${app.version}.jar"/>
    <property name="signed.jar"
              location="${build.dir}/signed/${app.name}-${app.version}.jar"/>
    <property name="signing.keystore" location="release-signing.p12"/>
    <property name="signing.alias" value="release-key"/>

    <target name="sign" depends="jar">
        <!-- Nạp biến môi trường của máy chạy Ant thành property env.*. -->
        <property environment="env"/>
        <mkdir dir="${build.dir}/signed"/>

        <signjar jar="${unsigned.jar}"
                 signedjar="${signed.jar}"
                 keystore="${signing.keystore}"
                 storetype="PKCS12"
                 alias="${signing.alias}"
                 storepass="${env.RELEASE_STOREPASS}"
                 keypass="${env.RELEASE_KEYPASS}"
                 digestalg="SHA-256"
                 sigalg="SHA256withRSA"
                 verbose="true"/>
    </target>
</project>
```

Trong ví dụ, `RELEASE_STOREPASS` và `RELEASE_KEYPASS` phải được cung cấp bởi môi trường chạy build hoặc secret store của CI. `property environment="env"` nhập environment variable vào Ant dưới dạng `${env.TEN_BIEN}`. Nếu dùng key password giống store password, có thể bỏ `keypass` để `jarsigner` sử dụng cách xử lý mặc định phù hợp với keystore.

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `jar` | JAR nguồn cần ký |
| `signedjar` | Đường dẫn JAR đầu ra đã ký; chỉ dùng khi có `jar` |
| `alias` | Alias của private key dùng để ký |
| `keystore` | Đường dẫn keystore |
| `storetype` | Loại keystore, ví dụ `PKCS12` hoặc `JKS` |
| `storepass` | Mật khẩu keystore |
| `keypass` | Mật khẩu private key nếu khác store password |
| `sigfile` | Tên cơ sở cho file `.SF` và signature block |
| `digestalg` | Thuật toán digest, ví dụ `SHA-256` |
| `sigalg` | Thuật toán chữ ký, ví dụ `SHA256withRSA` |
| `tsaurl` | URL của dịch vụ timestamp authority |
| `verbose` | Hiển thị chi tiết quá trình ký |
| `strict` | Bật kiểm tra nghiêm ngặt; có từ Ant 1.9.1 |

Nếu không chỉ định `signedjar` hoặc `destDir`, Ant ký trực tiếp file nguồn. Với release build, tạo một file đầu ra riêng thường dễ kiểm soát hơn: giữ lại JAR chưa ký để so sánh hoặc ký lại, đồng thời chỉ đưa JAR đã ký vào distribution.

### Ký nhiều JAR

Có thể dùng fileset để ký một nhóm JAR. `destDir` ghi các JAR đã ký vào thư mục đích:

```xml
<signjar destDir="build/signed-libs"
         alias="${signing.alias}"
         keystore="${signing.keystore}"
         storetype="PKCS12"
         storepass="${env.RELEASE_STOREPASS}"
         verbose="true">
    <path>
        <fileset dir="build/lib">
            <include name="**/*.jar"/>
            <exclude name="*-sources.jar"/>
            <exclude name="*-javadoc.jar"/>
        </fileset>
    </path>
</signjar>
```

Khi dùng `destDir` cùng nested path/fileset, có thể thêm mapper để quyết định tên file đích. Cần bảo đảm hai JAR nguồn khác nhau không bị map thành cùng một tên trong thư mục đích. Không đưa JAR nguồn chưa hoàn chỉnh hoặc artifact không thuộc phạm vi phát hành vào fileset ký.

### Ký lại và thuộc tính `lazy`

Mặc định `lazy="false"`, nếu nguồn và đích là cùng một file, task sẽ thực hiện ký. Khi `lazy="true"` và file đích trùng file nguồn, Ant chỉ ký nếu chưa thấy chữ ký tương ứng với alias/sigfile. Cơ chế này giúp tránh ký lặp trong một số build lặp lại, nhưng không phải bằng chứng rằng nội dung hiện tại vẫn đúng với bản phát hành mong muốn.

Khi dùng `signedjar` riêng, Ant có quy tắc kiểm tra ngày sửa đổi giữa file nguồn và file đích để quyết định có cần tạo lại chữ ký. Nếu build cần luôn ký lại bất kể trạng thái file đích, có thể dùng `force="true"`. Hãy chọn `lazy` hoặc `force` theo quy trình build; không dùng chúng để thay thế bước xác minh.

## 4. Timestamp chữ ký

Certificate có thời hạn hiệu lực. Timestamp từ một timestamp authority (TSA) đáng tin cậy ghi nhận thời điểm chữ ký được tạo. Khi timestamp hợp lệ, người xác minh có thể xác định chữ ký đã được tạo trong thời gian certificate còn hiệu lực, kể cả khi certificate hết hạn sau đó.

Có thể chỉ định TSA bằng `tsaurl`:

```xml
<signjar jar="build/libs/application.jar"
         signedjar="build/signed/application.jar"
         alias="${signing.alias}"
         keystore="${signing.keystore}"
         storetype="PKCS12"
         storepass="${env.RELEASE_STOREPASS}"
         tsaurl="https://tsa.example.com/"
         digestalg="SHA-256"
         sigalg="SHA256withRSA"/>
```

URL ở đây chỉ là ví dụ minh họa; phải dùng TSA endpoint do CA hoặc tổ chức phát hành cung cấp. Máy build cần kết nối được tới TSA và certificate của TSA phải được xác minh theo chính sách tin cậy. Nếu không có timestamp, người nhận chủ yếu đánh giá certificate theo thời điểm xác minh hiện tại; sau khi certificate hết hạn, khả năng xác minh tin cậy có thể bị ảnh hưởng.

## 5. Kiểm tra chữ ký bằng `<verifyjar>`

Sau khi ký, dùng `<verifyjar>` để yêu cầu `jarsigner` xác minh JAR. Task kiểm tra chữ ký trên nội dung archive và certificate chain; nó không chỉ tìm xem trong `META-INF` có file `.SF` hay `.RSA` hay không.

```xml
<target name="verify-signed-jar" depends="sign">
    <verifyjar jar="${signed.jar}"
               alias="${signing.alias}"
               keystore="${signing.keystore}"
               certificates="true"
               verbose="true"/>
</target>
```

`alias` là thuộc tính bắt buộc của task. `certificates="true"` yêu cầu hiển thị thông tin certificate; `verbose="true"` hiển thị chi tiết từng entry khi xác minh. Có thể bật `strict="true"` để yêu cầu chế độ kiểm tra nghiêm ngặt (thuộc tính này có từ Ant 1.9.1):

```xml
<verifyjar jar="${signed.jar}"
           alias="${signing.alias}"
           keystore="${signing.keystore}"
           certificates="true"
           verbose="true"
           strict="true"/>
```

Nếu xác minh thất bại, Ant ném `BuildException` và target dừng, trừ khi lỗi được xử lý bằng cấu trúc điều khiển khác. Đây là lý do nên đặt `verifyjar` trước target tạo ZIP hoặc upload artifact: JAR không đạt xác minh sẽ không đi tiếp vào gói phát hành.

### Kiểm tra từ command line

Có thể dùng JDK `jarsigner` trực tiếp để quan sát kết quả độc lập với Ant:

```shell
jarsigner -verify -verbose -certs build/signed/application.jar
```

Lệnh này giúp kiểm tra từng entry và hiển thị certificate chain. Trong quy trình Ant, `<verifyjar>` là cách đưa cùng bước kiểm tra vào dependency graph của build, để lỗi chữ ký làm release target thất bại.

`verifyjar` có thuộc tính `storepass` tùy chọn, nhưng tài liệu Ant lưu ý `jarsigner` không đọc mật khẩu từ stdin trong chế độ verify; mật khẩu phải được truyền qua command line và có thể hiển thị cho người dùng khác trên cùng hệ thống. Chỉ cung cấp khi thực sự cần và phải đánh giá rủi ro lộ secret. Nhiều trường hợp xác minh chữ ký chỉ cần certificate công khai đã được nhúng trong JAR cùng cấu hình trust phù hợp, không cần mật khẩu private key.

## 6. Chữ ký hợp lệ và certificate đáng tin cậy

Kết quả xác minh cần được hiểu theo hai câu hỏi riêng:

1. **Tính toàn vẹn:** nội dung được ký có còn khớp digest và chữ ký số hay không?
2. **Danh tính và độ tin cậy:** certificate thuộc về ai, chuỗi certificate có dẫn tới CA mà bên nhận tin cậy không, và certificate có hợp lệ theo thời gian/chính sách không?

Một JAR tự ký có thể vượt qua kiểm tra mật mã về tính toàn vẹn nhưng vẫn bị cảnh báo là certificate tự ký hoặc chưa được tin cậy. Điều đó không có nghĩa nội dung bị sửa; nó có nghĩa người nhận chưa có cơ sở tin cậy độc lập để gắn public key với danh tính nhà phát hành.

Với ứng dụng nội bộ, tổ chức có thể phân phối certificate hoặc CA nội bộ qua một kênh tin cậy và cấu hình truststore cho máy xác minh. Với sản phẩm công khai, dùng certificate và quy trình phát hành được khách hàng hoặc nền tảng mục tiêu chấp nhận. Không nên coi việc `verifyjar` chạy không lỗi là thay thế cho chính sách quản lý certificate và trust của tổ chức.

Các cảnh báo thường gặp gồm:

- Certificate tự ký hoặc chuỗi certificate không dẫn tới CA tin cậy.
- Certificate đã hết hạn hoặc chưa tới thời điểm hiệu lực.
- Không có timestamp tin cậy để chứng minh chữ ký được tạo trong thời gian certificate còn hiệu lực.
- Thuật toán chữ ký hoặc digest đã yếu/không còn được JDK cho phép.
- Một số entry không được ký hoặc có nội dung thay đổi sau khi ký.

`strict="true"` làm chế độ kiểm tra nghiêm ngặt hơn và có thể biến một số cảnh báo thành lỗi build. Vì vậy, hãy dùng certificate chain và timestamp phù hợp trước khi bật strict cho release pipeline. Với certificate tự ký trong bài tập, có thể cần quan sát cảnh báo và cấu hình trust riêng thay vì mặc định coi đó là một bản phát hành công khai đã được tin cậy.

## 7. Tích hợp ký và xác minh vào target phát hành

Một release target nên tạo JAR, ký JAR, xác minh JAR rồi mới đóng gói distribution. Ví dụ:

```xml
<project name="release-build" default="release">
    <property file="version.properties"/>
    <property environment="env"/>

    <property name="build.dir" location="build"/>
    <property name="dist.dir" location="build/distribution"/>
    <property name="unsigned.jar"
              location="${build.dir}/libs/${app.name}-${app.version}.jar"/>
    <property name="signed.dir" location="${build.dir}/signed"/>
    <property name="signed.jar"
              location="${signed.dir}/${app.name}-${app.version}.jar"/>
    <property name="signing.keystore" location="release-signing.p12"/>
    <property name="signing.alias" value="release-key"/>

    <target name="sign" depends="jar">
        <mkdir dir="${signed.dir}"/>
        <signjar jar="${unsigned.jar}"
                 signedjar="${signed.jar}"
                 keystore="${signing.keystore}"
                 storetype="PKCS12"
                 alias="${signing.alias}"
                 storepass="${env.RELEASE_STOREPASS}"
                 keypass="${env.RELEASE_KEYPASS}"
                 digestalg="SHA-256"
                 sigalg="SHA256withRSA"
                 verbose="true"/>
    </target>

    <target name="verify" depends="sign">
        <verifyjar jar="${signed.jar}"
                   alias="${signing.alias}"
                   keystore="${signing.keystore}"
                   certificates="true"
                   verbose="true"
                   strict="true"/>
    </target>

    <target name="release" depends="verify">
        <mkdir dir="${dist.dir}"/>
        <zip destfile="${dist.dir}/${app.name}-${app.version}.zip">
            <fileset dir="${build.dir}/distribution-stage">
                <include name="README.md"/>
                <include name="LICENSE"/>
                <include name="RELEASE-NOTES.md"/>
                <include name="config/**"/>
            </fileset>
            <zipfileset file="${signed.jar}"
                        fullpath="${app.name}-${app.version}.jar"/>
        </zip>
    </target>
</project>
```

Trong ví dụ, target `release` phụ thuộc vào `verify`, vì vậy Ant chỉ tạo ZIP khi ký và xác minh đều hoàn tất thành công. `zipfileset` đưa đúng JAR đã ký vào archive. Không dùng lại `unsigned.jar` trong distribution và không chạy task chỉnh sửa nội dung JAR sau bước verify.

Nếu phát hành nhiều JAR, có thể dùng fileset với `<signjar>` và `<verifyjar>`, hoặc lặp qua một path chung. Cần giữ nhất quán danh sách JAR được ký, danh sách được xác minh và danh sách được đóng gói; tránh trường hợp một JAR chưa ký lọt vào ZIP.

## 8. Bảo vệ private key và mật khẩu trong CI

Private key là căn cứ để người khác xác nhận artifact được ký bởi chủ thể nắm giữ key. Nếu private key bị lộ, kẻ khác có thể ký artifact giả mạo mang cùng danh tính. Vì vậy:

- Không commit keystore hoặc mật khẩu vào Git.
- Lưu keystore trong secret storage hoặc signing service được giới hạn quyền truy cập.
- Chỉ job phát hành đã được bảo vệ mới được đọc private key.
- Dùng environment variables hoặc cơ chế secret injection của CI để cung cấp mật khẩu cho Ant; không echo giá trị ra log.
- Giới hạn quyền đọc file keystore và xóa bản tạm sau khi ký nếu CI yêu cầu.
- Tách certificate công khai dùng để xác minh khỏi private key dùng để ký.
- Có kế hoạch xoay vòng, thu hồi và thay certificate khi key bị lộ hoặc certificate hết hạn.

Ant `<signjar>` không đưa `storepass` vào đối số `-storepass` của command line mà gửi mật khẩu khi `jarsigner` yêu cầu. Tuy vậy, mật khẩu vẫn đi qua tiến trình build và property expansion; không nên coi `build.xml` hay log verbose là nơi lưu secret. Riêng `verifyjar`, nếu truyền `storepass`, tài liệu cảnh báo mật khẩu có thể xuất hiện trên command line và bị người dùng khác trên cùng máy quan sát. Hạn chế truyền password trong verify và tránh chạy release signing trên máy dùng chung không được bảo vệ.

## 9. Những lỗi thường gặp

1. **Không tìm thấy alias.** Kiểm tra alias có tồn tại trong keystore và entry đó chứa private key, không chỉ là trusted certificate entry.
2. **Sai mật khẩu keystore hoặc key.** Phân biệt `storepass` và `keypass`; nếu hai mật khẩu khác nhau, truyền đúng từng giá trị.
3. **Không tìm thấy keystore.** Dùng đường dẫn chính xác, kiểm tra working directory của Ant và quyền đọc file.
4. **Không tìm thấy `jarsigner`.** Ant sử dụng executable từ JDK đang chạy Ant theo mặc định. Kiểm tra `JAVA_HOME`, `PATH` và phiên bản JDK; có thể chỉ định `executable` nếu cần dùng binary cụ thể.
5. **JAR đã ký nhưng verify báo digest mismatch.** Có thể archive bị chỉnh sửa sau khi ký, file bị hỏng khi truyền tải hoặc một công cụ đóng gói đã thay đổi entry. Tạo lại JAR từ nguồn rồi ký lại.
6. **Certificate tự ký bị cảnh báo.** Kiểm tra certificate và truststore. Chữ ký có thể đúng về mặt mật mã nhưng signer chưa được bên xác minh tin cậy.
7. **Strict verification thất bại vì warning.** Đọc đầy đủ output của `jarsigner`, xử lý certificate chain, timestamp hoặc thuật toán theo chính sách. Không tắt strict chỉ để làm build xanh nếu cảnh báo chưa được hiểu.
8. **JAR không còn hợp lệ sau khi ký.** Di chuyển thao tác thêm manifest, nén lại hoặc sửa nội dung trước task `signjar`; sau đó chạy `verifyjar` trên đúng file sẽ phát hành.
9. **Ký nhầm JAR trong thư mục.** Thu hẹp fileset bằng include/exclude và dùng `signedjar` hoặc `destDir` để phân biệt đầu vào/đầu ra.
10. **Timestamp authority không truy cập được.** Kiểm tra URL TSA, mạng, proxy và certificate của TSA. Nếu release policy yêu cầu timestamp, coi lỗi timestamp là lỗi phát hành.

## 10. Quy trình thực hành

1. Tạo hoặc nhận keystore chứa certificate và private key của signer.
2. Kiểm tra alias, loại keystore và quyền truy cập trước khi chạy release build.
3. Biên dịch và đóng gói JAR hoàn chỉnh, bao gồm manifest và mọi resource.
4. Dùng `<signjar>` ký JAR; lưu kết quả vào đường dẫn riêng nếu cần giữ bản chưa ký.
5. Dùng `<verifyjar>` xác minh chính xác file đầu ra sẽ phát hành.
6. Kiểm tra certificate, timestamp và warning theo chính sách trust của người nhận.
7. Chỉ sau khi verify thành công mới đưa JAR đã ký vào ZIP, repository hoặc hệ thống phân phối.
8. Bảo vệ private key và lưu metadata phát hành đủ để truy xuất certificate, alias, version và build tương ứng.

## Tài liệu tham khảo

- [Apache Ant Manual — SignJar Task](https://ant.apache.org/manual/Tasks/signjar.html): tham số ký JAR, keystore, alias, timestamp và chế độ ký nhiều file.
- [Apache Ant Manual — VerifyJar Task](https://ant.apache.org/manual/Tasks/verifyjar.html): tham số xác minh JAR, certificate, strict mode và các lưu ý về mật khẩu.
- [Oracle JDK — jarsigner Tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html): cách ký và xác minh JAR từ command line.
- [Oracle JDK — keytool Tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): tạo và quản lý key pair, certificate và keystore.
