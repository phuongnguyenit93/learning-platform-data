# Phân biệt requires với import trong mã Java

Trong Java, `requires` và `import` đều thường xuất hiện khi một phần mã cần sử dụng thành phần được định nghĩa ở nơi khác. Vì vậy, hai từ khóa này dễ bị nhầm là hai cách khai báo cùng một loại dependency. Thực tế, chúng hoạt động ở hai cấp độ khác nhau:

- `requires` là chỉ thị trong `module-info.java`, khai báo quan hệ đọc giữa các module trong Java Platform Module System (JPMS).
- `import` là khai báo trong một compilation unit Java, giúp mã nguồn tham chiếu kiểu hoặc thành viên bằng tên ngắn hơn.

Một module có thể cần cả hai: `requires` để được phép đọc module chứa API, và `import` để sử dụng tên lớp trong mã nguồn mà không phải viết tên đầy đủ ở mọi nơi.

## 1. requires là gì?

`requires` là một directive trong module declaration. Nó xuất hiện bên trong `module-info.java` và khai báo module hiện tại phụ thuộc vào một module khác.

Ví dụ, module đơn hàng cần sử dụng API của module danh mục:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

Khai báo này nói với hệ thống module rằng `com.example.orders` cần đọc `com.example.catalog`. Quan hệ đó được dùng khi biên dịch và khi Java phân giải module graph lúc khởi chạy ứng dụng modular.

`requires` không chỉ ra một lớp cụ thể. Nó khai báo dependency ở cấp module. Module được yêu cầu vẫn phải công khai package phù hợp bằng `exports` nếu module khác cần truy cập API trong package đó.

Một số biến thể thường gặp:

```java
module com.example.orders {
    requires com.example.catalog;
    requires transitive com.example.money;
    requires static com.example.annotations;
}
```

- `requires`: khai báo dependency thông thường.
- `requires transitive`: công bố khả năng đọc dependency cho các module đọc module hiện tại; hữu ích khi API của module hiện tại để lộ kiểu thuộc dependency đó.
- `requires static`: dependency cần ở thời điểm biên dịch nhưng không bắt buộc có ở runtime chỉ vì directive này được khai báo.

Mọi named module đều đọc `java.base` một cách ngầm định, nên thông thường không cần viết `requires java.base;`.

## 2. import là gì?

`import` là khai báo ở đầu một tệp mã nguồn Java. Nó cho phép dùng tên đơn giản của kiểu hoặc thành viên thay vì phải viết tên đầy đủ ở mỗi vị trí.

Ví dụ, không có import:

```java
public class OrderService {
    public com.example.catalog.api.Product findProduct(String id) {
        return new com.example.catalog.api.Product(id);
    }
}
```

Có import:

```java
import com.example.catalog.api.Product;

public class OrderService {
    public Product findProduct(String id) {
        return new Product(id);
    }
}
```

Cả hai cách đều tham chiếu cùng một kiểu `com.example.catalog.api.Product`. Khai báo `import` giúp mã ngắn và dễ đọc hơn; nó không tạo ra một module dependency mới.

Java có các dạng import phổ biến:

**Import một kiểu cụ thể**

```java
import java.util.List;
import java.util.Map;
```

**Import các kiểu trong một package bằng wildcard**

```java
import java.util.*;
```

Wildcard import không đệ quy vào các package con. Ví dụ, `import java.util.*;` không import các kiểu thuộc `java.util.concurrent`.

**Static import**

```java
import static java.lang.Math.PI;
import static java.lang.Math.sqrt;
```

Sau đó có thể dùng `PI` và `sqrt(25)` trực tiếp trong mã nguồn. Static import cũng chỉ ảnh hưởng cách viết tên trong compilation unit, không khai báo module dependency.

## 3. Khác nhau ở vị trí và phạm vi tác động

