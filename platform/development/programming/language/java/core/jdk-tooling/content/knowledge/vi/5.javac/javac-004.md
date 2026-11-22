# Source path trong javac

Source path là danh sách thư mục gốc mà trình biên dịch Java dùng để tìm các tệp mã nguồn khi cần phân giải kiểu hoặc lớp được tham chiếu nhưng chưa được truyền trực tiếp trong danh sách đầu vào. Khi dự án chia mã nguồn thành nhiều package hoặc nhiều source root, cấu hình source path giúp javac tìm đúng tệp .java, biên dịch các phụ thuộc nguồn cần thiết và tạo bytecode vào đúng cấu trúc thư mục.

Source path đặc biệt hữu ích khi dự án có nhiều thư mục mã nguồn, mã được sinh tự động, hoặc khi muốn tách mã nguồn khỏi các thư viện đã biên dịch. Cấu hình sai thường dẫn tới lỗi như package does not exist, cannot find symbol hoặc file not found dù tệp nguồn vẫn tồn tại trên máy.

## 1. Source path là gì?

Trong Java, một lớp thường được khai báo trong package. Ví dụ:

~~~java
package com.acme.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Nếu package là com.acme.model, tệp nguồn thường được đặt dưới một thư mục gốc theo cấu trúc:

~~~text
src/main/java/
└── com/
    └── acme/
        └── model/
            └── Customer.java
~~~

Thư mục src/main/java là source root. Đường dẫn tương đối bên dưới source root phản ánh tên package: com/acme/model tương ứng với package com.acme.model.

Khi một lớp khác tham chiếu Customer, javac cần tìm được tệp nguồn hoặc bytecode của lớp đó. Source path chỉ định các source root để javac có thể tìm những tệp .java cần thiết.

Ví dụ, nếu Main.java import com.acme.model.Customer, javac có thể tìm tệp nguồn tại:

~~~text
src/main/java/com/acme/model/Customer.java
~~~

Điểm quan trọng là source path thường trỏ tới thư mục gốc chứa các package, không trỏ thẳng vào thư mục package cuối cùng. Nếu source root là src/main/java, javac tự nối phần package path com/acme/model để tìm Customer.java.

## 2. Phân biệt source path, classpath và thư mục đầu ra

Ba khái niệm thường xuất hiện cùng nhau nhưng giải quyết ba việc khác nhau:

| Tùy chọn | Vai trò |
|---|---|
| -sourcepath | Tìm các tệp mã nguồn .java cần thiết để biên dịch. |
| -classpath hoặc -cp | Tìm các lớp đã biên dịch, JAR và thư viện mà mã nguồn phụ thuộc. |
| -d | Chọn thư mục đích để ghi các tệp .class được biên dịch. |

Ví dụ:

~~~bash
javac -sourcepath src/main/java -classpath lib/api.jar -d out src/main/java/com/acme/app/Main.java
~~~

Trong lệnh này:

- javac nhận Main.java là tệp nguồn đầu vào tường minh.
- -sourcepath src/main/java cho phép tìm thêm các tệp .java được Main tham chiếu.
- -classpath lib/api.jar cho phép tìm các lớp đã biên dịch trong thư viện api.jar.
- -d out ghi các tệp .class vào thư mục out theo cấu trúc package.

Source path không phải thư mục chứa các tệp .class đầu ra. Ngược lại, -d không cho javac biết nơi tìm mã nguồn đầu vào.

Nếu không chỉ định -sourcepath, javac mặc định tìm tệp nguồn và lớp người dùng trong user class path. Classpath mặc định thường là thư mục hiện tại, trừ khi được thay đổi bằng tùy chọn hoặc biến môi trường tương ứng. Khi chỉ định source path rõ ràng, hãy xem nó là nơi tìm mã nguồn; classpath vẫn phục vụ việc tìm các lớp đã biên dịch và thư viện.

Nếu các tệp nguồn đã được liệt kê tường minh trên command line, javac không cần tìm lại chính các tệp đó qua source path. Source path vẫn hữu ích để tìm các lớp nguồn mà những tệp đầu vào này tham chiếu tới.

## 3. Cấu trúc dự án với nhiều source root

Một dự án có thể chia mã nguồn thành nhiều thư mục, chẳng hạn mã chính và mã được sinh tự động:

~~~text
source-path-demo/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/acme/app/Main.java
│   └── generated/
│       └── java/
│           └── com/acme/generated/BuildInfo.java
├── src-model/
│   └── com/acme/model/Customer.java
└── out/
~~~

Mỗi source root là một điểm bắt đầu riêng. Trong ví dụ trên:

- src/main/java chứa package com.acme.app.
- src/generated/java chứa package com.acme.generated.
- src-model chứa package com.acme.model.

Khi Main sử dụng Customer và BuildInfo, javac phải tìm được cả ba source root. Có thể khai báo nhiều source root trong một giá trị -sourcepath.

Không nên đặt source path vào một thư mục con quá sâu. Nếu khai báo src/main/java/com/acme, javac sẽ tìm package tương đối từ thư mục đó; khi lớp khai báo package com.acme.model, cấu trúc tra cứu sẽ không còn khớp với source root dự định.

## 4. Ví dụ thực hành: biên dịch phụ thuộc từ nhiều source root

Tạo cấu trúc thư mục sau:

~~~text
source-path-demo/
├── src/main/java/com/acme/app/Main.java
├── src-model/com/acme/model/Customer.java
├── src-generated/com/acme/generated/BuildInfo.java
└── out/
~~~

Tệp src-model/com/acme/model/Customer.java:

~~~java
package com.acme.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Tệp src-generated/com/acme/generated/BuildInfo.java:

~~~java
package com.acme.generated;

public final class BuildInfo {
    public static final String VERSION = "2026.11";

    private BuildInfo() {
    }
}
~~~

Tệp src/main/java/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.generated.BuildInfo;
import com.acme.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Linh");

        System.out.println("Application: source-path-demo");
        System.out.println("Customer: " + customer.name());
        System.out.println("Build: " + BuildInfo.VERSION);
    }
}
~~~

Chạy các lệnh từ thư mục gốc source-path-demo.

Trên Linux hoặc macOS, dấu phân cách giữa các phần tử source path là dấu hai chấm:

~~~bash
mkdir -p out

javac -d out -sourcepath "src/main/java:src-model:src-generated" src/main/java/com/acme/app/Main.java

java -cp out com.acme.app.Main
~~~

Trên Windows PowerShell, dấu phân cách giữa các phần tử path là dấu chấm phẩy:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac -d out -sourcepath "src/main/java;src-model;src-generated" src/main/java/com/acme/app/Main.java

java -cp out com.acme.app.Main
~~~

Output chính xác của chương trình:

~~~text
Application: source-path-demo
Customer: Linh
Build: 2026.11
~~~

Trong ví dụ này, chỉ Main.java được truyền trực tiếp cho javac. Khi phân giải Customer và BuildInfo, trình biên dịch tìm các tệp nguồn tương ứng qua những source root đã khai báo. Các lớp nguồn được tìm thấy và biên dịch vào out.

Sau khi biên dịch, cấu trúc đầu ra sẽ có dạng:

~~~text
out/
└── com/
    └── acme/
        ├── app/Main.class
        ├── generated/BuildInfo.class
        └── model/Customer.class
~~~

Lệnh java dùng out làm classpath root và tên lớp đầy đủ com.acme.app.Main để chạy ứng dụng.

Ví dụ này minh họa việc javac tìm và biên dịch nguồn phụ thuộc. Với dự án thực tế, có thể chọn truyền tất cả tệp nguồn tường minh hoặc để javac tìm nguồn phụ thuộc qua source path. Việc liệt kê tường minh thường dễ kiểm soát đầu vào build hơn khi dự án có quy trình build lớn.

## 5. Cú pháp và cách truyền -sourcepath

Cú pháp cơ bản:

~~~bash
javac -sourcepath <source-path> <source-files>
~~~

Có thể dùng dạng viết dài:

~~~bash
javac --source-path <source-path> <source-files>
~~~

Giá trị source path là một hoặc nhiều thư mục được ngăn cách bằng dấu phân cách path của hệ điều hành.

| Hệ điều hành | Dấu phân cách nhiều thư mục |
|---|---|
| Windows | Dấu chấm phẩy ; |
| Linux | Dấu hai chấm : |
| macOS | Dấu hai chấm : |

Ví dụ trên Windows:

