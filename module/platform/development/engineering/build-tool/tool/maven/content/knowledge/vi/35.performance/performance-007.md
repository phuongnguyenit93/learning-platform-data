# Chọn đúng mô-đun cần build và hiểu phạm vi kiểm chứng bị giảm trong Maven

## 1. Vì sao build nhanh chưa chắc kiểm chứng đủ?

Trong nhóm **Hiệu năng**, Maven multi-module cho phép nhà phát triển chỉ biên dịch và kiểm thử phần họ cần thay vì luôn build cả repository. Đó là ưu điểm lớn khi một dự án có nhiều modules, nhưng cần phân biệt:

- **Build thành công cho một module**: chỉ các phase/plugin goals của module được chọn đã chạy thành công.
- **Build thành công cho module và các upstream dependencies**: đã kiểm tra tập upstream mà Maven reactor nhận diện, nhưng chưa kiểm tra mọi consumer downstream.
- **Build thành công cho module và downstream dependents**: đã mở rộng phạm vi sang modules phụ thuộc vào code được sửa, nhưng vẫn không bảo đảm mọi module độc lập hoặc runtime integration đã được test.
- **Full reactor thành công**: tất cả modules do root aggregator thu thập đã đi qua các phases/goals được cấu hình, nhưng external end-to-end/security checks chưa cấu hình vẫn không tự chạy.

Ví dụ:

```text
root (pom)
├── math-core ──> pricing-service ──> store-cli
└── analytics  (không có dependency edge với các module trên)
```

Chiều mũi tên: consumer nằm bên phải **phụ thuộc** provider bên trái.

Nếu chỉ build store-cli cùng upstream, test của analytics không chạy. Nếu chỉ test math-core, thay đổi API/behavior của math-core có thể khiến pricing-service và store-cli hỏng nhưng không được phát hiện.

**Thông điệp cốt lõi:** Maven `-pl`, `-am` và `-amd` là công cụ **chọn phạm vi build**. Mỗi lệnh partial green phải được ghi rõ **những gì đã và chưa kiểm chứng**; đừng tuyên bố một phần là toàn bộ.

Mục tiêu bài này:
1. Hiểu Maven reactor thu thập, sắp xếp và build modules thế nào.
2. Dùng `-pl`, `-am`, `-amd`, `-rf`, `-N`, `-f` đúng ngữ nghĩa.
3. Xây project Maven Java 17 có 4 Java modules và 8 JUnit tests.
4. Tự chứng minh một partial build có thể PASS khi một module khác FAIL.
5. Tự chứng minh chỉ chạy test ở core có thể bỏ sót regression downstream.
6. Xây CI policy fast-feedback đi kèm full-verification gate, không hy sinh an toàn để rút ngắn thời gian.

Ví dụ dùng Maven **3.9.x**, Java **17**, Surefire **3.5.2** và JUnit Jupiter **5.11.4**. Các version ghim để ví dụ nhất quán, không khẳng định chúng là phiên bản mới nhất.

## 2. Aggregator, parent và Maven reactor

Trong Maven, một root POM có thể khai báo modules:

```xml
<packaging>pom</packaging>
<modules>
    <module>math-core</module>
    <module>pricing-service</module>
    <module>store-cli</module>
</modules>
```

Khi chạy Maven từ root, **reactor**:
- **Collects** các module trong aggregator, bao gồm modules ở những cấp lồng nhau.
- **Sorts** chúng theo dependency/parent/plugin/extension relationships có thật.
- **Builds** đúng tập được chọn theo CLI options.

Aggregation (`<modules>`) và inheritance (`<parent>`) là **hai khái niệm khác nhau**: một child có thể kế thừa parent mà không được aggregator hiện tại thu thập, hoặc được aggregator thu thập mà không kế thừa root làm parent.

### 2.1. Thứ tự trong <modules> không thay dependency graph

Maven reactor sorts theo:
- Project dependency của module A vào module B trong cùng reactor.
- Plugin declaration khi plugin thực sự là project của reactor.
- Plugin dependency, build extension và quan hệ parent trong reactor.
- Thứ tự `<modules>` khi không có quan hệ nào khác buộc ưu tiên.

Vì vậy, ngay cả khi root POM liệt kê `store-cli` trước `math-core`, Maven vẫn build math-core trước pricing-service rồi store-cli khi dependencies được khai báo.

**Đừng nhầm:** chỉ khai báo version tại `dependencyManagement` hoặc `pluginManagement` **không tạo ra instantiated dependency edge** cho reactor sort. Muốn có quan hệ runtime/build thật thì các module phải khai báo dependency/plugin tương ứng.

### 2.2. Maven graph không phải toàn bộ kiến trúc hệ thống

Một module HTTP client gọi service bằng URL, test contract dùng shared JSON file, database migration hoặc message consumer không có Maven dependency trực tiếp vẫn có thể chịu tác động khi code thay đổi. Reactor **không tự suy ra toàn bộ runtime graph**. Điều này là lý do `-amd` có thể hữu ích nhưng không thay thế full/integration/contract tests.

## 3. Bảng các CLI options

