# Build mô-đun bằng `-pl`: phân biệt đường dẫn với `:artifactId` trong Maven Reactor

> **Build Tool Maven · Reactor nhiều mô-đun**  
> Trọng tâm: chọn đúng **project trong reactor** bằng `-pl`/`--projects`, hiểu vì sao `-pl apps/cli` khác `-pl :cli-tool`, khi nào dùng `groupId:artifactId`, và cách phối hợp `-am`, `-amd`, `-rf` trong Maven 3.x. Bài có dự án **Java 17** nhiều mô-đun, POM đầy đủ, các lệnh chạy lại được và kết quả kiểm chứng.

## 1. Câu trả lời ngắn nhất: `-pl` nhận *project selector*, không chỉ tên module

Trong một Maven multi-module build, lệnh:

```bash
mvn -pl apps/cli clean package
```

có nghĩa là **chọn project nằm ở đường dẫn `apps/cli`**, tương đối với reactor được Maven thu thập từ POM gốc.

Còn:

```bash
mvn -pl :cli-tool clean package
```

có nghĩa là **chọn project có `artifactId=cli-tool`** trong reactor.

Nếu muốn dùng tọa độ Maven rõ hơn:

```bash
mvn -pl org.example:cli-tool clean package
```

thì Maven chọn project có **`groupId=org.example` và `artifactId=cli-tool`** trong reactor.

Các selector này có thể trỏ đến **cùng một project**, mặc dù chuỗi `apps/cli`, `cli-tool` và `org.example:cli-tool` không giống nhau. Ngược lại:

```bash
mvn -pl cli-tool clean package
```

**không** có nghĩa “chọn artifactId `cli-tool`”. Theo tài liệu Apache Maven, một **tên trần không có dấu hai chấm** được hiểu là **đường dẫn**. Nếu không có thư mục module `cli-tool` ở vị trí tương ứng, selector sẽ không tìm được project.

**Ghi nhớ:** `-pl đường/dẫn/tương/đối`, `-pl :artifactId`, `-pl groupId:artifactId`.

### Bảng phân biệt

| Selector | Maven hiểu là | Phụ thuộc điều gì? | Ví dụ |
| --- | --- | --- | --- |
| `-pl apps/cli` | Đường dẫn project trong reactor | Vị trí thư mục module | Chọn POM ở `apps/cli/pom.xml` |
| `-pl ./apps/cli` | Đường dẫn tương đối | Vị trí thư mục và reactor gốc | Tương đương về ý định với `apps/cli` |
| `-pl :cli-tool` | Artifact ID | Giá trị `<artifactId>` của project | Chọn project có artifactId `cli-tool` |
| `-pl org.example:cli-tool` | Group ID + Artifact ID | Tọa độ G:A trong POM hiệu lực | Chọn chính xác `org.example:cli-tool` |
| `-pl cli-tool` | **Đường dẫn `cli-tool`** | Phải có module ở path đó | **Không** tự tra artifactId |
| `-pl :apps/cli` | Artifact ID `apps/cli` | Phải có artifactId khớp (không hợp lý cho ví dụ) | **Không** phải đường dẫn `apps/cli` |
| `-pl apps/cli,apps/web` | Danh sách hai đường dẫn | Cả hai là project đã được thu thập | Chọn hai modules |
| `-pl :cli-tool,:web-app` | Danh sách hai artifact IDs | Project IDs phải có trong reactor | Chọn hai modules |

Cú pháp `-pl` là viết tắt của `--projects`; nó là **Maven CLI option**, không phải plugin Maven cần khai báo trong POM. Dùng `-P` (chữ P viết hoa) là **chọn profiles**, hoàn toàn khác `-pl` (chữ p thường + chữ l thường).

## 2. Maven Reactor là gì?

Một project nhiều mô-đun thường có POM gốc:

```xml
<packaging>pom</packaging>
<modules>
    <module>shared/core</module>
    <module>apps/cli</module>
    <module>apps/web</module>
</modules>
```

Khi chạy Maven từ POM gốc, **reactor**:

1. Thu thập projects được khai báo bằng `<modules>` cùng các thành phần được cấu hình phù hợp.
2. Xác định **quan hệ và thứ tự xây dựng** giữa các projects.
3. Chọn project subset nếu có `-pl`, cùng các tùy chọn bổ sung.
4. Chạy lifecycle goals/phases trên các projects được chọn theo thứ tự cần thiết.

Nếu không dùng `-pl`:

```bash
mvn clean package
```

thì thông thường Maven build toàn bộ các projects trong reactor đã được thu thập, bao gồm parent/aggregator và các modules.

Nếu dùng:

```bash
mvn -pl apps/cli clean package
```

thì Maven **chỉ chọn project CLI**, không có nghĩa CLI được phép tự động lấy toàn bộ module phụ thuộc trong reactor. Muốn build kèm các modules cần cho nó, thường thêm **`-am`**.

### 2.1. Aggregation không giống inheritance

Hai mối quan hệ thường gặp:

- **Aggregation:** Root POM có `<modules>` để thu thập reactor projects và xác định đường dẫn của chúng.
- **Inheritance:** Child POM có `<parent>` để nhận cấu hình Maven từ parent POM như properties, pluginManagement, dependencyManagement.

Một module được liệt kê dưới `<modules>` **không đương nhiên kế thừa** mọi cấu hình parent nếu POM của nó không khai báo quan hệ parent đúng. Ngược lại, một child có thể kế thừa parent POM từ repository nhưng **không được thu thập trong reactor hiện tại** nếu không nằm trong danh sách modules/việc thu thập hiện tại.

`-pl` chọn trong **tập projects mà invocation hiện tại biết đến**, không tìm bất kỳ artifact nào trên Maven Central hoặc toàn bộ filesystem.

### 2.2. Reactor sắp xếp theo phụ thuộc, không đơn giản theo thứ tự khai báo

Nếu `apps/cli` phụ thuộc `shared/core`, reactor cần build **core trước CLI** dù `<modules>` có thể liệt kê CLI trước. Apache Maven Reactor Guide nêu các quan hệ ảnh hưởng sort order như dependencies, plugin dependencies, build extensions và parent relation. Trong nhiều trường hợp không có quan hệ khác thì thứ tự `<modules>` là yếu tố tie-break.

Lưu ý: Chỉ có một entry trong `<dependencyManagement>` hoặc `<pluginManagement>` mà không có dependency/plugin được sử dụng thực tế **không tự tạo quan hệ sort order**.

### 2.3. `-pl` chọn subset; `-am` và `-amd` mở rộng subset

Một quy tắc rất đáng nhớ:

```text
-pl   = Tôi muốn những project nào?
-am   = Đồng thời build những upstream projects trong reactor mà lựa chọn này cần.
-amd  = Đồng thời build những downstream projects trong reactor phụ thuộc lựa chọn này.
```

