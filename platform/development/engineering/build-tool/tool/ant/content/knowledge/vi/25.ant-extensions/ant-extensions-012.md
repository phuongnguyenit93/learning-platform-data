# Đóng gói, quản lý phiên bản và phân phối antlib

Antlib giúp một nhóm task, datatype và macro của Apache Ant được đóng gói thành thư viện có thể tái sử dụng giữa nhiều dự án. Để thư viện có thể được dùng ổn định, cần tổ chức descriptor `antlib.xml`, biên dịch các lớp mở rộng, tạo JAR, quản lý phiên bản, ghi metadata phát hành và phân phối artifact qua một kênh mà các build khác có thể truy cập.

Một antlib được phát hành tốt cần trả lời được các câu hỏi: thư viện cung cấp task nào, phiên bản nào đang được sử dụng, cần phiên bản Ant/JDK nào, dependency nào phải có khi chạy, artifact được tải từ đâu và làm sao xác minh nó không bị thay đổi. Những thông tin này giúp các dự án tiêu thụ thư viện có thể pin phiên bản, tái lập build và nâng cấp có kiểm soát.

## 1. Cấu trúc một dự án antlib có thể phát hành

Một dự án thư viện task có thể tổ chức như sau:

```text
acme-ant-tasks/
├── build.xml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── NOTICE
├── ivy.xml
├── src/
│   ├── main/java/
│   │   └── com/example/ant/
│   │       ├── HelloTask.java
│   │       └── GreetingType.java
│   └── main/resources/
│       └── com/example/ant/
│           └── antlib.xml
├── build/
│   └── classes/
└── dist/
```

Các thư mục và tệp có trách nhiệm riêng:

- `src/main/java`: mã Java triển khai custom task và datatype.
- `src/main/resources`: descriptor và tài nguyên cần được đưa vào JAR.
- `antlib.xml`: ánh xạ tên XML sang lớp task hoặc datatype.
- `build/classes`: bytecode sau khi biên dịch.
- `build/`: đầu ra trung gian, có thể xóa và tạo lại.
- `dist/`: artifact phát hành, chẳng hạn JAR, ZIP, metadata và checksum.
- `README.md`, `CHANGELOG.md`, `LICENSE`, `NOTICE`: hướng dẫn, lịch sử thay đổi và thông tin pháp lý đi kèm.
- `ivy.xml` hoặc POM: mô tả tọa độ và dependency khi phát hành lên repository hỗ trợ metadata tương ứng.

Đây là quy ước tổ chức, không phải cấu trúc bắt buộc của Ant. Điều quan trọng là buildfile có thể tạo lại artifact từ source và resource được quản lý trong repository.

## 2. Descriptor `antlib.xml` là giao diện công khai của thư viện

Ví dụ descriptor cho thư viện `com.example.ant`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<antlib>
    <taskdef name="hello"
             classname="com.example.ant.HelloTask"/>

    <typedef name="greeting"
             classname="com.example.ant.GreetingType"/>

    <macrodef name="say-hello">
        <attribute name="who"/>
        <sequential>
            <echo message="Hello, @{who}!"/>
        </sequential>
    </macrodef>
