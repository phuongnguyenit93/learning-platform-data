# Cố định phiên bản plugin tài liệu và kiểm tra lỗi tạo báo cáo trong Maven

## 1. Bài toán: build thành công nhưng tài liệu vẫn không đạt

Một dự án Maven có thể báo `BUILD SUCCESS` khi chạy `mvn clean verify` mà không có `target/site`, hoặc tạo được website nhưng thiếu Javadoc, trang Dependencies hay kết quả unit test. Một trường hợp khác: site chạy tốt trên máy người phát triển, còn CI báo lỗi trong Doxia, skin hoặc Maven Reporting API khi repository tự chọn một phiên bản plugin mới.

Điều này xảy ra vì **build sản phẩm** và **tạo website tài liệu** là hai quy trình có những đầu vào khác nhau:
- `mvn verify` chạy các goals được gắn vào default build lifecycle: compile, test, package và các bước verification.
- `mvn site` tạo website từ Markdown/APT/XDoc và các **reporting plugins** mà POM khai báo.
- Javadoc cần Java source và Javadoc tool; Surefire HTML cần `TEST-*.xml` do test runner tạo; dependency report cần dependency graph và POM metadata.
- Website có file `index.html` chưa đủ để kết luận các báo cáo bắt buộc đã được tạo, có dữ liệu mới nhất và không bị lỗi ẩn.

Bài này hướng dẫn **cố định phiên bản plugin tạo tài liệu và báo cáo** rồi **kiểm tra chất lượng đầu ra** theo chuỗi:

```text
Version/compatibility
       |
       v
Input readiness (source, tests, POM, config)
       |
       v
Report goal execution
       |
       v
Generated HTML files
       |
       v
Content checks / CI acceptance
```

Các ví dụ sử dụng Maven **3.9.x**, Java **17+** và một bộ plugin được ghim cụ thể theo tài liệu Apache Maven công bố đến năm 2026. Không dùng những version bên dưới như quy tắc vĩnh viễn: nâng version cần xem release notes, system requirements và chạy lại kiểm thử site.

| Thành phần | Artifact ID | Version ví dụ |
| --- | --- | --- |
| Maven Site | `maven-site-plugin` | `3.22.0` |
| Thông tin dự án | `maven-project-info-reports-plugin` | `3.9.0` |
| Tài liệu API | `maven-javadoc-plugin` | `3.12.0` |
| Render báo cáo test | `maven-surefire-report-plugin` | `3.6.1` |
| Chạy JUnit test | `maven-surefire-plugin` | `3.6.1` |
| Biên dịch Java | `maven-compiler-plugin` | `3.13.0` |
| Đóng gói JAR | `maven-jar-plugin` | `3.4.2` |

Đây là những **plugin versions khác nhau**, không cần có cùng số version. Riêng Surefire Plugin và Surefire Report Plugin cùng thuộc hệ sinh thái Surefire nên ví dụ chọn đồng nhất `3.6.1` cho dễ đối chiếu.

### Mục tiêu sau bài học

1. Phân biệt Site lifecycle với default build lifecycle.
2. Hiểu `build/plugins` khác `reporting/plugins` và `pluginManagement`.
3. Ghim chính xác phiên bản Site, Javadoc, Project Info, Surefire và các build plugins.
4. Dùng `reportSets` chọn báo cáo cần có, không phụ thuộc bộ report mặc định.
5. Phân biệt `surefire-report:report` với `surefire-report:report-only`.
6. Biết dữ liệu nào phải tồn tại trước khi tạo HTML.
7. Tạo project Java 17/JUnit 5 hoàn chỉnh có Markdown, Javadoc, Project Info và Surefire report.
8. Xác minh `TEST-*.xml`, HTML pages và test counts, không chỉ nhìn `BUILD SUCCESS`.
9. Chẩn đoán lỗi Javadoc, Doxia, plugin resolution, output directory, profile và CI cache.
10. Kiểm soát aggregate reports/multi-module navigation và site publishing.

## 2. Site và reporting nằm ở đâu trong Maven?

### 2.1. Hai vòng đời khác nhau

Maven mặc định có nhiều lifecycle. Để hiểu báo cáo, cần đối chiếu:

```text
Default build lifecycle                Site lifecycle
-----------------------                --------------
validate                                pre-site
compile                                 site -> site:site
test                                    post-site
package                                 site-deploy -> site:deploy
verify
install
deploy
```

Một lệnh:

```bash
mvn clean verify
```

đi qua compile/test/package/verify nhưng **không tự động sinh website Site**. Khi muốn site, gọi:

```bash
mvn site
```

Để tránh báo cáo đọc kết quả test chưa có hoặc cũ, quy trình thực hành ưu tiên:

```bash
mvn clean verify site
```

Maven thực hiện clean, phases đến verify và site lifecycle được yêu cầu. Không suy rằng `mvn site` tự làm toàn bộ kiểm thử, vì điều đó còn phụ thuộc các report goals được chọn.

**Cẩn thận với `site:deploy`:** goal này publish website tới `distributionManagement/site`; nó không phải lệnh kiểm tra HTML thuần túy. Site generation khác artifact deploy và khác site deploy.

### 2.2. Chuỗi tạo báo cáo

```text
src/site/markdown/*.md -----------------+
                                        |
POM + dependencies --> Project Info ----+
                                        |
Java source --------> Javadoc ----------+--> Maven Site / Doxia --> target/site/*.html
                                        |
JUnit sources --> Surefire --> TEST-*.xml
                                     |
                            Surefire Report
```

- **Maven Site Plugin** render tài liệu và điều phối output website.
- **Doxia** parse tài liệu nguồn như Markdown, APT, XDoc; Site Renderer cùng skin tạo giao diện.
- **Project Info Reports Plugin** tạo trang mô tả project/dependencies/SCM/licensing tùy `reportSets`.
- **Maven Javadoc Plugin** dùng công cụ `javadoc` của JDK để chuyển comments Java thành HTML.
- **Maven Surefire Plugin** chạy test, ghi XML và text reports.
- **Maven Surefire Report Plugin** đọc XML để dựng report HTML; bản thân nó không phải test runner.

### 2.3. Các đường dẫn cần nhớ

| Đầu ra | Đường dẫn thường gặp |
| --- | --- |
| Surefire XML | `target/surefire-reports/TEST-*.xml` |
| Surefire text report | `target/surefire-reports/*.txt` |
| Surefire HTML khi chạy report goal độc lập | `target/reports/surefire.html` |
| Trang chính website | `target/site/index.html` |
| Project summary | `target/site/summary.html` |
| Dependency report | `target/site/dependencies.html` |
| Javadoc khi chạy trong site | `target/site/apidocs/index.html` |
| Surefire HTML khi chạy trong site | `target/site/surefire.html` |

**Vì sao cùng report plugin có thể xuất ra hai thư mục?** Các reporting goals có parameter `outputDirectory`, nhưng khi chạy bên trong `mvn site`, Site Plugin cung cấp thư mục output dùng chung. Khi gọi một report goal standalone, nó có thể ghi dưới `target/reports`. Đừng debug bằng cách tra nhầm đường dẫn từ một loại invocation khác.

