# AvailabilityChangeEvent và thời điểm đổi trạng thái

Một ứng dụng Spring Boot có thể đã tạo xong các bean và mở cổng HTTP nhưng vẫn chưa sẵn sàng phục vụ request. Ngược lại, ứng dụng có thể đang chạy bình thường nhưng tạm thời không nên nhận traffic vì chuẩn bị bảo trì, đang rút khỏi cụm hoặc thiếu một điều kiện nghiệp vụ thiết yếu. Khi bắt đầu dừng, nó còn cần thông báo cho hệ thống điều phối ngừng gửi request mới trước khi các tài nguyên bị đóng.

Spring Boot cung cấp **ApplicationAvailability** để mô tả trạng thái khả dụng của tiến trình và **AvailabilityChangeEvent** để công bố sự thay đổi trạng thái đó. Hai khía cạnh được theo dõi là:

- **Liveness**: ứng dụng còn có khả năng hoạt động đúng hay đã rơi vào tình trạng hỏng nghiêm trọng và cần được khởi động lại?
- **Readiness**: ở thời điểm hiện tại ứng dụng có nên nhận traffic mới hay chưa?

Trạng thái này có ý nghĩa đặc biệt khi triển khai ứng dụng trên Kubernetes, hệ thống có load balancer hoặc bất kỳ nền tảng nào theo dõi health/readiness. Quan trọng hơn cả tên API là **thời điểm** thay đổi trạng thái: trước khi context hoàn tất, sau khi các startup runner chạy, trong giai đoạn nhận request và khi shutdown.

## 1. Vì sao cần phân biệt liveness và readiness?

Hãy xem một ứng dụng xử lý đơn hàng. Khi process vừa bắt đầu:

1. Spring đọc cấu hình và tạo các bean.
2. ApplicationContext được refresh.
3. Các ApplicationRunner thực hiện bước chuẩn bị bắt buộc.
4. Ứng dụng mới có thể phục vụ request ổn định.

Trong khoảng thời gian từ bước 1 đến bước 4, process Java vẫn đang chạy, nhưng việc đưa traffic vào quá sớm có thể khiến API truy cập dữ liệu chưa chuẩn bị xong.

Ở thời điểm khác, ứng dụng đang phục vụ bình thường nhưng cần chuyển sang bảo trì trong vài phút. Process vẫn còn sống và có thể tự phục hồi; khởi động lại nó không phải giải pháp phù hợp. Thay vào đó, load balancer nên ngừng gửi request mới.

Hai câu hỏi cần trả lời độc lập:

| Câu hỏi | Trạng thái liên quan | Hành động điển hình của nền tảng |
|---|---|---|
| Process có đang hoạt động đúng, hay bị hỏng không thể tự phục hồi? | **Liveness** | Cân nhắc restart khi liveness thất bại. |
| Instance này có thể nhận request mới ngay bây giờ không? | **Readiness** | Đưa vào hoặc loại khỏi tập endpoint nhận traffic. |

Một ứng dụng có thể **live nhưng chưa ready**. Đây là trạng thái hoàn toàn hợp lệ trong quá trình khởi động, bảo trì và graceful shutdown.

## 2. Các trạng thái mà Spring Boot cung cấp

Các kiểu chính nằm trong package:

~~~java
org.springframework.boot.availability
~~~

Những API quan trọng gồm:

- **ApplicationAvailability**: đọc trạng thái khả dụng hiện tại.
- **AvailabilityState**: giao diện chung của một loại trạng thái.
- **LivenessState**: tập trạng thái liveness.
- **ReadinessState**: tập trạng thái readiness.
- **AvailabilityChangeEvent**: sự kiện công bố thay đổi trạng thái.

### 2.1. LivenessState

Spring Boot có hai giá trị liveness cơ bản:

| Giá trị | Ý nghĩa |
|---|---|
| **LivenessState.CORRECT** | Ứng dụng đang được coi là hoạt động đúng ở khía cạnh liveness. |
| **LivenessState.BROKEN** | Ứng dụng được coi là hỏng nghiêm trọng; restart có thể là hành động phục hồi phù hợp. |

Đừng hiểu CORRECT là mọi chức năng, database và dịch vụ ngoài đều chắc chắn hoạt động. Nó chỉ phản ánh đánh giá liveness của process.

### 2.2. ReadinessState

Spring Boot có hai giá trị readiness cơ bản:

| Giá trị | Ý nghĩa |
|---|---|
| **ReadinessState.ACCEPTING_TRAFFIC** | Instance được coi là sẵn sàng nhận traffic. |
| **ReadinessState.REFUSING_TRAFFIC** | Instance chưa nên nhận traffic mới. |

REFUSING_TRAFFIC có thể là trạng thái bình thường khi app đang khởi động hoặc dừng; nó không tự có nghĩa process gặp lỗi nghiêm trọng.

### 2.3. Ma trận các tình huống

| Liveness | Readiness | Cách hiểu điển hình |
|---|---|---|
| CORRECT | ACCEPTING_TRAFFIC | Instance đang hoạt động và sẵn sàng nhận request. |
| CORRECT | REFUSING_TRAFFIC | Process còn khỏe nhưng chưa sẵn sàng, đang bảo trì hoặc chuẩn bị dừng. |
| BROKEN | REFUSING_TRAFFIC | Process gặp vấn đề nghiêm trọng hoặc chưa tới mốc được coi là live. |
| BROKEN | ACCEPTING_TRAFFIC | Trạng thái bất thường hoặc có cập nhật không nhất quán; không nên thiết kế hệ thống dựa vào tổ hợp này. |

