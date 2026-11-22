# Exports package để module khác compile và access

## 1. Vai trò của exports trong JPMS

Trong Java Platform Module System (JPMS), mỗi named module có thể khai báo những package mà module khác được phép sử dụng. Chỉ thị `exports` trong `module-info.java` thực hiện việc công bố đó.

Ví dụ:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Khai báo này công bố package `com.acme.orders.api` như một phần API của module `com.acme.orders`. Những package khác của module vẫn được giữ ở phạm vi nội bộ nếu không có chỉ thị công bố tương ứng.

Để một module tiêu thụ sử dụng package đã export, cần có hai điều kiện:

1. Module tiêu thụ phải **đọc được** module cung cấp package, thường thông qua `requires`.
2. Module cung cấp phải **export** package mà module tiêu thụ muốn truy cập.

Có thể ghi nhớ sự phân chia trách nhiệm như sau:

- `requires` xác định module nào module hiện tại cần đọc.
- `exports` xác định package nào module khác được phép truy cập.

Hai khai báo bổ sung cho nhau. Chỉ có `requires` không tự mở mọi package của module được yêu cầu; chỉ có `exports` cũng không tự tạo quan hệ đọc từ module tiêu thụ.

## 2. Cú pháp cơ bản

Cú pháp export một package cho mọi module đọc module hiện tại:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Tên package trong `exports` là tên đầy đủ, phân biệt chữ hoa và chữ thường. Chỉ thị được đặt bên trong module declaration của file `module-info.java`, thường ở thư mục gốc của source module.

Một module có thể export nhiều package:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.dto;
    exports com.acme.orders.spi;
}
~~~

Mỗi package được công bố độc lập. Nếu muốn công bố package con, phải khai báo riêng package đó.

Ví dụ, khai báo:

~~~java
exports com.acme.orders.api;
~~~

không tự động công bố:

~~~text
com.acme.orders.api.internal
com.acme.orders.api.model
~~~

Package trong Java không có cơ chế export đệ quy theo cây thư mục.

## 3. Ví dụ hai module cùng sử dụng API

Giả sử có hai module:

~~~text
orders/
├── module-info.java
└── com/acme/orders/
    ├── api/
    │   └── OrderService.java
    └── internal/
        └── OrderRepository.java

checkout/
├── module-info.java
└── com/acme/checkout/
    └── CheckoutService.java
~~~

Module `orders` công bố package API:

~~~java
// orders/module-info.java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Một kiểu public nằm trong package được export:

~~~java
// orders/com/acme/orders/api/OrderService.java
package com.acme.orders.api;

public class OrderService {
    public String findOrder(long id) {
        return "Order " + id;
    }
}
~~~

Module `checkout` khai báo phụ thuộc:

~~~java
// checkout/module-info.java
module com.acme.checkout {
    requires com.acme.orders;
}
~~~

Sau đó, code trong module `checkout` có thể import và gọi API:

~~~java
package com.acme.checkout;

import com.acme.orders.api.OrderService;

public class CheckoutService {
    public void checkout() {
        OrderService orders = new OrderService();
        System.out.println(orders.findOrder(1001));
    }
}
~~~

Khi biên dịch, compiler kiểm tra module `checkout` có đọc `com.acme.orders` hay không và package `com.acme.orders.api` có được module đó export hay không. Khi chạy, JVM tiếp tục áp dụng ranh giới module tương ứng.

Nếu bỏ `exports com.acme.orders.api;`, module `checkout` không thể sử dụng package này theo cách truy cập Java thông thường, dù đã viết `requires com.acme.orders;`.

Nếu bỏ `requires com.acme.orders;`, module `checkout` không có quan hệ readability cần thiết để dùng API của module `orders`.

## 4. exports cho phép truy cập đến đâu?

`exports` công bố package cho truy cập Java thông thường. Việc công bố package không làm mọi thành viên trong package trở thành public.

Quy tắc truy cập Java vẫn được áp dụng:

- Các kiểu public trong package được export có thể được module đọc sử dụng.
- Các thành viên public được truy cập theo quy tắc Java thông thường.
- Thành viên protected vẫn chịu các quy tắc truy cập protected, bao gồm quan hệ kế thừa và package.
- Kiểu hoặc thành viên package-private không trở thành public chỉ vì package được export.
- Thành viên private vẫn chỉ truy cập được theo quy tắc private của Java.

