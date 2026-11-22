# Compile error do requires hoặc exports thiếu

## 1. Hai ranh giới cần phân biệt trong JPMS

Khi biên dịch một ứng dụng modular, Java kiểm tra cả **module readability** và **package accessibility**. Hai cơ chế này liên quan nhưng giải quyết hai câu hỏi khác nhau:

- `requires` xác định module nào được module hiện tại đọc. Nếu module A cần sử dụng kiểu nằm trong module B, A thường phải khai báo `requires B`.
- `exports` xác định package nào của một module được module khác truy cập. Dù A đã đọc B, A vẫn không thể sử dụng một package của B nếu package đó không được export cho A.

Vì vậy, một dependency có thể đã nằm trên module path nhưng source vẫn không biên dịch được vì thiếu `requires`, hoặc module đã được đọc nhưng package chứa kiểu cần dùng chưa được export.

Ví dụ:

```text
com.acme.app  --requires-->  com.acme.api
                                  |
                                  +-- exports com.acme.api
```

Muốn sử dụng public type `com.acme.api.Customer`, consumer cần đọc module `com.acme.api` và package `com.acme.api` phải được export.

## 2. Ví dụ module API và consumer

Cấu trúc source:

```text
src/
├── com.acme.api/
│   ├── module-info.java
│   └── com/acme/api/Customer.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Module API:

```java
module com.acme.api {
    exports com.acme.api;
}
```

Class trong package được export:

```java
package com.acme.api;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

Module consumer:

```java
module com.acme.app {
    requires com.acme.api;
}
```

Consumer sử dụng API:

```java
package com.acme.app;

import com.acme.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Ada");
        System.out.println(customer.name());
    }
}
```

Ở đây hai điều kiện đã được đáp ứng:

1. `com.acme.app` đọc `com.acme.api` thông qua `requires`.
2. `com.acme.api` công khai package `com.acme.api` thông qua `exports`.

## 3. Lỗi thiếu requires: module không đọc dependency

Giả sử module descriptor của consumer bị bỏ directive:

```java
module com.acme.app {
    // Missing: requires com.acme.api;
}
```

Dù `com.acme.api` có trên module path và đã export package, consumer vẫn không đọc module đó. Khi biên dịch dòng:

```java
import com.acme.api.Customer;
```

Compiler có thể báo:

```text
package com.acme.api is not visible
(package com.acme.api is declared in module com.acme.api,
but module com.acme.app does not read it)
```

Cách sửa là thêm dependency vào `module-info.java` của consumer:

```java
module com.acme.app {
    requires com.acme.api;
}
```

Đừng sửa module API để export thêm package khi thông báo lỗi nói rõ consumer không đọc module. Đây là lỗi về readability, được điều khiển từ phía module cần sử dụng dependency.

### Phân biệt lỗi module not found

Nếu consumer đã có:

```java
requires com.acme.api;
```

nhưng compiler báo:

```text
module not found: com.acme.api
```

thì module descriptor đã yêu cầu dependency, nhưng compiler không tìm thấy module tương ứng. Hãy kiểm tra:

- JAR hoặc thư mục module có thực sự tồn tại không.
- Module path có trỏ tới đúng thư mục chứa module không.
- Tên module trong `requires` có khớp với tên khai báo trong `module-info.java` hoặc tên module được suy ra từ JAR không.
- Dependency có bị đặt nhầm trên classpath thay vì module path không.

Ví dụ biên dịch khi API đã được đóng gói trong thư mục `mods`:

```bash
javac --module-path mods \
  --module-source-path src \
  -d out \
  -m com.acme.app
```

## 4. Lỗi thiếu exports: module đã được đọc nhưng package bị đóng

Giả sử API module có descriptor:

```java
module com.acme.api {
    // Missing: exports com.acme.api;
}
```

Consumer vẫn khai báo đúng:

```java
module com.acme.app {
    requires com.acme.api;
}
```

