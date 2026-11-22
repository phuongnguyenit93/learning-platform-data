# Phân biệt build trong reactor với tiêu thụ artifact đã install

## 1. Tổng quan: hai ngữ cảnh Maven hoàn toàn khác nhau

Khi phát triển **Reactor nhiều mô-đun** trong Maven, bạn có thể build module `app` dùng mã của module `core` mà **không cần chạy `mvn install` trước**. Nhưng một dự án Maven độc lập dùng cùng dependency `core` có thể thất bại với lỗi `Could not find artifact`, dù file JAR của core đã nằm trong `target/`.

Không có mâu thuẫn. Cần phân biệt:

1. **Build trong reactor:** Maven thu thập các modules tham gia **cùng một Maven invocation**, sắp xếp thứ tự theo dependency graph và phân giải output/artifact từ những reactor projects đang được build. Nó không đòi mỗi upstream module phải install trước khi downstream module compile.
2. **Tiêu thụ artifact từ repository:** Maven project bên ngoài invocation đó phân giải dependency theo GAV qua local/remote Maven repository đã cấu hình. Nó không tự tìm một JAR tùy ý trong thư mục `target` của một source project ở gần.
3. **Install:** phase `install` cài binary artifact/POM/attachments đủ điều kiện vào Maven local repository để Maven projects khác tìm theo GAV.
4. **Deploy:** phase `deploy` có thể đưa artifacts lên remote repository được cấp quyền để những môi trường khác sử dụng.

```text
KỊCH BẢN A: BUILD TRONG REACTOR

reactor-lab/pom.xml
   |-- greeting-core
   +-- greeting-cli  --dependency--> greeting-core

mvn -f reactor-lab/pom.xml clean verify
   |
   +-- reactor biết cả hai projects
   +-- core build trước cli theo dependency
   +-- cli resolve core từ cùng reactor build
   +-- KHÔNG bắt buộc install core vào local repository


KỊCH BẢN B: CONSUMER NGOÀI REACTOR

external-client/pom.xml
   |
   +-- dependency: dev.learning:greeting-core:1.0.0-SNAPSHOT

mvn -f external-client/pom.xml clean package
   |
   +-- core không có trong reactor của lệnh này
   +-- Maven tìm GAV từ local/remote repositories
   +-- chưa có artifact -> có thể FAIL
   +-- đã có artifact -> dùng bản tìm được, có thể là bản cũ
```

**Không nên nói “consumer ngoài reactor luôn phải chạy install”.** Nếu artifact đã publish ở remote repository, Maven có thể tải nó trực tiếp. Cốt lõi là **artifact có được phân giải bằng repository system hay không**, và nó có phải version/build bạn muốn không.

Bài sử dụng Maven **3.9.x**, Java **17**, JUnit Jupiter **5.11.4** và plugin versions được ghim để tạo ví dụ độc lập. Không coi các versions này là mới nhất trong mọi thời điểm.

## 2. Reactor thu thập, sắp xếp và build modules

Theo tài liệu Maven 3, reactor có ba việc:

- **Collect:** lấy danh sách projects/modules cần build.
- **Sort:** dựa trên quan hệ dependency/parent/plugin để xác định thứ tự.
- **Build:** chạy lifecycle phases/goals của các projects được chọn.

Một quan hệ project dependency thật từ `greeting-cli` tới `greeting-core` sẽ khiến Core được build trước CLI. Điều này đúng ngay cả khi root POM liệt kê CLI trước Core trong `<modules>`.

```text
Thứ tự root <modules>:
  1. greeting-cli
  2. greeting-core

Quan hệ:
  greeting-cli ---> greeting-core

Reactor Build Order:
  maven-reactor-lab (parent/aggregator)
  greeting-core
  greeting-cli
```

Một số quan hệ khác cũng ảnh hưởng sort: parent project trong reactor, plugin artifact nằm trong reactor, plugin dependency hoặc build extension khi được khai báo thực tế. Nếu không có ràng buộc khác, thứ tự `<modules>` có thể được dùng.

