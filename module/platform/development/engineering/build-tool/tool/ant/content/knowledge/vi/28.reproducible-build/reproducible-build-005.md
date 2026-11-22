# Kiểm soát thông tin phiên bản sinh tự động và đường dẫn tuyệt đối trong Apache Ant

Trong chủ đề **Build Tool Ant**, bài học này giải quyết một nguyên nhân thường gặp khiến **build tái lập (reproducible build)** thất bại: cùng mã nguồn và cấu hình nhưng mỗi lần chạy Apache Ant lại tạo ra JAR/ZIP khác nhau, vì thông tin phiên bản được sinh từ trạng thái lần chạy hoặc vì đường dẫn tuyệt đối trên máy build bị ghi vào sản phẩm.

Mục tiêu không chỉ là chương trình chạy giống nhau. Với cùng đầu vào đã chốt và môi trường đã kiểm soát, hai lần build độc lập phải có thể tạo ra **cùng chuỗi byte**, từ đó có cùng SHA-256. Để thực hiện được, cần phân biệt dữ liệu mô tả **phiên bản của mã nguồn** với dữ liệu mô tả **phiên chạy CI**, đồng thời biết đường dẫn nào chỉ phục vụ Ant thao tác với file và đường dẫn nào thực sự được lưu vào artifact.

## 1. Hai nhóm nguồn gây sai khác

| Nguồn biến thiên | Ví dụ | Vì sao ảnh hưởng tính tái lập? | Cách xử lý |
| --- | --- | --- | --- |
| Thời gian hiện tại | `<tstamp/>`, `new Date()` trong code generator | Hai lần build khác phút/giây | Chọn thời điểm cố định từ commit/release |
| Bộ đếm lần chạy | `<buildnumber/>`, CI run number | Giá trị tăng dù source không đổi | Tách khỏi metadata trong artifact |
| Thông tin người/máy | `user.name`, hostname, `user.home` | Khác giữa local và CI | Không nhúng vào JAR/resource |
| Đường dẫn checkout | `${basedir}`, `${ant.file}` | Checkout ở hai thư mục khác nhau | Dùng tên logic tương đối trong artifact |
| File được đóng gói | Timestamp, thứ tự entry, quyền file | ZIP/JAR lưu metadata ngoài nội dung file | Chuẩn hóa timestamp, ổn định input và toolchain |
| Tool sinh mã/biên dịch | Annotation processor, compiler, dependency | Có thể ghi ngày, path hoặc thay đổi bytecode | Cố định công cụ và cấu hình sinh |

Ví dụ cùng commit được build ở `C:\Users\Lan\projects\demo` và `/home/runner/work/demo`. Nếu manifest chứa `Build-Directory: ...`, hai bản JAR sẽ khác byte dù `Demo.class` giống nhau. Một trường hợp khác: manifest chỉ khác `Build-Time` do thời gian chạy, hoặc nội dung giống nhau nhưng timestamp của các entry ZIP khác nhau.

**Phân biệt quan trọng:** Ant sử dụng đường dẫn tuyệt đối để *tìm* file trong lúc thực thi là hoàn toàn bình thường. Vấn đề xuất hiện khi giá trị đó bị *ghi vào* resource, source sinh tự động, manifest hoặc metadata đóng gói.

## 2. Thiết kế nguồn sự thật cho phiên bản

Một dự án có thể cần ba thông tin phát hành:

```properties
app.version=1.4.2
source.revision=8c0e5a4f7b0123456789abcdef0123456789abcd
build.instant=2025-01-01T00:00:00Z
```

Ý nghĩa của từng trường:

- **`app.version`:** phiên bản sản phẩm được chốt từ file cấu hình release hoặc tag có quy tắc; không phụ thuộc giờ và số lượt build.
- **`source.revision`:** commit/snapshot đầu vào; phải khớp với mã thực sự được biên dịch. SHA trong ví dụ chỉ là dữ liệu minh họa.
- **`build.instant`:** mốc thời gian *cố định của nguồn hoặc release*, biểu diễn ISO-8601 UTC; không phải đồng hồ của agent hiện tại.

