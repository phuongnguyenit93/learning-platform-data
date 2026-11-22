# Vai trò của ApplicationAvailability, LivenessState và ReadinessState

Một tiến trình Java đang chạy chưa chắc đã sẵn sàng phục vụ. Chẳng hạn, ứng dụng đã tạo xong các bean nhưng còn nạp bảng quy tắc bắt buộc trước khi xử lý yêu cầu. Nếu chỉ có một tín hiệu “tốt/xấu”, hệ thống vận hành khó phân biệt cần chờ ứng dụng hoàn tất công việc hay cần khởi động lại nó.

Spring Boot biểu diễn hai câu hỏi riêng:

- **Liveness — khả năng hoạt động đúng của nội bộ ứng dụng:** trạng thái hiện tại có đủ đúng để ứng dụng tiếp tục hoạt động hoặc tự phục hồi không?
- **Readiness — mức sẵn sàng nhận lưu lượng:** bản ứng dụng này có nên được nhận thêm yêu cầu vào lúc này không?

Bài học tập trung vào mô hình trạng thái và API Java của Spring Boot 3.3.x. Actuator là lớp công bố trạng thái ra ngoài; cấu hình đầy đủ Kubernetes và cách xây dựng mọi loại kiểm tra sức khỏe thuộc phạm vi rộng hơn.

## 1. Ba kiểu dữ liệu đảm nhiệm ba vai trò

| Thành phần | Vai trò | Ví dụ sử dụng |
| --- | --- | --- |
| `ApplicationAvailability` | Giao diện để đọc trạng thái khả dụng hiện tại của ứng dụng | Tiêm bean rồi gọi `getLivenessState()` hoặc `getReadinessState()` |
| `LivenessState` | Enum mô tả trạng thái hoạt động nội bộ | `CORRECT`, `BROKEN` |
| `ReadinessState` | Enum mô tả quyết định có sẵn sàng nhận lưu lượng | `ACCEPTING_TRAFFIC`, `REFUSING_TRAFFIC` |
| `AvailabilityChangeEvent<S>` | Sự kiện dùng để công bố một thay đổi trạng thái | Phát sự kiện chứa `ReadinessState.REFUSING_TRAFFIC` |

Cả hai enum đều triển khai `AvailabilityState`. Trong một ứng dụng Boot được tự động cấu hình thông thường, thành phần sử dụng chỉ cần phụ thuộc vào giao diện `ApplicationAvailability`; `ApplicationAvailabilityBean` là lớp triển khai giữ thông tin các sự kiện đã nhận. Không tự tạo một đối tượng triển khai riêng trong mỗi dịch vụ, vì chúng sẽ không đại diện cho cùng trạng thái được Spring quản lý.

Giao diện này phục vụ việc **đọc**; nó không có phương thức `setReadinessState(...)`. Muốn thay đổi trạng thái được quản lý, thành phần ứng dụng phát `AvailabilityChangeEvent` vào đúng `ApplicationContext`. Đây là API của Spring Boot core, nên có thể sử dụng mà không cần mở một endpoint Actuator. Xem [API ApplicationAvailability của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html).

## 2. Hiểu đúng từng enum

### LivenessState: có cần thay thế bản ứng dụng này không?

- `CORRECT`: trạng thái nội bộ được coi là đúng để tiếp tục hoạt động.
- `BROKEN`: nội bộ ứng dụng được coi là hỏng; trong tình huống đang vận hành, đây là tín hiệu cho hạ tầng cân nhắc khởi động lại bản ứng dụng.

Ví dụ phù hợp với liveness bị hỏng là dữ liệu nền tảng trong bộ nhớ bị phá vỡ đến mức ứng dụng không còn cách tự tái tạo đáng tin cậy. Một cơ sở dữ liệu bên ngoài mất kết nối vài giây thường không được giải quyết bằng cách khởi động lại tất cả bản ứng dụng.

