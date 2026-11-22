# Export package API và package implementation

Trong Java Platform Module System (JPMS), một module có thể chứa nhiều package nhưng không phải package nào cũng được phép sử dụng từ module khác. Chỉ thị **exports** trong file **module-info.java** xác định package nào được công khai qua ranh giới module. Đây là cách module phân biệt phần API ổn định mà người dùng được phép gọi với phần implementation nội bộ có thể thay đổi theo nhu cầu triển khai.

Thiết kế ranh giới này giúp giảm phụ thuộc giữa các module, hạn chế việc code bên ngoài truy cập chi tiết nội bộ và tạo điều kiện thay đổi implementation mà không làm ảnh hưởng người dùng API.

## 1. Package API và package implementation

Một module thường có hai nhóm package:

- **Package API** chứa các kiểu mà module khác cần sử dụng, chẳng hạn interface, class, exception và kiểu dữ liệu công khai.
- **Package implementation** chứa logic nội bộ, helper, adapter, repository cụ thể hoặc các class chỉ phục vụ việc triển khai bên trong module.

Ví dụ module thanh toán:

~~~text
com.example.payment
├── module-info.java
└── src
    └── com.example.payment
        ├── api
        │   ├── PaymentService.java
        │   ├── PaymentRequest.java
        │   └── PaymentResult.java
        └── internal
            ├── DefaultPaymentService.java
            └── GatewayClient.java
~~~

Package API là nơi các module khác cần biết để gọi chức năng thanh toán. Package internal chỉ phục vụ logic bên trong module payment. Cách phân chia này là quy ước thiết kế; JPMS thực thi ranh giới truy cập thông qua module descriptor.

## 2. Dùng exports để công khai package API

Giả sử module có tên **com.example.payment**. File **module-info.java** chỉ export package API:

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

Module khác có thể khai báo phụ thuộc:

~~~java
module com.example.order {
    requires com.example.payment;
}
~~~

Sau đó code trong module order có thể import các kiểu public thuộc package đã export:

~~~java
package com.example.order;

import com.example.payment.api.PaymentRequest;
import com.example.payment.api.PaymentResult;
import com.example.payment.api.PaymentService;

public class OrderCheckout {
    private final PaymentService paymentService;

    public OrderCheckout(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public PaymentResult checkout(PaymentRequest request) {
        return paymentService.pay(request);
    }
}
~~~

Chỉ thị **exports com.example.payment.api;** làm cho các kiểu public trong package API có thể được module đọc truy cập theo quy tắc Java. Module sử dụng vẫn phải có quan hệ đọc, thường được khai báo bằng **requires**.

**exports** áp dụng cho cả package, không chọn riêng từng class. Nếu một package chứa nhiều class public, các class public trong package đó đều nằm trong bề mặt API được export. Vì vậy, hãy tổ chức package sao cho những kiểu cần công khai nằm cùng package API, còn helper và chi tiết nội bộ nằm ở package riêng.

## 3. Package không export là implementation nội bộ

Giả sử module payment có implementation:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentRequest;
import com.example.payment.api.PaymentResult;
import com.example.payment.api.PaymentService;

public class DefaultPaymentService implements PaymentService {
    @Override
    public PaymentResult pay(PaymentRequest request) {
        // Thực hiện xử lý thanh toán nội bộ.
        return PaymentResult.success();
    }
}
~~~

Package **com.example.payment.internal** không được khai báo trong **exports**. Vì vậy, dù class **DefaultPaymentService** là public, module khác không thể truy cập nó qua ranh giới JPMS theo cách thông thường.

Điều này khác với modifier **public** của Java:

- **public** quyết định mức truy cập của kiểu hoặc thành viên theo ngôn ngữ Java.
- **exports** quyết định package có được công khai cho module khác hay không.
- Để sử dụng một kiểu public từ module khác, package chứa kiểu đó phải được export phù hợp và module gọi phải đọc module cung cấp.

Một class public nằm trong package không export vẫn có thể được sử dụng bên trong chính module sở hữu nó. Các package implementation có thể gọi lẫn nhau theo các quy tắc truy cập Java thông thường, nhưng module bên ngoài không được coi chúng là API.

Nếu module order cố import **com.example.payment.internal.DefaultPaymentService**, trình biên dịch sẽ báo package hoặc kiểu không được truy cập do package không được export. Việc thêm **requires com.example.payment** không giải quyết được lỗi này; cần dùng API được export hoặc thay đổi thiết kế cung cấp chức năng.

## 4. API nên công khai abstraction, không công khai class triển khai

Một thiết kế phổ biến là export interface hoặc abstraction, sau đó giữ class triển khai trong package internal.

Ví dụ API:

~~~java
package com.example.payment.api;

public interface PaymentService {
    PaymentResult pay(PaymentRequest request);
}
~~~

Module payment có thể tạo implementation bên trong:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentRequest;
import com.example.payment.api.PaymentResult;
import com.example.payment.api.PaymentService;

public final class DefaultPaymentService implements PaymentService {
    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.success();
    }
}
~~~