Ví dụ:

~~~java
package com.acme.orders.api;

public class Order {
    public String id;

    String internalCode;

    private String secret;
}
~~~

Module khác có thể truy cập kiểu public `Order` và trường public `id`. Trường `internalCode` có package-private access, còn `secret` là private; `exports` không thay đổi các mức truy cập đó.

Vì vậy, một package được export nên được xem là một phần API có thể nhìn thấy từ bên ngoài module. Nhóm phát triển cần cân nhắc kiểu public nào nên xuất hiện trong package này và giữ các chi tiết triển khai ở package nội bộ.

## 5. Qualified exports: chỉ công bố cho một số module

JPMS cho phép export một package có điều kiện, chỉ dành cho các module được chỉ định. Cách này gọi là **qualified exports**.

Cú pháp:

~~~java
module com.acme.orders {
    exports com.acme.orders.spi to
        com.acme.checkout,
        com.acme.admin;
}
~~~

Trong ví dụ này, package `com.acme.orders.spi` chỉ được công bố cho hai module `com.acme.checkout` và `com.acme.admin`. Các module khác không nhận được quyền truy cập package này thông qua chỉ thị đó.

Qualified exports hữu ích khi:

- Một package là API tích hợp dành riêng cho một số module nội bộ.
- Module muốn giới hạn số consumer được phép phụ thuộc vào một API chưa dành cho công chúng.
- Một nhóm module cần chia sẻ SPI hoặc contract kỹ thuật nhưng không muốn công bố cho toàn bộ module trong ứng dụng.

Ví dụ đầy đủ:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.checkout;
}
~~~

Module `com.acme.checkout` có thể đọc cả API công khai và SPI được cấp quyền. Một module khác chỉ có thể đọc package API công khai.

Qualified exports vẫn tuân theo nguyên tắc readability: module được nêu tên phải đọc module cung cấp nếu muốn sử dụng package.

## 6. exports không giống opens

Hai chỉ thị `exports` và `opens` đều liên quan đến ranh giới package, nhưng phục vụ hai kiểu truy cập khác nhau.

| Chỉ thị | Mục đích | Khả năng chính |
|---|---|---|
| `exports` | Truy cập Java thông thường | Module khác import và gọi API public của package |
| `opens` | Deep reflection | Cho phép framework hoặc thư viện phản chiếu truy cập sâu vào package |
| `opens ... to ...` | Deep reflection có giới hạn | Chỉ mở package cho các module được chỉ định |

Ví dụ module công bố API cho mọi consumer nhưng chỉ mở package model cho thư viện serialization:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    opens com.acme.orders.model to com.fasterxml.jackson.databind;
}
~~~

Trong trường hợp này:

- Module khác có thể import các kiểu public từ `com.acme.orders.api`.
- Module Jackson được cấp quyền deep reflection vào `com.acme.orders.model`.
- Các module khác không tự nhận quyền deep reflection đó.

`exports` không thay thế `opens`. Nếu một framework cần truy cập field private hoặc constructor không public bằng reflection, chỉ export package thường không đủ. Ngược lại, mở package cho reflection không có nghĩa package đã trở thành API có thể import và sử dụng thông thường.

## 7. exports có tính transitive không?

Không. Chỉ thị `exports` công bố package của module khai báo nó; nó không tự truyền quyền export sang module khác.

Cần phân biệt:

- `exports p;` công bố package `p`.
- `requires transitive m;` truyền khả năng đọc module `m` đến các module phụ thuộc vào module hiện tại.

Ví dụ, API public của module `com.acme.orders` sử dụng kiểu public từ module `com.acme.money`:

~~~java
module com.acme.orders {
    requires transitive com.acme.money;

    exports com.acme.orders.api;
}
~~~

`requires transitive` có thể cần thiết để consumer của `com.acme.orders` cũng đọc được `com.acme.money` khi sử dụng các kiểu thuộc module đó thông qua API của orders.

