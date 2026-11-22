# Sử dụng Maven Wrapper qua mvnw và mvnw.cmd

## 1. Maven Wrapper là gì?

**Maven Wrapper** là bộ script nằm cùng mã nguồn, cho phép chạy dự án bằng **phiên bản Apache Maven được chính dự án chỉ định**. Hai script chính:

- `mvnw`: dùng trên Linux/macOS hoặc môi trường có shell tương thích POSIX.
- `mvnw.cmd`: dùng trên Windows với Command Prompt hoặc PowerShell.

Thông thường, lệnh `mvn clean package` yêu cầu máy đã cài Maven và cấu hình `PATH`. Với wrapper, dự án có thể chạy `./mvnw clean package` (Linux/macOS) hoặc `.\mvnw.cmd clean package` (Windows PowerShell). Wrapper sẽ tìm bản Maven đã tải sẵn hoặc tải đúng bản cần dùng trước khi gọi Maven. Những tham số `clean`, `package`, `verify`, `-D...` được truyền tiếp cho Maven.

**Giới hạn quan trọng:** Maven Wrapper chọn/cung cấp **Maven**, không tự cài JDK và không tự quyết định phiên bản dependency trong `pom.xml`. Máy vẫn cần JDK tương thích với dự án và bản Maven được chọn. Trong ngữ cảnh Spring Boot hiện đại, JDK 17+ là lựa chọn phổ biến; yêu cầu chính xác phụ thuộc phiên bản Spring Boot.

```text
Checkout mã nguồn (pom.xml + wrapper files)
             |
             v
 ./mvnw ...       hoặc       .\mvnw.cmd ...
             |
             v
Đọc .mvn/wrapper/maven-wrapper.properties
             |
             v
Tìm hoặc tải Maven distribution đã cấu hình
             |
             v
Chạy Maven thực tế với các goal/phase đã truyền
             |
             v
Resolve dependency -> compile -> test -> package/verify
```

Dùng wrapper giúp người mới và hệ thống CI chạy **cùng phiên bản Maven**, giảm tình trạng “máy tôi build được vì Maven khác phiên bản”. Tuy nhiên, khả năng tái lập build còn phụ thuộc JDK, plugin, dependency, repository và môi trường.

## 2. Các file của Maven Wrapper trong dự án

Một dự án Maven có wrapper thường có cấu trúc:

```text
my-app/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    └── main/
        └── java/
```

| Thành phần | Chức năng |
|---|---|
| `pom.xml` | Khai báo artifact, dependency, plugin và quy trình Maven build |
| `mvnw` | Script wrapper cho shell kiểu Unix |
| `mvnw.cmd` | Script wrapper cho Windows |
| `.mvn/wrapper/maven-wrapper.properties` | Cấu hình địa chỉ/phiên bản Maven cần dùng, có thể kèm checksum |
| `.mvn/wrapper/maven-wrapper.jar` | Chỉ có ở **một số loại** wrapper |
| `.mvn/wrapper/MavenWrapperDownloader.java` | Có thể xuất hiện khi dùng loại wrapper bootstrap qua Java source |

**Không phải dự án nào cũng có `maven-wrapper.jar`.** Apache Maven Wrapper Plugin hiện hành mặc định sinh loại `only-script`: script tự tải Maven distribution, không cần wrapper JAR. Các dự án cũ hoặc dùng loại khác có thể kèm thêm JAR hoặc Java downloader. Không tự ý xóa chúng khi chưa biết kiểu wrapper của dự án.

Các script và cấu hình wrapper nên được commit vào Git để người clone dự án có thể sử dụng ngay. Trên Linux/macOS, file `mvnw` còn cần **quyền execute**; Git có thể lưu executable bit cho file đó.

## 3. Chạy wrapper sau khi clone dự án

Mở terminal ở **thư mục gốc chứa `pom.xml` và `mvnw`/`mvnw.cmd`**. Các lệnh tương ứng:

