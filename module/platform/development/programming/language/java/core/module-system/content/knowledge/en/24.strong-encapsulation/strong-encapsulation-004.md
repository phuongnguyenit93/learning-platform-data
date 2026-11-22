# IllegalAccessError sau khi module graph thay đổi

Khi một ứng dụng Java đã compile thành công nhưng sau đó gặp `IllegalAccessError` lúc chạy, nguyên nhân có thể nằm ở sự thay đổi của module graph hoặc module descriptor giữa thời điểm compile và runtime. Một module từng đọc được module khác, hoặc từng được phép truy cập một package, có thể không còn quyền đó trong cấu hình runtime mới.

`IllegalAccessError` là một lỗi liên kết ở runtime thuộc nhóm `LinkageError`. Nó thường cho biết bytecode đang cố truy cập một class hoặc member mà JVM không cho phép truy cập theo cấu trúc thực tế đang được nạp. Với JPMS, cần kiểm tra ít nhất hai điều kiện: **readability** (module gọi có đọc module đích hay không) và **accessibility** (package có được module đích export cho module gọi hay không).

Bài này tập trung vào lỗi phát sinh sau khi module graph thay đổi: nâng cấp thư viện, thay đổi `module-info.java`, thay module path, hoặc chạy bytecode cũ với descriptor mới.

## 1. IllegalAccessError là gì?

`IllegalAccessError` là một `LinkageError` được JVM ném khi một class cố truy cập một class hoặc member mà quyền truy cập thực tế không cho phép. Lỗi thường xuất hiện khi liên kết symbolic reference trong bytecode với class/member ở runtime.

Ví dụ thông báo có thể có dạng:

~~~text
java.lang.IllegalAccessError:
  class com.acme.app.Main (in module com.acme.app)
  cannot access class com.acme.library.internal.Helper
  (in module com.acme.library)
  because module com.acme.library does not export
  com.acme.library.internal to module com.acme.app
~~~

Thông báo này cho biết:

- Class gọi là `com.acme.app.Main`, thuộc module `com.acme.app`.
- Class được truy cập là `com.acme.library.internal.Helper`, thuộc module `com.acme.library`.
- Package `com.acme.library.internal` không được export cho module gọi.
- JVM từ chối truy cập khi liên kết/chạy bytecode.

Một dạng khác có thể nhắc tới việc module gọi không đọc module đích. Khi đó cần kiểm tra cạnh readability trong module graph.

Không phải mọi `IllegalAccessError` đều do JPMS. Lỗi cũng có thể xảy ra khi class, method hoặc field không còn public hoặc không còn đáp ứng quy tắc truy cập Java thông thường. Hãy đọc đầy đủ tên class, module, package và member trong thông báo trước khi chọn cách sửa.

## 2. Hai điều kiện quan trọng của JPMS: readability và exports

Để một class trong module A sử dụng public type thuộc module B, thông thường cần thỏa mãn cả hai điều kiện:

1. Module A **reads** module B.
2. Module B **exports** package chứa public type cho module A.

Ví dụ:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

Ứng dụng có thể sử dụng public type trong package `com.acme.library.api`. Cạnh `requires` tạo readability từ `com.acme.app` tới `com.acme.library`; chỉ thị `exports` cho phép truy cập API công khai trong package.

Nếu bỏ `requires com.acme.library`, module app có thể không đọc module library. Nếu bỏ `exports com.acme.library.api`, module app có thể đọc module library nhưng không được truy cập kiểu trong package đó. Hai lỗi có nguyên nhân khác nhau và cần sửa ở đúng cạnh.

### Readability không đồng nghĩa với accessibility

- `requires` điều khiển module nào được module hiện tại đọc.
- `exports` điều khiển package nào được module khác truy cập theo quy tắc Java thông thường.
- `opens` cấp quyền truy cập phản chiếu sâu (deep reflection) cho package; nó không thay thế `exports` cho lời gọi API thông thường.

Một package có thể được export cho module A nhưng không export cho module B. Đây là qualified export:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.app;
}
~~~

Chỉ module `com.acme.app` được truy cập package `com.acme.library.spi` theo chỉ thị qualified export.

## 3. Vì sao module graph thay đổi lại gây lỗi?

Có một số tình huống thường gặp.

### Descriptor của dependency thay đổi

Ở phiên bản thư viện cũ:

~~~java
module com.acme.library {
    exports com.acme.library.internal;
}
~~~

Ứng dụng vô tình sử dụng class trong package `internal`. Sau đó thư viện đổi descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Package `com.acme.library.internal` không còn được export. Bytecode ứng dụng đã compile trước đó vẫn chứa symbolic reference tới class cũ, nhưng khi chạy với phiên bản mới, JVM không còn cho phép truy cập. Kết quả có thể là `IllegalAccessError`.

