# Readability kết hợp với exports

## 1. Vì sao chỉ requires là chưa đủ?

Trong Java Platform Module System (JPMS), một named module không được tự động sử dụng mọi public class nằm trong những JAR khác. Để code ở module A truy cập một public type thuộc module B theo cách thông thường, ít nhất hai điều kiện độc lập phải được thỏa mãn:

1. **Readability**: A phải **đọc được** B trong module graph.
2. **Exports**: B phải **export package chứa type đó** cho A.

Sau đó Java vẫn áp dụng các quy tắc access modifier như public, protected, package-private và private. Một class không public sẽ không trở thành public chỉ vì package được export.

Ví dụ:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

App có thể tham chiếu public type trong com.acme.catalog.api nếu mã và môi trường biên dịch phù hợp. Nhưng app **không thể** import public type trong com.acme.catalog.internal khi package internal không được export. Ngược lại, nếu catalog đã export api mà app **không đọc được** catalog, app cũng không thể dùng type đó.

Có thể hình dung:

~~~text
       module com.acme.app
                 |
                 |  readability: requires
                 v
       module com.acme.catalog
                 |
                 |  exports com.acme.catalog.api
                 v
       public API của catalog

Điều kiện cần: có đường đọc module + package được export
~~~

**Điểm cốt lõi:** Readability kiểm soát quan hệ giữa các **module**; exports kiểm soát quyền truy cập các **package** qua ranh giới module. Hai cơ chế bổ sung cho nhau để thực thi strong encapsulation.

## 2. Ba tầng kiểm soát truy cập

JPMS không thay thế access modifier của Java; nó thêm tầng kiểm soát ở cấp module.

| Tầng | Câu hỏi | Cơ chế |
|---|---|---|
| Module | Module consumer có đọc được module provider không? | requires, requires transitive, quan hệ reads |
| Package | Package của provider có được export tới consumer không? | exports, exports ... to |
| Type/member | Type hoặc thành viên có mức truy cập hợp lệ không? | public, protected, package-private, private |

Ví dụ:

~~~java
package com.acme.catalog.api;

public class Product {
    private String code;

    public Product(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    void resetForTesting() {
        this.code = "";
    }
}
~~~

Nếu module catalog export com.acme.catalog.api và app đọc catalog:

- App có thể tạo new Product("P-1") và gọi code().
- App không thể gọi resetForTesting() vì phương thức là package-private.
- App không thể trực tiếp truy cập field code vì field private.

Không nên gọi exports là cơ chế “mở toàn bộ class”. Nó chỉ cho phép các truy cập Java thông thường mà access modifier đã cho phép.

## 3. Đặt vấn đề với một module API và một module ứng dụng

Giả sử source tree gồm:

~~~text
project/
├── src/
│   ├── com.acme.catalog/
│   │   ├── module-info.java
│   │   └── com/acme/catalog/
│   │       ├── api/Product.java
│   │       └── internal/ProductRepository.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
~~~

Descriptor của catalog:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Class API:

~~~java
package com.acme.catalog.api;

public record Product(String sku, String name) {
}
~~~

Class nội bộ:

~~~java
package com.acme.catalog.internal;

public final class ProductRepository {

    public ProductRepository() {
    }

    public String storageKey(String sku) {
        return "product:" + sku;
    }
}
~~~

Dù ProductRepository được khai báo public, package com.acme.catalog.internal **không được export**. Đây là chủ đích: implementation chi tiết tồn tại bên trong module, không thuộc public API.

Descriptor app:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Mã Main:

~~~java
package com.acme.app;

import com.acme.catalog.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("SKU-1", "Keyboard");
        System.out.println(product.name());
    }
}
~~~

Khi biên dịch và chạy đúng module path, app có quyền đọc catalog, package api được export, và Product là public. Cả ba điều kiện đều đúng.

## 4. Biên dịch và chạy ví dụ đúng

Với cấu trúc source trên:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.catalog,com.acme.app
~~~