Các tùy chọn có tên dài:

```text
-pl   == --projects
-am   == --also-make
-amd  == --also-make-dependents
-rf   == --resume-from
```

`-am` không tự build một dependency **ngoài reactor** và cũng không tự tải source code của dependencies. Các dependencies bên ngoài reactor vẫn được Maven resolve theo local/remote repositories như thông thường.

## 3. Dự án Java 17 mẫu: thư mục khác artifactId

Bài dùng một dự án Maven 3.x có một parent/aggregator POM và **ba JAR modules**.

| Vai trò | Đường dẫn thư mục | `groupId:artifactId` | Phụ thuộc module trong reactor |
| --- | --- | --- | --- |
| Aggregator/parent | `.` | `org.example:reactor-selector-demo` | Không |
| Core library | `shared/core` | `org.example:util-core` | Không |
| CLI application | `apps/cli` | `org.example:cli-tool` | `org.example:util-core` |
| Web-style demo application | `apps/web` | `org.example:web-app` | `org.example:util-core` |

**Chủ ý của thiết kế:** **không có module nào tên thư mục trùng với `artifactId`** (`shared/core` khác `util-core`, `apps/cli` khác `cli-tool`). Vì vậy không thể hiểu lẫn đường dẫn và `:artifactId` mà vẫn chạy “tình cờ đúng”.

### 3.1. Cây thư mục

```text
reactor-selector-demo/
├── pom.xml
├── shared/
│   └── core/
│       ├── pom.xml
│       └── src/
│           └── main/
│               └── java/
│                   └── org/example/core/Greeting.java
└── apps/
    ├── cli/
    │   ├── pom.xml
    │   └── src/
    │       └── main/
    │           └── java/
    │               └── org/example/cli/Main.java
    └── web/
        ├── pom.xml
        └── src/
            └── main/
                └── java/
                    └── org/example/web/WebMain.java
```

`web` ở đây chỉ là tên module để minh họa một **downstream consumer** khác của core. Nó là một project JAR Java đơn giản, **không** dựng HTTP server, servlet container hay Spring Boot. Nhờ vậy bài tập tập trung vào **reactor selection**, không bị phụ thuộc framework.

### 3.2. Root `reactor-selector-demo/pom.xml` — POM hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>reactor-selector-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared/core</module>
        <module>apps/cli</module>
        <module>apps/web</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Giải thích:**

- `<packaging>pom</packaging>` cho root aggregator/parent; root không tạo ứng dụng `.jar` như những children.
- `<modules>` khai báo **đường dẫn thư mục** tương đối tới root POM, **không khai báo artifactId**.
- `maven.compiler.release=17` đặt Java 17 target.
- `pluginManagement` ghim Maven Compiler Plugin/JAR Plugin versions cho child builds kế thừa; plugin versions được chọn có chủ đích để code biên dịch bằng JDK 17.
- Root là project `org.example:reactor-selector-demo`, có vai trò build orchestration, không phải nguồn Java chính của các modules.

Không nhầm `<module>shared/core</module>` với `<artifactId>util-core</artifactId>`: **cả hai hợp lệ, nhưng biểu diễn hai thứ khác nhau**.

### 3.3. `shared/core/pom.xml` — POM hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example</groupId>
        <artifactId>reactor-selector-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../../pom.xml</relativePath>
    </parent>

    <artifactId>util-core</artifactId>
    <packaging>jar</packaging>
</project>
```

Vì module ở `shared/core`, đường dẫn quay về root parent POM là `../../pom.xml` (đi lên từ `core` qua `shared` rồi tới root).

`groupId=org.example` và `version=1.0.0` được **kế thừa parent**, nên tọa độ module hiệu lực là:

```text
org.example:util-core:jar:1.0.0
```

Khi dùng `-pl`, selector G:A tương ứng là:

```bash
mvn -pl org.example:util-core clean package
```

Không thêm packaging/version vào project selector khi cú pháp yêu cầu `[groupId]:artifactId`.

### 3.4. `shared/core/src/main/java/org/example/core/Greeting.java`

```java
package org.example.core;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from core";
    }

    public static int add(int a, int b) {
        return a + b;
    }
}
```

Đây là Java source độc lập thuộc module `util-core`. Hai consumers có thể gọi `Greeting.message()` và `Greeting.add()`. Không có external runtime dependencies, nên kết quả in sẽ ổn định trên Java 17.

### 3.5. `apps/cli/pom.xml` — POM hoàn chỉnh

**`apps/cli/pom.xml` hoàn chỉnh:** Thư mục `apps/cli` khác artifactId `cli-tool`; project phụ thuộc module `util-core` trong reactor. Kế thừa parent theo đường dẫn `../../pom.xml`.

```xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                    https://maven.apache.org/xsd/maven-4.0.0.xsd"
```

**Ý nghĩa:** Child POM kế thừa `groupId=org.example`, `version=1.0.0`, Java release và plugin versions từ parent. Dependency `org.example:util-core:1.0.0` tạo quan hệ build nên khi core và CLI cùng được chọn, core được reactor sắp trước CLI.

### 3.6. `apps/cli/src/main/java/org/example/cli/Main.java`

```java
package org.example.cli;

import org.example.core.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("CLI: " + Greeting.message());
        System.out.println("2 + 3 = " + Greeting.add(2, 3));
    }
}
```

Khi classpath có cả `cli-tool` output và `util-core` output, **stdout chính xác** là:

```text
CLI: Hello from core
2 + 3 = 5
```

### 3.7. `apps/web/pom.xml` — POM hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example</groupId>
        <artifactId>reactor-selector-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../../pom.xml</relativePath>
    </parent>
    <artifactId>web-app</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>util-core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

Đường dẫn vẫn là `apps/web`, không phải `web-app`. Tên `web-app` nằm trong `<artifactId>`.

### 3.8. `apps/web/src/main/java/org/example/web/WebMain.java`

```java
package org.example.web;

import org.example.core.Greeting;

public final class WebMain {
    private WebMain() {
    }

