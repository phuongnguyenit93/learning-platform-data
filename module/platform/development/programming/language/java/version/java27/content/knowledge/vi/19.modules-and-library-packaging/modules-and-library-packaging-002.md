# Module descriptor với `requires`, `exports` và `opens` trong Java 27

Khi một ứng dụng Java lớn dần, việc chỉ chia mã thành các package chưa đủ để nói rõ **thư viện nào phụ thuộc thư viện nào** và **phần nào của thư viện được phép dùng từ bên ngoài**. Java Platform Module System (JPMS) giải quyết vấn đề này bằng **named module** và tệp mô tả `module-info.java`.

Trong chương **Module và đóng gói thư viện** của lộ trình **Java 27**, ba directive quan trọng nhất trong module descriptor là:

- **`requires`**: module này cần đọc module nào để sử dụng các API mà module kia cung cấp.
- **`exports`**: package nào là API công khai dành cho các module khác sử dụng bằng mã Java thông thường.
- **`opens`**: package nào cho phép module khác thực hiện **deep reflection** trong lúc chạy, chẳng hạn framework cần truy cập constructor hoặc field không `public`.

Ba directive giải quyết ba vấn đề khác nhau. Một module có thể đọc module khác nhưng vẫn không truy cập được package không xuất khẩu; ngược lại, một package có thể được mở cho reflection nhưng không trở thành API công khai để `import` và sử dụng trực tiếp.

Bài này trình bày các quy tắc của **Java SE 27**, cùng ví dụ tổ chức nhiều module, biên dịch, đóng gói và gỡ lỗi; không dựa vào cơ chế truy cập nội bộ JDK đã lỗi thời.

## 1. `module-info.java` nằm ở đâu và có vai trò gì?

Một module có tên thường chứa nhiều package và một module descriptor:

```text
src/
└── com.example.catalog/
    ├── module-info.java
    └── com/example/catalog/
        ├── api/Catalog.java
        └── internal/CatalogStore.java
```

Nội dung `module-info.java` là **module declaration**:

```java
module com.example.catalog {
    requires java.logging;
    exports com.example.catalog.api;
}
```

Cú pháp này khai báo tên module, các phụ thuộc và các package mà module muốn công bố. Nó không khai báo một class Java thông thường, không cần `package ...;`, và không nên viết nó như một class có `main()`.

Khi biên dịch, compiler tạo `module-info.class`. Với **modular JAR**, descriptor đã biên dịch nằm ở gốc JAR và được JVM/công cụ module dùng để dựng **module graph**.

### 1.1. Module khác package và JAR như thế nào?

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Package | Lớp/interface thuộc không gian tên nào? | `com.example.catalog.api` |
| Module | Nhóm package nào thuộc một đơn vị có dependency và mức đóng gói rõ ràng? | `com.example.catalog` |
| JAR | Class/resource được đóng trong một tệp phân phối nào? | `catalog.jar` |
| Module descriptor | Module phụ thuộc ai, xuất hoặc mở package nào? | `module-info.java` |

Một modular JAR thường chứa một named module. Tuy nhiên, **module không đồng nhất với JAR**: trong lúc phát triển, module có thể nằm trong một thư mục chứa `module-info.class` và các class khác.

Mặc định, package **không được export** chỉ vì trong package có lớp `public`. Không phải mọi class `public` trong module đều tạo thành API công khai cho module khác.

### 1.2. Module graph và readability

JPMS giải quyết phụ thuộc bằng việc cấu hình một tập module tại thời điểm biên dịch hoặc chạy. Khi module `com.example.app` đọc module `com.example.catalog`, nó có thể sử dụng những package mà `com.example.catalog` **export tới** `com.example.app`, nếu các quy tắc truy cập Java thông thường cũng cho phép.

```text
com.example.app
      |
      | requires
      v
com.example.catalog
      |
      | requires
      v
java.logging
```

Việc một module được đặt trên `--module-path` **không tự động** khiến mọi module khác đọc được nó. Phải phân biệt **module có thể quan sát**, **module được resolve**, và **readability** giữa các module trong cấu hình.

## 2. Cú pháp chung của module descriptor

Ví dụ một descriptor có nhiều directive:

```java
module com.example.catalog {
    requires java.logging;
    requires transitive com.example.model;
    requires static com.example.annotations;

    exports com.example.catalog.api;
    exports com.example.catalog.spi to com.example.partner;

    opens com.example.catalog.internal to com.example.inspector;

    uses com.example.catalog.spi.PriceProvider;
}
```

Trong đó:

- `requires java.logging`: module cần đọc module `java.logging`.
- `requires transitive com.example.model`: người đọc `com.example.catalog` cũng đọc được `com.example.model` theo quy tắc readability.
- `requires static com.example.annotations`: phụ thuộc bắt buộc cho kiểm tra khi biên dịch nhưng **không bắt buộc hiện diện khi chạy**.
- `exports com.example.catalog.api`: package API có thể được mọi module đọc phù hợp sử dụng.
- `exports ... to com.example.partner`: chỉ công bố package cho module được nêu tên.
- `opens ... to com.example.inspector`: cho phép deep reflection từ module cụ thể trong lúc chạy.
- `uses ...`: công bố việc module tiêu thụ một service interface; phần này thuộc cơ chế service và được đề cập ngắn ở cuối bài.

Các tên trên mang tính minh họa. Directive chỉ hợp lệ khi những module/package/type được khai báo phù hợp với nội dung thật của dự án.

