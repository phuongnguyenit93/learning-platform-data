# Phân tích module cần thiết bằng jdeps trong Java 17

## 1. jdeps dùng để làm gì?

`jdeps` là công cụ dòng lệnh đi kèm JDK, dùng để phân tích các phụ thuộc (*dependencies*) được thể hiện trong bytecode Java. Công cụ có thể đọc class file, thư mục chứa class, JAR và module để cho biết:

- Một class hoặc package tham chiếu tới những package nào.
- Một JAR phụ thuộc vào những JAR hoặc module nào.
- Ứng dụng cần những module nào của Java Platform Module System (JPMS).
- Một module descriptor đang khai báo phụ thuộc ra sao và có thể được đơn giản hóa như thế nào.
- Mã ứng dụng đang phụ thuộc vào API nội bộ của JDK hay không.
- Những dependency nào không thể được tìm thấy trên class path hoặc module path đang cung cấp cho công cụ.

Trong Java 17, `jdeps` đặc biệt hữu ích khi chuẩn bị chuyển một ứng dụng từ classpath sang module path, viết `module-info.java`, xác định tập module cần có cho runtime tùy biến bằng `jlink` hoặc tìm phụ thuộc vào API nội bộ cần thay thế.

`jdeps` thực hiện **phân tích tĩnh bytecode**. Nó không chạy ứng dụng và không quan sát mọi dependency được nạp động khi chương trình hoạt động. Vì vậy, kết quả là cơ sở để điều tra và thiết kế module; vẫn cần đối chiếu với cách ứng dụng thực tế sử dụng reflection, service loading, resource và plugin.

## 2. Java Platform Module System và dependency

Từ Java 9, JDK được tổ chức thành các module. Ví dụ:

| Module | Nội dung tiêu biểu |
|---|---|
| `java.base` | Các kiểu nền tảng như `String`, `Object`, collection cơ bản, I/O cơ bản và nhiều API cốt lõi. |
| `java.logging` | API logging của Java như `java.util.logging`. |
| `java.sql` | JDBC API. |
| `java.net.http` | HTTP Client API. |
| `java.xml` | XML API. |
| `java.desktop` | AWT, Swing và một số API desktop. |
| `jdk.unsupported` | Một số API nội bộ/không được khuyến nghị sử dụng như `sun.misc.Unsafe` qua module export tương ứng. |

Một module ứng dụng khai báo dependency bằng directive `requires` trong `module-info.java`:

~~~java
module com.example.orders {
    requires java.sql;
    requires java.net.http;
}
~~~

Module `java.base` được yêu cầu ngầm định bởi mọi module Java thông thường; không cần viết `requires java.base` trong descriptor của ứng dụng.

Nếu module sử dụng một API thuộc module khác nhưng không khai báo dependency cần thiết, quá trình biên dịch hoặc phân giải module có thể thất bại. `jdeps` giúp tìm các dependency được bytecode tham chiếu để bạn có cơ sở viết descriptor.

## 3. Chuẩn bị đầu vào cho jdeps

`jdeps` phân tích bytecode đã biên dịch, không phân tích trực tiếp file `.java` như một trình kiểm tra import source.

### 3.1. Kiểm tra công cụ và phiên bản

Mở terminal có JDK 17 trên PATH:

~~~text
java -version
jdeps --version
jdeps --help
~~~

Hãy xác nhận `java` và `jdeps` đến từ cùng một JDK hoặc từ bộ công cụ có phiên bản phù hợp. Nếu dùng nhiều JDK trên máy, gọi công cụ bằng đường dẫn tuyệt đối tới thư mục `bin` của JDK 17.

### 3.2. Phân tích một thư mục class

Giả sử mã nguồn được biên dịch vào thư mục `out`:

~~~text
javac -d out src/com/example/Main.java
jdeps out
~~~

`jdeps` đọc các class file bên trong thư mục đầu vào. Khi dự án có nhiều package hoặc nhiều module, hãy truyền đúng thư mục output tương ứng với phần bytecode muốn phân tích.

### 3.3. Phân tích một JAR

Với ứng dụng đã đóng gói:

~~~text
jdeps app.jar
~~~

Hoặc yêu cầu tóm tắt dependency:

~~~text
jdeps --summary app.jar
~~~

`--summary` cho cái nhìn gọn hơn theo archive/package dependency thay vì liệt kê từng class. Khi điều tra sâu, có thể tăng mức chi tiết.

### 3.4. Phân tích nhiều JAR

