# Kiểm tra điều kiện phát hành và xác minh gói sau khi phân phối

Một build Ant hoàn tất không đồng nghĩa gói phát hành đã sẵn sàng để đưa cho người dùng hoặc triển khai lên môi trường thật. Build có thể biên dịch thành công nhưng thiếu tài liệu, sai phiên bản, thiếu dependency runtime, chứa tệp tạm, bị hỏng khi sao chép hoặc không còn giống artifact đã được kiểm thử.

Quy trình phát hành cần có hai nhóm kiểm tra rõ ràng:

- **Kiểm tra điều kiện trước phát hành:** xác nhận đầu vào, phiên bản, kiểm thử, cấu hình, nội dung và artifact đáp ứng tiêu chí đã thống nhất trước khi cho phép phân phối.
- **Xác minh sau phân phối:** kiểm tra gói ở vị trí nhận cuối cùng, xác nhận checksum, cấu trúc archive, metadata và khả năng sử dụng sau khi tải lên, sao chép hoặc chuyển qua kho artifact.

Apache Ant cung cấp các task như `available`, `fail`, `condition`, `checksum`, `unzip`, `jar`, `zip`, `copy` và `exec` để xây dựng các bước kiểm tra. Ant điều phối quy trình và dừng build khi điều kiện không đạt; các kiểm tra nghiệp vụ hoặc kiểm tra triển khai chuyên biệt có thể cần chương trình, test runner hoặc công cụ của hệ thống phát hành.

## 1. Phân biệt build thành công, release-ready và distributed

Ba trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Bằng chứng cần có |
|---|---|---|
| Build successful | Các target build đã hoàn thành | Log Ant và mã thoát thành công |
| Release-ready | Artifact đáp ứng tiêu chí phát hành | Test, metadata, dependency, nội dung và kiểm tra chất lượng đạt yêu cầu |
| Distributed and verified | Gói đã được chuyển tới vị trí nhận và bản nhận đã được xác minh | Checksum khớp, archive đọc được, nội dung đúng và kiểm tra sau phân phối đạt |

Ví dụ, target `package` tạo ra `application-1.4.0.zip`. Nếu file đó được tạo thành công, Ant chỉ chứng minh bước đóng gói đã hoàn tất. Nó chưa chứng minh ZIP có đủ file, checksum không đổi sau khi upload, hoặc ứng dụng có thể chạy trên môi trường đích.

Một quy trình phát hành có thể biểu diễn như sau:

~~~text
Mã nguồn + cấu hình + dependency
              |
              v
      Kiểm tra đầu vào
              |
              v
        Compile + Test
              |
              v
     Kiểm tra release gate
              |
              v
       Tạo artifact
              |
              v
   Xác minh artifact cục bộ
              |
              v
     Phân phối / upload
              |
              v
 Tải hoặc đọc lại bản đã phân phối
              |
              v
  Xác minh checksum + cấu trúc
              |
              v
      Smoke test / nghiệm thu
              |
              v
        Release verified
~~~

Không nên gộp mọi bước vào một target lớn không có ranh giới. Khi một bước thất bại, target riêng giúp xác định rõ lỗi xuất hiện ở giai đoạn nào và giữ lại log phù hợp.

## 2. Xác định release gate trước khi đóng gói

Release gate là tập hợp điều kiện phải đạt trước khi artifact được phép phát hành. Các điều kiện cần phù hợp với loại sản phẩm và chính sách của nhóm.

Một release gate thường kiểm tra:

- Mã phiên bản phát hành đã được cung cấp và đúng quy ước.
- Các thư mục nguồn, descriptor, cấu hình mẫu và dependency bắt buộc tồn tại.
- Build chạy bằng phiên bản JDK và Ant được hỗ trợ.
- Biên dịch và test bắt buộc hoàn tất thành công.
- Checkstyle hoặc static analysis bắt buộc đã đạt.
- Không có tệp bí mật, cấu hình môi trường cá nhân hoặc dữ liệu kiểm thử nhạy cảm trong gói.
- Artifact được tạo đúng tên, đúng loại và không rỗng.
- Các module và thư viện cần thiết có mặt.
- Metadata, manifest và tài liệu phát hành phù hợp với phiên bản.

