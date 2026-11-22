# Named module trên module path

Trong Java Platform Module System (JPMS), **module path** là nơi trình biên dịch và JVM tìm các module có thể quan sát được. Một named module chỉ tham gia vào module graph khi Java tìm thấy module đó trên module path hoặc trong các nguồn module được cấu hình tương ứng. Module path vì vậy đóng vai trò quan trọng ở cả thời điểm biên dịch lẫn thời điểm chạy.

Khi chuyển từ classpath truyền thống sang JPMS, cần hiểu module path chứa những dạng module nào, Java phân giải dependency ra sao và cách chỉ định module ứng dụng cần khởi chạy.

## 1. Module path là gì?

Module path là một danh sách các vị trí mà Java dùng để tìm module. Tùy chọn thường dùng:

- **--module-path**: tên đầy đủ của tùy chọn.
- **-p**: dạng viết tắt của **--module-path**.

Ví dụ:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Trong ví dụ trên, thư mục **mods** là nơi JVM tìm module. Tùy chọn **--module** (hoặc **-m**) chọn module gốc và class main cần chạy.

Module path khác classpath ở mục tiêu và cách phân giải:

- Classpath là đường dẫn tìm class và JAR theo mô hình truyền thống.
- Module path là đường dẫn tìm module có tên, để Java đọc descriptor và xây dựng module graph.
- Named module phải khai báo dependency qua **requires**.
- Package được công khai qua ranh giới module phải được **exports** phù hợp.
- Module path cho phép Java kiểm tra một số vấn đề về dependency và ranh giới package trước hoặc trong lúc chạy.

Đặt một JAR vào module path không tự động làm cho mọi class bên trong trở thành API công khai. Java còn xét module descriptor và các directive của module đó.

## 2. Module path có thể chứa những gì?

Module path có thể cung cấp các dạng module sau:

**Modular JAR**

Đây là JAR có file **module-info.class** ở gốc. Descriptor chứa tên module, dependency và các quy tắc export/open. Khi được tìm thấy trên module path, JAR được nhận diện là named module theo descriptor.

**Exploded module**

Đây là module đã được giải nén thành thư mục. File **module-info.class** nằm ở gốc thư mục module, bên cạnh các package đã biên dịch. Dạng này thường xuất hiện trong thư mục output sau khi dùng javac.

**Automatic module**

Đây là JAR không có **module-info.class** nhưng được đặt trên module path. Java tạo tên module cho JAR, ưu tiên thuộc tính manifest **Automatic-Module-Name** nếu có, nếu không thì suy ra tên từ tên file. Automatic module giúp thư viện cũ tham gia module graph trong giai đoạn chuyển đổi.

Một thư mục module path thường chứa nhiều module:

~~~text
mods/
├── com.example.app/
│   ├── module-info.class
│   └── com/example/app/Main.class
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/Message.class
└── com.example.logging.jar
~~~

Trong ví dụ, hai thư mục đầu là exploded module; JAR cuối có thể là modular JAR hoặc automatic module tùy nội dung của nó.

## 3. Named module được tìm và phân giải như thế nào?

Module path cung cấp tập hợp module có thể quan sát được. Java không đơn giản nạp tất cả module tìm thấy trên đường dẫn. Trình phân giải bắt đầu từ các module gốc, sau đó theo các directive **requires** để xác định những module cần thiết và xây dựng module graph.

Ví dụ module ứng dụng:

~~~java
module com.example.app {
    requires com.example.greeting;
    requires java.sql;
}
~~~

Khi khởi chạy **com.example.app**, Java cần tìm **com.example.greeting** và các dependency cần thiết của nó. Module ứng dụng cũng đọc module hệ thống **java.sql**.

Nếu một module được yêu cầu không thể tìm thấy hoặc không thể phân giải, ứng dụng có thể dừng trước khi main method chạy. Do đó, chỉ có file JAR trên đĩa chưa đủ; nó phải được đặt ở vị trí mà module path có thể quan sát và tên module phải khớp với tên trong directive **requires**.

Module gốc có thể được chọn bằng:

~~~bash
java --module-path mods --module com.example.app
~~~

Nếu muốn chỉ định rõ main class:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Tùy chọn **--add-modules** có thể bổ sung module gốc vào tập module cần phân giải trong những trường hợp đặc biệt. Nó không thay thế việc khai báo dependency trực tiếp cần thiết trong module descriptor của ứng dụng.

## 4. Khai báo dependency trong module-info.java

