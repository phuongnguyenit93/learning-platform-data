# Dùng `-am` để build cả các mô-đun đầu vào trong Maven Reactor

## 1. Vấn đề: build một module nhưng thiếu module nó phụ thuộc

Trong một dự án Maven nhiều mô-đun, bạn có thể có ba module liên kết:

~~~text
foundation  ──►  service  ──►  cli

   (cung cấp)       (sử dụng foundation)
                        cli sử dụng service
~~~

Mũi tên ở sơ đồ này biểu thị **chiều cung cấp cho module phía sau**, không phải chiều viết dependency trong POM. Ở góc nhìn Maven, `cli` **phụ thuộc vào** `service` và `service` **phụ thuộc vào** `foundation`.

Bạn muốn chỉ build ứng dụng `cli`, không build các module không liên quan. Nếu chạy:

~~~bash
mvn -pl :cli package
~~~

Maven có thể thất bại vì chưa tìm được artifact của `service` hoặc `foundation` trong local/remote repository; nguy hiểm hơn, nó có thể thành công nhờ bản dependency **cũ** đã cài trước đó.

Lệnh đúng trong trường hợp muốn build cả các module cần thiết **từ source hiện có trong cùng Reactor** là:

~~~bash
mvn -pl :cli -am package
~~~

Trong đó:

- `-pl` là viết tắt của `--projects`: chọn những Maven projects/module muốn build.
- `:cli` là selector theo **artifactId**; dấu hai chấm là một phần cú pháp selector.
- `-am` là viết tắt của `--also-make`: build thêm các Maven projects trong Reactor **mà những projects đã chọn cần tới**.
- `package` là lifecycle phase chạy cho các projects đã được chọn vào build.

Bài Knowledge thuộc nhóm **Reactor nhiều mô-đun** và tập trung sâu vào ý nghĩa, điều kiện, giới hạn và cách dùng `-am`, không lẫn nó với `-amd` hoặc build toàn bộ Reactor.

**Kết quả cần đạt sau bài học:**

1. Hiểu Reactor thu thập modules, sắp thứ tự và thực thi build.
2. Biết khi nào cần `-pl ... -am` và tại sao chỉ `-pl` có thể dùng dependency cũ.
3. Phân biệt **module upstream** (đầu vào) và **module downstream** (tiêu thụ).
4. Hiểu `-am` chỉ xét những projects hiện có trong Reactor, không tải source của mọi dependency từ internet.
5. Dựng một Maven project Java 17 có root aggregator, ba modules phụ thuộc nối tiếp và một module độc lập.
6. Chạy các lệnh `-pl`, `-am`, `-amd`, `test`, `package`, `install` và dự đoán đúng Reactor Build Order.
7. Phân biệt aggregation, inheritance, dependency graph và `dependencyManagement`.
8. Khắc phục tình huống chọn sai POM, thiếu module, dependency version lệch, test thất bại ở module upstream hoặc multi-module build ở CI.

Phạm vi: **Apache Maven 3.x**, POM model 4.0.0, Java 17. Maven 4 có những điểm khác trong cơ chế tìm project root/chọn subprojects, nên không áp dụng tùy tiện các hành vi đặc thù của Maven 4 vào bài này.

## 2. Maven Reactor là gì?

Trong Maven, một POM aggregator có `<modules>` có thể thu thập nhiều Maven projects. Cơ chế thực thi chung được gọi là **Reactor**.

Theo hướng dẫn chính thức của Apache Maven, Reactor có ba việc quan trọng:

1. **Thu thập** các Maven projects/modules khả dụng trong build.
2. **Sắp xếp** các projects sao cho module cần thiết được build trước module phụ thuộc.
3. **Build** tập projects được chọn theo thứ tự và phase/goal yêu cầu.

Một root aggregator thường có:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>cli</module>
    <module>tools</module>
    <module>service</module>
    <module>foundation</module>
</modules>
~~~

Phần tử `<module>` là **đường dẫn thư mục tương đối** chứa một POM module, không phải tên groupId hay dependency tọa độ. Nếu `cli/pom.xml` tồn tại, `<module>cli</module>` hợp lệ.

**Có mặt trong `<modules>` không tự tạo dependency giữa các modules.** Để nói `cli` dùng `service`, module `cli` phải khai báo dependency (hoặc một quan hệ được Maven Reactor biết như plugin/build extension, tùy tình huống).

### Reactor khác local Maven repository

- **Reactor:** tập projects đang tham gia **lần gọi Maven hiện tại**.
- **Local repository:** kho cache/artifacts đã cài ở `~/.m2/repository` hoặc nơi tùy chỉnh.
- **Remote repository:** kho như Maven Central hoặc repository nội bộ.

`-am` chỉ thêm **projects từ Reactor** vào tập cần build. Nó không có nghĩa Maven sẽ tự tìm source code của dependency ở remote repository. Nếu một dependency bên ngoài không nằm trong Reactor, Maven vẫn giải quyết nó bằng cơ chế repository thông thường.

## 3. `-pl` chọn project; `-am` mở rộng sang các đầu vào

Cú pháp thường gặp:

~~~bash
mvn -pl :cli -am clean package
~~~

Viết đầy đủ:

~~~bash
mvn --projects :cli --also-make clean package
~~~

Với Maven 3, có nhiều cách chỉ định project ở `-pl`:

| Selector | Ý nghĩa | Khi nào tiện |
| --- | --- | --- |
| `-pl cli` | Chọn module theo **đường dẫn tương đối** `cli`. | Có cấu trúc thư mục rõ ràng từ root aggregator. |
| `-pl :cli` | Chọn project theo **artifactId** `cli`. | Muốn không phụ thuộc đường dẫn thư mục đơn giản. |
| `-pl dev.example:cli` | Chọn theo **groupId:artifactId**. | Có artifactId trùng trong tập Reactor. |
| `-pl :cli,:tools` | Chọn **nhiều** projects, cách nhau bằng dấu phẩy. | Muốn build một số mục tiêu cùng lúc. |

Dấu `:` trong `:cli` rất quan trọng: một selector tên trần như `cli` là đường dẫn, không phải tự động artifactId. Nếu thư mục tên khác artifactId, `-pl cli` và `-pl :cli` có thể chọn khác nhau hoặc một lệnh thất bại.

### Ý nghĩa logic

Giả sử phụ thuộc:

~~~text
foundation
   ▲
   │ dependency
service
   ▲
   │ dependency
cli

tools (độc lập)
~~~

Khi bạn chọn `-pl :cli`:

~~~text
Chỉ chọn: cli
~~~

Khi thêm `-am`:

