# Thuật ngữ cốt lõi của JDK Tooling

JDK Tooling là tập hợp công cụ đi kèm Java Development Kit (JDK), hỗ trợ toàn bộ vòng đời của một chương trình Java: viết mã nguồn, biên dịch, chạy, đóng gói, kiểm tra phụ thuộc, tạo môi trường chạy và chẩn đoán ứng dụng. Hiểu đúng thuật ngữ giúp phân biệt công cụ nào xử lý mã nguồn, công cụ nào khởi chạy JVM, và thành phần nào chịu trách nhiệm ở thời điểm chạy.

## 1. Bản đồ khái niệm

Một luồng làm việc Java điển hình có thể hình dung như sau:

1. **Mã nguồn** (.java) được viết bằng ngôn ngữ Java.
2. **Trình biên dịch** javac kiểm tra mã nguồn và tạo **bytecode** trong các tệp .class.
3. **Trình khởi chạy** java tìm lớp hoặc module cần chạy, khởi tạo JVM và chuyển quyền điều khiển cho chương trình.
4. **JVM** nạp, liên kết và thực thi bytecode. Tùy JVM, mã có thể được thông dịch hoặc biên dịch động thành mã máy.
5. Các công cụ khác của JDK hỗ trợ đóng gói, tài liệu hóa, kiểm tra API, phân tích phụ thuộc, ký số, tạo runtime image và chẩn đoán tiến trình.

Không phải mọi ứng dụng đều cần tất cả bước. Ví dụ, jshell có thể chạy biểu thức và đoạn mã tương tác; java cũng có thể chạy một tệp nguồn đơn giản trực tiếp mà không cần người dùng gọi javac trước.

## 2. JDK, JRE và JVM

### JVM — Java Virtual Machine

**JVM** là máy ảo thực thi Java bytecode. JVM quy định môi trường thực thi và các hành vi như nạp lớp, liên kết, quản lý bộ nhớ, xử lý luồng, kiểm tra bytecode và cơ chế ngoại lệ.

- JVM không phải là ngôn ngữ Java và cũng không phải trình biên dịch javac.
- Một JVM cụ thể là một bản triển khai của đặc tả JVM. HotSpot là một triển khai JVM phổ biến trong các bản phân phối OpenJDK.
- JVM có thể thông dịch bytecode hoặc dùng **JIT (Just-In-Time compiler)** để biên dịch những đoạn mã thường chạy thành mã máy trong lúc ứng dụng hoạt động.
- JVM chịu trách nhiệm thực thi bytecode; nó không tự động cung cấp toàn bộ công cụ phát triển như javac, javadoc hay jlink.

### JRE — Java Runtime Environment

**JRE** là khái niệm chỉ môi trường cần thiết để chạy ứng dụng Java: JVM cùng các thư viện và thành phần runtime liên quan.

Từ Java 9 trở đi, mô hình phát hành JRE riêng biệt không còn là cách phân phối mặc định phổ biến như trước. Nhiều nhà cung cấp phân phối JDK đầy đủ; ứng dụng có thể dùng runtime image tùy biến được tạo bằng jlink. Vì vậy, khi đọc tài liệu cũ, cần hiểu JRE là khái niệm về môi trường chạy, không mặc định rằng máy phải có một thư mục hoặc bộ cài riêng mang tên JRE.

### JDK — Java Development Kit

**JDK** là bộ công cụ dành cho phát triển Java. Nó bao gồm runtime để chạy chương trình và các công cụ phát triển, chẳng hạn:

- **javac**: biên dịch mã nguồn Java.
- **java**: khởi chạy ứng dụng Java.
- **jar**: tạo và thao tác với tệp JAR.
- **javadoc**: sinh tài liệu API.
- **javap**: xem thông tin lớp và bytecode.
- **jshell**: môi trường chạy Java tương tác.
- **jlink**, **jpackage**: tạo runtime image và gói cài đặt ứng dụng.
- Các công cụ chẩn đoán như **jcmd**, **jstack**, **jmap** và **jfr**.

Có thể nhớ mối quan hệ khái quát: **JDK phục vụ phát triển; JRE mô tả môi trường chạy; JVM thực thi bytecode**. Đây là ba khái niệm liên quan nhưng không đồng nghĩa.

## 3. Phiên bản, nhà cung cấp và cấu hình JDK

### Java version và JDK version

