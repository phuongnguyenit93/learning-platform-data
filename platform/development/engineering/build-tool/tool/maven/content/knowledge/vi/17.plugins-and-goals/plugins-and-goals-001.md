# Maven Build Plugin, Reporting Plugin và phần việc chúng đảm nhiệm

## 1. Bức tranh tổng quát: Maven làm việc thông qua plugin

Một dự án Java cần nhiều thao tác khác nhau: sao chép resource, biên dịch mã nguồn, chạy unit test, đóng gói JAR, kiểm tra chất lượng và tạo tài liệu cho người đọc. **Maven core** quản lý Project Object Model (POM), vòng đời build và cách chạy các tác vụ; phần lớn công việc cụ thể do **Maven plugins** cung cấp.

Hai nhóm chức năng bạn thường gặp là:

- **Build plugin**: thực thi công việc trong quá trình xây dựng, kiểm thử, đóng gói, cài đặt hoặc phát hành sản phẩm; được khai báo/cấu hình chủ yếu trong `<build><plugins>` hoặc được quản lý trong `<build><pluginManagement>`.
- **Reporting plugin**: sinh báo cáo, tài liệu hoặc trang thông tin để tích hợp vào **Maven Site**; được khai báo/cấu hình chủ yếu trong `<reporting><plugins>`. Thông thường chúng chạy khi Maven thực hiện **site lifecycle**.

Điều dễ nhầm là **một artifact plugin có thể cung cấp cả goal dùng để build lẫn goal dùng để report**. Chẳng hạn Maven Javadoc Plugin có thể tạo Javadoc độc lập và cũng tham gia hệ thống báo cáo của site. Vì vậy phải nhìn **goal, chỗ cấu hình và cách gọi**, không dán nhãn cứng cho mọi plugin.

### Tình huống mở đầu

Bạn chạy:

~~~bash
mvn clean verify
~~~

và thấy dự án có `target/classes`, `target/*.jar`, `target/surefire-reports/`. Nhưng file `target/site/index.html` hoặc báo cáo Javadoc trên site chưa xuất hiện. Bạn thêm Maven Javadoc Plugin vào `<reporting>` và chạy lại `mvn verify`, vẫn không thấy site.

Điều này **bình thường**: `verify` là phase của **default lifecycle**, còn `site` thuộc **site lifecycle**. Việc khai reporting plugin không tự gắn nó vào `verify`. Bạn thường cần:

~~~bash
mvn clean verify
mvn site
~~~

hoặc gọi các phase theo thứ tự trong cùng lệnh:

~~~bash
mvn clean verify site
~~~

Với điều kiện POM và plugins được cấu hình phù hợp, lệnh đầu tạo build/test outputs; lệnh thứ hai dùng những dữ liệu thích hợp để dựng trang báo cáo. Chạy `site` **không phải** cách thay thế test/build verification.

### Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích plugin, goal, Mojo, lifecycle, phase và execution khác nhau ra sao.
2. Phân biệt `<build>`, `<reporting>`, `<pluginManagement>` và `<reportSets>`.
3. Chỉ ra trách nhiệm của Compiler, Resources, Surefire, Failsafe, JAR, Site, Javadoc, Project Info Reports và Surefire Report plugins.
4. Giải thích vì sao `mvn verify` và `mvn site` tạo **hai loại đầu ra** khác nhau.
5. Viết POM Java 17 chạy được, có build plugin, reporting plugin, unit test và báo cáo HTML.
6. Chọn đúng cách gọi một goal trực tiếp hoặc cấu hình goal trong lifecycle.
7. Hiểu reporting plugin **trình bày kết quả** nhưng không nhất thiết là nơi **tạo/kiểm tra dữ liệu nguồn**.
8. Chẩn đoán lỗi build/report, site trống, báo cáo test thiếu, nhầm `site-deploy` với `deploy` và vấn đề multi-module.

## 2. Plugin, goal và Mojo: ba khái niệm không nên trộn

Mỗi Maven plugin là một artifact có tọa độ như:

~~~text
org.apache.maven.plugins:maven-compiler-plugin:3.14.0
~~~

Plugin có thể cung cấp nhiều **goals**, ví dụ:

~~~text
compiler:compile
compiler:testCompile
~~~

Một goal là một tác vụ Maven gọi được. Phía triển khai Java của goal thường gọi là một **Mojo** (Maven plain Old Java Object): một class mô tả tham số, hành vi và, khi có, phase mặc định.

Có thể hình dung:

~~~text
POM + Maven Core
       |
       v
Plugin artifact
       |
       +-- goal A  -> một tác vụ
       +-- goal B  -> một tác vụ
       +-- goal C  -> một tác vụ
       |
       v
Goal được gọi trực tiếp hoặc bind vào lifecycle phase
       |
       v
Output: bytecode / JAR / test results / report / site / ...
~~~

Ví dụ:

- `mvn compiler:compile` gọi trực tiếp một goal của Compiler Plugin.
- `mvn compile` yêu cầu Maven chạy **default lifecycle đến phase `compile`**. Với dự án `packaging=jar`, Maven có các binding mặc định, thường gồm `resources:resources` và `compiler:compile` ở những phase tương ứng.
- `mvn site` yêu cầu Maven chạy **site lifecycle** đến phase `site`; Maven Site Plugin tạo site và gọi các report goals thích hợp.
- `mvn javadoc:javadoc` gọi trực tiếp goal Javadoc; điều này **không đồng nghĩa** đã chạy toàn bộ site lifecycle.

**Mấu chốt:** phase không phải goal, plugin cũng không phải phase. Một phase có thể có nhiều goals, hoặc không có goal nào; một plugin có thể đóng góp nhiều goals cho các phase khác nhau.

## 3. Build plugin là gì?

Theo hướng dẫn Apache Maven, **build plugins** được cấu hình trong `<build>` và thực thi các công việc của build. Các goal của chúng có thể:

1. Được packaging mặc định bind vào lifecycle (ví dụ Compiler, Resources, Surefire, JAR với `jar` packaging).
2. Được bạn bind bằng `<executions><execution><phase>...`.
3. Được gọi trực tiếp trên CLI bằng `plugin-prefix:goal` hoặc tọa độ plugin đầy đủ.

### 3.1. Những build plugin thường gặp

| Plugin | Goal/đầu việc tiêu biểu | Phase thường liên quan | Đầu ra hoặc tác động |
| --- | --- | --- | --- |
| Maven Resources Plugin | `resources:resources`, `resources:testResources` | `process-resources`, `process-test-resources` | Copy/filter resources vào thư mục output |
| Maven Compiler Plugin | `compiler:compile`, `compiler:testCompile` | `compile`, `test-compile` | `.class` ở `target/classes` và `target/test-classes` |
| Maven Surefire Plugin | `surefire:test` | `test` | Chạy unit test; XML/TXT ở `target/surefire-reports` |
| Maven JAR Plugin | `jar:jar` | `package` cho `jar` packaging | `target/<artifactId>-<version>.jar` theo cấu hình mặc định |
| Maven Failsafe Plugin | `failsafe:integration-test`, `failsafe:verify` | `integration-test` và `verify` khi được cấu hình | Chạy/đánh giá integration tests; `target/failsafe-reports` |
| Maven Clean Plugin | `clean:clean` | `clean` của clean lifecycle | Dọn `target`/output cũ theo cấu hình |
| Maven Install Plugin | `install:install` | `install` | Đưa artifact vào local Maven repository |
| Maven Deploy Plugin | `deploy:deploy` | `deploy` | Phát hành artifact của project lên remote artifact repository |
| Maven Shade Plugin | `shade:shade` | Thường được bind vào `package` khi sử dụng | Tạo shaded/uber JAR theo cấu hình |
| Maven Antrun Plugin | `antrun:run` | Phase do bạn gắn | Chạy nhiệm vụ Ant thích hợp |