    public static void main(String[] args) {
        System.out.println("WEB: " + Greeting.message());
    }
}
```

Với classpath chứa `web-app` và `util-core`, stdout chính xác là:

```text
WEB: Hello from core
```

## 4. Build toàn bộ reactor để hiểu thứ tự

Đứng trong thư mục **`reactor-selector-demo/` chứa root `pom.xml`**:

```bash
java -version
javac -version
mvn -version
mvn -B clean package
```

Kết quả Maven reactor sẽ đi qua bốn projects:

```text
reactor-selector-demo (pom)
util-core             (jar)
cli-tool              (jar)
web-app               (jar)
```

Đây là **thứ tự quan hệ minh họa**: parent trước children, `util-core` trước cả `cli-tool` và `web-app`. Hai consumers không phụ thuộc lẫn nhau, nên thứ tự chúng chạy có thể theo thứ tự `<modules>` hoặc biến thể khi parallel build. Đừng viết integration test dựa vào một thứ tự không được dependency graph bảo đảm.

Sau build, artifacts cần có:

```text
shared/core/target/util-core-1.0.0.jar
apps/cli/target/cli-tool-1.0.0.jar
apps/web/target/web-app-1.0.0.jar
```

Bản main JAR của các modules chưa có `Main-Class` trong manifest, nên không giả định dùng `java -jar` được. Hãy chạy Java CLI bằng classpath gồm **hai output directories** tương ứng:

**Linux/macOS:**

```bash
java -cp "apps/cli/target/classes:shared/core/target/classes" org.example.cli.Main
java -cp "apps/web/target/classes:shared/core/target/classes" org.example.web.WebMain
```

**Windows PowerShell/cmd:**

```powershell
java -cp "apps/cli/target/classes;shared/core/target/classes" org.example.cli.Main
java -cp "apps/web/target/classes;shared/core/target/classes" org.example.web.WebMain
```

Stdout chương trình CLI:

```text
CLI: Hello from core
2 + 3 = 5
```

Stdout chương trình WebMain:

```text
WEB: Hello from core
```

**Giải thích khác biệt dấu `:` và `;`:** chúng là separator của **Java CLI classpath theo OS**, không liên quan đến dấu `:` trong selector Maven `:artifactId`. Trên Windows `-pl :cli-tool` vẫn dùng dấu hai chấm bình thường; chỉ `java -cp` mới dùng `;` để phân tách nhiều paths.

## 5. `-pl` theo đường dẫn: khi nào đúng, khi nào sai?

Tất cả lệnh dưới đây chạy **từ root reactor** của project ví dụ, trừ khi ghi rõ khác.

### 5.1. Đúng: dùng đường dẫn module

```bash
mvn -pl shared/core -am clean package
mvn -pl apps/cli -am clean package
mvn -pl apps/web -am clean package
```

Lý do:

- `<modules>` trong root khai báo đúng những paths này.
- Maven tìm POM tương ứng, đọc GAV rồi chọn project.
- `-am` đảm bảo các **reactor dependencies** cần thiết được đưa vào build (mục 8).

### 5.2. Sai với cấu trúc ví dụ: dùng artifactId như tên thư mục

```bash
mvn -pl cli-tool clean package
```

Maven hiểu **đường dẫn `cli-tool`**, trong khi project CLI nằm ở `apps/cli`. Không có module `cli-tool` ở root, nên Maven có thể báo:

```text
Could not find the selected project in the reactor: cli-tool
```

Đây là **dạng lỗi tiêu biểu**, không cam kết nguyên văn log theo mọi bản Maven. Lỗi không phải do artifactId `cli-tool` không tồn tại; chính xác hơn là **selector đang ở dạng path** không khớp với project path.

Cách sửa:

```bash
mvn -pl apps/cli -am clean package
```

hoặc:

```bash
mvn -pl :cli-tool -am clean package
```

### 5.3. Đừng thêm `:` phía trước đường dẫn

Lệnh:

```bash
mvn -pl :apps/cli clean package
```

không có nghĩa “chọn thư mục `apps/cli`”. Nó cố dùng **artifactId `apps/cli`** (không khớp với bài). Khi muốn đường dẫn, giữ nguyên `apps/cli` **không có `:` đầu**.

### 5.4. Path được hiểu trong phạm vi reactor invocation

Một selector path **không phải cơ chế tìm kiếm toàn máy**. Maven cần biết project từ reactor đã được thu thập. Nếu bạn sửa `<modules>` bỏ `apps/cli` ra khỏi root, `-pl apps/cli` từ root không có nghĩa Maven sẽ tự thêm project ấy trở lại reactor chỉ vì filesystem còn directory.

Tương tự, một POM thư viện nằm ngoài root reactor nhưng cùng tên folder cũng không thể được chọn bằng `-pl` trừ khi nó tham gia collection của invocation đó.

### 5.5. Dùng slash cho path trong lệnh Maven

Viết:

```bash
mvn -pl apps/cli -am package
```

là cách dễ mang giữa Windows, Linux và macOS. Đừng nhầm Maven module path trong `<modules>` với hệ phân cách classpath Java: `apps/cli` là project directory path, không phải danh sách nhiều paths.

## 6. `-pl :artifactId`: chọn theo danh tính Maven

Các lệnh tương đương về **project được chọn** trong demo:

```bash
mvn -pl apps/cli clean package
mvn -pl :cli-tool clean package
mvn -pl org.example:cli-tool clean package
```

Nhưng **kết quả build thành công** còn phụ thuộc việc `util-core` đã được resolve hay không. Vì vậy trong demo thực hành, hãy thêm `-am` khi cần build CLI từ một reactor sạch:

```bash
mvn -pl :cli-tool -am clean package
```

### 6.1. Lợi thế của `:artifactId`

Nếu thư mục CLI đổi từ:

```text
apps/cli
```

thành:

```text
tools/command-line
```

và root `<modules>` được cập nhật tương ứng, selector:

```bash
mvn -pl :cli-tool -am clean package
```

vẫn có thể chọn project vì **artifactId không đổi**. Còn `-pl apps/cli` phải thay theo layout mới.

Tuy nhiên, nếu artifactId thay đổi từ `cli-tool` thành `command-line-tool` mà đường dẫn vẫn `apps/cli`, thì **selector theo đường dẫn** vẫn đúng nhưng `:cli-tool` không còn khớp.

### 6.2. Khi nào nên dùng `groupId:artifactId`?

Trong một reactor lớn, có thể có nhiều projects với **artifactId giống nhau** nhưng groupId khác nhau:

```text
org.example.frontend:shared
org.example.backend:shared
```

Selector:

```bash
mvn -pl :shared clean package
```

chỉ nêu artifactId, nên có thể **mơ hồ** khi có nhiều project cùng tên artifact. Tùy Maven version/collection, kết quả có thể không như bạn kỳ vọng hoặc selector gặp vấn đề về tính duy nhất. Trong tình huống này, dùng:

```bash
mvn -pl org.example.backend:shared clean package
```

để nêu **G:A rõ ràng**.

Trong demo hiện tại, cú pháp:

```bash
mvn -pl org.example:cli-tool -am clean package
```

chọn đúng CLI. **Không** dùng:

```text
org.example:cli-tool:1.0.0
```

như `-pl` selector tiêu chuẩn chỉ yêu cầu `[groupId]:artifactId`. Version trong tọa độ artifact thực tế là thông tin khác.

### 6.3. Có cần escape dấu `:` không?

Không. Với lệnh Maven thông thường:

```bash
mvn -pl :cli-tool -am package
```

đối số `:cli-tool` là một chuỗi project selector. **Dấu `:` không phải phân cách classpath ở đây**, và bạn không thêm path separator hệ điều hành cho nó.

## 7. Danh sách project: một lệnh có thể chọn nhiều module

Maven nhận **danh sách phân tách bằng dấu phẩy** sau `-pl`:

```bash
mvn -pl apps/cli,apps/web -am clean package
```

hoặc:

```bash
mvn -pl :cli-tool,:web-app -am clean package
```

hoặc:

```bash
mvn -pl org.example:cli-tool,org.example:web-app -am clean package
```

Nếu trong shell có rules khác nhau cho ký tự đặc biệt, **quote toàn bộ danh sách** để tránh shell xử lý không mong muốn:

```bash
mvn -pl ':cli-tool,:web-app' -am clean package
```

Khi chọn cả hai apps, `-am` thêm `util-core` vì hai apps đều phụ thuộc module ấy. Nó không build `util-core` **hai lần** chỉ vì hai apps cùng sử dụng nó; reactor quản lý **một project** cho mỗi module.

### 7.1. Phối hợp path và artifactId trong cùng danh sách

Có thể kết hợp selectors:

```bash
mvn -pl 'shared/core,:cli-tool' -am clean package
```

Một mục chọn **path**, mục kia chọn **artifact ID**. Tuy nhiên trong scripts CI, nên chọn một style nhất quán để dễ đọc, nhất là khi project layout thay đổi.

### 7.2. Phân biệt lựa chọn và sắp xếp thứ tự

Thứ tự viết trong list `-pl` **không ghi đè dependency order**. Ví dụ:

```bash
mvn -pl ':cli-tool,:util-core' clean package
```

không có nghĩa CLI sẽ được build trước core khi cả hai đã chọn và có dependency relation. Reactor sắp xếp core trước CLI.

### 7.3. Exclude project bằng `!` — ghi nhớ shell quoting

Maven 3.x hỗ trợ dấu phủ định `!` cho project selector trong những phiên bản thông dụng. Ví dụ muốn loại module web khỏi tập đang được chọn:

```bash
mvn -pl '!apps/web' clean package
```

Ở Bash, dấu `!` có thể bị history expansion nếu không quote; trong PowerShell cũng nên quote nguyên selector để dễ mang lệnh. Lệnh exclusion chỉ có ý nghĩa trong **reactor đã thu thập**: nó không tự thay đổi `<modules>` hoặc loại dependency khỏi project POM.

Nếu module còn lại **cần** module bị loại và dependency artifact không được resolve từ repository, build có thể fail; exclusion không xóa dependency GAV.

**Thận trọng:** các quy tắc selection kết hợp exclude với `-am`/`-amd` và Maven versions có thể phức tạp. Với CI quan trọng, kiểm tra **Reactor Build Order** trước khi dùng lệnh phủ định.

## 8. Vấn đề lớn nhất: `-pl` không tự build các module cần thiết

Trong demo:

```text
util-core
   |--------------------|
   v                    v
