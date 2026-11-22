# Đặt JAR trên classpath, module path và hệ quả

Trong Java, class và JAR có thể được đưa vào chương trình thông qua **classpath** hoặc **module path**. Hai cơ chế này đều giúp JVM tìm thấy mã cần chạy, nhưng chúng tạo ra cách tổ chức và kiểm soát truy cập khác nhau. Chọn sai vị trí có thể khiến module không được tìm thấy, dependency không đọc được, hoặc ranh giới đóng gói của JPMS không được áp dụng như dự kiến.

Bài này tập trung vào cách đặt JAR, cách biên dịch và chạy ứng dụng, cùng những hệ quả trực tiếp đối với module graph, khả năng truy cập package và quá trình chuyển đổi ứng dụng cũ.

## 1. Classpath dùng để làm gì?

Classpath là đường dẫn tìm kiếm class truyền thống của Java. Nó có thể chứa thư mục class đã biên dịch hoặc các file JAR. Khi chạy ứng dụng, dùng **-cp** hoặc **--class-path**:

~~~bash
java -cp "out:libs/legacy.jar" com.example.app.Main
~~~

Trên Windows, dấu phân cách giữa các mục trong classpath là dấu chấm phẩy (**;**); trên Linux và macOS, dấu phân cách là dấu hai chấm (**:**). Có thể dùng dấu nháy kép để gom nhiều mục thành một giá trị khi shell cần.

Ví dụ biên dịch một ứng dụng classpath:

~~~bash
javac -cp libs/legacy.jar -d out src/com/example/app/Main.java
java -cp "out:libs/legacy.jar" com.example.app.Main
~~~

Các đặc điểm chính:

- JVM tìm class trong những thư mục và JAR được liệt kê.
- Dependency không cần khai báo bằng **requires**.
- Package không có ranh giới export theo JPMS; các class được nạp từ classpath thuộc unnamed module tương ứng của class loader.
- Nếu nhiều vị trí chứa class cùng tên, thứ tự tìm kiếm và class loader có thể ảnh hưởng class nào được nạp.
- **module-info.class** nằm trong JAR trên classpath không được dùng để tạo module graph.

Classpath phù hợp với ứng dụng Java truyền thống, thư viện chưa được modular hóa và các hệ thống cần duy trì cách chạy cũ. Tuy nhiên, nó không tạo ra dependency graph tường minh và không cung cấp khả năng đóng gói package theo từng named module.

## 2. Module path hoạt động như thế nào?

Module path là nơi JVM và trình biên dịch tìm các module JPMS. Dùng **-p** hoặc **--module-path**:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Module path có thể chứa:

- Modular JAR có **module-info.class**.
- Thư mục module đã được giải nén, trong đó có **module-info.class** ở gốc.
- JAR chưa có descriptor; khi được đặt trên module path, loại JAR này có thể được xem là automatic module.

Với modular JAR, Java đọc module descriptor để biết tên module, các dependency **requires**, package được **exports** hoặc **opens**, cùng những khai báo dịch vụ. Trình phân giải module sử dụng các thông tin đó để tạo module graph trước khi chạy ứng dụng.

Một named module cần khai báo dependency trực tiếp trong **module-info.java**:

~~~java
module com.example.app {
    requires java.sql;
    requires com.example.logging;
}
~~~

Nếu **com.example.logging** không có trong module path hoặc không thể phân giải theo tên được yêu cầu, quá trình biên dịch hoặc khởi chạy có thể thất bại. Đây là khác biệt quan trọng so với classpath: dependency của named module được kiểm tra qua module graph, thay vì chỉ dựa vào việc JAR có xuất hiện trong một danh sách classpath hay không.

## 3. Cùng một JAR có thể có cách xử lý khác nhau

Loại module được xác định bởi cả nội dung JAR và vị trí đặt nó.

| Nội dung JAR | Đặt trên classpath | Đặt trên module path |
|---|---|---|
| Có module-info.class | Được nạp như thành phần của unnamed module; descriptor không tham gia phân giải | Được nhận diện là named module theo descriptor |
| Không có module-info.class | Được nạp như thành phần của unnamed module | Được nhận diện là automatic module |

