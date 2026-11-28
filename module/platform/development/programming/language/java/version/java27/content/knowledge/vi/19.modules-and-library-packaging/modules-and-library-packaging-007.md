# Tạo JAR, manifest và executable JAR trong Java 27

Khi phát triển bằng Java 27, mã nguồn `.java` được biên dịch thành các tệp `.class`. Để phân phối ứng dụng hoặc thư viện, cách thông dụng là **đóng gói các class và tài nguyên vào tệp Java Archive (JAR)**. Một JAR có thể là thư viện được ứng dụng khác sử dụng, hoặc là **executable JAR** có điểm vào để chạy bằng `java -jar`.

Bài thuộc chương **Module và đóng gói thư viện**, tập trung vào công cụ `jar`, tệp manifest `META-INF/MANIFEST.MF`, cách tạo executable JAR, tổ chức dependency và phân biệt JAR chạy trên **class path** với **modular JAR** trên **module path**. Các hướng dẫn ưu tiên API và công cụ còn phù hợp với Java SE 27, tránh những cách triển khai đã lỗi thời.

## 1. JAR là gì và dùng khi nào?

JAR là định dạng lưu trữ dựa trên ZIP. Nó có thể chứa:

- Các tệp `.class` đã biên dịch.
- Tài nguyên như `.properties`, `.txt`, biểu tượng, mẫu văn bản.
- Metadata trong `META-INF/MANIFEST.MF`.
- Metadata dịch vụ trong `META-INF/services/` khi dùng cơ chế `ServiceLoader` trên class path.
- `module-info.class` nếu đây là modular JAR được tạo từ module có mô tả tường minh.

Một cấu trúc đơn giản:

~~~text
hello.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       └── app/
│           └── Main.class
└── app/
    └── banner.txt
~~~

JAR tiện hơn phân phối nhiều class rời vì ứng dụng, thư viện và tài nguyên liên quan được gom trong cùng archive. Tuy nhiên, **JAR không tự động bao gồm thư viện phụ thuộc** và **JAR không phải tệp thực thi native** của Windows, Linux hoặc macOS. Executable JAR vẫn cần một môi trường Java phù hợp để khởi chạy.

### 1.1. Phân biệt các loại JAR

| Khái niệm | Ý nghĩa | Cách sử dụng thường gặp |
|---|---|---|
| Library JAR | Chứa mã thư viện cho dự án khác gọi | Thêm vào class path hoặc module path phù hợp |
| Executable JAR | Có metadata chọn class khởi động, nhất là `Main-Class` | `java -jar app.jar` |
| Modular JAR | Có `module-info.class` tại gốc archive theo quy tắc module | `java --module-path ... --module ...` |
| Automatic module | JAR không có mô tả module tường minh nhưng được đặt trên module path | Dùng tên automatic module; là bước tích hợp với JPMS |
| Multi-release JAR | Chứa phiên bản class theo mức Java dưới `META-INF/versions/N` | Dùng khi thư viện phải thích nghi với nhiều mức Java |

Một JAR **có thể đồng thời** mang nhiều thuộc tính; ví dụ một modular JAR vẫn có thể có main class. Không nên coi “executable” và “modular” là hai định dạng file loại trừ lẫn nhau.

### 1.2. Công cụ hiện hành

| Công cụ | Công dụng |
|---|---|
| `javac` | Biên dịch Java source sang class |
| `jar` | Tạo, cập nhật, liệt kê, giải nén, kiểm tra và mô tả JAR |
| `java` | Khởi chạy class, executable JAR hoặc module |
| `jdeps` | Phân tích dependency ở mức class/package/module |
| `jlink` | Tạo runtime image chuyên biệt từ các module phù hợp |
| `jpackage` | Tạo gói phân phối ứng dụng cho hệ điều hành |

Để làm bài này, cần **JDK 27** có `javac`, `jar` và `java` trên command line. Có thể kiểm tra:

~~~shell
java --version
javac --version
jar --version
~~~

Các ví dụ giả định đang đứng tại thư mục gốc dự án và các lệnh biên dịch chạy trên JDK 27. Nếu ứng dụng chỉ dùng tính năng thuộc mức Java thấp hơn, hãy lựa chọn `--release` tương ứng theo chính sách hỗ trợ của sản phẩm.

## 2. Cấu trúc dự án mẫu: mã nguồn và tài nguyên

Tạo một ứng dụng rất nhỏ theo cấu trúc:

~~~text
hello-project/
├── src/
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
├── resources/
│   └── app/
│       └── banner.txt
├── build/
│   └── classes/         (sinh sau khi biên dịch)
└── dist/                (chứa JAR đầu ra)
~~~

