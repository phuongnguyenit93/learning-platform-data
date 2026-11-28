# Xử lý module mở và API package

## 1. Vấn đề khi một ứng dụng có nhiều application module

Trong một modular monolith, các nghiệp vụ dùng chung tiến trình Spring Boot nhưng được tổ chức thành những **application module** với ranh giới rõ ràng. Spring Modulith giúp phát hiện các module theo cấu trúc package, kiểm chứng phụ thuộc và tạo tài liệu về module graph. Khi hệ thống phát triển, một câu hỏi khó xuất hiện: **kiểu nào là API để module khác sử dụng, kiểu nào phải nằm sau ranh giới?**

Xét hệ thống bán hàng:

- `inventory` quản lý tồn kho và công bố truy vấn khả dụng.
- `checkout` xử lý thanh toán đơn, cần kiểm tra tồn kho.
- `notification` lắng nghe sự kiện nghiệp vụ.
- `legacybilling` chứa mã thanh toán cũ đang được nhiều nơi gọi trực tiếp.

Nếu `checkout` import `inventory.internal.StockRepository` thì Java vẫn có thể biên dịch khi lớp là `public`, nhưng thiết kế đó khiến module đặt hàng phụ thuộc trực tiếp vào cách lưu dữ liệu của module tồn kho. Ngược lại, nếu dùng một interface nghiệp vụ công khai, implementation có thể thay đổi mà không buộc các consumer sửa theo.

Bài này giải thích ba công cụ chính của Spring Modulith:

1. **Module đóng (closed)**: mặc định chỉ các phần API đã công bố mới được module khác tham chiếu.
2. **API package / named interface**: công bố có chủ đích các kiểu trong một subpackage bằng `@NamedInterface`.
3. **Module mở (open)**: nới ràng buộc truy cập vào các phần nội bộ của một application module trong những tình huống có lý do, đặc biệt khi đang chuyển đổi ứng dụng cũ.

Với phạm vi `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`, mục tiêu không dừng ở việc tổ chức mã. Ta còn cần dùng module graph, tài liệu, Actuator, event metrics, tracing và context propagation để kiểm chứng cấu trúc dự kiến so với hoạt động thực tế.

## 2. Package và ranh giới module

Trong cách phát hiện module thông dụng, package chứa lớp `@SpringBootApplication` là gốc, còn những subpackage trực tiếp đại diện cho các application module.

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory                          [module]
│   ├── AvailabilityQuery.java        [API mặc định]
│   ├── package-info.java
│   ├── events
│   │   ├── package-info.java         [named interface]
│   │   └── StockLow.java
│   └── internal
│       ├── InventoryService.java
│       └── StockRepository.java
├── checkout                           [module]
│   ├── CheckoutService.java
│   └── package-info.java
├── notification                       [module]
│   └── StockLowListener.java
└── legacybilling                      [module]
    ├── package-info.java
    └── internal
        └── LegacyChargeService.java
~~~

`inventory`, `checkout`, `notification` và `legacybilling` là những module ngang cấp. `events` và `internal` là subpackage **bên trong** module `inventory`; theo cách phát hiện mặc định, chúng không tự trở thành application module độc lập.

Cách phát hiện module có thể được tùy biến ở cấp ứng dụng. Vì vậy trước khi thiết kế API, cần xác nhận Spring Modulith thực sự phát hiện những module nào, đặc biệt với dự án có nhiều tầng package, nhiều source set hoặc chiến lược phát hiện riêng.

**Application module của Spring Modulith khác JPMS.** Nó là mô hình kiến trúc ứng dụng, không buộc dự án phải khai báo `module-info.java`. Quy tắc API của Spring Modulith cũng không đồng nghĩa với kiểm soát visibility tại Java compiler.

## 3. API mặc định của module đóng

Với một module thông thường, Spring Modulith coi các kiểu thuộc **package gốc của module** là API mặc định. Các subpackage không được công bố được xem là phần nội bộ khi kiểm tra phụ thuộc giữa module.

