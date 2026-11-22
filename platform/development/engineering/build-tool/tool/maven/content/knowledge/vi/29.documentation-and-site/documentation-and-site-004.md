# Tạo báo cáo thông tin dự án, phụ thuộc và kết quả kiểm thử bằng Maven Site

## 1. Bài toán và kết quả cần đạt

Một dự án Java build thành công chưa đồng nghĩa nhóm phát triển, kiểm thử hoặc vận hành đã có đủ **thông tin để hiểu và đánh giá** bản build. Ngoài JAR/WAR cuối cùng, một quy trình chất lượng cần trả lời được: project có tọa độ gì, ai bảo trì, có những dependency nào, plugin nào tham gia build, bao nhiêu test được chạy và thất bại ở đâu.

Trong Maven, các mục tiêu này được xử lý bởi những thành phần liên quan nhưng không giống nhau:

- **Maven Site Plugin** tạo một website tài liệu/báo cáo tĩnh cho project, thường tại `target/site/`.
- **Maven Project Info Reports Plugin** tạo các trang thông tin project như summary, dependencies, dependency management, plugins, modules, SCM và developer/team khi POM có dữ liệu.
- **Maven Surefire Plugin** chạy unit tests trong phase `test` và tạo dữ liệu kết quả gốc, thường là `TEST-*.xml` và `*.txt` tại `target/surefire-reports/`.
- **Maven Surefire Report Plugin** đọc kết quả Surefire và tạo trang HTML dễ xem, có thể tích hợp vào Maven Site.
- **Maven Dependency Plugin** cung cấp các goal kiểm tra dependency graph và report về khai báo dependency đã dùng/chưa khai báo; nó bổ sung, không phải thay thế các trang Project Info.
- Nếu dự án có integration tests qua **Maven Failsafe Plugin**, dữ liệu `target/failsafe-reports/` có lifecycle và cách báo cáo riêng, không nên nhập nhằng với Surefire unit tests.

Bài Knowledge này tập trung vào cách cấu hình và **đọc đúng ý nghĩa** ba nhóm báo cáo: **thông tin dự án**, **phụ thuộc** và **kết quả kiểm thử**. Người học sẽ xây một project Java 17 có một dependency runtime, bốn JUnit 5 tests, tạo site HTML, kiểm tra XML tự động và hiểu các giới hạn của báo cáo khi đưa vào CI.

**Nguyên tắc chính:** HTML là giao diện trình bày; **POM hiệu lực, dependency graph được resolve, test XML mới của lần build và exit code Maven** mới là những bằng chứng cần đối chiếu khi đánh giá chất lượng.

## 2. Phân biệt build lifecycle và site lifecycle

Maven có nhiều lifecycle. Với project `packaging=jar`, **default lifecycle** xử lý compile, unit test, package, verify, install, deploy; còn **site lifecycle** liên quan tạo và phát hành tài liệu dự án. Hai nhóm không đồng nghĩa:

```bash
mvn -B test
mvn -B verify
mvn -B site
mvn -B clean verify site
```

Ý nghĩa điển hình:

| Lệnh | Chức năng chính | Đầu ra cần tìm |
| --- | --- | --- |
| `mvn test` | Compile và chạy unit tests qua Surefire theo bindings | `target/surefire-reports/TEST-*.xml` |
| `mvn verify` | Chạy default lifecycle tới verify, gồm unit test và packaging | JAR/WAR và test reports; integration checks nếu cấu hình |
| `mvn site` | Chạy site lifecycle để dựng website và reports đã khai báo | `target/site/index.html`, các trang HTML |
| `mvn clean verify site` | Dọn kết quả cũ, chạy QA, rồi tạo site | Dữ liệu test mới và trang site từ cùng workspace |

**`mvn site` không mặc nhiên thực hiện lại phase `test`.** Một số report goals có thể fork phase khác khi chạy, nhưng không được dựa vào điều đó thay cho pipeline kiểm thử chủ động. Nếu report plugin được cấu hình goal `report-only`, nó **không chạy test**, chỉ đọc file XML hiện có. Vì vậy workflow dễ kiểm chứng nhất là:

```bash
mvn -B clean verify
mvn -B site
```

Hai câu lệnh tách riêng giúp nhận biết chính xác lỗi ở bước compile/test hay ở bước render HTML. Khi cần một lệnh, `mvn -B clean verify site` có cùng ý định tuần tự. Không coi `BUILD SUCCESS` của riêng bước site là bằng chứng tests vừa pass nếu chúng không chạy trong job hiện tại.

### 2.1. Ba vị trí output khác nhau

```text
target/
├── classes/                  class/resource biên dịch
├── site/                     site HTML và report pages
│   ├── index.html
│   ├── summary.html
│   ├── dependencies.html
│   └── surefire-report.html
├── surefire-reports/          dữ liệu unit test gốc
│   ├── TEST-*.xml
│   └── *.txt
└── site-report-lab-1.0.0.jar artifact ứng dụng
```

Đây là **các file cần tìm**, không phải toàn bộ danh sách chắc chắn của mọi plugin version. Những report không được cấu hình sẽ không có trang tương ứng, và một vài trang có thể có tên khác giữa các phiên bản/plugin. `target/site` là **đầu ra tài liệu tĩnh**, không phải phần nội dung tự động được đưa vào main JAR.

## 3. Ba lớp dữ liệu cần phân biệt

| Lớp | Nguồn gốc | Dùng để làm gì | Giới hạn |
| --- | --- | --- | --- |
| Project metadata | `pom.xml` và effective POM | GAV, tên, mô tả, SCM, developers, licenses, plugin configuration | POM thiếu field thì báo cáo cũng thiếu |
| Dependency resolution | `<dependencies>`, `dependencyManagement`, transitive graph | Hiểu scope, versions, direct/transitive dependency | Không tự kết luận có CVE hay license được phép dùng |
| Test execution | Surefire/Failsafe XML, logs và Maven exit code | Số test chạy, failure/error/skipped, chi tiết lỗi | Report HTML không chứng minh dữ liệu XML mới |

Báo cáo hữu ích nhất khi dữ liệu của cả ba lớp đến từ **cùng source commit, cùng Maven/JDK, cùng dependency versions và cùng lần chạy CI**. Nếu site được dựng từ một workspace cũ còn `TEST-*.xml` của build trước, trang kiểm thử có thể hiển thị kết quả **không thuộc commit đang đánh giá**.

### 3.1. “Site xanh” không bằng “test xanh”

Đặc biệt dễ nhầm:

- `mvn site` có thể tạo HTML thành công dù phần test report trống.
- `surefire-report:report-only` có thể xuất trang từ XML cũ mà không chạy bất kỳ test nào.
- `-DskipTests` có thể làm packaging pass mà không tạo test results mới.
- Một trang Dependencies có thể được render thành công dù Maven graph chứa phiên bản có lỗ hổng bảo mật.
- Một test report hiển thị `0 failures` nhưng `0 tests` không chứng minh ứng dụng đã được kiểm thử.

Một QA gate nghiêm túc cần kiểm tra **số test tối thiểu/kỳ vọng**, **exit code của verify**, **tính mới của report** và sự tương ứng với artifact được publish.

## 4. Maven Site Plugin: bộ kết xuất website

**Maven Site Plugin** phối hợp Maven Reporting API và Doxia để tạo HTML từ tài liệu dự án và những reporting plugins được cấu hình trong POM. Phiên bản Maven Site Plugin `3.21.0` tương thích dòng Maven 3 theo tài liệu plugin; ví dụ bài dùng Maven 3.9.x và JDK 17.

Cấu hình version dưới `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-site-plugin</artifactId>
    <version>3.21.0</version>
</plugin>
```

Đây là **plugin build** để chọn site renderer/version. Nó không quyết định tất cả report pages sẽ có nội dung gì; danh sách báo cáo thường được khai báo riêng trong **`<reporting>`**.

### 4.1. Vai trò của reporting section

Khung cấu hình:

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
            <artifactId>maven-surefire-report-plugin</artifactId>
            <version>3.5.5</version>
        </plugin>
    </plugins>
