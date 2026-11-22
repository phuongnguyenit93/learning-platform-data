# prepare-package, package và artifact được tạo trong Maven

Trong **default build lifecycle** của Maven, `prepare-package` và `package` là hai *phase* liên tiếp nhưng có nhiệm vụ khác nhau. `prepare-package` dành cho các bước chuẩn bị ngay trước đóng gói; `package` là điểm mà plugin đóng gói thường tạo ra artifact phân phối như JAR, WAR hoặc EAR. Để biết một lệnh thực sự tạo tệp gì, phải xét thêm `<packaging>`, những plugin goal được gắn vào các phase và cấu hình thực tế của dự án.

Ví dụ:

```bash
mvn clean prepare-package
mvn clean package
```

Cả hai lệnh đều chạy các phase đứng trước phase đích, bao gồm compile và unit test của kiểu đóng gói JAR thông thường. Nhưng với `jar` packaging mặc định, **lệnh thứ nhất không tự tạo JAR chính**, còn lệnh thứ hai chạy goal `jar:jar` tại `package` và thường tạo file `target/<artifactId>-<version>.jar`.

## 1. Phân biệt phase, goal và artifact

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Lifecycle** | Chuỗi các phase định nghĩa tiến trình build | `default`, `clean`, `site` |
| **Phase** | Mốc trong một lifecycle; không tự mô tả chính xác code thực thi | `compile`, `test`, `prepare-package`, `package` |
| **Plugin** | Thành phần mở rộng cung cấp tác vụ build | `maven-resources-plugin`, `maven-jar-plugin` |
| **Goal** | Tác vụ cụ thể của plugin, có thể gắn vào phase | `resources:copy-resources`, `jar:jar` |
| **Execution** | Một cấu hình gọi goal tại phase xác định | `<execution><phase>prepare-package</phase>...` |
| **Artifact** | Sản phẩm Maven định danh bằng tọa độ và các thuộc tính khác | `vn.example:packaging-demo:1.0.0`, JAR của dự án |

**Phase không phải tên plugin hoặc tên tệp.** Khi gõ `mvn package`, Maven chạy mọi phase cần thiết từ đầu **default lifecycle** đến `package`, đồng thời thực thi những plugin goal được binding vào các phase. Một phase không có goal nào được gắn vào có thể trôi qua mà không thực hiện tác vụ riêng.

**Artifact chính (main artifact)** là đối tượng Maven quản lý để có thể cài vào local repository hay publish. Nó thường có `groupId`, `artifactId`, `version`, `packaging/type`; sản phẩm đóng gói vật lý phụ thuộc loại packaging. File được tạo thêm bởi plugin có thể là **attached artifact** với classifier, hoặc chỉ là file hỗ trợ trong `target` chưa được Maven attach. Không phải mọi file trong `target` đều là artifact được publish.

## 2. Vị trí chính xác của prepare-package và package

Trình tự rút gọn của default lifecycle cho dự án `<packaging>jar</packaging>` thường là:

```text
validate
   |
process-resources   -- resources:resources
   |
compile             -- compiler:compile
   |
process-test-resources
   |
test-compile        -- compiler:testCompile
   |
test                -- surefire:test
   |
prepare-package     -- chạy các goal chuẩn bị do dự án/plugin gắn vào
   |
package             -- jar:jar
   |
pre-integration-test / integration-test / post-integration-test
   |
verify
   |
install
   |
deploy
```

Đây là **sơ đồ rút gọn**: giữa các mốc có thêm phase như `initialize`, `generate-sources`, `process-sources`, `process-classes`, `generate-test-sources`, `process-test-sources`, `generate-test-resources` và `process-test-classes`. Các goal hiển thị là binding điển hình của kiểu đóng gói JAR; project có thể bổ sung hoặc thay đổi execution bằng POM, plugin và profile.

Một số điều rất dễ nhầm:

