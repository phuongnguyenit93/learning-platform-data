# Aggregator POM, packaging=pom và khai báo modules trong Maven reactor

## 1. Vì sao dự án nhiều mô-đun cần một Aggregator POM?

Khi một sản phẩm Java được chia thành nhiều phần — thư viện dùng chung, xử lý nghiệp vụ, CLI, dịch vụ API hoặc adapter — việc đứng trong từng thư mục và chạy `mvn package` bằng tay rất dễ sai thứ tự, quên dependency hoặc tạo ra các phiên bản không nhất quán.

**Aggregator POM** là một Maven project dùng để **liệt kê các module sẽ được đưa vào cùng một lượt build**. Khi gọi Maven từ project aggregator, Maven **reactor** thu thập các module, xác định thứ tự phù hợp dựa trên quan hệ phụ thuộc, rồi thực hiện các goal/phase trên những project được chọn.

Ví dụ một repository có:

```text
reactor-demo/
├── pom.xml                <- aggregator
├── shared-core/
│   └── pom.xml            <- thư viện
└── cli-app/
    └── pom.xml            <- ứng dụng dùng shared-core
```

Trong root `pom.xml`:

```xml
<packaging>pom</packaging>
<modules>
    <module>shared-core</module>
    <module>cli-app</module>
</modules>
```

Sau đó chạy từ thư mục `reactor-demo`:

```bash
mvn clean package
```

Maven có thể build **root POM, shared-core, rồi cli-app** trong một reactor. Nếu `cli-app` khai báo dependency thật tới `shared-core`, reactor sẽ sắp xếp để thư viện sẵn sàng trước khi compile ứng dụng.

**Ba khái niệm cần tách ngay:**
- **Aggregator**: tổ chức **những project nào được build cùng nhau**, bằng `<modules>`.
- **Parent POM**: cung cấp **cấu hình được kế thừa**, bằng `<parent>` ở POM con.
- **Reactor**: cơ chế Maven thu thập project, sắp xếp và thực thi build.

Aggregator và parent thường là **cùng một POM trong dự án thực tế**, nhưng **không phải là một khái niệm** và không tự động tương đương nhau.

## 2. Vai trò của `<packaging>pom</packaging>`

Maven POM là mô tả project: `groupId`, `artifactId`, `version`, packaging, build plugins, dependencies và cấu hình. Nếu **không khai báo packaging**, Maven thường mặc định `jar`.

Một aggregator thông dụng phải đặt:

```xml
<packaging>pom</packaging>
```

Ý nghĩa:
1. Đây là project loại **POM**, thường làm **aggregator/parent**, không phải một module mã nguồn Java cần tạo JAR sản phẩm.
2. Với packaging `pom`, một lượt `mvn package` **không tự tạo `root/target/root.jar`** từ tất cả modules.
3. Nếu gọi `mvn install`, Maven có thể install **POM artifact của root** vào local repository, đồng thời xử lý các modules trong reactor.
4. `pom` packaging vẫn là một **Maven project hợp lệ**, có thể có properties, pluginManagement, dependencyManagement, reporting hoặc một số plugin executions được cấu hình riêng.
5. Nó không khiến dependencies giữa modules xuất hiện tự động. Tên modules chỉ mô tả **tham gia reactor**, không phải quan hệ compile/runtime.

Một lỗi thường gặp:

```xml
<project>
    ...
    <modules>
        <module>shared-core</module>
    </modules>
</project>
```

Đây là **minh họa thiếu cấu hình**, không phải POM để copy. Vì không đặt `<packaging>pom</packaging>`, Maven sẽ áp dụng default `jar`, khiến việc aggregation bị từ chối hoặc báo lỗi liên quan packaging khi load project. Hãy khai báo rõ `pom` cho aggregator.

**Phân biệt với `<packaging>jar</packaging>` ở module con**: một module thư viện/ứng dụng Java vẫn có thể build JAR bình thường dù POM root dùng `pom`. Mỗi module có **packaging riêng** và **thư mục `target` riêng**.

## 3. `<modules>` và `<module>` chỉ tới đâu?

`<modules>` là danh sách **đường dẫn tương đối từ thư mục chứa POM aggregator** tới các subproject.

Ví dụ:

```xml
<modules>
    <module>shared-core</module>
    <module>cli-app</module>
</modules>
```

Với file aggregator ở `reactor-demo/pom.xml`, Maven tìm:

```text
reactor-demo/shared-core/pom.xml
reactor-demo/cli-app/pom.xml
```

**Giá trị `<module>` không phải Maven GAV coordinates** và không có nghĩa là `groupId:artifactId`. Theo tài liệu Maven, module path có thể trỏ tới thư mục project hoặc trực tiếp một POM file. Cách dễ hiểu, dễ bảo trì nhất là **mỗi module một folder** và dùng path của folder.

Các ví dụ đường dẫn có thể hợp lệ tùy layout:

```xml
<modules>
    <module>libraries/core</module>
    <module>apps/cli</module>
    <module>../shared-tools</module>
</modules>
```

Đây là **cấu hình minh họa cho một layout khác**, không nằm trong POM hoàn chỉnh của bài. Nếu module dùng `../`, phải đảm bảo đường dẫn thực sự tồn tại, không đi lạc khỏi những project chủ đích và phù hợp chính sách repository.

### Tên folder và artifactId có bắt buộc giống nhau?

Không. Ví dụ:

```text
reactor-demo/
└── common-utils/
    └── pom.xml
```

POM `common-utils/pom.xml` có thể khai báo `<artifactId>shared-core</artifactId>`; aggregator vẫn dùng `<module>common-utils</module>` vì `common-utils` là **folder path**.

