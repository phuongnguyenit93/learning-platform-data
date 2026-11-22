# IntegrationObjectSupport logger và resource name

Trong Spring Integration, nhiều thành phần nội bộ cùng cần một số khả năng nền: nhận diện tên bean, truy cập `BeanFactory` và `ApplicationContext`, lấy `TaskScheduler` hoặc `ConversionService`, khởi tạo theo vòng đời Spring và ghi log. `IntegrationObjectSupport` gom các khả năng đó vào một lớp cơ sở để các channel, endpoint, handler và transformer có thể dùng chung.

Hai chi tiết thường gặp khi đọc mã nguồn hoặc chẩn đoán runtime là `logger` và tên định danh của component. Logger cho biết log thuộc về lớp Java nào; tên component cho biết instance nào trong integration flow đang phát log. Phân biệt hai thông tin này giúp đọc log chính xác, nhất là khi một lớp có nhiều bean hoặc nhiều endpoint cùng được tạo từ một kiểu handler.

## 1. Vai trò của IntegrationObjectSupport

`IntegrationObjectSupport` nằm trong package `org.springframework.integration.context`. Đây là lớp abstract dùng làm nền cho các thành phần của framework. Một số lớp kế thừa trực tiếp hoặc gián tiếp gồm `AbstractEndpoint`, `AbstractMessageChannel`, `AbstractTransformer`, `MessageHandlerSupport` và `AbstractConnectionFactory`.

Lớp này tích hợp với vòng đời Spring thông qua các interface như `BeanNameAware`, `BeanFactoryAware`, `ApplicationContextAware` và `InitializingBean`; đồng thời cung cấp định danh qua `NamedComponent`. Ở các phiên bản mới, nó còn triển khai `ComponentSourceAware` để giữ thông tin nguồn cấu hình của bean. Các tiện ích này phục vụ component của framework; code nghiệp vụ thông thường nên ưu tiên constructor injection và dependency injection tiêu chuẩn thay vì phụ thuộc trực tiếp vào `ApplicationContext`.

Một số khả năng thường được dùng từ lớp cơ sở:

| Thành phần | Mục đích |
|---|---|
| `logger` | Logger có sẵn cho lớp con |
| `getBeanName()` | Lấy tên bean do Spring container gán |
| `getComponentName()` | Lấy tên logic của component; mặc định dùng bean name nếu chưa đặt tên riêng |
| `setComponentName(String)` | Đặt tên logic riêng cho component |
| `getComponentType()` | Cung cấp loại component; lớp con có thể override |
| `getBeanFactory()` | Truy cập `BeanFactory` từ lớp con |
| `getApplicationContext()` | Truy cập `ApplicationContext` từ lớp con |
| `getTaskScheduler()` | Lấy scheduler dùng chung khi component cần lập lịch |
| `getConversionService()` | Lấy dịch vụ chuyển đổi kiểu |
| `getChannelResolver()` | Giải quyết tên channel thành `MessageChannel` |
| `onInit()` | Hook để lớp con thực hiện logic khởi tạo |

Không phải mọi lớp con đều dùng tất cả các tiện ích này. `IntegrationObjectSupport` cung cấp điểm chung; hành vi thực tế còn phụ thuộc vào lớp con và cấu hình của bean.

## 2. Logger được kế thừa

Trong Spring Integration 6.x, `IntegrationObjectSupport` cung cấp field `protected final LogAccessor logger`. Vì field có phạm vi `protected`, lớp con có thể ghi log trực tiếp mà không cần tạo một logger mới. `LogAccessor` là lớp tiện ích của Spring Core, cung cấp các mức `trace`, `debug`, `info`, `warn` và `error` cùng các phương thức kiểm tra mức log.

Ví dụ, một component có thể ghi log khi khởi tạo và khi nhận message:

~~~java
public class AuditMessageHandler extends IntegrationObjectSupport
        implements MessageHandler {

    @Override
    public String getComponentType() {
        return "audit-handler";
    }

    @Override
    protected void onInit() {
        logger.info(() -> "Initialized component '" + getComponentName()
                + "' with type '" + getComponentType() + "'");
    }

    @Override
    public void handleMessage(Message<?> message) {
        logger.debug(() -> "component='" + getComponentName()
                + "', messageId='" + message.getHeaders().getId() + "'");
    }
}
~~~

Các import chính:

~~~java
import org.springframework.integration.context.IntegrationObjectSupport;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
~~~

`logger` của lớp cơ sở được tạo theo class thực tế của instance, vì vậy logger category thường là tên đầy đủ của lớp con, chẳng hạn `com.example.integration.AuditMessageHandler`. Nếu có nhiều bean `AuditMessageHandler`, chúng vẫn dùng chung logger category này. Muốn biết instance nào phát log, hãy đưa `getComponentName()` vào nội dung log.

Các overload nhận `Supplier` cho phép tạo nội dung log một cách trì hoãn:

~~~java
logger.debug(() -> "component='" + getComponentName()
        + "', messageId='" + message.getHeaders().getId() + "'");
~~~

Đây là cách phù hợp cho thông điệp debug có phép nối chuỗi hoặc tính toán bổ sung. Khi mức DEBUG tắt, nội dung trong supplier không cần được tạo. Nếu ghi log lỗi, nên giữ exception để stack trace không bị mất:

~~~java
logger.error(exception,
        () -> "Failed to process message in '" + getComponentName() + "'");
~~~

Không nên khai báo lại một field tên `logger` trong lớp con nếu mục đích chỉ là dùng logger có sẵn. Việc che khuất field kế thừa làm người đọc khó biết câu lệnh đang dùng logger nào và có thể tạo ra hai logger category khác nhau. Nếu cần logger riêng cho một mục đích đặc biệt, hãy đặt tên field khác và giải thích rõ lý do.

### Logger category không phải component name

Logger category thuộc về hệ thống logging và thường được chọn theo class hoặc package. Có thể điều chỉnh mức log bằng cấu hình logging, ví dụ:

~~~yaml
logging:
  level:
    com.example.integration: DEBUG
~~~

Tên bean hoặc component không tự động trở thành logging category. Nếu cần lọc log của một instance cụ thể, hãy ghi tên component thành một field trong nội dung log hoặc đưa nó vào MDC theo quy tắc context propagation của ứng dụng. Với xử lý qua executor, không giả định MDC trên thread gửi tự động có mặt ở worker thread.

## 3. Tên bean và tên component

`IntegrationObjectSupport` có hai khái niệm định danh liên quan nhưng không đồng nhất.

**Bean name** là tên bean trong Spring container. Khi bean triển khai `BeanNameAware`, Spring gọi `setBeanName(String)` trong quá trình tạo bean. `IntegrationObjectSupport` cung cấp implementation `setBeanName` dạng `final`, nên lớp con không override phương thức này. Có thể đọc tên được gán bằng `getBeanName()`.

**Component name** là tên logic mà Spring Integration dùng để nhận diện component trong ngữ cảnh integration. Có thể đặt tên này bằng `setComponentName(String)`. `getComponentName()` trả về tên component đã đặt; nếu chưa đặt, nó dùng bean name làm giá trị mặc định.

Ví dụ, nếu một bean được khai báo với tên `auditMessageHandler` và không đặt component name riêng, kết quả thông thường là:

~~~java
getBeanName();      // "auditMessageHandler"
getComponentName(); // "auditMessageHandler"
~~~

Nếu đặt tên logic riêng:

~~~java
setComponentName("orders.audit");

getBeanName();      // "auditMessageHandler"
getComponentName(); // "orders.audit"
~~~

Tên riêng giúp tên component phản ánh vai trò trong flow thay vì chỉ phản ánh kiểu Java hoặc tên phương thức tạo bean. Nên chọn tên ngắn, ổn định và dễ tìm trong log, graph hoặc cấu hình giám sát.

| Thông tin | Ví dụ | Dùng để |
|---|---|---|
| Logger category | `com.example.integration.AuditMessageHandler` | Chọn mức log theo class/package |
| Bean name | `auditMessageHandler` | Định danh bean trong Spring container |
| Component name | `orders.audit` | Nhận diện component trong integration flow và thông tin vận hành |
| Component type | `audit-handler` | Mô tả loại component |

Trong một số tài liệu hoặc trao đổi, “resource name” có thể được dùng theo nghĩa tên để nhận diện một thành phần runtime. Với `IntegrationObjectSupport`, API cần xem trước tiên là `getComponentName()` và `getBeanName()`; lớp này không có một thuộc tính chung tên `resourceName` đại diện cho đường dẫn file. Nếu đang nói về file, classpath hoặc URL, đó là khái niệm `Resource`/`ResourceLoader` của Spring Core và là một cơ chế khác.

