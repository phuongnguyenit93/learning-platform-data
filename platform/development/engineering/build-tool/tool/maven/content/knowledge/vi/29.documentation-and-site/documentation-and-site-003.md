# Cấu hình tên, điều hướng và nội dung trang dự án với Maven Site Plugin

## 1. Tổng quan: website tài liệu là một sản phẩm của Maven

Một project Maven có thể xuất bản **website tài liệu** bên cạnh JAR/WAR và test reports. Site không được viết như một file HTML đơn lẻ rồi bỏ vào `target/`: Apache Maven Site Plugin tổ chức việc sinh site từ **metadata của POM**, **site descriptor** và **nội dung nguồn** do Apache Maven Doxia chuyển thành HTML.

Ba nhóm nguồn chính:

1. **`pom.xml`:** tên và mô tả project (`name`, `description`, `url`), thông tin tổ chức/developer/SCM/license khi có, cấu hình Site Plugin và reporting plugins.
2. **`src/site/site.xml`:** tên site, giao diện/skin, banner, breadcrumbs, links và menu trỏ đến các trang HTML.
3. **`src/site/markdown/`**, `apt/`, `fml/`, `xdoc/` và `resources/`: văn bản hướng dẫn, FAQ, hình ảnh/CSS, các tệp tĩnh.

Mục tiêu học là cấu hình tên, điều hướng và nội dung **khớp nhau**. Ví dụ một menu ghi “Hướng dẫn chạy” nhưng `href="usage.html"` thì phải có một trang `usage.html` được sinh từ nguồn tương ứng, thường là `src/site/markdown/usage.md`.

**Phạm vi:** bài dùng Maven 3.9.x, Java 17 và một phiên bản được pin của Maven Site Plugin (`3.22.0`) để minh họa. Giao diện/theme và chính xác tên report HTML có thể khác khi thay plugin/skin versions; đừng áp dụng mù quáng các ví dụ Site Plugin 2.x với schema DECORATION đời cũ.

## 2. Ba lớp cấu hình khác nhau

| Nguồn | Chức năng | Ví dụ |
| --- | --- | --- |
| POM `<name>` | Project display name, thường là site title mặc định. | `Greeting Service - Demo` |
| POM `<description>` | Project metadata, được hiển thị ở các báo cáo tương ứng. | `Website Maven cho Java 17` |
| POM `<url>` | Địa chỉ web công khai dự kiến cho project. | `https://example.org/greeting/` |
| POM `groupId:artifactId:version` | Tọa độ artifact Maven, **không phải nhãn menu**. | `org.example.docs:greeting-site:1.0.0` |
| `site.xml` attribute `site@name` | Site title tùy chỉnh, có thể khác POM name. | `Tài liệu Greeting Service` |
| `site.xml` `body/menu/item` | Nhãn và đường dẫn điều hướng. | `Hướng dẫn chạy → usage.html` |
| `site.xml` `links/breadcrumbs` | Liên kết chung và phân cấp điều hướng. | Home → Greeting |
| `site.xml` `skin` | Template/CSS/theme render trang. | Maven Fluido Skin |
| `src/site/markdown/*.md` | Nội dung tài liệu tự viết. | `index.md`, `usage.md` |
| `src/site/resources/*` | Logo, hình ảnh, CSS/static assets. | `images/greeting.svg` |
| POM `reporting/plugins` | Báo cáo sinh tự động từ Maven project. | Summary, dependency info |
| `target/site` | HTML/asset output **được tạo**, không phải source. | `index.html` |

**Không nhầm:** đổi `<name>` không đổi `artifactId`; đổi `site@name` không đổi tên file Markdown; đổi `item@name` không đổi `href`; `project.url` không mặc định là nơi Maven deploy site.

## 3. Cấu trúc một project có tài liệu và mã Java

Project thực hành có đầy đủ POM, Java source, site descriptor và bốn trang Markdown:

~~~text
greeting-site/
├── pom.xml
└── src/
    ├── main/java/org/example/docs/Main.java
    └── site/
        ├── site.xml
        ├── markdown/
        │   ├── index.md
        │   ├── usage.md
        │   ├── architecture.md
        │   └── faq.md
        └── resources/
            └── images/greeting.svg
~~~

Sau khi chạy `mvn site`, kết quả quan trọng thường là:

~~~text
target/site/
├── index.html
├── usage.html
├── architecture.html
├── faq.html
├── images/greeting.svg
├── css/
└── ... các assets và reports khác ...
~~~

**Luồng xử lý:**

