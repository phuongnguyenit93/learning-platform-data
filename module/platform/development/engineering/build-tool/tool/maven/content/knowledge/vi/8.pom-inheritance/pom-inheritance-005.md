# Phân biệt kế thừa cấu hình POM với tổng hợp mô-đun trong Maven

## 1. Hai cơ chế cùng xuất hiện trong nhiều dự án nhưng giải quyết hai bài toán khác nhau

Trong Maven, một dự án Java nhiều module thường có `pom.xml` ở thư mục gốc và các `pom.xml` nhỏ hơn bên trong từng module. Vì cả **kế thừa** (*POM inheritance*) và **tổng hợp** (*project aggregation*) có thể xuất hiện trong cùng một file gốc, người học dễ coi chúng là một tính năng. Thực tế, chúng độc lập về mục đích và hướng tham chiếu:

- **Kế thừa cấu hình:** POM con khai báo `<parent>` để nhận thông tin và chính sách build từ POM cha, sau khi Maven tổng hợp thành *effective POM*. Hướng quan hệ là **con → cha**.
- **Tổng hợp mô-đun:** POM tổng hợp khai báo `<modules>` để Maven biết những dự án con nào cần được thu thập và xây dựng trong một lần chạy **Reactor**. Hướng quan hệ là **bộ tổng hợp → các thư mục module**.

```text
KẾ THỪA (inheritance)                  TỔNG HỢP (aggregation)

app/pom.xml                            root/pom.xml
   │                                      │
   └─ <parent> ────> parent/pom.xml        ├─ <module>core</module> ──> core/pom.xml
                                          └─ <module>app</module> ───> app/pom.xml

"Cấu hình của ai được thừa hưởng?"     "Những dự án nào được build cùng lượt?"
```

Một cách kiểm tra nhanh: `<parent>` **không phải** lệnh “build module này từ root”; `<modules>` **không phải** lệnh “đưa dependency và plugin configuration xuống tất cả module”.

| Tiêu chí | Kế thừa POM | Tổng hợp mô-đun |
| --- | --- | --- |
| Khai báo chính | `<parent>` trong POM con | `<modules>` trong POM tổng hợp |
| Hướng tham chiếu | Con chỉ đến cha | Bộ tổng hợp liệt kê module |
| Mục tiêu | Chia sẻ cấu hình, quản lý version và chính sách build | Thu thập các project để build đồng thời theo thứ tự |
| Thành phần Maven phụ trách | Model builder/effective POM | Maven Reactor |
| Có tự tạo dependency giữa hai module? | Không | Không |
| Có tự cho module kế thừa `properties`/`pluginManagement`? | Có, theo quy tắc kế thừa POM | Không, chỉ vì được liệt kê trong `modules` |
| Có tự khiến lệnh tại root build hết module? | Không | Có, khi chạy build Reactor từ POM tổng hợp |
| Có thể dùng độc lập? | Có | Có |

**Điểm quan trọng nhất:** một dự án có thể vừa là **POM cha** vừa là **POM tổng hợp**, nhưng không bắt buộc phải là cả hai.

## 2. Cơ chế kế thừa POM: dùng `<parent>` để chia sẻ cấu hình

### 2.1. POM con chỉ ra POM cha như thế nào?

Một POM con có thể khai báo:

