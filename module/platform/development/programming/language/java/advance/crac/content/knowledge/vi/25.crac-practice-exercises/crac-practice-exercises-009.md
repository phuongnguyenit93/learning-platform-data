# So sánh Spring Boot onRefresh với checkpoint sau làm nóng

Spring Boot có thể dùng CRaC để tạo checkpoint theo hai thời điểm rất khác nhau. Cách thứ nhất là checkpoint tự động tại giai đoạn Spring context refresh bằng thuộc tính JVM `-Dspring.context.checkpoint=onRefresh`. Cách thứ hai là để ứng dụng khởi động hoàn chỉnh, chạy workload warm-up rồi yêu cầu checkpoint từ bên ngoài, thường bằng lệnh jcmd.

Hai cách đều lưu trạng thái JVM để khôi phục sau này, nhưng điểm chụp khác nhau quyết định lượng công việc đã hoàn tất, trạng thái nào được giữ và mức độ phức tạp khi vận hành. onRefresh tạo ảnh sớm: các singleton không lazy đã được tạo và callback khởi tạo đã chạy, nhưng lifecycle bean chưa start và Spring chưa phát ContextRefreshedEvent. Checkpoint sau làm nóng được tạo muộn hơn, khi web server đã chạy, ứng dụng đã đi qua startup runner và có thể đã xử lý các request đại diện. Ảnh này có thể giữ lại cache, class đã được nạp và JIT code đã được tối ưu.

Bài thực hành này dùng cùng một ứng dụng Spring Boot để so sánh cold start, checkpoint onRefresh và checkpoint thủ công sau warm-up. Mục tiêu là hiểu chính xác thời điểm checkpoint, cách tạo và restore từng loại ảnh, cách đo thời gian đến readiness và những rủi ro cần kiểm soát khi giữ trạng thái ứng dụng đã chạy.

## 1. Mục tiêu thực hành

Sau bài này, bạn có thể:

- Mô tả vị trí của LifecycleProcessor.onRefresh trong quá trình khởi động Spring.
- Giải thích những gì đã và chưa xảy ra khi checkpoint onRefresh được tạo.
- Tạo checkpoint tự động bằng spring.context.checkpoint=onRefresh.
- Dùng spring.context.exit=onRefresh để kiểm tra cùng mốc lifecycle mà không cần CRaC runtime.
- Khởi động ứng dụng hoàn chỉnh, gửi workload warm-up và tạo checkpoint thủ công.
- Restore hai loại checkpoint bằng CRaC-enabled JDK.
- So sánh thời gian restore-to-ready, thời gian request đầu tiên, kích thước ảnh và chi phí tạo ảnh.
- Chọn chiến lược phù hợp với mục tiêu startup và yêu cầu vận hành.

Trong toàn bộ bài thực hành, hãy dùng cùng JDK CRaC build, application build, container image và resource limits. Nếu thay đổi nhiều yếu tố cùng lúc, kết quả so sánh sẽ không còn đáng tin cậy.

## 2. Chuẩn bị môi trường

Spring Framework tích hợp CRaC từ dòng 6.1; Spring Boot hỗ trợ tích hợp này từ dòng 3.2. Cần kiểm tra phiên bản thực tế của Spring Framework được Spring Boot BOM quản lý, thay vì chỉ nhìn version của plugin build.

Các điều kiện cơ bản:

1. Linux environment có hỗ trợ checkpoint/restore theo JDK distribution đang dùng.
2. JDK build có tích hợp CRaC.
3. Có dependency org.crac:crac trên runtime classpath; tài liệu Spring hiện hành hỗ trợ phiên bản 1.4.0 trở lên.
4. Runtime và checkpoint engine được cấu hình theo hướng dẫn của nhà cung cấp.
5. Có quyền tạo checkpoint, ghi checkpoint directory và thực hiện restore.
6. Có đủ CPU, memory, disk và quyền hệ điều hành cho cả hai lần chạy.

Ví dụ cấu hình Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.crac:crac:1.4.0")
}
~~~

Phiên bản 1.4.0 ở đây là mốc tương thích tối thiểu được tài liệu Spring nêu, không phải khuyến nghị bỏ qua dependency management. Với dự án thật, chọn phiên bản đã được kiểm chứng với JDK CRaC và dependency graph của ứng dụng.

Có thể kiểm tra runtime trước khi chạy:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Ghi lại vendor, version, VM build, java.home, OS và architecture. Đừng dùng JDK thông thường để tạo checkpoint rồi giả định có thể restore bằng một JDK CRaC khác.

## 3. Hiểu vị trí onRefresh trong Spring startup

Spring tạo ApplicationContext, đăng ký bean definition, thực hiện dependency injection và khởi tạo các singleton eager. Sau đó context đi qua giai đoạn hoàn tất refresh. Trong quá trình đó, LifecycleProcessor.onRefresh() được gọi để khởi động các bean triển khai Lifecycle/SmartLifecycle. Khi giai đoạn này hoàn tất, Spring phát ContextRefreshedEvent.

Khi thuộc tính spring.context.checkpoint được đặt thành onRefresh, Spring Framework tạo checkpoint ngay trong LifecycleProcessor.onRefresh(). Thời điểm này có ý nghĩa cụ thể:

**Đã hoàn tất trước checkpoint:**

