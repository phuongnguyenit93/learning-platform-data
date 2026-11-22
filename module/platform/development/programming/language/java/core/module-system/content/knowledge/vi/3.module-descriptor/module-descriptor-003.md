# requires, exports, opens, uses và provides trong module descriptor

Trong Java Platform Module System (JPMS), file module-info.java là nơi một mô-đun khai báo hợp đồng với phần còn lại của ứng dụng. Module descriptor cho biết mô-đun cần đọc mô-đun nào, công khai package nào, cho phép reflection ở đâu và tham gia cơ chế service như thế nào.

Năm chỉ thị thường gặp nhất là **requires**, **exports**, **opens**, **uses** và **provides**. Mỗi chỉ thị điều khiển một khía cạnh riêng. Hiểu đúng chúng giúp thiết kế API có ranh giới rõ ràng và xử lý các vấn đề tương thích với framework.

## 1. Module descriptor nằm ở đâu?

Với một named module, file nguồn module-info.java nằm ở gốc source set của mô-đun, bên cạnh các package của nó. Ví dụ:

~~~text
src/
└── com.example.orders/
    ├── module-info.java
    └── com/
        └── example/
            └── orders/
                ├── api/
                │   └── OrderService.java
                └── internal/
                    └── OrderRepository.java
~~~

Descriptor tối giản:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Tên sau từ khóa module là tên mô-đun. Các chỉ thị bên trong cặp ngoặc nhọn mô tả dependency và quyền truy cập. Khi biên dịch, Java tạo module-info.class; trong một modular JAR, file này nằm ở thư mục gốc của JAR.

Một mô-đun luôn đọc được mô-đun nền tảng java.base mà không cần khai báo requires tường minh. Đây là nơi chứa các API cốt lõi như java.lang, java.util và java.io.

Module descriptor không phải là danh sách tất cả lớp trong JAR. Nó là bản khai báo các quan hệ và ranh giới mà JPMS sử dụng khi phân giải mô-đun và kiểm soát truy cập.

## 2. Tổng quan năm chỉ thị

| Chỉ thị | Câu hỏi mà nó trả lời | Tác dụng |
| --- | --- | --- |
| **requires** | Mô-đun này cần đọc mô-đun nào? | Khai báo dependency và quan hệ readability. |
| **exports** | Mô-đun khác được dùng API ở package nào? | Công khai package cho truy cập Java thông thường. |
| **opens** | Framework nào được reflection sâu vào package nào? | Cho phép deep reflection tại runtime. |
| **uses** | Mô-đun này cần tìm implementation của service nào? | Khai báo service consumer. |
| **provides** | Mô-đun này cung cấp implementation cho service nào? | Đăng ký service provider trong module layer. |

Các chỉ thị này không thay thế lẫn nhau. Chẳng hạn, requires không tự công khai package của dependency; exports không cấp quyền deep reflection; opens không làm package trở thành API để mã khác import tùy ý.

## 3. requires: khai báo mô-đun phụ thuộc

Cú pháp cơ bản:

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

Mô-đun orders khai báo rằng nó cần đọc mô-đun customer. Nhờ quan hệ này, mã trong orders có thể tham chiếu các kiểu thuộc những package mà customer export phù hợp.

Để việc sử dụng API thành công, cần có cả hai phía:

- Mô-đun sử dụng khai báo requires tới mô-đun sở hữu API.
- Mô-đun sở hữu API export package chứa các kiểu cần công khai.

Ví dụ:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

Nếu chỉ có requires mà package API chưa được export, mô-đun orders vẫn không thể truy cập package đó. Nếu package đã export nhưng orders không đọc customer, mã trong orders cũng không tự động có quyền sử dụng API.

### 3.1. requires transitive

~~~java
module com.example.orders.api {
    requires transitive com.example.customer.api;
}
~~~

requires transitive tạo ra quan hệ đọc được truyền tiếp. Các mô-đun đọc orders.api cũng được phép đọc customer.api thông qua quan hệ này.

Hãy dùng transitive khi kiểu của dependency xuất hiện trong API công khai của mô-đun hiện tại. Ví dụ một phương thức public trả về Customer hoặc nhận Customer làm tham số. Người dùng API có thể cần đọc mô-đun customer để biên dịch mã gọi phương thức đó.

