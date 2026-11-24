# Sự kiện trước và sau khi đăng ký phiên bản dịch vụ

## 1. Vì sao cần theo dõi sự kiện đăng ký?

Trong Spring Cloud Service Discovery, một ứng dụng thường tự đăng ký instance của nó với registry khi khởi động. Registry có thể là Eureka, Consul hoặc một hệ thống discovery khác. Thông tin đăng ký thường gồm service ID, host, port, trạng thái và metadata như phiên bản ứng dụng.

Quá trình đăng ký là một mốc quan trọng trong vòng đời ứng dụng. Trước khi gửi thông tin đến registry, hệ thống có thể cần ghi log, kiểm tra thông tin instance hoặc chuẩn bị metric. Sau khi thao tác đăng ký hoàn tất, ứng dụng có thể ghi nhận trạng thái, phát tín hiệu giám sát hoặc thực hiện một công việc phụ trợ.

Spring Cloud Commons cung cấp các application event để quan sát hai thời điểm này:

- **InstancePreRegisteredEvent:** được phát trước khi cơ chế auto-registration thực hiện đăng ký instance.
- **InstanceRegisteredEvent:** được phát sau khi thao tác đăng ký của cơ chế auto-registration hoàn tất.

Các event giúp thành phần khác trong ứng dụng phản ứng theo vòng đời đăng ký mà không phải nhúng logic giám sát vào chính lớp cấu hình Eureka hoặc Consul.

## 2. Đăng ký instance trong Spring Cloud diễn ra như thế nào?

Spring Cloud định nghĩa abstraction chung để làm việc với registry:

- **Registration:** mô tả một instance cần đăng ký, thường cung cấp service ID, host, port, URI và metadata.
- **ServiceRegistry:** cung cấp các thao tác quản lý đăng ký như register, deregister, getStatus và setStatus.
- **DiscoveryClient:** cung cấp cách tra cứu service ID và danh sách instance tương ứng.

Mỗi nhà cung cấp discovery hiện thực các abstraction này. Ví dụ, Eureka có implementation tích hợp với Eureka Client; Consul có implementation giao tiếp với agent/server Consul.

Với cơ chế auto-registration, Spring Cloud khởi tạo thông tin Registration, sau đó thực hiện trình tự khái quát:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot Application
    participant Auto as Auto Service Registration
    participant Event as Application Event Publisher
    participant Registry as ServiceRegistry
    participant Backend as Eureka / Consul
    App->>Auto: Ứng dụng khởi động
    Auto->>Event: InstancePreRegisteredEvent
    Auto->>Registry: register(Registration)
    Registry->>Backend: Gửi thông tin instance
    Backend-->>Registry: Kết quả thao tác
    Registry-->>Auto: Hoàn tất lời gọi register
    Auto->>Event: InstanceRegisteredEvent
~~~

Sơ đồ mô tả luồng auto-registration phổ biến. Chi tiết thực thi và cấu hình có thể khác giữa các implementation và phiên bản Spring Cloud.

## 3. Sự khác nhau giữa hai event

| Event | Thời điểm | Dữ liệu có thể quan sát | Mục đích thường dùng |
|---|---|---|---|
| **InstancePreRegisteredEvent** | Ngay trước khi auto-registration gọi thao tác đăng ký | Registration đang chuẩn bị đăng ký | Ghi log thông tin instance, kiểm tra metadata, tạo dấu mốc bắt đầu |
| **InstanceRegisteredEvent** | Sau khi auto-registration hoàn tất lời gọi đăng ký | Cấu hình hoặc đối tượng cấu hình liên quan đến đăng ký | Ghi nhận kết quả, metric, audit hoặc kích hoạt tác vụ phụ trợ |

Hai event biểu thị hai mốc khác nhau. Nhận được InstancePreRegisteredEvent không có nghĩa registry đã nhận instance. InstanceRegisteredEvent cho biết bước đăng ký của luồng auto-registration đã chạy xong; nó không phải cam kết rằng mọi node trong một cụm đã đồng bộ hoặc mọi client đã nhìn thấy instance ngay lập tức.

### 3.1. InstancePreRegisteredEvent

Event này được phát trước khi Spring Cloud gọi ServiceRegistry.register(...) trong luồng auto-registration. Listener có thể đọc thông tin instance sắp được đăng ký, chẳng hạn service ID, host, port và metadata.

Một số ứng dụng dùng mốc này để:

- Ghi log cấu hình instance trước khi công bố.
- Kiểm tra service ID hoặc metadata đã được chuẩn bị.
- Tạo metric đánh dấu thời điểm bắt đầu đăng ký.
- Ghi nhận thông tin phiên bản ứng dụng để phục vụ audit.

Event không phải một API thay thế cho cấu hình Registration. Nếu cần thay đổi host, port, service ID hoặc metadata, hãy cấu hình đối tượng registration tương ứng trước khi quá trình auto-registration chạy.

### 3.2. InstanceRegisteredEvent

Event này được phát sau khi thao tác đăng ký của luồng auto-registration hoàn tất. Listener có thể dùng nó để:

- Ghi log ứng dụng đã thực hiện bước đăng ký.
- Tăng metric hoặc gửi tín hiệu nội bộ cho hệ thống giám sát.
- Ghi nhận thông tin cấu hình đã được sử dụng.
- Kích hoạt một tác vụ phụ trợ không nằm trong luồng đăng ký cốt lõi.

Không nên coi event này là một health check của ứng dụng. Việc đăng ký thành công chỉ xác nhận bước giao tiếp đăng ký đã hoàn tất theo implementation; nó không chứng minh mọi endpoint nghiệp vụ đều khỏe hoặc mọi peer đã nhận bản sao registry.

## 4. Lắng nghe event bằng Spring ApplicationEvent

Spring cho phép lắng nghe application event bằng annotation @EventListener. Hai event của Spring Cloud Commons nằm trong package org.springframework.cloud.client.serviceregistry.event.

Ví dụ dưới đây ghi log thông tin trước và sau đăng ký:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.serviceregistry.event.InstancePreRegisteredEvent;
import org.springframework.cloud.client.serviceregistry.event.InstanceRegisteredEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RegistrationLifecycleListener {

    private static final Logger log =
            LoggerFactory.getLogger(RegistrationLifecycleListener.class);

    @EventListener
    public void beforeRegistration(InstancePreRegisteredEvent event) {
        ServiceInstance instance = event.getRegistration();

        log.info(
                "Preparing registration: serviceId={}, host={}, port={}",
                instance.getServiceId(),
                instance.getHost(),
                instance.getPort()
        );
    }

    @EventListener
    public void afterRegistration(InstanceRegisteredEvent event) {
        Object config = event.getConfig();

        log.info(
                "Registration step completed; configType={}",
                config == null ? "none" : config.getClass().getName()
        );
    }
}
~~~

Listener đầu tiên lấy thông tin từ registration được gửi kèm event. Listener thứ hai ghi nhận kiểu cấu hình được cung cấp bởi event; không nên ép kiểu sang một lớp riêng của Eureka hoặc Consul nếu ứng dụng cần giữ tính độc lập với nhà cung cấp registry.

Các getter và chi tiết kiểu dữ liệu thuộc API Spring Cloud Commons của phiên bản đang dùng. Khi nâng Spring Cloud release train, hãy kiểm tra API tương ứng nếu mã nguồn listener phụ thuộc vào các chi tiết cụ thể.

### 4.1. Lắng nghe bằng ApplicationListener

Nếu muốn dùng interface thay cho @EventListener, có thể tạo listener riêng cho từng event:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.cloud.client.serviceregistry.event.InstancePreRegisteredEvent;
import org.springframework.stereotype.Component;

@Component
public class BeforeRegistrationListener
        implements ApplicationListener<InstancePreRegisteredEvent> {

    @Override
    public void onApplicationEvent(InstancePreRegisteredEvent event) {
        String serviceId = event.getRegistration().getServiceId();
        // Ghi log hoặc metric trước khi đăng ký.
    }
}
~~~

@EventListener thuận tiện khi một component lắng nghe nhiều loại event. ApplicationListener hữu ích khi muốn thể hiện rõ kiểu event ngay ở khai báo interface hoặc cần cấu hình listener theo cơ chế Spring tương ứng.

## 5. Metadata phiên bản của instance

Event đăng ký và metadata phiên bản là hai khái niệm liên quan nhưng khác nhau:

- Event mô tả **thời điểm** luồng auto-registration đang diễn ra.
- Metadata mô tả **thông tin** mà instance công bố cho registry.

Ví dụ, một ứng dụng có thể công bố version và build number trong metadata Eureka:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    metadata-map:
      version: 2.4.1
      build: 2026.11.24
~~~

Metadata này giúp người vận hành hoặc client khác phân biệt các instance đang chạy phiên bản nào. Tên khóa và giá trị do ứng dụng quy ước; Eureka không tự hiểu version là một chiến lược nâng cấp hay tự động chuyển traffic theo version chỉ vì metadata tồn tại.

