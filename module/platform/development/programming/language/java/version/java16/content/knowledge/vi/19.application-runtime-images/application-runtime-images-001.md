# Quan hệ giữa jpackage và jlink khi tạo runtime đi kèm

## 1. Hai công cụ giải quyết hai phần của quy trình triển khai

Khi phân phối một ứng dụng Java cho máy người dùng, có hai việc thường cần làm: tạo một Java runtime chỉ chứa những module cần thiết và đóng gói ứng dụng cùng runtime đó thành một thư mục chạy độc lập hoặc bộ cài đặt theo hệ điều hành.

`jlink` và `jpackage` phối hợp để giải quyết hai việc này:

- **`jlink`** tạo một *runtime image* tùy chỉnh từ các module của JDK và module ứng dụng. Runtime image chứa bộ chạy Java cùng những module được chọn và các phụ thuộc cần thiết.
- **`jpackage`** đóng gói ứng dụng thành application image hoặc bộ cài đặt native. Gói có thể chứa runtime image để người dùng chạy ứng dụng mà không phải tự cài một JDK riêng.

`jlink` tập trung vào nội dung runtime. `jpackage` tập trung vào cấu trúc và định dạng phân phối ứng dụng. Hai công cụ không thay thế nhau; `jpackage` có thể dùng runtime do `jlink` tạo ra.

`jlink` được đưa vào JDK từ Java 9. `jpackage` được chuẩn hóa thành công cụ chính thức trong JDK 16 (JEP 392), sau các giai đoạn thử nghiệm trước đó. Cả hai vẫn là công cụ triển khai hiện hành trong các JDK hiện đại.

## 2. Luồng tạo gói: jpackage có thể gọi jlink

Khi không truyền tùy chọn `--runtime-image`, `jpackage` tự tạo runtime image bằng cách gọi `jlink`. Vì vậy, với ứng dụng module hóa, một lệnh `jpackage` có thể thực hiện cả việc tạo runtime và đóng gói:

~~~text
Module ứng dụng + các module JDK cần thiết
                 |
                 v
        jpackage gọi jlink
                 |
                 v
       Runtime image tùy chỉnh
                 |
                 v
  jpackage thêm launcher, ứng dụng,
  tài nguyên và metadata đóng gói
                 |
                 v
     Application image / installer
~~~

Nếu đã có runtime image được tạo và kiểm thử riêng, có thể truyền đường dẫn đó bằng `--runtime-image`. Khi ấy `jpackage` sử dụng runtime image đã có thay vì tự tạo runtime mới:

~~~text
Module ứng dụng + module JDK
          |
          v
         jlink
          |
          v
 Runtime image đã dựng
          |
          +-------------------+
                              |
Ứng dụng + tài nguyên --------+--> jpackage
                              |
                              v
                 Application image / installer
~~~

Điểm quyết định là:

| Cách chạy `jpackage` | Ai tạo runtime image? | Khi phù hợp |
| --- | --- | --- |
| Không có `--runtime-image` | `jpackage` gọi `jlink` | Ứng dụng có cấu hình module rõ ràng và muốn một lệnh đóng gói |
| Có `--runtime-image <đường-dẫn>` | Bạn tạo trước, thường bằng `jlink` | Cần kiểm soát, kiểm tra hoặc dùng lại runtime image đã chuẩn bị |

## 3. jlink tạo runtime image gồm những gì?

`jlink` lấy các module từ module path, bắt đầu từ những module gốc được chỉ định bằng `--add-modules`, rồi giải quyết các phụ thuộc module cần thiết. Kết quả là một thư mục runtime image có thể chạy Java trên nền tảng tương ứng.

Ví dụ, một ứng dụng module hóa có module descriptor:

~~~java
module com.example.inventory {
    requires java.sql;
}
~~~

Giả sử module ứng dụng đã được biên dịch vào thư mục `mods`. Có thể tạo runtime image:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.inventory --strip-debug --no-header-files --no-man-pages --output build\runtime
~~~

Trong ví dụ:

- `$env:JAVA_HOME\jmods` cung cấp các module hệ thống của JDK đang dùng.
- `mods` chứa module ứng dụng và các module ứng dụng phụ thuộc.
- `--add-modules com.example.inventory` chọn module ứng dụng làm module gốc.
- `requires java.sql` khiến module `java.sql` và các phụ thuộc cần thiết được đưa vào runtime.
- Các tùy chọn `--strip-debug`, `--no-header-files` và `--no-man-pages` loại bỏ dữ liệu debug, header native và trang hướng dẫn không cần cho runtime thông thường.
- `--output` chỉ định thư mục runtime image.