- Gọi `mvn prepare-package` **có chạy** các phase trước đó trong default lifecycle (bao gồm `test` nếu có binding), nhưng **không tự động chạy** phase `package` ở phía sau.
- Gọi `mvn package` **có chạy** `prepare-package` trước khi đến `package`; không cần gõ thêm `prepare-package` vào CLI.
- `clean` thuộc **clean lifecycle riêng**. `mvn clean package` là chạy phase `clean` rồi chạy default lifecycle đến `package`, chứ `clean` không phải một phase đứng ngay trước `prepare-package`.
- `install` và `deploy` **đứng sau** `package`: `mvn package` không tự cài artifact vào `~/.m2/repository` hoặc xuất bản lên remote repository.
- `verify` đứng sau `package`, dành cho các kiểm tra thêm, gồm tích hợp khi project cấu hình; `package` thông thường chỉ bao gồm unit test và đóng gói, không đồng nghĩa toàn bộ kiểm thử tích hợp đã hoàn tất.

## 3. prepare-package: chuẩn bị dữ liệu để đóng gói

Theo Maven Lifecycle Reference, `prepare-package` dành cho **operations necessary to prepare a package before the actual packaging**, thường để lại một bản nội dung đã xử lý nhưng chưa đóng gói. Với các project JAR thông thường, Maven không tự gắn goal mặc định vào phase này. Vì thế nếu POM không có execution phù hợp, gọi `mvn prepare-package` có thể chỉ chạy các việc ở phase trước như compile/test mà không tạo thêm tệp riêng tại phase `prepare-package`.

Các tác vụ thường được gắn vào `prepare-package` theo nhu cầu:

- Copy những file cấu hình/metadata sẽ nằm trong JAR hoặc WAR.
- Sinh hoặc cập nhật thông tin build tại `target/classes`, là thư mục JAR plugin sẽ lấy nội dung.
- Chuẩn bị thư mục staging/unpacked directory cho plugin đóng gói.
- Kết hợp resource đã generate ở các bước trước và xử lý lần cuối trước packaging.

**Cần đặt goal vào đúng thời điểm.** Nếu unit test cần đọc file được tạo trước khi test, `prepare-package` là quá muộn vì `test` đã chạy. Khi đó nên dùng `generate-resources`, `process-resources` hoặc phase sớm hơn thích hợp. Ngược lại, nếu mục tiêu là sửa/copy tài nguyên đã build xong ngay trước khi đóng gói, `prepare-package` là vị trí hợp lý.

Ví dụ cấu hình **một goal** `resources:copy-resources` chạy tại `prepare-package` (đây là đoạn XML đặt trong `<build><plugins>` của POM):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>copy-extra-file-before-package</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>copy-resources</goal>
            </goals>
            <configuration>
                <outputDirectory>${project.build.outputDirectory}</outputDirectory>
                <resources>
                    <resource>
                        <directory>${project.basedir}/src/package-resources</directory>
                        <filtering>false</filtering>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Với Maven Java project thông thường, `project.build.outputDirectory` mặc định là `target/classes`. Cấu hình trên sẽ copy file từ `src/package-resources` sang đây **sau test, trước goal đóng gói JAR**. `<id>` chỉ dùng để định danh execution; `<phase>` quyết định thời điểm, còn `<goal>copy-resources</goal>` mới là thao tác thực hiện.

Nếu bỏ `<phase>prepare-package</phase>` hoặc khai báo goal khác, không thể đoán nó chạy tại mốc nào chỉ từ tên plugin. Hãy kiểm tra cấu hình execution và metadata phase mặc định của từng goal.

## 4. package: tạo sản phẩm phân phối theo loại packaging

`package` là phase đóng gói mã đã build thành sản phẩm phân phối. Maven chọn goal mặc định dựa trên `<packaging>` và các lifecycle mappings của loại project đó.

| `<packaging>` | Goal đóng gói điển hình | Sản phẩm chính thường thấy |
| --- | --- | --- |
| `jar` (mặc định nếu không khai báo) | `maven-jar-plugin:jar` | `target/<artifactId>-<version>.jar` |
| `war` | `maven-war-plugin:war` | `target/<artifactId>-<version>.war` |
| `ear` | `maven-ear-plugin:ear` | `target/<artifactId>-<version>.ear` |
| `pom` | Không có goal đóng gói binary mặc định tại `package` | POM là artifact metadata; không có JAR do packaging mặc định |
| `maven-plugin` | Goal tạo JAR và bổ sung plugin metadata | JAR triển khai một Maven plugin |

Ví dụ khai báo packaging:

```xml
<groupId>vn.example</groupId>
<artifactId>my-library</artifactId>
<version>1.2.3</version>
<packaging>jar</packaging>
```

