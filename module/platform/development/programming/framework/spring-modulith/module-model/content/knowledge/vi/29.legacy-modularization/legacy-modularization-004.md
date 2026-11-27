# Đưa API ra root package từng bước

Khi áp dụng Spring Modulith vào một ứng dụng Spring Boot cũ, nhiều module có thể đang gọi trực tiếp service, repository hoặc class nằm sâu trong package của nhau. Nếu lập tức đóng tất cả module và chỉ cho phép truy cập root package, `ApplicationModules.verify()` có thể báo hàng loạt vi phạm. Việc sửa tất cả trong một lần thường quá rủi ro vì các class đó đang được nhiều luồng nghiệp vụ sử dụng.

Spring Modulith hỗ trợ `ApplicationModule.Type.OPEN` để đưa một module legacy vào mô hình trong giai đoạn chuyển đổi. Module mở tạm thời cho phép các module khác tiếp tục truy cập type trong package con. Nhóm có thể lần lượt đưa các hợp đồng cần công bố lên root package, chuyển consumer sang hợp đồng mới, giữ implementation ở package con và cuối cùng đóng module lại để bật kiểm tra boundary đầy đủ.

Bài học này trình bày lộ trình đó theo từng bước, từ khảo sát dependency hiện tại đến khi module chuyển từ `OPEN` sang `CLOSED`.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao module legacy có thể cần giai đoạn chuyển đổi ở trạng thái `OPEN`.
- Bật `@ApplicationModule(type = Type.OPEN)` cho module đang được modularize.
- Xác định các type bên ngoài đang phụ thuộc vào package con của module.
- Đưa facade, interface và kiểu dữ liệu hợp đồng cần thiết ra root package.
- Chuyển consumer từng bước sang API mới mà không phải di chuyển toàn bộ implementation.
- Giữ service triển khai, repository và adapter trong package con.
- Đóng module bằng `Type.CLOSED` sau khi các dependency bên ngoài đã đi qua API được công bố.
- Hiểu giới hạn của verification trong thời gian module còn mở và tránh duy trì trạng thái chuyển tiếp vô thời hạn.

## Root package là API mặc định

Giả sử application class nằm trong `com.acme`. Theo quy ước mặc định, mỗi package con trực tiếp là một application module:

```text
com.acme
├── Application.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── JpaOrderRepository.java
└── shipping
    └── ShippingService.java
```

Trong ví dụ này:

- `com.acme.orders` là base package của module `orders`.
- Root package `com.acme.orders` là API mặc định mà module khác được phép tham chiếu. Đây là root của module `orders`, không phải application root `com.acme`.
- Các package con như `com.acme.orders.internal` là implementation nội bộ.
- `com.acme.shipping` là module tiêu thụ API của `orders`.

Một type trong package con có thể phải khai báo `public` để các class khác trong module sử dụng. Java compiler không biết rằng type đó là internal theo quy tắc Spring Modulith. Spring Modulith bổ sung kiểm tra kiến trúc để ngăn module khác phụ thuộc vào type nội bộ khi module ở trạng thái đóng.

Ví dụ, `ShippingService` không nên import `JpaOrderRepository` hoặc một service nội bộ của `orders`. Nó nên phụ thuộc vào một hợp đồng nghiệp vụ được công bố ở root package, chẳng hạn `OrderLookup` hoặc `OrderManagement`.

## Vì sao cần chuyển đổi theo từng bước?

Một ứng dụng legacy thường có lịch sử package không tuân theo module boundary. Consumer có thể đang sử dụng:

- Service triển khai trong package `service` hoặc `impl`.
- Repository hoặc entity trong package `persistence`.
- Helper trong package `common` hoặc `internal`.
- DTO được đặt cùng adapter HTTP hoặc database.
- Các class có tên kỹ thuật nhưng đang được nhiều module dùng như API ngầm.

Đóng module ngay lập tức sẽ biến tất cả tham chiếu đó thành lỗi kiến trúc cùng lúc. Mỗi tham chiếu cần được hiểu về nghiệp vụ trước khi quyết định đưa type nào ra API, chuyển trách nhiệm hay thay bằng event.

Lộ trình chuyển đổi nên có những mốc rõ ràng:

1. Đưa module legacy vào mô hình và tạm thời mở module để không buộc sửa mọi consumer cùng lúc.
2. Lập danh sách các type bên ngoài đang sử dụng trong module.
3. Chọn hợp đồng nghiệp vụ ổn định và đưa chúng vào root package.
4. Chuyển từng consumer sang hợp đồng mới.
5. Kiểm tra không còn dependency ngoài vào package con.
6. Đóng module và để verification thực thi boundary.

