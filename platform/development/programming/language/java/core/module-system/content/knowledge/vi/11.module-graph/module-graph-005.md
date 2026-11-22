# Module path tìm module theo tên

Trong Java Platform Module System (JPMS), **module path** là nơi Java tìm các mô-đun có thể dùng khi biên dịch và khởi chạy. Điểm cốt lõi là JPMS định danh một mô-đun bằng **module name** trong module descriptor, chứ không tìm dependency bằng tên lớp hoặc tên file JAR như classpath truyền thống.

Khi một mô-đun khai báo requires, Java tìm mô-đun có tên tương ứng trên module path hoặc trong các mô-đun nền tảng mà runtime cung cấp. Sau đó, bộ phân giải xây dựng module graph từ các mô-đun gốc và những dependency mà chúng yêu cầu.

## 1. Module path là gì?

Module path là danh sách các vị trí chứa mô-đun. Một vị trí có thể là:

- Modular JAR có module-info.class.
- Thư mục mô-đun đã biên dịch dạng exploded module, trong đó có module-info.class.
- JAR cũ không có descriptor nhưng được nhận diện thành automatic module khi nằm trên module path.
- Thư mục chứa nhiều modular JAR hoặc exploded module.

Ví dụ thư mục:

~~~text
project/
├── mods/
│   ├── com.example.customer.jar
│   ├── com.example.orders.jar
│   └── com.example.reporting/
│       ├── module-info.class
│       └── com/example/reporting/Main.class
└── libs/
    └── commons-text-1.11.0.jar
~~~

Trong ví dụ này, mods chứa hai modular JAR và một exploded module. JAR trong libs có thể trở thành automatic module nếu được đưa vào module path và không có module descriptor.

Khi chạy ứng dụng, có thể chỉ định các vị trí này:

~~~bash
java --module-path mods:libs -m com.example.orders/com.example.orders.Main
~~~

Dấu hai chấm phân tách các phần tử đường dẫn trên Unix-like. Trên Windows, dùng dấu chấm phẩy:

~~~powershell
java --module-path "mods;libs" -m com.example.orders/com.example.orders.Main
~~~

Có thể dùng tùy chọn ngắn **-p** thay cho **--module-path**.

## 2. Java tìm mô-đun theo module name

Giả sử mô-đun orders có descriptor:

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

Mô-đun customer có descriptor:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

Khi biên dịch hoặc chạy orders, JPMS cần tìm một mô-đun có tên chính xác là **com.example.customer**. Tên này được lấy từ module-info.class của modular JAR hoặc exploded module.

Ví dụ file có tên:

~~~text
customer-library-2.0.jar
~~~

nhưng descriptor bên trong khai báo:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

thì module name vẫn là **com.example.customer**. Tên file JAR có thể thay đổi mà không làm thay đổi module name, miễn là descriptor vẫn giữ nguyên.

Điều này khác với automatic module: khi JAR không có module-info.class và không khai báo Automatic-Module-Name, tên mô-đun được suy ra từ tên file JAR. Vì vậy, cần phân biệt module name tường minh và tên suy ra.

Module name là định danh dùng trong các chỉ thị requires, exports to, opens to, uses, provides và trong lệnh khởi chạy bằng -m.

## 3. requires kết nối các mô-đun trong module graph

Module path cho biết Java có thể tìm thấy những mô-đun nào. Module descriptor cho biết mô-đun nào cần đọc mô-đun nào.

Ví dụ ba mô-đun:

~~~text
com.example.app
    └── requires com.example.orders

com.example.orders
    └── requires com.example.customer

com.example.customer
    └── requires java.sql
~~~

Khi ứng dụng khởi chạy từ com.example.app, bộ phân giải bắt đầu từ mô-đun gốc và lần theo các chỉ thị requires để xây dựng module graph.

Có thể biểu diễn:

~~~java
module com.example.app {
    requires com.example.orders;
}
~~~

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

~~~java
module com.example.customer {
    requires java.sql;
}
~~~

Nếu một dependency không được tìm thấy theo module name, quá trình biên dịch hoặc khởi chạy có thể thất bại với lỗi như:

~~~text
error: module not found: com.example.customer
~~~

hoặc:

~~~text
java.lang.module.FindException:
Module com.example.customer not found
~~~

Cách sửa là kiểm tra module name thực tế và bảo đảm mô-đun tương ứng nằm trong module path hoặc nguồn mô-đun thích hợp.

## 4. Observable module và resolved module

Hai khái niệm này giúp hiểu vì sao một JAR có trong module path nhưng chưa chắc đã được nạp vào module graph.

