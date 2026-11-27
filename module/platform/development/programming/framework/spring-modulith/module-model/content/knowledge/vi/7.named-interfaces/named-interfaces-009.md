# Giữ named interface ổn định khi thay implementation

Named interface là hợp đồng mà một application module công khai cho các mô-đun khác sử dụng. Khi mô-đun thay repository, framework persistence, thuật toán hoặc cấu trúc package nội bộ, các consumer vẫn nên hoạt động nếu hợp đồng công khai không thay đổi. Vì vậy, muốn thay implementation an toàn, hãy thiết kế named interface xoay quanh nhu cầu nghiệp vụ và giữ các kiểu triển khai ở bên trong mô-đun sở hữu.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, named interface giúp xác định API công khai và kiểm soát phụ thuộc giữa các package trong một ứng dụng Spring Boot. `ApplicationModules.verify()` có thể bảo vệ ranh giới kiến trúc, nhưng không tự bảo đảm ý nghĩa nghiệp vụ hay tính tương thích của hợp đồng. Nhóm cần kết hợp thiết kế API, kiểm thử hợp đồng và quy trình thay đổi có kiểm soát.

## 1. Named interface là hợp đồng công khai

Một application module có thể chứa package API và nhiều package triển khai. Ví dụ, `inventory` công khai các thao tác tồn kho qua named interface `api`:

```text
com.acme.shop.inventory
├── api
│   ├── package-info.java
│   ├── InventoryOperations.java
│   └── ReservationResult.java
└── internal
    ├── InventoryOperationsImpl.java
    ├── JpaInventoryRepository.java
    └── InventoryEntity.java
```

Trong `api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Các kiểu thuộc package `api` tạo thành một bề mặt được công khai. Mô-đun khác có thể được cho phép phụ thuộc vào bề mặt này. Các kiểu trong `internal` vẫn là chi tiết triển khai của `inventory`, kể cả khi một class ở đó có modifier `public`.

Named interface là nhóm kiểu được công khai theo package; nó không nhất thiết chỉ chứa Java `interface`. Tuy vậy, các kiểu được đưa vào nhóm nên được lựa chọn có chủ đích vì mọi kiểu đó đều có thể trở thành một phần của hợp đồng mà consumer dựa vào.

## 2. Thiết kế hợp đồng theo nghiệp vụ, không theo công nghệ triển khai

Giả sử `orders` cần yêu cầu `inventory` giữ một số lượng hàng. Hợp đồng công khai nên mô tả hành động nghiệp vụ và kết quả mà bên gọi cần:

```java
package com.acme.shop.inventory.api;

public interface InventoryOperations {

    ReservationResult reserve(String orderId, String sku, int quantity);
}
```

Kết quả có thể là một kiểu dữ liệu công khai đơn giản:

```java
package com.acme.shop.inventory.api;

public record ReservationResult(
    boolean accepted,
    String reservationId,
    String reason
) {}
```

Hợp đồng này nói rõ consumer yêu cầu giữ hàng và nhận kết quả chấp nhận hoặc từ chối. Nó không tiết lộ mô-đun đang dùng JPA, JDBC, SQL, Redis hay một thuật toán cụ thể.

Tránh đưa các kiểu sau vào API nếu chúng chỉ phục vụ triển khai:

- JPA entity hoặc object ánh xạ trực tiếp tới bảng dữ liệu.
- Spring Data repository, `EntityManager`, `JdbcTemplate` hoặc kiểu phụ thuộc framework.
- Class cấu hình, cache, transaction adapter hoặc helper nội bộ.
- Kiểu dữ liệu có cấu trúc phản ánh schema database thay vì nhu cầu nghiệp vụ.

Nếu API trả về `InventoryEntity`, consumer có thể dựa vào tên cột, quan hệ entity hoặc lazy-loading behavior. Khi thay persistence model, thay đổi nội bộ sẽ lan sang các mô-đun sử dụng API. Dùng DTO hoặc value type dành riêng cho hợp đồng giúp mô-đun sở hữu quyền thay đổi mô hình lưu trữ độc lập hơn.

## 3. Giữ implementation ở package internal

Implementation có thể dùng Spring Data JPA và entity riêng mà không làm thay đổi API:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.api.InventoryOperations;
import com.acme.shop.inventory.api.ReservationResult;
import org.springframework.stereotype.Service;

@Service
public class InventoryOperationsImpl implements InventoryOperations {

    private final JpaInventoryRepository repository;

    public InventoryOperationsImpl(JpaInventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public ReservationResult reserve(String orderId, String sku, int quantity) {
        // Kiểm tra tồn kho và cập nhật dữ liệu bằng repository nội bộ.
        // Chi tiết transaction và persistence nằm trong module inventory.
        var outcome = repository.reserve(orderId, sku, quantity);
        return new ReservationResult(
            outcome.accepted(),
            outcome.reservationId(),
            outcome.reason()
        );
    }
}
```

