# Phụ thuộc trực tiếp và phụ thuộc bắc cầu

Trong Java Platform Module System (JPMS), chỉ thị **requires** khai báo một module cần đọc module khác để biên dịch và chạy. Một module có thể khai báo phụ thuộc trực tiếp bằng **requires**, hoặc khai báo phụ thuộc trực tiếp có khả năng truyền quyền đọc đến các module tiêu thụ bằng **requires transitive**.

Hai cách khai báo này đều tạo cạnh phụ thuộc từ module hiện tại đến module được nêu tên. Điểm khác nhau nằm ở phạm vi đọc được: **requires** chỉ làm module khai báo đọc dependency; **requires transitive** còn làm cho những module đọc module khai báo cũng đọc được dependency đó. Hiểu đúng sự khác biệt này giúp thiết kế API module rõ ràng và tránh buộc mọi ứng dụng tiêu thụ phải khai báo lại những dependency đã là một phần của API công khai.

## 1. Phụ thuộc trực tiếp là gì?

Giả sử module ứng dụng cần sử dụng một thư viện có tên **com.acme.catalog**. Trong descriptor của ứng dụng, khai báo:

~~~java
module com.acme.store {
    requires com.acme.catalog;
}
~~~

Đây là phụ thuộc trực tiếp. Module **com.acme.store** đọc được **com.acme.catalog**, nên mã nguồn trong store có thể sử dụng các kiểu thuộc những package mà catalog export.

Để một module có thể đọc module khác, dependency phải được phân giải trên module path hoặc thông qua cấu hình module tương ứng. Chỉ thị **requires** cũng tham gia vào việc xác định thứ tự và tính hợp lệ của module graph khi JVM khởi chạy.

Ví dụ, module catalog công bố API:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Ứng dụng có thể import kiểu công khai:

~~~java
package com.acme.store;

import com.acme.catalog.api.Product;

public final class StoreService {
    public Product findProduct(String id) {
        return new Product(id, "Keyboard");
    }
}
~~~

Nếu bỏ **requires com.acme.catalog**, module store không đọc catalog. Dù JAR của catalog có mặt trên module path, module store vẫn không tự động được phép tham chiếu các kiểu của catalog.

Phụ thuộc trực tiếp nên được khai báo khi mã nguồn hoặc descriptor của module thực sự cần module kia. Việc khai báo rõ giúp người đọc nhận ra module nào là dependency trực tiếp, đồng thời giúp công cụ build và JVM phân giải module graph chính xác.

## 2. Phụ thuộc bắc cầu với requires transitive

Một thư viện trung gian đôi khi sử dụng kiểu dữ liệu từ module khác trong API công khai. Khi đó, các module tiêu thụ thư viện trung gian cũng cần đọc được module chứa kiểu dữ liệu đó.

Ví dụ có ba module:

- **com.acme.model** chứa kiểu dữ liệu Product.
- **com.acme.service** cung cấp dịch vụ và dùng Product trong API.
- **com.acme.app** là ứng dụng gọi service.

Nếu service khai báo:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

thì bất kỳ module nào đọc **com.acme.service** cũng đọc được **com.acme.model**. Ứng dụng chỉ cần:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Ứng dụng có thể sử dụng cả API của service và kiểu Product được service đưa ra trong API công khai, vì module service đã truyền khả năng đọc module model cho các module tiêu thụ.

Đây là ý nghĩa của từ “bắc cầu”: khả năng đọc được truyền qua module trung gian trong module graph. Nó không có nghĩa JVM tự động sao chép class hoặc gộp các JAR dependency vào JAR của service.

## 3. Ví dụ hoàn chỉnh với ba module

Ta xây dựng một ví dụ nhỏ để thấy rõ cách **requires** và **requires transitive** ảnh hưởng đến mã nguồn của module tiêu thụ.

Cấu trúc source tree:

~~~text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/Product.java
├── com.acme.service/
│   ├── module-info.java
│   └── com/acme/service/api/CatalogService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

### Module model

Descriptor:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

Kiểu dữ liệu:

~~~java
package com.acme.model;

public record Product(String id, String name) {
}
~~~

Module model export package **com.acme.model** để module đọc được nó có thể truy cập Product.

### Module service

Descriptor:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

API:

~~~java
package com.acme.service.api;

import com.acme.model.Product;

