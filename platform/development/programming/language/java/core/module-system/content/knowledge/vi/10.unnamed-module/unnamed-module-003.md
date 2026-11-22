# Named module không tự đọc unnamed module

Trong Java Platform Module System (JPMS), code trên classpath thuộc về **unnamed module**. Một named module có tên rõ ràng trong `module-info.java`, còn unnamed module không có tên module để khai báo trong `requires`.

Sự khác biệt này dẫn tới một quy tắc quan trọng: **unnamed module có thể đọc các named module trong boot layer theo quy tắc của JPMS, nhưng named module không tự động đọc unnamed module**. Vì vậy, một thư viện cũ nằm trên classpath có thể được code classpath sử dụng bình thường, nhưng khi chuyển ứng dụng sang named module, module đó có thể không truy cập được thư viện.

Hiểu đúng quy tắc này giúp giải thích lỗi khi chuyển từ classpath sang module path và chọn cách tích hợp thư viện legacy phù hợp.

## 1. Unnamed module hình thành từ đâu?

Một chương trình Java chạy bằng classpath có thể được khởi động như sau:

~~~bash
java --class-path app.jar:legacy-library.jar com.acme.app.Main
~~~

Các class được nạp từ classpath bởi một class loader sẽ thuộc unnamed module gắn với class loader đó. Unnamed module:

- Không có tên module như `com.acme.app`.
- Không có file `module-info.class` mô tả dependency.
- Export tất cả package của nó theo quy tắc unnamed module.
- Có readability rộng theo quy tắc JPMS: unnamed module đọc các named module trong boot layer và các unnamed module.

Trong ứng dụng thông thường, các thư viện đặt trên classpath được nạp bởi application class loader và thuộc unnamed module của class loader đó. Về mặt API, có thể kiểm tra bằng `Class.getModule()`.

Ví dụ:

~~~java
Module module = Main.class.getModule();

System.out.println(module.isNamed()); // false
System.out.println(module.getName()); // null
~~~

Kết quả `isNamed() == false` cho biết class thuộc unnamed module.

Lưu ý: unnamed module được gắn với class loader. Nếu ứng dụng có nhiều class loader, mỗi class loader có unnamed module riêng. Không nên hiểu rằng toàn bộ classpath của mọi class loader trong JVM luôn thuộc một unnamed module duy nhất.

## 2. Named module và unnamed module không có quan hệ đọc tự động hai chiều

Giả sử ứng dụng có hai phần:

- `com.acme.app`: named module, được khai báo bằng `module-info.java`.
- `legacy-library.jar`: thư viện cũ đặt trên classpath, thuộc unnamed module.

Graph có thể hình dung:

~~~text
Unnamed module  ──reads──>  named modules trong boot layer

Named module    - - -X- - -> unnamed module
                 không tự động đọc
~~~

Một named module không thể viết:

~~~java
module com.acme.app {
    requires unnamed;
}
~~~

vì unnamed module không có tên để đưa vào directive `requires`.

Ngay cả khi `legacy-library.jar` đã có mặt trong `--class-path`, điều đó cũng không tự tạo readability từ `com.acme.app` tới unnamed module. Classpath xác định nơi tìm class; nó không thay thế quan hệ module được khai báo trong module graph.

### Vì sao code classpath cũ vẫn chạy?

Trong ứng dụng chạy hoàn toàn trên classpath, các class thuộc unnamed module. Unnamed module có thể đọc các named module trong boot layer và các unnamed module khác theo quy tắc của nền tảng. Vì vậy, code legacy có thể sử dụng các thư viện trên classpath mà không cần descriptor.

Khi chuyển riêng một phần ứng dụng thành named module, hướng phụ thuộc thay đổi. Named module cần có quan hệ readability rõ ràng tới dependency. Nếu dependency vẫn nằm trên classpath, nó thuộc unnamed module và named module không tự đọc được nó.

Đây là một khác biệt thường gặp khi modularize ứng dụng cũ.

## 3. Ví dụ lỗi khi named module sử dụng thư viện trên classpath

Giả sử thư viện legacy có class:

~~~java
package com.legacy.format;

public final class LegacyFormatter {
    private LegacyFormatter() {
    }

    public static String format(String value) {
        return "[legacy] " + value;
    }
}
~~~

Thư viện được đóng gói thành `legacy-library.jar` và đặt trên classpath.

Ứng dụng mới có named module:

~~~java
module com.acme.app {
}
~~~

Code ứng dụng:

~~~java
package com.acme.app;

import com.legacy.format.LegacyFormatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(LegacyFormatter.format("JPMS"));
    }
}
~~~

Nếu chỉ thêm JAR vào classpath khi biên dịch và chạy, named module `com.acme.app` vẫn không tự đọc unnamed module chứa `LegacyFormatter`. Compiler có thể báo package không nhìn thấy hoặc không được module đọc; runtime cũng không có quan hệ readability cần thiết.

Đây không phải lỗi do class `LegacyFormatter` thiếu `public`. Lớp có thể public, package có thể tồn tại trên classpath, nhưng named module vẫn cần quyền đọc module chứa lớp đó.