Nếu không có tùy biến tên file hoặc plugin đặc biệt, kết quả chính là `target/my-library-1.2.3.jar`. Đường dẫn thư mục build mặc định là `target` (tương đương `${project.build.directory}`). Tên file mặc định thường lấy từ `${project.build.finalName}`, mặc định là `${project.artifactId}-${project.version}`. Dự án có thể đổi `<finalName>`, output directory, cấu hình WAR/JAR plugin hoặc thêm thao tác repackage, nên không nên luôn suy tên file bằng cách ghép tọa độ.

**Điều Maven không mặc nhiên làm tại `package`:**

- Không tự tải tất cả runtime dependencies rồi nhúng vào JAR. JAR thông thường chứa code/resources của chính project; muốn **fat/uber JAR** có thể cần Shade/Assembly plugin hoặc bước repackaging tương ứng.
- Không tự thêm `Main-Class` để có thể chạy bằng `java -jar`. Cần manifest phù hợp, và nếu project có runtime dependencies thì phải xử lý classpath/dependency.
- Không tự cài artifact vào local repository; đó là `install`.
- Không tự publish artifact lên Maven Central hoặc kho của công ty; đó là `deploy`.
- Không bảo đảm chỉ tạo **một** file: plugin bổ sung có thể tạo source JAR, test JAR, shaded JAR, checksum hoặc file tạm; chỉ artifact được gắn đúng với project/attach mới tham gia install/deploy theo cơ chế Maven.

## 5. Ví dụ chạy được trên Java 17: chuẩn bị resource rồi tạo JAR

Mục tiêu: quan sát `prepare-package` copy một file văn bản vào `target/classes`, còn `package` tạo JAR chứa class Java và file này.

### 5.1. Cấu trúc project

```text
packaging-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── vn/example/packaging/App.java
    └── package-resources/
        └── build-note.txt
```

`src/package-resources` là thư mục **tự đặt cho ví dụ này**; nó không phải `src/main/resources` mặc định của Maven. Vì thế goal `copy-resources` được dùng để đưa tài nguyên vào nơi JAR plugin đóng gói.

Nội dung `src/package-resources/build-note.txt`, lưu bằng UTF-8:

```text
Chuẩn bị ở prepare-package
```

Nội dung `src/main/java/vn/example/packaging/App.java`:

```java
package vn.example.packaging;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class App {
    public static void main(String[] args) throws IOException {
        try (InputStream in = App.class.getResourceAsStream("/build-note.txt")) {
            if (in == null) {
                throw new IllegalStateException("Không tìm thấy build-note.txt");
            }
            String note = new String(in.readAllBytes(), StandardCharsets.UTF_8).strip();
            System.out.println(note);
        }
    }
}
```

Chương trình tìm `build-note.txt` ngay tại **root của classpath**. Trong JAR đúng, file sẽ ở đường dẫn `build-note.txt`, còn class ở `vn/example/packaging/App.class`. `InputStream.readAllBytes()` và `String.strip()` hoạt động trên Java 17; try-with-resources sẽ đóng luồng tự động.

### 5.2. POM hoàn chỉnh

Nội dung `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>packaging-demo</artifactId>
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
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <executions>
                    <execution>
                        <id>copy-build-note</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>copy-resources</goal>
                        </goals>
                        <configuration>
                            <outputDirectory>${project.build.outputDirectory}</outputDirectory>
                            <resources>
                                <resource>
                                    <directory>${project.basedir}/src/package-resources</directory>
                                    <filtering>false</filtering>
                                </resource>
                            </resources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

POM dùng chuẩn POM model `4.0.0`, JDK 17 và pin version các plugin quan trọng để ví dụ ít phụ thuộc phiên bản mặc định từ môi trường. Cần có Maven đã cài hoặc Maven Wrapper hợp lệ, JDK 17+ và khả năng tải plugin/dependency ở lần chạy đầu.

Chỉ cần ba file đã nêu (POM, class Java, build-note.txt) để tái hiện việc copy rồi đóng gói. Ví dụ không có unit test; Maven vẫn đi qua phase `test` theo lifecycle.

### 5.3. Chạy đến prepare-package

Trong thư mục `packaging-demo`:

```bash
mvn -B clean prepare-package
```

Sau khi build **thành công và đã clean trước đó**, thư mục đích điển hình chứa:

```text
target/
└── classes/
    ├── build-note.txt
    └── vn/example/packaging/App.class