Thư mục output:

~~~text
mods/
├── com.acme.catalog/
│   ├── module-info.class
│   └── com/acme/catalog/
│       ├── api/Product.class
│       └── internal/ProductRepository.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Chạy:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Keyboard
~~~

Lệnh javac dùng module-info.java để kiểm tra module readability và package accessibility ngay khi compile. Khi chạy, launcher tiếp tục tạo module graph từ module roots và dependency thực tế.

--module-path chỉ xác định nơi tìm module đã biên dịch; nó **không tự thêm cạnh đọc giữa mọi cặp module có mặt trên path**.

## 5. Thiếu requires: package export vẫn không đủ

Giữ nguyên catalog:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Bây giờ thay descriptor app thành:

~~~java
module com.acme.app {
}
~~~

App vẫn import:

~~~java
import com.acme.catalog.api.Product;
~~~

Với module source compilation, compiler có thể báo package không visible vì com.acme.app không đọc được com.acme.catalog. Nếu module catalog còn chưa được đưa vào cấu hình phân giải, thông báo cũng có thể nói module không nằm trong module graph.

Nguyên nhân không phải Product thiếu public, cũng không phải catalog quên exports. Vấn đề là app **chưa có readability** tới catalog.

Cách sửa thông thường:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Khi một ứng dụng thật sự phụ thuộc API của catalog, khai báo requires trong descriptor là hợp đồng dependency rõ ràng và bền vững.

Không nên chỉ thêm catalog.jar vào module path rồi kỳ vọng lỗi sẽ biến mất. Module path cho biết module **có thể được tìm thấy**; requires xác lập quan hệ đọc của consumer.

## 6. Có requires nhưng thiếu exports: module readable vẫn chưa đủ

Giả sử app muốn gọi ProductRepository:

~~~java
package com.acme.app;

import com.acme.catalog.internal.ProductRepository;

public class InvalidMain {
    public static void main(String[] args) {
        ProductRepository repository = new ProductRepository();
        System.out.println(repository.storageKey("SKU-1"));
    }
}
~~~

App đã requires catalog, nhưng catalog chỉ export api:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Javac có thể báo:

~~~text
package com.acme.catalog.internal is not visible
(package is declared in module com.acme.catalog,
 which does not export it)
~~~

Đây là lỗi **package accessibility**, không phải lỗi module readability. Thêm một dòng requires nữa hoặc đổi vị trí JAR không giải quyết đúng nguyên nhân.

Các hướng xử lý:

1. **Ưu tiên gọi public API** thay vì truy cập internal package.
2. Nếu package thực sự là API dành cho mọi consumer, cân nhắc exports package đó.
3. Nếu chỉ một module integration được phép truy cập, dùng qualified exports.
4. Nếu nhu cầu là deep reflection, xem opens thay vì exports.

Không nên export com.acme.catalog.internal chỉ để sửa một lỗi compile mà chưa xác định quyền truy cập đó có phù hợp với thiết kế module hay không.

## 7. Ma trận readability và exports

Xét module A muốn import public class từ package p thuộc module B:

| A đọc B? | B export p tới A? | Kết quả truy cập Java thông thường |
|---|---|---|
| Không | Không | Không truy cập được |
| Không | Có | Không truy cập được vì thiếu readability |
| Có | Không | Không truy cập được vì package chưa export |
| Có | Có | Có thể truy cập public type/member theo access modifier |

Ma trận này là điểm ghi nhớ quan trọng nhất của bài học.

Cần lưu ý: “có thể truy cập” còn giả định module đã được phân giải, class tồn tại và type/member có mức truy cập hợp lệ. Chỉ thị exports không sửa lỗi ClassNotFoundException do thiếu bytecode, và chỉ thị requires không biến private field thành public.

## 8. Unqualified exports và qualified exports

**Unqualified export** công khai một package cho mọi module đọc module nguồn:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Bất kỳ named module nào có quan hệ đọc phù hợp tới com.acme.catalog đều có thể truy cập public type trong com.acme.catalog.api.

