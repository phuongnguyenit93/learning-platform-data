# Giới hạn của automatic module khi tạo runtime image bằng jlink

Java Platform Module System (JPMS) cho phép đưa thư viện JAR chưa có module descriptor lên module path dưới dạng **automatic module**. Cách này giúp ứng dụng module hóa sử dụng thư viện cũ trong giai đoạn chuyển đổi. Tuy nhiên, automatic module có một giới hạn quan trọng: **không thể được đưa vào runtime image do jlink tạo ra**. Giới hạn này vẫn áp dụng trong các JDK hiện đại.

Trong bài này, “image” là runtime image tùy biến của Java được tạo bằng jlink, không phải Docker image hay container image.

## 1. Phân biệt explicit module, automatic module và unnamed module

**Explicit module** là module có descriptor được đóng gói trong file **module-info.class**. Descriptor khai báo rõ các phụ thuộc bằng requires, các package được công khai bằng exports, quyền phản chiếu bằng opens và hợp đồng dịch vụ bằng uses/provides. Đây là dạng module mà jlink có thể phân tích và liên kết.

**Automatic module** xuất hiện khi một JAR không có module-info.class được đặt trên **module path**. Module system tạo một descriptor ngầm định cho JAR đó:

- Tên module lấy từ thuộc tính **Automatic-Module-Name** trong manifest nếu có; nếu không, tên được suy ra từ tên file JAR.
- Module tự động đọc các module khác trong cấu hình module.
- Các package trong JAR được export tự động.

Automatic module giúp thư viện chưa được module hóa tham gia vào module graph khi chạy ứng dụng. Descriptor ngầm định này không tương đương với một descriptor được tác giả thư viện khai báo và kiểm soát.

**Unnamed module** là nơi chứa các lớp trên classpath. Một JAR đặt trên classpath thuộc unnamed module; nó không trở thành automatic module chỉ vì thiếu module-info.class. Hai cách đặt JAR này có ngữ nghĩa khác nhau trong JPMS.

## 2. Vì sao jlink không liên kết automatic module?

jlink tạo một runtime image từ một tập module đã được phân giải. Ở thời điểm liên kết, công cụ cần module descriptor tường minh để xác định chính xác module nào được đưa vào image và quan hệ phụ thuộc của chúng.

Automatic module không đáp ứng yêu cầu đó. Vì vậy:

- Không thể thêm automatic module trực tiếp vào image bằng jlink.
- Nếu một explicit module có requires trỏ đến automatic module, automatic module nằm trong dependency graph cần phân giải; jlink sẽ từ chối liên kết graph đó.
- Việc đặt JAR trên module path hoặc chỉ định tên module bằng --add-modules không biến nó thành explicit module.
- Khai báo Automatic-Module-Name chỉ ổn định tên module được suy ra. JAR vẫn là automatic module nếu chưa có module-info.class.

Cần phân biệt **khả năng chạy** và **khả năng liên kết**. Một ứng dụng có thể chạy trên JDK đầy đủ với automatic module nằm trên module path, nhưng vẫn không thể đóng gói automatic module đó vào runtime image bằng jlink.

## 3. Ví dụ về thư viện tự động

Giả sử thư viện legacy-lib-1.0.jar không chứa module-info.class nhưng manifest có nội dung:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.vendor.legacy
~~~

Ứng dụng khai báo:

~~~java
module com.acme.app {
    requires com.vendor.legacy;
}
~~~

Khi cả ứng dụng và thư viện đều có trên module path, ứng dụng có thể được khởi chạy trên một JDK đầy đủ:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Lệnh trên giả định thư mục mods chứa module ứng dụng và legacy-lib-1.0.jar. Module system nhận diện thư viện là automatic module có tên com.vendor.legacy.

Nếu dùng cùng module path để tạo image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-image
~~~

jlink không thể liên kết dependency graph vì com.vendor.legacy là automatic module. Thông báo lỗi cụ thể có thể khác nhau theo phiên bản JDK, nhưng nguyên nhân vẫn là module tự động không được hỗ trợ trong image.

## 4. Ví dụ tối thiểu có thể liên kết bằng jlink

Ví dụ sau dùng một explicit module đơn giản, không có dependency bên thứ ba. Các lệnh minh họa theo cú pháp Linux/macOS.

Cấu trúc thư mục:

~~~text
demo/
├── src/
│   ├── module-info.java
│   └── com/
│       └── acme/
│           └── hello/
│               └── Main.java
~~~

Nội dung src/module-info.java:

~~~java
module com.acme.hello {
}
~~~

