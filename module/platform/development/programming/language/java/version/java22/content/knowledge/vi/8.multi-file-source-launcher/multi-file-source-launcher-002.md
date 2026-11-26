# Chọn tệp chứa điểm vào và chạy chương trình bằng lệnh `java` với tệp nguồn

Từ Java 22, lệnh `java` có thể khởi chạy chương trình được tổ chức trong nhiều tệp nguồn `.java` mà không cần chạy `javac` trước. Đây là nội dung của JEP 458, *Launch Multi-File Source-Code Programs*. Bạn chỉ định tệp nguồn chứa điểm vào; launcher tự tìm và biên dịch các tệp nguồn khác mà chương trình tham chiếu trong cùng source tree.

Tính năng này là một phần chính thức của JDK từ Java 22, không phải preview hay incubator. Cách dùng `java Main.java` và các quy tắc source-file mode vẫn áp dụng trên JDK hiện đại, bao gồm JDK 27. Tính đến ngày 25/11/2026, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất. Bài này dùng cú pháp truyền thống `public static void main(String[] args)` để ví dụ có thể chạy trên Java 22 trở lên.

## 1. Chọn tệp nguồn chứa điểm vào

Khi chạy ở source-file mode, đối số đầu tiên không phải option của launcher là đường dẫn đến tệp nguồn được dùng để khởi chạy chương trình. Với source file dạng truyền thống, top-level class đầu tiên trong tệp là class được chạy và phải có entry `main` method.

Ví dụ với chương trình chỉ có một tệp:

```java
// Main.java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
```

Chạy trực tiếp từ thư mục chứa tệp:

```bash
java Main.java
```

Launcher biên dịch mã nguồn vào bộ nhớ rồi chạy class điểm vào. Không cần tạo thư mục chứa `.class` bằng `javac` trước.

Nếu tệp có nhiều top-level class, class đầu tiên trong tệp là class được launcher chọn. Vì vậy, hãy đặt class chứa `main` lên đầu và chỉ định đúng tệp nguồn khi chạy. Tên tệp không nhất thiết phải trùng với tên top-level class theo quy tắc thông thường dành cho public class trong compilation thông thường, nhưng đặt tên tệp rõ ràng như `Main.java` giúp người đọc nhận ra điểm vào.

**Lưu ý với JDK 25 trở lên:** JEP 512 bổ sung *compact source files* và instance `main` methods. Một source file có thể khai báo method/field ở cấp cao nhất mà không cần viết `class` tường minh; compiler tạo một implicitly declared class làm điểm vào. `main` cũng có thể là instance method, chẳng hạn `void main()` hoặc `void main(String[] args)`. Cú pháp này là tính năng chính thức từ Java 25. Các ví dụ chính trong bài vẫn dùng `public static void main(String[] args)` để chạy được từ Java 22.

Ví dụ compact source file trên JDK 25 trở lên:

```java
// Main.java
void main(String[] args) {
    String name = args.length == 0 ? "Bạn" : args[0];
    IO.println("Xin chào, " + Greeter.greet(name) + "!");
}
```

```java
// Greeter.java
class Greeter {
    static String greet(String name) {
        return name;
    }
}
```

Chạy bằng `java Main.java Lan` trên JDK 25 trở lên. Trên Java 22–24, hãy dùng dạng class truyền thống vì compact source files và instance `main` chưa phải API/ngôn ngữ chính thức ở các phiên bản đó.

## 2. Tổ chức chương trình trong nhiều tệp

JEP 458 mở rộng source-file mode từ một tệp sang một source tree. Khi class điểm vào tham chiếu đến class chưa được tìm thấy trong các class đã biên dịch hoặc thư viện, launcher/compiler có thể tìm tệp `.java` tương ứng trong source tree và biên dịch nó cùng chương trình.

Ví dụ, chương trình được tổ chức như sau:

```text
project/
└── src/
    └── demo/
        ├── Main.java
        ├── model/
        │   └── User.java
        └── service/
            └── GreetingService.java
```

`Main.java` chứa điểm vào và sử dụng hai class nằm trong package con:

```java
// src/demo/Main.java
package demo;

import demo.model.User;
import demo.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Bạn";

        User user = new User(name);
        GreetingService service = new GreetingService();

        System.out.println(service.greet(user));
    }
}
```

```java
// src/demo/model/User.java
package demo.model;

public record User(String name) { }
```

```java
// src/demo/service/GreetingService.java
package demo.service;

import demo.model.User;

public class GreetingService {
    public String greet(User user) {
        return "Xin chào, " + user.name() + "!";
    }
}
```

Từ thư mục `project`, chạy:

```bash
java src/demo/Main.java Lan
```

Kết quả:

```text
Xin chào, Lan!
```

Bạn chỉ định `Main.java`. Launcher suy ra source root là `src` từ package `demo` và vị trí `src/demo/Main.java`. Các package và thư mục con còn lại tuân theo cấu trúc package, nên `demo.model.User` được tìm trong `src/demo/model/User.java`, còn `demo.service.GreetingService` được tìm trong `src/demo/service/GreetingService.java`.

