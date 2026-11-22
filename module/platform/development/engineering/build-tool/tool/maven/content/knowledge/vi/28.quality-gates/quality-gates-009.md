# Chia sẻ chính sách qua parent và quản lý ngoại lệ tường minh trong Maven

## 1. Bài toán: cổng chất lượng phải thống nhất nhưng không máy móc

Một repository Maven lớn có nhiều modules. Mỗi nhóm phát triển đều muốn build nhanh, nhưng tổ chức cần một **cổng chất lượng (quality gate)** chung: mọi module phải dùng một mức Java/Maven được hỗ trợ, không được kéo những dependency đã cấm, phải chạy tests và đáp ứng những kiểm tra về style, coverage hoặc security phù hợp.

Nếu mỗi module sao chép nguyên cấu hình plugin, sau một thời gian sẽ xảy ra **policy drift**:

- Module A dùng Java 17, module B vẫn cho phép Java 11.
- Module C tắt Maven Enforcer để bỏ qua một dependency cũ, vô tình bỏ luôn kiểm tra Maven/JDK.
- Module D chạy Checkstyle ở `verify`, module E chỉ sinh report nhưng không fail build.
- Plugin versions khác nhau khiến local và CI kiểm tra không giống nhau.
- Một module chứa code generated cần ngoại lệ Checkstyle, nhưng nhóm lại tắt Checkstyle cho cả Reactor.
- Một luật được thay ở parent nhưng các POM con không thực sự kế thừa hoặc kích hoạt plugin đó.
- Ngoại lệ xuất hiện mà không có lý do, người phụ trách, ticket hay hạn xử lý.

Giải pháp là **đặt chính sách mặc định ở parent POM**, để phần lớn modules kế thừa; khi có nhu cầu ngoại lệ, chỉ mở một phạm vi **nhỏ nhất có thể**, ghi rõ lý do và kiểm tra rằng các cổng còn lại vẫn hoạt động.

Bài Knowledge thuộc nhóm **Cổng chất lượng**, với các mục tiêu:

1. Phân biệt **parent POM**, **aggregator POM**, `pluginManagement`, `build/plugins` và cấu hình inherited.
2. Biết đặt phiên bản plugin, executions, rules và lifecycle phase ở đúng nơi để các modules thực sự chịu chính sách.
3. Hiểu quy tắc "mặc định nghiêm ngặt, ngoại lệ có kiểm soát", không lấy `skip=true` làm đường tắt.
4. Dùng Maven Enforcer Plugin để kiểm tra Maven/JDK versions và dependency bị cấm.
5. Dùng `bannedDependencies` với `includes` để **ngoại lệ chính xác** một dependency trong một module.
6. Thực hành Maven 3 + Java 17 + JUnit Jupiter với parent và hai modules, tạo một trường hợp PASS và một trường hợp FAIL có chủ đích.
7. Hiểu cách mở rộng cùng phương pháp sang Surefire, Failsafe, Checkstyle, JaCoCo và các quality gates khác.
8. Biết kiểm tra effective POM, plugin execution logs, Reactor Build Order và reports trong CI.
9. Thiết kế hồ sơ ngoại lệ gồm **phạm vi, lý do, người duyệt, ticket, thời hạn, bằng chứng và điều kiện gỡ bỏ**.

**Phạm vi ví dụ:** Maven 3.8+ chạy trên JDK 17+, Java source target 17. Các plugin versions trong demo được cố định để tái hiện, không khẳng định là mới nhất.

## 2. Ba lớp thiết kế: chính sách chung, thực thi, ngoại lệ

Một hệ thống quản trị cổng chất lượng tốt có thể mô tả như sau:

~~~text
                     parent POM
              (chính sách áp dụng chung)
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
       core module           legacy-adapter module
          │                       │
      kế thừa gate           kế thừa gate
          │                       │
      không ngoại lệ         cho phép đúng dependency cũ 1.2
          │                       │
          └───────────┬───────────┘
                      ▼
           CI chạy Maven clean verify
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
  Rule violation → FAIL      Rules + tests PASS
~~~

Có ba câu hỏi độc lập:

1. **Chính sách:** "Module phải chạy Maven >= 3.8 và JDK >= 17, không dùng dependency `commons-logging:commons-logging` theo mặc định."
2. **Thực thi:** Plugin nào kiểm tra điều này? Goal chạy ở phase nào? Có tự chạy khi gọi `mvn verify` không?
3. **Ngoại lệ:** Nếu legacy module tạm cần phiên bản `commons-logging:commons-logging:1.2`, làm sao cho phép **riêng module ấy, riêng artifact/version ấy** mà không mất kiểm tra Maven/JDK?

Một ngoại lệ đúng không phải chỉ khiến pipeline xanh. Nó phải chứng minh **những điều vẫn bị cấm tiếp tục bị chặn**.

### Nguyên tắc phạm vi nhỏ nhất

| Mức mở ngoại lệ | Ví dụ | Rủi ro |
| --- | --- | --- |
| Toàn tổ chức | Xóa Enforcer khỏi parent. | Mọi module mất chính sách. |
| Toàn build | `mvn -Denforcer.skip=true verify`. | Bỏ qua mọi Enforcer checks trong invocation. |
| Toàn module | `<skip>true</skip>` ở Enforcer của một module. | Module đó mất cả luật không liên quan. |
| Một execution | Override chỉ execution `dependency-policy`. | Hạn chế hơn, nhưng toàn bộ luật trong execution có thể bị bỏ. |
| **Một rule/một artifact** | `bannedDependencies/includes` cho `commons-logging:commons-logging:1.2` trong legacy module. | **Ưu tiên** khi rule hỗ trợ ngoại lệ đủ hẹp. |
| Một file/một lỗi style | Checkstyle `SuppressionFilter` cho rule và file xác định. | Ít ảnh hưởng, cần bảo trì và theo dõi hạn. |

Không phải plugin nào cũng hỗ trợ cùng một loại ngoại lệ. Khi rule không có cơ chế scope hẹp, cân nhắc tách execution hoặc cấu hình trong một module, nhưng phải giải thích phần nào bị bỏ qua.

## 3. Parent POM khác aggregator POM

Một **aggregator POM** có `<modules>` để Maven Reactor thu thập các modules khi gọi build tại root.

Một **parent POM** được module khai báo qua `<parent>` để kế thừa một phần cấu hình Maven model: properties, dependencyManagement, pluginManagement, build/plugins và các execution/configuration được phép inherit.

Hai vai trò có thể do cùng một POM đảm nhiệm, nhưng không bắt buộc.

~~~xml
<!-- Root aggregator đồng thời là parent -->
<groupId>demo.quality</groupId>
<artifactId>quality-parent</artifactId>
<version>1.0.0-SNAPSHOT</version>
<packaging>pom</packaging>
<modules>
    <module>core</module>
    <module>legacy-adapter</module>
</modules>
~~~

Module con:

~~~xml
<parent>
    <groupId>demo.quality</groupId>
    <artifactId>quality-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

**Có tên trong `<modules>` không tự khiến module kế thừa parent**: nó phải khai báo `<parent>`. Ngược lại, module có thể kế thừa một parent POM từ repository mà không nằm trong Reactor build hiện tại.

Để quality gates áp dụng nhất quán, phải kiểm tra **quan hệ inheritance** thực sự của những modules cần chịu chính sách, không chỉ nhìn cây thư mục.

## 4. `pluginManagement` và `build/plugins`: cấu hình khác kích hoạt

Đây là lỗi thường gặp nhất khi muốn "chia sẻ cổng chất lượng".

### `pluginManagement`: quản lý mặc định

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Cấu hình này quản lý version cho plugin khi nó được dùng/được lifecycle binding kích hoạt; `pluginManagement` **không phải cam kết rằng một execution tùy ý sẽ tự chạy ở mọi module**.

Ví dụ Surefire đã có default lifecycle binding cho `jar` projects ở phase `test`, nên quản lý version của Surefire vẫn có ý nghĩa. Nhưng một custom quality plugin như Maven Enforcer, nếu **chỉ** được đặt trong pluginManagement mà không có plugin declaration thực thi ở nơi cần, có thể không chạy khi chỉ gọi `mvn verify`.