Một named module mô tả dependency bằng directive **requires**:

~~~java
module com.example.app {
    requires com.example.greeting;
    requires java.sql;
}
~~~

Một số dạng requires thường gặp:

- **requires module.name;**: khai báo dependency bắt buộc.
- **requires transitive module.name;**: khai báo dependency và truyền tiếp khả năng đọc tới module sử dụng module hiện tại.
- **requires static module.name;**: dependency cần ở thời điểm biên dịch nhưng có thể không bắt buộc ở runtime.

Tên trong **requires** là module name, không nhất thiết là tên JAR hoặc tên dependency trong Maven/Gradle. Ví dụ artifact có thể tên **greeting-library-2.1.jar**, trong khi module name được khai báo là **com.example.greeting**.

Khi gặp lỗi không tìm thấy module, hãy kiểm tra tên mà JAR thực sự công bố thay vì đoán từ tên file.

## 5. Ví dụ biên dịch các named module vào thư mục output

Giả sử có hai module source:

~~~text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/Message.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Module thư viện export package API:

~~~java
// src/com.example.greeting/module-info.java
module com.example.greeting {
    exports com.example.greeting;
}
~~~

~~~java
// src/com.example.greeting/com/example/greeting/Message.java
package com.example.greeting;

public class Message {
    public static String text() {
        return "Hello from module path";
    }
}
~~~

Module ứng dụng khai báo dependency:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.greeting;
}
~~~

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.greeting.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

Biên dịch cả hai module:

~~~bash
javac --module-source-path src -d out -m com.example.greeting,com.example.app
~~~

Sau khi biên dịch, thư mục output có cấu trúc tương tự:

~~~text
out/
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/Message.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Các thư mục con trong **out** là exploded module. Có thể dùng chính thư mục **out** làm module path:

~~~bash
java --module-path out --module com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Hello from module path
~~~

Ở đây, Java tìm module ứng dụng và module greeting trong **out**, đọc descriptor của chúng, phân giải quan hệ **requires**, rồi chạy main class của module ứng dụng.

## 6. Đưa modular JAR lên module path

Sau khi biên dịch, có thể đóng gói một module thành modular JAR. Ví dụ đóng gói module greeting:

~~~bash
jar --create --file mods/com.example.greeting.jar -C out/com.example.greeting .
~~~

Sau đó module ứng dụng có thể chạy với thư mục chứa JAR trên module path:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Trong ví dụ này, **mods** là thư mục chứa các modular JAR cần thiết. Nếu module ứng dụng vẫn ở dạng exploded module trong **out**, có thể kết hợp hai vị trí:

~~~bash
java --module-path "out:mods" --module com.example.app/com.example.app.Main
~~~

Trên Windows, dấu phân cách giữa các phần tử đường dẫn là dấu chấm phẩy (**;**); trên Linux và macOS là dấu hai chấm (**:**). Khi viết script chạy đa nền tảng, nên dùng cơ chế cấu hình classpath/module path của công cụ build thay vì hard-code dấu phân cách.

## 7. Dùng module path ở thời điểm biên dịch

Trình biên dịch **javac** cũng cần tìm dependency dạng module. Tùy chọn **--module-path** có thể được dùng cùng **--module-source-path**:

~~~bash
javac --module-path libs \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

Trong ví dụ này:

- **libs** chứa các module dependency mà source của ứng dụng cần.
- **src** chứa các thư mục source module.
- **out** nhận kết quả biên dịch.
- **-m com.example.app** chọn module cần biên dịch cùng các source/dependency cần thiết theo cấu hình.

Nếu module ứng dụng phụ thuộc vào một thư viện trên module path, descriptor của ứng dụng vẫn phải khai báo **requires**. Chỉ thêm JAR vào **--module-path** không tự tạo dependency trong source.

Cần đảm bảo cấu hình module path lúc biên dịch và lúc chạy nhất quán. Một ứng dụng có thể biên dịch thành công trong IDE vì IDE đã cấu hình dependency, nhưng thất bại khi chạy bằng lệnh nếu module path runtime thiếu JAR hoặc thư mục module.

## 8. Module path và classpath không thay thế nhau

Classpath và module path có thể cùng xuất hiện trong một tiến trình, nhưng mỗi vị trí tuân theo quy tắc riêng.

