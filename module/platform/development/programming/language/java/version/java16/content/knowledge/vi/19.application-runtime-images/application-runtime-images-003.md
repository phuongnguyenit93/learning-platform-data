# Dùng jdeps --print-module-deps để lập danh sách module khởi đầu

## 1. Vì sao cần phân tích module trước khi dùng jlink?

Khi tạo runtime image bằng jlink, bạn phải chọn các module gốc cần có trong runtime. jlink sẽ giải quyết các quan hệ requires và đưa những module phụ thuộc cần thiết vào image. Nếu chọn thiếu module mà ứng dụng cần, ứng dụng có thể khởi động được nhưng lỗi khi chạy một chức năng cụ thể.

jdeps là công cụ phân tích phụ thuộc có trong JDK. Tùy chọn --print-module-deps in ra danh sách tên module phân cách bằng dấu phẩy. Danh sách này có thể dùng làm đầu vào ban đầu cho tùy chọn --add-modules của jlink.

jdeps không tạo runtime image. Nó phân tích bytecode và cho biết các module được tham chiếu qua những phụ thuộc mà công cụ có thể phát hiện. jlink mới là công cụ liên kết các module và tạo runtime image.

## 2. Xem danh sách module mà ứng dụng cần

Với ứng dụng đóng gói dưới dạng JAR, có thể chạy:

~~~powershell
jdeps --print-module-deps app.jar
~~~

Ví dụ đầu ra:

~~~text
java.base,java.logging,java.sql
~~~

Đây là danh sách module cần xem xét cho runtime. java.base thường xuất hiện vì hầu hết chương trình Java đều phụ thuộc vào các kiểu nền tảng cơ bản. java.logging và java.sql xuất hiện khi bytecode có tham chiếu tới các API thuộc những module đó.

Để xem thông tin dễ đọc hơn trong lúc phân tích, dùng --list-deps:

~~~powershell
jdeps --list-deps app.jar
~~~

--list-deps trình bày module dependencies theo dạng danh sách. --print-module-deps phù hợp hơn khi cần lấy chuỗi tên module để chuyển tiếp cho công cụ build.

## 3. Phân tích cả dependency trên classpath

Ứng dụng thường sử dụng thêm thư viện bên thứ ba nằm trong thư mục lib. Nếu chỉ phân tích JAR chính, jdeps có thể không đi sâu vào các thư viện đó. Hãy chỉ rõ classpath và bật phân tích đệ quy:

~~~powershell
jdeps --print-module-deps --recursive --class-path "lib/*" app.jar
~~~

Trong đó:

- --class-path "lib/*" cho jdeps biết nơi tìm các thư viện JAR phụ thuộc.
- --recursive yêu cầu phân tích tiếp các dependency được tìm thấy, thay vì chỉ xem các lớp được chỉ định trực tiếp.
- --print-module-deps xuất tên module cần thiết thành chuỗi phân cách bằng dấu phẩy.