~~~text
Chọn ban đầu: cli
Các đầu vào trong Reactor: service, foundation
Các POM parent cần thiết trong Reactor: parent aggregator nếu có
Không cần: tools
~~~

Maven sắp xếp sao cho `foundation` build trước `service`, rồi `cli`. Module độc lập `tools` không tham gia trừ khi được chọn riêng hoặc có quan hệ khiến nó cần thiết.

**Không có quy tắc “`-am` = build mọi module trước trong danh sách `<modules>`”.** `-am` dựa trên **quan hệ giữa projects**, không dựa đơn thuần vào vị trí trước/sau trong XML.

## 4. Đồ thị module đầu vào và đầu ra

Hãy gọi:

- **Upstream modules**: các modules cung cấp dependency/đầu vào cho module được chọn.
- **Downstream modules**: các modules phụ thuộc vào module được chọn.

Với chuỗi:

~~~text
foundation -> service -> cli
~~~

thì:

| Module đang xét | Upstream (cần từ nó) | Downstream (cần nó) |
| --- | --- | --- |
| `foundation` | Không có module thư viện upstream trong sơ đồ | `service`, gián tiếp `cli` |
| `service` | `foundation` | `cli` |
| `cli` | `service`, gián tiếp `foundation` | Không có |
| `tools` | Không có | Không có |

Đồ thị này là đồ thị **dependency giữa modules**, không phải đồ thị gọi hàm ở runtime. Một project vẫn có thể phụ thuộc vào external libraries như JUnit, nhưng chúng không phải reactor modules của demo.

### `-am` và `-amd` ngược hướng

| Cờ | Tên dài | Phạm vi |
| --- | --- | --- |
| `-am` | `--also-make` | Build thêm projects mà những projects được chọn **cần**. |
| `-amd` | `--also-make-dependents` | Build thêm projects **phụ thuộc vào** những projects được chọn. |

Ví dụ:

~~~bash
mvn -pl :cli -am package
~~~

chọn `cli` và các upstream `service`, `foundation`.

Ngược lại:

~~~bash
mvn -pl :foundation -amd package
~~~

hướng đến `foundation` và các downstream `service`, `cli`. Trong demo, `tools` độc lập nên không được chọn. `-amd` phù hợp khi thay thư viện lõi và muốn xem các module tiêu thụ còn build/test được không.

**Cẩn trọng:** với đồ thị thực có nhánh phụ thuộc phức tạp, hãy kiểm tra Reactor Build Order/summary. Đừng suy đoán danh sách cuối từ một đồ thị đơn giản khi project có plugin dependencies, parent, profiles hoặc modules con lồng nhau.

## 5. Reactor sắp xếp theo quan hệ thực, không chỉ theo thứ tự XML

Apache Maven 3 mô tả những quan hệ được Reactor xét khi sắp xếp projects:

- Dependency của một project vào một module khác trong cùng build.
- Plugin declaration nếu plugin cũng là module trong build.
- Plugin dependency trên một module trong build.
- Build extension sử dụng module trong build.
- Quan hệ POM parent khi parent là project trong build.
- Thứ tự `<modules>` làm quy tắc khi không có các quan hệ trên buộc một thứ tự khác.

**Quan trọng:** chỉ các tham chiếu thật sự được instantiate mới ảnh hưởng Reactor sorting. Chỉ liệt kê một dependency trong `<dependencyManagement>` hoặc plugin trong `<pluginManagement>` **không tự tạo cạnh dependency** và không làm Reactor bắt buộc build module đó trước.

Ví dụ root POM cố tình để module `cli` trước `foundation`:

~~~xml
<modules>
    <module>cli</module>
    <module>tools</module>
    <module>service</module>
    <module>foundation</module>
</modules>
~~~

Nếu `cli` khai báo dependency vào `service` và `service` khai báo dependency vào `foundation`, Reactor vẫn phải sắp xếp `foundation` và `service` trước `cli`. Không nên dựa vào thứ tự modules trong root POM để sửa lỗi dependency thiếu: phải sửa **dependency declarations đúng**.

### Aggregation và inheritance là hai khái niệm khác nhau

**Aggregation** là root POM có `<modules>` để thu thập project.

**Inheritance** là module con khai báo `<parent>` để kế thừa groupId/version/properties/pluginManagement và những phần POM hợp lệ khác.

Một project có thể được aggregate nhưng **không cần** inherit chính POM aggregator đó; ngược lại module có parent POM nhưng root build hiện tại không nhất thiết aggregate mọi module cùng repository. Trong demo, root vừa là **aggregator vừa là parent** để đơn giản.

Việc root có `packaging=pom` không có nghĩa root là một Java JAR. Root thường thực hiện mục đích quản lý cấu hình chung và tạo POM artifact của chính nó.

## 6. Ví dụ Java 17: bốn modules, ba dependency nối tiếp

Ta tạo project:

~~~text
maven-am-demo/
├── pom.xml
├── foundation/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/example/foundation/MessageSource.java
│       └── test/java/dev/example/foundation/MessageSourceTest.java
├── service/
│   ├── pom.xml
│   └── src/main/java/dev/example/service/GreetingService.java
├── cli/
│   ├── pom.xml
│   └── src/main/java/dev/example/cli/Main.java
└── tools/
    ├── pom.xml
    └── src/main/java/dev/example/tools/ToolsMain.java
~~~

Các modules có vai trò:

- `foundation`: cung cấp hàm tạo thông điệp.
- `service`: dùng `foundation` để tạo lời chào.
- `cli`: dùng `service` để in lời chào.
- `tools`: module ứng dụng độc lập, **không liên quan đến CLI**; giúp bạn quan sát `-am` có chọn thừa module không.

Có một JUnit 5 test trong `foundation` để kiểm tra rằng khi `-am` chọn upstream, **lifecycle test phase cũng chạy cho module đầu vào**, chứ không chỉ lấy artifact từ cache.

### 6.1. Root `pom.xml` hoàn chỉnh

Tạo file `maven-am-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>maven-am-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>cli</module>
        <module>tools</module>
        <module>service</module>
        <module>foundation</module>
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
~~~

**Tại sao cố tình đặt `cli` trước `foundation` trong `<modules>`?** Để chứng minh Maven không buộc build modules theo thứ tự khai báo khi có dependency graph. Root POM quản lý version compiler/Surefire/JAR plugins, nhưng phần `pluginManagement` **không tự tạo quan hệ module dependency**.

### 6.2. `foundation/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>maven-am-demo</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>foundation</artifactId>

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

Ở đây parent cung cấp groupId, version và các plugin versions; module chỉ thêm artifactId `foundation` và test dependency. JUnit từ Maven repository là **external dependency**, không phải module được `-am` build từ source trong demo.

