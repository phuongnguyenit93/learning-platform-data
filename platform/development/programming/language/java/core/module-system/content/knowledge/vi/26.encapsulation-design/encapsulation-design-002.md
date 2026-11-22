# Export tối thiểu cho public surface

## Mục tiêu

Sau bài này, bạn có thể thiết kế ranh giới API của một named module bằng cách export đúng những package cần công khai, phân biệt public Java access với module-level access, dùng qualified export khi cần giới hạn consumer, chọn `requires transitive` khi API công khai phụ thuộc kiểu từ module khác và kiểm tra module descriptor trước khi phát hành.

## 1. Public trong Java chưa chắc đã public giữa các module

Trong Java, từ khóa `public` điều khiển quyền truy cập ở cấp class/member. Với JPMS, một named module còn kiểm soát package nào được đưa ra cho module khác thông qua directive `exports`.

Ví dụ một class có thể được khai báo `public`:

~~~java
package com.acme.billing.internal;

public final class PricingEngine {
    public Money calculate(Order order) {
        // ...
        return Money.zero();
    }
}
~~~

Nhưng nếu package `com.acme.billing.internal` không được export trong `module-info.java`, module khác không thể sử dụng class này chỉ vì class có modifier `public`.

Có hai lớp kiểm soát khác nhau:

- **Java access control**: `public`, `protected`, package-private và `private` quyết định ai có thể truy cập class/member theo quy tắc ngôn ngữ.
- **Module access control**: `exports` quyết định package nào được module khác truy cập thông qua module graph và readability.

Để một module khác dùng public type trong package được export, thông thường cần cả hai điều kiện: module consumer đọc được module sở hữu package và package được export cho consumer đó.

Vì vậy, public surface của một module được hình thành từ các package mà module chủ động export, cùng các public/protected API bên trong những package đó. Đánh dấu class là `public` không tự động đưa nó vào public surface của module.

## 2. `exports` hoạt động ở cấp package

Cú pháp:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Directive này export toàn bộ package `com.acme.billing.api` cho các module khác có readability tới `com.acme.billing`. JPMS không có cú pháp export riêng từng class. Vì vậy, khi một package được export, tất cả public type trong package đó đều có thể trở thành một phần API được consumer sử dụng.

Ví dụ cấu trúc module:

~~~text
com.acme.billing/
  module-info.java
  com/acme/billing/api/
    BillingService.java
    Invoice.java
    PaymentStatus.java
  com/acme/billing/internal/
    PricingEngine.java
    InvoiceRepository.java
  com/acme/billing/adapter/
    SqlInvoiceRepository.java
~~~

Descriptor:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Các class public trong `com.acme.billing.api` có thể được module khác sử dụng nếu consumer đọc module `com.acme.billing`. Các package `internal` và `adapter` không được export nên vẫn được đóng gói ở cấp module.

Đây là lý do nên phân chia package theo ranh giới API và implementation. Nếu API và implementation cùng nằm trong một package được export, các public implementation class cũng sẽ có thể được consumer truy cập.

## 3. Thiết kế package API nhỏ và ổn định

Hãy tạo một package chuyên chứa những kiểu mà consumer thực sự cần:

~~~java
package com.acme.billing.api;

public interface BillingService {
    Invoice createInvoice(OrderRequest request);
}
~~~

~~~java
package com.acme.billing.api;

public record OrderRequest(String customerId, long amountInCents) {
}
~~~

~~~java
package com.acme.billing.api;

public record Invoice(String id, long amountInCents) {
}
~~~

Module descriptor:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Implementation nằm trong package không export:

~~~java
package com.acme.billing.internal;

import com.acme.billing.api.BillingService;
import com.acme.billing.api.Invoice;
import com.acme.billing.api.OrderRequest;

public final class DefaultBillingService implements BillingService {
    @Override
    public Invoice createInvoice(OrderRequest request) {
        // Validate, calculate and persist the invoice.
        return new Invoice("INV-001", request.amountInCents());
    }
}
~~~

Nếu module khác cần tạo service, hãy cung cấp factory hoặc composition root công khai thay vì export toàn bộ package implementation chỉ để consumer có thể gọi constructor nội bộ.

Ví dụ factory API:

~~~java
package com.acme.billing.api;

public final class BillingServices {
    private BillingServices() {
    }

    public static BillingService createDefault() {
        return new com.acme.billing.internal.DefaultBillingService();
    }
}
~~~

Trong thực tế, việc API package tham chiếu trực tiếp implementation package có thể khiến code API phụ thuộc vào chi tiết nội bộ. Có thể đặt factory trong module implementation, dùng service provider hoặc dependency injection nội bộ để giữ package API độc lập hơn. Điều quan trọng là consumer chỉ cần biết hợp đồng ổn định.