Ví dụ:

~~~text
com.acme.shop.inventory
├── AvailabilityQuery.java       được công bố qua API mặc định
├── events
│   └── StockLow.java            chưa công bố nếu thiếu @NamedInterface
└── internal
    ├── InventoryService.java    triển khai nội bộ
    └── StockRepository.java     triển khai nội bộ
~~~

API truy vấn có thể là:

~~~java
// com/acme/shop/inventory/AvailabilityQuery.java
package com.acme.shop.inventory;

public interface AvailabilityQuery {
    boolean isAvailable(String sku, int quantity);
}
~~~

Implementation nằm phía trong:

~~~java
// com/acme/shop/inventory/internal/InventoryService.java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.AvailabilityQuery;
import org.springframework.stereotype.Service;

@Service
class InventoryService implements AvailabilityQuery {

    private final StockRepository repository;

    InventoryService(StockRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean isAvailable(String sku, int quantity) {
        return quantity > 0 && repository.availableUnits(sku) >= quantity;
    }
}
~~~

Đây là ví dụ minh họa; `StockRepository` là abstraction dữ liệu nội bộ cần được dự án định nghĩa. Consumer nhận interface qua Spring DI:

~~~java
// com/acme/shop/checkout/CheckoutService.java
package com.acme.shop.checkout;

import com.acme.shop.inventory.AvailabilityQuery;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final AvailabilityQuery stock;

    public CheckoutService(AvailabilityQuery stock) {
        this.stock = stock;
    }

    public void validate(String sku, int quantity) {
        if (!stock.isAvailable(sku, quantity)) {
            throw new IllegalStateException("Insufficient stock");
        }
    }
}
~~~

Đường phụ thuộc `checkout → inventory.AvailabilityQuery` sử dụng hợp đồng công khai. Consumer không biết `StockRepository`, transaction, SQL, JPA hay cách tính số lượng tồn. Nhờ vậy, phần triển khai có thể đổi mà không làm lan thay đổi sang `checkout`.

### Ba khái niệm dễ bị nhầm

| Khái niệm | Được quyết định bởi | Ý nghĩa |
| --- | --- | --- |
| Java `public` | Ngôn ngữ Java và accessibility rules | Kiểu có thể được tham chiếu theo quy tắc Java |
| Modulith API | Package gốc, named interface và kiểu module | Kiểu được phép trở thành dependency giữa application modules |
| Runtime endpoint / Bean | Spring MVC, messaging, Spring DI, v.v. | Cách thành phần được gọi hoặc inject khi chạy |

Một lớp `public` nằm trong `inventory.internal` **không tự trở thành Modulith API**. Ngược lại, interface đúng API vẫn phải có khả năng được sử dụng hợp lệ ở cấp Java.

## 4. Tổ chức API package bằng named interface

Khi module lớn lên, package gốc có thể chứa quá nhiều interface, DTO và event. Spring Modulith cho phép công bố một **named interface**, thường đặt trên subpackage mang ý nghĩa cụ thể, ví dụ `events`, `spi` hoặc `api`.

Giả sử `inventory.events` chứa kiểu sự kiện mà `notification` và `checkout` cần tham chiếu. Trong `inventory/events/package-info.java`:

~~~java
@NamedInterface("events")
package com.acme.shop.inventory.events;

import org.springframework.modulith.NamedInterface;
~~~

Định nghĩa dữ liệu sự kiện:

~~~java
// com/acme/shop/inventory/events/StockLow.java
package com.acme.shop.inventory.events;

public record StockLow(String sku, long availableUnits) {
}
~~~

Spring Modulith hiểu `inventory::events` là một giao diện công bố có tên `events` của module `inventory`. Các consumer được khai báo cho phép dùng giao diện đó có thể phụ thuộc vào `StockLow` mà không có quyền tùy ý sử dụng mọi loại trong `inventory.internal`.