Điều này không có nghĩa package của `com.acme.money` được export bởi module `com.acme.orders`. Module `com.acme.money` vẫn phải tự công bố package API của nó.

## 8. Những lỗi và hiểu nhầm thường gặp

### 8.1. Có requires nhưng thiếu exports

Module tiêu thụ khai báo:

~~~java
module com.acme.checkout {
    requires com.acme.orders;
}
~~~

Nhưng module cung cấp không export package cần dùng:

~~~java
module com.acme.orders {
    // com.acme.orders.api chưa được export
}
~~~

Kết quả là module tiêu thụ vẫn không thể truy cập package đó. `requires` chỉ tạo readability; nó không bỏ qua encapsulation của module được yêu cầu.

### 8.2. Export package cha và nghĩ package con cũng được công bố

Khai báo:

~~~java
exports com.acme.orders.api;
~~~

không công bố `com.acme.orders.api.internal`. Nếu thực sự muốn module khác truy cập package con, phải thêm chỉ thị export riêng. Trước khi làm vậy, nên xem xét liệu package con có nên trở thành API hay không.

### 8.3. Nghĩ rằng exports biến mọi class thành public

Một lớp package-private vẫn không thể được import từ module khác chỉ vì package của nó đã export. `exports` kiểm soát ranh giới module; modifier của lớp và thành viên vẫn kiểm soát khả năng truy cập theo Java Language Specification.

### 8.4. Dùng exports khi framework cần reflection sâu

Nếu lỗi xuất hiện khi framework cố truy cập field private hoặc constructor không public, hãy xác định package có cần `opens` hay không. Thêm `exports` có thể không giải quyết được deep reflection.

### 8.5. Export quá nhiều package

Export toàn bộ package khiến nhiều chi tiết triển khai trở thành bề mặt API mà module khác có thể phụ thuộc. Khi cấu trúc nội bộ thay đổi, các consumer có thể bị ảnh hưởng.

Nên bắt đầu từ một tập package API nhỏ, chỉ export thêm khi có nhu cầu sử dụng thực tế và có chủ đích.

## 9. Cách chọn package để export

Khi thiết kế module, hãy đánh giá mỗi package theo vai trò:

- **API công khai:** chứa abstraction, kiểu dữ liệu và thao tác mà consumer cần dùng; thường được export không giới hạn.
- **SPI hoặc API tích hợp:** dành cho một số module cụ thể; có thể dùng qualified exports.
- **Implementation:** chứa repository implementation, mapper, helper và lớp nội bộ; thường không export.
- **Package cần reflection:** chỉ mở bằng `opens` cho framework thực sự cần, với phạm vi hẹp nhất có thể.

Ví dụ:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.checkout;

    opens com.acme.orders.model to com.fasterxml.jackson.databind;
}
~~~

Trong module này, API được công bố cho mọi module đọc `com.acme.orders`; SPI chỉ dành cho checkout; model được mở cho Jackson để reflection. Package triển khai khác vẫn được giữ kín.

Trước khi thêm một dòng `exports`, hãy trả lời:

1. Module consumer nào cần sử dụng package này?
2. Consumer cần import kiểu public nào?
3. Package có phải một phần API ổn định mà nhóm sẵn sàng hỗ trợ không?
4. Có nên export cho mọi module hay chỉ một số module?
5. Consumer cần truy cập thông thường hay cần deep reflection?

## 10. Ghi nhớ

`exports` là chỉ thị xác định **package nào của một named module được công bố cho module khác truy cập theo quy tắc Java thông thường**. Module tiêu thụ thường cần thêm `requires` để đọc module cung cấp.

- `requires` tạo quan hệ readability.
- `exports` công bố package.
- `exports p to m;` giới hạn consumer được phép truy cập package.
- `exports` không export package con một cách tự động.
- `exports` không thay đổi modifier `public`, `protected`, package-private hoặc `private`.
- `opens` dành cho deep reflection và có mục đích khác với `exports`.

Thiết kế tốt thường chỉ export các package tạo thành API cần thiết, giữ phần triển khai trong module và chỉ mở reflection cho đúng thư viện cần dùng. Đây là cách JPMS giúp module có ranh giới rõ ràng và giảm phụ thuộc vào chi tiết nội bộ.
