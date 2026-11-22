# Readability của named module

Trong Java Platform Module System (JPMS), một module có thể tồn tại trên module path nhưng code của module khác vẫn không được phép sử dụng các kiểu của nó. Một điều kiện quan trọng là **readability**: module đang viết code có đọc module chứa kiểu mà nó muốn sử dụng hay không.

Readability là quan hệ giữa các module trong module graph. Nó trả lời câu hỏi: “Module A có thể đọc module B không?”. Đây là điều kiện cần để sử dụng kiểu từ B, nhưng chưa đủ. Package chứa kiểu đó còn phải được export phù hợp và kiểu/member phải đáp ứng quy tắc truy cập Java.

## 1. Readability là gì?

Với named module, directive `requires` trong `module-info.java` khai báo dependency trực tiếp và tạo quan hệ đọc module.

Ví dụ:

~~~java
module com.acme.orders {
    requires com.acme.catalog;
}
~~~

Khai báo này cho biết module `com.acme.orders` đọc module `com.acme.catalog`. Code trong orders có thể tham chiếu các kiểu public thuộc package mà catalog export, nếu các điều kiện truy cập khác cũng thỏa mãn.

Có thể hình dung:

~~~text
com.acme.orders  ──reads──>  com.acme.catalog
~~~

Một module không tự động đọc mọi module chỉ vì các JAR của chúng cùng nằm trên module path. Module path là nơi tìm module; readability là quan hệ được xác định trong module graph sau khi phân giải.

Readability cũng không đồng nghĩa với việc nạp tất cả class của module vào bộ nhớ. Nó là quyền/quan hệ ở cấp module để compiler và runtime áp dụng quy tắc truy cập.

## 2. Quan hệ đọc trực tiếp qua requires

Nếu A khai báo `requires B`, A đọc B:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

~~~java
module com.acme.service {
    requires com.acme.model;
}
~~~

Graph có hai cạnh dependency:

~~~text
com.acme.app ──requires──> com.acme.service
com.acme.service ──requires──> com.acme.model
~~~

Từ các khai báo trên, app đọc service. Service đọc model. App **không tự động đọc model** chỉ vì service có dependency tới model.

Đây là điểm quan trọng khi đọc module descriptor: dependency của một module không mặc nhiên được truyền cho tất cả consumer của module đó. Mỗi module nên khai báo rõ những module mà code của chính nó cần đọc, trừ khi dependency được truyền qua `requires transitive`.

Ngoài dependency được khai báo, mọi named module (trừ chính `java.base`) có một yêu cầu ngầm tới `java.base`. Vì vậy, module thông thường có thể sử dụng các API nền tảng như `java.lang.String`, `java.util.List` mà không cần viết `requires java.base;` trong descriptor.

## 3. Readability có tính truyền qua khi dùng requires transitive

`requires transitive` cho phép một module truyền khả năng đọc dependency tới các module đọc nó.

Ví dụ:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

Nếu app khai báo:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

thì app đọc được cả service và model:

~~~text
com.acme.app
     │
     └── requires ──> com.acme.service
                              │
                              └── requires transitive ──> com.acme.model

Readability của app:
  app ──reads──> service
  app ──reads──> model
~~~

Có thể diễn đạt quy tắc như sau:

- A đọc trực tiếp B khi A khai báo `requires B`.
- Nếu A đọc B và B khai báo `requires transitive C`, A cũng đọc C.
- Quy tắc được áp dụng tiếp theo chuỗi các dependency transitive.
- Một cạnh `requires` thông thường của B không tự truyền C cho A.

`requires transitive` không sao chép code, không gộp module và không biến C thành một phần của B. Nó chỉ mở rộng quan hệ readability của consumer.

## 4. Khi nào nên dùng requires transitive?

Nên cân nhắc `requires transitive` khi kiểu của dependency xuất hiện trong API public của module và consumer cần đọc kiểu đó để sử dụng API.

Ví dụ module model cung cấp kiểu `Product`:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
package com.acme.model.api;

public record Product(String id, String name) {
}
~~~

Module service sử dụng `Product` trong chữ ký public:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
package com.acme.service.api;

import com.acme.model.api.Product;

public interface ProductService {
    Product findById(String id);
}
~~~

Consumer chỉ cần:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Vì service công khai `Product` trong API và khai báo model là transitive, app đọc được model để import và sử dụng `Product`.

Nếu service chỉ dùng model trong implementation nội bộ, còn API public chỉ trả về kiểu do service sở hữu, hãy dùng `requires` thông thường:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

Ví dụ API không làm lộ kiểu của model:

~~~java
package com.acme.service.api;

public record ProductSummary(String id, String displayName) {
}
~~~

