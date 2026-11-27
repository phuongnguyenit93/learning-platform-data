# Generic type làm lộ internal thế nào?

Bài này thuộc chương **API và internal** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong một ứng dụng Spring Boot. Một module có thể giữ class triển khai, entity và adapter trong package nội bộ, nhưng vô tình để những kiểu đó xuất hiện trong chữ ký API thông qua generic type.

Ví dụ, `List` là kiểu công khai của Java, nhưng `List<OrderEntity>` vẫn tiết lộ kiểu `OrderEntity`. Generic wrapper không tự che giấu kiểu phần tử. Nếu một API công khai trả về, nhận vào hoặc kế thừa một generic type có tham số thuộc package internal, module consumer có thể bị buộc phải biết đến chi tiết nội bộ đó.

## 1. Generic type có thể mang theo dependency tới kiểu nội bộ

Giả sử module order được tổ chức như sau:

~~~text
com.acme.shop.order
├── OrderQuery.java
├── OrderSummary.java
└── internal
    ├── OrderEntity.java
    ├── OrderMapper.java
    └── persistence
        └── JpaOrderRepository.java
~~~

Module order muốn giữ `OrderEntity` và repository bên trong package `internal`. Tuy nhiên, API sau lại trả về danh sách entity nội bộ:

~~~java
package com.acme.shop.order;

import java.util.List;
import com.acme.shop.order.internal.OrderEntity;

public interface OrderQuery {

    List<OrderEntity> findAll();
}
~~~

Nhìn nhanh, kiểu trả về có vẻ là `List`, một kiểu quen thuộc và công khai. Nhưng hợp đồng thực tế là `List<OrderEntity>`. Consumer cần biết kiểu phần tử nếu muốn đọc dữ liệu, gọi method hoặc khai báo biến với kiểu cụ thể.

Generic argument là một phần của chữ ký kiểu. Vì thế, việc bọc một kiểu nội bộ trong `List`, `Optional`, `Map` hay một wrapper khác không làm dependency biến mất.

## 2. Vì sao generic argument vẫn được nhìn thấy?

Java sử dụng type erasure khi biên dịch generic. Ví dụ, descriptor JVM của method trả về `List<OrderEntity>` dùng kiểu raw `List`. Tuy nhiên, thông tin generic signature vẫn được lưu trong class file để compiler và các công cụ phân tích có thể hiểu kiểu tham số.

Có thể phân biệt hai lớp thông tin:

- **Runtime representation:** generic thường bị xóa kiểu ở mức descriptor JVM; một `List<OrderEntity>` và một `List<OrderSummary>` đều được biểu diễn bằng `List`.
- **Compile-time contract:** chữ ký generic vẫn mô tả phần tử là `OrderEntity` hay `OrderSummary`, giúp compiler kiểm tra kiểu và công cụ phân tích kiến trúc thu nhận quan hệ kiểu.

Do đó, type erasure không phải cách che giấu dependency trong thiết kế API. Spring Modulith dựa trên mô hình dependency của ArchUnit để phân tích các tham chiếu kiểu trong code đã biên dịch; generic signature có thể làm lộ kiểu được dùng làm type argument.

## 3. Generic return type làm lộ internal

Một method công khai có thể trả về generic type chứa kiểu nội bộ:

~~~java
package com.acme.shop.order;

import java.util.Optional;
import com.acme.shop.order.internal.OrderEntity;

public interface OrderQuery {

    Optional<OrderEntity> findById(String orderId);
}
~~~

Ở đây, `Optional` không phải vấn đề. Kiểu bị lộ là `OrderEntity`, được đặt trong package `order.internal`.

Một consumer muốn xử lý kết quả có thể phải tham chiếu trực tiếp kiểu nội bộ:

~~~java
package com.acme.shop.shipping.internal;

import com.acme.shop.order.OrderQuery;
import com.acme.shop.order.internal.OrderEntity;

class ShippingPlanner {

    void prepare(OrderQuery orders, String orderId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();
        // Đọc trạng thái và thông tin giao hàng từ entity nội bộ.
    }
}
~~~

Khi đó, module shipping có dependency tới package nội bộ của order. Theo quy ước encapsulation, consumer nên dùng kiểu thuộc API mặc định hoặc named interface được module order công khai.

