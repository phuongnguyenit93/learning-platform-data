# ApplicationAvailability và trạng thái của ứng dụng

Một ứng dụng Spring Boot có thể đã khởi tạo được ApplicationContext nhưng vẫn chưa sẵn sàng nhận lưu lượng truy cập. Ngược lại, ứng dụng có thể còn chạy bình thường nhưng tạm thời cần ngừng nhận yêu cầu mới để bảo trì, giảm tải hoặc chuẩn bị dừng. Vì vậy, **đang chạy** và **sẵn sàng phục vụ** là hai trạng thái khác nhau.

Spring Boot mô hình hóa các trạng thái đó thông qua `ApplicationAvailability`, `LivenessState`, `ReadinessState` và `AvailabilityChangeEvent`. Các API này cho phép ứng dụng công bố trạng thái hiện tại, đồng thời tạo điểm tích hợp với health probes của Spring Boot Actuator và hệ thống điều phối như Kubernetes.

## 1. Vì sao cần theo dõi trạng thái ứng dụng?

Hãy xét một service xử lý đơn hàng. Khi tiến trình JVM vừa khởi chạy, Spring Boot còn phải tạo bean, nạp cấu hình và chạy các tác vụ startup. Trong khoảng thời gian đó, service chưa nên nhận request từ load balancer.

Sau khi khởi động thành công, service có thể nhận request. Tuy nhiên, khi người vận hành cần đưa instance ra khỏi vòng phục vụ để triển khai phiên bản mới, service nên từ chối lưu lượng mới trước khi đóng các thành phần còn lại.

Cũng có trường hợp tiến trình bị kẹt trong trạng thái không thể phục hồi: nó vẫn tồn tại nhưng không thể làm công việc hữu ích. Khi đó, hệ thống điều phối có thể cần khởi động lại instance.

Spring Boot phân biệt hai câu hỏi:

- **Liveness:** ứng dụng còn trong trạng thái có khả năng tiếp tục hoạt động, hay đã hỏng đến mức cần được khởi động lại?
- **Readiness:** ứng dụng có đang chấp nhận lưu lượng hoặc công việc mới hay không?

Hai câu hỏi độc lập này giúp hệ thống vận hành đưa ra hành động phù hợp, tránh khởi động lại một ứng dụng chỉ vì nó đang tạm thời không sẵn sàng.

## 2. ApplicationAvailability là gì?

`ApplicationAvailability` thuộc package `org.springframework.boot.availability`. Đây là interface dùng để **đọc trạng thái availability hiện tại** mà Spring Boot đã ghi nhận.

