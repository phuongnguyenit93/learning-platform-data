# Tổ chức parent và aggregator cùng chỗ hoặc tách riêng trong Maven reactor nhiều mô-đun

## 1. Hai vai trò thường nằm cùng một pom.xml nhưng không phải một

Khi làm dự án Maven nhiều mô-đun (*multi-module project*), có hai trách nhiệm độc lập:

- **Parent POM**: là POM được một project khác **khai báo trong `<parent>`** để kế thừa thông tin hoặc cấu hình build chung, ví dụ `groupId`, `version`, `properties`, `dependencyManagement` và `pluginManagement`.
- **Aggregator POM**: là POM có `<modules>` để Maven **thu thập các project con vào cùng một reactor**, sắp thứ tự build theo quan hệ thực tế và thực thi các phase/goals được yêu cầu.

Một `pom.xml` có thể đóng **cả hai vai trò**:

~~~text
root/pom.xml              <- parent + aggregator
    |
    +-- greeting-core/pom.xml  <- <parent> trỏ về root
    |
    +-- greeting-cli/pom.xml   <- <parent> trỏ về root
~~~

Cũng có thể **tách hai vai trò**:

~~~text
root/pom.xml                       <- aggregator, có <modules>
    |
    +-- build-parent/pom.xml        <- parent, không cần <modules>
    +-- greeting-core/pom.xml      <- kế thừa build-parent
    +-- greeting-cli/pom.xml       <- kế thừa build-parent
~~~

Trong cấu trúc thứ hai, aggregator có thể gom các project **không kế thừa chính nó**. Parent POM lại có thể được nhiều project kế thừa mà **không chứa một danh sách `<modules>` nào**.

**Kết luận cần nhớ:**

> **`<parent>` trả lời “project này kế thừa cấu hình từ đâu?”, còn `<modules>` trả lời “Maven chạy từ đây phải gom những project nào vào reactor?”. Hai mối quan hệ không tự thay thế cho nhau.**

Bài viết hướng dẫn chọn mô hình cùng chỗ hoặc tách riêng, cách viết đúng `relativePath`, phiên bản, management, lệnh reactor và ví dụ Java 17 có thể tự build trong Maven 3.9.x.

## 2. Bảng so sánh hai quan hệ

| Câu hỏi | Inheritance qua parent | Aggregation qua reactor |
| --- | --- | --- |
| Ai khai báo quan hệ? | **Project con** ghi `<parent>`. | **Aggregator** ghi `<modules>`. |
| POM biết được gì? | Parent có tọa độ `groupId:artifactId:version` và file path/repository resolution. | Danh sách các đường dẫn tương đối tới project modules. |
| Vai trò chính | Kế thừa cấu hình, quản lý version và plugin policies. | Thu thập nhiều project, chọn tập build, sắp build order. |
| Có cần `packaging=pom`? | Parent dùng làm parent POM phải có packaging `pom`. | Aggregator dùng `<modules>` thông thường cũng có packaging `pom`. |
| Có tự thêm thư viện vào classpath không? | Không chỉ vì có `<parent>`; dependency phải khai báo hoặc được kế thừa thực sự qua `dependencies`. | Không; `<modules>` không tạo Maven `<dependency>`. |
| Có tự kích hoạt plugin goal? | `pluginManagement` không tự kích hoạt goal mới chỉ vì được kế thừa. | `<modules>` không tự tạo plugin execution nào. |
| Có yêu cầu parent là aggregator? | Không. | Không yêu cầu các project được gom kế thừa aggregator. |
| Tác động khi chạy từ root | Parent model được dùng cho child có `<parent>` phù hợp. | Reactor build những modules mà aggregator tập hợp/chọn. |
| Có quyết định thứ tự build bằng `dependencyManagement` không? | Không. | Reactor sắp theo **quan hệ instantiated** như project dependencies, rồi mới xét thứ tự khai báo nếu chưa có quy tắc khác. |

**Một chú ý:** `parent` trong POM là quan hệ mô hình build, không phải Java inheritance hay Java package. Maven modules cũng không phải JPMS modules (`module-info.java`); bài tập này không dùng JPMS.

Nguồn chính thức: *Apache Maven — Introduction to the POM* và *Guide to Working with Multiple Modules*.

## 3. Maven mô hình hóa parent như thế nào?

Một child project khai báo:

~~~xml
<parent>
    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-root</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>

<artifactId>greeting-core</artifactId>
~~~

Đây là **mảnh child POM**, chưa phải POM đầy đủ. Maven tìm đúng parent POM theo coordinates được khai báo và cách cấu hình `relativePath`/repository.

Nếu child không ghi riêng `groupId` hoặc `version`, Maven có thể **kế thừa** hai giá trị đó từ parent, nhưng **`artifactId` không được kế thừa** vì mỗi project cần artifactId của chính nó.

Những thứ thường được kế thừa hoặc merge theo Maven model:

- `groupId`, `version` nếu child không tự đặt.
- `properties` chung, ví dụ `maven.compiler.release=17`.
- `dependencyManagement` để quản lý version/scopes/exclusions khi dependency được khai báo.
- `pluginManagement` để quản lý version/config mặc định cho plugins được sử dụng.
- `dependencies` và `build/plugins` nếu parent cố ý khai báo ở vị trí đó; các quy tắc merge/inherited cần được hiểu rõ.
- Thông tin về tổ chức/repositories/reporting và một số metadata khác theo POM inheritance rules.

Những điểm **không được hiểu nhầm**:

- `<modules>` không phải danh sách tự động được child “kế thừa để chạy module khác”.
- `<artifactId>` của parent không trở thành artifactId của child.
- `profiles` trong POM không được copy nguyên như những profiles độc lập của child; **tác dụng của active profiles ở parent** có thể tham gia effective model tùy trường hợp.
- Parent có `<dependencyManagement>` không làm child **tự có dependency**; child vẫn phải khai báo dependency thực tế.
- Parent `<pluginManagement>` không tự tạo execution mới ở child nếu plugin không được tham chiếu/bind phù hợp.

Bởi vậy, muốn biết **child thực sự nhận gì**, dùng **effective POM** của đúng child thay vì chỉ nhìn parent POM.

## 4. Aggregator làm gì khi có <modules>?

Một aggregator đơn giản:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-reactor</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>greeting-core</module>
        <module>greeting-cli</module>
    </modules>
</project>
~~~

Mỗi `<module>` là **đường dẫn tương đối tính từ thư mục chứa aggregator POM**, không phải bắt buộc là Maven artifactId hoặc Java package.

Maven reactor thực hiện ba công việc chính:

1. Thu thập những Maven projects được aggregator khai báo, gồm các aggregator lồng nhau khi có.
2. Phân tích các quan hệ **thực sự được khai báo** giữa những projects để xác định build order hợp lệ.
3. Build/chạy goals cho tập projects được chọn, theo dependency order hoặc các quan hệ khác mà reactor hỗ trợ.

Nếu `greeting-cli` có dependency tới `greeting-core`, Maven thường build core trước CLI **dù thứ tự hai `<module>` viết ngược**. Đây là nhờ **project dependency**, không phải nhờ child đã kế thừa cùng parent.

Theo hướng dẫn Maven 3 chính thức, reactor còn xét một số loại quan hệ instantiated khác như **plugin declaration**, **plugin dependency** và **build extension declaration** đối với project trong reactor. `dependencyManagement` và `pluginManagement` **không tạo quan hệ reactor sort** chỉ vì có mục được quản lý.

## 5. Khi nào chọn parent + aggregator chung một chỗ?

Mô hình chung thích hợp khi:

- Monorepo nhỏ hoặc trung bình với những child projects thuộc cùng một sản phẩm.
- Các modules **cùng chia sẻ vòng đời phát hành/version** và phần lớn cùng build policies.
- Các child thực sự muốn kế thừa chung Java release, plugin versions, encoding, test dependencies versions...
- Một lệnh ở root nên build toàn bộ các project.
- Nhóm muốn onboarding đơn giản: **một root `pom.xml`** vừa giải thích modules vừa chứa cấu hình chung.

Ví dụ:

