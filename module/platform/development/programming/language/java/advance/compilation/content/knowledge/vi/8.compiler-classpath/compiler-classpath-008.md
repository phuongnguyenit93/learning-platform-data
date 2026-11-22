# Chẩn đoán `cannot find symbol` và `package ... does not exist` do cấu hình classpath

## 1. Hai lỗi trông giống lỗi mã nguồn nhưng có thể bắt nguồn từ cấu hình

Trong Java, `javac` phải tìm thấy định nghĩa của các kiểu mà chương trình sử dụng để thực hiện **symbol resolution** và kiểm tra kiểu. Khi class, package hoặc dependency không nằm trong tập nguồn và đường dẫn compiler đang tra cứu, một tệp `.java` viết đúng cú pháp vẫn có thể báo:

~~~text
error: package com.example.lib does not exist
error: cannot find symbol
~~~

Đây là **lỗi biên dịch**. Chúng khác với `ClassNotFoundException` và `NoClassDefFoundError` thường gặp khi chương trình **đã biên dịch** nhưng JVM không nạp được class cần thiết lúc chạy.

**Nguyên tắc:** hãy xác định `javac` đang biên dịch những source nào, nhận những thư mục/JAR nào trên **compile classpath**, và tên package/class trong các artifact đó là gì. Không nên vội đổi `import` hoặc đổi tên lớp trước khi xác minh các điều kiện này.

| Chẩn đoán | Ý nghĩa trực tiếp | Nguyên nhân cấu hình có thể xảy ra |
| --- | --- | --- |
| `package p.q does not exist` | Compiler không tìm được package/kiểu có thể sử dụng trong import cụ thể | Thiếu dependency, sai classpath root, JAR sai, dependency chỉ có ở runtime, build module chưa chạy |
| `cannot find symbol` | Compiler không resolve được một tên class, variable, method hoặc thành viên tại vị trí sử dụng | Class chưa có trên compile path, source chưa được đưa vào build, import thất bại; cũng có thể là sai tên hoặc sai API |
| `cannot access p.q.Type` | Đã có dấu vết của kiểu nhưng compiler không đọc/định vị hợp lệ dependency cần thiết | Thiếu class phụ thuộc gián tiếp, JAR lỗi, binary không tương thích, phiên bản class sai |
| `package p.q is not visible` | Với JPMS, package có thể tồn tại nhưng module không cho đọc/export | `module-info.java`, `requires`, `exports`, module path hoặc flags sai |
| `class file has wrong version` | Class đã được tìm thấy nhưng bytecode mới hơn compiler hỗ trợ | Dùng JDK build cũ hơn bản JDK đã biên dịch dependency |

**Một root cause có thể gây nhiều diagnostic.** Nếu dòng `import` không tìm thấy `Greeter`, dòng `Greeter.message()` tiếp theo cũng có thể báo `cannot find symbol`. Trong trường hợp này hãy sửa **lỗi đầu tiên về dependency/package** rồi biên dịch lại; không coi mỗi dòng diagnostic là một lỗi độc lập.

## 2. Classpath là gì, và compiler tìm class theo đường dẫn nào?

Classpath là danh sách **thư mục gốc** và **JAR/ZIP** chứa các class (cùng một số tài nguyên), dùng bởi compiler hoặc runtime tùy ngữ cảnh. Khi cần class có binary name `com.example.lib.Greeter`, một thư mục trên classpath phải chứa:

~~~text
<root>/com/example/lib/Greeter.class
~~~

Nếu thư mục cấu trúc như sau:

~~~text
project/
  lib/
    out/
      com/
        example/
          lib/
            Greeter.class
  app/
    src/
      com/
        example/
          app/
            App.java
    out/
~~~

thì compile classpath root cần là **`lib/out`**, vì đó là thư mục mà đường dẫn `com/example/lib/Greeter.class` bắt đầu từ đó. Chỉ định `lib/out/com`, `lib/out/com/example` hoặc một thư mục `lib/src` không có class đã biên dịch có thể khiến compiler báo package không tồn tại.

