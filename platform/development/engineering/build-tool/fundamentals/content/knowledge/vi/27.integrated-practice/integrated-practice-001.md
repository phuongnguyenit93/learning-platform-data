# Lập bản đồ quy trình build thủ công của một ứng dụng Java nhỏ

Build tool như Gradle hoặc Maven tự động hóa nhiều bước: tìm mã nguồn, gọi compiler, xử lý resource, biên dịch test, chạy test, đóng gói JAR và quản lý dependency. Để hiểu build tool đang làm gì, một bài thực hành hữu ích là tự thực hiện các bước đó bằng JDK và command line, sau đó ghi lại đầu vào, công cụ, đầu ra và mối quan hệ giữa từng bước.

Bài học này xây dựng một ứng dụng Java CLI nhỏ không dùng thư viện bên ngoài. Ta sẽ đi từ source code đến class file, copy resource, compile và chạy một test đơn giản, tạo executable JAR, kiểm tra nội dung archive và chạy ứng dụng. Ví dụ dùng Java 17 trở lên để có thể chỉ định release 17 bằng javac.

Mục tiêu không phải tạo một quy trình thay thế Gradle/Maven cho dự án lớn. Mục tiêu là hiểu rõ những công việc mà build tool tự động thực hiện, biết output nào được tạo ở đâu, và có thể chẩn đoán lỗi khi một bước không hoạt động.

## 1. Bản đồ tổng thể của một lần build thủ công

Một ứng dụng Java nhỏ có thể đi qua các bước:

~~~text
Source files (.java)         Resource files (.properties)
       |                               |
       v                               v
Compile with javac             Copy resources
       |                               |
       v                               |
Class files (.class) <----------------+
       |
       v
Compile test sources
       |
       v
Run test program
       |
       v
Package classes + resources with jar
       |
       v
Executable JAR
       |
       v
Run with java -jar
       |
       v
Application output
~~~

Mỗi bước nhận đầu vào cụ thể và tạo đầu ra có thể quan sát:

| Bước | Đầu vào | Công cụ | Đầu ra |
|---|---|---|---|
| Chuẩn bị | JDK, source tree, resource, cấu hình release | Shell và JDK | Thư mục output |
| Biên dịch main | Các file .java | javac | .class trong thư mục classes |
| Xử lý resource | .properties hoặc file tĩnh | cp/Copy-Item | Resource trong class output |
| Biên dịch test | Test source và main class output | javac | Test class trong test-classes |
| Chạy test | Main classes, resources và test classes | java | Kết quả pass/fail |
| Đóng gói | Main classes và resources | jar | Executable JAR |
| Kiểm tra | JAR đã tạo | jar, unzip hoặc công cụ archive | Danh sách entry và manifest |
| Chạy ứng dụng | JAR và Java runtime | java -jar | Hành vi ứng dụng |

Build tool thường mô hình hóa các bước này thành task có input/output và dependency. Khi chạy task cuối, nó lập thứ tự thực hiện, kiểm tra output cũ, chỉ chạy phần cần thiết và báo lỗi tại bước thất bại.

## 2. Chuẩn bị JDK và môi trường

### 2.1. Phân biệt JDK với runtime

Để biên dịch thủ công, cần JDK vì JDK cung cấp các công cụ:

- javac: biên dịch Java source thành bytecode.
- java: chạy chương trình Java.
- jar: tạo và kiểm tra JAR archive.
- javadoc: sinh tài liệu API nếu cần.
- jshell: thử nhanh các biểu thức Java trong môi trường tương tác.

Kiểm tra phiên bản:

~~~bash
java -version
javac -version
jar --version
~~~

JDK dùng để chạy javac cần hỗ trợ tùy chọn release mà ta chọn. Ví dụ, để dùng --release 17, hãy dùng compiler JDK 17 trở lên.

Trên Windows PowerShell, có thể chạy cùng các lệnh trên. Nếu muốn biết executable nào được shell tìm thấy:

~~~powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v javac
echo "$JAVA_HOME"
~~~

Kết quả giúp phát hiện trường hợp java và javac đến từ hai JDK khác nhau hoặc JAVA_HOME chưa được cấu hình.

### 2.2. Xác định Java release mục tiêu

Trong ví dụ, ta chọn Java 17. Tùy chọn javac --release 17 yêu cầu compiler kiểm tra cú pháp, bytecode và API Java SE theo release 17.

Nếu ứng dụng cần chạy trên Java 17, tất cả dependency bên ngoài cũng phải tương thích với Java 17. Ví dụ này không có dependency ngoài nên việc kiểm soát đơn giản hơn.

### 2.3. Ghi lại điều kiện build

Trước khi chạy, ghi lại:

- JDK vendor và version.
- Hệ điều hành và kiến trúc.
- Java release mục tiêu.
- Working directory.
- Source revision nếu project nằm trong Git.
- Các biến môi trường có ảnh hưởng đến chương trình.

Điều này hữu ích khi so sánh kết quả giữa máy cá nhân và CI. Một lệnh javac giống nhau nhưng chạy trên compiler hoặc source tree khác vẫn có thể tạo output khác.

## 3. Tạo cấu trúc source project

Tạo một thư mục project tên manual-notes với cấu trúc:

~~~text
manual-notes/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/
│   │   │       └── example/
│   │   │           └── notes/
│   │   │               ├── Main.java
│   │   │               ├── Note.java
│   │   │               ├── NoteFormatter.java
│   │   │               └── AppConfig.java
│   │   └── resources/
│   │       └── app.properties
│   └── test/
│       └── java/
│           └── com/
│               └── example/
│                   └── notes/
│                       └── NoteFormatterTest.java
└── build/
    └── manual/
