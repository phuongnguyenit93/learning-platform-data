# --upgrade-module-path thay module hệ thống

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao Java có tùy chọn --upgrade-module-path, phân biệt upgrade module path với application module path, thay thế một system module có thể nâng cấp bằng bản modular JAR riêng, và nhận biết giới hạn của cơ chế này khi so sánh với --patch-module.

## 1. Bối cảnh: module hệ thống trong runtime image

Từ Java 9, JDK được tổ chức thành các module. Các module nền tảng như java.base, java.logging, java.sql, java.xml và nhiều module jdk.* được đóng gói trong runtime image của JDK.

Khi khởi động JVM, Java sử dụng các module hệ thống có sẵn trong runtime image để phân giải các dependency nền tảng. Ứng dụng có thể bổ sung module của mình bằng --module-path, nhưng đôi khi cần thay thế implementation của một module hệ thống bằng phiên bản khác.

Ví dụ, một môi trường triển khai có thể cần dùng bản cập nhật của một module thư viện trong JDK trước khi chuyển toàn bộ ứng dụng sang một JDK mới hơn. Trong trường hợp module đó được phép nâng cấp, Java cung cấp tùy chọn:

~~~bash
--upgrade-module-path <module-path>
~~~

Tùy chọn này chỉ định nơi Java tìm các phiên bản thay thế của những module hệ thống có thể nâng cấp. Module tìm được trên upgrade module path sẽ được ưu tiên thay cho module cùng tên trong runtime image.

Đây là cơ chế thay module ở cấp JPMS. Nó không thay toàn bộ JDK, không thay runtime image trên đĩa và không tự động thay mọi module trong hệ thống.

## 2. Upgrade module path hoạt động như thế nào?

Có thể hình dung quá trình phân giải như sau:

1. Runtime image cung cấp các module hệ thống của JDK.
2. Upgrade module path được kiểm tra để tìm các module hệ thống có thể nâng cấp.
3. Nếu đường dẫn nâng cấp chứa module cùng tên với một module hệ thống có thể nâng cấp, phiên bản trên upgrade module path được dùng thay thế.
4. Các module ứng dụng vẫn được tìm từ application module path được chỉ định bằng --module-path.
5. Module graph được phân giải dựa trên các module được chọn và quan hệ requires của chúng.

Ví dụ, JDK hiện tại cung cấp module java.xml. Nếu upgrade module path chứa một explicit module có tên java.xml, runtime có thể sử dụng module đó thay cho module java.xml có sẵn trong runtime image.

Tên module là yếu tố quyết định việc thay thế. Một JAR tên custom-xml.jar nhưng descriptor khai báo module com.acme.xml không thay thế java.xml. Ngược lại, file JAR có tên tùy ý nhưng descriptor khai báo đúng tên module hệ thống có thể nâng cấp thì được nhận diện theo tên module trong descriptor.

## 3. Phân biệt ba đường dẫn module thường gặp

| Tùy chọn | Vai trò |
|---|---|
| --module-path | Tìm các module ứng dụng hoặc thư viện mà ứng dụng cần sử dụng |
| --upgrade-module-path | Cung cấp phiên bản thay thế cho module hệ thống có thể nâng cấp trong runtime image |
| --system | Chỉ định runtime image/JDK dùng làm nguồn module hệ thống khi biên dịch bằng javac |

Ba tùy chọn này không thể thay thế lẫn nhau.

Ví dụ:

- com.acme.app nằm trên --module-path vì đây là module của ứng dụng.
- Bản thay thế của java.xml nằm trên --upgrade-module-path vì nó thay một module hệ thống có sẵn.
- Các module nền tảng còn lại tiếp tục đến từ runtime image của JDK đang chạy.

Nếu chỉ đưa một JAR thay thế vào --module-path, Java sẽ xem nó như một module ứng dụng hoặc thư viện thông thường. Đặt JAR vào --upgrade-module-path mới thể hiện ý định thay thế module hệ thống cùng tên.