```xml
<parent>
    <groupId>edu.demo</groupId>
    <artifactId>learning-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Đây là **đoạn POM**, không phải một file XML hoàn chỉnh. Maven dùng bộ tọa độ `groupId:artifactId:version` để nhận diện parent; `relativePath` là vị trí để thử tìm file POM cha cục bộ. Giá trị mặc định của `relativePath` là `../pom.xml`, nhưng khai báo tường minh có thể giúp người đọc hiểu cấu trúc dự án.

Cha thường sử dụng `<packaging>pom</packaging>`. POM con có thể bỏ `groupId` và `version` nếu muốn kế thừa hai giá trị đó từ cha, nhưng **`artifactId` của con phải tự xác định** để mỗi dự án có định danh riêng.

Maven không chỉ sao chép XML theo kiểu văn bản. Nó dựng mô hình hiệu lực bằng việc kết hợp POM con, POM cha, Super POM, các mặc định và cấu hình hoạt động. Một số thuộc tính con có thể ghi đè cấu hình cha; plugin executions với id tương ứng được hợp nhất theo quy tắc Maven. Vì vậy, hãy dùng `help:effective-pom` để xem kết quả sau kế thừa thay vì suy luận chỉ bằng cách đọc vài dòng XML.

### 2.2. Những cấu hình thường được kế thừa

| Nội dung ở cha | Hành vi có ý nghĩa tại con |
| --- | --- |
| `groupId`, `version` | Con có thể nhận hai giá trị nếu không khai báo riêng |
| `properties` | Con dùng các thuộc tính như `maven.compiler.release`, có thể ghi đè khi phù hợp |
| `dependencyManagement` | Đặt phiên bản, scope hoặc thông tin quản lý mặc định cho dependency khi con thực sự khai báo sử dụng |
| `dependencies` | Dependency khai báo trực tiếp ở cha có thể được kế thừa thành dependency thực của con |
| `build/pluginManagement` | Quản lý version và configuration mặc định của plugin mà con sử dụng |
| `build/plugins` | Các khai báo plugin/execution có thể được kế thừa theo quy tắc và cờ `inherited` |
| `repositories`, các cấu hình build phù hợp | Có thể ảnh hưởng cách con phân giải artifact và thực thi build |
| `name`, `artifactId` | Không nên coi là định danh tự được con kế thừa nguyên trạng; con cần định nghĩa danh tính riêng |

Không phải mọi thứ có trong POM cha đều làm một việc ở mọi POM con. Ví dụ, khai báo một plugin dưới `pluginManagement` **không tự tạo execution mới cho một goal**. Tuy nhiên, khi một plugin đã được gọi bởi binding vòng đời mặc định hoặc được khai báo trong `plugins`, các cấu hình được quản lý có thể áp dụng cho plugin đó.

### 2.3. Phân biệt `dependencyManagement` và `dependencies`

Giả sử cha có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đoạn này **quản lý phiên bản**. Nó chưa khiến tất cả module có JUnit trên classpath. Module muốn dùng JUnit vẫn khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Maven điền phiên bản `5.10.2` từ dependency management đã kế thừa. Nếu thay vì `dependencyManagement`, cha đặt JUnit trong `<dependencies>`, các con có thể **kế thừa dependency thật** dù không cần. Đó thường là lý do nên quản lý thư viện chung ở `dependencyManagement` và để từng module tự quyết định có sử dụng hay không.

### 2.4. Phân biệt `pluginManagement` và `plugins`

Cha có thể quản lý Maven Compiler Plugin như sau:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Trong module `jar`, goal biên dịch thông thường đã được vòng đời mặc định gắn với compiler plugin; cấu hình `pluginManagement` có thể đặt version khi plugin đó được thực thi. Nhưng `pluginManagement` không phải yêu cầu “chạy một goal bất kỳ” cho tất cả module. Với plugin tùy chọn, cần plugin được khai báo/áp dụng và, nếu muốn tự chạy ở một phase, cần `executions` hoặc binding thích hợp.

Còn một plugin được khai báo trong `<build><plugins>` của cha có thể được kế thừa xuống con, bao gồm các execution được cấu hình trừ khi quy tắc/cờ kế thừa nói khác. Vì thế, không nên đặt mọi plugin thử nghiệm ở `plugins` của cha rồi mong chỉ một module sử dụng.

### 2.5. Parent POM được tìm ở đâu?

Nếu POM con khai báo `<parent>`, Maven cần giải quyết đúng POM cha. Với bố cục `root/pom.xml` và `root/app/pom.xml`, đường dẫn `../pom.xml` thường hợp lý. Nếu cha ở nơi khác, chỉ rõ `relativePath` thích hợp hoặc bảo đảm artifact POM cha có thể được giải quyết qua môi trường Maven/repository.

Khi parent nằm ở repository và không muốn Maven thử file POM ở đường dẫn cục bộ mặc định, có thể dùng:

```xml
<relativePath/>
```

Cách này **không biến parent thành module**. Nó chỉ tác động quá trình tìm POM cha. Nếu GAV cha không đúng, phiên bản cha chưa có trong repository được phép, hoặc `relativePath` trỏ tới POM có tọa độ không khớp, Maven có thể thất bại ngay ở giai đoạn dựng model, trước cả biên dịch.

## 3. Cơ chế tổng hợp mô-đun: dùng `<modules>` để tổ chức Reactor

### 3.1. POM tổng hợp liệt kê đường dẫn đến những dự án nào?

Một POM ở root có thể viết:

```xml
<packaging>pom</packaging>

