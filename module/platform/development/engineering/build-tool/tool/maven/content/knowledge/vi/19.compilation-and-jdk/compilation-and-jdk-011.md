# Module path, classpath và mô-đun Maven so với mô-đun JPMS

## 1. Vấn đề: cùng một chữ “module”, hai cơ chế khác nhau

Trong một dự án Java dùng Maven, từ **module** có thể chỉ hai thứ hoàn toàn khác nhau:

1. **Maven module**: một **Maven project/POM** được một aggregator liệt kê trong `<modules>` để Maven reactor xây dựng cùng các project khác. Nó có tọa độ `groupId:artifactId:version` và có thể phát hành một JAR, WAR hoặc artifact khác.
2. **JPMS module** (*Java Platform Module System*, Java 9+): một đơn vị **đóng gói và giới hạn truy cập Java**, thường có tệp `module-info.java` khai báo tên module, những module cần đọc (`requires`) và những package được công khai (`exports`). JVM và `javac` phân giải nó qua **module path** hoặc một cơ chế module phù hợp.

Hai kiểu module **có thể đi cùng nhau** nhưng không đồng nghĩa:

- Một reactor Maven gồm 5 module **không tự động** tạo ra 5 named modules JPMS.
- Một JAR được Maven build từ một project **không tự nhiên** là explicit named module; cần `module-info.class` hoặc dùng quy tắc automatic module khi JAR được đưa lên module path.
- `<module>greeter-lib</module>` trong parent POM là **đường dẫn thư mục project**. `module org.example.greeter { ... }` trong Java là **tên module do Java giải quyết**. Hai giá trị không bắt buộc giống nhau.
- `<dependency>` trong POM quyết định Maven giải quyết artifact nào và classpath/module path đầu vào có thể gồm JAR nào. `requires` trong `module-info.java` quyết định **module readability** của Java, không tự tải artifact từ Maven repository.
- `exports` không phát hành artifact lên Maven Central; nó quyết định **package nào có thể được dùng từ ngoài named module** khi chạy theo JPMS.

**Ghi nhớ nhanh:** Maven module giải quyết **build orchestration và artifact dependencies**; JPMS module giải quyết **đọc module, package visibility và strong encapsulation**; classpath/module path là **hai cách Java công cụ hóa việc tìm và nạp class/module**.

Mục tiêu bài này là làm rõ ranh giới đó, chỉ ra các điểm giao nhau và cung cấp một dự án **Java 17 + Maven đa module** có thể biên dịch, chạy theo JPMS và chạy lại theo classpath để so sánh.

## 2. Bảng đối chiếu trực tiếp

| Câu hỏi | Maven module/project | JPMS module |
| --- | --- | --- |
| Định nghĩa ở đâu? | Mỗi project có `pom.xml`; aggregator liệt kê đường dẫn trong `<modules>`. | `src/main/java/module-info.java`, được biên dịch thành `module-info.class`; hoặc automatic module dựa trên JAR ở module path. |
| Định danh? | Thường `groupId:artifactId:version`. | Tên module Java như `org.example.greeter`. |
| Ai xử lý? | Maven model builder, dependency resolver và reactor. | `javac`, `java`, JPMS resolver và Java module system. |
| Đường quan hệ? | `<dependencies>` với coordinates/scope/version; reactor lấy graph để sắp build. | `requires`, `requires transitive`, `requires static`; module readability. |
| Chia sẻ API? | JAR/classes do project xuất bản, không tự kiểm soát package visibility theo JPMS. | `exports package.name` (truy cập công khai), `opens` cho deep reflection, `uses`/`provides` cho service binding. |
| Cấu hình đầu vào? | Maven dependency graph cho compile/test/runtime. | `--module-path` và module graph, hoặc `--class-path` cho legacy. |
| Có bắt buộc dùng cái còn lại không? | Không; Maven build app Java 8 hoặc Java 17 non-modular rất bình thường. | Không; có thể build JPMS bằng `javac`/`jar` thuần hoặc build tool khác Maven. |
| Có quyết định tự động thứ tự build không? | Reactor sắp theo các project dependency thực tế, plugin/build-extension relations... | JPMS `requires` **không tự làm Maven reactor** hiểu Maven coordinates nếu POM thiếu dependency. |
| Có chạy được bằng tên Java module? | Không chỉ vì nằm trong aggregator. | Named module có thể được chạy bằng `java --module-path ... --module name/mainClass`. |
| Có tương đương thư mục source package không? | Không; một module Maven thường chứa nhiều Java packages. | Cũng không; một JPMS module có thể chứa nhiều packages và export một phần. |

Sự trùng lặp về tên trong thực tế chỉ là **quy ước**, không phải phép biến đổi tự động. Bạn có thể đặt artifactId `greeter-lib`, còn JPMS module tên `org.example.greeter`.

## 3. Maven multi-module: reactor, parent và project dependency

Cấu trúc Maven thường gặp:

~~~text
root/
├── pom.xml                    # aggregator, có <modules>
├── greeter-lib/
│   └── pom.xml                # Maven project riêng
└── greeter-cli/
    └── pom.xml                # Maven project riêng
~~~

Ví dụ mảnh parent/aggregator:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>greeter-lib</module>
    <module>greeter-cli</module>
</modules>
~~~

Phần tử `<module>greeter-lib</module>` là **đường dẫn tương đối tới project con**, không phải tên JPMS và cũng không phải Java import.

Nếu `greeter-cli` sử dụng class từ `greeter-lib`, POM `greeter-cli` phải khai báo project dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.training</groupId>
        <artifactId>greeter-lib</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Maven reactor nhìn vào dependency thật này để build thư viện trước ứng dụng. Nếu chỉ có `<modules>` mà thiếu dependency, việc hai module cùng reactor **không tự đưa class của greeter-lib lên compiler classpath/module path của greeter-cli**.

**Parent và aggregator cũng là hai vai trò khác nhau:**

- `<parent>` trong POM con dùng để **kế thừa** properties, plugin management, dependency management...
- `<modules>` trong POM aggregator dùng để **gom nhiều project vào một lần build**.
- Một POM có thể vừa là parent vừa là aggregator, nhưng hai khái niệm không đồng nhất.
- `<dependencyManagement>` quản lý phiên bản, không tự tạo quan hệ dependency giữa hai project và không làm reactor sắp xếp theo một entry chỉ nằm trong management.

Điều này độc lập với JPMS: dự án Maven vẫn có thể gồm nhiều project con hoàn toàn không có `module-info.java`.

