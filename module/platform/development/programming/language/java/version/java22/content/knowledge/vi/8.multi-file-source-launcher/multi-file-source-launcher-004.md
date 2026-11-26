# Package, thư mục gốc nguồn và cách tổ chức các tệp phụ thuộc

Từ Java 22, lệnh **java** có thể chạy một chương trình gồm nhiều tệp nguồn trực tiếp. Khi khởi chạy một tệp **.java**, launcher tự xác định thư mục gốc của cây mã nguồn dựa trên package của lớp được chạy, rồi tìm và biên dịch những tệp nguồn phụ thuộc cần thiết trong cây đó.

Tính năng này được giới thiệu qua **JEP 458 — Launch Multi-File Source-Code Programs** và đã final ngay trong JDK 22. Nó tiếp tục được hỗ trợ trong JDK hiện đại, bao gồm JDK 25 LTS và JDK 27. Đây là mở rộng của source-file mode từng hỗ trợ chạy một tệp nguồn; không cần preview hoặc incubator để dùng tính năng nhiều tệp.

## 1. Source-file mode hoạt động như thế nào?

Thông thường, source-file mode được chọn khi đối số đầu tiên không phải tùy chọn của lệnh **java** là một đường dẫn tới tệp có phần mở rộng **.java**:

~~~shell
java Main.java
~~~

Launcher biên dịch mã nguồn trong bộ nhớ rồi chạy lớp chính được khai báo trong tệp. Với JDK 22 trở lên, quá trình biên dịch còn có thể tìm các tệp nguồn khác mà lớp chính phụ thuộc vào.

Có thể hình dung lệnh trên tương đương về ý tưởng với việc biên dịch tệp chính cùng source path rồi chạy lớp đã biên dịch:

~~~shell
javac -d <memory> --source-path <source-root> Main.java
java --class-path <memory> Main
~~~

Đây chỉ là mô hình giải thích. Launcher thực hiện việc biên dịch và nạp lớp trong bộ nhớ; bạn không cần tạo thư mục class output hoặc chạy hai lệnh riêng.

Khi khởi chạy, launcher:

1. Đọc package của lớp trong tệp nguồn được chỉ định.
2. Dựa vào package và vị trí tệp để xác định **source root**.
3. Dùng source root làm nơi tìm kiếm các tệp nguồn Java phụ thuộc.
4. Biên dịch những tệp nguồn cần thiết.
5. Nạp các lớp được biên dịch trong bộ nhớ và gọi entry point của lớp đầu tiên trong tệp được khởi chạy.

Launcher không nhất thiết biên dịch mọi tệp .java trong cây nguồn. Nó tìm những source file cần thiết để biên dịch chương trình bắt đầu từ tệp được chỉ định.

## 2. Tổ chức package và thư mục nguồn

Trong Java, cấu trúc thư mục của source tree nên phản ánh package được khai báo trong từng tệp. Ví dụ một chương trình nhỏ có ba lớp:

~~~text
my-app/
└── src/
    └── com/
        └── acme/
            ├── app/
            │   └── Main.java
            ├── model/
            │   └── Person.java
            └── service/
                └── GreetingService.java
~~~

Nội dung các tệp:

**src/com/acme/app/Main.java**

~~~java
package com.acme.app;

import com.acme.model.Person;
import com.acme.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Bạn";

        Person person = new Person(name);
        GreetingService service = new GreetingService();

        System.out.println(service.greet(person));
    }
}
~~~

**src/com/acme/model/Person.java**

~~~java
package com.acme.model;

public record Person(String name) {
}
~~~

**src/com/acme/service/GreetingService.java**

~~~java
package com.acme.service;

import com.acme.model.Person;

public class GreetingService {
    public String greet(Person person) {
        return "Xin chào, " + person.name() + "!";
    }
}
~~~

Từ thư mục **my-app**, chạy:

~~~shell
java src/com/acme/app/Main.java An
~~~

Kết quả:

~~~text
Xin chào, An!
~~~

Không cần liệt kê **Person.java** và **GreetingService.java** trong lệnh. Launcher suy ra source root là **src** từ package **com.acme.app** và vị trí **Main.java**. Khi biên dịch **Main**, compiler tìm các kiểu được import trong những package tương ứng dưới source root.

Ví dụ này dùng các package thông thường và entry point **public static void main(String[] args)** để chạy được trên JDK 22 đến các JDK mới hơn.

## 3. Source root được xác định từ package

