# Cách launcher tìm và biên dịch các tệp nguồn được chương trình tham chiếu

Từ Java 22, lệnh `java` có thể chạy một chương trình được viết trong nhiều tệp `.java` mà không cần gọi `javac` trước. Khi khởi chạy một tệp nguồn, launcher xác định thư mục gốc của cây mã nguồn từ package của lớp được chạy, rồi dùng thư mục đó làm source path để tìm và biên dịch các tệp nguồn khác mà chương trình tham chiếu.

Khả năng này được đưa vào JDK 22 theo JEP 458 và vẫn là hành vi chính thức của source-file mode trong JDK 27. Nó mở rộng chế độ chạy một tệp nguồn có từ Java 11. Đây là cách tiện lợi để chạy ví dụ, công cụ nhỏ, prototype hoặc bài thực hành nhiều lớp. Với dự án cần quản lý dependency, annotation processor, tài nguyên, kiểm thử và đóng gói lặp lại, Maven, Gradle hoặc quy trình build tương đương vẫn phù hợp hơn.

Sau bài học, bạn có thể:

- Chạy một chương trình nhiều tệp bằng một lệnh `java`.
- Giải thích cách launcher suy ra source root từ package của lớp khởi chạy.
- Tổ chức thư mục theo package để launcher tìm được các lớp được tham chiếu.
- Truyền classpath, module path và tham số chương trình đúng vị trí.
- Nhận biết giới hạn của source-file mode về annotation processing, class loader và module.

## 1. Source-file mode và khả năng chạy nhiều tệp

Trước Java 22, source-file mode chủ yếu thuận tiện cho chương trình nằm trong một tệp:

```bash
java Hello.java
```

Launcher biên dịch tệp nguồn vào bộ nhớ rồi chạy lớp chính. Khi chương trình lớn hơn và tham chiếu đến một lớp do bạn tự viết trong tệp khác, cách làm thông thường là biên dịch các tệp bằng `javac`, sau đó chạy lớp chính bằng `java`.

JEP 458 mở rộng source-file mode để launcher có thể tìm các tệp nguồn khác trong cùng cây mã nguồn khi cần. Ví dụ, nếu `Main.java` import `demo.model.Person`, launcher tìm tệp định nghĩa `Person` theo package và biên dịch nó cùng các nguồn cần thiết.

Lệnh khởi chạy vẫn có dạng:

```bash
java path/to/Main.java [arguments...]
```

Bạn chỉ định tệp nguồn chứa lớp khởi chạy. Các tệp nguồn phụ thuộc được tìm và biên dịch tự động theo source root; không cần liệt kê tất cả tệp `.java` trên dòng lệnh.

Tệp nguồn được khởi chạy phải chứa ít nhất một lớp cấp cao nhất. Launcher chọn lớp cấp cao nhất đầu tiên trong tệp đó để chạy, và lớp này phải khai báo một entry `main` method. Vì vậy, hãy đặt lớp có `main` trước các lớp cấp cao nhất khác trong cùng tệp nếu bạn chủ động khai báo nhiều lớp ở đó.

## 2. Cấu trúc thư mục và cách launcher tìm source root

Launcher tính source root dựa trên package khai báo trong tệp nguồn được khởi chạy. Phần đường dẫn tương ứng với package nằm bên dưới source root.

Ví dụ, chương trình có cấu trúc:

```text
project/
└── src/
    └── demo/
        ├── Main.java
        ├── model/
        │   └── Person.java
        └── service/
            └── Greeter.java
```

Tệp khởi chạy khai báo package `demo` và nằm trong `src/demo/Main.java`. Vì vậy launcher suy ra `src` là source root. Các package `demo.model` và `demo.service` tương ứng với các thư mục con `src/demo/model` và `src/demo/service`.

**Main.java**

```java
package demo;

import demo.model.Person;
import demo.service.Greeter;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Bạn" : args[0];
        Person person = new Person(name);
        System.out.println(Greeter.greet(person));
    }
}
```

**model/Person.java**

