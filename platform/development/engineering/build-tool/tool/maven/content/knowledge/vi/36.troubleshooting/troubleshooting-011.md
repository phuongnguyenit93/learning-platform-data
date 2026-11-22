# Build chạy được trong Maven Reactor nhưng thất bại khi build riêng mô-đun

## 1. Tình huống: root `verify` xanh, nhưng chạy từ thư mục module lại đỏ

Một repository chứa nhiều Maven modules:

~~~text
catalog-workspace/
├── pom.xml                  (aggregator và parent)
├── catalog-api/
│   └── pom.xml              (thư viện nội bộ)
└── catalog-app/
    └── pom.xml              (ứng dụng dùng catalog-api)
~~~

Ở root, lệnh:

~~~bash
mvn -B -ntp clean verify
~~~

thành công. Nhưng khi thử:

~~~bash
mvn -B -ntp -f catalog-app/pom.xml clean verify
~~~

Maven 3 có thể báo:

~~~text
Could not find artifact com.example.catalog:catalog-api:jar:1.0.0
~~~

Điều này **không tự chứng minh** source code của `catalog-app` bị sai. Có thể `catalog-app` đang phụ thuộc vào **artifact của một module anh em** mà Maven Reactor đã cung cấp trong build chung, nhưng khi build riêng, Maven không còn module đó trong tập dự án đang build và cần resolve nó từ local/remote repository.

Đây là một trong các lỗi thường gặp của nhóm **Chẩn đoán lỗi Maven**. Bài học hướng dẫn cách phân biệt:

1. **Reactor resolution:** Maven biết và build các module có quan hệ dependency ngay trong một invocation.
2. **Repository resolution:** Maven tìm một artifact theo GAV từ local/remote Maven repositories.
3. **Parent inheritance:** child cần một parent POM để tạo effective model, nhưng đó là bài toán khác việc tìm sibling JAR.
4. **Reactor aggregation:** `<modules>` mô tả những dự án được tập hợp, không tự biến mọi module thành một Java dependency.
5. **Các lớp lỗi khác**: sai GAV/version, plugin/code generation, profile, reactor CLI selection, test-jar/classifier, JDK hoặc môi trường CI.

**Phạm vi và phiên bản:** ví dụ runnable dưới đây dùng **Maven 3.9+, JDK 17+, Maven Compiler Plugin 3.13.0, Surefire Plugin 3.5.2, JUnit Jupiter 5.11.4**. Cơ chế Maven 4 khác Maven 3 về root discovery và project-local repository; bài sẽ ghi rõ ở phần riêng, không lấy một cách tái hiện lỗi của Maven 3 áp cho mọi Maven 4.

## 2. Reactor là gì và hoạt động khi nào?

Theo tài liệu Apache Maven, **Reactor** là cơ chế Maven dùng để:

- Thu thập các projects/modules thuộc một multi-module build.
- Xác định thứ tự build dựa trên quan hệ dependency thực tế.
- Build các projects đã chọn theo đúng thứ tự và goal/lifecycle yêu cầu.

Với graph:

~~~text
catalog-parent (packaging=pom)
       |
       +-- catalog-api (jar)
       |
       +-- catalog-app (jar)
                |
                +-- depends on catalog-api:1.0.0
~~~

Một root reactor build có thể build `catalog-api` trước `catalog-app`, dù app nằm trên API trong danh sách `<modules>` (Maven có dependency ordering). `catalog-app` có thể lấy output của `catalog-api` từ **reactor của chính invocation đó**.

Nhưng chạy:

~~~bash
mvn -f catalog-app/pom.xml verify
~~~

trên Maven 3 thường chỉ build project bắt đầu từ child POM đó (và những submodules của chính nó, nếu có). Parent POM có thể được Maven đọc để inherit cấu hình, nhưng **đọc parent không đồng nghĩa Maven cũng đã tập hợp mọi sibling modules thành reactor**.

Vì vậy dependency `catalog-api:jar:1.0.0` có thể không tồn tại trong tập đang build. Maven sẽ chuyển sang repository resolution theo graph và settings hiện hành.

### 2.1. Không phải cứ có `<modules>` là các module tự phụ thuộc nhau

Ví dụ root có:

~~~xml
<modules>
    <module>catalog-api</module>
    <module>catalog-app</module>
</modules>
~~~

nhưng nếu POM của app **không khai báo** dependency tới API, Maven không tự thêm `catalog-api.jar` vào `catalog-app` compile/runtime classpath. `<modules>` là thông tin aggregation. `<dependencies>` là mối quan hệ library.

Muốn app dùng class của API, cần declaration GAV phù hợp:

~~~xml
<dependency>
    <groupId>com.example.catalog</groupId>
    <artifactId>catalog-api</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Các tên thư mục `catalog-api` và tên package Java không thay thế GAV.

## 3. Căn cứ chẩn đoán: ba biểu đồ khác nhau

### 3.1. Cây thư mục

~~~text
root/
├── pom.xml
├── catalog-api/pom.xml
└── catalog-app/pom.xml
~~~

Cây thư mục chỉ nói có files ở đâu. Nó **không chứng minh** child POM nhận đúng parent hoặc app dependency dùng đúng GAV.

### 3.2. Quan hệ parent

~~~text
catalog-parent:1.0.0
    |
    +-- parent của catalog-api
    +-- parent của catalog-app
~~~

Quan hệ parent truyền properties, plugin configuration, dependencyManagement và các phần inheritable khác. Nó **không tự tạo classpath dependency từ app sang API**.

### 3.3. Quan hệ dependency

~~~text
catalog-app:jar:1.0.0
    |
    +-- com.example.catalog:catalog-api:jar:1.0.0
~~~

Đây là đồ thị quyết định `catalog-api` phải được cung cấp cho app. Trong một reactor đủ modules, Maven lấy từ reactor; ngoài reactor, Maven cần artifact từ repository. **Sự khác nhau nằm ở resolution scope**, không nhất thiết ở source Java.

## 4. Bốn loại lệnh có ý nghĩa khác nhau

| Lệnh chạy từ root | Dự án được chọn trên Maven 3 | Điều cần lưu ý |
| --- | --- | --- |
| `mvn clean verify` | Root + tất cả modules được aggregate | Reactor build đầy đủ |
| `mvn -pl :catalog-app verify` | Chọn app, không tự kéo API vào build | Cần API có sẵn trong repo, hoặc có thể fail |
| `mvn -pl :catalog-app -am verify` | App **và** các modules mà app phụ thuộc thuộc reactor | Cách chính để build chọn lọc có upstream |
| `mvn -f catalog-app/pom.xml verify` | Build bắt đầu từ child POM | Maven 3 không tự xem mọi sibling là reactor |
| `mvn -pl :catalog-api -amd verify` | API và các modules downstream phụ thuộc API | `-amd` khác `-am` |
| `mvn -N verify` | Chỉ project hiện tại, không recurse modules | Không kiểm đủ multi-module build |
| `mvn -rf :catalog-app verify` | Tiếp tục từ app theo reactor đã chọn | Có thể bỏ qua API nếu không kèm `-am`/repository |
| `mvn -fn verify` | Cố tiếp tục và có thể trả exit code 0 dù lỗi | **Không dùng** để tạo CI gate xanh |

Các CLI options quan trọng:

- `-pl` / `--projects`: chọn project theo path hoặc tọa độ.
- `-pl :catalog-app`: selector theo `artifactId`; tránh nhập nhầm một path.
- `-am` / `--also-make`: chọn cả những **reactor dependencies** cần thiết.
- `-amd` / `--also-make-dependents`: chọn những projects **phụ thuộc vào** project được chọn.
- `-rf` / `--resume-from`: bắt đầu từ một module; **không tự bảo đảm upstream được build lại**.
- `-N` / `--non-recursive`: build project hiện tại và không đi vào child modules.

**Không sửa lỗi “thiếu `catalog-api`” bằng `-amd`** nếu mục tiêu là build app. App **phụ thuộc vào** API, nên dùng `-am` từ reactor root.

## 5. Lab Java 17: tạo một project có thể tái hiện lỗi

Ta xây một Maven multi-module project với:
- Root `catalog-parent` đóng vai trò **aggregator + parent**.
- `catalog-api` là JAR cung cấp `MoneyMath`.
- `catalog-app` là JAR dùng `MoneyMath`.
- JUnit 5 có tests trong cả hai modules.
- Không database, không private repository, không external runtime services.

**Tình huống dự kiến:** root reactor build pass từ local Maven repository chưa chứa `catalog-api:1.0.0`; build `catalog-app` độc lập bằng Maven 3 fail nếu artifact chưa được install/deploy hoặc cached sẵn. Sau đó `-pl ... -am` build pass mà không cần cài sibling artifact vào repository.

### 5.1. Cấu trúc đầy đủ

~~~text
catalog-workspace/
├── pom.xml
├── catalog-api/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/catalog/api/MoneyMath.java
│       └── test/java/com/example/catalog/api/MoneyMathTest.java
└── catalog-app/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/catalog/app/App.java
        └── test/java/com/example/catalog/app/AppTest.java
~~~

Các tên file Java **phải khớp package và public class** trong source. Cấu trúc dưới đây là một project hoàn chỉnh; không cần một module `third-party` hay `lib/` chứa JAR thủ công.

## 6. Root `pom.xml` — parent và aggregator