Ngay cả khi consumer không khai báo biến kiểu `OrderEntity`, việc gọi các method đặc thù trên phần tử có thể khiến mã consumer tham chiếu tới kiểu nội bộ đó. Vì vậy, hãy đánh giá cả chữ ký API lẫn cách consumer thực sự sử dụng kết quả.

## 4. Generic parameter type cũng có thể làm lộ internal

Chiều dữ liệu đi vào API cũng có rủi ro tương tự:

~~~java
package com.acme.shop.order;

import java.util.List;
import com.acme.shop.order.internal.OrderCommand;

public interface OrderImport {

    void importOrders(List<OrderCommand> commands);
}
~~~

Consumer muốn gọi `importOrders` phải tạo danh sách chứa `OrderCommand`. Nếu kiểu command nằm trong package nội bộ, consumer phải phụ thuộc vào phần mà module muốn giữ kín.

Có thể gặp tình huống tương tự với:

~~~java
public interface OrderBatchProcessor {

    void process(Map<String, OrderCommand> commands);

    void validate(Collection<OrderCommand> commands);
}
~~~

Các kiểu container như `Map` và `Collection` không che giấu `OrderCommand`. Generic argument vẫn là một phần hợp đồng đầu vào.

Nếu consumer cần gửi dữ liệu vào module order, hãy định nghĩa command DTO ổn định trong API công khai, hoặc công khai một named interface dành riêng cho hợp đồng nhập liệu.

## 5. Generic lồng nhau vẫn làm lộ kiểu ở sâu bên trong

Một generic signature có thể lồng nhiều cấp:

~~~java
public interface OrderReport {

    Map<String, List<Optional<OrderEntity>>> findGroupedOrders();
}
~~~

Kiểu nội bộ `OrderEntity` vẫn xuất hiện ở lớp sâu nhất. Đổi wrapper hoặc thêm cấp generic không loại bỏ tham chiếu đó.

Một số dạng thường gặp:

| Chữ ký | Kiểu nội bộ bị lộ |
|---|---|
| `List<OrderEntity>` | `OrderEntity` |
| `Optional<OrderEntity>` | `OrderEntity` |
| `Map<String, OrderEntity>` | `OrderEntity` |
| `Page<OrderEntity>` | `OrderEntity` |
| `CompletableFuture<OrderEntity>` | `OrderEntity` |
| `ResponseEntity<List<OrderEntity>>` | `OrderEntity` |
| `Map<String, List<OrderEntity>>` | `OrderEntity` |

Điều cần xem là toàn bộ cây generic type, không chỉ outer type. Khi review API, hãy lần theo các type argument cho đến kiểu cụ thể ở bên trong.

## 6. Wildcard và type variable không tự che giấu internal

Wildcard có thể làm chữ ký linh hoạt hơn, nhưng không xóa kiểu được tham chiếu:

~~~java
public interface OrderQuery {

    List<? extends OrderEntity> findAll();

    void archive(List<? super OrderEntity> orders);
}
~~~

Cả `? extends OrderEntity` và `? super OrderEntity` đều nhắc đến `OrderEntity`. Consumer vẫn phải biết kiểu đó để làm việc với hợp đồng một cách an toàn về kiểu.

Type variable có bound nội bộ cũng có thể làm lộ implementation type:

~~~java
public interface InternalOrderQuery<T extends OrderEntity> {

    List<T> findAll();
}
~~~

Dù method dùng tên `T`, bound `T extends OrderEntity` vẫn ràng buộc generic contract với kiểu nội bộ. Đổi tên kiểu thành `T`, `R` hoặc `E` không làm dependency biến mất.

## 7. Generic superclass và interface cũng có thể để lộ internal

Rủi ro không chỉ nằm trong return type hay parameter. Một kiểu API có thể kế thừa generic superclass hoặc triển khai generic interface với type argument nội bộ:

~~~java
package com.acme.shop.order;

import com.acme.shop.order.internal.OrderEntity;

public class OrderPage extends Page<OrderEntity> {
}
~~~

Hoặc:

~~~java
package com.acme.shop.order;

import com.acme.shop.order.internal.OrderEntity;

public interface OrderStream extends Publisher<OrderEntity> {
}
~~~

