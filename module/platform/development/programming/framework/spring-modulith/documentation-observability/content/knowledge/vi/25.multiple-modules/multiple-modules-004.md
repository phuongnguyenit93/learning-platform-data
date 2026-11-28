# Đọc dependency type từ graph và span

> **Chương:** Nhiều module
> **Phạm vi:** Spring Modulith Documentation & Observability — đọc quan hệ giữa application module từ sơ đồ, JSON của Actuator và dấu vết thực thi bằng Micrometer Tracing trong ứng dụng Spring Boot.

## 1. Đặt vấn đề: hai cách nhìn vào cùng một hệ thống

Ứng dụng Spring Boot có thể chứa nhiều **application module** như **orders**, **payments**, **inventory** và **notifications**. Spring Modulith xác định ranh giới module, phân tích phụ thuộc giữa các kiểu Java, tạo sơ đồ và công bố metadata qua Actuator. Khi ứng dụng chạy, phần quan sát của Spring Modulith có thể ghi lại những lời gọi đi vào các API module dưới dạng **Micrometer span**, kèm metric cho event.

Để hiểu ứng dụng có đang tuân thủ kiến trúc không, phải đặt hai loại bằng chứng cạnh nhau:

- **Graph tĩnh (design-time/metadata):** module A có tham chiếu đến kiểu của module B theo hình thức nào; cạnh có **dependency type** gì. Graph được suy từ cấu trúc mã và cấu hình phát hiện module.
- **Span động (runtime):** lời gọi hoặc event listener cụ thể đã được quan sát lúc chạy, ở thời điểm nào, mất bao lâu và xuất hiện trong trace nào.

Hai câu hỏi khác nhau:

1. **Graph:** “Notifications phụ thuộc vào Orders vì đăng ký lắng nghe event từ Orders hay vì inject bean của Orders?”
2. **Trace:** “Trong yêu cầu xử lý đơn hàng vừa xảy ra, lời gọi qua Payments có thực thi không; listener Notifications có chạy, và trace có nối được qua bước xử lý bất đồng bộ không?”

**Không được suy rằng có cạnh graph là có một lời gọi đã xảy ra, hoặc không thấy span nghĩa là không có dependency.** Sampling, proxy, instrumentation, luồng async và phạm vi test ảnh hưởng những gì trace thể hiện.

### Kết quả cần đạt

Sau bài này, bạn có thể đọc hướng cạnh, nhận diện **DEFAULT**, **USES_COMPONENT**, **EVENT_LISTENER**, đối chiếu graph với span có nhãn **module.invocation-type**, phát hiện coupling ngoài ý muốn và đề xuất cách kiểm chứng bằng test, Actuator, metric, tracing cùng cơ chế context propagation.

## 2. Đọc hướng cạnh của dependency graph

Một cạnh **A → B** trong graph phụ thuộc có nghĩa **mã thuộc A phụ thuộc vào loại hoặc API do B cung cấp**; A là **source**, B là **target**. Mũi tên này **không mặc nhiên là hướng chảy của request, event hoặc dữ liệu nghiệp vụ**.

Ví dụ:

~~~mermaid
flowchart LR
    O["orders"] -->|"USES_COMPONENT: gọi bean"| P["payments"]
    N["notifications"] -->|"EVENT_LISTENER: dùng kiểu OrderCompleted"| O
    O -.->|"runtime: phát OrderCompleted"| N
~~~

Giải thích:

- **orders → payments:** Orders inject/call một Spring bean API của Payments; đây là hướng phụ thuộc tĩnh cũng thường trùng với hướng lời gọi đồng bộ.
- **notifications → orders:** Notifications có listener nhận kiểu event **OrderCompleted** được công bố trong API của Orders; đây là hướng tham chiếu kiểu Java từ nơi nghe đến nơi định nghĩa event.
- **orders ⇢ notifications:** Lúc vận hành, Orders phát event và Notifications xử lý. **Hướng luồng event có thể ngược hướng cạnh EVENT_LISTENER** vì đơn vị phụ thuộc tĩnh là **listener** cần biết định nghĩa event, không phải **publisher** cần biết người nhận.

Giữ riêng ba khái niệm khi đọc: **phụ thuộc mã nguồn**, **quan hệ bean cần khởi tạo** và **tương tác thực tế trong một trace**.

## 3. Các DependencyType quan trọng

Trong Java API, enum **org.springframework.modulith.core.DependencyType** biểu diễn loại phụ thuộc giữa application module. Các loại thường gặp:

| Dependency type | Ý nghĩa ở graph | Dấu hiệu trong source | Có thể suy từ span không? |
| --- | --- | --- | --- |
| **DEFAULT** | Tham chiếu thông thường tới một kiểu thuộc module khác. | Dùng kiểu trong chữ ký/field/tham chiếu mã, không được phân loại thành bean dependency hay event listener. | **Không trực tiếp.** Không có span chỉ vì Java dùng một DTO hoặc enum. |
| **USES_COMPONENT** | Phụ thuộc vào Spring component/bean từ module khác; module đích có thể cần được bootstrap để chạy module nguồn. | Constructor injection, phụ thuộc service/repository hoặc API do Spring quản lý. | Có thể thấy lời gọi khi điểm vào module được instrument, request được lấy mẫu. |
| **EVENT_LISTENER** | Module nguồn khai báo listener cho event do module đích định nghĩa. | **@EventListener**, **@TransactionalEventListener**, **@ApplicationModuleListener** hoặc cơ chế listener được Spring Modulith nhận diện. | Có thể thấy **module.invocation-type = event listener**, nhưng chỉ khi listener thực sự được instrument và chạy. |
| **ENTITY** | Java enum có thêm loại thể hiện việc tham chiếu entity của module khác. | Một module dùng trực tiếp kiểu entity thuộc module kia. | Không tự sinh span; xem API và cách xuất metadata trên đúng phiên bản. |

**Lưu ý phiên bản và định dạng:** Javadoc của **DependencyType** có hằng **ENTITY**, nhưng tài liệu về **/actuator/modulith** mô tả cụ thể ba giá trị **DEFAULT**, **USES_COMPONENT** và **EVENT_LISTENER** trong trường **dependencies[].types**. Đừng ép mọi artifact JSON phải có **ENTITY**; hãy đọc đúng phiên bản Spring Modulith và đầu ra thực tế đang chạy.

### Một cạnh có thể mang nhiều type

Nếu module **billing** vừa inject một service của **orders**, vừa lắng nghe một event định nghĩa trong **orders**, JSON có thể gộp thành **một cạnh billing → orders** với:

~~~json
{
  "target": "orders",
  "types": ["EVENT_LISTENER", "USES_COMPONENT"]
}
~~~

**types là mảng**, không phải một chuỗi; nó cho biết nhiều kiểu phụ thuộc cùng tồn tại giữa hai module. Muốn loại bỏ coupling, phải xem **từng lý do** tạo nên cạnh. Chuyển bean call sang event có thể xóa **USES_COMPONENT**, trong khi **EVENT_LISTENER** vẫn còn.

### Chỉ số đo lường không phải dependency type

Trong trace, **module.invocation-type** có thể mang giá trị **bean** hoặc **event listener**. Đó là nhãn mô tả **đường vào module được quan sát**, không phải enum DependencyType. Ví dụ **bean** trong span là dấu hiệu một lời gọi được bọc bằng instrumentation; không phải bằng chứng rằng đúng một cạnh **USES_COMPONENT** hiện diện trong JSON hay graph.

## 4. Đọc graph qua Spring Modulith Actuator

Spring Modulith cung cấp **/actuator/modulith** để công bố metadata module ở runtime. Để có support Actuator, có thể khai báo starter bao gồm cả Actuator và observability:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Dùng Spring Modulith BOM hoặc dependency management của phiên bản Spring Boot tương thích để quản lý version. Nếu chỉ cần graph qua Actuator, có thể dùng **spring-modulith-actuator** cùng **spring-boot-starter-actuator**; nếu chỉ cần instrumentation thì dùng module observability thích hợp với nhánh phiên bản đó.

Cho môi trường **phát triển nội bộ**, có thể cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health, info, modulith
  tracing:
    sampling:
      probability: 1.0 # Chỉ nên để 100% ở môi trường thực nghiệm.
~~~

Exposure là một bước riêng với đăng ký endpoint: cần dependency, cấu hình quản lý endpoint và quyền truy cập phù hợp. **Không mở công khai sơ đồ module hoặc metadata của hệ thống production**; giới hạn Actuator qua bảo mật, mạng quản trị hoặc cổng quản lý nội bộ.

Thực hiện yêu cầu trên ứng dụng đang chạy:

~~~http
GET /actuator/modulith
~~~