| Viết tắt | Tên đầy đủ | Ý nghĩa | Cảnh báo |
| --- | --- | --- | --- |
| `-pl` | `--projects` | Chọn modules cụ thể trong reactor | Không tự kéo upstream/downstream |
| `-am` | `--also-make` | Build thêm các reactor dependencies cần thiết cho tập đã chọn | Không tự build consumer |
| `-amd` | `--also-make-dependents` | Build thêm các reactor projects phụ thuộc vào tập đã chọn | Upstream khác có thể cần build |
| `-rf` | `--resume-from` | Resume từ một module trong thứ tự reactor | Không tính lại dependency closure |
| `-N` | `--non-recursive` | Chỉ build current POM, không descend modules | Root-only PASS không phải full PASS |
| `-f` | `--file` | Chỉ ra POM khởi đầu | Child POM không mặc nhiên thu thập siblings |
| `-ff` | `--fail-fast` | Dừng sớm khi lỗi, mặc định | Modules sau có thể chưa chạy |
| `-fae` | `--fail-at-end` | Tiếp tục những modules còn có thể build, báo FAIL cuối | Phụ thuộc failed module vẫn có thể SKIPPED |
| `-fn` | `--fail-never` | Giữ exit code 0 ngay cả khi module FAIL | **Không dùng cho required CI gates** |
| `-T` | `--threads` | Parallelize các modules độc lập | Không thay test selection, cần thread-safe plugins |

### 3.1. -pl chọn path hoặc tọa độ project

Từ reactor root:

```bash
mvn -pl store-cli verify
mvn -pl :store-cli verify
mvn -pl dev.course:store-cli verify
mvn -pl :math-core,:analytics verify
```

- `store-cli` là **relative path** của module.
- `:store-cli` chọn `artifactId=store-cli`.
- `dev.course:store-cli` chọn tọa độ groupId:artifactId.
- Dấu phẩy cho phép chọn nhiều projects.

Chọn theo path và artifactId không phải lúc nào cũng đồng nghĩa: thư mục có thể mang tên khác artifactId. Nếu Maven báo project không nằm trong reactor, kiểm tra root aggregator, module path, groupId và artifactId.

### 3.2. -am: mở rộng về phía dependencies (upstream)

```bash
mvn -pl :store-cli -am clean verify
```

Với graph ở bài:
- math-core được chọn vì pricing-service cần nó.
- pricing-service được chọn vì store-cli cần nó.
- store-cli là module yêu cầu.
- analytics vẫn **không được chọn** vì độc lập.

Một parent POM cũng có thể nằm trong tập build vì quan hệ parent; khi đánh giá số Java tests, hãy đếm modules Java chứ không phải tất cả projects trong reactor summary.

`-am` **không tự build tất cả external dependencies** ở remote repository; nó chỉ thêm upstream projects **đang có trong reactor**, còn external artifacts được Maven resolve theo cấu hình repositories bình thường.

### 3.3. -amd: mở rộng về phía modules tiêu thụ (downstream)

```bash
mvn -pl :math-core -amd clean verify
```

Với graph ví dụ, có math-core, pricing-service và store-cli vì hai modules sau phụ thuộc trực tiếp/gián tiếp vào math-core. Analytics không bị chọn.

Đây là hướng thích hợp khi sửa shared library: build downstream có thể phát hiện lỗi không xuất hiện trong unit tests của thư viện đó.

**Cần nhớ:** những downstream modules có thể phụ thuộc các upstream khác không thuộc subset đã chọn; trong dự án lớn, cân nhắc thêm `-am` hoặc chạy full reactor để bảo đảm các artifact nội bộ có thể resolve từ source hiện tại.

### 3.4. Kết hợp -am và -amd

```bash
mvn -pl :math-core -amd -am clean verify
```

Ý đồ là chọn module gốc, các modules phụ thuộc vào nó và dependencies cần thiết. **Tập thực tế vẫn phải được xác minh ở Reactor Build Order/Summary**; không suy ra rằng tổ hợp này tương đương build toàn bộ repository.

### 3.5. -rf, -N và -f không thay thế -am

```bash
mvn -rf :pricing-service verify
mvn -N verify
mvn -f path/to/reactor-scope-lab/pom.xml -pl :store-cli -am verify
```

- `-rf` tiếp tục **theo thứ tự reactor** từ một project, không tự build lại upstream.
- `-N` chỉ xử lý POM hiện tại; ở root packaging=pom, children tests không chạy.
- `-f` định vị starting POM. Maven 3.9.x từ child POM không tự build sibling modules chỉ vì chúng dùng cùng parent; khi muốn full root reactor, trỏ tới root POM.

## 4. Ma trận phạm vi trong dự án ví dụ

Trong bảng, chỉ liệt kê 4 Java modules; root parent có thể được Maven chọn thêm tùy quan hệ.