Tạo `catalog-workspace/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.catalog</groupId>
    <artifactId>catalog-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>catalog-app</module>
        <module>catalog-api</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.catalog</groupId>
                <artifactId>catalog-api</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

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
~~~

### 6.1. Vì sao `packaging=pom`?

Root chỉ tổng hợp và quản lý cấu hình. Nó không chứa Java source để tạo JAR; `pom` packaging phù hợp với parent/aggregator. Hai children mặc định dùng `jar` packaging.

### 6.2. Vì sao cố tình khai báo `catalog-app` trước `catalog-api`?

Đây là một **thử nghiệm về Reactor sorting**. Mặc dù `<modules>` liệt kê app trước API, Maven vẫn phải build API trước app vì app khai báo dependency lên API trong POM. **Không dùng thứ tự `<modules>` để thay thế khai báo dependency**.

Maven chỉ dùng thứ tự `<modules>` làm tie-break khi không có quan hệ khác buộc thứ tự. Một module không có dependency rõ ràng có thể bị sort theo thứ tự khai báo mà không có classpath thích hợp.

### 6.3. `dependencyManagement` có tải JAR không?

Không. Root `dependencyManagement` chỉ quản lý version của `catalog-api` cho các child POM có khai báo dependency. **Nó không tự đưa API vào app classpath và không tự build API**.

App phải có `<dependencies>` thực tế. Và version `1.0.0` mà dependencyManagement chọn vẫn phải resolve được từ Reactor hoặc repository.

### 6.4. `pluginManagement` có tự chạy plugin không?

Không theo nghĩa kích hoạt tùy ý goals mới. Nó quản lý version/configuration của plugins khi chúng được dùng (bao gồm các plugins từ default lifecycle bindings của `jar` packaging). Compiler/Surefire/JAR Plugin vẫn được gọi theo lifecycle tương ứng, với versions đã pin.

Nếu một module cần goal riêng như `generate-sources` hoặc `maven-dependency-plugin:copy`, không chỉ đưa execution vào `pluginManagement` rồi mặc định rằng mọi child sẽ chạy goal ấy. Cần xem plugin declaration/execution và inheritance thực tế.

### 6.5. JUnit trong parent

JUnit Jupiter được đặt ở root `<dependencies>` với scope `test`, vì vậy children thừa hưởng test dependency. **Nó không được đưa vào runtime dependencies của application JAR**. Đây là lựa chọn demo; dự án thực có thể quản lý version trong dependencyManagement và để từng module chọn có khai báo JUnit hay không.

## 7. `catalog-api/pom.xml` — thư viện được app sử dụng

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.catalog</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-api</artifactId>
    <packaging>jar</packaging>
</project>
~~~

`groupId` và `version` của API được thừa hưởng từ parent, nên GAV là:

~~~text
com.example.catalog:catalog-api:jar:1.0.0
~~~

**`<relativePath>../pom.xml</relativePath>` trỏ đến POM cha**, không phải đến JAR của `catalog-app`. Maven có thể tìm parent POM bằng đường dẫn filesystem khi tọa độ parent khớp. Parent lookup và sibling artifact lookup là hai việc khác nhau.

Nếu bạn di chuyển riêng thư mục `catalog-api` ra một repository không chứa `../pom.xml`, Maven có thể cần parent POM đã được install/deploy vào repository hoặc cần cấu hình parent phù hợp. Xem phần 17.

## 8. `catalog-app/pom.xml` — child phụ thuộc `catalog-api`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.catalog</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.catalog</groupId>
            <artifactId>catalog-api</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Chú ý `<dependency>` không ghi `<version>` ở child: root parent **quản lý version** của `catalog-api` trong `dependencyManagement`, nên effective POM của app dùng `1.0.0`.

Đây vẫn là **một dependency thật**, khác với chỉ khai báo API trong root `<modules>` hoặc `dependencyManagement`.

### 8.1. Nếu bỏ `<dependency>` khỏi app?

Compiler sẽ báo không tìm thấy class/package API (nếu app import API). Reactor **không tự thêm classpath chỉ vì hai directories nằm chung root**. Đừng sửa lỗi này bằng cách thêm `-am` khi Maven còn không thấy dependency edge trong model.

### 8.2. Nếu version bị lệch?

Nếu app yêu cầu:

~~~xml
<version>1.0.1</version>
~~~

nhưng reactor chỉ có `catalog-api:1.0.0`, Maven không coi hai tọa độ này là cùng artifact. Nó có thể tìm `1.0.1` trong repository và fail nếu không có. Sửa GAV/version theo release contract, không thêm `-U` như một cách tự động biến version khác thành đúng.

## 9. `MoneyMath.java` — Java17 API module

Tạo `catalog-api/src/main/java/com/example/catalog/api/MoneyMath.java`:

~~~java
package com.example.catalog.api;

public final class MoneyMath {

    private MoneyMath() {
    }

    public static long totalCents(
            long subtotalCents, int taxPercent) {

        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }

        if (taxPercent < 0 || taxPercent > 100) {
            throw new IllegalArgumentException(
                    "taxPercent must be in 0..100");
        }

        long tax = Math.multiplyExact(
                subtotalCents, taxPercent) / 100;

        return Math.addExact(subtotalCents, tax);
    }
}
~~~

Ví dụ dùng integer cents, tránh sự không chính xác của floating-point khi tính số tiền. `Math.multiplyExact` và `Math.addExact` giúp phát hiện overflow cho tính toán demo. Đây không phải library thuế đầy đủ: với tỷ lệ tạo phân số cent, phép chia integer ở ví dụ **truncates**; hệ thống tài chính thật cần quy định rounding, tax jurisdiction và tiền tệ.

Tại `subtotalCents=10_000` và `taxPercent=10`, kết quả là:

~~~text
11000
~~~

`MoneyMath` không có Java `main`, vì nó là API class. Việc thư viện không có `main` không gây lỗi compile/package JAR.

## 10. `MoneyMathTest.java` — tests trong API module

Tạo `catalog-api/src/test/java/com/example/catalog/api/MoneyMathTest.java`:

~~~java
package com.example.catalog.api;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MoneyMathTest {

    @Test
    void calculatesTax() {
        assertEquals(11_000L,
                MoneyMath.totalCents(10_000L, 10));
    }

    @Test
    void rejectsInvalidValues() {
        assertThrows(IllegalArgumentException.class,
                () -> MoneyMath.totalCents(-1L, 10));

        assertThrows(IllegalArgumentException.class,
                () -> MoneyMath.totalCents(10_000L, -1));

        assertThrows(IllegalArgumentException.class,
                () -> MoneyMath.totalCents(10_000L, 101));
    }
}
~~~

API module có **2 JUnit 5 test methods**. Method thứ hai kiểm nhiều invalid inputs trong một test, không tạo ba test methods riêng. JUnit được thừa hưởng với `test` scope từ root parent POM.

Trong báo cáo Surefire của `catalog-api`, kỳ vọng `Tests run: 2, Failures: 0, Errors: 0` khi project được cấu hình đúng.

## 11. `App.java` — sử dụng class từ sibling module

Tạo `catalog-app/src/main/java/com/example/catalog/app/App.java`:

~~~java
package com.example.catalog.app;

import com.example.catalog.api.MoneyMath;

public final class App {

    private App() {
    }

    public static String quote() {
        return "total-cents="
                + MoneyMath.totalCents(10_000L, 10);
    }

    public static void main(String[] args) {
        System.out.println(quote());
    }
}
~~~

`App` import API class từ **một Maven dependency**, không từ source folder `../catalog-api/src/main/java` bằng path thủ công. Chính sự phụ thuộc này tạo ra trường hợp reactor pass còn standalone resolve fail.

**Stdout chính xác của `App.main`:**

~~~text
total-cents=11000
~~~

Đây là output chương trình Java, không bao gồm Maven logs. Không chạy `java -jar catalog-app/target/catalog-app-1.0.0.jar` ở demo: POM chưa có `Main-Class` manifest và JAR app không phải fat JAR. Phần chạy đúng classpath nằm ở mục 14.

## 12. `AppTest.java` — kiểm app và API dependency

Tạo `catalog-app/src/test/java/com/example/catalog/app/AppTest.java`:

~~~java
package com.example.catalog.app;

import com.example.catalog.api.MoneyMath;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {

    @Test
    void rendersQuoteFromSiblingDependency() {
        assertEquals("total-cents=11000",
                App.quote());
    }

    @Test
    void callsApiAtZeroTax() {
        assertEquals(10_000L,
                MoneyMath.totalCents(10_000L, 0));
    }
}
~~~

App module có **2 test methods**. Tổng hai modules là **4 JUnit methods**. Root `packaging=pom` không có Java test class, nên không được cộng thêm tests ảo cho parent.

Nếu API không resolve được, Maven có thể fail ở **dependency resolution hoặc compilation** trước khi đến phase `test`; “không có báo cáo JUnit” không phải bằng chứng test suite rỗng, có thể đơn giản vì build chưa tới Surefire.

## 13. Chạy root Reactor build

Đứng trong `catalog-workspace/`, dùng Maven 3.9+ và JDK17+:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Một reactor summary **theo ý nghĩa**:

~~~text
catalog-parent ........................ SUCCESS
catalog-api ........................... SUCCESS
catalog-app ........................... SUCCESS
BUILD SUCCESS
~~~

Tùy Maven version, CLI và log styling, các dòng, thời lượng và tên project có thể khác. Quan trọng là **API build trước app**, dù `<modules>` đặt app trước API.

Điều xảy ra:
1. Maven đọc POM root, thu thập hai modules.
2. Maven tính effective model và dependency graph.
3. Maven sắp xếp API trước app theo dependency.
4. Compiler tạo `MoneyMath.class` và `catalog-api-1.0.0.jar`.
5. App được cung cấp artifact của API từ reactor.
6. Compiler tìm import `MoneyMath`, Surefire chạy 2 tests trong app.
7. `catalog-api` chạy 2 tests của nó.
8. Build `verify` pass khi mọi phase/plugin goal liên quan pass.

Một **root `verify` không tự install** API JAR vào local Maven repository. Do đó bước 5 diễn ra nhờ reactor, không phải vì Maven vừa copy JAR vào `~/.m2/repository`.

### 13.1. Ba output đáng quan sát

~~~text
catalog-api/target/catalog-api-1.0.0.jar
catalog-app/target/catalog-app-1.0.0.jar
catalog-app/target/surefire-reports/TEST-com.example.catalog.app.AppTest.xml
~~~

Artifact JAR đã được package trong `target`. **Có file tại `target` khác với có artifact trong Maven local repository** dưới GAV tương ứng.

## 14. Chạy `App` bằng classpath đúng trên Java17+

Sau reactor build thành công, đứng ở root:

POSIX/Linux/macOS:

~~~bash
java -cp catalog-app/target/classes:catalog-api/target/classes com.example.catalog.app.App
~~~

Windows PowerShell hoặc `cmd.exe`:

~~~powershell
java -cp "catalog-app/target/classes;catalog-api/target/classes" com.example.catalog.app.App
~~~

**Stdout chính xác:**

~~~text
total-cents=11000
~~~

Dấu phân cách classpath là `:` trên POSIX và `;` trên Windows. Lệnh này minh họa runtime dùng cả hai module outputs; JUnit không cần có trong runtime classpath của App.

**Một lỗi khác có thể xảy ra:** nếu chạy:

~~~bash
java -cp catalog-app/target/classes com.example.catalog.app.App
~~~

mà bỏ `catalog-api/target/classes`, JVM không tìm `MoneyMath` ở runtime và có thể báo `NoClassDefFoundError`. Đây là **runtime classpath error**, khác với Maven dependency resolution failure khi build module riêng.

## 15. Cách tái hiện lỗi build riêng trên Maven 3

Để thấy khác biệt, sau khi root `verify` đã pass, chạy:

~~~bash
mvn -B -ntp -f catalog-app/pom.xml clean verify
~~~

Nếu `com.example.catalog:catalog-api:1.0.0` chưa được install trong local repository và chưa có remote repository cung cấp nó, Maven 3 sẽ fail với thông báo có dạng:

~~~text
Could not resolve dependencies for project
com.example.catalog:catalog-app:jar:1.0.0
...
Could not find artifact
com.example.catalog:catalog-api:jar:1.0.0
~~~

Đây là **log dạng minh họa**, không cam kết Maven in từng dòng đúng tuyệt đối. Ở thời điểm fail, parent POM vẫn có thể được đọc qua `../pom.xml`, nhưng Maven **không build API sibling** vì API không nằm trong selected reactor của invocation đó.

**Điều kiện tái hiện phải được hiểu rõ:** nếu đã chạy `mvn install` từ root trước đó, hoặc API version `1.0.0` đã nằm trong local/remote repository, build child riêng **có thể pass**. Vì vậy “chạy riêng fail” không phải đặc tính bắt buộc của mọi dự án đa module; nó phụ thuộc trạng thái repository và Maven version.

### 15.1. Vì sao `mvn package` của root trước đó chưa đủ?

~~~text
mvn clean package
  -> target/catalog-api-1.0.0.jar
  -> reactor dùng artifact trong invocation
  -> không bắt buộc có com/.../catalog-api/1.0.0 trong ~/.m2/repository
~~~

Chạy `mvn -f catalog-app/pom.xml` sau đó trong Maven 3 bắt đầu một invocation mới với scope khác; việc API JAR tồn tại trong thư mục sibling `target/` **không khiến Maven tự gắn nó vào classpath**.

### 15.2. Lỗi có thể bị che bởi local cache

Một developer đã từng `mvn install` API version đó có thể thấy app standalone pass, trong khi developer khác và CI agent sạch fail. Đây là một **local repository contamination/hidden precondition**.

Đừng tuyên bố “đã sửa được” chỉ vì chạy trên laptop đã chứa dependencies nội bộ. Hãy kiểm workflow từ môi trường sạch và xác định artifact thực sự đến từ đâu.

## 16. Cách sửa thứ nhất: chọn app cùng upstream modules bằng `-pl` và `-am`

Từ **root aggregator**:

~~~bash
mvn -B -ntp -pl :catalog-app -am clean verify
~~~

Ý nghĩa:
- `-pl :catalog-app`: muốn kiểm target app.
- `-am`: kéo những reactor projects mà app phụ thuộc, trong đó có `catalog-api` và parent cần thiết.
- `clean verify`: dùng lifecycle có compile, tests và package.
- Không cần cài API JAR vào repository trước, vì API được build trong **cùng reactor invocation**.

Đây là phương án ưu tiên cho **monorepo/multi-module source đang phát triển cùng nhau**.

### 16.1. Dùng `-f` đúng cách

Nếu đang đứng ở một working directory khác nhưng vẫn muốn reactor từ root, trỏ `-f` đến **root POM**:

~~~bash
mvn -B -ntp -f /path/to/catalog-workspace/pom.xml -pl :catalog-app -am clean verify
~~~

`/path/to/catalog-workspace` là placeholder đường dẫn, phải thay bằng đường dẫn thật. Điểm cốt lõi là **POM được chỉ định làm entrypoint phải là aggregator root**, không phải child POM, trong kịch bản Maven 3 đang phân tích.

Nếu dùng Maven Wrapper, chạy wrapper từ vị trí phù hợp với repository và bảo đảm file `.mvn/wrapper` thực sự tồn tại. Không dùng một `./mvnw` không có trong project rồi kết luận Maven build lỗi.

### 16.2. Vì sao chỉ `-pl` có thể vẫn thất bại?

~~~bash
mvn -B -ntp -pl :catalog-app clean verify
~~~

`-pl` **chỉ chọn** app; nó không mặc định build API. App vẫn cần `catalog-api` JAR trong local/remote repo nếu không có `-am`. Trên laptop có API đã install, lệnh này có thể pass; trên agent sạch fail.

Công thức nhớ: **`-pl` chọn, `-am` mang theo upstream**.

## 17. Cách sửa thứ hai: publish upstream artifact và parent POM vào repository

Khi `catalog-app` thực sự cần được build như một **project độc lập**, không mang toàn bộ sibling source vào CI, cần làm cho dependencies của nó có thể resolve từ repository.

Một cách thử local trên workstation:

~~~bash
mvn -B -ntp -f pom.xml clean install
mvn -B -ntp -f catalog-app/pom.xml clean verify
~~~

Lệnh `install` cài artifacts/POM đã build vào local Maven repository. Khi đó app riêng có thể resolve `catalog-api:jar:1.0.0` và parent POM từ local state.

**Nhưng đây chưa phải giải pháp CI sạch lâu dài.** Local `~/.m2/repository` chỉ thuộc máy/job hiện tại. Nếu CI khác không chạy install/provisioning và không có internal repository, app vẫn fail.

Giải pháp có khả năng tái tạo cho các dự án độc lập:
1. Build/test `catalog-api` theo pipeline riêng.
2. Publish **POM và JAR** với GAV/version bất biến đến hosted Maven repository được phép.
3. Nếu parent/BOM không nằm trong source được checkout, publish các **parent/BOM POMs cần thiết**.
4. Cấu hình consumer repositories/mirrors trong Maven settings theo policy.
5. Pin dependency versions; không override cùng release GAV bằng bytes mới.
6. Test consumer từ local repo sạch, không dùng installed artifact tình cờ.
7. Dùng version alignment/release process để app biết chính xác API binary nào được kiểm.

Với monorepo cùng phát triển, `-pl -am` thường đúng và đơn giản hơn việc publish mọi snapshot sang repository chỉ để local compile.

### 17.1. `install` khác `package`

| Lệnh | Làm gì | Có làm artifact dùng được cho invocation khác qua local repo? |
| --- | --- | --- |
| `mvn package` | Tạo JAR ở module `target/` | Không mặc định |
| `mvn install` | Đi qua package rồi cài artifact vào local Maven repository | Có, trong môi trường local đó |
| `mvn deploy` | Theo lifecycle publish artifact lên configured remote repository | Có, cho consumers được cấp quyền |
| `mvn -pl :catalog-app -am verify` | Build selected reactor upstream + app trong một invocation | Không cần install để reactor dùng được |
| `mvn -f catalog-app/pom.xml verify` | Build child với repository-based resolution khi ngoài reactor | Cần artifact tương ứng có thể resolve |

Không sửa bằng `system` scope hoặc `systemPath` trỏ thẳng sang `../catalog-api/target/catalog-api.jar`; điều đó trói POM vào filesystem và khiến CI khó tái tạo.

## 18. Một vấn đề khác: parent POM resolve thất bại

Không phải mọi lỗi child standalone đều do sibling JAR. Nếu log là:

~~~text
Non-resolvable parent POM for ...
Could not find artifact com.example.catalog:catalog-parent:pom:1.0.0
and 'parent.relativePath' points at wrong local POM
~~~

thì **parent model** chưa resolve được; Maven chưa thể tính effective POM để biết dependencies/plugin rules.

Kiểm:

~~~xml
<parent>
    <groupId>com.example.catalog</groupId>
    <artifactId>catalog-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

`relativePath` phải trỏ đúng POM cha **và GAV POM đó phải khớp** với `<parent>`. Maven có default `../pom.xml` nếu không ghi `<relativePath>`; ghi explicit giúp intent rõ trong lab.

### 18.1. Child được tách sang repo riêng thì sao?

Nếu chỉ checkout `catalog-app` vào một folder không có root POM ở `../pom.xml`, muốn build độc lập phải có **parent POM** trong Maven repository hoặc thay quan hệ parent theo kiến trúc mới. Khi parent được publish, có thể dùng:

~~~xml
<relativePath/>
~~~

để yêu cầu Maven 3 tìm parent trong repositories thay vì tìm filesystem. **Đây là một quyết định phân phối POM**, không phải mẹo sửa sibling JAR.

Nếu parent POM chưa có trong repository, `<relativePath/>` chỉ làm Maven bỏ qua parent local và có thể khiến lỗi xảy ra sớm hơn. Cần chứng minh parent POM tồn tại đúng GAV trong repository được dùng.

### 18.2. Đừng nhầm parent với aggregator

Một POM có thể:
- Chỉ là aggregator (`<modules>`) mà không làm parent.
- Chỉ là parent (`<parent>` từ children) mà không aggregate.
- Là cả hai như root demo.

Nhiều projects tách hai vai trò để quản lý khác nhau. **`-am` chỉ giải quyết selected reactor graph**, không biến một missing parent POM bên ngoài root thành classpath artifact.

## 19. Sai GAV và version làm Reactor không ghép được modules

Một dependency chỉ match project artifact khi coordinates tương ứng:

~~~text
groupId        com.example.catalog
artifactId     catalog-api
version        1.0.0
type           jar (mặc định)
classifier     không có
~~~

Nếu app khai báo:

~~~xml
<dependency>
    <groupId>com.example.catalog</groupId>
    <artifactId>catalog-api</artifactId>
    <version>1.0.1</version>
</dependency>
~~~

trong khi Reactor có API `1.0.0`, Maven phải tìm **một artifact khác**. Tương tự:
- Group `com.example` khác `com.example.catalog`.
- Artifact `catalog-api-test` khác `catalog-api`.
- `jar:tests` classifier khác main `jar`.
- Một module đổi version khi build theo profile nhưng consumer vẫn pin version cũ.

**`-am` không tự rewrite một GAV sai.** Sửa model/dependency declaration, profile và release version alignment; xem effective POM để biết version sau khi interpolation/management.

### 19.1. `dependencyManagement` không cung cấp artifact

Trong root:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.catalog</groupId>
            <artifactId>catalog-api</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

đây chỉ là **version policy**. Cần `<dependency>` trong app. Nếu dependency đã có nhưng API module không nằm trong reactor, POM version management **không** cài JAR hộ bạn.

### 19.2. BOM `import` có thể là một artifact thiếu khác

Một module có thể cần:

~~~xml
<dependency>
    <groupId>com.example.catalog</groupId>
    <artifactId>catalog-bom</artifactId>
    <version>1.0.0</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
~~~

**Đây là fragment nằm trong `<dependencyManagement><dependencies>`**, không phải ordinary runtime dependency. Nếu `catalog-bom` chỉ được cung cấp qua root reactor hoặc local repo, standalone model building có thể fail khi BOM không resolve được.

Publish BOM/parent POM đúng repo hoặc build đúng aggregator. Không cố loại BOM rồi hardcode những version tùy tiện để chỉ cho một máy build xanh.

## 20. `pluginManagement` và plugins tự viết trong Reactor

Một số multi-module projects có module tạo **Maven plugin**, annotation processor hoặc build extension dùng trong modules khác.

Reactor sorting có thể xét:
- Actual dependency giữa modules.
- **Plugin declaration** của một module trỏ đến plugin artifact được build bởi module khác.
- Plugin dependency hoặc build extension.
- Parent relation.
- `<modules>` order khi không có ràng buộc khác.

Nhưng **chỉ những references thực sự được instantiate** mới ảnh hưởng Reactor sorting. Một mục nằm riêng trong `dependencyManagement` hoặc `pluginManagement` **không tự tạo ordering edge**.

Khi build child standalone, missing artifact có thể là:

~~~text
Plugin org.example:internal-codegen-plugin:1.0.0
or one of its dependencies could not be resolved
~~~

Đây là **plugin resolution**, không giống API `jar` dependency resolution. Nếu plugin tự viết chỉ nằm trong Reactor, child alone cần plugin đã install/deploy, hoặc cần build từ root reactor phù hợp.

### 20.1. Plugin chạy ở phase nào cũng quan trọng

Ví dụ generated sources được tạo ở `generate-sources`, nhưng build riêng chạy một goal khác mà bỏ phase đó. Compiler có thể fail `cannot find symbol` dù artifact dependency chính không thiếu.

Đọc lifecycle/plugin executions: `mvn test` đi qua `generate-sources`, `compile`, `test-compile`, `test` theo binding; gọi `mvn compiler:compile` trực tiếp **không tự chạy mọi goal trước compile** trong POM. Trước khi kết luận reactor khác standalone chỉ vì module selection, so **lệnh/phases/profiles được chạy**.

## 21. Test JAR và classifier: một biến thể khó hơn main JAR

Có projects chia sẻ test helpers qua một module có Maven JAR Plugin `test-jar` execution. Consumer khai báo:

~~~xml
<dependency>
    <groupId>com.example.catalog</groupId>
    <artifactId>catalog-api</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
~~~

Đây chỉ là fragment minh họa; demo runnable **không** dùng test-jar. Artifact có classifier `tests` và thường được attach trong phase `package` theo cấu hình plugin.

Nếu consumer test compile cần classified test JAR **trước khi producer đã attach nó**, chỉ có module trong Reactor chưa đủ để bảo đảm artifact đã sẵn ở phase cần. Một số multi-module setups có lifecycle timing vấn đề ngay cả khi `-am`.

Phân tích:
1. Artifact là **main jar** hay `test-jar` classifier?
2. Producer có execution tạo classifier đúng không?
3. Artifact được attach ở phase nào?
4. Consumer cần nó tại `test-compile` hay integration-test?
5. Build phase target có đi đủ để producer tạo artifact không?
6. Có thể thay shared test helpers bằng module `test-support` JAR chính riêng để tránh phase coupling không?

Không đổi `type=test-jar` thành default `jar` nếu thực sự cần tests helper mà main JAR không chứa.

## 22. Một cách kiểm tra từ Maven local repository sạch

Dù app standalone pass trên máy cá nhân, bạn có thể chưa biết nó đang dùng artifact nào. Một môi trường local repository cách ly giúp phát hiện dependency nội bộ bị che bởi cache.

POSIX minh họa:

~~~bash
mvn -B -ntp -Dmaven.repo.local=/tmp/catalog-isolated-m2 -pl :catalog-app -am clean verify
~~~

Chạy từ root. Một local repo mới có thể cần tải Maven plugins và JUnit từ Internet/internal mirror. **Nếu network unavailable, lỗi tải plugin không phải bằng chứng sibling artifact thiếu**.

Để thử standalone tương ứng (Maven 3):

~~~bash
mvn -B -ntp -Dmaven.repo.local=/tmp/catalog-isolated-m2 -f catalog-app/pom.xml clean verify
~~~

Lần đầu với `-pl -am` **không tự install API** vào local repo cách ly, nên standalone vẫn có thể fail vì API JAR chưa available. Tuy nhiên nếu đã có remote repository cung cấp API (hoặc người dùng đã chạy install), lệnh có thể pass. Đây là mục tiêu của phép thử: tách **reactor availability** khỏi **repository availability**.

**Không dùng đường dẫn `/tmp/...` trên Windows nguyên văn.** PowerShell có thể dùng một thư mục cách ly được quyền ghi, chẳng hạn `C:\temp\catalog-isolated-m2`, và chọn đường dẫn này trong `-Dmaven.repo.local=...`.

### 22.1. Đừng xóa bừa `~/.m2/repository`

Local Maven repository có thể lớn và dùng chung nhiều dự án. Không cần xóa nó để debug. Dùng một temporary repo path riêng cho thử nghiệm, hoặc quan sát artifact coordinates/provenance trước. Nếu cần cleanup, chỉ xóa chính thư mục thử nghiệm đã xác nhận đường dẫn an toàn.

## 23. `mvn dependency:tree` và effective POM

Để kiểm app dependency đã được model đúng, từ root có thể chạy:

~~~bash
mvn -B -ntp -pl :catalog-app -am dependency:tree
~~~

Điều cần tìm ở app's dependency tree là:

~~~text
com.example.catalog:catalog-app:jar:1.0.0
  com.example.catalog:catalog-api:jar:1.0.0:compile
~~~

Đây chỉ là **trích dạng ý nghĩa**; logs thực tế còn có JUnit test dependency và các dòng khác. `dependency:tree` không thay runtime tests.

Để xem effective POM của app ở root:

~~~bash
mvn -B -ntp -pl :catalog-app help:effective-pom
~~~

Kiểm:
- Parent POM được thừa hưởng chưa.
- `groupId`, `artifactId`, `version`, `packaging` sau interpolation.
- Dependency `catalog-api` có version `1.0.0` không.
- Compiler/Surefire/JAR plugin versions, executions và profiles.
- Repository/mirror settings (lưu ý diagnostics có thể chứa thông tin nội bộ).

**Không in secrets khi debug `settings.xml`.** `mvn -X` hoặc `help:effective-settings` có thể ghi thông tin nhạy cảm trong environments có credentials. Dùng diagnostics hẹp, redact trước khi chia sẻ logs.

### 23.1. Một loại lỗi do negative caching

Nếu Maven đã cố tìm `catalog-api:1.0.0` trong remote repo và nhận “not found”, nó có thể cache kết quả resolution failure với `.lastUpdated` metadata. Người dùng đôi khi thử:

~~~bash
mvn -U -B -ntp -f catalog-app/pom.xml verify
~~~

`-U` yêu cầu cập nhật checks cho snapshots/metadata và có thể giúp retry resolution khi remote đã được publish. **Nó không tự tạo artifact chưa tồn tại** và không thay `-am`, `install` hoặc `deploy`.

Nếu artifact là release chưa có trên bất kỳ repo nào, lệnh vẫn fail dù `-U`.

## 24. CI: đừng chạy child POM khi source sibling đang ở cùng checkout

Một CI step không tối ưu:

~~~yaml
- name: Build only catalog app from child POM
  run: mvn -B -ntp -f catalog-app/pom.xml clean verify
~~~

Nếu Jenkins/GitHub Actions/GitLab CI checkout cả monorepo nhưng chạy Maven 3 từ POM child, nó có thể thiếu API artifact chưa publish.

Step đề xuất cho monorepo:

~~~yaml
- name: Verify app and required reactor modules
  run: mvn -B -ntp -pl :catalog-app -am clean verify
~~~

Điều kiện: CI working directory phải là **aggregator root**. Nếu script `cd catalog-app`, thì cùng chuỗi `-pl :catalog-app -am` không chắc có root reactor như mong muốn trong Maven 3.

### 24.1. Ví dụ GitHub Actions workflow cho Maven 3/JDK17

~~~yaml
name: Catalog Maven reactor verification

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify-app:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Record Maven environment
        run: |
          mvn -version
          java -version

      - name: Verify selected module with upstream
        run: mvn -B -ntp -pl :catalog-app -am clean verify
~~~

Workflow này dùng Maven mà CI runner cung cấp. **Nếu cần cố định Maven chính xác**, dùng Maven Wrapper đã commit hoặc toolchain setup trong workflow. Ví dụ ở đây nhắm vào Maven 3 semantics; trên runner Maven 4, behavior root discovery khác và phải đối chiếu docs/compatibility.

`cache: maven` của `setup-java` chủ yếu cache dependencies dưới Maven local repository, **không tự bật reactor hoặc lấy API sibling source vào graph**. Chính `-pl ... -am` mới giải quyết upstream trong build hiện tại.

### 24.2. Nếu CI cố tình chỉ checkout app module?

Khi `catalog-api` source không được checkout, không có root aggregator và cần build app độc lập, **đúng giải pháp là phân phối API artifact + parent POM** vào repository được phép, không thể dùng `-am` tạo một module không tồn tại.

Đó là thay đổi kiến trúc release/dependency management, không chỉ CLI typo.

## 25. Maven 4: không áp dụng máy móc cách giải thích của Maven 3

**Điểm phiên bản rất quan trọng:** tài liệu chính thức Maven 4 mô tả cơ chế **tìm project root** từ POM hiện tại bằng cách đi ngược lên các thư mục cho đến POM root có `.mvn` sibling hoặc root attribute thích hợp. Điều này cho phép Maven 4 tìm sibling subprojects ngay cả khi invocation bắt đầu trong module con.

Maven 4 cũng có **project-local repository** tại vị trí tương tự:

~~~text
.mvn/target/project-local-repo
~~~

trong root project. Theo tài liệu Maven 4, sau khi một reactor build đạt `package` hoặc phase muộn hơn, artifacts của subprojects có thể được lưu ở project-local repository, hỗ trợ việc dùng lại chúng trong những invocation khác của cùng multi-project setup.

Vì vậy trên Maven 4, chỉ dựa vào:

~~~bash
mvn -f catalog-app/pom.xml verify
~~~

để dự đoán chắc chắn fail là **không chính xác**. Maven 4 có thể tìm root, làm selection khác hoặc resolve sibling từ project-local repo đã được build trước đó.

Cần xác minh:
1. `mvn -version` cho biết Maven major 3 hay 4.
2. Root project được Maven 4 tìm thấy chưa (`.mvn`/root marker).
3. Project-local repo có artifact đúng GAV sau package không.
4. Trước đó đã build phase nào (`compile` chưa chắc lưu artifact; `package` có thể đã lưu).
5. `mvn clean` có xóa project-local outputs/cache liên quan không.
6. Invocation đang bắt đầu từ POM nào và selected subprojects nào.
7. Dependency graph và GAV có khớp không.

**Bài lab và cách tái hiện lỗi child standalone ở các phần trước đặt trọng tâm vào Maven 3.9+**, không nhận định Maven 4 sai khi hành vi khác. Khi nâng Maven major, phải kiểm lại scripts, workflows và local/CI reproducibility.

## 26. Thứ tự debug nên bắt đầu từ lỗi đầu tiên, không từ log cuối

Khi build module riêng thất bại:

**Bước 1 — ghi chính xác hai lệnh đối chiếu:**

~~~bash
mvn -B -ntp -f pom.xml clean verify
mvn -B -ntp -f catalog-app/pom.xml clean verify
~~~

**Bước 2 — kiểm phiên bản Maven/JDK và working directory:**

~~~bash
mvn -version
java -version
~~~

**Bước 3 — phân loại failed artifact:**
- Parent POM?
- Sibling `jar` dependency?
- BOM `pom` import?
- Maven plugin/extension?
- Attached classifier `test-jar`?
- Generated source/resources?

**Bước 4 — đối chiếu effective GAV**, không đoán theo folder name.

**Bước 5 — chọn hướng xử lý theo mục tiêu:**
- Monorepo: dùng root reactor với `-pl ... -am`.
- Independent repo/CI checkout: publish upstream/parent/BOM đúng repository.
- Version mismatch: sửa GAV, profiles, dependencyManagement.
- Plugin execution/codegen: sửa phase/goal/configuration.
- Maven4: xem root/project-local-repo specifics.

**Bước 6 — xác minh từ môi trường sạch** và chạy tests, không chỉ compile.

Một lỗi “Could not resolve dependencies” thường xuất hiện trước compiler/tests. Đừng debug Java source khi Maven còn chưa có JAR cần để tạo compile classpath.

## 27. Bảng lỗi nhanh

| Triệu chứng | Nguyên nhân có thể | Điều nên kiểm |
| --- | --- | --- |
| Root Reactor pass, child standalone fail missing API JAR | API chỉ có trong Reactor, chưa install/deploy | `-pl :app -am` hoặc artifact repo |
| `Non-resolvable parent POM` | Parent path/GAV/repo sai | `<parent>`, `<relativePath>`, parent availability |
| `Could not find artifact ...:pom` | Parent/BOM descriptor chưa có | Effective POM, BOM import, repositories |
| `Could not find artifact ...:jar` | Dependency không có repo hoặc GAV lệch | GAV, reactor module list, `-am` |
| Root `package` pass nhưng child fail | Package không install vào local repo (Maven 3) | `install` vs `package` |
| Laptop child pass nhưng CI fail | Local repo có artifact cũ từ `install` | Isolated local repo, provenance |
| `-pl :app` fail, `-pl :app -am` pass | Thiếu upstream modules trong selection | Dùng `-am` từ root |
| `-amd` không fix app missing API | `-amd` chọn downstream | Phân biệt `-am` |
| `-rf :app` sau failure không resolve API | Resume không build earlier prereqs | Chọn lại root + upstream |
| Package import missing dù API folder tồn tại | App POM không khai báo `<dependency>` | Dependencies vs modules |
| Plugin not found | Internal plugin chỉ có trong Reactor hoặc không deploy | Plugin artifacts, plugin repo |
| `cannot find symbol` generated class | Plugin generate-sources không chạy/khác profile | Lifecycle, executions, generated-sources |
| JUnit test-jar missing | Classifier/phase/attachment mismatch | `type=test-jar`, producer package |
| `UnsupportedClassVersionError` | JDK runtime thấp hơn classfile | `mvn -version`, compiler release, javap |
| HTTP 401/403 repo | Credentials/repository permissions | Server id/settings/secret scopes |
| `-o` build fail | Offline repo không chứa artifact/plugin | Offline mode vs actual repo |
| `-U` vẫn fail | Artifact thực tế không tồn tại | Publish GAV hoặc reactor build |
| Maven 4 child khác Maven 3 | Root discovery/project-local-repo | Maven 4 docs và root marker |
| `-fn` CI xanh giả | Fail-never bỏ exit failure | Không dùng với protected checks |
| Root POM `packaging=jar` và modules lỗi | Aggregator packaging sai | Đặt aggregator `pom` |
| Reactor cycle detected | Dependency graph có vòng | Tách module/rào kiến trúc, không dùng `-am` để chữa |
| `Could not find artifact` version khác | POM dependency version không khớp module | So exact GAV/effective model |
| POM chỉ có dependencyManagement | Chưa tạo dependency edge thật | Thêm `<dependency>` đúng trong consumer |

## 28. Lưu ý về plugins/phases khi các lệnh không thật sự tương đương

Để đối chiếu root vs child, hai invocations nên:
- Dùng cùng Maven major/version, Java/JDK, profiles và properties.
- Đều chạy `clean verify` hoặc ít nhất cùng lifecycle target.
- Không một bên `-DskipTests` còn bên kia chạy tests.
- Dùng cùng repository/mirror/credentials/flags.
- Ghi working directory và selected modules.
- Đọc modules được liệt kê trong reactor summary.
- Xác minh local repository có từng artifact trước/sau không.

Một lần `mvn -f root/pom.xml package` và một lần `mvn -f app/pom.xml test` không phải hai phép thử hoàn toàn tương đương; mục tiêu phases khác. Nếu root build có active profile tạo generated sources còn child build không có, lỗi có thể nằm ở **profile activation**, không phải Reactor artifact availability.

### 28.1. Environment-dependent profiles

Một POM có profile active theo JDK, OS, property hoặc file presence. Khi chạy root và child ở working directories khác nhau, file-based activation hoặc relative paths có thể chọn profile khác; plugin configuration sẽ thay đổi.

Kiểm:

~~~bash
mvn -B -ntp help:active-profiles
mvn -B -ntp -f catalog-app/pom.xml help:active-profiles
~~~

Đừng chỉ nhìn source Java giống nhau rồi bỏ qua differences trong effective model/profiles.

### 28.2. Maven Wrapper và version drift

Nếu root CI dùng `./mvnw` với Maven 3 nhưng local child command dùng system `mvn` Maven4, bạn đang so hai engines khác nhau. Pin Maven distribution và in `mvn -version` trong mỗi environment. Dữ liệu từ Maven4 project-local-repo sẽ làm kết luận Maven3 sai nếu không phân biệt.

## 29. Quyết định sửa lỗi theo mục tiêu công việc

| Mục tiêu | Giải pháp phù hợp | Vì sao |
| --- | --- | --- |
| Chỉ cần nhanh build app trong monorepo | Root `-pl :catalog-app -am verify` | Build upstream cần thiết trong Reactor |
| Build toàn bộ source | Root `mvn clean verify` | Full Reactor verification |
| Làm API độc lập, app ở repo khác | Publish API JAR + POM và parent/BOM cần thiết | Consumer resolve từ repository có thể tái tạo |
| Debug version mismatch | So exact GAV, effective POM, profiles | Reactor không map sai version |
| Child standalone fail parent | Sửa `relativePath` hoặc publish parent POM | Parent model resolution là lỗi riêng |
| Build trên agent sạch | Dùng Reactor hoặc repo được phê duyệt | Không phụ thuộc laptop local install |
| Chỉ muốn kiểm test class trong module | Reactor `-pl :catalog-app -am -Dtest=...` cần policy về tests upstream | Không bỏ upstream/tests ngoài ý muốn |
| Tiếp tục sau lỗi Reactor | Review `-rf` kết hợp selection/upstream | Resume không phải build-from-scratch |
| Nâng từ Maven3 lên4 | Kiểm root marker/project-local-repo và semantics | Lệnh child có thể hành xử khác |
| Giảm thời gian CI | `-pl -am` + measured cache policy | Không sửa dependency bằng `-DskipTests` |

**Không có một flag duy nhất chữa mọi loại lỗi.** Xác định missing artifact là parent, sibling JAR, BOM, plugin hay classified attachment trước; sau đó chọn Reactor hoặc repository model đúng với cách team phân phối code.

## 30. Câu hỏi tự kiểm tra

**Câu 1.** Root Reactor `mvn verify` pass có nghĩa mọi child build riêng luôn pass không?

**Đáp:** Không. Reactor cung cấp các modules nội bộ trong cùng invocation; standalone cần resolve dependencies/parent theo context của nó.

**Câu 2.** `-pl :catalog-app` làm gì?

**Đáp:** Chọn project `catalog-app` theo artifactId; không tự kèm upstream dependencies.

**Câu 3.** `-am` và `-amd` khác nhau thế nào?

**Đáp:** `-am` build các reactor dependencies của project được chọn; `-amd` build các projects phụ thuộc vào project đó.

**Câu 4.** Vì sao Maven có thể build API trước app dù `<modules>` liệt kê app trước?

**Đáp:** Reactor sorting ưu tiên actual project dependencies, không chỉ thứ tự khai báo.

**Câu 5.** `dependencyManagement` có tự thêm API vào app classpath không?

**Đáp:** Không. Phải có `<dependency>` trong app.

**Câu 6.** `mvn package` đã install API vào `~/.m2` chưa?

**Đáp:** Không theo Maven 3 lifecycle mặc định. `install` mới cài vào local repository.

**Câu 7.** Nếu laptop standalone pass còn CI sạch fail, nên kiểm gì?

**Đáp:** Artifact API/parent/BOM có tồn tại trong laptop local repo do build trước không, và CI lấy dependency từ đâu.

**Câu 8.** `-U` có tự tạo một JAR chưa từng được publish không?

**Đáp:** Không. Nó chỉ ảnh hưởng retry/update resolution trong phạm vi thích hợp.

**Câu 9.** `relativePath` giải quyết gì?

**Đáp:** Tìm parent POM trên filesystem cho inheritance; không tự tạo sibling JAR.

**Câu 10.** Nếu chỉ checkout `catalog-app`, `-am` có tự dựng API source không?

**Đáp:** Không. Source module phải có trong reactor; nếu không cần repository artifact đã publish.

**Câu 11.** `pluginManagement` có tự sắp xếp Reactor như một plugin dependency thực tế không?

**Đáp:** Không. Chỉ các instantiated references được Maven Reactor sorting xét.

**Câu 12.** `NoClassDefFoundError` khi tự gọi `java -cp` thường khác gì `Could not find artifact`?

**Đáp:** Lỗi đầu ở runtime classpath; lỗi sau xảy ra trong Maven artifact resolution.

**Câu 13.** Vì sao Maven4 có thể khác Maven3 khi chạy từ child?

**Đáp:** Maven4 có root discovery và project-local repository; nó có thể thấy/reuse siblings ngoài pattern Maven3.

**Câu 14.** `mvn -rf :catalog-app` có luôn build lại API không?

**Đáp:** Không. Resume có thể bỏ các modules đã đi qua; kiểm upstream availability và dùng root selection phù hợp.

**Câu 15.** API JAR `1.0.0` có thỏa app đang yêu cầu `1.0.1` không?

**Đáp:** Không. Version là một phần artifact coordinates.

**Câu 16.** Nếu Maven log là `Non-resolvable parent POM`, có nên chỉ thêm API dependency không?

**Đáp:** Không. Phải giải quyết parent POM trước.

**Câu 17.** Có nên sửa lỗi bằng `systemPath=../catalog-api/target/...`?

**Đáp:** Không. Nó phụ thuộc local filesystem và làm build thiếu tính tái tạo.

**Câu 18.** Vì sao phải kiểm test-jar classifier?

**Đáp:** Classified artifact không giống main JAR, và có thể chỉ được tạo/attach ở phase package.

**Câu 19.** `mvn -fn` có phù hợp với required CI checks?

**Đáp:** Không. Nó có thể cho exit code thành công dù modules bị lỗi.

**Câu 20.** Cách kiểm app từ monorepo mà không cần install API local trước là gì?

**Đáp:** Từ aggregator root, `mvn -B -ntp -pl :catalog-app -am clean verify`.

## 31. Checklist khắc phục triệt để

1. Ghi hai lệnh root và child gây khác biệt.
2. Chạy `mvn -version` để phân biệt Maven3/Maven4.
3. Ghi Java/JDK/OS/profiles/working directory và effective CLI flags.
4. Xác minh root aggregator có `packaging=pom`.
5. Kiểm `<modules>` chứa đúng sibling source modules.
6. Kiểm GAV parent, child và dependency chính xác.
7. Không suy luận dependency chỉ từ tên folder.
8. Kiểm `<dependencies>` trong consumer, không chỉ dependencyManagement.
9. Đọc reactor summary để biết modules build và thứ tự.
10. Nếu xây trong monorepo, thử `-pl :catalog-app -am`.
11. Không nhầm `-am` và `-amd`.
12. Tránh `-N` khi thật sự cần siblings.
13. Cẩn trọng với `-rf` resume và missing upstream.
14. Kiểm parent `<relativePath>` với tọa độ parent.
15. Với standalone checkout, publish parent POM nếu cần.
16. Với standalone dependency, publish API JAR/POM đúng GAV.
17. Nếu dùng BOM, bảo đảm BOM import POM resolve được.
18. Với internal plugins, kiểm plugin artifacts/pluginRepositories.
19. Kiểm generated-sources goals và active profiles.
20. Kiểm classified `test-jar` và phase attachment.
21. Tách runtime classpath lỗi khỏi Maven resolution lỗi.
22. Không dùng `systemPath` để che missing repository artifact.
23. Không dùng `-DskipTests` thay QA.
24. Không dùng `-fn` ở protected CI checks.
25. Dùng local repo cách ly để phát hiện cache che lỗi.
26. Đừng xóa toàn bộ Maven local repository bừa bãi.
27. Dùng `dependency:tree` và `help:effective-pom`.
28. Nếu `-U` không giúp, kiểm artifact có tồn tại thật không.
29. Với Maven4, kiểm root discovery và project-local repository.
30. Chạy Maven từ đúng aggregator root trong CI.
31. Pin Java/Maven/plugin versions nếu cần reproducibility.
32. Kiểm API classpath, run smoke test sau compile.
33. Kiểm Surefire reports của API và app (demo tổng 4 tests).
34. Khi tách modules thành repositories riêng, thiết kế publication/versions.
35. Xác nhận kết quả cuối trên CI agent sạch, không chỉ laptop.

## Tài liệu tham khảo chính thức

- [Apache Maven 3 — Guide to Working with Multiple Modules (Reactor)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven 4 — Guide to Working with Multiple Subprojects](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [Apache Maven — Introduction to the POM (Aggregation and Inheritance)](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference (`parent.relativePath`, dependencies, dependencyManagement)](https://maven.apache.org/pom.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Reactor Build Order](https://maven.apache.org/guides/mini/guide-multiple-modules.html#the-reactor)
- [Apache Maven — Build Lifecycle: package, install, deploy](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Maven CLI Options](https://maven.apache.org/ref/current/maven-embedder/cli.html)
- [Apache Maven — Local Repository](https://maven.apache.org/repositories/local.html)
- [Apache Maven Compiler Plugin — Set --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven Surefire Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-plugin/usage.html)
- [Apache Maven Dependency Plugin — Dependency Tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Help Plugin — Effective POM](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.11.4/user-guide/)

