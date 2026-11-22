# NoSuchMethodError do phiên bản thư viện không tương thích

## 1. Hiểu đúng lỗi trước khi sửa dependency

`java.lang.NoSuchMethodError` là một lỗi liên kết ở runtime. JVM đang thực thi bytecode gọi một method bằng tên và descriptor cụ thể, nhưng class được nạp thực tế không có method tương ứng.

Thông báo thường có dạng:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.TextFormatter.format(java.lang.String, java.util.Locale)'
~~~

Đọc thông báo theo ba phần:

- `com.example.api.TextFormatter` là class mà JVM đang tìm method.
- `format` là tên method.
- Các kiểu tham số và kiểu trả về cho biết chữ ký bytecode mà caller đang yêu cầu.

Một lỗi điển hình xảy ra khi ứng dụng hoặc thư viện phụ thuộc được biên dịch với phiên bản API mới, trong đó method tồn tại, nhưng khi chạy JVM lại nạp phiên bản cũ của class, trong đó method đó chưa có hoặc đã bị thay đổi.

Ví dụ:

- Lúc compile: `text-api:2.0` có `format(String, Locale)`.
- Lúc runtime: classpath chỉ chứa `text-api:1.0`, chỉ có `format(String)`.
- Caller vẫn chứa lệnh gọi tới `format(String, Locale)`.
- JVM không tìm thấy method có descriptor cần thiết và ném `NoSuchMethodError`.

Đây là lỗi tương thích nhị phân (binary compatibility). Source code có thể đã compile thành công vì compiler nhìn thấy API mới, nhưng runtime lại nạp một định nghĩa class khác.

### 1.1. Vì sao compiler không phát hiện?

Khi biên dịch, compiler kiểm tra các class và method trên compile classpath. Nó ghi lời gọi method vào bytecode. Khi chạy, JVM phải liên kết lời gọi đó với class được nạp từ runtime classpath hoặc classloader thực tế.

Nếu hai tập class khác nhau, compiler có thể chấp nhận lời gọi mà runtime không thể liên kết.

Mô hình:

~~~text
Compile time
  Application source
       |
       v
  API library 2.0
  has format(String, Locale)
       |
       v
  Application bytecode
  invokes format(String, Locale)

Runtime
  Application bytecode
       |
       v
  ClassLoader loads API library 1.0
  has format(String) only
       |
       v
  NoSuchMethodError
~~~

Sự khác biệt có thể đến từ dependency bắc cầu, version conflict, JAR cũ còn trong thư mục triển khai, application server cung cấp thư viện riêng, shaded JAR hoặc classloader nạp class từ nguồn khác dự kiến.

### 1.2. Method descriptor là gì?

Ở mức Java source, một method thường được nhận diện bằng tên và danh sách kiểu tham số. Ở mức JVM bytecode, symbolic method reference chứa:

- Tên class/interface sở hữu method.
- Tên method.
- Descriptor của method.

Descriptor bao gồm kiểu tham số **và kiểu trả về**. Ví dụ:

~~~text
format(String, Locale): String
(Ljava/lang/String;Ljava/util/Locale;)Ljava/lang/String;
~~~

Vì vậy, thay đổi kiểu tham số, kiểu trả về hoặc class sở hữu method có thể làm bytecode cũ không còn liên kết được với API mới. Thêm một overload mới cũng không giúp caller cũ nếu runtime lại nạp phiên bản chưa có overload đó.

Một số tình huống thường gây lỗi:

| Thay đổi API | Hệ quả có thể gặp |
|---|---|
| Xóa hoặc đổi tên method | Caller cũ vẫn gọi method không còn tồn tại |
| Đổi kiểu tham số | Descriptor cũ không còn khớp |
| Đổi kiểu trả về | Descriptor bytecode thay đổi |
| Chuyển method sang class/interface khác | Caller tham chiếu owner cũ |
| Thêm overload nhưng runtime dùng bản cũ | Caller gọi overload chưa có trong bản runtime |
| Nạp nhầm phiên bản class cùng fully-qualified name | Runtime API khác compile-time API |

Không phải mọi thay đổi method đều tạo đúng `NoSuchMethodError`. Thay đổi giữa static và instance, hoặc thay đổi quan hệ class/interface, có thể dẫn đến `IncompatibleClassChangeError`; method abstract không có implementation phù hợp có thể dẫn đến `AbstractMethodError`.

## 2. Phân biệt các lỗi dễ nhầm

Tên lỗi gần giống nhau nhưng nguyên nhân và cách xử lý khác nhau:

| Lỗi | Ý nghĩa | Hướng điều tra đầu tiên |
|---|---|---|
| `NoSuchMethodError` | Bytecode gọi method không tồn tại trong class được nạp | So sánh method descriptor giữa compile-time và runtime class |
| `NoSuchMethodException` | Code dùng reflection tìm method nhưng không tìm thấy | Kiểm tra `getMethod`/`getDeclaredMethod`, tên và kiểu tham số |
| `NoClassDefFoundError` | JVM cần một class nhưng không thể nạp/định nghĩa class đó | Kiểm tra JAR thiếu, class initialization failure hoặc classloader |
| `ClassNotFoundException` | Một thao tác nạp class tường minh không tìm thấy class | Kiểm tra classpath và classloader gọi `Class.forName` |
| `AbstractMethodError` | Runtime gọi method abstract nhưng implementation được nạp không cung cấp implementation tương thích | Kiểm tra các phiên bản interface và implementation |
| `NoSuchFieldError` | Bytecode tham chiếu field không còn tồn tại | So sánh field trong caller và class runtime |
| `IncompatibleClassChangeError` | Cấu trúc class thay đổi không tương thích với cách caller sử dụng | Kiểm tra class/interface, static/instance và hierarchy |

Đừng sửa `NoSuchMethodError` bằng cách bắt exception rồi bỏ qua. Đây là `LinkageError`, thường cho thấy tập bytecode và thư viện đang chạy không cùng một hợp đồng API. Việc nuốt lỗi có thể làm ứng dụng tiếp tục trong trạng thái thiếu chức năng hoặc sai dữ liệu.

## 3. Các nguyên nhân thường gặp

### 3.1. Dependency bắc cầu kéo phiên bản cũ

Ứng dụng khai báo thư viện A và B. A yêu cầu API C phiên bản mới; B lại yêu cầu API C cũ. Công cụ build giải quyết xung đột và chọn một phiên bản C. Nếu phiên bản được chọn không còn tương thích nhị phân với caller, lỗi xuất hiện khi chạy.

Ví dụ đồ thị:

~~~text
application
  |-- report-client 4.0
  |      |-- text-api 2.0
  |
  |-- legacy-exporter 1.5
         |-- text-api 1.0

Resolved runtime:
  text-api 1.0
~~~

Cây dependency cần được kiểm tra để biết ai yêu cầu từng phiên bản và vì sao công cụ build chọn phiên bản cuối cùng.

### 3.2. Compile classpath khác runtime classpath

Một số cấu hình build tách dependency theo scope:

- Maven: `compile`, `provided`, `runtime`, `test`.
- Gradle: `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath`, `compileOnly`, `runtimeOnly`.

Ứng dụng có thể compile với một version nhưng khi đóng gói hoặc deploy lại dùng version khác. Ví dụ, một dependency `provided` được cung cấp bởi application server; phiên bản server cung cấp có thể cũ hơn API mà ứng dụng đã compile.

### 3.3. JAR trùng class hoặc thư viện bị đóng gói hai lần

Một ứng dụng có thể chứa hai JAR khác nhau cùng khai báo một class:

~~~text
lib/
  text-api-1.0.jar
  text-api-2.0.jar
~~~

Thứ tự classpath hoặc quy tắc của classloader quyết định class nào được nạp. Chỉ nhìn tên dependency trong POM/Gradle file chưa đủ để biết class thực tế đến từ JAR nào.

Tình huống này cũng xuất hiện khi:

- Một JAR được copy thủ công vào `lib/` bên cạnh dependency do Maven/Gradle quản lý.
- Fat JAR/shaded JAR chứa bản copy class cũ.
- WAR có thư viện trong `WEB-INF/lib` và server lại có thư viện cùng class.
- Docker image chưa được build lại sau khi dependency được cập nhật.
- Một module plugin hoặc application server dùng classloader riêng.

### 3.4. Version bị override ngoài BOM

Spring Boot kiểm thử từng release với một tập phiên bản thư viện cụ thể. Nếu ứng dụng override riêng Spring Framework, Jackson, Hibernate, logging hoặc một thư viện nền tảng mà không kiểm tra tương thích, các module có thể không còn đồng bộ.

Ví dụ, nâng `spring-core` nhưng để `spring-context` ở version cũ có thể tạo ra một tập Spring Framework không đồng nhất. Tương tự, override một thư viện nền tảng được nhiều starter sử dụng có thể làm caller và implementation lệch API.

### 3.5. Runtime không phải artifact vừa build

Một số trường hợp không xuất phát từ dependency graph hiện tại:

- CI build JAR mới nhưng máy chủ vẫn chạy JAR cũ.
- Có hai bản ứng dụng cùng tên ở hai thư mục triển khai.
- Container dùng image tag cũ hoặc cache layer chưa được invalidated.
- Application server giữ thư viện dùng chung ở thư mục global.
- Hot reload/devtools hoặc plugin classloader giữ class cũ trong một classloader khác.

Luôn xác minh đúng file được chạy và đúng class được nạp trước khi thay version hàng loạt.


## 4. Tái hiện lỗi bằng hai phiên bản JAR