**Qualified export** chỉ cho phép một số named module có tên cụ thể:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;

    exports com.acme.catalog.integration
        to com.acme.erp.bridge;
}
~~~

Module com.acme.erp.bridge có thể dùng public type trong com.acme.catalog.integration **nếu nó đọc được com.acme.catalog**:

~~~java
module com.acme.erp.bridge {
    requires com.acme.catalog;
}
~~~

Module com.acme.app dù cũng có requires com.acme.catalog vẫn không được hưởng qualified export dành cho bridge.

Có thể liệt kê nhiều module đích:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.integration
        to com.acme.erp.bridge,
           com.acme.reporting.bridge;
}
~~~

Tên sau to là **tên JPMS module**, không phải tên package, tên thư mục hay tên Maven artifact.

Qualified export giúp mở rộng khả năng tích hợp mà không biến toàn bộ implementation package thành API công khai.

## 9. Exports được áp dụng cho package, không phải từng class

JPMS không có cú pháp export riêng một class cụ thể:

~~~text
exports com.acme.catalog.api.Product;
~~~

Đây không phải chỉ thị module descriptor hợp lệ. Exports nhận **tên package**:

~~~java
exports com.acme.catalog.api;
~~~

Khi package được export, các public top-level type và public member có quyền truy cập hợp lệ trong package có thể được consumer sử dụng.

Nếu chỉ một số class cần trở thành API, hãy thiết kế package phù hợp:

~~~text
com.acme.catalog.api
    Product
    ProductService

com.acme.catalog.internal
    ProductRepository
    CacheIndex
~~~

Sau đó chỉ export com.acme.catalog.api. Việc tổ chức package là một phần của thiết kế encapsulation; module descriptor không thay thế bước phân tách code theo trách nhiệm.

## 10. Readability không tự bắc cầu qua requires thông thường

Xét ba module:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.order
    |
    | requires
    v
com.acme.model
~~~

Descriptor:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
module com.acme.order {
    requires com.acme.model;
    exports com.acme.order.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.order;
}
~~~

Order đọc model, app đọc order. Nhưng app **không tự động đọc model** chỉ vì order đọc model bằng requires thông thường.

Nếu app import:

~~~java
import com.acme.model.api.Customer;
~~~

compiler có thể báo app không đọc model. Package api của model đã export nhưng thiếu readability từ app đến model.

Cách sửa có thể là app khai báo requires com.acme.model trực tiếp. Nếu model là một phần của public API do order cung cấp, một lựa chọn có ý nghĩa hơn là requires transitive.

## 11. requires transitive và API của dependency

Một module nên cân nhắc **requires transitive** khi public API của nó chứa type từ module dependency.

Ví dụ type:

~~~java
package com.acme.model.api;

public record Customer(String id) {
}
~~~

OrderService công khai Customer trong chữ ký:

~~~java
package com.acme.order.api;

import com.acme.model.api.Customer;

public final class OrderService {
    public Customer getCustomer() {
        return new Customer("C-1");
    }
}
~~~

Descriptor order có thể viết:

~~~java
module com.acme.order {
    requires transitive com.acme.model;
    exports com.acme.order.api;
}
~~~

Descriptor app:

~~~java
module com.acme.app {
    requires com.acme.order;
}
~~~

Khi app đọc order, quy tắc requires transitive giúp app đồng thời đọc được model. Nếu model export com.acme.model.api, app có thể sử dụng type Customer trong public API của OrderService.

Hai điều vẫn cần tách riêng:

- requires transitive cung cấp readability tới model.
- exports com.acme.model.api của module model cung cấp accessibility tới package Customer.

Nếu model không export com.acme.model.api, requires transitive **không tự mở package đó**.

Chỉ dùng requires transitive khi phù hợp với contract API; không nên biến mọi dependency nội bộ thành transitive dependency vì sẽ làm module graph của consumer phụ thuộc rộng hơn cần thiết.

