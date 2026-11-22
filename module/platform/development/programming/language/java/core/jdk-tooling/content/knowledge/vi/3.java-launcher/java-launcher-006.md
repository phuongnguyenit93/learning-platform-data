# Module path runtime

## 1. Module path runtime là gì?

Từ Java 9, Java Platform Module System (JPMS) cho phép ứng dụng được tổ chức thành các module có tên, có mô tả phụ thuộc và quy tắc truy cập rõ ràng. Khi khởi chạy một ứng dụng modular, Java launcher phải tìm các module cần thiết, giải quyết đồ thị phụ thuộc, kiểm tra các quy tắc module và sau đó mới gọi phương thức main của ứng dụng.

**Module path** là nơi Java launcher tìm các module ở thời điểm chạy. Tùy cách đóng gói, một module trên module path có thể là:

- Một modular JAR có file **module-info.class**.
- Một thư mục module đã biên dịch dạng exploded module, có **module-info.class** ở thư mục gốc.
- Một JAR không có module descriptor, được xem như automatic module khi đặt trên module path.

Module path thường là một thư mục chứa các modular JAR hoặc các thư mục module đã biên dịch. Nó có thể gồm nhiều thư mục được phân tách bằng ký tự phân cách đường dẫn của hệ điều hành. Java launcher tìm module trong các vị trí này theo tên module được khai báo, sau đó dựng module graph cho tiến trình.

Ví dụ đơn giản:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Trong lệnh này:

- **--module-path mods** (viết ngắn là **-p mods**) chỉ định thư mục chứa các module.
- **--module** (viết ngắn là **-m**) chọn module gốc cần khởi chạy và lớp main.
- **com.example.app** là tên module, không nhất thiết trùng tên file JAR.
- **com.example.app.Main** là tên đầy đủ của lớp có phương thức main.

Module path thuộc giai đoạn khởi chạy và nạp module ở runtime. Nó liên quan chặt chẽ đến module descriptor, nhưng cần phân biệt với cấu hình module path lúc biên dịch bằng javac.

## 2. Phân biệt module path và classpath

Cả module path và classpath đều giúp JVM tìm bytecode, nhưng chúng có mô hình truy cập khác nhau.

| Tiêu chí | Module path | Classpath |
|---|---|---|
| Đơn vị tổ chức | Module có tên; có thể có module descriptor | Các lớp và JAR nằm trong unnamed module |
| Khai báo phụ thuộc | Dùng **requires** trong module descriptor | Thường dựa trên classpath và cấu hình build |
| Công khai package | Module chọn package bằng **exports** | Các package trên classpath không có quy tắc exports của JPMS |
| Quyền truy cập phản chiếu sâu | Có quy tắc encapsulation; thường cần **opens** hoặc tùy chọn mở package | Các lớp trong unnamed module có mô hình truy cập khác và ít ràng buộc module hơn |
| Cách chọn lớp chạy | **-m module/class** | **-cp path package.Class** hoặc **-classpath** |

Một ứng dụng modular thường khởi chạy theo dạng:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Một ứng dụng classpath truyền thống thường khởi chạy theo dạng:

~~~bash
java -cp "classes:lib/*" com.example.app.Main
~~~

Dấu hai chấm trong ví dụ classpath là dấu phân cách trên Linux/macOS; Windows dùng dấu chấm phẩy. Module path cũng dùng dấu phân cách theo hệ điều hành. Hai cách khởi chạy không thể hoán đổi tùy ý: đặt một JAR lên classpath không làm nó tự trở thành named module có descriptor.

Nếu một JAR thư viện cũ không có module descriptor được đặt trên module path, JVM có thể coi nó là **automatic module**. Đây là cầu nối hỗ trợ chuyển đổi ứng dụng cũ sang JPMS. Nếu JAR nằm trên classpath, các lớp của nó thuộc unnamed module. Không nên nhầm hai trường hợp này.

Với named module, module khác chỉ đọc được module đó theo quan hệ readability và chỉ truy cập được các public type trong package được export. Đây là điểm khác biệt cốt lõi so với cách phụ thuộc classpath truyền thống.