**Không phải mọi plugin trong bảng đều tự chạy ở mọi project.** Default binding phụ thuộc `packaging` và Maven core version; goal như Shade hay Failsafe thường cần cấu hình execution. Chỉ thấy plugin trong `<build><plugins>` cũng chưa chứng minh một goal tùy ý đã chạy.

### 3.2. Vai trò của `<executions>`

Đoạn POM minh họa (chỉ là một phần của `<project>`):

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <executions>
                <execution>
                    <id>say-hello-during-validate</id>
                    <phase>validate</phase>
                    <goals>
                        <goal>run</goal>
                    </goals>
                    <configuration>
                        <target>
                            <echo message="BUILD GOAL EXECUTED"/>
                        </target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Khi chạy `mvn validate`, Maven tới phase `validate` và thực hiện Antrun goal đã gắn. Nếu chỉ đặt plugin ở `<plugins>` mà không có goal mặc định được packaging bind, default phase hợp lệ hoặc execution, không thể mặc nhiên kết luận Antrun sẽ chạy.

`<executions>` là cơ chế cho **build plugin goals**. Để chọn **report goals** tạo trong site, bạn thường dùng `<reportSets>` ở phần reporting, chứ không đặt `<execution><phase>site</phase>` cho mọi report.

## 4. Reporting plugin là gì?

**Reporting plugins** tạo nội dung báo cáo cho **Maven Site**, ví dụ:

- Thông tin dự án: tên, version, dependencies, developer team, SCM, license, cấu hình build.
- Javadoc API của mã Java.
- Báo cáo kết quả unit test từ XML do Surefire tạo.
- Báo cáo style/analysis do Checkstyle, PMD, JXR hoặc công cụ kiểm tra tương ứng hỗ trợ.

Report output thường là **HTML, CSS, JavaScript hoặc tài nguyên web** trong `target/site` (mặc định), khác với file JAR được package và các XML test report gốc.

### 4.1. Những reporting plugin thông dụng

| Reporting plugin | Phần việc | Dữ liệu đầu vào | Kết quả thường thấy |
| --- | --- | --- | --- |
| Maven Project Info Reports Plugin | Trang Summary, Dependencies, Plugins, SCM, Licenses... | POM/effective model và metadata cần thiết | Các trang HTML thông tin dự án |
| Maven Javadoc Plugin | Tạo tài liệu API cho classes/methods | Java source và Javadoc comments | `target/site/apidocs/index.html` |
| Maven Surefire Report Plugin | Render thống kê và chi tiết test | `target/surefire-reports/TEST-*.xml` | `target/site/surefire-report.html` |
| Maven JXR Plugin | Cross-reference Java source theo dòng | Java source | HTML xref; có thể dùng để liên kết từ báo cáo khác |
| Maven Checkstyle Plugin | Report quy tắc coding style (nếu cấu hình report goal) | Java source/ruleset | HTML kiểm tra style |
| Maven PMD Plugin | Report vấn đề mã nguồn và duplicate code | Java source, rule set | HTML analysis/CPD |
| Maven Site Plugin | Điều phối tạo site và tích hợp reports | `src/site`, `<reporting>`, report goals | `target/site/index.html` và các file liên quan |

**Phân biệt nhóm chức năng với tên plugin:** Maven Javadoc, Checkstyle hoặc PMD có thể hỗ trợ **cả build goals lẫn report goals**. Surefire Plugin chuyên chạy test, còn Surefire **Report** Plugin chuyên dựng trang HTML từ kết quả test. Maven Site Plugin điều phối việc dựng site, bản thân nó thường được định phiên bản dưới `<build><plugins>` hay `pluginManagement`.

### 4.2. Report goal không nhất thiết tạo dữ liệu nguồn

Một số báo cáo chỉ đọc dữ liệu đã tồn tại:

~~~text
surefire:test
    |
    v
target/surefire-reports/TEST-*.xml
    |
    v
surefire-report:report-only (trong site/reporting)
    |
    v
target/site/surefire-report.html
~~~

Nếu chưa có XML test report, goal `report-only` **không tự chạy test** để tạo dữ liệu. Báo cáo có thể thiếu, trống hoặc báo không có kết quả. Khi đó đúng cách là chạy `mvn test`/`mvn verify` trước, không sửa reporting plugin thành build plugin bừa bãi.

Ngược lại, `surefire-report:report` (không có “only”) có những hành vi đi kèm chạy test; không nên mặc định hai goal giống nhau. Trong bài thực hành, ta chủ động dùng **`report-only`** để tách việc **chạy test** và **hiển thị kết quả test**.

### 4.3. Build fail và report hiển thị lỗi là hai vấn đề khác nhau

Nếu một unit test thất bại ở phase `test`, build thường nhận `BUILD FAILURE` qua Surefire. Site report có thể **hiển thị** một kết quả test đỏ, nhưng chỉ tạo trang HTML không phải cơ chế bảo đảm pipeline fail.

Ngược lại, một report plugin có thể gặp lỗi khi render trang và làm lệnh `mvn site` thất bại dù `mvn verify` trước đó đã PASS. Cần phân biệt **lỗi của build artifact** với **lỗi xuất bản tài liệu**.

## 5. Ba lifecycle: default, clean và site

Maven có ba lifecycle built-in: `default`, `clean` và `site`. Mỗi lifecycle có các phase riêng.

~~~text
clean lifecycle
  pre-clean -> clean -> post-clean
                  |
                  v
            dọn output cũ