**Source root** là thư mục gốc của cây source file mà launcher dùng để tìm các tệp .java phụ thuộc. Nó không nhất thiết là thư mục hiện tại của terminal, cũng không nhất thiết có tên **src**.

Giả sử tệp khởi chạy khai báo:

~~~java
package com.acme.app;
~~~

Và được lưu ở:

~~~text
workspace/
└── source-code/
    └── com/
        └── acme/
            └── app/
                └── Main.java
~~~

Đường dẫn package **com.acme.app** tương ứng với các thư mục **com/acme/app**. Vì vậy source root là **source-code**.

| Package trong tệp khởi chạy | Vị trí tệp | Source root |
|---|---|---|
| **com.acme.app** | **src/com/acme/app/Main.java** | **src** |
| **org.example.tool** | **source/org/example/tool/Launcher.java** | **source** |
| **com.store.api.v1** | **app-src/com/store/api/v1/Main.java** | **app-src** |
| Không khai báo package | **src/Main.java** | **src** |

Nếu lớp không khai báo package, đặt tệp khởi chạy trực tiếp trong source root. Không trộn lớp thuộc unnamed package với lớp thuộc named package trong cùng một thiết kế ứng dụng; hãy tổ chức package rõ ràng khi chương trình có nhiều lớp.

### Chạy từ thư mục source root

Có thể đổi thư mục làm việc sang source root rồi truyền đường dẫn tương đối đến tệp khởi chạy:

~~~shell
cd src
java com/acme/app/Main.java An
~~~

Source root vẫn là **src**. Đường dẫn tương đối chỉ thay đổi theo thư mục làm việc; quy tắc package không thay đổi.

Nếu chạy từ thư mục khác, có thể truyền đường dẫn đầy đủ hoặc đường dẫn tương đối đúng tới tệp .java. Hãy bảo đảm đường dẫn của tệp khởi chạy phản ánh package mà nó khai báo.

## 4. Cách launcher tìm các tệp nguồn phụ thuộc

Giả sử **Main.java** import một lớp:

~~~java
import com.acme.model.Person;
~~~

Launcher/compiler tìm source tương ứng dưới source root theo package:

~~~text
<source-root>/
└── com/
    └── acme/
        └── model/
            └── Person.java
~~~

Nếu lớp đó lại phụ thuộc vào lớp khác trong một package khác, quá trình biên dịch tiếp tục tìm source cần thiết trong cùng cây nguồn.

Ví dụ quan hệ phụ thuộc:

~~~mermaid
flowchart TD
    A["Main.java<br/>com.acme.app"] --> B["Person.java<br/>com.acme.model"]
    A --> C["GreetingService.java<br/>com.acme.service"]
    C --> B
~~~

Một số quy tắc tổ chức cần giữ:

- Mỗi tệp source dependency nên nằm trong thư mục tương ứng với package khai báo trong tệp.
- Tên tệp nên khớp với tên top-level public class, interface, enum hoặc record theo quy tắc Java thông thường.
- Các source dependency cần được đặt trong cùng source tree mà launcher suy ra từ tệp được khởi chạy.
- Câu lệnh **import** phải dùng đúng tên package và kiểu dữ liệu.
- Không cần ghi tất cả source dependency trên command line; launcher tìm chúng theo tham chiếu kiểu trong quá trình biên dịch.

Nếu một lớp nằm ngoài source root, launcher không tự quét mọi thư mục của dự án để tìm nó. Hãy đặt source vào đúng cây nguồn, hoặc biên dịch/đóng gói dependency đó riêng rồi đưa vào classpath hay module path.

## 5. Kết hợp source file với thư viện đã biên dịch

Source-file mode tự tìm các tệp .java trong source tree. Với thư viện bên ngoài đã được biên dịch thành JAR hoặc module, truyền đường dẫn tương ứng vào launcher.

### Dependency trên classpath

Giả sử chương trình dùng một thư viện đã biên dịch nằm trong thư mục **lib**:

~~~text
my-app/
├── lib/
│   └── commons-text.jar
└── src/
    └── com/
        └── acme/
            └── app/
                └── Main.java
~~~

Chạy:

~~~shell
java --class-path "lib/commons-text.jar" src/com/acme/app/Main.java
~~~

Có thể dùng wildcard classpath nếu thư mục chứa nhiều JAR:

~~~shell
java --class-path "lib/*" src/com/acme/app/Main.java
~~~

