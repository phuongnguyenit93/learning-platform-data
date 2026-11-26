# Đối số chương trình, tùy chọn JVM và lựa chọn phiên bản ngôn ngữ bằng `--source`

## 1. Cấu trúc lệnh khi chạy chương trình từ mã nguồn

Từ Java 22, `java` launcher có thể biên dịch và chạy một chương trình gồm nhiều file `.java` mà không cần gọi `javac` trước. Tính năng này được chuẩn hóa trong JEP 458: Launch Multi-File Source-Code Programs.

Cú pháp tổng quát trong source-file mode:

```text
java [JVM options] [compile options] [--source N] source-file [program arguments...]
```

Các thành phần có vai trò khác nhau:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| JVM options | Cấu hình máy ảo khi chạy chương trình. | `-Xmx512m`, `-Dapp.env=dev`, `-ea` |
| Compile options | Cung cấp class path, module path hoặc cấu hình module cần thiết khi launcher biên dịch source. | `--class-path lib/*`, `--module-path mods` |
| `--source N` | Chọn phiên bản cú pháp Java và API nền tảng mà mã nguồn được phép sử dụng. | `--source 22` |
| `source-file` | File nguồn chứa lớp khởi chạy. | `app/Main.java` |
| Program arguments | Các đối số được truyền vào `main(String[] args)`. | `--limit 10`, `"Nguyen An"` |

Ranh giới quan trọng là **source file**. Các tùy chọn launcher phải nằm trước file nguồn. Các mục nằm sau file nguồn được truyền cho chương trình như đối số `args`.

## 2. Ví dụ chương trình nhiều file

Giả sử một chương trình có cấu trúc thư mục như sau:

```text
greeting-app/
├── app/
│   └── Main.java
└── service/
    └── Greeter.java
```

File `app/Main.java`:

```java
package app;

import service.Greeter;

public class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";
        System.out.println(Greeter.greet(name));
    }
}
```

File `service/Greeter.java`:

```java
package service;

public class Greeter {
    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Mở terminal tại thư mục `greeting-app` rồi chạy:

```bash
java app/Main.java
```

Launcher xác định package `app` từ file khởi chạy, suy ra source root là thư mục `greeting-app`, tìm file nguồn của `service.Greeter`, biên dịch các source cần thiết trong bộ nhớ và chạy `app.Main`.

Kết quả:

```text
Xin chào, Java!
```

Không cần chạy `javac app/Main.java service/Greeter.java` trước và cũng không cần tạo thư mục `out` để chứa `.class`. Launcher chỉ biên dịch các source cần thiết để giải quyết các tham chiếu của chương trình; nó không mặc định biên dịch mọi file `.java` không liên quan trong thư mục.

## 3. Truyền đối số cho `main(String[] args)`

Đối số chương trình được đặt sau đường dẫn file nguồn. Mỗi đối số được chuyển thành một phần tử trong mảng `String[] args`:

```bash
java app/Main.java "Nguyen An" 3 --verbose
```

Trong `main`:

```java
public static void main(String[] args) {
    System.out.println(args.length); // 3
    System.out.println(args[0]);     // Nguyen An
    System.out.println(args[1]);     // 3
    System.out.println(args[2]);     // --verbose
}
```

Shell xử lý dấu nháy trước khi gọi launcher. Vì vậy, `"Nguyen An"` được truyền thành một đối số duy nhất có dấu cách. Nếu viết `Nguyen An` không có dấu nháy trong shell thông thường, chương trình sẽ nhận hai đối số riêng.

Đối số luôn có kiểu `String`; nếu cần số nguyên, số thực hoặc giá trị boolean, chương trình phải tự phân tích và kiểm tra:

```java
public static void main(String[] args) {
    if (args.length < 2) {
        System.err.println("Cách dùng: Main.java <name> <limit>");
        return;
    }

    String name = args[0];
    int limit;
    try {
        limit = Integer.parseInt(args[1]);
    } catch (NumberFormatException exception) {
        System.err.println("limit phải là số nguyên");
        return;
    }

    System.out.println(name + ": " + limit);
}
```

## 4. Tùy chọn JVM phải đặt trước source file

Các tùy chọn cấu hình JVM được đặt trước file nguồn, giống khi chạy một lớp đã biên dịch:

```bash
java -Xmx512m -Dapp.env=dev -ea app/Main.java "Nguyen An"
```

Ý nghĩa:

- `-Xmx512m`: đặt giới hạn heap tối đa là 512 MB.
- `-Dapp.env=dev`: tạo system property `app.env` có giá trị `dev`.
- `-ea`: bật Java assertions.

Chương trình có thể đọc system property bằng `System.getProperty("app.env")` và sử dụng `assert` khi kiểm tra điều kiện nội bộ.

```java
public static void main(String[] args) {
    System.out.println(System.getProperty("app.env")); // dev
    assert args.length > 0 : "Cần truyền tên người dùng";
}
```

Nếu đặt tùy chọn JVM sau file nguồn, launcher coi chúng là đối số chương trình:

```bash
java app/Main.java -Xmx512m -Dapp.env=dev
```

Trong lệnh này, `args[0]` là `-Xmx512m` và `args[1]` là `-Dapp.env=dev`. Heap và system property không được cấu hình bởi hai chuỗi đó.

## 5. Class path và module path khi có thư viện ngoài

Launcher tự tìm source phụ thuộc trong source tree theo package, nhưng không tự tải hoặc quản lý thư viện bên ngoài. Nếu chương trình sử dụng một thư viện đã đóng gói thành JAR, hãy cung cấp class path hoặc module path trước source file.

Ví dụ với thư viện trên class path:

```bash
java -Xmx512m --class-path "lib/*" app/Main.java "Nguyen An"
```

`--class-path` (viết tắt `-cp`) chỉ định nơi tìm class và JAR của thư viện. Dấu `*` trong `lib/*` cho phép launcher nạp các JAR trong thư mục `lib` theo quy tắc class path của Java.

Với thư viện dạng module:

```bash
java --module-path mods --add-modules com.example.reporting app/Main.java
```

`--module-path` (viết tắt `-p`) chỉ định module path; `--add-modules` đưa module cần thiết vào cấu hình module của ứng dụng. Các tùy chọn liên quan đến biên dịch như `--class-path`, `--module-path`, `--add-modules`, `--add-exports`, `--limit-modules` và `--patch-module` phải xuất hiện trước file nguồn để launcher sử dụng chúng khi biên dịch.

Nếu source root có `module-info.java`, launcher dùng khai báo module đó để biên dịch các source trong source tree thành một named module. Nếu không có, các source được biên dịch trong unnamed module. Với chương trình module, cần tổ chức `module-info.java` ở source root và khai báo `requires`/`exports` phù hợp.

## 6. Chọn phiên bản ngôn ngữ và API bằng `--source`

Nếu không chỉ định `--source`, launcher dùng phiên bản ngôn ngữ mặc định của JDK đang chạy. Có thể chọn một release cụ thể bằng:

```bash
java --source 22 app/Main.java "Nguyen An"
```

`--source 22` có hai tác dụng trong source-file mode:

1. Biên dịch theo quy tắc cú pháp của Java 22.
2. Giới hạn API nền tảng có thể sử dụng ở những API được định nghĩa trong Java 22.

Về mặt biên dịch, launcher xem `--source N` như một `--release N` ngầm định. Điều này quan trọng hơn việc chỉ kiểm tra cú pháp: mã nguồn không thể vô tình gọi API mới được thêm vào JDK 23, 24 hoặc 27 nếu chọn source/API level 22.

**`--source` không thay đổi JVM đang chạy.** Nếu lệnh `java` trỏ tới JDK 27, thì chương trình vẫn chạy trên JVM 27; `--source 22` chỉ giới hạn phiên bản ngôn ngữ và API khi biên dịch trong bộ nhớ. Nó cũng không tự bật preview feature của Java 22.

JEP 458 là tính năng chính thức từ Java 22, không phải preview. Nếu mã nguồn cần một preview feature khác, `--source 22` không bật tính năng đó. Preview feature chỉ dùng được với JDK của đúng release đang cung cấp preview; trên JDK 27, ví dụ cấu hình preview phải dùng `--enable-preview` cùng source release 27:

```bash
java --enable-preview --source 27 app/Main.java
```

Không thể dùng JDK 27 để bật lại preview feature từng xuất hiện trong JDK 22.

Các giá trị `N` được hỗ trợ thay đổi theo JDK. Tài liệu JDK 27 quy định launcher hỗ trợ release hiện tại và một số release trước đó; nếu chọn một giá trị không còn được hỗ trợ, lệnh sẽ báo lỗi. Kiểm tra danh sách release được hỗ trợ bằng `javac --help` của chính JDK đang dùng trước khi cố định `--source` trong script.

Nếu tên file nguồn không có phần mở rộng `.java`, cần chỉ định `--source` để launcher nhận biết source-file mode:

```bash
java --source 27 tools/report "monthly.csv"
```

Trong ví dụ này, `tools/report` là file chứa mã nguồn, không phải tên lớp. Giá trị `27` chỉ là ví dụ cho JDK 27; hãy thay bằng source release mà JDK hiện tại hỗ trợ và phù hợp với mã nguồn.

## 7. Phân biệt tùy chọn launcher với đối số chương trình

Thứ tự đối số quyết định cách launcher diễn giải dòng lệnh:

```bash
java -Xmx256m --class-path "lib/*" --source 22 app/Main.java --limit 10 "monthly report.csv"
```

| Vị trí | Giá trị | Được xử lý bởi |
|---|---|---|
| Trước source file | `-Xmx256m` | JVM: cấu hình heap |
| Trước source file | `--class-path "lib/*"` | Launcher/compiler: tìm thư viện |
| Trước source file | `--source 22` | Launcher/compiler: chọn source/API release |
| Mốc chuyển | `app/Main.java` | Launcher: file nguồn khởi chạy |
| Sau source file | `--limit` | Chương trình: `args[0]` |
| Sau source file | `10` | Chương trình: `args[1]` |
| Sau source file | `monthly report.csv` | Chương trình: `args[2]` |

Một lỗi thường gặp là đặt `--source` hoặc `--class-path` sau source file rồi mong launcher áp dụng chúng. Sau khi launcher gặp source file, các chuỗi tiếp theo là dữ liệu của chương trình. Hãy kiểm tra thứ tự trước khi sửa mã Java nếu chương trình nhận sai đối số hoặc không tìm thấy thư viện.

## 8. Những giới hạn cần biết của source-file mode

Multi-file source launcher rất hữu ích cho học tập, thử nghiệm, công cụ nội bộ nhỏ và chạy nhanh chương trình có cấu trúc package. Nó không thay thế hoàn toàn quy trình build của một ứng dụng lớn.

| Giới hạn | Ý nghĩa thực tế |
|---|---|
| Source tree phải theo package | File của `package service` phải nằm trong thư mục `service` bên dưới source root được suy ra từ package của file khởi chạy. |
| Chỉ biên dịch source cần thiết | File `.java` không được tham chiếu không tự động trở thành một phần chương trình. |
| Thư viện ngoài phải được cung cấp | Dùng class path hoặc module path; launcher không tự tìm và tải dependency từ Maven Central. |
| Annotation processing bị tắt | Source-file mode hoạt động như khi dùng `-proc:none`; không trông chờ annotation processor chạy. |
| Không chuyển được mọi tùy chọn `javac` | Các tùy chọn như `-processor` hoặc `-Werror` không có cơ chế truyền trực tiếp qua `java` source-file mode. |
| Class loader riêng cho source | Các lớp đã có trên application class path không thể tham chiếu ngược đến lớp chỉ được biên dịch từ source file trong lần khởi chạy này. |
| Lớp trùng tên | Nếu application class path đã có lớp cùng tên với lớp khởi chạy trong source file, launcher báo lỗi. |
| Không tạo artifact build thông thường | Các lớp nguồn được biên dịch trong bộ nhớ; nếu cần JAR, phân phối, kiểm thử và build lặp lại, hãy dùng `javac` hoặc build tool. |

File nguồn được chỉ định phải chứa ít nhất một top-level class; top-level class đầu tiên được launcher chọn để chạy và phải có entry `main` hợp lệ.

Nếu source root chứa `module-info.java`, các file `.java` trong source tree được biên dịch trong named module tương ứng. Nếu không có, chúng thuộc unnamed module. Không dùng source-file mode để thay thế cấu hình module phức tạp hoặc hệ thống build nhiều module khi dự án đã cần quản lý dependency, annotation processing và đóng gói.

JEP 458 không mở rộng shebang launcher cho chương trình nhiều file. Cách chạy source nhiều file bằng `java` không đồng nghĩa có thể chạy cả source tree như một shell script có shebang.

## 9. Quy trình sử dụng thực tế

Khi chạy một chương trình source nhiều file, có thể làm theo thứ tự sau:

1. Chọn file chứa lớp có `main` làm source file khởi chạy.
2. Đặt file theo đúng package hierarchy và đặt các source phụ thuộc trong source root tương ứng.
3. Xác định phiên bản cú pháp/API cần dùng; chỉ định `--source N` nếu cần cố định release.
4. Đặt JVM options như `-Xmx`, `-D...`, `-ea` trước source file.
5. Đặt `--class-path` hoặc `--module-path` trước source file nếu có thư viện ngoài.
6. Đặt source file, sau đó mới đặt các đối số nghiệp vụ dành cho `main`.
7. Nếu cần annotation processing, build reproducible, kiểm thử hoặc đóng gói artifact, chuyển sang quy trình `javac`/build tool phù hợp.

Ví dụ lệnh đầy đủ:

```bash
java -Xmx512m -Dapp.env=dev -ea --class-path "lib/*" --source 22 app/Main.java "Nguyen An" 10
```

Lệnh trên dùng JVM hiện tại, giới hạn mã nguồn theo Java 22, nạp thư viện từ `lib`, chạy file `app/Main.java`, rồi truyền hai đối số `Nguyen An` và `10` cho chương trình.

## 10. Tài liệu tham khảo

- [JEP 458: Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458) — mô tả tính năng được đưa vào JDK 22.
- [Java SE 27: The `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — cú pháp launcher, source-file mode, cách xử lý tùy chọn và đối số, source root và giới hạn biên dịch.
- [Java SE 27: The `javac` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — các release được hỗ trợ bởi `--source` và `--release`.
- [Dev.java: Launching Simple Source-Code Programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/) — hướng dẫn thực hành chạy chương trình một file và nhiều file.
