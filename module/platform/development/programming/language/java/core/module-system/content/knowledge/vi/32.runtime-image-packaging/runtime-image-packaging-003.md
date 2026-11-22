# Giảm runtime image bằng jlink --limit-modules

## 1. Mục tiêu

Một JDK đầy đủ cung cấp nhiều module, nhưng một ứng dụng thường chỉ cần một phần trong số đó. Khi triển khai ứng dụng trên máy chủ hoặc container, mang theo toàn bộ JDK có thể làm runtime lớn hơn mức cần thiết.

Công cụ `jlink` tạo một **custom runtime image** gồm runtime Java và các module được chọn. Tùy chọn `--limit-modules` giới hạn tập module mà resolver được phép quan sát trong lúc tạo image. Kết hợp nó với `--add-modules`, ta có thể xác định module gốc của ứng dụng và thu hẹp tập module ứng viên dùng để giải quyết dependency.

Cần phân biệt hai việc:

- `--add-modules` xác định các root modules cần đưa vào image.
- `--limit-modules` giới hạn universe module observable dùng trong quá trình resolution; các dependency bắc cầu cần thiết của những module trong tập giới hạn vẫn được tính đến.

`--limit-modules` không đơn giản có nghĩa là chỉ chép đúng các tên được liệt kê rồi bỏ mọi dependency. Resolver vẫn cần các module mà root yêu cầu trực tiếp hoặc gián tiếp. Nếu thiếu một dependency bắt buộc trong module path, quá trình link sẽ thất bại.

Sau bài này, bạn có thể tạo runtime image cho một modular application, chọn root modules, giới hạn tập module observable, kiểm tra image và xử lý lỗi khi module cần thiết bị thiếu.

## 2. jlink tạo ra những gì?

`jlink` lấy các module đã biên dịch từ module path, giải quyết dependency của các root modules và tạo một runtime image có thể chạy độc lập trên nền tảng tương ứng.

Một image thường có cấu trúc dạng:

~~~text
runtime/
├── bin/
│   ├── java
│   └── keytool
├── conf/
├── legal/
├── lib/
└── release
~~~

Các module được link nằm trong image. Ứng dụng modular cũng có thể được đóng gói vào image, vì vậy khi chạy không cần cung cấp lại các JAR ứng dụng qua module path bên ngoài.

Điều kiện cơ bản:

- Dùng JDK có công cụ `jlink`, không phải một runtime image tối giản đã loại bỏ linker.
- Ứng dụng và các dependency cần thiết phải là named modules hợp lệ.
- Module path phải chứa các module mà resolver cần tìm.
- Runtime image được tạo cho nền tảng tương ứng với JDK/toolchain đang dùng; không xem `jlink` như công cụ biên dịch chéo tùy ý giữa các hệ điều hành hoặc kiến trúc.

## 3. Chuẩn bị một modular application

Ví dụ ứng dụng có hai module:

- `com.example.api`: cung cấp API.
- `com.example.app`: chứa main class và sử dụng API.

Cấu trúc thư mục sau khi biên dịch:

~~~text
project/
├── mods/
│   ├── com.example.api.jar
│   └── com.example.app.jar
└── runtime/
~~~

Module API:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

~~~java
package com.example.api;

public final class Greeting {
    public static String message() {
        return "Hello from a custom runtime";
    }
}
~~~

Module ứng dụng:

~~~java
module com.example.app {
    requires com.example.api;
}
~~~

~~~java
package com.example.app;

import com.example.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Giả sử hai module đã được đóng gói thành modular JAR:

~~~text
mods/com.example.api.jar
mods/com.example.app.jar
~~~

Tên file JAR có thể khác tên module; module name thực tế lấy từ descriptor của module.

## 4. Cú pháp jlink cơ bản

Cú pháp tổng quát:

~~~bash
jlink --module-path <module-path> --add-modules <root-modules> --output <directory>
~~~

Các tùy chọn chính:

| Tùy chọn | Vai trò |
| --- | --- |
| `--module-path` | Nơi tìm các module nguồn, thường gồm thư mục `jmods` của JDK và thư mục chứa modular JAR của ứng dụng. |
| `--add-modules` | Chọn một hoặc nhiều root modules để đưa vào image. |
| `--limit-modules` | Giới hạn tập module observable trong quá trình resolution. |
| `--output` | Thư mục tạo runtime image. |
| `--bind-services` | Liên kết các service provider module phù hợp cùng dependency của chúng. |

Trên Linux/macOS, có thể link ứng dụng như sau:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
~~~

Trong đó:

- `$JAVA_HOME/jmods` chứa các module của JDK dưới dạng JMOD.
- `mods` chứa modular JAR của ứng dụng.
- `com.example.app` là root module.
- `runtime` là custom runtime image được tạo.