Module bên ngoài chỉ phụ thuộc vào **PaymentService**, **PaymentRequest** và **PaymentResult**. Nó không cần biết implementation hiện tại là **DefaultPaymentService**, **RemotePaymentService** hay một class khác.

Cách thiết kế này đem lại một số lợi ích:

- Có thể thay implementation mà không bắt module sử dụng sửa import hoặc khởi tạo class cụ thể.
- Giảm nguy cơ code bên ngoài phụ thuộc vào helper hoặc cấu trúc dữ liệu nội bộ.
- Giữ bề mặt API nhỏ, dễ tài liệu hóa và kiểm thử.
- Cho phép module sở hữu kiểm soát cách tạo và cấu hình implementation.

Một cách cung cấp implementation là factory method nằm trong package API:

~~~java
package com.example.payment.api;

public final class Payments {
    private Payments() {
    }

    public static PaymentService createDefault() {
        return com.example.payment.internal.PaymentServices.create();
    }
}
~~~

Trong thiết kế thực tế, factory có thể ủy quyền cho package nội bộ hoặc dùng cơ chế Service Provider Interface. Điều quan trọng là module bên ngoài chỉ cần biết kiểu API mà module đã export.

## 5. Qualified exports: chỉ công khai cho module được chọn

Không phải package API nào cũng cần mở cho tất cả module. JPMS hỗ trợ **qualified exports**, tức là chỉ export package cho danh sách module đích.

Ví dụ:

~~~java
module com.example.payment {
    exports com.example.payment.api;
    exports com.example.payment.integration to com.example.order,
                                               com.example.billing;
}
~~~

Trong ví dụ này:

- **com.example.payment.api** được export không giới hạn cho các module đọc module payment.
- **com.example.payment.integration** chỉ được export cho **com.example.order** và **com.example.billing**.
- Module khác không nằm trong danh sách không thể truy cập package integration qua ranh giới module.

Qualified exports phù hợp khi module có API dùng chung và một số package tích hợp chỉ dành cho các module cộng tác cụ thể. Tuy nhiên, danh sách module đích tạo thêm liên kết giữa module cung cấp và module tiêu thụ. Nếu danh sách thay đổi thường xuyên, hãy cân nhắc tách chức năng tích hợp thành module riêng hoặc thiết kế API chung phù hợp hơn.

Qualified exports vẫn là export cho truy cập thông thường của Java; nó không tương đương với **opens** cho reflection sâu.

## 6. exports khác opens như thế nào?

**exports** và **opens** đều xuất hiện trong **module-info.java**, nhưng giải quyết hai nhu cầu khác nhau:

| Chỉ thị | Mục đích | Truy cập được cấp |
|---|---|---|
| **exports package.name;** | Công khai API của package | Truy cập các kiểu public theo quy tắc Java |
| **exports package.name to module.name;** | Công khai API cho module được chọn | Truy cập thông thường trong phạm vi module đích |
| **opens package.name;** | Cho phép reflection sâu ở runtime | Reflection vào các thành viên kể cả private theo cơ chế JPMS |
| **opens package.name to module.name;** | Mở package cho framework/module cụ thể | Reflection sâu trong phạm vi module đích |

Ví dụ framework ánh xạ object cần truy cập field private:

~~~java
module com.example.payment {
    exports com.example.payment.api;
    opens com.example.payment.model to com.example.mapper;
}
~~~

Package **com.example.payment.model** được mở cho module mapper để framework có thể dùng reflection sâu. Chỉ thị này không làm package model trở thành API Java công khai thông thường. Nếu module khác cần import kiểu public trong package model, cần một directive exports thích hợp.

Không nên thêm **opens** chỉ để sửa lỗi import package hoặc truy cập API thông thường. Trường hợp đó cần xem lại **exports** và **requires**. Ngược lại, thêm **exports** không tự động giải quyết lỗi reflection vào private field hoặc constructor.

## 7. Ví dụ đầy đủ với hai module

Giả sử có hai module:

~~~text
src/
├── com.example.payment/
│   ├── module-info.java
│   └── com/example/payment/
│       ├── api/
│       │   ├── PaymentService.java
│       │   └── PaymentResult.java
│       └── internal/
│           └── DefaultPaymentService.java
└── com.example.checkout/
    ├── module-info.java
    └── com/example/checkout/
        └── Main.java
~~~

Module payment export duy nhất package API:

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

API:

~~~java
package com.example.payment.api;

public interface PaymentService {
    String pay();
}
~~~

Implementation:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentService;

public final class DefaultPaymentService implements PaymentService {
    @Override
    public String pay() {
        return "Payment accepted";
    }
}
~~~

Module checkout khai báo dependency:

~~~java
module com.example.checkout {
    requires com.example.payment;
}
~~~

Code checkout có thể sử dụng interface API:

~~~java
package com.example.checkout;

import com.example.payment.api.PaymentService;

