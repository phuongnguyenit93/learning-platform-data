# Theo dõi quá trình phân giải bằng --show-module-resolution

## 1. Module resolution diễn ra khi nào?

Khi khởi chạy một ứng dụng dùng Java Platform Module System (JPMS), Java phải xác định những module nào thuộc đồ thị module của ứng dụng. Quá trình này gọi là *module resolution* (phân giải module).

Từ các module gốc, runtime tìm những module được yêu cầu trực tiếp và gián tiếp qua các directive **requires**. Runtime cũng xét các module quan sát được trên module path, các tùy chọn bổ sung như **--add-modules** và quan hệ dịch vụ giữa **uses** với **provides** khi service binding được thực hiện.

Kết quả là một đồ thị module mà ứng dụng có thể đọc theo các quy tắc JPMS. Đồ thị này quyết định những module nào hiện diện và những quan hệ phụ thuộc nào được thiết lập.

Tùy chọn **--show-module-resolution** của Java launcher in thông tin phân giải trong lúc ứng dụng khởi động. Đây là công cụ chẩn đoán hữu ích khi cần biết:

- Module nào được chọn làm module gốc.
- Module nào được nạp vì một module khác khai báo **requires**.
- Module nào được thêm do service binding.
- Module được tìm thấy ở đâu: trong runtime image hay trên module path.
- Vì sao một module dự kiến không xuất hiện trong đồ thị.

Tùy chọn này được giới thiệu cùng JPMS từ Java 9 và vẫn dùng được trong các JDK hiện đại.

## 2. Cách sử dụng

Cú pháp cơ bản:

~~~bash
java --show-module-resolution --module-path <module-path> --module <module-name>/<main-class>
~~~

Các thành phần:

- **java** khởi chạy ứng dụng.
- **--show-module-resolution** yêu cầu in thông tin phân giải module trong giai đoạn khởi động.
- **--module-path** chỉ định thư mục hoặc JAR chứa các module ứng dụng.
- **--module** (viết tắt **-m**) chỉ định module và lớp main cần chạy.

Ví dụ:

~~~bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

Trong lệnh trên, **com.example.app** là module được chọn để khởi chạy và **com.example.app.Main** là lớp chứa phương thức main. Runtime bắt đầu phân giải từ module gốc này, sau đó xử lý các dependency của nó.

Tùy chọn chẩn đoán không thay đổi module descriptor, không tự thêm dependency và không cấp quyền truy cập package. Nó chỉ hiển thị kết quả phân giải mà runtime thực hiện theo cấu hình hiện tại.

## 3. Đọc các dòng trong kết quả

Một kết quả điển hình có thể chứa các dạng dòng sau:

~~~text
root com.example.app file:///.../mods/com.example.app/
com.example.app requires com.example.math file:///.../mods/com.example.math/
com.example.app requires mandated java.base jrt:/java.base
com.example.math requires mandated java.base jrt:/java.base
~~~

Đây là ví dụ minh họa. Đường dẫn, thứ tự dòng và các module xuất hiện thực tế phụ thuộc JDK, module path và đồ thị module của ứng dụng.

### 3.1. Dòng root

~~~text
root com.example.app file:///.../mods/com.example.app/
~~~

Dòng **root** cho biết module gốc được đưa vào đồ thị phân giải. Khi chạy bằng **--module com.example.app/...**, module **com.example.app** là một root module.

Một ứng dụng có thể có thêm module gốc do các tùy chọn như **--add-modules** chỉ định. Vì vậy, không nên mặc định mọi đồ thị chỉ có một root.

### 3.2. Dòng requires

~~~text
com.example.app requires com.example.math file:///.../mods/com.example.math/
~~~

Dòng này cho biết **com.example.app** khai báo dependency tới **com.example.math**. Runtime đã tìm thấy module math tại vị trí được hiển thị và đưa nó vào đồ thị.

Các dependency có thể tiếp tục kéo theo module khác. Ví dụ, nếu math khai báo **requires com.example.common**, runtime tiếp tục phân giải common và những dependency mà common yêu cầu.

### 3.3. Dòng requires mandated

~~~text
com.example.math requires mandated java.base jrt:/java.base
~~~

Mỗi named module đều có quan hệ phụ thuộc bắt buộc tới **java.base**, dù module descriptor không viết directive này một cách tường minh. Vì vậy, kết quả thường hiển thị **requires mandated java.base**.

Tiền tố **mandated** biểu thị dependency được quy định bắt buộc bởi nền tảng. Nó không có nghĩa là người phát triển đã tự khai báo một dòng requires thông thường trong module-info.java.

### 3.4. Dòng binds

Khi quá trình service binding bổ sung module cung cấp dịch vụ, kết quả có thể xuất hiện dòng dạng:

~~~text
some.consumer.module binds some.provider.module file:///.../mods/some.provider.module/
~~~

Dòng **binds** cho biết module provider được đưa vào đồ thị do quan hệ dịch vụ. Điều này liên quan đến khai báo **uses** ở module tiêu thụ và **provides ... with ...** ở module cung cấp.