Không phải dự án nào cũng cần mọi mục trên. Hãy xác định rõ điều kiện nào là bắt buộc, điều kiện nào chỉ tạo cảnh báo và ai có quyền phê duyệt ngoại lệ. Một điều kiện bắt buộc cần được biểu diễn bằng task làm build thất bại khi không đạt, thay vì chỉ in thông báo.

## 3. Kiểm tra tham số và đầu vào phát hành

### 3.1. Yêu cầu version rõ ràng

Không nên tạo artifact phát hành với tên chung như `application-latest.zip` hoặc một version mặc định không được kiểm soát. Hãy yêu cầu người gọi truyền version:

~~~xml
<target name="validate-release-version">
    <fail unless="release.version"
          message="Missing required property: release.version" />
</target>
~~~

Gọi Ant:

~~~text
ant -Drelease.version=1.4.0 release
~~~

Có thể kiểm tra version theo quy ước dự án bằng một bước validation riêng. Ví dụ, nếu tổ chức chấp nhận chuỗi version do pipeline tạo, hãy xác thực ở pipeline và truyền giá trị đã được kiểm tra vào Ant. Không ghép một chuỗi tùy ý vào tên đường dẫn hoặc lệnh hệ thống mà không kiểm tra ký tự được phép.

Ant property thông thường là bất biến. Vì vậy, hãy truyền user property từ dòng lệnh hoặc nạp cấu hình trước khi target sử dụng nó; không thiết kế build như thể property có thể thay đổi qua lại trong các target.

### 3.2. Kiểm tra các tệp bắt buộc

Task `available` kiểm tra một tệp hoặc thư mục tồn tại. Ví dụ:

~~~xml
<target name="validate-release-inputs">
    <available file="${basedir}/README.md"
               type="file"
               property="release.readme.present" />
    <available file="${basedir}/config/default.properties"
               type="file"
               property="release.config.present" />
    <available file="${basedir}/build/libs/application.jar"
               type="file"
               property="release.jar.present" />

    <fail unless="release.readme.present"
          message="Release input is missing: README.md" />
    <fail unless="release.config.present"
          message="Release input is missing: config/default.properties" />
    <fail unless="release.jar.present"
          message="Release input is missing: build/libs/application.jar" />
</target>
~~~

Đặt target này trước bước đóng gói:

~~~xml
<target name="package" depends="validate-release-inputs">
    <!-- Tạo gói phân phối -->
</target>
~~~

Nếu tệp có thể được tạo trong build, dependency của target cần bảo đảm nó được tạo trước khi kiểm tra. Không chạy validation quá sớm khi artifact đầu vào chưa tồn tại.

### 3.3. Kiểm tra thư mục và cấu hình

Có thể dùng `available type="dir"` để xác nhận thư mục staging hoặc cấu hình cần thiết tồn tại. Với cấu hình theo môi trường, hãy kiểm tra đúng profile được chọn và không lấy nhầm tệp local.

Không nên chỉ kiểm tra sự tồn tại của một tệp rồi coi nội dung hợp lệ. Ví dụ, `default.properties` có thể tồn tại nhưng thiếu khóa bắt buộc. Với dữ liệu cấu hình, hãy nạp property và xác thực từng giá trị cần thiết bằng `condition`, `fail` hoặc một validator chuyên biệt.

## 4. Kiểm tra kết quả compile, test và phân tích mã

Một artifact chỉ nên được đóng gói sau khi các bước kiểm tra bắt buộc đã hoàn tất. Có thể tạo target tổng hợp:

~~~xml
<target name="verify">
    <antcall target="compile" />
    <antcall target="test" />
    <antcall target="checkstyle" />
</target>

<target name="release" depends="verify">
    <antcall target="package" />
</target>
~~~

Ví dụ trên minh họa việc nhóm các bước vào luồng release. Trong dự án thực tế, ưu tiên dùng quan hệ `depends` trực tiếp giữa các target khi có thể, vì Ant quản lý dependency graph rõ ràng hơn và tránh gọi lặp target không cần thiết.