**Observable module** là mô-đun mà bộ phân giải có thể tìm thấy thông qua các module finder, chẳng hạn module path và các mô-đun hệ thống của JDK.

**Resolved module** là mô-đun đã được đưa vào module graph sau quá trình phân giải từ các mô-đun gốc và dependency của chúng.

Ví dụ module path có:

~~~text
mods/
├── com.example.app.jar
├── com.example.customer.jar
├── com.example.reporting.jar
└── com.example.unused.jar
~~~

Nếu ứng dụng gốc là com.example.app và nó chỉ yêu cầu com.example.customer, mô-đun reporting hoặc unused có thể vẫn quan sát được trên module path nhưng không thuộc module graph được phân giải của lần chạy đó.

Điều này có nghĩa việc đặt một JAR vào module path chỉ làm cho mô-đun có thể được tìm thấy. Nó không đồng nghĩa mọi mô-đun trong thư mục đều tự động trở thành dependency của ứng dụng.

Để bổ sung một mô-đun làm root module khi khởi chạy, dùng **--add-modules**:

~~~bash
java --module-path mods --add-modules com.example.reporting \
    -m com.example.app/com.example.app.Main
~~~

Tùy chọn này yêu cầu mô-đun reporting được đưa vào tập mô-đun gốc để phân giải. Các dependency requires của nó cũng được xem xét khi xây dựng module graph.

## 5. Mô-đun gốc được chọn như thế nào?

Khi khởi chạy một ứng dụng modular, tùy chọn **-m** hoặc **--module** chỉ định mô-đun gốc và lớp main:

~~~bash
java --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Cú pháp tổng quát:

~~~text
module.name/main.class
~~~

Trong đó:

- module.name là module name của mô-đun ứng dụng.
- main.class là tên đầy đủ của lớp có phương thức main.
- --module-path xác định nơi tìm các mô-đun.

Có thể thêm một hoặc nhiều root module bằng --add-modules:

~~~bash
java --module-path mods \
    --add-modules com.example.reporting,com.example.metrics \
    -m com.example.app/com.example.app.Main
~~~

Mỗi root module sẽ được phân giải cùng các dependency mà nó yêu cầu. Nếu tên root module không tồn tại trên module path hoặc trong nguồn mô-đun tương ứng, JVM sẽ báo không tìm thấy mô-đun.

Đối với lệnh chạy một lớp truyền thống bằng tên lớp sau -cp, lớp main thuộc unnamed module. Đây là cách khởi chạy theo classpath, không phải khởi chạy named module bằng -m.

## 6. Module path khác classpath ở điểm nào?

Classpath và module path đều giúp JVM tìm mã đã biên dịch, nhưng chúng dùng mô hình định danh và truy cập khác nhau.

| Đặc điểm | Classpath | Module path |
| --- | --- | --- |
| Đơn vị tìm kiếm | Lớp và tài nguyên trong thư mục/JAR | Mô-đun theo module name |
| Descriptor | Không dùng module descriptor để tạo named module | Dùng module-info.class hoặc quy tắc automatic module |
| Dependency | Thường được quản lý bởi build tool và class loader | Khai báo bằng requires trong module descriptor |
| Đóng gói package | Không có ranh giới JPMS giữa các JAR trên classpath | Package chịu kiểm soát bởi exports và opens |
| Danh tính | Các lớp thuộc unnamed module tương ứng | Named module hoặc automatic module |
| Truy cập | Theo quy tắc class loader và Java language | Theo cả quy tắc Java và module readability/access |

Một named module không thể viết requires tới unnamed module vì unnamed module không có module name. Nếu một thư viện chỉ nằm trên classpath, mô-đun có tên không thể tham chiếu nó bằng một chỉ thị requires thông thường.

Nếu cần dùng thư viện cũ từ named module, có thể đưa JAR lên module path để Java nhận diện nó thành automatic module, hoặc sử dụng một bản thư viện đã có module descriptor.

## 7. Tên file JAR không phải lúc nào cũng là module name

Với modular JAR, tên module được khai báo trong module-info.class.

Ví dụ:

~~~text
customer-client-2.1.jar
~~~

có thể chứa:

~~~java
module org.example.customer {
    exports org.example.customer.api;
}
~~~

Khi đó module name là **org.example.customer**.

Với JAR không có descriptor:

- Nếu manifest có Automatic-Module-Name, Java dùng giá trị đó.
- Nếu không có thuộc tính này, Java suy ra tên từ tên file JAR.

Kiểm tra bằng:

~~~bash
jar --describe-module --file libs/customer-client-2.1.jar
~~~

Kết quả cho biết module name mà JDK nhận diện, loại mô-đun và các package hoặc chỉ thị liên quan.