Có thể commit `release.properties` hoặc để pipeline truyền giá trị qua `ant -Dapp.version=... -Dsource.revision=... -Dbuild.instant=... release`. Điều kiện là mỗi giá trị phải có **một nguồn quyết định rõ ràng**. Tránh sinh Java class từ một file, rồi sinh manifest từ biến môi trường khác.

Ant property nhìn chung **bất biến sau lần gán đầu tiên**. Property dòng lệnh `-D...` có thể ưu tiên giá trị được nạp bằng `<property file="..."/>`. Vì vậy thứ tự nạp và quyền ghi đè cần là một phần của hợp đồng release.

### Vì sao `<buildnumber/>` dễ gây lỗi?

```xml
<!-- Không thích hợp khi số lần chạy quyết định byte artifact -->
<buildnumber file="build.number"/>
<jar destfile="dist/demo.jar">
    <manifest>
        <attribute name="Implementation-Version"
                   value="1.4.2-${build.number}"/>
    </manifest>
</jar>
```

Task `buildnumber` đọc một bộ đếm, tăng số, rồi ghi ngược vào file. Chạy lại cùng commit có thể tạo phiên bản `1.4.2-37`, rồi `1.4.2-38`. Nếu cần biết lần CI nào đã sản xuất artifact, lưu `CI_RUN_ID` trong log, kết quả workflow hoặc attestation/provenance liên kết với digest của artifact. Danh tính sản phẩm và danh tính lượt chạy là hai thông tin khác nhau.

Tương tự, các giá trị như `git describe --dirty` có thể thay đổi theo working tree; shallow clone có thể không mang đủ tag. Nếu dùng Git làm nguồn phiên bản, phải quy định rõ commit, tag, trạng thái sạch và cách xử lý thiếu dữ liệu.

## 3. Kiểm soát timestamp ở hai lớp

### 3.1. Timestamp xuất hiện trong nội dung

`<tstamp/>` thông thường gán `DSTAMP`, `TSTAMP` và `TODAY` dựa trên thời gian hiện tại. Đưa trực tiếp các property này vào `MANIFEST.MF` hoặc `build-info.properties` sẽ làm nội dung thay đổi theo lúc build:

```xml
<!-- Thời gian thay đổi theo lần chạy -->
<tstamp/>
<echo message="Build at ${DSTAMP}-${TSTAMP}"/>
```

Nếu cần định dạng một mốc cố định, Ant 1.10.2+ hỗ trợ `ant.tstamp.now.iso`:

```xml
<property name="ant.tstamp.now.iso"
          value="2025-01-01T00:00:00Z"/>
<tstamp>
    <format property="build.time.utc"
            pattern="yyyy-MM-dd'T'HH:mm:ss'Z'"
            timezone="UTC"
            locale="en,US"/>
</tstamp>
```

Khi giá trị đầu vào cố định, `build.time.utc` cũng cố định. Ghi rõ timezone và locale giúp việc định dạng không phụ thuộc thiết lập ngôn ngữ/múi giờ trên máy build.

Ant có các cơ chế liên quan:

- Từ **1.10.2**, `ant.tstamp.now` nhận Unix epoch **tính bằng giây**, còn `ant.tstamp.now.iso` nhận chuỗi ISO-8601.
- Từ **1.10.8**, `<tstamp>` nhận biết `SOURCE_DATE_EPOCH` từ môi trường nếu được đặt.
- Từ **1.10.18**, khi sử dụng `SOURCE_DATE_EPOCH`, timezone mặc định của `tstamp` là UTC; có thể và nên chỉ định tường minh khi format đầu ra cần ổn định.