Trong thiết kế thông thường, liveness và readiness thay đổi theo từng giai đoạn riêng; không nên dùng một cờ boolean duy nhất để biểu diễn cả hai.

## 3. ApplicationAvailability: đọc trạng thái hiện tại

Spring Boot cung cấp **ApplicationAvailability** dưới dạng bean để các thành phần trong ứng dụng đọc trạng thái được công bố.

Ví dụ:

~~~java
package com.example.availability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityInspector {

    private final ApplicationAvailability availability;

    public AvailabilityInspector(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean canReceiveTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }

    public boolean isLive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }
}
~~~

Interface này còn có API tổng quát:

~~~java
ReadinessState readiness = availability.getState(
        ReadinessState.class,
        ReadinessState.REFUSING_TRAFFIC);
~~~

Đối số thứ hai là giá trị fallback nếu chưa có trạng thái được công bố cho loại đó. Có thể dùng cách này khi muốn diễn đạt rõ trạng thái mặc định an toàn trong một đoạn code.

### 3.1. ApplicationAvailability phản ánh trạng thái đã được công bố

Khi một AvailabilityChangeEvent được xử lý, bean quản lý availability của Spring Boot cập nhật trạng thái gần nhất theo loại. Một nơi khác có thể truy vấn nó bằng ApplicationAvailability.

~~~text
AvailabilityChangeEvent
        │
        ▼
ApplicationAvailability cập nhật state
        │
        ├── getLivenessState()
        │
        └── getReadinessState()
~~~

Đây là trạng thái **trong một application process**. Nó không phải kho dữ liệu bền vững hoặc trạng thái chung của toàn bộ cluster. Mỗi replica có ApplicationAvailability của riêng mình.

### 3.2. Đọc state không thay thế việc kiểm tra chức năng

Ví dụ, readiness là ACCEPTING_TRAFFIC nhưng một endpoint nghiệp vụ có thể vẫn lỗi vì dịch vụ ngoài tạm thời không đáp ứng. Trạng thái availability chỉ có giá trị khi những điều kiện cần thiết được hệ thống giám sát và phản ánh đúng.

Vì vậy, không nên kết luận rằng một HTTP API sẽ thành công chỉ từ kết quả getReadinessState().

## 4. AvailabilityChangeEvent: công bố thay đổi

**AvailabilityChangeEvent** là một Spring application event mang một giá trị AvailabilityState. Khi event được publish trong ApplicationContext, các listener phù hợp có thể xử lý nó; Spring Boot cũng dùng cơ chế này để theo dõi trạng thái hiện tại.

Cách công bố trạng thái phổ biến:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

public class ReadinessController {

    private final ApplicationEventPublisher events;