Phiên bản Java thường được nhắc đến theo phiên bản nền tảng, ví dụ Java 17, Java 21 hoặc Java 25. JDK là bộ triển khai cụ thể dùng để phát triển và chạy ứng dụng trên phiên bản đó.

Khi kiểm tra môi trường, hai lệnh thường dùng là:

~~~bash
java --version
javac --version
~~~

java --version hiển thị phiên bản của trình khởi chạy/JDK được tìm thấy qua môi trường lệnh. javac --version hiển thị phiên bản trình biên dịch đang được gọi. Hai lệnh có thể cho kết quả khác nhau nếu máy có nhiều JDK và PATH trỏ đến các thư mục khác nhau.

### Feature release, LTS và bản cập nhật

- **Feature release** là bản phát hành Java có phiên bản chính tăng theo chu kỳ phát hành, ví dụ 17, 21, 25.
- **LTS (Long-Term Support)** là nhãn hỗ trợ dài hạn do nhà cung cấp hoặc chính sách phát hành áp dụng cho một số phiên bản. LTS không phải một cơ chế biên dịch hay một loại bytecode.
- **Update/patch release** là bản cập nhật trong cùng dòng phiên bản, thường chứa sửa lỗi, cập nhật bảo mật và cải tiến ổn định.
- **Preview feature** là tính năng xem trước, cần được bật tường minh khi biên dịch và chạy bằng --enable-preview theo quy tắc của phiên bản tương ứng. Không nên mặc định preview feature có cùng cam kết tương thích như tính năng đã hoàn tất.

### JDK distribution và vendor

**JDK distribution** là gói JDK do một nhà cung cấp xây dựng và phát hành. Các bản phân phối có thể khác nhau về lịch cập nhật, giấy phép, nền tảng hỗ trợ, công cụ đi kèm và chính sách hỗ trợ. Nhiều bản phân phối dựa trên mã nguồn OpenJDK.

Khi chọn JDK, cần xác định ít nhất:

- Phiên bản Java mục tiêu của dự án.
- Hệ điều hành và kiến trúc CPU.
- Nhà cung cấp và chính sách cập nhật cần dùng.
- Yêu cầu giấy phép và hỗ trợ của tổ chức.

Các bản phân phối tuân thủ cùng đặc tả Java thường hướng đến khả năng tương thích cao, nhưng không nên suy ra rằng mọi gói cài đặt có chính sách hỗ trợ, thành phần bổ sung và lịch cập nhật giống nhau.

### JAVA_HOME và PATH

- **JAVA_HOME** thường trỏ đến thư mục gốc của JDK đang được dự án hoặc công cụ build cấu hình sử dụng. Ví dụ, nếu JDK được cài tại C:\Java\jdk-21, thì JAVA_HOME có thể nhận giá trị đó.
- **PATH** là danh sách thư mục hệ điều hành tìm kiếm khi người dùng gọi một lệnh như java hoặc javac.
- Thêm thư mục bin của JDK vào PATH giúp gọi công cụ từ mọi thư mục. Trên Windows, đường dẫn thường có dạng %JAVA_HOME%\bin; trên Linux/macOS thường có dạng $JAVA_HOME/bin.
- JAVA_HOME và PATH có vai trò khác nhau. Đặt JAVA_HOME không tự bảo đảm rằng lệnh java đang chạy đến từ JDK đó; thứ tự thư mục trong PATH vẫn quyết định chương trình nào được tìm thấy trước.

Để kiểm tra lệnh thực tế được hệ điều hành tìm thấy, có thể dùng where java trên Windows hoặc which java trên Linux/macOS, rồi đối chiếu với JAVA_HOME.

## 4. Mã nguồn, bytecode và các dạng đầu ra

### Source file

**Source file** là tệp mã nguồn, thường có phần mở rộng .java. Tên tệp thường phải khớp với tên lớp public cấp cao nhất trong tệp. Mã nguồn được biên dịch bởi javac hoặc được xử lý bởi một công cụ hỗ trợ Java tương ứng.

### Bytecode và class file

**Bytecode** là tập lệnh trung gian mà JVM hiểu và thực thi. Sau khi biên dịch, javac thường tạo một **class file** có phần mở rộng .class.

Một class file chứa bytecode cùng metadata như tên lớp, thông tin phương thức, trường, hằng số và phiên bản định dạng class file. Class file không phải tệp mã máy dành riêng cho một CPU. JVM có thể thực thi nó trên những nền tảng có JVM tương thích.