Chọn một cơ chế làm nguồn thời gian; đừng đặt các giá trị mâu thuẫn giữa property và môi trường. Nếu không cần trường thời gian trong metadata sản phẩm, đơn giản nhất là **không tạo trường đó**.

### 3.2. Timestamp của entry trong JAR/ZIP

Ngay cả khi file `MANIFEST.MF` giống byte, JAR vẫn có thể khác vì ZIP chứa timestamp cho các entry như `Demo.class`, `META-INF/MANIFEST.MF` và resource. Từ Ant **1.10.2**, task `jar` và `zip` có thuộc tính `modificationtime` để đặt một thời điểm chung:

```xml
<jar destfile="dist/demo.jar"
     basedir="build/classes"
     modificationtime="2025-01-01T00:00:00Z"
     update="false"
     duplicate="fail"/>
```

`modificationtime` chỉ điều khiển thời gian lưu trong archive; nó không sửa các chuỗi ngày giờ đã có trong resource hoặc Java class. Cần xử lý **cả nội dung file và metadata của ZIP**.

Một bẫy về đơn vị: `SOURCE_DATE_EPOCH` và `ant.tstamp.now` dùng số **giây**, trong khi `modificationtime`, khi truyền dưới dạng **số**, hiểu là **mili giây**. Không đưa thẳng một số epoch vào hai nơi rồi cho rằng đó là cùng thời điểm. Có thể dùng chung chuỗi ISO-8601 có timezone.

ZIP có độ phân giải thời gian truyền thống khoảng **2 giây**. Thuộc tính `roundup` của Ant kiểm soát cách làm tròn; chọn một mốc có giây chẵn, nhất quán giúp dễ kiểm chứng. Thứ tự entry, quyền file và cách nén vẫn là các yếu tố khác cần kiểm soát.

## 4. Đường dẫn tuyệt đối trong Apache Ant

Hai khai báo này có ý nghĩa khác nhau:

```xml
<!-- Ant chuyển thành đường dẫn tuyệt đối theo basedir -->
<property name="root.abs" location="."/>

<!-- Giữ nguyên chuỗi tương đối, có ý nghĩa logic -->
<property name="source.logical" value="src/main/java"/>
```

Theo tài liệu task `property`, `location` mặc định chuyển path thành dạng tuyệt đối; `value` giữ giá trị được đưa vào. Các giá trị dựng sẵn `basedir` và `ant.file` cũng thường chứa đường dẫn tuyệt đối.

**Ví dụ đưa thông tin máy vào manifest:**

```xml
<jar destfile="dist/demo.jar" basedir="build/classes">
    <manifest>
        <attribute name="Build-Directory" value="${basedir}"/>
        <attribute name="Built-By" value="${user.name}"/>
    </manifest>
</jar>
```

**Ví dụ dùng thông tin nguồn ổn định hơn:**

```xml
<jar destfile="dist/demo.jar" basedir="build/classes">
    <manifest>
        <attribute name="Implementation-Version"
                   value="${app.version}"/>
        <attribute name="SCM-Revision"
                   value="${source.revision}"/>
        <attribute name="Source-Layout"
                   value="src/main/java"/>
    </manifest>
</jar>
```

`Source-Layout` là một tên logic trong repository, không phải thư mục checkout trên máy. Nếu ứng dụng không cần nó, bỏ hẳn thuộc tính này.

Nguyên tắc làm việc với đường dẫn:

1. **Cho phép task dùng path vật lý:** `srcdir`, `destdir`, `file`, `todir` có thể được Ant phân giải từ `basedir` mà không làm nhiễm artifact.
2. **Tên trong artifact phải độc lập máy:** dùng tên classpath/resource như `META-INF/build-info.properties` hoặc `config/app.yml`, dùng dấu `/` khi định nghĩa tên logic.
3. **Đặt gốc tập file cụ thể:** `<fileset dir="src">`, `<zipfileset dir="...">` giữ đường dẫn entry tương đối theo gốc đã chọn. Tránh đóng gói toàn bộ checkout, cache, `.git` và output cũ.
4. **Xem cả các bước sinh file:** annotation processor, template, task `echo`, `copy` có filter, trình tạo báo cáo có thể ghi `user.home`, `java.io.tmpdir` hoặc `ant.file`.
5. **Không sửa nhầm biểu hiện bên ngoài:** log in path tuyệt đối không làm JAR khác byte nếu chuỗi đó không được ghi vào sản phẩm.

Ant cũng hỗ trợ `<property location="..." relative="true" basedir="..."/>` để lấy đường dẫn tương đối. Với output cần dùng qua Windows/Linux, vẫn phải xác định cách chuẩn hóa dấu phân cách; tên logic đã biết trước thường đơn giản và đáng tin cậy hơn.

## 5. Ví dụ đầy đủ: sinh version metadata từ đầu vào ổn định

Ví dụ sau dùng **Ant 1.10.2+** và JDK 17+ (cùng bản JDK cho hai môi trường so sánh). Cấu trúc:

```text
repro-demo/
├── build.xml
├── release.properties
├── metadata/
│   └── build-info.properties.in
└── src/
    └── com/example/Demo.java

# build/ và dist/ là output được sinh khi chạy Ant.
```

**File `release.properties`** — các giá trị phát hành:

```properties
app.version=1.4.2
source.revision=8c0e5a4f7b0123456789abcdef0123456789abcd
build.instant=2025-01-01T00:00:00Z
```

Trong thực tế, revision phải là SHA thật của source đang được build; ví dụ ở đây chỉ mô tả dữ liệu mẫu.

**File `metadata/build-info.properties.in`** — template text:

```properties
version=@VERSION@
revision=@REVISION@
buildTime=@BUILD_TIME@
```

**File `src/com/example/Demo.java`** — class tối thiểu:

```java
package com.example;

public final class Demo {
    private Demo() {}

    public static void main(String[] args) {
        System.out.println("Reproducible Ant example");
    }
}
```

**File `build.xml`** — dùng chung đầu vào cho resource, manifest và timestamp ZIP:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="repro-demo" default="release" basedir=".">

    <property name="src.dir" value="src"/>
    <property name="build.dir" value="build"/>
    <property name="classes.dir" value="${build.dir}/classes"/>
    <property name="dist.dir" value="dist"/>

    <!-- -D... có thể cung cấp metadata phát hành trước file. -->
    <property file="release.properties"/>

    <target name="validate">
        <fail unless="app.version"
              message="Missing app.version"/>
        <fail unless="source.revision"
              message="Missing source.revision"/>
        <fail unless="build.instant"
              message="Missing build.instant"/>

        <!-- fail unless chỉ kiểm tra property tồn tại;
             kiểm tra riêng trường hợp chuỗi rỗng. -->
        <condition property="metadata.is.empty">
            <or>
                <equals arg1="${app.version}" arg2="" trim="true"/>
                <equals arg1="${source.revision}" arg2="" trim="true"/>
                <equals arg1="${build.instant}" arg2="" trim="true"/>
            </or>
        </condition>
        <fail if="metadata.is.empty"
              message="Release metadata must not be blank"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="prepare" depends="validate">
        <mkdir dir="${classes.dir}/META-INF"/>
        <mkdir dir="${dist.dir}"/>

        <property name="ant.tstamp.now.iso"
                  value="${build.instant}"/>
        <tstamp>
            <format property="build.time.utc"
                    pattern="yyyy-MM-dd'T'HH:mm:ss'Z'"
                    timezone="UTC"
                    locale="en,US"/>
        </tstamp>
    </target>

    <target name="generate-info" depends="prepare">
        <!-- Chỉ filter file văn bản; cố định mã hóa. -->
        <copy file="metadata/build-info.properties.in"
              tofile="${classes.dir}/META-INF/build-info.properties"
              overwrite="true"
              encoding="UTF-8"
              outputencoding="UTF-8">
            <filterset begintoken="@" endtoken="@">
                <filter token="VERSION" value="${app.version}"/>
                <filter token="REVISION" value="${source.revision}"/>
                <filter token="BUILD_TIME" value="${build.time.utc}"/>
            </filterset>
        </copy>
    </target>

    <target name="compile" depends="generate-info">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <jar destfile="${dist.dir}/demo.jar"
             basedir="${classes.dir}"
             update="false"
             duplicate="fail"
             modificationtime="${build.instant}">
            <manifest>
                <attribute name="Implementation-Title"
                           value="repro-demo"/>
                <attribute name="Implementation-Version"
                           value="${app.version}"/>
                <attribute name="SCM-Revision"
                           value="${source.revision}"/>
                <attribute name="Build-Time"
                           value="${build.time.utc}"/>
            </manifest>
        </jar>
    </target>

    <!-- Đảm bảo không trộn class/resource của lần build trước. -->
    <target name="release" depends="clean,package"/>