**Chỉ có `dependencyManagement` hoặc `pluginManagement` không tạo ra sorting edge.** Chúng chỉ cung cấp metadata/versions khi dependency hoặc plugin tương ứng thực sự được dùng.

### 2.1. Aggregator không đồng nghĩa parent

| Vai trò | XML chính | Công dụng |
| --- | --- | --- |
| Aggregator | `<modules>` | Thu thập modules để reactor build |
| Parent POM | `<parent>` | Cho child kế thừa GAV, properties và management |
| Dependency | `<dependencies>` | Đưa dependency lên classpath và tạo quan hệ resolution |
| Dependency management | `<dependencyManagement>` | Quản lý versions/scope, không tự thêm dependency |
| Plugin management | `<pluginManagement>` | Quản lý plugin version/config, không tự làm plugin chạy |
| Parent packaging | `<packaging>pom</packaging>` | Thường dùng cho aggregator/parent |

Parent và aggregator **có thể là cùng một project nhưng không bắt buộc**. Trong ví dụ, root làm cả hai vai trò. Một module kế thừa parent không tự import classes của sibling module; module cần khai báo dependency tới sibling nếu muốn dùng API của nó.

### 2.2. Reactor không tạo repository lưu vĩnh viễn

Trong cùng invocation, Maven resolver có thể sử dụng reactor projects, output classes và artifact đã được tạo theo phase phù hợp. Nhưng reactor **không phải** một Maven repository server hoặc một bước install ngầm.

Sau `mvn verify`, file `core/target/core.jar` có thể tồn tại, nhưng GAV của core **không tự được cài vào `~/.m2/repository`**. Vì thế một Maven process khác chạy ngoài reactor vẫn phải phân giải dependency theo repository system bình thường.

## 3. Các Maven lifecycle phases liên quan

| Lệnh | Điều diễn ra chính |
| --- | --- |
| `mvn compile` | Tạo classes tại `target/classes` |
| `mvn test` | Compile/chạy tests theo plugins đã cấu hình |
| `mvn package` | Đóng gói JAR/WAR vào `target/` |
| `mvn verify` | Kiểm tra build tới phase verify; **không tự install** |
| `mvn install` | Cài artifact và POM vào Maven local repository |
| `mvn deploy` | Xuất bản lên remote repository theo cấu hình và quyền |

Local repository mặc định thường là:

```text
~/.m2/repository/
```

Nhưng có thể đổi qua `settings.xml` hoặc system property `-Dmaven.repo.local`. Hai Maven invocations dùng **hai local repository paths khác nhau** sẽ không đương nhiên thấy cùng artifact đã install.

GAV của Core trong ví dụ là:

```text
groupId    = dev.learning
artifactId = greeting-core
version    = 1.0.0-SNAPSHOT
type       = jar
```

Sau install vào repository mặc định, Maven có thể tạo:

```text
~/.m2/repository/dev/learning/greeting-core/1.0.0-SNAPSHOT/
    greeting-core-1.0.0-SNAPSHOT.jar
    greeting-core-1.0.0-SNAPSHOT.pom
    maven-metadata-local.xml
```

Một consumer tìm theo GAV **không tự duyệt mọi `target/` trên ổ đĩa**. Nó phải tìm đúng tọa độ qua hệ thống repositories.

## 4. Ví dụ trọn vẹn: hai Maven modules và consumer độc lập

Tạo cây sau trong một workspace tự chọn:

```text
workspace-lab/
├── reactor-lab/
│   ├── pom.xml
│   ├── greeting-core/
│   │   ├── pom.xml
│   │   └── src/
│   │       ├── main/java/dev/learning/core/Greeter.java
│   │       └── test/java/dev/learning/core/GreeterTest.java
│   └── greeting-cli/
│       ├── pom.xml
│       └── src/
│           ├── main/java/dev/learning/cli/App.java
│           └── test/java/dev/learning/cli/AppTest.java
└── external-client/
    ├── pom.xml
    └── src/main/java/dev/consumer/ConsumerApp.java
```