Trong cả hai trường hợp, public type vẫn mang quan hệ generic tới `OrderEntity`. Consumer sử dụng `OrderPage` hoặc `OrderStream` có thể bị kéo theo hiểu biết về kiểu nội bộ.

Khi thiết kế public class, record hoặc interface, hãy xem cả generic superclass, implemented interfaces và type parameter bounds, không chỉ các method được khai báo trực tiếp.

## 8. Phân biệt internal implementation dependency và public API leak

Không phải mọi generic reference tới internal type đều là lỗi API. Phạm vi và vị trí khai báo quyết định ý nghĩa của nó.

| Trường hợp | Ý nghĩa |
|---|---|
| Lớp triển khai nội bộ có field `List<OrderEntity>`. | Dependency nội bộ trong module; thường hợp lý nếu lớp đó thực sự xử lý entity. |
| Method private trong adapter nhận `Optional<OrderEntity>`. | Chi tiết triển khai; không tự trở thành hợp đồng cho consumer bên ngoài. |
| Interface ở package API trả về `List<OrderEntity>`. | Public API làm lộ kiểu nội bộ trong generic signature. |
| Consumer module khai báo hoặc thao tác trực tiếp với `OrderEntity`. | Dependency xuyên module tới package internal; có thể vi phạm encapsulation. |
| Public API dùng `List<OrderSummary>` thuộc package API. | Hợp đồng công khai rõ ràng, không buộc consumer biết entity nội bộ. |

Một field private trong implementation vẫn tạo class dependency trong mô hình phân tích kiểu. Tuy nhiên, nó không đồng nghĩa kiểu đó đã được công khai cho module khác. Hãy phân biệt dependency nội bộ của provider với type leak qua bề mặt API.

## 9. Thiết kế lại bằng DTO hoặc public contract

Cách phổ biến là giữ entity và persistence model bên trong module, đồng thời trả về DTO hoặc view type thuộc API công khai.

Ví dụ, định nghĩa kiểu kết quả ở package gốc của order:

~~~java
package com.acme.shop.order;

public record OrderSummary(
    String orderId,
    String status,
    String deliveryAddress
) {
}
~~~

API công khai chỉ dùng kiểu này:

~~~java
package com.acme.shop.order;

import java.util.List;
import java.util.Optional;

public interface OrderQuery {

    List<OrderSummary> findAll();

    Optional<OrderSummary> findById(String orderId);
}
~~~

Phần triển khai nội bộ có thể chuyển entity thành DTO:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.order.OrderSummary;

class OrderMapper {

    OrderSummary toSummary(OrderEntity entity) {
        return new OrderSummary(
            entity.id(),
            entity.status(),
            entity.deliveryAddress()
        );
    }
}
~~~

Consumer chỉ cần biết `OrderSummary`:

~~~java
package com.acme.shop.shipping.internal;

import com.acme.shop.order.OrderQuery;
import com.acme.shop.order.OrderSummary;

class ShippingPlanner {

    void prepare(OrderQuery orders, String orderId) {
        OrderSummary order = orders.findById(orderId).orElseThrow();
        // Lập kế hoạch giao hàng từ dữ liệu công khai.
    }
}
~~~

Như vậy, module order giữ quyền thay đổi entity, ORM mapping và repository. Module shipping phụ thuộc vào hợp đồng công khai ổn định hơn.

## 10. Dùng named interface khi hợp đồng nằm trong package con

Nếu API query cần được nhóm riêng khỏi API mặc định, có thể đặt các kiểu công khai trong package con và đánh dấu bằng `@NamedInterface`.

Ví dụ:

~~~java
@org.springframework.modulith.NamedInterface("query")
package com.acme.shop.order.query;
~~~

Các kiểu trong named interface:

~~~java
package com.acme.shop.order.query;

public record OrderSummary(String orderId, String status) {
}
~~~

~~~java
package com.acme.shop.order.query;

import java.util.List;
import java.util.Optional;

public interface OrderQuery {

    List<OrderSummary> findAll();

    Optional<OrderSummary> findById(String orderId);
}
~~~

Module shipping khai báo dependency được phép:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"order::query"}
)
package com.acme.shop.shipping;
~~~

