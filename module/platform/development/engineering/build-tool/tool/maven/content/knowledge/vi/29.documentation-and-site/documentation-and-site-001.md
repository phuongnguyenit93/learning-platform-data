# Build plugin và reporting plugin trong quá trình tạo tài liệu với Maven

> **Build Tool Maven · Tài liệu và Site**  
> Thực hành với Maven 3.9.x, Java 17, Maven Site Plugin 3.22.0, Javadoc Plugin 3.12.0, Project Info Reports Plugin 3.9.0 và Surefire/Surefire Report Plugin 3.6.1. Mục tiêu là hiểu đúng hai vị trí cấu hình plugin, luồng tạo tài liệu Markdown → HTML, báo cáo Javadoc/test/dependencies, bản Javadoc JAR và cách xác minh dữ liệu trước khi xuất bản website.

## 1. Vấn đề: tại sao `mvn package` và `mvn site` cho output khác nhau?

Một dự án Maven có thể tạo JAR chạy chương trình, Javadoc API, các báo cáo kiểm thử, thống kê dependencies và website dự án. Không phải mọi công việc này đều được kích hoạt cùng một lifecycle.

Hai vị trí quan trọng trong POM:

```xml
<build>
    <plugins>
        <!-- Plugin goals được dùng khi build project -->
    </plugins>
</build>

<reporting>
    <plugins>
        <!-- Report goals được dùng khi tạo website tài liệu -->
    </plugins>
</reporting>
```

- **Build plugin** được khai báo dưới `<build>`. Goal của nó được thực thi nếu đã được bind vào phase, được gọi trực tiếp hoặc có default binding tương ứng. Ví dụ Compiler Plugin biên dịch Java, Surefire Plugin chạy unit tests, JAR Plugin đóng gói JAR, Javadoc Plugin có goal tạo classified Javadoc artifact.
- **Reporting plugin** được khai báo dưới `<reporting>`. Maven Site Plugin lấy các reporting goals đã chọn, chạy chúng và tích hợp kết quả vào bộ HTML site.
- **Maven Site Plugin** là plugin điều phối site lifecycle. Nó dùng Apache Doxia parse Markdown/APT/XDoc, Doxia Sitetools render HTML/skin/navigation, Maven Reporting Executor gọi report goals.
- **Một plugin có thể thuộc cả hai vai trò**. Javadoc Plugin có goal `jar` để đính kèm tài liệu dưới dạng artifact và report goal `javadoc` để render API page trong website.

Điểm then chốt: **một plugin xuất hiện trong POM không có nghĩa mọi goal của plugin đều được thực thi**.

### 1.1. Bảng so sánh

| Nội dung | Build plugin | Reporting plugin |
| --- | --- | --- |
| Vị trí khai báo | `<build><plugins>` | `<reporting><plugins>` |
| Chọn goals | `<executions><execution><goals>` | `<reportSets><reportSet><reports>` |
| Trigger thông thường | `mvn compile`, `test`, `package`, `verify` hoặc goal CLI | `mvn site` |
| Output thường gặp | `.class`, JAR, XML test reports, Javadoc JAR | HTML reports, API pages trong `target/site` |
| Ví dụ | `maven-surefire-plugin:test`, `maven-javadoc-plugin:jar` | `maven-surefire-report-plugin:report-only`, `maven-javadoc-plugin:javadoc` |
| Đảm bảo tests đã chạy? | Chỉ khi runner thực sự chạy | **Không**, report có thể dùng XML cũ |
| Tự deploy? | Không | Không, cần site deployment riêng |

### 1.2. Hai kết luận sai phổ biến

Sai thứ nhất: “Đã khai báo Javadoc Plugin trong `<reporting>`, vậy `mvn package` tự có `-javadoc.jar`.”

Sai thứ hai: “`mvn site` sinh Surefire HTML màu xanh, vậy tất cả tests vừa được thực thi trong lần gọi đó.”

Cả hai không đúng. **Javadoc JAR cần build goal**, còn **Surefire report HTML đọc dữ liệu kiểm thử** chứ bản thân báo cáo không thay thế test runner.

## 2. Ba lifecycle Maven

Maven có ba lifecycle chính:

```text
clean:
  pre-clean -> clean -> post-clean

default (rút gọn):
  validate -> compile -> test -> package -> verify -> install -> deploy

site:
  pre-site -> site -> post-site -> site-deploy
```

Default lifecycle còn có những phases trung gian như `process-resources`, `test-compile`, `integration-test`, `post-integration-test`. Sơ đồ tập trung vào những mốc liên quan bài này.

### 2.1. `mvn clean package`

Đối với project Java có `<packaging>jar</packaging>`, lệnh này thường xóa output cũ, compile main/test Java, chạy unit tests, tạo main JAR và chạy **những goal bổ sung đã được bind tới package**. Nếu cấu hình Javadoc Plugin goal `jar` trong phase `package`, Maven còn sinh classified Javadoc JAR.

