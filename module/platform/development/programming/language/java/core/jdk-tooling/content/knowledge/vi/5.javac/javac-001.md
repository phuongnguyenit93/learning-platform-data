# Lệnh javac

`javac` là trình biên dịch Java đi kèm JDK. Lệnh này đọc mã nguồn `.java`, kiểm tra cú pháp và kiểu dữ liệu, sau đó tạo bytecode trong các tệp `.class` để JVM có thể nạp và thực thi. Khi làm việc với Java, cần phân biệt ba công việc:

- `javac` biên dịch mã nguồn thành bytecode.
- `java` khởi chạy chương trình trên JVM.
- JDK cung cấp cả hai lệnh cùng các công cụ phát triển khác.

Một lệnh biên dịch thành công thường không in thông báo nào; các tệp `.class` được tạo ở thư mục đầu ra. Nếu có lỗi, `javac` hiển thị vị trí và mô tả để người phát triển sửa mã nguồn hoặc cấu hình biên dịch.

## 1. Kiểm tra javac và cú pháp lệnh

Trước khi biên dịch, xác nhận máy có trình biên dịch:

```sh
javac --version
```

Ví dụ, với JDK 21, kết quả có dạng:

```text
javac 21
```

Cách hiển thị số bản vá có thể khác giữa các nhà phân phối. Nếu hệ thống báo không tìm thấy lệnh, kiểm tra JDK đã được cài đầy đủ và thư mục `bin` của JDK có trong `PATH`.

Cú pháp tổng quát:

```text
javac [options] source-files
javac [options] @argfiles
```

Trong đó:

- `options` là các tùy chọn điều khiển phiên bản ngôn ngữ, thư mục đầu ra, classpath, encoding, cảnh báo và các bước xử lý khác.
- `source-files` là một hoặc nhiều tệp mã nguồn Java cần biên dịch.
- `@argfiles` là tệp văn bản chứa danh sách tùy chọn và tên tệp nguồn, hữu ích khi danh sách đầu vào dài.

Có thể xem trợ giúp của phiên bản JDK đang cài:

```sh
javac --help
javac -X
javac --help-extra
```

`--help` liệt kê các tùy chọn thông dụng; `-X` và `--help-extra` hiển thị thêm các tùy chọn nâng cao. Một số tùy chọn bắt đầu bằng `-X` có thể thay đổi giữa các phiên bản JDK, vì vậy hãy kiểm tra trợ giúp của chính JDK đang dùng.

## 2. Biên dịch một chương trình Java đơn giản

Tạo tệp `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
```

Mở Terminal tại thư mục chứa tệp và chạy:

```sh
javac Hello.java
```

Nếu không có lỗi, trình biên dịch tạo tệp `Hello.class` trong thư mục hiện tại. Chạy chương trình bằng lệnh `java`:

```sh
java Hello
```

Kết quả:

```text
Hello, Java!
```

Lưu ý:

- Khi gọi `javac`, truyền tên tệp nguồn có phần mở rộng `.java`.
- Khi gọi `java`, truyền tên lớp đầy đủ (ở ví dụ này là `Hello`), không thêm `.java` hoặc `.class`.
- Tên tệp phải khớp chính xác với tên lớp `public` cấp cao nhất. Lớp `public class Hello` phải nằm trong `Hello.java`.
- Nếu lệnh biên dịch thành công nhưng không thấy `.class`, kiểm tra thư mục làm việc và tùy chọn `-d` nếu có.

## 3. Biên dịch mã nguồn có package

Trong dự án thực tế, lớp thường nằm trong package. Ví dụ cấu trúc nguồn:

```text
project/
└── src/
    └── com/
        └── example/
            └── Hello.java
```

Nội dung `src/com/example/Hello.java`:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from package!");
    }
}
```

Từ thư mục `project`, biên dịch với tùy chọn `-d`:

```sh
javac -d out src/com/example/Hello.java
```

`-d out` chỉ định thư mục gốc chứa các tệp `.class`. Trình biên dịch tự tạo các thư mục con tương ứng với package:

```text
project/
├── src/
│   └── com/example/Hello.java
└── out/
    └── com/
        └── example/
            └── Hello.class