### 6.3. `foundation/src/main/java/dev/example/foundation/MessageSource.java`

~~~java
package dev.example.foundation;

public final class MessageSource {
    private MessageSource() {
    }

    public static String message(String name) {
        return "Hello " + name + " from foundation";
    }
}
~~~

Đây là mã Java 17 hợp lệ, không có external runtime dependency.

### 6.4. `foundation/src/test/java/dev/example/foundation/MessageSourceTest.java`

~~~java
package dev.example.foundation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageSourceTest {
    @Test
    void buildsMessage() {
        assertEquals(
                "Hello Maven from foundation",
                MessageSource.message("Maven"));
    }
}
~~~

Tên class `MessageSourceTest` phù hợp discovery convention của Maven Surefire; JUnit Jupiter 5.11.4 chạy test. Khi `foundation` tham gia build tới phase `test` hoặc xa hơn (như `package`/`verify`), test method này được kiểm tra.

**Không kết luận chỉ từ một dòng test log rằng tất cả modules đã được build.** Reactor summary mới là nơi xem module nào tham gia.

### 6.5. `service/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>maven-am-demo</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service</artifactId>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>foundation</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

Đây là **cạnh dependency thực** trong Reactor: `service` cần `foundation`. Biểu thức `${project.version}` dùng version của project `service` đã kế thừa là `1.0-SNAPSHOT`.

**Quan trọng:** nếu bỏ hẳn dependency khỏi `service` và chỉ khai báo `foundation` trong `dependencyManagement` của parent, không thể import `MessageSource` từ Java code service theo cách tự động. DependencyManagement chỉ quản lý version/scope/... của dependency **khi dependency được khai báo**.

### 6.6. `service/src/main/java/dev/example/service/GreetingService.java`

~~~java
package dev.example.service;

import dev.example.foundation.MessageSource;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(String name) {
        return MessageSource.message(name) + " via service";
    }
}
~~~

Method này gọi class từ `foundation`. Maven phải cung cấp `foundation` khi compile `service`. Lệnh `-am` cho phép build version nguồn mới của `foundation` trong cùng invocation thay vì hy vọng local repository đã có artifact phù hợp.

### 6.7. `cli/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>maven-am-demo</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>cli</artifactId>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>service</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

`cli` phụ thuộc **trực tiếp** vào `service`. `service` phụ thuộc vào `foundation`, nên `foundation` là dependency **gián tiếp/transitive** của `cli`. `-am` phải xét các dependency modules cần thiết trong graph của Reactor, không chỉ module nằm một cạnh ngay sát project đã chọn.

### 6.8. `cli/src/main/java/dev/example/cli/Main.java`

~~~java
package dev.example.cli;

import dev.example.service.GreetingService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(GreetingService.greet("Maven"));
    }
}
~~~

Chương trình in lời chào được tạo xuyên qua hai module upstream. Nó không dùng thư viện ngoài JDK ngoài chính các reactor modules đã khai báo.

### 6.9. `tools/pom.xml` — module độc lập

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>maven-am-demo</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>tools</artifactId>
</project>
~~~

`tools` không khai báo dependency trên `foundation`, `service` hay `cli`. Mặc dù có mặt trong root `<modules>`, nó **không là upstream input của CLI**.

### 6.10. `tools/src/main/java/dev/example/tools/ToolsMain.java`

~~~java
package dev.example.tools;

public final class ToolsMain {
    private ToolsMain() {
    }

    public static void main(String[] args) {
        System.out.println("Tools module");
    }
}
~~~

Class này chỉ nhằm minh họa rằng project `tools` có thể build độc lập. Nó không được CLI gọi, và trong lệnh `-pl :cli -am`, module `tools` không nằm trong tập projects được build.

## 7. Thực hành A — build toàn bộ Reactor

Từ thư mục `maven-am-demo` chứa root `pom.xml`:

~~~bash
mvn --version
java -version
mvn clean package
~~~

Lệnh **không dùng `-pl`** thông thường build tất cả projects mà aggregator đã thu thập:

~~~text
maven-am-demo (parent/aggregator)
foundation
service
cli
tools
~~~

Với dependency graph đã khai báo, `foundation` phải đứng trước `service` và `service` trước `cli`. Vì `tools` độc lập, vị trí của nó so với các modules không phụ thuộc có thể phụ thuộc thứ tự modules hoặc cách Reactor sắp xếp. **Không dùng một thứ tự đầy đủ duy nhất của cả năm modules làm assertion cứng nếu nhiều thứ tự đều hợp lệ.**

Khi thành công:

- `foundation/target/classes` có `MessageSource.class`.
- `service/target/classes` có `GreetingService.class`.
- `cli/target/classes` có `Main.class`.
- `tools/target/classes` có `ToolsMain.class`.
- Surefire ở `foundation` có thể in tổng **1 test, 0 failures, 0 errors, 0 skipped**.
- Các module JAR có thể tạo file `foundation-1.0-SNAPSHOT.jar`, `service-1.0-SNAPSHOT.jar`, `cli-1.0-SNAPSHOT.jar` và `tools-1.0-SNAPSHOT.jar`.

Đây là **kết quả kỳ vọng** cho source/POM của bài, không phải toàn bộ log Maven cố định. Đường dẫn, thời lượng và thứ tự các project độc lập tùy build.

## 8. Thực hành B — chỉ `-pl`, không `-am`

Chạy trong root:

~~~bash
mvn -pl :cli package
~~~

Tập projects được yêu cầu chỉ là `cli`. Maven sẽ **không tự build mọi upstream từ source** chỉ vì code trong module đó import chúng. Nó cố giải quyết `dev.example:service:1.0-SNAPSHOT` và các dependencies liên quan theo cơ chế Maven.

Có hai khả năng điển hình:

1. **Chưa có artifact phù hợp trong repositories** → build `cli` có thể fail vì không giải quyết được `service` hoặc parent/dependency metadata.
2. **Đã có artifacts cũ trong local repository** → build có thể pass nhưng dùng version binary cũ, không phản ánh chỉnh sửa source mới ở `service` hoặc `foundation`.

Vì vậy không nên viết tài liệu rằng “`mvn -pl :cli package` luôn fail” hoặc “luôn dùng source mới”. Kết quả phụ thuộc cache/repositories và project context.

### Vì sao chỉ build `cli` dễ gây nhầm?

Giả sử bạn đã thay:

~~~java
return MessageSource.message(name) + " via service";
~~~

ở `GreetingService.java` nhưng chỉ chạy `mvn -pl :cli package`. Nếu Maven lấy `service-1.0-SNAPSHOT.jar` đã cài trước đó, bytecode đang chạy **không nhất thiết** chứa thay đổi mới. `-am` là cách buộc các upstream reactor projects tham gia cùng build invocation.