</reporting>
```

Khung trên cho phép site renderer tìm các Maven reports tương ứng. Để tránh chạy một danh sách report rộng không cần thiết, nên dùng **`<reportSets>`** để chọn đúng các báo cáo phục vụ mục tiêu.

**Không nhầm `<build><plugins>` với `<reporting><plugins>`.** Surefire chạy test qua build lifecycle; Surefire Report hiển thị kết quả qua report rendering. Cùng một plugin có thể có goals dạng reporting, nhưng **khai báo ở build không tự thay thế reportSets**.

### 4.2. Nơi tạo website và cách mở

Từ project root:

```bash
mvn -B site
```

Output mặc định thường là:

```text
target/site/index.html
```

Mở `target/site/index.html` bằng trình duyệt hoặc một HTTP static server cục bộ nếu cần xem đầy đủ relative links/assets. Không cần phải deploy ra internet để xem website được sinh ở máy phát triển.

Đừng suy ra command này tự upload site. **`site` = tạo output cục bộ**; `site:deploy` liên quan phát hành site và yêu cầu site distribution config/credentials phù hợp. Trong bài thực hành **không dùng site:deploy**.

## 5. Project Info Reports Plugin: metadata và các mục trên website

Plugin `org.apache.maven.plugins:maven-project-info-reports-plugin:3.9.0` có các report goals tiêu biểu:

| Report ID trong reportSets | Trang/ý nghĩa thường gặp |
| --- | --- |
| `summary` | Project Summary: tên, mô tả, GAV, build info |
| `dependencies` | Dependencies: direct/transitive, scopes, licenses metadata, dependency tree |
| `dependency-info` | Maven coordinates ở dạng snippet dành cho consumers |
| `dependency-management` | Những dependencies được quản lý trong POM/effective model |
| `plugins` | Build Plugins của project |
| `plugin-management` | Managed Plugins |
| `modules` | Danh sách modules (hữu ích với aggregator) |
| `scm` | Source Code Management nếu POM khai báo |
| `team` | Developers/contributors nếu POM khai báo |
| `licenses` | Metadata license công bố trong POM |
| `issue-management` | Issue tracker configuration |
| `ci-management` | Continuous integration configuration |
| `distribution-management` | Artifact/site distribution info |
| `dependency-convergence` | Báo cáo hội tụ dependencies theo khả năng của plugin/version |

**`dependency-info` không phải `dependencies`:** nó cho người dùng những đoạn snippet tọa độ GAV để **khai báo dependency vào project**, còn `dependencies` mô tả **những dependencies mà project đang dùng**.

### 5.1. Chọn một số report thay vì kích hoạt tất cả

Ví dụ cấu hình để đưa đúng bốn trang project info lên Site:

```xml
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
                        <report>dependency-info</report>
                        <report>plugins</report>
                    </reports>
                </reportSet>
            </reportSets>
        </plugin>
    </plugins>
</reporting>
```

Đây là **đoạn reporting**, đặt đúng một lần dưới `<project>`. Nếu đã có reporting section, hợp nhất danh sách plugin/reportSet thay vì thêm hai `<reporting>` song song.

Lợi ích: output tập trung, thời gian site build có thể giảm, và người đọc không thấy các trang SCM/team/license trống khi dự án chưa khai báo thông tin đó.

### 5.2. Project Summary lấy dữ liệu từ đâu?

Ví dụ POM:

```xml
<groupId>demo.learning</groupId>
<artifactId>site-report-lab</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
<name>Site Report Lab</name>
<description>A Java 17 learning project with Maven reports.</description>
```

Trang Summary có cơ sở để hiển thị artifact coordinates và thông tin project. Nếu muốn báo cáo team/SCM/URL đầy đủ thì khai báo đúng những thông tin thật trong POM; đừng invent URL, email hoặc giấy phép chỉ để làm report có nhiều dòng.

**Summary là mô tả từ POM**, không phải báo cáo đo hiệu năng ứng dụng hay lịch sử test của mọi commit.

### 5.3. Dependencies page thể hiện gì?

Với dependency compile:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

và JUnit test:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.2</version>
    <scope>test</scope>
</dependency>
```

Trang Dependencies thường giúp quan sát compile/test scopes, direct/transitive dependencies và các thông tin do metadata POM của dependencies cung cấp. Cần phân biệt:

- **Direct dependency**: project khai báo trực tiếp trong `<dependencies>`.
- **Transitive dependency**: phụ thuộc của một dependency, được Maven Resolver đưa vào graph theo rules/scope.
- **`dependencyManagement`**: quản lý version/scope, **không tự thêm** artifact vào classpath.
- **Scope `test`**: dependency cần cho biên dịch/chạy test, không tự nằm trong artifact runtime của project.

Thông tin license mà trang report hiển thị phản ánh **POM metadata**, không phải kết luận legal audit, binary license scan hay security assessment. Không tuyên bố “an toàn” chỉ vì một trang Maven liệt kê `Apache-2.0`.

## 6. Dependency Plugin và Project Info: hai góc nhìn khác nhau

Maven Dependency Plugin có các goals dành cho CLI và reporting, ví dụ:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:list
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:analyze
```

- `dependency:tree`: hiển thị dependency tree Maven đã resolve; hữu ích khi tìm artifact transitive.
- `dependency:list`: liệt kê dependencies được resolve theo cấu hình goal.
- `dependency:analyze`: dùng phân tích bytecode để phân loại used/undeclared, unused/declared; có giới hạn với reflection, annotation processing, resources, service loading...
- `dependency:analyze-report`: một **Maven report** có thể đưa kết quả phân tích used/undeclared vào Site khi thêm vào `<reporting>`.

Các mục tiêu này khác với `project-info-reports:dependencies` là báo cáo tài liệu tổng quan về dependencies project.

### 6.1. Khi dependency tree và trang Dependencies khác cách trình bày

Một trang HTML có thể nhóm theo scope/metadata trong khi `dependency:tree` hiển thị cấu trúc cây. Khác nhau về bố cục **không tự chứng minh** Maven resolve các artifact khác. Để điều tra, phải kiểm tra:

- Có chạy ở **cùng module** hay không?
- Có cùng active profiles, settings, repositories không?
- Maven/JDK và plugin versions có giống không?
- Có file `pom.xml`/dependencyManagement được sửa giữa hai lệnh không?
- `test` dependencies có được đưa vào theo scope/report configuration không?

Khi cần đối chiếu, chạy cả hai trên cùng commit và cùng môi trường; không so báo cáo từ các lần build ngẫu nhiên.

### 6.2. Thêm analyze-report khi có nhu cầu

Đoạn cấu hình **tùy chọn**, không nằm trong POM runnable ở phần 10:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-dependency-plugin</artifactId>
    <version>3.6.1</version>
    <reportSets>
        <reportSet>
            <reports>
                <report>analyze-report</report>
            </reports>
        </reportSet>
    </reportSets>
</plugin>
```

Đặt plugin này **bên trong `<reporting><plugins>` hiện có**. Goal `analyze-report` có thể cần compile/test-compile output và thực hiện lifecycle fork phù hợp nếu dùng trực tiếp. Đừng cho rằng mọi lời cảnh báo “unused declared” là lỗi thật: dependency dùng bằng reflection, ServiceLoader hoặc công cụ framework có thể không hiện ra qua bytecode references.

Một report nói “used undeclared dependency” là tín hiệu cần sửa dependency declarations, nhưng phải kiểm chứng trong context. **Không xóa tùy tiện** các JAR chỉ vì analyzer không quan sát được static usage.

## 7. Surefire Plugin: dữ liệu kiểm thử gốc, không phải HTML site

Khi một project Maven `packaging=jar` chạy phase `test`, Maven thường dùng **Maven Surefire Plugin** để thực thi unit tests, bao gồm JUnit Jupiter khi plugin/dependency tương thích.

