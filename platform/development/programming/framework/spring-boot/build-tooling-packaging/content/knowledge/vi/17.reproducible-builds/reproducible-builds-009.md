# So sánh SHA-256 của hai bản dựng từ cùng nguồn trên môi trường sạch

## 1. Mục tiêu: chứng minh file đóng gói có thể tái lập

Một dự án Spring Boot có thể **build thành công nhiều lần** nhưng tạo ra các file JAR có **nội dung byte khác nhau** dù không sửa source code. Chẳng hạn, tệp ZIP/JAR có thể chứa timestamp, thứ tự entry, giá trị Build-Time, metadata từ Git, đường dẫn máy build hoặc output của annotation processor. Những chi tiết nhỏ này không nhất thiết làm ứng dụng chạy sai, nhưng chúng khiến SHA-256 khác nhau.

**Bản dựng tái lập (reproducible build)** theo nghĩa mạnh là: với cùng bộ input được xác định rõ (source code, dependencies, build scripts, toolchain và điều kiện build), kết quả artifact được tạo ra có cùng chuỗi byte. Chỉ cùng hành vi khi chạy **chưa đủ**; phải kiểm chứng **byte-for-byte** của file đầu ra.

Bài này đặt ra phép thử thực tế:

1. Chọn **một Git commit cố định**.
2. Tạo **hai checkout sạch, độc lập**, không mang theo các file build cũ.
3. Giữ nguyên versions của Maven/Gradle, JDK, plugins, dependencies và cấu hình.
4. Build cùng loại **Spring Boot executable JAR** hai lần.
5. Tính **SHA-256** của cả hai file.
6. So sánh hai digest và đối chiếu byte của hai file.
7. Nếu không khớp, kiểm tra nội dung ZIP, manifest, timestamp và dữ liệu sinh từ môi trường để tìm nguyên nhân.
8. Đưa phép thử vào CI để phát hiện regression về khả năng tái lập.

**Ví dụ sử dụng Java 17, Spring Boot 3.3.5, Maven 3.9.x hoặc Gradle 8.5**, với artifact tên **repro-demo-1.0.0.jar**. Đây là bộ version cố định cho bài thực hành, không phải các version mới nhất.

### Kết quả mong đợi

Nếu hai bản dựng thực sự có cùng byte, ví dụ minh họa là:

~~~text
BUILD_A_SHA256=<64 ký tự hexadecimal>
BUILD_B_SHA256=<cùng 64 ký tự hexadecimal>
REPRODUCIBLE=PASS
~~~

Dấu ngoặc trong sơ đồ trên chỉ giải thích định dạng; **không phải SHA-256 thật đã được đo**. Không thể biết trước một digest hợp lệ khi chưa thực sự build artifact. Trong phần script chạy được ở dưới, checksum thực sẽ được tính và in ra từ file JAR, không hard-code.

**Lưu ý về từ “môi trường sạch”:** Hai checkout sạch trong cùng máy là một thử nghiệm có kiểm soát rất hữu ích, nhưng **chưa chứng minh tính tái lập trên mọi hệ điều hành/JDK**. Muốn kiểm thử mức mạnh hơn, thực hiện trong hai container/runner độc lập có image digest, JDK và toolchain được pin và ghi lại.

## 2. SHA-256 xác nhận điều gì?

**SHA-256** là hàm băm mật mã chuyển một chuỗi byte bất kỳ thành digest **256 bit**, thường hiển thị bằng **64 ký tự hexadecimal**. Công thức về mặt khái niệm:

~~~text
SHA256(bytes của artifact-a.jar) = H1
SHA256(bytes của artifact-b.jar) = H2

H1 == H2  → bằng chứng thực tế rất mạnh rằng hai file có cùng byte
H1 != H2  → chắc chắn byte của hai file khác nhau
~~~

SHA-256 không quan tâm file tên gì, ứng dụng chạy được hay source “giống nhìn bằng mắt” hay không. Chỉ cần một bit trong file JAR thay đổi thì SHA-256 thường sẽ khác hoàn toàn.

**Không đồng nhất các khái niệm:**

| Kiểm tra | Ý nghĩa | Điều chưa được chứng minh |
| --- | --- | --- |
| Hai lần chạy test đều PASS | Logic được các test hiện có chấp nhận | JAR có byte giống nhau |
| Hai JAR cùng kích thước | Kích thước file bằng nhau | Nội dung byte bằng nhau |
| Hai JAR có cùng danh sách class | Có entry names tương ứng | Nội dung/ZIP metadata/timestamp như nhau |
| Hai JAR có cùng SHA-256 | Bằng chứng rất mạnh về byte giống nhau | Nguồn build/trust chain an toàn |
| cmp xác nhận hai file giống hệt | Kiểm tra trực tiếp từng byte | Artifact đúng với source đáng tin hay đã được ký |
| Digest được ký và có attestation | Có thêm bằng chứng provenance nếu xác thực đúng | Không thay thế kiểm tra nội dung, dependency và quy trình build |

Về mặt lý thuyết, hai input khác nhau có thể xảy ra va chạm hash, nhưng đối với kiểm tra reproducible builds thông thường, **SHA-256 trùng nhau là bằng chứng rất mạnh**. Ta bổ sung **cmp** để kiểm tra trực tiếp file khi cùng một máy/runner hỗ trợ.

**SHA-256 là phép kiểm tra tính nhất quán, không phải chứng nhận an toàn chuỗi cung ứng.** Nếu cả hai lần build cùng tải một dependency đã bị thay đổi nhưng có tọa độ giống nhau, hai JAR vẫn có thể có cùng hash. Để xác minh nguồn gốc, cần dependency verification, chữ ký, SBOM/provenance và chính sách publish phù hợp.

## 3. Định nghĩa chính xác “cùng nguồn” và “môi trường sạch”

### 3.1. Cùng nguồn là cùng Git commit, không chỉ cùng branch

Không dùng câu “cả hai đều ở branch main” làm chứng cứ đủ. Branch có thể thay đổi giữa hai lần checkout. Hãy cố định commit:

~~~bash
git rev-parse HEAD
~~~

Đầu ra là một Git object ID tùy repository, ví dụ là chuỗi hex; **không có một stdout cố định cho mọi dự án**. Với script tự động, lưu commit ID vào biến, rồi checkout hai lần **đúng ID**.

Nếu project dùng Git submodules, Git LFS hoặc generated code lấy từ repository khác, cần pin và fetch các input đó theo version/commit tương ứng. Chỉ pin root commit không đủ nếu build kéo dữ liệu mutable từ nơi khác.

### 3.2. Checkout sạch khác với chỉ chạy clean

Lệnh **mvn clean** hoặc **gradle clean** thường xóa output trong thư mục build đã cấu hình như target/ hoặc build/. Nhưng nó **không bảo đảm** xóa mọi file sinh bởi script ngoài quy ước, .env cục bộ, generated sources ngoài build directory, resource nằm trong src/ hoặc trạng thái còn sót trong thư mục dự án.

Vì vậy:

- **Hai checkout mới từ cùng commit** giúp tránh kết quả từ lần chạy trước.
- **clean package / clean bootJar** giúp loại output mặc định trước mỗi lần build.
- **Kho dependency/cache riêng** cho mỗi lần làm phép thử mạnh hơn, tránh hai lượt vô tình dùng trạng thái cache cục bộ chung.
- **Không chuyển artifact ở lần A sang checkout B** trước khi build B.
- **Không trộn file test reports hoặc artifact từ hai lần** vào cùng output path khi tính checksum.