Ví dụ, một thư viện **logging.jar** có module-info.class:

~~~bash
# Đưa JAR vào classpath
java -cp "app.jar:logging.jar" com.example.app.Main

# Đưa JAR vào module path
java --module-path "app.jar:logging.jar" --module com.example.app/com.example.app.Main
~~~

Hai lệnh trên không tương đương. Ở lệnh đầu, JVM không áp dụng các chỉ thị JPMS trong descriptor của **logging.jar**. Ở lệnh thứ hai, JAR được xử lý như một module có tên; ứng dụng cần khai báo và thỏa mãn quan hệ module tương ứng.

Tương tự, JAR cũ không có descriptor vẫn có thể chạy trên module path dưới dạng automatic module. Điều đó giúp tích hợp dần thư viện cũ, nhưng chưa tạo được hợp đồng export/opens được thiết kế tường minh như một named module hoàn chỉnh.

## 4. Hệ quả đối với dependency và khả năng đọc module

Trên classpath, ứng dụng thường chỉ cần đưa JAR cần thiết vào **-cp**. Trên module path, một named module cần có cạnh đọc tới module chứa API mà nó sử dụng. Cạnh này thường được khai báo bằng **requires**.

Ví dụ:

~~~java
module com.example.app {
    requires com.example.payment;
}
~~~

Nếu **com.example.payment** nằm trên module path nhưng ứng dụng thiếu **requires**, module graph không có quan hệ đọc cần thiết. Việc JAR tồn tại trên đĩa không tự động làm cho mọi named module có thể sử dụng nó.

Chiều truy cập tới classpath cũng có quy tắc riêng. Các class trên classpath thuộc unnamed module, và named module không tự động đọc unnamed module. Trong một số tình huống chuyển đổi, có thể thêm cạnh đọc tạm thời:

~~~bash
java --module-path mods --class-path libs/legacy-helper.jar --add-reads com.example.app=ALL-UNNAMED --module com.example.app/com.example.app.Main
~~~

Tùy chọn **--add-reads** ở ví dụ trên cho phép **com.example.app** đọc unnamed module. Nó hữu ích khi phải giữ một thư viện trên classpath trong lúc chuyển đổi, nhưng làm giảm tính tường minh của module graph. Khi có thể, nên đưa dependency lên module path và xác định loại module của nó một cách ổn định.

Cũng cần phân biệt khả năng đọc module với khả năng truy cập package:

- **requires** tạo quan hệ đọc giữa các module.
- **exports** công khai package để module khác truy cập các kiểu **public**.
- **opens** cho phép reflection sâu vào package ở runtime theo phạm vi được khai báo.

Có **requires** nhưng package không được export thì module gọi vẫn không thể sử dụng API trong package đó. Ngược lại, export package không tự tạo dependency **requires** cho module sử dụng.

## 5. Hệ quả đối với đóng gói và reflection

Classpath không áp dụng ranh giới đóng gói của named module. Khi JAR được đặt trên module path và trở thành named module, chỉ các package được export mới là API truy cập thông thường từ module khác.

Ví dụ:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module khác có thể sử dụng kiểu **public** trong **com.example.domain.api** sau khi khai báo **requires com.example.domain**. Package **com.example.domain.internal** không được export nên không trở thành API công khai qua ranh giới module.

Framework sử dụng reflection có thể cần truy cập trường hoặc constructor private. **exports** không cấp quyền truy cập sâu như vậy. Module sở hữu package có thể mở package cho module framework:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.mapper;
}
~~~

Trong giai đoạn chuyển đổi, **--add-exports** và **--add-opens** có thể bổ sung quyền truy cập ở runtime cho tình huống cụ thể. Ví dụ:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.mapper ...
~~~