Đây là dấu hiệu ứng dụng đang phụ thuộc vào một package không còn thuộc API được công khai.

### Cạnh requires bị loại bỏ hoặc thay đổi

Nếu module app trước đây đọc module library thông qua `requires`, `requires transitive`, hoặc một cấu hình bổ sung, nhưng descriptor/runtime graph mới không còn cạnh readability tương ứng, việc truy cập class ở runtime có thể thất bại.

Không nên dựa vào `requires transitive` của một module trung gian nếu ứng dụng thực sự dùng trực tiếp API của dependency. Hãy khai báo dependency trực tiếp khi module của bạn sử dụng kiểu thuộc module đó.

### Runtime nạp nhầm phiên bản module

Build có thể compile với một phiên bản JAR nhưng lệnh chạy lại dùng module path khác. Hai phiên bản có cùng module name nhưng descriptor và package export khác nhau. Launcher resolve module từ nguồn được tìm thấy trong cấu hình runtime, khiến quyền truy cập khác với lúc compile.

### Thay đổi từ classpath sang module path

Một thư viện từng chạy trên classpath có thể thuộc unnamed module và được truy cập theo quy tắc classpath. Khi đưa thư viện lên module path, nó trở thành named module (hoặc automatic module), nên quy tắc readability và exports được áp dụng rõ ràng hơn. Code cũ có thể bộc lộ dependency vào package nội bộ.

### Nâng cấp JDK và strong encapsulation

Các phiên bản Java mới đã tăng cường đóng gói nội bộ của JDK. Từ JDK 17, cơ chế `--illegal-access` không còn khôi phục chế độ truy cập rộng như các bản cũ. Ứng dụng truy cập JDK internal API có thể cần thay bằng API công khai hoặc cấu hình export/open có chủ đích trong thời gian chuyển đổi.

## 4. Phân biệt IllegalAccessError với lỗi truy cập reflection

Không phải lỗi truy cập nào cũng là `IllegalAccessError`.

| Lỗi | Thời điểm/cách phát sinh thường gặp | Ý nghĩa |
|---|---|---|
| `IllegalAccessError` | Runtime linkage/bytecode access | Bytecode truy cập class hoặc member không được phép |
| `IllegalAccessException` | Reflection API như `Method.invoke` trong một số trường hợp | Reflection không thể thực hiện thao tác truy cập |
| `InaccessibleObjectException` | `setAccessible(true)` hoặc `trySetAccessible()` không thể mở quyền truy cập sâu | Package/module không mở cho caller |
| `ClassNotFoundException` | Nạp class bằng tên, thường qua API class loading | Không tìm thấy class |
| `NoClassDefFoundError` | Linkage/runtime sau khi class cần thiết không sẵn sàng | Class definition cần dùng không thể được tìm/nạp |
| `NoSuchMethodError` | Runtime linkage | Bytecode tham chiếu method không tồn tại trong phiên bản class đang nạp |

Ví dụ reflection:

~~~java
Field field = SomeType.class.getDeclaredField("secret");
field.setAccessible(true);
~~~

Nếu package chứa `SomeType` không được mở cho module gọi, thao tác này có thể ném `InaccessibleObjectException`. Đây là vấn đề `opens` và deep reflection.

Ngược lại, nếu code gọi trực tiếp một public class trong package không được export, vấn đề là `exports` và có thể dẫn tới `IllegalAccessError`.

Không dùng `--add-opens` để sửa mọi `IllegalAccessError`. Hãy xác định lỗi là truy cập bytecode thông thường hay reflection trước.

## 5. Quy trình chẩn đoán

Khi lỗi chỉ xuất hiện ở runtime hoặc sau khi nâng cấp module, hãy thu thập bằng chứng theo thứ tự.

### Bước 1: Đọc đầy đủ stack trace

Ghi lại:

- Class gọi và module sở hữu class gọi.
- Class/member bị truy cập và module sở hữu nó.
- Package bị từ chối.
- Thông báo nói tới thiếu readability, thiếu export hay quyền truy cập class/member thông thường.
- JAR hoặc đường dẫn xuất hiện trong stack trace.

Đừng chỉ nhìn dòng đầu tiên rồi kết luận rằng cần thêm `--add-exports`.

### Bước 2: Xem module graph thực tế lúc chạy

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Output giúp xác nhận root module, dependency được resolve và vị trí module được chọn. Nếu module library đến từ đường dẫn khác với dự kiến, hãy kiểm tra module path và artifact đang chạy.

