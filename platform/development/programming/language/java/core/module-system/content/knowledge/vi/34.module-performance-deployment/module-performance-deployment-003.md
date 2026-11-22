# jlink image và thời gian khởi động

## 1. Mục tiêu

Một ứng dụng Java modular thường chạy trên một JDK hoặc JRE có nhiều module hơn mức ứng dụng thực sự cần. Khi triển khai, ta có thể tạo một **custom runtime image** chỉ chứa runtime module cần thiết cùng ứng dụng và dependency của nó. Công cụ `jlink` thực hiện việc liên kết này.

Custom image giúp đóng gói runtime nhất quán với ứng dụng, giảm dung lượng phân phối và có thể giảm thời gian khởi động trong một số môi trường. Tuy nhiên, image nhỏ hơn không tự động đồng nghĩa ứng dụng khởi động nhanh hơn: thời gian khởi động còn phụ thuộc class loading, khởi tạo framework, I/O, JIT, cấu hình JVM và công việc mà ứng dụng thực hiện.

Bài này hướng dẫn tạo image bằng `jlink`, xác định module cần đưa vào, cấu hình launcher và đánh giá tác động tới startup bằng phép đo có kiểm soát.

Sau bài này, bạn có thể:

- Giải thích custom runtime image và vai trò của `jlink`.
- Xác định module roots cùng dependency cần đóng gói.
- Tạo image có launcher riêng cho ứng dụng.
- Chọn các tùy chọn giảm kích thước và hiểu trade-off.
- Chạy ứng dụng bằng runtime image mà không phụ thuộc JDK cài trên máy đích.
- Đo cold startup và warm startup để đánh giá kết quả thực tế.

## 2. jlink tạo ra những gì?

`jlink` kết hợp các module đã biên dịch thành một runtime image có thể chạy độc lập. Image thường có cấu trúc tương tự:

~~~text
app-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── legal/
├── lib/
└── release
~~~

Cấu trúc và file cụ thể thay đổi theo hệ điều hành và JDK. Thư mục `bin` chứa launcher runtime và launcher ứng dụng nếu đã khai báo; các thư mục còn lại chứa cấu hình, thư viện runtime, thông tin pháp lý và metadata.

Image có thể được chuyển tới máy đích cùng hệ điều hành và kiến trúc tương thích. Máy đích không cần cài một JDK đầy đủ riêng để chạy ứng dụng từ image này.

Điều quan trọng là `jlink` làm việc với **named modules**. Các module đầu vào phải có thể được phân giải từ runtime modules và module path. Một thư viện chỉ có trên classpath hoặc một automatic module không thể được đưa trực tiếp vào linked image như một named module thông thường. Cần modularize, thay thế hoặc đóng gói dependency đó theo kiến trúc phù hợp trước khi link.

## 3. Chuẩn bị module cho ứng dụng

Giả sử có ứng dụng gồm hai module:

- `com.example.app`: module chứa main class.
- `com.example.greeting`: module cung cấp API mà app sử dụng.

Cấu trúc sau khi biên dịch:

~~~text
project/
├── mods/
│   ├── com.example.app.jar
│   └── com.example.greeting.jar
└── app-image/
~~~

Module ứng dụng:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

Module greeting:

~~~java
module com.example.greeting {
    exports com.example.greeting;
}
~~~

Main class:

~~~java
package com.example.app;

import com.example.greeting.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Trước khi link, cần bảo đảm tất cả dependency mà ứng dụng cần đều có thể được tìm thấy. Nếu module app dùng JDBC, logging, XML hoặc service khác, module tương ứng phải nằm trong dependency closure hoặc được thêm làm root theo yêu cầu thực tế.

Có thể dùng `jar --describe-module --file` để xem descriptor của từng modular JAR:

~~~bash
jar --describe-module --file mods/com.example.app.jar
~~~

Cần xác nhận module name, `requires`, `exports`, `uses` và `provides` phù hợp với cấu hình mong đợi.

## 4. Xác định module cần link

Tham số quan trọng nhất là `--add-modules`. Nó chỉ định root module; `jlink` sẽ giải quyết các dependency cần thiết của các root đó.