Các tùy chọn này nên được giới hạn đúng package và module đích. Nếu một ứng dụng chạy được trên classpath nhưng gặp **InaccessibleObjectException** sau khi chuyển sang module path, hãy kiểm tra nhu cầu reflection và các directive **opens** trước khi mở rộng quyền truy cập toàn bộ module.

## 6. Biên dịch và chạy một ứng dụng modular

Giả sử source của ứng dụng có cấu trúc:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java

libs/
└── com.example.logging.jar
~~~

Module descriptor khai báo dependency:

~~~java
module com.example.app {
    requires com.example.logging;
}
~~~

Biên dịch module:

~~~bash
javac --module-path libs --module-source-path src -d out -m com.example.app
~~~

Chạy ứng dụng:

~~~bash
java --module-path "out:libs" --module com.example.app/com.example.app.Main
~~~

Ở đây:

- **--module-source-path** cho biết vị trí các source module.
- **--module-path** giúp **javac** và JVM tìm dependency dạng module.
- **-d out** đặt kết quả biên dịch vào thư mục output.
- **-m** chọn module cần biên dịch hoặc chạy; ở lệnh chạy, phần sau dấu **/** là tên class main.

Trên Windows, thay dấu **:** trong danh sách đường dẫn bằng dấu **;**. Khi module có nhiều dependency, tất cả module cần thiết phải có thể được tìm thấy trên module path tại cả thời điểm biên dịch và thời điểm chạy.

## 7. Kết hợp classpath và module path

Java cho phép một tiến trình sử dụng cả hai cơ chế. Đây là cách hữu ích trong quá trình chuyển đổi hệ thống lớn, khi một số thư viện đã có module descriptor nhưng các thư viện khác vẫn được giữ trên classpath.

Ví dụ:

~~~bash
java --module-path mods --class-path "config:libs/old-driver.jar" --module com.example.app/com.example.app.Main
~~~

Cần xác định rõ module nào sử dụng thư viện nào. Nếu named module cần đọc class trên classpath, có thể cần **--add-reads** như phần trước. Nếu thư viện cũ cần truy cập package nội bộ của một named module, có thể phát sinh nhu cầu cấu hình export/open bổ sung; nên xử lý theo đúng module và package thực tế.

Một số lưu ý khi phối hợp:

- Không giả định JAR trên classpath tự động trở thành module chỉ vì tiến trình được khởi chạy bằng **--module**.
- Không giả định named module tự động đọc mọi thư viện trên classpath.
- Giữ các dependency có module descriptor trên module path để JPMS áp dụng descriptor của chúng.
- Tránh để cùng một thư viện hoặc các bản sao khác phiên bản xuất hiện ở nhiều vị trí, vì class loader và module resolution có thể tạo ra hành vi khó dự đoán.
- Kiểm tra module name thực tế của JAR trước khi viết **requires**; tên artifact Maven/Gradle có thể khác tên module.

## 8. Cách kiểm tra vị trí và module của JAR

Để xem một JAR được Java nhận diện ra sao, dùng:

~~~bash
jar --describe-module --file libs/example.jar
~~~

Kết quả cho biết tên module và các directive nếu JAR là modular JAR; với JAR không có descriptor, công cụ có thể hiển thị tên automatic module được suy ra hoặc khai báo trong manifest.

Để quan sát các module có sẵn trong runtime:

~~~bash
java --list-modules
~~~

Khi chẩn đoán, hãy kiểm tra lần lượt:

1. JAR hoặc thư mục class có thực sự được truyền vào lệnh chạy không?
2. Nó đang nằm trên classpath hay module path?
3. Nếu nằm trên module path, tên module thực tế là gì?
4. Named module sử dụng dependency đã khai báo **requires** chưa?
5. Package API đã được **exports** chưa?
6. Nếu framework dùng reflection, package cần thiết đã được **opens** đúng phạm vi chưa?

Các bước này giúp xác định lỗi thuộc đường dẫn tìm class, module resolution, quan hệ đọc hay quyền truy cập package.

## 9. Lỗi thường gặp

**ClassNotFoundException** hoặc **NoClassDefFoundError**

JAR hoặc thư mục class có thể chưa nằm trong classpath/module path của tiến trình, hoặc đường dẫn runtime khác với đường dẫn đã dùng khi biên dịch. Kiểm tra lệnh chạy và dependency thực tế, không chỉ cấu hình IDE.

**Module ... not found**

Module được khai báo trong **requires** không thể được tìm thấy hoặc phân giải. Kiểm tra **--module-path**, tên module trong descriptor/manifest và dependency bắc cầu cần thiết.

**package ... is not visible** hoặc lỗi truy cập package

Kiểm tra cả quan hệ **requires** lẫn directive **exports** của module sở hữu package. Hai điều kiện này giải quyết hai vấn đề khác nhau.

**Ứng dụng chuyển sang module path rồi lỗi reflection**

Kiểm tra thông báo lỗi để xác định package và module đích. Thêm **opens** có phạm vi hẹp nếu ứng dụng thực sự cần reflection sâu; tránh mở toàn bộ module khi chỉ một package cần được truy cập.

**Thư viện trên classpath không được named module nhìn thấy**

Named module không tự động đọc unnamed module. Có thể dùng **--add-reads ...=ALL-UNNAMED** làm giải pháp chuyển tiếp, hoặc chuyển dependency lên module path và khai báo module phù hợp.

**Ứng dụng chạy trong IDE nhưng lỗi khi chạy bằng lệnh**

IDE có thể đang cấu hình classpath, module path, VM options hoặc working directory khác với lệnh chạy độc lập. So sánh cấu hình launch thực tế, đặc biệt là **-cp**, **--module-path**, **--module** và các tùy chọn **--add-***.

## 10. Lộ trình chuyển từ classpath sang module path

Không cần chuyển toàn bộ ứng dụng trong một lần. Có thể thực hiện theo từng bước:

1. Liệt kê JAR và thư mục class mà ứng dụng đang sử dụng, bao gồm dependency runtime và dependency chỉ dùng khi biên dịch.
2. Kiểm tra từng JAR bằng **jar --describe-module** để biết nó đã có descriptor hay chưa.
3. Chọn một module ứng dụng hoặc thư viện có ranh giới package rõ ràng để tạo **module-info.java**.
4. Đưa module đã chuyển cùng các dependency phù hợp lên module path; giữ thư viện chưa sẵn sàng trên classpath nếu cần.
5. Khai báo **requires** và chỉ **exports** các package là API công khai.
6. Xử lý nhu cầu reflection bằng **opens** đúng package và đúng module đích.
7. Chạy lại cả bước biên dịch lẫn runtime bằng cấu hình module path thực tế.
8. Khi một dependency đã được modular hóa, loại bỏ các tùy chọn **--add-reads**, **--add-exports** hoặc **--add-opens** tạm thời nếu không còn cần thiết.

Trong quá trình này, cần giữ tên module ổn định và tránh để hai phiên bản của cùng một thư viện cùng xuất hiện trên các đường dẫn khác nhau. Với thư viện chưa có descriptor nhưng phải dùng trên module path lâu dài, hãy ưu tiên artifact có **Automatic-Module-Name** ổn định hoặc phiên bản đã cung cấp module descriptor.

## 11. Ghi nhớ

- **-cp** / **--class-path** đưa thư mục và JAR vào đường dẫn tìm class truyền thống.
- **-p** / **--module-path** đưa module vào vùng tìm kiếm để Java phân giải module graph.
- Modular JAR trên classpath được xử lý như thành phần của unnamed module; descriptor không được dùng.
- JAR có descriptor trên module path trở thành named module; JAR không có descriptor trên module path có thể trở thành automatic module.
- Named module cần **requires** để đọc module khác; package API cần **exports**; reflection sâu thường cần **opens**.
- Có thể kết hợp classpath và module path trong một tiến trình, nhưng cần kiểm soát rõ các cạnh đọc và quyền truy cập.
- Khi chuyển đổi, hãy kiểm tra đường dẫn ở cả compile time và runtime vì hai cấu hình có thể khác nhau.