Một kết quả **minh họa**, các module và tên do ví dụ đặt ra:

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.acme.shop.orders",
    "dependencies": [
      {
        "target": "payments",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "payments": {
    "displayName": "Payments",
    "basePackage": "com.acme.shop.payments",
    "dependencies": []
  },
  "notifications": {
    "displayName": "Notifications",
    "basePackage": "com.acme.shop.notifications",
    "dependencies": [
      {
        "target": "orders",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

Cách đọc chính xác:

| JSONPath hoặc trường | Diễn giải |
| --- | --- |
| **$.orders** | Module có technical name/identifier **orders**. |
| **$.orders.displayName** | Tên hiển thị dành cho người đọc tài liệu; có thể khác identifier. |
| **$.orders.basePackage** | Package gốc dùng để phân định phạm vi module. |
| **$.orders.dependencies[]** | Các phụ thuộc **đi ra** từ Orders. |
| **$.orders.dependencies[0].target** | Module mà Orders tham chiếu, ở đây là **payments**. |
| **$.orders.dependencies[0].types[]** | Các loại phụ thuộc giữa Orders và Payments; ở đây là **USES_COMPONENT**. |
| **$.notifications.dependencies[0]** | Notifications phụ thuộc vào Orders; **không** được đọc thành Orders phụ thuộc Notifications. |

Ở các cấu trúc có **nested module**, metadata có thể có thêm **parent** và **nested**. Đừng đồng nhất một nested module với package con bất kỳ khi chưa đối chiếu quy tắc phát hiện module.

### Tìm cạnh cần xem bằng công cụ dòng lệnh

Nếu máy có **jq**, có thể đọc một cách thủ công:

~~~bash
curl -s http://localhost:8080/actuator/modulith |
  jq '.orders.dependencies[] | {target, types}'
~~~

Hoặc rà mọi cạnh **USES_COMPONENT**:

~~~bash
curl -s http://localhost:8080/actuator/modulith |
  jq 'to_entries[] | .key as $source |
      .value.dependencies[]? |
      select(.types | index("USES_COMPONENT")) |
      {source: $source, target: .target, types: .types}'
~~~

Lệnh chỉ phân tích **metadata graph hiện tại**; nó không xác minh một lời gọi đã xảy ra và không đo thời lượng tương tác.

## 5. Đọc graph từ ApplicationModules và Documenter

### 5.1. Sinh sơ đồ module

Trong test/documentation task, **ApplicationModules** phân tích mô hình tĩnh; **Documenter** sinh tài liệu C4/UML Component, Module Canvas và các tệp tham chiếu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;
import org.springframework.modulith.docs.Documenter;
import org.springframework.modulith.docs.Documenter.DiagramOptions;

class ModuleGraphDocumentationTests {

    @Test
    void writeModuleGraphs() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        modules.verify(); // Phát hiện vi phạm ranh giới và chu trình.

        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml();

        // Ví dụ lựa chọn riêng các quan hệ bean và listener.
        new Documenter(modules).writeModulesAsPlantUml(
                DiagramOptions.defaults().withDependencyTypes(
                        DependencyType.USES_COMPONENT,
                        DependencyType.EVENT_LISTENER));
    }
}
~~~

**ShopApplication** là class **@SpringBootApplication** của dự án giả định. Ví dụ cần Spring Modulith core, module docs và JUnit trong classpath test. **Documenter** ghi các bản sinh tài liệu dưới thư mục **spring-modulith-docs** trong build output theo mặc định; khi viết nhiều sơ đồ với cùng tên mặc định, cần đặt tên đầu ra khác bằng **DiagramOptions.withTargetFileName(...)** nếu muốn giữ đồng thời các phiên bản.

**writeModulesAsPlantUml()** tạo sơ đồ tổng thể; **writeIndividualModulesAsPlantUml()** thể hiện module và các phụ thuộc trực tiếp. **DiagramOptions.withDependencyTypes(...)** lọc loại quan hệ được vẽ. **Không thấy cạnh trong biểu đồ đã lọc không có nghĩa graph đầy đủ không có cạnh đó.**

Sơ đồ PlantUML là một **góc nhìn** của ApplicationModules. Đường vẽ, nhãn hoặc kiểu nét tùy renderer/style; khi cần kiểm toán chính xác loại phụ thuộc, ưu tiên metadata JSON hoặc API DependencyType thay vì đoán từ màu hay chiều dài đường vẽ.

### 5.2. Truy vấn chính xác từng phụ thuộc từ Java API

Mỗi **ApplicationModuleDependency** cung cấp **getDependencyType()**, **getSourceType()**, **getTargetType()** và **getTargetModule()**. Có thể in các cạnh ở mức **kiểu Java**, trước khi gom thành cặp module:

~~~java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModuleDependency;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;

class DependencyInspection {

    static void printEdges() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        for (ApplicationModule source : modules) {
            for (ApplicationModuleDependency edge :
                    source.getDirectDependencies(modules).stream().toList()) {

                System.out.printf(
                        "%s -> %s | %s | %s -> %s%n",
                        source.getIdentifier(),
                        edge.getTargetModule().getIdentifier(),
                        edge.getDependencyType(),
                        edge.getSourceType().getName(),
                        edge.getTargetType().getName());
            }
        }
    }

    static void printBeanDependencies() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        for (ApplicationModule source : modules) {
            source.getDirectDependencies(
                    modules, DependencyType.USES_COMPONENT)
                    .stream()
                    .forEach(edge -> System.out.printf(
                            "%s -> %s%n",
                            source.getIdentifier(),
                            edge.getTargetModule().getIdentifier()));
        }
    }
}
~~~

Ví dụ trên dùng Java hỗ trợ **Stream.toList()** (Java 16+; các phiên bản Spring Boot/Spring Modulith mới hơn thường chạy trên JDK phù hợp). Nếu làm báo cáo, nên nhóm theo **source module**, **target module**, **DependencyType** và chỉ sau đó đếm số kiểu cụ thể: nhiều tham chiếu Java giữa cùng hai module vẫn có thể được trình bày thành **một cạnh module-level**.

Phân biệt:

- **getDirectDependencies(...)**: chỉ quan hệ trực tiếp, phù hợp để giải thích tại sao có cạnh trong graph.
- **getAllDependencies(...)**: bao gồm quan hệ bắc cầu; A phụ thuộc B, B phụ thuộc C **không đồng nghĩa A có import trực tiếp từ C**.
- **withType(DependencyType)** hoặc truyền các type vào phương thức đọc dependency: lọc kết quả theo loại; **không** làm thay đổi kiến trúc gốc.

## 6. Span cho ta bằng chứng gì?

Spring Modulith observability có thể tạo span khi lời gọi đi vào các Spring component nằm trong API module hoặc một event listener được instrument. Các span này liên kết với hệ sinh thái **Micrometer Observation/Tracing**, sau đó được xuất sang hệ thống trace (ví dụ Zipkin, Tempo qua OpenTelemetry), tùy cấu hình.

Tài liệu của Spring Modulith nêu các tag của **Module Entry Span**:

| Tag | Đọc như thế nào |
| --- | --- |
| **module.identifier** | Định danh kỹ thuật của module mà điểm vào đang được quan sát thuộc về. |
| **module.name** | Tên hiển thị của module đó. |
| **module.method** | Phương thức đang được thực thi tại điểm vào module. |
| **module.invocation-type** | Loại lời gọi quan sát được: **bean** hoặc **event listener**. |

**Không có tag chuẩn bắt buộc tên dependency.type trong danh sách trên.** Không nên viết truy vấn trace giả định một span đương nhiên có **DEFAULT**, **USES_COMPONENT** hoặc **EVENT_LISTENER**.

### Ví dụ trace đồng bộ

Giả sử HTTP request tới **orders** và Orders gọi API của Payments. Trong công cụ tracing, bạn có thể gặp cấu trúc **minh họa**:

~~~text
HTTP POST /orders/42/complete   [trace T1]
  └── module: orders
      tags:
        module.identifier=orders
        module.invocation-type=bean
        module.method=complete
      └── module: payments
          tags:
            module.identifier=payments
            module.invocation-type=bean
            module.method=capture
~~~

Lúc này:

1. **Graph** cho biết có cạnh **orders → payments**, có thể được phân loại **USES_COMPONENT**.
2. **Span** xác nhận trong **một lần chạy đã được ghi nhận**, Orders đi qua điểm vào Payments; có thể đọc thời gian bắt đầu, duration, lỗi và parent/child.
3. **Sự kết hợp** củng cố giả thuyết quan hệ bean đang được sử dụng. Để khẳng định *chính xác* kiểu cạnh, vẫn kiểm tra graph/API và source.

Span chỉ xuất hiện khi instrumentation tương ứng được bật, lời gọi đi qua cơ chế được instrument và trace được lấy mẫu. Lời gọi nội bộ trong cùng bean, method không được bọc proxy, reflective access hoặc một module nằm ngoài phạm vi quét có thể không tạo span như bạn kỳ vọng.

### Ví dụ event listener và hướng quan hệ

Tình huống Orders phát **OrderCompleted**, Notifications xử lý:

~~~text
Graph tĩnh: notifications -> orders [EVENT_LISTENER]

Luồng nghiệp vụ: orders (publish OrderCompleted)
                 -> notifications (handle event)

Span listener có thể có:
  module.identifier=notifications
  module.invocation-type=event listener
  module.method=on
~~~

Hai kết luận khác nhau:

- **EVENT_LISTENER ở graph** chứng minh listener có phụ thuộc tĩnh vào event do module khác công bố.
- **event listener ở span** chứng minh listener đã chạy ở một mẫu trace có instrumentation; chưa cho biết xử lý hoàn tất nghiệp vụ đúng, event đã được commit bền vững hay mọi lần publish đều được giao.

Với listener bất đồng bộ sau commit, phần Notifications **có thể nằm trong một trace khác** hoặc có liên hệ trace tùy cơ chế context propagation. Không nên đòi mọi listener phải là **child span** trực tiếp của span HTTP trong mọi cấu hình.

## 7. Ví dụ đầy đủ với ba module

Giả sử ứng dụng **com.acme.shop** có ba module mặc định theo package trực tiếp dưới package gốc:

~~~text
com.acme.shop
  ShopApplication
  orders
    OrderService
    OrderCompleted
  payments
    PaymentOperations
    PaymentService
  notifications
    ReceiptListener
~~~

### 7.1. Orders gọi bean Payments và phát event

Định nghĩa API trong **payments**:

~~~java
package com.acme.shop.payments;

import java.util.UUID;

public interface PaymentOperations {
    void capture(UUID orderId);
}
~~~

Bean triển khai cùng module:

~~~java
package com.acme.shop.payments;

import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
class PaymentService implements PaymentOperations {
    @Override
    public void capture(UUID orderId) {
        // Thao tác thanh toán thực tế của ứng dụng.
    }
}
~~~

Event được công khai từ package API **orders**:

~~~java
package com.acme.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {
}
~~~

Một service ở Orders gọi Payments, rồi phát event:

~~~java
package com.acme.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.acme.shop.payments.PaymentOperations;

@Service
class OrderService {

    private final PaymentOperations payments;
    private final ApplicationEventPublisher events;

    OrderService(PaymentOperations payments,
                 ApplicationEventPublisher events) {
        this.payments = payments;
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId) {
        payments.capture(orderId);
        events.publishEvent(new OrderCompleted(orderId));
    }
}
~~~

### 7.2. Notifications nghe OrderCompleted

~~~java
package com.acme.shop.notifications;

import com.acme.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ReceiptListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Gửi thông báo cho đơn hàng, xử lý retry/idempotency thực tế.
    }
}
~~~

