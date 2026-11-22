# Tài nguyên trên classpath và lớp trùng tên giữa các JAR

## 1. Tình huống thường gặp

Một dự án Java/Maven có thể biên dịch và chạy được trên máy phát triển nhưng lại lỗi khi chạy trong CI, khi đóng gói fat JAR, trên application server hoặc khi nâng cấp dependency. Các biểu hiện rất khác nhau:

- `getResourceAsStream("config/app.properties")` trả về `null`, dù file tồn tại trong repository.
- Ứng dụng đọc nhầm `app.properties` của một JAR khác có cùng đường dẫn.
- Hai thư viện chứa **cùng tên lớp đầy đủ** (*fully qualified/binary class name*) như `com.example.json.Parser`, nhưng chỉ một định nghĩa được nạp theo đường classpath hiện tại.
- Ở máy A chương trình chạy, máy B gặp `NoSuchMethodError` hoặc `NoClassDefFoundError` sau khi có thay đổi dependency/classpath.
- Unit test đọc resource của `src/test/resources`, còn khi đóng gói chạy thật lại đọc resource trong `src/main/resources`.
- Gộp nhiều JAR thành một shaded JAR làm mất một phần khai báo `META-INF/services/...` do trùng tên resource.

Để xử lý, cần phân biệt ba lớp:

1. **Maven quyết định những artifact nào được resolve** theo `dependencies`, scope, dependency management, optional và exclusions.
2. **Build/packaging đặt các file `.class` và resources ở đâu**, ví dụ `target/classes`, `target/test-classes` hay bên trong JAR.
3. **Java ClassLoader tìm lớp và tài nguyên theo quy tắc nào** trên classpath thực sự của tiến trình Java.

Đây là ba việc liên quan nhưng **không tương đương**. Đặc biệt, `mvn dependency:tree` chỉ hiển thị **artifact dependency graph**; nó không tự liệt kê mọi tên lớp/resource bị trùng giữa các JAR.

## 2. Classpath là gì? Có gì bên trong?

Trong Java truyền thống, **classpath** là danh sách các thư mục và JAR mà class loader có thể dùng để tìm các class và resource. Ví dụ:

```bash
java -cp "target/classes:lib/first.jar:lib/second.jar" demo.Main
```

Trên Linux/macOS, các mục classpath được ngăn bằng dấu `:`; trên Windows dùng dấu `;`:

```powershell
java -cp "target\classes;lib\first.jar;lib\second.jar" demo.Main
```

Trong ví dụ, Java nhận ba classpath entries: một thư mục `target/classes`, rồi hai JAR. Các class/resource trong **JAR không tự được bung ra** khi chạy; class loader có thể đọc các entry bên trong JAR trực tiếp.

Một đường classpath có thể chứa:

- Thư mục chứa cấu trúc package, ví dụ `target/classes/demo/Main.class`.
- JAR chứa các class, ví dụ `lib/first.jar` có entry `demo/util/Helper.class`.
- **Resources** không phải mã Java, như `config/app.properties`, `META-INF/services/...`, file JSON, XML, template, hình ảnh, dữ liệu và bản dịch `.properties`.

Maven chỉ đóng vai trò **xây dựng** classpath cho compiler, test runner và plugin; khi bạn khởi chạy `java -cp` bằng tay, **chính giá trị `-cp` quyết định classpath lúc chạy**. Một JAR tạo bằng Maven Jar Plugin thông thường không tự bao gồm toàn bộ các JAR dependency.

### Classpath khác module path

Bài này nói chủ yếu đến **classpath và class loader truyền thống**. Khi chạy theo Java Platform Module System (JPMS) qua `--module-path`, việc kiểm soát module/package, phát hiện split package và quá trình resolution có thể khác; không được áp dụng máy móc quy tắc “JAR đứng trước thắng” cho mọi ứng dụng modular.

## 3. Maven lấy resources từ đâu?

Theo cấu trúc Maven thông dụng:

```text
my-app/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/demo/Main.java
│   │   └── resources/
│   │       ├── config/app.properties
│   │       └── images/logo.png
│   └── test/
│       ├── java/demo/MainTest.java
│       └── resources/
│           └── config/app.properties
└── target/
    ├── classes/
    │   ├── demo/Main.class
    │   ├── config/app.properties
    │   └── images/logo.png
    └── test-classes/
        ├── demo/MainTest.class
        └── config/app.properties
```

Maven Resources Plugin xử lý:

| Đầu vào mặc định | Giai đoạn thường gặp | Goal | Đích mặc định |
| --- | --- | --- | --- |
| `src/main/resources` | `process-resources` | `resources:resources` | `target/classes` |
| `src/test/resources` | `process-test-resources` | `resources:testResources` | `target/test-classes` |