`java.base` đặc biệt: mọi named module đều **ngầm đọc `java.base`**, vì vậy không cần thêm `requires java.base;` để dùng `String`, `List`, `Objects` hay `System`.

## 3. `requires`: khai báo phụ thuộc và quyền đọc module

Một khai báo đơn giản:

```java
module com.example.billing {
    requires java.sql;
}
```

Nó cho phép mã trong `com.example.billing` tham chiếu các public API thuộc package được module `java.sql` export. Việc `java.sql` đã có sẵn trong JDK không đồng nghĩa module của bạn tự đọc được nó nếu thiếu `requires`.

Ví dụ:

```java
package com.example.billing;

import java.sql.Connection;

public interface ConnectionConsumer {
    void accept(Connection connection);
}
```

`java.sql.Connection` thuộc API mà `java.sql` export, nhưng module chứa `ConnectionConsumer` cần readability tới `java.sql`.

**Lưu ý:** `requires` không tự cấp quyền truy cập mọi class của module kia. Nó chỉ thiết lập readability; còn `exports`, access modifier của type/member và các quy tắc Java khác vẫn được kiểm tra.

### 3.1. `requires transitive`: phụ thuộc được truyền cho người sử dụng API

Giả sử `com.example.catalog.api.Catalog` trả về `com.example.model.Item` trong public signature. Người dùng Catalog thường cũng cần truy cập kiểu `Item`.

Trong `com.example.model/module-info.java`:

```java
module com.example.model {
    exports com.example.model;
}
```

Trong `com.example.catalog/module-info.java`:

```java
module com.example.catalog {
    requires transitive com.example.model;
    exports com.example.catalog.api;
}
```

Trong `com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.catalog;
}
```

Mã `com.example.app` có thể sử dụng API public của `com.example.model` vì:

1. `com.example.app` đọc `com.example.catalog`.
2. `com.example.catalog` có `requires transitive com.example.model`.
3. `com.example.model` export package `com.example.model`.

Sơ đồ:

```text
com.example.app
       |
       | requires
       v
com.example.catalog
       |
       | requires transitive
       v
com.example.model

=> com.example.app được suy ra readability tới com.example.model
```

**`requires transitive` không export package hộ module phụ thuộc.** Nếu `com.example.model` không export `com.example.model`, app vẫn không thể tự do import các type trong package đó.

Khi nào dùng? Khi kiểu dữ liệu thuộc module phụ thuộc xuất hiện trong **public API** của module hiện tại và người tiêu dùng phải hiểu các kiểu đó. Không nên dùng `transitive` cho mọi phụ thuộc nội bộ, vì nó mở rộng dependency contract của thư viện và làm module graph bị ràng buộc hơn cần thiết.

### 3.2. `requires static`: phụ thuộc cần lúc biên dịch, tùy chọn khi chạy

Directive `requires static` không có nghĩa phụ thuộc là một thành viên `static` của Java class. Nó diễn đạt **phụ thuộc giai đoạn biên dịch**.

```java
module com.example.billing {
    requires static com.example.annotations;
    exports com.example.billing.api;
}
```

Ở đây `com.example.annotations` phải quan sát được khi biên dịch module, nhưng không bắt buộc được resolve hoặc hiện diện khi thực thi ứng dụng.

Tình huống điển hình: một module có các annotation phục vụ compiler hoặc các công cụ build và không cần đến annotation API đó ở runtime. Hãy cân nhắc retention policy và việc thư viện/framework có tra cứu annotation đó ở runtime hay không trước khi kết luận phụ thuộc có thể vắng mặt.

**Không nên dùng `requires static` để che giấu một phụ thuộc thật sự cần khi chạy.** Nếu code khởi tạo một class hoặc gọi một API thuộc module tùy chọn khi module ấy vắng mặt, ứng dụng vẫn có thể thất bại vì không tìm được type hoặc vì module không được resolve. Optional dependency đòi hỏi thiết kế feature detection/fallback phù hợp.

### 3.3. Phân biệt ba dạng phụ thuộc

| Directive | Cần cho biên dịch? | Cần được resolve khi chạy? | Truyền readability cho module đọc module hiện tại? |
| --- | --- | --- | --- |
| `requires other.module;` | Có | Có, trong cấu hình liên quan | Không |
| `requires transitive other.module;` | Có | Có, trong cấu hình liên quan | Có |
| `requires static other.module;` | Có | Không bắt buộc | Không |

JLS cũng cho phép kết hợp `static` và `transitive`. Trường hợp này có ngữ nghĩa chuyên biệt đối với phụ thuộc tùy chọn và truyền readability; không cần dùng nếu thư viện không có nhu cầu rõ ràng.

## 4. `exports`: xác định API ở cấp package

`exports` cho phép **mã trong module khác** truy cập các type `public` và thành viên mà Java thông thường cho phép, với điều kiện bên dùng **đọc được module** đang export.

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Giả sử module có:

```text
com.example.catalog.api.Catalog       (public class)
com.example.catalog.internal.Store   (public class)
```

Mã trong module khác có thể import `Catalog`, nhưng không thể import `Store` nếu package `internal` không được export, dù `Store` khai báo `public`.

```java
import com.example.catalog.api.Catalog;       // Hợp lệ khi có readability
// import com.example.catalog.internal.Store; // Không hợp lệ theo JPMS
```

### 4.1. Export package, không export riêng class