```java
package demo.model;

public record Person(String name) {}
```

**service/Greeter.java**

```java
package demo.service;

import demo.model.Person;

public class Greeter {
    public static String greet(Person person) {
        return "Xin chào, " + person.name() + "!";
    }
}
```

Chạy từ thư mục `project`:

```bash
java src/demo/Main.java "Nguyễn An"
```

Kết quả:

```text
Xin chào, Nguyễn An!
```

Launcher thấy `Main.java` thuộc package `demo`, suy ra source root là `src`, rồi tìm các nguồn cần thiết cho `demo.model.Person` và `demo.service.Greeter`. Các lớp được biên dịch trong bộ nhớ và nạp để chạy; bạn không phải tạo trước thư mục `out` hay các tệp `.class`.

Nếu lớp khởi chạy không khai báo package, thư mục chứa tệp nguồn đó là source root. Dù dùng package hay unnamed package, hãy giữ cấu trúc thư mục khớp với package để việc tìm nguồn phụ thuộc có thể dự đoán được.

## 3. Launcher biên dịch những tệp nào?

Launcher không đơn giản biên dịch mọi tệp `.java` trong thư mục. Source root trở thành source path cho lần biên dịch; compiler tìm các tệp nguồn cần thiết để giải quyết những kiểu mà chương trình tham chiếu.

Ví dụ, nếu `Main` chỉ dùng `Person` và `Greeter`, các tệp nguồn khai báo những kiểu đó có thể được biên dịch. Một tệp `demo.tools.UnusedTool` không được tham chiếu không nhất thiết được biên dịch trong lần chạy này.

Quy trình khái quát:

```text
java src/demo/Main.java
        |
        v
Đọc package của lớp khởi chạy: demo
        |
        v
Suy ra source root: src
        |
        v
Đặt src làm source path
        |
        v
Tìm và biên dịch các nguồn phụ thuộc cần thiết
        |
        v
Nạp lớp đã biên dịch và gọi main
```

Đây là cách mô tả khái quát. Launcher và compiler vẫn áp dụng quy tắc phân giải kiểu, package, module và classpath của Java. Nếu một kiểu không được tìm thấy, package không khớp với cấu trúc thư mục hoặc mã nguồn có lỗi, quá trình biên dịch thất bại và launcher trả mã thoát khác `0`.

## 4. Dùng thư viện ngoài qua classpath

Source-file mode có thể dùng các thư viện đã biên dịch như JAR. Hãy đặt tùy chọn classpath trước đường dẫn tệp nguồn:

```bash
java --class-path "lib/json-library.jar" src/demo/Main.java input.json
```

Launcher sử dụng classpath cho môi trường biên dịch và thực thi. Trên Windows, dấu phân cách nhiều phần tử classpath là dấu chấm phẩy (`;`); trên Linux và macOS là dấu hai chấm (`:`). Dùng dấu ngoặc kép khi đường dẫn có khoảng trắng hoặc khi shell cần giữ nguyên ký tự đặc biệt.

Nếu thư viện là module trên module path, có thể dùng `--module-path` và các tùy chọn module phù hợp trước tệp nguồn. Các tùy chọn môi trường biên dịch được hỗ trợ trong source-file mode gồm `--class-path`, `--module-path`, `--add-exports`, `--add-modules`, `--limit-modules`, `--patch-module` và `--upgrade-module-path`.

Một giới hạn quan trọng liên quan đến class loader: các lớp được biên dịch từ source file được nạp bởi một class loader riêng, có ủy quyền cho application class loader. Do đó, mã nguồn đang chạy có thể tham chiếu thư viện trên classpath, nhưng lớp đã có trên application classpath không thể tham chiếu ngược đến lớp chỉ được biên dịch từ source files trong lần khởi chạy đó. Ngoài ra, nếu classpath đã có lớp trùng tên với lớp được khởi chạy, launcher báo lỗi.

## 5. Vị trí tùy chọn launcher và tham số chương trình