## 12. requires static và thời điểm biên dịch/chạy

Một module có thể khai báo:

~~~java
module com.acme.feature {
    requires static com.acme.annotations;
}
~~~

requires static biểu thị dependency cần cho compilation nhưng có thể vắng mặt ở runtime. Đây là trường hợp thường gặp với annotation chỉ được xử lý ở compile-time.

Tuy nhiên, khi dependency có mặt trong module graph, quyền truy cập public type của nó vẫn cần package exports phù hợp. Readability và exports không biến mất chỉ vì dependency là static.

Nếu code runtime thực sự nạp hoặc gọi type từ module optional nhưng module đó không tồn tại, ứng dụng vẫn có nguy cơ lỗi class loading/linkage. requires static không bảo đảm mọi sử dụng dependency đều an toàn khi module vắng mặt.

Nên phân biệt:

- requires: dependency bắt buộc khi phân giải module.
- requires static: dependency ở compilation, có thể vắng mặt runtime.
- requires transitive: readability lan truyền đến consumer đọc module nguồn.
- requires static transitive: kết hợp ý nghĩa static và transitive khi hợp đồng API yêu cầu.

Dùng đúng modifier giúp biểu diễn chính xác contract dependency thay vì xem mọi requires đều như nhau.

## 13. Package public nhưng không export vẫn được đóng gói kín

Một điểm dễ nhầm: **public** trong class declaration không có nghĩa class đó là public API cho toàn bộ module graph.

Ví dụ:

~~~java
package com.acme.catalog.internal;

public final class CacheManager {
    public void clear() {
    }
}
~~~

Class là public vì code thuộc các package khác **trong cùng module** có thể cần sử dụng nó. Nhưng nếu module-info.java không export com.acme.catalog.internal, module khác không thể sử dụng CacheManager qua truy cập Java thông thường.

Đây là lợi ích quan trọng của JPMS: một module có thể có nhiều package nội bộ trao đổi với nhau thông qua public type mà không bắt buộc công khai các type đó cho bên ngoài.

Ví dụ:

~~~text
com.acme.catalog
    com.acme.catalog.api          exported
    com.acme.catalog.service      not exported
    com.acme.catalog.repository   not exported
    com.acme.catalog.cache        not exported
~~~

Các package service, repository và cache có thể dùng public type của nhau **bên trong cùng module**. External consumer chỉ nhìn thấy API được export.

## 14. Qualified exports không tự tạo requires

Giả sử catalog viết:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.integration
        to com.acme.erp.bridge;
}
~~~

Dòng này không làm bridge tự động đọc catalog. Bridge vẫn cần descriptor:

~~~java
module com.acme.erp.bridge {
    requires com.acme.catalog;
}
~~~

Nếu bridge không có requires catalog, việc bridge được nêu sau to không đủ để import type thuộc package integration.

Đây là một lỗi thiết kế khá phổ biến: chỉ thấy module đích trong exports ... to rồi nhầm rằng dependency đã được thiết lập cả hai chiều.

Trong thực tế:

- **requires** xuất hiện ở module consumer, hướng tới module được dùng.
- **exports ... to** xuất hiện ở module provider, hướng quyền truy cập package tới consumer được chỉ định.

Hai chỉ thị nhìn từ hai phía của cùng một quan hệ API, nhưng không thay thế nhau.

## 15. Exports và opens giải quyết nhu cầu khác nhau

Có những trường hợp module consumer không import một type trực tiếp mà framework dùng reflection để gọi constructor hoặc truy cập private field.

Cần phân biệt:

**exports** hỗ trợ truy cập Java thông thường tới public type và public/protected member phù hợp.

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

**opens** cho phép deep reflection tới một package theo quy tắc JPMS.

~~~java
module com.acme.catalog {
    opens com.acme.catalog.entity;
}
~~~

**Qualified opens** giới hạn module được phép deep reflection:

~~~java
module com.acme.catalog {
    opens com.acme.catalog.entity
        to com.acme.persistence.framework;
}
~~~

Ví dụ framework serialization cần setAccessible(true) để đọc private field trong entity. Nếu package chưa được open phù hợp, reflection có thể gặp InaccessibleObjectException.

Điểm cần nhớ:

- exports không tự cho phép deep reflection vào private member.
- opens không tương đương việc export package để consumer import type trực tiếp trong source.
- Quy tắc package accessibility đối với public API không thể được sửa chỉ bằng cách mở package cho deep reflection.
- open module mở các package của module cho deep reflection rộng hơn; không dùng nếu chỉ một package/framework cần truy cập.

Readability và quyền truy cập reflective có các quy tắc riêng. Hãy xác định lỗi xuất hiện ở compile-time access, runtime method invocation hay deep reflection trước khi chọn cách cấu hình.

## 16. Phân biệt module path, resolution, reads và exports

Bốn khái niệm thường bị trộn lẫn:

1. **Observable**: module có thể được tìm qua module finder hoặc module path.
2. **Resolved**: module đã được chọn vào Configuration theo roots, requires hoặc service binding.
3. **Readable**: một module cụ thể có quan hệ reads tới module khác.
4. **Accessible**: package được export thích hợp và type/member có quyền truy cập hợp lệ.

Ví dụ module path:

~~~text
mods/
├── com.acme.app/
├── com.acme.catalog/
└── com.acme.experiment/
~~~

Chạy:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Không có nghĩa app đọc com.acme.experiment. Module experiment có thể chỉ observable chứ chưa resolved; ngay cả khi được resolved, app vẫn không có reads edge tới experiment nếu không có quan hệ JPMS phù hợp.

Có thể đưa module experiment vào root set:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiment \
     -m com.acme.app/com.acme.app.Main
~~~

Nhưng --add-modules **không tự thêm requires từ app tới experiment**.

Việc tách các khái niệm này giúp tránh sửa sai: lỗi module not found cần kiểm tra module path và roots, còn lỗi does not read cần kiểm tra readability graph.

## 17. So sánh classpath truyền thống

Trên classpath, class loader thường tìm class từ các JAR được cấu hình, các class đó thuộc unnamed module tương ứng. Những ranh giới module như requires/exports không được khai báo cho từng JAR.

Ví dụ:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

Trên module path:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Named module cần phụ thuộc tường minh và package được export. Không nên coi --module-path chỉ là một cách viết khác của --class-path.

Một thư viện có thể chạy tốt khi ở classpath nhưng không biên dịch được khi đưa thành named module, vì:

- Thiếu requires tới dependency.
- Dùng public type trong package mà dependency không export.
- Có split package giữa các modular JAR.
- Module name hoặc module descriptor không khớp artifact.
- Framework reflection cần opens mà descriptor chưa khai báo.

JPMS làm rõ những dependency đang bị ẩn trong cấu hình classpath chung.

## 18. Unnamed module và automatic module

**Unnamed module** chứa các class được nạp từ classpath truyền thống. Nó có các quy tắc readability rộng để hỗ trợ compatibility, nhưng không vì thế mà mọi package nội bộ của named module đều được export.

**Automatic module** xuất hiện khi một JAR chưa có module-info.class được đặt trên module path. Nó có module name tự động hoặc qua Automatic-Module-Name, và thường export tất cả package của mình theo quy tắc compatibility.

Automatic module có cơ chế đọc rộng hơn explicit named module, vì vậy nó là cầu nối khi modular hóa thư viện cũ. Tuy nhiên, nó vẫn tham gia module resolution và có thể gặp split package conflict nếu nhiều artifact cùng chứa package trùng nhau.

Điểm quan trọng: một thư viện nằm trên module path không phải lúc nào cũng là explicit named module với descriptor do tác giả viết. Cần xác định nó là explicit named module, automatic module hay code classpath để giải thích đúng quyền truy cập.

