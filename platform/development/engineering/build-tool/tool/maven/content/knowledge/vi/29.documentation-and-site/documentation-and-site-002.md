# Maven Site Plugin và vòng đời site: tạo tài liệu, báo cáo và xuất bản an toàn

## 1. Maven Site giải quyết vấn đề gì?

Một dự án Maven có thể build JAR thành công nhưng vẫn thiếu tài liệu cho người dùng, người bảo trì hoặc hệ thống CI: cách chạy ứng dụng, hướng dẫn phát triển, cấu trúc module, dependency graph, báo cáo Javadoc, tình trạng kiểm thử hay thông tin liên hệ. **Apache Maven Site Plugin** giúp biến tài liệu nguồn và các báo cáo được cấu hình thành một **website tĩnh** thống nhất.

Khác với `maven-compiler-plugin` tạo class files hay `maven-jar-plugin` tạo JAR, Site Plugin không phải công cụ chạy ứng dụng. Nó kết hợp ba thành phần:

1. **Doxia** đọc các định dạng tài liệu như Markdown, APT, FML hoặc XDoc và chuyển chúng thành nội dung HTML.
2. **Doxia Sitetools/Site Renderer** áp dụng giao diện (**skin**), menu, banner, liên kết và trang trí chung từ `site.xml`.
3. **Maven Reporting** điều phối những reporting goals được khai báo trong `<reporting>` của POM, ví dụ thông tin dependencies, project summary, Javadoc hoặc báo cáo kiểm thử khi đã cấu hình đúng.

Kết quả mặc định thường nằm trong:

~~~text
target/site/
├── index.html
├── guide.html
├── css/
├── images/
└── ... các báo cáo HTML được tạo theo cấu hình
~~~

**Điểm quan trọng:** sinh site ở `target/site` chỉ tạo **file trên máy build**. Đưa những file đó lên website công cộng, máy chủ nội bộ hay Git-based hosting là một **bước xuất bản riêng**, cần cấu hình đích, quyền và kiểm soát thông tin.

Bài học này phân biệt **ba lifecycle của Maven**, bốn phase trong **site lifecycle**, các goal của Site Plugin, cách viết tài liệu bằng Markdown và `site.xml`, cách cấu hình báo cáo, rồi hướng dẫn preview, stage, deploy và kiểm chứng CI. Ví dụ sử dụng **Maven 3.x + Java 17** và **không cần server deploy thực**.

## 2. Maven có ba lifecycle: default, clean và site

Maven không có một chuỗi phase duy nhất. Ba lifecycle quan trọng là:

| Lifecycle | Mục đích | Các phase thường dùng |
| --- | --- | --- |
| **default** | Build và kiểm thử artifact ứng dụng. | `validate`, `compile`, `test`, `package`, `verify`, `install`, `deploy`... |
| **clean** | Dọn sản phẩm build trước đó. | `pre-clean`, `clean`, `post-clean`. |
| **site** | Sinh và có thể xuất bản website tài liệu. | `pre-site`, `site`, `post-site`, `site-deploy`. |

Đừng lẫn `deploy` của **default lifecycle** với `site-deploy` của **site lifecycle**:

- `mvn deploy` mặc định xuất bản **artifact POM/JAR/WAR** lên artifact repository theo `<distributionManagement><repository>` và quy trình tương ứng.
- `mvn site-deploy` thực thi **site lifecycle tới phase site-deploy**, có thể xuất bản **HTML site** tới địa chỉ `<distributionManagement><site>`.
- Một dự án có thể dùng repository lưu JAR và host website ở **hai hệ thống hoàn toàn khác nhau**.
- `mvn site` **không tương đương** với `mvn deploy`, cũng **không tự đẩy HTML** ra mạng.

### Sơ đồ ba lifecycle

~~~text
Maven default:
  validate -> compile -> test -> package -> verify -> install -> deploy

Maven clean:
  pre-clean -> clean -> post-clean

Maven site:
  pre-site -> site -> post-site -> site-deploy
                         |
                         +-- Khi dừng ở phase "site" thì chưa deploy
~~~

Mỗi lifecycle có semantics riêng. Khi gõ `mvn site`, Maven chạy các phase site lifecycle **từ đầu đến site**, không tự chạy `post-site` hay `site-deploy`. Khi gõ `mvn site-deploy`, Maven chạy qua các phase **đến site-deploy**, bao gồm các phase trước đó.

**Không lấy tên goal trùng phase làm bằng chứng chúng là cùng một thao tác.** `site:site` là một **plugin goal**, còn `site` là một **lifecycle phase**. Chúng có liên hệ do Maven binding, nhưng không hoàn toàn tương đương về các phase đã được thực thi.

## 3. Bốn phase của site lifecycle

### `pre-site`

Dành cho những bước cần trước khi sinh site: chuẩn bị tài liệu do công cụ khác tạo, xác nhận nội dung, sinh dữ liệu đầu vào, hoặc kiểm tra điều kiện môi trường. Maven core **không bắt buộc phải chạy một goal riêng** ở phase này nếu POM không bind gì thêm.

**Ví dụ ý tưởng:** một plugin được cấu hình sinh tài liệu API dạng nguồn Doxia trước khi Site Plugin render. Đừng tự cho rằng `mvn site` luôn biên dịch Java hay chạy test trong phase này.

### `site`

Là phase tạo website. Trong Maven 3, phase này được binding tới goal của Maven Site Plugin để render tài liệu và báo cáo theo POM. Đầu ra mặc định nằm dưới `${project.reporting.outputDirectory}`, thông thường **`target/site`**.

Maven xử lý nội dung trong `src/site` (nếu có), áp `site.xml`, chạy reporting goals và tạo HTML. Những report plugins khác nhau có thể yêu cầu source, class files hoặc kết quả test đã tồn tại. **`mvn site` không đồng nghĩa đã chạy `mvn test` hoặc `mvn verify`**.

### `post-site`

Dành cho công việc **sau khi sinh site nhưng trước khi publish**, chẳng hạn kiểm tra broken links, thêm metadata đã duyệt, audit HTML, hoặc chuẩn bị gói upload. Nếu không có goal được bind thì phase này không tự sinh thêm công việc.

**Cần chú ý:** thông thường `mvn site` dừng **trước post-site**. Muốn kiểm chứng riêng cả post-site mà không deploy có thể dùng `mvn post-site`, nhưng chỉ khi biết các goal đã bind ở đó và chúng không tạo side effects ngoài ý muốn.

### `site-deploy`

Phase thực hiện công việc xuất bản site. Với binding của site lifecycle, Maven Site Plugin có goal `site:deploy`, dùng đích site URL trong `<distributionManagement>` và giao thức được Maven Wagon/provider hỗ trợ.