Có thể truyền nhiều archive trong cùng lệnh:

~~~text
jdeps app.jar lib/domain.jar lib/client.jar
~~~

Điều này giúp xem các quan hệ giữa những artifact đầu vào. Nếu các JAR phụ thuộc vào nhau nhưng không nằm trong danh sách đầu vào hoặc class path, kết quả có thể báo dependency không tìm thấy. Hãy cung cấp đủ thư viện liên quan để tránh hiểu nhầm kết quả.

## 4. Xem dependency ở cấp package và class

Mức chi tiết cần chọn theo câu hỏi đang điều tra.

### 4.1. Dependency theo package

~~~text
jdeps -verbose:package app.jar
~~~

Kết quả hiển thị quan hệ giữa package nguồn và package đích. Đây là mức phù hợp để hiểu cấu trúc tổng thể, ví dụ package nghiệp vụ đang phụ thuộc vào JDBC, HTTP hoặc logging.

Ví dụ đầu ra minh họa:

~~~text
com.example.orders -> java.lang
com.example.orders -> java.sql
com.example.orders -> java.net.http
com.example.orders -> com.example.domain
~~~

Các dòng trên chỉ minh họa cách đọc, không phải output cố định của một JAR cụ thể.

### 4.2. Dependency theo class

~~~text
jdeps -verbose:class app.jar
~~~

Chế độ class-level cho biết class nào tham chiếu class nào. Nó hữu ích khi một package có nhiều lớp và cần tìm chính xác nơi phát sinh dependency.

Ví dụ minh họa:

~~~text
com.example.orders.OrderClient
  -> java.net.http.HttpClient
  -> java.net.http.HttpRequest
  -> java.net.http.HttpResponse

com.example.orders.OrderRepository
  -> java.sql.Connection
  -> java.sql.PreparedStatement
~~~

Class-level output thường dài hơn đáng kể. Hãy dùng khi package-level output chưa đủ để tìm vị trí cần sửa.

### 4.3. Phân tích API công khai

Tùy chọn `--api-only` giới hạn phân tích vào API public và protected:

~~~text
jdeps --api-only -verbose:package app.jar
~~~

Chế độ này hữu ích khi xem dependency mà thư viện để lộ qua API công khai, chẳng hạn kiểu tham số, kiểu trả về hoặc superclass/interface. Một dependency chỉ xuất hiện trong implementation private có thể không được thể hiện trong kết quả API-only.

Nếu mục tiêu là đóng gói một ứng dụng thực thi, không nên chỉ dựa vào `--api-only` vì dependency trong phần triển khai vẫn có thể cần ở runtime.

## 5. Phân tích đệ quy

Mặc định, `jdeps` phân tích các đầu vào được chỉ định. Để duyệt tiếp dependency của chúng, dùng `--recursive`:

~~~text
jdeps --recursive app.jar
~~~

Có thể kết hợp với summary:

~~~text
jdeps --recursive --summary app.jar
~~~

Phân tích đệ quy giúp khám phá nhiều tầng dependency, nhưng kết quả phụ thuộc vào việc công cụ tìm được các archive và module liên quan. Hãy cung cấp class path hoặc module path phù hợp.

### 5.1. Class path cho thư viện bên ngoài

Nếu ứng dụng phụ thuộc vào các JAR nằm trong thư mục `lib`:

~~~text
jdeps --recursive --class-path "lib/*" app.jar
~~~

`--class-path` (alias `-cp`) chỉ định nơi tìm các class nằm trên classpath. Trên Windows, khi tự liệt kê nhiều đường dẫn classpath bằng dấu phân cách, hệ thống dùng dấu chấm phẩy; wildcard thư mục như `lib/*` thường tiện hơn khi tất cả JAR ở cùng một thư mục.

Nếu bỏ thư viện cần thiết khỏi class path, `jdeps` có thể báo missing dependency hoặc không thể phân tích đầy đủ. Đừng coi danh sách module đầu ra là hoàn chỉnh nếu có cảnh báo dependency không được tìm thấy.

### 5.2. Module path cho module đã đóng gói

Khi các dependency đã là module hoặc automatic module, dùng `--module-path`:

~~~text
jdeps --module-path mods --module com.example.orders
~~~

`--module-path` (alias `-p`) chỉ định đường dẫn chứa module. `--module` (alias `-m`) chọn module cần phân tích.

Với nhiều module, hãy cung cấp toàn bộ module path mà ứng dụng cần để công cụ phân giải graph đúng cách.