### Class loader

**Class loader** là thành phần nạp định nghĩa lớp vào JVM. Lớp thường được nạp khi cần, thay vì toàn bộ lớp của ứng dụng phải được nạp ngay lúc khởi động. Class loader tham gia vào quá trình nạp, liên kết và khởi tạo lớp.

Tên đầy đủ của một lớp thường gồm tên package và tên lớp, ví dụ com.example.tools.Main. Trong môi trường có nhiều class loader, danh tính lớp còn gắn với class loader đã định nghĩa lớp đó; hai lớp cùng tên nhưng do hai class loader khác nhau định nghĩa có thể được JVM xem là hai kiểu khác nhau.

### Package

**Package** là cơ chế nhóm lớp và tạo không gian tên trong Java. Ví dụ, com.example.tools là một tên package. Cấu trúc thư mục mã nguồn thường phản ánh tên package, nhưng package và thư mục trên đĩa là hai khái niệm khác nhau.

### Artifact

**Artifact** là sản phẩm được tạo ra hoặc phân phối sau một bước build. Trong dự án Java, artifact có thể là thư mục chứa class file, tệp JAR, tệp JMOD, runtime image hoặc gói cài đặt. Tên gọi này thường xuất hiện trong tài liệu build và CI/CD.

## 5. Classpath, module path và Java Platform Module System

### Classpath

**Classpath** là danh sách vị trí mà trình biên dịch hoặc JVM tìm kiếm lớp và tài nguyên theo cơ chế class path. Một mục classpath có thể là thư mục, tệp JAR hoặc một số dạng archive được hỗ trợ.

Ví dụ:

~~~bash
java -cp out com.example.Main
~~~

Ở đây out là thư mục chứa class file; com.example.Main là tên lớp đầy đủ cần khởi chạy. Tùy hệ điều hành, dấu phân cách giữa nhiều mục classpath khác nhau: dấu ; trên Windows và dấu : trên Linux/macOS.

Có thể viết -cp hoặc --class-path trong các lệnh hỗ trợ tùy chọn này. Classpath thường được dùng cho ứng dụng theo mô hình classpath truyền thống.

### Module và module path

**Module** là đơn vị đóng gói và khai báo phụ thuộc trong Java Platform Module System (JPMS), được giới thiệu trong Java 9. Một module có thể khai báo tên, các package được xuất ra và các module mà nó phụ thuộc.

Tệp module-info.java là module descriptor ở mã nguồn. Sau khi biên dịch, thông tin module được lưu trong module descriptor tương ứng.

**Module path** là nơi trình biên dịch hoặc JVM tìm kiếm các module. Có thể chỉ định bằng --module-path hoặc -p trong những lệnh hỗ trợ. Module path phục vụ cơ chế module; nó không chỉ là một cách viết khác của classpath.

### Named, automatic và unnamed module

- **Named module** có tên module được khai báo rõ ràng, thường thông qua module-info.java.
- **Automatic module** là module được suy ra khi một JAR không có module descriptor được đặt trên module path; tên module có thể được suy ra từ metadata hoặc tên tệp theo quy tắc của nền tảng.
- **Unnamed module** là module mà các lớp trên classpath thuộc về. Mỗi class loader có thể có unnamed module tương ứng.

Khi cấu hình ứng dụng, cần hiểu thư viện đang nằm trên classpath hay module path. Chỉ đổi tham số đường dẫn không tự động giải quyết mọi khác biệt về truy cập package, phụ thuộc hoặc cách đóng gói.

## 6. Các công cụ JDK thường gặp