Consumer của service chỉ cần đọc service. Việc service dùng model bên trong không phải lý do để truyền dependency model tới mọi consumer.

### Hai cách xử lý khi consumer cần kiểu của dependency

Giả sử app muốn sử dụng trực tiếp `Product`:

**Cách 1 — service công khai dependency transitive**

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Cách này phù hợp nếu service xác định model là một phần của hợp đồng API mà consumer nên đọc được thông qua service.

**Cách 2 — app khai báo dependency trực tiếp**

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.model;
}
~~~

Cách này phù hợp nếu app chủ động sử dụng model vì nhu cầu riêng của app. Dependency được thể hiện ngay tại nơi sử dụng.

Không nên chọn `transitive` chỉ để làm hết lỗi “package is not visible”. Hãy kiểm tra kiểu của dependency có nằm trong public API của module trung gian hay không và consumer có thực sự nên phụ thuộc vào nó hay không.

## 5. Readability khác exports và opens

Một module có thể đọc module khác nhưng vẫn không truy cập được package mà module kia giữ kín.

Ví dụ:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Module app:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

App đọc catalog, nhưng chỉ có thể sử dụng các kiểu public trong package `com.acme.catalog.api`. Nếu app cố import kiểu trong `com.acme.catalog.internal`, compiler báo package không được export hoặc không nhìn thấy.

Ba khái niệm cần được kiểm tra riêng:

| Khái niệm | Câu hỏi được trả lời | Directive |
| --- | --- | --- |
| Readability | Module A có đọc module B không? | `requires`, `requires transitive` |
| Export | Module B công khai package nào cho code Java thông thường? | `exports` |
| Open | Module B cho phép module nào deep reflection vào package? | `opens` |

Để app gọi được một method public trong package API của catalog, cần đồng thời:

1. App đọc module catalog.
2. Catalog export package chứa kiểu đó cho app (hoặc export không giới hạn).
3. Kiểu và member đáp ứng quy tắc truy cập Java thông thường.

`opens` không làm package trở thành API compile-time. Nó dành cho reflection khi chạy, chẳng hạn framework cần truy cập private field.

## 6. Ví dụ hoàn chỉnh: ba module app, service và model

Giả sử có ba module:

~~~text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/api/Product.java
├── com.acme.service/
│   ├── module-info.java
│   └── com/acme/service/api/ProductService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Module model:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
package com.acme.model.api;

public record Product(String id, String name) {
}
~~~

Module service truyền readability của model vì `Product` xuất hiện trong public API:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

~~~java
package com.acme.service.api;

import com.acme.model.api.Product;

public class ProductService {
    public Product findFeatured() {
        return new Product("P-100", "Java Module Guide");
    }
}
~~~

Module app chỉ yêu cầu service:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

~~~java
package com.acme.app;

import com.acme.model.api.Product;
import com.acme.service.api.ProductService;

public class Main {
    public static void main(String[] args) {
        Product product = new ProductService().findFeatured();
        System.out.println(product.id() + ": " + product.name());
    }
}
~~~

Biên dịch từ thư mục chứa `src`:

~~~bash
javac --module-source-path src -d out \
  -m com.acme.model,com.acme.service,com.acme.app
~~~

Chạy app:

~~~bash
java --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
P-100: Java Module Guide
~~~

App không khai báo `requires com.acme.model`, nhưng vẫn import được `Product` nhờ service đã khai báo `requires transitive com.acme.model`.

Nếu đổi descriptor service thành:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

thì code app vẫn đọc được `ProductService`, nhưng import `Product` sẽ không còn hợp lệ nếu app không khai báo `requires com.acme.model` trực tiếp. Đây là ví dụ thực tế cho thấy readability transitive ảnh hưởng trực tiếp tới khả năng biên dịch consumer.

## 7. Readability trong các trường hợp đặc biệt

### requires static

~~~java
module com.acme.report {
    requires static com.acme.annotations;
}
~~~

`requires static` biểu thị dependency cần ở compile-time nhưng có thể vắng mặt khi chạy. Nó hữu ích với một số annotation hoặc API chỉ phục vụ quá trình biên dịch. Nếu chương trình thực sự sử dụng class của dependency khi chạy, việc dependency vắng mặt vẫn có thể gây lỗi nạp hoặc liên kết.

Có thể kết hợp `static` và `transitive` khi hợp đồng cần truyền readability trong giai đoạn biên dịch nhưng dependency vẫn là tùy chọn ở runtime. Chỉ sử dụng khi semantics đó thực sự phù hợp với API.

### Automatic module

JAR cũ không có `module-info.class` khi đặt trên module path có thể được xem là automatic module. Automatic module có quy tắc readability và export rộng hơn explicit named module. Không nên lấy quy tắc của automatic module để suy luận rằng một named module bình thường có thể đọc mọi module trên module path.

