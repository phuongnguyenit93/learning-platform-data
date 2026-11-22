# Xác minh lại kiểm thử và classpath sau khi giải quyết xung đột phiên bản trong Maven

## 1. Vì sao sửa dependency conflict chưa phải là hoàn tất?

Trong Maven, một thư viện có thể đi vào dự án qua nhiều đường phụ thuộc với những phiên bản khác nhau. Maven chọn một phiên bản theo các quy tắc phân giải (*dependency mediation*, `dependencyManagement`, dependency trực tiếp, phạm vi scope và các yếu tố khác). Việc sửa `pom.xml` để không còn một xung đột hiển thị trong `dependency:tree` chỉ là **bước đầu**.

Một thay đổi phiên bản có thể:

- Làm mã sản phẩm **biên dịch được nhưng thất bại khi chạy** vì API hoặc binary compatibility đã thay đổi.
- Giúp unit test chạy nhưng ứng dụng triển khai thực tế lại dùng **JAR khác** trên runtime classpath.
- Tạo lỗi như `NoSuchMethodError`, `NoClassDefFoundError` hoặc `ClassCastException` chỉ khi một nhánh nghiệp vụ cụ thể được thực thi.
- Thay đổi test classpath vì dependency test hoặc plugin đã sử dụng một phiên bản khác.
- Khiến module A và module B trong cùng Maven Reactor phân giải **những graph khác nhau**.
- Tạo artifact mới nhưng script khởi chạy vẫn trỏ tới JAR cũ trong `lib/` hoặc image/container.
- Chỉ hoạt động trên laptop vì local repository còn cache; agent CI sạch không tái tạo được.

Vì vậy, tiêu chuẩn hoàn tất sau khi giải quyết xung đột phải gồm **cả cấu hình, dependency graph, classpath thực tế và kết quả kiểm thử**:

1. **Đúng phiên bản đã chọn:** artifact mong đợi xuất hiện trong graph của đúng module và scope.
2. **Không còn đường xung đột chưa được giải thích:** so sánh tree đầy đủ, nhất là các nhánh bị bỏ qua hoặc được quản lý.
3. **Biên dịch và test thực sự chạy:** thực hiện build sạch, đọc số lượng test, failure và error.
4. **Runtime tải đúng thư viện:** kiểm tra JAR được class loader nạp, không chỉ tên artifact trong POM.
5. **Đầu ra triển khai phù hợp:** kiểm tra JAR, thư mục `lib`, WAR, container hoặc cấu hình launcher thực tế.
6. **Kết quả tái lập trên CI:** cùng commit, Maven/JDK, profile, repository và lệnh build.

**Thông điệp chính:** “Maven đã chọn version X” và “ứng dụng/test đang nạp bytecode của version X” là **hai khẳng định khác nhau**, phải có bằng chứng riêng.

## 2. Nhắc lại cơ chế chọn version để biết cần xác minh điều gì

Giả sử ứng dụng `app` phụ thuộc vào module `api`, và cả hai liên quan tới Apache Commons Lang:

```text
app
├── demo:api:1.0.0:compile
│   └── org.apache.commons:commons-lang3:3.14.0:compile
└── org.apache.commons:commons-lang3:3.12.0:compile  ← app khai báo trực tiếp
```

Đây là **sơ đồ hai đường yêu cầu dependency trước khi Maven chốt graph hiệu lực**, không phải output của một lệnh Maven cụ thể. Nếu app trực tiếp yêu cầu `commons-lang3:3.12.0` trong khi api yêu cầu `3.14.0` qua một đường bắc cầu, đường trực tiếp thường thắng theo quy tắc **nearest definition** của Maven 3. Điều đó **không đồng nghĩa bản 3.12.0 tương thích** với tất cả các API mà api được biên dịch dựa trên 3.14.0.

Các cơ chế chính:

| Cơ chế | Maven làm gì? | Cần kiểm tra sau sửa |
| --- | --- | --- |
| **Nearest definition** | Với các version cạnh tranh, ưu tiên đường dependency gần project hơn; nếu cùng độ sâu, thứ tự khai báo có thể quyết định | Đường dẫn dẫn tới version được chọn có đúng ý định? |
| **Dependency trực tiếp** | Một dependency ở chính POM của app thường có độ sâu 1 | Có direct declaration vô tình ghim bản cũ không? |
| **`dependencyManagement`** | Có thể quản lý version/scope của dependency phù hợp, kể cả thông tin hiệu lực của nhánh bắc cầu | POM con có kế thừa management? Có ghi đè version trực tiếp? |
| **`exclusions`** | Loại một dependency bắc cầu qua một cạnh chỉ định | Sau loại trừ, runtime/test còn class cần thiết không? |
| **`optional=true`** | Dependency tùy chọn không tự lan sang project tiêu thụ thư viện | Module sử dụng tính năng có khai báo direct dependency chưa? |
| **Scope propagation** | Xác định `compile`, `runtime`, `test`... của dependency khi đi qua nhiều cạnh | JAR có ở classpath cần thiết không? |
| **Reactor** | Xây module có quan hệ phụ thuộc trong một lần Maven session | Đúng module/artifact nội bộ được build hay đang dùng bản cache? |

**Lưu ý:** bảng “nearest definition” và bảng lan truyền scope giải quyết những câu hỏi khác nhau: **version nào được chọn** và **artifact đó xuất hiện ở scope nào**. Một version đúng nhưng scope sai vẫn có thể dẫn đến lỗi compile hoặc runtime.

## 3. Bộ bằng chứng cần thu trước và sau khi sửa

Nên lưu trạng thái **trước khi thay đổi** và **sau khi thay đổi** bằng cùng Maven/JDK và cùng tập module để so sánh được. Những công cụ chính:

| Bằng chứng | Lệnh/cách kiểm tra | Trả lời câu hỏi |
| --- | --- | --- |
| Version Maven/JDK | `mvn -version` hoặc Maven Wrapper `./mvnw -version` | Công cụ đang dùng là gì? |
| Cấu hình hiệu lực | `mvn help:effective-pom` | Parent, dependencyManagement, plugin, profile nào đang áp dụng? |
| Dependency graph | `mvn dependency:tree` | Đã chọn phiên bản/scope nào? |
| Nhánh bị bỏ qua | `dependency:tree -Dverbose` với plugin hỗ trợ | Version hoặc nhánh nào bị loại do conflict/duplicate? |
| Classpath theo Maven | `dependency:build-classpath` hoặc cơ chế của plugin | Đường dẫn JAR được resolve trong classpath dự kiến? |
| Test Maven | `mvn clean test` và `target/surefire-reports` | Test có chạy và có fail không? |
| Kiểm thử tích hợp | `mvn verify` với Failsafe/plugin đã cấu hình | Các luồng tích hợp có chạy sau đóng gói không? |
| JAR được nạp thật | `CodeSource`, log class loading hoặc launcher | JVM thực tế lấy class từ file nào? |
| Artifact đã đóng gói | `jar tf ...`, `target/lib`, image manifest/SBOM | Bản giao hàng chứa/cấp dependency nào? |

Đừng rút ngắn quy trình thành “đổi version → chạy `mvn package` → thấy `BUILD SUCCESS`”. Nếu Surefire bị skip hoặc không tìm thấy test, build có thể thành công mà không chứng minh hành vi sau thay đổi.

## 4. Đọc dependency:tree đúng module và đúng phiên bản plugin

### 4.1. Dùng Maven Dependency Plugin để xem graph

Tại thư mục gốc một dự án Maven:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Lệnh gọi đầy đủ theo `groupId:artifactId:version:goal` giúp biết chính xác Maven Dependency Plugin `3.6.1` đang được dùng. Nếu POM đã quản lý version, có thể gọi ngắn `mvn dependency:tree`.

Trong một Reactor nhiều module, khi muốn xem app và những module cần xây kèm theo:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

`-pl :app` chọn artifactId `app`; `-am` bổ sung project liên quan theo quan hệ Reactor. Goal có thể in cây cho nhiều project được chọn: cần đọc **phần cây của app**, không lấy scope/version ở cây của api làm bằng chứng về app.

### 4.2. Hiển thị các nhánh omitted

Với phiên bản 3.6.1, tham số `verbose` được tài liệu goal xác nhận là hỗ trợ hiển thị các node bị loại khỏi dependency tree được trình bày:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dverbose
```

Các node có thể được chú thích kiểu `omitted for conflict with ...` hoặc `omitted for duplicate`. **Không tự khẳng định mọi node bị loại là lỗi**: một số bị loại hợp lệ vì trùng, scope, optional, exclusions hoặc quy tắc mediation. Cần hiểu **tại sao bỏ** và **version cuối cùng được chọn**.

Có thể lọc theo nhóm và artifact sau khi đã xem cây đầy đủ:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dverbose -Dincludes=org.apache.commons:commons-lang3
```

Tùy chọn `includes` chỉ thay **cây được in/lọc**, không tạo hoặc xóa dependency khỏi dự án. Khi debug conflict phức tạp, đừng chỉ dùng bản lọc: bản tree đầy đủ cho biết đường trung gian và những artifact khác bị ảnh hưởng.

### 4.3. Ghi snapshot an toàn cho pull request

Maven Dependency Plugin 3.6.1 cho phép chọn `outputFile` hoặc `outputType`, ví dụ:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -DoutputType=text -DoutputFile=target/dependency-tree.txt
```

Trong multi-module, output file tương đối có thể được đặt theo basedir của **từng project đang chạy goal**. Hãy xác định đúng file ứng với app khi thu bằng chứng. Không đặt nhiều module cùng ghi vào **một đường dẫn tuyệt đối chung** nếu chưa kiểm soát việc ghi đè.

Lưu ý cây dependency có thể tiết lộ tên artifact và repository nội bộ; nếu chia sẻ ngoài tổ chức, rà soát trước.

## 5. Ví dụ Java 17: xung đột 3.12.0 ↔ 3.14.0 và kiểm chứng sau khi sửa

Ta tạo một repository Maven gồm root, `api` và `app`. Mục tiêu học tập:

1. `api` dùng Commons Lang phiên bản **3.14.0** theo parent.
2. `app` khai báo **trực tiếp Commons Lang 3.12.0** để cố ý tạo xung đột.
3. Các test hành vi có thể vẫn chạy được, vì ví dụ chỉ gọi các API có ở cả hai phiên bản.
4. Một **test chẩn đoán version JAR được nạp** giúp phát hiện 3.12.0 dù test hành vi thông thường không báo lỗi.
5. Ta sửa app để nhận bản quản lý **3.14.0**, chạy lại mọi test, kiểm tra graph, runtime classpath và file JAR thực sự được nạp.

Các bản trong ví dụ được chọn để có tọa độ cụ thể và hiểu rõ kết quả, **không phải khuyến nghị chọn bản mới nhất**. Cần JDK 17+, Maven có thể thực thi plugin đã nêu và quyền tải artifact từ repository hợp lệ.

### 5.1. Cây thư mục

```text
version-conflict-lab/
├── pom.xml
├── api/
│   ├── pom.xml
│   └── src/main/java/demo/api/Greeter.java
└── app/
    ├── pom.xml
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/MainTest.java
```

### 5.2. Root pom.xml: quản lý version và tổng hợp module

Tệp `version-conflict-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>version-conflict-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>api</module>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <commons.version>3.14.0</commons.version>
        <junit.version>5.10.2</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>${commons.version}</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Root có hai vai trò: parent POM cho `api`/`app` và aggregator liệt kê các module cho Maven Reactor. `dependencyManagement` chốt version mặc định, **không tự thêm thư viện**. Nếu module khai báo version cụ thể ngay trong dependency trực tiếp, version đó có thể ghi đè giá trị mặc định được quản lý — chính là tình huống ta tạo trong app.

