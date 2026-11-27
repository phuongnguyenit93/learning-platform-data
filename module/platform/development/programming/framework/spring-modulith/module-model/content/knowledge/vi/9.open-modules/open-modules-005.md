# Open module hữu ích khi di chuyển ứng dụng legacy

Bài này thuộc chương **Open modules** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong một ứng dụng Spring Boot. Khi đưa một ứng dụng legacy vào mô hình module, việc đóng ngay toàn bộ package nội bộ có thể làm lộ ra rất nhiều phụ thuộc chéo cần xử lý cùng lúc.

**Open module** là một lựa chọn chuyển tiếp hữu ích: module vẫn được Spring Modulith nhận diện như một application module, nhưng cho phép module khác phụ thuộc vào các kiểu nằm trong package nội bộ của nó. Nhờ đó, nhóm có thể bắt đầu mô hình hóa kiến trúc hiện tại, sau đó từng bước đưa các phụ thuộc về API công khai và đóng module lại khi sẵn sàng.

## 1. Vấn đề thường gặp trong ứng dụng legacy

Một ứng dụng Spring Boot phát triển lâu năm thường có nhiều lớp được tổ chức theo technical layer hoặc được gọi xuyên package:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderService.java
│   ├── OrderRepository.java
│   ├── OrderEntity.java
│   └── OrderMapper.java
├── inventory
│   ├── InventoryService.java
│   ├── StockRepository.java
│   └── StockEntity.java
└── shipping
    ├── ShippingService.java
    └── ShippingRepository.java
~~~

Theo thời gian, module shipping có thể import trực tiếp `OrderEntity` hoặc `OrderRepository`; inventory có thể gọi một service nội bộ của order; nhiều lớp được dùng chung mà không có hợp đồng rõ ràng.

Nếu áp dụng ngay quy tắc đóng của Spring Modulith, các truy cập vào package nội bộ của module khác có thể trở thành lỗi kiến trúc. Trong một codebase lớn, số lượng lỗi như vậy có thể rất nhiều. Việc sửa tất cả trong một lần vừa tốn công vừa làm tăng rủi ro thay đổi hành vi nghiệp vụ.

Open module giúp nhóm bắt đầu từ cấu trúc hiện hữu, ghi nhận các module và tiếp tục tái cấu trúc theo từng bước có thể kiểm soát.

## 2. Open module là gì?

Theo quy ước mặc định, application module có API công khai ở package gốc và giữ các package con ở phạm vi nội bộ. Module khác chỉ nên phụ thuộc vào kiểu được cung cấp qua API mặc định hoặc named interface.

Một module được khai báo là **OPEN** cho phép các module khác truy cập cả những kiểu nằm trong package con nội bộ của nó. Nói cách khác, module mở rộng bề mặt có thể được phụ thuộc để tương thích với cấu trúc codebase hiện tại.

Có thể đánh dấu module bằng annotation `@ApplicationModule` trong file `package-info.java` của package gốc:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.order;
~~~

Hoặc viết với import để dễ đọc:

~~~java
import org.springframework.modulith.ApplicationModule;

@ApplicationModule(type = ApplicationModule.Type.OPEN)
package com.acme.shop.order;
~~~

Khi đó, các module khác có thể phụ thuộc vào các kiểu trong package con của `com.acme.shop.order`, kể cả các package thường được xem là internal như `order.persistence` hoặc `order.internal`.

Open module vẫn là một application module trong mô hình Spring Modulith. Việc mở module nới lỏng quy tắc đóng gói API của chính module đó; nó không biến package thành một dịch vụ độc lập và cũng không làm mất ý nghĩa của cấu trúc module.

## 3. Open module giải quyết điều gì khi migration?

Giả sử module shipping hiện đang truy cập trực tiếp vào entity của order:

~~~java
package com.acme.shop.shipping;

import com.acme.shop.order.internal.OrderEntity;
import com.acme.shop.order.internal.OrderRepository;

class ShippingService {

    private final OrderRepository orders;

    ShippingService(OrderRepository orders) {
        this.orders = orders;
    }

