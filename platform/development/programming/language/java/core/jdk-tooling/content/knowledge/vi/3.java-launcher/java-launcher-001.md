# Lệnh `java`

`java` là lệnh khởi chạy ứng dụng Java. Nó được cung cấp trong thư mục `bin` của JDK và dùng để khởi tạo Java Virtual Machine (JVM), nạp lớp hoặc module cần chạy, rồi gọi điểm vào của ứng dụng. Khi đã có bytecode trong các tệp `.class` hoặc một JAR phù hợp, bạn dùng `java` để thực thi chương trình. Từ Java 11, lệnh này còn hỗ trợ chạy trực tiếp một tệp mã nguồn `.java` ở chế độ source-file.

Cần phân biệt ba việc: `javac` biên dịch mã nguồn thành bytecode; `java` khởi chạy chương trình; JVM thực thi bytecode. Lệnh `java` là giao diện dòng lệnh để cấu hình và khởi chạy JVM.

## 1. Kiểm tra lệnh `java`

Mở terminal hoặc Command Prompt và chạy:

~~~text
java --version
~~~

Lệnh in ra phiên bản Java runtime mà terminal hiện tại tìm thấy. Ví dụ một môi trường Java 17 có thể hiển thị thông tin tương tự:

~~~text
openjdk 17.0.x 202x-xx-xx
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...
~~~

Các số bản vá và dòng mô tả phụ thuộc nhà cung cấp và bản cập nhật đã cài.

Để xem cú pháp và các tùy chọn được hỗ trợ:

~~~text
java --help
java --help-extra
~~~

`--help` liệt kê các tùy chọn launcher thông dụng; `--help-extra` liệt kê thêm các tùy chọn nâng cao. Tùy chọn `-X` có thể hiển thị các tùy chọn `-X` riêng của bản JVM đang dùng:

~~~text
java -X
~~~

Danh sách tùy chọn phụ thuộc phiên bản và triển khai JVM. Khi cần xác nhận một cờ cấu hình, hãy xem kết quả trợ giúp hoặc tài liệu đúng phiên bản JDK đang chạy.

## 2. Cú pháp tổng quát

Java launcher hỗ trợ một số cách chỉ định chương trình cần chạy:

~~~text
java [options] mainclass [args ...]
java [options] -jar jarfile [args ...]
java [options] -m module[/mainclass] [args ...]
java [options] --module module[/mainclass] [args ...]
java [options] source-file [args ...]
~~~

Ý nghĩa:

- `options`: các tùy chọn dành cho Java launcher hoặc JVM, chẳng hạn classpath, module path, system property và cấu hình bộ nhớ.
- `mainclass`: tên đầy đủ của lớp chứa phương thức `main`, ví dụ `com.example.Main`.
- `jarfile`: đường dẫn đến tệp JAR có khai báo lớp khởi chạy trong manifest.
- `module`: tên module cần khởi chạy; có thể chỉ định thêm lớp chính sau dấu `/`.
- `source-file`: đường dẫn đến tệp `.java` khi dùng source-file mode.
- `args`: các đối số ứng dụng được chuyển cho chương trình.

**Vị trí của tùy chọn rất quan trọng.** Những tùy chọn dành cho launcher/JVM phải đặt trước tên lớp, `-jar`, `-m` hoặc tệp nguồn. Những giá trị đặt sau mục tiêu khởi chạy được xem là đối số của ứng dụng và xuất hiện trong `String[] args`.

Ví dụ:

~~~text
java -Dapp.mode=dev -Xmx512m -cp out com.example.Main input.txt --verbose
~~~

Trong lệnh này:

- `-Dapp.mode=dev` đặt system property cho JVM.
- `-Xmx512m` đặt giới hạn heap tối đa là 512 MB.
- `-cp out` chỉ định nơi tìm lớp.
- `com.example.Main` là lớp chính.
- `input.txt` và `--verbose` là đối số ứng dụng, không phải tùy chọn JVM.

Nếu đặt `-Xmx512m` sau `com.example.Main`, nó sẽ được chuyển cho chương trình như một đối số văn bản; JVM sẽ không dùng nó để cấu hình heap.

## 3. Chạy một lớp đã biên dịch

Đây là cách chạy phổ biến khi học Java hoặc khi chương trình đã được biên dịch thành class file.

Tạo tệp `Main.java`:

~~~java
import java.util.Arrays;

public class Main {
    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "default");
        System.out.println("Mode: " + mode);
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
~~~

Biên dịch vào thư mục `out`:

~~~text
javac -d out Main.java
~~~