cli-tool               web-app
```

`cli-tool` cần `util-core`. Nếu chạy:

```bash
mvn -pl :cli-tool clean package
```

Maven chọn **chỉ project CLI**. Nó vẫn thấy trong POM của CLI:

```xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>util-core</artifactId>
    <version>${project.version}</version>
</dependency>
```

nhưng Maven **không tự đưa `util-core` vào reactor build** chỉ vì bạn đã dùng `-pl`. Nếu `org.example:util-core:1.0.0` không có trong local/remote repository, build có thể báo:

```text
Could not find artifact org.example:util-core:jar:1.0.0
```

Nếu local repository có một bản `util-core` đã `install` trước đó, CLI có thể build thành công **nhưng dùng bản cũ**, không phải thay đổi source mới nhất trong reactor. Đây là bẫy thường gặp khi debug.

### 8.1. Cách chuẩn: thêm `-am`

Chạy:

```bash
mvn -pl :cli-tool -am clean package
```

`-am` (*also make*) yêu cầu Maven build **những projects trong reactor mà lựa chọn hiện tại phụ thuộc**. Trong demo, tập quan trọng sẽ gồm:

```text
reactor-selector-demo (parent/aggregator khi được đưa vào do quan hệ build)
util-core
cli-tool
```

`web-app` không được chọn vì nó **phụ thuộc core**, chứ CLI **không phụ thuộc web**.

Tùy Maven version và cách parent được thu thập/chọn, thông tin reactor summary có thể hiển thị parent như một project được build. Không dựa vào chính xác số dòng log parent; tiêu chí là **core và CLI được build, web không bị kéo vào chỉ vì cùng dùng core**.

### 8.2. `-am` chỉ thêm module *trong reactor*

Nếu CLI còn phụ thuộc một JAR ngoài reactor, ví dụ từ Apache Commons, `-am` không tải source project Commons hay build nó từ đầu. Maven vẫn resolve external dependency như bình thường thông qua local/remote repositories.

Vì vậy câu “`-am` build tất cả dependencies” nên hiểu chính xác là **các dependency projects hiện diện trong reactor** (và những quan hệ Maven hỗ trợ khi lựa chọn). Không phải Maven tự clone mọi dependency source repo.

### 8.3. Đừng nhầm `package` với `install`

Lệnh:

```bash
mvn -pl :cli-tool -am clean package
```

sẽ tạo artifacts trong các module `target/`, nhưng **không nhất thiết cài chúng vào local Maven repository `~/.m2/repository`**. `package` tạo artifact, còn `install` thực hiện thêm bước cài artifact vào local repository.

Nếu sau đó bạn chạy **một invocation mới chỉ chọn CLI** mà không có `-am`, nó có thể không thấy `util-core` mới nhất qua repository. Giữ `-am` trong selective builds là cách tránh dựa vào local cached artifact.

Khi cần cài vào local repository cho một invocation ngoài reactor:

```bash
mvn -pl :cli-tool -am clean install
```

Lưu ý `install` thay đổi local Maven repository của người chạy. Không dùng nó như yêu cầu bắt buộc mọi lần CI chỉ cần verify build; trong CI, thường ưu tiên `verify` và quản lý artifacts/cache rõ ràng.

### 8.4. Lệnh nên chọn trong một checkout sạch

Khuyến nghị:

```bash
mvn -B -pl :cli-tool -am clean verify
```

Maven sẽ build các dependencies cùng reactor cần thiết và kiểm tra CLI tới phase verify. **Lệnh không tự bảo đảm đã chạy tests** nếu project không có test sources hoặc Surefire/Failsafe bị skip/config sai; hãy xem test reports khi đó là quality gate.

## 9. `-amd` là chiều ngược lại của `-am`

`-amd` viết tắt của `--also-make-dependents`: từ một project được chọn, Maven xét **các project khác trong reactor phụ thuộc vào nó**.

Trong demo, thay `Greeting.message()` của `util-core` có thể ảnh hưởng cả CLI và web-app. Để build core cùng các consumers:

```bash
mvn -pl :util-core -amd clean package
```

Kết quả quan trọng về **phạm vi module**:

```text
util-core
cli-tool
web-app
```

Đây là các projects liên quan theo chiều downstream. Parent/aggregator có thể xuất hiện trong summary theo cách Maven thu thập, nhưng **đừng hiểu `-amd` là “chỉ build các dependencies của core”** — đó là **chiều ngược**.

### 9.1. Một hình minh họa

```text
             util-core
             /      \
            v        v
         cli-tool   web-app

