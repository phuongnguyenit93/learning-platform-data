# Module giúp đóng gói, phụ thuộc và ẩn package như thế nào

Java Platform Module System (JPMS), được giới thiệu từ Java 9, bổ sung một ranh giới tổ chức ở cấp **module**. Một module gom các package có liên quan, khai báo module nào nó cần và chỉ định package nào được công khai cho module khác. Nhờ đó, ứng dụng có thể mô tả phụ thuộc rõ ràng và giữ các package triển khai ở bên trong.

Ba ý chính cần nối với nhau là: **đóng gói** xác định phần code thuộc về module nào; **phụ thuộc** xác định module nào được phép đọc và sử dụng module khác; **ẩn package** xác định phần nào của module trở thành API bên ngoài và phần nào chỉ dùng nội bộ.

## 1. Vì sao Java cần ranh giới module?

Một ứng dụng Java thường có nhiều package. Package giúp nhóm class và interface theo chức năng, đồng thời hỗ trợ kiểm soát truy cập bằng các modifier như `public`, `protected`, package-private và `private`.

Tuy nhiên, package riêng lẻ chưa diễn tả đầy đủ cấu trúc phụ thuộc của toàn ứng dụng. Khi chỉ dùng classpath, thư viện có thể được tìm thấy mà không có một khai báo module rõ ràng cho biết thành phần nào phụ thuộc vào thành phần nào. Các kiểu `public` trong package công khai cũng có thể trở thành bề mặt sử dụng rộng hơn dự kiến.

JPMS đưa ra cấp tổ chức cao hơn:

- **Package** nhóm các kiểu Java có liên quan.
- **Module** nhóm một hoặc nhiều package và có một tên module.
- **Module descriptor** khai báo tên module, phụ thuộc và các package được xuất ra ngoài.
- **Module path** là nơi Java tìm các module khi biên dịch hoặc chạy ứng dụng modular.

Một module được đặt tên thường có file `module-info.java` ở gốc mã nguồn module. Khi biên dịch, file này trở thành `module-info.class` trong module đã biên dịch; khi đóng gói thành modular JAR, descriptor được đặt ở gốc JAR.

Module không thay thế package. Package vẫn tổ chức class bên trong module; module tạo ranh giới phụ thuộc và khả năng truy cập giữa các nhóm package.

## 2. Module descriptor mô tả ranh giới

Ví dụ một module tên `com.acme.model`:

```java
module com.acme.model {
    exports com.acme.model.api;
}
```

Đoạn khai báo này có nghĩa:

- Tên module là `com.acme.model`.
- Module có thể chứa nhiều package.
- Package `com.acme.model.api` được xuất để module khác có thể sử dụng các kiểu công khai trong package đó.
- Những package khác của module không tự động trở thành API bên ngoài.

Tên module thường dùng dạng tên đảo ngược theo miền để giảm xung đột tên, chẳng hạn `com.acme.model`. Đây là quy ước đặt tên, không có nghĩa tên module bắt buộc phải trùng với tên package.

Module có thể khai báo nhiều package bằng nhiều chỉ thị `exports`. Nếu không khai báo `exports` cho package nào, các package đó không được module khác truy cập theo cách thông thường ở thời điểm biên dịch.

Mọi module đều đọc được module nền tảng `java.base` một cách ngầm định. Vì vậy, descriptor không cần viết `requires java.base;` trong các ví dụ thông thường.

## 3. Đóng gói: gom những gì thuộc cùng một module

Giả sử hệ thống quản lý khách hàng có ba phần:

- `com.acme.model`: mô hình dữ liệu khách hàng.
- `com.acme.service`: nghiệp vụ tra cứu khách hàng.
- `com.acme.app`: chương trình khởi chạy và giao diện dòng lệnh.

Cấu trúc mã nguồn có thể như sau:

```text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/api/
│       └── Customer.java
├── com.acme.service/
│   ├── module-info.java
│   ├── com/acme/service/api/
│   │   └── CustomerService.java
│   └── com/acme/service/internal/
│       └── CustomerRepository.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/
        └── Main.java
```

Mỗi thư mục con trực tiếp của `src` là một module nguồn. Bên trong module, các thư mục tiếp tục biểu diễn cấu trúc package.