**Đây là thao tác có thể ghi dữ liệu ra hệ thống ngoài.** Không dùng `mvn site-deploy` chỉ để xem site trên máy, không chạy trên repository/job chưa được phép publish.

### Bảng ghi nhớ

| Lệnh | Điều gì xảy ra? | Có publish site không? |
| --- | --- | --- |
| `mvn site` | Chạy site lifecycle tới phase `site`. | **Không**. |
| `mvn post-site` | Chạy tới `post-site`, gồm sinh site trước đó. | **Không**, trừ side effects tùy biến ở các goal đã bind. |
| `mvn site-deploy` | Chạy site lifecycle tới `site-deploy`. | **Có thể có**, nếu đích/credentials/protocol hợp lệ. |
| `mvn site:site` | Gọi trực tiếp Site Plugin goal. | **Không**. |
| `mvn site:deploy` | Gọi trực tiếp goal deploy trên output site đã có. | **Có thể có**, không tự là quy trình build/site đầy đủ. |
| `mvn clean site` | Dọn `target`, sau đó sinh site mới. | **Không**. |
| `mvn verify site` | Chạy build/test/verify rồi sinh site trong cùng lệnh Maven. | **Không**. |

**Cẩn trọng với `mvn post-site`:** lệnh không tự thực thi default lifecycle `verify`; nếu có reporting goal cần kết quả test thì hãy chủ động tạo các kết quả đó trước.

## 4. Site Plugin: các goal liên quan nhưng không giống nhau

| Goal | Vai trò | Khi dùng |
| --- | --- | --- |
| **`site:site`** | Sinh site cho project. | Gọi trực tiếp nếu không cần những execution ở `pre-site`. |
| **`site:run`** | Dựng web server để preview, render theo yêu cầu. | Vòng lặp chỉnh sửa tài liệu trên máy phát triển. |
| **`site:stage`** | Tạo cây site staging **cục bộ** theo site URL và cấu trúc module. | Kiểm tra liên kết/cây URL trước publish. |
| **`site:stage-deploy`** | Gửi site đến một URL staging/mock dùng Wagon. | Chỉ khi môi trường staging được phép ghi. |
| **`site:deploy`** | Đẩy site tới địa chỉ đã cấu hình trong distributionManagement. | Bước phát hành có phê duyệt. |
| **`site:effective-site`** | Hiển thị site descriptor hiệu lực sau inheritance/interpolation. | Chẩn đoán menu/skin/site inheritance. |
| **`site:attach-descriptor`** | Gắn descriptor vào artifacts được install/deploy để hỗ trợ site inheritance. | Site chung cho nhiều module/parent theo thiết kế. |
| **`site:jar`** | Đóng gói website thành JAR để lưu trữ/phân phối dưới dạng artifact. | Khi tổ chức muốn lưu site qua artifact repository. |

`site:stage` **không phải deploy production**, nhưng nó cần dữ liệu URL/structure phù hợp; thường dùng sau `mvn site`, đặc biệt hữu ích với site đa module. `site:stage-deploy` khác vì có thể gửi nội dung tới một **đích staging từ xa**. Không coi hai goal này là từ đồng nghĩa.

Một số goal phụ thuộc phiên bản Site Plugin; hãy đối chiếu đúng **plugin version** mà dự án pin trong POM. Ví dụ dưới dùng **Maven Site Plugin 3.12.1** thuộc nhánh ổn định của Maven 3, không khẳng định là bản mới nhất hiện tại.

## 5. Phân biệt `<build>` với `<reporting>`

Đây là nguồn nhầm lẫn phổ biến khi thêm báo cáo.

### `<build><plugins>`

Khai báo plugin tham gia **quy trình build**, có thể bind executions vào phases và cấu hình goals. Ví dụ Site Plugin được chốt version:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-site-plugin</artifactId>
            <version>3.12.1</version>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn POM minh họa**, không phải file độc lập. Site Plugin dùng để render site; việc khai báo nó ở build không tự động làm `mvn test` sinh HTML.

### `<reporting><plugins>`

Khai báo **report plugins** để Site Plugin biết những báo cáo nào cần render vào website:

~~~xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-project-info-reports-plugin</artifactId>
            <version>3.5.0</version>
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
    </plugins>
</reporting>
~~~

**`maven-project-info-reports-plugin`** tạo trang tổng quan dự án, dependencies và plugins bằng metadata từ POM. Các reports được chọn **không tự trở thành dependencies của ứng dụng** và cũng không thay runtime classpath.

Lựa chọn `<reportSets>` tránh chạy tất cả reporting goals một cách vô ý; hữu ích khi một report plugin có **aggregate** và **non-aggregate** goals với chi phí/đầu ra khác nhau.

Nếu muốn thêm **Javadoc**, **JXR**, **Surefire Report**, **Checkstyle**, **PMD** hoặc **JaCoCo** lên site, phải chọn report plugin tương ứng và cấu hình goal/phạm vi phù hợp. Đừng giả định mọi thứ tự xuất hiện chỉ vì Java project có tests.

## 6. Một dự án Java 17 hoàn chỉnh để thử site lifecycle

Bài thực hành tạo một project Maven đơn module, có:

- Mã Java 17 đơn giản và một JUnit Jupiter test.
- Trang chủ **Markdown** và trang hướng dẫn.
- `site.xml` khai báo navigation và **skin**.
- Project Info reports tạo summary/dependencies/plugins.
- `maven-site-plugin:3.12.1`, `maven-fluido-skin:1.11.2` và `maven-project-info-reports-plugin:3.5.0` được pin để tránh mặc định thay đổi.

**Yêu cầu chạy:** Maven 3.x thích hợp, JDK 17+ và Maven repository truy cập được các artifact đã chốt. Ví dụ không deploy lên mạng và không dùng dữ liệu bí mật.

Cấu trúc project:

~~~text
site-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/site/SiteGreeting.java
    ├── test/
    │   └── java/vn/example/site/SiteGreetingTest.java
    └── site/
        ├── site.xml
        └── markdown/
            ├── index.md
            └── guide.md
~~~

**Không thêm `target/site` vào source control như một bản tài liệu nguồn.** Đây là output được tạo từ POM và `src/site`; CI có thể giữ làm artifact để duyệt hoặc publish có kiểm soát.

### 6.1. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>site-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Site Lifecycle Demo</name>
    <description>Ví dụ Maven Site và báo cáo dự án</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    </properties>

    <dependencies>
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
                <artifactId>maven-site-plugin</artifactId>
                <version>3.12.1</version>
            </plugin>
        </plugins>
    </build>

    <reporting>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-project-info-reports-plugin</artifactId>
                <version>3.5.0</version>
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
        </plugins>
    </reporting>
