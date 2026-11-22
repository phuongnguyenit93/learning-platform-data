# Rủi ro tên module phụ thuộc tên file

## 1. Automatic module lấy tên từ đâu?

Một JAR không có `module-info.class` khi được đặt trên **module path** có thể được xem là một automatic module. JVM cần một tên module để đưa JAR đó vào module graph.

Tên automatic module được xác định theo thứ tự:

1. Nếu manifest của JAR có thuộc tính `Automatic-Module-Name`, giá trị đó được dùng làm tên module.
2. Nếu không có thuộc tính này, tên module được suy ra từ tên file JAR.

Ví dụ, một thư viện có file:

~~~text
payment-client-2.4.1.jar
~~~

có thể được suy ra tên module là:

~~~text
payment.client
~~~

Tên được suy ra bằng quy tắc chuẩn hóa tên file: bỏ phần mở rộng `.jar`, nhận diện và loại bỏ hậu tố phiên bản theo quy tắc đặt tên, thay các ký tự phân cách không hợp lệ bằng dấu chấm, gộp các dấu chấm liên tiếp và loại dấu chấm ở đầu/cuối. Đây là phép suy luận từ tên file, không phải tên được tác giả thư viện cam kết như một API ổn định.

Khi JAR đã có module descriptor tường minh, tên trong descriptor là tên module được sử dụng. `Automatic-Module-Name` và tên suy ra từ file chỉ liên quan đến JAR chưa có descriptor tường minh.

## 2. Vì sao phụ thuộc vào tên file tạo ra rủi ro?

Giả sử ứng dụng khai báo:

~~~java
module com.acme.checkout {
    requires payment.client;
}
~~~

Khai báo `requires` tham chiếu đến **tên module**, không tham chiếu trực tiếp đến tên file JAR, Maven artifact hay đường dẫn trên đĩa.

Nếu tên module được suy ra từ file, việc đổi tên artifact hoặc cách đóng gói có thể làm thay đổi tên mà compiler và JVM nhìn thấy. Khi đó, dòng `requires payment.client;` có thể không còn khớp với module thực tế.

Một số thay đổi có thể gây ảnh hưởng:

- Nhà cung cấp đổi tên artifact hoặc tên file JAR.
- Build pipeline thêm hoặc bỏ classifier trong tên file.
- Một bản phân phối đổi quy ước đặt tên file.
- Thư viện được chuyển từ một JAR gộp sang nhiều JAR có tên khác nhau.
- Một công cụ đóng gói đổi tên JAR khi copy vào thư mục triển khai.

Không phải mọi thay đổi phiên bản đều làm tên module thay đổi. Hậu tố phiên bản theo quy tắc thông thường thường được loại bỏ khi suy ra tên. Tuy nhiên, ứng dụng vẫn đang dựa vào một quy tắc đặt tên file và kết quả của nó, nên không nên xem tên suy ra là hợp đồng ổn định do nhà cung cấp bảo đảm.

## 3. Ví dụ tên file và tên module suy ra

Một số ví dụ minh họa:

| Tên file JAR | Tên automatic module có thể suy ra |
|---|---|
| `payment-client-2.4.1.jar` | `payment.client` |
| `json-core-1.8.jar` | `json.core` |
| `acme-logging.jar` | `acme.logging` |
| `legacy_http-3.0.jar` | `legacy.http` |

Hãy chú ý rằng tên module suy ra từ file không nhất thiết trùng với Maven coordinates:

~~~text
groupId    = com.vendor
artifactId = payment-client
version    = 2.4.1
file       = payment-client-2.4.1.jar
module     = payment.client
~~~

JPMS không tự lấy `groupId` để tạo prefix `com.vendor`. Nếu ứng dụng viết `requires com.vendor.payment.client;` trong khi JAR thực tế có tên automatic module `payment.client`, compiler sẽ không tìm thấy module được yêu cầu.

Tên trong ví dụ là kết quả minh họa theo quy tắc suy ra; với dependency thực tế, luôn kiểm tra chính artifact đã được resolve trong build.

## 4. Rủi ro khi tên file thay đổi

Giả sử thư viện ban đầu được phân phối như sau:

~~~text
libs/
└── payment-client-2.4.1.jar
~~~