Ví dụ pin version:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.5</version>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
```

Thêm `failIfNoTests=true` trong dự án mẫu để **báo lỗi nếu không tìm thấy test**. Trên dự án aggregator `packaging=pom` hoặc module hợp lệ không có test, phải thiết kế rule phù hợp; không áp dụng flag mù ở parent cho mọi module nếu một số modules cố ý không có tests.

Dữ liệu sau `mvn test` thường nằm ở:

```text
target/surefire-reports/
├── TEST-demo.learning.site.GreetingServiceTest.xml
├── TEST-demo.learning.site.LauncherTest.xml
├── demo.learning.site.GreetingServiceTest.txt
└── demo.learning.site.LauncherTest.txt
```

Đây là **những file mô phỏng expected names** theo class/package của ví dụ; plugin có thể thêm logs, dump files, output redirection và các file khác tùy config/failure mode.

### 7.1. Một TEST-*.xml có các thành phần gì?

Đoạn XML minh họa **dạng dữ liệu**, không phải một file Surefire thật đầy đủ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="demo.learning.site.GreetingServiceTest"
           tests="3" errors="0" skipped="0" failures="0"
           time="0.015">
    <testcase name="greetsNormalizedName"
              classname="demo.learning.site.GreetingServiceTest"
              time="0.004"/>
    <testcase name="usesDefaultForBlank"
              classname="demo.learning.site.GreetingServiceTest"
              time="0.003"/>
    <testcase name="preservesUnicode"
              classname="demo.learning.site.GreetingServiceTest"
              time="0.003"/>
</testsuite>
```

Những attribute quan trọng:

| Thuộc tính/element | Ý nghĩa |
| --- | --- |
| `tests` | Số testcases được suite báo cáo |
| `failures` | Assert thất bại, thường có `<failure>` với stack trace |
| `errors` | Lỗi thực thi/khởi tạo, thường có `<error>` |
| `skipped` | Testcases bị bỏ qua theo trạng thái test provider |
| `time` | Thời lượng theo report, không luôn so trực tiếp giữa máy |
| `testcase` | Một test case trong suite; có name, classname và dữ liệu chi tiết |
| `system-out` / `system-err` | Console output nếu plugin ghi/thu, phải coi là dữ liệu nhạy cảm tiềm ẩn |
| `properties` | Thông tin runtime/test properties nếu được xuất, không tự mặc định an toàn để công khai |

Với failure, XML thường có nội dung stack trace trong `<failure>`/`<error>`. HTML report chuyển dữ liệu này thành giao diện đọc được, nhưng **không có công dụng chữa lỗi** hoặc tự tạo test mới.

### 7.2. Phân biệt fail và skipped

Một pipeline bắt buộc hiểu:

- **Passed:** testcase chạy và thành công.
- **Failure:** assertion không đúng.
- **Error:** lỗi thực thi/khởi tạo hoặc exception ngoài kỳ vọng.
- **Skipped:** testcase không được chạy.
- **No test:** không phát hiện testcase; không phải đồng nghĩa “toàn bộ test pass”.

Trong CI, mỗi loại cần được xử lý theo policy. `failures=0` và `errors=0` không đủ nếu `tests=0` hoặc số tests giảm đột ngột.

## 8. Surefire Report Plugin: dựng trang HTML từ XML

Plugin `org.apache.maven.plugins:maven-surefire-report-plugin` đọc `TEST-*.xml` và tạo báo cáo trình bày qua cơ chế Maven Reporting/Doxia.

Có hai goals quan trọng:

| Goal | Hành vi |
| --- | --- |
| `surefire-report:report` | Tạo HTML report; khi chạy trực tiếp có thể invoke lifecycle `test` theo mô tả goal |
| `surefire-report:report-only` | Tạo report từ những test results **đã có**, **không chạy lại tests** |
| `surefire-report:failsafe-report-only` | Tạo report cho integration tests của Failsafe từ output phù hợp, không chạy lại IT |

Với nhu cầu "chạy test, sau đó render HTML", lựa chọn rõ ràng là **`report-only`**. Điều này ngăn site generation âm thầm chạy thêm một lượt unit tests chỉ để tạo report.

### 8.1. ReportSet chỉ render kết quả hiện có

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-report-plugin</artifactId>
    <version>3.5.5</version>
    <reportSets>
        <reportSet>
            <reports>
                <report>report-only</report>
            </reports>
        </reportSet>
    </reportSets>
