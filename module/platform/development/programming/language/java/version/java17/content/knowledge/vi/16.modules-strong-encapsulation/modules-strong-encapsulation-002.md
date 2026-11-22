# `module-info.java`, `requires` và quan hệ đọc module trong Java 17

Java Platform Module System (JPMS) tổ chức ứng dụng thành các **module** có tên, khai báo dependency và kiểm soát package nào được module khác sử dụng. Trong mỗi named module, tệp `module-info.java` là module descriptor (bản mô tả module). Chỉ thị `requires` khai báo module hiện tại phụ thuộc vào module khác và tạo quan hệ **readability** — khả năng một module đọc các kiểu được module kia cung cấp.

Ba khái niệm cần tách biệt:

- **Module descriptor:** khai báo tên module, dependency và các package được công khai.
- **`requires`:** cho biết module nào cần được đọc để biên dịch và chạy.
- **Readability:** xác định module nào có thể nhìn thấy các kiểu thuộc module khác; quyền truy cập package còn phụ thuộc `exports` và các quy tắc truy cập Java.

Ví dụ một module ứng dụng:

```java
module com.example.app {
    requires java.sql;
    requires com.example.service;
}
```

Khai báo này nói rằng module `com.example.app` cần đọc module `java.sql` và `com.example.service`. Nó không có nghĩa toàn bộ package của hai module kia tự động được mở cho ứng dụng. Module được yêu cầu vẫn phải export package phù hợp.

> **Phiên bản:** JPMS được giới thiệu trong Java 9 và vẫn là nền tảng module chính thức trong Java 17. Các ví dụ dùng cú pháp ổn định, không cần bật preview.

## 1. Module là gì?

Một **module** là đơn vị tổ chức mã nguồn và dependency có tên. Module có thể chứa:

- Các package và class/interface/record.
- Một module descriptor `module-info.java`.
- Các dependency tới module khác.
- Quy tắc export package cho module khác.
- Quy tắc mở package cho reflection khi cần.

So với package, module có phạm vi lớn hơn:

| Package | Module |
|---|---|
| Nhóm các kiểu liên quan theo namespace | Nhóm package thành một đơn vị triển khai và dependency |
| Tránh xung đột tên kiểu | Kiểm soát module đọc module nào |
| Có quy tắc truy cập package và member | Có thêm ranh giới export/open ở cấp module |
| Không tự khai báo dependency tới package khác | Khai báo dependency bằng `requires` |

Ví dụ:

```text
com.example.application
├── module-info.java
└── com/example/application/
    ├── Main.java
    └── config/
        └── Settings.java
```

Thư mục module chứa một module descriptor ở root của module source. Các package nằm bên dưới theo cấu trúc package thông thường.

### 1.1. Named module và classpath

Java 17 vẫn hỗ trợ ứng dụng chạy trên classpath. Khi các class được đặt trên classpath mà không thuộc named module, chúng thường nằm trong **unnamed module** của class loader tương ứng.

Named module được mô tả bằng `module-info.java` và được tìm qua **module path**. Đây là hai mô hình triển khai khác nhau:

| Mô hình | Cách nạp | Có module descriptor do dự án khai báo? |
|---|---|---|
| Classpath | `--class-path` hoặc `-cp` | Không bắt buộc; classpath code thuộc unnamed module |
| Named module | `--module-path` hoặc `-p` | Có `module-info.java` trong module |
| Automatic module | JAR không có descriptor nhưng được đặt trên module path | Không có descriptor tường minh; tên module được suy ra hoặc khai báo trong manifest |

Với dự án mới cần ranh giới module rõ ràng, nên khai báo named module tường minh. Automatic module vẫn là cơ chế tương thích hữu ích khi tích hợp thư viện JAR chưa có module descriptor; không nên nhầm nó với một module có khai báo dependency và exports do dự án kiểm soát đầy đủ.

## 2. `module-info.java` là gì?

`module-info.java` là tệp nguồn đặc biệt chứa khai báo module. Nó nằm ở **root của source module**, không nằm bên trong package như các class thông thường.

Ví dụ cấu trúc:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/
        └── example/
            └── app/
                └── Main.java