## 4. JPMS module: module-info.java là hợp đồng của Java

Một explicit named module thường có mô tả:

~~~java
module org.example.greeter {
    exports org.example.greeter;
}
~~~

Tệp phải nằm tại `src/main/java/module-info.java` của project modular tương ứng. Sau khi biên dịch, `module-info.class` nằm trong output và JAR modular.

Những chỉ thị chính của `module-info.java`:

| Chỉ thị | Ý nghĩa cốt lõi |
| --- | --- |
| `module name { ... }` | Khai báo **tên named module**. |
| `requires other.module;` | Module đang khai báo **đọc** một named module khác. |
| `requires transitive other.module;` | Ngoài việc đọc module khác, còn cho phép module đọc mình **đọc bắc cầu** module kia. Hữu ích khi API public trả về kiểu thuộc module kia. |
| `requires static other.module;` | Module được yêu cầu lúc **compile**, nhưng không bắt buộc tồn tại ở runtime; phù hợp dependency tùy chọn có chủ đích, không tự điều chỉnh Maven scope. |
| `exports some.package;` | Cho module khác truy cập **public types** của package, theo quy tắc JPMS. |
| `exports some.package to a,b;` | Export **có giới hạn** cho những named modules được nêu. |
| `opens some.package;` | Cho phép **deep reflection** runtime trên package; khác `exports`. |
| `opens some.package to framework.module;` | Mở reflection có giới hạn; thường gặp ở framework/test. |
| `uses service.Type;` | Khai báo việc dùng Java ServiceLoader service. |
| `provides service.Type with impl.Provider;` | Khai báo implementation/provider cho service. |
| `open module name { ... }` | Mở reflection trên tất cả package của module; là lựa chọn rộng, nên cân nhắc rủi ro encapsulation. |

Java `public class` **không tự đồng nghĩa** public đối với mọi named module. Nếu class nằm trong package không export, named module bên ngoài thường không thể import package đó dù có JAR và `requires`.

**`java.base`** được mọi named module đọc một cách ngầm định: bạn không phải viết `requires java.base;` chỉ để dùng `String`, `List`, `System`. Nhưng khi dùng các JDK modules khác, chẳng hạn `java.sql`, `java.net.http`, thường phải khai báo `requires java.sql;` hoặc `requires java.net.http;` tương ứng.

## 5. Classpath: kiểu truy cập truyền thống của Java

**Classpath** là tập các thư mục/JAR mà Java launcher và compiler dùng để tìm class khi chạy code ở **unnamed module**. Các tham số thường gặp:

~~~bash
javac --class-path "lib/a.jar:lib/b.jar" -d target/classes src/main/java/org/example/App.java
java --class-path "target/classes:lib/a.jar:lib/b.jar" org.example.App
~~~

Đây là **mẫu lệnh Unix minh họa**, không phải lời cam kết project App/những JAR ở đường dẫn đó đã tồn tại. Trên Windows, dấu phân cách các classpath entries là `;` thay vì `:`.

Tên gọi tương đương:

- `-cp`, `-classpath` và `--class-path` cho Java launcher; `javac` có các option tương đương phù hợp.
- Thư mục classpath được tìm theo đường dẫn package/class.
- Các JAR/module descriptors được đặt trên **classpath** nhìn chung tham gia **unnamed module** của classloader tương ứng; `module-info.class` trong JAR **không biến chúng thành named module** khi chúng chỉ được tải từ classpath.
- Unnamed module có cách đọc rộng hơn và không bị các `exports` của chính nó hạn chế theo cách explicit named modules.
- Classpath không dùng `requires`/module name để phân giải quan hệ; sự hiện diện của class và xung đột JAR phụ thuộc các đường dẫn, classloaders và thứ tự tìm kiếm.

Classpath vẫn được Java 17 hỗ trợ. **Không cần chuyển mọi ứng dụng Java sang JPMS** chỉ vì đang dùng Maven hoặc JDK 17.

Lỗi runtime thường gặp:

~~~text
java.lang.NoClassDefFoundError
java.lang.ClassNotFoundException
~~~

Chúng có thể xuất hiện vì **lệnh `java` không có runtime JAR cần thiết** dù Maven compiler đã có dependency ở compile time. Maven dependency declaration không tự làm một lệnh `java -cp target/classes ...` nhận mọi JAR từ `~/.m2/repository`.

## 6. Module path: JVM phân giải các named modules

**Module path** là tập vị trí (JAR hoặc thư mục phù hợp) mà Java module system dùng để tìm các **observable modules**. Tham số:

~~~bash
java --module-path "libs/a.jar:libs/b.jar" --module com.example.app/com.example.app.Main
~~~

Đây là cú pháp minh họa cho Linux/macOS. Trên Windows, dùng dấu `;` để phân cách các phần tử module path.

Trong ví dụ, `--module com.example.app/com.example.app.Main` có nghĩa:

- `com.example.app`: tên JPMS module được chọn làm entry module.
- `com.example.app.Main`: fully qualified class chứa `public static void main(String[] args)`.

`-p` là dạng rút gọn của `--module-path`, còn `-m` là dạng rút gọn của `--module`.

Cơ chế module path khác classpath:

1. Java quan sát các module có thể tìm thấy trên module path.
2. JVM/Javac tạo **module graph** từ entry modules và các quan hệ `requires`.
3. Để mã ở module A dùng public type ở module B, thường cần **A đọc B** và **B exports package chứa type đó cho A**.
4. Với reflection sâu, ngoài readability/public access có thể còn cần `opens` hoặc cấu hình JPMS tương ứng.
5. Không phải **mọi JAR xuất hiện trên module path** đều được tự thêm vào graph runtime; điều này phụ thuộc root modules, `requires`, `--add-modules` và các quy tắc phân giải.
6. Không phải một dependency Maven có mặt ở repository là đủ cho `java -m`: runtime command phải cung cấp đúng module path hoặc một packaging/launcher tạo module path phù hợp.

**Module path không phải “classpath với tên khác”.** Nó dẫn đến kiểm tra mạnh hơn về dependency, readability, exports, duplicate module names và split packages.

## 7. Hai đồ thị độc lập nhưng phải nhất quán

Một Java project Maven modular có hai đồ thị liên quan:

~~~text
MAVEN GRAPH
  org.example.training:greeter-cli:1.0.0
        |
        +-- org.example.training:greeter-lib:1.0.0
              |
              +-- (dependency khác nếu có)