## 3. Module descriptor quyết định điều gì ở runtime?

Một module khai báo tên và các quy tắc phụ thuộc trong file **module-info.java**. Sau khi biên dịch, descriptor trở thành **module-info.class** và được đặt ở gốc modular JAR hoặc gốc thư mục module.

Ví dụ:

~~~java
module com.example.orders {
    requires com.example.customer;
    exports com.example.orders.api;
}
~~~

Các chỉ thị thường gặp:

- **requires**: khai báo module phụ thuộc. Khi khởi chạy, module được yêu cầu phải được tìm thấy và đưa vào module graph, trừ những trường hợp đặc biệt như requires static.
- **requires transitive**: ngoài việc module hiện tại đọc module phụ thuộc, các module đọc module hiện tại cũng được truyền khả năng đọc module đó.
- **exports**: công khai một package cho các module khác truy cập các public type trong package đó.
- **exports package to module**: chỉ export package cho các module được liệt kê.
- **opens**: cho phép truy cập phản chiếu sâu vào các kiểu trong package; có thể mở cho tất cả module hoặc giới hạn theo module.
- **opens package to module**: mở package có chọn lọc cho các module cần reflection.
- **uses** và **provides ... with ...**: khai báo phía tiêu thụ và cung cấp dịch vụ theo cơ chế ServiceLoader.

Một module có thể đọc một module khác mà không được phép truy cập mọi package của module đó. **Readability** và **exports** là hai điều kiện khác nhau: requires tạo quan hệ đọc, còn exports xác định package nào được công khai.

Ví dụ, nếu module A có **requires B** nhưng module B không export package mà A muốn dùng, A vẫn không thể truy cập các public type trong package đó. Ngược lại, export package không tự tạo quan hệ requires cho module tiêu thụ.

Khi Java launcher giải quyết module graph, nó kiểm tra các module gốc và những phụ thuộc được khai báo. Các module cần thiết phải có mặt và không được vi phạm các quy tắc của hệ thống module. Lỗi tìm module, tên module, phụ thuộc hoặc xung đột thường xuất hiện trước khi phương thức main chạy.

## 4. Những dạng module có thể đặt trên module path

### Explicit named module

Đây là module có module descriptor rõ ràng. Modular JAR chứa **module-info.class**; exploded module có file này trong thư mục gốc.

Tên module lấy từ descriptor. Tên file JAR chỉ là tên artifact và có thể khác tên module. Vì vậy, khi viết lệnh **-m**, hãy dùng tên module, không tự suy ra từ tên file.

### Automatic module

Một JAR không có module descriptor nhưng được đặt trên module path có thể được xem là automatic module. Tên module thường được xác định theo thuộc tính **Automatic-Module-Name** trong manifest; nếu không có, tên có thể được suy ra từ tên file JAR theo quy tắc của JPMS.

Automatic module giúp thư viện cũ tham gia module graph trong giai đoạn chuyển đổi. Nó có các quy tắc nới lỏng hơn explicit module, chẳng hạn đọc các module quan sát được và export các package của nó. Tuy nhiên, tên suy ra từ tên file có thể thay đổi khi đổi cách đặt tên artifact. Với thư viện do nhóm phát triển và cần tên module ổn định, nên cung cấp module descriptor hoặc thuộc tính Automatic-Module-Name thích hợp.

### Unnamed module

Các lớp và JAR trên classpath thuộc unnamed module của class loader tương ứng. Unnamed module không có tên module cố định trong descriptor. Đây là mô hình tương thích cho ứng dụng chưa chuyển sang JPMS.

Named module không tự động đọc unnamed module. Khi tích hợp thư viện classpath vào ứng dụng modular, có thể cần cấu hình bổ sung như **--add-reads module.name=ALL-UNNAMED**; chỉ dùng khi đã hiểu ranh giới phụ thuộc và có kế hoạch loại bỏ cấu hình tương thích nếu có thể.

### Exploded module và modular JAR

