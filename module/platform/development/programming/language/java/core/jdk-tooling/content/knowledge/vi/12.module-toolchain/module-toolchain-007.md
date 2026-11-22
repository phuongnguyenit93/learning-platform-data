# requires transitive trong Java Module System

## 1. requires transitive là gì?

Java Platform Module System (JPMS), được giới thiệu trong Java 9, tổ chức ứng dụng thành các module có tên, khai báo dependency và quy định package nào được module khác truy cập. Mỗi named module thường có tệp **module-info.java** để khai báo tên module, dependency và package được export.

Trong module descriptor, directive **requires** khai báo một module cần đọc một module khác. Modifier **transitive** mở rộng khả năng đọc đó cho các module phụ thuộc vào module hiện tại.

Cú pháp:

~~~java
module com.example.facade {
    requires transitive com.example.api;
}
~~~

Khi một module khác khai báo:

~~~java
module com.example.app {
    requires com.example.facade;
}
~~~

thì com.example.app đọc được cả com.example.facade và com.example.api. Lý do là com.example.facade đã khai báo dependency com.example.api bằng requires transitive.

Nói cách khác, **requires transitive truyền khả năng đọc một dependency qua module đang được yêu cầu**. Nó đặc biệt hữu ích khi API công khai của một module sử dụng kiểu dữ liệu thuộc module khác.

## 2. Readability trong JPMS

JPMS phân biệt việc một module **đọc** module khác với việc một package được **export** cho module khác.

- **Readability** cho biết module hiện tại có thể tham chiếu các kiểu được cung cấp bởi module khác hay không.
- **Exports** quyết định package nào của một module có thể được module khác truy cập.
- **Requires** tạo quan hệ đọc giữa các module.
- **Requires transitive** tạo quan hệ đọc cho module hiện tại và truyền quan hệ đọc đó đến các module đọc module hiện tại.

Giả sử có ba module:

~~~text
com.example.app
       |
       | requires
       v
com.example.facade
       |
       | requires transitive
       v
com.example.api
~~~

com.example.facade đọc com.example.api để sử dụng API của nó. Vì dependency được đánh dấu transitive, com.example.app cũng đọc được com.example.api khi nó chỉ khai báo requires com.example.facade.

Readability được lan truyền theo các cạnh transitive trong module graph. Nếu một module đọc A, và A khai báo requires transitive B, module đó cũng đọc B. Nếu B tiếp tục khai báo requires transitive C, khả năng đọc có thể tiếp tục lan truyền đến C. Một dependency thông thường của B không tự động được truyền tiếp.

## 3. Phân biệt requires và requires transitive

Hai directive đều làm cho module khai báo chúng đọc được dependency. Khác biệt nằm ở khả năng đọc của các module downstream.

| Directive | Module khai báo đọc dependency | Module đọc module hiện tại có tự động đọc dependency? |
|---|---|---|
| requires B | Có | Không |
| requires transitive B | Có | Có |
| requires static B | Có ở compile time; optional ở runtime | Không |
| requires static transitive B | Có ở compile time; optional ở runtime | Có ở compile time |

Ví dụ module facade:

~~~java
module com.example.facade {
    requires com.example.api;
    exports com.example.facade;
}
~~~

Module facade đọc được com.example.api, nhưng module app chỉ requires com.example.facade thì không tự động đọc com.example.api. Nếu mã nguồn app import một kiểu thuộc package com.example.api, compiler báo package đó không được module app đọc.

Đổi thành:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

làm cho module app đọc được com.example.api thông qua facade mà không cần khai báo thêm requires com.example.api.

Nếu app có chủ đích phụ thuộc trực tiếp vào API của com.example.api ngoài phần API được facade cung cấp, app vẫn có thể khai báo requires com.example.api rõ ràng để thể hiện dependency kiến trúc của chính nó.

## 4. Khi nào nên dùng requires transitive?

Hãy cân nhắc requires transitive khi kiểu dữ liệu của dependency xuất hiện trong API công khai mà module hiện tại cung cấp cho client.

Các trường hợp điển hình:

- Một phương thức public trả về kiểu được định nghĩa trong module dependency.
- Một phương thức public nhận tham số thuộc module dependency.
- Một lớp public kế thừa lớp hoặc triển khai interface từ dependency.
- Một kiểu generic công khai dùng kiểu của dependency trong tham số kiểu hoặc giới hạn kiểu.
- Một record, annotation hoặc chữ ký API công khai cần kiểu từ dependency để client biên dịch và sử dụng.

