# Dùng dependency:list, dependency:tree và dependency:build-classpath trong Maven

Khi làm việc với dự án Java có nhiều thư viện, đọc mỗi phần `<dependencies>` trong `pom.xml` thường **không đủ** để biết Maven thực sự sử dụng những artifact nào. Một dependency trực tiếp có thể kéo theo dependency bắc cầu (*transitive dependency*), có thể bị thay phiên bản vì quy tắc xung đột, có scope riêng hoặc bị loại bởi `<exclusions>`. Maven Dependency Plugin cung cấp ba goal rất hữu ích để quan sát và xử lý phần này:

- **`dependency:list`:** hiển thị **danh sách phẳng** những dependency Maven đã resolve, gồm thông tin tọa độ/phiên bản/scope.
- **`dependency:tree`:** hiển thị **cây quan hệ** để biết dependency đến từ nhánh nào, giải thích phụ thuộc bắc cầu và hỗ trợ chẩn đoán xung đột phiên bản.
- **`dependency:build-classpath`:** tạo **chuỗi classpath** gồm đường dẫn đến các file dependency đã resolve, thuận tiện cho lệnh `java -cp` hoặc một công cụ ngoài Maven.

Ba goal có đầu ra và mục đích khác nhau; chúng không thay thế hoàn toàn cho nhau. Bài này dùng Maven 3.9.x, JDK 17+ và Maven Dependency Plugin phiên bản **3.11.0** làm môi trường minh họa. Đây là version cố định để cú pháp có thể kiểm tra nhất quán, không phải yêu cầu mọi dự án phải nâng lên phiên bản này.

## 1. Từ khai báo trong POM đến dependency thực tế

Một project có thể khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **đoạn** XML đặt bên trong `<project>` của POM. Maven không chỉ đọc hai dòng khai báo thư viện. Nó còn giải quyết POM của từng artifact, các dependency bắc cầu, scope, exclusions, optional, version được quản lý và quy tắc hòa giải xung đột.

Ví dụ, khai báo `junit-jupiter` ở scope `test` có thể kéo theo các module JUnit Jupiter API/engine và JUnit Platform cần cho test. Vì vậy, danh sách thực tế có thể có nhiều artifact hơn số `<dependency>` viết tay. Ngược lại, một dependency bị loại hoặc một version xung đột không nhất thiết hiện như một node được chọn để chạy.

Các khái niệm quan trọng:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Dependency trực tiếp | Được khai báo trong project `<dependencies>` hoặc nhận theo inheritance |
| Dependency bắc cầu | Được một dependency khác kéo vào dependency graph theo quy tắc Maven |
| Tọa độ artifact | `groupId:artifactId:version` cùng type/classifier khi có |
| Scope | Phạm vi dùng ở compile, runtime, test, provided, system… |
| Resolution | Quá trình xác định version, đọc metadata/POM, tải artifact theo repository |
| Mediation | Chọn version/nhánh thắng khi nhiều đường dẫn đưa đến cùng dependency |
| Local repository | Cache chứa artifact đã tải, thường `~/.m2/repository` |
| Dependency Plugin | Maven plugin cung cấp các goal `list`, `tree`, `build-classpath` |

**Lưu ý:** `dependency:list` và `dependency:tree` quan sát **dependency graph của project**. Chúng không phải công cụ liệt kê mặc định **dependencies của chính các Maven build plugins**. Nếu cần phân tích plugin dependencies, phải dùng các goal/cách kiểm tra plugin phù hợp; đừng xem output project dependency là toàn bộ mọi JAR Maven từng tải.

## 2. Cài đặt và gọi Maven Dependency Plugin

Ba goal đều thuộc plugin:

```text
groupId:    org.apache.maven.plugins
artifactId: maven-dependency-plugin
version:    3.11.0
```

Cách gọi ngắn ở thư mục có `pom.xml`:

```bash
mvn dependency:list
mvn dependency:tree
mvn dependency:build-classpath
```

Cách gọi tường minh, hữu ích nếu chưa pin plugin hoặc đang kiểm tra version:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:list
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:build-classpath
```

Để dùng được tên rút gọn `dependency:...` một cách ổn định, nên quản lý version plugin trong POM hoặc parent POM:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <version>3.11.0</version>
        </plugin>
    </plugins>
</build>
```

Đây là một **đoạn POM**. Khai báo plugin trong `<plugins>` không tự khiến cả ba goal chạy ở mọi phase. Ba lệnh trên gọi trực tiếp goal cụ thể; muốn chạy tự động trong lifecycle phải khai báo `<executions>` thích hợp.

**Điều kiện vận hành:** Maven phải resolve được chính Dependency Plugin cùng dependencies của plugin và những project dependencies cần thiết. Nếu máy offline hoặc repository không truy cập được, các goal có thể lỗi dù POM có cú pháp hợp lệ. Khi chạy Maven Wrapper (`./mvnw` hoặc `.\mvnw.cmd`), phải đảm bảo Wrapper đã được chuẩn bị và phiên bản Maven tương thích.

### Mỗi goal tạo loại kết quả gì?