**@ApplicationModuleListener** là annotation tích hợp các semantics của **@Async**, **@TransactionalEventListener** và transaction riêng; khi khai báo đúng hạ tầng async/transaction, listener thường chạy sau commit của transaction công bố. Nên kết hợp **Event Publication Registry** để lưu và theo dõi publication, hỗ trợ xử lý lỗi. Đây là cơ chế tách rời giao dịch, **không bảo đảm chỉ giao một lần**; listener thực tế cần idempotency.

### 7.3. Dự đoán và đối chiếu bằng chứng

| Bằng chứng | Dự kiến | Cách xác minh |
| --- | --- | --- |
| Graph Orders | **orders → payments**, có **USES_COMPONENT**. | Actuator JSON hoặc ApplicationModules API. |
| Graph Notifications | **notifications → orders**, có **EVENT_LISTENER**. | Kiểu **OrderCompleted** và annotation listener. |
| HTTP trace thành công | Điểm vào Orders và Payments có thể tạo span **bean**. | Tracing backend, kiểm tra trace ID và module.identifier. |
| Event listener được thực thi | Điểm vào Notifications có thể tạo span **event listener**. | Trigger event thật, đợi listener hoàn tất và tìm span. |
| Event metrics | Counter event do Orders phát tăng. | Micrometer metrics, kết hợp logging hoặc registry khi cần xác nhận listener thành công. |
| Kiểm chứng kiến trúc | Không có vòng dependency hoặc truy cập package internal trái phép. | **ApplicationModules.verify()**. |

