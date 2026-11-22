# Khắc phục lỗi sai classpath trong Java

## 1. Classpath là gì?

Classpath là danh sách vị trí mà Java dùng để tìm class và resource khi biên dịch hoặc chạy ứng dụng. Mỗi mục có thể là:

- Thư mục gốc chứa các file .class theo cấu trúc package.
- Một JAR hoặc ZIP chứa class và resource.
- Nhiều thư mục/JAR kết hợp theo thứ tự.

Ví dụ project:

~~~text
project/
├── src/
│   └── com/example/Main.java
├── build/
│   └── classes/
│       └── com/example/Main.class
└── lib/
    └── helper.jar
~~~

Nếu class có tên đầy đủ là com.example.Main, classpath phải trỏ tới thư mục build/classes, tức thư mục nằm ngay phía trên package com. Không trỏ tới build/classes/com/example.

Classpath không phải là đường dẫn tới một file class cụ thể. Nó là các root locations từ đó JVM có thể tìm package, class và resource.

## 2. Phân biệt compile-time classpath và runtime classpath

Hai thời điểm cần classpath khác nhau:

- **Compile time:** javac cần tìm class mà source đang import hoặc tham chiếu.
- **Runtime:** JVM cần tìm class được nạp trong lúc chương trình chạy, bao gồm dependency được gọi trực tiếp, dependency bắc cầu, reflection hoặc plugin.

Ví dụ, Main.java import com.example.lib.Helper. Nếu Helper nằm trong helper.jar, compiler phải nhìn thấy JAR đó khi compile. Khi chạy, JVM cũng phải tìm được Helper trong runtime classpath.

Compile thành công không chứng minh runtime classpath đã đầy đủ. Đây là lý do ứng dụng có thể biên dịch bình thường nhưng khi chạy lại báo NoClassDefFoundError.

## 3. Hiểu đúng cấu trúc package và classpath root

Giả sử file được tạo ra ở:

~~~text
build/classes/com/example/Main.class
~~~

Tên class là com.example.Main và classpath root là:

~~~text
build/classes
~~~

Lệnh đúng:

~~~bash
java -cp build/classes com.example.Main
~~~

Lệnh sai:

~~~bash
java -cp build/classes/com/example com.example.Main
~~~

Lệnh sai làm JVM tìm class tại:

~~~text
build/classes/com/example/com/example/Main.class
~~~

Đường dẫn package bị lặp nên JVM không tìm thấy class.

Quy tắc chung: bỏ phần package khỏi đường dẫn class file để xác định classpath root. Với com.example.service.UserService, root phải chứa thư mục com/example/service.

## 4. Compile và chạy một chương trình nhỏ

Tạo file src/com/example/Main.java:

~~~java
package com.example;

public final class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "local" : args[0];
        System.out.println("Classpath is correct");
        System.out.println("target=" + target);
    }
}
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/com/example/Main.java
~~~

Chạy:

~~~bash
java -cp build/classes com.example.Main test
~~~

Stdout chính xác:

~~~text
Classpath is correct
target=test
~~~

Option -d chỉ định thư mục đích cho class file. Vì source khai báo package com.example, javac tạo file trong build/classes/com/example/Main.class.

Có thể dùng đường dẫn classpath tương đối khi đang đứng tại project root. Nếu chạy từ thư mục khác, phải điều chỉnh đường dẫn hoặc dùng absolute path.

## 5. Cú pháp -cp và --class-path

Hai dạng sau tương đương:

~~~bash
java -cp build/classes com.example.Main
java --class-path build/classes com.example.Main
~~~

Với javac:

~~~bash
javac -cp lib/helper.jar -d build/classes src/com/example/Main.java
javac --class-path lib/helper.jar -d build/classes src/com/example/Main.java
~~~

Classpath là giá trị của một option. Khi cần nhiều entry, nối chúng bằng dấu phân cách của hệ điều hành.

Ví dụ:

~~~bash
java -cp "build/classes:lib/helper.jar" com.example.Main
~~~

Đây là cú pháp Linux/macOS. Trên Windows, dấu phân cách là dấu chấm phẩy:

~~~powershell
java -cp "build\classes;lib\helper.jar" com.example.Main
~~~

Đặt toàn bộ classpath trong dấu nháy để shell không tách các thành phần có khoảng trắng hoặc ký tự đặc biệt.