Lưu ý: cache Gradle/Maven không tự đồng nghĩa làm build không tái lập. Cache đúng có thể tái sử dụng output được định danh theo inputs. Tuy nhiên, khi kiểm chứng tính độc lập, cache tách biệt giúp xác định xem kết quả có phụ thuộc vào trạng thái cục bộ ẩn hay không.

### 3.3. Cùng phiên bản công cụ và môi trường

Nên ghi nhận tối thiểu:

~~~text
Git commit ID
OS và kiến trúc CPU
Java vendor + exact Java version
Maven/Gradle version
Spring Boot plugin version
Dependency graph và resolved versions
Locale, timezone, file encoding nếu có ảnh hưởng
Các biến môi trường được build script sử dụng
Build command và flags
Artifact path và SHA-256
~~~

**java -version**, **./mvnw -version** hoặc **./gradlew --version** giúp kiểm tra toolchain. Chỉ ghi “Java 17” chưa chắc đủ khi đang so sánh xuyên môi trường, vì patch release và vendor khác nhau có thể ảnh hưởng output của compiler/tool.

Cần pin Gradle Wrapper/Maven Wrapper ở Git commit. Khi dùng container image, pin **image digest** cho thử nghiệm mạnh hơn; tag có thể bị cập nhật. Trong ví dụ trước mắt, hai lần build chạy trên **cùng hệ điều hành/JDK**, tránh nhầm lỗi môi trường với nội dung build.

## 4. Nguồn biến động trong một Spring Boot executable JAR

### 4.1. Timestamp của các entry ZIP

JAR là một ZIP archive. Entry có thông tin như tên file, compressed bytes, CRC, timestamp và một số thuộc tính bổ sung. Nếu task đóng gói giữ **thời gian sửa file** khác nhau:

~~~text
Lần A: BOOT-INF/classes/... 2026-11-09 09:00:00
Lần B: BOOT-INF/classes/... 2026-11-09 09:02:00
~~~

... thì byte của ZIP/JAR có thể khác dù nội dung class giống nhau.

**Cách giảm sai khác:**

- **Maven:** dùng **project.build.outputTimestamp** và bảo đảm JAR packaging cùng Spring Boot **repackage** nhận timestamp ổn định.
- **Gradle:** với **AbstractArchiveTask**, đặt **preserveFileTimestamps = false** và **reproducibleFileOrder = true** cho các archive tasks cần kiểm tra; Gradle 9+ có mặc định thuận lợi hơn, nhưng bài pin Gradle 8.5 nên đặt rõ ràng.
- **Không** sửa timestamps trong ZIP sau build bằng tay như giải pháp chính; cấu hình ngay từ task tạo archive.

### 4.2. Thứ tự file trong archive

Hai ZIP chứa cùng files, nhưng entry được thêm vào theo thứ tự khác nhau:

~~~text
JAR A: A.class, B.class, application.properties
JAR B: application.properties, B.class, A.class
~~~

... có thể có SHA-256 khác nhau. File systems, thứ tự traversal hoặc custom copy task không ổn định là nguồn sai khác phổ biến.

Với Gradle, **reproducibleFileOrder=true** yêu cầu archive task đi qua files theo thứ tự ổn định. Với Maven, dùng plugin versions hỗ trợ reproducible archive và kiểm tra plugin/custom execution nào tự tạo file thứ tự không xác định.

### 4.3. Manifest và build metadata

Manifest **META-INF/MANIFEST.MF** hoặc **META-INF/build-info.properties** có thể chứa:

~~~text
Build-Time: <thời điểm thực thi>
Build-Host: <hostname máy chạy>
Build-User: <tài khoản người chạy>
Build-Revision: <Git revision>
~~~

Đây là ví dụ những dữ liệu có thể tạo khác biệt. **Spring Boot không tự thêm tất cả bốn trường này mặc định.** Chúng xuất hiện nếu project hoặc plugin đã cấu hình. Nếu một field dùng **new Date()**, **Instant.now()**, thời điểm CI, hostname hoặc đường dẫn workspace thì hai bản dựng sẽ khác nhau.

Hướng giải quyết:

- Nếu cần **revision**, lấy từ **cùng Git commit** cố định.
- Nếu cần **build time**, dùng giá trị reproducible lấy từ release metadata/source commit time hoặc bỏ trường thời gian khỏi artifact và ghi ở CI provenance.
- Với Spring Boot build-info, kiểm tra **build.time** nếu task/goal build-info được bật; không assume mặc định không có timestamp động trong mọi cấu hình.
- Không ghi user name, absolute machine path hoặc môi trường bí mật vào JAR.
- Thay đổi input metadata có chủ đích **phải làm thay đổi checksum**; đó không phải bug.

### 4.4. Annotation processor và generated code

Lombok, MapStruct, OpenAPI generator, protobuf compiler và codegen custom có thể sinh file theo thứ tự hoặc timestamp. Một processor ghi thời gian hiện tại vào source/class sẽ làm output khác dù app logic không đổi.

Kiểm tra:

- Plugin và processor versions được pin.
- Generated source nằm trong output directory sạch.
- Kết quả không phụ thuộc thứ tự duyệt file không ổn định.
- Không nhúng absolute source path hoặc hostname.
- Nếu có compile task incremental, so sánh với **clean** build; không để kết quả cũ ảnh hưởng lần A/B.

### 4.5. Dependencies và plugins

Một dependency có version **1.0-SNAPSHOT**, **1.+** hoặc Maven version range có thể resolve thành byte khác ở hai thời điểm. Maven/Gradle plugins cũng là inputs của build.

**Pin phiên bản** là bước đầu; với yêu cầu cao còn phải lưu và kiểm tra checksums của dependency artifacts. Gradle dependency locking/verification, Maven dependency version policies và repository immutable giúp hạn chế input mutable.

Không kết luận “cùng Git commit thì chắc chắn cùng dependencies” nếu build dùng dynamic selectors, snapshot metadata hoặc remote plugin resolution thay đổi.

### 4.6. Build scripts, OS và công cụ ZIP

Một script gọi công cụ hệ điều hành để tạo archive có thể dùng version thuật toán nén khác nhau, newline convention, file permissions/symlinks hoặc traversal order khác nhau. Những khác biệt này có thể không hiện khi so sánh Java source.

Khi kiểm tra cross-platform, pin image/tool versions, kiểm tra .gitattributes và line endings, file permissions, locale/timezone và native tools. **Đạt PASS trong cùng một máy** chỉ là bước đầu trước khi khẳng định cross-platform reproducibility.

## 5. Ứng dụng Spring Boot Java 17 tối thiểu để kiểm chứng

Tạo một project tên **repro-demo**. Chỉ cần một main class với output cố định, không có build time động, không cần database/web server.

### 5.1. Cấu trúc thư mục

