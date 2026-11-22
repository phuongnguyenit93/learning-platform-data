# Vì sao dependencyManagement không tự tạo cạnh phụ thuộc thực thi trong Maven Reactor

## 1. Vấn đề: một dependency được “quản lý” nhưng Reactor không đổi thứ tự

Trong một repository Maven nhiều mô-đun, nhóm phát triển thường đặt phiên bản thư viện ở POM cha:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.reactor</groupId>
            <artifactId>library-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó họ nhìn thấy `consumer-app` và `library-core` cùng nằm trong `<modules>` rồi kỳ vọng Maven tự hiểu:

~~~text
consumer-app phụ thuộc library-core
          |
          v
Reactor phải build library-core trước consumer-app
~~~

**Kỳ vọng đó không đúng chỉ từ `dependencyManagement`.** Phần này **quản lý thông tin của một dependency nếu dependency được sử dụng**; nó **không tự thêm** dependency vào danh sách trực tiếp của module ứng dụng. Khi thiếu một tham chiếu đã được khai báo sử dụng thực sự, Maven Reactor **không có cạnh dependency giữa hai module** để quyết định thứ tự.

Theo tài liệu chính thức của Apache Maven, khi sắp xếp Reactor, Maven chỉ xét những tham chiếu **“instantiated”** — nghĩa là những quan hệ thực sự xuất hiện trong mô hình build. Riêng các entry trong `dependencyManagement` và `pluginManagement` **không làm thay đổi thứ tự Reactor**.

Bài này làm rõ bốn khái niệm dễ nhầm:

1. **Aggregation**: `<modules>` đưa những module nào vào cùng một reactor build.
2. **Inheritance**: `<parent>` cho phép module thừa hưởng cấu hình và tạo quan hệ POM cha–con.
3. **Dependency management**: `<dependencyManagement>` thống nhất version, scope và metadata khi một dependency được dùng.
4. **Project dependency**: `<dependencies>` khai báo module này thực sự phụ thuộc module kia, tạo classpath relationship và **cạnh build-order trong Reactor** khi cả hai thuộc reactor.

**Công thức nhớ:** *Management quyết định “nếu dùng thì dùng như thế nào”; dependencies quyết định “có dùng hay không”.* Reactor phải dựa trên quan hệ đã được kích hoạt, chứ không tự dựng cạnh từ một danh sách quản lý phiên bản có thể không bao giờ được dùng.

## 2. Reactor làm gì với một build nhiều mô-đun?

**Maven Reactor** là cơ chế điều phối các Maven projects trong một phiên build đa module. Với mô hình Maven 3 truyền thống, Reactor:

1. **Thu thập** các module từ các aggregator POM và những module con phù hợp.
2. **Sắp thứ tự** các project sao cho những project mà project khác cần được build trước.
3. **Thực thi** lifecycle/goal cho tập projects được chọn, có xét graph và chế độ song song khi được bật.

Ví dụ:

~~~text
reactor-lab/                 root POM: packaging=pom
├── pom.xml
├── consumer-app/
│   └── pom.xml
└── library-core/
    └── pom.xml
~~~

Khai báo:

~~~xml
<modules>
    <module>consumer-app</module>
    <module>library-core</module>
</modules>
~~~

chỉ có nghĩa **hai đường dẫn được đưa vào reactor**. Nó **không tự biểu đạt** rằng consumer sử dụng API của core. Nếu không tồn tại cạnh khác, thứ tự trong `<modules>` được dùng làm **quy tắc phụ** khi Reactor sắp xếp.

**Lưu ý parent:** nếu cả `consumer-app` và `library-core` đều khai báo POM gốc bằng `<parent>`, sẽ có quan hệ parent-to-child được Reactor xem xét. Vì vậy root thường được xử lý trước children. Điều này **không đồng nghĩa có cạnh `consumer-app -> library-core`**; cần phân tích riêng quan hệ giữa **hai module anh em**.

Trong một build với `-T 2`, nhiều module độc lập còn có thể thực thi **đồng thời**. Không dùng thời gian chạy quan sát một lượt hoặc `System.out.println` để suy diễn dependency graph; hãy kiểm tra POM và build-order constraints.

## 3. Những cạnh nào thực sự ảnh hưởng Reactor sorting?

Tài liệu Apache Maven liệt kê các loại quan hệ được Reactor tôn trọng khi sắp xếp:

| Tham chiếu trong build | Có thể tạo ràng buộc thứ tự Reactor? | Ví dụ |
| --- | --- | --- |
| **Project dependency trực tiếp** trên module khác trong reactor | **Có** | `consumer-app` khai báo `library-core` dưới `<dependencies>`. |
| **Build plugin được khai báo sử dụng** là module khác trong reactor | **Có** | Một project dùng plugin tự phát triển ở module `company-maven-plugin`. |
| **Dependency của plugin** tham chiếu module trong reactor | **Có** | Plugin runtime có plugin dependency nằm trong reactor. |
| **Build extension** tham chiếu module khác trong reactor | **Có** | Project dùng extension xây trong cùng reactor. |
| **Parent POM** là module trong reactor | **Có** | `consumer-app` khai báo `<parent>` trỏ tới `reactor-lab`. |
| **Thứ tự khai báo `<modules>`** | **Quy tắc phụ** | Dùng khi không có ràng buộc trước nào phân biệt các module. |
| **Entry chỉ có trong `<dependencyManagement>`** | **Không** | Quản lý version của `library-core`, nhưng không có dependency thực. |
| **Entry chỉ có trong `<pluginManagement>`** | **Không** | Quản lý version/config plugin chưa được khai báo sử dụng. |

Mọi cạnh trên đều được xét **khi tham chiếu thực sự là quan hệ của project trong reactor**. Việc một artifact có cùng groupId/artifactId với một module khác nhưng chỉ xuất hiện như giá trị được quản lý **chưa đủ**.

**Hai điểm cần phân biệt:**

- “Không tạo cạnh” **không đồng nghĩa dependencyManagement vô tác dụng**. Nó vẫn chọn version/scope/exclusions cho những dependency được sử dụng và có thể ảnh hưởng kết quả giải quyết transitive dependency.
- “Có cạnh Reactor” **không hoàn toàn đồng nghĩa dùng library ở runtime**. Dependency scope `test` hoặc `provided` cũng biểu diễn một dependency thực sự cho một phần lifecycle, dù runtime classpath khác `compile`/`runtime`.