Không phải ứng dụng nào cũng có dòng binds. Nếu ứng dụng không có service binding làm phát sinh provider bổ sung, phần này có thể không xuất hiện.

### 3.5. Đọc vị trí module

Một số tiền tố vị trí thường gặp:

| Vị trí | Ý nghĩa |
|---|---|
| **jrt:/java.base** | Module thuộc runtime image của JDK. |
| **file:///.../mods/com.example.math/** | Module dạng exploded module trong thư mục trên file system. |
| **file:///.../library.jar** | Module được nạp từ một JAR trên module path. |

Đường dẫn giúp xác nhận runtime đang lấy module từ đúng JDK hoặc thư mục ứng dụng. Nếu cùng một module có nhiều bản ở các vị trí khác nhau, cần kiểm tra module path và cách runtime chọn module.

## 4. Ví dụ hoàn chỉnh: quan sát đồ thị của hai module

Ta tạo một thư viện math và một ứng dụng app. App yêu cầu math; cả hai đều là named module.

Cấu trúc thư mục:

~~~text
project/
├── src/
│   ├── com.example.math/
│   │   ├── module-info.java
│   │   └── com/example/math/Calculator.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
~~~

### 4.1. Module thư viện

File **src/com.example.math/module-info.java**:

~~~java
module com.example.math {
    exports com.example.math;
}
~~~

File **src/com.example.math/com/example/math/Calculator.java**:

~~~java
package com.example.math;

public class Calculator {
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

Module math export package chứa API Calculator để module app có thể sử dụng.

### 4.2. Module ứng dụng

File **src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.math;
}
~~~

File **src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

import com.example.math.Calculator;

public class Main {
    public static void main(String[] args) {
        Calculator calculator = new Calculator();
        System.out.println(calculator.add(19, 23));
    }
}
~~~

Directive **requires com.example.math** tạo dependency từ app tới math. Khi app là module gốc, math phải được phân giải để app có thể chạy.

### 4.3. Biên dịch và chạy với module resolution trace

Chạy tại thư mục **project** bằng JDK 17 trở lên:

~~~bash
javac --module-source-path src -d mods -m com.example.math,com.example.app
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

Lệnh javac biên dịch hai module và đặt đầu ra vào thư mục **mods**. Lệnh java khởi chạy app, đồng thời in trace phân giải module.

Phần trace có thể tương tự:

~~~text
root com.example.app file:///.../mods/com.example.app/
com.example.app requires com.example.math file:///.../mods/com.example.math/
com.example.app requires mandated java.base jrt:/java.base
com.example.math requires mandated java.base jrt:/java.base
~~~

Sau phần chẩn đoán, chương trình in kết quả:

~~~text
42
~~~

Các dòng trace ở trên chỉ minh họa những quan hệ chính của ví dụ. URI đầy đủ và thứ tự dòng có thể khác trên Windows, Linux, macOS hoặc giữa các bản JDK.

## 5. Kết hợp với các tùy chọn module khác

**--show-module-resolution** hữu ích nhất khi quan sát cùng những tùy chọn quyết định module graph.

### 5.1. Thêm module gốc bằng --add-modules

~~~bash
java --show-module-resolution --module-path mods --add-modules com.example.tools --module com.example.app/com.example.app.Main
~~~

**--add-modules** yêu cầu runtime đưa module được nêu vào tập module gốc hoặc tập module cần phân giải theo ngữ cảnh khởi chạy. Trace giúp xác nhận module đó có được tìm thấy và đưa vào đồ thị hay không.

Tùy chọn này thường hữu ích khi module được dùng gián tiếp qua service hoặc khi ứng dụng cần một module có mặt dù không có quan hệ requires trực tiếp từ module gốc.

### 5.2. Giới hạn tập module quan sát được bằng --limit-modules

**--limit-modules** giới hạn tập module hệ thống có thể quan sát được trong quá trình phân giải. Nếu dependency bắt buộc không còn nằm trong tập module có thể quan sát, quá trình khởi chạy có thể thất bại.

Khi dùng tùy chọn này, hãy đọc lỗi cùng trace để xác định module nào không còn khả dụng. Không nên thêm giới hạn chỉ để làm đồ thị ngắn hơn nếu ứng dụng vẫn cần những dependency đã bị loại bỏ.

### 5.3. Kết hợp module path và module gốc

Ví dụ trên Windows:

~~~bash
java --show-module-resolution --module-path "mods;plugins" --add-modules com.example.plugin --module com.example.app/com.example.app.Main
~~~

Trên Windows, dấu phân cách nhiều thư mục trong module path thường là dấu chấm phẩy. Trên Linux và macOS, dùng dấu hai chấm:

~~~bash
java --show-module-resolution --module-path "mods:plugins" --add-modules com.example.plugin --module com.example.app/com.example.app.Main
~~~