### `build/plugins`: khai báo plugin áp dụng cho build

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.6.2</version>
            <executions>
                <execution>
                    <id>environment-baseline</id>
                    <phase>validate</phase>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đây là **mảnh minh họa**; khi đặt trong parent, plugin declaration/execution có thể được các child kế thừa theo cơ chế Maven, vì plugin mặc định `<inherited>true</inherited>`. Nếu muốn **tắt inheritance** cho một execution, có `<inherited>false</inherited>` — hãy cân nhắc kỹ vì đó có thể làm child mất cổng chất lượng.

**Lưu ý:** goal `enforce` cần `<rules>` cụ thể; một execution chỉ có goal mà không có rules không phải ví dụ policy hoàn chỉnh. POM runnable ở mục 7 sẽ có rules đầy đủ.

### Tóm tắt khác biệt

| Khái niệm | Chức năng | Sai lầm thường gặp |
| --- | --- | --- |
| `dependencyManagement` | Quản lý thông số dependency khi dependency thực được khai báo. | Nghĩ nó tự thêm library vào classpath. |
| `dependencies` | Khai báo dependency mà project thật sự dùng. | Khai báo version tùy tiện ở nhiều modules. |
| `pluginManagement` | Quản lý versions/configurations cho plugins. | Nghĩ nó luôn tự kích hoạt quality goal không có lifecycle binding. |
| `build/plugins` | Đưa plugin vào build, cho phép execution được thực thi/kế thừa theo POM. | Đặt plugin ở parent nhưng tắt inheritance ngoài ý muốn. |
| `executions` | Gắn plugin goal với phase và configuration. | Chỉ cấu hình plugin mà quên goal/phase. |
| `profiles` | Thay đổi model khi profile active. | Chỉ bật gate ở profile mà CI không kích hoạt. |

## 5. Chọn cổng chất lượng theo vòng đời build

Các quality gates thường gặp:

| Cổng | Ví dụ công cụ | Phase thường dùng | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| Maven/JDK runtime policy | Maven Enforcer | `validate` | Build dừng nếu môi trường không đủ điều kiện. |
| Dependency policy | Enforcer `bannedDependencies`, `dependencyConvergence` | `validate` hoặc phase phù hợp | Dependency bị cấm hay version conflict bị phát hiện. |
| Source conventions | Maven Checkstyle Plugin | `validate` hoặc `verify` tùy config | Có rule thực thi và fail trên violation khi cần. |
| Unit tests | Maven Surefire | `test` | Test discovery, exit status, report. |
| Integration tests | Maven Failsafe | `integration-test` + `verify` | Có chạy IT, cleanup và `failsafe:verify` xử lý failure. |
| Coverage threshold | JaCoCo `check` | Thường `verify` | Có execution data và rule/threshold thực thi. |
| Static analysis | SpotBugs/PMD | Theo plugin execution | Tool chạy đúng module và fail theo policy, không chỉ sinh report. |

Một số điểm cần tránh nhầm:

- `mvn validate` chỉ chạy các goals được gắn tới phase `validate`; không chứng minh tests/coverage đã PASS.
- `mvn test` chưa chạy quality check nếu plugin chỉ bind ở `verify`.
- `mvn verify` chạy các phases trước nó, nhưng **không tự chạy một goal không hề được bind**.
- Sinh HTML/XML report khác với cấu hình **fail build khi không đạt threshold**.
- Dự án `packaging=pom` không phải Java module; quy tắc JDK/Maven có thể áp dụng được, nhưng coverage theo bundle cần xử lý khác với JAR module.

Trong demo, ta dùng Enforcer để tạo **hai executions riêng**: luật môi trường và luật dependency. Chia execution giúp xác định ranh giới ngoại lệ rõ ràng.

## 6. Maven Enforcer: chính sách nền và luật dependency

Maven Enforcer Plugin có built-in rules:

- `requireJavaVersion`: kiểm tra phiên bản **Java đang chạy Maven**, không tự chứng minh bytecode target.
- `requireMavenVersion`: kiểm tra Maven runtime version.
- `bannedDependencies`: chặn dependency khớp danh sách `excludes`, có thể cho phép ngoại lệ qua `includes`.
- `dependencyConvergence`, `requireUpperBoundDeps`: kiểm tra khía cạnh version graph với ý nghĩa/giới hạn riêng.
- Các rules khác tùy plugin version và mục tiêu governance.

Chốt plugin version, ví dụ `3.6.2`, để cùng POM không bất ngờ đổi hành vi giữa CI và local.

### Luật môi trường

~~~xml
<rules>
    <requireMavenVersion>
        <version>[3.8,)</version>
    </requireMavenVersion>
    <requireJavaVersion>
        <version>[17,)</version>
    </requireJavaVersion>
</rules>
~~~

Đây là **version range**: Maven ít nhất 3.8 và Java ít nhất 17 theo rule semantics. Nó **không** yêu cầu đúng Maven 3.8.0 hoặc chỉ Java 17; các version cao hơn cũng được chấp nhận theo range. Nếu tổ chức cần chỉ cho phép một danh sách cụ thể, phải cấu hình range/policy chặt hơn.

**Chú ý:** `<maven.compiler.release>17</maven.compiler.release>` là compiler target/API constraint khi Compiler Plugin build source; nó không có nghĩa Maven runtime nhất thiết chạy trên JDK 17. Enforcer `requireJavaVersion` và Compiler `release` trả lời hai câu hỏi khác nhau.

### Luật chặn dependency

~~~xml
<rules>
    <bannedDependencies>
        <excludes>
            <exclude>commons-logging:commons-logging</exclude>
        </excludes>
        <searchTransitive>true</searchTransitive>
    </bannedDependencies>
</rules>
~~~

Rule này chặn `commons-logging:commons-logging` nếu nó xuất hiện trong dependency graph theo phạm vi mà Enforcer kiểm tra. `searchTransitive=true` bao gồm cả transitive dependencies (đây là default của rule; demo viết tường minh).

**Đây là policy minh họa của demo**, không phải tuyên bố `commons-logging` hoặc phiên bản 1.2 luôn có lỗ hổng hay bị cấm trên thực tế. Doanh nghiệp chỉ nên cấm một thư viện dựa trên đánh giá license, security, duy trì hoặc tiêu chuẩn kiến trúc cụ thể.

### `includes` là ngoại lệ của `excludes`

Với `bannedDependencies`:

~~~xml
<bannedDependencies>
    <excludes>
        <exclude>commons-logging:commons-logging</exclude>
    </excludes>
    <includes>
        <include>commons-logging:commons-logging:1.2</include>
    </includes>
    <searchTransitive>true</searchTransitive>
</bannedDependencies>
~~~

`includes` **không phải danh sách dependencies cần tải**. Nó là **danh sách ngoại lệ**: chỉ những artifacts khớp exclude mới có ý nghĩa với include. Ở đây, commons-logging **đúng phiên bản 1.2** được cho phép; những version khác vẫn bị luật exclude chặn.

Nếu mục tiêu chỉ ban những version cũ và cho phép version mới, có thể thiết kế `excludes` theo version range thay vì whitelist một version, tùy policy. Không dùng include quá rộng như `commons-logging:*` nếu chỉ có lý do ngoại lệ cho một bản cụ thể.

## 7. Project Java 17 đa module: parent chia sẻ policy

Ví dụ có ba POM và mã Java đơn giản:

~~~text
quality-parent-demo/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/demo/core/Greeting.java
│       └── test/java/demo/core/GreetingTest.java
└── legacy-adapter/
    ├── pom.xml
    └── src/
        ├── main/java/demo/legacy/LegacyBridge.java
        └── test/java/demo/legacy/LegacyBridgeTest.java
~~~

`core` chỉ dùng JDK cho mã sản phẩm. `legacy-adapter` sử dụng `core` và dependency `commons-logging:commons-logging:1.2` vì mô phỏng adapter cần thư viện cũ.

Chính sách Enforcer nằm trong parent và được **cả hai modules kế thừa**. Riêng `legacy-adapter` khai báo lại **đúng execution ID** của luật banned dependency, thêm một `include` ngoại lệ cho version 1.2. Luật môi trường vẫn hoạt động ở cả hai modules.

### 7.1. Root `pom.xml` hoàn chỉnh