```

Trong lần chạy này, các phase đến `test` đã diễn ra, goal `resources:copy-resources` đã copy `build-note.txt` vào `target/classes`, nhưng binding `jar:jar` của phase `package` **chưa chạy**. Vì vậy **JAR chính `target/packaging-demo-1.0.0.jar` chưa được tạo từ build mới này**. Nếu không dùng `clean` và có JAR cũ trong `target` thì sự tồn tại của nó không chứng minh `prepare-package` đã tạo JAR.

Có thể quan sát file:

```bash
# Linux/macOS
ls -l target/classes/build-note.txt
ls -l target/classes/vn/example/packaging/App.class
```

```powershell
# Windows PowerShell
Get-Item target/classes/build-note.txt
Get-Item target/classes/vn/example/packaging/App.class
```

### 5.4. Chạy đến package và kiểm tra sản phẩm

Tiếp tục tại cùng thư mục:

```bash
mvn -B package
jar tf target/packaging-demo-1.0.0.jar
java -cp target/packaging-demo-1.0.0.jar vn.example.packaging.App
```

Lệnh `mvn package` ở lượt này thực thi lại các phase bắt buộc đến `package` (Maven có thể tận dụng đầu ra đã build) và cuối cùng chạy `jar:jar`. Lệnh `jar tf` liệt kê nội dung JAR; trong đó phải tìm được ít nhất:

```text
build-note.txt
vn/example/packaging/App.class
```

Đây là **hai mục cần kiểm tra**, không phải toàn bộ stdout hay thứ tự xuất hiện của `jar tf`. JAR còn có metadata như `META-INF`.

Lệnh `java -cp ... vn.example.packaging.App` có stdout chính xác:

```text
Chuẩn bị ở prepare-package
```

Kết quả này chứng tỏ file được tạo sẵn ở `prepare-package` đã được đóng vào JAR tại `package` và chương trình đọc được qua classpath. Bản JAR ví dụ không cấu hình manifest `Main-Class`, vì vậy **không thể mặc định thay lệnh trên bằng `java -jar target/packaging-demo-1.0.0.jar`**.

Trên Windows PowerShell, các lệnh Maven và JDK tương tự:

```powershell
mvn.cmd -B clean prepare-package
mvn.cmd -B package
jar.exe tf target/packaging-demo-1.0.0.jar
java.exe -cp target/packaging-demo-1.0.0.jar vn.example.packaging.App
```

Nếu dùng Maven Wrapper, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `mvn.cmd` bằng `.\mvnw.cmd` trên Windows. Các file `mvnw`/`mvnw.cmd` cần thực sự tồn tại trong dự án; ví dụ này chỉ mô tả ba file tối thiểu khi Maven đã cài.

## 6. Khi nào artifact xuất hiện, và nó nằm ở đâu?

Đối với POM ví dụ, có thể quan sát sự khác biệt qua bảng:

| Lệnh chạy từ trạng thái sạch | Đầu ra điển hình | Có JAR chính? |
| --- | --- | --- |
| `mvn clean compile` | `target/classes/.../App.class` | Chưa |
| `mvn clean test` | Classes, test output nếu có test | Chưa |
| `mvn clean prepare-package` | Classes cộng `target/classes/build-note.txt` | Chưa |
| `mvn clean package` | Các đầu ra trên cộng `target/packaging-demo-1.0.0.jar` | **Có** |
| `mvn clean verify` | JAR cộng các kết quả xác minh phụ thuộc cấu hình | **Có** |
| `mvn clean install` | JAR và artifact được cài vào local repository | **Có** |

Các dòng mô tả **ví dụ packaging JAR và bindings đã khai báo**, không phải lời hứa với mọi loại packaging. Nếu bạn gắn một goal tự tạo ZIP tại `prepare-package`, nó có thể tạo một file ZIP sớm hơn; điều đó không đồng nghĩa goal đóng gói chính tại `package` đã chạy. Ngược lại, với `<packaging>pom</packaging>`, `mvn package` không tạo JAR chính theo mặc định.

### 6.1. target/classes khác JAR

- `target/classes`: dạng **unpacked** chứa class/resource để công cụ build khác xử lý.
- `target/packaging-demo-1.0.0.jar`: file ZIP/JAR chứa class/resource đã đóng gói và metadata.
- `~/.m2/repository/vn/example/packaging-demo/1.0.0/...`: artifact được **install** sau `mvn install`, thường bao gồm POM và JAR tương ứng, chưa có chỉ sau `mvn package`.

Từ góc nhìn của Maven, artifact chính được quản lý theo tọa độ `vn.example:packaging-demo:1.0.0`. File trong `target` mới là sản phẩm build tại workspace; `install`/`deploy` sử dụng artifact do giai đoạn package gắn vào project.

### 6.2. finalName, classifier và attached artifacts

Ví dụ:

```xml
<build>
    <finalName>release-app</finalName>