JAR tương đương phải có **entry**:

~~~text
com/example/lib/Greeter.class
~~~

Tên file `greeter.jar` không mang thông tin package; cấu trúc các entry bên trong mới quyết định compiler tìm được kiểu nào.

Các lựa chọn `javac` phổ biến:

- `-cp <path>`, `-classpath <path>`, `--class-path <path>`: khai báo **compile classpath**.
- `-d <directory>`: nơi ghi class file sau khi biên dịch, **không tự động biến thành classpath cho một invocation khác**.
- `-sourcepath <path>` hoặc `--source-path <path>`: đường dẫn tìm **source Java** bổ sung; không thay cho classpath chứa dependency đã biên dịch.
- `--module-path <path>`: đường dẫn module trong dự án dùng Java Platform Module System (JPMS); có quy tắc module riêng, không đơn giản là classpath khác tên.
- `--release 17`: giới hạn ngôn ngữ, API nền tảng và class file target theo release đã chọn; không tự thêm dependency ứng dụng.
- `-encoding UTF-8`: cách đọc bytes của source; không sửa classpath.

Khi viết `-cp` với **nhiều entry**, separator phụ thuộc hệ điều hành:

| Nơi chạy `javac` / `java` | Classpath hai entry |
| --- | --- |
| Linux, macOS (Bash/Zsh) | `lib/out:app/out` |
| Windows (PowerShell/cmd) | `lib/out;app/out` |