## 4. Cấu trúc thư mục ví dụ

Giả sử ta có một ứng dụng modular và một bản thay thế cho module hệ thống:

~~~text
deployment/
  app-modules/
    com.acme.report.jar

  upgrade-modules/
    java.xml.jar
~~~

Trong ví dụ này:

- com.acme.report.jar là module ứng dụng.
- java.xml.jar là explicit modular JAR chứa module descriptor khai báo tên module java.xml.
- Các module hệ thống khác vẫn được cung cấp bởi JDK đang sử dụng.

Tên file java.xml.jar chỉ giúp người vận hành dễ nhận biết. Điều quan trọng là module-info.class bên trong JAR phải khai báo đúng tên java.xml và cấu trúc module phải hợp lệ.

Có thể kiểm tra descriptor của bản thay thế bằng:

~~~bash
jar --describe-module --file deployment/upgrade-modules/java.xml.jar
~~~

Kết quả cần xác nhận tên module là java.xml, đồng thời cho biết các requires, exports và những chỉ thị module khác mà bản thay thế khai báo.

Không nên đóng gói một thư viện JAR thông thường rồi chỉ đổi tên file thành java.xml.jar. Một module trên upgrade module path cần có descriptor module phù hợp để Java nhận diện đúng module cần nâng cấp.

## 5. Chạy ứng dụng với module thay thế

Dùng java launcher:

~~~bash
java \
    --upgrade-module-path deployment/upgrade-modules \
    --module-path deployment/app-modules \
    --module com.acme.report/com.acme.report.Main
~~~

Ý nghĩa:

- --upgrade-module-path chỉ định thư mục chứa module thay thế.
- --module-path chỉ định thư mục chứa module ứng dụng.
- --module chọn module và main class cần chạy.

Trên Windows, dấu phân tách nhiều mục trong một module path là dấu chấm phẩy; trên Linux và macOS là dấu hai chấm. Trong ví dụ trên mỗi tùy chọn nhận một thư mục nên không cần ghép nhiều mục.

Khi khởi chạy, Java phân giải com.acme.report cùng dependency của nó. Nếu module graph yêu cầu java.xml, runtime sử dụng phiên bản được tìm thấy trên upgrade module path thay cho phiên bản java.xml trong runtime image, miễn là module đó thuộc nhóm được phép nâng cấp và bản thay thế phân giải hợp lệ.

Nếu upgrade module path không chứa module thay thế tương ứng, Java tiếp tục sử dụng module có sẵn trong runtime image.

## 6. Module nào có thể được nâng cấp?

Không phải mọi thành phần của runtime đều có thể được thay bằng tùy chọn này. Module java.base là module nền tảng đặc biệt và không thể được nâng cấp bằng --upgrade-module-path.

Với các module hệ thống khác, khả năng nâng cấp phụ thuộc vào quy tắc của runtime/JDK đang dùng. Hãy kiểm tra tài liệu của đúng phiên bản JDK mục tiêu trước khi triển khai một module thay thế.

Bản thay thế cần đáp ứng các điều kiện cơ bản:

- Là một module hợp lệ mà Java có thể tìm thấy trên upgrade module path.
- Khai báo cùng tên module với module hệ thống cần thay.
- Có các dependency có thể phân giải trong module graph.
- Cung cấp các package và kiểu mà những module phụ thuộc mong đợi.
- Tương thích với runtime và các module còn lại trong JDK đang chạy.

JPMS kiểm soát tên module, khả năng đọc module và quyền truy cập package. Nó không bảo đảm API nhị phân của bản thay thế tương thích với mọi ứng dụng. Nếu bản mới bỏ một lớp hoặc phương thức mà ứng dụng đang dùng, ứng dụng vẫn có thể lỗi khi liên kết hoặc chạy.

Không nên giả định một module thay thế được biên dịch trên JDK mới hơn sẽ luôn chạy được trên mọi JDK cũ hơn. Hãy xây dựng và kiểm tra artifact trên phiên bản nền tảng được hỗ trợ.

