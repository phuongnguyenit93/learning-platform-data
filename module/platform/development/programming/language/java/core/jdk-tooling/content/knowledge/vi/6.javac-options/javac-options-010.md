# Tệp argument (argument file) trong javac

Khi dự án có nhiều tệp nguồn, thư viện và tùy chọn biên dịch, lệnh javac có thể trở nên rất dài. Trên một số hệ điều hành, độ dài command line còn bị giới hạn. Argument file (tệp đối số) giải quyết vấn đề này bằng cách lưu các tùy chọn và tên tệp vào một tệp văn bản, sau đó yêu cầu javac đọc chúng thông qua cú pháp `@filename`.

Argument file không thay đổi cách Java biên dịch chương trình. Nó chỉ gom các đối số thành một tệp để lệnh build ngắn hơn, dễ tái sử dụng và dễ quản lý.

## 1. Cú pháp cơ bản

Cú pháp:

~~~text
javac [compiler-options] @argument-file
~~~

Ví dụ:

~~~powershell
javac @build/compile.args
~~~

Khi gặp đối số bắt đầu bằng `@`, javac đọc nội dung tệp được chỉ định và mở rộng nội dung đó thành danh sách đối số của lệnh biên dịch.

Argument file có thể chứa:

- Tùy chọn compiler như `--release`, `-encoding`, `-d`, `-classpath` hoặc `--module-path`.
- Tên các tệp mã nguồn `.java`.
- Đường dẫn đến thư mục hoặc thư viện cần thiết cho quá trình biên dịch.
- Các đối số khác mà javac chấp nhận trên command line.

Bạn có thể đặt nhiều argument file trên cùng command line. Nội dung các tệp được xử lý theo thứ tự xuất hiện. Ví dụ:

~~~powershell
javac @build/common.args @build/application.args
~~~

Cách này hữu ích khi muốn dùng chung cấu hình compiler giữa nhiều module hoặc nhóm mã nguồn.

## 2. Cấu trúc và cách viết argument file

Argument file là tệp văn bản. Các đối số được phân tách bằng khoảng trắng hoặc ký tự xuống dòng. Cách dễ đọc và ít nhầm lẫn nhất là đặt mỗi đối số trên một dòng.

Ví dụ cấu trúc dự án:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── App.java
├── build/
│   └── compile.args
└── out/
~~~

Nội dung `build/compile.args`:

~~~text
--release
17
-encoding
UTF-8
-d
out
src/com/example/App.java
~~~

Chạy từ thư mục `project`:

~~~powershell
javac @build/compile.args
~~~

Các dòng trong argument file được hiểu tương đương với command line:

~~~powershell
javac --release 17 -encoding UTF-8 -d out src/com/example/App.java
~~~

Giải thích:

- `--release 17`: biên dịch theo cú pháp, bytecode và API nền tảng của Java 17.
- `-encoding UTF-8`: chỉ định encoding dùng để đọc các tệp mã nguồn.
- `-d out`: đặt các tệp `.class` vào thư mục `out`.
- `src/com/example/App.java`: tệp nguồn cần biên dịch.

Tên argument file không bắt buộc phải có phần mở rộng cụ thể. Các tên như `.args`, `.txt` hoặc `.options` đều có thể dùng; nên chọn một quy ước thống nhất trong dự án.

## 3. Ví dụ hoàn chỉnh

Tạo tệp nguồn `src/com/example/App.java`:

~~~java
package com.example;