    public ReadinessController(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Trong code thật, lớp này cần được đăng ký làm bean, và việc gọi các method phải nằm trong một quy trình vận hành được kiểm soát. Ví dụ chỉ minh họa cách publish; không tự mở endpoint công khai để người ngoài đổi trạng thái ứng dụng.

### 4.1. Event gồm những thông tin gì?

Một AvailabilityChangeEvent có:

- **State**: giá trị cụ thể như ReadinessState.REFUSING_TRAFFIC.
- **Source**: đối tượng nguồn gắn với event.
- Ngữ cảnh publish: application event được gửi tới các listener phù hợp qua cơ chế event của Spring.

Ví dụ listener:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessLogListener {

    @EventListener
    public void onReadinessChanged(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("Readiness changed to " + event.getState());
    }
}
~~~

Với hệ thống logging thật, nên dùng SLF4J thay System.out, gắn thêm timestamp, instance ID và lý do chuyển trạng thái do thành phần nghiệp vụ ghi nhận.

### 4.2. Publish không đồng nghĩa dừng HTTP server

Khi publish REFUSING_TRAFFIC, Spring Boot cập nhật trạng thái readiness, nhưng **không có nghĩa mọi socket HTTP lập tức bị đóng hoặc mọi client bị chặn ngay tại thời điểm đó**.

Trong hệ thống có readiness probe, bộ điều phối cần:

1. Gọi probe.
2. Nhận kết quả instance chưa ready.
3. Cập nhật danh sách endpoint có thể nhận traffic.
4. Chuyển traffic mới sang instance khác.

Các bước này có độ trễ. Những kết nối hiện tại hoặc request đang chạy vẫn có thể tiếp tục. Để dừng nhận request một cách có kiểm soát, cần phối hợp readiness, traffic draining và graceful shutdown.

## 5. Các mốc startup liên quan đến availability

Thời điểm Spring Boot công bố trạng thái có thể được hình dung như sau:

~~~text
SpringApplication.run(...)
          │
          ▼
Chuẩn bị Environment / ApplicationContext
          │
          ▼
ApplicationContext.refresh()
          │
          ├── Tạo các singleton cần khởi tạo
          └── Callback của bean
          │
          ▼
ApplicationStartedEvent
          │
          ▼
AvailabilityChangeEvent(LivenessState.CORRECT)
          │
          ▼
ApplicationRunner / CommandLineRunner
          │
          ▼
ApplicationReadyEvent
          │
          ▼
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
          │
          ▼
Ứng dụng ở trạng thái ready thông thường
~~~

Đây là trình tự khởi động thành công thông thường của Spring Boot. Nó biểu diễn **các mốc quan sát**, không phải lời hứa rằng mọi dịch vụ bên ngoài luôn khỏe hoặc mọi tác vụ do ứng dụng tự tạo đều đã kết thúc.

### 5.1. Trước khi ApplicationContext refresh xong

Khi bean đang được tạo và các callback như @PostConstruct đang chạy, ứng dụng chưa đi tới mốc startup hoàn chỉnh.

Do đó, không nên coi:

- Constructor hoàn tất.
- Một @PostConstruct hoàn tất.
- Web server bắt đầu khởi tạo.
- Một ApplicationContext bean đã tồn tại.

là bằng chứng rằng ứng dụng sẵn sàng nhận request.

Trong giai đoạn chưa tới mốc live/ready, các giá trị fallback mà Spring Boot áp dụng thường diễn đạt **BROKEN** cho liveness và **REFUSING_TRAFFIC** cho readiness. Tuy nhiên, probe bên ngoài cũng có thể chưa kết nối được vì HTTP server chưa mở. Không nên xây logic nghiệp vụ phụ thuộc việc probe phải truy cập được ngay từ giây đầu tiên.

### 5.2. Sau ApplicationStartedEvent

Spring Boot phát ApplicationStartedEvent sau khi context refresh xong nhưng trước khi gọi các startup runner.

Tiếp theo trong luồng startup thông thường, Boot công bố:

~~~java
LivenessState.CORRECT
~~~

Điều đó cho biết ứng dụng đã tới mốc được coi là live. Nó chưa chứng minh các runner đã chạy xong, vì vậy readiness vẫn thường đang ở trạng thái REFUSING_TRAFFIC.

### 5.3. Trong ApplicationRunner và CommandLineRunner

Spring Boot gọi các runner sau mốc started và trước mốc ready. Đây là nơi có thể thực hiện những bước chuẩn bị bắt buộc:

- Kiểm tra cấu hình nghiệp vụ cần thiết.
- Nạp dữ liệu tham chiếu.
- Chuẩn bị cache phải có trước khi nhận request.
- Xác minh tài nguyên cần thiết cho việc phục vụ API.

Khi runner còn chạy đồng bộ, ứng dụng chưa tới ApplicationReadyEvent. Nếu runner ném exception không được xử lý, quá trình startup có thể thất bại và không hoàn tất đường đi ready thông thường.

### 5.4. Sau ApplicationReadyEvent

Spring Boot phát ApplicationReadyEvent sau khi các startup runner hoàn tất. Sau sự kiện này, Boot công bố:

~~~java
ReadinessState.ACCEPTING_TRAFFIC
~~~

Đây là mốc chuyển sang ready trong luồng startup thành công. Điểm tinh tế là **ApplicationReadyEvent và AvailabilityChangeEvent với ACCEPTING_TRAFFIC là hai sự kiện liên tiếp, không phải cùng một sự kiện**.

Nếu một listener xử lý ApplicationReadyEvent đọc ApplicationAvailability ngay tại thời điểm đó, nó chưa nên giả định ReadinessState đã là ACCEPTING_TRAFFIC; Boot còn công bố readiness sau event ready.

## 6. Tại sao không nên publish readiness tùy tiện trong startup?

Giả sử ứng dụng cần làm ấm cache bất đồng bộ và muốn ngăn traffic cho tới khi cache sẵn sàng.

Một cách viết dễ mắc lỗi:

~~~java
@Component
public class CacheStartupListener {
    private final ApplicationEventPublisher publisher;

    public CacheStartupListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        AvailabilityChangeEvent.publish(
                publisher, ReadinessState.REFUSING_TRAFFIC);

        // Bắt đầu tác vụ warm-up nền ở đây.
    }
}
~~~

Vấn đề là listener này chạy **trong lúc ApplicationReadyEvent đang được phát**. Sau khi những listener đồng bộ của sự kiện ready hoàn tất, Spring Boot tiếp tục công bố trạng thái ACCEPTING_TRAFFIC. Vì vậy, REFUSING_TRAFFIC được publish trong listener có thể nhanh chóng bị sự kiện startup mặc định ghi đè.

Tác vụ warm-up nền có thể vẫn chưa xong dù trạng thái cuối cùng đã chuyển sang ACCEPTING_TRAFFIC.

### 6.1. Cách phù hợp nếu tác vụ bắt buộc phải xong trước ready

Chạy đồng bộ trong ApplicationRunner:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class RequiredWarmupRunner implements ApplicationRunner {

    private final CacheWarmupService warmupService;

    public RequiredWarmupRunner(CacheWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmupService.loadRequiredData();
    }
}
~~~

Nếu loadRequiredData() chỉ trả về khi dữ liệu bắt buộc đã sẵn sàng, Boot mới tiếp tục đến ApplicationReadyEvent và readiness ACCEPTING_TRAFFIC. Nếu không thể hoàn tất, exception nên phản ánh lỗi startup thay vì im lặng giả vờ sẵn sàng.

### 6.2. Cách phù hợp nếu warm-up bắt buộc chạy nền

Khi một tác vụ thật sự cần chạy nền mà vẫn phải chặn traffic, có thể tạo một **health contributor** dành cho readiness, trả về OUT_OF_SERVICE tới khi warm-up hoàn thành. Readiness probe thực tế phải bao gồm contributor này.

Mô hình:

~~~text
ApplicationReadyEvent
          │
          ├── Boot công bố ACCEPTING_TRAFFIC
          │
          └── Warm-up chạy nền
                    │
                    ▼
Readiness health group kiểm tra warm-up
          │
          ├── Chưa xong → OUT_OF_SERVICE
          │
          └── Đã xong → UP
~~~

Cách này phân biệt trạng thái availability do Boot quản lý với điều kiện nghiệp vụ riêng mà endpoint readiness cần đánh giá. Phần ví dụ health contributor sẽ được trình bày bên dưới.

## 7. Publish readiness khi ứng dụng đang chạy

Sau khi ứng dụng đã qua startup, một thành phần có thể chủ động phát AvailabilityChangeEvent để tạm ngừng hoặc tiếp tục nhận traffic.

Ví dụ:

~~~java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceService {

    private final ApplicationEventPublisher events;

    public MaintenanceService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void beginMaintenance() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
    }