**external-client là sibling của reactor-lab, không phải module của reactor-lab.** Không đưa nó vào root `<modules>`, vì toàn bộ mục tiêu là chứng minh một consumer thực sự nằm ngoài reactor invocation.

Các bản POM dưới đây dùng đúng Java 17, test dependencies chỉ ở scope test, version plugins rõ ràng.

### 4.1. Root aggregator/parent — reactor-lab/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning</groupId>
    <artifactId>maven-reactor-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <!-- Cố tình đặt CLI trước Core để quan sát sorting -->
        <module>greeting-cli</module>
        <module>greeting-core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.learning</groupId>
                <artifactId>greeting-core</artifactId>
                <version>1.0.0-SNAPSHOT</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

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
                    <version>3.5.2</version>
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

Root `packaging=pom` vừa thu thập modules, vừa là parent. `<dependencyManagement>` chứa version Core và JUnit, nhưng **không tạo dependency Core trong CLI** nếu CLI không khai báo nó.

### 4.2. Module Core — greeting-core/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.learning</groupId>
        <artifactId>maven-reactor-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
```

Module kế thừa groupId/version, compiler release và pluginManagement từ parent. Dependency JUnit Jupiter được khai báo thật, còn version/scope được quản lý ở root.

### 4.3. Module CLI — greeting-cli/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.learning</groupId>
        <artifactId>maven-reactor-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.learning</groupId>
            <artifactId>greeting-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
```

Dependency Core **được khai báo trong `<dependencies>`**, nên CLI có quyền compile code sử dụng public class của Core. Version Core vắng mặt ở đây vì root dependencyManagement đã định nghĩa nó. Đây chính là quan hệ Maven dùng để sắp Core trước CLI.

## 5. Mã Java 17 và kiểm thử

### 5.1. Greeter.java của Core

Tạo `reactor-lab/greeting-core/src/main/java/dev/learning/core/Greeter.java`:

```java
package dev.learning.core;

public final class Greeter {
    private Greeter() {
    }

    public static String say(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên không được để trống");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Mã chỉ dùng Java 17 Standard Library.

### 5.2. GreeterTest.java

Tạo `reactor-lab/greeting-core/src/test/java/dev/learning/core/GreeterTest.java`:

```java
package dev.learning.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {
    @Test
    void formatsName() {
        assertEquals("Xin chào, Lan!", Greeter.say(" Lan "));
    }

    @Test
    void rejectsBlank() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeter.say("  "));
    }

    @Test
    void rejectsNull() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeter.say(null));
    }
}
```

Core có **3 unit tests**.

### 5.3. App.java của CLI

Tạo `reactor-lab/greeting-cli/src/main/java/dev/learning/cli/App.java`:

```java
package dev.learning.cli;

import dev.learning.core.Greeter;

public final class App {
    private App() {
    }

    public static String render(String name) {
        return "CLI: " + Greeter.say(name);
    }

