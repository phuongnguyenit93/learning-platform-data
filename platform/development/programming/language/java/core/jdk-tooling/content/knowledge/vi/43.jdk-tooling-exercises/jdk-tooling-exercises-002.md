# Chạy ứng dụng Java bằng lệnh java

## 1. Vai trò của Java launcher

Lệnh java là chương trình khởi chạy ứng dụng Java. Nó tạo hoặc sử dụng JVM, nạp class/module cần chạy, thiết lập runtime options rồi gọi phương thức entry point của ứng dụng.

Cần phân biệt ba công việc:

- **Compile:** chuyển source .java thành bytecode .class, thường dùng javac hoặc build tool.
- **Package:** gom class, resource và metadata vào JAR/WAR/distribution, thường dùng jar, Maven hoặc Gradle.
- **Run:** khởi chạy class, module, source file hoặc executable JAR bằng java.

Lệnh java không tự động build toàn bộ project Maven/Gradle. Với ứng dụng đã compile, launcher cần biết main class và vị trí class/dependency. Với source-file mode, launcher có thể compile và chạy một source file đơn giản ngay trong một lệnh.

Một quy trình thông thường:

~~~text
Source code
    |
    v
javac / Maven / Gradle
    |
    v
.class files or executable JAR
    |
    v
java launcher
    |
    v
JVM runs main()
~~~

## 2. Kiểm tra Java launcher đang được sử dụng

Trước khi chạy ứng dụng, kiểm tra phiên bản và đường dẫn:

~~~bash
java --version
javac --version
where java
~~~

where java dành cho Windows Command Prompt/PowerShell. Trên Linux/macOS:

~~~bash
java --version
javac --version
command -v java
command -v javac
~~~

java --version cho biết phiên bản runtime thực tế được gọi qua PATH. Nếu máy cài nhiều JDK, terminal, IDE, Maven và Gradle có thể đang sử dụng những bản khác nhau.

Trên Windows PowerShell:

~~~powershell
Get-Command java, javac | Select-Object Name, Source
$env:JAVA_HOME
$env:PATH -split ';'
~~~

Trên Linux/macOS:

~~~bash
command -v java
echo "$JAVA_HOME"
echo "$PATH"
~~~

JAVA_HOME thường trỏ tới thư mục gốc của JDK; PATH nên chứa thư mục bin của JDK đó. Nếu java --version trả về bản không mong muốn, sửa thứ tự PATH hoặc chọn đúng JDK trước khi chẩn đoán lỗi ứng dụng.

## 3. Bốn cách khởi chạy chính

Java launcher có nhiều dạng gọi. Bốn dạng phổ biến:

| Dạng | Cú pháp | Dùng khi |
|---|---|---|
| Source-file mode | java Hello.java | Chạy nhanh một source file. |
| Main class | java -cp classes com.example.Main | Class đã compile, cần classpath. |
| Executable JAR | java -jar app.jar | JAR có manifest Main-Class. |
| Module | java --module-path mods -m module/name | Ứng dụng dùng Java Platform Module System. |

Các JVM options thường được đặt trước tên class, -jar, -m hoặc source file. Arguments dành cho ứng dụng được đặt sau entry point.

## 4. Chạy trực tiếp một source file

Từ Java 11, launcher hỗ trợ source-file mode:

~~~java
// Hello.java
public class Hello {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Chạy:

~~~bash
java Hello.java
java Hello.java "Ada Lovelace"
~~~

Output của lệnh thứ hai:

~~~text
Hello, Ada Lovelace!
~~~

Có thể chỉ định source level:

~~~bash
java --source 17 Hello.java "Java 17"
~~~

Trong source-file mode, Java launcher compile source rồi chạy chương trình. Cách này phù hợp với demo, script nhỏ và bài học. Project nhiều class, dependency, resource hoặc module nên dùng build tool hoặc compile thành class/JAR rõ ràng.

Tên source file phải đúng với đường dẫn đang chạy. Nếu path có khoảng trắng, đặt trong dấu nháy:

~~~powershell
java "C:\Projects\Java Demo\Hello.java" "Ada Lovelace"
~~~

## 5. Compile trước rồi chạy main class

Với project thông thường, hãy compile source thành class file trước.

Ví dụ cấu trúc:

~~~text
project/
├── src/
│   └── com/example/App.java
└── build/
    └── classes/
~~~

File src/com/example/App.java:

~~~java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "local");
        System.out.println("Application started");
        System.out.println("mode=" + mode);
        System.out.println("argument.count=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("argument[" + i + "]=" + args[i]);
        }
    }
}
~~~