Trong quá trình phát triển, thư mục output sau khi biên dịch có thể được dùng trực tiếp làm exploded module. Khi đóng gói, module có thể được tạo thành modular JAR. Cả hai đều có thể được tìm thấy qua module path nếu cấu trúc và descriptor hợp lệ.

Không nên đặt nhiều bản phát hành khác nhau của cùng một module name vào cùng module path. Điều đó khiến việc chọn phiên bản phụ thuộc vào cách tìm kiếm và thứ tự đường dẫn, gây khó khăn cho việc tái lập runtime. Hãy giữ một bản module có tên xác định trong cấu hình chạy.

## 5. Ví dụ ứng dụng gồm hai module

Ví dụ sau có module **com.example.greeter** cung cấp API chào hỏi và module **com.example.hello** sử dụng API đó. Cấu trúc thư mục mã nguồn:

~~~text
src/
  com.example.greeter/
    module-info.java
    com/example/greeter/api/Greeting.java
  com.example.hello/
    module-info.java
    com/example/hello/Main.java
~~~

### Module cung cấp API

File **src/com.example.greeter/module-info.java**:

~~~java
module com.example.greeter {
    exports com.example.greeter.api;
}
~~~

File **src/com.example.greeter/com/example/greeter/api/Greeting.java**:

~~~java
package com.example.greeter.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from module path";
    }
}
~~~

Module export package **com.example.greeter.api**, nhờ vậy module khác có thể đọc public type Greeting trong package này.

### Module ứng dụng

File **src/com.example.hello/module-info.java**:

~~~java
module com.example.hello {
    requires com.example.greeter;
}
~~~

File **src/com.example.hello/com/example/hello/Main.java**:

~~~java
package com.example.hello;

import com.example.greeter.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Module ứng dụng khai báo **requires com.example.greeter**. Nếu bỏ khai báo này, module không có quan hệ readability cần thiết để biên dịch hoặc truy cập API của module greeter theo quy tắc JPMS.

### Biên dịch thành exploded modules

Đứng tại thư mục dự án, tạo thư mục output **mods**, sau đó chạy:

~~~bash
javac -d mods --module-source-path src -m com.example.greeter,com.example.hello
~~~

Tùy hệ điều hành, có thể tạo thư mục **mods** trước bằng lệnh tạo thư mục tương ứng. Tùy chọn **--module-source-path src** cho javac biết nơi chứa cây source theo tên module; **-m** chọn hai module cần biên dịch. Kết quả có dạng:

~~~text
mods/
  com.example.greeter/
    module-info.class
    com/example/greeter/api/Greeting.class
  com.example.hello/
    module-info.class
    com/example/hello/Main.class
~~~

### Khởi chạy bằng module path

Chạy lệnh:

~~~bash
java --module-path mods --module com.example.hello/com.example.hello.Main
~~~

Kết quả:

~~~text
Hello from module path
~~~

Khi chạy, Java launcher tìm module **com.example.hello** trong thư mục **mods**, đọc descriptor, phát hiện module này yêu cầu **com.example.greeter**, tìm module phụ thuộc, dựng module graph rồi gọi main class. Không cần chỉ định riêng JAR của greeter trong classpath vì cả hai module đều nằm trong module path.

### Đóng gói thành modular JAR

Có thể đóng gói từng thư mục module thành JAR:

~~~bash
jar --create --file mlib/com.example.greeter.jar -C mods/com.example.greeter .
jar --create --file mlib/com.example.hello.jar -C mods/com.example.hello .
~~~

Thư mục **mlib** cần được tạo trước. Các JAR giữ nguyên module descriptor đã biên dịch. Sau đó chạy:

~~~bash
java --module-path mlib --module com.example.hello/com.example.hello.Main
~~~

Kết quả vẫn là:

~~~text
Hello from module path
~~~

Ví dụ cho thấy runtime module path có thể trỏ đến thư mục chứa exploded modules hoặc thư mục chứa modular JAR. Cấu trúc source và cách đóng gói có thể thay đổi, nhưng module name, descriptor, quan hệ requires và exports phải nhất quán.