</antlib>
```

Descriptor này cung cấp ba thành phần có thể được gọi từ buildfile:

| Local name | Loại | Ý nghĩa |
|---|---|---|
| `hello` | Java task | Gọi lớp `HelloTask` |
| `greeting` | Datatype | Tạo đối tượng cấu hình `GreetingType` |
| `say-hello` | Macro task | Chạy chuỗi task Ant đã được định nghĩa trước |

Nếu namespace URI là `antlib:com.example.ant`, descriptor phải được đóng gói ở resource path `com/example/ant/antlib.xml`. Không đặt descriptor ở thư mục gốc JAR trừ khi URI và cách nạp được thiết kế tương ứng.

Tên task, thuộc tính, nested element và hành vi mặc định tạo thành giao diện mà các buildfile khác phụ thuộc. Sau khi phát hành, thay đổi tên task hoặc bỏ thuộc tính đang được sử dụng có thể làm hỏng build của người tiêu thụ. Vì vậy, cần xem descriptor và API Java của task là một phần của hợp đồng tương thích.

## 3. Tách dependency của thư viện task khỏi dependency của ứng dụng

Custom task chạy trong JVM của Ant. Nó có thể cần các lớp API của Ant và những thư viện hỗ trợ riêng. Các dependency đó khác với thư viện mà ứng dụng Java được build bằng Ant sử dụng ở runtime.

Ví dụ, `HelloTask` kế thừa `org.apache.tools.ant.Task`. Khi biên dịch thư viện, compiler cần `ant.jar` trên compile classpath:

```xml
<path id="ant.compile.classpath">
    <pathelement location="${ant.home}/lib/ant.jar"/>
</path>

<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"
       encoding="UTF-8">
    <classpath refid="ant.compile.classpath"/>
</javac>
```

`ant.jar` cung cấp API của Ant và thường đã có trong runtime của Ant khi thư viện task được nạp. Không nên đóng gói bản sao `ant.jar` vào trong JAR antlib như một dependency bình thường; việc đó có thể tạo xung đột classloader và phiên bản API. Hãy ghi phiên bản Ant tối thiểu mà thư viện yêu cầu trong tài liệu và metadata.

Nếu task sử dụng một thư viện hỗ trợ, ví dụ parser hoặc client HTTP, dependency đó phải có sẵn khi Ant nạp task. Có thể phân phối các JAR phụ thuộc cạnh JAR antlib hoặc khai báo chúng trong metadata repository. Khi người dùng nạp thư viện, toàn bộ dependency cần thiết phải nằm trong classpath task library.

## 4. Quản lý phiên bản của antlib

Một thư viện antlib nên có phiên bản phát hành rõ ràng và không đổi nội dung sau khi đã công bố. Quy tắc Semantic Versioning (SemVer) là một lựa chọn phổ biến:

```text
MAJOR.MINOR.PATCH
```

| Thành phần | Khi nào tăng? | Ví dụ thay đổi |
|---|---|---|
| MAJOR | Có thay đổi không tương thích | Xóa task, đổi tên thuộc tính, đổi kiểu dữ liệu XML, tăng yêu cầu Ant/JDK gây vỡ build cũ |
| MINOR | Thêm tính năng tương thích ngược | Thêm task mới, thêm thuộc tính tùy chọn có mặc định an toàn |
| PATCH | Sửa lỗi tương thích ngược | Sửa xử lý đường dẫn, thông báo lỗi hoặc lỗi nội bộ mà không đổi hợp đồng sử dụng |

Ví dụ:

- `1.4.0`: thêm task `copy-report` mà không phá task hiện có.
- `1.4.1`: sửa lỗi xử lý tên file trong `copy-report`.
- `2.0.0`: thay đổi bắt buộc thuộc tính của task cũ hoặc bỏ một API đã công bố.

Với bản thử nghiệm, có thể dùng hậu tố như `2.0.0-alpha.1`, `2.0.0-beta.2` hoặc `2.0.0-rc.1`. Không nên phát hành các bản thử nghiệm dưới tên phiên bản ổn định vì người tiêu thụ khó phân biệt mức độ hoàn thiện.

SemVer là chính sách mà nhóm phát triển cam kết tuân theo; Ant không tự kiểm tra rằng thay đổi code có đúng mức tăng version hay không. Cần ghi quy tắc trong `README` hoặc tài liệu đóng góp và áp dụng nhất quán.

## 5. Những thay đổi nào ảnh hưởng tương thích?

Đối với antlib, tương thích không chỉ nằm ở chữ ký phương thức Java. Buildfile gọi task bằng XML, do đó các thay đổi sau có thể phá build của người dùng:

- Đổi namespace URI hoặc local name của task.
- Xóa hoặc đổi tên thuộc tính XML.
- Đổi thuộc tính từ tùy chọn thành bắt buộc.
- Thay đổi ý nghĩa của thuộc tính hoặc giá trị mặc định.
- Đổi kiểu nested element hoặc cách task nhận datatype.
- Thay đổi thứ tự thực thi hoặc tác dụng phụ của task.
- Nâng phiên bản Ant/JDK tối thiểu mà không thông báo.
- Đổi dependency sang phiên bản có hành vi hoặc API không tương thích.
- Thay đổi vị trí resource descriptor hoặc cách nạp thư viện.

Ví dụ, buildfile cũ:

```xml
<acme:hello message="Build started"/>
```

Nếu phiên bản mới đổi thuộc tính `message` thành `text` và không hỗ trợ tên cũ, buildfile tiêu thụ sẽ lỗi. Nếu cần thay API, có thể giữ thuộc tính cũ trong một giai đoạn chuyển tiếp, đánh dấu deprecated, cập nhật tài liệu rồi mới loại bỏ trong major release.

## 6. Đặt version tập trung trong `build.xml`

Không nên lặp số phiên bản ở nhiều task. Khai báo một property và sử dụng nó cho tên JAR, manifest, thư mục staging và archive:

```xml
<project name="acme-ant-tasks" default="package" basedir=".">

    <property name="library.name" value="acme-ant-tasks"/>
    <property name="library.version" value="1.4.0"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="jar.file"
              location="${dist.dir}/${library.name}-${library.version}.jar"/>