Không nên thêm transitive chỉ vì mô-đun hiện tại có sử dụng dependency ở bên trong. Nếu dependency chỉ là chi tiết triển khai và không xuất hiện trong hợp đồng API, requires thông thường phù hợp hơn.

### 3.2. requires static

~~~java
module com.example.orders {
    requires static com.example.optional.annotations;
}
~~~

requires static khai báo dependency cần có khi biên dịch nhưng không bắt buộc phải có trong cấu hình runtime. Nó thường phù hợp với annotation hoặc tích hợp tùy chọn chỉ phục vụ compile-time.

Nếu mã thực thi thực sự cần một lớp thuộc dependency tùy chọn, ứng dụng vẫn phải bảo đảm lớp đó có mặt khi chạy nhánh mã tương ứng. requires static không tự tạo stub và cũng không tự xử lý trường hợp thiếu lớp.

Có thể kết hợp static và transitive khi dependency vừa là dependency compile-time tùy chọn, vừa cần được truyền tiếp trong quan hệ readability:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
}
~~~

### 3.3. Dependency ngầm định java.base

Mọi named module đều có quan hệ đọc tới java.base. Vì vậy, descriptor thông thường không cần viết:

~~~java
module com.example.orders {
    // java.base được yêu cầu ngầm định.
}
~~~

Các mô-đun JDK khác như java.sql hoặc java.logging vẫn cần được khai báo khi mã của mô-đun sử dụng API của chúng:

~~~java
module com.example.reporting {
    requires java.sql;
    requires java.logging;
}
~~~

## 4. exports: công khai package API

Cú pháp:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

exports cho phép các mô-đun đọc được mô-đun orders truy cập các kiểu public trong package com.example.orders.api, cùng các thành viên public/protected theo quy tắc truy cập của Java.

Ví dụ:

~~~java
package com.example.orders.api;

public class OrderService {
    public void submit() {
        // Xử lý đơn hàng.
    }
}
~~~

Nếu package này được export, mô-đun khác có thể import OrderService khi đã khai báo requires tới mô-đun sở hữu package.

Một lớp public trong package không được export vẫn không trở thành API có thể sử dụng từ named module khác. Từ khóa public của Java và ranh giới export của JPMS là hai lớp kiểm soát khác nhau.

### 4.1. Qualified exports

Có thể giới hạn package chỉ dành cho một số mô-đun:

~~~java
module com.example.orders {
    exports com.example.orders.spi to
        com.example.orders.plugin,
        com.example.orders.test;
}
~~~

Đây là qualified export. Mô-đun orders.plugin và orders.test có thể truy cập package SPI, còn các mô-đun khác không nhận được quyền đó chỉ vì package đã được export có giới hạn.

Cách này hữu ích cho API nội bộ giữa các mô-đun trong cùng một sản phẩm. Nó cũng giúp tránh biến mọi package hỗ trợ thành hợp đồng công khai cho tất cả người dùng thư viện.

### 4.2. exports không mở private field cho reflection

exports phục vụ truy cập API thông thường. Nó không cấp quyền tổng quát để framework gọi setAccessible trên field hoặc constructor private của package.

Nếu framework cần deep reflection, cần xem xét opens. Không nên thêm exports chỉ để chữa InaccessibleObjectException vì hai chỉ thị giải quyết hai nhu cầu khác nhau.

## 5. opens: cho phép deep reflection

Một số framework cần truy cập thành viên không public để ánh xạ object, inject dependency, serialize dữ liệu hoặc tạo proxy. JPMS kiểm soát hoạt động này bằng opens.

Cú pháp:

~~~java
module com.example.domain {
    opens com.example.domain.model;
}
~~~

Khai báo trên mở package model cho deep reflection ở runtime đối với các mô-đun khác. Nó không công khai package như một API Java thông thường.

### 5.1. Qualified opens

Nên giới hạn quyền reflection cho mô-đun framework cụ thể khi có thể:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.mapper;
}
~~~

Chỉ mô-đun mapper được phép deep reflection trên package model. Nếu một framework khác cũng cần quyền, có thể liệt kê thêm tên mô-đun đích.

### 5.2. open module

Có thể mở tất cả package của mô-đun cho deep reflection bằng cú pháp:

~~~java
open module com.example.domain {
    requires com.example.validation;
}
~~~