## 6. Cú pháp Java launcher thường dùng

Cú pháp khởi chạy một module:

~~~bash
java --module-path <module-path> --module <module-name>[/<main-class>] [application-args...]
~~~

Các tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
|---|---|
| **--module-path**, **-p** | Chỉ định các vị trí chứa module để runtime tìm kiếm. |
| **--module**, **-m** | Chọn module gốc cần chạy, có thể chỉ rõ lớp main sau dấu gạch chéo. |
| **--add-modules** | Thêm các module vào tập module gốc cần giải quyết, ngoài các module được chọn mặc định. |
| **--limit-modules** | Giới hạn tập module quan sát được khi giải quyết module graph. |
| **--show-module-resolution** | Hiển thị thông tin các module được giải quyết, hữu ích khi chẩn đoán. |
| **--list-modules** | Liệt kê các module có thể quan sát từ cấu hình launcher hiện tại. |
| **--add-reads** | Bổ sung quan hệ readability giữa module nguồn và module đích. |
| **--add-exports** | Export một package của module cho module đích ở runtime. |
| **--add-opens** | Mở package cho truy cập phản chiếu sâu ở runtime. |
| **--patch-module** | Bổ sung hoặc thay thế lớp/tài nguyên của một module trong một số tình huống kiểm thử hoặc tương thích. |

Các tùy chọn **--add-reads**, **--add-exports**, **--add-opens** và **--patch-module** là công cụ can thiệp vào module graph hoặc encapsulation. Chúng hữu ích trong migration, kiểm thử và xử lý thư viện cũ, nhưng không nên trở thành cấu hình mặc định để che giấu module descriptor thiếu hoặc phụ thuộc sai.

Có thể yêu cầu launcher in module resolution:

~~~bash
java --show-module-resolution --module-path mods --module com.example.hello/com.example.hello.Main
~~~

Hoặc liệt kê module:

~~~bash
java --module-path mods --list-modules
~~~

Để xem descriptor của một module đã đóng gói, có thể dùng công cụ jar:

~~~bash
jar --describe-module --file mlib/com.example.hello.jar
~~~

Kết quả mô tả tên module, các package và các chỉ thị phụ thuộc/công khai được công cụ nhận diện. Đây là cách kiểm tra artifact đã đóng gói có descriptor như mong đợi hay không.

## 7. Đường dẫn module trên từng hệ điều hành

Một module path có thể chứa nhiều thư mục. Ký tự phân cách các thành phần phụ thuộc hệ điều hành:

- Windows: dấu chấm phẩy **;**.
- Linux và macOS: dấu hai chấm **:**.

Ví dụ trên Linux/macOS:

~~~bash
java --module-path "mods:vendor-mods" --module com.example.hello/com.example.hello.Main
~~~

Ví dụ trên Windows:

~~~powershell
java --module-path "mods;vendor-mods" --module com.example.hello/com.example.hello.Main
~~~

Nếu đường dẫn chứa khoảng trắng, đặt toàn bộ giá trị module path trong dấu nháy phù hợp với shell. Module path chỉ tìm các module theo cấu trúc được hỗ trợ; không giả định rằng launcher tự quét đệ quy mọi thư mục con tùy ý. Hãy đặt modular JAR hoặc thư mục module ở vị trí mà module path trực tiếp tìm kiếm.

Khi ứng dụng chạy trong IDE, kiểm tra cấu hình Run/Debug có dùng module path và module chính xác hay không. IDE có thể tự tạo command line khác với lệnh chạy thủ công; nên xem command line thực tế khi kết quả giữa IDE và terminal không giống nhau.

Trong Gradle hoặc Maven, cấu hình module path runtime phụ thuộc cách plugin/build tool tạo runtime classpath/module path và cách ứng dụng được khởi chạy. Không nên giả định mọi task Java đều tự chuyển toàn bộ dependency sang module path chỉ vì dự án có một file module-info.java. Hãy kiểm tra cấu hình run/test, plugin và command line thực tế.

## 8. Readability, exports và reflection ở runtime