**Không dùng việc build success một mình làm bằng chứng upstream source đã được biên dịch lại.** Hãy xem Reactor Build Order/summary.

## 9. Thực hành C — `-pl :cli -am`: build cả các đầu vào

Lệnh trọng tâm:

~~~bash
mvn -pl :cli -am clean package
~~~

Maven chọn `cli` rồi mở rộng tập thành các upstream projects có trong Reactor:

~~~text
maven-am-demo (POM parent)
foundation
service
cli
~~~

**Không chọn `tools`**, vì nó không phục vụ dependency của CLI.

### Thứ tự bắt buộc theo graph

Trong ví dụ này, các ràng buộc cần thỏa:

~~~text
parent POM
   │
   ▼
foundation
   │
   ▼
service
   │
   ▼
cli
~~~

Vì cả ba modules dùng cùng parent POM trong Reactor và dependency chain rõ ràng, thứ tự trên là kết quả mong đợi. Để kiểm chứng, tìm đoạn `Reactor Build Order` và `Reactor Summary` trong Maven log.

Một **đoạn tóm tắt minh họa**:

~~~text
[INFO] Reactor Build Order:
[INFO] maven-am-demo
[INFO] foundation
[INFO] service
[INFO] cli
...
[INFO] Reactor Summary:
[INFO] maven-am-demo ........................ SUCCESS
[INFO] foundation ........................... SUCCESS
[INFO] service .............................. SUCCESS
[INFO] cli .................................. SUCCESS
[INFO] BUILD SUCCESS
~~~

Tên hiển thị, dấu chấm, version và thời lượng trong log thật có thể khác. **Điểm kiểm tra được là tập projects và quan hệ build order**, không phải sao chép chính xác spacing.

### Nếu `tools/target` vẫn còn thì sao?

Giả sử bạn đã chạy full build trước đó, sau đó chạy selective build. Vì `tools` không được chọn, các file cũ ở `tools/target` có thể vẫn tồn tại; việc nhìn thấy thư mục này **không chứng minh** `tools` đã được build trong lệnh `-pl :cli -am` hiện tại.

Quan trọng hơn: `clean` trong một reactor build chọn lọc chỉ chạy trên các projects được thực thi. Nó không dọn toàn bộ mọi `target` của các module không chọn. Để khẳng định có tham gia build hay không, đọc Reactor summary của **đúng invocation**, không suy luận từ file cũ.

## 10. Kiểm chứng kết quả Java 17

Sau khi:

~~~bash
mvn -pl :cli -am clean package
~~~

đã build thành công, chạy Java với cả ba module output trên classpath.

### Linux/macOS (Bash)

~~~bash
java -cp "cli/target/classes:service/target/classes:foundation/target/classes" dev.example.cli.Main
~~~

### Windows PowerShell

~~~powershell
java -cp "cli\target\classes;service\target\classes;foundation\target\classes" dev.example.cli.Main
~~~

**Stdout chính xác của chương trình:**

~~~text
Hello Maven from foundation via service
~~~

Lý do cần cả ba directories:

- `cli/target/classes` chứa `Main.class`.
- `service/target/classes` chứa `GreetingService.class`.
- `foundation/target/classes` chứa `MessageSource.class`.

Dấu ngăn classpath là `:` trên Linux/macOS và `;` trên Windows. Trên Windows, dùng dấu nháy để shell không diễn giải dấu chấm phẩy như separator lệnh PowerShell.

**Không dùng `java -jar cli/target/cli-1.0-SNAPSHOT.jar` trong demo**: JAR Plugin mặc định không thêm manifest `Main-Class` và không gộp reactor dependencies vào một JAR. Ví dụ chạy qua `java -cp` là phù hợp với main classes và classpath hiện có.

### Dùng JARs thay directories cũng được

Sau `package` có thể chạy (Linux/macOS):

~~~bash
java -cp "cli/target/cli-1.0-SNAPSHOT.jar:service/target/service-1.0-SNAPSHOT.jar:foundation/target/foundation-1.0-SNAPSHOT.jar" dev.example.cli.Main
~~~

Kết quả vẫn là:

~~~text
Hello Maven from foundation via service
~~~

Nhưng điều này chỉ đúng nếu các JAR thực tế đã được build đúng như demo. Nếu dự án dùng Shade, Assembly hoặc plugins thay archive, kiểm tra classpath và artifact phù hợp.

## 11. Thực hành D — xem test upstream có chạy hay không

Chạy:

~~~bash
mvn -pl :cli -am clean test
~~~

Vì `-am` đưa `foundation` vào Reactor build, Maven chạy lifecycle tới phase `test` cho module đó, nên `MessageSourceTest` được thực thi theo cấu hình Surefire.

Bạn nên thấy ý nghĩa tương đương:

~~~text
Running dev.example.foundation.MessageSourceTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

Đây là **log minh họa của plugin**, không phải toàn bộ stdout cố định. Khi build chỉ qua phase `test`, có thể chưa có các file JAR do `package` tạo, nhưng các classfiles ở `target/classes` của các modules đã được biên dịch, đủ để chạy Java `-cp` như mục 10.

### `-DskipTests` không làm `-am` hết hiệu lực

Ví dụ:

~~~bash
mvn -pl :cli -am -DskipTests package
~~~

`-am` vẫn chọn upstream modules như trước. `-DskipTests` yêu cầu plugins kiểm thử phù hợp **không chạy tests**; test source vẫn có thể được biên dịch. Không dùng `-DskipTests` như cách chọn module hoặc loại upstream khỏi Reactor.

Tùy chọn `-Dmaven.test.skip=true` thường bỏ cả **test compilation** và test execution ở các plugin hỗ trợ nó. Đây là hành vi khác `-DskipTests`, nhưng cả hai đều **không thay đổi hướng phụ thuộc của `-am`**.

**Không khuyến nghị skip tests cho release/CI kiểm chứng** chỉ để làm Reactor Build Order ngắn hoặc tránh lỗi unit test tại upstream module.

## 12. Thực hành E — chỉ build đến `service`

Lệnh:

~~~bash
mvn -pl :service -am clean package
~~~

Các projects mong đợi:

~~~text
maven-am-demo
foundation
service
~~~

`cli` là **downstream consumer** của `service` nên không được chọn bởi `-am`. `tools` độc lập nên cũng không được chọn.

Nếu bạn chỉ sửa `service` và muốn build module ấy cùng input, đây là lệnh phù hợp. Nếu muốn kiểm thử **cả CLI tiêu thụ service** có còn hoạt động hay không, cân nhắc `-amd` hoặc chọn `cli` làm mục tiêu thay vì chỉ `-am` trên service.