**Nó không tự chạy toàn bộ report goals trong `<reporting>`**. Vì thế không thể suy ra có bộ website `target/site` chỉ từ `BUILD SUCCESS` của `package`.

### 2.2. `mvn site`

Lệnh này kích hoạt **site lifecycle**, dùng Maven Site Plugin để tạo HTML từ tài liệu nguồn và báo cáo đã chọn. Thư mục output mặc định thường là:

```text
target/site/
```

**Nó không tương đương `mvn clean verify site`.** Một số report goals tự có dependency resolution hoặc lifecycle requirements, nhưng không được lấy điều đó để chứng minh mọi unit/integration tests vừa chạy.

### 2.3. Lệnh cho tài liệu và test report mới

Khi cần site báo cáo kết quả của chính checkout hiện tại:

```bash
mvn -B clean verify site
```

Lệnh thực thi build/test tới verify rồi tạo site. Tuy vậy, nếu project dùng `-DskipTests`, không discover tests hoặc report goal không lấy đúng XML, **cần đọc logs và XML** chứ không chỉ nhìn exit code.

### 2.4. `mvn site:site` khác `mvn site`

`site:site` là **goal** của Maven Site Plugin. `site` là **phase** trong site lifecycle. Gọi lifecycle phase cho phép các goals được bind vào site phases theo mô hình Maven; gọi một goal trực tiếp không nhất thiết chạy toàn bộ phases trước nó.

Bạn có thể gọi rõ plugin/version khi debug:

```bash
mvn org.apache.maven.plugins:maven-site-plugin:3.22.0:site
```

Nhưng để xây tài liệu từ project POM, thường dùng `mvn site` và pin Site Plugin version.

## 3. Site Plugin, Doxia và site descriptor

Nguồn site thông thường:

```text
src/site/
├── markdown/index.md
├── markdown/guide.md
├── apt/
├── xdoc/
├── resources/
│   ├── css/site.css
│   └── images/logo.png
└── site.xml
```

Trong bài lab chỉ cần hai Markdown và `site.xml`. Các thư mục APT/XDoc/resources được liệt kê để nhận diện những nguồn tài liệu khác Site Plugin hỗ trợ.

Quy trình:

```text
src/site/markdown/*.md
          |
      Apache Doxia
          |
     Site Renderer + skin + navigation
          |
          +--> report goals trong <reporting>
          |
          v
    target/site/*.html
```

**`src/site/markdown` khác `src/main/resources`**: bên đầu dành cho site, bên sau là application resources được copy vào classpath/JAR. Không phải cứ tạo một file Markdown là Java runtime sẽ load được nó.

### 3.1. Đường dẫn HTML sau render

Ví dụ:

```text
src/site/markdown/index.md  ->  target/site/index.html
src/site/markdown/guide.md  ->  target/site/guide.html
```

Do đó link trong Markdown nên dùng tên HTML đích:

```markdown
Xem [Hướng dẫn](guide.html).
```

Không dẫn người đọc site tới filesystem path `src/site/markdown/guide.md`.

### 3.2. `site.xml` làm gì?

`site.xml` là **site descriptor**; nó thiết kế menu, site title, navigation, banners và skin. Nó **không** phải `pom.xml`, không khai báo Maven dependencies và không trực tiếp bind report goals.

Ví dụ:

```xml
<site name="Maven Site Lab">
    <body>
        <menu name="Tài liệu">
            <item name="Tổng quan" href="index.html" />
            <item name="Hướng dẫn" href="guide.html" />
        </menu>
        <menu ref="reports" />
    </body>
</site>
```

`menu ref="reports"` hiển thị các liên kết reports mà site generator có. Nó không tự tạo report nếu reporting plugin tương ứng chưa được cấu hình hoặc chưa chạy.

## 4. `executions` khác `reportSets`

Build Javadoc JAR dùng:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <executions>
        <execution>
            <id>attach-api-docs</id>
            <phase>package</phase>
            <goals>
                <goal>jar</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Reporting Javadoc HTML dùng:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <reportSets>
        <reportSet>
            <reports>
                <report>javadoc</report>
            </reports>
        </reportSet>
    </reportSets>
