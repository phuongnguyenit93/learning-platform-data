# Mô-đun có tên, mô-đun tự động và mô-đun không tên trong Java (JPMS)

JPMS (Java Platform Module System) được đưa vào Java 9 và vẫn là một phần của nền tảng Java hiện hành. Module gom các package thành một đơn vị có tên, khai báo phụ thuộc và xác định package nào được cung cấp cho module khác. Nhờ đó, ứng dụng có thể mô tả đồ thị phụ thuộc rõ ràng và giới hạn truy cập vào phần triển khai nội bộ.

Ba dạng cần phân biệt là **named module được khai báo tường minh**, **automatic module** và **unnamed module**. Dạng module mà một JAR tham gia phụ thuộc vào vị trí đặt JAR: module path hay classpath.

## 1. So sánh ba dạng module

| Dạng | Khi nào được tạo | Tên và descriptor | Khả năng đọc module khác | Khả năng truy cập package |
|---|---|---|---|---|
| Named module tường minh | Module có descriptor và được đặt trên module path hoặc trong runtime image | Có tên; khai báo trong module-info.java và được biên dịch thành module-info.class | Chỉ đọc các module được khai báo bằng requires và các quan hệ đọc được suy ra | Chỉ package được exports mới là API truy cập thông thường; opens cấp quyền reflection lúc chạy |
| Automatic module | JAR không có module descriptor được đặt trên module path | Có tên tự động; lấy từ Automatic-Module-Name trong manifest hoặc suy ra từ tên JAR | Đọc tất cả module quan sát được trong cấu hình, kể cả unnamed module | Tự động exports và opens tất cả package |
| Unnamed module | Các lớp và JAR được nạp từ classpath | Không có tên và không có module descriptor | Đọc tất cả module quan sát được | Tự động exports và opens tất cả package thuộc module đó |

Một JAR không có module-info.class trên **module path** trở thành automatic module. Cùng JAR đó trên **classpath** thuộc unnamed module. Một modular JAR có module-info.class khi được đặt trên classpath cũng được xử lý như nội dung classpath; descriptor không tham gia vào đồ thị module trong lần chạy đó.

Các dạng này đều thuộc mô hình JPMS hiện hành. Automatic module hỗ trợ chuyển đổi từng bước sang module path; unnamed module duy trì khả năng chạy ứng dụng và thư viện qua classpath.

## 2. Named module được khai báo tường minh

Named module tường minh có descriptor tên là module-info.java ở thư mục gốc của module nguồn. Descriptor khai báo tên module, phụ thuộc và ranh giới package. Khi biên dịch, descriptor trở thành module-info.class trong module đã biên dịch hoặc modular JAR.

### Cấu trúc ví dụ

Ví dụ có hai module: module thư viện cung cấp API Greeting và module ứng dụng sử dụng API đó.

~~~text
src/
├── com.example.greeter/
│   ├── module-info.java
│   └── com/example/greeter/Greeting.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Descriptor của module thư viện:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Dòng exports công bố package com.example.greeter cho module khác. Các package không được export vẫn thuộc phần triển khai nội bộ.

Lớp API:

~~~java
package com.example.greeter;

public class Greeting {
    public static String message() {
        return "Hello from a named module";
    }
}
~~~

Descriptor của ứng dụng:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

Dòng requires tạo quan hệ đọc từ com.example.app đến com.example.greeter. Ứng dụng có thể dùng các kiểu public trong package được module thư viện export.

Lớp chạy ứng dụng:

~~~java
package com.example.app;

import com.example.greeter.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Biên dịch cả hai module từ thư mục chứa src:

~~~bash
javac -d out --module-source-path src -m com.example.greeter,com.example.app
~~~

Chạy module ứng dụng:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả stdout:

~~~text
Hello from a named module
~~~

Ví dụ dùng cú pháp JPMS ổn định từ Java 9 và chạy được trên Java 17 trở lên. Module path trỏ đến thư mục out chứa các module đã biên dịch; tùy chọn -m chỉ rõ module và lớp main.

### Các directive quan trọng trong module-info.java

- **requires module.name**: khai báo phụ thuộc trực tiếp và cho phép module hiện tại đọc module được nêu tên. Mọi module thông thường đều có phụ thuộc ngầm định vào java.base.
- **requires transitive module.name**: ngoài việc đọc module phụ thuộc, module hiện tại truyền quan hệ đọc đó cho module khác phụ thuộc vào mình. Dùng khi kiểu trong API công khai của module hiện tại phụ thuộc vào kiểu của module kia.
- **requires static module.name**: phụ thuộc cần có lúc biên dịch nhưng có thể không cần hiện diện lúc chạy. Chỉ dùng khi thiết kế thực sự cho phép dependency đó vắng mặt ở runtime.
- **exports package.name**: công bố package cho các module đọc module hiện tại. Có thể giới hạn người nhận bằng exports package.name to module.a, module.b.
- **opens package.name**: mở package cho truy cập reflection lúc chạy. Có thể dùng opens package.name to framework.module để giới hạn framework được phép truy cập sâu.
- **open module module.name**: mở tất cả package của module cho reflection lúc chạy. Điều này không thay thế exports và không tự làm package trở thành API có thể import khi biên dịch.
- **uses service.Type**: khai báo module sử dụng một service thông qua ServiceLoader.
- **provides service.Type with implementation.Type**: khai báo implementation cung cấp cho service đó.

