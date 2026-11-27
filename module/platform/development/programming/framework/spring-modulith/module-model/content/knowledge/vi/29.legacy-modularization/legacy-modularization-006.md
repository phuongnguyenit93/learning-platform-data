# Giảm dependency trực tiếp vào internal

Trong một ứng dụng Spring Boot lâu năm, các package thường phát triển theo nhu cầu trước mắt. Một module có thể gọi trực tiếp service, repository hoặc entity nằm sâu bên trong module khác vì các lớp đó đang có sẵn và được khai báo public. Cách làm này giúp hoàn thành chức năng nhanh, nhưng dần khiến module phụ thuộc vào chi tiết triển khai của nhau. Khi một nhóm thay đổi repository hoặc cấu trúc dữ liệu, nhiều module không liên quan cũng phải sửa theo.

Spring Modulith giúp nhận diện và kiểm soát các quan hệ đó. Để hiện đại hóa ứng dụng từng bước, hãy tìm những phụ thuộc xuyên qua package nội bộ, xác định hợp đồng nghiệp vụ mà consumer thực sự cần, rồi chuyển từng consumer sang package gốc hoặc named interface công khai của module sở hữu. Sau mỗi bước, kiểm tra lại kiến trúc để bảo đảm ranh giới được cải thiện mà hành vi nghiệp vụ vẫn ổn định.

## 1. Vì sao dependency trực tiếp vào internal gây khó bảo trì?

Giả sử ứng dụng có hai module orders và billing:

~~~text
com.example
├── orders
│   ├── api
│   │   └── OrderManagement.java
│   └── internal
│       ├── OrderService.java
│       ├── OrderRepository.java
│       └── OrderEntity.java
└── billing
    └── InvoiceService.java
~~~

Nếu InvoiceService import trực tiếp OrderRepository hoặc OrderEntity, module billing đang phụ thuộc vào cách orders lưu trữ và xử lý dữ liệu. Một thay đổi như thay JPA bằng một cơ chế lưu trữ khác có thể buộc billing phải thay đổi dù nghiệp vụ lập hóa đơn không đổi.

Những vấn đề thường xuất hiện khi dependency nội bộ lan rộng:

- **Thay đổi lan truyền:** thay đổi một lớp triển khai kéo theo nhiều module phải sửa và phát hành lại.
- **Ranh giới nghiệp vụ bị mờ:** consumer tự truy vấn repository hoặc tự thực hiện một phần quy tắc thuộc module sở hữu.
- **Khó kiểm thử:** test của consumer phải dựng nhiều chi tiết persistence hoặc mock các lớp nội bộ.
- **Phụ thuộc vòng:** hai module gọi trực tiếp service của nhau và dần không thể thay đổi độc lập.
- **Khó nâng cấp:** nhóm phát triển không thể tái cấu trúc module cung cấp vì không biết có bao nhiêu consumer đang dựa vào implementation.

Một lớp Java được khai báo public có thể được import từ package khác theo quy tắc ngôn ngữ Java. Điều đó chỉ cho biết compiler cho phép tham chiếu; nó không có nghĩa lớp ấy là hợp đồng công khai của application module.

## 2. Nhận diện các điểm phụ thuộc vào internal

Bắt đầu bằng việc tìm các tham chiếu xuyên module. Có thể dùng chức năng Find Usages của IDE hoặc tìm import trong mã nguồn. Ví dụ, nếu module billing tham chiếu module orders, hãy tìm những import có dạng:

~~~java
import com.example.orders.internal.*;
~~~

Không chỉ kiểm tra câu lệnh import. Một consumer có thể phụ thuộc vào kiểu nội bộ thông qua:

- Kiểu tham số hoặc kiểu trả về của phương thức.
- Trường hoặc constructor injection.
- Kiểu generic, superclass hoặc interface được triển khai.
- Annotation hoặc cấu hình tham chiếu đến lớp nội bộ.
- Entity hoặc repository được dùng trong truy vấn trực tiếp.

Lập danh sách theo consumer và provider để xác định nơi cần thay đổi:

| Consumer | Dependency hiện tại | Nhu cầu nghiệp vụ thực tế |
|---|---|---|
| billing | orders.internal.OrderRepository | Lấy thông tin đơn hàng để lập hóa đơn |
| shipping | inventory.internal.StockRepository | Kiểm tra số lượng hàng có thể giao |
| notifications | orders.internal.OrderEntity | Nhận thông tin đơn hàng đã hoàn tất |

Bảng này giúp phân biệt nhu cầu nghiệp vụ với cách consumer đang đáp ứng nhu cầu đó. Ví dụ, shipping cần biết hàng có sẵn hay không; nó không nhất thiết cần biết repository nào truy vấn bảng tồn kho.

## 3. Đưa hợp đồng về module sở hữu

Hãy để module cung cấp chức năng định nghĩa API mô tả thao tác nghiệp vụ mà consumer cần. Ví dụ, module inventory cung cấp interface:

~~~java
package com.example.inventory.api;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
~~~

Đánh dấu package api là named interface trong package-info.java:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.inventory.api;
~~~

Implementation và repository vẫn thuộc nội bộ module:

~~~java
package com.example.inventory.internal;

import com.example.inventory.api.StockAvailability;
import org.springframework.stereotype.Service;

@Service
class StockAvailabilityService implements StockAvailability {

    private final StockRepository repository;

    StockAvailabilityService(StockRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean isAvailable(String sku, int quantity) {
        return repository.availableQuantity(sku) >= quantity;
    }
}
~~~

Module shipping chỉ cần inject hợp đồng:

~~~java
package com.example.shipping;

import com.example.inventory.api.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class ShippingService {

    private final StockAvailability stock;

    public ShippingService(StockAvailability stock) {
        this.stock = stock;
    }

    public void prepare(String sku, int quantity) {
        if (!stock.isAvailable(sku, quantity)) {
            throw new IllegalStateException("Không đủ hàng để giao");
        }

        // Tiếp tục quy trình chuẩn bị giao hàng.
    }
}
~~~

Spring vẫn tìm bean triển khai StockAvailability và inject vào constructor. Consumer không cần biết implementation dùng repository nào, truy vấn dữ liệu ra sao hoặc có cache hay không. Module inventory có thể thay đổi các chi tiết đó mà không buộc shipping thay đổi, miễn là hợp đồng API giữ nguyên.

Nếu API nhỏ và không cần nhóm package riêng, có thể đặt interface trực tiếp trong package gốc com.example.inventory. Package gốc là API mặc định của module. Named interface phù hợp khi muốn công khai một nhóm hợp đồng có tên và kiểm soát phụ thuộc theo nhóm.

## 4. Giới hạn dependency bằng allowedDependencies

Sau khi có API rõ ràng, khai báo module tiêu thụ chỉ được phụ thuộc vào named interface mà nó cần. Trong package-info.java của module shipping:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shipping;
~~~

Cú pháp inventory::api chỉ rõ module đích và named interface được phép sử dụng. Nếu shipping tham chiếu một package khác của inventory mà không được công khai, kiểm tra kiến trúc sẽ phát hiện vi phạm.

Nếu consumer chỉ sử dụng API mặc định ở package gốc, có thể giới hạn theo tên module:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory"
)
package com.example.shipping;
~~~

Khi khai báo allowedDependencies, hãy liệt kê đúng những module mà consumer cần. Tránh thêm một danh sách quá rộng chỉ để làm cho test vượt qua. Danh sách này là tài liệu thực thi được về các quan hệ mà module được phép duy trì.

## 5. Chuyển consumer từng bước mà không cần viết lại toàn hệ thống

Với hệ thống legacy, không nên cố di chuyển mọi lớp cùng lúc. Có thể dùng một lộ trình tăng dần:

1. **Chọn một dependency có phạm vi nhỏ.** Bắt đầu với một consumer và một thao tác nghiệp vụ rõ ràng.
2. **Xác định chủ sở hữu nghiệp vụ.** Quyết định module nào chịu trách nhiệm cho quy tắc và dữ liệu đó.
3. **Thiết kế hợp đồng tối thiểu.** Đưa vào API đúng thao tác và dữ liệu consumer cần, không sao chép toàn bộ repository hoặc entity.
4. **Tạo adapter hoặc facade trong provider.** Adapter gọi implementation hiện có và chuyển kết quả sang kiểu API công khai.
5. **Chuyển consumer sang hợp đồng mới.** Thay import và constructor injection, giữ nguyên kết quả nghiệp vụ.
6. **Kiểm tra hành vi và kiến trúc.** Chạy test liên quan cùng architecture test.
7. **Loại bỏ đường truy cập cũ.** Khi không còn consumer sử dụng, xóa hoặc thu hẹp API nội bộ cũ nếu phù hợp.