**Tên thư mục không đủ để xuất API.** Chỉ đặt kiểu trong `inventory.api` hoặc `inventory.events` mà không có `@NamedInterface` thì subpackage đó vẫn được xem là nội bộ với một module đóng. Annotation đặt ở đúng `package-info.java` mô tả ý định kiến trúc.

Có thể dùng nhiều named interface cho một module:

~~~text
inventory
├── AvailabilityQuery.java    API mặc định
├── events
│   └── package-info.java     @NamedInterface("events")
├── spi
│   └── package-info.java     @NamedInterface("spi")
└── internal
    └── ...                   nội bộ
~~~

Trong trường hợp này, `inventory::events` và `inventory::spi` có mục đích khác nhau. Hãy tạo giao diện được đặt tên theo **khả năng thực sự dành cho consumer**, tránh công bố một gói chứa hàng chục kiểu chỉ vì tên gói là `api`.

### Nên công bố những kiểu nào?

| Nên công bố khi cần thiết | Nên giữ nội bộ |
| --- | --- |
| Interface truy vấn/command theo ngữ nghĩa nghiệp vụ | Repository và persistence adapter |
| DTO, value object ổn định cho consumer | JPA entity, lazy proxy và kiểu phụ thuộc schema database |
| Domain event cần được module khác nhận | Event handler và cơ chế retry nội bộ |
| SPI rõ ràng để tích hợp hoặc mở rộng | Các helper, mapper, utility chỉ phục vụ implementation |
| Exception/result có hợp đồng ổn định | Exception hạ tầng và framework-specific detail |

Ngay cả khi Spring Modulith chấp nhận một API package, thiết kế vẫn có thể kém nếu chữ ký của interface làm lộ kiểu nội bộ:

~~~java
// Ví dụ thiết kế không nên dùng
package com.acme.shop.inventory;

public interface AvailabilityQuery {
    com.acme.shop.inventory.internal.StockEntity findEntity(String sku);
}
~~~

Ở đây, consumer vẫn phải biết `StockEntity`. Nên trả về dữ liệu nghiệp vụ công khai như `Availability` hoặc kết quả nguyên thủy phù hợp, tránh rò rỉ database entity ra ngoài module.

## 5. Giới hạn dependency bằng `allowedDependencies`

Công bố API trả lời câu hỏi **provider mở những gì**. `allowedDependencies` trả lời câu hỏi **consumer được khai báo phụ thuộc vào module hoặc named interface nào**.

Ví dụ `checkout/package-info.java`:

~~~java
@ApplicationModule(
    allowedDependencies = {
        "inventory",
        "inventory::events"
    }
)
package com.acme.shop.checkout;

import org.springframework.modulith.ApplicationModule;
~~~

Trong ví dụ:

- `inventory` chỉ phần API mặc định của module tồn kho, chứa `AvailabilityQuery`.
- `inventory::events` chỉ named interface công bố `StockLow`.
- `checkout` không được xem là có quyền tùy ý truy cập `inventory.internal`.

Tên logical module trong cấu hình cần khớp tên được Spring Modulith phát hiện. Nếu dự án thay đổi tên module hoặc cấu hình module detection, phải đối chiếu với metadata thực tế.

### Vì sao phải dùng cả API và dependency allowlist?

| Tình huống | Kiểm tra kiến trúc mong muốn |
| --- | --- |
| `checkout` gọi `inventory.AvailabilityQuery` và được phép phụ thuộc `inventory` | Hợp lệ |
| `checkout` gọi `inventory.events.StockLow` khi giao diện đã khai báo, và consumer cho phép `inventory::events` | Hợp lệ |
| `checkout` gọi `inventory.internal.StockRepository` khi `inventory` đóng | Vi phạm ranh giới API |
| `checkout` gọi module `payment` không được liệt kê trong allowlist | Vi phạm ràng buộc dependency được khai báo |