~~~powershell
javac -sourcepath "src/main/java;src/generated/java" -d out src/main/java/com/acme/app/Main.java
~~~

Ví dụ trên Linux/macOS:

~~~bash
javac -sourcepath "src/main/java:src/generated/java" -d out src/main/java/com/acme/app/Main.java
~~~

Đặt giá trị trong dấu nháy khi đường dẫn có khoảng trắng hoặc chứa ký tự có ý nghĩa đặc biệt với shell. Dấu nháy giúp shell truyền toàn bộ danh sách source path thành một đối số cho javac.

Không nhầm dấu phân cách giữa các thư mục với dấu phân cách giữa các thành phần package. Package com.acme.model được ánh xạ thành các thư mục com/acme/model trên hệ thống tệp; dấu chấm trong tên package không phải dấu phân cách danh sách source root.

## 6. Đường dẫn tương đối, tuyệt đối và thư mục làm việc

Đường dẫn tương đối được phân giải dựa trên thư mục làm việc hiện tại của tiến trình javac. Nó không nhất thiết dựa trên vị trí của tệp Java hoặc vị trí file build.

Ví dụ, với cấu trúc:

~~~text
project/
├── src/
│   └── com/example/Main.java
└── out/
~~~

Nếu terminal đang ở project, có thể dùng:

~~~bash
javac -sourcepath src -d out src/com/example/Main.java
~~~

Nếu terminal đang ở thư mục cha của project, phải điều chỉnh đường dẫn:

~~~bash
javac -sourcepath project/src -d project/out project/src/com/example/Main.java
~~~

Có thể dùng đường dẫn tuyệt đối để giảm phụ thuộc vào working directory, đặc biệt trong script CI. Tuy nhiên, đường dẫn tuyệt đối cố định theo máy cá nhân thường làm dự án khó chia sẻ. Nên dùng đường dẫn tương đối từ project root trong cấu hình build, hoặc tạo đường dẫn từ biến gốc dự án.

Trên Windows, đường dẫn có thể chứa khoảng trắng, ví dụ C:/Users/Dev User/Projects/demo/src. Khi truyền qua PowerShell hoặc Command Prompt, hãy đặt đường dẫn đó trong dấu nháy kép.

Trên Linux/macOS, hệ thống tệp thường phân biệt chữ hoa và chữ thường. Package com.acme và com.Acme có thể dẫn tới hai đường dẫn khác nhau. Trên Windows, hành vi phân biệt hoa thường của hệ thống tệp thường khác; vì vậy hãy giữ tên package và tên thư mục nhất quán để tránh lỗi chỉ xuất hiện trên CI Linux.

## 7. Source path và package phải khớp nhau

Với khai báo:

~~~java
package com.example.service;
~~~

Tệp nguồn thường nằm tại:

~~~text
<source-root>/com/example/service/Service.java
~~~

Nếu source root là src/main/java, đường dẫn đầy đủ thường là:

~~~text
src/main/java/com/example/service/Service.java
~~~

Nếu đặt source root thành src/main/java/com/example/service, javac sẽ coi thư mục đó là điểm bắt đầu tìm package. Khi một lớp khác tham chiếu package com.example.service, đường dẫn tra cứu có thể bị lặp thêm các thành phần package và không tìm thấy tệp.

Một lỗi khác là package khai báo trong tệp không khớp cấu trúc thư mục. Hãy kiểm tra cả hai: dòng package trong mã nguồn và đường dẫn tương đối từ source root. Tên tệp của lớp public cấp cao nhất cũng phải phù hợp với tên lớp, ví dụ lớp public Service cần nằm trong Service.java.

Source root không bắt buộc luôn có tên là src/main/java. Đó chỉ là quy ước phổ biến. Dự án nhỏ có thể dùng src; dự án cũ có thể dùng source; dự án có code generation có thể thêm generated-sources. Điều quan trọng là source path trỏ tới thư mục ngay phía trên cấu trúc package.

## 8. Khi nào javac tự tìm và biên dịch tệp nguồn?

Có hai cách cung cấp đầu vào cho javac:

1. **Nguồn tường minh:** liệt kê trực tiếp các tệp .java cần biên dịch.
2. **Nguồn được tìm gián tiếp:** javac phát hiện mã nguồn của kiểu được tham chiếu nhưng chưa có bytecode phù hợp, rồi tìm tệp nguồn qua source path.