public final class CatalogService {
    public Product findById(String id) {
        return new Product(id, "Mechanical Keyboard");
    }
}
~~~

Service phụ thuộc trực tiếp vào model vì implementation và chữ ký API của service sử dụng Product. Từ khóa **transitive** công bố rằng module model cũng là dependency mà người đọc service cần có khả năng đọc.

### Module app

Descriptor:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Lớp chạy ứng dụng:

~~~java
package com.acme.app;

import com.acme.model.Product;
import com.acme.service.api.CatalogService;

public final class Main {
    public static void main(String[] args) {
        CatalogService service = new CatalogService();
        Product product = service.findById("P-100");

        System.out.println(product.name());
    }
}
~~~

Mặc dù app không khai báo trực tiếp **requires com.acme.model**, nó vẫn có thể import và sử dụng Product vì service khai báo **requires transitive com.acme.model**. App đọc service; service truyền khả năng đọc model cho app.

### Biên dịch và chạy

Đứng tại thư mục dự án, biên dịch cả ba module bằng JDK:

~~~bash
javac -d out --module-source-path src -m com.acme.model,com.acme.service,com.acme.app
~~~

Chạy ứng dụng:

~~~bash
java --module-path out --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Mechanical Keyboard
~~~

Khi biên dịch, javac phân giải dependency từ các descriptor. Khi chạy, JVM cũng xây dựng module graph từ module path và các chỉ thị requires. Nếu module model không có mặt trong module path, việc phân giải service sẽ thất bại vì service cần model trực tiếp.

## 4. Điều gì xảy ra nếu service chỉ dùng requires?

Thay descriptor service bằng:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

Lúc này service vẫn đọc model và có thể biên dịch implementation của mình. Tuy nhiên, app chỉ khai báo **requires com.acme.service** sẽ không tự động đọc model.

Nếu mã nguồn app trực tiếp import Product hoặc khai báo biến có kiểu Product, trình biên dịch có thể báo package hoặc module không được đọc. Để app sử dụng Product, app cần khai báo thêm:

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.model;
}
~~~

Hai phương án có ý nghĩa API khác nhau:

| Descriptor của service | Khả năng đọc của app khi chỉ requires service |
|---|---|
| **requires com.acme.model** | App đọc service, nhưng không tự động đọc model. |
| **requires transitive com.acme.model** | App đọc service và được truyền khả năng đọc model. |

Nếu service không để lộ bất kỳ kiểu nào từ model trong API công khai, dùng **requires** thường là đủ. App không cần biết dependency nội bộ của service và không nên bị buộc phải phụ thuộc vào model chỉ vì implementation của service sử dụng nó.

## 5. Quy tắc truyền khả năng đọc qua nhiều tầng

Quan hệ bắc cầu có thể nối qua nhiều module. Giả sử:

~~~text
com.acme.app
    requires com.acme.service

com.acme.service
    requires transitive com.acme.model

com.acme.model
    requires transitive com.acme.types
~~~

Khi app đọc service, khả năng đọc được truyền tiếp qua các cạnh **requires transitive**. App có thể đọc service, model và types, miễn là các module liên quan được phân giải hợp lệ.

Có thể hình dung luồng như sau:

~~~text
app
 |
 | requires
 v
service
 |
 | requires transitive
 v
model
 |
 | requires transitive
 v
types
~~~

Một cạnh **requires** thông thường dừng việc truyền khả năng đọc ở module khai báo. Một cạnh **requires transitive** cho phép các module đọc module hiện tại tiếp tục đọc module đích. Khi nhiều cạnh transitive nối tiếp nhau, hiệu ứng được truyền qua các tầng tiếp theo.

Điều này không có nghĩa mọi dependency của một module đều tự động trở thành dependency bắc cầu. Mỗi cạnh trong module graph có ngữ nghĩa riêng. Nếu service khai báo **requires model** và model khai báo **requires types**, app đọc service không mặc nhiên đọc model hoặc types thông qua các cạnh thông thường đó.

## 6. Khi nào nên dùng requires transitive?

Nên dùng **requires transitive** khi module dependency là một phần có chủ đích của API công khai và module tiêu thụ hợp lý cần đọc được dependency đó.

Các tình huống thường gặp:

- API trả về hoặc nhận tham số là kiểu dữ liệu được định nghĩa trong module khác.
- Interface công khai kế thừa interface từ module dependency.
- Public class triển khai interface công khai thuộc module dependency.
- API công khai sử dụng kiểu generic, annotation hoặc kiểu khác từ dependency mà người gọi cần tham chiếu khi biên dịch.
- Một module façade được thiết kế để cung cấp một API thống nhất và công bố rõ các module nền tảng mà người dùng API cần đọc.

Ví dụ:

~~~java
module com.acme.orders.api {
    requires transitive com.acme.money;
    exports com.acme.orders;
}
~~~

Nếu public API của orders trả về **Money** hoặc nhận **Money** làm tham số, module tiêu thụ orders thường cần đọc module money để sử dụng chữ ký đó. Khai báo bắc cầu thể hiện đúng mối quan hệ này.

Không nên dùng **requires transitive** chỉ vì module hiện tại đang gọi một vài class từ dependency. Nếu dependency chỉ phục vụ implementation nội bộ và không xuất hiện trong hợp đồng API công khai, dùng **requires** để giữ module graph của người tiêu thụ gọn hơn.

## 7. API công khai, exports và requires transitive là ba việc khác nhau

Cần phân biệt ba khái niệm:

- **requires transitive** truyền khả năng đọc module dependency cho các module đọc module hiện tại.
- **exports** công bố một package để module khác đọc được có thể truy cập các kiểu công khai trong package đó.
- **opens** cho phép truy cập reflective sâu vào package theo quy tắc JPMS.

Một dependency có thể được đọc nhưng package của nó chưa được export. Trong trường hợp đó, module tiêu thụ vẫn không thể import kiểu trong package chưa export. Vì vậy, **requires transitive** không tự động công bố mọi package của dependency.

Ví dụ module model:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Module service:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

App đọc được model nhờ service truyền khả năng đọc, nhưng app chỉ truy cập được các package model đã export cho app theo quy tắc module. Package nội bộ không được export vẫn được đóng kín đối với truy cập thông thường từ module khác.

Cũng không nên nhầm **requires transitive** với **opens**. Một module có thể đọc module khác mà không được phép truy cập reflective sâu vào các thành viên private của package trong module đó.

## 8. Tác động đến hợp đồng và khả năng tương thích

Một chỉ thị **requires transitive** là một phần của module descriptor công khai. Các module tiêu thụ có thể dựa vào quan hệ này để tham chiếu kiểu từ dependency mà không cần khai báo **requires** riêng.

Nếu thư viện đổi từ:

~~~java
requires transitive com.acme.model;
~~~

thành:

~~~java
requires com.acme.model;
~~~

thì các ứng dụng trước đây chỉ đọc thư viện có thể mất khả năng đọc model. Mã nguồn tiêu thụ đang import Product có thể không biên dịch được sau khi nâng cấp thư viện.

Ngược lại, thêm **requires transitive** làm mở rộng tập module mà người tiêu thụ đọc được. Điều đó có thể hữu ích khi API bắt đầu công khai kiểu từ dependency, nhưng cũng làm tăng phạm vi dependency mà người dùng thư viện nhìn thấy.

Vì vậy, trước khi thay đổi **requires** thành **requires transitive** hoặc ngược lại, hãy kiểm tra chữ ký API công khai, kiểu được kế thừa/triển khai, tài liệu của thư viện và các module tiêu thụ. Việc thay đổi này nên được xem xét như một thay đổi hợp đồng module, không chỉ là chỉnh sửa cú pháp descriptor.

## 9. requires static và kết hợp với transitive

JPMS còn có biến thể **requires static** cho dependency cần khi biên dịch nhưng không bắt buộc phải có mặt ở runtime trong một số tình huống. Có thể kết hợp ý nghĩa này với truyền khả năng đọc:

~~~java
module com.acme.integration {
    requires static transitive com.acme.annotations;
}
~~~

Khai báo này cho biết dependency annotations được yêu cầu ở thời điểm biên dịch, và khả năng đọc nó được truyền đến module đọc integration. Tuy nhiên, vì dependency là static, ứng dụng vẫn phải bảo đảm dependency có mặt ở runtime nếu đường thực thi thực sự cần nó.

Không dùng **requires static transitive** để che giấu một dependency runtime bắt buộc. Nếu code luôn cần module đó để hoạt động, hãy khai báo dependency runtime rõ ràng. Đặc biệt, annotation có retention chỉ ở source hoặc class có thể có nhu cầu runtime khác với framework cần đọc annotation bằng reflection.