    OrderEntity loadOrder(String orderId) {
        return orders.findById(orderId);
    }
}
~~~

Nếu order được đóng theo mặc định, việc shipping phụ thuộc vào package nội bộ của order sẽ vi phạm ranh giới module. Trong giai đoạn đầu của migration, nhóm có thể đánh dấu order là OPEN để mô hình kiến trúc chấp nhận những phụ thuộc đang tồn tại:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.order;
~~~

Cách làm này có một số lợi ích:

- **Bắt đầu từ hiện trạng:** nhóm có thể đưa package hiện có vào mô hình module mà chưa cần sửa toàn bộ import xuyên package.
- **Tạo mốc kiến trúc:** application module được nhận diện và có tên rõ ràng trong khi nhóm đang khảo sát các phụ thuộc.
- **Migration theo từng capability:** có thể chọn một nhóm use case hoặc một module để làm sạch trước, thay vì thực hiện thay đổi lớn trên toàn ứng dụng.
- **Giảm rủi ro thay đổi đồng loạt:** mỗi đợt refactor có thể tập trung vào một hợp đồng và một nhóm consumer cụ thể.
- **Giữ được khả năng kiểm tra:** nhóm có thể tiếp tục sử dụng mô hình Spring Modulith để phát hiện các vấn đề kiến trúc khác trong quá trình chuyển đổi.

Open module là một cơ chế hỗ trợ chuyển tiếp. Nếu giữ trạng thái OPEN mãi mãi, nhóm vẫn có thể có cấu trúc module nhưng không tận dụng được đầy đủ lợi ích của việc bảo vệ API công khai.

## 4. OPEN không có nghĩa là bỏ mọi quy tắc kiến trúc

Cần hiểu đúng phạm vi của module mở:

| Quy tắc hoặc đặc điểm | Khi module được đánh dấu OPEN |
|---|---|
| Module được nhận diện từ package | Vẫn được nhận diện như application module. |
| Module khác truy cập package con nội bộ | Được cho phép bởi tính chất OPEN của module. |
| Module có API mặc định | Vẫn có package gốc và các hợp đồng công khai. |
| Named interface | Vẫn có thể được sử dụng để mô tả các hợp đồng cụ thể, nhưng OPEN làm ranh giới nội bộ của module rộng hơn. |
| Vòng phụ thuộc giữa các module | OPEN không phải cách giải quyết vòng phụ thuộc; cần xử lý hướng phụ thuộc riêng. |
| Ranh giới tiến trình hoặc bảo mật | OPEN không tạo ra cách ly runtime hay ranh giới bảo mật. |

Open module nới lỏng quy tắc đóng gói đối với các consumer. Nó không có nghĩa mọi quan hệ phụ thuộc đều tốt, không có nghĩa module nên phụ thuộc ngược lẫn nhau và cũng không phải cơ chế để bỏ qua thiết kế capability.

Nếu một module mở đang tạo vòng phụ thuộc với module khác, nhóm vẫn cần xem lại trách nhiệm và hướng phối hợp. Nếu một module có phụ thuộc không hợp lý về nghiệp vụ, việc đánh dấu OPEN không làm phụ thuộc đó trở nên đúng.

## 5. Migration từng bước từ open module về module đóng

Một chiến lược thực tế là bắt đầu với module OPEN, quan sát các phụ thuộc đang tồn tại, rồi giảm dần bề mặt API được sử dụng.

### Bước 1: Xác định package gốc và module

Chọn package gốc ứng dụng và xác định các package con trực tiếp đại diện cho capability. Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
├── shipping
└── customer
~~~

Đảm bảo các module có tên và trách nhiệm có thể giải thích được. Nếu package hiện tại chưa phản ánh capability, hãy ghi nhận đó là một phần của kế hoạch tái cấu trúc.

### Bước 2: Đánh dấu module legacy là OPEN

Với module có nhiều phụ thuộc nội bộ đang được sử dụng từ bên ngoài, khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.order;
~~~

Mục đích là cho phép mô hình kiến trúc chấp nhận những truy cập hiện tại vào package con của module order trong giai đoạn migration.

