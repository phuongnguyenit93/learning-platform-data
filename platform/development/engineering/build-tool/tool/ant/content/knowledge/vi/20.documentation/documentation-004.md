# Tạo thông tin phiên bản và tài liệu mô tả gói phân phối

Khi đóng gói một ứng dụng Java bằng Apache Ant, người nhận cần biết chính xác họ đang sử dụng phiên bản nào, gói được tạo cho mục đích gì, cần môi trường nào và phải cài đặt hoặc chạy ra sao. Những thông tin này nên đi cùng artifact để người dùng và hệ thống triển khai có thể nhận diện gói mà không cần mở mã nguồn của dự án.

Trong Ant, có thể tạo thông tin phiên bản ở nhiều vị trí:

- Manifest bên trong JAR, dùng các thuộc tính như `Implementation-Version`, `Implementation-Title` và `Main-Class`.
- File metadata riêng, chẳng hạn `version.properties` hoặc `VERSION.txt`, để công cụ triển khai và người vận hành đọc.
- Tài liệu phát hành như `README`, `INSTALL`, `RELEASE-NOTES`, `LICENSE` và `NOTICE` được đưa vào gói phân phối.
- Archive ZIP hoặc TAR chứa JAR, thư viện phụ thuộc, cấu hình mẫu và tài liệu.

Một nguyên tắc quan trọng là lấy phiên bản từ một nguồn duy nhất rồi tái sử dụng giá trị đó ở manifest, file metadata và tên gói. Nếu mỗi nơi tự ghi một phiên bản, các thông tin có thể lệch nhau sau vài lần phát hành.

## 1. Tập trung thông tin phiên bản trong một file

Có thể lưu thông tin phát hành trong `version.properties` ở thư mục gốc dự án:

```properties
app.name=inventory-service
app.version=2.4.0
app.vendor=Example Engineering
app.description=Inventory management service
app.main.class=com.example.inventory.Main
```

Nạp file này bằng task `<property>`:

```xml
<project name="inventory-service" default="dist">
    <property file="version.properties"/>

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.stage.dir" location="${build.dir}/dist-stage"/>
    <property name="dist.dir" location="${build.dir}/distribution"/>
</project>
```

Từ thời điểm nạp file, Ant có thể thay thế `${app.name}`, `${app.version}` và các property khác trong task. Property của Ant là bất biến sau khi đã được thiết lập: nếu cùng một property đã có giá trị trước đó, lệnh `<property>` tiếp theo không ghi đè nó. Điều này cho phép người chạy build truyền giá trị từ command line để chọn phiên bản hoặc vendor cho một lần build, miễn là property chưa bị đặt trước đó.

Ví dụ:

```shell
ant -Dapp.version=2.4.1 dist
```

Khi chạy theo cách này, `app.version` từ command line được ưu tiên vì property đã tồn tại trước lúc Ant đọc `version.properties`. Hãy quyết định rõ dự án có cho phép override phiên bản phát hành từ command line hay không; với build release, có thể muốn version file là nguồn duy nhất để tránh tạo nhầm gói.

Nên phân biệt:

| Thông tin | Ví dụ | Mục đích |
|---|---|---|
| Application version | `2.4.0` | Nhận diện phiên bản sản phẩm |
| Build number | `build-1842` | Nhận diện một lần chạy CI cụ thể |
| Revision/commit | `a1b2c3d` | Truy ngược mã nguồn đã tạo artifact |
| Build time | `2026-11-12T10:00:00Z` | Hỗ trợ điều tra và vận hành |

Application version thường ổn định trong một bản phát hành. Build number, revision và thời điểm build bổ sung khả năng truy xuất nguồn gốc. Không nên dùng timestamp làm thay thế version sản phẩm, vì mỗi lần chạy lại sẽ tạo một giá trị khác dù mã nguồn không đổi.

## 2. Tạo JAR manifest bằng task `<manifest>`

Manifest là file metadata nằm trong JAR tại đường dẫn `META-INF/MANIFEST.MF`. Java runtime và các công cụ đóng gói có thể dùng manifest để biết lớp khởi chạy, classpath và thông tin phiên bản của package.

Task `<manifest>` tạo file manifest độc lập. Ví dụ:

