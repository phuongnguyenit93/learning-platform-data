# Ba vòng đời `clean`, `default` và `site` trong Maven

## 1. Tổng quan: Maven có ba vòng đời chuẩn

Maven tổ chức hoạt động của một dự án thành **lifecycle** (vòng đời), **phase** (giai đoạn) và **plugin goal** (công việc cụ thể do plugin thực hiện). Ba vòng đời chuẩn có sẵn là:

- **`clean`**: dọn sản phẩm của lần build trước, thông thường là thư mục `target/`.
- **`default`**: kiểm tra cấu hình, xử lý tài nguyên, biên dịch, kiểm thử, đóng gói, xác minh, cài vào kho cục bộ hoặc triển khai artifact.
- **`site`**: tạo website tài liệu/báo cáo của dự án và, nếu được cấu hình, đưa website ấy lên máy chủ.

Ba vòng đời **độc lập về danh sách phase**, nhưng có thể được gọi liên tiếp trong **một câu lệnh Maven**. Khi gõ `mvn clean package`, bạn yêu cầu chạy phase `clean` của *clean lifecycle*, rồi chạy đến phase `package` của *default lifecycle*. Lệnh đó **không tự chạy site lifecycle**.

Một mô hình dễ nhớ:

~~~text
mvn clean package
    │       │
    │       └── default lifecycle: validate → ... → compile → test → package
    └────────── clean lifecycle: pre-clean → clean

mvn site
    └────────── site lifecycle: pre-site → site

mvn verify
    └────────── default lifecycle: validate → ... → package → ... → verify
~~~

Dấu `...` đại diện cho các phase trung gian, không có nghĩa những phase ấy bị bỏ qua. Chi tiết quan trọng: Maven **đi qua** từng phase theo thứ tự; một phase chỉ thực sự chạy công việc nếu có plugin goal được gắn vào phase đó.

## 2. Phân biệt lifecycle, phase và plugin goal

Ba khái niệm có vai trò riêng:

| Khái niệm | Bản chất | Ví dụ |
| --- | --- | --- |
| **Lifecycle** | Chuỗi các phase có thứ tự phục vụ một mục đích lớn. | `clean`, `default`, `site`. |
| **Phase** | Cột mốc trong lifecycle. Khi gọi một phase, Maven chạy các phase đứng trước nó trong cùng lifecycle. | `compile`, `test`, `package`, `verify`; `clean`; `site`. |
| **Plugin goal** | Tác vụ thực tế do một Maven plugin cung cấp, có thể được gắn vào phase hoặc gọi trực tiếp. | `compiler:compile`, `surefire:test`, `jar:jar`, `clean:clean`, `site:site`. |

Chẳng hạn, `mvn package` là lời gọi **phase**. Với dự án có `<packaging>jar</packaging>`, Maven dùng các binding mặc định hoặc binding do người dùng cấu hình để chạy những goal thích hợp trên đường đến `package`. Thông thường nó gọi goal xử lý resource, biên dịch Java, kiểm thử và đóng gói JAR.

Ngược lại, `mvn compiler:compile` là lời gọi **goal trực tiếp** của Compiler Plugin. Đừng coi nó hoàn toàn tương đương `mvn compile`: gọi goal trực tiếp không có nghĩa Maven tự chạy toàn bộ các phase trước đó của default lifecycle. Tương tự, `mvn clean:clean` gọi một plugin goal, còn `mvn clean` yêu cầu Maven xử lý phase `clean` cùng các phase trước nó trong clean lifecycle.

**Không có lệnh `mvn default` để thực hiện toàn bộ default lifecycle.** `default` là *tên lifecycle*, không phải tên một phase để gọi. Hãy chọn phase dừng theo mục đích, ví dụ `mvn compile`, `mvn package` hay `mvn verify`.

## 3. Clean lifecycle: dọn đầu ra build

Clean lifecycle gồm ba phase theo thứ tự:

| Phase | Ý nghĩa |
| --- | --- |
| `pre-clean` | Điểm móc cho công việc chuẩn bị dọn dẹp, nếu có goal được cấu hình. |
| `clean` | Giai đoạn dọn kết quả build; với cấu hình thông thường, Maven Clean Plugin xóa thư mục đầu ra `target/`. |
| `post-clean` | Điểm móc cho công việc sau dọn dẹp, nếu có goal được cấu hình. |

Với một dự án Maven JAR đơn giản:

~~~bash
mvn clean
~~~

Lệnh đi qua `pre-clean` và `clean`; **không tự chạy `post-clean`**, vì bạn yêu cầu dừng ở phase `clean`. Trong phần lớn dự án không có goal gắn vào `pre-clean`, nên hoạt động dễ quan sát nhất là xóa `target/`.

### `clean` xóa những gì?

Thông thường Maven Clean Plugin dọn thư mục build đầu ra như `target/`; nếu dự án đổi `project.build.directory` hoặc cấu hình riêng cho plugin, vị trí dọn có thể khác. `mvn clean` **không có chức năng xóa mã nguồn** trong `src/`, `pom.xml`, Git repository hay toàn bộ kho dependency `~/.m2/repository`.

Ví dụ:

~~~text
lifecycle-demo/
├── pom.xml
├── src/
│   └── main/java/com/example/App.java
└── target/
    ├── classes/com/example/App.class
    └── lifecycle-demo-1.0-SNAPSHOT.jar
~~~

Sau `mvn clean`, thư mục `target/` được xóa theo cấu hình mặc định. `pom.xml` và `src/main/java/com/example/App.java` vẫn còn. Nếu bạn chạy ngay `java -cp target/classes com.example.App` sau khi clean mà chưa build lại, lớp `App.class` có thể không còn để JVM tải.

### Clean không được Maven tự thực hiện trước mỗi build

~~~bash
mvn package
~~~

Lệnh trên chỉ chạy default lifecycle đến `package`; nó **không bắt đầu clean lifecycle**. Maven có thể tái sử dụng những đầu ra và trạng thái phù hợp từ lần trước. Để yêu cầu một bản build sau khi dọn đầu ra cũ:

~~~bash
mvn clean package
~~~

Mặc dù `clean package` hay được dùng, không nên nghĩ `clean` là một phase của default lifecycle. Chúng thuộc **hai lifecycle khác nhau** và được gọi nối tiếp.

## 4. Default lifecycle: hành trình từ dự án tới artifact

Default lifecycle có nhiều phase, phục vụ các điểm móc từ khâu xác nhận cấu hình đến phân phối artifact. Danh sách theo thứ tự chuẩn là:

~~~text
validate
initialize
generate-sources
process-sources
generate-resources
process-resources
compile
process-classes
generate-test-sources
process-test-sources
generate-test-resources
process-test-resources
test-compile
process-test-classes
test
prepare-package
package
pre-integration-test
integration-test
post-integration-test
verify
install
deploy
~~~

Không cần ghi nhớ ngay toàn bộ danh sách. Hãy nhận diện các mốc có ý nghĩa trực tiếp:

| Phase | Ý nghĩa thường gặp với dự án Java |
| --- | --- |
| `validate` | Kiểm tra dự án và model/configuration cơ bản trước khi build. |
| `process-resources` | Sao chép/xử lý `src/main/resources` vào thư mục lớp đầu ra, thường là `target/classes`. |
| `compile` | Biên dịch mã nguồn chính `src/main/java`. |
| `process-test-resources` | Chuẩn bị tài nguyên từ `src/test/resources` cho test. |
| `test-compile` | Biên dịch mã nguồn test trong `src/test/java`. |
| `test` | Chạy unit test theo plugin/cấu hình test của dự án. |
| `package` | Đóng gói theo kiểu `jar`, `war` hoặc kiểu packaging đã chọn. |
| `integration-test` | Điểm móc cho bài kiểm thử tích hợp và việc phối hợp môi trường, nếu được cấu hình. |
| `verify` | Xác minh kết quả build/kiểm thử và các điều kiện chất lượng đã cấu hình. |
| `install` | Cài artifact và POM vào repository Maven **cục bộ** để dự án khác trên cùng môi trường có thể dùng. |
| `deploy` | Đưa artifact lên repository **từ xa** theo quy trình Maven deploy được cấu hình. |