Sau khi biên dịch, `out` chứa `Main.class`. Khởi chạy lớp:

~~~text
java -cp out Main
~~~

Kết quả:

~~~text
Mode: default
Arguments: []
~~~

Truyền system property và đối số ứng dụng:

~~~text
java -Dapp.mode=dev -cp out Main "hello world" 42
~~~

Kết quả:

~~~text
Mode: dev
Arguments: [hello world, 42]
~~~

Chuỗi `"hello world"` được đặt trong dấu ngoặc kép để shell truyền nó thành một đối số duy nhất. Cú pháp đặt dấu ngoặc kép có thể khác đôi chút giữa PowerShell, Command Prompt, Bash và Zsh; mục tiêu là để Java nhận đúng hai đối số: `hello world` và `42`.

Nếu lớp thuộc package, phải dùng tên đầy đủ của lớp. Ví dụ với `package com.example;` và tệp nằm trong `out/com/example/Main.class`, chạy:

~~~text
java -cp out com.example.Main
~~~

Tên lớp không bao gồm đuôi `.class`. Đường dẫn classpath là thư mục gốc của cây package, trong ví dụ này là `out`.

Khi không chỉ định `-cp` hoặc `-classpath`, Java launcher dùng classpath mặc định. Để lệnh chạy ổn định giữa các môi trường, nên chỉ rõ classpath khi ứng dụng phụ thuộc vào thư mục đầu ra hoặc thư viện bên ngoài.

## 4. Chạy một JAR bằng `-jar`

Một ứng dụng có thể được đóng gói trong tệp JAR. Để chạy JAR theo chế độ executable JAR, manifest của JAR phải có thuộc tính `Main-Class` chỉ đến lớp chính.

Ví dụ tạo JAR từ lớp `Main.class`:

~~~text
jar --create --file app.jar --main-class Main -C out .
~~~

Sau đó chạy:

~~~text
java -jar app.jar
~~~

Truyền đối số cho ứng dụng:

~~~text
java -jar app.jar --mode dev input.txt
~~~

Các đối số sau tên JAR được chuyển vào `main(String[] args)`.

Một vài điểm cần nhớ:

- `Main-Class` trong manifest phải là tên lớp đầy đủ nếu lớp nằm trong package, ví dụ `com.example.Main`.
- Khi dùng `java -jar`, JAR được chỉ định là nguồn chứa lớp và tài nguyên ứng dụng để khởi chạy.
- Các thiết lập classpath bên ngoài như `-cp` không được dùng để bổ sung classpath theo cách chạy lớp thông thường khi đã chọn chế độ `-jar`. Nếu ứng dụng cần thư viện phụ thuộc, hãy đóng gói chúng phù hợp, dùng manifest `Class-Path` theo cấu trúc triển khai, hoặc chọn cách khởi chạy khác.
- Nếu JAR không có `Main-Class`, launcher không biết lớp nào là điểm vào và sẽ báo lỗi.

Để xem manifest của JAR, có thể liệt kê nội dung bằng `jar` hoặc giải nén JAR và mở tệp `META-INF/MANIFEST.MF`. Manifest cần có dòng tương tự:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
~~~

## 5. Chạy ứng dụng theo module

Ứng dụng modular Java có thể được khởi chạy bằng module name. Tùy chọn `--module-path` (viết tắt `-p`) chỉ định nơi JVM tìm module.

Ví dụ:

~~~text
java --module-path mods -m com.example.app/com.example.Main
~~~

Trong đó:

- `mods` là thư mục chứa các module đã biên dịch hoặc module JAR.
- `com.example.app` là tên module được khai báo trong `module-info.java`.
- `com.example.Main` là lớp chính trong module.

Nếu module khai báo duy nhất một lớp chính trong module descriptor, có thể khởi chạy module mà không cần ghi lớp sau dấu `/`:

~~~text
java --module-path mods -m com.example.app
~~~

Tùy chọn `--module` tương đương `-m`. Tên module và tên lớp chính phải đúng với cấu trúc ứng dụng. Module path và classpath phục vụ hai cơ chế phân giải lớp khác nhau: classpath đặt lớp vào unnamed module, còn module path tìm các module có mô tả module.