</project>
~~~

### Vì sao POM này hữu ích?

1. `project.build.sourceEncoding=UTF-8` và `project.reporting.outputEncoding=UTF-8` giảm nguy cơ lỗi dấu tiếng Việt khi đọc Markdown hoặc ghi HTML.
2. Site Plugin được khai báo **ở build/plugins** với version cố định.
3. Reporting Plugin nằm **ở reporting/plugins** với ba goals cụ thể, không phải ở application dependencies.
4. JUnit Jupiter có scope `test` để không đưa thư viện kiểm thử vào runtime artifact.
5. Compiler/Surefire Plugin được pin để khi `mvn verify` chạy, kết quả không phụ thuộc phiên bản plugin mặc định từ môi trường.
6. **POM không có `<distributionManagement><site>`**, vì bài học chỉ tạo site nội bộ; lệnh `mvn site` an toàn hơn việc vô ý publish từ một demo.
7. POM cũng không bind `site:site` vào phase `package`: site lifecycle đã là một lifecycle riêng; người dùng chủ động chọn khi nào tạo tài liệu.

Các plugin và skin versions chỉ là **baseline được chốt cho bài học**, không phải khẳng định chúng mới nhất. Khi áp dụng dự án thật, cần chọn những versions được tổ chức hỗ trợ và kiểm chứng compatibility giữa Site Plugin, skin, Doxia, reporting plugins và Maven/JDK.

## 7. Java 17 và unit test cho dự án mẫu

### 7.1. `src/main/java/vn/example/site/SiteGreeting.java`

~~~java
package vn.example.site;

public final class SiteGreeting {
    private SiteGreeting() {
    }

    public static String message() {
        return "Maven Site: OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Class không có dependencies ngoài JDK. Khi chạy:

~~~bash
mvn -B -ntp clean verify
java -cp target/classes vn.example.site.SiteGreeting
~~~

stdout **chính xác của riêng lệnh Java** là:

~~~text
Maven Site: OK
~~~

`mvn verify` **không tự gọi main**. Lệnh Java cuối chạy class đã biên dịch từ `target/classes`; phần tạo HTML site là bước khác.

### 7.2. `src/test/java/vn/example/site/SiteGreetingTest.java`

~~~java
package vn.example.site;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SiteGreetingTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Maven Site: OK", SiteGreeting.message());
    }
}
~~~

Unit test này chạy trong default lifecycle tại phase `test` qua Surefire. Chạy `mvn site` riêng **không bảo đảm test đã được chạy**; nếu muốn site có những báo cáo dựa vào test results, hãy chạy default lifecycle trước.

**Một số report plugins** có thể đọc kết quả test, phân tích classes, source files hoặc bytecode; khi cần, cấu hình đúng plugin và thứ tự build, không coi tất cả report goals chỉ đọc POM.

## 8. Site descriptor: `src/site/site.xml`

Tạo file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<site xmlns="http://maven.apache.org/SITE/2.0.0"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://maven.apache.org/SITE/2.0.0 https://maven.apache.org/xsd/site-2.0.0.xsd"
      name="Site Lifecycle Demo">

    <skin>
        <groupId>org.apache.maven.skins</groupId>
        <artifactId>maven-fluido-skin</artifactId>
        <version>1.11.2</version>
    </skin>

    <body>
        <menu name="Tài liệu">
            <item name="Trang chủ" href="index.html"/>
            <item name="Hướng dẫn" href="guide.html"/>
        </menu>
        <menu ref="reports"/>
    </body>
</site>
~~~

### Giải thích

- `site.xml` mô tả **navigation, skin và presentation**, không phải source content của trang chủ.
- `<skin>` xác định artifact skin được tải để render HTML. Với Site Plugin 3.12.1, **Fluido Skin 1.11.2** thuộc dòng 1.x tương thích, không trộn bừa với Fluido Skin 2.1.0 được thiết kế cho các Site Plugin mới hơn.
- `<menu name="Tài liệu">` chứa links tới các trang do người viết tạo.
- `<menu ref="reports"/>` để Site Renderer chèn menu của các report đã sinh. Nếu không có báo cáo phù hợp, không nên kỳ vọng menu chứa những trang chưa được tạo.
- `href="index.html"` và `href="guide.html"` liên hệ trực tiếp tới những Markdown files trong mục tiếp theo, **không dùng đuôi `.md` trong link HTML đầu ra**.
- XML dùng `UTF-8` để giữ tên menu tiếng Việt; cần kiểm tra build trên môi trường CI với encoding phù hợp.

**Không dùng placeholder `${reports}` cũ** trong site.xml; cú pháp menu reference `ref="reports"` rõ ràng hơn và là cách được tài liệu Site Plugin khuyến nghị.

Với site đa module, có thể thêm `<menu ref="modules"/>` nếu các module sites thực sự được tạo và staging/deployment URLs cấu hình đúng. Đừng thêm links tới module chưa tồn tại.

## 9. Trang chủ Markdown: `src/site/markdown/index.md`

~~~markdown
# Site Lifecycle Demo

Trang tài liệu được sinh từ Markdown bằng Maven Site Plugin.

## Bắt đầu

Ứng dụng Java 17 in ra thông báo `Maven Site: OK`.

Để kiểm tra mã nguồn:

```bash
mvn clean verify
java -cp target/classes vn.example.site.SiteGreeting
```

## Điều hướng

- [Hướng dẫn chạy](guide.html)
- Các báo cáo project nằm trong menu **Project Reports** nếu được tạo.

## Phạm vi

Website này là tài liệu tĩnh, không phải ứng dụng web server
và không cần publish lên máy chủ để xem nội bộ.
~~~

**Đây là nội dung nguyên văn của một file `.md`**, không phải lệnh shell và không cần copy các dấu `~~~markdown` bao ngoài vào file. Doxia đọc Markdown tại `src/site/markdown/index.md` và tạo **`target/site/index.html`**.

Dùng Markdown headings/link/code fences giúp nội dung dễ đọc trong cả repository và website. Với cú pháp Markdown nâng cao (tables, Mermaid, plugins mở rộng...), hãy kiểm tra Doxia parser của phiên bản Site Plugin thực tế; **không mặc định mọi extension của GitHub Flavored Markdown đều được hỗ trợ y hệt**.

## 10. Trang thứ hai: `src/site/markdown/guide.md`

~~~markdown
# Hướng dẫn sử dụng

## Yêu cầu

- Java 17 hoặc mới hơn.
- Maven tương thích với những plugin đã được chốt trong `pom.xml`.

## Lệnh chạy