Ví dụ chỉ định một tệp:

~~~bash
javac -sourcepath src -d out src/com/example/Main.java
~~~

Nếu Main tham chiếu com.example.model.Customer và tệp Customer.java nằm trong source root src, javac có thể tìm và biên dịch nguồn phụ thuộc đó.

Có thể chỉ định tất cả nguồn tường minh:

~~~bash
javac -d out src/com/example/Main.java src/com/example/model/Customer.java
~~~

Trong trường hợp này, javac không cần tự tìm Customer.java qua source path vì tệp đã được truyền trực tiếp.

Đối với dự án lớn, build tool thường quản lý danh sách nguồn và dependency. Lệnh javac thủ công hữu ích để hiểu cơ chế, thử một module nhỏ hoặc chẩn đoán lỗi cấu hình. Không nên dựa vào việc trình biên dịch tự phát hiện mọi tệp nguồn khi dự án có code generation, nhiều source set hoặc quy tắc build phức tạp.

## 9. Source path không phải source version

Một nhầm lẫn thường gặp là coi -sourcepath và -source là cùng một loại tùy chọn.

- **-sourcepath / --source-path** chỉ nơi tìm tệp nguồn.
- **-source** chọn phiên bản cú pháp/ngôn ngữ Java mà trình biên dịch chấp nhận.
- **--release** chọn phiên bản Java mục tiêu, bao gồm ngôn ngữ, bytecode và API nền tảng tương ứng.
- **-target** chọn phiên bản bytecode đích nhưng không tự giới hạn API nền tảng; với build mới nên ưu tiên --release khi phù hợp.

Ví dụ, JDK mới có thể dùng source path src/main/java nhưng biên dịch theo Java 17:

~~~bash
javac --release 17 -sourcepath src/main/java -d out src/main/java/com/example/Main.java
~~~

Ở đây source path vẫn chỉ là vị trí mã nguồn. --release 17 điều khiển mức tương thích Java mục tiêu. Hai tùy chọn giải quyết hai vấn đề khác nhau và có thể dùng cùng nhau.

## 10. Source path trong dự án có module

Với dự án dùng Java Platform Module System, mỗi module thường có module-info.java và cây package riêng. Khi biên dịch nhiều module từ một cây nguồn, tùy chọn phù hợp là --module-source-path.

Ví dụ cấu trúc:

~~~text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/Customer.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Module descriptor của model:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

Module descriptor của app:

~~~java
module com.acme.app {
    requires com.acme.model;
}
~~~

Biên dịch từ thư mục dự án:

~~~bash
javac --module-source-path src -d out --module com.acme.app
~~~

Tùy chọn --module-source-path cho javac biết nơi tìm cây mã nguồn của các module. Đây là cơ chế dành cho module source tree, khác với source path của dự án classpath thông thường.

Khi dự án đã có các module được biên dịch hoặc JAR module sẵn có, --module-path dùng để tìm module đã biên dịch. Không nên nhầm --module-path với --module-source-path: một bên tìm module đã biên dịch, một bên tìm mã nguồn module.

## 11. Source path và annotation processing / mã nguồn sinh tự động

Một số dự án tạo mã Java trong quá trình build, chẳng hạn annotation processor sinh lớp metadata, mapper hoặc adapter. Cần phân biệt các đường dẫn liên quan:

| Tùy chọn | Mục đích |
|---|---|
| -sourcepath | Tìm mã nguồn Java đầu vào hoặc nguồn phụ thuộc. |
| -processorpath | Tìm các lớp annotation processor đã biên dịch. |
| -s | Chọn thư mục ghi các tệp .java được annotation processor sinh ra. |
| -d | Chọn thư mục ghi các tệp .class. |

Ví dụ lệnh build có annotation processor:

~~~bash
javac -cp lib/api.jar -processorpath tools/code-generator.jar -s generated-src -d out -sourcepath src/main/java src/main/java/com/example/Main.java
~~~

Trong lệnh này, generated-src là nơi ghi mã nguồn được sinh; nó không tự động đồng nghĩa với source path của các nguồn đầu vào. Annotation processing có vòng xử lý riêng, trong đó các nguồn được tạo có thể được biên dịch ở những vòng tiếp theo của cùng lần chạy javac.