<modules>
    <module>core</module>
    <module>app</module>
</modules>
```

Đây là **đoạn cấu hình** trong POM root. Mỗi `<module>` là **đường dẫn tương đối tới thư mục module**, tại đó Maven tìm POM con. Nó không phải `groupId` hoặc `artifactId`. Ví dụ `<module>core</module>` hướng tới `root/core/pom.xml`.

Maven Reactor thu thập những dự án được tổng hợp, xác định quan hệ giữa chúng, sắp xếp thứ tự hợp lý rồi build các dự án được chọn. Chạy tại root:

```bash
mvn clean verify
```

Maven thường xây POM root cùng các module được chọn. Root có `packaging=pom` nên không tự tạo JAR ứng dụng như module `jar`. Những module vẫn có lifecycle, dependency và plugin riêng theo POM hiệu lực của chúng.

**Khai báo `modules` không tạo classpath giữa các module.** Nếu `app` cần lớp ở `core`, `app` phải khai báo dependency vào artifact `core`. Được liệt kê cùng trong `modules` chỉ đảm bảo Maven biết cả hai khi xây Reactor; bản thân nó không khiến `app` import được lớp ở `core`.

### 3.2. Reactor sắp xếp thứ tự không chỉ bằng vị trí trong `modules`

Maven nhìn vào những quan hệ thực tế giữa các dự án: dependency của project vào module khác, plugin hoặc plugin dependency được cung cấp bởi module khác, build extension, quan hệ parent nằm trong Reactor; thứ tự khai báo `modules` chỉ là căn cứ dự phòng khi không có quy tắc ưu tiên hơn.

Ví dụ:

```text
app ── dependency edu.demo:core:1.0.0 ──> core
```

Dù POM root liệt kê `app` trước `core`, Reactor vẫn phải chọn thứ tự đủ để xây `core` trước khi `app` cần dependency của nó. **Chỉ đặt `core` trong `dependencyManagement` không tạo một quan hệ dependency để Reactor sắp xếp**; `app` cần thực sự khai báo `<dependency>`.

### 3.3. Các tùy chọn Reactor quan trọng

| Lệnh tại root | Ý nghĩa |
| --- | --- |
| `mvn verify` | Thực thi đến `verify` cho các project trong Reactor được lựa chọn mặc định |
| `mvn -pl :app verify` | Chọn project có `artifactId=app`; không tự thêm dependency đang thiếu |
| `mvn -pl :app -am verify` | Chọn `app` và các project cần thiết làm dependency trong Reactor |
| `mvn -pl :core -amd verify` | Chọn `core` và các project trong Reactor phụ thuộc vào nó |
| `mvn -N validate` | Không đi đệ quy các module; xử lý project hiện tại |
| `mvn -f app/pom.xml verify` | Sử dụng trực tiếp POM của `app`; không tự động có Reactor của root |

`-pl` là `--projects`; `-am` là `--also-make`; `-amd` là `--also-make-dependents`; `-N` là `--non-recursive`. Ví dụ dùng ký hiệu `:app` để chọn theo `artifactId`, không phải đường dẫn thư mục. Trong các phiên bản Maven và project phức tạp, lựa chọn module còn chịu tác động quan hệ parent, plugin/extension và cấu trúc Reactor thực tế; nên xem danh sách project trong log thay vì tự suy đoán số module.

Một module được tổng hợp có thể kế thừa từ parent **khác** với POM root. Và một module có thể kế thừa root dù không được root liệt kê để build trong Reactor.

## 4. Ví dụ Java 17 chạy được: root vừa là parent, vừa là aggregator

Ta sẽ tạo ba POM: một POM gốc để chia sẻ cấu hình và tổng hợp; một module thư viện `core`; một module ứng dụng `app` phụ thuộc vào `core`. Mã Java chạy được trên Java 17 trở lên với Maven tương thích và quyền tải dependency/plugin từ repository phù hợp.

### 4.1. Cấu trúc dự án

```text
learning-parent/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/main/java/edu/demo/core/Greeter.java
└── app/
    ├── pom.xml
    ├── src/main/java/edu/demo/app/Application.java
    └── src/test/java/edu/demo/app/ApplicationTest.java
