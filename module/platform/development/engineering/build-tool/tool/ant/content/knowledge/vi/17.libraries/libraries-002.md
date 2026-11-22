# Quản lý thư viện thủ công trong `lib` và mô tả nguồn gốc phiên bản

Một dự án Java thường cần thư viện bên ngoài để làm việc với cơ sở dữ liệu, xử lý JSON, ghi log hoặc cung cấp các chức năng dùng chung. Với Apache Ant, dự án có thể quản lý những JAR này trực tiếp trong thư mục `lib` và khai báo chúng trong classpath của các task biên dịch, kiểm thử hoặc chạy ứng dụng.

Quản lý thủ công có nghĩa là nhóm phát triển tự tải, lựa chọn, lưu trữ và cập nhật từng thư viện. Vì buildfile không tự giải quyết dependency và dependency bắc cầu, dự án cần ghi rõ thư viện nào được dùng, lấy từ đâu, phiên bản nào, giấy phép nào và cách kiểm tra tệp JAR. Nếu thiếu thông tin nguồn gốc, một JAR trong `lib` có thể trở thành một binary không rõ xuất xứ, khó cập nhật và khó tái lập build.

## 1. Cấu trúc thư mục `lib`

Một cách tổ chức đơn giản là đặt các JAR runtime của ứng dụng trong `lib`:

```text
inventory-app/
├── build.xml
├── src/
│   └── main/java/
├── lib/
│   ├── jackson-core-2.17.2.jar
│   ├── jackson-databind-2.17.2.jar
│   ├── jackson-annotations-2.17.2.jar
│   ├── slf4j-api-2.0.16.jar
│   ├── README.md
│   └── dependencies.properties
├── build/
└── dist/
```

Tên JAR nên thể hiện tên artifact và phiên bản cụ thể. Ví dụ `jackson-core-2.17.2.jar` dễ nhận biết hơn `jackson-core.jar` hoặc `latest.jar`. Khi có nhiều phiên bản của cùng thư viện, tên file giúp người đọc thấy ngay phiên bản nào đang được lưu trong repository.

Với dự án lớn hơn, có thể phân nhóm theo mục đích:

```text
lib/
├── compile/
├── runtime/
├── test/
├── tools/
└── metadata/
```

- `compile`: thư viện cần để biên dịch mã nguồn.
- `runtime`: thư viện cần khi ứng dụng chạy.
- `test`: framework và thư viện chỉ dùng khi biên dịch hoặc chạy kiểm thử.
- `tools`: thư viện hoặc công cụ hỗ trợ build nếu dự án thực sự cần quản lý chúng tại đây.
- `metadata`: danh sách dependency, thông tin giấy phép, checksum hoặc tài liệu nguồn gốc.

Đây là quy ước của dự án, không phải cấu trúc bắt buộc của Ant. Có thể dùng một thư mục `lib` duy nhất nếu dự án nhỏ, miễn cách đặt tên và phạm vi sử dụng rõ ràng.

## 2. Ghi lại nguồn gốc và phiên bản của từng thư viện

Mỗi JAR nên có một bản ghi giúp trả lời được các câu hỏi: thư viện này là gì, do ai phát hành, lấy từ đâu, dùng phiên bản nào, vì sao cần, giấy phép nào áp dụng và có dependency nào khác đi kèm?

Một bảng trong `lib/README.md` có thể dùng cấu trúc như sau:

| Artifact | Version | Nguồn tải | License | Mục đích |
|---|---|---|---|---|
| `jackson-core` | `2.17.2` | Maven Central, group `com.fasterxml.jackson.core` | Apache-2.0 | Đọc/ghi JSON ở runtime |
| `jackson-databind` | `2.17.2` | Maven Central, group `com.fasterxml.jackson.core` | Apache-2.0 | Ánh xạ JSON sang đối tượng Java |
| `jackson-annotations` | `2.17.2` | Maven Central, group `com.fasterxml.jackson.core` | Apache-2.0 | Annotation dùng bởi Jackson |
| `slf4j-api` | `2.0.16` | Maven Central, group `org.slf4j` | MIT | API ghi log |

