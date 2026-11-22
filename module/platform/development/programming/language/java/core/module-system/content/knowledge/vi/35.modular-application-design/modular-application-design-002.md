# API module và implementation module

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao nên tách API contract khỏi implementation trong một modular application.
- Thiết kế module API chỉ công khai các type mà consumer cần sử dụng.
- Thiết kế implementation module phụ thuộc API và giữ package triển khai ở trạng thái encapsulated.
- Dùng `uses` và `provides` cùng `ServiceLoader` để tìm implementation mà không phụ thuộc class cụ thể.
- Hiểu hướng dependency giữa application, API và implementation.
- Nhận diện khi nào nên tách module và khi nào một module duy nhất là đủ.

## 1. Vì sao tách API và implementation?

Một module thường có hai nhóm nội dung khác nhau:

- **API contract**: những type, method và hành vi mà module khác được phép sử dụng.
- **Implementation**: class, thuật toán, cấu trúc dữ liệu và chi tiết nội bộ để thực hiện contract đó.

Nếu consumer phụ thuộc trực tiếp vào class triển khai, thay đổi implementation có thể kéo theo thay đổi ở consumer. Khi nhiều module cùng dùng một implementation cụ thể, việc thay thế hoặc nâng cấp nó trở nên khó khăn.

Tách API module và implementation module giúp xác định ranh giới rõ hơn:

- API module sở hữu contract ổn định.
- Implementation module cung cấp một cách thực hiện contract.
- Application module phụ thuộc vào API và sử dụng contract.
- Implementation có thể được thay thế mà không buộc application import class triển khai.

Mục tiêu không phải tạo thêm module cho mọi interface. Chỉ nên tách khi có ranh giới trách nhiệm và vòng đời thay đổi đủ rõ, chẳng hạn một domain capability có nhiều implementation, plugin hoặc nhiều consumer độc lập.

## 2. Hướng dependency mong muốn

Một thiết kế phổ biến có ba module:

~~~text
                 +--------------------+
                 |  com.acme.app      |
                 |  application       |
                 +---------+----------+
                           |
                           | requires API
                           v
                 +--------------------+
                 | com.acme.orders.api|
                 | public contract    |
                 +---------^----------+
                           |
                           | requires API
                 +---------+----------+
                 | com.acme.orders.impl
                 | implementation     |
                 +--------------------+
~~~

Cả application và implementation đều biết API contract. Application không cần biết class triển khai cụ thể.

Dependency direction:

- Application → API
- Implementation → API
- Application không cần compile dependency trực tiếp tới implementation khi dùng service discovery.
- API không phụ thuộc implementation.

Không tạo vòng phụ thuộc như API → implementation → API. Nếu contract cần một abstraction chung, abstraction đó thuộc API hoặc một module contract nhỏ hơn.

## 3. Thiết kế API module

Giả sử hệ thống có capability tạo đơn hàng. API module công khai một interface:

~~~java
package com.acme.orders.api;

public interface OrderService {

    String createOrder(String customerId);
}
~~~

Module descriptor:

~~~java
module com.acme.orders.api {
    exports com.acme.orders.api;
}
~~~

`exports` công khai package chứa contract để module khác có thể dùng public type của nó.

API nên chứa:

- Interface hoặc abstract contract mà consumer cần.
- DTO, request/response type và exception thuộc public contract.
- Enum, annotation hoặc value type cần chia sẻ.
- Service interface dùng cho dependency injection hoặc ServiceLoader.

API nên tránh chứa:

- Concrete implementation.
- Cấu hình database hoặc network client cụ thể.
- Framework adapter không thuộc contract.
- Internal helper và cache.
- Type chỉ phục vụ một implementation.

Nếu API cần DTO, hãy đặt DTO trong package được export phù hợp. Consumer chỉ nên nhìn thấy những type cần để gọi contract.

### 3.1. Giữ contract ổn định

API là ranh giới tương thích giữa các module. Khi thay đổi public method, constructor, record component hoặc semantics, có thể ảnh hưởng nhiều consumer.

Một số nguyên tắc:

- Đặt tên method theo nghiệp vụ, tránh rò rỉ chi tiết persistence.
- Không trả về type nội bộ của implementation.
- Không để API phụ thuộc vào ORM entity hoặc database-specific type nếu consumer không cần.
- Xác định rõ nullability, exception và ownership của dữ liệu.
- Version API theo quy tắc tương thích của hệ thống.

Ví dụ, nếu implementation dùng JPA, API không nhất thiết phải trả về JPA entity. Có thể trả về DTO hoặc abstraction độc lập với persistence.

## 4. Thiết kế implementation module