## 4. Không export package chỉ vì có class public

Trước khi thêm `exports`, hãy xác định consumer cần kiểu nào và vì sao cần dùng nó.

Ví dụ không nên export cả ba package chỉ vì chúng có public class:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    exports com.acme.billing.internal;
    exports com.acme.billing.adapter;
}
~~~

Nếu consumer chỉ cần `BillingService`, `Invoice` và `OrderRequest`, hai package implementation không nên nằm trong public surface. Export chúng sẽ cho phép consumer phụ thuộc vào class triển khai, repository hoặc adapter cụ thể.

Điều đó tạo ra các ràng buộc khó thay đổi:

- Consumer có thể khởi tạo implementation trực tiếp.
- Consumer có thể gọi method vốn chỉ được dự định dùng nội bộ.
- Việc đổi tên package hoặc thay class triển khai có thể phá vỡ code consumer.
- Các dependency của implementation có thể rò rỉ vào API.
- Module khó thay thế adapter hoặc thay đổi kiến trúc bên trong.

Một package chỉ nên được export khi module muốn cam kết rằng các public type của package đó là điểm tích hợp được hỗ trợ.

## 5. Qualified exports để giới hạn consumer

Nếu một package chỉ dành cho một hoặc vài module cụ thể, dùng qualified export:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    exports com.acme.billing.spi to com.acme.reporting;
}
~~~

Trong ví dụ:

- `com.acme.billing.api` được export không giới hạn target module.
- `com.acme.billing.spi` chỉ được export cho module `com.acme.reporting`.

Module đích vẫn phải có readability tới module nguồn, thường thông qua:

~~~java
module com.acme.reporting {
    requires com.acme.billing;
}
~~~

Qualified export hữu ích khi có một SPI hoặc integration package chỉ dành cho module đồng hành. Nó giúp tránh biến package đó thành API công khai cho mọi consumer.

Nếu package được export cho một target module cụ thể, các module khác không được quyền truy cập public type của package đó chỉ bằng cách thêm `requires`. Cả readability và export target đều phải phù hợp.

Qualified export không phải cơ chế bảo mật thay thế cho việc xác thực hoặc kiểm soát dữ liệu ở runtime. Nó là ranh giới truy cập ở cấp module.

## 6. Public API có tham chiếu kiểu từ module khác

Một quyết định quan trọng là dependency nào xuất hiện trong chữ ký public của API.

Giả sử module `com.acme.money` cung cấp kiểu `Money`:

~~~java
module com.acme.money {
    exports com.acme.money.api;
}
~~~

~~~java
package com.acme.money.api;

public record Money(long cents) {
}
~~~

Module billing dùng kiểu đó trong API:

~~~java
package com.acme.billing.api;

import com.acme.money.api.Money;

public interface BillingService {
    Money totalFor(String customerId);
}
~~~

Descriptor của billing:

~~~java
module com.acme.billing {
    requires transitive com.acme.money;
    exports com.acme.billing.api;
}
~~~

Consumer chỉ cần khai báo:

~~~java
module com.acme.client {
    requires com.acme.billing;
}
~~~

Nhờ `requires transitive com.acme.money`, module đọc `com.acme.billing` cũng có readability tới `com.acme.money`. Consumer có thể sử dụng `Money` trong chữ ký và code của mình mà không phải khai báo thêm `requires com.acme.money`.

Nếu billing chỉ khai báo:

~~~java
requires com.acme.money;
~~~

thì dependency này không được truyền tiếp cho module đọc billing. Consumer có thể cần khai báo `requires com.acme.money` trực tiếp để sử dụng kiểu `Money` trong API.

Quy tắc thực tế: dùng `requires transitive` khi module của bạn công khai kiểu từ dependency đó trong API mà consumer cần đọc. Không dùng `transitive` cho mọi dependency một cách mặc định, vì điều đó làm tăng readability graph của các module phụ thuộc và có thể vô tình mở rộng dependency công khai.

## 7. Phân biệt `exports` với `opens`

Hai directive này phục vụ hai loại truy cập khác nhau:

| Directive | Mục đích | Ví dụ sử dụng |
| --- | --- | --- |
| `exports` | Cho phép module khác truy cập public API trong package | Consumer gọi public service và DTO |
| `opens` | Cho phép deep reflection vào package ở runtime | ORM hoặc serializer truy cập private field |

Ví dụ:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    opens com.acme.billing.persistence to org.example.orm;
}
~~~

Package API được export cho truy cập Java thông thường. Package persistence được mở cho ORM named module để thực hiện deep reflection.