JPMS GRAPH
  module org.example.cli
        |
        +-- requires org.example.greeter
              |
              +-- java.base (ngầm định)
~~~

Ánh xạ ở ví dụ:

| Thành phần | Maven coordinates | JPMS name |
| --- | --- | --- |
| Thư viện | `org.example.training:greeter-lib:1.0.0` | `org.example.greeter` |
| Ứng dụng | `org.example.training:greeter-cli:1.0.0` | `org.example.cli` |
| Parent aggregator | `org.example.training:jpms-parent:1.0.0` | **Không có JPMS module** nếu chỉ là parent POM và không có Java module descriptor. |

Muốn app dùng Greeter:

- **Maven phải biết thư viện** qua child POM `<dependency>` để resolve artifact cho compiler/build.
- **JPMS phải biết quan hệ đọc** qua `requires org.example.greeter;`.
- **Library phải công khai package** qua `exports org.example.greeter;`.
- **Module path runtime phải chứa/quan sát được thư viện** để JVM resolve module tại lúc khởi chạy.

Thiếu một mắt xích có thể tạo lỗi riêng biệt. Nhớ rằng Maven `<dependency>` và Java `requires` **không tự sinh ra nhau**.

## 8. Ví dụ chạy được: Maven 3 multi-module + Java 17 JPMS

Ta xây dựng **hai Maven child projects**, mỗi child cung cấp **một explicit named JPMS module**. Parent vừa là aggregator vừa là parent chung.

Môi trường: **JDK 17+** và Maven 3.9.x. Ví dụ dùng Maven Compiler Plugin `3.13.0` và Maven JAR Plugin `3.4.2`, hai phiên bản cụ thể để bài không lệ thuộc plugin version ngẫu nhiên. Maven Compiler Plugin 3.13.0 có tham số `useModulePath`: với release/target 9+ và `module-info.java`, mặc định true cho phép compiler dùng module path theo cơ chế plugin. Ta ghi rõ giá trị này để người học dễ quan sát.

Cây thư mục hoàn chỉnh:

~~~text
jpms-vs-maven/
├── pom.xml
├── greeter-lib/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── org/example/greeter/Greeter.java
└── greeter-cli/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── org/example/cli/Main.java
~~~

**Lưu ý:** `greeter-lib` và `greeter-cli` là **tên thư mục/Maven modules**; JPMS module names nằm **trong hai tệp module-info.java**. Dự án này không dùng thư viện bên ngoài JDK cho mã Java, giúp kiểm tra cơ chế JPMS thuần túy.

### 8.1. Parent POM: jpms-vs-maven/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>jpms-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>greeter-lib</module>
        <module>greeter-cli</module>
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
                    <configuration>
                        <release>17</release>
                        <useModulePath>true</useModulePath>
                    </configuration>
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

Vì packaging của parent là `pom`, parent không tự sản sinh Java module hay `jpms-parent.jar`. Parent/aggregator này:

- Liệt kê **hai Maven modules** qua `<modules>`.
- Cung cấp Java release và encoding chung.
- Pin plugin versions; `pluginManagement` được áp dụng khi compiler/jar plugin được dùng bởi lifecycle `jar` của child. Bản thân `pluginManagement` không có nghĩa chạy mọi goal ở parent.
- **Không** chứa `module-info.java`; do đó **không** có named JPMS module `jpms-parent`.

### 8.2. Library child POM: greeter-lib/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.training</groupId>
        <artifactId>jpms-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeter-lib</artifactId>
</project>
~~~

Không khai báo `groupId` và `version` riêng vì chúng được kế thừa từ parent. Packaging mặc định là `jar`.

Tệp này **không cần** `<dependencies>` vì library chỉ dùng JDK trong ví dụ. Project vẫn là Maven module do aggregator liệt kê và có thể được build độc lập sau khi parent POM có thể resolve.

### 8.3. Library JPMS descriptor: greeter-lib/src/main/java/module-info.java

~~~java
module org.example.greeter {
    exports org.example.greeter;
}
~~~

Tên `org.example.greeter` **khác artifactId `greeter-lib`**. Lệnh `java -m` và chỉ thị `requires` về sau dùng **JPMS name**, không dùng artifactId.

`exports org.example.greeter` cho phép các **named modules khác** đọc package công khai khi chúng có `requires org.example.greeter;`. Nếu bỏ `exports`, class có thể vẫn public trong Java nhưng bị JPMS chặn khi module bên ngoài dùng theo module path.

### 8.4. Library source: greeter-lib/src/main/java/org/example/greeter/Greeter.java

~~~java
package org.example.greeter;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        String cleaned = (name == null || name.isBlank())
                ? "guest"
                : name.strip();
        return "Hello, " + cleaned + "!";
    }
}
~~~

Mã Java 17 hợp lệ:

- `String.isBlank()` kiểm tra chuỗi chỉ chứa whitespace.
- `String.strip()` loại whitespace đầu/cuối chuỗi.
- `greet(" JPMS ")` trả `Hello, JPMS!`.
- `greet("   ")` trả `Hello, guest!`.

Cả package và đường dẫn file đều khớp. Class `Greeter` là `public`, nằm trong package **được export** bởi module descriptor, nên có thể được dùng từ module `org.example.cli`.

### 8.5. CLI child POM: greeter-cli/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.training</groupId>
        <artifactId>jpms-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeter-cli</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.example.training</groupId>
            <artifactId>greeter-lib</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Ở đây, `greeter-cli` thực sự có Maven dependency vào `greeter-lib`. Vì cả hai project nằm trong reactor, Maven có thể sắp `greeter-lib` build trước `greeter-cli`. Không cần chạy `mvn install` riêng nếu build toàn reactor từ root.

`artifactId` vẫn là `greeter-cli`, khác tên JPMS module `org.example.cli`.

### 8.6. CLI JPMS descriptor: greeter-cli/src/main/java/module-info.java

~~~java
module org.example.cli {
    requires org.example.greeter;
}
~~~

`requires org.example.greeter` làm CLI module **đọc named module** của library. Nó **không** tự tìm Maven artifact `greeter-lib`; khả năng tìm library đến từ Maven dependency resolution/module path.

CLI **không cần** `exports org.example.cli;` chỉ để Java launcher chạy `Main` của chính module. Export dành cho những module **khác** dùng public API của package. Ở bài mẫu, CLI không cung cấp API công khai cho module khác.