~~~text
greeting-combined/
├── pom.xml              <- parent + aggregator
├── greeting-core/
│   ├── pom.xml           <- inherits ../pom.xml
│   └── src/
└── greeting-cli/
    ├── pom.xml           <- inherits ../pom.xml
    └── src/
~~~

Lợi ích:

1. Ít POM files hơn, ít nơi phải xem.
2. Child dùng `<relativePath>../pom.xml</relativePath>` tự nhiên.
3. Một thay đổi plugin policy có thể áp dụng nhất quán cho mọi child.
4. Reactor root rất dễ chạy: `mvn clean verify`.
5. Version chung thường dễ quản lý trong cùng một repository.

Giới hạn:

- Parent dễ phình to và chứa nhiều cấu hình không còn phù hợp với mọi child.
- Nếu một library trong repository khác chỉ cần kế thừa build policies, kéo theo parent POM của một reactor sản phẩm cụ thể có thể gây **coupling** không cần thiết.
- Parent POM publish cho các consumer bên ngoài có thể mang `<modules>` tham chiếu tới source tree không tồn tại ở consumer; điều này không tự làm artifact dependency fail, nhưng khó tổ chức vòng đời và quản trị release nếu dùng chung cho nhiều repository độc lập.
- Các build plugins đặt trực tiếp trong `build/plugins` có thể chạy/được kế thừa rộng hơn mong muốn.

**Tiêu chí thực tế:** nếu cùng đội sở hữu, cùng release cadence và modules nhất quán, mô hình chung thường là lựa chọn đơn giản và minh bạch.

## 6. Ví dụ A: parent và aggregator dùng chung root POM

### 6.1. Cấu trúc file đầy đủ

Tạo project:

~~~text
greeting-combined/
├── pom.xml
├── greeting-core/
│   ├── pom.xml
│   ├── src/main/java/org/example/reactor/core/GreetingFormatter.java
│   └── src/test/java/org/example/reactor/core/GreetingFormatterTest.java
└── greeting-cli/
    ├── pom.xml
    └── src/main/java/org/example/reactor/cli/Main.java
~~~

Ví dụ dùng **Java 17+, Maven 3.9.x**, JUnit Jupiter 5.11.4, Maven Compiler Plugin 3.13.0 và Maven Surefire Plugin 3.5.2. Plugin versions là **ví dụ được pin**, không mặc định là bản production mới nhất.

Ta cố tình có dependency **CLI → core** để người học quan sát Maven reactor sort. Không cần thêm external runtime library; khi chạy Java ta sẽ truyền hai JAR lên classpath.

### 6.2. greeting-combined/pom.xml — root vừa parent vừa aggregator

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-root</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <!-- The dependency graph, not this list's order, places core first. -->
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
                <groupId>org.example.reactor</groupId>
                <artifactId>greeting-core</artifactId>
                <version>1.0.0</version>
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

**Đây là POM độc lập và hợp lệ** với packaging `pom`.

- Root có `<modules>` nên là **aggregator**.
- Hai child sẽ dùng `<parent>...greeting-root...</parent>` nên root cũng là **parent**.
- `dependencyManagement` quản lý version của `greeting-core` và JUnit, **không tự thêm chúng làm project dependencies** ở hai child.
- `pluginManagement` quản lý compiler/surefire/jar versions khi các plugins được lifecycle sử dụng. Nó **không tự bind một custom goal mới** chỉ vì có entry trong management.
- `packaging=pom` có nghĩa root **không tự tạo greeting-root-1.0.0.jar**; nhiệm vụ của root là cấu hình và điều phối.
- Ta viết `greeting-cli` trước `greeting-core` trong modules để kiểm tra giả định sai “build theo thứ tự khai báo”; reactor vẫn cần tôn trọng `greeting-cli` phụ thuộc core.

### 6.3. greeting-core/pom.xml — child kế thừa root

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.reactor</groupId>
        <artifactId>greeting-root</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-core</artifactId>
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

Ở child này:

- `groupId` và `version` được kế thừa từ root.
- `artifactId=greeting-core` là định danh riêng, không kế thừa.
- Dependency JUnit có **scope=test**, version bị lược bỏ vì parent `dependencyManagement` đã quản lý `5.11.4`.
- Packaging JAR có nghĩa `greeting-core` tạo library JAR.
- Child không cần tự khai báo compiler plugin version; cấu hình của parent và lifecycle mapping áp dụng theo effective POM.

**Chú ý về test dependencies:** nếu chỉ đặt JUnit trong parent `dependencyManagement` mà không có `<dependency>` ở core như trên, compiler của test **không tự nhìn thấy** JUnit.

### 6.4. greeting-cli/pom.xml — child phụ thuộc core

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.reactor</groupId>
        <artifactId>greeting-root</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example.reactor</groupId>
            <artifactId>greeting-core</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Đây là **đường phụ thuộc Maven thực sự**: từ `greeting-cli` tới `greeting-core`. Parent quản lý version nên child không phải lặp lại `1.0.0` trong dependency.

Nếu xóa block `<dependencies>` này, việc hai modules cùng được aggregator liệt kê **không tạo ra compile dependency**. `Main.java` có import từ core sẽ không compile trong setup chuẩn.

### 6.5. Source Java 17: GreetingFormatter.java

Đường dẫn `greeting-core/src/main/java/org/example/reactor/core/GreetingFormatter.java`:

~~~java
package org.example.reactor.core;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String rawName) {
        String name = rawName.strip();
        if (name.isEmpty()) {
            name = "guest";
        }
        return "Hello, " + name + "!";
    }
}
~~~

Mã không cần third-party library. `String.strip()` có trong JDK 11+, và Java 17 hỗ trợ. Khi gọi `greet(" Maven ")`, kết quả là `"Hello, Maven!"`. `greet("   ")` trả `"Hello, guest!"`. Ví dụ giả định `rawName` khác null; null không được xử lý chủ đích trong API đơn giản này.

### 6.6. Source test: GreetingFormatterTest.java

Đường dẫn `greeting-core/src/test/java/org/example/reactor/core/GreetingFormatterTest.java`:

~~~java
package org.example.reactor.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingFormatterTest {
    @Test
    void trimsNameAndHandlesBlankString() {
        assertEquals("Hello, Maven!", GreetingFormatter.greet(" Maven "));
        assertEquals("Hello, guest!", GreetingFormatter.greet("   "));
    }
}
~~~

Đây là **một JUnit Jupiter test method** gồm hai assertions. `GreetingFormatterTest` khớp quy tắc Surefire `*Test`. JUnit Jupiter cho phép class và test method package-private.

Với core test này, khi reactor chạy phase `test`, unit test có thể được Surefire chọn và chạy. Không gọi code ở đây là integration test chỉ vì build có nhiều Maven modules; đây vẫn là một test logic nhỏ, cô lập.

### 6.7. Source app: Main.java

Đường dẫn `greeting-cli/src/main/java/org/example/reactor/cli/Main.java`:

~~~java
package org.example.reactor.cli;

import org.example.reactor.core.GreetingFormatter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("message=" + GreetingFormatter.greet(" Maven "));
    }
}
~~~

Mã import `GreetingFormatter` từ core JAR. Quan hệ này yêu cầu dependency trong `greeting-cli/pom.xml` và khiến reactor cần build core trước CLI.

## 7. Build và chạy ví dụ A: kết quả kiểm chứng được

Từ thư mục `greeting-combined/`:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu Maven/JDK tương thích và có thể resolve plugins/JUnit, reactor sẽ thu thập root + 2 child projects. Theo quan hệ `greeting-cli -> greeting-core`, core cần được build trước CLI dù root `<modules>` liệt kê CLI trước.

Những kết quả trọng tâm sau build:

~~~text
greeting-core/target/greeting-core-1.0.0.jar
greeting-cli/target/greeting-cli-1.0.0.jar
greeting-core/target/surefire-reports/
~~~

Đây là **cây rút gọn**, không phải toàn bộ `target/` hay log Maven. Test class `GreetingFormatterTest` chứa **một test method**. CLI chưa cấu hình `Main-Class` trong manifest và JAR CLI cũng không đóng gói core dependency vào chính nó. Vì vậy đừng kỳ vọng `java -jar greeting-cli/target/greeting-cli-1.0.0.jar` hoạt động ngay.