</build>
```

Khi đặt đoạn này trong POM JAR ví dụ, tên file trong `target` thường trở thành `release-app.jar`. Tuy nhiên, **tọa độ** vẫn là `vn.example:packaging-demo:1.0.0`. Khi artifact được cài/publish, Maven repository sử dụng quy tắc định danh artifact theo tọa độ; `finalName` không đổi `artifactId` hoặc `version`.

Nếu cấu hình thêm `maven-source-plugin` để tạo source JAR hoặc `maven-javadoc-plugin` để tạo tài liệu JAR, Maven có thể **attach** các artifact mang classifier như `sources`, `javadoc`. Chúng khác JAR chính. Một file tùy ý tạo trong `target` sẽ không tự được Maven install/deploy nếu chưa được plugin attach theo đúng cơ chế.

### 6.3. Multi-module và packaging POM

Dự án có POM root `<packaging>pom</packaging>` và `<modules>`:

```xml
<packaging>pom</packaging>
<modules>
    <module>api</module>
    <module>service</module>
</modules>
```

Đây là **đoạn POM**, không phải tài liệu XML độc lập. `mvn package` ở root thường chạy reactor gồm các module được chọn. Root packaging `pom` không tạo JAR chính theo mặc định; module `api`/`service` có thể tạo JAR/WAR riêng nếu packaging và cấu hình của chúng yêu cầu. Không tìm thấy file `target/root.jar` không đồng nghĩa cả reactor đóng gói lỗi.

## 7. Bind goal vào phase đúng cách

Có hai nguồn goal được chạy khi gọi `mvn package`:

1. **Goal mặc định theo packaging**: ví dụ JAR binding `resources:resources` tại `process-resources`, `compiler:compile` tại `compile`, `surefire:test` tại `test` và `jar:jar` tại `package`.
2. **Goal do POM/profile/plugin thêm vào** qua `<executions>`: ví dụ `resources:copy-resources` tại `prepare-package`.

Khi khai báo execution:

```xml
<execution>
    <id>prepare-before-jar</id>
    <phase>prepare-package</phase>
    <goals>
        <goal>copy-resources</goal>
    </goals>
</execution>
```

Đoạn này cần nằm trong một `<plugin>` hỗ trợ goal `copy-resources` và có cấu hình cần thiết (như `outputDirectory`, `resources`). Một `<execution>` không xác định đủ plugin/goal không thể hoạt động độc lập. `<id>` hữu ích để Maven và POM inheritance nhận diện execution khi merge/cấu hình chồng nhau.

**Thứ tự chạy:** Maven đi theo thứ tự phase. Khi nhiều goal gắn cùng phase, thứ tự có thể phụ thuộc lifecycle binding, thứ tự khai báo và khả năng điều chỉnh execution. Với những goal cùng phase, không nên dựa vào việc tên plugin đứng trước trong log trên mọi phiên bản; kiểm tra effective POM và log thực tế, đồng thời đặt bước phụ thuộc vào phase thích hợp nếu có thể.

**Tránh gọi goal đóng gói trực tiếp để thay thế lifecycle:**

```bash
mvn jar:jar
```

Lệnh này gọi một goal của JAR Plugin trực tiếp, không đương nhiên thực thi toàn bộ chuỗi `compile → test → prepare-package` như `mvn package`. Nếu `target/classes` chưa có, JAR có thể thiếu class/resource hoặc goal thất bại. Muốn có sản phẩm build đáng tin, ưu tiên:

```bash
mvn clean package
```

Nếu có nhu cầu chạy một goal độc lập, cần hiểu rõ preconditions và các output đã có.

## 8. Kiểm tra bằng lệnh Maven và log

Những lệnh hữu ích khi không chắc plugin nào chạy ở phase nào:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn -B clean prepare-package
mvn -B package
```