- ApplicationContext đã được tạo và cấu hình.
- Bean definitions đã được đăng ký.
- Các singleton không lazy đã được khởi tạo.
- Dependency injection đã hoàn tất cho các bean đó.
- Các callback khởi tạo như InitializingBean.afterPropertiesSet() đã chạy.
- Các bước khởi tạo bean thông thường, bao gồm @PostConstruct, đã chạy cho bean tương ứng.

**Chưa hoàn tất tại thời điểm checkpoint:**

- LifecycleProcessor chưa start các bean Lifecycle/SmartLifecycle.
- ContextRefreshedEvent chưa được phát.
- ApplicationRunner và CommandLineRunner chưa chạy.
- ApplicationReadyEvent chưa được phát.
- Ứng dụng chưa đạt trạng thái ready theo luồng khởi động Spring Boot.
- Workload HTTP thực tế chưa được dùng để warm-up ứng dụng.
- Các bean lazy chưa được tạo nếu chưa có đường code nào yêu cầu chúng.

Vì vậy, onRefresh là một checkpoint sớm trong startup. Nó giữ được kết quả tạo context và khởi tạo singleton eager, nhưng không giữ một ứng dụng đã chạy qua các request đại diện.

~~~text
SpringApplication.run()
        |
        v
Tạo Environment và ApplicationContext
        |
        v
Load bean definitions
        |
        v
Instantiate non-lazy singletons
        |
        v
@PostConstruct / afterPropertiesSet
        |
        v
LifecycleProcessor.onRefresh()
        |
        +---- spring.context.checkpoint=onRefresh?
        |               |
        |              Yes
        |               |
        |               v
        |         CRaC checkpoint
        |               |
        |         process lưu ảnh
        |         và kết thúc lượt tạo
        |
        v
Start Lifecycle / SmartLifecycle beans
        |
        v
Publish ContextRefreshedEvent
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
        |
        v
Ứng dụng ready và nhận request
~~~

Sơ đồ mô tả luồng lifecycle ở mức khái niệm. Chi tiết nội bộ có thể khác theo phiên bản Spring, nhưng ranh giới onRefresh được tài liệu Spring định nghĩa rõ: checkpoint diễn ra trước khi lifecycle start và trước ContextRefreshedEvent.

## 4. Checkpoint sau làm nóng diễn ra ở thời điểm nào?

Checkpoint thủ công sau warm-up được tạo sau khi ứng dụng đã khởi động đầy đủ. Quy trình thông thường:

1. Khởi chạy Spring Boot bằng JDK CRaC và cấu hình thư mục checkpoint.
2. Chờ ứng dụng đạt readiness.
3. Gửi các request hoặc chạy tác vụ warm-up an toàn.
4. Xác nhận cache và dependency đã sẵn sàng.
5. Yêu cầu checkpoint từ bên ngoài ứng dụng.
6. Spring dừng các bean Lifecycle đang chạy để chuẩn bị checkpoint.
7. CRaC lưu trạng thái tiến trình.
8. Khi restore, các callback phục hồi chạy và Spring khởi động lại các bean Lifecycle.

Checkpoint này có thể giữ thêm:

- Bean lazy đã được tạo bởi workload.
- Class và code path đã được load.
- JIT compilation và profiling state đã tích lũy.
- Cache ứng dụng đã được nạp.
- Metadata hoặc dữ liệu tham chiếu đã được warm-up.
- Trạng thái nội bộ của thư viện được giữ trong JVM image.
- Các thành phần ứng dụng đã chạy sau ApplicationReadyEvent.

Đây là lý do checkpoint sau warm-up thường có khả năng giảm độ trễ request đầu tiên và thời gian đến hiệu năng ổn định hơn. Tuy nhiên, nó cũng mang theo nhiều trạng thái biến động hơn, phụ thuộc môi trường và có thể chứa dữ liệu người dùng hoặc credential.

## 5. Tạo ứng dụng mẫu để dùng cho cả hai phương pháp

Dùng một ứng dụng nhỏ có service thực hiện công việc CPU-bound và cache kết quả. Cùng một endpoint sẽ được gọi trong warm-up của phương pháp thủ công. Trong phương pháp onRefresh, endpoint chưa được gọi trước checkpoint.

Ví dụ service:

~~~java
package com.example.cracdemo;

import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class CatalogService {

    private final Map<Integer, String> cache = new ConcurrentHashMap<>();

    public String lookup(int id) {
        return cache.computeIfAbsent(id, this::loadAndTransform);
    }

    private String loadAndTransform(int id) {
        long value = id;

        for (int i = 0; i < 100_000; i++) {
            value = (value * 31 + i) % 1_000_000_007L;
        }

        return "catalog-" + id + "-" + value;
    }

    public int cachedEntries() {
        return cache.size();
    }
}
~~~

Ví dụ controller:

~~~java
package com.example.cracdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/catalog/{id}")
    public Map<String, Object> lookup(@PathVariable int id) {
        long started = System.nanoTime();
        String value = catalogService.lookup(id);
        long elapsedNanos = System.nanoTime() - started;

        return Map.of(
                "id", id,
                "value", value,
                "elapsedMicros", elapsedNanos / 1_000,
                "cacheEntries", catalogService.cachedEntries());
    }

    @GetMapping("/ready-info")
    public Map<String, Object> readyInfo() {
        return Map.of(
                "status", "UP",
                "cacheEntries", catalogService.cachedEntries());
    }
}
~~~