default lifecycle (rút gọn)
  validate -> compile -> test -> package -> verify -> install -> deploy
                |          |        |
                v          v        v
           target/classes  tests   target/*.jar
                                      |
                                      v
                            artifact có thể phát hành

site lifecycle
  pre-site -> site -> post-site -> site-deploy
                |
                v
            target/site/
              index.html
              summary.html
              dependencies.html
              apidocs/
              surefire-report.html
~~~

**Đây là sơ đồ rút gọn**, không bao gồm mọi phase giữa `compile` và `verify`; output chỉ có nếu goal/configuration tương ứng đã chạy.

### 5.1. Lệnh nào làm gì?

| Lệnh | Ý nghĩa | Không nên suy ra |
| --- | --- | --- |
| `mvn clean` | Chạy clean lifecycle đến `clean` | Không chạy `compile` hoặc `site` |
| `mvn test` | Chạy default lifecycle đến `test` | Chưa chắc đóng gói JAR hoặc site |
| `mvn package` | Chạy đến `package` | Không tự dựng trang HTML của site |
| `mvn verify` | Chạy đến `verify`, gồm các phase default trước đó | Không tự gọi `site` chỉ vì có `<reporting>` |
| `mvn site` | Chạy site lifecycle đến `site` | Không phải `mvn verify` và không tự bảo đảm đã test |
| `mvn clean verify site` | Gọi các lifecycle/phase theo thứ tự trên CLI | Không tương đương với một plugin goal |
| `mvn deploy` | Publish project artifact vào artifact repository | Không giống `site-deploy` |
| `mvn site-deploy` | Publish generated site qua Site Plugin khi đã cấu hình | Không dùng để publish binary JAR |

Một Maven CLI có thể chứa nhiều phase của các lifecycle khác nhau. `mvn clean verify site` là cách rõ ràng để trước hết tạo/test artifact, rồi dựng site từ dữ liệu thích hợp. Nếu site cần một nguồn báo cáo được sinh ở plugin riêng, vẫn phải cấu hình goal nguồn đúng phase.

**Lưu ý Maven 4:** một số phase/binding và sự tương thích của plugin có thay đổi. Bài thực hành bên dưới chốt **Maven 3.9.x, Java 17+** để có cùng hành vi, và khuyến nghị kiểm tra compatibility trước khi chuyển sang Maven 4.

### 5.2. `site-deploy` không phải `deploy`

`mvn deploy` đưa artifact như `jar`, `pom` lên **Maven artifact repository** theo `distributionManagement/repository` và các yêu cầu phân phối artifact.

`mvn site-deploy` dùng **site lifecycle**, đưa **các file trang web/tài liệu** đến site server hoặc vị trí được quản lý theo `distributionManagement/site` thông qua giao thức phù hợp.

Đây là hai điểm đích khác nhau, ngay cả khi dự án khai cả hai dưới `distributionManagement`. Không chạy `mvn site-deploy` với kỳ vọng nó sẽ cập nhật JAR trên Nexus hoặc Artifactory.

## 6. Cấu hình POM: build và reporting có cấu trúc riêng

### 6.1. Cấu trúc tổng quát

~~~xml
<project>
    <!-- Các trường project thông thường -->

    <build>
        <pluginManagement>
            <plugins>
                <!-- Version và cấu hình plugin được quản lý -->
            </plugins>
        </pluginManagement>
        <plugins>
            <!-- Build plugins và executions -->
        </plugins>
    </build>

    <reporting>
        <excludeDefaults>false</excludeDefaults>
        <plugins>
            <!-- Report plugins và reportSets -->
        </plugins>
    </reporting>
</project>
~~~

Đây là **sơ đồ XML**, không phải POM đầy đủ có thể build, vì đã lược bỏ namespace/modelVersion và các phần cần thiết.

**Vai trò của bốn vị trí:**

- `build/plugins`: các plugin được dùng bởi project cho build goals và site orchestration nếu có.
- `build/pluginManagement`: version/configuration defaults cho **build plugins** khi được dùng; không tự chạy mọi goal.
- `reporting/plugins`: plugin cung cấp report goals cho site, có thể đặt `configuration` và `reportSets`.
- `reporting/excludeDefaults`: khi true, loại các báo cáo mặc định được Site Plugin bổ sung (như Project Info mặc định), hữu ích khi muốn site chỉ chứa report đã chọn.

### 6.2. Build `<executions>` và reporting `<reportSets>` khác nhau

Build execution:

~~~xml
<executions>
    <execution>
        <id>check-on-verify</id>
        <phase>verify</phase>
        <goals>
            <goal>check</goal>
        </goals>
    </execution>
</executions>
~~~

Đoạn trên có ý nghĩa **chỉ khi** plugin đang dùng thật sự có goal tên `check` phù hợp, ví dụ một plugin kiểm tra chất lượng. Không copy fragment đó vào bất kỳ plugin nào không hỗ trợ `check`.

Report set:

~~~xml
<reportSets>
    <reportSet>
        <reports>
            <report>summary</report>
            <report>dependencies</report>
        </reports>
    </reportSet>
</reportSets>
~~~

Đoạn trên chọn các report goals mà plugin tương ứng hỗ trợ, ví dụ Maven Project Info Reports Plugin. Nó **không tự bind goal `summary` hoặc `dependencies` vào phase `verify`**. Khi chạy `mvn site`, Site Plugin dùng cấu hình `reporting` để điều phối các report đã chọn.

### 6.3. Một plugin có thể đóng cả hai vai trò

Apache Maven hướng dẫn rằng **plugin không nhất thiết được phân loại vĩnh viễn chỉ là build hoặc report**. Một plugin có thể có nhiều Mojos, trong đó một số là report goals phù hợp với Maven Site.

Ví dụ Maven Javadoc Plugin:

- Khai dưới `<reporting>` để Site Plugin tạo Javadoc và liên kết nó vào site navigation.
- Gọi `javadoc:javadoc` trực tiếp để xuất Javadoc mà không yêu cầu tạo toàn bộ Maven Site.
- Có thể cấu hình dưới `<build>` và bind một goal thích hợp vào phase riêng nếu quy trình thật cần.

Do đó không nên nói “Javadoc luôn là reporting plugin, không thể gọi như build plugin” hoặc “một report không thể chạy qua CLI”. Cần đọc plugin documentation và chọn cách sử dụng đúng mục đích.

## 7. Cấu hình trực tiếp và `pluginManagement`

Giả sử parent POM thống nhất Java Compiler Plugin version `3.14.0` cho nhiều modules:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là **fragment của parent POM**. `pluginManagement` quản lý version và cấu hình có thể áp cho plugin được dùng trong modules; nó **không tự sinh một goal execution tùy ý**.

Khi module khai plugin này trong `<build><plugins>` hoặc packaging `jar` có binding compile cần plugin, version/configuration được quản lý có thể áp dụng. Nhưng bạn không thể chỉ thêm `maven-shade-plugin` vào `pluginManagement` rồi cho rằng `shade:shade` sẽ tự chạy khi `mvn package`.

Với reporting plugins, hãy **pin version ngay trong `<reporting><plugins>`**. Các phiên bản Maven Site Plugin hiện đại có khả năng kết hợp cấu hình từ `<reporting>` và phần build/pluginManagement trong ngữ cảnh phù hợp, nhưng đây không phải lý do để bỏ trống version của reporting plugin khi cần build tái lập.

### Một chi tiết cấu hình quan trọng

Theo hướng dẫn chính thức về Configuring Plug-ins:

- Trong **`mvn site`**, Maven Site Plugin từ phiên bản 3.4 trở lên có thể dùng cấu hình ở `<reporting>` và các thông số liên quan trong `<build>`.
- Khi bạn gọi **trực tiếp một report goal**, ví dụ `mvn javadoc:javadoc`, cấu hình riêng dưới `<reporting>` **không đương nhiên được dùng như ở site**; thông số dưới phần build của plugin và tham số CLI mới là nguồn được goal trực tiếp xử lý theo cơ chế tương ứng.

Vì thế hai lệnh có thể xuất ra báo cáo với nội dung/đường dẫn/filters khác nhau, dù cùng plugin artifact. **Đừng gộp `<reporting><configuration>` và `<build><configuration>` vào một khái niệm duy nhất.**

## 8. Bài thực hành hoàn chỉnh: Java 17, unit test và Maven Site

Ta tạo một dự án **chạy độc lập**, dùng Java 17 và Maven 3.9.x. Bài lab minh họa:

1. Build plugin: Compiler biên dịch Java, Surefire chạy unit test, JAR đóng gói sản phẩm.
2. Site Plugin: điều phối site lifecycle.
3. Reporting plugins: Project Info Reports (Summary/Dependencies/Plugins), Javadoc và Surefire Report.
4. Hai nguồn output khác nhau: sản phẩm build/test và trang báo cáo HTML.

### 8.1. Điều kiện và cấu trúc file

Yêu cầu:

- JDK 17+ có `javac` và `javadoc`.
- Maven 3.9.x hoặc Maven Wrapper trỏ đúng phiên bản Maven 3 tương thích.
- Có kết nối Maven Central hoặc mirror/repository hợp lệ để tải dependencies và plugins ở lần chạy đầu.
- Không cần IDE, Docker, database, Spring Boot hoặc dịch vụ trả phí.

Cấu trúc:

~~~text
maven-plugin-roles-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/example/
    │       ├── Calculator.java
    │       └── Main.java
    └── test/
        └── java/dev/example/
            └── CalculatorTest.java
~~~

### 8.2. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>maven-plugin-roles-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Maven Plugin Roles Demo</name>
    <description>Java 17 build and reporting plugin lesson</description>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                <version>3.14.0</version>
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

            <!-- Điều phối SITE lifecycle; không phải report goal -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-site-plugin</artifactId>
                <version>3.21.0</version>
            </plugin>
        </plugins>
    </build>

    <reporting>
        <!-- Chỉ dùng các báo cáo được chọn trong phần này -->
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
                            <report>plugins</report>
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
                <version>3.6.0</version>
                <reportSets>
                    <reportSet>
                        <reports>
                            <!-- Chỉ đọc kết quả test đã có -->
                            <report>report-only</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
        </plugins>
    </reporting>
</project>
~~~

**Giải thích từng nhóm:**

- `<packaging>jar</packaging>` khiến Maven có các default goal bindings cho dự án JAR.
- Compiler Plugin dùng `<maven.compiler.release>17</maven.compiler.release>` để biên dịch tương thích Java 17.
- Surefire Plugin chạy tests theo quy ước đặt tên, sử dụng JUnit 5 dependency có `scope=test`.
- JAR Plugin đóng gói các class chính trong `target/maven-plugin-roles-demo-1.0.0.jar`.
- Site Plugin `3.21.0` phù hợp với Maven 3.9.x, được pin version để không dựa vào default plugin resolution.
- `excludeDefaults=true` làm rõ site chỉ tập trung các report goals đã chọn (tránh thêm mặc định ngoài danh sách).
- Project Info Reports Plugin tạo trang `summary`, `dependencies`, `plugins`.
- Javadoc Plugin tạo trang API Javadoc.
- Surefire Report Plugin dùng `report-only`: đọc XML tests **đã được tạo** trước đó, không lấy việc render report làm công đoạn chạy lại test.

**Quan trọng về version:** phiên bản plugin phải được kiểm tra tương thích với Maven/JDK của project; các version này được chọn rõ ràng để người học tái lập hành vi của lab trên Maven 3.9.x. Không dùng kết quả lab này làm cam kết rằng mọi Maven 4 hoặc mọi plugin mới hơn sẽ giữ nguyên cách chạy.

### 8.3. Code Java 17 có Javadoc thật

Tạo `src/main/java/dev/example/Calculator.java`:

~~~java
package dev.example;

/**
 * Small arithmetic utility used to demonstrate Maven build and reporting.
 *
 * <p>The operations in this class are intentionally deterministic.</p>
 */
