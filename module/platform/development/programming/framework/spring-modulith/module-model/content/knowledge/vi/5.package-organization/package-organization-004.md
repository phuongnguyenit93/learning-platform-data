# Đặt package theo capability thay vì technical layer

Bài này thuộc chương **Package arrangement** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp tổ chức một ứng dụng Spring Boot thành các application module có ranh giới nghiệp vụ, API công khai và quan hệ phụ thuộc rõ ràng. Cách tổ chức package quyết định những ranh giới đó có dễ nhận ra và dễ kiểm chứng hay không.

Nguyên tắc trọng tâm của bài học là: **đặt package cấp cao theo capability nghiệp vụ, sau đó tổ chức các technical layer bên trong từng capability**. Nhờ vậy, mã nguồn được nhóm theo phần việc mà hệ thống thực hiện thay vì gom tất cả controller, service hoặc repository của toàn ứng dụng vào những khu vực kỹ thuật chung.

## 1. Hai cách tổ chức package

Hãy xét một ứng dụng bán hàng có các chức năng quản lý đơn hàng, kho hàng, khách hàng và thanh toán.

Cách tổ chức theo technical layer thường có dạng:

~~~text
com.acme.shop
├── ShopApplication.java
├── controller
│   ├── OrderController.java
│   ├── InventoryController.java
│   └── CustomerController.java
├── service
│   ├── OrderService.java
│   ├── InventoryService.java
│   └── CustomerService.java
├── repository
│   ├── OrderRepository.java
│   ├── InventoryRepository.java
│   └── CustomerRepository.java
└── entity
    ├── OrderEntity.java
    ├── InventoryEntity.java
    └── CustomerEntity.java
~~~

Cách này cho biết một lớp thuộc tầng kỹ thuật nào, nhưng để hiểu một capability phải đi qua nhiều package. Khi thay đổi quy trình đặt hàng, lập trình viên có thể phải tìm controller trong controller, service trong service, repository trong repository và entity trong entity.

Cách tổ chức theo capability nhóm các thành phần liên quan đến cùng một năng lực nghiệp vụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── OrderSummary.java
│   └── internal
│       ├── web
│       │   └── OrderController.java
│       ├── application
│       │   └── PlaceOrderHandler.java
│       ├── domain
│       │   ├── Order.java
│       │   └── OrderPolicy.java
│       └── persistence
│           └── JpaOrderRepository.java
├── inventory
│   ├── StockAvailability.java
│   └── internal
│       ├── web
│       ├── domain
│       └── persistence
├── customer
│   ├── CustomerProfile.java
│   └── internal
│       ├── web
│       ├── domain
│       └── persistence
└── payment
    ├── PaymentUseCases.java
    └── internal
        ├── web
        ├── domain
        └── integration
~~~

Ở đây, **order**, **inventory**, **customer** và **payment** là các khu vực nghiệp vụ cấp cao. Mỗi khu vực có thể có controller, application service, domain object và repository riêng. Người đọc có thể tìm hầu hết mã nguồn liên quan đến một capability trong cùng một nhánh package.

Hai cách tổ chức không nhất thiết loại trừ mọi yếu tố của nhau. Một capability vẫn có thể chia phần nội bộ thành các package web, application, domain và persistence. Điểm khác biệt là technical layer được đặt bên trong ranh giới capability, thay vì trở thành các package cấp cao dùng chung cho toàn ứng dụng.

## 2. Capability là gì và chọn ranh giới ra sao?

Capability là một năng lực hoặc trách nhiệm nghiệp vụ mà ứng dụng cần thực hiện. Nó mô tả hệ thống làm gì cho nghiệp vụ, thay vì mô tả mã nguồn được viết bằng công nghệ nào.

Trong ví dụ bán hàng:

- **order** chịu trách nhiệm tiếp nhận đơn, áp dụng quy tắc đặt hàng và theo dõi vòng đời đơn.
- **inventory** chịu trách nhiệm về số lượng hàng có thể bán, giữ hàng và cập nhật tồn kho.
- **customer** quản lý hồ sơ và thông tin khách hàng.
- **payment** chịu trách nhiệm khởi tạo, xác nhận và theo dõi thanh toán.