### 5.3. Module api: dùng Commons Lang bản 3.14.0

Tệp `version-conflict-lab/api/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo</groupId>
        <artifactId>version-conflict-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>api</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
    </dependencies>
</project>
```

`api` không ghi version riêng cho Commons Lang nên nhận `3.14.0` từ parent. Tệp `version-conflict-lab/api/src/main/java/demo/api/Greeter.java`:

```java
package demo.api;

import org.apache.commons.lang3.StringUtils;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        if (StringUtils.isBlank(name)) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Hello, " + StringUtils.capitalize(name.trim()) + "!";
    }
}
```

Class dùng `StringUtils.isBlank` và `StringUtils.capitalize`; những API này có ở cả các phiên bản 3.12.0 và 3.14.0. Đây là chủ ý để nhấn mạnh: **một vài test chức năng qua vẫn không chứng minh đúng phiên bản artifact**.

### 5.4. Module app — trạng thái trước sửa, cố ý có xung đột

Tệp `version-conflict-lab/app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo</groupId>
        <artifactId>version-conflict-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>demo</groupId>
            <artifactId>api</artifactId>
            <version>${project.version}</version>
        </dependency>

        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.12.0</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.6.1</version>
                <executions>
                    <execution>
                        <id>copy-runtime-dependencies</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>copy-dependencies</goal>
                        </goals>
                        <configuration>
                            <includeScope>runtime</includeScope>
                            <outputDirectory>${project.build.directory}/lib</outputDirectory>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Bốn điểm quan trọng:

- App phụ thuộc **trực tiếp** vào `demo:api:1.0.0`.
- App cũng phụ thuộc **trực tiếp** vào Commons Lang `3.12.0`. Đường trực tiếp này có thể được Maven chọn thay vì yêu cầu `3.14.0` bắc cầu từ api. Parent quản lý 3.14.0 nhưng một version được ghi rõ ngay ở direct dependency của app vẫn có ý nghĩa.
- JUnit Jupiter được khai báo `scope=test` và nhận version 5.10.2 từ parent.
- Dependency Plugin được cấu hình để **sau khi test đạt yêu cầu**, ở phase `prepare-package` sao chép các dependency runtime và compile cần thiết vào `app/target/lib`. Trong goal `copy-dependencies`, `includeScope=runtime` **bao gồm dependency compile và runtime**, không lấy JUnit chỉ có scope test. Đây là tiện ích cho demo classpath, **không tạo fat JAR**.

### 5.5. Mã Main.java dùng cả api và Commons Lang

Tệp `version-conflict-lab/app/src/main/java/demo/app/Main.java`:

```java
package demo.app;

import demo.api.Greeter;
import org.apache.commons.lang3.StringUtils;

import java.net.URISyntaxException;
import java.nio.file.Path;
import java.security.CodeSource;

public final class Main {
    private Main() {
    }

    public static String render(String input) {
        return Greeter.greet(StringUtils.trimToEmpty(input));
    }

    public static void main(String[] args) throws URISyntaxException {
        if (args.length == 1 && "--origin".equals(args[0])) {
            CodeSource origin =
                    StringUtils.class.getProtectionDomain().getCodeSource();
            if (origin == null || origin.getLocation() == null) {
                throw new IllegalStateException("Commons Lang CodeSource unavailable");
            }
            System.out.println(
                    Path.of(origin.getLocation().toURI()).getFileName());
            return;
        }
        System.out.println(render(" maven "));
    }
}
```

`Main.render` thật sự sử dụng Commons Lang nên **app cần khai báo dependency trực tiếp vào Commons Lang**. Tùy chọn `--origin` là công cụ chẩn đoán: thay vì tự tin rằng Maven đã chọn bản đúng, Java lấy `CodeSource` của class `StringUtils` **đã được class loader nạp** và in tên file chứa class đó.

Với chương trình đơn giản chạy từ JAR gốc trong local repository hoặc `target/lib`, tên file có thể phản ánh version chính xác. **Nhưng đừng biến kiểm tra tên file này thành tiêu chuẩn chung cho mọi production**: shaded JAR, classloader container, Java module layer hoặc cách đóng gói lại có thể làm tên file đổi hoặc không có CodeSource.

### 5.6. JUnit 5: kiểm tra hành vi và bản JAR thực sự được nạp

Tệp `version-conflict-lab/app/src/test/java/demo/app/MainTest.java`:

```java
package demo.app;

import org.apache.commons.lang3.StringUtils;
import org.junit.jupiter.api.Test;