Một số tùy chọn module thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--module-path`, `-p` | Chỉ định nơi tìm module |
| `--module`, `-m` | Chỉ định module cần khởi chạy |
| `--add-modules` | Bổ sung module gốc vào tập module được giải quyết |
| `--show-module-resolution` | Hiển thị thông tin phân giải module khi khởi chạy |

Chỉ sử dụng các tùy chọn mở rộng module khi cấu trúc ứng dụng yêu cầu; một ứng dụng classpath đơn giản không cần cấu hình module path.

## 6. Chạy trực tiếp tệp nguồn — source-file mode

Từ Java 11, Java launcher hỗ trợ chạy trực tiếp một tệp nguồn:

~~~text
java Main.java
~~~

Đây là source-file mode. Launcher biên dịch tệp nguồn để chạy chương trình mà không yêu cầu bạn gọi `javac` riêng trước. Cách này thuận tiện cho ví dụ nhỏ, script học tập và thử nghiệm nhanh.

Tệp `Main.java` vẫn phải có điểm vào hợp lệ cho phiên bản Java đang sử dụng. Có thể truyền đối số ứng dụng:

~~~text
java Main.java alpha "two words"
~~~

Trong source-file mode, các tùy chọn dành cho source launcher có thể đặt trước tên tệp. Ví dụ, chọn phiên bản ngôn ngữ cho mã nguồn:

~~~text
java --source 17 Main.java
~~~

Tùy chọn `--source` chọn mức ngôn ngữ nguồn cho source-file mode. Nó không phải cách thay thế tổng quát cho quá trình build của dự án. Với dự án nhiều lớp, dependency, kiểm thử và đóng gói, hãy dùng build tool hoặc quy trình `javac`/`jar` phù hợp.

## 7. Classpath: `-cp` và `--class-path`

Classpath là danh sách vị trí mà Java launcher/JVM tìm lớp và tài nguyên trong ứng dụng không chạy theo module. Có thể chỉ định bằng `-cp`, `-classpath` hoặc `--class-path`.

Ví dụ:

~~~text
java -cp out com.example.Main
~~~

Classpath có thể gồm nhiều thư mục hoặc JAR. Các phần tử được phân cách bằng ký tự phụ thuộc hệ điều hành:

| Hệ điều hành | Ký tự phân cách |
|---|---|
| Windows | Dấu chấm phẩy `;` |
| macOS/Linux | Dấu hai chấm `:` |

Ví dụ Windows:

~~~text
java -cp "out;lib/*" com.example.Main
~~~

Ví dụ macOS/Linux:

~~~text
java -cp "out:lib/*" com.example.Main
~~~

Mẫu `lib/*` cho phép đưa các tệp JAR trong thư mục `lib` vào classpath. Dấu `*` trong cú pháp classpath này được Java launcher xử lý; không nên giả định thứ tự các JAR được mở rộng là ổn định.

Các lỗi classpath thường bắt nguồn từ việc chỉ định sai thư mục gốc, thiếu JAR phụ thuộc hoặc nhầm tên lớp. Nếu lớp là `com.example.Main`, classpath phải trỏ đến thư mục chứa thư mục `com`, chứ không phải trỏ trực tiếp vào `com/example`.

Nếu cần kiểm tra đường dẫn hiện tại hoặc thư mục làm việc, hãy nhớ rằng đường dẫn tương đối được diễn giải từ **working directory** của tiến trình, không nhất thiết là thư mục chứa tệp `.java` hoặc JAR.

## 8. Tùy chọn JVM thường dùng

Các tùy chọn dưới đây được đặt trước tên lớp, `-jar`, `-m` hoặc tệp nguồn.

### 8.1. Đặt system property bằng `-D`

Cú pháp:

~~~text
-Dname=value
~~~

Ví dụ:

~~~text
java -Dapp.env=production -cp out Main
~~~

Ứng dụng đọc giá trị bằng:

~~~java
String env = System.getProperty("app.env");
~~~

System property phù hợp với cấu hình JVM hoặc ứng dụng cần đọc lúc chạy. Không dùng nó để lưu mật khẩu hoặc bí mật nhạy cảm trên dòng lệnh, vì tham số tiến trình có thể bị quan sát bởi công cụ quản trị hệ thống hoặc ghi vào log.

### 8.2. Cấu hình heap bằng `-Xms` và `-Xmx`

- `-Xms`: kích thước heap ban đầu.
- `-Xmx`: kích thước heap tối đa mà JVM được phép sử dụng.

Ví dụ:

~~~text
java -Xms256m -Xmx1g -cp out Main
~~~

Lệnh đặt heap ban đầu là 256 MB và heap tối đa là 1 GB. Đây là giới hạn heap, không phải giới hạn tổng bộ nhớ của tiến trình. JVM còn cần native memory, thread stack, metadata, code cache và các vùng khác.

Không nên chọn heap theo một con số cố định mà không đo. Hãy căn cứ vào dung lượng RAM, giới hạn container, số luồng, kích thước dữ liệu, GC và hành vi tải thực tế.

### 8.3. Bật assertion bằng `-ea`

Assertion trong Java thường bị tắt mặc định. Có thể bật bằng:

~~~text
java -ea -cp out Main
~~~

Khi bật, các câu lệnh `assert` trong chương trình được kiểm tra. Assertion hữu ích để kiểm tra giả định trong phát triển và kiểm thử. Không dùng assertion để thay thế validation đầu vào hoặc xử lý lỗi cần luôn hoạt động trong production.

### 8.4. Xem log và thông tin chẩn đoán

JDK hiện đại cung cấp unified logging. Ví dụ để xem thông tin nạp lớp:

~~~text
java -Xlog:class+load=info -cp out Main
~~~

Log có thể rất dài. Chỉ bật nhóm log cần thiết, và tránh để cấu hình chẩn đoán quá chi tiết trong môi trường có tải lớn nếu chưa đánh giá tác động.

Một số tùy chọn JVM phổ biến khác liên quan đến garbage collection, thread, JIT và dump khi lỗi. Tên và hành vi tùy chọn có thể thay đổi theo phiên bản hoặc bản triển khai; kiểm tra `java -X` và tài liệu JDK đang dùng trước khi áp dụng.

## 9. Truyền đối số cho chương trình

Mọi đối số nằm sau mục tiêu khởi chạy được chuyển vào phương thức `main` dưới dạng `String[] args`.

Ví dụ:

~~~text
java -cp out Main --file data.csv --limit 10
~~~

Với lệnh này, ứng dụng nhận bốn phần tử:

1. `--file`
2. `data.csv`
3. `--limit`
4. `10`

Launcher không tự phân tích ý nghĩa các cờ ứng dụng như `--file` hay `--limit`; chương trình hoặc thư viện CLI của ứng dụng phải xử lý chúng.

Nếu một giá trị chứa dấu cách, đặt nó trong dấu ngoặc kép theo cú pháp shell đang dùng:

~~~text
java -cp out Main "quarter one.csv"
~~~

Để truyền ký tự đặc biệt như dấu ngoặc kép, dấu gạch chéo ngược hoặc ký tự shell, phải escape theo shell. Java chỉ nhận các đối số sau khi shell đã phân tích dòng lệnh. Khi lỗi nằm ở cách đối số được chia tách, hãy kiểm tra giá trị `args` thực tế trước khi tìm lỗi trong logic ứng dụng.

## 10. Argument files và biến môi trường

### Argument files

Khi dòng lệnh có quá nhiều tùy chọn hoặc classpath dài, có thể lưu các tùy chọn vào tệp và truyền cho launcher bằng ký hiệu `@`.

Ví dụ tệp `java.args`:

~~~text
-Dapp.env=dev
-Xmx512m
--class-path
out;lib/*
~~~

Khởi chạy trên Windows:

~~~text
java @java.args com.example.Main
~~~

Trên macOS/Linux, dùng dấu `:` thay cho dấu `;` trong classpath của tệp. Argument file giúp rút gọn lệnh và tránh giới hạn độ dài command line của một số môi trường. Nội dung tệp được Java launcher phân tích theo cú pháp argument file; khi có khoảng trắng hoặc ký tự đặc biệt, hãy dùng quy tắc quoting/escaping được mô tả trong tài liệu launcher.

### Biến môi trường liên quan

Một số biến có thể ảnh hưởng đến lệnh `java`:

- `JDK_JAVA_OPTIONS`: chứa các tùy chọn được launcher thêm vào trước các tùy chọn trên command line. Hữu ích khi muốn áp dụng cấu hình chung cho các lần chạy trong một môi trường.
- `JAVA_TOOL_OPTIONS`: được JVM xem xét khi khởi tạo VM; có thể thêm tùy chọn cho các tiến trình khởi chạy JVM.
- `CLASSPATH`: có thể cung cấp classpath mặc định khi lệnh không chỉ định classpath rõ ràng.

Biến môi trường có thể khiến lệnh chạy khác với những gì nhìn thấy trên dòng lệnh. Khi điều tra hành vi bất ngờ, hãy kiểm tra các biến này và cấu hình của IDE/build tool. Ưu tiên truyền cấu hình cần thiết một cách tường minh trong script chạy để người khác có thể tái hiện.

## 11. Chẩn đoán các lỗi thường gặp

### `java` không được nhận diện

**Nguyên nhân:** JDK chưa được cài, thư mục `bin` không nằm trong PATH hoặc terminal đang dùng PATH cũ.

**Cách xử lý:** kiểm tra vị trí cài JDK, thêm thư mục `bin` phù hợp vào PATH và mở terminal mới. Trên Windows có thể dùng `where.exe java`; trên macOS/Linux có thể dùng `which -a java` để xem executable được tìm thấy.

### `Could not find or load main class`

**Nguyên nhân:** sai tên lớp, sai package hoặc classpath không chứa thư mục gốc của lớp.

**Cách xử lý:** kiểm tra tên đầy đủ của lớp, cấu trúc thư mục đầu ra và giá trị `-cp`. Ví dụ nếu class file ở `out/com/example/Main.class`, chạy `java -cp out com.example.Main`.

### `Main method not found`

**Nguyên nhân:** lớp được chỉ định không có điểm vào phù hợp với kiểu ứng dụng đang chạy hoặc khai báo `main` sai chữ ký.

**Cách xử lý:** với ứng dụng Java truyền thống, kiểm tra phương thức `public static void main(String[] args)` trong lớp chính và bảo đảm class file được biên dịch từ mã nguồn hiện tại.

### `Unable to access jarfile`

**Nguyên nhân:** đường dẫn JAR sai, tệp không tồn tại hoặc tiến trình không có quyền đọc tệp.

**Cách xử lý:** kiểm tra thư mục làm việc, tên tệp và đường dẫn. Nếu đường dẫn có dấu cách, đặt toàn bộ đường dẫn trong dấu ngoặc kép theo shell.

### `no main manifest attribute`

**Nguyên nhân:** JAR không có thuộc tính `Main-Class` trong manifest.

**Cách xử lý:** đóng gói lại JAR với `Main-Class` phù hợp hoặc chạy trực tiếp lớp chính bằng `java -cp ... package.Main`.

### `UnsupportedClassVersionError`

**Nguyên nhân:** class file được biên dịch bằng phiên bản Java mới hơn phiên bản runtime đang chạy.

**Cách xử lý:** dùng runtime tương thích hoặc biên dịch lại bằng `javac --release` theo phiên bản triển khai mục tiêu. Kiểm tra phiên bản thực tế bằng `java --version`, không chỉ kiểm tra phiên bản IDE.

### Ứng dụng không tìm thấy thư viện

**Nguyên nhân:** dependency không nằm trên classpath/module path, JAR phụ thuộc thiếu hoặc cấu hình manifest không đúng.

**Cách xử lý:** xác nhận thư viện được đóng gói hoặc được thêm vào đúng đường dẫn. Với ứng dụng modular, kiểm tra module path và khai báo `requires`; với ứng dụng classpath, kiểm tra `-cp` và các JAR cần thiết.

### JVM không nhận tùy chọn hoặc tùy chọn không có tác dụng

**Nguyên nhân:** tùy chọn đặt sau tên lớp/JAR, sai cú pháp hoặc không được hỗ trợ trong phiên bản đang dùng.

**Cách xử lý:** đặt tùy chọn JVM trước mục tiêu khởi chạy, kiểm tra `java --help`/`java -X` và tài liệu đúng phiên bản.

## 12. Quy trình chọn cách khởi chạy

| Tình huống | Lệnh nên dùng |
|---|---|
| Chạy một lớp đã biên dịch | `java -cp out com.example.Main` |
| Chạy JAR có `Main-Class` | `java -jar app.jar` |
| Chạy ứng dụng module | `java --module-path mods -m module/name.Main` |
| Thử nhanh một tệp nguồn Java 11+ | `java Main.java` |
| Truyền cấu hình cho JVM | `java -Dkey=value -Xmx512m ...` |
| Truyền đối số cho ứng dụng | Đặt chúng sau tên lớp, JAR, module hoặc tệp nguồn |

Khi chọn lệnh, hãy xác định ứng dụng được đóng gói theo kiểu classpath, executable JAR hay module. Sau đó đặt các tùy chọn JVM ở trước mục tiêu khởi chạy và đối số nghiệp vụ ở phía sau. Ghi lại working directory, phiên bản Java, classpath/module path và biến môi trường cần thiết để lệnh có thể chạy nhất quán ở máy khác.

`java` là điểm khởi đầu để thực thi ứng dụng Java: nó chọn chế độ khởi chạy, cấu hình JVM, tìm mã chương trình và chuyển đối số đến ứng dụng. Nắm vững cú pháp, thứ tự tùy chọn, classpath, JAR và module giúp bạn chạy chương trình chính xác cũng như chẩn đoán nhanh lỗi môi trường.