Các giá trị trên là ví dụ minh họa cách ghi metadata. Khi đưa thư viện vào dự án thật, hãy xác minh phiên bản, nguồn phân phối và giấy phép của đúng artifact đã tải. Không suy ra giấy phép của một JAR chỉ từ tên file.

Thông tin nên lưu cho mỗi dependency:

- **Tên artifact và phiên bản:** xác định chính xác binary được sử dụng.
- **Group hoặc namespace nhà phát hành:** phân biệt các thư viện trùng tên.
- **Nguồn tải:** URL repository hoặc trang phát hành chính thức, kèm ngày tải nếu quy trình yêu cầu.
- **Checksum:** SHA-256 của chính tệp JAR đã đưa vào dự án.
- **License:** giấy phép và liên kết tới văn bản giấy phép áp dụng.
- **Mục đích sử dụng:** thành phần nào cần thư viện và ở compile, test hay runtime.
- **Dependency bắc cầu:** những thư viện khác cần có để thư viện này hoạt động.
- **Ghi chú cập nhật:** lý do chọn phiên bản, hạn chế tương thích hoặc thay đổi quan trọng.

## 3. Tạo tệp metadata cho dependency

Có thể duy trì một tệp `lib/README.md` hoặc `lib/dependencies.properties` cùng repository. Ví dụ:

`lib/dependencies.properties`:

```properties
# JSON processing
jackson.group=com.fasterxml.jackson.core
jackson.version=2.17.2
jackson.core=jackson-core-2.17.2.jar
jackson.databind=jackson-databind-2.17.2.jar
jackson.annotations=jackson-annotations-2.17.2.jar

# Logging API
slf4j.group=org.slf4j
slf4j.version=2.0.16
slf4j.api=slf4j-api-2.0.16.jar
```

Tệp này là metadata do dự án tự quản lý. Ant có thể đọc nó bằng task `<property file="..."/>` nếu buildfile cần dùng lại phiên bản hoặc tên JAR trong nhiều nơi:

```xml
<property file="lib/dependencies.properties"/>

<path id="application.classpath">
    <pathelement location="lib/${jackson.core}"/>
    <pathelement location="lib/${jackson.databind}"/>
    <pathelement location="lib/${jackson.annotations}"/>
    <pathelement location="lib/${slf4j.api}"/>
</path>
```

Việc đặt tên file trong metadata giúp tránh lặp phiên bản ở nhiều chỗ. Tuy nhiên, metadata không tự tải JAR và cũng không kiểm tra rằng nội dung tệp có đúng artifact được ghi hay không. Nhóm phát triển vẫn phải đưa đúng binary vào `lib` và xác minh checksum.

## 4. Khai báo classpath tường minh trong `build.xml`

Sau khi đặt JAR vào `lib`, khai báo chúng trong datatype `Path`:

```xml
<path id="compile.classpath">
    <pathelement location="lib/jackson-core-2.17.2.jar"/>
    <pathelement location="lib/jackson-databind-2.17.2.jar"/>
    <pathelement location="lib/jackson-annotations-2.17.2.jar"/>
    <pathelement location="lib/slf4j-api-2.0.16.jar"/>
</path>
```

Sau đó dùng path này trong task `javac`:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Và dùng path runtime khi chạy ứng dụng:

```xml
<target name="run" depends="compile">
    <java classname="com.example.Main"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="build/classes"/>
            <path refid="compile.classpath"/>
        </classpath>
    </java>
</target>
```

`Path` cho phép kết hợp các phần tử tường minh và path đã khai báo. Cách này giúp buildfile thể hiện chính xác những JAR nào tham gia compile và runtime.

### Dùng FileSet để lấy tất cả JAR

Với dự án nhỏ, có thể thêm toàn bộ JAR trong thư mục bằng FileSet:

```xml
<path id="application.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib" includes="*.jar"/>
</path>
```

Đây là cách ngắn gọn, nhưng cần hiểu tác động của nó: bất kỳ JAR nào được đặt vào thư mục `lib` đều có thể tự động đi vào classpath. Nếu trong đó có JAR chỉ dùng để compile, JAR kiểm thử, bản cũ hoặc bản mới thay thế, build có thể nạp nhầm thư viện. Với dự án cần kiểm soát chặt, nên khai báo từng JAR hoặc dùng các FileSet riêng theo nhóm có quy ước rõ.