## 4. Đặt component name trong cấu hình Java

Khi tạo bean thủ công, có thể đặt component name trước khi Spring hoàn tất khởi tạo bean:

~~~java
@Configuration
@EnableIntegration
public class AuditIntegrationConfiguration {

    @Bean
    AuditMessageHandler auditMessageHandler() {
        AuditMessageHandler handler = new AuditMessageHandler();
        handler.setComponentName("orders.audit");
        return handler;
    }

    @Bean
    IntegrationFlow auditFlow(AuditMessageHandler auditMessageHandler) {
        return IntegrationFlow.from("orders.audit.input")
                .handle(auditMessageHandler)
                .get();
    }
}
~~~

Spring vẫn gán bean name `auditMessageHandler` thông qua `BeanNameAware`. Do component name đã được đặt, `getComponentName()` trả về `orders.audit`. Trong log, có thể ghi cả hai khi cần đối chiếu giữa cấu hình container và sơ đồ flow.

Đặt tên rõ ràng đặc biệt hữu ích khi một flow có nhiều endpoint cùng dùng một lớp handler, khi đăng ký flow động, hoặc khi cần so sánh tên trong log với tên component được hiển thị trong topology. Tránh dùng mã khách hàng, token hoặc giá trị thay đổi theo từng message làm component name; đó là dữ liệu runtime và sẽ khiến định danh component thiếu ổn định.

## 5. Component type, description và source

Ngoài tên, `NamedComponent` còn cung cấp `getComponentType()`. Lớp con có thể override để mô tả loại component, ví dụ `channel`, `service-activator` hoặc một loại riêng của ứng dụng. Tên và type có mục đích khác nhau: name nhận diện instance, type phân loại instance.

Ở các phiên bản có `ComponentSourceAware`, `IntegrationObjectSupport` còn có thể giữ:

- `getComponentDescription()`: mô tả dễ đọc về bean, thường lấy từ `BeanDefinition` nếu không được đặt riêng.
- `getComponentSource()`: đối tượng nguồn cấu hình, có thể là `null` nếu không có thông tin nguồn.
- `getBeanDescription()`: thông tin mô tả bean được cung cấp bởi lớp cơ sở.

Các metadata này hữu ích cho công cụ introspection và chẩn đoán cấu hình. Chúng không thay thế component name và không nên được dùng như một khóa định danh ổn định. Đặc biệt, component source có thể là đối tượng metadata cấu hình, không nhất thiết là chuỗi đường dẫn file.

## 6. Vòng đời khởi tạo và hook onInit

`IntegrationObjectSupport` triển khai `InitializingBean`. Spring gọi `afterPropertiesSet()` sau khi đã áp dụng các callback aware và cấu hình các thuộc tính bean. Phương thức `afterPropertiesSet()` của lớp cơ sở là `final`; nó chuẩn bị các tiện ích nội bộ cần thiết rồi gọi `onInit()` để lớp con thực hiện công việc khởi tạo.

Luồng khái quát:

~~~mermaid
flowchart TD
    A[Spring tạo bean] --> B[BeanNameAware.setBeanName]
    B --> C[BeanFactoryAware / ApplicationContextAware]
    C --> D[Áp dụng thuộc tính và dependency]
    D --> E[IntegrationObjectSupport.afterPropertiesSet]
    E --> F[Chuẩn bị tiện ích Integration]
    F --> G[Subclass.onInit]
    G --> H[Component sẵn sàng cho runtime]
~~~

Vì vậy, lớp con nên override `onInit()` cho logic cần chạy sau khi các dependency và context đã được cung cấp. Không override `afterPropertiesSet()`; phương thức này đã được lớp cơ sở quản lý. Cũng không nên dùng constructor để truy cập `BeanFactory`, `ApplicationContext` hoặc component name vì các callback của Spring chưa hoàn tất tại thời điểm constructor chạy.

Ví dụ, `onInit()` có thể kiểm tra cấu hình nội bộ và ghi một dòng log có component name. Tránh thực hiện công việc I/O dài hoặc khởi chạy thread không được quản lý tại đây; vòng đời và shutdown của tác vụ cần được thiết kế theo cơ chế quản lý lifecycle của Spring.