## 6. Tìm các module JDK cần thiết

Một nhiệm vụ phổ biến khi đóng gói ứng dụng là xác định module Java Platform mà ứng dụng cần.

### 6.1. Liệt kê dependency module

~~~text
jdeps --list-deps app.jar
~~~

Lệnh này liệt kê module dependency mà `jdeps` suy ra từ bytecode. Ví dụ một ứng dụng dùng JDBC và HTTP Client có thể phụ thuộc vào `java.base`, `java.sql` và `java.net.http`.

Đầu ra cụ thể phụ thuộc class được tham chiếu và dependency có được tìm thấy đầy đủ hay không.

### 6.2. Danh sách dependency đã rút gọn

~~~text
jdeps --list-reduced-deps app.jar
~~~

Tùy chọn này hiển thị dependency module đã rút gọn, loại bỏ những quan hệ đã được hàm ý bởi dependency khác trong graph. Nó giúp nhìn danh sách ngắn hơn khi các module có quan hệ phụ thuộc bắc cầu.

### 6.3. In danh sách module dạng CSV

~~~text
jdeps --print-module-deps app.jar
~~~

`--print-module-deps` in danh sách module phân cách bằng dấu phẩy, phù hợp để đưa vào bước đóng gói runtime tùy biến.

Ví dụ output minh họa:

~~~text
java.base,java.net.http,java.sql
~~~

Không chép ví dụ này cho mọi ứng dụng. Hãy chạy trên artifact thực tế cùng class path đầy đủ, rồi xem cảnh báo missing dependency trước khi sử dụng danh sách.

### 6.4. Kết hợp với jlink

`jlink` tạo runtime image chỉ chứa các module cần thiết. Có thể dùng kết quả của `jdeps --print-module-deps` làm đầu vào cho `--add-modules`:

~~~text
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

Giả sử kết quả là:

~~~text
java.base,java.logging,java.sql
~~~

Sau đó tạo runtime image:

~~~text
jlink --add-modules java.base,java.logging,java.sql --output runtime
~~~

Đây là hai bước riêng: `jdeps` phân tích bytecode và đề xuất module dependency; `jlink` phân giải các module và tạo image. Nếu ứng dụng dùng provider, reflection, resource hoặc module được nạp động mà static analysis không phát hiện, bạn có thể cần thêm module vào danh sách.

## 7. Kiểm tra module descriptor bằng --check

Khi một ứng dụng đã có `module-info.java`, có thể dùng `jdeps --check` để xem dependency và descriptor:

~~~text
jdeps --check com.example.orders --module-path mods
~~~

`--check` phân tích module được chỉ định, hiển thị module descriptor và các dependency. Công cụ cũng có thể đưa ra descriptor được đề xuất hoặc dependency được rút gọn để giúp nhận ra directive `requires` dư thừa hoặc chưa hợp lý.

### 7.1. Ví dụ module descriptor

Giả sử module:

~~~java
module com.example.orders {
    requires java.base;
    requires java.sql;
    requires java.logging;
    requires java.net.http;

    exports com.example.orders.api;
}
~~~

`java.base` là dependency ngầm định nên dòng `requires java.base` không cần thiết trong descriptor thông thường. Các dependency còn lại cần được đối chiếu với bytecode và API mà module sử dụng.

Sau khi đóng gói các module vào thư mục `mods`, chạy:

~~~text
jdeps --check com.example.orders --module-path mods
~~~

Hãy đọc phần descriptor hiện tại, suggested descriptor và dependency graph. Nếu công cụ gợi ý rút gọn `requires`, cần kiểm tra xem dependency đó có đang được module khác cung cấp theo quan hệ bắc cầu hay không và API công khai của module có để lộ kiểu từ module đó không.

### 7.2. Phân biệt requires thường và requires transitive

`jdeps` có thể giúp phát hiện quan hệ dependency, nhưng người thiết kế module vẫn phải quyết định ngữ nghĩa API:

- `requires X`: module hiện tại cần module X để triển khai hoặc biên dịch.
- `requires transitive X`: module hiện tại sử dụng kiểu từ X trong API công khai theo cách khiến module phụ thuộc cần đọc X.
- `requires static X`: dependency cần lúc biên dịch nhưng không nhất thiết cần lúc runtime; chỉ dùng khi đúng hợp đồng và cách sử dụng.

