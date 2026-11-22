# Maven packaging: loại artifact và vòng đời build mặc định

## 1. Packaging trong POM có ý nghĩa gì?

Trong Maven, `pom.xml` là mô hình dự án (Project Object Model). Ngoài `groupId`, `artifactId` và `version`, phần tử `<packaging>` xác định **kiểu đóng gói** của dự án. Giá trị này quyết định hai điều liên quan chặt chẽ:

1. **Artifact chính dự kiến tạo ra** khi đóng gói: chẳng hạn `.jar`, `.war`, `.ear` hoặc chính POM dạng metadata.
2. **Bộ plugin goal mặc định được gắn vào các phase của default lifecycle**: cùng lệnh `mvn package` nhưng dự án JAR sẽ gọi `jar:jar`, còn WAR gọi `war:war`.

Ví dụ, đoạn XML sau là một phần bên trong `<project>` của POM:

~~~xml
<groupId>org.example</groupId>
<artifactId>hello</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

Với các cấu hình output mặc định, `mvn package` thường tạo `target/hello-1.0.0.jar`. **Nếu không khai báo `<packaging>`, Maven dùng mặc định `jar`.** Những kiểu packaging tích hợp của Maven gồm `pom`, `jar`, `maven-plugin`, `ejb`, `war`, `ear` và `rar`; extension có thể cung cấp thêm loại khác.

Không nhầm hai khái niệm:

- **`<packaging>jar</packaging>`** là thuộc tính của dự án; có thể thay thành `war` hay `pom`.
- **`package`** trong `mvn package` là tên **phase** thuộc default lifecycle. Lệnh vẫn là `mvn package` bất kể packaging.

Packaging không phải hướng dẫn duy nhất về cách chạy chương trình. Một JAR thư viện có thể không có `main()`; một WAR thông thường cần servlet container. Các plugin bổ sung (Shade, Spring Boot, v.v.) có thể thay đổi cách phân phối hoặc chạy artifact mà không thay đổi `packaging` cơ bản.

## 2. Quan hệ với tọa độ và tên file

| Trường trong POM | Vai trò | Ví dụ |
| --- | --- | --- |
| `groupId` | Nhóm/tổ chức chứa artifact | `org.example` |
| `artifactId` | Tên định danh artifact | `hello` |
| `version` | Phiên bản | `1.0.0` |
| `packaging` | Loại artifact chính và lifecycle bindings | `jar` |
| `build.finalName` | Tên cơ sở của file tạo trong `target`, có thể tùy biến | `hello-release` |

Trong repository Maven, artifact được xác định bằng tọa độ; `<packaging>` liên quan đến loại artifact nhưng không thay thế `groupId`, `artifactId`, `version`. Với `packaging=jar`, tên tệp đóng gói mặc định thường là `<artifactId>-<version>.jar`. Nếu thêm:

~~~xml
<build>
    <finalName>hello-release</finalName>
</build>
~~~

thì file ở `target` thường đổi thành `hello-release.jar`, còn `artifactId=hello` và `version=1.0.0` vẫn giữ nguyên. Đoạn trên chỉ là **fragment POM** cần đặt đúng vị trí trong project.

Cũng cần phân biệt `packaging` của **project hiện tại** với `<type>` của một **dependency**. Dependency thường mặc định type `jar`; một BOM nhập trong `dependencyManagement` thường dùng `<type>pom</type>` kèm `<scope>import</scope>`. Không cần đổi packaging của ứng dụng chỉ vì dùng một dependency có type khác.

## 3. Phase và plugin goal: cơ chế của lifecycle

Maven có **ba lifecycle tích hợp**:

- `default`: thực hiện build, test, package, kiểm tra, install và deploy.
- `clean`: dọn output của lần build trước, thường là `target/`.
- `site`: tạo và triển khai site tài liệu dự án.