Mở package không làm package trở thành API public để consumer biên dịch phụ thuộc. Export package cũng không tự động cho phép framework truy cập private member bằng reflection sâu. Nếu cần cả hai quyền, phải khai báo cả `exports` và `opens` theo đúng mục đích.

## 8. Public surface ảnh hưởng đến khả năng thay đổi module

Một package được export là cam kết thiết kế. Khi consumer bắt đầu biên dịch và chạy dựa trên public type trong package đó, thay đổi API có thể ảnh hưởng tới các module khác.

Một số nguyên tắc để giảm chi phí bảo trì:

- Giữ public API nhỏ, đặt trong package riêng.
- Ưu tiên interface và kiểu dữ liệu có ý nghĩa nghiệp vụ thay vì expose class triển khai.
- Không để API trả về hoặc nhận tham số là kiểu nằm trong package implementation không export.
- Không expose framework-specific type nếu module không muốn phụ thuộc công khai vào framework đó.
- Dùng qualified export cho SPI nội bộ cần chia sẻ với một nhóm module xác định.
- Dùng `requires transitive` có chủ đích khi kiểu của dependency xuất hiện trong API.
- Xem việc xóa hoặc đổi tên package export là thay đổi có thể phá vỡ consumer.

Nếu cần thay đổi implementation, hãy giữ hợp đồng API ổn định và thay đổi class bên trong module. Đây là một lợi ích lớn của module encapsulation.

## 9. Tránh split package và ranh giới mơ hồ

Một package nên thuộc về một module rõ ràng trong module graph. Tránh đặt các class cùng package name vào nhiều module khác nhau, vì split package làm cho việc phân giải và nạp class trở nên khó dự đoán và thường bị module system từ chối trong cùng configuration.

Ví dụ thiết kế không nên dùng:

~~~text
com.acme.billing.api/
  BillingService.class     (module com.acme.billing.api)
  Invoice.class            (module com.acme.billing.model)
~~~

Hãy gom các kiểu thuộc cùng package vào một module, hoặc đổi package để phản ánh ranh giới thực sự:

~~~text
com.acme.billing.api/
  BillingService.class
  Invoice.class
~~~

Ngoài ra, đừng tạo package `com.acme.billing.internal` trong module khác chỉ để đặt implementation gần tên package API. Hãy chọn package name riêng cho module sở hữu implementation.

## 10. Kiểm tra public surface và dependency

Có thể đọc descriptor của modular JAR:

~~~bash
jar --describe-module --file mods/com.acme.billing.jar
~~~

Kết quả sẽ cho biết module name, các `requires`, `exports`, `opens`, `uses` và `provides` nếu có. Hãy xác nhận chỉ các package dự kiến mới xuất hiện trong phần exports.

Dùng `jdeps` để phân tích dependency của module và API:

~~~bash
jdeps --module-path mods --api-only --module com.acme.billing
~~~

`--api-only` tập trung phân tích các dependency xuất hiện trong public API. Đây là cách hữu ích để phát hiện dependency có thể cần `requires transitive` hoặc dependency implementation đang rò rỉ vào public surface.

Có thể kiểm tra module descriptor và dependency graph bằng:

~~~bash
jdeps --module-path mods --check com.acme.billing
~~~

Các lệnh phân tích giúp tìm dependency và descriptor cần xem lại; quyết định export package vẫn phải dựa trên hợp đồng API mà module muốn hỗ trợ.

## 11. Checklist khi thiết kế exports

1. Liệt kê các package mà consumer thực sự cần dùng.
2. Tách API ổn định khỏi package implementation, adapter và persistence.
3. Export package API bằng `exports`.
4. Dùng qualified export cho package chỉ dành cho module đích cụ thể.
5. Kiểm tra public/protected signature có tham chiếu kiểu từ module khác hay không.
6. Dùng `requires transitive` khi consumer của module cần readability tới dependency xuất hiện trong public API.
7. Dùng `opens` riêng cho deep reflection; không thay thế exports bằng opens.
8. Kiểm tra descriptor bằng `jar --describe-module` và dependency bằng `jdeps`.
9. Biên dịch một consumer module độc lập để xác nhận public surface đủ dùng nhưng không phụ thuộc implementation.
10. Xem mỗi package export là một cam kết API cần quản lý tương thích.

## Ghi nhớ

`exports` là ranh giới public API ở cấp package của named module. Chỉ export package mà consumer cần dùng và module sẵn sàng hỗ trợ lâu dài. Dùng qualified export để giới hạn SPI cho module đích; dùng `requires transitive` khi public API làm lộ kiểu từ dependency mà consumer cần đọc. Giữ implementation trong package không export, và dùng `opens` riêng cho framework cần deep reflection. Public surface nhỏ giúp module giữ quyền thay đổi implementation mà ít ảnh hưởng đến consumer.