`allowedDependencies` **không tự làm một subpackage của provider thành API**. Nó cũng không phải biện pháp kiểm soát truy cập ở runtime: Spring DI hay Java compiler không ngăn một Bean tồn tại chỉ vì khai báo kiến trúc. Cần đưa `ApplicationModules.verify()` vào test/CI để quy tắc có tác dụng thực tế.

## 6. Module mở (`Type.OPEN`) là gì?

Một hệ thống lâu năm thường có những dependency chưa thể sửa ngay. Ví dụ `reporting` và `settlement` đang import nhiều lớp ở `legacybilling.internal`. Nếu đóng module ngay, kiểm tra kiến trúc có thể báo hàng loạt vi phạm; viết lại tất cả cùng lúc tạo rủi ro lớn.

Spring Modulith cho phép đánh dấu module là **OPEN** trong `legacybilling/package-info.java`:

~~~java
@ApplicationModule(type = Type.OPEN)
package com.acme.shop.legacybilling;

import org.springframework.modulith.ApplicationModule;
import org.springframework.modulith.ApplicationModule.Type;
~~~

Module mở vẫn được nhận diện là application module, nhưng quy tắc truy cập API từ bên ngoài được **nới lỏng**: các kiểu nội bộ có thể bị consumer tham chiếu mà không phải chịu cùng giới hạn như module đóng. Đây là cách diễn tả một trạng thái chuyển tiếp, không có nghĩa mọi kiểu tự trở thành Java `public`.

| Tiêu chí | Module đóng | Module mở |
| --- | --- | --- |
| API mặc định tại package gốc | Có | Vẫn nên duy trì |
| Named interface | Dùng để công bố subpackage | Vẫn hữu ích làm hợp đồng mục tiêu |
| Truy cập vào subpackage nội bộ từ module khác | Bị kiểm tra như vi phạm nếu không được công bố | Được nới quy tắc truy cập API đối với module đó |
| Module graph | Vẫn phát hiện module và phụ thuộc | Vẫn phát hiện module và phụ thuộc |
| Java visibility và Spring DI | Không thay đổi | Không thay đổi |
| Mức kiểm soát coupling | Chặt chẽ hơn | Ít chặt chẽ hơn, cần lộ trình giảm dần |

Không nên kết luận rằng `Type.OPEN` vô hiệu hóa toàn bộ `verify()` hoặc mọi quy tắc phụ thuộc khác. Cơ chế mở tập trung vào **khả năng truy cập giao diện của module**, còn các ràng buộc khác trong mô hình ứng dụng phải được xem xét theo cấu hình thực tế.

### Khi nào nên mở?

- Tách dần một khối legacy nhiều phụ thuộc trực tiếp mà chưa thể chuyển đổi tất cả consumer.
- Cần ghi nhận module trong graph trước khi thiết kế lại hợp đồng.
- Có kế hoạch đóng lại, chủ sở hữu rõ ràng và danh sách dependency cần loại bỏ.

### Khi nào không nên mở?

- Chỉ để một kiến trúc test hết báo lỗi sau khi thêm import sai.
- Vì không muốn thiết kế một facade hoặc event rõ ràng.
- Vì tưởng module mở sẽ có hiệu năng tốt hơn hoặc tự cải thiện tracing.
- Để cho toàn bộ consumer sử dụng repository/entity nội bộ không giới hạn thời gian.

### OPEN khác với `open module` của Java

Cú pháp `open module` trong JPMS liên quan đến reflection ở mức JVM. `@ApplicationModule(type = Type.OPEN)` là metadata về kiến trúc Spring Modulith. Hai khái niệm không thay thế cho nhau; annotation này không cấp thêm khả năng reflective access trong JPMS.

## 7. Minh họa dependency trước và sau thiết kế API

Trạng thái đang gặp ở ứng dụng cũ:

~~~mermaid
flowchart LR
    C["checkout"] --> IR["inventory.internal.StockRepository"]
    R["reporting"] --> BL["legacybilling.internal.LegacyChargeService"]
~~~