Tạo `quality-parent-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.quality</groupId>
    <artifactId>quality-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>legacy-adapter</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
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
                    <version>3.5.4</version>
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
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>environment-baseline</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <fail>true</fail>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.8,)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                    <execution>
                        <id>dependency-policy</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <fail>true</fail>
                            <rules>
                                <bannedDependencies>
                                    <excludes>
                                        <exclude>commons-logging:commons-logging</exclude>
                                    </excludes>
                                    <searchTransitive>true</searchTransitive>
                                </bannedDependencies>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích chính xác:**

- Root là aggregator vì có `<modules>` và là parent nhờ modules khai báo `<parent>` ở POM riêng.
- `pluginManagement` ghim Compiler, Surefire, JAR Plugin versions cho các modules.
- Enforcer nằm trong **`build/plugins`**, không chỉ trong management.
- Hai executions có IDs khác nhau: `environment-baseline` và `dependency-policy`.
- Cả hai bind `enforce` tới `validate`, nên được kích hoạt khi `mvn validate`, `mvn test` hoặc `mvn verify` đi qua phase này.
- Chúng được thừa kế bởi child POM theo mặc định.
- Luật môi trường không trộn với luật dependency thành một execution duy nhất; điều đó cho phép module con override phạm vi cụ thể.
- `fail=true` làm build thất bại nếu rule kiểm tra không đạt; không chuyển thành cảnh báo mặc định.
- `bannedDependencies` xét dependency graph của từng project; không cần Java source có import thư viện mới áp dụng được.

### 7.2. `core/pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo.quality</groupId>
        <artifactId>quality-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`core` không khai báo plugin Enforcer riêng, nhưng kế thừa các executions do parent đặt trong `build/plugins`. Test dependency `junit-jupiter` thuộc scope `test`; nó không tự tạo ngoại lệ cho `bannedDependencies`.

### 7.3. `core/src/main/java/demo/core/Greeting.java`

~~~java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is blank");
        }
        return "Hello " + name + " from core";
    }

    public static void main(String[] args) {
        System.out.println(greet("Maven"));
    }
}
~~~

Đây là Java 17 hợp lệ. `String.isBlank()` có từ Java 11, nên dùng được với target 17.

### 7.4. `core/src/test/java/demo/core/GreetingTest.java`

~~~java
package demo.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {
    @Test
    void buildsGreeting() {
        assertEquals("Hello Maven from core", Greeting.greet("Maven"));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Greeting.greet("   "));
    }
}
~~~

Hai JUnit Jupiter tests hoạt động độc lập, không cần external services. File đúng quy tắc tên `*Test.java` cho Maven Surefire.

### 7.5. `legacy-adapter/pom.xml` hoàn chỉnh, có ngoại lệ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>demo.quality</groupId>
        <artifactId>quality-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>legacy-adapter</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>demo.quality</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
            <version>1.2</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <executions>
                    <execution>
                        <id>dependency-policy</id>
                        <configuration>
                            <rules>
                                <bannedDependencies>
                                    <excludes>
                                        <exclude>commons-logging:commons-logging</exclude>
                                    </excludes>
                                    <includes>
                                        <!-- Temporary: allow only version 1.2 in legacy-adapter.
                                             Approval/ref/expiry must be tracked by team. -->
                                        <include>commons-logging:commons-logging:1.2</include>
                                    </includes>
                                    <searchTransitive>true</searchTransitive>
                                </bannedDependencies>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Điểm then chốt:

1. POM child khai báo lại **cùng plugin coordinates** và **cùng execution ID `dependency-policy`** của parent.
2. Maven merge/inheritance cấu hình execution cùng ID; phase `validate` và goal `enforce` ở parent vẫn được kế thừa khi không đổi.
3. Child ghi lại `excludes` và thêm `includes` chính xác cho `commons-logging:commons-logging:1.2`. Việc khai báo lại exclude giúp reviewer đọc được **cả phạm vi bị cấm lẫn ngoại lệ** mà không phải đoán kết quả merge.
4. Child **không** override execution `environment-baseline`, nên yêu cầu Maven/JDK vẫn được giữ nguyên.
5. Child không có `<skip>true</skip>` và không dùng `enforcer.skip`.
6. Những dependency khác không khớp include vẫn phải tuân thủ chính sách. Nếu một transitive dependency khác cũng là `commons-logging` nhưng version ngoài 1.2, nó vẫn thuộc phạm vi bị cấm.
7. XML comment mang ý nghĩa tài liệu, **không tự tạo deadline hoặc approval control**. Trong dự án thật, hãy thêm issue/ticket ID, owner và ngày hết hạn có thật rồi quản lý bằng CI/bộ kiểm tra policy thích hợp.

**Lưu ý về merge:** XML configuration của Maven có cơ chế merge giữa parent và child; cách merge cụ thể có thể chịu ảnh hưởng `combine.self`/`combine.children` ở một POM thật. Vì vậy sau khi viết ngoại lệ, **bắt buộc xem `help:effective-pom`** của module, không chỉ tin vào source POM.

### 7.6. `legacy-adapter/src/main/java/demo/legacy/LegacyBridge.java`

~~~java
package demo.legacy;

import demo.core.Greeting;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

public final class LegacyBridge {
    private LegacyBridge() {
    }

    public static String createMessage(String name) {
        Log logger = LogFactory.getLog(LegacyBridge.class);
        if (logger.isDebugEnabled()) {
            logger.debug("Creating greeting");
        }
        return Greeting.greet(name) + " via legacy-adapter";
    }
}
~~~

Class này sử dụng cả dependency nội bộ `core` và `commons-logging`. Việc gọi logging chỉ minh họa lý do module cũ vẫn cần thư viện; đó **không phải lời khuyên** tiếp tục dùng dependency bị policy thật cấm vĩnh viễn.

### 7.7. `legacy-adapter/src/test/java/demo/legacy/LegacyBridgeTest.java`

~~~java
package demo.legacy;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LegacyBridgeTest {
    @Test
    void usesCoreAndLegacyLoggingDependency() {
        assertEquals(
                "Hello Maven from core via legacy-adapter",
                LegacyBridge.createMessage("Maven"));
    }
}
~~~

Với logging config thông thường, phương thức tạo message không phụ thuộc vào logger output. JUnit assertion kiểm tra **giá trị trả về**, không dựa vào stdout của Maven logs hoặc output không cố định của logging implementation.

## 8. Chạy project và xác minh cả hai tầng quality gates

### 8.1. Kiểm tra môi trường

Từ root `quality-parent-demo`:

~~~bash
mvn --version
java -version
~~~

Đảm bảo Maven đáp ứng range `[3.8,)` và JVM chạy Maven thuộc Java `[17,)`. Nếu không thỏa, execution `environment-baseline` sẽ chặn ở phase `validate`. Compiler release 17 cũng đòi JDK/toolchain phù hợp để build mã Java 17.

### 8.2. Chạy chỉ phase `validate`

~~~bash
mvn -B -ntp validate
~~~

Kỳ vọng Maven chạy các Enforcer executions được inherited trên các projects trong Reactor. Root/`core` không có dependency bị cấm. `legacy-adapter` có `commons-logging:commons-logging:1.2` nhưng được include exception.

Với JDK/Maven phù hợp và dependencies có thể resolve, quality checks kết thúc `BUILD SUCCESS`. **Đây không phải kết luận unit tests đã chạy**, vì phase `validate` đến trước `test`.

Dòng log thật có thể có:

~~~text
maven-enforcer-plugin:3.6.2:enforce (environment-baseline)
maven-enforcer-plugin:3.6.2:enforce (dependency-policy)
...
BUILD SUCCESS
~~~

Đây là **trích đoạn minh họa về goal/execution**, không phải stdout đầy đủ. Cần quan sát log của cả các modules và không đếm số dòng plugin như số tests.

### 8.3. Build, chạy unit tests và đóng gói

~~~bash
mvn -B -ntp clean verify
~~~

Từ root, Maven Reactor sắp `core` trước `legacy-adapter` vì module sau phụ thuộc module trước. Theo project mẫu:

- Parent POM được build, chạy Enforcer rules; không tạo Java JAR.
- `core` chạy `environment-baseline` và `dependency-policy`, biên dịch, có **2 JUnit tests PASS**.
- `legacy-adapter` chạy **cả hai executions Enforcer**, được phép dependency `commons-logging:1.2` trong phạm vi ngoại lệ, biên dịch, có **1 JUnit test PASS**.
- Các JAR main của hai modules được đóng gói.
- Trong điều kiện môi trường đúng, Maven kết thúc `BUILD SUCCESS`.