```

Tất cả thư mục nguồn dùng quy ước Maven. Mỗi lớp Java có `package` tương ứng với cây thư mục. Root chỉ là dự án `pom`; `core` và `app` là dự án `jar` (mặc định nếu không khai báo packaging).

### 4.2. Root `pom.xml` — đồng thời làm hai vai trò

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>learning-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.10.2</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.version}</version>
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
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Chỉ ra chính xác hai mục đích trong cùng POM:

- `<modules>` + `packaging=pom`: root là **aggregator**, giúp Maven Reactor thấy `core` và `app`.
- `properties`, `dependencyManagement` và `pluginManagement`: root là **parent cấu hình** mà các module sẽ kế thừa **chỉ khi** POM của chúng khai báo `<parent>` tương ứng.

`maven.compiler.release=17` và version compiler plugin làm ví dụ hướng tới Java 17. `junit.version` quản lý dependency test nhưng chưa tự thêm JUnit vào mọi module. Version Maven Compiler/Surefire được chỉ định để tránh dựa vào plugin version mặc định biến động. Chúng được dùng bởi các binding tiêu chuẩn của dự án `jar` khi phù hợp.

### 4.3. Module `core/pom.xml` — kế thừa từ root

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>learning-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
</project>
```

`core` không ghi lại `groupId` và `version` vì kế thừa từ parent. Nó cũng nhận cấu hình biên dịch Java 17. File này không có `<modules>`, cũng không cần tự liệt kê `app`.

Tệp `core/src/main/java/edu/demo/core/Greeter.java`:

```java
package edu.demo.core;

public final class Greeter {
    private Greeter() {
    }

    public static String message(String name) {
        return "Hello, " + name;
    }
}
```

Lớp `Greeter` không biết gì về Maven Reactor. Nó chỉ là mã Java sản phẩm được biên dịch thành `core/target/classes/edu/demo/core/Greeter.class` khi build module `core`.

### 4.4. Module `app/pom.xml` — vừa kế thừa, vừa khai báo dependency thực vào `core`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>learning-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>edu.demo</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Hai điểm cần chú ý:

1. Dependency `edu.demo:core:1.0.0` **được khai báo ở module `app`**. Chính quan hệ dependency thực này khiến Maven cung cấp lớp của `core` cho `app` khi biên dịch và xác định thứ tự Reactor, chứ không phải vì root liệt kê hai module.
2. Dependency `junit-jupiter` không ghi `version` vì phiên bản `5.10.2` đến từ `dependencyManagement` của parent. Việc JUnit xuất hiện trên test classpath là do `app` **có khai báo dependency**, không phải vì dependency đã được quản lý ở parent.

