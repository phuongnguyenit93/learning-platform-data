# Phân biệt source, target và release khi nhắm đến Java đích

## 1. Mục tiêu: biên dịch bằng JDK mới nhưng chạy trên Java cũ

Một nhóm đang dùng JDK 17 để build Maven, nhưng sản phẩm cần chạy trên Java 8. Chỉ nhìn dòng `BUILD SUCCESS` hoặc thấy `java -version` ở máy build là **17** không đủ để kết luận ứng dụng có chạy được trên Java 8 hay không. Có ít nhất ba câu hỏi độc lập:

1. **Mã nguồn được dùng những tính năng cú pháp của Java nào?** Ví dụ có được dùng `record`, `var`, `switch` expression hoặc lambda không?
2. **File `.class` được tạo ra cho phiên bản JVM nào?** Java 8 có đọc được class file đó hay báo `UnsupportedClassVersionError`?
3. **Mã biên dịch có tham chiếu API Java SE xuất hiện sau phiên bản đích không?** Ví dụ `String.isBlank()` chỉ có từ Java 11; Java 8 không cung cấp phương thức đó.

Ba lựa chọn của Java compiler và **Maven Compiler Plugin** liên quan trực tiếp đến ba câu hỏi:

- **`source`**: giới hạn **cú pháp và tính năng ngôn ngữ Java** mà compiler chấp nhận.
- **`target`**: đặt **phiên bản định dạng bytecode** (class-file version) được sinh ra.
- **`release`**: chọn **một phiên bản nền tảng Java** cho cả **ngôn ngữ, bytecode và tập API chuẩn được phép dùng**.

Trong ứng dụng Maven thông thường biên dịch bằng JDK 9 trở lên, **ưu tiên `maven.compiler.release`** khi muốn nhắm tới một Java đích cụ thể. Chỉ cài `source`/`target` có thể tạo bytecode ở mức cũ nhưng vẫn tham chiếu API không hề có ở JVM đích.

**Ghi nhớ:** `source` hỏi *“được viết theo ngữ pháp Java nào?”*; `target` hỏi *“JVM nào đọc được định dạng class?”*; `release` hỏi *“mã này được biên dịch theo hợp đồng nền tảng Java nào?”*.

## 2. Bảng phân biệt source, target và release

| Tùy chọn javac | Maven Compiler Plugin | Kiểm soát chính | Không tự bảo đảm |
| --- | --- | --- | --- |
| **`-source 8`** / **`--source 8`** | `maven.compiler.source=8` hoặc `<source>8</source>` | Cú pháp/ngữ nghĩa ngôn ngữ Java 8. | Class file Java 8 hoặc API chỉ từ Java 8 trở xuống nếu đặt riêng lẻ. |
| **`-target 8`** / **`--target 8`** | `maven.compiler.target=8` hoặc `<target>8</target>` | Mức class-file được sinh ra. | API đang tham chiếu thực sự tồn tại ở Java 8. |
| **`--release 8`** | `maven.compiler.release=8` hoặc `<release>8</release>` | Ngôn ngữ Java 8, bytecode Java 8 và API nền tảng Java 8 được công cụ hỗ trợ. | Dependency bên thứ ba tương thích Java 8 hoặc mọi đường chạy runtime đều đã được kiểm thử. |

**Không đồng nhất Maven version, JDK chạy Maven và Java đích.** Maven 3.9.x, JDK 17, Java release 8 là ba thông số độc lập:

~~~text
Maven runtime       Maven 3.9.x
JDK chạy Maven      JDK 17
Maven Compiler      maven-compiler-plugin 3.13.0
Java đích            8
javac option         --release 8
.class major version 52
Môi trường phải test  Java 8 thực tế (nếu sản phẩm hỗ trợ Java 8)
~~~

Đây là **tình huống cấu hình**, không phải output nguyên văn của Maven.

**`release` không có nghĩa build phải chạy trên đúng JDK đích.** JDK 17 có thể biên dịch nhắm Java 8 khi javac bản đó vẫn hỗ trợ release 8. Nhưng một JDK mới hơn không nhất thiết hỗ trợ mọi release đã quá cũ; cần kiểm tra danh sách release được javac hỗ trợ.

## 3. Nhìn qua javac trước khi cấu hình Maven

Maven Compiler Plugin cuối cùng cũng phải sử dụng một compiler (thường là `javac`/Java Compiler API). Vì vậy nên hiểu cơ chế javac trước.

Giả sử có tệp **Hello.java**:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
~~~

Với JDK 17 đang hoạt động, bạn có thể biên dịch:

~~~bash
javac -source 8 -target 8 Hello.java
~~~

hoặc ưu tiên:

~~~bash
javac --release 8 Hello.java
~~~

Cả hai có thể tạo `Hello.class` mang **major version 52**, định dạng class của Java 8. Tuy nhiên **ý nghĩa kiểm soát API khác nhau**, dù ví dụ đơn giản này chưa tạo ra sự khác biệt vì `System.out.println` có từ lâu.

Trên JDK 17, dùng:

~~~bash
javap -verbose Hello.class
~~~

và xem dòng:

~~~text
major version: 52
~~~

Đây là giá trị kỳ vọng khi class được biên dịch thành công với Java 8 target. Lệnh javap có thể in rất nhiều metadata khác.

**Lưu ý:** `javac --release 8` là tùy chọn javac có từ **JDK 9**. Không thể chạy trực tiếp lệnh đó bằng **javac của JDK 8** vì JDK 8 không nhận biết `--release`.

### Source chỉ điều khiển cú pháp

Ví dụ sau dùng **record**, được đưa vào Java chuẩn sau Java 8:

~~~java
public record User(String name) {
}
~~~

Đây là **đoạn mã minh họa**, không thuộc dự án runnable ở mục 7. Trên JDK 17, nếu cố dùng `-source 8` để biên dịch tệp chứa `record`, compiler sẽ không chấp nhận tính năng ngôn ngữ đó. **Chỉnh `-target 8` không biến record thành cú pháp Java 8**.