```bash
mvn clean verify site
java -cp target/classes vn.example.site.SiteGreeting
```

## Kết quả

Lệnh Java in:

```text
Maven Site: OK
```

## Kiểm tra tài liệu

Mở file `target/site/index.html` hoặc dùng một local HTTP server
để xem trang chủ, menu và các báo cáo.

Quay về [trang chủ](index.html).
~~~

Doxia chuyển file thành `target/site/guide.html`. Các liên kết tới `index.html`/`guide.html` được viết theo **đường dẫn đầu ra**. Không dùng `<a href="src/site/markdown/guide.md">` vì cấu trúc source không phải cấu trúc website sau render.

**Khi xem bằng `file://`, một số CSS/scripts hoặc link tương đối có thể khác so với host HTTP.** Có thể dùng `site:run` hoặc một static HTTP server cục bộ để kiểm tra hành vi trang trong môi trường gần thực tế, nhưng không cần deploy production.

## 11. Sinh site lần đầu và kiểm tra đầu ra

Ở thư mục root chứa POM:

~~~bash
mvn --version
mvn -B -ntp clean verify site
~~~

Lệnh trên thực thi:

1. **`clean`** dọn output build cũ.
2. **`verify`** chạy default lifecycle (trong đó có compile, unit test, package và những goals đã bind).
3. **`site`** chạy site lifecycle tới phase `site` để sinh HTML.

**Không giả định Maven chạy site ngay sau mỗi `mvn verify`** khi người dùng không yêu cầu phase `site` hoặc không cấu hình execution tương ứng.

Những file cần kiểm tra:

~~~text
target/classes/vn/example/site/SiteGreeting.class
target/surefire-reports/...
target/site/index.html
target/site/guide.html
target/site/css/...
target/site/... các Project Info reports
~~~

Dấu `...` ở đây có nghĩa **nhiều file thực tế tùy phiên bản/report configuration**, không phải tên file phải được tạo. Việc có CSS/images còn phụ thuộc skin và output được render.

### Lệnh kiểm tra file tối thiểu

**Linux/macOS:**

~~~bash
test -f target/site/index.html
test -f target/site/guide.html
ls target/site
~~~

**PowerShell:**

~~~powershell
Test-Path target\site\index.html
Test-Path target\site\guide.html
Get-ChildItem target\site
~~~

Trên PowerShell, `Test-Path` trả **`True`** khi file tồn tại; đây là điều kiện kiểm tra, không phải log Maven cố định. Nếu báo `False`, xem `mvn site` có thật sự thành công không và các file có được đặt đúng đường dẫn `src/site/markdown` hay không.

**Không lấy thông báo `BUILD SUCCESS` làm bằng chứng mọi trang đều có nội dung đúng.** Cần mở trang, kiểm tra menu, tiêu đề, các link và dữ liệu báo cáo.

## 12. `mvn site` khác với `mvn site:site` thế nào?

Một lệnh dùng **tên phase**:

~~~bash
mvn -B -ntp site
~~~

Maven đi qua các phase trước đó trong **site lifecycle**, bao gồm `pre-site`, rồi gọi goal được bind tại phase `site`.

Một lệnh gọi trực tiếp goal:

~~~bash
mvn -B -ntp site:site
~~~

thì Maven yêu cầu Site Plugin chạy goal `site`. Nó **không tự chạy những goals chỉ được bind ở `pre-site`**.

Trong POM demo chưa bind công việc ở `pre-site`, hai lệnh có thể tạo site tương tự. Nhưng trong dự án thật có bước chuẩn bị tài liệu, sinh API docs hoặc kiểm tra dữ liệu ở `pre-site`, gọi trực tiếp `site:site` có thể bỏ qua những bước này.

### Khi chạy goal trực tiếp, lưu ý prefix resolution

Nếu không pin plugin version, Maven có thể chọn Site Plugin version qua pluginManagement, parent hoặc cơ chế resolve khác. POM demo pin `3.12.1` ở build/plugins, nên cả lệnh phase và goal gắn với project sẽ dùng version được cấu hình.

Khi cần kiểm chứng chính xác plugin, gọi goal với **tọa độ đầy đủ**:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-site-plugin:3.12.1:site
~~~

**Không lấy phiên bản từ ví dụ khác làm mặc định cho dự án của mình**. Với Site Plugin 4.x/migration mới, các yêu cầu và defaults có thể khác; xem migration guide trước khi đổi major version.

## 13. `mvn site` không tự biên dịch hoặc chạy unit test

Đây là hiểu nhầm có hậu quả thực tế. Site lifecycle độc lập với default lifecycle. Khi chạy:

~~~bash
mvn -B -ntp site
~~~

Maven **không mặc nhiên chạy** toàn bộ `compile`, `test`, `package` và `verify`. Một report plugin có thể đọc POM mà không cần build, nhưng báo cáo Javadoc/JXR/Test/Coverage có thể cần source, compiled classes hoặc test output.

Vì vậy, với site có báo cáo dựa trên trạng thái build:

~~~bash
mvn -B -ntp clean verify site
~~~

là lựa chọn minh bạch. Điều này vẫn **không deploy** site. Trong CI nhiều jobs, nếu `verify` và `site` chạy ở hai job khác nhau, phải chuyển đủ reports/artifacts một cách rõ ràng; một job sạch không tự đọc được `target/surefire-reports` của job trước.

### Các câu hỏi trước khi gọi site trong CI

- Project cần những báo cáo nào? Chúng lấy dữ liệu từ POM, source, class files hay test results?
- Test có thật sự chạy, hay `-DskipTests`/profile đang bỏ qua?
- Các report plugins có tương thích JDK/Maven/Site Plugin đang dùng không?
- Có report aggregate nhiều modules không? Nó có chạy sai phạm vi/lặp nhiều lần không?
- CI giữ lại `target/site` như artifact hay publish tới site host?
- Nội dung được generate có vô tình chứa credentials, internal URLs hoặc metadata không được phép công khai?

**Đừng dùng Site Plugin làm công cụ sửa lỗ hổng chất lượng ứng dụng.** Site render các tài liệu/báo cáo; muốn fail build theo rule chất lượng cần cấu hình các plugin/gates tương ứng và chạy chúng ở đúng phase.

## 14. `src/site`: Doxia nhận những loại tài liệu nào?

Các thư mục theo định dạng thường gặp:

~~~text
src/site/
├── site.xml
├── markdown/
│   ├── index.md
│   └── guide.md
├── apt/
│   └── design.apt
├── fml/
│   └── faq.fml
├── xdoc/
│   └── architecture.xml
└── resources/
    ├── images/
    └── custom.css
~~~