Compile bằng JDK 17 API:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/com/example/App.java
~~~

Chạy main class:

~~~bash
java -cp build/classes com.example.App local "two words"
~~~

Stdout chính xác:

~~~text
Application started
mode=local
argument.count=2
argument[0]=local
argument[1]=two words
~~~

-cp là viết tắt của --class-path. Giá trị build/classes là thư mục gốc của package tree; không truyền trực tiếp đường dẫn đến file App.class.

Tên class đầy đủ là com.example.App, gồm package và class name, không có .java hoặc .class.

## 6. Hiểu classpath

Classpath cho JVM biết nơi tìm class và resource. Nó có thể chứa:

- Thư mục chứa class đã compile.
- JAR dependency.
- Nhiều thư mục và JAR kết hợp.
- Wildcard cho các JAR trong một thư mục.

Ví dụ Windows:

~~~powershell
java -cp "build\classes;lib\helper.jar;lib\logging.jar" com.example.App
~~~

Có thể dùng wildcard:

~~~powershell
java -cp "build\classes;lib\*" com.example.App
~~~

Linux/macOS dùng dấu : để phân cách các thành phần:

~~~bash
java -cp "build/classes:lib/helper.jar:lib/logging.jar" com.example.App
java -cp "build/classes:lib/*" com.example.App
~~~

Dấu phân cách classpath là ; trên Windows và : trên Linux/macOS. Khi viết script dùng nhiều OS, tạo classpath bằng API/tool phù hợp thay vì giả định một dấu phân cách dùng được ở mọi nơi.

