# Chuyển dần sang allowedDependencies

## Vì sao cần chuyển đổi theo từng bước?

Một ứng dụng Spring Boot lâu năm thường có nhiều package phụ thuộc trực tiếp vào nhau. Các lớp nghiệp vụ có thể import repository, entity hoặc service từ package của module khác. Khi bắt đầu áp dụng Spring Modulith, những quan hệ này có thể chưa tuân theo ranh giới module mong muốn.

Nếu lập tức áp dụng danh sách phụ thuộc cho toàn bộ ứng dụng, nhiều vi phạm cũ sẽ xuất hiện cùng lúc. Nhóm phát triển khó phân biệt lỗi kiến trúc mới với những quan hệ đã tồn tại từ trước, đồng thời phải thay đổi quá nhiều phần mã trong một lần.

Spring Modulith cho phép khai báo allowedDependencies trên từng module. Khi một module khai báo danh sách này, mã nguồn bên trong module chỉ được phụ thuộc vào các module hoặc named interface đã liệt kê. Các module chưa khai báo danh sách vẫn giữ cách kiểm tra phụ thuộc mặc định. Vì vậy, có thể chuyển đổi từng module, xử lý một nhóm phụ thuộc, rồi mở rộng dần phạm vi kiểm soát.

Mục tiêu là đưa các quan hệ phụ thuộc hiện có thành hợp đồng rõ ràng, sau đó thu hẹp từng hợp đồng về đúng API công khai.

## Hiểu đúng phạm vi của allowedDependencies

allowedDependencies là danh sách các module mà module đang được khai báo được phép phụ thuộc vào. Quy tắc có hướng: nó kiểm soát các phụ thuộc đi ra từ module được đánh dấu.

Ví dụ, nếu package orders được đánh dấu như sau:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "catalog", "customers" }
)
package com.acme.shop.orders;
~~~

thì mã trong orders chỉ được phụ thuộc vào API được phép của catalog và customers, cùng những kiểu không thuộc application module. Việc một module khác phụ thuộc vào orders được kiểm tra theo metadata của module tiêu thụ đó.

Cần phân biệt ba trạng thái:

| Khai báo | Ý nghĩa |
|---|---|
| Không khai báo allowedDependencies | Không áp dụng allowlist phụ thuộc tường minh cho module này |
| allowedDependencies có tên module hoặc named interface | Chỉ các phụ thuộc được liệt kê mới được phép |
| allowedDependencies là mảng rỗng | Không cho phép module phụ thuộc vào application module khác |

Mảng rỗng không có nghĩa là “chưa biết phụ thuộc nào”. Nó là một quy tắc chặt: module không được phụ thuộc vào module ứng dụng khác. Vì vậy, không nên thêm khai báo rỗng vào module legacy khi chưa xác nhận module đó thực sự độc lập.

Spring Modulith vẫn kiểm tra các quy tắc kiến trúc khác, kể cả khi module chưa khai báo allowlist. Những quy tắc quan trọng gồm không có chu trình phụ thuộc giữa các module và chỉ truy cập các package API được công bố của module khác. allowedDependencies bổ sung một lớp kiểm soát để giới hạn module nào được phép là dependency.

## Đánh giá hiện trạng trước khi thêm allowlist

Bắt đầu bằng việc tạo mô hình module từ lớp ứng dụng và chạy kiểm chứng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Nếu ứng dụng có nhiều vi phạm cũ, có thể thu thập danh sách trước để lập kế hoạch xử lý:

~~~java
var modules = ApplicationModules.of(ShopApplication.class);

modules.detectViolations()
    .forEach(System.out::println);
~~~

Ghi nhận các thông tin sau cho từng quan hệ:

- Module nguồn đang import hoặc gọi module nào?
- Kiểu được tham chiếu nằm ở package gốc, named interface hay package nội bộ?
- Phụ thuộc đó có thực sự cần thiết cho nghiệp vụ không?
- Có thể thay lời gọi trực tiếp bằng API công khai hoặc application event không?
- Module sở hữu kiểu đang bị truy cập có thể công bố một hợp đồng nhỏ hơn không?

Không nên suy ra danh sách allowedDependencies chỉ từ tên package. Hãy dựa vào các phụ thuộc thực tế trong mã nguồn và quyết định quan hệ nào có ý nghĩa nghiệp vụ.

Một bảng kiểm kê ban đầu có thể như sau:

| Module tiêu thụ | Module được sử dụng | Kiểu đang được tham chiếu | Hướng xử lý |
|---|---|---|---|
| orders | catalog | catalog.api.ProductCatalog | Giữ phụ thuộc qua API |
| orders | customers | customers.internal.CustomerEntity | Thay bằng API hoặc DTO công khai |
| billing | payments | payments.api.PaymentResult | Giữ named interface |
| notifications | orders | orders.internal.OrderRepository | Chuyển sang event hoặc API truy vấn |

Bảng này là cơ sở để viết allowlist chính xác và chia công việc thành các thay đổi nhỏ.

## Dùng OPEN như cầu nối tạm thời cho module legacy

Trong hệ thống cũ, một module có thể đang được nhiều package khác truy cập vào các kiểu nằm sâu trong package con. Việc chuyển tất cả consumer sang API công khai có thể cần nhiều đợt triển khai.

Spring Modulith cung cấp kiểu module OPEN để hỗ trợ chuyển đổi dần. Đặt annotation trên package gốc của module legacy:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.catalog;
~~~

Module OPEN cho phép các module khác truy cập những kiểu nội bộ của nó. Các kiểu trong package con cũng được đưa vào giao diện không tên của module, trừ những kiểu đã được gán rõ vào named interface.

Đây là cầu nối tương thích cho codebase đang được chuyển dần sang cấu trúc module. Nó giúp nhóm bắt đầu mô hình hóa module mà chưa phải lập tức di chuyển mọi kiểu đang bị sử dụng từ bên ngoài.

Tuy nhiên, OPEN mở rộng phạm vi API mà module cung cấp. Khi module đã được đóng gói tốt, việc giữ OPEN thường cho thấy ranh giới hoặc cách tổ chức package vẫn còn cần cải thiện. Hãy ghi nhận module OPEN như một hạng mục chuyển đổi có chủ sở hữu và tiêu chí đóng lại.

OPEN và allowedDependencies giải quyết hai câu hỏi khác nhau:

- OPEN quyết định các module khác có thể truy cập những kiểu nào của module này.
- allowedDependencies quyết định module hiện tại được phép phụ thuộc vào những module hoặc named interface nào.

Không dùng OPEN để thay thế allowlist, và không nhầm allowlist của consumer với quyền công bố API của provider.

## Giai đoạn 1: Ghi nhận các phụ thuộc hiện có

Giả sử module orders đang sử dụng hai module catalog và customers. Một số lớp của orders gọi API công khai, nhưng cũng có lớp import trực tiếp entity nội bộ của customers.

~~~java
package com.acme.shop.orders;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.customers.internal.CustomerEntity;
~~~

Trước khi thêm allowedDependencies, hãy xác định các quan hệ cần giữ và những quan hệ cần refactor. Nếu chưa thể đóng ngay module customers vì còn nhiều consumer, có thể tạm thời khai báo customers là OPEN trong khi lập kế hoạch công bố API.

Không thêm một danh sách rộng theo kiểu “cho phép mọi module đang tồn tại”. Hãy kiểm kê chính xác các module mà orders thực sự cần. Danh sách phụ thuộc có ý nghĩa khi nó phản ánh quyết định thiết kế, không chỉ sao chép mọi import hiện tại.

## Giai đoạn 2: Khai báo các phụ thuộc hợp lệ ban đầu

Sau khi xác định orders cần catalog và customers, khai báo allowlist tại package gốc của orders:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "catalog",
        "customers"
    }
)
package com.acme.shop.orders;
~~~

Ở bước này, mục tiêu là khóa phạm vi phụ thuộc giữa các module. Nếu orders còn phụ thuộc trực tiếp vào module khác mà chưa được liệt kê, kiểm chứng sẽ báo vi phạm. Hãy xem đó là tín hiệu để quyết định thêm một dependency có chủ đích hoặc refactor quan hệ không hợp lệ.

Khai báo tên module như catalog cho phép sử dụng package API gốc của module đó. Nếu module cung cấp API ở package con được công bố bằng named interface, hãy khai báo chính xác giao diện đó thay vì mở rộng quyền truy cập không cần thiết.

## Giai đoạn 3: Thu hẹp phụ thuộc vào named interface

Giả sử catalog có package API riêng:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.catalog.api;
~~~

Module orders chỉ cần ProductCatalog và ProductDetails từ named interface này. Hãy thay đổi allowlist:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::api"
)
package com.acme.shop.orders;
~~~

