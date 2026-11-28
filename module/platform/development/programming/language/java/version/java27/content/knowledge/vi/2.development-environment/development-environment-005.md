# Biên dịch và chạy chương trình Java bằng dòng lệnh

Dòng lệnh giúp bạn hiểu rõ từng bước một chương trình Java được biên dịch, nạp và thực thi như thế nào. Với JDK 27, các công cụ chính cho quy trình này là **javac** (trình biên dịch), **java** (trình khởi chạy ứng dụng) và **jar** (công cụ đóng gói).

Bài viết sử dụng cú pháp và công cụ hiện hành của JDK 27. Các ví dụ dùng dạng phương thức khởi chạy quen thuộc `public static void main(String[] args)`, vẫn được Java 27 hỗ trợ.

## 1. Hiểu quy trình biên dịch và chạy

Mã nguồn Java thường nằm trong các file có phần mở rộng `.java`. Trình biên dịch `javac` chuyển mã nguồn thành bytecode và ghi kết quả vào các file `.class`. Khi chạy ứng dụng, lệnh `java` khởi động Java Virtual Machine (JVM), nạp các lớp cần thiết rồi thực thi chương trình.

Quy trình cơ bản:

~~~text
Main.java
   |
   | javac
   v
Main.class (bytecode)
   |
   | java
   v
JVM thực thi chương trình
~~~

Ba công cụ có vai trò khác nhau:

| Công cụ | Vai trò | Khi nào dùng |
|---|---|---|
| `javac` | Biên dịch mã nguồn `.java` thành bytecode `.class` | Khi muốn chủ động kiểm soát bước biên dịch và thư mục đầu ra |
| `java` | Khởi chạy lớp đã biên dịch, ứng dụng JAR, module hoặc mã nguồn ở source-file mode | Khi muốn thực thi ứng dụng |
| `jar` | Tạo, liệt kê, cập nhật hoặc giải nén tệp JAR | Khi muốn đóng gói lớp và tài nguyên để phân phối |

Các công cụ này được cung cấp bởi **JDK**. Vì vậy, để vừa biên dịch vừa chạy chương trình, hãy sử dụng một bản JDK có cả `javac` và `java`.

## 2. Kiểm tra JDK đang được sử dụng

Mở Terminal, Command Prompt hoặc PowerShell và chạy:

~~~shell
java --version
javac --version
~~~

Nếu đang sử dụng JDK 27, cả hai lệnh cần cho thấy phiên bản 27. Hai lệnh có thể trả về phiên bản khác nhau nếu máy có nhiều bản JDK và biến môi trường `PATH` đang trỏ đến các thư mục khác nhau. Hãy kiểm tra cả hai để chắc chắn trình biên dịch và trình chạy thuộc bộ JDK dự định sử dụng.

Có thể kiểm tra đường dẫn lệnh được hệ điều hành tìm thấy:

**Windows PowerShell**

~~~powershell
Get-Command java
Get-Command javac
~~~

**Windows Command Prompt**

~~~bat
where.exe java
where.exe javac
~~~

**Linux hoặc macOS**

~~~shell
command -v java
command -v javac
~~~

Nếu `java` chạy được nhưng `javac` không được nhận diện, hãy kiểm tra xem máy đã cài JDK hay chưa và `PATH` có trỏ đến thư mục `bin` của đúng JDK hay không. Biến `JAVA_HOME`, nếu được cấu hình, nên trỏ đến thư mục gốc của JDK; `PATH` cần chứa thư mục `bin` bên trong thư mục đó. Sau khi thay đổi biến môi trường, mở một cửa sổ Terminal mới rồi kiểm tra lại.

## 3. Biên dịch và chạy một chương trình

### 3.1. Tạo cấu trúc thư mục và mã nguồn

Tạo một thư mục dự án với cấu trúc sau:

~~~text
java-cli-demo/
├── src/
│   └── hello/
│       ├── Greeter.java
│       └── Main.java
└── out/
~~~