Không suy rằng **orders → notifications** phải tồn tại như phụ thuộc Java: Orders chỉ công bố event mà không tham chiếu tới **ReceiptListener**. Đây là lợi ích chính của event-driven module design.

## 8. So sánh graph với trace theo quy trình từng bước

Khi nhận được một trace đáng ngờ, hãy làm theo quy trình đối chiếu sau:

1. **Xác định module thật:** dùng **module.identifier** của span, sau đó tìm key tương ứng trong Actuator JSON. Không dùng **displayName** làm khóa nối nếu có tên trùng hoặc tên thân thiện bị đổi.
2. **Đặt dấu thời gian:** graph công bố từ phiên bản ứng dụng nào? Span thuộc build/deployment nào? Không kết luận sai lệch nếu hai bằng chứng đến từ hai phiên bản khác nhau.
3. **Kiểm tra hướng của sự kiện:** với bean call A → B, xem **A.dependencies[].target = B**. Với event từ A tới listener B, trước tiên xem **B.dependencies[].target = A** và loại **EVENT_LISTENER**.
4. **Đọc đầy đủ mảng types:** nếu thấy **[EVENT_LISTENER, USES_COMPONENT]**, đừng xóa giả thuyết bean coupling chỉ vì trace hiện tại thể hiện listener.
5. **Kiểm tra điểm vào thực tế:** đọc **module.invocation-type**, **module.method**, parent span, duration và status/error; dùng chúng để xác nhận luồng vận hành, **không dùng để tự gán DependencyType**.
6. **Đánh giá mức phủ:** xác nhận sampling, actuator exposure, tracing backend, thời gian chờ async, proxy/instrumentation và context propagation. “Không tìm thấy span” là kết quả không đủ bằng chứng khi chưa kiểm tra các yếu tố này.
7. **Quay lại source và test:** tìm constructor injection hoặc listener khai báo tương ứng; chạy **verify()** và test hành vi đã kích hoạt trace.