Đây là quá trình thay đổi hợp đồng và dependency từng bước. Có thể giữ implementation hiện tại trong lúc chuyển consumer, miễn là API mới trở thành lối vào được kiểm soát.

## Bước 1: Đưa module legacy vào mô hình ở trạng thái OPEN

Đặt `@ApplicationModule(type = Type.OPEN)` trong `package-info.java` của root package module:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.orders;
```

Với Kotlin hoặc trường hợp dùng type metadata thay cho `package-info.java`:

```kotlin
package com.acme.orders

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(type = ApplicationModule.Type.OPEN)
class ModuleMetadata
```

Module `OPEN` cho phép các module khác truy cập các type nội bộ của nó. Các type trong package con cũng được đưa vào unnamed named interface, trừ những type được gán rõ ràng vào named interface khác.

Điều này giúp đưa module legacy vào mô hình mà chưa phải di chuyển toàn bộ API ngay. Nhóm có thể chạy các kiểm tra khác và bắt đầu ghi nhận module dependency trong lúc chuẩn bị chuyển đổi.

**Giới hạn quan trọng:** module `OPEN` không thực thi ranh giới nội bộ như module `CLOSED`. Theo API `ApplicationModule.Type`, module mở cũng bị loại khỏi thuật toán phát hiện dependency cycle. Vì vậy, một lần `verify()` thành công trong giai đoạn này không chứng minh module đã được đóng gói đúng. Hãy coi `OPEN` là trạng thái chuyển tiếp có kế hoạch kết thúc.

## Bước 2: Lập danh sách dependency đang đi vào package con

Trước khi di chuyển type, cần hiểu module khác đang dùng gì và vì sao. Ví dụ cấu trúc legacy:

```text
com.acme.orders
├── service
│   └── DefaultOrderService.java
├── persistence
│   ├── OrderRepository.java
│   └── OrderEntity.java
├── pricing
│   └── PricingPolicy.java
└── web
    └── OrderResponseMapper.java
```

Các module khác có thể đang import trực tiếp nhiều type trong những package này. Phân loại mỗi tham chiếu trước khi quyết định API:

| Type đang được sử dụng | Nhu cầu của consumer | Hướng xử lý |
|---|---|---|
| `DefaultOrderService` | Tạo hoặc hủy đơn hàng | Công bố interface use case như `OrderManagement` |
| `OrderRepository` | Đọc dữ liệu đơn hàng | Công bố query API nghiệp vụ, giữ repository nội bộ |
| `OrderEntity` | Hiển thị trạng thái đơn | Trả về DTO hoặc read model ổn định |
| `PricingPolicy` | Mở rộng quy tắc tính giá | Xác định đây là API, SPI hay logic nội bộ |
| `OrderResponseMapper` | Chuyển entity sang HTTP response | Đưa mapper về module sở hữu adapter hoặc công bố dữ liệu cần thiết thay vì mapper |

Hãy tìm cả dependency trực tiếp và gián tiếp:

- Import type từ package con.
- Constructor injection hoặc field injection của class nội bộ.
- Generic type, superclass, interface và method signature làm lộ type nội bộ.
- Event listener hoặc configuration property phụ thuộc vào module legacy.
- Test fixture dùng trực tiếp repository hoặc entity từ module khác.

Không phải type nào đang được import cũng nên đưa nguyên trạng ra API. Một repository, entity hoặc mapper có thể chỉ đang bị sử dụng vì trước đây chưa có hợp đồng phù hợp.

## Bước 3: Đưa facade hoặc interface nghiệp vụ ra root package

Tạo hợp đồng ở root package thể hiện khả năng mà module cam kết cung cấp. Ví dụ:

```java
package com.acme.orders;

import java.util.UUID;

public interface OrderManagement {

    UUID placeOrder(PlaceOrderCommand command);

    void cancelOrder(UUID orderId);
}
```

Các command, result hoặc value object xuất hiện trong chữ ký API cũng thuộc hợp đồng công khai. Đặt chúng ở root package hoặc một named interface được công bố có chủ đích:

```java
package com.acme.orders;

import java.util.UUID;

public record PlaceOrderCommand(UUID customerId) {}
```

Implementation cũ có thể tiếp tục nằm trong package con và triển khai interface mới:

```java
package com.acme.orders.service;

import java.util.UUID;

import com.acme.orders.OrderManagement;
import com.acme.orders.PlaceOrderCommand;
import com.acme.orders.persistence.OrderEntity;
import com.acme.orders.persistence.OrderRepository;
import org.springframework.stereotype.Service;