Thư mục `src` chứa mã nguồn. Thư mục `out` sẽ chứa các file bytecode sau khi biên dịch. Tên thư mục `hello` tương ứng với package `hello` được khai báo trong mã nguồn.

Nội dung file `src/hello/Greeter.java`:

~~~java
package hello;

public class Greeter {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Nội dung file `src/hello/Main.java`:

~~~java
package hello;

import java.util.Arrays;

public class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java 27";

        Greeter greeter = new Greeter();
        System.out.println(greeter.greet(name));
        System.out.println("Tham số: " + Arrays.toString(args));
    }
}
~~~

Lớp `Main` là điểm bắt đầu của ví dụ. Chương trình lấy tham số đầu tiên từ dòng lệnh làm tên người nhận lời chào; nếu không có tham số, chương trình dùng giá trị mặc định.

### 3.2. Biên dịch bằng javac

Đứng tại thư mục gốc `java-cli-demo` và chạy:

~~~shell
javac --release 27 -encoding UTF-8 -d out src/hello/Greeter.java src/hello/Main.java
~~~

Ý nghĩa các thành phần:

- `javac`: gọi trình biên dịch Java.
- `--release 27`: biên dịch theo quy tắc ngôn ngữ, định dạng bytecode và tập API của Java SE 27.
- `-encoding UTF-8`: xác định mã hóa của file nguồn, giúp các chuỗi tiếng Việt được đọc nhất quán.
- `-d out`: ghi các file `.class` vào thư mục `out`. Trình biên dịch tự tạo thư mục này nếu chưa tồn tại.
- Hai đường dẫn cuối là các file nguồn cần biên dịch. Có thể truyền nhiều file trong cùng một lệnh; trình biên dịch xử lý chúng cùng nhau và giải quyết các phụ thuộc giữa những khai báo trong các file đó.

Sau khi biên dịch thành công, cấu trúc đầu ra có dạng:

~~~text
out/
└── hello/
    ├── Greeter.class
    └── Main.class
~~~

Cấu trúc package được giữ lại bên dưới thư mục đầu ra. Dùng thư mục đầu ra riêng giúp mã nguồn và bytecode không bị trộn lẫn.

**Vì sao nên dùng `--release`?**

Khi cần biên dịch cho một phiên bản Java cụ thể, `--release N` đặt đồng thời mức ngôn ngữ, phiên bản bytecode đích và tập API được phép sử dụng của phiên bản đó. Ví dụ trên dùng `--release 27` cho Java 27. Nếu ứng dụng cần chạy trên một phiên bản thấp hơn, hãy chọn một giá trị `N` được trình biên dịch hiện tại hỗ trợ và kiểm tra ứng dụng trên đúng phiên bản runtime mục tiêu.

Không nên chỉ đặt riêng mức ngôn ngữ và mức bytecode rồi giả định rằng chương trình sẽ không gọi API mới hơn. `--release` còn giới hạn API theo phiên bản được chọn.

### 3.3. Chạy lớp đã biên dịch bằng java

Sau khi biên dịch thành công, chạy:

~~~shell
java -cp out hello.Main Phuong 27
~~~

Kết quả:

~~~text
Xin chào, Phuong!
Tham số: [Phuong, 27]
~~~

Giải thích:

- `java` khởi chạy JVM và ứng dụng.
- `-cp out` (viết đầy đủ là `--class-path out`) thêm thư mục `out` vào class path để JVM tìm các lớp đã biên dịch.
- `hello.Main` là tên đầy đủ của lớp, gồm package và tên lớp. Khi chạy theo tên lớp, không thêm đuôi `.class` và không thay dấu chấm package bằng dấu gạch chéo.
- Các giá trị `Phuong` và `27` nằm sau tên lớp nên được truyền vào mảng `args` của phương thức `main`.

Khi không chỉ định class path, Java có thể dùng giá trị mặc định của môi trường. Trong các lệnh học tập và tự động hóa, nên chỉ rõ class path để kết quả không phụ thuộc vào cấu hình ẩn của máy.

## 4. Chạy trực tiếp file nguồn với source-file mode