</project>
```

Chạy từ thư mục dự án:

```bash
ant -version
java -version
ant release
```

Đầu ra chính là `dist/demo.jar`. Bên trong nó có `META-INF/MANIFEST.MF`, `META-INF/build-info.properties` và `com/example/Demo.class`.

| Trường / metadata | Nguồn | Vì sao ổn định? |
| --- | --- | --- |
| `Implementation-Version` | `app.version` | Bắt nguồn từ release đã chốt |
| `SCM-Revision` | `source.revision` | Một revision duy nhất |
| `Build-Time` | `build.instant` qua `tstamp` cố định | Không đọc đồng hồ hiện tại |
| Timestamp các entry | `modificationtime="${build.instant}"` | Dùng một mốc chung |
| Build path, username, CI run # | Không ghi | Không đưa trạng thái phiên chạy vào sản phẩm |

Mẫu dùng `release="17"` để chọn API và định dạng classfile, nhưng điều đó **không cố định phiên bản javac**. Bytecode, manifest mặc định hoặc nén ZIP có thể thay đổi giữa bản JDK/Ant khác nhau. Khi thực sự đòi hỏi byte-for-byte, hãy pin bản Ant, JDK, dependencies, bộ sinh mã và cấu hình môi trường.

### Nếu lấy metadata từ Git trong pipeline

Hai lệnh thường dùng:

```bash
git rev-parse HEAD
git show -s --format=%ct HEAD
```

Lệnh thứ nhất cung cấp commit; lệnh thứ hai cho thời điểm commit dạng Unix epoch **giây**. Pipeline có thể chuyển epoch sang ISO-8601 UTC trước khi truyền `-Dbuild.instant=...`. Đừng dùng thời điểm bắt đầu job làm `build.instant`. Nếu có file release đã chốt, không đồng thời thay giá trị của nó theo một quy tắc khác trong build script.

## 6. Kiểm chứng bằng hai checkout khác đường dẫn

Chuẩn bị hai bản checkout sạch ở vị trí khác nhau, có cùng source commit, metadata phát hành và toolchain. Trên Linux/macOS, ví dụ:

```bash
(cd /tmp/repro-a && ant release)
(cd /tmp/repro-b && ant release)