    public void finishMaintenance() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Khi ứng dụng bắt đầu bảo trì, beginMaintenance() đánh dấu instance chưa nên nhận traffic. Sau khi điều kiện hoạt động bình thường được xác nhận, finishMaintenance() công bố trạng thái accepting traffic.

### 7.1. Không vội khôi phục readiness

Trước khi publish ACCEPTING_TRAFFIC, cần biết điều kiện khiến instance tạm từ chối traffic đã thực sự được giải quyết:

- Tài nguyên bắt buộc đã phục hồi?
- Công việc bảo trì đã hoàn tất?
- Ứng dụng còn đang trong quá trình shutdown không?
- Tính năng cốt lõi đã có thể phục vụ request đúng không?

Nếu nhiều thành phần có thể tự publish readiness, chúng có thể ghi đè trạng thái của nhau. Ví dụ service A báo chưa ready do maintenance nhưng service B báo accepting vì database vừa phục hồi.

Với nhiều điều kiện độc lập, nên có một coordinator tổng hợp trạng thái hoặc readiness health group gồm các contributor cần thiết, thay vì để mọi thành phần tự do phát event ACCEPTING_TRAFFIC.

### 7.2. Liveness có thể được công bố thủ công nhưng phải thận trọng

API cho phép công bố:

~~~java
AvailabilityChangeEvent.publish(
        events, LivenessState.BROKEN);
~~~

Đây là tín hiệu nghiêm trọng: hệ thống điều phối có thể coi process cần được khởi động lại. Không nên publish BROKEN chỉ vì một lời gọi HTTP thất bại, database tạm mất kết nối hoặc một tác vụ nền retry chưa thành công.

Các lỗi phụ thuộc bên ngoài thường phù hợp để phản ánh qua readiness hoặc health contributor. Liveness nên dành cho tình trạng tiến trình không thể tiếp tục hoạt động đúng và restart là cách phục hồi hợp lý.

## 8. Thời điểm đổi readiness trong shutdown

Khi một instance cần dừng, việc ngừng nhận request mới thường nên xảy ra **trước khi các tài nguyên phục vụ request bị đóng**.

Trình tự mục tiêu:

~~~text
Nhận tín hiệu dừng
          │
          ▼
Readiness → REFUSING_TRAFFIC
          │
          ▼
Load balancer / orchestrator dừng gửi request mới
          │
          ▼
Các request đang chạy được xử lý hoặc chờ theo giới hạn
          │
          ▼
Spring context và các tài nguyên được dừng
          │
          ▼
Process kết thúc
~~~

Spring Boot có các cơ chế lifecycle và graceful shutdown để hỗ trợ quá trình này. Trong luồng shutdown được quản lý phù hợp, readiness được đưa về REFUSING_TRAFFIC để báo instance không nên nhận traffic mới.

### 8.1. Readiness không tự bảo đảm graceful shutdown

Publish REFUSING_TRAFFIC là tín hiệu về khả năng nhận traffic. Nó không thay thế:

- Cơ chế dừng nhận kết nối mới của web server.
- Thời gian chờ các request đang xử lý.
- Cơ chế draining của load balancer hoặc ingress.
- Việc đóng connection pool, executor và message consumer.
- Thời hạn shutdown của container/orchestrator.

Vì probe được gọi theo chu kỳ, có thể còn một khoảng trễ trước khi các hệ thống ngoài nhận ra instance không ready. Những request đã được gửi trước đó vẫn có thể đến.

### 8.2. Cấu hình graceful shutdown

Một cấu hình minh họa:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Khi graceful shutdown được hỗ trợ bởi web server đang dùng, Spring Boot phối hợp để cho các request đang chạy có cơ hội hoàn tất trong thời hạn shutdown. Tùy loại web server và cách triển khai, cách xử lý kết nối mới trong giai đoạn này có thể khác nhau.

Đây là cơ chế shutdown, còn AvailabilityChangeEvent là cách thông báo trạng thái. Hai cơ chế cần được cấu hình và quan sát cùng nhau.

### 8.3. Không thể dựa vào callback khi bị kill đột ngột

Khi process crash, bị kill cưỡng bức hoặc mất máy, callback shutdown có thể không chạy. Lúc đó không có bảo đảm AvailabilityChangeEvent hoặc @PreDestroy sẽ được phát/hoàn tất.

Nền tảng triển khai cần dùng probe, timeout và cơ chế phát hiện mất kết nối để loại instance chết khỏi tập endpoint. Không nên thiết kế availability như một protocol bảo đảm mọi process đều phát được “goodbye event”.

## 9. Quan hệ giữa ApplicationReadyEvent và AvailabilityChangeEvent

Hai event có chức năng khác nhau:

| Event | Ý nghĩa |
|---|---|
| **ApplicationStartedEvent** | Context đã refresh, runners chưa được gọi. |
| **AvailabilityChangeEvent(LivenessState.CORRECT)** | Spring Boot công bố ứng dụng đã đạt mốc live thông thường. |
| **ApplicationReadyEvent** | Các runner đã được gọi và luồng startup thành công đã đến mốc ready. |
| **AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)** | Spring Boot công bố trạng thái ready để nhận traffic. |
| **AvailabilityChangeEvent(ReadinessState.REFUSING_TRAFFIC)** | Instance chưa nên nhận traffic hoặc đang rời trạng thái ready. |