## 4. Dùng --add-reads để tạo readability tạm thời

Khi cần tích hợp thư viện legacy mà chưa thể chuyển nó thành named module, có thể bổ sung quan hệ đọc bằng tùy chọn `--add-reads`.

Cú pháp:

~~~text
--add-reads source-module=target-module
~~~

Trong trường hợp target là các unnamed module, dùng tên đặc biệt `ALL-UNNAMED`:

~~~text
--add-reads com.acme.app=ALL-UNNAMED
~~~

Điều này cho phép named module `com.acme.app` đọc các unnamed module phù hợp trong cấu hình chạy. `ALL-UNNAMED` là token đặc biệt của tùy chọn launcher/compiler, không phải tên module có thể khai báo trong `module-info.java`.

### Biên dịch

Giả sử cấu trúc:

~~~text
project/
├── legacy-library.jar
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    └── các module dependency khác
~~~

Có thể biên dịch module app với classpath legacy và bổ sung readability:

~~~bash
javac \
  --module-path mods \
  --class-path legacy-library.jar \
  --add-reads com.acme.app=ALL-UNNAMED \
  --module-source-path src \
  -d out \
  -m com.acme.app
~~~

`--class-path` đưa thư viện legacy vào nơi compiler tìm class. `--add-reads` cho phép module đang biên dịch đọc unnamed module tương ứng.

### Chạy ứng dụng

Khi chạy, cần cấu hình lại classpath và readability cho JVM:

~~~bash
java \
  --module-path out:mods \
  --class-path legacy-library.jar \
  --add-reads com.acme.app=ALL-UNNAMED \
  --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
[legacy] JPMS
~~~

Trên Windows, dấu phân cách nhiều đường dẫn trong classpath/module path là dấu chấm phẩy (`;`); trên Linux và macOS là dấu hai chấm (`:`).

Cần cấp quyền ở cả compile-time và run-time khi cả hai giai đoạn đều cần named module tham chiếu tới class trên classpath. Chỉ thêm `--add-reads` khi chạy không thể sửa lỗi compile đã xảy ra trước đó; chỉ thêm ở compile-time cũng không tự cấu hình JVM khi khởi động.

## 5. --add-reads không giống requires hoặc exports

Các cơ chế sau giải quyết những vấn đề khác nhau:

| Cơ chế | Mục đích | Phạm vi |
| --- | --- | --- |
| `requires other.module` | Khai báo dependency tới named module | Trong `module-info.java`, có hiệu lực như một phần descriptor |
| `requires transitive other.module` | Truyền readability tới consumer của module hiện tại | Trong `module-info.java` |
| `--add-reads app=ALL-UNNAMED` | Bổ sung quan hệ đọc từ named module tới unnamed modules | Cấu hình compile/run tương ứng |
| `exports package.name` | Công khai package cho code Java thông thường | Trong descriptor của module sở hữu package |
| `--add-exports` | Bổ sung quyền truy cập package public chưa export | Cấu hình compile/run tương ứng |
| `opens package.name` | Cho phép deep reflection vào package | Trong descriptor của module sở hữu package |
| `--add-opens` | Bổ sung quyền deep reflection ở runtime | Cấu hình JVM khi chạy |

Với thư viện nằm trên classpath, unnamed module export các package của nó theo quy tắc riêng. Vấn đề chính khi named module muốn sử dụng thư viện đó là readability; `--add-reads` giải quyết quan hệ này.

Ngược lại, nếu dependency là một named module nhưng package cần dùng không được export, thêm `--add-reads` chưa đủ. Khi đó cần xem xét `exports` hoặc `--add-exports` tùy quyền kiểm soát descriptor và giai đoạn thực thi.

## 6. Phân biệt unnamed module và automatic module

Hai khái niệm này thường bị nhầm lẫn khi chuyển thư viện cũ sang JPMS.

| Đặc điểm | Unnamed module | Automatic module |
| --- | --- | --- |
| Nguồn phổ biến | Classpath | JAR không có descriptor đặt trên module path |
| Có tên module | Không | Có |
| Có thể dùng trong `requires` | Không | Có |
| Descriptor | Không có `module-info.class` | Descriptor được suy ra tự động |
| Package | Export theo quy tắc unnamed module | Export các package theo quy tắc automatic module |
| Được named module đọc bằng `requires` | Không thể vì không có tên | Có thể khai báo `requires automatic.name` |

Một JAR có manifest chứa:

~~~text
Automatic-Module-Name: com.legacy.format
~~~

vẫn thuộc unnamed module nếu nó được đặt trên classpath. Thuộc tính `Automatic-Module-Name` chỉ được dùng để xác định tên automatic module khi JAR được đặt trên module path và được xử lý như automatic module.

Nếu chuyển `legacy-library.jar` sang module path, có thể khai báo:

~~~java
module com.acme.app {
    requires com.legacy.format;
}
~~~