| Goal | Đầu ra chính | Câu hỏi giải đáp | Dùng cho |
| --- | --- | --- | --- |
| `dependency:list` | Danh sách tọa độ/scope, một artifact mỗi mục | Dự án đã resolve những artifact/version nào? | Kiểm kê, lọc scope, đối chiếu dependency |
| `dependency:tree` | Cây phụ thuộc và các nhánh | Vì sao artifact đó xuất hiện, đi qua nhánh nào? | Tracing transitive dependencies, xung đột phiên bản |
| `dependency:build-classpath` | Một chuỗi đường dẫn file, phân cách theo OS | Đưa các JAR đã resolve vào `java -cp` như thế nào? | Chạy tool/Java ngoài Maven, tạo classpath file |

`list` có thể gồm cả dependency trực tiếp và bắc cầu sau resolution; `tree` biểu diễn quan hệ dẫn tới các dependency được chọn; `build-classpath` chủ yếu xuất ra đường dẫn tới **các file dependency**, không phải một cây hay bản phân tích xung đột.

## 3. Ví dụ dự án Java 17 có dependency trực tiếp và test dependency

Tạo project:

```text
dependency-goals-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/deps/App.java
    └── test/
        └── java/vn/example/deps/AppTest.java
```

Dự án dùng `commons-lang3` trong mã ứng dụng và JUnit Jupiter trong test. Có hai scope khác nhau để quan sát những gì từng goal xuất ra.

### 3.1. File pom.xml hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>dependency-goals-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Plugin versions được pin để ví dụ tái lập hơn; lần chạy đầu cần truy cập repository chứa các version này. `commons-lang3` ở scope mặc định `compile` và JUnit ở scope `test`. POM không có `<dependencyManagement>` hay parent ngoài Super POM nên tương đối dễ đọc.

### 3.2. Mã Java chạy được

File `src/main/java/vn/example/deps/App.java`:

```java
package vn.example.deps;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message() {
        return StringUtils.isBlank("   ")
                ? "Dependency classpath OK"
                : "Unexpected result";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

`StringUtils.isBlank("   ")` trả về `true` vì chuỗi chỉ chứa khoảng trắng. Mã ứng dụng cần **Commons Lang trên compile classpath** và khi chạy lệnh `java` cần **Commons Lang trên runtime classpath**.

File `src/test/java/vn/example/deps/AppTest.java`:

```java
package vn.example.deps;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Dependency classpath OK", App.message());
    }
}
```

JUnit chỉ dành cho test trong ví dụ; muốn chạy ứng dụng chính không cần nạp JUnit JAR vào runtime classpath.

### 3.3. Build trước khi quan sát

Chạy trong thư mục `dependency-goals-demo`, với Maven 3.9.x và JDK 17+:

```bash
java -version
mvn --version
mvn -B clean verify
```

`verify` chạy các phase cần thiết, compile `App`/`AppTest`, chạy JUnit test và tạo JAR theo packaging. Khi thành công, kết quả dự kiến là `target/dependency-goals-demo-1.0.0.jar`.

**Không dùng stdout Maven làm output cố định:** log phụ thuộc version, OS, repository cache và lần đầu download. Ở các phần sau, những dòng có artifact coordinates là *mẫu được rút gọn*, không phải toàn bộ log chính xác.

## 4. dependency:list: kiểm kê các dependency đã resolve

Lệnh cơ bản:

```bash
mvn -B dependency:list
```

Goal `list` cần project Maven và giải quyết dependency trong phạm vi test để liệt kê. Đầu ra là danh sách các artifact sau resolution, thường gồm trực tiếp và bắc cầu, ví dụ các mục có hình thức:

```text
org.apache.commons:commons-lang3:jar:3.17.0:compile
org.junit.jupiter:junit-jupiter:jar:5.11.0:test
org.junit.jupiter:junit-jupiter-api:jar:5.11.0:test
org.junit.jupiter:junit-jupiter-engine:jar:5.11.0:test
```

Đây là **những dòng minh họa có thể xuất hiện**, không phải cam kết đủ mọi mục hoặc thứ tự. Danh sách thực tế còn tùy POM phụ thuộc của từng artifact và cơ chế resolve. Một mục thường thể hiện `groupId:artifactId:type:version:scope`; có thể có classifier khi artifact dùng classifier.

Từ `list` có thể biết phiên bản artifact được chọn và scope tương ứng, nhưng **không thể biết chắc tại sao** một dependency bắc cầu xuất hiện, vì quan hệ cha–con đã bị làm phẳng. Khi cần tìm đường dẫn xuất hiện, hãy dùng `dependency:tree`.

### 4.1. Lọc phạm vi

```bash
# Chỉ các dependency phù hợp runtime classpath
mvn -B dependency:list -DincludeScope=runtime

# Nhìn phạm vi test (bao gồm các dependency khả dụng cho test)
mvn -B dependency:list -DincludeScope=test
```

Trong Maven Dependency Plugin, `includeScope` là **ngưỡng theo cách dựng classpath**, *không phải* kiểm tra chính xác chữ `scope` trong POM. Theo tài liệu goal:

| `-DincludeScope` | Ý nghĩa lọc của các goal list/build-classpath |
| --- | --- |
| `runtime` | Gồm dependency ở **compile và runtime** |
| `compile` | Gồm **compile, provided, system** |
| `test` | Gồm tất cả phạm vi dependency (tương đương mặc định) |
| `provided` | Chỉ phạm vi provided |
| `system` | Chỉ phạm vi system |

Vì vậy `-DincludeScope=runtime` **không** có nghĩa “chỉ dependency có scope ghi đúng là runtime”. Trong ví dụ, Commons Lang ở scope compile vẫn được xuất ra vì nó cần khi chạy ứng dụng. JUnit ở test scope không thuộc runtime set đó.

### 4.2. Lọc theo groupId hoặc bỏ dependency bắc cầu

```bash
# Chỉ kiểm kê dependency thuộc nhóm JUnit
mvn -B dependency:list -DincludeGroupIds=org.junit.jupiter