Ba khái niệm thường bị nhầm:

1. **Readability:** module hiện tại có quyền đọc module khác hay không. Quan hệ này thường được khai báo bằng requires.
2. **Exports:** package có được công khai để module khác truy cập public type hay không.
3. **Opens:** package có được mở cho reflection sâu, chẳng hạn framework cần truy cập thành viên không public hay không.

Ví dụ một thư viện có thể export package API nhưng không mở package implementation cho reflection sâu. Điều đó cho phép ứng dụng gọi API công khai mà vẫn giữ chi tiết triển khai được đóng gói.

Nếu framework báo lỗi **InaccessibleObjectException** khi dùng reflection, trước tiên xem package nào đang bị đóng và module nào cần truy cập. Một cấu hình runtime có thể dùng:

~~~bash
java --add-opens com.example.app/com.example.app.internal=ALL-UNNAMED --module-path mods --module com.example.app/com.example.app.Main
~~~

Ví dụ này mở package **com.example.app.internal** của module **com.example.app** cho unnamed module. Đây là cách tương thích cho thư viện trên classpath cần reflection sâu. Nếu đối tượng truy cập là một named module cụ thể, có thể chỉ định tên module đích thay cho **ALL-UNNAMED**.

**--add-exports** khác **--add-opens**. add-exports cho phép truy cập các public type trong package chưa export; add-opens cho phép reflection sâu vào package. Dùng sai tùy chọn có thể không giải quyết được lỗi. Cách bền vững thường là dùng API được export hoặc cập nhật thư viện để hỗ trợ module system đúng cách.

Không mở toàn bộ module hoặc package chỉ để làm ứng dụng chạy qua lỗi. Mỗi lần mở rộng quyền truy cập đều làm giảm mức encapsulation mà module system cung cấp.

## 9. Dịch vụ và module path

JPMS tích hợp với cơ chế Java ServiceLoader. Module tiêu thụ có thể khai báo:

~~~java
module com.example.app {
    uses com.example.spi.GreetingProvider;
}
~~~

Module cung cấp triển khai có thể khai báo:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.GreetingProvider
        with com.example.provider.DefaultGreetingProvider;
}
~~~

Khi sử dụng service, cần bảo đảm module SPI và module provider được đặt ở vị trí runtime có thể quan sát và được giải quyết vào module graph theo cấu hình chạy. Module tiêu thụ khai báo **uses**; module provider khai báo **provides ... with ...**. Chỉ đặt file JAR vào một thư mục bất kỳ không bảo đảm provider được phát hiện nếu JAR không nằm trong module path hoặc không được module resolution đưa vào graph.

Trong trường hợp cần ràng buộc provider service khi giải quyết module, launcher có tùy chọn **--bind-services**. Chỉ bật khi mô hình ứng dụng thực sự cần cơ chế service binding đó; hãy kiểm tra kết quả bằng **--show-module-resolution** và kiểm thử service discovery.

## 10. Các lỗi thường gặp khi chạy bằng module path

### Could not find or load main class / module

Nguyên nhân thường là module path sai, module không có trong thư mục được chỉ định, tên module trong lệnh không khớp descriptor hoặc cú pháp **-m** bị viết sai. Hãy kiểm tra vị trí artifact, tên module bằng **jar --describe-module** và command line thực tế.

### Module not found

Một module được khai báo bằng requires nhưng runtime không tìm thấy module tương ứng. Kiểm tra module path có chứa dependency đó không, tên module có đúng không và dependency có đúng định dạng modular JAR, exploded module hoặc automatic module hay không.

### Module does not read / package is not visible

Module sử dụng chưa khai báo requires hoặc package của module phụ thuộc chưa export. Kiểm tra module descriptor của cả hai phía. Không nên sửa bằng cách chuyển mọi JAR sang classpath nếu ứng dụng cần giữ mô hình module.

### Package is not exported

Module đã được tìm thấy và có thể đọc, nhưng package cần dùng chưa được export. Thêm exports có chọn lọc trong module descriptor của module sở hữu package nếu đó là API được thiết kế công khai. Tùy chọn --add-exports chỉ nên là giải pháp có chủ đích cho runtime đặc biệt.