```

Nội dung `module-info.java`:

```java
module com.example.app {
    requires java.sql;
}
```

Tên module ở đây là `com.example.app`. Nó là định danh module, không nhất thiết phải trùng tên thư mục, tên package hoặc tên file JAR, mặc dù quy ước reverse-domain thường được dùng để giảm nguy cơ trùng tên.

### 2.1. Cú pháp cơ bản

```java
module module.name {
    requires another.module;
    exports public.package;
    opens reflective.package;
}
```

Một module descriptor có thể chứa nhiều directive. Bài này tập trung vào `requires` và readability; `exports` và `opens` được nhắc đến để phân biệt quyền đọc module với quyền truy cập package.

### 2.2. Module name

Tên module thường theo dạng reverse-domain:

- `com.example.app`
- `org.acme.orders`
- `vn.company.billing`

Mỗi thành phần tên tuân theo quy tắc identifier của Java. Tránh dùng tên chung như `utils` hoặc `common` nếu module có thể được chia sẻ với hệ thống lớn.

Tên được ghi trong `requires` là **tên module**, không phải tên package:

```java
module com.example.app {
    requires java.sql; // Tên module
}
```

`java.sql` là tên module của API SQL trong JDK. Nó có package `java.sql`, nhưng tên module và tên package là hai khái niệm riêng dù đôi khi nhìn giống nhau.

### 2.3. Một named module có một descriptor

Một module nguồn có một khai báo module. `module-info.java` không phải class thông thường và không đặt trong package. Không khai báo nhiều module trong cùng một descriptor.

Các source file thuộc named module phải nằm trong package có tên; không sử dụng unnamed package trong named module.

## 3. Directive `requires`

`requires` khai báo module hiện tại cần **đọc** module khác:

```java
module com.example.app {
    requires java.sql;
    requires com.example.model;
}
```

Ở đây, module `com.example.app` đọc được các kiểu public thuộc package mà `java.sql` và `com.example.model` export.

Cú pháp thông thường:

```java
requires module.name;
```

Mỗi directive `requires` kết thúc bằng dấu chấm phẩy.

### 3.1. `requires` là dependency ở cấp module

Giả sử module `com.example.model` chứa:

```java
package com.example.model;

public record Customer(String id, String name) {}
```

Module descriptor của model:

```java
module com.example.model {
    exports com.example.model;
}
```

Module ứng dụng muốn dùng `Customer` cần khai báo:

```java
module com.example.app {
    requires com.example.model;
}
```

Sau đó có thể import kiểu đã được export:

```java
package com.example.app;

import com.example.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("C01", "An");
        System.out.println(customer.name());
    }
}
```

Nếu thiếu `requires com.example.model;`, module app không có readability edge tới model và không thể dùng kiểu từ module đó theo quy tắc module thông thường.

Nếu module model không export `com.example.model`, chỉ thêm `requires` vẫn chưa đủ để app truy cập kiểu `Customer`. Phần `exports` được giải thích ở mục 9.

### 3.2. `requires` có hiệu lực lúc biên dịch và chạy

Dependency thông thường được kiểm tra khi biên dịch và được module resolver sử dụng khi khởi chạy ứng dụng. Module được yêu cầu phải có thể quan sát và phân giải được trên module path hoặc trong runtime image.

Nếu module không được tìm thấy, bạn có thể gặp lỗi như:

```text
error: module not found: com.example.model
```

Khi chạy, nếu module bắt buộc không có trong module graph, quá trình khởi động có thể thất bại với lỗi phân giải module. Vì vậy, cần cấu hình module path đúng ở cả bước compile và run.

## 4. Quan hệ đọc module (readability)

Một module **reads** module khác khi module đó được phép tham chiếu tới các kiểu mà module kia cung cấp, tùy thêm điều kiện export package và accessibility.

Ví dụ:

```java
module com.example.app {
    requires com.example.model;
}
```

Quan hệ đọc:

```text
com.example.app  ──requires──>  com.example.model
      │                               │
      └──────── reads ────────────────┘
```

Có thể hiểu mũi tên `requires` là dependency được khai báo từ module sử dụng sang module được yêu cầu.

### 4.1. Readability không phải là kế thừa

`requires` không làm class trong module này kế thừa class trong module khác. Nó cũng không tự import package.

Sau khi có readability, code Java vẫn cần `import` nếu muốn dùng tên kiểu không đầy đủ:

```java
import com.example.model.Customer;
```

Hoặc có thể viết tên đầy đủ:

```java
com.example.model.Customer customer =
        new com.example.model.Customer("C01", "An");
```

`import` là cú pháp ở source file; `requires` là dependency ở module descriptor. Hai việc giải quyết hai lớp vấn đề khác nhau.

### 4.2. Readability có hướng

Nếu module A yêu cầu module B, A đọc B. Điều đó không tự tạo quan hệ ngược lại:

```text
A ──requires──> B