Module `com.acme.service` chứa cả `api` và `internal`. Hai package thuộc cùng module nên code trong module có thể phối hợp sử dụng chúng theo quy tắc truy cập Java. Chỉ package `api` được xuất; package `internal` là chi tiết triển khai.

Đóng gói theo module giúp người đọc nhận ra phần nào thuộc cùng một thành phần, đồng thời cho phép build và phân phối thành phần đó như một module riêng. Một modular JAR có thể chứa các package của module cùng descriptor của nó.

## 4. Khai báo phụ thuộc bằng `requires`

Một module chỉ có thể sử dụng các module mà nó đọc được. Chỉ thị `requires` khai báo một phụ thuộc trực tiếp:

```java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
```

Ở đây, `com.acme.service` cần `com.acme.model`. Khi biên dịch và chạy, Java phải tìm được module được yêu cầu trong module graph. Nếu một phụ thuộc bắt buộc không thể được tìm thấy hoặc module không thể được phân giải, ứng dụng không thể khởi động theo cấu hình đó.

Cần phân biệt hai khái niệm:

- `import` trong file Java giúp viết tên kiểu ngắn hơn, ví dụ `import com.acme.model.api.Customer;`.
- `requires` trong `module-info.java` khai báo quan hệ phụ thuộc và khả năng đọc giữa các module.

Một lệnh `import` không tự tạo phụ thuộc module. Muốn sử dụng kiểu từ module khác, module hiện tại phải có khả năng đọc module chứa kiểu đó và package chứa kiểu phải được xuất phù hợp.

### `requires transitive`

Nếu kiểu của module A xuất hiện trong API công khai của module B, module C sử dụng B có thể cần đọc A để làm việc với API đó. Khi ấy B có thể khai báo:

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

`requires transitive` có nghĩa module đọc `com.acme.service` cũng được truyền khả năng đọc tới `com.acme.model`. Chỉ dùng nó khi phụ thuộc đó thực sự là một phần của API mà module muốn cung cấp cho người dùng.

Một số chỉ thị liên quan:

| Chỉ thị | Ý nghĩa |
|---|---|
| `requires module.name;` | Khai báo phụ thuộc bắt buộc trực tiếp |
| `requires transitive module.name;` | Khai báo phụ thuộc và truyền khả năng đọc tới module phụ thuộc cho các module đọc module hiện tại |
| `requires static module.name;` | Phụ thuộc cần có khi biên dịch nhưng có thể không cần hiện diện lúc chạy |

Không nên thêm `transitive` cho mọi phụ thuộc. Nếu một thư viện chỉ được dùng bên trong phần triển khai và không xuất hiện trong API công khai, `requires` thông thường thường thể hiện ý định rõ hơn.

## 5. Ẩn package bằng `exports`

Điểm quan trọng của JPMS là package không tự động công khai chỉ vì bên trong có class `public`.

Ví dụ module `com.acme.service` chỉ xuất package API:

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

Module có thể chứa hai package:

```text
com.acme.service.api
    CustomerService.java

com.acme.service.internal
    CustomerRepository.java
```

Các kiểu `public` trong `com.acme.service.api` có thể được module khác sử dụng vì package này được xuất. Các kiểu trong `com.acme.service.internal` vẫn nằm bên trong ranh giới module, dù một class trong đó được khai báo `public`.

Ví dụ:

```java
package com.acme.service.internal;

public class CustomerRepository {
    // Chi tiết truy cập dữ liệu nội bộ của service.
}
```

Một module bên ngoài không thể chỉ vì thấy class có modifier `public` mà import và sử dụng `CustomerRepository`. Package chứa class chưa được xuất khỏi module.

Cần nhớ ba tầng kiểm soát khác nhau:

1. **Module export:** module khác có được phép truy cập package hay không.
2. **Package và class access:** trong package đã được xuất, các modifier Java vẫn quyết định kiểu và thành viên nào truy cập được.
3. **Object access:** `private`, `protected` và các quy tắc truy cập thành viên vẫn có hiệu lực như bình thường.

Vì vậy, `exports` không biến mọi thành viên thành `public`; nó mở package ở ranh giới module, sau đó các quy tắc truy cập Java tiếp tục được áp dụng.

Có thể xuất package cho một module cụ thể bằng qualified export:

```java
exports com.acme.service.internal to com.acme.test;
```