Chạy trên Linux/macOS từ root:

~~~bash
java -cp "greeting-cli/target/greeting-cli-1.0.0.jar:greeting-core/target/greeting-core-1.0.0.jar" org.example.reactor.cli.Main
~~~

**Stdout chính xác của riêng lệnh `java`:**

~~~text
message=Hello, Maven!
~~~

Trên Windows PowerShell/CMD, phân cách classpath bằng dấu `;`:

~~~powershell
java -cp "greeting-cli\target\greeting-cli-1.0.0.jar;greeting-core\target\greeting-core-1.0.0.jar" org.example.reactor.cli.Main
~~~

**Kết quả Java giống hệt.** Tên hai JAR theo artifactId/version vì ta không tùy chỉnh `build.finalName`. Nếu sử dụng `java -cp` với chỉ CLI JAR và bỏ core JAR, ứng dụng có thể lỗi `NoClassDefFoundError` khi tải `GreetingFormatter`; reactor build đúng không có nghĩa lệnh Java tự tìm mọi Maven dependency.

## 8. Các lệnh reactor quan trọng trong mô hình chung

Thực hiện tại **root aggregator** `greeting-combined/`:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp -pl :greeting-cli -am package
mvn -B -ntp -pl :greeting-core test
mvn -B -ntp -N validate
~~~

Giải thích:

- `clean verify`: build toàn bộ modules được reactor thu thập đến `verify`.
- `-pl :greeting-cli`: chọn Maven project có artifactId `greeting-cli` trong reactor.
- `-am` hoặc `--also-make`: chọn thêm các reactor project dependencies cần thiết, trong đó có `greeting-core`. Không có `-am`, CLI có thể cần artifact core đã được install sẵn hoặc được resolve từ repository.
- `-pl :greeting-core`: chọn riêng core project. Các goals như `test` chỉ chạy ở những projects thực sự được chọn.
- `-N` hoặc `--non-recursive`: chỉ xử lý POM hiện tại, không đệ quy modules. Với root packaging `pom`, lệnh `-N validate` không đồng nghĩa compile cả hai JARs.

**Tại sao cần chạy từ đúng chỗ?** Nếu cd vào `greeting-cli/` rồi chạy `mvn package`, Maven có thể đọc child POM và parent ở `../pom.xml`, nhưng **không tự lập toàn bộ reactor từ parent aggregator** chỉ vì child có `<parent>`. Nếu core dependency chưa ở local/remote repository, build child cô lập có thể fail. Hãy chạy từ aggregator root với `-pl :greeting-cli -am` hoặc install/deploy core artifact đúng cách.

## 9. Khi nào nên tách parent ra khỏi aggregator?

Mô hình tách riêng phù hợp khi:

1. Một **build parent** cần được nhiều repository/product sử dụng chung, nhưng mỗi sản phẩm có tập modules khác nhau.
2. Repository muốn có **root aggregator nhẹ** chỉ mô tả sản phẩm nào được build, tránh ghép chính sách công cụ vào điều phối reactor.
3. Những modules cùng có cấu hình build chung nhưng không nhất thiết được build chung trong mọi công việc.
4. Tổ chức muốn phát hành **build-parent POM** theo release lifecycle riêng với từng sản phẩm ứng dụng.
5. CI cần thay đổi thành phần reactor (module selection/profiles) độc lập với parent POM được version/pin rõ.
6. Có nhiều product roots cùng áp dụng một parent tổ chức, nhưng không muốn parent phải biết đường dẫn của tất cả projects ở mọi repository.

Cấu trúc tách trong **cùng repository**:

~~~text
greeting-split/
├── pom.xml                <- chỉ aggregator
├── build-parent/
│   └── pom.xml            <- chỉ parent
├── greeting-core/
│   └── pom.xml            <- parent: ../build-parent/pom.xml
└── greeting-cli/
    └── pom.xml            <- parent: ../build-parent/pom.xml
~~~

Cấu trúc này có **bốn POMs** thay vì ba POMs của ví dụ A. Đổi lại, vai trò rõ ràng, và `build-parent` có thể được quản lý/phát hành như một artifact POM độc lập.

**Không cần tách nếu không có nhu cầu thật.** Tách chỉ để “đẹp về lý thuyết” có thể làm người mới phải theo dõi thêm file và publication order mà chưa tạo thêm lợi ích.

## 10. Ví dụ B: root aggregator tách khỏi build-parent POM

Để so sánh công bằng, dùng **chính ba Java source files ở mục 6.5–6.7**, cùng package/class/methods, và chỉ thay Maven POMs.

Cấu trúc đầy đủ:

~~~text
greeting-split/
├── pom.xml
├── build-parent/
│   └── pom.xml
├── greeting-core/
│   ├── pom.xml
│   ├── src/main/java/org/example/reactor/core/GreetingFormatter.java
│   └── src/test/java/org/example/reactor/core/GreetingFormatterTest.java
└── greeting-cli/
    ├── pom.xml
    └── src/main/java/org/example/reactor/cli/Main.java
~~~

**Không trộn POM của ví dụ A và ví dụ B trong cùng một root.** Đây là **hai layout thay thế**, không phải hai hệ thống cần chạy cùng lúc. Các tệp Java được copy đúng nguyên văn từ A sang B để kiểm thử sự khác biệt cấu trúc POM.

### 10.1. greeting-split/pom.xml — root chỉ aggregate

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-reactor</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>build-parent</module>
        <module>greeting-cli</module>
        <module>greeting-core</module>
    </modules>
</project>
~~~

Root có `<modules>` nên là **aggregator**, nhưng child `greeting-core` và `greeting-cli` **không khai báo root này làm parent**. Root không chứa `dependencyManagement` hoặc `pluginManagement` trong ví dụ; những cấu hình ấy thuộc `build-parent`.

Hệ quả:

- Chạy `mvn clean verify` từ root sẽ thu thập những project liệt kê.
- Root `greeting-reactor` **không trở thành groupId/artifactId/version parent của children** chỉ vì có `<modules>`.
- Root không tự chia sẻ `properties` với children qua aggregation.
- `<module>build-parent</module>` làm parent POM **có mặt trong tập project của reactor** khi chạy từ root. Điều này hữu ích cho một build/release chung, nhưng **không phải điều kiện bắt buộc để một parent được kế thừa** khi nó đã resolve được qua file path/repository.

Ta vẫn liệt kê CLI trước core để thấy **quan hệ project dependency** quyết định thứ tự hai JAR.

### 10.2. greeting-split/build-parent/pom.xml — parent không aggregate

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-build-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.example.reactor</groupId>
                <artifactId>greeting-core</artifactId>
                <version>1.0.0</version>
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

Parent này **không có `<modules>`**: nó là một POM dùng làm **nguồn cấu hình**, không phải lệnh điều phối toàn bộ project con. Các child chỉ thừa kế nó nếu `<parent>` trỏ đúng coordinates.

Khi xuất bản/reuse trong repository khác, parent này có ý nghĩa độc lập với cấu trúc thư mục của một sản phẩm nhất định.

**Điểm thiết kế:** Do `build-parent` không khai báo application dependencies trong `build/dependencies`, nó không kéo một library vào mọi child chỉ vì được kế thừa. Nó chỉ quản lý phiên bản. Đây là điểm tốt để chia sẻ build policy mà không vô tình thay dependency graph từng ứng dụng.

### 10.3. greeting-split/greeting-core/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.reactor</groupId>
        <artifactId>greeting-build-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../build-parent/pom.xml</relativePath>
    </parent>

    <artifactId>greeting-core</artifactId>
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

Khác ví dụ A, child **không trỏ `../pom.xml`**. Từ `greeting-core/` muốn tìm `greeting-split/build-parent/pom.xml` thì đường đúng là `../build-parent/pom.xml`.

Maven kiểm tra POM ở path tương đối và coordinates dự kiến. Nếu `relativePath` trỏ root aggregator (artifactId `greeting-reactor`) trong khi `<parent>` cần `greeting-build-parent`, Maven có thể báo **parent.relativePath points at wrong local POM** hoặc không thể resolve parent.