Maven Compiler Plugin biên dịch `src/main/java` vào `target/classes` và `src/test/java` vào `target/test-classes`. Sau `mvn package` của project `jar`, phần nội dung phù hợp trong `target/classes` thường được đặt vào JAR. Thông thường **test classes/resources không nằm trong JAR sản phẩm**.

**Điểm dễ nhầm:** trong Java, path dùng để truy cập resource là **path bên trong classpath root**, không phải đường dẫn tương đối so với thư mục shell.

Nếu file là `src/main/resources/config/app.properties` thì sau build resource thường được truy cập dưới tên:

```text
config/app.properties
```

Không phải:

```text
src/main/resources/config/app.properties
```

Vì `src/main/resources` là **source root**, còn `config/app.properties` là **resource name** nhìn từ classpath.

### Resource filtering không tự xảy ra cho mọi file

Maven Resources Plugin có tính năng *filtering* thay các placeholder được cấu hình. Nhưng không nên cho rằng mọi file `.properties`/`.yaml` đều tự được thay nội dung. Muốn filtering, bạn phải khai cấu hình tương ứng và chú ý encoding, ký tự escape, cách truyền secrets. Resource không được filter thì thường được sao chép nguyên nội dung. Cần đọc effective POM nếu file output khác source bất ngờ.

## 4. Scope Maven quyết định classpath nào có dependency

Một dependency Maven có scope ảnh hưởng nó tham gia các classpath ở những bước nào:

| Scope thông dụng | Main compile classpath | Test compile/test runtime | Runtime ứng dụng thông thường | Tác động |
| --- | --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có | Thường truyền bắc cầu theo quy tắc scope |
| `provided` | Có | Có | Không được Maven tự cung cấp cho runtime | Dùng khi container/JDK/môi trường cấp artifact |
| `runtime` | Không phải main compile dependency | Có | Có | Dùng thư viện cần khi chạy |
| `test` | Không | Có | Không | Dùng test runner/mock/assertions |
| `system` | Có theo cấu hình đường dẫn local | Có | Không theo cơ chế repository chuẩn | Không khuyến nghị, khó tái lập |

Bảng mô tả hành vi trong mô hình Maven cổ điển. Classpath thực tế còn phụ thuộc plugin, exclusions, optional, profile và launcher. Ví dụ `provided` có thể xuất hiện ở runtime **do container tự đưa vào**, chứ không phải do Maven bundling.

**Tại sao liên quan đến lớp trùng tên?** Một JAR chỉ có thể gây collision trên **classpath đang thực sự dùng**. Nếu `conflict-b` chỉ ở scope `test`, test runner có thể thấy nó nhưng ứng dụng production không thấy. Ngược lại, JAR có scope `runtime` có thể xuất hiện khi chạy dù compiler không dùng nó để compile mã main.

### Test resource có thể che resource main

Theo classpath mặc định được tài liệu Maven Surefire mô tả, test runtime thường tìm theo thứ tự:

1. `target/test-classes`;
2. `target/classes`;
3. các dependency đã resolve trong test classpath;
4. những classpath entries bổ sung được cấu hình.

Do đó, nếu **cả `src/test/resources/config/app.properties` và `src/main/resources/config/app.properties`** tồn tại, lệnh test sử dụng `ClassLoader.getResource("config/app.properties")` có thể lấy **bản trong `target/test-classes`**. Điều này hữu ích để override cấu hình test, nhưng dễ gây bất ngờ khi đóng gói chạy production: bản test không nằm trong main JAR và ứng dụng đọc bản main.

Không nên coi thứ tự này là quy luật tuyệt đối cho mọi IDE, custom test launcher hoặc container; hãy kiểm tra classpath thật khi vấn đề xảy ra.

## 5. Trùng **resource name** khác trùng **class name**

### 5.1. Hai JAR cùng có đường dẫn resource

Ví dụ:

```text
lib-a.jar
├── demo/conflict/Welcome.class
└── demo/banner.txt              # nội dung: banner-A

lib-b.jar
├── demo/conflict/Welcome.class
└── demo/banner.txt              # nội dung: banner-B
```

Hai resource cùng tên logic `demo/banner.txt`. Với class loader tra cứu theo classpath, gọi:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
java.net.URL first = loader.getResource("demo/banner.txt");
```

thường lấy **resource đầu tiên** mà loader tìm được theo cơ chế của nó. Nếu muốn biết tất cả resource được trả về, dùng:

```java
java.util.Enumeration<java.net.URL> matches =
        loader.getResources("demo/banner.txt");