@Service
class DefaultOrderService implements OrderManagement {

    private final OrderRepository repository;

    DefaultOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public UUID placeOrder(PlaceOrderCommand command) {
        // Giữ lại và tái sử dụng logic legacy phù hợp.
        return repository.save(OrderEntity.from(command)).getId();
    }

    @Override
    public void cancelOrder(UUID orderId) {
        // Điều phối logic hủy đơn hiện có.
    }
}
```

Facade hoặc interface ở root package trở thành điểm vào công khai. Implementation có thể được tái cấu trúc sau, từng phần, mà consumer không cần biết class cụ thể.

### Đừng đưa implementation lên root package

Mục tiêu là đưa hợp đồng ra root package, không phải chuyển toàn bộ service, repository và adapter ra đó. Root package nên chứa những type mà module chủ động cam kết cung cấp:

- Interface mô tả use case hoặc capability.
- Command, query và result DTO cần cho hợp đồng.
- Value object ổn định có ý nghĩa với consumer.
- Event type mà module công bố.

Các thành phần sau thường nên ở package con:

- Service triển khai interface.
- Repository và persistence adapter.
- JPA entity và mapper database.
- HTTP controller, client và integration adapter.
- Helper hoặc utility chỉ phục vụ implementation.

Nếu API cần công bố thêm một nhóm type nằm trong package con, hãy cân nhắc `@NamedInterface` với tên và mục đích rõ ràng. Không nên mở cả package chỉ vì một type cần được sử dụng.

## Bước 4: Chuyển từng consumer sang API mới

Trước khi chuyển, consumer có thể inject implementation cụ thể:

```java
package com.acme.shipping;

import com.acme.orders.service.DefaultOrderService;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final DefaultOrderService orders;

    ShippingService(DefaultOrderService orders) {
        this.orders = orders;
    }
}
```

Sau khi có API root package, thay dependency bằng interface:

```java
package com.acme.shipping;

import com.acme.orders.OrderManagement;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final OrderManagement orders;

    ShippingService(OrderManagement orders) {
        this.orders = orders;
    }
}
```

Consumer không còn phụ thuộc vào package `service` hoặc class triển khai. Spring vẫn inject bean `DefaultOrderService` vì bean đó implement `OrderManagement`.

Chuyển theo từng consumer giúp pull request nhỏ và dễ review. Với mỗi consumer:

1. Xác định use case thực sự cần từ module legacy.
2. Thêm hoặc điều chỉnh method trong public interface.
3. Thay import implementation bằng import API root package.
4. Bỏ các tham chiếu trực tiếp đến repository, entity hoặc mapper nội bộ.
5. Cập nhật test để kiểm tra qua hợp đồng công khai.
6. Chạy model test và test runtime liên quan trong quy trình của dự án.

Nếu consumer cần nhiều thao tác dữ liệu, hãy thiết kế một query API hoặc read model phù hợp. Đừng công bố repository chỉ để tránh viết facade.

## Bước 5: Xử lý type chưa thể chuyển ngay

Không phải dependency legacy nào cũng có thể thay bằng root API ngay. Có một số trường hợp cần lựa chọn riêng:

**Một extension point thực sự là API.** Nếu module cho phép module khác cung cấp chính sách hoặc adapter, đặt SPI trong package riêng và đánh dấu bằng `@NamedInterface("spi")`. Consumer khai báo dependency `orders :: spi`.

**Một event là hợp đồng giao tiếp.** Đưa event type vào package `events` và công bố named interface. Producer không cần biết listener thuộc module nào.

**Một type chỉ được dùng để đọc dữ liệu.** Thay entity hoặc repository bằng query service trả về DTO/read model. Consumer không cần biết cách persistence được tổ chức.

**Một dependency cần thêm thời gian chuyển đổi.** Giữ module `OPEN` trong thời gian giới hạn, ghi lại consumer còn lại và người phụ trách. Không tạo exclusion rộng hoặc chuyển mọi package con thành API lâu dài chỉ để pipeline xanh.

Ví dụ khai báo named interface cho SPI:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.orders.spi;
```