```

Chạy lớp bằng tên đầy đủ và đặt thư mục đầu ra lên classpath:

```sh
java -cp out com.example.Hello
```

Kết quả:

```text
Hello from package!
```

Tên package trong mã nguồn, cấu trúc thư mục và tên lớp đầy đủ phải nhất quán. Với dự án có package, nên dùng `-d` để giữ mã nguồn và bytecode ở hai vùng riêng biệt. Nếu bỏ `-d`, các tệp `.class` thường được đặt cạnh tệp nguồn tương ứng.

## 4. Biên dịch nhiều tệp và các lớp phụ thuộc

Một chương trình có thể gồm nhiều lớp. Ví dụ có hai tệp:

`src/com/example/Greeter.java`:

```java
package com.example;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

`src/com/example/Main.java`:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java"));
    }
}
```

Biên dịch cả hai tệp trong cùng một lệnh:

```sh
javac -d out src/com/example/Greeter.java src/com/example/Main.java
```

Chạy lớp có phương thức `main`:

```sh
java -cp out com.example.Main
```

Kết quả:

```text
Hello, Java!
```

Có thể truyền nhiều đường dẫn nguồn cho một lần gọi `javac`. Trình biên dịch kiểm tra quan hệ giữa các lớp trong cùng lượt biên dịch, nhờ đó tránh lỗi do biên dịch thiếu một lớp phụ thuộc trực tiếp.

Nếu mã nguồn phụ thuộc vào các lớp đã được biên dịch trước hoặc các thư viện JAR, cần khai báo chúng trên classpath. Nếu muốn trình biên dịch tìm thêm mã nguồn phụ thuộc trong một thư mục riêng, có thể chỉ định `-sourcepath`. Không nên nhầm thư mục chứa mã nguồn với thư mục chứa bytecode hoặc thư viện.

## 5. Các tùy chọn javac thường dùng

| Tùy chọn | Công dụng |
|---|---|
| `-d <dir>` | Chọn thư mục chứa tệp `.class` được tạo ra |
| `-cp <path>`, `-classpath <path>`, `--class-path <path>` | Khai báo classpath để tìm lớp và thư viện phụ thuộc khi biên dịch |
| `-sourcepath <path>`, `--source-path <path>` | Khai báo nơi tìm mã nguồn phụ thuộc |
| `--release <version>` | Biên dịch theo phiên bản nền tảng Java đã chọn, gồm quy tắc ngôn ngữ, định dạng bytecode và API công khai tương ứng |
| `-source <version>` | Chọn phiên bản cú pháp/ngôn ngữ nguồn |
| `-target <version>` | Chọn phiên bản định dạng bytecode đầu ra |
| `-encoding <encoding>` | Chọn encoding đọc tệp nguồn, ví dụ `UTF-8` |
| `-g` | Sinh thông tin gỡ lỗi |
| `-g:none` | Không sinh thông tin gỡ lỗi |
| `-parameters` | Lưu tên tham số phương thức để có thể truy vấn bằng reflection |
| `-Xlint:all` | Bật các nhóm cảnh báo của trình biên dịch |
| `-Werror` | Xem cảnh báo được phát hiện là lỗi và làm lượt biên dịch thất bại |
| `-verbose` | In thêm thông tin về hoạt động biên dịch và nạp lớp |
| `-proc:none` | Tắt annotation processing |
| `-processor <class>` | Chỉ định annotation processor cần chạy |
| `-processorpath <path>` | Khai báo nơi tìm annotation processor |
| `-s <dir>` | Chọn thư mục chứa mã nguồn được annotation processor sinh ra |
| `@<file>` | Đọc tùy chọn và tên tệp nguồn từ argument file |

Tên viết tắt và tên dài của classpath có cùng mục đích. Có thể dùng tên dài trong script để dễ đọc, hoặc tên ngắn trong lệnh tương tác.

### 5.1. Chọn thư mục đầu ra với -d

Ví dụ:

```sh
javac -d build/classes src/com/example/Main.java
```

Các lớp được biên dịch sẽ nằm trong `build/classes`, theo cấu trúc package. Thư mục đầu ra có thể được tạo nếu chưa tồn tại. Khi chạy chương trình, phải đưa đúng thư mục này vào classpath:

```sh
java -cp build/classes com.example.Main
```

`-d` không tự đóng gói chương trình thành JAR. Để tạo JAR, dùng công cụ `jar` sau khi biên dịch.

### 5.2. Dùng thư viện ngoài với classpath

Giả sử dự án dùng một thư viện ở `lib/example.jar`. Khi biên dịch, thêm thư viện vào classpath:

```sh
javac -cp "lib/example.jar" -d out src/com/example/Main.java
```

Nếu có nhiều JAR trong thư mục `lib`, có thể dùng wildcard:

```sh
javac -cp "lib/*" -d out src/com/example/Main.java
```

Classpath là danh sách các thư mục và tệp JAR mà công cụ tìm kiếm lớp. Ký tự phân tách các phần tử khác nhau theo hệ điều hành:

| Hệ điều hành | Ký tự phân tách classpath |
|---|---|
| Windows | Dấu chấm phẩy `;` |
| macOS và Linux | Dấu hai chấm `:` |

Ví dụ, khi cần hai mục classpath:

```text
Windows:       out;lib/example.jar
macOS/Linux:   out:lib/example.jar
```

Phải cấu hình classpath cho cả giai đoạn biên dịch và giai đoạn chạy khi chương trình cần thư viện đó. `javac -cp` chỉ ảnh hưởng đến lượt biên dịch hiện tại; nó không tự lưu thư viện vào cấu hình chạy của JVM. Ví dụ trên macOS/Linux:

```sh
java -cp "out:lib/*" com.example.Main
```

Trên Windows:

```powershell
java -cp "out;lib/*" com.example.Main
```

Khi đường dẫn có khoảng trắng, đặt đường dẫn trong dấu ngoặc kép để shell truyền nó thành một đối số. Không dùng dấu phân tách của Linux trên Windows hoặc ngược lại.

### 5.3. Chọn phiên bản nền tảng bằng --release

Một JDK mới có thể biên dịch mã nguồn cho một phiên bản Java cũ hơn. Ví dụ, dùng JDK 21 để biên dịch theo nền tảng Java 17:

```sh
javac --release 17 -d out src/com/example/Main.java
```

`--release 17` kiểm soát đồng thời:

- Cú pháp ngôn ngữ Java được phép sử dụng.
- Phiên bản bytecode được tạo ra.
- Tập API Java SE công khai có sẵn ở phiên bản 17.

Đây là cách thường được khuyến nghị khi cần bảo đảm chương trình tương thích với một phiên bản Java mục tiêu. Nếu chỉ dùng `-source 17 -target 17`, trình biên dịch có thể vẫn nhìn thấy API của JDK mới hơn và tạo mã tham chiếu đến API không tồn tại trên Java 17.

Không thể dùng `--release` cùng lúc với `-source` hoặc `-target`. Phiên bản đích cũng không thể mới hơn JDK đang chạy trình biên dịch. Ví dụ, JDK 17 không thể biên dịch với `--release 21`.

Nếu dự án cần tính năng preview, phải bật preview khi biên dịch bằng đúng JDK của phiên bản đó, ví dụ `--enable-preview --release 21`; khi chạy cũng cần bật `--enable-preview`. Tính năng preview không phải API ổn định để mặc định sử dụng trong ứng dụng thông thường.

### 5.4. Chọn encoding cho mã nguồn

Để tránh kết quả khác nhau giữa các máy có cấu hình mặc định khác nhau, có thể chỉ định UTF-8:

```sh
javac -encoding UTF-8 -d out src/com/example/Main.java
```

Tùy chọn này quy định cách trình biên dịch đọc nội dung tệp `.java`. Nó không thay đổi encoding mà chương trình dùng khi đọc hoặc ghi dữ liệu lúc chạy. Nếu mã nguồn chứa tiếng Việt mà encoding khai báo không khớp với encoding thật của tệp, có thể xuất hiện lỗi hoặc ký tự bị sai.

### 5.5. Bật cảnh báo và thông tin gỡ lỗi

Khi muốn phát hiện thêm vấn đề tiềm ẩn:

```sh
javac -Xlint:all -d out src/com/example/Main.java
```

Để coi cảnh báo là lỗi trong một quy trình build nghiêm ngặt:

```sh
javac -Xlint:all -Werror -d out src/com/example/Main.java
```

Không nên tắt cảnh báo hàng loạt chỉ để làm cho build có vẻ thành công. Hãy đọc loại cảnh báo, xác định mã nguồn hoặc thư viện gây ra cảnh báo, rồi sửa hoặc cấu hình ngoại lệ có chủ đích.

Tùy chọn `-g` sinh thông tin hỗ trợ debugger, chẳng hạn thông tin dòng nguồn và biến cục bộ. `-parameters` lưu tên tham số phương thức trong bytecode; điều này hữu ích với framework hoặc thư viện dùng reflection để đọc tên tham số. Hai tùy chọn có mục đích khác nhau.

## 6. Biên dịch dự án dùng Java Module System

Dự án modular có tệp `module-info.java` khai báo tên module và các quan hệ như `requires`, `exports`. Khi biên dịch, có thể dùng `--module-path` để chỉ định nơi tìm các module phụ thuộc.

Ví dụ cấu trúc:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Tệp `src/com.example.app/module-info.java`:

```java
module com.example.app {
}
```

Tệp `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Modular Java");
    }
}
```

Biên dịch module:

```sh
javac --module-source-path src -d out -m com.example.app
```

Chạy module:

```sh
java --module-path out -m com.example.app/com.example.app.Main
```

Kết quả:

```text
Modular Java
```

Khi module phụ thuộc vào module khác, thêm vị trí module phụ thuộc bằng `--module-path`. Classpath và module path có vai trò khác nhau: classpath chủ yếu tìm lớp trên classpath không định danh module, còn module path tìm các module đã được định nghĩa. Không chuyển tất cả thư viện sang module path một cách máy móc; cần hiểu thư viện đó là modular JAR, automatic module hay thư viện classpath.

## 7. Dùng argument file cho danh sách đầu vào dài

Khi dự án có nhiều tệp nguồn hoặc lệnh quá dài, lưu đối số vào một tệp, ví dụ `sources.txt`:

```text
-d
out
-encoding
UTF-8
--release
21
src/com/example/Greeter.java
src/com/example/Main.java
```

Chạy:

```sh
javac @sources.txt
```

Trình biên dịch đọc các tùy chọn và tên tệp từ argument file. Mỗi dòng ở ví dụ trên là một đối số riêng. Với đường dẫn chứa khoảng trắng, đặt đường dẫn trong dấu ngoặc kép theo quy tắc argument file. Đây là cách thuận tiện để giữ lệnh build gọn và tránh vượt giới hạn độ dài dòng lệnh của một số môi trường.

Argument file chỉ chứa đối số cho trình biên dịch; nó không thay thế cấu hình build đầy đủ của dự án. Với dự án Gradle hoặc Maven, nên để build tool quản lý danh sách nguồn, thư viện và các tùy chọn compiler thay vì duy trì một file lệnh thủ công song song.

## 8. Annotation processing

Trong quá trình biên dịch, `javac` có thể chạy annotation processor để đọc annotation và sinh thêm mã nguồn hoặc tài nguyên. Một số thư viện sử dụng cơ chế này để sinh lớp hỗ trợ, metadata hoặc mã truy cập dữ liệu.

Các tùy chọn thường gặp:

- `-processorpath`: chỉ định nơi chứa processor.
- `-processor`: chọn processor cụ thể.
- `-s`: chọn thư mục nhận các tệp nguồn được sinh ra.
- `-proc:none`: tắt annotation processing.

Ví dụ khung lệnh khi có processor trong JAR:

```sh
javac -processorpath "lib/processor.jar" -s generated-sources -d out src/com/example/Main.java
```

Lệnh này giả định processor và các thư viện cần thiết đã được cung cấp đầy đủ. Nếu dự án dùng processor, hãy theo cấu hình chính thức của thư viện hoặc build tool. Tắt annotation processing có thể làm build thất bại nếu mã nguồn cần các lớp được sinh ra.

## 9. Lệnh biên dịch mẫu cho dự án nhỏ

Với dự án Java 21 có cấu trúc `src` và muốn đặt bytecode ở `out`, một lệnh có thể dùng là:

```sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/com/example/Greeter.java src/com/example/Main.java
```

Sau khi biên dịch, chạy:

```sh
java -cp out com.example.Main
```

Nếu dự án phụ thuộc vào JAR, bổ sung classpath cho cả hai giai đoạn. Trên Windows dùng dấu chấm phẩy; trên macOS/Linux dùng dấu hai chấm. Nếu dự án lớn có nhiều source set, dependency, annotation processor hoặc module, nên dùng Gradle/Maven để quản lý cấu hình và gọi `javac` với đúng tham số được build tool tạo ra.

Trong dự án Gradle, `javac` thường được gọi bởi Java compiler task. Chạy `./gradlew compileJava` (Windows: `gradlew.bat compileJava`) để build tool áp dụng toolchain, dependency và tùy chọn compiler của dự án. Không tự thay thế lệnh build của dự án bằng một lệnh `javac` rút gọn nếu dự án cần cấu hình bổ sung.

## 10. Phân tích lỗi thường gặp

| Thông báo hoặc hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `javac: command not found` hoặc `javac is not recognized` | Chưa cài JDK hoặc thư mục `bin` chưa có trong `PATH` | Kiểm tra cài đặt JDK, `JAVA_HOME` và `PATH`; mở Terminal mới sau khi đổi biến |
| `error: file not found: ...` | Đường dẫn nguồn sai hoặc thư mục làm việc hiện tại không đúng | Kiểm tra vị trí tệp, tên tệp và đường dẫn tương đối; thử dùng đường dẫn tuyệt đối |
| `error: no source files` | Không truyền tệp nguồn hoặc argument file không chứa đầu vào hợp lệ | Kiểm tra đối số sau `javac` và nội dung argument file |
| `cannot find symbol` | Tên lớp, biến hoặc phương thức không tồn tại trong phạm vi; thiếu import hoặc thiếu dependency | Kiểm tra chính tả, khai báo, import, phiên bản API và classpath |
| `package ... does not exist` | Thiếu thư viện hoặc package không nằm trong source path/classpath | Thêm JAR hoặc thư mục đúng vào `-cp`, hoặc cấu hình source path |
| `class X is public, should be declared in a file named X.java` | Tên tệp không khớp với tên lớp public | Đổi tên tệp cho khớp chính xác với lớp public |
| `invalid source release` hoặc phiên bản release không được hỗ trợ | JDK đang chạy javac cũ hơn phiên bản đích | Cài hoặc chọn JDK đủ mới, hoặc dùng `--release` không vượt phiên bản JDK |
| `duplicate class` | Cùng một lớp được khai báo hoặc đưa vào biên dịch nhiều lần từ các nguồn xung đột | Kiểm tra package, source set, classpath và các tệp nguồn trùng |
| `module not found` | Module phụ thuộc không có trên module path hoặc tên module sai | Kiểm tra `--module-path`, tên module và cách đóng gói thư viện |
| Biên dịch thành công nhưng JVM không tìm thấy main class | Classpath khi chạy thiếu thư mục đầu ra hoặc dùng sai tên lớp | Dùng đúng `-cp` và tên lớp đầy đủ, ví dụ `com.example.Main` |
| `UnsupportedClassVersionError` khi chạy | JVM chạy ứng dụng cũ hơn phiên bản bytecode đã biên dịch | Chạy bằng JDK/JRE đủ mới hoặc biên dịch bằng `--release` phù hợp |

Có thể tăng mức chi tiết khi điều tra:

```sh
javac -Xdiags:verbose -Xlint:all -verbose -d out src/com/example/Main.java
```

`-Xdiags:verbose` hiển thị chẩn đoán chi tiết hơn; `-verbose` in thêm hoạt động của trình biên dịch. Không cần bật verbose thường xuyên trong build thông thường vì log có thể rất dài.

Khi gặp lỗi, đọc thông báo đầu tiên và vị trí dòng/cột mà trình biên dịch nêu ra. Các lỗi phía sau đôi khi chỉ là hệ quả của một lỗi cú pháp hoặc khai báo trước đó. Sửa lỗi gốc rồi biên dịch lại để tránh xử lý các thông báo dây chuyền không còn tồn tại.

## 11. Kiểm tra kết quả sau khi biên dịch

Sau khi `javac` chạy thành công, kiểm tra:

1. Mã thoát của lệnh là thành công và không có lỗi biên dịch.
2. Các tệp `.class` nằm đúng thư mục đầu ra.
3. Tên package và cấu trúc thư mục khớp nhau.
4. Classpath hoặc module path chứa đủ dependency.
5. Chương trình chạy bằng đúng phiên bản JVM mục tiêu.

Với ví dụ ở phần 4, có thể xem danh sách bytecode bằng lệnh hệ điều hành hoặc dùng công cụ `javap` để xem thông tin lớp:

```sh
javap -classpath out com.example.Main
```

`javap` là công cụ đi kèm JDK dùng để đọc cấu trúc lớp đã biên dịch, chẳng hạn chữ ký phương thức và bytecode. Nó hữu ích khi muốn xác nhận lớp được tạo ra hoặc điều tra khác biệt giữa mã nguồn và bytecode.

## 12. Phân biệt javac với các công cụ liên quan

| Công cụ | Vai trò |
|---|---|
| `javac` | Biên dịch mã nguồn `.java` thành bytecode `.class` |
| `java` | Khởi chạy ứng dụng hoặc lớp Java trên JVM |
| `jar` | Tạo, xem hoặc thao tác với tệp JAR |
| `javap` | Phân tích cấu trúc lớp và bytecode |
| `javadoc` | Sinh tài liệu API từ comment và khai báo trong mã nguồn |
| `jshell` | Môi trường tương tác để thử biểu thức và câu lệnh Java |

Một quy trình thủ công cơ bản thường là: dùng `javac` để biên dịch, `java` để chạy, rồi dùng `jar` nếu cần đóng gói. Trong dự án thực tế, Gradle hoặc Maven thường điều phối các bước này để bảo đảm cùng một cấu hình được sử dụng trên máy lập trình viên và trong CI.

## 13. Checklist khi sử dụng javac

- Đã chọn đúng JDK và kiểm tra `javac --version`.
- Đường dẫn đến mọi tệp nguồn đều chính xác.
- Tên tệp khớp với tên lớp public.
- Package và cấu trúc thư mục nhất quán.
- Đã chọn `-d` để tách bytecode khỏi mã nguồn khi cần.
- Đã khai báo classpath hoặc module path cho dependency.
- Đã chọn `--release` phù hợp với phiên bản Java mà dự án hỗ trợ.
- Đã khai báo encoding, thường là UTF-8, khi dự án cần tính nhất quán giữa các môi trường.
- Đã đọc cảnh báo và lỗi trước khi chạy ứng dụng.
- Khi chạy, đã dùng đúng classpath/module path và JVM tương thích.

Hiểu rõ `javac` giúp xác định lỗi thuộc giai đoạn biên dịch hay giai đoạn chạy, đồng thời giúp kiểm soát phiên bản Java, dependency và đầu ra bytecode. Đây cũng là nền tảng để hiểu cách Gradle và Maven cấu hình trình biên dịch trong dự án Java lớn.