-pl :cli-tool -am
  -> cli-tool + util-core (upstream)

-pl :util-core -amd
  -> util-core + cli-tool + web-app (downstream)
```

**Lệnh `-am` thường là bước cần khi build một module dùng dependency nội bộ.** **`-amd` hữu ích khi thay đổi thư viện chung và muốn kiểm tra các consumers bị ảnh hưởng.**

### 9.2. Có thể phối hợp `-am` và `-amd` không?

Có những workflow vừa cần upstream prerequisites vừa cần downstream consumers. Nhưng phạm vi thực tế phụ thuộc reactor graph và Maven version. Một command có thể dùng:

```bash
mvn -pl :util-core -am -amd clean verify
```

Điều quan trọng là **đọc reactor build order** và hiểu tập selected projects: kết hợp không phải mặc định “build cả repository” nếu có những modules không liên quan. Nếu cần quality gate cho toàn reactor, `mvn clean verify` từ root thường minh bạch hơn.

### 9.3. `-pl :cli-tool -amd` không giúp build util-core

`-amd` chọn **dependents of CLI**, không phải prerequisites mà CLI cần. Nếu CLI cần core nhưng core chưa có artifact, dùng `-am` chứ không dùng `-amd` để sửa lỗi resolve core.

## 10. `-rf` để resume: khác hoàn toàn `-pl`

`-rf`/`--resume-from` là tùy chọn **tiếp tục reactor từ một project** trong thứ tự build, hữu ích sau khi một project ở giữa reactor fail.

Ví dụ:

```bash
mvn -rf :cli-tool package
```

không có nghĩa “build riêng CLI cùng các dependencies”. Nó có nghĩa **resume reactor từ CLI trở đi** trong context selection của invocation. Các projects ở trước điểm resume có thể không được build lại.

Điều này thường an toàn hơn khi dependencies trước đó đã hoàn tất và artifacts cần thiết đã có. Sau một `clean`, nếu `util-core` không có artifact đã install hoặc không được đưa vào reactor phù hợp, resume có thể gặp lỗi resolution.

Khi cần build module từ checkout sạch với các prerequisites, thường chọn:

```bash
mvn -pl :cli-tool -am clean package
```

thay vì chỉ trông chờ `-rf` giải quyết dependencies.

### 10.1. Chọn đúng kiểu selector trong `-rf`

Cũng như project identification, khi viết `:cli-tool` bạn nêu một artifactId; khi viết `apps/cli` bạn nêu project theo đường dẫn. Tuy nhiên semantics **resume build** vẫn khác **subset selection** của `-pl`.

### 10.2. Không thay `-rf` bằng `-pl` một cách máy móc

Nếu reactor trước đó đã build thành công core, fail ở CLI, bạn có thể muốn resume từ CLI để tiết kiệm thời gian. Nhưng nếu các upstream modules đã thay đổi source hoặc bị clean sau đó, bạn cần `-am` hoặc full build để bảo đảm artifact phù hợp. Hãy căn cứ trạng thái build thay vì “lệnh nào ngắn hơn”.

## 11. Chạy từ thư mục nào và vai trò của `-f`

Mọi lệnh mẫu quan trọng của bài được giả định **chạy trong `reactor-selector-demo/`**, nơi có root POM khai báo đủ ba modules.

### 11.1. Nếu đứng trong `apps/cli`

```bash
cd apps/cli
mvn clean package
```

Maven ở POM module CLI có thể xử lý **một project**, biết parent qua `<relativePath>`, nhưng **không vì thế tự thu thập các sibling modules** `shared/core` và `apps/web` vào reactor. Nếu core chưa được install/resolved, lệnh có thể thất bại.

Cách dễ kiểm chứng nhất là **đổi về root reactor** rồi chạy:

```bash
mvn -pl :cli-tool -am clean package
```

### 11.2. Dùng `-f` để chỉ POM gốc

Khi cần thực thi từ vị trí khác, Maven hỗ trợ:

```bash
mvn -f /path/to/reactor-selector-demo/pom.xml -pl :cli-tool -am clean package
```

Đường dẫn `/path/to/...` ở trên là **minh họa cấu trúc**, không phải command runnable nguyên văn trên mọi máy. Thay bằng đường dẫn thật của repository. `-f`/`--file` cho Maven biết POM bắt đầu từ đâu; `-pl :cli-tool` tiếp tục chọn project theo artifactId trong reactor do POM gốc ấy thu thập.

**Để tránh nhầm path resolution** khi dùng `-f` từ thư mục khác, selector theo G:A (`-pl org.example:cli-tool`) hoặc theo artifact ID (`-pl :cli-tool`) thường dễ đọc và đáng tin hơn việc suy đoán path tương đối theo current working directory.

Ví dụ khi đứng ở `apps/cli` (hai cấp sâu):

```bash
mvn -f ../../pom.xml -pl :cli-tool -am clean package
```

Cú pháp này dùng root parent POM và select theo artifactId, không yêu cầu biết cách Maven diễn giải một project-path selector từ working directory hiện tại.

### 11.3. `-N`/`--non-recursive` có tác dụng ngược mục tiêu `-pl`

Lệnh:

```bash
mvn -N validate
```

từ root chỉ xử lý **project hiện tại**, không duyệt child modules để build đầy đủ. Vì vậy:

```bash
mvn -N -pl :cli-tool package
```

có thể không tìm được CLI trong tập reactor đã thu thập vì `-N` không cho Maven recurse vào children như một invocation bình thường. **Không dùng `-N` để “build một module nhanh”** khi mục tiêu là chọn giữa các child modules bằng `-pl`.

## 12. Các bẫy về module identity

### 12.1. `<module>` là path, `<artifactId>` là artifact identity

Root POM:

```xml
<module>apps/cli</module>
```

Child POM:

```xml
<artifactId>cli-tool</artifactId>
```

**Không có ràng buộc Maven buộc hai chuỗi phải giống nhau.** Bạn có thể đổi thư mục mà không đổi GAV; cũng có thể đổi artifactId mà giữ thư mục. Đó chính là lý do `-pl apps/cli` và `-pl :cli-tool` khác nhau.

### 12.2. `<name>` trong POM không phải artifactId

POM có thể có:

```xml
<name>My Awesome Command Line Tool</name>
<artifactId>cli-tool</artifactId>
```

Khi đó:

```bash
mvn -pl ':My Awesome Command Line Tool' package
```

không phải cách chọn module này. `-pl :...` dùng **artifactId**, không phải display name `<name>` mà Maven log có thể in cho module.

### 12.3. GAV không phải filesystem path

`org.example:cli-tool:1.0.0` là Maven artifact coordinates, khác với `apps/cli`. Khi dùng `-pl`, dạng G:A:

```bash
mvn -pl org.example:cli-tool package
```

không phải một đường dẫn có dấu `:` theo phong cách Windows drive letter. Parser Maven nhận đó là project identity selector.

### 12.4. Tên giống nhau giữa nhiều nhóm

Trong một reactor đủ lớn, có thể hai child modules có artifactId `api` nhưng groupIds khác. Đừng trông chờ `-pl :api` luôn xác định đúng một module theo ý con người. Dùng G:A khi cần rõ ràng:

```bash
mvn -pl org.example.backend:api package
```

Đối với module được cấu hình từ profile, hãy bảo đảm project ấy có mặt trong **reactor hiện tại**; nêu G:A không tự kích hoạt profile chứa `<module>` bị tắt.

### 12.5. Khi selector không tìm được project

Một số nguyên nhân:

1. Viết tên artifactId nhưng quên dấu `:`.
2. Nhầm `apps/cli` với `apps/command-line` sau khi đổi layout.
3. Project không xuất hiện trong `<modules>` đã được Maven thu thập.
4. Profile có `<modules>` chỉ active ở môi trường khác.
5. Chạy `mvn` từ child POM, nên reactor không có siblings.
6. Dùng `-N`, khiến children không được thu thập.
7. ArtifactId thực tế khác tên display trong logs.
8. Chọn G:A nhưng groupId được kế thừa từ parent khác dự đoán.
9. Copy cú pháp Maven 4 **không tương thích Maven 3**.

Đọc lỗi Maven và `Reactor Build Order`, không tự sửa bằng cách rename module project khi chỉ cần sửa một project selector.

## 13. Maven 3 so với Maven 4: đừng lấy ví dụ trên web dùng sai CLI version

Bài này dùng **Maven 3.x**. Tài liệu Apache Maven hiện có cả guide riêng cho Maven 4, với một số quy tắc selector mở rộng.

Điểm nhất quán giữa hai dòng:

```text
-pl relative/path
-pl :artifactId
-pl groupId:artifactId
```

Trong Maven 4, project selection có thêm tính năng như **optional project selector** với prefix `?`, ví dụ:

```bash
mvn -pl '?:optional-module' package
```

Dấu `?` cho phép Maven 4 bỏ qua một selector không tìm được project trong một số tình huống. **Maven 3 không hỗ trợ prefix `?` cho `-pl`.** Nếu bạn đang dùng Maven 3 và copy nguyên ví dụ `-pl ?:module`, có thể gặp selector error.

Vì thế trước khi dùng cú pháp mới, luôn:

```bash
mvn -version
mvn --help
```

và xem **đúng guide cho major version** của Maven đang chạy. Không kết luận tùy chọn CLI thuộc Maven 4 là mặc định Maven 3.

## 14. CI/CD: chọn module nhanh nhưng không làm yếu tính đúng đắn

Một pipeline có nhiều modules thường chỉ cần build một vài module bị ảnh hưởng. `-pl` + `-am` hữu ích để rút ngắn reactor:

```bash
mvn -B -ntp -pl :cli-tool -am clean verify
```

Lệnh này làm hai việc có ý nghĩa:

- Chỉ chọn CLI làm mục tiêu.
- Build kèm upstream reactor dependencies (ví dụ `util-core`) để không dựa vào bản core cũ đã install trong máy CI.

**Không có nghĩa test suite đầy đủ của cả repository đã chạy**. Nếu thay đổi ở core có thể ảnh hưởng cả CLI và WebMain, bạn có thể dùng:

```bash
mvn -B -ntp -pl :util-core -amd clean verify
```

để chọn downstream consumers hoặc chạy full reactor verify theo policy.

### 14.1. Một matrix CI có thể dùng `-pl`

Ví dụ một job riêng cho CLI:

```bash
mvn -B -ntp -pl :cli-tool -am clean verify
```

Job riêng cho web:

```bash
mvn -B -ntp -pl :web-app -am clean verify
```

Nếu có dependency nội bộ lớn, hai jobs có thể build core riêng; điều này có thể chấp nhận để tách tests hoặc có thể tối ưu bằng cache/artifact sharing phù hợp. Nhưng **không đánh đổi correctness bằng cách dùng một core JAR cũ không khớp source**.

### 14.2. Test reports theo module

`verify` là Maven lifecycle phase, nhưng test execution có thể là **0 tests** trong ví dụ đơn giản này vì không khai báo JUnit tests. Đừng báo “unit tests PASS” chỉ vì `mvn verify` ra `BUILD SUCCESS`. Trong dự án thật, đảm bảo test frameworks, Surefire/Failsafe plugins, số tests và reports tương ứng.

### 14.3. Phạm vi của `-pl` khác `-DskipTests`

`-pl` chọn **modules/projects** để chạy lifecycle; `-DskipTests` là **tham số Surefire** ảnh hưởng execution của tests trong những modules được chọn. Hai thứ không thay nhau:

```bash
mvn -pl :cli-tool -am test
```

chọn reactor subset và chạy đến phase test.

```bash
mvn -pl :cli-tool -am test -DskipTests=true
```

vẫn chọn subset ấy, nhưng có thể skip chạy Surefire unit tests. Lệnh sau không phải quality gate nếu team cần tests được thực thi.

### 14.4. Quan hệ parent và plugin declarations

`-am` có thể bao gồm parent POM/related project cần thiết theo reactor relationships, nhưng điều đó **không đồng nghĩa Maven build mọi child module của parent**. Trong demo, CLI cần core, không cần WebMain. `-pl :cli-tool -am` nên giới hạn vào những projects cần thiết, không vô tình build web chỉ vì web ở cùng `<modules>`.

Nếu parent POM có plugin gây chạy tác vụ ngoài dự kiến trong `validate` hoặc `verify`, nó vẫn có thể tác động tới build khi parent được chọn. Đọc parent plugin/execution configuration thay vì cho rằng packaging `pom` luôn làm “không có gì”.

## 15. Troubleshooting: bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Could not find the selected project in the reactor: cli-tool` | Quên `:` nên `cli-tool` bị hiểu thành path | Dùng `-pl :cli-tool` hoặc `-pl apps/cli` |
| `Could not find ... :apps/cli` | Đặt `:` trước đường dẫn | Dùng `-pl apps/cli` |
| `Could not find ... :api` | artifactId không khớp hoặc module không ở reactor | Kiểm tra child POM GAV, `<modules>`, profiles |
| `-pl :cli-tool` không thấy `util-core` | Chỉ CLI được chọn, core JAR chưa resolve | Dùng `-am` |
| CLI build bằng code core cũ | Local repository đã có core JAR phiên bản cũ | Dùng `-am` để build core source hiện tại |
| `-pl apps/cli` hoạt động ở root nhưng thất bại ở thư mục khác | Khác POM/reactor starting point | Chạy từ root hoặc dùng `-f root/pom.xml` + `:artifactId` |
| `-pl :cli-tool` chọn nhầm module | Có nhiều GAV/artifactId gần giống hoặc trùng | Dùng `groupId:artifactId` |
| `-pl :cli-tool -amd` không build core | `-amd` chọn downstream, không upstream | Dùng `-am` |
| `-pl :util-core -am` không build web | Web phụ thuộc core, không phải core phụ thuộc web | Dùng `-amd` nếu muốn consumers |
| Lệnh `-pl` không chạy một child vừa thêm | Child chưa có trong root `<modules>` hoặc profile chưa active | Cập nhật collection/active profile đúng |
| Build theo đường dẫn nhưng không theo G:A | GroupId/artifactId hiệu lực khác suy đoán | Xem child và parent POM |
| `-P` không chọn module | `-P` là activate profiles | Dùng `-pl` |
| `-N -pl :cli-tool` không tìm child | `-N` ngăn recursive collection | Bỏ `-N` khi cần reactor |
| `-rf :cli-tool` fail vì core missing | Resume không tự build mọi upstream prerequisites | Dùng `-pl :cli-tool -am` từ checkout sạch |
| Dùng selector với `?` trên Maven 3 bị lỗi | Optional selector là tính năng Maven 4 | Bỏ `?` hoặc dùng Maven 4 nếu workflow cho phép |
| Package CLI thành công nhưng `java -jar` báo no main manifest | POM mẫu không có Main-Class | Dùng `java -cp ... Main` hoặc cấu hình Maven JAR Plugin manifest riêng |
| Có `BUILD SUCCESS` nhưng không thấy test reports | Demo không có tests hoặc test config bị skip | Kiểm tra source/test plugins, đừng suy ra test PASS |
| `mvn package` build quá nhiều modules | Không dùng `-pl` hoặc chọn sai scope | Chọn mục tiêu bằng `-pl`, dùng `-am` hợp lý |
| `mvn -pl :util-core -amd` làm CI tốn hơn | Chọn downstream consumers của core | Đây là mục tiêu của `-amd`; dùng `-am` nếu chỉ cần prerequisites |
| Module build nhưng không có artifact trong `~/.m2` | `package` không phải `install` | Dùng `-am` trong reactor hoặc `install` khi cần local repository |
| Chọn hai modules nhưng thiếu core | Quên `-am`, không có artifact resolvable | `-pl :cli-tool,:web-app -am` |
| Windows chạy Java classpath có dấu `:` lỗi | Dùng separator Unix trên Windows | Dùng `;` cho `java -cp`; Maven `-pl :...` không đổi |
| Reactor order khác thứ tự list `-pl` | Sort dựa dependency graph | Đọc Reactor Build Order |
| Maven 4 hướng dẫn khác Maven 3 | Major-version khác | Xem `mvn -version` và docs theo version |

