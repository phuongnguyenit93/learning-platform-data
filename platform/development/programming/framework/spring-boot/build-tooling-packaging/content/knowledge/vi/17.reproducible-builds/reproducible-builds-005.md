# Ổn định timestamp với project.build.outputTimestamp của Maven

## 1. Vì sao hai JAR giống về chương trình lại khác SHA-256?

Bạn checkout cùng một commit của dự án Spring Boot, chạy Maven **clean verify** hai lần và đều nhận **BUILD SUCCESS**. Source, tests và Java behavior không thay đổi, nhưng hash SHA-256 của file **target/app.jar** lại khác. Một nguyên nhân là metadata **thời gian của những entry trong JAR/ZIP** đã thay đổi trong lúc đóng gói.

Một JAR chứa không chỉ bytecode Java mà còn nhiều entries như:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/repro/ReproApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/spring-boot-....jar
BOOT-INF/lib/...
~~~

Các ZIP entries có thể mang timestamp. Nếu archive được tạo với timestamps lấy từ thời điểm build, JAR build hôm nay có thể khác JAR build ngày mai ở một vài byte dù source không đổi. Khi phát hành artifact, điều đó gây khó khăn cho xác minh “binary này có được tạo từ source và công cụ đã công bố không?”.

Apache Maven hỗ trợ quy trình **Reproducible Builds**. Trong đó có Maven property:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

Các Maven plugins hỗ trợ reproducible archives sẽ dùng giá trị này làm mốc thời gian ổn định cho **entries của archive**. Đặc biệt:
- **maven-jar-plugin:jar** hỗ trợ tham số **outputTimestamp** từ phiên bản **3.2.0**.
- **spring-boot-maven-plugin:repackage** hỗ trợ tham số **outputTimestamp** từ phiên bản **2.3.0**, mặc định lấy giá trị Maven property trên.
- Các plugin phát hành source JAR, WAR, assembly, javadoc và artifact khác có thể cần kiểm tra riêng.

**Cố định timestamp không phải điều kiện đủ để tất cả bytes giống nhau**. Nó chỉ xử lý một nhóm nguồn không xác định. Dependencies, JDK, Maven plugins, generated sources, resources, manifest hoặc môi trường vẫn có thể gây khác biệt.

Bài học này tập trung vào **project.build.outputTimestamp của Maven** trong bối cảnh Spring Boot, hướng dẫn cách đặt timestamp có chủ đích, build và so hai JAR bằng SHA-256, tìm nguyên nhân nếu còn khác nhau, và đưa cấu hình vào release/CI.

## 2. Hiểu đúng reproducible build

**Reproducible build** nghĩa là với cùng source code, môi trường build và hướng dẫn build đã công bố, có thể tái tạo các artifact mục tiêu **giống nhau từng byte**. Định nghĩa này mạnh hơn “chạy đúng” nhưng cũng không đồng nghĩa phần mềm bảo mật hoặc logic không có lỗi.

| Khái niệm | Kiểm tra điều gì? | Không chứng minh điều gì? |
| --- | --- | --- |
| **Functional equivalence** | Hai JAR cho cùng hành vi trong test | Không chứng minh hai JAR giống bytes |
| **Local bit-for-bit reproducibility** | Hai clean builds cùng môi trường tạo JAR có SHA-256 giống nhau | Chưa chứng minh máy thứ ba làm lại giống |
| **Independent reproducibility** | Bên khác dùng source/toolchain đã công bố tạo được bytes đúng artifact release | Không thay thế audit hoặc kiểm tra bảo mật |
| **Supply-chain provenance** | Nguồn gốc, builder, workflow và đầu vào được ghi nhận | Không tự biến code dễ tổn thương thành an toàn |

Tập artifact cần kiểm tra phải được nêu rõ: **main Boot JAR**, plain JAR, WAR, sources JAR, javadoc JAR, POM xuất bản, buildinfo, SBOM hoặc image. Hai main JAR giống nhau không tự đảm bảo **toàn bộ release package** reproducible.

### 2.1. Timestamp filesystem không phải timestamp ZIP entry

Khi Maven tạo **target/repro-demo-1.0.0.jar**, hệ điều hành có thể gán **mtime** cho chính file JAR ở thời điểm hiện tại. Build lần hai, mtime của file có thể khác lần một.

Nhưng **project.build.outputTimestamp** hướng tới metadata **bên trong archive** do các plugins hỗ trợ tạo ra. Nó **không hứa** sẽ cố định filesystem mtime của file JAR bên ngoài. Vì thế:
- Đừng dùng **ls -l** để quyết định reproducibility.
- Đừng dùng thời gian file đã được upload lên artifact repository.
- Hãy dùng **sha256sum / Get-FileHash / cmp** so toàn bộ nội dung binary.

### 2.2. Timestamp được ghi vào nội dung file là vấn đề khác

Ví dụ một plugin/resource generator đưa giá trị này vào **application.properties**:

~~~properties
app.build.at=2026-11-09T10:37:42+07:00
~~~

Nếu lần build sau nó ghi timestamp mới, nội dung resource khác, khiến JAR hash khác dù mọi ZIP entry timestamp đã cố định. Tương tự, file **META-INF/build-info.properties**, generated Java source, manifest hoặc JSON được tạo với đồng hồ hiện tại có thể làm output không ổn định.

Vì vậy phải phân biệt:

| Loại thời gian | Nằm ở đâu? | project.build.outputTimestamp có xử lý trực tiếp không? |
| --- | --- | --- |
| ZIP/JAR entry metadata | Archive entries do plugin hỗ trợ tạo | **Có** |
| Filesystem mtime | target/*.jar trên ổ đĩa | **Không bảo đảm** |
| Giá trị bên trong file | Property, manifest, Java source, resource | **Tùy plugin/generator có dùng giá trị ổn định hay không** |
| CI job log timestamp | Log, monitoring của runner | **Không** |
| Runtime startup/deploy timestamp | Process đang chạy | **Không** |

Không cần xóa timestamp khỏi runtime logs; chúng giúp debug và không mặc nhiên nằm trong artifact release.

## 3. project.build.outputTimestamp hoạt động như thế nào?

### 3.1. Cấu hình property trong POM

Đặt trong phần **properties**:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Maven plugins có tham số **outputTimestamp** được khai báo mặc định từ property này sẽ dùng một mốc ổn định để tạo archive entries. Nếu project có parent POM, property có thể được thừa kế hoặc bị override bởi child, profile hoặc user property.

**Đây là Maven property, không phải Spring runtime property.** Không nên thêm nó vào **application.properties** rồi mong Maven Jar Plugin tự đọc.

### 3.2. Định dạng hợp lệ

Hai dạng thông dụng:

- **ISO 8601 extended offset date-time**, nên chọn UTC marker **Z** để thống nhất.
- **Số nguyên giây tính từ Unix epoch**, tương tự quy ước **SOURCE_DATE_EPOCH**.

Ví dụ tương đương:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

và:

~~~xml
<project.build.outputTimestamp>1782864000</project.build.outputTimestamp>
~~~

**1782864000** là số **giây** tính từ Unix epoch cho thời điểm UTC nêu trên. Không truyền epoch milliseconds (ví dụ **1782864000000**) vì plugin kỳ vọng seconds và có thể báo lỗi hoặc diễn giải sai.

Một chuỗi ISO 8601 như **2026-07-01T07:00:00+07:00** cùng chỉ tới thời điểm đó, nhưng khi nhiều người cùng sửa POM, chọn một quy ước UTC Z giảm hiểu nhầm về offset.

### 3.3. Giá trị được chọn từ mốc nào?

Một build của **cùng source release** phải nhận **cùng output timestamp**. Có ba chiến lược:

1. **Static timestamp được commit trong POM** cùng phiên bản phát hành. Cách dễ học và audit.
2. **Timestamp của một Git commit/tag đã chốt**, tính xác định từ Git history và truyền qua release pipeline.
3. **Release metadata do CI lưu lại**, được mọi bên rebuild sử dụng chính xác như lần tạo artifact phát hành.

Tránh lấy **thời điểm thực tế mỗi lần Maven chạy**. Hai lần build cùng source vào 09:00 và 10:00 sẽ lại có timestamp khác nhau; đó không phải cách giữ tính tái lập.

### 3.4. Đừng nhầm Maven property với SOURCE_DATE_EPOCH

**SOURCE_DATE_EPOCH** là quy ước biến môi trường phổ biến trong reproducible builds, giá trị là seconds từ epoch. Nhưng việc Maven hoặc một plugin có **tự đọc biến này** hay không còn tùy phiên bản/cơ chế plugin.

Để hành vi rõ ràng giữa nhiều version, nên **cấu hình project.build.outputTimestamp tường minh** hoặc chuyển epoch từ CI sang Maven user property, sau đó kiểm tra **effective property**.

Cú pháp truyền một mốc từ môi trường Unix khi đã kiểm soát biến:

~~~bash
./mvnw -B -ntp   "-Dproject.build.outputTimestamp=$SOURCE_DATE_EPOCH"   clean verify
~~~

Lệnh giả định **SOURCE_DATE_EPOCH** đã được thiết lập đúng dạng seconds, không rỗng và ổn định cho cùng source. Đừng mặc định biến của CI luôn tồn tại.

### 3.5. Maven core và Maven plugin hỗ trợ ở mức nào?

Tài liệu Maven hiện hành ghi nhận **Maven 3.10.0** và **4.0.0-beta-5** bật chế độ reproducible builds mặc định trong các trường hợp được hỗ trợ. Tuy nhiên:
- Không phải mọi project đều chạy Maven phiên bản đó.
- Một plugin cũ hoặc plugin bên thứ ba có thể bỏ qua outputTimestamp.
- Generated resource có thể tự ghi current time.
- Dependency/repository/JDK vẫn có thể khác nhau.

Vì vậy **đặt property rõ ràng** và **so artifact thật** vẫn là cách kiểm tra hữu ích. Không diễn giải rằng chỉ cần một phiên bản Maven mới thì mọi plugin custom sẽ trở nên deterministic.

Tài liệu: https://maven.apache.org/guides/mini/guide-reproducible-builds.html

## 4. Vì sao Spring Boot repackage cần cùng timestamp?

Quy trình Spring Boot Maven thường có các giai đoạn:

~~~text
src/main/java + src/main/resources
             |
             v
compile + process-resources
             |
             v
maven-jar-plugin:jar -> ordinary JAR
             |
             v
spring-boot-maven-plugin:repackage
             |
             v
Executable Spring Boot JAR
  BOOT-INF/classes
  BOOT-INF/lib/*.jar
  Spring Boot Loader + manifest
~~~

Bước **repackage** tạo layout Boot, đưa dependencies vào **BOOT-INF/lib** và cập nhật archive. Nếu chỉ làm timestamps của Jar Plugin ổn định mà Boot Plugin viết metadata không ổn định, **final executable JAR** vẫn có thể khác hash.

Spring Boot Maven Plugin **repackage** có tham số:

~~~text
outputTimestamp: String
default = project.build.outputTimestamp
~~~

Với plugin hỗ trợ và property đã đặt, không cần khai báo outputTimestamp ở từng nơi chỉ để dùng cùng giá trị. Tuy nhiên, nếu POM custom plugin configuration, parent/profile, archive layout hoặc classifier, nên kiểm tra effective POM và artifact thực.

**Nested JARs vẫn là một nguồn dữ liệu đầu vào.** Nếu một dependency SNAPSHOT được publish lại với cùng tọa độ nhưng bytes khác, final Boot JAR không thể giống nhau chỉ vì timestamp của **outer archive entries** đã ổn định.

### 4.1. Khi nào cấu hình outputTimestamp riêng ở plugin?

Bạn có thể viết minh họa trong **build/plugins**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
    </configuration>
</plugin>
~~~

Đây là **đoạn cấu hình phụ** để mô tả tham số plugin, không phải POM hoàn chỉnh. Với Spring Boot Maven Plugin đang có mặc định này, **thường không cần** dòng riêng ở plugin; chỉ project property là đủ. Nếu trong release có thêm WAR/source/assembly JAR, phải đảm bảo **tất cả** plugin tạo artifact đều được kiểm tra, thay vì chỉ chỉnh Boot repackage.

Tài liệu: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html

## 5. Ví dụ Java 17 có thể build và chạy với Spring Boot

Dùng một project không cần database hoặc HTTP server để tránh các nguồn biến động từ bên ngoài. Ví dụ kỹ thuật sử dụng Java **17** và Spring Boot **3.5.16**; đó là phiên bản cụ thể để minh họa, không phải khuyến nghị mặc định cho mọi dự án mới ở mọi thời điểm.

### 5.1. Cấu trúc dự án

~~~text
repro-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/repro/
    │   │   ├── ReproApplication.java
    │   │   └── StableMessage.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/repro/
            └── StableMessageTest.java
~~~

Maven Wrapper cần được tạo bằng Spring Initializr hoặc Maven Wrapper plugin; không được hiểu chỉ tạo POM là các tệp **mvnw** sẽ xuất hiện. Nếu chưa có Wrapper, dùng Maven được cài trên máy tương thích rồi thay các lệnh **./mvnw** bằng **mvn**; để so reproducibility, vẫn phải pin Maven version.

### 5.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích những phần quan trọng:**
- **spring-boot-starter-parent** quản lý versions của Spring Boot dependencies và một số Maven plugins.
- **java.version=17** cấu hình Java compilation level theo convention của parent.
- **project.build.outputTimestamp** đặt mốc archive entries ổn định.
- **spring-boot-starter** đưa Spring Boot core vào project, nhưng không tự tạo web endpoint hay mở cổng 8080.
- **spring-boot-starter-test** phục vụ JUnit và các utilities cho test.
- **spring-boot-maven-plugin** tạo executable archive thông qua **repackage** theo execution mà parent chuẩn bị.

Không cần tự khai báo Maven Jar Plugin version ở ví dụ có starter parent khi parent đã cung cấp một phiên bản tương thích. Với POM corporate parent, phải kiểm tra dependency/plugin management và execution thật trong effective POM.

### 5.3. Java helper trả dữ liệu ổn định

Tệp **src/main/java/com/example/repro/StableMessage.java**:

~~~java
package com.example.repro;

public final class StableMessage {
    private StableMessage() {
    }

    public static String text() {
        return "repro-build-ok";
    }
}
~~~

### 5.4. Main application class

Tệp **src/main/java/com/example/repro/ReproApplication.java**:

~~~java
package com.example.repro;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReproApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReproApplication.class, args);
        System.out.println(StableMessage.text());
    }
}
~~~

Spring Boot sẽ có logs startup thay đổi theo thời gian chạy, nhưng sau khi context thành công, chương trình in một dòng riêng có **stdout chính xác**:

~~~text
repro-build-ok
~~~

Đừng cố làm timestamp trong logs runtime bằng **outputTimestamp**; đó là thời điểm hoạt động thực, không phải metadata của archive.

### 5.5. application.properties

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=repro-demo
~~~

Đây là resource tĩnh, không tự sinh thời điểm build. Nếu bạn dùng Maven Resources Plugin filtering để thay token thời gian, kiểm tra nội dung được copy vào **target/classes** và quyết định xem giá trị ấy có thể được tái tạo không.

### 5.6. JUnit test

Tệp **src/test/java/com/example/repro/StableMessageTest.java**:

~~~java
package com.example.repro;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StableMessageTest {
    @Test
    void textIsStable() {
        assertEquals("repro-build-ok", StableMessage.text());
    }
}
~~~

Test chạy khi Maven Surefire được cấu hình phù hợp qua parent và starter-test. **Không dùng -DskipTests** trong một bản build rồi đối chiếu với bản build khác có test nếu đang so hai quy trình release: phạm vi xác minh đã thay đổi.

### 5.7. Build và chạy artifact

Trên Linux/macOS:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
java -jar target/repro-demo-1.0.0.jar
~~~

Trên Windows dùng **mvnw.cmd** hoặc **.\mvnw.cmd** theo terminal. **clean verify** đi qua các phase compile/test/package và goal repackage của project. Tên artifact **target/repro-demo-1.0.0.jar** tương ứng với group/artifact/version ở POM; nếu dùng classifier hoặc custom output name thì đường dẫn thực sẽ khác.

Các lần run có thể khác nhau về thời gian/log, nhưng JAR bytes có thể ổn định khi tất cả input/plugin outputs deterministic.

## 6. Kiểm tra Maven thực sự đọc timestamp

### 6.1. Đọc property bằng Maven Help Plugin

~~~bash
./mvnw -q help:evaluate -Dexpression=project.build.outputTimestamp -DforceStdout
~~~

Với project ví dụ, giá trị mong đợi:

~~~text
2026-07-01T00:00:00Z
~~~

Maven Help Plugin có thể cần download lần đầu; nếu có warnings/log khác, tìm giá trị property, không dựa vào việc toàn bộ console chỉ có đúng một dòng.

Nếu giá trị khác mong đợi, xem effective POM:

~~~bash
./mvnw help:effective-pom
~~~

Tìm property, active profiles và plugin versions. **effective-pom** phản ánh cấu hình đã ghép từ parent/profile, nhưng vẫn phải kiểm tra artifact thực để xác minh hành vi.

### 6.2. Đọc outputTimestamp trong plugin

~~~bash
./mvnw help:describe -Dplugin=org.apache.maven.plugins:maven-jar-plugin -Dgoal=jar -Ddetail=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Maven Jar Plugin từ **3.2.0** và Spring Boot repackage từ **2.3.0** có tham số **outputTimestamp** hỗ trợ reproducible archive entries.

Nếu project dùng **maven-war-plugin**, **maven-source-plugin**, **maven-assembly-plugin**, **maven-shade-plugin**, custom packaging hoặc plugin ký số, kiểm tra từng plugin. Đừng coi việc thấy property trong POM là bằng chứng mọi output của mọi plugin sẽ deterministic.

## 7. Quy trình quan trọng: build hai lần, so hash chính xác

### 7.1. Vì sao phải copy JAR ra ngoài target?

Maven goal **clean** xóa **target/**. Nếu vừa build lần một rồi gọi clean lần hai mà chưa copy file reference, artifact cũ đã mất; lúc đó bạn không có hai binary thật để so sánh.

Luồng kiểm tra:

~~~text
Cố định source commit + Maven/JDK + dependency versions
                           |
                           v
                    clean verify #1
                           |
                           v
              Copy first JAR ngoài target
                           |
                           v
                    clean verify #2
                           |
                           v
              Copy second JAR ngoài target
                           |
                           v
                 SHA-256 + byte compare
                     |           |
                   PASS         FAIL
                     |           |
             Kiểm tra độc lập  Điều tra nội dung/ZIP metadata
~~~

Khi so, không thêm hoặc bỏ cờ test giữa hai lượt, không chỉnh POM, không thay nguồn dependencies. **Build lần một và lần hai đều phải thành công** trước khi chốt kết quả.

### 7.2. Bash script cho Linux

Tạo file **compare-repro.sh** ở project root:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

artifact="target/repro-demo-1.0.0.jar"
result_dir="$(mktemp -d)"
echo "Comparison outputs are in $result_dir"

echo "First clean build"
./mvnw -B -ntp clean verify
cp "$artifact" "$result_dir/first.jar"

echo "Second clean build"
./mvnw -B -ntp clean verify
cp "$artifact" "$result_dir/second.jar"

echo "SHA-256 of both artifacts:"
sha256sum "$result_dir/first.jar" "$result_dir/second.jar"

if cmp -s "$result_dir/first.jar" "$result_dir/second.jar"; then
    echo "PASS: artifacts are byte-for-byte identical"
else
    echo "FAIL: artifacts differ; inspect both copies"
    exit 1
fi
~~~

Chạy trong workspace được phép build/clean:

~~~bash
chmod +x compare-repro.sh
./compare-repro.sh
~~~

Nếu qua được nhánh thành công, script in chính xác dòng kết luận:

~~~text
PASS: artifacts are byte-for-byte identical
~~~

Các giá trị SHA-256 thực tế **không cố định trong bài** vì phụ thuộc version/toolchain/artifact bytes. Script không tự xóa **result_dir** để bạn còn lưu reference khi xảy ra FAIL; khi dọn dẹp, chỉ xóa thư mục tạm đã xác minh.

**Các điều kiện dùng script:**
- Có Bash, Maven Wrapper, Java và quyền chạy build.
- Có **sha256sum** và **cmp** (thường có trên Linux).
- Khi dùng macOS có thể thay **sha256sum** bằng **shasum -a 256**.
- Cả hai clean builds thực thi **cùng lệnh**, cùng source và project dependencies.
- Mỗi lần gặp lỗi Maven/test thì **set -e** làm script dừng, tránh ghi nhận fail là một bản build hợp lệ.

### 7.3. PowerShell trên Windows

Với Windows PowerShell:

~~~powershell
$artifact = ".\target\repro-demo-1.0.0.jar"
$dir = Join-Path $env:TEMP ("maven-repro-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $dir | Out-Null

& .\mvnw.cmd -B -ntp clean verify
if ($LASTEXITCODE -ne 0) {
    throw "First Maven build failed"
}
Copy-Item -LiteralPath $artifact -Destination (Join-Path $dir "first.jar")

& .\mvnw.cmd -B -ntp clean verify
if ($LASTEXITCODE -ne 0) {
    throw "Second Maven build failed"
}
Copy-Item -LiteralPath $artifact -Destination (Join-Path $dir "second.jar")

$first = (Get-FileHash (Join-Path $dir "first.jar") -Algorithm SHA256).Hash
$second = (Get-FileHash (Join-Path $dir "second.jar") -Algorithm SHA256).Hash

Write-Host "First SHA-256: $first"
Write-Host "Second SHA-256: $second"

if ($first -eq $second) {
    Write-Host "PASS: SHA-256 hashes match"
} else {
    throw "FAIL: two Maven outputs have different hashes"
}
~~~

Hai JAR được giữ ngoài **target/** trong thư mục tạm. Hash bình đẳng rất khó xảy ra ngẫu nhiên với hai nội dung khác nhau, nên là cách kiểm tra byte identity phù hợp. Tuy nhiên, việc hash khớp **không chứng minh** nguồn build độc lập đã được kiểm tra hoặc project không có lỗ hổng.

### 7.4. Kết quả nào được coi là PASS?

| Kết quả | Kết luận |
| --- | --- |
| Hai clean builds thành công, cùng SHA-256, cùng phạm vi | PASS phép kiểm tra cục bộ đối với artifact đó |
| Hai builds PASS nhưng SHA-256 khác | FAIL reproducibility cục bộ; cần điều tra |
| Một build/test FAIL | Không có cặp build thành công để so |
| SHA-256 trùng nhưng chỉ build một lần rồi copy file hai lần | **Không phải** phép kiểm tra tái lập |
| Hai JAR giống nhưng sources JAR khác | Chưa đạt tính tái lập của **toàn bộ release** nếu sources JAR thuộc phạm vi |
| Hai builds trên máy A khớp | Vẫn cần độc lập rebuild khi tuyên bố independently reproducible |

**Quan trọng:** timestamp trên filesystem của **first.jar** và **second.jar** vẫn có thể khác, trong khi SHA-256 của cả hai bằng nhau. Không gọi đó là FAIL.

## 8. Maven Artifact Plugin: kiểm tra theo công cụ chính thức

Maven có **maven-artifact-plugin** hỗ trợ kiểm tra Reproducible Builds.

### 8.1. Tìm plugin dễ gây nondeterminism

~~~bash
./mvnw artifact:check-buildplan
~~~

Goal **artifact:check-buildplan** đánh giá build plan để chỉ ra plugin/goals có vấn đề reproducibility đã biết hoặc cần nâng phiên bản. Nó **không thể chứng nhận** tất cả custom plugins, code generators hoặc runtime environment đều deterministic.

### 8.2. So với artifact tham chiếu trong local repository

Theo hướng dẫn Maven, có thể:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

Lệnh đầu install artifact đã build vào local repository; lệnh thứ hai build sạch và dùng **artifact:compare** đối chiếu output mới với reference. Cách này giúp kiểm tra release artifacts theo cơ chế plugin, đặc biệt khi có nhiều outputs/attached artifacts.

**Không nhầm local install với artifact đã được publish lên Maven Central hoặc repository production.** Một bản so local PASS chưa chứng minh máy thứ ba đã rebuild được file release xuất bản. Khi cần kiểm tra độc lập, lấy published artifact làm reference và dựng lại bằng source/toolchain đã khai báo.

### 8.3. Nếu compare FAIL

Các bước điều tra:
1. Giữ nguyên hai file output và log plugin.
2. Xác định artifact nào lệch: main JAR, sources, Javadoc, WAR, POM hoặc metadata.
3. Dùng **diffoscope** hoặc công cụ ZIP diff có hỗ trợ để tìm entry metadata/nội dung khác.
4. Xem goal/plugin đã tạo file sai khác.
5. Nâng lên phiên bản plugin hỗ trợ reproducibility hoặc sửa codegen/input chưa xác định.
6. Build lại và so toàn bộ artifact.

Không tự sửa ZIP bytes sau khi build để “làm hash khớp” trong khi giữ nguyên lỗi generator.

Tài liệu: https://maven.apache.org/guides/mini/guide-reproducible-builds.html

## 9. Khi fixed timestamp vẫn chưa đủ

### 9.1. Plugin cũ hoặc cấu hình sai

Nếu **maven-jar-plugin** hoặc **spring-boot-maven-plugin** chưa hỗ trợ outputTimestamp hoặc không được gọi, POM property không làm final JAR ổn định. Ngoài ra, parent/profile có thể ghi đè cấu hình.

Dùng **help:effective-pom**, **help:describe** và Maven build logs để xác định **version + execution goal** thực sự.

### 9.2. Dynamic dependency hoặc SNAPSHOT

Nếu build phụ thuộc bản SNAPSHOT được cập nhật hoặc version range resolve khác, JAR cuối có thể chứa một **dependency khác byte** dù tọa độ trông như nhau.

Với Spring Boot executable archive, dependencies được đóng dưới **BOOT-INF/lib**. Thay đổi byte của một nested JAR thường thay hash của outer Boot JAR. Maven outputTimestamp **không khóa dependencies** và không làm nội dung mọi third-party JAR giống nhau.

### 9.3. JDK, compiler và generated source

**javac** của các JDK major versions khác nhau có thể cho class files khác ngay cả khi cùng Java source. Annotation processors, code generators hoặc plugins tạo Java source có thể ghi:
- thời điểm generate;
- đường dẫn workspace tuyệt đối;
- tên máy/user;
- random UUID;
- danh sách fields không theo thứ tự xác định;
- compiler/build tool version.

Cần chốt JDK/toolchain và plugin versions, kiểm tra generated source và class bytecode. Không tự thay outputTimestamp bằng một số khác khi vấn đề thực nằm ở generated code.

### 9.4. Line endings, encoding, locale và OS

Một resource text trên Windows có thể dùng **CRLF**, trên Unix dùng **LF**. Resource filtering, generated code, default encoding và locale khác nhau có thể làm bytes khác. Cần thống nhất:
- **UTF-8** cho source/resources khi phù hợp;
- line ending policy;
- timezone/locale được generators sử dụng;
- cùng Java major version và plugin versions;
- profile/CI options áp dụng giữa các hệ.

Tài liệu Maven nhấn mạnh việc rebuild độc lập trên Windows và Unix có thể cần xử lý newline/OS differences.

### 9.5. File order và ZIP metadata khác timestamp

Một plugin có thể đưa entries vào JAR theo thứ tự filesystem traversal không ổn định; một plugin khác ghi attributes/permissions hoặc extra ZIP fields khác nhau. **Same timestamp** không làm những phần khác trở nên giống nhau.

Dùng binary/ZIP-aware diff để phân loại:
- chỉ entry timestamps khác;
- entry ordering khác;
- manifest khác;
- compiled .class khác;
- resource content khác;
- nested libs khác;
- chữ ký/signing metadata khác.

Chọn cách sửa từ bằng chứng, không tăng/giảm timestamps để che mọi khác biệt.

## 10. Spring Boot build-info.properties có time bên trong nội dung

Spring Boot Maven Plugin hỗ trợ goal **build-info** tạo:

~~~text
META-INF/build-info.properties
~~~

Khi được kích hoạt, file này có thể chứa **build.group, build.artifact, build.name, build.version, build.time**. Đây là nội dung resource, không phải ZIP entry timestamp.

Theo tài liệu Spring Boot **3.5.16**, tham số **time** của goal **spring-boot:build-info** lấy **project.build.outputTimestamp** nếu có; nếu không, plugin có thể dùng thời gian bắt đầu Maven session. Vì vậy property cố định không chỉ ảnh hưởng repackage mà còn giúp **build.time** deterministic khi build-info goal được sử dụng.

### 10.1. Kích hoạt build-info khi có yêu cầu

Trong POM ví dụ, **thay** block Spring Boot Maven Plugin hiện tại bằng block này:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>build-info</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đoạn XML trên chỉ là **block plugin** đặt trong **build/plugins**, không phải POM độc lập. Với Spring Boot starter parent, **repackage** vẫn được tích hợp theo parent, còn **build-info** được thêm theo execution này.

Sau build, kiểm tra nội dung **target/classes/META-INF/build-info.properties** (khi goal đã tạo file), và nếu cần so entry đó trong final Boot JAR. Không giả định **build-info.properties** luôn được tạo chỉ vì project có Spring Boot Plugin.

### 10.2. Tách “ngày build đã chốt” với “ngày job chạy”

**build.time** theo project property có thể được giữ cố định khi tái lập cùng release dù job CI chạy một tuần sau. Nếu dashboard cần thời điểm deploy/start mới nhất, lấy từ deployment metadata hoặc runtime monitoring, **không sửa outputTimestamp mỗi lần job chạy**.

Nếu muốn loại **build.time** khỏi resource, Spring Boot Plugin có tùy chọn **excludeInfoProperties** hoặc giá trị **off** cho time; cần chọn theo yêu cầu sản phẩm và vẫn kiểm tra các field khác trong file.

## 11. Chọn timestamp phù hợp cho release pipeline

### 11.1. Giá trị cố định trong POM

Một release có thể đặt:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

Cùng source release, cùng giá trị timestamp. Khi chuẩn bị một phiên bản mới, pipeline/release manager cập nhật mốc theo chính sách và commit thay đổi đó cùng version/metadata. Đây là cách dễ audit nhưng phải có kỷ luật không quên cập nhật.

### 11.2. Dùng Git commit timestamp

Git có thể cung cấp số giây của HEAD commit:

~~~bash
git log -1 --format=%ct
~~~

Khi release pipeline đã xác định HEAD là commit được phát hành, có thể chuyển giá trị vào Maven:

~~~bash
stamp="$(git log -1 --format=%ct)"
./mvnw -B -ntp "-Dproject.build.outputTimestamp=$stamp" clean verify
~~~

**%ct** trả epoch **seconds**, ổn định theo cùng commit. Nếu source là dirty workspace thì commit time không mô tả hết source; trước khi release hãy bảo đảm checkout được kiểm soát.

Đây là **phương án thay thế cho static timestamp**, không phải bắt buộc vừa sửa property POM sang một giá trị mới vừa ghi đè một giá trị khác mỗi lần gọi. Nếu CLI dùng property override, xác minh **help:evaluate** và behavior plugin trên phiên bản Maven thật.

### 11.3. Lưu ý Maven Release Plugin

Tài liệu Maven mô tả những Maven Release Plugin versions hỗ trợ cập nhật outputTimestamp trong workflow release (mốc hỗ trợ từ **3.0.0-M1**). Custom release pipeline hoặc versions-maven-plugin có behavior tùy version. Chỉ dùng automation sau khi thử trên branch/release staging, không giả định mọi plugin sẽ tự đồng bộ timestamp.

### 11.4. Không lấy thời gian hiện tại của job CI

Nếu cùng commit được build lại vào ngày khác, dùng current time làm property sẽ tạo mốc khác. Nó giải quyết việc có một timestamp được ghi vào archive nhưng **không ổn định**, nên đánh mất mục tiêu reproducible build. Timestamp dùng trong artifact phải là **release metadata xác định**, không phải đồng hồ hiện tại.

## 12. Multi-module Maven và parent inheritance

Trong project nhiều module:

~~~text
platform-parent/
├── pom.xml
├── api/pom.xml
├── library/pom.xml
└── boot-app/pom.xml
~~~

Có thể định nghĩa ở **parent POM**:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Child modules **thực sự khai báo parent** thích hợp sẽ thừa kế giá trị nếu không override. **Chỉ liệt kê module trong một aggregator POM không đồng nghĩa tất cả module kế thừa properties**. Dùng effective POM của từng module nếu cần chứng minh.

Trong multi-module:
- Từng JAR/WAR/source archive phải được plugin tạo ra đúng version và cùng policy.
- Nếu một module generate resource với timestamp động, chỉ module ấy có thể làm toàn release thiếu reproducibility.
- Đảm bảo cùng reactor selection và build flags khi so hai lần.
- Đừng so một lần build toàn repo với một lần chỉ build một module rồi tuyên bố là cùng workload.

Ví dụ module **boot-app** tồn tại:

~~~bash
./mvnw -pl boot-app -am -B -ntp clean verify
~~~

**-pl** chọn module, **-am** thêm reactor dependencies. Lệnh này không tương đương build toàn bộ repo nếu bỏ các module khác.

## 13. Chẩn đoán kết quả khi hash vẫn khác

| Hiện tượng | Câu hỏi cần đặt | Cách kiểm tra |
| --- | --- | --- |
| Property tồn tại nhưng JAR đổi hash | Plugin nào tạo/ghi lại archive? | Effective POM, plugin goal logs |
| Maven Jar Plugin tạo output ổn định nhưng Boot JAR khác | Repackage có dùng outputTimestamp? Nested libs có khác? | Spring Boot Plugin version, diff Boot JAR |
| Hai ZIP entries có timestamps khác | Plugin cũ hoặc bước archive khác làm mới metadata? | Plugin outputTimestamp, ZIP diff |
| Bytes của class files khác | JDK/compiler/codegen khác? | Compare .class, javap, toolchain |
| File resource khác | Có dùng current time, env variable hay filtering? | target/classes, generated files |
| Nested JAR khác | Snapshot/version range hoặc repository có đổi? | dependency:tree, hashes của dependency |
| Manifest khác | Đang nhúng build time/host/JDK info? | So META-INF/MANIFEST.MF |
| Build-info có build.time động | Goal build-info dùng session time? | Property và build-info time config |
| SHA khớp trên Linux nhưng không khớp Windows | Newline/encoding/OS assumptions? | Chuẩn hóa JDK và resource bytes |
| Filesystem mtime khác nhưng SHA khớp | Chỉ outer file metadata thay đổi | Reproducibility nội dung đã PASS |
| Source JAR khác trong khi Boot JAR giống | Plugin khác xử lý source archive | Kiểm tra source plugin và file entries |
| Dynamic dependencies không đổi coordinates nhưng đổi bytes | Cùng SNAPSHOT bị publish lại? | Repository metadata, dependency hashes |
| Plugin dùng đường dẫn máy | Absolute source path trong generated output? | Diffoscope và source generator config |
| JAR có timestamp ổn định nhưng signing output khác | Chữ ký/chứng nhận có metadata thời gian riêng | Kiểm soát quá trình ký theo release policy |
| artifact:check-buildplan PASS nhưng binary khác | Tool chỉ biết một số vấn đề plugin | So hash và diffoscope thật |
| Hai hash bằng nhau nhưng chỉ copy một file hai lần | Thí nghiệm sai | Hai lần clean build độc lập |

**Cách đi từ rộng đến hẹp:**
1. Đảm bảo source commit, Maven/JDK, dependencies và active profiles giống nhau.
2. Xác nhận **project.build.outputTimestamp** và plugin versions.
3. Giữ hai binary tham chiếu và mới.
4. Dùng **diffoscope** hoặc công cụ ZIP-aware diff để tìm entry khác.
5. Xác định file được tạo bởi goal/plugin nào.
6. Thay đổi đúng nguyên nhân, rebuild, so hash lại.

Không tự dùng **touch** đổi file mtime và cho rằng đã sửa ZIP metadata. Không mở JAR rồi chỉnh nội dung bằng tay chỉ để hai binary giống nhau: phải sửa **quy trình tạo artifact**.

## 14. Khác biệt với Gradle

Bài này hướng vào **Maven project.build.outputTimestamp**, không phải Gradle build-cache hoặc Spring runtime property. Gradle Java plugin có những cơ chế riêng cho reproducible archive tasks, chẳng hạn cấu hình **preserveFileTimestamps** và **reproducibleFileOrder** với archive tasks phù hợp. Không sao chép XML Maven vào **build.gradle**; nếu dùng Gradle, kiểm tra Gradle task settings và Spring Boot Gradle packaging theo tài liệu của plugin đó.

Việc bật Maven outputTimestamp **không tăng tốc compile**, không làm JVM chạy nhanh hơn và không thay thế dependency cache. Reproducibility giải quyết **tính nhất quán của bytes**, còn performance đo bằng thời gian và resource consumption.

## 15. Bài tập thực hành có lời giải

### Bài 1: phân biệt timestamp filesystem và archive

Bạn build hai lần, **mtime của target/repro-demo-1.0.0.jar khác** nhưng **SHA-256 giống nhau**. Bản dựng có reproducible không?

**Đáp án:** Đối với nội dung bytes của main JAR được kiểm tra, kết quả **PASS phép kiểm tra cục bộ**. mtime filesystem không phải ZIP entry bytes. Vẫn cần xác minh các artifact khác nếu thuộc release và kiểm tra độc lập khi muốn kết luận mạnh hơn.

### Bài 2: tại sao static timestamp chưa đủ?

POM có:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

Nhưng một custom Maven plugin ghi **build.startTime** bằng đồng hồ hệ thống vào JSON được đóng gói. Hash có thể khác không?

**Đáp án:** Có. Dữ liệu **bên trong file JSON** đã khác. Phải thay bằng release timestamp ổn định, hoặc để timestamp runtime/CI ở nơi khác thay vì artifact.

### Bài 3: seconds hay milliseconds?

Hai giá trị:

~~~text
1782864000
1782864000000
~~~

Giá trị nào phù hợp nếu dùng epoch integer cho Maven outputTimestamp?

**Đáp án:** **1782864000** là số giây. Giá trị dài hơn là milliseconds, không phải dạng được plugin mô tả.

### Bài 4: Maven Jar Plugin ổn nhưng Boot repackage cũ

Một plain JAR của project có hash giống nhau, nhưng final Spring Boot JAR khác. Nên làm gì?

**Đáp án:** Kiểm tra Spring Boot Maven Plugin version, **repackage outputTimestamp** và nested dependencies; so file khác nhau trước khi thay đổi cấu hình. Đừng dừng ở kết quả plain JAR.

### Bài 5: main JAR ổn nhưng sources JAR khác

Có thể tuyên bố toàn bộ release reproducible không?

**Đáp án:** Nếu release bao gồm sources JAR, **chưa**. Cần kiểm tra plugin tạo sources archive và sources metadata; tiêu chí reproducibility phải áp dụng cho tất cả artifact mục tiêu.

### Bài 6: cùng Git commit nhưng CI runs ở các múi giờ khác nhau

Hai build lấy timestamp bằng **git log -1 --format=%ct**, cùng JDK/inputs. Múi giờ khác có làm epoch seconds khác không?

**Đáp án:** **%ct** là Unix epoch seconds của commit, nên không đổi chỉ vì máy nằm ở timezone khác. Tuy nhiên các plugins/resources khác vẫn có thể phụ thuộc timezone của máy, và phải được kiểm tra riêng.

### Bài 7: build-info.properties có build.time khác

Nếu goal Spring Boot build-info lấy session time vì Maven project property không được đặt, nên làm gì?

**Đáp án:** Đặt **project.build.outputTimestamp** ổn định hoặc cấu hình **build-info time** theo release policy. So content build-info chứ không chỉ xem timestamps của ZIP entries.

### Bài 8: đã so hai lần trong cùng máy, có thể nói bên ngoài rebuild được không?

**Đáp án:** Chưa. Phải có independent rebuild trên một môi trường khác được kiểm soát, so với **published artifact** và ghi nhận toolchain/dependency/provenance.

## 16. Checklist trước khi phát hành

- [ ] Đã xác định chính xác artifact cần reproducible: main Boot JAR, WAR, sources, javadoc, v.v.
- [ ] Source commit/tag được chốt, không có dirty changes không ghi nhận.
- [ ] Maven version/Wrapper, JDK/compiler và plugin versions được chốt.
- [ ] Dependencies ổn định, tránh snapshots/version ranges không kiểm soát.
- [ ] **project.build.outputTimestamp** có giá trị ISO 8601 UTC hoặc Unix epoch **seconds** ổn định.
- [ ] Property được đọc đúng trong effective POM, không bị profile/CLI override ngoài ý muốn.
- [ ] Maven Jar Plugin và Spring Boot Maven Plugin hỗ trợ outputTimestamp; các archive plugins khác được kiểm tra riêng.
- [ ] Resource filtering, generated sources, manifest, build-info không ghi timestamp động, hostname hay random IDs.
- [ ] Newlines/encoding/locale/OS/JDK được kiểm soát theo release process.
- [ ] Chạy **hai clean builds**, giữ JAR thứ nhất ngoài target trước build lần hai.
- [ ] So toàn bộ bytes bằng **SHA-256** hoặc **cmp**, không chỉ file mtime.
- [ ] Khi hash khác, dùng **artifact:check-buildplan**, **artifact:compare**, diffoscope và kiểm tra plugins.
- [ ] Nếu có multi-module, so đúng module scope, cùng parent inheritance và cùng source versions.
- [ ] Khi công bố independent reproducibility, có rebuild từ môi trường khác và so với artifact đã phát hành.
- [ ] Vẫn chạy unit/integration tests, scanning và release checks; reproducibility không thay thế chúng.
- [ ] Lưu build provenance: source ref, toolchain versions, timestamp policy, dependency sources và checksum release.

## 17. Tổng kết

**project.build.outputTimestamp** là một Maven property cung cấp **mốc thời gian ổn định cho các entry trong archive** của các plugins có hỗ trợ, nổi bật là **maven-jar-plugin** và **spring-boot-maven-plugin:repackage**. Nó giúp loại bỏ sự thay đổi binary phát sinh chỉ vì build diễn ra vào một ngày khác.

Quy trình cần nhớ:

~~~text
Chốt source + Maven/JDK/dependencies
                  |
                  v
Chọn timestamp theo release/commit
                  |
                  v
Đặt project.build.outputTimestamp
                  |
                  v
Clean build #1, giữ artifact ngoài target
                  |
                  v
Clean build #2, giữ artifact ngoài target
                  |
                  v
So SHA-256 và kiểm tra artifact đúng scope
                  |
             +----+----+
             |         |
            PASS      FAIL
             |         |
  Kiểm tra độc lập  So binary/ZIP/codegen,
                    tìm plugin và sửa nguyên nhân
~~~

**Kết luận không nên rút gọn thành “thêm một dòng property là xong”.** Một build thực sự tái lập được phải có artifacts giống bytes, source/toolchain/dependencies được kiểm soát và bằng chứng đối chiếu từ đúng quy trình release.

## 18. Tài liệu tham khảo chính thức

- Apache Maven — Configuring for Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Apache Maven JAR Plugin — jar:jar, outputTimestamp: https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html
- Apache Maven Artifact Plugin — artifact:check-buildplan: https://maven.apache.org/plugins/maven-artifact-plugin/check-buildplan-mojo.html
- Apache Maven Artifact Plugin — artifact:compare: https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Spring Boot 3.5.16 Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5.16 Maven Plugin — Build Info: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-info.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Reproducible Builds — SOURCE_DATE_EPOCH: https://reproducible-builds.org/docs/source-date-epoch/
- Reproducible Builds — Timestamps: https://reproducible-builds.org/docs/timestamps/