Có thể khai báo:

~~~xml
<target name="verify" depends="compile,test,checkstyle" />
<target name="package" depends="verify" />
<target name="release" depends="package" />
~~~

Nếu target test hoặc Checkstyle thất bại, Ant không thể hoàn tất chuỗi dependency thành công. Hãy bảo đảm target release của CI thực sự phụ thuộc vào các bước bắt buộc; một target package được gọi độc lập có thể bỏ qua các gate nếu dependency không được khai báo.

Với kiểm thử tích hợp, cần xác định môi trường và dữ liệu test tương ứng. Một unit test thành công không chứng minh package đã deploy đúng trên application server hoặc hoạt động với database thật.

## 5. Kiểm tra tên, kích thước và vị trí artifact

Sau khi tạo gói, kiểm tra artifact đã xuất hiện và có kích thước hợp lý:

~~~xml
<target name="validate-package-file">
    <available file="${dist.file}"
               type="file"
               property="release.package.present" />

    <fail unless="release.package.present"
          message="Release package was not created: ${dist.file}" />

    <length file="${dist.file}"
            property="release.package.bytes" />

    <condition property="release.package.nonempty">
        <not>
            <equals arg1="${release.package.bytes}" arg2="0" />
        </not>
    </condition>

    <fail unless="release.package.nonempty"
          message="Release package is empty: ${dist.file}" />
</target>
~~~

Task `length` có thể lưu kích thước tệp vào property. Nếu chỉ cần kiểm tra tệp không rỗng, có thể dùng điều kiện tương đương theo cách phù hợp với phiên bản Ant. Hãy nhớ property của Ant không thể ghi đè; dùng tên property riêng cho mỗi artifact và mỗi lần kiểm tra trong cùng một invocation.

Kiểm tra kích thước không chứng minh nội dung hợp lệ. Một ZIP có thể có kích thước lớn nhưng thiếu module, chứa tệp cũ hoặc không đọc được. Cần xác minh archive ở bước tiếp theo.

## 6. Kiểm tra cấu trúc và nội dung archive

### 6.1. Giải nén vào thư mục tạm để kiểm tra

Task `unzip` có thể giải nén artifact vào thư mục kiểm tra. Sau đó, dùng `available` để xác nhận các mục bắt buộc:

~~~xml
<property name="verify.dir"
          location="${basedir}/build/release-verification" />

<target name="verify-package-contents" depends="validate-package-file">
    <delete dir="${verify.dir}" />
    <mkdir dir="${verify.dir}" />

    <unzip src="${dist.file}" dest="${verify.dir}" />

    <available file="${verify.dir}/application.jar"
               type="file"
               property="package.app.present" />
    <available file="${verify.dir}/README.md"
               type="file"
               property="package.readme.present" />
    <available file="${verify.dir}/config/default.properties"
               type="file"
               property="package.config.present" />

    <fail unless="package.app.present"
          message="Package is missing application.jar" />
    <fail unless="package.readme.present"
          message="Package is missing README.md" />
    <fail unless="package.config.present"
          message="Package is missing config/default.properties" />
</target>
~~~

Đây là cách xác minh cấu trúc sau khi archive được đọc và giải nén. Nó phát hiện nhiều lỗi như đóng gói thiếu file, sai tên hoặc sai đường dẫn tương đối.

Chỉ giải nén artifact do pipeline của mình tạo hoặc đã được xác thực nguồn gốc vào thư mục kiểm tra riêng. Không dùng một thư mục có dữ liệu người dùng làm đích giải nén. Với gói nhận từ nguồn không tin cậy, cần kiểm tra an toàn archive và đường dẫn entry trước khi giải nén bằng công cụ phù hợp.

### 6.2. Kiểm tra manifest và metadata

Với JAR, có thể kiểm tra nội dung bằng:

~~~text
jar tf build/libs/application.jar
~~~

Với ZIP:

~~~text
jar tf dist/application-1.4.0.zip
~~~

Lệnh `jar tf` liệt kê các entry của archive. Có thể dùng `unzip -l` nếu môi trường có công cụ unzip. Hãy xác nhận:

- Manifest có mặt nếu định dạng và ứng dụng yêu cầu.
- Main-Class hoặc các thuộc tính manifest cần thiết được thiết lập đúng.
- Descriptor có đúng phiên bản schema.
- Tên module trong descriptor khớp archive thực tế.
- Không có tệp test, log, file tạm hoặc thư viện build bị đóng gói nhầm.
- Các tệp cấu hình được phát hành là cấu hình mẫu, không chứa secret hoặc endpoint riêng của môi trường.

### 6.3. Kiểm tra số lượng và danh sách file

Với sản phẩm có cấu trúc cố định, nên định nghĩa rõ danh sách file bắt buộc và tùy chọn. Nếu một module mới được thêm vào, cập nhật danh sách kiểm tra cùng thay đổi build.

Không nên chỉ kiểm tra số lượng entry của archive. Số lượng đúng vẫn có thể chứa sai file. Hãy kiểm tra đường dẫn và tên cụ thể, đồng thời kiểm tra nội dung metadata quan trọng.

## 7. Tạo checksum cho artifact phát hành

### 7.1. Tạo SHA-256 sau khi package

Checksum giúp phát hiện artifact bị thay đổi hoặc hỏng trong quá trình lưu trữ, sao chép và truyền tải.

Ant có task `checksum`. Ví dụ tạo digest SHA-256:

~~~xml
<target name="create-release-checksum" depends="validate-package-file">
    <checksum file="${dist.file}"
              algorithm="SHA-256"
              property="release.package.sha256" />

    <echo file="${dist.file}.sha256"
          message="${release.package.sha256}  ${dist.file}" />
</target>
~~~

Tệp sidecar có thể có dạng:

~~~text
<sha256-hex>  application-1.4.0.zip
~~~

Digest là giá trị thực do Ant tính từ artifact; không điền một giá trị minh họa cố định vào build file. Tên file trong sidecar cần khớp với tên artifact mà người nhận sẽ kiểm tra.

Checksum nên được tạo sau khi package hoàn tất và trước khi phân phối. Nếu artifact bị chỉnh sửa sau khi tạo checksum, sidecar không còn đại diện cho nội dung hiện tại.

### 7.2. So sánh checksum của bản gốc và bản đã sao chép

Để kiểm tra một bản sao tại thư mục nhận, tính digest riêng cho cả hai file:

~~~xml
<target name="verify-distribution-copy">
    <checksum file="${dist.file}"
              algorithm="SHA-256"
              property="source.package.sha256" />

    <checksum file="${received.file}"
              algorithm="SHA-256"
              property="received.package.sha256" />

    <condition property="distribution.copy.valid">
        <equals arg1="${source.package.sha256}"
                arg2="${received.package.sha256}" />
    </condition>

    <fail unless="distribution.copy.valid"
          message="Distributed package checksum does not match source package" />
</target>
~~~

Trước target này, cần bảo đảm `received.file` đã được tải hoặc sao chép vào đúng vị trí. Dùng tên property khác nhau cho hai digest vì Ant property không ghi đè giá trị đã thiết lập.

Nếu bản nhận nằm trên một máy khác, hãy tính checksum tại máy nhận hoặc trong job xác minh sau khi tải về. So sánh digest được tạo ở hai đầu giúp phát hiện hỏng dữ liệu trong quá trình truyền.

### 7.3. Checksum không thay thế chữ ký số

SHA-256 chứng minh hai tệp có cùng nội dung khi digest khớp, nhưng không tự chứng minh artifact đến từ nhà phát hành đáng tin cậy. Nếu người tấn công có thể thay cả artifact lẫn tệp checksum, hai tệp vẫn có thể khớp nhau.

Với yêu cầu xác thực nguồn gốc, dùng chữ ký số hoặc chữ ký artifact được quản lý bằng khóa tin cậy. Kiểm tra chữ ký cần xác minh certificate/key, chuỗi tin cậy và chính sách phát hành. Không lưu private key trong repository hoặc log build.

## 8. Xác minh gói sau khi phân phối

### 8.1. Kiểm tra ở vị trí nhận cuối cùng