## 13. Thực hành F — chiều ngược lại với `-amd`

Chạy:

~~~bash
mvn -pl :foundation -amd clean package
~~~

`-amd` là **also make dependents**: ngoài `foundation`, Reactor tìm những projects **phụ thuộc vào nó**, trực tiếp hoặc qua chuỗi modules. Trong demo, điều này bao gồm `service` và `cli`. `tools` độc lập không cần được chọn.

| Lệnh | Mục tiêu gốc | Hướng bổ sung | Các modules ứng dụng được mong đợi |
| --- | --- | --- | --- |
| `-pl :cli -am` | `cli` | Upstream | `foundation`, `service`, `cli` |
| `-pl :service -am` | `service` | Upstream | `foundation`, `service` |
| `-pl :foundation -am` | `foundation` | Upstream | `foundation` |
| `-pl :foundation -amd` | `foundation` | Downstream | `foundation`, `service`, `cli` |
| `-pl :tools -am` | `tools` | Upstream | `tools` |

Trong ví dụ, root parent POM có thể xuất hiện như project cần thiết vì các child inherit nó. Bảng tập trung vào **các module ứng dụng/JAR**, không hiển thị parent ở mỗi ô.

Khi đổi sang một project có nhánh phụ thuộc phức tạp, `-amd` chỉ là hướng mở rộng theo quan hệ dependents; không được suy luận rằng nó cũng tự thêm mọi upstream của từng dependent theo cách `-am` làm. Nếu cần cả hai nhóm trong một job, hãy chọn flags và project set theo khả năng Maven version, kiểm tra Reactor summary và build thực tế.

## 14. Chọn nhiều modules với `-pl` và `-am`

Bạn có thể chọn cả CLI và Tools:

~~~bash
mvn -pl :cli,:tools -am package
~~~

Tập gốc có hai modules; `-am` bổ sung upstream của `cli`, còn `tools` được giữ lại vì người dùng đã chọn nó:

~~~text
foundation
service
cli
tools
(+ parent POM theo quan hệ trong Reactor)
~~~

Maven chỉ build một project **một lần trong một invocation**, dù nó là dependency cần bởi nhiều selected modules. Điều này là lợi thế so với việc chạy thủ công `mvn install` riêng cho từng module, dễ build lặp và tạo các kết quả không đồng bộ.

### Tránh typo selector

Ví dụ:

~~~bash
mvn -pl :clii -am package
~~~

sẽ không tự “đoán gần đúng” `cli`. Maven 3 thường báo lỗi project được chọn không tìm thấy trong Reactor. Hãy kiểm tra artifactId thật, dấu `:`, path và root POM. Nếu đang ở thư mục con, selector dạng path có thể phụ thuộc cách bạn chỉ định aggregator.

## 15. Root working directory và `-f`

Lệnh trong bài được chạy từ **root `maven-am-demo`**. Nếu đang đứng trong module `cli`, Maven 3 thường không có đủ ngữ cảnh aggregator/root Reactor chỉ bằng `mvn -am package`.

Để chỉ định root POM khi ở `cli/`, dùng:

~~~bash
mvn -f ../pom.xml -pl :cli -am clean package
~~~

`-f` là viết tắt của `--file`: yêu cầu Maven bắt đầu từ POM mà bạn chỉ định, trong ví dụ là root aggregator. Khi đó các modules được thu thập theo `<modules>` của root.

**Không nhầm:**

- `-f ../pom.xml`: chọn POM để Maven khởi tạo project/Reactor.
- `-pl :cli`: chọn project cần build từ tập đã thu thập.
- `-am`: mở rộng sang những projects input trong tập đó.
- `package`: phase cần thực thi cho tập projects sau khi lựa chọn.

Nếu mở terminal trong một nested module, có các POM aggregator khác nhau hoặc CI dùng working directory khác, hãy log rõ `pwd`/working directory và lệnh Maven đầy đủ. Nhiều lỗi “không tìm thấy selected project trong Reactor” là do Maven đang nhìn **sai POM aggregator**, không phải do `-am` hỏng.

## 16. `-am` không tự cài artifact vào local repository

Lệnh:

~~~bash
mvn -pl :cli -am package
~~~

chạy tới phase `package` cho các projects đã chọn, tạo JARs cần thiết trong `target`. Nó **không tự thực hiện `install`**.

Nếu thật sự muốn đưa artifact của selected projects và upstream vào local Maven repository:

~~~bash
mvn -pl :cli -am install
~~~

Đây là lifecycle build tới `install`. Với demo, các artifact/POM cần thiết sẽ được cài theo chính sách Maven vào local repository (thường trong `~/.m2/repository/dev/example/...`), còn `tools` không được cài do không được chọn.

### Vì sao build `package` vẫn giải quyết được dependency trong Reactor?

Khi Maven đang build nhiều modules cùng invocation, nó có khả năng dùng các project/artifacts do Reactor đang tạo để giải quyết **intra-reactor dependencies**, thay vì bắt bạn `mvn install` upstream trước. Đó là mục tiêu thực dụng của `-pl ... -am`.

Nếu bạn chuyển sang một invocation mới chỉ chọn `cli` mà không có `-am`, Maven có thể cần dependency đã cài trong repository. Vì vậy “đã chạy `package` có `-am` hôm qua” không đồng nghĩa hôm nay có thể bỏ `-am` và chắc chắn resolve được mọi upstream.

### Không nhầm `install` với `deploy`

`mvn deploy` có thể đẩy artifacts đến remote repository **nếu project có distributionManagement hoặc repository config thích hợp và bạn có quyền**. Đừng dùng `mvn -pl :cli -am deploy` như một bài kiểm tra vô hại ở hệ thống thật: nó có thể phát hành cả upstream modules được chọn.

Để thực hành cơ chế `-am`, `clean package` hoặc `clean verify` đủ an toàn hơn và không cần publish.

## 17. Vì sao `-am` không tự giải quyết mọi lỗi dependency?

### 17.1. Dependency bên ngoài Reactor

Nếu `service` phụ thuộc vào `org.apache.commons:commons-lang3`, còn root `<modules>` không có một Maven project xây commons-lang3, `-am` không tự tải source commons-lang3 để build. Maven vẫn lấy binary artifact từ repositories theo cơ chế thông thường.

**Reactor scope** quyết định upstream nào được build, **dependency resolver** quyết định artifact ngoài Reactor được lấy từ đâu. Hai cơ chế liên quan nhưng không giống nhau.

### 17.2. Module không nằm trong `<modules>` đang active