Trên Linux và macOS, dấu phân cách các mục trong module path thường là dấu hai chấm (`:`); trên Windows là dấu chấm phẩy (`;`). Hãy dùng đúng dấu phân cách của hệ điều hành đang build.

Runtime image thường có thư mục `bin` chứa lệnh chạy Java và thư mục `lib` chứa các thành phần runtime. Nó không phải một JDK đầy đủ dành cho phát triển: các công cụ như compiler `javac` không được thêm vào trừ khi chủ động đưa module công cụ tương ứng vào.

Có thể xem các module trong runtime sau khi tạo:

~~~powershell
.\build\runtime\bin\java.exe --list-modules
~~~

Lệnh này giúp xác nhận runtime có các module dự kiến. Nó không thay thế kiểm thử ứng dụng thực tế.

## 4. jpackage đóng gói ứng dụng cùng runtime

Sau khi có runtime image, `jpackage` tạo application image hoặc installer native. Với ứng dụng module hóa trong ví dụ trên:

~~~powershell
jpackage --type app-image --name InventoryApp --module-path mods --module com.example.inventory/com.example.inventory.Main --runtime-image build\runtime --dest dist
~~~

Các tùy chọn chính:

- `--type app-image` yêu cầu tạo thư mục ứng dụng có thể chạy trực tiếp.
- `--name` đặt tên ứng dụng và launcher.
- `--module-path` giúp `jpackage` tìm module ứng dụng cần đóng gói.
- `--module` xác định module chính và lớp main.
- `--runtime-image` chỉ định runtime image dựng sẵn bằng `jlink`.
- `--dest` chọn thư mục chứa kết quả.

Application image thường có launcher, các thành phần ứng dụng, tài nguyên và thư mục runtime đi kèm. Người dùng chạy launcher được tạo trong application image; họ không cần gọi `java -jar` bằng một JDK cài riêng.

Nếu không cần dựng runtime riêng, có thể bỏ `--runtime-image`. `jpackage` sẽ gọi `jlink` để tạo runtime trong quá trình đóng gói:

~~~powershell
jpackage --type app-image --name InventoryApp --module-path mods --module com.example.inventory/com.example.inventory.Main --dest dist
~~~

Nếu ứng dụng cần thêm một module được nạp động mà quan hệ `requires` không thể hiện trong module graph, có thể chỉ định module bổ sung bằng `--add-modules` khi để `jpackage` tạo runtime. Với runtime dựng sẵn, hãy thêm module đó vào lệnh `jlink` trước khi đóng gói.

## 5. Phân biệt application image và installer native

`jpackage` có thể tạo thư mục application image hoặc bộ cài đặt theo định dạng của hệ điều hành:

| Loại đầu ra | Ví dụ nền tảng | Mục đích |
| --- | --- | --- |
| `app-image` | Windows, Linux, macOS | Thư mục ứng dụng có launcher và runtime đi kèm |
| `msi` hoặc `exe` | Windows | Bộ cài đặt Windows |
| `deb` hoặc `rpm` | Linux | Gói cài đặt cho các hệ quản lý gói tương ứng |
| `dmg` hoặc `pkg` | macOS | Ảnh đĩa hoặc gói cài đặt macOS |

Các loại installer phụ thuộc hệ điều hành và công cụ đóng gói sẵn có trên máy build. Không phải mọi loại đầu ra đều được hỗ trợ trên mọi nền tảng.

Ví dụ, sau khi kiểm thử application image, có thể tạo installer Windows:

~~~powershell
jpackage --type msi --name InventoryApp --module-path mods --module com.example.inventory/com.example.inventory.Main --runtime-image build\runtime --dest dist
~~~

Trên máy build Windows, `jpackage` tạo đầu ra theo định dạng Windows được hỗ trợ. Muốn phát hành cho macOS hoặc Linux, cần build và kiểm thử gói tương ứng trên môi trường của nền tảng đích.

Application image không đồng nghĩa với installer. Application image là thư mục ứng dụng đã đóng gói; installer native bổ sung quy trình cài đặt theo quy ước hệ điều hành.

## 6. Khi nào nên để jpackage tự gọi jlink?

