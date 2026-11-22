# Giới hạn build đệ quy bằng -N trong Maven Reactor nhiều mô-đun

## 1. Mục tiêu

Một dự án Maven có nhiều mô-đun thường khai báo các thư mục con trong phần `<modules>` của POM gốc. Khi chạy một phase từ thư mục gốc, Maven có thể tạo **reactor build**: thu thập các project, sắp thứ tự theo những dependency/parent relationships, rồi thực hiện lifecycle trên nhiều module.

Tuy nhiên, có lúc bạn chỉ muốn xử lý **POM hiện tại**: kiểm tra cấu hình parent, cài đặt riêng parent POM, xem effective POM hoặc thực thi một goal của project tổng hợp. Cờ `-N` giải quyết đúng nhu cầu ấy:

~~~bash
mvn -N validate
~~~

`-N` viết đầy đủ là **`--non-recursive`**. Nó yêu cầu Maven không đệ quy vào những module con từ project bắt đầu. Với Maven 3.9.x, hiểu đơn giản: **chỉ build project của starting POM, không build toàn bộ các project được liệt kê trong `<modules>`**.

Cần nhớ hai ý song song:

- `-N` giúp hạn chế **tập project được build**, không phải nút tắt mọi Maven plugin.
- `mvn -N verify` trên root POM packaging `pom` có thể báo **BUILD SUCCESS** mà không compile/test bất kỳ module Java con nào.

Vì vậy cờ này hữu ích cho công việc root-only, nhưng có thể gây chất lượng giả nếu vô tình đưa vào lệnh CI “verify toàn repository”.

## 2. -N làm gì và không làm gì?

Hai cách viết tương đương:

~~~bash
mvn -N validate
mvn --non-recursive validate
~~~

Maven xác định starting POM theo working directory hoặc `-f`. Nó tạo effective model cho project ấy, gồm parent inheritance, properties, profiles và cấu hình plugins cần thiết. Khi có `-N`, Maven không thu thập những submodules để chạy một reactor build đệ quy như thông thường.

**Điều -N không bảo đảm:**

1. Không tắt các plugin goals đang bind vào lifecycle của starting project.
2. Không tắt dependency/plugin resolution từ local hoặc remote repositories.
3. Không bỏ qua parent inheritance của starting project.
4. Không skip unit tests của chính starting project nếu project ấy có tests và goal được chạy.
5. Không giới hạn tác dụng phụ của plugin vào một thư mục duy nhất; plugin riêng có thể ghi file hoặc gọi dịch vụ bên ngoài.
6. Không tự chọn một child module; muốn chọn starting POM khác phải dùng `-f`, hoặc dùng reactor project selection như `-pl`.

**Nói gọn:** `-N` điều khiển **module recursion**, không thay thế chính sách plugin, test, dependency hay bảo mật của build.

## 3. Aggregator, parent và reactor khác nhau

Giả sử project:

~~~text
reactor-n-lab/
├── pom.xml                  root, packaging=pom
├── core/
│   └── pom.xml              packaging=jar
└── app/
    └── pom.xml              packaging=jar
~~~

Root là **aggregator** nếu khai báo:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>core</module>
    <module>app</module>
</modules>
~~~

`<modules>` gồm những đường dẫn thư mục mà Maven thu thập, **không phải dependency declaration**.

Root cũng có thể là **parent** nếu child POM khai báo:

~~~xml
<parent>
    <groupId>dev.example</groupId>
    <artifactId>reactor-n-lab</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Parent quản lý properties, dependencyManagement, pluginManagement và cấu hình được kế thừa. Quan hệ này **không biến mất** khi chạy child-only với `-N`.

**Reactor** là danh sách project trong một invocation multi-module, với thứ tự build do Maven tính dựa trên relationships đã khai báo. Nếu `app` phụ thuộc `core`, reactor cần build core trước app.

Cùng một POM có thể làm cả parent và aggregator, nhưng **đọc parent để kế thừa** không giống **build parent như một reactor project**.

## 4. Trực quan hóa phạm vi lệnh

Từ thư mục root:

~~~text
mvn verify
  |
  +-- reactor-n-lab (root POM)
  +-- core          (module JAR)
  +-- app           (module JAR)

mvn -N verify
  |
  +-- reactor-n-lab (root POM)
~~~

Nếu root đóng vai trò aggregator packaging `pom`, `mvn -N verify` không tự biên dịch mã của core/app. Dù vậy một plugin execution được bind trên root có thể chạy và in log.

### Một số lệnh dễ nhầm

