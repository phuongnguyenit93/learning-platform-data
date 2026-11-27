# Event listener tạo required interface

## Required interface trong mô hình module

Spring Modulith mô hình hóa mỗi application module qua ba phần: API mà module cung cấp, phần triển khai nội bộ và những hợp đồng mà module cần từ module khác. Phần thứ ba được gọi là *required interface*.

Required interface là khái niệm trong mô hình kiến trúc. Nó không có nghĩa Spring Modulith tự sinh một Java interface mới. Nó mô tả các phụ thuộc mà một module cần để thực hiện công việc, chẳng hạn:

- Spring bean mà module gọi thông qua constructor hoặc field injection.
- Application event mà module đăng ký listener để nhận.
- Configuration properties được module khác công bố.

Với giao tiếp qua event, module phát event cung cấp một hợp đồng; module có listener cho event đó cần hợp đồng ấy. Vì vậy, listener tạo ra một quan hệ phụ thuộc trong mô hình module, dù module phát event không gọi trực tiếp bean listener.

## Event listener tạo ra quan hệ phụ thuộc như thế nào?

Giả sử ứng dụng có hai module:

- **orders** quản lý đơn hàng và phát **OrderCompleted** khi đơn hàng hoàn tất.
- **inventory** lắng nghe **OrderCompleted** để cập nhật tồn kho.

Luồng tương tác diễn ra như sau:

~~~mermaid
flowchart LR
    O["orders<br/>phát OrderCompleted"] -->|"Application event"| L["inventory<br/>listener nhận event"]
    L -. "required interface:<br/>inventory cần event của orders" .-> O
~~~

Mũi tên liền biểu diễn luồng event lúc chạy. Mũi tên nét đứt biểu diễn hướng phụ thuộc trong mô hình kiến trúc: **inventory** phụ thuộc vào hợp đồng event do **orders** cung cấp.

Hướng phụ thuộc này rất quan trọng. **orders** không cần biết module nào sẽ xử lý **OrderCompleted**. Khi một module mới đăng ký listener, module phát event không phải sửa mã nguồn để gọi module mới. Tuy vậy, mô hình kiến trúc vẫn ghi nhận rằng module nhận event cần biết kiểu event được công bố.

## Ví dụ với @ApplicationModuleListener

Giả sử package gốc của ứng dụng là **com.acme.shop**:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   └── OrderCompleted.java
└── inventory
    └── InventoryOrderCompletedListener.java
~~~

Trong ví dụ này, **OrderCompleted** nằm ngay trong package gốc của module **orders**. Package gốc là API mặc định của module, vì vậy module khác có thể tham chiếu kiểu event công khai này.

### Module phát event

Khai báo event như một kiểu dữ liệu công khai:

~~~java
package com.acme.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {}
~~~

**OrderManagement** phát event sau khi hoàn tất thay đổi nghiệp vụ:

~~~java
package com.acme.shop.orders;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderManagement {

    private final ApplicationEventPublisher events;

    public OrderManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId) {
        // Thực hiện chuyển trạng thái đơn hàng sang COMPLETED.

        events.publishEvent(new OrderCompleted(orderId));
    }
}
~~~

**ApplicationEventPublisher** là cơ chế phát event của Spring Framework. Module **orders** chỉ công bố sự kiện nghiệp vụ sau khi thực hiện thay đổi trạng thái cần thiết. Nó không cần tham chiếu đến **InventoryOrderCompletedListener**.

### Module nhận event

Module **inventory** đăng ký listener:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho dựa trên đơn hàng đã hoàn tất.
    }
}
~~~

Kiểu tham số **OrderCompleted** cho biết listener nhận event do module **orders** công bố. Spring Modulith có thể dùng quan hệ này để xác định module **inventory** cần hợp đồng event của **orders**.

**@ApplicationModuleListener** là cách khai báo listener được Spring Modulith khuyến nghị cho tích hợp giữa các module. Annotation này kết hợp xử lý event sau khi transaction phát event commit, chạy bất đồng bộ và thực hiện listener trong transaction riêng (**REQUIRES_NEW**). Nhờ vậy, công việc của listener được tách khỏi transaction nghiệp vụ ban đầu.

Nếu cần xử lý đồng bộ hoặc có semantics transaction khác, hãy chọn cơ chế listener của Spring phù hợp với yêu cầu. Dù chọn annotation nào, kiểu event vẫn là hợp đồng mà module nhận phải sử dụng.

## Required interface khác với lời gọi Spring bean

Có hai cách phổ biến để module **inventory** sử dụng chức năng của **orders**.

**Gọi trực tiếp Spring bean:** **inventory** inject một bean công khai của **orders**. Mô hình ghi nhận phụ thuộc qua kiểu bean mà module sử dụng.

~~~java
@Component
class InventoryService {

    private final OrderQuery orderQuery;

    InventoryService(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }
}
~~~

**Nhận application event:** **inventory** khai báo listener nhận **OrderCompleted**. Mô hình ghi nhận phụ thuộc qua kiểu event mà listener xử lý.

~~~java
@Component
class InventoryOrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Xử lý event.
    }
}
~~~

Cả hai đều tạo ra required interface của **inventory**, nhưng biểu đạt hai hình thức tương tác khác nhau:

| Hình thức | Hợp đồng mà module cần | Quan hệ lúc chạy |
|---|---|---|
| Spring bean dependency | Kiểu bean/API của module cung cấp | Module tiêu thụ gọi bean |
| Event listener | Kiểu application event được công bố | Module phát event, listener nhận event |

