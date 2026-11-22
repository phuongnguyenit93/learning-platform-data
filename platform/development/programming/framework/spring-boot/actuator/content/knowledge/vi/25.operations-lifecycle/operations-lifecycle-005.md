# Theo dõi AvailabilityChangeEvent trong chu kỳ sống ứng dụng

Một ứng dụng Spring Boot có thể đã khởi tạo xong ngữ cảnh Spring nhưng vẫn đang nạp dữ liệu cần thiết trước khi phục vụ yêu cầu. Khi đó, ứng dụng vẫn hoạt động bình thường, còn bộ cân bằng tải cần đợi. Spring Boot biểu diễn hai quyết định này bằng hai loại trạng thái độc lập và phát `AvailabilityChangeEvent<S>` để thành phần trong ứng dụng có thể theo dõi các lần công bố trạng thái.

| Loại trạng thái | Giá trị của Spring Boot | Câu hỏi vận hành |
| --- | --- | --- |
| `LivenessState` | `CORRECT`, `BROKEN` | Tiến trình có còn hoạt động đúng hoặc có khả năng tự phục hồi không? |
| `ReadinessState` | `ACCEPTING_TRAFFIC`, `REFUSING_TRAFFIC` | Hạ tầng có nên chuyển yêu cầu mới tới phiên bản ứng dụng này ngay lúc này không? |

Ví dụ, khi một phiên bản ứng dụng đang nạp bộ nhớ đệm, trạng thái hợp lý là `CORRECT` và `REFUSING_TRAFFIC`. Hạ tầng có thể tạm ngừng chuyển yêu cầu tới phiên bản đó trong khi để nó tiếp tục chuẩn bị.

## Khi nào Spring Boot công bố trạng thái?

Trình tự dưới đây áp dụng cho một lần khởi động thành công trên Spring Boot 3.3.x, với cách xử lý sự kiện đồng bộ mặc định.

| Mốc | Điều có thể quan sát |
| --- | --- |
| Trước khi Boot công bố trạng thái | Khi có thể đọc `ApplicationAvailability`, các phương thức `getLivenessState()` và `getReadinessState()` dùng giá trị mặc định `BROKEN` và `REFUSING_TRAFFIC` nếu chưa nhận được sự kiện tương ứng. Giá trị mặc định có thể xuất hiện mà chưa có sự kiện. |
| Sau khi làm mới ngữ cảnh Spring | Boot phát `ApplicationStartedEvent`, rồi phát `AvailabilityChangeEvent<LivenessState>` với `CORRECT`. |
| Trong lúc chạy `ApplicationRunner` và `CommandLineRunner` | Liveness thường đã là `CORRECT`. Readiness vẫn mặc định là `REFUSING_TRAFFIC` nếu ứng dụng chưa tự công bố giá trị khác. |
| Sau khi các runner hoàn tất | Boot phát `ApplicationReadyEvent`, rồi phát `AvailabilityChangeEvent<ReadinessState>` với `ACCEPTING_TRAFFIC`. |
| Khi đóng ngữ cảnh web đang hoạt động | Boot công bố `REFUSING_TRAFFIC` khi bắt đầu đóng ngữ cảnh. Với graceful shutdown được bật, máy chủ có thời gian xử lý các yêu cầu đang chạy theo cấu hình tắt ứng dụng. |

Nếu mục tiêu là ghi nhận đúng thời điểm Boot **công bố readiness**, hãy nghe `AvailabilityChangeEvent<ReadinessState>`. Trình nghe `ApplicationReadyEvent` chạy trước lần công bố `ACCEPTING_TRAFFIC` mặc định. Nếu một runner chỉ lên lịch công việc nền rồi trả về, Boot có thể báo sẵn sàng khi công việc nền vẫn đang chạy. Hãy hoàn thành phần chuẩn bị bắt buộc trong runner nếu nó quyết định ứng dụng có thể phục vụ an toàn.

## Chọn cách quan sát phù hợp

- **Ghi lại các lần công bố.** Đặt một phương thức `@EventListener` trong bean Spring và dùng kiểu tham số cụ thể như `AvailabilityChangeEvent<ReadinessState>`. Nếu cần theo dõi cả liveness, thêm một phương thức nhận `AvailabilityChangeEvent<LivenessState>`. Trong trình nghe, lấy trạng thái của lần công bố từ `event.getState()`. Có thể ghi thêm `event.getTimestamp()` và nguồn phát từ `event.getSource()` khi điều tra.
- **Đọc trạng thái hiện tại.** Tiêm `ApplicationAvailability` rồi gọi `getReadinessState()` hoặc `getLivenessState()` tại thời điểm cần ra quyết định. `getLastChangeEvent(ReadinessState.class)` trả sự kiện gần nhất đã nhận cho kiểu trạng thái đó, hoặc `null` nếu chưa có. Nếu cần dựng lại trình tự qua nhiều lần chuyển trạng thái hoặc qua một lần khởi động lại, hãy lưu nhật ký sự kiện ra ngoài tiến trình.
- **Công bố trạng thái do ứng dụng quyết định.** Gọi `AvailabilityChangeEvent.publish(context, state)` trên ngữ cảnh ứng dụng. Ví dụ, một phiên bản chuẩn bị bảo trì có thể phát `REFUSING_TRAFFIC`, rồi phát `ACCEPTING_TRAFFIC` khi đã phục vụ lại được. Cần xác định thành phần chịu trách nhiệm cho quyết định này vì mỗi lần phát cập nhật trạng thái mới nhất theo kiểu. Phát lại cùng một giá trị vẫn gửi một sự kiện, nên mã xử lý cần chịu được việc nhận trùng.