Tùy chọn classpath phải đặt trước tệp nguồn được khởi chạy. Launcher dùng classpath để tìm các lớp đã biên dịch trong lúc biên dịch source file và khi thực thi chương trình.

Có một giới hạn về class loader cần nhớ: các lớp được biên dịch từ source file được nạp bởi class loader riêng, có ủy quyền cho application class loader. Vì vậy, source code có thể tham chiếu các lớp trên classpath, nhưng các lớp đã có trên application classpath không thể tham chiếu ngược đến các lớp chỉ được biên dịch trong source-file mode.

### Dependency trên module path

Nếu thư viện bên ngoài là named module, đặt module đã biên dịch trên module path:

~~~shell
java --module-path "mods" src/com/acme/app/Main.java
~~~

Các tùy chọn như **--class-path**, **--module-path**, **--add-modules** và một số tùy chọn liên quan module được launcher xử lý khi biên dịch source file. Đặt các tùy chọn đó trước tên tệp .java.

Không dùng classpath thay cho module path khi dependency được thiết kế và phân phối như named module cần được resolve theo module system.

## 6. Dùng module-info.java trong source tree

Nếu source root có tệp **module-info.java**, launcher sử dụng khai báo module đó để đặt các lớp được biên dịch từ source tree vào một named module. Nếu không có **module-info.java**, các lớp được biên dịch thuộc unnamed module.

Ví dụ cấu trúc module:

~~~text
my-app/
├── mods/
│   └── com.acme.logging.jar
└── src/
    ├── module-info.java
    └── com/
        └── acme/
            └── app/
                └── Main.java
~~~

**src/module-info.java**

~~~java
module com.acme.app {
    requires com.acme.logging;
}
~~~

**src/com/acme/app/Main.java**

~~~java
package com.acme.app;

import com.acme.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger.info("Ứng dụng bắt đầu");
    }
}
~~~

Chạy:

~~~shell
java --module-path mods src/com/acme/app/Main.java
~~~

Trong ví dụ, **src** là source root và **module-info.java** nằm ngay tại thư mục đó. Các source file được biên dịch thuộc module **com.acme.app**. Module **com.acme.logging** là dependency đã biên dịch được tìm trên module path.

Khi source tree có module descriptor:

- Tên module lấy từ khai báo trong **module-info.java**.
- Các package và lớp nguồn trong source tree thuộc module đó.
- Các dependency module phải được khai báo bằng **requires** và có mặt trên module path.
- Quy tắc export/readability của Java Module System vẫn được áp dụng.

Nếu không cần named module, có thể không tạo **module-info.java**. Khi đó các lớp trong source tree được chạy trong unnamed module.

## 7. Tham số dòng lệnh và tùy chọn source version

Mọi đối số đặt sau tên tệp nguồn được chuyển đến phương thức **main**:

~~~shell
java src/com/acme/app/Main.java "Nguyễn An"
~~~

Trong ví dụ này, chuỗi **Nguyễn An** là phần tử đầu tiên của **args**.

Có thể dùng tùy chọn **--source N** trước tên tệp để chỉ định phiên bản ngôn ngữ và API Java mà source file được phép sử dụng:

~~~shell
java --source 27 src/com/acme/app/Main.java An
~~~

Nếu không chỉ định **--source**, launcher dùng phiên bản source mặc định tương ứng với JDK đang chạy. Khi chỉ định **--source N**, compiler áp dụng tương đương một **--release N** cho source file, tức vừa giới hạn cú pháp ngôn ngữ vừa giới hạn API Java SE được phép dùng.

Các giá trị **N** được hỗ trợ thay đổi theo từng JDK. Chỉ chọn phiên bản được launcher/compiler của JDK đang cài đặt hỗ trợ; không giả định mọi phiên bản Java cũ đều luôn được chấp nhận.

Các tùy chọn JVM/compiler environment phải đặt trước source file:

~~~shell
java --class-path "lib/*" --source 27 src/com/acme/app/Main.java An
~~~

Các đối số sau source file là tham số chương trình, không còn là tùy chọn launcher. Nếu cần danh sách đối số dài, launcher cũng hỗ trợ argument file theo cú pháp **@file**.

## 8. Giới hạn của source-file mode

Multi-file source launcher phù hợp để chạy nhanh chương trình nhỏ, ví dụ học Java, demo API, script nội bộ hoặc công cụ đơn giản. Nó không thay thế toàn bộ quy trình build của dự án phần mềm.