Lớp Application:

~~~java
package com.example.cracdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CracDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CracDemoApplication.class, args);
    }
}
~~~

Đây là workload minh họa để quan sát khác biệt giữa bean initialization, cache warm-up và code path được thực thi. Một phép benchmark thực tế nên dùng workload đại diện cho service thật, ví dụ deserialize payload, serialize response, truy vấn repository, gọi client hoặc chạy business logic quan trọng.

## 6. Quan sát các mốc lifecycle

Để thấy checkpoint onRefresh nằm trước các giai đoạn nào, có thể thêm một bean triển khai SmartLifecycle và một listener cho ContextRefreshedEvent.

~~~java
package com.example.cracdemo;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class LifecycleMarker implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("MARKER: SmartLifecycle.start");
    }

    @Override
    public void stop() {
        running = false;
        System.out.println("MARKER: SmartLifecycle.stop");
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Listener:

~~~java
package com.example.cracdemo;

import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshEventMarker {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        System.out.println("MARKER: ContextRefreshedEvent");
    }
}
~~~

Có thể thêm InitializingBean để quan sát callback khởi tạo:

~~~java
package com.example.cracdemo;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class InitializationMarker implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        System.out.println("MARKER: afterPropertiesSet");
    }
}
~~~

Khi chạy với onRefresh, log của afterPropertiesSet có trước checkpoint. Log SmartLifecycle.start và ContextRefreshedEvent chưa xuất hiện trong lượt tạo checkpoint vì checkpoint được thực hiện trước hai mốc đó. Khi restore, tiến trình tiếp tục sau điểm checkpoint và Spring hoàn tất phần startup còn lại.

Khi chạy cold start thông thường, các marker xuất hiện theo lifecycle startup bình thường. Khi tạo checkpoint thủ công sau khi ứng dụng ready, tất cả marker đã xuất hiện trước checkpoint; lúc checkpoint, SmartLifecycle.stop được gọi, và sau restore các bean được start lại.

Không dùng log marker làm phép đo hiệu năng chính. Logging có overhead và độ phân giải thời gian không phù hợp để thay thế metric. Chúng chỉ giúp quan sát thứ tự lifecycle.

## 7. Thực hành A: kiểm tra onRefresh mà chưa cần CRaC

Spring cung cấp thuộc tính spring.context.exit=onRefresh cho mục đích kiểm tra. Nó khiến ứng dụng thoát tại cùng giai đoạn LifecycleProcessor.onRefresh mà không tạo checkpoint. Có thể dùng nó để xem startup đã đi đến đâu và phát hiện bean initialization nào phụ thuộc vào dịch vụ ngoài trước khi lifecycle start.

Chạy:

~~~bash
java -Dspring.context.exit=onRefresh -jar build/libs/crac-demo.jar
~~~

Quan sát:

- afterPropertiesSet đã chạy.
- SmartLifecycle.start chưa chạy.
- ContextRefreshedEvent chưa được phát.
- ApplicationRunner và ApplicationReadyEvent chưa xảy ra.
- Process kết thúc ở mốc onRefresh.

Thuộc tính này hữu ích khi ứng dụng có bean khởi tạo kết nối tới database hoặc dịch vụ ngoài ngay trong constructor, @PostConstruct hay afterPropertiesSet. Nếu các kết nối đó không cần thiết để tạo checkpoint sớm, hãy cân nhắc lazy initialization, trì hoãn việc mở kết nối đến lifecycle start hoặc thiết kế bean để chỉ giữ cấu hình ở giai đoạn khởi tạo.

spring.context.exit=onRefresh là công cụ kiểm tra phase, không thay thế phép thử CRaC. Nó không chứng minh checkpoint/restore thành công và không thực hiện các callback CRaC.

## 8. Thực hành B: tạo checkpoint tự động bằng onRefresh

Trước tiên, bảo đảm checkpoint directory chưa chứa artifact của lần chạy khác. Dùng thư mục riêng cho từng phương pháp.

Khởi chạy ứng dụng:

~~~bash
java \
  -Dspring.context.checkpoint=onRefresh \
  -XX:CRaCCheckpointTo=./checkpoint-on-refresh \
  -jar build/libs/crac-demo.jar
~~~

Spring Framework nhận biết thuộc tính spring.context.checkpoint=onRefresh và yêu cầu CRaC tạo checkpoint trong giai đoạn LifecycleProcessor.onRefresh.

Kết quả mong đợi:

1. Spring khởi tạo ApplicationContext.
2. Các singleton eager và callback khởi tạo hoàn tất.
3. Spring yêu cầu CRaC checkpoint.
4. Runtime ghi checkpoint vào checkpoint-on-refresh.
5. Lượt chạy tạo checkpoint kết thúc theo hành vi của CRaC runtime.
6. Khi restore, JVM tiếp tục startup sau điểm checkpoint; Spring start lifecycle beans, phát ContextRefreshedEvent và hoàn tất Spring Boot startup.

Restore bằng cùng JDK CRaC tương thích:

~~~bash
java -XX:CRaCRestoreFrom=./checkpoint-on-refresh
~~~