Khi chuyển thư viện từ automatic module sang explicit named module, cần khai báo rõ `requires` và `exports`. Các consumer có thể phải bổ sung dependency trực tiếp nếu trước đó dựa vào hành vi rộng của automatic module.

### Unnamed module

Code chạy trên classpath thuộc unnamed module. Unnamed module có khả năng đọc rộng các module trong cấu hình runtime theo quy tắc của JPMS, nhưng điều đó không có nghĩa named module cũng có readability rộng như vậy.

Khi ứng dụng chuyển từ classpath sang module path, các dependency trước đây hoạt động nhờ unnamed module có thể cần khai báo rõ trong `module-info.java`.

## 8. Điều chỉnh readability khi cần tương thích

Có thể bổ sung quan hệ đọc module bằng tùy chọn launcher:

~~~bash
java --add-reads com.acme.app=com.acme.legacy \
  --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

`--add-reads source=target` yêu cầu module nguồn đọc module đích trong lần chạy đó. Đây là cơ chế hữu ích cho tương thích hoặc chẩn đoán, đặc biệt khi chưa thể sửa descriptor của dependency.

Ở compile-time, `javac` cũng có tùy chọn `--add-reads` tương ứng. Runtime option không tự sửa `module-info.class` và không thay đổi source descriptor.

Không nên dùng `--add-reads` như giải pháp mặc định cho kiến trúc lâu dài. Nếu dependency là một phần ổn định của module, hãy khai báo `requires` trong source để dependency được quản lý, review và kiểm tra cùng code.

## 9. Chẩn đoán lỗi readability

Khi compiler hoặc JVM báo module không đọc được module khác, hãy xác định đúng giai đoạn và quan hệ:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `module not found` | Module cần thiết không có trên module path/module source path | Kiểm tra vị trí artifact và tên module trong descriptor |
| `package ... is not visible` | Module đọc được nhưng package chưa export, hoặc thiếu readability | Kiểm tra cả `requires` và `exports` |
| App dùng kiểu từ dependency bắc cầu nhưng compile thất bại | Module trung gian dùng `requires` thông thường | App khai báo dependency trực tiếp hoặc module trung gian công khai transitive nếu phù hợp |
| Runtime báo thiếu module bắt buộc | Dependency không có trong runtime configuration | Kiểm tra runtime module path và các root module |
| Code classpath hoạt động nhưng named module thất bại | Trước đây code dựa vào readability rộng của unnamed module | Khai báo dependency và package access rõ ràng |

Các lệnh hữu ích:

~~~bash
# Hiển thị module graph được phân giải khi chạy
java --show-module-resolution \
  --module-path out \
  --module com.acme.app/com.acme.app.Main

# Kiểm tra dependency của một module
jdeps --check com.acme.app --module-path out
~~~

Khi dùng `jdeps`, hãy bảo đảm module path chứa các module mà công cụ cần phân tích. Nếu cần kiểm tra descriptor cụ thể, có thể dùng `jar --describe-module` hoặc `javap -v module-info.class`.

## 10. Nguyên tắc thiết kế

1. **Requires trực tiếp:** mỗi named module khai báo dependency mà code của nó thực sự cần đọc.
2. **Transitive có chủ đích:** chỉ truyền readability khi dependency xuất hiện trong API public và consumer cần dùng kiểu đó.
3. **Không dựa vào module path:** việc JAR tồn tại trên module path không tự tạo quan hệ đọc cho named module.
4. **Tách readability khỏi visibility:** kiểm tra cả `requires` và `exports`; đừng dùng một directive để giải quyết nhầm vấn đề của directive kia.
5. **Giữ public API gọn:** module trung gian không nên truyền mọi dependency của implementation tới consumer.
6. **Kiểm tra cả compile và runtime:** module graph và module path của hai giai đoạn phải phù hợp.
7. **Giảm ngoại lệ cấu hình:** dùng `--add-reads` cho tương thích có kiểm soát; đưa dependency bền vững vào descriptor.

## Kết luận

Readability xác định module nào có thể đọc module nào trong JPMS. `requires` tạo quan hệ đọc trực tiếp; `requires transitive` truyền khả năng đọc tới consumer khi dependency là một phần của hợp đồng public. Readability vẫn phải đi cùng `exports` để code Java thông thường truy cập package và kiểu public.

Thiết kế named module rõ ràng bằng dependency trực tiếp, API nhỏ và transitive có chủ đích giúp module graph dễ hiểu, giảm phụ thuộc vô tình và giữ thay đổi nội bộ ít ảnh hưởng tới consumer.