Một bảng dự kiến:

| Module | Enforcer environment | Enforcer dependency | Unit tests | Build |
| --- | --- | --- | ---: | --- |
| `quality-parent` | PASS | PASS | Không có Java tests | PASS |
| `core` | PASS | PASS | 2 PASS | PASS |
| `legacy-adapter` | PASS | PASS, có exception chính xác | 1 PASS | PASS |

Đây là **kỳ vọng của demo**, không phải log build thực sự được chạy trong bất kỳ repository production nào. Báo cáo Surefire trong từng module nằm ở `core/target/surefire-reports` và `legacy-adapter/target/surefire-reports`. Không nhầm root `target` là nơi duy nhất chứa test reports.

### 8.4. Chạy chương trình Java có stdout kiểm chứng được

`Greeting` trong module `core` có `main` dùng JDK và mã chính nó, nên có thể chạy:

**Linux/macOS:**

~~~bash
java -cp core/target/classes demo.core.Greeting
~~~

**Windows PowerShell:**

~~~powershell
java -cp "core\target\classes" demo.core.Greeting
~~~

**Stdout chính xác của riêng chương trình:**

~~~text
Hello Maven from core
~~~

Không dùng `java -jar core/target/core-1.0.0-SNAPSHOT.jar` trong ví dụ vì JAR Plugin chưa được cấu hình `Main-Class`. Cũng không cần tự tìm JAR commons-logging để chạy `Greeting`: class này không dùng dependency đó.

### 8.5. Build chọn lọc một module

~~~bash
mvn -pl :legacy-adapter -am -B -ntp clean verify
~~~

`-pl` chọn `legacy-adapter`; `-am` bổ sung `core` là module upstream nằm trong Reactor, và parent liên quan cũng có thể tham gia theo Reactor relationships. Đây là cách kiểm chứng legacy module **cùng source core hiện tại** thay vì phụ thuộc một JAR core cũ đã cài trong local repository.

**Không khẳng định `-am` là ngoại lệ chất lượng**: nó chỉ thay tập modules được build; mỗi module được chọn vẫn phải đi qua những quality gate được inherited/bind.

## 9. Chứng minh ngoại lệ thật sự hẹp bằng negative test

Một quality gate chỉ đáng tin nếu ta biết **đổi sai sẽ làm build FAIL**.

### 9.1. Thí nghiệm A — bỏ `includes` ở legacy module

Trên một nhánh/checkout thử nghiệm, tạm xóa:

~~~xml
<includes>
    <include>commons-logging:commons-logging:1.2</include>
</includes>
~~~

trong `legacy-adapter/pom.xml`. Giữ nguyên dependency `commons-logging:1.2`, các POM khác không đổi.

Chạy:

~~~bash
mvn -B -ntp validate
~~~

Dự kiến:

- Parent/`core` vẫn đạt rule môi trường và dependency, nếu runtime đúng.
- `legacy-adapter` vi phạm `bannedDependencies` vì dependency bị exclude mà không còn include exception.
- Maven báo **BUILD FAILURE** tại `dependency-policy`; không cần chờ compile/test.

Kết quả này chứng minh parent policy đang được áp dụng lên legacy module. Không nên dùng chính cờ `-Denforcer.skip=true` để "sửa" lần fail này, vì làm vậy bỏ luôn bằng chứng quality gate hoạt động.

### 9.2. Thí nghiệm B — khôi phục ngoại lệ

Khôi phục chính xác `includes` cho version 1.2 rồi chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Dự kiến build PASS khi môi trường phù hợp. Đây là một biến thể cho phép có chủ đích, không phải mặc định nới luật cho toàn repository.

### 9.3. Thí nghiệm C — kiểm tra gate nền vẫn còn

Từ module con, đọc effective POM để xác nhận hai Enforcer executions vẫn tồn tại. Nếu muốn thử negative case của version gate, **trong một bản sao/branch tạm** có thể thay required Java version thành một range không được máy hỗ trợ, chẳng hạn `[99,)`, rồi chạy `mvn validate` để quan sát failure. Sau đó hoàn tác ngay thay đổi kiểm thử.

Không khuyến nghị chỉnh parent quality policy trên branch chính chỉ để tạo lỗi. Không để một cấu hình test cố ý thất bại lọt vào pull request thật.

### 9.4. Không viết test dựa vào log line cố định

Enforcer có thể thay đổi wording giữa các phiên bản và Maven runtime có thể khác. Khi viết CI verification, dùng **exit code, rule/execution identity và trạng thái artifact**; log là bằng chứng bổ sung.

## 10. Cách kiểm tra effective POM để xác nhận inheritance

Sau khi parent và child POM được soạn, **đừng chỉ đọc POM nguồn** để kết luận đã kế thừa. Dùng Maven Help Plugin:

~~~bash
mvn -pl :core help:effective-pom -Doutput=core-effective.xml
mvn -pl :legacy-adapter help:effective-pom -Doutput=legacy-effective.xml
~~~

Những lệnh này có thể tải Maven Help Plugin khi chưa cache. Đường dẫn file output thực tế có thể liên quan module base directory; đọc log và tìm file được ghi. Đây là **báo cáo phát sinh**, không phải file POM nguồn để sửa trực tiếp.

Trong **effective POM của `core`**, cần xác minh:

- Plugin `maven-enforcer-plugin:3.6.2` nằm trong build plugins.
- Execution `environment-baseline` bind `validate`, kiểm tra Java/Maven versions.
- Execution `dependency-policy` bind `validate`, chặn `commons-logging:commons-logging`.
- Không có include exception vô tình lan từ module legacy.
- Surefire/Compiler plugin versions được quản lý theo parent.

Trong **effective POM của `legacy-adapter`**, cần xác minh:

- Execution `environment-baseline` vẫn tồn tại, không bị tắt.
- Execution `dependency-policy` vẫn bind `validate` và có `bannedDependencies`.
- `excludes` vẫn chứa `commons-logging:commons-logging`.
- `includes` chứa **đúng** `commons-logging:commons-logging:1.2`.
- `fail=true` không bị đổi thành `false`.
- Không có `skip=true` hoặc `enforcer.skip` dẫn đến việc bỏ toàn rule.
- Dependency `commons-logging` chỉ trong module legacy, không lan sang core qua parent `dependencies`.

### Sự khác nhau giữa hiệu lực và thực thi

- **Effective POM** chứng minh Maven model có cấu hình mong đợi.
- **Maven execution log** chứng minh goal thực sự được chạy ở lifecycle phase.
- **Negative test** chứng minh rule có thể làm build FAIL.
- **Surefire reports** chứng minh test methods thực sự chạy và kết quả.

Một build `BUILD SUCCESS` mà cổng chất lượng không hề chạy **không phải bằng chứng** chính sách đang được thực thi.

## 11. Ngoại lệ ở plugin level, execution level và rule level

### 11.1. Rule-level exception (ưu tiên)

Ví dụ `bannedDependencies/includes` trong module cụ thể. Nó cho phép một artifact/version nhưng những dependency khác vẫn bị chặn. Đây là chiến lược trong demo.

### 11.2. Execution-level exception (chỉ khi cần)

Đôi khi plugin không có mechanism `includes` hoặc suppression đủ hẹp. Nếu parent tách các executions `environment-baseline` và `dependency-policy`, module con có thể điều chỉnh đúng execution `dependency-policy`. Chẳng hạn:

~~~xml
<execution>
    <id>dependency-policy</id>
    <configuration>
        <skip>true</skip>
    </configuration>
</execution>
~~~

Đây là **anti-pattern để phân tích**, không thêm vào demo runnable: nó bỏ **toàn execution dependency policy** trong module. Environment execution có thể vẫn chạy do ID khác, nhưng quality risk cao hơn include exception.

Nếu buộc phải dùng, cần issue, phê duyệt, giới hạn modules, hạn gỡ bỏ và CI chứng minh các executions khác vẫn chạy. Nếu có thể mở phạm vi theo một rule duy nhất, không chọn skip execution.

### 11.3. Plugin-level/global skip (nguy hiểm nhất)