Khi đó package được xuất có giới hạn cho module `com.acme.test`, thay vì công khai cho mọi module đọc được module hiện tại. Cách này hữu ích khi cần cho một module tích hợp hoặc kiểm thử truy cập một API đặc biệt.

## 6. `opens`: cho phép reflection truy cập sâu

`exports` phục vụ khả năng truy cập API ở mức biên dịch và sử dụng kiểu thông thường. Một số framework lại cần reflection để kiểm tra hoặc truy cập thành viên không công khai, chẳng hạn framework ánh xạ object, dependency injection hoặc thư viện tuần tự hóa.

Đối với trường hợp đó, JPMS có `opens`:

```java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal to com.acme.mapper;
}
```

Chỉ thị `opens` cho phép module `com.acme.mapper` truy cập sâu bằng reflection vào package `com.acme.model.internal`, trong phạm vi các quy tắc reflection và quyền truy cập của Java.

Hai chỉ thị có mục đích khác nhau:

| Chỉ thị | Mục đích | Dùng khi |
|---|---|---|
| `exports` | Cho module khác sử dụng kiểu công khai trong package | Package là API mà module muốn cung cấp |
| `opens` | Cho phép truy cập sâu bằng reflection ở runtime | Framework cần đọc hoặc truy cập thành viên qua reflection |

Có thể dùng `opens package.name;` để mở package cho reflection từ các module khác. Nếu viết `opens package.name to framework.module;`, quyền mở được giới hạn cho module được nêu.

Cú pháp `open module` mở tất cả package của module cho deep reflection:

```java
open module com.acme.legacy {
    requires com.acme.model;
}
```

`open module` không đồng nghĩa với việc xuất tất cả package như `exports`. Nó phục vụ reflection; module khác vẫn không có API package công khai để import các kiểu nội bộ theo cách thông thường.

Hãy mở đúng package và đúng module cần thiết. Mở toàn bộ module có thể làm giảm lợi ích đóng gói mà JPMS mang lại.

## 7. Ví dụ hoàn chỉnh với ba module

Các file dưới đây kết hợp phụ thuộc, API công khai và package nội bộ.

**Module `com.acme.model`:**

`src/com.acme.model/module-info.java`

```java
module com.acme.model {
    exports com.acme.model.api;
}
```

`src/com.acme.model/com/acme/model/api/Customer.java`

```java
package com.acme.model.api;

public record Customer(String id, String name) {}
```

Module model chỉ xuất package `com.acme.model.api`.

**Module `com.acme.service`:**

`src/com.acme.service/module-info.java`

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

`src/com.acme.service/com/acme/service/internal/CustomerRepository.java`

```java
package com.acme.service.internal;

import com.acme.model.api.Customer;

public class CustomerRepository {
    public Customer findById(String id) {
        return new Customer(id, "An");
    }
}
```

`src/com.acme.service/com/acme/service/api/CustomerService.java`

```java
package com.acme.service.api;

import com.acme.model.api.Customer;
import com.acme.service.internal.CustomerRepository;

public class CustomerService {
    private final CustomerRepository repository =
            new CustomerRepository();

    public Customer find(String id) {
        return repository.findById(id);
    }
}
```

Service cần model để tạo và trả về `Customer`. Vì `Customer` xuất hiện trong kiểu trả về của API `CustomerService.find`, descriptor dùng `requires transitive` để module sử dụng service có thể đọc model qua service.

Package `com.acme.service.internal` không được xuất. `CustomerService` trong cùng module vẫn có thể sử dụng `CustomerRepository`, còn module bên ngoài không thể import trực tiếp repository.

**Module `com.acme.app`:**

`src/com.acme.app/module-info.java`

```java
module com.acme.app {
    requires com.acme.service;
}
```

`src/com.acme.app/com/acme/app/Main.java`

```java
package com.acme.app;

import com.acme.model.api.Customer;
import com.acme.service.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        Customer customer = new CustomerService().find("C01");
        System.out.println(customer.id() + " - " + customer.name());
    }
}
```

App chỉ khai báo phụ thuộc trực tiếp vào service. Nhờ `requires transitive` trong service, app có thể đọc kiểu `Customer` từ model. Nếu service chỉ khai báo `requires com.acme.model;`, app muốn sử dụng trực tiếp kiểu `Customer` sẽ phải khai báo thêm `requires com.acme.model;`.