## 3. Ghim version plugin để build có thể tái lập

### 3.1. Plugin version không phải dependency version

Maven có:
- Project dependencies trong `<dependencies>`, ví dụ JUnit Jupiter.
- Build plugins trong `<build><plugins>`, ví dụ Compiler/Surefire/Site.
- Reporting plugins trong `<reporting><plugins>`, ví dụ Javadoc/Project Info/Surefire Report.

Ba nhóm này có trách nhiệm khác nhau. Nếu bạn thêm `maven-javadoc-plugin` làm dependency thông thường, Maven không hiểu rằng cần tạo Javadoc trong `mvn site`.

Apache Maven khuyến nghị **khai báo version cho từng plugin** để bảo đảm reproducibility. Tránh:

```xml
<version>LATEST</version>
```

hoặc không đặt version rồi mong environment luôn chọn cùng một binary. Dùng một version cụ thể đã kiểm thử tương thích:

```xml
<version>3.22.0</version>
```

Một chính sách plugin version tốt gồm: ghim version, ghi mục đích, kiểm system requirements của Maven/JDK, nâng có chủ đích, đối chiếu output trong CI và có khả năng quay về bộ version trước khi regression.

### 3.2. Cấu hình Site Plugin trong build/plugins

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-site-plugin</artifactId>
            <version>3.22.0</version>
        </plugin>
    </plugins>
</build>
```

Đây là **POM fragment**. Site Plugin là công cụ tạo site nên khai báo build plugin version tường minh. `site:site` được gọi qua site lifecycle/CLI chứ không cần gắn vào phase `verify`. Nếu gắn site goal vào default lifecycle, mỗi lần build sản phẩm có thể phát sinh chi phí tạo HTML ngoài ý muốn.

### 3.3. Reporting plugins được khai báo riêng

```xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-project-info-reports-plugin</artifactId>
            <version>3.9.0</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.12.0</version>
        </plugin>
    </plugins>
</reporting>
```

Fragment này chỉ minh họa vị trí. Chúng ta sẽ giới hạn report goals cụ thể trong `reportSets` ở POM đầy đủ, thay vì để plugin cung cấp tất cả reports mặc định.

**Plugin Javadoc có thể được khai báo cả dưới `build` lẫn `reporting`.** Hai nơi này có cấu hình/đường thực thi riêng: `mvn javadoc:javadoc` trực tiếp khác `mvn site` trong việc áp dụng reporting configuration. Khi debug, xác định bạn đang chạy dạng nào.

### 3.4. pluginManagement có đủ chưa?

`<build><pluginManagement>` của một parent POM có thể ghim versions/configuration mà modules con kế thừa khi plugin được kích hoạt. Nhưng bản thân pluginManagement **không bảo đảm site hay report goal được thực thi**.

Với site output, hãy đảm bảo:
- Site Plugin hiện diện/được quản lý đúng version cho invocation thực tế.
- Reporting plugins nằm trong cấu hình `<reporting><plugins>` hiệu lực.
- `reportSets` có report goal bắt buộc.
- Parent/inheritance/profiles không ghi đè phiên bản hoặc làm mất reportSets.

Dùng `mvn help:effective-pom` để kiểm hiệu quả cuối cùng; đừng chỉ đọc một file POM nguồn và suy ra toàn bộ kết quả của inheritance.

### 3.5. Vì sao Site, Doxia và Skin cũng cần được xem là một stack?

Maven Site Plugin dùng:
- Doxia parser chuyển Markdown/APT/XDoc sang biểu diễn nội bộ.
- Doxia Sitetools/renderer dựng HTML, menus và theme.
- Maven Reporting Executor điều phối report goals.
- Maven skin, plugin classes và report formatters.

Một site plugin mới đi kèm stack Doxia/Reporting mới có thể không tương thích với reporting plugin hoặc custom skin rất cũ. Khi gặp `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi skin parse, nguyên nhân có thể ở **plugin compatibility** chứ không phải Java source.

Site Plugin **3.22.0** thuộc dòng ổn định 3.x trong bộ ví dụ. Các mốc `4.0.0-M*` không nên được copy như bản phát hành production chỉ vì major version lớn hơn. Khi nâng major, đọc migration guide và test lại từng report/skin.

## 4. Chọn reportSets để tránh báo cáo dư hoặc thiếu

### 4.1. Project Info: Summary và Dependencies

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-project-info-reports-plugin</artifactId>
    <version>3.9.0</version>
    <reportSets>
        <reportSet>
            <reports>
                <report>summary</report>
                <report>dependencies</report>
            </reports>
        </reportSet>
    </reportSets>
</plugin>
```

Các goal `summary` và `dependencies` cho ra trang tương ứng. Không nên chấp nhận một “Project Reports” menu có nhiều trang trống vì thiếu metadata SCM/issue tracker hoặc team details. Chỉ chọn đúng báo cáo team thực sự cần.

### 4.2. Javadoc report thay vì mọi goal Javadoc

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

`javadoc` là non-aggregate report của project. Khi có reactor nhiều module, Javadoc Plugin có những aggregate goals, test-javadoc hoặc khác; chỉ thêm chúng khi có nhu cầu và hiểu việc kế thừa reportSets. Một lựa chọn reportSet quá rộng có thể dẫn đến report bị chạy nhiều lần và output trùng.

### 4.3. Surefire Report: report so với report-only

`surefire-report:report` **có thể kích hoạt phase test** trước khi dựng HTML. `surefire-report:report-only` **không chạy tests**, chỉ phân tích `TEST-*.xml` có sẵn. Trong pipeline đã có `mvn verify`, dùng `report-only` giúp tránh test được thực thi lại vì report goal.

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
    <configuration>
        <alwaysGenerateSurefireReport>false</alwaysGenerateSurefireReport>
    </configuration>
</plugin>
```

`alwaysGenerateSurefireReport=false` tránh tự tạo báo cáo nếu không có XML theo cơ chế plugin. Nhưng đó **không phải hard failure gate** khi XML thiếu: báo cáo có thể đơn giản không sinh. Vì vậy **CI bắt buộc kiểm `TEST-*.xml`, test counts và file HTML**.

Một nhầm lẫn thường gặp:
- `mvn clean site` xóa XML rồi chạy site. Với `report-only`, nó không tự tạo lại XML.
- `mvn clean verify site` chạy tests trước site. XML có và HTML có dữ liệu.

### 4.4. excludeDefaults và quyền kiểm soát đầu ra

Trong `<reporting>` có thể dùng:

```xml
<excludeDefaults>true</excludeDefaults>
```

để kiểm soát những default reports thay vì để Site thêm những trang không được chọn. Nhưng đừng quên `<reportSets>` cho từng plugin: nếu không, reporting plugin vẫn có thể tạo nhiều report goals khả dụng theo mặc định.

Đặt yêu cầu kiểm chứng trong CI: những trang có trong `reportSets` phải tồn tại, không rỗng và chứa nội dung hợp lệ. Không chỉ chấp nhận `index.html` làm đại diện cho cả bộ report.

