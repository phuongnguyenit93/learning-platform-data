# JEP 458: thực thi chương trình nhiều tệp Java trực tiếp bằng source launcher

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách `java` launcher tìm và biên dịch các tệp nguồn được chương trình tham chiếu.
- Tổ chức các tệp Java theo package để chạy chương trình mà không cần gọi `javac` riêng.
- Kết hợp source launcher với thư viện bên ngoài và nhận biết những giới hạn của cách chạy này.

## JEP 458 giải quyết vấn đề gì?

Trong quy trình Java thông thường, bạn biên dịch mã nguồn thành bytecode rồi mới chạy lớp chứa điểm vào chương trình:

```bash
javac Main.java Helper.java
java Main
```

Source-file mode của `java` launcher cho phép chạy trực tiếp một tệp `.java`. Trước Java 22, cách chạy này phù hợp nhất với chương trình nằm trong một tệp; khi tách lớp sang các tệp nguồn khác, bạn thường phải biên dịch chúng trước.

JEP 458, được đưa vào JDK 22, mở rộng source-file mode: khi tệp nguồn khởi chạy tham chiếu đến các kiểu được khai báo trong những tệp `.java` khác, launcher có thể tìm, biên dịch và nạp các tệp nguồn cần thiết trong cùng cây mã nguồn. Vì vậy, bạn có thể tổ chức một ví dụ hoặc tiện ích nhỏ thành nhiều tệp mà vẫn khởi chạy bằng một lệnh:

```bash
java Main.java
```

Việc biên dịch vẫn diễn ra; launcher tự thực hiện trong lúc khởi chạy. Đây là tính năng tiêu chuẩn từ JDK 22, không cần bật preview.

## Chuẩn bị môi trường

Sử dụng JDK 22 trở lên. Kiểm tra phiên bản Java đang được gọi trong terminal:

```bash
java --version
```

Hãy chắc chắn lệnh `java` trỏ đến bản JDK mong muốn. Source-file mode cần trình biên dịch đi kèm JDK.

Khi đối số đầu tiên của launcher là đường dẫn đến tệp `.java` tồn tại, `java` chọn source-file mode:

```bash
java Main.java
```

Lệnh sau có ý nghĩa khác: nó chạy lớp `Main` đã được biên dịch và có thể tìm thấy trên class path hoặc module path.

```bash
java Main
```

## Chạy chương trình gồm nhiều tệp

Giả sử bạn có cấu trúc thư mục sau:

```text
demo/
├── Main.java
├── model/
│   └── Person.java
└── service/
    └── GreetingService.java
```

`model/Person.java` khai báo một kiểu trong package `model`:

```java
package model;

public record Person(String name) {
}
```

`service/GreetingService.java` sử dụng kiểu `Person`:

```java
package service;

import model.Person;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(Person person) {
        return "Xin chào, " + person.name() + "!";
    }
}
```

Tệp khởi chạy `Main.java` nằm trong package mặc định và tham chiếu đến cả hai kiểu trên:

```java
import model.Person;
import service.GreetingService;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : String.join(" ", args);
        Person person = new Person(name);

        System.out.println(GreetingService.greet(person));
    }
}
```

Mở terminal tại thư mục `demo` và chạy:

```bash
java Main.java Phuong
```

Kết quả:

```text
Xin chào, Phuong!
```

Bạn chỉ truyền `Main.java` cho launcher. Khi biên dịch `Main`, trình biên dịch phát hiện các tham chiếu đến `Person` và `GreetingService`, sau đó tìm các tệp nguồn tương ứng trong cây mã nguồn và biên dịch chúng khi cần. Không phải liệt kê `Person.java` và `GreetingService.java` trên dòng lệnh.

## Cách launcher tìm các tệp nguồn

Launcher xác định thư mục gốc của cây mã nguồn (*source root*) từ package được khai báo trong tệp khởi chạy và vị trí của tệp đó trên hệ thống tệp. Thư mục gốc này được dùng làm source path để tìm những tệp nguồn cần thiết.

Nếu tệp khởi chạy không khai báo package, thư mục chứa tệp đó là source root. Trong ví dụ trên, `Main.java` không có khai báo `package`, vì vậy `demo/` là source root. Các lớp trong package `model` và `service` phải nằm lần lượt trong `demo/model/` và `demo/service/`.

Với tệp khởi chạy có package, cấu trúc thư mục phải khớp với tên package. Ví dụ:

```text
project/
└── src/
    └── com/
        └── example/
            ├── Main.java
            └── Greeter.java
```

Nếu `Main.java` khai báo `package com.example;`, hãy chạy từ thư mục `project`:

```bash
java src/com/example/Main.java
```

Trong trường hợp này, `src/` là source root. Một tệp khai báo `package com.example` cần nằm trong thư mục `com/example` bên dưới source root để launcher tìm thấy nó theo cấu trúc package.

## Truyền tham số và dùng thư viện bên ngoài

Các đối số xuất hiện sau đường dẫn tệp `.java` được chuyển cho phương thức `main` của chương trình. Ví dụ:

```bash
java Main.java Nguyen Van An
```

Trong chương trình mẫu, `args` nhận ba phần tử và `String.join(" ", args)` ghép chúng thành tên `Nguyen Van An`.