`help:effective-pom` là goal của Maven Help Plugin; nó tạo POM đã hợp nhất từ parent, profiles, defaults và phần cấu hình được kế thừa. Nếu plugin Help chưa nằm trong cache hoặc mạng bị chặn, lệnh này có thể thất bại vì không resolve được plugin, chứ không phải cấu trúc lifecycle sai.

Trong log hãy tìm goal có tên như:

```text
--- resources:3.3.1:copy-resources (copy-build-note) @ packaging-demo ---
--- jar:3.4.2:jar (default-jar) @ packaging-demo ---
```

Đó là **mẫu log minh họa**, không cam kết chuỗi chữ, format hay vị trí chính xác của các dòng giữa mọi Maven/plugin version. Điều quan trọng là quan sát `copy-resources` chạy tại `prepare-package` **trước** `jar:jar` ở `package`.

Cách kiểm tra thực tế không dựa vào log duy nhất:

- Trước `package`: kiểm tra `target/classes/build-note.txt` và `target/classes/vn/example/packaging/App.class`.
- Sau `package`: kiểm tra có `target/packaging-demo-1.0.0.jar`, xem `jar tf` có cả class và resource.
- Chạy Java bằng `java -cp` để chứng minh resource có thể được tải từ artifact.
- Nếu project còn chạy Shade/Repackage hoặc goal bổ sung, xác định chúng tạo/đổi/attach artifact nào trước khi kết luận file cuối cùng.

## 9. Lỗi thường gặp và cách xử lý

| Hiểu nhầm / lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| “`mvn prepare-package` phải tạo JAR.” | Goal đóng JAR mặc định nằm ở `package` | Chạy `mvn package`; kiểm tra execution thực tế |
| “`mvn package` không chạy prepare-package.” | Maven chạy tuần tự các phase đến mốc được gọi | Gắn goal chuẩn bị ở `<phase>prepare-package</phase>` |
| Chạy `prepare-package` rồi thấy JAR cũ | File từ lần build trước còn trong `target` | Dùng `mvn clean prepare-package` khi đối chiếu |
| File thêm trước package không có trong JAR | Copy sai thư mục, phase quá muộn, bị exclude hoặc plugin ghi đè | Kiểm tra `target/classes` và cấu hình JAR/WAR plugin |
| Unit test không đọc được file sinh ở prepare-package | Phase `test` chạy trước `prepare-package` | Sinh file ở phase sớm hơn nếu test cần |
| Gõ `mvn jar:jar` trên project sạch và JAR thiếu class | Goal gọi trực tiếp, bỏ qua compile/test | Chạy `mvn package` |
| `target` có JAR mà `~/.m2/repository` chưa có | `package` chưa cài artifact | Chạy `mvn install` nếu thật sự cần local install |
| JAR không chạy bằng `java -jar` | Thiếu `Main-Class` hoặc runtime classpath | Cấu hình manifest, dependency strategy; thử `java -cp` |
| Build thành công nhưng không có JAR ở root | Root packaging `pom`, hoặc output/finalName đã tùy chỉnh | Kiểm tra module/packaging, target file và effective POM |
| Có nhiều JAR trong `target` | Source/test/shade/spring-boot plugin tạo hoặc attach artifact thêm | Phân biệt main artifact, classifier và attached artifacts |

### Câu hỏi kiểm tra nhanh

**Tình huống:** một POM `jar` khai báo `resources:copy-resources` ở `prepare-package` và dùng `jar:jar` mặc định ở `package`. Nếu chạy `mvn clean prepare-package` rồi `mvn package`, sau mỗi lệnh có thể mong đợi gì?

**Đáp án:** sau lệnh đầu, mã đã compile và các resource chuẩn bị đã có ở output directory, nhưng chưa có JAR mới vì phase `package` chưa chạy. Sau lệnh thứ hai, Maven chạy các phase đến `package`, goal `jar:jar` đóng class/resource thành JAR chính. Nếu dự án có plugin/goal khác được bind thêm, cần xét chúng để biết toàn bộ output.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Lifecycle Reference và built-in bindings](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html#lifecycle-reference)
- [Apache Maven Resources Plugin — Copy Resources](https://maven.apache.org/plugins/maven-resources-plugin/examples/copy-resources.html)
- [Apache Maven JAR Plugin — Usage](https://maven.apache.org/plugins/maven-jar-plugin/usage.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