Không nên giữ hai phiên bản của cùng artifact trong một thư mục được quét bằng `*.jar`. Cả hai có thể xuất hiện trong classpath và kết quả phụ thuộc thứ tự nạp lớp. Xóa bản cũ khỏi tập hợp đang dùng hoặc phân nhóm chúng ra ngoài classpath hiện hành.

## 5. Phân biệt compile, runtime và test dependency

Không phải thư viện nào cũng cần ở mọi giai đoạn. Ví dụ, API của một thư viện có thể cần để biên dịch, trong khi một implementation cụ thể chỉ được nạp ở runtime. Framework kiểm thử chỉ cần cho target test.

```xml
<path id="compile.classpath">
    <fileset dir="lib/compile" includes="*.jar"/>
</path>

<path id="runtime.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib/compile" includes="*.jar"/>
    <fileset dir="lib/runtime" includes="*.jar"/>
</path>

<path id="test.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
    <path refid="compile.classpath"/>
    <path refid="runtime.classpath"/>
    <fileset dir="lib/test" includes="*.jar"/>
</path>
```

Ví dụ này minh họa cách chia scope. Một số JAR có thể cần ở cả compile và runtime, nên chúng có thể xuất hiện trong cả hai path. Tránh thêm thư viện kiểm thử vào runtime của ứng dụng phát hành nếu ứng dụng không cần chúng.

## 6. Quản lý dependency bắc cầu

Một JAR có thể phụ thuộc vào những JAR khác. Ví dụ, thư viện A sử dụng thư viện B; nếu chỉ thêm A vào `lib`, ứng dụng có thể biên dịch được nhưng lỗi khi chạy do thiếu lớp của B.

Khi quản lý thủ công, dự án phải ghi lại dependency bắc cầu và tự thêm các artifact cần thiết. Ant không tự đọc metadata Maven của JAR để giải quyết và tải các dependency bắc cầu như một dependency manager chuyên dụng.

Một bản ghi dependency có thể bao gồm:

```text
Application
└── jackson-databind 2.17.2
    ├── jackson-core 2.17.2
    └── jackson-annotations 2.17.2
```

Đây là ví dụ về cách thể hiện quan hệ. Hãy lấy danh sách dependency chính xác từ metadata phát hành của phiên bản đang dùng, chẳng hạn POM tương ứng trên repository hoặc tài liệu chính thức của thư viện. Đừng suy đoán dependency bắc cầu từ tên các JAR đang có trong thư mục.

Nếu thư viện cần dependency bắc cầu nhưng không có trong `lib`, các lỗi thường gặp là `NoClassDefFoundError` hoặc `ClassNotFoundException` khi chạy. Khi đó, hãy xác định lớp bị thiếu thuộc artifact nào, bổ sung đúng phiên bản tương thích và cập nhật metadata.

## 7. Ghi checksum để xác minh binary

Checksum giúp phát hiện JAR bị thay đổi, tải thiếu hoặc bị thay bằng một binary khác có cùng tên file. SHA-256 là lựa chọn phổ biến để ghi dấu vân tay của tệp.

Trên Windows PowerShell:

```powershell
Get-FileHash .\lib\jackson-core-2.17.2.jar -Algorithm SHA256
```

Trên Linux:

```sh
sha256sum lib/jackson-core-2.17.2.jar
```

Trên macOS:

```sh
shasum -a 256 lib/jackson-core-2.17.2.jar
```

Ghi giá trị checksum thu được vào metadata cùng tên file và nguồn tải. Khi nhận JAR từ một máy khác hoặc khôi phục từ kho lưu trữ, tính lại checksum rồi so sánh với giá trị đã ghi.

Ví dụ metadata:

```text
File: jackson-core-2.17.2.jar
Artifact: com.fasterxml.jackson.core:jackson-core:2.17.2
Source: https://repo.maven.apache.org/maven2/
SHA-256: <ghi-gia-tri-da-xac-minh>
License: Apache-2.0
```