~~~text
repro-demo/
├── pom.xml                    # phương án Maven
├── settings.gradle            # phương án Gradle
├── build.gradle               # phương án Gradle
├── mvnw / mvnw.cmd            # wrapper Maven nếu chọn Maven
├── .mvn/wrapper/...           # wrapper Maven tương ứng
├── gradlew / gradlew.bat      # wrapper Gradle nếu chọn Gradle
├── gradle/wrapper/...         # wrapper Gradle tương ứng
└── src/main/java/com/example/repro/ReproApplication.java
~~~

**Maven và Gradle là hai phương án build thay thế.** Một repository bài tập thực tế chỉ cần bộ file của công cụ đã chọn. Wrapper phải được tạo/scaffold và đưa vào Git; chỉ liệt kê tên wrapper trong sơ đồ không có nghĩa tệp đó tự tồn tại.

### 5.2. Java application

File **src/main/java/com/example/repro/ReproApplication.java**:

~~~java
package com.example.repro;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReproApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReproApplication.class, args);
    }

    @Bean
    CommandLineRunner result() {
        return args -> System.out.println("REPRO_BUILD_OK");
    }
}
~~~

Đây là class Java 17 hoàn chỉnh. Không dùng **Instant.now()**, random UUID hoặc hostname làm dữ liệu đóng gói. Nó cũng không khởi động HTTP server vì dependency là Spring Boot starter cơ bản, không phải starter-web.

Sau khi build executable JAR thành công và chạy:

~~~bash
java -jar target/repro-demo-1.0.0.jar
~~~

hoặc đường dẫn Gradle phù hợp, ứng dụng in dòng **stdout từ code**:

~~~text
REPRO_BUILD_OK
~~~

Spring Boot có thể ghi thêm log và banner tùy cấu hình; **REPRO_BUILD_OK** là dòng cố định của bài thực hành. **Kết quả của java -jar không được dùng thay cho SHA-256**: hai JAR khác byte vẫn có thể cùng in REPRO_BUILD_OK.

## 6. Maven: cấu hình outputTimestamp cho JAR và Spring Boot repackage

### 6.1. pom.xml đầy đủ

Dùng **pom.xml** sau cho phương án Maven:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM hoàn chỉnh** cho demo Spring Boot 3.3.5. Có những điểm cần hiểu:

1. **project.build.outputTimestamp** là một input ổn định cho thời gian ZIP entries, không phải thời điểm hiện tại mỗi lần build. Giá trị mẫu **2024-01-01T00:00:00Z** được chọn vì dễ kiểm chứng, không mang nghĩa ngày phát hành thật.
2. **maven-jar-plugin** tạo JAR thường trong package lifecycle và hỗ trợ outputTimestamp theo cấu hình.
3. **spring-boot-maven-plugin** repackages thành executable JAR, cũng có tham số outputTimestamp. Mặc định của Boot plugin liên quan tới **project.build.outputTimestamp**, nhưng trong bài ta cấu hình rõ để người đọc nhìn thấy hai bước.
4. **spring-boot-starter-parent** cung cấp dependency management và execution repackage tiêu chuẩn. Không cần tự khai báo execution repackage trùng.
5. **project.build.sourceEncoding=UTF-8** làm rõ encoding source/resources khi các plugin liên quan cần giá trị đó.
6. Dependency **spring-boot-starter** không ghi version vì Spring Boot parent quản lý. Version parent/plugin đã pin **3.3.5**.
7. **Không bật spring-boot:build-info với build.time động** hoặc custom manifest value hiện tại, tránh thêm input phi quyết định.

**outputTimestamp không phải nút bảo đảm tuyệt đối.** Nếu có file generated code chứa timestamp, dependency thay đổi, custom packager hoặc thứ tự nén không ổn định, hai JAR vẫn có thể khác. Nó giải quyết **một nguyên nhân rất quan trọng** chứ không thay thế toàn bộ kiểm tra.

### 6.2. Build và lấy artifact

Trong project Maven đã có wrapper:

~~~bash
./mvnw -B -ntp clean package
~~~

Hoặc dùng Maven tương thích đã cài:

~~~bash
mvn -B -ntp clean package
~~~

Trên Windows dùng **mvnw.cmd**. Tùy cách cài Maven, tham số **-ntp** (no transfer progress) giúp log ít nhiễu hơn, không ảnh hưởng nội dung JAR.

Artifact cuối cần kiểm tra:

~~~text
target/repro-demo-1.0.0.jar
~~~

Với Spring Boot parent và goal repackage, đây là executable Boot JAR. Không so sánh tệp **.jar.original** nếu mục tiêu là artifact triển khai.

### 6.3. Khi nào dùng Git commit timestamp thay hằng số?

Bài dùng một timestamp cố định để đơn giản. Trong release pipeline, có thể dùng **timestamp lấy từ commit cố định** (ví dụ từ git log) hoặc release epoch đã được phê duyệt, thay vì hard-code ngày 2024.

**Điều kiện quan trọng:** Hai lần build từ cùng commit phải nhận **cùng giá trị**. Đừng dùng lệnh date +%s mỗi lần build để đặt outputTimestamp, vì nó quay lại vấn đề timestamp động.

Nếu truyền giá trị từ CI qua Maven property, hãy ghi lại nó trong build provenance. Các plugin và build steps khác sinh archive cũng phải nhận cùng chính sách timestamp.

## 7. Gradle: reproducible archive tasks, bootJar và source set

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'repro-demo'
~~~

### 7.2. build.gradle đầy đủ (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Đây là **build.gradle hoàn chỉnh** khi kết hợp với Java class ở mục 5. Mục đích của từng dòng:

- **java + java.toolchain** cấu hình project sử dụng Java 17 cho compiler/toolchain được quản lý.
- **Spring Boot Gradle Plugin 3.3.5** tạo **bootJar** (với Java plugin) để đóng executable Boot archive.
- **io.spring.dependency-management 1.1.6** tích hợp BOM Spring Boot để starter không cần version tường minh.
- **tasks.withType(AbstractArchiveTask).configureEach** áp chính sách cho các archive tasks phù hợp, gồm **jar** và **bootJar** vì bootJar là một dạng archive task. Không chỉ cấu hình **jar** rồi bỏ qua **bootJar**.
- **preserveFileTimestamps = false** ngăn giữ mốc thời gian nguồn khác nhau cho ZIP entries.
- **reproducibleFileOrder = true** bảo đảm thứ tự duyệt file trong archive có tính quyết định hơn, độc lập thứ tự file system.
- Với **Gradle 8.5**, hai thuộc tính này nên được đặt rõ ràng. Với Gradle 9+, chúng có mặc định hỗ trợ reproducible archives tốt hơn, nhưng kiểm tra plugin/custom task vẫn cần thiết.

**Không ghi Build-Time = new Date()** vào manifest của bootJar. Bất kỳ file/thông tin nào chứa dữ liệu từ thời điểm chạy build có thể phá SHA-256 dù archive task được cấu hình đúng.

### 7.3. Build và xác định đúng JAR

~~~bash
./gradlew --no-daemon clean bootJar
~~~

Hoặc nếu muốn thêm các bước verification tiêu chuẩn:

~~~bash
./gradlew --no-daemon clean build
~~~

Trong dự án dùng Spring Boot Gradle plugin, executable archive dự kiến:

~~~text
build/libs/repro-demo-1.0.0.jar
~~~

Gradle có thể tạo plain JAR khác khi chạy **build**:

~~~text
build/libs/repro-demo-1.0.0-plain.jar
~~~