| Giới hạn | Ý nghĩa khi tổ chức dự án |
|---|---|
| Source root được suy ra từ package và vị trí file khởi chạy | Không thể kỳ vọng launcher tìm source ở bất kỳ thư mục nào ngoài source tree đã xác định |
| Tệp nguồn phụ thuộc phải nằm trong source tree | Dependency ngoài cây nguồn cần được biên dịch/đóng gói riêng hoặc đặt trên classpath/module path |
| Annotation processing bị tắt | Các annotation processor dùng để sinh source hoặc metadata không chạy trong source-file mode |
| Không truyền được mọi compiler option | Các tùy chọn như **-processor** hoặc **-Werror** không có cơ chế truyền riêng cho compiler qua source-file mode |
| Lớp được biên dịch trong bộ nhớ | Không có thư mục output .class để đóng gói hoặc triển khai trực tiếp |
| Có custom class loader | Lớp trên application classpath không thể phụ thuộc ngược vào lớp chỉ có trong source tree đang chạy |
| Tài nguyên và quy trình build không được quản lý đầy đủ | Copy resource, xử lý generated source, kiểm thử, đóng gói và reproducible build cần công cụ phù hợp |

Nếu dự án sử dụng annotation processor, code generation, nhiều module, resource filtering, unit/integration test, đóng gói JAR hoặc quy trình CI/CD, hãy dùng **javac** cùng Maven hoặc Gradle. Các công cụ build cung cấp cấu hình source set, dependency, compiler options và output rõ ràng hơn.

## 9. Các lỗi thường gặp khi tổ chức nhiều source file

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy lớp được import | Source file không nằm dưới source root hoặc package không khớp thư mục | Kiểm tra package declaration và vị trí tệp theo cây thư mục |
| Chạy được Main nhưng thiếu dependency ngoài | JAR chưa được đặt trên classpath hoặc module path | Thêm **--class-path** hoặc **--module-path** trước source file |
| Lớp trong JAR không truy cập được package của module khác | Module chưa export package hoặc module ứng dụng chưa requires dependency | Kiểm tra **module-info.java** của các module |
| Chạy sai lớp chính trong file | Có nhiều top-level class và lớp đầu tiên không phải lớp mong muốn | Đặt lớp entry point đầu tiên trong file khởi chạy |
| Compiler không chạy annotation processor | Source-file mode tự tắt annotation processing | Chuyển sang quy trình **javac** hoặc build tool |
| Classpath dependency không thấy kiểu chỉ có trong source tree | Classpath class không thể tham chiếu ngược tới lớp do source launcher nạp | Đưa các lớp cần chia sẻ vào dependency đã biên dịch hoặc tổ chức lại ranh giới module |
| Báo trùng tên lớp chính | Application classpath đã chứa class cùng tên với lớp đang được khởi chạy | Loại bỏ bản class trùng hoặc dùng classpath phù hợp |

## 10. Quy trình kiểm tra source tree trước khi chạy

1. **Xác định package của lớp khởi chạy.** Đọc dòng package trong file .java.
2. **Kiểm tra vị trí file.** Các thư mục cuối của đường dẫn phải khớp package; phần đường dẫn còn lại là source root.
3. **Liệt kê source dependency.** Tìm các lớp được import hoặc tham chiếu trực tiếp và kiểm tra file tương ứng trong cùng source root.
4. **Kiểm tra dependency đã biên dịch.** Xác định JAR nào cần classpath và module nào cần module path.
5. **Kiểm tra module descriptor.** Nếu source root có module-info.java, xác minh requires và module path của dependency.
6. **Chạy từ đúng đường dẫn.** Đặt các tùy chọn launcher trước source file; đặt đối số ứng dụng sau source file.
7. **Chuyển sang build tool khi cần.** Nếu cần annotation processing, generated sources, kiểm thử hoặc đóng gói, cấu hình Maven/Gradle và chạy compiler/build pipeline phù hợp.

## Tài liệu tham khảo chính thức

- [JEP 458 — Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458): đặc tả tính năng được đưa vào JDK 22.
- [The java Command — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html): source-file mode, cách tính source root và quy tắc tìm source dependency tại phiên bản giới thiệu.
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): hành vi source-file mode hiện hành, module-info, classloader và tùy chọn launcher.
- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): source path, module source path và compiler options khi cần quy trình biên dịch đầy đủ.
- [Launching a Multi-File Program — dev.java](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/): ví dụ tổ chức package và chạy chương trình nhiều source file.