public final class Calculator {
    private Calculator() {
    }

    /**
     * Adds two integers.
     *
     * @param left the first operand
     * @param right the second operand
     * @return the arithmetic sum of the operands
     */
    public static int add(int left, int right) {
        return left + right;
    }
}
~~~

File có Javadoc cho class và public method để Maven Javadoc Plugin sinh nội dung thực tế, thay vì một báo cáo trống.

Tạo `src/main/java/dev/example/Main.java`:

~~~java
package dev.example;

/**
 * Demonstrates a tiny application packaged using Maven.
 */
public final class Main {
    private Main() {
    }

    /**
     * Runs the demo.
     *
     * @param args command-line arguments, unused
     */
    public static void main(String[] args) {
        System.out.println("Build plugin demo: " + Calculator.add(7, 5));
    }
}
~~~

`Main.java` không cần JUnit lúc chạy. Tạo file test `src/test/java/dev/example/CalculatorTest.java`:

~~~java
package dev.example;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(12, Calculator.add(7, 5));
    }
}
~~~

JUnit 5 test này đúng cho `maven-surefire-plugin:3.5.2`, đặt tên `CalculatorTest` thuộc pattern tìm test thông dụng. Kết quả mong đợi: **một test, không có failure/error/skip**.

### 8.4. Thực hành A — chạy build plugin

Ở thư mục `maven-plugin-roles-demo`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify
~~~

Theo POM, các công việc chính diễn ra:

~~~text
clean:clean                      -> xóa output của lần build trước
resources:resources             -> copy resources nếu có
compiler:compile                -> compile Java 17
resources:testResources         -> copy test resources nếu có
compiler:testCompile            -> compile CalculatorTest
surefire:test                   -> chạy JUnit 5 test
jar:jar                         -> tạo JAR
verify                          -> chạy những checks gắn tại đây, nếu có
~~~

Dòng trên là **mẫu trình tự mục đích**, không phải bản sao nguyên văn Maven log. Số lượng goal và plugin version hiển thị thực tế có thể có thêm các mục của Maven core.

Sau build thành công, kiểm tra:

~~~text
target/
├── classes/dev/example/Calculator.class
├── classes/dev/example/Main.class
├── test-classes/dev/example/CalculatorTest.class
├── maven-plugin-roles-demo-1.0.0.jar
└── surefire-reports/
    ├── TEST-dev.example.CalculatorTest.xml
    └── dev.example.CalculatorTest.txt
~~~

**Không cần đúng thứ tự file như sơ đồ**, và `target` còn có các folder do plugin tạo. Cần quan sát `.class`, JAR và XML test report. JAR plugin mặc định **không** đưa JUnit dependency vào JAR thường, và JAR này chưa khai `Main-Class` trong manifest để chạy bằng `java -jar`.

Chạy application trực tiếp với classpath là classes:

~~~bash
java -cp target/classes dev.example.Main
~~~

**Stdout chính xác:**

~~~text
Build plugin demo: 12
~~~

Câu lệnh `java` ở trên chạy class Java độc lập, không yêu cầu người học cài plugin Exec hoặc sửa manifest. Điều này làm rõ sự khác biệt giữa **JAR đóng gói** và **chạy main class**, vốn là hai công đoạn riêng.

### 8.5. Thực hành B — chạy reporting plugins

Sau khi `mvn clean verify` PASS, chạy:

~~~bash
mvn -B -ntp site
~~~

Maven thực hiện site lifecycle và điều phối các report goals đã khai trong `<reporting>`. Sau khi thành công, kỳ vọng thấy các file tương đương:

~~~text
target/site/
├── index.html
├── summary.html
├── dependencies.html
├── plugins.html
├── apidocs/
│   └── index.html
└── surefire-report.html
~~~

Tùy Site/Report Plugin, version, theme/skin và cấu hình, ngoài các file trên còn có CSS, JS, images và các trang con. Với site được tạo thành công, hãy bắt đầu bằng `target/site/index.html`, sau đó mở menu Project Reports để kiểm tra các trang đã chọn.

**Cách mở output:**

- Linux/macOS: mở `target/site/index.html` trong trình duyệt hoặc file manager; một số trình duyệt hạn chế tài nguyên/đường dẫn `file://` nên có thể cần local HTTP server cho kiểm tra đầy đủ.
- Windows: mở `target\site\index.html` bằng trình duyệt/file manager.

Để xác nhận test report đã được dựng từ XML **của lượt verify vừa chạy**, nhìn cả `target/surefire-reports` lẫn `target/site/surefire-report.html`. Đừng dựa vào việc file HTML tồn tại để suy rằng test mới nhất đã chạy.

### 8.6. So sánh kết quả sau hai lệnh

| Kiểm tra | Sau `mvn clean verify` | Sau `mvn site` tiếp theo |
| --- | --- | --- |
| `target/classes` | Có nếu compile thành công | Không tự mất; site không thay `compile` |
| `target/*.jar` | Có nếu package thành công | Site không tự sinh bản JAR mới thay thế |
| `target/surefire-reports/TEST-*.xml` | Có nếu test chạy | `report-only` có thể đọc lại XML |
| `target/site/index.html` | Không được tạo bởi `verify` trong POM mẫu | Có nếu site tạo thành công |
| `target/site/apidocs` | Không được tạo bởi `verify` trong POM mẫu | Có nếu Javadoc report chạy |
| `target/site/surefire-report.html` | Không được tạo bởi `verify` trong POM mẫu | Có nếu report render thành công |

Có thể gọi gộp:

~~~bash
mvn -B -ntp clean verify site
~~~

Trong POM demo, đây là cách gọn để kiểm tra cả sản phẩm build/test và trang tài liệu, vì `verify` được chạy trước `site`.