~~~text
pom.xml metadata + reporting
src/site/site.xml (title, menu, skin)
src/site/markdown/*.md (Doxia source)
src/site/resources/** (static assets)
            |
            v
      Maven Site Plugin
            |
            v
      target/site/*.html
~~~

Không sửa trực tiếp `target/site/index.html` rồi mong thay đổi giữ nguyên: `target/` là build output, sẽ bị làm mới trong những lần build/clean tiếp theo. Muốn cập nhật nội dung, sửa đúng file dưới `src/site/` và build lại.

## 4. POM đầy đủ: tên project, Site Plugin và reporting

Tệp `greeting-site/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.docs</groupId>
    <artifactId>greeting-site</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Greeting Service - Demo</name>
    <description>Website tai lieu Maven cho ung dung Java 17.</description>
    <url>https://example.org/greeting/</url>

    <organization>
        <name>Example Documentation Team</name>
        <url>https://example.org/</url>
    </organization>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
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
                        <id>project-overview</id>
                        <reports>
                            <report>summary</report>
                            <report>dependency-info</report>
                            <report>plugins</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
        </plugins>
    </reporting>
</project>
~~~

POM này là **tệp hoàn chỉnh**, không phụ thuộc parent corporate hoặc BOM ngoài ví dụ. Namespace `org.example.docs` là giả định, không đại diện artifact đã có trên Maven Central. URL `https://example.org/greeting/` là một ví dụ thuộc miền dành cho tài liệu, **không phải website đã triển khai**; website local vẫn build được dù URL đó không phục vụ nội dung.

Ý nghĩa:

- `groupId/artifactId/version` là danh tính Maven artifact. `<name>` là metadata, không tác động GAV.
- `<description>` và `<organization>` phục vụ thông tin dự án và những reports phù hợp, không thay phần nội dung Markdown tự viết.
- `maven.compiler.release=17` yêu cầu toolchain JDK tương thích, không tự cài JDK.
- `maven-site-plugin:3.22.0` được pin version trong `build/plugins` để site generation không vô tình đổi phiên bản plugin.
- `maven-project-info-reports-plugin:3.9.0` thuộc **`reporting/plugins`** để sinh report content.
- `reportSets` chọn ba reports tiêu biểu thay vì cố tạo mọi report có thể có.
- `project.reporting.outputEncoding=UTF-8` giúp đầu ra text giữ chữ Unicode khi plugin hỗ trợ.
- Chưa có `distributionManagement.site`, nên không có remote deployment setup.

Với Maven, `reporting` và `build/plugins` **không đồng nghĩa**: reporting plugins sinh nội dung báo cáo của site, trong khi build plugin configurations điều khiển các goals/lifecycles của Maven.

## 5. Site descriptor: file src/site/site.xml đầy đủ

Tệp `greeting-site/src/site/site.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<site xmlns="http://maven.apache.org/SITE/2.1.0"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://maven.apache.org/SITE/2.1.0
        https://maven.apache.org/xsd/site-2.1.0.xsd"
      name="Tài liệu Greeting Service">

    <bannerLeft href="index.html">
        <image src="images/greeting.svg" alt="Greeting Service"/>
    </bannerLeft>

    <skin>
        <groupId>org.apache.maven.skins</groupId>
        <artifactId>maven-fluido-skin</artifactId>
        <version>2.1.0</version>
    </skin>

    <publishDate position="right"/>
    <version position="left"/>

    <body>
        <breadcrumbs>
            <item name="Example" href="https://example.org/"/>
            <item name="Greeting Service" href="index.html"/>
        </breadcrumbs>

        <links>
            <item name="Apache Maven" href="https://maven.apache.org/"/>
            <item name="Java 17" href="https://docs.oracle.com/en/java/javase/17/"/>
        </links>

        <menu name="Bắt đầu">
            <item name="Tổng quan" href="index.html"/>
            <item name="Hướng dẫn chạy" href="usage.html"/>
        </menu>

        <menu name="Tham khảo">
            <item name="Kiến trúc" href="architecture.html"/>
            <item name="FAQ" href="faq.html"/>
        </menu>

        <menu ref="reports"/>
    </body>
</site>
~~~

Đây là **site descriptor hoàn chỉnh** cho ví dụ. Schema dùng site descriptor v2 của Maven Site Plugin; không nên trộn mẫu `DECORATION` legacy vào cùng XML mà chưa đọc migration guide.

### site@name và project.name

`site@name="Tài liệu Greeting Service"` **override title website** dù POM `<name>Greeting Service - Demo</name>`. Nếu bỏ attribute `name` trong descriptor, plugin có thể dùng giá trị `project.name` làm site title mặc định.

**Không phải hai file POM bị mâu thuẫn:** project name và website title phục vụ những lớp hiển thị khác nhau. Còn `artifactId=greeting-site` không đổi.

### bannerLeft và skin

`bannerLeft/image@src` trỏ tới **đường dẫn tài nguyên trong output site**, `images/greeting.svg`, không phải `src/site/resources/images/greeting.svg`. `skin` quyết định bộ template/CSS. Maven Fluido Skin là skin được Maven cung cấp trong hệ sinh thái Apache; ví dụ pin `2.1.0` cho consistency.

### links, breadcrumbs, menu

`links` tạo thanh link chung; `breadcrumbs` là đường dẫn phân cấp; `menu` chứa các navigation item. **Đổi nhãn** `item@name` không đổi URL; `href` phải khớp trang HTML sinh ra.

### report menu

`<menu ref="reports"/>` không chứa link thủ công; Maven tạo nó theo các reports được sinh. Khi không có reports thích hợp hoặc build report fail, đừng trông chờ menu có nội dung như dự kiến.

## 6. File Markdown trang chủ: index.md

Tệp `greeting-site/src/site/markdown/index.md`:

~~~markdown
# Greeting Service

Chào mừng đến website tài liệu của **Greeting Service**.

Project minh họa một chương trình Java 17 được quản lý bằng Maven
và một website sinh bằng Maven Site Plugin.

## Bắt đầu

Đọc [Hướng dẫn chạy](usage.html) để biên dịch và chạy Java.

## Tài liệu

- [Kiến trúc](architecture.html)
- [FAQ](faq.html)
- [Apache Maven](https://maven.apache.org/)

## Maven artifact

Tọa độ của ví dụ: org.example.docs:greeting-site:1.0.0.
~~~

`src/site/markdown/index.md` sẽ tạo `target/site/index.html`. Tiêu đề H1 trong content là tiêu đề trang, **không đồng nghĩa với `site@name`**. Trang có thể dùng một H1 “Greeting Service”, trong khi browser title chứa “Tài liệu Greeting Service” cùng tên trang theo renderer/skin.

Dòng version `1.0.0` ở trang chủ là văn bản **static** trong ví dụ. Nếu bump version trong POM, Maven **không tự tìm và thay mọi chuỗi 1.0.0** của Markdown. Muốn nội dung dynamic, cần cơ chế filtering/template phù hợp.

Các links nội bộ viết `usage.html`, `architecture.html`, `faq.html` vì người dùng duyệt **generated HTML**, không duyệt `src/site/markdown/*.md` của repository.

## 7. File hướng dẫn: usage.md

Tệp `greeting-site/src/site/markdown/usage.md`:

~~~markdown
# Hướng dẫn chạy

Ứng dụng sử dụng **JDK 17+** và Maven 3.9.x.

## Biên dịch

Tại thư mục có pom.xml, thực thi lệnh
`mvn -B -ntp clean verify`.

## Chạy chương trình

Sau khi Maven compile thành công, thực thi lệnh
`java -cp target/classes org.example.docs.Main`.

Chương trình in: **Greeting site demo ready**.

## Xem website tài liệu

Thực thi `mvn -B -ntp site`, rồi mở `target/site/index.html`.

Trở lại [Trang chủ](index.html) hoặc đọc [Kiến trúc](architecture.html).
~~~

Các ``...`` bên trong đoạn ví dụ sẽ được thay thành backticks khi tạo Markdown hoàn chỉnh cho bài Knowledge; đây là cú pháp inline code hợp lệ trong `usage.md` và Doxia render thành code spans. Để tránh nhầm với source tệp đang hiển thị, hãy **chép đúng nội dung bên trong khung Markdown**; không chép dấu `~~~markdown` ở bên ngoài.

Lệnh `mvn clean verify` dành cho Java build/test, còn `mvn site` tạo docs. Hai workflows bổ sung nhau.

## 8. File kiến trúc: architecture.md

Tệp `greeting-site/src/site/markdown/architecture.md`:

~~~markdown
# Kiến trúc

Project có hai sản phẩm: Java JAR và website tài liệu.

## Cấu trúc trách nhiệm

- **pom.xml**: Maven GAV, Java release, plugins, project metadata.
- **Main.java**: chương trình Java đơn giản.
- **site.xml**: site title, skin, links, breadcrumbs, menus.
- **src/site/markdown/**: nội dung trang tự viết.
- **src/site/resources/**: assets tĩnh của website.
- **target/site/**: kết quả HTML và reports do Maven sinh.

## Luồng xây tài liệu

1. Maven nạp POM và site descriptor.
2. Doxia parse các file Markdown.
3. Skin render HTML với menu và giao diện chung.
4. Reporting plugins bổ sung reports theo POM configuration.

Đọc [Hướng dẫn chạy](usage.html) hoặc trở lại [Trang chủ](index.html).
~~~

Một trang kiến trúc thực tế có thể chứa sơ đồ, constraints, quyết định thiết kế, API dependency graph và liên kết tới source. Không ghi credentials, private configuration hoặc bí mật công ty trong một site có thể được publish công khai.

## 9. File FAQ: faq.md

Tệp `greeting-site/src/site/markdown/faq.md`:

~~~markdown
# FAQ

## Có cần chạy Maven Site để biên dịch Java?

Không. Dùng `mvn clean verify` hoặc phase phù hợp để build Java.

## Vì sao menu hiện nhưng bấm link không mở?

Kiểm `href` trong site.xml có khớp file HTML được sinh
trong `target/site` hay không.

## Đổi project.name có đổi artifactId không?

Không. Tên project là metadata, artifactId là tọa độ Maven.

## Xem website local trước khi publish được không?

Có. Chạy `mvn site`, rồi mở `target/site/index.html`.
Đối với multi-module, dùng `site:stage` khi cần kiểm link giữa modules.

[Trang chủ](index.html)
~~~

FAQ có thể dùng FML (`src/site/fml/faq.fml`) nếu đội muốn định dạng hỏi-đáp riêng của Doxia, nhưng Markdown đủ cho demo. **Không tạo cả hai file Markdown FAQ và FML FAQ nếu chúng cùng sinh `faq.html`**, vì các output có thể collision/ghi đè.

## 10. Logo SVG và static resources

Tệp `greeting-site/src/site/resources/images/greeting.svg`:

~~~xml
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 420 84" width="420" height="84"
     role="img" aria-label="Greeting Service">
    <rect x="2" y="2" width="416" height="80" rx="12" fill="#14365D"/>
    <text x="22" y="54" font-size="31"
          font-family="Arial, sans-serif" font-weight="bold"
          fill="#FFFFFF">Greeting Service</text>
</svg>
~~~

Maven Site Plugin sẽ copy tệp static resource đến `target/site/images/greeting.svg`. Trong `site.xml`, banner trỏ đến `images/greeting.svg` là **đường dẫn trong generated website**.

Bạn cũng có thể dùng `src/site/resources/css/site.css` cho custom style theo tài liệu Maven Site Plugin. Cẩn thận với skin CSS selectors và nguy cơ làm giảm khả năng truy cập. Trong demo, chưa cần custom CSS; pin skin version để giảm khác biệt giữa các build.

Logo trong ví dụ là hình vector tự tạo bằng SVG markup, không tải từ Internet. Nếu dùng logo công ty thật, kiểm quyền thương hiệu và bảo đảm file logo được copy lên hosting; không trỏ tới file tuyệt đối trên máy phát triển.

## 11. Java source để kiểm Maven build độc lập

Tệp `greeting-site/src/main/java/org/example/docs/Main.java`:

~~~java
package org.example.docs;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Greeting site demo ready");
    }
}
~~~

Đây là chương trình Java 17 đầy đủ và không dùng thư viện ngoài JDK. Chạy:

~~~bash
mvn -B -ntp clean verify
java -cp target/classes org.example.docs.Main
~~~

**Stdout chính xác của riêng lệnh Java:**

~~~text
Greeting site demo ready
~~~

Maven build có log riêng; không trình bày một dòng output Java ở trên như toàn bộ stdout của `mvn clean verify`.

Chương trình không có Java `Main-Class` được ghi vào JAR manifest, nên **không** dùng `java -jar target/greeting-site-1.0.0.jar` như một phép thử tương đương. `java -cp target/classes` gọi trực tiếp fully qualified `Main`.

## 12. Tạo website và xác minh các file kết quả

Tại project root:

~~~bash
mvn -B -ntp site
~~~

Khi Site Plugin/reporting/skin dependencies resolve thành công, những file chính sẽ xuất hiện:

~~~text
target/site/index.html
target/site/usage.html
target/site/architecture.html
target/site/faq.html
target/site/images/greeting.svg
~~~

Một số báo cáo có thể xuất thêm trang HTML như `summary.html`, `dependency-info.html`, `plugins.html` theo reporting plugin/version. Output còn có CSS, images và JS assets của skin. Danh sách trên chỉ mô tả các kết quả trọng tâm.

Để kiểm cả code và documentation:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp site
~~~

**Phân biệt lifecycle:** `mvn site` tạo website; không được coi nó là bước thay cho `mvn verify`. `mvn package` cũng không mặc định tạo đầy đủ tài liệu site.

Mở `target/site/index.html` trong browser và bấm từng menu item. Với các trang tĩnh đơn module, local preview thường đủ xem navigation. Nếu `file://` khiến asset loading bị hạn chế, có thể dùng một local HTTP server được phép để preview. Multi-module cần kiểm layout đã stage, vì các thư mục `target/site` riêng không giống deployed tree.

## 13. Bản đồ href của ví dụ

| Nút/nhãn | `href` | Đích cần tồn tại |
| --- | --- | --- |
| Banner image | `images/greeting.svg` | `target/site/images/greeting.svg` |
| Breadcrumb `Greeting Service` | `index.html` | `target/site/index.html` |
| Menu “Tổng quan” | `index.html` | `target/site/index.html` |
| Menu “Hướng dẫn chạy” | `usage.html` | `target/site/usage.html` |
| Menu “Kiến trúc” | `architecture.html` | `target/site/architecture.html` |
| Menu “FAQ” | `faq.html` | `target/site/faq.html` |
| Menu `ref="reports"` | do plugin tạo | report HTML thực sự được sinh |
| Thanh “Apache Maven” | `https://maven.apache.org/` | website bên ngoài |

Đổi `item name="FAQ"` thành `item name="Trợ giúp"` **không bắt buộc rename `faq.md`**. Chỉ đổi nhãn hiển thị.

Ngược lại, rename source `usage.md` thành `how-to.md` dẫn tới output `how-to.html`, thì menu/hyperlinks vẫn trỏ `usage.html` sẽ hỏng nếu không cập nhật hoặc tạo redirect. Đây là một dạng **tương thích URL tài liệu** cần review giống đường dẫn API.

## 14. Links, breadcrumbs, menus và preset reports

Bốn thành phần có vị trí và ý nghĩa khác nhau:

~~~xml
<body>
    <breadcrumbs>
        <item name="Home" href="https://example.org/"/>
        <item name="Greeting" href="index.html"/>
    </breadcrumbs>

    <links>
        <item name="Apache Maven" href="https://maven.apache.org/"/>
    </links>

    <menu name="Bắt đầu">
        <item name="Tổng quan" href="index.html"/>
        <item name="Hướng dẫn" href="usage.html"/>
    </menu>

    <menu ref="reports"/>
</body>
~~~

Đây là **mảnh nằm trong `site.xml`**, không phải XML độc lập. Với skin hỗ trợ:

- `breadcrumbs` hiển thị vị trí phân cấp của project/site.
- `links` hiển thị liên kết chung, thường gần banner.
- `menu` chứa nhóm navigation, thường sidebar hoặc topbar theo skin config.
- `menu ref="reports"` tạo menu theo reports đã được tạo.

Một số preset menu refs:

~~~xml
<menu ref="reports"/>
<menu ref="parent"/>
<menu ref="modules"/>
~~~

`reports` liên kết reporting output; `parent` liên kết parent site; `modules` dành cho child module site links khi thích hợp. Các cú pháp menu cũ kiểu `${reports}`/`${modules}`/`${parent}` được tài liệu Site Plugin đánh dấu deprecated; ưu tiên `ref` cho sites mới.

**Cẩn trọng:** `<menu ref="modules"/>` không khai báo Maven reactor modules. `<modules><module>...</module></modules>` trong POM mới làm việc đó.

## 15. Reporting: vì sao phải cấu hình trong POM?

Maven Project Info Reports Plugin có các goals như project summary, dependencies, dependency-info, licenses, SCM, plugins, modules. Chúng đọc Maven project metadata/dependency model và sinh báo cáo HTML.

Ví dụ plugin trong `<reporting>`:

~~~xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-project-info-reports-plugin</artifactId>
            <version>3.9.0</version>
            <reportSets>
                <reportSet>
                    <id>project-overview</id>
                    <reports>
                        <report>summary</report>
                        <report>dependency-info</report>
                        <report>plugins</report>
                    </reports>
                </reportSet>
            </reportSets>
        </plugin>
    </plugins>
</reporting>
~~~

Mảnh này giống phần reporting của POM mẫu:

- `summary` là báo cáo tổng quan về project metadata.
- `dependency-info` gợi ý cấu hình dependency coordinates cho consumers.
- `plugins` cho thấy Maven build plugins được dùng.

Đưa các report links vào navigation bằng `<menu ref="reports"/>`. **Chỉ thêm menu không khiến mọi report mục tiêu tự tồn tại**: phải có reporting plugin, goal được chọn, plugin chạy thành công và output HTML.

Nếu menu “Project Reports” thiếu, kiểm effective POM của module, plugin version, reportSets và Maven Site logs; không tự điền `href="summary.html"` cho một file chưa được sinh.

## 16. Chọn Markdown, APT, FML hay XDoc?

Maven Doxia có thể đọc nhiều ngôn ngữ markup; các thư mục source thường dùng:

| Source | Mục đích | Output |
| --- | --- | --- |
| `src/site/markdown/usage.md` | Tài liệu hướng dẫn hiện đại. | `usage.html` |
| `src/site/apt/legacy.apt` | Tài liệu Almost Plain Text cũ. | `legacy.html` |
| `src/site/fml/general.fml` | FAQ dạng FML. | `general.html` |
| `src/site/xdoc/reference.xml` | Tài liệu XDoc/XML. | `reference.html` |
| `src/site/resources/images/diagram.png` | Asset tĩnh không qua markup conversion. | `images/diagram.png` |

Markdown được hỗ trợ trong các Maven Site Plugin thế hệ mới (từ 3.3 theo tài liệu). Nhưng parser **không tự tương đương mọi extension của GitHub-Flavored Markdown**, MDX/JSX hoặc Mermaid: hãy đối chiếu với Doxia/plugin version và thêm extension có hỗ trợ khi cần.

Nếu hai tệp nguồn khác format nhưng sinh **cùng tên HTML đích**, có thể xảy ra va chạm. Vì vậy không đồng thời tạo `markdown/faq.md` và `fml/faq.fml` nếu cả hai được ánh xạ tới `faq.html`.

Nguồn Markdown và media cần được version control; HTML cuối trong `target/site` có thể được lưu như CI artifact, không phải source of truth.

## 17. site.xml không phải sitemap.xml hoặc web server config

Ba thứ này đều có chữ “site” nhưng không cùng vai trò:

- `src/site/site.xml`: **Maven Site Descriptor**, nơi cấu hình site title, menu, links, breadcrumbs và skin.
- `sitemap.xml`: sơ đồ URL cho máy tìm kiếm/crawler nếu project phát hành theo tiêu chuẩn đó.
- Nginx/Apache HTTP Server config: cấu hình phục vụ website trên môi trường triển khai, **ngoài phạm vi trực tiếp của Site Plugin**.

`mvn site` không cần chạy một server web để xuất HTML local. Nó cũng không tự sinh sitemap.xml theo mọi plugin version mặc định. Nếu nhóm cần sitemap/SEO, cấu hình plugin hoặc deployment pipeline phù hợp sau khi xác định nhu cầu, không đặt nhầm XML sitemap vào đường dẫn `src/site/site.xml`.

## 18. Skin, banner và tùy chỉnh giao diện

`skin` là một artifact template/CSS/resources. Ví dụ:

~~~xml
<skin>
    <groupId>org.apache.maven.skins</groupId>
    <artifactId>maven-fluido-skin</artifactId>
    <version>2.1.0</version>
</skin>
~~~

Pin skin version giúp giảm thay đổi bất ngờ của site output. Nếu không khai báo skin, Maven Site Plugin có default skin, nhưng giao diện/version cụ thể phụ thuộc plugin và môi trường.

Một số skin như Fluido có custom settings:

~~~xml
<custom>
    <fluidoSkin>
        <topBarEnabled>true</topBarEnabled>
        <sideBarEnabled>true</sideBarEnabled>
    </fluidoSkin>
</custom>
~~~

Đây là **mảnh tùy chọn** trong site descriptor, không thuộc full demo site.xml. Skin khác có thể không hiểu các properties này; vì vậy cần xem tài liệu skin được chọn và kiểm browser output. Các URL trong banner và img src phải đúng relative paths/HTTPS remote URLs thật.

Khi muốn đổi một màu hoặc font, hãy dùng `src/site/resources/css/site.css` hoặc cấu hình skin hỗ trợ; không edit `target/site/css/*` trực tiếp vì output sẽ bị tạo lại.

## 19. Tên website và project version hiển thị

Descriptor có:

~~~xml
<publishDate position="right"/>
<version position="left"/>
~~~

`publishDate` và `version` cho phép hiển thị thông tin ngày và project version theo renderer/skin. Đây là **metadata hiển thị**, không phải release tag hoặc chứng chỉ artifact đã publish.

Nếu muốn ẩn ngày build nhằm giảm output thay đổi, các docs mô tả:

~~~xml
<publishDate position="none"/>
~~~

Tùy mục tiêu, chọn hiển thị hoặc ẩn, rồi kiểm với skin thực tế. Nếu website cần đảm bảo provenance, ghi source SHA/build ID ở release records; chỉ hiển thị `version=1.0.0` không chứng minh files được tạo từ commit nào.

**Độc lập:** Maven artifact version thay đổi từ `1.0.0` sang `1.1.0` có thể làm phần version ở site header thay đổi, nhưng Markdown tự viết chứa literal “1.0.0” sẽ không tự đổi trừ khi bạn chỉnh text hoặc bật filtering/template.

## 20. Property interpolation và Velocity template trong nội dung

`site.xml` có hỗ trợ expressions Maven như:

~~~text
${project.name}
${project.version}
${project.organization.name}
~~~

theo quy tắc Site Descriptor interpolation. Nhưng một file Markdown thông thường chứa:

~~~text
Version: ${project.version}
~~~

**không được mặc định bảo đảm** giá trị tự thay trong mọi project/plugin config. Muốn chèn dynamic values vào content, xem **Filtering Content** và templating của Maven Site Plugin.

Với Velocity-based content `.vm`, có một bẫy: Velocity coi `##` là comment một dòng, trong khi Markdown dùng `##` để viết heading cấp hai. Vì vậy template Markdown kiểu `.md.vm` cần escape/cơ chế tương thích theo tài liệu Doxia/Velocity; nếu không các headings có thể mất trong HTML.

**Giải pháp an toàn:** chỉ dùng template/filtering khi thật sự cần, kiểm output HTML và giữ Markdown plain cho các trang static. Không trộn cú pháp Maven/Velocity mà không có kiểm thử.

## 21. Sinh site, stage và deploy là ba thao tác riêng

- `mvn site`: sinh site local (mặc định dưới `target/site`).
- `site:stage`: đặt site output vào một **staging tree** để kiểm layout/links theo cấu trúc phân phối, đặc biệt multi-module.
- `site:deploy` hoặc site-deploy lifecycle: publish site tới đích `distributionManagement.site` với protocol/auth phù hợp.

Ví dụ cấu hình **chỉ minh họa** cho remote site:

~~~xml
<distributionManagement>
    <site>
        <id>project-docs</id>
        <url>scp://docs.example.org/var/www/greeting/</url>
    </site>
</distributionManagement>
~~~

`docs.example.org` là placeholder domain dành cho tài liệu, không phải host được cấp quyền trong bài. `project.url` là địa chỉ dự kiến public, không phải lệnh publish và không thay `distributionManagement.site`. Credentials thường ở Maven settings/CI secret store, **không hard-code password vào POM**.

**Không chạy deploy trên remote site chưa được cấp quyền.** Bài demo chỉ cần local generation và đọc HTML. Với GitHub Pages/SCM-based hosting, có thể dùng Maven SCM Publish Plugin hoặc CI deployment riêng; Maven Site Plugin không tự cấu hình GitHub Pages chỉ vì `<url>` trỏ GitHub.

## 22. Multi-module site và các liên kết parent/child

Một Maven reactor có:

~~~text
my-project/
├── pom.xml                  (packaging=pom; aggregator)
├── api/pom.xml
└── cli/pom.xml
~~~

Sau `mvn site` từ root, các modules thường có site output riêng:

~~~text
my-project/target/site/
my-project/api/target/site/
my-project/cli/target/site/
~~~

Các đường dẫn **local** này khác **deployed multi-module tree**, nên link từ parent site sang child module site có thể không hoạt động khi chỉ mở các file `target/site` riêng lẻ.

Các preset menu thường dùng ở site descriptor khi phù hợp:

~~~xml
<menu ref="parent"/>
<menu ref="modules"/>
~~~

Chúng hỗ trợ navigation theo quan hệ project; **không tạo reactor modules**. Module nào tồn tại được định nghĩa bởi `<modules>` trong POM. Apache Maven khuyến nghị dùng `site:stage` để kiểm tree và links giữa modules trước khi deploy.

Khi làm multi-module sites, hãy cân nhắc nội dung parent là tổng quan sản phẩm, còn child sites chứa tài liệu API/CLI riêng. Báo cáo dependency/reporting ở mỗi child cũng là báo cáo của module tương ứng, không luôn giống report root.

## 23. Kế thừa site descriptor từ parent POM

Site descriptor có inheritance theo Maven site model, nhưng menu merge rules riêng với POM dependencies.

Với Maven 3, nếu child cần site descriptor của **parent POM đã install/deploy**, cần **attach descriptor** vào parent artifact khi phù hợp. Tài liệu Maven nêu goal `site:attach-descriptor`; việc này không còn được kích hoạt tự động trong lifecycle Maven 3 cho mọi parent packaging `pom`.

Ví dụ một mảnh cấu hình trong parent project:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-site-plugin</artifactId>
    <version>3.22.0</version>
    <executions>
        <execution>
            <id>attach-site-descriptor</id>
            <goals>
                <goal>attach-descriptor</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây **không phải POM đầy đủ**, không cần trong single-module demo. Khi dùng parent/shared site descriptor:

1. Bảo đảm child `<parent>` trỏ đúng parent GAV.
2. Bảo đảm parent descriptor đã được attach/resolve đúng build/repository context.
3. Kiểm `links` và `breadcrumbs` được kế thừa/tích lũy theo quy tắc.
4. Với menus, có các thuộc tính `inherit="top"`/`inherit="bottom"` cho vị trí menu được kế thừa theo tài liệu multi-module site.
5. Dùng `site:effective-site` để kiểm descriptor cuối sau interpolation/inheritance.
6. Stage sites để xác minh parent/child href trong đúng deployed layout.

Đừng mặc định một aggregator dùng `<modules>` là parent của mọi child; inheritance chỉ xảy ra khi child thực sự ghi `<parent>` thích hợp.

## 24. Kiểm site title bằng help:evaluate và effective-site

Hai lệnh xem hai lớp khác nhau:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:evaluate -Dexpression=project.name -q -DforceStdout
mvn -B -ntp org.apache.maven.plugins:maven-site-plugin:3.22.0:effective-site
~~~

Lệnh Help Plugin với project demo trả giá trị Maven model:

~~~text
Greeting Service - Demo
~~~

Trong khi descriptor có title:

~~~text
Tài liệu Greeting Service
~~~

Chúng khác nhau **một cách có chủ đích**. Goal `site:effective-site` cung cấp effective descriptor (sau inheritance/interpolation) để kiểm menu/skin/tên site mà renderer nhận, đặc biệt hữu ích khi có parent và nhiều module.

Không cố “chữa” sự khác nhau giữa hai tên bằng cách đổi GAV của project.

## 25. Site testing và accessibility

Một site tạo thành công chưa bảo đảm navigation tốt hoặc an toàn khi công bố. Kiểm:

- **Sự tồn tại** của `index.html`, `usage.html`, `architecture.html`, `faq.html`.
- **Link đúng đích** trong menu, breadcrumbs, links và giữa các Markdown pages.
- **Đường dẫn asset** như `images/greeting.svg` thực sự có trong output.
- **Chữ Unicode/UTF-8** hiển thị tiếng Việt đúng.
- **Alt text** cho ảnh, headings H1/H2 rõ, labels mô tả đích.
- **Contrast, keyboard focus, responsive layout** với skin version đang dùng.
- **Giới hạn public information**: không publish secret config, private issue links, credentials hoặc reports nhạy cảm.
- **Báo cáo đúng module** khi build nhiều modules.
- **No broken external links** do URL thay đổi hoặc test environment không truy cập được.
- **Version/provenance** được quản lý tách khỏi trang tĩnh.

Website được sinh từ Markdown/POM không tự đạt mọi tiêu chuẩn accessibility hoặc link integrity. Với docs quan trọng, thêm link checker/HTML tests và kiểm thủ công trong browser.

## 26. CI workflow: build và lưu site, không tự publish

Một workflow GitHub Actions **minh họa**:

~~~yaml
name: Verify Maven Site
on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify Java build
        run: mvn -B -ntp clean verify
      - name: Generate site
        run: mvn -B -ntp site
      - name: Verify essential pages
        run: |
          test -f target/site/index.html
          test -f target/site/usage.html
          test -f target/site/architecture.html
          test -f target/site/faq.html
      - name: Upload docs artifact
        uses: actions/upload-artifact@v4
        with:
          name: greeting-site
          path: target/site/
~~~

Workflow này chỉ xác minh một số file và upload **CI artifact để review**, không deploy production website. Lệnh `test -f` chạy được trên Ubuntu runner. Trong production, nên pin Maven distribution qua Maven Wrapper đã commit hoặc CI toolchain policy; ví dụ hiện chưa tạo `mvnw` nên không giả định file đó tồn tại.

Muốn publish, bổ sung một bước riêng với approval, quyền hosting, branch protection và kiểm links/security; không tự nâng `mvn site` thành thao tác deploy.

## 27. Lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Tên site khác POM `<name>`. | `site@name` đã override. | Xem `site.xml` và effective-site. |
| Đổi POM name nhưng browser title không đổi. | Site có tên riêng; hoặc site chưa rebuild. | Kiểm descriptor và chạy `mvn site` lại. |
| Menu không hiện như mong muốn. | `site.xml` sai path/schema, skin render khác. | Kiểm `src/site/site.xml`, log và browser. |
| Menu trỏ 404. | `item@href` không khớp generated HTML. | So `href` với `target/site`. |
| Viết `usage.md` trong `src/main/resources` nhưng không có trang web. | Đặt sai source directory. | Dùng `src/site/markdown/usage.md`. |
| Logo không có. | Thiếu file `resources/images` hoặc banner src sai. | So output `target/site/images` và `image@src`. |
| `menu ref="reports"` trống. | Reporting goal không chạy/tạo output. | Kiểm `<reporting>`, logs, reportSets. |
| Markdown source còn H1 nhưng output page mất heading. | Đang dùng Velocity template `.vm` với `##` bị coi comment. | Escape theo tài liệu hoặc dùng Markdown thường. |
| `${project.version}` hiện nguyên trong trang. | Chưa bật site filtering/templating. | Chọn cơ chế đúng, không đoán mọi property tự được render. |
| Parent/child links hỏng khi mở local HTML. | Local multi-module output tree khác deployed layout. | Stage site trước khi kiểm. |
| Child không nhận parent menu/skin. | Descriptor chưa attach/resolve hoặc menu inheritance config khác. | Kiểm `site:attach-descriptor`, `effective-site`. |
| `mvn package` không tạo docs. | Site lifecycle tách khỏi default lifecycle. | Chạy `mvn site`. |
| `mvn site` pass nhưng Java integration tests chưa pass. | Site generation không thay `verify`. | Chạy hai quality gates riêng. |
| Site local đúng nhưng remote không publish. | Thiếu `distributionManagement.site`/credentials/protocol. | Thiết lập theo quyền quản trị, không dựa `project.url`. |
| Trang có dấu tiếng Việt lỗi font/encoding. | Source và reporting output encodings không khớp. | Kiểm UTF-8 và rendered browser. |
| 2 file source cùng ra `faq.html`. | Markdown và FML output path collision. | Giữ một canonical source cho mỗi trang. |
| Styles khác sau dependency/plugin upgrade. | Skin/plugin versions chưa pin hoặc incompatible. | Pin và kiểm visual regression. |

**Debug theo thứ tự:** `pom.xml` name/url/reporting → `src/site/site.xml` name/menu/href → `src/site/markdown/*` → `mvn site` logs → `target/site` → báo cáo và skin → browser/stage preview.

## 28. Checklist review dự án

- [ ] POM `name/description/url` đúng ý, không nhầm với GAV.
- [ ] Site title `site@name` được chủ đích đặt hoặc để dùng POM name.
- [ ] Descriptor dùng namespace/schema phù hợp và XML well formed.
- [ ] Skin và Site Plugin có versions phù hợp, được pin.
- [ ] Tất cả menu labels rõ nghĩa, href trỏ đúng output HTML.
- [ ] `links`, `breadcrumbs` và `menus` được kiểm độc lập theo skin.
- [ ] `index.md` có H1 và link tới trang cần thiết.
- [ ] Các trang Markdown nằm ở `src/site/markdown/`.
- [ ] Không có hai nguồn cùng output HTML filename.
- [ ] Logo/ảnh/CSS nằm dưới `src/site/resources/`, đường dẫn không phụ thuộc máy dev.
- [ ] Reporting goals được chọn đúng và `menu ref="reports"` có dữ liệu thật.
- [ ] UTF-8 được sử dụng và dấu tiếng Việt hiển thị chính xác.
- [ ] `mvn clean verify` đã kiểm mã, `mvn site` đã sinh docs; không trộn hai điều kiện.
- [ ] Đã bấm thử links/kiểm file trong `target/site` sau khi build.
- [ ] Nếu multi-module, đã kiểm links ở staging/deployed layout.
- [ ] Nếu dùng shared parent site, đã xem attach descriptor/inheritance.
- [ ] Không chứa secrets và nội dung chưa được phép public.
- [ ] Pipeline CI lưu generated docs cho review trước deploy.
- [ ] Địa chỉ public project.url và deployment target được quản lý riêng.

## 29. Câu hỏi tự kiểm tra

1. **POM `<name>` có đổi Maven `artifactId` không?** Không; name là metadata, artifactId là tọa độ artifact.
2. **Tên site lấy từ đâu?** Có thể lấy từ POM project.name hoặc được override bằng attribute `name` của `<site>` trong site.xml.
3. **Đường dẫn descriptor là gì?** `src/site/site.xml` theo cấu trúc mặc định.
4. **`src/site/markdown/usage.md` tạo file nào?** Thường là `target/site/usage.html`.
5. **Menu trỏ tới `usage.md` hay `usage.html`?** Trang HTML đã được sinh, thường `usage.html`.
6. **`links` có giống `breadcrumbs` không?** Không: liên kết chung và phân cấp điều hướng có mục đích khác.
7. **`menu ref="reports"` có tự sinh report plugin?** Không; nó liên kết các reports đã được tạo.
8. **Cấu hình project-info reports nằm ở đâu?** Thường trong POM `<reporting><plugins>...`.
9. **`skin` có đổi compiled Java class?** Không; skin là template/CSS của website.
10. **`mvn site` có tự deploy tới project.url?** Không; publishing là workflow riêng.
11. **Vì sao parent/child links có thể hỏng ở local `target/site`?** Vì output directory hierarchy khác site tree sau stage/deploy.
12. **Tại sao hai source files không nên cùng tạo `faq.html`?** Có thể collision hoặc ghi đè output.
13. **Làm sao kiểm effective descriptor?** Goal `site:effective-site` với phiên bản plugin phù hợp.
14. **Đổi file `faq.md` thành `help.md` cần làm gì?** Cập nhật `href` và các nội dung links/redirect policy.
15. **Thêm `${project.version}` vào Markdown có tự sinh version không?** Không mặc định; cần filtering/template đúng.
16. **Site build thành công có chứng minh JUnit/integration tests pass không?** Không; Java lifecycle quality gates là riêng.
17. **Logo trong `src/site/resources/images` được truy cập ở output thế nào?** Theo đường dẫn output `images/...`.
18. **Tại sao không sửa HTML trong `target/site`?** Vì đó là generated output, sẽ bị ghi lại ở build sau.

## 30. Tài liệu tham khảo chính thức

- [Apache Maven Site Plugin — Introduction](https://maven.apache.org/plugins/maven-site-plugin/): kiến trúc, lifecycle và site goals.
- [Apache Maven Site Plugin — Configuring the Site Descriptor](https://maven.apache.org/plugins/maven-site-plugin/examples/sitedescriptor.html): site title, menus, links, breadcrumbs, banners, skin.
- [Apache Maven Site Plugin — Creating Content](https://maven.apache.org/plugins/maven-site-plugin/examples/creating-content.html): Markdown, APT, FML, XDoc, resources.
- [Apache Maven Site Plugin — Configuring Reports](https://maven.apache.org/plugins/maven-site-plugin/examples/configuring-reports.html): `reporting`, reportSets và preset reports menu.
- [Apache Maven Site Plugin — Building a Multi-Module Site](https://maven.apache.org/plugins/maven-site-plugin/examples/multimodule.html): staging/deploy và descriptor inheritance.
- [Apache Maven Site Plugin — Filtering Content](https://maven.apache.org/plugins/maven-site-plugin/examples/filtering.html): property interpolation trong trang.
- [Apache Maven — Guide to Creating a Site](https://maven.apache.org/guides/mini/guide-site.html): cấu trúc source, output site và deployment.
- [Apache Maven — Multi-module Sites Guide](https://maven.apache.org/guides/mini/guide-multimodule-site.html): link và site:stage.
- [Apache Maven Project Info Reports Plugin](https://maven.apache.org/plugins/maven-project-info-reports-plugin/): các reporting goals và metadata.
- [Apache Maven Fluido Skin](https://maven.apache.org/skins/maven-fluido-skin/): theme và options.
- [Apache Maven POM Reference](https://maven.apache.org/pom.html): project name/description/url/reporting/distributionManagement.
- [Apache Maven Site Descriptor Reference](https://maven.apache.org/doxia/doxia-sitetools/doxia-decoration-model/): descriptor schema và các XML elements.

**Kết luận:** Tên website, cây điều hướng và nội dung trang dự án là ba lớp cấu hình độc lập nhưng phải nhất quán. Dùng `pom.xml` để cung cấp Maven metadata và reports, `src/site/site.xml` để chọn site title/skin/menus/links/breadcrumbs, và `src/site/markdown/*` để viết nội dung. Chạy `mvn site` để xuất `target/site`, kiểm từng URL thật; với nhiều module, thêm kiểm tra site staging. Không coi `project.url` là deployment target hoặc coi trang HTML đẹp là bằng chứng Java tests đã chạy.
