# Vai trò ContextRefresher trong quy trình refresh

> **Chương:** Làm mới cấu hình  
> **Module:** SPRING_CLOUD_CORE

Trong ứng dụng Spring Cloud, thay đổi một giá trị ở Config Server hoặc nguồn cấu hình bên ngoài chưa làm cho bean đang chạy tự động nhận giá trị mới. Ứng dụng cần một quy trình để đọc lại nguồn cấu hình, cập nhật `Environment`, xác định thuộc tính nào đã thay đổi và thông báo cho các thành phần cần phản ứng. **`ContextRefresher`** là thành phần điều phối quan trọng trong quy trình đó.

`ContextRefresher` thuộc Spring Cloud Context. Nó kết nối việc cập nhật môi trường cấu hình với các sự kiện thay đổi cấu hình và vòng đời của `RefreshScope`. Hiểu đúng vai trò này giúp phân biệt ba việc thường bị gọi chung là “refresh”: tải lại cấu hình, thông báo thuộc tính thay đổi và tạo lại target của bean refresh-scoped.

## 1. ContextRefresher nằm ở đâu trong kiến trúc?

Một ứng dụng Spring Boot có thể nhận cấu hình từ nhiều nguồn: `application.yml`, file theo profile, biến môi trường, tham số dòng lệnh, Spring Cloud Config hoặc nguồn cấu hình tùy biến. Spring đưa các nguồn đó vào `Environment` dưới dạng các `PropertySource`.

Khi cần refresh, ứng dụng phải thực hiện một chuỗi công việc:

1. Lưu lại trạng thái cấu hình hiện tại để làm mốc so sánh.
2. Nạp lại hoặc cập nhật các property source theo cơ chế cấu hình đang sử dụng.
3. So sánh giá trị trước và sau để tìm các key thay đổi.
4. Phát sự kiện để những thành phần quan tâm có thể xử lý các key đó.
5. Invalidate các target được quản lý bởi refresh scope để chúng có thể được tạo lại với cấu hình mới.

`ContextRefresher` điều phối chuỗi công việc này. Nó **không phải Config Server**, không phải scheduler theo dõi file và cũng không tự quyết định khi nào người vận hành cần refresh.

~~~mermaid
flowchart TB
    A["Nguồn cấu hình thay đổi"] --> B["Trigger refresh"]
    B --> C["ContextRefresher"]
    C --> D["Chụp trạng thái Environment hiện tại"]
    D --> E["Cập nhật / nạp lại property sources"]
    E --> F["So sánh trước và sau"]
    F --> G["EnvironmentChangeEvent"]
    G --> H["Listener xử lý key thay đổi"]
    F --> I["RefreshScope.refreshAll()"]
    I --> J["Invalidate target trong refresh scope"]
    J --> K["Lần gọi tiếp theo tạo target mới"]
~~~

Sơ đồ là mô hình khái niệm. Nguồn remote được tải lại bằng implementation cụ thể của Spring Cloud Config Client hoặc cơ chế cấu hình đang dùng; listener và bean được cập nhật phụ thuộc dependency, phiên bản và cách ứng dụng đăng ký chúng.

## 2. ContextRefresher làm những việc gì?

Trong Spring Cloud Context, `ContextRefresher` cung cấp các thao tác chính để làm mới môi trường cấu hình. API thường gặp gồm:

| Thao tác | Vai trò |
| --- | --- |
| `refresh()` | Điều phối refresh môi trường và làm mới refresh scope; trả về tập key được nhận diện là thay đổi |
| `refreshEnvironment()` | Cập nhật Environment, so sánh trạng thái trước/sau và phát `EnvironmentChangeEvent`; không tự gọi `RefreshScope.refreshAll()` |
| `updateEnvironment()` | Điểm mở rộng ở implementation cụ thể để nạp/cập nhật nguồn cấu hình |

Trong nhiều phiên bản, `ContextRefresher` là lớp nền có phương thức cập nhật môi trường được implementation cụ thể cung cấp. Spring Cloud Config Client hoặc cơ chế cấu hình tích hợp sẽ quyết định cách lấy lại dữ liệu. Vì vậy, khi đọc source hoặc debug, cần phân biệt API điều phối với implementation chịu trách nhiệm tải nguồn.

### 2.1. Chụp trạng thái trước khi cập nhật