Để `jpackage` tự tạo runtime là lựa chọn gọn khi:

- Ứng dụng đã được module hóa và module descriptor khai báo đầy đủ phụ thuộc tĩnh.
- Không cần một runtime image dùng chung cho nhiều ứng dụng.
- Các module bổ sung có thể khai báo trực tiếp bằng tùy chọn của `jpackage`.
- Quy trình build muốn giảm số bước và không cần kiểm tra runtime ở một giai đoạn độc lập.

Ưu điểm là cấu hình ngắn và giảm thao tác thủ công. `jpackage` điều phối việc tạo runtime rồi đóng gói trong cùng quy trình.

Tuy nhiên, vẫn phải kiểm tra tập module thực tế. Các phụ thuộc được tải qua reflection, tên module cấu hình trong file ngoài, `ServiceLoader`, JNI hoặc cơ chế plugin có thể không được thể hiện đầy đủ trong quan hệ `requires` thông thường.

## 7. Khi nào nên tạo runtime bằng jlink trước?

Tạo runtime riêng bằng `jlink` hữu ích khi:

- Cần xem và kiểm soát chính xác tập module được đưa vào runtime.
- Nhiều ứng dụng cùng dùng một runtime image đã được chuẩn hóa và kiểm thử.
- Muốn kiểm tra runtime độc lập trước khi tạo installer.
- Quy trình phát hành cần lưu runtime image như một đầu ra build có thể tái sử dụng.
- Cần áp dụng các tùy chọn `jlink` riêng, chẳng hạn `--bind-services`, hoặc cấu hình module roots rõ ràng.

Sau khi tạo runtime, kiểm tra module:

~~~powershell
.\build\runtime\bin\java.exe --list-modules
~~~

Sau đó chạy thử ứng dụng với runtime này trước khi đưa đường dẫn vào `jpackage`. Nếu ứng dụng thiếu module, hãy điều chỉnh module roots hoặc cấu hình service binding khi tạo lại runtime.

Tạo runtime riêng giúp kiểm soát tốt hơn, nhưng cũng tạo thêm một sản phẩm build cần quản lý phiên bản. Khi ứng dụng hoặc dependency thay đổi, phải đánh giá lại runtime tương ứng.

## 8. Chọn module cần thiết và tránh runtime thiếu phụ thuộc

`jlink` xây dựng runtime từ module graph. Các quan hệ `requires` trong module descriptor giúp xác định phụ thuộc tĩnh, nhưng không phải mọi dependency đều có thể suy ra từ mã nguồn.

Một số trường hợp cần chú ý:

- **Reflection:** tên lớp hoặc module được nạp từ cấu hình có thể không xuất hiện trong tham chiếu tĩnh.
- **Service loading:** ứng dụng dùng `ServiceLoader` có thể cần các module cung cấp service; cân nhắc `--bind-services` khi tạo runtime.
- **JNI và thư viện native:** file native phải được phân phối đúng nền tảng và kiến trúc; `jlink` không tự biến thư viện native của một OS thành thư viện dùng được trên OS khác.
- **Plugin hoặc module tải động:** cần xác định rõ module nào phải có sẵn trong runtime hoặc được triển khai theo cơ chế plugin riêng.

`jdeps` có thể hỗ trợ phân tích dependency tĩnh của ứng dụng và thư viện. Kết quả phân tích không thể thay thế việc kiểm tra các đường nạp động, reflection, service và native library.

Không nên thêm thật nhiều module chỉ để tránh lỗi một cách mơ hồ. Hãy tái hiện tính năng cần chạy, xác định module bị thiếu và thêm module gốc phù hợp. Ngược lại, cũng không nên loại module chỉ dựa vào việc một ca chạy thử đơn giản không sử dụng đến nó.

Với ứng dụng dùng service provider, tùy chọn `--bind-services` của `jlink` yêu cầu công cụ liên kết các module cung cấp service phù hợp vào runtime image. Chỉ bật khi ứng dụng cần cơ chế đó và vẫn phải kiểm thử service discovery ở runtime.

## 9. Giới hạn module path của jlink

`jlink` làm việc với các module có thể liên kết vào runtime image, chẳng hạn module JDK và module ứng dụng có tên rõ ràng. Một JAR chỉ nằm trên classpath hoặc một automatic module không thể được coi như module gốc để liên kết bằng `jlink`.

