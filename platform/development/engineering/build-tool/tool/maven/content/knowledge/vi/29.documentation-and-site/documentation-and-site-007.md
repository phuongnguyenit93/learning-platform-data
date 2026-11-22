# Phân biệt tạo site với xuất bản site qua site-deploy

> Thuộc nhóm **Tài liệu và Site** trong Maven. Bài hướng dẫn cách sinh website tài liệu **cục bộ** và cách **xuất bản** bộ website đó đến một đích được cấu hình, đồng thời chỉ rõ sự khác nhau giữa tên phase và tên goal.

## 1. Bản chất của Maven Site

Maven Site Plugin là công cụ tạo các trang HTML tài liệu dự án, thường kết hợp tài liệu viết tay và các báo cáo build. Nó dùng **Doxia** để chuyển các định dạng tài liệu được hỗ trợ (như Markdown, APT, XDoc, FML) thành nội dung HTML, và dùng site renderer/skin để ghép các trang thành website.

Có **hai hành động hoàn toàn khác nhau**:

- **Generate site**: tạo file HTML/CSS/assets trong workspace build. Lệnh điển hình `mvn site`. Output mặc định là thư mục **`target/site/`**.
- **Deploy site**: chuyển những file website **đã được generate** tới vị trí `distributionManagement.site.url`, thường qua giao thức do **Maven Wagon** hỗ trợ. Goal điển hình `mvn site:deploy`.

Có thêm một **phase** Maven tên **`site-deploy`**, gọi bằng `mvn site-deploy`: khi chạy phase đó, Maven đi qua `site` rồi mới tới `site-deploy`, nghĩa là **generate và deploy trong một invocation**.

```text
pom.xml + src/site/markdown + site.xml + reporting plugins
                             |
                             | mvn site
                             v
                     target/site/
                     index.html
                     guide.html
                     css/...
                             |
                 +-----------+-------------+
                 |                         |
                 | mvn site:stage          | mvn site:deploy
                 v                         v
          target/staging/           distributionManagement
          preview local              .site.url
                                      |
                                      v
                                site publication

mvn site-deploy  ==>  site lifecycle phase:
                      pre-site -> site -> post-site -> site-deploy
                      (generate rồi publish)
```

**Không suy diễn:** Một lệnh `mvn site` báo `BUILD SUCCESS` không đồng nghĩa trang web trên Internet đã đổi. Ngay cả khi `site:deploy` báo thành công, vẫn cần kiểm tra địa chỉ đích thật sự phục vụ đúng website, không có lỗi permission, relative link hoặc cache.

### Mục tiêu của bài học

Sau khi học, bạn có thể:

1. Phân biệt **`mvn site`**, **`mvn site:site`**, **`mvn site:deploy`**, **`mvn site-deploy`**, **`mvn site:stage`**, **`mvn site:stage-deploy`**, **`mvn site:run`** và **`mvn deploy`**.
2. Hiểu các đầu vào: `src/site`, site descriptor `site.xml` và cấu hình `<reporting>`.
3. Tạo một Maven site từ project **Java 17** có POM, Java source, JUnit test, Markdown docs và menu.
4. Kiểm tra tệp kết quả tại `target/site` **trước khi publish**.
5. Publish thử vào **`file:///tmp/...` cục bộ** mà không cần quyền máy chủ thật.
6. Dùng `distributionManagement.site.id` với `settings.xml` đúng cách khi có authentication, không ghi secrets vào POM.
7. Thiết kế pipeline CI có staging, kiểm tra URL/link và tách quyền publish khỏi quyền build.
8. Xử lý multi-module link layout, site URL inheritance, lỗi stale output và các tình huống deploy nhầm.

## 2. Bảng lệnh: phase khác goal

| Lệnh | Loại | Hành động | Output/side effect |
| --- | --- | --- | --- |
| `mvn site` | Phase `site` của site lifecycle | Render website | Ghi `target/site/`; **không publish** |
| `mvn site:site` | Site Plugin goal `site` | Render site cho một project | Ghi `target/site/`; không publish |
| `mvn site:stage` | Site Plugin goal `stage` | Tổ chức preview cây site theo destination layout | Ghi `target/staging/` hoặc directory được chỉ định; không upload production |
| `mvn site:run` | Site Plugin goal `run` | Xem site qua Jetty preview server | Khởi động preview process; không upload |
| `mvn site:deploy` | Site Plugin goal `deploy` | **Transfer website đã generate** | Ghi tới `distributionManagement.site.url` |
| `mvn site-deploy` | **Phase `site-deploy`** của site lifecycle | **Generate rồi deploy** | Ghi `target/site` và destination |
| `mvn site:stage-deploy` | Site Plugin goal `stage-deploy` | Transfer site tới staging destination | Có side effect **publish staging** |
| `mvn deploy` | Phase `deploy` của **default** lifecycle | Publish JAR/WAR/POM tới Maven repository | **Không phải site website deployment** |
| `mvn clean site` | Clean + site phase | Xóa output cũ rồi generate site | Site mới trong `target/site`; không upload |
| `mvn package` | Default lifecycle phase | Build Java artifact | Tạo `.jar`/`.war`; không tạo website mặc định |

Cách nhận biết nhanh: dấu hai chấm `:` trong `site:deploy` thể hiện **plugin:goal**; dấu gạch nối `-` trong `site-deploy` là một phần tên **lifecycle phase**. Hai cách viết có hệ quả khác nhau vì gọi phase sẽ thực hiện những phase đứng trước nó.

## 3. Phải hiểu Maven lifecycle để không nhầm với `mvn deploy`