Với chương trình nhỏ, Java launcher có thể biên dịch và chạy mã nguồn trong một lệnh mà không cần gọi `javac` riêng:

~~~shell
java src/hello/Main.java Phuong 27
~~~

Có thể chỉ rõ phiên bản ngôn ngữ và API bằng tùy chọn `--source`:

~~~shell
java --source 27 src/hello/Main.java Phuong 27
~~~

Ở chế độ này, launcher biên dịch mã nguồn trong bộ nhớ rồi thực thi lớp đầu tiên phù hợp trong file nguồn. Các đối số đặt sau đường dẫn file nguồn được truyền cho chương trình. Với cấu trúc package đúng quy ước, launcher cũng có thể tìm và biên dịch những file nguồn khác mà chương trình cần. Khả năng chạy chương trình gồm nhiều file nguồn được bổ sung từ JDK 22 và tiếp tục có trong JDK 27.

Source-file mode hữu ích khi thử nghiệm nhanh, học cú pháp hoặc chạy một tiện ích nhỏ. Khi cần giữ lại file `.class`, kiểm soát đầy đủ tùy chọn biên dịch, xử lý annotation processor hoặc tạo đầu ra có thể đóng gói, hãy dùng quy trình `javac` rồi `java` ở phần trước.

## 5. Làm việc với nhiều file và thư viện

### 5.1. Biên dịch nhiều file nguồn

Khi chương trình gồm nhiều lớp, có thể liệt kê các file nguồn cần biên dịch trong cùng một lệnh:

~~~shell
javac --release 27 -encoding UTF-8 -d out src/hello/Greeter.java src/hello/Main.java
~~~

Nếu một lớp tham chiếu đến lớp khác, hãy bảo đảm trình biên dịch có thể tìm thấy khai báo tương ứng. Với dự án nhỏ, truyền các file nguồn liên quan trực tiếp thường là cách dễ hiểu nhất. Với cây mã nguồn lớn hơn, có thể dùng `--source-path` để chỉ định nơi tìm thêm file nguồn.

### 5.2. Dùng class path cho thư viện

Một ứng dụng có thể phụ thuộc vào các thư viện bên ngoài được cung cấp dưới dạng file JAR. Khi biên dịch, dùng `-cp` hoặc `--class-path` để chỉ định nơi tìm các lớp và annotation processor cần thiết.

Ví dụ, thư mục `lib` chứa các thư viện JAR:

~~~shell
javac --release 27 -cp "lib/*" -d out src/hello/Greeter.java src/hello/Main.java
~~~

Khi chạy, phải cung cấp cả thư mục chứa lớp ứng dụng và các thư viện cần thiết.

Dấu phân cách giữa các mục trong class path phụ thuộc hệ điều hành:

| Hệ điều hành | Dấu phân cách | Ví dụ chạy ứng dụng |
|---|---|---|
| Windows | Dấu chấm phẩy `;` | `java -cp "out;lib/*" hello.Main Phuong` |
| Linux và macOS | Dấu hai chấm `:` | `java -cp "out:lib/*" hello.Main Phuong` |

Ký tự `*` trong `lib/*` cho phép Java launcher tìm các JAR trong thư mục `lib`. Hãy đặt toàn bộ class path trong dấu nháy kép để tránh shell diễn giải các ký tự đặc biệt theo cách không mong muốn.

Class path dùng để tìm các lớp và thư viện không được tổ chức thành module. Nếu thư viện hoặc ứng dụng sử dụng Java Platform Module System, hãy cấu hình module path thay vì coi mọi thư viện đều là thành phần trên class path.

## 6. Đóng gói và chạy ứng dụng JAR

Khi muốn phân phối chương trình dưới dạng một tệp JAR, trước tiên hãy biên dịch các file nguồn vào `out`. Với một JAR thực thi thông thường, tạo file manifest có nội dung sau và lưu thành `manifest.mf` ở thư mục gốc dự án:

~~~text
Main-Class: hello.Main

~~~

Thuộc tính `Main-Class` khai báo lớp khởi chạy. Sau đó, tạo JAR bằng lệnh:

~~~shell
jar --create --file app.jar --manifest manifest.mf -C out .
~~~

Ý nghĩa:

- `--create`: tạo một tệp lưu trữ mới.
- `--file app.jar`: đặt tên tệp đầu ra là `app.jar`.
- `--manifest manifest.mf`: thêm thông tin manifest, trong đó có lớp khởi chạy.
- `-C out .`: chuyển vào thư mục `out` và đưa nội dung của thư mục đó vào JAR, giữ nguyên cấu trúc package.

Chạy ứng dụng:

~~~shell
java -jar app.jar Phuong
~~~

Có thể xem danh sách nội dung của JAR bằng:

~~~shell
jar --list --file app.jar
~~~

Tùy chọn `-jar` yêu cầu JAR có thông tin lớp chính trong manifest. Khi chạy theo cách này, các thiết lập class path khác trên dòng lệnh bị bỏ qua. Nếu ứng dụng cần thư viện bên ngoài, hãy đóng gói hoặc cấu hình đường dẫn phụ thuộc phù hợp trong quá trình phân phối; không giả định rằng chỉ tạo một JAR từ thư mục `out` là đã bao gồm mọi thư viện.

## 7. Chạy ứng dụng sử dụng Java module

Với ứng dụng dùng Java Platform Module System, mã nguồn thường có file `module-info.java`. Ví dụ cấu trúc:

~~~text
modular-demo/
└── src/
    └── hello.app/
        ├── module-info.java
        └── hello/
            └── Main.java
~~~

Nội dung `src/hello.app/module-info.java`:

~~~java
module hello.app {
}
~~~

Nội dung `src/hello.app/hello/Main.java` có thể dùng lớp `Main` với phương thức khởi chạy quen thuộc. Biên dịch module:

~~~shell
javac --module-source-path src -d out -m hello.app
~~~

Chạy module:

~~~shell
java --module-path out -m hello.app/hello.Main
~~~

Ở đây, `--module-source-path` chỉ định nơi chứa mã nguồn của các module; `--module-path` chỉ định nơi tìm các module đã biên dịch; `-m` chọn module và lớp khởi chạy. Khi ứng dụng có nhiều module phụ thuộc lẫn nhau, cần khai báo quan hệ module và cung cấp đầy đủ module cần thiết trên module path.

Đối với chương trình chưa sử dụng module, ví dụ class path ở các phần trước thường đơn giản hơn.

## 8. Một số tùy chọn javac và java thường dùng

| Tùy chọn | Công dụng |
|---|---|
| `--release 27` | Biên dịch theo quy tắc ngôn ngữ, bytecode và API của Java 27 |
| `-d out` | Chỉ định thư mục ghi file `.class` |
| `-encoding UTF-8` | Chỉ định mã hóa file nguồn |
| `-cp` hoặc `--class-path` | Chỉ định nơi tìm lớp và thư viện trên class path |
| `-Xlint` | Bật các cảnh báo lint được khuyến nghị để phát hiện vấn đề trong mã nguồn |
| `--source-path` | Chỉ định nơi tìm thêm file nguồn khi biên dịch |
| `--module-path` hoặc `-p` | Chỉ định nơi tìm module |
| `--enable-preview` | Cho phép dùng tính năng ngôn ngữ preview khi kết hợp với mức release/source phù hợp |

Nếu mã nguồn sử dụng một tính năng preview của Java 27, cần bật preview trong cả bước biên dịch và bước chạy. Ví dụ:

~~~shell
javac --enable-preview --release 27 -d out src/hello/Main.java
java --enable-preview -cp out hello.Main
~~~

Chỉ thêm tùy chọn này khi mã nguồn thực sự sử dụng tính năng preview. Với mã Java thông thường, không cần bật preview.

Để xem tùy chọn được hỗ trợ bởi bộ JDK đang cài, dùng:

~~~shell
javac --help
java --help
jar --help
~~~

## 9. Xử lý các lỗi thường gặp