Đây là open module declaration. Mọi package trong mô-đun được mở cho deep reflection ở runtime. Vì phạm vi rộng, chỉ nên dùng khi mô-đun thực sự cần khả năng reflection tổng quát.

Một open module declaration không được chứa các chỉ thị opens riêng lẻ. Nếu chỉ một vài package cần mở, hãy dùng module declaration bình thường cùng các chỉ thị opens có phạm vi rõ ràng.

### 5.3. Mở package bằng tham số JVM

Khi chưa thể sửa module-info.java của thư viện, có thể kiểm tra hoặc cấu hình tạm bằng --add-opens:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.mapper ...
~~~

Nếu framework nằm trong classpath và thuộc unnamed module:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED ...
~~~

Tham số này mở package ở runtime cho đích được chỉ định. Nó hữu ích để xác nhận lỗi đến từ giới hạn reflection, nhưng cần quản lý cẩn thận trong cấu hình triển khai.

## 6. uses: khai báo service consumer

JPMS hỗ trợ Service Provider Interface (SPI), cho phép mô-đun sử dụng một hợp đồng service mà không cần phụ thuộc trực tiếp vào lớp triển khai.

Mô-đun sử dụng khai báo service bằng uses:

~~~java
module com.example.checkout {
    requires com.example.payment.api;
    uses com.example.payment.api.PaymentProcessor;
}
~~~

Trong ví dụ, checkout cần tìm một hoặc nhiều implementation của PaymentProcessor. Nó phụ thuộc vào mô-đun chứa interface service, nhưng không cần khai báo requires tới từng mô-đun provider.

Interface service có thể được định nghĩa như sau:

~~~java
package com.example.payment.api;

public interface PaymentProcessor {
    void process(long orderId);
}
~~~

Package chứa interface phải được export để mô-đun consumer có thể tham chiếu kiểu PaymentProcessor.

Khi mã trong checkout gọi ServiceLoader, khai báo uses cho biết mô-đun này có ý định tiêu thụ service đó:

~~~java
ServiceLoader<PaymentProcessor> processors =
        ServiceLoader.load(PaymentProcessor.class);

for (PaymentProcessor processor : processors) {
    processor.process(1001L);
}
~~~

Trong named module, việc gọi ServiceLoader.load cho service cần được mô-đun khai báo bằng uses. Thiếu khai báo có thể dẫn tới ServiceConfigurationError khi ServiceLoader kiểm tra quyền sử dụng service.

## 7. provides: đăng ký service provider

Mô-đun chứa implementation khai báo provider bằng provides ... with ...:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor
        with com.example.payment.card.CardPaymentProcessor;
}
~~~

Implementation:

~~~java
package com.example.payment.card;

import com.example.payment.api.PaymentProcessor;

public class CardPaymentProcessor implements PaymentProcessor {
    @Override
    public void process(long orderId) {
        System.out.println("Xử lý thanh toán thẻ cho đơn " + orderId);
    }
}
~~~

Mô-đun provider cần đọc mô-đun chứa service interface. Chỉ thị provides liên kết service type với một hoặc nhiều provider type.

Có thể đăng ký nhiều provider cho cùng một service:

~~~java
module com.example.payment {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor with
        com.example.payment.card.CardPaymentProcessor,
        com.example.payment.wallet.WalletPaymentProcessor;
}
~~~

Package chứa provider không nhất thiết phải export. ServiceLoader có thể tạo provider theo khai báo mô-đun mà không cần công khai package triển khai cho mọi mô-đun khác.

Một provider trong named module thường cung cấp public no-argument constructor, hoặc một public static provider method theo quy tắc ServiceLoader. Provider method có tên provider, không nhận tham số và trả về một kiểu tương thích với service type. Cơ chế provider method hữu ích khi việc tạo implementation cần được điều khiển bởi mô-đun provider.

## 8. Ví dụ hoàn chỉnh: tách API, ứng dụng và provider

Một ví dụ nhỏ gồm ba mô-đun:

~~~text
src/
├── com.example.payment.api/
│   ├── module-info.java
│   └── com/example/payment/api/PaymentProcessor.java
├── com.example.payment.card/
│   ├── module-info.java
│   └── com/example/payment/card/CardPaymentProcessor.java
└── com.example.checkout/
    ├── module-info.java
    └── com/example/checkout/Main.java
~~~

### Mô-đun API

module-info.java:

~~~java
module com.example.payment.api {
    exports com.example.payment.api;
}
~~~

