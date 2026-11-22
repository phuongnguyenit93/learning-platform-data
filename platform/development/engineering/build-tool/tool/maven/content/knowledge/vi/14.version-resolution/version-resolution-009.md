# Chẩn đoán NoSuchMethodError hoặc NoClassDefFoundError do lệch phụ thuộc Maven

## 1. Vấn đề: build thành công nhưng JVM vẫn lỗi

Một tình huống thường gặp trong dự án Java dùng Maven:

- `mvn clean package` hoặc `mvn verify` báo **BUILD SUCCESS**.
- Test chạy được trên máy lập trình viên, nhưng ứng dụng lỗi ở server hoặc sau khi đóng gói.
- Stack trace xuất hiện `java.lang.NoSuchMethodError` hoặc `java.lang.NoClassDefFoundError`.
- Nhiều module/thư viện đang yêu cầu **những phiên bản khác nhau của cùng một artifact**.

Hai lỗi thường liên quan **binary linkage**: mã bytecode đã biên dịch chứa một tham chiếu tới class/method, nhưng khi JVM chạy, nó tải một bộ class không đáp ứng tham chiếu ấy. Maven giúp chọn và tải dependency, nhưng kết quả Maven resolve **không tự bảo đảm** classpath mà JVM ở môi trường chạy thật sử dụng là giống hệt.

Câu hỏi cần trả lời không chỉ là “dependency có được khai báo trong POM không?” mà là:

1. **Bytecode được biên dịch dựa trên API nào?**
2. **Maven chọn phiên bản nào trong dependency graph hiệu lực?**
3. **JVM khi lỗi thực sự nạp class từ JAR/đường dẫn nào?**
4. **Class/method đang bị thiếu có thực sự nằm trong JAR được nạp không?**

Bài này hướng dẫn chẩn đoán theo bốn lớp ấy và cung cấp ví dụ **Java 17 có thể tái lập** cả hai lỗi bằng cách cho chương trình chạy nhầm bản API cũ.

## 2. Phân biệt hai lỗi trước khi sửa POM

| Tiêu chí | `NoSuchMethodError` | `NoClassDefFoundError` |
| --- | --- | --- |
| Điều JVM không tìm thấy | Một method có tên và **descriptor** phù hợp trên class đã resolve | Định nghĩa của một class mà bytecode hoặc class loader cần |
| Cấp kế thừa | `NoSuchMethodError → IncompatibleClassChangeError → LinkageError` | `NoClassDefFoundError → LinkageError` |
| Tình huống điển hình | Compile với thư viện v2 có `greet(String)`, runtime dùng v1 không có method đó | Compile với v2 có `Feature`, runtime chỉ có v1 không chứa `Feature.class` |
| Lỗi có thể xuất hiện khi nào? | Khi liên kết/thực thi lời gọi phương thức không tương thích | Khi JVM cần nạp hoặc dùng class, hoặc sau lỗi khởi tạo class |
| Nên kiểm tra đầu tiên | Class nào sở hữu method? Chữ ký nào được bytecode yêu cầu? JAR runtime nào chứa class đó? | Tên class thiếu, class loader, artifact cung cấp class, classpath và root cause |
| Có chắc do Maven chọn nhầm version? | Không, còn có thay đổi binary API, đóng gói hoặc runtime loader khác | Không, còn có classpath thiếu JAR, lỗi khởi tạo class hoặc lỗi deploy/container |

Hai loại này là **`Error`** thuộc nhánh `LinkageError`, không phải lỗi nghiệp vụ thông thường nên không nên “xử lý” bằng `catch` rồi tiếp tục chạy. Đúng hướng là làm cho bộ bytecode/classpath tương thích và phát hành artifact phù hợp.

### 2.1. Dấu hiệu đặc trưng của NoSuchMethodError

Trên Java 17, thông báo thường gần giống:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String demo.api.Greeter.greet(java.lang.String)'
    at demo.client.MethodDemo.main(MethodDemo.java:...)
~~~

Đây là **trích đoạn minh họa**; số dòng và cách trình bày phụ thuộc JDK và mã nguồn. JVM tìm được `demo.api.Greeter`, nhưng không tìm được method **có đúng chữ ký ở mức bytecode** mà client đang gọi.

Cần nhìn kỹ:

- **Class sở hữu method**: `demo.api.Greeter`.
- **Tên method**: `greet`.
- **Kiểu tham số**: `java.lang.String`.
- **Kiểu trả về**: `java.lang.String`.
- **Vị trí gọi**: `demo.client.MethodDemo.main`.

Chỉ thấy một method “cùng tên” trong source chưa đủ. Descriptor JVM còn phân biệt danh sách tham số và kiểu trả về; static/instance, visibility và kiểu class còn có những điều kiện linkage riêng. Ví dụ `greet()` **không thay thế** `greet(String)` chỉ vì cùng tên.

### 2.2. Dấu hiệu đặc trưng của NoClassDefFoundError

Ví dụ:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: demo/api/Feature
    at demo.client.ClassDemo.main(ClassDemo.java:...)
Caused by: java.lang.ClassNotFoundException: demo.api.Feature
    ...
~~~

Với tình huống này, `Feature` tồn tại khi client được biên dịch, nhưng classpath runtime không cung cấp định nghĩa mà JVM cần. `ClassNotFoundException` ở nhánh `Caused by` thường chỉ rõ class loader đã thử tải class nhưng thất bại.

**Cẩn thận:** `NoClassDefFoundError: Could not initialize class ...` có thể xuất hiện **sau khi một static initializer đã thất bại** (`ExceptionInInitializerError`). Khi đó class có thể **đang hiện diện trong JAR**; vấn đề là khởi tạo class bị lỗi. Phải đọc **lần lỗi đầu tiên và toàn bộ chuỗi `Caused by`**, không đoán rằng cứ `NoClassDefFoundError` thì thiếu dependency.

### 2.3. Khác gì với ClassNotFoundException?

- `ClassNotFoundException` là checked exception, thường từ API chủ động nạp class theo tên, ví dụ `Class.forName("...")` hoặc `ClassLoader.loadClass`.
- `NoClassDefFoundError` là `LinkageError` khi JVM không tìm/không dùng được định nghĩa một class mà bytecode cần, hoặc class từng thất bại khi khởi tạo.
- Một `NoClassDefFoundError` do thiếu class có thể chứa **`ClassNotFoundException` là nguyên nhân**; hai tên không đồng nghĩa.

Đừng dùng `-DskipTests` hoặc chỉ xóa cache Maven làm “bản sửa” cho hai lỗi này khi chưa xác định bytecode và classpath.

## 3. Vì sao Maven có thể chọn phiên bản khác mong muốn?

Maven đọc POM của các dependency và tạo đồ thị **transitive dependencies**. Ví dụ:

~~~text
my-app
├── legacy-adapter:1.0.0
│   └── demo.linkage:linkage-api:1.0.0
└── modern-client:1.0.0
    └── demo.linkage:linkage-api:2.0.0
~~~

Hai nhánh yêu cầu **cùng groupId/artifactId nhưng version khác**. Maven phải quyết định một phiên bản cho một conflict identity trong dependency resolution thông thường.

Cơ chế **dependency mediation** của Maven:

1. **Nearest definition wins**: phiên bản ở đường ngắn hơn từ project hiện tại thường được chọn.
2. Nếu hai đường ở **cùng độ sâu**, đường được khai báo trước theo thứ tự dependency thường thắng.
3. Khai báo dependency trực tiếp trong project giúp bạn kiểm soát phiên bản rõ hơn.
4. `<dependencyManagement>` trong effective POM có thể quản lý version của những dependency bắc cầu phù hợp và có ưu tiên so với mediation trong trường hợp áp dụng được.
5. Scope, optional, exclusions, profile và BOM cũng thay đổi **những đường phụ thuộc nào tham gia** đồ thị.