A reads B
B không tự động reads A
```

Nếu B cũng cần dùng kiểu public được A export, B phải khai báo dependency phù hợp. Không nên giả định dependency luôn hai chiều.

### 4.3. Readability có thể được truyền qua requires transitive

`requires transitive` tạo quan hệ đọc được truyền tới module phụ thuộc. Đây là điểm quan trọng khi một module công khai kiểu của dependency trong API của chính nó.

Phần tiếp theo giải thích chi tiết.

## 5. `requires transitive` — truyền readability cho module phụ thuộc

Cú pháp:

```java
module com.example.service {
    requires transitive com.example.model;
}
```

Directive này có hai ý nghĩa:

1. Module `com.example.service` đọc được `com.example.model`.
2. Module khác yêu cầu `com.example.service` cũng được đọc `com.example.model` thông qua quan hệ transitive.

Có thể hình dung:

```text
com.example.app
      |
      | requires
      v
com.example.service
      |
      | requires transitive
      v
com.example.model

Kết quả: app reads service và model.
```

### 5.1. Ví dụ ba module

Giả sử có ba module:

- `com.example.model`: chứa kiểu dữ liệu `Customer`.
- `com.example.service`: cung cấp dịch vụ làm việc với `Customer`.
- `com.example.app`: ứng dụng sử dụng service.

**Module model**

```java
module com.example.model {
    exports com.example.model;
}
```

File `Customer.java`:

```java
package com.example.model;

public record Customer(String id, String name) {}
```

**Module service**

```java
module com.example.service {
    requires transitive com.example.model;
    exports com.example.service;
}
```

File `CustomerService.java`:

```java
package com.example.service;

import com.example.model.Customer;

public class CustomerService {
    public Customer findCustomer(String id) {
        return new Customer(id, "An");
    }
}
```

API public của service dùng `Customer` trong kiểu trả về. Vì vậy service khai báo `requires transitive com.example.model` để module client đọc service cũng có thể đọc model.

**Module app**

```java
module com.example.app {
    requires com.example.service;
}
```

File `Main.java`:

```java
package com.example.app;

import com.example.model.Customer;
import com.example.service.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.findCustomer("C01");

        System.out.println(customer.name());
    }
}
```

App chỉ khai báo `requires com.example.service`, nhưng vẫn có thể dùng `Customer` vì service đã khai báo dependency tới model là transitive.

### 5.2. Nếu service dùng requires thông thường thì sao?

Nếu module service khai báo:

```java
module com.example.service {
    requires com.example.model;
    exports com.example.service;
}
```

thì service vẫn đọc được model và vẫn có thể dùng `Customer` trong implementation/API của nó. Nhưng module app chỉ `requires com.example.service` **không tự động đọc model**.

Nếu app cần tham chiếu `Customer`, app phải khai báo thêm:

```java
module com.example.app {
    requires com.example.service;
    requires com.example.model;
}
```

Vì vậy, khác biệt không nằm ở việc service có sử dụng model hay không; khác biệt là **dependency model có được truyền tới module client hay không**.

### 5.3. Khi nào nên dùng transitive?

Dùng `requires transitive` khi dependency là một phần trong API mà module muốn client có thể sử dụng trực tiếp.

Ví dụ:

- Module API trả về kiểu từ module model.
- Module facade công khai kiểu collection hoặc abstraction từ một dependency.
- Một module thư viện được thiết kế để re-export readability của dependency mà client cần để biên dịch.

Không dùng transitive chỉ vì implementation của module có gọi một thư viện. Nếu dependency chỉ được dùng nội bộ, `requires` thông thường giúp module graph gọn hơn và không buộc client biết về dependency đó.

**Quy tắc thiết kế:** dependency nào xuất hiện trong kiểu public của API có thể cần transitive; dependency chỉ nằm trong implementation thường chỉ cần requires bình thường. Cần xét hợp đồng API thực tế thay vì áp dụng máy móc.

## 6. `requires static` — dependency bắt buộc lúc compile, tùy chọn lúc runtime

Cú pháp:

```java
module com.example.app {
    requires static com.example.annotations;
}
```

`requires static` thể hiện dependency cần có khi biên dịch module, nhưng có thể không cần được phân giải ở runtime.

Nó hữu ích với dependency chỉ phục vụ biên dịch hoặc chỉ có mặt trong một số môi trường chạy, chẳng hạn annotation có retention phù hợp và không được dùng như dependency runtime bắt buộc.

### 6.1. Ví dụ với annotation compile-time

Giả sử module `com.example.annotations` chứa annotation:

```java
package com.example.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface GeneratedMarker {}
```

Descriptor:

```java
module com.example.annotations {
    exports com.example.annotations;
}
```

Module sử dụng:

```java
module com.example.app {
    requires static com.example.annotations;
}
```

Source:

```java
package com.example.app;

import com.example.annotations.GeneratedMarker;