Listener trước đăng ký có thể đọc metadata để ghi log hoặc kiểm tra. Listener sau đăng ký có thể ghi nhận phiên bản đã công bố trong metric hoặc audit. Nếu cần thay đổi metadata, hãy thực hiện ở cấu hình instance trước khi registration được tạo; không nên giả định event listener có thể sửa registration dùng chung.

## 6. Kết hợp sự kiện với ServiceRegistry

Khi cần thao tác registry theo cách chủ động, Spring Cloud cung cấp ServiceRegistry. Ví dụ minh họa sau thể hiện API tổng quát:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;
public class RegistryOperations<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;

    public RegistryOperations(ServiceRegistry<R> serviceRegistry) {
        this.serviceRegistry = serviceRegistry;
    }

    public void register(R registration) {
        serviceRegistry.register(registration);
    }

    public void deregister(R registration) {
        serviceRegistry.deregister(registration);
    }
}
~~~

Đây là ví dụ generic về abstraction; kiểu R phải là kiểu Registration cụ thể mà implementation registry đang sử dụng. Cách tạo và inject đối tượng RegistryOperations phụ thuộc implementation và cấu hình ứng dụng. Trong nhiều ứng dụng Spring Cloud, auto-registration đã thực hiện đăng ký khi khởi động, vì vậy không nên gọi thêm register thủ công nếu chưa có chủ đích rõ ràng.

Một điểm cần lưu ý: InstancePreRegisteredEvent và InstanceRegisteredEvent gắn với luồng auto-registration của Spring Cloud. Nếu ứng dụng tự gọi ServiceRegistry.register(...) ở một nơi khác, không nên mặc định rằng hai event trên sẽ tự động được phát cho lời gọi thủ công đó. Nếu cần event cho quy trình tự quản lý, ứng dụng phải chủ động định nghĩa và phát domain event phù hợp.

## 7. Thứ tự khởi động và ảnh hưởng của listener

Application event trong Spring mặc định được xử lý đồng bộ trên luồng phát event, trừ khi ứng dụng cấu hình cơ chế bất đồng bộ. Vì vậy, một listener thực hiện công việc lâu có thể kéo dài bước khởi động hoặc làm chậm quá trình auto-registration.

Một số nguyên tắc triển khai:

- Giữ listener ngắn gọn: ghi log, tăng counter hoặc chuyển một thông điệp nhẹ sang hệ thống xử lý khác.
- Tránh gọi dịch vụ bên ngoài với timeout dài ngay trong listener trước đăng ký.
- Không thực hiện migration dữ liệu hoặc công việc nặng trước khi registry được cập nhật.
- Nếu cần xử lý bất đồng bộ, cấu hình rõ executor và chính sách xử lý lỗi; bảo đảm tác vụ không phụ thuộc vào việc listener đã hoàn tất đồng bộ.
- Thiết kế tác vụ sau đăng ký có thể chạy lặp mà không gây tác dụng phụ ngoài ý muốn.

Nếu listener ném exception trong luồng đồng bộ, exception có thể ảnh hưởng đến luồng khởi động hoặc đăng ký tùy vị trí phát event và cách implementation xử lý lỗi. Hãy bắt và xử lý những lỗi có thể phục hồi bên trong listener; không nuốt các lỗi cấu hình nghiêm trọng mà hệ thống cần phát hiện.

## 8. Những điều event không bảo đảm

Khi thiết kế logic dựa trên event, cần phân biệt tín hiệu trong tiến trình ứng dụng với trạng thái của toàn hệ thống discovery:

| Nhận định | Có thể kết luận? | Giải thích |
|---|---|---|
| Nhận InstancePreRegisteredEvent nghĩa là instance đã có trong registry | Không | Event được phát trước thao tác đăng ký |
| Nhận InstanceRegisteredEvent nghĩa là luồng auto-registration đã thực hiện xong lời gọi đăng ký | Có, theo luồng auto-registration của implementation | Đây là mốc sau thao tác đăng ký trong luồng đó |
| Mọi peer Eureka đã có instance ngay khi nhận event sau đăng ký | Không | Replication giữa peer có thể có độ trễ |
| Mọi Eureka Client đã nhìn thấy instance | Không | Client có thể dùng registry cache và cập nhật theo chu kỳ |
| Instance đã vượt qua health check nghiệp vụ | Không | Đăng ký discovery không thay thế health check |
| Mã phiên bản trong metadata tự điều khiển routing | Không | Routing theo version cần chính sách riêng ở client hoặc gateway |