Maven có ba lifecycle chính:

- **default**: `compile -> test -> package -> verify -> install -> deploy` (đây chỉ là các mốc tiêu biểu, còn nhiều phase trung gian).
- **clean**: `pre-clean -> clean -> post-clean`.
- **site**: `pre-site -> site -> post-site -> site-deploy`.

Trong site lifecycle, Maven mặc định bind `site:site` vào phase `site` và `site:deploy` vào phase `site-deploy`.

```text
default lifecycle                    site lifecycle
-----------------                    --------------
compile                              pre-site
test                                 site       -> site:site
package                              post-site
verify                               site-deploy-> site:deploy
install
deploy -> deploy:deploy
```

Vì vậy:

- `mvn test` chỉ chạy tới phase `test` của default lifecycle, không tự tạo trang tài liệu.
- `mvn verify` thực thi những kiểm tra được bind tới default lifecycle, không tự upload docs.
- `mvn deploy` thường deploy artifact **JAR/WAR/POM** vào repository được khai trong `distributionManagement.repository` hoặc `snapshotRepository`.
- `mvn site` tạo **website tài liệu**.
- `mvn site-deploy` publish website qua `distributionManagement.site`.
- Không có mặc định “`mvn deploy` gọi `site-deploy`”, cũng không có mặc định “`mvn site` chạy mọi JUnit tests”.

Một project có thể có đồng thời **artifact đã release** nhưng **site chưa publish**, hoặc **site đã cập nhật** nhưng artifact Java vẫn là bản cũ. Trong CI, cần theo dõi hai loại output riêng.

## 4. Trang nào được đưa vào site?

Maven Site Plugin đọc thông tin POM, tài liệu nguồn và reporting plugins:

```text
project/
├── pom.xml                     # project metadata, build, reporting, site URL
└── src/
    └── site/
        ├── site.xml            # menu, navigation, skin, breadcrumbs
        ├── markdown/
        │   ├── index.md        # homepage
        │   └── guide.md        # user guide
        ├── apt/                # APT markup, nếu có
        ├── xdoc/               # XDoc XML, nếu có
        ├── fml/                # FAQ markup, nếu có
        └── resources/          # ảnh, CSS hoặc static resources
```

Các nguồn thường được ánh xạ như sau:

| Input | Output site |
| --- | --- |
| `src/site/markdown/index.md` | `target/site/index.html` |
| `src/site/markdown/guide.md` | `target/site/guide.html` |
| `src/site/apt/faq.apt` | `target/site/faq.html` |
| `src/site/resources/images/logo.png` | `target/site/images/logo.png` |
| `<reporting>` + Project Info Reports | Những trang HTML thông tin POM như Dependencies, Summary, License... tùy cấu hình |

**`README.md` ở root project không tự biến thành `index.html`.** Đặt Markdown vào đúng vị trí `src/site/markdown` để Doxia nhận dạng theo cấu trúc Site Plugin.

### Cấu hình báo cáo khác cấu hình goal build

```xml
<build>
    <plugins>
        <!-- Ví dụ: maven-site-plugin, compiler, surefire -->
    </plugins>
</build>

<reporting>
    <plugins>
        <!-- Ví dụ: maven-project-info-reports-plugin -->
    </plugins>
</reporting>
```

Đây là fragment giải thích hai phần POM, không phải project POM hoàn chỉnh. Plugin dưới `build/plugins` được dùng cho **build goals/executions**. Reporting plugin dưới `reporting/plugins` xác định **report goals** để Site Plugin đưa vào website. Không được nghĩ chỉ vì một plugin tạo report có mặt ở `build/plugins` thì trang HTML báo cáo tự động có trong site.

## 5. Dự án thực hành: Java 17, Markdown và Site Plugin

Ví dụ sử dụng **Java 17**, **Maven 3.9.x**, **Maven Site Plugin 3.22.0**, **Project Info Reports Plugin 3.9.0**, **JUnit Jupiter 5.11.4**. Project chạy local, không kết nối database hay external API.

Mục tiêu của phần này là kiểm chứng được **hai loại sản phẩm độc lập**: executable Java JAR và bộ HTML site. Java chỉ là ví dụ tối thiểu giúp thấy `mvn verify` khác `mvn site`.

### 5.1. Cấu trúc tệp đầy đủ

```text
maven-site-boundaries/
├── pom.xml
├── src/
│   ├── main/java/dev/lesson/site/SiteApp.java
│   ├── test/java/dev/lesson/site/SiteAppTest.java
│   └── site/
│       ├── site.xml
│       └── markdown/
│           ├── index.md
│           └── guide.md
└── target/                         # Maven sinh, không cần tạo sẵn
```

### 5.2. POM hoàn chỉnh — `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>maven-site-boundaries</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Maven Site Boundaries</name>
    <description>Compare building Maven sites with publishing them</description>

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
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.site.SiteApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
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
                            <report>index</report>
                            <report>dependencies</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
        </plugins>
    </reporting>

    <!-- ONLY for POSIX local demonstration; use a permitted directory.
         On Windows change URL to file:///C:/temp/maven-site-boundaries-public -->
    <distributionManagement>
        <site>
            <id>local-site-demo</id>
            <url>file:///tmp/maven-site-boundaries-public</url>
        </site>
    </distributionManagement>