Cú pháp đầy đủ và cách truyền các tham số bổ sung khi restore có thể khác theo JDK vendor. Hãy dùng đúng hướng dẫn của distribution đã tạo checkpoint. Không thêm một JAR khác hoặc chạy một application build khác nếu runtime không yêu cầu.

Sau restore, chờ readiness endpoint:

~~~bash
curl http://localhost:8080/ready-info
~~~

Gọi endpoint catalog và ghi lại thời gian request đầu tiên. Ở checkpoint onRefresh, cache catalog chưa được warm-up bởi endpoint trước checkpoint, nên request đầu tiên sẽ thực hiện loadAndTransform.

## 9. Thực hành C: tạo checkpoint sau warm-up

Dùng một checkpoint directory riêng. Lần này không bật spring.context.checkpoint=onRefresh.

Khởi chạy ứng dụng với tùy chọn CRaC checkpoint destination:

~~~bash
java \
  -XX:CRaCCheckpointTo=./checkpoint-warmed \
  -jar build/libs/crac-demo.jar
~~~

Chờ ứng dụng đạt readiness:

~~~bash
curl http://localhost:8080/ready-info
~~~

Gửi các request warm-up đại diện. Ví dụ:

~~~bash
for id in 1 2 3 4 5 6 7 8 9 10; do
  curl "http://localhost:8080/catalog/$id"
done
~~~

Gọi lặp lại cùng một tập ID để tạo cache hit. Với ứng dụng thật, warm-up cần đi qua những đường code quan trọng, không chỉ gọi một endpoint health. Cân nhắc warm-up serialization, validation, repository query, mapping, template hoặc client call theo workload thực tế.

Khi ứng dụng đã được làm nóng và không còn request đang chạy, mở terminal thứ hai và tìm PID hoặc command target của JVM. Tạo checkpoint:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Một số JDK hoặc hướng dẫn vendor cho phép dùng tên process/JAR thay cho PID. Kiểm tra jcmd -l để xác định target và dùng cú pháp được runtime hỗ trợ.

Với checkpoint on-demand, Spring dừng các bean đang chạy triển khai Lifecycle để chúng có cơ hội đóng resource. CRaC lưu trạng thái JVM. Sau restore, Spring khởi động lại các bean đó. Các thư viện không tích hợp với Spring có thể cần org.crac.Resource riêng để đóng/mở resource đúng lifecycle.

Restore:

~~~bash
java -XX:CRaCRestoreFrom=./checkpoint-warmed
~~~

Chờ readiness rồi gọi lại các ID đã warm-up. Nếu cache nằm trong heap và được giữ trong checkpoint, request có thể trở thành cache hit ngay sau restore. Tuy nhiên, kết quả này chỉ đúng với cache có thể giữ qua checkpoint; cache dựa trên TTL, remote state hoặc identity theo instance có thể cần invalidate hoặc refresh.

## 10. Khác biệt về thời điểm và trạng thái được giữ

Bảng sau tóm tắt các mốc chính:

| Thành phần/trạng thái | onRefresh | Sau warm-up |
|---|---|---|
| ApplicationContext | Đã tạo | Đã tạo |
| Non-lazy singleton | Đã khởi tạo | Đã khởi tạo |
| afterPropertiesSet / @PostConstruct | Đã chạy cho bean đã khởi tạo | Đã chạy |
| Lazy bean chưa được truy cập | Chưa khởi tạo | Có thể đã khởi tạo nếu warm-up dùng đến |
| SmartLifecycle.start | Chưa chạy tại điểm checkpoint | Đã chạy trước checkpoint |
| ContextRefreshedEvent | Chưa phát tại điểm checkpoint | Đã phát |
| ApplicationRunner / CommandLineRunner | Chưa chạy tại điểm checkpoint | Đã chạy |
| ApplicationReadyEvent | Chưa phát tại điểm checkpoint | Đã phát |
| HTTP request workload | Chưa chạy | Có thể đã chạy |
| Application cache | Chủ yếu trạng thái khởi tạo | Có thể đã warm-up |
| JIT compilation | Chủ yếu mức khởi tạo sớm | Có thể đã tối ưu qua workload |
| Web server lifecycle | Chưa start tại điểm checkpoint | Đã start; Spring cần xử lý lifecycle khi checkpoint |
| Dependency connection | Có thể chưa được mở nếu mở ở lifecycle start; connection mở sớm cần được xử lý | Có thể đang hoạt động và phải đóng/reconnect đúng cách |

Không phải mọi ứng dụng đều có các component này. Bảng cho biết vị trí tương đối trong lifecycle, không khẳng định một bean cụ thể luôn được tạo hoặc giữ lại.

## 11. So sánh ưu điểm và giới hạn

### onRefresh

Ưu điểm:

- Tạo checkpoint tự động trong startup, ít cần một bước warm-up riêng.
- Dễ chuẩn hóa trong pipeline build hoặc chuẩn bị image.
- Giữ kết quả khởi tạo ApplicationContext và singleton eager.
- Không cần chờ ứng dụng nhận traffic thật trước khi tạo checkpoint.
- Có thể phù hợp khi mục tiêu là bỏ qua phần lớn chi phí tạo bean và cấu hình context.

Giới hạn:

- Chưa chạy Lifecycle.start tại điểm checkpoint.
- Chưa phát ContextRefreshedEvent.
- Chưa chạy ApplicationRunner/CommandLineRunner.
- Chưa xử lý request để warm-up application code hoặc JIT.
- Bean lazy chưa được khởi tạo nếu chưa được truy cập.
- Không mang lại toàn bộ lợi ích của một JVM đã chạy qua workload đại diện.
- Bean initialization có thể vẫn truy cập remote service hoặc giữ credential trong checkpoint.

### Checkpoint sau warm-up

Ưu điểm:

- Có thể giữ cache và dữ liệu tham chiếu đã được nạp.
- Có thể giữ class đã load và code path đã được JIT tối ưu.
- Ứng dụng có thể đạt hiệu năng request tốt hơn ngay sau restore.
- Có thể warm-up các đường nghiệp vụ cụ thể thay vì chỉ khởi tạo framework.
- Hữu ích khi cold-start hoặc first-request latency là yêu cầu quan trọng.

Giới hạn:

- Cần chạy ứng dụng và warm-up trước khi tạo ảnh.
- Thường cần quyền truy cập dependency từ môi trường tạo checkpoint.
- Cần kiểm soát request đang chạy, scheduler, transaction và message consumer.
- Cần xử lý socket, file, connection pool và các resource bên ngoài.
- Có thể mang theo cache, token hoặc dữ liệu nhạy cảm trong heap.
- Cần xác định trạng thái nào phải invalidate hoặc refresh sau restore.
- Checkpoint có thể phụ thuộc chặt hơn vào host, network và runtime profile.

## 12. Ảnh hưởng đến startup latency và first-request latency

Không nên chỉ đo thời gian process xuất hiện. Có ít nhất ba đại lượng cần phân biệt:

- **Restore-to-ready:** Từ lúc yêu cầu restore đến khi ứng dụng đạt readiness.
- **First-request latency:** Độ trễ của request đầu tiên sau khi readiness thành công.
- **Steady-state latency:** Độ trễ sau khi ứng dụng đã xử lý workload ổn định.

onRefresh có thể rút ngắn restore-to-ready vì Spring không phải tạo lại toàn bộ ApplicationContext và các singleton eager. Nhưng code path nghiệp vụ chưa được warm-up; request đầu tiên có thể vẫn trả giá cho class loading, JIT compilation, cache miss hoặc lazy bean initialization.

Checkpoint sau warm-up có thể làm tăng thời gian chuẩn bị artifact, nhưng giảm first-request latency và đưa ứng dụng gần steady-state hơn. Kết quả thực tế phụ thuộc workload, số code path được warm-up, cache policy và cách JVM xử lý JIT state.

Một ví dụ minh họa:

~~~text
Cold start:
  JVM startup
  + Spring context refresh
  + lifecycle start
  + runners
  + readiness
  + first request warm-up

onRefresh restore:
  JVM restore
  + Spring lifecycle start
  + ContextRefreshedEvent
  + runners
  + readiness
  + first request warm-up

Warm checkpoint restore:
  JVM restore
  + resource recovery
  + lifecycle restart
  + readiness
  + request trên code path đã warm-up
~~~

Sơ đồ không phải cam kết thời gian hoặc thứ tự nội bộ đầy đủ của mọi ứng dụng. Nó chỉ cho thấy phần công việc nào có thể được chuyển sang trước thời điểm checkpoint.

## 13. Thiết kế warm-up có ý nghĩa

Một warm-up tốt phải đại diện cho workload production nhưng không gây side effect không mong muốn.

Nên ưu tiên:

- Request đọc dữ liệu hoặc thao tác idempotent.
- Payload đại diện cho kích thước và cấu trúc thường gặp.
- Các đường code có tần suất cao.
- Serialization/deserialization, validation và mapping.
- Query có thể chạy an toàn trên dữ liệu test hoặc read replica.
- Tạo cache dữ liệu tham chiếu có thể chia sẻ.
- Khởi tạo client theo cách có thể refresh sau restore.

Cần tránh:

- Tạo đơn hàng, thanh toán hoặc giao dịch thật.
- Gửi email, SMS hoặc message nghiệp vụ.
- Tạo tài khoản hoặc dữ liệu dùng chung không có cleanup.
- Giữ session hoặc credential của người dùng thật trong ảnh.
- Warm-up bằng tenant hoặc identity không phù hợp với restore target.
- Tạo cache gắn với node/hostname cũ rồi dùng lại ở node mới.
- Tạo job nền chạy liên tục trong khi chuẩn bị checkpoint.

Nếu warm-up cần remote services, hãy xác định dữ liệu và identity dùng để tạo checkpoint có thể được chia sẻ an toàn không. Với dữ liệu phụ thuộc môi trường, cân nhắc làm mới sau restore thay vì snapshot nó.

## 14. Resource lifecycle khi checkpoint sau warm-up

Ở thời điểm checkpoint sau warm-up, ứng dụng đã có thể mở socket, HTTP connection pool, database pool, message consumer và scheduler. Những resource này không nhất thiết còn hợp lệ khi tiến trình được restore ở thời điểm hoặc máy khác.

Spring Framework phối hợp checkpoint/restore với Lifecycle contract. Khi checkpoint on-demand, Spring dừng các bean Lifecycle đang chạy để chúng có cơ hội đóng resource; sau restore, Spring start lại chúng. Với thư viện không tích hợp Spring, có thể triển khai org.crac.Resource và đăng ký resource vào CRaC context.