Nhưng khi import `com.acme.api.Customer`, compiler có thể báo package được khai báo trong module `com.acme.api` nhưng module này không export package đó.

Cách sửa là export đúng package trong module sở hữu API:

```java
module com.acme.api {
    exports com.acme.api;
}
```

`exports` là directive của module chứa package. Consumer không thể tự export package thuộc module khác bằng cách thêm một dòng vào module descriptor của mình.

Cũng cần nhớ rằng export package không đồng nghĩa mọi thành viên đều công khai. Consumer vẫn chỉ truy cập được các type và member theo quy tắc truy cập Java thông thường; thành viên package-private vẫn không trở thành public.

## 5. Qualified exports: chỉ export cho một số module

Một module có thể giới hạn package chỉ cho một số consumer cụ thể:

```java
module com.acme.api {
    exports com.acme.api to com.acme.app;
}
```

Đây là **qualified export**. Package `com.acme.api` chỉ được export cho module `com.acme.app` được nêu tên. Module khác có thể đọc `com.acme.api` nhưng vẫn không truy cập được package đó.

Nếu consumer mới là `com.acme.report`, cần cân nhắc thêm module này vào danh sách:

```java
module com.acme.api {
    exports com.acme.api to
        com.acme.app,
        com.acme.report;
}
```

Chỉ nên dùng qualified exports khi thực sự muốn giới hạn tập consumer. Nếu package là API công khai cho mọi module, dùng unqualified export:

```java
exports com.acme.api;
```

Tên trong danh sách qualified export phải là module name, không phải package name, artifact name tùy ý hay tên class.

## 6. requires transitive: khi API công khai làm lộ dependency

Có trường hợp module trung gian sử dụng type từ dependency trong public API của chính nó. Khi đó consumer của module trung gian có thể cần đọc dependency đó.

Ví dụ:

```text
com.acme.app
    |
    | requires
    v
com.acme.facade
    |
    | requires
    v
com.acme.api
```

Giả sử public method của facade trả về `com.acme.api.Customer`:

```java
package com.acme.facade;

import com.acme.api.Customer;

public class CustomerFacade {
    public Customer findCustomer(String id) {
        // Implementation omitted
        return null;
    }
}
```

Nếu descriptor của facade chỉ khai báo:

```java
module com.acme.facade {
    requires com.acme.api;
    exports com.acme.facade;
}
```

thì module `com.acme.app` khai báo `requires com.acme.facade` không tự động đọc `com.acme.api`. Khi consumer cần gọi `findCustomer` và sử dụng kiểu trả về `Customer`, compiler có thể báo dependency không được đọc hoặc package không visible.

Nếu facade chủ ý đưa type của API dependency vào public API và muốn truyền readability cho consumer, dùng:

```java
module com.acme.facade {
    requires transitive com.acme.api;
    exports com.acme.facade;
}
```

`requires transitive` khiến các module đọc facade cũng đọc module API. Đây là quyết định về hợp đồng công khai của facade, không phải cách sửa mặc định cho mọi lỗi `requires`. Nếu consumer trực tiếp sử dụng một dependency không được facade tái xuất có chủ ý, consumer nên khai báo `requires` dependency đó.

## 7. requires static và dependency tùy chọn

Directive:

```java
requires static com.acme.annotations;
```

khai báo một dependency cần có khi biên dịch nhưng có thể không bắt buộc ở runtime theo quy tắc của `requires static`. Nó thường phù hợp với annotation hoặc dependency chỉ phục vụ compile-time.

`requires static` không phải cách thay thế cho `requires` thông thường khi ứng dụng thực sự cần module ở runtime. Cũng không thể dùng nó để che giấu việc thiếu module trên module path trong lúc biên dịch: compiler vẫn cần tìm thấy dependency compile-time đó.

## 8. exports và opens không giống nhau

Hai directive này thường bị nhầm:

- `exports package.name;` cho phép module khác truy cập các public type và public/protected API trong package theo quy tắc Java.
- `opens package.name;` cho phép truy cập reflective sâu vào package ở runtime, ví dụ framework cần đọc hoặc thay đổi private member bằng reflection.