Các phase như `generate-sources`, `process-sources`, `initialize` và `prepare-package` là **điểm mở rộng**: nếu không có goal nào gắn vào chúng, Maven đi qua mà không nhất thiết tạo ra dòng log công việc hay một tệp đầu ra mới. Không suy luận mọi phase đều thực thi một plugin.

### Khi chạy `mvn test`, `mvn package` hay `mvn verify`

- `mvn test`: chạy từ `validate` qua `test`, do đó thường xử lý resource, compile mã chính, compile mã test và chạy test. Nó **không tự chạy `package`**.
- `mvn package`: chạy tất cả phase trước `package` rồi đến `package`. Với packaging `jar`, nó thường tạo JAR trong `target/`.
- `mvn verify`: chạy tiếp qua `pre-integration-test`, `integration-test`, `post-integration-test` và `verify`. Nếu đã cấu hình plugin kiểm thử tích hợp như Maven Failsafe Plugin, đây là điểm dừng phù hợp để chạy và kiểm tra kết quả tích hợp.
- `mvn install`: chạy các phase cho đến `install`, bao gồm những bước của `verify`; kết quả được đưa vào repository cục bộ.
- `mvn deploy`: đi qua `install` và đến `deploy`; có thể tác động lên kho từ xa, vì vậy chỉ dùng khi được cấp quyền và có cấu hình publishing thực tế.

**Lưu ý về kiểm thử tích hợp:** chỉ vì tên phase là `integration-test` mà không có nghĩa mọi dự án tự có integration test. Cần khai báo plugin/goal tương ứng. Với nhiều dự án dùng Failsafe Plugin, chạy thẳng `mvn integration-test` có thể dừng trước phase `post-integration-test` (là điểm móc cleanup) và `verify` (nơi đánh giá kết quả). Khi muốn chạy đầy đủ kiểm thử tích hợp, hãy ưu tiên `mvn verify` theo cấu hình dự án.

## 5. Site lifecycle: tạo website tài liệu dự án

Site lifecycle có bốn phase:

| Phase | Vai trò |
| --- | --- |
| `pre-site` | Chuẩn bị trước khi sinh tài liệu/site; chỉ chạy goal nếu đã gắn. |
| `site` | Tạo website dự án thông qua Maven Site Plugin và các báo cáo liên quan đã cấu hình. |
| `post-site` | Bước sau khi dựng site, nếu có goal gắn vào. |
| `site-deploy` | Đưa website đã tạo tới vị trí công bố tài liệu theo cấu hình site deployment. |

Ví dụ:

~~~bash
mvn site
~~~

Lệnh gọi **phase `site`** và các phase đứng trước nó trong site lifecycle, thường tạo các tệp website ở:

~~~text
target/site/
└── index.html
~~~

Dự án có thể chứa nguồn tài liệu trong `src/site/` và cấu hình báo cáo bằng Maven Reporting Plugins. Site Plugin thường sinh HTML, CSS/tài nguyên giao diện và trang báo cáo tùy cấu hình. Bản site không phải JAR ứng dụng.

**`mvn site` không đồng nghĩa `mvn package`.** Site lifecycle có mục đích riêng, không bắt buộc chạy các phase biên dịch/đóng gói của default lifecycle trước đó. Nếu báo cáo site cần kết quả build, test hoặc Javadoc, quy trình dự án phải bảo đảm các đầu vào đó đã sẵn sàng.

### Không nhầm `deploy` và `site-deploy`

- `mvn deploy` chạy đến phase `deploy` thuộc **default lifecycle**, thường upload artifact JAR/POM lên Maven artifact repository bằng cơ chế triển khai đã cấu hình.
- `mvn site-deploy` chạy tới phase `site-deploy` thuộc **site lifecycle**, thường upload **website tài liệu** tới đích site được khai báo, ví dụ `distributionManagement.site`.