Các việc cần kiểm tra:

- Web server ngừng nhận request mới và drain request đang chạy.
- Database transaction đã commit hoặc rollback.
- Connection pool có đóng/recreate hoặc validate lại đúng cách.
- HTTP client loại bỏ connection stale.
- Message consumer pause, commit và tham gia group lại sau restore.
- Scheduler không chạy bù các tác vụ ngoài ý muốn.
- Executor dừng task và khởi động lại với cấu hình phù hợp.
- File watcher hoặc file handle được mở lại.
- Credential provider refresh token và identity theo môi trường mới.

Spring Boot quản lý lifecycle của một số resource như socket, file và thread pool trong phạm vi nhất định; không nên hiểu rằng mọi thư viện bên thứ ba đều được tự động hỗ trợ. Kiểm tra tài liệu của dependency và viết adapter CRaC nếu cần.

## 15. Lưu ý với @Scheduled khi dùng checkpoint on-demand

Với tác vụ định kỳ dùng fixedRate, thời gian tiến trình bị dừng giữa checkpoint và restore có thể khiến các lần chạy bị bỏ lỡ được thực thi bù sau restore. Ví dụ một task được khai báo fixedRate 5 giây, nhưng checkpoint được lưu trong 10 phút, có thể có nhiều lần chạy đã đến hạn trong khoảng thời gian đó.

Nếu không muốn hành vi catch-up, tài liệu Spring khuyến nghị cân nhắc fixedDelay hoặc cron expression. fixedDelay tính thời gian chờ sau mỗi lần task thực thi; cron được tính lại theo lịch. Dù chọn loại nào, tác vụ vẫn cần idempotency và cơ chế lease nếu nhiều replica có thể chạy cùng lúc.

Trong bài thực hành, nếu ứng dụng có scheduler, ghi nhận hành vi trước và sau restore. Không dùng một scheduler chạy side effect thật trong warm-up benchmark.

## 16. Bảo mật checkpoint được tạo sau warm-up

Checkpoint sau warm-up có thể chứa nhiều trạng thái nhạy cảm hơn checkpoint onRefresh:

- Token đã được resolve.
- Connection configuration và endpoint.
- Cache có dữ liệu ứng dụng.
- Request hoặc response buffer.
- Dữ liệu nghiệp vụ vừa được warm-up.
- Thông tin identity của instance.
- Trạng thái client và thư viện.

Checkpoint onRefresh cũng có thể chứa secret đã được đọc trong quá trình bean initialization. Vì vậy, không có phương pháp nào mặc nhiên an toàn chỉ vì checkpoint được tạo sớm.

Cần bảo vệ checkpoint directory, artifact storage và đường truyền; hạn chế quyền đọc/restore; dùng encryption at rest và TLS; quản lý retention; không đóng gói secret dài hạn vào image; và làm mới credential theo identity của instance sau restore. Nếu checkpoint được đưa vào container image, xem image đó như một artifact có thể chứa dữ liệu trong bộ nhớ ứng dụng.

## 17. Đo lường công bằng giữa ba phương pháp

Dùng ba kịch bản:

1. Cold start thông thường, không checkpoint.
2. Automatic checkpoint tại onRefresh.
3. Manual checkpoint sau warm-up.

Đo các metric:

| Metric | Cold start | onRefresh | Sau warm-up |
|---|---|---|---|
| JVM process launch đến readiness | Có | Đo khi restore | Đo khi restore |
| Thời gian tạo checkpoint | Không áp dụng | Có | Có |
| Thời gian chuẩn bị context | Toàn bộ | Đã lưu phần trước onRefresh | Đã lưu phần lớn startup |
| Warm-up time trước checkpoint | Không áp dụng | Không có request warm-up | Có |
| Restore-to-ready | Không áp dụng | Có | Có |
| First-request latency | Có | Có | Có |
| Steady-state latency | Có | Có | Có |
| Artifact size | Không áp dụng | Có | Có |
| CPU/memory khi tạo ảnh | Không áp dụng | Có | Có |
| Dependency cần lúc tạo ảnh | Startup dependencies | Bean initialization dependencies | Warm-up dependencies |

Đo ít nhất:

- Từ lúc process được gọi đến readiness.
- Thời gian tạo checkpoint.
- Thời gian từ checkpoint request đến artifact-ready.
- First-request latency.
- p50/p95/p99 của workload đại diện.
- Artifact size trước và sau compression nếu có.
- CPU-seconds, peak memory và I/O bytes.
- Tỷ lệ checkpoint/restore thành công.

Không cộng thời gian warm-up vào restore-to-ready của manual checkpoint rồi so sánh với onRefresh restore. Hãy báo cáo cả chi phí chuẩn bị checkpoint và lợi ích restore riêng. Nếu checkpoint được dùng cho nhiều replica, có thể phân bổ chi phí tạo ảnh theo số lần restore trong mô hình chi phí, nhưng vẫn phải báo cáo latency từng phase.

## 18. Thiết lập thí nghiệm lặp lại

Để kết quả có thể so sánh:

1. Dùng cùng application build.
2. Dùng cùng JDK vendor, version và build.
3. Dùng cùng container image, CPU/memory limits và kernel.
4. Dùng cùng storage class hoặc cùng loại local disk.
5. Reset checkpoint directory trước mỗi lần tạo mới.
6. Giữ workload warm-up nhất quán.
7. Dùng cùng dependency state hoặc ghi rõ khác biệt.
8. Chạy nhiều lượt, không kết luận từ một mẫu.
9. Báo median và p95, kèm min/max hoặc độ phân tán.
10. Restore artifact vừa tạo và kiểm tra readiness/functionality.

Với onRefresh, kiểm tra checkpoint directory sau lần chạy tạo ảnh rồi restore. Với manual warm-up, tạo ảnh sau khi cùng một workload warm-up hoàn tất. Không dùng artifact từ build cũ cho một kịch bản và build mới cho kịch bản còn lại.

Nếu muốn đo lợi ích JIT, chạy đủ workload để code path có cơ hội được biên dịch. Một vài request đơn lẻ có thể chỉ warm cache nhưng chưa đủ để tối ưu code. Không đặt một số request cố định cho mọi ứng dụng; xác định từ profiling hoặc workload thực tế.

## 19. Bảng ghi kết quả

Dùng bảng sau để ghi kết quả từng lần chạy:

| Trường | Cold start | onRefresh | Sau warm-up |
|---|---:|---:|---:|
| JDK build | | | |
| Spring Boot / Framework | | | |
| CPU limit / memory limit | | | |
| Process launch đến readiness (ms) | | | |
| Checkpoint preparation (ms) | N/A | | |
| Artifact-ready (ms) | N/A | | |
| Artifact size (MiB) | N/A | | |
| Restore-to-ready (ms) | N/A | | |
| First request (ms) | | | |
| Steady-state p95 (ms) | | | |
| CPU-seconds khi tạo ảnh | N/A | | |
| Peak memory khi tạo ảnh (MiB) | N/A | | |
| Restore success | N/A | | |

Đừng điền số liệu ước lượng. Ghi rõ cách đo, số lượt chạy và percentile. Nếu có phase chồng lấp, đo end-to-end riêng thay vì cộng các phase duration.

## 20. Diễn giải kết quả

Một số kiểu kết quả thường gặp:

**onRefresh restore nhanh hơn cold start nhưng request đầu tiên vẫn chậm.** Điều này phù hợp với việc context và singleton eager đã được khởi tạo, trong khi code path nghiệp vụ chưa được warm-up.

**Warm checkpoint có restore-to-ready tương đương onRefresh nhưng first request nhanh hơn.** Lợi ích có thể nằm ở cache, class loading hoặc JIT state được giữ lại, không nhất thiết ở thời điểm readiness.

**Warm checkpoint restore-to-ready chậm hơn onRefresh.** Ảnh lớn hơn hoặc nhiều resource cần stop/restart có thể làm tăng chi phí restore. Kiểm tra callback, resource recovery và kích thước image.

**Warm checkpoint tạo ảnh lâu hơn.** Ứng dụng có thêm cache, heap pages và trạng thái runtime; callback cũng phải dừng nhiều component hơn. Đổi lại, nhiều lần restore có thể hưởng lợi từ trạng thái warm-up.

**onRefresh checkpoint thất bại do kết nối remote.** Một bean có thể mở kết nối trong constructor hoặc initialization callback trước khi Lifecycle.start. Dùng spring.context.exit=onRefresh để kiểm tra, sau đó trì hoãn kết nối đến lifecycle start nếu kiến trúc cho phép.

**Warm checkpoint restore thất bại vì resource stale.** Cần sửa lifecycle của client, pool, socket, scheduler hoặc file watcher. Không nên kết luận phương pháp warm checkpoint không phù hợp trước khi xác định resource gây lỗi.

## 21. Chọn phương pháp nào?

Chọn onRefresh khi:

- Mục tiêu là giảm thời gian tạo ApplicationContext và singleton eager.
- Muốn tạo checkpoint tự động trong pipeline build.
- Không cần giữ cache nghiệp vụ hoặc JIT warm-up.
- Muốn giảm sự phụ thuộc vào remote workload trong giai đoạn tạo ảnh.
- Ứng dụng có thể khởi động các Lifecycle bean và chạy runner sau restore trong thời gian chấp nhận được.

Chọn checkpoint sau warm-up khi:

- First-request latency và thời gian đạt hiệu năng ổn định rất quan trọng.
- Có thể chạy workload warm-up đại diện và an toàn.
- Cache hoặc code path đã warm có giá trị sau restore.
- Nền tảng có thể cung cấp dependency cần thiết để warm-up.
- Có thể quản lý lifecycle của socket, pool, scheduler, consumer và credential.
- Checkpoint artifact được bảo vệ và có compatibility profile rõ ràng.

Có thể dùng cả hai trong giai đoạn thử nghiệm để tìm điểm cân bằng. Tuy nhiên, pipeline production nên có một quy trình tạo ảnh được định nghĩa rõ ràng, không chọn ngẫu nhiên giữa các checkpoint có trạng thái và điều kiện khác nhau.

## 22. Các lỗi thường gặp trong bài thực hành

**Nghĩ rằng onRefresh nghĩa là ứng dụng đã sẵn sàng.** Checkpoint xảy ra trước Lifecycle.start và ContextRefreshedEvent. Runner và ApplicationReadyEvent chưa chạy.