Trong mỗi lifecycle, **phase** là một mốc theo thứ tự, còn **plugin goal** là tác vụ thực sự được Maven gọi ở mốc đó. Một phase có thể được bind với 0, 1 hoặc nhiều goal; phase không có goal vẫn có thể được đi qua mà không làm gì đáng kể.

Các phase thường gặp trong `default` theo thứ tự:

~~~text
validate
  |
process-resources
  |
compile
  |
process-test-resources
  |
test-compile
  |
test
  |
package
  |
verify
  |
install
  |
deploy
~~~

Sơ đồ rút gọn những phase thường thấy. Lifecycle còn có `initialize`, `generate-sources`, `process-classes`, `prepare-package`, `pre-integration-test`, `integration-test` và `post-integration-test`. Chạy phase ở phía sau sẽ thực thi các phase trước đó **trong cùng lifecycle** đến hết phase được chỉ định.

| Lệnh | Maven thực hiện | Lưu ý |
| --- | --- | --- |
| `mvn validate` | Đến phase validate của default lifecycle | Xác nhận mô hình dự án hợp lệ |
| `mvn compile` | Đến compile | Chạy goal xử lý resource và compiler nếu packaging/cấu hình có bind |
| `mvn test` | Đến test | Có thể compile và chạy unit test, nhưng chưa đi tới package |
| `mvn package` | Đến package | Goal package cụ thể do packaging quyết định |
| `mvn verify` | Đến verify | Bao gồm package và các kiểm tra bổ sung được cấu hình |
| `mvn install` | Đến install | Lưu artifact/POM vào local Maven repository |
| `mvn deploy` | Đến deploy | Đưa artifact/POM lên remote repository nếu đã cấu hình |
| `mvn clean package` | Chạy clean lifecycle đến clean rồi default lifecycle đến package | Loại bỏ output cũ trước khi build |

**`mvn package` không tự chạy `clean`**, vì đây là lifecycle khác. `mvn compiler:compile` gọi trực tiếp một goal của Compiler Plugin, không tương đương hoàn toàn `mvn compile`: những goal được bind ở phase trước (như xử lý resource) có thể không được chạy.

Đừng mặc định `mvn package` luôn tạo artifact. Với `packaging=pom`, phase package mặc định không có goal tạo JAR/WAR; Maven vẫn có thể kết thúc thành công.

## 4. Default lifecycle bindings phụ thuộc packaging

Khi chọn `packaging=jar`, Maven tự gắn các goal phổ biến sau vào default lifecycle:

| Phase | Plugin goal mặc định với `jar` | Kết quả |
| --- | --- | --- |
| `process-resources` | `resources:resources` | Chép/xử lý resource vào `target/classes` |
| `compile` | `compiler:compile` | Biên dịch `src/main/java` thành bytecode |
| `process-test-resources` | `resources:testResources` | Chuẩn bị resource cho test |
| `test-compile` | `compiler:testCompile` | Biên dịch class test |
| `test` | `surefire:test` | Chạy unit test phù hợp |
| `package` | `jar:jar` | Đóng class/resource thành JAR |
| `install` | `install:install` | Đưa artifact và POM vào local repository |
| `deploy` | `deploy:deploy` | Đưa artifact và POM vào remote repository |

Những tên goal trên được viết rút gọn `plugin:goal`, không ấn định phiên bản plugin. Plugin version có thể khác tùy Maven, parent POM và cấu hình dự án.

**Khi đổi từ `jar` sang `war`**, các goal process-resources, compile, test của mapping tích hợp gần như tương tự, nhưng ở `package` Maven dùng **`war:war`**. Khi đổi sang **`pom`**, mapping mặc định không có goal compile/test/package; `install` và `deploy` vẫn dùng `install:install` và `deploy:deploy`.

So sánh các loại packaging tích hợp:

| Packaging | Goal chính tại `package` | Artifact chính | Sử dụng điển hình |
| --- | --- | --- | --- |
| `jar` | `jar:jar` | `.jar` | Library/ứng dụng Java |
| `war` | `war:war` | `.war` | Web app dùng servlet container |
| `pom` | Không có goal package mặc định | POM metadata | Parent, aggregator, BOM |
| `ear` | `ear:ear` | `.ear` | Java enterprise application |
| `maven-plugin` | `jar:jar` và `plugin:addPluginArtifactMetadata` | Plugin JAR kèm metadata | Viết Maven plugin |
| `ejb` | `ejb:ejb` | EJB artifact | Thành phần enterprise |
| `rar` | `rar:rar` | `.rar` | Resource adapter |

Ngoài phase package, `ear` còn bind `ear:generate-application-xml` tại `generate-resources`; `maven-plugin` còn bind `plugin:descriptor` tại `generate-resources`. Những khác biệt này chứng minh **packaging chọn cả một bộ lifecycle bindings**, không chỉ chọn phần mở rộng của file đầu ra.

Đây là các **binding mặc định**. `build/plugins`, parent POM, profile và extension có thể thêm hoặc điều chỉnh goal, nên với dự án thật cần xem cả effective POM và log build.

## 5. Thực hành 1 — JAR mặc định, ví dụ Java 17 chạy được

Tạo dự án với cấu trúc:

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── App.java
~~~

Nội dung **`pom.xml`** hoàn chỉnh:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Bạn có thể xóa dòng `<packaging>jar</packaging>` mà Maven vẫn dùng `jar` mặc định. `maven.compiler.release=17` yêu cầu JDK dùng để build có khả năng biên dịch cho Java 17; ví dụ chạy Maven bằng JDK 17+. Ghim Maven Compiler Plugin phiên bản 3.14.1 để hỗ trợ `release` ổn định. Vì packaging đã bind `compiler:compile` vào `compile`, chỉ cần khai báo plugin/version, không phải tạo execution thủ công cho goal này.

Nội dung **`src/main/java/org/example/App.java`**:

~~~java
package org.example;

public class App {
    public static void main(String[] args) {
        System.out.println("Packaging JAR OK");
    }
}
~~~

Mở terminal tại `lifecycle-demo/` và chạy:

~~~bash
java -version
javac -version
mvn -version
mvn clean package
jar tf target/lifecycle-demo-1.0.0.jar
java -cp target/lifecycle-demo-1.0.0.jar org.example.App
~~~

Sau build thành công, ít nhất cần thấy `target/classes/org/example/App.class` và file `target/lifecycle-demo-1.0.0.jar`. `jar tf` liệt kê entry như `org/example/App.class` và `META-INF/MANIFEST.MF`; thứ tự và metadata khác nhau tùy plugin. Kết quả **stdout của dòng `java -cp ...`**:

~~~text
Packaging JAR OK
~~~

Ví dụ này cố ý dùng `java -cp ... org.example.App` vì **JAR mặc định không nhất thiết có `Main-Class`** trong manifest. `java -jar` chỉ chạy được nếu manifest chứa một `Main-Class` hợp lệ (hoặc có launcher do framework cung cấp). Do đó, một file JAR build thành công vẫn có thể không khởi chạy được bằng `java -jar` mà không phải lỗi đóng gói.

Muốn hỗ trợ `java -jar`, có thể bổ sung fragment sau trong `<build><plugins>` của POM trên:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>org.example.App</mainClass>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

Build lại bằng `mvn clean package` rồi chạy `java -jar target/lifecycle-demo-1.0.0.jar`; với chương trình mẫu, stdout vẫn là `Packaging JAR OK`. Đây là fragment plugin để ghép vào POM, không phải file XML độc lập.

## 6. Thực hành 2 — WAR: đổi goal ở phase package

Đoạn POM của một web project có thể có:

~~~xml
<groupId>org.example</groupId>
<artifactId>web-demo</artifactId>
<version>1.0.0</version>
<packaging>war</packaging>
~~~