</project>
```

Giải thích:

1. `packaging=jar` và các Compiler/JAR/Surefire plugins phục vụ **Java build**.
2. `maven-site-plugin` được pin ở version `3.22.0` để generate/publish docs.
3. Project Info Reports Plugin `3.9.0` nằm trong `reporting`; hai report goals `index`/`dependencies` cung cấp trang thông tin project.
4. `<project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>` giữ tiếng Việt khi render.
5. `distributionManagement.site.url` là **đích site deployment**, **không** phải Java artifact repository.
6. Trong POM thực hành, URL là `file:///tmp/maven-site-boundaries-public`: **đích ghi file cục bộ** phù hợp Linux/macOS. Trên Windows, chỉnh thành `file:///C:/temp/maven-site-boundaries-public` và đảm bảo quyền ghi.
7. POM này cố ý không khai `distributionManagement.repository`. Khi học bài site, **không cần gọi `mvn deploy`** để upload Java artifact tới remote repository.
8. POM không đưa password/token vào source, và không trỏ tới máy chủ sản xuất. Khi áp dụng thật phải có review/cấp quyền riêng.

### 5.3. Java source — `src/main/java/dev/lesson/site/SiteApp.java`

```java
package dev.lesson.site;

public final class SiteApp {
    private SiteApp() {
    }

    public static String greeting(String name) {
        return "Hello, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println("SITE=" + greeting("Maven"));
    }
}
```

Source dùng Java standard library, không có runtime dependency. JAR Plugin được cấu hình `Main-Class`, nên `java -jar` có thể gọi đúng main.

### 5.4. JUnit test — `src/test/java/dev/lesson/site/SiteAppTest.java`

```java
package dev.lesson.site;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class SiteAppTest {
    @Test
    void greets() {
        assertEquals("Hello, Maven!", SiteApp.greeting("Maven"));
    }
}
```

Test thuộc default build lifecycle phase `test`. **`mvn site` không phải cách mặc định để chạy đầy đủ JUnit tests**; muốn site phản ánh test results, trước tiên chạy tests và khai báo reporting plugin tương ứng.

### 5.5. Trang Markdown — `src/site/markdown/index.md`

```markdown
# Maven Site Boundaries

Đây là trang tài liệu được tạo bởi Maven Site Plugin.

## Thao tác

- `mvn site`: render HTML dưới `target/site/`.
- `mvn site:deploy`: đưa các trang HTML đã render đến đích.
- `mvn site-deploy`: chạy site lifecycle đến phase xuất bản.

Xem [Hướng dẫn](guide.html) để tìm hiểu từng bước.
```

Nội dung trong code block này là **nội dung file Markdown nguồn**. Khi render, Maven tạo `target/site/index.html`. Link `guide.html` là output HTML tương ứng với `guide.md`.

### 5.6. Trang Markdown — `src/site/markdown/guide.md`

```markdown
# Hướng dẫn

## Generate

Chạy `mvn site` rồi kiểm tra `target/site/index.html`.

## Publish

Kiểm tra trước `distributionManagement.site.url`.
Chỉ sau khi đã xác minh đích mới chạy `mvn site:deploy`.

## Kiểm chứng

So sánh nội dung trong `target/site/` với bản ở destination.
```

Sau render, file dự kiến `target/site/guide.html`.

### 5.7. Site descriptor — `src/site/site.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="Maven Site Boundaries">
    <body>
        <menu name="Tài liệu">
            <item name="Trang chủ" href="index.html"/>
            <item name="Hướng dẫn" href="guide.html"/>
        </menu>
        <menu ref="reports"/>
    </body>
</project>
```

Site descriptor quyết định menu/navigation, không quyết định đích deploy. `<menu ref="reports"/>` dùng menu cho report pages khi đã cấu hình `<reporting>`.

Với dự án nhiều cấu hình hơn, có thể khai XML namespace và decoration model schema theo tài liệu Maven Doxia. Phần này cố ý giữ cấu hình descriptor đơn giản để học viên tập trung vào khác biệt **generate/site-deploy**.

## 6. Build Java và generate site: hai bước có output khác nhau

### Bước 1 — Java build/test/JAR

Tại root `maven-site-boundaries/`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Khi build thành công, những outputs quan trọng:

```text
target/classes/dev/lesson/site/SiteApp.class
target/surefire-reports/
target/maven-site-boundaries-1.0.0.jar
```

Chạy Java artifact:

```bash
java -jar target/maven-site-boundaries-1.0.0.jar
```

**Stdout chính xác của ứng dụng:**

```text
SITE=Hello, Maven!
```

Điều này xác minh Java JAR. Nó **không chứng minh site HTML đã generate**.

### Bước 2 — generate site

```bash
mvn -B -ntp site
```

Site Plugin tạo website tĩnh, thông thường ở:

```text
target/site/
├── index.html
├── guide.html
├── dependencies.html
├── project-info.html
├── css/
└── ... các tài nguyên/báo cáo khác
```

Đây là **layout minh họa các mục tiêu kiểm tra**, không cam kết output luôn có cùng danh sách report file ở mọi report/plugin config. `index.html` và `guide.html` là đích chính từ Markdown; report plugin tạo project info pages nếu goals chạy thành công.

**Trạng thái ở đây: `SITE_GENERATED`, chưa phải `SITE_PUBLISHED`.** Việc POM đã khai URL `file:///tmp/...` không khiến `mvn site` tự động ghi tới đó.

### Bước 3 — kiểm tra output cục bộ

Linux/macOS:

```bash
ls -la target/site/
grep -n 'Maven Site Boundaries' target/site/index.html
grep -n 'Hướng dẫn' target/site/guide.html
```

Windows PowerShell:

```powershell
Get-ChildItem target\site
Select-String -Path target\site\index.html -Pattern 'Maven Site Boundaries'
Select-String -Path target\site\guide.html -Pattern 'Hướng dẫn'
```

Ngoài kiểm tra text, mở `target/site/index.html` để xem menu/CSS/link. Nếu browser hạn chế một số resources do chính sách `file://`, có thể dùng server preview (Site Plugin `site:run`) để đánh giá.

**Kiểm tra site là kiểm tra tài liệu**, khác với Java unit test. Một site generate thành công vẫn có thể chứa link 404, hình ảnh mất hoặc nội dung nhầm version.

## 7. Cơ chế của `mvn site:deploy`

Goal `site:deploy` của Site Plugin chuyển nội dung **đã có** từ thư mục output site (mặc định `project.reporting.outputDirectory`, thường là `target/site`) đến đích trong:

```xml
<distributionManagement>
    <site>
        <id>local-site-demo</id>
        <url>file:///tmp/maven-site-boundaries-public</url>
    </site>
</distributionManagement>
```

- `id` là định danh deployment destination, dùng để tìm thông tin xác thực nếu cần.
- `url` là vị trí được ghi tài liệu HTML.
- Giao thức `file://` ghi filesystem, `scp://` thường dùng SSH/Wagon provider, các transport khác cần cấu hình phù hợp.
- Goal **không đồng nghĩa Maven default lifecycle deploy**.
- Goal **không tự chạy `mvn site` trước** như một phase invocation. Tài liệu chính thức yêu cầu **site đã được generate**.

### Thực hành xuất bản an toàn ra filesystem cục bộ

**Chỉ trên Linux/macOS, trong project demo và ở máy được phép ghi `/tmp`:**

```bash
mvn -B -ntp site
mvn -B -ntp site:deploy
```

Khi thành công, đích cục bộ có thể trông như:

```text
/tmp/maven-site-boundaries-public/
├── index.html
├── guide.html
├── dependencies.html
├── css/
└── ...
```

Tùy plugin, transport và thư mục đích, các file/tên report có thể khác. **Không suy rằng đích sẽ được làm sạch hoàn toàn**: một số file cũ có thể vẫn tồn tại; file trùng tên có thể bị overwrite. Chỉ chạy ở nơi chắc chắn không chứa tài liệu khác cần giữ.

Kiểm tra **sau deploy**:

```bash
ls -la /tmp/maven-site-boundaries-public/
grep -n 'Maven Site Boundaries' /tmp/maven-site-boundaries-public/index.html
grep -n 'Hướng dẫn' /tmp/maven-site-boundaries-public/guide.html
```

Sự khác biệt quan sát được:

- Sau `mvn site`: có `target/site/index.html`.
- Sau `mvn site:deploy`: **có thêm các file ở destination**. Đó là hành động publish.

**Đây không phải website Internet**; `file:///tmp` chỉ là đích file local. Nếu muốn trang public, cần web server/storage/CDN phục vụ các tệp đã publish, kèm DNS/TLS/permissions/caching.

### Nếu chạy `mvn clean` giữa hai bước?

```bash
mvn site
mvn clean
mvn site:deploy
```

`clean` thường xóa `target/site`. Goal `site:deploy` sau đó **không còn output mới để chuyển**, dẫn đến fail/thiếu nội dung. Cách đúng:

```bash
mvn clean site
mvn site:deploy
```

hoặc dùng `mvn site-deploy` để site lifecycle generate rồi deploy trong một lần gọi.

## 8. `mvn site-deploy` khác `mvn site:deploy` ở đâu?

Một ví dụ cần học thuộc **ý nghĩa, không chỉ chính tả**:

```bash
mvn -B -ntp site:deploy
```

Có dấu `:`, nên gọi **goal deploy** của Site Plugin. **Site phải được tạo trước**.

Ngược lại:

```bash
mvn -B -ntp site-deploy
```

Có dấu `-`, nên chạy **phase site-deploy** của site lifecycle:

```text
pre-site
    |
site          -> site:site tạo target/site
    |
post-site
    |
site-deploy   -> site:deploy đưa site lên URL đích
```

Vì phase bao gồm những phase trước đó, `mvn site-deploy` là lựa chọn **generate-and-publish**.

### Một invocation nhưng vẫn hai hành động

```bash
mvn -B -ntp site site:deploy
```

Câu lệnh gọi **site phase** rồi **site:deploy goal** theo thứ tự. Nó thể hiện rõ hai bước trong một command, nhưng không phải chính tả khác của site-deploy phase.

**Trong học tập và review:** nên chạy `mvn site` rồi xem `target/site` trước, bởi lệnh publish có tác động bên ngoài. **Trong CI đã có approval và destination kiểm soát:** có thể dùng `mvn site-deploy` nếu muốn generate và publish một lần, nhưng vẫn cần post-deploy checks.

## 9. `project.url`, `distributionManagement.site` và Maven repository

Một POM có thể có nhiều URL với **mục đích khác nhau**:

```xml
<url>https://docs.example.invalid/project/</url>

<distributionManagement>
    <repository>
        <id>artifacts</id>
        <url>https://repo.example.invalid/releases/</url>
    </repository>
    <site>
        <id>docs-production</id>
        <url>scp://docs.example.invalid/var/www/docs/project/</url>
    </site>
</distributionManagement>
```

Đây là **fragment minh họa**, không thay thế đoạn `distributionManagement` trong POM demo:

- `<url>` cấp project: đường dẫn homepage thông tin, có thể được renderer dùng khi tạo links.
- `distributionManagement.repository`: đích publish Maven **JAR/WAR/POM** khi chạy `mvn deploy`.
- `distributionManagement.site`: đích publish **website HTML** khi chạy `site:deploy`/`site-deploy`.
- `site.id`: key tìm credential trong `settings.xml`.
- `site.url`: URL được Site Plugin/Wagon transfer files đến.

`docs.example.invalid` và `repo.example.invalid` là **hostnames minh họa, không hoạt động như dịch vụ thật**. Remote `scp://` cần provider phù hợp, quyền ghi trên server, host key verification và đường dẫn remote tồn tại/được tạo. Không có bảo đảm mọi Maven installation hỗ trợ mọi URL protocol mặc định.

**Trường hợp `https://`:** website có thể truy cập qua HTTPS nhưng không hỗ trợ upload qua Wagon HTTP transport. Không chỉ thay `scp` bằng `https` nếu server không cấp API PUT/WebDAV tương ứng. Với S3/GitHub Pages/CDN, có thể cần publisher/extension hoặc CI workflow khác hoàn toàn, từ đầu vào `target/site`.

## 10. Quản lý credentials, không chèn secret vào POM

Khi remote site URL yêu cầu xác thực, cấu hình thông tin xác thực trong Maven settings, secrets manager và environment được kiểm soát. `<server><id>` phải khớp `distributionManagement.site.id`.

Ví dụ cấu trúc `settings.xml` (không chứa secret thật):

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>docs-production</id>
            <username>publisher</username>
        </server>
    </servers>
</settings>
```

Đây là **mẫu giải thích ID binding, không phải credentials hoàn chỉnh**. Trong thực tế, passwords/SSH keys/tokens phải được cấp từ secret store/credential helper hoặc `settings.xml` riêng được bảo vệ theo chính sách, không commit vào Git.

Một số nguyên tắc:

- `file://` local cần **filesystem permissions**, thường không cần remote credentials.
- `scp://` cần SSH identity/host key trust và Wagon provider thích hợp.
- Đừng log plaintext secrets với `-X` hoặc truyền password thẳng qua CLI khi có cơ chế an toàn hơn.
- Chỉ cấp quyền **publish production** cho job trên trusted branch/tag, không cho mọi Pull Request.
- Kiểm tra POM và Site descriptor trong PR vì chúng có thể thay URL đích hoặc nội dung website.
- Cấp quyền tối thiểu: một credential chỉ được ghi site path của project, không dùng admin-level account.

**Đừng đặt thông tin nhạy cảm vào Markdown docs**, vì nó sẽ được chuyển thành HTML public nếu website được publish.

## 11. Xem trước bằng `site:run` hoặc `site:stage`

### `site:run` — preview HTTP server

```bash
mvn -B -ntp site:run
```

Site Plugin có goal chạy Jetty để preview site, phù hợp khi chỉnh tài liệu. Lệnh có thể giữ terminal chạy cho tới khi bạn dừng. Đọc log để lấy **URL và port thật**; không giả định một port cố định nếu chưa có cấu hình.

**Không có upload production** chỉ vì `site:run` chạy thành công.

### `site:stage` — ghép cây site preview local

```bash
mvn -B -ntp site
mvn -B -ntp site:stage
```

Site Plugin stage dựa vào site distribution URL và project hierarchy, tạo preview, mặc định ở:

```text
target/staging/
```

Bạn có thể chỉ định **đường dẫn tuyệt đối**:

```bash
mvn -B -ntp site:stage -DstagingDirectory=/tmp/maven-site-preview
```

Đây vẫn là **local filesystem staging**, không phải publication lên production. `site:stage` cần site đã generate; gọi riêng sau `clean` mà chưa generate có thể lỗi.

### `site:stage-deploy` — publication tới staging, không phải local-only

Đừng nhầm `site:stage-deploy` với `site:stage`. Goal `stage-deploy` dùng Wagon transfer tới **staging URL** đã được cấu hình. Nó có **side effect từ xa** nếu đích remote, và cũng cần quyền/credentials đúng.

Một ví dụ cú pháp mang tính khái niệm:

```bash
mvn site
mvn site:stage-deploy -DstagingSiteURL=scp://staging.example.invalid/var/www/docs-preview/
```

**Không chạy nguyên xi:** URL placeholder và auth/transport chưa cấu hình. Chọn staging destination thật được cấp quyền; kiểm tra phiên bản plugin và tham số `stagingSiteURL` bằng `site:help -Ddetail=true -Dgoal=stage-deploy` trước khi dùng trong CI.

## 12. Multi-module: tại sao cần staging trước publish?

Giả sử Maven reactor:

```text
team-platform/
├── pom.xml       # aggregator + parent, packaging=pom
├── api/pom.xml
└── cli/pom.xml
```

Chạy:

```bash
mvn site
```

thường có site tách riêng:

```text
team-platform/target/site/
team-platform/api/target/site/
team-platform/cli/target/site/
```

Cả ba đều hợp lệ về mặt file build, nhưng **liên kết tương đối giữa modules có thể bị sai** khi chỉ mở `api/target/site/index.html`. Đó không nhất thiết là lỗi report generation.

### Dùng `site:stage` để kiểm tra layout website cuối

```bash
mvn site
mvn site:stage
```

Staging tập hợp các sites theo cấu trúc mà Maven định dùng khi deploy để có thể xem parent/child links. Điều này quan trọng vì `mvn site` tạo site cho từng project tại `target/site` của module, không thể hiện đầy đủ cấu trúc publish cuối.

### URL inheritance và nguy cơ ghi đè