Implementation module phụ thuộc API:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;
}
~~~

Implementation cung cấp class thực thi interface:

~~~java
package com.acme.orders.impl;

import com.acme.orders.api.OrderService;

public final class DefaultOrderService implements OrderService {

    public DefaultOrderService() {
    }

    @Override
    public String createOrder(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }

        return "ORDER-CREATED-FOR-" + customerId;
    }
}
~~~

Package triển khai không cần export. Descriptor đầy đủ sẽ được bổ sung directive `provides`:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;

    provides com.acme.orders.api.OrderService
        with com.acme.orders.impl.DefaultOrderService;
}
~~~

Điểm quan trọng: `com.acme.orders.impl` không có `exports com.acme.orders.impl`. Class provider có thể là public để đáp ứng quy tắc provider constructor, nhưng package vẫn không được công khai cho code Java thông thường của module khác. ServiceLoader có thể tìm provider được khai báo mà consumer không cần import class triển khai.

Không dùng `opens` để thay thế `exports` trong trường hợp này. Reflection openness là một hợp đồng khác; service provider không cần mở toàn bộ package triển khai chỉ để được phát hiện.

## 5. Application phụ thuộc API và dùng ServiceLoader

Application module khai báo:

~~~java
module com.acme.app {
    requires com.acme.orders.api;

    uses com.acme.orders.api.OrderService;
}
~~~

`requires` tạo dependency tới API. `uses` khai báo application là consumer của service `OrderService`.

Code sử dụng service:

~~~java
package com.acme.app;

import com.acme.orders.api.OrderService;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        OrderService service = ServiceLoader
                .load(OrderService.class)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException(
                                "No OrderService provider found"
                        )
                );

        String result = service.createOrder("customer-42");
        System.out.println(result);
    }
}
~~~

Application chỉ import `OrderService`. Nó không import `DefaultOrderService` và không cần biết package triển khai.

Implementation module khai báo `provides`; application module khai báo `uses`. Hai directive này mô tả hợp đồng service ở cấp module.

### 5.1. Vì sao không dùng new DefaultOrderService()?

Nếu application viết:

~~~java
OrderService service = new DefaultOrderService();
~~~

thì application phải:

- Biết tên class triển khai.
- Compile dependency tới implementation module.
- Có quyền truy cập package chứa class.
- Thay đổi code khi đổi implementation.

Điều đó làm mất lợi ích của việc tách contract. ServiceLoader tạo một điểm tìm implementation qua API thay vì tham chiếu concrete class.

Nếu ứng dụng chỉ có một implementation cố định và không cần thay thế, plugin hoặc service discovery, constructor injection trực tiếp có thể đơn giản hơn. Tách module và ServiceLoader nên phục vụ nhu cầu kiến trúc thực tế.

## 6. Cấu trúc source tree hoàn chỉnh

Ví dụ project có ba module:

~~~text
project/
└── src/
    ├── com.acme.orders.api/
    │   ├── module-info.java
    │   └── com/acme/orders/api/
    │       └── OrderService.java
    ├── com.acme.orders.impl/
    │   ├── module-info.java
    │   └── com/acme/orders/impl/
    │       └── DefaultOrderService.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/
            └── Main.java
~~~

Các descriptor:

**API**

~~~java
module com.acme.orders.api {
    exports com.acme.orders.api;
}
~~~

**Implementation**

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;

    provides com.acme.orders.api.OrderService
        with com.acme.orders.impl.DefaultOrderService;
}
~~~

**Application**

~~~java
module com.acme.app {
    requires com.acme.orders.api;

    uses com.acme.orders.api.OrderService;
}
~~~

Compile các module:

~~~bash
javac -d mods --module-source-path src -m com.acme.orders.api,com.acme.orders.impl,com.acme.app
~~~

Output có dạng:

~~~text
mods/
├── com.acme.orders.api/
│   ├── module-info.class
│   └── com/acme/orders/api/OrderService.class
├── com.acme.orders.impl/
│   ├── module-info.class
│   └── com/acme/orders/impl/DefaultOrderService.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Các package của API được export. Package implementation không được export, dù provider được khai báo trong descriptor.

## 7. Resolve implementation module và service binding

Một điểm quan trọng khi dùng ServiceLoader với named modules là provider module phải có mặt trong module layer nơi service được tìm.

Khi chạy launcher, có thể đưa implementation module vào graph rõ ràng:

~~~bash
java --module-path mods --add-modules com.acme.orders.impl -m com.acme.app/com.acme.app.Main
~~~

`--add-modules` thêm provider module vào tập module được resolve. Application vẫn chỉ phụ thuộc API trong source code; tên implementation được cấu hình ở bước khởi chạy.