Dù vậy, khi tên thư mục bằng artifactId, cấu trúc sẽ dễ tìm và dễ dùng các lệnh như `-pl :shared-core`. Đây là convention, **không phải một ràng buộc cú pháp của Maven**.

### Lỗi đường dẫn

- Sai: `<module>com.example:shared-core:1.0.0</module>` nếu đó không phải tên path thực.
- Sai: `<module>src/main/java</module>` vì đó thường là source directory chứ không có project POM.
- Sai: liệt kê folder không chứa POM hợp lệ.
- Đúng: đường dẫn tới project module mà Maven có thể load POM của nó.

Nếu Maven báo **Child module ... does not exist**, hãy kiểm tra chính xác vị trí và chữ hoa/thường của đường dẫn, POM module và vị trí POM aggregator đang chạy.

## 4. Aggregation không phải inheritance: một bảng so sánh

| Điểm so sánh | Aggregation | Inheritance |
| --- | --- | --- |
| Khai báo ở đâu? | Aggregator POM có `<modules>` | Child POM có `<parent>` |
| Quan hệ chỉ hướng nào? | Aggregator chỉ đến các module | Child chỉ đến parent |
| Mục đích chính | Gom project trong **một reactor build** | Chia sẻ và kế thừa **POM model/configuration** |
| Có tự tạo dependency giữa module không? | Không | Không |
| Có tự làm child kế thừa `groupId`, `version`, properties? | Không | Có thể, theo quy tắc inheritance |
| Chạy `mvn package` ở root có chạy children không? | Có, với reactor mặc định và modules hợp lệ | Không, nếu root chỉ là parent và không khai báo modules |
| Cần packaging POM của root? | Có theo mô hình aggregator Maven | Parent thông thường cũng dùng `pom` |
| Có thể tồn tại độc lập? | Có | Có |

**Ví dụ aggregator nhưng không là parent:** Root POM chỉ liệt kê các module. Những POM con có thể tự khai báo GAV và kế thừa một parent khác (hoặc không kế thừa parent riêng). Root tổ chức build, không ép children nhận properties của root.

**Ví dụ parent nhưng không aggregator:** Một POM `engineering-parent` định nghĩa `maven.compiler.release`, versions plugins và dependencyManagement; các dự án khác khai báo `<parent>` trỏ tới nó. Parent **không khai báo `<modules>`**. Chạy Maven tại folder của parent không có nghĩa các project con ở repository khác tự được build.

**Ví dụ cả hai:** Root POM vừa có `<modules>` vừa là `<parent>` trong POM của các module. Đây là mẫu dễ học và sẽ dùng xuyên suốt bài.

## 5. Mô hình thực hành Java 17: hai module và một POM root

Ta xây một project Java 17 **có thể compile, test và chạy**:

```text
reactor-demo/
├── pom.xml
├── shared-core/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   └── java/com/example/reactor/core/GreetingFormatter.java
│       └── test/
│           └── java/com/example/reactor/core/GreetingFormatterTest.java
└── cli-app/
    ├── pom.xml
    └── src/
        └── main/
            └── java/com/example/reactor/app/Main.java
```

**Thiết kế:**
- Root `reactor-demo`: aggregator **và** parent, packaging `pom`.
- `shared-core`: module JAR chứa public API `GreetingFormatter`, có unit tests JUnit 5.
- `cli-app`: module JAR phụ thuộc `shared-core` ở compile scope; chứa class `Main` in kết quả từ library.

**Mục tiêu kiểm chứng:** `mvn clean verify` từ root build cả hai; reactor sắp xếp shared-core trước cli-app; Java command chạy cả hai output classes; không phải `mvn install` từng module trước.

### 5.1. reactor-demo/pom.xml — POM root hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.reactor</groupId>
    <artifactId>reactor-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-core</module>
        <module>cli-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
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
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
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

Giải thích:
- `modelVersion=4.0.0`: model Maven POM thường dùng.
- `groupId`, `artifactId`, `version`: tọa độ **của root project**.
- `packaging=pom`: không yêu cầu root sinh JAR ứng dụng.
- `<modules>`: các đường dẫn relative tới child project folders.
- `<properties>`: **được child kế thừa** khi các child chỉ về root qua `<parent>`.
- `<pluginManagement>`: tập trung version/compiler/surefire/jar plugin, giúp các module dùng cùng cấu hình khi plugin được áp dụng. Nó không tự khiến Maven tải và thực thi một plugin ngoài lifecycle bindings.
- Root **không khai báo `<dependency>` từ cli-app tới shared-core**: dependency đó thuộc POM của **cli-app**.

Lưu ý: phiên bản plugin được ghim để ví dụ tái lập. Cần **Maven 3.6.3+ tương thích các plugins và JDK 17+**, truy cập repository hoặc có cache Maven trước đó.

### 5.2. shared-core/pom.xml — POM module thư viện

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.reactor</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Đây là **POM hoàn chỉnh** của module. Nó không cần lặp `groupId` và `version` ở project level vì Maven có thể kế thừa từ `<parent>`.

**`<relativePath>../pom.xml</relativePath>` ở đâu?** Đây là đường dẫn **từ `shared-core/pom.xml` tới POM cha**. Maven thường mặc định kiểm tra `../pom.xml` nếu không khai báo; ở đây viết tường minh để người học thấy sự khác nhau với `<module>shared-core</module>` ở root.

- `<module>` ở **aggregator**: trỏ **xuống** project con.
- `<parent><relativePath>` ở **child**: trỏ **lên** POM cha cho inheritance/local parent resolution.

Hai đường dẫn phục vụ hai quan hệ khác nhau.

Dependency JUnit 5 được dùng **chỉ trong test scope**. `junit.jupiter.version` là property thừa hưởng từ parent. Maven Surefire được packaging `jar` bind vào phase `test`; pluginManagement của parent chọn phiên bản phù hợp.

