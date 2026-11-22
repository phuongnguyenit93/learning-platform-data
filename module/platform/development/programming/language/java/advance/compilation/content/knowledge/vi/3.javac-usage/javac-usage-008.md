# Thư mục làm việc, biến môi trường và cấu hình ngầm khi sử dụng javac

Cùng một bộ tệp \`.java\` và cùng dòng lệnh \`javac\`, chương trình có thể biên dịch thành công trên máy này nhưng báo thiếu tệp hoặc thiếu lớp trên máy khác. Nguyên nhân thường không nằm ở mã Java: **thư mục làm việc**, **biến môi trường**, **đường dẫn ngầm định** và **cách IDE/build tool gọi trình biên dịch** có thể làm thay đổi đầu vào thực tế.

Mục tiêu của bài là hiểu những yếu tố đó ảnh hưởng đến \`javac\` như thế nào, nhận diện sự khác biệt giữa giai đoạn biên dịch và chạy, và xây dựng lệnh biên dịch dễ tái lập. Ví dụ dùng JDK 17 trở lên; các đoạn có ghi rõ hệ điều hành hoặc shell tương ứng.

## 1. Bốn nguồn cấu hình quyết định một lệnh javac

Khi gõ:

~~~sh
javac -d out src/lab/Main.java
~~~

kết quả phụ thuộc vào nhiều thứ ngoài nội dung \`Main.java\`:

1. **Working directory (CWD, current working directory):** thư mục hiện tại của tiến trình \`javac\`. Các đường dẫn tương đối \`out\` và \`src/lab/Main.java\` được hiểu theo thư mục này.
2. **Tham số dòng lệnh:** \`-d\`, \`-classpath\`/\`-cp\`, \`-sourcepath\`, \`--module-path\`, \`-encoding\`, \`--release\` và các tùy chọn khác thay đổi cách compiler tìm, phân tích, ghi tệp.
3. **Biến môi trường:** \`PATH\` giúp shell chọn chương trình \`javac\`; \`CLASSPATH\` có thể cung cấp đường dẫn lớp mặc định; \`JDK_JAVAC_OPTIONS\` có thể đưa thêm tùy chọn vào lệnh \`javac\` khởi chạy qua launcher tương ứng.
4. **Ngữ cảnh gọi lệnh:** terminal, IDE, script CI hoặc Maven/Gradle có thể chọn JDK, thư mục làm việc, classpath và danh sách nguồn khác nhau.

Cần phân biệt ba khái niệm:

| Khái niệm | Dùng để làm gì? | Ví dụ |
|---|---|---|
| Source root | Gốc chứa cây package của các tệp nguồn | \`src\` chứa \`src/lab/Main.java\` |
| Compilation output root | Nơi \`javac\` ghi các tệp \`.class\` | \`-d out\` → \`out/lab/Main.class\` |
| Classpath | Các gốc thư mục/JAR chứa lớp đã biên dịch cần tìm | \`-cp out\` hoặc \`-cp libs/helper.jar\` |

Source root, output root và working directory **có thể là ba thư mục khác nhau**. Giá trị \`-d out\` không có nghĩa \`javac\` tự chuyển thư mục hiện tại sang \`out\`; việc biên dịch cũng không làm \`out\` tự động trở thành runtime classpath cho lệnh \`java\` tiếp theo.

## 2. Working directory: đường dẫn tương đối tính từ đâu?

Working directory là thuộc tính của tiến trình do shell hoặc chương trình gọi đặt khi khởi chạy. Nó **không tự động là** thư mục chứa tệp \`.java\`, tệp \`.class\`, thư mục cài JDK hay vị trí của tệp script.

Ví dụ cấu trúc:

~~~text
lab-project/
├── src/
│   └── lab/
│       ├── Message.java
│       └── Main.java
├── config/
│   └── flag.txt
├── compiler.args
└── out/                  # tạo trước khi biên dịch
~~~

Nếu terminal đang ở \`lab-project\`, đường dẫn \`src/lab/Main.java\` trỏ đến tệp nguồn. Nếu chuyển sang \`lab-project/src\` nhưng vẫn dùng chuỗi đường dẫn đó, trình biên dịch sẽ đi tìm \`lab-project/src/src/lab/Main.java\` và thường báo không thấy tệp.

Lệnh xem working directory:

~~~sh
# Linux/macOS: shell POSIX
pwd
~~~

~~~powershell
# Windows PowerShell
Get-Location
~~~

\`cd\` hoặc \`Set-Location\` thay đổi working directory của shell hiện tại; các tiến trình tạo sau đó thông thường kế thừa nó. Với IDE/CI, phải kiểm tra **working directory được cấu hình cho tác vụ**, vì mở một tệp nguồn trong editor không nhất thiết đổi thư mục làm việc.

### 2.1. Ví dụ biên dịch và chạy có thể kiểm chứng

Tạo \`src/lab/Message.java\`:

~~~java
package lab;

public final class Message {
    public static String text() {
        return "Xin chào javac";
    }
}
~~~

Tạo \`src/lab/Main.java\`:

~~~java
package lab;

import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
        System.out.println(
            Files.exists(Path.of("config", "flag.txt"))
        );
    }
}
~~~

Tạo tệp văn bản \`config/flag.txt\` với nội dung bất kỳ, chẳng hạn \`ok\`. Hai tệp Java và tệp cấu hình phải nằm đúng các đường dẫn trên. Mở terminal tại **\`lab-project/\`**, tạo \`out/\` nếu chưa tồn tại.

Trên Linux/macOS:

~~~sh
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
java -cp out lab.Main
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
java -cp out lab.Main
~~~

Đầu ra chính xác khi chạy từ \`lab-project/\`:

~~~text
Xin chào javac
true
~~~

Lệnh \`javac\` tạo \`out/lab/Message.class\` và \`out/lab/Main.class\`. \`--release 17\` buộc compiler kiểm tra mã/API theo Java 17. \`-encoding UTF-8\` xác định mã hóa để đọc nguồn; \`-d out\` chỉ nơi ghi \`.class\`.

Bây giờ di chuyển vào \`src\` và chạy **cùng bytecode** nhưng với classpath đúng theo vị trí mới:

~~~sh
cd src
java -cp ../out lab.Main
~~~

Kết quả:

~~~text
Xin chào javac
false
~~~

Dòng đầu vẫn đúng vì JVM tìm được \`lab.Main\` và \`lab.Message\` trong \`../out\`. Dòng thứ hai đổi thành \`false\` vì \`Path.of("config", "flag.txt")\` được phân giải theo **working directory của tiến trình Java lúc chạy**; lúc này nó tìm \`src/config/flag.txt\`. Đây là hành vi runtime, khác với lúc compiler tìm \`src/lab/Main.java\`.

Muốn chạy lại với kết quả \`true\`, trở về gốc dự án (\`cd ..\`) rồi dùng \`java -cp out lab.Main\`. Ví dụ đã được kiểm tra thực tế bằng \`javac --release 17\` và hai cách gọi \`java\` trên.

### 2.2. Các loại đường dẫn thường bị ảnh hưởng

| Đầu vào | Ví dụ | Thư mục gốc khi truyền đường dẫn tương đối |
|---|---|---|
| Tệp \`.java\` trên command line | \`src/lab/Main.java\` | Working directory của \`javac\` |
| Nơi ghi bytecode | \`-d out\` | Working directory; nên tạo \`out\` trước |
| Mục classpath | \`-cp libs/helper.jar\` | Working directory |
| Gốc source path | \`-sourcepath src\` | Working directory |
| Gốc module path | \`--module-path mods\` | Working directory |
| Đường dẫn tệp chứa tham số | \`@compiler.args\` | Working directory |
| Tệp do mã Java mở lúc chạy | \`Path.of("config/flag.txt")\` | Working directory của tiến trình **\`java\`** |

Đường dẫn tuyệt đối giảm sự phụ thuộc vào working directory nhưng thường khó di chuyển sang máy khác. Giải pháp phổ biến là luôn chạy từ một **gốc dự án xác định** và dựng các đường dẫn tương đối nhất quán.

## 3. Phân biệt classpath, sourcepath và vị trí đầu ra

\`javac\` xử lý cả nguồn \`.java\` lẫn các lớp \`.class\`/JAR có sẵn. Chúng thuộc những khái niệm khác nhau:

- \`-classpath\` (viết tắt \`-cp\`): nơi tìm các kiểu đã biên dịch và các dependency cần thiết trong quá trình biên dịch đối với cách dùng classpath.
- \`-sourcepath\`: nơi tìm tệp \`.java\` của các kiểu được tham chiếu nhưng không truyền trực tiếp ở command line.
- \`-d\`: nơi xuất tệp \`.class\` mới; không thay thế classpath, sourcepath hoặc working directory.
- \`--module-path\`: nơi tìm **named modules** đối với dự án dùng Java Platform Module System (JPMS); không đơn thuần thay thế \`-cp\`.

Với hai tệp nguồn ở phần 2, cách rõ ràng nhất là truyền đủ cả hai tệp trong một lần gọi:

~~~sh
javac --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
~~~

Bạn cũng có thể chỉ truyền \`Main.java\` và chỉ rõ gốc tìm các tệp phụ thuộc:

~~~sh
javac --release 17 -encoding UTF-8 -sourcepath src -d out src/lab/Main.java
~~~

Trong cấu trúc ví dụ, compiler có thể tìm \`src/lab/Message.java\` từ \`-sourcepath src\`. Nếu tự động tìm nguồn phụ thuộc theo mặc định, hành vi còn tùy cấu hình đường dẫn tìm kiếm và các \`.class\` hiện có; với dự án thực hành hãy chủ động chỉ định tập nguồn hoặc \`-sourcepath\`.

**Mặc định classpath:** khi không truyền \`-classpath\`/\`-cp\` hay \`--class-path\`, lệnh \`javac\` dùng giá trị \`CLASSPATH\` nếu môi trường đặt biến đó; nếu không có, classpath mặc định thường là working directory (\`.\`). Khi cung cấp classpath tường minh, giá trị \`CLASSPATH\` môi trường không tự cộng thêm vào. Đừng cho rằng classpath luôn bao gồm \`.\` khi đã đặt \`-cp\`; muốn dùng thư mục hiện tại, hãy thêm nó một cách tường minh.

\`javac\` cũng có thể sử dụng classpath để tìm nguồn khi không có sourcepath tường minh, tùy chế độ tìm kiếm. Trong các dự án cần kết quả tái lập, việc quy định rõ nguồn và classpath đáng tin hơn dựa vào hành vi tự tìm kiếm.

**Lúc chạy:** \`java -cp out lab.Main\` phải có \`out\` trên runtime classpath. Compiler thành công không đảm bảo JVM tìm đủ các thư viện lúc chạy. Ngoài ra, dùng một phiên bản JAR khi compile rồi một phiên bản khác khi chạy có thể gây \`NoClassDefFoundError\` hoặc \`NoSuchMethodError\`.

## 4. Những biến môi trường liên quan đến javac

### 4.1. \`PATH\`: shell chọn bản javac nào?

Trên máy có nhiều JDK, lệnh \`javac\` được shell tìm qua \`PATH\` (hoặc quy tắc phân giải lệnh của shell). Do đó terminal, IDE và CI có thể vô tình dùng các compiler khác phiên bản.

Kiểm tra Linux/macOS:

~~~sh
command -v javac
javac -version
java -version
printf '%s\n' "$JAVA_HOME"
~~~

Kiểm tra Windows PowerShell:

~~~powershell
Get-Command javac
javac -version
java -version
$env:JAVA_HOME
~~~

\`JAVA_HOME\` là quy ước phổ biến để công cụ build/script chọn một JDK, nhưng **đặt \`JAVA_HOME\` đơn thuần không bảo đảm shell đang dùng \`$JAVA_HOME/bin/javac\`**. Phải đối chiếu lệnh thực tế trong \`PATH\` hoặc gọi đường dẫn JDK mong muốn một cách tường minh. Đối với JDK 9 trở lên, có thể dùng \`--release 17\` để nhắm mục tiêu Java 17; tùy chọn này không tự thay đổi JDK đang chạy trình biên dịch.

### 4.2. \`CLASSPATH\`: đường dẫn phụ thuộc bị ẩn

\`CLASSPATH\` có thể làm một lệnh biên dịch không có \`-cp\` chạy được trên máy này nhưng không chạy được trên máy khác. Đường dẫn được phân cách bằng \`:\` trên Linux/macOS và \`;\` trên Windows; phần tử dạng \`deps\` là đường dẫn tương đối nên vẫn phụ thuộc working directory.

Giả sử có thêm:

~~~text
lab-project/
├── deps-src/
│   └── addon/
│       └── Marker.java
├── deps/                    # các .class đã biên dịch
├── app-src/
│   └── app/
│       └── Runner.java
└── app-out/
~~~

Tệp \`deps-src/addon/Marker.java\`:

~~~java
package addon;

public final class Marker {
    public static String text() {
        return "dependency";
    }
}
~~~

Tệp \`app-src/app/Runner.java\`:

~~~java
package app;

import addon.Marker;

public final class Runner {
    public static void main(String[] args) {
        System.out.println(Marker.text());
    }
}
~~~

Tại \`lab-project/\`, tạo \`deps/\` và \`app-out/\`, rồi biên dịch thư viện trước:

~~~sh
javac --release 17 -d deps deps-src/addon/Marker.java
~~~

Lúc này \`deps/addon/Marker.class\` đã tồn tại. Trên Linux/macOS, một lệnh tạm thời đặt \`CLASSPATH\` chỉ cho tiến trình compiler là:

~~~sh
CLASSPATH=deps javac --release 17 -d app-out app-src/app/Runner.java
java -cp "app-out:deps" app.Runner
~~~

Trên Windows PowerShell, có thể đặt biến chỉ trong phiên terminal thử nghiệm:

~~~powershell
$env:CLASSPATH = "deps"
javac --release 17 -d app-out app-src/app/Runner.java
java -cp "app-out;deps" app.Runner
~~~

Sau thử nghiệm hãy khôi phục giá trị \`CLASSPATH\` ban đầu (hoặc đóng terminal thử nghiệm). Cả hai cách chạy đều in:

~~~text
dependency
~~~

Nếu \`CLASSPATH\` không chứa \`deps\`, và \`javac\` không được cung cấp classpath/source khác chứa \`addon.Marker\`, việc biên dịch \`Runner.java\` không tìm thấy package \`addon\`. Nếu thêm \`-cp app-out\` vào lệnh \`javac\`, classpath tường minh đó sẽ thay thế \`CLASSPATH=deps\`; muốn đủ dependency phải nêu cả các mục cần thiết.

Cách ổn định hơn là **truyền classpath rõ ràng** thay vì dựa vào biến môi trường:

~~~sh
# Linux/macOS
javac --release 17 -cp deps -d app-out app-src/app/Runner.java
java -cp "app-out:deps" app.Runner
~~~

~~~powershell
# Windows PowerShell
javac --release 17 -cp deps -d app-out app-src/app/Runner.java
java -cp "app-out;deps" app.Runner
~~~

Khi dùng \`-cp\`/classpath, nhớ rằng \`java\` và \`javac\` là **hai tiến trình với hai giai đoạn tìm dependency khác nhau**. Phải cấu hình đầy đủ ở mỗi giai đoạn cần thiết.

### 4.3. \`JDK_JAVAC_OPTIONS\`: tham số tự đưa vào javac

Từ các JDK hiện đại (Java 9 trở lên), launcher \`javac\` hỗ trợ biến \`JDK_JAVAC_OPTIONS\`. Nội dung biến được xử lý như các đối số bổ sung **được đưa vào trước đối số trên command line**, theo cú pháp token/quote phù hợp. Ví dụ shell POSIX:

~~~sh
JDK_JAVAC_OPTIONS="-Xlint:deprecation" javac --release 17 -d out src/lab/Message.java src/lab/Main.java
~~~

PowerShell:

~~~powershell
$env:JDK_JAVAC_OPTIONS = "-Xlint:deprecation"
javac --release 17 -d out src/lab/Message.java src/lab/Main.java
~~~

Cờ \`-Xlint:deprecation\` yêu cầu cảnh báo về cách dùng API đã bị đánh dấu deprecated. Nếu mã không dùng API thuộc diện cảnh báo, lệnh có thể không in thêm cảnh báo nào. Không phải mọi tùy chọn đều hợp lệ trong \`JDK_JAVAC_OPTIONS\`; nếu biến chứa tùy chọn sai, lệnh có thể thất bại dù phần bạn gõ ở terminal không có lỗi. Khôi phục biến sau khi thử nghiệm.

**Điểm cần nhớ:** lệnh nhìn thấy trên terminal chưa chắc là toàn bộ tập tùy chọn compiler nhận. Với lỗi khó hiểu, kiểm tra \`JDK_JAVAC_OPTIONS\` trước khi kết luận rằng \`javac\` bỏ qua hoặc tự thêm một cờ.

### 4.4. \`JAVA_TOOL_OPTIONS\`, \`JAVA_HOME\` và biến môi trường khác

\`JAVA_TOOL_OPTIONS\` tác động đến các JVM được khởi tạo qua cơ chế launcher/VM phù hợp, thường dùng cho tùy chọn JVM, theo dõi hoặc instrumentation. Nó **không đồng nghĩa** với \`JDK_JAVAC_OPTIONS\` và không nên dùng để truyền các cờ ngôn ngữ như \`--release\` cho \`javac\`. Cấu hình JVM do môi trường chèn vào có thể ảnh hưởng lúc khởi chạy công cụ hoặc làm công cụ thất bại.

Các biến như \`LANG\`, \`LC_ALL\` (trên hệ thống hỗ trợ) có thể ảnh hưởng locale/hiển thị thông báo; hệ thống file và encoding mặc định cũng khác nhau theo môi trường. Khi nguồn có ký tự tiếng Việt, luôn cân nhắc \`-encoding UTF-8\`; khi cần kiểm tra API/ngôn ngữ đích, dùng \`--release\` phù hợp. Đừng dựa vào một cảnh báo hoặc chuỗi lỗi có cùng ngôn ngữ trên mọi máy.

Để tránh phơi lộ dữ liệu nhạy cảm, chỉ kiểm tra các biến liên quan đến biên dịch như \`PATH\`, \`JAVA_HOME\`, \`CLASSPATH\`, \`JDK_JAVAC_OPTIONS\`; không đăng nguyên bản toàn bộ environment lên issue/log công khai.

## 5. @argfile và những cấu hình “nằm ngoài” dòng lệnh

Với nhiều tệp và tham số, \`javac\` có thể đọc đối số từ một argument file. Trong ví dụ ở phần 2, tạo \`compiler.args\` tại gốc \`lab-project/\` với nội dung:

~~~text
--release 17
-encoding UTF-8
-d out
src/lab/Message.java
src/lab/Main.java
~~~

Từ \`lab-project/\`, chạy:

~~~sh
javac @compiler.args
java -cp out lab.Main
~~~

Lệnh biên dịch tương đương việc viết trực tiếp các đối số tương ứng vào terminal. Tên tệp đứng sau \`@\` và các đường dẫn tương đối được cung cấp trong argument file vẫn cần được hiểu theo **working directory của lần gọi**; không tự lấy vị trí chứa argument file làm gốc của mọi đường dẫn. Nếu đổi vị trí chạy, hãy cập nhật đường dẫn hoặc vào đúng gốc dự án trước.

Argument file giúp tránh dòng lệnh quá dài và có thể được công cụ build tạo ra. Khi đọc log, một lệnh ngắn như \`javac @compiler.args\` không cho thấy ngay danh sách nguồn và flags; phải kiểm tra nội dung argument file đang dùng. Đối số có khoảng trắng cần đặt trong dấu nháy theo cú pháp argument file hỗ trợ; không giả định argument file là shell script, bởi \`javac\` không thực thi các lệnh shell ở trong đó.

Một số tùy chọn cũng có thể do \`JDK_JAVAC_OPTIONS\`, script wrapper hay IDE bổ sung. Khi nghi ngờ, kiểm tra cả lệnh **sau khi công cụ build tạo ra**, working directory của task, biến môi trường và nội dung argfile tương ứng.

## 6. Cấu hình ngầm trong IDE, Maven, Gradle và CI

Các công cụ này quản lý quá trình biên dịch giúp bạn, nhưng cũng che giấu nhiều chi tiết mà lúc viết \`javac\` trực tiếp cần chỉ rõ:

- **IDE:** chọn Project SDK/JDK, compiler output và classpath theo module/project. Working directory của cấu hình **Run** có thể khác thư mục gốc project hay thư mục của cấu hình **Build**. Chạy nút Run trong IDE không bảo đảm giống \`java -cp out ...\` ở terminal.
- **Maven:** plugin compiler dùng source roots, dependencies và các thuộc tính build của dự án; phiên bản JDK/toolchain có thể do cấu hình quyết định. Không nên xem lệnh \`javac\` thủ công là bản sao chính xác của Maven.
- **Gradle:** tác vụ \`JavaCompile\` dùng source sets, \`classpath\`, \`destinationDirectory\` và Java toolchain theo cấu hình build. Gradle daemon có thể tồn tại qua nhiều lệnh; khi chẩn đoán thay đổi JDK hoặc environment, phải kiểm tra môi trường/tùy chọn thực tế mà tiến trình build nhận.
- **CI/container:** checkout directory, bước \`working-directory\`, môi trường container, cache và JDK cài đặt có thể khác máy cá nhân.

Nếu terminal chạy thành công nhưng IDE/CI lỗi, so sánh lần lượt: **phiên bản \`javac\` → working directory → danh sách tệp nguồn → compile classpath → sourcepath/module path → output root → biến môi trường và argument file**. Đừng sửa mã Java trước khi xác nhận hai quá trình thật sự có cùng đầu vào.

## 7. Các lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Điều cần kiểm tra | Hướng sửa |
|---|---|---|
| \`error: file not found: src/lab/Main.java\` | Đang đứng trong \`lab-project/\` hay trong \`src/\`? Tên tệp/hoa thường đúng không? | Dùng \`pwd\`/\`Get-Location\`, vào đúng thư mục trước khi gọi \`javac\`. |
| \`package addon does not exist\`, \`cannot find symbol\` | Classpath/sourcepath và danh sách nguồn có \`addon.Marker\` không? Có ngầm dựa vào \`CLASSPATH\` không? | Dùng \`-cp deps\` tường minh, hoặc cung cấp tệp nguồn \`Marker.java\`. |
| Chạy được trên máy A nhưng lỗi trên máy B | Hai máy có khác \`PATH\`, \`JAVA_HOME\`, \`CLASSPATH\`, \`JDK_JAVAC_OPTIONS\`, \`@argfile\` không? | Ghi rõ JDK đích, source root, classpath, encoding, flags. |
| \`javac\` báo tùy chọn lạ dù command line không ghi | Biến \`JDK_JAVAC_OPTIONS\`, wrapper script hoặc IDE có chèn flags? | Kiểm tra và tạm bỏ cấu hình chèn; chạy lại trong môi trường kiểm soát. |
| \`Could not find or load main class lab.Main\` | Lệnh \`java\` có \`out\` trên runtime classpath? Đúng tên package chưa? | Chạy \`java -cp out lab.Main\` từ gốc dự án; kiểm tra vị trí \`.class\`. |
| Chạy từ IDE đọc được file, chạy từ terminal không đọc được | Runtime working directory khác nhau? | Dùng đường dẫn cấu hình đã xác định, hoặc chuyển working directory vào đúng gốc. |
| Biên dịch thành công nhưng khi chạy báo thiếu lớp | Runtime classpath/module path thiếu dependency | Khai báo thư viện cho cả compile và run, tránh dùng JAR khác phiên bản. |
| Thông báo lỗi ký tự nguồn hoặc chữ tiếng Việt sai | Encoding của tệp \`.java\` và tùy chọn compiler khác nhau | Lưu nguồn UTF-8 phù hợp và dùng \`-encoding UTF-8\`; tránh BOM khi JDK/compiler không chấp nhận. |
| Thư mục \`out\` chứa bytecode cũ, kết quả khó hiểu | Output được dùng lại giữa nhiều đợt biên dịch với cấu hình khác | Dùng thư mục output riêng, chạy clean build có chủ đích, xác minh dependency. |

Khi cần xem đường dẫn mà \`javac\` thực sự tìm/đọc, dùng \`-verbose\` trong một lượt chẩn đoán:

~~~sh
javac -verbose --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
~~~

Tùy chọn này in rất nhiều thông tin về nguồn/lớp được đọc hoặc ghi và làm log dài. Nó là công cụ **chẩn đoán**, không nên bật thường trực chỉ để dạy ví dụ nhỏ. Dùng \`javac --help\` và \`javac -X\` để tra các tùy chọn có trong JDK đang cài; tránh cho rằng mọi JDK đều hỗ trợ đúng cùng tập cờ.

## 8. Quy trình làm cho kết quả biên dịch dễ tái lập

Một quy trình rõ ràng cho bài thực hành nhiều tệp:

1. Chọn một **gốc dự án cố định**; đầu script/build task kiểm tra hoặc chuyển đến gốc đó.
2. Chọn và kiểm tra **JDK cụ thể** bằng \`javac -version\`; dùng \`--release\` theo phiên bản Java mục tiêu khi phù hợp.
3. Xác định chính xác danh sách nguồn hoặc source root; bảo đảm package khớp cấu trúc thư mục.
4. Chọn output root riêng (\`out\`, \`build/classes\`…) và tạo nó trước khi biên dịch.
5. Chỉ rõ compile classpath, module path và sourcepath khi cần; không phụ thuộc vào \`CLASSPATH\` vô tình tồn tại trên máy.
6. Chỉ rõ \`-encoding UTF-8\` nếu dự án lưu nguồn theo UTF-8.
7. Kiểm tra biến \`JDK_JAVAC_OPTIONS\`, argfile và wrapper khi compiler nhận đối số không như dự kiến.
8. Cấu hình runtime classpath và runtime working directory riêng; xác nhận cả \`java\` chạy đúng, không chỉ \`javac\` báo thành công.
9. Trong CI và dự án thực tế, đưa các lựa chọn vào cấu hình build có kiểm soát phiên bản (Gradle/Maven), tránh cấu hình phụ thuộc máy cá nhân.

Một kiểm tra nhanh trước khi xử lý lỗi:

~~~text
Mình đang đứng ở đâu?        -> pwd / Get-Location
Mình dùng javac nào?         -> command -v javac / Get-Command javac
Bản javac bao nhiêu?         -> javac -version
Nguồn .java nằm ở đâu?       -> đường dẫn tương đối từ CWD
Dependency ở đâu?            -> -cp, -sourcepath, --module-path
.class sẽ được ghi ở đâu?    -> -d
Có tùy chọn ẩn không?        -> CLASSPATH, JDK_JAVAC_OPTIONS, @argfile
Khi chạy Java có gì khác?    -> java -cp, runtime CWD, dependency
~~~

## 9. Câu hỏi tự luyện

1. Bạn đang đứng trong \`lab-project/src\`; vì sao lệnh \`javac -d out src/lab/Main.java\` có thể thất bại dù \`Main.java\` vẫn tồn tại? Sửa bằng hai cách: đổi working directory, hoặc đổi các đường dẫn tương đối.
2. Trên máy có \`CLASSPATH=deps\`, vì sao \`javac -d app-out app-src/app/Runner.java\` có thể thành công nhưng lệnh tương tự trên CI không thành công? Thêm \`-cp deps\` có lợi ích gì?
3. Với \`java -cp ../out lab.Main\` chạy từ thư mục \`src\`, vì sao phép kiểm tra tồn tại \`config/flag.txt\` cho \`false\` trong khi không cần biên dịch lại một byte nào?
4. \`JDK_JAVAC_OPTIONS\` khác \`JAVA_HOME\` và \`CLASSPATH\` về vai trò thế nào? Vì sao kiểm tra riêng từng biến giúp tìm ra lỗi khó tái hiện?
5. Nếu \`compiler.args\` ở thư mục \`config/\` nhưng trong đó ghi \`src/lab/Main.java\`, bạn cần đứng ở thư mục nào để đường dẫn nguồn có nghĩa như trong ví dụ? Điều gì xảy ra nếu xem vị trí của argfile là gốc đường dẫn một cách sai lầm?
6. Tại sao \`javac -d out\` thành công không bảo đảm \`java lab.Main\` chạy đúng? Lựa chọn classpath nào cần thêm cho runtime?

Đích cuối cùng là giải thích được **toàn bộ cấu hình hữu hiệu** của một lần biên dịch: chương trình \`javac\` nào được chọn, nó bắt đầu ở thư mục nào, nhận đối số tường minh và ngầm nào, tìm nguồn/dependency ở đâu, ghi output vào đâu, và JVM sau đó tìm/chạy các lớp trong ngữ cảnh nào. Khi những yếu tố này được ghi rõ, kết quả biên dịch ổn định và lỗi khác biệt giữa máy, IDE, terminal hay CI trở nên dễ truy vết.