### 8.7. CLI source: greeter-cli/src/main/java/org/example/cli/Main.java

~~~java
package org.example.cli;

import org.example.greeter.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet(" JPMS "));
        System.out.println(Greeter.greet("   "));
        System.out.println("cli.module=" + Main.class.getModule().getName());
        System.out.println("lib.module=" + Greeter.class.getModule().getName());
    }
}
~~~

Mã này thể hiện cả **API call** lẫn **JPMS runtime identity**:

- `Greeter` nằm trong module `org.example.greeter`.
- `Main` nằm trong module `org.example.cli` khi chạy qua module path như mục 9.
- `Class.getModule().getName()` trả tên module nếu class thuộc named module; trả `null` khi class thuộc unnamed module. Ở hai chế độ chạy khác nhau, phần output module name sẽ thay đổi.

Không dùng reflection không cần thiết, external dependency, test provider hoặc `--add-opens`; vì vậy ví dụ không phụ thuộc vào cấu hình Surefire/JPMS test phức tạp.

## 9. Build và chạy bằng module path: stdout chính xác

### 9.1. Build toàn Maven reactor

Từ thư mục `jpms-vs-maven/` chứa parent `pom.xml`, chạy:

~~~bash
mvn -B -ntp clean package
~~~

Maven lần lượt xử lý parent, `greeter-lib` rồi `greeter-cli` theo quan hệ project dependency. Với JDK 17+, Maven tương thích và repository/plugin resolution thành công, compiler tạo `module-info.class` trong mỗi output.

Các output chính:

~~~text
greeter-lib/target/
├── classes/
│   ├── module-info.class
│   └── org/example/greeter/Greeter.class
└── greeter-lib-1.0.0.jar

greeter-cli/target/
├── classes/
│   ├── module-info.class
│   └── org/example/cli/Main.class
└── greeter-cli-1.0.0.jar
~~~

Đây là cây **rút gọn**; Maven có thể tạo thêm metadata, output status, logs khác. Không giả định toàn bộ log `mvn` là cố định. Cả hai JAR do JAR Plugin đóng gói sẽ có module descriptors nếu compile thành công.

### 9.2. Chạy Java 17 với named modules trên Linux/macOS

Ngay tại thư mục root của project sau build:

~~~bash
java --module-path "greeter-lib/target/greeter-lib-1.0.0.jar:greeter-cli/target/greeter-cli-1.0.0.jar" --module org.example.cli/org.example.cli.Main
~~~

**Stdout chính xác của riêng lệnh `java`**, với đúng các file của bài mẫu:

~~~text
Hello, JPMS!
Hello, guest!
cli.module=org.example.cli
lib.module=org.example.greeter
~~~

Trong lệnh:

- `--module-path` chứa **hai modular JARs**.
- `org.example.cli` là tên module CLI, không phải Maven artifactId `greeter-cli`.
- `org.example.cli.Main` là class có method `main`.
- Module descriptor CLI yêu cầu module `org.example.greeter`; module descriptor library export package để CLI import được `Greeter`.

### 9.3. Chạy trên Windows PowerShell/CMD

Tại root của project, khác biệt chính là dấu phân cách module path:

~~~powershell
java --module-path "greeter-lib\target\greeter-lib-1.0.0.jar;greeter-cli\target\greeter-cli-1.0.0.jar" --module org.example.cli/org.example.cli.Main
~~~

Kết quả Java được mong đợi **giống hệt bốn dòng stdout** ở mục 9.2. Dấu `;` trên Windows là phân cách path entries, không phải tên module hoặc cách ngăn Maven projects.

Có thể viết ngắn:

~~~bash
java -p "greeter-lib/target/greeter-lib-1.0.0.jar:greeter-cli/target/greeter-cli-1.0.0.jar" -m org.example.cli/org.example.cli.Main
~~~

Mẫu rút gọn trên là cho Unix. Chỉ nên dùng nếu shell và đường dẫn chính xác.

## 10. Cùng hai JAR, thử chạy bằng classpath để so sánh

Một điểm rất hữu ích: **cùng hai JAR đã đóng gói** có thể được đưa lên **classpath** thay vì module path. Trong chế độ này, `module-info.class` bên trong JAR **không khiến các class thuộc explicit named modules**; các class do application classloader tải từ classpath thuộc unnamed module.

Trên Linux/macOS:

~~~bash
java --class-path "greeter-lib/target/greeter-lib-1.0.0.jar:greeter-cli/target/greeter-cli-1.0.0.jar" org.example.cli.Main
~~~

Với đúng code mẫu, stdout riêng của lệnh Java sẽ là:

~~~text
Hello, JPMS!
Hello, guest!
cli.module=null
lib.module=null
~~~

**Vì sao?** `Main.class.getModule().getName()` và `Greeter.class.getModule().getName()` trả `null` khi hai class thuộc unnamed module. JVM chạy theo classpath truyền thống; các ràng buộc `requires`/`exports` của hai descriptor không được áp dụng như trong module path execution.

Trên Windows:

~~~powershell
java --class-path "greeter-lib\target\greeter-lib-1.0.0.jar;greeter-cli\target\greeter-cli-1.0.0.jar" org.example.cli.Main
~~~

Output cũng gồm bốn dòng, với `cli.module=null` và `lib.module=null`.

**So sánh trọng tâm:**

| Cách chạy | Cách chọn main | Module.getName() | JPMS descriptors được dùng để dựng named module graph? |
| --- | --- | --- | --- |
| `java -p ... -m org.example.cli/org.example.cli.Main` | Tên JPMS module + main class | `org.example.cli` / `org.example.greeter` | Có |
| `java -cp ... org.example.cli.Main` | Fully qualified main class | `null` / `null` | Không; classpath classes ở unnamed module |

Điều này cho thấy **không phải Maven artifactId hoặc sự hiện diện của `module-info.class` trong JAR một mình quyết định chế độ runtime**. **Cách JVM nạp artifact** mới quyết định JAR được đối xử như named module hay legacy classpath code.

## 11. Kiểm tra một JAR thật sự có module descriptor

JDK cung cấp lệnh `jar`:

~~~bash
jar --describe-module --file greeter-lib/target/greeter-lib-1.0.0.jar
jar --describe-module --file greeter-cli/target/greeter-cli-1.0.0.jar
~~~

Lệnh không cần chạy chương trình. Trong phần mô tả:

- Library có module name `org.example.greeter` và `exports org.example.greeter`.
- CLI có module name `org.example.cli` và `requires org.example.greeter`.
- `java.base` có thể được hiển thị như quan hệ bắt buộc/mandated vì mọi module đều đọc module nền tảng.
- Exact formatting/ordering của output phụ thuộc phiên bản JDK, nên **không gán một stdout đầy đủ cố định** cho lệnh `jar --describe-module`.

Lệnh kiểm tra nhanh file trong JAR:

~~~bash
jar --list --file greeter-lib/target/greeter-lib-1.0.0.jar
~~~

Trong danh sách phải có `module-info.class` cùng `org/example/greeter/Greeter.class` nếu build mẫu thành công.

Dùng `jdeps` nếu cần phân tích dependency thực tế ở cấp bytecode/module graph:

~~~bash
jdeps --module-path "greeter-lib/target/greeter-lib-1.0.0.jar" --describe-module greeter-cli/target/greeter-cli-1.0.0.jar
~~~

**Lệnh `jdeps` trên chỉ mang tính gợi ý**: các option hiện hành cần kiểm tra bằng `jdeps --help` trên JDK của bạn vì goal phân tích module dependencies và goal mô tả module không phải lúc nào giống thao tác `jar --describe-module`. Trong quy trình thực hành, hai lệnh `jar --describe-module` phía trên đã đủ để xác minh tệp chứa module descriptor đúng mà không phụ thuộc vào tùy chọn `jdeps`.

## 12. Maven project dependency và JPMS requires: hai điều kiện đều cần

Có bốn trường hợp quan trọng khi module CLI muốn dùng `Greeter`:

| POM CLI có dependency `greeter-lib`? | `module-info.java` CLI có `requires org.example.greeter;`? | Hệ quả khi biên dịch theo JPMS |
| --- | --- | --- |
| Có | Có | Đúng hướng; còn cần thư viện export package và module path phù hợp. |
| **Không** | Có | Maven không tự lấy/build thư viện theo Maven dependency, compiler có thể báo `module not found: org.example.greeter`. |
| Có | **Không** | JAR có thể được resolve nhưng module CLI **không đọc** JPMS module Greeter; compiler có thể báo package không visible. |
| Không | Không | Không có artifact cũng không có JPMS readability; import không hợp lệ trừ khi thay kiến trúc/cấu hình. |

### Thử sai số 1: xóa Maven dependency, giữ requires

Trong `greeter-cli/pom.xml`, thử bỏ `<dependency>` Greeter và vẫn giữ:

~~~java
module org.example.cli {
    requires org.example.greeter;
}
~~~

Compiler không tự đoán `org.example.greeter` phải lấy từ tọa độ Maven `org.example.training:greeter-lib:1.0.0`. Ngay cả khi parent có `<module>greeter-lib</module>`, không có bảo đảm thư viện được đưa vào compile module path của CLI. Maven cần **dependency declaration** phù hợp.

### Thử sai số 2: giữ Maven dependency, bỏ requires

Trong `greeter-cli/src/main/java/module-info.java`, bỏ `requires org.example.greeter;`:

~~~java
module org.example.cli {
}
~~~

Khi compiler dùng JPMS module path, nó không thể cho code CLI truy cập package của module Greeter nếu module CLI không đọc Greeter. Maven đã resolve JAR **không thay thế JPMS readability**.

### Thử sai số 3: giữ requires, bỏ exports

Trong descriptor library, đổi thành:

~~~java
module org.example.greeter {
}
~~~

Dù CLI yêu cầu library và Maven đã resolve đúng artifact, package `org.example.greeter` **không được export**, nên mã CLI không thể truy cập `Greeter` như API public từ named module khác.

**Lưu ý:** Đây đều là các **thay đổi cố tình làm hỏng** POM/source để học cách đọc lỗi. Không đưa chúng vào project runnable cuối cùng. Exact compiler diagnostic có thể thay đổi theo JDK/plugin version; hãy xem mục “module không đọc” và “package không được export” trong log, không học thuộc từng dấu câu của lỗi.

## 13. Maven Compiler Plugin và useModulePath

Maven Compiler Plugin nhận project compile dependencies từ Maven và truyền chúng cho compiler. Với Maven Compiler Plugin `3.13.0`, có tham số:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <useModulePath>true</useModulePath>
    </configuration>
</plugin>
~~~

Đây là **mảnh plugin config**; trong POM ví dụ, nó đã nằm trong parent `pluginManagement`. Tài liệu plugin `compiler:compile` của phiên bản 3.13.0 mô tả `useModulePath=true` (mặc định): khi release/target 9+ và có `module-info.java` hoặc `module-info.class`, plugin sử dụng module path.

- `<release>17</release>` tương đương mục tiêu `javac --release 17` về ngôn ngữ/API JDK target. Nó **không tự cài JDK 17** hay đổi JDK đang chạy Maven; xem `mvn --version`/toolchains.
- `useModulePath=true` là **cấu hình compile plugin**, không phải Maven CLI tự biến mọi dependency thành JPMS module.
- Với project không có module descriptor, compile thường dùng project classpath như ứng dụng non-modular.
- Với project modular, compiler/Javac còn xét đúng `requires`, `exports`, module names và split packages.
- `useModulePath=false` có thể ép compiler dùng classpath, nhưng không phải lời giải đúng cho mọi lỗi JPMS. Nếu source vẫn có `module-info.java`, việc tắt module path có thể khiến compiler không tìm thấy named modules hoặc tạo setup không hợp lệ. Không dùng nó như cách “bỏ qua modularity” mà không hiểu hệ quả.
- Maven 4 và Compiler Plugin 4.x có thay đổi đáng kể về modeling/dep types; bài dùng **Maven 3 + Compiler Plugin 3.13.0** để ví dụ cụ thể, không gộp hướng dẫn của các thế hệ plugin.

Kiểm tra JDK thực tế Maven sử dụng:

~~~bash
mvn --version
java --version
javac --version
~~~

Đối chiếu `JAVA_HOME`/Maven toolchains nếu Maven và terminal chạy JDK khác nhau.

## 14. Test với Surefire khi có module-info.java

Nếu dự án có `src/test/java` và dùng Maven Surefire Plugin, phải phân biệt **test compiler classpath/module path** và **test execution runtime của Surefire**.

Surefire có tùy chọn `useModulePath`: với JDK 9+ và có `module-info.java`, mặc định `true` ở những phiên bản Surefire hỗ trợ; `false` yêu cầu chế độ classpath cho thực thi test. Cấu hình minh họa:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <useModulePath>true</useModulePath>
    </configuration>