## 4. Ví dụ đồ thị: trước và sau một khai báo thật

Giả sử root POM liệt kê `consumer-app` **trước** `library-core`, nhưng quản lý version core.

**Trạng thái A — chỉ quản lý:**

~~~text
     reactor-lab (parent)
         /         \
        v           v
 consumer-app     library-core

Không có cạnh consumer-app -> library-core
Dùng thứ tự fallback của <modules> giữa hai module anh em
~~~

Với một lượt Maven tuần tự và không có ràng buộc khác, thứ tự dự kiến:

~~~text
reactor-lab
consumer-app
library-core
~~~

**Trạng thái B — khai báo project dependency thật:**

~~~text
     reactor-lab (parent)
         /         \
        v           v
 consumer-app ---> library-core
    yêu cầu        cung cấp API

Để build consumer-app, library-core phải được build trước
~~~

Mũi tên ở đây chỉ **chiều phụ thuộc** (*consumer cần core*), nên **thứ tự xây dựng đi ngược chiều mũi tên**:

~~~text
reactor-lab
library-core
consumer-app
~~~

Chính **sự xuất hiện của dependency trong `<dependencies>`** tạo quan hệ build-order cần thiết giữa hai siblings. Việc đổi vị trí `<modules>` mà không khai báo dependency thực sự chỉ thay thứ tự fallback, **không làm library xuất hiện trong classpath của consumer**.

## 5. Ba cấu trúc POM có vai trò khác nhau

### 5.1. `<modules>`: tập hợp projects

~~~xml
<modules>
    <module>consumer-app</module>
    <module>library-core</module>
</modules>
~~~

Đây là **aggregation**, không phải một danh sách dependencies. Các path là đường dẫn tới project POM. Một project có thể vừa là aggregator vừa là parent, nhưng **aggregation và inheritance là hai khái niệm riêng**.

### 5.2. `<dependencyManagement>`: metadata nếu sử dụng

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.reactor</groupId>
            <artifactId>library-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Entry chỉ **định nghĩa phiên bản được quản lý** cho một dependency phù hợp. Nó không nói module nào cần class của `library-core` và không buộc Maven chèn JAR vào classpath của tất cả module con.

### 5.3. `<dependencies>`: dependency đã được khai báo

Trong POM của `consumer-app`:

~~~xml
<dependencies>
    <dependency>
        <groupId>vn.example.reactor</groupId>
        <artifactId>library-core</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **khai báo sử dụng thực sự**. Version được lấy từ `dependencyManagement` kế thừa ở parent nên không cần lặp `1.0.0` trong child. Khi `library-core` cũng thuộc reactor, Maven có dữ liệu để **xếp core trước app**.

**Một lựa chọn tốt:** quản lý phiên bản tập trung ở parent nhưng **khai báo dependencies đúng nhu cầu tại từng child**. Điều đó làm graph minh bạch: module không dùng core sẽ không cần core chỉ vì parent có danh sách managed dependencies.

## 6. Dự án Java 17 chạy được — trạng thái A: chỉ dependencyManagement

Ta tạo một reactor gồm:

- **Root `reactor-lab`**: aggregator và parent, packaging `pom`, quản lý dependency versions và plugin versions.
- **`consumer-app`**: ứng dụng Java độc lập, ban đầu **không dùng** API của core.
- **`library-core`**: thư viện Java nhỏ.
- **JUnit Jupiter** để kiểm tra cả hai module.

Bản đầu tiên cố ý khai báo `consumer-app` trước `library-core`. Hai module đều có parent nên phụ thuộc root về mô hình POM, nhưng **không có dependency giữa hai anh em**.

**Yêu cầu:** Maven 3.9+ và JDK 17+ trong môi trường có khả năng tải plugin/JUnit đã chỉ định. Cấu hình thuộc nhánh Maven 3 với `<modules>`; Maven 4 có tài liệu riêng về nhiều subprojects.

Cây project:

~~~text
reactor-lab/
├── pom.xml
├── consumer-app/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/reactor/app/App.java
│       └── test/java/vn/example/reactor/app/AppTest.java
└── library-core/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/reactor/core/CoreMessage.java
        └── test/java/vn/example/reactor/core/CoreMessageTest.java
~~~

### 6.1. Root `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.reactor</groupId>
    <artifactId>reactor-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <!-- Cố ý đặt consumer trước core để quan sát sorting. -->
    <modules>
        <module>consumer-app</module>
        <module>library-core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>vn.example.reactor</groupId>
                <artifactId>library-core</artifactId>
                <version>1.0.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
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
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Điểm cần đọc cẩn thận:**

- `<modules>` chỉ thu thập hai module, theo thứ tự **consumer trước core**.
- `<dependencyManagement>` quản lý cả version `library-core` lẫn JUnit. Nó **không thêm core vào consumer** và **không tự chạy JUnit**.
- `<pluginManagement>` pin versions của Compiler, Surefire và JAR Plugin khi lifecycle sử dụng chúng; **không tự tạo project dependency**.
- Root packaging `pom` không có `src/main/java` và không biên dịch như module `jar`.
- Vì các child khai báo `<parent>` trỏ tới root, chúng **thừa hưởng** các phiên bản được quản lý và property Java 17.
- Đặt JUnit trong `dependencyManagement` mới là bước quản lý version; ở mỗi child vẫn phải **khai báo JUnit thực sự trong `<dependencies>`** nếu muốn compile/run test JUnit.

### 6.2. `consumer-app/pom.xml` — chưa phụ thuộc core

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>consumer-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Lưu ý về cú pháp XML:** ở dòng khai báo `<project>` thực tế chỉ cần khai báo `xmlns:xsi` **một lần**, như POM đầy đủ chuẩn dưới đây. Dùng bản đã chuẩn hóa này khi tạo file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>consumer-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Trong POM này, **không có dependency với artifactId `library-core`**. Do đó consumer không thể sử dụng class của core chỉ nhờ root management. JUnit là dependency thật nhưng nó là thư viện ngoài reactor, không tạo cạnh giữa hai siblings.