`CORRECT` không chứng minh rằng mọi giao dịch nghiệp vụ sẽ thành công. Nó cũng không đo thời gian phản hồi, mức đầy của hàng đợi hay tình trạng của mọi hệ thống phụ thuộc. Ngược lại, việc có giá trị `BROKEN` tự nó không gọi `System.exit`, không đóng JVM và không thực hiện restart. Vai trò restart thuộc bộ giám sát/hạ tầng đã được cấu hình để đọc tín hiệu. Xem [định nghĩa LivenessState](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html).

### ReadinessState: có nên đưa yêu cầu mới tới đây không?

- `ACCEPTING_TRAFFIC`: bản ứng dụng thông báo rằng nó sẵn sàng nhận lưu lượng.
- `REFUSING_TRAFFIC`: bản ứng dụng thông báo rằng hiện tại nó chưa sẵn sàng nhận lưu lượng mới.

Một khoảng tạm dừng nhận lưu lượng có thể phục vụ việc chuẩn bị tài nguyên, xử lý quá tải có kiểm soát hoặc thực hiện bảo trì cục bộ. Sau khi nguyên nhân đã hết, ứng dụng có thể công bố lại `ACCEPTING_TRAFFIC`.

Tuy nhiên, **công bố trạng thái không đồng nghĩa với chặn yêu cầu ngay tại controller**. Nếu bộ cân bằng tải chưa đọc probe, nếu có độ trễ cập nhật, hoặc nếu người dùng gọi trực tiếp địa chỉ ứng dụng, yêu cầu vẫn có thể đến nơi. Việc từ chối nghiệp vụ tại chỗ cần cơ chế tiếp nhận riêng nếu bài toán yêu cầu. Tương tự, readiness không tự dừng lịch chạy tác vụ, luồng xử lý nền hoặc bộ tiêu thụ thông điệp.