### Bảng chẩn đoán nhanh

| Graph | Span | Diễn giải hợp lý | Việc cần kiểm tra |
| --- | --- | --- | --- |
| A → B **USES_COMPONENT** | Thấy **bean span** của B dưới tác vụ A | Bean dependency có dấu hiệu đang dùng trong đường chạy này. | Cùng version, parent/child, call site và thời lượng. |
| A → B **USES_COMPONENT** | Không thấy B | Chưa đủ chứng cứ; lời gọi có thể không xảy ra hoặc bị bỏ qua. | Nhánh code, sampling, instrumentation, test input. |
| B → A **EVENT_LISTENER** | Thấy **event listener span** ở B sau publish của A | Luồng event đã đi tới listener trong lần quan sát. | Xác thực event, async, lỗi và registry publication. |
| B → A **EVENT_LISTENER** | Listener là trace riêng | Có thể xảy ra qua async boundary hoặc thiếu context propagation. | Executor, propagator, baggage, sampling và quan hệ trace. |
| Cạnh **DEFAULT** | Không có span | Bình thường khi chỉ dùng type/DTO. | Rà mức độ chia sẻ kiểu và ranh giới module. |
| Trace có module B | Không thấy cạnh A → B | Có thể là luồng do framework/event hoặc graph bị lọc/different deployment. | Loại bỏ filter; đúng hướng listener; chạy source check. |
| Graph có **[USES_COMPONENT, EVENT_LISTENER]** | Chỉ thấy **bean span** | Hệ thống có cả hai dạng phụ thuộc, dù lần chạy này chỉ dùng một. | Code và tình huống kích hoạt event còn thiếu. |

## 9. Observability: metric, tracing và context propagation

### 9.1. Bật tracing thực sự

Artifact **spring-modulith-starter-insight** cung cấp Modulith Actuator và hỗ trợ observability, nhưng để xem span trong Zipkin/Tempo/Grafana cần cấu hình **Micrometer Tracing bridge** (ví dụ OpenTelemetry/Brave) và **exporter** phù hợp theo tài liệu Spring Boot của phiên bản đang sử dụng. Riêng thêm starter **không tự bảo đảm có trace hiển thị** ở bên ngoài.

Trong môi trường thử nghiệm:

- Cấu hình sampling cao để thấy các luồng cần phân tích; production dùng mức phù hợp với chi phí và mục tiêu quan sát.
- Tạo request có đầu vào định danh dễ tra cứu bằng một **correlation ID đã xử lý an toàn**.
- Truy vấn trace có **module.identifier** của module đích, kiểm tra cả nhãn **module.invocation-type**.
- Phân tích độ trễ **bean span** cùng lỗi, sau đó kiểm tra event listener riêng nếu workflow bất đồng bộ.

Không thêm orderId, token, email hay payload tùy ý vào **metric tag**: chúng tạo cardinality cao hoặc làm rò dữ liệu nhạy cảm. Nếu cần tương quan chi tiết, dùng log/trace theo chính sách bảo mật và lưu trữ phù hợp.

### 9.2. Event metrics không thay thế delivery metrics

Tài liệu Spring Modulith mô tả các counter:

- **module.events.published**: tổng hợp các event publication.
- **module.events.published.{moduleIdentifier}.{simpleEventTypeName}**: metric riêng cho một loại event.

Ví dụ, tổng số **OrderCompleted** được phát từ Orders tăng **không chứng minh** Notifications đã gửi thông báo thành công. Để đánh giá end-to-end, cần thêm trạng thái **Event Publication Registry** (nếu sử dụng), độ trễ listener, lỗi và thông tin retry. Đối với giao dịch bất đồng bộ, theo dõi backlog publication, số bản ghi thất bại/quá hạn và thời gian xử lý bên cạnh published counter.

### 9.3. Context propagation qua @Async và event listener

Một request thường mang **trace context** theo thread đang chạy. Khi sự kiện được xử lý trên thread khác hoặc sau transaction commit, context không tự động được giữ trong mọi thiết lập. Kết quả có thể là:

~~~text
Trace T-100:
  HTTP POST /orders
    -> orders.complete
       -> payments.capture

Trace T-101:
  notifications.on(OrderCompleted)
~~~

Điều đó **chưa chứng minh có hai yêu cầu nghiệp vụ độc lập**. Chúng có thể bắt nguồn từ cùng một event nhưng bị tách trace. Phải kiểm tra:

1. Cấu hình **TaskExecutor**, **@Async** và propagator được Spring Boot/Micrometer hỗ trợ.
2. **Micrometer Context Propagation** hoặc **TaskDecorator/ContextSnapshot** trên executor nếu dự án dùng cơ chế truyền context thủ công. API cụ thể phụ thuộc phiên bản.
3. Các ranh giới như thread pool, scheduler, messaging broker, Reactor và listener sau commit; mỗi loại có cơ chế kích hoạt propagation riêng.
4. Cách trace backend thể hiện **parent/child** hoặc **span link**; một event async không nhất thiết là lời gọi đồng bộ trực tiếp.
5. Tình huống trace bị sampling: nếu event đã xử lý nhưng span vắng, kiểm tra rate và exporter trước khi kết luận mất event.