### 9.1. Vì sao event ordering quan trọng?

Giả sử một listener được đăng ký:

~~~java
@EventListener(ApplicationReadyEvent.class)
void onReady() {
    // Tại đây ApplicationReadyEvent đang được xử lý.
}
~~~

Nếu muốn biết chính xác lúc **ReadinessState đổi sang ACCEPTING_TRAFFIC**, listener của ApplicationReadyEvent không phải tín hiệu trực tiếp nhất. Hãy lắng nghe AvailabilityChangeEvent cho readiness.

~~~java
@EventListener
void onReadinessChange(
        AvailabilityChangeEvent<ReadinessState> event) {

    if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
        // Readiness đang được công bố là accepting traffic.
    }
}
~~~

Nếu ứng dụng tự publish readiness nhiều lần, listener này có thể được gọi mỗi lần trạng thái được công bố. Đừng mặc định nó chỉ chạy đúng một lần trong vòng đời ứng dụng.

## 10. Quan sát cả liveness và readiness

Có thể viết một listener chung:

~~~java
package com.example.availability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityAuditListener {

    private static final Logger log =
            LoggerFactory.getLogger(AvailabilityAuditListener.class);

    @EventListener
    public void onAvailabilityChange(AvailabilityChangeEvent<?> event) {
        Object state = event.getState();

        if (state instanceof ReadinessState) {
            log.info("Readiness changed: {}", state);
        } else if (state instanceof LivenessState) {
            log.info("Liveness changed: {}", state);
        }
    }
}
~~~

Đây là listener phục vụ quan sát. Tránh tự publish một event khác chỉ vì nhận được event hiện tại nếu không có quy tắc chuyển trạng thái rõ ràng, vì điều đó có thể tạo vòng lặp hoặc thay đổi state không mong muốn.

### 10.1. Event và trạng thái hiện tại không hoàn toàn giống nhau

- **Event** cho biết một thay đổi đã được công bố, có thời điểm và state cụ thể.
- **ApplicationAvailability** trả về state hiện tại được theo dõi trong process.

Một listener được tạo sau khi một event đã phát không tự nhận lại tất cả event lịch sử. Nếu cần biết trạng thái hiện tại, hãy đọc ApplicationAvailability; nếu cần phản ứng khi thay đổi, hãy nghe event.

### 10.2. Chú ý dispatch bất đồng bộ

Spring application event thường được xử lý đồng bộ với cấu hình event multicaster mặc định. Tuy nhiên, ứng dụng có thể thay đổi multicaster hoặc cấu hình listener bất đồng bộ.

Khi event dispatch bất đồng bộ, không nên mặc định publish xong là mọi listener và thành phần quan sát đã cập nhật xong ngay lập tức. Nếu cần một hợp đồng đồng bộ mạnh, phải xác định rõ cơ chế event dispatch và điểm xác nhận trạng thái trong kiến trúc.

## 11. AvailabilityChangeEvent và Spring Boot Actuator

Spring Boot Actuator có thể phản ánh availability qua các health contributor cho liveness/readiness. Khi được cấu hình phù hợp, hai endpoint quen thuộc là:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Khi ứng dụng được nhận diện là chạy trên Kubernetes, Spring Boot có thể tự bật probe health groups theo cơ chế tích hợp của phiên bản đang dùng. Ở môi trường khác, có thể bật tường minh:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

### 11.1. Trạng thái readiness và HTTP health response

Theo ánh xạ health status mặc định thường gặp:

| Availability state | Health status tương ứng | HTTP status thường thấy |
|---|---|---|
| CORRECT (liveness) | UP | 200 |
| BROKEN (liveness) | DOWN | 503 |
| ACCEPTING_TRAFFIC (readiness) | UP | 200 |
| REFUSING_TRAFFIC (readiness) | OUT_OF_SERVICE | 503 |

Đây là ánh xạ điển hình của các availability health indicators. Ứng dụng có thể tùy chỉnh status mapping, health group và contributor; vì vậy cần xác nhận response thực tế của endpoint được triển khai.

### 11.2. Probe đọc endpoint, không trực tiếp đọc Java event

Kubernetes, ingress hoặc load balancer không nhận trực tiếp AvailabilityChangeEvent trong JVM. Chúng đọc kết quả health endpoint hoặc một cơ chế health check khác.

Luồng tương tác:

~~~text
AvailabilityChangeEvent
         │
         ▼
ApplicationAvailability
         │
         ▼
Actuator availability health indicator
         │
         ▼
HTTP readiness/liveness endpoint
         │
         ▼
Kubernetes probe / load balancer health check
         │
         ▼
Điều phối restart hoặc routing traffic
~~~

Nếu không có probe hoặc hệ thống điều phối không sử dụng kết quả probe, event vẫn có thể cập nhật state trong process nhưng không tự khiến traffic bên ngoài được điều hướng lại.

### 11.3. Management port riêng có thể che vấn đề cổng ứng dụng

Nếu Actuator chạy trên một management port riêng, probe có thể trả 200 dù cổng chính phục vụ API đang gặp vấn đề. Với một số cấu hình, nên cân nhắc expose các health probe path bổ sung trên cổng ứng dụng chính:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Khi được hỗ trợ, cấu hình này có thể cung cấp những đường dẫn như **/livez** và **/readyz** trên server port chính. Cần xác nhận endpoint, security và routing theo phiên bản Boot và web stack đang dùng.

## 12. Chọn điều gì đưa vào readiness probe