### 8.7. Thực hành C — tách vai trò bằng cách đổi POM

Để tự chứng minh sự khác biệt:

**Thử 1:** giữ nguyên `<build>`, nhưng tạm bỏ entry `maven-javadoc-plugin` khỏi `<reporting>`, rồi chạy `mvn clean site`. Site vẫn có thể có Project Info/Surefire Reports, nhưng **không được mong đợi có Javadoc mới từ entry đó**. Hãy xóa output site cũ để tránh nhìn nhầm file cũ; `mvn clean site` phù hợp cho thử nghiệm này nhưng không thay `verify`.

**Thử 2:** chỉ giữ `<reporting>` nhưng bỏ entry `maven-surefire-plugin` khỏi `<build>` của POM mẫu. Với `jar` packaging, Maven còn có thể dùng **default Surefire binding** do packaging/Maven core chọn phiên bản, nên test **chưa chắc ngừng chạy**. Điều này chứng minh “bỏ khai báo plugin” không nhất thiết tắt default lifecycle binding. Muốn loại một goal khỏi lifecycle cần hiểu packaging/binding/skip/execution thực tế và hậu quả đối với verification.

**Thử 3:** đổi `<report>report-only</report>` thành một report goal khác mà Surefire Report Plugin hỗ trợ, ví dụ `report`, rồi đối chiếu hành vi. Với `report`, plugin có thể thực hiện thêm việc chạy test hoặc fork lifecycle, làm phân tách công đoạn kém rõ ràng. Hoàn nguyên `report-only` sau thử nghiệm.

**Quy tắc:** khi thử loại một report, chạy trên **build sạch** hoặc xóa riêng output site cũ, rồi kiểm tra file mới thực sự được sinh; việc thấy file từ lần trước không chứng minh plugin vừa chạy.

## 9. Khi nào dùng plugin thực thi build và khi nào dùng báo cáo?

### 9.1. Chọn build goal khi cần tạo/kiểm tra sản phẩm

Các tình huống:

- Cần đảm bảo Java source compile được: `compiler:compile`.
- Cần biết unit tests PASS/FAIL: `surefire:test`, thường qua `mvn test`/`mvn verify`.
- Cần kiểm tra integration test có setup/teardown: `failsafe:integration-test` và `failsafe:verify` gắn đúng phases, thường gọi `mvn verify`.
- Cần JAR/war dùng để chạy, phát hành: `jar:jar` hoặc plugin packaging phù hợp.
- Cần áp quality gate trên CI: dùng goal `check` của plugin chất lượng **được bind vào phase phù hợp**, để lỗi làm build fail theo cấu hình.
- Cần tạo báo cáo JaCoCo coverage làm artifact để kiểm tra ngưỡng: dùng các goals `prepare-agent`, `report`, `check` theo đúng lifecycle/configuration, thay vì chỉ hiển thị một trang site.

Build goal và report goal có thể cùng xuất file HTML trong một số plugin, nhưng chất lượng của pipeline phụ thuộc **goal nào chạy và có điều kiện fail hay không**, không phụ thuộc file extension.

### 9.2. Chọn reporting goal khi cần công bố, xem hoặc chia sẻ kết quả

Các tình huống:

- Trang tài liệu cho người mới: Project Info Reports.
- Javadoc API duyệt theo package/class/method.
- Bảng kết quả test có liên kết đến test case, duration, failure.
- Báo cáo style/static analysis cho người review.
- Trang HTML có menu tích hợp nhiều báo cáo.

Reporting plugin **không tự đảm bảo** dữ liệu đầu vào mới, không thay Maven verification, không biến mọi warning thành `BUILD FAILURE`. Khi cần quality gate, thiết kế thêm goal kiểm tra tương ứng trong default lifecycle.

### 9.3. Khi một plugin có cả goal build và report

Ví dụ Maven Checkstyle Plugin hỗ trợ kiểm tra coding conventions trong build và tạo báo cáo cho site. Một cấu hình có thể:

- Gắn Checkstyle `check` vào `verify` để CI FAIL nếu vi phạm quy tắc.
- Khai Checkstyle report goal trong `<reporting>` để tạo trang HTML cho người đọc.

Hai công việc liên quan nhưng **khác mục đích**: một bên là **enforcement**, bên kia là **presentation**. Thường cần cấu hình ruleset, excludes, version và encoding thống nhất, nhưng vẫn phải kiểm tra behavior của mỗi goal.

## 10. Gọi trực tiếp reporting goal không giống `mvn site`

Giả sử bạn muốn tạo duy nhất Javadoc, không cần cả project website. Bạn có thể gọi goal trực tiếp của Javadoc Plugin:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-javadoc-plugin:3.12.0:javadoc
~~~

Kết quả là tài liệu Javadoc độc lập (thư mục output tùy goal và configuration). Nó **không chạy toàn bộ Site Plugin**, không tự tạo menu Project Reports của Maven Site.

Nếu muốn một report Project Info đơn lẻ:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-project-info-reports-plugin:3.9.0:dependencies
~~~

Goal này được tài liệu Project Info Reports đánh dấu là report goal, với output location riêng cho trường hợp gọi trực tiếp, có thể khác nơi Maven Site điều phối tạo báo cáo. Hãy nhìn log và tham số `outputDirectory` thay vì mặc nhiên xem `target/site/dependencies.html` là đường dẫn cố định trong cả hai kiểu gọi.

**Cảnh báo về cấu hình:** giá trị trong `<reporting><configuration>` **không được tự động dùng y nguyên** trong lời gọi trực tiếp. Để cấu hình goal được gọi trực tiếp, cần xem `<build><plugins>`, cấu hình execution/plugin và tham số CLI theo tài liệu plugin. Do đó:

~~~bash
mvn site
mvn javadoc:javadoc
~~~

có thể dùng cùng plugin artifact nhưng nhận **configuration khác nhau** và sinh đầu ra ở ngữ cảnh khác nhau.

### 10.1. Dùng `help:describe` xác định goal nào hỗ trợ

Có thể tra tài liệu goal trực tiếp:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.apache.maven.plugins:maven-javadoc-plugin -Dgoal=javadoc -Ddetail
~~~

Mục tiêu của `help:describe` là xem thông tin về goal, tham số, default phase và yêu cầu plugin. Lệnh không thay thế việc chạy goal; nó hỗ trợ **xác định cách gọi đúng**.

### 10.2. Khi thấy build log có `site:site`

Đừng hiểu dòng `site:site` nghĩa mọi report goal đã chạy. Site Plugin có thể tạo site không có report cụ thể, report bị skip, `excludeDefaults` loại report mặc định, profile chưa active hoặc plugin báo không có dữ liệu.

Hãy kiểm tra **log của từng report goal**, các file HTML mới được tạo và `<reporting>` trong effective POM.

## 11. `reportSets`, `excludeDefaults` và các mặc định

### 11.1. `reportSets` chọn report goals cụ thể

Ví dụ:

~~~xml
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
                    </reports>
                </reportSet>
            </reportSets>
        </plugin>
    </plugins>
</reporting>
~~~

Đây là **fragment dưới `<project>`**, không phải toàn bộ POM. Khi `mvn site` chạy và report plugin hoạt động phù hợp, nó tạo những report được chọn.

Một report goal hợp lệ là goal **do plugin đó công bố**, không phải bất kỳ chuỗi nào người dùng tự nghĩ. Nếu khai `<report>java-code-report</report>` cho plugin không có goal đó, site generation có thể thất bại vì không tìm được report.

### 11.2. `excludeDefaults` và Project Info

Site Plugin thường có các báo cáo Project Info mặc định nếu không loại chúng và có môi trường cần thiết. `<excludeDefaults>true</excludeDefaults>` dùng khi bạn muốn tránh các report mặc định ngoài danh sách được quản lý.