Cú pháp `exports` nhận **tên package**, không nhận tên class:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Không có directive hợp lệ như `exports com.example.catalog.api.Catalog;` nếu đó là tên class. Nếu muốn một class không thành API, có thể đặt nó ở package nội bộ hoặc không khai báo nó `public` (tùy nhu cầu trong package).

Export một package **không làm các thành viên `private`, package-private hoặc `protected` trở thành `public`**. Quy tắc truy cập ở cấp type/member vẫn có hiệu lực.

### 4.2. Export không lan sang subpackage

Nếu `com.example.catalog.api` được export thì package `com.example.catalog.api.internal` **không tự được export**.

```java
module com.example.catalog {
    exports com.example.catalog.api;
    // com.example.catalog.api.internal vẫn bị đóng gói
}
```

Tên package phân cấp không có nghĩa directive áp dụng đệ quy cho toàn bộ package bắt đầu bằng cùng tiền tố.

### 4.3. Qualified exports: chỉ cho module được chỉ định

Đôi khi chỉ một module bạn chọn được phép sử dụng một package hỗ trợ:

```java
module com.example.catalog {
    exports com.example.catalog.api;
    exports com.example.catalog.spi to com.example.partner;
}
```

`com.example.partner` có thể truy cập package `com.example.catalog.spi` khi có readability, còn module khác không được cấp quyền chỉ bởi directive này.

Qualified export hữu ích cho tích hợp có kiểm soát hoặc module bạn sở hữu cùng hệ thống, nhưng cũng tạo một coupling với **tên module đích**. Nếu đổi tên module hoặc tách ứng dụng, cần xem lại descriptor.

**Không nên coi `exports ... to ...` là hàng rào bảo mật chống mã độc**. JPMS là cơ chế đóng gói và truy cập trong runtime, không phải hệ thống phân quyền truy cập dữ liệu theo người dùng hoặc sandbox bảo mật.

## 5. `opens`: mở package cho deep reflection trong lúc chạy

Nhiều framework cần đọc hoặc khởi tạo đối tượng mà không gọi trực tiếp các method public trong source code. Ví dụ mapper, serializer hoặc dependency injection có thể dùng Reflection API để:

- Tìm constructor.
- Đọc metadata.
- Cố gắng gọi constructor không `public`.
- Truy cập field private hoặc method không `public` thông qua `setAccessible(true)`.

`opens` cho phép **suppression of Java language access checks trong runtime** cho một package đối với các module được chỉ định, theo quy tắc API Reflection.

```java
module com.example.catalog {
    exports com.example.catalog.api;
    opens com.example.catalog.internal to com.example.inspector;
}
```

Hệ quả:

1. `com.example.inspector` có thể dùng deep reflection trên package `internal` nếu các bước reflection hợp lệ.
2. `opens` **không** khiến mã trong `com.example.inspector` được phép `import com.example.catalog.internal.Store;` và gọi Store trực tiếp như một API exported.
3. Module không được liệt kê trong `to` không được quyền deep reflection chỉ nhờ directive này.

Nếu muốn mở package cho **tất cả module**, dùng:

```java
module com.example.catalog {
    opens com.example.catalog.dto;
}
```

### 5.1. Reflection thông thường khác deep reflection

Một package được `exports` có thể được các module có readability truy cập các API `public` theo quy tắc Java. Trong các tình huống Reflection API cho phép, public member của public type trong exported package có thể được invoke mà không cần `opens`.

**Deep reflection** là việc bỏ qua rào cản truy cập thông thường, điển hình khi gọi `setAccessible(true)` cho private field/constructor của type thuộc module khác. Trường hợp này **không được cấp quyền chỉ bởi `exports`**.

Đừng kết luận “hễ dùng reflection là phải opens”. Hãy kiểm tra framework cần truy cập **public API** hay cần **private member**. Mở thêm package khi không cần làm giảm tính đóng gói.

### 5.2. `setAccessible(true)` không tự vượt JPMS

Ví dụ module `com.example.inspector` có:

```java
Class<?> type =
    Class.forName("com.example.catalog.internal.SecretConfiguration");

var field = type.getDeclaredField("endpoint");
field.setAccessible(true); // Yêu cầu package đã mở cho module caller
```

Nếu package `internal` không mở cho caller, lời gọi `setAccessible(true)` có thể ném `InaccessibleObjectException`. Java cũng có `trySetAccessible()`, cho phép kiểm tra khả năng mở truy cập theo API thay vì mặc nhiên giả định sẽ thành công.

Thông báo lỗi có thể chứa tên module và package, giúp xác định cần sửa `opens` ở descriptor nào.

## 6. `exports` và `opens` có thể cùng xuất hiện cho một package

Một package vừa là public API vừa cần được framework truy cập sâu có thể được **export** và **open**:

```java
module com.example.api {
    exports com.example.api.dto;
    opens com.example.api.dto to com.example.json;
}
```

Như vậy:
- Mọi module đọc `com.example.api` được dùng các public type/member trong `dto`.
- `com.example.json` còn có quyền deep reflection đối với package `dto`.
- Các module khác không được deep reflection trên private member chỉ vì package đã được export.

Bảng so sánh:

| Thuộc tính | `exports p;` | `opens p;` |
| --- | --- | --- |
| Cho module khác `import` public type theo readability | Có | Không |
| Hỗ trợ truy cập trực tiếp các public member theo quy tắc Java | Có | Không tự cấp |
| Cho deep reflection từ các module được cấp quyền | Không mặc nhiên | Có |
| Áp dụng lúc biên dịch | Có | Không cấp quyền API trực tiếp |
| Áp dụng lúc chạy | Có | Có |
| Có dạng `to module.name` | Có | Có |