Dự án thường đặt trang web ở `src/main/webapp/` và code Java (Servlet, service) ở `src/main/java/`:

~~~text
web-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        ├── resources/
        └── webapp/
            └── index.html
~~~

Vẫn sử dụng `mvn clean package`, nhưng Maven bind **`war:war`** vào phase `package`, vì vậy file chính là `target/web-demo-1.0.0.war` chứ không phải `.jar`. Có thể kiểm tra:

~~~bash
mvn clean package
jar tf target/web-demo-1.0.0.war
~~~

WAR có thể chứa `index.html`, `WEB-INF/classes` và `WEB-INF/lib` tùy nội dung dự án. Một WAR bình thường được **deploy vào servlet container tương thích** như Tomcat, không mặc định chạy với `java -jar`. Một số ứng dụng framework hỗ trợ WAR chạy độc lập nhờ cấu hình/launcher riêng, nhưng đó là tác dụng của framework/plugin, không phải quy tắc chung của packaging `war`.

Một số phiên bản WAR Plugin hoặc cấu hình ứng dụng cũ yêu cầu `WEB-INF/web.xml`, trong khi ứng dụng servlet hiện đại có thể không cần descriptor; cần đối chiếu plugin và tiêu chuẩn Servlet của dự án. **Đoạn POM ở đầu mục chỉ minh họa thuộc tính packaging**, không phải mẫu web app độc lập đã khai báo mọi dependency cần thiết.

## 7. Thực hành 3 — POM và reactor multi-module

`<packaging>pom</packaging>` phù hợp khi project chủ yếu quản lý metadata: **parent POM**, **aggregator**, **BOM**. Với kiểu này, mặc định phase `package` không gọi compiler/test/plugin tạo JAR. Điều đó không có nghĩa project bị lỗi khi `mvn package` hoàn thành mà không có `.jar`.

Ví dụ project nhiều module:

~~~text
shop/
├── pom.xml             # packaging pom
├── service/
│   ├── pom.xml         # packaging jar
│   └── src/main/java/
└── web/
    ├── pom.xml         # packaging war
    └── src/main/webapp/
~~~

Root **`shop/pom.xml`**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example</groupId>
    <artifactId>shop-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>service</module>
        <module>web</module>
    </modules>
</project>
~~~

Giả sử mỗi module con có POM hợp lệ và các source/resource cần thiết, từ root chạy:

~~~bash
mvn clean package
~~~

Maven tạo **reactor build**: root POM quản lý các module; module `service` có thể tạo JAR và module `web` có thể tạo WAR ở **thư mục `target/` của riêng chúng**. Root `shop-parent` không vì thế sinh ra `shop-parent.jar`.

Nếu muốn chạy riêng project root mà không đi vào module con:

~~~bash
mvn -N package
~~~

`-N` có nghĩa *non-recursive*. Khi root chỉ là `pom` đơn thuần, lệnh trên không tạo JAR. Ở phase `install`, Maven có thể cài chính file POM như artifact metadata; các module vẫn có artifact riêng.

**Aggregation khác inheritance:**

- **Aggregation** dùng `<modules>` ở root để đưa các dự án con vào reactor build.
- **Inheritance** dùng `<parent>` trong POM của project con để thừa hưởng properties, dependencyManagement, pluginManagement và cấu hình.

Một project có thể đồng thời là parent và aggregator; nhưng có `<modules>` không tự động làm các POM con kế thừa root. BOM có thể dùng packaging `pom` mà không chứa module nào.

## 8. Packaging mặc định và plugin bổ sung phối hợp thế nào?

`packaging` chọn các goal mặc định; bạn vẫn có thể khai báo các plugin khác trong `<build><plugins>` để bổ sung goal vào phase. Cấu hình `<executions>` có thể chỉ rõ `<phase>` và `<goals>`.