```xml
<target name="write-manifest">
    <mkdir dir="${build.dir}/metadata"/>

    <manifest file="${build.dir}/metadata/MANIFEST.MF"
              mode="replace">
        <attribute name="Built-By" value="${user.name}"/>
        <attribute name="Implementation-Title" value="${app.name}"/>
        <attribute name="Implementation-Version" value="${app.version}"/>
        <attribute name="Implementation-Vendor" value="${app.vendor}"/>
        <attribute name="Specification-Title" value="${app.name}"/>
        <attribute name="Specification-Version" value="${app.version}"/>
        <attribute name="Specification-Vendor" value="${app.vendor}"/>
    </manifest>
</target>
```

Task có hai chế độ chính:

- `mode="replace"` tạo manifest mới theo nội dung được khai báo; đây là mặc định.
- `mode="update"` đọc manifest hiện có rồi cập nhật hoặc bổ sung các thuộc tính được chỉ định.

`file` là đường dẫn tới manifest cần tạo hoặc cập nhật. Mỗi `<attribute>` đại diện cho một header trong main section. Có thể dùng `<section>` để gắn metadata riêng cho một package hoặc một vùng nội dung:

```xml
<manifest file="${build.dir}/metadata/MANIFEST.MF" mode="replace">
    <attribute name="Built-By" value="${user.name}"/>

    <section name="com/example/inventory/">
        <attribute name="Specification-Title" value="Inventory API"/>
        <attribute name="Specification-Version" value="${app.version}"/>
        <attribute name="Implementation-Title" value="Inventory Service"/>
        <attribute name="Implementation-Version" value="${app.version}"/>
        <attribute name="Implementation-Vendor" value="${app.vendor}"/>
    </section>
</manifest>
```

Các thuộc tính trong main section áp dụng chung; section có tên cho phép cung cấp metadata cụ thể hơn cho một package hoặc entry. Tên thuộc tính manifest phải theo cú pháp header hợp lệ. Ant xử lý việc xuống dòng tiếp nối theo quy tắc manifest của JAR; không tự cắt chuỗi dài bằng cách chèn newline tùy ý.

## 3. Nhúng manifest vào JAR bằng `<jar>`

Nếu chỉ cần tạo manifest để đưa ngay vào JAR, có thể khai báo `<manifest>` lồng bên trong `<jar>`. Cách này giữ thông tin đóng gói ở cùng task:

```xml
<target name="jar" depends="compile">
    <mkdir dir="${build.dir}/libs"/>

    <jar destfile="${build.dir}/libs/${app.name}-${app.version}.jar"
         basedir="${classes.dir}">
        <manifest>
            <attribute name="Main-Class" value="${app.main.class}"/>
            <attribute name="Implementation-Title" value="${app.name}"/>
            <attribute name="Implementation-Version" value="${app.version}"/>
            <attribute name="Implementation-Vendor" value="${app.vendor}"/>
        </manifest>
    </jar>
</target>
```

`Main-Class` cho phép khởi chạy JAR theo dạng:

```shell
java -jar inventory-service-2.4.0.jar
```

Nếu manifest bị bỏ qua, Ant vẫn tạo một manifest đơn giản cho JAR. Manifest lồng trong `<jar>` tương tự task `<manifest>`, nhưng không khai báo `file` và `mode` vì manifest được ghi trực tiếp vào archive. Nếu dùng cả manifest file ngoài qua thuộc tính `manifest` của `<jar>` và manifest lồng, Ant sẽ merge chúng theo quy tắc của task.

### Truyền classpath cho executable JAR

`Main-Class` chỉ chỉ định lớp khởi chạy; nó không tự đóng gói hoặc tìm tất cả thư viện bên ngoài. Nếu ứng dụng cần các JAR phụ thuộc đặt cạnh JAR chính trong thư mục `lib`, manifest có thể khai báo `Class-Path` với đường dẫn tương đối từ vị trí JAR:

```xml
<path id="runtime.dependencies">
    <fileset dir="${dist.stage.dir}/lib">
        <include name="*.jar"/>
    </fileset>
</path>

<manifestclasspath property="jar.classpath"
                    jarfile="${dist.stage.dir}/${app.name}-${app.version}.jar">
    <classpath refid="runtime.dependencies"/>
</manifestclasspath>

<jar destfile="${dist.stage.dir}/${app.name}-${app.version}.jar"
     basedir="${classes.dir}">
    <manifest>
        <attribute name="Main-Class" value="${app.main.class}"/>
        <attribute name="Class-Path" value="${jar.classpath}"/>
        <attribute name="Implementation-Version" value="${app.version}"/>
    </manifest>
</jar>
```