Trong source-file mode, các tùy chọn launcher cần thiết phải đặt trước tệp nguồn. Những đối số sau tệp nguồn được chuyển cho `main` của chương trình.

```bash
java -Dapp.mode=demo --class-path "lib/*" src/demo/Main.java "Nguyễn An" --verbose
```

Trong ví dụ này:

- `-Dapp.mode=demo` là tùy chọn JVM.
- `--class-path "lib/*"` cung cấp thư viện cho biên dịch và chạy.
- `src/demo/Main.java` chọn source-file mode và chỉ định lớp khởi chạy.
- `"Nguyễn An"` và `--verbose` là đối số chương trình, có thể đọc từ `args`.

Không đặt đối số chương trình trước tệp nguồn vì launcher có thể hiểu chúng là tên lớp hoặc tùy chọn launcher. Tương tự, không đặt `--class-path` sau tên tệp nguồn với ý định cấu hình classpath; ở vị trí đó nó thuộc danh sách đối số được truyền cho chương trình.

Nếu tệp nguồn không có phần mở rộng `.java`, phải chỉ rõ `--source` để launcher nhận biết source-file mode. Tùy chọn `--source N` cũng xác định phiên bản ngôn ngữ và tập public API được phép dùng khi biên dịch. Giá trị `N` được hỗ trợ thay đổi theo từng JDK; JDK hiện hành chỉ hỗ trợ phiên bản hiện tại và một số phiên bản trước đó. Đừng giả định mọi JDK mới đều còn chấp nhận `--source 22`.

## 6. Chạy chương trình có module-info.java

Nếu source root chứa `module-info.java`, launcher sử dụng khai báo module đó để biên dịch các lớp nguồn trong cây và chạy chúng trong named module. Nếu không có `module-info.java`, các lớp nguồn được biên dịch trong unnamed module.

Ví dụ source root có thể được tổ chức như sau:

```text
project/
└── src/
    ├── module-info.java
    └── demo/
        └── Main.java
```

**module-info.java**

```java
module demo.app {
    exports demo;
}
```