Ví dụ facade cung cấp phương thức:

~~~java
public ApiType create() {
    return new ApiType("v1");
}
~~~

Client sử dụng kết quả ApiType. Nếu facade chỉ khai báo requires com.example.api, client sẽ không có readability đến module chứa ApiType. requires transitive thể hiện rằng dependency đó là một phần của hợp đồng API mà facade cung cấp.

Nếu dependency chỉ được dùng bên trong để triển khai, chẳng hạn một lớp private hoặc một lời gọi nội bộ không xuất hiện trong API công khai, directive requires thông thường thường phù hợp hơn.

Không nên đánh dấu mọi dependency là transitive. Việc đó làm tăng số module mà client phải đọc, mở rộng bề mặt phụ thuộc và có thể khiến implementation detail trở thành một phần hợp đồng công khai.

## 5. requires transitive không thay thế exports

Một module có thể đọc module khác nhưng vẫn không truy cập được package chưa được export.

Ví dụ module API:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

Package com.example.api được export nên module đọc com.example.api có thể truy cập các kiểu public trong package đó.

Nếu module facade khai báo:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

thì hai việc xảy ra độc lập:

- com.example.facade export package com.example.facade cho client.
- com.example.facade truyền readability đến com.example.api.

requires transitive không export package com.example.api thay cho module sở hữu package đó. Module com.example.api vẫn phải export package cần dùng.

Có thể dùng qualified export:

~~~java
module com.example.api {
    exports com.example.api to com.example.facade;
}
~~~

Cách này chỉ export package cho các module được liệt kê. Một client downstream như com.example.app có thể đọc com.example.api nhờ requires transitive nhưng vẫn không truy cập package nếu package chỉ được export riêng cho com.example.facade.

Hãy phân biệt ba câu hỏi:

1. Module client có đọc module API không?
2. Module API có export package chứa kiểu cần dùng không?
3. Kiểu và thành viên được truy cập có đủ quyền public/protected theo ngữ cảnh hay không?

Cả readability và package accessibility đều cần thỏa mãn.

## 6. Ví dụ đầy đủ với ba module Java 17

Ví dụ sau có ba module:

- **com.example.api** cung cấp kiểu ApiType.
- **com.example.facade** dùng ApiType trong API public và khai báo requires transitive.
- **com.example.app** chỉ requires com.example.facade nhưng vẫn có thể dùng ApiType.

Cấu trúc thư mục:

~~~text
project/
  src/
    com.example.api/
      module-info.java
      com/example/api/ApiType.java
    com.example.facade/
      module-info.java
      com/example/facade/Facade.java
    com.example.app/
      module-info.java
      com/example/app/Main.java
  mods/
~~~

### Module 1: com.example.api

Tệp src/com.example.api/module-info.java:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

Tệp src/com.example.api/com/example/api/ApiType.java:

~~~java
package com.example.api;

public final class ApiType {
    private final String value;