Ví dụ:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --output app-image
~~~

Giải thích:

- `--module-path`: nơi tìm các module đầu vào. Ví dụ gồm thư mục `jmods` của JDK và thư mục chứa modular JAR của ứng dụng.
- `--add-modules com.example.app`: chọn app làm root module để link.
- `--output app-image`: thư mục đích của runtime image.

Trên Windows PowerShell, path-list dùng dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
~~~

Trên Linux/macOS, path-list thường dùng dấu hai chấm:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output app-image
~~~

Đường dẫn `$JAVA_HOME/jmods` phải thuộc JDK tương thích với công cụ `jlink` đang chạy. Không nên trộn các module runtime từ những JDK release khác nhau.

### Tìm module dependency bằng jdeps

`jdeps` phân tích dependency tĩnh của class hoặc module và có thể gợi ý danh sách module cần thiết:

~~~bash
jdeps --print-module-deps --module-path mods --module com.example.app
~~~

Kết quả là danh sách module dependency có thể dùng làm đầu vào để xem xét cho `--add-modules`. Hãy đọc và xác nhận danh sách trước khi link.

Phân tích tĩnh không thể luôn phát hiện dependency được nạp qua reflection, tên class cấu hình trong file, JNI hoặc plugin được khám phá động. Nếu ứng dụng có các cơ chế này, hãy kiểm tra cấu hình thực tế và bổ sung module cần thiết bằng `--add-modules`.

## 5. Thêm service provider khi cần

Nếu ứng dụng sử dụng `ServiceLoader`, provider module phải được đưa vào runtime image để ứng dụng tìm thấy implementation khi chạy.

Có thể dùng:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --bind-services \
    --output app-image
~~~

`--bind-services` yêu cầu linker liên kết các service provider module phù hợp với service được các module đã chọn sử dụng, cùng dependency cần thiết của chúng. Tùy chọn này hữu ích khi provider không phải dependency `requires` trực tiếp của app.

Không phải ứng dụng nào cũng cần `--bind-services`. Nếu không dùng service binding hoặc provider đã được đưa vào graph bằng cách khác, hãy chọn tùy chọn theo cấu trúc ứng dụng. Sau khi link, nên chạy kiểm thử chức năng cho từng service để xác nhận provider thực sự có mặt.

## 6. Tạo launcher riêng cho ứng dụng

Có thể tạo launcher mang tên ứng dụng ngay trong image:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --launcher app=com.example.app/com.example.app.Main \
    --output app-image
~~~

Cú pháp:

~~~text
--launcher <launcher-name>=<module-name>/<main-class>
~~~

Sau khi tạo image, có thể chạy launcher:

Trên Linux/macOS:

~~~bash
./app-image/bin/app
~~~

Trên Windows:

~~~powershell
.\app-image\bin\app.bat
~~~

Launcher được tạo từ module và main class đã chỉ định. Có thể truyền thêm đối số ứng dụng sau tên launcher:

~~~bash
./app-image/bin/app --config config/app.yml
~~~

Cách này giúp người vận hành chạy ứng dụng bằng một lệnh rõ ràng mà không cần nhớ module name và main class.

## 7. Giảm kích thước runtime image

`jlink` cung cấp nhiều tùy chọn để giảm kích thước image. Ví dụ:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --compress=2 \
    --output app-image
~~~

Các tùy chọn:

| Tùy chọn | Tác dụng | Trade-off cần cân nhắc |
| --- | --- | --- |
| `--strip-debug` | Loại bỏ thông tin debug khỏi class file. | Có thể làm việc debug, phân tích stack và công cụ cần metadata kém thuận tiện hơn. |
| `--no-header-files` | Bỏ header file dùng cho native development. | Không phù hợp nếu image cần cung cấp header cho quy trình biên dịch native. |
| `--no-man-pages` | Bỏ man page của runtime. | Người vận hành không có tài liệu man page trong image. |
| `--compress=2` | Nén resource trong image ở mức cao hơn. | Có thể tăng chi phí giải nén/đọc resource và không nhất thiết cải thiện startup. |