sha256sum /tmp/repro-a/dist/demo.jar
sha256sum /tmp/repro-b/dist/demo.jar
```

Trên PowerShell có thể dùng:

```powershell
Get-FileHash -Algorithm SHA256 C:\work\repro-a\dist\demo.jar
Get-FileHash -Algorithm SHA256 C:\work\repro-b\dist\demo.jar
```

Hai SHA-256 bằng nhau chứng minh **hai file cụ thể** bằng byte. Nếu khác nhau, trước tiên xem các phần ở bên trong:

```bash
jar tf dist/demo.jar
jar tvf dist/demo.jar
unzip -p dist/demo.jar META-INF/MANIFEST.MF
unzip -p dist/demo.jar META-INF/build-info.properties
```

`jar tf` cho biết tên các entry; `jar tvf` hiển thị thêm thông tin thời gian/kích thước; `unzip -p` xem nội dung. Nếu môi trường không có `unzip`, dùng công cụ giải nén tương đương hoặc `jar xf` trong một thư mục tạm.

Quy trình điều tra khi hash khác:

1. Xác nhận hai checkout đúng **cùng revision** và trạng thái input; kiểm tra dependency, Ant/JDK và tham số `-D`.
2. So từng file được sinh: `MANIFEST.MF`, `build-info.properties`, generated Java, JSON/XML và báo cáo đóng gói.
3. Tìm chuỗi theo máy: `${basedir}`, `${ant.file}`, `${user.name}`, hostname, home directory và thư mục tạm.
4. So timestamp, thứ tự entry, quyền file, phương thức nén, extra fields ZIP và encoding tên file.
5. Chạy lại từ output sạch; một output cũ có thể làm Ant bỏ qua bước compile hoặc vô tình giữ file không thuộc revision hiện tại.

Khi manifest và resource giống nhau mà SHA còn khác, không nên tự kết luận nguyên nhân chắc chắn là timestamp. Compiler, thứ tự đóng gói và metadata ZIP cũng có thể làm byte thay đổi.

## 7. Các lỗi thường gặp và cách sửa đúng chỗ

### Chỉ cố định tên file JAR

```xml
<jar destfile="dist/demo-1.4.2.jar"
     basedir="build/classes"/>
```

Tên JAR cố định không kiểm soát nội dung và timestamp của entry. Cần tiếp tục xử lý nguồn metadata, `modificationtime` và các đầu vào được đóng gói.

### Cố định `tstamp` nhưng quên `modificationtime`

```xml
<property name="ant.tstamp.now.iso"
          value="2025-01-01T00:00:00Z"/>
<tstamp/>
<jar destfile="dist/demo.jar" basedir="build/classes"/>
```

Timestamp trong property có thể đã ổn, nhưng timestamp các entry ZIP chưa được chốt. Hai việc có cơ chế riêng.

### Ghi `location` vào resource

```xml
<property name="config.path"
          location="src/main/resources/app.yml"/>
<echo file="build/classes/config-location.txt"
      message="${config.path}"/>
```

File `config-location.txt` sẽ mang đường dẫn của máy hiện tại. Nếu ứng dụng cần truy cập resource trong JAR, hãy dùng tên classpath như `app.yml` thay vì path của workspace.

### Đóng gói quá rộng

```xml
<!-- Có thể gom cả build/, dist/, file cá nhân hoặc .git. -->
<zip destfile="dist/source.zip">
    <fileset dir="."/>