Task `<manifestclasspath>` tính chuỗi classpath tương đối dựa trên vị trí JAR và các phần tử trong path. Thư mục và vị trí thực tế của dependency khi triển khai phải khớp với cấu trúc được dùng lúc tính toán. Nếu classpath chứa đường dẫn không tồn tại trong gói phát hành, `java -jar` có thể khởi chạy được lớp chính nhưng thất bại khi nạp class phụ thuộc.

Không thêm `Class-Path` nếu ứng dụng được chạy bằng script hoặc launcher khác đã tự xây classpath. Hãy chọn một cách quản lý runtime classpath rõ ràng.

## 4. Tạo file version metadata riêng

Manifest phù hợp với thông tin gắn với JAR. Một file metadata riêng hữu ích khi script triển khai, hệ thống kiểm kê hoặc người vận hành cần đọc phiên bản mà không phải mở archive.

Có thể tạo file properties bằng `<echo>`:

```xml
<target name="write-version-file">
    <mkdir dir="${build.dir}/metadata"/>

    <echo file="${build.dir}/metadata/version.properties"
          encoding="UTF-8">app.name=${app.name}
app.version=${app.version}
app.vendor=${app.vendor}
app.main.class=${app.main.class}
</echo>
</target>
```

Ứng dụng Java hoặc script triển khai có thể đọc file này như properties thông thường. Nếu cần lưu thêm commit hoặc build number, hãy khai báo các property đó một cách tường minh rồi ghi chúng vào cùng file.

Ví dụ Java đọc metadata:

```java
Properties version = new Properties();
try (InputStream input = Files.newInputStream(
        Path.of("metadata", "version.properties"))) {
    version.load(input);
}

System.out.println("Application: " + version.getProperty("app.name"));
System.out.println("Version: " + version.getProperty("app.version"));
```

Đường dẫn ở ví dụ Java được phân giải từ working directory. Nếu metadata được đặt bên trong JAR, hãy đọc nó qua classpath resource thay vì `Files.newInputStream` với đường dẫn file ngoài.

Với file văn bản dành cho người đọc, có thể tạo `VERSION.txt`:

```xml
<echo file="${dist.stage.dir}/VERSION.txt" encoding="UTF-8">${app.name}
Version: ${app.version}
Vendor: ${app.vendor}
</echo>
```

Không nên duy trì cả `version.properties`, `VERSION.txt` và manifest bằng các con số viết tay riêng biệt. Hãy sinh chúng từ cùng bộ Ant properties.

## 5. Viết tài liệu mô tả gói phân phối

Một gói phân phối nên tự giải thích được nội dung và cách sử dụng. Tài liệu đi kèm thường gồm:

| File | Nội dung nên có |
|---|---|
| `README.md` | Tên sản phẩm, mô tả ngắn, phiên bản, chức năng, yêu cầu môi trường, cách cài đặt và chạy |
| `INSTALL.md` hoặc `INSTALL.txt` | Các bước cài đặt, cấu hình, quyền truy cập và kiểm tra sau cài đặt |
| `RELEASE-NOTES.md` | Tính năng mới, lỗi đã sửa, thay đổi có thể ảnh hưởng người dùng và vấn đề đã biết |
| `LICENSE` | Điều khoản giấy phép áp dụng cho phần mềm được phân phối |
| `NOTICE` | Thông báo bản quyền hoặc ghi nhận bắt buộc theo các dependency được phân phối, nếu có |
| `config/*.example` | Cấu hình mẫu không chứa mật khẩu, token hoặc thông tin bí mật |
| `VERSION.txt` | Phiên bản chính xác của artifact trong gói |

Nội dung tài liệu cần khớp với gói thực tế. Nếu README hướng dẫn chạy `bin/start.sh` nhưng archive không chứa script đó, gói phân phối chưa hoàn chỉnh. Tương tự, không nên ghi một dependency vào hướng dẫn cài đặt nếu dependency đó đã được đóng gói sẵn mà người dùng không cần tải riêng.

Một README tối thiểu có thể được tổ chức như sau:

```markdown
# Inventory Service

Version: 2.4.0

## Overview
Inventory management service for internal applications.

## Requirements
- JDK 21 or compatible runtime
- Access to the configured database

## Distribution contents
- `inventory-service-2.4.0.jar`: application
- `lib/`: runtime libraries
- `config/application.properties.example`: sample configuration
- `VERSION.txt`: release metadata

## Configure
Copy the sample configuration and set environment-specific values.
Do not commit production credentials into the configuration file.

## Run
Use the deployment script or the documented Java command.

## Release notes
See `RELEASE-NOTES.md`.
```