Ghi nhớ: `requires` là hướng **tôi cần đọc ai**, còn `exports` và `opens` là hướng **ai có thể tiếp cận phần nào của tôi**, thông qua hai cơ chế truy cập khác nhau.

## 7. `open module`: mở mọi package cho reflection

Thay vì `module`, có thể khai báo:

```java
open module com.example.legacyintegration {
    requires java.logging;
    exports com.example.legacyintegration.api;
}
```

Đây là **open module**. Khi chạy, **mọi package** trong module đều mở cho deep reflection từ các module khác.

Quan trọng:
- `open module` **không tự export tất cả package** cho việc import trực tiếp.
- Nếu muốn code từ module khác dùng public API, vẫn khai báo `exports` cho những package cần thiết.
- Không được có directive `opens ...` riêng trong một `open module`, vì mọi package đã open theo ngữ nghĩa của khai báo.
- Việc mở toàn bộ module làm giảm ranh giới đóng gói; nên ưu tiên `opens p to framework.module` theo phạm vi nhỏ nhất có thể.

`open module` có thể là giải pháp chuyển đổi có kiểm soát cho ứng dụng có nhiều công cụ runtime cần deep reflection, nhưng không nên dùng như mặc định cho một thư viện muốn giữ API rõ ràng.

## 8. Ví dụ hoàn chỉnh: 4 module cùng hoạt động

Ví dụ dưới đây minh họa đồng thời ba directive: `requires transitive`, `exports` và `opens to`. Tất cả source đều hợp lệ về cú pháp trong Java 27.

### 8.1. Cấu trúc thư mục

```text
project/
└── src/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/Item.java
    ├── com.example.catalog/
    │   ├── module-info.java
    │   └── com/example/catalog/
    │       ├── api/Catalog.java
    │       └── internal/SecretConfiguration.java
    ├── com.example.app/
    │   ├── module-info.java
    │   └── com/example/app/Main.java
    └── com.example.inspector/
        ├── module-info.java
        └── com/example/inspector/Main.java
```

### 8.2. Module dữ liệu: `com.example.model`

`src/com.example.model/module-info.java`:

```java
module com.example.model {
    exports com.example.model;
}
```

`src/com.example.model/com/example/model/Item.java`:

```java
package com.example.model;

public record Item(String id) {
    public Item {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
    }
}
```

`Item` là một record bất biến dùng làm thành phần trong public API của thư viện Catalog.

### 8.3. Module thư viện: `com.example.catalog`

`src/com.example.catalog/module-info.java`:

```java
module com.example.catalog {
    requires transitive com.example.model;

    exports com.example.catalog.api;
    opens com.example.catalog.internal to com.example.inspector;
}
```

`src/com.example.catalog/com/example/catalog/api/Catalog.java`:

```java
package com.example.catalog.api;

import com.example.model.Item;

public final class Catalog {
    public Item findItem(String id) {
        return new Item(id);
    }
}
```

`src/com.example.catalog/com/example/catalog/internal/SecretConfiguration.java`:

```java
package com.example.catalog.internal;

public final class SecretConfiguration {
    private final String endpoint = "https://example.invalid/catalog";

    public SecretConfiguration() {
    }
}
```

`SecretConfiguration` được cố ý đặt trong package **không export**. Mục đích là minh họa reflection, không phải cách lưu bí mật thực tế: mã hóa cứng token hoặc thông tin xác thực vào class là một thiết kế bảo mật kém.

### 8.4. Module ứng dụng: `com.example.app`

`src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.catalog;
}
```

`src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.catalog.api.Catalog;
import com.example.model.Item;

public class Main {
    public static void main(String[] args) {
        Item item = new Catalog().findItem("A-42");
        System.out.println(item.id());
    }
}
```

Ở đây `com.example.app` **không khai báo** `requires com.example.model;` nhưng vẫn dùng được `Item`: `com.example.catalog` có `requires transitive com.example.model` và `com.example.model` export package công khai của mình.

Nếu đổi directive trong Catalog thành `requires com.example.model;` thông thường, App phải thêm `requires com.example.model;` nếu muốn trực tiếp gọi tên `Item`.

### 8.5. Module dùng reflection: `com.example.inspector`

`src/com.example.inspector/module-info.java`:

```java
module com.example.inspector {
    requires com.example.catalog;
}
```

`src/com.example.inspector/com/example/inspector/Main.java`:

```java
package com.example.inspector;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Class.forName(
            "com.example.catalog.internal.SecretConfiguration"
        );

        var ctor = type.getDeclaredConstructor();
        ctor.setAccessible(true);
        Object configuration = ctor.newInstance();

        var field = type.getDeclaredField("endpoint");
        field.setAccessible(true);
        System.out.println(field.get(configuration));
    }
}
```

Dù type `SecretConfiguration` là `public`, package của nó không export, nên App hoặc Inspector không thể import nó như một API thông thường. Tuy nhiên Inspector có quyền deep reflection vì Catalog khai báo:

```java
opens com.example.catalog.internal to com.example.inspector;
```

Lưu ý: `opens` không khiến mọi phản chiếu đều chắc chắn thành công. Reflection còn phụ thuộc chữ ký, constructor thực tế, lỗi trong constructor và điều kiện khác. Ví dụ trên được thiết kế với một constructor không tham số để tập trung vào kiểm tra quyền.

### 8.6. Biên dịch nhiều module

Từ thư mục `project`, chạy:

```text
javac --module-source-path src -d mods -m com.example.model,com.example.catalog,com.example.app,com.example.inspector
```

`--module-source-path src` nhận cấu trúc `src/<module-name>/...`. `-d mods` tạo output cho từng module dưới `mods`. `-m` chỉ định những module cần biên dịch và compiler giải quyết các phụ thuộc cần thiết.

Chạy hai module:

```text
java --module-path mods -m com.example.app/com.example.app.Main
java --module-path mods -m com.example.inspector/com.example.inspector.Main
```

Kết quả tương ứng:

```text
A-42
https://example.invalid/catalog
```

Đường dẫn tệp, dấu phân cách đường dẫn và quoting trong script thực tế phụ thuộc hệ điều hành; lệnh ví dụ không cần dấu phân cách danh sách module path vì `mods` chỉ là một thư mục.

### 8.7. Thử thay đổi descriptor để quan sát khác biệt

| Thay đổi | Kết quả mong đợi |
| --- | --- |
| Bỏ `requires com.example.catalog` khỏi App | App không đọc được module Catalog; compile code import Catalog thất bại |
| Bỏ `exports com.example.catalog.api` khỏi Catalog | App không truy cập trực tiếp Catalog qua package API |
| Đổi `requires transitive com.example.model` thành `requires com.example.model` | App phải thêm `requires com.example.model` nếu muốn dùng trực tiếp `Item` |
| Bỏ `opens ... to com.example.inspector` | Lời gọi `setAccessible(true)` trong Inspector không được cấp quyền và có thể ném `InaccessibleObjectException` |
| Thay `opens` bằng `exports com.example.catalog.internal` | Direct public API access có thể được cấp, nhưng quyền deep reflection vào private field vẫn không được bảo đảm |
| Thay `exports ...` bằng `opens ...` cho package API | App không được phép import API đó trực tiếp chỉ nhờ `opens` |

Các tình huống trên cho thấy từng directive là một phần **có thể kiểm tra được** của hợp đồng module.

## 9. Đóng gói thành modular JAR

Khi đã biên dịch các module vào `mods`, tạo JAR cho từng module. Từ thư mục `project`:

```text
mkdir dist

jar --create --file dist/com.example.model.jar -C mods/com.example.model .
jar --create --file dist/com.example.catalog.jar -C mods/com.example.catalog .
jar --create --file dist/com.example.app.jar -C mods/com.example.app .
jar --create --file dist/com.example.inspector.jar -C mods/com.example.inspector .
```

Các JAR này chứa `module-info.class` ở gốc, vì vậy là **modular JAR**. `jar` có khả năng tạo modular JAR và xem module descriptor.

Chạy từ JAR:

```text
java --module-path dist -m com.example.app/com.example.app.Main
java --module-path dist -m com.example.inspector/com.example.inspector.Main
```

Xem descriptor của thư viện:

```text
jar --describe-module --file dist/com.example.catalog.jar
```

Descriptor có thể được diễn giải bởi công cụ theo dạng chuẩn hóa khác với thứ tự khai báo trong source, nhưng về ý nghĩa phải thể hiện `requires transitive`, `exports` và `opens` tương ứng.

**Không kết luận rằng đặt JAR ở `--module-path` đã đủ để mọi class được load và đọc bởi mọi module.** JVM cấu hình module graph từ root modules và phụ thuộc; tên module, exports và opens vẫn được áp dụng.

## 10. Kiểm tra read edge, exports và opens lúc chạy

Java cung cấp API phản ánh thông tin module:

```java
Module current = Main.class.getModule();
System.out.println(current.getName());
```

Có thể kiểm tra readability và quyền truy cập cấp module:

```java
Module app = com.example.app.Main.class.getModule();
Module catalog = com.example.catalog.api.Catalog.class.getModule();

System.out.println(app.canRead(catalog));
System.out.println(catalog.isExported("com.example.catalog.api", app));
```

Đoạn kiểm tra trên là **minh họa đặt trong module có quyền tham chiếu các class tương ứng**. Không thể đặt trực tiếp ở mọi module vì mã tham chiếu `com.example.app.Main` có thể không đọc module App; riêng các phương thức `Module` có thể được dùng trong code được tổ chức phù hợp để quan sát module graph.

Các API đáng biết:

- `Class::getModule`: lấy `Module` chứa type.
- `Module::canRead`: kiểm tra read edge.
- `Module::isExported`: kiểm tra package được export không điều kiện hoặc tới module chỉ định.
- `Module::isOpen`: kiểm tra package mở không điều kiện hoặc tới module chỉ định.
- `ModuleDescriptor` (qua `getDescriptor`) mô tả các directive của named module.

Phân biệt kiểm tra descriptor với kiểm tra runtime: VM có thể áp dụng các tùy chọn bổ sung như `--add-exports`, `--add-opens` hoặc `--add-reads` ngoài các directive được ghi trong JAR.

## 11. Gỡ lỗi `requires` và module resolution

### 11.1. “Module not found”

Một lỗi phổ biến khi chạy là:

```text
java.lang.module.FindException: Module com.example.catalog not found
```

Các câu hỏi cần kiểm tra:

1. JAR hoặc thư mục class của module đã có trên `--module-path` chưa?
2. Tên module trong descriptor có khớp tên bạn khai báo trong `requires` hoặc `-m` không?
3. Module đã được biên dịch và JAR có chứa `module-info.class` chưa?
4. Có module phụ thuộc nào chưa được cung cấp hoặc chưa thể resolve không?
5. Có đặt nhầm thư viện ở classpath thay vì module path không?