## 5. Các đầu vào trước khi tạo báo cáo

### 5.1. Project Info cần POM và dependency resolution

`summary` chủ yếu dùng metadata từ POM: name, description, version và những field có sẵn. `dependencies` dùng dependency graph, có thể cần Maven resolve artifacts từ local/remote repository. Nếu `mvn site` fail do repository timeout hoặc parent POM không tải được, không nên sửa `reportSets` một cách ngẫu nhiên.

POM có thể thiếu SCM/license/issue metadata khi project chưa khai báo; đó là vấn đề **chất lượng dữ liệu**, không phải nhất thiết là plugin lỗi. Không bịa URL/owner hoặc license chỉ để trang HTML đầy đủ.

### 5.2. Javadoc cần source và JDK phù hợp

Maven Javadoc Plugin gọi công cụ `javadoc` của JDK:
- Java source phải tồn tại trong `src/main/java` hoặc source roots mà build đã cấu hình.
- Những types được tham chiếu phải có trong classpath.
- Comments phải có `@param`, `@return` và `{@link ...}` hợp lệ.
- Encoding của source/report nên là UTF-8 khi có tiếng Việt.
- Nếu dùng generated sources, cần chạy goal tạo source trước Javadoc.

Javadoc có thể FAIL dù compiler PASS vì Java compiler bỏ qua nhiều lỗi *cú pháp documentation* trong comments, còn javadoc/doclint kiểm tra chúng. Không “chữa” bằng cách tắt mọi `failOnError` hoặc `doclint` chỉ để CI xanh.

### 5.3. Surefire XML là dữ liệu, không phải hình thức

Surefire Plugin chạy tests trong phase `test`, thường sinh `target/surefire-reports/TEST-*.xml`. HTML report chỉ **trình bày lại** dữ liệu này.

| Triệu chứng | Nguyên nhân có thể |
| --- | --- |
| Không có XML | Tests chưa chạy, bị skip, class không match pattern/provider |
| XML có nhưng HTML không | Reporting plugin/reportSet chưa chạy, output path sai |
| HTML có nhưng 0 tests | XML rỗng, stale, plugin bỏ qua hoặc không có test |
| HTML từ commit khác | Reuse `target`/cache/report từ run cũ |
| XML có tests failed | Test runner đã ghi failure, website có thể trình bày failure nhưng không làm build pass |

**Không được đồng nhất “report đã render” với “tests đã pass”.** Test goal exit status và test counts mới là bằng chứng kết quả test; report HTML là công cụ quan sát.

### 5.4. Báo cáo khác có dữ liệu riêng

- **Failsafe report:** Failsafe Plugin cần chạy IT ở `integration-test/verify` và ghi XML trong `target/failsafe-reports`. Surefire Report Plugin có `failsafe-report-only` chỉ render dữ liệu, không chạy IT.
- **JaCoCo report:** cần execution data của test run và cấu hình agent/report goals; HTML không có coverage khi chưa có dữ liệu.
- **Checkstyle/PMD:** cần source + ruleset; report goal không đồng nghĩa enforcement goal đã fail build khi có vi phạm.
- **Changelog/SCM:** cần SCM metadata, có thể cần Git history/network. CI shallow checkout/offline có thể thiếu dữ liệu.
- **JXR:** cần source cross-reference; muốn liên kết test failure tới dòng source cần cấu hình tương ứng.

Những plugin này có thể có output directory, lifecycle prerequisite và aggregate behavior khác nhau. Với mỗi report, xác định **input, producer, output và acceptance check** trước khi ghim vào CI.

## 6. Project Java 17 hoàn chỉnh: Markdown, Javadoc, Summary, Dependencies, Surefire

Project mẫu không dùng Spring Boot, Docker, database hoặc dịch vụ ngoài; JUnit tests chỉ kiểm chuỗi nên xác định được kết quả chính xác.

### 6.1. Cây thư mục

```text
maven-site-report-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/docs/GreetingService.java
    ├── test/
    │   └── java/com/example/docs/GreetingServiceTest.java
    └── site/
        └── markdown/index.md
```

Không cần `src/site/site.xml` ở ví dụ tối thiểu; plugin có default site descriptor. `index.md` được render thành `target/site/index.html`. Với giao diện/menu tùy chỉnh, có thể thêm `site.xml` sau khi baseline hoạt động.

### 6.2. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-site-report-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Maven Site Report Lab</name>
    <description>Thực hành cố định plugin tạo tài liệu và kiểm tra báo cáo.</description>

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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-site-plugin</artifactId>
                <version>3.22.0</version>
            </plugin>
        </plugins>
    </build>

    <reporting>
        <excludeDefaults>true</excludeDefaults>
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
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>

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
                <configuration>
                    <alwaysGenerateSurefireReport>false</alwaysGenerateSurefireReport>
                </configuration>
            </plugin>
        </plugins>
    </reporting>
</project>
```

**Đối chiếu cấu hình:**

1. Không có parent phức tạp, là Java JAR project Maven chuẩn.
2. Java compiler đặt `release=17`; các nguồn và report dùng UTF-8.
3. JUnit Jupiter được khai báo `test`; code chính không phụ thuộc test libraries.
4. `maven-surefire-plugin:3.6.1` chạy hai tests và tạo XML.
5. `maven-site-plugin:3.22.0` được pin trong build plugins.
6. `maven-project-info-reports-plugin:3.9.0` xuất đúng Summary/Dependencies.
7. `maven-javadoc-plugin:3.12.0` xuất Javadoc, không bật aggregate/test-javadoc.
8. `maven-surefire-report-plugin:3.6.1` dùng `report-only` nên không tự chạy lại tests.
9. Không có `generateReports=false` ở Site Plugin; reporting được bật.
10. Không có upload/deploy URL nên `mvn site` chỉ xuất file địa phương; `site:deploy` chưa được cấu hình.
11. Giữ `<reporting><excludeDefaults>true</excludeDefaults>` để chỉ tập trung vào những reports được chọn.
12. Không khai `maven-javadoc-plugin` trong `build/plugins` vì ví dụ chỉ dùng nó như Site report.

### 6.3. `src/main/java/com/example/docs/GreetingService.java`

```java
package com.example.docs;

/**
 * Provides deterministic greeting messages.
 *
 * <p>The output is independent of network services, locale and time.
 *
 * @since 1.0.0
 */
public final class GreetingService {

    private GreetingService() {
    }

    /**
     * Creates a normalized greeting.
     *
     * @param name a caller-supplied name, possibly blank
     * @return a greeting for the given name or a default guest
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            return "Xin chào, bạn!";
        }
        return "Xin chào, " + name.strip() + "!";
    }

    /**
     * Runs a sample greeting.
     *
     * @param args ignored command-line arguments
     */
    public static void main(String[] args) {
        System.out.println(greet("  Maven  "));
    }
}
```

File này có Javadoc cho class và public methods. JDK 17 có `String.isBlank()` và `String.strip()`. Câu `@return`, `@param` khớp Java method signatures. Những comments này là **đầu vào thật** cho Javadoc Plugin.

### 6.4. `src/test/java/com/example/docs/GreetingServiceTest.java`

```java
package com.example.docs;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