| Công việc | Linux/macOS | Windows PowerShell |
|---|---|---|
| Kiểm tra Maven | `./mvnw -version` | `.\mvnw.cmd -version` |
| Biên dịch mã chính | `./mvnw compile` | `.\mvnw.cmd compile` |
| Chạy unit test | `./mvnw test` | `.\mvnw.cmd test` |
| Xóa output cũ và đóng gói | `./mvnw clean package` | `.\mvnw.cmd clean package` |
| Kiểm tra đến phase verify | `./mvnw verify` | `.\mvnw.cmd verify` |
| Build theo chế độ CI | `./mvnw -B -ntp clean verify` | `.\mvnw.cmd -B -ntp clean verify` |

Trên **Windows Command Prompt** (cmd.exe), dùng tên file batch trực tiếp:

```bat
mvnw.cmd -version
mvnw.cmd clean package
mvnw.cmd verify
```

Trên **Windows PowerShell**, thêm `.\` vì shell thường không tự tìm chương trình trong thư mục hiện tại:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd clean package
.\mvnw.cmd verify
```

Trên **Linux/macOS**:

```bash
./mvnw -version
./mvnw clean package
./mvnw verify
```

`-B` là batch mode, thích hợp trong CI; `-ntp` giảm các dòng tiến độ tải về. `-version`/`-v` cho biết **phiên bản Maven thực tế mà wrapper sử dụng**, cùng thông tin Java và hệ điều hành. Đừng giả định kết quả của `mvn -version` bằng kết quả của `./mvnw -version`: lệnh `mvn` chạy Maven từ `PATH`, còn wrapper chọn bản Maven từ cấu hình dự án.

Nếu trên Unix gặp `Permission denied`, thử `chmod +x mvnw` rồi lưu executable bit vào Git. Nếu file có line ending Windows CRLF làm shell báo `/bin/sh^M` hoặc “bad interpreter”, khôi phục line ending LF cho script `mvnw`. Lệnh này chỉ giải quyết quyền hoặc định dạng file; không sửa nguyên nhân liên quan JDK, mạng hay dependency.

## 4. Sinh wrapper cho dự án chưa có

**Cần có Maven cài sẵn ở bước khởi tạo wrapper**, vì dự án chưa có script để gọi. Với dự án có `pom.xml`, chạy từ root:

```bash
mvn -N wrapper:wrapper -Dmaven=3.9.9 -Dtype=only-script
```

Ý nghĩa:

- `wrapper:wrapper`: goal của **Apache Maven Wrapper Plugin**, sinh hoặc cập nhật file wrapper.
- `-N` (`--non-recursive`): chỉ chạy trên project hiện tại; hữu ích ở root dự án nhiều module.
- `-Dmaven=3.9.9`: ví dụ **pin Maven 3.9.9**; đây là bản minh họa có thật, không phải khẳng định bản mới nhất. Chọn bản phù hợp dự án.
- `-Dtype=only-script`: wrapper script nhẹ, không cần thêm file wrapper JAR vào repository.

Sau khi tạo, có thể kiểm tra:

```bash
chmod +x mvnw
./mvnw -version
./mvnw clean verify
```

Trên Windows, sau khi sinh wrapper dùng `mvnw.cmd -version` ở Command Prompt hoặc `.\mvnw.cmd -version` ở PowerShell. Với dự án đã có sẵn wrapper, **không cần chạy lại `wrapper:wrapper` mỗi lần build**. Dùng ngay script có sẵn; lệnh tạo/cập nhật wrapper thuộc công việc bảo trì cấu hình build.

Đưa các file cần thiết vào version control (lệnh minh họa trong repository của riêng bạn):

```bash
git add pom.xml mvnw mvnw.cmd .mvn/wrapper
git commit -m "Add Maven Wrapper"
```

### Các loại wrapper cần phân biệt