Với dependency chưa module hóa, cần xem xét cách tổ chức lại dependency thành explicit module hoặc thiết kế đóng gói phù hợp. `jpackage` hỗ trợ nhiều cách đóng gói ứng dụng Java, nhưng điều đó không có nghĩa `jlink` có thể liên kết mọi JAR classpath thành module.

Phân biệt hai module path:

- `--module-path` của `jlink` tìm các module dùng để dựng runtime, thường gồm thư mục `jmods` của JDK và module ứng dụng.
- `--module-path` của `jpackage` giúp tìm module ứng dụng cần đóng gói.

Hai tùy chọn có tên giống nhau nhưng phục vụ hai bước khác nhau. Khi dùng runtime dựng sẵn, module path của `jpackage` vẫn cần trỏ tới module ứng dụng; `--runtime-image` trỏ tới runtime đã tạo ở bước trước.

## 10. Runtime image và gói ứng dụng gắn với nền tảng đích

Runtime image do `jlink` tạo chứa thành phần native của nền tảng build. Vì vậy, không nên tạo runtime trên Windows rồi kỳ vọng dùng nguyên runtime đó cho Linux hoặc macOS. Kiến trúc CPU cũng cần phù hợp với môi trường đích.

Một quy trình phát hành đa nền tảng thường có build riêng cho từng nền tảng:

1. Build module ứng dụng và dependency cho nền tảng/phiên bản JDK mục tiêu.
2. Dùng `jlink` tạo runtime image trên môi trường phù hợp, hoặc để `jpackage` tạo runtime tại bước đóng gói.
3. Dùng `jpackage` tạo application image hoặc installer native cho nền tảng đó.
4. Kiểm thử trên máy sạch không cài JDK, đúng hệ điều hành và kiến trúc được hỗ trợ.

Nên dùng bộ công cụ `jlink` và `jpackage` từ cùng một JDK release cho một quy trình build để tránh sai khác module hoặc định dạng runtime. Phiên bản runtime đi kèm phải đáp ứng phiên bản bytecode, API và dependency mà ứng dụng sử dụng.

## 11. Các bước kiểm thử sau khi đóng gói

Sau khi tạo application image hoặc installer, cần kiểm tra:

- Launcher khởi động được khi máy thử không cài JDK riêng.
- Runtime đi kèm có đủ module cho các luồng nghiệp vụ chính.
- Tài nguyên, file cấu hình mặc định và dependency được tìm thấy từ vị trí triển khai.
- Các tính năng reflection, service loading, plugin và JNI hoạt động.
- Quyền truy cập file, thư mục ghi dữ liệu và biến môi trường phù hợp với hệ điều hành.
- Cài đặt, khởi chạy, nâng cấp và gỡ cài đặt hoạt động đúng nếu phân phối bằng installer.

Không nên lưu dữ liệu người dùng hoặc dữ liệu thay đổi thường xuyên bên trong thư mục runtime image. Hãy dùng thư mục dữ liệu ứng dụng theo quy ước hệ điều hành để cập nhật ứng dụng không làm mất dữ liệu.

## 12. Cách chọn quy trình phù hợp

| Nhu cầu | Quy trình nên chọn |
| --- | --- |
| Muốn một lệnh tạo gói cho ứng dụng module hóa | `jpackage` không truyền `--runtime-image` |
| Muốn kiểm tra tập module trước khi đóng gói | `jlink` tạo runtime, sau đó `jpackage --runtime-image` |
| Nhiều ứng dụng dùng cùng runtime chuẩn hóa | Dựng và quản lý runtime bằng `jlink`, sau đó dùng lại khi đóng gói |
| Muốn tạo thư mục chạy trực tiếp | `jpackage --type app-image` |
| Muốn tạo bộ cài đặt native | `jpackage --type` theo nền tảng đích |
| Ứng dụng có service provider hoặc module nạp động | Xác định module bổ sung, cấu hình `jlink`, rồi kiểm thử runtime thực tế |

**Ghi nhớ:** `jlink` tạo runtime image tùy chỉnh từ module; `jpackage` đóng gói ứng dụng và có thể tự gọi `jlink` nếu chưa được cung cấp runtime image. Dùng quy trình tự động khi cấu hình đơn giản; tạo runtime riêng khi cần kiểm soát và tái sử dụng. Dù chọn cách nào, phải kiểm tra module nạp động, service, native library và chạy thử gói trên đúng nền tảng đích trước khi phát hành.