Không truyền nguyên **SecurityContext**, dữ liệu xác thực hoặc thông tin cá nhân qua context tùy tiện. Propagation phục vụ tương quan và một số bối cảnh thực thi cần thiết, nhưng cũng cần đánh giá lifecycle, quyền truy cập và cleanup thread-local.

## 10. Kiểm chứng kiến trúc và cách test

### 10.1. Kiểm tra invariant graph bằng Spring Modulith

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    @Test
    void architectureIsConsistent() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**verify()** kiểm tra chu trình ở mức module, các truy cập trái phép vào package internal (theo thiết lập module) và ràng buộc **allowedDependencies** khi được khai báo. Nó **không chứng minh** listener chạy, trace có đủ sampling hay tất cả API đều nhanh.

Nếu dùng cấu hình module tùy biến (ví dụ đổi cách nhận diện module), phải bảo đảm **runtime** và **test/documentation** dùng cùng quy tắc phát hiện để tránh graph so sánh lệch.

### 10.2. Kiểm tra quan hệ bằng test có chủ đích

Một bộ kiểm thử hữu ích cần các nhóm:

| Nhóm | Bài thử | Bằng chứng đạt |
| --- | --- | --- |
| **Static** | Assert module graph sau mỗi thay đổi package/constructor/annotation. | Các dependency type đúng; không vi phạm ranh giới. |
| **Documentation** | Sinh C4/UML từ **Documenter**; diff đồ thị với baseline. | Cạnh mới được giải thích, không có coupling bất ngờ. |
| **Actuator** | Lấy **/actuator/modulith** ở bản build thử nghiệm. | Identifier, target và **types[]** khớp kỳ vọng. |
| **Bean call** | Thực thi **orders.complete()** đi qua Payments. | Payment được gọi; khi instrumentation sẵn sàng, có span thích hợp. |
| **Event** | Commit một OrderCompleted rồi đợi listener xử lý. | Event được nhận; kiểm tra thêm trạng thái registry và lỗi nếu có. |
| **Async propagation** | Chạy listener trên thread khác. | Có dấu tương quan đủ để tra luồng; diễn giải chính xác quan hệ trace. |
| **Sampling failure** | Hạ sampling hoặc vô hiệu exporter trong môi trường test riêng. | Ứng dụng vẫn đúng nghiệp vụ; báo cáo không suy thiếu dependency từ span vắng. |

Có thể dùng **@ApplicationModuleTest** để bootstrap các module có chủ đích. Các chế độ **STANDALONE**, **DIRECT_DEPENDENCIES** và **ALL_DEPENDENCIES** giúp phân biệt module nào cần bean của module nào khi test. Riêng **USES_COMPONENT** thường ảnh hưởng việc cần bootstrap hoặc mock bean; **EVENT_LISTENER** chỉ thể hiện quan hệ kiểu event và không mặc nhiên buộc bootstrap module publisher để chạy module subscriber.

### 10.3. Trường hợp graph/trace khác nhau do môi trường

- **Graph khác giữa máy dev và production:** khả năng thiếu cùng bộ classpath, tính năng module detection bị cấu hình riêng trong test, build artifact khác hoặc công cụ đọc phiên bản không đồng nhất.
- **Module có API nhưng span không xuất hiện:** Spring bean có thể chưa được instrument, request không đi qua public API, sampling thấp hoặc proxy không kích hoạt.
- **Event published counter tăng, listener không chạy:** kiểm tra transaction có commit, listener có được đăng ký, async executor, lỗi listener và registry. Với **@TransactionalEventListener**, event phát ngoài transaction có thể có hành vi khác nếu không cấu hình fallback; không mặc định xem đó là lỗi graph.
- **Có span event listener nhưng business side effect thất bại:** span chứng minh điểm vào đã thực thi, cần kiểm tra status/error, transaction rollback và kết quả nghiệp vụ.
- **Một event bị xử lý nhiều lần:** cần idempotency; một trace thành công không có nghĩa quá trình retry/delivery bảo đảm exactly once.

## 11. Bài tập thực hành: tìm sai lệch giữa graph và span

Hệ thống báo:

~~~json
{
  "orders": {
    "dependencies": [
      {"target": "payments", "types": ["USES_COMPONENT"]}
    ]
  },
  "notifications": {
    "dependencies": [
      {"target": "orders", "types": ["EVENT_LISTENER", "DEFAULT"]}
    ]
  }
}
~~~

Một trace sau khi hoàn tất đơn hàng thể hiện:

~~~text
Trace A:
  orders.complete   [module.invocation-type=bean]
    payments.capture [module.invocation-type=bean]

Trace B:
  notifications.on  [module.invocation-type=event listener]
~~~

Hãy trả lời:

1. **Module nào phụ thuộc tĩnh vào Orders?** Vì sao điều đó không đồng nghĩa Orders inject Notifications?
2. **Notifications → Orders có hai type** có nghĩa gì? Vì sao không được chỉ đọc phần tử đầu tiên?
3. **Trace B khác trace A** có nhất thiết là mất context propagation hay lỗi nghiệp vụ không?
4. **Nếu bỏ việc inject Payments trong Orders**, loại type nào có khả năng biến mất? Cần xác minh bằng cách nào?
5. **Nếu Published counter tăng nhưng không có Trace B**, đâu là ba điều kiện cần kiểm tra trước khi kết luận listener không chạy?

**Gợi ý đáp án:**

1. Notifications phụ thuộc Orders vì dùng kiểu/event công bố ở Orders. Hướng event runtime là Orders phát để Notifications nhận; trong mã Orders không cần biết class listener.
2. Có cả **EVENT_LISTENER** và **DEFAULT**. Có thể có thêm tham chiếu kiểu thông thường ngoài điểm listener; phải kiểm tra **getSourceType()/getTargetType()** để biết nguồn gốc cạnh.
3. Không. Listener async có thể có trace riêng, context chưa được nối hoặc backend biểu diễn link khác; cần kiểm tra cấu hình propagation và bản ghi thực thi.
4. **USES_COMPONENT** ở cạnh Orders → Payments có thể biến mất nếu đó là phụ thuộc duy nhất, nhưng phải kiểm tra lại toàn bộ source, Actuator JSON và **verify()**.
5. Kiểm tra transaction/registry, đăng ký và lỗi listener, sampling/exporter/async tracing. Tăng counter publish không đồng nghĩa listener đã nhận thành công.

## 12. Những nguyên tắc cần giữ khi đọc nhiều module

- Cạnh **source → target** trong graph biểu diễn **module nguồn phụ thuộc module đích**; không suy nó là hướng event runtime.
- **DEFAULT**, **USES_COMPONENT** và **EVENT_LISTENER** phân loại dependency tĩnh; **ENTITY** cũng tồn tại trong Java enum nhưng cần đối chiếu phiên bản và định dạng JSON thực tế.
- **module.invocation-type = bean/event listener** là nhãn **runtime span**, không phải tên hằng của DependencyType.
- **types[]** có thể chứa nhiều giá trị cho cùng cặp module; luôn đọc hết mảng và khi cần thì quay về từng phụ thuộc ở mức Java type.
- **ApplicationModules/Documenter/Actuator** trả lời cấu trúc và ranh giới; **trace/metric/registry** trả lời điều gì đã chạy, có thể đo hoặc thất bại.
- **Không thấy span** cần đánh giá sampling, context propagation, instrumentation và độ phủ kích hoạt trước khi suy không có tương tác.
- **ApplicationModules.verify()** là chốt kiểm tra kiến trúc tĩnh; test module, event và tracing là bằng chứng bổ sung về vận hành.

## Tài liệu tham chiếu chính thức

1. [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html) — Documenter, C4/UML, Module Canvas, DiagramOptions.
2. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Actuator JSON, dependencies.types, các tag của module span và event metrics.
3. [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html) — quy tắc graph, API boundary, allowedDependencies.
4. [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — @ApplicationModuleListener, async, transaction, publication registry.
5. [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html) — STANDALONE, DIRECT_DEPENDENCIES, ALL_DEPENDENCIES.
6. [DependencyType Javadoc](https://docs.spring.io/spring-modulith/docs/2.1.1/api/org/springframework/modulith/core/DependencyType.html) — DEFAULT, USES_COMPONENT, EVENT_LISTENER, ENTITY.
7. [ApplicationModuleDependency Javadoc](https://docs.spring.io/spring-modulith/docs/2.1.1/api/org/springframework/modulith/core/ApplicationModuleDependency.html) — getDependencyType(), getSourceType(), getTargetType().
8. [Documenter.DiagramOptions Javadoc](https://docs.spring.io/spring-modulith/docs/2.1.1/api/org/springframework/modulith/docs/Documenter.DiagramOptions.html) — withDependencyTypes(), withTargetFileName().
9. [Spring Boot — Actuator/Observability/Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — bridge/exporter, sampling, propagation.

Đối chiếu **đúng bản Spring Boot và Spring Modulith được khóa trong dependency management** khi triển khai ví dụ. API, điều kiện instrumentation và tên artifact có thể thay đổi theo nhánh phiên bản; mục tiêu bài này là đọc đúng bản chất **dependency type của graph** và bằng chứng **span của runtime**.