~~~bash
mvn -Denforcer.skip=true verify
~~~

Theo Enforcer usage, đây là user property để skip kiểm tra. Lệnh này có thể bypass tất cả Enforcer executions trong phạm vi build, bao gồm Java/Maven requirements và dependency policy. **Không dùng nó trong pipeline chính thức chỉ vì một exception legacy**.

Tương tự:

~~~xml
<configuration>
    <skip>true</skip>
</configuration>
~~~

đặt tại mức toàn plugin của một module có thể bỏ nhiều rules hơn dự định. Đặt trong parent còn nguy hiểm hơn vì lan sang mọi module con.

### 11.4. `fail=false` không phải PASS đúng nghĩa

Enforcer hỗ trợ `fail=false`: lỗi rule có thể được ghi dưới dạng warning thay vì fail build. Điều đó không có nghĩa policy đã đạt; cần tách rõ **violation tồn tại** và **build gate quyết định fail hay không**.

Một rule có thể hỗ trợ `level=WARN`, nhưng cảnh báo cũng không thay cho ngoại lệ có thời hạn. Nếu organization muốn chuyển dần sang enforce, giai đoạn warning cần được ghi nhận/giám sát trước khi bật error.

## 12. Mẫu quản trị ngoại lệ: không chỉ là XML comment

Một exception nên được nhìn như **khoản nợ kỹ thuật được kiểm soát**, không phải một dòng cấu hình lặng lẽ.

Một mẫu record (đây là **ví dụ quy trình**, không phải metadata mà Maven tự hiểu):

| Trường | Nội dung |
| --- | --- |
| Exception ID | `QG-017` |
| Module | `legacy-adapter` |
| Gate/rule | Enforcer `dependency-policy` / `bannedDependencies` |
| Chính xác thứ được cho phép | `commons-logging:commons-logging:1.2` |
| Lý do | Module tích hợp hệ thống cũ chưa thể thay adapter ngay. |
| Rủi ro | Phụ thuộc thư viện nằm ngoài chính sách chung. |
| Người phụ trách | Owner của module legacy. |
| Người phê duyệt | Người chịu trách nhiệm quality/security policy. |
| Ticket | Một issue có thể truy vết trong hệ thống của nhóm. |
| Hạn xem xét | Ngày cụ thể do team quyết định, không được bỏ trống dài hạn. |
| Kế hoạch gỡ | Thay adapter/logging API, xóa `includes`, chạy lại tests. |
| Bằng chứng | CI run, dependency tree, effective POM, negative test. |

Các giá trị `QG-017`, owner, ticket là **ví dụ**, không phải sự kiện có thật. Khi dùng trong tổ chức, thay bằng thông tin đã được phê duyệt, tránh tự dựng approval.

### Vì sao cần thời hạn?

Một exception được thêm vì "đang migrate" có thể còn trong POM nhiều năm. Nếu không có expiry/review cadence và trách nhiệm, cổng chất lượng dần trở thành danh sách ngoại lệ vô hạn.

POM XML comment **không tự hết hạn**. Có thể dùng:

- PR/issue với due date và người phụ trách.
- CI script kiểm tra exception registry (ví dụ YAML/JSON được quản lý riêng).
- Review định kỳ policies, số ngoại lệ và mức nghiêm trọng.
- Automation có kiểm soát để nhắc owner kiểm tra trước khi hết hạn.

Khi policy được đổi, cần review lại tất cả exceptions: một exception hợp lệ theo luật cũ có thể vượt quá phạm vi khi luật mới thay đổi.

## 13. Quản lý ngoại lệ Checkstyle cho một file và một rule

Một tình huống khác: parent áp dụng Checkstyle để kiểm tra style, nhưng một source file generated hoặc legacy chưa thể đáp ứng **một** rule cụ thể.

Không nên:

~~~xml
<skip>true</skip>
~~~

để tắt Checkstyle toàn module nếu chỉ có một file vi phạm.

Checkstyle hỗ trợ **SuppressionFilter**. Cấu hình minh họa tại `checkstyle.xml`:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <module name="SuppressionFilter">
        <property name="file" value="${checkstyle.suppressions.file}"/>
    </module>
    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
    </module>
</module>
~~~

File suppression riêng, ví dụ `checkstyle-suppressions.xml`:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE suppressions PUBLIC
    "-//Checkstyle//DTD SuppressionFilter Configuration 1.0//EN"
    "https://checkstyle.org/dtds/suppressions_1_0.dtd">
<suppressions>
    <suppress checks="AvoidStarImport"
              files="LegacyAdapter[.]java"/>
</suppressions>
~~~

Đây là **các file minh họa cho một cấu hình Checkstyle khác**, không phải file cần có trong dự án Enforcer runnable ở mục 7. Pattern ở `files` là regular expression; cần xác nhận cách plugin đưa đường dẫn và tên checks vào báo cáo theo Checkstyle version thực tế.

Trong Maven Checkstyle Plugin, một mảnh configuration có thể dùng:

~~~xml
<configuration>
    <configLocation>checkstyle.xml</configLocation>
    <suppressionsLocation>checkstyle-suppressions.xml</suppressionsLocation>
</configuration>
~~~

**Điểm khác biệt:** Enforcer `bannedDependencies/includes` loại trừ một artifact khỏi danh sách bị cấm; Checkstyle `SuppressionFilter` loại trừ một **loại vi phạm** tại file/đường dẫn phù hợp. Hai cơ chế đều tuân thủ tư tưởng ngoại lệ nhỏ, nhưng cú pháp và ý nghĩa thuộc **hai plugin khác nhau**.

Đừng cấu hình `suppressionsLocation` mà quên khai báo `SuppressionFilter` trong rule set, hoặc cho rằng file suppressions được Maven tự áp dụng cho mọi plugin. Khi triển khai thật, nên có một negative test chứng minh rule style vẫn chặn những file không được miễn trừ.

## 14. JaCoCo coverage gate: ngoại lệ phải dựa trên dữ liệu đúng

Với coverage, tổ chức có thể đặt threshold ở parent nhưng phải cân nhắc bản chất module:

- Java library có unit tests có thể kiểm theo `LINE COVEREDRATIO`.
- DTO generated code hoặc mapping code đặc thù có thể cần policy riêng cho generated artifacts.
- Integration-test module có thể cần kết hợp dữ liệu từ Failsafe, không chỉ Surefire.
- Parent aggregator `packaging=pom` không có bundle bytecode giống JAR module.
- Module mới rất nhỏ hoặc chưa có tests cần **quy tắc rõ**, không tự gán coverage=100% chỉ vì không có file report.

JaCoCo Maven Plugin có goal `prepare-agent` để chuẩn bị agent, `report` tạo báo cáo, `check` đánh giá ngưỡng theo rule cấu hình; `check` thường bind ở phase `verify`. Muốn một gate hiệu lực, phải bảo đảm **execution data thực sự được sinh**, report/check được gọi và rule áp dụng đúng module.

Ví dụ **mảnh cấu hình check**:

~~~xml
<execution>
    <id>verify-coverage</id>
    <phase>verify</phase>
    <goals>
        <goal>check</goal>
    </goals>
    <configuration>
        <rules>
            <rule>
                <element>BUNDLE</element>
                <limits>
                    <limit>
                        <counter>LINE</counter>
                        <value>COVEREDRATIO</value>
                        <minimum>0.80</minimum>
                    </limit>
                </limits>
            </rule>
        </rules>
    </configuration>
</execution>
~~~

Mảnh này **không phải POM chạy JaCoCo hoàn chỉnh**: còn cần plugin declaration/version, cách chuẩn bị agent và lifecycle phù hợp. Với Surefire/Failsafe, không dùng `forkCount=0` nếu mong JaCoCo agent gắn qua `argLine` của forked JVM. Nếu Surefire `argLine` có cấu hình riêng, cần bảo toàn cách JaCoCo cấp JVM agent options.

Một ngoại lệ coverage đúng nên:

1. Chỉ ra **module/bundle/package** cần policy đặc biệt.
2. Xác định ngưỡng, rule hoặc danh sách generated files rõ ràng.
3. Tránh tắt toàn bộ `jacoco:check` ở parent để "giải cứu" một module.
4. Có ticket, owner và ngày xem xét.
5. Được kiểm chứng bằng cả report, check goal và negative test khi thích hợp.