### 5.3. cli-app/pom.xml — POM module ứng dụng

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.reactor</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>cli-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.reactor</groupId>
            <artifactId>shared-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

**Đây là dòng quyết định thứ tự build:** `cli-app` **khai báo dependency trực tiếp** tới `shared-core` theo GAV thật. Reactor thấy dependency này khi cả hai project nằm trong cùng reactor và sắp xếp `shared-core` trước `cli-app`.

**Chỉ liệt kê hai module trong `<modules>` là chưa đủ** để Java code trong `cli-app` import class từ `shared-core`. Phải có `<dependency>` trong module tiêu thụ, hoặc một cơ chế classpath khác phù hợp. `dependencyManagement` cũng chỉ quản lý version/scope mặc định khi dependency được khai báo, **không tự thêm dependency vào classpath**.

POM này **không cấu hình `Main-Class`**. Nó sẽ tạo JAR đơn giản; muốn chạy chương trình, ta dùng `java -cp` với các compiled classes/JAR. Aggregator **không tự đóng thành một fat executable JAR**.

### 5.4. shared-core/src/main/java/com/example/reactor/core/GreetingFormatter.java

```java
package com.example.reactor.core;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, friend!";
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

Mã dùng `String.isBlank()` và `String.strip()`, có trong Java 11+, chạy trên Java 17. Không có I/O hoặc dependency bên ngoài cho production class.

- `greet(" Maven ")` -> `Hello, Maven!`.
- `greet(" ")` -> `Hello, friend!`.
- `greet(null)` -> `Hello, friend!`.

Vì class ở package `com.example.reactor.core`, path nguồn phải là `shared-core/src/main/java/com/example/reactor/core/GreetingFormatter.java`, không đặt nhầm trong package của `cli-app`.

### 5.5. shared-core/src/test/java/com/example/reactor/core/GreetingFormatterTest.java

```java
package com.example.reactor.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {

    @Test
    void greetsTrimmedName() {
        assertEquals("Hello, Maven!", GreetingFormatter.greet(" Maven "));
    }

    @Test
    void greetsBlankNameWithFallback() {
        assertEquals("Hello, friend!", GreetingFormatter.greet("  "));
    }
}
```

Đây là JUnit Jupiter test với **2 test methods**, lớp tên kết thúc bằng `Test` phù hợp default discovery của Maven Surefire. Dependency `junit-jupiter` nằm trong POM của `shared-core` với `scope=test`.

Trong một lượt `mvn test` hoặc phase sau, nếu hai assertions đều đúng, report Surefire của module này cần có **2 tests, 0 failures, 0 errors**.

Đường dẫn report thường là:

```text
shared-core/target/surefire-reports/TEST-com.example.reactor.core.GreetingFormatterTest.xml
```

Việc aggregator đưa module này vào reactor **không thay thế JUnit engine hoặc Surefire**. Maven cần source, test dependency và test plugin hoạt động như một module Java bình thường.

### 5.6. cli-app/src/main/java/com/example/reactor/app/Main.java

```java
package com.example.reactor.app;