</plugin>
```

**Hai ví dụ là fragments đặt ở hai khu vực khác nhau của POM**. Build fragment nằm dưới `<build><plugins>`; reporting fragment dưới `<reporting><plugins>`.

Trong build, `<execution>` có phase và goal. Trong reporting, `<reportSets>` có report goal names. Nếu đưa `<goal>` vào `<reports>` hoặc `<report>` vào build `<goals>`, đó không phải cấu hình hợp lệ tương đương.

### 4.1. Khi không khai báo `reportSets`

Site Plugin có thể chạy **tất cả reporting goals** mà plugin cung cấp theo mặc định. Một số report plugins có aggregate goals, có thể làm site lớn, report bị lặp hoặc chạy nhiều công việc không cần. Cách dễ kiểm soát là liệt kê rõ reports thực sự muốn render.

### 4.2. `pluginManagement` chỉ quản lý, không tự bind tùy ý

`<build><pluginManagement>` là chỗ tốt để ghim versions/config dùng chung. Nhưng chỉ đưa Maven Javadoc Plugin vào `pluginManagement` không tự làm `javadoc:jar` chạy ở `package`. Cần explicit execution trong `<build><plugins>` nếu không có default binding phù hợp.

## 5. Project Java 17 runnable: JAR, Javadoc JAR, HTML site và test report

Project này cho thấy **bốn loại đầu ra khác nhau**:

1. Main JAR.
2. Classified **Javadoc JAR** tạo bằng build plugin.
3. Surefire XML/text do JUnit tests được runner thực thi.
4. Website HTML từ Markdown và reporting plugins.

### 5.1. Cấu trúc thư mục

```text
maven-site-lab/
├── pom.xml
└── src/
    ├── main/java/org/example/site/
    │   ├── Calculator.java
    │   └── App.java
    ├── test/java/org/example/site/
    │   └── CalculatorTest.java
    └── site/
        ├── site.xml
        └── markdown/
            ├── index.md
            └── guide.md
```

Dùng **JDK 17+**, Maven **3.9.x** và repository/mirror cho plugins/dependencies khi cần tải lần đầu.

### 5.2. `pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example</groupId>
    <artifactId>maven-site-lab</artifactId>
    <version>1.0.0</version>
    <name>Maven Site Lab</name>
    <description>Documenting build and reporting plugins</description>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <executions>
                    <execution>
                        <id>attach-javadoc-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-site-plugin</artifactId>
                <version>3.22.0</version>
            </plugin>
        </plugins>
    </build>

    <reporting>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-project-info-reports-plugin</artifactId>
                <version>3.9.0</version>
                <reportSets>
                    <reportSet>
                        <reports>
                            <report>summary</report>
                            <report>dependencies</report>
                            <report>plugins</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <show>public</show>
                </configuration>
                <reportSets>
                    <reportSet>
                        <reports>
                            <report>javadoc</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-report-plugin</artifactId>
                <version>3.6.1</version>
                <reportSets>
                    <reportSet>
                        <reports>
                            <report>report-only</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
        </plugins>
    </reporting>
</project>
```

**Các plugin trong POM có vai trò tách biệt:**

| Plugin | Vai trò | Kết quả |
| --- | --- | --- |
| Compiler 3.14.1 | Build | Java classes |
| Surefire 3.6.1 | Build | Chạy JUnit, sinh test XML |
| Javadoc 3.12.0 | Build | `javadoc:jar` ở `package` |
| Site 3.22.0 | Build/site lifecycle | Dựng website |
| Project Info Reports 3.9.0 | Reporting | Summary/dependencies/plugins HTML |
| Javadoc 3.12.0 | Reporting | API HTML pages |
| Surefire Report 3.6.1 | Reporting | HTML từ test XML, không chạy lại tests |

Đây là một POM hoàn chỉnh, không phải tập snippets rời.

### 5.3. `src/main/java/org/example/site/Calculator.java`

```java
package org.example.site;

/**
 * Small integer arithmetic library.
 */
public final class Calculator {
    private Calculator() {
    }

    /**
     * Adds two integer values.
     *
     * @param first first addend
     * @param second second addend
     * @return the arithmetic sum, using int overflow semantics
     */
    public static int add(int first, int second) {
        return first + second;
    }
}
```

Đây là Java 17 source có **Javadoc comments hợp lệ trong bản cuối**. Mô tả `@param`/`@return` giúp tạo API docs có ý nghĩa thay vì chỉ danh sách method signatures.

### 5.4. `src/main/java/org/example/site/App.java`

```java
package org.example.site;

/**
 * Console entry point for the site demonstration.
 */
public final class App {
    private App() {
    }

    /**
     * Runs the sample program.
     *
     * @param args ignored command-line arguments
     */
    public static void main(String[] args) {
        System.out.println("2 + 3 = " + Calculator.add(2, 3));
    }
}
```

Sau compilation:

```bash
java -cp target/classes org.example.site.App
```

**Stdout chính xác:**

```text
2 + 3 = 5
```

POM không đặt `Main-Class` cho main JAR; vì vậy **không** giả định `java -jar target/maven-site-lab-1.0.0.jar` sẽ chạy được.

### 5.5. `src/test/java/org/example/site/CalculatorTest.java`

```java
package org.example.site;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsPositive() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void addsNegative() {
        assertEquals(-2, Calculator.add(-5, 3));
    }
}
```

Có **hai tests**, được đặt tên phù hợp Surefire default test discovery. Khi chạy được với Surefire 3.6.1 và JUnit Jupiter, dòng summary trọng tâm dự kiến là:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **dòng summary minh họa**, không phải toàn bộ Maven stdout.

### 5.6. `src/site/markdown/index.md`

```markdown
# Maven Site Lab