Trong dự án thật, README và release notes nên là file do nhóm phát triển quản lý. Ant chỉ cần sao chép chúng vào đúng vị trí trong archive; không nên tự ghi đè nội dung tài liệu đã được biên tập.

## 6. Tổ chức staging directory và tạo gói ZIP

Nên dựng một thư mục staging có cấu trúc giống hệt gói sau khi giải nén. Sau đó, nén toàn bộ staging directory thành một archive. Cách làm này giúp kiểm tra cấu trúc trước khi phát hành và tránh đưa nhầm file build nội bộ vào gói.

Ví dụ cấu trúc mong muốn:

```text
inventory-service-2.4.0/
├── inventory-service-2.4.0.jar
├── VERSION.txt
├── README.md
├── RELEASE-NOTES.md
├── LICENSE
├── NOTICE
├── config/
│   └── application.properties.example
└── lib/
    ├── database-driver.jar
    └── logging-api.jar
```

Build file có thể tạo cấu trúc này như sau:

```xml
<target name="stage-distribution" depends="jar">
    <delete dir="${dist.stage.dir}"/>
    <mkdir dir="${dist.stage.dir}/config"/>
    <mkdir dir="${dist.stage.dir}/lib"/>

    <copy file="${build.dir}/libs/${app.name}-${app.version}.jar"
          todir="${dist.stage.dir}"/>

    <copy file="README.md" todir="${dist.stage.dir}"/>
    <copy file="RELEASE-NOTES.md" todir="${dist.stage.dir}"/>
    <copy file="LICENSE" todir="${dist.stage.dir}"/>
    <copy file="NOTICE" todir="${dist.stage.dir}"/>

    <copy file="config/application.properties.example"
          todir="${dist.stage.dir}/config"/>

    <copy todir="${dist.stage.dir}/lib">
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
    </copy>

    <echo file="${dist.stage.dir}/VERSION.txt" encoding="UTF-8">${app.name}
Version: ${app.version}
Vendor: ${app.vendor}
</echo>
</target>

<target name="dist" depends="stage-distribution">
    <mkdir dir="${dist.dir}"/>
    <zip destfile="${dist.dir}/${app.name}-${app.version}.zip"
         basedir="${dist.stage.dir}"
         duplicate="fail"/>
</target>
```

Trong ví dụ, `basedir` của `<zip>` là thư mục staging, vì vậy các entry trong archive bắt đầu trực tiếp bằng các file và thư mục bên trong staging. Nếu muốn archive chứa một thư mục gốc `inventory-service-2.4.0/`, hãy đặt staging directory bên trong một thư mục cha rồi dùng `<zip>` trên thư mục cha, hoặc dùng `zipfileset` với `prefix` phù hợp.

`duplicate="fail"` giúp build dừng nếu nhiều fileset đưa cùng một đường dẫn entry vào archive. Đây là lựa chọn hữu ích khi cần phát hiện file bị đóng gói trùng. `<zip>` hỗ trợ fileset, include và exclude pattern; chỉ đưa các file cần cho người sử dụng vào gói phát hành.

## 7. Tạo checksum và kiểm tra artifact phát hành

Sau khi tạo archive, có thể sinh checksum để người nhận kiểm tra file tải xuống có bị thay đổi hay không. Ví dụ dùng task `<checksum>` của Ant:

```xml
<target name="checksum" depends="dist">
    <checksum file="${dist.dir}/${app.name}-${app.version}.zip"
              algorithm="SHA-256"
              fileext=".sha256"/>
</target>
```

Task tạo file checksum cạnh archive theo phần mở rộng được chỉ định. Người nhận cần dùng cùng thuật toán để tính lại hash trên file tải xuống và so sánh với giá trị phát hành. Checksum phát hiện lỗi truyền tải hoặc thay đổi nội dung; nó không chứng minh nguồn phát hành đáng tin cậy nếu checksum được tải từ cùng một nguồn không xác thực. Với nhu cầu xác thực nguồn gốc, cần một cơ chế ký số hoặc kênh phát hành được bảo vệ.

Trước khi công bố gói, có thể kiểm tra các điểm sau bằng quy trình phát hành:

- Tên archive chứa đúng tên sản phẩm và phiên bản.
- Manifest trong JAR có `Main-Class` và version metadata như dự kiến.
- File `VERSION.txt` trùng với manifest và tên archive.
- README, release notes, license, notice và cấu hình mẫu có mặt.
- Không có file cấu hình chứa mật khẩu, token hoặc khóa bí mật.
- Các thư viện runtime cần thiết đã được đưa vào đúng thư mục.
- Có thể giải nén archive và chạy ứng dụng theo hướng dẫn.
- Checksum được tạo sau khi archive đã hoàn tất.

## 8. Những lỗi thường gặp

1. **Manifest và tên JAR dùng hai phiên bản khác nhau.** Lấy cả hai từ cùng `${app.version}` trong một file properties, không viết version riêng trong từng task.
2. **Nghĩ rằng `Main-Class` tự thêm dependency vào JAR.** Thuộc tính này chỉ chỉ định lớp khởi chạy. Hãy đóng gói thư viện cần thiết hoặc khai báo `Class-Path`/launcher phù hợp.
3. **Tạo manifest riêng nhưng quên gắn vào JAR.** Task `<manifest>` chỉ tạo file; hãy dùng thuộc tính `manifest` trên `<jar>` hoặc khai báo manifest lồng trong task `<jar>`.
4. **Đặt `file` hoặc `mode` trong manifest lồng.** Manifest lồng trong `<jar>` không dùng hai thuộc tính đó; chúng thuộc task `<manifest>` độc lập.
5. **Dùng `mode="update"` khi muốn tạo lại hoàn toàn.** Update giữ các thuộc tính đã có mà không bị thay thế. Dùng `replace` khi muốn manifest phản ánh chính xác tập metadata được khai báo cho lần build này.
6. **Tự xuống dòng trong giá trị manifest.** Ant tự xử lý continuation theo đặc tả JAR. Chuỗi dài được wrap không có nghĩa file manifest bị hỏng.
7. **Đóng gói cả thư mục `build` hoặc file bí mật.** Dùng staging directory và fileset có include rõ ràng để kiểm soát nội dung phát hành.
8. **Tài liệu không khớp cấu trúc archive.** Kiểm tra hướng dẫn chạy và danh sách file với staging directory thực tế trước khi phát hành.
9. **Checksum được tạo trước khi archive thay đổi.** Tạo checksum sau bước ZIP cuối cùng; nếu archive được đóng gói lại, phải tạo lại checksum.
10. **Override version ngoài ý muốn.** Ant properties là immutable và giá trị đặt trước có thể thắng giá trị trong file. Kiểm soát đầu vào command line của release build.

## 9. Tổ chức target cho quy trình phát hành

Một chuỗi target dễ hiểu có thể chia theo trách nhiệm:

```text
load-version
     |
     v
  compile
     |
     v
    jar  --------> MANIFEST.MF
     |
     v
stage-distribution ----> README / RELEASE-NOTES / LICENSE / config
     |
     v
    dist --------------> product-version.zip
     |
     v
  checksum ------------> product-version.zip.sha256
```

Target `load-version` thường được thực hiện khi Ant đọc build file và nạp `version.properties`. `compile` tạo class files; `jar` đóng gói code cùng manifest; `stage-distribution` tập hợp artifact và tài liệu; `dist` tạo archive; `checksum` tạo hash cuối cùng. Các target có thể được tách nhỏ hơn theo quy mô dự án, nhưng dependency giữa chúng phải bảo đảm metadata và checksum luôn được tạo sau artifact mà chúng mô tả.

## Tài liệu tham khảo

- [Apache Ant Manual — Manifest Task](https://ant.apache.org/manual/Tasks/manifest.html): tạo hoặc cập nhật manifest, attribute và section.
- [Apache Ant Manual — JAR Task](https://ant.apache.org/manual/Tasks/jar.html): tạo JAR, dùng manifest bên ngoài hoặc khai báo manifest lồng.
- [Apache Ant Manual — Manifest Class-Path Task](https://ant.apache.org/manual/Tasks/manifestclasspath.html): tính classpath tương đối để đưa vào manifest.
- [Apache Ant Manual — ZIP Task](https://ant.apache.org/manual/Tasks/zip.html): tạo archive từ basedir và fileset, kiểm soát file trùng.
- [Apache Ant Manual — Checksum Task](https://ant.apache.org/manual/Tasks/checksum.html): tạo checksum cho artifact phát hành.
