# Giới hạn --add-reads và ý nghĩa ALL-UNNAMED

Trong Java Platform Module System (JPMS), một module chỉ được phép tham chiếu các kiểu public của module khác khi nó **đọc** module đó và package chứa kiểu được **export** cho module đang gọi. Hai điều kiện này độc lập: readability trả lời câu hỏi “module này có thể phụ thuộc vào module kia không?”, còn exports quyết định “package nào được phép dùng từ bên ngoài?”.

Tùy chọn **--add-reads** bổ sung một cạnh đọc vào module graph khi biên dịch hoặc chạy chương trình. Nó hữu ích khi tích hợp thư viện cũ, kiểm thử hoặc xử lý một ranh giới module đặc biệt mà chưa thể thay đổi module descriptor. Tùy chọn này không sửa tệp **module-info.java**, không tự export package và không mở quyền reflection.

**ALL-UNNAMED** là tên đích đặc biệt có thể dùng với **--add-reads**. Nó biểu thị tất cả unnamed module, thường là mã được nạp từ classpath. Vì phạm vi này có thể rộng hơn nhiều so với một thư viện cụ thể, cần hiểu rõ quyền được cấp trước khi đưa cấu hình vào production.

Các ví dụ trong bài dùng cú pháp Java 17 trở lên và đã được kiểm tra trên JDK 24.

## 1. Readability trong module graph là gì?

Một named module có thể khai báo dependency trực tiếp trong **module-info.java**:

~~~java
module com.example.application {
    requires com.example.service;
}
~~~

Directive **requires** tạo quan hệ đọc từ **com.example.application** tới **com.example.service**. Mã trong application có thể tham chiếu các kiểu public thuộc package mà service export cho application.

Nếu module descriptor không có **requires**, module application không mặc nhiên đọc mọi named module chỉ vì module đó có mặt trên module path. Việc đặt một JAR trên module path cũng không tự tạo quan hệ đọc giữa tất cả các module.

Có thể hình dung điều kiện truy cập API public như sau:

1. Module gọi phải đọc module chứa API.
2. Package chứa API phải được module nguồn export cho module gọi.
3. Kiểu và thành viên được sử dụng phải đáp ứng quy tắc truy cập Java thông thường.

**--add-reads** chỉ giải quyết điều kiện thứ nhất. Nó không thay thế điều kiện export và cũng không thay đổi modifier **public**, **protected**, **package-private** hoặc **private** của class/member.

## 2. Cú pháp của --add-reads

Cú pháp trên Java launcher:

~~~text
--add-reads <source-module>=<target-module>(,<target-module>)*
~~~

Ví dụ:

~~~bash
java --add-reads=com.example.application=com.example.service -m com.example.application/com.example.application.Main
~~~

Ý nghĩa:

- **source-module** là named module được bổ sung quyền đọc.
- **target-module** là named module mà source module cần đọc.
- Có thể chỉ định nhiều target module bằng dấu phẩy.
- Quan hệ được thêm theo một chiều: application đọc service không có nghĩa service tự động đọc application.

Tùy chọn cũng có trên **javac** để compiler chấp nhận quan hệ đọc bổ sung trong lúc biên dịch:

~~~bash
javac --add-reads com.example.application=com.example.service ...
~~~

Nếu chương trình được biên dịch nhờ một read edge bổ sung, runtime cũng cần có cấu hình tương ứng. **javac --add-reads** không ghi một directive mới vào **module-info.class** và không tự mang cấu hình đó sang lệnh **java**.

Khi cần một dependency ổn định và là một phần của thiết kế ứng dụng, nên khai báo **requires** trong module descriptor. **--add-reads** phù hợp hơn với cấu hình build/test, migration hoặc tích hợp có phạm vi rõ ràng.

## 3. Giới hạn thứ nhất: chỉ thêm readability, không export package

Giả sử module **com.example.library** có descriptor:

~~~java
module com.example.library {
    // Package com.example.library.internal không được export.
}
~~~

Module application thêm:

~~~bash
--add-reads=com.example.application=com.example.library
~~~

Application có thể đọc module library trong module graph, nhưng vẫn không thể import kiểu nằm trong package **com.example.library.internal** vì package này chưa được export.

Nếu cần truy cập API public của package được export có giới hạn, hãy kiểm tra directive **exports**. Nếu package chưa được export và có lý do hợp lệ để cho phép truy cập, tùy chọn phù hợp là **--add-exports**. Nếu framework cần deep reflection vào thành viên không public, cơ chế liên quan là **opens** hoặc **--add-opens**.