Tên module phải đúng với tên automatic module mà JAR công bố hoặc tên được suy ra. Với thư viện quan trọng, nên kiểm tra tên thực tế bằng:

~~~bash
jar --describe-module --file legacy-library.jar
~~~

Đặt JAR trên module path không biến nó thành explicit named module. Nếu JAR không có `module-info.class`, nó vẫn là automatic module.

## 7. Cách kiểm tra module nào đang chứa class

Có thể dùng Java Reflection API để kiểm tra module của một class:

~~~java
Module appModule = Main.class.getModule();
Module legacyModule = LegacyFormatter.class.getModule();

System.out.println("App named: " + appModule.isNamed());
System.out.println("App name: " + appModule.getName());

System.out.println("Legacy named: " + legacyModule.isNamed());
System.out.println("Legacy name: " + legacyModule.getName());

System.out.println("App reads legacy: "
    + appModule.canRead(legacyModule));
~~~

Nếu `Main` thuộc named module còn `LegacyFormatter` thuộc unnamed module:

- `appModule.isNamed()` trả về `true`.
- `legacyModule.isNamed()` trả về `false`.
- `legacyModule.getName()` trả về `null`.
- `appModule.canRead(legacyModule)` thường là `false` nếu chưa có `--add-reads`, và có thể là `true` khi quan hệ đọc đã được bổ sung đúng.

Có thể bật log phân giải module khi chạy:

~~~bash
java --show-module-resolution \
  --module-path out \
  --class-path legacy-library.jar \
  --add-reads com.acme.app=ALL-UNNAMED \
  --module com.acme.app/com.acme.app.Main
~~~

Log giúp xem module nào được phân giải. Để xác định class cụ thể thuộc module nào, `Class.getModule()` và `Module.isNamed()` thường trực tiếp hơn.

## 8. Hướng xử lý lâu dài khi chuyển ứng dụng sang JPMS

`--add-reads` là cầu nối tương thích hữu ích, nhưng không nên trở thành cách khai báo dependency chính cho mọi thư viện. Có thể chọn một trong các hướng sau:

**Giữ thư viện trên classpath trong giai đoạn chuyển tiếp.** Dùng `--add-reads module=ALL-UNNAMED` cho module cần tích hợp, đồng thời giới hạn phạm vi sử dụng classpath legacy.

**Dùng automatic module.** Đặt JAR trên module path và khai báo `requires` theo tên automatic module. Cách này tạo quan hệ named-module rõ hơn nhưng automatic module có boundary khá rộng, vì vậy nên xem là bước chuyển tiếp.

**Modularize thư viện.** Bổ sung `module-info.java`, export API cần thiết và giữ package implementation không export. Khi đó consumer khai báo `requires` theo tên module ổn định.

**Tách API và implementation.** Nếu thư viện là một integration lớn, tạo module API nhỏ để module nghiệp vụ phụ thuộc vào hợp đồng, còn adapter/provider triển khai hợp đồng đó. Cách này giảm việc module nghiệp vụ phải biết chi tiết thư viện legacy.

Khi chọn hướng xử lý, hãy cân nhắc khả năng sửa dependency, mức độ ổn định của API và số module cần dùng thư viện. Không nên mở rộng `ALL-UNNAMED` cho mọi module nếu chỉ một module cần tương thích với thư viện cũ.

## 9. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Named module không import được package trên classpath | Named module không tự đọc unnamed module | Thêm `--add-reads module=ALL-UNNAMED` ở compile-time và runtime hoặc modularize dependency |
| `requires com.legacy.format` báo không tìm thấy module | JAR vẫn nằm trên classpath, không phải named/automatic module trên module path | Chuyển JAR sang module path và kiểm tra tên module, hoặc tiếp tục dùng unnamed module với `--add-reads` |
| Đã thêm `--add-reads` nhưng vẫn không truy cập được package của named module | Package của module đích chưa export | Kiểm tra `exports` hoặc `--add-exports` |
| Compile thành công nhưng runtime lỗi | Runtime thiếu classpath hoặc thiếu quan hệ đọc | Kiểm tra cả `--class-path` và `--add-reads` ở lệnh chạy |
| Class được nạp bởi class loader khác | Class thuộc unnamed module khác với module mà cấu hình dự kiến | Kiểm tra `Class.getClassLoader()` và `Class.getModule()` |

## Kết luận

Named module không tự động đọc unnamed module vì unnamed module không có tên để khai báo bằng `requires`. Đây là lý do code trên classpath có thể chạy tốt trong ứng dụng cũ nhưng gặp lỗi khi một phần ứng dụng chuyển thành named module.

Trong giai đoạn tương thích, `--add-reads named.module=ALL-UNNAMED` có thể bổ sung readability ở compile-time và runtime. Về lâu dài, nên chuyển dependency thành automatic hoặc explicit named module, hoặc tách một API nhỏ để module nghiệp vụ phụ thuộc vào hợp đồng ổn định. Khi chẩn đoán, hãy kiểm tra class thực sự thuộc module nào và tách bạch readability với exports/opens.