### Bước 3: Mô tả descriptor của hai module

~~~bash
java --module-path mods --describe-module com.acme.app
java --module-path mods --describe-module com.acme.library
~~~

Kiểm tra:

- App có `requires com.acme.library` hay không.
- Library có export đúng package cho app hay không.
- Export là unqualified hay qualified.
- Có `opens` nào liên quan nếu lỗi đến từ reflection không.

### Bước 4: Kiểm tra descriptor đã compile và artifact runtime

Có thể đọc trực tiếp descriptor trong output directory:

~~~bash
javap -v out/com.acme.library/module-info.class
~~~

Với modular JAR:

~~~bash
jar --describe-module --file lib/com.acme.library.jar
~~~

So sánh descriptor của dependency được dùng khi compile với descriptor của dependency đang chạy. Đảm bảo build output cũ không bị trộn với artifact mới.

### Bước 5: Kiểm tra dependency bằng jdeps

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

Nếu nghi ngờ ứng dụng phụ thuộc vào JDK internal API:

~~~bash
jdeps --jdk-internals app.jar
~~~

`jdeps` giúp phân tích dependency tĩnh. Nó không thay thế việc quan sát module resolution tại runtime, nhưng có thể chỉ ra dependency hoặc API nội bộ cần được xử lý.

## 6. Cách sửa ưu tiên: sửa module descriptor và dependency

Nếu ứng dụng sử dụng public API hợp lệ, sửa descriptor để thể hiện đúng dependency.

Ví dụ module app thực sự dùng module library:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

Nếu module library dự định hỗ trợ API đó, export package tương ứng:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Nếu API chỉ dành cho một số module được chỉ định:

~~~java
module com.acme.library {
    exports com.acme.library.spi to com.acme.app;
}
~~~

Nếu module app cần đọc một module khác nhưng dependency không được mô tả trong descriptor (chẳng hạn do cấu hình triển khai đặc biệt), có thể dùng `--add-reads` như biện pháp tương thích tạm thời. Tuy nhiên, với dependency ổn định của ứng dụng, nên khai báo `requires` trong `module-info.java`.

Nếu package nội bộ không được thiết kế làm API công khai, cách bền vững là chuyển code sang public API được hỗ trợ. Việc mở lại package nội bộ chỉ nên dùng khi có lý do tương thích rõ ràng.

## 7. Các tùy chọn command line để xử lý chuyển đổi

JPMS cung cấp một số tùy chọn bổ sung. Chúng hữu ích khi cần chạy ứng dụng cũ, kiểm chứng nguyên nhân hoặc chuyển đổi từng bước. Hãy giới hạn target module cụ thể và ghi nhận rõ vì sao cần chúng.

### --add-reads

Cú pháp:

~~~bash
--add-reads <source-module>=<target-module>
~~~

Bổ sung readability edge từ module nguồn sang module đích.

Ví dụ:

~~~bash
java --add-reads com.acme.app=com.acme.optional   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Tùy chọn này không tự export package của module đích. Nếu package chưa được export, chỉ thêm readability vẫn chưa đủ.

### --add-exports

Cú pháp:

~~~bash
--add-exports <source-module>/<package>=<target-module>
~~~

Cho phép module đích truy cập các kiểu public trong package được chỉ định.

Ví dụ:

~~~bash
java --add-exports com.acme.library/com.acme.library.internal=com.acme.app   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Nếu caller thuộc unnamed module (ứng dụng chạy trên classpath), có thể dùng target `ALL-UNNAMED`. Với named module, hãy ghi rõ tên module tiêu thụ.

Nếu cần compile code mới đang truy cập package được export bổ sung, truyền tùy chọn tương ứng cho javac:

~~~bash
javac --add-exports com.acme.library/com.acme.library.internal=com.acme.app ...
~~~

Để ứng dụng chạy được với bytecode đã compile, cấu hình runtime cũng phải cung cấp quyền export tương ứng. Tùy chọn compile không tự thay đổi descriptor của module ở runtime.

### --add-opens

Cú pháp:

~~~bash
--add-opens <source-module>/<package>=<target-module>
~~~

Mở package cho deep reflection tại runtime. Ví dụ:

~~~bash
java --add-opens com.acme.library/com.acme.library.internal=com.acme.app   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Dùng tùy chọn này khi framework thực sự cần reflection sâu vào member không public. Nó không thay thế `--add-exports` cho truy cập API thông thường và không phải cách sửa chung cho `IllegalAccessError`.

### Không dựa vào --illegal-access