# Loại phần bắc cầu, tập trung vào dependency trực tiếp
mvn -B dependency:list -DexcludeTransitive=true
```

`includeGroupIds` nhận danh sách groupId phân cách dấu phẩy; `excludeTransitive=true` yêu cầu goal lọc các transitive dependencies khỏi danh sách. Đây là **bộ lọc báo cáo**, không sửa POM, không xóa thư viện trong local repository và không thay dependency graph của build.

Một số tham số khác hữu ích:

```bash
# Hiển thị đường dẫn tuyệt đối của artifact trong danh sách
mvn -B dependency:list -DoutputAbsoluteArtifactFilename=true

# Ghi danh sách vào file
mvn -B dependency:list -DoutputFile=target/dependency-list.txt
```

`outputFile` của **`dependency:list`** dùng user property `outputFile`. Khi ghi ra file, không cần cố copy stdout Maven vì output console còn chứa log, màu terminal hoặc thông báo tải artifact. Dùng một đường dẫn phù hợp với môi trường CI nếu muốn lưu báo cáo.

### 4.3. Những điều `list` không trả lời

- **Đường dẫn quan hệ** từ project đến dependency: `list` không diễn giải các nhánh.
- **Lý do một phiên bản thắng xung đột:** cần `tree`, kiểm tra `dependencyManagement` và đôi khi `-Dverbose`.
- **Danh sách plugin dependencies:** project dependency list không đồng nghĩa plugin classpath.
- **Thư viện thực sự được load ở runtime:** danh sách resolve không chứng minh từng class đã được JVM tải; classpath và cách khởi động ứng dụng còn quan trọng.

## 5. dependency:tree: nhìn quan hệ trực tiếp, bắc cầu và xung đột

Lệnh:

```bash
mvn -B dependency:tree
```

Cây rút gọn trong project mẫu có thể trông như:

```text
vn.example:dependency-goals-demo:jar:1.0.0
+- org.apache.commons:commons-lang3:jar:3.17.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.11.0:test
   +- org.junit.jupiter:junit-jupiter-api:jar:5.11.0:test
   \- org.junit.jupiter:junit-jupiter-engine:jar:5.11.0:test
```

**Đây là sơ đồ minh họa đã giản lược một số node bắc cầu**, không phải output nguyên văn. Indentation cùng `+-` và `\-` cho biết dependency cha và con. Project là root; Commons Lang và JUnit Jupiter được khai báo trực tiếp; các module JUnit phía dưới đến từ dependency bắc cầu.

Có thể giải thích vì sao:

- Một artifact xuất hiện dù `pom.xml` của project không khai báo trực tiếp nó.
- Một dependency đi qua nhánh nào (ví dụ qua `junit-jupiter`).
- Có nhiều đường dẫn tiềm năng đến cùng một thư viện hay không.
- Một dependency được filter hoặc version khác đang được chọn ra sao.

### 5.1. Lọc cây theo tọa độ

```bash
# Chỉ những nhánh liên quan nhóm org.junit.jupiter
mvn -B dependency:tree -Dincludes=org.junit.jupiter

# Lọc theo một artifact cụ thể
mvn -B dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

Filter của `tree` dùng cú pháp gần với `[groupId]:[artifactId]:[type]:[version]` và hỗ trợ wildcard/đoạn bỏ trống tùy thành phần. Lệnh lọc phù hợp để **tập trung vào một nhóm trong báo cáo**; nó không thêm hoặc loại dependency khỏi build.

Nếu dùng PowerShell/cmd và filter chứa dấu `*` hoặc ký tự có ý nghĩa với shell, cần quote tham số đúng cách. Với chuỗi filter có dấu phẩy, đặt trong dấu nháy có thể giúp tránh shell biến đổi ngoài dự kiến.

### 5.2. Xem dependency tree cho một scope

```bash
mvn -B dependency:tree -Dscope=runtime
mvn -B dependency:tree -Dscope=test
```

Ở goal `tree`, tham số là **`scope`**, không phải `includeScope` như goal `list` hoặc `build-classpath`. Nó lọc những node/nhánh được trình bày theo phạm vi được resolve. Không nhầm tham số giữa các goal: `-DincludeScope=runtime` là option được tài liệu hóa cho `list`/`build-classpath`; với `tree` dùng `-Dscope=runtime`.

Báo cáo scope không phải cam kết toàn bộ mã thực sự được load ở runtime: còn class loader của ứng dụng, packaging, container/server và cách triển khai.

### 5.3. Xem node bị bỏ và phiên bản xung đột

```bash
mvn -B dependency:tree -Dverbose
```

Tùy phiên bản Dependency Plugin, `-Dverbose` cho phép hiển thị cả các node **omitted** trong cây serialized, hữu ích khi tìm conflict hoặc duplicate. Một ví dụ thông điệp dạng khái niệm:

```text
...:lib-helper:jar:2.0:compile (omitted for conflict with 1.5)
```

Đây **không phải kết quả mặc định** của project Java trong mục 3. Nó mô tả tình huống hai nhánh muốn dùng các phiên bản khác nhau; Maven Resolver chọn một version, còn candidate không thắng có thể bị bỏ khỏi cây rút gọn.

Cần hiểu quy tắc:

- Maven dùng **nearest definition** (dependency gần root hơn trong graph thường thắng) cho xung đột cùng artifact khi không có quản lý version đặc biệt.
- Nếu cùng độ sâu, **khai báo gặp trước** có thể quyết định.
- `dependencyManagement` có thể kiểm soát version được chọn và thay cách mediation thể hiện.
- `exclusions` và optional dependencies có thể loại hẳn một số nhánh.
- `tree` mặc định mô tả tập dependency được giải quyết, không phải danh sách mọi version từng được đề xuất. `-Dverbose` giúp xem thêm một số omitted nodes, nhưng không thay thế việc đọc effective POM/dependency management.

Đừng cố khắc phục xung đột bằng cách xóa thư viện bất kỳ khỏi `~/.m2/repository`: cache không quyết định graph version theo kiểu “file nào đang tồn tại thì Maven ưu tiên file đó”. Sửa khai báo/management/exclusions có chủ đích và chạy lại test.

### 5.4. Xuất tree ra file, JSON hoặc DOT

```bash
# File văn bản để diff trong CI
mvn -B dependency:tree -DoutputFile=target/dependency-tree.txt

# JSON: Dependency Plugin phiên bản 3.7.0 trở lên
mvn -B dependency:tree -DoutputType=json -DoutputFile=target/dependency-tree.json

# DOT: dùng cho công cụ tạo sơ đồ như Graphviz
mvn -B dependency:tree -DoutputType=dot -DoutputFile=target/dependency-tree.dot
```

Theo tài liệu chính thức, các định dạng output được hỗ trợ gồm `text`, `dot`, `graphml`, `tgf` và `json` (JSON có từ Dependency Plugin 3.7.0). Chọn định dạng theo nhu cầu: text dễ đọc, JSON phù hợp công cụ phân tích, DOT cho trực quan hóa đồ thị.

Lưu ý: `-DoutputFile` và `-DoutputType` là tham số **của goal tree**, không làm Maven thay cách đóng gói project hoặc chọn dependency version. File output có thể thay đổi khi parent/BOM/profile/settings thay đổi dù mã Java không đổi.

## 6. dependency:build-classpath: chuyển dependency thành đường dẫn JAR

`dependency:build-classpath` tạo một **chuỗi classpath** chứa đường dẫn đến artifact files đã resolve (thường là JAR trong local repository), để dùng với JVM hoặc tool khác.

```bash
mvn -B dependency:build-classpath
```

Nếu không đặt `outputFile` hoặc `outputProperty`, goal có thể log classpath ở mức INFO. Dạng minh họa trên Linux/macOS:

```text
/home/dev/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar:/home/dev/.m2/repository/org/junit/jupiter/junit-jupiter/5.11.0/junit-jupiter-5.11.0.jar:...
```

Đường dẫn này **khác nhau theo máy và OS**, nên không thể dùng như output cố định. Trên Linux/macOS, separator đường dẫn classpath là `:`; trên Windows là `;`. Các path có thể chứa khoảng trắng và dấu gạch ngược. Goal có tham số thay separator nhưng thông thường nên để mặc định theo OS nơi file được dùng.

### 6.1. Ghi classpath vào file với đúng tên tham số

Đây là điểm dễ nhầm khi chuyển từ `list`/`tree` sang `build-classpath`:

```bash
mvn -B dependency:build-classpath -Dmdep.outputFile=target/dependency-classpath.txt
```

**`-Dmdep.outputFile` mới là user property được tài liệu hóa cho `build-classpath`.** Trong khi `dependency:list` và `dependency:tree` dùng `-DoutputFile`. Một số tài liệu hoặc cấu hình plugin dùng tên XML `<outputFile>`, nhưng **tên user property CLI không nhất thiết giống tên XML**.

Để chỉ lấy tập dependency phù hợp runtime classpath:

```bash
mvn -B dependency:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/dependency-classpath.txt
```

Với project ví dụ, file trên phải có đường dẫn đến `commons-lang3-3.17.0.jar` vì nó là compile dependency cần lúc chạy; nó **không cần JUnit** vì JUnit có scope test. Không giả định có một dấu newline hay thứ tự JAR cố định; muốn kiểm tra chính xác nên đọc file và tìm tên artifact.

Lưu ý khi chạy lặp lại: goal có kiểm tra độ mới của file. Nếu cần bảo đảm file được tái sinh dù có sẵn, tham số được hỗ trợ là `-Dmdep.regenerateFile=true`. Chọn một file output riêng cho từng module nếu project là multi-module.

### 6.2. build-classpath không tự thêm target/classes

**Cực kỳ quan trọng:** classpath được goal tạo là **đường dẫn đến dependencies**, chứ không tự bao gồm `target/classes` của project. Vì vậy chỉ chạy:

```bash
# Thiếu class của chính project:
java -cp "$(cat target/dependency-classpath.txt)" vn.example.deps.App
```