Trong giai đoạn chuyển tiếp, có thể giữ một facade tương thích để các consumer cũ di chuyển dần. Facade nên gọi implementation hiện tại và tập trung việc chuyển đổi tại một ranh giới. Tránh để facade trở thành một API thứ hai chứa nhiều logic nghiệp vụ hoặc tiếp tục phơi bày repository và entity.

Ví dụ, nếu nhiều consumer đang dùng repository của orders, có thể tạo OrderLookup trong API package để trả về một kiểu đọc ổn định. Chuyển từng consumer sang OrderLookup, sau đó mới thay đổi hoặc loại bỏ các truy cập repository trực tiếp. Việc chuyển theo từng consumer giúp mỗi thay đổi nhỏ, dễ review và có thể rollback độc lập.

## 6. Không để kiểu nội bộ rò rỉ qua API

Tạo interface công khai nhưng trả về entity nội bộ vẫn khiến consumer phụ thuộc vào chi tiết triển khai. Ví dụ sau chưa tạo ra ranh giới tốt:

~~~java
package com.example.orders.api;

import com.example.orders.internal.OrderEntity;
import java.util.UUID;

public interface OrderLookup {

    OrderEntity findById(UUID id);
}
~~~

Thay vào đó, định nghĩa kiểu kết quả phù hợp với hợp đồng:

~~~java
package com.example.orders.api;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderSummary(
        UUID id,
        String customerReference,
        BigDecimal total
) {}
~~~

~~~java
package com.example.orders.api;

import java.util.Optional;
import java.util.UUID;

public interface OrderLookup {

    Optional<OrderSummary> findSummary(UUID orderId);
}
~~~

Implementation trong orders.internal chuyển đổi entity sang OrderSummary. Consumer chỉ nhận dữ liệu cần thiết, không thể truy cập lazy association hoặc gọi phương thức persistence của entity.

Khi thiết kế hợp đồng, chú ý các kiểu sau:

- **Entity và persistence model:** không trả JPA entity hoặc Hibernate proxy qua ranh giới module.
- **Repository:** không công khai repository chỉ để consumer tự quyết định cách truy vấn dữ liệu.
- **Exception:** dùng lỗi có ý nghĩa nghiệp vụ trong API khi consumer cần xử lý; không để consumer phụ thuộc exception của thư viện persistence.
- **Collection mutable:** trả cấu trúc bất biến hoặc bản sao để consumer không thể sửa trạng thái nội bộ.
- **DTO quá rộng:** chỉ đưa dữ liệu cần thiết cho use case, tránh tạo một object chứa mọi field của entity.

Một API tốt mô tả điều module cung cấp. Nó không mô tả bảng dữ liệu, repository hoặc cách provider triển khai chức năng.

## 7. Xử lý phụ thuộc vòng khi tách internal

Đôi khi consumer truy cập internal vì hai module đã chia sẻ logic qua lại. Ví dụ:

- orders gọi billing để tính trạng thái thanh toán.
- billing lại gọi orders để lấy thông tin đơn hàng.

Đây là dấu hiệu cần xem lại quyền sở hữu nghiệp vụ và hướng phụ thuộc. Có một số cách giải quyết:

- Chuyển quy tắc về module sở hữu dữ liệu hoặc nghiệp vụ đó, rồi cung cấp API một chiều.
- Tạo một hợp đồng nhỏ trong module sở hữu khái niệm chung nếu khái niệm đó thực sự thuộc module ấy.
- Dùng application event khi một module chỉ cần thông báo sự kiện đã xảy ra và không cần kết quả đồng bộ từ consumer.
- Dùng adapter ở biên khi tích hợp một hệ thống hoặc mô hình legacy có thuật ngữ và cấu trúc khác.