Không nhất thiết phải mở tất cả module. Chỉ đánh dấu OPEN cho module có nhu cầu tương thích thực tế. Những module mới hoặc đã có ranh giới tốt có thể tiếp tục dùng quy ước đóng mặc định.

### Bước 3: Thu thập các phụ thuộc xuyên vào nội bộ

Dùng kiểm tra kiến trúc và tìm kiếm import để xác định module nào đang sử dụng package nội bộ của order. Phân loại các phụ thuộc theo nhu cầu:

- Consumer cần gọi một hành vi nghiệp vụ.
- Consumer chỉ cần một dữ liệu kết quả.
- Consumer đang truy cập repository hoặc entity để đọc/ghi dữ liệu.
- Consumer đang phụ thuộc vào một chi tiết kỹ thuật có thể thay đổi.

Mỗi loại cần một cách xử lý khác nhau. Ví dụ, nhu cầu gọi hành vi nên được chuyển thành API/use case; nhu cầu dữ liệu có thể cần một DTO hoặc query contract; truy cập trực tiếp repository thường cần xem lại quyền sở hữu dữ liệu.

### Bước 4: Tạo API công khai theo nhu cầu thực tế

Giả sử shipping chỉ cần mã đơn và trạng thái giao hàng. Thay vì import entity và repository nội bộ, order có thể công khai một hợp đồng nhỏ:

~~~java
package com.acme.shop.order;

public interface OrderShippingDetails {

    ShippingOrder findForShipping(String orderId);

    record ShippingOrder(String orderId, String status) {
    }
}
~~~

Module shipping sử dụng hợp đồng:

~~~java
package com.acme.shop.shipping;

import com.acme.shop.order.OrderShippingDetails;

class ShippingService {

    private final OrderShippingDetails orders;

    ShippingService(OrderShippingDetails orders) {
        this.orders = orders;
    }

    void prepareShipment(String orderId) {
        var order = orders.findForShipping(orderId);
        // Lập kế hoạch giao hàng từ dữ liệu được công khai.
    }
}
~~~

Phần triển khai của `OrderShippingDetails` vẫn có thể sử dụng repository và entity nội bộ. Consumer chỉ biết hợp đồng mà order sở hữu.

### Bước 5: Chuyển consumer sang API công khai

Thực hiện từng consumer một:

1. Xác định kiểu nội bộ mà consumer đang import.
2. Xác định hành vi hoặc dữ liệu consumer thực sự cần.
3. Thiết kế hợp đồng công khai nhỏ, ổn định trong module provider.
4. Cập nhật consumer để sử dụng hợp đồng.
5. Chạy các bài test phù hợp và kiểm tra lại dependency.
6. Gỡ các import trực tiếp vào package nội bộ khi không còn cần thiết.

Giữ thay đổi nhỏ giúp dễ xác định nguyên nhân nếu hành vi thay đổi. Không nên tạo một API khổng lồ chỉ để bao bọc toàn bộ entity hoặc repository hiện có; API nên phản ánh nhu cầu của consumer.

### Bước 6: Đóng module khi đã sẵn sàng

Khi các consumer không còn phụ thuộc vào package nội bộ, bỏ cấu hình OPEN để module quay về quy ước đóng mặc định:

~~~java
package com.acme.shop.order;
~~~

Nếu module cần công khai thêm một package con có chủ đích, hãy đánh dấu package đó bằng `@NamedInterface` và khai báo phụ thuộc cụ thể ở module consumer. Ví dụ, order có thể công khai named interface `shipping`:

~~~java
@org.springframework.modulith.NamedInterface("shipping")
package com.acme.shop.order.shipping;
~~~

Module shipping có thể giới hạn phụ thuộc:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"order::shipping"}
)
package com.acme.shop.shipping;
~~~

Sau khi đóng module, chạy kiểm tra kiến trúc để xác nhận không còn consumer nào truy cập package nội bộ ngoài hợp đồng đã công khai.

## 6. Dùng kiểm tra kiến trúc trong suốt quá trình migration

Có thể đặt kiểm tra Spring Modulith trong test suite:

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