### 6.3. `library-core/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>library-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 6.4. `consumer-app/src/main/java/vn/example/reactor/app/App.java`

~~~java
package vn.example.reactor.app;

public final class App {
    private App() {
    }

    public static String describe() {
        return "APP_STANDALONE";
    }

    public static void main(String[] args) {
        System.out.println(describe());
    }
}
~~~

Đoạn này chỉ dùng Java chuẩn, **không tham chiếu `CoreMessage`**. Bởi thế consumer là module thực sự độc lập ở trạng thái A, chứ không cố compile một class còn thiếu dependency.

### 6.5. `consumer-app/src/test/java/vn/example/reactor/app/AppTest.java`

~~~java
package vn.example.reactor.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void standaloneBehavior() {
        assertEquals("APP_STANDALONE", App.describe());
    }
}
~~~

JUnit compile/run được vì consumer POM có dependency JUnit thực trong `<dependencies>` với version do parent quản lý.

### 6.6. `library-core/src/main/java/vn/example/reactor/core/CoreMessage.java`

~~~java
package vn.example.reactor.core;

public final class CoreMessage {
    private CoreMessage() {
    }

    public static String message() {
        return "ready";
    }

    public static void main(String[] args) {
        System.out.println("CORE: " + message());
    }
}
~~~

### 6.7. `library-core/src/test/java/vn/example/reactor/core/CoreMessageTest.java`

~~~java
package vn.example.reactor.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CoreMessageTest {
    @Test
    void returnsStableMessage() {
        assertEquals("ready", CoreMessage.message());
    }
}
~~~

Các file trong mục 6 ghép thành **trạng thái A độc lập và runnable**. Chưa cần thay thêm module nào, không có database, Docker hoặc source generator.

## 7. Thực hành A: build thành công nhưng không có cạnh consumer → core

Chạy từ thư mục `reactor-lab`:

~~~bash
mvn --version
mvn -B -ntp clean verify
~~~

Với Maven 3.x, JDK 17+, đủ dependency, Reactor thu thập root và hai module. Vì **không có dependency giữa consumer và core**, thứ tự build tuần tự dự kiến theo các ràng buộc POM hiện tại là:

~~~text
Reactor Build Order:
  reactor-lab
  consumer-app
  library-core
~~~

Đây là **kết cấu thứ tự minh họa**, không phải toàn bộ log Maven hay bảo đảm cách format tên hiển thị đúng mọi phiên bản.

Cả hai child có một JUnit test. Khi Surefire chạy đúng, các assertions đều pass. Không khẳng định chính xác số dòng log, vì Maven/plugin versions và caching có thể thay đổi.

### Chạy các class độc lập

**Linux/macOS:**

~~~bash
java -cp consumer-app/target/classes vn.example.reactor.app.App
java -cp library-core/target/classes vn.example.reactor.core.CoreMessage
~~~

**Windows PowerShell:**

~~~powershell
java -cp consumer-app\target\classes vn.example.reactor.app.App
java -cp library-core\target\classes vn.example.reactor.core.CoreMessage
~~~

Stdout **riêng của từng lệnh Java** là:

~~~text
APP_STANDALONE
~~~

và:

~~~text
CORE: ready
~~~

Không cần thêm JUnit vào runtime classpath của hai main class: chúng không gọi API JUnit.

### Chỉ chọn consumer với `-pl -am`

~~~bash
mvn -B -ntp -pl :consumer-app -am clean verify
~~~

`-pl :consumer-app` chọn module bằng artifactId, còn `-am` (*also make*) bổ sung các project upstream mà module được chọn cần trong reactor. Ở **trạng thái A**, `library-core` **không phải upstream dependency của consumer**, nên nó **không được kéo vào chỉ nhờ entry managed ở root**.

Parent POM gốc vẫn có thể nằm trong tập cần xử lý do parent relationship; điều quan trọng của thí nghiệm là **không có lý do dependency để thêm `library-core`**. Đừng so cứng log tên parent giữa các Maven versions; hãy xác định có hay không `library-core`.

**Thí nghiệm này là bằng chứng rất trực quan:** nếu chỉ nhìn root `<dependencyManagement>` thấy `library-core` mà `-pl -am` không chọn core, điều đó chứng minh managed entry **không phải một dependency edge**.

## 8. Thực hành B: thêm khai báo thật và thấy Reactor đổi thứ tự

Giờ giả sử ứng dụng **thực sự cần API** của core. Ta thay **POM consumer** và mã ứng dụng/test để mô hình build phản ánh nhu cầu đó.

### 8.1. Thay `consumer-app/pom.xml` bằng bản sau

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>consumer-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example.reactor</groupId>
            <artifactId>library-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Chú ý **dependency core không khai báo `<version>`**. Maven lấy version `1.0.0` từ root `dependencyManagement`. Đây chính xác là vai trò mong muốn của management: **không quyết định có dùng core, chỉ định version khi child đã nói cần core**.

### 8.2. Thay `App.java` bằng mã dùng API core

~~~java
package vn.example.reactor.app;

import vn.example.reactor.core.CoreMessage;

public final class App {
    private App() {
    }

    public static String describe() {
        return "APP_WITH_CORE: " + CoreMessage.message();
    }

    public static void main(String[] args) {
        System.out.println(describe());
    }
}
~~~

Bây giờ source có `import vn.example.reactor.core.CoreMessage;`. Vì POM consumer đã có direct dependency, class này có trên **compile classpath** khi core được xây dựng đúng.

### 8.3. Thay `AppTest.java`

~~~java
package vn.example.reactor.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void usesCoreLibrary() {
        assertEquals("APP_WITH_CORE: ready", App.describe());
    }
}
~~~

**Không cần sửa root `dependencyManagement` hoặc POM của `library-core`**. Ta chỉ thêm dependency thực vào đúng child cần dùng và cập nhật code/test tương ứng.

## 9. Thực hành B: thứ tự build đổi dù `<modules>` giữ nguyên

Chạy lại ở root:

~~~bash
mvn -B -ntp clean verify
~~~

Root vẫn liệt kê:

~~~xml
<modules>
    <module>consumer-app</module>
    <module>library-core</module>
</modules>
~~~

nhưng Reactor hiện có cạnh **consumer-app phụ thuộc library-core**. Thứ tự build tuần tự dự kiến:

~~~text
Reactor Build Order:
  reactor-lab
  library-core
  consumer-app
~~~

**Vì sao?** Core phải có artifact cho consumer ở compile/test/package trước. Quan hệ đã được khai báo thực sự có ưu tiên so với thứ tự fallback trong `<modules>`.

### Kiểm tra `-pl -am` sau khi thêm cạnh

~~~bash
mvn -B -ntp -pl :consumer-app -am clean verify
~~~

Ở trạng thái B, lệnh này **phải bao gồm library-core** trong tập project upstream cần build trước consumer, vì consumer có direct project dependency thật.

Có thể so sánh với trạng thái A:

| Tình huống | Chỉ có managed entry ở parent? | Direct dependency trong consumer? | `-pl :consumer-app -am` có kéo core? |
| --- | --- | --- | --- |
| **A**: consumer độc lập | Có | **Không** | **Không**, chỉ managed không tạo edge. |
| **B**: consumer dùng core | Có | **Có** | **Có**, vì đã có project dependency. |

Đây là cách hiểu đúng về **“cạnh phụ thuộc thực thi”**: Reactor dùng cạnh để quyết định module nào phải sẵn sàng trước module khác. Cạnh đó **đến từ project dependency đã khai báo**, không phải metadata phiên bản chưa được sử dụng.

### Chạy ứng dụng B với đúng classpath

**Linux/macOS:**

~~~bash
java -cp "consumer-app/target/classes:library-core/target/classes" vn.example.reactor.app.App
~~~

**Windows PowerShell:**

~~~powershell
java -cp "consumer-app\target\classes;library-core\target\classes" vn.example.reactor.app.App
~~~

Stdout **chính xác**:

~~~text
APP_WITH_CORE: ready
~~~

**Phân biệt classpath theo OS:** Java dùng `:` ngăn cách classpath entries trên Unix và `;` trên Windows. Không chạy lệnh của Unix nguyên xi trên Windows hoặc ngược lại.

Đoạn ví dụ chạy từ `target/classes` của hai module để không cần cài JAR vào local Maven repository. Với sản phẩm thật, nên kiểm thử runtime artifact/JAR và dependency graph được đóng gói hoặc triển khai phù hợp; classpath từ target classes **chỉ dùng cho thí nghiệm build-order**.

## 10. Nếu giữ import nhưng xóa direct dependency thì sao?

Đây là một phản chứng hữu ích. Ở **trạng thái B**, code `App.java` đang:

~~~java
import vn.example.reactor.core.CoreMessage;
~~~

Nếu bạn **xóa dependency `library-core` khỏi `<dependencies>` của consumer** nhưng vẫn giữ root `dependencyManagement` và source import, Maven **không có lý do đưa `library-core` vào compile classpath**. Khi compile, thường xuất hiện lỗi có ý nghĩa như:

~~~text
package vn.example.reactor.core does not exist
cannot find symbol: variable CoreMessage
~~~

Dòng trên là **thông báo rút gọn minh họa**, không cam kết compiler version dùng đúng câu chữ. Mấu chốt: **version management không cấp classpath**.

Điều này cũng giải thích vì sao **thư viện đã tồn tại trong `.m2/repository` không đủ**. Maven không tự thêm mọi JAR có sẵn vào classpath. Phải có **dependency thực sự** (trực tiếp hoặc theo đường transitive hợp lệ) mới được giải quyết vào classpath phù hợp.

Nếu ứng dụng vô tình compile nhờ một dependency **bắc cầu**, có thể phát sinh dependency “ẩn” dễ gãy khi graph thay đổi. Apache Maven khuyến nghị khai báo **trực tiếp** các thư viện mà source code của project trực tiếp sử dụng.

## 11. `dependencyManagement` thực sự quản lý những gì?

Khi một dependency được kích hoạt, `dependencyManagement` có thể dùng để:

- **Cố định phiên bản** của dependency khi child bỏ `<version>`.
- **Quản lý scope** hoặc metadata dependency ở những trường hợp phù hợp.
- **Quản lý exclusions/optional** theo cấu trúc dependency management được áp dụng.
- **Ảnh hưởng version selection của transitive dependencies**, tức dependency mediation trong graph đã tồn tại.
- **Chuẩn hóa thông tin** giữa nhiều module cùng dùng một thư viện nhưng tránh copy-paste version.

Ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Nếu `consumer-app` **không khai báo Commons Lang và không có đường transitive phù hợp**, management entry đó **không làm Commons Lang xuất hiện trên runtime classpath**.

Nếu consumer khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

thì Maven chọn version managed cho dependency đó. **Bây giờ có dependency thật với Commons Lang**, nhưng vì Commons Lang là thư viện **ngoài các project trong reactor ví dụ**, nó **không tạo cạnh giữa `consumer-app` và `library-core`**.

### Managed dependency có thể là dependency bắc cầu

Một dependency managed có thể ảnh hưởng phiên bản của artifact được đưa tới qua transitive graph. Tuy nhiên, điều đó **không giống** management tự đặt thêm một project dependency mới. Cần phân biệt:

- **Chọn version của artifact đã tham gia resolution**.
- **Tạo một cạnh project → artifact** bằng dependency đã được khai báo/thực sự được dùng.

Với reactor sorting, tài liệu Maven mô tả việc chỉ các **instantiated references** được xét. Khi điều tra một graph phức tạp có nhiều transitive dependencies, nên xem cả **effective POM**, **dependency tree** và thứ tự Reactor thực tế, không suy luận từ một managed list.

## 12. `dependencyManagement` khác `<dependencies>` đặt ở parent

Đây là một bẫy lớn khi thiết kế POM cha.

**Đặt ở `<dependencyManagement>` của parent:**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.reactor</groupId>
            <artifactId>library-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Chỉ quản lý phiên bản. Child **không tự nhận library-core** như dependency.

**Đặt ở `<dependencies>` của parent:**

~~~xml
<dependencies>
    <dependency>
        <groupId>vn.example.reactor</groupId>
        <artifactId>library-core</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Đây là dependency thật **được thừa hưởng bởi các child**, nên có thể đưa `library-core` vào nhiều module **kể cả module không sử dụng nó**. Tệ hơn, nếu `library-core` cũng khai báo parent là root, việc để root project phụ thuộc ngược vào library-core có thể dẫn tới **chu trình project/parent graph** hoặc build khó giải quyết.