| Công cụ | Vai trò chính | Thuật ngữ gắn liền |
|---|---|---|
| javac | Biên dịch mã nguồn .java thành class file | Compiler, bytecode, classpath, module path |
| java | Khởi chạy lớp, JAR, module hoặc chế độ chạy mã nguồn | Launcher, JVM, runtime |
| jshell | Chạy biểu thức và đoạn mã Java tương tác | REPL, snippet |
| jar | Tạo, liệt kê và thao tác với tệp JAR | Archive, manifest |
| javadoc | Sinh tài liệu API từ comment và khai báo mã nguồn | API documentation |
| javap | Hiển thị thông tin lớp, chữ ký và bytecode | Class file inspection |
| jdeps | Phân tích phụ thuộc ở cấp package, lớp hoặc module | Dependency analysis |
| jmod | Tạo và kiểm tra tệp JMOD | JDK module archive |
| jlink | Ghép các module cần thiết thành runtime image tùy biến | Runtime image |
| jpackage | Đóng gói ứng dụng thành gói cài đặt theo nền tảng | Application packaging |
| keytool | Quản lý keystore và chứng thư | Keystore, certificate |
| jarsigner | Ký và xác minh chữ ký trên JAR | Digital signature |
| jcmd | Gửi lệnh chẩn đoán đến JVM đang chạy | Diagnostic command |
| jstack | Lấy thread dump | Thread, stack trace |
| jmap | Lấy thông tin heap hoặc heap dump theo tùy chọn hỗ trợ | Heap, memory analysis |
| jstat | Theo dõi một số thống kê JVM | GC, runtime statistics |
| jinfo | Xem hoặc hỗ trợ kiểm tra cấu hình JVM theo khả năng của phiên bản | VM flags, system properties |
| jps | Liệt kê các tiến trình Java mà công cụ có thể quan sát | Process discovery |
| jfr | Làm việc với bản ghi Java Flight Recorder | Event recording, profiling |
| jhsdb | Công cụ Serviceability Agent để kiểm tra tiến trình/core dump trong tình huống phù hợp | JVM diagnostics |

Không phải công cụ nào cũng được cài trong mọi runtime image. Các công cụ phát triển và chẩn đoán thường có trong JDK đầy đủ; runtime image tối giản tạo bằng jlink có thể chỉ chứa các module runtime được chọn. Một số thao tác chẩn đoán còn phụ thuộc quyền truy cập tiến trình, cấu hình JVM, hệ điều hành và khả năng của bản JDK đang dùng.

### Một số thuật ngữ gắn với công cụ

- **Compiler (trình biên dịch):** chuyển mã nguồn thành dạng đầu ra khác. Trong luồng Java thông thường, javac chuyển .java thành .class.
- **Launcher (trình khởi chạy):** phân tích lệnh chạy, xác định lớp/JAR/module hoặc nguồn cần chạy và khởi động môi trường thực thi. java là launcher của JDK.
- **REPL:** viết tắt của Read-Eval-Print Loop, môi trường nhập một đoạn mã, đánh giá nó, in kết quả và tiếp tục nhận đầu vào. jshell là REPL cho Java.
- **Manifest:** metadata nằm trong thư mục META-INF của JAR. Thuộc tính Main-Class có thể chỉ định lớp bắt đầu cho JAR chạy bằng java -jar.
- **Thread dump:** ảnh chụp trạng thái các luồng tại một thời điểm, thường gồm stack trace và trạng thái luồng. Nó hữu ích khi điều tra deadlock hoặc ứng dụng bị treo.
- **Heap dump:** dữ liệu mô tả heap tại một thời điểm, thường dùng để phân tích đối tượng và mức sử dụng bộ nhớ. Đây có thể là tệp lớn và chứa dữ liệu nhạy cảm của ứng dụng.
- **JFR (Java Flight Recorder):** cơ chế ghi sự kiện có chi phí tương đối thấp trong nhiều tình huống, hỗ trợ phân tích hoạt động JVM và ứng dụng.
- **Runtime image:** cấu trúc runtime có thể chạy được, gồm các module và thành phần cần thiết. Runtime image do jlink tạo có thể nhỏ hơn một JDK đầy đủ.
- **JAR (Java ARchive):** định dạng archive dựa trên ZIP, dùng để gom class file, tài nguyên và metadata. JAR không phải bản thân ngôn ngữ Java và cũng không nhất thiết là tệp thực thi độc lập.

## 7. Tùy chọn dòng lệnh quan trọng

### --release, -source và -target

Khi biên dịch, cần phân biệt ba khái niệm:

- **--release N** yêu cầu compiler biên dịch theo phiên bản nền tảng Java mục tiêu N, bao gồm mức ngôn ngữ, phiên bản class file và tập API Java SE được phép sử dụng cho bản phát hành đó.
- **-source N** chọn mức cú pháp/ngôn ngữ nguồn được chấp nhận.
- **-target N** chọn phiên bản class file được tạo.

Với dự án cần nhắm đến một bản Java cụ thể, --release thường là lựa chọn rõ ràng hơn vì nó phối hợp các ràng buộc quan trọng. Chỉ đặt -source và -target không tự bảo đảm rằng mã không gọi API chỉ có ở JDK mới hơn.