Dự án này minh họa build plugin và reporting plugin.

- Main JAR và Javadoc JAR là sản phẩm của build.
- Website HTML và các báo cáo là sản phẩm của site lifecycle.

Xem thêm [Hướng dẫn](guide.html).
```

### 5.7. `src/site/markdown/guide.md`

```markdown
# Quy trình tạo website tài liệu

1. Chạy `mvn clean verify`.
2. Chạy `mvn site`.
3. Mở `target/site/index.html`.

Javadoc JAR được tạo ở package.
Javadoc HTML report được tạo khi chạy site.
Surefire HTML report đọc XML có từ bước test.
```

Doxia render Markdown này thành `target/site/index.html` và `target/site/guide.html`.

### 5.8. `src/site/site.xml`

```xml
<site name="Maven Site Lab">
    <body>
        <menu name="Tài liệu">
            <item name="Tổng quan" href="index.html" />
            <item name="Hướng dẫn" href="guide.html" />
        </menu>
        <menu ref="reports" />
    </body>
</site>
```

Menu **Tài liệu** dẫn tới pages do bạn viết; menu **reports** dẫn tới báo cáo từ plugin goals. Chỉ sửa site descriptor không tự chạy thêm report plugin.

## 6. Thí nghiệm A — build plugin chạy đến `package`

Tại root project:

```bash
java -version
javac -version
mvn -version
mvn -B clean package
```

Các file quan trọng dự kiến xuất hiện:

```text
target/classes/org/example/site/Calculator.class
target/classes/org/example/site/App.class
target/test-classes/org/example/site/CalculatorTest.class
target/surefire-reports/TEST-org.example.site.CalculatorTest.xml
target/maven-site-lab-1.0.0.jar
target/maven-site-lab-1.0.0-javadoc.jar
target/apidocs/index.html
```

Lệnh:

```bash
jar tf target/maven-site-lab-1.0.0-javadoc.jar
```

dùng để xem HTML API docs đã được gói trong classified artifact. Main JAR chứa `.class`; `-javadoc.jar` chứa documentation HTML và không tự tạo executable Java program.

**Quan trọng:** `target/apidocs` là output thường gặp của Javadoc khi chạy standalone/build-oriented goal. Nó **khác** `target/site/apidocs` dành cho Javadoc report trong website.

Nếu sau `mvn clean package` chưa có `target/site/index.html`, đó là **đúng** vì site lifecycle chưa được yêu cầu.

## 7. Thí nghiệm B — website và reporting goals

Chạy:

```bash
mvn -B clean verify site
```

Thông thường sẽ có:

```text
target/site/
├── index.html
├── guide.html
├── apidocs/
│   └── index.html
├── css/
│   └── ...
└── [các trang HTML report được chọn]
```

Đây chỉ là **một phần cây output**, không phải cam kết tên mọi file. Theme/skin và report plugin có thể thêm CSS, JS, images và nhiều HTML pages với tên khác nhau.

Các trang/hạng mục cần kiểm tra:

1. Trang Markdown `index.html`, có link đến `guide.html`.
2. Menu Tài liệu chứa hai liên kết do `site.xml` khai báo.
3. Menu Project Reports hoặc các liên kết report tương ứng.
4. Javadoc public API có `Calculator.add` và `App.main`.
5. Project summary report, dependencies report và plugins report.
6. Surefire HTML report hiển thị số liệu từ XML tests hiện tại.

**`BUILD SUCCESS` chỉ là điều kiện cần**, không thay cho kiểm tra link/HTML hoặc dữ liệu báo cáo.

### 7.1. Cách xem site local

Bộ HTML trong `target/site` là **static files**. Bạn có thể mở `target/site/index.html` trong trình duyệt bằng file explorer. Trên macOS:

```bash
open target/site/index.html
```

Trên Linux có môi trường desktop:

```bash
xdg-open target/site/index.html
```

Trên Windows PowerShell, dùng File Explorer hoặc:

```powershell
Invoke-Item .\target\site\index.html
```

Khi kiểm tra assets/relative links, bạn cũng có thể phục vụ site bằng một static HTTP server của môi trường local. Không cần deploy lên Internet để làm bài lab.

### 7.2. Đọc test report đúng thời điểm

Surefire runner ghi:

```text
target/surefire-reports/TEST-org.example.site.CalculatorTest.xml
```

Trong khi Surefire Report Plugin chuyển kết quả ấy thành **HTML report trong site**. Nếu bạn chỉ chạy `mvn site` sau một build cũ, XML cũ có thể vẫn còn, nên HTML xanh có thể phản ánh kết quả hôm trước.

Với CI, dùng `mvn clean verify site`, đọc Surefire logs và XML, kiểm tra test count/phân tích failures, rồi mới gắn nhãn test suite PASS.

### 7.3. Đừng nhầm output của các goal

```text
target/maven-site-lab-1.0.0.jar         -> main artifact
target/maven-site-lab-1.0.0-javadoc.jar -> classified documentation artifact
target/apidocs/                         -> standalone/build Javadoc output
target/site/apidocs/                    -> website Javadoc report
target/site/index.html                  -> website home
target/surefire-reports/                -> XML/text test results
```

Một Javadoc JAR **không thay thế website Javadoc**; website có API pages không có nghĩa `-javadoc.jar` đã được install/deploy.

## 8. Surefire runner và Surefire Report Plugin là hai thành phần

**Maven Surefire Plugin** (`surefire:test`) thường chạy khi Maven đi qua phase `test` trong Java JAR lifecycle. Nó discover/run JUnit tests và tạo XML/text results.

**Maven Surefire Report Plugin** (`surefire-report:report-only`) đọc những XML results đó để tạo báo cáo HTML. Goal `report-only` **không chạy tests**, phù hợp khi tests đã được chạy trước site generation.

### 8.1. Cấu hình hai nơi

Build:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
</plugin>
```