public class Main {
    public static void main(String[] args) {
        PaymentService service = null;
        System.out.println("Checkout module can compile against PaymentService");
    }
}
~~~

Code checkout không thể import **com.example.payment.internal.DefaultPaymentService**, bởi package internal không được export. Trong ví dụ tối giản, module checkout cần nhận một instance PaymentService qua factory, dependency injection hoặc ServiceLoader khi chạy thật. Cách khởi tạo implementation không làm thay đổi nguyên tắc: module tiêu thụ chỉ phụ thuộc vào API đã export.

Biên dịch các module theo module source path:

~~~bash
javac --module-source-path src -d out -m com.example.payment,com.example.checkout
~~~

Khi biên dịch, nếu checkout import class trong package internal, compiler sẽ từ chối truy cập package đó. Đây là kiểm tra hữu ích để bảo vệ ranh giới API ngay từ thời điểm biên dịch.

## 8. Tổ chức package để ranh giới API rõ ràng

Khi thiết kế module mới, có thể áp dụng các nguyên tắc sau:

1. Đặt interface, DTO, exception và kiểu công khai trong các package API có tên rõ ràng.
2. Đặt implementation cụ thể, helper và adapter nội bộ trong package riêng như **internal**, **impl** hoặc package chuyên trách.
3. Chỉ export package mà module tiêu thụ thực sự cần.
4. Hạn chế qualified exports cho những tích hợp có quan hệ module rõ ràng.
5. Dùng **opens** riêng cho nhu cầu reflection đã xác định, thường là cho framework cụ thể.
6. Tránh đưa class implementation vào cùng package với API nếu không muốn chúng cùng nằm trong bề mặt export.
7. Xem các kiểu public trong package đã export là cam kết API; thay đổi chữ ký của chúng có thể ảnh hưởng module tiêu thụ.

Tên **internal** hay **impl** tự nó không tạo ra bảo vệ. Ranh giới được JPMS thực thi nhờ việc không export package đó. Nếu module descriptor export nhầm package internal, package đó trở thành một phần API bất kể tên package.

Cũng cần lưu ý rằng export package không đồng nghĩa mọi dependency của module tự động được công khai lại. Nếu API public của module payment sử dụng kiểu thuộc module khác, module cung cấp có thể cần khai báo **requires transitive** cho dependency phù hợp để module tiêu thụ API nhận được khả năng đọc cần thiết theo thiết kế. Việc export package và việc truyền tiếp quan hệ đọc là hai quyết định độc lập.

## 9. Lỗi thường gặp và cách xử lý

**Module đã requires nhưng không truy cập được class public**

Kiểm tra package chứa class đã được export chưa. Modifier public không vượt qua ranh giới module khi package không được export.

**Implementation class bị module khác import trực tiếp**

Nếu class nằm trong package internal chưa export, compiler sẽ từ chối. Module tiêu thụ nên gọi abstraction trong API; module sở hữu có thể cung cấp factory hoặc cơ chế tạo implementation.

**Đã export package nhưng framework vẫn không truy cập được private field**

Exports chỉ công khai API thông thường. Nếu cần reflection sâu, mở đúng package bằng opens hoặc qualified opens cho module framework.

**Module ngoài truy cập được nhiều package không nên công khai**

Kiểm tra module-info.java và bỏ các directive exports không cần thiết. Sau đó chuyển class nội bộ sang package không export và cập nhật các điểm sử dụng hợp lệ trong module sở hữu.

**Qualified exports làm module mới không biên dịch được**

Kiểm tra tên module đích có khớp với tên module thực tế hay không. Chỉ các module được liệt kê mới có quyền truy cập package được qualified export.

**API public phụ thuộc vào kiểu từ module khác nhưng module tiêu thụ không đọc được dependency**

Xem xét quan hệ **requires transitive** trong module cung cấp API. Không nên thêm transitive một cách máy móc; chỉ dùng khi dependency thực sự là một phần của hợp đồng API cần module tiêu thụ đọc được.

## 10. Ghi nhớ

- **exports** công khai package cho module khác; package không export vẫn là implementation nội bộ theo ranh giới JPMS.
- **public** là modifier của Java, còn **exports** là quyền truy cập package qua ranh giới module.
- Không thể export riêng từng class; exports áp dụng cho toàn bộ package.
- Qualified exports giới hạn package API cho các module đích được chỉ định.
- **opens** dành cho reflection sâu ở runtime, không thay thế exports.
- Nên công khai abstraction ổn định và giữ class triển khai trong package không export.
- Chỉ thị **requires transitive** điều khiển việc truyền tiếp khả năng đọc dependency; nó độc lập với exports.
- Tên package **internal** không tự bảo vệ implementation; module descriptor mới quyết định package có được công khai hay không.

Khi review một module, hãy nhìn vào danh sách exports trong module-info.java và xác định từng package có thực sự là API cần hỗ trợ module bên ngoài hay không. Một bề mặt API nhỏ và có chủ đích giúp module dễ thay đổi implementation, giảm phụ thuộc và giữ hợp đồng giữa các module rõ ràng.