Khi children kế thừa site URL của parent, Maven thường tự append `artifactId` của child để tránh cùng một directory:

```text
parent site: /docs/team-platform/
api site:    /docs/team-platform/api/
cli site:    /docs/team-platform/cli/
```

Đây là mô hình điển hình nếu không override URL. Nếu tự cấu hình nhiều project dùng **cùng một site URL không có subfolder**, các file `index.html`, `css/*`... có thể ghi đè nhau. Với reactor nhiều modules, nên kiểm tra effective site URL và cây staging trước khi publish.

Một điểm kỹ thuật: mục tiêu `site:deploy` không được Site Plugin 3.22.0 đánh dấu **thread-safe**. Đừng dựa vào `mvn -T 4 site-deploy` mà kỳ vọng upload đồng thời an toàn; với shared publish paths nên chạy tuần tự và kiểm tra kết quả.

## 13. Generate và publish nên tách thành hai CI jobs

Một quy trình tài liệu website thực tế có thể là:

```text
Commit/PR
  |
mvn -B -ntp clean verify site
  |
Kiểm tra target/site/index.html, guide.html, reports, links
  |
Lưu target/site như CI artifact (kèm commit SHA)
  |
Stage preview nếu multi-module
  |
Review + approval + whitelist destination
  |
Trusted branch/tag + publish credentials
  |
mvn site:deploy hoặc một static-site publisher tương thích
  |
HTTP GET/permission/cache checks trên đích
```

**Lưu ý:** `mvn clean verify site` chạy Java tests/build rồi Site Plugin, chứ `mvn site` riêng không tự đảm bảo Surefire/Failsafe pass. Nếu website có báo cáo tests/coverage, phải bảo đảm reports được tạo trước và `<reporting>` có plugin thực sự chuyển chúng thành trang HTML.

### Khi nào nên dùng `mvn site-deploy` trong CI?

Khi publisher có quyền đọc source/POM và bạn muốn **generate rồi publish trong cùng một invocation**, `mvn site-deploy` thuận tiện. Tuy nhiên, nếu CI đã QA chính xác các bytes trong `target/site` ở job trước, chạy `mvn site-deploy` tại môi trường khác có thể generate lại nội dung khác do Maven/plugin/data/time.

Muốn publish **đúng output đã review**:

- Lưu và chuyển site artifacts giữa jobs theo checksum/commit.
- Ở publish job, tránh regenerate không chủ đích; dùng goal `site:deploy` trên generated site hoặc một publisher trực tiếp phục vụ static files.
- Có kiểm tra destination allowlist, quyền upload, thư mục và version.
- Sau deploy đọc file hoặc HTTP endpoint thực tế để xác nhận content version.

### Release versioned docs và rollback

Một chiến lược giúp giảm rủi ro:

```text
docs.example.invalid/team-platform/1.0.0/
docs.example.invalid/team-platform/1.1.0/
docs.example.invalid/team-platform/current/
```

Dùng destination theo version và chỉ đổi alias `current` sau validation. `site:deploy` tự nó không cung cấp **atomic deployment**, versioned rollback hoặc tự xóa mọi file cũ. Nếu truyền file bị lỗi giữa chừng, destination có thể chứa hỗn hợp trang cũ/mới. Với production, tổ chức cần staging upload, atomic switch/symlink/CDN switch, backup và kiểm tra sau chuyển.

## 14. “Site đã build” khác “site có nội dung mới”

Site Plugin có thể tối ưu render theo timestamp. Nếu source Markdown không đổi thì có thể không regenerate tài liệu, trong khi `pom.xml`, `site.xml`, properties hoặc resources thay đổi. Vì vậy docs chính thức khuyến nghị generate sạch khi có thay đổi ảnh hưởng link/menu:

```bash
mvn clean site
```

Nhưng **không** nên chạy `mvn clean` **giữa** generate và deploy. Cần tạo site mới rồi giữ nguyên đến lúc chuyển nó.

Các nguyên nhân “site deploy xong nhưng nội dung cũ”:

- CI lấy sai commit/tag.
- `target/site` còn output cũ và không clean khi cần.
- Site output mới nhưng destination URL trỏ tới path khác web root.
- Transfer thành công nhưng CDN/browser cache vẫn phục vụ bản cũ.
- Deployment của module con ghi lên directory không đúng.
- SitePlugin staging/publishing giữ lại tệp cũ mà bạn nghĩ sẽ bị xóa.
- Link tới site khác hoặc absolute URL sai trong descriptor.

**Build success chỉ là một chỉ báo của quá trình build**, không phải bằng chứng hoàn chỉnh người dùng thấy nội dung đúng.

## 15. Xác minh website sau khi publish

Cần kiểm tra nhiều tầng:

| Tầng kiểm chứng | Câu hỏi | Phương pháp |
| --- | --- | --- |
| 1. Source | Docs nằm đúng vị trí và menu href đúng? | Xem `src/site/markdown`, `src/site/site.xml` |
| 2. Render | `target/site` có HTML/asset đúng? | Filesystem check, mở browser, link checker |
| 3. Staging | Parent/child link layout đúng? | `site:stage`, preview cây tổng hợp |
| 4. Transfer | Các files có xuất hiện ở `distributionManagement.site.url`? | Listing/checksum ở destination |
| 5. Hosting | HTTP URL có trả 200, Content-Type đúng, TLS hợp lệ? | HTTP GET/headers/browser |
| 6. Freshness | Phiên bản tài liệu khớp commit/release? | SHA/version marker, checksum |
| 7. Access | User được phép thấy trang; trang nội bộ không bị public? | AuthZ/security review |
| 8. Cache | CDN/browser nhận bản mới? | Cache invalidation/URL versioning |

