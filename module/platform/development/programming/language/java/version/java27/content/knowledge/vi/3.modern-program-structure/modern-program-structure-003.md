# Chạy trực tiếp tệp mã nguồn và xác định phạm vi sử dụng

Java 27 cho phép khởi chạy một chương trình từ tệp mã nguồn `.java` bằng chính lệnh `java`, không cần gọi `javac` trước. Cách chạy này được gọi là **source-file mode** (chế độ chạy tệp mã nguồn). Launcher biên dịch mã nguồn rồi thực thi chương trình trên JVM; vì vậy, “chạy trực tiếp” vẫn có bước biên dịch, chỉ là bước đó được launcher tự thực hiện.

Tính năng này hữu ích khi học Java, thử một ý tưởng nhỏ, chạy ví dụ hoặc viết tiện ích dòng lệnh ngắn. Java 27 còn hỗ trợ chạy chương trình có nhiều tệp mã nguồn liên quan và cú pháp tệp nguồn rút gọn đã trở thành tính năng chính thức từ Java 25. Để dùng hiệu quả, cần hiểu cách chọn chế độ chạy, cách truyền tham số và giới hạn của source-file mode.

## 1. Source-file mode hoạt động như thế nào?

Source-file mode được giới thiệu trong Java 11 qua JEP 330. Khi lệnh `java` nhận một đường dẫn đến tệp `.java`, launcher nhận diện đây là chương trình mã nguồn, gọi trình biên dịch để biên dịch mã rồi khởi chạy lớp có phương thức `main` phù hợp. Theo tài liệu JDK 27, hiệu ứng tương đương với việc biên dịch vào bộ nhớ rồi chạy các lớp đã biên dịch đó.

```mermaid
flowchart LR
    A[Source file .java] --> B[Java launcher]
    B --> C[Compile source]
    C --> D[Load compiled classes]
    D --> E[Run on JVM]
    E --> F[Program output]
```

Ví dụ, tạo tệp `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java 27!");
    }
}
```

Chạy trực tiếp từ thư mục chứa tệp:

```bash
java Hello.java
```

Launcher tự biên dịch và chạy chương trình. Bạn không cần thực hiện riêng hai lệnh `javac` và `java`, cũng không cần tự chỉ định thư mục đầu ra cho class file trung gian.

## 2. Cách gọi launcher và truyền tham số

Cú pháp tổng quát:

```text
java [các tùy chọn của launcher] <source-file> [tham số của chương trình...]
```

Nếu đối số đầu tiên không phải tùy chọn là đường dẫn tới tệp đang tồn tại có phần mở rộng `.java`, launcher chọn source-file mode. Có thể chỉ rõ phiên bản ngôn ngữ bằng `--source`:

```bash
java --source 27 Hello.java
```

`--source 27` yêu cầu biên dịch theo mức ngôn ngữ Java 27 và giới hạn API công khai được dùng ở mức API của JDK 27. Tùy chọn này không cài đặt JDK 27 và cũng không biến một runtime cũ thành runtime 27; lệnh `java` đang chạy vẫn quyết định JVM thực thi chương trình. Giá trị phiên bản được chấp nhận thay đổi theo từng bản JDK; JDK 27 hỗ trợ 27 cùng một số phiên bản trước đó còn được duy trì.

Nếu tên tệp không có phần mở rộng `.java`, phải chỉ rõ `--source` để launcher biết cần xử lý tệp đó như mã nguồn Java:

```bash
java --source 27 greeting-script
```

Ví dụ truyền đối số cho chương trình. Sửa `Hello.java` thành:

```java
public class Hello {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
```

Chạy:

```bash
java Hello.java Phuong
```

Chuỗi `Phuong` nằm sau tên tệp nguồn nên được chuyển vào `main` dưới dạng phần tử của `args`. Các tùy chọn dành cho JVM hoặc môi trường biên dịch phải đặt trước tên tệp nguồn; các đối số đặt sau tệp được chuyển cho chương trình.

## 3. Dùng tệp nguồn rút gọn trong Java 27

Từ Java 25, **Compact Source Files and Instance Main Methods** (JEP 512) là tính năng chính thức, không còn ở trạng thái preview. Java 27 tiếp tục hỗ trợ tính năng này. Nhờ đó, chương trình nhỏ có thể bỏ phần khai báo lớp tường minh và dùng phương thức `main` dạng instance:

```java
void main() {
    IO.println("Hello, Java 27!");
}
```

Lưu đoạn mã trên trong `Hello.java` và chạy:

```bash
java Hello.java
```

Trình biên dịch hiểu các thành viên ở cấp cao nhất trong tệp là thành viên của một lớp được khai báo ngầm. Lớp này nằm trong unnamed package và có constructor mặc định. Launcher tạo đối tượng khi cần gọi instance `main`. Lớp ngầm định chỉ đóng vai trò điểm bắt đầu của chương trình; không thể tham chiếu tên lớp đó từ mã nguồn khác.

Các điểm cần nhớ:

- Có thể khai báo phương thức và trường trực tiếp trong tệp, không cần bọc chúng trong `class`.
- `main` có thể là instance method, không bắt buộc `static` hoặc `public`.
- Có thể dùng `void main()` khi không cần nhận tham số; cũng có thể dùng `void main(String[] args)` để nhận tham số dòng lệnh.
- `IO.println(...)` và `IO.readln(...)` là API I/O dòng lệnh đơn giản của Java 25 trở lên; lớp `IO` thuộc `java.lang` và được tự động import.
- Cú pháp rút gọn phù hợp với chương trình nhỏ, ví dụ học tập và tiện ích độc lập. Khi chương trình cần nhiều kiểu dữ liệu, namespace, đóng gói hoặc tái sử dụng giữa các thành phần, nên chuyển sang cấu trúc lớp, package và module tường minh.

Kiểu `main` truyền thống vẫn hoàn toàn hợp lệ:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java 27!");
    }
}
```

Java 25 mở rộng quy tắc tìm phương thức khởi chạy để hỗ trợ các dạng `main` có hoặc không có tham số, là `static` hoặc instance, với mức truy cập phù hợp. Với lớp thông thường, nên giữ dạng `public static void main(String[] args)` khi cần khả năng tương thích rõ ràng với các công cụ và môi trường Java cũ hơn. Tệp nguồn rút gọn và các dạng `main` mới cần JDK hỗ trợ Java 25 trở lên.

## 4. Chạy chương trình gồm nhiều tệp nguồn

Từ Java 22, JEP 458 mở rộng launcher để chạy chương trình được cung cấp qua nhiều tệp mã nguồn. Khi chạy một tệp nguồn, launcher xác định **source root** dựa trên package của lớp được khởi chạy. Thư mục gốc đó được dùng làm source path; những tệp `.java` khác trong cây thư mục sẽ được tìm và biên dịch khi cần để giải quyết các kiểu mà chương trình tham chiếu.

Ví dụ cấu trúc thư mục:

```text
project/
└── src/
    └── com/
        └── example/
            ├── App.java
            └── Greeting.java
```

`App.java`:

```java
package com.example;