Các giá trị nén được hỗ trợ và hành vi chi tiết phụ thuộc phiên bản JDK. Kiểm tra `jlink --help` của đúng JDK dùng để build trước khi chọn mức nén.

Không nên bật mọi tùy chọn giảm kích thước theo thói quen. Hãy xác định image có cần header, man page, debug metadata hay resource được truy cập thường xuyên không. Kích thước image là một chỉ số triển khai; nó không phải thước đo trực tiếp của hiệu năng ứng dụng.

## 8. Chạy và kiểm tra runtime image

Sau khi link xong, dùng chính runtime trong image để chạy:

~~~bash
./app-image/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
.\app-image\bin\java.exe --list-modules
~~~

Danh sách này cho thấy module có trong custom runtime image. Có thể kiểm tra launcher app:

~~~bash
./app-image/bin/app
~~~

Nếu image chạy lỗi do thiếu module hoặc service, hãy kiểm tra lại module roots, dependency, module path đầu vào và tùy chọn `--bind-services`. Đừng mặc định rằng lệnh link thành công đã chứng minh mọi luồng chạy đều hoạt động.

Nên chạy kiểm thử trên môi trường sạch tương tự máy đích, không dựa vào các JAR hoặc JDK module có sẵn trên máy phát triển. Điều này giúp phát hiện trường hợp ứng dụng vô tình phụ thuộc vào môi trường build.

## 9. jlink ảnh hưởng đến thời gian khởi động như thế nào?

Custom runtime image có thể ảnh hưởng tới startup theo một số cách:

- **Ít module và resource hơn:** có thể giảm lượng dữ liệu runtime cần phân phối và một số công việc khởi tạo liên quan đến module không được đóng gói.
- **Ít file hơn:** có thể giảm I/O hoặc chi phí dò tìm trong một số môi trường triển khai.
- **Nén resource:** giảm kích thước image nhưng có thể thêm chi phí giải nén khi resource được đọc.
- **Khởi tạo ứng dụng:** thời gian tạo Spring context, kết nối database, nạp cấu hình, scan classpath/module path và chạy code khởi động thường chiếm phần đáng kể. `jlink` không tự loại bỏ các công việc này.
- **JIT và warm-up:** lần chạy đầu có thể khác các lần chạy sau do JVM biên dịch code nóng và hệ điều hành có cache.

Do đó, kết quả phụ thuộc workload và môi trường. Một image nhỏ hơn có thể giúp tải xuống và khởi tạo môi trường nhanh hơn nhưng thời gian từ lúc chạy lệnh tới lúc ứng dụng sẵn sàng vẫn có thể gần như không đổi nếu phần lớn thời gian nằm ở application initialization hoặc kết nối bên ngoài.

Nếu mục tiêu là startup latency thấp, hãy đo ứng dụng thực tế và xác định phần thời gian bị chi phối bởi runtime hay bởi logic khởi tạo của ứng dụng.

## 10. Đo cold startup và warm startup

Một phép đo có ý nghĩa phải định nghĩa rõ điểm bắt đầu và điểm kết thúc.

Ví dụ, với ứng dụng CLI kết thúc ngay sau khi in kết quả, có thể đo thời gian process:

Trên Linux/macOS:

~~~bash
time ./app-image/bin/app
~~~

Trên Windows PowerShell:

~~~powershell
Measure-Command { & ".\app-image\bin\app.bat" }
~~~

Với server, thời điểm process bắt đầu chưa phải thời điểm server sẵn sàng. Nên đo từ lúc launch đến khi health endpoint trả về trạng thái ready hoặc log phát ra tín hiệu readiness có ý nghĩa.

Để so sánh JDK đầy đủ và custom image:

1. Build cùng một phiên bản ứng dụng, cùng cấu hình và cùng dependency.
2. Dùng cùng JDK release, JVM flags, máy, CPU quota, memory limit và điều kiện môi trường.
3. Định nghĩa một mốc readiness giống nhau cho cả hai cách chạy.
4. Chạy nhiều lần, ghi từng kết quả và so sánh median cùng các percentile phù hợp.
5. Tách lần chạy cold process khỏi warm process; nếu cần đo cold OS cache, phải kiểm soát cache và môi trường riêng.
6. Giữ nguyên các dịch vụ ngoài như database, DNS và network để tránh so sánh hai điều kiện khác nhau.
7. Đo đồng thời kích thước image, thời gian tải/phân phối và startup latency.