### Câu lệnh kiểm tra local files

Linux/macOS:

```bash
test -f target/site/index.html
test -f target/site/guide.html
grep -n 'Maven Site Boundaries' target/site/index.html
```

Windows PowerShell:

```powershell
Test-Path target\site\index.html
Test-Path target\site\guide.html
Select-String -Path target\site\index.html -Pattern 'Maven Site Boundaries'
```

Nếu dùng remote hosting thật, truy cập URL dự kiến bằng browser hoặc HTTP GET sau deploy. Nếu cần kiểm tra `http://`/`https://`, hãy dùng **đúng URL public của site**, không lấy `scp://` deployment URL rồi cho rằng browser có thể mở trực tiếp.

## 16. Những lỗi hay gặp và cách giải quyết

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `mvn site` pass nhưng web công ty chưa đổi | Chỉ generate local, không publish | Dùng `site:deploy` sau review hoặc site-deploy phase |
| `mvn site:deploy` không thấy site | Chưa generate, hoặc vừa `clean` | Chạy `mvn site` trước, giữ `target/site` |
| `mvn site-deploy` bất ngờ upload docs | Lệnh là lifecycle phase bao gồm deploy | Phân biệt dấu `-` và `:`; kiểm tra quyền |
| `mvn deploy` thành công nhưng docs không cập nhật | Đang publish Java Maven artifacts | Dùng Site Plugin, không phải Maven Deploy Plugin |
| Plugin yêu cầu site URL | `distributionManagement.site.url` thiếu | Khai địa chỉ site destination hợp lệ |
| HTTP web 404 dù files đã upload | Web root path/routing/permissions sai | Kiểm tra serving config, upload directory, public URL |
| Report không xuất hiện | Plugin chỉ ở `build`, không trong `reporting` | Khai reporting plugin/reportSets, regenerate |
| Guide có file nhưng không có menu link | `site.xml` thiếu `item` hoặc href sai | Khai `href="guide.html"`, không dùng `guide.md` |
| 404 CSS/images | Resources/relative prefix/skin path sai | Xem `src/site/resources`, build/stage/public URL |
| Multi-module link fail local | Site ở từng module directory tách biệt | Dùng `site:stage`/check deployed layout |
| Hai modules ghi đè index của nhau | Cùng site URL không subdir | Dùng inherited URL/artifactId path hoặc override |
| Site stale sau thay POM/site.xml | Incremental generation/cache | `mvn clean site`, kiểm tra html output |
| Upload `scp://` lỗi | Credential, host key, Wagon provider hoặc permission | Kiểm tra `settings.xml`, protocol/extension, SSH server |
| `site:deploy` thành công nhưng người dùng thấy cũ | CDN/browser cache hoặc sai URL | Kiểm tra cache invalidation/HTTP GET và digest |
| `site:stage-deploy` ghi nhầm production | Staging URL/scope sai | Kiểm tra `stagingSiteURL`, server id và allowlist |
| `site:run` tạo server nhưng site không public | Nó chỉ là preview | Publish riêng nếu cần |
| Windows file:///tmp không hợp lệ | Đang dùng path POSIX trong POM demo | Dùng `file:///C:/...` và đúng Windows directory |
| `mvn site` không chạy tests | Site lifecycle riêng | Chạy `mvn verify site`, cấu hình report plugin |
| CI publish docs của commit khác | Chuyển sai build artifact/workspace | Pin commit SHA, dùng checksums |
| CI dùng `-T` và deploy lỗi ngẫu nhiên | Site deploy goal không thread-safe | Chạy serial, không cùng publish path |
| Site report đưa thông tin nội bộ ra public | Project reports chứa URLs/metadata nhạy cảm | Review output và hạn chế public reports |

### Lệnh debug an toàn hơn trước deploy

```bash
mvn -version
mvn help:effective-pom
mvn -B -ntp site
mvn -B -ntp site:effective-site
mvn -B -ntp site:stage
mvn -B -ntp site:help -Ddetail=true -Dgoal=deploy
```

`site:effective-site` hiển thị effective site descriptor/menu sau inheritance và interpolation. Nó **không upload** trang site.

Nếu thực sự cần debug transfer:

```bash
mvn -B -ntp -e site:deploy
mvn -B -ntp -X site:deploy
```

**Cảnh báo:** hai lệnh cuối **có hành động publish**; đừng chạy trên production chỉ để xem log. `-X` có thể in endpoint, local paths, system properties và cấu hình nhạy cảm, cần rà soát trước khi chia sẻ.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** `mvn site` tạo `target/site/index.html`, vậy site có trên Internet chưa?

**Đáp án:** Chưa. Nó chỉ generate output tại workspace, không upload.

**Câu 2:** `mvn site:deploy` khác `mvn site-deploy` điểm cốt lõi nào?

**Đáp án:** `site:deploy` là một **plugin goal** deploy site đã generate; `site-deploy` là **lifecycle phase** chạy site generation rồi deployment.

**Câu 3:** Lệnh nào chỉ tạo preview local có layout đầy đủ cho multi-module?

**Đáp án:** `mvn site` rồi `mvn site:stage`. `stage` không publish production.

**Câu 4:** `mvn site:stage-deploy` có nhất thiết chỉ tạo file local?

**Đáp án:** Không. Nó có thể publish đến staging URL qua Wagon, có remote side effects.

**Câu 5:** Cấu hình `<distributionManagement><site>` đã đủ khiến `mvn site` tự upload?