## 10. Phân biệt module graph với dependency graph của Maven/Gradle

JPMS và build tool cùng mô tả dependency, nhưng chúng giải quyết những việc khác nhau:

| Khía cạnh | JPMS | Maven/Gradle |
|---|---|---|
| Mục tiêu | Quy định module nào đọc module nào và package nào được truy cập. | Tìm, tải, chọn phiên bản và đưa artifact vào compile/runtime classpath hoặc module path. |
| Khai báo | **requires**, **requires transitive**, **requires static** trong module descriptor. | Dependency declarations và configuration/scope của build tool. |
| Truyền dependency | Truyền khả năng đọc trong module graph. | Quy tắc dependency transitivity của hệ thống quản lý artifact. |
| Đóng gói | Descriptor không tự gom dependency vào JAR. | Plugin và task quyết định artifact được publish hoặc đưa vào gói phân phối. |

Một khai báo **requires transitive** không thay thế cấu hình publish dependency của Maven hoặc Gradle. Build tool vẫn cần biết artifact nào phải được phân giải và công bố cho người dùng thư viện. Tương tự, một dependency được Maven/Gradle kéo về không tự động có nghĩa module hiện tại được phép đọc nó theo JPMS.

Với dự án modular, cần đồng bộ hai đồ thị: dependency artifact phải được build tool phân giải đúng, và module descriptor phải mô tả đúng khả năng đọc giữa các named module. Nếu build chạy được nhờ classpath nhưng ứng dụng được khởi chạy bằng module path, các thiếu sót trong descriptor có thể xuất hiện rõ ràng.

## 11. Cách kiểm tra module readability

Có thể xem descriptor của module đã đóng gói bằng:

~~~bash
jar --describe-module --file mods/com.acme.service.jar
~~~

Kiểm tra module trên module path:

~~~bash
java --module-path mods --describe-module com.acme.service
~~~

Để quan sát quá trình phân giải khi chạy ứng dụng:

~~~bash
java --show-module-resolution --module-path mods --module com.acme.app
~~~

Khi gặp lỗi, hãy lần lượt kiểm tra:

1. Module đích có nằm trên module path hoặc trong cấu hình module được dùng hay không.
2. Tên module trong **requires** có khớp với tên trong descriptor hoặc tên automatic module hay không.
3. Module trung gian có khai báo **requires transitive** đúng dependency mà API công khai đang làm lộ hay không.
4. Module chứa kiểu dữ liệu có export package tương ứng hay không.
5. Dependency của JPMS có khớp với dependency được build tool phân giải và đóng gói hay không.

Lỗi không đọc được module và lỗi package chưa export là hai vấn đề khác nhau. Hãy xác định lỗi thuộc module readability hay package accessibility trước khi thay descriptor.

## 12. Checklist thiết kế dependency

Khi viết module descriptor, hãy tự trả lời:

- Module hiện tại có trực tiếp dùng kiểu hoặc dịch vụ từ dependency này không? Nếu có, khai báo **requires**.
- Dependency có xuất hiện trong API công khai khiến người tiêu thụ cần đọc nó không? Nếu có, cân nhắc **requires transitive**.
- Package chứa API của dependency đã được export phù hợp chưa?
- Dependency chỉ cần khi biên dịch hay bắt buộc ở runtime? Chỉ dùng **requires static** khi vòng đời dependency thực sự cho phép vắng mặt lúc chạy.
- Việc truyền dependency có làm lộ quá nhiều module nội bộ cho người tiêu thụ không?
- Cấu hình Maven/Gradle đã công bố và phân giải artifact phù hợp với module descriptor chưa?
- Thay đổi descriptor có làm hỏng khả năng biên dịch của các module tiêu thụ hiện tại không?

Một module nên công bố đúng những dependency mà hợp đồng API của nó yêu cầu. **requires** giữ dependency ở phạm vi module trực tiếp; **requires transitive** truyền khả năng đọc đến người tiêu thụ khi dependency thực sự thuộc bề mặt API. Chọn đúng giữa hai chỉ thị giúp module graph phản ánh rõ kiến trúc, giảm khai báo lặp và giữ dependency nội bộ không bị phơi bày không cần thiết.