Giả sử directory `another-library` tồn tại nhưng không được aggregator root thu thập, `-am` không thể tự đoán đây là một module đầu vào chỉ vì folder có `pom.xml`.

Nếu modules được khai báo trong Maven profile và profile đó không active, tập Reactor cũng có thể khác. Hãy kiểm tra root POM, active profiles và Reactor Build Order.

### 17.3. Version mismatch

`cli` phụ thuộc:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>service</artifactId>
    <version>2.0-SNAPSHOT</version>
</dependency>
~~~

nhưng module `service` đang có project version `1.0-SNAPSHOT`. Dù có project source `service` trong Reactor, **tọa độ không khớp**, Maven có thể phải giải quyết phiên bản `2.0-SNAPSHOT` từ repository và không dùng module source hiện tại theo ý bạn.

Đây là **mảnh POM cố ý sai trong demo** để giải thích vấn đề, không chèn vào `cli/pom.xml` runnable. Sửa dependency version cho khớp với module thực, hoặc dùng cơ chế quản lý versions phù hợp.

### 17.4. Chưa khai báo dependency thật

`service` chỉ có import Java:

~~~java
import dev.example.foundation.MessageSource;
~~~

nhưng không khai báo `<dependency>` trên `foundation` trong `service/pom.xml`. Khi đó Reactor không thể xác định đúng dependency chỉ từ import trong source code; compiler cũng có thể thiếu classpath entry. **`-am` không scan toàn bộ Java source để suy luận Maven dependencies.**

### 17.5. Parent POM không được resolve

Root aggregator và Maven parent không bắt buộc là cùng một POM. Nếu project module dùng một parent bên ngoài và parent chưa có trong local/remote repository, Maven phải resolve parent theo `relativePath` hoặc repositories; `-am` không tự chữa mọi lỗi parent resolution.

Trong demo, mỗi module có:

~~~xml
<relativePath>../pom.xml</relativePath>
~~~

nên Maven biết parent ở root. Nếu CI chỉ checkout một module mà thiếu root POM, cấu hình inheritance có thể không resolve được.

### 17.6. Lỗi plugin, JDK, test hoặc cấu hình không liên quan lựa chọn module

`-am` chỉ mở rộng project set; nó không sửa:

- Maven plugin version không tương thích với JDK.
- Unit test assertion fail ở upstream module.
- Missing resources hoặc source compile errors.
- External dependency không tải được vì repository/proxy.
- Cyclic dependencies khiến Reactor không thể sắp xếp.
- CI memory hoặc timeout quá thấp.

Đừng đặt `-am` như một cờ “fix mọi build failure”. Đầu tiên xác định lỗi do **thiếu reactor upstream** hay nguyên nhân khác.

## 18. Dependency graph khác `dependencyManagement`

Một parent POM có thể quản lý version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>foundation</artifactId>
            <version>1.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **quản lý thông số** dependency. Nó không tự thêm `foundation` vào classpath của mọi child module.

`service` vẫn cần:

~~~xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>foundation</artifactId>
    </dependency>
</dependencies>
~~~

khi thực sự dùng class từ foundation. Đây là ví dụ **thay thế** cho khai báo có version tường minh trong POM runnable: nếu version được quản lý từ parent thì dependency ở child có thể bỏ `<version>`.

Tương tự, `pluginManagement` quản lý versions/configuration khi plugins được dùng, nhưng **không tự đặt cạnh dependency giữa các modules**. Tài liệu Apache Maven nhấn mạnh Reactor sorting xét các tham chiếu instantiated chứ không dùng những entries chỉ có ở management để sắp xếp projects.

## 19. `-am` và các tính năng Reactor khác

### 19.1. `-N` / `--non-recursive`

~~~bash
mvn -N validate
~~~

Chỉ xây project hiện tại, không tạo recursive Reactor build từ `<modules>`. Nếu bạn cần `-am` tìm upstream sibling projects, `-N` đi ngược mục tiêu đó vì nó giảm phạm vi projects được thu thập.

### 19.2. `-rf` / `--resume-from`

Khi một module thất bại trong Reactor, Maven có thể gợi ý resume từ module đó:

~~~bash
mvn -rf :service package
~~~

Nhưng resume **không đồng nghĩa** tự build lại tất cả prerequisites của nó. Nếu module upstream chưa được install và lần build mới không đưa chúng vào Reactor, bạn có thể gặp lỗi dependency resolution. Với Maven 3, một cách dễ hiểu và thường đáng tin hơn khi muốn tái build phần phụ thuộc là chọn target rồi dùng `-am`:

~~~bash
mvn -pl :cli -am package
~~~

Lệnh này có thể làm nhiều việc hơn resume một phần, nhưng đảm bảo target và các upstream trong Reactor cùng được xem xét. Khi tối ưu CI cho project lớn, hãy lựa chọn theo log lỗi và trạng thái artifacts thật thay vì cố dùng resume mọi trường hợp.

### 19.3. `-T` / `--threads`

~~~bash
mvn -T 2 -pl :cli -am package
~~~

`-T 2` cho phép Maven reactor build song song khi các module **độc lập** với nhau. Nó không xóa dependency order: `foundation` vẫn phải được build trước khi `service` cần nó, và `service` trước `cli`. Với một chain tuyến tính, tăng threads có thể không đem lại lợi ích.

Trong đồ thị có nhánh độc lập, các modules có thể được xử lý song song sau khi prerequisites sẵn sàng. Đừng đặt `-T` cao mà không tính RAM, CPU, concurrent tests và resource contention.

### 19.4. `-fae`, `-ff`, `-fn`

Những tùy chọn xử lý lỗi Reactor:

- `-ff` / `--fail-fast`: dừng sớm khi module fail; là hành vi mặc định thường gặp.
- `-fae` / `--fail-at-end`: cố gắng build những modules khác không bị chặn và báo lỗi tổng vào cuối.
- `-fn` / `--fail-never`: cố gắng không trả exit failure cho toàn bộ Maven invocation; **rất nguy hiểm** nếu CI chỉ dựa exit code để đánh dấu PASS.

Chúng **không thay đổi mục tiêu chính của `-am`**. Nếu `foundation` fail compile, `service` hoặc `cli` vẫn không có dependency hợp lệ chỉ nhờ `-fae`. Dùng fail-at-end để thu thập thêm lỗi ở các nhánh độc lập, không để lờ đi một prerequisite bị hỏng.

## 20. CI: chọn đúng tập upstream, tránh stale dependencies

### CI cho một ứng dụng CLI

Từ root repository, pipeline có thể chạy:

~~~bash
mvn --batch-mode -pl :cli -am clean verify
~~~