**APT** (*Almost Plain Text*) là định dạng tài liệu cũ phổ biến của Maven; **FML** thường dùng cho FAQ; **XDoc** là XML của Doxia; **Markdown** được Site Plugin hỗ trợ trong các phiên bản 3.x phù hợp. Các nguồn này được map về thư mục site output, ví dụ `src/site/apt/design.apt` có thể thành `target/site/design.html`.

**Không đặt hai file nguồn có cùng đích HTML** như `apt/index.apt` và `markdown/index.md` mà không có chiến lược xử lý: cả hai cùng hướng tới `index.html`, dễ ghi đè hoặc tạo hành vi khó dự đoán.

### Static resources

Những file được lưu dưới `src/site/resources` thường được đưa vào cây output mà không qua Markdown parser. Ví dụ:

~~~text
src/site/resources/images/flow.png
            |
            v
target/site/images/flow.png
~~~

Trong Markdown có thể tham chiếu ảnh theo đường dẫn tương ứng với HTML đã render. **Không coi `src/site/resources` là nơi nhét configuration secrets**; file static có thể xuất hiện trên website sau publish.

### Site renderer không phải trình duyệt

Doxia chuyển markup sang HTML; nó không bảo đảm thực thi JavaScript, chụp screenshot hay kiểm tra đường link ngoài. Một site sinh thành công vẫn có thể chứa link 404, ảnh mất hoặc nội dung sai. Cần một bước **post-generation QA** phù hợp.

## 15. Report Plugin: cấu hình đúng mục tiêu, tránh report chạy thừa

Project Info Reports Plugin có nhiều reports: `summary`, `dependencies`, `plugins`, `team`, `scm`, `licenses`, `modules`, `dependency-management`... Tùy mục tiêu dự án, không phải report nào cũng có metadata hữu ích.

Trong POM demo, `<reportSets>` giới hạn ba report:

~~~xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-project-info-reports-plugin</artifactId>
            <version>3.5.0</version>
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
    </plugins>
</reporting>
~~~

Đây là **đoạn trích từ POM chạy được**, không phải file thứ hai cần tạo.

### Vì sao `<reportSets>` có giá trị?

- Khi thêm report plugin mà không chọn goals, site generation có thể chạy **mọi reporting goal** của plugin, mất thời gian hoặc cần cấu hình thêm.
- Một số plugin cung cấp cả report đơn module và report aggregate; nếu không chọn cụ thể có thể tạo outputs trùng/không phù hợp.
- Có thể cấu hình nhiều reportSets khác nhau nếu report plugin hỗ trợ những tham số độc lập.
- **Reporting configuration** tách khỏi **build plugin executions**. Một report nhìn đẹp trên website không tự động fail build khi chất lượng code giảm.

Ví dụ **Maven Javadoc Plugin** có thể được khai báo trong `<reporting>` để tạo API docs, nhưng cần kiểm tra `reportSets` để tránh chạy aggregate Javadoc sai phạm vi. Với coverage như JaCoCo, báo cáo có thể yêu cầu agent/traces từ quá trình test; chỉ thêm một goal báo cáo không sinh dữ liệu coverage.

## 16. Javadoc, Surefire report và code-quality reports

Một site dự án thực tế thường muốn nhiều nhóm report:

| Nhóm | Ví dụ plugin | Điều kiện nguồn dữ liệu |
| --- | --- | --- |
| Thông tin project | Maven Project Info Reports Plugin | POM metadata/dependency resolution. |
| API docs | Maven Javadoc Plugin | Source Java, classpath/JDK tương thích. |
| Test results | Maven Surefire Report Plugin | Báo cáo được Surefire tạo; cấu hình report phù hợp. |
| Source cross-reference | Maven JXR Plugin | Source code và index. |
| Static analysis | Maven PMD/Checkstyle/SpotBugs integrations | Plugin config, source/compiled classes tùy công cụ. |
| Coverage | JaCoCo Maven Plugin | Coverage execution data từ test run và goal report. |

**Lưu ý về test reports:** `mvn site` không chạy tests theo default lifecycle; báo cáo Surefire không thể dự đoán “vừa tạo xong” nếu chưa có test run. Dùng `mvn verify site` khi muốn site phản ánh kết quả test hiện tại.

**Lưu ý về chất lượng:** Site Plugin render báo cáo. Nó không tự áp threshold như “line coverage >= 80%”. Muốn chặn PR, cấu hình check/verify goals của plugin phù hợp trong default lifecycle và báo lỗi rõ.

**Lưu ý về bản quyền/dữ liệu:** Một báo cáo dependency hoặc SCM có thể hiển thị GAV nội bộ, repository URL và thông tin nhóm. Cần phân loại dữ liệu trước khi đưa site lên hosting công khai.

## 17. Site descriptor inheritance và multi-module

Một reactor nhiều module có thể có:

~~~text
parent/
├── pom.xml                packaging pom; modules: api, app
├── src/site/site.xml       điều hướng chung, nếu có
├── api/
│   ├── pom.xml
│   └── src/site/...
└── app/
    ├── pom.xml
    └── src/site/...
~~~

Có hai mối quan hệ phải phân biệt:

1. `<modules>` trong parent aggregator quyết định tập Maven projects được build.
2. `<parent>` trong child xác định cấu hình POM được **kế thừa**, trong đó có những site/report settings khi được tổ chức đúng.

Tài liệu site descriptor có thể được kế thừa theo cơ chế riêng của Maven Site. Với Maven 3.x, khi một parent packaging `pom` cần **đính kèm site descriptor để các module khác dùng**, có thể phải bind rõ goal **`site:attach-descriptor`**; đừng giả định Maven tự attach như một số cấu hình cũ.

### Vấn đề links giữa module sites

Khi chạy `mvn site` ở reactor đa module, mỗi module có thể sinh ra:

~~~text
parent/target/site/
parent/api/target/site/
parent/app/target/site/
~~~

**Đây là đường dẫn trong workspace**, không nhất thiết giống cấu trúc URL thực khi site được deploy. Vì vậy một link “module A → module B” có thể nhìn như hỏng khi mở `target/site/index.html` của từng module trực tiếp.

`site:stage` tạo cây staging **theo site deployment URL**, giúp kiểm tra relative links giữa các module đúng hơn. Cần cấu hình site URL ở `distributionManagement` và chạy sinh site trước khi staging. Đừng dùng một site staging sai base URL để kết luận link trên host production chắc chắn đúng.

### Site của parent và child không phải một HTML duy nhất

Một parent `pom` có thể sinh **site riêng** và các child mỗi module cũng có site. Nếu muốn một trang tổng hợp toàn reactor, cần thiết kế report aggregates, site structure và deployment tree. Không phải cứ có `<modules>` là Site Plugin tự gom toàn bộ nội dung và mọi báo cáo vào một trang `index.html` duy nhất.