Xác minh chỉ trên thư mục build cục bộ chưa đủ. Sau khi upload lên artifact repository, copy sang máy chủ hoặc tải xuống từ hệ thống phân phối, hãy kiểm tra đúng bản tại vị trí nhận.

Quy trình có thể gồm:

1. Xác định URL, artifact ID hoặc đường dẫn nhận.
2. Tải artifact về thư mục xác minh sạch.
3. Kiểm tra file tồn tại và kích thước khác 0.
4. Tính SHA-256 của bản nhận.
5. So sánh với digest đã được phát hành qua kênh tin cậy.
6. Mở archive và kiểm tra nội dung.
7. Chạy smoke test hoặc kiểm tra triển khai phù hợp.

Nếu dùng artifact repository, hãy xác minh đúng tọa độ, version, classifier và loại packaging. Không chỉ kiểm tra một URL chung có thể trỏ tới bản mới nhất.

### 8.2. Không ghi đè phiên bản đã phát hành

Artifact của một version phát hành nên bất biến. Nếu cần sửa nội dung, tạo version mới hoặc một bản phát hành được định danh rõ ràng theo chính sách của tổ chức.

Ghi đè `application-1.4.0.zip` sau khi đã phân phối khiến checksum, log, release notes và bản người dùng đang giữ không còn nhất quán. Nếu repository hỗ trợ immutable release hoặc retention policy, hãy bật chính sách tương ứng.

### 8.3. Kiểm tra lại metadata phát hành

Bản nhận cần có đúng metadata của bản đã được duyệt:

- Tên artifact và version.
- Commit hoặc revision nguồn nếu quy trình có ghi nhận.
- Build number hoặc mã pipeline.
- Phiên bản JDK và Ant.
- Checksum và chữ ký nếu có.
- Release notes và tài liệu đi kèm.
- Thời điểm phát hành và repository đích.

Có thể lưu thông tin này trong manifest phát hành riêng hoặc metadata của artifact repository. Không đưa secret, access token hoặc thông tin nội bộ không cần thiết vào metadata công khai.

## 9. Smoke test và kiểm tra sau phân phối

Checksum và cấu trúc archive xác nhận tính toàn vẹn và sự hiện diện của file, nhưng chưa chứng minh ứng dụng chạy đúng. Smoke test kiểm tra một tập hành vi tối thiểu sau khi gói được đặt vào môi trường gần với môi trường sử dụng.

Ví dụ với ứng dụng Java có entry point dòng lệnh:

~~~xml
<target name="smoke-test" depends="verify-package-contents">
    <java jar="${verify.dir}/application.jar"
          fork="true"
          timeout="60000"
          failonerror="true">
        <arg value="--version" />
    </java>
</target>
~~~

Ví dụ này giả định JAR hỗ trợ tham số `--version` và kết thúc với mã 0. Không phải mọi ứng dụng đều có giao diện dòng lệnh như vậy. Với web application, smoke test có thể gọi health endpoint; với EAR, cần triển khai lên application server tương thích và kiểm tra endpoint, EJB/JNDI hoặc các luồng tích hợp cần thiết.

Nếu smoke test cần đọc stdout để so sánh version, có thể chuyển output vào tệp hoặc property theo khả năng của task Java, sau đó kiểm tra kết quả bằng bước riêng. Đừng chỉ dựa vào việc tiến trình kết thúc với mã 0 nếu chương trình có thể báo version sai nhưng vẫn trả mã thành công.

### 9.1. Kiểm tra ứng dụng trên môi trường đích

Với ứng dụng triển khai trên application server, quy trình sau phân phối thường cần:

- Deploy đúng EAR/WAR vào server phiên bản đã xác định.
- Xác nhận server chấp nhận descriptor và khởi tạo module.
- Kiểm tra log khởi động không có lỗi nghiêm trọng.
- Kiểm tra datasource, JNDI, transaction, security và messaging.
- Gọi health endpoint hoặc chạy integration test tối thiểu.
- Xác nhận version đang chạy đúng với artifact vừa phân phối.

Ant có thể gọi script hoặc CLI của server bằng task `exec`, nhưng cú pháp và cơ chế xác thực phụ thuộc nhà cung cấp. Không đặt password quản trị trực tiếp trong build file; dùng secret store và quyền triển khai của CI.