Không nên tạo module common hoặc shared rồi chuyển mọi kiểu đang được nhiều nơi sử dụng vào đó. Module dùng chung quá rộng dễ trở thành nơi tập trung dependency và làm mất ý nghĩa của ranh giới nghiệp vụ. Chỉ tách một hợp đồng dùng chung khi có chủ sở hữu rõ ràng và trách nhiệm ổn định.

## 8. Kiểm chứng từng bước bằng Spring Modulith

Tạo architecture test ở source set test:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Test này giúp phát hiện các phụ thuộc không hợp lệ như truy cập package nội bộ, phụ thuộc vòng và vi phạm allowedDependencies. Đưa test vào test suite để mỗi pull request có thay đổi cấu trúc module đều được kiểm tra.

Trong quá trình chuyển đổi, có thể dùng quy trình sau:

| Giai đoạn | Điều cần xác nhận |
|---|---|
| Trước khi refactor | Đã ghi nhận consumer và kiểu nội bộ đang được tham chiếu |
| Sau khi tạo API | Hợp đồng mô tả đúng use case và không lộ entity/repository |
| Sau khi chuyển consumer | Consumer chỉ import package gốc hoặc named interface đã công khai |
| Sau khi giới hạn dependencies | allowedDependencies phản ánh đúng quan hệ được phép |
| Trước khi kết thúc | Architecture test vượt qua và đường truy cập nội bộ cũ đã được loại bỏ hoặc có kế hoạch chuyển tiếp rõ ràng |

Nếu cần xem kết quả xác minh để xử lý có điều kiện, ApplicationModules còn cung cấp detectViolations() và đối tượng Violations. Với kiểm tra thường xuyên trong JUnit, lời gọi verify() thường là cách đơn giản nhất vì test sẽ thất bại ngay khi có vi phạm.

## 9. Ví dụ lộ trình chuyển đổi module inventory

Giả sử shipping đang truy cập StockRepository của inventory để kiểm tra tồn kho. Thay đổi có thể được chia thành các bước độc lập:

**Trước khi chuyển đổi**

~~~java
class ShippingService {

    private final StockRepository repository;

    ShippingService(StockRepository repository) {
        this.repository = repository;
    }

    boolean canShip(String sku, int quantity) {
        return repository.availableQuantity(sku) >= quantity;
    }
}
~~~

**Sau khi chuyển đổi**

~~~java
class ShippingService {

    private final StockAvailability stock;

    ShippingService(StockAvailability stock) {
        this.stock = stock;
    }

    boolean canShip(String sku, int quantity) {
        return stock.isAvailable(sku, quantity);
    }
}
~~~

Module inventory sở hữu cách tính số lượng có thể giao. shipping chỉ sử dụng kết quả qua hợp đồng. Điều này cũng cho phép inventory bổ sung quy tắc giữ hàng, hàng lỗi hoặc tồn kho theo kho mà không phải thay đổi consumer nếu hợp đồng vẫn đáp ứng nhu cầu.

## 10. Bài tập thực hành

1. Chọn một module legacy đang import trực tiếp repository hoặc service từ package internal của module khác.
2. Ghi lại consumer, provider, kiểu được tham chiếu và use case nghiệp vụ thực tế.
3. Tạo một interface hoặc kiểu hợp đồng trong package gốc hoặc named interface của provider.
4. Chuyển implementation cũ vào sau hợp đồng, giữ logic nghiệp vụ tại module sở hữu.
5. Chuyển một consumer sang constructor injection qua API công khai.
6. Nếu cần, khai báo allowedDependencies để giới hạn consumer vào đúng module hoặc named interface.
7. Chạy architecture test và test nghiệp vụ liên quan.
8. Chuyển các consumer còn lại từng bước, rồi loại bỏ các truy cập nội bộ không còn sử dụng.

Sau bài tập, bạn cần giải thích được vì sao một kiểu Java public vẫn có thể là chi tiết nội bộ của application module, cách thiết kế hợp đồng tối thiểu cho consumer, và cách chuyển đổi legacy mà không phải viết lại toàn bộ ứng dụng trong một lần.

## Tài liệu tham khảo

- [Application Modules – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Verifying Application Module Structure – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/verification.html)
- [NamedInterface API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