### exports và opens khác nhau thế nào?

exports phục vụ truy cập API thông thường. Khi module khác đọc module hiện tại, các kiểu public và protected trong package được export có thể được truy cập theo quy tắc Java.

opens phục vụ reflection lúc chạy. Nó cho phép framework hoặc thư viện truy cập sâu vào kiểu và thành viên trong package, kể cả thành viên không public, theo quyền truy cập reflection của JPMS. opens không cho phép mã nguồn module khác import package đó như một API thông thường.

Không nên export hoặc open toàn bộ package chỉ để làm lỗi truy cập biến mất. Hãy công bố API cần thiết và mở đúng package cho framework thực sự cần reflection.

## 3. Automatic module

Automatic module được tạo khi một JAR không có module descriptor được đặt trên module path. Nó là **named module** trong đồ thị JPMS, vì vậy module khác có thể viết requires để phụ thuộc vào nó.

### Cách đặt tên

Tên module được xác định theo thứ tự:

1. Nếu manifest của JAR có thuộc tính Automatic-Module-Name, giá trị đó được dùng làm tên module.
2. Nếu không có thuộc tính này, tên module được suy ra từ tên file JAR theo quy tắc đặt tên automatic module.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
~~~

Nếu JAR trên module path có tên module com.example.legacy, một named module tường minh có thể khai báo:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

JAR phải nằm trên module path để được nhận diện là automatic module. Nếu đặt trên classpath, nó thuộc unnamed module và tên Automatic-Module-Name không tạo ra một module riêng trong đồ thị JPMS.

### Quyền đọc và package

Automatic module có ba đặc điểm quan trọng:

- Nó đọc tất cả module quan sát được trong cấu hình, bao gồm cả unnamed module. Vì vậy, nó có thể đóng vai trò cầu nối khi một phần ứng dụng đã chuyển sang module path nhưng phần khác vẫn ở classpath.
- Nó tự động export tất cả package, nên module đọc nó có thể truy cập các API public theo quy tắc Java.
- Nó tự động open tất cả package cho reflection lúc chạy.

Automatic module vẫn chịu các quy tắc kiểm tra của module system, chẳng hạn các xung đột package trong đồ thị module. Việc tự động export và open mọi package khiến ranh giới đóng gói của nó rộng hơn named module tường minh.

### Khi nào dùng?

Automatic module hữu ích khi một dependency hiện chưa cung cấp module descriptor nhưng ứng dụng cần đặt dependency đó trên module path. Đây là cách chuyển đổi từng bước mà không phải modular hóa mọi thư viện cùng lúc.

Nếu bạn phát triển thư viện, nên công bố Automatic-Module-Name ổn định để người dùng module path có thể phụ thuộc vào một tên rõ ràng. Khi thư viện chuyển sang named module tường minh, tên module và các package được export có thể được tác giả điều chỉnh; vì vậy không nên coi hành vi export toàn bộ của automatic module là hợp đồng API lâu dài. Đặc biệt, hãy cân nhắc kỹ trước khi dùng requires transitive với automatic module.

Có thể kiểm tra descriptor hoặc tên module mà JDK nhận diện bằng lệnh:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

## 4. Unnamed module

Unnamed module là module mà JVM tạo cho các lớp được nạp từ classpath. Nó không có tên để module khác tham chiếu trong directive requires và không cần module-info.java.

Trong cách chạy ứng dụng thông thường, các lớp trên classpath được nạp bởi cùng một class loader thuộc unnamed module của class loader đó. Mỗi class loader có unnamed module riêng. Vì vậy, không nên hiểu unnamed module là một tên chung có thể dùng trong module-info.java.

### Quyền đọc và package

Unnamed module:

- Đọc tất cả module quan sát được trong cấu hình.
- Export tất cả package thuộc unnamed module.
- Open tất cả package thuộc unnamed module cho reflection lúc chạy.

Điểm quan trọng là **chiều truy cập không đối xứng**: mã trong unnamed module có thể đọc các named module và sử dụng package mà các named module export. Ngược lại, named module không thể khai báo requires để đọc unnamed module vì unnamed module không có tên. Theo mặc định, mã trong named module vì thế không nhìn thấy lớp chỉ có trên classpath.

Trong một bước chuyển đổi tạm thời, có thể bổ sung quan hệ đọc lúc chạy bằng tùy chọn:

~~~bash
java --add-reads com.example.app=ALL-UNNAMED --module-path mods -m com.example.app/com.example.app.Main
~~~