Điều này kiểm tra cả upstream `foundation` và `service` trong build context hiện tại. Nếu unit test `MessageSourceTest` fail, job có thể fail trước khi build xong `cli`; đó là tín hiệu đúng vì CLI phụ thuộc vào nền tảng lỗi.

**Không cần `install` cho mọi bước CI** nếu mục tiêu chỉ verify reactor source. `install` có thể dùng khi job khác cần các artifact qua local repository, nhưng cũng dễ làm cache bị nhiễm SNAPSHOT cũ. Trong build một lần từ source, `-am` cho phép dependency resolution trong Reactor.

### CI kiểm tra thay đổi thư viện core

Nếu một commit sửa `foundation`, có thể dùng:

~~~bash
mvn --batch-mode -pl :foundation -amd clean verify
~~~

để lựa chọn các **dependents**. Trong demo, `service` và `cli` đều phụ thuộc vào `foundation`. Tuy nhiên với build graph phức tạp, hãy xác nhận tập projects trong Reactor Build Order, nhất là khi có parent/plugin modules hoặc một phần modules không nằm trong scope hiện tại.

### Dùng cache đúng cách

Local repository là cache hữu ích nhưng không phải nguồn sự thật cho những source modules vừa sửa:

- Chỉ `-pl :cli` có thể dùng artifact cũ của `service`.
- `-pl :cli -am` đưa upstream source projects vào cùng build để giải quyết chính xác dependencies nội bộ tương ứng.
- External dependencies vẫn có thể cần tải hoặc lấy từ cache.
- `--offline` / `-o` chỉ dùng khi dependencies/plugins cần thiết đã sẵn trong cache; `-am` không tạo được những external artifacts bị thiếu.

### Không coi timestamp file là bằng chứng duy nhất

Một file trong `tools/target` có thể đến từ lần build trước, còn `service/target` có thể đã được tạo lại. Hãy lưu **command, commit, Maven/JDK versions và Reactor summary** để biết module nào thực sự đã build trong job.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `-pl :cli package` báo không resolve được `service`. | Chưa có upstream artifact ở repo; thiếu `-am`. | Chạy từ root với `-pl :cli -am package`. |
| `-pl :cli package` PASS nhưng không thấy thay đổi mới. | Maven dùng upstream dependency đã install cũ. | Dùng `-am`, kiểm tra reactor summary và class output. |
| Thêm `-am` vẫn không thấy `foundation`. | Foundation chưa thuộc Reactor, version không khớp hoặc thiếu dependency thật. | Kiểm tra root modules, service dependency và tọa độ. |
| Maven báo selected project không tìm thấy. | Dùng sai POM, sai selector/path/artifactId. | Dùng root `-f`, `-pl :cli` hoặc tọa độ đầy đủ. |
| `-am` build quá nhiều modules. | Target có nhiều dependencies thực trong Reactor hoặc chọn nhiều projects. | Xem Reactor dependency graph, đừng bỏ prerequisite bừa. |
| `-am` không build `tools`. | Tools là module độc lập. | Đây là kết quả đúng; chọn `-pl :tools` nếu muốn build nó. |
| `-am` không build các modules phụ thuộc vào `foundation`. | `-am` là upstream; dependents là downstream. | Dùng `-amd` cho nhu cầu đó. |
| Đổi thứ tự `<modules>` không sửa compile failure. | Thiếu dependency declaration hoặc version mismatch. | Sửa POM module, Maven tự sắp topo. |
| `-DskipTests` vẫn build upstream modules. | Skip tests khác chọn projects. | Dùng đúng `-pl`/`-am`; không nhầm skip tests với skip modules. |
| `mvn -pl :cli -am test` không tạo JAR. | Phase `test` chưa đến `package`. | Dùng `package` nếu cần archive. |
| `mvn -pl :cli -am package` không thấy artifact trong `~/.m2`. | `package` không thực thi `install`. | Dùng `install` khi cần cài local artifacts. |
| `java -jar cli-...jar` fail dù build thành công. | JAR chưa có Main-Class và chưa gộp dependencies. | Dùng `java -cp` như bài hoặc cấu hình archive/launcher. |
| `-am` không lấy dependency ngoài Maven Central. | External dependency không có source project trong Reactor. | Kiểm tra repository/settings/network. |
| Module phụ thuộc một version khác source. | GAV mismatch; Reactor project không đáp ứng dependency đó. | Thống nhất version/dependencyManagement. |
| Build nhanh ở máy dev, fail trên clean CI. | Local repository có cache SNAPSHOT cũ. | Chạy selective reactor `-am` và test trên môi trường sạch. |
| `-T 4` không nhanh hơn với 3 modules phụ thuộc nối tiếp. | Graph gần như hoàn toàn tuần tự. | Giảm threads hoặc chỉ song song các nhánh độc lập. |
| `-rf` thất bại do thiếu dependency khi resume. | Resume không tạo lại đủ upstream artifacts. | Chạy lại `-pl :target -am` hoặc chuẩn bị prerequisites đúng cách. |
| Module upstream test FAIL làm CLI không được build. | Lifecycle test của upstream đã được chọn theo `-am`. | Sửa test hoặc chọn quy trình/phase phù hợp; không che lỗi. |
| Project chỉ khai báo `dependencyManagement` mà không có dependency thật. | Management không tạo classpath edge. | Khai báo `<dependency>` trong module cần dùng. |
| Build với `-N` không thấy sibling modules. | Non-recursive tắt Reactor recursion. | Bỏ `-N` để `-am` có tập modules phù hợp. |

## 22. Checklist sử dụng `-am` đúng cách

Trước khi chạy build chọn lọc:

- [ ] Đang đứng ở root aggregator hoặc dùng `-f` trỏ đúng root POM.
- [ ] `<modules>` chứa các upstream projects cần thiết trong Reactor đang active.
- [ ] Đã xác định target bằng path, `:artifactId` hoặc `groupId:artifactId` không mơ hồ.
- [ ] Đã dùng `-pl` để chọn target rõ ràng.
- [ ] Đã dùng `-am` nếu cần source của các prerequisite reactor modules.
- [ ] Đã phân biệt `-am` (upstream) với `-amd` (downstream dependents).
- [ ] Dependencies trong từng module được khai báo thật và version khớp với Reactor.
- [ ] Không nghĩ `dependencyManagement`/`pluginManagement` tự tạo module dependency.
- [ ] Đã chọn đúng lifecycle phase: `test`, `package`, `verify` hay `install`.
- [ ] Nếu cần test upstream, không skip tests một cách vô ý.
- [ ] Đã xem Reactor Build Order và Reactor Summary cho **lần chạy hiện tại**.
- [ ] Không dùng file `target` cũ ở module không chọn để suy đoán tập projects.
- [ ] Đã kiểm tra external dependency resolution riêng với Reactor module resolution.
- [ ] Nếu dùng CI, có ghi JDK/Maven versions, build command và thông tin commit.