Lệnh hữu ích:

```text
java --module-path dist --list-modules
java --module-path dist --describe-module com.example.catalog
jar --describe-module --file dist/com.example.catalog.jar
```

Các lệnh này giúp quan sát module có thể nhận diện và descriptor được runtime/công cụ hiểu. `java --describe-module` có thể mô tả một module theo tên và module path đã cung cấp.

### 11.2. “package is not visible”

Khi compiler báo một package không visible, thường do **module đích không được đọc** hoặc **package chưa export**:

- Kiểm tra `requires` ở module sử dụng.
- Kiểm tra `exports` ở module cung cấp.
- Kiểm tra target `to` khi dùng qualified exports.
- Kiểm tra type/member thực sự có quyền `public` thích hợp.
- Kiểm tra không có hai module gây split-package conflict trong cấu hình.

Không giải quyết các lỗi này bằng cách đổi hàng loạt `private` thành `public`. Nếu package không export, đổi access modifier không sửa vấn đề JPMS.

### 11.3. `InaccessibleObjectException`

Lỗi khi framework cố gọi `setAccessible(true)` thường là dấu hiệu **package chưa được mở tới đúng caller module**.

Cách xử lý:

1. Xác định **module chứa type** và **package của type**.
2. Xác định **module thực sự thực hiện reflection**; không nhất thiết là module ứng dụng chính.
3. Mở đúng package đến đúng module framework, nếu thật sự cần deep reflection.
4. Ưu tiên thiết kế public API hoặc constructor thích hợp nếu framework không cần private access.
5. Viết integration test để phát hiện lỗi này khi cập nhật framework/JDK.

Ví dụ một descriptor hợp lý:

```java
module com.example.orders {
    requires com.example.serializer;

    exports com.example.orders.api;
    opens com.example.orders.dto to com.example.serializer;
}
```

Mã source trên chỉ minh họa contract giữa module; không giả định cụ thể một thư viện JSON bất kỳ dùng đúng tên module `com.example.serializer`.

## 12. Tùy chọn `--add-reads`, `--add-exports`, `--add-opens`

Java launcher và compiler có các tùy chọn hỗ trợ **bổ sung cạnh module** trong các trường hợp tích hợp hoặc kiểm thử đặc biệt:

| Tùy chọn | Tác động chủ yếu | Khi cần cân nhắc |
| --- | --- | --- |
| `--add-reads` | Bổ sung khả năng đọc module | Di trú/integration có dependency graph đặc biệt |
| `--add-exports` | Bổ sung quyền sử dụng public type/member của package | Thử nghiệm hoặc tích hợp đang phụ thuộc package chưa export |
| `--add-opens` | Bổ sung quyền deep reflection đối với package | Framework/test cần truy cập private member |

Ví dụ cú pháp runtime:

```text
java --module-path dist --add-opens=com.example.catalog/com.example.catalog.internal=com.example.inspector -m com.example.inspector/com.example.inspector.Main
```

Trong ví dụ hoàn chỉnh ở trên, flag này **không cần**, vì descriptor đã cấp quyền `opens` tương ứng. Nếu loại bỏ directive `opens` để kiểm thử, flag có thể dùng **tạm thời** khi phân tích hành vi.

Đây **không phải thay thế mặc định** cho module descriptor đúng. Các flag:
- Tạo cấu hình runtime khác với contract thể hiện trong source/JAR.
- Dễ bị quên khi chuyển môi trường hoặc tạo runtime image.
- Có thể mở rộng phạm vi truy cập hơn cần thiết, đặc biệt khi mở package nội bộ.

Trong Java hiện đại, các package nội bộ JDK được đóng gói mạnh theo chính sách hiện hành. Không xây ứng dụng mới dựa vào truy cập trái phép các phần nội bộ JDK hoặc tùy chọn `--illegal-access` theo các hướng dẫn di trú lỗi thời; dùng API public được hỗ trợ.

## 13. `requires` có phải quản lý phiên bản dependency không?

**Không.** Trong `module-info.java`, `requires com.example.catalog;` chỉ định **tên module**, không chỉ định phiên bản tối thiểu/tối đa theo cú pháp kiểu Maven/Gradle:

```java
module com.example.app {
    requires com.example.catalog;
}
```

Việc chọn artifact version, tải dependency, kiểm tra conflict và dựng module path ở build/deployment vẫn do quy trình build, package manager hoặc hệ thống phân phối đảm nhiệm. `module-info.class` có thể mang metadata phiên bản trong một số cách đóng gói, nhưng cú pháp `requires` không cho phép ghi điều kiện phiên bản như `requires catalog >= 2.0;`.

Một dependency graph được định nghĩa rõ **không tự** đảm bảo thư viện tương thích về binary/API. Hãy duy trì kiểm thử, quản trị phiên bản và chính sách phát hành riêng.

## 14. Qualified exports/opens và kiến trúc thư viện

Khi phát triển thư viện modular, chia package theo trách nhiệm sẽ khiến descriptor dễ hiểu hơn:

```text
com.example.payment.api        API cho client
com.example.payment.spi        Điểm mở rộng cho tích hợp đã biết
com.example.payment.internal   Chi tiết triển khai
com.example.payment.dto        Kiểu dữ liệu mà serializer có thể cần
```

Descriptor minh họa:

```java
module com.example.payment {
    requires java.logging;

    exports com.example.payment.api;
    exports com.example.payment.spi to com.example.partner;

    opens com.example.payment.dto to com.example.serializer;
}
```