Reporting:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-report-plugin</artifactId>
    <version>3.6.1</version>
    <reportSets>
        <reportSet>
            <reports>
                <report>report-only</report>
            </reports>
        </reportSet>
    </reportSets>
</plugin>
```

Các fragments này không phải dependencies ứng dụng; đừng đưa report plugin vào `<dependencies>` chỉ để có HTML.

### 8.2. Failsafe/integration tests là báo cáo khác

Nếu project sử dụng Maven Failsafe Plugin cho integration tests ở các phase `integration-test`/`verify`, Surefire Report Plugin có goal **`failsafe-report-only`** để render kết quả Failsafe tương ứng. Nó không tự dựng database, server hay chạy integration tests.

Đừng hiểu Surefire `report-only` là parser bao trùm tất cả kết quả kiểm thử trong mọi plugin.

## 9. Project Info Reports Plugin lấy dữ liệu gì?

`maven-project-info-reports-plugin` có nhiều reporting goals:

| Goal | Dữ liệu |
| --- | --- |
| `summary` | Thông tin tổng quan project |
| `dependencies` | Dependencies và metadata |
| `plugins` | Plugin configuration |
| `dependency-management` | Chính sách versions được quản lý |
| `plugin-management` | Plugin versions/management |
| `licenses` | License metadata |
| `team` | Developers/contributors |
| `scm` | SCM metadata |
| `modules` | Modules của aggregator |

Nhiều báo cáo có thể thiếu dữ liệu nếu project POM không khai báo tương ứng. Vì thế lab chọn `summary`, `dependencies`, `plugins`, không tự dựng tên SCM/team/licenses giả.

### 9.1. `reportSets` giúp scope rõ

```xml
<reportSets>
    <reportSet>
        <reports>
            <report>summary</report>
            <report>dependencies</report>
            <report>plugins</report>
        </reports>
    </reportSet>
</reportSets>
```

Nếu không có `reportSets`, plugin có thể chạy nhiều report goals hơn dự kiến, đặc biệt khi có aggregate reports.

### 9.2. `excludeDefaults`

Reporting có cấu hình tùy chọn:

```xml
<reporting>
    <excludeDefaults>true</excludeDefaults>
    <plugins>
        <!-- Các reports được khai báo rõ -->
    </plugins>
</reporting>
```

Đây là **fragment nâng cao**, không có trong POM lab. Nó kiểm soát **default reports** mà site generator thường thêm. Không hiểu `excludeDefaults=true` là tắt toàn bộ reporting goals được khai báo rõ.

### 9.3. Output directory của reporting goal

Nhiều reporting goals có tham số `outputDirectory`. Khi gọi goal **standalone**, output path có thể theo goal config. Khi Site Plugin gọi goal **để tích hợp website**, Site Plugin quyết định shared output directory.

Vì thế output của:

```bash
mvn project-info-reports:dependencies
```

không nhất thiết ở cùng path với trang dependencies tạo ra qua:

```bash
mvn site
```

Luôn xem output thực tế và Site Plugin docs.

## 10. Javadoc Plugin: build config và reporting config có thể khác

Javadoc Plugin 3.12.0 hỗ trợ cả hai ngữ cảnh.

Ví dụ build:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.12.0</version>
            <configuration>
                <show>private</show>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Ví dụ reporting:

```xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.12.0</version>
            <configuration>
                <show>public</show>
            </configuration>
        </plugin>
    </plugins>