</plugin>
~~~

Đây **không phải plugin bắt buộc** cho dự án mẫu hiện tại vì mẫu không có source test. Nếu thêm JUnit 5 hoặc Mockito:

1. Module có test phải khai báo JUnit hoặc framework tương ứng trong **project dependencies scope test**.
2. Test compiler cần nhìn thấy API test.
3. Test runtime cần module accessibility, có thể sử dụng module patching, mở package cho framework hoặc các option tương ứng.
4. Reflection sâu trên test classes/private members có thể cần `opens` hay `--add-opens` theo framework/runtime.
5. Cần xác định test là test source trong **cùng JPMS module**, một test JPMS module riêng hay kiểm thử trên classpath. Ba cách có cấu hình khác nhau.
6. `useModulePath=false` ở Surefire chỉ ảnh hưởng cách plugin dựng runtime test; nó không có nghĩa thay đổi toàn bộ compile-phase module descriptors.
7. Tùy phiên bản plugin/JDK, Surefire có hỗ trợ tự động `--patch-module` hoặc các điều chỉnh classpath cho test; dùng tài liệu plugin version tương ứng thay vì tự thêm mọi `--add-opens`.

Vì test modularity có các chi tiết riêng, **dự án chính ở mục 8–10 cố tình không có JUnit/test module**; khi build bằng `clean package`, không có ca test cần test runtime/JPMS reflection. Đây là lựa chọn để ví dụ runnable và stdout kiểm chứng đơn giản, không có nghĩa Maven không hỗ trợ JPMS tests.

## 15. Explicit, automatic và unnamed modules: ba trường hợp cần phân biệt

### 15.1. Explicit named module

Có `module-info.class` mô tả tên, `requires`/`exports`; đặt lên module path sẽ tham gia JPMS graph theo descriptor.

Ví dụ `greeter-lib-1.0.0.jar` của bài, với `module-info.class` tại JAR root. `java -p ... -m ...` chạy theo semantics JPMS.

### 15.2. Automatic named module

Một **JAR không có `module-info.class`** nhưng được đưa lên **module path** có thể trở thành **automatic named module**:

- Nếu manifest có `Automatic-Module-Name`, JVM dùng tên đó.
- Nếu không có, JVM suy tên từ filename theo quy tắc định danh module.
- Automatic module export/open tất cả packages, đồng thời có khả năng đọc rộng để hỗ trợ chuyển đổi ứng dụng legacy.
- Tên suy từ filename có thể thay đổi khi artifact rename/versioning/package convention thay đổi, vì vậy **không nên đoán** name.
- Dùng `jar --describe-module --file legacy-library.jar` để biết JVM nhận diện tên gì; nếu không có descriptor, công cụ có thể hiển thị dạng automatic module.

Maven coordinates **không phải nguồn tên automatic module bắt buộc**. Artifact `groupId:artifactId` và tên JPMS automatic là những khái niệm khác nhau.

### 15.3. Unnamed module

Code được nạp từ **classpath** thuộc unnamed module của classloader tương ứng, không có tên JPMS; `Class.getModule().getName()` trả `null`. Trong ví dụ, cùng `Greeter` và `Main` xuất hiện là unnamed khi chạy `java -cp ...`.

**Named explicit module không thể đơn giản ghi `requires unnamed;`** vì unnamed module không có tên để chỉ định trong `module-info.java`. Đây là một khó khăn phổ biến khi chuyển project đã dùng nhiều legacy JAR sang JPMS; hãy kiểm tra whether dependency có thể được đưa lên module path như automatic module hay cần thay đổi cấu trúc packaging. Các escape hatches `--add-reads` tồn tại nhưng nên dùng có kiểm soát.

## 16. exports, opens và strong encapsulation

Hai chỉ thị dễ nhầm:

~~~java
module org.example.greeter {
    exports org.example.greeter;
}
~~~

`exports` cho module bên ngoài sử dụng **public types** của package (khi có readability). Nó không cho deep reflection vào private members như một quyền mặc định.

Trong ứng dụng có framework dùng reflection (serialization, dependency injection, ORM, test engine), có thể cần:

~~~java
module org.example.greeter {
    exports org.example.greeter;
    opens org.example.greeter to some.framework.module;
}
~~~

**Đây là mảnh minh họa, không phải descriptor của ví dụ chạy được.** `some.framework.module` chỉ là tên giả định; phải dùng **tên module thật** của framework khi áp dụng. Không copy nguyên vào project mẫu.

Khác biệt:

- `exports`: cho phép compile-time và runtime access tới public API theo JPMS.
- `opens`: cho phép reflective access sâu ở runtime (trên phạm vi target module nếu khai báo `to`).
- `open module`: mở reflection trên toàn bộ packages của module; có thể quá rộng.
- `--add-exports` và `--add-opens` ở CLI: escape hatches cho runtime/compiler trong những trường hợp di trú hoặc framework legacy, không phải giải pháp kiến trúc mặc định.
- `public` vẫn cần thiết nếu muốn Java public API, nhưng **public không vượt qua một JPMS package chưa export**.

Không dùng `--add-opens ALL-UNNAMED` bừa bãi ở production. Khi gặp lỗi `InaccessibleObjectException` hoặc `IllegalAccessException`, xác định module/package/loader/target thật trước khi thêm quyền tạm.

## 17. Những lỗi thường gặp và cách phân biệt