Một capability nên có phạm vi đủ rõ để nhóm có thể giải thích trách nhiệm của nó, đồng thời có quyền sở hữu đối với các quy tắc và dữ liệu liên quan. Nếu một package gom nhiều chức năng không liên quan chỉ vì chúng cùng dùng REST hoặc JPA, đó thường là dấu hiệu của tổ chức theo technical layer.

Không nên tạo capability chỉ từ tên một bảng dữ liệu hoặc một lớp. Ví dụ, package **repository** không phải capability vì nó mô tả cách truy cập dữ liệu. Package **order** có thể là capability nếu nó thực sự sở hữu quy trình và quy tắc nghiệp vụ của đơn hàng.

Ranh giới capability là quyết định thiết kế dựa trên nghiệp vụ và cách hệ thống thay đổi. Spring Modulith giúp biểu diễn và kiểm tra cấu trúc đã chọn; công cụ không tự suy ra ranh giới nghiệp vụ đúng từ tên package.

## 3. Tổ chức capability phù hợp với mô hình application module

Spring Modulith thường nhận diện các application module từ những package con trực tiếp của package gốc ứng dụng. Nếu lớp có **@SpringBootApplication** nằm trong package **com.acme.shop**, các package như **com.acme.shop.order** và **com.acme.shop.inventory** là các module cấp cao được khám phá theo quy ước mặc định.

Điều này tạo ra mối liên hệ trực tiếp giữa cách tổ chức capability và mô hình kiến trúc:

- Package gốc ứng dụng là điểm bắt đầu để khám phá.
- Mỗi package capability trực tiếp bên dưới nó có thể trở thành một application module.
- Package gốc của từng module là giao diện mặc định mà module khác được phép sử dụng.
- Các package con bên trong module là phần nội bộ, trừ khi được công khai có chủ đích bằng named interface.

Vì vậy, cấu trúc như **com.acme.shop.order.internal.persistence** giữ phần lưu trữ bên trong module đơn hàng. Module khác nên gọi chức năng được công khai bởi **order**, thay vì tham chiếu trực tiếp đến repository trong package persistence.

Ví dụ, API mặc định của module đơn hàng có thể cung cấp một hợp đồng:

~~~java
package com.acme.shop.order;

import java.util.UUID;

public interface OrderManagement {

    OrderSummary findOrder(UUID orderId);
}
~~~

Kiểu kết quả thuộc cùng API:

~~~java
package com.acme.shop.order;

import java.util.UUID;

public record OrderSummary(UUID id, String status) {
}
~~~

Phần triển khai có thể nằm trong các package con:

~~~java
package com.acme.shop.order.internal.application;

import com.acme.shop.order.OrderManagement;
import com.acme.shop.order.OrderSummary;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
class DefaultOrderManagement implements OrderManagement {

    private final LoadOrder loadOrder;

    DefaultOrderManagement(LoadOrder loadOrder) {
        this.loadOrder = loadOrder;
    }

    @Override
    public OrderSummary findOrder(UUID orderId) {
        var order = loadOrder.byId(orderId);
        return new OrderSummary(order.id(), order.status());
    }
}
~~~

Đây là ví dụ minh họa cấu trúc và hướng phụ thuộc. Trong ứng dụng thực tế, các lớp triển khai, adapter và cấu hình Spring cần được tổ chức sao cho component scanning và dependency injection hoạt động đúng.

## 4. Đặt technical layer bên trong capability

Tổ chức theo capability không có nghĩa phải bỏ mọi phân lớp kỹ thuật. Khi một capability đủ lớn, các package con có thể chia theo vai trò kỹ thuật để mã nguồn dễ điều hướng.

Một cách chia thường gặp:

| Package con | Trách nhiệm |
|---|---|
| **web** | Controller, request/response model và adapter HTTP của capability. |
| **application** | Use case, handler và điều phối luồng nghiệp vụ. |
| **domain** | Entity nghiệp vụ, value object, domain service và quy tắc nghiệp vụ. |
| **persistence** | Adapter lưu trữ, repository implementation và mapping dữ liệu. |
| **integration** | Adapter kết nối hệ thống bên ngoài hoặc giao thức tích hợp. |

Ví dụ:

~~~text
com.acme.shop.order
├── OrderManagement.java
├── OrderSummary.java
└── internal
    ├── web
    │   ├── OrderController.java
    │   └── CreateOrderRequest.java
    ├── application
    │   ├── PlaceOrderHandler.java
    │   └── LoadOrder.java
    ├── domain
    │   ├── Order.java
    │   └── OrderPolicy.java
    └── persistence
        ├── JpaOrderRepository.java
        └── OrderEntity.java