</reporting>
```

Hai đoạn **chỉ minh họa** sự khác biệt config và không cần đưa vào POM lab. Tài liệu Apache Maven Javadoc Plugin ghi rõ cấu hình từ build và reporting **không nhất thiết có cùng hành vi merge**. `mvn site` có thể chọn public API docs, trong khi standalone Javadoc goal có thể áp cấu hình khác.

### 10.1. Lỗi khi render Javadoc

Các lỗi thường gặp:

- Type/member trong `{@link ...}` không tồn tại.
- JavaDoc HTML tags không hợp lệ.
- Thiếu dependencies trên documentation classpath.
- JDK toolchain không khớp source/release.
- Package/module name thay đổi nhưng comments chưa được cập nhật.
- Cấu hình doclint hoặc source level của project không nhất quán.

Đừng mặc định tắt doclint/failOnError để che lỗi docs. Cần sửa comments, API references hoặc dependencies cho đúng.

### 10.2. Javadoc JAR khác source JAR

- `artifactId-version.jar`: compiled classes/resources.
- `artifactId-version-javadoc.jar`: API HTML documentation.
- `artifactId-version-sources.jar`: Java source files, thường dùng Maven Source Plugin.

Không nhầm các loại artifacts khi upload hoặc kiểm chứng dependency repository.

## 11. Multi-module sites và báo cáo tổng hợp

Một reactor có thể gồm:

```text
parent (packaging=pom)
├── api
├── implementation
└── application
```

Khi chạy site từ reactor, mỗi module có thể tạo output riêng dưới `target/site`. Tuy vậy **module links trên filesystem local không chắc đúng** với cách URL được triển khai sau publish.

Maven Site Plugin hỗ trợ:

```bash
mvn site
mvn site:stage
```

để kiểm tra **staged site layout** và các liên kết cross-module. `site:stage` có thể cần `distributionManagement.site` hợp lệ hoặc cấu hình staging tương ứng.

### 11.1. Inheritance của reporting

Nếu parent POM khai báo reporting plugin, các children có thể kế thừa/merge cấu hình. Những goal `aggregate` của Javadoc/JXR/Checkstyle hoặc plugins khác có thể cần `reportSet` riêng, và `<inherited>false</inherited>` khi không muốn chạy trên từng child.

**Per-module report** không giống **aggregate report**: cái trước mô tả một module, cái sau gom dữ liệu các modules. Khi chỉ chọn reactor subset bằng `-pl`, báo cáo tổng cũng có thể thiếu modules. Đừng cho rằng một site ở root luôn chứa tất cả trang API của mọi module nếu chưa xác minh.

### 11.2. Site deployment và artifact deployment

POM có thể cấu hình:

```xml
<distributionManagement>
    <site>
        <id>documentation-site</id>
        <url>file:///var/www/maven-site-lab</url>
    </site>
</distributionManagement>
```

Đây **chỉ là fragment ví dụ cho hệ thống Unix có thư mục và quyền phù hợp**, không thuộc POM runnable. `mvn site:deploy` có thể ghi vào destination, nên không chạy thử khi chưa cấu hình đích/ủy quyền.

**`mvn deploy` không tự upload HTML site**: nó publish artifacts JAR/POM theo repository configuration. Tách hai workflows trong CI để tránh công khai site ngoài ý muốn.

## 12. CI: quality gate cho tài liệu và báo cáo

Một pipeline có thể:

```text
Checkout source
    |
mvn clean verify
    +-- Java classes
    +-- JUnit XML/text reports
    +-- Main JAR và Javadoc JAR
    |
mvn site
    +-- Markdown -> HTML qua Doxia
    +-- Javadoc reporting HTML
    +-- Project Info Reports HTML
    +-- Surefire Report HTML từ XML
    |
Kiểm tra output, links, freshness, thông tin nhạy cảm
    |