## 19. --add-reads có thể bổ sung readability tạm thời

Với ứng dụng cần tương thích, JDK hỗ trợ:

~~~text
--add-reads source.module=target.module
~~~

Ví dụ:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiment \
     --add-reads com.acme.app=com.acme.experiment \
     -m com.acme.app/com.acme.app.Main
~~~

Tùy chọn này bổ sung một quan hệ reads ở runtime. Nếu module đích có public API export cho app, app có thể truy cập API đó theo quy tắc bình thường.

Tuy nhiên:

- --add-reads không tự export package.
- --add-reads không tạo module mới hoặc tự đảm bảo module đích được resolved.
- --add-reads không chỉnh sửa module-info.class.
- Nếu cần dùng type lúc biên dịch, build có thể cần tùy chọn tương ứng ở compile-time.
- Đây là giải pháp cấu hình hoặc migration, không nên thay cho requires trong descriptor chính thức nếu dependency ổn định.

Có thể dùng đích đặc biệt ALL-UNNAMED trong một số tình huống interoperability để một named module đọc classpath, nhưng đây là lựa chọn tương thích cần quản lý cẩn thận.

## 20. --add-exports có thể mở package tạm thời

Cú pháp:

~~~text
--add-exports source.module/package=target.module
~~~

Ví dụ:

~~~bash
java --module-path mods \
     --add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.app \
     -m com.acme.app/com.acme.app.Main
~~~

Lệnh trên bổ sung export package internal cho app trong runtime. Nó không tự thêm reads edge.

Muốn code app import internal type tại compile-time khi descriptor gốc chưa export, có thể cần cung cấp tùy chọn --add-exports tương ứng cho javac. Muốn package được mở cho deep reflection, xem --add-opens thay vì chỉ --add-exports.

Dùng --add-exports có thể hữu ích với thư viện cũ hoặc kiểm thử đặc thù, nhưng việc export package internal rộng rãi làm tăng coupling và phụ thuộc vào chi tiết implementation.

Nếu module API thực sự cần công khai cho consumer ổn định, hãy cân nhắc cập nhật module-info.java thay vì cố duy trì một bộ tùy chọn startup rời rạc.

## 21. Kết hợp --add-reads và --add-exports

Một tình huống migration có thể cần cả hai:

- App chưa đọc dependency module.
- Dependency module chưa export package được dùng.

Ví dụ khái niệm:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiment \
     --add-reads com.acme.app=com.acme.experiment \
     --add-exports com.acme.experiment/com.acme.experiment.api=com.acme.app \
     -m com.acme.app/com.acme.app.Main
~~~

Bộ tùy chọn trên không thay đổi module descriptor trong JAR; nó điều chỉnh cấu hình runtime. Nếu source app được biên dịch dựa trên quan hệ này, cần cấu hình javac phù hợp từ trước.

Tuy nhiên, khi app thực sự có dependency trực tiếp và lâu dài, giải pháp kiến trúc thường là:

~~~java
module com.acme.app {
    requires com.acme.experiment;
}
~~~

và module provider export package API theo chính sách thiết kế:

~~~java
module com.acme.experiment {
    exports com.acme.experiment.api;
}
~~~

Điều này rõ ràng hơn, dễ bảo trì hơn và dễ phân tích bằng jdeps hoặc jar --describe-module.

## 22. ServiceLoader và provider module không cần exports implementation

Trong kiến trúc plugin, consumer thường cần một service contract nhưng không cần import implementation class.

Service API:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

Consumer:

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

Provider:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.card.CardGateway;
}
~~~

Provider module không cần exports com.acme.payment.card chỉ để ServiceLoader tạo instance. Consumer làm việc với type PaymentGateway từ API module, nên accessibility cần thiết nằm ở API package đã export.

Đây là ví dụ quan trọng về cách module readability và exports kết hợp với dependency inversion. App chỉ phụ thuộc vào hợp đồng service; provider có thể được đưa vào module layer qua resolution/service binding mà không cần app import class provider.