Ví dụ, biên dịch mã nguồn theo API và bytecode của Java 17 bằng JDK mới hơn:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Lệnh giả định tệp nguồn tồn tại ở đường dẫn đã nêu. Tùy chọn -d out chỉ định thư mục nhận class file; thư mục package sẽ được tạo bên dưới out khi cần.

### -cp / --class-path và --module-path

- **-cp** hoặc **--class-path** cấu hình nơi tìm lớp theo cơ chế classpath.
- **--module-path** cấu hình nơi tìm module.
- **--add-modules** có thể yêu cầu đưa thêm module vào đồ thị module của ứng dụng trong các tình huống phù hợp.

Không nên thay classpath bằng module path một cách máy móc. Cách tổ chức thư viện và quy tắc truy cập của ứng dụng quyết định đường dẫn nào phù hợp.

### -D, -X và -XX

- **-Dname=value** đặt một system property cho JVM. Ứng dụng đọc giá trị bằng System.getProperty("name").
- **-X...** thường dùng cho tùy chọn nâng cao của JVM, ví dụ cấu hình kích thước heap.
- **-XX:...** thường dùng cho cờ cấu hình chuyên sâu của một JVM cụ thể.

Các tùy chọn -X và -XX có thể khác nhau giữa các triển khai hoặc phiên bản JVM. Cần kiểm tra tài liệu của JDK đang chạy thay vì giả định mọi cờ đều được hỗ trợ giống nhau.

### Preview feature

Khi sử dụng một preview feature của phiên bản Java tương ứng, cần bật preview ở cả bước biên dịch và bước chạy. Ví dụ minh họa cho JDK 21:

~~~bash
javac --release 21 --enable-preview -d out src/com/example/Main.java
java --enable-preview -cp out com.example.Main
~~~

Ví dụ này chỉ phù hợp khi mã nguồn thực sự dùng preview feature của phiên bản 21 và đang chạy trên JDK có hỗ trợ tương ứng. Không nên bật --enable-preview như một tùy chọn mặc định cho mọi dự án.

## 8. Ví dụ một vòng đời công cụ tối giản

Giả sử có lớp Main trong package com.example:

~~~java
// File: src/com/example/Main.java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, JDK tooling!");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Chạy class file vừa tạo:

~~~bash
java -cp out com.example.Main
~~~

Kết quả:

~~~text
Hello, JDK tooling!
~~~

Có thể xem chữ ký và bytecode của lớp bằng:

~~~bash
javap -classpath out -c com.example.Main
~~~

Trong ví dụ này:

- src là thư mục mã nguồn.
- out là thư mục đầu ra của compiler.
- Main.java là source file.
- Main.class là class file chứa bytecode.
- javac là compiler.
- java là launcher khởi chạy JVM.
- -cp out đưa thư mục out vào classpath.
- javap dùng để kiểm tra class file.

Các lệnh giả định đang chạy từ thư mục gốc của dự án và JDK đã được cấu hình trong môi trường lệnh. Nếu hệ thống có nhiều JDK, cần kiểm tra java --version, javac --version và đường dẫn thực tế của hai lệnh.

## 9. Build tool, IDE và JDK Tooling

**JDK Tooling** là các công cụ được cung cấp cùng JDK. **Build tool** như Maven hoặc Gradle là phần mềm riêng, dùng để điều phối các bước build như tải thư viện, biên dịch, chạy test, đóng gói và quản lý tác vụ. Build tool thường gọi compiler hoặc launcher của một JDK đã được cấu hình.

**IDE** như IntelliJ IDEA, Eclipse hoặc VS Code cung cấp môi trường viết mã, điều hướng, debug và tích hợp build. IDE có thể sử dụng một JDK riêng được cấu hình trong dự án, trong khi terminal lại gọi một JDK khác qua PATH.

Vì vậy, khi gặp lỗi kiểu “chạy được trong IDE nhưng không chạy được trên terminal”, cần so sánh JDK mà IDE, build tool và terminal đang sử dụng, cùng với phiên bản mục tiêu và classpath/module path của từng môi trường.

**Toolchain** là tập hợp phiên bản và công cụ được chọn để thực hiện một quy trình build hoặc chạy. Một toolchain Java thường bao gồm JDK cụ thể, build tool, cấu hình compiler, thư viện phụ thuộc và nền tảng đích. Khóa phiên bản toolchain giúp kết quả build nhất quán hơn giữa máy lập trình viên và CI.