| Cấu hình | Cách Java xử lý |
|---|---|
| Modular JAR trên module path | Named module theo module descriptor |
| JAR không có descriptor trên module path | Automatic module |
| JAR trên classpath | Thành phần của unnamed module |
| Thư mục module đã biên dịch trên module path | Exploded module |
| Thư mục class trên classpath | Class được tìm theo cơ chế classpath |

Ví dụ một ứng dụng modular có thể dùng thêm thư viện cũ trên classpath:

~~~bash
java --module-path mods \
     --class-path libs/legacy-helper.jar \
     --module com.example.app/com.example.app.Main
~~~

Named module không tự động đọc unnamed module. Nếu module ứng dụng cần truy cập class trên classpath, có thể cần một cạnh đọc bổ sung như **--add-reads com.example.app=ALL-UNNAMED** trong giai đoạn chuyển đổi. Nên cân nhắc đưa thư viện lên module path và sử dụng automatic module nếu phù hợp, thay vì duy trì các quyền bổ sung không cần thiết.

## 9. Tên module và xung đột trên module path

Tên module trong descriptor là định danh được dùng trong module graph. Khi có nhiều module trên module path, cần bảo đảm tên module rõ ràng và không có nhiều phiên bản khác nhau cùng công bố một module name trong cấu hình.

Có thể kiểm tra JAR bằng:

~~~bash
jar --describe-module --file libs/example.jar
~~~

Lệnh này hiển thị module name và các directive của modular JAR; với JAR không có descriptor, công cụ có thể hiển thị tên automatic module được suy ra hoặc khai báo trong manifest.

Một số lỗi thường gặp:

- **Module not found**: module được yêu cầu không có trên module path hoặc tên trong requires không khớp.
- **FindException / ResolutionException**: module graph không thể phân giải do thiếu dependency hoặc có xung đột.
- **Package ... is not visible**: package chưa được export phù hợp, dù module đã được tìm thấy.
- **Duplicate module**: nhiều nguồn trên module path cùng công bố tên module gây xung đột hoặc lựa chọn không mong muốn.

Không nên giải quyết lỗi bằng cách thêm tất cả JAR vào module path một cách máy móc. Hãy xác định dependency thực tế, module name và loại module của từng thư viện.

## 10. Lỗi thường gặp khi cấu hình module path

**Đặt nhầm thư mục module path**

Nếu chỉ định một thư mục không chứa module hợp lệ theo cấu trúc mong đợi, Java sẽ không tìm thấy module. Kiểm tra xem thư mục có modular JAR, exploded module hoặc các module có thể quan sát được hay không.

**Có JAR nhưng module vẫn không tìm thấy**

JAR có thể nằm trên classpath thay vì module path, hoặc module name trong **requires** khác tên được công bố trong descriptor. Dùng **jar --describe-module** để kiểm tra.

**Chạy được trong IDE nhưng không chạy bằng terminal**

IDE có thể đã cấu hình module path riêng. Hãy kiểm tra command line thực tế, đặc biệt là **--module-path**, **--module** và dependency runtime.

**Biên dịch thành công nhưng runtime thiếu module**

Cấu hình compile-time và runtime có thể khác nhau. Đảm bảo mọi module cần thiết đều được đưa vào module path lúc chạy, không chỉ lúc biên dịch.

**Module path chứa nhiều bản của một module**

Loại bỏ phiên bản dư thừa và giữ một module name nhất quán trong cấu hình. Tránh trộn các JAR của nhiều phiên bản thư viện trong cùng module path.

## 11. Ghi nhớ

- Module path là nơi Java tìm named module, exploded module và automatic module có thể quan sát được.
- Dùng **--module-path** hoặc **-p** để cấu hình đường dẫn module.
- Dùng **--module** hoặc **-m** để chọn module gốc cần chạy.
- Named module khai báo dependency bằng **requires**; chỉ có JAR trên module path không tự tạo quan hệ dependency trong source.
- Có thể dùng module path ở cả thời điểm biên dịch với javac và thời điểm chạy với java.
- Module path và classpath có thể kết hợp, nhưng class trên classpath thuộc unnamed module và named module không tự động đọc nó.
- Kiểm tra module name bằng **jar --describe-module** khi gặp lỗi phân giải.
- Giữ module path nhất quán giữa môi trường phát triển, kiểm thử và triển khai.

Khi cấu hình ứng dụng modular, hãy coi module path là một phần của cấu hình build và runtime. Đặt đúng module vào đúng vị trí, khai báo dependency tường minh và kiểm tra module graph giúp ứng dụng có thể khởi chạy ổn định ngoài IDE.