Tương tự, `-source 8` cho phép lambda vì lambda đã xuất hiện trong Java 8, nhưng không cho phép `var` cho biến cục bộ được đưa vào từ Java 10 hoặc các tính năng ngôn ngữ mới hơn.

### Target chỉ điều khiển định dạng class file

`-target 8` yêu cầu định dạng class file phù hợp Java 8. Nó **không làm thư viện Java runtime của JDK 17 biến thành thư viện Java 8** và không tự thay API mà compiler thấy từ JDK đang dùng. Đây là lý do phần thực hành phản chứng ở mục 5 rất quan trọng.

### Release kiểm soát API nền tảng

Với `--release 8`, `javac` dùng thông tin API của Java 8 do công cụ cung cấp. Những phương thức, class hoặc module chỉ xuất hiện ở Java 9, 11, 17... **không được coi là API Java 8** trong quá trình biên dịch. Vì vậy lỗi xảy ra **ngay ở compile time**, thay vì để một bản build tưởng như hợp lệ gặp lỗi khi chạy trên JVM 8.

## 4. Bảng bytecode major version thông dụng

Mỗi class file có trường **major version** cho biết định dạng class tối thiểu mà JVM cần hiểu.

| Java đích | Class major version | Nhận xét |
| --- | ---: | --- |
| Java 8 | **52** | Đích thường gặp của thư viện cần hỗ trợ Java 8. |
| Java 9 | **53** | Java Platform Module System ra đời. |
| Java 11 | **55** | Một phiên bản LTS thông dụng. |
| Java 17 | **61** | Một phiên bản LTS thông dụng. |
| Java 21 | **65** | Một phiên bản LTS mới hơn. |

Ví dụ một file class major **61** không thể được nạp bởi JVM Java 8 (nó chỉ hiểu tới major 52). JVM thường báo:

~~~text
java.lang.UnsupportedClassVersionError: ... has been compiled by a more recent version of the Java Runtime
~~~

Đây là **mẫu lỗi được rút gọn**; toàn bộ thông báo có thể chứa major version, tên lớp và stack trace.

Tuy nhiên, **major 52 không phải bằng chứng ứng dụng chắc chắn chạy được trên Java 8**. Class có thể gọi API không tồn tại trên Java 8, hoặc một dependency đi kèm có class major cao hơn. Phải kiểm tra **cả bytecode, Java API và thư viện ngoài**.

## 5. Phản chứng cốt lõi: source 8 + target 8 vẫn dùng được API Java 11

Tạo file **NewApiProbe.java** tách biệt với dự án mẫu ở mục 7:

~~~java
public class NewApiProbe {
    public static void main(String[] args) {
        System.out.println(" ".isBlank());
    }
}
~~~

Phương thức **`String.isBlank()`** được đưa vào Java từ **Java 11**. Trên JDK 17, hãy thử hai cách biên dịch.

### Cách A — chỉ source và target

~~~bash
javac -source 8 -target 8 NewApiProbe.java
~~~

**Trên JDK 17, cách này có thể biên dịch thành công** dù mục tiêu bytecode là Java 8, bởi compiler đang nhìn thấy API của JDK 17 chứa `String.isBlank()`. Bạn có thể thấy warning kiểu:

~~~text
warning: [options] bootstrap class path not set in conjunction with -source 8
~~~

Không dựa vào nguyên văn warning vì nó thay đổi theo JDK và tham số. Kiểm tra class file:

~~~bash
javap -verbose NewApiProbe.class
~~~

Kết quả có **major version: 52**, nhưng nếu chạy class đó trên một **Java 8 runtime thật**, dòng gọi `String.isBlank()` không tồn tại trong `java.lang.String` của Java 8. JVM có thể ném:

~~~text
java.lang.NoSuchMethodError: java.lang.String.isBlank()Z
~~~

Đây là **dấu hiệu lỗi liên kết runtime minh họa**; cách diễn đạt của JVM có thể khác. Trong khi đó nếu chạy trên Java 17, chương trình in `true`.

### Cách B — dùng release

~~~bash
javac --release 8 NewApiProbe.java
~~~

Compiler trên JDK 17 sẽ **từ chối** đoạn mã vì API `String.isBlank()` không thuộc Java 8. Thông báo thường có phần:

~~~text
cannot find symbol
  symbol:   method isBlank()
~~~

Đây là nguyên nhân chính nên dùng **`--release 8`** thay vì chỉ `-source 8 -target 8` khi cần bảo đảm code chỉ tham chiếu API nền tảng Java 8.

**Đừng thêm NewApiProbe.java vào `src/main/java` của dự án runnable sau đây** khi POM đặt release 8; nó sẽ cố ý làm build thất bại. Mục 5 là **thí nghiệm độc lập để quan sát khác biệt**.

### Vì sao lỗi có thể lọt qua cả unit test?

Nếu CI build bằng JDK 17 với `source 8 + target 8` rồi chạy test cũng trên JDK 17, API `String.isBlank()` vẫn tồn tại nên test có thể pass. Khi bản class major 52 được chuyển lên máy Java 8, API không còn và runtime mới lỗi.

**`--release 8` phát hiện tình huống này ngay khi biên dịch**, nhưng không giải quyết hết mọi loại tương thích. Vẫn cần test sản phẩm trên JVM đích và kiểm tra dependency bắc cầu.

## 6. Cấu hình source, target và release trong Maven Compiler Plugin

Các thuộc tính thông dụng của **Maven Compiler Plugin**:

| Thuộc tính trong POM | Parameter plugin | Ý nghĩa |
| --- | --- | --- |
| `<maven.compiler.source>8</maven.compiler.source>` | `<source>8</source>` | Truyền lựa chọn ngôn ngữ `-source` theo compiler. |
| `<maven.compiler.target>8</maven.compiler.target>` | `<target>8</target>` | Truyền lựa chọn class-file target `-target`. |
| `<maven.compiler.release>8</maven.compiler.release>` | `<release>8</release>` | Dùng `--release 8` với javac/JDK hỗ trợ. |
| `<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>` | Cấu hình encoding của plugin | Ổn định cách đọc mã nguồn có ký tự tiếng Việt. |

### Cách ưu tiên: chọn release trong properties

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đây là **đoạn POM**, không phải XML độc lập. Với Maven Compiler Plugin được quản lý/version phù hợp, nó yêu cầu javac trên JDK 9+ biên dịch theo Java 8 release.

### Hoặc cấu hình trực tiếp plugin

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>8</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Cách này hợp khi bạn muốn cấu hình tập trung tại plugin hoặc đặt nhiều compiler options có chủ đích. Với dự án đa module, có thể pin version trong parent `pluginManagement`, còn cấu hình bản đang sử dụng trong đúng module hoặc nơi phù hợp.

### Cách cũ: source và target

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
~~~

Cấu hình này đặt ngôn ngữ và bytecode, **không phải hợp đồng API Java 8** khi biên dịch trên JDK cao hơn. Apache Maven Compiler Plugin khuyến nghị `release` trong trường hợp plugin/JDK hỗ trợ.

### Có nên khai báo cả ba?

**Với `javac` JDK 9+**, tùy chọn command line **`--release` không thể dùng đồng thời với `-source` hoặc `-target`**. Vì vậy trong POM hiện đại chỉ cần `maven.compiler.release` khi muốn đặt mức Java duy nhất.

**Ngoại lệ có chủ đích:** từ Maven Compiler Plugin **3.13.0**, với compiler ID mặc định `javac`, thuộc tính `release` trên **JDK 8** được plugin chuyển thành source/target. Tài liệu Maven cho phép khai báo cả ba với cùng version **8** để một POM hỗ trợ cả build bằng JDK 8 và build bằng JDK 9+; plugin biết lựa chọn tham số phù hợp. **Đừng tự áp dụng quy tắc đó cho lệnh javac thô hoặc compiler/plugin khác**.

### Không nên dựa vào default ngầm định

Maven Compiler Plugin **3.13.0** có default `source=1.8` và `target=1.8` nếu không cấu hình; các phiên bản plugin khác có thể thay default. Việc `mvn --version` báo JDK 17 **không đồng nghĩa default compiler target 17**. Một POM muốn có hợp đồng Java đích rõ ràng nên **cấu hình tường minh `release` và pin plugin version**, thay vì phụ thuộc vào ngầm định của một bản plugin.

## 7. Dự án Java 17 build, nhắm Java 8: POM và mã nguồn chạy được

Ta dùng **JDK 17 để thực hiện build**, nhưng sản phẩm là class dùng **Java 8 language/API**. Ví dụ có Maven Compiler Plugin `3.13.0`, một lớp Java chính và một test JUnit Jupiter.

Cấu trúc:

~~~text
java-target-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/target/LegacyApp.java
    └── test/java/vn/example/target/LegacyAppTest.java
~~~

### 7.1. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>java-target-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>8</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
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
    </build>
</project>
~~~

**Giải thích:**

1. **`maven.compiler.release=8`** nói với Compiler Plugin dùng Java 8 làm nền tảng đích; khi build trên JDK 17 với javac, plugin sẽ dùng hành vi tương đương `--release 8`.
2. **`maven.compiler.release` không thay đổi JVM đang chạy Maven**: muốn biết đó là JDK nào, dùng `mvn --version`.
3. **`maven-compiler-plugin` version 3.13.0** hỗ trợ property `release` và cách xử lý JDK 8 được tài liệu hóa.
4. JUnit Jupiter `5.10.2` có scope **test**; không phải dependency runtime của main class.
5. Surefire thực thi test ở phase test, JAR Plugin đóng gói class/resource của dự án khi package.
6. **JAR của dự án chưa cấu hình `Main-Class`**, vì vậy lệnh chạy dùng `java -cp ... <fully-qualified-class>`, không dùng `java -jar`.

**Không lấy ví dụ này làm khẳng định mọi JUnit version đều tương thích Java 8**. Khi nhắm tới Java cũ, phải kiểm tra minimum Java version của **từng dependency/test tool version**. JUnit 5.10.x thuộc nhánh hỗ trợ Java 8, nhưng các major version mới có thể có yêu cầu khác.

### 7.2. src/main/java/vn/example/target/LegacyApp.java

~~~java
package vn.example.target;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public final class LegacyApp {
    private LegacyApp() {
    }

    public static String labels() {
        List<String> names = Arrays.asList("maven", "java");
        return names.stream()
                .map(name -> name.toUpperCase(Locale.ROOT))
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        System.out.println("Java 8 target OK: " + labels());
    }
}
~~~

Mã dùng **lambda, Stream API và Collectors**, đều nằm trong Java 8. Không dùng `List.of(...)` (Java 9), `String.isBlank()` (Java 11), record hoặc syntax Java mới. Vì vậy source này biên dịch được với `--release 8` khi JDK hiện tại còn hỗ trợ release 8.

### 7.3. src/test/java/vn/example/target/LegacyAppTest.java

~~~java
package vn.example.target;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LegacyAppTest {
    @Test
    void joinsUppercaseLabels() {
        assertEquals("MAVEN, JAVA", LegacyApp.labels());
    }
}
~~~

Test sử dụng API JUnit Jupiter phù hợp, nhưng lưu ý test chạy trong JVM do **Surefire** khởi tạo. Nó **không tự đổi sang JDK 8** chỉ vì compiler nhắm Java 8.

### 7.4. Build và chạy bằng JDK 17

Tại thư mục `java-target-demo`:

~~~bash
mvn --version
mvn -B clean verify
java -cp target/classes vn.example.target.LegacyApp
~~~

**Stdout chính xác của riêng lệnh Java cuối**, không tính log Maven:

~~~text
Java 8 target OK: MAVEN, JAVA
~~~

Nếu `mvn clean verify` thành công, mã chính/test đã được biên dịch và JUnit test phù hợp đã chạy. Điều này **chưa phải một phép thử trên Java 8 runtime** nếu Maven/Surefire đang chạy JDK 17. Để khẳng định hỗ trợ Java 8, cần thêm phép chạy trên Java 8 thật hoặc CI matrix phù hợp.

### 7.5. Kiểm tra class-file version

Sau khi build:

~~~bash
javap -verbose target/classes/vn/example/target/LegacyApp.class
~~~

Tìm trong output:

~~~text
major version: 52
~~~

Java 8 tương ứng major version **52**. Trên Windows PowerShell, bạn có thể lọc theo chuỗi:

~~~powershell
javap -verbose target\classes\vn\example\target\LegacyApp.class | Select-String "major version"
~~~

Trên Linux/macOS:

~~~bash
javap -verbose target/classes/vn/example/target/LegacyApp.class | grep "major version"
~~~

Đây là phép xác nhận **định dạng bytecode**, không thay cho kiểm tra tương thích API của dependency hoặc chạy trên Java 8 thực tế.

### 7.6. Chạy trên JVM đích để kiểm chứng

Nếu một máy/runner có JDK 8 được cài và biến môi trường **JAVA8_HOME** đã được cấu hình tới thư mục JDK 8, trên Linux/macOS có thể chạy:

~~~bash
"$JAVA8_HOME/bin/java" -cp target/classes vn.example.target.LegacyApp
~~~

Nếu đúng Java 8 runtime, stdout kỳ vọng vẫn là:

~~~text
Java 8 target OK: MAVEN, JAVA
~~~

Ở Windows PowerShell, khi biến môi trường **JAVA8_HOME** được đặt đúng:

~~~powershell
& "$env:JAVA8_HOME\bin\java.exe" -cp target\classes vn.example.target.LegacyApp
~~~

**Chỉ những lệnh chạy trên một Java 8 runtime thật mới xác nhận lớp main này hoạt động trên Java 8**. Ví dụ không cần dependency runtime bên thứ ba, nên classpath chỉ cần `target/classes`. Khi ứng dụng thật có dependencies, launcher phải cấp đúng runtime JARs và phải kiểm chứng từng dependency tương thích JVM đích.

## 8. Khi muốn nhắm Java 11, Java 17 hoặc Java 21

Nguyên tắc không thay đổi: cấu hình **`maven.compiler.release`** thành phiên bản Java thấp nhất mà sản phẩm **cam kết hỗ trợ** và bảo đảm JDK compiler đang dùng hỗ trợ release đó.

Ví dụ cho dự án yêu cầu **Java 17**:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Khi build bằng JDK 17 hoặc một JDK mới hơn còn hỗ trợ release 17, compiler giới hạn ngôn ngữ, bytecode và API nền tảng ở Java 17. Nếu mã sử dụng record, text block hay các tính năng Java 17 đã chuẩn hóa, chúng có thể hợp lệ; muốn dùng tính năng Java 21 thì cần release phù hợp.

Ví dụ cho **Java 11**:

~~~xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
~~~

Mã được phép dùng những API Java 11 như `String.isBlank()`, nhưng không được sử dụng API chỉ xuất hiện ở Java 17/21 trong quá trình biên dịch theo release 11.

**Không tự suy ra rằng `release=21` chạy được khi Maven đang dùng JDK 17**. Compiler JDK 17 không biết nền tảng Java 21, nên thường báo:

~~~text
error: release version 21 not supported
~~~

Đây là dấu hiệu `javac` được chọn **không hỗ trợ release yêu cầu**. Phải dùng JDK compiler 21 hoặc mới hơn còn hỗ trợ 21, có thể thông qua Maven Toolchains hoặc nâng JDK chạy Maven theo chính sách.

### Java 8 khác biệt về số phiên bản

Khi dùng javac hiện đại, đặt **`release=8`**, **`source=8`**, **`target=8`** theo cách tên phiên bản hiện đại; không dùng `release=1.8`. Một số công cụ và file cấu hình cũ có cú pháp `1.8` cho source/target nhưng Apache Maven khuyến nghị giá trị hiện đại `8` cho release. Với Java 9 trở lên, dùng số phát hành `9`, `11`, `17`, `21` như các ví dụ.

## 9. `release` không thay đổi JDK chạy Maven

Có thể xem ba vai trò khác nhau:

~~~text
JDK chạy Maven
  |
  +-- chạy Maven Core và plugin (cần đáp ứng version tối thiểu của chúng)
  |
  +-- Maven Compiler Plugin gọi javac
          |
          +-- javac được chọn (có thể là compiler của JDK khác qua toolchain)
          |
          +-- --release 8
                  |
                  +-- Java 8 syntax
                  +-- Java 8 class-file version
                  +-- Java 8 platform API signatures
~~~

Chỉ đặt property `maven.compiler.release=8` **không làm Maven hạ cấp JDK** về 8 và cũng không bắt Maven tải JDK 8.

Kiểm tra:

~~~bash
mvn --version
java -version
javac -version
~~~

Nếu kết quả khác nhau, có thể là vì `JAVA_HOME`, `PATH`, Maven Wrapper, IDE hoặc cấu hình Toolchains đang chọn runtime/compiler khác. **`mvn --version` quan trọng vì nó cho biết Java runtime mà Maven thực tế dùng**; `java -version` trong shell chỉ nói về lệnh java tìm được qua shell ở thời điểm đó.

### Toolchains: biên dịch bằng JDK khác JVM của Maven