Hai đích upload và hai nhóm quyền xác thực có thể hoàn toàn khác nhau. Lệnh `site-deploy` chỉ có ý nghĩa khi site deployment được cấu hình đầy đủ, có thể yêu cầu protocol, Maven Wagon/provider hoặc credential phù hợp với môi trường. Không chạy thử với URL giả.

## 6. Thực hành: tạo một dự án Java 17 minh họa cả ba lifecycle

Ta tạo một dự án Java nhỏ để quan sát **cùng một POM** tham gia nhiều lifecycle. Cây thư mục:

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/
    │           └── example/
    │               └── App.java
    └── site/
        └── markdown/
            └── index.md
~~~

Tại đây:

- `pom.xml` mô tả dự án JAR và chọn phiên bản plugin cho build/site.
- `src/main/java/com/example/App.java` là mã Java độc lập.
- `src/site/markdown/index.md` là **nguồn nội dung trang site**, không phải Java source hay classpath resource.
- `target/classes/` và `target/site/` được tạo trong quá trình build/site; không phải thư mục nguồn cần commit.

### 6.1. Tệp `pom.xml`

Tạo `lifecycle-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Lifecycle Demo</name>
    <description>Vi du ve clean, default va site trong Maven.</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-site-plugin</artifactId>
                <version>3.12.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Những phiên bản plugin được **khai báo cụ thể để ví dụ dễ đối chiếu**, không có nghĩa chúng là phiên bản mới nhất. POM dùng cho Maven 3.x cùng JDK 17+; một môi trường Maven khác có thể có yêu cầu plugin tương thích riêng. Lần chạy đầu cần mạng nếu các plugin chưa nằm trong Maven cache. Java release 17 là mục tiêu của compiler, còn phiên bản Java **chạy Maven** được xác nhận bằng `mvn --version`.

POM chưa khai báo test dependency, nên bài này không có unit test người học viết. Phase `test` vẫn được Maven đi qua khi build đến `package`, nhưng không có ca kiểm thử do ví dụ cung cấp.

### 6.2. Mã Java chạy được

Tạo `src/main/java/com/example/App.java`:

~~~java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Maven lifecycles!");
    }
}
~~~

Lớp `App` có phương thức `main` hợp lệ, không cần thư viện ngoài JDK. Khi chạy được, stdout chính xác là:

~~~text
Hello from Maven lifecycles!
~~~

### 6.3. Nguồn tài liệu cho site

Tạo `src/site/markdown/index.md`:

~~~markdown
# Lifecycle Demo

Day la trang tai lieu duoc tao boi Maven Site Plugin.

- Clean: don dau ra cu.
- Default: bien dich va dong goi Java.
- Site: tao website tai lieu.
~~~

Nội dung cố ý dùng văn bản ASCII để giảm phụ thuộc vào cấu hình charset của bộ xử lý Markdown trong các môi trường khác nhau. Bạn có thể viết tiếng Việt có dấu nếu file được lưu UTF-8 và pipeline Doxia/Site Plugin được cấu hình xử lý charset nhất quán.

Tệp `index.md` phục vụ tạo trang HTML; nó **không tự được đóng gói vào JAR Java** vì `src/site/` không phải `src/main/resources/`.

## 7. Chạy thử từng lifecycle và quan sát đầu ra

Mở terminal trong thư mục `lifecycle-demo`, nơi chứa `pom.xml`. Kiểm tra trước:

~~~bash
mvn --version
java -version
javac -version
~~~

### Bước A — Default lifecycle đến `package`

~~~bash
mvn package
~~~

Maven đi qua các phase của default lifecycle đến `package`, tạo các đầu ra quan trọng:

~~~text
target/
├── classes/
│   └── com/
│       └── example/
│           └── App.class
└── lifecycle-demo-1.0-SNAPSHOT.jar
~~~

Đây là cây giản lược: Maven có thể tạo thêm thư mục metadata/plugin trong `target`.

Chạy lớp Java từ JAR:

~~~bash
java -cp target/lifecycle-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác:**

~~~text
Hello from Maven lifecycles!
~~~

Lệnh chạy với `-cp` vì POM chưa cấu hình `Main-Class` trong manifest. `java -jar target/lifecycle-demo-1.0-SNAPSHOT.jar` không phải cách chạy được bảo đảm cho ví dụ này.

### Bước B — Clean lifecycle

~~~bash
mvn clean
~~~

Quan sát `target/` bị xóa theo cấu hình mặc định. Đây là bằng chứng trực tiếp của clean lifecycle, **không phải lỗi build**. Mã nguồn `App.java` và `src/site/markdown/index.md` vẫn còn.

Sau `clean`, hãy build lại nếu muốn chạy lớp Java:

~~~bash
mvn clean package
java -cp target/lifecycle-demo-1.0-SNAPSHOT.jar com.example.App
~~~

Lệnh `mvn clean package` chạy hai lifecycle theo thứ tự, còn lệnh `java` chỉ kiểm tra artifact kết quả.

### Bước C — Site lifecycle

~~~bash
mvn site
~~~

Dự án có nguồn `src/site/markdown/index.md` và đã khai báo Maven Site Plugin. Sau khi lệnh thành công, kiểm tra `target/site/index.html` và mở tệp HTML bằng trình duyệt để xem trang tài liệu. Các resource CSS, hình hoặc metadata của site có thể nằm cạnh trang HTML trong `target/site`.

Site được tạo dựa trên nội dung `src/site/` và cấu hình báo cáo của Maven Site Plugin; nó không phải sản phẩm chạy bởi `java -cp`. Mặt khác, việc tạo site không cần chuyển nguồn Markdown sang `src/main/java` hay `src/main/resources`.

### Bước D — Chạy build và site trong một câu lệnh

~~~bash
mvn clean package site
~~~

Thứ tự mang ý nghĩa: dọn `target`, thực hiện default lifecycle tới `package`, sau đó thực hiện site lifecycle tới `site`. Sau khi cả ba phần thành công, bạn có thể thấy:

~~~text
target/
├── classes/com/example/App.class
├── lifecycle-demo-1.0-SNAPSHOT.jar
└── site/index.html
~~~

Vì `target` chứa cả JAR lẫn site, câu lệnh này giúp giữ hai nhóm đầu ra cùng từ một trạng thái nguồn tương ứng.

**Không đảo lệnh thành `mvn package clean` nếu mục tiêu là giữ artifact.** Maven xử lý tác vụ theo thứ tự được yêu cầu: sau khi build được JAR, phase `clean` có thể xóa chính thư mục `target` chứa JAR đó. Thứ tự trong câu lệnh nhiều phase có tác động thực tế.

## 8. Binding: phase nào chạy plugin goal nào?

**Lifecycle quyết định thứ tự; binding quyết định công việc.** Ví dụ điển hình cho `<packaging>jar</packaging>`:

| Lifecycle/phase | Goal thường được gắn | Tác dụng |
| --- | --- | --- |
| Clean / `clean` | `maven-clean-plugin:clean` | Xóa thư mục build output được cấu hình. |
| Default / `process-resources` | `maven-resources-plugin:resources` | Copy/xử lý tài nguyên chính. |
| Default / `compile` | `maven-compiler-plugin:compile` | Biên dịch Java chính. |
| Default / `process-test-resources` | `maven-resources-plugin:testResources` | Copy/xử lý tài nguyên test. |
| Default / `test-compile` | `maven-compiler-plugin:testCompile` | Biên dịch mã test. |
| Default / `test` | `maven-surefire-plugin:test` | Chạy unit test. |
| Default / `package` | `maven-jar-plugin:jar` | Tạo JAR cho packaging `jar`. |
| Default / `install` | `maven-install-plugin:install` | Cài artifact vào kho cục bộ. |
| Default / `deploy` | `maven-deploy-plugin:deploy` | Upload artifact ra repository từ xa. |
| Site / `site` | `maven-site-plugin:site` | Sinh website dự án. |
| Site / `site-deploy` | `maven-site-plugin:deploy` | Triển khai website đã tạo. |

Bảng mô tả **binding thường gặp**, không phải cam kết tất cả dự án có cấu hình giống nhau. Các plugin bổ sung hoặc override có thể gắn nhiều goal vào một phase. Ví dụ khi chuyển packaging từ `jar` sang `war`, goal đóng gói mặc định thường thuộc Maven WAR Plugin thay vì Maven JAR Plugin. Với `pom` packaging (thường gặp ở parent/aggregator), phase `package` không có nghĩa tự tạo một JAR Java.

Việc đặt một plugin trong `<build><plugins>` **không tự làm mọi goal của plugin chạy ở mọi lifecycle**. Goal chạy khi thuộc binding mặc định, được plugin descriptor khai báo phase mặc định trong ngữ cảnh invocation phù hợp, được cấu hình execution/phase cụ thể, hoặc được gọi trực tiếp.

### Ví dụ gắn một goal vào phase

Đoạn XML bên dưới chỉ là **mảnh cấu hình** để minh họa execution: chèn cấu hình `<executions>` bên trong khai báo plugin tương ứng trong `<build><plugins>`. Nếu goal vốn đã được packaging gắn mặc định, cần kiểm tra khả năng thực thi lặp trước khi bổ sung.

~~~xml
<executions>
    <execution>
        <id>run-at-verify</id>
        <phase>verify</phase>
        <goals>
            <goal>check</goal>
        </goals>
    </execution>
</executions>
~~~

Ở đây `<phase>verify</phase>` và `<goal>check</goal>` chỉ cho thấy **hình dạng cú pháp**. Để chạy thật, phải đặt đoạn XML dưới **một plugin có goal tên `check`**, đồng thời cấu hình và input cần thiết cho goal đó. Không được dán mảnh này vào một plugin không có goal `check` rồi cho rằng POM sẽ build được.

Với một plugin cụ thể, bạn có thể đọc tài liệu của chính plugin để biết goal, phase mặc định, input và side effect thay vì suy diễn từ tên goal.

## 9. So sánh các lệnh Maven dễ nhầm

| Lệnh | Lifecycle/đích xử lý | Kết quả cần hiểu |
| --- | --- | --- |
| `mvn clean` | Clean → `clean` | Dọn đầu ra cũ, không đóng gói lại. |
| `mvn compile` | Default → `compile` | Có lớp Java đã biên dịch, chưa chắc có JAR. |
| `mvn test` | Default → `test` | Chạy chuỗi phase cho đến test, chưa đóng gói. |
| `mvn package` | Default → `package` | Đóng gói theo packaging của POM. |
| `mvn clean package` | Clean → `clean`, rồi Default → `package` | Dọn và tạo bản package mới. |
| `mvn verify` | Default → `verify` | Thực hiện thêm các phase kiểm tra sau package (nếu có goal được gắn). |
| `mvn install` | Default → `install` | Đưa artifact vào kho Maven cục bộ. |
| `mvn deploy` | Default → `deploy` | Có thể upload artifact tới repository từ xa. |
| `mvn site` | Site → `site` | Sinh tài liệu website trong `target/site`. |
| `mvn clean site` | Clean → `clean`, rồi Site → `site` | Xóa output cũ, tạo site; **không tự build JAR**. |
| `mvn site-deploy` | Site → `site-deploy` | Tạo/triển khai site theo cấu hình site publishing, có tác động từ xa. |
| `mvn clean verify site` | Clean, Default → `verify`, rồi Site → `site` | Dọn, build/kiểm tra và sinh site. |

Cần nhớ rằng **`site` không phải phase nằm sau `deploy` trong default lifecycle**. Nó thuộc một lifecycle khác. Và `site-deploy` không phải biến thể của `deploy` dùng để xuất bản thư viện JAR.

## 10. Xem Maven đang làm gì trong log

Để hiểu lý do một plugin được chạy, thử:

~~~bash
mvn clean package
~~~

Những đoạn log thường có thông tin plugin/goal đang thực thi và kết thúc bằng trạng thái:

~~~text
[INFO] BUILD SUCCESS
~~~

Ví dụ trong log có thể thấy goal `clean`, `resources`, `compile`, `testResources`, `testCompile`, `test` và `jar`. Tên plugin, phiên bản và thứ tự các goal bổ sung phụ thuộc POM/packaging, profile và các plugin đã cấu hình, nên không coi đây là transcript cố định của mọi dự án.

Bạn có thể tăng mức chi tiết khi cần điều tra:

~~~bash
mvn -X package
~~~

`-X` bật debug logging, giúp quan sát cơ chế plugin execution và các cấu hình liên quan. Log debug có thể dài, có đường dẫn môi trường hoặc thông tin hệ thống; nên lọc phần cần thiết trước khi gửi cho người khác. Trước khi kết luận một goal đã chạy, hãy kiểm tra log **của đúng invocation và đúng module**.

Một lệnh kiểm tra POM hiệu lực là:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

`effective-pom` kết hợp cấu hình POM, parent và profile thích hợp, giúp phân tích cấu hình plugin/execution. Tuy nhiên, nó **không nên được coi là bản ghi đầy đủ của mọi goal thực tế đã chạy**: binding theo packaging, việc kích hoạt profile và điều kiện thực thi cần xem cùng log. Lệnh này có thể cần tải Maven Help Plugin trong lần đầu.

## 11. Site publishing và an toàn khi triển khai

Maven Site Plugin có thể tạo HTML cục bộ bằng `mvn site` mà không cần bạn có máy chủ website. Nếu muốn **công bố** site, thông thường cần chỉ định đích site trong POM, cùng transport/credential phù hợp.

Một dạng cấu hình minh họa cấp `project` là:

~~~xml
<distributionManagement>
    <site>
        <id>documentation-server</id>
        <name>Documentation Server</name>
        <url>scp://docs.example.org/var/www/html/lifecycle-demo</url>
    </site>
</distributionManagement>
~~~

Đây là URL **giả** để thấy cấu trúc metadata. Cấu hình ấy **chưa đủ bảo đảm triển khai chạy được**: giao thức `scp` có thể cần Maven Wagon/provider tương thích, server thực, quyền ghi và thông tin đăng nhập tách khỏi POM. `settings.xml` có thể chứa cấu hình server theo `id`, còn credential bí mật nên được cấp an toàn từ môi trường/CI.

Khi cần xuất bản **artifact JAR**, Maven deploy truyền thống thường nhìn vào `distributionManagement.repository` / `snapshotRepository`; khi cần xuất bản **website site**, plugin dùng `distributionManagement.site`. Quy trình publish hiện đại có thể dùng plugin hoặc dịch vụ khác, nên luôn đối chiếu hệ thống phát hành đang dùng.

Không đặt token hay mật khẩu vào `pom.xml`, không dùng đích sản xuất trong bài thực hành và không chạy `mvn deploy`/`mvn site-deploy` khi chưa có quyền cùng cấu hình chính xác.

## 12. Những lỗi và hiểu lầm thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Chạy `mvn clean` xong, không thấy JAR | Clean chỉ dọn output. | Chạy `mvn package` hoặc `mvn clean package` để tạo lại artifact. |
| `mvn package` chạy nhưng JAR cũ vẫn xuất hiện trong `target` | Không gọi clean, hoặc đã thay tên artifact/version. | Kiểm tra đúng tệp và chạy `mvn clean package` khi cần build sạch. |
| `mvn test` thành công nhưng không có JAR | `test` đứng trước `package`. | Dùng `mvn package` khi cần đóng gói. |
| `mvn verify` không chạy bài integration test dự kiến | Chưa cấu hình plugin/goal kiểm thử tích hợp. | Kiểm tra Maven Failsafe Plugin hoặc công cụ integration test đang dùng và phase binding. |
| `mvn integration-test` để lại môi trường test | Đã dừng trước `post-integration-test`/`verify`. | Dùng `mvn verify` theo workflow của dự án để có cleanup/xác minh khi goal được gắn đúng. |
| `mvn site` không tạo JAR | Site lifecycle dành cho tài liệu. | Chạy `mvn package` riêng hoặc `mvn package site` theo thứ tự phù hợp. |
| Không tìm thấy `target/site/index.html` | Site goal lỗi, nguồn site/cấu hình plugin có vấn đề hoặc thư mục bị clean sau đó. | Xem log `mvn site`, đường dẫn `src/site`, plugin version và thứ tự lệnh. |
| `mvn clean package site` chạy xong, site không có báo cáo test | Site Plugin không tự tạo mọi loại báo cáo; plugin report có thể chưa cấu hình. | Đối chiếu cấu hình reporting và dữ liệu test/build cần thiết. |
| Maven nói “Unknown lifecycle phase” hoặc “Unknown lifecycle phase default” | Gọi sai tên phase hay dùng tên lifecycle như phase. | Dùng tên phase hợp lệ như `compile`, `package`, `verify`, `site`. |
| Đổi packaging sang `pom` rồi `package` không tạo JAR | Binding của packaging `pom` khác `jar`. | Kiểm tra `<packaging>` và plugin đóng gói cần thiết. |
| `mvn deploy` báo thiếu repository hoặc 401/403 | Chưa khai báo đúng đích, credential hoặc chưa có quyền. | Kiểm tra cấu hình distribution, ID server và quyền phát hành. |
| `mvn site-deploy` lỗi transport/đường dẫn | Đích site, giao thức hoặc quyền công bố website chưa cấu hình hoàn chỉnh. | Kiểm tra site publishing riêng; không dùng cấu hình deploy artifact để suy ra site deploy. |
| Các phase có vẻ “bị bỏ qua” trong log | Không có plugin goal gắn vào phase, hoặc goal không cần làm gì với input hiện tại. | Phân biệt phase với goal; xem POM, packaging và thông tin plugin execution. |

Chẩn đoán theo thứ tự: **lệnh đã gọi đến phase nào → phase thuộc lifecycle nào → packaging của POM là gì → goal nào thực sự được gắn → log goal và đầu ra thực tế**. Nhìn đường đi này rõ ràng thường giúp phát hiện nhầm lẫn nhanh hơn việc thay các phiên bản plugin một cách ngẫu nhiên.

## 13. Bài tập tự kiểm chứng

1. Tạo ba tệp `pom.xml`, `src/main/java/com/example/App.java` và `src/site/markdown/index.md` đúng như hướng dẫn.
2. Chạy `mvn package`. Xác nhận xuất hiện JAR `target/lifecycle-demo-1.0-SNAPSHOT.jar`, chạy lớp `com.example.App` và kiểm tra đúng một dòng stdout.
3. Chạy `mvn clean`. Quan sát output `target` được xóa, còn `src/main/java` và `src/site` giữ nguyên.
4. Chạy `mvn site` trên dự án vừa clean. Quan sát `target/site/index.html` được tạo, nhưng **không mặc định có `target/classes/App.class` hay JAR** vì chưa chạy default lifecycle.
5. Chạy `mvn clean package site`. Quan sát đồng thời JAR, `target/classes` và site trong `target`.
6. Xem log và gán tên goal vào phase của bảng binding: goal nào tạo `App.class`, goal nào tạo JAR, goal nào tạo `index.html`?
7. Giải thích vì sao `mvn package clean` có thể làm mất artifact vừa đóng gói và vì sao `mvn verify` phù hợp hơn `mvn integration-test` đối với workflow đã gắn integration test/cleanup.
8. Thử `mvn compile` sau clean; xác nhận tạo bytecode nhưng chưa yêu cầu Maven tới phase `package`.

**Câu hỏi tự đánh giá:** `clean` có thuộc default lifecycle không? `mvn test` có đi qua `compile` không? Một phase không có goal thì xảy ra chuyện gì? `mvn site` có thể chạy độc lập với `mvn package` không? `deploy` và `site-deploy` khác nhau ở sản phẩm và đích xuất bản nào?

Khi trả lời được bằng đầu ra và log của chính dự án, bạn sẽ nắm được cách Maven tổ chức công việc: **clean dọn đầu ra, default tạo và xác minh artifact, site tạo tài liệu; phase quyết định thứ tự, plugin goal thực hiện hành động**.