Biên dịch cả ba module từ thư mục chứa `src`:

```bash
javac --module-source-path src -d out \
  -m com.acme.model,com.acme.service,com.acme.app
```

Chạy ứng dụng:

```bash
java --module-path out \
  -m com.acme.app/com.acme.app.Main
```

Kết quả:

```text
C01 - An
```

Ví dụ cho thấy module app gọi API của service, service dùng package nội bộ của chính nó và model cung cấp kiểu dữ liệu được xuất công khai. Các quan hệ này được mô tả bằng descriptor thay vì phụ thuộc hoàn toàn vào quy ước của nhóm phát triển.

## 8. Điều gì xảy ra khi module vi phạm ranh giới?

Nếu app cố import:

```java
import com.acme.service.internal.CustomerRepository;
```

trong khi `com.acme.service` không xuất package `com.acme.service.internal`, thao tác sử dụng kiểu này từ module app sẽ bị từ chối khi biên dịch hoặc khi phân giải quyền truy cập module. Việc class `CustomerRepository` được khai báo `public` không vượt qua được ranh giới module.

Nếu module app không khai báo khả năng đọc module chứa một kiểu cần dùng, compiler cũng sẽ không coi kiểu đó là API sẵn có của app. Tương tự, nếu module khai báo một phụ thuộc bắt buộc nhưng module đó không có trên module path, quá trình phân giải module sẽ thất bại.

Một package cũng không nên được chia sẻ đồng thời giữa nhiều named module trong cùng module graph. Hãy để một module sở hữu package và xuất API cần thiết cho các module khác. Điều này giúp tránh split package và làm rõ nơi chịu trách nhiệm cho từng namespace.

Module system hỗ trợ đóng gói và kiểm soát truy cập ở cấp kiến trúc. Nó không phải sandbox bảo mật để chạy mã không đáng tin cậy; không nên coi ranh giới module là cơ chế cô lập an toàn thay cho các biện pháp bảo mật của ứng dụng và môi trường chạy.

## 9. Cách chọn `requires`, `exports` và `opens`

Khi thiết kế một module, có thể lần lượt tự hỏi:

1. **Module này cần dùng module nào?** Khai báo `requires` cho phụ thuộc trực tiếp.
2. **Kiểu của phụ thuộc có xuất hiện trong API công khai không?** Nếu người dùng API cần đọc module phụ thuộc thông qua module hiện tại, cân nhắc `requires transitive`.
3. **Package nào là API cho module khác?** Chỉ xuất những package cần công khai bằng `exports`.
4. **Framework có cần reflection sâu vào package nào không?** Chỉ mở package cần thiết bằng `opens`, và giới hạn module nhận quyền nếu có thể.
5. **Package nào chỉ phục vụ triển khai?** Giữ chúng không được xuất để module khác không phụ thuộc trực tiếp vào chi tiết nội bộ.

Một thiết kế tốt thường có ít package được xuất, phụ thuộc rõ ràng và các package triển khai được giữ trong module sở hữu chúng. Khi cần thay đổi nội bộ, module có thể thay đổi cách cài đặt mà ít ảnh hưởng đến module tiêu thụ API.

## Ghi nhớ

- **Đóng gói:** module gom các package thuộc cùng một thành phần và có descriptor riêng.
- **Phụ thuộc:** `requires` khai báo module cần đọc; `requires transitive` truyền khả năng đọc cho người dùng module hiện tại.
- **Ẩn package:** chỉ package được `exports` mới trở thành API thông thường cho module khác; package không xuất vẫn dùng được bên trong module.
- **Reflection:** `opens` cho phép truy cập sâu ở runtime, có thể giới hạn cho module cụ thể.
- **Phân quyền nhiều lớp:** module export, modifier của Java và quyền truy cập thành viên cùng phối hợp tạo nên ranh giới thực tế.

Khi nhìn vào `module-info.java`, hãy đọc nó như bản đồ kiến trúc của module: module cần gì, công khai package nào và cho phép framework truy cập sâu vào đâu. Đó là cách JPMS giúp hệ thống Java có phụ thuộc minh bạch, API gọn và phần triển khai được đóng kín hơn.