### 9.2. Tách smoke test khỏi unit test

Unit test thường chạy trên mã nguồn hoặc class đã biên dịch trong workspace. Smoke test sau phân phối cần sử dụng chính artifact đã tạo hoặc bản đã tải về. Nếu smoke test vô tình dùng `build/classes` thay vì nội dung package, nó không kiểm tra được việc đóng gói thiếu file hoặc sai classpath.

Hãy cấu hình smoke test đọc từ thư mục đã giải nén hoặc triển khai đúng artifact đã nhận. Như vậy, test xác minh cả kết quả đóng gói lẫn hành vi tối thiểu của sản phẩm.

## 10. Tổ chức target release và verify trong build.xml

Một cấu trúc target có thể như sau:

~~~xml
<project name="release-example" default="release" basedir=".">

    <property name="release.version" value="1.4.0" />
    <property name="dist.dir" location="${basedir}/dist" />
    <property name="build.dir" location="${basedir}/build" />
    <property name="verify.dir" location="${build.dir}/release-verification" />

    <property name="dist.file"
              location="${dist.dir}/application-${release.version}.zip" />

    <target name="validate-release-version">
        <fail unless="release.version"
              message="Missing release.version" />
    </target>

    <target name="verify-prerequisites" depends="validate-release-version">
        <available file="${basedir}/README.md"
                   type="file"
                   property="readme.present" />
        <fail unless="readme.present"
              message="README.md is required for release" />
    </target>

    <target name="compile" depends="verify-prerequisites">
        <!-- Compile application -->
    </target>

    <target name="test" depends="compile">
        <!-- Run required tests -->
    </target>

    <target name="package" depends="test">
        <mkdir dir="${dist.dir}" />
        <zip destfile="${dist.file}">
            <fileset dir="${basedir}/build/distribution" />
            <fileset file="${basedir}/README.md" />
        </zip>
    </target>

    <target name="verify-package" depends="package">
        <available file="${dist.file}"
                   type="file"
                   property="package.present" />
        <fail unless="package.present"
              message="Release package was not created" />

        <delete dir="${verify.dir}" />
        <mkdir dir="${verify.dir}" />
        <unzip src="${dist.file}" dest="${verify.dir}" />

        <available file="${verify.dir}/README.md"
                   type="file"
                   property="package.readme.present" />
        <fail unless="package.readme.present"
              message="Package is missing README.md" />

        <checksum file="${dist.file}"
                  algorithm="SHA-256"
                  property="package.sha256" />
        <echo file="${dist.file}.sha256"
              message="${package.sha256}  application-${release.version}.zip" />
    </target>

    <target name="release" depends="verify-package">
        <echo message="Release package verified: ${dist.file}" />
    </target>

</project>
~~~

Đây là khung minh họa. Trong dự án thực tế:

- Bỏ giá trị default của `release.version` nếu quy trình yêu cầu version phải được truyền rõ ràng.
- Thay comment compile/test bằng target thật của dự án.
- Bảo đảm thư mục `build/distribution` chứa đúng nội dung staging.
- Kiểm tra thêm các file bắt buộc ngoài README.
- Thêm target xác minh bản đã upload/tải về; ví dụ trên mới xác minh artifact cục bộ.
- Cấu hình CI lưu log và báo cáo ngay cả khi một gate thất bại.

Một target `release` hoàn tất chỉ nên có nghĩa các gate đã khai báo trong build file thành công. Nếu chưa có bước upload và verify bản nhận, không nên gọi trạng thái đó là distributed-and-verified.

## 11. Dùng target riêng cho bước phân phối và bước xác minh bản nhận

Không phải hệ thống phân phối nào cũng có cùng giao diện. Có thể tách phần chuyển artifact thành một target và phần xác minh thành target khác:

~~~xml
<target name="publish-artifact" depends="verify-package">
    <!-- Gọi repository CLI hoặc upload task đã được dự án cấu hình -->
</target>