## 16. Quy trình debug có thể lặp lại

Nếu `-pl` không chọn được module hoặc build thiếu dependency, từ root:

```bash
mvn -version
mvn -B -pl :cli-tool -am validate
mvn -B -pl apps/cli -am validate
mvn -B -pl org.example:cli-tool -am validate
mvn -B -pl :cli-tool -am clean package
```

Đọc logs để xác định **reactor project list** và build summary. `validate` ở đây có thể giúp xem selection mà không chạy compilation, nhưng một số project có plugin goals bind vào `validate`, nên không được coi nó là thao tác không gây side effects trong mọi repository.

Nếu muốn debug sâu:

```bash
mvn -X -pl :cli-tool -am clean package
```

Dùng `-X` khi cần plugin/project selection chi tiết. Log debug có thể chứa đường dẫn riêng máy, repository URLs hoặc thông tin nhạy cảm; xem trước khi chia sẻ công khai.

### 16.1. Xem POM hiệu lực theo module

Có thể chạy Maven Help Plugin cho CLI:

```bash
mvn -pl :cli-tool help:effective-pom -Doutput=cli-effective-pom.xml
```

Lệnh này **ghi file output** trong working context của project được chọn theo tham số Help Plugin; khi đọc lại, xác nhận đường dẫn file thực tế Maven đã ghi. Effective POM hiển thị GAV và cấu hình sau inheritance/profiles, giúp kiểm chứng artifactId/groupId thật.