## 10. Những nhầm lẫn thường gặp

1. **Đồng nhất JDK, JRE và JVM.** JDK là bộ công cụ phát triển; JRE mô tả môi trường chạy; JVM là máy ảo thực thi bytecode.
2. **Cho rằng javac chạy chương trình.** javac biên dịch; java khởi chạy chương trình trên JVM.
3. **Cho rằng bytecode là mã máy.** Bytecode là định dạng trung gian cho JVM; JVM có thể thông dịch hoặc biên dịch JIT thành mã máy.
4. **Cho rằng JAR luôn là ứng dụng chạy độc lập.** JAR chỉ là archive. Muốn chạy bằng java -jar, JAR cần có cấu hình điểm vào phù hợp, thường là thuộc tính Main-Class trong manifest, và vẫn có thể cần thư viện phụ thuộc.
5. **Cho rằng JAVA_HOME quyết định lệnh java.** PATH quyết định executable nào được tìm thấy khi gọi lệnh; hai cấu hình cần được kiểm tra riêng.
6. **Đánh đồng classpath với module path.** Classpath và module path tuân theo các quy tắc tìm kiếm và truy cập khác nhau.
7. **Cho rằng -source và -target bảo đảm tương thích API.** Hai tùy chọn này không giới hạn đầy đủ API nền tảng như --release.
8. **Cho rằng mọi JDK distribution giống nhau về hỗ trợ.** Cần kiểm tra nhà cung cấp, nền tảng, giấy phép, lịch cập nhật và chính sách hỗ trợ.
9. **Cho rằng runtime image có mọi công cụ như JDK đầy đủ.** Runtime image tối giản chỉ chứa những module được đưa vào khi tạo.
10. **Cho rằng IDE và terminal luôn dùng cùng JDK.** Mỗi môi trường có thể có cấu hình JDK và biến môi trường riêng.

## 11. Checklist khi đọc hoặc chạy lệnh JDK

- Xác định JDK nào đang được sử dụng bằng java --version và javac --version.
- Kiểm tra JAVA_HOME và đường dẫn thực tế được tìm thấy qua PATH.
- Xác định mã nguồn được biên dịch thành class file ở thư mục nào.
- Xác định ứng dụng dùng classpath hay module path.
- Xác định phiên bản Java mục tiêu; ưu tiên --release khi cần giới hạn API theo một bản phát hành.
- Phân biệt tùy chọn của compiler (javac), launcher (java) và JVM.
- Khi chẩn đoán sự cố, chọn công cụ phù hợp: jstack cho thread dump, jmap cho heap, jcmd cho lệnh chẩn đoán tổng quát, jfr cho bản ghi sự kiện.
- Ghi rõ phiên bản JDK và toolchain trong hướng dẫn build để người khác có thể tái tạo môi trường.

## 12. Tóm tắt cần nhớ

| Thuật ngữ | Ý nghĩa ngắn gọn |
|---|---|
| JDK | Bộ công cụ phát triển Java |
| JRE | Môi trường cần thiết để chạy ứng dụng Java |
| JVM | Máy ảo nạp và thực thi bytecode |
| javac | Trình biên dịch Java |
| java | Trình khởi chạy ứng dụng Java |
| Bytecode | Mã trung gian trong class file, dành cho JVM |
| Classpath | Đường dẫn tìm lớp và tài nguyên theo cơ chế classpath |
| Module path | Đường dẫn tìm module theo JPMS |
| JAR | Archive chứa class file, tài nguyên và metadata |
| JAVA_HOME | Biến thường trỏ đến thư mục gốc JDK |
| PATH | Danh sách thư mục dùng để tìm executable |
| --release | Chọn phiên bản nền tảng Java mục tiêu khi biên dịch |
| Runtime image | Môi trường chạy được tạo từ các module runtime cần thiết |
| Toolchain | Tập hợp công cụ và phiên bản dùng trong quy trình build |

Khi đọc một lệnh JDK, hãy xác định ba điều: **công cụ nào đang chạy, đầu vào/đầu ra là gì, và cấu hình nào quyết định môi trường Java được dùng**. Ba câu hỏi này giúp định vị phần lớn vấn đề trong quá trình biên dịch, chạy và chẩn đoán ứng dụng Java.