public class App {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : String.join(" ", args);
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Tạo thư mục đầu ra và tệp `build/compile.args` với nội dung:

~~~text
--release
17
-encoding
UTF-8
-d
out
src/com/example/App.java
~~~

Từ thư mục gốc `project`, chạy:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac @build/compile.args
java -cp out com.example.App "argument file"
~~~

Kết quả:

~~~text
Hello, argument file!
~~~

Ở đây, javac đọc các tùy chọn từ `compile.args`, biên dịch mã nguồn và ghi bytecode vào `out`. Lệnh java sau đó chạy lớp chính bằng classpath `out`. Argument file chỉ tham gia vào bước biên dịch; nó không được truyền cho ứng dụng khi chạy.

Nếu thư mục `out` chưa tồn tại, có thể tạo nó trước bằng `New-Item` như ví dụ trên hoặc bằng `mkdir -p out` trong Bash/Zsh.

## 4. Đường dẫn có khoảng trắng và dấu phân cách

Nếu một tên tệp hoặc đường dẫn chứa khoảng trắng, đặt toàn bộ đối số đó trong dấu ngoặc kép.

Ví dụ cấu trúc:

~~~text
project/
├── source files/
│   └── App.java
└── build.args
~~~

Nội dung `build.args`:

~~~text
--release 17
-d
out
"source files/App.java"
~~~

Chạy:

~~~powershell
javac @build.args
~~~

Nếu đường dẫn thư viện chứa khoảng trắng, cũng cần đặt toàn bộ giá trị classpath trong dấu ngoặc kép.

Ví dụ trên Windows:

~~~text
-classpath
"lib/core api.jar;lib/logging.jar"
~~~

Ví dụ trên Linux/macOS:

~~~text
-classpath
"lib/core api.jar:lib/logging.jar"
~~~

Dấu phân cách các phần tử classpath là dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS. Dấu ngoặc kép giữ cả chuỗi classpath thành một đối số; sau đó javac xử lý dấu phân cách theo quy tắc classpath.

Khi đường dẫn phức tạp, nên dùng đường dẫn tương đối nhất quán hoặc đường dẫn tuyệt đối được tạo bởi hệ thống build. Tránh giả định rằng đường dẫn trong argument file được phân giải tương đối với thư mục chứa argument file; hãy chạy compiler từ working directory đã được quy định trong script hoặc CI.

## 5. Kết hợp argument file với tùy chọn javac

Argument file có thể chứa hầu hết tùy chọn biên dịch thường dùng. Một số ví dụ:

| Tùy chọn | Mục đích |
|---|---|
| `--release 17` | Chọn Java release mục tiêu |
| `-encoding UTF-8` | Encoding của tệp nguồn |
| `-d out` | Thư mục chứa class file đầu ra |
| `-classpath` hoặc `-cp` | Vị trí tìm class và thư viện trên classpath |
| `--module-path` | Vị trí tìm các module |
| `-sourcepath` | Vị trí tìm mã nguồn phụ thuộc |
| `-g` | Sinh thông tin debug |
| `-parameters` | Lưu tên tham số phương thức trong class file |
| `-proc:none` | Tắt annotation processing |

Ví dụ argument file cho ứng dụng dùng thư viện bên ngoài:

~~~text
--release
17
-encoding
UTF-8
-classpath
"lib/*"
-d
out
src/com/example/App.java
src/com/example/Service.java
~~~

Trên Windows, classpath có nhiều thư mục hoặc JAR được phân tách bằng dấu `;`; trên Linux/macOS dùng dấu `:`. Wildcard trong classpath như `lib/*` có ý nghĩa theo quy tắc classpath của Java. Không nên mặc định rằng wildcard nguồn như `src/**/*.java` sẽ được mở rộng trong argument file; hãy liệt kê tệp nguồn rõ ràng hoặc dùng công cụ build để tạo danh sách nguồn.

## 6. Dùng argument file cho dự án module

Argument file cũng dùng được với các tùy chọn module của javac.

Ví dụ, dự án có module `com.example.app` với `module-info.java` và lớp `Main.java`. Tạo `build/module-compile.args`:

~~~text
--release
17
-d
mods/com.example.app
src/module-info.java
src/com/example/app/Main.java
~~~

Biên dịch:

~~~powershell
javac @build/module-compile.args
~~~

Sau đó có thể chạy module đã biên dịch:

~~~powershell
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Tệp argument chỉ lưu đối số của javac; lệnh java chạy ứng dụng là một bước riêng. Nếu dự án có nhiều module, tạo một argument file cho từng module hoặc dùng các file cấu hình chung kết hợp với danh sách nguồn phù hợp.

## 7. Kết hợp đối số trực tiếp và argument file

Bạn không bắt buộc phải đưa mọi tùy chọn vào argument file. Có thể đặt một số tùy chọn trực tiếp trên command line và phần còn lại trong tệp.

Ví dụ:

~~~powershell
javac -J-Xmx1g @build/compile.args
~~~

Trong đó:

- `-J-Xmx1g` chuyển tùy chọn `-Xmx1g` đến JVM đang chạy compiler javac.
- `@build/compile.args` cung cấp các tùy chọn compiler và tên tệp nguồn.

Phân biệt rõ bộ nhớ của compiler và bộ nhớ của ứng dụng: `-J-Xmx1g` điều chỉnh JVM chạy javac; nó không đặt heap cho chương trình được biên dịch. Heap của ứng dụng được cấu hình ở lệnh java khi chạy ứng dụng.

## 8. Giới hạn và lưu ý

### 8.1. Tùy chọn -J phải đặt trực tiếp trên command line

Tùy chọn bắt đầu bằng `-J` được chuyển cho JVM khởi chạy compiler, không phải là tùy chọn biên dịch thông thường. Vì vậy, `-J` không được hỗ trợ bên trong argument file. Nếu cần tăng bộ nhớ cho compiler, hãy đặt tùy chọn này trực tiếp trên command line:

~~~powershell
javac -J-Xmx2g @build/compile.args
~~~

### 8.2. Encoding của argument file và encoding mã nguồn là hai việc khác nhau

`-encoding UTF-8` chỉ định cách javac đọc các tệp mã nguồn. Nó không có nghĩa là mọi tệp cấu hình đầu vào đều tự động được đọc bằng UTF-8.

Argument file được đọc theo encoding mặc định của nền tảng chạy compiler. Khi dự án có đường dẫn hoặc nội dung ngoài ASCII, hãy bảo đảm encoding của argument file phù hợp với môi trường build. Trong CI, nên thống nhất encoding, locale và working directory giữa các máy.

### 8.3. Argument file không thay thế build tool

Argument file phù hợp với script biên dịch trực tiếp bằng javac, dự án nhỏ hoặc quy trình build tùy chỉnh. Với dự án lớn, Maven hoặc Gradle thường quản lý dependency, source set, annotation processor, module và tác vụ biên dịch tốt hơn.

Build tool có thể tự tạo argument file nội bộ khi gọi compiler. Không nên chỉnh sửa file tạm do build tool sinh ra; hãy cấu hình thông qua `pom.xml`, `build.gradle` hoặc `build.gradle.kts`.

### 8.4. Không thay đổi ngữ nghĩa của compiler

Đưa tùy chọn vào argument file không làm thay đổi cách javac xử lý chúng. Nếu một lệnh trực tiếp có lỗi cú pháp, sai classpath hoặc thiếu dependency thì chuyển các đối số đó vào file cũng không tự khắc phục lỗi.

Hãy kiểm tra command line sau khi mở rộng về mặt logic: thứ tự tùy chọn, giá trị theo sau từng tùy chọn, danh sách source file và working directory phải đúng.

## 9. Tổ chức argument file trong dự án

Với dự án có nhiều mục tiêu biên dịch, có thể chia file theo trách nhiệm:

~~~text
project/
├── build/
│   ├── common.args
│   ├── main.args
│   └── test.args
├── src/
│   ├── main/
│   └── test/
└── out/
~~~

Ví dụ `build/common.args`:

~~~text
--release
17
-encoding
UTF-8
~~~

Ví dụ `build/main.args`:

~~~text
-d
out/main
src/main/java/com/example/App.java
src/main/java/com/example/Service.java
~~~

Biên dịch bằng cách kết hợp các tệp:

~~~powershell
javac @build/common.args @build/main.args
~~~

Ví dụ này minh họa cách tái sử dụng thiết lập chung. Khi cấu hình thực tế, hãy bảo đảm thư mục đầu ra tồn tại hoặc được tạo bởi script trước khi biên dịch. Các tệp cấu hình cần được quản lý cùng dự án để mọi thành viên và CI dùng chung một bộ tùy chọn.

## 10. Lỗi thường gặp khi dùng argument file

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `File not found` khi gọi `@build/compile.args` | Sai đường dẫn argument file hoặc chạy từ working directory khác | Kiểm tra vị trí hiện tại và đường dẫn tới file |
| `file not found: source files/App.java` | Đường dẫn có khoảng trắng chưa được đặt trong dấu ngoặc kép | Bao toàn bộ tên đường dẫn bằng dấu ngoặc kép trong argument file |
| `invalid flag` | Dòng đối số bị tách sai hoặc tên tùy chọn không hợp lệ | Kiểm tra từng token, dấu ngoặc kép và phiên bản javac |
| `invalid source release` | Release trong file không được compiler hỗ trợ | Kiểm tra `javac -version` và giá trị `--release` |
| `package ... does not exist` | Classpath/module path hoặc danh sách nguồn chưa đầy đủ | Kiểm tra `-classpath`, `--module-path` và các dependency |
| Compiler không nhận `-J-Xmx...` trong file | `-J` không được hỗ trợ bên trong argument file | Đặt `-J` trực tiếp trên command line |
| Ký tự tiếng Việt hoặc tên file bị sai | Encoding của argument file không khớp môi trường | Lưu file bằng encoding phù hợp với máy build; chuẩn hóa CI |
| Lệnh chạy được trên máy cá nhân nhưng lỗi trên CI | Working directory, đường dẫn hoặc môi trường build khác nhau | Chuẩn hóa thư mục chạy, JDK và cấu trúc dự án |

Khi chẩn đoán, hãy thử chạy compiler với một argument file nhỏ nhất có thể. Bắt đầu từ một tùy chọn và một tệp nguồn, sau đó thêm classpath, module path và các tùy chọn khác từng bước. Cách này giúp xác định chính xác token hoặc đường dẫn gây lỗi.

## 11. Checklist trước khi dùng argument file

- [ ] Tệp argument nằm ở đường dẫn có thể truy cập từ working directory của lệnh build.
- [ ] Mỗi tùy chọn và giá trị của nó được viết thành các đối số hợp lệ.
- [ ] Đường dẫn có khoảng trắng được đặt trong dấu ngoặc kép.
- [ ] `-encoding` được dùng cho encoding mã nguồn; encoding argument file được xử lý riêng.
- [ ] `-J` được đặt trực tiếp trên command line.
- [ ] Classpath/module path dùng đúng dấu phân cách theo hệ điều hành.
- [ ] Danh sách source file và dependency đầy đủ.
- [ ] Working directory, JDK và encoding được thống nhất giữa máy phát triển và CI.
- [ ] Build tool được cấu hình qua file dự án thay vì sửa file argument tạm do tool sinh ra.

Argument file giúp quản lý command line javac dài bằng cách đưa tùy chọn và tên tệp vào một tệp văn bản. Hãy dùng cú pháp `@filename`, viết đối số rõ ràng, trích dẫn đường dẫn có khoảng trắng và giữ môi trường build nhất quán. Khi cần cấu hình compiler phức tạp hoặc quản lý dependency lớn, nên cân nhắc Maven hoặc Gradle để duy trì quy trình biên dịch ổn định.