Tùy chọn này cho named module com.example.app đọc các lớp thuộc unnamed module. Chỉ nên dùng khi cần tích hợp trong giai đoạn chuyển đổi; cách thiết kế rõ ràng hơn là đưa dependency phù hợp lên module path để nó trở thành named module hoặc automatic module.

### Khi nào dùng?

Classpath và unnamed module vẫn phù hợp với ứng dụng chưa cần ranh giới module tường minh, công cụ chạy mã classpath và quá trình chuyển đổi dần một hệ thống lớn. Không cần thêm module-info.java chỉ để chương trình Java thông thường tiếp tục chạy.

## 5. Quan hệ giữa ba dạng module

| Module đang chạy mã | Có thể đọc named module tường minh | Có thể đọc automatic module | Có thể đọc unnamed module |
|---|---|---|---|
| Named module tường minh | Có, khi khai báo requires phù hợp | Có, khi khai báo requires bằng tên automatic module | Không theo mặc định; không thể khai báo requires cho unnamed module |
| Automatic module | Có, vì automatic module đọc mọi module quan sát được | Có, vì nó đọc mọi module quan sát được | Có |
| Unnamed module | Có, vì nó đọc mọi module quan sát được | Có | Có |

Khả năng đọc module không đồng nghĩa với quyền truy cập mọi kiểu trong module đó. Để truy cập API thông thường, module hiện tại phải đọc module đích và package đích phải được export. Để framework truy cập sâu bằng reflection, package đích phải được open cho module thực hiện reflection.

Có thể ghi nhớ ba quy tắc:

1. **requires tạo quan hệ đọc** giữa các named module.
2. **exports xác định API package** có thể được module khác sử dụng bình thường.
3. **opens cấp quyền reflection lúc chạy** cho package được mở.

## 6. Chọn dạng module cho dự án

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Ứng dụng hoặc thư viện mới cần ranh giới phụ thuộc rõ ràng | Named module tường minh | Chủ động khai báo dependency, API và package nội bộ |
| Dependency là JAR chưa có module descriptor nhưng cần đặt trên module path | Automatic module | Có thể tham gia đồ thị module trong khi chờ dependency được modular hóa |
| Ứng dụng hoặc thư viện tiếp tục chạy trên classpath | Unnamed module | Giữ cách nạp classpath và khả năng tương thích hiện có |
| Chuyển đổi hệ thống lớn theo từng phần | Kết hợp các dạng module | Có thể đưa một số thành phần lên module path trước, sau đó thay automatic module bằng descriptor tường minh |

Một số nguyên tắc thực hành:

- Với module mới, khai báo dependency trực tiếp và chỉ export package thực sự là API.
- Dùng requires transitive khi dependency xuất hiện trong API công khai và người dùng module hiện tại cần đọc dependency đó.
- Chỉ dùng opens cho package mà framework cần reflection; ưu tiên mở có giới hạn bằng opens ... to ....
- Với thư viện chưa modular, kiểm tra tên module mà JAR cung cấp trước khi viết requires.
- Nếu bạn là tác giả thư viện, khai báo Automatic-Module-Name ổn định để hỗ trợ người dùng chuyển đổi.
- Không cần chuyển toàn bộ dự án sang JPMS trong một lần. Classpath vẫn là cách chạy hợp lệ; module path mang lại lợi ích khi cần quản lý phụ thuộc và đóng gói rõ ràng.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Module not found | JAR hoặc module chưa có trên module path, hoặc tên trong requires không khớp tên module thực tế | Kiểm tra module path và dùng jar --describe-module để xem tên module |
| Package is not visible hoặc package không được truy cập | Module hiện tại chưa đọc module đích, hoặc package đích chưa export | Bổ sung requires và kiểm tra exports trong module-info.java |
| Framework không truy cập được field hoặc constructor khi reflection | Package chưa được mở cho module framework | Dùng opens package to framework.module với đúng package và module |
| Named module không tìm thấy lớp chỉ nằm trên classpath | Named module không đọc unnamed module theo mặc định | Đưa dependency lên module path hoặc dùng --add-reads ...=ALL-UNNAMED trong giai đoạn chuyển đổi |
| Split package hoặc xung đột package | Cùng package xuất hiện trong nhiều named module được giải quyết vào cùng cấu hình | Gộp package về một module hoặc điều chỉnh ranh giới module |

## 8. Tài liệu tham khảo

- [Dev.java — Modules](https://dev.java/learn/organizing/modules/): tổng quan JPMS, module path, classpath, dịch vụ và cách xây dựng module.
- [Dev.java — Automatic Modules](https://dev.java/learn/organizing/modules/automatic-module/): quy tắc tên, khả năng đọc, exports và opens của automatic module.
- [Dev.java — The Unnamed Module](https://dev.java/learn/organizing/modules/unnamed-module/): hành vi của mã trên classpath và chiều đọc giữa unnamed module với named module.
- [Java Language Specification, Java SE 26 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html): đặc tả chính thức về module declaration, dependencies, exports, opens và unnamed modules.