Ví dụ nhỏ sau chứng minh cùng một application bytecode có thể chạy với API mới nhưng lỗi với API cũ. Dùng Java 17 trở lên và các lệnh PowerShell; nếu chạy trên Linux/macOS, thay dấu phân tách classpath `;` bằng `:`.

### 4.1. Cấu trúc thư mục

~~~text
nosuchmethod-demo/
├── src-v1/
│   └── demo/api/GreetingService.java
├── src-v2/
│   └── demo/api/GreetingService.java
└── src-app/
    └── demo/app/Main.java
~~~

### 4.2. Phiên bản API 1.0

Tệp `src-v1/demo/api/GreetingService.java`:

~~~java
package demo.api;

public final class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### 4.3. Phiên bản API 2.0

Tệp `src-v2/demo/api/GreetingService.java`:

~~~java
package demo.api;

public final class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }

    public String greet(String name, String locale) {
        if ("vi".equals(locale)) {
            return "Xin chao, " + name;
        }
        return greet(name);
    }
}
~~~

Phiên bản 2.0 bổ sung overload `greet(String, String)`. Đây là method mà caller sẽ sử dụng.

### 4.4. Ứng dụng gọi API mới

Tệp `src-app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        System.out.println(new GreetingService().greet("Lan", "vi"));
    }
}
~~~

### 4.5. Build hai JAR và compile ứng dụng

Từ thư mục gốc của demo, chạy trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/v1, build/v2, build/app | Out-Null

javac -d build/v1 src-v1/demo/api/GreetingService.java
jar --create --file build/greeting-v1.jar -C build/v1 .

javac -d build/v2 src-v2/demo/api/GreetingService.java
jar --create --file build/greeting-v2.jar -C build/v2 .

javac -cp build/greeting-v2.jar -d build/app src-app/demo/app/Main.java
~~~

Điểm quan trọng: ứng dụng được compile với `greeting-v2.jar`. Vì vậy bytecode của `Main` chứa lời gọi `greet(String, String)`.

### 4.6. Chạy nhầm API 1.0

Đưa JAR 1.0 vào runtime classpath:

~~~powershell
java -cp "build/app;build/greeting-v1.jar" demo.app.Main
~~~

Kết quả lỗi trên JDK 17 có dạng:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String demo.api.GreetingService.greet(java.lang.String, java.lang.String)'
        at demo.app.Main.main(Main.java:7)
~~~

Caller yêu cầu method có hai tham số kiểu String. Class runtime 1.0 chỉ có method một tham số, nên JVM không thể liên kết lời gọi.

### 4.7. Chạy với API 2.0

Dùng đúng JAR mà ứng dụng đã compile cùng:

~~~powershell
java -cp "build/app;build/greeting-v2.jar" demo.app.Main
~~~

Stdout chính xác:

~~~text
Xin chao, Lan
~~~

Ví dụ cho thấy lỗi không nằm ở cú pháp gọi method trong source code. Vấn đề là class được compile và class được nạp lúc chạy không cùng phiên bản API.


## 5. Quy trình chẩn đoán từ stack trace đến JAR thực tế

Không bắt đầu bằng cách nâng tất cả dependency lên phiên bản mới nhất. Trước tiên xác định class và method mà JVM không liên kết được, sau đó tìm nguồn class runtime.

### Bước 1: Đọc toàn bộ stack trace

Ghi lại:

- Tên class trong thông báo lỗi.
- Tên method và danh sách kiểu tham số.
- Frame đầu tiên thuộc code của ứng dụng hoặc thư viện bên thứ ba.
- Method nào gọi vào API bị lỗi.
- Lỗi xảy ra lúc startup, khi xử lý request, chạy scheduled job hay chỉ trong test.

Nếu frame đầu tiên nằm trong một thư viện bên thứ ba, điều đó không có nghĩa code ứng dụng không liên quan. Caller trực tiếp có thể là thư viện đó; ứng dụng chỉ đưa vào classpath một tổ hợp version không tương thích.

### Bước 2: Xác định class runtime đến từ đâu

Có thể in classloader và code source của class:

~~~java
package demo.app;

import java.security.CodeSource;

public final class ClassOrigin {

    private ClassOrigin() {
    }

    public static void print(Class<?> type) {
        System.out.println("class=" + type.getName());
        System.out.println("classLoader=" + type.getClassLoader());

        CodeSource source = type.getProtectionDomain().getCodeSource();
        System.out.println(
                "codeSource=" + (source == null ? "<unknown>" : source.getLocation())
        );
    }
}
~~~

Gọi helper bằng class được nêu trong lỗi:

~~~java
ClassOrigin.print(demo.api.GreetingService.class);
~~~

Nếu code source trả về null, class có thể được nạp từ một nguồn không cung cấp CodeSource hoặc từ môi trường classloader đặc biệt. Không coi null là bằng chứng class không có JAR; dùng thêm class-loading log.

Trên Java 9 trở lên:

~~~powershell
java -Xlog:class+load=info -cp "build/app;build/greeting-v1.jar" demo.app.Main 2>&1 | Select-String "demo.api.GreetingService"
~~~

Trên Java 8:

~~~powershell
java -verbose:class -cp "build/app;build/greeting-v1.jar" demo.app.Main
~~~

Log class loading cho biết JVM nạp class từ nguồn nào. Trong ứng dụng Spring Boot executable JAR, đường dẫn có thể trỏ tới nested JAR bên trong archive. Trong application server, classloader cha có thể cung cấp class trước thư viện trong ứng dụng.

### Bước 3: So sánh API của JAR cũ và JAR mới

Dùng `javap` để xem method và descriptor:

~~~powershell
javap -classpath build/greeting-v1.jar -p -s demo.api.GreetingService
javap -classpath build/greeting-v2.jar -p -s demo.api.GreetingService
~~~

Với JAR 1.0, phần method liên quan có dạng:

~~~text
public java.lang.String greet(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
~~~

Với JAR 2.0, có thêm:

~~~text
public java.lang.String greet(java.lang.String, java.lang.String);
  descriptor: (Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
~~~

Tiếp tục kiểm tra bytecode của caller:

~~~powershell
javap -classpath "build/app;build/greeting-v2.jar" -c -s demo.app.Main
~~~

Tìm lệnh gọi có dạng:

~~~text
invokevirtual ... // Method demo/api/GreetingService.greet:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
~~~

Nếu caller yêu cầu descriptor hai tham số nhưng class runtime chỉ có descriptor một tham số, đã xác định được mismatch cụ thể.

`javap` cho biết nội dung class file; nó không tự xác định class nào được application server hoặc container nạp. Ghép kết quả `javap` với class-loading log hoặc code source để hoàn tất việc truy vết.

### Bước 4: Kiểm tra dependency graph của cấu hình runtime

Đừng chỉ xem file khai báo dependency. Cần xem version được chọn cuối cùng trong đúng configuration mà ứng dụng chạy.

Với Maven:

~~~powershell
mvn dependency:tree -Dverbose -Dincludes=com.example:text-api
mvn help:effective-pom
~~~

Thay `com.example:text-api` bằng `groupId:artifactId` thật. `dependency:tree` cho biết đường dẫn dependency và các phiên bản được yêu cầu/được chọn; `effective-pom` giúp kiểm tra parent, BOM và `dependencyManagement` đã áp dụng.

Nếu cần xem classpath runtime mà Maven tạo:

~~~powershell
mvn dependency:build-classpath -Dmdep.includeScope=runtime -Dmdep.outputFile=target/runtime-classpath.txt
~~~

So sánh runtime scope với compile/test scope. Một dependency `provided` có thể được container cung cấp khi deploy nên cần kiểm tra version của container, không chỉ kết quả Maven.

Với Gradle:

~~~powershell
.\gradlew dependencies --configuration compileClasspath
.\gradlew dependencies --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency com.example:text-api --configuration runtimeClasspath
~~~

Thay module bằng tọa độ dependency thực tế. `dependencyInsight` chỉ rõ ai yêu cầu version, version nào được chọn và lý do lựa chọn. Nếu lỗi chỉ xảy ra trong test, kiểm tra thêm `testRuntimeClasspath`; nếu chỉ xảy ra trong production, lấy thông tin từ đúng artifact/image/container đang chạy.

### Bước 5: Kiểm tra nội dung artifact được deploy

Với JAR thường:

~~~powershell
jar tf target/application.jar
~~~

Với executable Spring Boot JAR, kiểm tra các thư viện trong:

~~~text
BOOT-INF/lib/
~~~

Với WAR, kiểm tra:

~~~text
WEB-INF/lib/
~~~

Tìm tất cả JAR có thể chứa class lỗi. Nếu ứng dụng được deploy lên Tomcat, application server hoặc nền tảng plugin, kiểm tra thêm thư viện dùng chung ở container. Dependency tree của project không thể hiển thị thư viện được server thêm vào ngoài artifact.

Với Docker, xác nhận image digest/tag và lệnh khởi động. Không suy luận rằng image đang chạy chứa đúng file JAR vừa build chỉ vì pipeline build thành công.

## 6. Dấu hiệu để khoanh vùng nguyên nhân

| Dấu hiệu | Khả năng cao | Kiểm tra tiếp |
|---|---|---|
| Compile thành công, chạy ngay sau deploy lỗi | Runtime dùng JAR khác compile classpath | Class-loading log, CodeSource, dependency runtime |
| Chỉ một máy hoặc một container lỗi | Image/server có thư viện cũ hoặc classloader khác | So sánh image digest, mounted volumes, shared libs |
| Chỉ test lỗi | `testRuntimeClasspath` khác runtime production | Gradle/Maven test dependency tree |
| Chỉ lỗi khi bật một integration | Dependency bắc cầu của integration đó xung đột | `dependencyInsight` hoặc Maven tree theo artifact |
| Lỗi sau khi override Spring Framework/Jackson/Hibernate | Các module không còn cùng release line | BOM, effective POM và resolved graph |
| Stack trace trỏ vào plugin hoặc server | Plugin/server nạp class riêng | Classloader và shared library của môi trường |
| Có nhiều JAR chứa cùng FQCN | Classpath order hoặc shading | `jar tf`, class-loading log và archive contents |

Một lỗi chỉ xảy ra ở một endpoint có thể do lazy initialization: class không được liên kết cho tới khi method cụ thể được gọi. Vì vậy, ứng dụng khởi động thành công không chứng minh toàn bộ runtime API đều tương thích.


## 7. Sửa dependency conflict trong Maven

Maven dùng dependency mediation để chọn một version khi cùng artifact được yêu cầu nhiều lần. Quy tắc mặc định là **nearest definition**: đường dẫn gần project nhất thắng; nếu hai đường dẫn cùng độ sâu, dependency khai báo trước thắng.

Ví dụ project có hai nhánh cùng kéo `com.example:text-api`:

~~~text
application
  |-- report-client:4.0
  |      |-- text-api:2.0
  |
  |-- legacy-exporter:1.5
         |-- text-api:1.0
~~~

Nếu nhánh tới `text-api:1.0` gần project hơn, Maven có thể chọn bản 1.0 dù một thư viện khác đã compile với API 2.0.

### 7.1. Khai báo version tương thích trực tiếp

Nếu xác định `text-api:2.0` là version tương thích với toàn bộ caller, có thể quản lý version ở project:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>text-api</artifactId>
            <version>2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi cần API trực tiếp trong code, khai báo dependency trong `dependencies` mà không lặp version:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>text-api</artifactId>
    </dependency>
</dependencies>
~~~

`dependencyManagement` quản lý version khi dependency được khai báo trực tiếp hoặc được tham chiếu bắc cầu. Chỉ pin version sau khi xác nhận version đó tương thích với các thư viện gọi nó.

### 7.2. Loại trừ dependency cũ khỏi nhánh gây xung đột

Nếu `legacy-exporter` kéo một dependency không tương thích và không thực sự cần dùng ở runtime, có thể exclude tại đúng edge:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-exporter</artifactId>
    <version>1.5</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>text-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Sau đó khai báo version tương thích một cách tường minh. Exclusion chỉ xóa một đường dependency; nếu caller vẫn cần API đó, phải cung cấp dependency thay thế. Không exclude một thư viện chỉ để làm dependency tree trông gọn hơn.

### 7.3. Import BOM thay vì tự pin hàng loạt

Nếu nhiều thư viện thuộc cùng một hệ sinh thái, ưu tiên BOM của nhà cung cấp:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`3.5.0` chỉ là version minh họa cú pháp. Chọn BOM đúng với dòng Spring Boot mà dự án đang dùng. Không copy version ví dụ này vào dự án khác mà chưa kiểm tra release line.

Sau khi thay đổi, chạy lại:

~~~powershell
mvn dependency:tree -Dverbose
mvn clean verify
~~~

Xác nhận version được chọn đúng trong mọi module và scope. Đọc cả đường dẫn dependency bị omitted/conflict để biết vì sao Maven chọn version cuối cùng.

## 8. Sửa dependency conflict trong Gradle

Gradle giải quyết version conflict bằng cách xét các version được yêu cầu trong dependency graph. Theo mặc định, Gradle thường chọn version cao nhất trong các version hợp lệ; dependency constraints, platforms, rich version và resolution rules có thể thay đổi kết quả.

### 8.1. Dùng platform/BOM

Ví dụ Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.example:text-api'
}
~~~

Platform đưa các version constraint từ BOM vào configuration. Trong Gradle, `platform(...)` cung cấp constraint có thể tham gia conflict resolution; một dependency khác vẫn có thể làm version được chọn thay đổi. `enforcedPlatform(...)` áp đặt version mạnh hơn và có thể ảnh hưởng các dependency consumer, vì vậy chỉ dùng khi có lý do rõ ràng.

### 8.2. Dùng dependency constraint cho một thư viện

Nếu chỉ cần quản lý một module cụ thể:

~~~groovy
dependencies {
    constraints {
        implementation('com.example:text-api:2.0') {
            because 'The runtime API must include the overload used by report-client'
        }
    }
}
~~~

Constraint giúp Gradle chọn version có chủ đích trong configuration liên quan. Tuy nhiên, phải kiểm tra version 2.0 có thực sự tương thích với tất cả consumer và provider trong graph hay không.

Tránh dùng `resolutionStrategy.force` như cách sửa mặc định. Ép version có thể làm lỗi chuyển sang một thư viện khác vốn cần API cũ. Nếu buộc phải dùng force trong thời gian ngắn, ghi rõ lý do, phạm vi configuration và test bảo vệ.

### 8.3. Xác minh version được chọn

Chạy:

~~~powershell
.\gradlew dependencyInsight --dependency com.example:text-api --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency com.example:text-api --configuration compileClasspath
.\gradlew dependencies --configuration runtimeClasspath
~~~

So sánh compile và runtime. Nếu chỉ test lỗi, chạy thêm `testRuntimeClasspath`. Báo cáo `dependencyInsight` giải thích version nào được chọn, dependency nào yêu cầu và selection reason như conflict resolution, constraint, rule hoặc forced version.

Sau khi sửa:

~~~powershell
.\gradlew clean test
.\gradlew bootJar
~~~

Không chỉ xác nhận build xanh. Chạy chính JAR vừa đóng gói và kiểm tra dependency bên trong archive.

## 9. Đồng bộ dependency trong Spring Boot

Spring Boot phát hành `spring-boot-dependencies` BOM để quản lý một tập dependency đã được kiểm thử cùng nhau. Với ứng dụng Spring Boot:

- Dùng Spring Boot parent POM hoặc import đúng BOM trong Maven.
- Dùng Spring Boot Gradle plugin/dependency management plugin hoặc native Gradle platform.
- Tránh gán version riêng cho từng module Spring Framework, Spring Data, Spring Security, Jackson hoặc Hibernate nếu BOM đã quản lý.
- Kiểm tra Spring Cloud và các thư viện ngoài BOM bằng compatibility matrix riêng.
- Nếu bắt buộc override version, ghi rõ lý do và chạy integration test trên tập dependency thực tế.

Ví dụ Maven khi dùng Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>
~~~

Version ở trên chỉ minh họa. Hãy chọn maintenance release phù hợp và giữ Spring Boot Maven plugin cùng dòng version.

Ví dụ Gradle với native BOM support:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.5.0'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Nếu dùng plugin `io.spring.dependency-management`, Spring Boot Gradle plugin có thể tự import BOM tương ứng. Không cần khai báo thêm một platform trùng lặp nếu build đã có cơ chế quản lý dependency này.

Một BOM không thể bảo vệ ứng dụng khỏi thư viện được đóng gói thủ công, JAR do application server cung cấp hoặc class trùng trong shaded archive. Vì vậy, vẫn phải kiểm tra artifact và classloader khi dependency tree nhìn có vẻ đúng nhưng lỗi còn tồn tại.

## 10. Kiểm tra các nguồn class bên ngoài dependency graph

Khi Maven/Gradle đã chọn đúng version nhưng `NoSuchMethodError` vẫn xảy ra, kiểm tra runtime thực tế:

1. **Executable Spring Boot JAR:** kiểm tra `BOOT-INF/lib/` để tìm phiên bản thư viện được đóng gói.
2. **WAR:** kiểm tra `WEB-INF/lib/` và thư viện dùng chung của Servlet container.
3. **Application server:** xem thư viện global/shared và quy tắc parent-first/child-first classloading.
4. **Docker/Kubernetes:** kiểm tra image digest, tag, mount, entrypoint và file JAR đang được chạy.
5. **Shaded/uber JAR:** tìm duplicate class; nếu thật sự phải đóng gói nhiều phiên bản, dùng relocation đúng cách và kiểm tra bytecode sau shading.
6. **Plugin hoặc hot reload:** kiểm tra classloader riêng và restart process hoàn toàn để loại trạng thái class cũ.

Lệnh `jar tf` liệt kê nội dung archive nhưng không giải quyết duplicate class. Ghép kết quả đó với class-loading log để biết class nào thực sự được chọn.

Không xóa toàn bộ Maven/Gradle cache như bước đầu tiên. Cache hỏng có thể xảy ra, nhưng nếu dependency resolution đang chọn sai version thì tải lại cùng artifact không thay đổi kết quả. Trước tiên sửa graph và xác minh artifact; chỉ làm sạch cache khi có bằng chứng file tải về bị hỏng hoặc metadata cache sai.


## 11. Chọn cách sửa theo nguyên nhân

Khi đã xác định class và version runtime, chọn một trong các hướng sau.

### Trường hợp A: Runtime đang dùng bản cũ hơn caller cần

Nếu caller được compile với API 2.0 nhưng runtime nạp API 1.0:

- Nâng dependency runtime lên version có method tương ứng.
- Kiểm tra mọi thư viện khác có tương thích với version mới không.
- Loại JAR cũ khỏi classpath, thư mục deploy, image hoặc shared library.
- Build lại artifact và xác nhận classloader nạp đúng JAR mới.

Không chỉ thêm API 2.0 vào POM nếu API 1.0 vẫn được đóng gói hoặc server vẫn nạp class cũ trước.

### Trường hợp B: Một thư viện cũ không tương thích với API mới

Nếu nâng API dùng chung làm một thư viện khác lỗi:

- Nâng thư viện caller lên phiên bản hỗ trợ API mới.
- Hoặc chọn một version API tương thích với tất cả caller.
- Nếu không có version giao nhau, thay thế thư viện cũ hoặc tách integration thành module/classloader độc lập.
- Không ép version bằng force nếu chưa kiểm tra toàn bộ consumer trong dependency graph.

### Trường hợp C: Application server cung cấp API

Nếu class đến từ server:

- Xác định version API mà server thực sự cung cấp.
- Dùng version đó khi compile và test.
- Cấu hình scope `provided` khi server là bên sở hữu dependency.
- Nếu ứng dụng phải tự đóng gói thư viện, tuân theo hướng dẫn classloading và deployment của server; tránh hai bản cùng FQCN.

Không giả định `WEB-INF/lib` luôn thắng thư viện global. Thứ tự phụ thuộc application server và cấu hình classloader.

### Trường hợp D: API đã bị thay đổi không tương thích

Nếu nhà cung cấp đã xóa hoặc đổi descriptor method, cần nâng caller lên phiên bản hỗ trợ API mới hoặc sửa caller để dùng API hiện hành. Nếu quản lý cả API và caller, phát hành thay đổi theo một release plan có kiểm thử tương thích nhị phân.

### Trường hợp E: Artifact deploy không trùng artifact build

Nếu dependency graph đúng nhưng server vẫn nạp JAR cũ:

- Xác minh file và image đang chạy bằng checksum/digest.
- Dừng process cũ và deploy artifact mới theo đúng quy trình.
- Xóa bản copy thủ công hoặc thư mục deploy cũ sau khi xác nhận đúng đích.
- Khởi động lại process để tạo classloader mới.
- Ghi lại version và CodeSource của class khi smoke test.

Không xóa file hoặc thư mục production chỉ dựa trên tên gần giống. Xác minh đường dẫn artifact đang chạy trước khi thay đổi deployment.

## 12. Ví dụ xử lý một sự cố thực tế

Giả sử ứng dụng báo:

~~~text
java.lang.NoSuchMethodError:
  'com.example.json.JsonNode com.example.json.JsonMapper.readTree(java.io.InputStream)'
    at com.example.report.ReportParser.parse(ReportParser.java:48)
~~~

Quy trình:

1. Stack trace cho biết caller là `ReportParser.parse`, còn method không tìm thấy thuộc `JsonMapper`.
2. Kiểm tra `JsonMapper.class.getProtectionDomain().getCodeSource()` để biết JAR runtime.
3. Dùng `javap -p -s` trên JAR đang được nạp để xem có method `readTree(InputStream)` và descriptor tương ứng không.
4. Chạy Maven `dependency:tree` hoặc Gradle `dependencyInsight` cho artifact chứa `JsonMapper`.
5. So sánh compile classpath, runtime classpath và dependency nằm trong `BOOT-INF/lib`/`WEB-INF/lib`.
6. Tìm thư viện nào yêu cầu API mới và nhánh dependency nào kéo API cũ.
7. Chọn version tương thích, sửa BOM/constraint/exclusion hoặc nâng caller library.
8. Build sạch, đóng gói lại và kiểm tra JAR thực tế.
9. Chạy smoke test bằng chính lệnh deploy hoặc container production.
10. Ghi nhận resolved version và class source trong log để tránh lặp lại.

Tên class và method trong ví dụ là minh họa. Trong sự cố thật, thay bằng owner, method descriptor và artifact đúng từ stack trace.

## 13. Phòng ngừa lỗi tương thích nhị phân

### 13.1. Quản lý version tập trung

- Dùng BOM hoặc dependency management cho các thư viện thuộc cùng release train.
- Tránh khai báo version lặp lại ở nhiều module.
- Hạn chế version range và dynamic version trong môi trường release.
- Kiểm tra dependency graph trong CI, không chỉ trên máy developer.
- Nếu dự án cần tái lập chính xác dependency graph, cân nhắc Gradle dependency locking hoặc cơ chế khóa version phù hợp.

Khóa version giúp build tái lập; nó không tự chứng minh các version đã khóa tương thích với nhau.

### 13.2. Kiểm tra compile và runtime classpath

Trong CI, xác minh các configuration quan trọng:

- Compile classpath.
- Runtime classpath.
- Test compile/runtime classpath.
- Integration test classpath.
- Dependency được container cung cấp nếu deploy WAR hoặc plugin.

Chạy test trên artifact đã package, không chỉ trên class directory của IDE. Một số lỗi chỉ xuất hiện khi executable JAR, WAR hoặc image được tạo vì quá trình đóng gói có thể đưa vào dependency khác với classpath test.

### 13.3. Kiểm tra tương thích khi phát hành thư viện

Nếu nhóm phát triển thư viện:

- Tránh xóa hoặc đổi descriptor method public trong một minor release nếu cam kết binary compatibility.
- Dùng deprecation và migration path trước khi loại API.
- Kiểm tra public API và binary compatibility bằng công cụ phù hợp trong CI.
- Test thư viện với các version dependency mà nó tuyên bố hỗ trợ.
- Công bố rõ minimum/maximum version và compatibility matrix.
- Khi thay đổi major version, nâng caller cùng release notes và hướng dẫn migration.

Một thư viện compile thành công với dependency mới chưa chứng minh nó tương thích với dependency runtime cũ mà consumer có thể đang dùng.

### 13.4. Test artifact theo cách người dùng triển khai

Với ứng dụng:

1. Build executable JAR hoặc WAR.
2. Kiểm tra dependency được đóng gói.
3. Chạy đúng artifact vừa tạo, không chạy class directory từ IDE.
4. Smoke test các luồng gọi tới thư viện liên quan.
5. Kiểm tra log class loading khi có class trùng hoặc classloader đặc biệt.

Với starter/library:

1. Publish hoặc install artifact vào repository test.
2. Tạo consumer sample chỉ khai báo dependency công khai.
3. Khởi động consumer bằng đúng runtime.
4. Xác minh dependency transitives, package và auto-configuration được nạp từ artifact dự kiến.
5. Chạy test với các version dependency trong compatibility matrix.

## 14. Những cách xử lý sai nên tránh

1. **Nâng tất cả dependency lên latest ngay lập tức.** Có thể tạo thêm nhiều incompatibility; xác định artifact và method trước.
2. **Chỉ chạy clean build rồi kết luận xong.** Clean xóa output cũ nhưng không sửa dependency resolution hoặc server classloader.
3. **Thêm dependency trực tiếp mà không xem graph.** Có thể tạo thêm xung đột hoặc che giấu nhánh dependency cũ.
4. **Dùng force/exclusion hàng loạt.** Có thể làm thư viện khác thiếu method hoặc class cần thiết.
5. **Bắt `LinkageError` rồi tiếp tục.** Ứng dụng có thể chạy trong trạng thái không đúng và lỗi xuất hiện muộn hơn.
6. **Chỉ kiểm tra POM/Gradle file.** Cần xác minh version được resolve và class được nạp.
7. **Cho rằng version mới luôn tương thích ngược.** SemVer và release notes là hướng dẫn, nhưng vẫn cần kiểm tra hợp đồng API cụ thể.
8. **Xóa cache như giải pháp mặc định.** Nếu graph vẫn chọn cùng version thì tải lại JAR không sửa được nguyên nhân.
9. **Chỉ test trên máy local.** CI, container, application server và production có thể dùng classpath khác.
10. **Đóng gói hai version cùng một class mà không kiểm soát relocation.** Classloader sẽ chọn một định nghĩa; caller có thể liên kết với bản không phù hợp.

## 15. Checklist xử lý NoSuchMethodError

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Stack trace | Class owner, method và descriptor nào bị thiếu? |
| Caller | Bytecode nào đang gọi method đó? |
| Runtime class | JVM nạp class từ JAR/URL nào? |
| API comparison | JAR compile-time và runtime có cùng method descriptor không? |
| Dependency graph | Artifact nào yêu cầu từng version và version nào được chọn? |
| Scope | Compile, runtime, test và container có cùng dependency không? |
| Packaging | JAR/WAR/image có chứa JAR cũ hoặc duplicate class không? |
| Classloader | Có server/plugin/shared library nạp class khác không? |
| Resolution | BOM, dependencyManagement, constraint hoặc exclusion đã sửa đúng edge chưa? |
| Verification | Đã chạy chính artifact được đóng gói trong môi trường gần production chưa? |

## 16. Ghi nhớ

- `NoSuchMethodError` là `LinkageError`: bytecode gọi method nhưng class được JVM nạp không có đúng method descriptor.
- Nguyên nhân phổ biến là caller compile với API một version, runtime lại nạp version khác.
- Đọc stack trace, xác định class owner, in CodeSource/classloader và dùng `javap` để so sánh descriptor.
- Maven chọn version theo nearest definition; Gradle mặc định chọn version cao nhất trong conflict resolution. Dùng dependency tree/insight để hiểu vì sao.
- Spring Boot BOM giữ dependency trong cùng release train; override từng module cần có lý do và kiểm thử.
- Dependency tree không hiển thị mọi thư viện được application server, plugin, shaded JAR hoặc container thêm vào.
- Sửa đúng version hoặc caller, loại duplicate JAR, build lại và xác minh chính artifact runtime.
- Không nuốt `LinkageError`, không ép version mù quáng và không kết luận thành công chỉ vì compile xanh.

### Tài liệu tham khảo chính thức

- Java SE API — `NoSuchMethodError`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NoSuchMethodError.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Viewing and Debugging Dependencies (`dependencies`, `dependencyInsight`): https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Graph Resolution and Version Conflict Resolution: https://docs.gradle.org/current/userguide/graph_resolution.html
- Spring Boot — Managing Dependencies and BOM Support: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