Giá trị `${project.version}` trong POM ứng với phiên bản hiện tại của module `app` sau khi kế thừa parent, tức `1.0.0` trong ví dụ. Khi dùng version riêng giữa module, phải chọn version của `core` đúng thực tế; không luôn dùng `${project.version}` nếu chúng không đồng phiên bản.

Tệp `app/src/main/java/edu/demo/app/Application.java`:

```java
package edu.demo.app;

import edu.demo.core.Greeter;

public final class Application {
    private Application() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.message("Maven"));
    }
}
```

Tệp `app/src/test/java/edu/demo/app/ApplicationTest.java`:

```java
package edu.demo.app;

import edu.demo.core.Greeter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ApplicationTest {
    @Test
    void greetsMaven() {
        assertEquals("Hello, Maven", Greeter.message("Maven"));
    }
}
```

JUnit Jupiter được dùng bởi Surefire thông qua plugin đã được quản lý version. Test chỉ kiểm tra kết quả thuần của phương thức nên không phụ thuộc mạng hoặc thứ tự chạy; tên `ApplicationTest` phù hợp mẫu phát hiện test thông thường của Surefire.

### 4.5. Build và chứng minh hai cơ chế cùng hoạt động

Từ thư mục `learning-parent/`, chạy:

```bash
mvn clean verify
```

Maven sẽ dựng Reactor từ root và hai module, chọn thứ tự phù hợp. `core` được biên dịch và đóng gói trước khi `app` cần dependency của nó; `app` biên dịch cả mã chính và mã test, rồi Surefire chạy **1 bài test thành công** khi môi trường và mã đúng như ví dụ.

Các đầu ra quan trọng:

```text
core/target/classes/edu/demo/core/Greeter.class
core/target/core-1.0.0.jar
app/target/classes/edu/demo/app/Application.class
app/target/test-classes/edu/demo/app/ApplicationTest.class
app/target/surefire-reports/...
app/target/app-1.0.0.jar
```

Để chạy trực tiếp các lớp đã biên dịch sau build mà không cần tạo executable/fat JAR, dùng classpath gồm **cả hai module**.

Linux/macOS:

```bash
java -cp "app/target/classes:core/target/classes" edu.demo.app.Application
```

Windows PowerShell:

```powershell
java -cp "app\target\classes;core\target\classes" edu.demo.app.Application
```

Stdout chính xác của lệnh Java này:

```text
Hello, Maven
```

Trong ví dụ trên, `app-1.0.0.jar` chỉ là JAR thông thường và không tự gói mọi dependency; chưa cấu hình manifest `Main-Class`. Vì vậy không nên mặc định lệnh `java -jar app/target/app-1.0.0.jar` sẽ chạy được. Phần cần hiểu ở đây là **kế thừa cấu hình biên dịch/test** và **Reactor phân giải dependency giữa module**, chứ không phải tạo JAR độc lập.

Có thể chọn xây `app` và những module mà `app` phụ thuộc vào:

```bash
mvn -pl :app -am verify
```

`-am` giúp đưa project phụ thuộc như `core` vào build. Nếu chỉ chạy `mvn -pl :app verify` từ trạng thái không có artifact `core` phù hợp trong local repository, dependency có thể không được giải quyết vì `core` không được thêm vào tập build. Nếu chạy riêng POM `app` mà không dùng Reactor, artifact `core` cũng cần sẵn trong repository hoặc cần được cài đặt trước.

## 5. Trường hợp chỉ kế thừa, không tổng hợp

Một công ty có thể công bố parent POM chứa quy tắc Java version, plugin version, dependency version và chất lượng build tại repository artifact. Nhiều dự án hoàn toàn khác thư mục/repository có thể cùng khai báo:

```xml
<parent>
    <groupId>com.example.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>2.0.0</version>
    <relativePath/>
</parent>
```

Đây là **mẫu minh họa tọa độ parent giả định**, không phải artifact đã có sẵn để tải. Nếu POM cha không có `<modules>` trỏ tới các dự án đó, việc kế thừa **không** làm lệnh `mvn verify` ở repository của parent tự đi build tất cả dự án kế thừa.