Nếu app cố import CardGateway trực tiếp từ package không export, nó sẽ bị từ chối theo quy tắc package accessibility — dù ServiceLoader vẫn có thể khởi tạo provider phù hợp.

## 23. Cách quan sát module access

Khi gặp lỗi, hãy đọc descriptor và quan sát resolution.

Xem named module trong modular JAR:

~~~bash
jar --describe-module --file dist/com.acme.catalog.jar
~~~

Xem descriptor đã biên dịch:

~~~bash
javap -v -p mods/com.acme.catalog/module-info.class
~~~

Quan sát module resolution khi chạy:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Có thể phân tích dependency tĩnh bằng jdeps:

~~~bash
jdeps --list-deps \
      --module-path mods \
      --module com.acme.app
~~~

Những công cụ này giúp trả lời:

- Module app có được phân giải không?
- Module catalog có được phân giải không?
- Descriptor app có requires catalog hay không?
- Có cạnh requires transitive nào cung cấp readability gián tiếp?
- Catalog export package nào và export cho những module nào?
- App đang import đúng package API hay nhầm package internal?

jdeps là phân tích tĩnh theo bytecode; nó không thay thế việc xem mọi service provider hoặc reflective dependency được nạp động lúc runtime.

## 24. Các lỗi thường gặp

### module not found

Ví dụ:

~~~text
module not found: com.acme.catalog
~~~

Đây thường là lỗi module resolution hoặc compiler không tìm module dependency. Kiểm tra module path, tên module, modular JAR và output directory.

### module does not read

Ví dụ:

~~~text
package com.acme.catalog.api is not visible
(module com.acme.app does not read com.acme.catalog)
~~~

Đây là lỗi readability. Kiểm tra requires của app, khả năng requires transitive phù hợp và các relation được bổ sung bởi runtime config.

### package is not exported

Ví dụ:

~~~text
package com.acme.catalog.internal is not visible
(module com.acme.catalog does not export it)
~~~

Đây là lỗi exports/accessibility. Kiểm tra chính sách public API và có nên sử dụng internal type không.

### public class vẫn không truy cập được

Class public nằm trong package không export, hoặc module consumer không có readability. Kiểm tra đủ hai điều kiện JPMS; public đơn lẻ không đủ.

### Package đã opens nhưng import vẫn lỗi

opens phục vụ deep reflection, không phải cách thay thế exports để cho phép Java source import public type từ một module khác.

### Framework báo InaccessibleObjectException

Framework đang muốn deep reflection vào package chưa được open tới module framework. Cân nhắc qualified opens hoặc --add-opens với đúng package/module đích.

### ClassNotFoundException và NoClassDefFoundError

Đây thường là vấn đề class loading/linkage hoặc dependency runtime. Cần kiểm tra artifact có chứa class, module layer, class loader, version tương thích và module graph.

### Tưởng --add-modules đã tạo readability

--add-modules bổ sung root module nhưng không tự thêm reads edge từ consumer tới module đó. Nếu import của consumer thiếu readability, cần chỉnh requires hoặc --add-reads đúng mục đích.

### Exports package sai tên

Exports phải chỉ định tên package thực sự nằm trong module. Tên module và tên package là hai định danh khác nhau; không export class theo tên đầy đủ.

## 25. Lộ trình thiết kế module access

Một quy trình thực tế:

1. Xác định **module sở hữu** mỗi API package.
2. Đặt public API ổn định vào package riêng, không trộn với implementation.
3. Export những package thật sự là hợp đồng cho consumer.
4. Trong consumer, khai báo requires tới module được dùng trực tiếp.
5. Dùng requires transitive khi public API của một module làm lộ type từ dependency.
6. Dùng qualified exports cho integration có số lượng module đích kiểm soát được.
7. Giữ package internal không export khi không có consumer hợp lệ.
8. Dùng opens riêng cho framework deep reflection, không thay thế exports một cách tùy tiện.
9. Kiểm tra output compiler và module path thực tế khi chạy.
10. Dùng --show-module-resolution để phân biệt module chỉ observable với module đã resolved.
11. Tránh duy trì --add-reads và --add-exports như cấu hình mặc định nếu có thể biểu diễn quan hệ bằng descriptor.
12. Khi mở rộng service/provider, dùng SPI/ServiceLoader để tránh phụ thuộc trực tiếp vào implementation class.