Hai câu hỏi liveness/readiness được giới thiệu trong [mô hình Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### Vì sao không gộp hai trạng thái?

| Tình huống minh họa | Liveness | Readiness | Ý nghĩa vận hành |
| --- | --- | --- | --- |
| Chuẩn bị dữ liệu sau khi context khởi tạo | `CORRECT` | `REFUSING_TRAFFIC` | Chờ chuẩn bị xong; restart thường không giúp |
| Hoạt động bình thường | `CORRECT` | `ACCEPTING_TRAFFIC` | Có thể nhận lưu lượng |
| Tạm dừng nhận yêu cầu mới để bảo trì cục bộ | `CORRECT` | `REFUSING_TRAFFIC` | Giữ tiến trình, tạm chuyển lưu lượng sang nơi khác |
| Phát hiện lỗi nội bộ không tự phục hồi được | `BROKEN` | Theo trạng thái readiness đã công bố | Cần chính sách xử lý lỗi và bộ giám sát thích hợp |

Hàng cuối nhấn mạnh rằng hai giá trị được lưu theo hai loại trạng thái riêng. Việc phát `LivenessState.BROKEN` không tự phát thêm `ReadinessState.REFUSING_TRAFFIC`. Ứng dụng cần có quyết định phối hợp phù hợp nếu muốn biểu đạt cả hai.

## 3. Quan hệ với vòng đời Spring Boot

Boot chủ động công bố các mốc khả dụng trong quá trình chạy ứng dụng:

| Mốc | Liveness thông thường | Readiness thông thường |
| --- | --- | --- |
| Chưa nhận sự kiện xác lập trạng thái | `BROKEN` theo giá trị mặc định của getter | `REFUSING_TRAFFIC` theo giá trị mặc định của getter |
| Context đã refresh; sau `ApplicationStartedEvent` | `CORRECT` | `REFUSING_TRAFFIC` |
| Đang thực hiện `ApplicationRunner` / `CommandLineRunner` | `CORRECT` | `REFUSING_TRAFFIC` |
| Các runner hoàn tất; sau `ApplicationReadyEvent` | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Bắt đầu đóng context của ứng dụng web Boot | Thông thường vẫn `CORRECT` | `REFUSING_TRAFFIC` |

Thứ tự quan trọng là: refresh context → `ApplicationStartedEvent` → sự kiện liveness `CORRECT` → thực hiện runner → `ApplicationReadyEvent` → sự kiện readiness `ACCEPTING_TRAFFIC`. Vì vậy, một listener đang xử lý chính `ApplicationReadyEvent` không nên giả định sự kiện readiness tiếp theo đã được xử lý. Xem [thứ tự sự kiện của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners).

Giá trị mặc định `BROKEN` trước khi có sự kiện là trạng thái thận trọng khi chưa xác lập được khả năng hoạt động; không phải bằng chứng rằng ứng dụng đã gặp sự cố không thể phục hồi.

Nếu dữ liệu bắt buộc phải có trước khi phục vụ, một runner có thể thực hiện công việc đó trước khi trả về. Nếu runner chỉ khởi chạy một tác vụ bất đồng bộ rồi kết thúc ngay, Boot không tự đợi tác vụ riêng ấy hoàn tất. Cần thiết kế cơ chế sẵn sàng cho trường hợp đó, thay vì suy luận rằng mọi luồng nền đều đã xong khi Boot chuyển sang ready.

Trong Boot 3.3, muốn cho máy chủ web xử lý yêu cầu đang chạy trước khi dừng thì cấu hình `server.shutdown=graceful`. Readiness chuyển sang từ chối lưu lượng và cơ chế dừng có trật tự là hai phần phối hợp; chỉ thay enum không tạo ra toàn bộ quy trình dừng máy chủ. Khi HTTP server chưa khởi động hoặc đã dừng, trạng thái còn có thể được hiểu bên trong nhưng URL probe có thể chưa hoặc không còn truy cập được. Xem [cơ chế graceful shutdown của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).

## 4. Đọc, công bố và quan sát thay đổi

### Đọc trạng thái

Hai getter chuyên biệt trả về enum tương ứng:

- `getLivenessState()`: liveness hiện tại, mặc định `BROKEN` khi chưa có thông tin.
- `getReadinessState()`: readiness hiện tại, mặc định `REFUSING_TRAFFIC` khi chưa có thông tin.

Khi cần biết có sự kiện thực sự hay chưa, sử dụng `getState(ReadinessState.class)`: kết quả có thể là `null` nếu chưa có sự kiện của loại đó. Biến thể `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)` cho phép chỉ định giá trị thay thế. Không nhầm giá trị thay thế này với một sự kiện đã được công bố.

`getLastChangeEvent(ReadinessState.class)` trả về sự kiện cuối của loại đó và cũng có thể là `null`. Sự kiện cho biết trạng thái, nguồn phát và thời điểm tạo; nó không phải một nhật ký đầy đủ của mọi lần thay đổi.

### Công bố thay đổi

`AvailabilityChangeEvent.publish(context, state)` phát sự kiện qua context. Biến thể `publish(publisher, source, state)` phù hợp khi cần chỉ rõ thành phần hoặc nguyên nhân làm nguồn sự kiện. Xem [API AvailabilityChangeEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).

Trong cách cấu hình sự kiện mặc định của Spring, việc phát được phân phối đồng bộ. Ví dụ thực hành bên dưới đọc lại ngay sau khi phát vì giữ cấu hình mặc định này. Nếu ứng dụng thay cơ chế phân phối bằng thực thi bất đồng bộ, phải xét lại thời điểm có thể quan sát trạng thái mới; không chuyển giả định của ví dụ sang mọi cấu hình.

Để quan sát bằng listener trong ứng dụng Boot, có thể dùng `@EventListener` với tham số `AvailabilityChangeEvent<ReadinessState>` rồi đọc `event.getState()`. Listener nên xử lý nhanh, tránh thực hiện kiểm tra mạng chậm trong luồng phát sự kiện.

## 5. Thực hành: hai trạng thái thay đổi độc lập

Ví dụ dùng **JDK 21, Gradle 8.5 và Spring Boot core 3.3.0**. Mã Java chỉ dùng cú pháp tương thích Java 17+. Mục đích là quan sát API mà không cần dựng máy chủ HTTP, Actuator hay Kubernetes.

Đây là một chương trình độc lập dùng `GenericApplicationContext`, **không gọi `SpringApplication.run(...)`**. Nó đăng ký đúng một `ApplicationAvailabilityBean` và tự phát các sự kiện. Vì vậy các nhãn `live`, `ready`, `paused` là các bước của thí nghiệm, không phải bằng chứng rằng vòng đời Boot tự chạy trong context này.

Tạo cấu trúc:

```text
availability-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/AvailabilityDemo.java
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'availability-demo'
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot:3.3.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'AvailabilityDemo'
}

tasks.register('copyRuntimeLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

Nội dung `src/main/java/AvailabilityDemo.java`:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ApplicationAvailabilityBean;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.support.GenericApplicationContext;

public class AvailabilityDemo {
    public static void main(String[] args) {
        try (var context = new GenericApplicationContext()) {
            context.registerBean("applicationAvailability",
                    ApplicationAvailabilityBean.class);
            context.refresh();

            var availability = context.getBean(ApplicationAvailability.class);
            print("initial", availability);

            AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
            print("live", availability);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            print("ready", availability);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            print("paused", availability);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            print("resumed", availability);

            AvailabilityChangeEvent.publish(context, LivenessState.BROKEN);
            print("broken", availability);

            var last = availability.getLastChangeEvent(ReadinessState.class);
            System.out.println("lastReadiness=" + last.getState());
        }
    }

    private static void print(
            String phase, ApplicationAvailability availability) {
        System.out.printf("%s: %s / %s%n", phase,
                availability.getLivenessState(),
                availability.getReadinessState());
    }
}
```

Chạy trong thư mục ví dụ, với Gradle 8.5 đã được cài:

```shell
gradle -q run --console=plain
```

Lần đầu cần mạng để tải thư viện. Nếu thư mục ví dụ đã có Gradle Wrapper 8.5, có thể thay `gradle` bằng `./gradlew` trên Linux/macOS hoặc `.\gradlew.bat` trên Windows.

Đầu ra của chương trình:

```text
initial: BROKEN / REFUSING_TRAFFIC
live: CORRECT / REFUSING_TRAFFIC
ready: CORRECT / ACCEPTING_TRAFFIC
paused: CORRECT / REFUSING_TRAFFIC
resumed: CORRECT / ACCEPTING_TRAFFIC
broken: BROKEN / ACCEPTING_TRAFFIC
lastReadiness=ACCEPTING_TRAFFIC
```

Có ba điểm cần đối chiếu:

1. `initial` có hai giá trị mặc định vì chưa có sự kiện availability, dù context của thí nghiệm đã refresh.
2. `paused` chỉ đổi readiness; liveness vẫn `CORRECT`. `resumed` cho thấy việc tạm ngừng nhận lưu lượng có thể đảo ngược.
3. `broken` đổi liveness nhưng readiness vẫn `ACCEPTING_TRAFFIC`. Dòng cuối xác nhận sự kiện readiness cuối vẫn là sự kiện đã phát ở bước `resumed`.

Có thể dùng trực tiếp `javac`/`java` sau khi sao chép các thư viện chạy bằng task đã khai báo:

```shell
gradle -q copyRuntimeLibraries
javac --release 17 -cp "build/runtime-libs/*" -d build/manual src/main/java/AvailabilityDemo.java
```

Chạy trên Windows:

```shell
java -cp "build/manual;build/runtime-libs/*" AvailabilityDemo
```

Chạy trên Linux/macOS:

```shell
java -cp "build/manual:build/runtime-libs/*" AvailabilityDemo
```

Hai cách chạy cho cùng bảy dòng kết quả. Dấu phân cách các mục classpath là `;` trên Windows và `:` trên Linux/macOS.

## 6. Áp dụng vào bean trong ứng dụng Boot thực tế

Trong ứng dụng có tự động cấu hình Boot, tiêm giao diện đọc trạng thái và context đang quản lý ứng dụng. Ví dụ dưới đây là **một bean tích hợp**, không phải chương trình có `main` độc lập. Đặt lớp trong phạm vi component scan của ứng dụng Boot:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class TrafficAdmission {
    private final ApplicationAvailability availability;
    private final ApplicationContext context;

    public TrafficAdmission(
            ApplicationAvailability availability, ApplicationContext context) {
        this.availability = availability;
        this.context = context;
    }

    public boolean isAcceptingTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }

    public void pause() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resume() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

`pause()` và `resume()` chỉ công bố quyết định tiếp nhận lưu lượng; ví dụ không tự mở API điều khiển chúng. `isAcceptingTraffic()` đọc tín hiệu để thành phần khác quyết định cách xử lý. Nếu dùng nó để điều khiển tiếp nhận nghiệp vụ thì vẫn phải triển khai hành vi từ chối, chính sách đồng thời và xử lý yêu cầu đã nhận.

Đây là ví dụ có **một nơi điều khiển readiness**. Với nhiều lý do từ chối đồng thời, không để từng thành phần tự gọi `ACCEPTING_TRAFFIC` khi việc riêng của mình hoàn tất. Chẳng hạn, chuẩn bị dữ liệu xong nhưng bảo trì vẫn đang bật thì ứng dụng vẫn phải từ chối lưu lượng. Nên có thành phần tổng hợp các điều kiện rồi công bố quyết định chung.

Ngoài ra, sự kiện readiness phát quá sớm lúc khởi động có thể bị sự kiện ready mặc định của Boot phát sau đó thay thế. Muốn giữ trạng thái bảo trì qua giai đoạn này, cần phối hợp với vòng đời hoặc một kiểm tra readiness được tổng hợp riêng. Cặp enum không tự quản lý danh sách nguyên nhân đang chặn.

## 7. Actuator nối trạng thái Java với probe như thế nào?

Luồng khái niệm:

```text
Vòng đời Boot / quyết định của ứng dụng
              ↓
AvailabilityChangeEvent
              ↓
ApplicationAvailabilityBean
              ↓ đọc qua ApplicationAvailability
LivenessStateHealthIndicator / ReadinessStateHealthIndicator
              ↓
Health group / probe HTTP
              ↓
Hạ tầng giám sát đọc và thực hiện chính sách
```

Theo ánh xạ mặc định của hai indicator trong Spring Boot 3.3:

| Giá trị trong ứng dụng | Trạng thái health của indicator |
| --- | --- |
| `LivenessState.CORRECT` | `UP` |
| `LivenessState.BROKEN` | `DOWN` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` |

Đó là phép chuyển đổi giữa enum Java và mô hình health; tên enum không phải tên trạng thái JSON. Mã HTTP còn do ánh xạ health và cấu hình nhóm quyết định. Một nhóm readiness có thêm kiểm tra khác có thể thất bại dù enum readiness vẫn là `ACCEPTING_TRAFFIC`; đọc nhóm health cũng không tự ghi ngược kết quả vào enum.

Với ứng dụng web có `spring-boot-starter-actuator`, có thể chủ động bật hai nhóm probe ngoài Kubernetes:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Khi dùng đường dẫn mặc định, truy cập `/actuator/health/liveness` và `/actuator/health/readiness`. Còn cần bảo đảm endpoint health được bật, được công bố và bên kiểm tra được phép truy cập. Không thêm cơ sở dữ liệu vào liveness chỉ vì muốn có nhiều phép kiểm tra hơn. Những lựa chọn về hệ thống phụ thuộc của readiness phải dựa trên khả năng phục vụ thực tế. Xem [Kubernetes Probes trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Điểm cần nhớ khi chẩn đoán là có ba lớp: **trạng thái bên trong**, **kết quả probe**, **hành động của hạ tầng**. Chúng có liên hệ nhưng không xảy ra đồng thời một cách tuyệt đối.

## 8. Lỗi thường gặp và cách suy luận

| Cách hiểu hoặc cách làm | Vấn đề | Cách xử lý phù hợp |
| --- | --- | --- |
| “JVM còn chạy nghĩa là liveness luôn đúng” | Tiến trình có thể còn sống nhưng nội bộ đã không tự phục hồi được | Xác định liveness theo khả năng hoạt động đúng |
| “Readiness từ chối thì cần restart” | Tình huống có thể chỉ là chuẩn bị hoặc bảo trì tạm thời | Tách quyết định chuyển lưu lượng khỏi restart |
| Tự `new ApplicationAvailabilityBean()` trong dịch vụ | Đọc một đối tượng tách rời trạng thái được quản lý | Tiêm `ApplicationAvailability` của context |
| Gọi `getLastChangeEvent(...).getState()` ngay khi chưa có sự kiện | Có thể gặp `NullPointerException` | Kiểm tra `null`; dùng getter enum khi chỉ cần giá trị hiện tại |
| Cho rằng đổi readiness sẽ lập tức đóng mọi kết nối | Enum chỉ biểu đạt quyết định khả dụng | Cấu hình probe và cơ chế tiếp nhận/dừng phù hợp |
| Mỗi tác vụ tự bật lại readiness | Một tác vụ hoàn tất có thể che lấp nguyên nhân từ chối khác | Tổng hợp điều kiện ở một nơi |
| Gộp kết quả mọi health check thành liveness | Lỗi phụ thuộc bên ngoài có thể dẫn tới restart hàng loạt | Chọn kiểm tra theo ý nghĩa vận hành của từng tín hiệu |

Khi có sự cố “bản ứng dụng vẫn nhận yêu cầu dù đã từ chối lưu lượng”, kiểm tra lần lượt: giá trị readiness trong đúng context; kết quả nhóm readiness; đường dẫn/port mà bên giám sát đang đọc; thời gian đồng bộ của hạ tầng; có đường gọi trực tiếp bỏ qua bộ định tuyến hay không. Không kết luận enum không hoạt động chỉ từ một yêu cầu còn tới được máy chủ.

## 9. Tự kiểm tra

1. Ở ví dụ độc lập, bỏ lần phát `LivenessState.CORRECT` rồi giữ lần phát readiness accepting. Cặp trạng thái có thể trở thành gì?
2. Nếu thêm một kiểm tra vào health group readiness và kiểm tra ấy trả về lỗi, có nhất thiết `ApplicationAvailability.getReadinessState()` cũng đổi không?
3. Một tác vụ khởi động được runner gửi sang luồng nền rồi runner kết thúc. Tại sao readiness mặc định của Boot có thể chuyển sang accepting trước khi tác vụ ấy hoàn tất?
4. Hai lý do đang chặn tiếp nhận là “bảo trì” và “chưa nạp xong dữ liệu”. Khi dữ liệu nạp xong, thành phần tổng hợp nên công bố trạng thái nào?

Đáp án định hướng:

1. `BROKEN / ACCEPTING_TRAFFIC`: chưa có sự kiện liveness mới; hai loại trạng thái độc lập.
2. Không. Kết quả nhóm health là kết quả tổng hợp; nó không tự phát sự kiện để sửa enum.
3. Boot theo dõi việc runner đã hoàn tất, không tự biết thời điểm kết thúc của tác vụ nền tùy ý mà runner khởi chạy.
4. Vẫn `REFUSING_TRAFFIC` vì lý do bảo trì còn hiệu lực.

Sau bài này, người học cần xác định được mình đang **đọc trạng thái**, **công bố quyết định mới**, hay **cấu hình bên ngoài phản ứng với quyết định đó**, rồi chọn đúng thành phần tương ứng.