</project>
```

Tên artifact sẽ có dạng:

```text
dist/acme-ant-tasks-1.4.0.jar
```

Khi phát hành version mới, cập nhật một giá trị `library.version`. Có thể đưa version vào tệp properties hoặc truyền từ CI bằng `-Dlibrary.version=...`; nếu dùng property mặc định trong buildfile, property dòng lệnh được Ant thiết lập trước và không bị `<property>` thông thường ghi đè.

Không dùng `latest.jar` làm tên artifact phát hành chính thức. Tên file có version giúp người tiêu thụ pin đúng binary và cho phép giữ nhiều bản phát hành trong repository mà không ghi đè lẫn nhau.

## 7. Ghi metadata phiên bản trong manifest

Ngoài tên JAR, có thể ghi thông tin phát hành trong `META-INF/MANIFEST.MF`:

```xml
<jar destfile="${jar.file}" basedir="${classes.dir}">
    <manifest>
        <attribute name="Implementation-Title" value="Acme Ant Tasks"/>
        <attribute name="Implementation-Version" value="${library.version}"/>
        <attribute name="Implementation-Vendor" value="Example Engineering"/>
        <attribute name="Specification-Title" value="Acme Ant Task API"/>
        <attribute name="Specification-Version" value="1"/>
    </manifest>
</jar>
```

Các thuộc tính manifest giúp công cụ và người quản trị nhận diện JAR. Có thể đọc manifest từ Java hoặc giải nén file `META-INF/MANIFEST.MF` để kiểm tra.

Không nên nhầm `Implementation-Version` với version của API specification. Nếu API được quản lý độc lập với bản triển khai, hãy tăng `Specification-Version` theo chính sách riêng. Metadata trong manifest hỗ trợ nhận diện; nguồn chuẩn về version phát hành vẫn nên là tọa độ artifact và changelog.

## 8. Tạo JAR antlib có descriptor và resource

Giả sử source đã biên dịch vào `build/classes` và descriptor nằm trong `src/main/resources/com/example/ant/antlib.xml`. Task `<jar>` có thể đóng gói cả hai:

```xml
<target name="jar" depends="compile">
    <mkdir dir="${dist.dir}"/>

    <jar destfile="${jar.file}" basedir="${classes.dir}">
        <fileset dir="src/main/resources"/>
        <manifest>
            <attribute name="Implementation-Title" value="Acme Ant Tasks"/>
            <attribute name="Implementation-Version" value="${library.version}"/>
            <attribute name="Implementation-Vendor" value="Example Engineering"/>
        </manifest>
    </jar>