Nhưng **`help:effective-pom` không thay thế việc xem reactor collection**: project không được collect thì không thể `-pl` chọn nó dù bạn biết đường dẫn của một POM ở nơi khác.

### 16.2. So sánh ba selector cùng một module

Dùng:

```bash
mvn -pl apps/cli -am validate
mvn -pl :cli-tool -am validate
mvn -pl org.example:cli-tool -am validate
```

**Kỳ vọng:** cả ba chọn cùng **tập project mục tiêu**, với in-reactor prerequisites được kéo vào qua `-am`. Trong thực tế logs có thể khác về thời gian/repositories, nhưng danh tính module CLI phải giống nhau.

### 16.3. Bằng chứng chất lượng cho việc lựa chọn

Đối với project demo, sau:

```bash
mvn -pl :cli-tool -am clean package
```

kiểm tra ít nhất:

```text
shared/core/target/util-core-1.0.0.jar
apps/cli/target/cli-tool-1.0.0.jar
```

`apps/web/target/web-app-1.0.0.jar` **không nên được xây mới chỉ vì lệnh này**. Nếu file web JAR có từ trước, đừng nhầm sự tồn tại của file **cũ** với việc reactor invocation hiện tại đã build web; đọc Maven reactor summary và timestamps. Nếu muốn chứng minh không build web, thử trong checkout sạch/workspace sạch.

## 17. Tự kiểm tra

**1.** `-pl apps/cli` có nghĩa gì?  
**Đáp án:** Chọn project theo **đường dẫn thư mục tương đối** trong reactor.