import com.example.reactor.core.GreetingFormatter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(GreetingFormatter.greet(" Maven "));
        System.out.println("Module: cli-app");
    }
}
```

Mã `cli-app` import `GreetingFormatter` từ **module khác**. Nếu POM app không khai báo dependency đến `shared-core`, Maven Compiler Plugin có thể báo `package com.example.reactor.core does not exist`. Điều này chứng minh aggregation **không thay dependency declaration**.

**Stdout chính xác** khi classpath đầy đủ:

```text
Hello, Maven!
Module: cli-app
```

## 6. Chạy build reactor từ thư mục root

Đảm bảo ba `pom.xml`, các file `.java` và thư mục đúng theo sơ đồ. Tại `reactor-demo`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Với Maven 3 tương thích và JDK 17+, Maven:
1. Đọc root aggregator có packaging `pom`.
2. Thu thập `shared-core` và `cli-app` từ `<modules>`.
3. Thấy app phụ thuộc library và sắp xếp module hợp lệ.
4. Thực hiện các phase thích hợp trên root, library, app.
5. Biên dịch `GreetingFormatter`, chạy 2 unit tests trong shared-core.
6. Biên dịch `Main` với dependency `shared-core` từ reactor.
7. Tạo mỗi JAR riêng ở phase `package`.

Đầu ra chính:

```text
shared-core/target/shared-core-1.0.0.jar
cli-app/target/cli-app-1.0.0.jar
shared-core/target/surefire-reports/TEST-com.example.reactor.core.GreetingFormatterTest.xml
```

Có thể còn metadata, report và các thư mục `classes`, `test-classes`, `generated-sources`. **Không mong chờ** `reactor-demo/target/reactor-demo.jar`: root là packaging `pom`.

### 6.1. Ví dụ Reactor Build Order

Log Maven thường có phần gần như:

```text
Reactor Build Order:
reactor-demo
shared-core
cli-app
```

Đây là **minh họa lược bớt**; Maven thật có thể in tên dự án/tọa độ và các dòng khác. Thứ tự module có thể bị ràng buộc bởi parent và dependencies; không nên coi `<modules>` là một danh sách job buộc chạy đúng thứ tự thủ công.

Trong ví dụ này, app phụ thuộc core; do đó core phải sẵn sàng trước khi app compile.

### 6.2. Kiểm tra JAR từng module

```bash
jar tf shared-core/target/shared-core-1.0.0.jar
jar tf cli-app/target/cli-app-1.0.0.jar
```

Trong JAR core có `com/example/reactor/core/GreetingFormatter.class`; trong JAR app có `com/example/reactor/app/Main.class`. **Không** mặc nhiên có `GreetingFormatter.class` trong JAR app, vì plain JAR Plugin không gộp dependency classes.

### 6.3. Chạy ứng dụng Java bằng classpath

**Linux/macOS** tại root:

```bash
java -cp "cli-app/target/classes:shared-core/target/classes" com.example.reactor.app.Main
```

**Windows PowerShell hoặc Command Prompt** tại root:

```powershell
java -cp "cli-app/target/classes;shared-core/target/classes" com.example.reactor.app.Main
```

Ở cả hai môi trường, khi build thành công và classpath đúng:

```text
Hello, Maven!
Module: cli-app
```

Dấu `:` và `;` là **bộ phân tách entries trên classpath theo hệ điều hành**, không phải cú pháp module trong POM.

**Chú ý:** Đừng dùng `java -jar cli-app/target/cli-app-1.0.0.jar` rồi nghĩ Maven reactor đã gộp library vào app. POM ví dụ chưa viết `Main-Class` và không làm fat JAR. Nếu muốn executable distribution, đó là bài riêng về Maven JAR Plugin, manifest Class-Path, Shade/Assembly hoặc launcher.

### 6.4. Chạy bằng hai JAR outputs

Sau package, cũng có thể dùng JAR classpath.

Linux/macOS:

```bash
java -cp "cli-app/target/cli-app-1.0.0.jar:shared-core/target/shared-core-1.0.0.jar" com.example.reactor.app.Main
```

Windows:

```powershell
java -cp "cli-app/target/cli-app-1.0.0.jar;shared-core/target/shared-core-1.0.0.jar" com.example.reactor.app.Main
```

Ví dụ không có external **production** dependency ngoài thư viện core, nên hai JAR này đủ cho chương trình. Nếu core có production dependency bên thứ ba, classpath cần cả những JAR runtime đó.

## 7. Maven reactor sắp xếp modules dựa trên điều gì?

Maven reactor không chạy module theo thứ tự khai báo đơn thuần. Theo hướng dẫn chính thức, reactor:
1. Thu thập những module có trong lượt build.
2. Phân tích quan hệ giữa project trong reactor.
3. Sắp xếp theo các quan hệ phải đi trước.
4. Thực thi goal/phase trên các project được chọn.

Những quan hệ **thực sự có hiệu lực với reactor sorting** gồm:
- Project A có **dependency thực tế** đến một project B cũng thuộc reactor.
- Project dùng một **build plugin** là module nằm trong reactor.
- Project dùng **plugin dependency** là module trong reactor.
- Project dùng **build extension** là module trong reactor.
- Một project có **parent** cũng nằm trong reactor.
- Khi không có những ràng buộc trên, thứ tự `<modules>` có thể đóng vai trò tie-breaker.

**Điểm dễ nhầm:** Khai báo version trong `<dependencyManagement>` hoặc `<pluginManagement>` **không tạo quan hệ sorting**; đó là cấu hình quản lý, không phải một instantiated dependency/plugin. Phải có dependency/plugin thực sự được áp dụng.

### 7.1. Thử đảo thứ tự khai báo

Trong root POM, bạn có thể **trên một bản sao thực hành** đảo thành:

```xml
<modules>
    <module>cli-app</module>
    <module>shared-core</module>
</modules>
```

Vẫn có dependency `cli-app -> shared-core`. Reactor sẽ sắp xếp core trước app theo dependency, dù app xuất hiện đầu tiên trong XML. Khi không có quan hệ bắt buộc, thứ tự modules có thể ảnh hưởng thứ tự project độc lập.

**Không nên cố dùng `<modules>` như một giải pháp cho dependency chưa khai báo**. Nếu app import core, hãy khai báo `<dependency>` trong app POM; đó là quan hệ compile cần thiết.

### 7.2. Chỉ nằm chung reactor có tự dùng class của nhau không?

Không. Đây là một bẫy lớn khi học Maven:

```text
Aggregator có module A và module B
          !=