Trong ứng dụng plugin hoặc khi tạo module layer bằng API, có thể dùng `Configuration.resolveAndBind` để resolve dependency và bind các service provider tương ứng với service mà các module đã resolve sử dụng. Đây là cách phù hợp khi host xây dựng layer động từ một tập module finder.

Nếu ServiceLoader không tìm thấy provider, hãy kiểm tra:

1. API interface có đúng class identity với provider không?
2. Consumer module đã khai báo `uses` chưa?
3. Provider module có khai báo `provides ... with ...` đúng không?
4. Provider module có được resolve vào layer không?
5. Provider class có đáp ứng yêu cầu của ServiceLoader không?
6. Bạn có đang dùng đúng layer khi gọi ServiceLoader không?

Với named module, `ServiceLoader.load(serviceType)` tìm provider trong layer phù hợp với module của service type. Nếu host tự tạo layer mới, có thể cần dùng overload nhận layer cụ thể:

~~~java
ServiceLoader<OrderService> services =
        ServiceLoader.load(pluginLayer, OrderService.class);
~~~

Điều này giúp host tìm provider trong layer plugin thay vì mặc định chỉ tìm ở layer context phù hợp khác.

## 8. Nhiều implementation cho cùng một API

Một lợi ích của API/implementation separation là có thể có nhiều implementation:

~~~text
com.acme.orders.api
       ^
       |
       +-------------------+
       |                   |
com.acme.orders.impl.sql   com.acme.orders.impl.memory
       |                   |
       +-------- provides -+
               OrderService
~~~

Ví dụ:

- SQL implementation dùng database.
- In-memory implementation dùng cho test hoặc demo.
- Remote implementation gọi service bên ngoài.

Mỗi implementation module có thể khai báo:

~~~java
provides com.acme.orders.api.OrderService
    with com.acme.orders.impl.sql.SqlOrderService;
~~~

hoặc:

~~~java
provides com.acme.orders.api.OrderService
    with com.acme.orders.impl.memory.MemoryOrderService;
~~~

Nếu nhiều provider cùng được resolve, `ServiceLoader` có thể trả về nhiều implementation. Không nên gọi `findFirst()` rồi giả định thứ tự provider là quy tắc chọn implementation ổn định.

Nếu chỉ cho phép một implementation, hãy đảm bảo module graph chỉ đưa một provider vào layer. Nếu hỗ trợ nhiều provider, hãy định nghĩa chính sách lựa chọn rõ ràng, ví dụ:

- Provider có priority được khai báo trong metadata riêng.
- Qualifier hoặc configuration key chọn provider.
- Host chọn module/layer tương ứng.
- API cung cấp factory hoặc registry có contract xác định.

Không dựa vào thứ tự file trên module path hoặc thứ tự scan không được cam kết.

## 9. Encapsulation của implementation module

Một implementation module nên export ít package nhất có thể.

Ví dụ descriptor:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;

    provides com.acme.orders.api.OrderService
        with com.acme.orders.impl.DefaultOrderService;
}
~~~

Không cần:

~~~java
exports com.acme.orders.impl;
~~~

Khi không export package:

- Application không thể import class triển khai qua module boundary thông thường.
- Implementation có thể thay class hoặc cấu trúc package mà không thay đổi public API.
- Các internal helper, repository adapter và cache vẫn nằm sau module boundary.
- ServiceLoader vẫn có thể sử dụng provider được khai báo theo service contract.

Nếu một framework cần reflection vào package nội bộ, chỉ thêm qualified `opens` cho đúng package và module framework thực sự cần quyền. Không mở toàn bộ implementation module chỉ vì một thư viện.

## 10. Tránh rò rỉ implementation qua API

Việc tạo hai module chưa đủ nếu API vẫn trả về concrete implementation type.

Ví dụ contract không tốt:

~~~java
public interface OrderService {
    JpaOrderRepository getRepository();
}
~~~

Consumer bị phụ thuộc vào persistence implementation. Khi đổi JPA sang một cách lưu trữ khác, API và consumer đều có thể phải thay đổi.

Một contract tốt hơn chỉ để lộ capability cần thiết:

~~~java
public interface OrderService {
    String createOrder(String customerId);
}
~~~

Một số dạng rò rỉ khác:

- API trả về implementation-specific exception.
- API yêu cầu consumer truyền ORM entity.
- API expose class cấu hình nội bộ.
- API phụ thuộc vào type chỉ tồn tại trong một implementation module.
- API khai báo callback hoặc annotation của framework không phải dependency chung đã được chấp nhận.