</target>
```

JAR kết quả phải chứa ít nhất:

```text
com/example/ant/antlib.xml
com/example/ant/HelloTask.class
com/example/ant/GreetingType.class
META-INF/MANIFEST.MF
```

Nếu descriptor không được copy vào archive, namespace `antlib:com.example.ant` sẽ không thể tìm thấy resource tương ứng. Nếu class được khai báo trong descriptor không được đóng gói, Ant có thể đọc descriptor nhưng thất bại khi tạo task.

Kiểm tra nội dung JAR bằng:

```sh
jar tf dist/acme-ant-tasks-1.4.0.jar
```

## 9. Buildfile hoàn chỉnh để biên dịch và đóng gói

Ví dụ sau thể hiện một buildfile tối giản cho thư viện antlib. Nó biên dịch Java, copy resource, tạo JAR có version và đóng gói tài liệu phát hành:

```xml
<project name="acme-ant-tasks" default="distribution" basedir=".">

    <property name="library.name" value="acme-ant-tasks"/>
    <property name="library.version" value="1.4.0"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="stage.dir" location="build/distribution"/>
    <property name="jar.file"
              location="${dist.dir}/${library.name}-${library.version}.jar"/>

    <path id="ant.compile.classpath">
        <pathelement location="${ant.home}/lib/ant.jar"/>
    </path>

    <target name="clean">
        <delete dir="build"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="ant.compile.classpath"/>
        </javac>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${jar.file}" basedir="${classes.dir}">
            <fileset dir="src/main/resources"/>
            <manifest>
                <attribute name="Implementation-Title" value="Acme Ant Tasks"/>
                <attribute name="Implementation-Version" value="${library.version}"/>
                <attribute name="Implementation-Vendor" value="Example Engineering"/>
            </manifest>
        </jar>
    </target>

    <target name="distribution" depends="jar">
        <mkdir dir="${stage.dir}"/>
        <copy file="${jar.file}" todir="${stage.dir}"/>
        <copy file="README.md" todir="${stage.dir}"/>
        <copy file="CHANGELOG.md" todir="${stage.dir}"/>
        <copy file="LICENSE" todir="${stage.dir}"/>
        <copy file="NOTICE" todir="${stage.dir}"/>

        <zip destfile="${dist.dir}/${library.name}-${library.version}-distribution.zip"
             basedir="${stage.dir}"/>
    </target>

</project>
```

Trong ví dụ, `ant.jar` chỉ nằm trên compile classpath. Nó không được đưa vào JAR antlib. Nếu custom task có dependency runtime khác, cần bổ sung chúng vào classpath khi antlib được nạp và đưa thông tin dependency vào metadata hoặc gói phát hành.

## 10. Phân biệt JAR thư viện và gói phân phối

JAR là artifact chính chứa class và resource để Ant nạp. Gói phân phối có thể chứa JAR cùng tài liệu và metadata.

```text
acme-ant-tasks-1.4.0-distribution.zip
├── acme-ant-tasks-1.4.0.jar
├── README.md
├── CHANGELOG.md
├── LICENSE
├── NOTICE
├── dependencies.md
└── checksums/
    └── SHA256SUMS