**Khuyến nghị:** khi muốn tất cả modules dùng cùng version nhưng **chỉ một số module thật sự dùng thư viện**, hãy giữ dependency version ở `dependencyManagement`, còn khai báo `<dependencies>` tại đúng các child cần API đó. **Đừng chuyển cả danh sách managed vào parent dependencies chỉ để ép thứ tự Reactor**.

## 13. `pluginManagement` cũng không tự tạo cạnh

Một parent có thể quản lý plugin nội bộ:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>vn.example.build</groupId>
                <artifactId>company-check-plugin</artifactId>
                <version>1.0.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là đoạn XML **minh họa**, không phải phần của dự án runnable ở mục 6. Nếu plugin `company-check-plugin` có module riêng trong reactor nhưng consumer **chỉ kế thừa pluginManagement**, Maven **không có plugin-use edge** chỉ từ danh sách quản lý này.

Nếu consumer thực sự khai báo plugin trong `build/plugins`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>vn.example.build</groupId>
            <artifactId>company-check-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

thì đó là một **plugin declaration instantiated**, có thể tạo quan hệ sort nếu plugin là một module khác trong reactor. Version có thể được lấy từ `pluginManagement`, tương tự managed project dependency.

**Cẩn trọng:** plugin declaration không phải `project dependency` trong classpath của ứng dụng. Plugin được Maven chạy ở build time trong plugin realm, khác runtime classpath mà code main dùng. Không dùng `<build><plugins>` để thay cho dependency API của `App.java`.

## 14. Parent và aggregator: cùng một POM, hai trách nhiệm

Một POM root thường có:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>consumer-app</module>
    <module>library-core</module>
</modules>
~~~

Đó là **aggregator**: thu thập modules.

Một child lại có:

~~~xml
<parent>
    <groupId>vn.example.reactor</groupId>
    <artifactId>reactor-lab</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Đó là **inheritance**: nhận effective model từ parent. Root trong demo **vừa là aggregator vừa là parent**, nhưng hai chức năng độc lập về mặt mô hình.

Những hiểu nhầm cần tránh:

- Có `<module>consumer-app</module>` **không mặc định** làm root trở thành `<parent>` của consumer.
- Có `<parent>` **không mặc định** đưa child vào reactor nếu aggregator không thu thập nó.
- Có parent relationship **không nói** consumer phụ thuộc library-core; cả hai có thể chỉ cùng phụ thuộc mô hình POM root.
- Có `dependencyManagement` ở root aggregator mà child **không kế thừa root** thì child không tự có managed entries đó (trừ khi dùng cơ chế import/management khác hợp lệ).

**Đừng tạo “cạnh giả” bằng cách thay đổi cấu trúc parent chỉ để ép thứ tự modules.** Hãy biểu diễn quan hệ thật bằng đúng khái niệm Maven.

## 15. Vì sao đổi vị trí trong `<modules>` chỉ là cách chữa tạm?

Giả sử đổi root thành:

~~~xml
<modules>
    <module>library-core</module>
    <module>consumer-app</module>
</modules>
~~~

Ở trạng thái A (không có project dependency), thứ tự tuần tự fallback sẽ dễ thành **core trước app**. Nhưng:

1. **Consumer không có compile classpath chứa core.**
2. `-pl :consumer-app -am` vẫn **không kéo core** nếu không có quan hệ khác.
3. `mvn -T 2` có thể build hai siblings độc lập song song.
4. Một dự án nhiều module thay đổi thứ tự `<modules>` có thể che chứ không sửa graph.
5. Khi ai đó tách consumer ra một reactor subset, giả định “core đã build trước” biến mất.

**Reactor không phải một script tuần tự được mô tả duy nhất bằng `<modules>`**. Nó sử dụng graph quan hệ trước; thứ tự modules chỉ là tie-breaker. Nếu code cần core, hãy **khai báo core trong dependencies**.

## 16. Khi nào `-pl -am` và `-amd` giúp kiểm tra graph?

Các lệnh này đặc biệt hữu ích khi muốn kiểm tra xem Reactor có “biết” dependency thật hay không.

| Cờ | Ý nghĩa | Tình huống |
| --- | --- | --- |
| **`-pl :consumer-app`** | Chọn project cụ thể theo artifactId. | Chỉ build consumer (nếu các artifacts upstream đã có). |
| **`-am`** | *Also make*: thêm các reactor projects mà project đã chọn cần. | Chọn consumer, kéo library-core nếu có project dependency thật. |
| **`-amd`** | *Also make dependents*: thêm các modules phụ thuộc project được chọn. | Chọn core, kéo consumer nếu consumer khai báo dùng core. |
| **`-rf :consumer-app`** | Resume từ project được chọn trong reactor sequence. | Tiếp tục sau failure, không dùng để tạo graph. |
| **`-T 2`** | Cho phép thực thi song song các modules đủ điều kiện. | Kiểm tra graph đủ an toàn với parallel build. |

**Thực hành B:**

~~~bash
mvn -B -ntp -pl :consumer-app -am clean verify
~~~

sẽ kéo core vì consumer có dependency thực. Ở trạng thái A, không.

Ngược chiều:

~~~bash
mvn -B -ntp -pl :library-core -amd verify
~~~

có thể bao gồm consumer ở trạng thái B vì consumer **phụ thuộc** core, nhưng ở A không có quan hệ này để kéo consumer. Lưu ý với `-amd` khi chạy goal cần artifact upstream: tùy graph selection và artifacts đã cài/build, có thể phải build đủ modules trước; đừng diễn giải một lỗi artifact resolution thành bằng chứng rằng -amd không nhận quan hệ.

**Không dùng `-pl` như cách tự giải quyết thiếu dependency**. Nếu module chọn thiếu upstream chưa được build/không có trong repository, cần thêm `-am` khi quan hệ thực tồn tại, hoặc thiết lập resolution phù hợp; `-pl` chỉ chọn project.

## 17. Quan sát `effective-pom` để phân biệt managed và actual

Một cách kiểm tra không cần thay code là xuất effective POM của consumer:

~~~bash
mvn -pl :consumer-app help:effective-pom -Doutput=effective-consumer-pom.xml
~~~