~~~

Các thư mục có ý nghĩa:

- src/main/java: source code chính của ứng dụng.
- src/main/resources: resource được đóng gói cùng ứng dụng.
- src/test/java: source test.
- build/manual/classes: nơi lưu class file và resource của ứng dụng.
- build/manual/test-classes: nơi lưu class file của test.
- build/manual: nơi chứa JAR và các output thủ công.

Cấu trúc này giống quy ước source layout phổ biến của Gradle/Maven, dù ở bài thực hành ta chưa dùng build tool.

### 3.1. Tạo thư mục

Linux/macOS:

~~~bash
mkdir -p src/main/java/com/example/notes
mkdir -p src/main/resources
mkdir -p src/test/java/com/example/notes
mkdir -p build/manual/classes
mkdir -p build/manual/test-classes
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path src/main/java/com/example/notes
New-Item -ItemType Directory -Force -Path src/main/resources
New-Item -ItemType Directory -Force -Path src/test/java/com/example/notes
New-Item -ItemType Directory -Force -Path build/manual/classes
New-Item -ItemType Directory -Force -Path build/manual/test-classes
~~~

Các lệnh tạo thư mục có thể chạy lại mà không làm hỏng source hiện có. Trong một quy trình thực tế, task build tool sẽ tự tạo output directory khi cần.

## 4. Viết source code chính

Ứng dụng sẽ đọc tên ứng dụng từ resource, tạo một note từ tham số command line và in nội dung đã định dạng.

### 4.1. Note.java

File src/main/java/com/example/notes/Note.java:

~~~java
package com.example.notes;

public record Note(String title, String body) {
}
~~~

Note là một Java record, chứa hai thành phần title và body. Record phù hợp cho kiểu dữ liệu đơn giản cần constructor, accessor và các method cơ bản do compiler sinh ra.

Vì record có từ Java 16, project cần compiler và runtime phù hợp. Ta chọn release 17 để có một mục tiêu rõ ràng.

### 4.2. NoteFormatter.java

File src/main/java/com/example/notes/NoteFormatter.java:

~~~java
package com.example.notes;

public final class NoteFormatter {
    private NoteFormatter() {
    }

    public static String format(String applicationName, Note note) {
        return applicationName + " | " + note.title() + ": " + note.body();
    }
}
~~~

Lớp này nhận tên ứng dụng và Note, sau đó trả về một dòng đã định dạng. Nó không phụ thuộc framework hoặc thư viện bên ngoài.

### 4.3. AppConfig.java

File src/main/java/com/example/notes/AppConfig.java:

~~~java
package com.example.notes;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class AppConfig {
    private AppConfig() {
    }

    public static String loadApplicationName() throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                     AppConfig.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Resource app.properties was not found");
            }

            properties.load(input);
        }

        return properties.getProperty("app.name", "Notes CLI");
    }
}
~~~

Lớp này tìm resource app.properties từ classpath. Dấu slash đầu tên resource có nghĩa tìm từ root của classpath. Khi chạy ứng dụng, file resource phải được copy vào class output hoặc nằm trong một JAR trên classpath.

### 4.4. Main.java

File src/main/java/com/example/notes/Main.java:

~~~java
package com.example.notes;

import java.io.IOException;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        String applicationName = AppConfig.loadApplicationName();

        String title = args.length > 0
                ? args[0]
                : "Manual build";

        String body = args.length > 1
                ? args[1]
                : "The build process is visible.";

        Note note = new Note(title, body);

        System.out.println(
                NoteFormatter.format(applicationName, note));
    }
}
~~~

Main là entry point của ứng dụng. JVM gọi method main khi khởi chạy lớp này. Chương trình đọc resource, tạo object và in kết quả.

### 4.5. app.properties

File src/main/resources/app.properties:

~~~properties
app.name=Notes CLI
~~~

Đây là resource, không phải Java source. javac không tự copy file này vào output directory. Ta phải thực hiện bước copy riêng hoặc để build tool quản lý resource processing.

## 5. Biên dịch Java source bằng javac

### 5.1. Biên dịch tất cả source trong một lần gọi

Đứng tại thư mục gốc manual-notes.

Linux/macOS:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d build/manual/classes \
  src/main/java/com/example/notes/Note.java \
  src/main/java/com/example/notes/NoteFormatter.java \
  src/main/java/com/example/notes/AppConfig.java \
  src/main/java/com/example/notes/Main.java
~~~

Windows PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 -d build/manual/classes src/main/java/com/example/notes/Note.java src/main/java/com/example/notes/NoteFormatter.java src/main/java/com/example/notes/AppConfig.java src/main/java/com/example/notes/Main.java
~~~

Ý nghĩa các tùy chọn:

| Tùy chọn | Tác dụng |
|---|---|
| --release 17 | Compile theo Java 17 language/API/bytecode target |
| -encoding UTF-8 | Đọc source bằng UTF-8 |
| -d build/manual/classes | Ghi class file vào output directory |
| Các đường dẫn .java | Những source file cần biên dịch |

javac có thể biên dịch nhiều source file trong cùng một invocation và tự liên kết các kiểu được khai báo trong những file đó. Vì vậy, không cần tự biên dịch Note trước rồi mới compile Main nếu đưa tất cả source vào cùng command.

### 5.2. Kiểm tra output

Sau khi compile thành công, thư mục classes có cấu trúc tương tự:

~~~text
build/manual/classes/
└── com/
    └── example/
        └── notes/
            ├── AppConfig.class
            ├── Main.class
            ├── Note.class
            └── NoteFormatter.class
~~~

Dùng lệnh liệt kê:

~~~bash
find build/manual/classes -type f
~~~

PowerShell:

~~~powershell
Get-ChildItem build/manual/classes -Recurse -File
~~~

Class file chứa bytecode JVM, không phải source code Java. Có thể xem bytecode bằng javap:

~~~bash
javap -classpath build/manual/classes -c com.example.notes.Main
~~~

javap giúp quan sát bytecode và xác nhận class đã được tạo. Nó không chạy ứng dụng.

### 5.3. Nếu compiler báo lỗi

Một số lỗi thường gặp:

- javac không được nhận diện: JDK chưa có trên PATH hoặc JAVA_HOME/PATH sai.
- invalid source release: JDK compiler không hỗ trợ release được yêu cầu.
- package does not exist: source import một package không có trên compile classpath/module path.
- cannot find symbol: class, method hoặc field không tồn tại/không được nhìn thấy.
- file not found: đường dẫn source không đúng so với working directory.
- class public phải có tên file tương ứng: tên file và public top-level class không khớp.

Đọc lỗi đầu tiên và xác định file/line trước khi thay đổi nhiều cấu hình. Một lỗi source có thể kéo theo nhiều lỗi cannot find symbol khác.

## 6. Xử lý resource bằng cách copy vào class output

javac chỉ biên dịch source Java. Resource cần được đưa vào classpath riêng.

Linux/macOS:

~~~bash
cp -R src/main/resources/. build/manual/classes/
~~~

Windows PowerShell:

~~~powershell
Copy-Item -Path src/main/resources/* -Destination build/manual/classes -Recurse -Force
~~~

Sau khi copy, output sẽ có:

~~~text
build/manual/classes/
├── app.properties
└── com/
    └── example/
        └── notes/
            ├── AppConfig.class
            ├── Main.class
            ├── Note.class
            └── NoteFormatter.class
~~~

Vì app.properties nằm ở root classpath, lời gọi getResourceAsStream("/app.properties") có thể tìm thấy nó.

### 6.1. Vì sao cần bước resource riêng?

Trong build tool, resource processing thường là task riêng:

- Gradle có processResources.
- Maven có resources plugin và phase resources.

Các task này copy resource từ source directory sang output directory, có thể hỗ trợ filtering, encoding và exclude/include. Khi build thủ công, ta thực hiện copy trực tiếp nên phải tự bảo đảm đúng vị trí và nội dung.

### 6.2. Chạy thử từ class output

~~~bash
java -cp build/manual/classes com.example.notes.Main "Build map" "Classes and resources are ready."
~~~

Trên Windows PowerShell, classpath chỉ có một thư mục nên command tương tự:

~~~powershell
java -cp build/manual/classes com.example.notes.Main "Build map" "Classes and resources are ready."
~~~

Kết quả dự kiến:

~~~text
Notes CLI | Build map: Classes and resources are ready.
~~~

Nếu báo Resource app.properties was not found, kiểm tra file đã copy vào build/manual/classes/app.properties chưa và command có dùng đúng classpath root không.

## 7. Biên dịch và chạy test thủ công

Build tool thường có source set riêng cho test, classpath test và test runner. Để hiểu ranh giới đó, ta tạo một test Java nhỏ không dùng JUnit.

### 7.1. NoteFormatterTest.java

File src/test/java/com/example/notes/NoteFormatterTest.java:

~~~java
package com.example.notes;

public final class NoteFormatterTest {
    private NoteFormatterTest() {
    }

    public static void main(String[] args) {
        Note note = new Note("Release", "Ready");

        String actual = NoteFormatter.format("Notes CLI", note);
        String expected = "Notes CLI | Release: Ready";

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + ", actual: " + actual);
        }

        System.out.println("NoteFormatterTest: PASS");
    }
}
~~~

Đây là test harness đơn giản: nếu kết quả sai, chương trình ném AssertionError và process kết thúc khác 0. Nếu đúng, nó in PASS. Nó không phải JUnit test và không có khả năng discovery/reporting như test framework.

### 7.2. Compile test source

Test source cần thấy class chính đã compile. Vì vậy, thêm main classes vào compile classpath.

Linux/macOS:

~~~bash
javac --release 17 -encoding UTF-8 \
  -classpath build/manual/classes \
  -d build/manual/test-classes \
  src/test/java/com/example/notes/NoteFormatterTest.java
~~~

Windows PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 -classpath build/manual/classes -d build/manual/test-classes src/test/java/com/example/notes/NoteFormatterTest.java
~~~

Sau khi compile, test class nằm trong:

~~~text
build/manual/test-classes/
└── com/
    └── example/
        └── notes/
            └── NoteFormatterTest.class
~~~

### 7.3. Chạy test

Linux/macOS dùng dấu hai chấm để phân cách các entry classpath:

~~~bash
java -ea -classpath build/manual/classes:build/manual/test-classes com.example.notes.NoteFormatterTest
~~~

Windows dùng dấu chấm phẩy:

~~~powershell
java -ea -classpath "build/manual/classes;build/manual/test-classes" com.example.notes.NoteFormatterTest
~~~

Tùy chọn -ea bật Java assertions. Test ví dụ dùng AssertionError trực tiếp nên vẫn phát hiện lỗi dù không bật -ea; tuy nhiên, giữ -ea hữu ích khi test có dùng từ khóa assert.

Kết quả dự kiến:

~~~text
NoteFormatterTest: PASS
~~~

### 7.4. Test classpath khác main classpath

Test thường cần:

- Main output để sử dụng class của ứng dụng.
- Test output để JVM tìm test class.
- Resource cần thiết để test.
- Test framework và test dependency nếu có.

Trong ví dụ, resource đã nằm trong main classes nên test classpath có thể đọc được nó. Khi dùng JUnit, cần thêm JUnit API vào compile classpath và JUnit engine vào runtime classpath phù hợp. Build tool sẽ quản lý các configuration này thay cho việc tự nối từng JAR.

## 8. Tạo executable JAR bằng jar

Sau khi compile main source và copy resource, ta có thể đóng gói toàn bộ nội dung trong class output thành một JAR.

~~~bash
jar --create --file build/manual/notes-app.jar --main-class com.example.notes.Main -C build/manual/classes .
~~~

Trên PowerShell, có thể dùng cùng command trên một dòng.

Ý nghĩa:

- --create yêu cầu tạo archive.
- --file chỉ định file JAR đầu ra.
- --main-class ghi tên lớp có method main vào manifest.
- -C chuyển vào thư mục classes trước khi thêm nội dung.
- Dấu chấm thêm toàn bộ nội dung trong thư mục hiện tại vào archive.

JAR được tạo tại build/manual/notes-app.jar.

### 8.1. Manifest và Main-Class

Một JAR có thể chứa file META-INF/MANIFEST.MF. Với lệnh trên, jar ghi thông tin Main-Class để Java launcher biết lớp cần gọi khi chạy java -jar.

Manifest có dạng khái quát:

~~~text
Manifest-Version: 1.0
Created-By: ...
Main-Class: com.example.notes.Main

~~~

Tên main class phải là tên đầy đủ gồm package. Nếu sai tên hoặc class không có method main đúng chữ ký, lệnh java -jar sẽ thất bại.

### 8.2. Kiểm tra nội dung JAR

Liệt kê entries:

~~~bash
jar --list --file build/manual/notes-app.jar
~~~

Kết quả cần có:

~~~text
META-INF/
META-INF/MANIFEST.MF
app.properties
com/example/notes/AppConfig.class
com/example/notes/Main.class
com/example/notes/Note.class
com/example/notes/NoteFormatter.class
~~~

Tên entry dùng dấu slash kể cả trên Windows vì JAR/ZIP có quy ước đường dẫn riêng. Không mong đợi source .java hoặc test class xuất hiện trong application JAR nếu ta chỉ đóng gói main classes.

Có thể giải nén manifest vào một thư mục kiểm tra riêng:

Linux/macOS:

~~~bash
mkdir -p build/manual/inspect
cd build/manual/inspect
jar --extract --file ../notes-app.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ../../..
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path build/manual/inspect
Push-Location build/manual/inspect
jar --extract --file ../notes-app.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
Pop-Location
~~~

Thư mục inspect tách biệt giúp không ghi đè file trong source tree.

## 9. Chạy ứng dụng từ executable JAR

Chạy:

~~~bash
java -jar build/manual/notes-app.jar "Release checklist" "Manual packaging is complete."
~~~

Kết quả dự kiến:

~~~text
Notes CLI | Release checklist: Manual packaging is complete.
~~~

Lệnh này cho Java launcher biết JAR nào cần chạy. Launcher đọc Main-Class từ manifest, nạp class và resource trong JAR rồi gọi main.

### 9.1. Phân biệt -cp và -jar

Chạy class trực tiếp:

~~~bash
java -cp build/manual/classes com.example.notes.Main
~~~

Chạy JAR:

~~~bash
java -jar build/manual/notes-app.jar
~~~

Hai cách có mục tiêu khác nhau:

- -cp chỉ định classpath do người chạy cung cấp và tên lớp main.
- -jar yêu cầu launcher dùng JAR được chỉ định và Main-Class trong manifest.

Khi dùng -jar, các tùy chọn classpath bên ngoài không được dùng như cách của -cp. Nếu ứng dụng cần dependency ngoài, phải đóng gói hoặc khai báo dependency runtime theo cơ chế phù hợp.

### 9.2. Working directory ảnh hưởng file tương đối

Resource classpath trong ví dụ không phụ thuộc working directory vì nó được nạp từ JAR. Nhưng nếu ứng dụng đọc file như ./config/app.yml hoặc ghi output vào ./data, đường dẫn tương đối được tính từ working directory của process.

Vì vậy, deployment cần xác định working directory hoặc dùng đường dẫn cấu hình rõ ràng. Không nhầm resource bên trong JAR với file cấu hình bên ngoài JAR.

## 10. Nếu ứng dụng có dependency bên ngoài

Ví dụ hiện tại chỉ dùng Java standard library nên compile classpath không cần JAR ngoài. Trong ứng dụng thực tế, dependency ngoài phải có mặt ở cả compile và runtime theo cách source sử dụng.

Giả sử source import một class từ lib/formatter.jar.

### 10.1. Compile với dependency

Linux/macOS:

~~~bash
javac --release 17 -classpath "lib/formatter.jar" -d build/manual/classes src/main/java/com/example/notes/*.java
~~~

Windows PowerShell:

~~~powershell
javac --release 17 -classpath "lib/formatter.jar" -d build/manual/classes src/main/java/com/example/notes/*.java
~~~

Khi có nhiều dependency, classpath có thể chứa nhiều JAR. Linux/macOS dùng dấu hai chấm; Windows dùng dấu chấm phẩy.

### 10.2. Chạy với dependency

Linux/macOS:

~~~bash
java -classpath "build/manual/classes:lib/*" com.example.notes.Main
~~~

Windows PowerShell:

~~~powershell
java -classpath "build/manual/classes;lib/*" com.example.notes.Main
~~~

Classpath wildcard lib/* cho phép launcher nạp các JAR trong thư mục lib theo quy tắc classpath của Java.

### 10.3. Thin JAR không tự chứa dependency

Nếu chỉ đóng gói build/manual/classes, JAR ứng dụng không tự chứa formatter.jar. Khi chạy, dependency phải được cung cấp bên ngoài.

Một distribution có thể có cấu trúc:

~~~text
notes-distribution/
├── notes-app.jar
└── lib/
    └── formatter.jar
~~~

Nếu dùng manifest Class-Path, các đường dẫn được ghi tương đối với vị trí JAR và được phân tách bằng khoảng trắng. Ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.notes.Main
Class-Path: lib/formatter.jar

~~~

Không dùng ký tự wildcard lib/* trong manifest Class-Path theo cách của command-line classpath. Liệt kê từng JAR cần thiết hoặc dùng một application distribution/plugin đóng gói dependency.

### 10.4. Vì sao không nên tự gộp mọi JAR một cách tùy tiện?

Fat/uber JAR có thể thuận tiện khi triển khai một file, nhưng việc gộp archive cần xử lý đúng:

- File cùng tên trong nhiều dependency.
- META-INF/services và Java ServiceLoader.
- Manifest của dependency.
- Signature metadata.
- License/notice.
- Resource cần merge hoặc giữ nguyên.
- Module descriptors và package sealing nếu có.

Build tool/plugin chuyên dụng thường xử lý các quy tắc này tốt hơn việc giải nén mọi JAR rồi copy đè file. Với ứng dụng nhỏ, application distribution chứa JAR và thư mục lib thường dễ hiểu và ít biến đổi hơn.

## 11. Lập bản đồ từng input và output

Đến đây, quy trình có thể được ghi thành một bản đồ chi tiết:

| Input | Bước xử lý | Output | Dùng ở bước sau |
|---|---|---|---|
| Note.java, NoteFormatter.java, AppConfig.java, Main.java | javac | .class trong classes | Run/test/package |
| app.properties | Copy resource | app.properties trong classes | Runtime classpath/JAR |
| Main classes + resource | javac test source | Test class trong test-classes | Test execution |
| classes + test-classes | java | Exit code và test output | Quyết định tiếp tục package |
| classes + resource | jar | notes-app.jar | Inspect/run |
| notes-app.jar | jar --list, manifest inspection | Entry list/manifest | Xác nhận package |
| notes-app.jar + JDK runtime | java -jar | Application output | Smoke check |

Một build tool thường ghi nhận quan hệ phụ thuộc giữa task:

~~~text
compileJava ----+
                |
processResources+----> classes output ----+----> jar
                |                         |
                +----> compileTestJava ---+----> test
~~~

Sơ đồ trên thể hiện luồng khái quát. Trong Gradle/Maven thực tế, task/phase và dependency graph chi tiết hơn. Test thường cần compile main output và resource trước khi chạy.

### 11.1. Source input và generated input

Trong ví dụ, mọi Java source được viết thủ công. Dự án thật có thể thêm generated source từ:

- Annotation processors.
- OpenAPI/Protobuf/schema generators.
- Code generation plugin.
- Parser/compiler generator.
- Task tạo version/build metadata.

Generated source cũng cần được đưa vào compile task đúng thời điểm. Nếu compile chạy trước khi generator tạo file, compiler có thể báo cannot find symbol.

### 11.2. Output cần được phân biệt

Các loại output không giống nhau:

- Class output: thư mục chứa .class.
- Resource output: file cấu hình/tài nguyên đã copy.
- Test output: test class và report.
- Archive output: JAR/WAR/ZIP.
- Runtime output: log, file được ứng dụng tạo, dữ liệu hoặc kết quả xử lý.

Không nên đặt runtime data vào thư mục classes rồi vô tình đóng gói nó vào JAR. Output của build và dữ liệu ứng dụng lúc chạy cần có vị trí riêng.

## 12. Clean build và incremental build thủ công

### 12.1. Clean output

Một clean build bắt đầu bằng việc xóa output cũ rồi chạy lại các bước:

Linux/macOS:

~~~bash
rm -rf build/manual
mkdir -p build/manual/classes
mkdir -p build/manual/test-classes
~~~

Windows PowerShell:

~~~powershell
Remove-Item -LiteralPath build/manual -Recurse -Force
New-Item -ItemType Directory -Force -Path build/manual/classes
New-Item -ItemType Directory -Force -Path build/manual/test-classes
~~~

Chỉ xóa output directory được xác định cho bài thực hành. Không xóa source hoặc cache toàn cục.

### 12.2. Vì sao build thủ công chưa có incremental checking?

Nếu gọi javac với tất cả source mỗi lần, compiler sẽ xử lý lại các source được truyền vào. Ta chưa xây dựng cơ chế theo dõi input/output để biết file nào thay đổi và chỉ compile phần cần thiết.

Build tool bổ sung:

- Input tracking: source, resource, compiler option và dependency.
- Output tracking: class/resource/archive được tạo.
- Up-to-date checking: bỏ qua task khi input/output không thay đổi.
- Incremental compilation: chỉ xử lý phần source bị ảnh hưởng khi có thể.
- Build cache: tái sử dụng output task từ cache khi input tương ứng.
- Task dependency graph: sắp xếp công việc theo quan hệ cần thiết.

Nếu thay NoteFormatter.java, build tool có thể nhận biết compileJava cần chạy lại và test phụ thuộc vào output mới. Với command line thủ công, người thực hiện phải tự quyết định compile lại những file nào hoặc đơn giản compile lại toàn bộ source.

### 12.3. Tại sao cần clean build khi chẩn đoán?

Output cũ có thể che giấu lỗi. Ví dụ, source đã xóa một class nhưng file .class cũ vẫn còn trong build/manual/classes; ứng dụng có thể chạy nhờ class cũ dù source hiện tại không còn tạo ra nó.

Clean build giúp xác nhận toàn bộ output có thể được tạo từ source và đầu vào hiện tại. Nó đặc biệt hữu ích khi nghi ngờ stale class, resource cũ hoặc generated output không được cập nhật.

## 13. Kiểm tra và chẩn đoán từng bước

Khi ứng dụng không build hoặc không chạy, hãy xác định bước đầu tiên bị lỗi.

### 13.1. Không tìm thấy javac

Dấu hiệu: shell báo javac không được nhận diện.

Kiểm tra:

~~~bash
java -version
javac -version
~~~

Nếu java có nhưng javac không có, có thể chỉ runtime được cài hoặc PATH đang trỏ đến một môi trường không có JDK compiler. Cài JDK và cấu hình PATH/JAVA_HOME phù hợp.

### 13.2. Compile báo cannot find symbol

Kiểm tra:

- Source file có được đưa vào javac command không?
- Package declaration và thư mục source có khớp không?
- Class được tham chiếu có nằm trong source list hoặc classpath không?
- Dependency version có chứa class/method cần dùng không?
- Generated source đã được tạo chưa?

Không nên giải quyết lỗi bằng cách copy một JAR bất kỳ vào thư mục output. Hãy xác định artifact cung cấp symbol và đưa nó vào compile classpath đúng cách.

### 13.3. Chạy class báo ClassNotFoundException

Nếu compile thành công nhưng chạy bằng class name thất bại, kiểm tra classpath root. Ví dụ, nếu file nằm ở:

~~~text
build/manual/classes/com/example/notes/Main.class
~~~

Classpath root phải là:

~~~text
build/manual/classes
~~~

Không đặt classpath ở thư mục package com/example/notes nếu đang gọi tên đầy đủ com.example.notes.Main.

### 13.4. Resource không tìm thấy

Nếu chương trình báo app.properties không có, kiểm tra:

- File nằm trong src/main/resources chưa?
- Bước copy resource đã chạy chưa?
- File đã nằm tại root classpath chưa?
- JAR có entry app.properties không?
- Tên resource có phân biệt chữ hoa/chữ thường đúng không?

Một resource được đặt nhầm dưới META-INF hoặc thư mục package sẽ cần tên resource tương ứng khi gọi getResourceAsStream.

### 13.5. JAR không có main manifest attribute

Lỗi này thường có nghĩa manifest không chứa Main-Class. Tạo lại JAR bằng --main-class hoặc manifest file có thuộc tính Main-Class đúng.

### 13.6. NoClassDefFoundError khi chạy

Ứng dụng có thể compile thành công nhưng thiếu dependency runtime. Compile classpath và runtime classpath là hai tập hợp có thể khác nhau. Kiểm tra dependency JAR đã được đóng gói hay được đặt trong thư mục lib và khai báo đúng chưa.

### 13.7. UnsupportedClassVersionError

Runtime JVM quá cũ so với bytecode class file. Kiểm tra:

~~~bash
java -version
javap -verbose -classpath build/manual/classes com.example.notes.Main
~~~

Tìm major version trong javap output và đối chiếu với Java runtime mục tiêu. Nếu cần hỗ trợ Java cũ hơn, compile bằng JDK phù hợp với --release và bảo đảm dependency cũng tương thích.

## 14. So sánh quy trình thủ công với Gradle và Maven

| Công việc | Thủ công | Gradle thường dùng | Maven thường dùng |
|---|---|---|---|
| Compile main source | javac | compileJava | compiler:compile trong compile phase |
| Copy resource | cp/Copy-Item | processResources | resources:resources |
| Compile test | javac với main output trên classpath | compileTestJava | testCompile |
| Chạy test | java gọi test harness | test | surefire:test trong test phase |
| Đóng gói JAR | jar | jar | jar:jar trong package phase |
| Tạo executable distribution | Tự chuẩn bị manifest/classpath/script | application plugin tasks | assembly/other packaging plugin tùy cấu hình |
| Dependency resolution | Tự tải và nối classpath | Dependency configurations/resolution | Dependencies/scopes/resolution |
| Clean | Xóa output directory | clean | clean |
| Publish library | Tự copy artifact và metadata | maven-publish | deploy lifecycle/plugin |
| Triển khai application | Tự copy/run trên môi trường đích | Không tự động chỉ vì build | Không tự động chỉ vì Maven deploy |

Bảng này mô tả ánh xạ khái niệm. Task/goal chính xác phụ thuộc plugin và cấu hình project. Gradle/Maven còn thực hiện dependency resolution, task ordering, cache, test reports, variant/metadata và nhiều bước khác.

### 14.1. Build tool không thay thế javac và jar

Gradle/Maven thường gọi compiler và archiver tương ứng hoặc API/tooling tích hợp để thực hiện công việc. Build tool bổ sung cách khai báo và điều phối công việc, không thay đổi bản chất output: compiler vẫn tạo class file và archive vẫn chứa class/resource/metadata.

### 14.2. Build tool giúp giảm thao tác dễ sai

Trong ví dụ thủ công, người thực hiện phải nhớ:

- Tất cả source cần compile.
- Compiler release và encoding.
- Nơi lưu class file.
- Resource cần copy.
- Compile classpath của test.
- Runtime classpath.
- Main-Class của JAR.
- Dependency ngoài nếu có.
- Thứ tự các bước.

Build tool lưu các quy tắc này trong build script/POM để mọi người dùng cùng một mô hình. Khi project lớn hơn, việc thực hiện bằng tay sẽ khó lặp lại và khó kiểm tra hơn.

## 15. Bản đồ quy trình dưới dạng bảng công việc

Có thể lập một build map cho ứng dụng nhỏ như sau:

| ID | Công việc | Input | Output | Điều kiện để chạy | Cách xác nhận |
|---|---|---|---|---|---|
| B1 | Kiểm tra JDK | PATH, JAVA_HOME, JDK | Compiler/runtime khả dụng | JDK cài đúng | java/javac --version |
| B2 | Tạo output directory | Project layout | classes, test-classes | Thư mục build có quyền ghi | Liệt kê directory |
| B3 | Compile main | Main source, release, encoding | Main .class | B1, B2 thành công | javac exit code, class files |
| B4 | Copy resources | Resource source | Resource output | B2 thành công | File tồn tại ở classpath root |
| B5 | Compile tests | Test source, main classes | Test .class | B3 thành công | Test class file tồn tại |
| B6 | Run tests | Main/test classes, resource | Pass/fail | B4, B5 thành công | Exit code và test output |
| B7 | Package | Main classes và resource | Application JAR | B3, B4 thành công; B6 pass theo policy | JAR tồn tại |
| B8 | Inspect archive | Application JAR | Entry list/manifest | B7 thành công | jar --list và Main-Class |
| B9 | Smoke run | JAR, runtime, arguments | Application output | B8 đúng | Exit code và output |

Thứ tự này thể hiện dependencies của công việc. Ví dụ, compile test phụ thuộc main classes; package cần main classes và resources; smoke run cần JAR đã đóng gói.

## 16. Tự động hóa nhẹ bằng script

Sau khi hiểu từng lệnh, có thể gom chúng thành script để tránh gõ lại. Đây vẫn là build thủ công ở mức đơn giản: script chỉ điều phối các lệnh JDK, không có dependency resolution hay incremental engine như build tool.

Ví dụ shell script build-manual.sh:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

OUT="build/manual"
CLASSES="$OUT/classes"
TEST_CLASSES="$OUT/test-classes"

rm -rf "$OUT"
mkdir -p "$CLASSES" "$TEST_CLASSES"

javac --release 17 -encoding UTF-8 \
  -d "$CLASSES" \
  src/main/java/com/example/notes/Note.java \
  src/main/java/com/example/notes/NoteFormatter.java \
  src/main/java/com/example/notes/AppConfig.java \
  src/main/java/com/example/notes/Main.java

cp -R src/main/resources/. "$CLASSES/"

javac --release 17 -encoding UTF-8 \
  -classpath "$CLASSES" \
  -d "$TEST_CLASSES" \
  src/test/java/com/example/notes/NoteFormatterTest.java

java -ea \
  -classpath "$CLASSES:$TEST_CLASSES" \
  com.example.notes.NoteFormatterTest

jar --create \
  --file "$OUT/notes-app.jar" \
  --main-class com.example.notes.Main \
  -C "$CLASSES" .

java -jar "$OUT/notes-app.jar" "Build script" "The manual pipeline completed."
~~~

Script dừng ngay khi một lệnh thất bại nhờ set -e. Các biến CLASSES và TEST_CLASSES giúp giảm lặp đường dẫn. Script cần quyền thực thi:

~~~bash
chmod +x build-manual.sh
./build-manual.sh
~~~

Đối với Windows, có thể tạo file build-manual.ps1 với các lệnh New-Item, Remove-Item, Copy-Item, javac, java và jar tương ứng. Classpath test cần dùng dấu chấm phẩy.

Không nên coi script ngắn này là build system hoàn chỉnh. Khi có hàng trăm source file, nhiều dependency, nhiều module, annotation processor, test framework, packaging variants và CI cache, Gradle/Maven cung cấp mô hình phù hợp hơn.

## 17. Các yếu tố làm quy trình thủ công khó mở rộng

### 17.1. Nhiều source file

Gõ từng đường dẫn source dễ bỏ sót file. Có thể dùng javac argument file. Ví dụ nội dung build/manual/sources.txt:

~~~text
--release
17
-encoding
UTF-8
-d
build/manual/classes
src/main/java/com/example/notes/Note.java
src/main/java/com/example/notes/NoteFormatter.java
src/main/java/com/example/notes/AppConfig.java
src/main/java/com/example/notes/Main.java
~~~

Sau đó chạy:

~~~bash
javac @build/manual/sources.txt
~~~

Argument file giúp quản lý danh sách dài và tránh giới hạn command line. Đường dẫn trong file phải được viết theo cú pháp javac argument file; nếu có khoảng trắng, cần quote đúng.

### 17.2. Nhiều dependency

Tự tải JAR và nối classpath gây khó khăn:

- Phải biết dependency trực tiếp và bắc cầu.
- Phải chọn version tương thích.
- Phải tránh duplicate class và xung đột version.
- Phải kiểm tra checksum/nguồn artifact.
- Phải phân biệt compile, runtime, test và processor path.

Build tool quản lý graph và metadata từ repository để giải quyết các việc này.

### 17.3. Nhiều module

Nếu module persistence phụ thuộc module domain, phải compile domain trước và đưa output vào classpath của persistence. Nếu application phụ thuộc cả hai, phải compile chúng trước application.

Task graph của build tool mô hình hóa quan hệ này và thực thi đúng thứ tự. Nếu làm thủ công, người thực hiện phải duy trì danh sách module và dependency order.

### 17.4. Incremental compilation và cache

Script trên xóa output và compile lại toàn bộ source. Với project lớn, điều này tốn thời gian. Build tool có thể theo dõi input/output, incremental compilation, up-to-date checks và build cache để giảm công việc lặp lại.

### 17.5. Cross-platform differences

Classpath separator, shell quoting, file permissions, path separator, line endings và cách copy resource khác nhau giữa Windows và Unix. Script thủ công cần xử lý các khác biệt này. Build tool giúp chuẩn hóa nhiều phần nhưng vẫn có thể phụ thuộc OS/architecture nếu project dùng native library hoặc task riêng.

## 18. Bài thực hành: tự vẽ build map

Sau khi chạy các lệnh, hãy tự điền bảng sau cho project của mình:

| Câu hỏi | Ghi nhận |
|---|---|
| JDK nào chạy compiler? | |
| Java release mục tiêu là bao nhiêu? | |
| Main source nằm ở đâu? | |
| Resource source nằm ở đâu? | |
| Main class output nằm ở đâu? | |
| Resource output nằm ở đâu? | |
| Test source cần classpath nào? | |
| Test output nằm ở đâu? | |
| JAR được tạo từ thư mục nào? | |
| Main-Class trong manifest là gì? | |
| Runtime dependency được cung cấp từ đâu? | |
| Command nào chạy ứng dụng? | |
| Output nào cần xóa khi clean? | |
| Bước nào cần chạy lại khi chỉ sửa một resource? | |

Bảng này là bản đồ vận hành của build. Khi có lỗi, có thể xác định lỗi xảy ra ở bước nào và output nào cần kiểm tra.

## 19. Bài tập mở rộng

### Bài 1: Thay đổi source

Thay nội dung NoteFormatter để đổi định dạng output. Chỉ compile lại main source, copy resource nếu cần, rồi chạy test. Ghi lại những file .class nào thay đổi.

### Bài 2: Thay đổi resource

Đổi app.name trong app.properties nhưng không thay Java source. Copy lại resource và chạy ứng dụng. Quan sát vì sao không cần gọi javac khi chỉ thay resource.

### Bài 3: Tạo lỗi resource

Đổi tên app.properties hoặc bỏ bước copy resource. Chạy ứng dụng và ghi thông báo lỗi. Sau đó khôi phục file và xác định bước build đã bị bỏ sót.

### Bài 4: Tạo lỗi manifest

Tạo JAR mà không chỉ định Main-Class. Chạy bằng java -jar, ghi lỗi và sửa manifest. So sánh cách chạy class trực tiếp bằng -cp với chạy archive bằng -jar.

### Bài 5: Tách test output

Thử chạy test mà bỏ test-classes khỏi classpath. Quan sát ClassNotFoundException. Sau đó thêm test-classes và chạy lại.

### Bài 6: Thêm dependency

Thêm một thư viện ngoài vào source, tải JAR từ repository tin cậy, compile với JAR trên classpath và chạy với cùng dependency. Ghi lại vì sao dependency cần có ở cả compile và runtime nếu source trực tiếp dùng nó.

### Bài 7: Kiểm tra release target

Thử compile với --release 17 và chạy trên Java 17. Sau đó compile bằng JDK mới hơn với release 17, xác nhận artifact vẫn chạy trên Java 17. Không dùng API chỉ có ở JDK mới hơn.

### Bài 8: Tạo clean build

Xóa build/manual, chạy lại toàn bộ quy trình và so sánh output. Xác nhận không có class/resource cũ nào làm ứng dụng chạy sai.

## 20. Khi nào nên chuyển từ build thủ công sang build tool?

Build thủ công phù hợp để học compiler, classpath, resource và archive; cũng hữu ích cho một thử nghiệm nhỏ. Khi dự án có nhiều dependency, module, test framework hoặc yêu cầu CI, việc tự quản lý command sẽ trở nên mong manh.

Nên dùng Gradle hoặc Maven khi cần:

- Dependency resolution từ repository và quản lý version.
- Compile/test/package theo lifecycle/task graph.
- Nhiều source set, module và variant.
- Annotation processor và generated source.
- Resource filtering và packaging phức tạp.
- Incremental build, cache và parallel execution.
- Plugin cho quality, test, publishing và reporting.
- Tích hợp CI và Wrapper để build nhất quán.
- Publish metadata cho consumer.
- Tạo application distribution hoặc container pipeline.

Build tool không làm mất các bước đã học. Nó mô tả các bước đó bằng cấu hình có thể chia sẻ và tự động thực thi theo dependency graph.

## 21. Nguyên tắc duy trì bản đồ build

- Mỗi bước phải có input và output xác định.
- Compile source và copy resource là hai công việc khác nhau.
- Test cần main output, test output và dependency phù hợp.
- JAR là archive; executable JAR cần Main-Class.
- Dependency compile và runtime phải được cung cấp đúng classpath.
- Không đưa test class hoặc runtime data vào application artifact nếu không có chủ đích.
- Clean chỉ xóa output được xác định, không xóa source hoặc cache dùng chung.
- Ghi rõ JDK/compiler và release target.
- Kiểm tra archive và manifest trước khi triển khai.
- Tách build artifact khỏi việc chạy ứng dụng trong môi trường đích.
- Khi có lỗi, xác định bước đầu tiên thất bại và kiểm tra input/output của bước đó.
- Chuyển sang Gradle/Maven khi dependency graph và quy trình vượt quá khả năng quản lý bằng script thủ công.

Sau bài thực hành, ta có thể đọc một build script Gradle hoặc Maven và nhận ra nó đang tự động hóa những thao tác nào: compile, resource processing, test, packaging, dependency resolution và execution. Bản đồ thủ công giúp giải thích vì sao một task cần chạy trước task khác, classpath được tạo từ đâu và artifact cuối cùng chứa những gì.