B tự động thấy toàn bộ classes của A
```

Chỉ khi B khai báo dependency thích hợp tới A thì Maven có thể đưa A vào classpath của B. Aggregator giúp build nhiều project đúng thứ tự; nó không biến nhiều module thành **một project với một classpath chung**.

### 7.3. Dependency vòng tròn

Nếu `shared-core` phụ thuộc `cli-app`, đồng thời `cli-app` phụ thuộc `shared-core`, reactor có thể báo **cyclic dependency** vì không có thứ tự build hợp lệ.

Cách sửa là thiết kế ranh giới:
- Core chứa interface/value objects dùng chung, không phụ thuộc application.
- Application phụ thuộc core.
- Nếu hai module cần một kiểu dữ liệu chung, chuyển nó sang module thứ ba thấp hơn trong graph thay vì tạo vòng lặp.

Không thể khắc phục dependency cycle đơn thuần bằng đảo `<module>` lines.

## 8. Chọn một module hoặc một nhánh reactor bằng CLI

Trong repository lớn, không phải lúc nào cũng muốn build tất cả module. Maven 3 có các lựa chọn quan trọng:

| Tùy chọn | Ý nghĩa thông dụng |
| --- | --- |
| `-pl` / `--projects` | Chỉ chọn những project cụ thể trong reactor |
| `-am` / `--also-make` | Xây cả những project reactor mà project được chọn **phụ thuộc vào** |
| `-amd` / `--also-make-dependents` | Xây các project reactor **phụ thuộc vào** project được chọn |
| `-N` / `--non-recursive` | Chỉ xử lý project hiện tại, không thu thập modules để build đệ quy |
| `-rf` / `--resume-from` | Tiếp tục build từ project đã chỉ định trong một reactor phù hợp |
| `-fae` / `--fail-at-end` | Khi module thất bại, cố gắng build các module không bị chặn, báo lỗi ở cuối |
| `-ff` / `--fail-fast` | Thất bại module thì dừng sớm (default behavior) |

### 8.1. Chọn ứng dụng theo artifactId

Tại root:

```bash
mvn -B -ntp -pl :cli-app -am package
```

- `-pl :cli-app`: chọn Maven project có artifactId `cli-app`.
- `-am`: đưa cả **module dependencies cần thiết trong reactor** vào cùng build.
- Với demo, `shared-core` là dependency của app; Maven có thể build library rồi app trong cùng reactor.

Dạng path:

```bash
mvn -B -ntp -pl cli-app -am package
```

Ở đây `cli-app` **không có dấu hai chấm**, được Maven hiểu theo path thư mục tương đối. Dạng `:cli-app` dựa trên artifactId, thường hữu ích nếu tên folder và artifactId khác nhau.

**Chú ý:** `-pl :cli-app` một mình không có nghĩa tự động build tất cả dependencies chưa có artifact ở local repository. Khi muốn chắc chắn lấy module dependencies từ checkout hiện tại, thêm `-am` hoặc build toàn reactor từ root.

### 8.2. Build core và dependents

```bash
mvn -B -ntp -pl :shared-core -amd test
```

Maven chọn `shared-core` và những project reactor phụ thuộc vào nó, ở demo là `cli-app`. Đây có thể hữu ích khi sửa API core và muốn test những consumers trong cùng repository.

`-amd` **không phải** tính năng chạy reverse dependencies từ mọi project Maven trên Internet; nó giới hạn ở **reactor được thu thập** trong lượt build.

### 8.3. Chỉ xử lý root aggregator POM

```bash
mvn -B -ntp -N validate
```

`-N` ngăn recursive multi-module build; lệnh trên chỉ chạy `validate` cho root project. Nó không compile/test `shared-core` hoặc `cli-app`.

Vì root có packaging `pom`, chạy `-N package` cũng không có nghĩa tạo một JAR chứa toàn bộ modules.

### 8.4. Chạy Maven từ directory khác bằng -f

```bash
mvn -f reactor-demo/pom.xml clean package
```

Lệnh minh họa cho trường hợp **working directory là folder chứa `reactor-demo`**, không phải từ trong root. `-f` chọn POM aggregator; module paths được resolve theo **vị trí POM**, không phải theo tên artifactId.

### 8.5. Sau khi build lỗi: -rf và giới hạn

Ví dụ Maven in failure ở `cli-app`:

```bash
mvn -B -ntp -rf :cli-app package
```

`-rf` nghĩa là resume reactor từ một project. Nó **không tự chữa** lỗi và không tự bảo đảm mọi prerequisite module artifact sẵn có nếu module trước chưa package/install đầy đủ. Trong CI sạch, khi thiếu dependency có thể cần chạy lại với selection/`-am` phù hợp hoặc chạy toàn reactor.

**Không dùng `-fn` (fail-never) để che lỗi CI.** Nếu bắt buộc một module phải xanh, cần xem exit code, log và Reactor Summary; `-fn` có thể khiến exit code bằng 0 dù có module build fail.

## 9. `<parent>` và `<relativePath>`: inheritance hoạt động riêng

Trong POM con:

```xml
<parent>
    <groupId>com.example.reactor</groupId>
    <artifactId>reactor-demo</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

`<parent>` chọn Maven model kế thừa, được định danh bằng **GAV của parent POM**. `<relativePath>` chỉ một file POM local giúp Maven tìm parent trong checkout, không thay thế điều kiện khớp coordinates.

Các trường hợp:
- **Cấu trúc sibling dưới root**: `../pom.xml` thường là mặc định thích hợp.
- **Parent ở `../build-parent/pom.xml`**: phải đặt `<relativePath>` tương ứng nếu muốn Maven đọc parent trong filesystem.
- **Parent chỉ có trên repository**: có thể đặt `<relativePath/>` để không thử tìm parent local mặc định.
- **POM ở relativePath có GAV không khớp**: Maven có thể báo lỗi parent resolution hoặc tiếp tục tìm repository theo cơ chế phiên bản; không nên “chữa” bằng đổi GAV cho khớp tùy tiện.

**Quan trọng:** `<parent>` không yêu cầu project parent phải liệt kê child trong `<modules>`. Kế thừa model có thể hoạt động ngay khi parent POM được resolve, dù root parent không đóng vai trò aggregator.

### Kế thừa groupId và version

Trong hai POM child ở demo, **không viết** project-level `<groupId>` và `<version>`. Maven có thể kế thừa từ root parent:

```text
com.example.reactor:shared-core:1.0.0
com.example.reactor:cli-app:1.0.0
```

Lưu ý groupId/version được kế thừa ở child **không có nghĩa** `cli-app` đã có dependency tới `shared-core`. Dependency cần được khai báo riêng.

### Xem Effective POM

Tại root:

```bash
mvn -pl :cli-app help:effective-pom -Doutput=effective-cli.xml
```

Help Plugin có thể in effective POM sau inheritance và plugin management. Tuy nhiên cú pháp/đường dẫn output khi chạy từ root với `-pl` cần chú ý project basedir; hãy kiểm tra file sinh ra ở module hoặc dùng:

```bash
mvn -f cli-app/pom.xml help:effective-pom -Doutput=effective-cli.xml
```

Lệnh thứ hai chạy ở root với `-f` trỏ POM child; tùy các lựa chọn Maven/goal, output thường được resolve theo basedir của module hoặc theo tham số output. Dùng nó để xác minh **groupId, version, compiler release, dependencies thực tế** chứ không giả định mọi project tự nhận cùng một classpath.

## 10. dependencyManagement và pluginManagement trong aggregator/parent

Root POM hay đóng hai vai trò: aggregator + parent. Đây là vị trí hợp lý để quản lý nhất quán versions mà không ép tất cả module dùng cùng một dependency.