Với lời gọi bean, module tiêu thụ thường biết trực tiếp thành phần cung cấp chức năng. Với event, module phát sự kiện không cần biết danh sách consumer. Điều này giúp giảm liên kết trực tiếp và hỗ trợ mở rộng thêm consumer.

## Công bố event qua named interface

Khi số lượng kiểu trong module tăng lên, nhóm phát triển có thể đặt event vào package riêng để phân biệt hợp đồng tích hợp với phần triển khai. Package đó cần được công bố bằng named interface nếu module khác phải tham chiếu đến các kiểu bên trong.

Ví dụ, chuyển event sang **com.acme.shop.orders.events**:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Kiểu event nằm trong package này:

~~~java
package com.acme.shop.orders.events;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {}
~~~

Listener của **inventory** import kiểu từ named interface:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.events.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho.
    }
}
~~~

Nếu module **inventory** khai báo rõ các phụ thuộc được phép, có thể giới hạn nó vào named interface **events** của **orders**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders::events"
)
package com.acme.shop.inventory;
~~~

Cú pháp **orders::events** chỉ rõ module đích và named interface được phép sử dụng. Cách khai báo này giúp consumer truy cập hợp đồng event mà không cần mở toàn bộ package triển khai của **orders**.

Nếu không khai báo **allowedDependencies** tường minh, Spring Modulith vẫn áp dụng quy tắc hiển thị mặc định của module. Dù sử dụng cách nào, kiểu event được tham chiếu phải nằm trong phần API mà module nguồn công bố.

## Kiểm chứng required interface được tạo từ listener

Có thể kiểm tra cấu trúc module bằng **ApplicationModules.verify()**:

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

Khi kiểm chứng, Spring Modulith phân tích cấu trúc package và các quan hệ phụ thuộc thể hiện trong mã nguồn, bao gồm những event type mà module có listener xử lý. Một số vấn đề có thể được phát hiện:

- Listener tham chiếu event type thuộc package nội bộ của module khác.
- Module tiêu thụ sử dụng event contract không được module nguồn công bố.
- Phụ thuộc event không phù hợp với danh sách **allowedDependencies** đã khai báo.
- Việc tổ chức package khiến kiểu event không thuộc module mà nhóm phát triển dự định.

Nếu listener không biên dịch được vì không truy cập được kiểu event, hãy kiểm tra package và quyền truy cập Java trước. Nếu mã nguồn biên dịch nhưng kiểm chứng kiến trúc thất bại, hãy đọc thông báo để xác định module nguồn, module tiêu thụ và named interface liên quan.

## Những nhầm lẫn thường gặp

**Cho rằng listener làm module phát event phụ thuộc vào consumer.** Quan hệ required interface đi từ module có listener đến module sở hữu event type. Module phát event không cần biết consumer.

**Cho rằng required interface là một Java interface được sinh tự động.** Đây là mô tả hợp đồng phụ thuộc trong mô hình module. Kiểu event vẫn là class hoặc record do ứng dụng định nghĩa.

**Đặt event trong package nội bộ rồi mong module khác sử dụng được.** Nếu event là hợp đồng tích hợp, hãy đặt nó ở package API mặc định hoặc công bố package riêng bằng **@NamedInterface**.

**Cho rằng dùng event thì không còn phụ thuộc kiến trúc.** Event giảm liên kết trực tiếp lúc chạy, nhưng consumer vẫn phụ thuộc vào cấu trúc và ý nghĩa của event type. Thay đổi event contract vẫn có thể ảnh hưởng đến consumer.

**Dùng event cho mọi lời gọi.** Nếu caller cần kết quả ngay để tiếp tục quyết định nghiệp vụ, một API truy vấn hoặc lời gọi service có thể phù hợp hơn. Event thích hợp khi module muốn công bố một sự kiện đã xảy ra để các module quan tâm tự xử lý.

**Nhầm lẫn mô hình phụ thuộc với bảo đảm xử lý event thành công.** Việc Spring Modulith nhận diện required interface không tự bảo đảm listener hoàn tất thành công. Với yêu cầu độ tin cậy cao, cần xem xét Event Publication Registry để theo dõi publication và hỗ trợ xử lý lại khi listener thất bại.

## Bài tập vận dụng

Một hệ thống bán hàng có ba module: **orders**, **inventory** và **notifications**. Khi đơn hàng hoàn tất, **orders** phát **OrderCompleted**; **inventory** cập nhật tồn kho và **notifications** gửi email cho khách hàng.

Hãy xác định:

1. Module nào cung cấp event contract?
2. Những module nào có required interface phụ thuộc vào event của **orders**?
3. Hướng phụ thuộc trong mô hình đi từ module phát event đến listener hay từ listener đến module sở hữu event?
4. Nếu **OrderCompleted** được chuyển vào package **orders.events**, cần khai báo gì để consumer được phép sử dụng kiểu event?
5. Khi thêm module **notifications**, có cần sửa **OrderManagement** để gọi trực tiếp module mới không?

Kết quả mong đợi: **orders** cung cấp event contract; **inventory** và **notifications** đều có required interface tham chiếu đến event đó. Hướng phụ thuộc kiến trúc đi từ mỗi consumer về **orders**. Nếu event nằm trong package riêng, công bố package bằng named interface và chỉ cấp quyền phụ thuộc cần thiết. **OrderManagement** tiếp tục phát event mà không cần biết các consumer.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể giải thích vì sao một event listener tạo required interface, xác định đúng hướng phụ thuộc giữa module phát event và module nhận event, tổ chức event type trong API công khai hoặc named interface, và dùng **ApplicationModules.verify()** để kiểm tra hợp đồng đó.

Tài liệu tham khảo:

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [ApplicationModule API — getEventsListenedTo](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [ApplicationModuleListener API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html)