**Phải so sánh đúng loại artifact.** Không lấy **-plain.jar** của lần A so với **bootJar** lần B, cũng không so một file copy/đổi tên được pipeline xử lý khác với JAR gốc mà nghĩ build không tái lập.

### 7.4. Kiểm tra task nào sinh archive

~~~bash
./gradlew tasks --all
./gradlew help --task bootJar
~~~

Khi project có custom Zip/War/Jar task, từng archive có thể cần chính sách timestamp/order tương tự. **Không tự suy ra toàn bộ build reproducible chỉ vì bootJar có cấu hình đúng.** Generated resources, compiled classes và nested dependency JAR đều là inputs.

## 8. Thực nghiệm A/B: hai checkout sạch từ cùng Git commit

Đây là phần trọng tâm. Ta tạo **hai Git worktree mới** từ một commit, build độc lập rồi so SHA-256. Worktree có .git reference tới repository gốc nhưng working files nằm ở hai thư mục khác nhau. Chúng tránh mang theo output untracked từ working tree hiện tại. Vẫn cần pin tools, dependencies và xử lý mọi input ngoài Git.

### 8.1. Điều kiện chạy

- Máy có **Git**, **JDK 17**, Maven/Gradle tương thích và shell Bash.
- Source project đã **commit vào Git**, gồm POM hoặc Gradle files, Java source và Wrapper/scripts cần thiết.
- Trong repository root, lệnh **git rev-parse --show-toplevel** trỏ tới project được build. Nếu project nằm trong subfolder của monorepo, cần điều chỉnh bước chạy tới subfolder đó.
- Project có wrapper hợp lệ **mvnw** hoặc **gradlew** (và file cấu hình wrapper trong Git). Nếu không có wrapper, thay bằng Maven/Gradle cài sẵn đúng version.
- Maven/Gradle download dependencies từ repository có thể truy cập, hoặc đã có chính sách cache/offline hợp lệ.
- Output path đúng theo mục 6 (Maven) hoặc mục 7 (Gradle); không có custom classifier/filename khác.

### 8.2. Script Bash hoàn chỉnh: scripts/check-repro.sh

Tạo file **scripts/check-repro.sh** tại root và commit script nếu muốn tái sử dụng. Nó chấp nhận **maven** hoặc **gradle** để chọn công cụ. Đoạn script dưới đây dùng cùng Git commit và hai **dependency cache/user home riêng**.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: bash scripts/check-repro.sh maven|gradle" >&2
  exit 2
fi

MODE="$1"
if [ "$MODE" != "maven" ] && [ "$MODE" != "gradle" ]; then
  echo "Choose maven or gradle" >&2
  exit 2
fi

REPO="$(git rev-parse --show-toplevel)"
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
TMP="$(mktemp -d)"

A="$TMP/source-a"
B="$TMP/source-b"

cleanup() {
  git -C "$REPO" worktree remove --force "$A" >/dev/null 2>&1 || true
  git -C "$REPO" worktree remove --force "$B" >/dev/null 2>&1 || true
  rm -rf -- "$TMP"
}
trap cleanup EXIT

git -C "$REPO" worktree add --detach "$A" "$COMMIT"
git -C "$REPO" worktree add --detach "$B" "$COMMIT"

if [ "$MODE" = "maven" ]; then
  (
    cd "$A"
    ./mvnw -B -ntp -Dmaven.repo.local="$TMP/maven-a" clean package
  )
  (
    cd "$B"
    ./mvnw -B -ntp -Dmaven.repo.local="$TMP/maven-b" clean package
  )
  ARTIFACT="target/repro-demo-1.0.0.jar"
else
  (
    cd "$A"
    GRADLE_USER_HOME="$TMP/gradle-a" ./gradlew --no-daemon clean bootJar
  )
  (
    cd "$B"
    GRADLE_USER_HOME="$TMP/gradle-b" ./gradlew --no-daemon clean bootJar
  )
  ARTIFACT="build/libs/repro-demo-1.0.0.jar"
fi

FILE_A="$A/$ARTIFACT"
FILE_B="$B/$ARTIFACT"

test -f "$FILE_A"
test -f "$FILE_B"

HASH_A="$(sha256sum "$FILE_A" | awk '{print $1}')"
HASH_B="$(sha256sum "$FILE_B" | awk '{print $1}')"

printf 'COMMIT=%s\n' "$COMMIT"
printf 'BUILD_A_SHA256=%s\n' "$HASH_A"
printf 'BUILD_B_SHA256=%s\n' "$HASH_B"

if [ "$HASH_A" = "$HASH_B" ] && cmp -s "$FILE_A" "$FILE_B"; then
  echo "REPRODUCIBLE=PASS"
else
  echo "REPRODUCIBLE=FAIL" >&2
  exit 1
fi
~~~

Đây là **script Bash đầy đủ** cho Linux và các môi trường Unix có sha256sum. Nó sử dụng **hai worktrees cùng COMMIT**, với **hai thư mục Maven local repository hoặc Gradle user home riêng**.

Điểm quan trọng:

1. **MODE** quyết định Maven hay Gradle; script **không build cả hai công cụ rồi so chéo**.
2. **COMMIT** được lấy một lần, nên hai checkout có cùng source revision.
3. **mktemp -d** tạo workspace tạm độc lập để không lấy build output từ dự án đang làm việc.
4. **git worktree add --detach** tạo hai checkout sạch từ một commit. Giữ Git metadata để các build plugins cần revision có thể nhận ra commit giống nhau.
5. **clean package / clean bootJar** chạy trong từng worktree, không dùng chung target/build.
6. **-Dmaven.repo.local** và **GRADLE_USER_HOME** tách caches; wrapper distribution/dependency downloads có thể phải tải hai lần. Cả hai vẫn truy cập external repositories, do đó chưa bảo đảm remote input bất biến nếu repository có mutable versions.
7. **sha256sum** tạo digest thật. **awk** lấy digest mà không dính filepath; nếu so toàn bộ output sha256sum, đường dẫn A/B khác nhau sẽ khiến text so sánh sai dù checksum giống.
8. **cmp -s** kiểm tra file byte-by-byte khi digest trùng.
9. **exit 1** nếu khác; CI có thể dùng kết quả để fail gate.
10. **trap cleanup** xóa hai Git worktrees và thư mục temp khi script kết thúc. Nếu muốn điều tra khi FAIL, tạm sửa script để **giữ lại workspace** thay vì dọn dẹp ngay; không quên cleanup sau khi phân tích.

**Cảnh báo về cleanup:** Script chỉ xóa thư mục **TMP vừa tạo bởi mktemp** và hai worktree tự đăng ký. Không chạy script sau khi thay mktemp/TMP bằng một đường dẫn tùy ý không kiểm chứng, vì cleanup sẽ xóa đường dẫn đó. Đọc kỹ trước khi sao chép vào CI.

### 8.3. Cách gọi và stdout

Với dự án Maven:

~~~bash
bash scripts/check-repro.sh maven
~~~

Với dự án Gradle:

~~~bash
bash scripts/check-repro.sh gradle
~~~

Nếu **hai JAR byte-identical**, phần cuối output bao gồm:

~~~text
COMMIT=<Git commit ID được đo>
BUILD_A_SHA256=<SHA-256 của JAR A>
BUILD_B_SHA256=<cùng SHA-256>
REPRODUCIBLE=PASS
~~~