Cạnh đầu truy cập phần nội bộ của module đóng; cạnh thứ hai là sự phụ thuộc legacy có thể được tạm chấp nhận khi `legacybilling` mở. Cả hai đều gây coupling lớn.

Mục tiêu sau refactor:

~~~mermaid
flowchart LR
    C["checkout"] --> IQ["inventory.AvailabilityQuery"]
    R["reporting"] --> BF["legacybilling.BillingFacade"]
    IQ --> IS["inventory.internal.InventoryService"]
    BF --> BL["legacybilling.internal.LegacyChargeService"]
~~~

Bên ngoài chỉ biết hợp đồng nghiệp vụ; triển khai vẫn ở bên trong module. Khi thay database hoặc cổng thanh toán, phần cần sửa chủ yếu nằm trong module chịu trách nhiệm.

Trong dự án thật, hãy phân biệt ba loại cạnh:

1. **Dependency tĩnh:** class reference, kiểu method, annotation, import hoặc cấu trúc được phát hiện từ code.
2. **Tương tác khi chạy:** method call, event publication, HTTP request, message, listener.
3. **Dependency được thiết kế cho phép:** thỏa API và allowlist của module.

Một lời gọi xuất hiện trong trace có thể là bằng chứng rằng module khác đang phụ thuộc vào một phần nội bộ, nhưng trace không tự cho biết cạnh ấy đúng hay sai về mặt kiến trúc.

## 8. Refactor một module legacy đang mở

Giả sử hiện tại `reporting.ReportService` gọi `legacybilling.internal.LegacyChargeService`. Có thể chuyển đổi từng bước mà vẫn quan sát được tiến độ.

### Bước 1 — Giữ lại trạng thái hiện tại có kiểm soát

Đánh dấu `legacybilling` là `Type.OPEN`; ghi lại những consumer và kiểu nội bộ đang bị gọi trực tiếp. Lưu module graph làm baseline. Ví dụ sổ theo dõi:

| Consumer | Kiểu nội bộ đang dùng | Hợp đồng thay thế dự kiến |
| --- | --- | --- |
| `reporting` | `LegacyChargeService` | `BillingQuery` |
| `settlement` | `LegacyChargeService` | `BillingFacade` |
| `notification` | `BillingEntity` | `BillingCompleted` event |

Tránh giả định cùng một interface sẽ phù hợp cho tất cả; phân biệt truy vấn, thay đổi trạng thái và sự kiện.

### Bước 2 — Công bố facade tại package gốc

~~~java
// com/acme/shop/legacybilling/BillingFacade.java
package com.acme.shop.legacybilling;

public interface BillingFacade {
    ChargeResult charge(String orderId, long amountInCents);
}
~~~

`ChargeResult` là kiểu hợp đồng minh họa phải được định nghĩa trong API của module hoặc một named interface phù hợp. Không nên trả trực tiếp `legacybilling.internal.BillingEntity`.

Implementation `legacybilling.internal` có thể triển khai `BillingFacade` và gọi hệ thống thanh toán cũ. Consumer chỉ inject interface. Kiểm thử cần xác nhận cả kết quả, transaction, idempotency và các lỗi nghiệp vụ.

### Bước 3 — Di chuyển consumer theo nhóm

Sửa từng consumer dùng facade/query/event phù hợp, cập nhật `allowedDependencies` ở các module có allowlist, chạy lại kiểm thử nghiệp vụ. Nếu chuyển method call sang event, phải kiểm tra độ trễ, eventual consistency, retry và transaction boundary; event không phải phương án thay thế đồng nghĩa cho lời gọi đồng bộ.

### Bước 4 — Đóng lại module

Khi không còn consumer import các kiểu nội bộ trái quy tắc, có thể đổi `legacybilling/package-info.java`:

~~~java
@ApplicationModule
package com.acme.shop.legacybilling;

import org.springframework.modulith.ApplicationModule;
~~~