    public ApiType(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
~~~

Module này export package com.example.api để module khác có thể dùng lớp ApiType.

### Module 2: com.example.facade

Tệp src/com.example.facade/module-info.java:

~~~java
module com.example.facade {
    requires transitive com.example.api;
    exports com.example.facade;
}
~~~

Tệp src/com.example.facade/com/example/facade/Facade.java:

~~~java
package com.example.facade;

import com.example.api.ApiType;

public class Facade {
    public ApiType create() {
        return new ApiType("v1");
    }
}
~~~

Facade dùng ApiType trong kiểu trả về của phương thức public. requires transitive cho biết client đọc facade cũng cần được phép đọc module API để biên dịch và sử dụng kiểu này.

### Module 3: com.example.app

Tệp src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.facade;
}
~~~

Tệp src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.facade.Facade;
import com.example.api.ApiType;

public class Main {
    public static void main(String[] args) {
        ApiType api = new Facade().create();
        System.out.println("API value: " + api.value());
    }
}
~~~

Lưu ý module app không khai báo requires com.example.api. Nó đọc được module đó thông qua directive requires transitive trong module facade.

### Biên dịch cả ba module

Chạy từ thư mục project:

~~~bash
javac --release 17 -d mods --module-source-path src \
    -m com.example.api,com.example.facade,com.example.app
~~~

Compiler tạo các module đã biên dịch trong thư mục mods.

### Chạy ứng dụng

~~~bash
java --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Kết quả chính xác:

~~~text
API value: v1
~~~

Ví dụ này chứng minh module app có thể import ApiType dù module-info.java của app chỉ requires com.example.facade.

## 7. Thử bỏ transitive để thấy khác biệt

Trong module-info.java của com.example.facade, thay:

~~~java
requires transitive com.example.api;
~~~

bằng:

~~~java
requires com.example.api;
~~~

Biên dịch lại cả ba module bằng lệnh javac ở phần trước. Module app sẽ báo lỗi tương tự:

~~~text
package com.example.api is not visible
(package com.example.api is declared in module com.example.api,
 but module com.example.app does not read it)
~~~

Nguyên nhân là facade vẫn đọc api, nhưng quan hệ đọc đó không được truyền đến app.

Có hai cách sửa tùy ý định thiết kế:

**Cách 1: Giữ requires transitive ở facade.** Dùng khi ApiType thực sự là một phần của API public mà facade muốn cung cấp cho client.

**Cách 2: Giữ requires thông thường ở facade và thêm dependency trực tiếp vào app.** Sửa module-info.java của app:

~~~java
module com.example.app {
    requires com.example.facade;
    requires com.example.api;
}
~~~

Cách này phù hợp khi app chủ động phụ thuộc vào cả hai module và facade không muốn công bố dependency api như một phần của hợp đồng.

## 8. requires static transitive

JPMS cho phép kết hợp modifier static và transitive:

~~~java
module com.example.annotations {
    requires static transitive com.example.annotation.api;
}
~~~

Modifier **static** biểu thị dependency cần thiết khi biên dịch nhưng có thể không có mặt khi chạy. Modifier **transitive** vẫn thể hiện rằng module đọc module hiện tại cũng cần readability đến dependency trong ngữ cảnh biên dịch.

Có thể cân nhắc dạng này cho dependency tùy chọn chỉ phục vụ compile time, chẳng hạn kiểu annotation hoặc metadata mà ứng dụng không cần để thực thi luồng chính.

Tuy nhiên, nếu kiểu của dependency xuất hiện trong API public và client thực sự cần nạp hoặc gọi nó khi chạy, dependency phải có mặt ở runtime. Nếu thiếu module, thao tác cần kiểu đó có thể thất bại khi nạp hoặc liên kết lớp. Vì vậy, chỉ dùng static khi dependency thực sự có thể vắng mặt ở runtime theo thiết kế.

So sánh:

- **requires transitive B**: B là dependency bắt buộc trong module graph.
- **requires static transitive B**: B cần khi biên dịch và được truyền readability cho client; B có thể không được yêu cầu ở runtime nếu không có mặt và không cần cho đường chạy thực tế.

Không dùng static để né việc đóng gói một dependency bắt buộc.

## 9. Kiểm tra module descriptor và module graph

Có thể dùng công cụ JDK để kiểm tra directive đã được ghi vào module descriptor.

Sau khi biên dịch module facade, đóng gói module thành JAR:

~~~bash
jar --create --file mods/com.example.facade.jar \
    -C mods/com.example.facade .
~~~

Xem mô tả module:

~~~bash
jar --describe-module --file mods/com.example.facade.jar
~~~

Phần output quan trọng có dạng:

~~~text
com.example.facade
exports com.example.facade
requires com.example.api transitive
requires java.base mandated
~~~

Dòng requires com.example.api transitive xác nhận modifier đã có trong module descriptor.

Có thể yêu cầu launcher hiển thị quá trình phân giải module khi chạy:

~~~bash
java --show-module-resolution --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Output cho biết các module được resolve và quan hệ phụ thuộc trong lần khởi chạy. Đây là cách hữu ích khi module path chứa nhiều JAR hoặc khi một module không được tìm thấy.

Nếu cần phân tích dependency của ứng dụng, công cụ jdeps cũng có thể hỗ trợ kiểm tra các module được tham chiếu:

~~~bash
jdeps --module-path mods --check com.example.facade
~~~

Kết quả cần được đọc cùng module descriptor và cấu trúc source; jdeps phân tích dependency mà bytecode sử dụng, còn requires transitive thể hiện chính sách readability được khai báo.

## 10. Quan hệ với Maven và Gradle

requires transitive thuộc JPMS và được ghi trong module-info.class. Build tool có hệ thống dependency riêng, nên không nên coi hai cơ chế là một.

Với Gradle Java Library Plugin:

- **api dependency** được đưa vào compile classpath của consumer.
- **implementation dependency** chỉ phục vụ implementation của thư viện và không được công bố trên compile classpath của consumer.

Nếu một thư viện modular công khai kiểu của dependency B trong API, thiết kế build thường cần công bố B như API dependency. Trong module-info.java, requires transitive B biểu diễn quan hệ readability tương ứng ở JPMS.

Với Maven, dependency scope và cách đóng gói artifact ảnh hưởng đến dependency được truyền đến consumer. Module descriptor vẫn cần khai báo requires transitive nếu muốn JPMS truyền readability cho các module downstream.

Hãy kiểm tra cả hai lớp cấu hình:

1. Build tool có cung cấp dependency JAR cho compile/runtime classpath hoặc module path không?
2. module-info.java có khai báo đúng requires, requires transitive hoặc requires static không?

Một directive đúng trong module-info.java không tự tải dependency về máy và cũng không tự đóng gói dependency vào JAR.

## 11. Lỗi thường gặp và cách xử lý

### Package is not visible hoặc module does not read it

Nguyên nhân thường gặp:

- Module client chưa requires module chứa package.
- Module trung gian dùng requires thông thường dù API công khai có kiểu của dependency.
- Dependency chưa được resolve trên module path.

Cách xử lý: xác định module nào chứa kiểu bị lỗi; kiểm tra chuỗi requires; dùng requires transitive tại module trung gian nếu dependency thuộc API công khai của nó, hoặc khai báo requires trực tiếp ở client nếu client có dependency riêng.

### Module được đọc nhưng package vẫn không truy cập được

Readability đã có nhưng module sở hữu package chưa export package đó, hoặc chỉ export cho một module khác bằng qualified export. Kiểm tra exports trong module-info.java của module chứa package.

### Dùng requires transitive cho mọi dependency

Việc truyền readability không cần thiết làm lộ thêm dependency của module và tạo coupling cho client. Chỉ dùng khi dependency là phần cần thiết của API công khai hoặc khi hợp đồng module chủ đích yêu cầu client đọc dependency đó.

### Thiếu module khi chạy

Kiểm tra module path và dependency đã được đóng gói. requires transitive không tự mang JAR dependency theo ứng dụng. Nếu dùng requires static, xác nhận code path lúc chạy thực sự không cần module tùy chọn.

### Dependency cycle

JPMS không cho phép chu trình phụ thuộc giữa các named module. Nếu A requires B và B requires A, module graph không thể được resolve hợp lệ. Hãy tách phần API dùng chung thành module riêng hoặc điều chỉnh hướng phụ thuộc.

### Nhầm exports với requires transitive

exports mở package của module sở hữu package đó. requires transitive truyền readability đến module dependency. Hai directive giải quyết hai vấn đề khác nhau và thường cần kết hợp khi xây dựng API modular.

## 12. Nguyên tắc thiết kế và checklist

Khi quyết định dùng requires transitive, hãy tự hỏi:

- [ ] Dependency có xuất hiện trong chữ ký API public/protected của module không?
- [ ] Client cần đọc dependency để sử dụng API của module hiện tại không?
- [ ] Module sở hữu kiểu đó đã export package phù hợp chưa?
- [ ] Dependency có thật sự bắt buộc khi chạy, hay có thể là static?
- [ ] requires transitive có làm lộ implementation detail không cần thiết không?
- [ ] Build tool có cung cấp dependency đúng trên compile/runtime module path không?
- [ ] Ví dụ hoặc ứng dụng đã biên dịch được khi client chỉ requires module facade chưa?
- [ ] Đã kiểm tra module descriptor bằng jar --describe-module chưa?
- [ ] Đã kiểm tra module resolution khi chạy bằng --show-module-resolution chưa?

Dùng requires transitive để mô tả dependency mà client cần đọc thông qua API công khai của module hiện tại. Dùng requires thông thường cho dependency chỉ phục vụ nội bộ. Kết hợp đúng với exports để bảo đảm client vừa đọc được module vừa truy cập được package cần thiết.