**Không hiểu `excludeDefaults=true` là “tắt tất cả report plugins”**. Nó loại report mặc định; các report plugins/report sets **bạn cấu hình tường minh** vẫn có thể được chạy. Trong lab, chúng ta chọn ba report Project Info có mục đích rõ ràng, vì vậy không cần cả bộ default reports.

### 11.3. Không có reportSets và cấu hình mặc định

Nếu plugin báo cáo không có `<reportSets>`, Site Plugin có thể sử dụng danh sách **report goals mặc định do plugin hỗ trợ**, tùy plugin/version. Với một plugin có nhiều reports (như Project Info), điều này có thể tạo nhiều trang hơn dự kiến.

Khi site lớn, chủ động dùng `reportSets` để giảm những report không cần thiết, thời gian tạo site, dependency resolution và khả năng phải cấu hình SCM/issue tracker chưa có dữ liệu.

### 11.4. `reporting.outputDirectory`

Output site mặc định thường là `${project.build.directory}/site`, tức `target/site` theo default project build directory. POM có thể đổi `reporting.outputDirectory` hoặc cấu hình Site Plugin để chuyển vị trí.

Nếu site sinh thành công nhưng bạn tìm không thấy file ở `target/site`, kiểm tra **effective POM**, plugin output setting và log. Đừng suy luôn rằng Maven không tạo báo cáo.

## 12. Multi-module và parent: report của module nào?

Giả sử project:

~~~text
workspace/
├── pom.xml           (parent và aggregator, packaging=pom)
├── api/pom.xml       (module library)
└── service/pom.xml   (module service)
~~~

Trong multi-module project:

- Mỗi module có effective POM, dependencies và build outputs riêng.
- Parent POM có thể quản lý plugins và reporting configuration để modules kế thừa theo quy tắc.
- Site generation có thể tạo **site của từng module** hoặc một cấu trúc module-site tùy cách gọi và cấu hình reactor.
- Một số report goals có tính **aggregate** và xử lý nhiều module; không phải mọi report đều tự kết hợp toàn bộ reactor.
- **Site Plugin cảnh báo** liên kết giữa các module sites có thể không hoạt động đúng nếu bạn chỉ tạo local site một cách đơn giản mà không stage theo cấu trúc triển khai.

Vì vậy, không nên mong `mvn site` ở parent chỉ tạo **một trang duy nhất** chứa toàn bộ thống kê mọi module với cùng semantics. Để dựng site đa module có liên kết đúng, xem **Maven Site Plugin – Building a Multi-module Site**, các goal `site:stage` và/hoặc khả năng aggregate của reporting plugin phù hợp.

### Phân biệt parent và aggregator

`<parent>` tạo quan hệ **kế thừa cấu hình**. `<modules>` xác định **reactor modules**. Một POM thường đóng cả hai vai trò nhưng không bắt buộc.

Nếu bạn định nghĩa `<reporting>` ở parent, child chỉ có thể nhận cấu hình theo quy tắc inheritance khi thật sự khai `<parent>`. Chỉ liệt kê child trong `<modules>` không tự làm child kế thừa report plugin từ aggregator.

### Chỗ đặt version nhất quán cho nhiều module

Thông thường:

~~~text
parent pom.xml:
    build/pluginManagement  -> version/configuration build plugins
    reporting/plugins       -> report plugins, reportSets, version
    build/plugins           -> plugin executions muốn áp toàn bộ modules (nếu phù hợp)

child pom.xml:
    parent                  -> quan hệ kế thừa
    build/plugins           -> dùng/override plugin khi module cần
    reporting               -> bổ sung/override report theo nhu cầu
~~~

Không ép tất cả modules chạy report nặng nếu không cần. Đặc biệt với Javadoc và JXR, module `packaging=pom` không có Java source thì report có thể trống; đây không nhất thiết là lỗi.

## 13. CI/CD: kết hợp build, kiểm thử và sinh báo cáo

Một pipeline có thể có hai mục đích riêng:

1. **Quality gate**: đảm bảo compile/test/verify PASS, chặn merge khi test đỏ.
2. **Documentation artifact**: tạo trang HTML để review hoặc publish.

Trình tự thường hợp lý:

~~~text
Checkout + JDK + Maven Wrapper
              |
              v
        ./mvnw clean verify
              |
              +--> JAR / class files
              +--> surefire/failsafe XML
              +--> checks PASS/FAIL
              |
              v  (nếu policy cho phép)
        ./mvnw site
              |
              +--> target/site/index.html
              +--> Javadoc / Project Info / Surefire report
              |
              v
     Upload target/site as CI artifact
          hoặc publish website đã duyệt
~~~

Ví dụ đoạn **steps của GitHub Actions**, không phải workflow hoàn chỉnh:

~~~yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'

  - name: Verify Java project
    run: ./mvnw -B -ntp clean verify

  - name: Generate Maven Site
    run: ./mvnw -B -ntp site

  - name: Save generated site
    uses: actions/upload-artifact@v4
    with:
      name: maven-site
      path: target/site/
~~~

Đoạn này giả định repository **đã có Maven Wrapper** (`mvnw` và các file wrapper thích hợp). Nếu chưa có, dùng Maven có sẵn trên runner với version đã chuẩn hóa. Workflow hoàn chỉnh còn cần `on`, `jobs`, `runs-on` và quyền CI cần thiết.

**Tình huống test thất bại:** theo mặc định nếu bước `verify` thất bại, các bước tiếp theo thông thường không được chạy. Nếu chính sách cần lưu báo cáo kể cả khi test thất bại, phải thiết kế bước artifact upload phù hợp (ví dụ `if: always()` cho phần upload), song song việc bảo toàn trạng thái CI fail. Không được khiến pipeline xanh chỉ để thu thập HTML.

**Lưu ý về report-only:** nếu `site` được chạy trong một job khác với job test, cần chuyển **test XML** và các inputs cần thiết sang job đó; `report-only` không thể suy lại số test từ không khí. Một site trống trên runner sạch có thể chỉ vì report nguồn không được chuyển.

### Có nên chạy `mvn site-deploy` tự động?

Chỉ khi có site server/site distribution management được định nghĩa, quyền publish và quy trình xác nhận nội dung. `site-deploy` không phải thao tác đơn thuần upload artifact CI; nó có thể cập nhật website công khai hoặc nội bộ. Không dùng lệnh publish site trong mọi pull request nếu quyền hoặc nội dung nhạy cảm chưa được kiểm soát.

## 14. Xử lý lỗi và các hiểu nhầm phổ biến

### 14.1. “Đã thêm reporting plugin nhưng `mvn verify` không có HTML report”

**Nguyên nhân:** goal được khai trong `<reporting>` cho site, không tự bind vào `verify`.

**Hướng sửa:** chạy `mvn site` sau build. Nếu thật sự cần một check trong `verify`, cấu hình **build goal phù hợp** có khả năng kiểm tra và fail, không chỉ tạo report HTML.

### 14.2. “`mvn site` ra trang thông tin nhưng không có test report”

**Nguyên nhân có thể:** chưa chạy Surefire, report XML không tồn tại, unit test không được discover, report plugin chưa khai đúng, `reportSets` sai hoặc site được tạo ở một build/job sạch.

**Hướng sửa:** chạy `mvn clean verify`, kiểm tra `target/surefire-reports/TEST-*.xml`, sau đó `mvn site` và tìm `target/site/surefire-report.html`. Với `report-only`, đừng kỳ vọng nó chạy lại tests.

### 14.3. “Chạy `mvn site` mà không có Javadoc”