Trước khi nạp lại cấu hình, refresher thu thập các thuộc tính hiện có từ Environment. Trạng thái này dùng làm mốc để xác định giá trị nào đã thay đổi.

Ví dụ trước refresh:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v1.internal"
    read-timeout: 3s
    max-attempts: 2
~~~

Sau khi nguồn cấu hình được cập nhật:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v2.internal"
    read-timeout: 2s
    max-attempts: 2
~~~

Các key có giá trị khác nhau là:

- `catalog.client.base-url`
- `catalog.client.read-timeout`

Key `catalog.client.max-attempts` không thay đổi. Tập key trả về giúp listener hoặc công cụ vận hành biết những thuộc tính nào đã được nhận diện là khác biệt.

### 2.2. Cập nhật Environment

Sau khi chụp trạng thái cũ, `ContextRefresher` gọi logic cập nhật môi trường của implementation. Tùy cách tích hợp, logic đó có thể dựng lại bootstrap/configuration context cần thiết, đọc lại Config Server hoặc nạp lại nguồn cấu hình theo cơ chế hỗ trợ.

Điều quan trọng là **Environment phải thực sự nhận giá trị mới**. Chỉ gọi `RefreshScope.refreshAll()` không tải cấu hình từ xa. Nếu property source chưa đổi, target mới được tạo ra vẫn có thể nhận giá trị cũ.

### 2.3. So sánh và trả về key thay đổi

Sau khi Environment được cập nhật, refresher so sánh snapshot trước và sau. Tập key thay đổi thường được biểu diễn dưới dạng `Set<String>`.

Ví dụ kết quả:

~~~text
[
  "catalog.client.base-url",
  "catalog.client.read-timeout"
]
~~~

Đây là thông tin hữu ích để:

- Kiểm tra lần refresh có thay đổi cấu hình hay không.
- Xác định listener nào cần xử lý.
- Ghi log/metric về các key đã đổi mà không in giá trị nhạy cảm.
- Viết kiểm thử xác nhận đúng property được cập nhật.

Tập key này không phải bản sao đầy đủ của cấu hình mới và cũng không cho biết mọi bean đã được tạo lại. Nó chỉ mô tả những property được nhận diện là thay đổi theo phép so sánh của implementation.

## 3. EnvironmentChangeEvent thông báo thay đổi cấu hình

Sau khi xác định các key thay đổi, quy trình refresh phát `EnvironmentChangeEvent` trong ApplicationContext. Event mang theo tập key đã thay đổi để các listener có thể phản ứng.

~~~java
import java.util.Set;

import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationChangeLogger {

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        Set<String> changedKeys = event.getKeys();

        // Chỉ ghi tên key; không ghi giá trị cấu hình hoặc secret.
        changedKeys.forEach(key ->
                System.out.println("Configuration changed: " + key));
    }
}
~~~

Đây là ví dụ listener quan sát thay đổi. Trong hệ thống thật nên dùng logger/metrics thay vì `System.out`, đồng thời lọc key nhạy cảm nếu tên property cũng tiết lộ thông tin nội bộ.

### 3.1. Event và listener có trách nhiệm gì?

`EnvironmentChangeEvent` cho biết Environment đã được cập nhật và key nào thay đổi. Listener quyết định phải làm gì với thông tin đó.

Một số thành phần Spring Cloud có thể lắng nghe event để:

- Rebind các bean cấu hình có cơ chế hỗ trợ.
- Cập nhật cấu hình logging.
- Thực hiện hành động nội bộ phù hợp với một số property cụ thể.

Không nên giả định mọi singleton hoặc mọi bean trong ApplicationContext đều tự động được tạo lại. Một bean singleton giữ giá trị trong field có thể vẫn giữ snapshot cũ nếu không có cơ chế rebind hoặc refresh tương ứng.

### 3.2. Rebind @ConfigurationProperties khác với refresh scope

Hai cơ chế có mục đích khác nhau:

| Cơ chế | Điều được cập nhật | Cách hoạt động |
| --- | --- | --- |
| Rebind cấu hình | Bean được quản lý bởi cơ chế rebinding và hỗ trợ cập nhật | Listener xử lý event và bind lại các property phù hợp |
| Refresh scope | Target của bean thuộc `@RefreshScope` | Cache target bị invalidate; proxy tạo/lấy target mới ở lần gọi sau |
| Singleton thông thường | Không mặc nhiên được tạo lại | Field đã gán trong constructor vẫn có thể giữ giá trị cũ |