**Đáp án:** Không. Cấu hình mô tả destination, còn goal/phase quyết định thời điểm upload.

**Câu 6:** `mvn deploy` có đưa `target/site/index.html` lên website không?

**Đáp án:** Không mặc định. Nó dùng default lifecycle Maven artifacts, khác site lifecycle.

**Câu 7:** Đặt URL public ở `<url>` cấp project có thay `distributionManagement.site.url` được không?

**Đáp án:** Không. Project URL mô tả homepage; site URL mới là Wagon deployment location.

**Câu 8:** Vì sao cần `site:stage` cho multi-module?

**Đáp án:** Site của mỗi module được tạo dưới `module/target/site` riêng, nên intermodule relative links có thể sai cho đến khi được ghép theo publish hierarchy.

**Câu 9:** Nếu `mvn site:deploy` báo success nhưng web public vẫn 404 thì kiểm tra gì?

**Đáp án:** So destination filesystem với web root/routing, permissions, URL prefix, TLS và caching; transfer success không đồng nghĩa HTTP serving đúng.

**Câu 10:** Vì sao không để production credentials trong POM?

**Đáp án:** POM nằm trong source control và có thể bị PR sửa/lộ. Credentials thuộc `settings.xml`/secret manager và chỉ xuất hiện trong publish job đáng tin.

## 18. Checklist trước khi kết luận “site đã xuất bản”

- [ ] Biết rõ mình đang **generate**, **stage** hay **publish**.
- [ ] Không nhầm `mvn site` với `mvn site:deploy`.
- [ ] Không nhầm goal `site:deploy` với phase `site-deploy`.
- [ ] Không dùng `mvn deploy` để thay website publishing.
- [ ] Site Plugin/report plugins được pin version, tương thích Maven/JDK.
- [ ] Tài liệu ở đúng `src/site/<format>`, đặc biệt Markdown index/guide.
- [ ] `site.xml` có links đúng output HTML, không dẫn tới nguồn .md.
- [ ] Reports được khai ở `<reporting>` khi cần.
- [ ] Tests/report data được tạo trước site nếu nội dung website dựa trên chúng.
- [ ] `target/site/index.html` và pages chính tồn tại.
- [ ] Giao diện/menu/encoding/links/assets đã kiểm tra.
- [ ] Multi-module đã stage và kiểm tra link giữa modules.
- [ ] Không publish output stale từ workspace/commit cũ.
- [ ] `distributionManagement.site.url` chỉ tới destination được phép.
- [ ] Không có modules/projects cùng upload đè lên một site root.
- [ ] Wagon protocol provider/permissions và `settings.xml` server id đúng.
- [ ] Không đặt secrets trong POM, docs hoặc debug logs.
- [ ] Chỉ trusted branch/tag và publish job có credentials.
- [ ] Site có staging/version path/rollback strategy khi cần.
- [ ] Sau deploy đã xác minh files ở destination.
- [ ] Nếu có public site, đã kiểm tra HTTP URL/permissions/cache.
- [ ] Báo cáo tách **`SITE_GENERATED`** khỏi **`SITE_DEPLOYED_VERIFIED`**.

**Kết luận:** `mvn site` sinh website dự án dưới **`target/site`**; `mvn site:deploy` chuyển **site đã được tạo** đến **`distributionManagement.site.url`**; `mvn site-deploy` là phase của site lifecycle nên **generate rồi publish**. `site:stage` phục vụ kiểm tra cây preview local, `site:stage-deploy` có thể publish đến staging, còn `mvn deploy` thuộc default lifecycle để phát hành Java artifacts. Để tuyên bố website đã được xuất bản, phải **kiểm chứng destination và URL người dùng truy cập**, không chỉ xem `BUILD SUCCESS`.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Site Plugin 3.22.0 — Introduction](https://maven.apache.org/plugins/maven-site-plugin/)
- [Apache Maven Site Plugin — Usage: Generating, Deploying and Staging](https://maven.apache.org/plugins/maven-site-plugin/usage.html)
- [Apache Maven Site Plugin — site:site](https://maven.apache.org/plugins/maven-site-plugin/site-mojo.html)
- [Apache Maven Site Plugin — site:deploy](https://maven.apache.org/plugins/maven-site-plugin/deploy-mojo.html)
- [Apache Maven Site Plugin — site:stage](https://maven.apache.org/plugins/maven-site-plugin/stage-mojo.html)
- [Apache Maven Site Plugin — Creating Content](https://maven.apache.org/plugins/maven-site-plugin/examples/creating-content.html)
- [Apache Maven Site Plugin — Site Descriptor](https://maven.apache.org/plugins/maven-site-plugin/examples/sitedescriptor.html)
- [Apache Maven Site Plugin — Configuring Reports](https://maven.apache.org/plugins/maven-site-plugin/examples/configuring-reports.html)
- [Apache Maven — Building Multi-module Sites](https://maven.apache.org/guides/mini/guide-multimodule-site.html)
- [Apache Maven Site Plugin — Inheritance of Site Distribution Management](https://maven.apache.org/plugins/maven-site-plugin/examples/inheritance-site-distribution-management.html)
- [Apache Maven Project Info Reports Plugin](https://maven.apache.org/plugins/maven-project-info-reports-plugin/)

*Bài hướng dẫn dùng Java 17, Maven 3.9.x, Site Plugin 3.22.0 và Project Info Reports 3.9.0. Ví dụ file-based deployment chỉ dành cho môi trường local được cấp quyền; các lệnh publish chưa được thực thi trên server thật.*