## 18. `site:stage`: khi cần kiểm tra cấu trúc URL trước khi publish

Sau khi sinh site:

~~~bash
mvn -B -ntp site
~~~

một dự án có **site URL được cấu hình đúng** có thể stage:

~~~bash
mvn -B -ntp site:stage
~~~

Tùy plugin version/configuration, output staging mặc định nằm dưới một thư mục như **`target/staging`**. Mục đích là **tạo cây site cục bộ mô phỏng vị trí deploy**, không upload production.

**Trong POM demo ở mục 6 không có `distributionManagement/site`**. Vì vậy **đừng chạy `site:stage` và kỳ vọng có đủ layout/URL của production**: ví dụ chưa biết sẽ publish ở đâu. Nếu muốn thực hành staging, hãy tạo một biến thể POM riêng có site URL được duyệt, không sử dụng URL giả như đích thật.

### Kiểm chứng staging

- Site root và child module locations có đúng convention không?
- Links giữa modules có trỏ đúng khi mở từ staging root?
- CSS/images có đường dẫn tương đối phù hợp không?
- Có links tới `/latest` hoặc version path chưa được tạo không?
- Site descriptors của parent/children đã kế thừa đúng chưa?
- Thư mục staging có vô tình chứa file từ build trước không?
- Có phần nào chứa dữ liệu không được phép xuất bản?

Nếu staging thành công vẫn phải kiểm tra **permission/network/protocol** của đích deploy thật và quy trình review. Stage **không thay thế** sự xác nhận production deployment.

## 19. Phân biệt `site:run` với `site:site`

`site:run` khởi động một **local Jetty-based server** để preview site nhanh hơn trong quá trình soạn tài liệu. Nó có thể render nội dung theo yêu cầu khi bạn truy cập trang, giúp vòng lặp viết–xem bớt thời gian hơn build toàn bộ site mỗi lần.

~~~bash
mvn site:run
~~~

Lệnh thường **giữ process chạy** cho đến khi bạn dừng nó; không phải command build batch lý tưởng trong CI. Để biết port và URL preview chính xác, đọc log Site Plugin và tham số `site:run` của version đang dùng; **không mặc định port luôn rảnh hoặc là 8080**.

Trong dự án demo, bạn cũng có thể chạy:

~~~bash
mvn -B -ntp site
~~~

rồi xem output static HTML dưới `target/site`. Chạy một static HTTP server tùy chọn là bước bên ngoài Maven Site Plugin, không phải bằng chứng `site:run` đã làm đúng.

### Hai kiểu lỗi khi preview

- **Server port conflict:** có process khác đang listen trên port preview. Đổi cổng theo parameter version Site Plugin hỗ trợ, hoặc dừng đúng process mà bạn sở hữu; không kill ngẫu nhiên service của người khác.
- **Link `file://` khác HTTP:** trình duyệt có thể xử lý đường dẫn, font hoặc JavaScript khác khi mở file trực tiếp. Kiểm tra site qua HTTP cục bộ và staging layout nếu mục tiêu là hosting.

**Không mở preview server lên internet** bằng cách bind public interface khi chỉ cần localhost; preview không có nghĩa đã được harden để trở thành website production.

## 20. Đích deploy đặt ở đâu và ai cấp quyền?

Trong POM của dự án **đã được phép publish**, site deployment URL được khai báo dưới:

~~~xml
<distributionManagement>
    <site>
        <id>project-docs</id>
        <url>scp://docs.example.invalid/var/www/project</url>
    </site>
</distributionManagement>
~~~

**Đây chỉ là cấu hình minh họa, không phải URL thật hoặc mục tiêu được phép ghi.** Với `scp`, cần Maven Wagon provider phù hợp và quyền SSH/hosting. Với `file:` protocol có thể ghi vào filesystem; với các host khác có thể dùng một cơ chế publish riêng như SCM Publish, static hosting CI artifact hoặc object storage adapter.

**Không nhầm** `<distributionManagement><repository>` để deploy JAR với `<distributionManagement><site>` để deploy website. Hai phần này có thể có ID, URL, credentials và access control hoàn toàn khác nhau.

Trong `settings.xml`, Maven có thể tìm credentials qua `<server><id>project-docs</id>...` khi Wagon cần authentication. **Không hardcode password/token vào `pom.xml`, site.xml, Markdown hoặc source control.** Dùng secret store và quyền tối thiểu cho CI, với môi trường staging và production tách biệt.

### Vì sao `site-deploy` là một quyết định riêng?

Lệnh:

~~~bash
mvn site-deploy
~~~

chạy tới phase có thể **ghi nội dung lên server website**. Trước khi gọi, phải biết:

1. Địa chỉ deploy có đúng môi trường (staging/production) không?
2. Site đã được generate và kiểm tra nội dung chưa?
3. Credentials từ CI secret store có quyền chính xác và được redaction trong logs không?
4. Site được publish theo version path hay ghi đè trang hiện tại?
5. Có rollback, backup và cách xác minh hash/file sau upload không?
6. Việc publish có được phê duyệt cho commit/tag/branch này không?

**Không chạy `mvn site-deploy` trong dự án demo**, vì mục tiêu bài tập chỉ là sinh HTML và kiểm tra local.

## 21. Phát hành site trong CI có kiểm soát

Quy trình đề xuất:

~~~text
1. Checkout commit/tag đã được xác nhận
2. Chọn đúng JDK và Maven (mvn --version)
3. Resolve dependencies từ repository/mirror được duyệt
4. mvn -B -ntp clean verify site
   - Java compile/unit tests
   - reporting goals
   - Doxia render src/site => target/site
5. Kiểm tra HTML đầu ra, link, report completeness và encoding
6. Scan nội dung để tránh lộ secret/internal metadata
7. Lưu target/site làm CI artifact để review
8. Nếu site nhiều module: staging đúng URL và kiểm tra module links
9. Review/approval theo chính sách phát hành
10. Publish qua site-deploy hoặc hệ thống hosting phù hợp
11. Xác minh URL, nội dung và rollback plan
~~~

**Không trộn tự động publish vào mọi pull request**. Một pull request chưa được review có thể chứa tài liệu chưa chính xác hoặc lộ thông tin nội bộ; nên sinh site và đăng artifact preview riêng, rồi mới cho branch/tag được phép đẩy lên production host.

Đối với CI có các jobs riêng:
- Job build/test có thể tạo reports.
- Job site có thể cần nhận reports/source hoặc chạy `verify site` riêng.
- Job deploy nhận đúng artifact site đã QA, không âm thầm build lại từ một commit khác.
- Job deploy dùng **environment protection**, scoped secrets và quyền ghi hạn chế.

