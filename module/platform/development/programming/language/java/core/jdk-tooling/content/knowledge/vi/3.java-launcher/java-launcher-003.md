# Chạy JAR bằng Java launcher

JAR (Java Archive) là tệp lưu trữ theo định dạng ZIP, thường chứa bytecode .class, tài nguyên và metadata của ứng dụng Java. Java launcher có thể chạy một JAR như một chương trình nếu JAR khai báo lớp khởi chạy trong manifest. Đây là cách đóng gói và triển khai ứng dụng Java phổ biến: người dùng chỉ cần một lệnh gọi Java cùng tên tệp JAR và các tham số cần thiết.

Cần phân biệt ba việc:

- **Tạo JAR**: dùng công cụ **jar** của JDK để đóng gói class và tài nguyên.
- **Khai báo điểm bắt đầu**: đặt thuộc tính **Main-Class** trong manifest.
- **Chạy JAR**: dùng **java -jar** để yêu cầu JVM khởi chạy lớp chính.

Một JAR thư viện có thể hợp lệ dù không có Main-Class. JAR đó dùng làm dependency cho ứng dụng khác, nhưng không thể chạy trực tiếp bằng lệnh java -jar.

## 1. Điều kiện để chạy một JAR

Để chạy JAR theo dạng executable JAR, cần có:

1. Một JVM tương thích với phiên bản bytecode của ứng dụng.
2. Một tệp JAR hợp lệ, có cấu trúc archive đúng.
3. Một lớp chính có phương thức entry point hợp lệ: public static void main(String[] args).
4. Thuộc tính **Main-Class** trong manifest trỏ tới lớp chính.
5. Các dependency cần thiết có thể được JVM tìm thấy tại runtime.

Ví dụ manifest tối thiểu:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main

~~~

Tên lớp trong Main-Class là tên đầy đủ của lớp (fully qualified class name), gồm package và tên lớp; không thêm phần mở rộng .class và không viết đường dẫn thư mục. Nếu lớp nằm trong package com.example, giá trị phải là com.example.Main.

Manifest nằm tại **META-INF/MANIFEST.MF** bên trong JAR. Tên file và đường dẫn phải đúng chữ hoa, chữ thường theo quy ước của định dạng.

## 2. Tạo một executable JAR bằng JDK

Ví dụ sau dùng JDK 17 trở lên. Cấu trúc thư mục ban đầu:

~~~text
jar-demo/
  src/
    com/
      example/
        Main.java
~~~

Nội dung file **src/com/example/Main.java**:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JAR");

        if (args.length > 0) {
            System.out.println("First argument: " + args[0]);
        }
    }
}
~~~

Chương trình in một dòng cố định và in thêm đối số đầu tiên nếu có. Đây là chương trình Java độc lập, có thể biên dịch và chạy trực tiếp trước khi đóng gói.

### Bước 1: Kiểm tra JDK

~~~bash
java --version
javac --version
jar --version
~~~

Ba lệnh trên kiểm tra Java launcher, trình biên dịch và công cụ đóng gói. Nếu cần phát hành ứng dụng cho Java 17, hãy biên dịch bằng JDK 17 hoặc dùng tùy chọn --release 17 của javac trên một JDK mới hơn có hỗ trợ target đó.

### Bước 2: Biên dịch class

Chạy từ thư mục gốc jar-demo:

~~~bash
mkdir -p out
javac --release 17 -d out src/com/example/Main.java
~~~

Trên PowerShell, có thể tạo thư mục output bằng:

~~~powershell
New-Item -ItemType Directory -Force out
javac --release 17 -d out src/com/example/Main.java
~~~

Giải thích:

- **--release 17**: biên dịch theo API và mức bytecode Java 17.
- **-d out**: đặt file .class vào thư mục out và tự tạo cấu trúc package.
- File nguồn thuộc package com.example nên class được tạo tại out/com/example/Main.class.