</zip>
```

Thay bằng tập input cụ thể, ví dụ `<fileset dir="src"/>` cộng các file cấu hình cần phát hành. Tránh file sinh từ lần chạy trước và ấn định metadata ZIP khi phát hành.

### Dùng run number để định danh nội dung

`demo-1.4.2-ci-482.jar` và `demo-1.4.2-ci-483.jar` có thể đại diện cho cùng commit nhưng lại khác tên và khác nội dung nếu số phiên được nhúng. Nếu cần theo dõi từng job, liên kết CI run ID với một artifact theo **hash** trong hệ thống quản lý phát hành.

### Công cụ phụ vẫn ghi thời gian/path

Annotation processor có thể sinh chú thích ngày giờ, thư viện tạo code có thể ghi đường dẫn nguồn, plugin khác có thể lấy `user.dir`. Ant không tự loại bỏ thông tin đó. Cần tìm đúng file và đúng bước tạo ra sai khác, rồi sửa cấu hình hoặc thay đổi cách generator sinh dữ liệu.

## 8. Hợp đồng tái lập để áp dụng vào dự án

| Thành phần | Quy ước nên có |
| --- | --- |
| Source | Một commit hoặc snapshot xác định; kiểm soát thay đổi chưa commit |
| Version | `app.version` từ nguồn phát hành duy nhất |
| Revision | SHA/tag xác định, không phụ thuộc tên job |
| Thời gian nội dung | Mốc cố định, ISO-8601, UTC và locale rõ ràng |
| Thời gian JAR/ZIP | `modificationtime` cố định; chú ý độ phân giải 2 giây |
| Path | Path vật lý dùng nội bộ; artifact chứa tên logic tương đối |
| Metadata host/user | Không nhúng vào sản phẩm tái lập |
| Generated files | Template, encoding, newline và input rõ ràng |
| Packaging | Tập file, entry, nén, quyền và toolchain được kiểm soát |
| Dependency | Phiên bản và nguồn tải được chốt |
| Xác nhận | Hai checkout khác path, cùng input, so SHA-256 và điều tra nguyên nhân |

Một build tạo được cùng byte chưa tự động bảo đảm nguồn và dependency đáng tin cậy. Tính tái lập là một thuộc tính kỹ thuật của quy trình tạo artifact; xác thực nguồn và provenance cung cấp thêm bảo đảm về nguồn gốc.

## 9. Bài thực hành

1. Thêm `<attribute name="Build-Directory" value="${basedir}"/>` vào manifest của ví dụ, build từ hai path khác nhau. Mở manifest và giải thích vì sao SHA-256 thay đổi.
2. Thay `build.instant` bằng thời điểm hiện tại rồi dùng nó cho `Build-Time` và `modificationtime`. Chỉ ra hai nơi byte có thể đổi.
3. Khôi phục ba metadata cố định; chạy hai build sạch từ cùng commit ở hai checkout khác đường dẫn. So SHA-256, liệt kê entry bằng `jar tvf`, rồi thay riêng `app.version` để quan sát thay đổi có chủ đích.

**Câu hỏi tự đánh giá:** Đổi tất cả `location="..."` thành `value="..."` có luôn giải quyết lỗi path không? Không. Nhiệm vụ trước tiên là tìm **giá trị nào bị ghi vào artifact**. Sửa một đường dẫn mà task cần để đọc file có thể gây lỗi mới, trong khi một generator khác vẫn ghi `${basedir}`.

## Tài liệu tham khảo

- Apache Ant — [Tstamp](https://ant.apache.org/manual/Tasks/tstamp.html): mốc cố định, `SOURCE_DATE_EPOCH`, timezone.
- Apache Ant — [Jar](https://ant.apache.org/manual/Tasks/jar.html) và [Zip](https://ant.apache.org/manual/Tasks/zip.html): manifest, timestamp, `modificationtime` và `roundup`.
- Apache Ant — [Property](https://ant.apache.org/manual/Tasks/property.html): property bất biến, `value`, `location` và relative path.
- Apache Ant — [Copy](https://ant.apache.org/manual/Tasks/copy.html) và [FilterSet](https://ant.apache.org/manual/Types/filterset.html): sinh resource từ template với encoding rõ ràng.
- Apache Ant — [BuildNumber](https://ant.apache.org/manual/Tasks/buildnumber.html): đọc, tăng rồi ghi lại bộ đếm.
- Reproducible Builds — [Build path](https://reproducible-builds.org/docs/build-path/): đường dẫn máy build trong đầu ra.

**Điểm cốt lõi:** Với Ant, phiên bản và thời gian phải được lấy từ **đầu vào bất biến**, còn đường dẫn tuyệt đối chỉ phục vụ thao tác nội bộ. Khi cả nội dung metadata, timestamp của archive và toolchain được kiểm soát, việc so byte giữa hai lần build mới có ý nghĩa.