Trong giai đoạn module còn OPEN, kiểm tra vẫn giúp nhóm phát hiện các vấn đề kiến trúc khác mà mô hình đang kiểm soát, chẳng hạn các vòng phụ thuộc. Sau khi đóng module, các truy cập vào package nội bộ của module đó sẽ trở thành vi phạm cần xử lý.

Một vòng lặp migration hữu ích:

~~~text
Đưa module legacy vào mô hình
             |
             v
       Đánh dấu OPEN
             |
             v
   Quan sát dependency hiện tại
             |
             v
    Tạo API theo nhu cầu
             |
             v
  Chuyển từng consumer sang API
             |
             v
    Không còn truy cập nội bộ?
          /       \
        Chưa       Rồi
         |           |
         v           v
    Tiếp tục      Đóng module
    refactor          |
                      v
              Chạy verify() trong CI
~~~

Điểm quan trọng là kiểm tra kiến trúc cần được chạy lặp lại trong quá trình chuyển đổi. Nếu chỉ chạy một lần ở cuối, nhóm có thể phát hiện nhiều vi phạm cùng lúc và khó truy ra thay đổi nào đã tạo ra chúng.

## 7. Rủi ro nếu giữ module OPEN quá lâu

Open module có thể hữu ích trong giai đoạn chuyển đổi, nhưng có một số chi phí cần quản lý:

- **Bề mặt phụ thuộc rộng:** consumer có thể tiếp tục import các kiểu nội bộ, khiến module khó thay đổi.
- **Phụ thuộc vào chi tiết triển khai:** entity, repository hoặc adapter có thể trở thành hợp đồng ngầm mà module khác dựa vào.
- **Khó xác định quyền sở hữu:** nhiều module có thể cùng thao tác dữ liệu hoặc quy tắc mà lẽ ra một module nên kiểm soát.
- **Migration bị trì hoãn:** nếu không có mục tiêu đóng module, trạng thái chuyển tiếp có thể trở thành trạng thái vĩnh viễn.
- **Tăng chi phí refactor:** mỗi consumer mới sử dụng nội bộ sẽ làm tăng số nơi cần cập nhật khi muốn đóng module.

Để tránh những vấn đề đó, hãy ghi nhận lý do mở module, danh sách nhóm phụ thuộc cần xử lý, mục tiêu đóng và người chịu trách nhiệm. Không cần đặt một thời hạn giống nhau cho mọi module; mức độ phức tạp và số consumer sẽ quyết định lộ trình phù hợp.

## 8. Khi nào không nên dùng open module?

Không nên chọn OPEN chỉ để làm cho kiểm tra kiến trúc hết lỗi mà không xem xét nguyên nhân. Trước khi mở module, hãy tự hỏi:

- Có phải module đang được nhận diện từ package chưa phù hợp?
- Có phải các consumer đang truy cập nhầm package nội bộ vì thiếu API?
- Có thể tạo named interface nhỏ cho capability cần thiết không?
- Phụ thuộc chéo có cho thấy ranh giới nghiệp vụ chưa rõ hoặc vòng phụ thuộc không?
- Module đã có ranh giới tốt và có thể giữ quy ước đóng mặc định không?

Nếu một module mới có API rõ ràng, hãy giữ nó đóng ngay từ đầu. Nếu chỉ một nhóm hợp đồng con cần được chia sẻ, named interface thường diễn đạt ý định chính xác hơn việc mở toàn bộ module.

## Ghi nhớ

Open module cho phép module khác truy cập các kiểu trong package con nội bộ của một application module. Đây là công cụ hữu ích khi đưa codebase legacy vào mô hình Spring Modulith mà chưa thể xử lý toàn bộ phụ thuộc chéo ngay lập tức.

Hãy dùng OPEN như một trạng thái chuyển tiếp có mục tiêu: nhận diện module, quan sát dependency, thiết kế API theo nhu cầu consumer, chuyển từng phụ thuộc về hợp đồng công khai rồi đóng module và kiểm chứng lại. Khi kết thúc migration, các module đóng với API rõ ràng sẽ giúp bảo vệ quyền sở hữu và khả năng thay đổi độc lập của từng capability.