Sau bước này, cấu trúc chính là:

~~~text
jar-demo/
  out/
    com/
      example/
        Main.class
  src/
    com/
      example/
        Main.java
~~~

### Bước 3: Tạo JAR và khai báo lớp chính

~~~bash
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

Ý nghĩa các tùy chọn:

- **--create**: tạo archive mới.
- **--file app.jar**: đặt tên file đầu ra.
- **--main-class com.example.Main**: ghi thuộc tính Main-Class vào manifest.
- **-C out .**: chuyển thư mục làm việc của lệnh jar sang out rồi thêm toàn bộ nội dung thư mục đó vào archive. Dấu chấm có nghĩa là lấy tất cả nội dung bên trong out.

Lệnh jar là công cụ đóng gói, không phải lệnh chạy ứng dụng. Lệnh java mới khởi động JVM và thực thi bytecode.

### Bước 4: Kiểm tra nội dung JAR

~~~bash
jar --list --file app.jar
~~~

Kết quả sẽ có cấu trúc tương tự:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
~~~

Thứ tự hiển thị có thể khác. Điều cần kiểm tra là có file lớp chính đúng package và manifest nằm tại META-INF/MANIFEST.MF.

Có thể đọc manifest bằng cách giải nén riêng file đó:

~~~bash
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Sau lệnh trên, file được giải nén vào thư mục hiện tại. Nội dung manifest cần có Main-Class: com.example.Main. Nếu chỉ muốn kiểm tra nhanh, có thể dùng công cụ xem archive tương thích ZIP mà không cần giải nén toàn bộ JAR.

### Bước 5: Chạy JAR

~~~bash
java -jar app.jar
~~~

Stdout:

~~~text
Hello from JAR
~~~

Truyền thêm đối số cho chương trình:

~~~bash
java -jar app.jar demo
~~~

Stdout:

~~~text
Hello from JAR
First argument: demo
~~~

Phần đối số xuất hiện sau tên JAR được chuyển vào mảng String[] args của phương thức main. Trong ví dụ này, args[0] nhận giá trị demo.

## 3. Cú pháp và thứ tự tham số của java -jar

Cú pháp tổng quát:

~~~bash
java [JVM options] -jar jar-file [application arguments]
~~~

Các phần có ý nghĩa khác nhau:

- **java**: khởi chạy JVM.
- **JVM options**: tùy chọn cấu hình bộ nhớ, system properties, logging, module và các tính năng runtime.
- **-jar**: yêu cầu launcher chạy ứng dụng từ JAR được chỉ định.
- **jar-file**: đường dẫn đến file JAR.
- **application arguments**: đối số mà chương trình nhận qua String[] args.

Ví dụ:

~~~bash
java -Xms256m -Xmx1g -Dapp.env=production -jar app.jar --port 8080
~~~

Trong lệnh này:

- **-Xms256m**: đặt heap ban đầu là 256 MB.
- **-Xmx1g**: giới hạn heap tối đa là 1 GB.
- **-Dapp.env=production**: tạo system property có tên app.env và giá trị production.
- **--port 8080**: là đối số của ứng dụng, không phải tùy chọn JVM.

Thứ tự rất quan trọng. JVM options phải đặt trước **-jar**. Những phần sau tên JAR được chuyển cho ứng dụng. Ví dụ sau không thiết lập heap tối đa 1 GB:

~~~bash
java -jar app.jar -Xmx1g
~~~

Ở lệnh này, chuỗi -Xmx1g là application argument. Nếu muốn kiểm tra system property trong Java, dùng:

~~~java
String environment = System.getProperty("app.env", "local");
~~~

Nếu muốn kiểm tra đối số ứng dụng, dùng args trong main. System properties và application arguments là hai cơ chế truyền cấu hình khác nhau.

## 4. Dùng đường dẫn JAR và thư mục làm việc

Có thể truyền đường dẫn tương đối hoặc tuyệt đối:

~~~bash
java -jar build/app.jar
java -jar /opt/myapp/app.jar
~~~

Trên Windows:

~~~powershell
java -jar "C:\Apps\My App\app.jar"
~~~

Đặt đường dẫn trong dấu nháy kép khi có khoảng trắng để shell coi toàn bộ đường dẫn là một đối số. Với đường dẫn tương đối, vị trí được tính từ **thư mục làm việc hiện tại của process**, không mặc nhiên tính từ thư mục chứa JAR.

Ví dụ chương trình mở file cấu hình bằng đường dẫn tương đối config/app.properties sẽ tìm file dựa trên current working directory. Khi chạy ứng dụng từ service manager, container hoặc IDE, thư mục làm việc có thể khác với lúc chạy trong terminal. Nếu ứng dụng cần truy cập tài nguyên được đóng gói trong JAR, nên đọc chúng qua classpath resource thay vì giả định chúng là file vật lý bên cạnh JAR.

Có thể kiểm tra thư mục làm việc trong Java bằng:

~~~java
System.out.println(System.getProperty("user.dir"));
~~~

## 5. Manifest và cách khai báo Main-Class thủ công

Tùy chọn --main-class của jar giúp tạo executable JAR nhanh. Khi cần kiểm soát thêm metadata, có thể tạo manifest riêng.

Tạo file **MANIFEST.MF** ở thư mục dự án:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main

~~~

Dòng trống ở cuối manifest là cần thiết để kết thúc phần khai báo. Sau đó tạo JAR:

~~~bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
~~~

Kiểm tra lại bằng:

~~~bash
jar --list --file app.jar
~~~

Không khai báo Main-Class hai lần với giá trị mâu thuẫn. Nếu dùng manifest tự tạo, hãy bảo đảm Main-Class đúng với class đã được đóng gói.

Manifest hỗ trợ nhiều thuộc tính chuẩn và thuộc tính mở rộng. Mỗi thuộc tính có dạng tên: giá trị. Dòng trong manifest có giới hạn độ dài theo byte; giá trị dài phải được ngắt theo quy tắc manifest, các dòng tiếp nối bắt đầu bằng một dấu cách. Dùng công cụ jar để ghi manifest thường an toàn hơn tự nối chuỗi tùy ý.

## 6. Chạy JAR có dependency bên ngoài

Một JAR chỉ chứa các class và tài nguyên được đóng gói vào archive. Nếu ứng dụng phụ thuộc vào thư viện ngoài, JVM phải tìm thấy các thư viện đó tại runtime.

Giả sử cấu trúc triển khai:

~~~text
app/
  app.jar
  lib/
    library-a.jar
    library-b.jar
~~~

Có ba cách phổ biến để cung cấp dependency.

### Cách 1: Dùng manifest Class-Path

Thêm thuộc tính Class-Path vào manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/library-a.jar lib/library-b.jar

~~~

Tạo JAR như bình thường rồi chạy:

~~~bash
java -jar app.jar
~~~

Giá trị Class-Path là danh sách URL được phân tách bằng dấu cách. Đường dẫn tương đối được phân giải theo vị trí của JAR chứa manifest. Vì vậy, với cấu trúc trên, thư mục lib nằm cạnh app.jar. Nếu đường dẫn có ký tự đặc biệt hoặc khoảng trắng, cần biểu diễn theo cú pháp URL phù hợp.

Cách này phù hợp khi có thể triển khai cả JAR chính và các dependency theo cấu trúc thư mục ổn định.

### Cách 2: Dùng classpath ở command line

Có thể chạy lớp chính bằng classpath tường minh:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

Trên Windows, dấu phân cách các phần tử classpath là dấu chấm phẩy:

~~~powershell
java -cp "app.jar;lib/*" com.example.Main
~~~

Trong ví dụ này:

- **-cp** hoặc **-classpath** chỉ định nơi JVM tìm class và resource.
- **app.jar** chứa lớp chính.
- **lib/*** yêu cầu launcher đưa các JAR trực tiếp trong thư mục lib vào classpath.
- **com.example.Main** là lớp có phương thức main được gọi.

Lưu ý: khi dùng **-jar**, các thiết lập classpath trên command line như -cp bị bỏ qua. Vì vậy, không dùng lệnh **java -cp "lib/*" -jar app.jar** với kỳ vọng các thư viện trong lib sẽ được thêm vào classpath. Hãy dùng manifest Class-Path hoặc chạy lớp chính qua -cp như ví dụ trên.

### Cách 3: Đóng gói dependency vào một JAR tổng hợp

Một số build tool hoặc plugin tạo fat JAR/uber JAR, chứa cả class của ứng dụng và dependency. Khi đó có thể chạy bằng:

~~~bash
java -jar app-all.jar
~~~

Cách này tiện khi triển khai một file, nhưng cần dùng công cụ đóng gói có hiểu biết về metadata, resource trùng tên và service loader. Không nên chỉ giải nén thủ công mọi dependency rồi nén lại mà bỏ qua các file metadata như META-INF/services, chữ ký JAR hoặc cấu hình framework.

Một JAR thông thường do Maven hoặc Gradle tạo ra có thể chỉ chứa class của chính project. Việc có đuôi .jar không có nghĩa là JAR đó đã chứa dependency hoặc chắc chắn chạy được bằng -jar.

## 7. Chạy JAR được tạo từ Maven hoặc Gradle

Trong dự án thực tế, build tool thường quản lý dependency, biên dịch, test và đóng gói.

### Maven

Lệnh thường dùng:

~~~bash
mvn clean package
~~~

JAR đầu ra thường nằm trong thư mục target. Tuy nhiên, JAR mặc định có thể chỉ là thư viện và không có Main-Class. Cần cấu hình Maven JAR Plugin để thêm thuộc tính Main-Class nếu muốn dùng java -jar.

Nếu ứng dụng cần dependency bên ngoài, cấu hình Main-Class đơn thuần chưa đủ. Cần một cách phân phối dependency, ví dụ manifest Class-Path cùng thư mục lib, hoặc plugin đóng gói fat JAR phù hợp với dự án.

### Gradle

Với Gradle:

~~~bash
./gradlew build
~~~

Trên Windows:

~~~powershell
.\gradlew.bat build
~~~

Task jar mặc định tạo archive từ output của source set; nó không tự động đóng gói tất cả dependency runtime vào cùng một file. Với ứng dụng cần triển khai, có thể dùng Application Plugin để tạo script và thư mục phân phối chứa runtime dependencies, hoặc dùng plugin fat JAR theo yêu cầu.

Sau khi build, hãy xem nội dung archive và manifest thay vì đoán tên file hay giả định JAR đầu ra là executable. Dùng **jar --list --file path/to/app.jar** và kiểm tra META-INF/MANIFEST.MF.

## 8. Chạy ứng dụng dạng module

Với ứng dụng modular có file module-info.class, có thể khởi chạy module bằng module path thay vì -jar:

~~~bash
java --module-path app.jar --module com.example.app/com.example.Main
~~~

Trong đó com.example.app là tên module khai báo trong module-info.java và com.example.Main là lớp chính. Tên module và lớp chính phải khớp với cấu trúc module đã biên dịch.

Đây là cách chạy theo module system của Java. Với executable JAR kiểu classpath truyền thống, lệnh phổ biến vẫn là:

~~~bash
java -jar app.jar
~~~

Không trộn lẫn quy tắc classpath và module path: classpath dùng để tìm class theo cơ chế class loader truyền thống, còn module path dùng để tìm và phân giải các module.

## 9. Kiểm tra phiên bản Java và tính tương thích

Một ứng dụng được biên dịch bằng JDK mới hơn có thể không chạy trên JVM cũ. Ví dụ class được biên dịch cho Java 21 không thể chạy trên Java 17.

Kiểm tra JVM đang được gọi:

~~~bash
java --version
~~~

Kiểm tra vị trí executable:

~~~bash
where java
~~~

Trên Linux/macOS:

~~~bash
which java
~~~

Máy có thể cài nhiều JDK và PATH có thể trỏ tới bản khác với JAVA_HOME. Vì vậy, khi chạy từ service hoặc script, hãy kiểm tra đúng executable mà process thực sự sử dụng.

Để tạo bytecode tương thích Java 17 khi dùng JDK hỗ trợ:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Tùy chọn --release giúp giới hạn cả mức bytecode và API nền tảng được phép sử dụng. Chỉ đặt source/target version riêng lẻ có thể không ngăn việc vô tình gọi API chỉ có ở JDK mới hơn phiên bản runtime.

## 10. Một số tùy chọn runtime hữu ích

Ví dụ chạy với bộ nhớ và cấu hình:

~~~bash
java -Xms512m -Xmx2g -Dapp.env=production -Duser.timezone=UTC -jar app.jar
~~~

Các nhóm tùy chọn thường gặp:

- **-Xms**: heap ban đầu.
- **-Xmx**: heap tối đa.
- **-Dname=value**: thiết lập system property.
- **-ea**: bật assertion trong ứng dụng.
- **-verbose:class**: in thông tin nạp class, hữu ích khi điều tra classpath ở mức cơ bản.

Không nên đặt -Xmx theo một con số tùy ý. Cần xem giới hạn RAM của máy hoặc container, native memory, thread stack và overhead JVM. Heap tối đa không phải toàn bộ mức RAM process cần dùng.

Để xem cách launcher phân tích các tùy chọn hoặc trợ giúp:

~~~bash
java --help
java -X
~~~

Các tùy chọn nâng cao và tên cờ có thể thay đổi theo phiên bản JDK và JVM implementation. Kiểm tra tài liệu đúng phiên bản trước khi đưa cấu hình vào production.

## 11. Chạy trong môi trường server và ghi log

Có thể chuyển stdout và stderr vào file bằng shell:

~~~bash
java -jar app.jar > app.log 2>&1
~~~

Lệnh này ghi stdout vào app.log và chuyển stderr vào cùng file. Trên Linux/macOS, có thể chạy tiến trình nền bằng shell, nhưng môi trường production nên dùng service manager hoặc container orchestration để quản lý restart, tín hiệu dừng, log rotation, health check và giới hạn tài nguyên.

Một số điểm cần xác định khi triển khai:

- Java executable và phiên bản JDK/JRE mà môi trường sử dụng.
- Thư mục làm việc, đường dẫn cấu hình, thư mục log và quyền truy cập file.
- Biến môi trường và system properties cần thiết.
- Giới hạn heap phù hợp với RAM được cấp.
- Dependency được đóng gói hoặc triển khai đúng vị trí.
- Cách theo dõi stdout, stderr, exit code và trạng thái process.
- Chính sách dừng ứng dụng và xử lý shutdown hook.

Không nên dựa vào terminal đang mở để giữ ứng dụng production. Hãy để hệ thống quản lý dịch vụ chịu trách nhiệm vòng đời process.

## 12. Các lỗi thường gặp khi chạy JAR

| Thông báo hoặc triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| no main manifest attribute | Manifest thiếu Main-Class | Kiểm tra META-INF/MANIFEST.MF và tạo lại JAR với --main-class |
| Unable to access jarfile | Sai đường dẫn, tên file, quyền đọc hoặc file không tồn tại | Kiểm tra current directory, đường dẫn, dấu nháy và quyền |
| Invalid or corrupt jarfile | Archive hỏng hoặc file không phải JAR hợp lệ | Kiểm tra file đầu ra và thử jar --list --file |
| Could not find or load main class | Sai tên lớp, package hoặc classpath | Kiểm tra Main-Class, cấu trúc archive và tên lớp đầy đủ |
| ClassNotFoundException | Ứng dụng yêu cầu nạp một class nhưng class loader không tìm thấy | Kiểm tra dependency và classpath |
| NoClassDefFoundError | Class cần thiết không có tại runtime hoặc khởi tạo class thất bại | Kiểm tra dependency, phiên bản thư viện và nguyên nhân xuất hiện trước đó trong stack trace |
| UnsupportedClassVersionError | Bytecode mới hơn JVM đang chạy hỗ trợ | Dùng JVM mới hơn hoặc biên dịch với --release phù hợp |
| NoSuchMethodError / NoSuchFieldError | Phiên bản thư viện runtime không tương thích với phiên bản lúc biên dịch | Kiểm tra dependency tree và thứ tự classpath |
| Exception in thread "main" | Ứng dụng đã khởi chạy nhưng phát sinh exception | Đọc stack trace và xử lý lỗi trong logic hoặc cấu hình ứng dụng |

Một số ví dụ cụ thể:

**Thiếu Main-Class**

~~~text
no main manifest attribute, in app.jar
~~~

Nguyên nhân thường là JAR chỉ được đóng gói như thư viện. Tạo lại bằng tùy chọn --main-class hoặc cung cấp manifest có Main-Class đúng.

**Thiếu dependency**

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: org/example/Library
~~~

Kiểm tra dependency có được đưa vào fat JAR, được liệt kê trong manifest Class-Path hoặc được thêm vào classpath khi chạy lớp chính hay không.

**JVM quá cũ**

~~~text
java.lang.UnsupportedClassVersionError
~~~

Kiểm tra java --version và phiên bản bytecode mục tiêu. Nếu không thể nâng JVM, biên dịch lại bằng --release tương thích và tránh gọi API mới hơn phiên bản runtime.

Khi chẩn đoán, phân biệt lỗi do launcher không thể tìm thấy hoặc khởi chạy class với exception phát sinh sau khi phương thức main đã bắt đầu chạy.

## 13. Checklist trước khi bàn giao một JAR

- Xác nhận file JAR được tạo thành công và có thể liệt kê nội dung.
- Xác nhận Main-Class trỏ tới đúng class có public static void main(String[] args).
- Kiểm tra dependency runtime và tài nguyên cần thiết.
- Xác nhận phiên bản JVM tối thiểu và kiểm tra bằng đúng Java executable của môi trường đích.
- Chạy thử lệnh java -jar trên môi trường sạch hoặc gần giống production.
- Kiểm tra các tham số JVM, system properties và application arguments.
- Kiểm tra đường dẫn tương đối, thư mục làm việc và quyền đọc/ghi.
- Kiểm tra stdout, stderr, exit code và cách dừng process.
- Kiểm tra nội dung JAR không vô tình chứa secret, file cấu hình riêng tư hoặc dữ liệu không nên phát hành.
- Ghi lại lệnh triển khai và phiên bản artifact để có thể tái tạo và rollback.

## 14. Ghi nhớ

- **jar** dùng để tạo, cập nhật, liệt kê và giải nén archive; **java** dùng để chạy ứng dụng.
- Executable JAR cần thuộc tính **Main-Class** trong manifest.
- Cú pháp chuẩn là **java [JVM options] -jar app.jar [application arguments]**.
- Tùy chọn JVM đặt trước -jar; đối số ứng dụng đặt sau tên JAR.
- JAR có dependency phải cung cấp dependency bằng manifest Class-Path, classpath tường minh hoặc fat JAR.
- Khi dùng -jar, classpath command line như -cp bị bỏ qua.
- JAR chỉ chạy được trên JVM tương thích với bytecode và API mà ứng dụng sử dụng.
- Luôn kiểm tra manifest, nội dung archive, dependency và môi trường chạy khi gặp lỗi.