Một biến thể ở cùng repository: root `pom.xml` có `packaging=pom` và các quy tắc build, còn `app/pom.xml` khai báo parent `../pom.xml`. Nếu root **không** khai báo `<modules>`, khi đứng ở root và chạy `mvn verify`, Maven không tự “khám phá” `app` để build; cần chạy từ `app` hoặc dùng `mvn -f app/pom.xml verify`. Parent relation không thay thế việc đăng ký module trong Reactor.

Dùng mô hình **parent riêng** khi muốn chia sẻ chuẩn build giữa nhiều ứng dụng, kể cả các ứng dụng không cần release hoặc build cùng nhau. Parent POM thường có vòng đời phát hành độc lập với module tiêu thụ.

## 6. Trường hợp chỉ tổng hợp, không kế thừa

Một root có thể chỉ tập hợp những dự án cần build cùng lượt:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>suite-reactor</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>service</module>
        <module>client</module>
    </modules>
</project>
```

Đây là POM tổng hợp hoàn chỉnh về cấu trúc cơ bản, **không tự cho `service` và `client` kế thừa `groupId`, `version` hay plugin version của nó**. Hai module phải có POM hợp lệ của riêng mình; chúng có thể khai báo parent ở repository bên ngoài, một parent khác trong cây thư mục, hoặc không có parent cụ thể ngoài Super POM.

Ví dụ POM `service` tối giản không kế thừa `suite-reactor`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.services</groupId>
    <artifactId>service</artifactId>
    <version>4.2.0</version>
</project>
```

Root vẫn có thể xây dự án `service` trong Reactor vì đường dẫn `<module>service</module>` trỏ tới nó. Nhưng nếu root thêm `<properties><maven.compiler.release>17</maven.compiler.release></properties>`, `service` **không tự được thừa hưởng** thuộc tính đó, bởi POM `service` không khai báo root là parent.

Mô hình này phù hợp khi cần một lệnh điều phối nhiều dự án độc lập với chu kỳ phát hành hoặc chính sách parent khác nhau.

## 7. Parent, aggregator và dependency là ba mối quan hệ riêng

Một sơ đồ ghép đủ ba loại quan hệ cho ví dụ ở phần 4:

```text
                 learning-parent/pom.xml
                    /            \
             modules:core      modules:app
                 │                  │
           core/pom.xml        app/pom.xml
                 │                  │
                 └── parent ↑  ↑ parent ┘
                    (cùng kế thừa learning-parent)

           app -- dependency edu.demo:core:1.0.0 --> core
```

Các đường trên có ý nghĩa khác nhau:

- **Parent:** POM nào cung cấp chính sách và cấu hình dùng chung?
- **Module:** Những project nào được root nhận diện để cùng chạy trong một Reactor?
- **Dependency:** Artifact nào cần xuất hiện trên compile/runtime/test classpath của một project khác?

Không thể thay `<dependency>` bằng `<module>` hoặc `<parent>` để đưa lớp `Greeter` lên classpath của `app`. Và dù `app` có dependency vào artifact `core`, Maven không cần cả hai ở cùng một repository nguồn; dependency có thể được lấy từ local/remote artifact repository mà không cần Reactor build chung. Reactor chỉ giúp xây đồng thời **khi các project tương ứng có mặt và được chọn**.

## 8. Kế thừa POM không giống import BOM

Maven còn cho phép import một POM kiểu BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>dependency-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là ví dụ tọa độ BOM giả định. BOM giúp **nhập bộ quy tắc quản lý dependency**, không tương đương `<parent>`: nó không tự làm dự án kế thừa toàn bộ plugin configuration, properties hay thông tin parent. Một dự án chỉ có **một parent trực tiếp** trong `<parent>`, nhưng có thể áp dụng các danh sách dependency management phù hợp từ BOM khi cấu hình đúng.