Ví dụ fragment POM sau bind Maven Antrun Plugin vào phase `validate` để in một thông báo minh họa:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>show-lifecycle-message</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="Validate phase reached"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **fragment plugin**, chỉ chạy nếu đặt trong `<build><plugins>` của một POM thích hợp và plugin tải được. Nó thêm một goal vào `validate` nhưng không đổi `packaging=jar` hay gỡ goal `jar:jar` ở `package`. Khi gọi `mvn package`, các phase từ đầu đến `package` sẽ đi qua `validate` nên execution mới cũng được thực thi.

**`pluginManagement` không giống `plugins`.** `pluginManagement` định nghĩa version/cấu hình để quản lý cách các project dùng plugin; tự đặt một plugin dưới `pluginManagement` không đồng nghĩa bật một execution của nó trong build hiện tại.

Các plugin như **Maven Shade Plugin** có thể tạo fat/uber JAR chứa các dependency runtime, **Maven Source Plugin** có thể attach source JAR, còn plugin framework có thể tạo executable JAR. Điều này không buộc `<packaging>` phải đổi: ví dụ ứng dụng vẫn có `packaging=jar` nhưng sản phẩm đã được plugin xử lý bổ sung.

Nếu dự án dùng **custom packaging**, có thể cần Maven extension để đăng ký lifecycle mapping mới. Lỗi `Unknown packaging: ...` thường liên quan đến tên không hợp lệ hoặc extension chưa được nạp.

## 9. Tự quan sát effective packaging và các plugin goal

Trong một project có `pom.xml`, chạy:

~~~bash
mvn -version
mvn help:evaluate -Dexpression=project.packaging -q -DforceStdout
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean package
~~~

- `help:evaluate` cho biết `project.packaging` đã được Maven tính sau các giá trị mặc định/kế thừa; ở project không khai báo packaging, giá trị bình thường là `jar`.
- `help:effective-pom` xuất POM hiệu lực để xem plugin, parent và cấu hình. File `effective-pom.xml` là đầu ra của lệnh chẩn đoán ở thư mục đang chạy, không phải artifact được sinh từ lifecycle package.
- Log của `mvn clean package` cho thấy các plugin goal được thực sự gọi; hãy tìm `jar:jar`, `war:war` hoặc goal package tương ứng.

Lần đầu Maven Help Plugin có thể cần tải từ remote repository. Nếu dự án đa module, hãy đọc log và output **theo module**. Effective POM rất hữu ích để xem cấu hình nhưng không phải lúc nào cũng là bản liệt kê thứ tự mọi goal runtime; kết hợp với log build. Khi cần, `mvn -X package` in debug log chi tiết.

Trên Windows, Maven dùng lệnh `mvn` giống các hệ điều hành khác. Sau build, bạn có thể dùng `Get-ChildItem .\target` trong PowerShell hoặc `dir target` trong cmd; trên Linux/macOS dùng `ls -la target`. Công cụ `jar tf` là một phần của JDK, có thể kiểm tra file JAR hoặc WAR trên cả ba hệ điều hành.

## 10. Lỗi và ngộ nhận thường gặp