```

`getResources` là công cụ chẩn đoán hữu ích vì bạn có thể liệt kê **các URL mà class loader thực sự thấy**. Không thể khẳng định tất cả các file trùng trên đĩa đều được liệt kê nếu chúng không nằm trong classpath/loader đó.

Đối với `.properties`, việc `getResourceAsStream` trả về resource đầu tiên **không tự gộp các key** từ nhiều JAR. Muốn merge phải chủ động thiết kế thuật toán hoặc dùng cơ chế/config framework phù hợp.

### 5.2. Hai JAR có cùng fully qualified class name

Giả sử hai JAR đều có entry:

```text
demo/conflict/Welcome.class
```

Điều này nghĩa là cả hai cung cấp **cùng binary name** `demo.conflict.Welcome`. Trong **classpath đơn giản** với một application class loader và không có class definition đã được nạp từ trước, JVM thường tìm theo classpath entry order và class loader sử dụng **một định nghĩa** phù hợp; không gộp bytecode của hai bản.

Hệ quả:

- Có thể chạy nhầm bản cũ dù dependency mới đã được thêm.
- Compiler chọn một API, còn runtime chọn API khác → `NoSuchMethodError`, `NoSuchFieldError`, `IncompatibleClassChangeError`...
- Nếu trùng tên nhưng bytecode có khác biệt logic, chương trình có thể chạy mà trả kết quả sai, **không** báo lỗi ngay.
- Class loader khác nhau có thể nạp các định nghĩa cùng tên trong những namespace runtime khác nhau. Khi trao đổi đối tượng giữa hai loader, có thể gặp `ClassCastException` dù tên lớp trong message nhìn giống nhau.

**Không nên dùng “JAR nào đứng trước cũng luôn thắng” như luật áp dụng mọi nơi.** Java có cơ chế *parent delegation*, custom classloaders, module layers, application servers và fat-JAR launchers. Thứ tự nạp trong môi trường cụ thể có thể khác thứ tự dependency bạn nhìn thấy trong POM.

### 5.3. Maven chọn version không tự phát hiện trùng lớp giữa hai artifact khác tên

`dependency:tree` có thể giúp phân tích xung đột **cùng GAV family** và version mediation. Nhưng nếu `lib-a` và `lib-b` là hai artifact ID khác nhau, đều chứa `demo.conflict.Welcome`, Maven thường coi đó là **hai artifact hợp lệ**. Dependency mediation không thể tự biết chúng đang đóng gói cùng class.

Điều đó giải thích tại sao `dependency:tree` có thể không có conflict về **phiên bản**, nhưng classpath vẫn có **trùng FQN**.

## 6. Ví dụ Java 17 hoàn chỉnh: hai JAR chứa cùng lớp và cùng resource

Bài thực hành dùng **ba Maven project độc lập** để tránh phụ thuộc thư viện bên ngoài không ổn định:

- `jar-a` cung cấp `demo.conflict.Welcome` trả về `jar-A` và resource `demo/banner.txt` chứa `banner-A`.
- `jar-b` cung cấp **cùng** `demo.conflict.Welcome` nhưng trả về `jar-B`, với resource cùng tên chứa `banner-B`.
- `viewer-app` chỉ khai dependency vào `jar-a` để compile. Khi khởi chạy Java **bằng classpath thủ công**, bạn chủ động đưa thêm `jar-b` vào để quan sát hành vi hai JAR trùng nhau.

### 6.1. Cây thư mục cần tạo

```text
classpath-lab/
├── jar-a/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/conflict/Welcome.java
│       └── resources/demo/banner.txt
├── jar-b/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/conflict/Welcome.java
│       └── resources/demo/banner.txt
└── viewer-app/
    ├── pom.xml
    └── src/main/java/demo/app/Main.java
```

Ba thư mục có POM riêng. Không có `pom.xml` tổng hợp ở `classpath-lab/`; ta sẽ dùng `mvn -f` để build từng project, đúng theo thứ tự.

### 6.2. POM của `jar-a`

File `classpath-lab/jar-a/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.lesson</groupId>
    <artifactId>jar-a</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

File `classpath-lab/jar-a/src/main/java/demo/conflict/Welcome.java`:

```java
package demo.conflict;

public final class Welcome {
    private Welcome() {
    }

    public static String origin() {
        return "jar-A";
    }
}
```

File `classpath-lab/jar-a/src/main/resources/demo/banner.txt` là UTF-8, chỉ chứa dòng:

```text
banner-A
```

### 6.3. POM của `jar-b`

File `classpath-lab/jar-b/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.lesson</groupId>
    <artifactId>jar-b</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

File `classpath-lab/jar-b/src/main/java/demo/conflict/Welcome.java`:

```java
package demo.conflict;

public final class Welcome {
    private Welcome() {
    }