Spring mặc định gọi trình nghe sự kiện ngay trên luồng phát. Ghi log ngắn phù hợp với mốc vòng đời này. Nếu cần gửi dữ liệu qua mạng hoặc chạy công việc lâu, hãy chuyển việc đó ra khỏi trình nghe để tránh kéo dài quá trình khởi động hoặc tắt ứng dụng.

## Thực hành với Java 17 và Spring Boot 3.3

Chương trình bên dưới chạy Spring Boot ở chế độ không có máy chủ web để quan sát trực tiếp thứ tự sự kiện. Boot tự công bố hai mốc khởi động. Sau khi `run()` trả về, chương trình tự phát hai sự kiện readiness để mô phỏng tạm dừng nhận yêu cầu và mở lại. Lưu mã vào `AvailabilityDemo.java`.

```java
package demo.availability;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class AvailabilityDemo {
    public static void main(String[] args) {
        var application = new SpringApplication(AvailabilityDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (var context = application.run(args)) {
            AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
            AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);

            var availability = context.getBean(ApplicationAvailability.class);
            System.out.println("AFTER_RESUME " + availability.getReadinessState());
        }
    }

    @Bean
    ApplicationRunner checkWhileStarting(ApplicationAvailability availability) {
        return args -> System.out.println("RUNNER " + availability.getLivenessState()
                + " / " + availability.getReadinessState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("LIVENESS " + event.getState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS " + event.getState());
    }
}
```

Để chạy riêng, đặt `pom.xml` sau cạnh tệp Java. Dự án chỉ cần các thư viện từ `spring-boot-starter`.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.availability</groupId>
    <artifactId>availability-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.3.0</version>
        </dependency>
    </dependencies>
</project>
```

Từ thư mục chứa hai tệp, tải thư viện bằng Maven rồi biên dịch và chạy với JDK 17 trở lên.

```bash
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
javac -cp "lib/*" -d out AvailabilityDemo.java
java -cp "out:lib/*" demo.availability.AvailabilityDemo
```

Trên Windows, dùng `java -cp "out;lib/*" demo.availability.AvailabilityDemo`. Khi chạy với cấu hình mặc định của ví dụ, chương trình in ra các dòng sau.

```text
LIVENESS CORRECT
RUNNER CORRECT / REFUSING_TRAFFIC
READINESS ACCEPTING_TRAFFIC
READINESS REFUSING_TRAFFIC
READINESS ACCEPTING_TRAFFIC
AFTER_RESUME ACCEPTING_TRAFFIC
```

Dòng `RUNNER` minh họa khoảng thời gian liveness và readiness khác nhau. Hai dòng `READINESS ACCEPTING_TRAFFIC` đến từ hai lần công bố riêng. Dòng đầu do Boot phát sau runner. Dòng sau do chương trình phát khi kết thúc mô phỏng bảo trì. `AFTER_RESUME` xác nhận lần công bố cuối đã cập nhật giá trị mà các thành phần khác đọc được qua `ApplicationAvailability`.

## Đối chiếu với các phép kiểm tra của Actuator

Trong ứng dụng **web** đã có `spring-boot-starter-actuator`, có thể bật hai nhóm kiểm tra ở môi trường local bằng cấu hình sau. Ví dụ dòng lệnh giả định cổng `8080`, đường dẫn quản trị mặc định và quyền truy cập phù hợp.

```properties
management.endpoint.health.probes.enabled=true
```

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

Với các nhóm mặc định và endpoint đang truy cập được, `CORRECT` ánh xạ thành `UP` cho liveness. `REFUSING_TRAFFIC` ánh xạ thành `OUT_OF_SERVICE` cho readiness và trả HTTP 503 theo cấu hình mặc định. `ACCEPTING_TRAFFIC` đưa nhóm readiness về `UP`. Sự kiện cho biết **khi nào ứng dụng công bố trạng thái**, còn lần gọi HTTP cho biết **trạng thái nhóm tại thời điểm kiểm tra**. Khi máy chủ chưa mở cổng hoặc đã đóng cổng, có thể nhận lỗi kết nối thay vì phản hồi HTTP.

Việc phát `REFUSING_TRAFFIC` cập nhật tín hiệu mà hạ tầng đọc. Muốn bộ cân bằng tải ngừng gửi yêu cầu mới, hạ tầng phải dùng tín hiệu readiness để quyết định tuyến. Nếu một phụ thuộc dùng chung như cơ sở dữ liệu gặp sự cố, hãy cân nhắc ảnh hưởng đến khả năng phục vụ khi cấu hình readiness. Gắn sự cố đó vào liveness có thể khiến nhiều phiên bản bị khởi động lại cùng lúc trong khi nguyên nhân vẫn còn.

Tài liệu Spring Boot 3.3. [Vòng đời và thứ tự sự kiện](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners) · [API AvailabilityChangeEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html) · [Các nhóm kiểm tra của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