Khả năng rebind phụ thuộc kiểu bean, cách binding và phiên bản Spring Cloud/Spring Boot. Các cấu hình immutable hoặc constructor-bound không nên được giả định là có thể cập nhật bằng cách thay field; cần chọn cách tạo lại bean hoặc thiết kế bean refresh-scoped nếu yêu cầu runtime update.

## 4. ContextRefresher kết hợp với RefreshScope

`RefreshScope` quản lý target của các bean được đánh dấu `@RefreshScope`. Consumer thường tương tác với bean thông qua scoped proxy. Khi refresh scope được làm mới, target đang cache bị loại bỏ; lần gọi tiếp theo qua proxy sẽ tạo target mới.

Trong quy trình `ContextRefresher.refresh()`, bước refresh scope thường được thực hiện sau khi Environment đã được cập nhật và event thay đổi cấu hình đã được phát.

~~~mermaid
sequenceDiagram
    participant Trigger as Refresh endpoint / Bus
    participant Refresher as ContextRefresher
    participant Env as Environment
    participant Event as Event listeners
    participant Scope as RefreshScope
    participant Proxy as Scoped proxy
    participant Target as Target bean

    Trigger->>Refresher: refresh()
    Refresher->>Env: Đọc snapshot cũ
    Refresher->>Env: Nạp cấu hình mới
    Refresher->>Refresher: Tính tập key thay đổi
    Refresher->>Event: Publish EnvironmentChangeEvent
    Refresher->>Scope: refreshAll()
    Scope->>Target: Hủy/invalidate target đang cache
    Note over Proxy,Target: Proxy và singleton consumer vẫn tồn tại
    Proxy->>Scope: Lời gọi tiếp theo
    Scope->>Target: Tạo target mới khi cần
    Target-->>Proxy: Giá trị cấu hình mới
~~~

Cần phân biệt:

- `ContextRefresher` điều phối quá trình cập nhật Environment.
- `EnvironmentChangeEvent` thông báo các key thay đổi.
- `RefreshScope` quản lý việc invalidate target.
- Scoped proxy chuyển lời gọi đến target hiện tại.

`ContextRefresher` không tự thay thế mọi bean singleton. Nó cũng không bảo đảm một HTTP client hoặc connection pool được tạo từ cấu hình cũ sẽ tự cập nhật, trừ khi chính đối tượng đó được tái tạo hoặc được thiết kế để đọc cấu hình động.

## 5. Phân biệt refreshEnvironment() và refresh()

Hai phương thức này dễ bị gọi nhầm vì tên gần nhau.

### 5.1. Chỉ cập nhật Environment

`refreshEnvironment()` tập trung vào việc cập nhật nguồn cấu hình, tính các key thay đổi và phát `EnvironmentChangeEvent`.

Dùng riêng thao tác này khi cần cập nhật Environment và để các listener xử lý theo cơ chế riêng. Nó không tương đương với việc invalidate toàn bộ target refresh-scoped.

### 5.2. Refresh đầy đủ

`refresh()` điều phối cập nhật Environment, phát event và làm mới refresh scope. Đây là thao tác thường được dùng khi mục tiêu là để các bean refresh-scoped tạo lại target theo cấu hình mới.

Có thể hình dung:

| Bước | `refreshEnvironment()` | `refresh()` |
| --- | --- | --- |
| Cập nhật nguồn/Environment | Có | Có |
| So sánh key trước/sau | Có | Có |
| Phát `EnvironmentChangeEvent` | Có | Có |
| Gọi `RefreshScope.refreshAll()` | Không | Có |
| Trả tập key thay đổi | Có | Có |

Khi gọi `refresh()`, không nên gọi thêm `refreshEnvironment()` trước đó chỉ để “chắc chắn”, vì thao tác này có thể tải cấu hình và phát event hai lần. Hãy dùng đúng API theo mục đích.

## 6. Ai kích hoạt ContextRefresher?

`ContextRefresher` không tự theo dõi Config Server. Một thành phần khác phải yêu cầu refresh.

### 6.1. Refresh endpoint của Actuator