## 7. Dùng tên component để chẩn đoán runtime

Khi điều tra một message lỗi, nên kết hợp định danh component với khóa nhận diện message. Một log hữu ích có thể chứa:

- Component name và component type.
- Message ID để tìm một message cụ thể.
- Correlation ID để gom các message thuộc cùng một nghiệp vụ.
- Tên channel hoặc endpoint nếu component xử lý tại một điểm cụ thể.
- Kết quả xử lý, thời gian hoặc exception cần điều tra.

Ví dụ:

~~~java
logger.debug(() -> "component='" + getComponentName()
        + "', type='" + getComponentType()
        + "', messageId='" + message.getHeaders().getId()
        + "', correlationId='" + message.getHeaders().get("correlationId")
        + "'");
~~~

Không nên ghi toàn bộ payload chỉ để xác định message. Payload có thể chứa dữ liệu cá nhân, bí mật nghiệp vụ hoặc dữ liệu lớn. Các ID và tên component thường đủ để nối log với Message History, Integration Graph và metric. Nếu cần ghi thêm dữ liệu nghiệp vụ, hãy giới hạn trường được phép và áp dụng quy tắc che dữ liệu.

Một lưu ý khác: `IntegrationObjectSupport` chỉ cung cấp logger nền. Việc tắt/bật main-path logging qua `IntegrationManagement.setLoggingEnabled(...)` thuộc về các component triển khai `IntegrationManagement`, chẳng hạn nhiều channel và message handler. Không thể suy ra mọi subclass của `IntegrationObjectSupport` đều có thuộc tính `loggingEnabled` chỉ vì chúng kế thừa `logger`.

## 8. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Logger name chính là bean name | Logger category thường theo class; bean name và component name là metadata riêng |
| `getBeanName()` luôn bằng `getComponentName()` | Chỉ bằng nhau khi chưa đặt component name riêng |
| Component name là tên file cấu hình | Đây là tên logic của component; thông tin nguồn cấu hình được biểu diễn riêng |
| `IntegrationObjectSupport` có `resourceName` cho mọi component | API định danh chung là bean name/component name; đường dẫn `Resource` thuộc cơ chế Spring Core khác |
| Có thể override `afterPropertiesSet()` | Phương thức này là `final`; dùng `onInit()` cho logic khởi tạo của lớp con |
| Logger kế thừa tự động cho biết instance nào phát log | Nhiều instance cùng class có thể dùng chung logger category; thêm `getComponentName()` vào nội dung log |
| Mọi subclass đều có `setLoggingEnabled()` | Chỉ component triển khai `IntegrationManagement` mới có contract quản lý logging đó |

## 9. Checklist khi xây dựng component

- [ ] Chỉ kế thừa `IntegrationObjectSupport` khi component thực sự cần các tiện ích và lifecycle của Spring Integration.
- [ ] Dùng logger `protected` được kế thừa; tránh che khuất field `logger` nếu không có lý do rõ ràng.
- [ ] Đưa `getComponentName()` vào log để phân biệt các instance cùng class.
- [ ] Đặt component name ngắn, ổn định và có ý nghĩa trong flow.
- [ ] Override `getComponentType()` nếu công cụ quan sát cần phân loại component tùy chỉnh.
- [ ] Đặt cấu hình trước giai đoạn `afterPropertiesSet()` và dùng `onInit()` cho logic khởi tạo.
- [ ] Log message ID/Correlation ID thay vì ghi toàn bộ payload.
- [ ] Chỉ dùng `setLoggingEnabled()` khi component thực sự triển khai `IntegrationManagement`.

Khi tách bạch logger category, bean name và component name, log sẽ vừa cho biết lớp Java phát sự kiện vừa chỉ ra instance nào trong integration flow đang xử lý. `IntegrationObjectSupport` cung cấp các điểm nối này cùng lifecycle và một số tiện ích context; sử dụng đúng từng khái niệm giúp component dễ quan sát và dễ chẩn đoán hơn.

## Tài liệu tham khảo

- [Spring Integration 6.4 API: IntegrationObjectSupport](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/context/IntegrationObjectSupport.html)
- [Spring Integration API: NamedComponent](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/support/context/NamedComponent.html)
- [Spring Integration API: IntegrationManagement](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/support/management/IntegrationManagement.html)
- [Spring Framework API: LogAccessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/log/LogAccessor.html)