import java.net.URISyntaxException;
import java.nio.file.Path;
import java.security.CodeSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MainTest {

    @Test
    void rendersValidInput() {
        assertEquals("Hello, Maven!", Main.render(" maven "));
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
                     () -> Main.render("   "));
    }

    @Test
    void loadsApprovedCommonsLangArtifact() throws URISyntaxException {
        CodeSource origin =
                StringUtils.class.getProtectionDomain().getCodeSource();
        assertNotNull(origin, "Commons Lang has no CodeSource");
        assertNotNull(origin.getLocation(), "Commons Lang has no origin URL");

        String actualJar =
                Path.of(origin.getLocation().toURI()).getFileName().toString();

        assertEquals("commons-lang3-3.14.0.jar", actualJar,
                     "Loaded Commons Lang from " + origin.getLocation());
    }
}
```

Phân biệt ba ý nghĩa của test:

1. `rendersValidInput` kiểm tra nghiệp vụ thường dùng.
2. `rejectsBlankInput` kiểm tra đường lỗi và exception.
3. `loadsApprovedCommonsLangArtifact` là **test chẩn đoán có chủ đích cho ví dụ**; nó kiểm tra tên JAR Commons Lang đang nạp khi Surefire chạy. Nếu hiện tại app thật sự dùng `commons-lang3-3.12.0.jar` thì test thứ ba thất bại, dù hai test chức năng có thể vẫn thành công.

Trong hệ thống sản phẩm, không nên duy trì vô điều kiện một assertion phụ thuộc tên file JAR như trên: phải thích nghi với cách đóng gói thật, hoặc chuyển việc chốt version sang **dependency policy + báo cáo artifact/SBOM + một số bài kiểm tra class loading phù hợp**. Mục đích của test này là thể hiện sự khác biệt giữa “test nghiệp vụ pass” và “đúng artifact đã được nạp”.

## 6. Thực hành trước sửa: chứng minh vấn đề thay vì chỉ đoán

Từ thư mục `version-conflict-lab/`, chạy:

```bash
mvn -version
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dverbose
```

Nếu các POM được tạo đúng như trên, app trực tiếp yêu cầu Commons Lang **3.12.0**, còn api yêu cầu **3.14.0**. Khi xem phần tree của app, tìm đường trực tiếp và đường bắc cầu; một nhánh có thể hiển thị là bị bỏ qua do conflict. Đừng chép một đoạn log giả làm stdout vì thứ tự node, mức độ verbose và log Reactor có thể khác theo môi trường.

Sau đó:

```bash
mvn -B -pl :app -am clean test
```

Kỳ vọng trong môi trường Maven/Surefire thông thường với project chưa chỉnh:

- `api` biên dịch được nhờ Commons Lang 3.14.0.
- `app` biên dịch được nhờ Commons Lang 3.12.0; cả hai API dùng trong ví dụ đều tồn tại.
- Hai test kiểm tra hành vi có thể **PASS**.
- Test `loadsApprovedCommonsLangArtifact` có chủ đích sẽ **FAIL** nếu class được nạp từ `commons-lang3-3.12.0.jar`, vì assertion yêu cầu 3.14.0.
- Maven báo `BUILD FAILURE` do assertion này; đây là **kết quả mong đợi của giai đoạn trước sửa**, không phải lỗi của ví dụ.

Kiểm tra báo cáo ở:

```text
app/target/surefire-reports/
```

Đọc phần tổng kết của `MainTest` để xác định test nào thất bại và **tên file JAR thật sự quan sát được**. Nếu môi trường custom hóa class loader hoặc cache khiến kết quả khác, đừng cưỡng ép kết luận từ tên JAR trong ví dụ: mở dependency tree và kiểm tra cơ chế nạp class thực tế.

## 7. Cách sửa đúng: bỏ bản ghim cũ ở dependency trực tiếp

Trong `app/pom.xml`, **chỉ bỏ dòng version `3.12.0`** của dependency Commons Lang:

**Trước sửa:**

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.12.0</version>
</dependency>
```

**Sau sửa:**

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
</dependency>
```

Lúc này parent `dependencyManagement` đã chốt `commons.version=3.14.0` cho dependency này. `app` vẫn giữ **direct dependency** vì mã `Main.java` gọi `StringUtils`. Không xóa toàn bộ dependency chỉ vì api cũng dùng Commons Lang; làm vậy khiến app dựa vào một nhánh bắc cầu để biên dịch API mà chính app import trực tiếp.

Ở dự án thật, chọn version sửa chữa sau khi đánh giá **yêu cầu Java, tương thích API/ABI, thay đổi hành vi, bảo mật, license và yêu cầu của các thư viện khác**. Không mặc định cứ chọn số version cao nhất là đủ.

### 7.1. Vì sao không sửa bằng cách thêm exclusion tùy tiện?

Nếu thêm exclusion Commons Lang vào dependency `demo:api` nhưng app vẫn dùng 3.12.0, Maven có thể không còn hiển thị đường xung đột từ api, nhưng **chưa có bằng chứng api tương thích 3.12.0**. Exclusion làm graph “đẹp hơn” không đồng nghĩa đã giải quyết tính tương thích.

Nếu bản 3.14.0 thực sự không tương thích với một thư viện nào đó, cần quyết định ở mức kiến trúc/version và test sau thay đổi, thay vì che đường dependency để lệnh tree không thấy conflict.

## 8. Xác minh sau sửa: một chuỗi kiểm tra có thứ tự

### 8.1. Chạy sạch tới verify

Từ root của dự án:

```bash
mvn -B clean verify
```

Với ví dụ đã sửa, kỳ vọng:

- `api` được build trước `app` theo dependency Reactor.
- Main và Greeter được biên dịch bằng Java release 17.
- Surefire ở app chạy **3 test, 0 failure, 0 error** trong môi trường ví dụ bình thường.
- Dependency Plugin ở app chạy goal `copy-dependencies` tại `prepare-package`, đưa runtime dependency vào `app/target/lib`.
- App được đóng gói thành `app/target/app-1.0.0.jar`. API được đóng gói thành `api/target/api-1.0.0.jar`.

Đây là kết quả **kỳ vọng theo cấu hình**, cần xem log và report thật ở máy chạy. Nếu môi trường có profile/flags skip test, `BUILD SUCCESS` không tự chứng minh 3 test đã được chạy.

Các output cần quan sát:

```text
api/target/api-1.0.0.jar
app/target/app-1.0.0.jar
app/target/surefire-reports/...
app/target/lib/api-1.0.0.jar
app/target/lib/commons-lang3-3.14.0.jar
```

Trong ví dụ, `clean` trước khi copy đặc biệt quan trọng: nếu thư mục `target/lib` còn cả JAR 3.12.0 và 3.14.0 từ hai lần build, một Java classpath wildcard có thể nạp bản bất ngờ. **Không chỉ kiểm tra file mới có mặt; phải kiểm tra bản cũ không còn trong tập thư viện dùng để chạy.**

### 8.2. Kiểm tra dependency graph sau sửa

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dverbose
```