Khi ứng dụng có Spring Cloud Context và tích hợp Actuator tương ứng, `RefreshEndpoint` có thể cung cấp endpoint quản trị, thường được truy cập qua:

~~~http
POST /actuator/refresh
~~~

Ví dụ cấu hình expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - refresh
~~~

Cấu hình này chỉ minh họa việc expose endpoint; dependency, phiên bản, endpoint enablement và base path có thể ảnh hưởng URL thực tế. Không expose endpoint refresh công khai. Cần xác thực, phân quyền, giới hạn network và audit ai đã yêu cầu refresh.

### 6.2. Spring Cloud Bus

Trong hệ thống có nhiều instance, gọi refresh endpoint trên một instance thường chỉ làm mới instance nhận request đó. Nếu muốn truyền sự kiện tới nhiều instance, có thể tích hợp Spring Cloud Bus.

Một luồng điển hình:

1. Nguồn cấu hình trung tâm được cập nhật.
2. Một thao tác quản trị hoặc Config Monitor phát sự kiện qua Bus.
3. Các instance nhận sự kiện refresh phù hợp.
4. Listener ở từng instance gọi quy trình refresh cục bộ.
5. Mỗi instance cập nhật Environment và refresh target của chính nó.

Bus phân phối sự kiện; `ContextRefresher` vẫn thực hiện cập nhật cấu hình ở từng application context. Không nên coi một lần gọi local là bằng chứng tất cả replica đã nhận cấu hình mới.

### 6.3. Gọi từ code nội bộ

Một bean quản trị có thể inject `ContextRefresher` nếu ứng dụng có implementation phù hợp:

~~~java
import java.util.Set;

import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.stereotype.Service;

@Service
public class ConfigurationRefreshService {

    private final ContextRefresher contextRefresher;

    public ConfigurationRefreshService(ContextRefresher contextRefresher) {
        this.contextRefresher = contextRefresher;
    }

    public Set<String> refreshConfiguration() {
        return contextRefresher.refresh();
    }
}
~~~

Đây là ví dụ về cách gọi API từ một thành phần nội bộ. Không nên tạo endpoint tùy tiện bao quanh method này nếu chưa có kiểm soát quyền, giới hạn tần suất và audit. Trong nhiều ứng dụng, endpoint Actuator hoặc Bus đã là đường kích hoạt được quản lý tập trung.

## 7. ContextRefresher không phải ApplicationContext.refresh()

Tên hai API khá giống nhau nhưng trách nhiệm khác nhau.

| API/khái niệm | Ý nghĩa |
| --- | --- |
| `ContextRefresher.refresh()` | Cập nhật cấu hình hiện tại, phát event và invalidate refresh scope |
| `ConfigurableApplicationContext.refresh()` | Khởi tạo hoặc refresh ApplicationContext theo lifecycle của Spring container |
| `RefreshScope.refreshAll()` | Invalidate các target đang cache trong refresh scope |
| `EnvironmentChangeEvent` | Sự kiện thông báo tập key cấu hình thay đổi |

Không gọi `ApplicationContext.refresh()` để thay thế refresh cấu hình runtime. Lifecycle refresh của ApplicationContext là thao tác cấp container, có thể liên quan tới việc khởi tạo bean và quản lý tài nguyên của toàn context; nó không phải cơ chế cập nhật property source thông thường của Spring Cloud.

## 8. Những gì được cập nhật và những gì không tự cập nhật?

Một lần refresh không có nghĩa toàn bộ ứng dụng được khởi động lại. Kết quả phụ thuộc bean được quản lý như thế nào.

| Thành phần | Hành vi sau refresh |
| --- | --- |
| Environment/property sources | Được cập nhật bởi implementation nạp cấu hình |
| Key được trả về | Phản ánh các property được nhận diện là thay đổi |
| Listener của EnvironmentChangeEvent | Có thể xử lý/rebind các key theo trách nhiệm |
| Bean `@RefreshScope` | Target cache bị invalidate; tạo lại khi được gọi |
| Scoped proxy | Thường vẫn là tham chiếu được consumer giữ |
| Singleton thông thường | Không mặc nhiên được tạo lại |
| Field đã sao chép giá trị cấu hình | Không tự thay đổi nếu không có cơ chế cập nhật |
| HTTP client/pool đã tạo | Không tự cập nhật nếu không được tái tạo hoặc hỗ trợ cập nhật |
| Static field | Không tự thay đổi chỉ vì Environment được cập nhật |