Không sao chép một checksum từ một phiên bản khác hoặc một trang không phải nguồn đáng tin cậy. Checksum chỉ xác minh nội dung tệp khớp với giá trị tham chiếu; nó không chứng minh nhà phát hành là ai nếu nguồn của checksum không đáng tin cậy. Khi repository cung cấp checksum hoặc chữ ký số, hãy lấy từ kênh phát hành chính thức và tuân theo quy trình xác minh của tổ chức.

## 8. Kiểm tra nội dung JAR và thông tin phát hành

JAR là tệp ZIP có cấu trúc. Có thể xem danh sách nội dung bằng lệnh:

```sh
jar tf lib/jackson-core-2.17.2.jar
```

Để xem manifest:

```sh
jar xf lib/jackson-core-2.17.2.jar META-INF/MANIFEST.MF
```

Lệnh thứ hai giải nén manifest vào thư mục hiện tại. Nếu chỉ muốn đọc mà không làm thay đổi thư mục làm việc, có thể dùng công cụ ZIP phù hợp để in nội dung entry. Manifest có thể chứa tên implementation, phiên bản hoặc thông tin đóng gói, nhưng không phải mọi JAR đều cung cấp đầy đủ metadata và nội dung manifest không thay thế nguồn phát hành chính thức.

Với JAR có thể là module Java, dùng:

```sh
jar --describe-module --file lib/some-library.jar
```

Để xem dependency và tham chiếu lớp ở mức bytecode, có thể dùng `jdeps`:

```sh
jdeps --summary lib/some-library.jar
```

Các công cụ này giúp điều tra binary đang dùng, nhưng không thay thế việc ghi tọa độ artifact, phiên bản, nguồn tải và giấy phép vào metadata của dự án.

## 9. Ghi nhận giấy phép và nghĩa vụ phân phối

Thư viện bên ngoài đi kèm điều kiện giấy phép. Trước khi đưa JAR vào repository hoặc gói phát hành, cần xác định license của đúng phiên bản và kiểm tra nghĩa vụ áp dụng cho cách sử dụng của dự án.

Một số việc cần lưu ý:

- Lưu tên license và bản văn license hoặc liên kết tới nguồn chính thức.
- Kiểm tra yêu cầu giữ copyright notice, license notice hoặc tệp NOTICE.
- Xác định có cần đưa các tệp thông báo vào gói phân phối hay không.
- Kiểm tra license của dependency bắc cầu, không chỉ thư viện được khai báo trực tiếp.
- Ghi lại nếu dự án có sửa đổi hoặc đóng gói lại binary so với bản phát hành ban đầu.

Không nên kết luận rằng mọi JAR tải từ Maven Central đều có cùng giấy phép. Cùng một repository có thể lưu trữ artifact với nhiều license khác nhau; hãy xem metadata và tài liệu đi kèm của từng artifact/version.

## 10. Quy tắc đặt tên và khóa phiên bản

Tên file có phiên bản giúp tránh thay thế binary âm thầm. Ví dụ:

```text
lib/
├── gson-2.11.0.jar
├── slf4j-api-2.0.16.jar
└── logback-classic-1.5.8.jar
```

Nên áp dụng các nguyên tắc:

1. Dùng tên artifact và phiên bản chính xác trong tên file.
2. Không dùng tên chung như `library.jar`, `new.jar` hoặc `latest.jar`.
3. Không ghi đè một JAR đang dùng bằng binary phiên bản mới nhưng giữ nguyên tên file.
4. Cập nhật buildfile và metadata trong cùng một thay đổi khi nâng phiên bản.
5. Nếu cần giữ bản cũ để so sánh, đặt nó ngoài thư mục được đưa vào classpath.
6. Ghi rõ nguồn tải và checksum cho binary mới.

Việc pin phiên bản giúp mọi máy build dùng cùng một dependency. Nếu chỉ quét `lib/*.jar` mà không có quy ước, người khác có thể thêm một JAR bất kỳ và vô tình làm thay đổi classpath của ứng dụng.

## 11. Cập nhật hoặc thay thế một thư viện

Khi nâng cấp thư viện, không chỉ thay file JAR. Cần xử lý toàn bộ thông tin liên quan:

1. Xác định lý do nâng cấp, chẳng hạn sửa lỗi, yêu cầu tính năng, tương thích JDK hoặc bản vá bảo mật.
2. Chọn phiên bản cụ thể và kiểm tra ghi chú phát hành.
3. Xác định dependency bắc cầu và các phiên bản tương thích.
4. Tải binary từ nguồn phát hành tin cậy.
5. Xác minh checksum và license.
6. Đặt JAR mới vào đúng thư mục, cập nhật `Path` trong `build.xml` và metadata.
7. Xóa JAR cũ khỏi classpath đang sử dụng để tránh hai phiên bản cùng được nạp.
8. Biên dịch, chạy kiểm thử và khởi động ứng dụng với cấu hình mới.
9. Ghi lại thay đổi và lý do trong lịch sử phiên bản của dự án.

Không nên giữ cả phiên bản cũ và mới trong cùng FileSet được đưa vào classpath. Hai JAR có thể chứa cùng fully qualified class name; JVM thường dùng lớp được tìm thấy đầu tiên, khiến hành vi phụ thuộc thứ tự classpath và khó chẩn đoán.

## 12. Tạo target kiểm tra sự hiện diện của thư viện

Ant có task `<available>` để kiểm tra một tệp có tồn tại trước khi chạy target phụ thuộc. Ví dụ:

```xml
<target name="check-libraries">
    <available file="lib/jackson-core-2.17.2.jar"
               property="jackson.core.present"/>
    <fail unless="jackson.core.present"
          message="Missing lib/jackson-core-2.17.2.jar"/>
</target>

<target name="compile" depends="check-libraries">
    <!-- Các task javac được khai báo ở đây. -->
</target>
```

Target này kiểm tra sự hiện diện của file theo đường dẫn đã chỉ định. Nó không xác minh checksum, license hay tính tương thích của JAR. Nếu cần xác minh nội dung binary, phải bổ sung bước checksum hoặc công cụ kiểm tra phù hợp.

Có thể kiểm tra nhiều file bằng nhiều phần tử `<available>` hoặc tạo một target kiểm tra riêng để lỗi thiếu dependency xuất hiện sớm với thông báo dễ hiểu.

## 13. Một ví dụ buildfile quản lý thư viện thủ công

Ví dụ dưới đây dùng property để pin tên JAR, khai báo compile/runtime path và kiểm tra một dependency trước khi biên dịch:

```xml
<project name="manual-library-demo" default="run" basedir=".">

    <property file="lib/dependencies.properties"/>
    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>

    <path id="application.dependencies">
        <pathelement location="lib/${jackson.core}"/>
        <pathelement location="lib/${jackson.databind}"/>
        <pathelement location="lib/${jackson.annotations}"/>
        <pathelement location="lib/${slf4j.api}"/>
    </path>

    <path id="runtime.classpath">
        <pathelement location="${classes.dir}"/>
        <path refid="application.dependencies"/>
    </path>

    <target name="check-libraries">
        <available file="lib/${jackson.core}"
                   property="jackson.core.present"/>
        <available file="lib/${jackson.databind}"
                   property="jackson.databind.present"/>
        <available file="lib/${jackson.annotations}"
                   property="jackson.annotations.present"/>
        <fail unless="jackson.core.present"
              message="Missing Jackson Core JAR"/>
        <fail unless="jackson.databind.present"
              message="Missing Jackson Databind JAR"/>
        <fail unless="jackson.annotations.present"
              message="Missing Jackson Annotations JAR"/>
    </target>

    <target name="compile" depends="check-libraries">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="application.dependencies"/>
        </javac>
    </target>

    <target name="run" depends="compile">
        <java classname="com.example.Main"
              fork="true"
              failonerror="true">
            <classpath refid="runtime.classpath"/>
        </java>
    </target>

</project>
```

Tệp `dependencies.properties` cần có các khóa tương ứng với tên file thực tế. Ví dụ ở phần trên chỉ minh họa cấu trúc; nếu thay phiên bản JAR, hãy cập nhật tên artifact, phiên bản, checksum, license và dependency bắc cầu cùng lúc.

## 14. Có nên commit JAR vào repository?

Việc lưu binary trong Git có ưu điểm là checkout repository đã có dependency và build không cần truy cập mạng. Tuy nhiên, JAR làm repository tăng dung lượng, khó xem diff và cần quy trình cập nhật rõ ràng.