@GeneratedMarker
public class GeneratedType {}
```

Module app cần module annotation trên module path lúc compile để compiler tìm được annotation type. Ở runtime, annotation có retention `CLASS` không được yêu cầu để ứng dụng đọc bằng reflection, nên dependency có thể không cần được phân giải.

### 6.2. `requires static` không có nghĩa “có thì dùng, không có thì mọi thứ vẫn chạy”

Nếu code thực tế cần load class từ module optional ở runtime, việc thiếu module có thể gây lỗi khi đường code đó được thực thi. `requires static` không tự tạo fallback và không thay thế cơ chế plugin hoặc kiểm tra khả năng có mặt của dependency.

Hãy dùng nó cho dependency thực sự tùy chọn ở runtime. Nếu ứng dụng luôn cần module đó để hoạt động, hãy dùng `requires` thông thường.

### 6.3. So sánh requires và requires static

| Directive | Khi biên dịch | Khi chạy | Mục đích |
|---|---|---|---|
| `requires M;` | Bắt buộc module M có thể được phân giải | M là dependency bắt buộc | Dependency cần thiết của module |
| `requires static M;` | M phải có để biên dịch | M không bắt buộc phải có trong runtime graph | Dependency compile-time hoặc runtime-optional |

Một module có thể kết hợp `static` với `transitive` nếu dependency vừa là tùy chọn ở runtime vừa cần truyền readability cho các module phụ thuộc trong các ngữ cảnh thích hợp:

```java
requires static transitive com.example.annotations;
```

Dùng dạng kết hợp này chỉ khi hợp đồng API thực sự yêu cầu.

## 7. `requires transitive` và `requires static transitive`

Hai modifier giải quyết hai khía cạnh khác nhau:

- `transitive`: truyền khả năng đọc dependency tới module yêu cầu module hiện tại.
- `static`: dependency cần ở compile time nhưng có thể vắng ở runtime.

Có thể dùng cả hai:

```java
module com.example.api {
    requires static transitive com.example.optional.annotations;
}
```

Đọc từng phần:

1. `com.example.api` cần module annotation khi biên dịch.
2. Các module phụ thuộc vào `com.example.api` có thể được truyền readability tới annotation module trong module graph tương ứng.
3. Dependency vẫn được đánh dấu optional ở runtime.

Đây là một khai báo chuyên biệt, không phải dạng mặc định. Hãy cân nhắc liệu module client có thật sự cần nhìn thấy dependency đó hay không.

## 8. `java.base` được đọc ngầm định

Mọi named module, ngoại trừ chính module `java.base`, đều có readability tới `java.base` theo quy tắc module system. Vì thế không cần viết:

```java
module com.example.app {
    requires java.base; // Không cần khai báo tường minh
}
```

Các kiểu nền tảng như `String`, `Object`, `List`, `System`, `RuntimeException` và nhiều API cơ bản thuộc `java.base`.

Ví dụ module descriptor có thể chỉ là:

```java
module com.example.app {
}
```

Code vẫn sử dụng được:

```java
package com.example.app;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình");
        System.out.println(names);
    }
}
```

Không cần `requires java.base`. Viết dependency này tường minh thường không cần thiết và có thể bị compiler cảnh báo là redundant.

Các module JDK khác như `java.sql`, `java.logging`, `java.net.http` không được tự động đọc chỉ vì chúng thuộc JDK; nếu dùng API từ chúng trong named module, hãy khai báo dependency phù hợp.

Ví dụ:

```java
module com.example.database {
    requires java.sql;
}
```

## 9. Readability khác với exports và opens

Đây là một phân biệt rất quan trọng khi học JPMS.

**`requires` tạo quan hệ đọc module. `exports` kiểm soát package nào được module khác truy cập. `opens` cho phép reflection sâu vào package theo phạm vi đã khai báo.**

### 9.1. Có requires nhưng không có exports

Module library:

```java
module com.example.internal {
    // Không export package com.example.internal.api
}
```

Nó có class public:

```java
package com.example.internal.api;