Upload target/site vào CI artifacts hoặc publish có kiểm soát
```

Dùng một command nếu muốn đơn giản:

```bash
mvn -B -V clean verify site
```

### 12.1. Những điều phải kiểm tra

- Surefire logs xác nhận số tests mong đợi thực sự đã chạy.
- `target/surefire-reports` chứa XML từ checkout hiện tại.
- `target/site/index.html` và `guide.html` có nội dung đúng.
- Menu report có links hợp lệ; pages được sinh.
- API Javadoc có các public classes/methods cần công bố.
- `-javadoc.jar` tồn tại nếu pipeline định publish classified artifact.
- HTML encoding, link, CSS, hình ảnh hoạt động.
- Site không lộ credentials, tokens, internal-only repository URLs.
- Không có phần báo cáo **rỗng** bị coi là một kiểm tra thành công.
- Có owner/quy trình duyệt khi deploy công khai.

**Chỉ nhìn `BUILD SUCCESS` là chưa đủ để tuyên bố website/documentation đạt chất lượng.**

### 12.2. Khác biệt giữa quality gate và report

Một báo cáo PMD/Checkstyle có thể **hiển thị vi phạm** nhưng site vẫn render thành công. Nếu cần fail CI, phải dùng build-time **check goal** có policy thích hợp. Reporting goal là kênh trình bày thông tin, không mặc định là quality gate.

Tương tự, Surefire Report Plugin không thay thế `surefire:test`. Nếu muốn ngăn merge khi test fail, cần test runner thực sự chạy và Maven build phải fail.

### 12.3. Site public có thể lộ metadata

Các Project Info reports có thể lộ tên modules, version dependencies, SCM URLs, developers/team hoặc các repository URLs nếu POM khai báo. Kiểm tra generated HTML trước khi public, tránh để tokens/passwords trong POM hoặc site source. `site` thành công không có nghĩa nội dung an toàn để chia sẻ.

## 13. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `mvn package` không tạo `target/site` | Chưa chạy site lifecycle | `mvn site` |
| Có Javadoc JAR, không có Javadoc trong site | Chỉ bind build `javadoc:jar` | Thêm Javadoc reporting goal |
| Có Javadoc HTML trong site, không có `-javadoc.jar` | Chỉ có report goal | Bind build goal `jar` ở package |
| Chỉ có plugin trong `pluginManagement` | Chưa có execution | Thêm plugin/execution khi cần |
| Reporting plugin chỉ nằm trong build | Không có report configuration | Thêm `<reporting><plugins>` |
| Report không hiện | Sai goal name/reportSets | Kiểm tra `<report>` và plugin docs |
| Dùng `<goal>` bên trong `<reports>` | Sai syntax | Dùng `<report>` |
| Site không hiển thị Markdown | Sai `src/site/markdown` | Kiểm tra file path/Doxia |
| Menu thiếu Project Reports | Thiếu `menu ref="reports"` | Sửa `site.xml` |
| Surefire HTML rỗng | Không có XML, tests bị skip | `mvn clean verify site`, xem runner |
| Surefire HTML xanh nhưng là build cũ | XML còn sau invocation trước | Clean và kiểm tra test logs |
| Javadoc báo error | Link/type/doclint/classpath | Sửa comments/API/release |
| Site reports nhiều hơn mong đợi | Không cấu hình reportSets | Chọn report goals cụ thể |
| `java -jar` báo không có Main-Class | Main JAR không cấu hình entry point | `java -cp target/classes org.example.site.App` |
| Multi-module links hỏng | Local layout khác deployment | Dùng site staging |
| Maven Site Plugin 2.x trên Maven 3 thiếu reports | Plugin 2.x không hỗ trợ như 3.x | Nâng phiên bản site plugin |
| `mvn deploy` không có HTML | Artifact deploy khác site deploy | Dùng site workflow |
| `site:deploy` lỗi 403/transport | Thiếu credentials/URL/Wagon | Kiểm tra destination được ủy quyền |
| Site bị lỗi tiếng Việt | Encoding source/report khác | Dùng UTF-8, kiểm tra output |
| Site HTML lộ private metadata | POM report trích nội bộ | Rà soát trước public |

### 13.1. Quy trình kiểm tra tuần tự

```bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn -B clean verify site
```

Đọc:

1. `build.plugins` và `reporting.plugins`.
2. `reportSets` có goals hợp lệ.
3. `src/site/markdown`, `src/site/site.xml`.
4. Surefire XML và test count.
5. Main JAR/Javadoc JAR.
6. `target/site` và các report pages thực.
7. JavaDoc links và nội dung.
8. Site deploy URL (chỉ khi cần publish).

Khi cần debug:

```bash
mvn -X site
```

Log `-X` có thể chứa internal paths, proxy, repository URLs; lọc thông tin nhạy cảm trước khi chia sẻ.

## 14. Câu hỏi tự kiểm tra

**1.** Build plugin cấu hình ở đâu?  
**Đáp án:** `<build><plugins>`.

**2.** Reporting plugin cấu hình ở đâu?  
**Đáp án:** `<reporting><plugins>`.

**3.** Build goal dùng XML gì để bind phase?  
**Đáp án:** `<executions><execution><phase><goals><goal>`.

**4.** Reporting goal dùng XML gì để chọn?  
**Đáp án:** `<reportSets><reportSet><reports><report>`.

**5.** `mvn package` có mặc định tạo HTML site không?  
**Đáp án:** Không.

**6.** Site Plugin dùng thành phần nào parse Markdown?  
**Đáp án:** Apache Doxia.

**7.** `src/site/site.xml` điều khiển gì?  
**Đáp án:** Giao diện/menu/navigation của site.

**8.** `menu ref="reports"` có tự sinh report plugin không?  
**Đáp án:** Không; nó liên kết reports đã tạo.

**9.** `javadoc:jar` tạo gì?  
**Đáp án:** Classified Javadoc artifact.

**10.** Javadoc reporting goal tạo gì?  
**Đáp án:** API HTML pages trong site.

**11.** Surefire `report-only` có chạy JUnit tests không?  
**Đáp án:** Không, nó đọc XML results.

**12.** Làm sao tránh Surefire HTML báo dữ liệu cũ?  
**Đáp án:** Build sạch bằng `mvn clean verify site`, kiểm tra logs/XML.

**13.** `mvn deploy` có giống `mvn site:deploy` không?  
**Đáp án:** Không; một bên publish Maven artifacts, một bên publish website.

**14.** Vì sao cần reportSets?  
**Đáp án:** Chọn những báo cáo cần, tránh reports dư/aggregate sai.

**15.** Reporting plugin có là dependency runtime của app không?  
**Đáp án:** Không.

**16.** Multi-module nên kiểm tra staging khi nào?  
**Đáp án:** Trước publish khi cần xác nhận parent-child links đúng.

**17.** Một HTML report tồn tại có chứng minh tests PASS ở commit hiện tại?  
**Đáp án:** Không; cần xác nhận XML/run mới.

**18.** Một website được render thành công đã an toàn public chưa?  
**Đáp án:** Chưa; cần security/content/link review.

## 15. Checklist trước khi phát hành website

- [ ] Plugin versions phù hợp Maven 3/JDK 17 và được ghim.
- [ ] Phân biệt đúng `<build>` với `<reporting>`.
- [ ] Build goal `javadoc:jar` có execution khi cần artifact.
- [ ] Javadoc report có trong `reportSets` khi cần API website.
- [ ] Project Info reports chọn các mục có dữ liệu hữu ích.
- [ ] Surefire runner chạy trước Surefire `report-only` khi muốn report mới.
- [ ] Markdown nằm đúng `src/site/markdown`.
- [ ] Site descriptor có menu và HTML links phù hợp.
- [ ] Đã chạy `mvn clean verify site`.
- [ ] Đã kiểm tra test count, XML và Surefire HTML cùng lần.
- [ ] Đã kiểm tra `-javadoc.jar` và `target/site/apidocs` riêng.
- [ ] Đã xem `target/site/index.html` trong trình duyệt.
- [ ] Các links/assets/encoding không bị lỗi.
- [ ] Với multi-module, đã kiểm tra staging/aggregate reports.
- [ ] Artifact repository deploy và website deploy tách biệt.
- [ ] Đã rà soát thông tin nhạy cảm trước public.
- [ ] Website được publish chỉ khi có phê duyệt và đích rõ.

## 16. Nguồn tham khảo chính thức

1. [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html).
2. [Apache Maven — POM Reference / Reporting](https://maven.apache.org/pom.html).
3. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html).
4. [Maven Site Plugin 3.22.0 — Overview](https://maven.apache.org/plugins-archives/maven-site-plugin-3.22.0/).
5. [Maven Site Plugin — Creating Content](https://maven.apache.org/plugins/maven-site-plugin/examples/creating-content.html).
6. [Maven Site Plugin — Site Descriptor](https://maven.apache.org/plugins/maven-site-plugin/examples/sitedescriptor.html).
7. [Maven Site Plugin — Configuring Reports](https://maven.apache.org/plugins/maven-site-plugin/examples/configuring-reports.html).
8. [Maven Site Plugin — Usage and Site Staging](https://maven.apache.org/plugins/maven-site-plugin/usage.html).
9. [Maven Javadoc Plugin 3.12.0 — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html).
10. [Maven Javadoc Plugin — `javadoc:jar`](https://maven.apache.org/plugins/maven-javadoc-plugin/jar-mojo.html).
11. [Project Info Reports Plugin 3.9.0](https://maven.apache.org/plugins/maven-project-info-reports-plugin/).
12. [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/).
13. [Maven Surefire Report Plugin](https://maven.apache.org/surefire/maven-surefire-report-plugin/).

**Ghi nhớ:** **Build plugin** tạo artifacts và chạy goals theo build lifecycle; **reporting plugin** tạo những báo cáo được Site Plugin đưa vào website; **Doxia** chuyển nguồn tài liệu thành HTML. Javadoc JAR khác Javadoc website, còn Surefire HTML report không tự đảm bảo test runner vừa chạy. Kiểm tra riêng **build outputs, report freshness và site nội dung** trước khi publish.