## 6. Dấu phân cách classpath theo hệ điều hành

Đây là lỗi phổ biến khi chuyển script giữa Windows và Linux/macOS.

| Hệ điều hành | Dấu phân cách | Ví dụ |
|---|---|---|
| Windows | ; | classes;lib/a.jar;lib/b.jar |
| Linux | : | classes:lib/a.jar:lib/b.jar |
| macOS | : | classes:lib/a.jar:lib/b.jar |

Windows:

~~~powershell
java -cp "build\classes;lib\helper.jar;lib\logging.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/helper.jar:lib/logging.jar" com.example.Main
~~~

Không dùng dấu : để phân tách classpath trên Windows. Dấu : vốn xuất hiện trong ký tự ổ đĩa như C:, nên không phải separator của Windows classpath.

Khi tạo script đa nền tảng, nên để Maven/Gradle quản lý runtime classpath hoặc dùng API/tool sinh classpath thay vì ghép chuỗi bằng một dấu phân cách cố định.

## 7. Đường dẫn tương đối và working directory

Classpath tương đối được giải quyết từ working directory của process, không tự động tính từ thư mục chứa source file, class file hoặc JAR.

Kiểm tra working directory:

~~~powershell
Get-Location
~~~

Linux/macOS:

~~~bash
pwd
~~~

Trong Java:

~~~java
System.out.println(System.getProperty("user.dir"));
~~~

Ví dụ, nếu working directory là project root, classpath build/classes có thể hoạt động. Nếu chạy cùng lệnh từ thư mục scripts, JVM sẽ tìm scripts/build/classes và báo lỗi.

Cách sửa:

- Chạy lệnh từ thư mục đã xác định.
- Dùng classpath tương đối tính từ working directory hiện tại.
- Hoặc dùng absolute path.
- Trong IDE/CI, đặt working directory rõ ràng.

Đừng nhầm working directory với thư mục chứa JAR. Hai thư mục có thể khác nhau.

## 8. Xử lý đường dẫn có khoảng trắng

Nếu project nằm ở đường dẫn như:

~~~text
C:\Users\Developer\Java Projects\demo\
~~~

Classpath phải được quote đúng.

PowerShell:

~~~powershell
java -cp "C:\Users\Developer\Java Projects\demo\build\classes;C:\Users\Developer\Java Projects\demo\lib\helper.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "/home/developer/Java Projects/demo/build/classes:/home/developer/Java Projects/demo/lib/helper.jar" com.example.Main
~~~

Không đặt dấu nháy riêng quanh từng phần rồi để shell tách cả biểu thức. Quote toàn bộ giá trị classpath giúp shell truyền nó như một argument.

Nếu script ghép đường dẫn động, dùng cơ chế join path của shell hoặc build tool. Tránh tự nối slash và dấu phân cách trên mọi hệ điều hành.

## 9. Thêm nhiều JAR vào classpath

Khi ứng dụng cần nhiều dependency, có thể liệt kê tất cả JAR:

Windows:

~~~powershell
java -cp "build\classes;lib\helper.jar;lib\logging.jar;lib\json.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/helper.jar:lib/logging.jar:lib/json.jar" com.example.Main
~~~

Classpath có thể kết hợp thư mục class với JAR. Thứ tự entry có ý nghĩa: khi có nhiều class cùng tên, class loader có thể nạp bản đầu tiên tìm thấy theo thứ tự classpath.

Không nên để hai phiên bản khác nhau của cùng một library cùng xuất hiện trên classpath. Điều này có thể gây lỗi khó hiểu như NoSuchMethodError, AbstractMethodError hoặc hành vi phụ thuộc thứ tự.

## 10. Dùng wildcard cho thư mục lib

Java launcher hỗ trợ wildcard cho các JAR trực tiếp trong một thư mục.

Windows:

~~~powershell
java -cp "build\classes;lib\*" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/*" com.example.Main
~~~

Wildcard lib/* không tìm đệ quy trong các thư mục con. Ví dụ lib/plugins/a.jar không tự động được đưa vào classpath nếu chỉ có lib/*.

Không dựa vào thứ tự các JAR được mở rộng bởi wildcard để giải quyết class trùng tên. Nếu thứ tự quan trọng, liệt kê dependency rõ ràng hoặc để build tool tạo runtime classpath có kiểm soát.

Wildcard của Java launcher khác wildcard do shell mở rộng. Đặt classpath trong dấu nháy giúp Java launcher xử lý phần wildcard của JAR directory.

## 11. Lỗi Could not find or load main class

Thông báo thường gặp:

~~~text
Error: Could not find or load main class com.example.Main
Caused by: java.lang.ClassNotFoundException: com.example.Main
~~~

Lỗi này thường có nghĩa JVM không tìm thấy main class được yêu cầu. Kiểm tra:

1. Class đã được compile chưa?
2. Classpath root có đúng không?
3. Package và tên class có đúng chữ hoa/chữ thường không?
4. Working directory có đúng không?
5. Đã truyền classpath bằng -cp/--class-path chưa?
6. Có vô tình dùng dấu phân cách của OS khác không?

Kiểm tra file:

~~~powershell
Test-Path .\build\classes\com\example\Main.class
~~~

Linux/macOS:

~~~bash
test -f build/classes/com/example/Main.class && echo "class exists"
~~~

Nếu file tồn tại nhưng vẫn không tìm thấy, kiểm tra classpath có trỏ tới build/classes hay không. Đừng truyền build/classes/com/example khi tên class là com.example.Main.

## 12. Phân biệt ClassNotFoundException và NoClassDefFoundError

Hai lỗi này có liên quan nhưng thường xuất hiện ở những tình huống khác nhau.

| Lỗi | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| ClassNotFoundException | Một API nạp class theo tên không tìm thấy class. | Class.forName("com.example.Plugin"). |
| NoClassDefFoundError | JVM cần một class khi liên kết hoặc thực thi nhưng không tìm thấy định nghĩa cần thiết. | Main gọi Helper nhưng helper.jar thiếu khi chạy. |

Ví dụ thiếu runtime dependency:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: com/example/lib/Helper
Caused by: java.lang.ClassNotFoundException: com.example.lib.Helper
~~~

Nếu javac đã dùng helper.jar nhưng java không dùng JAR đó, compile thành công nhưng runtime thất bại.

Cách xử lý là thêm dependency vào runtime classpath hoặc dùng cách đóng gói/phân phối phù hợp. Kiểm tra cả dependency bắc cầu, không chỉ thư viện mà source import trực tiếp.

## 13. Compile-time dependency không tự động trở thành runtime dependency

Ví dụ Main.java tham chiếu Helper.java. Compile:

~~~bash
javac -cp lib/helper.jar -d build/classes src/com/example/Main.java
~~~

Lệnh trên chỉ giúp compiler tìm Helper. Nó không tự copy helper.jar vào build/classes và cũng không tự thêm helper.jar vào lệnh chạy.

Khi chạy bằng classpath, phải cung cấp cả hai:

Windows:

~~~powershell
java -cp "build\classes;lib\helper.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/helper.jar" com.example.Main
~~~

Với Maven, dependency scope phải phù hợp với việc sử dụng lúc runtime. Với Gradle, kiểm tra runtimeClasspath và các configuration như implementation, runtimeOnly. Không dùng compileOnly cho thư viện mà ứng dụng thực sự cần lúc chạy.

## 14. Hiểu khác biệt giữa -cp và -jar

Đây là một trong những nguyên nhân phổ biến gây lỗi classpath.

Khi chạy:

~~~bash
java -cp "app.jar:lib/helper.jar" com.example.Main
~~~

JVM sử dụng classpath được truyền qua -cp.

Nhưng khi chạy:

~~~bash
java -cp "lib/helper.jar" -jar app.jar
~~~

Classpath từ -cp bị bỏ qua. Với -jar, Java lấy entry point từ Main-Class trong manifest và dùng manifest Class-Path để tìm dependency bổ sung.

Vì vậy, không thể thêm dependency cho executable JAR bằng cách đặt -cp trước -jar. Chọn một trong hai cách:

- Chạy main class trực tiếp bằng -cp.
- Dùng -jar và khai báo dependency trong manifest Class-Path hoặc đóng gói dependency vào artifact phù hợp.

## 15. Khai báo dependency trong manifest Class-Path

Một executable JAR có thể tham chiếu dependency nằm cạnh nó.

Cấu trúc:

~~~text
dist/
├── app.jar
└── lib/
    └── helper.jar
~~~

Manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/helper.jar
~~~

Chạy:

~~~bash
java -jar dist/app.jar
~~~

Các path trong manifest Class-Path là URL tương đối với vị trí của JAR chứa manifest. Dùng dấu slash / trong manifest kể cả khi chạy trên Windows.

Manifest chỉ tham chiếu tới dependency, không copy thư viện vào app.jar. Đảm bảo file lib/helper.jar tồn tại tương đối với app.jar và có thể đọc được.

Nếu dependency nằm ở vị trí khác, cập nhật manifest hoặc phân phối lại thư mục ứng dụng đúng cấu trúc. Khi cần một artifact duy nhất, cân nhắc shaded/fat JAR và kiểm tra việc gộp service descriptor, resource và chữ ký.

## 16. Classpath và module path không giống nhau

Classpath phục vụ classpath/unnamed module. Ứng dụng dùng Java Platform Module System có thể cần module path.

Ví dụ module path:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

Có thể viết ngắn option --module thành -m:

~~~bash
java --module-path mods -m com.example.app/com.example.Main
~~~

Nếu đặt named module chỉ trên classpath, module descriptor không được dùng như khi chạy trên module path. Ngược lại, dependency module cần được resolve theo module graph.

Kiểm tra module:

~~~bash
jar --describe-module --file lib/helper.jar
java --list-modules
~~~

Nếu gặp FindException hoặc ModuleNotFoundException, kiểm tra module path, tên module, module descriptor và dependency module. Không giải quyết lỗi module bằng cách thêm ngẫu nhiên JAR vào classpath nếu ứng dụng được thiết kế theo module system.

## 17. Classpath mặc định và biến CLASSPATH

Nếu không truyền -cp hoặc --class-path, Java launcher có thể dùng giá trị CLASSPATH của environment hoặc classpath mặc định.

Kiểm tra trên Windows PowerShell:

~~~powershell
$env:CLASSPATH
~~~

Linux/macOS:

~~~bash
echo "$CLASSPATH"
~~~

Biến CLASSPATH toàn cục dễ làm một project chạy được trên máy developer nhưng thất bại trên CI hoặc máy khác. Nó cũng có thể đưa phiên bản dependency cũ vào ứng dụng mà không ai nhận ra.

Trong script, IDE Run Configuration và CI, nên chỉ định classpath rõ ràng hoặc để Maven/Gradle quản lý. Một classpath tường minh qua -cp thay thế giá trị user classpath mặc định cho lần chạy đó.

Không đặt tất cả dependency của mọi project vào CLASSPATH hệ thống.

## 18. Classpath order và class bị trùng

Nếu hai JAR cùng chứa com.example.util.Version, kết quả có thể phụ thuộc thứ tự classpath. JVM thường nạp class đầu tiên được tìm thấy trong quá trình tìm kiếm.

Ví dụ:

~~~bash
java -cp "lib/old.jar:lib/new.jar:app.jar" com.example.Main
~~~

Linux/macOS ở ví dụ trên. Windows dùng dấu chấm phẩy.

Nếu old.jar và new.jar cùng định nghĩa một class, bản xuất hiện trước có thể được nạp. Đây là nguồn gây lỗi binary incompatibility.

Cách xử lý:

- Loại dependency version cũ.
- Dùng dependency management/BOM để thống nhất version.
- Chạy dependency tree/report của Maven hoặc Gradle.
- Kiểm tra classpath thực tế của process.
- Tránh tự copy nhiều phiên bản JAR vào lib.

Nếu gặp NoSuchMethodError dù class đã được tìm thấy, hãy kiểm tra phiên bản class thực sự được nạp, không chỉ kiểm tra file JAR có tồn tại.

## 19. Classpath cho resource

Classpath không chỉ chứa .class mà còn chứa resource như properties, XML, template và file cấu hình được đóng gói.

Ví dụ:

~~~java
var stream = Main.class.getResourceAsStream("/config/app.properties");
~~~

Nếu resource nằm trong classpath tại config/app.properties, có thể đọc bằng class resource API. Đường dẫn bắt đầu bằng / được hiểu từ root classpath.

Phân biệt resource đóng gói trong JAR với file bên ngoài. File config ngoài JAR thường được giải quyết theo working directory hoặc absolute path, không tự động nằm trên classpath.

Kiểm tra resource trong archive:

~~~bash
jar --list --file app.jar
~~~

Nếu class tìm thấy nhưng resource trả về null, kiểm tra resource có được copy vào output directory/JAR và đường dẫn có đúng chữ hoa/chữ thường không.

## 20. Chẩn đoán classpath bằng công cụ JDK

Có thể dùng các công cụ sau để quan sát và kiểm tra:

Liệt kê nội dung JAR:

~~~bash
jar --list --file lib/helper.jar
~~~

Xem classpath mà launcher nhận:

~~~bash
java -XshowSettings:properties -version
~~~

Tìm class được nạp và nguồn của nó:

~~~bash
java -verbose:class -cp "build/classes:lib/*" com.example.Main
~~~

JDK mới cũng hỗ trợ logging class loading:

~~~bash
java -Xlog:class+load=info -cp "build/classes:lib/*" com.example.Main
~~~

Phân tích dependency:

~~~bash
jdeps --multi-release 17 --class-path "lib/*" app.jar
~~~

Kiểm tra bytecode/class name:

~~~bash
javap -classpath app.jar -verbose com.example.Main
~~~

Trên Windows, thay dấu : trong classpath bằng ;. Output verbose có thể rất dài; lọc theo tên package/class cần điều tra và tránh gửi log chứa thông tin nhạy cảm.

## 21. Maven và Gradle quản lý classpath như thế nào?

Trong project Maven, khai báo dependency trong pom.xml thay vì tự ghép classpath cho từng lần chạy. Maven phân biệt compile/runtime/test scopes. Dependency chỉ có scope compileOnly hoặc provided có thể không nằm trong runtime của ứng dụng theo cách bạn mong đợi.

Kiểm tra dependency tree:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency helper --configuration runtimeClasspath
~~~

Nếu dùng Gradle Application Plugin, task run sử dụng runtime classpath do plugin quản lý. Với executable JAR, vẫn cần đảm bảo dependency được phân phối qua manifest, application distribution hoặc fat JAR.

Không lấy classpath compile làm mặc định cho runtime. Hãy kiểm tra configuration/task thực sự được dùng khi ứng dụng chạy.

## 22. Cấu hình IDE Run Configuration

IDE thường tạo classpath riêng từ module/project configuration. Nếu chạy từ terminal thành công nhưng IDE thất bại, kiểm tra:

- Main class đầy đủ.
- Module hoặc project được chọn.
- Dependencies đã được import/resolved.
- Project SDK và language level.
- Run Configuration có dùng đúng module classpath.
- Working directory.
- Test/runtime scope của dependency.
- Generated sources và resource directories.

Trong IntelliJ IDEA, kiểm tra Run/Debug Configuration và module classpath. Trong Eclipse, kiểm tra Java Build Path và launch configuration. Trong VS Code, kiểm tra project import và Java runtime/classpath do extension quản lý.

Nếu IDE dùng output cũ, clean/rebuild project rồi chạy lại. Không sửa classpath thủ công bằng một danh sách JAR dài nếu build tool đã có thể quản lý dependency.

## 23. Quy trình chẩn đoán từng bước

Khi gặp lỗi classpath, đi theo thứ tự:

1. Ghi lại nguyên văn lệnh java hoặc javac đã chạy.
2. Xác nhận Java executable và version bằng java --version.
3. Xác định working directory.
4. Xác định entry point: class, JAR, source file hay module.
5. Tìm file .class hoặc JAR chứa class cần chạy.
6. Xác định classpath root dựa trên package.
7. Kiểm tra separator theo OS.
8. Kiểm tra quote của path có khoảng trắng.
9. Kiểm tra dependency runtime, không chỉ compile-time.
10. Nếu dùng -jar, kiểm tra Main-Class và manifest Class-Path.
11. Nếu dùng module path, kiểm tra module descriptor và module graph.
12. Dùng -verbose:class hoặc jdeps để xem class/dependency thực tế.
13. So sánh lệnh chạy ở terminal, IDE và CI.

Đừng thay đổi nhiều biến cùng lúc. Thay một yếu tố, chạy lại cùng lệnh và so sánh thông báo lỗi để xác định nguyên nhân.

## 24. Lab: tái hiện và sửa lỗi sai classpath

Tạo hai source file.

Main.java:

~~~java
package com.example;

import com.example.lib.Helper;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Classpath demo started");
        System.out.println(Helper.message());
        System.out.println("argument.count=" + args.length);
    }
}
~~~

Helper.java:

~~~java
package com.example.lib;

public final class Helper {
    public static String message() {
        return "helper loaded";
    }
}
~~~

Compile Helper:

~~~bash
javac --release 17 -d helper-classes src/com/example/lib/Helper.java
jar --create --file lib/helper.jar -C helper-classes .
~~~

Compile Main dựa trên Helper:

~~~bash
javac --release 17 -cp helper-classes -d app-classes src/com/example/Main.java
~~~

Chạy đúng classpath trên Windows:

~~~powershell
java -cp "app-classes;dist\lib\helper.jar" com.example.Main first "two words"
~~~

Linux/macOS:

~~~bash
java -cp "app-classes:dist/lib/helper.jar" com.example.Main first "two words"
~~~

Output:

~~~text
Classpath demo started
helper loaded
argument.count=2
~~~

Nếu bỏ helper.jar khỏi runtime classpath, chương trình compile thành công nhưng chạy sẽ báo NoClassDefFoundError. Nếu classpath trỏ nhầm vào app-classes/com/example thay vì app-classes, JVM không tìm thấy com.example.Main.

## 25. Kết quả lab đã kiểm chứng

Fixture được biên dịch bằng Java 17 target và chạy trên Windows 11 với Azul Zulu JDK 24.0.2; cùng classpath hợp lệ cũng chạy trên Amazon Corretto 17.0.15.

| Tình huống | Kết quả thực tế |
|---|---|
| Explicit classpath gồm app-classes và helper.jar | PASS |
| Wildcard lib/* | PASS |
| Classpath root đặt sai | Could not find or load main class; exit code 1 |
| Thiếu helper.jar lúc runtime | NoClassDefFoundError; exit code 1 |
| Truyền -cp cùng -jar để thêm helper.jar | Vẫn NoClassDefFoundError; -cp bị bỏ qua |
| Manifest Class-Path trỏ lib/helper.jar | PASS |
| Chạy classpath từ thư mục có khoảng trắng | PASS |
| Cùng classpath trên Corretto 17.0.15 | PASS |

Thông báo khi đặt sai classpath root:

~~~text
Error: Could not find or load main class com.example.Main
Caused by: java.lang.ClassNotFoundException: com.example.Main
~~~

Thông báo khi thiếu dependency:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: com/example/lib/Helper
Caused by: java.lang.ClassNotFoundException: com.example.lib.Helper
~~~

Các kết quả này cho thấy lỗi main class và lỗi dependency runtime là hai vấn đề khác nhau, cần sửa đúng vị trí.

## 26. Checklist trước khi bàn giao ứng dụng

- [ ] Main class/package được xác định chính xác.
- [ ] Classpath root trỏ tới đúng thư mục chứa package tree.
- [ ] Tất cả dependency runtime đã được cung cấp.
- [ ] Separator đúng với Windows hoặc Linux/macOS.
- [ ] Path có khoảng trắng được quote.
- [ ] Working directory được xác định rõ.
- [ ] Không phụ thuộc CLASSPATH toàn cục.
- [ ] Wildcard không được dùng khi cần kiểm soát thứ tự JAR.
- [ ] Không có nhiều version trùng lặp của cùng library.
- [ ] Không dùng -cp với -jar để bổ sung dependency.
- [ ] Manifest Class-Path đúng nếu chạy bằng java -jar.
- [ ] Module path được cấu hình nếu ứng dụng modular.
- [ ] Smoke test chạy từ thư mục sạch và runtime tối thiểu được hỗ trợ.
- [ ] CI sử dụng cùng dependency graph và launch command đã kiểm thử.

## 27. Tài liệu tham khảo

- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [The jar Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [JAR File Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html)
- [ClassLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html)
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)

Classpath sai có thể khiến JVM không tìm thấy main class, thiếu dependency hoặc nạp nhầm phiên bản class. Hãy xác định đúng package root, working directory, OS separator và runtime dependencies; sau đó kiểm tra lệnh chạy thực tế thay vì chỉ nhìn cấu hình compile.