public class App {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

`Greeting.java`:

```java
package com.example;

public class Greeting {
    static String message() {
        return "Hello from another source file";
    }
}
```

Từ thư mục `project`, chạy:

```bash
java src/com/example/App.java
```

Vì `App.java` khai báo package `com.example` và nằm trong `src/com/example`, launcher suy ra `src` là source root. Khi biên dịch `App`, launcher có thể tìm và biên dịch `Greeting.java` vì lớp `App` sử dụng `Greeting`. Không cần liệt kê từng tệp nguồn trên dòng lệnh.

Với thư viện đã biên dịch bên ngoài cây mã nguồn, truyền class path trước tệp nguồn:

```bash
java --class-path "lib/*" src/com/example/App.java
```

Nếu chương trình dùng module, `module-info.java` đặt tại source root sẽ xác định module chứa các lớp được biên dịch từ cây nguồn đó. Có thể truyền các module phụ thuộc bằng `--module-path`. Nếu không có `module-info.java`, các lớp được biên dịch trong unnamed module.

## 5. Các tùy chọn thường dùng

| Tùy chọn | Mục đích khi chạy source-file mode |
|---|---|
| `--source 27` | Chọn mức ngôn ngữ và API Java 27 cho quá trình biên dịch |
| `--class-path` hoặc `-cp` | Cung cấp thư mục hoặc JAR chứa các lớp đã biên dịch mà mã nguồn cần dùng |
| `--module-path` hoặc `-p` | Cung cấp các module phụ thuộc |
| `--add-modules` | Bổ sung module cần được phân giải khi khởi chạy |
| `--enable-preview` | Cho phép dùng tính năng preview của đúng bản JDK đang chạy, nếu chương trình thực sự cần |

Ví dụ kết hợp class path và source-file mode:

```bash
java --class-path "lib/*" --source 27 src/com/example/App.java input.txt
```

Trong ví dụ này, `lib/*` phục vụ quá trình biên dịch và nạp thư viện; `input.txt` là đối số của chương trình. Trên Windows, dấu phân cách các phần tử class path là dấu chấm phẩy (`;`); trên Linux và macOS là dấu hai chấm (`:`). Cách viết wildcard `lib/*` giúp launcher đưa các JAR trong thư mục `lib` vào class path.

## 6. Phân biệt các cách khởi chạy Java

Các dạng lệnh sau đều dùng launcher `java`, nhưng chọn đầu vào và quy trình khác nhau:

| Cách chạy | Đầu vào | Khi nào dùng |
|---|---|---|
| `java Hello.java` | Tệp mã nguồn | Chạy nhanh ví dụ hoặc chương trình nhỏ; launcher tự biên dịch |
| `javac --release 27 -d out Hello.java` rồi `java -cp out Hello` | Class file được biên dịch tường minh | Khi cần kiểm soát đầu ra biên dịch, cảnh báo, annotation processing hoặc quy trình build |
| `java -jar app.jar` | JAR có khai báo `Main-Class` | Chạy ứng dụng đã đóng gói để phân phối |
| `java -m module.name/com.example.App` | Module đã được biên dịch | Chạy ứng dụng tổ chức theo Java Platform Module System |

Source-file mode là một cách khởi chạy tiện lợi. Nó không thay thế quy trình build của dự án. Đối với ứng dụng đã đóng gói, launcher thường chạy class file, JAR hoặc module theo cách triển khai của ứng dụng.

## 7. Giới hạn và phạm vi sử dụng phù hợp

Source-file mode có thể tự biên dịch các tệp nguồn cần thiết trong source tree, nhưng không thực hiện toàn bộ công việc của Maven, Gradle hoặc một hệ thống build tương đương. Các giới hạn quan trọng gồm:

- **Annotation processing bị tắt:** source-file mode hoạt động như thể `-proc:none` được bật. Các quy trình cần annotation processor như sinh mã ở thời điểm biên dịch phải dùng quy trình biên dịch/build tường minh.
- **Không nhận mọi tùy chọn của `javac`:** launcher chuyển tiếp một số tùy chọn liên quan đến môi trường biên dịch như class path, module path và preview; không có cơ chế tổng quát để truyền tùy chọn compiler như `-processor` hoặc `-Werror`.
- **Không tự quản lý phụ thuộc từ kho artifact:** thư viện bên ngoài phải có sẵn và được khai báo qua class path hoặc module path. Launcher không thay thế Maven/Gradle để tải, khóa phiên bản và kiểm tra cây phụ thuộc.
- **Phạm vi mã nguồn theo source root:** launcher tìm các tệp nguồn cần thiết trong cây nguồn được suy ra từ package. Một dự án nhiều module, nhiều source set, mã nguồn sinh tự động hoặc quy trình xử lý tài nguyên thường cần build tool.
- **Cần môi trường có compiler:** launcher phải có khả năng biên dịch mã nguồn. Một runtime image tối giản được tạo mà không bao gồm thành phần compiler có thể không chạy được source-file mode.
- **Có thể gặp xung đột lớp:** nếu class path đã chứa lớp trùng tên với lớp được chọn để chạy từ source file, việc khởi chạy có thể thất bại.

| Nhu cầu | Cách phù hợp |
|---|---|
| Học cú pháp, minh họa một API hoặc thử đoạn mã | Source-file mode |
| Viết script Java hoặc tiện ích dòng lệnh nhỏ | Source-file mode, có thể kết hợp `--source` và tham số dòng lệnh |
| Thử một chương trình nhỏ có vài lớp nguồn cùng package | Source-file mode với source tree được tổ chức đúng package |
| Sinh mã bằng annotation processor | Biên dịch tường minh hoặc Maven/Gradle |
| Ứng dụng có nhiều thư viện, kiểm thử, tài nguyên và nhiều bước build | Maven hoặc Gradle |
| Phân phối ứng dụng ổn định cho môi trường triển khai | JAR, module hoặc runtime image được build và kiểm thử rõ ràng |

## 8. Quy trình thực hành và kiểm tra

Khi chạy một tệp nguồn, có thể kiểm tra theo thứ tự sau:

1. Xác nhận JDK đang được dùng bằng `java --version`.
2. Kiểm tra tệp nguồn có phần mở rộng `.java`; nếu không, thêm `--source 27`.
3. Kiểm tra package và vị trí tệp để source root được suy ra đúng.
4. Xác nhận tệp có phương thức `main` có thể khởi chạy; với tệp nguồn rút gọn, dùng cú pháp compact source file của Java 25 trở lên.
5. Thêm `--class-path` hoặc `--module-path` trước tên tệp nếu có thư viện ngoài.
6. Đặt tham số của chương trình sau tên tệp nguồn.
7. Nếu gặp lỗi, phân biệt lỗi biên dịch, lỗi không tìm thấy phụ thuộc và lỗi khi thực thi trên JVM.

Ví dụ kiểm tra nhanh:

```bash
java --version
java --source 27 Hello.java Phuong
```

Nếu chương trình cần được build lặp lại trong CI, chạy kiểm thử tự động, đóng gói, kiểm soát annotation processor hoặc triển khai nhiều môi trường, hãy chuyển sang Maven/Gradle và xác định phiên bản JDK mục tiêu. Với những nhu cầu đó, việc biên dịch tường minh giúp kiểm soát rõ hơn đầu ra và các bước tạo artifact.

## 9. Tài liệu tham khảo chính thức

- [The `java` Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — cú pháp launcher, source-file mode, tùy chọn biên dịch và cách xử lý source tree.
- [JEP 330: Launch Single-File Source-Code Programs](https://openjdk.org/jeps/330) — giới thiệu source-file mode từ JDK 11.
- [JEP 458: Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458) — mở rộng launcher để tìm và biên dịch các tệp nguồn phụ thuộc từ JDK 22.
- [Compact Source Files and Instance Main Methods — Java SE 25](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html) — cú pháp tệp nguồn rút gọn, instance `main` và API `java.lang.IO`, đã là tính năng chính thức từ Java 25.
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — trạng thái các thay đổi ngôn ngữ theo từng phiên bản Java.