Maven Toolchains cho phép một số plugin, gồm Compiler Plugin có hỗ trợ, **sử dụng JDK công cụ khác với JDK chạy Maven**. Ví dụ Maven Core và một số plugin chạy với JDK 17, nhưng Compiler Plugin được yêu cầu dùng JDK 21 để build `release=21`.

Điều này cần cấu hình toolchain và JDK được cài thật, không chỉ thêm một dòng `release`. Khi plugin không hỗ trợ hoặc chưa được cấu hình toolchain, nó có thể tiếp tục dùng Java của Maven. Một toolchain cũng **không tự khiến Surefire test chạy trên cùng JDK**; phải kiểm tra cấu hình test JVM và môi trường CI.

**Chọn công cụ giải quyết đúng vấn đề:**

- Muốn tạo class Java 8 bằng JDK 17: **`release=8`**.
- Muốn build feature Java 21 nhưng Maven đang chạy JDK 17: cần **compiler JDK 21**, qua Toolchains hoặc nâng runtime Maven phù hợp.
- Muốn xác nhận ứng dụng chạy trên Java 8: **thực thi ứng dụng/test trên Java 8**, không chỉ nhìn class major version.
- Muốn plugin chỉ hỗ trợ JDK 17 chạy được: Maven hoặc plugin runtime phải đáp ứng yêu cầu đó; `release=8` không giải quyết yêu cầu runtime của plugin.

## 10. Ngoại lệ JDK 8: plugin 3.13.0 có cơ chế fallback

**JDK 8 không có `javac --release`.** Trước khi hiểu rõ khả năng của plugin, dễ gặp nghịch lý: “Nếu phần mềm cần chạy trên Java 8, tại sao POM dùng `maven.compiler.release=8` lại không chạy khi build bằng JDK 8?”

Apache Maven Compiler Plugin đã giải quyết một phần khác biệt:

- Với **Compiler Plugin 3.13.0 trở lên** và compiler ID mặc định **`javac`**, khi build bằng **JDK 9+**, property `release` được dùng để đưa ra `--release` phù hợp.
- Khi build bằng **JDK 8**, plugin có thể chuyển property `release` sang source/target tương ứng, vì JDK 8 **không hỗ trợ `--release`**.
- Với **Compiler Plugin cũ hơn 3.13.0** hoặc compiler khác javac, có thể cần profile theo JDK để chỉ bật release khi javac hỗ trợ.

Ví dụ cấu hình dành cho trường hợp **có chủ đích hỗ trợ build bằng cả JDK 8 và JDK mới**:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>8</release>
                <source>8</source>
                <target>8</target>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây chỉ là **đoạn build/plugin** (không phải POM đầy đủ). Tài liệu Apache Maven nêu trường hợp này khi dùng Compiler Plugin 3.13.0+ mặc định. **Không dùng kết hợp ba tham số đó trong lệnh `javac` JDK 9+ trực tiếp**: javac không cho `--release` đi cùng `-source`/`-target`. Plugin điều phối tùy chọn phù hợp theo JDK đang chạy.

Nếu build bằng **JDK 8 thật** với source/target 8, compiler chỉ nhìn thấy API của JDK 8 đang được sử dụng; tuy không có `--release`, điều đó vẫn giúp tránh việc vô tình dùng API chuẩn Java 11. Nhưng dự án vẫn phải xác nhận dependency và plugin version có hỗ trợ JDK 8.

### Mẫu profile cho plugin cũ

Nếu buộc phải dùng Compiler Plugin cũ hơn 3.13.0 (hoặc compiler không phải javac), tài liệu Maven hướng dẫn cách bật release có điều kiện:

~~~xml
<profiles>
    <profile>
        <id>javac-release</id>
        <activation>
            <jdk>[9,)</jdk>
        </activation>
        <properties>
            <maven.compiler.release>8</maven.compiler.release>
        </properties>
    </profile>
</profiles>
~~~

Đây **chỉ là đoạn cấu hình minh họa**, phải phối hợp với `source/target=8` phù hợp trên JDK 8. Trong một hệ thống hiện đại, ưu tiên nâng compiler plugin tới phiên bản hỗ trợ và giảm điều kiện profile phức tạp nếu có thể.

## 11. Một dự án có thể dùng nhiều mức Java khác nhau không?

Các module trong cùng reactor có thể có **release khác nhau** nếu từng module có yêu cầu tương thích riêng, ví dụ:

~~~text
multi-module-build/
├── pom.xml                  quản lý plugin version
├── common-api/              release 8
├── service/                 release 17
└── application/             release 17
~~~

Điều này hợp lệ về mặt thiết kế khi dependency đi theo chiều tương thích. **Module release 8 không thể phụ thuộc vào thư viện đã biên dịch thành Java 17 class files nếu nó cần chạy trên Java 8.** Ngược lại, module Java 17 có thể dùng một thư viện Java 8 nếu API và dependencies phù hợp.

Maven có thể quản lý Compiler Plugin version tại parent:

~~~xml
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
~~~

Mỗi child có thể đặt `maven.compiler.release` phù hợp. Nhưng hãy tránh override release ở nhiều profile mà không ghi rõ điều kiện; CI và local có thể build ra class-file versions khác nhau.

**`pluginManagement` chỉ quản lý version/config mặc định**, không tự tạo mọi goal execution. Với packaging `jar`, Compiler Plugin thường đã được bind vào lifecycle compile/testCompile; plugin management có thể ảnh hưởng version khi plugin được dùng.

Để thấy cấu hình hiệu lực của **module đang xét**, chạy:

~~~bash
mvn -pl common-api help:effective-pom -Doutput=effective-common-pom.xml
mvn -pl service help:effective-pom -Doutput=effective-service-pom.xml
~~~

Các lệnh giả định reactor có module với tên hoặc path tương ứng. Không đọc một effective POM của parent rồi kết luận tất cả child đều có cùng release.

## 12. Release cho main sources và test sources