## 7. Kiểm tra module đang được phân giải

Có thể dùng các lệnh của JDK để xem module hệ thống và descriptor:

~~~bash
java --list-modules
~~~

Lệnh này liệt kê các module có trong runtime đang được sử dụng. Nó hữu ích để xác định tên module và phiên bản module mà JDK cung cấp.

Xem descriptor của module trong JDK:

~~~bash
java --describe-module java.xml
~~~

Để kiểm tra file JAR thay thế trước khi chạy, dùng:

~~~bash
jar --describe-module --file deployment/upgrade-modules/java.xml.jar
~~~

Khi cần quan sát module graph hoặc tìm nguyên nhân một module không được phân giải, có thể bật log module:

~~~bash
java -Xlog:module+load=info \
     --upgrade-module-path deployment/upgrade-modules \
     --module-path deployment/app-modules \
     --module com.acme.report/com.acme.report.Main
~~~

Các tag log có thể khác nhau giữa các phiên bản JDK. Nếu tag không được runtime hỗ trợ, xem danh sách tag bằng -Xlog:help rồi chọn tag phù hợp.

## 8. Phân biệt --upgrade-module-path với --patch-module

Hai tùy chọn đều tác động đến nội dung module, nhưng cách hoạt động khác nhau:

| Tiêu chí | --upgrade-module-path | --patch-module |
|---|---|---|
| Mục đích | Thay module hệ thống có thể nâng cấp bằng module cùng tên | Bổ sung hoặc thay thế class/resource trong một module đã tồn tại |
| Artifact | Module thay thế có descriptor riêng | Các class/resource được đưa vào module đích |
| Module descriptor | Dùng descriptor của module thay thế | Không thay module descriptor hiện có |
| Phạm vi | Module hệ thống có thể nâng cấp | Module được chỉ định để patch |
| Trường hợp thường gặp | Thử nghiệm hoặc triển khai phiên bản mới của module hệ thống | Test, instrumentation hoặc thêm lớp vào module hiện hữu |

Ví dụ patch module java.base bằng một thư mục class đã biên dịch:

~~~bash
java \
    --patch-module java.base=build/patches/java.base \
    --module-path app-modules \
    --module com.acme.app/com.acme.app.Main
~~~

Đường dẫn sau dấu bằng là nội dung bổ sung cho module đích. Patch không thay descriptor của module, không tạo một module mới và không tự thay các chỉ thị requires, exports hay opens.

Ngược lại, --upgrade-module-path cung cấp một module thay thế hoàn chỉnh có tên tương ứng. Hãy chọn patch khi cần bổ sung hoặc thay một số lớp trong module hiện hữu; chọn upgrade path khi cần cung cấp phiên bản module thay thế theo cơ chế JPMS.

## 9. Phân biệt với --add-exports và --add-opens

Một số lỗi runtime liên quan đến module bị đóng gói thường khiến người học nhầm --upgrade-module-path với các tùy chọn mở quyền truy cập.

- --add-exports mở một package cho module đích truy cập các kiểu public trong package đó.
- --add-opens mở package cho reflective access sâu tại runtime.
- --upgrade-module-path chọn một implementation module khác cho module hệ thống có thể nâng cấp.

Ví dụ:

~~~bash
java \
    --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
    -jar legacy-app.jar
~~~

Lệnh này mở package sun.nio.ch của java.base cho unnamed module. Nó không thay module java.base và cũng không cập nhật implementation của module đó.

Nếu ứng dụng cần truy cập package nội bộ, hãy xử lý quyền truy cập bằng tùy chọn exports/opens phù hợp. Nếu cần thay implementation của một module hệ thống có thể nâng cấp, hãy xem xét upgrade module path.

## 10. Dùng --upgrade-module-path khi biên dịch

Javac cũng có tùy chọn --upgrade-module-path để chỉ định module thay thế khi phân giải các module hệ thống trong quá trình biên dịch.

Ví dụ:

~~~bash
javac \
    --upgrade-module-path upgrade-modules \
    --module-path app-dependencies \
    -d build/classes \
    --module-source-path src \
    -m com.acme.report
~~~

Ở đây:

- --upgrade-module-path cho javac biết nơi tìm phiên bản thay thế của module hệ thống có thể nâng cấp.
- --module-path cung cấp các module dependency của ứng dụng.
- --module-source-path chỉ định cấu trúc source theo module.
- -m chọn module cần biên dịch.

Nếu biên dịch với một phiên bản java.xml thay thế nhưng chạy bằng JDK không có cùng artifact trên upgrade module path, môi trường compile và runtime có thể khác nhau. Hãy đồng bộ cấu hình hai giai đoạn để tránh biên dịch thành công nhưng chạy lỗi do API/module được chọn khác nhau.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Module thay thế không được chọn | Đặt JAR trên --module-path thay vì --upgrade-module-path | Đặt artifact vào đúng upgrade module path |
| Module không thay thế được system module | Tên trong module descriptor không trùng tên module cần thay | Dùng jar --describe-module để kiểm tra module name |
| Không thể nâng cấp java.base | java.base là module nền tảng không upgrade được | Không dùng upgrade path để thay java.base |
| FindException hoặc ResolutionException | Module thay thế hoặc dependency của nó không thể phân giải | Kiểm tra descriptor, requires và các đường dẫn module |
| NoSuchMethodError hoặc NoClassDefFoundError | Bản thay thế không tương thích với module/ứng dụng đang dùng | Kiểm tra API và binary compatibility |
| Compile thành công nhưng runtime lỗi | Javac và java sử dụng các module thay thế hoặc phiên bản JDK khác nhau | Đồng bộ upgrade module path ở cả compile và runtime |
| Lỗi truy cập package nội bộ vẫn còn | Upgrade path không tự mở package hoặc cấp quyền reflective access | Xem xét --add-exports hoặc --add-opens nếu đúng nhu cầu |

Khi chẩn đoán, hãy kiểm tra theo thứ tự: module name của artifact, đường dẫn được truyền vào launcher/compiler, khả năng nâng cấp của module đích, dependency trong descriptor và tính tương thích API. Chỉ kiểm tra tên file JAR là chưa đủ.

## 12. Khi nào nên dùng tùy chọn này?

--upgrade-module-path hữu ích khi cần thử nghiệm hoặc triển khai một bản thay thế của module hệ thống được phép nâng cấp mà không thay toàn bộ JDK runtime image.

Trước khi dùng trong môi trường production, cần kiểm tra:

- Module đích có thuộc nhóm upgradeable của JDK đang chạy không.
- Artifact thay thế có đúng module name và descriptor hợp lệ không.
- Dependency của module có thể phân giải không.
- API của bản thay thế có tương thích với ứng dụng và các module khác không.
- Cấu hình lúc compile và runtime có nhất quán không.
- Môi trường triển khai có sử dụng đúng JDK và đúng upgrade module path đã kiểm thử không.

Nếu mục tiêu chỉ là thêm một module ứng dụng mới, hãy dùng --module-path. Nếu mục tiêu chỉ là thêm hoặc thay một số class trong module hiện hữu, hãy xem xét --patch-module. Nếu cần thay module hệ thống có thể nâng cấp bằng một module cùng tên, --upgrade-module-path là tùy chọn tương ứng.

## Ghi nhớ

--upgrade-module-path cung cấp các module thay thế cho module hệ thống có thể nâng cấp trong runtime image. Java dùng module cùng tên trên đường dẫn này thay cho module tương ứng trong JDK; java.base là ngoại lệ không thể nâng cấp. --module-path dành cho module ứng dụng, còn --patch-module bổ sung hoặc thay class/resource trong module hiện có mà không thay descriptor. Khi dùng upgrade path, hãy kiểm tra module name, dependency, khả năng tương thích và bảo đảm cấu hình compile/runtime đồng nhất.