# Tổng hợp tài liệu cho dự án nhiều mô-đun bằng Maven Site

Trong một dự án Java nhiều Maven modules, tài liệu không còn nằm trong một chỗ: mỗi module có source code, API Javadoc, báo cáo dependency, kết quả kiểm thử và hướng dẫn sử dụng riêng. Ở cấp root, nhóm phát triển thường muốn có **một bộ tài liệu thống nhất**: trang giới thiệu, sơ đồ kiến trúc, menu chuyển giữa modules, các báo cáo Maven và **Javadoc tổng hợp** của các public API.

Maven hỗ trợ nhu cầu này thông qua **Maven Site Plugin**, **Doxia/Site Renderer**, **Maven Javadoc Plugin** và các **reporting plugins**. Nhưng một "Maven reactor nhiều mô-đun" không tự đồng nghĩa "một website đã tổng hợp xong".

Ba thao tác cần phân biệt:

1. **Aggregate Maven projects:** root `pom.xml` dùng `<modules>` để thu thập và build nhiều projects trong một reactor. Đây là mô hình build, chưa phải báo cáo HTML.
2. **Sinh sites cho từng module:** chạy `mvn site` tại root, Maven tạo site ở `target/site` của root và từng child project. Các thư mục output **vẫn tách biệt**.
3. **Ghép site để preview và tạo reports tổng hợp:** `site:stage` đưa các module sites vào một cây local có cấu trúc tương tự khi publish; những goal như `javadoc:aggregate` tạo **một báo cáo Javadoc từ nhiều Java modules**.

**Điểm dễ sai nhất:** sau `mvn site`, liên kết tương đối từ root site sang child site có thể hỏng khi mở trực tiếp các file `target/site/index.html`. Apache Maven giải thích rằng cấu trúc build output khác cấu trúc deployed site; **`site:stage` là bước phù hợp để kiểm tra navigation của toàn dự án**.

Bài học này trình bày đầy đủ từ khái niệm, cấu hình POM/reporting/site descriptor, Java 17 lab hai modules, Javadoc aggregate, staging/deployment, đến vấn đề CI/CD, tài liệu sinh tự động, kiểm tra liên kết và các lỗi thực tế.

## 1. Bức tranh tổng thể: build, report, site, stage

Giả sử repository:

```text
multi-site-lab/
├── pom.xml                  # parent + aggregator
├── greeting-api/
│   ├── pom.xml
│   └── src/main/java/...
└── greeting-app/
    ├── pom.xml
    └── src/main/java/...
```

Reactor giải quyết thứ tự build theo quan hệ `greeting-app -> greeting-api`. Site Plugin được chạy trên những modules trong invocation sẽ sinh HTML của từng project. Javadoc aggregate có thể đọc source/API của nhiều modules để tạo một tập Javadoc chung.

```text
Maven Reactor
  |
  +-- parent pom              -- site --> root/target/site/
  |
  +-- greeting-api jar        -- site --> greeting-api/target/site/
  |                                \
  |                                 \  Javadoc của api
  |
  +-- greeting-app jar        -- site --> greeting-app/target/site/
                                   \
                                    \ Javadoc của app

Sau đó: site:stage
    root site + module sites + report outputs
          |
          v
      local staging tree
          |
          +-- index.html
          +-- greeting-api/index.html
          +-- greeting-app/index.html
          +-- ... Javadoc/report pages ...
```

Sơ đồ mô tả nguyên lý. Tên đường dẫn sau stage phụ thuộc `distributionManagement.site`, inheritance và `topSiteURL`; hãy đọc log thực tế thay vì mặc định mọi dự án có cùng path.

### 1.1. Site Plugin không thay default build lifecycle

Các phase `compile`, `test`, `package`, `verify`, `install` và `deploy` thuộc **default lifecycle**. Site Plugin được gọi qua site lifecycle hoặc goals riêng.

| Lệnh | Ý nghĩa chính | Có tạo site HTML không? |
| --- | --- | --- |
| `mvn clean verify` | Xóa output cũ, compile, chạy tests, kiểm tra đến verify | Không mặc định |
| `mvn install` | Build và cài binary/POM vào local repository | Không mặc định |
| `mvn deploy` | Deploy binary/POM qua Maven default lifecycle | Không mặc định |
| `mvn site` | Sinh site và reports của modules | Có |
| `mvn site:stage` | Dựng cây site xem thử từ output đã có | Không tự sinh lại tất cả input site |
| `mvn site:deploy` | Công bố tài liệu theo `distributionManagement.site` | Có side effect publication |
| `mvn site:stage-deploy` | Công bố site đến staging location được cấu hình | Có thể là remote staging |
| `mvn javadoc:aggregate` | Sinh báo cáo API tổng hợp | Chỉ Javadoc, không toàn bộ site |

**Không nhầm `mvn deploy` và `mvn site:deploy`.** Một lệnh nhắm đến Maven artifact repository, lệnh kia nhắm đến site hosting/URL. Chúng có thể yêu cầu credentials và quy trình release khác nhau.

### 1.2. Aggregator khác parent

- **Aggregator:** `<modules>` điều phối những projects thuộc build.
- **Parent POM:** `<parent>` trong child cho phép kế thừa properties, pluginManagement, reporting và metadata.
- **Project dependency:** `<dependencies>` diễn đạt app thực sự sử dụng JAR của api; `<modules>` **không tự đưa classes lên classpath**.

Một root có thể vừa là parent vừa là aggregator, như lab. Nhưng trong workspace thực, parent và aggregator có thể là hai POM khác nhau. Khi reports/plugin config không xuất hiện ở child, hãy xem `effective-pom` và parent reference thay vì chỉ nhìn modules list.

## 2. Những thành phần tạo nên site

Maven Site dùng các nguồn dữ liệu khác nhau:

| Nguồn | Vị trí ví dụ | Kết quả |
| --- | --- | --- |
| Metadata project | `pom.xml`: `name`, `description`, modules | Tên site, Project Info pages |
| Tài liệu Markdown | `src/site/markdown/*.md` | HTML pages tùy chỉnh |
| Tài liệu APT/FML/XDoc | `src/site/apt`, `fml`, `xdoc` | HTML theo Doxia markup |
| Site descriptor | `src/site/site.xml` | Skin, menus, navigation |
| Static assets | `src/site/resources/images`/`css` | Images, CSS |
| Reporting plugins | `<reporting><plugins>` | Dependency/Javadoc/other reports |
| Build outputs | `target/classes`, generated sources | Input cho một số Javadoc reports |
| Site staging | `site:stage` | Cây thư mục HTML xem thử |