Trong ví dụ hai nhánh cùng sâu ở trên, thứ tự `legacy-adapter` và `modern-client` có thể quyết định phiên bản được chọn nếu không có quản lý hoặc declaration khác. Kết quả **không phải lúc nào cũng là version cao nhất**.

### Vì sao build vẫn có thể thành công?

Giả sử `modern-client` được build và publish **trước đó** bằng API 2.0. Ứng dụng `my-app` chỉ gọi method trong `modern-client` nên bản thân source của `my-app` **không tham chiếu trực tiếp** method mới của API 2.0. Maven lại chọn API 1.0 vì cây dependency. Compilation của `my-app` có thể không phát hiện việc method mà bytecode của `modern-client` cần không tồn tại trong API 1.0. Khi chạy tới nhánh code ấy, JVM mới báo `NoSuchMethodError`.

Tương tự, một class `Feature` chỉ có trong API 2.0 có thể bị thiếu lúc runtime do API 1.0 được chọn.

**Một nguyên nhân thứ hai, rất quan trọng:** Maven có thể **đã** chọn API 2.0 trong build, nhưng cách đóng gói/deploy hoặc classloader server lại đưa API 1.0 vào runtime. Khi đó dependency tree của build **đúng**, còn classpath thực tế **sai**.

Vì thế đừng dừng ở một kết quả `mvn dependency:tree`; khi cần phải kiểm tra luôn **JAR thực sự được JVM tải**.

## 4. Ví dụ tái lập Java 17 — ba dự án Maven độc lập

Ta sẽ tạo:

- `api-v1`: xuất bản artifact `demo.linkage:linkage-api:1.0.0`, có class `Greeter` nhưng **không có** `greet(String)` hoặc `Feature`.
- `api-v2`: xuất bản artifact `demo.linkage:linkage-api:2.0.0`, thêm `greet(String)` và class `Feature`.
- `client`: biên dịch với `linkage-api:2.0.0`, có hai chương trình riêng dùng hai API mới.

Sau đó ta **cố ý đổi classpath runtime sang JAR v1**, không sửa code client, để thấy lỗi tương ứng.

Thư mục:

~~~text
linkage-lab/
├── api-v1/
│   ├── pom.xml
│   └── src/main/java/demo/api/Greeter.java
├── api-v2/
│   ├── pom.xml
│   └── src/main/java/demo/api/
│       ├── Greeter.java
│       └── Feature.java
└── client/
    ├── pom.xml
    └── src/main/java/demo/client/
        ├── MethodDemo.java
        └── ClassDemo.java
~~~

**Không có parent POM tại thư mục gốc trong ví dụ này.** Mỗi `pom.xml` là một Maven project độc lập. Chúng được build theo thứ tự bằng `mvn -f ...` từ thư mục `linkage-lab/`, tránh nhầm với Maven Reactor có hai module cùng artifactId nhưng version khác.

### 4.1. Project api-v1 — POM đầy đủ

Tạo `api-v1/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.linkage</groupId>
    <artifactId>linkage-api</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `api-v1/src/main/java/demo/api/Greeter.java`:

~~~java
package demo.api;

public final class Greeter {
    private Greeter() {
    }

    public static String greet() {
        return "Hello from v1";
    }
}
~~~

API 1.0 chỉ có `greet()`. Nó **không** định nghĩa `greet(String)`. Đây là khác biệt sẽ dùng để tái hiện `NoSuchMethodError`.

### 4.2. Project api-v2 — POM đầy đủ

Tạo `api-v2/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.linkage</groupId>
    <artifactId>linkage-api</artifactId>
    <version>2.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `api-v2/src/main/java/demo/api/Greeter.java`:

~~~java
package demo.api;

public final class Greeter {
    private Greeter() {
    }

    public static String greet() {
        return "Hello from v1";
    }

    public static String greet(String name) {
        return "Hello " + name;
    }
}
~~~

API v2 giữ `greet()` và **bổ sung** overload `greet(String)`. Thay đổi này nhìn chung tương thích ngược với client chỉ sử dụng `greet()`, nhưng **client biên dịch với v2 và dùng overload mới** sẽ không chạy được với v1.

Tạo `api-v2/src/main/java/demo/api/Feature.java`:

~~~java
package demo.api;

public final class Feature {
    private Feature() {
    }

    public static String status() {
        return "Feature ready";
    }
}
~~~

Class `demo.api.Feature` chỉ tồn tại trong JAR v2. Khi client được biên dịch với v2 mà runtime dùng v1, class này sẽ không được tìm thấy.

### 4.3. Project client — POM đầy đủ