```

Không nhất thiết phải đưa toàn bộ tài liệu vào JAR. Người tiêu thụ thường cần JAR và các dependency để chạy; người quản trị hoặc người phân phối cần README, changelog, license, notice và checksum để xác định nguồn gốc và điều kiện sử dụng.

Nếu phân phối dependency riêng, có thể dùng cấu trúc:

```text
acme-ant-tasks-1.4.0/
├── lib/
│   ├── acme-ant-tasks-1.4.0.jar
│   └── acme-ant-support-2.3.1.jar
├── README.md
├── CHANGELOG.md
├── LICENSE
└── NOTICE
```

Tài liệu phải nói rõ cách thêm các JAR vào classpath của Ant. Không nên giả định rằng JAR đặt trong thư mục `lib` của project sẽ tự động được Ant nạp.

## 11. Metadata dependency bằng Maven POM hoặc Ivy descriptor

Nếu artifact được phân phối qua Maven repository, cần metadata tọa độ Maven như groupId, artifactId, version và dependency. Ví dụ POM tối thiểu:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.build</groupId>
    <artifactId>acme-ant-tasks</artifactId>
    <version>1.4.0</version>
    <packaging>jar</packaging>
    <name>Acme Ant Tasks</name>
    <description>Reusable Ant tasks and datatypes.</description>
    <url>https://example.com/acme-ant-tasks</url>
    <licenses>
        <license>
            <name>Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
        </license>
    </licenses>
    <dependencies>
        <dependency>
            <groupId>org.apache.ant</groupId>
            <artifactId>ant</artifactId>
            <version>1.10.15</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
</project>
```

Đây là ví dụ metadata; thay version Ant, URL, license và dependency bằng thông tin thực tế. Scope `provided` biểu thị rằng Ant runtime cung cấp API Ant khi chạy task. Nếu thư viện task cần dependency ngoài khác, hãy khai báo chúng với scope phù hợp để người tiêu thụ có thể lấy đủ dependency.

Với hệ thống dùng Apache Ivy, có thể cung cấp descriptor `ivy.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info organisation="com.example.build"
          module="acme-ant-tasks"
          revision="1.4.0"
          status="release"/>

    <configurations>
        <conf name="default"/>
        <conf name="compile"/>
        <conf name="runtime" extends="compile"/>
    </configurations>

    <dependencies>
        <dependency org="org.apache.ant"
                    name="ant"
                    rev="1.10.15"
                    conf="compile->default;runtime->default"/>
    </dependencies>
</ivy-module>
```

Metadata phải khớp version JAR được phát hành. Nếu JAR tên `acme-ant-tasks-1.4.0.jar` nhưng POM hoặc Ivy descriptor khai báo `1.3.0`, người tiêu thụ có thể tải nhầm hoặc không thể xác minh đúng tọa độ artifact.

## 12. Phân phối qua repository

Antlib có thể được lưu trong repository nội bộ hoặc repository Maven/Ivy để các project khác resolve theo tọa độ.

Ví dụ tọa độ:

```text
groupId:    com.example.build
artifactId: acme-ant-tasks
version:    1.4.0
packaging:  jar
```

Trong layout Maven repository, artifact thường được lưu theo cấu trúc:

```text
com/example/build/acme-ant-tasks/1.4.0/
├── acme-ant-tasks-1.4.0.jar
├── acme-ant-tasks-1.4.0.pom
└── metadata/checksum files theo repository
```

Build phát hành có thể dùng công cụ quản lý repository của tổ chức, Maven deploy plugin hoặc task publish của Ivy. Ant core không tự cung cấp một cơ chế duy nhất để publish tới mọi loại repository; cần chọn công cụ phù hợp với repository đích và xác thực của nó.

Với Ivy, task `ivy:publish` có thể publish artifact và descriptor tới resolver hỗ trợ publish. Ví dụ khái quát:

```xml
<project name="publish-antlib"
         default="publish"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <target name="publish">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:publish resolver="company-releases"
                     pubrevision="1.4.0"
                     status="release"
                     overwrite="false">
            <artifacts pattern="dist/[artifact]-[revision].[ext]"/>
        </ivy:publish>
    </target>

</project>
```

Đây là ví dụ cấu trúc; resolver `company-releases` phải được khai báo trong `ivysettings.xml`, và artifact/descriptor cần được đặt đúng vị trí mà Ivy publish mong đợi. Kiểm tra tài liệu Ivy của phiên bản đang dùng về `publishpattern`, `artifactspattern`, descriptor và cấu hình resolver. Không publish bản release bằng `overwrite="true"` nếu chính sách repository yêu cầu artifact bất biến.