### Lệnh ngắn thường dùng

~~~bash
# Build cli và các đầu vào trong Reactor
mvn -pl :cli -am clean package

# Chạy test của cli cùng upstream modules
mvn -pl :cli -am clean test

# Chạy kiểm chứng tới verify
mvn -pl :cli -am clean verify

# Cài artifacts của cli và upstream vào local repository
mvn -pl :cli -am clean install

# Build service cùng foundation, không cần cli
mvn -pl :service -am package

# Từ foundation, build cả modules phụ thuộc vào foundation
mvn -pl :foundation -amd verify

# Chọn hai mục tiêu, cộng upstream cho cả hai
mvn -pl :cli,:tools -am package

# Khi đang đứng trong thư mục cli, chỉ rõ root aggregator
mvn -f ../pom.xml -pl :cli -am clean package
~~~

Các lệnh đều giả định project demo tồn tại, chạy từ root trừ lệnh cuối và Maven 3 tương thích. Phải điều chỉnh selectors theo POM project thật.

## 23. Bài tập thực hành có đáp án

### Bài A — Dự đoán Reactor project set

Với đồ thị:

~~~text
foundation -> service -> cli
tools (độc lập)
~~~

hãy dự đoán modules JAR được chọn bởi:

1. `mvn -pl :cli package`
2. `mvn -pl :cli -am package`
3. `mvn -pl :service -am package`
4. `mvn -pl :foundation -am package`
5. `mvn -pl :foundation -amd package`
6. `mvn -pl :cli,:tools -am package`

**Đáp án:**

| Lệnh | Các modules JAR |
| --- | --- |
| (1) | `cli` |
| (2) | `foundation`, `service`, `cli` |
| (3) | `foundation`, `service` |
| (4) | `foundation` |
| (5) | `foundation`, `service`, `cli` |
| (6) | `foundation`, `service`, `cli`, `tools` |

Root parent POM có thể tham gia theo quan hệ parent trong Reactor; bảng tập trung vào modules tạo JAR. Khi làm project thật, đối chiếu Reactor Build Order thay vì chỉ tin bảng dự đoán.

### Bài B — Dựng Java 17

1. Tạo đầy đủ root POM và bốn module POM ở mục 6.
2. Tạo các class `MessageSource`, `GreetingService`, `Main` và `ToolsMain`.
3. Tạo `MessageSourceTest` trong `foundation`.
4. Chạy `mvn clean package`, quan sát toàn bộ modules.
5. Chạy `mvn -pl :cli -am clean package`, xác nhận `tools` không xuất hiện trong Reactor summary.
6. Chạy Java từ `target/classes` theo lệnh Bash/PowerShell ở mục 10 và đối chiếu stdout `Hello Maven from foundation via service`.
7. Chạy `mvn -pl :service -am clean package`, xác nhận `cli` không được build.
8. Chạy `mvn -pl :foundation -amd clean package`, ghi danh sách dependents.
9. Chạy `mvn -pl :cli -am clean test`, xác nhận test ở `foundation` vẫn chạy.
10. Giải thích sự khác biệt giữa `mvn ... package` và `mvn ... install`.

### Bài C — Lỗi do cache cũ

Một người thay đổi `GreetingService.greet` nhưng chỉ build:

~~~bash
mvn -pl :cli package
~~~

Lệnh PASS nhưng CLI vẫn hiển thị thông điệp cũ. Hãy:

1. Xem log để xác định `service` có được build trong invocation đó không.
2. Kiểm tra dependency version và local repository có JAR cũ không.
3. Chạy `mvn -pl :cli -am clean package`.
4. Dùng `java -cp` với classes output mới của các modules để kiểm chứng.
5. Giải thích vì sao `-am` thường đáng tin hơn việc chạy `mvn install` thủ công riêng cho nhiều module mà không biết thứ tự.

### Bài D — Chọn chiến lược CI

Nhóm A muốn build một ứng dụng `cli` cùng thư viện nguồn; nhóm B sửa `foundation` và muốn kiểm tra modules tiêu thụ; nhóm C chỉ muốn biên dịch `tools`. Chọn:

- `-pl :cli -am` cho A.
- `-pl :foundation -amd` cho B, rồi kiểm tra đầy đủ prerequisite/repository theo reactor graph thực.
- `-pl :tools` cho C; thêm `-am` nếu tools có upstream reactor dependencies trong project thật.

### Câu hỏi tự đánh giá

- Vì sao `-pl :cli package` có thể PASS dù source `service` chưa được build?
- `-am` có tự lấy Java source của dependency bên ngoài Reactor từ Maven Central không?
- `-pl cli` khác `-pl :cli` thế nào?
- `-am` dựa vào graph dependencies hay thứ tự `<modules>`?
- `dependencyManagement` có tự tạo dependency edge không?
- Khi thêm `-am`, upstream tests có thể chạy trong phase `verify` không?
- Nếu chỉ cần artifact build trong `target`, có bắt buộc chạy `install` không?
- Vì sao `-T 4` không có ích nhiều cho chuỗi modules tuyến tính?
- `-amd` phục vụ nhu cầu nào khác `-am`?
- Khi đang trong nested module, nên chọn root POM bằng tùy chọn gì?
- Vì sao không có `tools` trong Reactor summary không đồng nghĩa `tools/target` chắc chắn không tồn tại?

## 24. Tổng kết

**`-am` / `--also-make` là công cụ build những modules đầu vào của các projects được chọn bằng `-pl` trong cùng Maven Reactor.** Nó giúp chọn build một mục tiêu mà không bỏ sót các prerequisites và không vô tình dùng binary SNAPSHOT cũ đã cài trước đó.

Ghi nhớ:

~~~text
mvn -pl :cli -am clean package

                 chọn cli
                     │
                     ▼
    tìm các prerequisite modules trong Reactor
                     │
                     ▼
       foundation -> service -> cli
                     │
                     ▼
     build theo dependency order, không có tools
~~~

Ngược lại, `-amd` chọn các projects **phụ thuộc vào** mục tiêu. `-am` không tự thêm external source dependencies, không tự thay `package` thành `install`, không sửa sai version hoặc thiếu dependency declaration. Cách dùng bền vững là **đúng aggregator, đúng dependency graph, đúng selector, đúng phase và kiểm tra Reactor summary**.

## Tài liệu chính thức

- Apache Maven 3 — Guide to Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Maven CLI Options Reference (`-pl`, `-am`, `-amd`): https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Introduction to Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Surefire Plugin — JUnit Platform Examples: https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html