Chọn directive theo contract:
- Public API cho mọi client: `exports api`.
- API cho một số module nội bộ/đối tác đã biết: `exports spi to ...`.
- Package được một framework cần reflect private state: `opens dto to ...`.
- Chi tiết triển khai không được bên ngoài truy cập: không export và không open.
- Dependency xuất hiện trong chữ ký API public: cân nhắc `requires transitive`.

**Không cần export tất cả package.** Mục tiêu của module là **strong encapsulation**: chỉ lộ những phần nằm trong hợp đồng sử dụng thực sự.

### 14.1. Tránh split packages

Đừng đặt cùng một package, ví dụ `com.example.common`, trải trên hai named modules trong một cấu hình module có quan hệ đọc khiến package bị trùng/không thể phân giải hợp lệ.

Nên chọn tên package duy nhất theo module hoặc tái cấu trúc thành một module sở hữu package đó. Đặc biệt cẩn thận khi chuyển một JAR lớn sang nhiều module mà nhiều JAR cũ cùng chứa một package.

### 14.2. Nhiều module không có nghĩa tự động có nhiều class loader

JPMS quản lý module identity, readability và encapsulation. Module không tương đương quy tắc “mỗi module có class loader riêng”. Class-loader arrangement phụ thuộc module layer và runtime; không thiết kế logic chỉ dựa vào suy đoán một class loader cho mỗi module.

### 14.3. Chia sẻ internal package không phải lựa chọn mặc định

Nếu liên tục cần `exports internal to ...` cho nhiều module, hãy xem lại boundaries: API hỗ trợ đó có nên chuyển thành một package `spi` được định nghĩa rõ không? Qualified exports là công cụ hữu ích, nhưng không thay thế thiết kế module interface ổn định.

## 15. `uses` và `provides`: liên quan nhưng khác phạm vi bài này