Nội dung src/com/acme/hello/Main.java:

~~~java
package com.acme.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a linked runtime image.");
    }
}
~~~

Dùng JDK 17 trở lên để biên dịch module và tạo image:

~~~bash
javac -d mods/com.acme.hello src/module-info.java src/com/acme/hello/Main.java
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.hello --launcher hello=com.acme.hello/com.acme.hello.Main --output runtime-image
./runtime-image/bin/hello
~~~

Kết quả chuẩn trên stdout:

~~~text
Hello from a linked runtime image.
~~~

Ví dụ này thành công vì com.acme.hello có module-info.class và dependency graph chỉ gồm các module tường minh cần thiết. Trên Windows, dấu phân cách các mục trong module path là dấu chấm phẩy (;); trên Linux và macOS là dấu hai chấm (:). JAVA_HOME phải trỏ đến JDK dùng để chạy javac và jlink.

## 5. Cách xử lý khi dependency là automatic module

### Ưu tiên dùng phiên bản thư viện có module descriptor

Kiểm tra JAR bằng:

~~~bash
jar --describe-module --file legacy-lib-1.0.jar
~~~

Nếu kết quả cho biết module được suy ra tự động, hãy kiểm tra phiên bản mới của thư viện có cung cấp module-info.class hay không. Nếu có, dùng phiên bản đó và kiểm tra lại tên module cùng các khai báo requires/exports.

### Bổ sung explicit module descriptor khi cần duy trì thư viện

Nếu thư viện chưa có phiên bản module hóa, có thể duy trì một bản fork hoặc bản đóng gói có module-info.class phù hợp. Công cụ jdeps có thể tạo bản nháp descriptor:

~~~bash
jdeps --generate-module-info generated legacy-lib-1.0.jar
~~~

Đầu ra của jdeps chỉ là điểm khởi đầu. Cần rà soát thủ công các dependency, package exports, opens cho reflection, uses/provides cho ServiceLoader và các phụ thuộc chỉ được gọi qua reflection hoặc cấu hình. Phân tích tĩnh không thể tự xác nhận đầy đủ mọi hành vi ở runtime. Sau khi biên dịch và đóng gói descriptor vào JAR, chạy lại jar --describe-module để xác nhận JAR đã là explicit module; sau đó kiểm thử ứng dụng và jlink.

### Giữ thư viện bên ngoài runtime image

Nếu chưa thể module hóa thư viện, có thể tạo image chỉ chứa các module JDK tường minh cần thiết, rồi phân phối JAR ứng dụng và thư viện automatic riêng để cung cấp lúc chạy. Khi khởi chạy, đặt các JAR cần thiết trên module path hoặc classpath theo cách ứng dụng được thiết kế.

Cách này giữ được runtime image nhỏ nhưng dependency không nằm bên trong image. Hệ thống triển khai phải quản lý phiên bản, vị trí và tính sẵn có của các JAR bên ngoài. Nếu yêu cầu là một image tự chứa cả ứng dụng lẫn dependency, cần thay thế hoặc module hóa thư viện trước khi dùng jlink.

Không có tùy chọn jlink nào có thể tự chuyển automatic module thành explicit module. Việc đổi tên JAR, thêm Automatic-Module-Name hoặc thêm --add-modules không giải quyết được giới hạn này.

## 6. Quy trình kiểm tra trước khi tạo image

1. Xác định mỗi JAR đang nằm trên classpath hay module path. Chỉ JAR trên module path mới được coi là automatic module.
2. Kiểm tra descriptor của từng thư viện bằng jar --describe-module.
3. Rà soát toàn bộ dependency graph, bao gồm dependency bắc cầu. Một automatic module ở bất kỳ vị trí nào trong graph cần liên kết đều có thể làm jlink thất bại.
4. Thay thế hoặc module hóa các dependency tự động nếu chúng phải nằm trong image.
5. Chạy jlink trong quy trình build/CI, sau đó khởi chạy ứng dụng bằng chính java trong image vừa tạo để kiểm tra các module, resource và service cần thiết.

## Kết luận

Automatic module là cơ chế tương thích hữu ích để đưa thư viện JAR cũ lên module path và chạy cùng các explicit module. Nó không phải dạng module có thể liên kết vào runtime image. Muốn tạo image bằng jlink, toàn bộ module thuộc dependency graph cần liên kết phải có descriptor tường minh. Nếu chưa thể đáp ứng điều kiện đó, hãy giữ dependency ở bên ngoài image hoặc chuyển sang phiên bản thư viện đã được module hóa.