**Cho rằng onRefresh đã warm-up JIT.** Khởi tạo bean không tương đương với thực thi workload đại diện. Code path chưa chạy có thể chưa được tối ưu.

**Dùng ApplicationRunner để warm-up cho onRefresh.** Runner chạy sau refresh, nên không thể warm-up trước checkpoint onRefresh. Dùng checkpoint thủ công sau khi runner và workload hoàn tất.

**Quên bean lazy.** Bean chưa được truy cập có thể chưa được tạo tại onRefresh. Xác định lazy bean nào cần thiết và warm-up chúng nếu chọn manual checkpoint.

**Tạo checkpoint thủ công khi còn request đang chạy.** Request có thể giữ transaction, stream hoặc socket. Drain công việc và dùng lifecycle phù hợp.

**Cho rằng Spring quản lý mọi dependency.** Spring hỗ trợ một số resource trong phạm vi giới hạn. Kiểm tra thư viện ngoài và bổ sung org.crac.Resource khi cần.

**So sánh thời gian không cùng mốc.** Startup-to-ready, checkpoint creation và restore-to-ready là metric khác nhau. Ghi riêng từng loại.

**Warm-up tạo side effect.** Request benchmark có thể gửi message hoặc ghi dữ liệu thật. Dùng thao tác idempotent và dữ liệu thử.

**Không kiểm tra scheduler sau restore.** fixedRate có thể chạy bù các lần bị bỏ lỡ. Chọn fixedDelay/cron hoặc chính sách phù hợp.

**Dùng checkpoint có dependency hoặc credential cũ.** Refresh identity và kết nối theo môi trường restore; bảo vệ artifact như dữ liệu nhạy cảm.

**Chỉ kiểm tra restore thành công mà không gửi request.** Process tồn tại chưa chứng minh cache, dependency và code path hoạt động. Kiểm tra readiness và workload sau restore.

## 23. Checklist hoàn thành

- [ ] Đã xác nhận Spring Framework 6.1+ và Spring Boot 3.2+ hoặc phiên bản có hỗ trợ tương ứng chưa?
- [ ] Đã chạy bằng JDK CRaC và dependency org.crac tương thích chưa?
- [ ] Đã quan sát afterPropertiesSet, Lifecycle.start và ContextRefreshedEvent chưa?
- [ ] Đã xác nhận onRefresh checkpoint diễn ra trước Lifecycle.start và ContextRefreshedEvent chưa?
- [ ] Đã thử spring.context.exit=onRefresh để kiểm tra startup phase chưa?
- [ ] Đã tạo và restore checkpoint onRefresh chưa?
- [ ] Đã chờ ứng dụng ready rồi chạy workload warm-up chưa?
- [ ] Đã tạo checkpoint thủ công bằng cơ chế được JDK hỗ trợ chưa?
- [ ] Đã xác nhận Lifecycle bean stop/restart đúng cách chưa?
- [ ] Đã xử lý resource ngoài Spring và credential theo lifecycle chưa?
- [ ] Đã kiểm tra cache, lazy bean và first-request behavior sau restore chưa?
- [ ] Đã đo cold start, onRefresh restore và warm restore bằng cùng resource profile chưa?
- [ ] Đã đo checkpoint preparation, artifact size, restore-to-ready và first-request latency riêng chưa?
- [ ] Đã chạy nhiều lượt và ghi median/p95 chưa?
- [ ] Đã kiểm tra scheduler, transaction và side effect sau restore chưa?
- [ ] Đã bảo vệ checkpoint artifact và dữ liệu nhạy cảm chưa?
- [ ] Đã chọn chiến lược dựa trên số liệu và yêu cầu vận hành chưa?

## Kết luận

spring.context.checkpoint=onRefresh tạo checkpoint sớm trong LifecycleProcessor.onRefresh. Tại thời điểm đó, các singleton không lazy đã được khởi tạo và callback afterPropertiesSet đã chạy, nhưng Lifecycle bean chưa start, ContextRefreshedEvent chưa được phát và workload ứng dụng chưa được dùng để warm-up. Cách này phù hợp khi muốn lưu trạng thái khởi tạo Spring và rút ngắn phần đầu của startup.

Checkpoint sau warm-up được tạo khi ứng dụng đã chạy đầy đủ và đã thực hiện workload đại diện. Ảnh có thể giữ cache, code path đã load và trạng thái JIT đã tích lũy, giúp giảm first-request latency và đưa instance gần steady-state hơn. Đổi lại, cần kiểm soát resource lifecycle, request đang chạy, dependency, scheduler, credential và dữ liệu nhạy cảm trong checkpoint.

Hãy dùng cùng một ứng dụng để đo cold start, onRefresh và manual warm checkpoint. Tách thời gian tạo ảnh khỏi restore-to-ready và first-request latency, kiểm thử resource recovery trên đúng JDK CRaC, rồi chọn phương pháp dựa trên số liệu. onRefresh tối ưu điểm bắt đầu của Spring context; checkpoint sau warm-up tối ưu trạng thái của ứng dụng đã thực sự chạy.

## Tài liệu tham khảo

- Spring Framework Reference — JVM Checkpoint Restore: https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html
- Spring Boot Reference — Checkpoint and Restore With the JVM: https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html
- Azul CRaC — Frameworks With CRaC Support, phần Spring and Spring Boot: https://docs.azul.com/crac/usage/frameworks