| Thông báo hoặc hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| `java` hoặc `javac` không được nhận diện | JDK chưa được cài, hoặc thư mục `bin` của JDK chưa có trong `PATH` | Kiểm tra đường dẫn bằng `Get-Command`, `where.exe` hoặc `command -v`; cập nhật cấu hình JDK rồi mở Terminal mới |
| `javac` và `java` hiển thị hai phiên bản khác nhau | Hai lệnh được phân giải từ hai bản cài đặt khác nhau | Kiểm tra đường dẫn của từng lệnh và cấu hình để dùng cùng bộ JDK |
| `error: file not found` | Đường dẫn file nguồn không đúng với thư mục hiện tại | Kiểm tra thư mục làm việc và đường dẫn tương đối; có thể dùng đường dẫn tuyệt đối |
| `Could not find or load main class` | Class path không chứa thư mục gốc của package, hoặc tên lớp khởi chạy không đúng | Nếu lớp là `hello.Main`, class path phải trỏ đến thư mục cha của `hello`, ví dụ `out`; chạy bằng tên đầy đủ `hello.Main` |
| `NoClassDefFoundError` hoặc `ClassNotFoundException` | Thiếu lớp hoặc thư viện cần thiết khi chạy | Bổ sung thư mục hoặc JAR phụ thuộc vào class path; nếu dùng module, kiểm tra module path và khai báo module |
| `UnsupportedClassVersionError` | Runtime đang dùng không hỗ trợ phiên bản bytecode mà trình biên dịch đã tạo | Chạy bằng JDK tương thích hoặc biên dịch lại với `--release` phù hợp với runtime mục tiêu |
| Ký tự tiếng Việt hiển thị sai | Mã hóa file nguồn hoặc cấu hình Terminal không phù hợp | Lưu file nguồn bằng UTF-8 và biên dịch với `-encoding UTF-8`; kiểm tra encoding của Terminal |
| Không tìm thấy phương thức khởi chạy | Lớp được chọn không có entry point hợp lệ | Kiểm tra lớp chính và phương thức khởi chạy; trong các ví dụ cơ bản của bài này, dùng `public static void main(String[] args)` |

Nên phân biệt lỗi biên dịch và lỗi khi chạy. Lỗi cú pháp, kiểu dữ liệu hoặc không tìm thấy khai báo cần thiết thường xuất hiện trong bước `javac`. Lỗi thiếu thư viện, không tìm thấy lớp khởi chạy hoặc lỗi logic thường chỉ xuất hiện khi thực thi bằng `java`.

## 10. Quy trình thực hành đề xuất

Khi làm việc với một chương trình Java bằng dòng lệnh, có thể theo trình tự sau:

1. Mở Terminal tại thư mục dự án.
2. Chạy `java --version` và `javac --version` để xác nhận đúng bộ JDK.
3. Kiểm tra file nguồn, tên package và cấu trúc thư mục.
4. Biên dịch bằng `javac`, chỉ rõ `--release`, encoding và thư mục đầu ra khi cần.
5. Nếu biên dịch thành công, chạy lớp bằng `java` với class path hoặc module path phù hợp.
6. Nếu cần phân phối ứng dụng, tạo JAR và kiểm tra manifest cũng như các thư viện phụ thuộc.
7. Khi có lỗi, xác định lỗi xảy ra ở bước biên dịch, tìm lớp/thư viện hay lúc thực thi để chọn đúng hướng xử lý.

Source-file mode là lựa chọn thuận tiện để chạy nhanh một chương trình nhỏ. Khi dự án có nhiều file, thư viện, module, quy trình đóng gói hoặc cần tái lập kết quả giữa các môi trường, hãy dùng các bước biên dịch và chạy tường minh; với dự án lớn, có thể kết hợp công cụ build để quản lý phụ thuộc và quy trình build.

## Tài liệu tham khảo chính thức

- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [The jar Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html)
- [Launching Simple Source-Code Programs — dev.java](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)
- [Java SE 27 Specifications](https://docs.oracle.com/en/java/javase/27/docs/specs/index.html)