public class SecretService {
    public void execute() {}
}
```

Module client:

```java
module com.example.client {
    requires com.example.internal;
}
```

Dù client đọc được module `com.example.internal`, package `com.example.internal.api` không được export. Vì vậy client không thể truy cập `SecretService` như API công khai của module.

**Readability là điều kiện cần, không phải điều kiện đủ để truy cập mọi kiểu.**

### 9.2. Exports package

Module library:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Module client:

```java
module com.example.client {
    requires com.example.library;
}
```

Khi đó client có thể dùng các kiểu public trong `com.example.library.api`, với điều kiện các quy tắc truy cập Java khác cũng được thỏa mãn.

`exports` không làm tất cả package bên trong library công khai. Chỉ package được export mới được mở cho truy cập thông thường từ module khác.

### 9.3. Qualified exports

Có thể export package cho một số module cụ thể:

```java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.internal.spi to com.example.plugin;
}
```

Package `com.example.library.internal.spi` chỉ được export cho module `com.example.plugin` theo qualified export. Các module khác không tự động có quyền truy cập package này.

### 9.4. Opens phục vụ reflection

`opens` không giống `exports`. Nó cho phép framework hoặc thư viện reflection truy cập sâu vào thành viên của package ở runtime theo quy tắc module system:

```java
module com.example.domain {
    opens com.example.domain.model to com.example.mapper;
}
```

Điều này thường cần với framework ánh xạ object, dependency injection hoặc serialization dùng reflection sâu. Nếu chỉ muốn công khai API Java bình thường, dùng `exports`.

| Directive | Mục đích | Thời điểm/chức năng chính |
|---|---|---|
| `requires` | Module hiện tại đọc module khác | Readability |
| `requires transitive` | Truyền readability dependency tới client | Readability gián tiếp |
| `exports` | Công khai package cho module khác | Truy cập kiểu public |
| `opens` | Cho phép deep reflection vào package | Reflection runtime |

Đừng thêm `opens` chỉ để sửa lỗi import package; lỗi import thường cần kiểm tra `requires` và `exports`.

## 10. Module graph và cách đọc dependency

Khi khởi chạy ứng dụng modular, JVM xây dựng module graph từ các module gốc và dependency của chúng. Mỗi directive `requires` tạo một cạnh trong graph; modifier `transitive` ảnh hưởng cách readability được truyền.

Ví dụ:

```java
module com.example.app {
    requires com.example.service;
}

module com.example.service {
    requires transitive com.example.model;
}

module com.example.model {
    exports com.example.model;
}
```

Sơ đồ:

```text
             requires
com.example.app ───────────> com.example.service
                                  |
                                  | requires transitive
                                  v
                            com.example.model

Readability:
- app reads service (direct)
- service reads model (direct)
- app reads model (transitive)
```

Nếu service đổi thành `requires com.example.model` thông thường, app không tự đọc model. App phải khai báo thêm `requires com.example.model` nếu source của app tham chiếu tới kiểu trong module model.

### 10.1. Readability không phải “đọc tất cả dependency của dependency”

Không phải cứ module A yêu cầu B là A tự đọc mọi module mà B yêu cầu. Chỉ các dependency được truyền bằng `requires transitive` mới được truyền readability theo quy tắc này.

Ví dụ:

```text
app --requires--> service --requires--> model

app reads service
service reads model
app không tự động reads model
```

Nếu cạnh từ service tới model là `requires transitive`, app sẽ đọc model:

```text
app --requires--> service --requires transitive--> model

app reads service
app also reads model
```

Đây là lý do cần thiết kế transitive có chủ đích thay vì bật cho mọi dependency.

### 10.2. Không có dependency vòng

Module graph phải có thể phân giải mà không tạo chu trình `requires`. Ví dụ:

```java
// module A
module com.example.a {
    requires com.example.b;
}

// module B
module com.example.b {
    requires com.example.a;
}
```

Hai module phụ thuộc vòng nhau là cấu trúc không hợp lệ cho module graph. Khi gặp lỗi, hãy xem lại ranh giới trách nhiệm: tách API chung thành module thứ ba, hoặc đảo chiều phụ thuộc bằng interface/service abstraction.

Ví dụ hướng giải quyết:

```text
          com.example.a
                |
                v
          com.example.api
                ^
                |
          com.example.b
```

Cả A và B phụ thuộc vào API chung; API không phụ thuộc ngược lại vào A hoặc B.

## 11. Module path và module resolution

`module-info.java` chỉ mô tả dependency; compiler và JVM vẫn cần tìm module thực tế. Module path là nơi chứa module dạng exploded directory, modular JAR hoặc các module phù hợp khác.

### 11.1. Compile bằng module source path

Một cấu trúc dự án nhiều module có thể như sau:

```text
project/
└── src/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/Customer.java
    ├── com.example.service/
    │   ├── module-info.java
    │   └── com/example/service/CustomerService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

Biên dịch tất cả module:

```bash
javac --module-source-path src -d out \
  -m com.example.model,com.example.service,com.example.app
```

`--module-source-path` chỉ vị trí cây source chứa các module; `-d out` chỉ thư mục xuất class/module đã biên dịch; `-m` chọn các module cần biên dịch.

### 11.2. Chạy một module

```bash
java --module-path out \
  -m com.example.app/com.example.app.Main
```

Cú pháp `-m module/class` chọn module chính và main class. JVM phân giải các module mà app yêu cầu theo module graph.