## 13. Quy tắc bất biến của release artifact

Một version release nên đại diện cho đúng một nội dung binary. Sau khi phát hành `1.4.0`, không nên thay JAR ở cùng tọa độ bằng một binary khác nhưng vẫn giữ version `1.4.0`.

Nếu phát hiện lỗi trong artifact đã phát hành:

1. Sửa source.
2. Tăng version, ví dụ từ `1.4.0` lên `1.4.1`.
3. Tạo lại JAR và metadata.
4. Tạo checksum mới.
5. Phát hành version mới.

Không sửa nội dung một release đã được người dùng tải về. Việc giữ artifact bất biến giúp cache, checksum, repository proxy và build tái lập hoạt động đáng tin cậy.

Với snapshot hoặc build thử nghiệm, có thể dùng repository snapshot riêng hoặc version có hậu tố pre-release. Không trộn snapshot với release ổn định trong cùng quy trình publish nếu repository có chính sách khác nhau.

## 14. Changelog và chính sách deprecation

`CHANGELOG.md` nên mô tả thay đổi theo từng version, tập trung vào điều người tiêu thụ cần biết:

```markdown
# Changelog

## 1.4.1
- Fixed path handling in the copy-report task.
- Improved diagnostics when an input file is missing.

## 1.4.0
- Added the copy-report task.
- Added the greeting datatype.

## 1.3.0
- Added optional encoding configuration to the hello task.
```

Khi chuẩn bị bỏ một task hoặc thuộc tính, nên có giai đoạn deprecation:

- Giữ API cũ trong một hoặc nhiều minor release nếu có thể.
- Ghi rõ API mới thay thế.
- Phát cảnh báo deprecation ở log khi người dùng vẫn gọi API cũ.
- Cập nhật README và ví dụ.
- Chỉ xóa API cũ trong major release theo chính sách đã công bố.

Một task antlib có thể được sử dụng trong nhiều repository và build pipeline. Việc thông báo deprecation sớm giúp các project tiêu thụ có thời gian cập nhật mà không bị hỏng build đột ngột.

## 15. Xác minh artifact trước khi phát hành

Trước khi đưa JAR vào repository, cần xác minh archive chứa descriptor, class và metadata mong đợi. Có thể dùng:

```sh
jar tf dist/acme-ant-tasks-1.4.0.jar
```

Đọc manifest:

```sh
jar xf dist/acme-ant-tasks-1.4.0.jar META-INF/MANIFEST.MF
```

Tính checksum SHA-256:

```sh
sha256sum dist/acme-ant-tasks-1.4.0.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash .\dist\acme-ant-tasks-1.4.0.jar -Algorithm SHA256
```

Checksum cần được lưu cùng artifact hoặc metadata phát hành và lấy từ binary cuối cùng sau khi đã đóng gói. Nếu JAR thay đổi sau khi tạo checksum, phải tạo lại checksum.

Checksum phát hiện nội dung không khớp với giá trị tham chiếu. Nếu cần xác minh nguồn phát hành, có thể ký artifact hoặc checksum bằng chữ ký số và công bố public key/fingerprint qua kênh đáng tin cậy. Chữ ký số và checksum giải quyết hai mục đích liên quan nhưng khác nhau: checksum so sánh nội dung; chữ ký xác nhận nội dung được ký bởi khóa tương ứng.

## 16. Kiểm thử antlib từ góc nhìn người tiêu thụ

Một JAR có thể chứa đủ file nhưng vẫn không hoạt động nếu descriptor sai, classpath thiếu dependency hoặc task không tương thích với phiên bản Ant. Vì vậy, trước khi phát hành, nên tạo một project tiêu thụ tối thiểu trong thư mục thử nghiệm:

```xml
<project name="antlib-consumer-test"
         default="run"
         xmlns:acme="antlib:com.example.ant">

    <path id="acme.classpath">
        <pathelement location="dist/acme-ant-tasks-1.4.0.jar"/>
        <fileset dir="dist/lib" includes="*.jar"/>
    </path>

    <taskdef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpathref="acme.classpath"/>

    <target name="run">
        <acme:hello message="Antlib consumer test"/>
    </target>

</project>
```

Chạy:

```sh
ant -f consumer-build.xml run
```

Nên thử trên các phiên bản Ant/JDK mà thư viện tuyên bố hỗ trợ. Nếu hỗ trợ nhiều major version của Ant, có thể chạy ma trận kiểm tra trên từng phiên bản. Đừng chỉ thử trong project source của chính thư viện vì classpath phát triển có thể chứa các lớp hoặc dependency không có trong gói phát hành.

## 17. Hướng dẫn người dùng nạp antlib

README của thư viện nên có một hướng dẫn ngắn, chính xác và có thể sao chép:

### Cách A: nạp bằng `-lib`

```sh
ant -lib lib/acme-ant-tasks-1.4.0.jar run
```

Trong buildfile:

```xml
<project name="consumer" xmlns:acme="antlib:com.example.ant">
    <target name="run">
        <acme:hello message="Hello"/>
    </target>
</project>
```

Nếu task library có dependency ngoài, các JAR đó cũng cần được thêm vào classpath của Ant theo cách phù hợp. Có thể truyền nhiều vị trí qua `-lib` theo quy tắc path của hệ điều hành, hoặc cấu hình explicit classpath trong buildfile.

### Cách B: nạp tường minh bằng `<taskdef>`

```xml
<project name="consumer"
         xmlns:acme="antlib:com.example.ant">

    <path id="acme.classpath">
        <pathelement location="tools/acme-ant-tasks-1.4.0.jar"/>
        <fileset dir="tools/acme-dependencies" includes="*.jar"/>
    </path>

    <taskdef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpathref="acme.classpath"/>

    <target name="run">
        <acme:hello message="Hello"/>
    </target>

</project>
```

Cách nạp tường minh giúp buildfile thể hiện dependency của task library ngay trong project. Cách `-lib` có thể thuận tiện khi thư viện được cài ở cấp môi trường build hoặc khi muốn tự động phát hiện antlib descriptor.

## 18. Tổ chức repository và tên artifact

Đối với repository nội bộ, nên dùng tọa độ ổn định và layout có version:

```text
com/example/build/acme-ant-tasks/1.4.0/
├── acme-ant-tasks-1.4.0.jar
├── acme-ant-tasks-1.4.0.pom
├── acme-ant-tasks-1.4.0.jar.sha256
└── metadata theo repository
```

Các nguyên tắc hữu ích:

- Dùng group/organization phản ánh namespace của nhóm phát triển.
- Artifact ID ổn định, không đổi chỉ vì thêm task mới.
- Version được pin trong build consumer.
- Release artifact không bị ghi đè.
- Snapshot và release dùng repository hoặc policy riêng nếu tổ chức yêu cầu.
- Metadata khai báo dependency và license đầy đủ.
- Checksum và chữ ký được phân phối cùng artifact khi chính sách yêu cầu.

## 19. Ví dụ tiêu thụ một version cụ thể trong build khác

Một project consumer có thể pin phiên bản antlib trong property:

```xml
<project name="inventory-app"
         default="build"
         xmlns:acme="antlib:com.example.ant">

    <property name="acme.ant.version" value="1.4.0"/>

    <path id="acme.ant.classpath">
        <pathelement location="tools/acme-ant-tasks-${acme.ant.version}.jar"/>
        <fileset dir="tools/acme-ant-dependencies" includes="*.jar"/>
    </path>

    <taskdef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpathref="acme.ant.classpath"/>

    <target name="build">
        <acme:hello message="Build inventory application"/>
    </target>

</project>
```