Từ góc nhìn `app`, bản Commons Lang được chọn phải là **3.14.0** ở scope phù hợp. Bản 3.12.0 không còn được yêu cầu trực tiếp bởi POM sau sửa. Một nhánh 3.14.0 có thể được báo là duplicate, điều đó không nhất thiết là lỗi.

Chạy bản lọc để tập trung:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dincludes=org.apache.commons:commons-lang3
```

**Ghi nhận ở cả api và app**: scope/version tại cây api có thể khác cây app trong hệ thống lớn. Với demo đồng bộ hai module, cả hai dự kiến nhận Commons Lang 3.14.0.

### 8.3. Kiểm tra test report thật

Không chỉ nhìn dòng `BUILD SUCCESS`. Trong `app/target/surefire-reports`, mở báo cáo JUnit tương ứng với `demo.app.MainTest`:

- Test `rendersValidInput` đã chạy và pass?
- Test `rejectsBlankInput` đã chạy và pass?
- Test `loadsApprovedCommonsLangArtifact` đã chạy và pass?
- Tổng có đúng **3 test** (theo ví dụ) và số test skipped/error/failure bằng 0?
- Có profile, cờ `-DskipTests` hoặc `-Dmaven.test.skip=true` vô tình bật không?

Trong dự án thật, cần chạy lại **toàn bộ các bộ test liên quan** chứ không chỉ test mới thêm. Mục đích là phát hiện regression ở những module/thành phần dùng cùng thư viện.

## 9. Runtime classpath: chứng minh JVM đang nạp đúng JAR

### 9.1. Chạy chương trình với dependency runtime đã được copy

Goal `copy-dependencies` trong app đã chuẩn bị `app/target/lib`. Từ root của ví dụ:

**Linux/macOS:**

```bash
java -cp "app/target/classes:app/target/lib/*" demo.app.Main
```

**Windows PowerShell:**

```powershell
java -cp "app\target\classes;app\target\lib\*" demo.app.Main
```

Sau khi sửa và build đúng, stdout của lệnh Java chạy chương trình là:

```text
Hello, Maven!
```

Dấu `:` phân tách classpath entry trên Unix/Linux/macOS; Windows dùng dấu `;`. `lib/*` là wildcard Java launcher để nạp các JAR trực tiếp dưới thư mục lib, không phải lệnh copy JAR.

**Đây là kiểm tra hành vi ở JVM runtime riêng**, không phải JVM thực thi Maven Surefire. Một bài test pass trong Surefire chưa bảo đảm thư viện ở JVM mà script deploy sẽ nạp giống hệt nhau.

### 9.2. In tên JAR của class thực sự được nạp

Với tùy chọn `--origin` đã được code trong `Main.java`, chạy:

Linux/macOS:

```bash
java -cp "app/target/classes:app/target/lib/*" demo.app.Main --origin
```

Windows PowerShell:

```powershell
java -cp "app\target\classes;app\target\lib\*" demo.app.Main --origin
```

Trong ví dụ sau sửa (với layout JAR nguyên bản), stdout là:

```text
commons-lang3-3.14.0.jar
```

Lệnh này quan sát `StringUtils.class.getProtectionDomain().getCodeSource()` của **class đã được JVM nạp**. Nó gần với sự thật runtime hơn việc chỉ đọc POM, nhưng vẫn cần hiểu giới hạn: tên file có thể khác khi dùng shade/uber JAR, Java agents, custom class loader hoặc container. Kết luận hợp lệ trong demo là `StringUtils` đến từ file JAR có tên đã hiển thị trên classpath của lệnh Java đó.

Nếu muốn xem log nạp class của Java 17 thay vì thêm mã chẩn đoán:

```bash
java -Xlog:class+load=info -cp "app/target/classes:app/target/lib/*" demo.app.Main
```

Lệnh này in **rất nhiều dòng**. Trong log, tìm `org.apache.commons.lang3.StringUtils` và nguồn tải class; không sao chép một dòng log cố định vì định dạng và thứ tự có thể khác theo JVM/launcher. Chạy riêng trên môi trường bạn kiểm soát, không gửi debug log chứa đường dẫn nội bộ khi chưa rà soát.

### 9.3. Kiểm tra không còn hai JAR xung đột trên runtime path

Với `target/lib` của demo, thông thường **chỉ có một phiên bản Commons Lang được chọn**. Nếu tồn tại cả:

```text
app/target/lib/commons-lang3-3.12.0.jar
app/target/lib/commons-lang3-3.14.0.jar
```

thì phải dừng việc kết luận classpath đã đúng. Có thể một JAR là output cũ được copy từ lần build trước hoặc được thêm bởi script khác. Java wildcard không phải quy tắc ưu tiên phiên bản Maven và thứ tự JAR trong wildcard classpath không nên được dựa vào để xử lý conflict.

Làm sạch `target` rồi đóng gói lại theo quy trình chính thức; kiểm tra nguồn copy và script runtime. Trong ứng dụng thật, còn cần kiểm tra thư viện được cấp bởi **application server, Docker image hoặc plugin framework**, vì chúng có thể đưa JAR khác vào parent classloader.

### 9.4. Cẩn trọng với JAR thường và executable JAR

Lệnh:

```bash
jar tf app/target/app-1.0.0.jar
```

liệt kê entry bên trong JAR của app. Với POM này, app là **JAR thường** và không tự chứa toàn bộ class của `api`/Commons Lang; plugin đã copy dependency sang `target/lib` để có thể dùng `java -cp`. Cũng chưa cấu hình `Main-Class` trong manifest nên `java -jar app/target/app-1.0.0.jar` không phải lệnh chạy demo phù hợp.

Với Shade Plugin, Spring Boot repackaging, WAR hay container, phải kiểm tra output **sau bước đóng gói tương ứng**, không kết luận từ `target/classes` đơn lẻ.

## 10. Xác minh các classpath compile, runtime, test khác nhau như thế nào

Scope của dependency ảnh hưởng việc nó có trên **compile**, **runtime** và **test** classpath. Bảng tổng quát với dependency thông thường:

| Scope hiệu lực | Compile của mã chính | Runtime của sản phẩm | Test |
| --- | --- | --- | --- |
| `compile` | Có | Có | Có |
| `provided` | Có | Không (thường do container cấp) | Có |
| `runtime` | Không | Có | Có |
| `test` | Không | Không | Có |

Điều cần kiểm tra sau giải quyết xung đột:

- **Compile classpath:** mã chính còn biên dịch khi dependency mới đổi version/scope không? Có import API mà runtime-only dependency không cung cấp cho compiler?
- **Test classpath:** JUnit/Mockito/test helper và các nhánh bắc cầu có đúng version? Test có đang nạp cùng thư viện khác version với ứng dụng không?
- **Runtime classpath:** sản phẩm được chạy theo launcher thực tế có đủ JAR và chỉ có bản phù hợp của những class quan trọng không?
- **Plugin classpath:** plugin Maven chạy trong classloader/cấu hình riêng; dependency của plugin không tự trở thành dependency của ứng dụng.

Theo tài liệu Maven Surefire, test classpath thường gồm **`target/test-classes`, `target/classes`, project dependencies ở các scope thích hợp và những mục được bổ sung hợp lệ**. Test thành công có thể do test-only dependency cung cấp lớp mà runtime sản phẩm không có. Vì vậy, luôn thêm kiểm tra runtime nếu xung đột ảnh hưởng code thực thi sau deployment.

### 10.1. Xuất dependency classpath bằng plugin

Maven Dependency Plugin 3.6.1 có goal `dependency:build-classpath`, hỗ trợ `includeScope` và `mdep.outputFile`. Vì goal này lấy đường dẫn artifact từ local repository, trong một ví dụ nhiều module, nên trước hết **cài những artifact liên quan vào local repository của chính môi trường kiểm tra**:

```bash
mvn -B clean install
```

Sau khi toàn bộ test thành công, từ root dùng POM app riêng để in runtime dependency path:

```bash
mvn -B -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/runtime.classpath
```

Với goal này, `includeScope=runtime` nghĩa là **lấy dependency compile và runtime**, không phải chỉ những dependency được khai báo literal `<scope>runtime</scope>`. File đầu ra nằm ở `app/target/runtime.classpath` khi đường dẫn tương đối được giải quyết từ basedir của app. Nó chứa đường dẫn JAR local; nếu dùng `-f` ở môi trường khác hoặc cấu hình dự án riêng, kiểm tra vị trí file thực tế theo log.

Nếu cần đối chiếu compile classpath:

```bash
mvn -B -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath -DincludeScope=compile -Dmdep.outputFile=target/compile.classpath
```

Ở Dependency Plugin 3.6.1, `includeScope=compile` có ngữ nghĩa lọc classpath gồm compile, provided và system khi thích hợp. Đừng hiểu nó đơn giản là “chỉ dependencies khai báo compile”.

Đối với test:

```bash
mvn -B -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath -DincludeScope=test -Dmdep.outputFile=target/test.classpath
```

`includeScope=test` lấy các dependency ở các scope phục vụ test. **Các file do build-classpath sinh chỉ liệt kê dependency JAR**, không tự thể hiện toàn bộ output directories như `target/classes`, `target/test-classes` hoặc mọi classloader đặc biệt mà Surefire/app server dùng. Vì vậy, không đồng nhất chúng với chính xác mọi runtime launch command.

### 10.2. Vì sao test và ứng dụng có thể nạp hai version khác nhau?

Ví dụ một plugin thử nghiệm có `additionalClasspathElements` hoặc một test runner đặt JAR khác lên test classpath, trong khi script triển khai lại nạp thư viện từ container/image. Hoặc một dependency chỉ có scope `test` khiến test được bổ sung một JAR mà runtime không có.

Để xác minh:

1. Xem graph/scope của app và những module liên quan.
2. Xem cấu hình Surefire, fork/class loading và báo cáo test thực tế.
3. Chạy chương trình qua **đường chạy thật của sản phẩm**.
4. Nếu cần, ghi `CodeSource` của những lớp gây conflict và so artifact/manifest/SBOM với release.

Không sửa `surefire.additionalClasspathElements` hoặc classloader flags chỉ để “ép test pass” khi vấn đề nằm ở version/scope dependency chưa được quản lý đúng.

## 11. Kiểm thử hồi quy: test gì sau khi giải quyết xung đột?

Một chiến lược hợp lý có nhiều lớp kiểm tra:

| Nhóm kiểm thử | Mục đích | Ví dụ |
| --- | --- | --- |
| **Compile sạch** | Phát hiện API/class không tồn tại tại compile time | `mvn clean compile` |
| **Unit test** | Kiểm tra logic và exception ở mức module | JUnit test của `Greeter`/`Main` |
| **Classpath origin check** | Đối chiếu version JAR/class đã được nạp trong môi trường kiểm tra | `CodeSource` của `StringUtils` |
| **Integration test** | Phát hiện lỗi khi nhiều module/dịch vụ/hệ thống phối hợp | HTTP client, database driver, serialization |
| **Smoke test runtime** | Chạy artifact/launcher gần với production | `java -cp`, container, application server |
| **Contract/API compatibility** | Phát hiện đổi kiểu dữ liệu, phương thức, reflection, SPI | Test gọi API có nguy cơ đổi sau nâng version |
| **Security/license check** | Kiểm tra chính sách thư viện mới | SBOM, vulnerability scanner, license policy |
| **Reproducibility/CI** | Phát hiện phụ thuộc cache/profile/JDK riêng | Clean checkout, build trên agent chuẩn |

Với dự án thực tế, không phải mọi trường hợp đều cần đủ từng công cụ, nhưng **hạng mục kiểm tra phải tương xứng rủi ro thay đổi**. Ví dụ nâng major version của Jackson, Hibernate hoặc driver cần kiểm tra serialization, mapping, database interactions hoặc behavior xuyên module; chỉ test getter/setter sẽ bỏ sót nhiều lỗi.

### 11.1. Surefire và Failsafe không thay thế nhau

Trong dự án Java thông thường, **Surefire** chạy unit test tại phase `test`, còn **Failsafe** thường được cấu hình để chạy integration test tại `integration-test` và kiểm tra kết quả tại `verify`. Nếu POM không gắn Failsafe hoặc công cụ tích hợp khác, `mvn verify` **không tự bảo đảm có integration test**.

Sau khi giải quyết conflict ảnh hưởng tới dịch vụ, nên có ít nhất một smoke/integration test chạy cùng classpath đóng gói/triển khai, nếu quy trình dự án cho phép. Đừng chỉ trông vào unit test có test-scoped dependencies rộng hơn runtime.

### 11.2. Kiểm tra đường lỗi, không chỉ happy path

Một binary incompatibility có thể chỉ xảy ra khi API được gọi trong một nhánh hiếm, khi một nhà cung cấp SPI được chọn hoặc khi class được load theo phản chiếu (*reflection*). Tùy thư viện, thêm test bao phủ:

- Đường xử lý thành công và các giá trị rỗng/biên.
- Ngoại lệ và lỗi phân giải class/method.
- Serialization/deserialization nếu thư viện xử lý dữ liệu.
- SPI/ServiceLoader, JDBC driver hoặc classloader plugin nếu dự án dùng.
- Đa luồng/transaction/timezone nếu thay đổi thư viện có tác động tới các yếu tố đó.

Các test này không xuất hiện trong demo Commons Lang đơn giản nhưng là trọng tâm khi sửa dependency conflict của hệ thống thật.

## 12. Dependency convergence và quy tắc tự động trong CI

Nếu dự án thường xuyên gặp conflict, có thể bổ sung Maven Enforcer Plugin như một hàng rào. Ví dụ **đoạn plugin để đặt vào `<build><plugins>` của POM muốn kiểm tra**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.4.1</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Rule `dependencyConvergence` có thể làm build thất bại khi các đường trong tree yêu cầu các version khác nhau của cùng một artifact. Nó giúp phát hiện conflict bị cơ chế nearest definition che đi.

**Nhưng phải hiểu sự khác biệt:**

- `dependencyConvergence` kiểm tra **sự nhất quán yêu cầu version trên các đường liên quan**, theo cấu hình scope/exclusions của rule. Nó có thể nghiêm ngặt hơn điều mà Maven cần để build thành công.
- `requireUpperBoundDeps` là rule khác: kiểm tra version được chọn có thấp hơn một version được yêu cầu ở đường khác hay không, theo ngữ nghĩa rule. Nó **không thay thế bài test tương thích**.
- Hai rule không chứng minh rằng “mọi thư viện cùng version là an toàn”. API behavior có thể đổi dù graph đã convergence.
- Một số dự án có ngoại lệ hợp lệ theo scope, BOM hoặc hệ sinh thái thư viện; nếu cần exception, phải ghi rõ lý do, đường phụ thuộc và kế hoạch xử lý.

Trong demo, chỉ thêm rule này **sau khi đã quan sát test chẩn đoán trước sửa** nếu muốn trải nghiệm cả hai cách phát hiện. Nếu gắn Enforcer ngay từ đầu và rule fail tại `validate`, Maven sẽ dừng trước khi Surefire thực thi test; đó là hành vi chính xác của quy trình có chốt kiểm soát sớm, không phải lỗi Maven.

## 13. Những nguyên nhân khiến “sửa conflict rồi build xanh” vẫn chưa ổn

| Dấu hiệu | Nguyên nhân cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| Tree hiển thị bản mới nhưng `NoSuchMethodError` khi chạy | Runtime nạp JAR cũ từ lib/container; binary incompatibility | `CodeSource`, runtime launcher, class loading log |
| Test pass nhưng ứng dụng không tìm thấy class | Test classpath có thư viện test-only, runtime không có | Scope, Surefire config, runtime smoke test |
| Có cả hai bản JAR trong `target/lib` | Output cũ hoặc copy task không xóa bản cũ | `mvn clean verify` và kiểm tra thư mục lib sau build |
| CI fail nhưng laptop pass | Cache khác, profile/settings/mirror khác, JDK khác | Maven/JDK version, effective POM, clean agent |
| Một module pass, module khác fail | Chỉ sửa dependencyManagement ở một POM/module | Tree của từng module, effective POM từng module |
| `mvn package -DskipTests` xanh | Test không được thực thi | Đọc Surefire reports, chạy lại không skip |
| `dependency:tree` chỉ thấy một version nhưng enforcer fail | Version yêu cầu ở các nhánh không hội tụ, dù mediation đã chọn một bản | `-Dverbose` và quy tắc Enforcer cụ thể |
| `ClassCastException` liên quan API | Class cùng tên được load bằng nhiều classloader hoặc API type đổi | Classloader identity, CodeSource, plugin/container realms |
| `ServiceConfigurationError` hoặc SPI không thấy provider | Resource/provider JAR thiếu trong gói runtime | `META-INF/services`, runtime jars và integration test |
| `java -jar` lỗi nhưng `mvn test` pass | Thiếu manifest, thiếu dependency JAR hoặc khác launcher | `jar tf`, manifest, packaging/plugin và lệnh triển khai |
| Tree lấy từ root khác tree app | Project root/aggregator có POM và dependency riêng | Xác định đúng module với `-pl`/`-f` |
| Conflict được “sửa” bằng exclusion nhưng runtime fail | Đã loại luôn thư viện mà một tính năng cần | Chạy test nghiệp vụ, kiểm tra dependency graph và classpath |
| Version mới cần JDK cao hơn | Bytecode hoặc API yêu cầu runtime JDK khác | `mvn -version`, compiler release và runtime thật |
| Maven plugin báo lỗi sau nâng dependency | Nhầm project dependency với dependency của plugin | POM `build/plugins`, plugin realms, plugin version |

Không phải lỗi nào cũng xuất phát từ Maven mediation. Có những vấn đề đến từ bản thân source code, classloader container, cấu trúc package, reflection hoặc đóng gói. Hãy dùng **bằng chứng đã quan sát** để phân loại trước khi sửa tiếp.

## 14. Quy trình dành cho pull request và pipeline CI

Một thay đổi version có thể được review và kiểm chứng bằng thứ tự:

1. **Ghi nguyên nhân:** artifact nào có conflict, các đường nào yêu cầu version gì, version nào đang được chọn và rủi ro nếu giữ nguyên.
2. **Chọn chiến lược sửa:** direct dependency đúng version, parent/BOM `dependencyManagement`, nâng cấp các thư viện liên quan, hoặc exclusion có cơ sở; giải thích vì sao.
3. **Tạo bản diff POM tối thiểu:** không đồng thời thay quá nhiều nhóm library nếu không có lý do; tránh khó định vị regression.
4. **So tree trước/sau:** dùng cùng Dependency Plugin version, đúng module, kiểm tra `verbose` và scope.
5. **Build sạch + unit test:** `mvn -B clean verify`; xác nhận thực tế số test, failure và skipped.
6. **Kiểm tra runtime classpath:** runtime jars/output sau đóng gói, không còn bản cũ ở launcher, class origin của API dễ xung đột.
7. **Chạy integration/smoke test:** đúng môi trường gần production, nhất là với API có serialization, SPI hoặc driver.
8. **Đối chiếu Maven/JDK/settings và cache:** tái lập trên agent CI sạch, không dựa artifact còn trong cache cá nhân.
9. **Lưu kết quả review:** phạm vi thay đổi, version được duyệt, dependency tree đã ẩn dữ liệu nhạy cảm, tóm tắt test, bằng chứng artifact/CodeSource khi phù hợp.
10. **Chốt chính sách phòng ngừa:** quản lý version tập trung, Enforcer/baseline kiểm tra dependency và theo dõi cập nhật sau phát hành.

Một pipeline đơn giản có thể dùng Maven Wrapper nếu dự án đã cài Wrapper an toàn:

```bash
./mvnw -B -ntp clean verify
```

`-ntp` tắt hiển thị tiến độ tải trong các bản Maven hỗ trợ; `-B` là batch mode. **Lệnh này chỉ chạy những goal đã được POM cấu hình**. Nếu dự án có integration test, smoke test container hoặc quét SBOM riêng, cần thêm stage/goal tương ứng; đừng tự nhận những bước chưa chạy là đã hoàn tất.

Khi build quan trọng, tuyệt đối không chấp nhận “PASS nhờ `-DskipTests`” như bằng chứng đã kiểm tra regression. Có thể dùng skip trong một stage tạm thời có chủ đích, nhưng phải có một stage khác **thực sự chạy test** trước khi chấp thuận thay đổi.

## 15. Checklist kết luận một conflict đã được xử lý

Trước khi đóng vấn đề, trả lời có bằng chứng:

- [ ] Dependency cần sửa đã xác định đúng **`groupId:artifactId`, version, type/classifier và scope**?
- [ ] Đã hiểu **đường trực tiếp và bắc cầu** nào khiến Maven chọn version cũ?
- [ ] Sau sửa, `dependency:tree` của **đúng module** có phiên bản mong đợi?
- [ ] Các node bị omit trong `-Dverbose` được hiểu và không che đường quan trọng chưa xử lý?
- [ ] `dependencyManagement`/BOM được áp dụng đồng bộ, không còn module override version ngoài ý muốn?
- [ ] Build sạch thành công với đúng JDK/Maven và **không skip những test cần thiết**?
- [ ] Test reports chứng minh **test thực sự chạy**, không chỉ log `BUILD SUCCESS`?
- [ ] Test chức năng, đường lỗi và integration test liên quan đến library mới đều pass?
- [ ] Runtime launcher hoặc artifact triển khai thực sự nạp **bản JAR/class** mong đợi?
- [ ] Không còn bản JAR cũ nằm song song ở thư mục lib, container image hoặc nơi classloader có thể nạp?
- [ ] Phiên bản plugin, profile và cache giữa local/CI đã được kiểm tra nếu kết quả khác nhau?
- [ ] Có bằng chứng lưu trong PR/ticket và quy tắc phòng ngừa conflict tái xuất hiện?

**Kết luận:** Maven là công cụ chọn version và dựng classpath; nó không thể tự chứng minh mọi chương trình dùng thư viện đó tương thích về hành vi. Sau khi giải quyết xung đột, cần kiểm tra đồng thời **resolved dependency graph**, **test classpath**, **runtime classpath**, **JAR thực sự được nạp** và **kết quả kiểm thử hồi quy**. Khi tất cả các lớp bằng chứng này nhất quán, thay đổi mới đủ cơ sở để đưa vào CI và phát hành.

### Tài liệu chính thức để tra cứu

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Working with Multiple Modules / Reactor](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven Dependency Plugin 3.6.1 — dependency:tree](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.6.1/tree-mojo.html)
- [Maven Dependency Plugin 3.6.1 — dependency:build-classpath](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.6.1/build-classpath-mojo.html)
- [Maven Dependency Plugin 3.6.1 — dependency:copy-dependencies](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.6.1/copy-dependencies-mojo.html)
- [Maven Surefire Plugin — Configuring the Classpath](https://maven.apache.org/surefire/maven-surefire-plugin/examples/configuring-classpath.html)
- [Maven Surefire Plugin — Class Loading and Forking](https://maven.apache.org/surefire/maven-surefire-plugin/examples/class-loading.html)
- [Maven Enforcer Rules — dependencyConvergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
