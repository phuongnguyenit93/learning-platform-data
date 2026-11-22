# Package export và khả năng truy cập giữa các module trong Java (JPMS)

Trong Java Platform Module System (JPMS, từ Java 9), việc một lớp được khai báo `public` chưa đủ để mã ở module khác sử dụng lớp đó. Module chứa lớp phải **cho phép module gọi đọc được nó** và **export package chứa lớp**. Cơ chế này tạo ranh giới API rõ ràng, giúp thư viện công khai đúng những package cần thiết, đồng thời giữ phần hiện thực bên trong module.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `public` không đồng nghĩa với “truy cập được từ mọi module”.
- Dùng `exports`, `exports ... to` và `requires` để xây dựng API giữa các named module.
- Phân biệt quyền truy cập thông thường với quyền truy cập qua reflection (`opens`).
- Đọc lỗi biên dịch liên quan đến module readability và package visibility.
- Biên dịch, chạy và thử nghiệm một ứng dụng nhiều module bằng `--module-path`.

## 2. Ba điều kiện để truy cập một kiểu từ module khác

Giả sử module `com.example.app` muốn dùng lớp `com.example.library.api.Greeting` nằm trong module `com.example.library`. Muốn dùng lớp ở mã Java thông thường (ví dụ `import` và gọi phương thức), cần đồng thời thỏa mãn:

1. **Readability:** `com.example.app` *reads* `com.example.library`. Cách phổ biến là khai báo `requires com.example.library;` trong `module-info.java` của ứng dụng.
2. **Package export:** `com.example.library` export package `com.example.library.api` cho module ứng dụng, bằng `exports com.example.library.api;` hoặc một qualified export cho phép đúng module đó.
3. **Quy tắc truy cập của Java:** lớp phải có phạm vi truy cập phù hợp, thường là `public`; constructor, field, method được gọi cũng phải truy cập được. Quy tắc `private`, package-private, `protected` vẫn có hiệu lực.

Có thể ghi nhớ:

> Truy cập xuyên module = module đọc được module đích + package được export cho bên gọi + thành phần Java đủ mức truy cập.

`requires` thiết lập quan hệ đọc, còn `exports` công bố package như một phần API. **Hai chỉ thị này giải quyết hai vấn đề khác nhau.**

### Ví dụ tối thiểu

`module-info.java` của thư viện:

```java
module com.example.library {
    exports com.example.library.api;
}
```

`module-info.java` của ứng dụng:

```java
module com.example.app {
    requires com.example.library;
}
```

Ở đây, `com.example.app` có thể dùng các kiểu `public` trong `com.example.library.api`. Nếu thư viện còn có package `com.example.library.internal` nhưng không export, các kiểu `public` trong package `internal` vẫn không thể được ứng dụng truy cập trực tiếp theo quy tắc JPMS.

## 3. `exports` hoạt động ở mức package

Một module có thể chứa nhiều package. Từng dòng `exports` chỉ công bố **một package cụ thể**; không tự động công bố các package con.

```java
module com.example.library {
    exports com.example.library.api;
    // Không export com.example.library.api.internal
    // Không export com.example.library.impl
}
```

| Khai báo | Ý nghĩa |
| --- | --- |
| `exports com.example.library.api;` | Các module đọc được thư viện có thể truy cập kiểu `public` trong package API. |
| Không khai báo `exports` cho package | Package bị đóng đối với việc truy cập mã thông thường từ module khác. |
| `exports com.example.library.spi to com.example.plugin;` | Chỉ module `com.example.plugin` (nếu đọc được thư viện) được truy cập kiểu `public` của package SPI. |
| `opens com.example.library.model;` | Cho phép deep reflection trên package này ở thời gian chạy, không biến nó thành API có thể `import` tùy ý. |
| `open module com.example.library { ... }` | Mở tất cả package để phục vụ reflection; đây là lựa chọn phạm vi rộng, cần cân nhắc. |

**Lưu ý:** `exports` không làm cho một lớp package-private thành `public`, không bỏ qua `private` và cũng không tự thêm `requires` vào module gọi.

### Bên trong cùng module