| Lệnh | Java modules được kiểm tra | Java modules không được kiểm chứng |
| --- | --- | --- |
| `mvn clean verify` | math-core, pricing-service, store-cli, analytics | Không |
| `mvn -pl :store-cli verify` | store-cli (cần upstream artifacts đã resolve) | math-core, pricing-service, analytics |
| `mvn -pl :store-cli -am verify` | math-core, pricing-service, store-cli | analytics |
| `mvn -pl :math-core verify` | math-core | pricing-service, store-cli, analytics |
| `mvn -pl :math-core -amd verify` | math-core, pricing-service, store-cli | analytics |
| `mvn -pl :pricing-service -am verify` | math-core, pricing-service | store-cli, analytics |
| `mvn -pl :pricing-service -amd verify` | pricing-service, store-cli | math-core, analytics |
| `mvn -pl :analytics verify` | analytics | math-core, pricing-service, store-cli |
| `mvn -N verify` | Chỉ parent POM | Cả bốn Java modules |

**Các lệnh không có -am cần thận trọng với local repository.** Nếu build trước đã install một version nội bộ cũ, Maven có thể compile/test consumer với artifact đó thay vì source module mới nhất. Nếu local cache sạch và không có internal artifact, Maven có thể FAIL khi resolve dependency. Cả hai tình huống đều không có nghĩa source upstream hiện tại đã được kiểm chứng.

## 5. Cấu trúc dự án Maven Java 17 đầy đủ

Tạo trong một thư mục thí nghiệm mới:

```text
reactor-scope-lab/
├── pom.xml
├── math-core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/course/math/Calculator.java
│       └── test/java/dev/course/math/CalculatorTest.java
├── pricing-service/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/course/pricing/PriceService.java
│       └── test/java/dev/course/pricing/PriceServiceTest.java
├── store-cli/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/course/cli/App.java
│       └── test/java/dev/course/cli/AppTest.java
└── analytics/
    ├── pom.xml
    └── src/
        ├── main/java/dev/course/analytics/Stats.java
        └── test/java/dev/course/analytics/StatsTest.java
```

Lab có **4 Java modules × 2 unit tests = 8 unit tests**. Không dùng network service hoặc DB thật; lần Maven đầu có thể cần tải plugins/JUnit từ repository.

### 5.1. Root pom.xml

Tạo `reactor-scope-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.course</groupId>
    <artifactId>reactor-scope-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <!-- Consumer cố ý đứng trước provider -->
    <modules>
        <module>store-cli</module>
        <module>analytics</module>
        <module>pricing-service</module>
        <module>math-core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <!-- Cả 4 children đều cần JUnit để chạy unit tests -->
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Root đóng vai trò **aggregator và parent**. Các children kế thừa phiên bản Java, JUnit test dependency, Compiler/Surefire/JAR plugins. Root packaging=pom không tự có unit tests, cũng không phải JAR executable.

### 5.2. math-core/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.course</groupId>
        <artifactId>reactor-scope-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>math-core</artifactId>
    <packaging>jar</packaging>
</project>
```

### 5.3. pricing-service/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.course</groupId>
        <artifactId>reactor-scope-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>pricing-service</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>dev.course</groupId>
            <artifactId>math-core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

Dependency thật vào math-core tạo graph edge. Một version chỉ nằm trong `dependencyManagement` không tương đương với dependency đã được khai báo như ở đây.

### 5.4. store-cli/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.course</groupId>
        <artifactId>reactor-scope-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>store-cli</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>dev.course</groupId>
            <artifactId>pricing-service</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

store-cli phụ thuộc pricing-service; pricing-service lại phụ thuộc math-core. Maven sẽ build upstream modules trước consumer nếu chúng cùng tham gia reactor.

### 5.5. analytics/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.course</groupId>
        <artifactId>reactor-scope-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>analytics</artifactId>
    <packaging>jar</packaging>
</project>
```

analytics kế thừa root configuration nhưng **không có project dependency** với chuỗi math-core → pricing-service → store-cli, nên phép chọn module theo graph chuỗi này không tự kéo analytics.

## 6. Java source và unit tests

### 6.1. math-core/Calculator.java

```java
package dev.course.math;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static int multiply(int left, int right) {
        return left * right;
    }
}
```

Tệp tại `math-core/src/main/java/dev/course/math/Calculator.java`.

### 6.2. math-core/CalculatorTest.java

```java
package dev.course.math;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(7, Calculator.add(3, 4));
    }

    @Test
    void multipliesTwoNumbers() {
        assertEquals(12, Calculator.multiply(3, 4));
    }
}
```

Tệp tại `math-core/src/test/java/dev/course/math/CalculatorTest.java`. Có **2 unit tests**, chưa kiểm tra mọi đầu vào mà downstream consumers có thể dùng.

### 6.3. pricing-service/PriceService.java

```java
package dev.course.pricing;

import dev.course.math.Calculator;

public final class PriceService {
    private PriceService() {
    }

    public static int total(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "Giá và số lượng phải không âm");
        }
        return Calculator.multiply(unitPrice, quantity);
    }
}
```

Tệp tại `pricing-service/src/main/java/dev/course/pricing/PriceService.java`.

### 6.4. pricing-service/PriceServiceTest.java

```java
package dev.course.pricing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceServiceTest {
    @Test
    void totalsForStoreOrder() {
        assertEquals(36, PriceService.total(12, 3));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> PriceService.total(10, -1));
    }
}
```

Tệp tại `pricing-service/src/test/java/dev/course/pricing/PriceServiceTest.java`. Có **2 unit tests**; một case kiểm tra luồng consumer với 12×3.

### 6.5. store-cli/App.java

```java
package dev.course.cli;