</plugin>
```

Đây là **đoạn cấu hình cho `<reporting><plugins>`**, không phải Surefire **test execution** plugin. Khi Site dựng report, nó sẽ dùng XML ở report directories phù hợp.

**Bẫy:** `report-only` không cho biết XML có mới không. Sau `mvn site`, nếu test results còn từ một commit cũ, trang vẫn có thể hiện `4 tests pass`. Vì vậy phải chạy `clean verify` trước trong cùng job hoặc có cơ chế xác minh report provenance.

### 8.2. Trang report nằm ở đâu?

Khi được render trong Maven Site, trang thường ở:

```text
target/site/surefire-report.html
```

Đây là expected filename với cấu hình phiên bản mẫu; nếu thay plugin versions hoặc output report name, kiểm tra kết quả `target/site` thực tế. Không nhầm `target/site/surefire-report.html` với dữ liệu máy đọc `target/surefire-reports/TEST-*.xml`.

### 8.3. report-only khác chạy standalone report

Có thể gọi trực tiếp một goal:

```bash
mvn -B org.apache.maven.plugins:maven-surefire-report-plugin:3.5.5:report-only
```

Nó không chạy unit tests. **Đường dẫn output khi chạy goal riêng** có thể không trùng hoàn toàn đường dẫn report trong Site vì report goal cấu hình outputDirectory theo cách gọi. Với project mẫu, lệnh chính để xem trang report có navigation hoàn chỉnh vẫn là `mvn -B site` sau `verify`.

## 9. Ba dạng thông tin đầu ra và cách chọn kênh tiêu thụ

| Nhu cầu | Đầu ra gợi ý | Người tiêu thụ |
| --- | --- | --- |
| Đọc tổng quan project | `target/site/summary.html` | Developer, reviewer, onboarding |
| Xem dependencies | `target/site/dependencies.html` | Maintainer, release reviewer |
| Copy Maven GAV cho project khác | `target/site/dependency-info.html` | Consumer của library |
| Xem build plugins | `target/site/plugins.html` | Người bảo trì build |
| Xem kết quả test dạng HTML | `target/site/surefire-report.html` | Developer và QA |
| Parse test result máy đọc | `target/surefire-reports/TEST-*.xml` | CI test reporter và scripts |
| Đọc nguyên nhân lỗi chi tiết | `target/surefire-reports/*.txt`, CI logs | Developer debug |
| Quan sát dependency tree | `dependency:tree` CLI output | Dev/CI/debug tool |
| Phân tích unused/undeclared dependency | `dependency:analyze` hoặc analyze-report | Maintainer |
| Đối chiếu artifact thực phát hành | `target/*.jar` và POM repository | Release pipeline |

**HTML phù hợp để đọc; XML phù hợp để máy tính tổng hợp; Maven exit code phù hợp làm điều kiện chặn build.** Không dùng HTML như một nguồn duy nhất để quyết định release.

## 10. Dự án Java 17 + Maven: đầy đủ POM, code và test

Dự án ví dụ tên `site-report-lab`; có một dependency compile để trang Dependencies không trống và JUnit Jupiter 5 để tạo hai test suites với tổng bốn cases.

Cấu trúc:

```text
site-report-lab/
├── pom.xml
├── src/
│   ├── main/java/demo/learning/site/
│   │   ├── GreetingService.java
│   │   └── Launcher.java
│   └── test/java/demo/learning/site/
│       ├── GreetingServiceTest.java
│       └── LauncherTest.java
└── tools/
    └── summarize-reports.py     (tạo nếu muốn parse XML bằng Python)
```

**Điều kiện:** JDK 17+, Maven 3.9.x, môi trường được phép truy cập Maven repository hoặc cache đã chuẩn bị, Python 3 chỉ dùng cho bước kiểm tra XML tùy chọn. Plugin/library versions được pin cho bài thực hành, **không coi là bản mới nhất** hay bảo đảm không có CVE ở mọi thời điểm.

### 10.1. POM hoàn chỉnh

Tệp `site-report-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.learning</groupId>
    <artifactId>site-report-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Site Report Lab</name>
    <description>A Java 17 learning project with Maven reports.</description>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
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
                <version>3.5.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-site-plugin</artifactId>
                <version>3.21.0</version>
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
                            <report>dependency-info</report>
                            <report>plugins</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-report-plugin</artifactId>
                <version>3.5.5</version>
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

**Giải thích POM:**

1. `packaging=jar` giúp Maven dùng default lifecycle để compile/test/đóng gói một JAR thông thường.
2. `commons-lang3` có scope mặc định `compile`, nên trang Dependencies có một dependency sản phẩm thực sự.
3. `junit-jupiter` scope `test` và Surefire 3.5.5 chạy JUnit Jupiter tests.
4. `maven.compiler.release=17` yêu cầu JDK hỗ trợ Java release 17; không cài JDK.
5. `maven-site-plugin` được pin trong `build` để tạo website.
6. `maven-project-info-reports-plugin` nằm trong `reporting` và chỉ được chọn bốn report IDs.
7. `maven-surefire-report-plugin` trong `reporting` được chọn `report-only` để dựng HTML từ XML **đã được tạo**.
8. `failIfNoTests=true` buộc đơn module này fail khi không tìm thấy test, tránh site hiện “0 test” mà build vẫn xanh.
9. Không khai báo SCM URL, developer email hay license giả; report chỉ hiển thị metadata mà POM thật có.
10. Không có plugin site deployment; tất cả output tạo tại `target/` và không công bố ra mạng.

### 10.2. GreetingService.java: sử dụng thư viện ngoài

Tệp `src/main/java/demo/learning/site/GreetingService.java`:

```java
package demo.learning.site;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(String rawName) {
        String normalized = StringUtils.trimToEmpty(rawName)
                .toLowerCase(Locale.ROOT);
        if (normalized.isBlank()) {
            return "Xin chào, bạn!";
        }
        return "Xin chào, "
                + StringUtils.capitalize(normalized) + "!";
    }
}
```

Code sử dụng một class từ `commons-lang3` để trim và capitalize chuỗi; như vậy dependency compile **thật sự được sử dụng**. Java 17 hỗ trợ `String.isBlank()` và `Locale.ROOT`.

Khi truyền `"  liNH  "`: trim → `"liNH"`, lowercase → `"linh"`, capitalize → `"Linh"`; phương thức trả chính xác `"Xin chào, Linh!"`.

### 10.3. Launcher.java: entrypoint quan sát stdout

Tệp `src/main/java/demo/learning/site/Launcher.java`:

```java
package demo.learning.site;

public final class Launcher {
    private Launcher() {
    }

    public static String message() {
        return GreetingService.greet("  liNH  ");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Dự án **không cấu hình Main-Class trong JAR manifest**, vì bài tập tập trung vào Site/Reports. Để chạy `Launcher`, truyền `-cp` và dependency JAR thật nếu cần. Unit tests Maven tự cung cấp classpath compile/test, không cần cấu hình `java -cp` thủ công để chạy test.

### 10.4. GreetingServiceTest.java: ba testcases

Tệp `src/test/java/demo/learning/site/GreetingServiceTest.java`:

```java
package demo.learning.site;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {
    @Test
    void greetsNormalizedName() {
        assertEquals("Xin chào, Linh!",
                     GreetingService.greet("  liNH  "));
    }

    @Test
    void usesDefaultForBlank() {
        assertEquals("Xin chào, bạn!",
                     GreetingService.greet("  "));
        assertEquals("Xin chào, bạn!",
                     GreetingService.greet(null));
    }

    @Test
    void preservesUnicode() {
        assertEquals("Xin chào, Ánh!",
                     GreetingService.greet("  ÁNH  "));
    }
}
```

Các test vừa minh họa logic và cho Surefire report dữ liệu có tên test rõ ràng. Test thứ hai chứa hai assertions nhưng vẫn là **một testcase JUnit**; số method có `@Test` mới quyết định số tests thông thường ở ví dụ này.

### 10.5. LauncherTest.java: testcase thứ tư

Tệp `src/test/java/demo/learning/site/LauncherTest.java`:

```java
package demo.learning.site;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LauncherTest {
    @Test
    void exposesExpectedMessage() {
        assertEquals("Xin chào, Linh!", Launcher.message());
    }
}
```

Có bốn `@Test` methods trên **hai test classes**. Với Maven/Surefire cấu hình ở POM mẫu, kết quả kỳ vọng:

```text
GreetingServiceTest: 3 tests
LauncherTest:        1 test
---------------------------
Total:               4 tests
Failures:            0
Errors:              0
Skipped:             0
```

Con số này chỉ là **expected QA**; bài Knowledge không khẳng định đã chạy Maven build thực tế trong workspace người dùng.

## 11. Thực hành: chạy test trước, dựng báo cáo sau

Từ thư mục project root:

```bash
mvn -version
mvn -B clean verify
```

Kiểm tra log:

- Compiler plugin đã biên dịch Java 17 không?
- Surefire plugin đã nhận diện `GreetingServiceTest` và `LauncherTest` không?
- Có **4 tests run**, failures/errors/skipped = 0 không?
- Maven có `BUILD SUCCESS` không?
- Có file `target/site-report-lab-1.0.0.jar` không?

Sau đó:

```bash
mvn -B site
```

Kiểm tra các tệp quan trọng:

```text
target/site/index.html
target/site/summary.html
target/site/dependencies.html
target/site/dependency-info.html
target/site/plugins.html
target/site/surefire-report.html
```

Đây là tên file dự kiến của **các report đã khai báo**, không bảo đảm site chỉ có đúng sáu file. Site Plugin thường sinh thêm CSS, images, JavaScript, metadata và navigation.

**Quan trọng:** chỉ mở HTML trong trình duyệt sau khi lệnh `mvn site` đã thành công; nếu không thấy trang, xem log của report plugin cụ thể thay vì giả định tất cả report plugins dùng cùng tên output.

### 11.1. Lấy thông tin chính từ từng trang

Trong `summary.html`, kỳ vọng thấy các định danh project:

```text
GroupId:    demo.learning
ArtifactId: site-report-lab
Version:    1.0.0
Type:       jar
```

Đây là **các giá trị cần đối chiếu**, không phải chuỗi HTML/display text cố định. Skin/localization có thể thay nhãn.

Trong `dependencies.html`, kiểm tra có `org.apache.commons:commons-lang3:3.14.0` với scope compile và `org.junit.jupiter:junit-jupiter:5.10.2` scope test, cùng transitive dependencies có thể xuất hiện theo cách Maven resolve.

Trong `dependency-info.html`, tìm snippet Maven coordinates `demo.learning:site-report-lab:1.0.0` để consumer tham chiếu project này. Nó **khác** danh sách dependency mà project đã khai báo.

Trong `plugins.html`, xem các build plugins hiện diện trong POM hiệu lực, ví dụ compiler/surefire/site, với versions tương ứng. Không lấy Plugins Report làm bằng chứng chắc chắn tất cả goals đã chạy; nó mô tả cấu hình/plugin metadata.

Trong `surefire-report.html`, kỳ vọng thấy **4 tests pass** chia trên hai classes. Trang có thể liệt kê thời lượng thực tế khác nhau giữa các lần chạy; không ghi một số milliseconds cố định vào tiêu chí chấm.

### 11.2. Kiểm tra source test XML trước khi tin trang HTML

```text
target/surefire-reports/TEST-demo.learning.site.GreetingServiceTest.xml
target/surefire-reports/TEST-demo.learning.site.LauncherTest.xml
```

Mở XML hoặc dùng chương trình ở phần 12. Nếu hai file XML không có, report HTML có thể trống hoặc dữ liệu không đúng kỳ vọng; cần sửa step `test`/test discovery trước khi sửa màu sắc Maven Site.

## 12. Kiểm tra XML tự động bằng Python 3

Dữ liệu XML phù hợp để CI tổng hợp số test, failure, error và skipped. Để tiện so sánh với HTML, tạo **tệp tùy chọn** `tools/summarize-reports.py`:

```python
from pathlib import Path
from xml.etree import ElementTree as ET

report_dir = Path("target/surefire-reports")
files = sorted(report_dir.glob("TEST-*.xml"))

if not files:
    raise SystemExit("ERROR: no Surefire TEST-*.xml files found")

totals = {
    "tests": 0,
    "failures": 0,
    "errors": 0,
    "skipped": 0,
}

for path in files:
    root = ET.parse(path).getroot()
    if root.tag != "testsuite":
        raise SystemExit(f"ERROR: unexpected root tag in {path}")
    for attribute in totals:
        totals[attribute] += int(root.attrib.get(attribute, "0"))

print(f"Suite XML: {len(files)}")
print(f"Tests: {totals['tests']}")
print(f"Failures: {totals['failures']}")
print(f"Errors: {totals['errors']}")
print(f"Skipped: {totals['skipped']}")

if totals["tests"] != 4 or any(
    totals[name] != 0
    for name in ("failures", "errors", "skipped")
):
    raise SystemExit("ERROR: test summary did not meet expected policy")
```

Từ project root, sau `mvn -B clean verify`:

```bash
python3 tools/summarize-reports.py
```

Trên Windows môi trường có Python launcher, có thể thay bằng:

```powershell
py -3 tools\summarize-reports.py
```

Với đúng hai suites và bốn testcase của dự án mẫu, stdout mong đợi:

```text
Suite XML: 2
Tests: 4
Failures: 0
Errors: 0
Skipped: 0
```

Script trả nonzero nếu không thấy XML, root XML sai, sai test count hoặc có failure/error/skipped ngoài chính sách. Nó là công cụ **QA bổ sung**, không phải Maven test provider. Nếu dự án có nested XML suites, test namespacing, custom Surefire provider/report schema hoặc plugin khác sinh test output, phải điều chỉnh parser phù hợp thay vì dùng script này như bộ đọc XML tổng quát.

### 12.1. Vì sao xác nhận số tests quan trọng?

Một đội có 200 tests mà vô tình đổi Surefire includes khiến chỉ 1 test chạy vẫn có thể thấy `0 failures`. Script ví dụ yêu cầu chính xác **4** vì project mẫu có bốn tests. Trong dự án thật nên đặt chính sách minimum count hoặc kiểm tra selected test suites theo quy định, và review khi test count giảm không có lý do.

### 12.2. Không parse nội dung XML không đáng tin bằng cấu hình yếu

`xml.etree.ElementTree` của Python thường phù hợp để đọc kết quả test được tạo bởi toolchain tin cậy trong CI. Nếu phải xử lý XML do bên ngoài gửi tùy ý, cân nhắc XML security policy, parser hardening và giới hạn kích thước; không biến một script báo cáo đơn giản thành dịch vụ parse dữ liệu không đáng tin mà không xét bảo mật.

### 12.3. Report XML có thể chứa thông tin nhạy cảm

Đừng upload công khai toàn bộ XML/TXT nếu tests in token, hostname nội bộ, đường dẫn chứa thông tin cá nhân hoặc environment variables. Dữ liệu `system-out`/`system-err`/stack trace có thể tiết lộ secrets. Hãy dùng CI artifact access controls và log redaction, và cấu hình tests không in thông tin nhạy cảm.

## 13. Chạy lớp main bằng classpath có dependencies

JAR Maven mặc định **không tự gộp Commons Lang**. Nếu bạn chỉ chạy:

```bash
java -cp target/classes demo.learning.site.Launcher
```

thì runtime có thể không tìm thấy `org.apache.commons.lang3.StringUtils` nếu không có dependency JAR trong classpath. Khi tests chạy, Maven/Surefire đã tự xây test classpath có Commons Lang và JUnit, nhưng Java launcher từ CLI không tự đọc `pom.xml`.

Cách dễ kiểm chứng là nhờ **Maven Dependency Plugin** ghi runtime classpath ra file:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath -Dmdep.outputFile=target/runtime-classpath.txt -Dmdep.includeScope=runtime
```

Goal `build-classpath` có các parameter theo plugin version; nên kiểm tra file được tạo trước khi dùng. Tệp `target/runtime-classpath.txt` chứa một chuỗi path theo hệ điều hành đến những dependency JAR đã resolve.

Để chạy chắc chắn đa nền tảng mà không ghép dấu phân cách sai, một lựa chọn đơn giản là dùng **Maven Exec Plugin** đã pin version và đặt `exec.classpathScope` cho CLI (ví dụ `org.codehaus.mojo:exec-maven-plugin`), nhưng trong bài này **không bắt buộc chạy main** để kiểm tra Site/Reports. Nếu muốn chạy thủ công, chọn classpath separator đúng với hệ điều hành:

Trên Linux/macOS (thay đường dẫn version/JAR thực tế):

```bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" demo.learning.site.Launcher
```

Trên Windows PowerShell (thay local repository path nếu cấu hình khác):

```powershell
java -cp "target\classes;$env:USERPROFILE\.m2\repository\org\apache\commons\commons-lang3\3.14.0\commons-lang3-3.14.0.jar" demo.learning.site.Launcher
```

Khi classpath đúng, stdout của riêng lệnh Java là:

```text
Xin chào, Linh!
```

Cách xây đường dẫn trong ví dụ giả định Maven local repository mặc định. Nếu settings đã thay localRepository, đừng copy nguyên lệnh mà không kiểm tra path. Để tạo **executable distribution** thực sự, phải thiết kế manifest/classpath hoặc packaging plugin phù hợp; bài này tập trung vào báo cáo build.

## 14. Kiểm tra dependencies bằng report và CLI cùng lúc

Trong project mẫu, hai dependencies direct là Commons Lang (compile) và JUnit Jupiter (test). Phần Site Dependencies giải thích graph theo cách trực quan; để điều tra sâu hơn, chạy:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Tùy phiên bản, output có dạng:

```text
demo.learning:site-report-lab:jar:1.0.0
+- org.apache.commons:commons-lang3:jar:3.14.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
   ... các artifact transitive khác ...
```

Đây là **sơ đồ rút gọn**, không phải stdout nguyên văn theo đúng số dấu gạch, và JUnit có thể kéo thêm Jupiter API/Engine/Platform. **Không hardcode** toàn bộ transitive tree nếu chưa resolve trên máy thực.

### 14.1. Project dependencies và license metadata

Project Info Dependencies page có thể hiển thị license metadata do POM dependencies khai báo. Khi điều tra license, phải phân biệt:

- License field trong POM của dependency.
- License của source/binary thực tế theo artifact version.
- Các transitive dependencies có license riêng.
- Policy của tổ chức và nghĩa vụ về notice/copyleft.
- CVE/security advisories, không nằm trong kết luận của Site report mặc định.

Một project có trang Dependencies đẹp **chưa được quét vulnerabilities**. Cần SBOM/SCA scanner nếu release policy yêu cầu, độc lập với việc site được render.

### 14.2. dependency-info là snippet dành cho consumer

Trang `dependency-info` thường đưa ví dụ:

```xml
<dependency>
    <groupId>demo.learning</groupId>
    <artifactId>site-report-lab</artifactId>
    <version>1.0.0</version>
</dependency>
```

Điều đó **không chứng minh** artifact đã được `deploy` lên repository mà consumer có quyền truy cập. Đây chỉ là tọa độ đúng để khai báo; người tiêu thụ còn cần artifact/POM thực sự được install/deploy và permission/resolution hợp lệ.

## 15. Phân biệt Surefire unit tests và Failsafe integration tests

Maven Surefire Plugin thường dành cho **unit tests** gắn vào phase `test`. Maven Failsafe Plugin dành cho integration tests, thường có các goals `integration-test` và `verify`. Hai loại có vị trí output khác nhau:

```text
target/surefire-reports/         unit tests
target/failsafe-reports/         integration tests
```

Nếu project chỉ dùng Surefire như ví dụ, không kỳ vọng tự có Failsafe HTML report. Nếu project thật dùng Failsafe, có thể thêm `maven-surefire-report-plugin` goal `failsafe-report-only` vào `<reporting>` hoặc tạo riêng theo plugin capabilities. **Phải chạy integration-test/verify thực sự trước khi render HTML**, vì goal report-only không chạy ITs.

### 15.1. Vì sao không dùng surefire-report để kết luận integration test pass?

Tên plugin "Surefire Report" dễ gây hiểu nhầm. Nó có thể render cả report về Failsafe qua goal chuyên biệt, nhưng dữ liệu unit tests và integration tests **không giống nhau**. Unit tests có thể pass trong khi môi trường container/database integration fail, hoặc ITs chưa được kích hoạt.

Trên CI, lưu riêng:

- Surefire TEST XML + HTML unit tests.
- Failsafe XML + HTML ITs khi có.
- Maven `verify` exit code, logs và artifacts.
- Môi trường test (JDK, database/container versions) và trạng thái test fixtures.

**Không cộng trùng testcase** từ Surefire và Failsafe nếu cùng test class bị cấu hình chạy ở hai plugin.

## 16. Multi-module Site: parent, module links và report outputs

Ví dụ Reactor:

```text
learning-parent/
├── pom.xml             packaging=pom
├── model/pom.xml       packaging=jar
├── core/pom.xml        packaging=jar
└── cli/pom.xml         packaging=jar
```

Khi chạy từ root:

```bash
mvn -B clean verify
mvn -B site
```

Maven có thể tạo **site của từng Maven project**, ví dụ:

```text
target/site/
model/target/site/
core/target/site/
cli/target/site/
```

Root site có thể có Modules report khi cấu hình Project Info Reports Plugin phù hợp. Các module con có dependencies/tests riêng; **đừng nhìn mỗi root `target/site/surefire-report.html` rồi kết luận mọi module đều có cùng số unit tests**.

### 16.1. Inheritance và aggregation khác nhau

- `<modules>` tập hợp modules vào Reactor.
- `<parent>` cho child kế thừa `reporting`, plugin versions và cấu hình khi không bị override.
- `<dependencies>` thể hiện Java artifact graph và ảnh hưởng dependency resolution.

Một root aggregator chứa `model`, `core`, `cli` nhưng các child dùng parent khác **không tự kế thừa** reporting section chỉ nhờ có tên trong `<modules>`.

### 16.2. Local links và site:stage

Tài liệu Maven Site Plugin cảnh báo liên kết giữa parent/child site có thể không hoạt động khi chỉ mở từng `target/site` trực tiếp vì **local directory layout khác deployed layout**. Khi cần kiểm thử điều hướng multi-module, dùng `site:stage` theo cách Maven plugin hướng dẫn, sau khi cấu hình site URL/distributionManagement cần thiết.

`site:stage` tạo bản local staging/mock để kiểm tra liên kết theo layout site triển khai; **không tự deploy**. Ngược lại `site:deploy` có thể phát hành lên server khi đã cấu hình credential/URL. Không dùng `site:deploy` chỉ để xác minh site có render đủ HTML.

### 16.3. Chỗ đặt báo cáo trong parent POM

Nếu muốn mọi child có những reports giống nhau:

```xml
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
```

Đặt section này vào **parent mà child thực sự kế thừa**. Những module packaging=pom không có tests có thể cần reporting policy riêng cho Surefire. Kiểm tra effective POM của từng module vì child có thể override reporting hoặc active profile.

## 17. Metadata quality: thông tin project cần khai báo có chủ đích

Project Info Reports phản ánh POM metadata. Một project có thể thêm các trường như:

```xml
<name>Example Service</name>
<description>A JVM component maintained by the team.</description>
<url>https://example.org/documentation</url>

<licenses>
    <license>
        <name>Apache License, Version 2.0</name>
        <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
    </license>
</licenses>
```

Đoạn trên **chỉ minh họa cú pháp**. Không được copy `example.org` hoặc tuyên bố license Apache-2.0 cho mã sản phẩm thật nếu dự án chưa có URL/license đó. Báo cáo project info có thể hiển thị dữ liệu thiếu hoặc sai nếu POM bị điền placeholder không được quản lý.

Các nhóm metadata khác có thể gồm:

- `<scm>`: source control URL và connection/developerConnection.
- `<developers>` / `<contributors>`: người bảo trì, chỉ điền thông tin được phép công khai.
- `<issueManagement>`: issue tracker.
- `<ciManagement>`: CI system và URL.
- `<distributionManagement>`: artifact repository và site deployment.
- `<organization>`, `<mailingLists>`, `<licenses>`: tùy project governance.

Không nên chèn email cá nhân, internal URL, token hoặc repository credentials vào báo cáo site được publish công khai. Nếu site là tài liệu nội bộ, vẫn áp dụng phân quyền và quy trình rà soát thông tin.

## 18. Doxia source content và site-generated reports

Maven Site không chỉ có báo cáo tự sinh. Có thể thêm tài liệu viết tay theo các định dạng được Doxia/Maven Site hỗ trợ, ví dụ một số tệp trong `src/site`. Tuy nhiên chúng là **tài liệu hướng dẫn**, còn Project Info/Surefire reports là **dữ liệu sinh bởi plugin**.

Mục tiêu bài này là tạo report được cập nhật theo POM và test execution, nên không bắt buộc có `src/site/site.xml` hoặc một cây tài liệu lớn. Những file tùy chỉnh có thể thêm sau khi báo cáo cơ bản chạy đúng.

**Đừng nhầm:** chỉ tạo `src/site/markdown/index.md` (nếu dùng định dạng hỗ trợ) không chứng minh Surefire XML tồn tại. Và chỉ cấu hình `<reporting>` không tự tạo một README riêng chi tiết về kiến trúc nếu không có source documentation.

### 18.1. site.xml là cấu hình trình bày/navigation

Tệp `src/site/site.xml` có thể điều khiển menus, skin, logo và links theo schema Maven Site Descriptor. Đây là cấu hình navigation, không phải nơi đặt Maven dependencies hoặc test cases.

Không cần thêm site.xml chỉ để xem bốn Project Info reports và một Surefire report. Khi cần custom navigation, tạo file hợp lệ cho Site Plugin version hiện dùng và kiểm tra rendered HTML/relative links.

## 19. CI pipeline: run tests rồi publish HTML

Một trình tự phù hợp cho một dự án Java:

```text
Checkout source commit
        │
        ▼
Chọn JDK/Maven/Wrapper từ cấu hình đã duyệt
        │
        ▼
mvn -B clean verify
        │
        ├─ Maven exit code
        ├─ Surefire TEST-*.xml + *.txt
        └─ target/*.jar
        │
        ▼
Kiểm chứng suite count, failures/errors/skipped
        │
        ▼
mvn -B site
        │
        ├─ target/site/summary.html
        ├─ target/site/dependencies.html
        ├─ target/site/plugins.html
        └─ target/site/surefire-report.html
        │
        ▼
Archive CI test report XML (máy đọc)
Archive Maven Site HTML (người đọc, phân quyền phù hợp)
        │
        ▼
Chỉ promote/publish artifact khi QA gates đạt
```

Maven có thể chạy `verify` rồi site trong một command, nhưng **CI thường nên tách bước** để báo rõ build/test lỗi hay report rendering lỗi và vẫn lưu test XML khi Maven `verify` thất bại.

### 19.1. Không chỉ upload website mà bỏ Surefire XML

Nhiều hệ thống CI có giao diện test trends, failed test list và lịch sử theo test suite dựa trên JUnit-format XML. HTML site khó tổng hợp theo hàng nghìn builds và có thể chứa resource links. Vì vậy nên giữ **hai artifact classes riêng**:

- **Máy đọc:** XML trong `target/surefire-reports/`, gồm log liên quan nếu policy cho phép.
- **Người đọc:** toàn bộ `target/site/`, không chỉ `index.html` vì các HTML khác cần CSS/images.

Không dùng `target/site` làm nguồn parse duy nhất để xác định failure count. Cũng không tự công khai file có stack trace/paths/secret values.

### 19.2. Chạy site khi verify fail?

Nếu `mvn verify` fail vì unit tests, mặc định pipeline có thể dừng trước Site. Để debug, vẫn có thể upload **Surefire XML và log** ở bước cleanup/finally của CI. Có thể render một báo cáo bổ sung từ XML đã ghi bằng goal `report-only` nếu workflow cho phép, nhưng không được biến việc render thành công thành job success khi tests fail.

Không cố chạy lại goal `surefire-report:report` có thể fork `test` rồi xóa/sửa bằng chứng đầu tiên. Khi điều tra thất bại, giữ log/report của lần failed run và các timestamp tương ứng.

### 19.3. Artifact version và provenance

Bản site cần gắn với commit, Maven version, JDK, POM và dependency versions đã dùng khi generate. Vì Project Info Reports đọc project model, một HTML site được upload sau khi source đã bị sửa nhưng test XML chưa làm mới có thể kể hai câu chuyện khác nhau.

Để audit, lưu cùng lần chạy:

- Source commit hash và branch/tag theo quy trình.
- Maven/JDK/toolchain versions.
- `mvn verify` exit status.
- XML test reports, Site HTML, JAR/WAR và POM.
- File hash của artifact/report bundle khi yêu cầu.
- Active profiles và dependency lock/policies nếu dự án có.

## 20. Kiểm tra output site một cách có hệ thống

Sau hai bước:

```bash
mvn -B clean verify
mvn -B site
```

đối chiếu các điều kiện:

| Điều kiện | Cách kiểm chứng | Kỳ vọng demo |
| --- | --- | --- |
| Test execution | Surefire XML + Maven logs | 4 testcases |
| Không có lỗi test | XML failures/errors | 0/0 |
| Không bỏ qua | XML skipped | 0 |
| Tổng suite | Danh sách TEST-*.xml | 2 |
| Site tồn tại | `target/site/index.html` | Có |
| Project info | `summary.html` | Có GAV demo |
| Dependencies | `dependencies.html` | Có Commons Lang/JUnit |
| Consumer coordinates | `dependency-info.html` | Có demo.learning:site-report-lab:1.0.0 |
| Plugin report | `plugins.html` | Có các build plugins |
| HTML test results | `surefire-report.html` | Có 4 tests pass |
| Main artifact | `target/site-report-lab-1.0.0.jar` | Có |
| Security/provenance | Rà soát data/report và chính sách CI | Không rò secrets |

Đây là **acceptance criteria** của ví dụ. Không chạy Maven ngay trong bài Knowledge, nên không khẳng định đã thực nghiệm các file này trên một máy cụ thể.

### 20.1. Kiểm tra một file HTML không bảo đảm website sử dụng được

Nếu chỉ copy `index.html` mà bỏ CSS/JS/images hoặc các trang liên kết, site có thể bị mất style, link hỏng hoặc thiếu nội dung. Khi lưu artifacts, archive **toàn bộ thư mục `target/site`**, nhưng chỉ sau khi rà soát thông tin nhạy cảm.

Nếu multi-module, thu thêm site của các child hoặc một bản staged site theo distribution policy. Không tự cho rằng root `target/site` chứa toàn bộ HTML/test data của mọi child.

### 20.2. Kiểm tra timestamp và stale files

`mvn clean` xóa `target` của project theo Clean Plugin, giúp giảm nguy cơ HTML/XML stale. Trong multi-module hoặc CI với workspace cache, cần đảm bảo cleanup bao phủ đúng tập module. Nếu chỉ chạy `-pl :one-module clean verify site` nhưng archive toàn bộ repository `**/target/site`, có thể lấy site cũ của modules không được chọn.

Một quy tắc đơn giản: artifact/report được upload phải có quan hệ rõ ràng với **module đã build ở run hiện tại**, không lấy file tồn tại trên disk làm bằng chứng.

## 21. Những lỗi phổ biến khi tạo Maven Site và báo cáo

| Triệu chứng | Nguyên nhân khả dĩ | Cách khoanh vùng |
| --- | --- | --- |
| Không có `target/site/index.html` | Chưa chạy `mvn site` hoặc plugin fail | Xem site plugin log, version, network/repository |
| Có site nhưng thiếu Dependencies | Không cấu hình Project Info Reports/reportSet hoặc report goal lỗi | Xem `<reporting>`, plugin version và Site log |
| `summary.html` thiếu metadata | POM thiếu name/description/SCM/team | Bổ sung thông tin **thật**, không invent |
| `dependency-info` chỉ có GAV | Đó là report snippet cho consumer, không phải dependency tree | Xem `dependencies.html` hoặc `dependency:tree` |
| Trang Dependencies không hiển thị expected artifact | Scope/profile/management khác hoặc resolution fail | Xem effective POM và dependency tree |
| `target/site/surefire-report.html` không có | Chưa cấu hình Surefire Report Plugin hoặc report goal fail | Đọc Site logs và reportSets |
| Surefire report HTML trống | Chưa có `TEST-*.xml`, test bị skip hoặc đường dẫn report khác | Chạy `mvn clean verify` rồi xem XML |
| HTML test báo PASS nhưng code mới chưa test | XML stale từ build cũ | Clean workspace và ràng report với commit hiện tại |
| `mvn site` thành công nhưng unit test fail trước đó | Site không thay thế test lifecycle | Dùng Maven verify exit code làm gate |
| Test count = 0 nhưng không fail | Surefire không discover test hoặc skip flags | Kiểm tra test class naming, provider, failIfNoTests |
| Có XML nhưng không có site HTML | Chưa chạy Site hoặc Surefire Report config thiếu | Chạy site với reporting plugin đã pin |
| `report-only` không tạo XML mới | Goal chỉ render data hiện có | Chạy phase `test` trước |
| `surefire-report:report` chạy test thêm lần | Goal có thể invoke test phase | Dùng `report-only` nếu đã có XML |
| Maven project report chậm | Quá nhiều report plugins/SCM fetch/dependency resolution | Chọn reportSets cần thiết, xem plugin logs |
| Site khác local/CI | Profiles, settings, Maven/JDK/plugin versions khác | Pin toolchain, ghi active profiles |
| Multi-module links hỏng khi mở local | Local site layout khác deployed layout | Dùng site:stage theo docs và site distribution config |
| Báo cáo root không có tests child | Mỗi module có site/Surefire output riêng | Thu đúng module sites và XML |
| Site deploy thất bại | Chưa có distributionManagement.site/credentials | Phân biệt site build với site deploy |
| Dependency analyze báo unused sai | Bytecode analyzer không thấy reflection/runtime usage | Review code/config, không xóa mù |
| License report có thiếu dữ liệu | Metadata dependency POM thiếu hoặc sai | Dùng license compliance tools chuyên dụng |
| Report thấy dependency có CVE? | Site reports không là security scanner | Thêm SCA/SBOM/security policy |
| XML chứa credentials | Test đã log secret/stack trace nhạy cảm | Redact và giới hạn quyền CI artifacts |
| Maven Site Plugin 4 không chạy trên Maven 3 | Không tương thích hệ Maven core/plugin version | Chọn plugin 3.x cho Maven 3, xem compatibility docs |
| Link report CSS bị thiếu khi upload | Chỉ upload một HTML thay vì toàn bộ site | Archive `target/site` như một thư mục |
| Chỉ có test TXT không có XML | Surefire config hoặc test provider/output path khác | Xem cấu hình report XML và logs |
| Maven verify có integration tests nhưng Site chỉ báo unit tests | Chưa cấu hình Failsafe report riêng | Thu `failsafe-reports` và report-only tương ứng |

### 21.1. Debug thứ tự nào hiệu quả?

1. Xem `mvn -version`: Maven/JDK nào đang chạy?
2. Xem `pom.xml` và effective POM: reporting plugins/versions/reportSets đúng chưa?
3. Chạy `mvn -B clean verify`: Surefire có chạy và tạo `TEST-*.xml` mới không?
4. Mở XML: test count/failure/error/skipped ra sao?
5. Chạy `mvn -B site`: plugin nào báo error?
6. Kiểm tra file HTML được tạo và relative links.
7. So Dependencies page với `dependency:tree` trong cùng environment.
8. Nếu multi-module, xem site của từng module và bố cục stage.
9. Xem CI artifact upload path, permissions và tính mới.
10. Nếu chuẩn bị release, kiểm tra security/provenance, không chỉ UI report đẹp.

Đừng khắc phục một test suite không được discover bằng cách sửa menu HTML. Vấn đề phải giải quyết ở **lifecycle/test provider** trước.

## 22. Site Plugin 3.x và Maven 4: lưu ý tương thích

Maven Site Plugin có các dòng version khác nhau. Với **Maven 3**, sử dụng dòng Maven Site Plugin 3.x tương thích; ví dụ pin `3.21.0`. Những thay đổi về Doxia, Maven Reporting API và Maven Site Plugin 4.x có thể yêu cầu Maven runtime khác.

Khi đổi toolchain, kiểm tra:

- Maven version, JDK version và yêu cầu tối thiểu của Site Plugin.
- Project Info Reports Plugin version có hoạt động với Site Plugin đang dùng không?
- Surefire Report Plugin version có render được Surefire XML theo version test plugin không?
- Report IDs có bị đổi hoặc deprecated không? `dependency-info` chẳng hạn có lộ trình đổi tên trong tài liệu Project Info Reports.
- Site skin/Doxia configuration có làm thay navigation/report links không?
- Nếu multi-module, site staging/deploy layout có khác không?

**Không lấy một cấu hình Maven 3 sang Maven 4 mà không kiểm chứng**. Một báo cáo Site có thể lỗi do build tool/reporting API không tương thích dù Java code vẫn compile.

## 23. Tối ưu lựa chọn báo cáo theo đối tượng đọc

### 23.1. Người mới tham gia dự án

Nên đưa các trang:

- Summary: GAV, name/description, cách tìm source.
- Dependencies: các thư viện, scope và dependency tree.
- Plugins: hiểu cách build Java/test/site.
- Surefire Report: biết phần nào được kiểm thử.
- Một README hoặc tài liệu kiến trúc viết tay nếu cần bối cảnh nghiệp vụ.

Không bắt buộc bật mọi report goal cho một onboarding Site.

### 23.2. Người bảo trì dependencies

Cần Dependencies page và dependency tree CLI, thêm dependencyManagement/convergence khi phù hợp, nhưng phải đối chiếu với POM hiệu lực, version mediation, security scanners và module-specific dependencies.

Một report `unused declared` không tự mang nghĩa “có thể xóa ngay”. Thư viện dùng qua reflection/annotation processor hoặc class loading có thể không được static analyzer nhận ra.

### 23.3. QA/CI engineer

Cần Surefire XML gốc, Failsafe XML nếu có, Maven exit code, test count trend, failures/skipped, JDK/version và HTML chỉ như giao diện đọc.

Một Site có `4 tests pass` là ảnh chụp của **một build cụ thể**, không bảo đảm đã có regression coverage đầy đủ hay test mới nhất nếu provenance không rõ.

### 23.4. Release/Compliance reviewer

Cần artifact metadata, POM được phát hành, dependency graph, license/security audit riêng, checksum và report access control. Maven Site là tài liệu hỗ trợ, không thay tool ký số, SCA hoặc chính sách phê duyệt.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** `mvn site` có tự bảo đảm unit tests mới được chạy không?

**Đáp án:** Không. Phải chạy test/verify chủ động và đảm bảo report chỉ đọc XML của run hiện tại. `report-only` không thực thi tests.

**Câu 2.** `project-info-reports:dependency-info` và `project-info-reports:dependencies` khác nhau thế nào?

**Đáp án:** Dependency-info hiển thị snippet tọa độ Maven cho consumer khai báo project này; Dependencies report liệt kê và mô tả thư viện mà project đang phụ thuộc.

**Câu 3.** Surefire `TEST-*.xml` nằm ở đâu trong dự án đơn module mặc định?

**Đáp án:** Thường ở `target/surefire-reports/`, không phải `target/site/`.

**Câu 4.** `report-only` hiển thị 4 tests pass có chứng minh 4 tests vừa chạy trên commit này không?

**Đáp án:** Không. XML có thể là file cũ. Cần `clean verify` và ràng test reports với CI run/commit hiện tại.

**Câu 5.** Trong POM mẫu, test class có ba methods `@Test` nhưng bốn assertions. Surefire đếm mấy tests cho class này?

**Đáp án:** Ba testcases trong trường hợp JUnit 5 bình thường, vì testcase count không bằng số assertions.

**Câu 6.** Một Project Dependencies page chứa license `Apache-2.0` có đủ chứng minh dependency không có CVE không?

**Đáp án:** Không. License metadata không phải vulnerability analysis; cần công cụ/policy bảo mật riêng.

**Câu 7.** Lệnh `mvn site:deploy` có phù hợp để chỉ kiểm tra HTML local không?

**Đáp án:** Không. Nó có thể cần distributionManagement và quyền publish; dùng `mvn site` để dựng local rồi xem `target/site`.

## 25. Checklist trước khi bàn giao Maven Site và test reports

- [ ] Project POM có GAV, name/description và metadata cần thiết, không có placeholder URL/email bịa?
- [ ] Maven Site Plugin version tương thích Maven/JDK đang sử dụng?
- [ ] `<reporting>` có đúng Project Info Reports Plugin và reportSets cần thiết?
- [ ] Surefire Plugin chạy unit tests ở phase `test` và tạo `TEST-*.xml`?
- [ ] Surefire Report Plugin ở `reporting` dùng `report-only` khi muốn tránh chạy lại tests?
- [ ] `mvn -B clean verify` chạy trên đúng source commit và không skip?
- [ ] Số test, failures, errors, skipped đã đối chiếu với XML mới?
- [ ] `mvn -B site` tạo `target/site/index.html` và các HTML đã khai báo?
- [ ] Trang Summary có GAV đúng, Dependencies chứa đúng direct/transitive graph?
- [ ] Đã phân biệt Dependency-info snippet dành cho consumer với dependency tree?
- [ ] Report HTML và XML đến từ cùng build/version, không có stale reports?
- [ ] Nếu là multi-module, đã thu báo cáo của các child và kiểm link stage?
- [ ] Nếu có Failsafe ITs, báo cáo riêng của integration tests đã được tạo/kiểm tra?
- [ ] Không kết luận an toàn bản quyền/bảo mật chỉ từ Dependencies/licenses metadata?
- [ ] CI lưu XML và logs ngay cả khi verify fail, không biến site render pass thành test pass?
- [ ] Báo cáo HTML được archive cùng assets và có access control phù hợp?
- [ ] Test output không làm rò token, dữ liệu cá nhân hoặc nội dung nội bộ nhạy cảm?
- [ ] Có thông tin commit, JDK/Maven versions và artifact provenance để tái tạo báo cáo?
- [ ] Trước khi publish public site hoặc artifact release đã qua review và policy tương ứng?

**Kết luận:** Maven Site kết nối **thông tin dự án**, **dependency reports** và **kết quả unit tests** thành website HTML dễ đọc. Project Info Reports mô tả POM/GAV/graph; Surefire tạo XML kiểm thử; Surefire Report hiển thị XML đó dưới dạng HTML. Quy trình đáng tin là **chạy `clean verify` trên source hiện tại → kiểm tra Surefire XML và exit code → chạy `site` → đối chiếu từng trang HTML → lưu report artifacts với provenance rõ ràng**. Đừng đánh đồng “site tạo được” với “test pass” hoặc “dependency an toàn”; những kết luận đó cần bằng chứng và công cụ riêng.

### Tài liệu chính thức

- [Apache Maven Site Plugin — Usage](https://maven.apache.org/plugins/maven-site-plugin/usage.html)
- [Apache Maven Site Plugin 3.21.0 — Plugin Info](https://maven.apache.org/plugins-archives/maven-site-plugin-3.21.0/plugin-info.html)
- [Apache Maven Project Info Reports Plugin — Plugin Info](https://maven.apache.org/plugins/maven-project-info-reports-plugin/plugin-info.html)
- [Project Info Reports — Run Selective Reports](https://maven.apache.org/plugins/maven-project-info-reports-plugin/examples/selective-reports.html)
- [Project Info Reports — Dependencies Goal](https://maven.apache.org/plugins/maven-project-info-reports-plugin/dependencies-mojo.html)
- [Project Info Reports — Dependency Info Goal](https://maven.apache.org/plugins/maven-project-info-reports-plugin/dependency-info-mojo.html)
- [Maven Surefire Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-plugin/usage.html)
- [Maven Surefire Report Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-report-plugin/usage.html)
- [Maven Surefire Report — report-only Goal](https://maven.apache.org/surefire-archives/surefire-3.5.5/maven-surefire-report-plugin/report-only-mojo.html)
- [Maven Dependency Plugin — Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