`JpaInventoryRepository` và entity được đặt trong `internal`. Chỉ implementation của `inventory` sử dụng chúng. Consumer chỉ biết `InventoryOperations` và `ReservationResult`.

Mô-đun `orders` khai báo phụ thuộc vào named interface:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Consumer inject hợp đồng:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.api.InventoryOperations;
import com.acme.shop.inventory.api.ReservationResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacement {

    private final InventoryOperations inventory;

    public OrderPlacement(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    public void place(String orderId, String sku, int quantity) {
        ReservationResult result = inventory.reserve(orderId, sku, quantity);

        if (!result.accepted()) {
            throw new IllegalStateException(result.reason());
        }
    }
}
```

Dependency của `orders` đi qua `inventory::api`. Nếu `inventory` thay `JpaInventoryRepository` bằng JDBC hoặc một cơ chế lưu trữ khác, consumer không cần thay đổi miễn là hợp đồng và hành vi được công bố vẫn tương thích.

## 4. Những gì cần ổn định trong một hợp đồng

Một hợp đồng ổn định không chỉ là giữ nguyên tên package và tên method. Consumer còn phụ thuộc vào kiểu dữ liệu, ý nghĩa, điều kiện gọi và cách xử lý kết quả.

| Thành phần hợp đồng | Điều cần giữ ổn định |
|---|---|
| Tên và vị trí package API | Named interface tiếp tục được nhận diện dưới cùng tên và package đã công khai |
| Tên method và chữ ký | Không tùy tiện đổi tên, xóa method, đổi kiểu tham số hoặc kiểu trả về |
| Ý nghĩa tham số | Đơn vị đo, định dạng ID, quy tắc null và phạm vi giá trị phải rõ ràng |
| Ý nghĩa kết quả | Consumer hiểu nhất quán trạng thái thành công, từ chối và kết quả trung gian |
| Exception và lỗi nghiệp vụ | Phân biệt lỗi nghiệp vụ dự kiến với lỗi hạ tầng; không âm thầm đổi cách báo lỗi |
| Transaction semantics | Làm rõ thao tác đã commit hay chỉ được chấp nhận, và phạm vi nhất quán được cam kết |
| Hiệu ứng phụ | Không âm thầm thay đổi hành vi như phát event, gửi thông báo hoặc cập nhật dữ liệu khác |

Ví dụ, method `reserve(sku, quantity)` phải có quy ước rõ về đơn vị của `quantity`, cách xử lý số lượng bằng không hoặc âm, và kết quả khi tồn kho không đủ. Nếu implementation mới diễn giải `quantity` theo đơn vị khác, chữ ký Java vẫn giống nhau nhưng hợp đồng đã bị phá vỡ về mặt ngữ nghĩa.

Hãy giữ API nhỏ và thể hiện đúng những quyết định nghiệp vụ mà consumer cần. Một hợp đồng càng phơi bày nhiều chi tiết thì càng khó thay đổi mà không ảnh hưởng consumer.

## 5. Thay implementation mà không đổi named interface

Giả sử ban đầu `inventory` dùng JPA:

```text
inventory::api
    InventoryOperations
    ReservationResult

inventory::internal
    InventoryOperationsImpl
    JpaInventoryRepository
    InventoryEntity
```

Sau này nhóm chuyển sang JDBC:

```text
inventory::api
    InventoryOperations       // giữ nguyên
    ReservationResult         // giữ nguyên

inventory::internal
    InventoryOperationsImpl   // có thể thay đổi
    JdbcInventoryRepository   // thay cho JPA repository
    InventoryRow              // mô hình lưu trữ mới
```

Consumer vẫn gọi `InventoryOperations.reserve(...)`. Việc thay đổi repository, entity, câu SQL, mapping hoặc thuật toán nằm trong `inventory`. Đây là lợi ích chính của việc tách hợp đồng công khai khỏi implementation.

Một quy trình thay đổi có thể gồm:

1. Xác định các kiểu công khai mà consumer đang sử dụng.
2. Tạo implementation mới bên trong `internal` và giữ nguyên chữ ký API.
3. Chạy unit test và integration test của mô-đun sở hữu để xác nhận hành vi mới.
4. Kiểm tra Spring bean wiring để bảo đảm chỉ implementation dự kiến được chọn.
5. Chạy test consumer và kiểm thử kiến trúc bằng `ApplicationModules.verify()`.
6. Chuyển cấu hình hoặc thay bean implementation khi kết quả đã được xác nhận.
7. Loại bỏ implementation cũ sau khi không còn được sử dụng.

Trong quá trình chuyển đổi, tránh đăng ký đồng thời hai bean cùng implement một hợp đồng nếu không có quy tắc lựa chọn rõ ràng như `@Primary` hoặc qualifier. Việc Spring Modulith xác nhận dependency hợp lệ không bảo đảm Spring dependency injection sẽ chọn đúng bean khi có nhiều implementation.

## 6. Phân biệt thay đổi tương thích và thay đổi phá vỡ hợp đồng

Một số thay đổi nội bộ thường không ảnh hưởng consumer:

- Thay JPA bằng JDBC hoặc thay thư viện persistence.
- Đổi tên class implementation hoặc repository nội bộ.
- Tối ưu truy vấn, cache hoặc thuật toán nội bộ.
- Tổ chức lại package `internal`.
- Thay cấu trúc bảng nếu implementation vẫn giữ đúng hành vi và dữ liệu qua API.

Các thay đổi sau có thể phá vỡ hợp đồng:

- Xóa hoặc đổi tên method công khai.
- Đổi kiểu tham số hoặc kiểu trả về mà consumer đang sử dụng.
- Chuyển một kiểu ra khỏi named interface khiến nó không còn được công khai.
- Đổi ý nghĩa tham số, đơn vị đo, quy tắc null hoặc trạng thái trả về.
- Thay exception nghiệp vụ bằng exception khác mà consumer không xử lý.
- Thay đổi transaction hoặc thời điểm hiệu lực theo cách làm consumer hiểu sai kết quả.

Một thay đổi có thể tương thích ở cấp biên dịch nhưng vẫn phá vỡ tương thích hành vi. Chẳng hạn, method vẫn trả `true` nhưng từ nay chỉ có nghĩa “đã nhận yêu cầu”, trong khi consumer hiểu đó là “đã giữ hàng thành công”. Vì vậy, kiểm thử cần xác nhận cả chữ ký lẫn ý nghĩa nghiệp vụ.

## 7. Khi bắt buộc phải thay đổi API

Không phải mọi hợp đồng đều có thể giữ nguyên mãi. Khi nghiệp vụ đòi hỏi thay đổi phá vỡ tương thích, hãy làm rõ consumer hiện tại và cung cấp lộ trình chuyển đổi.

Một cách là thêm hợp đồng mới song song trong package mới, ví dụ:

```text
inventory
├── api
│   ├── package-info.java               // Named Interface "api"
│   ├── InventoryOperations.java       // hợp đồng cũ
│   └── ReservationResult.java
├── v2
│   ├── package-info.java               // Named Interface "v2"
│   ├── InventoryReservation.java
│   └── ReservationOutcome.java
└── internal
    └── InventoryOperationsImpl.java
```

Khai báo named interface mới trong `v2/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("v2")
package com.acme.shop.inventory.v2;
```

Consumer được phép dùng hợp đồng mới có thể khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::v2"
)
package com.acme.shop.orders;
```

Đây là cách tổ chức hai bề mặt API cùng tồn tại trong thời gian chuyển đổi; Spring Modulith không tự quản lý version hoặc migration của hợp đồng. Nhóm phải tự xác định consumer nào dùng phiên bản nào, thời gian hỗ trợ hợp đồng cũ và điều kiện loại bỏ nó. Chỉ tạo named interface mới khi thật sự cần duy trì hai hợp đồng khác nhau, không tạo phiên bản mới cho mọi thay đổi implementation.

Một lộ trình chuyển đổi an toàn thường là:

1. Công bố hợp đồng mới và giữ hợp đồng cũ hoạt động.
2. Chuyển từng consumer sang hợp đồng mới.
3. Kiểm tra không còn consumer sử dụng hợp đồng cũ.
4. Xóa hợp đồng cũ và cập nhật quy tắc phụ thuộc sau khi hoàn tất chuyển đổi.

## 8. Kiểm thử để bảo vệ named interface

Kiểm thử kiến trúc xác nhận các dependency giữa mô-đun vẫn tuân thủ ranh giới:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Có thể thêm kiểm thử hợp đồng để xác nhận API vẫn cung cấp các kiểu quan trọng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.NamedInterface;

class InventoryApiTests {

    @Test
    void keepsInventoryApiVisible() {
        var modules = ApplicationModules.of(ShopApplication.class);
        var inventory = modules.getModuleByName("inventory").orElseThrow();
        NamedInterface api = inventory.getNamedInterfaces()
            .getByName("api")
            .orElseThrow();

        assertThat(api.contains(InventoryOperations.class)).isTrue();
        assertThat(api.contains(ReservationResult.class)).isTrue();
    }
}
```

Kiểm thử này bảo vệ việc hai kiểu vẫn nằm trong named interface `api`. Nó không chứng minh hợp đồng còn tương thích về ngữ nghĩa. Vì vậy, cần thêm unit test cho quy tắc nghiệp vụ của implementation và consumer-level test cho cách consumer diễn giải kết quả.

| Kiểm thử | Điều được bảo vệ |
|---|---|
| `ApplicationModules.verify()` | Dependency và ranh giới mô-đun theo quy tắc Spring Modulith |
| Named interface model test | Các kiểu quan trọng vẫn thuộc API được công khai |
| Contract/consumer test | Consumer vẫn hiểu đúng chữ ký, kết quả và lỗi |
| Module integration test | Implementation mới thực hiện đúng hành vi qua API |

Không nên coi một test duy nhất là bằng chứng đầy đủ cho tính ổn định của API. Mỗi loại test bảo vệ một khía cạnh khác nhau của hợp đồng.

## 9. Những ngộ nhận cần tránh

- **“Giữ nguyên tên named interface là đủ.”** Consumer còn phụ thuộc vào chữ ký, kiểu dữ liệu và ngữ nghĩa của hợp đồng.
- **“Named interface tự quản lý version.”** Đây là cơ chế công khai nhóm kiểu theo package; lộ trình tương thích và chuyển đổi vẫn do nhóm thiết kế.
- **“Implementation class phải public để Spring Modulith nhận ra API.”** API nên được công khai có chủ đích; implementation nằm trong package nội bộ và không cần trở thành hợp đồng cho mô-đun khác.
- **“Có thể trả entity vì consumer chỉ đọc.”** Entity vẫn phơi bày persistence model và có thể kéo theo lazy loading, quan hệ và thay đổi schema.
- **“`verify()` chứng minh API không bị breaking change.”** `verify()` kiểm tra các quy tắc kiến trúc được mô hình hóa, không đánh giá đầy đủ ý nghĩa nghiệp vụ hoặc tương thích hành vi.
- **“Mọi thay đổi đều cần tạo named interface mới.”** Thay implementation nội bộ thường không cần thay đổi hợp đồng hoặc tên interface.

## Kết luận

Muốn thay implementation mà không ảnh hưởng consumer, hãy giữ named interface nhỏ, ổn định và diễn đạt hợp đồng nghiệp vụ. Công khai DTO hoặc value type dành riêng cho API, giữ entity, repository và framework adapter trong package `internal`, đồng thời giới hạn dependency bằng `allowedDependencies`. Khi cần thay đổi phá vỡ tương thích, cung cấp lộ trình chuyển đổi rõ ràng cho consumer. Kết hợp kiểm thử kiến trúc, kiểm thử hợp đồng và kiểm thử hành vi để bảo vệ cả ranh giới package lẫn ý nghĩa của API.