Consumer có thể giới hạn dependency:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shipping;
```

Named interface là một lựa chọn công bố có chủ đích. Nó khác với việc để module `OPEN`, trong đó các package con được mở rộng vào unnamed interface.

## Bước 6: Theo dõi tiến độ khi module còn OPEN

Trong thời gian module mở, Spring Modulith chưa thể chặn mọi tham chiếu đến package con. Vì vậy, nhóm cần theo dõi migration bằng những bằng chứng khác:

- Tìm import từ module ngoài vào các package con của module đang mở.
- Review diff để không tạo thêm dependency nội bộ mới.
- Dùng IntelliJ IDEA hoặc Spring Tools để xem module structure và tham chiếu vi phạm theo mô hình.
- Duy trì danh sách consumer đã chuyển và consumer còn lại.
- Viết test cho facade để bảo đảm API mới giữ đúng hành vi legacy.
- Chọn mốc đóng module và không gia hạn trạng thái `OPEN` nếu không có lý do được review.

Một bảng theo dõi đơn giản:

| Consumer | Dependency cũ | API mới | Trạng thái |
|---|---|---|---|
| `shipping` | `orders.service.DefaultOrderService` | `orders.OrderManagement` | Đã chuyển |
| `billing` | `orders.persistence.OrderRepository` | `orders.OrderLookup` | Đã chuyển |
| `reporting` | `orders.persistence.OrderEntity` | `orders.OrderSummary` | Đang chuyển |

Khi các consumer chuyển xong, danh sách package con còn được tham chiếu từ bên ngoài phải rỗng, ngoại trừ named interface được công bố rõ ràng.

## Bước 7: Đóng module và bật boundary verification

Khi consumer không còn phụ thuộc vào implementation package con, chuyển module về `CLOSED`:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.orders;
```

`CLOSED` là kiểu module mặc định; nhóm cũng có thể bỏ annotation `type` nếu không cần khai báo metadata khác. Khai báo tường minh giúp người đọc thấy rõ module đã kết thúc giai đoạn mở.

Sau khi đóng, package gốc là API mặc định. Package con chỉ được module khác truy cập nếu được công bố rõ bằng named interface. Những dependency còn sót lại vào `service`, `persistence` hoặc `internal` sẽ bị phát hiện khi chạy:

```java
@Test
void verifiesModuleBoundaries() {
    ApplicationModules.of(Application.class).verify();
}
```

Nếu module tiêu thụ đã khai báo `allowedDependencies`, hãy cho phép module `orders` bằng logical identifier của nó:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shipping;
```

Khai báo này cho phép consumer dùng API ở root package `orders`. Nếu consumer chỉ cần một named interface cụ thể, hãy dùng cú pháp `orders :: spi` thay vì mở rộng dependency không cần thiết.

Nếu test thất bại, không mở module trở lại một cách tự động. Đọc từng dependency và quyết định đưa hợp đồng lên root, công bố một named interface có chủ đích hoặc chuyển trách nhiệm về module sở hữu.

Khi module đã đóng, verification cũng có thể kiểm tra chu trình liên quan đến module theo quy tắc module đóng. Điều này khôi phục mức bảo vệ kiến trúc mà giai đoạn `OPEN` đã nới lỏng.

## Ví dụ lộ trình trước và sau

**Trước khi chuyển đổi:**

```text
com.acme.orders
├── service
│   └── DefaultOrderService.java
├── persistence
│   ├── OrderRepository.java
│   └── OrderEntity.java
└── web
    └── OrderResponseMapper.java

com.acme.shipping
└── ShippingService.java  ---> orders.service.DefaultOrderService
```

**Trong giai đoạn chuyển đổi:**

```text
com.acme.orders                 [OPEN]
├── OrderManagement.java        # Hợp đồng công khai mới
├── PlaceOrderCommand.java      # Dữ liệu hợp đồng
├── service
│   └── DefaultOrderService.java # Implementation cũ
├── persistence
│   ├── OrderRepository.java
│   └── OrderEntity.java
└── web
    └── OrderResponseMapper.java

com.acme.shipping
└── ShippingService.java  ---> orders.OrderManagement
```

**Sau khi hoàn tất:**

```text
com.acme.orders                 [CLOSED]
├── OrderManagement.java        # API công khai
├── PlaceOrderCommand.java      # API công khai
└── internal
    ├── DefaultOrderService.java
    ├── JpaOrderRepository.java
    └── OrderEntity.java