Với **trạng thái A**, effective POM sẽ có `dependencyManagement` kế thừa từ parent, bao gồm managed `library-core`, nhưng **`dependencies` của consumer không chứa library-core**.

Với **trạng thái B**, effective POM còn có **entry library-core trong `dependencies`**, được điền thông tin managed như version.

**Cần tìm trong hai phần XML khác nhau**:

~~~text
project/dependencyManagement/dependencies/dependency
    = metadata quản lý
project/dependencies/dependency
    = dependencies của project
~~~

Đây là **sơ đồ vị trí XML**, không phải cách viết XPath được chuẩn hóa. Đừng chỉ search text `library-core` trong toàn file rồi kết luận module có dependency, vì từ đó có thể nằm **chỉ trong dependencyManagement**.

Nếu dùng `-Dverbose` với Help Plugin phiên bản hỗ trợ, output có thể hiển thị nguồn kế thừa của cấu hình; hữu ích khi parent/BOM/profile phức tạp.

**Không sửa `effective-consumer-pom.xml` để thay đổi project**. Đây là output quan sát; nguồn cấu hình là `pom.xml` của parent, child hoặc imported BOM/profiles.

## 18. Dependency tree: chỉ hiển thị graph được giải quyết, không phải managed catalog

Sau khi đã build cả reactor và các dependency cần thiết được giải quyết, có thể chạy:

~~~bash
mvn -B -ntp -pl :consumer-app -am \
    org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
~~~

Trên Windows PowerShell, viết cùng câu lệnh **trên một dòng**:

~~~powershell
mvn -B -ntp -pl :consumer-app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
~~~

Mục đích của goal `dependency:tree` là xem graph **project dependencies thực sự được giải quyết**, gồm đường transitive nếu có, chứ không in mọi entry managed chỉ vì chúng nằm trong catalog.

- **Trạng thái A:** consumer tree có JUnit test và các transitive dependencies, nhưng **không có một đường `consumer-app -> library-core`**.
- **Trạng thái B:** consumer tree có `vn.example.reactor:library-core:jar:1.0.0` trực tiếp, vì đã khai báo nó trong `<dependencies>`.

**Hạn chế thao tác:** `dependency:tree` có thể cần artifacts trong local repository hoặc output reactor phù hợp. Nếu chạy goal khi artifact chưa được build và resolver báo không tìm thấy JAR, trước hết build các modules cần thiết. Không tự kết luận management tạo edge chỉ vì Maven đang tải hay nhìn thấy metadata từ `.m2`.

### Vì sao không chỉ nhìn `mvn dependency:list`?

Các goal quan sát dependency có thể hiển thị dữ liệu khác nhau: dependency list, tree, effective model, plugins, managed entries. Để điều tra **cạnh Reactor**, hãy xác nhận chính xác **module consumer có actual dependency hay không**, không dựa vào một danh sách version mang tên “managed”.

## 19. BOM import và những ngộ nhận trong multi-module

Một **Bill of Materials (BOM)** là một POM mô tả danh sách managed dependency versions. Khi import:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>2.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Maven dùng BOM để bổ sung **quy tắc dependency management**. Điều này **không thêm tất cả artifact trong BOM vào ứng dụng** và không làm mọi dependency có trong BOM trở thành cạnh Reactor.

**Hai lưu ý khác nhau:**

1. **BOM được import phải giải quyết được như một POM artifact** khi Maven xây dựng effective model. Đừng nhầm việc resolve BOM POM với việc tham gia runtime classpath.
2. Tài liệu Maven lưu ý **không nên cố import một BOM được định nghĩa như submodule của chính POM đang import**, vì có thể phát sinh vấn đề resolution/quan hệ vòng. Với repo nhiều module, thường publish/import một BOM đã có sẵn hoặc thiết kế parent management trực tiếp phù hợp.

**BOM là phiên bản catalog, không phải một chỉ thị build thứ tự**. Với các thay đổi Maven 4, cách tổ chức projects/BOM có thể khác so với Maven 3; hãy kiểm tra đúng hướng dẫn cho major version đang dùng.

## 20. Dependency scope có biến management thành dependency không?

Không. Scope chỉ có ý nghĩa khi có **dependency thực sự**.

Ví dụ:

~~~xml
<dependency>
    <groupId>vn.example.reactor</groupId>
    <artifactId>library-core</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đây vẫn là một **actual dependency**, dù chỉ cần cho test compile/runtime. Nếu core là module trong reactor, quan hệ này có thể buộc core được build trước consumer khi chạy lifecycle cần dependency đó. Nhưng class của core **không mặc nhiên có trong runtime classpath production**.

Những scope thường gặp:

| Scope | Mục đích gần đúng | Liên quan graph |
| --- | --- | --- |
| `compile` (mặc định) | Compile và runtime của ứng dụng. | Actual dependency khi khai báo dưới `<dependencies>`. |
| `provided` | Cần khi compile nhưng môi trường deployment cấp runtime. | Vẫn là actual dependency; phải kiểm tra runtime provider. |
| `runtime` | Cần khi chạy, thường không cần compile API trực tiếp. | Vẫn là actual dependency. |
| `test` | Chỉ cho test compile/test runtime. | Vẫn là actual dependency trong phạm vi test. |
| `system` | Kiểu cũ dựa vào file local, kém tái lập. | Tránh dùng; có quy tắc resolution riêng. |
| `import` | Chỉ hợp lệ với `type=pom` trong `dependencyManagement`. | Nhập managed versions, **không đưa tất cả deps vào app**. |

**Không trộn “dependency được khai báo thật” với “dependency có mặt trên runtime classpath sản phẩm”.** Với mục tiêu của bài, điều quyết định tạo cạnh Reactor là một **quan hệ module được sử dụng thực sự**, chứ không phải chỉ có version metadata.

## 21. Transitive dependency không thay thế khai báo rõ ràng

Giả sử:

~~~text
consumer-app --> service-lib --> library-core
~~~

Nếu consumer chỉ trực tiếp phụ thuộc `service-lib`, Maven có thể giải quyết `library-core` qua transitive dependencies theo scope/optional/exclusion rules. Với một reactor chứa các module tương ứng, graph được xây từ những dependency đã tồn tại trong các POM thực, không phải từ managed entries chưa được dùng.