Nếu lỗi xảy ra khi biên dịch một import hoặc tham chiếu type, hãy kiểm tra `requires` và `exports`. Thêm `opens` thường không sửa được compile error do package chưa được export.

Ví dụ mở package cho framework:

```java
module com.acme.model {
    exports com.acme.model.api;

    opens com.acme.model.internal to com.acme.framework;
}
```

Package API được export để code khác biên dịch và gọi public API. Package internal chỉ mở reflective access cho framework đã chỉ định.

## 9. Biên dịch modular và đọc thông báo lỗi

Khi compile nhiều module từ source tree:

```bash
javac --module-source-path src \
  -d out \
  -m com.acme.api,com.acme.app
```

Khi compile consumer và lấy dependency từ thư mục JAR/module đã build:

```bash
javac --module-path mods \
  --module-source-path src \
  -d out \
  -m com.acme.app
```

Có thể chạy ứng dụng:

```bash
java --module-path out:mods \
  -m com.acme.app/com.acme.app.Main
```

Trên Windows, dấu phân cách nhiều phần tử của module path là dấu chấm phẩy (`;`) thay cho dấu hai chấm (`:`).

Khi đọc compiler output, phân loại thông báo trước khi sửa:

| Thông báo hoặc dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `module not found: X` | Không tìm thấy module X | Kiểm tra module path, tên module và artifact |
| Package is not visible vì module hiện tại does not read module X | Thiếu readability | Thêm `requires X` ở consumer |
| Package is declared in module X, which does not export it | Package chưa được export | Thêm `exports` ở module sở hữu package |
| Package is not exported to module Y | Qualified export không bao gồm consumer | Cập nhật danh sách module đích hoặc dùng export không giới hạn |
| Public API dùng type từ module khác nhưng consumer không đọc được module đó | Dependency chưa được truyền qua API module | Consumer thêm `requires` hoặc API module dùng `requires transitive` nếu phù hợp |
| Reflection bị chặn ở runtime | Package chưa được mở cho reflective access | Dùng `opens` hoặc `--add-opens` cho tình huống phù hợp |

Tên thông báo có thể thay đổi theo phiên bản JDK và vị trí lỗi. Hãy dựa vào phần giải thích đầy đủ của compiler, đặc biệt tên module sở hữu package và tên module đang biên dịch.

## 10. Quy trình chẩn đoán ngắn

Khi gặp compile error trong dự án modular, thực hiện theo thứ tự:

1. Xác định type đang import thuộc package và module nào. Có thể xem descriptor bằng `jar --describe-module --file dependency.jar`.
2. Xác nhận module dependency có trên module path của lệnh `javac`.
3. Kiểm tra module consumer có `requires` đúng module chưa.
4. Kiểm tra module sở hữu package có `exports` package đó cho consumer không; nếu là qualified export, kiểm tra đúng module name.
5. Nếu type xuất hiện trong public API của module trung gian, xem xét `requires transitive`.
6. Nếu vấn đề chỉ xuất hiện khi framework truy cập private member lúc runtime, kiểm tra `opens`, không nhầm với lỗi compile-time.
7. Biên dịch lại toàn bộ module liên quan từ cùng một cấu hình module path để tránh dùng nhầm artifact cũ.

Có thể dùng `jdeps --check` để xem xét module descriptor và dependency của một module:

```bash
jdeps --check com.acme.app --module-path mods
```

## Ghi nhớ

- `requires` tạo readability giữa các module.
- `exports` công khai package từ module sở hữu package.
- Đọc được module không có nghĩa mọi package của module đều truy cập được.
- `requires transitive` truyền readability qua module trung gian khi public API cần điều đó.
- `requires static` là dependency compile-time tùy chọn ở runtime, không phải cách bỏ qua dependency khi biên dịch.
- `opens` phục vụ reflective access ở runtime; nó không thay thế `exports` cho compile-time access.