Ví dụ, nếu public method của module trả về `java.sql.Connection`, consumer của module có thể cần đọc module `java.sql` để biên dịch mã sử dụng API đó. Khi thiết kế API module, hãy cân nhắc `requires transitive java.sql` nếu hợp đồng công khai thực sự yêu cầu điều đó.

Không nên biến mọi dependency tìm thấy bởi `jdeps` thành `requires transitive`. Chỉ các dependency cần được truyền tới consumer theo ngữ nghĩa API mới nên dùng directive này.

## 8. Phát hiện dependency vào JDK internal API

Một lý do quan trọng để chạy `jdeps` là tìm việc sử dụng API nội bộ của JDK.

Các package như `sun.*`, `com.sun.*` hoặc những package không được export công khai có thể thay đổi giữa các bản JDK. Phụ thuộc vào chúng làm ứng dụng dễ gặp lỗi khi nâng cấp hoặc khi chạy với module encapsulation.

Chạy:

~~~text
jdeps --jdk-internals app.jar
~~~

Hoặc kết hợp class-level để xem vị trí dependency:

~~~text
jdeps --jdk-internals -verbose:class app.jar
~~~

Ví dụ đầu ra có thể chỉ ra một class đang dùng API nội bộ và gợi ý API thay thế nếu JDK có thông tin tương ứng.

### 8.1. Vì sao nên loại bỏ internal API?

- Internal API không phải hợp đồng tương thích công khai.
- Module system giới hạn quyền truy cập tới package không được export.
- API có thể bị thay đổi hoặc loại bỏ giữa các bản phát hành.
- Việc thêm cờ mở package/module có thể che vấn đề thiết kế và làm cấu hình triển khai phức tạp hơn.

Khi thấy kết quả, hãy tìm API công khai thay thế trong Java SE hoặc thư viện được hỗ trợ. Sau khi sửa, chạy lại `jdeps --jdk-internals` để xác nhận dependency đã biến mất.

### 8.2. Kết quả không phát hiện internal API không phải chứng nhận tuyệt đối

`jdeps` phân tích dependency có thể suy ra từ bytecode. Nếu ứng dụng nạp tên class nội bộ qua chuỗi, reflection, JNI hoặc thư viện runtime, static analysis có thể không nhìn thấy toàn bộ đường đi. Hãy kết hợp kiểm tra source, test trên JDK mục tiêu và theo dõi hành vi thực tế.

## 9. Tìm dependency bị thiếu

Khi thư viện không nằm trong class path/module path, công cụ có thể không giải quyết được một số tham chiếu. Có thể dùng:

~~~text
jdeps --missing-deps app.jar
~~~

Tùy chọn này liệt kê các dependency không tìm thấy trong quá trình phân tích. Để bỏ qua cảnh báo missing dependencies khi chỉ muốn xem phần còn lại, có tùy chọn:

~~~text
jdeps --ignore-missing-deps app.jar
~~~

Hai cách có mục đích khác nhau:

- `--missing-deps` giúp chủ động tìm class/package dependency không được tìm thấy.
- `--ignore-missing-deps` cho phép tiếp tục phân tích mà không dừng vì các dependency thiếu; nó không sửa hoặc cung cấp thư viện còn thiếu.

Không nên dùng `--ignore-missing-deps` để tạo danh sách module cuối cùng cho runtime mà không điều tra cảnh báo. Một dependency bị thiếu có thể khiến danh sách module in ra không đầy đủ.

### 9.1. Kiểm tra class path và module path

Nếu một class thuộc thư viện bên ngoài không được tìm thấy:

1. Xác định JAR chứa class đó.
2. Nếu thư viện nằm trên classpath, thêm vào `--class-path`.
3. Nếu thư viện là module, thêm vào `--module-path`.
4. Chạy lại `--missing-deps` để xem dependency còn thiếu.
5. Chỉ sử dụng kết quả module sau khi dependency quan trọng đã được giải quyết.

`jdeps` không thay thế Maven hoặc Gradle dependency resolution. Công cụ phân tích bytecode dựa trên những artifact và đường dẫn bạn cung cấp; nó không tự tải dependency từ repository.

## 10. Tạo module-info.java cho JAR chưa modular

Một thư viện JAR chưa có `module-info.class` có thể trở thành automatic module khi đặt trên module path. Để bắt đầu chuyển sang explicit module, `jdeps` có thể sinh bản nháp descriptor.

Dùng:

~~~text
jdeps --generate-module-info generated-modules lib/customer-domain.jar
~~~