**Main.java**

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("Running in a named module");
    }
}
```

Khi `module-info.java` ở source root, các lớp được biên dịch từ cây nguồn thuộc module được khai báo ở đó. Nếu cần phụ thuộc module khác, khai báo `requires` trong module descriptor và cung cấp module trên module path bằng tùy chọn launcher tương ứng.

Với ứng dụng module phức tạp, nhiều module nguồn hoặc cần đóng gói và triển khai, hãy dùng quy trình build/module thông thường. Source-file mode hữu ích cho ví dụ nhỏ, nhưng không thay thế toàn bộ công cụ quản lý module của dự án.

## 7. Giới hạn cần biết trước khi sử dụng

Source-file mode có một số giới hạn khiến nó không phù hợp với mọi dự án:

| Giới hạn | Tác động thực tế |
|---|---|
| Annotation processing bị tắt (tương đương `-proc:none`) | Không dùng source launcher để chạy quy trình phụ thuộc annotation processor sinh mã. |
| Không truyền được tùy chọn compiler tùy ý như `-processor` hoặc `-Werror` | Nếu cần kiểm soát đầy đủ javac, hãy gọi `javac` hoặc build tool. |
| Source root được suy ra từ package của lớp khởi chạy | Cấu trúc package và thư mục phải rõ ràng; không phải source tree tùy ý nào cũng tự phân giải được. |
| Lớp từ application classpath không thể tham chiếu ngược lớp chỉ có trong source tree được launcher biên dịch | Tránh trộn hai chiều dependency giữa JAR có sẵn và nguồn được biên dịch tạm thời. |
| Chỉ các nguồn cần thiết được biên dịch | Một tệp nguồn không được tham chiếu có thể không được kiểm tra trong lần chạy. |
| Kết quả biên dịch nằm trong bộ nhớ | Không tạo thư mục output có thể triển khai như một build thông thường. |
| Có quy tắc riêng khi classpath chứa lớp trùng tên với lớp khởi chạy | Cần tránh xung đột tên lớp giữa mã nguồn và dependency. |

Ngoài ra, source-file mode không tự giải quyết phiên bản dependency, tải thư viện từ repository, quản lý tài nguyên đóng gói, chạy test suite hay tạo artifact phát hành. Đây là các trách nhiệm thường thuộc về Maven, Gradle hoặc công cụ build của dự án.

## 8. Khi nào nên dùng source launcher nhiều tệp?

| Tình huống | Khuyến nghị |
|---|---|
| Bài học có `Main`, model và service ở các tệp riêng | Rất phù hợp; chạy trực tiếp tệp `Main.java`. |
| Prototype nhỏ cần thử nhanh một API | Phù hợp, đặc biệt khi dependency có sẵn trên classpath. |
| Script nội bộ có một vài lớp phụ trợ | Có thể dùng nếu cấu trúc package và quyền truy cập file rõ ràng. |
| Dự án cần annotation processor hoặc code generation | Dùng `javac` hoặc build tool. |
| Ứng dụng có nhiều module, tài nguyên, test và dependency phức tạp | Dùng Maven, Gradle hoặc quy trình build tương đương. |
| Cần artifact `.class`, JAR hoặc image triển khai tái lập | Dùng quy trình biên dịch và đóng gói thông thường. |

Điểm tiện lợi của source launcher là giảm bước thiết lập khi học hoặc thử nghiệm. Khi chương trình trở thành một phần của sản phẩm, việc chuyển sang build tool giúp kiểm soát phiên bản, dependency, kiểm thử và đóng gói rõ ràng hơn.

## 9. Phiên bản Java và trạng thái hiện hành

| Phiên bản | Khả năng source launcher |
|---|---|
| Java 11 | Có source-file mode cho chương trình một tệp. |
| Java 22 | JEP 458 bổ sung khả năng tìm và biên dịch các tệp nguồn phụ thuộc trong source tree. Đây là tính năng chính thức, không phải preview. |
| JDK hiện hành (Java SE 27) | Hỗ trợ source-file mode nhiều tệp; quy tắc được mô tả trong tài liệu lệnh `java`. |

Không cần `--enable-preview` để dùng JEP 458. Với JDK 22, có thể chạy ví dụ bằng lệnh `java src/demo/Main.java`. Trên JDK mới, cùng cú pháp source-file mode vẫn được hỗ trợ; hãy kiểm tra tài liệu launcher của phiên bản triển khai nếu phụ thuộc vào một tùy chọn hoặc source level cụ thể.

Nếu muốn hiểu cách launcher làm việc, có thể xem source-file mode như một quy trình biên dịch ngầm tương đương về mặt khái niệm với việc gọi `javac` trên tệp khởi chạy cùng source path, sau đó chạy lớp đã biên dịch. Tuy nhiên, launcher quản lý lớp đã biên dịch trong bộ nhớ và áp dụng class loader riêng, vì vậy không nên coi nó hoàn toàn giống một lệnh build thủ công.

## 10. Kết luận

JEP 458 giúp launcher `java` chạy chương trình nhiều tệp bằng cách tự tìm và biên dịch các nguồn phụ thuộc. Launcher suy ra source root từ package của lớp khởi chạy, dùng thư mục đó làm source path, rồi biên dịch các tệp cần thiết để thực thi chương trình.

Để sử dụng hiệu quả, hãy tổ chức thư mục theo package, đặt tùy chọn classpath hoặc module path trước tệp nguồn, và đặt đối số chương trình sau tệp nguồn. Cần nhớ các giới hạn về annotation processing, compiler options và class loader. Source launcher nhiều tệp là tính năng chính thức từ Java 22 và vẫn hữu ích trên JDK hiện đại cho chương trình nhỏ, ví dụ và prototype.

## Tài liệu tham khảo

- [JEP 458: Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
- [Java SE 22: The `java` Command — Source-File Mode](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html)
- [Java SE 27: The `java` Command — Using Source-File Mode](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Dev.java: Launching a Multi-File Program](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)