Tên automatic module được suy ra là `payment.client`. Ứng dụng khai báo:

~~~java
module com.acme.checkout {
    requires payment.client;
}
~~~

Sau đó, một bước đóng gói đổi tên file thành:

~~~text
libs/
└── acme-payment.jar
~~~

Nếu JAR không có `Automatic-Module-Name` và không có `module-info.class`, tên suy ra có thể trở thành `acme.payment`. Lúc này module consumer vẫn yêu cầu `payment.client`, trong khi module path chỉ có `acme.payment`.

Kết quả thường là lỗi phân giải module như:

~~~text
module not found: payment.client
~~~

Lỗi xuất hiện dù bytecode bên trong JAR có thể vẫn giống hệt trước khi đổi tên. Nguyên nhân nằm ở metadata tên module mà module system nhìn thấy.

Đổi tên file cũng có thể gây ra lỗi theo chiều ngược lại: một JAR mới vô tình được suy ra thành tên module mà code hiện tại chưa từng yêu cầu. Vì vậy, khi nâng cấp hoặc thay cách đóng gói dependency, cần kiểm tra tên module thực tế.

## 5. Rủi ro trùng tên module

Hai JAR khác nhau có thể suy ra cùng một tên module nếu tên file sau khi chuẩn hóa giống nhau.

Ví dụ:

~~~text
libs/
├── payment-client-2.4.1.jar
└── payment-client-3.0.0.jar
~~~

Cả hai có thể được suy ra thành `payment.client`. Nếu cùng được đưa vào một cấu hình module, module resolver không thể xem chúng là hai module độc lập có cùng tên để ứng dụng chọn phiên bản tùy ý.

JPMS không cung cấp cơ chế nạp hai phiên bản của cùng một module name trong một module configuration như một dependency version resolver. Việc chọn phiên bản phải được build tool hoặc quy trình đóng gói xử lý trước khi tạo module path.

Điều này cũng cho thấy không thể dùng automatic module name để cô lập phiên bản thư viện. Nếu cần hai phiên bản cùng tồn tại, phải thiết kế ranh giới triển khai hoặc class loader/layer phù hợp; việc đổi tên file JAR đơn thuần không tạo ra một cơ chế version isolation an toàn.

## 6. Cách ổn định tên bằng Automatic-Module-Name

Để tránh phụ thuộc vào tên file, nhà cung cấp thư viện có thể đặt thuộc tính `Automatic-Module-Name` trong manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.payment.client
~~~

Khi JAR chưa có `module-info.class`, JPMS dùng tên trong manifest thay cho tên suy ra từ file. Vì vậy, file có thể được đổi tên hoặc có phiên bản mới mà module name vẫn ổn định, miễn là nhà cung cấp giữ nguyên thuộc tính đó.

Consumer khi đó khai báo:

~~~java
module com.acme.checkout {
    requires com.acme.payment.client;
}
~~~

Ví dụ cấu hình Gradle Groovy cho thư viện do nhóm phát triển sở hữu:

~~~groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Automatic-Module-Name': 'com.acme.payment.client'
        )
    }
}
~~~

Khi thư viện chuyển sang named module tường minh, nên giữ cùng tên trong `module-info.java`:

~~~java
module com.acme.payment.client {
    exports com.acme.payment.api;
}
~~~

Giữ tên nhất quán giúp consumer không phải đổi `requires` chỉ vì thư viện đã chuyển từ automatic module sang explicit named module.

Với thư viện bên thứ ba, nên ưu tiên bản phát hành đã công bố `Automatic-Module-Name` hoặc có module descriptor. Việc tự đổi tên file chỉ để làm cho `requires` khớp có thể khiến lần nâng cấp tiếp theo phát sinh lỗi và làm quy trình build khó dự đoán.

## 7. Kiểm tra tên module thực tế bằng công cụ JDK

Đừng đoán tên module chỉ từ Maven coordinates. Dùng chính file JAR đang được build sử dụng:

~~~bash
jar --describe-module --file libs/payment-client-2.4.1.jar
~~~

Với JAR không có descriptor tường minh, đầu ra cho biết đây là automatic module và hiển thị tên được dùng. Nếu manifest có `Automatic-Module-Name`, hãy kiểm tra tên đó trong kết quả.

Có thể kiểm tra thêm manifest:

~~~bash
unzip -p libs/payment-client-2.4.1.jar META-INF/MANIFEST.MF
~~~

Tìm dòng:

~~~text
Automatic-Module-Name: com.acme.payment.client
~~~

Nếu môi trường không có `unzip`, có thể giải nén manifest bằng công cụ ZIP sẵn có hoặc xem nội dung manifest trong artifact repository. Điểm quan trọng là kiểm tra đúng file JAR mà build đã resolve, không chỉ xem tên dependency trong file cấu hình.

Sau khi xác nhận tên, đối chiếu ba nơi:

1. Tên module trong `requires` của consumer.
2. Tên module hiển thị từ `jar --describe-module`.
3. File JAR thực sự có trên module path lúc compile và runtime.

## 8. Automatic module còn có đặc tính truy cập rộng

Tên file không phải rủi ro duy nhất khi dùng automatic module. Automatic module được thiết kế như một cơ chế chuyển tiếp để thư viện cũ có thể tham gia module path:

- Automatic module export tất cả package của nó.
- Automatic module đọc các module khác trong module configuration.
- Nó chưa thể hiện ranh giới API chặt chẽ như một named module có descriptor được thiết kế rõ ràng.

Vì vậy, việc JAR có một tên module và có thể được dùng trong `requires` không có nghĩa thư viện đã được modular hóa hoàn chỉnh. Consumer vẫn có thể nhìn thấy nhiều package nội bộ hơn mức thư viện muốn hỗ trợ lâu dài.

Khi cần encapsulation rõ ràng, nên ưu tiên thư viện có `module-info.class` và chỉ export những package API cần thiết. Automatic module phù hợp để hỗ trợ chuyển đổi từng bước, nhưng không nên mặc định xem nó là trạng thái thiết kế cuối cùng.

## 9. Quy trình xử lý khi nâng cấp dependency

Khi nâng cấp một JAR đang được sử dụng như automatic module, thực hiện các bước sau:

1. Resolve dependency bằng Maven/Gradle và xác định đường dẫn file JAR thực tế.
2. Chạy `jar --describe-module --file <jar>` để lấy tên module.
3. Kiểm tra manifest để biết có `Automatic-Module-Name` hay không.
4. Đối chiếu tên module với chỉ thị `requires` của consumer.
5. Kiểm tra module path không chứa hai JAR có cùng module name.
6. Build lại consumer để phát hiện lỗi module resolution và readability.
7. Chạy ứng dụng trên module path để xác nhận runtime sử dụng đúng artifact.

Nếu tên module thay đổi, trước tiên xác định thay đổi đến từ manifest, tên file hay việc thư viện đã chuyển sang module descriptor tường minh. Sau đó mới quyết định cập nhật `requires` hoặc chọn phiên bản artifact khác.

Không nên sửa module name dựa trên suy đoán hoặc đổi tên file một cách thủ công mà không ghi nhận quy tắc trong build. Tên module là một phần của contract mà consumer đang phụ thuộc.

## 10. Ghi nhớ

Automatic module cần tên để tham gia module graph. Nếu JAR có `Automatic-Module-Name`, JPMS dùng tên ổn định do nhà cung cấp khai báo. Nếu không có, tên được suy ra từ tên file JAR và có thể bị ảnh hưởng bởi cách đặt tên hoặc đóng gói artifact.

- `requires` tham chiếu đến module name, không phải Maven coordinates hay tên file.
- Hậu tố phiên bản theo quy tắc thông thường thường được loại bỏ khi suy ra tên; không nên giả định mọi quy ước tên file đều cho kết quả ổn định.
- Hai JAR có thể suy ra cùng module name và gây xung đột trong cùng module configuration.
- `Automatic-Module-Name` giúp giữ tên ổn định qua thay đổi tên file.
- Module descriptor tường minh là cách thể hiện ranh giới API rõ ràng hơn automatic module.
- Luôn kiểm tra artifact thực tế bằng `jar --describe-module` trước khi kết luận tên module.

Khi một dependency automatic module gây lỗi `module not found`, hãy kiểm tra tên module mà JAR thực sự công bố trước. Đó là bằng chứng trực tiếp để xác định `requires` đang tham chiếu sai tên hay build đang đưa sai artifact lên module path.