Maven Compiler Plugin có các goal khác nhau:

- **`compiler:compile`**: biên dịch `src/main/java` trong phase compile của packaging thích hợp.
- **`compiler:testCompile`**: biên dịch `src/test/java` trong phase test-compile.

Tùy plugin version, goal testCompile có thể dùng các property riêng như **`maven.compiler.testRelease`**, **`maven.compiler.testSource`**, **`maven.compiler.testTarget`** để override mức của test sources. Nếu không có override phù hợp, cấu hình chung từ compiler/plugin thường áp dụng theo cách plugin phiên bản đó định nghĩa.

Trong ví dụ mục 7, project đặt `maven.compiler.release=8`; mã chính và test đều chỉ sử dụng syntax Java 8 phù hợp. **JUnit 5.10.x hỗ trợ Java 8**, nên test source của ví dụ có thể biên dịch dưới Java 8 release, dù Surefire được chạy trên JVM mới hơn.

Trong thực tế có trường hợp **thư viện phát hành cho Java 8** nhưng test harness muốn dùng API Java 17. Khi đó có thể thiết kế riêng mức biên dịch test bằng `maven.compiler.testRelease=17` nếu Compiler Plugin đang dùng hỗ trợ và JDK compiler đủ mới. Tuy nhiên:

1. Test classes Java 17 **không chạy trên JVM 8**.
2. CI phải chạy test dưới JVM tương thích với test class versions.
3. Điều này không chứng minh artifact chính tương thích Java 8 nếu dependency runtime vẫn cần Java mới.
4. Khi tiêu chí phát hành là hỗ trợ Java 8, vẫn cần có bước test hoặc smoke test trên **Java 8 runtime thật**.

**Không dùng testRelease cao hơn để che lỗi chính**: mã trong `src/main/java` muốn hỗ trợ Java 8 phải được biên dịch nhắm Java 8 và chỉ dùng các API tương ứng.

## 13. Ba bẫy khác mà --release không tự giải quyết

### 13.1. Dependency bên thứ ba dùng bytecode cao hơn

Giả sử dự án `release=8` nhưng dependency `library-x.jar` được biên dịch với class major 61 (Java 17). Việc Maven chấp nhận dependency coordinates **không làm JAR đó tự tương thích Java 8**.

Lỗi có thể xuất hiện:

- Ngay khi compile nếu javac phải đọc class file quá mới so với compiler đang dùng.
- Khi chạy Java 8 nếu class của dependency được load, với `UnsupportedClassVersionError`.
- Khi thư viện bắc cầu bị thay version hoặc packaging chứa class mới hơn, dù source code của dự án không đổi.

Cần tra **minimum Java version** của dependency trong tài liệu chính thức/release notes, kiểm tra dependency tree và **test runtime trên JVM đích**. `--release` chủ yếu bảo vệ **việc dùng API nền tảng Java theo phiên bản**, không phải phép kiểm toán tương thích đầy đủ của mọi third-party JAR.

### 13.2. API của JDK khác với API bên thứ ba

`--release 8` kiểm tra API nền tảng Java 8 do javac cung cấp. Nó **không thể biết** một thư viện bên thứ ba bạn gọi có giữ tương thích nhị phân với một thư viện khác trong production hay không, hoặc một phương thức third-party chỉ tồn tại từ phiên bản lib mới.

Ví dụ `com.vendor.Library.newMethod()` có thể biên dịch nếu classpath có bản mới, nhưng runtime dùng bản cũ sẽ báo `NoSuchMethodError`. Đó là vấn đề **dependency version/binary compatibility**, cần kiểm thử graph runtime, không thể chỉ giải quyết bằng release.

### 13.3. Reflection, native libraries và môi trường chạy

Một ứng dụng có thể dùng reflection gọi API mới qua tên string, load service qua `ServiceLoader`, dùng JNI hoặc phụ thuộc native libraries. `--release` không phát hiện mọi hành vi dynamic như vậy.

Cần thực hiện **integration/smoke tests** trên runtime đích, nhất là nếu Java version hỗ trợ là một cam kết của sản phẩm. API compatibility ở compile time là điều kiện quan trọng nhưng không thay thế việc thử nghiệm môi trường thật.

### Multi-release JARs và Java Platform Module System

Một số dependency phát hành **multi-release JAR**, chứa class chọn theo phiên bản JVM dưới `META-INF/versions`. Cùng một JAR có thể cung cấp implementation khác nhau cho Java 8, 11, 17... nên việc đọc một class file hoặc nhìn một major version không phản ánh toàn bộ hành vi runtime. Kiểm tra tài liệu library và các test trên JVM được hỗ trợ.

Với JPMS/module-path của Java 9+, còn có quy tắc module resolution/export/open khác classpath truyền thống. Release kiểm soát API của nền tảng theo phiên bản, nhưng không tự sửa xung đột module-path của ứng dụng.

## 14. Lệnh Maven để kiểm tra cấu hình thực tế

### 14.1. Xác định JDK đang chạy Maven

~~~bash
mvn --version
~~~

Output thường cho biết Maven version, Java version và Java home. Đừng chỉ nhìn `java -version` vì Maven có thể được chạy từ IDE, wrapper hoặc script với `JAVA_HOME` khác.

### 14.2. Xem effective POM

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Trong file được sinh, tìm:

~~~xml
<maven.compiler.release>8</maven.compiler.release>
~~~

và Compiler Plugin version/configuration hiệu lực. Đây là **một dòng mẫu**, không phải toàn bộ effective POM. Nếu cấu hình được quản lý ở parent hoặc profile, effective POM cho biết module cuối cùng nhận giá trị nào.

**Không chỉnh file effective-pom sinh ra**; sửa POM nguồn/parent/profile thật sự định nghĩa lựa chọn. Nếu đang build multi-module, chạy lệnh trong đúng module hoặc dùng `-pl`/`-f` phù hợp.