Đặc biệt, không nên dùng InstanceRegisteredEvent làm tín hiệu duy nhất để đưa ứng dụng vào trạng thái sẵn sàng nhận traffic. Hãy kết hợp health indicator, readiness probe và kiểm tra các dependency thiết yếu của ứng dụng.

## 9. Kiểm thử và quan sát vòng đời đăng ký

Có thể kiểm tra hành vi event bằng cách khởi động ứng dụng trong môi trường thử nghiệm và quan sát log:

1. Bật log ở listener trước đăng ký.
2. Khởi động ứng dụng với endpoint registry có thể truy cập.
3. Xác nhận log InstancePreRegisteredEvent xuất hiện trước log sau đăng ký.
4. Kiểm tra registry có instance với đúng service ID, host, port và metadata version.
5. Xác nhận listener sau đăng ký được gọi.
6. Thử khởi động khi registry không truy cập được để quan sát lỗi và hành vi retry của implementation.
7. Khởi động nhiều instance với metadata version khác nhau để xác nhận registry hiển thị đúng từng instance.

Nên ghi lại tối thiểu các thông tin sau trong log hoặc metric:

| Trường | Mục đích |
|---|---|
| Service ID | Xác định tên dịch vụ |
| Instance ID hoặc host/port | Phân biệt từng instance |
| Metadata version/build | Xác định phiên bản đang công bố |
| Event type | Phân biệt mốc trước và sau đăng ký |
| Timestamp | Đo thời gian từ lúc chuẩn bị đến khi đăng ký hoàn tất |
| Kết quả hoặc exception | Hỗ trợ điều tra lỗi đăng ký |

Tránh ghi dữ liệu nhạy cảm vào metadata hoặc log đăng ký. Metadata thường được nhiều client có quyền tra cứu registry nhìn thấy; chỉ công bố thông tin cần thiết cho discovery và vận hành.

## 10. Ví dụ luồng triển khai phiên bản mới

Giả sử payment-service đang chạy hai instance phiên bản 2.4.0. Đội triển khai đưa thêm một instance 2.5.0 vào hệ thống:

1. Instance mới khởi động và chuẩn bị registration với metadata version: 2.5.0.
2. InstancePreRegisteredEvent được phát; listener ghi nhận service ID và version sắp công bố.
3. Auto-registration gọi ServiceRegistry.register(...).
4. Khi thao tác đăng ký hoàn tất, InstanceRegisteredEvent được phát; listener ghi metric cho instance mới.
5. Registry cập nhật và các client dần nhận được instance mới theo cơ chế của provider.
6. Bộ cân bằng tải hoặc gateway áp dụng chính sách routing đã cấu hình để đưa traffic đến các instance phù hợp.

Sự kiện sau đăng ký chỉ là một mốc trong tiến trình triển khai. Chiến lược rolling update, canary hoặc blue-green cần được quản lý bởi nền tảng triển khai, gateway hoặc chính sách routing riêng. ServiceRegistry event không tự thực hiện chuyển traffic hay thay thế instance cũ.

~~~mermaid
flowchart TD
    START[Instance phiên bản mới khởi động] --> META[Chuẩn bị Registration và metadata version]
    META --> PRE[InstancePreRegisteredEvent]
    PRE --> REG[ServiceRegistry.register]
    REG --> POST[InstanceRegisteredEvent]
    POST --> SYNC[Registry và client cập nhật dần]
    SYNC --> ROUTE[Chính sách routing chọn instance]
~~~

## 11. Tổng kết

Spring Cloud Commons cung cấp InstancePreRegisteredEvent và InstanceRegisteredEvent để quan sát trước và sau bước auto-registration của một service instance. Event trước đăng ký phù hợp để ghi nhận thông tin sắp công bố; event sau đăng ký phù hợp để ghi log, metric hoặc kích hoạt công việc phụ trợ sau thao tác đăng ký.

Metadata như version và build là dữ liệu do ứng dụng công bố, còn event biểu thị mốc vòng đời. InstanceRegisteredEvent không bảo đảm toàn bộ peer hoặc client đã nhìn thấy instance, cũng không thay thế health check hay chính sách routing. Hãy giữ listener ngắn gọn, tránh tác vụ chặn luồng khởi động và kiểm thử hành vi với đúng implementation, phiên bản Spring Cloud và registry mà ứng dụng sử dụng.