    public static String origin() {
        return "jar-B";
    }
}
```

File `classpath-lab/jar-b/src/main/resources/demo/banner.txt`:

```text
banner-B
```

Hai lớp Java có **cùng `package`, tên lớp và chữ ký method `origin()`**, chỉ khác kết quả trả về. Chúng được build trong **hai project khác nhau**, vì vậy compiler của mỗi project không nhìn thấy hai source trùng FQN cùng lúc.

### 6.4. POM của `viewer-app`

File `classpath-lab/viewer-app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.lesson</groupId>
    <artifactId>viewer-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>jar-a</artifactId>
            <version>1.0.0</version>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`viewer-app` **không** khai dependency vào `jar-b`. Ta sẽ thêm JAR B **chỉ tại câu lệnh Java khi chạy**, làm rõ khác biệt giữa dependency graph trong POM và classpath do launcher thực sự dùng.

### 6.5. Lớp ứng dụng đọc class và resource

File `classpath-lab/viewer-app/src/main/java/demo/app/Main.java`:

```java
package demo.app;

import demo.conflict.Welcome;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("class=" + Welcome.origin());

        ClassLoader loader = Main.class.getClassLoader();

        try (InputStream stream =
                     loader.getResourceAsStream("demo/banner.txt")) {
            if (stream == null) {
                throw new IllegalStateException("Missing demo/banner.txt");
            }
            String content = new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8
            ).trim();
            System.out.println("first-resource=" + content);
        }

        Enumeration<URL> matches = loader.getResources("demo/banner.txt");
        int count = 0;
        while (matches.hasMoreElements()) {
            matches.nextElement();
            count++;
        }
        System.out.println("resource-count=" + count);
    }
}
```

Giải thích:

- `Welcome.origin()` gọi một phương thức có cùng chữ ký trong cả hai JAR, nên giá trị trả về cho biết Java đã nạp class từ bản nào.
- `Main.class.getClassLoader()` chọn class loader đã nạp `Main`, tránh giả định thread context class loader luôn giống loader này.
- `getResourceAsStream("demo/banner.txt")` đọc **một** resource được loader tìm thấy; `stream == null` giúp báo lỗi rõ ràng thay vì `NullPointerException`.
- `getResources("demo/banner.txt")` liệt kê các resource URL có cùng tên theo khả năng thấy của loader. Đếm kết quả giúp thấy cả hai JAR có resource trùng tên.
- `InputStream.readAllBytes()` và `StandardCharsets.UTF_8` dùng được trên Java 17.
- `trim()` loại ký tự xuống dòng cuối file để stdout ổn định trong ví dụ.

### 6.6. Build theo thứ tự

Yêu cầu: JDK 17+; Maven 3.x hiện đại; Maven có thể resolve Compiler/Jar plugins từ repository hoặc mirror được cấu hình.

Đứng trong thư mục `classpath-lab/`:

```bash
mvn -version
mvn -f jar-a/pom.xml clean install
mvn -f jar-b/pom.xml clean package
mvn -f viewer-app/pom.xml clean package
```

Tại sao thứ tự này quan trọng?

1. `jar-a` được **install** vào Maven local repository, nên `viewer-app` resolve được dependency `dev.lesson:jar-a:1.0.0`.
2. `jar-b` chỉ cần `package` để tạo file JAR ở `jar-b/target/`; ứng dụng không phụ thuộc `jar-b` trong POM.
3. `viewer-app` compile dựa trên API `Welcome.origin()` từ `jar-a`, tạo `target/classes` và JAR ứng dụng.

Nếu build thành công, các file quan trọng:

```text
classpath-lab/
├── jar-a/target/jar-a-1.0.0.jar
├── jar-b/target/jar-b-1.0.0.jar
└── viewer-app/target/viewer-app-1.0.0.jar
```

Bạn có thể xem entry trong JAR bằng công cụ đi kèm JDK:

```bash
jar tf jar-a/target/jar-a-1.0.0.jar
jar tf jar-b/target/jar-b-1.0.0.jar
```

Trong **cả hai JAR** sẽ có entry `demo/conflict/Welcome.class` và `demo/banner.txt`. Không cần mở bytecode để thấy tên entry bị trùng.

### 6.7. Chạy A trước, B sau

Đứng tại `classpath-lab/`, trên Linux/macOS/Bash:

```bash
java -cp "viewer-app/target/classes:jar-a/target/jar-a-1.0.0.jar:jar-b/target/jar-b-1.0.0.jar" demo.app.Main
```

Trong ví dụ **Java CLI classpath thuần túy** này, output dự kiến:

```text
class=jar-A
first-resource=banner-A
resource-count=2
```

Vì classpath liệt kê `jar-a` trước `jar-b`, application class loader thông thường tìm `Welcome.class` và `demo/banner.txt` ở JAR A trước. `getResources` vẫn liệt kê **hai** resource cùng tên từ cả hai JAR.

### 6.8. Đổi chỗ hai JAR

```bash
java -cp "viewer-app/target/classes:jar-b/target/jar-b-1.0.0.jar:jar-a/target/jar-a-1.0.0.jar" demo.app.Main
```

Output dự kiến:

```text
class=jar-B
first-resource=banner-B
resource-count=2
```

