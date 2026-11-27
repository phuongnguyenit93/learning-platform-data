# Đặt quy ước package trước khi bật verification

Bài này thuộc chương **Module detection** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp mô hình hóa các application module trong một ứng dụng Spring Boot, từ đó làm rõ ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package. Trước khi bật kiểm tra kiến trúc, nhóm cần thống nhất cách đặt package để mô hình mà công cụ phát hiện phản ánh đúng cấu trúc mong muốn.

Nếu quy ước package chưa rõ, kết quả verification có thể chỉ ra rất nhiều vấn đề cùng lúc: package technical layer bị nhận diện thành module, module khác truy cập vào package nội bộ, hoặc các phụ thuộc không theo hướng nghiệp vụ. Thống nhất quy ước trước giúp nhóm hiểu mình đang bảo vệ ranh giới nào và sửa lỗi có thứ tự.

## 1. Vì sao cần quy ước trước khi verification?

Spring Modulith khám phá application module dựa trên package gốc của ứng dụng và cấu trúc package bên dưới. Theo chiến lược mặc định, các package con trực tiếp của application base package là các module cấp cao.

Điều đó có nghĩa cấu trúc package đã chứa thông tin kiến trúc. Ví dụ, nếu package gốc là `com.acme.shop`, các package con trực tiếp `order`, `inventory` và `payment` có thể trở thành module. Nếu nhóm đặt `controller`, `service` và `repository` ở cấp đó, mô hình phát hiện sẽ phản ánh các technical layer thay vì capability nghiệp vụ.

Verification có thể phát hiện vi phạm quy tắc, nhưng không tự quyết định cách chia capability đúng. Nhóm cần thống nhất trước:

- Package nào là application base package.
- Package con trực tiếp nào đại diện cho module.
- Mỗi module sở hữu trách nhiệm nghiệp vụ nào.
- Phần nào là API công khai và phần nào là nội bộ.
- Module nào được phép phụ thuộc vào module hoặc named interface nào.
- Những quy tắc nào sẽ được kiểm tra tự động.

Khi những quyết định này rõ ràng, verification trở thành công cụ thực thi quy ước của nhóm thay vì một danh sách lỗi khó giải thích.

## 2. Chọn application base package

Đặt lớp có `@SpringBootApplication` trong package gốc bao trùm các capability của ứng dụng.

Ví dụ:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Trong ví dụ này, `com.acme.shop` là application base package. Khi tạo mô hình:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

Spring Modulith sử dụng lớp ứng dụng làm điểm bắt đầu để khám phá module. Vì vậy, hãy thống nhất vị trí lớp ứng dụng và tránh di chuyển nó tùy tiện sau khi đã tổ chức package.

Thay đổi package của lớp `@SpringBootApplication` có thể ảnh hưởng đến phạm vi component scanning mặc định của Spring Boot cũng như phạm vi khám phá module. Khi thay đổi package gốc, cần kiểm tra cả việc tìm bean và mô hình kiến trúc.

## 3. Đặt package con trực tiếp theo capability

Dưới application base package, dùng package con trực tiếp cho các năng lực nghiệp vụ hoặc capability chính.

Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
├── customer
├── payment
└── shipping
~~~

Theo chiến lược mặc định, các package `order`, `inventory`, `customer`, `payment` và `shipping` là các ứng viên application module.

Nên chọn tên dựa trên trách nhiệm mà module sở hữu:

| Tên package | Trách nhiệm ví dụ |
|---|---|
| `order` | Vòng đời đơn hàng, xác nhận và hủy đơn. |
| `inventory` | Tồn kho, khả năng cung ứng và giữ hàng. |
| `customer` | Hồ sơ khách hàng và thông tin liên hệ. |
| `payment` | Yêu cầu thanh toán, xác nhận và hoàn tiền. |
| `shipping` | Lập kế hoạch và theo dõi giao hàng. |

Tên package là quy ước của nhóm, không phải từ khóa bắt buộc của Spring Modulith. Tuy nhiên, tên nên nhất quán, ngắn gọn và thể hiện capability để người đọc có thể đoán trách nhiệm mà không phải mở từng lớp.

## 4. Không đặt technical layer ở cấp module

Tránh tổ chức các package cấp cao theo framework hoặc vai trò kỹ thuật nếu mục tiêu là phát hiện module theo capability.

Cấu trúc dễ gây nhầm lẫn:

~~~text
com.acme.shop
├── ShopApplication.java
├── controller
├── service
├── repository
├── entity
└── config
~~~

Với chiến lược mặc định, các package con trực tiếp `controller`, `service`, `repository`, `entity` và `config` có thể được nhận diện như module. Cấu trúc này khiến ranh giới module đi theo kỹ thuật thay vì nghiệp vụ.

Cấu trúc theo capability:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       ├── web
│       ├── application
│       ├── domain
│       └── persistence
├── inventory
│   ├── StockAvailability.java
│   └── internal
│       ├── web
│       ├── domain
│       └── persistence
└── payment
    ├── PaymentUseCases.java
    └── internal
        ├── web
        ├── application
        └── integration