Nhưng nếu code của `consumer-app` **trực tiếp import một class thuộc `library-core`**, hãy cân nhắc khai báo `library-core` trực tiếp trong consumer:

~~~xml
<dependency>
    <groupId>vn.example.reactor</groupId>
    <artifactId>library-core</artifactId>
</dependency>
~~~

**Vì sao?** `service-lib` có thể đổi dependencies hoặc chuyển sang optional/excluded. Khi đó consumer sẽ mất classpath dù source vẫn cần core. Direct dependency giúp graph, ownership và hợp đồng của từng module minh bạch.

Đừng dùng `dependencyManagement` để “ép” một transitive library luôn xuất hiện khi nó vốn **không có đường dependency**. Management có thể chọn version cho một artifact trong graph, **không tạo đường đi mới từ hư vô**.

## 22. Maven phiên bản khác nhau và giới hạn minh họa

Bài tập dùng **Maven 3.x** để khai báo `<modules>`. Tài liệu Maven 4 có hướng dẫn riêng về **multi-subproject build**, bao gồm các thay đổi về mô hình root và cách thu thập subprojects. Tuy nhiên nguyên tắc chính **được Maven 4 tài liệu hóa tương tự**: Reactor sorting chỉ xét những instantiated references; `dependencyManagement` và `pluginManagement` không tự thay thứ tự.

Một số chi tiết có thể khác:

- Cách Maven 4 tìm root/subprojects khác Maven 3 trong một số cấu trúc repository.
- CLI flags và thông báo lỗi/build order có thể được mở rộng.
- Model validation ở bản Maven mới có thể nghiêm ngặt hơn.
- Parallel build hoặc selection semantics có thể ảnh hưởng tập project thực sự được chạy.

**Khi debug, luôn ghi `mvn --version` và dùng tài liệu đúng major version.** Không so một bản build Maven 3 với Maven 4 rồi kết luận chỉ từ thứ tự console log mà bỏ qua graph/selection khác nhau.

## 23. Anti-pattern: thay graph bằng scripts hoặc flags

### 23.1. Ép core bằng một script CI

~~~bash
mvn -pl :library-core install
mvn -pl :consumer-app verify
~~~

Đây là **mẫu script minh họa** có thể khiến ứng dụng build được nếu consumer đã có dependency thật và core được cài vào local repository, nhưng **không sửa thiếu khai báo dependency** nếu POM thực sự không có. Script còn tạo state trong `.m2` dễ che các lỗi resolution giữa các runner.

Nếu consumer cần core, hãy khai báo dependency và dùng:

~~~bash
mvn -B -ntp -pl :consumer-app -am clean verify
~~~

khi cả hai thuộc reactor.

### 23.2. Dùng `<modules>` như danh sách chạy tuần tự

Nếu thay `<modules>` chỉ để khiến output trông “đúng”, parallel reactor và `-pl -am` có thể làm lộ giả định sai. Cần ghi dependency thực.

### 23.3. Đặt `library-core` vào parent `<dependencies>` của mọi module

Cách này có thể lan thư viện và tạo quan hệ không cần thiết; thậm chí gây circular references trong một số mô hình parent/module. Cần đặt dependency vào child nào thật sự sử dụng nó.

### 23.4. Chỉ quản lý version rồi thử import class

Nếu consumer import class từ core nhưng chỉ parent có managed entry, compilation có thể fail dù `library-core` đã build trước tình cờ. **Order đúng không tự cấp classpath**.

### 23.5. Dùng `pluginManagement` để chạy plugin

Managed plugin version không đồng nghĩa plugin goal được bind vào lifecycle. Với một **plugin nội bộ** từ module khác, muốn có plugin-use relationship phải khai báo sử dụng ở build hoặc một lifecycle binding hợp lệ.

## 24. Lỗi thường gặp và cách đọc

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Module library nằm trong parent `dependencyManagement` nhưng app không tìm class | Không có actual dependency trong consumer. | Thêm dependency vào `consumer-app/pom.xml`; version từ management. |
| `-pl :consumer-app -am` không build `library-core` | Không có instantiated edge giữa hai module. | Xem `consumer-app/dependencies`, không chỉ parent management. |
| Maven build core sau app dù app “nên” cần core | Không khai báo dependency thực; `<modules>` chỉ fallback. | Thêm project dependency và chạy reactor sạch. |
| `dependencies.dependency.version is missing` | Child dùng dependency nhưng không có version trực tiếp hoặc management có hiệu lực. | Xem đúng parent/BOM/identity; quản lý version phù hợp. |
| Consumer compile lỗi sau khi xóa dependency | Code còn import API của core. | Khôi phục direct dependency thực hoặc xóa sự phụ thuộc trong code. |
| Core build trước app nhưng app vẫn không thấy class | Thứ tự build không cấp compile classpath. | Kiểm tra actual dependencies và scope. |
| Effective POM chứa tên core nhưng dependency tree không có | Tên chỉ nằm trong `dependencyManagement`. | Đọc riêng `project/dependencies`. |
| Quản lý phiên bản ở aggregator mà child không nhận | Aggregation khác inheritance. | Child phải có parent/import mechanism phù hợp. |
| Plugin nội bộ không được build trước consumer | Plugin chỉ có trong pluginManagement, chưa instantiated. | Xem plugin declaration trong `build/plugins`. |
| Parent POM build trước child nhưng hai siblings vẫn độc lập | Parent edge không tạo sibling edge. | Thêm dependency giữa đúng sibling khi cần. |
| `mvn -T 2` làm build fail ngẫu nhiên | Có shared files/process hoặc graph thiếu cạnh thật; plugin không thread-safe. | Khai báo dependency thật, cô lập output, kiểm tra plugin thread safety. |
| `mvn -pl` riêng lẻ không resolve sibling artifact | Upstream chưa được build/cài, hoặc graph/selection thiếu. | Dùng `-am` khi có dependency thật, kiểm tra resolution. |
| `dependency:tree` fail do artifact chưa có | Goal cần giải quyết artifacts. | Build full reactor trước, kiểm tra `.m2`, repository và GAV. |
| BOM import không giải quyết được | POM BOM chưa publish, cấu trúc vòng/cùng reactor không phù hợp. | Dùng BOM đã resolve được hoặc parent management đúng thiết kế. |
| Reactor sort báo cycle | Có chu trình project dependencies/parent/plugin references. | Bỏ thiết kế vòng, tách interface/common module hoặc sửa chiều phụ thuộc. |