### 14.3. Đánh giá property

~~~bash
mvn help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
~~~

Nếu POM mẫu đang dùng và Help Plugin hỗ trợ, output sẽ là:

~~~text
8
~~~

Có thể kiểm tra các property khác khi cần:

~~~bash
mvn help:evaluate -Dexpression=maven.compiler.source -q -DforceStdout
mvn help:evaluate -Dexpression=maven.compiler.target -q -DforceStdout
~~~

Nếu POM chỉ đặt `release`, source/target property **không bắt buộc phải hiện giá trị**; đó không phải lỗi. Mục tiêu là kiểm tra release hiệu lực và Compiler Plugin nhận được cấu hình đúng.

### 14.4. Đọc log compiler

~~~bash
mvn -B -ntp -X clean compile
~~~

Tìm dòng liên quan Compiler Plugin, release/source/target và các compiler arguments. Nội dung log thay đổi theo Maven/Compiler Plugin, cấu hình fork và compiler backend. **Không kỳ vọng mọi log phải in nguyên văn `javac --release 8`** nếu plugin dùng Java Compiler API nội bộ.

### 14.5. Xác minh class file

~~~bash
javap -verbose target/classes/vn/example/target/LegacyApp.class
~~~

**Major 52** chứng tỏ class file của ứng dụng được sinh theo Java 8 target. Một lớp khác có major khác có thể do module khác, generated source hoặc dependency được đóng gói ngoài dự kiến. Kiểm tra artifact đúng module và version build, không đọc nhầm file `.class` còn từ build cũ.

### 14.6. Thử runtime thực tế

Chạy ứng dụng trên Java đích, chạy test tích hợp và so sánh log. Nếu CI chỉ có JDK mới, dùng **CI matrix với JDK 8** (cho artifact đã biên dịch nhắm Java 8) hoặc một môi trường staging phù hợp. Không đưa artifact Java 8 vào production chỉ vì compiler log cho thấy `--release 8` mà không kiểm chứng dependencies.

## 15. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `release version 21 not supported` | javac đang dùng không hỗ trợ đích Java 21. | Dùng JDK compiler đủ mới và kiểm tra Maven Toolchains/`mvn --version`. |
| `invalid target release: 17` | Compiler không hỗ trợ target 17. | Kiểm tra JDK compiler thực, không chỉ property target. |
| `source release 17 requires target release 17` | source và target không tương thích. | Chọn bộ source/target hợp lệ hoặc dùng một `release`. |
| `record`/`var` không được chấp nhận | source đặt thấp hơn phiên bản tính năng ngôn ngữ. | Viết lại mã theo Java đích hoặc tăng release theo chính sách sản phẩm. |
| `cannot find symbol: isBlank()` với `--release 8` | API chỉ có từ Java 11. | Dùng API Java 8 hoặc tăng Java đích có chủ đích. |
| Build pass nhưng JVM Java 8 báo `NoSuchMethodError` | Dùng API mới vì chỉ đặt source/target, hoặc dependency version runtime khác. | Dùng `release`, kiểm tra runtime classpath, test trên Java 8. |
| JVM báo `UnsupportedClassVersionError` | Class file major cao hơn JVM hỗ trợ. | Biên dịch lại với release phù hợp và kiểm tra dependency bytecode. |
| Mã compile Java 8 nhưng test chỉ chạy được JDK 17 | Test framework/testRelease yêu cầu Java 17. | Tách test harness nhưng giữ smoke test Java 8 hoặc dùng test dependency phù hợp. |
| Cấu hình `source`/`target` và `release` bị conflict | `javac --release` không dùng kèm `-source/-target` trực tiếp. | Trên JDK 9+ ưu tiên release; ngoại lệ plugin 3.13.0 JDK 8 phải được hiểu đúng. |
| `--release` không được nhận biết | Đang gọi javac JDK 8 trực tiếp hoặc dùng compiler backend khác. | Dùng JDK 9+ hoặc fallback/source-target đúng môi trường và phiên bản plugin. |
| `maven.compiler.release=8` nhưng class major 61 | Module/profile không nhận config, build output cũ hoặc compiler khác. | `mvn clean compile`, effective POM, log Compiler Plugin, javap đúng class. |
| Maven Core/plugin không chạy trên JDK thấp | Runtime Maven/Plugin có yêu cầu Java riêng. | Nâng Java chạy Maven hoặc chọn plugin compatible; release không thay JVM Maven. |
| Thư viện thứ ba vẫn lỗi trên Java 8 | Dependency dùng major >52 hoặc API runtime mới. | Chọn version thư viện hỗ trợ Java 8 và kiểm tra trên Java 8 thật. |
| Maven Compiler Plugin tự dùng source/target không như mong đợi | Không pin plugin/config; default thay theo version. | Pin plugin version và đặt `maven.compiler.release` rõ ràng. |

Đừng sửa lỗi `UnsupportedClassVersionError` bằng cách đổi đại một `target` rồi bỏ qua những API/dependency đang dùng. Cần xác định **class nào lỗi**, major version nào, do module của bạn hay third-party JAR, và **JVM runtime thực tế**.

## 16. Ví dụ trước–sau cho một dự án cần hỗ trợ Java 8

### Trước: build bằng JDK 17 nhưng chỉ đặt source/target

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
~~~

Hậu quả: compiler có thể chấp nhận code dùng API Java 11 như `String.isBlank()`, tạo major 52, unit test trên JDK 17 vẫn pass. Production Java 8 gặp lỗi runtime.

### Sau: dùng release làm hợp đồng

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Khi biên dịch bằng JDK 17/Compiler Plugin phù hợp, gọi API Java 11 bị từ chối tại compile time. Đội không cần đưa bản lỗi tới môi trường Java 8 để phát hiện **lỗi API nền tảng** đó.

**Nhưng vẫn phải:**