Các package khác nhau *trong cùng một module* không cần `exports` để sử dụng nhau; chúng vẫn tuân thủ mức truy cập thông thường của ngôn ngữ Java. Ví dụ, một lớp `public` ở package `impl` có thể được lớp thuộc package `api` trong cùng module sử dụng dù package `impl` không export.

## 4. Dự án thực hành với hai named module

Cấu trúc thư mục:

```text
src/
├── com.acme.catalog/
│   ├── module-info.java
│   └── com/acme/catalog/
│       ├── api/Product.java
│       └── internal/PriceRule.java
└── com.acme.shop/
    ├── module-info.java
    └── com/acme/shop/Main.java
```

**Thư viện:** `src/com.acme.catalog/module-info.java`

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

**Lớp API:** `src/com.acme.catalog/com/acme/catalog/api/Product.java`

```java
package com.acme.catalog.api;

public final class Product {
    private final String name;

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

**Lớp hiện thực nội bộ:** `src/com.acme.catalog/com/acme/catalog/internal/PriceRule.java`

```java
package com.acme.catalog.internal;

public final class PriceRule {
    public static int discountPercent() {
        return 10;
    }
}
```

`PriceRule` là `public` nhưng package `com.acme.catalog.internal` **không được export**.

**Module ứng dụng:** `src/com.acme.shop/module-info.java`

```java
module com.acme.shop {
    requires com.acme.catalog;
}
```

**Điểm chạy:** `src/com.acme.shop/com/acme/shop/Main.java`

```java
package com.acme.shop;

import com.acme.catalog.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("Sách Java");
        System.out.println(product.getName());
    }
}
```

Tại thư mục gốc dự án, dùng JDK 9 trở lên:

```bash
javac --module-source-path src -d mods -m com.acme.catalog,com.acme.shop
java --module-path mods -m com.acme.shop/com.acme.shop.Main
```

Kết quả mong đợi:

```text
Sách Java
```

`javac --module-source-path src` cho trình biên dịch biết nguồn được tổ chức theo tên module; `-d mods` đặt kết quả biên dịch vào cây module tương ứng. Lệnh chạy dùng `--module-path mods` để tìm module và `-m module/lớp-main` để chọn điểm vào.

### Thử truy cập package không export

Sửa `Main.java` và thêm:

```java
import com.acme.catalog.internal.PriceRule;
```

Nếu sử dụng `PriceRule.discountPercent()`, việc biên dịch module ứng dụng sẽ bị từ chối vì `com.acme.catalog` không export `com.acme.catalog.internal`. Lớp `PriceRule` có `public` cũng không thay đổi kết quả.

Có hai hướng giải quyết đúng về thiết kế:

- Nếu đây là tính năng thực sự dành cho bên ngoài, cung cấp một API ổn định trong package đã export (ví dụ phương thức thuộc `com.acme.catalog.api`).
- Chỉ khi cố ý công khai trực tiếp package đó, thêm khai báo `exports com.acme.catalog.internal;` vào module thư viện. Đây là một thay đổi hợp đồng API, cần được cân nhắc.

Trong ví dụ này, nên giữ `internal` kín và đưa hành vi cần thiết qua API công khai.

## 5. Qualified exports: công khai cho module cụ thể

Đôi khi thư viện cần chia sẻ một package chuyên dụng với một module đối tác nhưng không muốn biến nó thành API chung:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.internal to com.acme.report;
}
```

Khi đó:

- `com.acme.shop` có thể dùng API chung, nhưng không thể `import` `com.acme.catalog.internal.PriceRule`.
- `com.acme.report` có thể dùng các kiểu `public` của package `internal` **nếu** module đó cũng khai báo `requires com.acme.catalog;` (hoặc có quan hệ readability tương đương).
- Một qualified export không làm thay đổi phạm vi truy cập nội bộ của class, constructor hay method.

Đây là cách có chủ đích để mở package cho một số module đã biết tên. Nó tạo sự phụ thuộc vào tên module đích; khi đổi tên module, cần cập nhật khai báo.

## 6. `requires` và `requires transitive` không thay thế `exports`

Xét ba module:

```text
com.acme.client  ->  com.acme.facade  ->  com.acme.catalog
```

Nếu `com.acme.facade` khai báo:

```java
module com.acme.facade {
    requires transitive com.acme.catalog;
    exports com.acme.facade.api;
}
```

và `com.acme.client` khai báo:

```java
module com.acme.client {
    requires com.acme.facade;
}
```

thì việc client đọc `com.acme.facade` cũng dẫn tới đọc `com.acme.catalog` nhờ `requires transitive`. Nhưng client vẫn chỉ truy cập trực tiếp được **những package mà catalog export cho client**. `requires transitive` lan truyền khả năng đọc module, không biến mọi package thành công khai.

`requires static` là biến thể khác dùng khi phụ thuộc cần có tại thời điểm biên dịch nhưng không bắt buộc có ở thời điểm chạy; nó cũng không thay thế `exports`.

## 7. `exports` và `opens`: truy cập mã thường so với reflection

Reflection có hai mức sử dụng đáng phân biệt:

- **Truy cập công khai thông thường:** mã bên ngoài sử dụng các kiểu/thành phần `public` trong package được export; reflection có thể tra cứu và sử dụng các thành phần công khai theo những quy tắc truy cập tương ứng.
- **Deep reflection:** thư viện/framework muốn truy cập thành phần không công khai, ví dụ field `private` qua `setAccessible(true)`. Với named module, package thường phải được mở bằng `opens`, `open module` hoặc cấu hình mở tương ứng ở thời gian chạy.

Ví dụ một module lưu dữ liệu cho framework:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.serializer;
}
```

Ở đây `com.acme.serializer` được phép thực hiện deep reflection trên `com.acme.catalog.model`, nhưng câu lệnh `opens` **không có nghĩa** mã nguồn của serializer được `import` và gọi trực tiếp mọi lớp thuộc model như một package đã export. Nếu cần cả hai quyền, có thể dùng đồng thời `exports` và `opens` cho cùng package.

Không nên thêm `opens` chỉ để chữa lỗi `import` ở thời điểm biên dịch; hãy kiểm tra `requires` và `exports` trước.

## 8. Classpath, module path và khả năng truy cập

| Cách đặt mã | Đặc điểm liên quan đến đóng gói |
| --- | --- |
| `--class-path` / `-cp` | Mã thông thường thuộc *unnamed module*. Không dùng `module-info.java` của ứng dụng classpath để khai báo `requires/exports`; các quy tắc truy cập Java truyền thống vẫn áp dụng. |
| `--module-path` / `-p` với explicit named module | JPMS thực thi readability và exports của `module-info.java`, bên cạnh quy tắc truy cập Java. |
| JAR không có `module-info.class` nhưng đặt trên module path | Có thể trở thành *automatic module*, với tên được xác định từ metadata/tên JAR; nó có hành vi tương thích rộng hơn về đọc/export so với explicit module. |

Với một ứng dụng classpath cần dùng named module trên module path, module đích còn phải được đưa vào tập module đã resolve (trong một số cấu hình cần `--add-modules`). Sau đó, việc truy cập trực tiếp vẫn phụ thuộc package có export phù hợp, chẳng hạn export không giới hạn.

Ngược lại, một explicit named module không thể chỉ viết `requires` đến “unnamed module” của classpath: unnamed module không có tên để khai báo. Khi chuyển một ứng dụng cũ sang JPMS, hãy kiểm tra vị trí JAR, tên module và hướng phụ thuộc trước.

## 9. Đọc và xử lý các lỗi thường gặp

**Lỗi A — Module không đọc dependency**

Thông báo thường nói module hiện tại “does not read” module chứa package, hoặc package không hiển thị do thiếu quan hệ đọc.

Cách kiểm tra: module ứng dụng có `requires ten.module;` không? Dependency đã có trên `--module-path` và tham gia module graph chưa? Tên module có đúng không?

**Lỗi B — Package không được export**

Thông báo có thể có dạng:

```text
package com.acme.catalog.internal is not visible
(package ... is declared in module com.acme.catalog,
 which does not export it)