~~~

Technical layer vẫn có thể tồn tại, nhưng nằm bên trong module sở hữu capability đó. Một thay đổi về quy trình đặt hàng khi ấy chủ yếu diễn ra trong nhánh `order`, và các chi tiết triển khai không bị gom chung với module khác chỉ vì chúng cùng dùng JPA hoặc HTTP.

Không cần tạo mọi package con ngay từ đầu. Chỉ thêm `web`, `application`, `domain` hoặc `persistence` khi quy mô và trách nhiệm của module cần chúng.

## 5. Thống nhất quy ước API công khai và package nội bộ

Sau khi xác định module base package, hãy thống nhất cách công khai hợp đồng.

Theo quy ước mặc định:

- Package gốc của module là API mặc định (unnamed interface).
- Package con của module thuộc phần nội bộ.
- Package con chỉ trở thành API công khai khi được đánh dấu rõ ràng bằng `@NamedInterface`.

Ví dụ:

~~~text
com.acme.shop.inventory
├── StockAvailability.java
├── reservation
│   ├── package-info.java
│   └── StockReservation.java
└── internal
    ├── persistence
    └── policy
~~~

Hợp đồng ở package gốc có thể được module khác sử dụng qua API mặc định:

~~~java
package com.acme.shop.inventory;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Nếu muốn công khai capability reservation trong package con, khai báo trong `package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("reservation")
package com.acme.shop.inventory.reservation;
~~~

Nhóm nên thống nhất rằng repository, entity, mapper và adapter thuộc package nội bộ trừ khi có lý do kiến trúc rõ ràng để công khai. Không nên để một lớp có modifier `public` đồng nghĩa với việc mọi module khác được phép phụ thuộc vào nó.

## 6. Đặt quy ước tên package và cấu trúc nội bộ

Một bộ quy ước ngắn gọn giúp codebase nhất quán:

| Phạm vi | Quy ước đề xuất | Ví dụ |
|---|---|---|
| Application base package | Tên miền gốc của ứng dụng | `com.acme.shop` |
| Module base package | Tên capability, viết thường | `com.acme.shop.order` |
| Package nội bộ | Tên vai trò bên trong capability | `order.internal.persistence` |
| Named interface | Tên capability được công khai | `inventory::availability` |
| Package metadata | Dùng `package-info.java` ở package cần khai báo | `order/package-info.java` |

Đây là quy ước đặt tên để nhóm áp dụng, không phải tất cả đều là giới hạn cú pháp của framework.

Một số nguyên tắc bổ sung:

- Dùng chữ thường cho tên package theo quy ước Java.
- Tránh tên mơ hồ như `misc`, `stuff`, `common2` hoặc `utils` nếu không có trách nhiệm rõ.
- Tránh tạo module chỉ vì một technical layer cần được gom lại.
- Không chia một capability thành nhiều package con trực tiếp nếu chúng vẫn cùng một quyền sở hữu nghiệp vụ và không có lý do để thành module riêng.
- Đặt package theo một quy tắc nhất quán giữa các capability.
- Giữ package Java và cấu trúc thư mục tương ứng nhất quán để việc điều hướng và review dễ dàng.

## 7. Thống nhất quy tắc phụ thuộc giữa các module

Khi module đã được nhận diện, nhóm cần quyết định hướng phụ thuộc hợp lệ. Ví dụ, order có thể sử dụng API availability của inventory và API customer:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"inventory::availability", "customer"}
)
package com.acme.shop.order;
~~~

Trong ví dụ này, `inventory::availability` là named interface được inventory công khai; `customer` là API mặc định của module customer.

Hãy khai báo dependency ở package gốc của module sử dụng. Tên module và named interface phải khớp với cấu trúc và metadata đã thống nhất.

Trước khi bật verification, nên thống nhất các câu hỏi:

- Module nào sở hữu dữ liệu và quy tắc nghiệp vụ?
- Module nào được gọi API của module nào?
- Có dependency nào đang đi ngược chiều trách nhiệm không?
- Có vòng phụ thuộc giữa các module không?
- Consumer có đang import package nội bộ của provider không?
- Có hợp đồng nào nên trở thành named interface để giới hạn bề mặt API không?

Không nên thêm mọi module vào danh sách allowed dependencies chỉ để làm kiểm tra qua. Mỗi dependency cần có lý do nghiệp vụ hoặc kiến trúc có thể giải thích.

## 8. Ghi lại quy ước bằng package metadata khi cần

Spring Modulith cho phép khai báo metadata của module trong `package-info.java`. Ví dụ, module order có thể khai báo các phụ thuộc được phép:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory::availability",
        "customer"
    }
)
package com.acme.shop.order;
~~~

Package cung cấp named interface có thể khai báo:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Các khai báo này giúp ý định kiến trúc nằm gần package mà chúng mô tả. Khi review, nhóm có thể xem ngay module công khai gì và module được phép phụ thuộc vào đâu.

Không cần thêm annotation cho mọi package. Hãy dùng metadata ở nơi cần thể hiện ranh giới, named interface hoặc quy tắc phụ thuộc rõ ràng.

## 9. Lộ trình chuẩn bị trước khi bật verification

Một trình tự thực tế giúp tránh bật kiểm tra khi cả nhóm còn chưa thống nhất mô hình:

1. **Chốt package gốc ứng dụng.** Xác định lớp `@SpringBootApplication` và application base package.
2. **Liệt kê capability.** Viết ra các module cấp cao dự kiến như order, inventory, customer và payment.
3. **Đối chiếu cây package hiện tại.** Tìm package technical layer đang nằm trực tiếp dưới package gốc và xác định cách tái cấu trúc.
4. **Chốt quyền sở hữu.** Xác định module nào sở hữu quy tắc và dữ liệu của từng capability.
5. **Chốt bề mặt API.** Xác định kiểu ở package gốc và package con nào cần công khai bằng named interface.
6. **Chốt hướng phụ thuộc.** Ghi lại các quan hệ hợp lệ và lý do của chúng.
7. **Chuyển đổi các import xuyên package.** Ưu tiên các phụ thuộc vào entity, repository hoặc service nội bộ.
8. **Thêm metadata cần thiết.** Dùng `@ApplicationModule` và `@NamedInterface` ở đúng package.
9. **Bật kiểm tra trong test.** Thêm bài kiểm tra `ApplicationModules.verify()` và xử lý các vi phạm có ý nghĩa.
10. **Đưa vào CI.** Chạy kiểm tra cùng bộ test để các thay đổi mới tiếp tục tuân thủ quy ước.

Nếu codebase legacy còn nhiều phụ thuộc nội bộ, có thể thực hiện theo từng module. Điều quan trọng là có kế hoạch xử lý các phụ thuộc đang tồn tại và tránh để trạng thái chuyển tiếp trở thành quy ước lâu dài.

## 10. Bật verification sau khi quy ước đã rõ

Khi cấu trúc và quy tắc đã được thống nhất, thêm bài kiểm tra kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Bài kiểm tra này yêu cầu Spring Modulith xây dựng mô hình và xác minh các quy tắc kiến trúc mà mô hình hỗ trợ, chẳng hạn phụ thuộc vào package nội bộ, dependency không được phép và vòng phụ thuộc.

Khi test thất bại, hãy phân loại vấn đề trước khi sửa:

- **Sai cách phát hiện:** package cấp cao không đại diện cho module mong muốn.
- **Sai bề mặt API:** consumer truy cập package con nội bộ.
- **Sai dependency:** module sử dụng một module hoặc named interface chưa được cho phép.
- **Sai hướng kiến trúc:** các module phụ thuộc vòng hoặc quyền sở hữu chưa rõ.

Không nên xử lý mọi lỗi bằng cách mở module hoặc nới lỏng dependency. Hãy sửa quy ước hoặc hợp đồng khi mô hình hiện tại chưa phản ánh đúng ý định thiết kế.

## 11. Checklist quy ước package của nhóm

Trước khi đưa verification vào CI, hãy có câu trả lời cho từng mục:

- [ ] Lớp `@SpringBootApplication` nằm ở package gốc đã thống nhất.
- [ ] Package con trực tiếp được đặt theo capability, không theo technical layer.
- [ ] Mỗi application module có trách nhiệm và chủ sở hữu rõ.
- [ ] Package gốc module là nơi đặt API mặc định.
- [ ] Package con được giữ nội bộ trừ khi có named interface rõ ràng.
- [ ] Tên named interface mô tả capability được công khai.
- [ ] Các dependency được phép có lý do và hướng rõ ràng.
- [ ] Không có vòng phụ thuộc chưa được giải quyết.
- [ ] Các phụ thuộc vào entity, repository hoặc service nội bộ đã được xem xét.
- [ ] Bài kiểm tra kiến trúc chạy được trong môi trường test và CI.

Checklist này là công cụ trao đổi trong nhóm. Nó không thay thế kết quả của Spring Modulith hoặc việc review nghiệp vụ, nhưng giúp bảo đảm những người cùng phát triển đang áp dụng một bộ quy ước nhất quán.

## Ghi nhớ

Trước khi bật verification, hãy thống nhất application base package, package capability cấp cao, API công khai, phần nội bộ và hướng phụ thuộc giữa các module. Với chiến lược mặc định, package con trực tiếp của package gốc ứng dụng trở thành application module; vì vậy, tên và vị trí package quyết định mô hình mà Spring Modulith khám phá.

Khi quy ước đã rõ, dùng `@NamedInterface` và `@ApplicationModule` để ghi lại hợp đồng cần thiết, sau đó chạy `ApplicationModules.verify()` trong test và CI. Verification khi ấy trở thành cơ chế bảo vệ kiến trúc mà nhóm đã chủ động thiết kế.