~~~

Cấu trúc này vừa giữ được khả năng tìm kiếm theo kỹ thuật bên trong capability, vừa tránh việc một lớp của đơn hàng nằm cạnh lớp của thanh toán chỉ vì cả hai cùng là repository.

Không cần tạo đủ mọi package con ngay từ đầu. Một capability nhỏ có thể chỉ cần vài lớp trong package gốc và một package internal. Chỉ thêm web, domain, persistence hoặc integration khi quy mô và trách nhiệm thực tế khiến việc tách chúng có ích. Quá nhiều package rỗng hoặc quá sâu làm tăng chi phí điều hướng mà không tạo thêm ranh giới có ý nghĩa.

## 5. Quan hệ phụ thuộc nên đi giữa các capability

Khi capability được tổ chức thành application module, các phụ thuộc giữa chúng trở nên dễ nhìn hơn. Ví dụ, quy trình đặt hàng có thể cần kiểm tra khả năng cung ứng hàng và thông tin khách hàng:

~~~text
             ┌────────────┐
             │  customer  │
             └─────▲──────┘
                   │
┌─────────┐   ┌────┴────┐   ┌───────────┐
│ payment │◄──│  order  │──►│ inventory │
└─────────┘   └─────────┘   └───────────┘
~~~

Sơ đồ chỉ minh họa một khả năng phụ thuộc trong ví dụ. Hướng phụ thuộc thực tế phải xuất phát từ hợp đồng mà capability cung cấp và quy tắc kiến trúc mà nhóm lựa chọn.

Chẳng hạn, module **order** có thể sử dụng một API do **inventory** công khai:

~~~java
package com.acme.shop.inventory;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Trong phần triển khai use case, đơn hàng phụ thuộc vào hợp đồng đó:

~~~java
package com.acme.shop.order.internal.application;

import com.acme.shop.inventory.StockAvailability;

class PlaceOrderHandler {

    private final StockAvailability stockAvailability;