Readiness nên phản ánh việc instance **có thể phục vụ request đúng**. Không phải mọi dependency bên ngoài đều nên được đưa vào readiness.

Ví dụ:

- Nếu mọi request bắt buộc gọi database và không có fallback, database không sẵn sàng có thể làm instance chưa ready.
- Nếu hệ thống gửi email bị lỗi nhưng chức năng chính vẫn có thể phục vụ, không nên tự động loại toàn bộ instance khỏi traffic chỉ vì email thất bại.
- Nếu cache là tối ưu hóa có fallback, warm-up cache chưa xong có thể không cần chặn readiness.
- Nếu một bước nạp dữ liệu nền bắt buộc chưa hoàn tất, readiness nên phản ánh trạng thái đó.

Một readiness gate quá nghiêm ngặt có thể khiến tất cả replica cùng bị loại khỏi routing khi một dependency dùng chung mất kết nối. Điều này có thể làm sự cố lan rộng hơn. Hãy chọn contributor dựa trên hợp đồng phục vụ request và mô hình dự phòng của ứng dụng.

### 12.1. Ví dụ health contributor cho warm-up

Giả sử ứng dụng phải hoàn tất một quá trình chuẩn bị trước khi endpoint có thể trả kết quả đúng. Ta tạo trạng thái:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class WarmupState {
    private final AtomicBoolean ready = new AtomicBoolean(false);

    public void markReady() {
        ready.set(true);
    }

    public boolean isReady() {
        return ready.get();
    }
}
~~~

HealthIndicator đọc trạng thái:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("warmup")
public class WarmupHealthIndicator implements HealthIndicator {

    private final WarmupState warmup;

    public WarmupHealthIndicator(WarmupState warmup) {
        this.warmup = warmup;
    }

    @Override
    public Health health() {
        return warmup.isReady()
                ? Health.up().build()
                : Health.outOfService().build();
    }
}
~~~

Sau đó thêm contributor này vào readiness health group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,warmup
~~~

Khi warmup chưa ready, endpoint readiness có thể trả OUT_OF_SERVICE dù ApplicationAvailability đã nhận ACCEPTING_TRAFFIC từ luồng startup mặc định. Sau khi WarmupState chuyển sang true, readiness group có thể trả UP nếu các contributor khác cũng sẵn sàng.

Điểm cần hiểu: **ReadinessState và health group không phải cùng một biến**. Health group có thể tổng hợp thêm những điều kiện mà ứng dụng cần kiểm tra.

## 13. Phân biệt readiness event với trạng thái nghiệp vụ riêng

AvailabilityChangeEvent phù hợp để công bố một trạng thái availability tổng quát. Nó không lưu chi tiết:

- Vì sao instance chưa ready?
- Tác vụ nào đang chặn?
- Bao nhiêu phần trăm warm-up đã hoàn thành?
- Có bao nhiêu lỗi retry?
- Dependency nào đang trong trạng thái degraded?

Nếu cần những thông tin đó, ứng dụng nên có cơ chế quan sát riêng như metrics, logs, health details hoặc một trạng thái nghiệp vụ cụ thể.

Ví dụ một hệ thống có ba điều kiện:

~~~text
Readiness tổng hợp
        │
        ├── Dataset initialized?
        ├── Search index usable?
        └── Local worker initialized?
~~~

Thay vì để ba thành phần publish ACCEPTING_TRAFFIC độc lập, có thể để health contributors hoặc một coordinator tính điều kiện tổng hợp:

~~~text
Ready = datasetReady AND searchReady AND workerReady
~~~

Khi mọi điều kiện bắt buộc đều thỏa, instance mới nên báo ready. Cách này tránh cuộc đua ghi đè trạng thái giữa các thành phần.

## 14. Thử nghiệm chuyển trạng thái tại runtime

Trong một ứng dụng Spring Boot có Actuator và probes được bật, có thể tạo service quản lý trạng thái như ví dụ MaintenanceService rồi gọi nó thông qua một quy trình vận hành nội bộ.

Quy trình quan sát:

1. Khởi động ứng dụng và đợi các startup runner hoàn tất.
2. Đọc readiness endpoint; khi điều kiện bình thường thỏa, kết quả thường là UP.
3. Kích hoạt MaintenanceService.beginMaintenance().
4. Đọc readiness endpoint sau khi event đã được xử lý; kết quả availability readiness thường chuyển sang OUT_OF_SERVICE.
5. Hoàn thành công việc bảo trì và xác nhận ứng dụng có thể phục vụ lại.
6. Gọi finishMaintenance().
7. Đọc readiness endpoint; trạng thái thường trở lại UP nếu không còn contributor khác báo lỗi.

Nếu response không đổi, cần kiểm tra:

- Event có được publish qua ApplicationEventPublisher của đúng context không?
- ApplicationAvailability có được cập nhật không?
- Probe endpoint và health group đã bật đúng chưa?
- Có health contributor nào khác vẫn báo DOWN hoặc OUT_OF_SERVICE không?
- Có thiết lập custom event multicaster làm listener xử lý bất đồng bộ không?
- Probe hoặc load balancer có cache trạng thái hay độ trễ polling không?

Việc đổi Java state là một bước; kết quả routing bên ngoài còn phụ thuộc cấu hình hạ tầng.

## 15. Kiểm thử event và trạng thái trong Spring context