`jdeps` tạo thư mục chứa `module-info.java` cho module tương ứng. File được sinh là điểm khởi đầu; hãy đọc và chỉnh sửa trước khi dùng chính thức.

### 10.1. Tạo open module descriptor

Nếu cần tạo descriptor với từ khóa `open module`:

~~~text
jdeps --generate-open-module generated-open-modules lib/legacy-model.jar
~~~

Open module mở các package của module cho deep reflection theo ngữ nghĩa module system. Đây là lựa chọn rộng; chỉ dùng khi framework thực sự cần reflection sâu trên nhiều package. Nếu chỉ một số package cần reflection, cân nhắc directive `opens` có mục tiêu cụ thể thay vì mở toàn module.

### 10.2. Vì sao descriptor được sinh cần được xem lại?

`jdeps` có thể suy ra dependency từ bytecode nhưng không hiểu đầy đủ ý định thiết kế:

- Package nào nên `exports` cho consumer.
- Package nào cần `opens` cho framework reflection.
- Service nào module `uses` hoặc `provides`.
- Dependency nào nên là `requires transitive`.
- Dependency nào chỉ cần ở compile time hoặc chỉ trong cấu hình tùy chọn.
- API nào là nội bộ và không nên export.

Do đó, module descriptor được sinh không phải quyết định kiến trúc cuối cùng. Hãy chỉnh sửa theo API và ranh giới module mong muốn.

### 10.3. Quy trình chuyển một JAR thành explicit module

1. Chạy `jdeps --summary` và `jdeps --verbose:class` để hiểu dependency.
2. Dùng `--print-module-deps` để biết các module JDK cần thiết.
3. Chạy `--generate-module-info` để tạo descriptor ban đầu.
4. Chỉnh sửa `module-info.java`: requires, exports, opens, uses và provides.
5. Biên dịch lại JAR với descriptor.
6. Đặt JAR và dependency trên module path.
7. Chạy `jdeps --check` và kiểm thử ứng dụng bằng module path.

## 11. Phân tích Multi-Release JAR

Multi-Release JAR có thể chứa nhiều phiên bản class trong cùng archive, ví dụ class cơ sở và các phiên bản thay thế trong `META-INF/versions/`. Runtime chọn class phù hợp với phiên bản Java đang chạy.

Để phân tích nội dung dành cho một phiên bản cụ thể:

~~~text
jdeps --multi-release 17 app-mr.jar
~~~

`--multi-release` cho phép chỉ định phiên bản cần phân tích trong multi-release JAR. Khi đánh giá ứng dụng cho Java 17, hãy phân tích đúng phiên bản 17 thay vì chỉ xem class cơ sở.

Điều này quan trọng vì phiên bản class trong thư mục `META-INF/versions/17` có thể dùng API/module khác với class cơ sở. Kết quả dependency có thể thay đổi theo phiên bản runtime mục tiêu.

## 12. Xuất đồ thị dependency bằng DOT

Khi dependency graph lớn, output văn bản có thể khó theo dõi. `jdeps` có thể xuất dữ liệu đồ thị để dùng với Graphviz:

~~~text
jdeps --dot-output dot-output app.jar
~~~

Thư mục `dot-output` chứa các file DOT biểu diễn dependency. Có thể dùng Graphviz để render:

~~~text
dot -Tsvg dot-output/summary.dot -o dependency-graph.svg
~~~

Tên file DOT cụ thể phụ thuộc các archive/module được phân tích. Hãy liệt kê nội dung thư mục output trước khi gọi Graphviz.

### 12.1. Khi nào nên dùng đồ thị?

- Xác định package tạo ra dependency vòng hoặc coupling quá chặt.
- Tìm module có quá nhiều dependency trực tiếp.
- Trình bày cấu trúc module cho nhóm phát triển.
- So sánh dependency graph trước và sau khi modularize.

Đồ thị cho biết quan hệ phụ thuộc mà công cụ phát hiện được; nó không tự đánh giá chất lượng thiết kế. Một graph ít cạnh hơn chưa chắc tốt hơn nếu API bị phân mảnh hoặc các dependency bị che bằng reflection.

## 13. Ví dụ quy trình từ JAR đến danh sách module

Giả sử cấu trúc dự án:

~~~text
orders-app/
  app.jar
  lib/
    customer-domain.jar
    reporting-client.jar
~~~

Ứng dụng dùng JDBC, HTTP Client và logging. Ta thực hiện lần lượt:

### Bước 1 — Phân tích package dependency

~~~text
jdeps -verbose:package --class-path "lib/*" app.jar
~~~

Xem package nào của ứng dụng phụ thuộc package nào của thư viện và JDK.

### Bước 2 — Phân tích đệ quy

~~~text
jdeps --recursive --summary --class-path "lib/*" app.jar
~~~

Xem dependency qua nhiều tầng archive. Kiểm tra cảnh báo nếu có thư viện không tìm thấy.

### Bước 3 — In danh sách module JDK

~~~text
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

Lưu danh sách module mà công cụ suy ra. Nếu output có các module ngoài dự kiến, quay lại class-level analysis để xác định class tạo dependency.

### Bước 4 — Tìm internal API

~~~text
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

Nếu có kết quả, tìm API công khai thay thế và sửa thư viện/ứng dụng nếu có thể.

### Bước 5 — Sinh descriptor nếu ứng dụng cần trở thành module

~~~text
jdeps --generate-module-info generated --class-path "lib/*" app.jar
~~~

Xem descriptor được sinh, chỉnh sửa tên module và các directive theo kiến trúc thực tế.

### Bước 6 — Kiểm tra module descriptor

Sau khi biên dịch và đóng gói module vào thư mục `mods`:

~~~text
jdeps --check com.example.orders --module-path "mods;mods/lib"
~~~

Trên Windows, module path nhiều thư mục dùng dấu chấm phẩy; trên Linux/macOS dùng dấu hai chấm. Thay đường dẫn minh họa bằng module path thực tế của dự án.

### Bước 7 — Tạo runtime image

Khi đã xác nhận module dependency, dùng danh sách module phù hợp với `jlink`:

~~~text
jlink --module-path "%JAVA_HOME%/jmods;mods" --add-modules com.example.orders --output runtime
~~~

Đây là ví dụ cho Windows Command Prompt; trên Linux/macOS, dùng cú pháp đường dẫn và biến môi trường tương ứng. `jlink` tự phân giải dependency của module gốc đã chọn trên module path.

## 14. Giới hạn của phân tích tĩnh

`jdeps` rất hữu ích, nhưng không thể suy ra mọi dependency runtime từ bytecode.

### 14.1. Reflection và tên class dạng chuỗi

Ví dụ:

~~~java
String implementation = config.getProperty("handler.class");
Class<?> type = Class.forName(implementation);
~~~

Nếu tên class chỉ có trong file cấu hình hoặc được tạo động, bytecode có thể không chứa một tham chiếu kiểu tĩnh tới class đó. `jdeps` có thể không phát hiện module cần thiết từ đường đi này.

### 14.2. ServiceLoader và provider

Ứng dụng có thể tìm implementation thông qua `ServiceLoader`:

~~~java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class);
~~~

Provider có thể được khai báo trong descriptor bằng `provides ... with ...` hoặc metadata tương ứng. Khi modularize, cần xem cả module cung cấp service và module tiêu thụ service:

~~~java
module com.example.payment.api {
    exports com.example.payment;
}

module com.example.payment.app {
    requires com.example.payment.api;
    uses com.example.payment.PaymentProvider;
}

module com.example.payment.provider {
    requires com.example.payment.api;
    provides com.example.payment.PaymentProvider
            with com.example.payment.provider.DefaultProvider;
}
~~~

Không nên chỉ dựa vào dependency class-level để xác định provider nào phải có mặt trong runtime image.

### 14.3. JNI và thư viện native

Dependency native được nạp qua `System.loadLibrary()` hoặc cơ chế tương tự không nhất thiết được thể hiện như module Java trong bytecode. Cần kiểm tra thư viện native, kiến trúc CPU, hệ điều hành và cấu hình triển khai riêng.

### 14.4. Resource và cấu hình

Ứng dụng có thể đọc resource, file cấu hình, script hoặc template để xác định class/plugin cần nạp. `jdeps` không thay thế việc kiểm tra resource và cấu hình này.

### 14.5. Dependency được nạp bởi framework

Một số framework sử dụng reflection, annotation scanning, classpath scanning hoặc plugin registry. Hãy kiểm tra tài liệu framework và chạy integration test trên module path/runtime image dự kiến.

### 14.6. Phân tích một phiên bản JAR không đại diện mọi runtime

Với multi-release JAR, dependency của class được chọn có thể khác theo phiên bản Java. Dùng `--multi-release` tương ứng với runtime mục tiêu và kiểm tra artifact cuối cùng sẽ triển khai.