**Nguyên nhân có thể:** Javadoc plugin không khai dưới `reporting`, report set thiếu goal `javadoc`, không có Java source, Javadoc lỗi cú pháp hay toolchain/JDK thiếu.

**Hướng sửa:** xem Site/Javadoc Plugin log, kiểm tra `javac`/`javadoc`, `target/site/apidocs` và cấu hình `<reporting>`. Tránh coi lỗi Javadoc source syntax là lỗi Maven Site Plugin.

### 14.4. “`mvn javadoc:javadoc` cho output khác `mvn site`”

**Nguyên nhân:** gọi goal trực tiếp và gọi qua site có **ngữ cảnh configuration** khác nhau.

**Hướng sửa:** đọc `<build><plugins>`, `<reporting><plugins>`, `reportSets` và tham số goal; xác minh output directories thay vì so hai lệnh như một.

### 14.5. “Đổi version/reportSet rồi site vẫn chứa HTML cũ”

**Nguyên nhân:** file `target/site` từ lượt chạy trước còn tồn tại hoặc build cache đã giữ output.

**Hướng sửa:** dùng `mvn clean site` để quan sát site mới trong thử nghiệm phù hợp; nếu report cần test XML, hãy chạy `mvn clean verify site` vì `clean` sẽ xóa XML cũ. Không xóa `target` giữa `verify` và `site` nếu site cần báo cáo test.

### 14.6. “Thêm `<pluginManagement>` mà plugin goal không chạy”

**Nguyên nhân:** `pluginManagement` **quản lý cấu hình**, không tự kích hoạt mọi goal.

**Hướng sửa:** thêm entry vào `build/plugins` và `executions` nếu muốn goal tự chạy, hoặc gọi goal trực tiếp. Một số goals có binding mặc định cho packaging; cần xem execution plan, không đoán.

### 14.7. “Thêm plugin vào `<build><plugins>` mà `mvn package` chưa tạo báo cáo”

**Nguyên nhân:** plugin đó có thể **không có goal được bind** vào default lifecycle của project. Riêng report goal có thể chỉ được site tích hợp khi khai trong `reporting`.

**Hướng sửa:** xác định mục đích: muốn **report cho site** thì dùng `reporting` và `mvn site`; muốn **build check** thì bind đúng goal/plugin vào phase phù hợp.

### 14.8. “Javadoc chỉ cần chạy `mvn site` trước `mvn test`”

**Nguyên nhân:** Javadoc có thể tạo từ Java source, nhưng Surefire HTML report cần test XML. Chạy `site` trước `test` có thể tạo site chưa đủ thông tin.

**Hướng sửa:** dùng `mvn clean verify site` nếu site cần các reports từ kết quả build/test của **cùng lượt**.

### 14.9. “`mvn site-deploy` báo 401/403 hoặc không có URL”

**Nguyên nhân:** thiếu `distributionManagement/site`, credentials không khớp server ID, server URL sai, không có quyền publish hoặc Wagon/protocol chưa cấu hình.

**Hướng sửa:** phân biệt **site publish** với **artifact publish**; kiểm tra URL/ID và quyền tối thiểu. Không dán token trong POM hoặc CI log.

### 14.10. “`mvn site` có trang mặc định ngoài ý muốn”

**Nguyên nhân:** default Project Info reports hoặc nhiều report goals mặc định của một reporting plugin.

**Hướng sửa:** dùng `<excludeDefaults>true</excludeDefaults>` khi thích hợp và `<reportSets>` để liệt kê những report cần thiết.

### 14.11. “Một plugin có hai nơi cấu hình khiến report khác nhau”

**Nguyên nhân:** plugin hỗ trợ build goals và report goals, trong khi `<build>` và `<reporting>` là các ngữ cảnh khác nhau; site có quy tắc merge riêng.

**Hướng sửa:** pin version, kiểm tra hiệu lực cấu hình bằng `help:effective-pom`, biết goal nào chạy từ site và goal nào chạy trực tiếp; đơn giản hóa cấu hình trùng lặp.

### 14.12. “Maven báo site thành công nhưng web khó mở bằng `file://`”

**Nguyên nhân:** browser giới hạn local files hoặc đường dẫn resource, links giữa module sites chưa được staging hoặc dùng đường dẫn absolute không phù hợp.

**Hướng sửa:** kiểm tra `target/site/index.html` và các assets, sau đó xem qua một local HTTP server/preview được phê duyệt nếu cần; với multi-module dùng site staging phù hợp. Đừng xem lỗi preview browser là lỗi compile Java.

## 15. Đọc execution plan và kiểm chứng đúng plugin đã chạy

Một POM có rất nhiều plugin entries nhưng điều bạn cần biết là **goal nào thực sự được Maven gọi**. Quy trình đáng tin:

**Bước 1 — xác định phiên bản môi trường:**

~~~bash
mvn -version
~~~

Ghi Maven core, JVM, OS. Đối với dự án có wrapper, dùng `./mvnw -version` (Windows: `.\mvnw.cmd -version`) thay vì đoán `mvn` toàn hệ thống.

**Bước 2 — xem effective POM:**

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Tìm `build/plugins`, `build/pluginManagement`, `reporting/plugins` và `reportSets`, nhất là những giá trị từ parent và active profiles. `-Dverbose=true` của Help Plugin được thiết kế để giúp truy vị trí nguồn model.

**Bước 3 — xem profile active:**

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
~~~

Profile có thể thêm hoặc bỏ plugin trong các điều kiện khác nhau, nên build local và CI có thể cho kết quả report khác nhau.

**Bước 4 — chạy mục tiêu cụ thể:**

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp site
~~~

Đọc log của từng goal. Tìm `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-jar-plugin` trong default lifecycle và `maven-site-plugin` cùng các reporting plugins khi tạo site.

**Bước 5 — đối chiếu file output:**

~~~text
maven-plugin-roles-demo-1.0.0.jar   -> artifact build
TEST-dev.example.CalculatorTest.xml -> dữ liệu kiểm thử
index.html                          -> trang site
apidocs/index.html                  -> Javadoc
surefire-report.html                -> trang HTML kết quả test
~~~

Tìm file trong đúng thư mục tương ứng và xem timestamp/content. Có file **không tự chứng minh** goal vừa chạy nếu output cũ chưa được dọn.

**Bước 6 — chỉ bật `-X` khi cần:**

~~~bash
mvn -X site
~~~

Debug có thể giúp xác định plugin version, execution và configuration, nhưng log rất dài và có thể chứa thông tin môi trường/repository/credentials. Lưu và chia sẻ có kiểm soát, không công bố nguyên log khi có dữ liệu nhạy cảm.

### Tự kiểm tra bằng file hệ thống

Linux/macOS:

~~~bash
test -f target/maven-plugin-roles-demo-1.0.0.jar && echo "JAR_EXISTS"
test -f target/site/index.html && echo "SITE_EXISTS"
test -f target/site/apidocs/index.html && echo "JAVADOC_EXISTS"
test -f target/site/surefire-report.html && echo "TEST_REPORT_EXISTS"
~~~

Các dòng in ra chỉ khi từng file tồn tại. Nếu build và site đều thành công với POM demo và output mặc định, kỳ vọng:

~~~text
JAR_EXISTS
SITE_EXISTS
JAVADOC_EXISTS
TEST_REPORT_EXISTS
~~~

Windows PowerShell:

~~~powershell
Test-Path .\target\maven-plugin-roles-demo-1.0.0.jar
Test-Path .\target\site\index.html
Test-Path .\target\site\apidocs\index.html
Test-Path .\target\site\surefire-report.html
~~~

Kết quả kỳ vọng của mỗi dòng là `True` nếu file tương ứng đã được tạo. Nếu Javadoc hoặc Test Report không có, xem log/reportSet/plugin version chứ không tự sửa tên file thành đường dẫn đoán trước.