Hoặc bỏ annotation nếu không cần metadata khác và cấu hình phát hiện mặc định đã đủ. Chạy lại kiểm tra kiến trúc và kiểm thử tích hợp. Nếu còn lỗi, xác định dependency nào chưa chuyển; không mở lại toàn bộ module như một giải pháp vĩnh viễn.

### Bước 5 — Theo dõi sau triển khai

Đối chiếu trace và event metrics với baseline để phát hiện hành vi thay đổi: thời gian xử lý, lỗi listener, retry, transaction và propagation của correlation context. Một module đóng về mặt cấu trúc vẫn có thể có lỗi runtime, vì vậy hai nhóm kiểm tra phải bổ sung cho nhau.

## 9. Kiểm chứng tự động bằng `ApplicationModules.verify()`

Tạo test kiến trúc:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void moduleDependenciesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này dùng mô hình module do Spring Modulith phát hiện để kiểm tra những ràng buộc kiến trúc mà framework hỗ trợ, trong đó có dependency qua API của module đóng và `allowedDependencies` đã cấu hình.

Ví dụ lỗi cần xử lý:

~~~text
checkout.CheckoutService
  └─ references inventory.internal.StockRepository
       └─ inventory is a closed application module
~~~

Cách sửa thường là chuyển logic sang `inventory`, bổ sung phương thức nghiệp vụ trên `AvailabilityQuery` hoặc thêm một named interface **nếu thực sự muốn công bố nhóm API ấy**. Đừng giải quyết bằng cách đưa repository ra package gốc chỉ để test đạt.

**Giới hạn:** `verify()` không tự xác minh kết quả nghiệp vụ, transaction, tính đúng đắn của truy vấn SQL, security hay context propagation. Với module mở, cần thêm review và phép đo dependency trực tiếp vì một số tương tác với phần nội bộ được nới lỏng.

## 10. Tạo tài liệu module graph

Thành phần tài liệu của Spring Modulith có thể chuyển mô hình module thành tài liệu và sơ đồ giúp nhóm đánh giá các phụ thuộc. Ví dụ test tạo tài liệu, với module tài liệu Spring Modulith tương thích có mặt trong test classpath:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocsTest {

    @Test
    void documentsModules() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        new Documenter(modules).writeDocumentation();
    }
}
~~~

Đường dẫn và định dạng được sinh ra phụ thuộc phiên bản/cấu hình Spring Modulith. Khi review kết quả, cần trả lời:

- Module nào có quá nhiều consumer?
- Module nào đang bị tham chiếu vào phần nội bộ?
- `inventory::events` có phản ánh đúng phạm vi event public không?
- Có phụ thuộc vòng nào cần giải quyết không?
- Đặt `legacybilling` là OPEN có khiến graph ghi nhận thêm những dependency cần loại bỏ không?
- Sau mỗi lần refactor, các cạnh từ consumer đến API ổn định có thay thế các cạnh trực tiếp đến implementation chưa?

Dùng graph như bản đồ thảo luận thiết kế và `verify()` làm cổng tự động trong CI. Việc sinh được sơ đồ chưa đủ chứng minh một module đã có API phù hợp.

## 11. Liên hệ Actuator, event metrics và tracing

Mục đích của Spring Modulith Documentation & Observability là kết nối **mô hình tĩnh** với **sự tương tác khi ứng dụng vận hành**.

### 11.1. Actuator và metadata module

Khi dự án tích hợp thành phần Actuator của Spring Modulith và cấu hình exposure phù hợp, metadata về cấu trúc module có thể được cung cấp qua endpoint vận hành dành cho Modulith. Điều này giúp đối chiếu kiến trúc mà ứng dụng triển khai đang nhận diện với tài liệu của build.

Endpoint có thể chứa cấu trúc nội bộ; cần kiểm soát quyền truy cập theo chính sách bảo mật. Dependency, endpoint path, exposure và dữ liệu trả về phải kiểm tra theo phiên bản Spring Boot/Modulith đang dùng; annotation `@NamedInterface` không tự động công bố endpoint ra mạng.

### 11.2. Event metrics