có thể gặp `ClassNotFoundException` hoặc `Could not find or load main class`, vì `App.class` nằm trong `target/classes`, không nằm trong các dependency JAR.

Sau khi `mvn clean verify` thành công, để chạy chương trình **trên Linux/macOS**, dùng:

```bash
mvn -B dependency:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/dependency-classpath.txt

# Ghép output classes và dependency classpath; quote để giữ nguyên dấu cách trong path
DEPS_CP="$(cat target/dependency-classpath.txt)"
java -cp "target/classes:$DEPS_CP" vn.example.deps.App
```

Nếu cần test chính JAR thay vì classes directory:

```bash
java -cp "target/dependency-goals-demo-1.0.0.jar:$DEPS_CP" vn.example.deps.App
```

Chỉ trên Unix, separator ở ví dụ là `:`. Với Windows PowerShell:

```powershell
mvn.cmd -B dependency:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/dependency-classpath.txt
$depsCp = (Get-Content -LiteralPath "target/dependency-classpath.txt" -Raw).Trim()
java.exe -cp "target/classes;$depsCp" vn.example.deps.App
```

Trên Windows, separator của classpath là `;`, không phải `:`. File JAR có thể nằm trong `C:\Users\...\ .m2\repository`; goal tự xuất path phù hợp với môi trường nơi nó chạy. **Đừng copy classpath file của Linux sang Windows rồi dùng trực tiếp.**

Đầu ra **chính xác** của chương trình Java minh họa khi classpath đúng:

```text
Dependency classpath OK
```

Không cần cấu hình manifest `Main-Class` vì ta dùng `java -cp ... vn.example.deps.App`. Lệnh `java -jar` hoạt động theo quy tắc manifest khác và không đương nhiên dùng classpath dòng lệnh như ví dụ.

### 6.3. includeScope và excludeScope của build-classpath

Giống `dependency:list`, goal này có `includeScope` và `excludeScope` để chọn tập dependency. Ví dụ:

```bash
# Runtime classpath
mvn -B dependency:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/runtime-cp.txt

# Test classpath: bao gồm tất cả scope cần xét theo ngưỡng test
mvn -B dependency:build-classpath -DincludeScope=test -Dmdep.outputFile=target/test-cp.txt
```

Đừng coi `includeScope=compile` là bộ lọc “chỉ những artifact viết scope=compile”: theo tài liệu plugin, nó còn tính provided và system. Với một app Java deploy lên servlet container, quyết định runtime/provided classpath phụ thuộc cả container, không chỉ chuỗi `build-classpath`.

Các bộ lọc như `includeGroupIds`, `excludeArtifactIds`, `excludeTransitive` có thể được dùng khi cần classpath đặc thù. Nhưng **lọc bớt dependency bắc cầu có thể làm app lỗi `NoClassDefFoundError` lúc chạy**. Với ứng dụng thông thường, hãy bắt đầu từ runtime classpath đầy đủ, rồi chỉ loại artifact nếu hiểu lý do.

### 6.4. build-classpath không tạo fat JAR

Goal này chỉ tạo **chuỗi đường dẫn**; nó không đóng gói dependency JAR vào artifact chính, không rewrite manifest, không copy toàn bộ JAR ra một thư mục phát hành và không biến `target/...jar` thành self-contained executable.

Muốn fat/uber JAR có thể cần Maven Shade Plugin, Maven Assembly Plugin hoặc plugin repackage của framework; đó là tác vụ khác với `dependency:build-classpath`. Nếu deploy Docker image, có thể chọn layout chứa JAR ứng dụng cùng thư viện ở thư mục `lib`; khi ấy cũng cần cấu hình copy/packaging tương ứng thay vì chỉ sinh classpath file.

## 7. So sánh ba goal trên cùng project

Với project ở mục 3, chạy:

```bash
mvn -B clean verify
mvn -B dependency:list
mvn -B dependency:tree
mvn -B dependency:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/dependency-classpath.txt
```

Đối chiếu kết quả:

| Điều cần quan sát | list | tree | build-classpath |
| --- | --- | --- | --- |
| Tên/version của Commons Lang | Có | Có | Chỉ qua tên/path file JAR |
| JUnit test dependency | Có theo bộ lọc mặc định | Có theo cây/scope | Không có khi `includeScope=runtime` |
| JUnit transitive chain | Danh sách phẳng | Thấy nhánh qua JUnit | Chỉ chứa path nếu scope cho phép |
| Quan hệ cha–con của graph | Không | **Có** | Không |
| Node bị loại do conflict | Không giải thích | Có thể xem qua `verbose` | Không |
| Tạo đường dẫn cho JVM | Không trực tiếp | Không trực tiếp | **Có** |
| Hỗ trợ xuất báo cáo | `-DoutputFile` | `-DoutputFile`, `-DoutputType` | `-Dmdep.outputFile` |
| Có tự sửa POM/build không? | Không | Không | Không |

Một **chuỗi classpath** có thể chứa ít artifact hơn `dependency:list` mặc định nếu bạn đã chọn `includeScope=runtime`. Đó là hành vi đúng, không phải Maven “làm mất” dependency test.

## 8. Scope, optional, exclusions và dependencyManagement ảnh hưởng ra sao?

### 8.1. Scope được propagate theo dependency graph