```

Cách kiểm tra: module thư viện có export **đúng package** hay không; nếu là `exports ... to`, module gọi có nằm trong danh sách cho phép không? Không nhầm package cha với package con.

**Lỗi C — Thành phần Java không đủ mức truy cập**

Package có thể đã export, nhưng constructor `private`, phương thức package-private hoặc lớp không `public` vẫn không gọi được. Sửa thiết kế mức truy cập Java, không thể chỉ dùng `exports` để vượt qua.

**Lỗi D — Framework reflection bị chặn**

Thông báo runtime có thể là `InaccessibleObjectException`. Xác định package chứa thành phần bị truy cập và module thực hiện reflection; cân nhắc `opens package to framework.module;` nếu đúng nhu cầu.

**Lỗi E — Dùng tham số mở tạm thời khi tích hợp mã cũ**

Có thể dùng cấu hình JVM/trình biên dịch như:

```bash
# Tạm cho phép một module truy cập package nội bộ theo phạm vi chỉ định:
--add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.shop

# Tạm mở package cho deep reflection khi chạy:
--add-opens com.acme.catalog/com.acme.catalog.model=com.acme.serializer
```

Đây là **các tùy chọn đặt sau lệnh `java`/`javac` phù hợp**, không phải hai lệnh shell độc lập. `--add-opens` dành cho hành vi ở runtime; `--add-exports` có thể phải được thiết lập ở cả giai đoạn biên dịch và chạy tùy ca sử dụng. Chúng hữu ích khi chẩn đoán hoặc duy trì phần mềm cũ, nhưng trong thiết kế mới nên sửa `module-info.java` và API thay vì duy trì quyền vượt rào.

## 10. Nguyên tắc thiết kế API module

1. **Export ít nhất có thể:** chỉ các package chủ định làm API/SPI ổn định mới nên công khai; package `internal` và `impl` thường để đóng.
2. **Định nghĩa module boundary theo vai trò:** không export chỉ vì một lớp đang được đánh dấu `public`; có thể cần `public` cho mã bên trong chính module.
3. **Giảm phụ thuộc ngược:** module sử dụng API phụ thuộc vào package đã công bố; tránh phụ thuộc trực tiếp vào chi tiết triển khai.
4. **Dùng qualified exports đúng mục đích:** phù hợp với tích hợp đã biết tên module đích; ghi nhận đây là quyền mở cho đối tác cụ thể.
5. **Tách reflection khỏi API:** dùng `opens` chính xác cho framework cần deep reflection; không mở rộng toàn module khi chỉ cần một package.
6. **Kiểm tra cả biên dịch và runtime:** các cờ module path, tập module được resolve và các chỉ thị `requires/exports` phải nhất quán.

## 11. Bài tập tự kiểm tra

**Bài 1.** Module `m.data` có:

```java
module m.data {
    exports dev.demo.api;
}
```

Trong `dev.demo.api` có lớp `public class Item` và lớp `class HiddenHelper`. Module `m.app` khai báo `requires m.data;`. Hỏi `m.app` có thể dùng cả hai lớp không?

**Đáp án:** Dùng được `Item` nếu thành phần cần gọi có mức truy cập thích hợp; `HiddenHelper` là package-private nên không truy cập trực tiếp từ package khác, dù package đã export.

**Bài 2.** Module `m.data` export `dev.demo.api` nhưng **không** export `dev.demo.api.internal`. Một lớp `public` ở `dev.demo.api.internal` có thể được module khác gọi trực tiếp không?

**Đáp án:** Không. Export package cha không đồng nghĩa export package con.

**Bài 3.** `m.app` khai báo `requires m.data;` nhưng `m.data` không export package chứa kiểu cần import. Thêm `requires transitive m.data;` vào `m.app` có sửa được không?

**Đáp án:** Không. `requires transitive` chỉ liên quan readability được lan truyền đến module đọc `m.app`; package đích vẫn cần export phù hợp.

**Bài 4.** Framework cần ghi một field `private` bằng reflection trong package `dev.demo.model` thuộc module `m.data`. Có nên dùng `exports dev.demo.model;`?

**Đáp án:** Chỉ export không đáp ứng yêu cầu deep reflection vào field `private`. Xem xét `opens dev.demo.model to ten.module.framework;` và giữ phạm vi mở nhỏ nhất.

## Ghi nhớ

Một package trong named module chỉ trở thành API cho module ngoài khi có khai báo `exports` phù hợp. Module tiêu thụ còn phải đọc được module cung cấp, và mọi lời gọi vẫn chịu các quy tắc `public`/`protected`/package-private/`private` của Java. Với reflection cần quyền sâu hơn, sử dụng `opens` theo phạm vi thực sự cần thiết.