<target name="verify-received-artifact" depends="publish-artifact">
    <!-- Tải artifact về received.dir -->
    <!-- Tính checksum và so sánh với digest đã được phê duyệt -->
    <!-- Giải nén và kiểm tra nội dung bản nhận -->
</target>
~~~

Các comment là vị trí tích hợp công cụ thực tế, không phải task Ant có thể chạy nguyên trạng. Hãy dùng plugin, CLI hoặc API phù hợp với artifact repository của tổ chức.

Nếu việc upload và tải xuống là hai job riêng, lưu digest và metadata phát hành thành artifact của job đầu, rồi truyền chúng cho job xác minh. Job xác minh cần tải đúng version vừa phát hành, không dùng một alias có thể thay đổi theo thời gian.

Ví dụ target so sánh checksum khi bản nhận đã có tại chỗ:

~~~xml
<target name="compare-received-package">
    <checksum file="${dist.file}"
              algorithm="SHA-256"
              property="source.sha256" />
    <checksum file="${received.file}"
              algorithm="SHA-256"
              property="received.sha256" />

    <condition property="received.matches">
        <equals arg1="${source.sha256}"
                arg2="${received.sha256}" />
    </condition>

    <fail unless="received.matches"
          message="Received artifact differs from released artifact" />
</target>
~~~

Trong pipeline thực tế, `received.file` cần được gán tới file vừa tải về. Nếu nguồn phân phối là một máy khác, phép so sánh phải được thực hiện sau khi download hoàn tất.

## 12. Lưu bằng chứng phát hành

Một release có thể cần bằng chứng để truy vết khi có sự cố. Tùy quy trình, lưu:

- Log của Ant cho các target verify, package và release.
- Kết quả compile, test và static analysis.
- Checksum SHA-256 của artifact.
- Chữ ký số và kết quả xác minh chữ ký nếu có.
- Danh sách file trong archive hoặc báo cáo kiểm tra nội dung.
- Version, commit, build number và toolchain.
- Kết quả smoke test hoặc deployment verification.
- Đường dẫn artifact repository và thời điểm phân phối.

Không nên chỉ lưu log thành công rồi xóa log thất bại. Log lỗi thường là bằng chứng quan trọng nhất để xác định release gate nào đã chặn phát hành.

Nếu artifact được phân phối cho nhiều nơi, nên ghi nhận checksum của từng bản nhận. Một bản tải xuống lỗi không nên làm mất bản gốc đã được xác minh; có thể tải lại và xác minh lần nữa theo chính sách retry của hệ thống.

## 13. An toàn khi kiểm tra và phân phối

Artifact có thể chứa mã thực thi, script, cấu hình và metadata. Trước khi phát hành:

- Không đưa password, token, private key hoặc file credential vào archive.
- Không đóng gói cấu hình local như endpoint development hoặc đường dẫn workspace.
- Không đưa log chứa dữ liệu nhạy cảm vào gói.
- Kiểm tra dependency và license theo chính sách của tổ chức.
- Hạn chế quyền ghi vào thư mục artifact đã phát hành.
- Không ghi đè artifact version đã phân phối.
- Xác minh chữ ký khi yêu cầu tính xác thực nguồn gốc.
- Chỉ giải nén gói tin cậy vào thư mục kiểm tra được kiểm soát.

Checksum bảo vệ tính toàn vẹn khi so sánh với digest tin cậy; chữ ký số hoặc cơ chế provenance mới giúp xác minh nguồn gốc theo mô hình khóa và trust của tổ chức. Không coi hai cơ chế này là thay thế cho nhau.