### 10.1. Quản lý dependency version không tự thêm dependency

Root parent có thể khai báo:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.reactor</groupId>
            <artifactId>shared-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu child kế thừa parent, trong `cli-app/pom.xml` có thể viết dependency đến `shared-core` mà không lặp version:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.reactor</groupId>
        <artifactId>shared-core</artifactId>
    </dependency>
</dependencies>
```

Hai đoạn này là **biến thể minh họa**, không cần thêm vào POM đầy đủ ở mục 5. Chúng sẽ tạo dependency khi **child khai báo `<dependency>`**.

Chỉ có `dependencyManagement` ở parent thì `cli-app` **không** tự dùng `shared-core` và reactor **không** dùng managed-only relationship để sắp xếp modules.

### 10.2. Plugin management không luôn thực thi plugin

Root ví dụ khai báo:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
        </plugin>
    </plugins>
</pluginManagement>
```

Mục đích là quản lý plugin version/configuration. **Một plugin chỉ ở `<pluginManagement>` không tương đương với việc bind một execution mới vào lifecycle mọi module**. Các goals đã được packaging mặc định bind như `compiler:compile` trong `jar` packaging vẫn được thực thi; pluginManagement có thể cung cấp version/cấu hình cho chúng.

Nếu cần plugin riêng như code generator hoặc một goal chạy ở `generate-sources`, module hoặc parent phải có execution được áp dụng hợp lệ. Không nên nghĩ root aggregator sẽ tự chạy một plugin chỉ vì plugin ấy có version trong pluginManagement.

## 11. Aggregator nhiều tầng và layout phức tạp

Một repo lớn có thể dùng aggregator lồng nhau:

```text
platform/
├── pom.xml
├── libraries/
│   ├── pom.xml
│   ├── common/
│   │   └── pom.xml
│   └── validation/
│       └── pom.xml
└── apps/
    ├── pom.xml
    └── cli/
        └── pom.xml
```

Root `platform/pom.xml` có thể liệt kê:

```xml
<modules>
    <module>libraries</module>
    <module>apps</module>
</modules>
```

`libraries/pom.xml` có thể tự là aggregator:

```xml
<packaging>pom</packaging>
<modules>
    <module>common</module>
    <module>validation</module>
</modules>
```

Các POM này **chỉ là fragments minh họa**; cần đủ GAV và `<project>` để chạy thực. Reactor sẽ thu thập modules theo cấu trúc thích hợp.

**Phân biệt ba loại quan hệ trong layout trên:**
- Folder hierarchy: `libraries/common`.
- Aggregation: `platform` khai báo `libraries`, `libraries` khai báo `common`.
- Inheritance: `common/pom.xml` có thể chọn `platform` hoặc một parent POM riêng trong `<parent>`.

Không nhất thiết parent POM phải nằm ngay cùng cấp hoặc trùng aggregator trực tiếp. Khi cấu trúc khác default, thiết kế `<relativePath>` cẩn thận.

### Thêm module mới an toàn

Giả sử thêm `apps/reporting`:
1. Tạo `apps/reporting/pom.xml` hợp lệ (thường packaging jar).
2. Thêm `<module>reporting</module>` vào `apps/pom.xml` nếu `apps` là aggregator trực tiếp.
3. Khai báo `<parent>` nếu muốn kế thừa, với GAV/relativePath đúng.
4. Thêm `<dependency>` đến các module khác nếu source thực sự dùng.
5. Chạy `mvn validate` từ aggregator liên quan để xác nhận đường dẫn và POM parse.
6. Chạy `mvn clean verify`/selection phù hợp để kiểm tra reactor sort và output.

**Không thêm module vào một danh sách `<modules>` mà quên tạo POM child**, và không thêm dependencies giả chỉ để ép thứ tự build.

## 12. Khi module không thuộc reactor thì sao?

Một Maven dependency có thể là:
- Module khác đã được **thu thập trong reactor hiện tại**;
- Artifact đã có trong **local repository**;
- Artifact tải từ **remote repository**.

Reactor chỉ có thể sort/build những project nó thu thập. Nếu `cli-app` khai báo dependency `shared-core` nhưng chạy **chỉ** trong folder `cli-app` trên một máy sạch, Maven có thể không thấy `shared-core` trong reactor và cố resolve artifact từ repository.

Lệnh sau là **cách an toàn nhất cho demo từ root**:

```bash
mvn -B -ntp clean verify
```

Hoặc chọn app cùng prerequisites:

```bash
mvn -B -ntp -pl :cli-app -am clean package
```

Nếu một IDE mở root aggregator nhưng terminal đang ở `cli-app`, lệnh `mvn package` ở terminal **không tương đương** lệnh toàn reactor ở root. Kiểm tra working directory hoặc dùng `-f` rõ.

### Tại sao `mvn install` không phải điều kiện bắt buộc trong reactor?

Khi hai modules nằm cùng reactor và dependency được khai báo, Maven có thể đưa artifact của module dependency vào quá trình build module consumer mà **không yêu cầu cài nó vào local repository trước**. `install` chủ yếu phục vụ việc lưu artifacts để các lượt build/project **ngoài reactor hiện tại** resolve được.

Đừng dùng `mvn install` như bước chữa mọi lỗi phụ thuộc module nếu nguyên nhân thực là POM sai GAV, thiếu `<dependency>` hoặc module không được thu thập.

## 13. Kiểm tra cấu hình bằng lệnh Maven

### 13.1. Kiểm tra reactor và POM nhanh

```bash
mvn -version
mvn -B -ntp validate
```

`validate` giúp phát hiện nhiều lỗi POM/module path trước khi compile Java. Không kết luận “mã nguồn compile đúng” chỉ vì validate thành công.

### 13.2. Test toàn bộ modules

```bash
mvn -B -ntp clean test
```