    public static void main(String[] args) {
        System.out.println(render(" Lan "));
    }
}
```

Lệnh import Core yêu cầu có Core trên classpath. Trong reactor, Maven cung cấp đầu ra từ module Core; ngoài reactor, dependency phải có trong repository hoặc classpath được cấp bằng cách khác.

### 5.4. AppTest.java

Tạo `reactor-lab/greeting-cli/src/test/java/dev/learning/cli/AppTest.java`:

```java
package dev.learning.cli;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void rendersUsingCore() {
        assertEquals("CLI: Xin chào, Lan!",
                App.render(" Lan "));
    }
}
```

CLI có **1 unit test**. Tổng reactor: **4 lượt test** ở hai modules.

## 6. Build full reactor — chỉ tới verify

Đứng tại `workspace-lab`:

```bash
mvn -version
mvn -f reactor-lab/pom.xml clean verify
```

Nếu Maven/JDK hợp lệ, repository có plugin/JUnit cần thiết và source files đúng:

1. Maven thu thập root + Core + CLI.
2. Core được build trước CLI theo dependency graph (dù root liệt kê CLI trước).
3. Core chạy **3 tests**, tạo Core JAR.
4. CLI compile/test với Core từ reactor, chạy **1 test**, tạo CLI JAR.
5. Reactor Summary báo các modules thành công.

Các dòng log đại diện:

```text
[INFO] Building maven-reactor-lab 1.0.0-SNAPSHOT
[INFO] Building greeting-core 1.0.0-SNAPSHOT
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
[INFO] Building greeting-cli 1.0.0-SNAPSHOT
[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
```

Đây là **minh họa số liệu và thứ tự**, không phải full Maven log.

File outputs:

```text
reactor-lab/greeting-core/target/greeting-core-1.0.0-SNAPSHOT.jar
reactor-lab/greeting-cli/target/greeting-cli-1.0.0-SNAPSHOT.jar
reactor-lab/greeting-core/target/surefire-reports/
reactor-lab/greeting-cli/target/surefire-reports/
```

Lệnh `verify` chưa bao gồm phase `install`. Vì vậy nó **không tự cài Core artifact mới vào local repository**, dù CLI đã build thành công từ source Core.

### 6.1. Chạy CLI với Java classpath

Trên Bash/zsh:

```bash
java -cp "reactor-lab/greeting-cli/target/classes:reactor-lab/greeting-core/target/classes" dev.learning.cli.App
```

Trên Windows PowerShell:

```powershell
java -cp "reactor-lab/greeting-cli/target/classes;reactor-lab/greeting-core/target/classes" dev.learning.cli.App
```

Stdout **chính xác do ứng dụng in**:

```text
CLI: Xin chào, Lan!
```

Vì POM chưa cấu hình executable/fat JAR, không dùng `java -jar greeting-cli-...jar` như thể dependency Core đã nằm trong JAR này.

### 6.2. Biên dịch thủ công với javac để hiểu classpath

Trên Bash/zsh tại `workspace-lab`:

```bash
mkdir -p manual/core manual/cli
javac -encoding UTF-8 --release 17 -d manual/core \
  reactor-lab/greeting-core/src/main/java/dev/learning/core/Greeter.java
javac -encoding UTF-8 --release 17 -cp manual/core -d manual/cli \
  reactor-lab/greeting-cli/src/main/java/dev/learning/cli/App.java
java -cp "manual/core:manual/cli" dev.learning.cli.App
```

Kết quả cũng là `CLI: Xin chào, Lan!`. Nhưng đây **không phải reactor build**, chỉ là Java compiler thủ công theo thứ tự Core rồi CLI. Nếu bỏ `-cp manual/core` khi compile CLI, `javac` không thể tìm thấy Greeter class.

## 7. Build một phần reactor: -pl, -am, -amd và -rf

| Tùy chọn | Tên dài | Vai trò |
| --- | --- | --- |
| `-pl` | `--projects` | Chỉ chọn module được chỉ định |
| `-am` | `--also-make` | Build thêm reactor modules mà module được chọn phụ thuộc |
| `-amd` | `--also-make-dependents` | Build những reactor modules phụ thuộc ngược vào module được chọn |
| `-rf` | `--resume-from` | Tiếp tục từ một module sau khi build fail |
| `-N` | `--non-recursive` | Chỉ build project hiện tại, không đi vào child modules |

### 7.1. Build CLI cùng Core từ source

```bash
mvn -f reactor-lab/pom.xml -pl :greeting-cli -am clean verify
```

Dấu `:` trong `-pl :greeting-cli` chọn module theo artifactId. `-am` đưa **Core** và các upstream reactor projects cần thiết vào build. Đây là cách đúng khi source Core đang sửa và bạn muốn CLI dùng kết quả mới.

So với:

```bash
mvn -f reactor-lab/pom.xml -pl :greeting-cli clean verify
```

Lệnh này có thể **không build Core**. CLI có thể fail do repository thiếu Core, hoặc nguy hiểm hơn là **PASS nhờ artifact Core cũ đã install** cùng GAV. Vì thế `BUILD SUCCESS` của một module chọn riêng chưa bảo đảm upstream source mới đã được kiểm chứng.

### 7.2. Build Core và những modules phụ thuộc

```bash
mvn -f reactor-lab/pom.xml -pl :greeting-core -amd clean verify
```

Trong ví dụ, CLI phụ thuộc Core, nên `-amd` đưa cả CLI vào build. Dùng khi thay API của Core và cần kiểm tra downstream impact.

### 7.3. Resume từ một module

```bash
mvn -f reactor-lab/pom.xml -rf :greeting-cli verify
```

`-rf` chọn điểm bắt đầu tiếp tục theo reactor order, **không tự bảo đảm build lại upstream Core**. Khi Core đổi source hoặc cache không có artifact thích hợp, ưu tiên `-pl :greeting-cli -am verify` hoặc full reactor build.

## 8. Consumer độc lập không nằm trong reactor

Tạo project `workspace-lab/external-client`, **không** thêm nó vào root modules.

### 8.1. external-client/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.consumer</groupId>
    <artifactId>external-client</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.learning</groupId>
            <artifactId>greeting-core</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
    </dependencies>

    <build>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Consumer khai báo đúng Core GAV nhưng không có `<parent>maven-reactor-lab</parent>`, không nằm trong reactor-lab modules. Maven của consumer giải quyết Core bằng repositories.

### 8.2. ConsumerApp.java

Tạo `workspace-lab/external-client/src/main/java/dev/consumer/ConsumerApp.java`:

```java
package dev.consumer;

import dev.learning.core.Greeter;

public final class ConsumerApp {
    private ConsumerApp() {
    }

    public static void main(String[] args) {
        System.out.println(
                "Consumer: " + Greeter.say(" Minh "));
    }
}
```

Khi dependency đúng, stdout của Java main:

```text
Consumer: Xin chào, Minh!
```

## 9. Thử consumer trước và sau khi install

### 9.1. Trước install

Giả sử bạn **chỉ** chạy reactor tới verify. Nếu Core GAV **không tồn tại trong local repository và bất kỳ remote repository nào** consumer dùng, lệnh:

```bash
mvn -f external-client/pom.xml clean package
```

có thể thất bại với thông điệp tương tự:

```text
Could not resolve dependencies for project ...
Could not find artifact dev.learning:greeting-core:jar:1.0.0-SNAPSHOT
```

Đây là **mẫu lỗi**, không phải log chính xác. Dù Core có JAR trong `reactor-lab/greeting-core/target`, consumer không tự thấy artifact đó theo GAV.

Nếu local/remote repo **đã có** GAV Core, lệnh có thể pass. Nhưng hãy kiểm tra bản đó có đúng source/build hiện tại hay không; không suy luận consumer dùng Core mới chỉ từ trạng thái PASS.

### 9.2. Install toàn reactor

Chạy:

```bash
mvn -f reactor-lab/pom.xml clean install
```

Maven build và install root parent POM, Core JAR/POM và CLI JAR/POM. Các paths trong local repository mặc định có thể gồm:

```text
~/.m2/repository/dev/learning/maven-reactor-lab/1.0.0-SNAPSHOT/
    maven-reactor-lab-1.0.0-SNAPSHOT.pom

~/.m2/repository/dev/learning/greeting-core/1.0.0-SNAPSHOT/
    greeting-core-1.0.0-SNAPSHOT.jar
    greeting-core-1.0.0-SNAPSHOT.pom

~/.m2/repository/dev/learning/greeting-cli/1.0.0-SNAPSHOT/
    greeting-cli-1.0.0-SNAPSHOT.jar
    greeting-cli-1.0.0-SNAPSHOT.pom
```

Parent POM rất quan trọng khi artifact Core có metadata kế thừa từ parent: một consumer ngoài source tree có thể cần parent để Maven giải quyết model của artifact.

### 9.3. Consumer sau install

```bash
mvn -f external-client/pom.xml clean package
mvn -q -f external-client/pom.xml compile exec:java -Dexec.mainClass=dev.consumer.ConsumerApp
```

Exec Maven Plugin chạy class Java với project classpath chứa Core JAR đã phân giải theo GAV. Dòng stdout do chương trình tạo:

```text
Consumer: Xin chào, Minh!
```

`-q` giảm bớt Maven logs nhưng môi trường có thể sinh warning khác; **dòng stdout ứng dụng** là kết quả cần đối chiếu.

Điều khác biệt là **repository đã có Core artifact/POM**, không phải consumer tự động tìm được source Core ở folder cạnh đó.

## 10. Dùng local repository riêng để tránh artifact stale

Một developer có thể từng install Core từ build cũ. Vì thế consumer **vẫn pass trước thử nghiệm install mới**, khiến bạn tưởng `verify` đã tự publish Core. Cách kiểm chứng tốt là dùng local repository lab riêng.

Từ `workspace-lab`:

Bash/zsh:

```bash
LAB_REPO="$(pwd)/.maven-repo-lab"
mvn -f reactor-lab/pom.xml "-Dmaven.repo.local=$LAB_REPO" clean verify
mvn -f external-client/pom.xml "-Dmaven.repo.local=$LAB_REPO" clean package
```

PowerShell:

```powershell
$labRepo = Join-Path (Get-Location).Path ".maven-repo-lab"
mvn -f reactor-lab/pom.xml "-Dmaven.repo.local=$labRepo" clean verify
mvn -f external-client/pom.xml "-Dmaven.repo.local=$labRepo" clean package
```

Trong repo lab chưa có Core và remote repository không cung cấp GAV đó, consumer có thể báo lỗi thiếu Core; reactor verify vẫn pass vì build các modules trong cùng invocation.

**Lưu ý:** repo lab mới trống có thể phải tải Maven plugins, JUnit và metadata khác. Nếu network không cho tải, lỗi tải plugin không phải lỗi chứng minh reactor/consumer behavior.

Sau đó install vào chính repo lab:

Bash/zsh:

```bash
mvn -f reactor-lab/pom.xml "-Dmaven.repo.local=$LAB_REPO" clean install
mvn -q -f external-client/pom.xml "-Dmaven.repo.local=$LAB_REPO" compile exec:java -Dexec.mainClass=dev.consumer.ConsumerApp
```

PowerShell:

```powershell
mvn -f reactor-lab/pom.xml "-Dmaven.repo.local=$labRepo" clean install
mvn -q -f external-client/pom.xml "-Dmaven.repo.local=$labRepo" compile exec:java -Dexec.mainClass=dev.consumer.ConsumerApp
```

**Phải dùng cùng một repository path** cho lệnh install và consumer. Nếu cài vào repo A nhưng consumer đọc repo B, kết quả lại fail dù đã install thành công ở A.

Đưa cache và build outputs vào `workspace-lab/.gitignore`:

```gitignore
.maven-repo-lab/
**/target/
manual/
```

Không commit `.m2` hoặc JAR output vào Git chỉ để tránh việc thiết lập Maven repo đúng cách.

## 11. Rủi ro artifact cũ cùng version

Giả sử Core `1.0.0-SNAPSHOT` đã install tuần trước. Bạn chỉnh `Greeter.java` hôm nay nhưng **chưa install lại**. Sau đó bạn chỉ chạy:

```bash
mvn -f reactor-lab/pom.xml -pl :greeting-cli verify
```

Do không có `-am`, Core có thể không nằm trong selected reactor. Maven có thể giải quyết dependency từ local/remote repository — một artifact **cùng version nhưng không chứa source mới**. CLI có thể vẫn compile/test pass với API cũ.

Để chắc chắn build từ source:

```bash
mvn -f reactor-lab/pom.xml -pl :greeting-cli -am clean verify
```

Điều này buộc các reactor dependencies upstream được chọn vào build.

Các CLI flags khác:

- `-U` kiểm tra cập nhật remote artifacts/snapshot metadata theo Maven settings; **không tự biên dịch Core source** nếu Core không thuộc selected reactor.
- `-o` dùng offline cache; **không biến source sibling thành dependency có sẵn**.
- `-N` tại root không build các child modules; chỉ install parent POM không phải install Core JAR.
- `-rf :greeting-cli` tiếp tục từ CLI, **không bảo đảm làm mới upstream Core**.

**Đừng “sửa” bằng cách xóa toàn bộ local repository hoặc tự chép JAR vào cache**. Hãy xác định đúng Maven invocation, project selection, GAV, install/deploy và repository path.

## 12. Chẩn đoán nhanh

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Full reactor verify PASS nhưng consumer FAIL | Core chưa có ở repo consumer | Install đúng repo hoặc publish có kiểm soát |
| `-pl :greeting-cli` FAIL dù Core source tồn tại | Core không được build và repo thiếu artifact | Thêm `-am` |
| CLI pass nhưng hành vi Core không đổi | Dùng artifact cũ đã install | Build Core cùng CLI bằng `-am` |
| CLI compile báo `package dev.learning.core does not exist` | CLI thiếu dependency Core hoặc resolution fail | Xem CLI POM và dependency graph |
| Chỉ có Core trong parent dependencyManagement | Management không thêm classpath | Khai báo Core trong CLI dependencies |
| Reactor sort Core trước CLI | Dependency edge có độ ưu tiên | Đúng behavior; không sửa thứ tự tùy tiện |
| Consumer tìm sai version | GAV/version không khớp | Đối chiếu đúng groupId/artifactId/version |
| Consumer không nhìn thấy artifact sau install | Khác `maven.repo.local` hoặc settings | Dùng cùng repo path |
| Parent POM không resolve | Artifact Core kế thừa parent chưa có ở repo | Install parent cùng modules |
| CI fail còn laptop pass | Laptop có local artifacts riêng | Dùng clean repo/CI cache có kiểm soát |
| `-U` vẫn lấy API cũ | Không rebuild source Core | Sửa reactor selection, không chỉ update metadata |
| `NoClassDefFoundError` khi chạy JVM | Runtime classpath thiếu Core | Dùng đúng -cp hoặc packaging hợp lý |
| `-o` fail trong repo mới | Plugin/JUnit/dependency chưa cache | Setup repository/network |
| Reactor chỉ build root | Đang dùng `-N` hoặc modules không được chọn | Đọc lệnh và root POM |
| `dependency:tree` fail do artifact chưa có | Goal cần resolution, GAV chưa giải quyết được | Kiểm tra repo/phase và dùng full reactor |

Lệnh kiểm tra hữu ích:

```bash
mvn -version
mvn -f reactor-lab/pom.xml help:effective-pom
mvn -f reactor-lab/pom.xml -pl :greeting-cli dependency:tree
mvn -f reactor-lab/pom.xml -pl :greeting-cli -am clean verify
mvn -f reactor-lab/pom.xml clean install
mvn -f external-client/pom.xml dependency:tree
```

`help:effective-pom` cho thấy parent inheritance, dependencyManagement, pluginManagement và profiles. `dependency:tree` cho thấy dependencies/versions nhưng chính goal có thể fail nếu artifact chưa phân giải được.

## 13. CI và kiểm thử khả năng phân phối

Đối với source multi-module repository, CI nội bộ có thể chạy:

```bash
mvn -B -ntp -f reactor-lab/pom.xml clean verify
```

Lệnh này kiểm tra build/test Core và CLI từ source hiện tại **mà không cần install trước**.

Nếu dự án phát hành thư viện để consumer bên ngoài sử dụng, còn cần một bước hợp lệ hóa artifact:

1. Build full reactor và chạy tests.
2. Install vào local repo lab hoặc publish staging repository có kiểm soát.
3. Build một external consumer bằng repository settings tương ứng.
4. Chạy ConsumerApp/test kiểm tra behavior đã phân phối.
5. Xác nhận parent POM, Core JAR/POM và các transitive dependencies được resolution đúng.
6. Chỉ deploy lên remote repo khi được cấp quyền và theo release process.

**Reactor verify và external consumer contract test kiểm tra hai yêu cầu khác nhau.** Một bên xác minh các module nguồn build cùng nhau; bên kia xác minh artifacts sau phân phối có thể giải quyết và sử dụng độc lập.

## 14. Bài tập

1. Tạo cây `workspace-lab` gồm root reactor, Core, CLI và external consumer như bài.
2. Giải thích sự khác nhau giữa root aggregator, parent POM và Core dependency.
3. Đảo thứ tự entries trong `<modules>`; vì sao build order của reactor vẫn là Core trước CLI?
4. Xóa dependency Core trong CLI nhưng giữ dependencyManagement; compiler sẽ báo gì?
5. Chạy `mvn -f reactor-lab/pom.xml clean verify`; kiểm tra 3 tests của Core, 1 test của CLI và hai JAR.
6. Chạy `java -cp` với hai classes directories, so sánh với classpath chỉ có CLI.
7. Dùng `javac` thủ công và giải thích vì sao phải compile Core trước CLI.
8. Chạy `-pl :greeting-cli -am clean verify`; Maven build modules nào?
9. Chạy `-pl :greeting-core -amd clean verify`; vì sao CLI được chọn?
10. Tạo external consumer; giải thích vì sao vị trí folder sibling không biến nó thành reactor.
11. Sau full reactor verify nhưng trước install, consumer khi nào fail và khi nào có thể pass?
12. Chạy full reactor install rồi consumer; kiểm tra stdout `Consumer: Xin chào, Minh!`.
13. Dùng local repository lab riêng. Vì sao mỗi lệnh phải truyền cùng `-Dmaven.repo.local`?
14. Sửa Core source nhưng không install lại; tại sao `-pl :greeting-cli` có thể dùng code cũ?
15. So sánh mục đích `-U`, `-o`, `-am` và `-rf`.
16. Vì sao một project bên ngoài reactor cần artifact POM và có thể cần parent POM?
17. Phân biệt `mvn verify`, `mvn install` và `mvn deploy` về tác động repository.
18. Vì sao một CI job clean repository hữu ích để tìm lỗi cache ẩn?
19. Khi nào reactor build không phải bằng chứng artifact đã được publish hợp lệ?
20. Với release artifact bất biến, điều gì sai khi thay nội dung đã publish nhưng giữ nguyên version?

## 15. Tổng kết

**Build trong Maven reactor** nghĩa là Maven nhìn thấy các modules tham gia cùng invocation và có thể dùng artifact/output của upstream reactor module, **không cần install từng module trước**.

**Tiêu thụ artifact đã install** là tình huống khác: một consumer bên ngoài reactor phân giải dependency theo GAV từ local/remote repository. Một JAR trong `target/` sau `verify` **không tự thành artifact trong local repo**. Chạy `install` vào repository phù hợp hoặc publish tới remote repository theo quy trình khi cần consumer sử dụng.

Dùng `-pl :greeting-cli -am verify` để build Core cùng CLI từ source hiện hành. Dùng `mvn install` và consumer độc lập để xác minh artifact có thể phân phối. Cẩn thận với SNAPSHOT hoặc local artifact cũ cùng GAV: một build success không tự chứng minh đã dùng source mới nhất.

## 16. Nguồn tham khảo

- [Maven 3 — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Maven — Guide to Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Maven 4 — Multiple Subprojects](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