Có thể viết gọn `--module-path` thành `-p` và `--module` thành `-m`.

### 11.3. Compile module dùng JAR dependency

Nếu module model đã được đóng gói thành JAR:

```bash
javac --module-path lib \
  -d out/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
```

Thư mục `lib` phải chứa JAR/module có tên khớp với directive `requires`. Tên module được xác định từ descriptor hoặc quy tắc automatic module, không đơn giản chỉ là tên file JAR.

### 11.4. Module path khác classpath

| Tham số | Vai trò |
|---|---|
| `--class-path` / `-cp` | Tìm class và tài nguyên trên classpath |
| `--module-path` / `-p` | Tìm module để module resolver xây dựng module graph |
| `--module` / `-m` | Chọn module và main class để chạy |
| `--module-source-path` | Tìm source của nhiều module khi biên dịch |

Đặt một JAR trên classpath không tương đương với đặt nó trên module path. Nếu muốn kiểm soát dependency bằng `requires`, cần hiểu module đó đang được phân giải theo mô hình nào.

## 12. Kiểm tra module descriptor và module graph

JDK 17 có các công cụ dòng lệnh hữu ích.

### 12.1. javac báo lỗi module not found

Nếu gặp:

```text
error: module not found: com.example.model
```

Hãy kiểm tra:

- Module có trong module source path hoặc module path không?
- Tên module trong `module-info.java` có đúng không?
- Module có được chọn/đưa vào quá trình compile không?
- Đang dùng `--module-path` hay chỉ có `--class-path`?
- JAR có module descriptor hoặc automatic module name đúng như dependency yêu cầu không?

### 12.2. Hiển thị module trong JDK

Lệnh:

```bash
java --list-modules
```

liệt kê các module quan sát được trong runtime image/module path theo cấu hình chạy.

Để mô tả một module:

```bash
java --describe-module java.sql
```

Có thể dùng lệnh tương tự với module ứng dụng khi module nằm trên module path:

```bash
java --module-path out --describe-module com.example.app
```

Output cho biết module có những directive và package liên quan nào, hữu ích khi kiểm tra tên module hoặc exports/requires.

### 12.3. Đọc descriptor trong JAR

Lệnh `jar --describe-module` giúp xem descriptor của JAR:

```bash
jar --describe-module --file lib/example.jar
```

Nếu JAR là automatic module, output có thể chỉ rõ tên automatic module. Đây là cách kiểm tra hữu ích khi tích hợp thư viện ngoài.

## 13. Những lỗi thường gặp với requires và readability

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `module not found` | Module không có trên module path hoặc sai tên | Kiểm tra module path và tên trong descriptor |
| `package ... is not visible` | Chưa đọc module hoặc package chưa được export | Kiểm tra `requires` và `exports` |
| Client không dùng được kiểu trong dependency của service | Service dùng `requires` thường, không truyền readability | Client thêm requires trực tiếp hoặc service dùng transitive nếu đúng hợp đồng API |
| Nghĩ requires làm package public | Nhầm readability với export | Module cung cấp phải export package cần dùng |
| Runtime thiếu module | Dependency bắt buộc không được phân giải | Đưa module lên module path/runtime image |
| Module graph có chu trình | Hai hay nhiều module requires vòng nhau | Tách API chung hoặc điều chỉnh hướng phụ thuộc |
| Classpath chạy nhưng module path lỗi | Hai chế độ nạp và encapsulation khác nhau | Kiểm tra descriptor, exports, requires và module path |

### 13.1. Lỗi thiếu requires

Module descriptor:

```java
module com.example.app {
    // Thiếu requires com.example.model;
}
```

Source:

```java
import com.example.model.Customer;
```

Nếu `Customer` thuộc named module `com.example.model`, module app cần khai báo dependency tới module đó hoặc nhận readability qua một đường transitive hợp lệ.

### 13.2. Lỗi package không được export

Module descriptor của library:

```java
module com.example.library {
    // Không export com.example.library.api
}
```

Client đã có:

```java
module com.example.client {
    requires com.example.library;
}
```

Client vẫn không thể import kiểu trong package chưa export. Sửa module cung cấp bằng:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Nếu package chỉ dành cho implementation nội bộ, không nên export chỉ để làm compiler hết báo lỗi; hãy xác định API công khai đúng của module.

### 13.3. Lỗi dùng requires transitive quá rộng

Nếu module service chỉ dùng module model bên trong implementation, khai báo transitive khiến mọi client của service phải nhìn thấy thêm dependency model. Điều này làm tăng coupling và khiến module graph của ứng dụng lớn hơn.

Chỉ truyền readability khi dependency là một phần của hợp đồng API hoặc có lý do thiết kế rõ ràng.