Một service có thể nhận interface qua constructor:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AvailabilityInspector {

    private final ApplicationAvailability availability;

    public AvailabilityInspector(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean isLive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }

    public boolean isReady() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

Spring Boot cung cấp bean `ApplicationAvailability` để các thành phần trong ApplicationContext tra cứu trạng thái mà không cần tự duy trì các biến cờ rời rạc.

Interface có các phương thức thường dùng:

~~~java
LivenessState liveness = availability.getLivenessState();
ReadinessState readiness = availability.getReadinessState();
~~~

Ngoài ra, có thể đọc một loại trạng thái thông qua `getState(...)` và chỉ định giá trị dự phòng nếu cần:

~~~java
ReadinessState readiness = availability.getState(
        ReadinessState.class,
        ReadinessState.REFUSING_TRAFFIC
);
~~~

`ApplicationAvailability` là API để quan sát trạng thái. Khi ứng dụng cần **thay đổi** trạng thái, hãy phát một `AvailabilityChangeEvent` thay vì cố chỉnh sửa đối tượng availability trực tiếp.

## 3. LivenessState: ứng dụng còn sống hay đã hỏng?

`LivenessState` có hai giá trị:

| Giá trị | Ý nghĩa | Phản ứng vận hành thường gặp |
|---|---|---|
| `CORRECT` | Ứng dụng ở trạng thái nội bộ có thể tiếp tục hoạt động | Giữ tiến trình chạy |
| `BROKEN` | Ứng dụng bị lỗi nội bộ nghiêm trọng, không còn khả năng tự phục hồi như dự kiến | Có thể khởi động lại instance |

Liveness tập trung vào khả năng hoạt động của **chính tiến trình**. Đây không phải phép kiểm tra xem mọi dịch vụ bên ngoài đều sẵn sàng hay không.

Ví dụ, nếu database tạm ngừng kết nối nhưng ứng dụng có cơ chế kết nối lại, sự cố đó thường không có nghĩa JVM cần được khởi động lại. Đánh dấu `BROKEN` chỉ vì database lỗi có thể khiến toàn bộ replica cùng khởi động lại liên tục mà không giải quyết được vấn đề database.

Trái lại, nếu một thành phần cốt lõi rơi vào trạng thái lỗi không thể hồi phục, ứng dụng có thể công bố `LivenessState.BROKEN`. Hệ thống giám sát hoặc orchestrator sử dụng liveness probe khi đó có thể quyết định restart instance.

Lưu ý: việc công bố `BROKEN` **không tự động gọi** `System.exit()`, cũng không trực tiếp yêu cầu JVM khởi động lại. Hành động restart phụ thuộc vào hệ thống quản lý tiến trình hoặc cấu hình liveness probe ở bên ngoài.

## 4. ReadinessState: ứng dụng có chấp nhận công việc mới không?

`ReadinessState` cũng có hai giá trị:

| Giá trị | Ý nghĩa | Phản ứng vận hành thường gặp |
|---|---|---|
| `ACCEPTING_TRAFFIC` | Instance sẵn sàng tiếp nhận lưu lượng mới | Đưa instance vào tập backend có thể nhận request |
| `REFUSING_TRAFFIC` | Instance chưa hoặc tạm thời không sẵn sàng nhận lưu lượng mới | Tạm rút instance khỏi tuyến phục vụ |

Readiness có thể thay đổi nhiều lần trong suốt vòng đời ứng dụng. Các thời điểm thường gặp:

- Trong quá trình khởi động, các runner hoặc bước chuẩn bị vẫn đang thực hiện.
- Sau khi startup hoàn tất, instance bắt đầu nhận lưu lượng.
- Trước khi dừng, instance cần rút khỏi load balancer.
- Khi một thành phần thiết yếu tạm thời quá tải và ứng dụng có cơ chế chủ động giảm lưu lượng.

Readiness không nhất thiết đồng nghĩa service đã mất khả năng xử lý mọi request. Một ứng dụng có thể chuyển sang `REFUSING_TRAFFIC` để tránh nhận **request mới**, trong khi các request đang xử lý vẫn tiếp tục cho đến khi hoàn thành.

Việc đổi readiness state không tự đóng cổng HTTP hay từ chối kết nối tại tầng mạng. Nó công bố trạng thái để các thành phần như Actuator health indicator và hệ thống điều phối có thể sử dụng.

## 5. Trạng thái thay đổi ra sao khi Spring Boot khởi động?

Spring Boot tự công bố các mốc availability trong vòng đời `SpringApplication.run()`. Có thể hình dung luồng thông thường như sau:

~~~text
SpringApplication.run()
        |
        v
Khởi động và chuẩn bị ApplicationContext
        |
        |  Liveness:  BROKEN (giá trị mặc định ban đầu)
        |  Readiness: REFUSING_TRAFFIC
        v
ApplicationContext được refresh thành công
        |
        v
ApplicationStartedEvent
        |
        v
LivenessState.CORRECT
        |
        v
Chạy ApplicationRunner / CommandLineRunner
        |
        |  Readiness vẫn REFUSING_TRAFFIC
        v
ApplicationReadyEvent
        |
        v
ReadinessState.ACCEPTING_TRAFFIC
        |
        v
Ứng dụng tiếp tục phục vụ
~~~

Giá trị ban đầu được thiết kế theo hướng thận trọng: ứng dụng chưa chứng minh đã khởi động ổn định thì chưa nên được coi là ready.

Sau khi context refresh, Spring Boot phát `ApplicationStartedEvent` rồi công bố liveness `CORRECT`. Tiếp đó, `ApplicationRunner` và `CommandLineRunner` được gọi. Sau khi các runner hoàn tất, Boot phát `ApplicationReadyEvent` và công bố readiness `ACCEPTING_TRAFFIC`.

Do vậy, **liveness có thể đã CORRECT trong khi readiness vẫn REFUSING_TRAFFIC**. Đây là trạng thái hợp lệ: container đã tạo xong những thành phần cần thiết, nhưng các bước startup cấp ứng dụng chưa hoàn tất.

Nếu quá trình startup thất bại, ứng dụng có thể phát `ApplicationFailedEvent` và không đi tới trạng thái ready. Với hệ thống điều phối, nên kết hợp readiness và startup/liveness probes theo chính sách triển khai để tránh đưa một instance chưa khởi động xong vào vòng phục vụ.

## 6. AvailabilityChangeEvent: thay đổi trạng thái bằng sự kiện

`AvailabilityChangeEvent<S>` thuộc package `org.springframework.boot.availability`, với `S` là loại trạng thái availability cụ thể. Khi event được công bố trong ApplicationContext, cơ chế availability của Spring Boot ghi nhận giá trị mới; các listener cũng có thể nhận event để cập nhật quan sát.

Ví dụ, một component cần tạm rút instance khỏi vòng nhận traffic:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class TrafficAdmissionController {

    private final ApplicationEventPublisher publisher;

    public TrafficAdmissionController(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void pauseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void resumeNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

`AvailabilityChangeEvent.publish(...)` phát event thông qua `ApplicationEventPublisher`. Sau khi event được xử lý, `ApplicationAvailability` phản ánh trạng thái được công bố.

Một quy trình bảo trì có thể gọi `pauseNewTraffic()` trước khi bắt đầu, đợi hệ thống điều phối ngừng đưa request mới tới instance, rồi xử lý các tác vụ còn lại. Khi dịch vụ đã đáp ứng lại các điều kiện nhận traffic, nó có thể gọi `resumeNewTraffic()`.

Điểm cần nhớ: lời gọi `publish(..., REFUSING_TRAFFIC)` **không đảm bảo traffic ngừng ngay lập tức**. Load balancer, Kubernetes readiness probe hoặc một thành phần điều phối khác cần quan sát trạng thái, cập nhật danh sách đích và có thể mất một khoảng thời gian mới ngừng định tuyến.

### Phát trạng thái BROKEN khi có lỗi không thể phục hồi

Có thể phát một thay đổi liveness:

~~~java
AvailabilityChangeEvent.publish(
        publisher,
        LivenessState.BROKEN
);
~~~

Chỉ nên làm điều này khi lỗi thực sự khiến instance không còn khả năng hoạt động an toàn hoặc tự phục hồi. Việc restart tiến trình phụ thuộc vào cơ chế vận hành bên ngoài, và liveness probe cần được cấu hình phù hợp.

Không nên tự động chuyển liveness thành `BROKEN` mỗi khi một request thất bại hoặc một upstream trả về lỗi tạm thời.

### Phân biệt trạng thái ứng dụng với trạng thái một request

Availability mang ý nghĩa **toàn instance**. Một request thiếu dữ liệu, xác thực thất bại hoặc gặp lỗi nghiệp vụ thường chỉ cần được xử lý bằng HTTP status và exception handling tương ứng.

Không nên chuyển `REFUSING_TRAFFIC` hoặc `BROKEN` cho toàn ứng dụng chỉ vì một request có lỗi thông thường. Hãy chọn mốc chuyển trạng thái dựa trên năng lực phục vụ chung của instance.

## 7. Quan sát AvailabilityChangeEvent

Ngoài việc đọc trạng thái hiện tại từ `ApplicationAvailability`, ứng dụng có thể lắng nghe event chuyển trạng thái bằng `@EventListener`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityLogger {

    private static final Logger log =
            LoggerFactory.getLogger(AvailabilityLogger.class);

    @EventListener
    public void onAvailabilityChanged(AvailabilityChangeEvent<?> event) {
        if (event.getState() instanceof LivenessState liveness) {
            log.info("Liveness changed to {}", liveness);
        } else if (event.getState()
                instanceof ReadinessState readiness) {
            log.info("Readiness changed to {}", readiness);
        }
    }
}
~~~

Logger trên nhận các event và ghi lại giá trị mới. Khi đọc state bằng `ApplicationAvailability`, code nhận được trạng thái gần nhất đã được ghi nhận, còn listener cho phép phản ứng tại thời điểm xảy ra thay đổi.

Với hệ thống có nhiều context hoặc event publisher, cần lưu ý phạm vi context và cơ chế truyền event. Không nên xem event là một tín hiệu thay đổi trạng thái toàn cluster. Mỗi instance có availability riêng.

Nếu cần cho hệ thống bên ngoài biết trạng thái, thông thường nên thông qua health probes hoặc hệ thống giám sát thay vì tự phát thông điệp thủ công từ mỗi listener.

## 8. Spring Boot Actuator cung cấp liveness và readiness probes

Khi thêm Spring Boot Actuator, ứng dụng web có thể công bố health groups riêng cho liveness và readiness. Hai nhóm này dùng các health indicator dựa trên `ApplicationAvailability`:

- `livenessState`: phản ánh `LivenessState`.
- `readinessState`: phản ánh `ReadinessState`.

Các endpoint thường dùng là:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Trong Kubernetes, Spring Boot có khả năng tự bật các health probe groups theo môi trường được phát hiện. Khi chạy ngoài Kubernetes nhưng vẫn muốn dùng chúng, có thể bật rõ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Với Gradle, ứng dụng cần có Actuator dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Đây là endpoint quan sát. Spring Boot ánh xạ availability state sang trạng thái health group, rồi sang HTTP status theo cấu hình health endpoint.

| Availability state | Health thường nhận | HTTP thông thường |
|---|---|---|
| `LivenessState.CORRECT` | `UP` | 200 |
| `LivenessState.BROKEN` | `DOWN` | 503 |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | 200 |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | 503 |

Các mã trên là hành vi ánh xạ health status mặc định thường gặp. Ứng dụng có thể tùy chỉnh HTTP status mapping hoặc health groups, vì vậy cần kiểm tra endpoint thực tế nếu môi trường đã có cấu hình Actuator riêng.

### Ví dụ Kubernetes probes

Một cấu hình Deployment có thể gọi các đường dẫn health của ứng dụng:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Ví dụ giả định các endpoint Actuator được phục vụ trên cổng ứng dụng `8080`. Nếu Actuator dùng cổng riêng, đường dẫn và cổng trong probes phải được cấu hình tương ứng.

Kubernetes sử dụng liveness probe để quyết định khi nào container cần được khởi động lại nếu probe liên tục thất bại. Readiness probe quyết định khi nào Pod sẵn sàng nhận traffic từ Service; khi probe thất bại, Pod có thể bị loại khỏi tập endpoint phục vụ mà không phải restart.

Trong ứng dụng khởi động chậm, có thể dùng thêm `startupProbe` để Kubernetes chưa áp dụng ngưỡng liveness quá sớm trong giai đoạn startup. Không dùng độ trễ tùy ý để thay thế việc hiểu quy trình khởi động thực tế.

### Khi management server chạy trên cổng khác

Nếu đặt `management.server.port` khác cổng chính, probes có thể chỉ kiểm tra management server đang hoạt động mà không phản ánh đúng đường đi request của ứng dụng chính.

Spring Boot có thể công bố thêm health probe paths ngay trên cổng ứng dụng bằng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Với cấu hình này, các đường dẫn bổ sung thông thường là:

~~~text
GET /livez
GET /readyz
~~~

Các endpoint bổ sung trên cổng chính giúp kiểm tra khả năng phục vụ của chính web server ứng dụng, tránh chỉ kiểm tra một management server độc lập.

## 9. Tích hợp readiness vào quy trình dừng ứng dụng

Readiness đặc biệt hữu ích ở giai đoạn dừng. Trong một lần triển khai rolling update, instance cần ngừng nhận request mới nhưng vẫn có thể cần thời gian hoàn tất công việc đang xử lý.

Một trình tự vận hành thường gặp:

~~~text
Yêu cầu dừng / thay instance
        |
        v
Readiness = REFUSING_TRAFFIC
        |
        v
Hệ thống điều phối ngừng gửi request mới
        |
        v
Hoàn tất request và tác vụ đang chạy
        |
        v
Dừng web server, đóng context và tài nguyên
        |
        v
Tiến trình kết thúc
~~~

Spring Boot hỗ trợ graceful shutdown cho web server có hỗ trợ và tích hợp với vòng đời ApplicationContext. Có thể cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

`server.shutdown=graceful` yêu cầu web server thực hiện quá trình dừng có kiểm soát theo khả năng của server. `spring.lifecycle.timeout-per-shutdown-phase` đặt giới hạn thời gian cho mỗi pha shutdown của Spring lifecycle.

Availability state và graceful shutdown là hai phần bổ trợ:

- Readiness công bố liệu instance có nên nhận traffic mới.
- Orchestrator hoặc load balancer quyết định có tiếp tục định tuyến traffic hay không.
- Graceful shutdown xử lý việc dừng server và hoàn tất các công việc đang diễn ra trong thời gian cho phép.

Không nên hiểu việc phát `REFUSING_TRAFFIC` là đã tự hoàn tất graceful shutdown. Nó không thay thế thời gian drain, timeout của load balancer, chính sách dừng Pod hay việc đóng tài nguyên của ứng dụng.

Trong các hệ thống phân tán, phải tính đến độ trễ cập nhật readiness và việc một request có thể đã được định tuyến trước khi instance bị rút khỏi pool. Đó là lý do quy trình shutdown cần phối hợp cả tín hiệu readiness lẫn khả năng xử lý các request còn lại.

## 10. Không nên đưa mọi dependency vào liveness probe

Một lỗi vận hành phổ biến là cho liveness probe kiểm tra database, message broker hoặc một API bên ngoài. Khi dependency chung gặp sự cố, tất cả instance có thể đồng loạt thất bại liveness probe và bị restart liên tục.

Hành vi đó có thể tạo ra vòng lặp restart và gia tăng tải lên dependency đang lỗi.

**Liveness nên phản ánh khả năng phục hồi của chính ứng dụng.** Nếu database tạm mất kết nối mà service có thể hồi phục khi database trở lại, thường không nên đánh dấu liveness là BROKEN.

Readiness có thể cần xét một số phụ thuộc thiết yếu nếu ứng dụng thực sự không thể phục vụ công việc khi chúng không sẵn sàng. Tuy nhiên, phải cân nhắc tác động khi cả hệ thống cùng bị rút khỏi pool:

- Nếu một dependency mất kết nối, liệu mọi replica đều không thể phục vụ hay chỉ một nhóm tác vụ bị ảnh hưởng?
- Kiểm tra readiness có quá chậm hoặc quá nhạy với lỗi ngắn hạn không?
- Khi dependency phục hồi, ứng dụng có tự chuyển lại readiness không?
- Việc loại toàn bộ replica khỏi danh sách đích có khiến hệ thống không còn đường xử lý yêu cầu hoặc không còn cơ chế tự phục hồi không?

Spring Boot mặc định không tự thêm mọi health indicator bên ngoài vào readiness group. Khi cần, ứng dụng có thể tùy chỉnh nhóm health, nhưng nên làm với hiểu biết về ranh giới lỗi và hành vi của hệ thống điều phối.

## 11. Kiểm tra trạng thái khi ứng dụng đang chạy

Có thể quan sát availability theo ba cách bổ trợ nhau.

**Đọc trực tiếp qua ApplicationAvailability:** một component trong context có thể gọi `getLivenessState()` và `getReadinessState()` để biết trạng thái gần nhất được ghi nhận.

**Lắng nghe AvailabilityChangeEvent:** một listener nhận event khi trạng thái mới được công bố, phù hợp cho ghi log hoặc cập nhật metrics.

**Kiểm tra health probes:** hệ thống bên ngoài gọi `/actuator/health/liveness` và `/actuator/health/readiness` để quyết định hành động điều phối.

Một số tình huống đáng kiểm tra khi xây dựng ứng dụng:

| Tình huống | Liveness mong đợi | Readiness mong đợi |
|---|---|---|
| Ứng dụng đang khởi động | Chưa `CORRECT` cho tới mốc thích hợp | `REFUSING_TRAFFIC` |
| Context đã refresh, runner đang chạy | `CORRECT` | `REFUSING_TRAFFIC` |
| Startup hoàn tất, có thể phục vụ | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Chủ động tạm dừng nhận lưu lượng | `CORRECT` | `REFUSING_TRAFFIC` |
| Tác vụ bảo trì hoàn tất, có thể phục vụ lại | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Lỗi nội bộ không thể phục hồi | `BROKEN` | Phụ thuộc chính sách dừng và lỗi |
| Đang dừng có kiểm soát | Có thể còn `CORRECT` trong lúc drain | `REFUSING_TRAFFIC` |

Bảng mô tả mục tiêu trạng thái theo vòng đời và các sự kiện ứng dụng công bố. Trạng thái ở một thời điểm thực tế phụ thuộc vào giai đoạn startup/shutdown và những `AvailabilityChangeEvent` mà ứng dụng hoặc framework đã phát.

Nếu dùng Actuator ngoài Kubernetes, nhớ bật health probes nếu cần. Nếu triển khai Kubernetes, hãy kiểm tra đúng endpoint, HTTP status và cổng mà probe thực sự gọi. Khi cấu hình readiness động, cần quan sát cả chiều chuyển từ accepting sang refusing và chiều phục hồi.

## 12. Những nhầm lẫn thường gặp

### Liveness và readiness là một

Không đúng. Liveness trả lời liệu tiến trình có nên tiếp tục tồn tại; readiness trả lời liệu instance có thể nhận công việc mới. Một instance có thể live nhưng không ready trong thời gian khởi động, bảo trì hoặc drain.

### ApplicationReadyEvent đồng nghĩa mọi thứ luôn ready về sau

`ApplicationReadyEvent` là mốc startup. `ReadinessState` là trạng thái có thể được cập nhật nhiều lần sau startup bằng `AvailabilityChangeEvent`. Việc ứng dụng đã từng ready không có nghĩa nó không thể chuyển sang `REFUSING_TRAFFIC`.

### Phát REFUSING_TRAFFIC sẽ tự chặn HTTP request

Không đúng. Event thay đổi trạng thái được công bố trong ứng dụng. Một cơ chế như Kubernetes readiness probe và Service routing cần sử dụng trạng thái đó. Một số request đang xử lý hoặc vừa được định tuyến vẫn có thể tiếp tục.

### Phát BROKEN sẽ tự restart JVM

Không đúng. `BROKEN` công bố tình trạng nội bộ. Việc restart phụ thuộc hệ thống giám sát hoặc orchestrator quan sát liveness probe và chính sách restart đã cấu hình.

### Kiểm tra database ở liveness để ứng dụng luôn khỏe

Kiểm tra dependency ngoài ứng dụng trong liveness có thể khiến mọi replica restart cùng lúc vì một sự cố chung. Nên dành liveness cho tình trạng lỗi nội bộ không thể phục hồi; lựa chọn readiness hay health group riêng cho dependency tùy theo yêu cầu vận hành.

### Cho rằng health và availability là cùng một API

`ApplicationAvailability` quản lý trạng thái liveness/readiness; Actuator health tổng hợp `HealthIndicator` để công bố sức khỏe. Các health group liveness/readiness có thể sử dụng availability state, nhưng health và availability có phạm vi trách nhiệm khác nhau.

## 13. Cách chọn và sử dụng trạng thái phù hợp

Khi thiết kế tín hiệu trạng thái cho một Spring Boot service:

1. Xác định rõ khi nào instance được phép nhận lưu lượng mới.
2. Sử dụng `ReadinessState.REFUSING_TRAFFIC` cho giai đoạn startup chưa hoàn tất, tạm rút lưu lượng hoặc chuẩn bị dừng.
3. Chuyển sang `ReadinessState.ACCEPTING_TRAFFIC` khi instance thực sự đáp ứng điều kiện phục vụ.
4. Chỉ công bố `LivenessState.BROKEN` cho lỗi nội bộ nghiêm trọng không thể phục hồi theo chính sách của ứng dụng.
5. Dùng `ApplicationAvailability` để đọc trạng thái hiện tại và `AvailabilityChangeEvent` để công bố thay đổi.
6. Dùng Actuator health probes để hệ thống vận hành quan sát trạng thái, cùng cấu hình liveness, readiness và startup probes phù hợp.
7. Phối hợp readiness với graceful shutdown, timeout và thời gian rút lưu lượng khỏi load balancer.
8. Tránh biến health probe thành chuỗi kiểm tra dependency nặng và không ổn định.

`ApplicationAvailability` tạo một hợp đồng rõ ràng giữa vòng đời Spring Boot và hệ thống vận hành. Liveness cho biết khi nào tiến trình không còn khả năng phục hồi; readiness cho biết khi nào instance sẵn sàng hoặc tạm ngừng nhận công việc. Khi áp dụng đúng hai tín hiệu này, ứng dụng có thể khởi động, phục vụ, tạm dừng và kết thúc theo cách dễ quan sát và kiểm soát hơn.