## 16. Bài tập thực hành có đáp án

**Bài 1 — xác định vai trò.** `maven-compiler-plugin` nằm trong `build/plugins` và thực hiện `compiler:compile`. Nó là build plugin hay reporting plugin trong trường hợp này?

**Đáp án:** build plugin/goal; tạo bytecode của Java source phục vụ build, không phải trang site.

**Bài 2 — phân biệt hai lệnh.** Tại sao `mvn verify` PASS nhưng `target/site/index.html` chưa có?

**Đáp án:** `verify` thuộc default lifecycle, còn `site` thuộc site lifecycle. `<reporting>` không tự bind report vào `verify`.

**Bài 3 — chọn cấu hình đúng.** Bạn cần tạo trang Summary và Dependencies của Project Info, không cần Team/SCM. Dùng phần nào của POM?

**Đáp án:** `<reporting><plugins>` với `maven-project-info-reports-plugin` và `<reportSets>` chọn `summary`, `dependencies`. Khi cần loại các report mặc định không nằm trong danh sách, dùng `excludeDefaults` có chủ đích.

**Bài 4 — test vs test report.** Surefire Plugin làm gì? Surefire Report Plugin làm gì?

**Đáp án:** `surefire:test` chạy unit tests và tạo dữ liệu XML/TXT; Surefire Report Plugin đọc kết quả để tạo báo cáo HTML. `report-only` không chạy lại tests.

**Bài 5 — Javadoc có phải chỉ là reporting plugin?** Nếu bạn dùng `mvn javadoc:javadoc` mà không chạy `mvn site`, có thể sinh Javadoc không?

**Đáp án:** có. Một plugin có thể cung cấp goal gọi trực tiếp và report goals cho site; ngữ cảnh configuration và output có thể khác.

**Bài 6 — site-deploy.** Muốn publish JAR của project lên artifact repo, `mvn deploy` hay `mvn site-deploy`?

**Đáp án:** `mvn deploy` (project binary artifact). `mvn site-deploy` dành cho website tài liệu, cần `distributionManagement/site` phù hợp.

**Bài 7 — pluginManagement.** Parent chỉ khai `maven-shade-plugin` trong `pluginManagement`, module gọi `mvn package`. Có chắc tạo uber JAR không?

**Đáp án:** không. Phải có goal được sử dụng/bind phù hợp; quản lý version không tự tạo execution.

**Bài 8 — báo cáo sai/stale.** CI tạo Surefire HTML report nhưng test XML từ ngày trước. Có thể xem HTML là bằng chứng tests của commit hiện tại đã PASS không?

**Đáp án:** không. Cần gắn report vào test XML của cùng lần build và xác nhận `mvn verify` thành công; nếu build/test thất bại, phải bảo toàn trạng thái FAIL.

**Bài 9 — reportSet.** Nếu Site Plugin chạy, nhưng một reporting plugin được cấu hình `reportSet` chỉ chứa goal `dependencies`, nó có nhất thiết tạo `summary.html` không?

**Đáp án:** không phải từ report set đó. Các báo cáo mặc định hoặc plugin khác có thể vẫn tạo trang tương tự nếu chúng được bật; đọc `excludeDefaults` và toàn bộ cấu hình trước khi kết luận.

**Bài 10 — thực hành.** Chạy POM demo theo thứ tự `mvn clean verify` rồi `mvn site`. Liệt kê hai file chứng minh build/test và hai file chứng minh reporting.

**Đáp án gợi ý:** build/test: `target/maven-plugin-roles-demo-1.0.0.jar`, `target/surefire-reports/TEST-dev.example.CalculatorTest.xml`. Reporting: `target/site/index.html`, `target/site/apidocs/index.html` hoặc `target/site/surefire-report.html`.

## 17. Checklist chọn và quản lý plugins trong dự án

- [ ] Biết rõ **phần việc** muốn thực hiện: tạo sản phẩm, kiểm tra chất lượng hay xuất báo cáo.
- [ ] Phân biệt plugin, goal, execution và lifecycle phase.
- [ ] Pin phiên bản Maven plugins quan trọng; dùng Wrapper/parent POM khi cần tái lập.
- [ ] Đặt build goals và lifecycle executions dưới `<build><plugins>` khi phù hợp.
- [ ] Dùng `<build><pluginManagement>` để quản lý version/config, không mặc định nó tự chạy goals.
- [ ] Đặt reporting plugins dưới `<reporting><plugins>`, định version rõ ràng.
- [ ] Dùng `<reportSets>` để chọn report goals, tránh sinh báo cáo thừa.
- [ ] Hiểu `<excludeDefaults>` và default Project Info reports.
- [ ] Phân biệt Maven Site Plugin điều phối site và các reporting plugins tạo report content.
- [ ] Không nhầm `mvn verify` với `mvn site` hoặc `mvn deploy` với `mvn site-deploy`.
- [ ] Nếu report dùng Surefire/Failsafe/coverage inputs, đảm bảo dữ liệu nguồn được tạo trong đúng build.
- [ ] Tạo quality gates bằng build checking goals nếu muốn CI FAIL khi tiêu chí không đạt.
- [ ] Đã kiểm tra Javadoc/test report/site ở thư mục output thực tế.
- [ ] Nếu goal gọi trực tiếp cho kết quả khác site, đối chiếu `build` vs `reporting` configuration.
- [ ] Ở multi-module, xem đúng effective POM, report aggregation và site staging.
- [ ] Không đưa tokens/credentials hoặc thông tin nội bộ từ Maven debug/effective-settings lên site công khai.
- [ ] Sau khi chỉnh plugin/reportSet, kiểm tra bằng build sạch và site mới, tránh file cũ.
- [ ] Nếu nâng Maven core/plugin lớn, đọc compatibility/migration guide rồi chạy lại test và site.

## 18. Nguồn tham khảo Apache Maven

1. [Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html) — phân biệt build/report plugins, `executions`, `reportSets`, cấu hình trực tiếp và site.
2. [Available Maven Plugins](https://maven.apache.org/plugins/) — danh mục build plugins, reporting plugins và plugins hỗ trợ cả hai vai trò.
3. [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — default, clean, site lifecycles; phase và goal bindings.
4. [Apache Maven POM Reference](https://maven.apache.org/pom.html) — `build/plugins`, `pluginManagement`, `reporting/plugins`, `excludeDefaults` và `reportSets`.
5. [Apache Maven Site Plugin](https://maven.apache.org/plugins/maven-site-plugin/) — `site:site`, `site:deploy`, cấu hình reports và multi-module site.
6. [Maven Site Plugin 3.21.0 Documentation](https://maven.apache.org/plugins-archives/maven-site-plugin-3.21.0/plugin-info.html) — bản plugin dùng trong lab và yêu cầu Maven/JDK.
7. [Maven Project Info Reports Plugin](https://maven.apache.org/plugins/maven-project-info-reports-plugin/) — các report goals như `summary`, `dependencies` và `plugins`.
8. [Maven Project Info Reports — Selective Reports](https://maven.apache.org/plugins/maven-project-info-reports-plugin/examples/selective-reports.html) — `reportSets` để chọn reports.
9. [Maven Javadoc Plugin — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html) — Javadoc dưới `reporting` và khi gọi goal độc lập.
10. [Maven Surefire Report Plugin](https://maven.apache.org/surefire/maven-surefire-report-plugin/) — tạo HTML report từ XML results và phân biệt `report`/`report-only`.
11. [Maven Surefire Report Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-report-plugin/usage.html) — cấu hình reporting trong site.
12. [Guide to Developing Java Report Plugins](https://maven.apache.org/guides/plugin/guide-java-report-plugin-development.html) — một Maven plugin có thể triển khai goal thông thường và report goals.