Không sửa bằng cách ép artifactId của aggregator và parent giống nhau; hãy sửa đúng đường dẫn và coordinates.

### 10.4. greeting-split/greeting-cli/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.reactor</groupId>
        <artifactId>greeting-build-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../build-parent/pom.xml</relativePath>
    </parent>

    <artifactId>greeting-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example.reactor</groupId>
            <artifactId>greeting-core</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Ở đây, `greeting-cli` vừa:

- **Kế thừa** cấu hình từ `greeting-build-parent`.
- **Phụ thuộc** artifact `greeting-core` qua Maven project dependency.
- **Được aggregator** `greeting-reactor` đưa vào reactor khi build từ root.

Đó là **ba quan hệ độc lập**. Parent inheritance không thay Maven dependency, và aggregator membership không thay Maven dependency. `<modules>` có thể liệt kê CLI trước core, nhưng Maven phải tôn trọng quan hệ CLI cần core khi build.

## 11. Build và chạy ví dụ B

Tại root `greeting-split/`:

~~~bash
mvn -B -ntp clean verify
~~~

Maven thu thập:

~~~text
org.example.reactor:greeting-reactor:1.0.0       packaging pom
org.example.reactor:greeting-build-parent:1.0.0  packaging pom
org.example.reactor:greeting-core:1.0.0          packaging jar
org.example.reactor:greeting-cli:1.0.0           packaging jar
~~~

Đây là danh sách **những project dự kiến được collect**, không phải thứ tự/log nguyên văn. Parent và aggregator đều packaging POM, **không tạo JAR riêng**; hai child đóng gói main JAR. Maven cần core trước CLI do dependency thực sự của CLI.

Chạy cùng chương trình Java với classpath tương tự ví dụ A:

~~~bash
java -cp "greeting-cli/target/greeting-cli-1.0.0.jar:greeting-core/target/greeting-core-1.0.0.jar" org.example.reactor.cli.Main
~~~

**Stdout chính xác của riêng lệnh Java:**

~~~text
message=Hello, Maven!
~~~

Trên Windows:

~~~powershell
java -cp "greeting-cli\target\greeting-cli-1.0.0.jar;greeting-core\target\greeting-core-1.0.0.jar" org.example.reactor.cli.Main
~~~

Kết quả giống hệt. Các file Java của ví dụ B **đúng nguyên văn** như mục 6.5–6.7, vì bài đang so sánh **cách tổ chức parent và aggregator**, không đổi behavior của app.

Nếu bạn chạy:

~~~bash
mvn -B -ntp -f build-parent/pom.xml clean verify
~~~

thì Maven chỉ thấy `build-parent` POM **không chứa `<modules>`**. Lệnh này **không phải build toàn bộ greeting-core/CLI**. Muốn build toàn reactor, chạy tại root aggregator `greeting-split/pom.xml`.

## 12. relativePath trong hai mô hình: lỗi rất hay gặp

### 12.1. Mặc định của relativePath

Với Maven 3, nếu không khai báo `<relativePath>`, giá trị mặc định của `<parent>` thường là:

~~~xml
<relativePath>../pom.xml</relativePath>
~~~

Maven có thể thử parent POM theo đường đó trước, đồng thời kiểm tọa độ tương ứng. Nếu không tìm đúng local parent, Maven cần resolve parent từ repository theo cơ chế thích hợp.

Điều này phù hợp với **mô hình A**, nơi parent ở thư mục ngay phía trên child:

~~~text
greeting-combined/pom.xml
greeting-combined/greeting-core/pom.xml
~~~

Nhưng với **mô hình B**, parent ở thư mục sibling:

~~~text
greeting-split/build-parent/pom.xml
greeting-split/greeting-core/pom.xml
~~~

nên phải khai báo rõ:

~~~xml
<relativePath>../build-parent/pom.xml</relativePath>
~~~

### 12.2. relativePath không phải module path

Trong aggregator:

~~~xml
<module>greeting-core</module>
~~~

đường dẫn được hiểu **từ aggregator POM** đến project core.

Trong child:

~~~xml
<relativePath>../build-parent/pom.xml</relativePath>
~~~

đường dẫn được hiểu **từ child project** tới POM của parent.

Hai path có hướng **ngược nhau**. Vì vậy không thể dùng `relativePath` để “thêm module” hoặc dùng `<modules>` để “khai báo parent”.

### 12.3. Khi parent được phân phối qua repository

Với một shared corporate parent đã publish lên Maven repository, có thể có:

~~~xml
<parent>
    <groupId>org.example.build</groupId>
    <artifactId>company-build-parent</artifactId>
    <version>3.2.0</version>
    <relativePath/>
</parent>
~~~

**Đây là mảnh minh họa** một parent khác với ví dụ runnable. `<relativePath/>` rỗng ở Maven 3 yêu cầu bỏ cơ chế tìm local parent qua đường mặc định, ưu tiên resolution từ repository. Project phải có parent POM đã install hoặc có thể tải từ remote repository. Không sao chép vào ví dụ B vì ở đó parent **nằm cùng source tree** và chưa nhất thiết được publish.

Tài liệu Maven 4 có thay đổi về cách tìm parent trong tập project đang build; hướng dẫn chính của bài này **dành cho Maven 3**. Khi migration sang Maven 4, xem tài liệu dành riêng cho Maven 4 thay vì suy tất cả chi tiết resolution là giống nhau.

## 13. Những thứ thực sự kế thừa và những thứ không được mặc định kế thừa

| Thành phần | Parent POM quản lý/cho kế thừa? | Aggregator POM chỉ có modules? |
| --- | --- | --- |
| `groupId`, `version` | Có thể được child kế thừa khi child dùng `<parent>`. | Không tự thay groupId/version của module chỉ vì aggregate. |
| `artifactId` | Child phải tự định danh artifactId. | Không ảnh hưởng child artifactId. |
| `properties` (Java release/encoding) | Có thể kế thừa và override có chủ đích. | Không tự đi xuống modules nếu chúng không inherit aggregator. |
| `dependencyManagement` | Child có thể nhận version/scopes/exclusions quản lý. | Không tự áp vào modules không inherit. |
| `dependencies` | Có thể được kế thừa nếu parent đặt dependencies thực tế ở đây. | Không thêm dependency chỉ nhờ liệt kê module. |
| `pluginManagement` | Child có thể kế thừa plugin versions/config defaults. | Không tự điều chỉnh plugin config của modules không inherit. |
| `build/plugins` | Có quy tắc inheritance/merge/executions. | Không tự chạy trên children không inherit. |
| `modules` | Không phải cơ chế inheritance child → parent. | Được Maven đọc để thu thập reactor modules. |
| `repositories`/`pluginRepositories` | Có thể tham gia effective model theo quy tắc Maven. | Không tự cấp cấu hình cho module nếu không được kế thừa. |
| `profiles` | Tác dụng của active profiles từ parent có thể được đưa vào model; profile definitions không đơn giản được copy. | Chỉ profile-defined modules nếu profile phù hợp đang active; không phải inheritance. |

**Một rủi ro thực tế:** nếu root dùng chung vừa parent vừa aggregator, một plugin goal đặt ở `build/plugins` có thể được kế thừa vào mọi child và chạy nhiều lần, thậm chí khi chỉ muốn chạy một lần ở root. Với các goals mang tính aggregator (tạo release report, distribution ZIP, SBOM tổng hợp), phải chọn đúng plugin goal semantics, cấu hình `<inherited>false</inherited>` khi phù hợp, hoặc tách plugin execution sang reactor-only project.

Ngược lại, đặt một plugin chỉ trong `pluginManagement` mà không được gọi/bind cũng không bảo đảm nó thực thi. Hãy dùng `effective-pom` và log thực để xác nhận.

## 14. dependencyManagement khác dependencies, pluginManagement khác plugins

### 14.1. dependencyManagement

Parent chỉ quy định:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.reactor</groupId>
            <artifactId>greeting-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Điều này **không biến mọi child thành consumer của greeting-core**. Chỉ child nào **khai báo `<dependency>` thực sự** như `greeting-cli` mới có relationship CLI → core trong project graph.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.reactor</groupId>
        <artifactId>greeting-core</artifactId>
    </dependency>