1. Pin Maven Compiler Plugin version đã kiểm chứng.
2. Kiểm tra yêu cầu JDK tối thiểu của Maven/Compiler Plugin và các plugin khác.
3. Kiểm tra version/bytecode/API của các dependency runtime.
4. Chạy test/smoke test thực tế bằng JVM Java 8.
5. Đảm bảo packaging/launcher không chứa class của module khác được build nhắm Java cao hơn.

Đây mới là quy trình đảm bảo tương thích thực tế, thay vì coi `release` như công tắc “mọi thứ chắc chắn chạy trên Java 8”.

## 17. Checklist trước khi công bố hỗ trợ một Java target

1. **Xác định Java đích thấp nhất thật sự cần hỗ trợ**: Java 8, 11, 17 hay 21; không chọn theo JDK mới nhất trên máy developer.
2. **Chốt Maven/Compiler Plugin version**; kiểm tra plugin còn hỗ trợ JDK chạy Maven và release được chọn.
3. **Đặt `maven.compiler.release` tường minh**; tránh trông chờ defaults hoặc đặt source/target rời rạc trên JDK mới.
4. **Xem `mvn --version` và compiler runtime** để biết JDK nào đang thực hiện build.
5. **Xác nhận language features** được dùng trong `src/main/java` thuộc Java target; đừng dùng tính năng preview không được tính trong release mà không thiết kế riêng.
6. **Xác nhận Java platform API** qua `--release`: các API mới hơn Java đích phải bị compiler từ chối.
7. **Kiểm tra class major version** bằng `javap -verbose` hoặc công cụ tương đương trên artifact đúng module.
8. **Kiểm tra dependency trực tiếp và bắc cầu** về minimum Java version, class files và compatibility khi chạy.
9. **Đánh giá testRelease/test JVM**: test chạy bằng JVM nào, test dependencies có yêu cầu Java cao hơn không?
10. **Chạy build sạch**: `mvn clean verify` từ POM/branch/CI được quản lý.
11. **Chạy ứng dụng trên JVM thấp nhất được hỗ trợ** với đúng bản phân phối và runtime classpath.
12. **Kiểm tra multi-module/parent/profile** có module nào override release không được ghi trong tài liệu.
13. **Nếu dùng Toolchains**, đảm bảo compiler JDK thật sự được chọn và CI cài đúng toolchain.
14. **Khi nâng Java target**, ghi rõ thay đổi minimum runtime vào release notes và kiểm tra môi trường khách hàng còn phù hợp.
15. **Duy trì CI matrix** tối thiểu trên JDK build tiêu chuẩn và JVM Java thấp nhất mà sản phẩm cam kết chạy.

## 18. Bài tập thực hành

**Bài 1 — đo ba thuộc tính.** Trên JDK 17, biên dịch `Hello.java` với `-source 8 -target 8` và với `--release 8`, sau đó dùng `javap -verbose`. Giải thích vì sao cả hai có thể tạo major 52 nhưng không có cùng phạm vi kiểm soát API.

**Bài 2 — API mới trong bytecode cũ.** Biên dịch `NewApiProbe.java` dùng `String.isBlank()` bằng `-source 8 -target 8`; quan sát compiler có thể chấp nhận trên JDK 17. Tiếp theo dùng `--release 8`, xem lỗi compile. Nếu có Java 8 runtime, thử chạy bản bytecode cũ và phân biệt `NoSuchMethodError` với `UnsupportedClassVersionError`.

**Bài 3 — Maven POM và output.** Tạo project mục 7, chạy `mvn clean verify`. Chạy `LegacyApp` và đối chiếu stdout **Java 8 target OK: MAVEN, JAVA**; kiểm tra class major 52.

**Bài 4 — nâng Java đích.** Đổi `maven.compiler.release` từ 8 sang 11, thêm một lời gọi `String.isBlank()` trong module thử nghiệm. Giải thích vì sao bản Java 11 compile hợp lệ, nhưng không thể giữ cam kết Java 8 runtime.

**Bài 5 — JDK compiler thấp hơn đích.** Dùng một môi trường có javac 17, thử đặt `release=21` trong POM thử nghiệm và đọc lỗi. Xác định vì sao phải chọn compiler đủ mới, thay vì cố chỉnh Maven version hoặc thêm một dependency.

**Bài 6 — runtime dependency.** Thêm một thư viện bên thứ ba có minimum runtime Java cao hơn Java 8; tìm class major bằng javap và thử trên Java 8. Giải thích vì sao `--release 8` không tự biến dependency đó thành bytecode Java 8.

**Bài 7 — multi-module.** Thiết kế parent quản lý Compiler Plugin, module API nhắm Java 8 và module service nhắm Java 17. Kiểm tra từng effective POM và mô tả chiều phụ thuộc an toàn giữa hai module.

### Tổng kết

**`source` giới hạn cú pháp, `target` giới hạn định dạng `.class`, `release` kiểm soát cả cú pháp, class file và API nền tảng Java theo phiên bản đích.** Khi một project Maven cần chạy trên Java cũ nhưng được build bằng JDK mới, `maven.compiler.release` là lựa chọn được Apache Maven khuyến nghị.

Đừng đồng nhất “compiler chạy JDK 17”, “class major 52” và “ứng dụng chắc chắn chạy trên Java 8”. Muốn có cam kết tương thích thật, cần **cấu hình release đúng, kiểm tra dependency, dùng compiler/JDK phù hợp và chạy thử trên runtime Java thấp nhất được hỗ trợ**.

### Tài liệu chính thức

- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
- [Apache Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven Compiler Plugin — Setting the -source and -target of the Java Compiler](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html)
- [Apache Maven Compiler Plugin 3.13.0 — compiler:compile parameters](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html)
- [Apache Maven Compiler Plugin — Compile Using A Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html)
- [Apache Maven Toolchains — Guide](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Oracle Java 17 — javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java 17 — javap command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