Giữ contract nhỏ giúp consumer không cần biết implementation hoạt động bên trong như thế nào.

## 11. Dependency, versioning và compatibility

API module thường có vòng đời tương thích quan trọng hơn implementation module vì nhiều consumer phụ thuộc vào nó.

Khi thay đổi API:

- Thêm method abstract vào interface có thể phá implementation hiện có.
- Xóa hoặc đổi kiểu public method có thể phá consumer.
- Đổi tên module hoặc package có thể làm hỏng requires và service descriptor.
- Thay đổi DTO/record có thể ảnh hưởng serialization và binary compatibility.
- Thay đổi semantics có thể phá hành vi dù signature không đổi.

Khi thay implementation:

- Giữ nguyên service interface.
- Giữ module name hoặc cập nhật cấu hình provider có kiểm soát.
- Giữ semantics và error behavior của contract.
- Chạy contract tests với từng implementation.
- Không để application phụ thuộc vào implementation package.

Nếu API và implementation được phát hành thành artifact riêng, cần version compatibility rõ ràng. Ví dụ implementation phiên bản mới phải tương thích với dải API mà nó khai báo hoặc được kiểm thử cùng.

## 12. Kiểm thử theo ranh giới module

Nên có nhiều loại kiểm thử:

### API contract test

Kiểm tra hành vi và semantics mà consumer được phép dựa vào. Contract test nên độc lập với chi tiết database hoặc framework của một implementation cụ thể.

### Implementation test

Kiểm tra từng implementation thực hiện contract đúng. Có thể dùng test fixture riêng cho database hoặc in-memory storage.

### Service discovery integration test

Chạy ứng dụng trên module path thật và xác nhận ServiceLoader tìm đúng provider. Test chỉ chạy trên classpath có thể bỏ qua lỗi descriptor, uses/provides hoặc module resolution.

### Encapsulation test

Xác nhận application không thể import package implementation khi package không export. Nếu cần, kiểm tra module descriptor hoặc compile một consumer test nhỏ trong named module.

### Replacement test

Thay implementation module bằng implementation khác mà không sửa source application. Đây là bằng chứng thực tế rằng consumer phụ thuộc vào contract.

## 13. Khi nào không cần tách API và implementation?

Không phải module nào cũng cần chia thành hai artifact/module.

Có thể giữ chung một module khi:

- Module nhỏ, chỉ có một consumer nội bộ.
- Implementation không có khả năng thay thế và không cần plugin.
- Public API và implementation có cùng vòng đời thay đổi.
- Việc tách chỉ tạo thêm dependency, build configuration và versioning mà không tạo ranh giới hữu ích.

Tách module khi có ít nhất một lý do rõ ràng:

- Nhiều consumer cần dùng chung contract.
- Có nhiều implementation hoặc plugin.
- Implementation cần được thay thế độc lập.
- Muốn giữ package nội bộ không export.
- API cần versioning và compatibility độc lập.
- Có ranh giới triển khai hoặc ownership riêng.

Đừng tách chỉ vì mọi interface đều có vẻ nên nằm trong một module API. Ranh giới module nên phản ánh contract và ownership thực tế.

## 14. Checklist thiết kế

Trước khi đưa API/implementation separation vào một modular application, hãy xác nhận:

- [ ] API module chỉ chứa contract và public types cần thiết.
- [ ] API không phụ thuộc implementation.
- [ ] Implementation module phụ thuộc API, không tạo vòng dependency.
- [ ] Application phụ thuộc API thay vì concrete implementation khi cần thay thế.
- [ ] Package implementation không export nếu consumer không cần truy cập trực tiếp.
- [ ] Nếu dùng ServiceLoader, consumer có `uses` và provider có `provides`.
- [ ] Provider module thực sự được resolve vào module layer.
- [ ] Có chính sách rõ ràng nếu nhiều provider cùng tồn tại.
- [ ] API không làm lộ ORM entity, repository hoặc framework-specific type ngoài contract.
- [ ] Có contract test và integration test trên module path.
- [ ] Module split mang lại lợi ích ownership, versioning hoặc thay thế rõ ràng.

## Kết luận

API module định nghĩa hợp đồng mà consumer được phép dùng. Implementation module phụ thuộc vào hợp đồng đó, cung cấp cách thực hiện và giữ package triển khai ở trạng thái encapsulated. Application có thể phụ thuộc API và tìm implementation qua `uses`, `provides` và `ServiceLoader`.

Hãy giữ dependency direction rõ ràng: **application → API; implementation → API**. Khi application chỉ biết contract, implementation có thể được thay thế hoặc mở rộng mà không buộc consumer phụ thuộc vào class triển khai cụ thể.