Ví dụ `inventory` phát `StockLow` và `notification` nhận sự kiện. `@NamedInterface("events")` giúp diễn tả **hợp đồng kiểu sự kiện** mà consumer được tham chiếu. Việc sự kiện có được phát, nhận, hoàn tất hay retry là trách nhiệm của cơ chế event publication/listener và hệ quan sát runtime.

Các chỉ số nên quan sát gồm số event xuất bản, thời gian xử lý, tỷ lệ lỗi, retries, trạng thái công bố và kết quả nghiệp vụ. Không mặc định mọi metric xuất hiện chỉ vì đã thêm named interface; khả năng instrumentation và tên metric phụ thuộc cấu hình, phiên bản và thư viện quan sát.

### 11.3. Trace và context propagation

Một request có thể đi qua:

~~~text
POST /checkout
  checkout.CheckoutService
    inventory.AvailabilityQuery
    publish StockLow
      notification.StockLowListener (có thể bất đồng bộ)
~~~

Khi listener chuyển sang executor/thread khác, trace hoặc observation context có thể cần cơ chế propagation phù hợp với Spring Boot, Micrometer và thư viện tích hợp đang dùng. Một trace bị mất tương quan có thể do cấu hình propagation, không nhất thiết do sự kiện không được xử lý.

Bản thân module mở/đóng không quyết định việc context được mang sang thread mới. Cần kiểm tra riêng hành vi này bằng integration test và telemetry thực tế.

### 11.4. Mỗi công cụ trả lời câu hỏi khác nhau

| Công cụ | Câu hỏi giải quyết tốt | Không thể tự kết luận |
| --- | --- | --- |
| `ApplicationModules.verify()` | Dependency tĩnh có tuân thủ ranh giới và allowlist không? | Mọi luồng nghiệp vụ chạy đúng |
| Module graph / `Documenter` | Các module phụ thuộc nhau như thế nào? | Tần suất và độ trễ lời gọi thực tế |
| Metadata qua Actuator | Ứng dụng triển khai nhận diện cấu trúc module ra sao? | Event đã được xử lý thành công |
| Event metrics, publication state | Event đã được phát/nhận/xử lý theo kết quả nào? | API package đã thiết kế đúng |
| Tracing | Request/event đi qua các thành phần nào? | Mọi dependency tĩnh chưa chạy trong trace đều hợp lệ |

Đối chiếu các nguồn trên giúp phát hiện chênh lệch giữa **kiến trúc dự định** và **cách module đang tương tác**.

## 12. Các lỗi thiết kế thường gặp

### Chỉ đặt tên package là `api`

~~~text
inventory/api/AvailabilityQuery.java
~~~

Chỉ tên `api` không tự xuất giao diện. Cần đặt contract tại package gốc của module hoặc công bố subpackage qua `@NamedInterface`.

### Đổi mọi module thành `Type.OPEN`

Kiểm tra kiến trúc sẽ mất nhiều khả năng phát hiện consumer sử dụng chi tiết triển khai. Nếu chỉ một API còn thiếu, hãy thiết kế API đó và để module ở trạng thái đóng. Với mã cũ, ghi rõ lý do mở và lộ trình đóng lại.

### Tưởng `allowedDependencies` xuất API của provider

Allowlist thuộc phía consumer; nó không làm `inventory.internal` trở thành public API theo Spring Modulith. Phải xét quy tắc công bố của provider và ràng buộc ở consumer cùng lúc.

### Đặt DTO bên ngoài nhưng để entity nội bộ trong chữ ký

Kiểu trả về, tham số, generic type, exception và annotation có thể vô tình kéo đối tượng nội bộ sang module khác. Rà soát cả hợp đồng Java, không chỉ vị trí file.

### Nhầm OPEN với cơ chế JVM/Spring runtime

`OPEN` không tự tăng khả năng inject Bean, không mở JPMS reflection, không tạo REST endpoint, không tự sinh metrics và không giải quyết vòng phụ thuộc nghiệp vụ.