| Nhu cầu | Directive/tùy chọn liên quan |
|---|---|
| Module A cần đọc module B | **requires** hoặc **--add-reads** |
| Module A cần dùng kiểu public trong package B đã export | **exports** |
| Cấp quyền dùng package public chưa export cho một module | **--add-exports** |
| Cấp quyền deep reflection vào package | **opens** hoặc **--add-opens** |

Đừng dùng **--add-reads** để xử lý lỗi package không được export. Cũng đừng dùng **--add-exports** để giải quyết lỗi module không đọc module khác. Hãy xác định chính xác điều kiện nào đang thiếu từ thông báo compiler/runtime.

## 4. Giới hạn thứ hai: module đích phải được resolve

Một named module có thể nằm trên module path nhưng chưa chắc đã được đưa vào module graph của tiến trình. Nếu **--add-reads** nhắc tới một module chưa được resolve, runtime có thể cảnh báo module không xác định và lớp cần dùng không được nạp.

Ví dụ, nếu application cần đọc **com.example.provider**, có thể chủ động resolve module đó bằng:

~~~bash
--add-modules com.example.provider
~~~

Kết hợp:

~~~bash
java --module-path mods --add-modules com.example.provider --add-reads=com.example.application=com.example.provider -m com.example.application/com.example.application.Main
~~~

**--add-modules** và **--add-reads** có hai vai trò khác nhau:

- **--add-modules** yêu cầu resolve module được chỉ định vào module graph.
- **--add-reads** thêm cạnh đọc từ source module tới target module.

Không phải lúc nào cũng cần thêm **--add-modules**. Nếu module đích đã được resolve qua dependency khác hoặc là root module của ứng dụng, nó đã có mặt trong graph. Khi module chỉ nằm trên module path và chưa được resolve, hãy kiểm tra bằng **--show-module-resolution** và bổ sung **--add-modules** nếu cần.

Với một named target module, cần dùng đúng tên module thực tế. Tên artifact JAR, tên file Maven hoặc tên thư mục không nhất thiết trùng với module name. Có thể kiểm tra module descriptor bằng:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

## 5. ALL-UNNAMED biểu thị điều gì?

Trong JPMS, code trên classpath thuộc unnamed module. Mỗi class loader có thể có unnamed module tương ứng; các lớp không thuộc named module được tổ chức trong unnamed module thay vì một named module có tên trong **module-info.java**.

**ALL-UNNAMED** là target đặc biệt của tùy chọn module command line. Trong:

~~~bash
--add-reads=com.example.application=ALL-UNNAMED
~~~

named module **com.example.application** được cấp readability tới tất cả unnamed module. Điều này thường cho phép code trong named module tham chiếu các kiểu public của thư viện đặt trên classpath, với điều kiện các kiểu đó có thể được tìm thấy và các quy tắc truy cập còn lại được đáp ứng.

Các điểm cần nhớ:

- **ALL-UNNAMED không phải tên một named module.** Không khai báo **requires ALL-UNNAMED** trong **module-info.java**.
- Đây là target đặc biệt của tùy chọn dòng lệnh, không phải cú pháp module declaration.
- Quyền đọc được cấp từ source module tới mọi unnamed module; nó không tự tạo quan hệ ngược chiều.
- Phạm vi bao gồm các unnamed module, không chỉ một JAR hay một thư mục classpath cụ thể.
- Nó không thêm JAR vào classpath hoặc module path. Vẫn phải cấu hình đường dẫn để class loader tìm được thư viện.
- Nó không export package của một named module khác và không mở package cho deep reflection.

Vì phạm vi rộng, **ALL-UNNAMED** thường hữu ích khi một named module cần tích hợp với nhiều thư viện legacy còn chạy trên classpath. Nếu chỉ cần đọc một named module cụ thể, hãy dùng đúng tên module thay vì mở rộng tới mọi unnamed module.

## 6. Ví dụ 1: thêm read edge tới một named module

Ví dụ có hai named module. Module provider export API public; module application không khai báo **requires** trong descriptor. Read edge được thêm bằng tùy chọn compiler và runtime.

Cấu trúc:

~~~text
project/
  provider-src/
    com.example.provider/
      module-info.java
      com/example/provider/api/Greeting.java
  app-src/
    com.example.app/
      module-info.java
      com/example/app/Main.java
  mods/
~~~

**Tệp provider-src/com.example.provider/module-info.java:**

~~~java
module com.example.provider {
    exports com.example.provider.api;
}
~~~

**Tệp provider-src/com.example.provider/com/example/provider/api/Greeting.java:**

~~~java
package com.example.provider.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "named-module";
    }
}
~~~

**Tệp app-src/com.example.app/module-info.java:**