## 15. Các tùy chọn jdeps thường dùng

| Tùy chọn | Mục đích |
|---|---|
| `--summary` | Tóm tắt dependency theo archive/package. |
| `-verbose:package` | Hiển thị dependency theo package. |
| `-verbose:class` | Hiển thị dependency theo class. |
| `--recursive` | Duyệt dependency đệ quy. |
| `--class-path` | Cung cấp classpath để phân giải thư viện. |
| `--module-path` | Cung cấp module path. |
| `--module` | Chọn module cần phân tích. |
| `--list-deps` | Liệt kê module dependency. |
| `--list-reduced-deps` | Liệt kê module dependency đã rút gọn. |
| `--print-module-deps` | In module dependency dạng danh sách phân cách bằng dấu phẩy. |
| `--check` | Kiểm tra module descriptor và dependency. |
| `--jdk-internals` | Tìm dependency vào JDK internal API. |
| `--missing-deps` | Liệt kê dependency không tìm thấy. |
| `--ignore-missing-deps` | Bỏ qua missing dependency trong quá trình phân tích. |
| `--generate-module-info` | Sinh module descriptor cho JAR chưa modular. |
| `--generate-open-module` | Sinh open module descriptor. |
| `--multi-release` | Chọn phiên bản của multi-release JAR cần phân tích. |
| `--api-only` | Chỉ phân tích public/protected API. |
| `--dot-output` | Xuất dependency graph dưới dạng DOT. |

Không cần ghi nhớ tất cả tùy chọn. Dùng `jdeps --help` và `jdeps --version` để xem cú pháp trên đúng JDK đang sử dụng.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy class từ thư viện bên ngoài | Thiếu JAR trên classpath hoặc module path. | Bổ sung `--class-path` hoặc `--module-path`. |
| Danh sách module có vẻ thiếu | Dependency động hoặc thư viện chưa được cung cấp. | Kiểm tra missing dependencies, reflection, service provider và resource. |
| Output quá dài | Dùng class-level hoặc recursive trên nhiều JAR. | Bắt đầu với `--summary` hoặc package-level. |
| Không thấy dependency internal API | Dependency được nạp qua reflection/JNI hoặc không nằm trong bytecode đầu vào. | Kết hợp kiểm tra source, config và runtime test. |
| Descriptor sinh ra chưa chạy được | `jdeps` không hiểu đầy đủ ý định exports/opens/uses/provides. | Chỉnh sửa descriptor theo kiến trúc module và kiểm thử. |
| Module path không phân giải được | Thiếu module hoặc tên module không đúng. | Kiểm tra module name, module path và `java --list-modules`. |
| Kết quả thay đổi giữa Java 11 và Java 17 | Multi-release JAR hoặc API/module khác theo phiên bản. | Dùng `--multi-release 17` khi phù hợp và phân tích artifact mục tiêu. |
| `jlink` báo thiếu module | Danh sách module hoặc module path chưa đầy đủ. | Kiểm tra lại dependency và bổ sung module/provider cần thiết. |
| Nghĩ `jdeps` tự tải dependency | Công cụ chỉ phân tích artifact được cung cấp. | Dùng Maven/Gradle để resolve dependency trước. |

## 17. Bài tập thực hành

### Bài tập 1 — Phân tích JAR

Chọn một JAR trong dự án. Chạy `jdeps --summary`, `jdeps -verbose:package` và `jdeps -verbose:class`. So sánh mức chi tiết và xác định package tạo ra dependency tới JDK module.

### Bài tập 2 — In module dependency

Chạy `jdeps --list-deps` và `jdeps --print-module-deps` trên cùng artifact. Ghi lại các module JDK cần thiết và giải thích vì sao output dạng comma-separated hữu ích cho `jlink`.

### Bài tập 3 — Tìm internal API

Chạy `jdeps --jdk-internals` trên ứng dụng và thư viện bên thứ ba. Nếu có kết quả, tìm API công khai thay thế và ghi lại module/package liên quan.

### Bài tập 4 — Kiểm tra missing dependencies

Chạy `jdeps --missing-deps` khi cố ý bỏ một JAR khỏi class path. Sau đó bổ sung JAR bằng `--class-path` và so sánh kết quả.

### Bài tập 5 — Tạo module descriptor

Dùng `--generate-module-info` cho một JAR chưa có module descriptor. Đọc file được sinh, loại bỏ `requires java.base` nếu có, rồi xem xét `exports`, `opens` và `requires transitive` theo API của thư viện.