| Triệu chứng | Giải thích | Cách xử lý |
| --- | --- | --- |
| Không khai báo packaging mà vẫn ra JAR | Maven mặc định `jar` | Đây là hành vi đúng |
| `mvn test` không sinh artifact | Phase `test` đứng trước `package` | Chạy `mvn package` hoặc `mvn verify` |
| `mvn package` không xóa `target` cũ | `clean` thuộc lifecycle khác | Dùng `mvn clean package` |
| Parent `packaging=pom` không có JAR | POM chỉ có default install/deploy, không có goal tạo JAR ở package | Xem module con và `target` của từng module |
| Đổi packaging sang `war` nhưng không thấy JAR | WAR Plugin tạo `.war` theo mapping mới | Xem `target/*.war` và cấu trúc web app |
| `java -jar` báo `no main manifest attribute` | JAR không có `Main-Class` | Cấu hình manifest hoặc dùng `java -cp ... MainClass` |
| Build JAR nhưng thiếu thư viện lúc chạy | Thin JAR mặc định không gói toàn bộ dependency | Chuẩn bị classpath hoặc cấu hình Shade/plugin đóng gói phù hợp |
| `Unknown packaging` | Kiểu packaging không được nhận diện hoặc thiếu extension | Kiểm tra tên packaging, plugin và extension bắt buộc |
| Đã thêm plugin ở `pluginManagement` nhưng không chạy | Chưa có plugin/execution kích hoạt tương ứng | Xem `build/plugins` và lifecycle mapping |
| Tên JAR khác artifactId-version | Có `finalName` hoặc plugin đổi tên output | Xem effective POM và log package |
| Chạy lệnh ở root nhưng JAR nằm trong module | Reactor build có nhiều POM, target riêng | Kiểm tra target đúng module |
| `mvn compiler:compile` không xử lý resource như mong đợi | Gọi goal riêng thay vì phase compile | Dùng `mvn compile` để chạy các goal đã bind ở phase trước |

## 11. Bài tự kiểm tra

**Câu 1.** POM chỉ có `groupId`, `artifactId` và `version`, không có `packaging`. `mvn package` kỳ vọng kiểu artifact gì?  
**Trả lời:** JAR, vì `jar` là mặc định. Với `artifactId=hello` và `version=1.0.0`, tên file thông thường là `target/hello-1.0.0.jar`.

**Câu 2.** Đổi `<packaging>jar</packaging>` thành `<packaging>war</packaging>`. Có phải chạy `mvn war` thay cho `mvn package` không?  
**Trả lời:** Không. Vẫn dùng phase `package`; Maven chọn goal `war:war` mặc định theo packaging `war`.

**Câu 3.** Root `packaging=pom` có `<modules>` trỏ tới hai module con. Root có phải tạo một JAR không?  
**Trả lời:** Không. Root POM là artifact metadata; những module con có packaging riêng có thể tạo JAR/WAR. Reactor build không biến root POM thành JAR.

**Câu 4.** Có thể tạo fat JAR trong project `packaging=jar` không?  
**Trả lời:** Có, bằng plugin đóng gói phù hợp như Maven Shade Plugin. Packaging chọn default mapping nhưng vẫn có thể cấu hình thêm plugin.

**Câu 5.** `mvn compiler:compile` và `mvn compile` có hoàn toàn giống nhau không?  
**Trả lời:** Không. Câu đầu gọi goal riêng; câu sau chạy phase compile cùng các phase trước nó, theo lifecycle bindings của dự án.

## 12. Checklist khi thiết kế POM

1. Xác định loại sản phẩm cần phân phối: thư viện hoặc Java app thường là `jar`; web app chạy trong servlet container là `war`; parent/aggregator/BOM là `pom`.
2. Khai báo tọa độ `groupId`, `artifactId`, `version`. Khai báo `packaging` rõ ràng khi cần; hiểu default `jar`.
3. Kiểm tra default goal tại `package` và các plugin bổ sung (entry point, dependency packaging, compiler, framework).
4. Build bằng `mvn clean package` để nhìn rõ output mới; chạy `mvn verify` khi cần những kiểm tra bổ sung.
5. Tìm artifact tại `target` của đúng module; kiểm tra JAR/WAR bằng `jar tf` và cách chạy/deploy phù hợp.
6. Nếu kết quả khác mong đợi, kiểm tra `help:evaluate`, effective POM, plugin goal trong log và các module của reactor.

**Tài liệu chính thức:**
- [Introduction to the Build Lifecycle — Maven](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Introduction to the POM — Maven](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [POM Reference: Packaging — Maven](https://maven.apache.org/pom.html)
- [Default Lifecycle Bindings — Maven Core](https://maven.apache.org/ref/3-LATEST/maven-core/default-bindings.html)
- [Configuring Plugins — Maven](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