final class GreetingServiceTest {

    @Test
    void trimsName() {
        assertEquals(
                "Xin chào, Maven!",
                GreetingService.greet("  Maven  "));
    }

    @Test
    void usesGuestForBlankName() {
        assertEquals(
                "Xin chào, bạn!",
                GreetingService.greet("   "));
    }
}
```

Đây là **2 JUnit Jupiter test methods**, cùng nằm trong class kết thúc bằng `Test` nên Surefire phát hiện theo naming conventions. Khi code đúng, 2 tests PASS, không có failures/errors/skips. Nếu log báo `Tests run: 0`, đó là dấu hiệu sai cấu hình test discovery/skip, không phải mặc nhiên đạt chất lượng.

### 6.5. `src/site/markdown/index.md`

```markdown
# Maven Site Report Lab

Đây là website tài liệu cho dự án Java 17.

## Mục tiêu

- Cố định phiên bản Site Plugin và các reporting plugins.
- Tạo Javadoc API cho GreetingService.
- Tạo Project Summary và Dependencies.
- Dựng Surefire HTML từ XML của hai JUnit tests.

## Quy trình

Từ thư mục dự án:

    mvn clean verify site

Kết quả website ở target/site.
Kiểm XML trong target/surefire-reports trước khi đánh giá Surefire HTML.
```

Maven Site Plugin nhận Markdown dưới `src/site/markdown`; `index.md` là trang nguồn chính. Nếu đặt file vào `src/main/resources`, đó là vùng resources của ứng dụng, không phải thư mục site mặc định.

### 6.6. Toàn bộ các tệp đã đủ để chạy chưa?

Có: `pom.xml`, `GreetingService.java`, `GreetingServiceTest.java`, `index.md`. Không yêu cầu `site.xml`, API endpoint, external database, Docker hoặc plugin snapshot. JDK 17+, Maven 3.9.x và khả năng resolve các artifacts lần đầu là các yêu cầu môi trường.

Project này **không khai Main-Class trong manifest của JAR**, vì mục đích chính là tài liệu. Để chạy chương trình dùng `java -cp`, không dùng `java -jar` rồi chẩn đoán nhầm rằng plugin site đã lỗi.

## 7. Chạy site và kiểm tra kết quả

### 7.1. Kiểm tra môi trường

```bash
mvn -version
java -version
javac -version
```

`mvn -version` nói Maven đang dùng JDK nào. Nếu PATH Java khác JAVA_HOME Maven, `java -version` và `mvn -version` có thể không trùng; hãy dùng một toolchain phù hợp trước khi debug Javadoc. Plugin có thể không tải được khi CI proxy/offline chưa cache đủ.

### 7.2. Build và sinh report theo thứ tự đúng

```bash
mvn -B -ntp clean verify site
```

Ý nghĩa:
- `-B`: batch mode phù hợp CI.
- `-ntp`: bớt progress tải artifact.
- `clean`: xóa `target` cũ để không nhận report stale.
- `verify`: biên dịch Java, chạy **2 JUnit tests**, tạo `TEST-*.xml`.
- `site`: chạy Maven Site Plugin và reportSets đã cấu hình.
- `report-only`: đọc XML vừa tạo, không tự gọi test lại.

Kết quả mong đợi được **tóm tắt**, không phải Maven stdout nguyên văn:

```text
Surefire: Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
Site: generated documentation and reports under target/site
BUILD SUCCESS
```

Tên plugin logger, thời gian, số tài nguyên CSS và các dòng log phụ thuộc Maven/JDK. Dòng "Site: generated..." trên là mô tả kết quả, không phải câu Maven bắt buộc in đúng từng chữ.

### 7.3. Tệp đầu ra cần xác minh

```text
target/
├── surefire-reports/
│   ├── TEST-com.example.docs.GreetingServiceTest.xml
│   └── com.example.docs.GreetingServiceTest.txt
└── site/
    ├── index.html
    ├── summary.html
    ├── dependencies.html
    ├── surefire.html
    └── apidocs/
        └── index.html
```

Các báo cáo Java API còn nhiều HTML/CSS/JS files. Danh sách chỉ nêu những output được kiểm trong tutorial.

Linux/macOS:

```bash
test -s target/site/index.html
test -s target/site/summary.html
test -s target/site/dependencies.html
test -s target/site/surefire.html
test -s target/site/apidocs/index.html
test -s target/surefire-reports/TEST-com.example.docs.GreetingServiceTest.xml
```

`test -s` thành công nếu file tồn tại **và không rỗng**. Khi đưa vào Bash CI, bật `set -e` hoặc xử lý exit code của mỗi lệnh; đừng chạy nhiều lệnh thủ công rồi chỉ nhìn exit code của dòng cuối.

Windows PowerShell:

```powershell
$files = @(
  "target/site/index.html",
  "target/site/summary.html",
  "target/site/dependencies.html",
  "target/site/surefire.html",
  "target/site/apidocs/index.html",
  "target/surefire-reports/TEST-com.example.docs.GreetingServiceTest.xml"
)
foreach ($file in $files) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
    throw "Missing report: $file"
  }
  if ((Get-Item -LiteralPath $file).Length -le 0) {
    throw "Empty report: $file"
  }
}
Write-Output "REPORT_FILES_OK"
```

Khi mọi file bắt buộc tồn tại và không rỗng, script in chính xác:

```text
REPORT_FILES_OK
```

Lệnh này mới kiểm **file existence/size**, chưa kiểm số test hay nội dung HTML.

### 7.4. Kiểm XML trước HTML

Trong `TEST-com.example.docs.GreetingServiceTest.xml`, cần kiểm metadata tổng hợp tương đương:

```xml
<testsuite name="com.example.docs.GreetingServiceTest"
           tests="2" failures="0" errors="0" skipped="0">
    <!-- Generated testcase elements and properties -->