| Tiêu chí | `requires` | `import` |
|---|---|---|
| Vị trí | Trong `module-info.java` | Trong tệp mã nguồn Java thông thường |
| Cấp độ | Module | Compilation unit |
| Mục đích | Khai báo module hiện tại cần đọc module khác | Cho phép tham chiếu kiểu hoặc thành viên bằng tên ngắn |
| Đối tượng | Module có tên | Kiểu, kiểu lồng nhau hoặc thành viên static |
| Ảnh hưởng module graph | Có | Không |
| Tạo quyền truy cập package | Thiết lập quan hệ đọc; package vẫn cần được export phù hợp | Không cấp quyền truy cập package |
| Có thể thay thế nhau? | Không | Không |

Một cách nhớ ngắn gọn:

- `requires` trả lời: **Module của tôi cần đọc module nào?**
- `import` trả lời: **Trong tệp mã nguồn này, tôi muốn viết tên kiểu hoặc thành viên nào ngắn gọn hơn?**

Hai câu hỏi có liên quan, nhưng không phải cùng một câu hỏi.

## 4. Ví dụ kết hợp requires và import

Giả sử có hai module:

- `com.example.catalog` cung cấp kiểu `Product`.
- `com.example.orders` sử dụng `Product` để tạo đơn hàng.

Cấu trúc đơn giản:

```text
catalog/
└── src/
    └── com.example.catalog/
        ├── module-info.java
        └── com/example/catalog/api/Product.java

orders/
└── src/
    └── com.example.orders/
        ├── module-info.java
        └── com/example/orders/OrderService.java
```

### Bước 1: Module catalog công khai API

Tệp `catalog/module-info.java`:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Tệp `Product.java`:

```java
package com.example.catalog.api;

public record Product(String id, String name) {
}
```

Chỉ thị `exports` cho phép module khác truy cập các kiểu public trong package `com.example.catalog.api`.

### Bước 2: Module orders khai báo dependency

Tệp `orders/module-info.java`:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

Chỉ thị `requires` tạo quan hệ đọc từ orders tới catalog. Module orders có thể sử dụng các package được catalog công khai, tùy theo các quy tắc truy cập Java thông thường.

### Bước 3: Mã nguồn orders import kiểu Product

Tệp `OrderService.java`:

```java
package com.example.orders;

import com.example.catalog.api.Product;

public class OrderService {
    public String describe(Product product) {
        return "Order for " + product.name();
    }
}
```

Ở đây hai khai báo có vai trò riêng:

- `requires com.example.catalog;` nằm trong descriptor của module orders, khai báo quan hệ module.
- `import com.example.catalog.api.Product;` nằm trong tệp `OrderService.java`, giúp mã nguồn sử dụng tên ngắn `Product`.

Nếu mã nguồn dùng tên đầy đủ, có thể bỏ import:

```java
package com.example.orders;

public class OrderService {
    public String describe(com.example.catalog.api.Product product) {
        return "Order for " + product.name();
    }
}
```

Nhưng module orders vẫn cần `requires com.example.catalog;` vì mã nguồn của một named module vẫn phải có khả năng đọc module chứa kiểu được sử dụng.

## 5. Vì sao import không thay thế được requires?

Hãy thử bỏ directive `requires` khỏi `module-info.java` của orders nhưng giữ import:

```java
module com.example.orders {
}
```

Trong mã nguồn:

```java
import com.example.catalog.api.Product;

public class OrderService {
    Product find() {
        return null;
    }
}
```

Nếu `com.example.catalog` nằm trên module path và là named module, module orders chưa khai báo quan hệ đọc tới nó. Import không thể tự tạo quan hệ đó. Trình biên dịch có thể báo lỗi rằng package thuộc module khác không hiển thị vì module hiện tại không đọc module đó.

Ngược lại, nếu có `requires com.example.catalog;` nhưng không viết import, module orders vẫn có quan hệ đọc tới catalog. Ta chỉ cần dùng tên đầy đủ:

```java
package com.example.orders;

public class OrderService {
    com.example.catalog.api.Product find() {
        return null;
    }
}
```

Điều này cho thấy:

- Có import không đồng nghĩa với có module readability.
- Có requires không đồng nghĩa với đã import một kiểu cụ thể.
- Hai khai báo có thể cùng cần thiết trong một chương trình modular.

## 6. Vì sao requires không thay thế được import?

`requires` chỉ khai báo module mà mã nguồn hiện tại có thể đọc. Nó không đưa tên các lớp trong module đó vào namespace của mọi tệp Java.

Ví dụ:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

Trong `OrderService.java`, ta vẫn cần một trong hai cách sau để dùng kiểu `Product`.

Cách 1: dùng import:

```java
import com.example.catalog.api.Product;

public class OrderService {
    Product find() {
        return null;
    }
}
```

Cách 2: dùng tên đầy đủ:

```java
public class OrderService {
    com.example.catalog.api.Product find() {
        return null;
    }
}
```

Nếu chỉ viết:

```java
public class OrderService {
    Product find() {
        return null;
    }
}
```

mà không import `Product` và không có kiểu `Product` phù hợp trong package hiện tại hoặc các nguồn tên được xét, trình biên dịch không thể tự suy ra rằng tên này thuộc `com.example.catalog.api.Product`.

`requires` không phải wildcard import của một module. Nó không đưa tất cả kiểu trong module vào phạm vi tên của tệp mã nguồn.

## 7. Import cũng không vượt qua exports

Ngay cả khi module orders đã khai báo:

```java
module com.example.orders {
    requires com.example.catalog;
}
```

orders chỉ có thể sử dụng các package mà catalog cho phép truy cập theo quy tắc JPMS.

Ví dụ catalog chỉ export API:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Một lớp nằm trong package nội bộ:

```java
package com.example.catalog.internal;

public class ProductRepositoryImpl {
}
```

Module orders không thể biến package nội bộ thành API công khai chỉ bằng cách viết:

```java
import com.example.catalog.internal.ProductRepositoryImpl;
```

Import không cấp thêm quyền truy cập. Để mã bên ngoài truy cập package theo cách thông thường, module sở hữu package phải export package đó và module tiêu thụ phải đọc module sở hữu. Sau đó, các access modifier Java vẫn tiếp tục được áp dụng.

Đây là lý do `requires`, `exports` và `import` cần được hiểu cùng nhau:

- `requires` thiết lập quan hệ đọc giữa module.
- `exports` công khai package từ module sở hữu.
- `import` giúp mã nguồn tham chiếu kiểu trong package đã có thể truy cập.

## 8. Import có tạo dependency cho Maven hoặc Gradle không?

Không. Import không tự động thêm thư viện vào cấu hình build và cũng không tải JAR từ repository.

Ví dụ:

```java
import org.example.json.JsonParser;
```

Dòng import này chỉ hợp lệ nếu kiểu `JsonParser` đã có sẵn trên classpath hoặc module path phù hợp. Nếu thư viện chưa được cung cấp, trình biên dịch không thể tìm thấy kiểu đó.

Trong Gradle, dependency artifact có thể được khai báo:

```groovy
dependencies {
    implementation "org.example:json-library:1.2.0"
}
```

Nếu thư viện là named module và module hiện tại chạy theo JPMS, descriptor còn cần khai báo module tương ứng:

```java
module com.example.application {
    requires com.example.json;
}
```

Tên module `com.example.json` phải khớp với tên module mà JAR thực tế công bố; tên artifact và tên module không nhất thiết giống nhau.

Như vậy có ba việc riêng:

1. Công cụ build cung cấp artifact và phiên bản dependency.
2. `requires` khai báo module hiện tại cần đọc module nào.
3. `import` giúp mã nguồn sử dụng tên kiểu hoặc thành viên.

## 9. Trường hợp ứng dụng chạy trên classpath

Khi chạy trên classpath, các lớp thuộc unnamed module của classloader tương ứng. Trong mô hình này, ứng dụng không khai báo dependency bằng `requires` cho từng JAR trên classpath.

Mã nguồn Java vẫn có thể dùng `import` như bình thường:

```java
import java.util.List;
import com.example.catalog.api.Product;
```

Khi chuyển sang named module trên module path, mã nguồn vẫn có thể giữ các import đó, nhưng module descriptor cần khai báo các quan hệ đọc tương ứng. Package được sử dụng cũng phải được module sở hữu export theo quy tắc JPMS.

Một named module không thể khai báo `requires` trực tiếp tới unnamed module. Vì vậy, khi chuyển một ứng dụng cũ sang JPMS, cần xem xét cách cung cấp các thư viện cũ và ranh giới giữa classpath với module path.

## 10. Các lỗi thường gặp và cách hiểu

| Tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Import một kiểu từ named module nhưng báo package không hiển thị | Module hiện tại chưa đọc module sở hữu | Thêm `requires` đúng tên module |
| Đã requires nhưng không tìm thấy tên lớp đơn giản | Tệp mã nguồn chưa import kiểu hoặc chưa dùng tên đầy đủ | Thêm `import` hoặc viết tên đầy đủ |
| Import package internal bị từ chối | Module sở hữu chưa export package | Dùng API đã export hoặc thiết kế lại ranh giới module |
| Có import nhưng build báo không tìm thấy package | Artifact chưa có trên classpath/module path | Khai báo dependency trong Maven/Gradle hoặc cấu hình đường dẫn phù hợp |
| Thêm import nhưng module graph không thay đổi | Import không tham gia module resolution | Khai báo dependency trong `module-info.java` |
| Thêm requires nhưng mã vẫn báo không tìm thấy tên kiểu ngắn | Requires không import tên kiểu vào compilation unit | Thêm import tương ứng |

Khi đọc lỗi biên dịch, hãy xác định lỗi thuộc cấp nào. Lỗi module readability thường liên quan `requires`; lỗi package visibility liên quan `exports`; lỗi tên kiểu trong mã nguồn thường liên quan `import`, tên đầy đủ hoặc việc cung cấp artifact.

## 11. Quy trình kiểm tra khi sử dụng một kiểu từ module khác

Khi cần sử dụng một kiểu từ module khác, có thể kiểm tra theo thứ tự:

1. **Xác định artifact chứa kiểu:** tìm đúng JAR hoặc module sở hữu package.
2. **Kiểm tra đường dẫn:** đảm bảo artifact được cung cấp trên module path cho ứng dụng modular.
3. **Xác định tên module:** dùng tên thực tế mà descriptor hoặc automatic module công bố.
4. **Kiểm tra package export:** module sở hữu phải export package cần sử dụng.
5. **Khai báo requires:** module hiện tại phải đọc module sở hữu.
6. **Import kiểu:** thêm import trong tệp Java nếu muốn dùng tên đơn giản.
7. **Biên dịch và chạy:** kiểm tra cả module graph lẫn dependency runtime.

Ví dụ, để dùng `Product` từ `com.example.catalog.api`, cần module catalog công khai package đó, module orders khai báo `requires com.example.catalog;`, artifact catalog có mặt trên module path và tệp Java có thể viết `import com.example.catalog.api.Product;`.

## Kết luận

`requires` và `import` giải quyết hai vấn đề khác nhau trong Java. `requires` là directive của JPMS, khai báo module hiện tại cần đọc module nào và tham gia xây dựng module graph. `import` là khai báo của một compilation unit, giúp mã nguồn tham chiếu kiểu hoặc thành viên bằng tên ngắn.

Import không tạo module dependency, không thêm JAR vào build và không vượt qua ranh giới `exports`. Requires cũng không tự đưa tên lớp vào phạm vi của mọi tệp Java. Khi một named module sử dụng kiểu từ module khác, cần đảm bảo artifact có mặt, module được đọc, package được export và mã nguồn tham chiếu kiểu bằng import hoặc tên đầy đủ.

Hãy nhớ ba lớp trách nhiệm: build tool cung cấp thư viện, `requires` thiết lập quan hệ module, còn `import` làm cho mã nguồn dễ viết và dễ đọc hơn.