BOM cũng không phải aggregator và không tự xây các module được nêu ở nơi khác. Phân biệt cả ba giúp thiết kế cấu trúc tổ chức lớn mà không bắt mọi dự án sử dụng cùng một parent POM.

## 9. Kiểm tra cấu hình thực tế thay vì suy đoán

### 9.1. Xem effective POM của module

Sau khi tạo cấu trúc ví dụ, có thể chạy từ root:

```bash
mvn -f app/pom.xml help:effective-pom
```

Lệnh này yêu cầu Maven Help Plugin in effective POM của `app`. Khi xem, tìm `groupId` và `version` đã kế thừa, `maven.compiler.release`, `dependencyManagement`, `pluginManagement`, cùng dependency `core` và JUnit thực sự trong `dependencies`. Có thể truyền tùy chọn `-Doutput=...` khi dùng version Help Plugin hỗ trợ để ghi tệp nhằm so sánh; không cần chỉnh nội dung POM nguồn chỉ để xem kết quả.

Nếu trong effective POM không thấy cấu hình dự kiến, kiểm tra parent GAV, `relativePath`, profile hoạt động, định nghĩa override và version plugin đang dùng. Đừng kết luận parent đúng chỉ vì hai file có tên giống nhau.

### 9.2. Xem Maven Reactor đã chọn những dự án nào

Chạy ở root:

```bash
mvn validate
mvn -N validate
mvn -pl :app -am validate
```

Với root aggregator, lệnh đầu đi qua các project thuộc Reactor; lệnh thứ hai chỉ ở project gốc; lệnh thứ ba chọn app và những project cần xây kèm theo trong Reactor. Kiểm tra `Reactor Build Order` và phần tổng kết khi Maven in ra, thay vì đoán thứ tự chỉ qua vị trí trong `<modules>`.

Nếu module phụ thuộc vào artifact bên ngoài Reactor, `-am` không tự sao chép dự án ngoài vào Reactor. Maven vẫn cần giải quyết artifact đó theo cơ chế repository bình thường.

### 9.3. Chẩn đoán khi con không giải quyết được parent

Các triệu chứng thường là thông báo kiểu `Non-resolvable parent POM` hoặc nhận nhầm POM tại `../pom.xml`. Kiểm tra:

- `groupId:artifactId:version` trong `<parent>` có khớp parent thực tế không?
- `relativePath` có trỏ đúng file và đúng tọa độ không?
- Khi dùng `<relativePath/>`, artifact parent đã có trong repository được phép chưa?
- Nếu version parent là snapshot hoặc repository nội bộ, chính sách repository và credential đã đúng chưa?
- Có đang chạy từ vị trí không có POM/đang dùng `-f` trỏ nhầm project không?

Lỗi tìm parent xảy ra ở giai đoạn dựng project model, khác với lỗi build dependency Java. Sửa nhầm sang `<modules>` không chữa được trường hợp parent GAV sai.

## 10. Các lỗi và hiểu lầm phổ biến

