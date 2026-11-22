# Đường dẫn có khoảng trắng và ký hiệu phân cách trên Windows, Linux khi dùng javac

Khi chạy `javac`, ba thứ rất dễ bị nhầm là **đường dẫn đến tệp/thư mục**, **cách shell chia đối số có khoảng trắng** và **ký hiệu nối nhiều mục trong classpath**. Một dự án Java có thể biên dịch tốt ở Linux nhưng thất bại trên Windows nếu dùng dấu hai chấm (`:`) để ngăn các thư mục classpath; một đường dẫn hợp lệ cũng có thể bị tách thành nhiều đối số nếu thiếu dấu nháy. Bài này hướng dẫn viết lệnh nhất quán, giải thích cơ chế và chẩn đoán lỗi cụ thể trên PowerShell, Command Prompt và Bash.

## 1. Phân biệt bốn loại ký hiệu

| Mục đích | Windows | Linux/Unix | Ví dụ |
| --- | --- | --- | --- |
| Phân cách **thành phần thư mục** trong đường dẫn | Thường là `\`; nhiều công cụ Java cũng chấp nhận `/` | `/` | Windows: `src\com\example\Main.java`; Linux: `src/com/example/Main.java` |
| Phân cách **các mục trong classpath** | `;` (dấu chấm phẩy) | `:` (dấu hai chấm) | Windows: `classes;lib/tool.jar`; Linux: `classes:lib/tool.jar` |
| Phân cách các thành phần **package Java** | `.` | `.` | `com.example.app.Main` |
| Chứa khoảng trắng trong một đối số shell | Bao **toàn bộ đối số** bằng nháy, thường dùng `"..."` | Bao **toàn bộ đối số** bằng nháy, thường dùng `"..."` | `-d "build output"` |

**Quy tắc quyết định:** `\` hoặc `/` tách thư mục; `;` hoặc `:` tách **các entry classpath**; `.` phân tách package. Không dùng một ký hiệu cho tất cả vai trò.

Trên Windows, dấu `:` trong `C:\Work Projects` là một phần của ổ đĩa (`C:`), không phải ký hiệu phân cách hai classpath entry. Trên Linux, `C:\Work Projects` không được hiểu như ổ C: của Windows. Các đối số đường dẫn phụ thuộc hệ điều hành nơi **chạy** chương trình, không phụ thuộc hệ điều hành nơi viết mã Java.

## 2. Shell chuyển đối số cho javac như thế nào?

Xét lệnh sai trên một terminal:

~~~text
javac -d build output source code/com/example/app/Main.java
~~~

Shell có thể tách nó thành các đối số khác nhau: `-d`, `build`, `output`, `source` và `code/com/example/app/Main.java`. `javac` không đoán được rằng `build output` phải là **một** thư mục hay `source code` là một phần của **một** đường dẫn. Hệ quả có thể là lỗi file not found, invalid flag hoặc đầu ra được ghi sai nơi.

Cách đúng:

~~~bash
javac -d "build output" "source code/com/example/app/Main.java"
~~~

Sau khi shell xử lý dấu nháy, `javac` nhận `build output` và `source code/com/example/app/Main.java` như hai đối số nguyên vẹn. **Dấu nháy phục vụ việc phân nhóm đối số**; nó không trở thành một phần của tên tệp.

Đặc biệt lưu ý:

- Tùy chọn `-d` và giá trị của nó là **hai đối số**. Viết `-d "build output"`; tương tự, `-cp "app classes;library classes"`.
- Với đường dẫn có khoảng trắng, đặt dấu nháy quanh **toàn bộ giá trị**, bao gồm mọi thư mục có khoảng trắng: `"C:\Java Projects\out classes"`.
- Đặt nháy cho đường dẫn ngay cả khi dự án hiện chưa có khoảng trắng cũng là thói quen an toàn, nhất là trong script.
- Dấu nháy **không sửa** đường dẫn sai, tệp không tồn tại hoặc classpath root bị nhầm. Kiểm tra thư mục làm việc và cấu trúc tệp riêng.
- Trên Bash, dấu `\` bên ngoài dấu nháy có thể là ký tự escape của shell. Trong PowerShell và CMD, `\` thường là dấu phân cách đường dẫn, không phải escape cho khoảng trắng. Đừng sao chép máy móc cú pháp escape từ Linux sang Windows.

Ví dụ Bash có thể viết `source\ code/com/example/app/Main.java`, nhưng dạng `"source code/com/example/app/Main.java"` rõ ràng và phù hợp hơn khi cần đọc các lệnh của nhiều hệ điều hành.

## 3. Ví dụ Java 17+ hoàn chỉnh: project root có khoảng trắng

Tạo một thư mục dự án tên `Java Projects` (bạn có thể chọn nơi chứa khác), rồi tạo đúng cây tệp sau ở bên trong:

~~~text
Java Projects/
└── source code/
    └── com/
        └── example/
            ├── lib/
            │   └── Greeter.java
            └── app/
                └── Main.java
~~~

**Tệp `source code/com/example/lib/Greeter.java`:**

~~~java
package com.example.lib;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Paths OK";
    }
}
~~~

**Tệp `source code/com/example/app/Main.java`:**

~~~java
package com.example.app;

import com.example.lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
        System.out.println(Main.class.getName());
    }
}
~~~

Ở đây:

- `Java Projects` là thư mục dự án có khoảng trắng; `source code` là source root cũng có khoảng trắng.
- `com/example/lib` và `com/example/app` phản ánh package ở trong mã nguồn.
- Tên đầy đủ của lớp chạy chính là `com.example.app.Main`.
- Thư mục đầu ra sẽ có tên `build output` để chủ ý kiểm chứng xử lý khoảng trắng.
- Hai tệp nguồn được liệt kê **tường minh**; không cần dựa vào việc shell có hỗ trợ wildcard `*.java` hay không.

### 3.1. Windows PowerShell

Mở PowerShell, chuyển đến thư mục `Java Projects`:

~~~powershell
Set-Location "C:\Work\Java Projects"
New-Item -ItemType Directory -Force "build output" | Out-Null
javac -encoding UTF-8 -d "build output" "source code\com\example\lib\Greeter.java" "source code\com\example\app\Main.java"
java -cp "build output" com.example.app.Main
~~~

`C:\Work\Java Projects` chỉ là **đường dẫn ví dụ**: nếu bạn tạo dự án ở nơi khác, hãy thay bằng đường dẫn thực tế. Mọi lệnh từ `New-Item` trở đi giả định PowerShell đang đứng tại **root của dự án**. `New-Item` tạo thư mục đầu ra khi chưa có; `Out-Null` ngăn kết quả tạo thư mục xuất hiện trên terminal.

### 3.2. Windows Command Prompt (cmd.exe)

Mở CMD và chuyển vào root của dự án:

~~~bat
cd /d "C:\Work\Java Projects"
if not exist "build output" mkdir "build output"
javac -encoding UTF-8 -d "build output" "source code\com\example\lib\Greeter.java" "source code\com\example\app\Main.java"
java -cp "build output" com.example.app.Main
~~~

`cd /d` đổi cả thư mục lẫn ổ đĩa khi cần. Dạng `if not exist ... mkdir ...` chỉ bảo đảm thư mục đầu ra tồn tại. Không đưa cú pháp PowerShell như `New-Item` vào CMD; hai shell có lệnh nội bộ khác nhau, còn `javac`/`java` là chương trình dòng lệnh chung.

### 3.3. Linux (Bash)

Mở terminal Bash, chuyển đến thư mục `Java Projects`:

~~~bash
cd "$HOME/Java Projects"
mkdir -p "build output"
javac -encoding UTF-8 -d "build output" "source code/com/example/lib/Greeter.java" "source code/com/example/app/Main.java"
java -cp "build output" com.example.app.Main
~~~

`$HOME/Java Projects` chỉ đúng nếu bạn đặt thư mục dự án trực tiếp trong home; hãy thay khi vị trí khác. Dấu nháy kép trong Bash vẫn cho phép mở rộng biến `$HOME` nhưng giữ khoảng trắng trong đường dẫn kết quả.

**Stdout của lệnh `java` trên cả ba shell:**

~~~text
Paths OK
com.example.app.Main
~~~

Lệnh `javac` biên dịch thành công thường **không in stdout**. Sau đó cây kết quả có dạng:

~~~text
Java Projects/
├── source code/
│   └── com/example/
│       ├── lib/Greeter.java
│       └── app/Main.java
└── build output/
    └── com/example/
        ├── lib/Greeter.class
        └── app/Main.class
~~~

`-d "build output"` bảo compiler đặt các `.class` ở dưới **thư mục đầu ra**, theo cấu trúc package. `-cp "build output"` bảo JVM coi `build output` là classpath root; JVM tự tìm `com/example/app/Main.class` từ tên `com.example.app.Main`. Vì vậy cách chạy sau **sai ý nghĩa**:

~~~text
java -cp "build output/com/example/app" Main
java -cp "build output" "com/example/app/Main.class"
~~~

Hãy dùng `java -cp "build output" com.example.app.Main`. Không gắn đuôi `.class` vào main class name.

## 4. Khi classpath có nhiều mục: Windows dùng ;, Linux dùng :

**Classpath** là một danh sách entry gồm thư mục chứa cây package hoặc tệp JAR/ZIP. Khi biên dịch, `javac` dùng compile classpath để tìm các kiểu đã biên dịch; khi chạy, `java` dùng runtime classpath để tìm các class cần thực thi. Mỗi entry là một **đường dẫn**; ký hiệu nối các entry do hệ điều hành quy định.

Giả sử ta biên dịch `Greeter` vào `library classes` và `Main` vào `app classes`. Cả hai đường dẫn đều có khoảng trắng.

**Windows PowerShell hoặc CMD** (đứng tại root dự án):

~~~bat
javac -encoding UTF-8 -d "library classes" "source code\com\example\lib\Greeter.java"
javac -encoding UTF-8 -cp "library classes" -d "app classes" "source code\com\example\app\Main.java"
java -cp "app classes;library classes" com.example.app.Main
~~~

**Linux Bash** (đứng tại root dự án):

~~~bash
javac -encoding UTF-8 -d "library classes" "source code/com/example/lib/Greeter.java"
javac -encoding UTF-8 -cp "library classes" -d "app classes" "source code/com/example/app/Main.java"
java -cp "app classes:library classes" com.example.app.Main
~~~

**Stdout giống nhau:**

~~~text
Paths OK
com.example.app.Main
~~~

Ở lần biên dịch thứ hai, compiler phải đọc `Greeter.class` trong `library classes`; vì vậy truyền `-cp "library classes"`. Khi chạy, JVM cần **cả** `Main.class` và `Greeter.class`, nên classpath phải chứa **hai** thư mục đầu ra. Đặt toàn bộ danh sách sau `-cp` trong **một cặp dấu nháy** để shell không tách nó tại khoảng trắng, và để PowerShell không diễn giải dấu `;` như dấu kết thúc lệnh.

### Vì sao không dùng dấu : cho classpath Windows?

Trong Windows:

~~~bat
java -cp "app classes;library classes" com.example.app.Main
~~~

Trong Linux:

~~~bash
java -cp "app classes:library classes" com.example.app.Main
~~~

Viết `"app classes:library classes"` trên Windows có thể khiến Java xử lý đó như **một** entry không tồn tại hoặc sai, thay vì hai thư mục. Viết `"app classes;library classes"` trên Linux cũng không tạo thành hai entry classpath. **Đặt nháy đúng vẫn không cứu được dấu phân cách classpath sai hệ điều hành.**

Có thể nhận biết dấu phân cách Java sử dụng trên máy đang chạy qua `java.io.File.pathSeparator` (dấu `;` hoặc `:`). Khi viết ứng dụng Java ghép classpath, dùng hằng số này thay vì hardcode dấu phân cách.

## 5. Đường dẫn đến JAR có khoảng trắng

Classpath entry cũng có thể là tệp JAR. Để kiểm chứng từ ví dụ trên, trước hết bảo đảm đã biên dịch `Greeter.java` vào `library classes` như mục 4.

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force "library jars" | Out-Null
jar --create --file "library jars\greetings lib.jar" -C "library classes" .
javac -encoding UTF-8 -cp "library jars\greetings lib.jar" -d "app classes" "source code\com\example\app\Main.java"
java -cp "app classes;library jars\greetings lib.jar" com.example.app.Main
~~~

**Linux Bash:**

~~~bash
mkdir -p "library jars"
jar --create --file "library jars/greetings lib.jar" -C "library classes" .
javac -encoding UTF-8 -cp "library jars/greetings lib.jar" -d "app classes" "source code/com/example/app/Main.java"
java -cp "app classes:library jars/greetings lib.jar" com.example.app.Main
~~~

Hai lệnh `jar` trên chạy từ root dự án và tạo JAR chứa `com/example/lib/Greeter.class`. `-C "library classes" .` yêu cầu công cụ `jar` chuyển thư mục nguồn nội bộ sang `library classes` rồi thêm toàn bộ nội dung hiện có vào gốc JAR; dấu `.` ở cuối là một đối số riêng. Tên file `greetings lib.jar` có khoảng trắng nên bắt buộc được bảo vệ bằng dấu nháy trong các shell này.

Kết quả khi chạy vẫn là:

~~~text
Paths OK
com.example.app.Main
~~~

Lưu ý: `-cp` nhận JAR cụ thể hoặc thư mục class; chỉ đặt `-cp "library jars"` sẽ **không** tự thêm mọi JAR trong thư mục ấy.

### Wildcard classpath lib/*

Java launcher và `javac` có hỗ trợ wildcard classpath theo dạng `some-directory/*`: nó bao gồm các JAR (và ZIP) phù hợp **trực tiếp trong thư mục đó**, không tự quét các thư mục lồng và không phải wildcard tùy ý như `lib/*.jar` hay `src/**/*.java`. Nếu thư mục tên `library jars` có khoảng trắng, hãy viết:

~~~bat
javac -cp "library jars/*" -d "app classes" "source code\com\example\app\Main.java"
java -cp "app classes;library jars/*" com.example.app.Main
~~~

Trên Linux, lệnh tương ứng dùng đường dẫn nguồn `/` và classpath separator `:`:

~~~bash
javac -cp "library jars/*" -d "app classes" "source code/com/example/app/Main.java"
java -cp "app classes:library jars/*" com.example.app.Main
~~~

Giữ wildcard **bên trong dấu nháy** để nó được công cụ Java xử lý ở vị trí classpath thay vì bị Bash mở rộng thành nhiều đối số. Wildcard classpath không đảm bảo thứ tự các JAR; nếu nhiều JAR chứa cùng tên class hoặc có xung đột dependency, cần quản lý thứ tự và dependency rõ ràng.

## 6. Dấu nháy và biến đường dẫn trong từng shell

| Tình huống | PowerShell | CMD | Bash |
| --- | --- | --- | --- |
| Path literal có khoảng trắng | `"C:\Java Projects\out"` | `"C:\Java Projects\out"` | `"/home/user/Java Projects/out"` |
| Home directory trong chuỗi có mở rộng biến | `"$env:USERPROFILE\Java Projects"` | `"%USERPROFILE%\Java Projects"` | `"$HOME/Java Projects"` |
| Dấu nháy đơn cho path literal | `'C:\Java Projects\out'` | **Không dùng** `'...'` làm nháy nhóm đối số CMD | `'/home/user/Java Projects/out'` |
| Dấu phân cách classpath | `;` | `;` | `:` |
| Dấu nối nhiều dòng shell | Backtick PowerShell (dễ lỗi nếu có khoảng trắng sau) | `^` tại cuối dòng | Backslash `\` tại cuối dòng |

- **PowerShell:** nháy kép cho phép biến `$env:USERPROFILE` được mở rộng; nháy đơn giữ nguyên ký tự `$`. PowerShell dùng backtick (`\u0060`) để escape, không dùng backslash làm escape tổng quát. Khi lệnh ngắn, viết **một dòng** để tránh lỗi nối dòng.
- **CMD:** dấu nháy kép gom đường dẫn chứa khoảng trắng. Nháy đơn không tương đương nháy kép. Biến môi trường ở dạng `%USERPROFILE%`; `;` không phải dấu phân tách câu lệnh CMD như PowerShell, nhưng vẫn cần nháy toàn bộ classpath có khoảng trắng.
- **Bash:** dấu nháy kép cho phép mở rộng `$HOME`; dấu nháy đơn ngăn mở rộng biến. Ngoài dấu nháy, khoảng trắng và nhiều ký hiệu như `*` có ý nghĩa đối với shell. Backslash có thể escape ký tự, nhưng dùng cặp nháy quanh cả đường dẫn thường dễ duy trì hơn.

Để tránh sự khác biệt trong ví dụ đa nền tảng, ưu tiên lệnh `javac`/`java` **một dòng**, chỉ dùng thư mục tương đối và quote các giá trị đường dẫn. Nếu triển khai script PowerShell, CMD và Bash riêng, hãy dùng cú pháp biến môi trường của đúng shell.

## 7. Đường dẫn tuyệt đối, tương đối và working directory

Một đường dẫn **tương đối** như `"source code/com/example/app/Main.java"` được giải quyết từ thư mục làm việc của tiến trình `javac`, không phải tự động từ thư mục chứa `javac.exe` hoặc từ vị trí tệp Java. Vì vậy lệnh giống nhau có thể thành công hoặc thất bại tùy bạn đang đứng ở đâu.

Ví dụ, khi root dự án là `C:\Work\Java Projects`:

~~~powershell
Set-Location "C:\Work\Java Projects"
javac -d "build output" "source code\com\example\app\Main.java"
~~~

Đoạn này chỉ minh họa cách giải quyết **đường dẫn tương đối**. Vì `Main.java` phụ thuộc `Greeter`, muốn biên dịch thành công cần biên dịch cả hai nguồn như mục 3, đặt `Greeter.class` lên compile classpath như mục 4, hoặc cấu hình source path phù hợp.

Nếu chạy lệnh từ thư mục khác, có thể dùng đường dẫn tuyệt đối:

~~~powershell
javac -d "C:\Work\Java Projects\build output" "C:\Work\Java Projects\source code\com\example\lib\Greeter.java" "C:\Work\Java Projects\source code\com\example\app\Main.java"
java -cp "C:\Work\Java Projects\build output" com.example.app.Main
~~~

Trên Linux (giả sử đặt dự án tại `/home/user/Java Projects`):

~~~bash
javac -d "/home/user/Java Projects/build output" "/home/user/Java Projects/source code/com/example/lib/Greeter.java" "/home/user/Java Projects/source code/com/example/app/Main.java"
java -cp "/home/user/Java Projects/build output" com.example.app.Main
~~~

Đừng thêm dấu `/` hoặc `\` thừa vào **giữa tên một thư mục có khoảng trắng**. Đường dẫn không phải chuỗi bất kỳ: mọi thành phần phải trùng với thư mục/tệp thực tế, bao gồm chữ hoa, chữ thường và tên file.

Linux thường phân biệt chữ hoa/chữ thường, nên `Main.java` và `main.java` có thể là hai tệp khác nhau. Windows mặc định thường không phân biệt chữ hoa/chữ thường trong truy cập tệp, nhưng code Java vẫn cần đúng tên kiểu/package; không dựa vào tính chất filesystem Windows để viết lệnh chạy được ở Linux.

## 8. -sourcepath, -d, -cp: ba đường dẫn khác vai trò

Trong lệnh `javac`, các tùy chọn liên quan nhưng không thay thế nhau:

| Tùy chọn | Ý nghĩa | Khi giá trị có khoảng trắng |
| --- | --- | --- |
| `-d` | Gốc thư mục xuất `.class` | `-d "build output"` |
| `-classpath` hoặc `-cp` | Tìm các class/JAR phụ thuộc khi biên dịch | Windows: `-cp "lib classes;external jars/tool.jar"` |
| `-sourcepath` | Vị trí tìm các tệp nguồn bổ sung để giải quyết kiểu | `-sourcepath "source code"` |
| `--module-path` | Tìm module khi dùng hệ thống module JPMS | Windows: `--module-path "mods;external mods"` |

Ví dụ, đứng tại root dự án:

~~~bash
javac -encoding UTF-8 -sourcepath "source code" -d "build output" "source code/com/example/app/Main.java"
~~~

Với layout ở mục 3, `javac` có thể tìm `source code/com/example/lib/Greeter.java` từ source path để biên dịch kiểu được tham chiếu. Trường hợp này phụ thuộc cấu hình các đường tìm kiếm và việc tệp nguồn thực sự tồn tại; nếu muốn kiểm soát chính xác các nguồn đầu vào, liệt kê tường minh cả hai file như mục 3.

Đường dẫn sau `-d` là **output root**, không phải package directory; đường dẫn sau `-sourcepath` là **source root**; các entry trong `-cp` là **classpath root hoặc tệp JAR**, không phải đường dẫn đến từng `Main.class`. Dấu phân cách của `--module-path` khi có nhiều entry cũng theo hệ điều hành như classpath, nhưng dùng JPMS còn cần `module-info.java` và các quan hệ `requires`/`exports` hợp lệ.

## 9. Viết Java code xử lý đường dẫn: khác với câu lệnh shell

Khi tạo đường dẫn **trong chương trình Java**, có thể sử dụng `java.nio.file.Path` thay vì tự nối `\`, `/` hoặc dấu phân cách hệ điều hành.

**Tệp `PathDemo.java`** (một chương trình độc lập):

~~~java
import java.io.File;
import java.nio.file.Path;

public final class PathDemo {
    public static void main(String[] args) {
        Path source = Path.of(
                "source code", "com", "example", "app", "Main.java"
        );
        System.out.println(source);
        System.out.println("pathSeparator=" + File.pathSeparator);
        System.out.println("fileSeparator=" + File.separator);
    }
}
~~~

Biên dịch, chạy trong thư mục chứa tệp:

~~~bash
javac PathDemo.java
java PathDemo
~~~

**Ví dụ output trên Linux:**

~~~text
source code/com/example/app/Main.java
pathSeparator=:
fileSeparator=/
~~~

**Ví dụ output trên Windows:**

~~~text
source code\com\example\app\Main.java
pathSeparator=;
fileSeparator=\
~~~

Hai output thể hiện quy tắc của hệ điều hành và file system mặc định. `File.separator` là dấu phân cách thư mục, còn `File.pathSeparator` là dấu nối **các entry** trong danh sách đường dẫn như classpath. `Path.of(...)` ghép các thành phần đường dẫn mà không cần tự mã hóa dấu ngăn thư mục.

**Quan trọng với chuỗi Java:** muốn viết đường dẫn có dấu backslash trực tiếp trong Java string literal phải escape thành `\\`. Ví dụ:

~~~java
Path windowsPath = Path.of("C:\\Work\\Java Projects\\source code");
~~~

Trong dòng code trên, `\\` trong mã nguồn Java biểu diễn **một** backslash trong giá trị chuỗi ở runtime. Điều này khác hẳn quy tắc đặt dấu nháy ở PowerShell/CMD. Trên Windows, dùng dấu `/` trong chuỗi đường dẫn Java nhiều khi cũng hoạt động, nhưng `Path.of` với các thành phần riêng thường rõ ràng hơn. Đừng dùng Windows absolute path này để giả định chương trình sẽ chạy tương tự trên Linux.

## 10. Các lỗi thực tế thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `error: file not found: ...` khi tên thư mục chứa khoảng trắng | Shell đã chia đường dẫn nguồn thành nhiều đối số; hoặc working directory sai | Quote nguyên đường dẫn nguồn; kiểm tra root dự án và sự tồn tại của file |
| `error: invalid flag: ...` | Đối số rời do thiếu quote hoặc thứ tự cờ sai | In lại/đọc lệnh; mỗi giá trị `-d`, `-cp`, `-sourcepath` là một đối số đầy đủ |
| `package com.example.lib does not exist` | Thiếu source/class dependency khi compile, hoặc compile classpath sai | Liệt kê cả hai `.java`; hoặc đưa `library classes`/JAR vào `-cp` |
| `cannot find symbol: Greeter` | Java compiler không resolve được kiểu được tham chiếu | Kiểm tra package, import, compile classpath, source path |
| `Could not find or load main class com.example.app.Main` | JVM không tìm main class từ classpath root, hoặc FQN sai | Dùng `java -cp "build output" com.example.app.Main`; kiểm tra đường dẫn `build output/com/example/app/Main.class` |
| `NoClassDefFoundError: com/example/lib/Greeter` | Main tìm được nhưng runtime không thấy dependency cần thiết | Bổ sung `library classes`/JAR vào **runtime classpath**; dùng đúng `;` hoặc `:` |
| Lệnh chạy Linux được, Windows không | Dùng dấu `:` nối classpath trên Windows; escape/variable của Bash; đường dẫn `/home/...` | Thay classpath separator bằng `;`, dùng cú pháp đường dẫn/shell Windows |
| Lệnh chạy PowerShell được, Bash không | Dùng dấu `;` nối classpath, đường dẫn Windows `C:\...` hoặc biến `$env:...` | Dùng `:`, `/` và biến `$HOME`/đường dẫn Linux |
| `Main.class` có mà `java Main` không chạy | Truyền simple name, sai package hoặc sai classpath root | Truyền FQN và gốc của cây `com/example/...` |
| Dùng `"lib"` trên classpath nhưng JAR nằm trong lib | Classpath trỏ thư mục nhưng không tự nạp JAR bên trong | Nêu tên JAR hoặc dùng `"lib/*"` đúng quy tắc wildcard |
| Dòng lệnh có `;` trong PowerShell bị chia thành hai lệnh | Classpath không được quote đầy đủ | Quote một chuỗi duy nhất: `-cp "app classes;library classes"` |
| Ví dụ dùng `*.java` không tìm được file trên một shell | Tùy shell/cách gọi chương trình, wildcard tệp nguồn không được mở rộng như dự kiến | Liệt kê các tệp `.java` cụ thể hoặc dùng build tool quản lý nguồn |

Cách chẩn đoán theo thứ tự:

1. Kiểm tra shell đang dùng: PowerShell, CMD hay Bash; xác minh `javac -version` và `java -version` thuộc JDK/JRE phù hợp.
2. Xác định working directory thực tế: PowerShell `Get-Location`; CMD `cd`; Bash `pwd`.
3. Xác nhận tên các tệp và thư mục có khoảng trắng, quote giá trị đầy đủ; không đoán đường dẫn.
4. Kiểm tra mỗi tùy chọn và giá trị: `-d` là một output root, `-cp` là một danh sách entry, các đường dẫn cuối là các tệp `.java`.
5. Đối chiếu dấu nối classpath: **Windows `;`**, **Linux `:`**; mỗi entry phải tồn tại hoặc phù hợp cơ chế wildcard.
6. Kiểm tra cây `.class` sau khi compile và main FQN; sau đó kiểm tra dependency có mặt ở cả compile classpath và runtime classpath nếu cần.

## 11. Bài tập thực hành có đáp án

### Bài 1: sửa đường dẫn có khoảng trắng

Lệnh Linux sau đang thiếu quote:

~~~bash
javac -d build output source code/com/example/app/Main.java
~~~

Sửa:

~~~bash
javac -d "build output" "source code/com/example/app/Main.java"
~~~

Nếu `Main` phụ thuộc `Greeter` trong ví dụ, cần kèm nguồn của `Greeter` hoặc compile classpath/source path phù hợp. Quote chỉ sửa việc phân nhóm đường dẫn.

### Bài 2: hai classpath entry trên hai hệ điều hành

Đường dẫn `classes first` và `libs/greeting tools.jar` đều có khoảng trắng. Viết runtime classpath đúng:

~~~bat
java -cp "classes first;libs\greeting tools.jar" com.example.app.Main
~~~

~~~bash
java -cp "classes first:libs/greeting tools.jar" com.example.app.Main
~~~

Các lệnh giả định các entry thực tế tồn tại và có các class cần thiết. Dấu nháy bao cả danh sách, không chèn khoảng trắng dư giữa dấu phân cách entry trừ khi nó thuộc tên đường dẫn thực.

### Bài 3: chọn đúng classpath root

Giả sử có tệp:

~~~text
build output/com/example/app/Main.class
~~~

Lựa chọn đúng là `java -cp "build output" com.example.app.Main`. Không dùng `"build output/com/example/app"` làm classpath root rồi truyền tên đầy đủ: gốc đó nằm quá sâu trong cây package.

### Bài 4: biến môi trường và dấu nháy

Với thư mục dự án trong home người dùng, viết đường dẫn đầu ra chứa khoảng trắng:

~~~powershell
javac -d "$env:USERPROFILE\Java Projects\build output" "$env:USERPROFILE\Java Projects\source code\com\example\lib\Greeter.java"
~~~

~~~bash
javac -d "$HOME/Java Projects/build output" "$HOME/Java Projects/source code/com/example/lib/Greeter.java"
~~~

Cả hai minh họa cách quote và mở rộng biến tương ứng từng shell; các lệnh chỉ biên dịch nguồn `Greeter.java` và giả định thư mục dự án đã có, đường dẫn đúng.

## Ghi nhớ

- Quote **toàn bộ giá trị đường dẫn có khoảng trắng**, nhất là sau `-d`, `-cp`, `-sourcepath` và tên tệp `.java`.
- **Windows classpath dùng `;`, Linux dùng `:`**. Dấu `\`/`/` là để đi qua thư mục, dấu `.` là để viết tên package; chúng có vai trò khác nhau.
- PowerShell, CMD và Bash có cú pháp biến môi trường/escape khác nhau; ưu tiên lệnh một dòng và quote toàn bộ đường dẫn để giảm lỗi.
- Chạy class bằng **tên đầy đủ** với **classpath root đúng**; compiler và JVM cần đúng những dependency tương ứng ở hai giai đoạn.
- Java code cần dùng `Path.of`, `File.separator` và `File.pathSeparator` cho mục đích tương ứng khi xây đường dẫn đa nền tảng.