**Không cần liệt kê mọi tệp nguồn trên command line.** Các tệp phụ thuộc được tìm tự động khi cần theo source tree. Đây là điểm khác biệt quan trọng so với cách biên dịch nhiều tệp bằng `javac`, nơi bạn thường chỉ định danh sách tệp hoặc cấu hình source path.

## 3. Source root và quy tắc package

Launcher xác định source root dựa trên package của class được khởi chạy. Thư mục chứa tệp nguồn phải phản ánh package path:

| Khai báo trong `Main.java` | Vị trí tệp | Source root |
| --- | --- | --- |
| Không có `package` | `project/Main.java` | `project/` |
| `package demo;` | `project/src/demo/Main.java` | `project/src/` |
| `package com.example.app;` | `project/src/com/example/app/Main.java` | `project/src/` |

Với package có tên, chạy bằng đường dẫn tới chính tệp nguồn:

```bash
java src/com/example/app/Main.java
```

Các source file được tìm trong source tree bắt đầu từ source root đó. Tệp phụ thuộc cần nằm trong thư mục tương ứng với package của nó. Nếu một class nằm ngoài source tree hoặc cấu trúc thư mục không khớp package, launcher có thể không tìm thấy source file.

## 4. Phân biệt option của launcher và đối số của chương trình

Các option cần cho JVM hoặc môi trường biên dịch phải đặt trước source file. Những đối số nằm sau source file được chuyển vào `main(String[] args)`.

Ví dụ truyền thư viện bên ngoài qua class path:

```bash
java --class-path "lib/*" src/demo/Main.java Lan
```

Trong lệnh trên:

- `--class-path "lib/*"` là option của launcher, dùng để tìm các class/JAR phụ thuộc đã biên dịch.
- `src/demo/Main.java` là source file chứa điểm vào.
- `Lan` là đối số của chương trình, xuất hiện trong `args[0]`.

Một số option thường dùng trước source file:

| Option | Công dụng |
| --- | --- |
| `-cp`, `-classpath`, `--class-path` | Khai báo class path cho thư viện đã biên dịch. |
| `-p`, `--module-path` | Khai báo module path cho các module phụ thuộc. |
| `--add-modules` | Thêm module vào tập module được resolve. |
| `-Dname=value` | Thiết lập system property cho JVM. |
| `-ea` | Bật assertion khi chạy. |
| `--source N` | Chọn source/API release N cho việc biên dịch source file. |

Ví dụ nhận cả system property và đối số ứng dụng:

```bash
java -Dapp.env=dev --class-path "lib/*" src/demo/Main.java Lan 25
```

Trong `main`, `args` chứa `"Lan"` và `"25"`; system property được đọc bằng `System.getProperty("app.env")`.

Đặt option sau source file sẽ khiến token đó được xem là đối số chương trình. Vì vậy, hãy đặt option JVM, class path và module path trước source file.

## 5. Chọn phiên bản ngôn ngữ bằng `--source`

Mặc định, launcher sử dụng phiên bản source tương ứng với JDK đang chạy. Có thể dùng `--source N` để chọn một source/API release được JDK hiện tại hỗ trợ:

```bash
java --source 27 src/demo/Main.java Lan
```

`--source N` không chỉ giới hạn cú pháp ngôn ngữ. Nó còn giới hạn các public API mà mã nguồn được phép sử dụng theo JDK N, tương đương việc compiler áp dụng release tương ứng. Ví dụ, nếu cần kiểm tra chương trình theo API của một JDK cũ, chọn release đó thay vì chỉ thay đổi mức cú pháp.

Danh sách giá trị `N` được hỗ trợ thay đổi theo từng JDK. Hãy xem `java --help` hoặc tài liệu của đúng JDK đang cài trước khi dùng một release cũ. Không giả định mọi JDK mới đều tiếp tục hỗ trợ tất cả source version từng tồn tại.

Nếu source file dùng tên không kết thúc bằng `.java`, phải chỉ định `--source` để launcher nhận biết đó là source file:

```bash
java --source 27 script
```

Đây là cách dùng dành cho file nguồn được đặt tên như script. Với chương trình Java thông thường, giữ phần mở rộng `.java` giúp command line rõ ràng hơn.

## 6. Dùng với module

Nếu source root có `module-info.java`, launcher sử dụng khai báo module đó để đặt các class được biên dịch từ source tree vào named module. Nếu không có `module-info.java`, các class được biên dịch thuộc unnamed module.

Ví dụ source tree có module descriptor:

```text
project/
└── src/
    ├── module-info.java
    └── demo/
        └── Main.java
```

`module-info.java` có thể khai báo module và các package export/require theo nhu cầu của ứng dụng. Khi khởi chạy `src/demo/Main.java`, source root được xác định là `src`, do đó launcher tìm `module-info.java` ở đó.

Với chương trình nhỏ không cần module riêng, không cần tạo `module-info.java`. Khi dùng module path cho thư viện phụ thuộc, đặt `--module-path` trước source file. Với ứng dụng module phức tạp, nhiều module nguồn hoặc quy trình build cần cấu hình chặt chẽ, nên dùng `javac` cùng build tool để kiểm soát module graph rõ ràng.