Một số dự án lưu thư viện trực tiếp trong `lib`; dự án khác lưu binary trong kho artifact nội bộ và chỉ tải về theo hướng dẫn riêng. Nếu chọn commit JAR:

- Chỉ lưu các binary được phép phân phối theo license.
- Ghi nguồn gốc, checksum và phiên bản trong repository.
- Không commit JAR tự build hoặc JAR tải không rõ nguồn.
- Dùng tên file bất biến theo phiên bản.
- Xem xét chính sách lưu trữ binary của tổ chức và giới hạn dung lượng repository.

Nếu không commit JAR, cần cung cấp hướng dẫn tải đúng binary và xác minh checksum. Không để build âm thầm phụ thuộc vào một thư mục `lib` cá nhân không được quản lý hoặc không có hướng dẫn tái tạo.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `javac` báo không tìm thấy package | JAR thiếu khỏi compile classpath hoặc dependency bắc cầu chưa được thêm | Xác định artifact chứa lớp cần thiết và cập nhật Path cùng metadata |
| Ứng dụng báo `NoClassDefFoundError` | Dependency có khi compile nhưng thiếu lúc runtime | Bổ sung JAR vào runtime classpath và kiểm tra dependency bắc cầu |
| Chạy nhầm phiên bản thư viện | Nhiều JAR cùng artifact hoặc tên file không thể hiện version | Pin phiên bản trong tên file và loại bản cũ khỏi classpath |
| Build chạy khác nhau trên hai máy | Một máy có JAR cục bộ không được ghi nhận hoặc classpath quét JAR không kiểm soát | Quản lý JAR và metadata trong repository hoặc cung cấp quy trình tải tái lập |
| JAR tải về không khớp bản ghi | Binary bị thay thế, tải lỗi hoặc checksum tham chiếu sai | Tải lại từ nguồn tin cậy và xác minh SHA-256 |
| License của thư viện không rõ | Chỉ lưu JAR mà không lưu metadata phát hành | Kiểm tra artifact/version chính xác và ghi license cùng thông báo cần phân phối |
| Hai JAR chứa cùng lớp | Có phiên bản trùng hoặc thư viện được đóng gói lặp | Loại bản trùng, kiểm tra thứ tự classpath và dependency bắc cầu |
| JAR có tên đúng nhưng nội dung không như mong đợi | File bị đổi tên hoặc lấy nhầm artifact | Kiểm tra manifest, danh sách nội dung, module metadata và checksum |
| Buildfile báo thiếu file dù JAR tồn tại | Đường dẫn tương đối được tính từ project base directory khác dự kiến | Dùng `${basedir}` hoặc property `location` để tạo đường dẫn rõ ràng |

## 16. Checklist quản lý thủ công thư viện

- [ ] Mỗi JAR có tên artifact và phiên bản cụ thể.
- [ ] Đã xác định group/artifact/version và nhà phát hành.
- [ ] Đã ghi nguồn tải chính thức hoặc repository tin cậy.
- [ ] Đã xác minh và lưu SHA-256 của binary.
- [ ] Đã ghi license và các thông báo cần giữ khi phân phối.
- [ ] Đã ghi dependency bắc cầu và phạm vi compile/runtime/test.
- [ ] `build.xml` khai báo classpath rõ ràng bằng `Path`, `pathelement` hoặc FileSet có phạm vi kiểm soát.
- [ ] Không có nhiều phiên bản của cùng artifact trong classpath đang dùng.
- [ ] Có hướng dẫn tái tạo thư mục `lib` khi checkout trên máy mới.
- [ ] Mọi nâng cấp đều cập nhật binary, buildfile và metadata trong cùng một thay đổi.
- [ ] Đã kiểm tra biên dịch, kiểm thử và chạy ứng dụng sau khi thay đổi dependency.

Quản lý thư viện thủ công trong `lib` phù hợp với dự án nhỏ hoặc môi trường build cần giữ dependency tại chỗ. Để cách làm này đáng tin cậy, hãy pin phiên bản, khai báo classpath có chủ đích, ghi nguồn gốc và license, lưu checksum, quản lý dependency bắc cầu và cập nhật mọi metadata cùng với binary tương ứng.