**Chỉ thay thứ tự classpath, không sửa source, POM hoặc JAR nào.** Phép thử cho thấy một chương trình có thể đổi hành vi khi có class/resource trùng tên giữa JAR.

**Trên Windows PowerShell**, dùng dấu `;` để ngăn các mục classpath:

```powershell
java -cp "viewer-app\target\classes;jar-a\target\jar-a-1.0.0.jar;jar-b\target\jar-b-1.0.0.jar" demo.app.Main
```

Đổi thứ tự `jar-a`/`jar-b` tương tự. Dấu `;` là phần của **một chuỗi classpath được quote**; nếu bỏ quote, shell có thể tách command sai.

**Giới hạn của kết luận:** thứ tự A/B và stdout ở trên dành riêng cho các câu lệnh `java -cp` minh bạch, class loader ứng dụng tiêu chuẩn và hai JAR có nội dung đúng như tạo. Khi dùng wildcard `lib/*`, fat JAR loader, plugin chạy trong Maven, IDE hoặc app server, thứ tự thực tế có thể khác hoặc không được bảo đảm bởi người viết lệnh.

### 6.9. Dùng `dependency:tree` và hiểu giới hạn của nó

Tại `classpath-lab/`:

```bash
mvn -f viewer-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Với POM ứng dụng mẫu, dependency graph thường chỉ có `jar-a`, **không có `jar-b`**, bởi `jar-b` được bạn chủ động đưa vào **runtime `-cp`**, không được khai trong POM.

Điều này không mâu thuẫn với output `resource-count=2`:

- `dependency:tree` trả lời “Maven đã resolve artifact nào cho project này?”.
- `java -cp` trả lời “launcher Java cụ thể này đang nhìn thấy classpath entry nào?”.
- `getResources` trả lời “class loader cụ thể này tìm thấy resource URL nào?”.

Muốn kiểm chứng runtime thật, phải xét cả ba góc nhìn, đặc biệt trong hệ thống dùng launcher riêng.

## 7. Đọc resource đúng cách trong Java

### `ClassLoader.getResourceAsStream`: path tuyệt đối từ classpath root

```java
try (InputStream in = Main.class.getClassLoader()
        .getResourceAsStream("demo/banner.txt")) {
    if (in == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Đọc stream...
}
```

Đây là **đoạn Java minh họa**, không phải class hoàn chỉnh độc lập. Tên resource không bắt đầu bằng `/` khi dùng `ClassLoader.getResource...`.

### `Class.getResourceAsStream`: path có thể tương đối với package

Với `demo.app.Main.class`:

```java
Main.class.getResourceAsStream("/demo/banner.txt");
```

Dấu `/` đầu thể hiện path **từ classpath root** khi dùng API `Class.getResourceAsStream`. Nếu viết:

```java
Main.class.getResourceAsStream("demo/banner.txt");
```

thì API dạng tương đối có thể tìm theo package của `Main`, tương đương path `demo/app/demo/banner.txt`, **không phải** file `demo/banner.txt` đã tạo. Đây là một trong những lỗi resource-path phổ biến nhất.

**Phân biệt:**

| API | Ví dụ | Cách hiểu path |
| --- | --- | --- |
| `ClassLoader.getResourceAsStream("demo/banner.txt")` | Không có `/` đầu | Từ classpath root |
| `Main.class.getResourceAsStream("/demo/banner.txt")` | Có `/` đầu | Từ classpath root |
| `Main.class.getResourceAsStream("banner.txt")` | Không có `/` đầu | Tương đối với package `demo.app` |

### Không dùng `new File(...)` cho resource bên trong JAR

Nếu resource nằm ở `target/classes`, `new File("src/main/resources/...")` có thể tình cờ chạy khi CWD đúng. Nhưng khi đóng gói, resource nằm trong JAR dưới dạng entry, không còn là một file thường ở đường dẫn đó. Với resource thuộc classpath, ưu tiên `getResourceAsStream`/`getResource`.

Tương tự, đừng mặc định `Paths.get(resourceUrl.toURI())` sẽ tạo một `Path` của file thường: URL có thể có scheme `jar:` hoặc đến từ custom loader. Nếu cần đọc resource, stream là cách dùng linh hoạt hơn.

## 8. Cách tìm JAR thật sự chứa lớp/resource đang được dùng

### 8.1. In CodeSource của lớp

Trong Java, có thể thêm đoạn chẩn đoán:

```java
var codeSource = demo.conflict.Welcome.class
        .getProtectionDomain().getCodeSource();
System.out.println(codeSource == null
        ? "Unknown code source"
        : codeSource.getLocation());
```

Đây là đoạn chẩn đoán **bổ sung vào phương thức Java**, không phải một chương trình Java độc lập. Với class do class loader tiêu chuẩn nạp từ JAR, URL thường chỉ đến JAR tương ứng. Tuy nhiên, một số môi trường bảo mật, framework hoặc class loader tự tạo class có thể không cung cấp `CodeSource`.

Nếu cần biết chính xác class được nạp thế nào, trên Java 17 có thể dùng diagnostic logging của JVM trong môi trường kiểm soát:

```bash
java -Xlog:class+load=info -cp "viewer-app/target/classes:jar-a/target/jar-a-1.0.0.jar:jar-b/target/jar-b-1.0.0.jar" demo.app.Main
```

Log sẽ dài; lọc theo tên class cần điều tra. Đừng bật log quá mức trên production mà chưa đánh giá hiệu năng và thông tin nhạy cảm. Một class loader khác có thể có các quy tắc load riêng.

### 8.2. Liệt kê tất cả URL của resource

Nếu bạn cần xem các source resource thay vì chỉ đếm, có thể dùng trong method:

```java
ClassLoader loader = Main.class.getClassLoader();
Enumeration<URL> all = loader.getResources("demo/banner.txt");
while (all.hasMoreElements()) {
    System.out.println(all.nextElement());
}
```

Các URL có thể cho biết resource thuộc JAR nào, ví dụ dạng `jar:file:/.../jar-a-1.0.0.jar!/demo/banner.txt`. Đây là **dạng minh họa**, không phải stdout cố định vì path phụ thuộc máy và loại launcher.

### 8.3. So sánh cây dependency và classpath của Maven

```bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath
```

Chạy ở đúng thư mục có POM hoặc thêm `-f path/to/pom.xml`. Những lệnh này giúp xem GAV/scope/đường dẫn dependency mà Maven resolve. Nếu JAR đến từ classpath tùy chỉnh ở IDE/container hoặc `java -cp`, nó **có thể không xuất hiện trong Maven graph**.

Đừng ngộ nhận rằng `mvn dependency:tree` phát hiện hai JAR khác artifactId nhưng chứa một lớp trùng FQN. Cần **quét entry trong JAR** hoặc dùng plugin/công cụ chuyên biệt cho trùng lớp.

### 8.4. Kiểm tra entry bên trong từng JAR

Trên máy có JDK:

```bash
jar tf lib-a.jar
jar tf lib-b.jar
```

Tìm `demo/conflict/Welcome.class` và `demo/banner.txt` trong output. Nếu JAR là Spring Boot executable JAR hoặc có cấu trúc nested JAR, hãy chú ý lớp/đường dẫn đóng gói bên trong; không nên kết luận theo cách quét JAR thường mà không hiểu loader của ứng dụng.

Với nhiều dependency, có thể bổ sung bước CI dùng công cụ kiểm tra duplicate classpath entries. Ví dụ **Maven Enforcer** cùng một quy tắc bên thứ ba như `BanDuplicateClasses` (từ extra-enforcer-rules khi được cấu hình tương thích) có thể hỗ trợ kiểm tra. Đó **không** phải goal `dependency:tree` và không phải rule mặc định của Maven core.

## 9. Khi đóng gói fat JAR hoặc shaded JAR, chuyện gì xảy ra?

Trong ví dụ thực hành, classpath có hai JAR độc lập. Nhưng đôi khi dự án dùng:

- Maven Shade Plugin để đóng gói nhiều dependency vào một *uber/shaded JAR*;
- Maven Assembly Plugin với descriptor `jar-with-dependencies`;
- Spring Boot Maven Plugin để tạo executable JAR với các nested JAR;
- ứng dụng chạy trên application server/container với class loader đặc thù.

Những kiểu packaging này **không đồng nhất**. Ví dụ Shade Plugin có thể kết hợp nội dung từ nhiều artifact vào một JAR, khiến **entry name trùng nhau** xuất hiện ngay trong quá trình đóng gói. Với resource trùng tên, cần chính sách cụ thể để chọn/merge/transform; không thể kỳ vọng mọi file tự được ghép nội dung theo logic đúng.

### `META-INF/services` và `ServiceLoader`

Java SPI/`ServiceLoader` dùng resource tên:

```text
META-INF/services/com.example.spi.GreeterProvider
```

Mỗi file có thể chứa tên class implementation. Nếu hai JAR cùng cung cấp provider cho một service, classpath có thể cho phép `ServiceLoader` tìm **nhiều service configuration resources** và đọc các provider entries.

Khi **shade thành một JAR**, nếu xử lý trùng tên resource đơn giản bằng cách chỉ lấy một file thì provider trong file còn lại có thể bị mất. Maven Shade Plugin có `ServicesResourceTransformer` để **gộp nội dung `META-INF/services` và xử lý tên class khi relocation**, ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn cấu hình plugin** cần đặt trong `<build><plugins>` của POM thích hợp; không phải một POM độc lập. Nó minh họa transformer dành cho service resource, **không tự đảm bảo** mọi resource `.properties`, YAML hay mọi lớp trùng tên được xử lý đúng.

### Relocation không giống exclusion

- **Exclusion** trong dependency declaration có thể loại một transitive artifact khỏi graph ở một nhánh.
- **Relocation** của Maven Shade Plugin có thể đổi package/class names trong bytecode đã đóng gói để tránh va chạm tên, nhưng phải kiểm tra các string-based references, resources và framework reflection.
- **Resource transformer** gộp/xử lý một nhóm resource theo logic cụ thể.

Không chọn công cụ bừa chỉ để “build hết warning”. Muốn loại một thư viện cần chắc chắn không thiếu class lúc chạy; muốn relocate cần test toàn bộ đường load/serialization/reflection.

## 10. Các lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| `getResourceAsStream` trả `null` | Dùng sai tên path, resource không được copy, không nằm trên classpath, khác loader | Kiểm tra `target/classes`/JAR, sửa path API, in `getResources` |
| Trong test đọc đúng, đóng gói đọc sai | `src/test/resources` override resource main, test runner classpath khác production | So sánh `target/test-classes`, `target/classes` và runtime launcher |
| App đọc nhầm cấu hình từ thư viện | Trùng `config/app.properties` hoặc thư viện đóng gói resource generic | Đặt resource name có namespace, liệt kê tất cả URL |
| `NoSuchMethodError` | Compile và runtime nạp class khác version/API | In CodeSource, xem classpath và dependency mediation |
| `NoClassDefFoundError` | Runtime thiếu class/JAR hoặc lỗi khởi tạo class | Xem stack trace và lỗi gốc; đối chiếu runtime graph |
| `ClassCastException` cho tên lớp giống nhau | Cùng binary name nhưng bị nạp bởi nhiều class loader khác nhau | In `getClassLoader()` của từng type, kiểm tra module/container |
| Build shade cảnh báo overlap | Nhiều JAR có entry path trùng nhau | Quét `jar tf`, quyết định exclusion/relocation/transform |
| `ServiceLoader` thiếu provider sau shade | `META-INF/services` bị ghi đè hoặc chưa merge | Cấu hình `ServicesResourceTransformer`, test provider enumeration |
| Máy phát triển chạy, CI lỗi | JAR order khác, dependency/version, JDK, plugin hoặc launcher khác | So sánh full runtime classpath, `mvn -version`, dependency tree |
| Maven không báo conflict nhưng vẫn trùng class | Hai artifact ID khác nhau chứa cùng FQN | Scan JAR entries, dùng rule duplicate-class kiểm tra |

Một lỗi như `NoSuchMethodError` có thể có nhiều nguyên nhân khác nhau (API incompatibility, compile/runtime mismatch); **đừng tự kết luận nguyên nhân chỉ từ tên exception**. Thu thập cả classpath thực tế, CodeSource và phiên bản JAR.

## 11. Cách thiết kế để tránh trùng resource và lớp

### 11.1. Đặt resource theo namespace

Thay vì mỗi thư viện đều dùng `config.properties` ở classpath root, đặt tên rõ phạm vi:

```text
META-INF/my-company/my-library/defaults.properties
com/example/library/config/defaults.properties
```

Tùy framework, path được framework cố định không thể đổi tùy ý; trong trường hợp đó cần cơ chế override/merge do framework cung cấp. Quy tắc là **namespace resource riêng** khi thiết kế thư viện mới.

### 11.2. Khai dependency theo nhu cầu thật

- Khai trực tiếp thư viện có API mà source của bạn sử dụng.
- Loại version không mong muốn bằng dependency management/exclusion có kiểm soát; không dùng `systemPath` để giấu dependency.
- Khi nhiều thư viện chứa cùng class do copy/shading, ưu tiên bản thư viện chính thức đã sửa hoặc đóng gói lại có relocation hợp lý.
- Không phụ thuộc vào thứ tự JAR không được bảo đảm như một “cách sửa” lâu dài.

### 11.3. Kiểm thử đúng runtime classpath

Test Maven có thể dùng `target/test-classes` trước main; container runtime có thể dùng parent-first/child-first. Bởi vậy một test PASS không chứng minh production chắc chắn nạp cùng class/resource. Với ứng dụng đóng gói, nên chạy smoke/integration test **đối với artifact cuối cùng** bằng launcher sẽ dùng trong triển khai.

### 11.4. Đưa kiểm tra collision vào CI

Với hệ thống lớn, có thể thêm kiểm tra:

1. Resolve toàn bộ dependency theo profile/target runtime.
2. Liệt kê class entries trong mọi JAR thực sự nằm trên classpath.
3. Nhóm theo path `.../Welcome.class` để phát hiện một FQN có nhiều nguồn.
4. Quét những resource nhạy cảm như `META-INF/services/*` và config name có nguy cơ trùng.
5. Duy trì danh sách ngoại lệ có giải thích; fail build khi gặp collision không chấp nhận được.
6. Chạy smoke test trên fat JAR/container image để xác nhận class/resource được load.

Không nhất thiết phải coi **mọi** duplicate resource là lỗi: `META-INF/services` có thể cố ý được nhiều JAR đóng góp; các license/notice cũng có thể trùng hợp lệ. Hãy xây **chính sách riêng cho duplicate class và duplicate resource**, thay vì xóa đại một JAR.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Có file `src/main/resources/demo/banner.txt`, bạn nên gọi API nào để đọc từ classpath root?

**Đáp án:** `Main.class.getClassLoader().getResourceAsStream("demo/banner.txt")` hoặc `Main.class.getResourceAsStream("/demo/banner.txt")`. Không nhất thiết dùng `src/main/resources/...` khi app đã được đóng gói.

**Câu 2.** Hai JAR đều có `demo/conflict/Welcome.class`. Maven `dependency:tree` có luôn cảnh báo duplicate class không?

**Đáp án:** Không. `dependency:tree` hiển thị graph artifact và version; cần quét nội dung JAR hoặc dùng công cụ chuyên biệt để phát hiện trùng binary class name.

**Câu 3.** Với `java -cp "A.jar:B.jar"` trên Linux và class loader ứng dụng thông thường, nếu cả hai JAR chứa cùng class, bản nào thường được tìm trước?

**Đáp án:** A. Nhưng đó là nhận xét cho tình huống classpath đơn giản, không suy rộng sang mọi class loader, wildcard, JPMS hoặc fat JAR launcher.

**Câu 4.** Vì sao `src/test/resources/config/app.properties` có thể che bản `src/main/resources/config/app.properties` khi test?

**Đáp án:** Test classpath thường có `target/test-classes` trước `target/classes`; resource lookup đầu tiên có thể lấy bản test. Khi chạy production, classpath có thể không có `target/test-classes`.

**Câu 5.** Nếu Shade Plugin gộp hai JAR cùng khai `META-INF/services/...`, bạn cần lưu ý gì?

**Đáp án:** Resource service configuration phải được merge theo cơ chế phù hợp, ví dụ `ServicesResourceTransformer`; nếu chỉ giữ một file, một số provider có thể biến mất.

## 13. Checklist chẩn đoán nhanh

- [ ] Tôi phân biệt **classpath thật của tiến trình** với dependency graph trong POM.
- [ ] Tôi đã kiểm tra resource nằm trong `target/classes`, `target/test-classes` hoặc đúng JAR chưa.
- [ ] Tôi dùng path theo **classpath root**, không theo CWD hoặc `src/main/resources`.
- [ ] Tôi phân biệt `ClassLoader.getResourceAsStream("...")` với `Class.getResourceAsStream("/...")`.
- [ ] Tôi kiểm tra scope Maven của dependency trong compile/test/runtime.
- [ ] Tôi đã tìm các resource URL trùng nhau bằng `getResources`.
- [ ] Tôi đã xác định class nạp từ JAR nào bằng CodeSource/log hoặc bằng test hành vi.
- [ ] Tôi không giả định `dependency:tree` phát hiện trùng FQN giữa hai artifact khác tên.
- [ ] Tôi đã kiểm tra classloader cụ thể của IDE/Surefire/container/fat JAR.
- [ ] Với shaded JAR, tôi đã xét chính sách merge resource và `META-INF/services`.
- [ ] Với lỗi runtime, tôi đã chạy smoke test trên đúng artifact và launcher cuối cùng.
- [ ] Tôi đã ưu tiên loại nguyên nhân (dependency sai, bản cũ, class duplication) thay vì chữa bằng đổi thứ tự JAR ngẫu nhiên.

**Ghi nhớ:** Maven quyết định *artifact nào được resolve*, plugin build quyết định *class và resource nằm ở đâu*, còn ClassLoader quyết định *bản nào thực sự được nhìn thấy/nạp khi chạy*. Hai JAR có thể cùng tồn tại hợp lệ trong dependency graph nhưng vẫn trùng class hoặc resource path. Muốn chẩn đoán chính xác, hãy nhìn **cả dependency tree, nội dung JAR và classpath/classloader thực tế**.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Resources Plugin — Introduction](https://maven.apache.org/plugins/maven-resources-plugin/)
- [Apache Maven Resources Plugin — resources:resources](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html)
- [Apache Maven Surefire Plugin — Configuring the Classpath](https://maven.apache.org/surefire-archives/surefire-3.5.5/maven-surefire-plugin/examples/configuring-classpath.html)
- [Apache Maven Shade Plugin — Resource Transformers](https://maven.apache.org/components/plugins/maven-shade-plugin/examples/resource-transformers.html)
- [Oracle Java API — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Oracle Java API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