| Loại | Cách bootstrap | Điểm cần nhớ |
|---|---|---|
| `only-script` | `mvnw`/`mvnw.cmd` tải trực tiếp Maven distribution | Mặc định khi cài mới bằng plugin hiện hành; không dùng wrapper JAR |
| `bin` | JAR wrapper được cung cấp trong `.mvn/wrapper` | Thường cần commit `maven-wrapper.jar` |
| `script` | Script tải wrapper JAR khi cần rồi sử dụng nó | Cơ chế tải khác `only-script` |
| `source` | Có Java source để hỗ trợ tải wrapper JAR | Có thêm file Java downloader |

Tập file chính xác có thể phụ thuộc phiên bản plugin/wrapper. Nếu đổi loại, hãy dùng goal `wrapper:wrapper` với `-Dtype=...` rồi kiểm tra toàn bộ file mới sinh; không thay đổi hoặc xóa ngẫu nhiên các file bootstrap.

## 5. Ví dụ Java 17 chạy được từ đầu đến cuối

Ví dụ thuần Java dưới đây giúp phân biệt vai trò của wrapper với lệnh `java`. Tạo dự án:

```text
maven-wrapper-demo/
├── pom.xml
└── src/main/java/vn/example/wrapper/WrapperDemo.java
```

Nội dung `pom.xml` hoàn chỉnh:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-wrapper-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/vn/example/wrapper/WrapperDemo.java`:

```java
package vn.example.wrapper;