## 7. Những giới hạn cần biết

Source-file mode được thiết kế cho việc chạy nhanh chương trình từ mã nguồn, không thay thế toàn bộ quy trình build của một ứng dụng lớn.

### 7.1. Annotation processing bị tắt

Trong source-file mode, annotation processing bị tắt như thể compiler nhận `-proc:none`. Vì vậy, không dựa vào source launcher để chạy annotation processor sinh mã trong lúc biên dịch. Những công cụ cần annotation processing như Lombok hoặc MapStruct cần được cấu hình qua quy trình build phù hợp.

### 7.2. Không truyền được mọi compiler option

Launcher nhận một số option liên quan đến môi trường biên dịch như class path, module path và source release. Nó không cung cấp cơ chế tổng quát để truyền mọi option riêng của `javac`, chẳng hạn `-processor` hoặc `-Werror`. Nếu cần kiểm soát đầy đủ compiler flags, hãy gọi `javac` trực tiếp hoặc dùng Maven/Gradle.

### 7.3. Class đã biên dịch không thể phụ thuộc ngược vào class đang biên dịch từ source tree

Các class được tạo từ source file được nạp bằng custom class loader, loader này ủy quyền cho application class loader. Do đó, class có sẵn trên application class path không thể tham chiếu đến class chỉ được biên dịch trong source-file mode. Chiều ngược lại vẫn dùng được: source file có thể tham chiếu đến class/JAR đã có trên class path.

### 7.4. Trùng tên với class trên class path

Nếu application class path đã có class cùng tên với class điểm vào, launcher báo lỗi thay vì âm thầm chọn một trong hai. Hãy kiểm tra class path và source tree để tránh trùng lặp.

### 7.5. Không tạo thư mục output class file như `javac -d`

Source file được biên dịch vào bộ nhớ để chạy. Nếu cần lưu `.class`, đóng gói JAR, kiểm soát artifact, chạy kiểm thử trong pipeline hoặc triển khai, hãy dùng `javac`/build tool.

### 7.6. Phạm vi source tree có giới hạn

Launcher chỉ tìm source phụ thuộc trong source tree được xác định từ package của tệp điểm vào. Với source nằm ở nhiều root, nhiều module nguồn hoặc được sinh ra trong các bước build, cấu hình source launcher sẽ không thay thế được một build system đầy đủ.

## 8. Khi nào nên dùng source launcher?

| Tình huống | Cách phù hợp |
| --- | --- |
| Học Java, thử API hoặc chạy ví dụ nhỏ có vài class | `java Main.java` |
| Chương trình nhiều package nhưng nằm trong một source tree đơn giản | `java path/to/Main.java` |
| Cần dùng JAR bên ngoài đã có sẵn | Source launcher kết hợp `--class-path` |
| Cần annotation processing, compiler flags tùy chỉnh hoặc sinh mã | `javac` hoặc build tool |
| Cần build reproducible, test, dependency management, đóng gói và phát hành | Maven, Gradle hoặc hệ thống build tương đương |
| Dự án nhiều module nguồn hoặc có quy trình compile phức tạp | Build tool và `javac` với cấu hình module rõ ràng |

Source launcher giúp giảm bước thiết lập khi thử nghiệm hoặc học tập. Khi dự án cần quản lý dependency, kiểm thử, đóng gói và triển khai nhất quán, hãy chuyển sang quy trình build chuyên dụng.

## Ghi nhớ

- JEP 458 đưa khả năng chạy chương trình nhiều source file vào Java 22; đây là tính năng chính thức, không phải preview.
- Chỉ định tệp nguồn chứa điểm vào bằng `java path/to/Main.java`; với source file truyền thống, top-level class đầu tiên được chọn. Từ Java 25, compact source file cũng có thể cung cấp entry point qua implicitly declared class và instance `main`.
- Launcher tự tìm và biên dịch source file phụ thuộc trong source tree; không cần liệt kê từng file `.java` trên command line.
- Source root được suy ra từ package của class điểm vào và cấu trúc thư mục phải khớp package.
- Đặt JVM/compiler options trước source file; các token sau source file được chuyển vào `main(String[] args)`.
- `--source N` chọn source/API release được JDK hiện tại hỗ trợ; mặc định là release của JDK đang chạy.
- Annotation processing bị tắt và không phải mọi compiler option của `javac` đều có thể truyền qua launcher.
- Dùng source launcher cho chương trình nhỏ, ví dụ và thử nghiệm; dùng build tool khi cần quy trình build, test và phát hành đầy đủ.

## Tài liệu tham khảo

- [JEP 458: Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
- [JEP 512: Compact Source Files and Instance Main Methods (Final, JDK 25)](https://openjdk.org/jeps/512)
- [Java SE 27 — The `java` Command, Using Source-File Mode](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs)
- [Java SE 22 — The `java` Command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html)
- [Java SE 25 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html)
- [Dev.java — Launching Simple and Multi-File Source-Code Programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)