Nếu một module không xuất hiện, hãy xác nhận nó thực sự nằm trong module path được cung cấp, tên module khớp với module descriptor hoặc tên automatic module, và module đó thuộc tập module được phân giải.

## 6. Quy trình chẩn đoán khi module không được phân giải

Khi ứng dụng báo không tìm thấy module hoặc khởi chạy thất bại, có thể kiểm tra theo trình tự sau:

1. Xác định module gốc trong lệnh chạy. Kiểm tra giá trị sau **--module** hoặc **-m**.
2. Kiểm tra module path. Đảm bảo thư mục hoặc JAR chứa module cần thiết đã được đưa vào **--module-path**.
3. Đọc các dòng **requires** để xác định dependency trực tiếp và gián tiếp.
4. Kiểm tra tên module. Tên trong directive requires phải khớp với tên module thực tế, không phải tên package hay tên class.
5. Kiểm tra **--add-modules** nếu module cần được đưa vào đồ thị như một root hoặc được yêu cầu bổ sung.
6. Kiểm tra **--limit-modules** nếu một dependency hệ thống không còn nằm trong tập module có thể quan sát.
7. Nếu ứng dụng dùng ServiceLoader, kiểm tra khai báo **uses** và **provides** cùng provider module trên module path.

Ví dụ, nếu trace có:

~~~text
root com.example.app file:///.../mods/com.example.app/
~~~

nhưng không có dòng dependency mà bạn mong đợi, hãy kiểm tra module descriptor của app và xem module đó có thực sự được yêu cầu hay được thêm qua tùy chọn khởi chạy hay không.

Nếu trace đã cho thấy module được phân giải nhưng chương trình vẫn báo package không truy cập được, vấn đề có thể nằm ở ranh giới truy cập. Khi đó, kiểm tra **exports**, qualified exports hoặc **opens** theo nhu cầu reflection. **--show-module-resolution** không thay thế các directive này và không tự cấp quyền truy cập package.

## 7. Phân biệt với các công cụ chẩn đoán khác

| Công cụ | Mục đích |
|---|---|
| **--show-module-resolution** | Hiển thị module gốc, dependency và thông tin service binding trong quá trình khởi động. |
| **--module-path** | Chỉ định nơi runtime tìm các module ứng dụng. |
| **--add-modules** | Bổ sung module cần phân giải ngoài tập module gốc mặc định. |
| **--limit-modules** | Giới hạn tập module hệ thống có thể quan sát. |
| **--validate-modules** | Kiểm tra tính nhất quán của module path theo chức năng validation của Java launcher. |
| **jdeps** | Phân tích dependency của class hoặc JAR để hỗ trợ chuyển đổi và thiết kế module. |

Các công cụ trên bổ trợ nhau. Trace cho biết runtime đang phân giải điều gì khi khởi động; **jdeps** hữu ích khi cần khảo sát dependency tĩnh trước khi thiết kế module descriptor.

## 8. Lưu ý khi sử dụng trong môi trường thực tế

- Dùng **--show-module-resolution** khi điều tra lỗi khởi động, kiểm tra dependency hoặc xác nhận cấu hình module path.
- Trace có thể chứa nhiều dòng nếu ứng dụng có đồ thị lớn hoặc nhiều module dịch vụ. Tập trung vào root, requires và binds liên quan đến module đang điều tra.
- Vị trí module được hiển thị là manh mối quan trọng để phát hiện nhầm JDK, nhầm thư mục mods hoặc nạp nhầm phiên bản JAR.
- Nội dung và thứ tự trace có thể khác theo JDK và cấu hình. Hãy xem đây là đầu ra chẩn đoán dành cho người vận hành, không phụ thuộc vào chuỗi output cố định để viết logic ứng dụng.
- Tùy chọn này không làm ứng dụng chạy nhanh hơn, không sửa dependency sai và không thay đổi quyền truy cập.
- Khi thu thập log, có thể chuyển hướng luồng lỗi để lưu trace riêng, ví dụ:

~~~bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main 2> resolution.log
~~~

Trace được tách khỏi output chuẩn của ứng dụng trong cách chạy thông thường. Nếu chạy qua IDE hoặc hệ thống triển khai, vị trí hiển thị có thể phụ thuộc cách công cụ đó thu thập stdout và stderr.

## 9. Kết luận

**--show-module-resolution** giúp quan sát đồ thị module mà Java xây dựng khi khởi chạy ứng dụng modular. Bằng cách đọc các dòng **root**, **requires**, **requires mandated** và **binds**, có thể xác định module gốc, dependency được phân giải, module hệ thống và provider được bổ sung qua service binding.

Khi debug, hãy dùng trace cùng module path và các tùy chọn điều khiển module graph để tìm đúng nguyên nhân. Nếu module đã được phân giải nhưng API vẫn không truy cập được, hãy kiểm tra ranh giới **exports** và **opens** riêng biệt. Công cụ này cung cấp bằng chứng về quá trình phân giải, giúp việc cấu hình và vận hành JPMS rõ ràng hơn.