Nên ghi **commit SHA, POM version, Maven/JDK versions và thời điểm xuất bản** theo chính sách, nhưng không nhúng access token hay secret vào HTML.

## 22. Các dấu hiệu site đã sinh nhưng chưa đủ chất lượng

Tạo được `target/site/index.html` là một bước, chưa phải kiểm chứng hoàn chỉnh. Các lỗi phổ biến:

- Có index.html nhưng **menu trỏ `guide.md`** thay vì `guide.html`.
- Nội dung trang tài liệu có **dấu tiếng Việt bị lỗi** do encoding không đồng bộ.
- Site chứa menu **Project Reports** nhưng báo cáo mong đợi bị skip vì cấu hình sai `<reporting>`.
- Site có link tới module khác nhưng bản build local chưa có staging layout.
- Javadoc là bản cũ vì job site không chạy lại compile/generate.
- Test report được sinh từ `target/surefire-reports` cũ; CI không chạy tests mới.
- CSS/image không tải do asset không nằm trong `src/site/resources`.
- Site vô tình có `.env`, token, internal repository URL hoặc thông tin không được phép công bố.
- Skin/version của Doxia không tương thích, render lỗi dù `pom.xml` hợp lệ.
- Site được publish từ branch khác với source code đã kiểm chứng.

**Checklist QA site tối thiểu:**

1. File chính trong `target/site` tồn tại và có nội dung đúng.
2. Điều hướng `index.html`, `guide.html` hoạt động trong HTTP/staging.
3. Project Info reports có những trang được cấu hình.
4. Titles/menu/skin render rõ ràng, không broken images/CSS.
5. Encoding tiếng Việt đúng ở cả source và output.
6. Dữ liệu report khớp POM/dependency graph sau build.
7. CI test results phù hợp commit hiện tại.
8. Không lộ secret/internal-only data khi publish công khai.
9. Với đa module, stage và kiểm tra cross-module links.
10. Chỉ deploy sau phê duyệt và có thể truy vết/rollback.

## 23. Khi `mvn site` báo lỗi: cách chẩn đoán có thứ tự

### Lỗi A — Không thấy `target/site/index.html`

Kiểm tra:
- File nguồn `src/site/markdown/index.md` có nằm đúng vị trí không?
- `mvn site` có được gọi thành công, hay lệnh dừng ở `mvn test`?
- Site Plugin có `siteDirectory` hoặc `outputDirectory` override khác mặc định không?
- Có file `index.apt` và `index.md` cùng target output gây xung đột không?
- Doxia parser cho định dạng được sử dụng có được bật không?

### Lỗi B — Site Plugin/skin không resolve được

Thường do repository/mirror/offline cache, version không tồn tại hoặc phiên bản plugin/skin không tương thích. Kiểm tra đúng GAV và tài liệu **versions đã pin**, không chạy `latest` chỉ để “cho qua”.

**Không giải quyết bằng cách thêm repository HTTP không tin cậy hoặc bỏ TLS verification**. Kiểm tra network, Maven settings và artifact source được phép.

### Lỗi C — XML `site.xml` không hợp lệ

Kiểm tra namespace/XSD version của site descriptor, đóng đủ tags, escaping XML đúng và chọn skin thực sự tồn tại. Nếu thêm raw HTML/JS vào XML, dùng quy tắc escape/CDATA phù hợp; không paste trực tiếp ký tự đặc biệt làm hỏng XML.

Có thể xem descriptor hiệu lực bằng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-site-plugin:3.12.1:effective-site
~~~

Goal này giúp quan sát **site descriptor sau inheritance**, không tự chứng minh toàn bộ HTML render đúng.

### Lỗi D — Reporting Plugin không chạy

Kiểm tra:
- Plugin có nằm dưới `<reporting><plugins>` và tên goals đúng không?
- Có `<reportSets>` vô tình bỏ goal mong muốn không?
- Plugin version có tương thích Site Plugin/Doxia/JDK không?
- Report cần source/classes/test data được tạo trước chưa?
- `generateReports` có bị tắt không?

Đừng nhầm `build/plugins` và `reporting/plugins`.

### Lỗi E — `NoSuchMethodError` hoặc `ClassNotFoundException` trong report generation

Một nhóm plugin/reporting library dùng các version Doxia/Sitetools/API khác nhau có thể gây lỗi linkage. Xem full Maven error stack, versions của Site Plugin, report plugins và skin, rồi chọn tổ hợp tương thích. **Không sửa code ứng dụng nếu lỗi nằm trong class realm của report plugin**.

### Lỗi F — `site:stage` không có link module đúng

Kiểm tra `distributionManagement/site` URL, cấu trúc module và có chạy `mvn site` trước hay chưa. Link trong staging không nhất thiết giống local `target/site` của module. Đừng sửa thủ công mọi HTML output nếu nguyên nhân là base URLs/site descriptor.

### Lỗi G — `site:deploy` thất bại

Phân biệt:
- Site URL không có hoặc sai.
- Protocol Wagon provider không hỗ trợ.
- Credential `<server><id>` không khớp site ID.
- Host/network/SSH permission không phù hợp.
- Hệ thống đích không cho ghi.
- Quota/rate limit hoặc hosting policy chặn upload.

**Không retry ghi đè mù** nếu không biết deploy đã ghi được một phần hay chưa. Đối chiếu trạng thái host và sử dụng cơ chế publish atomic/staging/rollback theo hạ tầng.

## 24. `maven-site-plugin` không thay mọi công cụ tài liệu khác

Site Plugin phù hợp khi:
- Dự án đã dùng Maven.
- Cần tài liệu cùng lifecycle với POM/dependencies.
- Muốn báo cáo Maven trong một giao diện thống nhất.
- Muốn tạo HTML tĩnh cho CI artifact hoặc hosting của tổ chức.

Nhưng Site Plugin **không tự thay thế**:
- OpenAPI/Swagger spec generation.
- API reference được công cụ khác tạo (chỉ có thể tích hợp output).
- Static analysis quality gates trong `verify`.
- Security scanning/secret scanning.
- CI approval hoặc deployment orchestration.
- Search engine/documentation hosting/CDN.
- Automated broken-link/accessibility testing.

Chọn đúng vai trò của từng công cụ. Nếu tổ chức dùng MkDocs, Docusaurus hoặc Sphinx làm tài liệu chính, vẫn có thể giữ Site Plugin cho Maven-specific reports hoặc kết hợp output, nhưng phải tránh **hai nguồn nội dung site trùng nhau và hai hệ thống publish cùng một URL**.