Vì `com.example.app` khai báo `requires com.example.api`, resolver đưa cả `com.example.api` và các dependency cần thiết của nó vào image. `java.base` cũng có mặt vì các named module thông thường phụ thuộc nền tảng vào module này.

## 5. Dùng --limit-modules để thu hẹp tập module observable

Cú pháp:

~~~bash
jlink --module-path <module-path> --add-modules <root-modules> --limit-modules <module-list> --output <directory>
~~~

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --limit-modules "java.base,com.example.api,com.example.app" --output runtime
~~~

Ở đây:

- `com.example.app` là root module được link.
- `java.base`, `com.example.api` và `com.example.app` là các module được nêu trong giới hạn observable.
- Dependency bắc cầu cần thiết của các module trong tập này vẫn được resolver xét đến.
- Các module không nằm trong tập giới hạn và không thuộc dependency closure cần thiết sẽ không được xem như module observable cho lần link này.

Trong ví dụ nhỏ, danh sách giới hạn nêu rõ app, API và module nền tảng mà ứng dụng cần. Với dự án thực tế, phải xét cả các module được yêu cầu gián tiếp, module hệ thống mà thư viện sử dụng và service provider cần được bind.

Nếu `--limit-modules` loại mất một module mà ứng dụng thực sự cần, `jlink` sẽ báo lỗi resolution thay vì âm thầm tạo image thiếu dependency.

## 6. --add-modules và --limit-modules không thay thế nhau

Hai tùy chọn giải quyết hai câu hỏi khác nhau:

| Câu hỏi | Tùy chọn |
| --- | --- |
| Module nào là root cần đưa vào image? | `--add-modules` |
| Resolver được phép quan sát tập module nào? | `--limit-modules` |

Ví dụ chỉ định root:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
~~~

Ví dụ chỉ định root và giới hạn universe:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --limit-modules "java.base,com.example.api,com.example.app" --output runtime
~~~

Nếu chỉ có `--limit-modules` mà không chọn root phù hợp, nó không tự nói rằng module ứng dụng nào phải được đưa vào image. Ngược lại, `--add-modules` không phải danh sách cấm tất cả module khác; nó chọn roots, còn resolver tính dependency closure.

## 7. Service provider trong runtime image

Nếu ứng dụng sử dụng `ServiceLoader`, cần tính đến provider module trong lúc đóng gói.

Ví dụ consumer khai báo:

~~~java
module com.example.app {
    requires com.example.api;

    uses com.example.api.GreetingService;
}
~~~

Provider khai báo:

~~~java
module com.example.provider {
    requires com.example.api;

    provides com.example.api.GreetingService
        with com.example.provider.FormalGreetingService;
}
~~~

Nếu provider không phải dependency `requires` trực tiếp của root, có thể dùng `--bind-services` để linker tìm và liên kết các provider module phù hợp:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output runtime
~~~

Khi kết hợp với `--limit-modules`, bảo đảm các provider module cần dùng nằm trong tập module observable hoặc dependency closure của tập đó. Nếu giới hạn loại provider khỏi universe, linker không thể bind provider ấy.

Việc provider module được đưa vào image không đồng nghĩa service instance đã được tạo lúc link. Instance được yêu cầu khi ứng dụng chạy và gọi ServiceLoader.

## 8. Tối ưu thêm kích thước runtime image

Sau khi chọn đúng module set, có thể dùng các plugin của `jlink` để giảm dung lượng image.

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --limit-modules "java.base,com.example.api,com.example.app" --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime
~~~

Ý nghĩa:

- `--strip-debug`: loại bỏ thông tin debug khỏi các class trong image.
- `--no-header-files`: không đưa các header file native vào image.
- `--no-man-pages`: không đưa manual page vào image.
- `--compress=2`: nén resource trong image theo mức nén được hỗ trợ.

Các plugin này là lựa chọn tối ưu đóng gói; chúng không thay thế việc xác định đúng dependency module. Trước khi bỏ header hoặc man page, xác nhận image không được dùng như bộ JDK phát triển native hoặc tài liệu tham khảo trên máy đích.

Có thể xem danh sách plugin khả dụng bằng:

~~~bash
jlink --list-plugins
~~~

Danh sách và chi tiết plugin phụ thuộc phiên bản JDK đang dùng.

## 9. Kiểm tra runtime image sau khi link

Sau khi lệnh `jlink` hoàn tất, dùng chính launcher trong image để kiểm tra danh sách module:

~~~bash
runtime/bin/java --list-modules
~~~

Kết quả sẽ liệt kê các module có trong custom runtime image. Có thể xem descriptor của module ứng dụng:

~~~bash
runtime/bin/java --describe-module com.example.app
~~~

Chạy ứng dụng bằng runtime mới:

~~~bash
runtime/bin/java --module com.example.app/com.example.app.Main
~~~

Trên Windows, launcher thường nằm tại:

~~~powershell
runtime\bin\java.exe --list-modules
runtime\bin\java.exe --module com.example.app/com.example.app.Main
~~~

Kiểm tra thực tế nên gồm:

- Ứng dụng khởi động thành công bằng launcher trong image.
- Mọi API được sử dụng đều có mặt.
- Các module provider cần thiết được bind nếu ứng dụng dùng service.
- Resource, locale, security provider, logging và cấu hình runtime hoạt động như mong đợi.
- Image chạy trên môi trường đích có cùng nền tảng hệ điều hành và kiến trúc.

Không chỉ kiểm tra lệnh link thành công. Hãy chạy các luồng chức năng quan trọng trên image cuối cùng.

## 10. Lỗi thường gặp

**Module not found**

Module được nêu trong `--add-modules` hoặc `--limit-modules` không được tìm thấy. Kiểm tra module path, tên module trong descriptor và sự hiện diện của JDK `jmods`.

**Missing required module**

Một root hoặc dependency của nó yêu cầu module không có trong module path hoặc không còn observable sau khi giới hạn. Thêm đúng module vào module path và điều chỉnh giới hạn để dependency closure hợp lệ.

**Module bị giới hạn nhưng ứng dụng cần dùng**

Nếu một module nằm ngoài tập giới hạn và không thuộc dependency closure của các module được liệt kê, resolver không thể dùng module đó. Cập nhật danh sách giới hạn hoặc bỏ `--limit-modules` để xác định liệu giới hạn có phải nguyên nhân.

**Automatic module không thể link**

`jlink` yêu cầu các module được link phải phù hợp với mô hình modular image; automatic module từ JAR không có descriptor không phải đầu vào thay thế trực tiếp cho explicit named module. Hãy nâng cấp thư viện, tạo modular JAR hợp lệ hoặc đóng gói dependency theo cách phù hợp trước khi link.

**Service provider không xuất hiện trong image**

Kiểm tra consumer có `uses`, provider có `provides`, provider nằm trên module path và có thể được quan sát. Nếu muốn linker tự bind các provider phù hợp, cân nhắc `--bind-services`; nếu dùng `--limit-modules`, đừng loại provider cần thiết khỏi tập observable.

**Image tạo được nhưng ứng dụng lỗi khi chạy**

Kiểm tra lại module roots, module resolution, service binding và các tài nguyên cần ở runtime. Chạy bằng chính `runtime/bin/java` thay vì JDK phát triển để phát hiện module hoặc resource vô tình chỉ có trong môi trường build.

## 11. Quy trình tạo image có kiểm soát

1. Biên dịch và đóng gói ứng dụng thành explicit modular JAR.
2. Liệt kê dependency module của ứng dụng qua `module-info.java` và kiểm tra descriptor của thư viện.
3. Xác định root module, thường là module chứa ứng dụng.
4. Xác định module provider cần có nếu ứng dụng sử dụng ServiceLoader.
5. Chọn module path gồm JDK `jmods` và modular JAR của ứng dụng.
6. Chạy `jlink` với `--add-modules` để chọn root.
7. Thêm `--limit-modules` khi cần giới hạn tập module observable, đồng thời giữ đủ dependency closure.
8. Thêm plugin giảm kích thước sau khi module set đã đúng.
9. Kiểm tra `--list-modules`, `--describe-module` và chạy các bài test trên image tạo ra.
10. Đóng gói image cho đúng hệ điều hành và kiến trúc đích.

## 12. Ghi nhớ

- `jlink` tạo custom runtime image từ các module đã biên dịch.
- `--add-modules` chọn root modules cần link.
- `--limit-modules` giới hạn module observable trong quá trình resolution; dependency bắc cầu cần thiết vẫn được giải quyết.
- Module path phải chứa JDK modules và các modular JAR của ứng dụng.
- Dùng `--bind-services` khi muốn linker liên kết service provider module phù hợp.
- Các plugin như `--strip-debug`, `--no-header-files`, `--no-man-pages` và `--compress=2` có thể giảm dung lượng nhưng không thay thế việc chọn dependency đúng.
- Dùng launcher trong image để kiểm tra module list và chạy ứng dụng thực tế.

Hãy bắt đầu bằng việc xác định root module và dependency closure của ứng dụng. Sau đó dùng `--limit-modules` để thu hẹp tập module resolver có thể nhìn thấy, link image và kiểm thử chính image đó trên môi trường triển khai.
