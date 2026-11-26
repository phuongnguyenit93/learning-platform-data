# Giới hạn khi làm việc với module, annotation processor và quy trình biên dịch phức tạp

Java launcher có thể biên dịch và chạy chương trình từ nhiều file `.java` mà không cần tạo cấu hình dự án trước. Chế độ này được gọi là *source-file mode* và được mở rộng để hỗ trợ nhiều file từ Java 22 theo JEP 458. Khi chạy `java Main.java`, launcher biên dịch file chính cùng các file nguồn cần thiết trong source tree rồi chạy chương trình.

Source-file mode rất tiện cho ví dụ, công cụ nhỏ, thử nghiệm và chương trình có cấu trúc vừa phải. Tuy nhiên, nó có quy tắc riêng về phạm vi source tree, module, class loader và compiler options. Đặc biệt, annotation processing bị tắt và launcher không cung cấp toàn bộ tùy chọn của `javac`. Vì vậy, với dự án cần nhiều module nguồn, sinh mã hoặc quy trình build kiểm soát chặt, hãy dùng `javac` trực tiếp hoặc build tool.

JEP 458 là tính năng chính thức từ Java 22, không phải preview. Các giới hạn và ví dụ trong bài được đối chiếu với tài liệu `java` của JDK 27, feature release mới nhất tại thời điểm biên soạn.

## 1. Source-file mode biên dịch nhiều file như thế nào?

Giả sử dự án có cấu trúc:

```text
project/
└── src/
    └── com/
        └── example/
            └── app/
                ├── Main.java
                └── Greeter.java
```

`Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(new Greeter().greet(name));
    }
}
```

`Greeter.java`:

```java
package com.example.app;

public class Greeter {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Chạy từ thư mục `project`:

```bash
java src/com/example/app/Main.java Phuong
```

Kết quả:

```text
Xin chào, Phuong!
```

Launcher chọn source-file mode vì đối số đầu tiên là file `.java`. Nó biên dịch `Main.java` trong bộ nhớ và tìm `Greeter.java` trong source tree khi cần kiểu `Greeter`. Các file nguồn khác được biên dịch theo nhu cầu trong quá trình nạp lớp, thay vì nhất thiết biên dịch tất cả ngay trước khi chương trình bắt đầu chạy.

Nếu chương trình cần thư viện đã biên dịch, có thể đưa class path vào trước file nguồn:

```bash
java --class-path "lib/*" src/com/example/app/Main.java Phuong
```

Các đối số xuất hiện sau tên file nguồn được truyền cho `main`. Vì vậy, hãy đặt tùy chọn của launcher trước file `.java` và đặt đối số của ứng dụng sau file đó.

## 2. Source root được xác định từ package của file khởi chạy

Launcher suy ra gốc source tree từ package khai báo trong file được khởi chạy. Ví dụ, nếu `Main.java` khai báo `package com.example.app` và nằm ở `src/com/example/app/Main.java`, source root được suy ra là `src`.

Source root này được dùng làm source path để tìm các file `.java` khác mà chương trình cần. Vì vậy:

- File nguồn nên được đặt trong thư mục tương ứng với package của nó.
- Các package khác nên nằm dưới cùng source root theo cấu trúc thư mục tương ứng.
- Chỉ các file nguồn có thể tìm thấy trong source tree suy ra từ file khởi chạy mới tham gia cơ chế biên dịch theo nhu cầu này.
- Source-file mode không cung cấp tùy chọn compiler tổng quát để tùy ý truyền một source path khác như khi gọi `javac`.

File được khởi chạy phải chứa một hoặc nhiều top-level class; top-level class đầu tiên được chọn làm class chạy và phải có entry `main` hợp lệ. Launcher cũng dùng một class loader riêng cho các class biên dịch từ source tree. Class đã biên dịch trên application class path không thể tham chiếu ngược đến class chỉ được khai báo trong các file nguồn của lần chạy này. Nếu class path đã có class trùng tên với class khởi chạy, việc chạy sẽ báo lỗi.

Do biên dịch theo nhu cầu, một lỗi biên dịch trong file phụ có thể chỉ xuất hiện khi chương trình lần đầu cần nạp class đó. Điều này khác với quy trình build thông thường vốn thường biên dịch toàn bộ source set trước khi chạy ứng dụng.

## 3. Giới hạn khi làm việc với module

Source-file mode vẫn có thể chạy chương trình thuộc một named module. Nếu `module-info.java` nằm ở source root được suy ra, launcher dùng khai báo module đó để đặt toàn bộ các file nguồn được biên dịch trong source tree vào cùng một module. Nếu không có `module-info.java`, các file nguồn được biên dịch trong unnamed module.

Ví dụ một source tree thuộc một module:

```text
project/
└── src/
    ├── module-info.java
    └── com/
        └── example/
            └── app/
                └── Main.java