## 25. Vấn đề hiệu năng, ổn định và đa ngôn ngữ

### Hiệu năng

- Chọn reporting goals cần thiết; không bắt tất cả plugins tạo mọi report.
- Tránh report aggregate nhiều lần ở từng module.
- Nếu report đòi dependency resolution lớn hoặc source cross-reference, dự trù thời gian build.
- Giữ plugin/cache versions ổn định và tách bước deploy khỏi build nếu cần review.
- Site Plugin 3.12.1 `site:site` **không đánh dấu thread-safe**; đừng mặc định chạy `mvn -T ... site` sẽ song song an toàn. Xem warnings và tài liệu version phù hợp.

### Encoding và ngôn ngữ

- Dùng UTF-8 cho `src/site` và site output.
- Nếu tạo tài liệu tiếng Việt, kiểm tra font/encoding và ký tự HTML thực tế.
- Site Plugin có tham số `locales` theo version; khi đa ngôn ngữ, cần mô hình thư mục/translation phù hợp, không chỉ thay property rồi kỳ vọng mọi Markdown tự dịch.
- Một số report plugins có localization khác với tài liệu thủ công; kiểm tra UX thống nhất.

### Tính tái lập

Site output có thể mang **ngày build, timestamps hoặc nội dung lấy từ dependency metadata**. Nếu tổ chức yêu cầu reproducible outputs, cần kiểm soát từng nguồn không xác định và so sánh artifact site. **Cùng một site trông giống nhau không bảo đảm SHA-256 giống nhau** nếu metadata khác.

Không nhúng secret từ CI environment vào template hay filtered Doxia content. Khóa việc publish vào chỉ những bản build/commit đã được phê duyệt.

## 26. Bài tập củng cố

**Bài 1 — nắm lifecycle.** Vẽ ba lifecycle `clean`, `default`, `site`. Giải thích vì sao `mvn site` không tự chạy unit test và không deploy.

**Bài 2 — tự dựng site.** Tạo đúng `pom.xml`, `SiteGreeting.java`, `SiteGreetingTest.java`, `site.xml`, `index.md`, `guide.md` trong mục 6–10. Chạy `mvn -B -ntp clean verify site`; xác nhận source Java được test, hai trang HTML tồn tại.

**Bài 3 — stdout.** Chạy `java -cp target/classes vn.example.site.SiteGreeting`; kết quả chính xác là **Maven Site: OK**. Phân biệt stdout này với log từ `mvn site`.

**Bài 4 — thay menu.** Thêm một Markdown page `faq.md` và menu link `faq.html` trong `site.xml`. Xác nhận Doxia tạo đúng HTML và menu không chứa broken link.

**Bài 5 — báo cáo.** Giữ `reportSets` chỉ gồm `summary`, `dependencies`, `plugins`. Mở site và xác nhận các report mong đợi thực sự xuất hiện; thử bỏ một report goal rồi so output.

**Bài 6 — build và site.** So `mvn test`, `mvn verify`, `mvn site`, `mvn verify site`, và `mvn site:site`. Lập bảng phase/goal nào chạy; ghi rõ các bước không thể tự suy từ tên lệnh.

**Bài 7 — site descriptor.** Dùng `site:effective-site` để kiểm tra `name`, skin và menu từ file `site.xml`. Giải thích vì sao `site.xml` khác `pom.xml` và vì sao `ref="reports"` cần cấu hình reporting.

**Bài 8 — multi-module.** Phác thảo parent + hai modules, mỗi module có `target/site`. Chỉ ra lý do links có thể hỏng khi mở HTML local và khi nào cần `site:stage` với site URL đã biết.

**Bài 9 — hosting.** Trên giấy, thiết kế `<distributionManagement><site>` và credential ID trong `settings.xml` (không điền secret thật). Phân biệt `site:deploy`, `site:stage`, `site:stage-deploy`, và default `deploy`.

**Bài 10 — CI.** Thiết kế pipeline chỉ cho preview site trên PR, chỉ publish trên branch/tag được duyệt. Liệt kê report completeness, secret scanning, version/JDK provenance và rollback trước production deploy.

### Tổng kết

**Maven Site Plugin biến tài liệu từ `src/site` và reporting goals thành website tĩnh trong `target/site`.** Site lifecycle là một lifecycle riêng gồm **`pre-site → site → post-site → site-deploy`**. `mvn site` chỉ sinh site; `mvn site-deploy` mới đi tới bước có thể publish. `site:site`, `site:run`, `site:stage` và `site:deploy` là những plugin goals với phạm vi khác nhau, không nên coi chúng là các cách viết khác của một lệnh.

Khi tạo tài liệu, đặt Markdown dưới `src/site/markdown`, giao diện/menu trong `src/site/site.xml`, chọn skin tương thích và cấu hình reports trong `<reporting>`. Muốn reports dựa vào kết quả test/compiled classes mới nhất, hãy chạy **`mvn clean verify site`**. Kiểm tra HTML/links/encoding và dữ liệu nhạy cảm trước khi publish; dùng staging và đích deploy được duyệt nếu làm site đa module hoặc site production.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Core — Lifecycles Reference (Maven 3)](https://maven.apache.org/ref/3-LATEST/maven-core/lifecycles.html)
- [Apache Maven Site Plugin 3.12.1 — Introduction](https://maven.apache.org/plugins-archives/maven-site-plugin-3.12.1/)
- [Apache Maven Site Plugin 3.12.1 — Plugin Goals](https://maven.apache.org/plugins-archives/maven-site-plugin-3.12.1/plugin-info.html)
- [Apache Maven Site Plugin 3.12.1 — site:site](https://maven.apache.org/plugins-archives/maven-site-plugin-3.12.1/site-mojo.html)
- [Apache Maven Site Plugin — Creating Content](https://maven.apache.org/plugins/maven-site-plugin/examples/creating-content.html)
- [Apache Maven Site Plugin — Configuring the Site Descriptor](https://maven.apache.org/plugins/maven-site-plugin/examples/sitedescriptor.html)
- [Apache Maven Site Plugin 3.12.1 — Configuring Reports](https://maven.apache.org/plugins-archives/maven-site-plugin-3.12.1/examples/configuring-reports.html)
- [Apache Maven Site Plugin 3.12.1 — site:stage](https://maven.apache.org/plugins-archives/maven-site-plugin-3.12.1/stage-mojo.html)
- [Apache Maven Project Info Reports Plugin](https://maven.apache.org/plugins/maven-project-info-reports-plugin/)
- [Apache Maven — Available Skins and Compatibility](https://maven.apache.org/skins/index.html)
- [Apache Maven — Creating a Site](https://maven.apache.org/guides/mini/guide-site.html)