Không nên sửa requires theo suy đoán từ artifactId hoặc tên file. Hãy xác minh module name trên đúng artifact đang được build hoặc triển khai.

## 8. Nhiều vị trí module path và vấn đề trùng tên

Có thể cung cấp nhiều vị trí module path:

~~~bash
java --module-path mods:libs:plugins \
    -m com.example.app/com.example.app.Main
~~~

Java có thể tìm mô-đun trong các vị trí được cấu hình. Tuy nhiên, module graph yêu cầu tên mô-đun phải được định danh rõ ràng. Nếu nhiều artifact cung cấp cùng một module name trong cùng module finder hoặc cấu hình, quá trình tìm kiếm/phân giải có thể báo lỗi trùng mô-đun.

Ví dụ:

~~~text
libs/
├── customer-1.0.jar
└── customer-2.0.jar
~~~

Nếu cả hai cùng khai báo module name com.example.customer hoặc cùng suy ra một automatic module name, không nên đặt cả hai vào cùng module configuration.

Hãy chọn phiên bản phù hợp bằng dependency management của Gradle hoặc Maven, rồi xác nhận module path cuối cùng chỉ chứa một mô-đun cho tên cần dùng.

Tên file khác nhau không làm cho hai mô-đun cùng tên trở thành hai dependency độc lập.

## 9. Module path của javac và java cần nhất quán

Khi biên dịch mã nguồn modular, cung cấp dependency trên module path:

~~~bash
javac --module-path libs \
    --module-source-path src \
    -d out \
    -m com.example.app
~~~

Lệnh trên cho javac biết:

- libs chứa dependency đã biên dịch.
- src chứa các source module theo cấu trúc module source path.
- out là thư mục output.
- com.example.app là mô-đun cần biên dịch.

Khi chạy, cung cấp các mô-đun đã biên dịch và dependency:

~~~bash
java --module-path out:libs \
    -m com.example.app/com.example.app.Main
~~~

Nếu compile dùng module path nhưng runtime lại thiếu một dependency, ứng dụng có thể biên dịch thành công rồi thất bại khi khởi chạy.

Ngược lại, thêm một JAR vào classpath khi ứng dụng được khởi chạy bằng -m không tự biến JAR đó thành một named module mà requires có thể tham chiếu.

## 10. Các tùy chọn liên quan đến module graph

Một số tùy chọn JVM hữu ích khi làm việc với module path:

| Tùy chọn | Mục đích |
| --- | --- |
| --module-path hoặc -p | Chỉ định nơi tìm mô-đun. |
| --module hoặc -m | Chỉ định mô-đun gốc và lớp main. |
| --add-modules | Bổ sung mô-đun gốc cần phân giải. |
| --show-module-resolution | Hiển thị quá trình phân giải mô-đun khi khởi chạy. |
| --list-modules | Liệt kê các mô-đun mà runtime quan sát được trong cấu hình. |
| --limit-modules | Giới hạn tập mô-đun hệ thống có thể quan sát. |
| --upgrade-module-path | Cung cấp mô-đun thay thế cho mô-đun hệ thống theo cơ chế upgrade. |
| --patch-module | Bổ sung lớp/tài nguyên vào một mô-đun đã có. |

Không nên nhầm --upgrade-module-path với module path thông thường. Nó phục vụ cơ chế thay thế một số mô-đun hệ thống theo quy tắc riêng của JPMS.

Tương tự, --patch-module không phải cách thông thường để thêm một dependency mới. Nó bổ sung nội dung vào một mô-đun đã xác định.

## 11. Kiểm tra mô-đun nào được tìm thấy và phân giải

Khi gặp lỗi module not found hoặc muốn biết module graph thực tế, có thể kiểm tra theo trình tự:

### Bước 1: Xác định module name của artifact

~~~bash
jar --describe-module --file libs/customer.jar
~~~

Xác nhận tên mô-đun bên trong JAR. Nếu là automatic module, xem tên lấy từ manifest hoặc tên file.

### Bước 2: Kiểm tra runtime nhìn thấy những mô-đun nào

~~~bash
java --module-path mods:libs --list-modules
~~~

Lệnh này giúp kiểm tra các mô-đun hệ thống và mô-đun trên module path mà runtime có thể quan sát.

### Bước 3: Xem quá trình phân giải

~~~bash
java --show-module-resolution \
    --module-path mods:libs \
    -m com.example.app/com.example.app.Main
~~~

Đầu ra cho biết các mô-đun được resolve và quan hệ dependency liên quan. Đây là bằng chứng hữu ích khi một mô-đun có trên module path nhưng không xuất hiện trong graph như dự kiến.