File `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class Main {
    public static void main(String[] args) throws IOException {
        String name = args.length > 0 ? args[0] : "bạn";

        try (InputStream input = Main.class.getResourceAsStream(
                "/app/banner.txt")) {

            if (input == null) {
                throw new IOException(
                        "Thiếu tài nguyên /app/banner.txt"
                );
            }

            String banner = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();

            System.out.println(banner + ", " + name + "!");
        }
    }
}
~~~

File `resources/app/banner.txt` (lưu bằng UTF-8):

~~~text
Xin chào Java 27
~~~

Trong ví dụ này, `Main` chỉ đọc một tài nguyên nhỏ đã biết. Trong ứng dụng thật, không nên dùng `readAllBytes()` trên nội dung rất lớn hoặc từ nguồn không kiểm soát mà không có giới hạn kích thước.

### 2.1. Vì sao cần đường dẫn class và tài nguyên đúng?

Từ khai báo:

~~~java
package com.example.app;
~~~

class sau biên dịch phải có đường dẫn tương ứng:

~~~text
com/example/app/Main.class
~~~

Điều này độc lập với vị trí tệp nguồn lúc viết; Java class loader tìm class theo tên đầy đủ và cấu trúc bên trong class path hoặc module.

Tương tự, lệnh:

~~~java
Main.class.getResourceAsStream("/app/banner.txt")
~~~

tìm tài nguyên `app/banner.txt` tại **gốc đường dẫn tài nguyên**, không tìm theo thư mục làm việc của hệ điều hành. Vì vậy, khi tạo JAR phải đóng gói thêm thư mục `resources` với nội dung ở đúng vị trí.

## 3. Biên dịch trước khi tạo JAR

Từ thư mục `hello-project`, tạo hai thư mục đầu ra:

**Linux/macOS:**

~~~shell
mkdir -p build/classes dist
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/classes, dist
~~~

Biên dịch bằng lệnh hoàn chỉnh trên một dòng (dùng được trong PowerShell, Bash hoặc Zsh):

~~~shell
javac --release 27 -encoding UTF-8 -d build/classes src/com/example/app/Main.java
~~~

Các thành phần:

- `--release 27`: nhắm tới API, ngôn ngữ và định dạng class của Java 27.
- `-encoding UTF-8`: diễn giải nội dung source code theo UTF-8.
- `-d build/classes`: đặt class biên dịch trong thư mục đích, giữ cấu trúc package.

Kết quả mong đợi:

~~~text
build/classes/com/example/app/Main.class
~~~

### 3.1. Kiểm tra trước khi đóng gói

Trên **Linux/macOS**, có thể chạy khi tài nguyên nằm trên class path:

~~~shell
java --class-path "build/classes:resources" com.example.app.Main An
~~~

Trên **Windows PowerShell**:

~~~powershell
java --class-path "build/classes;resources" com.example.app.Main An
~~~

Kết quả:

~~~text
Xin chào Java 27, An!
~~~

Dấu phân tách **nhiều đường dẫn** trong class path là `:` trên Linux/macOS và `;` trên Windows. Đây là khác biệt của **tùy chọn class path**, không phải cú pháp bên trong file JAR.

Nếu thử chạy chỉ với `build/classes`, chương trình sẽ không tìm được `/app/banner.txt`. Đây là lỗi thiếu resource trên class path, không phải lỗi biên dịch Java.

## 4. Công cụ jar và các thao tác cơ bản

`jar` là công cụ đi kèm JDK để tạo và quản lý archive. Các option dạng dài thường dễ đọc và tránh nhầm lẫn hơn tổ hợp ký tự ngắn.

| Tác vụ | Cú pháp |
|---|---|
| Tạo archive | `jar --create --file app.jar ...` |
| Liệt kê | `jar --list --file app.jar` |
| Cập nhật | `jar --update --file app.jar ...` |
| Giải nén | `jar --extract --file app.jar ...` |
| Mô tả module | `jar --describe-module --file app.jar` |
| Kiểm tra cấu trúc archive | `jar --validate --file app.jar` |
| Xem trợ giúp | `jar --help` |

Các option dạng ngắn `-c`, `-t`, `-u`, `-x`, `-f` vẫn tồn tại, nhưng ví dụ này sử dụng dạng dài để trình bày rõ tác vụ.

### 4.1. Tạo library JAR cơ bản

Nếu chỉ muốn đóng gói class:

~~~shell
jar --create --file dist/hello-library.jar -C build/classes .
~~~

Ý nghĩa `-C build/classes .`:

1. Dùng `build/classes` làm thư mục gốc tạm thời cho các file được đóng gói.
2. Thêm mọi nội dung của thư mục đó vào JAR.
3. Tạo tên entry dựa trên đường dẫn tương đối, ví dụ `com/example/app/Main.class`.

Không viết:

~~~shell
# Không nên: dễ đưa cả tiền tố build/classes vào archive.
jar --create --file dist/wrong.jar build/classes
~~~

Vì archive kiểu này có thể chứa:

~~~text
build/classes/com/example/app/Main.class
~~~

trong khi class loader cần:

~~~text
com/example/app/Main.class
~~~

### 4.2. Liệt kê các entry trong JAR

~~~shell
jar --list --file dist/hello-library.jar
~~~

Đầu ra thường có:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/app/
com/example/app/Main.class
~~~

Lệnh `--list` xem cấu trúc archive mà không yêu cầu giải nén.

### 4.3. Giải nén vào thư mục được kiểm soát

Trên JDK 27:

~~~shell
jar --extract --file dist/hello-library.jar --dir extracted
~~~

Khi thao tác với archive từ nguồn không tin cậy, cần đánh giá rủi ro path traversal, overwrite, số lượng entry và ZIP bomb trước khi tự động giải nén. `jar --validate` cung cấp một số kiểm tra cấu trúc nhưng **không thay thế** chính sách bảo mật khi xử lý nội dung không tin cậy.

## 5. Tạo executable JAR bằng --main-class

Bây giờ tạo JAR vừa có class vừa có resource và khai báo main class:

~~~shell
jar --create --file dist/hello.jar --main-class com.example.app.Main -C build/classes . -C resources .
~~~

Với cú pháp trên:

- `--create`: tạo JAR.
- `--file dist/hello.jar`: chọn đường dẫn đầu ra.
- `--main-class com.example.app.Main`: khai báo class điểm vào.
- `-C build/classes .`: đóng gói toàn bộ class theo đúng package.
- `-C resources .`: đóng gói resource `app/banner.txt`.

Liệt kê:

~~~shell
jar --list --file dist/hello.jar
~~~

Nội dung chính dự kiến:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/example/app/Main.class
app/banner.txt
~~~

Thứ tự và sự hiện diện của các entry thư mục có thể khác nhau; phần quan trọng là tên class và resource nằm đúng vị trí.

### 5.1. Chạy executable JAR

~~~shell
java -jar dist/hello.jar An
~~~

Kết quả:

~~~text
Xin chào Java 27, An!
~~~

Đây là **executable JAR** vì JAR có metadata chỉ ra điểm vào phù hợp và chứa class/tài nguyên cần thiết cho ví dụ.

**Tham số sau tên JAR** như `An` được truyền vào mảng `String[] args` của `main`. Còn tùy chọn JVM nên đặt trước `-jar` khi cần cấu hình runtime:

~~~shell
java -Dapp.mode=demo -jar dist/hello.jar An
~~~

### 5.2. Main-Class phải là tên class đầy đủ

Trong ví dụ:

~~~text
Main-Class: com.example.app.Main
~~~

Không viết:

~~~text
Main-Class: Main.class
Main-Class: com/example/app/Main.class
~~~

Giá trị cần là **binary name của class**, dùng dấu chấm phân cách package và không có phần mở rộng `.class`.

Để ví dụ dễ tương thích, điểm vào sử dụng chữ ký truyền thống:

~~~java
public static void main(String[] args)
~~~

Đây vẫn là một cách hợp lệ và rõ ràng để xác định điểm vào cho ứng dụng Java 27.

## 6. Manifest: metadata nằm trong META-INF/MANIFEST.MF

Manifest là tệp metadata đặt trong archive theo tên:

~~~text
META-INF/MANIFEST.MF
~~~

Một manifest cho ví dụ `hello.jar` có thể chứa:

~~~text
Manifest-Version: 1.0
Created-By: 27 (JDK)
Main-Class: com.example.app.Main

~~~

Dòng `Created-By` chỉ là ví dụ metadata; giá trị thực có thể do công cụ `jar` tạo và không cần giống nội dung minh họa.

### 6.1. Một số thuộc tính quan trọng

| Thuộc tính | Ý nghĩa |
|---|---|
| `Manifest-Version` | Phiên bản định dạng manifest, thường là `1.0` |
| `Main-Class` | Class có điểm vào khi chạy `java -jar` |
| `Class-Path` | Danh sách relative URL đến thư viện hoặc thư mục phụ thuộc trên class path |
| `Automatic-Module-Name` | Gợi ý tên automatic module nếu JAR không có module descriptor được đặt trên module path |
| `Multi-Release` | Đánh dấu JAR có các phiên bản class/resource theo mức Java khi giá trị là `true` |
| `Implementation-Title` | Thông tin mô tả implementation |
| `Implementation-Version` | Phiên bản implementation trong metadata |
| `Implementation-Vendor` | Thông tin đơn vị phát triển implementation |

Các thuộc tính này không phải toàn bộ thuộc tính được hỗ trợ bởi JAR spec. Nhiều mục đích như ký số, service provider và package sealing có quy tắc riêng.

### 6.2. Cú pháp manifest có quy tắc riêng

Manifest **không phải** một tệp `.properties` thông thường, dù cùng có cặp tên–giá trị.

Một manifest chính xác cần chú ý:

1. Dùng mẫu `Tên-Thuộc-Tính: giá trị`, có **dấu cách sau dấu hai chấm**.
2. `Manifest-Version: 1.0` nên đứng ở đầu manifest do ứng dụng tự tạo.
3. Phần main section được kết thúc bởi **một dòng trống**.
4. Tên thuộc tính không được lặp lại trong cùng section.
5. Mỗi dòng vật lý tối đa **72 byte UTF-8**, không phải 72 ký tự Unicode.
6. Khi giá trị dài phải xuống dòng, dòng nối tiếp phải bắt đầu bằng **một dấu cách** theo quy tắc của JAR manifest.

Ví dụ nội dung manifest tự viết cho chương trình:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

~~~

Nếu tạo file thủ công, đảm bảo file thực sự có ký tự xuống dòng kết thúc các thuộc tính và một dòng trống sau main section. Không dựa vào việc một trình soạn thảo hiển thị dòng trống như thế nào để suy luận nội dung byte; khi nghi ngờ, dùng API `java.util.jar.Manifest` hoặc công cụ build phù hợp để tạo metadata chuẩn.

### 6.3. Cảnh báo với UTF-8 BOM và dòng quá dài

Manifest sử dụng quy tắc UTF-8 cụ thể; phần mềm tạo manifest không nên thêm **BOM** trước `Manifest-Version`. Một BOM không mong muốn có thể khiến parser nhận sai tên thuộc tính đầu tiên.

Khi giá trị thuộc tính chứa nội dung dài hoặc ký tự Unicode, quy tắc 72 **byte** cần được áp dụng sau khi mã hóa UTF-8. Việc chia chuỗi theo số ký tự có thể sai đối với chữ tiếng Việt và các ký tự nhiều byte.

Với manifest có nhiều thuộc tính động, nên để công cụ `jar` hoặc thư viện build đảm nhiệm việc tạo định dạng hợp lệ.

## 7. Chỉ định manifest thủ công bằng --manifest

Nếu muốn kiểm soát các thuộc tính, tạo file manifest ở ngoài archive trước, ví dụ `app.mf`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Title: Java 27 Greeting App
Implementation-Version: 1.0.0

~~~

Sau đó dùng:

~~~shell
jar --create --file dist/hello-with-manifest.jar --manifest app.mf -C build/classes . -C resources .
~~~

Chạy:

~~~shell
java -jar dist/hello-with-manifest.jar An
~~~

Khi dùng `--manifest app.mf`, công cụ `jar` thêm/ghép metadata manifest theo cú pháp mà nó hỗ trợ. Đừng ghi trực tiếp một `META-INF/MANIFEST.MF` bất kỳ vào archive đồng thời lại chỉ định metadata mâu thuẫn trên command line mà không kiểm tra kết quả.

### 7.1. Khi nào chọn --main-class, khi nào chọn --manifest?

Dùng `--main-class` khi chỉ cần nhanh chóng tạo executable JAR với một class điểm vào:

~~~shell
jar --create --file dist/hello.jar --main-class com.example.app.Main -C build/classes . -C resources .
~~~

Dùng `--manifest` khi cần khai báo thêm `Class-Path` hoặc metadata khác:

~~~shell
jar --create --file dist/hello.jar --manifest app.mf -C build/classes . -C resources .
~~~

Thông thường, không cần khai báo đồng thời `Main-Class` bằng cả option và file manifest. Một nguồn cấu hình nhất quán sẽ dễ kiểm tra và bảo trì hơn.

## 8. Xem và kiểm tra manifest đã đóng gói

Liệt kê archive:

~~~shell
jar --list --file dist/hello.jar
~~~

Tìm entry:

~~~text
META-INF/MANIFEST.MF
~~~

Để kiểm tra nội dung, có thể giải nén manifest vào một thư mục kiểm tra riêng:

~~~shell
jar --extract --file dist/hello.jar --dir inspection META-INF/MANIFEST.MF
~~~

Sau đó mở:

~~~text
inspection/META-INF/MANIFEST.MF
~~~

Tránh giải nén trực tiếp vào thư mục source hoặc build đang dùng nếu việc ghi đè có thể làm thay đổi file công việc.

### 8.1. Đọc manifest bằng API Java

Java cung cấp `java.util.jar.JarFile` và `java.util.jar.Manifest` để truy cập metadata trực tiếp mà không phải giải nén toàn bộ JAR:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class InspectManifest {
    public static void main(String[] args) throws IOException {
        Path jarPath = Path.of("dist/hello.jar");

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            Manifest manifest = jar.getManifest();

            if (manifest == null) {
                System.out.println("JAR không có manifest");
                return;
            }

            Attributes attributes = manifest.getMainAttributes();

            String mainClass = attributes.getValue(
                    Attributes.Name.MAIN_CLASS
            );

            System.out.println("Main-Class = " + mainClass);
        }
    }
}
~~~

Đối với JAR từ nguồn không tin cậy, không xem việc đọc được manifest là dấu hiệu nội dung đã an toàn. Manifest là metadata do bên tạo archive kiểm soát.

### 8.2. Kiểm tra cấu trúc với jar --validate

JDK 27 hỗ trợ:

~~~shell
jar --validate --file dist/hello.jar
~~~

Lệnh này thực hiện các kiểm tra tính toàn vẹn/cấu trúc đã được tài liệu hóa, ví dụ tên entry trùng, đường dẫn entry không hợp lệ và tính nhất quán của một số multi-release JAR. Đây **không phải** kiểm tra chữ ký số, scan mã độc hoặc kiểm định toàn bộ hành vi của ứng dụng.

## 9. java -jar hoạt động như thế nào?

Lệnh:

~~~shell
java -jar dist/hello.jar An
~~~

yêu cầu Java launcher tìm manifest của JAR, đọc `Main-Class` rồi nạp class khởi động theo cơ chế chạy JAR.

Sơ đồ:

~~~text
java -jar dist/hello.jar
             |
             v
    META-INF/MANIFEST.MF
             |
             v
   Main-Class: com.example.app.Main
             |
             v
   com/example/app/Main.class
             |
             v
      main(String[] args)
~~~

**Điều quan trọng:** chạy bằng `java -jar` là chế độ khởi chạy ứng dụng theo JAR. Nó khác với việc dùng `-cp` và chỉ định main class tường minh.

| Cách chạy | Điểm vào được chọn bằng | Phụ thuộc |
|---|---|---|
| `java -cp dist/hello.jar com.example.app.Main` | Tên class sau tùy chọn | Class path được truyền |
| `java -jar dist/hello.jar` | `Main-Class` trong manifest | JAR được chỉ định và `Class-Path` trong manifest |
| `java --module-path dist/m.jar --module module.name` | Module và main class được chỉ định/ghi trong descriptor | Module path và module graph |

### 9.1. Vì sao -cp không giải quyết dependency khi dùng -jar?

Theo tài liệu launcher Java, khi sử dụng `-jar`, JAR chỉ định làm nguồn chính cho user classes; các thiết lập class path khác từ `-cp` hoặc biến môi trường `CLASSPATH` bị bỏ qua trong chế độ này.

Ví dụ **không nên trông đợi**:

~~~shell
java -cp extra.jar -jar dist/hello.jar
~~~

để thêm `extra.jar` vào class path của ứng dụng đang chạy bằng `-jar`.

Nếu executable JAR cần các thư viện khác, các chiến lược hợp lệ thường là:

- Khai báo các thư viện trên manifest `Class-Path` với relative URL hợp lệ.
- Chạy bằng `java -cp ... MainClass` thay vì `-jar`.
- Dùng công cụ build tạo một gói ứng dụng có đầy đủ dependency theo cấu trúc phù hợp.
- Với ứng dụng module, dùng module path và `java --module ...` theo module graph.
- Khi cần gói triển khai thân thiện cho người dùng, cân nhắc `jpackage` hoặc runtime image phù hợp.

Không nhầm một file `app.jar` chứa **file `dependency.jar` nằm bên trong** với việc các class của dependency đó được nạp tự động. Java launcher chuẩn không tự coi các nested JAR thông thường là class path.

## 10. Manifest Class-Path: khai báo thư viện phụ thuộc

`Class-Path` trong manifest liệt kê các relative URL đến JAR hoặc thư mục tài nguyên phụ thuộc.

Ví dụ ứng dụng phân phối như sau:

~~~text
dist/
├── app.jar
└── lib/
    ├── greetings.jar
    └── more-utils.jar
~~~

Manifest của `dist/app.jar`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.cli.Runner
Class-Path: lib/greetings.jar lib/more-utils.jar

~~~

Ý nghĩa:

- Hai giá trị được phân cách bằng **dấu cách** trong manifest, không phải `:` hoặc `;` như command-line class path.
- Đường dẫn là URL **tương đối từ vị trí chứa JAR ngữ cảnh**, trong ví dụ là `dist/app.jar`.
- File `dist/lib/greetings.jar` và `dist/lib/more-utils.jar` phải hiện diện khi chạy.
- `Class-Path` không tải dependency từ Maven Central và cũng không định nghĩa phiên bản/thỏa mãn dependency tự động.

Để dùng đúng quy tắc, không viết đường dẫn tuyệt đối hoặc dẫn sang một vị trí không nằm trong phạm vi hợp lệ của manifest Class-Path. Với thư viện bên cạnh ứng dụng, cấu trúc thư mục `lib/` là một cách triển khai dễ hiểu.

### 10.1. Ví dụ hoàn chỉnh: hai JAR liên kết qua manifest

Dự án:

~~~text
with-dependency/
├── src/
│   └── com/
│       └── example/
│           ├── lib/
│           │   └── Greeter.java
│           └── cli/
│               └── Runner.java
├── app.mf
├── build/
│   ├── lib/
│   └── app/
└── dist/
    ├── app.jar
    └── lib/
        └── greeter.jar
~~~

File `src/com/example/lib/Greeter.java`:

~~~java
package com.example.lib;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

File `src/com/example/cli/Runner.java`:

~~~java
package com.example.cli;

import com.example.lib.Greeter;

public class Runner {
    public static void main(String[] args) {
        String who = args.length > 0 ? args[0] : "Java";
        System.out.println(Greeter.hello(who));
    }
}
~~~

File `app.mf`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.cli.Runner
Class-Path: lib/greeter.jar

~~~

Tạo thư mục đầu ra.

**Linux/macOS:**

~~~shell
mkdir -p build/lib build/app dist/lib
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/lib, build/app, dist/lib
~~~

Biên dịch thư viện:

~~~shell
javac --release 27 -encoding UTF-8 -d build/lib src/com/example/lib/Greeter.java
~~~

Đóng gói thư viện:

~~~shell
jar --create --file dist/lib/greeter.jar -C build/lib .
~~~

Biên dịch ứng dụng với thư viện trên class path:

~~~shell
javac --release 27 -encoding UTF-8 --class-path dist/lib/greeter.jar -d build/app src/com/example/cli/Runner.java
~~~

Đóng gói ứng dụng, dùng manifest:

~~~shell
jar --create --file dist/app.jar --manifest app.mf -C build/app .
~~~

Chạy:

~~~shell
java -jar dist/app.jar An
~~~

Kết quả mong đợi:

~~~text
Xin chào, An!
~~~

Nếu xóa hoặc di chuyển `dist/lib/greeter.jar` nhưng vẫn giữ `app.jar`, chương trình có thể gặp `NoClassDefFoundError` khi sử dụng `Greeter`. Vì vậy, **executable JAR không phải lúc nào cũng là một file duy nhất có thể sao chép đi bất kỳ đâu**.

### 10.2. Chạy bằng class path thay cho manifest Class-Path

Có thể bỏ `Class-Path` trong manifest và dùng `-cp` khi khởi chạy tường minh.

Linux/macOS:

~~~shell
java -cp "dist/app.jar:dist/lib/greeter.jar" com.example.cli.Runner An
~~~

Windows PowerShell:

~~~powershell
java -cp "dist/app.jar;dist/lib/greeter.jar" com.example.cli.Runner An
~~~

Trong ví dụ này, `Main-Class` không còn bắt buộc vì tên class điểm vào đã được ghi trực tiếp sau `-cp`.

## 11. Thin JAR, fat JAR và cách đóng gói dependency

Khi một ứng dụng dùng nhiều thư viện, cần chọn mô hình phân phối.

### 11.1. Thin JAR

Một **thin JAR** chứa class và tài nguyên của chính ứng dụng nhưng để dependency thành các JAR riêng.

~~~text
release/
├── app.jar
└── lib/
    ├── library-a.jar
    ├── library-b.jar
    └── library-c.jar
~~~

Ưu điểm:

- Dễ kiểm tra và thay dependency độc lập.
- Các thành phần rõ ràng, dễ kiểm tra giấy phép và nguồn gốc.
- Không trộn lẫn các resource cùng tên từ nhiều dependency.

Hạn chế:

- Cần mang theo đủ cây thư mục phân phối.
- Phải cấu hình class path hoặc manifest `Class-Path` chính xác.

### 11.2. Uber JAR / shaded JAR

Một **uber JAR** hoặc **shaded JAR** thường chứa class và resource của ứng dụng cùng dependency dưới một archive để chạy thuận tiện.

Nhưng chỉ chạy:

~~~shell
jar --create --file app.jar lib/a.jar lib/b.jar
~~~

**không** biến hai thư viện đó thành class có thể được Java launcher nạp trực tiếp; lệnh trên chỉ đặt hai file `a.jar` và `b.jar` làm entry bên trong archive.

Để tạo executable archive có dependency, hệ thống build thường cần hợp nhất class/resource và xử lý các xung đột:

- Nhiều thư viện có cùng path `META-INF/services/...`.
- Manifest hoặc file chữ ký của dependency cũ.
- Class cùng tên hoặc package xung đột.
- License và metadata bắt buộc giữ lại.
- Trùng tên cấu hình/resource và thứ tự ưu tiên.
- Phạm vi dependency cần thiết lúc chạy.

Đối với dự án thật, nên dùng plugin đóng gói phù hợp của Maven/Gradle thay vì tự giải nén nhiều JAR và trộn tùy tiện. Khái niệm fat/uber/shaded JAR là cách tổ chức phân phối, **không phải một định dạng JAR mới do JDK tự quy định**.

### 11.3. Nested JAR và custom launcher

Một số framework phân phối executable archive có thư viện JAR lồng bên trong và dùng một launcher hoặc class loader riêng để đọc các nested JAR đó.

Không lấy cấu trúc của một framework rồi kết luận rằng **mọi** lệnh `java -jar` đều tự hỗ trợ nested JAR. Hỗ trợ phụ thuộc vào cách launcher và framework được triển khai.

## 12. Resource trong JAR: cần nằm đúng class path

Với ví dụ `Main.class.getResourceAsStream("/app/banner.txt")`, tài nguyên phải là entry:

~~~text
app/banner.txt
~~~

Câu lệnh đóng gói đúng:

~~~shell
jar --create --file dist/hello.jar --main-class com.example.app.Main -C build/classes . -C resources .
~~~

Nếu bỏ `-C resources .`:

~~~shell
jar --create --file dist/without-resource.jar --main-class com.example.app.Main -C build/classes .
~~~

ứng dụng sẽ ném ngoại lệ do resource không tồn tại.

### 12.1. Phân biệt nguồn tài nguyên và tệp trên đĩa

Đoạn mã:

~~~java
Path.of("app/banner.txt")
~~~

tạo đường dẫn **trên hệ thống tệp của hệ điều hành** tương đối với thư mục làm việc; nó không mặc nhiên chỉ vào resource nằm trong JAR.

Ngược lại:

~~~java
Main.class.getResourceAsStream("/app/banner.txt")
~~~

truy cập thông qua hệ thống tải class/resource.

Trong chương trình chạy từ JAR, URL của tài nguyên có thể dùng scheme `jar:`; không nên giả định nó có thể được chuyển trực tiếp sang `Path` trên hệ thống tệp mặc định.

Nếu cần thao tác như filesystem bên trong một archive, Java còn có ZIP FileSystem Provider, nhưng việc dùng nó là thiết kế riêng. Đối với tệp cấu hình/văn bản đi kèm ứng dụng, `getResourceAsStream` thường phù hợp.

### 12.2. Quy tắc tương đối và tuyệt đối của getResourceAsStream

~~~java
Main.class.getResourceAsStream("local.txt");
~~~

tìm `local.txt` tương đối với package `com.example.app`.

~~~java
Main.class.getResourceAsStream("/app/banner.txt");
~~~

tìm `app/banner.txt` từ gốc tài nguyên trong trường hợp class path thông thường.

Trong named module, truy cập tài nguyên qua class loader và `Class.getResourceAsStream` còn chịu các quy tắc module encapsulation cho resource trong package. Khi đóng gói ứng dụng module, hãy đọc hợp đồng resource lookup của API tương ứng và kiểm tra mô hình truy cập thay vì giả định mọi resource đều luôn công khai.

## 13. Cập nhật JAR có sẵn

Công cụ `jar` hỗ trợ cập nhật archive.

Ví dụ đã sửa `resources/app/banner.txt` và muốn thay entry tương ứng:

~~~shell
jar --update --file dist/hello.jar -C resources app/banner.txt
~~~

Với `-C resources app/banner.txt`, entry được cập nhật theo tên tương đối `app/banner.txt`. Không vô tình đặt entry thành `resources/app/banner.txt`, vì khi đó chương trình tra cứu `/app/banner.txt` sẽ không tìm thấy.

Sau cập nhật:

~~~shell
jar --list --file dist/hello.jar
jar --validate --file dist/hello.jar
java -jar dist/hello.jar An
~~~

### 13.1. Khi nào không nên cập nhật trực tiếp archive?

Đối với gói phát hành chính thức, nhiều hệ thống có quy trình:

1. Biên dịch lại từ một phiên bản source xác định.
2. Đóng gói JAR mới.
3. Chạy kiểm thử và kiểm tra dependency.
4. Tính checksum/ký số và công bố artifact đã kiểm thử.

Sửa trực tiếp JAR đã ký hoặc artifact đã phát hành có thể làm hỏng chữ ký, làm lệch checksum hoặc khiến nội dung không còn khớp với mã nguồn và pipeline build.

Trong môi trường triển khai nghiêm ngặt, thường nên **rebuild** và tạo artifact phát hành mới thay vì chắp vá JAR ngay tại nơi chạy.

## 14. JAR và Java Platform Module System (JPMS)

Java hỗ trợ mô hình module để khai báo tên module, dependency và khả năng truy cập package.

Điểm phân biệt:

- **JAR không có `module-info.class`**: là JAR thông thường trên class path; khi đặt trên module path, có thể trở thành **automatic module**.
- **JAR có `module-info.class` ở gốc**: là **modular JAR**; khi đặt trên module path, được xem như explicit named module.
- **JAR có modular metadata nhưng đặt trên class path**: mã của nó hoạt động theo cơ chế class path, không trở thành explicit named module chỉ vì file bên trong có `module-info.class`.

Manifest `Main-Class` và module descriptor giải quyết các vấn đề có liên quan nhưng khác nhau. Không xem `Automatic-Module-Name` là thay thế hoàn chỉnh cho `module-info.java`.

### 14.1. Ví dụ tạo modular JAR

Cấu trúc:

~~~text
modular-demo/
└── modsrc/
    └── com.example.greeting/
        ├── module-info.java
        └── com/
            └── example/
                └── greeting/
                    └── Main.java
~~~

File `modsrc/com.example.greeting/module-info.java`:

~~~java
module com.example.greeting {
}
~~~

Module trên không khai báo dependency bên ngoài `java.base`. Các type trong `java.base` được module Java đọc mặc định.

File `modsrc/com.example.greeting/com/example/greeting/Main.java`:

~~~java
package com.example.greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println("Xin chào từ modular JAR!");
    }
}
~~~

Tạo thư mục đích.

Linux/macOS:

~~~shell
mkdir -p build/mods/com.example.greeting dist
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/mods/com.example.greeting, dist
~~~

Biên dịch:

~~~shell
javac --release 27 -encoding UTF-8 -d build/mods/com.example.greeting modsrc/com.example.greeting/module-info.java modsrc/com.example.greeting/com/example/greeting/Main.java
~~~

Tạo modular JAR, đồng thời khai báo main class trong metadata module:

~~~shell
jar --create --file dist/com.example.greeting.jar --main-class com.example.greeting.Main -C build/mods/com.example.greeting .
~~~

Kiểm tra:

~~~shell
jar --describe-module --file dist/com.example.greeting.jar
~~~

Lệnh trên cho biết module tường minh `com.example.greeting` và metadata chính liên quan.

Khởi chạy theo **module path**:

~~~shell
java --module-path dist/com.example.greeting.jar --module com.example.greeting
~~~

Kết quả:

~~~text
Xin chào từ modular JAR!
~~~

Có thể chỉ định class điểm vào nếu cần:

~~~shell
java --module-path dist/com.example.greeting.jar --module com.example.greeting/com.example.greeting.Main
~~~

Đây là cơ chế chạy module, khác với `java -jar`. Khi sử dụng `java -jar`, điểm vào của archive phải được khai báo theo cách launcher yêu cầu bằng manifest `Main-Class`; trong khi `java --module` có thể dùng main class được ghi trong module descriptor.

### 14.2. Cần exports trong module-info.java không?

Một ứng dụng chỉ có main class và không cung cấp API cho module khác không nhất thiết phải `exports` package chứa main class.

Với thư viện modular JAR cung cấp API cho module khác, cần xuất package cần dùng:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Một module khác muốn truy cập API đó có thể khai báo `requires com.example.library;`, sau khi các module được đặt đúng trên module path.

`exports` không biến mọi class trong module thành public, và `opens` (dành cho khả năng truy cập phản chiếu) có ý nghĩa khác. Không dùng `opens` đại trà chỉ để xử lý vấn đề đóng gói thiếu class.

## 15. Automatic-Module-Name và tên JAR

Một JAR không có module descriptor có thể được sử dụng trên module path như **automatic module**.

Nếu muốn tên automatic module ổn định và chủ động, có thể đặt trong manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.greeter

~~~

Khi JAR như vậy không có `module-info.class` và được đặt trên module path, tên này được ưu tiên theo quy tắc automatic module.

Nếu không có `Automatic-Module-Name`, tên automatic module có thể được suy từ tên tệp JAR theo quy tắc module finder. Đừng dựa vào tên tự suy nếu thư viện được đổi tên hoặc phiên bản artifact có thể thay đổi.

`Automatic-Module-Name` **không** khai báo `requires`, `exports` hoặc mô hình dịch vụ tường minh như một module descriptor. Nếu cần ranh giới module rõ ràng, nên tạo `module-info.java` và xuất bản modular JAR phù hợp.

## 16. Multi-release JAR: lựa chọn khi hỗ trợ nhiều mức Java

Một **multi-release JAR** cho phép một JAR cung cấp phiên bản class/resource phù hợp với nhiều mức Java.

Cấu trúc khái quát:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 21/
│           └── com/example/lib/Feature.class
└── com/example/lib/Feature.class
~~~

Manifest có:

~~~text
Multi-Release: true
~~~

Khi chạy trên Java phù hợp, runtime chọn phiên bản class cao nhất không vượt quá mức Java hiện tại, theo thứ tự và quy tắc của JAR spec.

JDK `jar` hỗ trợ `--release N` khi đóng gói các class riêng theo mức Java:

~~~shell
jar --create --file dist/lib-mr.jar -C build/base . --release 21 -C build/java21 .
~~~

Lệnh này chỉ có ý nghĩa khi `build/base` và `build/java21` đã chứa các class được biên dịch với `--release` phù hợp và cùng thiết kế API hợp lệ. Các class phiên bản cao cần thỏa quy tắc tương thích API mà JAR spec yêu cầu.

**Không cần multi-release JAR** nếu dự án chỉ chạy trên Java 27 và không phải phân phối chung cho các mức Java cũ hơn. Tránh tăng độ phức tạp đóng gói khi không có yêu cầu hỗ trợ nhiều runtime.

## 17. Version của JAR và tính tương thích runtime

Có hai khái niệm dễ bị nhầm:

- **Phiên bản artifact/thư viện**, ví dụ `1.2.3` trong metadata build hoặc manifest.
- **Phiên bản class file và Java API mục tiêu**, quyết định runtime nào có thể nạp và thực thi class.

Ví dụ:

~~~shell
javac --release 27 -d build/classes src/com/example/app/Main.java
~~~

tạo class cho mức Java 27. Một runtime Java cũ hơn có thể ném `UnsupportedClassVersionError` khi gặp class có phiên bản bytecode cao hơn khả năng hỗ trợ.

Ngược lại:

~~~text
Implementation-Version: 1.2.3
~~~

chỉ biểu diễn phiên bản implementation trong metadata; giá trị này **không tự khiến bytecode tương thích** với runtime thấp hơn.

Nếu cần hỗ trợ nhiều mức JDK, hãy xác định yêu cầu tối thiểu, biên dịch bằng `--release` phù hợp, kiểm tra dependency tương thích và chạy thử trên các runtime được hỗ trợ.

## 18. Tái lập build và tính toàn vẹn artifact

Một JAR không chỉ cần “chạy được trên máy người viết”. Khi phát hành, cần xác nhận nội dung và nguồn gốc.

### 18.1. Quy tắc kiểm tra tối thiểu

Sau khi tạo JAR:

~~~shell
jar --list --file dist/hello.jar
jar --validate --file dist/hello.jar
java -jar dist/hello.jar An
~~~

Kiểm tra:

1. `META-INF/MANIFEST.MF` tồn tại và có `Main-Class` đúng.
2. Class của điểm vào nằm đúng package.
3. Tài nguyên được đặt đúng vị trí được dùng bởi `getResourceAsStream`.
4. Dependency thực sự có mặt trên class path/module path theo cách chạy.
5. Ứng dụng chạy trên runtime được phát hành/hỗ trợ.
6. Không có entry trùng tên hoặc tên archive bất thường.
7. Các file kết quả được tạo từ source và phiên bản dependency đã được kiểm soát.

### 18.2. Timestamp và reproducible build

Khi tạo archive, timestamp của entry và cách sắp xếp/nén có thể ảnh hưởng đến byte đầu ra. Công cụ `jar` hỗ trợ `--date` để chỉ định timestamp cho entry khi tạo hoặc cập nhật:

~~~shell
jar --create --date=2026-11-01T00:00:00Z --file dist/hello.jar --main-class com.example.app.Main -C build/classes . -C resources .
~~~

Đây **chỉ là một yếu tố** hỗ trợ tính tái lập. Để tạo artifact giống byte trên nhiều máy, còn cần cố định phiên bản JDK, dependency, cách sinh class/resource, metadata và công cụ build. Không tuyên bố rằng chỉ đặt `--date` thì mọi build sẽ cho checksum giống nhau.

### 18.3. JAR và chữ ký số

Một JAR có thể chứa các entry chữ ký trong `META-INF`. Chữ ký số dùng để xác thực nguồn gốc/tính toàn vẹn theo cơ chế tương ứng, **khác** việc chỉ kiểm tra ZIP hay chạy `jar --validate`.

Nếu phân phối artifact cần xác thực, hãy có quy trình ký và kiểm tra chữ ký phù hợp, đồng thời bảo vệ khóa ký. Khi cập nhật entry trong một JAR đã ký, phải xem xét ký lại artifact theo quy trình phát hành; không coi chữ ký cũ vẫn có hiệu lực.

## 19. Lỗi thường gặp khi tạo executable JAR

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `no main manifest attribute, in app.jar` | Thiếu `Main-Class` trong manifest | Tạo lại bằng `--main-class` hoặc manifest hợp lệ |
| `Could not find or load main class ...` | Tên class sai, thiếu class, cấu trúc package sai | Kiểm tra `jar --list` và tên `Main-Class` |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu dependency trên class path khi chạy | Đặt thư viện đúng chỗ, cấu hình `Class-Path` hoặc dùng module path |
| Tài nguyên trả `null` | Không đóng gói resource hoặc đường dẫn sai | Thêm `-C resources .`, kiểm tra tên entry |
| `UnsupportedClassVersionError` | Chạy class build cho mức Java mới hơn runtime | Chọn runtime tương thích hoặc biên dịch bằng `--release` thích hợp |
| Chạy bằng `-jar` nhưng `-cp` không có tác dụng | Chế độ `-jar` bỏ qua class path do `-cp` cung cấp | Dùng manifest `Class-Path` hoặc `java -cp ... MainClass` |
| Manifest có `Main-Class` nhưng JVM vẫn không đọc được | Sai tên/encoding/cú pháp manifest hoặc thiếu dòng kết thúc | Kiểm tra manifest thực và tạo bằng công cụ chuẩn |
| JAR không chứa tài nguyên mặc dù build/classes có class | Tài nguyên không được copy vào archive | Thêm resource root vào lệnh jar |
| `InvalidModuleDescriptorException` | Module descriptor/package/module graph không hợp lệ | Kiểm tra `module-info.java`, biên dịch và tạo lại |
| `FindException` khi chạy module | Không tìm được module hoặc dependency trên module path | Kiểm tra `--module-path` và `jar --describe-module` |
| Runtime không có Java phù hợp | Máy đích thiếu runtime, JDK/JRE không tương thích | Phát hành hướng dẫn runtime hoặc đóng gói bằng jpackage/jlink |
| JAR chạy trên máy phát triển nhưng không chạy trên máy khác | Thiếu thư viện, resource, tùy chọn runtime hoặc khác biệt hệ điều hành | Kiểm thử gói phân phối như một đơn vị độc lập |
| JAR chứa thư viện con nhưng không nạp được class | Nested JAR không tự vào class path | Dùng launcher chuyên dụng, thin JAR hay uber JAR đúng cách |
| `jar --validate` báo lỗi | Entry bất thường, trùng tên hoặc vấn đề liên quan multi-release | Xác định nguyên nhân và build lại artifact |

### 19.1. Quy trình gỡ lỗi nhanh

Khi `java -jar app.jar` thất bại, kiểm tra theo trình tự:

~~~text
Có thể mở JAR?
    |
    v
jar --list --file app.jar
    |
    v
META-INF/MANIFEST.MF có tồn tại?
    |
    v
Main-Class có đúng tên đầy đủ?
    |
    v
Class tương ứng có trong archive?
    |
    v
Resource và dependency có sẵn?
    |
    v
Runtime có hỗ trợ class/API?
    |
    v
Chạy với java -jar và xem stack trace thực tế
~~~

Nên ưu tiên sửa nguyên nhân theo mô hình đóng gói, thay vì thêm ngẫu nhiên nhiều đường dẫn class path hoặc bỏ các kiểm tra của JDK.

## 20. Lựa chọn mô hình phân phối phù hợp

| Yêu cầu | Hướng làm phù hợp |
|---|---|
| Thư viện nhỏ cho ứng dụng khác | Library JAR có API/package rõ ràng |
| CLI đơn giản, không có dependency ngoài | Executable JAR bằng `jar --main-class` |
| CLI cần vài JAR phụ thuộc | Thin JAR + manifest `Class-Path` hoặc class path tường minh |
| Muốn một artifact chứa lớp ứng dụng và dependency | Uber/shaded JAR với plugin build phù hợp |
| Ứng dụng có dependency theo JPMS | Modular JAR và `java --module-path --module` |
| Muốn bản phân phối có runtime đi kèm | `jlink` / `jpackage` tùy loại ứng dụng |
| Thư viện cần chạy trên nhiều mức JDK | `--release` phù hợp; multi-release JAR nếu thực sự cần |
| Cần phân phối có thể xác thực | Kiểm soát dependency, checksum và ký số theo chính sách phát hành |

**Điểm cốt lõi:** Một executable JAR chỉ giải quyết vấn đề chọn class khởi động. Việc cung cấp runtime, thư viện phụ thuộc, cấu hình, tài nguyên, quyền truy cập hệ điều hành và kiểm soát phiên bản vẫn cần được thiết kế riêng.

## 21. Bài tập thực hành

### Bài tập 1: Tạo JAR thư viện

Từ ví dụ `hello-project`:

1. Biên dịch class vào `build/classes`.
2. Tạo `dist/hello-library.jar` **không cần** main class.
3. Liệt kê và xác nhận tồn tại `com/example/app/Main.class`.
4. Chạy bằng `java -cp ... com.example.app.Main` với tài nguyên ở class path.

**Câu hỏi:** Vì sao `java -jar dist/hello-library.jar` không chạy được nếu manifest không có `Main-Class`?

### Bài tập 2: Tạo executable JAR

1. Đóng gói class và `app/banner.txt` vào JAR.
2. Khai báo `--main-class com.example.app.Main`.
3. Chạy `java -jar dist/hello.jar An`.
4. Thay nội dung resource, đóng gói lại và xem output.

**Câu hỏi:** Nếu JAR chỉ chứa class mà không chứa `banner.txt`, lỗi xảy ra ở compile time hay runtime? Vì sao?

### Bài tập 3: Dependency ở ngoài JAR

1. Tạo `greeter.jar` như ví dụ phần `Class-Path`.
2. Biên dịch `Runner` với `--class-path`.
3. Đóng gói `app.jar` và khai báo `Class-Path: lib/greeter.jar`.
4. Chạy và xác nhận kết quả.
5. Đổi tên hoặc tạm di chuyển thư viện phụ thuộc và quan sát lỗi.

**Câu hỏi:** Khi thay bằng `java -cp ... com.example.cli.Runner`, giá trị `Main-Class` trong manifest còn được dùng để chọn điểm vào không?

### Bài tập 4: Modular JAR

1. Tạo `module-info.java` và class `Main`.
2. Biên dịch và tạo modular JAR.
3. Chạy `jar --describe-module` để kiểm tra metadata.
4. Chạy `java --module-path ... --module ...`.

**Câu hỏi:** Điểm khác giữa `Main-Class` trong manifest và main class gắn với module là gì? Một JAR không có `module-info.class` có thể xuất hiện trên module path theo cơ chế nào?

## 22. Checklist trước khi công bố JAR

- [ ] JAR chứa class ở đường dẫn package đúng.
- [ ] Resource được đóng gói theo đường dẫn mà mã Java sử dụng.
- [ ] Điểm vào `Main-Class` đúng nếu phát hành executable JAR theo `-jar`.
- [ ] Manifest đúng định dạng, có dòng kết thúc và không bị lỗi encoding.
- [ ] Dependency được cung cấp đầy đủ, không phụ thuộc ngẫu nhiên vào máy phát triển.
- [ ] Đã phân biệt `-jar`, `-cp` và `--module-path`.
- [ ] Nếu là modular JAR, `module-info.class` ở vị trí và có metadata đúng.
- [ ] Nếu hỗ trợ nhiều runtime, cấu hình `--release` và dependency tương thích.
- [ ] Đã kiểm tra archive bằng `jar --list` và `jar --validate`.
- [ ] Đã chạy thử trên một môi trường giống máy đích.
- [ ] Có kiểm soát phiên bản artifact, thông tin dependency và nguồn gốc.
- [ ] Có chiến lược kiểm tra chữ ký/checksum nếu phạm vi phát hành yêu cầu.

## 23. Tóm tắt

- **JAR là ZIP dành cho việc đóng gói class, resource và metadata Java.**
- Lệnh `jar --create --file ... -C directory .` đóng gói class theo đúng đường dẫn package.
- `--main-class` giúp tạo executable JAR; `java -jar` dựa vào manifest `Main-Class` để khởi động.
- Manifest nằm tại `META-INF/MANIFEST.MF` và có cú pháp riêng, bao gồm quy tắc xuống dòng và giới hạn 72 byte UTF-8 mỗi dòng.
- `Class-Path` trong manifest tham chiếu các thư viện phụ thuộc bằng relative URL, không có chức năng tải dependency tự động.
- Khi chạy `java -jar`, không trông đợi `-cp` bổ sung dependency cho ứng dụng; phải chọn chiến lược class path thích hợp.
- **Library JAR, executable JAR và modular JAR** là những khái niệm có thể giao nhau nhưng không đồng nghĩa.
- `module-info.class` giúp định nghĩa explicit module; `Automatic-Module-Name` chỉ giúp đặt tên automatic module khi phù hợp.
- Không nhầm một nested JAR với dependency đã được Java launcher tự nạp.
- Đảm bảo bytecode, tài nguyên và dependency phù hợp với runtime được hỗ trợ.
- Kiểm tra và phát hành JAR như một artifact có thể tái lập, có nguồn gốc và được kiểm thử.

## Tài liệu chính thức Java SE 27

- [The jar Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html)
- [The java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [JAR File Specification — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/jar/jar.html)
- [JarFile API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/jar/JarFile.html)
- [Manifest API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/jar/Manifest.html)
- [Module System — java.lang.Module API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Module.html)
- [The jdeps Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html)
- [The jlink Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html)
- [The jpackage Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html)