**2.** `-pl :cli-tool` có nghĩa gì?  
**Đáp án:** Chọn project có `<artifactId>cli-tool</artifactId>`.

**3.** `-pl cli-tool` có tra cứu artifactId không?  
**Đáp án:** Không. Tên trần được hiểu là đường dẫn; trong demo không có folder `cli-tool` dưới root.

**4.** Dùng selector nào nếu muốn chỉ rõ cả groupId?  
**Đáp án:** `-pl org.example:cli-tool`.

**5.** Vì sao `<module>apps/cli</module>` khác `<artifactId>cli-tool</artifactId>` mà Maven vẫn build?  
**Đáp án:** `<module>` là path để thu thập project; artifactId là tên Maven artifact được đọc từ child POM.

**6.** `-pl :cli-tool` có tự build `util-core` không?  
**Đáp án:** Không mặc định. Dùng `-am` để thêm upstream modules trong reactor.

**7.** Nếu dùng `-pl :cli-tool` và local repo có core JAR cũ, điều gì có thể xảy ra?  
**Đáp án:** CLI có thể build với code core cũ, vì build không nhất thiết chọn reactor project core.

**8.** `-am` so với `-amd` khác nhau thế nào?  
**Đáp án:** `-am` thêm upstream prerequisites; `-amd` thêm downstream dependents.

**9.** Muốn build core và cả hai consumers của demo, chọn gì?  
**Đáp án:** `mvn -pl :util-core -amd clean package`.

**10.** Vì sao `mvn -pl :cli-tool -amd package` không chắc sửa lỗi missing core?  
**Đáp án:** Vì `-amd` không thêm prerequisites mà CLI phụ thuộc; cần `-am`.

**11.** `-rf :cli-tool` có phải alias của `-pl :cli-tool` không?  
**Đáp án:** Không. `-rf` resume từ một project, còn `-pl` chọn project subset.

**12.** Khi đứng ở `apps/cli`, vì sao `mvn package` có thể không resolve `util-core`?  
**Đáp án:** Vì invocation chỉ thu thập project CLI; module core không tự tham gia reactor từ child directory.

**13.** `-pl` và `-P` khác nhau?  
**Đáp án:** `-pl` là projects; `-P` kích hoạt profiles.

**14.** Dùng `-N` khi cần `-pl` chọn child module có vấn đề gì?  
**Đáp án:** `-N` ngăn recursive reactor collection, có thể khiến child không nằm trong tập để chọn.

**15.** Maven 3 có hiểu optional selector prefix `?` của Maven 4 không?  
**Đáp án:** Không.

**16.** `mvn -pl :cli-tool -am package` có install util-core vào `~/.m2` không?  
**Đáp án:** `package` không tự làm phase `install`; không dựa vào việc core đã có trong local repo.

**17.** Tại sao `java -cp` trên Windows dùng `;` nhưng `-pl :cli-tool` vẫn có `:`?  
**Đáp án:** `;` là Java classpath separator trên Windows; `:` trong `-pl` là Maven artifactId selector syntax.

**18.** Một project không có trong `<modules>`/reactor collection có chọn được bằng `-pl` không?  
**Đáp án:** Không. `-pl` chỉ chọn các projects đã được reactor thu thập trong invocation hiện tại.

## 18. Checklist khi build một module Maven

- [ ] Đứng tại root reactor hoặc dùng `-f` trỏ chính xác tới root POM.
- [ ] Xác nhận child module nằm trong `<modules>` đang active.
- [ ] Phân biệt rõ thư mục (`apps/cli`) với artifactId (`cli-tool`).
- [ ] Với path selector, viết `-pl apps/cli`.
- [ ] Với artifactId selector, viết `-pl :cli-tool`.
- [ ] Nếu có trùng artifactIds giữa groups, ưu tiên `-pl groupId:artifactId`.
- [ ] Đừng dùng `-pl cli-tool` rồi tưởng Maven sẽ tự hiểu đó là artifact ID.
- [ ] Với dependency nội bộ chưa chắc có trong local repo, thêm `-am`.
- [ ] Khi sửa shared library và muốn kiểm tra consumers, cân nhắc `-amd`.
- [ ] Đừng nhầm `-rf` (resume) với `-pl` (select).
- [ ] Đừng nhầm `-P` (profiles) với `-pl` (projects).
- [ ] Không dùng `-N` khi mục tiêu là collect và chọn child modules.
- [ ] Kiểm tra đúng Java/Maven versions và syntax theo Maven major version.
- [ ] Nhớ Maven 3 không hỗ trợ `?` optional project selector.
- [ ] Sau build, đọc Reactor Build Order, không chỉ xem file JAR còn trên disk.
- [ ] Dùng `clean` khi cần loại artifact cũ trong QA.
- [ ] Kiểm tra `BUILD SUCCESS` không tự đồng nghĩa tests đã chạy.
- [ ] CI nên có chính sách rõ cho build selected modules và full integration test gates.
- [ ] Lệnh đầu tiên khi cần module CLI từ checkout sạch: `mvn -pl :cli-tool -am clean verify`.

## 19. Nguồn tham khảo chính thức

1. [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — Reactor, sorting, `-pl` selectors và `-am`/`-amd`.
2. [Apache Maven 3 — Maven CLI Options Reference](https://maven.apache.org/ref/3.9.11/maven-embedder/cli.html) — các tùy chọn `-pl`, `-am`, `-amd`, `-rf`, `-N`, `-P`.
3. [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — `<modules>`, `<parent>`, `<groupId>`, `<artifactId>`.
4. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — `compile`, `test`, `package`, `verify`, `install`.
5. [Apache Maven — Guide to Working with Multiple Subprojects in Maven 4](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html) — khác biệt major version, ví dụ optional `?` selector không có trên Maven 3.
6. [Sonatype — Maven: The Complete Reference, Advanced Reactor Options](https://www.sonatype.com/maven-complete-reference/running-maven) — các ví dụ project subset, also-make và resume.
7. [Apache Maven Compiler Plugin — Plugin Overview](https://maven.apache.org/plugins/maven-compiler-plugin/) — compile Java code.
8. [Apache Maven JAR Plugin — Plugin Overview](https://maven.apache.org/plugins/maven-jar-plugin/) — đóng gói JAR modules.

**Kết luận:** Đối với Maven 3, **selector không có dấu `:` được hiểu là path**, **`:artifactId` chọn theo Maven artifactId**, còn **`groupId:artifactId` chỉ rõ project identity**. Chọn module **không có nghĩa tự build dependency modules**; muốn build upstream prerequisites trong reactor hãy thêm **`-am`**, muốn build consumers phụ thuộc một module hãy cân nhắc **`-amd`**. Luôn chạy lệnh từ reactor root và xác minh **Reactor Build Order**.