| Hiểu lầm hoặc triệu chứng | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Root có `modules` nên con thừa hưởng tất cả plugin version.” | Aggregation không tạo quan hệ parent | Thêm `<parent>` phù hợp trong con hoặc quản lý cấu hình tại parent thực sự |
| “Con khai báo parent nên chạy `mvn verify` ở parent sẽ build con.” | Inheritance không đăng ký con vào Reactor | Thêm `<modules>` hoặc build từng dự án |
| “Hai module trong cùng Reactor nên `app` import được lớp của `core`.” | Reactor không thay thế dependency trên classpath | Khai báo `<dependency>` vào `core` ở `app` |
| “Đặt dependency ở `dependencyManagement` thì mọi module dùng dependency.” | Management chỉ cung cấp quy tắc khi dependency được khai báo | Module nào cần dependency thì khai báo ở `dependencies` |
| “Đặt plugin dưới `pluginManagement` thì goal luôn tự chạy.” | Không tự tạo execution cho goal tùy ý | Khai báo plugin/execution hoặc dùng binding vòng đời đã có |
| “Maven xây theo thứ tự liệt kê `modules` dù `app` phụ thuộc `core`.” | Reactor ưu tiên quan hệ dependency và các liên kết thực | Để Maven sắp xếp; xác minh log Reactor |
| “`<module>core</module>` nghĩa là artifactId phải là `core`.” | Giá trị module là đường dẫn thư mục tương đối | Đọc `core/pom.xml` để lấy định danh thực |
| “Parent có `packaging=pom` là tự động aggregator.” | Parent có thể chia sẻ cấu hình mà không khai báo module nào | Chỉ dùng `<modules>` khi cần xây cùng một Reactor |
| “`-pl :app` sẽ tự kéo `core` vào build.” | `-pl` chỉ chọn project, khác `-am` | Dùng `-am` khi cần build project phụ thuộc trong Reactor |
| “`mvn -N verify` sẽ build module như thường.” | `-N` tắt đệ quy Reactor của aggregator | Bỏ `-N` khi muốn build module |
| “Root và module cùng `groupId/version` nên chắc chắn có quan hệ parent.” | Trùng tọa độ thành phần không phải quan hệ kế thừa | Kiểm tra `<parent>` trong POM con |

Một lỗi nghiêm trọng khác là đưa dependency test vào `<dependencies>` của parent POM mà không cân nhắc mọi module sẽ thừa hưởng dependency đó. Tốt hơn là quản lý version trong `dependencyManagement`, rồi chỉ khai báo dependency thật tại module cần dùng.

## 11. Quy tắc thiết kế thực tế

**Chọn parent khi:** nhiều project cần chung Java release, encoding, plugin/dependency version, quy tắc kiểm tra chất lượng hoặc policy build. Các project có thể nằm ở repository khác nhau và không cần build cùng nhau.

**Chọn aggregator khi:** các project nằm trong một cấu trúc nguồn và cần xây dựng/kiểm tra đồng thời, đặc biệt khi có dependency giữa module, để Reactor sắp xếp thứ tự và CI có thể chạy từ một entry point.

**Chọn cả hai khi:** repository nhiều module cần **vừa** chia sẻ cấu hình **vừa** build cùng một lượt. Đây là mô hình thường gặp: root có `packaging=pom` và `modules`, còn mỗi module có `parent` trỏ về root. Tuy nhiên, không có điều kiện Maven nào bắt buộc hai vai trò phải thuộc cùng một POM nếu hệ thống có thiết kế phân tầng khác.

Để bàn giao một cấu trúc Maven nhiều module có thể kiểm chứng được:

1. Mở từng POM con để xác định **parent GAV** và `relativePath`.
2. Mở POM aggregator để xác định **danh sách đường dẫn module**.
3. Kiểm tra từng dependency nội bộ có được **khai báo thật** ở dự án tiêu thụ không.
4. Dùng `mvn -f app/pom.xml help:effective-pom` để xem cấu hình sau kế thừa.
5. Chạy `mvn clean verify` từ aggregator để kiểm tra build đa module và báo cáo test.
6. Thử `mvn -pl :app -am verify` để xác nhận quan hệ nội bộ và hành vi chọn dự án.
7. Đối chiếu artifact/test thực tế, tránh đánh giá chỉ từ việc Maven trả về mã thoát 0 nếu các bước quan trọng đã bị skip.

**Ghi nhớ một câu:** `<parent>` trả lời **“Con lấy cấu hình từ đâu?”**, `<modules>` trả lời **“Root cùng build những dự án nào?”**, còn `<dependencies>` trả lời **“Một dự án cần artifact nào để biên dịch/chạy?”**. Ba quan hệ này phối hợp với nhau, nhưng không thể thay thế nhau.

### Tài liệu chính thức

- [Apache Maven — Introduction to the POM: Project Inheritance vs Project Aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Guide to Working with Multiple Modules và Reactor Sorting](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to the Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