Để nâng cấp lên `1.5.0`, consumer cập nhật một property và kiểm tra changelog, dependency, Ant/JDK compatibility trước khi merge. Không dùng tên `latest` để tự động thay đổi task library giữa các lần build.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| JAR phát hành không nhận diện namespace | Descriptor không có trong archive hoặc nằm sai resource path | Kiểm tra `jar tf` và đặt `antlib.xml` đúng theo `antlib:<package>` |
| Task được đăng ký nhưng không tạo được instance | Class task thiếu hoặc dependency không có trong classpath Ant | Kiểm tra classname trong descriptor và toàn bộ task classpath |
| Người dùng phải thêm JAR thủ công dù đã cài thư viện | README không mô tả cách nạp hoặc nhầm classpath ứng dụng với classpath Ant | Cung cấp hướng dẫn `-lib` và `<taskdef classpathref>` |
| Hai project dùng cùng version nhưng nhận binary khác nhau | Repository cho phép ghi đè release artifact | Bật chính sách release bất biến và phát hành version mới khi nội dung thay đổi |
| Consumer lỗi sau khi nâng version minor | Thay đổi thực tế phá tương thích nhưng version policy không phản ánh | Rà soát API XML và Java, tăng major nếu thay đổi không tương thích |
| Consumer không resolve được dependency của task | POM/Ivy metadata thiếu dependency hoặc scope sai | Khai báo đầy đủ dependency runtime của task library |
| Build phụ thuộc phiên bản Ant trên máy developer | Ant API hoặc task behavior không được pin/ghi rõ | Ghi Ant tối thiểu/tối đa được hỗ trợ và kiểm thử ma trận phiên bản |
| JAR chạy trên máy phát triển nhưng lỗi trong CI | Classpath phát triển có dependency không nằm trong gói phát hành | Kiểm thử bằng consumer project sạch chỉ dùng artifact đã phát hành |
| Checksum không khớp sau publish | Checksum được tạo trước khi JAR hoàn tất hoặc binary bị thay | Tạo checksum từ đúng artifact cuối và kiểm tra lại file repository trả về |
| Changelog không phản ánh thay đổi | Release không có quy trình cập nhật ghi chú | Cập nhật changelog cùng commit phát hành và rà soát trước khi publish |

## 21. Checklist phát hành antlib

- [ ] Descriptor `antlib.xml` có đúng resource path và khai báo các task/datatype cần phát hành.
- [ ] JAR chứa đầy đủ class, descriptor và resource cần thiết.
- [ ] Phiên bản được đặt tập trung và xuất hiện trong tên artifact/manifest/metadata.
- [ ] Chính sách version phản ánh đúng thay đổi tương thích hoặc không tương thích.
- [ ] Dependency của task library được phân biệt với dependency của ứng dụng.
- [ ] `ant.jar` được dùng như API môi trường biên dịch/runtime, không bị nhúng bản sao vào JAR antlib.
- [ ] README hướng dẫn cách nạp namespace, classpath và dependency.
- [ ] Changelog ghi rõ tính năng, sửa lỗi và breaking change.
- [ ] License, NOTICE và metadata repository được cập nhật.
- [ ] JAR được kiểm tra nội dung và manifest.
- [ ] Checksum được tạo từ binary cuối; chữ ký số được dùng nếu chính sách yêu cầu.
- [ ] Consumer test chạy bằng artifact phát hành trong classpath sạch.
- [ ] Phiên bản Ant/JDK hỗ trợ được ghi rõ và đã kiểm tra.
- [ ] Release artifact là bất biến; lỗi sau phát hành được sửa bằng version mới.

## 22. Kết luận

Đóng gói antlib là quá trình biến custom task, datatype và macro thành một JAR có descriptor đúng vị trí, dependency rõ ràng và giao diện namespace ổn định. Quản lý version theo chính sách tương thích, ghi metadata trong manifest và repository, duy trì changelog, xác minh checksum, rồi thử artifact từ một project consumer sạch sẽ giúp thư viện được phân phối và nâng cấp an toàn giữa nhiều build Ant.