### InaccessibleObjectException

Framework hoặc thư viện đang dùng reflection sâu vào package không được mở. Kiểm tra module và package được nêu trong exception. Cân nhắc cập nhật framework hoặc khai báo opens có giới hạn; nếu dùng --add-opens, mở đúng package cho đúng module đích.

### Lỗi duplicate module hoặc split package

Module path có thể chứa nhiều artifact khai báo cùng module name hoặc nhiều module có package xung đột. Kiểm tra dependency tree, loại bỏ phiên bản trùng và thống nhất phiên bản thư viện. Không dựa vào thứ tự thư mục để vô tình chọn một bản.

### Chạy được trong IDE nhưng lỗi ở terminal hoặc production

IDE, Gradle/Maven, script khởi chạy và container có thể dùng module path khác nhau. So sánh command line, biến môi trường, đường dẫn module path, danh sách module và các tùy chọn launcher. Kiểm tra cả phiên bản JDK runtime thực tế.

### Thiếu class dù JAR đã có trong thư mục lib

Một JAR có mặt trên ổ đĩa không đồng nghĩa nó đã nằm trên module path hoặc classpath. Xác định rõ dependency được đặt ở đâu và cách launcher nhận nó. Module path không tự động quét mọi thư mục lồng nhau.

## 11. Quy trình kiểm tra khi triển khai

Khi một ứng dụng modular không chạy đúng, kiểm tra theo thứ tự:

1. Xác nhận đúng JDK runtime bằng **java --version**.
2. Xem command line đầy đủ mà IDE, script hoặc service dùng để khởi chạy.
3. Xác nhận **--module-path** trỏ đến thư mục chứa đúng modular JAR hoặc exploded modules.
4. Xác nhận tên module gốc và main class trong tùy chọn **-m**.
5. Dùng **jar --describe-module** để kiểm tra descriptor của từng artifact quan trọng.
6. Dùng **--show-module-resolution** để xem module nào được tìm thấy và đưa vào graph.
7. Kiểm tra requires, exports, opens và các khai báo uses/provides.
8. Kiểm tra module name trùng, split package và phiên bản dependency.
9. Chạy lại bằng đúng cấu hình runtime của production, kể cả trong container nếu có.

Khi đóng gói để triển khai, hãy giữ module path có thể tái lập: ghi rõ các modular JAR, phiên bản dependency và cách tạo thư mục runtime. Tránh đưa các bản JAR trùng module name vào nhiều thư mục tìm kiếm. Không dùng một module path rộng chứa hàng trăm thư viện không liên quan nếu ứng dụng chỉ cần một tập module nhỏ.

## 12. Checklist trước khi bàn giao ứng dụng modular

- [ ] Module chính có module descriptor hợp lệ và tên module được xác định rõ.
- [ ] Tất cả module được requires đều có mặt trong module path runtime.
- [ ] Mỗi package cần dùng từ module khác đã được export phù hợp.
- [ ] Các package cần reflection sâu đã được opens có giới hạn hoặc thư viện đã hỗ trợ JPMS.
- [ ] Không có nhiều phiên bản cùng module name hoặc split package không chủ đích.
- [ ] Lệnh launcher dùng đúng --module-path và --module.
- [ ] Đã kiểm tra module resolution bằng --show-module-resolution khi cần.
- [ ] IDE, build tool, script và production dùng cấu hình module path tương thích.
- [ ] Runtime trong container hoặc máy chủ đã được kiểm thử với đúng tập module.
- [ ] Dependency và cách tạo module path được ghi lại để có thể tái lập.

Module path runtime giúp Java chạy ứng dụng theo một đồ thị module có tên, phụ thuộc và ranh giới truy cập rõ ràng. Khi descriptor, module path và lệnh launcher được cấu hình nhất quán, lỗi thiếu module hoặc truy cập package sẽ dễ xác định hơn, đồng thời ứng dụng giữ được tính đóng gói mà JPMS cung cấp.