Script còn hiển thị log Git/Maven/Gradle nên **không chỉ có bốn dòng trên**. Hai giá trị hash là kết quả thực đo, không có digest cố định sẵn trong tài liệu. Khi FAIL, script in **REPRODUCIBLE=FAIL** và trả exit code khác 0.

**Ranh giới bằng chứng:** Lệnh trên chứng minh tái lập trên hai clean working trees cùng host và những inputs bên ngoài đã resolve trong lần chạy. Nó không tự chứng minh tính tái lập cross-platform hay sau nhiều tháng.

### 8.4. Thử lại theo cách đơn giản nếu không dùng script

Trước khi áp dụng script trong CI, người học có thể làm thủ công:

~~~bash
./mvnw -B -ntp clean package
sha256sum target/repro-demo-1.0.0.jar
~~~

Sau đó checkout cùng commit trong **một thư mục sạch khác**, chạy lại cùng lệnh, ghi nhận hash và so sánh. Với Gradle, thay bằng **./gradlew --no-daemon clean bootJar** và đường dẫn **build/libs/repro-demo-1.0.0.jar**.

**Không đủ** nếu chỉ chạy **mvn package** hai lần trên cùng thư mục mà bỏ clean, hoặc so SHA của JAR cũ còn trong output. Cách thủ công cần đảm bảo xóa output và nguồn không bị thay đổi.

## 9. Windows PowerShell: kiểm tra SHA-256 không cần sha256sum

Windows có cmdlet **Get-FileHash**. Nếu đã có hai bản build trong các đường dẫn A và B, dùng PowerShell:

~~~powershell
$a = Get-FileHash -Algorithm SHA256 -LiteralPath "C:\build-a\target\repro-demo-1.0.0.jar"
$b = Get-FileHash -Algorithm SHA256 -LiteralPath "C:\build-b\target\repro-demo-1.0.0.jar"

Write-Output ("BUILD_A_SHA256=" + $a.Hash)
Write-Output ("BUILD_B_SHA256=" + $b.Hash)

if ($a.Hash -eq $b.Hash) {
    Write-Output "REPRODUCIBLE=PASS"
} else {
    Write-Output "REPRODUCIBLE=FAIL"
    exit 1
}
~~~

Đây là **script minh họa phép so sánh PowerShell**: hai đường dẫn C:\build-a và C:\build-b là nơi bạn phải thực sự tạo hai source checkout và build, **không phải thư mục có sẵn**. Khi dùng Gradle, đổi đường dẫn target/... sang **build\libs\repro-demo-1.0.0.jar**.

**Lưu ý:** PowerShell so sánh hash chính xác theo chữ hex, không đối chiếu byte trực tiếp bằng cmp. Nếu cần phép so sánh nhị phân độc lập, có thể dùng công cụ binary compare của môi trường hoặc tự đọc hai streams; SHA-256 trùng nhau đã là bằng chứng thực tiễn mạnh.

Bên Windows, để build Maven thường dùng **mvnw.cmd**, Gradle dùng **gradlew.bat**. Không copy nguyên lệnh Bash/mktemp/sha256sum rồi mong PowerShell 5.1 hỗ trợ tất cả cú pháp đó.

## 10. Kiểm tra artifact nào chính xác đang được hash

Trong dự án Spring Boot Gradle, một lệnh **build** có thể sinh:

~~~text
build/libs/repro-demo-1.0.0.jar        # executable bootJar
build/libs/repro-demo-1.0.0-plain.jar  # plain jar
~~~

Với Maven Spring Boot parent, sau repackage không classifier thường có:

~~~text
target/repro-demo-1.0.0.jar           # executable Boot JAR
target/repro-demo-1.0.0.jar.original  # JAR trước repackage, khi có
~~~

**Không so plain với executable**, không lấy file đầu tiên match **build/libs/*.jar** vì glob có thể chọn nhầm. Giữ đúng cùng loại archive và path do cùng một task sinh ra.

Dùng JDK để kiểm tra entries:

~~~bash
jar tf target/repro-demo-1.0.0.jar
~~~

hoặc:

~~~bash
jar tf build/libs/repro-demo-1.0.0.jar
~~~

Một Boot executable JAR thông thường có entry dưới:

~~~text
BOOT-INF/classes/com/example/repro/ReproApplication.class
BOOT-INF/lib/...
META-INF/MANIFEST.MF
~~~

**Nếu hai JAR có cùng SHA-256**, chạy một hoặc cả hai bằng **java -jar** để bảo đảm artifact vẫn thực sự khởi động. **Reproducible không tự đồng nghĩa correct**: có thể tái lập một bản build bị lỗi.

## 11. Nếu SHA-256 khác nhau: quy trình phân tích không đoán mò

### Bước 1: xác minh đầu vào thực sự giống nhau

Kiểm tra hai checkout cùng Git commit, cùng Gradle/Maven Wrapper, cùng JDK vendor/patch version, cùng build commands và flags. Nếu một lần có **-DskipTests** hoặc **-PprofileA**, project có thể tạo artifact khác, đó là input khác nhau chứ không phải lỗi reproducibility.

Kiểm tra build có dùng dynamic/snapshot dependencies, plugin version không pin hoặc resource được tải từ network trong quá trình build không.

### Bước 2: xác minh đúng artifact và kích thước

So sánh filename và kích thước bằng **ls -l** trên Linux/macOS hoặc **Get-Item** trong PowerShell. File cùng kích thước vẫn có thể khác byte; file khác kích thước chắc chắn khác. Không coi kích thước bằng nhau là PASS.

### Bước 3: so sánh danh sách ZIP entries

Dùng:

~~~bash
jar tf /path/to/build-a/repro-demo-1.0.0.jar
jar tf /path/to/build-b/repro-demo-1.0.0.jar
~~~

Danh sách có thể cho biết:

- Bản A có thêm **META-INF/build-info.properties** hoặc một generated file.
- Bản B có thêm/thay một dependency JAR trong **BOOT-INF/lib**.
- Thứ tự entries khác nhau.
- Một số tệp resources/class khác nhau.

Nếu entry names khác, tập trung vào source/resources copy tasks, dependencies và code generation.

### Bước 4: so metadata ZIP và timestamp

Nếu hệ thống có công cụ unzip/zipinfo:

~~~bash
unzip -lv /path/to/build-a/repro-demo-1.0.0.jar
unzip -lv /path/to/build-b/repro-demo-1.0.0.jar
~~~

**unzip -lv** cho phép xem phương thức nén, kích thước và timestamp của entries (chi tiết output tùy phiên bản). Nếu cả nội dung tệp có vẻ giống nhưng timestamp/order khác, kiểm tra **outputTimestamp** trên Maven hoặc **preserveFileTimestamps/reproducibleFileOrder** trên Gradle.

### Bước 5: trích xuất hai JAR để so từng entry

Tạo hai thư mục tạm riêng, giải nén vào từng nơi rồi dùng diff theo nội dung. Ví dụ trên Unix:

~~~bash
mkdir -p /tmp/jar-a-inspect /tmp/jar-b-inspect
cd /tmp/jar-a-inspect
jar xf /path/to/build-a/repro-demo-1.0.0.jar
cd /tmp/jar-b-inspect
jar xf /path/to/build-b/repro-demo-1.0.0.jar
diff -qr /tmp/jar-a-inspect /tmp/jar-b-inspect
~~~

**Đây là ví dụ kiểm tra**, hai đường dẫn **/path/to/...** phải được thay bằng paths thật, và trước khi giải nén cần đảm bảo thư mục inspect trống để không dính file từ lượt cũ. **jar xf** giải nén theo working directory hiện tại; không chạy tại project root nếu không muốn tạo BOOT-INF, META-INF ở đó.