```

`module-info.java`:

```java
module com.example.app {
    exports com.example.app;
}
```

`Main.java` vẫn khai báo `package com.example.app`. Có thể chạy module nguồn và cung cấp các dependency đã biên dịch trên module path:

```bash
java --module-path mods src/com/example/app/Main.java
```

Điểm cần nhớ là `module-info.java` phải nằm ngay tại source root. Khi có file này, các file nguồn được biên dịch từ source tree thuộc module được khai báo ở đó. Source-file mode không phải quy trình biên dịch nhiều module nguồn độc lập trong cùng một lần gọi; ví dụ, không thể dùng một source tree duy nhất để biên dịch đồng thời `com.example.app` và `com.example.lib` như một module-source-path build.

Nếu dự án có nhiều module nguồn, dùng `javac` với `--module-source-path`:

```text
project/
└── src/
    ├── com.example.lib/
    │   ├── module-info.java
    │   └── com/example/lib/Formatter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

`src/com.example.lib/module-info.java`:

```java
module com.example.lib {
    exports com.example.lib;
}
```

`src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.lib;
}
```

Ví dụ biên dịch hai module:

```bash
javac -d out --module-source-path src -m com.example.lib,com.example.app
```

Sau đó chạy module ứng dụng:

```bash
java --module-path out -m com.example.app/com.example.app.Main
```

`--module-path` trong source-file mode vẫn hữu ích để tìm các module dependency đã được đóng gói hoặc biên dịch. Giới hạn nằm ở việc tổ chức và biên dịch nhiều module nguồn độc lập, vốn cần quy trình module-aware của `javac` hoặc build tool.

## 4. Annotation processing bị tắt

Trong source-file mode, annotation processing bị vô hiệu hóa, tương đương `javac -proc:none`. Launcher không chạy các annotation processor để phân tích annotation và sinh thêm source hoặc class.

Điều này ảnh hưởng đến những dự án phụ thuộc vào công cụ sinh mã lúc biên dịch, ví dụ:

- Processor tạo mapper hoặc implementation từ interface và annotation.
- Processor sinh metamodel, registry hoặc mã truy cập dữ liệu.
- Processor kiểm tra quy tắc tùy chỉnh và phát lỗi biên dịch.
- Công cụ cần sinh source file để các class khác sử dụng trong cùng lần biên dịch.

Đưa file processor hoặc thư viện của nó vào class path không làm annotation processing tự chạy. Source-file mode không có cơ chế bật processor trong bước biên dịch nội bộ.

Khi cần annotation processing, gọi `javac` và khai báo rõ processor path, tên processor cùng thư mục chứa mã nguồn được sinh:

```bash
javac \
  --source-path src \
  --class-path "lib/*" \
  --processor-path "processors/*" \
  --processor com.example.processor.GenerateProcessor \
  -s generated-src \
  -d out \
  src/com/example/app/Main.java
```

Sau khi biên dịch và sinh mã thành công, chạy class đã biên dịch:

```bash
java --class-path "out:lib/*" com.example.app.Main
```

Ví dụ dùng dấu `:` để phân tách class path trên Linux và macOS; trên Windows, dùng dấu `;`. Trong dự án thật, cần cấu hình processor path và dependency đúng với công cụ đang sử dụng.

## 5. Không truyền được toàn bộ tùy chọn javac

Java launcher chỉ chuyển một tập tùy chọn liên quan đến môi trường biên dịch cho compiler nội bộ, chẳng hạn:

- `--class-path` / `-cp` để tìm class và thư viện.
- `--module-path` / `-p` để tìm module dependency.
- `--add-exports`, `--add-modules`, `--limit-modules`.
- `--patch-module`, `--upgrade-module-path`.
- `--enable-preview` khi chương trình dùng preview feature của đúng phiên bản JDK.

Launcher không cung cấp cách truyền các compiler option tùy ý như `-processor` hoặc `-Werror`. Các tùy chọn kiểm soát lint, cảnh báo, processor, thư mục output và quy trình sinh mã cần được đặt trực tiếp trong lệnh `javac` hoặc cấu hình build tool.

Ví dụ, nếu CI yêu cầu mọi cảnh báo được xử lý và phải thất bại khi có cảnh báo, hãy biên dịch tường minh:

```bash
javac -Xlint:all -Werror -d out --source-path src \
  src/com/example/app/Main.java
```

Không thể thêm `-Werror` vào lệnh `java Main.java` để yêu cầu compiler nội bộ thực hiện cùng quy tắc.

## 6. Những giới hạn khác của quy trình biên dịch theo nhu cầu

Source-file mode tối ưu cho thao tác chạy nhanh, nên một số khả năng của quy trình build đầy đủ không được cung cấp trực tiếp:

| Nhu cầu | Source-file mode | Quy trình phù hợp |
| --- | --- | --- |
| Chạy một chương trình từ nhiều file nguồn | Có, tìm file trong source tree theo nhu cầu | Không cần build tool cho ví dụ nhỏ |
| Dùng thư viện đã biên dịch | Có, qua `--class-path` hoặc `--module-path` | Dùng dependency đã có sẵn |
| Chạy một source tree thuộc một named module | Có, nếu `module-info.java` ở source root | Dùng module path cho dependency đã biên dịch |
| Biên dịch nhiều module nguồn độc lập | Không trong một source-file invocation | `javac --module-source-path` hoặc build tool |
| Chạy annotation processor | Không; processing bị tắt | `javac --processor-path` / build tool |
| Đặt thư mục class output và generated source | Không có compiler option tổng quát để cấu hình | `javac -d`, `javac -s` hoặc build tool |
| Áp dụng `-Werror`, `-processor` và tùy chọn javac khác | Không | Gọi `javac` trực tiếp |
| Quản lý test, resources, đóng gói JAR và nhiều giai đoạn build | Không phải mục tiêu của source-file mode | Maven, Gradle hoặc build system tương ứng |

Các class biên dịch trong source-file mode được giữ trong bộ nhớ cho lần chạy đó. Đây không phải quy trình tạo output directory hoặc artifact phát hành. Nếu cần kiểm soát chính xác những file nào được biên dịch, tạo generated source, lưu class file, đóng gói JAR hoặc tái lập build trong CI, hãy dùng quy trình build rõ ràng.

## 7. Cách chọn công cụ theo tình huống

| Tình huống | Nên dùng |
| --- | --- |
| Thử một ví dụ Java có một vài file nguồn | `java Main.java` |
| Chia ví dụ thành nhiều package nhưng vẫn ở một source tree | Source-file mode |
| Dùng một module nguồn nhỏ cùng dependency module đã biên dịch | Source-file mode với `module-info.java` và `--module-path` |
| Dự án có nhiều module nguồn | `javac --module-source-path` hoặc Maven/Gradle |
| Dự án cần Lombok, MapStruct hoặc annotation processor khác | `javac` với processor hoặc build tool đã cấu hình |
| CI cần lint, warnings-as-errors, generated sources, tests và đóng gói | Maven, Gradle hoặc quy trình `javac` đầy đủ |

Source-file mode vẫn hữu ích trong dự án lớn để tạo ví dụ tái hiện lỗi, viết script bảo trì hoặc thử một API nhỏ. Có thể giữ dependency đã biên dịch trên class path/module path và chạy file nguồn độc lập. Khi chương trình cần quy trình biên dịch xác định, hãy chuyển sang `javac` hoặc build tool thay vì cố biến launcher thành một hệ thống build.

## 8. Ví dụ thực tế: từ chạy nhanh đến build có kiểm soát

Ở giai đoạn thử nghiệm, có thể tổ chức `src` thành nhiều package và chạy trực tiếp:

```bash
java src/com/example/app/Main.java
```

Khi chương trình bắt đầu cần annotation processor, nhiều module hoặc kiểm tra cảnh báo nghiêm ngặt, chuyển sang biên dịch tường minh:

```bash
javac -Xlint:all -Werror \
  --module-source-path src \
  --processor-path processors \
  -s generated-src \
  -d out \
  -m com.example.lib,com.example.app
```

Sau đó chạy module đã biên dịch:

```bash
java --module-path out -m com.example.app/com.example.app.Main
```

Với dự án thực tế, Maven hoặc Gradle có thể quản lý dependency, thứ tự các giai đoạn biên dịch, annotation processor, test, resource, packaging và cấu hình CI. Những công cụ này giúp toàn bộ nhóm dùng chung một quy trình build có thể lặp lại.

## 9. Phiên bản và trạng thái tính năng

JEP 458 được hoàn thiện trong Java 22. Source-file mode nhiều file là tính năng chính thức, vì vậy không cần `--enable-preview` để sử dụng nó trên JDK 22 trở lên.

Các tùy chọn preview mà `java` launcher nhận chỉ phục vụ chương trình đang dùng một preview feature khác của đúng phiên bản JDK. Chúng không biến annotation processing thành tính năng được hỗ trợ trong source-file mode và cũng không mở rộng tập compiler option mà launcher chuyển tiếp.

Tài liệu hiện hành của JDK 27 vẫn mô tả các giới hạn về annotation processing, tập tùy chọn compiler và cách tổ chức source tree/module như trên. Khi nâng JDK, hãy kiểm tra lại trang `java` command của đúng phiên bản để xác nhận hành vi launcher.

## 10. Tài liệu tham khảo

- [JEP 458: Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458) — mục tiêu và thiết kế source-file mode nhiều file, được hoàn thiện trong Java 22.
- [JDK 27 — The `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — source-file mode, source root, module-info, annotation processing và các tùy chọn được chuyển cho compiler.
- [JDK 27 — The `javac` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — tùy chọn biên dịch, module source path và annotation processing.
- [JDK 27 — Introduction to Modules](https://dev.java/learn/modules/intro/) — cách biên dịch và khởi chạy ứng dụng modular.