    PlaceOrderHandler(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    boolean canPlace(String productCode, int quantity) {
        return stockAvailability.hasAvailableStock(productCode, quantity);
    }
}
~~~

Module đơn hàng biết hợp đồng kiểm tra tồn kho, nhưng không cần biết inventory dùng bảng dữ liệu nào hoặc repository nào. Tổ chức package theo capability giúp giữ các chi tiết đó bên trong đúng module sở hữu.

Khi các capability phụ thuộc vào nhau, hãy tránh tạo vòng phụ thuộc. Nếu **order** cần gọi **inventory** và **inventory** lại cần truy cập trực tiếp vào repository nội bộ của **order**, cần xem lại quyền sở hữu nghiệp vụ và hợp đồng phối hợp. Có thể dùng một API phù hợp, một sự kiện nghiệp vụ hoặc điều chỉnh trách nhiệm để hướng phụ thuộc trở nên rõ ràng.

## 6. Những dấu hiệu cho thấy ứng dụng đang tổ chức theo technical layer quá mức

Một số dấu hiệu thường gặp:

- Muốn sửa một capability phải tìm và thay đổi lớp ở nhiều package cấp cao khác nhau.
- Package **service** chứa các lớp thuộc nhiều nghiệp vụ không liên quan và trở thành nơi tập trung mọi logic.
- Package **repository** cho phép nhiều khu vực nghiệp vụ truy cập trực tiếp dữ liệu của nhau.
- Các lớp controller biết quá nhiều về entity và repository của capability khác.
- Không thể trả lời rõ package nào sở hữu một quy tắc nghiệp vụ hoặc một nhóm dữ liệu.
- Thay đổi trong một capability thường gây sửa đổi dây chuyền ở nhiều package kỹ thuật chung.

Những dấu hiệu này không chứng minh mọi package phải được chuyển đổi ngay. Hãy kiểm tra xem sự phân tán đó có làm tăng liên kết và khiến ranh giới trách nhiệm khó duy trì hay không. Với ứng dụng nhỏ, một cấu trúc đơn giản vẫn có thể phù hợp; điều quan trọng là giữ được hướng phụ thuộc và quyền sở hữu rõ ràng khi hệ thống phát triển.

## 7. Tránh các lỗi khi chuyển sang capability-first

**Tạo một capability quá lớn.** Package **business** hoặc **core** chứa hầu hết ứng dụng không tạo ra ranh giới có ích. Hãy chia theo những năng lực có trách nhiệm và quy tắc riêng.

**Tạo capability cho từng lớp hoặc từng bảng.** Một package **orderRepository** hoặc **customerEntity** chỉ đổi tên technical layer thành một cấu trúc khác. Capability cần đại diện cho một trách nhiệm nghiệp vụ.

**Để package common trở thành nơi chia sẻ mọi thứ.** Khi các module đều đưa entity, service và helper vào một package **common**, quyền sở hữu bị mờ và phụ thuộc chéo tăng lên. Chỉ chia sẻ những hợp đồng hoặc khái niệm thực sự ổn định, có chủ sở hữu và mục đích rõ ràng.

**Công khai quá nhiều package con.** Package nội bộ nên được giữ kín theo mặc định. Chỉ tạo named interface khi có một nhóm hợp đồng cần được module khác sử dụng ổn định.

**Đưa toàn bộ cấu hình kỹ thuật vào một module nghiệp vụ.** Các cấu hình ứng dụng dùng chung có thể cần một vị trí phù hợp ở cấp ứng dụng. Tuy nhiên, adapter và quy tắc cấu hình đặc thù cho một capability nên nằm gần capability đó để quyền sở hữu không bị tách rời.

**Chia package quá sâu.** Nhiều tầng thư mục không tự động tạo ra kiến trúc tốt. Hãy chọn cấu trúc nhỏ nhất giúp thể hiện rõ trách nhiệm, API và phần nội bộ.

## 8. Chuyển đổi từ technical layer sang capability theo từng bước

Với một ứng dụng đã có mã nguồn, có thể chuyển đổi dần để giảm rủi ro:

1. **Lập danh sách capability.** Xác định các phần nghiệp vụ như order, inventory, customer và payment dựa trên trách nhiệm thực tế.
2. **Chọn một capability để bắt đầu.** Ưu tiên phần có ranh giới tương đối rõ và ít phụ thuộc chéo.
3. **Nhóm lớp theo quyền sở hữu.** Di chuyển controller, use case, domain object và repository implementation về cùng nhánh capability.
4. **Xác định API công khai.** Giữ lại những hợp đồng mà capability khác cần sử dụng ở package gốc hoặc named interface phù hợp.
5. **Ẩn chi tiết triển khai.** Đưa repository, entity và adapter vào package con nội bộ; cập nhật các nơi đang tham chiếu trực tiếp.
6. **Kiểm tra hướng phụ thuộc.** Loại bỏ truy cập xuyên capability vào package nội bộ và xử lý các vòng phụ thuộc.
7. **Lặp lại với capability tiếp theo.** Giữ các thay đổi nhỏ để dễ review và dễ phát hiện vấn đề.

Sau mỗi bước, hãy bảo đảm ứng dụng vẫn biên dịch và các bài kiểm tra hiện có vẫn chạy. Khi cấu trúc module đã rõ, có thể bổ sung kiểm tra kiến trúc:

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

Đưa kiểm tra này vào CI giúp phát hiện những phụ thuộc làm sai lệch ranh giới module khi có thay đổi mới. Nó hỗ trợ thực thi quy tắc kiến trúc mà nhóm đã chọn, nhưng không thay thế việc đánh giá capability có phản ánh đúng nghiệp vụ hay không.

## Ghi nhớ

Đặt package theo capability giúp cấu trúc mã nguồn phản ánh các năng lực nghiệp vụ của ứng dụng. Trong Spring Modulith, các package capability trực tiếp dưới package gốc có thể trở thành application module; các technical layer như web, application, domain và persistence được tổ chức bên trong từng module để giữ chi tiết triển khai gần nơi sở hữu chúng.

Hãy bắt đầu từ câu hỏi **“Ứng dụng cần thực hiện những năng lực nghiệp vụ nào?”**, rồi xác định API công khai và phụ thuộc giữa các capability. Khi một thay đổi nghiệp vụ chủ yếu diễn ra trong một nhánh package có chủ sở hữu rõ ràng, cấu trúc đó đang hỗ trợ tốt hơn cho modular monolith.