## 14. Quan hệ đọc và strong encapsulation

JPMS được thiết kế để tăng tính đóng gói. Trước module system, classpath thường cho phép nhiều package cùng được nhìn thấy trong một không gian rộng; module system đưa thêm ranh giới rõ ràng giữa các module.

Strong encapsulation dựa trên các cơ chế:

1. Module khai báo package nào được export.
2. Module client khai báo dependency bằng `requires`.
3. Package không export không trở thành API thông thường của module khác.
4. Reflection sâu chịu quy tắc `opens` và quyền truy cập tương ứng.

Ví dụ:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Các package `com.example.library.internal` và `com.example.library.impl` vẫn có thể tồn tại trong module nhưng không được export. Client không nên phụ thuộc vào implementation detail của chúng.

### 14.1. Public class chưa chắc là API công khai giữa các module

```java
package com.example.library.internal;

public class InternalCache {}
```

Modifier `public` chỉ giải quyết mức truy cập của Java language. Nếu package không được export, module khác không thể dùng class đó như API thông thường.

### 14.2. Requires không mở encapsulation

```java
module com.example.client {
    requires com.example.library;
}
```

Khai báo này không có nghĩa client được phép truy cập mọi package trong library. Nó chỉ thiết lập readability. Package nào có thể được sử dụng còn phụ thuộc exports và accessibility của kiểu/member.

### 14.3. Không dựa vào JDK internal API

Trong ứng dụng mới, chỉ dùng API công khai được Java SE/JDK tài liệu hóa. Module system tăng cường encapsulation đối với implementation nội bộ của JDK; dựa vào package nội bộ như `sun.*` hoặc `com.sun.*` làm ứng dụng dễ hỏng khi nâng cấp.

Không thiết kế dependency bằng cách mở rộng quyền truy cập tới implementation detail của JDK nếu đã có API công khai thay thế.

## 15. Cách thiết kế requires trong ứng dụng nhiều module

Một module graph dễ bảo trì thường có dependency đi theo một hướng rõ ràng.

Ví dụ phân lớp:

```text
             com.example.app
                    |
                    v
            com.example.service
                    |
                    v
             com.example.model

             com.example.api
             (nếu cần tách contract)
```

Một số nguyên tắc:

- Module ứng dụng ở tầng trên có thể phụ thuộc service.
- Service có thể phụ thuộc model hoặc API.
- Module model nên ít phụ thuộc vào tầng ứng dụng.
- Tránh dependency vòng.
- Dùng `requires transitive` khi dependency thực sự xuất hiện trong public API và client cần đọc nó.
- Giữ dependency implementation ở dạng `requires` thường.
- Không đưa mọi module JDK vào descriptor “cho chắc”; chỉ khai báo module mà code hoặc module descriptor thực sự cần.

### 15.1. Một module có thể requires nhiều module

```java
module com.example.reporting {
    requires java.sql;
    requires java.logging;
    requires com.example.model;
    requires com.example.service;
}
```

Mỗi directive là một dependency riêng. Tên module cần tồn tại trong module graph.

### 15.2. Không requires package

Sai:

```java
module com.example.app {
    // Sai: đây là tên package, không phải module name.
    // requires com.example.model.api;
}
```

Đúng nếu `com.example.model` là tên module:

```java
module com.example.app {
    requires com.example.model;
}
```

Package `com.example.model.api` có thể được module `com.example.model` export. `requires` luôn trỏ tới module.

### 15.3. Không requires JAR file name

Nếu file là `customer-model-1.0.jar`, không tự viết:

```java
requires customer-model-1.0;
```

trừ khi đó thực sự là tên module được descriptor hoặc quy tắc automatic module xác định. Hãy kiểm tra bằng `jar --describe-module` hoặc `java --describe-module`.

## 16. Ví dụ hoàn chỉnh ba module chạy bằng JDK 17

Cấu trúc:

```text
src/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/Customer.java
├── com.example.service/
│   ├── module-info.java
│   └── com/example/service/CustomerService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

**1. Module model**

```java
// src/com.example.model/module-info.java
module com.example.model {
    exports com.example.model;
}
```

```java
// src/com.example.model/com/example/model/Customer.java
package com.example.model;

public record Customer(String id, String name) {}
```

**2. Module service**

```java
// src/com.example.service/module-info.java
module com.example.service {
    requires transitive com.example.model;
    exports com.example.service;
}
```

```java
// src/com.example.service/com/example/service/CustomerService.java
package com.example.service;

import com.example.model.Customer;