</testsuite>
```

Đây là **đoạn minh họa**, không phải toàn bộ XML file do Surefire phát hành: file thật có thể có timestamp, hostname, time, properties và nhiều attributes khác. Với code nguyên vẹn, cần xác nhận:
- tests bằng 2;
- failures/errors/skipped bằng 0;
- có test cases cho `trimsName`, `usesGuestForBlankName`.

Không nên parse XML tổng quát bằng regex nếu CI tính tổng nhiều suite; dùng XML parser có namespace/attribute handling đúng. Nhiều module có nhiều XML, cần cộng count của **mọi suite cần kiểm**, không chỉ file đầu tiên.

### 7.5. Xem báo cáo HTML

Mở `target/site/index.html` bằng trình duyệt hoặc static file server của môi trường được phép. Quan sát:
- Markdown hiển thị tiếng Việt đúng dấu;
- navigation có hoặc trỏ tới `summary.html`/`dependencies.html`/`surefire.html`;
- Javadoc chứa class `GreetingService` và method `greet(String)`;
- Surefire HTML có hai methods và không báo “no tests”;
- không có link broken, skin lỗi CSS, hình ảnh missing;
- báo cáo thuộc đúng project/version/commit hiện tại.

**Maven SITE BUILD SUCCESS chưa bảo đảm semantic QA.** Một page có HTML/CSS đầy đủ nhưng không có số test cũng có thể là output kỹ thuật hợp lệ, nên CI phải quy định gì là báo cáo được chấp nhận.

### 7.6. Chạy Java code thật

```bash
java -cp target/classes com.example.docs.GreetingService
```

Stdout chính xác của chương trình:

```text
Xin chào, Maven!
```

Đây là stdout ứng dụng, không phải output plugin. Nếu cố gọi `java -jar target/maven-site-report-lab-1.0.0.jar`, JVM có thể báo thiếu main manifest vì ví dụ không cấu hình entry point trong manifest.

## 8. Thí nghiệm lỗi A: không có XML khi dùng report-only

Từ một checkout sạch:

```bash
mvn clean site
```

Lệnh này xóa `target`, rồi yêu cầu site generation **mà không chạy build test lifecycle trước**. Với `report-only`, plugin **không tự tạo TEST-*.xml**. Với `alwaysGenerateSurefireReport=false`, trang Surefire có thể không được sinh.

Cách điều tra:
1. Xác nhận `target/surefire-reports/TEST-*.xml` **không có**.
2. Kiểm log của Surefire test goal: có chạy `surefire:test` không?
3. Kiểm `<report>report-only</report>` trong effective POM.
4. Chạy lại `mvn clean verify site`.
5. Kiểm XML có 2 tests, HTML đã xuất, rồi xem trang.

**Không giải quyết bằng cách bật `alwaysGenerateSurefireReport=true` chỉ để có một trang rỗng.** Mục đích báo cáo test là thể hiện dữ liệu test thật.

Nếu project đã có XML từ lần trước mà `mvn site` cho HTML, hãy coi đó là **render từ dữ liệu hiện có**; không thể suy rằng tests vừa được chạy lại.

## 9. Thí nghiệm lỗi B: Java compile PASS nhưng Javadoc FAIL

Java compiler có thể bỏ qua link trong Javadoc comment, còn công cụ `javadoc` phải resolve nó.

Trong `GreetingService.java`, tạm thay **chỉ dòng mô tả comment** của `greet`:

```java
/**
 * Creates a greeting with {@link MissingGreetingType}.
 *
 * @param name a caller-supplied name
 * @return a greeting for the given name
 */
```

**Không thay chữ ký hay phần thân method.** Đây là fragment Javadoc, không phải Java program độc lập. Khi chạy:

```bash
mvn clean verify site
```

Code vẫn có thể compile và test PASS, nhưng bước Javadoc có thể FAIL với lỗi tham chiếu không resolve, dạng:

```text
reference not found: MissingGreetingType
```

Thông báo là **dạng minh họa**, không cam kết nguyên văn ở mọi JDK/version. Cách sửa: khôi phục comment đúng hoặc dùng link tới class thật sự tồn tại. Không tự ý đặt `<failOnError>false</failOnError>` hoặc tắt toàn bộ `doclint` để che lỗi API docs cho bản phát hành.

Nếu Javadoc fail chỉ ở CI, kiểm JDK, toolchain, generated source roots và dependencies trước khi kết luận source comment sai.

## 10. Thí nghiệm lỗi C: site thành công nhưng thiếu một trang bắt buộc

Trong `maven-project-info-reports-plugin` reportSet, tạm bỏ:

```xml
<report>dependencies</report>
```

rồi chạy:

```bash
mvn clean verify site
```

Site có thể vẫn xuất `index.html`, `summary.html`, Javadoc và Surefire. Tuy nhiên `dependencies.html` **không còn được yêu cầu từ reportSet**, nên bước kiểm file bắt buộc của CI sẽ FAIL.

Bài học: **Site Plugin không biết doanh nghiệp bắt buộc phải có trang nào**. ReportSets là cấu hình dự định, nhưng pipeline cần kiểm output thực tế. Sau thí nghiệm, khôi phục `dependencies` trong reportSet.

## 11. Phân loại lỗi theo tầng để sửa đúng nguyên nhân

### 11.1. Lỗi plugin resolution / repository

Triệu chứng:
- `PluginResolutionException` hoặc `Could not find artifact ...maven-site-plugin...`;
- HTTP 401/403/429, timeout, proxy, TLS/certificate;
- Plugin version không tồn tại trong repository được phép.

Cách xử lý:
1. Xem tọa độ + version plugin trong POM và log.
2. Xem `mvn -version`, `settings.xml`, mirrors, proxy, quyền truy cập.
3. Kiểm repository/mirror có artifacts đó không.
4. Nếu môi trường offline, plugin và transitive plugin dependencies phải được cached từ trước.
5. `-U` chỉ phù hợp với chính sách cập nhật SNAPSHOT/metadata; **nó không chữa mọi lỗi 403/429 hoặc artifact không tồn tại**.
6. Đừng xóa toàn bộ `~/.m2` ngay: việc đó có thể xóa những artifacts CI offline đang cần.

Khi Maven còn chưa tải plugin, lỗi **không liên quan Javadoc syntax hoặc số test**. Đừng sửa source trước khi xác nhận plugin goal có khởi chạy.

### 11.2. Lỗi Doxia, Maven Reporting API và skin

Triệu chứng:
- `NoSuchMethodError`, `ClassNotFoundException` khi render;
- plugin realm/loader không tương thích;
- parser không nhận diện Markdown extension;
- skin cũ làm layout/menu lỗi;
- site plugin mới nhưng report plugin rất cũ.

Cách xử lý:
1. Xem plugin nào ở dòng lỗi, không dựa vào tên bước cuối cùng.
2. Ghim Site Plugin và mọi reporting plugin; với custom skin cũng ghim version.
3. Xem system requirements và migration notes đúng version/major.
4. So sánh với bộ version đã chạy PASS; nâng từng plugin để cô lập regression.
5. Nếu dùng custom Doxia parser, xác định parser dependency tương thích với Doxia của Site Plugin.
6. Không thêm các dependency `doxia-core` hay `maven-reporting-api` override tùy tiện để ép ClassLoader nếu chưa có bằng chứng.

Maven Site Plugin 3.22.0 dùng stack mới hơn các hướng dẫn Site Plugin 2.x trên internet. Các POM có version `2.1.1` của Project Info Reports chỉ là ví dụ lịch sử; cần xem docs hiện hành và cố định bộ version thực tế.

### 11.3. Lỗi test input và report-only

Triệu chứng: thiếu `surefire.html` hoặc HTML có 0 tests.

Kiểm theo thứ tự:
- `mvn test` hoặc `mvn verify` đã chạy chưa?
- `-DskipTests`, `-Dmaven.test.skip=true` hoặc selector có làm test không thực thi không?
- Test class name có match `*Test`, `Test*` theo conventions?
- JUnit Jupiter engine/provider có mặt không?
- `target/surefire-reports/TEST-*.xml` có không và timestamp đúng?
- Maven Surefire Report Plugin có reportSet `report-only` không?
- Site Plugin có `generateReports=false` hay profile tắt report không?
- CI có đang tìm trong `target/reports` thay vì `target/site` không?

**File `surefire.html` tồn tại nhưng 0 tests không phải điều kiện PASS khi policy yêu cầu chạy test.**

### 11.4. Lỗi source/Javadoc/doclint

Triệu chứng: `unknown tag`, `reference not found`, malformed HTML trong Javadoc, `@param` sai, JDK tool không tìm được, encoding lỗi.

Cách xử lý:
- Sửa source comment theo line Javadoc báo.
- Xác minh `@param`/`@return` và class type references.
- Kiểm UTF-8 của source, `project.build.sourceEncoding` và `project.reporting.outputEncoding`.
- Kiểm `mvn -version` và `javac -version`, Javadoc tool thực tế.
- Với generated sources, sinh source trước khi gọi Javadoc.
- Giữ policy doclint rõ ràng; chỉ relax khi có quyết định chất lượng chính thức.

### 11.5. Lỗi reportSets/paths

Triệu chứng: HTML tạo ở `target/reports` nhưng site menu không có report; hoặc report thiếu vì reportSet không chọn goal.

Cách xử lý:
- Đọc `<reporting>` và effective POM, không chỉ `<build>`.
- Kiểm `<reportSets><report>...` đúng tên report goal.
- Kiểm `<excludeDefaults>`, inheritance và active profiles.
- Xác nhận invocation `mvn site` hay goal standalone.
- Kiểm Site Plugin `generateReports` và outputDirectory.
- Xem HTML thật trong `target/site`, menu chỉ là một lớp navigation.

### 11.6. Lỗi dữ liệu stale

Triệu chứng: HTML chứa thông tin một branch khác, test count khác source hiện tại, site có dữ liệu dù lệnh chỉ chạy `site`.

Cách xử lý:
- Chạy `mvn clean verify site` trên đúng commit.
- Không dùng `target/site` hoặc `target/surefire-reports` cached như chứng cứ run mới.
- Khi CI jobs chia nhau build/test/report, dùng artifacts có version/SHA metadata.
- Kiểm timestamp và XML test counts trước khi publish.
- Cache `.m2` có thể giúp download, nhưng cần kiểm version consistency; đừng coi cache là báo cáo mới.

## 12. Direct goal và site report khác nhau thế nào?

### 12.1. Surefire Report Plugin

Gọi standalone goal `report`:

```bash
mvn org.apache.maven.plugins:maven-surefire-report-plugin:3.6.1:report
```

Goal này có thể thực thi test lifecycle trước khi render; không nên dùng nếu bạn chỉ muốn chuyển một XML đã có thành HTML.

Chỉ render XML:

```bash
mvn org.apache.maven.plugins:maven-surefire-report-plugin:3.6.1:report-only
```

Khi gọi độc lập, HTML thường xuất ở:

```text
target/reports/surefire.html
```

Khi chạy thông qua `mvn site`:

```text
target/site/surefire.html
```

Vì vậy cần **đọc log xác định goal và output path**; không chỉ hỏi “file surefire.html ở đâu?” mà thiếu loại invocation.

### 12.2. Javadoc Plugin

`mvn javadoc:javadoc` gọi goal trực tiếp với configuration có thể lấy từ build plugin setup; còn Javadoc report trong `mvn site` lấy reporting configuration. Output path và report menu có thể khác. Đừng giả định thêm Javadoc plugin vào `build/plugins` đồng nghĩa Site luôn có API docs.

### 12.3. Project Info Reports Plugin

Một report goal như `project-info-reports:dependencies` được gọi trực tiếp có thể tạo output độc lập. Nhưng khi được chọn trong `reporting/reportSets`, nó tham gia Site Plugin output và menu. Các tham số outputDirectory của reporting plugins không nhất thiết quyết định Site output root khi Site điều phối.

## 13. Site descriptor, Markdown, menu và tiếng Việt

### 13.1. Nguồn site nằm dưới src/site

Maven Site Plugin hỗ trợ Markdown (cũng như APT, FML, XDoc và các định dạng có parser phù hợp). Cấu trúc phổ biến:

```text
src/site/
├── markdown/
│   ├── index.md
│   └── guide.md
└── site.xml
```

`site.xml` tùy chọn, dùng cho menu/navigation/skin. `src/site/markdown/index.md` render thành `target/site/index.html`; không đặt Markdown vào `src/main/resources` để chờ Site tự lấy.

### 13.2. Menu Project Reports

Nếu cần custom menu, một **fragment body** của descriptor:

```xml
<body>
    <menu name="Hướng dẫn">
        <item name="Tổng quan" href="index.html"/>
    </menu>
    <menu ref="reports"/>