### Cho rằng trace thành công là ranh giới hợp lệ

Trace cho biết đường đi thực tế. Để biết đường đó có phù hợp kiến trúc hay không, vẫn phải đối chiếu module API, named interface, allowlist và kết quả `verify()`.

### Công bố event rồi coi như đã bảo đảm delivery

Named interface chỉ làm rõ loại event được dùng. Cần xem riêng transaction, listener, replay/retry, idempotency, bảo mật và context propagation trong các đường xử lý bất đồng bộ.

## 13. Bài thực hành với hai module

**Đề bài:** một ứng dụng `com.example.store` có `catalog` và `ordering`.

1. Trong `catalog`, khai báo `ProductLookup` ở package gốc, `JpaProductRepository` ở `catalog.internal`.
2. Tạo `catalog.events.ProductDiscontinued` và `catalog/events/package-info.java` với `@NamedInterface("events")`.
3. Trong `ordering/package-info.java`, khai báo `allowedDependencies = {"catalog", "catalog::events"}`.
4. Viết `OrderingService` gọi `ProductLookup` và listener tiêu thụ `ProductDiscontinued`. Xác định behavior của listener khi xử lý lỗi hoặc bất đồng bộ.
5. Cố ý cho `OrderingService` tham chiếu `catalog.internal.JpaProductRepository`, chạy `ApplicationModules.verify()` và ghi nhận vi phạm. Thay tham chiếu bằng API đúng.
6. Tại một nhánh thực hành, đánh dấu `catalog` là `Type.OPEN`, xem khác biệt khi kiểm chứng; sau đó trở lại module đóng.
7. Tạo module graph bằng `Documenter` và đối chiếu với import trong code.
8. Nếu đã tích hợp observability, tạo một request làm phát event, kiểm tra metrics/trace và xem context có được nối qua listener không.

**Câu hỏi tự kiểm tra:**

- Vì sao class `public` trong `catalog.internal` không mặc nhiên thuộc API của module đóng?
- Khi nào nên đặt API tại package gốc, khi nào nên tạo `@NamedInterface`?
- Hai chuỗi `catalog` và `catalog::events` trong allowlist có ý nghĩa gì?
- `Type.OPEN` nới lỏng điều gì và không thay đổi điều gì?
- Tại sao module graph và trace cần được đối chiếu thay vì thay thế cho nhau?

## 14. Checklist khi review một ứng dụng nhiều module

| Việc cần xác nhận | Bằng chứng |
| --- | --- |
| Module được phát hiện đúng theo package và cấu hình | Danh sách `ApplicationModules` |
| Mỗi module có API mặc định nhỏ, hợp lý | Các interface/DTO ở package gốc |
| API subpackage được công bố chủ đích | `package-info.java` có `@NamedInterface` |
| Consumer chỉ phụ thuộc vào giao diện cần thiết | Import code và `allowedDependencies` |
| Module OPEN có mục tiêu rõ | Danh sách dependency legacy, chủ sở hữu và điều kiện đóng |
| Không có vi phạm ranh giới chưa được xử lý | Test `ApplicationModules.verify()` trong CI |
| Graph thể hiện cấu trúc mong đợi | Tài liệu `Documenter` được review |
| Tương tác runtime quan trọng được kiểm chứng | Actuator, event metrics, tracing và test context propagation |
| Chuyển module OPEN sang closed không gây hồi quy | Kiểm thử kiến trúc, module và tích hợp đạt |

**Nguyên tắc:** ưu tiên **module đóng** với hợp đồng rõ ràng. Dùng **package gốc** cho API mặc định, **`@NamedInterface`** để công bố một subpackage có mục đích cụ thể và **`Type.OPEN`** để quản lý có kiểm soát các phụ thuộc legacy. Module graph cho thấy cấu trúc; Actuator, event metrics và trace cho thấy hoạt động thực tế; kiểm thử kiến trúc giữ cho hai góc nhìn không trôi xa thiết kế.