public class CustomerService {
    public Customer find(String id) {
        return new Customer(id, "An");
    }
}
```

**3. Module app**

```java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.service;
}
```

```java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.model.Customer;
import com.example.service.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.find("C01");

        System.out.println(customer.id() + ": " + customer.name());
    }
}
```

Biên dịch từ thư mục dự án:

```bash
javac --module-source-path src -d out \
  -m com.example.model,com.example.service,com.example.app
```

Chạy:

```bash
java --module-path out \
  -m com.example.app/com.example.app.Main
```

Kết quả:

```text
C01: An
```

Tại sao app dùng được `Customer` dù app chỉ requires service?

- Service trực tiếp requires model.
- Service khai báo dependency đó là transitive.
- App requires service nên readability tới model được truyền sang app.
- Model export package `com.example.model` nên app truy cập được kiểu `Customer`.

Nếu đổi `requires transitive com.example.model` thành `requires com.example.model`, app cần khai báo thêm `requires com.example.model` để dùng trực tiếp `Customer`.

## 17. Bài tập tự luyện

### Bài 1 — Đọc module descriptor

Cho:

```java
module com.example.order {
    requires java.sql;
    requires com.example.customer;
}
```

**Câu hỏi:** Module `com.example.order` đọc những module nào được khai báo trực tiếp?

**Đáp án:** `java.sql` và `com.example.customer`. Module này cũng có readability ngầm định tới `java.base`.

### Bài 2 — Requires có mở package không?

Module A:

```java
module com.example.a {
    exports com.example.a.api;
}
```

Module B:

```java
module com.example.b {
    requires com.example.a;
}
```

**Câu hỏi:** B có truy cập mọi package trong A không?

**Đáp án:** Không. B đọc module A nhưng chỉ package được export mới có thể được truy cập theo quy tắc module. Package không export vẫn được đóng với module khác.

### Bài 3 — Requires transitive

A requires B; B requires transitive C. A có đọc C không?

**Đáp án:** Có. Dependency transitive của B truyền readability tới A.

### Bài 4 — Requires thông thường

A requires B; B requires C (không transitive). A có tự đọc C không?

**Đáp án:** Không. A đọc B; B đọc C. Readability không tự truyền qua dependency thông thường.

### Bài 5 — Chọn requires hay requires transitive

Một module service dùng model trong implementation nhưng không để lộ kiểu model trong public API. Nên chọn gì?

**Đáp án:** `requires` thông thường. Không cần buộc client đọc model nếu client không cần tham chiếu nó.

### Bài 6 — Dependency compile-time optional

Một module dùng annotation chỉ cần cho compiler, annotation có retention `CLASS` và không được ứng dụng đọc bằng reflection ở runtime. Có thể cân nhắc directive nào?

**Đáp án:** `requires static`. Module annotation phải có lúc compile; dependency có thể không cần trong runtime graph. Nếu code thực tế cần class đó khi chạy, phải thiết kế dependency runtime rõ ràng.

### Bài 7 — Vì sao không requires java.base?

**Đáp án:** Mọi named module khác `java.base` đều đọc `java.base` ngầm định. Không cần ghi directive tường minh.

### Bài 8 — Phân biệt package và module name

Module `com.example.library` export package `com.example.library.api`. Module client cần viết requires nào?

**Đáp án:** `requires com.example.library;`. Không viết tên package trong directive.

## 18. Ghi nhớ

- `module-info.java` là module descriptor ở root của source module.
- `requires M;` khai báo dependency trực tiếp và khiến module hiện tại đọc M.
- Readability có hướng; A requires B không làm B tự động đọc A.
- `requires transitive M;` truyền readability tới các module yêu cầu module hiện tại.
- `requires static M;` yêu cầu dependency lúc compile nhưng cho phép nó vắng ở runtime.
- `java.base` được mọi named module khác đọc ngầm định.
- `requires` trỏ tới **module name**, không phải package name hoặc tên file JAR.
- Readability không đồng nghĩa package access: module cung cấp phải `exports` package cần dùng.
- `opens` phục vụ deep reflection, khác với `exports`.
- Module graph không được có chu trình requires.
- Dùng module path để biên dịch/chạy named modules; classpath và module path có quy tắc nạp khác nhau.
- Dùng `requires transitive` có chủ đích khi dependency là một phần hợp đồng API; dependency nội bộ thường chỉ cần `requires`.

## Tài liệu tham khảo chính thức cho Java 17

- [Java Language Specification 17 — `7.7`: Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7).
- [Java Language Specification 17 — `7.7.1`: Dependencies](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.1).
- [Java Language Specification 17 — `7.7.2`: Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2).
- [Java SE 17 API — `java.lang.module.ModuleDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html).
- [Java SE 17 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).
- [Oracle Java 17 — The Java Module System](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).