Nếu dự án cần dùng mã nguồn đã sinh từ một lần build trước, hãy thêm thư mục đó vào source path như một source root phù hợp. Nếu mã được sinh ngay trong lần build hiện tại, hãy cấu hình processor path và thư mục -s đúng theo build tool hoặc lệnh javac.

Không đưa JAR chứa annotation processor vào source path với kỳ vọng javac sẽ tự chạy processor. Processor là mã thực thi được nạp theo cơ chế annotation processing; -processorpath hoặc cấu hình processor tương ứng mới chỉ định nơi tìm processor.

## 12. Những lỗi thường gặp và cách xử lý

| Thông báo hoặc hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| package ... does not exist | Source root sai, package path không khớp hoặc dependency chưa có trên classpath/module path. | Kiểm tra package declaration, source root và đường dẫn thư viện. |
| cannot find symbol | Lớp hoặc thành viên không được tìm thấy; có thể thiếu nguồn, thiếu classpath hoặc sai import. | Xác định symbol thuộc package nào; kiểm tra source path và classpath riêng. |
| file not found | Đường dẫn tệp đầu vào tương đối tính từ working directory khác dự kiến. | Kiểm tra thư mục làm việc và đường dẫn thực tế; thử đường dẫn tuyệt đối để chẩn đoán. |
| javac không tự biên dịch lớp phụ thuộc | Source path không chứa source root phù hợp hoặc có bytecode khác được tìm thấy trước. | Kiểm tra source path, classpath và vị trí lớp đã biên dịch. |
| Lớp biên dịch vào sai thư mục | Không dùng -d hoặc đang nhìn nhầm source root/đầu ra. | Dùng -d out và kiểm tra package path bên trong out. |
| Hoạt động trên Windows nhưng lỗi trên Linux | Khác biệt chữ hoa/chữ thường hoặc cách phân cách path. | Chuẩn hóa tên package/thư mục và dùng dấu phân cách theo nền tảng. |
| Đường dẫn có dấu cách không được nhận diện | Shell tách một đối số thành nhiều phần. | Đặt toàn bộ source path trong dấu nháy. |
| Mã nguồn sinh không được tìm thấy | Nhầm thư mục -s với source path hoặc chưa chạy bước code generation. | Kiểm tra thứ tự build, processor path và source root của mã được sinh. |

Khi cần xem javac đang tìm và nạp nguồn/lớp ở đâu, có thể bật verbose:

~~~bash
javac -verbose -sourcepath src/main/java -d out src/main/java/com/example/Main.java
~~~

Output verbose khá dài, nhưng có thể cho biết tệp nguồn và lớp nào được nạp. Đây là cách hữu ích để phân biệt lỗi do source path với lỗi do classpath.

Có thể xem các tùy chọn được hỗ trợ bởi phiên bản javac hiện tại:

~~~bash
javac --help
javac -version
~~~

## 13. Checklist cấu hình source path

Trước khi kết luận javac bị lỗi, hãy kiểm tra lần lượt:

1. Xác định thư mục làm việc hiện tại của lệnh build.
2. Xác định chính xác các source root của dự án.
3. Kiểm tra package declaration trong mỗi tệp và đường dẫn thư mục tương ứng.
4. Kiểm tra tệp nguồn có đúng tên và đúng chữ hoa/thường không.
5. Truyền đúng nhiều source root bằng dấu phân cách của hệ điều hành.
6. Phân biệt nguồn .java cần tìm với lớp .class/JAR cần tìm trên classpath.
7. Dùng -d để tách bytecode khỏi cây mã nguồn.
8. Nếu có module, dùng module-source-path và module-path đúng vai trò.
9. Nếu có annotation processor, kiểm tra processor path và thư mục -s riêng.
10. Dùng -verbose để xem javac thực sự tìm tệp ở đâu.
11. Chạy lại lệnh từ đúng project root hoặc chuẩn hóa đường dẫn trong script/CI.

Source path là một phần của cấu hình đầu vào khi biên dịch Java. Khi xác định đúng source root, giữ cấu trúc package nhất quán và tách biệt source path khỏi classpath, module path và output directory, javac có thể tìm đúng mã nguồn phụ thuộc và tạo bytecode theo cấu trúc dự án mong muốn.