Không nên dùng `jacoco.skip=true` toàn CI để né một module chưa đạt ngưỡng. Nếu muốn ngưỡng khác nhau, có thể dùng cấu hình/inheritance riêng từng child nhưng cần xác nhận effective POM.

## 15. Surefire và Failsafe: không biến "không có test" thành PASS

Trong quality policy, test gate không chỉ là câu lệnh `mvn test`.

### Surefire

Surefire thường chạy unit tests ở phase `test` và ghi `target/surefire-reports`. Một build được đánh dấu SUCCESS không chứng minh **mọi module đã chạy đủ test** nếu chúng bị skip hoặc test discovery patterns không phù hợp.

Có thể cấu hình `failIfNoTests` cho những Java modules **bắt buộc có unit tests**:

~~~xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
~~~

Nhưng nếu áp cứng cho parent packaging `pom` hoặc modules vốn không có tests, cần cân nhắc execution/lifecycle. Trong demo `core` và `legacy-adapter` đều có JUnit tests, nên có thể kiểm tra reports mà không cần ép property này trên mọi loại module.

### Failsafe

Failsafe thường chạy integration tests ở `integration-test` và kiểm tra kết quả tại `verify`. Nếu một module không có IT nhưng team không yêu cầu IT ở module đó, đừng đặt một `failIfNoTests=true` chung không phân biệt module khiến build fail giả.

Nếu module bắt buộc chạy IT, chính sách nên kiểm tra số tests thực sự và goal `failsafe:verify` đã chạy; không chỉ kiểm tra thư mục report có tồn tại.

### Ngoại lệ test policy phải có mục tiêu rõ

Thay vì global `-DskipTests`:

- Cho phép một module chưa có IT bằng cách cấu hình **chỉ Failsafe của module đó**, còn unit tests vẫn chạy.
- Ghi lý do: chưa có external environment hay integration suite nào?
- Xác định thời hạn và owner của kế hoạch thêm tests.
- Kiểm chứng trong CI: module còn chạy Enforcer/JUnit unit gate?
- Không cho phép bypass test ở các modules critical mà không có phê duyệt.

Một policy chung chỉ có giá trị nếu pipeline công bố **gate nào đã chạy, gate nào bị miễn, gate nào không áp dụng**.

## 16. Đừng nhầm Maven profiles với cơ chế ngoại lệ an toàn

Một số nhóm tạo profile:

~~~xml
<profile>
    <id>skip-quality</id>
    <properties>
        <enforcer.skip>true</enforcer.skip>
        <checkstyle.skip>true</checkstyle.skip>
    </properties>
</profile>
~~~

Đây là **anti-pattern để phân tích**, không thêm vào demo runnable. Profile này cho phép tắt nhiều gates, dễ bị CI vô tình bật hoặc bị người dùng dùng làm lối tắt thường xuyên.

Profiles có thể thích hợp cho những kiểm tra **phụ thuộc môi trường** (ví dụ module platform-specific, integration environment), nhưng chúng phải:

- Có tên nêu rõ phạm vi thay vì “bỏ hết”.
- Được kích hoạt/khóa tại đúng pipeline.
- Giữ các baseline gates không liên quan.
- Có output cho thấy profile nào active.
- Có negative test hoặc guard để không âm thầm skip khi release build.

Chạy `mvn help:active-profiles` và xem effective POM trong profile phù hợp giúp phát hiện policy bị thay bởi activation conditions.

### Không dùng property "skip" làm hợp đồng ngoại lệ lâu dài

Các tham số như `-Denforcer.skip=true`, `-Dcheckstyle.skip=true` hay `-DskipTests` tiện để chẩn đoán ngắn hạn, nhưng chúng thường có phạm vi **quá rộng**. Một exception thật nên được khai báo và review trong source-controlled configuration hoặc registry riêng, không phụ thuộc một biến môi trường bí mật mà không ai kiểm tra.

## 17. Test cổng chất lượng như test phần mềm

Quality configuration cũng có thể lỗi. Hãy làm **positive test** và **negative test**.

| Kiểm chứng | Hành động | Kỳ vọng |
| --- | --- | --- |
| Positive baseline | Build source/POM chuẩn trên Maven/JDK đạt yêu cầu. | Enforcer executions + JUnit tests PASS. |
| Negative environment | Trong bản sao, đặt required Java range không đáp ứng. | Build FAIL ở `environment-baseline`. |
| Negative dependency | Trong bản sao, bỏ include trong legacy module. | Build FAIL ở `dependency-policy`. |
| Exception scope | Giữ include chỉ ở legacy module. | `core` vẫn không có quyền dùng dependency bị cấm. |
| Effective model | Xem effective POM của cả core và legacy. | Rules inherited và include xuất hiện đúng nơi. |
| CI test gate | `mvn clean verify`, đọc Surefire reports. | 2 core tests và 1 legacy test chạy. |
| Profile test | Bật đúng CI/release profile. | Các gates bắt buộc vẫn được thực thi. |
| Regression cleanup | Gỡ exception khi không còn dependency cũ. | Mọi modules PASS mà không cần include. |

**Mọi negative tests làm hỏng cấu hình phải diễn ra trên branch/checkout tạm hoặc được hoàn tác có kiểm soát**. Không tạo lỗi giả ngay trên branch release rồi dựa vào việc nhớ sửa lại.

### Vì sao cần kiểm tra vị trí và tên execution?

Maven plugin executions có `id`; khi parent/child cùng khai báo execution ID, Maven dùng cơ chế merge/inheritance. Nếu child dùng ID mới (ví dụ `dependency-policy-legacy` thay vì `dependency-policy`), nó có thể **tạo execution thứ hai**, không phải override policy gốc. Kết quả là rule cấm vẫn chạy và legacy module vẫn FAIL.

Do đó khi tùy biến execution: giữ đúng plugin coordinates, đúng execution ID, đọc effective POM và logs. Không suy luận từ tên file.

### Vì sao không chỉ nhìn `BUILD SUCCESS`?

Một module không bật `-am` khi build chọn lọc có thể dùng dependency binary cũ; một plugin đặt trong management có thể không chạy; một profile có thể tắt gate; một suite có thể không discover tests. Quality gate QA cần **bằng chứng rule đã chạy và có thể fail**, không chỉ exit code 0.

## 18. Triển khai ở CI/CD với bằng chứng có thể kiểm tra

Một pipeline Maven đa module có thể bắt đầu:

~~~bash
mvn -B -ntp clean verify
~~~

Khi chỉ muốn kiểm tra legacy module cùng upstream:

~~~bash
mvn -B -ntp -pl :legacy-adapter -am clean verify
~~~

Các bước CI nên:

1. Dùng Maven/JDK versions được công bố rõ.
2. Checkout đúng commit và dùng root aggregator POM.
3. Ghi lại active profiles và Maven command thực tế.
4. Chạy các Enforcer executions, Surefire và các quality plugin khác được bind.
5. Tải/lưu Surefire, Failsafe, Checkstyle, JaCoCo reports khi có; không để report mất khi job fail.
6. Phân biệt **FAIL**, **PASS**, **NOT RUN** và **APPROVED EXCEPTION** cho từng gate.
7. Xuất danh sách ngoại lệ đang active (module, rule, artifact/file, owner, expiry).
8. So phạm vi exception với policy đã duyệt; thay đổi ngoại lệ phải qua code review.
9. Kiểm tra không có cờ skip toàn cục ngoài chính sách.
10. Lưu build ID, commit, Maven/JDK/plugin versions và hạn xử lý các ngoại lệ.

**Không gửi secrets vào logs:** effective POM và debug output có thể chứa repository URLs, properties hoặc cấu hình nhạy cảm. Giới hạn artifact access phù hợp.

### Ví dụ bảng CI Quality Gate

| Module | JDK/Maven | Dependency rule | Unit tests | Ngoại lệ | Kết luận |
| --- | --- | --- | --- | --- | --- |
| `core` | PASS | PASS | 2 PASS | Không | PASS |
| `legacy-adapter` | PASS | PASS sau include hẹp | 1 PASS | JCL 1.2, được duyệt | PASS với ngoại lệ |
| Module chưa được build | NOT RUN | NOT RUN | NOT RUN | Không kết luận | UNKNOWN |