**Lưu ý:** Nếu các file sau khi giải nén bằng nhau nhưng JAR hashes khác nhau, nguyên nhân có thể là **ZIP metadata, compression, thứ tự entries hoặc quyền/timestamps** chứ không phải nội dung logic của từng entry.

### Bước 6: dùng diffoscope nếu có

**diffoscope** là công cụ chuyên phân tích khác biệt của artifacts; có thể hiển thị ZIP metadata, nội dung Java class và sự khác nhau của các file bên trong. Nó là **công cụ tùy chọn**, không được cài mặc định với JDK/Maven/Gradle. Khi có sẵn:

~~~bash
diffoscope /path/to/build-a/repro-demo-1.0.0.jar /path/to/build-b/repro-demo-1.0.0.jar
~~~

Kết quả cần được diễn giải: timestamp khác, generated file khác, manifest khác hay dependency JAR khác. Không sửa tất cả cùng lúc rồi mất khả năng xác định nguyên nhân gốc.

### Bước 7: sửa nguyên nhân, chạy lại A/B

Ví dụ:
- Timestamp trong archive khác → cấu hình timestamp normalization.
- Entry order khác → cấu hình reproducible file order/custom task.
- Build-Info time khác → bỏ giá trị động hoặc cố định theo cùng input.
- Manifest Build-Revision khác → lấy revision từ cùng commit.
- H2/Guava/starter/dependency ZIP khác → pin versions, kiểm tra immutable repository/checksums.
- Bytecode khác → pin JDK compiler vendor/patch, processors, compiler options.
- Resource có absolute path → bỏ path môi trường khỏi artifact hoặc chuẩn hóa input.

Sau mỗi sửa, chạy lại **hai clean builds** và so SHA-256; đừng tuyên bố FIXED chỉ vì đã loại một cảnh báo.

## 12. Reproducible build không giống build cache và incremental build

| Khái niệm | Mục tiêu | Phép kiểm tra |
| --- | --- | --- |
| **Incremental compilation** | Chỉ biên dịch lại phần thay đổi | Gradle/Maven chạy nhanh hơn khi input unchanged |
| **Up-to-date checks** | Bỏ qua task khi output được xem là còn hợp lệ | Gradle task báo UP-TO-DATE |
| **Build cache** | Tái sử dụng output dựa trên input fingerprint | Task báo FROM-CACHE khi có cached output |
| **Dependency cache** | Tránh tải lại thư viện đã có | Thấy artifact được dùng từ local cache |
| **Reproducible artifact** | Cùng input tạo ra **cùng byte** | Hai clean build, SHA-256 bằng nhau và/hoặc cmp |
| **Supply-chain verification** | Xác nhận nguồn gốc/toàn vẹn của input/output | Signatures, provenance, checksums, SBOM, policies |

Một **FROM-CACHE** không phải chứng minh build từ source lần B có thể tạo cùng artifact nếu thực thi lại; đó có thể là cùng output được lấy từ cache của A. Vì vậy thử nghiệm mạnh có thể dùng **caches độc lập** hoặc tắt build cache ở giai đoạn kiểm tra tương ứng.

Trong script mục 8, **GRADLE_USER_HOME** và **maven.repo.local** đã tách giữa A và B. Để tránh một build cache ngoài mặc định vẫn được cấu hình bởi tổ chức, cần kiểm tra các cơ chế remote cache, settings và environment thực tế. Với Gradle có thể chạy **--no-build-cache** trong lệnh khi CI yêu cầu kiểm thử không dùng cached task outputs; Maven cũng có thể có extensions riêng cần được kiểm soát.

## 13. Thử nghiệm trong hai container/runner sạch

### 13.1. Mức bằng chứng

Có thể chia các mức độ:

1. **Hai lần chạy clean cùng thư mục**: hữu ích để phát hiện timestamp, nhưng vẫn có state ẩn từ workspace.
2. **Hai Git checkout/worktree khác nhau trên cùng máy**: loại phần lớn output cũ và đường dẫn source giống/khác có kiểm soát.
3. **Hai runner/container độc lập cùng image digest**: tách môi trường tốt hơn và pin OS/JDK/tools.
4. **Hai hệ điều hành hoặc kiến trúc khác nhau**: kiểm tra cross-platform reproducibility, khó hơn do native tools/file metadata.
5. **Rebuild độc lập từ source bởi bên khác**: hướng tới verifiable/reproducible supply chain và provenance.

Bài thực hành đạt mức 2; hướng triển khai CI có thể nâng lên mức 3.

### 13.2. Cần pin gì trong container?

- **Container image bằng immutable digest**, không chỉ latest hoặc tag mutable.
- **JDK vendor + exact update version**, không chỉ Java major 17.
- **Maven/Gradle Wrapper**, plugin versions và repositories.
- **Dependencies/lockfile/verification metadata** khi dự án sử dụng.
- **Locale/TZ/encoding** nếu codegen hoặc plugins đọc môi trường.
- **Source commit**, submodules, LFS objects và build scripts.
- **Không mount chung thư mục output** giữa hai job.
- **Không cho các bước sinh tài nguyên phụ thuộc thời điểm hiện tại** hoặc dịch vụ mutable khi không được pin.

**Kết quả giống nhau giữa hai container cùng image** vẫn chưa tuyệt đối bảo đảm tất cả thời điểm tương lai giống nhau nếu dependencies mutable hoặc build chạy script truy cập internet theo thời điểm.

## 14. Tích hợp so sánh SHA-256 vào CI/CD

### 14.1. Gate cho một project

Với Linux CI runner có Git/JDK/Gradle/Maven sẵn theo policy, có thể gọi:

~~~bash
bash scripts/check-repro.sh maven
~~~

hoặc:

~~~bash
bash scripts/check-repro.sh gradle
~~~

CI coi exit code **0** là phép thử A/B PASS, exit code **1** là hai artifact khác nhau, exit code **2** là sử dụng script sai. Script còn có thể fail vì thiếu dependencies, wrapper, network hoặc permission; những lỗi đó **không nên diễn giải là SHA mismatch** nếu chưa tới bước so sánh.

Nên lưu **commit ID, build image digest, toolchain versions, SHA-256 A/B và log** vào báo cáo build. Không cần lưu toàn bộ hai artifact ở mọi pull request nếu chi phí quá lớn, nhưng khi FAIL nên giữ ít nhất hai JAR dưới dạng CI artifacts để dùng diffoscope điều tra.

### 14.2. Khi release

Thực tiễn tốt:

1. Build và chạy tests trên source commit đã chốt.
2. Tạo artifact với toolchain/dependency versions được pin.
3. Rebuild ở môi trường độc lập theo chính sách, tính SHA-256 A/B.
4. Nếu khớp, công bố **hash cùng artifact release** và provenance phù hợp.
5. Ký artifact/checksum và đưa lên registry/repository immutable theo quy trình tổ chức.
6. Khi consumer download artifact, so checksum và xác minh chữ ký nếu có.