Cách tiếp cận này giúp module graph phản ánh đúng hướng phụ thuộc, đồng thời package exports thể hiện chính xác API surface của từng module.

## 26. Bài tập thực hành

**Bài 1 — Thiếu requires**

Giữ catalog export api nhưng xóa requires com.acme.catalog trong app. Thử biên dịch app rồi giải thích vì sao package được export vẫn chưa đủ để import Product.

**Bài 2 — Thiếu exports**

Giữ app requires catalog, thử import ProductRepository từ package internal chưa export. Xác định lỗi nằm ở module readability hay package exports.

**Bài 3 — Qualified exports**

Tạo module com.acme.erp.bridge, thêm exports com.acme.catalog.integration to com.acme.erp.bridge và requires tương ứng. Kiểm tra bridge truy cập được public type trong package integration nhưng app thường không truy cập được.

**Bài 4 — requires transitive**

Tạo module model và service, trong đó public API của service trả về type Customer của model. Đổi requires thành requires transitive ở service và xem app có thể sử dụng Customer khi chỉ requires service hay không.

**Bài 5 — Reflection**

Tạo entity với private field trong package không export. Thử dùng reflection qua một named module khác; quan sát sự khác nhau giữa exports, opens và --add-opens.

**Bài 6 — Module có trên path**

Đặt thêm module com.acme.experiment vào mods nhưng không requires. Dùng --show-module-resolution để xác định nó đã được phân giải hay chưa; dùng --add-modules và đánh giá liệu app có tự đọc được experiment không.

Mục tiêu của các bài tập là nhận diện chính xác từng tầng: module resolution, readability, package exports và Java access modifier.

## 27. Ghi nhớ

- Một named module muốn truy cập public type ở module khác cần **readability** tới module nguồn và **exports** phù hợp cho package chứa type.
- requires là cạnh dependency/readability; exports là quyền truy cập package. Chúng **không thay thế nhau**.
- Dù class public, nó vẫn không phải public API bên ngoài module nếu package không được export.
- exports package áp dụng cho toàn package; không có cú pháp export riêng một class.
- exports ... to giới hạn package cho những named module đích đã liệt kê; module đích vẫn cần đọc module nguồn.
- requires transitive làm readability lan truyền khi một module cung cấp public API sử dụng type từ dependency.
- requires static cho phép dependency compile-time có thể vắng mặt ở runtime, nhưng không bỏ qua quy tắc access và linkage.
- opens/opens ... to phục vụ deep reflection, không phải cách thay requires hay exports trong source-level access.
- Module xuất hiện trên module path chưa chắc đã được resolved hoặc readable từ một consumer.
- --add-reads bổ sung quan hệ đọc tạm thời; --add-exports bổ sung quyền export package; --add-opens phục vụ deep reflection.
- ServiceLoader có thể tạo provider mà package implementation không export, miễn service contract và metadata provider hợp lệ.
- Khi chẩn đoán lỗi, hãy phân biệt module not found, module does not read, package not exported và reflection denied.

**Kết luận:** Trong JPMS, tính truy cập không còn chỉ là câu hỏi class có public và có nằm trên classpath hay không. Module consumer phải đọc được module nguồn, package chứa type phải được export phù hợp, rồi access modifier Java tiếp tục áp dụng. Sự phối hợp giữa **readability và exports** tạo nên ranh giới API rõ ràng, cho phép module công khai những gì thực sự cần thiết trong khi vẫn giữ phần triển khai nội bộ được đóng gói kín.