`shared-core` cần chạy hai test methods; `cli-app` không có test nguồn nên Surefire có thể báo không có test để chạy (đây không mặc nhiên là lỗi trong demo).

### 13.3. Package toàn bộ modules

```bash
mvn -B -ntp clean package
```

Tìm hai JAR trong `shared-core/target` và `cli-app/target`. **Root `packaging=pom` không tự tạo third combined JAR.**

### 13.4. Chọn module cần thiết

```bash
mvn -B -ntp -pl :cli-app -am verify
```

Với demo, core được build cùng app vì app phụ thuộc core. Nếu bạn muốn chỉ build core:

```bash
mvn -B -ntp -pl :shared-core test
```

### 13.5. Xem effective model

```bash
mvn -f shared-core/pom.xml help:effective-pom
mvn -f cli-app/pom.xml help:effective-pom
```

Tìm các trường được kế thừa, versions plugins và dependency app -> core. Đây là phép kiểm cấu hình, **không thay thế compile/test thực tế**.

### 13.6. Xem dependency graph

```bash
mvn -B -ntp -pl :cli-app -am org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Phần liên quan trong kết quả dự kiến có dạng:

```text
com.example.reactor:cli-app:jar:1.0.0
\- com.example.reactor:shared-core:jar:1.0.0:compile
```

Đây là **sơ đồ rút gọn**, không phải toàn bộ Maven log. Dependencies chỉ ở test scope của core không nhất thiết transitively có mặt trên runtime classpath của app.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Aggregator báo phải dùng packaging pom | Root có `<modules>` nhưng packaging mặc định `jar` | Thêm `<packaging>pom</packaging>` |
| `Child module ... does not exist` | `<module>` sai relative path hoặc thiếu POM | Kiểm tra folder và `pom.xml` thực tế |
| Maven không build module mới | Quên thêm `<module>` trong aggregator đúng cấp | Sửa `<modules>` đúng POM |
| Chỉ có `root/pom.xml` được xử lý | Chạy `-N` hoặc `-pl` chỉ root | Chạy Maven từ root không `-N`, xem selection |
| Child không inherit Java release | Chưa khai báo `<parent>` hoặc parent sai GAV/path | Kiểm tra `<parent>` và effective POM |
| Parent POM resolution error | `<relativePath>` sai, GAV mismatch, parent chưa resolve | Kiểm tra local parent POM/repository |
| Module có tên folder khác artifactId | Nhầm `<module>` path với dependency GAV | Dùng folder path trong modules, GAV trong dependency |
| App import core nhưng compiler báo package does not exist | Có aggregation nhưng thiếu `<dependency>` | Thêm dependency app -> core |
| App chạy thiếu core class | Plain app JAR không nhúng dependency | Thêm runtime classpath, thin distribution hoặc Shade nếu cần |
| Module build sai thứ tự | Inter-module dependency chưa thực sự khai báo | Kiểm tra dependency graph, không ép XML order |
| `dependencyManagement` không đổi reactor order | Chỉ quản lý version, chưa instantiate dependency | Khai báo dependency thật |
| Root `mvn package` không tạo combined JAR | Packaging `pom` chỉ gom build | Xem target từng module; dùng plugin packaging riêng nếu muốn distribution |
| Chạy `mvn -pl :cli-app package` không resolve core trên máy sạch | Chọn app không kèm reactor dependency | Dùng `-am` hoặc build toàn reactor |
| `mvn -f cli-app/pom.xml` không thấy sibling module | POM child không phải aggregator của sibling | Chạy từ root aggregator hoặc `-f root/pom.xml` |
| Reactor báo cyclic dependency | Hai module phụ thuộc vòng tròn | Tách module/đưa interface chung xuống lớp thấp hơn |
| `mvn test` core thấy 0 tests | Test source/annotation/provider/naming sai | Kiểm tra JUnit dependency, Surefire và report |
| `invalid target release: 17` | JVM/compiler Maven cũ | Kiểm tra `mvn -version`, dùng JDK 17+ |
| `-pl shared-core` không chọn đúng module | Đang ở folder khác hoặc dùng nhầm path | Chạy từ root hoặc dùng `-pl :shared-core` |
| Module dùng version parent cũ | Child `<parent><version>` không khớp | Đồng bộ GAV và xem effective POM |
| Root parent đặt plugin ở management nhưng không chạy | Plugin chưa có execution/binding phù hợp | Khai báo plugin/execution nơi cần |
| Maven 4 project khác quy ước | Đang dùng guide/configuration cho Maven 3 | Đọc tài liệu Maven 4 tương ứng |

### Quy trình debug 8 bước

1. Xác minh **đang đứng đúng root aggregator** và `mvn -version` cho biết phiên bản Maven/JDK.
2. Kiểm tra root `<packaging>pom</packaging>` và mọi `<module>` relative paths.
3. Kiểm tra mỗi module có `pom.xml`, GAV hợp lệ và packaging mong muốn.
4. Nếu mong inheritance, kiểm tra child `<parent>` và `<relativePath>`.
5. Nếu module tiêu thụ class của module khác, kiểm tra `<dependency>` thực tế.
6. Chạy `mvn -B -ntp validate` và xem Reactor Build Order.
7. Chạy `mvn -B -ntp clean verify` và đọc từng module's test reports.
8. Đối chiếu JAR riêng từng module, chạy Java với classpath chứa những module cần thiết.

## 15. Maven 3 và Maven 4: lưu ý phiên bản

Ví dụ trong bài dùng **Maven 3 và POM model 4.0.0** với `<modules>` ở aggregator. Apache Maven có **hướng dẫn riêng cho Maven 4**, trong đó mô hình thu thập subprojects/định vị root có khác biệt và tài liệu mô tả cả cấu hình `<subprojects>`.

Vì vậy:
- Nếu đang dùng Maven 3, học cú pháp `<modules>` và các lựa chọn reactor theo guide Maven 3.
- Nếu đang thử Maven 4, đọc guide Maven 4 về subprojects/root discovery; không mặc định mọi lệnh/trường cấu hình trong tài liệu Maven 3 cho kết quả giống hệt.
- Đừng đổi cú pháp cấu hình chỉ vì thấy một guide mới: xác nhận `mvn -version`, Maven model/plugin versions và thử trên project thực.

Cụm từ “module” ở bài này chủ yếu chỉ **Maven subproject/module trong reactor**, không phải **Java Platform Module System** với `module-info.java`. Hai cơ chế khác nhau, có thể cùng tồn tại nhưng không nên đánh đồng.

## 16. Bài tập luyện tập

**Bài 1.** Root có `<modules>` nhưng thiếu `<packaging>pom</packaging>`. Vì sao điều này nguy hiểm?

*Đáp án định hướng:* Maven mặc định `jar`, không phù hợp aggregator theo mô hình bài; hãy dùng packaging `pom` cho root aggregator.

**Bài 2.** Trong root có `<module>common-utils</module>`, còn child POM có `<artifactId>shared-core</artifactId>`. Đây có phải lỗi?

*Đáp án:* Không. `<module>` là đường dẫn thư mục/POM; `artifactId` là tọa độ Maven.

**Bài 3.** Root POM có cả `<modules>` và `<properties>`, nhưng child không khai báo `<parent>`. Child có chắc nhận property root không?

*Đáp án:* Không. Aggregation không tự động tạo inheritance.

**Bài 4.** Root là parent nhưng không khai báo `<modules>`. Chạy Maven tại root có tự build các child dùng nó làm parent không?

*Đáp án:* Không. Parent relationship khác aggregation.

**Bài 5.** `cli-app` import class `GreetingFormatter`, nhưng chỉ nằm chung `<modules>` với `shared-core`. Còn thiếu gì?

*Đáp án:* Dependency GAV thật từ `cli-app` tới `shared-core`.

**Bài 6.** Đảo thứ tự `cli-app` đứng trước `shared-core` trong `<modules>` thì reactor có bắt buộc build app trước không?

*Đáp án:* Không. Inter-module dependency thực tế buộc core build trước app.

**Bài 7.** Vì sao `mvn -pl :cli-app -am package` hữu ích trên checkout sạch?

*Đáp án:* `-pl` chọn app, `-am` build cả các module mà app phụ thuộc trong reactor.

**Bài 8.** `mvn -N validate` ở root xử lý bao nhiêu project?

*Đáp án:* Chỉ root hiện tại, không recursively build các modules.

**Bài 9.** `mvn clean package` ở root có tạo một JAR hợp nhất của mọi module không?

*Đáp án:* Không; root đóng gói POM, JARs được tạo riêng ở modules. Muốn fat JAR/distribution cần cấu hình bổ sung.

**Bài 10.** Một dependency chỉ có trong `<dependencyManagement>` của parent có tự được đưa vào app classpath hoặc ảnh hưởng reactor sort không?

*Đáp án:* Không nếu chưa được instantiated qua `<dependency>` thực tế.

## 17. Checklist thiết kế Aggregator POM

- [ ] Root aggregator có `<packaging>pom</packaging>`.
- [ ] Root `<modules>` liệt kê đúng relative paths tới **các Maven project**.
- [ ] Mỗi child directory có một `pom.xml` hợp lệ.
- [ ] Không nhầm `<module>` path với `groupId:artifactId:version`.
- [ ] Phân biệt aggregator relationship và parent inheritance.
- [ ] Nếu muốn children kế thừa properties/config, khai báo `<parent>` với GAV chính xác.
- [ ] `<relativePath>` từ child tới parent POM đúng (hoặc chủ động resolve parent từ repository).
- [ ] Mỗi module có packaging đúng (`jar`, `war`, `pom`... theo nhiệm vụ).
- [ ] Module tiêu thụ public API của module khác phải khai báo `<dependency>` thực tế.
- [ ] Không dùng `<modules>` order để bù cho dependency thiếu.
- [ ] Không tạo dependency cycle giữa module.
- [ ] Root `pom` không được kỳ vọng tạo combined executable JAR.
- [ ] Khi dùng `-pl`, cân nhắc `-am` để build prerequisites trong reactor.
- [ ] Kiểm tra build từ root, Reactor Build Order và các `target/` riêng.
- [ ] Child POM kế thừa đúng versions/properties, xác minh bằng effective POM.
- [ ] JDK/Maven/plugin versions phù hợp Java release 17.
- [ ] Trước CI, có lệnh build toàn reactor và selective build để phát hiện cấu hình bị thiếu.
- [ ] Nếu dùng Maven 4, đối chiếu riêng tài liệu subprojects/root discovery.

**Kết luận:** Aggregator POM là điểm vào của **Maven multi-module reactor**, dùng `<packaging>pom</packaging>` và `<modules>` để thu thập các Maven project, nhưng **không tự tạo dependencies hoặc kế thừa cấu hình**. Kế thừa xảy ra qua `<parent>`, và quan hệ compile/runtime thực sự cần `<dependency>` trong module tiêu thụ. Khi hiểu đúng ba mối quan hệ **aggregation – inheritance – dependency**, bạn có thể build toàn repository bằng một lệnh, chọn module bằng `-pl`, xây prerequisites bằng `-am` và dự đoán chính xác thứ tự reactor.

## Nguồn Apache Maven chính thức

- [Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven — Introduction to the POM: Inheritance vs Aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Maven — POM Reference: Aggregation / modules](https://maven.apache.org/pom.html)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — Maven 4 Guide to Multiple Subprojects](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)