**Đừng tự xóa toàn bộ cache hoặc đảo `<modules>` trước khi kiểm tra POM.** Hãy bắt đầu từ dependency thực sự trong consumer và effective model.

## 25. Checklist review một Maven multi-module repository

1. **Xác định aggregator:** module nào nằm trong `<modules>` và build root thật là đâu?
2. **Xác định parent:** child nào thừa hưởng root hoặc parent khác?
3. **Đọc `dependencyManagement`:** version nào được quản lý, entry nào chỉ là catalog?
4. **Đọc `project/dependencies`:** module nào thật sự yêu cầu class/artifact của module nào?
5. **Đọc plugin declarations/build extensions** nếu reactor có plugin nội bộ.
6. **Không suy ra cạnh từ `pluginManagement`/`dependencyManagement`**.
7. **Kiểm tra scope** để biết classpath compile/test/runtime của dependency đã khai báo.
8. **Kiểm tra graph không có cycle**, nhất là khi parent quản lý sibling dependencies.
9. **Đặt version tập trung**, nhưng để các child khai báo dependencies chúng thực sự cần.
10. **Dùng `-pl -am`** để xem tập upstream; dùng `-amd` cho dependents khi phù hợp.
11. **Chạy `help:effective-pom`** và đọc riêng managed/actual dependency sections.
12. **Chạy `dependency:tree`** sau khi có artifacts và phân biệt graph với catalog.
13. **Dùng CI build từ checkout sạch**, không dựa vào artifact cũ trong local repository.
14. **Kiểm tra `-T`** sau khi graph đúng; song song không được thay thế dependency declaration.
15. **Ghi Maven/JDK versions** trong build report để so hành vi chính xác.
16. **Kiểm chứng code sử dụng thư viện thật** bằng compile/test, không chỉ nhìn Reactor Build Order.
17. **Đừng đưa dependency vào parent `<dependencies>` đại trà** nếu nhiều child không cần.
18. **Không dùng BOM import từ sibling chưa có artifact** để tự tạo build-order.
19. **Nếu module được tách ra build riêng**, bảo đảm dependencies thật có thể được resolve từ reactor hoặc repository.
20. **Review thay đổi POM song song với source code**: import API mới thường cần dependency direct mới.

## 26. Bài tập củng cố

**Bài 1 — dựng trạng thái A.** Tạo đúng root POM và hai modules ở mục 6. Chạy `mvn -B -ntp clean verify`; quan sát consumer được liệt kê trước core khi không có sibling dependency và `<modules>` có consumer trước.

**Bài 2 — project selection.** Ở A, chạy `mvn -pl :consumer-app -am clean verify`; tìm xem library-core có nằm trong reactor selection không. Giải thích tại sao managed entry không kéo nó vào.

**Bài 3 — thay đổi duy nhất cần thiết.** Thêm direct dependency `library-core` vào consumer rồi đổi `App.java`/`AppTest.java` theo mục 8. Không thay root `dependencyManagement` hoặc `<modules>`. Chạy build và quan sát core trước consumer.

**Bài 4 — xác minh `-am`.** Ở B, chạy `mvn -pl :consumer-app -am clean verify`. Giải thích quan hệ upstream mà Maven đã phát hiện.

**Bài 5 — đối chiếu runtime.** Chạy main class của trạng thái A và B theo classpath tương ứng. Kiểm tra stdout **APP_STANDALONE** trước và **APP_WITH_CORE: ready** sau.

**Bài 6 — management không cấp classpath.** Ở B, trên nhánh thử nghiệm, xóa riêng dependency core trong consumer POM nhưng giữ import class trong App.java. Ghi lại compiler error và giải thích vì sao file JAR trong `.m2` không được tự thêm vào classpath.

**Bài 7 — parent vs aggregator.** Bỏ `<parent>` ở một child trong bản sao thử nghiệm và thêm groupId/version/Compiler configuration đầy đủ cần thiết. Thảo luận vì sao child có thể vẫn được aggregator thu thập nhưng không thừa hưởng dependencyManagement.

**Bài 8 — pluginManagement.** Tạo ví dụ tưởng tượng về một Maven plugin nội bộ ở module khác. So sánh chỉ quản lý plugin version tại parent với việc consumer khai báo plugin thật ở build/plugins.

**Bài 9 — dùng `-T`.** Sau khi hai project độc lập ở trạng thái A, bật `-T 2`. Giải thích vì sao thứ tự quan sát thời điểm chạy không phải hợp đồng; sau trạng thái B, core phải sẵn sàng trước phần consumer cần nó.

**Bài 10 — dự án thật.** Chọn một module cần class của module khác; vẽ graph từ `<dependencies>` và parent relationship, so sánh với managed catalog. Xác định entry nào dư thừa, edge nào thiếu và lệnh CI nào kiểm chứng đủ.

### Tổng kết

**`dependencyManagement` không tạo cạnh phụ thuộc thực thi vì nó không phải một lời tuyên bố rằng project đang dùng thư viện.** Nó quản lý version và metadata cho dependency **nếu dependency được kích hoạt bằng quan hệ thực sự**. Trong Maven Reactor, chỉ các **instantiated references** như project dependency, plugin được dùng, plugin dependency, build extension và parent relationship mới có thể ảnh hưởng thứ tự; `<modules>` chỉ cung cấp tập project và thứ tự fallback khi thiếu ràng buộc.

Để một module ứng dụng thực sự cần module thư viện, hãy khai báo dependency trong **`<dependencies>` của module ứng dụng**, còn version có thể để parent quản lý. Khi đó Reactor mới biết phải build thư viện trước ứng dụng và `-pl :consumer-app -am` mới kéo module cần thiết vào reactor selection. Đây là thiết kế đúng cả cho classpath, build-order lẫn khả năng bảo trì của dự án nhiều module.

### Tài liệu chính thức

- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Guide to Working with Multiple Subprojects (Maven 4)](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference: Dependency Management, Aggregation, Inheritance](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