Không phải mọi dependency bắc cầu giữ nguyên scope đã khai báo ở POM cấp dưới. Maven tính **effective scope** dựa trên phạm vi của dependency dẫn đến nó và scope của dependency con, cùng các quy tắc transitivity. Những artifact có scope `test` thường không được đưa vào runtime classpath của ứng dụng; `provided` thường không đóng gói theo runtime set mà goal `build-classpath -DincludeScope=runtime` chọn.

Vì vậy, đọc output `list/tree` để kiểm tra scope sau resolution thay vì tự cho rằng mọi artifact dưới một dependency đều có cùng scope.

### 8.2. optional và exclusions

Giả sử một thư viện khai báo dependency với `<optional>true</optional>`; nó không tự trở thành transitive dependency của mọi consumer như một dependency bắt buộc. Consumer có thể phải khai báo trực tiếp nếu thật sự cần. `<exclusions>` trên dependency trực tiếp cũng có thể loại một nhánh transitive.

Ví dụ exclude một artifact qua POM (minh họa cấu trúc, không phải cấu hình cần áp dụng cho project ở mục 3):

```xml
<dependency>
    <groupId>vn.example.libs</groupId>
    <artifactId>integration-client</artifactId>
    <version>2.4.0</version>
    <exclusions>
        <exclusion>
            <groupId>vn.example.libs</groupId>
            <artifactId>old-transport</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Nếu thư viện thực tế `integration-client` phụ thuộc `old-transport`, exclusion có thể loại nó khỏi nhánh resolution. Tọa độ trong ví dụ là hư cấu: **không sao chép để chạy** nếu artifact không tồn tại. Khi sửa exclusions, cần thử compile/test/runtime vì loại transitive dependency có thể làm mất class cần thiết.

### 8.3. dependencyManagement và BOM

`dependencyManagement` trong POM/parent và BOM import có thể quyết định version được dùng khi resolve dependencies. Nhưng nó **không tự thêm dependency** vào project. Vì vậy, một artifact có version được quản lý trong BOM không chắc xuất hiện trong `dependency:list` hoặc `dependency:tree` nếu chưa có nhánh thực sự yêu cầu artifact đó.

Ví dụ một POM quản lý `org.apache.commons:commons-lang3:3.17.0`; nếu dự án không khai báo/không kéo theo Commons Lang, nó sẽ không xuất hiện như một JAR runtime chỉ vì có management.

Nếu phiên bản trong `list` khác bản bạn tưởng dựa trên `<dependencies>`, kiểm tra effective POM, parent, BOM, active profiles và cây dependency. Maven có thể đã áp dụng version management hoặc hòa giải các nhánh transitive.

## 9. Các trường hợp thực tế và quy trình chọn đúng goal

### 9.1. “Một artifact lạ xuất hiện, ai kéo vào?”

Dùng:

```bash
mvn -B dependency:tree -Dincludes=org.junit.jupiter
```

Quan sát nhánh cha của artifact trong tree. Nếu thấy version mâu thuẫn hoặc node bị bỏ, kiểm tra `-Dverbose` và `dependencyManagement`. Sau đó quyết định update version, thay dependency trực tiếp hay dùng exclusion có chủ đích. Không chỉnh nhầm cache local hoặc settings mirror khi vấn đề là dependency graph.

### 9.2. “Tôi cần danh sách dependency đã resolve để đối chiếu hoặc kiểm toán”

```bash
mvn -B dependency:list -DoutputFile=target/dependency-list.txt
```

Đầu ra dạng tọa độ hữu ích để đối chiếu giữa hai lần build; có thể lưu report dưới dạng CI artifact. Tuy nhiên, đây **không mặc nhiên là SBOM đầy đủ** theo chuẩn CycloneDX/SPDX: nó không đảm bảo chứa thông tin license, hash, vulnerabilities, container/native dependencies hay dependencies ngoài Maven. Với yêu cầu SBOM chính thức, sử dụng công cụ chuyên dụng và chính sách supply chain của tổ chức.

### 9.3. “Tôi muốn chạy class Java từ terminal sau khi compile”

```bash
mvn -B clean package
mvn -B dependency:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/dependency-classpath.txt
```

Sau đó ghép đường dẫn `target/classes` hoặc JAR chính với chuỗi trong classpath file, sử dụng separator `:` hoặc `;` theo OS như mục 6.2. Nếu phụ thuộc vào Java module path (`--module-path`) hoặc module system, classpath truyền thống có thể không phản ánh đầy đủ module graph; phải thiết kế lệnh khởi động riêng phù hợp Java module system.

### 9.4. “Tôi muốn biết vì sao laptop chạy được nhưng CI không”

Chạy ba goal bằng **cùng JDK/Maven/plugin version** và cùng Maven settings/active profiles càng giống càng tốt. So sánh:

1. `dependency:list`: artifact version và scope nào khác?
2. `dependency:tree`: nhánh transitive nào gây khác biệt?
3. `dependency:build-classpath`: file thực tế nằm ở đâu, separator OS đúng không?
4. `help:effective-pom` (khi cần): parent/BOM/profiles đã được áp dụng như mong muốn chưa?
5. `mvn -X ...` (khi được phép): repository resolution/cache có vấn đề gì, nhưng cần lọc thông tin nhạy cảm khỏi debug log.

Cần biết phân biệt lỗi graph/version với lỗi tải artifact: nếu Maven chưa tải được một dependency do repository/credentials, cả ba goal có thể dừng ở bước resolution trước khi in kết quả.

## 10. Maven multi-module: mục tiêu của mỗi module và reactor

Trong dự án có nhiều module, Maven có thể chạy goal cho nhiều reactor projects. Ví dụ root aggregator:

```text
multi-module/
├── pom.xml             (packaging=pom, có <modules>)
├── api/pom.xml
└── service/pom.xml
```

Gọi ở root:

```bash
mvn -B dependency:tree
```

có thể in nhiều cây khác nhau cho từng module được build. Không được hiểu đó là một cây duy nhất đại diện cho toàn bộ organization. Module `api` và `service` có dependency graph, scopes và plugin configuration riêng.

Khi muốn xem cụ thể một module:

```bash
mvn -B -pl service dependency:tree
```

`-pl` chọn project/module trong reactor. Nếu module phụ thuộc vào những module anh em chưa install/không được build phù hợp, resolution có thể thất bại; cần chạy các phase/goal cần thiết trên reactor (`-am` để đưa những module cần thiết vào build) hoặc đảm bảo artifact nội bộ có sẵn trong local repository. Không cố dùng `build-classpath` của một module rồi xem đó là classpath tổng của cả reactor.

Với `build-classpath` ở nhiều module, cần xuất ra **file riêng cho mỗi module** để tránh trộn kết quả; đường dẫn tương đối `target/...` được hiểu trong ngữ cảnh project thực thi goal. Khi cần phân tích một service ở CI, nên chỉ định module rõ ràng và giữ nguyên build profiles.

## 11. Những lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `No plugin found for prefix 'dependency'` | Không resolve được Dependency Plugin/prefix mapping, repository/pluginRepository thiếu | Pin plugin, dùng tọa độ goal đầy đủ, kiểm tra mirrors/network |
| `PluginResolutionException` | Plugin JAR/POM hoặc plugin dependencies không tải được | Kiểm tra phiên bản plugin, settings, cache, quyền truy cập |
| `DependencyResolutionException` | Dependency dự án chưa có hoặc bị xung đột/khai báo sai | Tọa độ, parent/BOM, repositories, online/offline |
| `dependency:list` có nhiều mục hơn POM | Có dependencies bắc cầu | Dùng `tree` để truy nguồn |
| `tree` không thấy version mà bạn mong | Mediation/management/omission | Effective POM, `tree -Dverbose`, exclusions |
| `build-classpath` xuất cả JUnit nhưng chỉ muốn runtime | Không lọc scope, mặc định có thể lấy cả test | `-DincludeScope=runtime` |
| Classpath file không được tạo tại nơi mong đợi | Dùng sai `-DoutputFile` thay vì `-Dmdep.outputFile` | Dùng đúng property goal và kiểm tra đường dẫn |
| `java` báo `Could not find or load main class` | Thiếu `target/classes`/JAR project trong `-cp` hoặc sai tên main class | Ghép path output của project với deps; kiểm tra package/class |
| `NoClassDefFoundError` ở runtime | Thiếu JAR transitive, lọc quá chặt hoặc classloader khác | Dùng runtime graph đầy đủ, kiểm tra `build-classpath` |
| Lệnh chạy trên Linux nhưng lỗi ở Windows | Separator `:`/`;`, đường dẫn/quoting khác | Sinh classpath riêng trên từng OS và quote đúng |
| `dependency:tree` không thấy Maven build plugin | Goal báo cáo project dependencies, không phải plugin graph | Dùng công cụ/goal inspect plugin dependencies |
| Dự án multi-module in nhiều báo cáo | Maven áp goal trên các reactor projects | Chọn module với `-pl`, file output riêng |
| `mvn -o dependency:tree` lỗi khi offline | Thiếu plugin/dependency metadata/cache | Warm online đủ artifact, rồi kiểm thử offline |
| `json` tree không nhận `outputType` | Dependency Plugin quá cũ | Dùng plugin 3.7.0+ hoặc format có sẵn |
| Classpath chứa đường dẫn máy khác | Đã copy file classpath tuyệt đối sang máy/OS khác | Tái sinh classpath ở môi trường đích |

**Lưu ý về lỗi `ClassNotFoundException` và `NoClassDefFoundError`:** cả hai đều có thể liên quan classpath, nhưng không đồng nghĩa. Lỗi đầu thường xảy ra khi tìm class theo tên, lỗi sau có thể xảy ra khi JVM cần nạp class được tham chiếu nhưng không tìm được. Đọc stack trace và kiểm tra đúng artifact classpath thay vì chỉ thêm JAR tùy tiện.

## 12. Các hiểu nhầm quan trọng

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`dependency:list` chỉ có dependency trực tiếp.” | Mặc định nó còn có dependency bắc cầu đã resolve; có `-DexcludeTransitive=true` khi cần |
| “`dependency:tree` chỉ là list được in nhiều dòng.” | Tree cho biết **quan hệ** và nhánh dẫn đến dependency |
| “`build-classpath` tạo một JAR chạy độc lập.” | Nó tạo **chuỗi đường dẫn**, không đóng gói fat JAR |
| “Classpath file đã bao gồm class của project.” | Thường chỉ gồm dependency artifact paths; phải thêm `target/classes`/JAR project khi chạy |
| “`-DoutputFile` dùng giống nhau ở cả ba goal.” | `list/tree` dùng `outputFile`; `build-classpath` dùng `mdep.outputFile` |
| “`includeScope=runtime` nghĩa là chỉ scope ghi đúng runtime.” | Theo classpath semantics nó còn lấy compile dependencies |
| “`dependency:tree` cho thấy mọi version bị loại.” | Tree mặc định thường chỉ chọn tập thực tế; `verbose` có thể giúp xem omitted nodes |
| “Có dependency trong BOM thì `list` luôn hiển thị.” | Management không tự thêm dependency vào graph |
| “Xóa cache local sẽ giúp Maven chọn đúng version.” | Version do POM, management và mediation quyết định, không do file cache tùy tiện |
| “Build Maven thành công nghĩa là `java -cp` luôn chạy được.” | Phải chọn classpath đúng scope, OS separator và thêm class/JAR của project |
| “Maven Dependency Plugin là một goal built-in không cần tải.” | Nó là plugin, cũng phải resolve plugin artifacts |
| “File classpath sinh ở máy A dùng nguyên trên mọi máy.” | Path tuyệt đối và separator phụ thuộc môi trường |

## 13. Bài thực hành tự kiểm tra

**Bài 1 — Tìm dependency bắc cầu.** Với project JUnit trong mục 3, chạy `mvn dependency:list` và `mvn dependency:tree`. Kể tên một artifact nằm dưới `junit-jupiter` trong tree nhưng không được khai báo trực tiếp trong project POM.

**Gợi ý đáp án:** ví dụ `junit-jupiter-api` hoặc `junit-jupiter-engine` theo graph được resolve. `list` có thể hiển thị cùng artifact nhưng không cho biết nó được kéo từ nhánh nào; `tree` hiển thị quan hệ.

**Bài 2 — Chọn runtime classpath.** Bạn chỉ muốn chạy `vn.example.deps.App`, không chạy test. Lệnh tạo file classpath nào hợp lý và vì sao?

**Đáp án:** `mvn dependency:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/dependency-classpath.txt`. Nó giữ Commons Lang (compile dependency cần ở runtime), không đưa JUnit test vào runtime classpath theo bộ lọc này.

**Bài 3 — Chạy Java sau khi sinh classpath.** Vì sao lệnh `java -cp "$DEPS_CP" vn.example.deps.App` có thể không tìm được class của ứng dụng?

**Đáp án:** file tạo bởi goal chỉ chứa dependency paths, còn `App.class` nằm trong `target/classes` hoặc file JAR chính. Cần ghép đường dẫn đến output project bằng separator OS phù hợp trước khi gọi `java`.

**Bài 4 — Tìm phiên bản xung đột.** Hai dependency dẫn tới `x:y:1.0` và `x:y:2.0`. Goal nào nên dùng trước?

**Đáp án:** `dependency:tree` để tìm các nhánh, có thể thêm `-Dverbose` để xem node omitted; sau đó kiểm tra `dependencyManagement` và quy tắc nearest definition. `build-classpath` không giải thích lý do version thắng.

**Bài 5 — Kết quả classpath khác giữa CI và máy dev.** Đâu là hai nguyên nhân không cần sửa Java source?

**Gợi ý đáp án:** khác OS khiến separator/path khác; Maven settings/local repository hoặc active profiles/parent version khác khiến artifact được resolve khác. Cần đối chiếu effective POM, settings và scopes trước khi sửa dependencies.

## 14. Checklist sử dụng trong dự án thực tế

1. Chạy trong thư mục chứa POM đúng; xác minh `mvn --version` và project được chọn.
2. Pin phiên bản Maven Dependency Plugin thích hợp với môi trường (ví dụ 3.11.0).
3. Khi chỉ muốn **kiểm kê**: dùng `dependency:list`, có thể `includeScope` và `outputFile`.
4. Khi muốn **truy nguồn/xung đột**: dùng `dependency:tree`, lọc `includes` và dùng `verbose` khi cần.
5. Khi muốn **chuỗi đường dẫn JAR**: dùng `dependency:build-classpath` với `-Dmdep.outputFile`; chọn `includeScope=runtime` nếu chỉ chạy app.
6. Nếu chạy Java ngoài Maven: thêm `target/classes` hoặc JAR project vào `-cp`, quote đường dẫn, dùng `:` trên Unix và `;` trên Windows.
7. Khi khác version kỳ vọng: kiểm tra parent, BOM, `dependencyManagement`, scope, optional, exclusions và active profiles.
8. Với reactor multi-module: quan sát đúng module, tránh trộn kết quả nhiều project.
9. Nếu offline: phải có dependency, plugin và plugin dependencies trong cache; `-o` không tự tải artifact thiếu.
10. Kiểm tra bằng build/test thực tế. Cả ba goal hỗ trợ **quan sát/chạy thủ công**, không tự đảm bảo ứng dụng vận hành đúng, không thay thế integration tests hay SBOM chuyên dụng.

## Tài liệu chính thức

- [Apache Maven Dependency Plugin — dependency:list](https://maven.apache.org/plugins/maven-dependency-plugin/list-mojo.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Dependency Plugin — dependency:build-classpath](https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html)
- [Apache Maven Dependency Plugin — Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Apache Maven Dependency Plugin — Dependency Tree Output Formats](https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