**Doxia** thực hiện rendering markup vào HTML theo Site Plugin. Một Markdown extension riêng của GitHub không chắc được Doxia hỗ trợ giống hệt. Cần preview đúng generated HTML, đặc biệt bảng, heading anchors, code blocks, Unicode và links.

### 2.1. Mapping source files sang HTML

Với Maven Site Plugin 3.22.0, một số mappings thông thường:

```text
src/site/markdown/index.md             -> target/site/index.html
src/site/markdown/architecture.md      -> target/site/architecture.html
src/site/apt/release-notes.apt          -> target/site/release-notes.html
src/site/fml/faq.fml                    -> target/site/faq.html
src/site/resources/images/logo.png     -> target/site/images/logo.png
```

Những directories `src/site/markdown`, `apt`, `fml`, `xdoc` và `resources` là conventions của Site Plugin. Không cần tạo tất cả nếu dự án chỉ dùng Markdown.

### 2.2. Reporting khác build/plugins

```xml
<build>
    <plugins>
        <!-- plugins phục vụ compile, test, package, goals -->
    </plugins>
</build>

<reporting>
    <plugins>
        <!-- plugins sinh báo cáo phục vụ Maven Site -->
    </plugins>
</reporting>
```

Đây là snippet minh họa. Một Maven Javadoc Plugin trong `build/plugins` có thể hỗ trợ goals gọi trực tiếp, nhưng **muốn chọn các reports hiển thị trong site**, cần cấu hình reporting/`reportSets` đúng. `pluginManagement` chỉ quản lý version/config của plugin khi được sử dụng, không tự buộc site aggregate mọi report.

### 2.3. Site menu chỉ trỏ tới content thật

Site descriptor có các menu đặc biệt:
- `<menu ref="modules"/>`: links đến các child module sites.
- `<menu ref="parent"/>`: link đến parent site khi có parent phù hợp.
- `<menu ref="reports"/>`: links đến reports đã được sinh.
- `<menu name="...">`: những links do bạn tự định nghĩa.

**Menu được tạo không đồng nghĩa target đã tồn tại.** Nếu bạn thêm `<item href="architecture.html">` ở descriptor root rồi cho child kế thừa descriptor mà child không có `architecture.md`, link trên child có thể hỏng. Nên phân biệt navigation chung và navigation riêng từng module.

## 3. Site riêng từng module và staging tree

Khi chạy:

```bash
mvn -B -ntp site
```

ở root, sites thường nằm tại:

```text
target/site/                         # root
greeting-api/target/site/            # API module
greeting-app/target/site/            # app module
```

Đây là output paths **tính từ root hiện tại**. Vì mỗi site ở một thư mục `target/site` riêng, relative links giữa chúng có thể chưa phù hợp.

Sau khi hoàn tất generation:

```bash
mvn -B -ntp site:stage
```

Site Plugin dựng local staging tree, mặc định thường ở `target/staging` của aggregator hoặc directory được cấu hình. Staging giúp bạn bấm links như khi sites được publish. Goal **không upload** HTML đến remote theo nghĩa của `site:deploy`.

### 3.1. `site:stage` khác `site:stage-deploy`

`site:stage` là local preview; `site:stage-deploy` triển khai tới một **staging URL**, có thể remote. Đừng chạy stage-deploy để "xem thử" khi chưa biết nó sẽ ghi vào host/repository nào.

Site Plugin `site:stage` có các options:
- `stagingDirectory`: đường dẫn local absolute khi muốn đặt ở vị trí khác.
- `topSiteURL`: điều chỉnh top distribution-management site URL dùng để tính đường dẫn module nếu auto calculation không phù hợp.
- `inputDirectory`: site/report output directory; mặc định dựa trên `project.reporting.outputDirectory`.
- `skip`/`skipDeploy`: các cờ bỏ qua khi thật sự cần theo policy.

**Không đổi `stagingDirectory` lung tung trong reactor** khiến nhiều modules ghi vào cùng một shared path từ các goals không có ý định chạy aggregate. Dùng cấu hình được document và kiểm tra log.

### 3.2. Site publish và binary publish là hai release streams

`distributionManagement.repository` và `distributionManagement.site` là hai trường khác nhau:

```xml
<distributionManagement>
    <repository>
        <id>release-repository</id>
        <url>https://repo.example.invalid/releases</url>
    </repository>
    <site>
        <id>documentation-host</id>
        <url>https://docs.example.invalid/multi-site-lab</url>
    </site>
</distributionManagement>
```

Đây là **ví dụ để giải thích**, không phải endpoints thật. Domain `example.invalid` có chủ đích không hoạt động; **không chạy deploy tới các URLs minh họa**. Binary repository nhận JAR/POM, site hosting nhận HTML, images, CSS và report pages. Từng stream cần quyền, kiểm thử và rollback thích hợp.

## 4. Javadoc riêng và Javadoc tổng hợp

Một module Java có thể sinh Javadoc riêng qua `javadoc:javadoc` hoặc report `javadoc-no-fork`. Aggregator cần Javadoc chứa public API của nhiều modules.

| Goal | Input/mục đích | Cần lưu ý |
| --- | --- | --- |
| `javadoc:javadoc` | Source của một project | Có thể fork generate-sources khi dùng report |
| `javadoc:javadoc-no-fork` | Javadoc của một project | Cần source/generated inputs đã có |
| `javadoc:aggregate` | API Javadoc cho nhiều modules | Có thể kích hoạt compile lifecycle bổ sung |
| `javadoc:aggregate-no-fork` | Aggregate Javadoc không fork compile | Chạy compile/install trước |
| `javadoc:test-javadoc` | Test source Javadoc của module | Khác public main API |
| `javadoc:test-aggregate` | Javadoc tổng hợp test sources | Cần test source roots |
| `javadoc:aggregate-jar` | Gói tài liệu tổng hợp thành JAR | Không phải site:stage |

Theo Apache Maven Javadoc Plugin, từ version **3.1.0**, aggregate reports có thể được tạo ở **nhiều cấp trong reactor**. Nếu muốn chỉ một aggregate report ở root, tạo report set với `<inherited>false</inherited>`.

```xml
<reportSet>
    <id>aggregate</id>
    <inherited>false</inherited>
    <reports>
        <report>aggregate-no-fork</report>
    </reports>
</reportSet>
```

Đây là trích đoạn reportSet. Nó không phải lệnh executable đơn lẻ.

### 4.1. Vì sao chọn aggregate-no-fork?

Nếu chạy build và site trong CI, goal aggregate tiêu chuẩn có thể yêu cầu chạy `compile` lại, kích hoạt code generation/Enforcer/những executions khác lần nữa. `aggregate-no-fork` tránh vòng compile bổ sung nhưng **chỉ hoạt động đúng khi sources/classes cần thiết đã được tạo trước**.