</dependencies>
~~~

Phiên bản `1.0.0` được parent management cung cấp cho entry thực tế này.

**Reactor sorting:** Maven chỉ dựa vào `dependencyManagement` để lựa version không được hiểu là một dependency edge. Trong mô hình A và B, quan hệ thực tế nằm ở `greeting-cli/pom.xml`.

### 14.2. pluginManagement

Parent quản lý:

~~~xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
    </plugins>
</pluginManagement>
~~~

Lợi ích là child có thể dùng version/config được quản lý khi Maven lifecycle/plugin declaration áp dụng compiler plugin. Nhưng một custom plugin không thuộc lifecycle mặc định sẽ **không tự chạy execution mới** chỉ vì xuất hiện ở `pluginManagement`. Nếu muốn chạy task thực, phải có plugin execution trong `build/plugins` (hoặc cơ chế lifecycle phù hợp).

**Không đặt mọi plugin trực tiếp vào parent `build/plugins`** chỉ để pin version; hãy phân biệt “quản lý policy” với “buộc execution chạy”. Đặc biệt với aggregator-only tasks, đặt sai cấp inheritance có thể gây build lặp hoặc tạo artifact trùng.

## 15. Reactor sort order: đừng nhầm list order với dependency order

Trong cả hai ví dụ, aggregator liệt kê:

~~~xml
<modules>
    <module>greeting-cli</module>
    <module>greeting-core</module>
</modules>
~~~

Nhưng `greeting-cli/pom.xml` có:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.reactor</groupId>
        <artifactId>greeting-core</artifactId>
    </dependency>
</dependencies>
~~~

Vì thế Maven reactor cần đảm bảo core được build trước CLI để CLI có artifact/classpath đúng.

Apache Maven 3 reactor guide nêu những quan hệ có thể ảnh hưởng tới sorting: **project dependency thực tế**, **plugin declaration tới một reactor module**, **plugin dependency** và **build extension declaration** tới reactor module. Khi không có quan hệ nào áp dụng, thứ tự trong `<modules>` có thể được dùng làm fallback.

**Hai điểm rất quan trọng:**

1. `<dependencyManagement>` chỉ quản lý version, không tạo edge.
2. `<pluginManagement>` cũng không tự tạo edge.

Nếu bỏ dependency CLI → core nhưng giữ core trong `<modules>`, Maven **không tự thêm core vào compiler classpath của CLI**. Kể cả bạn đổi `<modules>` để core được liệt kê trước, CLI vẫn thiếu dependency declaration và có thể compile fail vì `GreetingFormatter` không resolve.

Muốn hiểu reactor build order, xem **Reactor Build Order** trong log và dependency declarations, không suy hoàn toàn từ XML `<modules>`.

## 16. Parent và aggregator có thể không nằm trong cùng thư mục

Chọn một trong các bố cục sau, tùy mục tiêu:

### 16.1. Cùng chỗ, thư mục con trực tiếp

~~~text
project/
  pom.xml                  # parent + aggregator
  module-a/pom.xml
  module-b/pom.xml
~~~

Child dùng `<relativePath>../pom.xml</relativePath>`. Đây là mẫu dễ học nhất.

### 16.2. Parent là thư mục sibling của child, aggregator tại root

~~~text
project/
  pom.xml                  # aggregator only
  build-parent/pom.xml     # parent only
  module-a/pom.xml
  module-b/pom.xml
~~~

Child dùng `<relativePath>../build-parent/pom.xml</relativePath>`, còn aggregator dùng `<module>build-parent</module>`, `<module>module-a</module>`, `<module>module-b</module>`.

### 16.3. Parent ở repository dùng chung, aggregator ở product repo

~~~text
product-repo/
  pom.xml                  # aggregator only
  service/pom.xml          # parent from artifact repository
  cli/pom.xml              # parent from artifact repository
~~~

Các child có parent `org.example.build:company-build-parent:3.2.0` và có thể dùng `<relativePath/>` để buộc repository resolution theo mục đích. Lúc này **không có thư mục build-parent local** cần được aggregator liệt kê.

### 16.4. Aggregator ở thư mục con chứ không ở root

Maven cho phép POM aggregator ở `build/aggregator/pom.xml` và liệt kê các module bằng đường dẫn tương đối thích hợp, chẳng hạn `../../module-a`. Nhưng chọn bố cục lệch root có thể làm lệnh CI và `-f` khó đọc hơn. Không đặt module paths bằng đường dẫn máy tuyệt đối hoặc path chỉ đúng trên laptop một thành viên.

**Nguyên tắc:** `<modules>` tính từ aggregator POM; `<relativePath>` tính từ child POM. Thiết kế source tree trước, rồi điền paths theo đúng hướng.

## 17. Vì sao parent POM vẫn cần được resolve khi build child độc lập?

Khi Maven đọc child POM có:

~~~xml
<parent>
    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-build-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../build-parent/pom.xml</relativePath>
</parent>
~~~

Maven cần xây **effective model** của child: nó phải tìm được parent POM để biết properties, version management, plugin defaults... Không có parent, Maven chưa thể build đúng model child.

Trong repository chung (ví dụ B), path `../build-parent/pom.xml` đủ để Maven tìm parent khi source tree đầy đủ. Nếu child được checkout/build **riêng** (không có thư mục build-parent), cần parent POM đã có ở local/remote repository hoặc thay đổi cách phân phối phù hợp.

**Đừng dùng `-am` để chữa mọi lỗi parent resolution.** `-am` chọn reactor dependencies của project, không tự tạo một parent POM đang thiếu ở disk/repository. Nếu local parent chưa có và child POM cần nó, Maven có thể fail ngay ở model building.

Đối với parent dùng chung nhiều repo:

1. Publish parent với tọa độ và version rõ.
2. Cấu hình repositories/mirrors theo chính sách tổ chức.
3. Pin `<parent><version>...` trong các project sử dụng.
4. Test build từ một checkout sạch, không phụ thuộc parent POM tình cờ còn ở local cache.
5. Khi nâng parent version, đánh giá ảnh hưởng compile/test/plugin policies riêng.

Đây là một trong những lý do kiến trúc khiến **shared parent thường nên tách khỏi product aggregator**.

## 18. Parent POM và BOM có giống nhau không?

**Không.** Một POM packaging `pom` có thể được dùng làm:

- **Parent POM** qua `<parent>`: cung cấp inheritance rộng, gồm properties/pluginManagement/dependencyManagement...
- **BOM (Bill of Materials)** khi được import qua `<dependencyManagement><dependency scope="import" type="pom">`: chủ yếu cung cấp **dependency management**, không mang theo toàn bộ parent inheritance.
- **Aggregator** qua `<modules>`: chọn projects tham gia reactor.
- Một project có thể đóng một hoặc vài vai trò tùy cách dùng.

Ví dụ **mảnh BOM import**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.build</groupId>
            <artifactId>company-dependencies-bom</artifactId>
            <version>5.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là mảnh minh họa **khác với project runnable ở mục 6/10**; không có artifact BOM thật đi kèm bài.

Một project chỉ có **một direct parent** trong `<parent>`, nhưng có thể import nhiều BOMs với quản trị version/conflicts đúng. Vì vậy tổ chức thường:

- Dùng **shared build parent** để quản lý Java/plugin/quality policies.
- Dùng **BOM** để quản lý tập dependency versions mà nhiều sản phẩm cùng dùng.
- Dùng **aggregator** để nhóm source projects trong từng repository/sản phẩm.

Không cần dùng một mega-parent làm hết nếu ba vòng đời/version khác nhau.

## 19. Cách kiểm effective POM và reactor graph

### 19.1. Effective POM cho child

Trong root của ví dụ A hoặc B:

~~~bash
mvn -B -ntp -pl :greeting-cli org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
~~~

Lệnh Help Plugin cho biết child cuối cùng nhận thông tin từ parent và Super POM ra sao. Tìm:

- `groupId=org.example.reactor` và `version=1.0.0`.
- `dependencyManagement` có `greeting-core=1.0.0`.
- `build/plugins`/`pluginManagement` nhận version của compiler/surefire/jar phù hợp.
- `greeting-cli` có dependency thực tế vào `greeting-core`.
- **Không** suy rằng một config xuất hiện trong effective POM luôn có nghĩa plugin goal đã chạy; cần xem lifecycle bindings và log.

Để lưu output ra file theo cấu hình plugin, có thể dùng option `-Doutput=...` của Help Plugin nếu được hỗ trợ; lựa chọn đường dẫn cụ thể không cần cho bài học.

### 19.2. Dependency tree

~~~bash
mvn -B -ntp -pl :greeting-cli org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Với mô hình bài, tree của CLI chứa dependency vào:

~~~text
org.example.reactor:greeting-core:jar:1.0.0:compile
~~~

Đây là một **dòng mô tả tọa độ kỳ vọng**, không phải toàn bộ log Maven. Nó cho thấy dependency graph khác với việc chỉ đặt core vào `<modules>`.

### 19.3. Reactor selection

~~~bash
mvn -B -ntp -pl :greeting-cli -am clean package
~~~

Maven chọn CLI cùng reactor dependencies cần thiết; chương trình cần core để compile. Dùng lệnh này khi chỉ muốn build ứng dụng CLI và các dependencies nội bộ liên quan.

### 19.4. Kiểm version inherited

~~~bash
mvn -B -ntp -pl :greeting-cli org.apache.maven.plugins:maven-help-plugin:3.5.1:evaluate -Dexpression=project.version -q -DforceStdout
~~~

Với cả hai mô hình đang dùng version 1.0.0, giá trị kỳ vọng:

~~~text
1.0.0
~~~

Đây là **giá trị trả về mong đợi**, không đảm bảo log Maven không có thêm metadata nếu plugin version/environment khác.

## 20. Hai cách tổ chức parent cho nhiều repository

### 20.1. Parent riêng được phát hành tập trung

Một nhóm platform sở hữu:

~~~text
build-conventions-repo/
  pom.xml   -> org.example.build:company-build-parent:3.2.0
~~~

Các product repos khác nhau có aggregator của riêng mình và children dùng:

~~~xml
<parent>
    <groupId>org.example.build</groupId>
    <artifactId>company-build-parent</artifactId>
    <version>3.2.0</version>
    <relativePath/>
</parent>
~~~

Ưu điểm: policy được version hóa và nâng có chủ đích; aggregator của product không phụ thuộc đường dẫn source của parent ở repo khác.

Rủi ro: parent publication outage/mirror không cho phép download khiến build mới fail; thay đổi parent version có thể nâng Maven plugins, Java release hoặc test policies cùng lúc. Cần release notes, compatibility checks và repository governance.

### 20.2. Parent riêng nhưng nằm ngay trong monorepo

Mô hình B giữ parent ở `build-parent/` và aggregator root chứa tất cả modules. Đó là sự tách **vai trò POM**, chứ không buộc phải tách **Git repository** hoặc publish parent riêng.

Ưu điểm: vẫn thử thay đổi parent và children trong cùng PR/repo; parent packaging POM tham gia reactor; không cần mỗi developer install parent thủ công khi build từ root với local relativePath đúng.

Hạn chế: số POMs tăng và việc chạy riêng từ child vẫn có thể cần source parent cũng được checkout.

**Chọn theo nhu cầu governance/release**, không theo quy tắc rằng “parent phải nằm ở một repository khác”.

## 21. Những bẫy khi chuyển từ mô hình chung sang mô hình tách

Giả sử ban đầu child có:

~~~xml
<parent>
    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-root</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Sau khi tạo `build-parent/pom.xml` và root aggregator riêng, cần đổi thành:

~~~xml
<parent>
    <groupId>org.example.reactor</groupId>
    <artifactId>greeting-build-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../build-parent/pom.xml</relativePath>
</parent>
~~~

Đồng thời:

1. Chuyển **properties/dependencyManagement/pluginManagement** cần kế thừa từ root cũ sang build-parent mới.
2. Root aggregator giữ `<modules>` và packaging `pom`, nhưng **không được tự coi mình là parent** nữa.
3. Đảm bảo `build-parent` được liệt kê trong reactor nếu muốn build/publish nó cùng sản phẩm.
4. Rà soát `build/plugins` của root cũ: execution nào cần kế thừa, execution nào chỉ cần ở aggregator, execution nào chỉ cần trong một child?
5. Rà soát `dependencies` thực tế: đừng vô tình chuyển những dependencies chỉ dùng trong một child vào parent khiến mọi child có thêm chúng.
6. Chốt cùng version hoặc version độc lập theo chính sách; nếu parent version khác sản phẩm, children phải khai báo đúng parent version.
7. Đảm bảo relativePaths trên cả Linux và Windows; dùng `/` trong POM paths để portability tốt.
8. Build sạch từ root, sau đó thử build từng module theo chiến lược `-pl/-am`.
9. Xem effective POM trước và sau migration cho một child đại diện, đặc biệt compiler/surefire/plugins, dependency versions, repositories.
10. Cập nhật CI scripts chạy đúng aggregator POM, không nhầm `-f build-parent/pom.xml` với full reactor build.

**Không đổi hàng loạt tọa độ artifact ứng dụng nếu không cần.** Tên parent/aggregator có thể thay mà `greeting-core` và `greeting-cli` vẫn giữ `org.example.reactor:...:1.0.0` trong demo; sửa dependency ở consumer chỉ khi GAV app thực sự đổi.

## 22. Các lệnh Maven hay bị dùng sai

| Lệnh/setting | Kỳ vọng sai | Hành vi nên hiểu |
| --- | --- | --- |
| `mvn -f build-parent/pom.xml verify` | “Sẽ chạy mọi child đang kế thừa parent.” | Chỉ chạy project và modules mà POM đó aggregate; parent của B **không có modules**. |
| `mvn -N package` từ root | “Sẽ build reactor nhanh mà không cần plugin.” | `-N` tắt recursive reactor collection, chỉ chạy root POM. |
| `mvn -pl :greeting-cli package` | “Tự build core vì cùng modules.” | Không có `-am`, có thể cần core artifact ở repository; tập build chỉ chọn CLI. |
| `mvn -pl :greeting-cli -am package` | “Làm CLI có Java classpath của mọi module.” | Chỉ chọn các reactor dependency projects cần, classpath vẫn do `<dependencies>` xác định. |
| `mvn -pl :greeting-core -amd test` | “Chỉ chạy core.” | `-amd` thêm **reactor dependents** (ví dụ CLI) nếu áp dụng, không giống `-am`. |
| `mvn -rf :greeting-cli verify` | “Tự build upstream chưa có artifact.” | Resume từ một module; có thể cần upstream artifacts sẵn, không đồng nghĩa `-am`. |
| Đặt core trong `dependencyManagement` | “CLI import được core.” | Không, còn thiếu `<dependencies>` ở CLI. |
| Đặt compiler trong `pluginManagement` | “Mọi custom execution sẽ tự chạy.” | Không; management quản lý plugin đã được sử dụng/bind. |
| `<parent><relativePath>../pom.xml` trong layout B | “Root sẽ tìm sang build-parent.” | Sai path; cần `../build-parent/pom.xml`. |
| Chỉ sửa root aggregator `<modules>` | “Thay đổi ngay mọi child plugin config.” | Không có inheritance nếu child không trỏ root làm parent. |

**Đặc biệt về `-pl`:** một module có thể được chọn theo path hoặc `:artifactId`; dùng syntax phù hợp project/Maven version. Trong reactor có artifactId trùng nhau giữa các groups, cần chọn định danh rõ ràng hơn để tránh mơ hồ.

## 23. Parent chung và plugin inheritance: đừng tạo side effect cho mọi module

Parent thường là nơi đặt:

~~~xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
    </plugins>
</pluginManagement>
~~~

Đây là lựa chọn tốt để quản lý compiler version.

Nhưng nếu đặt **plugin execution thực tế** trong `build/plugins` của parent:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <id>print-message</id>
            <phase>validate</phase>
            <goals><goal>run</goal></goals>
            <configuration>
                <target>
                    <echo message="parent-execution"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