import dev.course.pricing.PriceService;

public final class App {
    private App() {
    }

    public static String message() {
        return "TOTAL=" + PriceService.total(12, 3);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Tệp tại `store-cli/src/main/java/dev/course/cli/App.java`. Với classpath đầy đủ, stdout **chính xác**:

```text
TOTAL=36
```

### 6.6. store-cli/AppTest.java

```java
package dev.course.cli;

import dev.course.pricing.PriceService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void producesOrderSummary() {
        assertEquals("TOTAL=36", App.message());
    }

    @Test
    void pricesZeroQuantity() {
        assertEquals(0, PriceService.total(50, 0));
    }
}
```

Tệp tại `store-cli/src/test/java/dev/course/cli/AppTest.java`.

### 6.7. analytics/Stats.java

```java
package dev.course.analytics;

public final class Stats {
    private Stats() {
    }

    public static double average(int left, int right) {
        return ((double) left + right) / 2.0;
    }
}
```

Tệp tại `analytics/src/main/java/dev/course/analytics/Stats.java`.

### 6.8. analytics/StatsTest.java

```java
package dev.course.analytics;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StatsTest {
    @Test
    void computesAverage() {
        assertEquals(3.5, Stats.average(3, 4));
    }

    @Test
    void handlesZeroes() {
        assertEquals(0.0, Stats.average(0, 0));
    }
}
```

Tệp tại `analytics/src/test/java/dev/course/analytics/StatsTest.java`.

**Chốt số tests:** CalculatorTest 2 + PriceServiceTest 2 + AppTest 2 + StatsTest 2 = **8**. Các tests không yêu cầu database hoặc service ngoài, nên phù hợp lab về phạm vi reactor.

## 7. Mốc kiểm chứng chuẩn: build toàn bộ từ root

Từ thư mục `reactor-scope-lab`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Khi JDK/Maven/plugins resolve bình thường:
- Maven thu thập root + bốn children.
- math-core chạy trước pricing-service; pricing-service chạy trước store-cli.
- Analytics không có dependency edge với chuỗi trên; vị trí tương đối của analytics không cần cố định.
- Surefire chạy **2 tests trong mỗi Java module**, tổng **8 tests**.
- Maven build 4 ordinary JARs và in Reactor Summary.

Log minh họa rút gọn, **không phải full raw log**:

```text
math-core       Tests run: 2, Failures: 0
pricing-service Tests run: 2, Failures: 0
store-cli       Tests run: 2, Failures: 0
analytics       Tests run: 2, Failures: 0
BUILD SUCCESS
```

Để chạy Java main từ root trên Linux/macOS:

```bash
java -cp "store-cli/target/classes:pricing-service/target/classes:math-core/target/classes" dev.course.cli.App
```

Trên Windows PowerShell/cmd, separator classpath là dấu chấm phẩy:

```powershell
java -cp "store-cli/target/classes;pricing-service/target/classes;math-core/target/classes" dev.course.cli.App
```

Kết quả:

```text
TOTAL=36
```

Không mặc định chạy `java -jar store-cli/target/store-cli-1.0.0-SNAPSHOT.jar`, vì POM không cấu hình manifest `Main-Class` hay fat JAR. Lệnh `java -cp ...` ở trên phù hợp với source lab.

## 8. Partial build cho module ứng dụng

```bash
mvn -B -ntp -pl :store-cli -am clean verify
```

Các Java modules được chạy:
- math-core: 2 unit tests.
- pricing-service: 2 unit tests.
- store-cli: 2 unit tests.
- analytics: **NOT SELECTED**.

Kết quả trong healthy lab: **6 tests** PASS, Maven BUILD SUCCESS. Đây là **partial verification**. Việc analytics không có report mới không thể diễn giải là analytics đã PASS.

So với:

```bash
mvn -B -ntp -pl :store-cli clean verify
```

lệnh **không có -am** cần dependency artifacts của pricing-service/math-core đã resolve được từ local/remote repositories. Có hai khả năng:
1. Không có artifacts: Maven FAIL do dependency resolution, trước khi tests chạy.
2. Có artifacts cũ: Maven có thể dùng binaries stale và PASS, nhưng **không kiểm tra source upstream hiện tại**.

Nếu đang sửa project nhiều modules trong cùng Git tree, `-am` thường đáng tin hơn cho feedback của selected module.

## 9. Thí nghiệm 1: partial PASS khi module độc lập FAIL

Chỉ áp dụng trong project lab. Sửa tạm một assertion trong `analytics/StatsTest.java`:

Từ:

```java
assertEquals(3.5, Stats.average(3, 4));
```

sang:

```java
assertEquals(9.9, Stats.average(3, 4));
```

Vẫn compile được, nhưng Stats.average(3,4) thật ra trả 3.5 nên unit test `computesAverage` FAIL.

### 9.1. Chạy subset không có analytics

```bash
mvn -B -ntp -pl :store-cli -am clean verify
```

Expected:
- 6 tests của math-core, pricing-service, store-cli PASS.
- Analytics không được chọn nên **test lỗi không chạy**.
- Maven BUILD SUCCESS **cho tập được chọn**, không phải cho toàn dự án.

### 9.2. Chạy full reactor

```bash
mvn -B -ntp clean verify
```

Lúc này analytics test FAIL và Maven báo BUILD FAILURE khi tới module đó. Những module khác có thể chạy hoặc không tùy reactor order và fail-fast policy.

**Khôi phục assertion đúng**:

```java
assertEquals(3.5, Stats.average(3, 4));
```

Không commit mutation cố ý. Ý nghĩa: không được biến một build xanh vì **bỏ module** thành bằng chứng “toàn project đã PASS”.

## 10. Thí nghiệm 2: core PASS nhưng consumer có hồi quy

Một lỗi upstream có thể không được unit tests của chính upstream phát hiện.

Trong lab, `CalculatorTest` chỉ test phép nhân 3×4. Sửa tạm Calculator.multiply thành:

```java
public static int multiply(int left, int right) {
    int result = left * right;
    return left > 10 ? result - 1 : result;
}
```

Đây là **mutation giả lập lỗi**, không phải business logic hợp lệ.

- Core test `multiply(3,4)` vẫn trả 12 → PASS.
- PricingService test `total(12,3)` nay trả 35 thay vì 36 → FAIL.
- Store CLI message cũng bị ảnh hưởng, có thể trả TOTAL=35.

### 10.1. Chỉ build core

```bash
mvn -B -ntp -pl :math-core -am clean verify
```

Maven có thể BUILD SUCCESS vì math-core tests không cover case 12×3. Nhưng đó **không phải kiểm chứng consumer**.

### 10.2. Chạy downstream

```bash
mvn -B -ntp -pl :math-core -amd clean verify
```

Với graph mẫu, Maven thêm pricing-service và store-cli. PriceServiceTest phải phát hiện giá trị 35 ≠ 36 và FAIL; nếu Maven dừng fail-fast, AppTest có thể chưa chạy.

Trên reactor phức tạp có thể dùng:

```bash
mvn -B -ntp -pl :math-core -amd -am clean verify
```

để xem cả downstream và upstream dependencies cần thiết. Kiểm tra Reactor Build Order/Summary thay vì giả định lệnh bao phủ tất cả.

**Khôi phục Calculator.multiply**:

```java
public static int multiply(int left, int right) {
    return left * right;
}
```

Sau đó:

```bash
mvn -B -ntp clean verify
```

Kỳ vọng 8 tests PASS. Mutation này chứng minh **-am và -amd trả lời hai câu hỏi khác nhau**: build dependencies cần cho module đã chọn, và kiểm thử những consumers phụ thuộc module bị sửa.

## 11. -rf và failure modes: không hiểu nhầm resume

Nếu một module fail, Maven có thể gợi ý:

```bash
mvn -rf :pricing-service verify
```

Ý nghĩa: resume từ pricing-service **theo reactor order**. Nó không tự build lại tất cả upstream source nằm trước điểm resume và không phải thuật toán chọn tập downstream cần regression test.

Ví dụ math-core đã từng được build trong reactor thất bại nhưng chưa `install` vào local repo, chạy `-rf :pricing-service` có thể:
- Fail vì không tìm thấy math-core SNAPSHOT artifact.
- Dùng cached math-core artifact cũ từ local repository.
- Bỏ qua source thay đổi ở upstream sau lần build trước.

Khi cần xác minh từ source mới, thường an toàn hơn:

```bash
mvn -B -ntp -pl :pricing-service -am clean verify
```

Nếu thay đổi ảnh hưởng store-cli:

```bash
mvn -B -ntp -pl :pricing-service -amd -am clean verify
```

Hoặc full reactor khi cần release-level confidence.

### 11.1. -fae, -ff và -fn

- `-ff` (default): fail sớm, một số modules còn lại có thể SKIPPED.
- `-fae`: tiếp tục modules vẫn có thể build và báo failure cuối, hữu ích để thu nhiều kết quả lỗi.
- `-fn`: fail never, Maven có thể trả exit code 0 dù một module báo lỗi; **không dùng trong required CI jobs**, vì có thể che test failures.

Nếu muốn giữ reports khi build đỏ, CI có cơ chế upload chạy cả khi thất bại. Đừng bật fail-never chỉ để giữ logs.

## 12. Phạm vi tests và quality gates bị hẹp theo module selection

Các Maven phases chạy trên **tập selected projects**. Nếu module không được chọn, các plugin executions của nó không chạy.

| Loại kiểm chứng | Full reactor | -pl/-am/-amd partial |
| --- | --- | --- |
| Java compiler | Selected Java projects của toàn reactor | Selected subset |
| Surefire | Unit tests trong modules đã build | Unit tests chỉ của selected modules |
| Failsafe | Integration tests nếu plugin/executions đã cấu hình | IT ở các selected modules có cấu hình |
| Checkstyle/PMD/SpotBugs | Static analysis/gates nếu đã bật | Chỉ các modules được chọn có goal phù hợp |
| JaCoCo | Coverage theo modules được instrument/test | Coverage chỉ là subset |
| Aggregate reports | Phụ thuộc plugin và toàn bộ inputs | Có thể thiếu modules không build |
| Reactor Summary | Trạng thái các projects trong invocation | Không phải status của mọi module trong repository |

**POM lab chỉ cài Surefire, không cài Failsafe/JaCoCo/Checkstyle.** Vì thế gọi `verify` ở lab chỉ chạy những goals thực sự được bind, chứ không tự kích hoạt mọi kiểu quality gate.

Nếu dashboard coverage nhận JaCoCo data chỉ từ math-core/pricing-service/store-cli, không được trình bày đó là **coverage của cả analytics**. Các modules không có report mới phải được đánh dấu **NOT RUN/NOT VERIFIED**, không được suy luận zero failures.

### 12.1. Giới hạn của Maven dependency graph

Những liên kết này có thể không tạo `-amd` edge:
- HTTP/REST call giữa hai services không phụ thuộc nhau trong POM.
- Kafka/event payload hoặc queue schema shared qua file.
- Database migrations dùng chung.
- Reflection, ServiceLoader hoặc module được đọc bằng tên chuỗi.
- Frontend calling backend qua API contract.
- Shared CI scripts, parent POM, BOM, toolchain hoặc resource generator.

Do đó sau khi sửa shared infrastructure hoặc public contract, một narrow reactor có thể chưa đủ; cần explicit contract tests/e2e/full build.

## 13. Đọc Reactor Summary để báo cáo trung thực

Sau selective build, hãy ghi lại:

1. Maven command nguyên văn, gồm `-pl/-am/-amd/-rf/-N`.
2. Starting POM/root, Maven/JDK/tool versions.
3. Reactor Build Order (modules được thu thập và chọn).
4. Reactor Summary (SUCCESS, FAILURE, SKIPPED).
5. Test report counts và Maven goals thực sự được thực thi.
6. Modules **không được chọn**.
7. Các quality/integration gates không chạy hoặc chưa cấu hình.
8. CI job exit code, thay vì chỉ nhìn badge xanh.

Một báo cáo minh họa:

```text
Mode: PARTIAL_REACTOR
Command: mvn -B -ntp -pl :store-cli -am clean verify
Verified Java modules: math-core, pricing-service, store-cli
Not selected: analytics
Surefire tests: 6 passed (lab)
Failsafe IT: not configured in lab
Full repository verification: NOT CLAIMED
Maven result: BUILD SUCCESS
```

Đây là **định dạng báo cáo do nhóm đề xuất**, không phải Maven tự in nguyên văn. Khác biệt quan trọng: một module **NOT SELECTED** khác một module **SKIPPED sau failure**, và cả hai đều khác **PASS**.

## 14. CI strategy: nhanh ở PR, đầy đủ trước phát hành

Một chính sách thực tế có thể dùng hai lớp.

**Fast feedback trên pull request:**
- Xác định module chứa thay đổi.
- Chạy `-pl ... -am` để build dependencies nội bộ đang phát triển.
- Nếu sửa shared core, chạy thêm downstream `-amd` khi thích hợp.
- Ghi rõ những modules chưa được chạy.
- Khi path mapping hoặc impact không chắc, chạy full reactor.
- Không dùng skipTests hoặc fail-never như cách ép green.

**Full verification trên main/release hoặc trước merge theo policy:**
- Chạy root `mvn -B -ntp clean verify`.
- Chạy integration/contract/end-to-end/security gates đã cấu hình.
- Trường hợp thay parent POM, dependencyManagement, pluginManagement, BOM, wrapper/JDK/toolchain, API/schema hoặc CI scripts thường nên trigger full.
- Dùng metadata và reports để xác nhận mọi module cần thiết thực sự được kiểm chứng.
- Không deploy nếu full required gates fail.

### 14.1. GitHub Actions minh họa hai mức

Workflow sau là mẫu để hiểu phạm vi, **không tự suy ra changed modules**. Ví dụ fast job luôn chọn store-cli + upstream; full job chạy khi push main. Nếu tổ chức cần full verification **trước merge**, hãy mở rộng full job sang pull_request và đặt làm required check.

```yaml
name: Maven module-scope verification

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Fast feedback for store-cli
        run: mvn -B -ntp -pl :store-cli -am clean verify
      - name: Save reports from selected modules
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: partial-surefire
          path: '**/target/surefire-reports/'
          if-no-files-found: warn
          retention-days: 7

  full:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify entire reactor
        run: mvn -B -ntp clean verify
      - name: Save all generated reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: full-surefire
          path: '**/target/surefire-reports/'
          if-no-files-found: warn
          retention-days: 7
```

**Vì sao hai jobs khác nhau?** Fast job phát hiện lỗi sớm trong chuỗi store-cli; full job mới kiểm tra analytics. Upload-artifact giữ file XML khi Maven FAIL, **không tự sửa exit code hoặc tạo JUnit reports cho modules không chạy**.

Trong dự án thực, pin actions theo policy, kiểm soát retention và secrets; không đưa release credentials vào PR jobs không đáng tin.

### 14.2. Automatic changed-module selection cần fail closed

Khi triển khai script chọn modules từ Git diff:

- Map path đã đổi sang Maven module đúng, không suy luận bằng tên file.
- Các file shared (root POM, BOM, .mvn, wrapper, toolchains, plugin config, generated schema) có thể ảnh hưởng toàn reactor.
- Mở rộng upstream/downstream dựa trên graph thật.
- Bổ sung contract/test ownership map cho cross-service edges không trong Maven.
- Nếu không xác định được module bị ảnh hưởng, **full build** thay vì “chạy ít nhất cho nhanh”.
- Cho reviewer thấy selected và unselected modules; không đánh dấu omitted modules PASS.

Một PR chạm parent plugin version có thể làm tất cả module behavior đổi dù không sửa Java source nào. Đây là tình huống cần full verification rõ ràng.

## 15. Tối ưu hiệu năng nhưng phải đo đúng

Có thể so ba lệnh:

```bash
mvn -B -ntp clean verify
mvn -B -ntp -pl :store-cli -am clean verify
mvn -B -ntp -pl :math-core -amd clean verify
```

Ghi elapsed time, CPU, memory, cache state và số tests/modules thực sự chạy. Không tuyên bố “tiết kiệm X%” nếu chưa đo trong project thật.

So sánh có ý nghĩa khi:
- Cùng JDK/Maven/plugin versions và cấu hình build.
- Cùng loại runner hoặc được normalise theo hardware.
- Phân biệt cold cache với warm cache, tránh so hai môi trường khác hẳn.
- Dùng `clean` khi phép đo cần chắc chắn build output mới.
- Ghi chính xác phần verification được bỏ qua.

Một số lựa chọn khác như `-T 1C` (parallel reactor), compiler incrementality hoặc build cache có thể giảm thời gian **mà không cố tình loại modules**, nhưng phải kiểm tra thread-safe plugins và shared test resources. Đừng giả định parallel build luôn nhanh hơn hoặc ổn định hơn.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `-pl :store-cli` không tìm thấy pricing-service | Upstream SNAPSHOT chưa install | Chạy từ root với `-am` |
| `-pl store-cli` không tìm module | Path khác artifactId/cwd sai | Kiểm tra path hoặc `:artifactId` |
| Maven nói module không thuộc reactor | Starting POM không thu thập module | Chạy từ root hoặc `-f root/pom.xml` |
| `-am` không chạy consumer | -am chỉ kéo upstream | Dùng `-amd` khi cần downstream |
| `-amd` không chạy HTTP consumer | Không có Maven dependency edge | Thêm explicit integration/contract tests |
| Partial PASS nhưng analytics FAIL | analytics bị omit | Full build và báo phạm vi đúng |
| Core unit tests PASS, pricing regression FAIL | Case dùng ở consumer chưa được cover ở core | Chạy downstream tests |
| `-rf` dùng dependency cũ | Bỏ qua earlier upstream modules | `-pl ... -am` hoặc full |
| `-N verify` không có Surefire reports | Chỉ parent packaging=pom | Bỏ -N |
| `-f child/pom.xml` không build siblings | Maven 3 starting POM không phải aggregator | Dùng root reactor |
| Test reports có từ run cũ | Workspace/target không clean | Xem build ID/timestamp, clean theo policy |
| Coverage aggregate thấp/khác | Partial coverage subset | Không gọi là full coverage |
| Module SKIPPED trong Summary | Failure sớm hoặc dependency fail | Không tính module SKIPPED là PASS |
| CI pipeline PASS dù module FAIL | `-fn` hoặc shell che exit code | Giữ Maven exit code |
| `dependencyManagement` không đổi sorting | Chưa có instantiated dependency | Khai báo dependency thực |
| Module version mismatch | Internal GAV lệch reactor | Kiểm tra effective POM và version |
| Graph selector bỏ sót module runtime | Coupling ngoài Maven graph | Full/contract/e2e tests |
| Tests chạy qua IDE nhưng Maven report không có | IDE test runner khác Surefire | Chạy Maven goals trong IDE |
| Parallel reactor flaky | Tests/plugins dùng shared state | Giới hạn -T, cô lập resources |

Lệnh xác minh cấu hình:

```bash
mvn -version
mvn help:effective-pom
mvn -B -ntp -pl :store-cli -am validate
mvn -B -ntp clean verify
```

Khi chạy dependency goal:

```bash
mvn -pl :store-cli -am dependency:tree
```

Output phụ thuộc những modules/goals được chọn và external artifact resolution. Đây không phải full map của runtime HTTP/event/database relationships.

## 17. Bài tập tự luyện

1. Nêu ba bước của Maven reactor: collect, sort, build.
2. Aggregator có `<modules>` khác với parent inheritance ở đâu?
3. Vì sao math-core được build trước store-cli dù đứng sau trong root modules list?
4. Vì sao dependencyManagement không tự sinh module dependency edge?
5. Phân biệt `-pl store-cli`, `-pl :store-cli` và `-pl dev.course:store-cli`.
6. Chạy `-pl :store-cli -am verify`, liệt kê các Java modules và số tests chạy.
7. Analytics có được kiểm chứng trong câu 6 không?
8. Chạy `-pl :math-core -amd verify`, liệt kê dependents.
9. Vì sao -am không tự kiểm thử mọi downstream consumer?
10. Vì sao -amd không nhận diện cross-service HTTP dependency nếu POM không có edge?
11. `-rf :pricing-service` có tự rebuild math-core từ source mới không?
12. Vì sao `-N verify` rất nhanh nhưng không xác nhận child tests?
13. Tạo 5 POM, 8 Java files và chạy full reactor; xác minh **8 unit tests**.
14. Chạy Java App với đúng cross-platform classpath và xác nhận stdout `TOTAL=36`.
15. Cố ý làm analytics test fail, vì sao store-cli partial build vẫn có thể PASS?
16. Khi chạy full build với analytics mutation, module nào gây FAILURE?
17. Khôi phục analytics rồi tạo bug giả trong Calculator.multiply với left>10.
18. Vì sao math-core tests vẫn PASS nhưng PriceServiceTest FAIL?
19. Dùng `-amd` để phát hiện regression downstream.
20. Tại sao cần khôi phục mutation tests trước commit?
21. Khi Maven reactor `-fae`, modules nào còn có thể chạy sau failure?
22. Vì sao `-fn` không nên dùng cho required CI gate?
23. Nếu JaCoCo chỉ có report ở selected modules, có thể gọi là coverage toàn project không?
24. Nếu một E2E test ở module độc lập, `-am` có tự chạy nó không?
25. Khi thay parent POM/BOM/plugin version, CI nên dùng phạm vi nào?
26. Định nghĩa rõ PASS, NOT SELECTED, SKIPPED, NOT CONFIGURED.
27. Trình bày hai jobs fast và full trong workflow mẫu; khi nào cần full trước merge?
28. Nêu ba loại runtime coupling mà Maven dependency graph không tự biết.
29. Khi đo thời gian build, những điều kiện cache/JDK/tests cần thống nhất?
30. Vì sao một xanh từ selected reactor không đủ làm release approval?

## 18. Checklist chọn phạm vi đúng

- [ ] Đã xác định Maven version và root aggregator.
- [ ] Biết modules nào được reactor thu thập.
- [ ] Chọn path hoặc coordinates đúng cho -pl.
- [ ] Hiểu upstream vs downstream theo dependencies thực tế.
- [ ] Có -am nếu cần source-built internal dependencies.
- [ ] Có -amd/contract tests nếu core change ảnh hưởng consumers.
- [ ] Không phụ thuộc stale cached SNAPSHOT artifacts mà không biết.
- [ ] Không hiểu -rf là closure, không hiểu -N là full build.
- [ ] Không dùng -fn hoặc skipTests để làm CI green giả.
- [ ] Sau build xem Reactor Build Order và Summary.
- [ ] Ghi rõ test counts của selected và omitted modules.
- [ ] Không đánh dấu NOT SELECTED/SKIPPED là PASS.
- [ ] Failsafe/quality/coverage goals có bind và chạy thật nếu policy yêu cầu.
- [ ] Cross-service runtime dependencies có mapping/test riêng.
- [ ] Shared config, BOM, parent POM, wrapper/toolchain change trigger full build.
- [ ] Full reactor và release gates thực sự chạy trước publish/deploy.
- [ ] Hiệu năng đo bằng dữ liệu thật, không suy từ số modules đơn thuần.

## 19. Tổng kết

**Maven selective reactor builds giúp tăng tốc feedback, nhưng đồng thời thu hẹp bằng chứng chất lượng.**

- `-pl` chọn module.
- `-am` thêm các reactor dependencies **phía upstream**.
- `-amd` thêm các reactor dependents **phía downstream**.
- `-rf` resume theo build order; `-N` chỉ current POM; `-f` thay starting POM.
- Full root `mvn clean verify` kiểm tra phạm vi rộng hơn, nhưng các external integration/security checks vẫn cần được cấu hình rõ.

Lab Java 17 chứng minh full reactor chạy **8 unit tests**, còn `-pl :store-cli -am verify` chỉ chạy **6 tests** và bỏ qua analytics. Một lỗi cố ý tại math-core có thể lọt qua unit tests của core nhưng bị phát hiện bởi PriceServiceTest khi chạy downstream bằng `-amd`. Chương trình App đúng in:

```text
TOTAL=36
```

**Một kết quả BUILD SUCCESS chỉ có ý nghĩa cùng với phạm vi module, goals và tests thực sự đã chạy.** Dùng partial builds cho vòng phản hồi nhanh; giữ full/contract/release gates ở vị trí cần bảo đảm chất lượng toàn hệ thống.

## 20. Tài liệu chính thức

- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — CLI Reference](https://maven.apache.org/ref/current/maven-embedder/cli.html)
- [Apache Maven — Multiple Subprojects in Maven 4 (để đối chiếu khác biệt)](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [Apache Maven Surefire — Test Inclusion/Exclusion](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Surefire — Overview](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Failsafe — Overview](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven — Configuring Build Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