PaymentProcessor.java:

~~~java
package com.example.payment.api;

public interface PaymentProcessor {
    void process(long orderId);
}
~~~

### Mô-đun provider

module-info.java:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor
        with com.example.payment.card.CardPaymentProcessor;
}
~~~

CardPaymentProcessor.java:

~~~java
package com.example.payment.card;

import com.example.payment.api.PaymentProcessor;

public class CardPaymentProcessor implements PaymentProcessor {
    @Override
    public void process(long orderId) {
        System.out.println("Card payment for order " + orderId);
    }
}
~~~

### Mô-đun ứng dụng

module-info.java:

~~~java
module com.example.checkout {
    requires com.example.payment.api;
    uses com.example.payment.api.PaymentProcessor;
}
~~~

Main.java:

~~~java
package com.example.checkout;

import com.example.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<PaymentProcessor> loader =
                ServiceLoader.load(PaymentProcessor.class);

        for (PaymentProcessor processor : loader) {
            processor.process(1001L);
        }
    }
}
~~~

Ứng dụng chỉ biết interface PaymentProcessor. Nó không cần import CardPaymentProcessor và cũng không cần khai báo requires tới mô-đun provider. Quan hệ service được mô tả qua uses và provides.

Biên dịch ba mô-đun:

~~~bash
javac --module-source-path src -d out -m     com.example.payment.api,com.example.payment.card,com.example.checkout
~~~

Khi khởi chạy, cần bảo đảm mô-đun provider được đưa vào cấu hình mô-đun. Có thể thêm provider như một root module:

~~~bash
java --module-path out --add-modules com.example.payment.card     -m com.example.checkout/com.example.checkout.Main
~~~

Hoặc dùng cơ chế service binding phù hợp với cấu hình chạy để các provider được liên kết vào module graph. Nếu chỉ resolve mô-đun checkout và API mà không đưa provider vào cấu hình, ServiceLoader không thể tìm thấy provider chưa được resolve.

## 9. Kết hợp các chỉ thị trong một descriptor

Một module descriptor có thể dùng nhiều chỉ thị cùng lúc:

~~~java
module com.example.orders {
    requires java.sql;
    requires transitive com.example.customer.api;
    requires static com.example.annotations;

    exports com.example.orders.api;
    exports com.example.orders.spi to com.example.orders.plugin;

    opens com.example.orders.model to com.example.orm;

    uses com.example.orders.spi.OrderProcessor;

    provides com.example.orders.spi.OrderProcessor
        with com.example.orders.internal.DefaultOrderProcessor;
}
~~~

Ví dụ này thể hiện các quyết định khác nhau:

- java.sql là dependency mà mô-đun sử dụng.
- customer.api được truyền tiếp readability vì kiểu của nó có thể xuất hiện trong API công khai.
- annotations chỉ là dependency compile-time tùy chọn.
- package api được công khai cho các mô-đun đọc orders.
- package spi chỉ dành cho plugin nội bộ.
- package model mở cho ORM thực hiện deep reflection.
- mô-đun vừa tiêu thụ OrderProcessor, vừa cung cấp implementation mặc định.

Không nhất thiết dự án nào cũng cần cả năm loại chỉ thị. Chỉ khai báo những quan hệ có thật trong thiết kế mô-đun.

## 10. Phân biệt exports, opens và provides

Ba chỉ thị này thường bị nhầm vì đều đề cập đến package hoặc kiểu trong mô-đun, nhưng chúng phục vụ các cơ chế khác nhau:

| Chỉ thị | Ai sử dụng? | Kết quả |
| --- | --- | --- |
| exports | Mã Java của mô-đun khác | Có thể import và gọi API public trong package được export. |
| opens | Framework hoặc thư viện dùng reflection | Có thể deep reflection vào package tại runtime. |
| provides | ServiceLoader và module resolution | Đăng ký implementation cho một service type. |

Ví dụ, ORM cần đọc field private thì cần opens. Một mô-đun muốn import OrderService thì cần package chứa OrderService được exports và mô-đun gọi có requires. Một ứng dụng muốn tìm implementation qua ServiceLoader thì consumer cần uses và provider cần provides.

## 11. Kiểm tra module descriptor và lỗi thường gặp

Có thể xem descriptor của một JAR bằng:

~~~bash
jar --describe-module --file libs/example.jar
~~~