Trên Windows, danh sách nhiều đường dẫn classpath được phân cách bằng dấu chấm phẩy. Trên Linux và macOS, dấu phân cách thường là dấu hai chấm. Cú pháp wildcard lib/* được Java tools hỗ trợ cho các JAR trong thư mục đó.

Lưu ý: thư viện bên thứ ba nằm trên classpath không tự biến thành module JDK và không được jlink đóng gói chỉ vì nó xuất hiện trong kết quả phân tích. jdeps giúp xác định các module nền tảng Java mà ứng dụng và dependency tham chiếu; các JAR bên thứ ba vẫn phải được phân phối cùng ứng dụng theo cấu hình classpath/module phù hợp.

## 4. Dùng danh sách đầu ra làm module roots cho jlink

Trên PowerShell, có thể lưu kết quả phân tích vào biến rồi truyền cho jlink:

~~~powershell
$modules = jdeps --print-module-deps --recursive --class-path "lib/*" app.jar
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules $modules --strip-debug --no-header-files --no-man-pages --output build\runtime
~~~

Ở đây:

1. jdeps phân tích JAR chính và các thư viện trong lib.
2. $modules nhận chuỗi tên module, ví dụ java.base,java.logging,java.sql.
3. jlink tìm các module trong thư mục jmods của JDK đang dùng.
4. --add-modules chọn các module gốc; jlink tự giải quyết những module phụ thuộc trong module graph.
5. --output chỉ định nơi tạo runtime image.

Trước khi chạy jlink, hãy in và xem giá trị của $modules. Nếu đầu ra trống, có cảnh báo hoặc lỗi phân tích, hãy xử lý nguyên nhân trước khi dùng nó làm đầu vào. Không nên âm thầm thay danh sách rỗng bằng một danh sách module đoán trước.

Với ứng dụng modular, module ứng dụng cũng phải nằm trên module path và được chọn làm module gốc. Ví dụ, nếu module chính là com.example.app, cần đưa tên module ứng dụng vào tập module roots cùng các module cần thiết do phân tích xác định:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,java.logging,java.sql --output build\runtime
~~~

Danh sách module trong ví dụ chỉ minh họa. Hãy dùng tên module thực tế từ module descriptor và kết quả phân tích của ứng dụng.

## 5. Phân tích ứng dụng modular và ứng dụng classpath

Hai kiểu ứng dụng cần được phân tích theo cách phù hợp:

| Ứng dụng | Cách phân tích | Điều cần đưa vào runtime |
| --- | --- | --- |
| JAR không có module descriptor | Phân tích JAR và classpath dependency | Các module nền tảng Java được tham chiếu; ứng dụng và thư viện vẫn được phân phối riêng |
| Ứng dụng có module-info.class | Phân tích module cùng module path dependency | Module ứng dụng và các module phụ thuộc cần thiết |
| Ứng dụng có plugin/module tải động | Phân tích phần tĩnh, sau đó bổ sung module từ cấu hình triển khai | Cả module được nạp động mà ứng dụng cần |

Với ứng dụng modular, có thể chỉ rõ module cần phân tích và module path:

~~~powershell
jdeps --print-module-deps --module-path mods --module com.example.app
~~~

Đảm bảo module path chứa các module ứng dụng mà module chính phụ thuộc. Nếu dùng module path cho thư viện bên thứ ba, kiểm tra chúng có tên module phù hợp và được công cụ phân giải.

Với ứng dụng classpath, kết quả jdeps không thay thế việc đóng gói các JAR phụ thuộc. jlink chỉ liên kết module; nó không biến toàn bộ thư viện classpath thành module của runtime image.

## 6. Các giới hạn của phân tích tĩnh

jdeps phân tích tham chiếu có thể nhận ra từ bytecode. Một số dependency chỉ xuất hiện khi chạy nên có thể không được suy ra đầy đủ:

- **Reflection:** lớp hoặc phương thức được nạp bằng tên chuỗi lấy từ file cấu hình.
- **ServiceLoader:** implementation được phát hiện qua khai báo service và module provider.
- **Plugin:** module hoặc JAR được chọn từ thư mục plugin khi ứng dụng chạy.
- **JNI:** thư viện native được nạp theo tên hoặc đường dẫn.
- **Cấu hình ngoài:** tên driver, provider hoặc adapter được đọc từ file cấu hình hay biến môi trường.

Với các trường hợp đó, cần bổ sung module hoặc dependency dựa trên cấu hình triển khai và kiểm thử chức năng thực tế. Khi dùng service provider trong runtime image, cân nhắc tùy chọn --bind-services của jlink để liên kết các provider phù hợp theo module graph.

Không nên dùng --ignore-missing-deps để che khuất dependency chưa được giải quyết rồi coi danh sách là đầy đủ. Hãy tìm thư viện thiếu, bổ sung đúng classpath/module path hoặc xác định rõ dependency được nạp động.

## 7. Phân tích API nội bộ và dependency còn thiếu

Ngoài việc lập danh sách module, jdeps còn có thể giúp phát hiện các vấn đề ảnh hưởng đến khả năng đóng gói:

~~~powershell
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Lệnh trên báo các tham chiếu dependency mà công cụ không tìm thấy trong classpath/module path được cung cấp. Hãy bổ sung dependency còn thiếu trước khi kết luận danh sách module là hoàn chỉnh.

Để phát hiện tham chiếu tới API nội bộ của JDK:

~~~powershell
jdeps --jdk-internals app.jar
~~~

Nếu ứng dụng phụ thuộc vào package nội bộ như sun.* hoặc com.sun.* không được hỗ trợ như API công khai, hãy tìm API chuẩn thay thế. Việc đưa thêm module vào runtime không biến API nội bộ thành API ổn định.

Kết quả jdeps là dữ liệu phân tích, không phải chứng nhận ứng dụng tương thích với mọi phiên bản JDK. Sau khi thay dependency hoặc API, hãy phân tích và kiểm thử lại.

## 8. Xử lý multi-release JAR

Một multi-release JAR có thể chứa các phiên bản lớp khác nhau trong META-INF/versions. Khi phân tích, cần chọn góc nhìn phiên bản phù hợp với runtime mục tiêu:

~~~powershell
jdeps --multi-release 16 --print-module-deps --recursive --class-path "lib/*" app.jar
~~~

Tùy chọn --multi-release 16 yêu cầu jdeps phân tích phiên bản lớp phù hợp với release 16 trong JAR nhiều phiên bản. Nếu mục tiêu là runtime mới hơn, chọn release tương ứng hoặc dùng cấu hình phân tích phù hợp với JDK mục tiêu.

Không nên mặc định phân tích phần lớp base nếu ứng dụng thực tế sẽ chạy các lớp thay thế trong META-INF/versions. Chọn sai góc nhìn có thể làm kết quả phụ thuộc module không phản ánh code được nạp trên runtime dự kiến.

## 9. Từ kết quả jdeps đến kiểm thử runtime image

Danh sách module là điểm khởi đầu cho jlink. Sau khi tạo runtime image, cần kiểm tra:

~~~powershell
.\build\runtime\bin\java.exe --list-modules
~~~

Tiếp theo chạy ứng dụng bằng runtime image đó và kiểm thử các luồng nghiệp vụ quan trọng, đặc biệt là:

- Chức năng sử dụng thư viện bên thứ ba.
- Chức năng nạp lớp qua reflection hoặc plugin.
- Service provider được phát hiện qua ServiceLoader.
- Truy cập database, logging, desktop hoặc các API nền tảng khác mà ứng dụng dùng.
- Nạp thư viện JNI/native theo nền tảng.

Nếu một chức năng lỗi do thiếu module, xác định module thực sự cần thiết rồi bổ sung vào module roots hoặc cấu hình service binding. Sau khi thay đổi, tạo lại runtime image và chạy lại test.

## 10. Quy trình đề xuất

1. Build ứng dụng và xác định JAR, module path, classpath dependency thực tế.
2. Chạy jdeps --print-module-deps; dùng --recursive khi cần phân tích dependency transitively.
3. Xem kết quả bằng --list-deps và xử lý missing dependencies.
4. Kiểm tra các đường nạp động, reflection, service, plugin và JNI để bổ sung module không thể suy ra từ bytecode.
5. Dùng danh sách module đã rà soát làm đầu vào cho jlink --add-modules.
6. Kiểm tra runtime image bằng --list-modules.
7. Chạy ứng dụng và test trên runtime image, sau đó mới đóng gói bằng jpackage.

**Ghi nhớ:** jdeps --print-module-deps tạo danh sách tên module khởi đầu từ phân tích bytecode; jlink dùng danh sách module roots đó để tạo runtime image và tự giải quyết phụ thuộc module. Kết quả jdeps không bao quát mọi dependency động, không đóng gói JAR bên thứ ba và không thay thế kiểm thử trên runtime thực tế. Hãy rà soát reflection, service, plugin, JNI và dependency còn thiếu trước khi phát hành.