Nếu orders vẫn cần package gốc của catalog cho một API khác, hãy liệt kê cả hai dependency theo đúng nhu cầu:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "catalog",
        "catalog::api"
    }
)
package com.acme.shop.orders;
~~~

Các dạng khai báo thường gặp:

| Giá trị | Phạm vi được phép |
|---|---|
| catalog | Package API gốc của catalog |
| catalog::api | Named interface api |
| catalog::* | Tất cả named interface được khai báo, không bao gồm package gốc |
| catalog::** | Package gốc và tất cả named interface được khai báo |

Chỉ dùng * hoặc ** khi module thực sự cần toàn bộ các giao diện tương ứng. Trong quá trình chuyển đổi, khai báo một named interface cụ thể thường giúp xác định hợp đồng rõ ràng hơn.

## Giai đoạn 4: Refactor consumer khỏi package nội bộ

Khi module customers đã xác định được API phù hợp, tạo một hợp đồng công khai thay cho việc consumer import CustomerEntity.

Ví dụ API:

~~~java
package com.acme.shop.customers.api;

public interface CustomerDirectory {
    CustomerDetails findById(String customerId);
}
~~~

Kiểu dữ liệu công khai:

~~~java
package com.acme.shop.customers.api;

public record CustomerDetails(
    String customerId,
    String displayName,
    String email
) {}
~~~

Công bố package:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.customers.api;
~~~

Trong orders, thay import entity nội bộ bằng API:

~~~java
package com.acme.shop.orders;

import com.acme.shop.customers.api.CustomerDirectory;
import com.acme.shop.customers.api.CustomerDetails;
import org.springframework.stereotype.Service;

@Service
class OrderCustomerService {

    private final CustomerDirectory customers;

    OrderCustomerService(CustomerDirectory customers) {
        this.customers = customers;
    }

    CustomerDetails customerFor(String customerId) {
        return customers.findById(customerId);
    }
}
~~~

Sau đó giới hạn allowlist của orders:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "catalog::api",
        "customers::api"
    }
)
package com.acme.shop.orders;
~~~

Khi consumer không còn tham chiếu các kiểu nội bộ của customers, có thể chuyển customers từ OPEN về CLOSED (hoặc bỏ khai báo OPEN vì CLOSED là mặc định). Hãy chạy kiểm chứng để tìm những consumer khác vẫn còn sử dụng phần triển khai nội bộ trước khi đóng module.

## Giai đoạn 5: Lặp lại theo từng module

Không cần chuyển toàn bộ module trong một lần. Chọn một module có phạm vi vừa phải, hoàn thành các bước:

1. Kiểm kê dependency thực tế của module.
2. Xác định API gốc và named interface cần sử dụng.
3. Khai báo allowedDependencies với các quan hệ hợp lệ.
4. Refactor import nội bộ thành API công khai hoặc event contract.
5. Đóng module provider nếu không còn lý do giữ OPEN.
6. Chạy ApplicationModules.verify() và cập nhật tài liệu kiến trúc.
7. Đánh dấu module đã chuyển đổi và chọn module tiếp theo.

Ví dụ, nhóm có thể chuyển orders trước, sau đó đến billing và notifications. Mỗi module sau khi hoàn tất sẽ có một danh sách phụ thuộc rõ ràng, giúp thay đổi tiếp theo dễ đánh giá hơn.

## Tích hợp verification vào CI

Một test kiến trúc nên chạy trong pipeline CI để ngăn phụ thuộc mới vượt qua allowlist:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesAllowedModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Khi một pull request thêm import từ module mới hoặc truy cập package nội bộ, kiểm chứng sẽ báo lỗi nếu quan hệ đó vi phạm quy tắc hiện tại.

Hãy xử lý thông báo vi phạm theo thứ tự:

- Xác định module chứa mã đang tạo dependency.
- Xác định module đích và package/type bị tham chiếu.
- Nếu quan hệ hợp lệ, công bố API phù hợp và thêm dependency cụ thể.
- Nếu quan hệ không hợp lệ, refactor để loại bỏ phụ thuộc hoặc chuyển tương tác sang event.
- Chạy lại verification và xác nhận allowlist vẫn phản ánh thiết kế mong muốn.

Không sửa allowlist chỉ để làm CI xanh. Mỗi dependency mới cần có lý do nghiệp vụ và một API được công bố phù hợp.

## Theo dõi tiến độ chuyển đổi

Một nhóm có thể theo dõi trạng thái từng module bằng bảng migration đơn giản:

| Module | Trạng thái | Bước tiếp theo |
|---|---|---|
| catalog | OPEN tạm thời | Chuyển consumer khỏi internal, sau đó đóng module |
| customers | OPEN tạm thời | Công bố API và chuyển entity sang nội bộ |
| orders | Có allowedDependencies | Thu hẹp dependency vào named interface |
| billing | Chưa có allowlist | Kiểm kê các phụ thuộc hiện tại |
| notifications | Đã đóng | Giữ verification trong CI |

Đặt tiêu chí kết thúc rõ ràng cho từng module:

- Các consumer chỉ dùng package gốc hoặc named interface đã công bố.
- allowedDependencies liệt kê đúng các module cần thiết.
- Không còn dependency ngoài danh sách.
- Module không cần OPEN nếu đã bảo vệ được phần nội bộ.
- Verification chạy thành công trong CI.

Nếu một module vẫn cần OPEN vì có consumer chưa thể refactor, hãy ghi rõ lý do, người phụ trách và bước tiếp theo. Không coi OPEN là trạng thái hoàn tất của quá trình modularization.

## Những lỗi thường gặp khi chuyển đổi

**Thêm allowlist rỗng cho module còn phụ thuộc.** Mảng rỗng cấm mọi dependency đến application module khác. Hãy kiểm kê trước khi chọn cấu hình này.

**Khai báo dependency trên module provider thay vì consumer.** allowedDependencies kiểm soát các module mà module được đánh dấu có thể sử dụng. Hãy đặt annotation tại package gốc của module chứa mã đang gọi API bên ngoài.

**Chỉ thêm tên module mà không công bố API phù hợp.** allowlist không tự biến package internal thành API. Provider vẫn phải công bố package cần thiết hoặc duy trì OPEN tạm thời trong giai đoạn chuyển đổi.

**Dùng catalog::** hoặc named interface không tồn tại. Tên module và tên named interface phải khớp với mô hình được phát hiện. Dùng cú pháp module::interface và xác nhận interface đó đã được khai báo.

**Dùng wildcard quá rộng.** catalog::* cho phép tất cả named interface, còn catalog::** bao gồm cả package gốc. Chỉ chọn phạm vi này khi consumer thật sự cần.

**Giữ OPEN sau khi đã refactor xong.** Khi không còn consumer cần truy cập nội bộ, đóng module để khôi phục ranh giới bảo vệ.

**Cho rằng allowedDependencies loại bỏ mọi chu trình.** Allowlist kiểm soát dependency được phép; quy tắc không có chu trình vẫn được kiểm tra riêng. Một danh sách hợp lệ không làm cho đồ thị phụ thuộc vòng trở nên hợp lệ.

## Bài tập vận dụng

Một ứng dụng legacy có ba module: orders, customers và payments. Hiện tại orders import CustomerEntity từ customers.internal và PaymentRepository từ payments.internal. Module payments cũng truy cập một số kiểu trong orders.internal.

Hãy lập kế hoạch chuyển đổi:

1. Chạy ApplicationModules.verify() và ghi nhận các dependency hiện có.
2. Tạm đánh dấu customers và payments là OPEN nếu cần giữ tương thích trong lúc refactor.
3. Công bố CustomerDirectory trong customers.api và PaymentOperations trong payments.api.
4. Chuyển orders sang các API công khai, đồng thời chuyển giao tiếp hai chiều không cần kết quả tức thời sang domain event nếu phù hợp.
5. Khai báo allowedDependencies cho orders và payments theo đúng API mà mỗi module cần.
6. Refactor consumer còn lại khỏi các package internal rồi đóng các module đã hoàn tất.
7. Giữ test verification trong CI để ngăn phụ thuộc mới vượt qua allowlist.

Kết quả mong đợi: mỗi module có danh sách dependency được chủ đích hóa; consumer dùng API công khai hoặc named interface; package internal chỉ được sử dụng bên trong module sở hữu; các module đã hoàn tất không còn cần OPEN.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể giải thích allowedDependencies kiểm soát hướng phụ thuộc nào, phân biệt allowlist với module OPEN, kiểm kê dependency của một codebase legacy, công bố named interface, refactor consumer khỏi package internal và chuyển từng module sang danh sách phụ thuộc tường minh mà vẫn giữ verification chạy trong CI.

Tài liệu tham khảo:

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Fundamentals: Open Application Modules and Explicit Dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