Workflow hợp lý:

```bash
mvn -B -ntp clean install
mvn -B -ntp site site:stage
```

`install` trong lab chỉ cài artifacts vào local Maven repository; không publish ra remote. Nó giúp các Maven report goals cần internal dependencies resolve đúng version.

### 4.2. Maven module không đồng nghĩa JPMS named module

`<modules>` trong POM là Maven reactor structure. `module-info.java` của Java 9+ là JPMS descriptor. Nếu sử dụng named modules, aggregate Javadoc có các hạn chế module path, package export/readability và Automatic-Module-Name. Lab dùng Java 17 **không có `module-info.java`**, tập trung Maven multi-module và plain Java packages.

### 4.3. API documentation khác binary compatibility test

Javadoc build thành công chứng minh khả năng tạo tài liệu từ source, **không chứng minh public API tương thích với version trước**. Khi một library được xuất bản cho consumer khác, có thể cần Revapi/japicmp, contract tests và release notes. Reports không thay thế các quality gates đó.

## 5. Lab Java 17: hai Maven modules, một tài liệu tổng hợp

Cấu trúc file cần tạo:

```text
multi-site-lab/
├── pom.xml
├── src/site/
│   ├── site.xml
│   └── markdown/
│       ├── index.md
│       └── architecture.md
├── greeting-api/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/site/api/Greeter.java
│       ├── test/java/dev/training/site/api/GreeterTest.java
│       └── site/markdown/index.md
└── greeting-app/
    ├── pom.xml
    └── src/
        ├── main/java/dev/training/site/app/Main.java
        ├── test/java/dev/training/site/app/MainTest.java
        └── site/markdown/index.md
```

**Lab chạy với** JDK 17+, Maven 3.9.x, Maven Site Plugin 3.22.0, Maven Javadoc Plugin 3.12.0, Maven Project Info Reports Plugin 3.9.0, Maven Fluido Skin 2.1.0, Compiler 3.14.1, Surefire 3.6.1 và JUnit Jupiter 5.11.4.

Bộ phiên bản này là **baseline được ghim cho ví dụ**, không phải khẳng định tất cả đều mới nhất vào thời điểm hiện tại. Cần Maven Central hoặc mirror được phép nếu những artifacts đó chưa nằm trong local cache.

### 5.1. Tạo thư mục

Linux/macOS:

```bash
mkdir -p multi-site-lab/src/site/markdown
mkdir -p multi-site-lab/greeting-api/src/main/java/dev/training/site/api
mkdir -p multi-site-lab/greeting-api/src/test/java/dev/training/site/api
mkdir -p multi-site-lab/greeting-api/src/site/markdown
mkdir -p multi-site-lab/greeting-app/src/main/java/dev/training/site/app
mkdir -p multi-site-lab/greeting-app/src/test/java/dev/training/site/app
mkdir -p multi-site-lab/greeting-app/src/site/markdown
cd multi-site-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "multi-site-lab/src/site/markdown" | Out-Null
New-Item -ItemType Directory -Force -Path "multi-site-lab/greeting-api/src/main/java/dev/training/site/api" | Out-Null
New-Item -ItemType Directory -Force -Path "multi-site-lab/greeting-api/src/test/java/dev/training/site/api" | Out-Null
New-Item -ItemType Directory -Force -Path "multi-site-lab/greeting-api/src/site/markdown" | Out-Null
New-Item -ItemType Directory -Force -Path "multi-site-lab/greeting-app/src/main/java/dev/training/site/app" | Out-Null
New-Item -ItemType Directory -Force -Path "multi-site-lab/greeting-app/src/test/java/dev/training/site/app" | Out-Null
New-Item -ItemType Directory -Force -Path "multi-site-lab/greeting-app/src/site/markdown" | Out-Null
Set-Location multi-site-lab
```

Các lệnh sau giả định working directory là `multi-site-lab`. Tạo đủ từng file dưới đây rồi mới chạy Maven.

## 6. Root POM đầy đủ: `multi-site-lab/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.site</groupId>
    <artifactId>multi-site-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <name>Multi-Module Documentation Lab</name>
    <description>Maven Site and aggregate Javadoc example</description>

    <modules>
        <module>greeting-api</module>
        <module>greeting-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <distributionManagement>
        <site>
            <id>docs-demo</id>
            <url>https://docs.example.invalid/multi-site-lab</url>
        </site>
    </distributionManagement>

    <build>
        <pluginManagement>
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
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-site-plugin</artifactId>
                    <version>3.22.0</version>
                </plugin>
            </plugins>
        </pluginManagement>
        <plugins>
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
                        <id>selected-project-info</id>
                        <reports>
                            <report>summary</report>
                            <report>modules</report>
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
                        <id>aggregate</id>
                        <inherited>false</inherited>
                        <reports>
                            <report>aggregate-no-fork</report>
                        </reports>
                    </reportSet>
                    <reportSet>
                        <id>default</id>
                        <reports>
                            <report>javadoc-no-fork</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
        </plugins>
    </reporting>
</project>
```

**Các điểm thiết kế cần hiểu:**
- Root có `packaging=pom`, vừa aggregator vừa là parent của children.
- `<modules>` thu thập hai projects; dependency giữa chúng phải được khai báo riêng trong app POM.
- `project.reporting.outputEncoding` bảo vệ tiếng Việt trong docs HTML; source files cần được lưu UTF-8 thật.
- Compiler, Surefire, JAR Plugin versions được ghim trong `pluginManagement`.
- Site Plugin cũng được khai báo ở `build/plugins` để gọi site goals với version ổn định.
- `reporting` chọn project reports và Javadoc. `excludeDefaults=true` giảm các default reports không có chủ đích.
- Report set aggregate có `inherited=false`; child site không tự chạy aggregate tương tự.
- Site URL `example.invalid` chỉ dùng làm **địa chỉ logic cho stage**. **Không thực hiện `site:deploy` đến URL này.**

**Quan trọng:** root POM là một project packaging `pom`, nên nó không sinh JAR từ Java source. Child `greeting-api` và `greeting-app` mới là `jar` projects.

## 7. Site descriptor đầy đủ: `src/site/site.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<site xmlns="http://maven.apache.org/SITE/2.1.0"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://maven.apache.org/SITE/2.1.0
                          https://maven.apache.org/xsd/site-2.1.0.xsd"
      name="Multi-Module Documentation Lab">

    <skin>
        <groupId>org.apache.maven.skins</groupId>
        <artifactId>maven-fluido-skin</artifactId>
        <version>2.1.0</version>
    </skin>

    <body>
        <menu name="Tài liệu">
            <item name="Giới thiệu" href="index.html"/>
        </menu>
        <menu ref="modules"/>
        <menu ref="parent"/>
        <menu ref="reports"/>
    </body>