public class WrapperDemo {
    public static void main(String[] args) {
        System.out.println("Maven Wrapper OK");
    }
}
```

Sau khi tạo các file và sinh wrapper theo mục 4, với JDK 17+ trên Linux/macOS:

```bash
./mvnw clean package
java -cp target/classes vn.example.wrapper.WrapperDemo
```

Windows PowerShell:

```powershell
.\mvnw.cmd clean package
java -cp target/classes vn.example.wrapper.WrapperDemo
```

**Stdout chính xác của lệnh `java -cp ...`** (không tính log Maven ở lệnh build trước):

```text
Maven Wrapper OK
```

Cũng có thể biên dịch trực tiếp bằng JDK 17, để thấy rõ wrapper chỉ phục vụ **lệnh Maven**, không cần khi chạy Java đã biên dịch:

```bash
javac -d out src/main/java/vn/example/wrapper/WrapperDemo.java
java -cp out vn.example.wrapper.WrapperDemo
```

Lệnh chạy cũng in `Maven Wrapper OK`. `-d out` đặt bytecode ở `out/vn/example/wrapper`; `-cp out` đưa thư mục root đó lên classpath.

Sau `package`, Maven tạo `target/maven-wrapper-demo-1.0.0.jar`. Đây là **JAR thư viện thông thường**: ví dụ trên chưa thêm `Main-Class` vào manifest, nên không mặc định `java -jar target/maven-wrapper-demo-1.0.0.jar` có thể chạy. Muốn chạy bằng `java -jar` cần cấu hình manifest phù hợp hoặc dùng cơ chế executable JAR của Spring Boot.

## 6. Dùng Maven Wrapper trong dự án Spring Boot

Với Spring Boot Maven project đã có wrapper, cách gọi Maven vẫn là cùng goal/phase, chỉ khác script:

```bash
# Linux/macOS
./mvnw clean package
./mvnw verify
./mvnw dependency:tree
./mvnw spring-boot:run
```

```powershell
# Windows PowerShell
.\mvnw.cmd clean package
.\mvnw.cmd verify
.\mvnw.cmd dependency:tree
.\mvnw.cmd spring-boot:run
```

- `clean package`: xóa output của build trước rồi chạy các phase đến `package`, gồm compile và test theo cấu hình.
- `verify`: chạy đến phase kiểm tra artifact; trong một số dự án còn có integration test/check bổ sung.
- `dependency:tree`: in cây dependency để chẩn đoán phiên bản hoặc xung đột.
- `spring-boot:run`: goal của **Spring Boot Maven Plugin**, chạy ứng dụng từ project nếu plugin và lớp khởi động đã được cấu hình.

Ví dụ đoạn `pom.xml` cho dự án dùng `spring-boot-starter-parent`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Đây **chỉ là phần `build` chèn vào POM Spring Boot có parent thích hợp**, không phải một POM độc lập. Khi plugin và execution `repackage` được cấu hình, `package` có thể tạo executable JAR chạy bằng `java -jar`. Nếu dùng POM không kế thừa Spring Boot parent, cần khai báo phiên bản và cấu hình plugin/execution phù hợp.

**Maven Wrapper không tự biến JAR thường thành Spring Boot executable JAR.** Việc đóng gói là trách nhiệm của plugin và cấu hình build; wrapper chỉ chọn bản Maven để thực thi. Nó cũng không tự thêm starter web, web controller hay mở cổng HTTP.

## 7. Cấu hình phiên bản Maven và nơi lưu cache

File `.mvn/wrapper/maven-wrapper.properties` chứa `distributionUrl`, ví dụ:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

URL trên là ví dụ pin **Maven 3.9.9**. Với dự án thực tế, chọn phiên bản đã được đội ngũ kiểm thử, sau đó kiểm tra lại bằng `./mvnw -version` hoặc `.\mvnw.cmd -version`. Có thể cập nhật wrapper bằng goal `wrapper:wrapper` hoặc thay `distributionUrl` có kiểm soát. Khi cập nhật wrapper đã tồn tại, plugin thường giữ kiểu phân phối cũ nếu không truyền `-Dtype`.

Cần phân biệt các đường dẫn:

| Vị trí | Chứa gì? |
|---|---|
| `.mvn/wrapper/maven-wrapper.properties` | Cấu hình wrapper **được commit** trong dự án |
| `~/.m2/wrapper/dists` | Maven distribution wrapper đã tải và giải nén |
| `~/.m2/repository` | Maven local repository lưu dependency, plugin, parent POM, artifact |
| `target/` | Các file tạo từ build hiện tại; thường được dọn bởi phase `clean` |

Lần đầu, wrapper có thể tải Maven distribution và Maven sau đó tải tiếp các dependency/plugin cần thiết. Các lần sau có thể dùng cache. **Có Maven trong cache không đồng nghĩa build offline chắc chắn thành công**: local repository vẫn có thể thiếu dependency hoặc Maven plugin.

Một số bản wrapper hỗ trợ `distributionSha256Sum` để xác minh distribution tải về; các kiểu dùng wrapper JAR có thể dùng `wrapperSha256Sum`. Hash phải lấy từ nguồn phát hành đáng tin cậy, không tự đặt giá trị minh họa. Dùng HTTPS và repository/mirror được tin cậy; nếu checksum không khớp, điều tra nguyên nhân, không xóa kiểm tra một cách tùy tiện.

Wrapper pin Maven, còn:
- **JDK**: cài ở máy/CI, có thể được chuẩn hóa qua toolchain hay quy định dự án.
- **Dependencies**: khai báo trong `pom.xml`, parent/BOM, dependency management.
- **Maven plugins**: được quản lý bởi POM, parent và plugin management.
- **Wrapper scripts/bootstrap**: là các file source control trong dự án; có phiên bản riêng với Maven distribution.

## 8. Sử dụng Maven Wrapper trong CI

Để build nhất quán trên máy phát triển và CI:

1. Commit `mvnw`, `mvnw.cmd`, `.mvn/wrapper` và `pom.xml` vào repository.
2. Giữ executable bit của `mvnw` trong Git để runner Linux chạy được.
3. Cấu hình JDK phù hợp; dùng wrapper làm lệnh Maven chính.
4. Bảo đảm môi trường có quyền truy cập Maven distribution và dependency repository (hoặc đã có cache/mirror).
5. Chạy `verify` hoặc mục tiêu kiểm thử tương đương trước khi phát hành artifact.

Ví dụ workflow GitHub Actions cho dự án Java 17 có wrapper, đặt tại `.github/workflows/build.yml`:

```yaml
name: Java build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Build with Maven Wrapper
        run: ./mvnw -B -ntp verify