### Bước 4: Kiểm tra dependency của mô-đun

~~~bash
jdeps --module-path mods:libs --check com.example.app
~~~

jdeps hỗ trợ phân tích dependency và kiểm tra module descriptor. Khi cần phân tích một JAR cụ thể, có thể dùng thêm các tùy chọn như --print-module-deps hoặc --list-deps.

### Bước 5: Đối chiếu lệnh build và lệnh triển khai

So sánh module path ở compile-time với module path ở runtime. Kiểm tra phiên bản JDK, vị trí artifact và module name của từng dependency. IDE có thể tự bổ sung module path nên lệnh chạy trực tiếp trong terminal là phép kiểm tra quan trọng.

## 12. Những lỗi thường gặp

| Thông báo hoặc hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| module not found | JAR thiếu, sai module name hoặc sai module path | Dùng jar --describe-module và kiểm tra --module-path. |
| FindException: Module ... not found | Root module hoặc dependency requires không quan sát được | Kiểm tra tên sau -m/--add-modules và các requires. |
| Duplicate module | Nhiều artifact cùng cung cấp một module name | Loại bỏ phiên bản hoặc artifact trùng. |
| Mã nguồn không import được package | Thiếu requires hoặc package chưa exports | Kiểm tra descriptor của mô-đun gọi và mô-đun sở hữu API. |
| Chạy bằng IDE được nhưng terminal lỗi | IDE và terminal dùng module path khác nhau | So sánh lệnh chạy và dependency thực tế. |
| JAR có trong thư mục nhưng không xuất hiện trong graph | Mô-đun chỉ observable, chưa được resolve từ root | Kiểm tra requires, root module và --add-modules. |
| JAR trên classpath nhưng requires không tìm thấy | JAR thuộc unnamed module | Đưa JAR lên module path hoặc thay đổi thiết kế tích hợp. |

## 13. Nguyên tắc sử dụng module path

- Dùng module name đã xác minh trong module-info.java và lệnh -m.
- Giữ module path của compile-time và runtime nhất quán với cấu hình triển khai.
- Tách rõ thư viện trên module path và thư viện trên classpath.
- Chỉ thêm root module bằng --add-modules khi có nhu cầu phân giải cụ thể.
- Tránh đưa nhiều phiên bản có cùng module name vào một module configuration.
- Dùng jar --describe-module để xác định tên mô-đun của JAR.
- Dùng --show-module-resolution để hiểu module graph thực tế.
- Không xem việc một JAR có mặt trên module path là bằng chứng rằng nó đã được resolve.

Module path tìm mô-đun theo tên và module descriptor. Module graph sau đó được hình thành từ các mô-đun gốc cùng những quan hệ requires của chúng. Khi phân biệt rõ vị trí tìm kiếm, module name và trạng thái resolution, việc chẩn đoán dependency của ứng dụng modular sẽ chính xác hơn.

## 14. Tự kiểm tra

**Tình huống 1:** Một JAR tên customer-client.jar chứa module-info.class khai báo module org.example.customer. Mô-đun ứng dụng cần viết requires theo tên nào?

Trả lời: requires org.example.customer. Với modular JAR, module name lấy từ module descriptor, không lấy trực tiếp từ tên file.

**Tình huống 2:** Một JAR đã có trong thư mục mods nhưng không xuất hiện trong module graph của ứng dụng. Có thể do đâu?

Trả lời: JAR có thể observable trên module path nhưng chưa được resolve từ root module. Kiểm tra requires, root module và tùy chọn --add-modules.

**Tình huống 3:** Mô-đun app khai báo requires orders; orders khai báo requires customer. App có cần khai báo requires customer không?

Trả lời: Nếu mã của app trực tiếp sử dụng kiểu thuộc customer, app cần quan hệ readability phù hợp. Nếu chỉ orders sử dụng customer và dependency không được truyền tiếp bằng requires transitive, app không tự động đọc customer.

**Tình huống 4:** Có thể đặt hai phiên bản của cùng một named module trong hai thư mục khác nhau trên module path không?

Trả lời: Không nên. Nếu cả hai cùng cung cấp một module name trong cùng module configuration, việc tìm và phân giải có thể báo trùng mô-đun. Hãy chọn một phiên bản.

**Tình huống 5:** Thư viện nằm trên classpath, nhưng named module khai báo requires tới thư viện đó. Vì sao không hoạt động?

Trả lời: Trên classpath, thư viện thuộc unnamed module và không có module name để requires tham chiếu. Đưa thư viện lên module path để được nhận diện thành automatic module hoặc dùng bản modular của thư viện.