Wildcard lib/* của Java launcher đưa các JAR trực tiếp trong thư mục lib vào classpath; nó không tự tìm đệ quy trong các thư mục con. Đặt classpath trong dấu nháy để tránh shell xử lý wildcard hoặc khoảng trắng ngoài ý muốn.

Nếu không truyền -cp, launcher có thể dùng classpath mặc định hoặc biến môi trường CLASSPATH. Trong script và CI, nên truyền classpath tường minh để kết quả không phụ thuộc cấu hình máy.

## 7. Chạy executable JAR

Executable JAR khai báo entry point trong META-INF/MANIFEST.MF bằng thuộc tính Main-Class.

Tạo JAR từ class đã compile:

~~~bash
jar --create \
  --file build/app.jar \
  --main-class com.example.App \
  -C build/classes .
~~~

Chạy:

~~~bash
java -jar build/app.jar
~~~

Java đọc Main-Class từ manifest rồi gọi phương thức main của class đó.

Kiểm tra nội dung JAR:

~~~bash
jar --list --file build/app.jar
~~~

Đọc manifest:

~~~bash
jar --extract --file build/app.jar META-INF/MANIFEST.MF
~~~

Manifest tối thiểu có dạng:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.App
~~~

Tên class phải chính xác, có package đầy đủ và phân biệt chữ hoa/chữ thường. Nếu JAR không có Main-Class, nó vẫn có thể là library JAR hợp lệ; chỉ là không thể chạy độc lập bằng java -jar.

## 8. Truyền arguments cho ứng dụng

Arguments dành cho ứng dụng đứng sau tên main class, -jar, module entry point hoặc source file.

Ví dụ:

~~~bash
java -cp build/classes com.example.App import "quarter 1.csv" --verbose
~~~

Trong main(String[] args):

- args[0] là import.
- args[1] là quarter 1.csv.
- args[2] là --verbose.

Dấu nháy giúp shell truyền chuỗi có khoảng trắng thành một argument duy nhất.

Windows PowerShell:

~~~powershell
java -jar .\build\app.jar "quarter 1.csv" --verbose
~~~

Linux/macOS:

~~~bash
java -jar ./build/app.jar "quarter 1.csv" --verbose
~~~

Java launcher không diễn giải ý nghĩa của application arguments. Chính chương trình cần parse args, kiểm tra số lượng, validate input và hiển thị usage khi người dùng truyền sai.

## 9. Thứ tự JVM options và application arguments

Một lỗi phổ biến là đặt JVM option sau -jar hoặc sau tên main class. Khi đó option có thể bị chuyển thành application argument.

Đúng:

~~~bash
java -Dapp.mode=ci -Xms32m -Xmx128m -jar build/app.jar first "two words"
~~~

Cấu trúc:

~~~text
java [JVM options] -jar app.jar [application arguments]
~~~

Tương tự khi chạy main class:

~~~bash
java -Dapp.mode=ci -Xmx256m -cp build/classes com.example.App first
~~~

-D, -Xms, -Xmx nằm trước entry point. Các giá trị sau com.example.App được đưa vào args.

Trong Windows PowerShell, nên quote system property option có dấu chấm để tránh PowerShell 5.1 tách token khi gọi native executable:

~~~powershell
java '-Dapp.mode=ci' '-Xms32m' '-Xmx128m' -jar .\build\app.jar first "two words"
~~~

Cách viết có dấu nháy cũng chạy trong Bash. Nếu một lệnh chạy được trong Command Prompt nhưng thất bại trong PowerShell, hãy kiểm tra cách shell truyền arguments trước khi thay đổi code Java.

## 10. Truyền system properties bằng -D

System property là cấu hình dạng key/value có thể đọc trong JVM:

~~~bash
java -Dapp.mode=production -Dapp.region=ap-southeast-1 \
  -cp build/classes com.example.App
~~~

Trong code:

~~~java
String mode = System.getProperty("app.mode", "local");
String region = System.getProperty("app.region", "default");
~~~

-Dname=value phải xuất hiện trước entry point. Đây là system property của JVM, không phải application argument và cũng không phải environment variable.

Dùng system property cho cấu hình đơn giản như mode, endpoint hoặc feature flag. Với cấu hình phức tạp, dùng file config hoặc configuration framework và validate giá trị ngay khi ứng dụng khởi động.

Không đưa password, API token hoặc private key vào command line nếu có thể tránh. Command line có thể xuất hiện trong process listing, diagnostic log hoặc history của shell.

## 11. Cấu hình bộ nhớ JVM

Hai option thường gặp:

- -Xms: heap size ban đầu.
- -Xmx: heap size tối đa.

Ví dụ:

~~~bash
java -Xms256m -Xmx1g -jar build/app.jar
~~~

-Xmx1g đặt giới hạn heap tối đa khoảng 1 GiB. Nó không có nghĩa JVM sẽ dùng ngay 1 GiB hoặc toàn bộ bộ nhớ máy.

Chọn heap theo workload, container memory limit và tài nguyên còn lại cho metaspace, thread stack, direct buffer, native library và hệ điều hành. Đặt -Xmx quá cao có thể khiến process bị hệ điều hành/container kill; quá thấp có thể gây OutOfMemoryError.

Một số tùy chọn -X và -XX phụ thuộc phiên bản hoặc implementation JVM. Kiểm tra tài liệu của JDK đang dùng:

~~~bash
java -X
java -XX:+PrintFlagsFinal -version
~~~

Không sao chép hàng loạt JVM flags từ một máy khác mà chưa đo và kiểm thử.

## 12. Bật Java assertions

Java assertions giúp kiểm tra invariant trong lúc phát triển hoặc test.

Ví dụ:

~~~java
public class CheckArgs {
    public static void main(String[] args) {
        assert args.length > 0 : "Expected at least one argument";
        System.out.println(args[0]);
    }
}
~~~

Assertions mặc định không được bật. Chạy với -ea:

~~~bash
java -ea -cp build/classes CheckArgs hello
~~~

Nếu không có -ea, câu lệnh assert có thể không được thực thi. Không dùng assertion để validate dữ liệu người dùng hoặc thay thế xử lý lỗi bắt buộc; dùng kiểm tra thông thường và exception cho những điều kiện phải luôn được kiểm tra.

## 13. Working directory và đường dẫn file

Working directory là thư mục process nhìn thấy khi mở đường dẫn tương đối. Nó không nhất thiết là thư mục chứa JAR hoặc class file.

Kiểm tra trong Java:

~~~java
System.out.println(System.getProperty("user.dir"));
~~~

Ví dụ chạy:

~~~bash
java -jar /opt/apps/app.jar
~~~

Nếu working directory là /home/user, một đường dẫn tương đối như config/app.properties sẽ được giải quyết từ /home/user, không phải /opt/apps.

Cách xử lý:

- Chọn working directory rõ ràng trong script/service/CI.
- Dùng absolute path khi file nằm ở vị trí cố định.
- Với resource đóng gói trong JAR, đọc qua classpath resource API thay vì giả định có file vật lý.
- Không ghép path bằng dấu slash cố định; dùng Path.resolve.
- Không phụ thuộc thư mục hiện tại của IDE hoặc terminal developer.

Đường dẫn config và dữ liệu runtime nên được xác định qua option, environment variable hoặc cấu hình triển khai rõ ràng.

## 14. Environment variables ảnh hưởng đến việc chạy

Các biến thường gặp:

| Biến | Tác dụng |
|---|---|
| JAVA_HOME | Chỉ thư mục cài JDK/JRE mà công cụ khác có thể sử dụng. |
| PATH | Quyết định shell tìm executable java nào. |
| CLASSPATH | Classpath mặc định khi không truyền classpath rõ ràng. |
| JDK_JAVA_OPTIONS | Bổ sung launcher options cho các lần gọi Java launcher. |
| JAVA_TOOL_OPTIONS | Bổ sung JVM options khi JVM được khởi tạo. |

JDK_JAVA_OPTIONS có thể khiến lệnh chạy khác với những gì nhìn thấy trực tiếp trên command line. JAVA_TOOL_OPTIONS cũng có thể thêm agent hoặc VM options. Nếu ứng dụng khởi động với option lạ, kiểm tra các biến này.

Trên PowerShell:

~~~powershell
Get-ChildItem Env:JAVA_HOME, Env:CLASSPATH, Env:JDK_JAVA_OPTIONS, Env:JAVA_TOOL_OPTIONS
~~~

Trên Linux/macOS:

~~~bash
env | grep -E '^(JAVA_HOME|CLASSPATH|JDK_JAVA_OPTIONS|JAVA_TOOL_OPTIONS)='
~~~

Không đặt classpath toàn cục nếu mỗi project có dependency khác nhau. Không in toàn bộ environment vào log vì có thể lộ secret.

## 15. Chạy ứng dụng modular

Ứng dụng dùng Java Platform Module System có thể được khởi chạy qua module path.

Ví dụ cấu trúc:

~~~text
src/
├── module-info.java
└── com/example/ModuleApp.java
~~~

module-info.java:

~~~java
module com.example.app {
}
~~~

ModuleApp.java:

~~~java
package com.example;

public final class ModuleApp {
    public static void main(String[] args) {
        System.out.println("Module application started");
        System.out.println("argument.count=" + args.length);
    }
}
~~~

Compile module:

~~~bash
javac --release 17 \
  -d mods/com.example.app \
  src/module-info.java \
  src/com/example/ModuleApp.java
~~~

Chạy từ exploded module directory:

~~~bash
java --module-path mods \
  --module com.example.app/com.example.ModuleApp "two words"
~~~

Có thể đóng gói module thành JAR:

~~~bash
jar --create \
  --file build/module-app.jar \
  -C mods/com.example.app .
~~~

Chạy modular JAR:

~~~bash
java --module-path build/module-app.jar \
  --module com.example.app/com.example.ModuleApp "two words"
~~~

--module-path xác định nơi tìm module; --module hoặc -m chọn module và main class. Khi debug lỗi module, kiểm tra tên module và dependency bằng:

~~~bash
jar --describe-module --file build/module-app.jar
java --list-modules
~~~

## 16. Chọn đúng runtime Java cho bytecode

Runtime phải hỗ trợ class file version và API mà ứng dụng sử dụng.

Ví dụ compile tương thích Java 17:

~~~bash
javac --release 17 -d build/classes src/com/example/App.java
~~~

Sau đó có thể chạy trên Java 17 hoặc các runtime mới hơn, miễn là dependency và tính năng ứng dụng tương thích.

Kiểm tra runtime:

~~~bash
java --version
~~~

Kiểm tra class file version:

~~~bash
javap -verbose -classpath build/classes com.example.App
~~~

Nếu gặp UnsupportedClassVersionError, runtime đang dùng quá cũ so với bytecode. Cách xử lý là chọn runtime đủ mới hoặc build lại với --release phù hợp và bảo đảm dependency cũng tương thích.

Build JDK và runtime JDK có thể khác nhau. Hãy test trên phiên bản runtime tối thiểu mà sản phẩm cam kết hỗ trợ.

## 17. Đọc stdin, stdout, stderr và exit code

Ứng dụng console thường giao tiếp qua ba luồng:

- stdin: dữ liệu đầu vào.
- stdout: kết quả thông thường.
- stderr: lỗi và thông báo chẩn đoán.

Chuyển hướng output:

~~~bash
java -jar app.jar > app.log 2> app-error.log
~~~

Gộp stderr vào stdout:

~~~bash
java -jar app.jar > app.log 2>&1
~~~

Truyền file làm stdin:

~~~bash
java -jar app.jar < input.txt
~~~

Exit code được đọc ngay sau khi process kết thúc. Trên PowerShell:

~~~powershell
java -jar .\app.jar
$LASTEXITCODE
~~~

Trên Bash:

~~~bash
java -jar ./app.jar
echo $?
~~~

Theo quy ước thông dụng, 0 biểu thị thành công và giá trị khác 0 biểu thị lỗi. Chương trình nên trả exit code nhất quán bằng System.exit(code) khi cần báo trạng thái cho script/CI; không gọi System.exit trong thư viện dùng chung.

## 18. Chạy JAR có dependency bên ngoài

Một JAR có thể chứa main class nhưng vẫn cần thư viện khác. Nếu dependency nằm trong thư mục lib, có thể chạy main class qua classpath.

Windows:

~~~powershell
java -cp "app.jar;lib/*" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

Lưu ý: khi dùng java -jar app.jar, classpath được truyền qua -cp hoặc -classpath không được sử dụng như cách bổ sung dependency. -jar lấy entry point từ manifest.

Có hai lựa chọn:

1. Chạy main class trực tiếp bằng -cp, liệt kê JAR chính và dependency.
2. Giữ java -jar và khai báo dependency tương đối trong manifest Class-Path.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/helper.jar lib/logging.jar
~~~

Các path trong manifest Class-Path là URL tương đối với JAR chứa manifest và dùng dấu slash /, kể cả trên Windows. Manifest chỉ tham chiếu tới dependency; nó không tự đóng gói thư viện.

## 19. Chạy ứng dụng được build bằng Maven hoặc Gradle

Với Maven, trước hết build artifact:

~~~bash
mvn -B clean package
~~~

Nếu JAR có Main-Class và dependency được phân phối đúng, chạy:

~~~bash
java -jar target/app-1.0.0.jar
~~~

Với Gradle:

~~~bash
./gradlew clean jar
java -jar build/libs/app-1.0.0.jar
~~~

Windows dùng wrapper:

~~~powershell
.\gradlew.bat clean jar
java -jar .\build\libs\app-1.0.0.jar
~~~

Nếu project dùng Gradle Application Plugin, có thể khai báo:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.example.Main'
}
~~~

Sau đó chạy task run:

~~~bash
./gradlew run
~~~

Task run dùng runtime classpath do Gradle quản lý. Lệnh java -jar chạy artifact đã đóng gói và cần manifest/dependency phù hợp. Hai cách có thể có classpath khác nhau; kiểm tra cả hai nếu ứng dụng chỉ lỗi sau khi đóng gói.

## 20. Chạy trong Windows, Linux và macOS

| Nền tảng | Chạy executable JAR | Ghi chú |
|---|---|---|
| Windows CMD | java -jar app.jar | Classpath separator là ;. |
| Windows PowerShell | java -jar .\app.jar | Quote JVM option như '-Dapp.mode=ci' khi cần. |
| Linux | java -jar ./app.jar | Classpath separator là :. |
| macOS | java -jar ./app.jar | Kiểm tra đúng JDK được chọn qua PATH hoặc java_home. |

Một JAR thuần Java có thể chạy trên nhiều OS nếu runtime và dependency tương thích. Ứng dụng có JNI/native library, file path đặc thù hoặc service tích hợp OS có thể cần artifact/runtime khác nhau.

Không giả định nhấp đúp JAR sẽ hoạt động. File association và desktop launcher phụ thuộc hệ điều hành; chạy từ terminal giúp xem lỗi và exit code rõ hơn.

## 21. Chẩn đoán lỗi khi chạy ứng dụng

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| java không được nhận diện | Java chưa cài hoặc PATH sai. | Kiểm tra java --version, JAVA_HOME, PATH. |
| Could not find or load main class | Sai tên class hoặc classpath. | Kiểm tra package, -cp và vị trí .class. |
| no main manifest attribute | JAR thiếu Main-Class. | Kiểm tra manifest; xác định JAR có phải executable không. |
| Unable to access jarfile | Sai đường dẫn hoặc quyền đọc. | Kiểm tra working directory, absolute path và quyền file. |
| NoClassDefFoundError | Thiếu runtime dependency. | Bổ sung dependency vào classpath/manifest/module path. |
| UnsupportedClassVersionError | Runtime cũ hơn bytecode. | Chọn JDK mới hoặc build với --release phù hợp. |
| FindException: Module not found | Thiếu module hoặc sai module path. | Kiểm tra --module-path, tên module và descriptor. |
| OutOfMemoryError | Heap hoặc native memory không đủ. | Đo memory usage, kiểm tra leak và điều chỉnh JVM options. |
| Ứng dụng đọc sai file config | Working directory không như dự kiến. | In user.dir, truyền absolute path hoặc config path rõ ràng. |
| Option lạ tự xuất hiện | Environment thêm JVM options. | Kiểm tra JDK_JAVA_OPTIONS và JAVA_TOOL_OPTIONS. |
| PowerShell truyền sai -D | Native argument parsing/quoting. | Quote toàn bộ token, ví dụ '-Dapp.mode=ci'. |
| Cửa sổ console đóng nhanh | Ứng dụng kết thúc hoặc lỗi không hiển thị. | Chạy từ terminal và kiểm tra stdout/stderr. |

Khi có stack trace, bắt đầu từ exception đầu tiên có ý nghĩa và đọc nguyên nhân Caused by sâu nhất. Không thay đổi heap, classpath hoặc JDK theo phỏng đoán; trước tiên xác định launcher đang chạy gì và nhận những arguments nào.

## 22. Bảo mật khi khởi chạy ứng dụng

- Chỉ chạy JAR từ nguồn đáng tin cậy.
- Kiểm tra checksum hoặc chữ ký khi nhà phát hành cung cấp.
- Không truyền secret trong command line nếu có kênh cấu hình an toàn hơn.
- Không log toàn bộ environment variables hoặc system properties có thể chứa credential.
- Giới hạn quyền user và quyền truy cập file của process.
- Dùng JDK được cập nhật bảo mật.
- Không mở remote debugging port trong môi trường public nếu không có kiểm soát truy cập.
- Kiểm tra native dependency vì nó chạy với quyền của process Java.

Các JVM options ảnh hưởng bảo mật, TLS, module access hoặc native access cần được quản lý như cấu hình triển khai, có review và test.

## 23. Lab: chạy cùng ứng dụng qua source, class, JAR và module

Bộ lab dùng một chương trình Java 17 để kiểm tra các cách launch. Chương trình com.example.App in system property và application arguments:

~~~java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "local");
        System.out.println("Application started");
        System.out.println("mode=" + mode);
        System.out.println("argument.count=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("argument[" + i + "]=" + args[i]);
        }
    }
}
~~~

Compile class:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/App.java
~~~

Run class:

~~~bash
java -cp build/classes com.example.App local "two words"
~~~

Tạo và chạy JAR:

~~~bash
jar --create --file build/app.jar --main-class com.example.App -C build/classes .
java -Dapp.mode=ci -Xms32m -Xmx128m -jar build/app.jar first "two words"
~~~

Với Windows PowerShell, quote JVM options:

~~~powershell
java '-Dapp.mode=ci' '-Xms32m' '-Xmx128m' -jar .\build\app.jar first "two words"
~~~

Output của lần chạy JAR:

~~~text
Application started
mode=ci
argument.count=2
argument[0]=first
argument[1]=two words
~~~

Lệnh không truyền application argument:

~~~bash
java -jar build/app.jar
~~~

Output:

~~~text
Application started
mode=local
argument.count=0
~~~

## 24. Kết quả lab đã kiểm chứng

Các lệnh đã được chạy trên Windows 11 với Azul Zulu JDK 24.0.2 và runtime Amazon Corretto 17.0.15:

| Cách chạy | Kết quả |
|---|---|
| Source-file mode java Hello.java | PASS |
| Compile javac --release 17 | PASS |
| Main class với explicit classpath | PASS |
| Executable JAR với java -jar | PASS |
| -Dapp.mode, -Xms, -Xmx | PASS |
| Application arguments có khoảng trắng | PASS |
| Java 17 chạy JAR compile target 17 | PASS |
| Modular JAR qua --module-path và --module | PASS |

Source-file mode in chính xác Hello, source file!.

JAR chạy trên Java 17 với output:

~~~text
Application started
mode=local
argument.count=2
argument[0]=first
argument[1]=two words
~~~

Modular JAR in:

~~~text
Module application started
argument.count=1
~~~

Kết quả này xác nhận các dạng launch trong lab trên Windows và các JDK đã nêu. Nó không thay thế kiểm thử riêng cho Linux/macOS hoặc dependency/native library của ứng dụng thực tế.

## 25. Checklist trước khi đưa lệnh chạy vào script hoặc CI

1. Kiểm tra đúng java executable và phiên bản runtime.
2. Xác định launch mode: source file, main class, JAR hay module.
3. Đảm bảo classpath/module path chứa đầy đủ runtime dependencies.
4. Đặt JVM options trước entry point.
5. Đặt application arguments sau entry point.
6. Quote path và arguments có khoảng trắng.
7. Xác định working directory.
8. Truyền config path và environment rõ ràng.
9. Chọn heap phù hợp với giới hạn container/máy.
10. Thu stdout, stderr và exit code.
11. Test trên runtime Java tối thiểu được hỗ trợ.
12. Kiểm tra checksum/signature nếu chạy artifact bên ngoài.

Một script chạy production nên kiểm tra exit code tương ứng với shell, ghi log vừa đủ và không in secret.

## 26. Tài liệu tham khảo

- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [The jar Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [JAR File Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html)
- [Java Platform Module System](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/package-summary.html)
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)

Để chạy ứng dụng Java ổn định, hãy xác định đúng entry point, runtime version, classpath hoặc module path, JVM options, application arguments và working directory. Khi lệnh được đưa vào script hoặc CI, ghi rõ những đầu vào này để kết quả không phụ thuộc cấu hình ngầm của máy developer.