</site>
```

Đây là **site descriptor v2**: `<site>` là root, namespace `SITE/2.1.0`. Cấu trúc legacy `<project xmlns="...DECORATION/1.x">` dùng trong một số tutorials cũ có thể được hỗ trợ với deprecation warning, nhưng không nên trộn hai schemas.

**Skin có version tường minh.** Maven Site Guide hiện đại yêu cầu một skin trong descriptor hoặc thừa kế từ parent. Ghim `maven-fluido-skin:2.1.0` giúp output không âm thầm thay đổi theme theo repository metadata.

Site descriptor kế thừa sang child phải cẩn thận với relative href. Trong lab menu chung chỉ có `index.html` — root và hai children đều có index tương ứng — nên link chung không trỏ tới một trang chỉ có ở root. `<menu ref="modules"/>` dành cho root có children; `<menu ref="parent"/>` hữu ích ở child; `reports` link những reports thực tế đã sinh.

### 7.1. Cú pháp menu hiện hành

```xml
<menu ref="modules"/>
<menu ref="parent"/>
<menu ref="reports"/>
```

Apache Maven khuyến nghị `ref` thay cho cú pháp cũ dùng `${modules}`/`${parent}`/`${reports}` như macro trong descriptor. Các ref entries không tự nhập nội dung tài liệu; renderer chỉ tạo links tới targets có thể có.

### 7.2. Lỗi inherited navigation

Đừng thêm vào site descriptor dùng chung:

```xml
<menu name="Tài liệu">
    <item name="Kiến trúc" href="architecture.html"/>
</menu>
```

nếu chỉ root có `architecture.md`. Khi child kế thừa menu, URL `architecture.html` trỏ vào site child có thể không tồn tại. Tạo child-specific menu, điều chỉnh inheritance, hoặc đặt link tới kiến trúc **trong root index** như lab.

## 8. Các tệp Markdown site của lab

Tệp **`src/site/markdown/index.md`**:

```markdown
# Multi-Module Documentation Lab

Đây là tài liệu tổng hợp cho hai Maven modules.

## Modules

- **greeting-api**: public API định dạng lời chào.
- **greeting-app**: ứng dụng sử dụng greeting-api.

Dùng menu **Modules** để chuyển giữa các module,
và **Project Reports** để xem báo cáo Maven.

Xem [kiến trúc dự án](architecture.html).

## Build và tài liệu

Lệnh từ root:

- `mvn clean install`
- `mvn site site:stage`

Sau đó kiểm tra Javadoc của `Greeter` và `Main`.
```

Tệp **`src/site/markdown/architecture.md`**:

```markdown
# Kiến trúc

Root `multi-site-lab` là parent/aggregator packaging `pom`.

`greeting-api` đóng gói thư viện public class `Greeter`.
`greeting-app` khai báo Maven dependency tới `greeting-api`.

Maven Site Plugin sinh site cho root và từng module.
Project Info Reports Plugin tạo báo cáo từ metadata của POM.
Maven Javadoc Plugin tạo Javadoc của từng module và báo cáo aggregate.

Dùng `site:stage` để kiểm tra liên kết giữa module sites.
Tài liệu sau deploy phải tương ứng cùng source commit và release version.
```

Tệp **`greeting-api/src/site/markdown/index.md`**:

```markdown
# Greeting API

Public Java API của module: `dev.training.site.api.Greeter`.

Method `Greeter.format(String)` nhận tên người dùng,
loại khoảng trắng ở hai đầu và tạo câu chào.

Ví dụ:

- Input: `"  Maven  "`
- Output: `"Hello, Maven!"`

Truy cập menu Project Reports để xem Javadoc/API của module.
```

Tệp **`greeting-app/src/site/markdown/index.md`**:

```markdown
# Greeting App

Ứng dụng CLI phụ thuộc `greeting-api:1.0.0`.

Java main class: `dev.training.site.app.Main`.

Từ root sau khi `mvn clean install` thành công,
chạy với cả hai thư mục class:

`java -cp "greeting-app/target/classes:greeting-api/target/classes" dev.training.site.app.Main`

Trên Windows, dùng dấu `;` giữa các classpath entries.

Stdout:

`Hello, Site!`

Trang Project Reports cung cấp các thông tin Maven của module này.
```

Đây là **nội dung đầy đủ của bốn tệp Markdown**, không phải bash scripts. Khi tạo file thật, tên file/đường dẫn khớp cấu trúc; những dấu inline code trong bài được biểu diễn bằng Markdown backticks.

### 8.1. Không trỏ vào `target/site` từ nội dung publish

`target/site` là **đường dẫn trên máy build**, không phải một URL được người xem website sử dụng sau deployment. Viết link `../../greeting-api/target/site/index.html` trong tài liệu là sai mô hình. Các links cross-module phải theo **staged/deployed structure** và nên được kiểm tra với `site:stage`.

## 9. API module: POM và Java code

### 9.1. `greeting-api/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.site</groupId>
        <artifactId>multi-site-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-api</artifactId>
    <packaging>jar</packaging>
    <name>Greeting API</name>
    <description>Library defining greeting messages</description>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Child nhận version/compiler/reporting/site plugin configuration từ root parent. `greeting-api` không phụ thuộc `greeting-app`; graph không vòng.

### 9.2. `Greeter.java` — có Javadoc public API

Tệp **`greeting-api/src/main/java/dev/training/site/api/Greeter.java`**:

```java
package dev.training.site.api;

/**
 * Tạo lời chào chuẩn hóa cho một tên người dùng.
 *
 * <p>Lớp là public API của module greeting-api.</p>
 */
public final class Greeter {

    private Greeter() {
    }

    /**
     * Trả về câu chào cho tên đã bỏ khoảng trắng hai đầu.
     *
     * @param name tên hợp lệ, không null và không chỉ có khoảng trắng
     * @return chuỗi theo mẫu "Hello, NAME!"
     * @throws IllegalArgumentException nếu name rỗng hoặc null
     */
    public static String format(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

Class và method đều `public`, vì vậy Javadoc Plugin có public API để đưa vào per-module/aggregated report, với `@param`, `@return` và `@throws` rõ ràng.

### 9.3. `GreeterTest.java` — 2 unit tests

Tệp **`greeting-api/src/test/java/dev/training/site/api/GreeterTest.java`**:

```java
package dev.training.site.api;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {

    @Test
    void trimsWhitespace() {
        assertEquals("Hello, Maven!", Greeter.format("  Maven  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
            () -> Greeter.format("   "));
    }
}
```

Surefire chạy hai JUnit tests trong lifecycle `test`. Chúng xác minh behavior trước khi build documentation; **site generation không thay unit test execution**.

## 10. Application module: phụ thuộc nội bộ thật

### 10.1. `greeting-app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.site</groupId>
        <artifactId>multi-site-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-app</artifactId>
    <packaging>jar</packaging>
    <name>Greeting App</name>
    <description>CLI using greeting-api</description>

    <dependencies>
        <dependency>
            <groupId>dev.training.site</groupId>
            <artifactId>greeting-api</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Quan trọng:** có `greeting-api` trong root `<modules>` chưa khiến app import được `Greeter`. Chính `<dependency>` ở đây tạo classpath và reactor sorting relationship. `greeting-app` build sau `greeting-api`.

### 10.2. `Main.java`

Tệp **`greeting-app/src/main/java/dev/training/site/app/Main.java`**:

```java
package dev.training.site.app;

import dev.training.site.api.Greeter;

/**
 * Chương trình ví dụ sử dụng module greeting-api.
 */
public final class Main {

    private Main() {
    }

    /**
     * In lời chào ra standard output.
     *
     * @param args tham số CLI, không được sử dụng trong demo
     */
    public static void main(String[] args) {
        System.out.println(Greeter.format("Site"));
    }
}
```

Ứng dụng chỉ dùng `Greeter` từ API module. Dù build qua Maven reactor, JAR output của greeting-app **không tự gộp** greeting-api JAR như Shade/Assembly; Java launcher cần runtime classpath phù hợp.

### 10.3. `MainTest.java` — 1 unit test

Tệp **`greeting-app/src/test/java/dev/training/site/app/MainTest.java`**:

```java
package dev.training.site.app;

import dev.training.site.api.Greeter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {

    @Test
    void usesApiModule() {
        assertEquals("Hello, Site!", Greeter.format(" Site "));
    }
}
```

Lab có **3 unit tests tổng cộng**: 2 API tests và 1 application test, JUnit Jupiter 5.11.4. Các class names khớp Surefire naming convention.

## 11. Build trước, sinh site sau

Từ root `multi-site-lab`:

```bash
mvn -version
mvn -B -ntp clean install
```

Khi build thành công:
1. Maven xử lý root POM project.
2. Biên dịch `greeting-api`, chạy 2 tests, tạo JAR, install local.
3. Biên dịch `greeting-app` với dependency API, chạy 1 test, tạo JAR, install local.
4. Reactor Summary báo thành công các projects.
5. Generated class outputs và internal artifacts sẵn sàng cho reporting goals.

**Thứ tự build mong đợi:**

```text
multi-site-lab
greeting-api
greeting-app
```

Tên hiển thị có thể lấy từ `<name>` của POM. Đây là thứ tự logic, không phải toàn bộ Maven console output.

**Thống kê unit test dự kiến:**

```text
greeting-api: Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
greeting-app: Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Đây là diễn giải số tests mong đợi, không phải nguyên văn dòng log của một build cụ thể. Nếu plugin/repository tải lỗi thì không thể coi tests đã chạy.

### 11.1. Chạy Java application để kiểm chứng

Linux/macOS:

```bash
java -cp "greeting-app/target/classes:greeting-api/target/classes" dev.training.site.app.Main
```

Windows PowerShell:

```powershell
java -cp "greeting-app\target\classes;greeting-api\target\classes" dev.training.site.app.Main
```

**Stdout chính xác của Java main:**

```text
Hello, Site!
```

Không cần JUnit trên runtime classpath, vì nó nằm ở test scope. Không chạy `java -jar greeting-app/target/greeting-app-1.0.0.jar` rồi kết luận Maven Site hỏng: JAR chưa có `Main-Class` manifest và chưa gộp dependency greeting-api.

## 12. Generate và stage trang tài liệu

Sau khi `mvn clean install` thành công:

```bash
mvn -B -ntp site
mvn -B -ntp site:stage
```

Hoặc gộp một invocation:

```bash
mvn -B -ntp site site:stage
```

Không thêm `-N` ở root nếu cần site của children, vì `-N` (non-recursive) bỏ qua những child modules. Không dùng `-pl :greeting-app` rồi báo "tài liệu toàn reactor đã được tổng hợp", vì subset selection có thể loại site của API hoặc root.

### 12.1. Sau `mvn site`

Các đường dẫn thường có:

```text
target/site/index.html
target/site/architecture.html

greeting-api/target/site/index.html
greeting-app/target/site/index.html
```

Ngoài ra, báo cáo Project Info và Javadoc do `<reporting>` sinh có thể có các HTML pages/dirs khác theo phiên bản plugin và reportSets.

**Chưa nên coi isolated root `target/site/index.html` là preview chính thức của cross-module navigation.** Mỗi child vẫn nằm dưới directory riêng.

### 12.2. Sau `site:stage`

Với cấu hình site URLs của lab, staging tree thường có hình thức gần như:

```text
target/staging/
    index.html
    architecture.html
    greeting-api/
        index.html
    greeting-app/
        index.html
    ... generated reports, Javadoc, CSS/images ...
```

Đây là **sơ đồ minh họa**: output location và module subdirectories cuối cùng phải đối chiếu với `site:stage` logs. Khi site URL/`topSiteURL` khác convention, cấu trúc có thể thay đổi.

Mở trang `index.html` trong staging và kiểm tra:
- Root giới thiệu dự án và link `architecture.html`.
- Menu Modules có Greeting API/Greeting App.
- Trang child có link Parent nếu được renderer tạo.
- Project Reports liên kết tới reports thực sự tồn tại.
- Javadoc của `Greeter.format` có phần parameter/return/throws đúng.
- CSS/images của skin được tải.
- Các links nội bộ không báo 404.
- Site không chứa secrets, private URLs hoặc tài liệu không được phép công khai.

**Chỉ kiểm tra file tồn tại là chưa đủ**. Staging có thể sinh index thành công nhưng JavaDoc report lỗi/rỗng, menu trỏ sai hoặc Unicode bị sai.

### 12.3. Đường dẫn cross-module cần kiểm tra sau stage

Một link giữa hai module thường dựa trên URL site sau publication, không phải filesystem `target/site`. Nếu dùng URL absolute bắt đầu bằng `/`, phải lưu ý path prefix của website, ví dụ khi docs host ở `/project/v1.0.0/`. Nếu URL root thay đổi, relative paths có thể cần regenerate để đúng.

**Không sửa broken links bằng cách thêm `target/site` vào Markdown** — đó là path build local, không phải web route.

## 13. Javadoc aggregate report và inheritance

POM root của lab đã chứa:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <reportSets>
        <reportSet>
            <id>aggregate</id>
            <inherited>false</inherited>
            <reports>
                <report>aggregate-no-fork</report>
            </reports>
        </reportSet>
        <reportSet>
            <id>default</id>
            <reports>
                <report>javadoc-no-fork</report>
            </reports>
        </reportSet>
    </reportSets>
</plugin>
```

Đây là **trích đoạn của root POM hoàn chỉnh**, không copy lại như plugin thứ hai. Ý nghĩa:

- `javadoc-no-fork`: khi được inherit vào children, tạo API docs từng project.
- `aggregate-no-fork` ở root: tổng hợp public Java API của reactor modules, với `inherited=false` tránh chạy lại aggregate report tại mỗi child.
- `reportSets`: chọn rõ báo cáo cần tạo, không dùng mặc định tất cả goals của Javadoc Plugin.

### 13.1. Tại sao tổng hợp Javadoc có thể chậm?

Javadoc Plugin goal `aggregate` thường có khả năng fork compile lifecycle; nếu code generation hoặc Enforcer/plugin executions chạy trong compile phase, site build có thể kéo theo nhiều hành động nữa. Với CI đã hoàn thành `mvn clean install` trước, `aggregate-no-fork` tránh lặp compile. **Nhưng nếu workspace sạch không có compiled/generated inputs, no-fork có thể thiếu thông tin để báo cáo**.

### 13.2. Public API và test docs

`Greeter.java` có Javadoc `@param`/`@return`/`@throws` cho public method. `GreeterTest.java` nằm trong test source và thường không nằm trong main Javadoc report. Muốn test docs, dùng goals `test-javadoc`, `test-aggregate` hoặc `test-aggregate-no-fork` trong workflow phù hợp.

Đừng publish test docs chứa private fixture data, token, hostnames hoặc chi tiết implementation không được phép công khai.

### 13.3. Javadoc aggregate và JPMS

Nếu dự án Java 17 có `module-info.java`, Javadoc có thể sử dụng JPMS module path, và aggregate reports chịu ràng buộc named/unnamed modules. Khi đó cần xem hướng dẫn Maven Javadoc Plugin về modularized projects; có thể cần `Automatic-Module-Name` hoặc packaged JAR theo tình huống. Lab không có `module-info.java`, nên minh họa Maven reactor multi-module chứ không phải module system của Java.

## 14. Project Info Reports trong nhiều mô-đun

Maven Project Info Reports Plugin có goals như:
- `summary`: tổng quan project.
- `modules`: child modules của aggregator.
- `dependencies`: dependencies của project được báo cáo.
- `dependency-management`: thông tin dependencyManagement.
- `plugins`/`plugin-management`: build plugin metadata.
- `scm`/`team`/`licenses`/`ci-management`: metadata bổ sung nếu POM khai báo.

**Không hiểu `dependencies` report ở root là "toàn bộ transitive dependencies của mọi module".** Root `packaging=pom` có thể không có project dependencies runtime; report ở root phản ánh root model. Muốn xem dependency của `greeting-app`, vào **site/report của greeting-app**.

Chỉ bật reports có mục đích. Lab chọn `summary`, `modules` và `dependencies` bằng reportSet tường minh, tránh tạo hàng loạt trang rỗng khi không có SCM/team/issue tracker metadata.

### 14.1. ReportSet không phải build execution

```xml
<reportSet>
    <id>selected-project-info</id>
    <reports>
        <report>summary</report>
        <report>modules</report>
        <report>dependencies</report>
    </reports>
</reportSet>
```

ReportSet cho Site Plugin biết các report goals cần render. Nó **không phải** execution bind vào `compile` hoặc `verify`. `mvn verify` không tự tạo HTML site chỉ bởi phần `reporting`.

### 14.2. Những báo cáo "aggregate" khác

Có những use cases yêu cầu:
- **JaCoCo aggregate coverage**: cần `report-aggregate` và data/class roots theo modules; report không tự chặn build khi thiếu coverage threshold.
- **Surefire Report**: dùng test XML từ modules; phải xem goals/aggregate semantics của đúng plugin version.
- **Dependency convergence**: có report của Project Info Reports Plugin; khác Maven Enforcer rule có thể fail build.
- **Maven JXR**: source code cross-reference pages; không tự hiện lên nếu không cấu hình reporting.
- **API compatibility**: tool Revapi/japicmp, không phải mục đích của Javadoc aggregate.

**Không có một toggle chung khiến tất cả reports tự gộp dữ liệu của toàn reactor**. Mỗi plugin có mục tiêu, inputs và options riêng. Phải kiểm tra nơi goal chạy và cách nó tổng hợp.

## 15. CI/CD: tạo tài liệu đáng tin cậy

Đề xuất pipeline nhiều giai đoạn:

1. **Build/test source chính xác:** trên cùng commit/tag, chạy `mvn -B -ntp clean install` hoặc các phases thích hợp.
2. **Sinh tài liệu:** chạy `mvn -B -ntp site` trên toàn reactor.
3. **Stage và QA:** chạy `mvn -B -ntp site:stage` và kiểm tra link/HTML/assets.
4. **Lưu artifact preview:** upload local staged tree như CI artifact có retention hợp lý.
5. **Review:** đảm bảo nội dung không lộ bí mật, docs version khớp binary release và các quality gates cần thiết đều pass.
6. **Publish có ủy quyền:** dùng `site:deploy`/SCM Publish/static-hosting workflow được quản lý; không dùng demo URL.
7. **Post-deploy smoke test:** xác minh HTTP links/permissions/CDN cache ở website thực.
8. **Archive/rollback:** lưu versioned docs nếu nhiều API releases cần truy cập.

**Đừng chạy site:deploy trên pull request không tin cậy** nếu job đang sở hữu credentials publication. Không đưa token/password vào `pom.xml`, Markdown hoặc generated HTML.

### 15.1. Vì sao docs build không được coi là release gate mặc định?

`mvn verify` và `mvn site` thuộc các lifecycles khác nhau. Một pipeline chỉ có `mvn verify` **chưa chứng minh site có thể render**. Nếu tài liệu là điều kiện phát hành, hãy đặt job docs như **required CI check** và chỉ chạy release job khi đạt.

### 15.2. Generated sources và Javadoc no-fork

OpenAPI/protobuf/JAXB/annotation processing có thể tạo source ở `target/generated-sources` hoặc phase cụ thể. `aggregate-no-fork` không tạo lại sources; chạy site quá sớm có thể thiếu class hoặc links. Với build docs phải:
- Activate đúng profiles.
- Chạy phase đủ để tạo source roots/class files.
- Xác nhận Javadoc plugin thấy source roots mong đợi.
- Tránh công khai generated code nội bộ ngoài phạm vi cho phép.

### 15.3. Hiệu năng và `-T`

Aggregator reporting goals có thể không thread-safe. Tránh mặc định chạy `mvn -T 4 site` khi chưa xác minh rằng Javadoc/report plugins, generated sources và staging output có thể hoạt động song song an toàn. Khi điều tra lỗi, bắt đầu bằng build site **tuần tự**.

### 15.4. Site versioning và artifact provenance

Nếu code release là `1.0.0` nhưng site được tạo từ branch main thay đổi sau đó, người dùng có thể đọc Javadoc không còn khớp artifact đã publish. Nên gắn docs với **đúng source commit/tag, Maven/JDK/plugin versions và binary artifact GAV**. Khi có nhiều major releases, website có thể có versioned paths như `/docs/1.0.0/` và `/docs/2.0.0/` theo hosting policy.

## 16. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Menu Modules hỏng trong root `target/site` | Modules có output sites riêng, chưa stage | Dùng `site:stage` và kiểm tra staging tree |
| `site:stage` lỗi input không tồn tại | Chưa chạy `mvn site` hoặc đã clean output | Chạy site trước stage |
| Stage đặt child sai thư mục | Parent/child site URL hoặc `topSiteURL` chưa đúng | Kiểm tra `distributionManagement.site` và logs |
| Không có Javadoc aggregate | ReportSet/goal sai hoặc không ở root | Kiểm tra reporting và Site Plugin logs |
| Javadoc aggregate chạy lặp ở children | ReportSet bị inherit | Đặt `inherited=false` cho aggregate report set |
| no-fork Javadoc lỗi source/class | Chưa compile/generated sources hoặc dependency resolution lỗi | Build trước, kiểm tra module paths |
| Site bị lỗi UTF-8 | Source/report encoding sai | Dùng UTF-8, kiểm tra generated HTML |
| Project Reports trống | Reporting không có reports thực, reportSet cấu hình sai | Xem goal logs và output files |
| Root dependency report trống | Root không có dependency runtime | Xem child dependency report |
| `site.xml` không parse được | Mix v1/v2 hoặc XML sai | Dùng schema v2 đúng và valid XML |
| Skin không tải được | Maven repo mirror/SSL/version artifact lỗi | Kiểm tra Maven settings và skin version |
| `mvn -N site` không tạo child sites | `-N` non-recursive | Bỏ `-N` |
| `mvn deploy` không cập nhật docs | Deploy artifacts khác site deploy | Dùng đúng site publication |
| Website sau deploy bị 404 | Path prefix/CDN/cache/URL calculation khác stage | Test remote links/site base URL |
| CI site rất chậm | Javadoc goal fork compile, nhiều reports, generator lặp | Dùng no-fork sau build, chọn reports |
| Website lộ internal info | Docs/resources/reports chứa secrets | Review, scan và access control |
| Javadoc không nhận JPMS modules | Named/unnamed module setup không nhất quán | Xem hướng dẫn modularized Javadoc |
| Site khác local và CI | Toolchain/plugins/profiles/repository/cache khác | Pin versions và ghi build provenance |

### 16.1. Lỗi site:stage hiển thị links nhưng không mở được

Có thể site staging path thật không giống giả định:
- `distributionManagement.site.url` parent có prefix, nhưng child override sai.
- StagingDirectory được cấu hình ở một child thay vì aggregator.
- Menu tự định nghĩa hard-code `target/site` hoặc URL bắt đầu bằng `/` không phù hợp base path.
- Doxygen/Asciidoc/custom generated pages không nằm trong standard source paths.
- Markdown link dùng `index.md` thay vì generated `index.html`.

Hãy xem **HTML href được sinh**, site stage logs và file thực trong staging. Sửa **source Markdown/site.xml/POM** rồi build lại; đừng sửa HTML output trong `target` bằng tay.

### 16.2. Lỗi site generation nhưng build Java vẫn pass

Site Plugin còn cần skin/report plugin dependencies, Doxia parser và Javadoc tool. Java compile có thể pass dù Maven Site không lấy được skin, một report plugin chưa tương thích, Javadoc tags sai hoặc site descriptor XML invalid. Đây là lý do docs nên có job kiểm thử riêng khi là deliverable quan trọng.

### 16.3. Lỗi Javadoc do package/JPMS

Nếu Java Javadoc fail với "package is not visible" hoặc duplicate module/package messages, kiểm tra JPMS module descriptors, module path, compiler/Javadoc versions, exported packages và additional Javadoc options. Không tắt toàn bộ `failOnError` chỉ để tạo HTML thiếu API documentation; giải quyết nguyên nhân thực, trừ khi có waiver được ghi rõ.

## 17. Checklist hoàn thành

- [ ] Root POM có `<modules>` đúng, children tham chiếu parent phù hợp.
- [ ] Dependencies nội bộ được khai báo thực tế, không chỉ liệt kê modules.
- [ ] JDK/Maven/Compiler/Site/Javadoc/reporting/skin versions được ghim.
- [ ] `src/site/markdown` có trang index root và các trang cần cho children.
- [ ] Site descriptor v2 `src/site/site.xml` hợp lệ.
- [ ] Menu `modules`, `parent`, `reports` được cấu hình có chủ đích.
- [ ] Không có inherited link trỏ đến trang không tồn tại trong child.
- [ ] `<reporting>` chọn reportSets đúng.
- [ ] Aggregate Javadoc reportSet dùng `inherited=false` nếu chỉ muốn ở root.
- [ ] Generated sources/classes được chuẩn bị trước no-fork Javadoc.
- [ ] `mvn clean install` thành công trên cùng commit/tag.
- [ ] Java stdout/unit tests của lab hoặc dự án thật đạt yêu cầu.
- [ ] `mvn site` sinh HTML cho root và từng module.
- [ ] `site:stage` tạo cây local preview.
- [ ] Các liên kết nội bộ/Javadoc/report pages hoạt động ở staging.
- [ ] CSS/assets/locale/UTF-8 không bị lỗi.
- [ ] Site không chứa thông tin nhạy cảm.
- [ ] Không nhầm `mvn deploy` với `site:deploy`.
- [ ] Chỉ người/job được phép mới publish site.
- [ ] Site URL thực và version prefix đúng release policy.
- [ ] CI giữ reports/preview đủ để đối chiếu sau build.
- [ ] Sau deploy có smoke test HTTP links và rollback/retention.

## 18. Câu hỏi ôn tập và đáp án

**Câu 1.** Root có `<modules>` thì Maven đã tạo một website hợp nhất chưa?

**Đáp án:** Chưa. Root aggregator điều phối build; phải chạy Site Plugin và staging riêng.

**Câu 2.** `mvn site` tạo output của child ở đâu?

**Đáp án:** Mỗi child thường có `target/site` riêng, ví dụ `greeting-api/target/site`.

**Câu 3.** Vì sao link Modules có thể hỏng khi mở trực tiếp root `target/site`?

**Đáp án:** Vì output directories chưa theo bố cục deployment; dùng `site:stage` để dựng cây preview.

**Câu 4.** `site:stage` có publish tới website thật không?

**Đáp án:** Không. Goal dựng local staging; `site:deploy` mới publish theo cấu hình site URL.

**Câu 5.** `mvn deploy` và `mvn site:deploy` khác nhau thế nào?

**Đáp án:** Một lệnh deploy Maven artifacts, lệnh kia deploy trang tài liệu HTML.

**Câu 6.** Nơi ghi Markdown cho Site Plugin là đâu?

**Đáp án:** `src/site/markdown/*.md`, ví dụ `index.md`.

**Câu 7.** File điều khiển menu/skin là gì?

**Đáp án:** `src/site/site.xml`.

**Câu 8.** Menu liên kết module sites là cú pháp nào?

**Đáp án:** `<menu ref="modules"/>`.

**Câu 9.** Menu Project Reports được sinh theo cú pháp nào?

**Đáp án:** `<menu ref="reports"/>` khi báo cáo thực sự có output.

**Câu 10.** Javadoc aggregate khác Javadoc từng module ở đâu?

**Đáp án:** Aggregate thu API sources từ nhiều modules; per-module Javadoc chỉ của project hiện tại.

**Câu 11.** Vì sao dùng `aggregate-no-fork` sau build?

**Đáp án:** Để không tự chạy lại compile lifecycle, tránh thừa công việc; cần generated classes đã sẵn.

**Câu 12.** `inherited=false` trong aggregate reportSet giải quyết điều gì?

**Đáp án:** Tránh aggregate report chạy lại ở các child theo inheritance behavior của plugin.

**Câu 13.** Lab gồm những modules nào?

**Đáp án:** `greeting-api` và `greeting-app`; root `multi-site-lab` là parent/aggregator.

**Câu 14.** Java app in chính xác gì?

**Đáp án:** `Hello, Site!`.

**Câu 15.** Lab có bao nhiêu unit tests?

**Đáp án:** Ba: 2 API tests, 1 app test.

**Câu 16.** Site descriptor v2 có namespace nào?

**Đáp án:** `http://maven.apache.org/SITE/2.1.0` trong lab.

**Câu 17.** `Project Info Reports:dependencies` ở root có tự gom mọi dependency của children không?

**Đáp án:** Không. Nó báo thông tin của project đó; xem báo cáo mỗi child khi cần.

**Câu 18.** Chỉ có Javadoc build success đã chứng minh binary compatibility chưa?

**Đáp án:** Chưa; cần tool/API contract tests riêng.

**Câu 19.** Vì sao không chạy `mvn -N site` để tổng hợp toàn reactor?

**Đáp án:** `-N` chỉ chạy current project, bỏ children.

**Câu 20.** Có nên chạy `site:deploy` tới URL ví dụ trong lab không?

**Đáp án:** Không. `example.invalid` là domain không hoạt động, chỉ phục vụ mô hình staging.

**Câu 21.** Maven multi-module có đồng nghĩa JPMS modules không?

**Đáp án:** Không. `<modules>` là reactor structure; `module-info.java` là JPMS.

**Câu 22.** Vì sao báo cáo JaCoCo aggregate không tự là coverage gate?

**Đáp án:** Nó tạo report; cần threshold/check/CI policy được thực thi riêng để chặn release.

**Câu 23.** Nên kiểm tra cross-module links ở đâu?

**Đáp án:** Trên cây site sau `site:stage` và thêm smoke test sau deploy nếu phát hành remote.

**Câu 24.** `mvn verify` có tự tạo site mặc định không?

**Đáp án:** Không. Cần `mvn site` hoặc báo cáo được cấu hình vào CI job riêng.

**Câu 25.** Nếu site phải tương ứng release v1.0.0, cần kiểm tra gì?

**Đáp án:** Docs và Javadoc được sinh từ đúng commit/tag, Maven/JDK/plugin versions và artifact contract của v1.0.0.

## 19. Tài liệu chính thức

- [Apache Maven – Building Multi-module Sites](https://maven.apache.org/guides/mini/guide-multimodule-site.html): vì sao modules có site riêng và cần `site:stage` để preview links.
- [Maven Site Plugin – Introduction](https://maven.apache.org/plugins/maven-site-plugin/): `site:site`, `site:stage`, `site:deploy` và `site:stage-deploy`.
- [Maven Site Plugin – Building Multi-module Sites](https://maven.apache.org/plugins/maven-site-plugin/examples/multimodule.html): cách stage/deploy đa module.
- [Maven Site Plugin – Creating Content](https://maven.apache.org/plugins/maven-site-plugin/examples/creating-content.html): Markdown, APT, XDoc, FML, resources.
- [Apache Maven – Guide to Creating a Site](https://maven.apache.org/guides/mini/guide-site.html): site descriptor v2, skin, menu/report configuration.
- [Maven Site Plugin – Site Descriptor](https://maven.apache.org/plugins/maven-site-plugin/examples/sitedescriptor.html): menu `modules`, `parent`, `reports` và links.
- [Maven Site Plugin – Configuring Reports](https://maven.apache.org/plugins/maven-site-plugin/examples/configuring-reports.html): `<reporting>` và reportSets.
- [Maven Site Plugin – site:stage](https://maven.apache.org/plugins/maven-site-plugin/stage-mojo.html): `stagingDirectory` và `topSiteURL`.
- [Maven Javadoc Plugin – Aggregating Javadocs for Multi-Projects](https://maven.apache.org/plugins/maven-javadoc-plugin/examples/aggregate.html): `aggregate` goal và `inherited=false`.
- [Maven Javadoc Plugin – aggregate-no-fork](https://maven.apache.org/plugins/maven-javadoc-plugin/examples/aggregate-nofork.html): tránh compile lifecycle lặp.
- [Maven Project Info Reports Plugin](https://maven.apache.org/plugins/maven-project-info-reports-plugin/): `summary`, `modules` và `dependencies`.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor sorting/selection.
- [Apache Maven POM Reference](https://maven.apache.org/pom.html): modules/parent/reporting/distributionManagement.