thì mảnh này (nếu đặt dưới `<build><plugins>`) có thể được **kế thừa** và áp dụng ở child, làm echo chạy ở nhiều modules. Đó là behavior hữu ích nếu **mọi module** cần policy check, nhưng sai nếu bạn chỉ muốn thao tác một lần ở product-level aggregator.

Để hạn chế inheritance, một số plugin hoặc execution có thể dùng:

~~~xml
<inherited>false</inherited>
~~~

Chỉ chèn `<inherited>false</inherited>` tại vị trí mà POM/plugin schema cho phép và có mục tiêu rõ. Với công việc thực sự cần chạy một lần cuối reactor, còn phải kiểm plugin goal có tính aggregator hay không và chọn execution/phase phù hợp. `<inherited>false>` **không tự biến bất kỳ goal nào thành aggregator goal**.

Trong ví dụ A/B, ta **không** dùng Antrun thực thi; ví dụ trên là **mảnh minh họa anti-pattern có thể xảy ra**, không thuộc POM runnable.

## 24. Phiên bản parent, children và phát hành

Trong ví dụ A:

~~~text
org.example.reactor:greeting-root:1.0.0       <- parent + aggregator
org.example.reactor:greeting-core:1.0.0       <- child library
org.example.reactor:greeting-cli:1.0.0        <- child app
~~~

Trong ví dụ B:

~~~text
org.example.reactor:greeting-reactor:1.0.0       <- aggregator
org.example.reactor:greeting-build-parent:1.0.0  <- parent
org.example.reactor:greeting-core:1.0.0          <- child library
org.example.reactor:greeting-cli:1.0.0           <- child app
~~~

Hai layout đều dùng version `1.0.0` để minh họa. **Trong thực tế, parent version và product/app versions không bắt buộc bằng nhau.** Một corporate parent có thể là `3.2.0` trong khi app được phát hành `2026.11`. Parent version thay đổi là một quyết định nâng build policy, không đồng nghĩa app version phải tăng trừ khi quy trình release yêu cầu.

### 24.1. Vì sao parent POM cần được publish?

Khi một child JAR được đưa lên Maven repository, POM của nó thường có `<parent>`. Một consumer/build machine sạch cần resolve parent đó khi dựng effective POM của child theo quy tắc Maven. Nếu parent không có ở repository và cũng không có local source path phù hợp, Maven có thể không đọc được child model dù file JAR tồn tại.

Vì vậy khi publish modules cho users ở ngoài reactor:

- Đảm bảo parent POM có thể resolve theo đúng GAV, đặc biệt với corporate/private repositories.
- Đảm bảo dependency versions/classifiers và POM metadata đúng.
- Không chỉ copy `target/*.jar` rồi bỏ quên POM/parent khi kỳ vọng Maven consumer tự resolve transitive graph.

### 24.2. Aggregator có cần publish không?

**Không mặc định.** Nếu root aggregator chỉ dùng để điều phối source build, consumer dùng JAR của child **không cần aggregator POM** chỉ vì child được root liệt kê. Nếu aggregator **cũng là parent** (mô hình A), parent POM này lại cần resolve với vai trò parent.

Trong mô hình B, bạn có thể chọn không phát hành `greeting-reactor` nếu nó thuần điều phối; nhưng `greeting-build-parent` cần được publish nếu các child phát hành với POM vẫn tham chiếu nó và consumer phải resolve qua repository.

**Lưu ý:** `mvn install` từ root reactor thông thường sẽ cài cả những POM modules được chọn vào local repository. Sự hiện diện của aggregator POM trong repository không có nghĩa consumer cần khai báo nó như dependency.

## 25. CI/CD: chạy lệnh nào và đặt cache thế nào?

Với cả A lẫn B, pipeline nên làm việc từ **aggregator root** khi cần kiểm toàn product:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu chỉ muốn kiểm CLI và dependencies của nó:

~~~bash
mvn -B -ntp -pl :greeting-cli -am clean verify
~~~

Đừng chọn `build-parent/pom.xml` làm build entrypoint trong mô hình B khi mục tiêu là build toàn sản phẩm.

Một workflow GitHub Actions minh họa:

~~~yaml
name: Maven reactor verify
on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify all reactor modules
        run: mvn -B -ntp clean verify
~~~

Đây là **ví dụ workflow**, giả định runner đã có Maven đủ mới/tương thích và repository root là aggregator. Nó không tự pin Maven distribution version; trong production, nên dùng Maven Wrapper hoặc cách quản lý Maven version được kiểm soát.

Nếu project có Maven Wrapper được commit vào Git, lệnh tương ứng là:

~~~bash
./mvnw -B -ntp clean verify
~~~

Nhưng ví dụ A/B **không tự tạo wrapper files**. Không dùng `./mvnw` nếu repository chưa có file thực. Với CI Windows, shell command cũng phải thích hợp với runner và wrapper script.

Để tránh “chạy tốt trên laptop vì local cache”:

1. Dùng repository/cache của CI theo chính sách tổ chức.
2. Verify child POM có thể resolve parent trong checkout/repository như dự kiến.
3. Kiểm `mvn --version` và JDK 17 thật, không chỉ `maven.compiler.release`.
4. Dùng `-pl/-am` rõ ràng cho partial builds.
5. Kiểm status/test reports **theo module**, không chỉ root POM packaging `pom`.
6. Với build artifacts publish cho người khác, test resolution trên một môi trường sạch để phát hiện parent POM chưa publish.

## 26. Các ca lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Non-resolvable parent POM`. | Parent sai coordinates/version, `relativePath` sai hoặc repository chưa có parent. | Đối chiếu `<parent>`, path tương đối từ child, parent artifact GAV, quyền repository. |
| `parent.relativePath points at wrong local POM`. | Layout đã tách parent nhưng child vẫn trỏ `../pom.xml`. | Đổi thành `../build-parent/pom.xml` hoặc policy parent repository resolution. |
| Root aggregator chạy nhưng child không nhận Java 17 property. | Child không inherit aggregator, mà inherit parent khác. | Đặt properties ở **parent thật** và xem effective POM. |
| Child compile fail không tìm `GreetingFormatter`. | CLI chưa khai báo project dependency core hoặc không resolve được artifact. | Thêm `<dependency>` đúng GAV, build từ root với `-am` hoặc install core. |
| Thứ tự `<modules>` CLI trước core gây hiểu nhầm. | Tưởng list order là toàn bộ build order. | Xem reactor sort và Maven dependencies; CLI → core thì core cần build trước. |
| `dependencyManagement` có core nhưng CLI import không được. | Management không tạo dependency thực tế. | Thêm core vào `greeting-cli/dependencies`. |
| Parent có pluginManagement nhưng custom goal không chạy. | Plugin chưa được bind/tham chiếu. | Cấu hình plugin execution ở đúng `build/plugins`. |
| Antrun/plugin execution chạy ở mọi child ngoài ý muốn. | Kế thừa `build/plugins` từ parent. | Xem inheritance/`inherited=false`/execution scope đúng mục tiêu. |
| `mvn -f build-parent/pom.xml verify` không build core/CLI. | Parent đã tách và không có `<modules>`. | Chạy từ **aggregator root**. |
| Chạy từ CLI folder fail dù root build thành công. | Child không tự hình thành full reactor từ parent; core chưa install. | Dùng root `-pl :greeting-cli -am` hoặc install dependencies. |
| CI trên checkout sạch báo parent missing. | Parent chỉ tồn tại local cache laptop hoặc chưa publish. | Publish/install parent đúng chính sách hoặc checkout source parent và relativePath đúng. |
| Sau tách, consumer fail resolve child POM. | Child tham chiếu parent mới chưa được publish. | Publish parent trước/đúng release workflow và kiểm POM metadata. |
| Root POM tạo ra không có JAR. | Packaging `pom` đúng chức năng. | Tìm JAR trong `greeting-core/target` hoặc `greeting-cli/target`. |
| `java -jar greeting-cli-1.0.0.jar` không chạy. | Chưa có Main-Class và core dependency không bundle. | Dùng `java -cp` như bài, hoặc cấu hình executable/fat-JAR riêng. |
| `mvn -N verify` chỉ build root. | `-N` tắt recursion. | Bỏ `-N` khi muốn build modules. |
| Parent build policy thay đổi nhưng children khác nhau. | Module nào đó có override profile/plugins/dependencies. | Xem effective POM theo module và plugin execution logs. |
| Shared parent gây lỗi trên Java/Maven cũ. | Parent nâng compiler/plugin versions nhưng downstream toolchain chưa đáp ứng. | Pin/kiểm build toolchain, release notes, test upgrade parent theo từng product. |
| Aggregator chứa đường dẫn module máy cá nhân. | `<modules>` khai báo absolute/nonportable path. | Dùng đường dẫn tương đối đúng từ aggregator POM. |