Tạo `client/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.linkage</groupId>
    <artifactId>linkage-client</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>demo.linkage</groupId>
            <artifactId>linkage-api</artifactId>
            <version>2.0.0</version>
            <scope>compile</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Chú ý:** `client` chỉ khai báo API 2.0, không khai báo API 1.0. Lệnh Maven build client sẽ resolve 2.0.0 từ local/remote repository. Việc chúng ta **cố tình thay JAR runtime thành 1.0.0** ở bước sau là một phép thử ngoài Maven để minh họa điều gì xảy ra khi classpath runtime khác classpath compile.

Tạo `client/src/main/java/demo/client/MethodDemo.java`:

~~~java
package demo.client;

import demo.api.Greeter;

public final class MethodDemo {
    private MethodDemo() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Maven"));
    }
}
~~~

Tạo `client/src/main/java/demo/client/ClassDemo.java`:

~~~java
package demo.client;

import demo.api.Feature;

public final class ClassDemo {
    private ClassDemo() {
    }

    public static void main(String[] args) {
        System.out.println(Feature.status());
    }
}
~~~

Hai class main được **tách riêng** để mỗi phép thử chỉ kiểm tra một lỗi, không phụ thuộc thứ tự JVM resolve class khác. Cả hai đều là chương trình Java 17 hợp lệ khi biên dịch với API v2.

## 5. Build cả ba project theo đúng thứ tự

Đứng tại thư mục `linkage-lab/`; máy cần Maven và **JDK 17+**.

Chạy:

~~~bash
mvn -B -ntp -f api-v1/pom.xml clean package
mvn -B -ntp -f api-v2/pom.xml clean install
mvn -B -ntp -f client/pom.xml clean package
~~~

Ý nghĩa từng lệnh:

1. Build **API v1**, tạo `api-v1/target/linkage-api-1.0.0.jar`. **Không cần install v1** để tạo lỗi minh họa.
2. Build **API v2** rồi `install` để cài version 2.0.0 vào Maven local repository, giúp project `client` resolve đúng version nó khai báo.
3. Build **client** với API v2, tạo bytecode tham chiếu `Greeter.greet(String)` và `Feature.status()`.

Nếu cả ba thành công, Maven in `BUILD SUCCESS` cho từng lần build. Lệnh `mvn package` **không tự chạy** `main` của hai class client. Chúng ta sẽ chạy Java thủ công sau.

Dù cùng `groupId`/`artifactId`, v1 và v2 có **version khác nhau** nên chúng là hai artifact được Maven lưu ở hai tọa độ/version khác nhau. `client` chỉ yêu cầu API v2; `api-v1` có thể tồn tại trên disk nhưng không được Maven đưa vào compile classpath của client.

Các phiên bản Maven Compiler Plugin chỉ là phiên bản được cố định cho ví dụ, không hàm ý đây là bản mới nhất.

## 6. Chạy với API 2.0: hai chương trình đều đúng

### 6.1. Linux/macOS/Bash

Tại thư mục `linkage-lab/`, dấu phân cách classpath là dấu **`:`**:

~~~bash
java -cp "client/target/classes:api-v2/target/linkage-api-2.0.0.jar" demo.client.MethodDemo
java -cp "client/target/classes:api-v2/target/linkage-api-2.0.0.jar" demo.client.ClassDemo
~~~

Stdout của lệnh thứ nhất:

~~~text
Hello Maven
~~~

Stdout của lệnh thứ hai:

~~~text
Feature ready
~~~

### 6.2. Windows PowerShell hoặc CMD

Trên Windows, dấu phân cách classpath là dấu **`;`**, còn các dấu `/` trong đường dẫn ví dụ vẫn được Java chấp nhận:

~~~powershell
java -cp "client/target/classes;api-v2/target/linkage-api-2.0.0.jar" demo.client.MethodDemo
java -cp "client/target/classes;api-v2/target/linkage-api-2.0.0.jar" demo.client.ClassDemo
~~~

Hai lệnh có kết quả chương trình giống Linux/macOS.

Kết luận từ lượt chạy đúng: code của client đã biên dịch thành công và chạy được **khi API 2.0 thực sự có trên runtime classpath**. Đây là trạng thái gốc để so sánh với lượt cố ý gây lỗi.

## 7. Chạy sai phiên bản: tái hiện NoSuchMethodError

Giữ nguyên `client/target/classes`, **chỉ thay API 2.0 bằng API 1.0** trên classpath.

Linux/macOS:

~~~bash
java -cp "client/target/classes:api-v1/target/linkage-api-1.0.0.jar" demo.client.MethodDemo
~~~

Windows:

~~~powershell
java -cp "client/target/classes;api-v1/target/linkage-api-1.0.0.jar" demo.client.MethodDemo
~~~

Kỳ vọng JVM báo gần dạng:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String demo.api.Greeter.greet(java.lang.String)'
    at demo.client.MethodDemo.main(MethodDemo.java:...)
~~~

Không đóng khung số dòng cụ thể; stack trace tùy cách biên dịch và phiên bản JVM. **Không có stdout `Hello Maven`** vì JVM gặp lỗi lúc liên kết lời gọi trước khi `System.out.println` có thể in kết quả.

Nguyên nhân theo từng bước:

1. Khi compile, `MethodDemo.class` được tạo dựa trên API v2, nên trong bytecode có lời gọi `Greeter.greet(String)`.
2. Khi chạy, JVM tìm và load `demo.api.Greeter` **từ API v1**.
3. Class v1 vẫn tồn tại, nhưng chỉ có `greet()`, không có overload nhận `String`.
4. JVM không liên kết được symbolic reference tới method mong đợi và phát sinh `NoSuchMethodError`.

Đây **không phải** lỗi dấu ngoặc Java hay Java compiler. Bytecode client hợp lệ với v2; môi trường chạy không phù hợp với hợp đồng binary mà bytecode yêu cầu.

**Hành động sửa đúng trong ví dụ:** trả runtime classpath về API v2 hoặc build lại client sao cho API sử dụng tương thích với bản runtime được hỗ trợ. Không sửa `maven.compiler.release` để chữa mismatch giữa hai JAR.

## 8. Chạy sai phiên bản: tái hiện NoClassDefFoundError

Tiếp tục dùng API v1 ở runtime, nhưng chạy chương trình thứ hai.

Linux/macOS:

~~~bash
java -cp "client/target/classes:api-v1/target/linkage-api-1.0.0.jar" demo.client.ClassDemo
~~~

Windows:

~~~powershell
java -cp "client/target/classes;api-v1/target/linkage-api-1.0.0.jar" demo.client.ClassDemo
~~~

Kỳ vọng trace gần dạng:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: demo/api/Feature
    at demo.client.ClassDemo.main(ClassDemo.java:...)
Caused by: java.lang.ClassNotFoundException: demo.api.Feature
    ...
~~~

Vì sao?

1. `ClassDemo.class` được biên dịch khi `demo.api.Feature` có trong API v2.
2. JAR API v1 ở runtime **không chứa** `demo/api/Feature.class`.
3. Khi JVM cần định nghĩa class đó để gọi `status()`, nó không tìm được và báo `NoClassDefFoundError`.
4. Khi đổi lại classpath sang API v2, `Feature.class` có mặt và lệnh in `Feature ready`.

Chú ý thông báo `demo/api/Feature` sử dụng dấu `/` vì tên nội bộ của JVM, trong khi source Java viết `demo.api.Feature` với dấu chấm. Khi tìm file trong JAR, cần tìm entry `demo/api/Feature.class`.

Hai phép thử chứng minh khác biệt quan trọng:

- **NoSuchMethodError:** class có mặt, method signature không có.
- **NoClassDefFoundError:** class được yêu cầu không có trong classpath runtime (đối với ví dụ này).

## 9. Dùng javap để so chữ ký thật trong hai bản JAR

Khi gặp `NoSuchMethodError`, tên method trong stack trace là đầu mối, nhưng cần kiểm tra **bytecode descriptor**.

Dùng công cụ `javap` của JDK 17:

~~~bash
javap -classpath api-v1/target/linkage-api-1.0.0.jar -s demo.api.Greeter
javap -classpath api-v2/target/linkage-api-2.0.0.jar -s demo.api.Greeter
~~~

Trong output v1, sẽ có method:

~~~text
public static java.lang.String greet();
  descriptor: ()Ljava/lang/String;
~~~

Trong output v2, ngoài `greet()` còn có:

~~~text
public static java.lang.String greet(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
~~~

`-s` yêu cầu javap in **JVM method descriptor**, thứ giúp xác định sự tương thích ở mức bytecode, không chỉ nhìn source. Descriptor `(Ljava/lang/String;)Ljava/lang/String;` nghĩa là một tham số `String`, trả về `String`. Descriptor này không khớp với `()Ljava/lang/String;` của bản v1.

Để xem bytecode client thực sự gọi gì:

~~~bash
javap -classpath client/target/classes -c -p demo.client.MethodDemo
~~~

Trong phần `main`, một dòng hướng tới `invokestatic ... Greeter.greet:(Ljava/lang/String;)Ljava/lang/String;` sẽ cho thấy lời gọi tới API v2 mà client đã mã hóa. Dạng ghi chỉ số constant pool có thể khác, nên tìm **tên method và descriptor**, không học thuộc offset bytecode.

Đối với `NoClassDefFoundError`, kiểm tra JAR bằng `jar tf`:

~~~bash
jar tf api-v1/target/linkage-api-1.0.0.jar
jar tf api-v2/target/linkage-api-2.0.0.jar
~~~

Bản v1 có `demo/api/Greeter.class` nhưng không có `demo/api/Feature.class`. Bản v2 có cả hai class. Đây là bằng chứng trực tiếp về sự khác nhau của artifact; không cần đoán từ tên JAR “1.0” hay “2.0”.

**Nếu artifact thực tế là shaded/relocated JAR**, tên package trong class có thể được đổi. Khi đó phải kiểm tra class entry sau relocation, chứ không chỉ dùng tên nguyên thủy trong POM.

## 10. Dùng dependency:tree để tìm version được Maven chọn

Bài thực hành ở trên cố ý thay classpath bằng tay. Trong dự án thật, một nguyên nhân phổ biến là Maven đã chọn phiên bản transitive khác với phiên bản mà một module/thư viện được biên dịch dựa vào.

Trước tiên chạy trong **đúng project đang gặp lỗi**:

~~~bash
mvn -B -ntp dependency:tree
~~~

Để kết quả tái lập không phụ thuộc version alias của plugin, có thể ghim Maven Dependency Plugin:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Đây là lệnh đọc đồ thị, không thêm/xóa dependency trong POM.

### 10.1. Lọc theo group/artifact có vấn đề

Nếu stack trace nhắc `demo.api.Greeter`, đã xác định `demo.linkage:linkage-api` là artifact nghi vấn, có thể dùng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=demo.linkage:linkage-api
~~~

Plugin lọc serialization theo pattern GAV; cú pháp đầy đủ cho phép groupId/artifactId/type/version. Dùng ID từ POM/metadata của artifact, **không** dùng tên class làm pattern của `dependency:tree`.

Với một ứng dụng có xung đột, hãy chú ý version **được giữ lại** và đường từ project root tới artifact đó. Trích đoạn *minh họa*:

~~~text
demo.linkage:service:jar:1.0.0
+- demo.linkage:legacy-adapter:jar:1.0.0:compile
|  \- demo.linkage:linkage-api:jar:1.0.0:compile
\- demo.linkage:modern-client:jar:1.0.0:compile
~~~

Nếu Maven chọn API 1.0 do mediation, dependency tree dạng mặc định thường chỉ cho thấy đường được chọn; **đừng suy ra modern-client không có nhu cầu API 2.0** chỉ vì bản 2.0 không hiện ở output ngắn.

### 10.2. Hiển thị node bị bỏ vì xung đột

Theo tài liệu Maven Dependency Plugin 3.11.0, goal `tree` có tham số `verbose` để thêm các node bị bỏ khỏi cây resolve:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
~~~

Với graph minh họa, ta có thể thấy giải thích đại ý:

~~~text
demo.linkage:modern-client:jar:1.0.0:compile
  \- (demo.linkage:linkage-api:jar:2.0.0:compile - omitted for conflict with 1.0.0)
~~~

Thông điệp trên chỉ **minh họa ý nghĩa của node bị loại**; không phải stdout thực tế của một project đã chạy. Phiên bản cũ của Dependency Plugin có thời kỳ không hỗ trợ `verbose` ổn định, nên khi cần lặp lại chẩn đoán hãy kiểm tra version/goal đang sử dụng và tài liệu của chính phiên bản đó. Ví dụ ở đây cố định `3.11.0` để giảm mơ hồ.

Nếu dự án lớn, xuất graph ra file:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -DoutputType=json -DoutputFile=dependency-tree.json
~~~

Định dạng JSON được plugin hỗ trợ ở các phiên bản mới hơn; nó hữu ích để so sánh hai lần build nhưng cũng có thể chứa tọa độ/artifact nội bộ. Không công khai toàn bộ nếu không cần thiết.

### 10.3. Chú ý scope và project/module

`dependency:tree` phải chạy tại module đúng: classpath của `app` có thể khác classpath của `library`. Với multi-module Reactor, có thể dùng `-pl` hoặc `-f` để chọn module, cùng các cờ môi trường mà build lỗi đã sử dụng:

~~~bash
mvn -B -ntp -pl :my-app -Pci dependency:tree
~~~

Lệnh này là **mẫu dành cho project có module artifactId `my-app` và profile `ci` hợp lệ**; không dùng nguyên trong project ví dụ ba POM độc lập. Khi cần resolve local reactor artifacts, `-am` có thể build cả các module mà project chọn phụ thuộc; tùy goal và kiến trúc, có thể cần `install` các module local trước.

Đừng kết luận một dependency không có trong runtime chỉ vì nó không được hiển thị bởi **bộ lọc scope hoặc includes** đang dùng. Nếu chưa rõ, xem cây đầy đủ.

## 11. Nhìn dependency graph thôi chưa đủ: kiểm tra class thật được JVM load

Đây là bước phân biệt **Maven đã chọn gì** với **JVM thực sự tải gì**. Java 17 hỗ trợ unified logging để theo dõi class loading:

Linux/macOS, dùng API v1 cố ý:

~~~bash
java -Xlog:class+load=info -cp "client/target/classes:api-v1/target/linkage-api-1.0.0.jar" demo.client.MethodDemo
~~~

Windows:

~~~powershell
java -Xlog:class+load=info -cp "client/target/classes;api-v1/target/linkage-api-1.0.0.jar" demo.client.MethodDemo
~~~

Log có nhiều class JDK. Hãy tìm dòng nhắc `demo.api.Greeter` và nguồn đã nạp, ví dụ một URL kiểu `file:/.../linkage-api-1.0.0.jar`. **Đường dẫn cụ thể tùy máy**, không có một output cố định.

Nếu application container/classloader đặc biệt, `-Xlog:class+load` thường vẫn cung cấp dấu vết class load, nhưng cơ chế URL, module layer, nested JAR loader hoặc custom classloader có thể hiển thị khác. Có thể cần log của framework/container để biết thứ tự ưu tiên classloader.

Một cách khác là in `CodeSource` từ chính ứng dụng, **chỉ thêm khi được phép sửa code để chẩn đoán**:

~~~java
System.out.println(
        demo.api.Greeter.class
                .getProtectionDomain()
                .getCodeSource()
                .getLocation()
);
~~~

Đoạn này là **một biểu thức minh họa đặt trong method Java**, không phải tệp chương trình độc lập. Nó có thể in URL chứa class `Greeter`. Với một số class JDK/classloader, `getCodeSource()` có thể là `null`; không áp dụng máy móc cho mọi class. Không cho phép chèn log đường dẫn nội bộ vào bản production nếu không cần.

**Không sử dụng duy nhất tên file JAR để chứng minh JVM đã tải nó.** Hai file có thể cùng tên ở thư mục khác, hoặc container có cache/parent classloader tải class trước bản đi kèm ứng dụng.

## 12. Trường hợp Java 17 nói rõ method descriptor mà source không nói hết

Khi JVM link một lời gọi method, nó dùng symbolic reference trong constant pool. Thay đổi API có thể không tương thích theo nhiều cách:

| Thay đổi ở thư viện | Rủi ro lúc chạy client cũ | Dạng lỗi có thể gặp |
| --- | --- | --- |
| Xóa method hoặc đổi tên | Client vẫn gọi symbol cũ | `NoSuchMethodError` |
| Đổi kiểu tham số hoặc kiểu trả về | Descriptor không còn phù hợp | Có thể `NoSuchMethodError` |
| Đổi static method thành instance hoặc ngược lại | Cách gọi trong bytecode không phù hợp | Có thể `IncompatibleClassChangeError` |
| Hạ độ truy cập method/class | Symbol còn nhưng client không được phép truy cập | Có thể `IllegalAccessError` |
| Xóa/đổi tên class | Class mà client cần không tồn tại | Có thể `NoClassDefFoundError` |
| Method thân cũ gọi một class transitive đã biến mất | Class phụ chỉ được cần khi nhánh chạy | Có thể `NoClassDefFoundError` |
| Dependency version sai nhưng API tương thích | Không nhất thiết lỗi | Có thể chạy bình thường; vẫn nên kiểm chứng |
| Thư viện trùng class ở nhiều JAR | Classloader chọn bản khác mong đợi | Nhiều lỗi linkage tùy class được chọn |

Không cứ thay đổi signature là chắc chắn `NoSuchMethodError`; lỗi cụ thể còn phụ thuộc opcode, quyền truy cập, inheritance, interface/class kind và class loader. Nhưng nếu stack trace đã cho descriptor cần tìm, **`javap -s`** là công cụ mạnh để kiểm chứng.

Trường hợp method bị overload không tương thích có thể gây nhầm: trong ví dụ, v2 vẫn có `greet()`, nên chỉ tìm từ khóa “greet” trong source hoặc log là chưa đủ. Phải kiểm tra **`greet(java.lang.String)`**, tức chữ ký được client yêu cầu.

## 13. Lệch phiên bản ở những đâu ngoài POM?

| Nơi lệch | Ví dụ tình huống | Dấu hiệu |
| --- | --- | --- |
| Maven transitive conflict | A/B kéo cùng artifact các version khác nhau | `dependency:tree` và mediation chọn bản không mong muốn |
| `dependencyManagement`/BOM | Parent/BOM ép version khác version thư viện được compile/test | Effective POM khác POM con hoặc dependency tree khác dự kiến |
| Scope `provided` | Compile có API nhưng runtime container không cung cấp | Test local chạy, deploy thiếu class |
| Scope `runtime`/`test` sai | Launcher không đưa một JAR cần thiết vào app runtime | `NoClassDefFoundError` khi chạy |
| Shade/Assembly/exclusion | JAR cuối bị loại class, merge sai hoặc mang bản cũ | `jar tf` không có class/entry cần thiết |
| Spring Boot/nested JAR | `BOOT-INF/lib` chứa phiên bản khác hoặc cách chạy khác | Build graph và nội dung executable JAR không khớp |
| WAR/Servlet container | `WEB-INF/lib` có API mới nhưng server parent loader cung cấp API cũ | Lỗi chỉ trên server cụ thể |
| `java -cp` tự tạo | Quên thêm runtime dependency hoặc xếp JAR cũ trước | Maven `exec:java` chạy, lệnh Java thủ công lỗi |
| Classloader/plugin realm | Maven plugin hoặc agent chạy class trong realm riêng | Lỗi nằm trong goal/plugin, không ở app runtime |
| Cache/triển khai cũ | Server vẫn chạy file JAR trước, container image tag bị tái sử dụng | Build mới đúng nhưng process đang chạy nạp bản cũ |
| Duplicate classes/relocation | Hai JAR cung cấp cùng FQCN hoặc shade đổi package | Kết quả phụ thuộc classloader/đóng gói |

**Lưu ý:** `mvn dependency:tree` phản ánh **dependency graph của project Maven tại thời điểm gọi goal**. Nó không tự đọc cấu trúc image Docker đang chạy, toàn bộ WAR/container libraries, module-path tùy chỉnh hoặc các JAR được nạp động sau đó.

Khi lỗi chỉ xuất hiện sau deploy, cần kết hợp Maven với **inspect artifact** và **điều tra môi trường runtime**. Chỉ ép Maven chọn một version mới hơn chưa chắc sửa được classloader cũ hoặc image chưa được thay.

## 14. Sửa lỗi đúng cách bằng khai báo trực tiếp và dependencyManagement

Khi đã xác định phiên bản an toàn, có thể buộc project dùng version phù hợp.

### 14.1. Khai báo dependency trực tiếp

Trong `<dependencies>` của project ứng dụng (đây là **đoạn POM**, không phải XML độc lập):

~~~xml
<dependency>
    <groupId>demo.linkage</groupId>
    <artifactId>linkage-api</artifactId>
    <version>2.0.0</version>
    <scope>compile</scope>
</dependency>
~~~

Declaration trực tiếp cho Maven một đường gần root tới API 2.0 và làm yêu cầu API của ứng dụng minh bạch. Nhưng **đừng cập nhật lên version mới chỉ vì số lớn hơn**: một framework hoặc thư viện khác có thể không tương thích. Cần xem release notes, binary compatibility và test theo toàn bộ graph.

### 14.2. Quản lý thống nhất trong parent POM

Ví dụ đoạn trong `<project>` của parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.linkage</groupId>
            <artifactId>linkage-api</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Các module kế thừa parent được quản lý version theo quy tắc Maven. Phần này **không tự thêm** API vào classpath nếu không có đường dependency hợp lệ. Nếu module trực tiếp khai báo một version khác, cần kiểm tra cách direct declaration và management tương tác trong effective POM; không khẳng định dependency management luôn ghi đè mọi version trực tiếp.

Ưu điểm là dễ cố định version áp dụng cho nhiều module thay vì dựa vào “nearest wins” thay đổi theo thứ tự POM. Trong dự án có BOM của framework, nên tuân theo BOM đã kiểm thử hoặc sử dụng một BOM chung có chính sách nâng cấp thay vì phối hợp nhiều BOM gây chồng chéo không rõ.

### 14.3. BOM import

Đoạn dùng trong `<dependencyManagement>`:

~~~xml
<dependency>
    <groupId>example.platform</groupId>
    <artifactId>platform-bom</artifactId>
    <version>1.0.0</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
~~~

`example.platform:platform-bom:1.0.0` ở đây chỉ là **tọa độ minh họa**, không cam kết artifact tồn tại trên Maven Central. BOM giúp quản lý nhiều version nhất quán khi có BOM thật do framework/tổ chức phát hành. Nó không tự kiểm tra binary compatibility hoặc bổ sung runtime JAR nếu không được khai báo.

### 14.4. Exclusion có chủ đích

Khi một dependency mang theo bản không phù hợp, bạn có thể exclude một đường cụ thể:

~~~xml
<dependency>
    <groupId>demo.linkage</groupId>
    <artifactId>legacy-adapter</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>demo.linkage</groupId>
            <artifactId>linkage-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là **đoạn POM**. Exclusion chặn `linkage-api` qua **đường legacy-adapter**, không xóa mọi đường khác trên graph. Nếu adapter thực sự đòi API v1, ép nó chạy với API v2 phải được thử tương thích; không xóa bừa rồi coi build xanh là đủ.

Nếu một dependency là `optional`, project tiêu thụ không tự nhận nó qua transitivity. Lỗi `NoClassDefFoundError` có thể xuất hiện khi code dùng nhánh tùy chọn mà app chưa khai báo dependency cung cấp class đó. Khi đó **thêm dependency trực tiếp đúng scope** thường rõ ràng hơn việc sửa bản thân library.

## 15. Kiểm tra lại scope, exclusions và packaging trước khi đổi version

Nhiều lỗi `NoClassDefFoundError` là **thiếu classpath**, không nhất thiết sai version. Trước khi nâng cấp, kiểm tra:

- **`compile`**: có ở main compile, test và runtime classpath theo Maven.
- **`runtime`**: không cần main compile, nhưng có ở test và runtime classpath.
- **`provided`**: có ở compile/test nhưng **không** được Maven đưa vào application runtime classpath thông thường, vì môi trường được kỳ vọng cung cấp.
- **`test`**: chỉ dùng cho test, không là application runtime dependency.
- **`optional=true`**: không tự truyền từ thư viện sang project tiêu thụ qua đường bắc cầu đó.
- **`exclusions`**: chặn một dependency qua một cạnh đã khai báo.
- **`import`** của BOM: chỉ quản lý version, không thêm class.
- **`system`**: phụ thuộc đường dẫn file cục bộ, dễ không tái lập; nên tránh.

Ví dụ nếu ứng dụng compile bằng `jakarta.servlet-api` scope `provided`, servlet container phải thật sự cung cấp API tương thích. Nếu chạy WAR ở container khác version API, có thể phát sinh linkage error. Không giải quyết bằng cách đổi sang `compile` mà không xem chính sách packaging/classloader của container.

Một **thin JAR** Maven thông thường không đóng tất cả dependency bên trong; vì vậy lệnh `java -cp target/classes ...` sẽ thiếu thư viện nếu không có đầy đủ JAR trong classpath. `java -jar app.jar` cũng không tự nạp những JAR Maven đã resolve, trừ khi manifest/launcher hoặc packaging cụ thể thiết lập điều đó.

**Kiểm tra file cuối:** dùng `jar tf target/your-app.jar` hoặc tool thích hợp cho WAR/fat JAR. Với executable JAR của framework, tìm thư viện dưới thư mục nested JAR tương ứng; đừng coi nội dung của `target/classes` là bằng chứng toàn bộ artifact có đúng dependency.

## 16. Những lớp kiểm tra bổ sung trong dự án nhiều module

Dự án multi-module có thể build nhiều thư viện trong Reactor, nhưng khi phát hành, ứng dụng lại phụ thuộc artifact đã publish trước đó. Một số nguyên nhân khó thấy:

- Module A dùng API v2, module B lại ghim API v1 thông qua `dependencyManagement` riêng.
- Parent đã nâng version nhưng một child `pom.xml` khai báo direct version cũ.
- CLI dùng `-pl`, `-am`, `-P`, `-D`, hoặc settings khác nhau ở local và CI.
- Library của bên thứ ba được compile với dependency version mới hơn version cuối do ứng dụng chọn.
- Artifact cache của Maven local repository hoặc repository manager chưa được đồng bộ với source mà build hiện tại dựa vào.
- Runtime deployment không dùng JAR vừa build, dù build log thành công.

Công cụ hữu ích:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
mvn -B -ntp dependency:tree
mvn -B -ntp dependency:analyze
~~~

`help:effective-pom` giúp tìm version quản lý và plugin config sau inheritance/profile. `dependency:tree` giúp quan sát version resolve. `dependency:analyze` tìm một số “used undeclared dependencies” và “unused declared dependencies”, nhưng phân tích bytecode có thể không nhận ra reflection, service loader hoặc dynamic plugin loading; **không xóa dependency chỉ dựa trên một cảnh báo**.

Chạy chẩn đoán ở **module có lỗi** với đúng project, Maven/JDK, profile, settings như build thật. Nếu classpath runtime khác build graph, hãy chuyển sang kiểm tra launcher/container; không quay vòng chỉnh sửa POM vô mục đích.

## 17. Enforcer rules và kiểm soát lệch phiên bản từ CI

Maven Enforcer Plugin có các quy tắc hữu ích:

- **`dependencyConvergence`**: có thể làm build fail khi cùng dependency xuất hiện qua các nhánh với version không đồng nhất, giúp nhìn thấy nơi cần chốt dependency management.
- **`requireUpperBoundDeps`**: kiểm tra version được resolve có thấp hơn version cao nhất mà các đường dependency liên quan yêu cầu hay không, theo quy tắc của rule.

Đây là **hai phép kiểm tra khác nhau**. `dependencyConvergence` chú trọng tính hội tụ giữa các đường; `requireUpperBoundDeps` chú trọng điều kiện upper bound. Cả hai **không bảo đảm tuyệt đối** binary compatibility, vì version “cao nhất” vẫn có thể xóa API cũ hoặc framework yêu cầu version khác.

Đoạn plugin có thể đặt trong `<build><plugins>` của POM phù hợp:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.7.0</version>
    <executions>
        <execution>
            <id>check-dependency-conflicts</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                    <requireUpperBoundDeps/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây không phải POM hoàn chỉnh. Goal `enforcer:enforce` thường chạy tại phase `validate` theo default binding của goal, nên lỗi conflict có thể được phát hiện **trước compile/package**. Trên project lớn, một số thư viện của framework tạo nhiều đường yêu cầu version khác nhau; phải đánh giá rule theo policy, dùng dependency management/exclusions có lý do hoặc cấu hình điều kiện phù hợp, không tắt mọi rule cho build xanh.

Một quy trình CI đáng tin gồm cả **test chạy trong môi trường runtime tương ứng** sau khi Maven resolve và đóng gói. Enforcer chỉ nhìn dependency graph mà nó kiểm tra; container khác hoặc JAR bị thay sau build vẫn có thể gặp linkage error.

## 18. “BUILD SUCCESS” không đồng nghĩa tương thích ở production

Vì sao compiler chưa bắt lỗi? Khi compile một module, Java compiler kiểm tra source và những API **có trên compile classpath lúc đó**. Nó không thể khẳng định mọi thư viện khác đã được compile trước sẽ tìm đúng version khi ứng dụng được deploy sau này.

Một ma trận kiểm tra thực tế:

| Kiểm tra | Bắt được vấn đề gì | Không bắt được gì một cách mặc định |
| --- | --- | --- |
| `mvn compile` | Source hiện tại không thể compile với dependency compile đã chọn | Runtime classpath khác, method chỉ được gọi trong binary của thư viện khác |
| `mvn test` | Lỗi trong các unit test thực sự chạy | Nhánh chưa được test, classloader của production |
| `mvn verify` | Các goal kiểm chứng đã được bind và thực thi | Không tự đảm bảo có integration/binary compatibility tests |
| `dependency:tree` | Version/scope/path Maven resolve cho project | JAR thực tế mà server/custom launcher đã tải |
| `javap` | Class và method descriptor có trong bytecode/JAR | Chính JVM đang sử dụng file JAR nào |
| `-Xlog:class+load` | Nguồn class JVM đã load trong lần chạy đang xét | Không giải thích tự động vì sao Maven chọn version ấy |
| Smoke test artifact thực | Lỗi khi chạy artifact đóng gói đúng launcher | Tất cả kịch bản production nếu coverage chưa đủ |

Với library được phát hành cho bên thứ ba, kiểm tra API/binary compatibility giữa bản trước và bản mới bằng công cụ chuyên dụng như **Revapi** hoặc **japicmp** (nếu áp dụng cho dự án) cũng hữu ích. Những công cụ này cần cấu hình thích hợp; Maven không tự chạy chúng chỉ nhờ có pha `verify`.

**Không dùng test skip** để khắc phục linkage error. Với môi trường bị lỗi sau deploy, cần một kiểm tra chạy bằng đúng artifact/launcher/classpath mà người dùng sẽ sử dụng, không chỉ test classpath của Maven.

## 19. Quy trình chẩn đoán có thể áp dụng ngay

### Bước 1 — Chốt lỗi và artifact đúng thời điểm

Ghi lại:

- Lớp lỗi chính xác: `NoSuchMethodError` hay `NoClassDefFoundError`.
- Tên class/method/descriptor (nếu có) từ stack trace.
- `Caused by`, đặc biệt `ClassNotFoundException` hoặc `ExceptionInInitializerError`.
- Build ID, Git commit, version artifact, image tag/digest và môi trường đang lỗi.
- JDK/Maven version, lệnh Maven, profile `-P`, settings `-s` và module.

Tránh chỉ chụp ảnh một dòng `BUILD FAILURE` hoặc dán stack trace đã cắt mất `Caused by`.

### Bước 2 — Xác định class nằm trong artifact nào

Tìm theo tài liệu dependency hoặc repository metadata. Kiểm tra với `jar tf` từng JAR nghi vấn. Trong ví dụ:

~~~bash
jar tf api-v1/target/linkage-api-1.0.0.jar
jar tf api-v2/target/linkage-api-2.0.0.jar
~~~

Đối chiếu `demo/api/Feature.class`. Với method, dùng `javap -classpath ... -s ...` để xác nhận signature. **Đừng chọn artifact chỉ bằng tên package giống nhau**; một số thư viện đã đổi artifactId/groupId hoặc đưa class qua shaded JAR.

### Bước 3 — Kiểm tra dependency graph Maven

~~~bash
mvn -B -ntp dependency:tree
mvn -B -ntp dependency:tree -Dverbose=true
~~~

Nếu phiên bản plugin hiện tại không hỗ trợ tham số mà bạn cần, pin plugin có tài liệu hỗ trợ, ví dụ `3.11.0` như ở mục 10. Tìm **đường gần nhất**, cùng độ sâu, dependency management, BOM, scope, optional và exclusions.

### Bước 4 — Đối chiếu với classpath runtime

Kiểm tra:

- Lệnh `java -cp` hoặc `java -jar` thực sự dùng.
- JAR/WAR/fat JAR có chứa dependency được kỳ vọng hay không.
- Class nào JVM load và từ file nào qua `-Xlog:class+load=info` trong môi trường kiểm soát.
- Container/application server có thư viện riêng/parent loader được ưu tiên không.
- Có cache hoặc artifact cũ đang được sử dụng thay cho build mới không.

Đây là bước quyết định nếu `dependency:tree` cho version đúng nhưng runtime vẫn báo lỗi.

### Bước 5 — Sửa nguyên nhân nhỏ nhất có thể kiểm chứng

Các cách sửa phổ biến:

- Khai báo trực tiếp đúng dependency/version.
- Dùng một parent/BOM/dependencyManagement nhất quán để tránh mediation tình cờ.
- Xem xét `exclusions` nếu một nhánh không nên kéo artifact cũ.
- Đảm bảo launcher/container dùng JAR đúng và không còn duplicate class.
- Đổi scope về `compile` hoặc `runtime` khi class cần ở runtime và không có provider thực.
- Chọn một cặp thư viện tương thích theo tài liệu framework và kiểm thử, không chỉ “lấy version mới nhất”.
- Rebuild và redeploy **artifact thực sự đã được kiểm chứng**, không tái sử dụng output cũ.

### Bước 6 — Chạy test hồi quy

Thực hiện build sạch và test phù hợp:

~~~bash
mvn -B -ntp clean verify
~~~

Sau đó chạy **chính artifact đã build** với launcher và dependency set dự kiến. Một unit test đơn thuần có thể không đi tới nhánh method/class đang lỗi, nên cần integration/smoke test tái hiện đường code đó. Chỉ tuyên bố sửa thành công sau khi lỗi ban đầu không còn xảy ra ở đúng môi trường.

## 20. Khi NoClassDefFoundError không phải do thiếu JAR

Không phải mọi `NoClassDefFoundError` đều do dependency bị bỏ ra khỏi classpath. Một tình huống khác là class **đã tồn tại** nhưng quá trình khởi tạo static thất bại.

Ví dụ minh họa class:

~~~java
package demo.fail;

public final class BrokenConfig {
    static {
        if (System.getProperty("required.config") == null) {
            throw new IllegalStateException("required.config is missing");
        }
    }

    private BrokenConfig() {
    }

    public static String name() {
        return "ready";
    }
}
~~~

Đoạn này **chỉ là class minh họa**, không phải project thực hành thứ tư cần build. Lần đầu chạm vào `BrokenConfig` trong một JVM không có system property `required.config`, quá trình class initialization có thể báo `ExceptionInInitializerError` với nguyên nhân `IllegalStateException`. Sau đó, lần sử dụng lại class trong cùng class loader có thể báo `NoClassDefFoundError: Could not initialize class demo.fail.BrokenConfig`.

Ở đây thêm một JAR nữa không chữa được. Cần sửa cấu hình runtime hoặc nguyên nhân trong static initialization. Vì vậy khi gặp thông điệp `Could not initialize class`, phải tìm **root cause của lần khởi tạo đầu tiên**, đặc biệt trong log trước đó.

Bên cạnh đó, `NoClassDefFoundError` có thể xảy ra khi một class hiện diện trong JAR nhưng phụ thuộc **class cha/interface hoặc field type khác** đã biến mất. Khi đó class được nêu trong trace có thể không phải artifact duy nhất cần rà soát. Đọc toàn bộ cause chain và classloader log.

## 21. Phân biệt lỗi trong ứng dụng, plugin và test runner

Maven có nhiều loại classpath/classloader:

- **Project compile classpath**: các dependency mã chính dùng để biên dịch.
- **Project test classpath**: mã chính, mã test, dependency test.
- **Application runtime classpath**: những dependency được launcher/container dùng để chạy.
- **Plugin realm**: các dependency của chính Maven plugin, có cơ chế quản lý riêng.
- **Application server/container classloader**: có thể cung cấp API/JAR khác với dự án.

Nếu lỗi xảy ra ở `maven-surefire-plugin` hoặc plugin khác **trước khi ứng dụng khởi chạy**, hãy kiểm tra plugin version và plugin dependencies. `<dependencyManagement>` của project **không tự quản lý mọi transitive dependency của plugin**. Đổi dependency của `<dependencies>` không chắc chữa lỗi nằm trong plugin realm.

Nếu lỗi chỉ xuất hiện trong test, nhớ Surefire/Failsafe có test classpath và fork/classloader riêng. Một dependency `test` có thể hiện diện khi test chạy nhưng vắng mặt ở application runtime; ngược lại, lỗi ở production có thể không tái hiện nếu test classpath vô tình chứa một bản JAR phù hợp khác.

Nếu lỗi xảy ra trong servlet container, trước khi đổi scope `provided`, hãy đối chiếu JAR trong `WEB-INF/lib` với classloader của container và chính sách phiên bản. Một fix tốt phải bảo đảm không có hai bản không tương thích cùng cạnh tranh trong classloader theo cách khó kiểm soát.

## 22. Cảnh báo về xóa cache và dùng snapshot

Xóa `~/.m2/repository` hoặc chạy `mvn -U` đôi khi làm thay đổi kết quả vì dependency được tải lại, nhưng:

- **`-U` không sửa logic mediation** nếu POM vẫn chọn version sai.
- Xóa toàn bộ local repository có thể tốn thời gian, tăng tải mạng và **không chữa** JAR cũ trong Docker image/server.
- Với **`-SNAPSHOT`**, cùng version string có thể trỏ tới binary khác theo thời gian; cần xem timestamp/build ID/checksum/provenance, không chỉ ghi “SNAPSHOT giống nhau”.
- Một artifact release lý tưởng có tính bất biến; không tùy tiện ghi đè nội dung binary đã phát hành dưới cùng GAV để “vá nhanh”.

Khi nghi cache hỏng hoặc bản SNAPSHOT cũ, kiểm tra hash/metadata và chỉ làm sạch artifact cụ thể sau khi hiểu hạ tầng. Sau đó **đối chiếu lại dependency tree và class được runtime load**. Nếu POM sai, sửa POM trước.

Không nên xóa hoặc đổi tên file cache trên máy đồng nghiệp/CI runner chỉ để thử may rủi mà chưa có quyền và kế hoạch tái tạo.

## 23. Quy trình phòng ngừa trong phát hành thư viện

Một số biện pháp giảm nguy cơ lỗi binary khi project lớn:

1. **Ghim version phụ thuộc bằng POM/parent/BOM** theo policy; không dựa vào thứ tự ngẫu nhiên của transitive dependencies.
2. **Khai báo dependency trực tiếp** cho những thư viện mà mã nguồn module sử dụng trực tiếp.
3. **Chạy Enforcer rules hợp lý**, nhưng xem xét false positive/các đường hợp lệ và không coi rule là bảo đảm tương thích API.
4. **Kiểm tra binary API compatibility** khi release thư viện dùng chung; thay đổi method/class phải được đánh giá theo Semantic Versioning/contract của dự án.
5. **Chạy integration/smoke test trên artifact cuối** với runtime classpath tương ứng môi trường triển khai.
6. **Kiểm tra duplicate classes** trong packaging, plugin Shade/Assembly, WAR hoặc container classpath khi có dấu hiệu conflict.
7. **Liên kết commit với artifact digest** và tránh deploy nhầm bản cũ.
8. **Xác nhận version JDK và môi trường chạy**; một số linkage error cũng có thể từ bytecode/JDK API không tương thích.
9. **Lưu dependency tree/report của CI** và thay đổi đồ thị dependency được review khi nâng cấp.
10. **Không log secret** khi dùng `-X`, dump settings hoặc gửi full classpath nội bộ trong báo cáo công khai.

Nếu một ứng dụng có nhiều module được phát hành tách thời điểm, nên định nghĩa **ma trận phiên bản tương thích** giữa các module. Version resolution thành công chỉ có nghĩa artifact có thể được tìm thấy và chọn, chưa chứng minh mọi lời gọi binary giữa chúng đều tương thích.

## 24. Bài tập tự kiểm tra

1. **Build client với API 2.0 có `greet(String)`, runtime dùng API 1.0 chỉ có `greet()`. Lỗi nào dễ gặp?**  
   **Đáp án:** `NoSuchMethodError`; JVM tìm được class nhưng không tìm được method descriptor được bytecode gọi.

2. **Client import `demo.api.Feature`, runtime JAR không có `Feature.class`. Lỗi nào dễ gặp?**  
   **Đáp án:** `NoClassDefFoundError`, có thể kèm `ClassNotFoundException` ở `Caused by`.

3. **Maven dependency:tree hiển thị đúng API 2.0 nhưng production vẫn tải API 1.0. Cần kiểm tra gì?**  
   **Đáp án:** Classpath runtime, packaging, image/container, classloader và class-load log; tree chỉ phản ánh graph lúc Maven resolve.

4. **Maven thấy hai version cùng artifact qua hai đường có độ sâu khác nhau, thường chọn gì?**  
   **Đáp án:** `nearest definition` (đường gần root hơn), nếu không có quyết định management/direct khác.

5. **Hai đường sâu bằng nhau, Maven chọn theo version lớn hơn?**  
   **Đáp án:** Không. Với quy tắc mediation thông thường, declaration xuất hiện trước có thể thắng.

6. **Muốn nhìn method descriptor, dùng công cụ JDK nào?**  
   **Đáp án:** `javap -s`, có thể kết hợp `-classpath` tới JAR nghi vấn và `-c` để xem lời gọi từ client.

7. **`NoSuchMethodError` có chắc vì class bị thiếu?**  
   **Đáp án:** Không. Class có thể đã được load; thiếu method có chữ ký đúng.

8. **`NoClassDefFoundError: Could not initialize class` có chắc thiếu JAR?**  
   **Đáp án:** Không. Có thể class initialization đã thất bại ở lần gọi trước; tìm `ExceptionInInitializerError` và root cause.

9. **`dependencyManagement` có tự đưa JAR vào runtime classpath?**  
   **Đáp án:** Không. Nó quản lý dependency theo quy tắc Maven, còn dependency phải được khai báo/đi qua đường hợp lệ.

10. **Một transitive dependency được khai báo `test` ở library, app có nhận nó khi runtime không?**  
    **Đáp án:** Không qua đường transitive đó; test scope không là application runtime dependency bình thường.

11. **Nếu một JAR có đúng filename/version nhưng chứa class cũ, làm gì?**  
    **Đáp án:** Kiểm tra nội dung bằng `jar tf`/`javap`, checksum/provenance và nguồn phát hành, không chỉ dựa vào tên file.

12. **Một service bị `NoSuchMethodError` trong plugin Maven chứ không trong app. Có nên sửa `<dependencies>` project ngay?**  
    **Đáp án:** Không. Trước tiên kiểm tra plugin realm, plugin version và plugin dependencies.

13. **Version cao nhất có luôn an toàn không?**  
    **Đáp án:** Không; binary API có thể đã thay đổi không tương thích. Cần xem hợp đồng API, thư viện liên quan và test.

14. **Vì sao chạy `java -cp target/classes ...` có thể báo NoClassDefFoundError dù Maven build thành công?**  
    **Đáp án:** Lệnh JVM thủ công không tự đưa runtime JAR dependencies vào classpath.

15. **Sau khi sửa POM, kiểm chứng điều gì trước khi đóng incident?**  
    **Đáp án:** Dependency graph mới, bytecode/JAR đúng, class-loading path runtime đúng và test tái hiện lỗi ban đầu đã PASS.

## 25. Checklist ngắn để xử lý incident

- [ ] Đã lưu **stack trace đầy đủ** và phân biệt đúng `NoSuchMethodError` với `NoClassDefFoundError`.
- [ ] Đã kiểm tra `Caused by` và trường hợp lỗi **static initialization**.
- [ ] Đã nhận diện class/method/descriptor và artifact cung cấp API đó.
- [ ] Đã dùng `javap -s` hoặc công cụ tương đương so binary API ở các JAR.
- [ ] Đã kiểm tra `jar tf` để biết class có thật trong artifact runtime không.
- [ ] Đã chạy `dependency:tree` trong **đúng module**, với profile/settings như build lỗi.
- [ ] Đã xét nearest definition, cùng độ sâu, `dependencyManagement`, BOM, scopes, exclusions và optional.
- [ ] Đã xác nhận class mà JVM thực sự load bằng `-Xlog:class+load` hoặc quan sát classloader phù hợp.
- [ ] Đã kiểm tra fat/thin JAR, WAR, image/container và launcher thật.
- [ ] Đã sửa version hoặc packaging **có căn cứ**, không chỉ nâng lên mới nhất.
- [ ] Đã build sạch và chạy test tái hiện bằng artifact cuối.
- [ ] Đã xác nhận CI/production dùng **đúng bản artifact sau fix**.
- [ ] Đã loại bỏ thông tin nhạy cảm khỏi log, đường dẫn và báo cáo chia sẻ.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, nearest definition, scopes, exclusions và dependency management.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved tree, `includes`, `verbose`, file output và định dạng JSON.
- [Apache Maven Dependency Plugin — Resolving Conflicts](https://maven.apache.org/plugins/maven-dependency-plugin/examples/resolving-conflicts-using-the-dependency-tree.html): cách tìm dependency conflict và hiểu node được chọn/bị bỏ.
- [Oracle Java SE 17 — NoSuchMethodError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html): error khi method không còn có định nghĩa tương thích lúc runtime.
- [Oracle Java SE 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): class definition đã có lúc compile nhưng không tìm thấy khi dùng.
- [Oracle Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): cách kiểm tra descriptor `-s`, bytecode `-c` và classpath `-classpath`.
- [Oracle Java SE 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): các tùy chọn JVM, classpath và class-loading logs.
- [Apache Maven Enforcer Plugin — Built-in Rules](https://maven.apache.org/enforcer/enforcer-rules/): `dependencyConvergence` và `requireUpperBoundDeps`.

**Kết luận:** `NoSuchMethodError` và `NoClassDefFoundError` thường không phải lỗi “Java không biết compile”. Chúng chỉ ra rằng **bytecode kỳ vọng một API khác với API/classpath mà JVM đang dùng** hoặc rằng quá trình khởi tạo class đã hỏng. Cách chẩn đoán tin cậy là nối được bốn bằng chứng: **method/class cần dùng → binary API đã compile → version Maven resolve → JAR thực tế được runtime load**. Khi đủ bốn điểm, bản sửa sẽ rõ ràng và có thể kiểm chứng.