Ví dụ, nếu singleton tạo `WebClient` trong constructor từ một base URL, việc refresh bean giữ chuỗi URL không tự thay đổi `WebClient` đã tạo. Có thể đặt factory/client phù hợp trong refresh scope hoặc thiết kế client để lấy endpoint qua một proxy ở thời điểm gửi request.

## 9. Xử lý lỗi và giới hạn vận hành

Refresh là thao tác thay đổi cấu hình đang chạy nên cần chính sách rõ ràng.

### 9.1. Nguồn cấu hình không truy cập được

Nếu Config Server hoặc nguồn tùy biến không phản hồi:

- Đặt timeout hữu hạn cho request lấy cấu hình.
- Quyết định nguồn đó bắt buộc hay tùy chọn.
- Nếu bắt buộc, báo lỗi rõ và không âm thầm dùng cấu hình không hợp lệ.
- Nếu cho phép fallback, ghi rõ giá trị fallback và cách quan sát.
- Không giả định Environment luôn được rollback nguyên tử về snapshot cũ nếu implementation cập nhật nguồn thất bại giữa chừng; cần kiểm thử hành vi của phiên bản và nguồn cấu hình thực tế.

### 9.2. Nhiều lần refresh đồng thời

Một số implementation đồng bộ hóa thao tác refresh trong phạm vi một refresher instance, nhưng điều đó không tạo ra khóa phân tán giữa các replica. Hệ thống vẫn cần điều phối nếu nhiều node có thể nhận nhiều sự kiện gần nhau.

Tránh phát refresh liên tục theo từng request. Nên gom thay đổi cấu hình, đặt giới hạn tần suất và theo dõi thời gian hoàn tất. Nếu nhiều refresh chồng nhau, target có thể bị invalidate nhiều lần và gây tải khởi tạo tăng.

### 9.3. Request đang sử dụng target cũ

Refresh scope không có nghĩa mọi request đang chạy lập tức dừng. Một request có thể đã lấy target trước thời điểm invalidate. Đối tượng đang thực thi cần hoàn tất hoặc xử lý lỗi theo chính sách của nó. Với client giữ connection, scheduler hoặc pool, cần destruction callback và cơ chế graceful shutdown phù hợp.

### 9.4. Refresh scope rộng quá mức

Nếu quá nhiều bean được đánh dấu `@RefreshScope`, một lần refresh có thể invalidate nhiều target cùng lúc. Lần truy cập tiếp theo có thể tạo lại nhiều client, cache hoặc tài nguyên, gây đột biến kết nối và latency.

Chỉ đánh dấu các bean có thể tái tạo an toàn. Không đưa trạng thái nghiệp vụ lâu dài vào refresh-scoped target nếu trạng thái đó phải tồn tại qua refresh.

## 10. Kiểm thử vai trò ContextRefresher

Kiểm thử nên tách thành nhiều lớp để biết lỗi nằm ở đâu.

### 10.1. Kiểm tra tập key thay đổi

Tạo một cấu hình test có giá trị ban đầu, cập nhật nguồn cấu hình theo cách mà implementation test hỗ trợ, rồi xác nhận refresher trả về các key thay đổi. Không kiểm tra giá trị secret trong assertion hoặc log.

Ví dụ assertion về kết quả:

~~~java
Set<String> changedKeys = contextRefresher.refresh();

assertThat(changedKeys)
        .contains("catalog.client.base-url")
        .doesNotContain("catalog.client.max-attempts");
~~~

Đoạn assertion giả định test fixture chỉ thay đổi base URL; cách cung cấp property source mới phụ thuộc implementation Config Data hoặc legacy bootstrap đang kiểm thử.

### 10.2. Kiểm tra event

Đăng ký listener test hoặc dùng cơ chế ghi nhận event của Spring test để xác nhận `EnvironmentChangeEvent` được phát và chứa đúng key. Cần phân biệt event có được phát với listener nghiệp vụ có xử lý thành công hay không.

### 10.3. Kiểm tra refresh-scoped target

Sau khi Environment có giá trị mới, gọi `refresh()` hoặc thao tác scope phù hợp, rồi gọi proxy. Xác nhận target mới đọc được cấu hình mới và consumer singleton vẫn tồn tại.