~~~java
module com.example.app {
}
~~~

**Tệp app-src/com.example.app/com/example/app/Main.java:**

~~~java
package com.example.app;

import com.example.provider.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Tạo thư mục output cho provider và biên dịch module này:

~~~bash
mkdir -p mods/com.example.provider
javac --release 17 -d mods/com.example.provider provider-src/com.example.provider/module-info.java provider-src/com.example.provider/com/example/provider/api/Greeting.java
~~~

Biên dịch application với read edge và yêu cầu resolve provider:

~~~bash
javac --release 17 --module-path mods --add-modules com.example.provider --add-reads com.example.app=com.example.provider --module-source-path app-src -d mods -m com.example.app
~~~

Chạy application với cùng quan hệ đọc:

~~~bash
java --module-path mods --add-modules com.example.provider --add-reads=com.example.app=com.example.provider -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
named-module
~~~

Trong ví dụ, package **com.example.provider.api** được export nên application có thể dùng kiểu public sau khi được cấp readability. Nếu bỏ **--add-reads**, application không có quan hệ đọc provider dù provider đã nằm trên module path. Nếu bỏ **--add-modules** trong một tình huống provider chưa được resolve, runtime có thể không nhận ra target module và không nạp được class.

## 7. Ví dụ 2: đọc thư viện classpath bằng ALL-UNNAMED

Ví dụ tiếp theo dùng một thư viện legacy đặt trên classpath. Module application không khai báo **requires** cho thư viện vì thư viện không phải named module.

Cấu trúc:

~~~text
project/
  legacy-src/
    legacy/util/LegacyFormatter.java
  legacy-classes/
  app-src/
    com.example.app/
      module-info.java
      com/example/app/Main.java
  mods/
~~~

**Tệp legacy-src/legacy/util/LegacyFormatter.java:**

~~~java
package legacy.util;

public final class LegacyFormatter {
    private LegacyFormatter() {
    }

    public static String message() {
        return "unnamed-module";
    }
}
~~~

Biên dịch thư viện legacy vào classpath output:

~~~bash
mkdir -p legacy-classes
javac --release 17 -d legacy-classes legacy-src/legacy/util/LegacyFormatter.java
~~~

**Tệp app-src/com.example.app/module-info.java:**

~~~java
module com.example.app {
}
~~~

**Tệp app-src/com.example.app/com/example/app/Main.java:**

~~~java
package com.example.app;

import legacy.util.LegacyFormatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(LegacyFormatter.message());
    }
}
~~~

Biên dịch module application với classpath và read edge tới tất cả unnamed module:

~~~bash
javac --release 17 --class-path legacy-classes --add-reads com.example.app=ALL-UNNAMED --module-source-path app-src -d mods -m com.example.app
~~~

Chạy với cùng classpath và read edge:

~~~bash
java --module-path mods --class-path legacy-classes --add-reads=com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
unnamed-module
~~~

Ở đây, **LegacyFormatter** thuộc unnamed module vì được nạp từ classpath. **ALL-UNNAMED** cho phép named module application đọc unnamed module đó. Không cần và cũng không thể viết **requires ALL-UNNAMED** trong descriptor.

Ví dụ này cho thấy cách tương thích với thư viện cũ trong khi module application vẫn là named module. Tuy nhiên, quyền đọc được cấp cho tất cả unnamed module, nên nếu classpath chứa nhiều thư viện không liên quan, chúng cũng nằm trong phạm vi readability đó.

## 8. Phân biệt requires, --add-reads và ALL-UNNAMED

| Cơ chế | Nơi khai báo | Target | Tính chất |
|---|---|---|---|
| **requires module.name;** | module-info.java | Một named module | Dependency được ghi trong module descriptor |
| **--add-reads=source=target** | javac/java command line | Named module đã được resolve | Thêm read edge cho lần biên dịch hoặc lần chạy được cấu hình |
| **--add-reads=source=ALL-UNNAMED** | javac/java command line | Tất cả unnamed module | Mở rộng readability tới code trên classpath |
| **--add-modules module.name** | java/javac command line | Named module | Yêu cầu resolve module vào graph; không tự cấp read edge |

Ưu tiên **requires** khi dependency là một phần ổn định của kiến trúc. Tùy chọn **--add-reads** phù hợp khi cần bổ sung readability tạm thời hoặc theo môi trường. **ALL-UNNAMED** chỉ nên dùng khi thực sự cần tích hợp với code không có module name.

Cấu hình command line có thể bị bỏ sót ở một môi trường. Ví dụ, IDE truyền option khi chạy ứng dụng nhưng test runner hoặc container production lại không truyền. Vì vậy, hãy quản lý các option này trong build profile hoặc cấu hình triển khai có kiểm soát, đồng thời kiểm tra lệnh JVM thực tế.