| Lệnh | Điều khiển |
| --- | --- |
| `mvn -N verify` | Chặn đệ quy vào submodules từ starting POM |
| `mvn -q verify` | Giảm log, **không chặn modules** |
| `mvn -ntp verify` | Bỏ transfer progress, **không chặn modules** |
| `mvn verify -DskipTests` | Có thể skip test execution theo plugin hỗ trợ, **vẫn build modules** |
| `mvn -pl :app verify` | Chọn module bằng reactor selector |
| `mvn -pl :app -am verify` | Chọn app và các reactor prerequisites của nó |
| `mvn -N -f core/pom.xml verify` | Chọn core làm starting POM và không đệ quy từ core |

## 5. Bài thực hành Java 17 với hai module

Để thấy rõ điều gì được build, ta tạo một project có:

- Root `pom.xml` packaging `pom`, quản lý hai modules.
- Module `core` chứa class `Greeting` và một JUnit test.
- Module `app` phụ thuộc core, chứa `App.main` và một JUnit test.
- Maven AntRun Plugin chạy ở phase `validate` và in tên `project.artifactId` đang thực thi.

Dự án không cần Spring Boot, database hoặc network runtime. Lần build đầu vẫn cần Maven resolve những plugins và JUnit từ Maven repositories hợp lệ.

Cấu trúc:

~~~text
reactor-n-lab/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/example/core/Greeting.java
│       └── test/java/dev/example/core/GreetingTest.java
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/dev/example/app/App.java
        └── test/java/dev/example/app/AppTest.java
~~~

### 5.1. Root pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>reactor-n-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
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

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>print-project</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo message="ACTIVE_PROJECT=${project.artifactId}"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích:**

1. Root khai báo `<modules>core/app</modules>` thông qua hai phần tử module riêng.
2. Root packaging `pom` không tự tạo một application JAR khi chạy root-only.
3. Plugin versions được ghim trong `pluginManagement`. Các Maven lifecycle bindings của child packaging `jar` dùng những plugins cần thiết theo effective model.
4. AntRun Plugin nằm trong `<build><plugins>` và bind goal `run` vào `validate`. Vì execution được kế thừa theo mặc định, full reactor build có thể in marker ở cả root/core/app.
5. Giá trị `${project.artifactId}` thay đổi theo Maven project hiện tại. Markers làm bằng chứng về những project thực sự được Maven xử lý.
6. Không có lệnh nào trong AntRun tự biên dịch/test Java; nó chỉ in thông tin.

### 5.2. Module core: core/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>reactor-n-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Parent cung cấp `groupId`, `version` và cấu hình Java release. Module core dùng JUnit trong scope test.

### 5.3. core/src/main/java/dev/example/core/Greeting.java

~~~java
package dev.example.core;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String value) {
        return "Hello, " + value;
    }
}
~~~

### 5.4. core/src/test/java/dev/example/core/GreetingTest.java

~~~java
package dev.example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void formatsMessage() {
        assertEquals("Hello, Core", Greeting.message("Core"));
    }
}
~~~

### 5.5. Module app: app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>reactor-n-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Chú ý:** `<modules>` chỉ liệt kê các thư mục. Để Java code `app` import classes của core, cần **dependency declaration** như trên.

### 5.6. app/src/main/java/dev/example/app/App.java

~~~java
package dev.example.app;

import dev.example.core.Greeting;

public final class App {
    private App() {
    }