Một module không chỉ cung cấp class API. Nó có thể khai báo **service consumption** và **service provision**:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Codec;
}
```

Module triển khai:

```java
module com.example.impl {
    requires com.example.spi;
    provides com.example.spi.Codec
        with com.example.impl.DefaultCodec;
}
```

Đây là contract của `ServiceLoader`. Một `provides` directive không đồng nghĩa phải export package chứa provider implementation như API public. Tuy nhiên **service type** và khả năng đọc module chứa service interface phải được thiết kế phù hợp.

`uses` và `provides` là các directive hợp lệ của module descriptor Java 27, nhưng trọng tâm bài này vẫn là dependency readability (`requires`), API visibility (`exports`) và reflection openness (`opens`). Khi xây dựng plugin architecture, nên học thêm service binding và cách module resolution chọn provider.

## 16. Classpath, module path và automatic modules khi chuyển đổi

Có thể tiếp tục sử dụng thư viện trên **classpath**; code không thuộc named module thường nằm trong **unnamed module**. JPMS không bắt buộc mọi ứng dụng hoặc dependency phải đổi sang named modules ngay lập tức.

Với một JAR **chưa có `module-info.class`** trên module path, runtime có thể xem nó là **automatic module**. Automatic module được áp dụng các quy tắc đặc biệt để hỗ trợ chuyển đổi, ví dụ các package được xem như exported và open. Tên module automatic có thể suy ra từ tên JAR hoặc metadata, vì vậy cần xác định tên ổn định trước khi ghi nó vào `requires` của module khác.

Một số thực hành phù hợp:
- Với thư viện mới có module contract rõ ràng, cung cấp modular JAR chính thức.
- Khi dùng thư viện bên thứ ba chưa modular hóa, kiểm tra tên module thực tế bằng `jar --describe-module`.
- Tránh dựa vào automatic module mãi mãi nếu cần đóng gói mạnh và API ổn định.
- Đừng nhầm “có JAR trên classpath” với “named module có thể đọc trực tiếp toàn bộ classpath”. Phụ thuộc hỗn hợp thường cần kế hoạch di trú cụ thể.

**Không khuyến khích chuyển toàn bộ dự án sang module chỉ vì muốn sử dụng `jar`.** Modularization mang lại ranh giới API và dependency rõ hơn, nhưng cần cân nhắc thư viện bên thứ ba, reflection framework, test tooling và vận hành.

## 17. Thiết kế kiểm thử cho module descriptor

Kiểm thử source code không thay thế kiểm thử **module graph khi chạy**. Một API có thể biên dịch và chạy khi tất cả class vô tình nằm trên classpath, nhưng thất bại khi đóng thành modular JAR và đưa lên module path.

Các ca nên kiểm tra:

| Ca kiểm tra | Điều kiện mong đợi |
| --- | --- |
| Client bình thường gọi API public | Module client có `requires`, package API có `exports` |
| Client cố import internal type | Bị ngăn nếu internal package không export |
| API public lộ kiểu từ module model | `requires transitive` được dùng khi phù hợp |
| Framework reflection truy cập private field | Package `opens` đúng tới module framework |
| Module không có quyền reflection cố `setAccessible` | Truy cập bị từ chối theo quy tắc runtime |
| Chuyển từ thư mục class sang modular JAR | Descriptor vẫn đúng và chạy với `-m` |
| Module phụ thuộc vắng mặt | Lỗi được phát hiện trong phân giải module hoặc lúc chạy theo loại phụ thuộc |
| Đổi tên module framework | Qualified `opens to` được cập nhật đúng |
| Dùng JAR automatic module | Tên module thật được xác minh, không đoán theo artifact |
| Hai module chứa package trùng | Công cụ báo vấn đề/được giải quyết bằng cấu trúc hợp lệ |
| Phân phối release | Dùng module path đúng trên môi trường chạy thực |

**Lưu ý với unit test:** một số test engine hoặc mock framework cần deep reflection vào package chứa test hoặc class bị kiểm thử. Hãy mở đúng package đến đúng tên module thực hiện reflection, hoặc dùng cấu hình test-time phù hợp. Tránh mở toàn bộ module chỉ để tất cả test “chạy được” nếu thư viện sản xuất không cần quyền đó.

## 18. Bảng lỗi thường gặp

| Hiểu lầm/lỗi | Sự thật theo Java 27 | Hướng xử lý |
| --- | --- | --- |
| “Đã `requires` thì import được mọi class của module kia” | Chỉ package được export, type/member đủ quyền mới truy cập trực tiếp được | Kiểm tra `exports`, public visibility |
| “Class `public` luôn là public API toàn hệ thống” | `public` trong package không export vẫn bị encapsulate giữa module | Đặt API vào package đã export |
| “`exports` cho phép reflection private field” | Không tự cấp deep reflection | Dùng `opens` khi thật sự cần |
| “`opens` cho phép import class như bình thường” | Opens chỉ dành cho runtime reflection, không phải compile-time API access | Dùng `exports` cho public API |
| “`open module` export mọi package” | Nó mở mọi package cho reflection, không tự export mọi package | Export package API tường minh |
| “`requires transitive` tự export package của dependency” | Nó lan truyền readability, không thay `exports` của dependency | Dependency tự export API cần thiết |
| “`requires static` bảo đảm module sẽ có lúc chạy” | Đây là phụ thuộc compile-time, runtime có thể vắng mặt | Dùng `requires` nếu runtime bắt buộc |
| “Có JAR trên module path nghĩa là mọi module đọc được nó” | Module resolution/readability có quy tắc riêng | Kiểm tra module graph |
| “Exports API package sẽ tự export subpackage” | Package không được export đệ quy | Khai báo đúng từng package |
| “Module descriptor quản lý version như Maven” | `requires` chỉ tên module | Quản lý version ở build/deployment |
| “Dùng `--add-opens` lâu dài là cách chuẩn” | Flag là workaround/config bổ sung, dễ làm lệch contract | Sửa module descriptor, dùng API public |
| “Module mới thì bắt buộc mỗi module một class loader” | Class loading và module graph không tương đương | Không phụ thuộc suy đoán về loader |
| “Mỗi thư viện JAR bắt buộc có `module-info.java`” | Classpath và automatic module vẫn có chỗ đứng | Chọn migration phù hợp |

## 19. Checklist thiết kế module descriptor

Trước khi phát hành một modular library, hãy trả lời:

1. Tên module có ổn định, duy nhất và phù hợp namespace package không?
2. Public API thực sự nằm trong những package nào? Có export **đúng** các package đó không?
3. Package internal nào cần được giữ đóng, không export hoặc open?
4. Public API có dùng type từ module phụ thuộc không? Có cần `requires transitive` không?
5. Phụ thuộc nào chỉ cần lúc compile? `requires static` có thực sự an toàn lúc chạy không?
6. Framework có cần deep reflection vào package nào? Có thể thay bằng API public không?
7. Nếu cần reflection, có dùng `opens ... to module.framework` thay vì mở rộng toàn bộ không?
8. Test có chạy **trên module path** đúng như production không?
9. `jar --describe-module` và `java --describe-module` hiển thị module graph như thiết kế không?
10. Có split-package, automatic-module-name không ổn định hoặc dependency từ classpath khó resolve không?
11. Build/deploy đã cấp đúng modular JAR và các phụ thuộc runtime cần thiết chưa?
12. Có đang dùng tùy chọn truy cập nội bộ JDK từ hướng dẫn cũ thay vì API được hỗ trợ không?

**Ghi nhớ:** `requires` quy định **module nào được đọc**, `exports` quy định **package nào là API truy cập thông thường**, và `opens` quy định **package nào được truy cập sâu qua reflection**. Một descriptor tốt chỉ cấp những quyền thực sự cần, nên ranh giới thiết kế và lỗi dependency được thể hiện sớm hơn.

## Tài liệu tham khảo chính thức

- [Java Language Specification 27 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html): quy tắc module declaration, readability, `requires`, `exports`, `opens`.
- [JLS 27 §7.7.1 — Dependences](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html#jls-7.7.1): phụ thuộc `requires`, `transitive` và `static`.
- [JLS 27 §7.7.2 — Exported and Opened Packages](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html#jls-7.7.2): export, open và open module.
- [Java SE 27 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Module.html): module runtime, `canRead`, `isExported`, `isOpen`.
- [Java SE 27 API — `ModuleDescriptor`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/ModuleDescriptor.html): descriptor của named, open và automatic modules.
- [Java SE 27 API — `AccessibleObject`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html): kiểm tra và bỏ qua access checks khi reflection.
- [Java SE 27 — `javac` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--module-source-path`, `--module-path`, biên dịch named modules.
- [Java SE 27 — `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): khởi chạy module qua `-m`, module path, `--add-exports`, `--add-opens`.
- [Java SE 27 — `jar` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html): modular JAR và `--describe-module`.
- [Oracle Migration Guide — Strong Encapsulation](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): thay đổi truy cập internal JDK và hướng di trú.