Tùy chọn `--illegal-access` từng hỗ trợ giai đoạn chuyển đổi strong encapsulation ở các bản Java cũ. Từ JDK 17, nó không còn khôi phục quyền truy cập rộng vào JDK internals. Đừng dùng nó làm giải pháp cho ứng dụng hiện đại; hãy thay internal API hoặc cấp đúng quyền truy cập cần thiết bằng tùy chọn cụ thể trong thời gian migration.

## 8. Ví dụ tái hiện lỗi khi export thay đổi

Giả sử bản library đầu tiên có descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.internal;
}
~~~

Và class:

~~~java
package com.acme.library.internal;

public class Helper {
    public static String message() {
        return "from library";
    }
}
~~~

App khai báo:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

App gọi trực tiếp:

~~~java
package com.acme.app;

import com.acme.library.internal.Helper;

public class Main {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
~~~

Compile và chạy với phiên bản library cũ:

~~~bash
javac --module-path mods --module-source-path src -d out --module com.acme.app
java --module-path "out:mods" --module com.acme.app/com.acme.app.Main
~~~

Sau đó thay descriptor library bằng phiên bản chỉ export API:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Giữ bytecode app cũ và chạy lại với phiên bản library mới. App vẫn chứa tham chiếu đến `com.acme.library.internal.Helper`, nhưng package đó không còn export. JVM có thể ném `IllegalAccessError` khi liên kết tham chiếu.

Cách xử lý đúng là:

1. Nếu `Helper` là API mà app được phép dùng, đưa nó vào package API được export và compile lại app theo descriptor mới.
2. Nếu `Helper` là implementation nội bộ, đổi app để dùng API công khai.
3. Nếu cần xác nhận nhanh nguyên nhân khi migration, thử `--add-exports` có phạm vi cụ thể; không giữ workaround rộng nếu không cần.

Ví dụ dùng package API mới:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

App chuyển sang import class thuộc package API đó, sau đó compile lại với module path đúng. Đây là cách đồng bộ code, descriptor và artifact runtime.

## 9. Các lỗi dễ nhầm và cách tránh

**Chỉ thêm `requires` nhưng vẫn lỗi.** Module app có thể đã đọc library, nhưng package chứa class vẫn chưa được export. Kiểm tra cả readability lẫn exports.

**Chỉ thêm `exports` nhưng vẫn lỗi.** App có thể không đọc module library. Kiểm tra cạnh `requires` hoặc cấu hình readability cần thiết.

**Dùng `opens` để sửa truy cập trực tiếp.** `opens` dành cho deep reflection. Truy cập public API thông thường cần `exports`.

**Compile và runtime dùng hai phiên bản dependency khác nhau.** Kiểm tra đường dẫn bằng `--show-module-resolution`, mô tả JAR thực tế và làm sạch build output trước khi kết luận.

**Dùng package nội bộ của JDK hoặc thư viện.** Package nội bộ có thể bị đóng gói mạnh hơn sau khi nâng cấp. Chuyển sang API công khai được hỗ trợ; chỉ dùng `--add-exports` khi có kế hoạch migration và phạm vi rõ ràng.

**Nhầm với InaccessibleObjectException.** Nếu framework gọi `setAccessible(true)` và bị chặn, kiểm tra `opens` và dùng `--add-opens` khi thực sự cần. Nếu bytecode gọi trực tiếp class/member không được phép, kiểm tra `requires` và `exports`.

## 10. Thực hành

1. Tạo module `com.acme.library` export package `com.acme.library.internal` và module `com.acme.app` yêu cầu library.
2. Compile và chạy app với phiên bản descriptor đầu tiên.
3. Thay descriptor library để bỏ export package internal nhưng giữ bytecode app cũ; chạy lại và ghi nhận lỗi.
4. Dùng `--show-module-resolution` để xác nhận phiên bản module library và vị trí được nạp.
5. Dùng `java --describe-module` để kiểm tra export của library và requires của app.
6. Thử `--add-exports` cho đúng package và module gọi để xác nhận nguyên nhân, sau đó bỏ workaround.
7. Refactor app để dùng package API công khai, compile lại và chạy với descriptor mới.
8. Tạo một ví dụ reflection dùng `setAccessible(true)`; so sánh lỗi `InaccessibleObjectException` và cách xử lý bằng `opens`.

Khi gặp `IllegalAccessError` sau khi module graph thay đổi, hãy xác định module gọi, module đích, package và quyền truy cập bị thiếu. Đối chiếu descriptor lúc compile với descriptor thực sự được resolve lúc chạy. Ưu tiên sửa dependency và API contract; chỉ dùng `--add-reads`, `--add-exports` hoặc `--add-opens` cho đúng loại quyền cần thiết và trong phạm vi hẹp.