| Triệu chứng | Nơi nên kiểm tra | Ý nghĩa |
| --- | --- | --- |
| `module not found: org.example.greeter` khi compile CLI | Maven dependency và module path, tên JPMS module | Java không resolve được named module dù descriptor có `requires`. |
| `package org.example.greeter is not visible` | `requires` và `exports` | CLI không đọc thư viện hoặc thư viện không export package, dù JAR có mặt. |
| `Cannot find symbol: Greeter` | Class/package import và project artifact | Mã nguồn, đường dẫn, scope hoặc API không đúng; không nhất thiết là JPMS. |
| Maven reactor build app trước library rồi fail | `greeter-cli/pom.xml` dependency | `<modules>` không tự tạo project dependency; cần link project thật. |
| `-pl :greeter-cli` build fail dù root build trước đó pass | Reactor selection và artifact cache | Đơn độc có thể không có library đã install; cân nhắc `-am`. |
| `java -m greeter-cli/...` không tìm thấy module | Nhầm artifactId với JPMS name | Dùng `org.example.cli` như descriptor, không phải `greeter-cli`. |
| `java -p ... -m ...` báo Java cannot find module | Module path runtime | Đưa modular JAR đúng đường dẫn và tên, kiểm artifact tồn tại. |
| `java -cp ...` in `module=null` | Chạy classpath mode | Code ở unnamed module, không phải bug của Maven. |
| `NoClassDefFoundError` chỉ lúc run app | Runtime path/JARs | Compile dependencies không tự được Java launcher nạp. |
| `FindException: Two versions of module ...` | Module path chứa module trùng tên | Giảm duplicate modules và kiểm soát resolution/packaging. |
| `LayerInstantiationException` hoặc lỗi split package | Hai modules chứa package trùng | Tránh split packages giữa named modules; thiết kế package/module boundaries lại. |
| Maven compile pass nhưng Surefire test lỗi reflection | Surefire JPMS mode, opens/patch-module | Test framework có thể cần access ngoài `exports`. |
| Dependency legacy JAR không được module-info nhận | Automatic module name/manifest | Kiểm tra `jar --describe-module` thay vì dùng Maven artifactId. |
| Java 17 build fail với plugin cũ | JDK / compiler plugin compatibility | Pin plugin phù hợp, kiểm `mvn --version` và `release`. |
| Project có hai Maven modules nhưng chỉ một JPMS module name | Trùng tên descriptors | Mỗi named module phải có định danh nhất quán/duy nhất trên module path. |
| Bật `useModulePath=false` nhưng module-info still fails | Compiler module-aware behavior | Không nên dùng false như công tắc vô hiệu hóa yêu cầu JPMS trong source. |

**Cách debug có hệ thống:** xem Maven POM/module nào thiếu dependency → xác minh output `module-info.class` → dùng `jar --describe-module` để kiểm tên/export → xem `requires` của caller → kiểm `java --module-path`/`--class-path` → nếu là test, xem Surefire JPMS settings → chạy lại build sạch. Không chỉnh cả POM và module-info ngẫu nhiên trong cùng một lượt vì sẽ khó xác định nguyên nhân.

## 18. Maven CLI khác Java CLI: các option không tương đương

Maven có các option chọn project/reactor:

~~~bash
mvn -pl :greeter-cli -am clean package
mvn -pl :greeter-lib clean package
mvn -N validate
~~~

Giải nghĩa:

- `-pl`/`--projects` chọn **Maven projects** theo path hoặc `:artifactId`.
- `-am`/`--also-make` kèm những project dependencies trong reactor, khi cần.
- `-N`/`--non-recursive` chỉ thao tác Maven project tại thư mục hiện tại, không chạy toàn reactor.

Những lệnh này **không bật/tắt JPMS exports**, không thêm `requires` và không tương đương `--module-path`. Ví dụ `mvn -pl :greeter-cli -am clean package` là lệnh hữu ích để build CLI và library dựa trên **Maven dependency graph**, còn `java -m org.example.cli/...` chọn **JPMS named module** để chạy.

Java có các option khác:

~~~bash
java --module-path "greeter-lib/target/greeter-lib-1.0.0.jar:greeter-cli/target/greeter-cli-1.0.0.jar" --module org.example.cli/org.example.cli.Main
java --class-path "greeter-lib/target/greeter-lib-1.0.0.jar:greeter-cli/target/greeter-cli-1.0.0.jar" org.example.cli.Main
~~~

Hai lệnh Java khác nhau vì **lựa chọn module path vs classpath**, không liên quan đến lệnh Maven đã chọn project nào.

Trong CI, một lỗi thường gặp là gọi `mvn -pl :greeter-cli package` mà library chưa được cài ở local repository, trong khi root `mvn package` trước đó thành công vì đã có cả hai project trong reactor. Sử dụng `-am` khi muốn Maven build những Maven dependencies liên quan từ source trong reactor.

## 19. Dependency scope Maven không thay thế JPMS requires

Scope Maven và requires JPMS có mục đích khác nhau:

| Maven dependency scope | Classpath/module path theo project resolution | Cần chú ý trong module-info |
| --- | --- | --- |
| `compile` (mặc định) | Thư viện có mặt cho main compile và thường cả runtime. | Nếu app modular dùng API từ named module tương ứng, cần `requires` cùng exports đúng. |
| `provided` | Thấy lúc compile/test, môi trường chạy cung cấp ở runtime. | `requires` vẫn có thể khiến JVM cần module khi chạy; provider phải được cung cấp đúng. |
| `runtime` | Không nằm ở main compile classpath; có ở runtime. | Không dùng API của runtime-only artifact trực tiếp trong main code compile nếu thiếu compile dependency. |
| `test` | Chỉ phục vụ test compilation/execution. | Test JPMS có quy tắc riêng; không đưa JUnit vào main module-info nếu production code không dùng nó. |
| `import` | Chỉ cho BOM POM trong dependencyManagement. | Không có ý nghĩa của JPMS `requires`. |

Vài ví dụ suy luận:

- Mã CLI có `requires org.example.greeter;` nhưng POM thiếu greeter-lib → **JPMS không biết tải Maven coordinates**, compile thiếu.
- POM CLI có dependency greeter-lib nhưng descriptor thiếu `requires` → **Java không tự đọc named module** chỉ vì Maven đã có JAR.
- POM có dependency `scope=runtime` cho một JDBC driver chỉ được load động → không nhất thiết thêm `requires driver.module;` vào main module descriptor, tùy service loading/provider design.
- `requires static something;` của JPMS không tự làm Maven chuyển dependency sang scope `provided`; phải lựa chọn Maven scope riêng theo runtime deployment.
- Một dependency Maven transitive có thể được Maven resolve, nhưng JPMS readability/transitive exports vẫn phải thỏa mãn. Không suy “Maven kéo JAR là Java import được mọi package”.

Kết luận: **POM quyết định cung cấp artifact cho build**, JPMS descriptor quyết định **readability và API visibility**. Cần hai lớp cấu hình nhất quán.

## 20. Thiết kế module boundaries trong dự án lớn

Đưa JPMS vào dự án đa module có thể cải thiện kiểm soát API, nhưng cũng làm lộ các giả định cũ:

1. **Chọn ranh giới Maven module theo artifact và trách nhiệm build**, không chỉ theo package name. Một Maven project có thể chứa nhiều packages.
2. **Chọn ranh giới JPMS theo API/export và dependency graph**; thường mô hình 1 Maven JAR project ↔ 1 named JPMS module là điểm bắt đầu dễ quản lý, nhưng không phải quy luật bắt buộc.
3. **Không export mọi package** chỉ để compiler im lặng. Chọn public API packages; giữ implementation/internal packages không export.
4. **Tránh split packages** giữa những named modules. Nếu hai JAR có cùng tên package, có thể cần refactor hoặc gộp module.
5. **Kiểm tra automatic modules** khi dùng third-party JAR. Ưu tiên thư viện có module descriptor hoặc `Automatic-Module-Name` ổn định; không đoán tên từ Maven artifactId.
6. **Đọc plugin/JDK docs khi dùng reflection**, frameworks và test engines; dùng `opens ... to ...` khi có lý do.
7. **Không lạm dụng `--add-exports`, `--add-opens`, `--add-reads`, `--patch-module`** trong CI để che lấp một modular design chưa đúng.
8. **Giữ Maven dependencies tường minh** cho API/module thực sự dùng; đừng dựa vô tình vào dependency transitive chỉ để compiler nhìn thấy class.
9. **Pin Maven/JDK/compiler/surefire plugin versions** để tránh khác biệt cách auto-detect module path.
10. **Chạy package thực tế bằng đúng kiểu runtime mong muốn**; build pass trên module path nhưng launcher production chỉ dùng classpath sẽ chạy theo semantics khác.
11. **Quan sát module graph và classpath trong từng module**; Maven reactor có nhiều projects, không có một global classpath chung.
12. **Dùng CI tests** cho cả compile, unit tests, integration tests và startup trên runtime image/container thật trước khi chuyển hoàn toàn sang JPMS.

Với các ứng dụng framework phức tạp, lộ trình chuyển đổi thường bắt đầu từ **ổn định Maven dependency graph**, sau đó modular hóa các JAR ít phụ thuộc reflection, và mới xử lý modules dùng framework/test runtime. Không nhất thiết biến mọi module Maven thành JPMS module ngay trong một lần refactor.

## 21. Một số câu hỏi tự kiểm tra

1. **Parent `pom.xml` có hai `<module>`, dự án đã là JPMS chưa?**  
   Chưa. Đó là hai Maven child projects; nếu không có `module-info.java` hoặc cách dùng automatic module phù hợp trên module path, chưa có explicit JPMS modules.

2. **Tên `greeter-lib` và `org.example.greeter` có phải giống nhau không?**  
   Không. Một cái là Maven artifactId/thư mục, một cái là tên JPMS module do module descriptor xác định.

3. **CLI POM phụ thuộc `greeter-lib` rồi, cần `requires org.example.greeter;` không?**  
   Nếu CLI là explicit JPMS module và muốn dùng public API của library qua module path, có. POM dependency không tự tạo JPMS readability.

4. **Library đã `exports org.example.greeter`, có cần CLI requires không?**  
   Có. Package được export không có nghĩa mọi named module tự đọc library.

5. **Nếu JAR chứa module-info.class nhưng chạy qua `java -cp`, Greeter.class.getModule().getName() trả gì?**  
   `null` với JAR trên application classpath, vì class thuộc unnamed module, không phải named module từ descriptor.

6. **Điều gì thay đổi khi chuyển `java -cp` thành `java -p ... -m ...`?**  
   JVM xử lý named module graph, kiểm `requires` và `exports`, và module names xuất hiện trong runtime identity.

7. **`requires transitive` có thay thế Maven transitive dependency không?**  
   Không. Nó là quy tắc readability bắc cầu của JPMS, không làm Maven tự resolve artifact coordinates.

8. **`<maven.compiler.release>17</...>` có làm máy tự có JDK 17 không?**  
   Không. Máy/build toolchain phải có compiler/JDK tương thích.

9. **Dùng Maven `-pl :greeter-cli -am` có chọn JPMS module org.example.cli không?**  
   Không. Nó chọn Maven project và các Maven dependencies để build trong reactor.

10. **Named module có thể đơn giản `requires unnamed;` để dùng JAR trên classpath không?**  
    Không. Unnamed module không có tên JPMS để viết vào requires; cần chiến lược migration/module path/automatic module hoặc escape hatch phù hợp.

11. **Maven Compiler Plugin `useModulePath=false` có xóa module-info.java khỏi source không?**  
    Không. Nó thay cách plugin cung cấp đường dẫn cho compiler, không viết lại Java source hay loại bỏ JPMS declarations.

12. **Vì sao test chạy lỗi reflection dù source đã compile?**  
    Vì test runtime có thể cần `opens` hoặc module patching/JPMS options riêng; exports chỉ liên quan public API, không mặc định cho deep reflection.

## 22. Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — Maven reactor, `<modules>`, sort order, `-pl` và `-am`.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — parent, aggregation, dependencies và plugin management.
- [Apache Maven Compiler Plugin 3.13.0 — compiler:compile](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html) — `useModulePath`, compile scope, Java release.
- [Apache Maven Compiler Plugin — Older projects with module-info](https://maven.apache.org/plugins/maven-compiler-plugin/examples/module-info.html) — module-info và biên dịch cho Java versions cũ.
- [Apache Maven Surefire Plugin — JPMS in Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/jpms.html) — modular tests với Java 9+.
- [Apache Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html) — `useModulePath` và test execution.
- [Oracle Java SE 17 — java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — `--module-path`, `--class-path`, `-m`.
- [Oracle Java SE 17 — javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — compile with classpath/module path.
- [Oracle Java SE 17 — jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) — `--describe-module` và `--list`.
- [dev.java — Automatic Modules](https://dev.java/learn/organizing/modules/automatic-module/) — automatic module names, legacy migration và unnamed module.
- [Java Language Specification, Java SE 17, Chapter 7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html) — module declarations, `requires` và `exports`.

**Tóm tắt:** Maven modules là **đơn vị build/artifact** do `pom.xml` và reactor quản lý; JPMS modules là **đơn vị Java readability/encapsulation** do `module-info.java` và JVM/Javac quản lý. Classpath thường đặt code vào **unnamed module**; module path cho phép **named modules** tham gia graph có `requires` và `exports`. Một dự án Maven có thể dùng hoặc không dùng JPMS; khi dùng cả hai, **Maven dependency và JPMS requires phải được cấu hình nhất quán**. Hãy dùng ví dụ Java 17, kiểm tra `jar --describe-module` và so sánh `java -p -m` với `java -cp` để thấy sự khác biệt thực tế.