</body>
```

Đây **không phải site.xml đầy đủ**: file thực cần root `<project>` và schema/namespace của Site Decoration Model phù hợp version. Không copy fragment này thành file hoàn chỉnh. Dùng documentation Site Plugin đúng version để viết descriptor; sau đó chạy `mvn site` và xem links.

Nếu `summary.html` có nhưng menu không link tới nó, lỗi có thể ở descriptor/skin, **không phải report generation**.

### 13.3. Doxia và Markdown extensions

Markdown renderer của GitHub không đồng nghĩa Doxia hiểu mọi extension giống hệt. Nếu tài liệu dùng Mermaid, custom parser hoặc một DSL riêng, kiểm Site Plugin/Doxia docs và dependencies phù hợp. Không tự ghi vào site config một extension không có trong phiên bản đang dùng.

### 13.4. Encoding tiếng Việt

Dùng UTF-8 cho:
- Java source/Javadoc comments;
- Markdown source `src/site/markdown`;
- `project.build.sourceEncoding`;
- `project.reporting.outputEncoding`;
- output HTML/skin.

Các label của reporting plugins có thể chưa dịch đủ sang tiếng Việt dù source dùng UTF-8; đó là vấn đề localization resources, không nhất thiết là mất encoding. Kiểm trực tiếp HTML với ký tự `Xin chào, Maven!` để phân biệt.

## 14. Multi-module: tránh báo cáo tổng hợp bị trùng

Giả sử:

```text
root/ (packaging=pom)
├── api/
├── service/
└── cli/
```

Trong reactor, mỗi module có thể tạo site riêng. Không phải module nào cũng có tests hoặc Java source:
- Parent aggregator có thể không có `TEST-*.xml`.
- Một module chỉ có POM có thể không có Javadoc.
- Một report aggregate có thể tổng hợp nhiều modules và cần đặt ở root.
- Local `target/site` của các modules không có layout links giống website được publish.

Nếu muốn Javadoc aggregate, có thể cấu hình reportSets trong parent/aggregator, ví dụ:

```xml
<reportSets>
    <reportSet>
        <id>module-javadoc</id>
        <reports>
            <report>javadoc</report>
        </reports>
    </reportSet>
    <reportSet>
        <id>root-aggregate</id>
        <inherited>false</inherited>
        <reports>
            <report>aggregate</report>
        </reports>
    </reportSet>