### Bài tập 6 — Kiểm tra module đã khai báo

Đặt module lên module path và chạy `jdeps --check`. Đọc descriptor hiện tại và suggested descriptor; giải thích dependency nào có thể rút gọn và vì sao.

### Bài tập 7 — Phân tích Multi-Release JAR

Chọn một Multi-Release JAR và chạy phân tích với `--multi-release 17`. So sánh kết quả với phiên bản cơ sở hoặc một target version khác nếu artifact có hỗ trợ.

### Bài tập 8 — Tạo runtime image

Dùng `--print-module-deps` để lấy module list. Tạo runtime image bằng `jlink` và chạy ứng dụng trên image đó. Nếu ứng dụng lỗi do provider hoặc class nạp động, tìm module cần bổ sung và giải thích vì sao static analysis không phát hiện.

## 18. Quy trình sử dụng jdeps trong dự án thực tế

Khi chuẩn bị modularize hoặc tạo runtime image cho ứng dụng Java 17, có thể áp dụng trình tự:

1. **Resolve dependency trước.** Dùng Maven/Gradle để tải và đặt đầy đủ artifact vào thư mục build.
2. **Chọn đúng artifact.** Phân tích class directory hoặc JAR đúng phiên bản sẽ triển khai.
3. **Bắt đầu bằng summary.** Dùng `jdeps --summary` để hiểu cấu trúc tổng quát.
4. **Đi sâu theo package/class.** Dùng `-verbose:package` hoặc `-verbose:class` để tìm nguồn dependency.
5. **Cung cấp đường dẫn thư viện.** Dùng `--class-path` hoặc `--module-path` để phân giải dependency.
6. **Tìm module JDK.** Dùng `--list-deps` và `--print-module-deps`.
7. **Tìm internal API và dependency thiếu.** Dùng `--jdk-internals` và `--missing-deps`.
8. **Sinh hoặc kiểm tra descriptor.** Dùng `--generate-module-info` cho JAR chưa modular và `--check` cho module đã có descriptor.
9. **Đối chiếu dependency động.** Kiểm tra reflection, ServiceLoader, JNI, resource và framework plugin.
10. **Tạo runtime image và kiểm thử.** Dùng `jlink` với module path đầy đủ, sau đó chạy integration test trên image cuối cùng.

`jdeps` giúp giảm phỏng đoán khi thiết kế module. Kết quả tốt nhất đến từ việc kết hợp phân tích bytecode với hiểu biết về API công khai, cấu hình runtime và cách ứng dụng thực sự nạp thành phần.

## 19. Các nguyên tắc cần ghi nhớ

- `jdeps` phân tích dependency tĩnh từ class file, JAR, thư mục và module; nó không chạy ứng dụng.
- `--summary` cho góc nhìn tổng quát; `-verbose:package` và `-verbose:class` giúp truy vết chi tiết hơn.
- `--recursive` duyệt nhiều tầng dependency; cần cung cấp class path/module path đầy đủ.
- `--list-deps`, `--list-reduced-deps` và `--print-module-deps` giúp xác định module cần thiết cho runtime.
- `--print-module-deps` tạo danh sách module phân cách bằng dấu phẩy, có thể dùng làm đầu vào cho `jlink --add-modules`.
- `--check` giúp kiểm tra descriptor và dependency của module.
- `--jdk-internals` tìm việc sử dụng JDK internal API cần xem xét thay thế.
- `--generate-module-info` tạo descriptor ban đầu; cần xem lại requires, exports, opens, uses và provides trước khi dùng.
- `--multi-release` cho phép phân tích đúng lớp được chọn trong Multi-Release JAR.
- `--missing-deps` giúp tìm dependency không được giải quyết; `--ignore-missing-deps` chỉ bỏ qua cảnh báo, không bổ sung thư viện.
- Phân tích tĩnh có thể bỏ sót dependency qua reflection, tên class dạng chuỗi, ServiceLoader, JNI, resource và plugin.
- `jdeps` không thay thế Maven/Gradle dependency resolution, kiểm thử runtime hoặc thiết kế module.
- Chỉ tạo runtime image sau khi đã kiểm tra dependency động và thử chạy ứng dụng trên image mục tiêu.

### Tài liệu tham khảo

- [Oracle Java 17 — jdeps Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html).
- [Oracle Java 17 — Java Platform Module System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html).
- [Oracle Java 17 — jlink Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).