Bảng mang tính minh họa; không có tool nào tự tạo đầy đủ status, approval và expiry chỉ từ XML POM. CI/quality governance phải định nghĩa cách thu thập và xác minh các trạng thái này.

## 19. Những tình huống khó và trade-off

### 19.1. Parent POM có module không phải Java

Nếu parent được dùng bởi frontend, documentation, BOM hoặc `packaging=pom` modules, không phải plugin nào cũng áp dụng giống nhau. Enforcer runtime/version rule có thể hợp lệ cho root POM; JaCoCo coverage cho POM-only module thường cần skip hoặc execution scope riêng theo thiết kế.

Đặt **baseline phổ quát** ở parent chung, còn **gate đặc thù ngôn ngữ/module type** trong parent tầng dưới hoặc plugin activation ở nhóm modules phù hợp.

### 19.2. Parent nhiều tầng

Một tổ chức có thể có:

~~~text
organization-parent
   │
   ├── java-library-parent
   │      └── core
   │
   └── java-service-parent
          └── service
~~~

Parent tầng tổ chức đặt Maven/JDK/security baseline; parent tầng library/service đặt Checkstyle, Surefire, Failsafe, JaCoCo thresholds phù hợp. Child chỉ khai báo ngoại lệ nhỏ.

Cần xác minh chính xác `<parent>` chain, không cho rằng module ở cùng Git repository luôn kế thừa cùng policy. Nếu một child dùng parent từ remote Maven repository, phiên bản parent policy có thể khác những modules khác; phải kiểm tra effective POM và version release process.

### 19.3. Exception cho transitive dependency

`bannedDependencies` mặc định tìm cả transitive dependencies. Nếu violation nằm ở dependency gián tiếp, có thể:

- Nâng dependency trực tiếp để lấy transitive version khác.
- Dùng Maven `<exclusions>` tại đúng cạnh dependency nếu thư viện bị cấm không cần dùng.
- Thay thư viện hoặc kiến trúc phụ thuộc.
- Nếu thực sự không tránh được, khai báo include exception hẹp, có owner và expiry.

Đừng tắt `searchTransitive` toàn parent chỉ để không nhìn thấy vấn đề: nó có thể bỏ sót những dependency khác cũng bị cấm.

### 19.4. Một version ngoại lệ được nâng cấp

Trong demo include đúng `commons-logging:commons-logging:1.2`. Nếu dependency đổi lên version khác mà rule ban vẫn giữ nguyên, build **cần fail** cho đến khi policy/approval được review. Đó là ưu điểm của exception có version cụ thể.

Tuy nhiên nếu policy đã cho phép một dải versions an toàn, có thể mã hóa range phù hợp thay vì cấp exceptions vụn vặt theo từng patch. Quyết định dựa trên threat model/compatibility, không dựa vào convenience.

### 19.5. Ngoại lệ che lỗi thật

Một module có thể PASS vì include, nhưng điều đó không chứng minh thư viện đã an toàn. Build gate chỉ thực thi **chính sách đã cấu hình**, không thay cho vulnerability scanning hay threat analysis. Exception record phải nêu rủi ro được chấp nhận và biện pháp hạn chế đi kèm.

### 19.6. Parent thay policy và ảnh hưởng diện rộng

Nếu cập nhật Enforcer exclude từ một artifact thành cả group wildcard, mọi child có thể bị ảnh hưởng; những includes cũ có thể vô tình cho phép nhiều hơn dự kiến, hoặc mất hiệu lực. Mỗi policy change nên chạy full Reactor, kiểm tra effective POM ở modules có ngoại lệ và so negative tests.

## 20. Các lỗi thường gặp và hướng sửa

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Parent có Enforcer config nhưng child không thấy goal chạy. | Plugin chỉ nằm ở pluginManagement hoặc child không inherit parent. | Kiểm tra parent chain, `build/plugins`, effective POM và phase binding. |
| Child có rule nhưng `mvn verify` vẫn PASS khi vi phạm. | Execution không bind, `skip` hoặc `fail=false`. | Xem effective POM và thử negative test. |
| Thay execution ở child tạo hai lần Enforcer. | Execution ID khác parent. | Dùng cùng `<id>` nếu định override, xác minh merged model. |
| Ngoại lệ cho một dependency vẫn bị ban. | `includes` không khớp exact GAV/version, hoặc merge mất includes. | Xem effective rule, dependency tree và version thực tế. |
| Ngoại lệ lan sang mọi module. | Include được đặt ở parent thay vì child. | Đưa ngoại lệ về POM module và review các inherited settings. |
| `enforcer.skip=true` khiến cả JDK gate mất hiệu lực. | Skip toàn Enforcer. | Bỏ skip, dùng includes/rule-level exception. |
| Maven/JDK version vẫn không đạt dù đã include. | Include chỉ áp dụng bannedDependencies. | Sửa môi trường hoặc chính sách hợp lệ, không bypass baseline. |
| Core không thể resolve dependency legacy. | Dependency ngoài repo hoặc Reactor/POM version lệch. | Kiểm tra đúng repositories, tọa độ và parent/module dependencies. |
| JaCoCo report trống trên CI. | Agent không chạy, Surefire fork bị tắt, test không được discover. | Kiểm tra `prepare-agent`, `argLine`, `forkCount` và test logs. |
| Checkstyle suppression không có tác dụng. | Chưa bật `SuppressionFilter`, regex không khớp, path sai. | Kiểm tra configLocation, suppressionsLocation và report. |
| Checkstyle pass dù source có lỗi. | Chỉ chạy `checkstyle:checkstyle` để sinh report, chưa có fail gate. | Bind `checkstyle:check` với fail policy phù hợp. |
| `mvn validate` PASS nhưng coverage chưa được kiểm. | JaCoCo check nằm ở `verify`. | Chạy `mvn verify`. |
| Module không có IT bị fail bởi `failIfNoTests=true`. | Chính sách IT áp dụng đồng loạt không theo loại module. | Tách parent/activation, chỉ buộc IT ở modules bắt buộc. |
| CI reports xanh nhưng có 0 tests. | Test skip, naming mismatch hoặc provider config. | Kiểm tra test counts, fail-if-no-tests policy theo module. |
| Parent policy đổi nhưng child dùng version cũ. | Child kế thừa parent release khác. | Rà soát parent coordinates và effective POM. |
| `BUILD SUCCESS` nhưng thực tế gate không chạy. | Plugin thiếu execution hoặc profile không active. | Log execution + negative test, không tin mỗi exit code. |
| Exception để mãi không ai gỡ. | Không có owner/expiry/issue. | Ghi registry, review định kỳ, CI guard expiry. |
| Build chọn lọc dùng binary core cũ. | `-pl` thiếu `-am`. | Chạy `-pl :legacy-adapter -am clean verify`. |
| Rule chặn một dependency ngoài ý muốn. | Transitive dependency match exclude wildcard. | Xem dependency:tree, sửa dependency/exclusion hoặc exception được duyệt. |

## 21. Checklist thiết kế và review quality policy

### 21.1. Chính sách parent

- [ ] Parent POM là nguồn cấu hình chung có version và ownership rõ.
- [ ] Các modules thực sự khai báo `<parent>` đúng; không nhầm aggregation với inheritance.
- [ ] Plugin versions được ghim/managed, không phụ thuộc phiên bản mặc định thay đổi theo môi trường.
- [ ] Các quality goals được kích hoạt bằng `build/plugins` và executions/lifecycle đúng.
- [ ] Enforcer Maven/JDK baseline không bị skip ở modules con.
- [ ] Source/test/coverage gates áp dụng đúng loại module, không buộc POM-only modules có Java coverage.
- [ ] Có cách xác minh effective POM và execution logs trong CI.

### 21.2. Phạm vi ngoại lệ

- [ ] Có lý do kỹ thuật/kinh doanh cụ thể, không chỉ "để build PASS".
- [ ] Ngoại lệ gắn **đúng module** chứ không đặt global ở parent.
- [ ] Chọn scope hẹp nhất: rule, artifact version, file, package, threshold hoặc execution.
- [ ] Không vô hiệu hóa thêm những gate không liên quan.
- [ ] Có owner/approver/ticket/expiry và kế hoạch gỡ bỏ.
- [ ] Đã đọc effective POM sau merge parent/child.
- [ ] Có positive và negative tests chứng minh policy hoạt động.
- [ ] CI ghi PASS với ngoại lệ khác PASS không cần ngoại lệ.
- [ ] Nếu có transitive dependencies, đã kiểm tra cả dependency tree.
- [ ] Không chấp nhận `enforcer.skip`/`skipTests`/`checkstyle.skip` toàn pipeline một cách vô thức.