Named interface giúp công khai đúng nhóm hợp đồng. Nó không làm một kiểu internal trở thành an toàn chỉ vì kiểu đó được đặt trong generic của interface. Các type argument của API vẫn phải thuộc bề mặt được công khai và có ý nghĩa ổn định.

## 11. Không dùng raw type hoặc Object để che type leak

Một cách né tránh có vẻ đơn giản là bỏ generic argument:

~~~java
public interface OrderQuery {

    List findAll();
}
~~~

Hoặc trả về `List<Object>`:

~~~java
public interface OrderQuery {

    List<Object> findAll();
}
~~~

Cách này làm mất thông tin kiểu, khiến consumer phải ép kiểu và có thể tạo lỗi runtime. Nó không cải thiện chất lượng hợp đồng, cũng không giải quyết quyền sở hữu dữ liệu.

Tương tự, dùng `Object`, `Map<String, Object>` hoặc chuỗi JSON không cấu trúc chỉ để tránh tham chiếu tới internal type sẽ chuyển vấn đề từ dependency tĩnh sang hợp đồng yếu và khó kiểm soát.

Hãy tạo DTO, projection hoặc interface công khai thể hiện đúng dữ liệu mà consumer cần. Nếu dữ liệu thực sự cần linh hoạt, thiết kế một schema có cấu trúc và quy tắc tương thích rõ ràng.

## 12. Kiểm chứng type leak bằng Spring Modulith

Sau khi xác định API và package nội bộ, chạy kiểm tra kiến trúc:

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

Giả sử order công khai package gốc hoặc named interface `query`, nhưng shipping tham chiếu `com.acme.shop.order.internal.OrderEntity`. Spring Modulith có thể phát hiện consumer đang truy cập package nội bộ của module order.

Khi kiểm tra thất bại, hãy lần theo:

1. Module consumer đang tham chiếu kiểu nào?
2. Kiểu đó nằm trong generic argument, bound, superclass hay method signature nào?
3. Package chứa kiểu đó thuộc API mặc định, named interface hay internal?
4. Consumer có thực sự cần entity/implementation type đó không?
5. Có thể thay bằng DTO hoặc public contract phù hợp không?

Không nên mở toàn bộ module chỉ để làm verification qua. Nếu kiểu đó thực sự cần được chia sẻ, hãy đưa nó vào hợp đồng công khai có chủ đích và đánh giá xem nó có ổn định, đúng ngữ nghĩa hay không.

## 13. Checklist review generic API

Trước khi công khai một interface hoặc class, hãy rà soát:

- [ ] Return type có chứa generic argument thuộc package internal không?
- [ ] Parameter type có chứa internal type trong collection hoặc wrapper không?
- [ ] Generic type có lồng nhiều cấp không?
- [ ] Wildcard `extends` hoặc `super` có tham chiếu internal type không?
- [ ] Type variable có bound là internal class/interface không?
- [ ] Public superclass hoặc implemented interface có generic argument nội bộ không?
- [ ] Các kiểu được chia sẻ có thuộc package API hoặc named interface không?
- [ ] DTO có chứa đúng dữ liệu consumer cần, không làm lộ entity/ORM model không?
- [ ] Consumer có thể sử dụng API mà không import package internal không?
- [ ] `ApplicationModules.verify()` chạy thành công với quy tắc module đã khai báo không?

Checklist này giúp phát hiện type leak trước khi API được nhiều module sử dụng. Khi hợp đồng đã được dùng rộng rãi, thay đổi generic argument có thể trở thành thay đổi tương thích ảnh hưởng đến nhiều consumer.

## Ghi nhớ

Generic type không che giấu kiểu nội bộ. `List<InternalType>`, `Optional<InternalType>`, `Page<InternalType>`, generic lồng nhau, wildcard và type variable bound đều có thể mang tham chiếu tới internal type trong chữ ký. Type erasure ở runtime không xóa generic contract được lưu trong metadata class file và được compiler hoặc công cụ phân tích sử dụng.

Hãy giữ entity, repository và implementation model trong package nội bộ; công khai DTO hoặc interface ổn định trong package gốc hay named interface. Review toàn bộ cây generic type của field và chữ ký API, rồi dùng `ApplicationModules.verify()` để phát hiện consumer phụ thuộc vào package internal ngoài ý muốn.