Lệnh này hiển thị tên mô-đun, các requires, exports, opens và thông tin provider nếu có.

Một số lỗi và cách kiểm tra:

| Triệu chứng | Nguyên nhân có thể | Kiểm tra hoặc sửa |
| --- | --- | --- |
| package is not visible | Thiếu requires hoặc package chưa exports | Kiểm tra descriptor của cả consumer và owner. |
| module does not read module | Chưa có quan hệ readability | Thêm requires đúng mô-đun. |
| does not export package | Package API chưa được export cho consumer | Thêm exports hoặc qualified exports. |
| InaccessibleObjectException | Framework cần deep reflection | Mở đúng package bằng opens hoặc --add-opens. |
| ServiceConfigurationError | Thiếu uses, provider chưa được resolve hoặc provider sai cấu hình | Kiểm tra uses, provides và module graph. |
| Module not found | Thiếu JAR hoặc sai tên mô-đun | Dùng jar --describe-module và kiểm tra module path. |

Khi chẩn đoán, hãy phân biệt lỗi compile-time với runtime. exports có ảnh hưởng đến khả năng truy cập API thông thường khi biên dịch và chạy; opens chủ yếu phục vụ reflection ở runtime. uses và provides liên quan đến việc khai báo, phân giải và tìm service provider.

## 12. Nguyên tắc thiết kế descriptor dễ bảo trì

- **Khai báo dependency trực tiếp:** mỗi mô-đun nên mô tả những mô-đun mà mã của nó thực sự cần đọc.
- **Dùng transitive có chủ đích:** chỉ truyền tiếp readability khi dependency là một phần của API mà mô-đun công khai.
- **Export package API:** tránh export package implementation hoặc package chỉ phục vụ nội bộ.
- **Giới hạn qualified exports/opens:** nếu chỉ một vài mô-đun cần quyền truy cập, hãy ghi rõ tên đích.
- **Mở reflection theo nhu cầu framework:** không dùng open module rộng chỉ để tránh tìm hiểu package nào thực sự cần mở.
- **Tách service contract và provider:** consumer phụ thuộc vào interface; provider phụ thuộc vào contract và đăng ký bằng provides.
- **Kiểm tra module graph:** sau khi thêm hoặc thay dependency, xác minh descriptor và cấu hình runtime bằng công cụ JDK.

Module descriptor tốt làm rõ hợp đồng của mô-đun ngay tại một nơi: dependency nào được đọc, API nào được công khai, package nào mở cho reflection và service nào được tiêu thụ hoặc cung cấp.

## 13. Tự kiểm tra

**Tình huống 1:** Mô-đun checkout gọi một kiểu public trong package của customer nhưng gặp lỗi package is not visible. Cần kiểm tra những khai báo nào?

Trả lời: checkout cần requires tới customer; customer cần exports package chứa kiểu đó. Chỉ có một trong hai khai báo là chưa đủ.

**Tình huống 2:** ORM cần gán giá trị vào field private của entity. Có nên export package entity không?

Trả lời: nhu cầu này là deep reflection. Hãy dùng opens cho package entity và giới hạn tới mô-đun ORM nếu có thể. exports không thay thế opens.

**Tình huống 3:** Ứng dụng cần tìm mọi implementation của PaymentProcessor mà không phụ thuộc vào lớp triển khai cụ thể. Cần những khai báo nào?

Trả lời: mô-đun ứng dụng khai báo uses PaymentProcessor; mỗi mô-đun provider khai báo provides PaymentProcessor with Implementation. Các mô-đun provider cũng cần được đưa vào module configuration để ServiceLoader có thể phát hiện chúng.

**Tình huống 4:** Một thư viện xuất hiện trong API public của facade. Khi nào dùng requires transitive?

Trả lời: dùng requires transitive khi người đọc facade cũng cần đọc thư viện đó để sử dụng kiểu hoặc hợp đồng được facade đưa ra. Nếu dependency chỉ là chi tiết nội bộ, dùng requires thông thường.

**Tình huống 5:** Một framework chạy trên classpath cần reflection vào package trong named module. Có thể mở package cho ai?

Trả lời: có thể dùng opens ... to ... nếu framework có tên mô-đun phù hợp; với thư viện trên classpath, đích có thể là ALL-UNNAMED khi dùng tham số --add-opens.