Không dùng một lần chạy duy nhất làm kết luận. Kết quả có thể bị nhiễu bởi antivirus, filesystem cache, CPU scheduling, container startup, network và trạng thái máy.

Với server, nên ghi timestamp tại ít nhất hai mốc: process start và application ready. Nếu cần phân tích sâu hơn, thêm mốc sau khi module/lớp chính được nạp, sau khi framework context khởi tạo và sau khi kết nối dependency ngoài hoàn tất.

## 11. Khi startup vẫn chậm

Nếu custom image đã nhỏ nhưng ứng dụng vẫn khởi động chậm, hãy điều tra công việc thực tế trong startup path:

- Giảm scan package/class không cần thiết và tránh nạp plugin không dùng.
- Trì hoãn khởi tạo component chỉ dùng ở một số request.
- Giảm số kết nối hoặc truy vấn đồng bộ được thực hiện trước readiness.
- Tránh gọi network hoặc đọc file lớn trong static initializer.
- Đo thời gian khởi tạo framework và từng bean/service quan trọng.
- Kiểm tra logging, DNS, TLS handshake và database connection pool.
- Xem xét Class Data Sharing (CDS) nếu phù hợp với JDK, nền tảng và cách đóng gói. CDS là cơ chế riêng cần cấu hình và đo riêng; nó không tự được bật chỉ vì đã dùng `jlink`.

Không tối ưu bằng cách bỏ module mà ứng dụng vẫn cần. Một image nhỏ nhưng thiếu module sẽ không thể chạy đúng; một image có đủ module nhưng startup chậm vẫn cần profiling ở tầng ứng dụng.

## 12. Quy trình triển khai đề xuất

1. Build các named module và dependency thành artifact có descriptor hợp lệ.
2. Dùng `jdeps` để gợi ý dependency tĩnh; rà soát thêm reflection, JNI, plugin và service loading.
3. Chọn module root bằng `--add-modules`; thêm `--bind-services` nếu cần liên kết provider.
4. Chạy `jlink` với module path chứa JDK modules và application modules.
5. Thêm launcher bằng `--launcher` và chỉ bật các tùy chọn giảm kích thước phù hợp.
6. Kiểm tra danh sách module của image và chạy test trên môi trường sạch.
7. Đo startup theo readiness marker, lặp nhiều lần và so sánh với baseline.
8. Lưu lệnh link, JDK version, module roots, checksum image và kết quả benchmark cùng artifact phát hành.

Ví dụ lệnh tổng hợp:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --bind-services \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --compress=2 \
    --launcher app=com.example.app/com.example.app.Main \
    --output app-image
~~~

Đây là cấu hình minh họa. Chọn module, service binding và tùy chọn nén theo dependency và yêu cầu thực tế của ứng dụng.

## 13. Ghi nhớ

- `jlink` tạo custom runtime image từ named modules và dependency đã được resolve.
- `--module-path` chỉ nơi tìm JDK modules và application modules; `--add-modules` chọn root module.
- `--bind-services` giúp đưa service provider phù hợp vào image khi ứng dụng dùng ServiceLoader.
- `--launcher` tạo lệnh chạy ứng dụng trong image.
- `--strip-debug`, `--no-header-files`, `--no-man-pages` và `--compress` có thể giảm kích thước nhưng có trade-off.
- Image nhỏ hơn không bảo đảm startup nhanh hơn; phải đo cold/warm startup và thời điểm application ready.
- Nếu startup vẫn chậm, profiling application initialization, I/O, network và framework thường cho biết nguyên nhân cụ thể hơn.
- Kiểm thử image trên môi trường sạch tương tự production trước khi phát hành.

Hãy dùng `jlink` để tạo runtime gọn và có thể tái lập, sau đó dùng benchmark trên chính ứng dụng để quyết định cấu hình nào thực sự cải thiện thời gian triển khai và khởi động.