Có thể tạo một context nhỏ để kiểm tra cách AvailabilityChangeEvent được publish và quan sát. Ví dụ dưới đây tập trung vào state event, không cần web server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ApplicationAvailabilityBean;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class AvailabilityChangeEventTests {

    @Test
    void updatesReadinessWhenEventIsPublished() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(ApplicationAvailabilityBean.class);
            context.refresh();

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);

            assertThat(availability.getReadinessState())
                    .isEqualTo(ReadinessState.REFUSING_TRAFFIC);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);

            assertThat(availability.getReadinessState())
                    .isEqualTo(ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

Ví dụ này minh họa việc event cập nhật trạng thái trong một context có ApplicationAvailabilityBean và event dispatch đồng bộ mặc định.

Đối với test tích hợp của ứng dụng thật, có thể dùng @SpringBootTest và đọc ApplicationAvailability sau khi context đã khởi động. Khi test thay đổi readiness của context dùng chung, cần cô lập hoặc khôi phục state để không gây ảnh hưởng tới test khác.

### 15.1. Kiểm thử thứ tự startup theo hành vi

Với một startup runner bắt buộc, test nên xác nhận:

- Nếu công việc chuẩn bị thành công, ứng dụng đi tới mốc ready.
- Nếu runner ném lỗi, startup không được coi là thành công.
- Nếu công việc chạy async, readiness endpoint vẫn phản ánh đúng điều kiện nghiệp vụ cần thiết.

Đừng chỉ test rằng AvailabilityChangeEvent đã được phát; hãy test tác động thực tế mà người sử dụng cần, chẳng hạn readiness probe báo chưa sẵn sàng khi dữ liệu bắt buộc chưa có.

## 16. Các lỗi thường gặp về thời điểm chuyển trạng thái

### 16.1. Cho rằng @PostConstruct tương đương application ready

**Dấu hiệu:** một bean ghi log “ready” trong @PostConstruct, nhưng runner chưa chạy hoặc dữ liệu chưa sẵn sàng.

**Giải thích:** callback bean xảy ra khi bean đang được khởi tạo, trước khi toàn bộ luồng startup hoàn tất.

**Cách xử lý:** dùng runner đồng bộ hoặc mốc ready phù hợp; để liveness/readiness do Boot phản ánh theo lifecycle.

### 16.2. Publish REFUSING_TRAFFIC trong ApplicationReadyEvent và bị ghi đè

**Dấu hiệu:** listener đã publish refusing nhưng readiness nhanh chóng trở lại accepting khi warm-up vẫn đang chạy.

**Giải thích:** Spring Boot công bố ACCEPTING_TRAFFIC sau ApplicationReadyEvent trong luồng startup thành công.

**Cách xử lý:** chạy tác vụ bắt buộc đồng bộ trước ready hoặc đưa trạng thái warm-up vào readiness health group. Tránh trông cậy vào việc publish refusing trong ready listener để giữ cổng đóng.

### 16.3. Đánh dấu BROKEN khi dependency ngoài tạm lỗi

**Dấu hiệu:** Kubernetes restart hàng loạt replica khi database dùng chung tạm mất kết nối.

**Giải thích:** liveness thất bại thường được diễn giải là cần restart process. Một lỗi ở hệ thống ngoài có thể không được sửa bằng restart.

**Cách xử lý:** thiết kế readiness, retry và fallback theo nghiệp vụ; chỉ dùng BROKEN cho tình trạng process không thể hoạt động đúng.

### 16.4. Publish readiness nhưng traffic vẫn đến

**Dấu hiệu:** sau khi state là REFUSING_TRAFFIC, vẫn thấy request mới.

**Giải thích:** event không tự đóng socket, có độ trễ probe, load balancer và kết nối hiện tại.

**Cách xử lý:** kiểm tra readiness probe, load balancer routing, thời gian polling và quy trình graceful shutdown.

### 16.5. ApplicationAvailability đã accepting nhưng readiness health vẫn 503

**Dấu hiệu:** getReadinessState() trả ACCEPTING_TRAFFIC nhưng endpoint readiness trả OUT_OF_SERVICE.

**Giải thích:** health group có thể tổng hợp thêm contributor khác đang báo lỗi, như warmup hoặc dependency bắt buộc.

**Cách xử lý:** xem từng health contributor và điều kiện nghiệp vụ cụ thể.

### 16.6. Readiness thay đổi qua lại liên tục

**Dấu hiệu:** endpoint readiness nhảy giữa UP và OUT_OF_SERVICE nhiều lần trong thời gian ngắn.

**Giải thích:** có thể do dependency không ổn định, hai thành phần cùng publish state hoặc thiếu hysteresis trong health check.

**Cách xử lý:** xác định nguồn chuyển trạng thái, gom điều kiện vào một coordinator, áp dụng ngưỡng và chính sách phục hồi phù hợp thay vì để event cạnh tranh.

### 16.7. Dùng readiness như cơ chế dừng process

**Dấu hiệu:** ứng dụng bị yêu cầu tắt nhưng chỉ publish REFUSING_TRAFFIC và process vẫn tiếp tục chạy.

**Giải thích:** readiness chỉ nói “không nhận traffic”; nó không gọi SpringApplication.exit hoặc đóng context.

**Cách xử lý:** nếu thật sự cần dừng, dùng cơ chế shutdown lifecycle phù hợp; readiness là một phần trong quá trình draining.

### 16.8. Kỳ vọng event được lưu lại sau restart

**Dấu hiệu:** sau khi restart instance, trạng thái bảo trì do process cũ publish không còn.

**Giải thích:** ApplicationAvailability là trạng thái in-memory của process; event không phải dữ liệu bền vững.

**Cách xử lý:** với chế độ bảo trì phải tồn tại qua restart, lưu ý định bảo trì trong hệ thống cấu hình/điều phối bền vững và áp dụng lại theo lifecycle phù hợp.

## 17. Những hiểu nhầm thường gặp

**“Ứng dụng đã mở cổng HTTP nghĩa là ready.”**  
Không. Spring Boot có thể đã mở cổng trước khi các startup runner hoàn tất. Readiness được công bố ở mốc riêng.

**“ApplicationStartedEvent và ApplicationReadyEvent giống nhau.”**  
Không. Started xuất hiện trước runner; Ready xuất hiện sau runner.

**“ApplicationReadyEvent có nghĩa readiness đã được publish là ACCEPTING_TRAFFIC.”**  
Không nên giả định tại thời điểm đang xử lý listener ready. Spring Boot công bố trạng thái accepting traffic sau ApplicationReadyEvent trong luồng thông thường.

**“AvailabilityChangeEvent chỉ do Spring Boot tự phát.”**  
Không. Ứng dụng có thể chủ động publish sự kiện availability qua ApplicationEventPublisher.

**“Publish REFUSING_TRAFFIC sẽ lập tức chặn mọi request.”**  
Không. Nó cập nhật trạng thái availability; việc điều hướng traffic phụ thuộc probe, load balancer và độ trễ của hạ tầng.

**“CORRECT bảo đảm database và mọi dịch vụ ngoài đều đang hoạt động.”**  
Không. CORRECT là liveness, không phải kiểm chứng mọi dependency.

**“Readiness phải xuống khi bất cứ dependency nào gặp lỗi.”**  
Không. Chỉ nên phản ánh dependency thực sự ảnh hưởng đến khả năng phục vụ request theo hợp đồng.

**“BROKEN là trạng thái phù hợp cho mọi lỗi tạm thời.”**  
Không. BROKEN có thể dẫn tới restart; lỗi bên ngoài tạm thời thường không cần restart process.

**“ApplicationAvailability là trạng thái của toàn cluster.”**  
Không. Mỗi instance theo dõi trạng thái riêng trong process.

**“AvailabilityChangeEvent được lưu và phát lại cho listener mới.”**  
Không. Đây là application event. Muốn đọc trạng thái hiện tại, dùng ApplicationAvailability; muốn lịch sử, cần ghi log/metrics hoặc lưu riêng.

**“Một @Async bắt đầu từ ApplicationReadyEvent sẽ làm Boot đợi cho đến khi xong.”**  
Không. Tác vụ nền có thể tiếp tục sau khi Boot công bố readiness; cần readiness gate hoặc chạy đồng bộ trước ready nếu công việc là điều kiện bắt buộc.

**“Graceful shutdown được bảo đảm chỉ bằng một availability event.”**  
Không. Cần phối hợp shutdown của web server, request draining, timeout và nền tảng triển khai.

## 18. Nguyên tắc lựa chọn thời điểm đổi trạng thái

1. **Để Spring Boot quản lý các mốc startup chuẩn**: liveness sau started và readiness sau ready là các tín hiệu vòng đời cơ bản.
2. **Dùng ApplicationRunner đồng bộ cho chuẩn bị bắt buộc**: startup không tiến tới mốc ready khi runner chưa hoàn tất.
3. **Dùng readiness health contributor cho điều kiện bất đồng bộ**: khi có nhiều điều kiện độc lập hoặc công việc nền, health group nên phản ánh đúng khả năng phục vụ.
4. **Publish REFUSING_TRAFFIC khi cần rút instance khỏi routing**: ví dụ bảo trì hoặc điều phối drain sau khi ứng dụng đã khởi động.
5. **Không publish ACCEPTING_TRAFFIC chỉ vì một điều kiện đơn lẻ phục hồi**: xác nhận các điều kiện bắt buộc khác cũng đã được đáp ứng.
6. **Chỉ dùng BROKEN cho lỗi process thật sự nghiêm trọng**: restart phải là chiến lược phục hồi có ý nghĩa.
7. **Đảm bảo probe được cấu hình và sử dụng thực tế**: một event trong JVM không tự điều khiển load balancer.
8. **Phối hợp readiness với shutdown**: thông báo refusing, cho traffic draining, rồi đóng tài nguyên theo thời hạn rõ ràng.
9. **Quan sát và giải thích mỗi lần chuyển trạng thái**: ghi log nguồn thay đổi, thời điểm và lý do để dễ chẩn đoán.
10. **Xem availability là trạng thái theo từng replica**: nếu trạng thái cần tồn tại qua restart hoặc đồng bộ cluster, cần cơ chế quản lý bên ngoài.

## Ghi nhớ cốt lõi

**AvailabilityChangeEvent** là cơ chế Spring Boot dùng để công bố thay đổi trạng thái **LivenessState** và **ReadinessState**; **ApplicationAvailability** cho phép đọc state hiện tại. Trong luồng startup thành công, Boot công bố liveness CORRECT sau ApplicationStartedEvent, chạy ApplicationRunner/CommandLineRunner, phát ApplicationReadyEvent rồi công bố readiness ACCEPTING_TRAFFIC. Khi chuẩn bị dừng hoặc khi một instance tạm chưa thể nhận traffic, readiness có thể chuyển về REFUSING_TRAFFIC.

Thời điểm publish quyết định ý nghĩa thực tế. Đặt REFUSING_TRAFFIC trong ApplicationReadyEvent có thể bị startup event kế tiếp ghi đè; công việc bắt buộc nên hoàn tất đồng bộ trước ready, còn công việc nền cần readiness health gate thích hợp nếu phải chặn request. Availability event là tín hiệu trạng thái trong JVM; để ảnh hưởng đến routing và shutdown, nó phải phối hợp với Actuator probes, nền tảng điều phối và cơ chế graceful shutdown.