    public static String message() {
        return Greeting.message("Maven Reactor");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 5.7. app/src/test/java/dev/example/app/AppTest.java

~~~java
package dev.example.app;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void usesCore() {
        assertEquals("Hello, Maven Reactor", App.message());
    }
}
~~~

**Kết quả chạy Java chính xác:** với runtime classpath có cả app và core, `App.main` in một dòng:

~~~text
Hello, Maven Reactor
~~~

## 6. Lần chạy thứ nhất: full reactor

Đứng tại root `reactor-n-lab`:

~~~bash
mvn -version
mvn -B -ntp clean verify
~~~

Với dependency app → core, reactor build order hợp lý là:

~~~text
reactor-n-lab   pom
core            jar
app             jar
~~~

Các marker AntRun sẽ xuất hiện trong log tại từng project, không nhất thiết liền nhau:

~~~text
[echo] ACTIVE_PROJECT=reactor-n-lab
[echo] ACTIVE_PROJECT=core
[echo] ACTIVE_PROJECT=app
~~~

Đây là **trích các dòng dự kiến**, không phải toàn bộ log Maven.

Kết quả mong đợi:

- Core compile, chạy `GreetingTest`.
- App compile với core dependency trong reactor, chạy `AppTest`.
- Các module `jar` tạo `core/target/core-1.0.0.jar` và `app/target/app-1.0.0.jar`.
- Root POM được xử lý theo lifecycle.
- Maven báo `BUILD SUCCESS` nếu các steps đều đạt.

### Chạy ứng dụng sau full build

Trên Linux/macOS:

~~~bash
java -cp "app/target/classes:core/target/classes" dev.example.app.App
~~~

Trên Windows PowerShell:

~~~powershell
java -cp "app\target\classes;core\target\classes" dev.example.app.App
~~~

Stdout:

~~~text
Hello, Maven Reactor
~~~

Dấu phân tách classpath là `:` trên Unix-like và `;` trên Windows. Không dùng `java -jar app/target/app-1.0.0.jar` như thể đó là fat/executable JAR: trong POM demo chưa có Main-Class và app JAR không tự đóng core dependency.

## 7. Lần chạy thứ hai: root-only -N

Từ root:

~~~bash
mvn -B -ntp -N clean verify
~~~

Lệnh này chỉ build project root, nên AntRun marker kỳ vọng:

~~~text
[echo] ACTIVE_PROJECT=reactor-n-lab
~~~

Không có AntRun marker từ core/app trong **invocation này**. Không có chuyện Maven tự chạy JUnit tests của child modules vì bạn đã yêu cầu chặn recursion.

Root có `packaging=pom`, nên `BUILD SUCCESS` lúc này chỉ chứng minh **root lifecycle/goals đã hoàn tất**. Nó **không chứng minh**:

- Core compile.
- App compile.
- Hai JUnit tests chạy.
- Hai child JARs được tạo mới.
- Reactor dependency app → core được kiểm chứng.

Đặc biệt, nếu chạy full build trước đó, các file dưới `core/target` và `app/target` có thể vẫn tồn tại. `-N clean` ở root không cam kết xóa output của child modules, vì chúng không được build/clean trong reactor này.

## 8. Chỉ validate root POM

~~~bash
mvn -B -ntp -N validate
~~~

Đây là cách dùng phổ biến khi muốn thực hiện root-only checks nhanh. Trong demo, AntRun ở `validate` vẫn chạy:

~~~text
[echo] ACTIVE_PROJECT=reactor-n-lab
~~~

Nếu root còn có Enforcer Plugin, validation của parent config hoặc goal được bind vào `validate`, những goal ấy vẫn có thể chạy. **`-N` không vô hiệu hóa plugin executions của root.**

**Giới hạn:** Một child POM bị lỗi hoặc mã Java module con không compile được có thể không bị phát hiện bởi lần validate root-only. Vì vậy job này không nên mang tên “validate all modules”.

## 9. Chỉ install parent POM bằng -N

~~~bash
mvn -B -ntp -N install
~~~

Với root packaging `pom`, Maven tiến đến phase `install` của **root project**. Artifact có coordinates:

~~~text
dev.example:reactor-n-lab:pom:1.0.0
~~~

Một đường dẫn local repository mặc định thường có dạng:

~~~text
~/.m2/repository/dev/example/reactor-n-lab/1.0.0/
~~~

với file `reactor-n-lab-1.0.0.pom`. Trên Windows, custom repository hoặc CI runner, đường dẫn thực tế có thể khác.

**Lệnh này không tạo/install `core.jar` và `app.jar`.** Cài riêng parent POM có ích nếu cần resolve parent inheritance của một project khác, nhưng không thay thế việc build/install artifacts của modules.

Muốn install toàn reactor:

~~~bash
mvn -B -ntp clean install
~~~

Khi lệnh này thành công, core và app artifacts cũng được install theo reactor project selection.

## 10. -f chọn một starting POM khác

Muốn build/test module core từ root:

~~~bash
mvn -B -ntp -N -f core/pom.xml test
~~~

Starting POM bây giờ là **core**. Maven vẫn đọc parent qua `relativePath` để kế thừa cấu hình; nhưng lifecycle test chỉ được chạy trên core, không phải parent như một reactor project riêng.

Dòng marker của AntRun:

~~~text
[echo] ACTIVE_PROJECT=core
~~~

Kết quả test:

- `GreetingTest` chạy.
- App module không được build.
- Core vẫn kế thừa compiler release 17 và Surefire version từ parent.

Tương tự:

~~~bash
mvn -B -ntp -N -f app/pom.xml test
~~~

chọn **app**. Nhưng app cần `dev.example:core:jar:1.0.0`, nên Maven phải resolve core từ local/remote repository nếu core không có trong reactor build này.

Nếu core chưa được install, có thể gặp:

~~~text
Could not find artifact dev.example:core:jar:1.0.0
~~~

Đây là lỗi dependency resolution có thể dự đoán, không phải lỗi `-N`.

### Stale dependency là một rủi ro

Sau một lần full install:

~~~bash
mvn -B -ntp clean install
~~~

app-only `-N -f app/pom.xml test` có thể PASS nhờ core đã có trong local repository. Tuy nhiên core JAR ấy có thể **cũ hơn source code core hiện tại**. Vì vậy để kiểm tra cùng revision của repository, dùng `-pl :app -am` từ root.

## 11. -pl chọn child module trong reactor

`-pl`/`--projects` dùng để chọn các project thay vì build toàn reactor:

~~~bash
mvn -B -ntp -pl :core test
mvn -B -ntp -pl :app test
~~~

`:core` là artifactId selector. Dạng:

~~~bash
mvn -B -ntp -pl core test
~~~

thường chọn module theo **relative path** `core`. Hai dạng có thể khác nhau nếu directory name và artifactId không trùng.

**Điều khác với -N:** `-pl` là bộ lọc reactor projects. `-N` chặn đệ quy từ starting POM. Nếu muốn kiểm soát một child trong multi-module repo, `-pl` là công cụ thích hợp hơn thay vì chỉ dùng `-N` ở root.

## 12. -am đi theo chiều dependencies

Muốn build app **và core mà app cần**:

~~~bash
mvn -B -ntp -pl :app -am clean verify
~~~

Ý nghĩa:

- `-pl :app` chọn app.
- `-am` bổ sung các projects cần thiết cho app trong reactor, gồm core khi dependency thật được khai báo.
- Maven sắp thứ tự, compile/test core rồi app.
- Không cần install core thủ công vào local repository trước khi chạy.

Cách này thường tốt hơn `-N -f app/pom.xml test` nếu bạn đang sửa code ở cả hai module và cần xác nhận cùng source revision.

Một root parent POM có thể cũng xuất hiện trong selected reactor theo Maven version/model relationships; hãy đọc log thật để biết tập projects chính xác.

## 13. -amd đi theo chiều dependents

Nếu bạn sửa `core`, muốn kiểm tra những module đang dùng core:

~~~bash
mvn -B -ntp -pl :core -amd clean verify
~~~

`-amd`/`--also-make-dependents` bổ sung các module **phụ thuộc vào** module đã chọn. Trong lab, app phụ thuộc core nên app cũng được build/test.

Nhớ chiều:

| Cờ | Đối tượng bổ sung |
| --- | --- |
| `-am` | Các dependencies/prerequisites mà selected project cần |
| `-amd` | Những dependents/consumers sử dụng selected project |

Không nhầm hai cờ. Một thư viện có hàng trăm consumers có thể khiến `-amd` chọn một tập lớn hơn dự kiến.

## 14. Maven 3 và Maven 4: cẩn thận khi kết hợp -N với -pl

Trong tài liệu reactor Maven 3, `--non-recursive` được mô tả là **không dùng reactor build ngay cả khi current POM khai báo modules**. Vì vậy với Maven 3.9.x, những cách viết rõ ràng là:

- Root-only: `mvn -N validate`.
- Child-only: `mvn -pl :core test` hoặc `mvn -N -f core/pom.xml test`.
- App cùng dependencies: `mvn -pl :app -am verify`.
- Core và dependents: `mvn -pl :core -amd verify`.

**Maven 4 có nuance khác:** hướng dẫn chính thức Working with Multiple Subprojects in Maven 4 mô tả `-N` có thể kết hợp với `-pl` để ngăn việc một aggregator được chọn tự kéo descendants vào tập build.

Vì vậy không nên khẳng định “`-N` và `-pl` không bao giờ kết hợp được”; nhưng cũng **không nên mang tổ hợp `-N -pl ...` từ Maven 4 sang Maven 3 mà không kiểm tra**.

Luôn xác minh:

~~~bash
mvn -version
~~~

và đọc Reactor Build Order/summary của đúng Maven version. Nếu dự án dùng Maven Wrapper, dùng version được wrapper ghim để tránh lệch local/CI.

## 15. Bảng chọn lệnh cho lab

| Lệnh từ root | Root | Core | App |
| --- | :---: | :---: | :---: |
| `mvn validate` | Có | Có | Có |
| `mvn -N validate` | Có | Không | Không |
| `mvn clean verify` | Có | Có | Có |
| `mvn -N clean verify` | Có | Không | Không |
| `mvn -N install` | Có | Không | Không |
| `mvn -N -f core/pom.xml test` | Chỉ đọc làm parent | Có | Không |
| `mvn -N -f app/pom.xml test` | Chỉ đọc làm parent | Không | Có |
| `mvn -pl :app -am verify` | Tùy reactor parent selection | Có | Có |
| `mvn -pl :core -amd verify` | Tùy reactor parent selection | Có | Có |

Bảng mô tả mục đích và hiệu ứng chính theo Maven 3.9.x. Riêng dòng `-pl/-am/-amd`, Maven cũng có thể chọn parent POM theo quan hệ reactor; đừng hard-code số lượng projects thay cho kiểm tra log.

Với `-f child/pom.xml`, root parent có thể được **đọc để inherit**, nhưng điều đó không phải lifecycle build root.

## 16. -N khác skipTests

Hai lệnh sau **không tương đương**:

~~~bash
mvn -B -ntp -N verify
mvn -B -ntp verify -DskipTests
~~~

Ở root lab:

- Câu đầu chỉ build root POM, **không compile/package child modules**.
- Câu sau vẫn thu thập/build nhiều module theo reactor; Surefire thường bỏ qua **test execution**, nhưng compilation/packaging vẫn có thể diễn ra theo cấu hình.

`-Dmaven.test.skip=true` có thể bỏ cả test compilation trong những plugins hỗ trợ, nhưng cũng không phải một bộ chọn reactor.

Khi cần skip test vì một tình huống ngoại lệ, chọn cờ kiểm thử phù hợp và ghi rõ rủi ro; **không dùng -N để giả vờ toàn bộ module đã được build**.

## 17. Dependency resolution không bị tắt bởi -N

App POM có:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Khi chạy app-only:

~~~bash
mvn -B -ntp -N -f app/pom.xml test
~~~

Maven vẫn phải tìm core JAR cho compile/test classpath. Nếu không có reactor core trong lần build, artifact phải có từ local hoặc remote repository.

Hệ quả:

- `-N` không xóa dependency declaration.
- `-N` không có nghĩa build offline.
- `-N` không bảo đảm test đang dùng core source mới nhất.
- `-N` có thể giúp giảm thời gian khi artifact dependency đã có, nhưng đổi lại giảm mức kiểm chứng source trong repository.

Trong CI quality gate cho một PR sửa cả app/core, nên dùng reactor `-am` để bảo đảm những dependencies được build đúng từ source revision.

## 18. -N clean và output cũ

Hai câu:

~~~bash
mvn -B -ntp clean
mvn -B -ntp -N clean
~~~

khác nhau ở module collection:

- Full reactor clean có thể chạy Clean Plugin trên root và các selected modules.
- Root-only `-N clean` chỉ yêu cầu clean đối với starting project.

Nếu core/app targets còn tồn tại từ lần trước, root-only clean **không bảo đảm** xóa chúng. Vì vậy:

- Không nhìn thấy `core/target/core-1.0.0.jar` rồi kết luận lần root-only vừa build core.
- Không sử dụng child test reports từ lần chạy cũ như bằng chứng lần build hiện tại.
- Khi điều tra cache/stale output, cần full reactor `mvn clean verify`.

Plugin/script tùy biến ở root có thể xóa những đường dẫn khác, nhưng đó là **side effect riêng**, không nên được coi là hành vi mặc định của `-N`.

## 19. -N và các goal đọc thông tin Maven

Một lệnh root-only hữu ích:

~~~bash
mvn -B -ntp -N help:effective-pom -Doutput=effective-root.xml
~~~

Lệnh giúp xem effective POM của **starting root project**. Nó không có nghĩa đã kiểm tra effective POM của core/app. Child có thể khai báo những dependency/profiles riêng.

Tương tự:

~~~bash
mvn -B -ntp -N dependency:tree
~~~

ở root packaging `pom` có thể in rất ít thông tin nếu root không có dependencies. Không coi output đó là dependency graph tổng hợp của cả repository.

Muốn xem dependency tree của app:

~~~bash
mvn -B -ntp -N -f app/pom.xml dependency:tree
~~~

Những goals này có thể resolve plugin artifacts và dependencies khi cần; `-N` không làm chúng chạy “không dùng repository”.

**Lưu ý:** Với một plugin goal có logic aggregator hoặc thao tác nhiều POM/files, hãy đọc tài liệu goal trước khi coi kết quả `-N` là phạm vi tác dụng phụ tuyệt đối.

## 20. Plugin inheritance vẫn có hiệu lực

Ở root lab, AntRun Plugin được khai báo trong `<build><plugins>`, có execution tại `validate`. Child modules kế thừa execution theo quy tắc Maven plugin inheritance.

Chạy:

~~~bash
mvn -B -ntp -N -f core/pom.xml validate
~~~

có marker:

~~~text
[echo] ACTIVE_PROJECT=core
~~~

Điều này **không chứng minh root project đã chạy lifecycle**. Nó chứng minh child đang thực thi goal được kế thừa, và Maven property `project.artifactId` lấy giá trị của child.

Nếu goal chỉ nên chạy tại root, cần thiết kế inheritance/plugin execution phù hợp (chẳng hạn `<inherited>false</inherited>` khi áp dụng đúng) thay vì bật `-N` trong mọi job để che việc goal bị kế thừa nhầm.

## 21. Với nested aggregators

Một repository có thể chứa nhiều tầng:

~~~text
platform/
├── pom.xml
├── api/
│   ├── pom.xml
│   ├── model/pom.xml
│   └── client/pom.xml
└── services/
    ├── pom.xml
    ├── service-a/pom.xml
    └── service-b/pom.xml
~~~

Root platform liệt kê api/services; mỗi sub-aggregator lại liệt kê module của riêng nó.

Từ platform root:

~~~bash
mvn -N validate
~~~

chỉ xử lý starting POM platform theo Maven 3, không đệ quy xuống children/grandchildren.

Muốn chỉ xử lý aggregator api:

~~~bash
mvn -N -f api/pom.xml validate
~~~

starting POM bây giờ là api, và Maven không đi vào model/client như child modules.

Muốn toàn bộ reactor:

~~~bash
mvn validate
~~~

không kèm `-N`.

## 22. Profiles chứa modules

Một profile có thể điều khiển modules được thu thập:

~~~xml
<profiles>
    <profile>
        <id>with-integration-tests</id>
        <modules>
            <module>integration-tests</module>
        </modules>
    </profile>
</profiles>
~~~

Đây là một đoạn POM **minh họa riêng**, không phải phần của lab runnable vì lab không có thư mục integration-tests.

Khi dùng:

~~~bash
mvn -Pwith-integration-tests verify
~~~

profile có thể góp thêm module vào reactor. Nhưng:

~~~bash
mvn -N -Pwith-integration-tests verify
~~~

vẫn yêu cầu không đệ quy child modules từ starting POM. Profile **vẫn có thể thay đổi properties/plugins** của starting project, nên `-N` không có nghĩa tắt tất cả profiles.

## 23. -N với -T và parallel build

~~~bash
mvn -T 4 verify
~~~

cho phép Maven dùng nhiều threads cho các modules thích hợp trong reactor, tùy dependency constraints và thread safety.

~~~bash
mvn -N -T 4 verify
~~~

khi chỉ có một starting project sẽ không tạo thêm child modules để chạy song song. `-T` không hủy ý nghĩa non-recursive của `-N`.

Nhưng một plugin bên trong starting project có thể tự dùng threads/processes, nên `-N` **không phải lệnh giới hạn mọi hoạt động đồng thời**.

## 24. Cẩn thận với install/deploy trong CI

So sánh:

~~~bash
mvn -B -ntp -N install
mvn -B -ntp install
~~~

Lệnh đầu trên root packaging `pom` chỉ install root POM. Lệnh sau build/install modules được thu thập.

Tương tự:

~~~bash
mvn -B -ntp -N deploy
mvn -B -ntp deploy
~~~

Nếu mục tiêu là phát hành **toàn bộ module artifacts**, `-N deploy` trên root là sai phạm vi: nó không tự deploy child JARs. Nếu mục tiêu là phát hành riêng parent POM, `-N` có thể hữu ích nhưng vẫn cần cấu hình distributionManagement, credentials và version release phù hợp.

**Không chạy thử deploy lên production chỉ để xem lệnh nào chọn module nào.** Dùng `validate`/`verify` và log để kiểm tra tập project trước, rồi thực hiện release trong môi trường được cấp quyền.

## 25. Những lỗi phổ biến và xử lý

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `-N verify` xanh nhưng không có test reports | Child modules không chạy | Full reactor verify hoặc `-pl ... -am` |
| `-N install` không có core.jar | Chỉ parent POM được install | Chạy full install nếu cần child artifacts |
| `-N` không build module bạn mong | Cờ không chọn child | Dùng `-f` hoặc `-pl` |
| App-only fail thiếu core | Core chưa install, không ở reactor | Dùng `-pl :app -am` |
| App-only PASS nhưng dùng core cũ | Maven local repo chứa JAR cũ | Build cùng reactor/source |
| `-N clean` không xóa target con | Clean chỉ ở starting project | Dùng full reactor clean |
| `-N validate` vẫn in AntRun log | Root execution vẫn active | Đây là behavior đúng; xem effective POM |
| Child-only vẫn kế thừa parent config | Inheritance không bị -N tắt | Kiểm tra parent/relativePath |
| `-N dependency:tree` không liệt kê app deps | Goal chạy trên root project | Chọn app POM |
| `-N -pl` kết quả không như dự kiến | Maven version/project selection khác | Xem tài liệu Maven 3/4 và reactor log |
| Deploy thiếu module artifacts | Dùng root-only deploy nhầm | Bỏ -N khi cần toàn reactor |
| Plugin sửa file ngoài root | Side effects riêng của goal | Kiểm tra plugin docs và quyền ghi |
| Root-only success nhưng child mã lỗi | Không compile/test child | Full verify hoặc chọn child |
| Log quá ít nên không thấy phạm vi | Dùng -q hoặc CI che output | Bỏ quiet, đọc Reactor Summary |
| Child target vẫn còn sau root clean | Stale build output | Clean các module được yêu cầu |

## 26. Tình huống chọn lệnh

**Tình huống A — Chỉ validate parent POM:** chọn `mvn -N validate`. Kết quả không thay thế child verification.

**Tình huống B — Cài parent POM để project khác kế thừa:** chọn `mvn -N install` nếu parent packaging `pom` và không cần module artifacts.

**Tình huống C — Sửa app, cần core từ cùng repo:** chọn `mvn -pl :app -am verify`.

**Tình huống D — Sửa core API, cần kiểm tra consumers:** chọn `mvn -pl :core -amd verify`.

**Tình huống E — Muốn build riêng core trong CLI:** chọn `mvn -f core/pom.xml test` và có thể thêm `-N` nếu core có module con và bạn muốn tránh đệ quy.

**Tình huống F — CI quality gate cho toàn repository:** chọn `mvn clean verify` không kèm `-N`.

**Tình huống G — Kiểm tra effective POM của root:** chọn `mvn -N help:effective-pom -Doutput=effective-root.xml`.

**Tình huống H — Phát hành mọi child artifacts:** không dùng `-N deploy` trên root; kiểm chứng reactor rồi mới publish có kiểm soát.

## 27. Checklist khi đưa -N vào build pipeline

- [ ] Tôi biết starting POM chính xác và working directory hoặc `-f`.
- [ ] Tôi hiểu root là parent, aggregator hay cả hai.
- [ ] Tôi biết modules được khai báo trong `<modules>`.
- [ ] Tôi thật sự muốn bỏ qua child modules, không chỉ muốn giảm output log.
- [ ] Tôi phân biệt `-N` với `-pl`, `-am`, `-amd` và `-DskipTests`.
- [ ] Tôi biết root plugin executions vẫn có thể chạy.
- [ ] Tôi biết parent inheritance vẫn áp dụng khi chọn child POM.
- [ ] Tôi hiểu dependency artifacts vẫn phải được resolve.
- [ ] Tôi không coi root-only BUILD SUCCESS là bằng chứng tests ở modules PASS.
- [ ] Tôi không dùng child target files từ lần build cũ làm bằng chứng mới.
- [ ] Tôi biết `-N clean` không mặc nhiên xóa child outputs.
- [ ] Tôi biết `-N install` ở root POM không tạo child JARs.
- [ ] Tôi biết `-N deploy` chỉ phát hành project được chọn theo build hiện tại.
- [ ] Tôi đã kiểm tra Maven version khi phối hợp `-N` với `-pl`.
- [ ] Tôi đọc Reactor Build Order/Summary và các module markers trong log.
- [ ] Job root-only và job full reactor được đặt tên và mục tiêu riêng.
- [ ] CI vẫn có gate build/test các modules bắt buộc.
- [ ] Tôi kiểm tra plugin-specific side effects nếu goal có thể ghi files.
- [ ] Tôi dùng Maven Wrapper nếu cần Maven version thống nhất giữa CI/local.
- [ ] Tôi kiểm tra lệnh bằng `validate`/`verify` trước khi deploy thật.

## 28. Bài tập có đáp án

1. **`-N` là gì?**  
   **Đáp án:** Dạng ngắn của `--non-recursive`.

2. **Từ root, `mvn -N validate` có build core/app của lab không?**  
   **Đáp án:** Không.

3. **Vì sao `-N validate` vẫn in ACTIVE_PROJECT ở root?**  
   **Đáp án:** AntRun goal của root được bind vào validate và vẫn chạy.

4. **`mvn -N verify` thành công có chứng minh GreetingTest và AppTest đã chạy không?**  
   **Đáp án:** Không.

5. **`mvn -N install` trên root packaging pom tạo gì?**  
   **Đáp án:** Install parent/root POM, không tự build/install child JARs.

6. **Muốn build toàn repo?**  
   **Đáp án:** `mvn clean verify` không kèm -N.

7. **Muốn chọn riêng core từ reactor?**  
   **Đáp án:** `mvn -pl :core test`.

8. **Muốn chạy core từ POM của nó?**  
   **Đáp án:** `mvn -N -f core/pom.xml test`.

9. **Muốn app cùng core từ source hiện tại?**  
   **Đáp án:** `mvn -pl :app -am verify`.

10. **Muốn core cùng các dependents?**  
    **Đáp án:** `mvn -pl :core -amd verify`.

11. **-N có tắt dependency resolution không?**  
    **Đáp án:** Không.

12. **-N có tắt parent inheritance không?**  
    **Đáp án:** Không.

13. **-N có giống -DskipTests không?**  
    **Đáp án:** Không; một cờ điều khiển project set, cờ còn lại điều khiển test execution theo plugin.

14. **Vì sao app-only build có thể fail khi core chưa install?**  
    **Đáp án:** Core không được reactor build nên dependency cần được resolve từ repository.

15. **Vì sao app-only build có thể PASS với core cũ?**  
    **Đáp án:** Maven lấy artifact từ local repository, không tự build core source.

16. **-N clean có dọn child targets không?**  
    **Đáp án:** Không mặc nhiên.

17. **-f dùng để làm gì?**  
    **Đáp án:** Chọn starting POM.

18. **-pl :app khác -pl app thế nào?**  
    **Đáp án:** Dạng có dấu hai chấm chọn artifactId, dạng còn lại có thể chọn theo relative path.

19. **-am bổ sung module theo hướng nào?**  
    **Đáp án:** Những dependencies mà selected project cần.

20. **-amd bổ sung module theo hướng nào?**  
    **Đáp án:** Những dependents phụ thuộc selected project.

21. **Maven 4 có nuance gì với -N và -pl?**  
    **Đáp án:** Có trường hợp tài liệu cho phép kết hợp để kiểm soát việc tự chọn descendants của aggregator.

22. **-N có làm mọi plugin chỉ đọc root files?**  
    **Đáp án:** Không; goal-specific side effects vẫn có thể xảy ra.

23. **Vì sao parent được đọc nhưng không nhất thiết được build khi chọn core?**  
    **Đáp án:** Đọc để inherit model khác với chạy lifecycle của parent reactor project.

24. **Nên kiểm tra gì để biết đúng project nào đã build?**  
    **Đáp án:** Maven version, starting POM, Reactor Build Order/Summary và plugin markers.

25. **Khi nào không dùng -N?**  
    **Đáp án:** Khi cần compile/test/package/deploy toàn bộ modules hoặc cùng build reactor dependencies.

## 29. Nguồn tham khảo

- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor, -N, -pl, -am, -amd và thứ tự modules.
- [Apache Maven — Working with Multiple Subprojects in Maven 4](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html): Maven 4 project collection và sự kết hợp -N với -pl.
- [Apache Maven — Maven CLI Options Reference](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html): short/long command line flags cho Maven 3.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): parent/aggregation/inheritance.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): modules, parent, packaging, pluginManagement.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): lifecycle phases và packaging.
- [Apache Maven — Maven AntRun Plugin](https://maven.apache.org/plugins/maven-antrun-plugin/): AntRun execution bind vào phase validate.
- [Apache Maven — Maven Help Plugin](https://maven.apache.org/plugins/maven-help-plugin/): effective POM.
- [Apache Maven — Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): unit tests trong Maven lifecycle.

**Kết luận:** `-N`/`--non-recursive` làm Maven **không đệ quy build các module con**. Nó thích hợp với root-only checks hoặc install riêng parent POM, nhưng **không thay thế** một full reactor verification. Để chọn một module và các dependency liên quan, dùng `-pl` kết hợp `-am`; để test những module phụ thuộc vào một thư viện, dùng `-amd`. Khi đánh giá chất lượng build, phải nhìn **project set thực tế**, không chỉ dòng BUILD SUCCESS.