## 9. Chẩn đoán lỗi liên quan tới --add-reads

Khi gặp lỗi module access, trước hết phân loại lỗi theo điều kiện còn thiếu.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Compiler báo module không đọc module khác | Thiếu read edge | Thêm **requires** hoặc **--add-reads** phù hợp |
| Runtime cảnh báo Unknown module khi dùng **--add-reads** | Target named module chưa được resolve hoặc tên module sai | Kiểm tra tên module và thêm **--add-modules** khi cần |
| Compiler báo package không được export | Readability đã có nhưng package chưa export | Kiểm tra **exports** hoặc **--add-exports** |
| Reflection ném **InaccessibleObjectException** | Package chưa mở cho deep reflection | Kiểm tra **opens** hoặc **--add-opens** |
| Không tìm thấy class sau khi thêm **ALL-UNNAMED** | Thư viện không nằm trên classpath hoặc sai đường dẫn | Kiểm tra **--class-path** và cấu trúc package/class |
| Ứng dụng chạy ở IDE nhưng lỗi trong production | JVM production thiếu option đã dùng khi test | Kiểm tra command line thực tế của tiến trình production |
| Module khác vẫn không đọc application | Read edge chỉ được thêm theo một chiều | Cấp read edge riêng nếu kiến trúc thật sự cần chiều ngược lại |

Các công cụ hỗ trợ chẩn đoán:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
java --list-modules
jar --describe-module --file path/to/library.jar
~~~

**--show-module-resolution** giúp xem quá trình resolve module khi khởi động. **--list-modules** liệt kê các module có thể được quan sát từ runtime. **jar --describe-module** giúp kiểm tra tên module, package export và descriptor của một JAR.

Nếu lỗi xảy ra ở bước biên dịch, xem thông báo của **javac** và xác định compiler thiếu readability hay thiếu export. Nếu lỗi xảy ra lúc chạy, kiểm tra option có được truyền tới đúng JVM process hay không.

## 10. Giới hạn và lưu ý bảo mật

- **Read edge có hướng:** cấp quyền cho A đọc B không tự động cấp cho B đọc A.
- **Không phải quyền truy cập reflection:** readability không mở private field, constructor hoặc method.
- **Không thay thế exports:** module đọc được target vẫn cần package được export để dùng kiểu public qua mã Java thông thường.
- **Không tự resolve target:** module đích cần có mặt trong module graph; dùng **--add-modules** nếu nó chưa được resolve.
- **ALL-UNNAMED có phạm vi rộng:** mọi unnamed module có thể nằm trong phạm vi, không chỉ dependency đang cần.
- **Không thay đổi module descriptor:** các option command line không sửa **module-info.java** hay artifact đã đóng gói.
- **Compile và runtime là hai lần cấu hình:** nếu compiler cần read edge thì thêm option cho **javac**; nếu ứng dụng cần edge lúc chạy thì thêm option cho **java**.
- **Không dùng tên file JAR thay module name:** target named module phải dùng module name được khai báo hoặc suy ra theo quy tắc module.
- **Không đưa option migration vào production vô thời hạn:** ghi lại lý do, phạm vi, môi trường áp dụng và kế hoạch chuyển sang dependency/module descriptor ổn định nếu phù hợp.

## 11. Checklist trước khi thêm --add-reads

- [ ] Đã xác định source module và target module thực tế.
- [ ] Đã xác định lỗi là thiếu readability, không phải thiếu export hoặc opens.
- [ ] Target named module đã được resolve; nếu cần đã cấu hình **--add-modules**.
- [ ] Nếu target là classpath code, đã hiểu **ALL-UNNAMED** bao phủ mọi unnamed module.
- [ ] Đã cân nhắc **requires** trong module descriptor cho dependency ổn định.
- [ ] Đã thêm option cho cả compiler và runtime nếu cả hai cần read edge.
- [ ] Đã kiểm tra module graph và classpath/module path thực tế.
- [ ] Không dùng **ALL-UNNAMED** chỉ để né việc xác định một named dependency cụ thể.
- [ ] Cấu hình được giới hạn trong đúng build/test/deployment profile.
- [ ] Có kiểm thử trên đúng JDK và môi trường triển khai mục tiêu.

## 12. Tài liệu tham khảo

- [Java SE 25 — java launcher options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Java SE 25 — javac compiler options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Java Language Specification — Module Declarations, §7.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Java Platform Module System — Module resolution and readability](https://openjdk.org/projects/jigsaw/spec/sotms/)