### 21.3. Trước khi merge PR

- [ ] `mvn -B -ntp clean verify` trên Reactor thật PASS.
- [ ] Đã xem Surefire/Failsafe test count và quality reports.
- [ ] Không có changes ngoài phạm vi POM/rules/exception.
- [ ] Chạy negative test trong branch/checkout thử nghiệm.
- [ ] Plugin and JDK/Maven versions trong CI đúng policy.
- [ ] Xem security/license impact của dependencies được miễn.
- [ ] Exception được phê duyệt, có hạn xem lại thực tế.
- [ ] Có kế hoạch đưa module trở về policy chung.

## 22. Bài tập thực hành

### Bài A — xác định kế thừa

Cho root POM có:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Câu hỏi:

1. Cấu hình này có bảo đảm `enforcer:enforce` được chạy tại `validate` ở mọi child không?
2. Nếu không, phải khai báo plugin/execution ở đâu?
3. Nếu child không khai báo `<parent>` trỏ đúng root, child có tự inherit chỉ vì nằm trong `<modules>` không?
4. Nếu một child tạo execution ID mới, Maven có thể thêm execution hay override cái cũ?

**Gợi ý đáp án:** pluginManagement chỉ quản lý cấu hình khi plugin được dùng, không tự tạo phase execution; cần plugin declaration và goal binding ở parent/build hoặc chỗ kích hoạt thích hợp; aggregation khác inheritance; execution ID phải khớp khi muốn override.

### Bài B — chạy demo

1. Tạo đầy đủ ba POM và bốn Java files ở mục 7.
2. Chạy `mvn --version`, `java -version` để xác nhận Maven/JDK.
3. Chạy `mvn -B -ntp validate`, xác nhận hai Enforcer executions chạy ở các modules.
4. Chạy `mvn -B -ntp clean verify`, kiểm tra `core` có 2 unit tests và `legacy-adapter` có 1 unit test.
5. Chạy `java -cp core/target/classes demo.core.Greeting`, xác nhận stdout `Hello Maven from core`.
6. Chạy `mvn -pl :legacy-adapter -am -B -ntp clean verify` để kiểm chứng selective Reactor.
7. Xem effective POM của cả hai modules và đối chiếu `dependency-policy`/`environment-baseline`.
8. Trong bản sao thử nghiệm, bỏ include ở legacy; xác nhận build fail do banned dependency.
9. Khôi phục include, kiểm tra build PASS; không bỏ baseline gate.
10. Viết record ngoại lệ với owner, ticket, expiry và điều kiện gỡ (dùng thông tin thật nếu áp dụng vào dự án).

### Bài C — chọn cách mở ngoại lệ

Tình huống 1: Checkstyle báo một rule ở một file generated, các file khác đúng.

Tình huống 2: Legacy module cần đúng một version của dependency bị ban, các modules còn lại không dùng.

Tình huống 3: Một module bắt buộc có integration tests nhưng environment chưa sẵn trong CI.

Tình huống 4: Parent phải chạy Maven >=3.8 và Java >=17; một developer định dùng `-Denforcer.skip=true` để build bằng Java cũ.

Hãy đề xuất cho mỗi trường hợp:

- Gate nào cần giữ?
- Có thể mở ngoại lệ hẹp tới file/rule/artifact/module hay không?
- Ai duyệt và khi nào hết hạn?
- Làm positive và negative tests thế nào?
- Có cần thay CI environment thay vì đổi policy không?

**Gợi ý:** (1) suppression đúng file/rule; (2) include đúng artifact/version ở child; (3) xem policy/test environment và có ngoại lệ tạm được ghi nhận cho đúng IT execution khi hợp lệ; (4) nâng JDK/Maven hoặc tuân thủ policy, không skip toàn Enforcer.

### Câu hỏi tự đánh giá

- Aggregator và parent POM khác nhau ở điểm nào?
- `pluginManagement` có tự kích hoạt goal mới ở một phase không?
- Khi nào nên đặt Enforcer trong `build/plugins`?
- Vì sao cần execution ID cố định?
- `bannedDependencies/includes` có tác dụng gì?
- Include artifact có tự thêm dependency đó vào classpath không?
- Vì sao `enforcer.skip=true` quá rộng cho một ngoại lệ?
- Một module đã PASS `validate` có chứng minh unit tests đã chạy không?
- `mvn verify` có tự chạy plugin goal chưa được bind không?
- Làm sao biết một child POM thật sự kế thừa environment gate?
- Vì sao cổng coverage cần agent execution data trước khi dùng `check`?
- Checkstyle suppression cần giới hạn theo file và rule như thế nào?
- Tại sao XML comment không tự làm exception hết hạn?
- Vì sao negative tests quan trọng với quality policy?
- Khi nâng version dependency được miễn từ 1.2 lên phiên bản khác, rule nên phản ứng thế nào?

## 23. Kết luận

**Chính sách chung đặt ở parent; ngoại lệ có chủ đích đặt đúng module và đúng rule.** Maven hỗ trợ thiết kế này thông qua inheritance, plugin executions, cấu hình được quản lý và cơ chế merge giữa parent/child POM.

Ghi nhớ:

- `pluginManagement` quản lý defaults, **không đồng nghĩa mọi quality goal đã được bind/thi hành**.
- `build/plugins` với executions/phase rõ ràng giúp các cổng như Enforcer thực thi và kế thừa theo đúng model.
- Tách baseline environment rule và dependency policy thành những executions có IDs ổn định giúp quản lý phạm vi ngoại lệ.
- `bannedDependencies/includes` cho phép một artifact/version mà vẫn giữ rule chặn các trường hợp khác.
- `enforcer.skip`, `skipTests` hay `checkstyle.skip` là bypass rộng; không dùng như cơ chế ngoại lệ lâu dài nếu chỉ một module/file có vấn đề.
- Effective POM + logs + positive/negative tests mới chứng minh policy **được áp dụng và có thể phát hiện vi phạm**.
- Ngoại lệ cần owner, approval, issue, expiry và kế hoạch loại bỏ; Maven XML không tự thực thi những quy tắc quản trị đó.

Mục tiêu không phải làm mọi pipeline xanh bằng cách nới chuẩn. Mục tiêu là có **một baseline dễ duy trì, các trường hợp đặc biệt minh bạch, và bằng chứng kiểm chứng được rằng phần lớn hệ thống vẫn chịu cùng chất lượng tối thiểu**.

## Tài liệu chính thức

- Apache Maven — POM Reference (inheritance, pluginManagement, plugin configuration): https://maven.apache.org/pom.html
- Apache Maven — Guide to Configuring Plugins: https://maven.apache.org/guides/mini/guide-configuring-plugins.html
- Apache Maven — Guide to Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven Enforcer Plugin — Usage: https://maven.apache.org/enforcer/maven-enforcer-plugin/usage.html
- Maven Enforcer Built-In Rules — Banned Dependencies: https://maven.apache.org/enforcer/enforcer-rules/bannedDependencies.html
- Maven Enforcer Built-In Rules — Require Java Version: https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html
- Maven Enforcer Built-In Rules — Require Maven Version: https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html
- Maven Enforcer Plugin — `enforcer:enforce`: https://maven.apache.org/enforcer/maven-enforcer-plugin/enforce-mojo.html
- Apache Maven Checkstyle Plugin — Suppressions Filter: https://maven.apache.org/plugins/maven-checkstyle-plugin/examples/suppressions-filter.html
- Apache Maven Checkstyle Plugin — `checkstyle:check`: https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html
- JaCoCo — Maven Plugin and `check`: https://www.jacoco.org/jacoco/trunk/doc/maven.html
- JaCoCo — `jacoco:check`: https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html
- Maven Surefire Plugin: https://maven.apache.org/surefire/maven-surefire-plugin/
- Maven Failsafe Plugin: https://maven.apache.org/surefire/maven-failsafe-plugin/