Các ký tự `:` và `;` ở đây là **classpath separators**, khác dấu `/` hoặc `\` trong đường dẫn file. Trích dẫn cả giá trị classpath khi có khoảng trắng hoặc ký tự shell đặc biệt, ví dụ `-cp "lib/out;app/out"` trên Windows. Trong PowerShell, nếu tham số chứa `;`, việc đặt trong dấu nháy là đặc biệt quan trọng để shell không tách thành các statement.

## 3. Ví dụ đầy đủ: có dependency nhưng javac không thấy

Thí nghiệm có hai thành phần: thư viện `Greeter` và ứng dụng `App`. Chúng được biên dịch **trong hai lần gọi `javac` riêng** để quan sát đúng nguyên nhân lỗi do classpath. Dùng JDK 17+.

### 3.1. Cấu trúc source

~~~text
project/
  lib/
    src/com/example/lib/Greeter.java
    out/
  app/
    src/com/example/app/App.java
    out/
~~~

Tệp **`lib/src/com/example/lib/Greeter.java`**:

~~~java
package com.example.lib;

public final class Greeter {
    public static String message() {
        return "Hello, classpath!";
    }
}
~~~

Tệp **`app/src/com/example/app/App.java`**:

~~~java
package com.example.app;

import com.example.lib.Greeter;

public final class App {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

Hai class có thể được biên dịch và sử dụng độc lập. Dòng `package` phải đúng với tên đầy đủ mà người dùng import; thư mục `src/com/example/...` là tổ chức nhất quán giúp build dễ hiểu. Chính package declaration, không phải chỉ tên thư mục, xác định binary name của class.

### 3.2. Biên dịch thư viện

Tại `project/` trong Bash:

~~~bash
mkdir -p lib/out app/out
javac --release 17 -encoding UTF-8 -d lib/out lib/src/com/example/lib/Greeter.java
~~~

Khi thành công, compiler tạo:

~~~text
lib/out/com/example/lib/Greeter.class
~~~

Lệnh trên mới chỉ tạo class cho thư viện. Không có quy tắc nào bắt `javac` invocation tiếp theo phải tự biết `lib/out`.

### 3.3. Cố tình bỏ classpath để tái hiện lỗi

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 -d app/out app/src/com/example/app/App.java
~~~

Vì `javac` chưa được cung cấp `lib/out`, các chẩn đoán quan trọng xuất hiện (đường dẫn tuyệt đối và cách hiển thị có thể khác):

~~~text
App.java:3: error: package com.example.lib does not exist
import com.example.lib.Greeter;
                      ^
App.java:7: error: cannot find symbol
        System.out.println(Greeter.message());
                           ^
  symbol:   variable Greeter
  location: class App
2 errors
~~~

Đây là một lần biên dịch **thất bại đúng dự kiến**. Diagnostic thứ hai không có nghĩa `Greeter` đã trở thành biến trong Java source; compiler chỉ đang nói tên `Greeter` tại vị trí expression không resolve thành ký hiệu hợp lệ. Nguyên nhân nằm ở việc class `Greeter` chưa được đưa vào vùng compiler tìm kiếm.

Nếu thay `-cp lib/out` bằng `-cp lib/out/com`, lỗi **vẫn xảy ra**: classpath root đã bị đặt quá sâu nên đường dẫn tương đối tới `com/example/lib/Greeter.class` không khớp.

### 3.4. Sửa compile classpath

~~~bash
javac --release 17 -encoding UTF-8 -cp lib/out -d app/out app/src/com/example/app/App.java
~~~

Bây giờ `javac` có thể đọc `com.example.lib.Greeter` từ `lib/out`. Trong phép thử trên JDK hỗ trợ `--release 17`, lệnh trả exit code 0, không phát diagnostic.

Lúc **chạy** cần cả hai thư mục, vì JVM cần nạp `App.class` và `Greeter.class`:

~~~bash
java -cp "app/out:lib/out" com.example.app.App
~~~

Trên **Windows PowerShell/cmd**, thay dấu `:` trong giá trị classpath bằng dấu `;`:

~~~powershell
java -cp "app/out;lib/out" com.example.app.App
~~~

Stdout trong cả hai trường hợp:

~~~text
Hello, classpath!
~~~

Đây là nguyên tắc quan trọng: **compile classpath và runtime classpath là hai tập cấu hình riêng**. Việc biên dịch thành công với `-cp lib/out` không tự đảm bảo khi chạy `java -cp app/out ...` JVM cũng tìm được `Greeter`. Runtime thiếu thư viện có thể gây `NoClassDefFoundError: com/example/lib/Greeter`.

### 3.5. Dùng JAR thay cho thư mục class

Tạo JAR thư viện từ thư mục `lib/out`:

~~~bash
jar --create --file greeter.jar -C lib/out .
jar --list --file greeter.jar
~~~

Bên trong JAR phải có entry `com/example/lib/Greeter.class`. Sau đó:

~~~bash
javac --release 17 -encoding UTF-8 -cp greeter.jar -d app/out app/src/com/example/app/App.java
java -cp "app/out:greeter.jar" com.example.app.App
~~~

Lệnh `java` dành cho Windows dùng `-cp "app/out;greeter.jar"`. Stdout vẫn là `Hello, classpath!`. Các lệnh thư mục và JAR này đã được kiểm chứng với `javac --release 17`, `jar` và `java`.

**Sai lầm thường gặp:** JAR được tạo bằng cách đóng gói cả thư mục `out` như một entry cha, dẫn tới `out/com/example/lib/Greeter.class` thay vì `com/example/lib/Greeter.class`. Nếu entry không đúng package path, việc thêm JAR đó vào `-cp` vẫn không giải quyết được lỗi.

## 4. Cơ chế symbol resolution: tìm package rồi tìm kiểu và thành viên

Trong đoạn:

~~~java
import com.example.lib.Greeter;
System.out.println(Greeter.message());
~~~

Dòng đầu là **trích đoạn** từ `App.java`, dòng thứ hai phải nằm trong method. `javac` cần tìm class có tên `com.example.lib.Greeter` từ source đang biên dịch, source path được phép, classpath hoặc module path tùy cấu hình. Sau đó compiler mới resolve member `message()` của class `Greeter`.

Nếu class chưa tìm thấy, không thể phân tích đúng lời gọi member, vì vậy hai diagnostic cùng xuất hiện. Khi class đã tìm thấy nhưng method không có hoặc không accessible, chẩn đoán có thể chuyển thành `cannot find symbol: method message()` hoặc lỗi access tương ứng. Khi ấy **không tiếp tục sửa classpath một cách mù quáng**: kiểm tra API của phiên bản dependency đang dùng.

Một số tình huống khác cũng tạo `cannot find symbol`:

| Ký hiệu không thấy | Điều cần kiểm tra trước |
| --- | --- |
| Tên class `Greeter` | Source file, import, package, classpath/module path |
| `Greeter.message()` khi class đã resolve | Đúng tên/case method, danh sách tham số, `static`, version của thư viện |
| Tên biến `result` | Phạm vi (scope), khai báo và chính tả |
| Tên annotation | Artifact annotation có mặt trên compile path chưa |
| Type được sinh bởi annotation processor | Processor thực sự chạy, generated-source output có tồn tại, đã đưa đúng vào compile |
| Class từ Java standard library | Đúng JDK và `--release`; ví dụ API mới không có trong release cũ |

Do đó thông báo `cannot find symbol` **không đủ để kết luận classpath sai**. Cần đọc dòng `symbol:`, `location:`, import có liên quan và ngữ cảnh build.

## 5. Các nguyên nhân cấu hình phổ biến và cách sửa

### 5.1. Thiếu dependency ở compile scope

Một thư viện có thể nằm trong runtime packaging nhưng bị loại khỏi **compile classpath**. Các build tool sử dụng scopes/configurations để quyết định dependency xuất hiện ở pha nào.

- Maven: dependency `provided` vẫn có mặt trên compile classpath nhưng thường không được đóng gói như runtime dependency; `runtime` không đưa dependency vào compile classpath. Với một API được source trực tiếp import, scope `compile` thường phù hợp hơn `runtime`.
- Gradle: `implementation` cho code sử dụng trong module hiện tại, `api` (với plugin `java-library`) khi API công khai của module cần lộ dependency cho consumer; `runtimeOnly` không cấp dependency để compile source.
- IDE: chọn đúng module dependency, version, scope và cấu hình compiler của IDE; **IDE hiển thị import không đỏ chưa chứng minh CI compile có cùng classpath**.

### 5.2. Đặt sai classpath root hoặc nhầm source folder với classes folder

Classpath để tìm class đã biên dịch cần trỏ đến **gốc của cấu trúc package**. Nếu artifact nằm ở `build/classes/java/main/com/example/lib/Greeter.class`, root là `build/classes/java/main`, không phải `build/classes/java/main/com/example/lib`. Nếu chỉ có source `Greeter.java` mà chưa có bytecode, cần biên dịch thư viện trước hoặc cấu hình source path/source set đúng.

Hãy nhớ `javac -d lib/out ...` là **output**, còn `javac -cp lib/out ...` là **input của invocation khác**.

### 5.3. Thiếu một source Java ở invocation hiện tại

Nếu hai tệp cùng dự án và compiler được gọi thủ công, có thể truyền cả hai source:

~~~bash
javac --release 17 -encoding UTF-8 -d out lib/src/com/example/lib/Greeter.java app/src/com/example/app/App.java
java -cp out com.example.app.App
~~~

Khi compiler xử lý trực tiếp cả hai tệp, không cần tạo `lib/out` rồi dùng `-cp` giữa hai lần. Tuy vậy, trong dự án có nhiều module, quản lý dependency/compile order qua build tool vẫn rõ ràng hơn.

Cẩn thận với `-sourcepath`, working directory và việc `javac` **có thể** tự tìm source khi môi trường cho phép: không nên phụ thuộc hành vi tự phát hiện ngầm để có build tái lập. Cấu hình source set và explicit classpath/source path trong build script là tốt hơn.

### 5.4. Tên package, tên lớp và chữ hoa/thường không khớp

Kiểm tra phần đầu tệp:

~~~java
package com.example.lib;
public final class Greeter { /* ... */ }
~~~

Đây là đoạn rút gọn minh họa khai báo kiểu. Import `com.example.libs.Greeter` (thừa `s`) hoặc `com.example.lib.greeter` (khác chữ hoa) không trỏ đến cùng class. Java phân biệt chữ hoa/thường; sự khác nhau giữa filesystem Windows và Linux có thể khiến lỗi chỉ xuất hiện trong CI.

Nếu file .class nằm đúng thư mục nhưng internal binary name thực tế khác với đường dẫn đang dùng, compiler có thể báo `bad class file` hoặc nói class file chứa wrong class. Kiểm tra bằng `javap` và rebuild từ package declaration đúng.

### 5.5. JAR sai hoặc thiếu dependency bắc cầu

Một JAR có thể tồn tại trên classpath mà **không chứa class cần thiết**, hoặc chứa class đó nhưng thiếu dependency mà nó tham chiếu. Kiểm tra cấu trúc:

~~~bash
jar tf greeter.jar
javap -classpath greeter.jar com.example.lib.Greeter
~~~

`jar tf` liệt kê các entry; `javap` tìm class theo binary name trên classpath. Nếu `javap` không thấy class thì kiểm tra artifact/version/package, không đơn thuần thêm lại cùng path.

Nếu thư viện `A` có method trả về class từ thư viện `B`, source consumer có thể không compile nếu `B` thiếu trên compile path, dù chỉ import trực tiếp từ `A`. Trong build tool, kiểm tra **resolved dependency graph** và các loại dependency exposure, chứ không chỉ dependency cấp đầu.

### 5.6. Kết quả build cũ, output khác hoặc thứ tự build sai

Dự án có thể compile theo thứ tự sai: module `app` bắt đầu trước khi module `lib` tạo output; hoặc một shell dùng `out` trong khi IDE ghi vào `target/classes` / `build/classes/java/main`. Cách xử lý là dùng **một pipeline build có khai báo quan hệ phụ thuộc**, chạy sạch khi nghi có artifact cũ, rồi xem lệnh compile thật sự và vị trí output mới.

Không sao chép ngẫu nhiên `.class` vào các thư mục để làm lỗi biến mất: cách đó thường tạo duplicate và khiến lỗi trở lại trên CI.

## 6. Thiết lập Maven cho dependency giữa hai module

Giả sử thư viện có tọa độ Maven:

~~~text
groupId    = com.example
artifactId = greeter-lib
version    = 1.0.0
~~~

Trong POM của module ứng dụng, cấu hình dependency (đây là **đoạn của POM**, không phải toàn bộ file):

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>greeter-lib</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Khi module thư viện thật sự có những tọa độ đó và đã được đưa vào Maven reactor hoặc repository mà build đang sử dụng, Maven sẽ đưa dependency vào compile classpath mặc định của app.

Với **multi-module reactor** chuẩn, parent POM cần khai báo modules tương ứng (các tên thư mục dưới đây là tên ví dụ):

~~~xml
<modules>
    <module>lib</module>
    <module>app</module>
</modules>
~~~

Các khối XML này mô tả **phần cấu hình liên quan**; POM hoàn chỉnh còn cần `modelVersion`, `groupId`, `artifactId`, `version`, `packaging` và thiết lập compiler thích hợp. Khi dùng reactor, lệnh `mvn -pl app -am compile` cho phép Maven build cả dependency modules trong reactor cần thiết cho app (với module names đúng theo reactor của dự án). Đảm bảo quan hệ qua dependency của module, không chỉ dựa vào thứ tự liệt kê trong `<modules>`.

Các lệnh kiểm tra hữu ích:

~~~bash
mvn dependency:tree
mvn -X compile
~~~

Đọc resolved artifact, scope và compiler arguments trong log; tránh đưa `greeter-lib` vào scope `runtime` nếu `App.java` import trực tiếp `Greeter`.

## 7. Thiết lập Gradle cho dependency giữa hai module

Ví dụ một dự án Gradle nhiều module dùng cấu trúc **chuẩn của plugin Java**: `lib/src/main/java/com/example/lib/Greeter.java`, `app/src/main/java/com/example/app/App.java`.

Trong **`settings.gradle`** (Groovy DSL):

~~~groovy
rootProject.name = 'classpath-demo'
include 'lib', 'app'
~~~

Trong **`lib/build.gradle`**:

~~~groovy
plugins {
    id 'java-library'
}
~~~

Trong **`app/build.gradle`**:

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':lib')
}

application {
    mainClass = 'com.example.app.App'
}
~~~

Các file này thể hiện một cấu hình tối giản. Với Gradle có JDK/toolchain tương thích và source đặt đúng đường dẫn theo plugin, chạy:

~~~bash
./gradlew :app:run
~~~

Trên Windows có thể chạy `gradlew.bat :app:run`. Gradle tự build module `lib`, đưa kết quả lên **compile classpath** của app và cấu hình runtime path theo dependency. Nếu bỏ `implementation project(':lib')`, import `com.example.lib.Greeter` trong app sẽ thất bại.

Một dependency chỉ khai báo `runtimeOnly project(':lib')` sẽ không đủ để source app dùng trực tiếp `Greeter` khi compile.

Để kiểm tra classpath dependency được chọn:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

Đây là lệnh kiểm tra cấu hình dependency được Gradle resolve, không phải cách tự sửa build. Với Kotlin DSL, cú pháp config sẽ khác đôi chút.

## 8. Classpath, module path và Java Platform Module System

Kể từ Java 9, dự án có thể khai báo `module-info.java`. Lúc đó Java có thể phân biệt:

- **Classpath**: code nằm trong *unnamed module* (theo mô hình cổ điển).
- **Module path**: nơi chứa named modules; compiler kiểm tra quan hệ `requires`, `exports` và khả năng đọc package.

Ví dụ module `com.example.app` muốn dùng public class từ module `com.example.lib` thì thường cần:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

Đây là nội dung **`module-info.java` của app** trong một dự án JPMS được cấu hình module path đúng; thư viện cũng cần có module descriptor hoặc cơ chế module tương ứng. Nếu dependency nằm trên module path nhưng app module không `requires` nó, lỗi có thể là `package ... is not visible`, khác với `package ... does not exist`.

Không giải quyết lỗi visibility bằng cách tùy tiện đổi `--module-path` thành `-cp` nếu dự án có module descriptors và yêu cầu encapsulation. Cần xác định dự án là classpath-based hay module-based rồi cấu hình thống nhất.

## 9. Phân biệt compile-time và runtime classpath

| Câu hỏi | Khi compile (`javac`) | Khi chạy (`java`) |
| --- | --- | --- |
| Class chính phải có ở đâu? | Source được truyền, source path hoặc classpath/module path phù hợp | Main class/module phải load được trên runtime path |
| Thiếu dependency dùng trong code? | `package ... does not exist`, `cannot find symbol`, `cannot access` | Có thể là `NoClassDefFoundError`, `ClassNotFoundException`, `ServiceConfigurationError`... |
| Tùy chọn chính | `javac -cp ... -d ...` | `java -cp ... package.Main` |
| Có tự truyền cấu hình sang phía kia? | Không | Không |

Nếu chạy `java -jar app.jar`, launcher dùng manifest `Main-Class` và cách tìm dependency liên quan đến manifest/JAR/class loader; tham số `-cp` của launcher không được áp dụng để định vị app classes theo cách chạy `java -cp ... Main` thông thường khi `-jar` có hiệu lực. Để phát hành app cần đóng gói dependencies hoặc khai báo manifest/classpath thích hợp, dùng fat JAR hoặc distribution từ build tool tùy nhu cầu.

Một lỗi runtime sau khi compile đúng là **một bài toán khác**: cần xem runtime launch command, manifest và JAR thực tế. Không thể sửa chỉ bằng cách bổ sung dependency vào `javac -cp` nếu runtime vẫn không chứa nó.

## 10. Quy trình chẩn đoán có thứ tự, tránh sửa mò

**Bước 1 — Ghi chính xác diagnostic đầu tiên.** Lấy đường dẫn file, số dòng, `symbol`, `location`, package, và lệnh build. Nếu import lỗi ở dòng 3 và symbol lỗi ở dòng 7, ưu tiên xác định dependency của import.

**Bước 2 — Xác minh tên đầy đủ.** Mở source đang được biên dịch để kiểm tra `package`, `import`, tên public class, chữ hoa/thường và API thật sự tồn tại trong phiên bản thư viện. Nếu class là `com.example.lib.Greeter`, đường dẫn class file trong thư mục/JAR phải phản ánh đúng tên này.

**Bước 3 — Kiểm tra artifact đã tồn tại.** Sau khi compile lib, phải có `lib/out/com/example/lib/Greeter.class` hoặc JAR chứa entry đó. Nếu không có, sửa build của thư viện, source inclusion hoặc output path trước.

**Bước 4 — Kiểm tra compile classpath thực tế.** Đường dẫn là thư mục **trên package tree**; JAR là file JAR, không phải chỉ thư mục chứa JAR. Dùng dấu phân cách phù hợp hệ điều hành và quote đường dẫn. Với Maven/Gradle, xem cấu hình đã resolve.

**Bước 5 — Thực hiện một lệnh compile tối thiểu.** Với ví dụ:

~~~bash
javac --release 17 -encoding UTF-8 -cp lib/out -d app/out app/src/com/example/app/App.java
~~~

Nếu chạy được thủ công nhưng build tool thất bại, vấn đề nằm ở cách tool dựng classpath, version hoặc source set. Đừng coi giải pháp thủ công là cấu hình bền vững cho CI.

**Bước 6 — Kiểm tra class có đúng API không.** Khi package/import đã resolve nhưng method chưa thấy, dùng:

~~~bash
javap -classpath lib/out -public com.example.lib.Greeter
~~~

Nếu phương thức `message()` không có hoặc signature khác, kiểm tra version của JAR, class trùng tên, quyền truy cập và static/instance.

**Bước 7 — Kiểm tra JDK, module và annotation processing.** `--release` có thể chặn API mới của JDK; JPMS có thể chặn export/read; generated type có thể thiếu do annotation processor chưa chạy. Mỗi trường hợp có cách sửa riêng.

**Bước 8 — Build sạch và chạy bằng runtime path đúng.** Sửa cấu hình trong repository rồi build trên máy sạch/CI. Với ví dụ:

~~~bash
java -cp "app/out:lib/out" com.example.app.App
~~~

Đổi dấu `:` thành `;` trên Windows. Xác minh stdout và artifact thay vì chỉ thấy IDE hết gạch đỏ.

## 11. Các bẫy classpath dễ bỏ sót

1. **Thêm `lib/out/com/example` thay vì `lib/out`.** Package lookup luôn ghép đường dẫn từ classpath root.
2. **Chỉ đặt `CLASSPATH` environment variable.** Một `-cp` tường minh trên invocation sẽ xác định đường tìm class riêng; build tool thường tự thiết lập arguments nên môi trường không phải nơi cấu hình đáng tin.
3. **Quên dấu `.` khi đặt `-cp` thủ công.** Khi đã đặt classpath tường minh, current directory không mặc nhiên được thêm chỉ vì nó là working directory; dùng `.` như một entry nếu thật sự cần. Nhưng nên ưu tiên output directory cụ thể.
4. **Nhầm `-d` với `-cp`.** Đầu ra của lần compile trước chỉ là input của lần compile sau khi path được chỉ ra đúng.
5. **Lấy nhầm artifact khác version.** Một `Greeter.class` cũ có thể không có method mới, dẫn đến `cannot find symbol` dù import hoạt động.
6. **Classpath chứa nhiều version trùng class.** Classpath order ảnh hưởng bản class nào được tìm trước; kiểm tra duplicate và dependency tree.
7. **Wildcard `lib/*` giải quyết mọi thứ.** Wildcard classpath thông thường mở rộng JAR trong một thư mục, không tìm đệ quy các thư mục con và không biến source `.java` thành compiled class.
8. **Sai scope dependency.** `runtimeOnly` hay Maven `runtime` không đủ cho class được source dùng trực tiếp ở compile phase.
9. **Đường dẫn có khoảng trắng.** Không quote đúng giá trị `-cp` hoặc bị shell cắt ở dấu `;` khiến compiler nhận đường dẫn thiếu.
10. **Trộn module path với classpath.** Có thể giải quyết import nhưng phát sinh lỗi package visibility hoặc split package; phải phân biệt JPMS.
11. **Chạy `java` ở project root rồi nghĩ JVM tự tìm toàn bộ `.class` sâu bên dưới.** Runtime classpath cũng cần đúng gốc package.
12. **Chỉ sửa IDE mà không sửa build script.** CI và người khác vẫn thiếu dependency; build configuration phải là nguồn chính xác.

## 12. Tự kiểm tra bằng các tình huống

**Câu 1.** Có file `build/classes/com/acme/Service.class` và source import `com.acme.Service`. Nên thêm gì vào classpath?  
**Đáp án:** `build/classes`; đặt `build/classes/com` quá sâu sẽ tìm sai đường dẫn.

**Câu 2.** `App.java` báo `package com.example.lib does not exist`, rồi báo `cannot find symbol: Greeter`. Có cần sửa hai dòng mã riêng?  
**Đáp án:** Chưa. Kiểm tra compile classpath trước; nếu dependency có mặt sau khi sửa path, cả hai diagnostic có thể biến mất.

**Câu 3.** `javac -cp lib/out` thành công, nhưng `java -cp app/out com.example.app.App` lỗi. Vì sao?  
**Đáp án:** Runtime classpath thiếu `lib/out`; cần `app/out:lib/out` trên Unix hoặc `app/out;lib/out` trên Windows.

**Câu 4.** Đã import được `Greeter`, nhưng compiler báo `cannot find symbol: method message()`. Làm gì?  
**Đáp án:** Dùng `javap` xem class thực tế trên compile classpath và kiểm tra signature, visibility, version; đây có thể là API mismatch chứ không phải thiếu package.

**Câu 5.** Lệnh `jar tf greeter.jar` in `out/com/example/lib/Greeter.class`. Cấu hình `-cp greeter.jar` có đủ không?  
**Đáp án:** Chưa; entry sai gốc package. Tạo lại JAR bằng `jar --create --file greeter.jar -C lib/out .`.

**Câu 6.** Maven dependency của API dùng trong source đặt scope `runtime`, hoặc Gradle đặt `runtimeOnly`. Có tác dụng với compile không?  
**Đáp án:** Không. Chuyển sang scope/configuration thích hợp với compile path.

**Câu 7.** Dự án có `module-info.java`, thư viện vẫn tồn tại nhưng compiler báo `package ... is not visible`. Có nên lập tức thêm JAR vào classpath?  
**Đáp án:** Kiểm tra `requires`, `exports`, module path và module boundaries trước; lỗi là visibility trong JPMS, không đơn thuần thiếu file.

**Câu 8.** Biên dịch qua IDE thành công nhưng CI báo package không tồn tại. Bằng chứng nào hữu ích nhất?  
**Đáp án:** Compiler invocation, resolved dependency graph, module/source set và các artifact có thật trong pipeline CI.

## 13. Tài liệu chuẩn để đối chiếu

- [javac Command — Classpath, source path, module path](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [java Command — classpath và cách chạy chương trình](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Maven: Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle: Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)

**Điểm cốt lõi:** `package ... does not exist` thường cho biết compiler không tìm thấy package/class cần import; `cannot find symbol` cho biết một tên không resolve được và có nhiều nguyên nhân. Khi hai lỗi xuất hiện cùng nhau, hãy bắt đầu từ **package declaration → class file/JAR entry → classpath root → compile invocation → dependency scope/version**. Sửa cấu hình build ở đúng pha, kiểm tra lại bằng lệnh biên dịch và chạy sạch để tránh lệ thuộc IDE hoặc máy cá nhân.