com.acme.shipping
└── ShippingService.java  ---> orders.OrderManagement
```

Implementation có thể được di chuyển hoặc đổi tên sau khi consumer đã phụ thuộc vào interface. Không bắt buộc phải tái cấu trúc mọi class nội bộ cùng lúc với việc chuyển API.

## Những lỗi thường gặp

| Cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| Đóng tất cả module ngay từ đầu | Hàng loạt vi phạm xuất hiện và khó phân loại | Mở module legacy theo phạm vi rồi chuyển từng consumer |
| Giữ `Type.OPEN` vô thời hạn | Internal package tiếp tục được truy cập và cycle detection bị giảm phạm vi | Ghi owner, tiến độ và tiêu chí chuyển sang `CLOSED` |
| Đưa mọi class ra root package | API phình to và implementation bị công bố | Chỉ đưa facade, contract và DTO cần thiết ra root |
| Chuyển nguyên repository ra root để hết lỗi | Consumer bị ràng buộc với persistence | Công bố query/use case API và giữ repository nội bộ |
| Chỉ đổi import nhưng vẫn trả entity nội bộ từ API | Boundary vẫn rò rỉ qua method signature | Dùng DTO/value object thuộc hợp đồng công khai |
| Đánh dấu toàn bộ package con thành named interface | Internal code bị mở lâu dài | Chỉ công bố package cần thiết và đặt tên interface theo mục đích |
| Nghĩ `verify()` trong giai đoạn OPEN chứng minh module đã kín | Open module không thực thi kiểm tra internal như closed module | Dùng danh sách migration và đóng module để xác minh cuối cùng |
| Di chuyển implementation và consumer cùng một thay đổi lớn | Khó review và khó xác định lỗi hồi quy | Tạo facade trước, chuyển consumer từng nhóm, refactor implementation sau |

## Checklist hoàn tất một module migration

Trước khi chuyển module từ `OPEN` sang `CLOSED`, hãy xác nhận:

- [ ] Base package của module đã được xác định rõ.
- [ ] Các API cần consumer sử dụng đã nằm trong root package.
- [ ] DTO, command, result và event trong chữ ký API không làm lộ entity hoặc repository nội bộ.
- [ ] Consumer không còn import implementation từ package con.
- [ ] Những package con còn được truy cập đã được công bố thành named interface có chủ đích.
- [ ] Test của facade xác nhận hành vi nghiệp vụ cần giữ lại.
- [ ] `ApplicationModules.verify()` chạy thành công sau khi module được đóng.
- [ ] Không còn dependency cycle bị che bởi trạng thái `OPEN`.
- [ ] Annotation `Type.OPEN` đã được gỡ hoặc đổi thành `Type.CLOSED`.
- [ ] Tài liệu module và danh sách dependency đã được cập nhật.

## Bài tập tự đánh giá

Module `billing` đang ở trạng thái `OPEN`. Các module `orders`, `reporting` và `support` lần lượt import `billing.service.InvoiceService`, `billing.persistence.InvoiceRepository` và `billing.persistence.InvoiceEntity`.

Nhóm muốn chuyển `billing` sang `CLOSED` mà không thay đổi toàn bộ implementation trong một lần.

Hãy đề xuất:

1. Những hợp đồng nào nên đưa ra root package để thay thế ba dependency hiện tại?
2. Vì sao không nên công bố `InvoiceRepository` và `InvoiceEntity` như API mặc định?
3. Có thể giữ `InvoiceService` làm implementation nội bộ và tạo `InvoiceManagement` facade như thế nào?
4. Consumer nào nên được chuyển trước và test nào cần cập nhật?
5. Bằng chứng nào xác nhận đã có thể đổi `Type.OPEN` sang `Type.CLOSED`?

Một hướng giải quyết là công bố `InvoiceManagement` cho use case, `InvoiceLookup` cho truy vấn và `InvoiceSummary` làm read model ở root package. `InvoiceService` và `InvoiceRepository` tiếp tục nằm trong package con; implementation facade gọi service và repository nội bộ. Chuyển `orders`, `reporting`, `support` lần lượt sang các hợp đồng mới, kiểm tra không còn import package con từ module ngoài, rồi đóng `billing` và chạy `ApplicationModules.verify()`.

## Kết luận

Đưa API ra root package là một quá trình chuyển đổi hợp đồng, không phải thao tác di chuyển hàng loạt class. Với module legacy, `Type.OPEN` giúp bắt đầu mô hình hóa mà chưa chặn toàn bộ dependency cũ; nhóm dùng giai đoạn đó để tạo facade, chuyển consumer từng bước và giữ implementation trong package con. Khi không còn tham chiếu ngoài vào internal package, chuyển module sang `CLOSED` và để `ApplicationModules.verify()` thực thi boundary đầy đủ. Hãy đặt thời hạn cho trạng thái mở, vì nó nới lỏng kiểm tra internal và ảnh hưởng đến cycle detection.

## Tài liệu tham khảo

- [Spring Modulith Reference — Open Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.advanced.open)
- [Spring Modulith Reference — Application Modules and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModule.Type`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.Type.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [JetBrains — Migrating to a Modular Monolith using Spring Modulith](https://blog.jetbrains.com/idea/2026/02/migrating-to-modular-monolith-using-spring-modulith-and-intellij-idea/)