**Lưu ý:** SHA-256 A/B trùng nhau chỉ thể hiện **tính tái lập trong điều kiện thử nghiệm**. Nó không thay thế unit/integration tests, static analysis, vulnerability scanning, license checks hoặc security review.

### 14.3. Khi dùng Docker image làm artifact phát hành

Có hai loại digest:

- **SHA-256 của Spring Boot JAR**: hash chính xác bytes file JAR.
- **Digest container image**: hash manifest/layers/config theo định dạng image; còn phụ thuộc Dockerfile, base image, layer timestamps và build tooling.

Hai JAR giống hệt không đảm bảo **hai Docker image digest** giống nhau nếu image creation thêm timestamp/metadata khác. Nếu mục tiêu bài là JAR, **hash JAR trước khi đưa vào image**. Khi muốn reproducible container image, cần thiết kế phép thử riêng cho toàn bộ OCI image và layers.

## 15. Kiểm tra phần khác biệt bằng Java 17 (không phụ thuộc SHA tool hệ điều hành)

Để tránh phụ thuộc sha256sum khi chạy trên nhiều hệ điều hành, bạn có thể dùng **MessageDigest** trong Java 17 để tính SHA-256.

Tạo file **Sha256Compare.java** tại root project (cùng cấp với pom.xml hoặc build.gradle), **không** đưa vào src/main/java vì nó là công cụ kiểm tra build, không phải một phần của ứng dụng.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class Sha256Compare {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java Sha256Compare.java <artifact-a> <artifact-b>");
        }

        String a = sha256(Path.of(args[0]));
        String b = sha256(Path.of(args[1]));

        System.out.println("BUILD_A_SHA256=" + a);
        System.out.println("BUILD_B_SHA256=" + b);

        if (a.equals(b)) {
            System.out.println("REPRODUCIBLE=PASS");
        } else {
            System.out.println("REPRODUCIBLE=FAIL");
            System.exit(1);
        }
    }

    private static String sha256(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream stream = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Đây là **Java 17 source-file launcher program hoàn chỉnh**, dùng **MessageDigest**, **Files** và **HexFormat** từ JDK. Nó đọc file bằng stream, tránh phải nạp toàn bộ JAR lớn vào RAM.

Sau khi hai JAR tồn tại, dùng đường dẫn thực tế:

~~~bash
java Sha256Compare.java /path/to/build-a/repro-demo-1.0.0.jar /path/to/build-b/repro-demo-1.0.0.jar
~~~

**/path/to/... là đường dẫn minh họa phải thay bằng file thật.** Với Gradle, dùng path build/libs tương ứng.

Nếu hai file khớp, chương trình in:

~~~text
BUILD_A_SHA256=<digest thực đo>
BUILD_B_SHA256=<cùng digest thực đo>
REPRODUCIBLE=PASS
~~~

Với hai file khác nhau, dòng cuối là **REPRODUCIBLE=FAIL** và exit code 1. **Không có SHA-256 cố định trước build**. Khác với script Bash ở mục 8, Java verifier chỉ so hash và không gọi cmp; cần thêm byte compare khi muốn kiểm tra trực tiếp.

## 16. Một số tình huống cần hiểu đúng

### 16.1. Hai JAR cùng source nhưng khác timestamp: có cần lo?

Nếu source, bytecode class và dependencies không đổi nhưng ZIP entry timestamps khác, ứng dụng có thể hoạt động y hệt. Tuy nhiên, **mục tiêu reproducible build đã không đạt** theo tiêu chuẩn byte-for-byte. Nếu môi trường yêu cầu artifact signing, caching, provenance hoặc xác minh release, khác biệt này vẫn đáng sửa.

### 16.2. Hai JAR có SHA-256 giống nhau nhưng source thay đổi?

SHA trùng nghĩa là bytes artifact cùng nhau, không chứng minh Git commit giống nhau. Có thể source chỉ thay đổi comments hoặc test code không đi vào artifact. Cần **ghi nhận commit ID** và toolchain, không dùng hash để tự suy ngược rằng source bằng nhau.

### 16.3. Test code thay đổi nhưng Boot JAR giống nhau?

Nếu test classes/resources không được đóng gói vào main Boot JAR, thay test code có thể không đổi JAR. Điều đó có thể hợp lệ; tuy nhiên thay test có thể ảnh hưởng release qualification dù artifact byte-identical.

### 16.4. Maven và Gradle cùng build một ứng dụng có phải cùng SHA?

**Không.** Hai công cụ có archive packager, bytecode/compiler configuration, manifest metadata, ZIP entries/compression/order khác nhau. Chỉ nên so **Maven A với Maven B**, hoặc **Gradle A với Gradle B** trước. Yêu cầu cross-tool byte-identical là một mục tiêu khác, đòi hỏi cấu hình và kiểm chứng riêng.

### 16.5. Dependency đã pin version nhưng cùng tọa độ bị ghi đè

Repository cho phép thay đổi artifact dưới cùng GAV có thể khiến Maven/Gradle tải byte khác sau vài giờ. Dùng immutable release repositories và dependency checksum verification. **Version pin không thay thế checksum pin** khi nguồn artifact không đáng tin hoặc có khả năng mutable.

### 16.6. Dùng timestamp cố định “giả” có làm mất thông tin build?

Một mốc ZIP reproducible không được hiểu là timestamp thực hiện build. Thời điểm release thực tế có thể lưu ở **CI provenance, release manifest hoặc build logs**. Điều quan trọng là **phân biệt metadata xác định nội dung** với **metadata vận hành thay đổi theo lần chạy**.

### 16.7. Muốn so cả plain JAR, sources JAR, WAR và container

Phải so từng loại với chính loại tương ứng: bootJar A vs bootJar B, plainJar A vs plainJar B, sourcesJar A vs sourcesJar B, bootWar A vs bootWar B. Mỗi artifact có task/format riêng và có thể cần tùy chỉnh reproducibility riêng. Không suy diễn từ Boot JAR PASS rằng mọi artifact khác đều PASS.

## 17. Các lỗi phổ biến và cách khắc phục

**Lỗi 1 — Chỉ so hai stdout của java -jar.** Cùng in REPRO_BUILD_OK không chứng minh JAR byte-identical. **Sửa:** hash đúng hai artifact cuối.

**Lỗi 2 — So SHA của source zip thay vì executable JAR.** Bài yêu cầu artifact build; source zip có thể giống dù output khác. **Sửa:** hash target/repro-demo-1.0.0.jar hoặc build/libs/repro-demo-1.0.0.jar.

**Lỗi 3 — So Maven Boot JAR với Gradle Boot JAR.** Khác tooling và ZIP format choices là input khác. **Sửa:** trước tiên so hai lượt cùng công cụ/cấu hình.

**Lỗi 4 — Hai lần chạy cùng thư mục mà không clean.** Output cũ có thể được tái sử dụng; phép thử không kiểm chứng môi trường sạch. **Sửa:** hai clean checkout và clean build.

**Lỗi 5 — Dùng chung artifact output folder giữa A và B.** Một lần build có thể ghi đè hoặc dùng nhầm file. **Sửa:** hai worktrees/output dirs tách biệt.

**Lỗi 6 — So nguyên dòng sha256sum có chứa filepath.** Hash giống nhưng đường dẫn khác khiến chuỗi output khác. **Sửa:** chỉ so 64 ký tự digest (awk field 1).

**Lỗi 7 — Chỉ kiểm tra kích thước JAR.** Kích thước giống không có nghĩa bytes giống. **Sửa:** SHA-256 và cmp.

**Lỗi 8 — Timestamp ZIP entry khác.** Tệp source được copy với modified time thay đổi. **Sửa:** Maven outputTimestamp; Gradle preserveFileTimestamps=false.

**Lỗi 9 — Thứ tự ZIP entries không ổn định.** Filesystem traversal hoặc custom task làm order khác. **Sửa:** Gradle reproducibleFileOrder=true và kiểm tra packager khác.

**Lỗi 10 — Dùng Spring Boot build-info với thời gian hiện tại.** META-INF/build-info.properties có build.time khác. **Sửa:** dùng timestamp xác định hoặc bỏ build.time khi không cần.

**Lỗi 11 — Build manifest chứa username/hostname hoặc absolute path.** Hai runner khác metadata. **Sửa:** không embed giá trị môi trường không cần thiết; giữ chúng trong CI provenance.

**Lỗi 12 — Gradle chỉ chỉnh task jar, bỏ task bootJar.** Plain JAR có thể tái lập nhưng executable JAR vẫn khác. **Sửa:** cấu hình đúng AbstractArchiveTask/bootJar và so Boot JAR.

**Lỗi 13 — Maven chỉ chỉnh maven-jar-plugin, không xét Boot repackage.** Archive cuối do Boot plugin tạo lại; có thể vẫn có sự khác biệt. **Sửa:** kiểm tra outputTimestamp cho cả hai bước.

**Lỗi 14 — Dùng dynamic version hoặc SNAPSHOT không bất biến.** Dependencies thay đổi giữa A/B. **Sửa:** pin versions và kiểm tra checksums.

**Lỗi 15 — JDK vendor/patch khác nhau.** Compiler output hoặc tool defaults có thể khác. **Sửa:** pin JDK vendor + exact version, Gradle toolchain/Maven compiler.

**Lỗi 16 — Script dùng date/UUID trong resource generation.** Build input thay đổi từng lần. **Sửa:** bỏ randomness hoặc lấy từ dữ liệu nguồn cố định.

**Lỗi 17 — Generated code phụ thuộc order của Map hoặc filesystem.** Output class/source thay đổi. **Sửa:** sắp xếp input keys/files deterministically trong generator.

**Lỗi 18 — Chọn nhầm Gradle -plain.jar hoặc Maven .jar.original.** Hash không cùng loại artifact. **Sửa:** chọn Boot executable JAR do task/goal phát hành.

**Lỗi 19 — Bật remote build cache và nghĩ cùng hash chứng minh compile lặp lại.** Lần B có thể chỉ lấy output từ cache A. **Sửa:** tách cache hoặc dùng --no-build-cache khi làm thử nghiệm độc lập.

**Lỗi 20 — Hash khác nhưng script vẫn exit 0.** CI không phát hiện regression. **Sửa:** so digest/cmp và exit khác 0 khi mismatch.

**Lỗi 21 — Giải nén hai JAR vào cùng folder.** Files bị ghi đè, làm diff sai. **Sửa:** tách directory inspect và dọn trước khi so.

**Lỗi 22 — Không lưu hai artifact khi CI FAIL.** Không đủ dữ liệu tìm nguyên nhân. **Sửa:** upload hai JAR, versions và logs để điều tra bằng diffoscope.

**Lỗi 23 — Tuyên bố cross-platform reproducible sau hai build cùng máy.** Kết luận vượt quá phép thử. **Sửa:** phân loại rõ mức bằng chứng và thực hiện trên runner/OS khác khi cần.

**Lỗi 24 — Hash bằng nhau được coi là chứng minh an ninh tuyệt đối.** Hai build có thể cùng dùng dependency độc hại. **Sửa:** tách reproducibility khỏi supply-chain verification, SBOM, chữ ký và security checks.

## 18. Checklist trước khi chốt kết quả SHA-256

- [ ] Ghi nhận **Git commit ID** và nguồn phụ thuộc ngoài Git.
- [ ] Chọn rõ artifact **Maven Boot JAR** hoặc **Gradle bootJar**, không chọn nhầm plain JAR.
- [ ] Pin Maven/Gradle Wrapper, JDK 17 vendor/patch, Spring Boot plugin và dependencies.
- [ ] Tắt/bỏ dữ liệu build-time động không cần thiết trong generated resources/manifest/build-info.
- [ ] Maven dùng **project.build.outputTimestamp** cho archive creation và repackage.
- [ ] Gradle đặt **preserveFileTimestamps=false** và **reproducibleFileOrder=true** cho archive tasks liên quan.
- [ ] Tạo **hai checkout/worktree sạch cùng commit**.
- [ ] Dùng riêng output directories và nếu có thể riêng dependency cache.
- [ ] Chạy **clean package** hoặc **clean bootJar** trong từng checkout.
- [ ] Xác minh hai file thực sự tồn tại và là cùng loại artifact.
- [ ] Tính **SHA-256 từng file**, so giá trị hash chứ không so cả filepath.
- [ ] Dùng **cmp** để kiểm tra byte-by-byte nếu công cụ hỗ trợ.
- [ ] Khi FAIL, so entries, timestamps, manifest, generated code và dependency graph.
- [ ] Khi PASS, tiếp tục smoke test **java -jar** và các quality gates khác.
- [ ] Báo cáo **COMMIT, toolchain, hash, kết quả PASS/FAIL** cùng mức độ môi trường được kiểm chứng.
- [ ] Nếu có yêu cầu release security, bổ sung signatures, provenance và kiểm tra dependencies.

## 19. Tài liệu tham khảo chính thức

- Gradle — Reproducible Archives / Working with Files: https://docs.gradle.org/8.5/userguide/working_with_files.html
- Gradle — AbstractArchiveTask API, preserveFileTimestamps và reproducibleFileOrder: https://docs.gradle.org/8.5/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Maven — Guide to Configuring Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Maven JAR Plugin — outputTimestamp: https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html
- Spring Boot 3.3 Maven Plugin — Repackage / outputTimestamp: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 Gradle Plugin — Executable Archive Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Oracle Java 17 — MessageDigest API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Oracle Java 17 — HexFormat API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- Reproducible Builds — Definitions and background: https://reproducible-builds.org/docs/definition/

**Ghi nhớ:** Để kết luận hai bản dựng từ cùng nguồn có thể tái lập, hãy xây **đúng cùng executable Spring Boot JAR** từ **hai checkout sạch của cùng Git commit**, dùng **toolchain/dependencies cố định**, chuẩn hóa **ZIP timestamps và file order**, rồi **so SHA-256** (và đối chiếu byte trực tiếp khi có thể). **Hash giống nhau** là bằng chứng mạnh cho tính đồng nhất byte trong điều kiện đã kiểm tra; **hash khác nhau** là tín hiệu phải tìm chính xác input/packaging metadata gây biến động, không phải lý do để bỏ bước kiểm tra.