## 14. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Build thành công nhưng không có file phát hành | Target package chưa được gọi hoặc output path sai | Kiểm tra dependency target và dist.file |
| Artifact rỗng hoặc nhỏ bất thường | Staging không có nội dung hoặc fileset sai | Kiểm tra thư mục staging và danh sách file |
| ZIP tạo được nhưng thiếu module | Include trong fileset không khớp tên hoặc module chưa build | Kiểm tra nội dung archive và target dependency |
| Checksum thay đổi sau upload | Tệp bị hỏng, bị thay thế hoặc repository lưu sai artifact | Tải lại đúng version và so sánh digest |
| Checksum hai đầu khớp nhưng nguồn gốc chưa rõ | Digest được lấy từ cùng nguồn không tin cậy | Xác minh chữ ký hoặc lấy digest qua kênh tin cậy |
| Smoke test chạy được trên workspace nhưng package lỗi | Test dùng classpath build thay vì artifact đã giải nén | Chạy test từ bản package hoặc bản nhận |
| Artifact có version sai | Property version mặc định hoặc pipeline truyền nhầm | Yêu cầu version rõ ràng và kiểm tra metadata |
| Bản phát hành bị ghi đè | Repository hoặc script cho phép upload cùng tên/version | Dùng version bất biến và chính sách không overwrite |
| Báo cáo không còn sau khi job thất bại | Pipeline chỉ lưu artifact khi thành công | Cấu hình lưu log/báo cáo cả khi thất bại |
| Archive có file thừa hoặc secret | Fileset đóng gói quá rộng hoặc staging chưa được làm sạch | Dùng include rõ ràng, dọn staging và kiểm tra nội dung |
| Ant báo thiếu file khi validation chạy | Target kiểm tra chạy trước target tạo file | Sắp xếp dependency để build đầu vào trước rồi mới kiểm tra |
| Bản nhận không đúng artifact vừa build | Dùng URL alias hoặc version không cố định | Tải bằng tọa độ/version chính xác và so sánh checksum |

## 15. Checklist release gate và xác minh sau phân phối

**Trước phát hành**

- [ ] Version phát hành được cung cấp và xác thực.
- [ ] JDK, Ant và dependency đúng phiên bản đã quy định.
- [ ] Các tệp cấu hình và tài liệu bắt buộc tồn tại.
- [ ] Compile hoàn tất thành công.
- [ ] Unit test và các test bắt buộc đạt.
- [ ] Checkstyle/static analysis đạt theo chính sách.
- [ ] Không có secret hoặc file local trong staging.
- [ ] Artifact có tên, loại và kích thước hợp lệ.
- [ ] Archive chứa đủ module, resource và metadata.
- [ ] Checksum được tạo và lưu cùng metadata phát hành.

**Sau phân phối**

- [ ] Đã lấy đúng artifact version từ vị trí nhận.
- [ ] Bản nhận tồn tại và không rỗng.
- [ ] SHA-256 của bản nhận khớp digest đã được phê duyệt.
- [ ] Archive mở được và cấu trúc đúng.
- [ ] Manifest, descriptor và danh sách module đúng.
- [ ] Chữ ký số đã được xác minh nếu quy trình yêu cầu.
- [ ] Smoke test hoặc deployment verification đạt.
- [ ] Log, checksum và metadata được lưu để truy vết.
- [ ] Artifact version đã phát hành không bị ghi đè.

## 16. Nguyên tắc duy trì

- Tách rõ build successful, release-ready và distributed-and-verified.
- Đặt release gate trước bước package hoặc publish.
- Dùng `available`, `condition` và `fail` để biến điều kiện bắt buộc thành kiểm tra thực thi được.
- Kiểm tra cấu trúc archive bằng cách đọc hoặc giải nén vào thư mục xác minh riêng.
- Tạo checksum sau khi artifact hoàn tất và so sánh lại trên bản nhận.
- Hiểu rằng checksum xác nhận tính toàn vẹn, còn chữ ký xác nhận nguồn gốc theo trust model.
- Chạy smoke test trên artifact đã đóng gói hoặc bản đã tải về.
- Dùng version bất biến và tránh ghi đè bản phát hành.
- Lưu log, checksum, metadata và kết quả xác minh cho mỗi release.
- Giữ bí mật ngoài artifact, log và build file.

Một quy trình phát hành đáng tin cậy không dừng ở thời điểm Ant tạo được file ZIP hoặc EAR. Artifact cần vượt qua các release gate, được kiểm tra nội dung, được phân phối theo version xác định và được xác minh lại tại nơi nhận. Khi những bước này được biểu diễn thành target rõ ràng, nhóm có bằng chứng tốt hơn để biết chính xác gói nào đã được phát hành và gói đó có còn nguyên vẹn sau khi phân phối hay không.