</reportSets>
```

Đây là **fragment nâng cao**, không có trong POM mẫu một module. `inherited=false` trên aggregate reportSet giúp không tạo lại aggregate reports ở từng child. Phải kiểm reactor/project structure và phiên bản Javadoc plugin khi áp dụng.

Để kiểm module links theo layout gần site đã publish, Maven Site Plugin có `site:stage` sau khi site đã tạo, thường cần `distributionManagement/site` URL phù hợp. **Không gọi site:deploy chỉ để kiểm link**.

## 15. CI: yêu cầu đầu ra tài liệu như một quality gate

### 15.1. Lệnh chuẩn

Một CI job dựng tài liệu nên bắt đầu từ checkout sạch và chạy:

```bash
mvn -B -ntp clean verify site
```

Sau đó kiểm:
1. Maven exit code là 0.
2. Surefire XML cho đúng commit có **2 tests, 0 failures/errors/skipped**.
3. `target/site/index.html` có nội dung Markdown.
4. `summary.html` và `dependencies.html` có dữ liệu POM/dependency.
5. `apidocs/index.html` có class/method API cần thiết.
6. `surefire.html` hiển thị kết quả test hiện tại.
7. Không có broken internal links, lỗi layout/encoding hoặc báo cáo “no tests”.

Nếu CI không cho chạy UI visual check mỗi lần, ít nhất có file checks, XML parsing và periodic review/screenshot cho thay đổi plugin/skin. **Không tự báo all reports passed chỉ vì Maven SITE step exit 0.**

### 15.2. Test failures và xuất báo cáo khi lỗi

Khi unit tests fail, `mvn verify` thường trả mã lỗi và pipeline dừng trước site generation. Nếu team muốn thu HTML để debug test failures, có thể cấu hình job/artifact collection sau failure hoặc một stage riêng đọc XML còn tồn tại. Nhưng job chính **vẫn phải FAIL**; không dùng `-DskipTests` hoặc `maven.test.skip` chỉ để render HTML rồi gọi đó là successful build.

Nếu báo cáo từ test thất bại được render trong stage khác, ghi rõ status `FAILED`, source commit, test counts và thời điểm. Không trộn chúng với báo cáo từ run thành công trước.

### 15.3. CI artifact vs site deploy

- `target/site` là local output có thể upload làm CI artifact.
- `site:deploy` là publish website, cần URL và quyền riêng.
- `mvn deploy` publish JAR/POM vào Maven artifact repository, không phải publish website.

Không tự đưa credentials production vào job thử tạo site. Khi phát hành website công khai, kiểm tài liệu không chứa secrets, internal URLs hoặc log có thông tin nhạy cảm.

### 15.4. Build reproducibility và thay đổi version

Khi nâng plugin:
- đọc release notes và minimum Maven/JDK;
- kiểm `help:effective-pom` sau inheritance;
- pin versions của plugin/skin;
- clean build;
- kiểm file paths/HTML/test data;
- giữ một baseline trước upgrade để so diff nếu output thay đổi;
- ghi lại CI runner image và Java version.

`<version>` tường minh giúp **lặp lại bộ binary được chọn**, nhưng chưa bảo đảm report có cùng thời gian tạo, SCM branch hoặc dependencies trong một snapshot mutable. Reproducibility còn cần quản trị input data và environment.

## 16. Bảng lỗi hay gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `mvn verify` PASS, không có target/site | Chưa chạy site lifecycle | `mvn clean verify site` |
| `mvn clean site` thiếu Surefire | report-only không chạy tests | Chạy verify trước site |
| Surefire HTML ghi 0 tests | XML thiếu/rỗng, test bị skip | Kiểm test counts trong XML và Surefire log |
| Site HTML có nhưng thiếu Dependencies | Không chọn report trong reportSets | Thêm `dependencies`, kiểm file |
| Javadoc FAIL, Java compile PASS | Invalid Javadoc links/tags/doclint | Sửa comment, kiểm Javadoc error line |
| Javadoc không xuất hiện | Reporting plugin không có hoặc no sources | Kiểm `reporting`, source roots, reportSet |
| `PluginResolutionException` | Plugin version/repo/mirror/quota | Kiểm versions/settings/network |
| `NoSuchMethodError` trong Doxia | Plugin/renderer/reporting stack mismatch | Pin compatibility, đọc migration |
| Skin làm menu/CSS lỗi | Skin không tương thích | Thử default skin, pin version |
| HTML tiếng Việt lỗi font/dấu | Source/report encoding hoặc skin | Giữ UTF-8 và xem HTML |
| `target/reports/surefire.html` có, target/site thiếu | Gọi report standalone | Chạy site hoặc kiểm đúng output |
| Report plugin ở build/plugins nhưng Site không có trang | Thiếu reporting/plugins | Đặt report plugin/reportSet đúng |
| pluginManagement có version nhưng không tạo report | Chưa kích hoạt reporting | Cấu hình reporting/execution |
| Site Plugin generateReports=false | Cấu hình cố ý tắt report | Bỏ/điều chỉnh option |
| CI build xanh nhưng report cũ | Reuse target/site hoặc XML | Clean build, so commit/timestamp |
| Multi-module aggregate bị tạo nhiều lần | ReportSet inheritance/aggregate sai | inherited=false ở aggregate |
| Multi-module links hỏng | Local build layout khác deployed layout | site:stage, kiểm URLs |
| site:deploy FAIL | Thiếu distributionManagement/site/auth | Chỉ deploy khi đã chuẩn bị |
| Site quá chậm | Chọn quá nhiều reports, report goal chạy test lại | Giới hạn reportSets, dùng report-only |
| No data trong JaCoCo | Test/agent chưa tạo exec data | Kiểm coverage instrumentation |
| Report được sinh dù tests fail | Báo cáo chỉ render dữ liệu lỗi | Giữ CI failure status, không coi HTML là PASS |

## 17. Quy trình điều tra khi xuất báo cáo lỗi

1. **Xác nhận CLI và môi trường:** `mvn -version`, command line, active profiles, JDK, settings/mirrors.
2. **Kiểm plugin resolution:** mục tiêu nào không tải được, version nào, lỗi Maven/plugin hay source.
3. **Kiểm build tests:** chạy `mvn clean verify`; kiểm `TEST-*.xml`, tests/errors/failures/skips.
4. **Kiểm reporting POM:** `<reporting>`, `<reportSets>`, `excludeDefaults`, Site Plugin version.
5. **Chạy riêng site:** `mvn site` sau khi có input XML; đọc log goal cụ thể.
6. **Nếu Javadoc lỗi:** sửa comment/link, xác định JDK tool và source roots.
7. **Nếu renderer lỗi:** đối chiếu Site/Doxia/skin/Reporting API stack và versions.
8. **Nếu thiếu file:** phân biệt output standalone `target/reports` với site `target/site`.
9. **Nếu có file nhưng 0 data:** kiểm XML/counts/metadata, không chỉ non-empty.
10. **Rerun từ sạch:** `mvn clean verify site`; chốt QA đầu ra và lưu artifact đúng commit.

Lệnh hỗ trợ:

```bash
mvn -version
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-site-plugin:3.22.0" -Dgoal=site -Ddetail=true
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-javadoc-plugin:3.12.0" -Dgoal=javadoc -Ddetail=true
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-surefire-report-plugin:3.6.1" -Dgoal=report-only -Ddetail=true
```

`help:effective-pom` cho bạn cấu hình plugin/reporting đã qua inheritance; `help:describe` cho parameters của một goal. Không lệnh nào **chạy tests hoặc xác nhận report HTML** thay cho lệnh build và kiểm tra output thực tế.

## 18. Bài tập tự đánh giá

**Bài 1.** Vì sao `mvn verify` không mặc nhiên tạo website? Vì default lifecycle và site lifecycle khác nhau, site phải được gọi hoặc bind riêng.

**Bài 2.** Ghim Site Plugin 3.22.0 có tự ghim Surefire Report Plugin không? Không. Mỗi plugin có coordinate/version độc lập.

**Bài 3.** Cấu hình `maven-project-info-reports-plugin` trong `<build><plugins>` có bảo đảm `mvn site` tạo Summary không? Không; cần reporting setup/reportSets thích hợp.

**Bài 4.** Sự khác nhau giữa `surefire-report:report` và `report-only`? `report` có thể kích hoạt test lifecycle; `report-only` chỉ đọc XML đã có.

**Bài 5.** Vì sao `mvn clean site` có thể không tạo `surefire.html` ở POM mẫu? Vì `clean` xóa XML, còn report-only không chạy tests.

**Bài 6.** XML có `tests=0` nhưng HTML file tồn tại: có PASS policy yêu cầu 2 tests không? Không. Phải kiểm số test thực chạy.

**Bài 7.** Tệp nào chứng minh Surefire test runner đã tạo input cho report? `target/surefire-reports/TEST-com.example.docs.GreetingServiceTest.xml` cùng counts hợp lệ.

**Bài 8.** Đường nào cho Surefire HTML khi standalone, đường nào khi Site? Thường `target/reports/surefire.html` và `target/site/surefire.html`.

**Bài 9.** Javadoc link sai có thể làm Java compiler pass mà site fail không? Có. Javadoc tool kiểm comments/doclint.

**Bài 10.** Bạn bỏ `<report>dependencies</report>` trong reportSet mà site vẫn BUILD SUCCESS. Điều gì còn thiếu? CI file/content check bắt buộc cho dependencies.html.

**Bài 11.** Vì sao không dùng Site Plugin 4 milestone khi thấy phiên bản cao hơn? Phải xem ổn định, compatibility, Maven/JDK requirements và migration guide.

**Bài 12.** `target/site/index.html` có, menu báo cáo không xuất hiện; kiểm gì? `site.xml`, `menu ref="reports"`, reportSets, output HTML và skin.

**Bài 13.** `<pluginManagement>` đã ghim Javadoc, nhưng module không có reporting plugin; site có chắc report không? Không.

**Bài 14.** Một multi-module site có links sai giữa child sites trong local target; phương án nào? Đọc docs về `site:stage` và site deployment layout.

**Bài 15.** CI giữ file target/site cũ trong cache, sau source change vẫn báo PASS. Sai ở đâu? Báo cáo không tương ứng commit/test run mới; cần clean và xác minh metadata.

## 19. Checklist trước khi chốt bài/bộ tài liệu dự án

- [ ] Đã xác định Maven/JDK runtime và system requirements của plugins.
- [ ] Maven Site Plugin được ghim version ở `build/plugins`.
- [ ] Project Info, Javadoc và Surefire Report được ghim versions ở `reporting/plugins`.
- [ ] Không dùng dynamic plugin versions `LATEST`/`RELEASE`.
- [ ] `reportSets` chỉ rõ các báo cáo bắt buộc, không phụ thuộc default bất ngờ.
- [ ] `Surefire Plugin` chạy tests và tạo XML trước khi report-only render.
- [ ] Test count, errors, failures, skipped được kiểm từ XML của run hiện tại.
- [ ] Javadoc source/comments, links, toolchain và UTF-8 đúng.
- [ ] Không tắt failOnError hoặc doclint để che lỗi API docs quan trọng.
- [ ] `mvn clean verify site` chạy trên checkout sạch.
- [ ] `target/site/index.html`, `summary.html`, `dependencies.html` có thật và có dữ liệu.
- [ ] `target/site/apidocs/index.html` có class/method documentation.
- [ ] `target/site/surefire.html` hiển thị test results tương ứng XML.
- [ ] Đã phân biệt `target/reports` của standalone report với `target/site`.
- [ ] Site descriptor/menu/skin được kiểm links và encoding.
- [ ] Khi nâng plugin, đã review migration/release notes và diff output.
- [ ] Với multi-module, aggregate reports và module links được kiểm đúng.
- [ ] `site:deploy` chỉ dùng khi có đích và quyền publish được xác nhận.
- [ ] CI lưu generated site cùng test XML và commit/SHA, không dùng report stale.
- [ ] Đã phân biệt “tạo được báo cáo” với “test/code/release đã đạt”.

**Kết luận:** Để có tài liệu Maven đáng tin, không chỉ đặt `maven-site-plugin` rồi chạy `mvn site`. Hãy **ghim phiên bản Site và từng reporting plugin**, cấu hình rõ `reportSets`, đảm bảo dữ liệu đầu vào (đặc biệt Surefire XML) đã sinh trong cùng build, rồi kiểm **tồn tại file, nội dung và test counts**. Với project thực hành: `mvn clean verify site` phải cho hai tests PASS và xuất `index.html`, `summary.html`, `dependencies.html`, `apidocs/index.html`, `surefire.html`. Khi lỗi, xử lý đúng tầng: **plugin resolution → input → report goal → output → semantic QA**; đừng tắt lỗi hoặc dựa vào mỗi dòng `BUILD SUCCESS`.

### Tài liệu chính thức của Apache Maven

- [Maven Site Plugin 3.22.0 — Introduction](https://maven.apache.org/plugins/maven-site-plugin/)
- [Maven Site Plugin — Configuring Reports / reportSets](https://maven.apache.org/plugins/maven-site-plugin/examples/configuring-reports.html)
- [Maven Site Plugin — Creating Content](https://maven.apache.org/plugins/maven-site-plugin/examples/creating-content.html)
- [Maven Site Plugin — site:site goal](https://maven.apache.org/plugins/maven-site-plugin/site-mojo.html)
- [Maven Site Plugin — Migration guide](https://maven.apache.org/plugins/maven-site-plugin/migrate.html)
- [Project Info Reports Plugin 3.9.0](https://maven.apache.org/plugins/maven-project-info-reports-plugin/)
- [Maven Javadoc Plugin 3.12.0 — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html)
- [Maven Surefire Plugin 3.6.1 — Usage](https://maven.apache.org/surefire/maven-surefire-plugin/usage.html)
- [Maven Surefire Report Plugin — report-only](https://maven.apache.org/surefire/maven-surefire-report-plugin/report-only-mojo.html)
- [Maven Surefire Report Plugin — report](https://maven.apache.org/surefire/maven-surefire-report-plugin/report-mojo.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — POM Reference / Reporting](https://maven.apache.org/pom.html#Reporting)
- [Apache Maven — Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