```

`setup-java` cung cấp JDK; `mvnw` cung cấp phiên bản Maven của dự án. Caching cho local Maven repository giúp tiết kiệm thời gian, nhưng không thay thế việc pin phiên bản Maven hay kiểm tra artifact. Ví dụ giả định executable bit của `mvnw` đã được lưu đúng trong repository.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khái niệm cần kiểm tra | Cách xử lý |
|---|---|---|
| `./mvnw: Permission denied` | Quyền chạy script Unix | `chmod +x mvnw`; lưu executable bit trong Git |
| `./mvnw: No such file or directory` | Sai thư mục, thiếu script, shebang/CRLF | Chạy từ root; kiểm tra file và line ending LF |
| PowerShell không nhận `mvnw.cmd` | Quy tắc tìm file tại thư mục hiện tại | Dùng `.\mvnw.cmd` |
| `JAVA_HOME is not defined correctly` hoặc không tìm thấy Java | JDK/`JAVA_HOME`/`PATH` | Kiểm tra `java -version`, `javac -version` và JDK tương thích |
| Tải Maven distribution thất bại | `distributionUrl`, proxy, mạng, TLS/mirror | Kiểm tra URL, kết nối và cấu hình mạng |
| Maven đã khởi động nhưng `Could not resolve ...` | Dependency/plugin/repository | Kiểm tra `pom.xml`, `settings.xml`, repository và cache dependency |
| `mvn -version` khác `./mvnw -version` | Maven hệ thống so với Maven được pin | Kiểm tra `distributionUrl` và cấu hình dự án |
| Báo thiếu `maven-wrapper.jar` | File bootstrap thiếu hoặc sai kiểu wrapper | Kiểm tra kiểu `bin`/`script`/`source` và các file đi kèm |
| Checksum mismatch | File tải về khác checksum kỳ vọng | Đối chiếu URL và hash từ nguồn đáng tin, không bỏ xác minh tùy tiện |
| Chạy offline thất bại | Thiếu distribution hoặc dependency trong cache | Chuẩn bị cache/mirror và thử lại sau khi tải đủ |
| `java -jar` báo thiếu main manifest | JAR chưa được đóng gói thành executable JAR | Kiểm tra `Main-Class` hoặc Spring Boot `repackage` |

Khi chẩn đoán, có thể bật Maven debug:

```bash
./mvnw -X validate
```

Để in thêm thông tin **wrapper bootstrap** trên Linux/macOS:

```bash
MVNW_VERBOSE=true ./mvnw -version
```

Hoặc Windows PowerShell:

```powershell
$env:MVNW_VERBOSE = 'true'
.\mvnw.cmd -version
Remove-Item Env:MVNW_VERBOSE
```

Debug log có thể chứa URL repository nội bộ hoặc biến môi trường; xem lại trước khi chia sẻ.

## 10. Tự kiểm tra sau bài học

- Có đủ `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties` và `pom.xml` trong root dự án.
- Dùng đúng script theo hệ điều hành và đúng root; trên PowerShell nhớ `.\`.
- `-version` cho thấy Maven đã được pin; JDK phù hợp với ứng dụng.
- `clean verify` hoặc `clean package` chạy thành công, không bị lỗi bootstrap, dependency hay compile.
- Đã lưu file wrapper và quyền execute trong Git để cả nhóm và CI dùng chung.
- Với Spring Boot, đã cấu hình plugin đóng gói nếu muốn `java -jar` chạy executable JAR.

**Cách nhớ:** `mvnw` và `mvnw.cmd` là hai cách khởi chạy **Maven được dự án cấu hình**. Chúng giúp chuẩn hóa Maven trên các máy; còn JDK, dependency, plugin, classpath và loại artifact vẫn do môi trường và POM quyết định.

**Tài liệu chính thức:**
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
- [Maven Wrapper Plugin — wrapper goal](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)