Source launcher cũng có thể dùng thư viện đã được đóng gói thành JAR. Đặt JAR trong thư mục `lib` rồi thêm thư mục đó vào class path:

```bash
java --class-path "lib/*" Main.java Phuong
```

Class path cung cấp các lớp đã biên dịch để trình biên dịch và chương trình sử dụng. Các tệp `.java` thuộc chương trình vẫn được tìm trong source tree bắt đầu từ source root đã xác định. Với thư viện dạng module, dùng module path và cấu hình module tương ứng.

## Chương trình dùng Java Platform Module System

Nếu source root có tệp `module-info.java`, launcher dùng khai báo trong tệp đó để đặt các lớp nguồn được biên dịch vào một named module. Nếu không có `module-info.java`, các lớp được biên dịch trong unnamed module.

Các dependency dạng module đã biên dịch được cung cấp qua module path. Source launcher hỗ trợ trường hợp chương trình nguồn thuộc một module; việc tổ chức nhiều module, quản lý phiên bản dependency và đóng gói ứng dụng vẫn nên được thực hiện bằng hệ thống build phù hợp.

## Điều gì xảy ra khi chạy?

Quá trình có thể hình dung qua các bước:

1. `java` nhận diện source-file mode từ đường dẫn `.java` được truyền vào.
2. Launcher xác định source root dựa trên package và vị trí của tệp khởi chạy.
3. Trình biên dịch biên dịch tệp khởi chạy và các tệp nguồn cần thiết được tham chiếu trong source tree.
4. Launcher nạp lớp đầu tiên ở cấp cao nhất trong tệp khởi chạy và gọi phương thức `main` phù hợp.

Các lớp được biên dịch cho lần chạy này được lưu trong bộ nhớ để nạp và thực thi. Cách chạy này không yêu cầu bạn tự tạo thư mục chứa `.class` trước khi chạy. Tệp khởi chạy phải có lớp cấp cao nhất đầu tiên chứa điểm vào `main` mà launcher có thể gọi.

## Giới hạn cần biết

- **Cấu trúc package phải đúng:** launcher tìm tệp nguồn theo source root và đường dẫn package. Tệp đặt sai thư mục có thể khiến kiểu được tham chiếu không tìm thấy.
- **Không chạy annotation processing:** source-file mode hoạt động như thể `-proc:none` được bật. Các annotation processor như bộ xử lý tạo mã không được thực thi trong lần khởi chạy này.
- **Không truyền được mọi tùy chọn của `javac`:** launcher chỉ xử lý những tùy chọn biên dịch được hỗ trợ trong source-file mode. Các tùy chọn chuyên sâu như cấu hình annotation processor hoặc `-Werror` không thể được chuyển tùy ý như khi gọi `javac` trực tiếp.
- **Không thay thế quy trình build đầy đủ:** khi ứng dụng cần nhiều module, sinh mã, quản lý dependency theo phiên bản, chạy test, đóng gói hoặc triển khai lặp lại, hãy dùng `javac` cùng công cụ build như Maven hoặc Gradle.
- **Lỗi biên dịch xuất hiện khi khởi chạy:** vì biên dịch diễn ra trong lần chạy, lỗi ở một tệp nguồn phụ thuộc có thể chỉ được phát hiện khi launcher cần biên dịch tệp đó.

## Khi nào nên dùng source launcher?

Source launcher phù hợp với bài thực hành, ví dụ giảng dạy, thử nghiệm API, script nội bộ hoặc tiện ích nhỏ có cấu trúc nhiều tệp nhưng chưa cần cấu hình build. Bạn vẫn có thể chia lớp theo trách nhiệm và package ngay từ đầu, sau đó chạy chương trình bằng một lệnh.

Khi dự án cần cấu hình biên dịch ổn định, dependency phức tạp, kiểm thử tự động, đóng gói hoặc quy trình phát hành, hãy chuyển sang quy trình build tường minh. JEP 458 giúp bắt đầu với ít cấu hình hơn; nó không loại bỏ nhu cầu quản lý vòng đời của một dự án Java lớn.

## Phân biệt ba cách gọi `java`

| Lệnh | Chế độ | Điều kiện |
|---|---|---|
| `java Main.java` | Source-file mode | Có tệp nguồn; launcher biên dịch tệp đó và các nguồn phụ thuộc cần thiết. |
| `java Main` | Class mode | Lớp `Main` đã được biên dịch và có thể tìm thấy trên class path hoặc module path. |
| `javac Main.java` rồi `java Main` | Biên dịch và chạy tường minh | Bạn chủ động kiểm soát bước biên dịch, thư mục đầu ra và các tùy chọn của compiler. |

## Tự kiểm tra

1. Vì sao lệnh `java Main.java` có thể chạy được khi `Main` tham chiếu đến một lớp nằm trong tệp `.java` khác?
2. Nếu `Main.java` khai báo `package com.example`, source root được xác định như thế nào?
3. Bạn cần làm gì để source launcher sử dụng một thư viện được đóng gói trong JAR?
4. Vì sao một dự án dùng annotation processor hoặc cần đóng gói nhiều module thường phù hợp hơn với Maven hoặc Gradle?

## Tài liệu tham khảo

- [JEP 458: Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
- [The `java` Command — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html)
- [Launching Simple Source-Code Programs — dev.java](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)