### 10.4. Kiểm tra từng instance

Trong môi trường nhiều replica, kiểm tra từng instance:

- Instance có nhận refresh event không?
- Environment của instance đã cập nhật chưa?
- Tập key thay đổi có giống kỳ vọng không?
- Refresh-scoped target có được tạo lại ở lần gọi tiếp theo không?
- Log/metrics có cho thấy lỗi hoặc độ trễ không?

Một endpoint trả HTTP thành công ở một node không đủ chứng minh toàn bộ cụm đã refresh.

## 11. Ví dụ chẩn đoán theo triệu chứng

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| Config Server đã đổi nhưng `Environment.getProperty()` vẫn cũ | Trigger có chạy không; implementation có tải lại remote source không; profile/label có đúng không |
| Environment đã mới nhưng bean refresh-scoped vẫn trả giá trị cũ | `RefreshScope` có invalidate target không; consumer có gọi qua proxy không |
| `ContextRefresher.refresh()` trả tập key rỗng | Giá trị có thực sự khác không; property source có được cập nhật không; phép diff có nhìn thấy key không |
| Singleton vẫn giữ endpoint cũ | Singleton có sao chép URI vào field hoặc tạo client bất biến từ giá trị cũ không |
| Một replica cập nhật, replica khác không | Refresh endpoint được gọi ở node nào; Bus/event có phân phối tới tất cả node không |
| Refresh thành công nhưng client HTTP vẫn gọi host cũ | Client đã được tái tạo chưa; client có đọc endpoint qua proxy tại thời điểm gọi không |
| Refresh gây latency tăng | Có quá nhiều target bị invalidate; việc tạo lại client/pool có tạo tải đột biến không |
| Cấu hình lỗi sau refresh | Kiểm tra validation, schema, timeout và hành vi fallback của nguồn |

Khi điều tra, ghi lại thời điểm refresh, instance ID, application name, profile, tập key thay đổi và kết quả xử lý. Không ghi giá trị secret hoặc toàn bộ Environment.

## 12. Quy trình refresh đề xuất

Trong một ứng dụng Spring Cloud, có thể tổ chức quy trình như sau:

1. **Cập nhật nguồn:** thay đổi cấu hình ở Config Server hoặc nguồn cấu hình được quản lý.
2. **Kích hoạt:** gọi endpoint quản trị có bảo vệ hoặc phát sự kiện qua Spring Cloud Bus.
3. **Nạp lại:** implementation phù hợp cập nhật property sources trong Environment.
4. **So sánh:** ContextRefresher xác định các key thay đổi.
5. **Thông báo:** phát EnvironmentChangeEvent để listener phù hợp xử lý.
6. **Invalidate target:** refresh scope loại bỏ target đang cache.
7. **Tạo lại khi cần:** lần gọi tiếp theo qua scoped proxy tạo target mới.
8. **Xác minh:** kiểm tra key, bean, từng replica, log và metric.
9. **Khôi phục:** nếu cấu hình mới không hợp lệ, áp dụng quy trình rollback hoặc phát hành cấu hình sửa lỗi; không mặc định refresh tự rollback.

Nên thử quy trình này trên staging với ít nhất một lần thay đổi endpoint/timeout có thể quan sát được. Đồng thời kiểm tra hành vi khi Config Server không truy cập được và khi một replica bỏ lỡ sự kiện.

## 13. Điểm cần ghi nhớ

`ContextRefresher` là **bộ điều phối quy trình refresh cấu hình** trong Spring Cloud Context. Nó phối hợp việc cập nhật Environment, so sánh các property trước/sau, phát `EnvironmentChangeEvent` và làm mới `RefreshScope` khi dùng thao tác `refresh()`. Nó không tự theo dõi Config Server, không tự phân phối sự kiện tới mọi replica và không khởi động lại toàn bộ ApplicationContext.

Muốn refresh hoạt động đúng, cần bảo đảm nguồn cấu hình được tải lại, listener xử lý đúng các key thay đổi, bean cần tái tạo được đặt trong refresh scope và consumer tiếp tục gọi qua scoped proxy. Phân biệt rõ Environment refresh, event rebinding và target invalidation là nền tảng để thiết kế cấu hình runtime có thể quan sát, kiểm thử và vận hành an toàn trong **SPRING_CLOUD_CORE**.