**Quy trình chẩn đoán:** kiểm project đang chạy từ POM nào → kiểm aggregator `<modules>` → kiểm child `<parent>`/`relativePath` → kiểm effective POM → kiểm dependency thực tế giữa modules → kiểm reactor build order → kiểm plugins và command-line selection.

## 27. Checklist thiết kế trước khi chọn mô hình

- [ ] Đã phân biệt inheritance, aggregation và project dependencies là **ba quan hệ khác nhau**.
- [ ] Biết project nào là parent thật và POM nào là aggregator root.
- [ ] Parent POM packaging `pom`, tọa độ GAV rõ.
- [ ] Aggregator POM packaging `pom` và `<modules>` ghi đúng đường dẫn tương đối.
- [ ] Child `<parent>` trỏ đúng tọa độ/`relativePath`, không đoán từ tên thư mục.
- [ ] Nếu muốn kế thừa groupId/version, child không ghi giá trị khác ngoài chủ đích.
- [ ] Mỗi child có artifactId riêng.
- [ ] Version cho inter-module dependency được quản lý hoặc khai báo rõ.
- [ ] Child thực sự dùng library khác phải có `<dependencies>`; management không tự thêm.
- [ ] Plugin versions và build policies được quản lý tại parent, custom executions đặt đúng project/phase.
- [ ] Reactor order được kiểm theo instantiated dependencies, không dựa tuyệt đối vào danh sách modules.
- [ ] Nếu tách parent, đã quyết định có publish/build parent cùng root reactor hay không.
- [ ] CI chạy từ aggregator root, trừ khi cố ý chỉ build parent.
- [ ] `-pl/-am/-amd/-N/-rf` được dùng có chủ đích, không nhầm với inheritance.
- [ ] Child cần build độc lập có thể resolve parent lẫn project dependencies.
- [ ] Test reports và JAR outputs được kiểm ở đúng child `target/`.
- [ ] Shared parent không kéo execution/dependency không phù hợp vào mọi child.
- [ ] Khi phát hành, Maven consumer có thể resolve parent POM của published child.
- [ ] Có tài liệu release/version governance nếu parent được chia sẻ liên repository.
- [ ] Sau migration, đã so effective POM và chạy build sạch trước/sau.

## 28. Câu hỏi tự kiểm tra

1. **`<parent>` trong child và `<modules>` trong root có cùng nghĩa không?**  
   Không. Parent chỉ định nguồn **inheritance**; modules chỉ định tập project **aggregation/reactor**.

2. **Một root POM có thể vừa là parent vừa là aggregator không?**  
   Có. Mô hình A dùng `greeting-root/pom.xml` packaging POM, children trỏ về root và root liệt kê modules.

3. **Aggregator có thể gom các project không kế thừa chính nó không?**  
   Có. Mô hình B root `greeting-reactor` aggregate core/CLI; children kế thừa `greeting-build-parent`.

4. **Parent POM có thể không có `<modules>` không?**  
   Có. Parent chỉ cần được child trỏ tới và có packaging POM phù hợp, không nhất thiết aggregate.

5. **`<modules>greeting-core</modules>` có tự cấp classpath cho CLI không?**  
   Không. CLI cần Maven dependency thực sự vào core. Đồng thời XML đúng là `<modules><module>greeting-core</module></modules>`.

6. **Nếu modules liệt kê CLI trước core nhưng CLI phụ thuộc core, project nào build trước?**  
   Reactor cần build core trước CLI theo dependency edge.

7. **`dependencyManagement` của parent có tự làm child import được core không?**  
   Không. Child vẫn phải khai báo `<dependencies>`; management hỗ trợ version/scopes.

8. **Trong mô hình B, child để `relativePath=../pom.xml` là đúng không?**  
   Không; đó là aggregator khác tọa độ. Dùng `../build-parent/pom.xml`.

9. **`mvn -f build-parent/pom.xml verify` có build cả reactor B không?**  
   Không; parent không khai báo modules. Hãy chạy từ aggregator root.

10. **Parent nằm ở remote repository, có thể dùng `<relativePath/>` không?**  
    Có, đó là cách tắt việc tìm local parent bằng relative path ở Maven 3; parent phải resolve được từ repository.

11. **Tại sao `mvn -pl :greeting-cli -am package` hữu ích?**  
    Nó chọn CLI và các upstream reactor dependencies của CLI (gồm core), thay vì chỉ cố build CLI cô lập.

12. **Cùng repository thì việc tách parent bắt buộc phải publish parent riêng không?**  
    Không. Nếu local parent path tồn tại, reactor build có thể resolve parent từ source tree; publication cần khi build/consumer ngoài source tree cần parent.

13. **Khi publish child artifact, vì sao parent POM có thể quan trọng?**  
    Published child POM có `<parent>`; consumer Maven cần resolve parent để dựng effective model và transitive dependency management.

14. **`pluginManagement` có bảo đảm plugin goal custom chạy không?**  
    Không. Nó quản lý cấu hình cho plugin được sử dụng/bind, không tự tạo mọi execution.

15. **Nếu chỉ muốn chạy một plugin ở aggregator, cần thận trọng gì khi root cũng là parent?**  
    Xem plugin goal semantics và inheritance; một `build/plugins` execution có thể lan xuống children nếu không giới hạn.

16. **Parent version có nhất thiết bằng product version không?**  
    Không. Một build parent chung có thể được version/release độc lập với các sản phẩm đang dùng.

17. **Một project chỉ được aggregate nhưng không inherit root có nhận project properties của root không?**  
    Không tự động. Chỉ quan hệ inheritance hoặc cấu hình thực sự được áp dụng mới đem properties vào effective POM.

18. **Bố cục nào nên chọn trước cho nhóm nhỏ, cùng release và build policy?**  
    Parent + aggregator chung thường đơn giản hơn; chỉ tách khi có nhu cầu reuse/governance hoặc lifecycle rõ.

## 29. Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html) — định nghĩa inheritance, aggregation, `relativePath` và mô hình kết hợp cả hai.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — reactor collection, sorting, instantiated relationships, `-am`, `-amd`, `-N` và `-rf` trong Maven 3.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — `parent`, `modules`, inheritance, `dependencyManagement`, `pluginManagement`, phần tử `build` và packaging.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — dependencies thực tế, management và scope.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — lifecycle với packaging `pom` và `jar`, phase `test`/`verify`.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html) — kiểm kết quả inheritance và active profile effects.
- [Apache Maven Help Plugin — evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html) — xem model expressions như `project.version`.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — project dependency graph và version đã resolve.
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html) — profile activation và inherited effects.
- [Apache Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html) — Java release 17 trong Maven builds.
- [Apache Maven Surefire Plugin — Using JUnit 5 Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html) — JUnit Jupiter test execution.

**Kết luận:** Parent và aggregator là **hai vai trò của POM**, không phải hai loại Java code hay hai cách viết cùng một relationship. Chọn **một POM vừa làm parent vừa làm aggregator** khi các modules cùng sản phẩm, cùng policy và cần sự đơn giản; **tách một shared parent khỏi aggregator** khi muốn tái sử dụng build conventions, quản lý release độc lập hoặc có nhiều repositories với tập modules khác nhau. Trong mọi mô hình, child phải trỏ đúng `<parent>`, aggregator phải liệt kê đúng `<modules>`, và module thật sự dùng code của module khác phải có `<dependency>`. Kiểm bằng `mvn clean verify`, `-pl/-am`, effective POM và Java runtime, không đoán từ tên thư mục.
