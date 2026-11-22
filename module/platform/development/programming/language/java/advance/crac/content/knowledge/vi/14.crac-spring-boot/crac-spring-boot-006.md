# Thử giai đoạn khởi tạo bằng `spring.context.exit=onRefresh`

Khi chuẩn bị ứng dụng Spring Boot cho CRaC, cần biết chính xác những công việc nào đã hoàn tất tại thời điểm tạo checkpoint. Một câu hỏi quan trọng là: các bean có thể được khởi tạo mà chưa cần chạy các thành phần lifecycle hay chưa? Spring Framework cung cấp một chế độ thử nghiệm dành cho việc này: đặt JVM system property `spring.context.exit=onRefresh`.

Khi property được bật, Spring chạy quá trình khởi tạo ApplicationContext tới giai đoạn `LifecycleProcessor.onRefresh`, sau đó kết thúc JVM ngay tại điểm đó. Các non-lazy singleton đã được tạo và callback khởi tạo như `InitializingBean.afterPropertiesSet()` đã chạy; các bean lifecycle chưa được tự động start và `ContextRefreshedEvent` chưa được phát. Chế độ này cho phép quan sát xem việc tạo bean có vô tình kết nối database, gọi HTTP service hoặc cần dependency từ xa trước khi ứng dụng bắt đầu chạy hay không.

Đây là phép thử giai đoạn khởi tạo. Nó không tạo checkpoint, không restore tiến trình và không yêu cầu CRaC-enabled JDK, thư viện `org.crac:crac` hay Linux. Khi cần kiểm tra checkpoint thực tế ở cùng giai đoạn, Spring Framework có property riêng là `spring.context.checkpoint=onRefresh`.

## 1. `spring.context.exit=onRefresh` là gì?

`spring.context.exit` là một Spring Framework property được `DefaultLifecycleProcessor` đọc khi khởi tạo. Giá trị được nhận diện là `onRefresh` (không phân biệt chữ hoa/chữ thường). Khi `LifecycleProcessor.onRefresh()` được gọi trong quá trình refresh ApplicationContext, implementation mặc định kiểm tra property này và kết thúc JVM tại giai đoạn đó.

Tính năng được bổ sung từ Spring Framework 6.1. Với Spring Boot, cần kiểm tra phiên bản Spring Framework thực tế trong dependency graph; các bản Spring Boot sử dụng Spring Framework 6.1 trở lên có thể dùng tính năng này khi vẫn dùng `DefaultLifecycleProcessor` mặc định. Không nên chỉ nhìn tên Spring Boot mà bỏ qua phiên bản Framework được resolve hoặc việc ứng dụng có thay thế lifecycle processor hay không.

Property này được thiết kế để kiểm tra quá trình khởi tạo trước khi các bean lifecycle bắt đầu chạy. Ví dụ, một bean có thể tạo HTTP client trong constructor hoặc `@PostConstruct`, trong khi việc mở kết nối thực tế chỉ cần diễn ra khi worker được start. Chạy ứng dụng với `spring.context.exit=onRefresh` giúp phát hiện những kết nối sớm như vậy.

## 2. Spring dừng ở đâu trong vòng đời khởi động?

Spring refresh ApplicationContext qua nhiều giai đoạn. Với phép thử này, điều quan trọng là phân biệt khởi tạo bean với khởi động các bean có lifecycle.

```mermaid
flowchart TD
    A[Spring Boot bắt đầu khởi động] --> B[Đọc cấu hình và tạo ApplicationContext]
    B --> C[Đăng ký bean definitions và tạo non-lazy singletons]
    C --> D[Chạy constructor, dependency injection và init callbacks]
    D --> E[LifecycleProcessor.onRefresh]
    E --> F{spring.context.exit=onRefresh?}
    F -->|Có| G[Runtime.halt(0): kết thúc JVM]
    F -->|Không| H[Start Lifecycle / SmartLifecycle beans]
    H --> I[Phát ContextRefreshedEvent]
    I --> J[Spring Boot tiếp tục runners và sự kiện ready]
```

Khi `spring.context.exit=onRefresh` được bật, JVM kết thúc trong `LifecycleProcessor.onRefresh`. Những công việc đã hoàn thành trước điểm này gồm:

- ApplicationContext đã được tạo và refresh tới giai đoạn lifecycle processor.
- Các non-lazy singleton đã được khởi tạo.
- Constructor, dependency injection, `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và các init callback tương ứng đã chạy đối với bean được tạo.
- Những dependency đồng bộ được gọi trong quá trình khởi tạo bean đã có cơ hội thực thi.

Những công việc chưa diễn ra gồm:

- Các bean `Lifecycle`/`SmartLifecycle` chưa được tự động start bởi `DefaultLifecycleProcessor`.
- `ContextRefreshedEvent` chưa được publish.
- Các bước sau refresh của Spring Boot như chạy `ApplicationRunner` và `CommandLineRunner` chưa diễn ra.
- `ApplicationReadyEvent` chưa được phát.
- Web server lifecycle chưa được start để nhận request. Một số đối tượng server có thể đã được tạo trong quá trình refresh, nhưng giai đoạn start của lifecycle chưa chạy.

Bean lazy-init chỉ được khởi tạo nếu có dependency khác yêu cầu nó. Vì vậy, kết quả của phép thử phản ánh các bean thực sự được khởi tạo ở giai đoạn này, không chứng minh rằng mọi bean trong ứng dụng đã được tạo.

## 3. Cách bật property

Hãy truyền property như một JVM system property ngay khi khởi chạy ứng dụng:

```bash
java -Dspring.context.exit=onRefresh -jar application.jar
```

Trên Windows PowerShell, cách gọi tương đương là:

```powershell
java "-Dspring.context.exit=onRefresh" -jar .\application.jar
```

Nếu chạy bằng Docker, đặt JVM argument trước `-jar`:

```dockerfile
ENTRYPOINT ["java", "-Dspring.context.exit=onRefresh", "-jar", "/app/application.jar"]
```

Nếu ứng dụng được khởi chạy qua một build plugin như `bootRun` hoặc `spring-boot:run`, hãy cấu hình JVM arguments của tiến trình ứng dụng. Đừng nhầm JVM arguments với tham số truyền cho method `main` hoặc với program arguments.

### 3.1. Vì sao nên dùng `-D` thay vì `application.properties`?

`DefaultLifecycleProcessor` đọc giá trị thông qua `SpringProperties.getProperty(...)`. `SpringProperties` tìm property trong file `spring.properties` ở root classpath, sau đó dùng JVM system property làm fallback. Đây là cơ chế property cấp thấp của Spring Framework, không phải tra cứu từ Spring `Environment`.

Vì vậy, cấu hình sau trong `application.properties` hoặc `application.yml` không phải cách được tài liệu Spring hướng dẫn cho property này và thường không được `SpringProperties` nhìn thấy:

```properties
spring.context.exit=onRefresh
```

Hãy ưu tiên `-Dspring.context.exit=onRefresh` để giá trị có mặt ngay từ lúc JVM khởi động. Cũng có thể cấu hình qua `spring.properties` ở root classpath, nhưng file đó là Spring Framework properties file, khác với `application.properties` của Spring Boot.

Giá trị được đọc trong quá trình khởi tạo `DefaultLifecycleProcessor`, nên đừng đợi đến khi ApplicationContext đã refresh rồi mới đặt system property. Đặt property trước khi JVM chạy là cách rõ ràng và dễ tái hiện nhất.

## 4. Điều gì xảy ra khi property được bật?

Trong `DefaultLifecycleProcessor.onRefresh()`, Spring kiểm tra property `spring.context.exit`. Nếu giá trị là `onRefresh`, implementation gọi `Runtime.getRuntime().halt(0)` tại lifecycle phase đó.

Điểm này có một hệ quả quan trọng: đây là kết thúc JVM tức thời, không phải đóng ApplicationContext theo quy trình shutdown thông thường. `Runtime.halt(0)` không khởi chạy shutdown hooks. Do Spring không đi qua `ApplicationContext.close()`, không nên kỳ vọng các callback dọn dẹp như `@PreDestroy`, `DisposableBean.destroy()`, `ContextClosedEvent` hoặc các thao tác đóng tài nguyên do Spring quản lý sẽ chạy.

Mã thoát thường là `0`, nên shell hoặc CI có thể xem tiến trình là thành công. Tuy nhiên, mã thoát này chỉ cho biết JVM đã đi tới điểm exit được cấu hình; nó không chứng minh ứng dụng đã khởi động đầy đủ, web server đã nhận request hay mọi dependency đã sẵn sàng.

Đó là lý do nên dùng chế độ này như một lần chạy chẩn đoán có chủ đích, với môi trường và dữ liệu kiểm thử phù hợp. Không bật property này trong cấu hình production thông thường.

## 5. Dùng phép thử để phát hiện kết nối từ xa quá sớm

Một lợi ích chính của `spring.context.exit=onRefresh` là xác định bean nào cần dịch vụ bên ngoài ngay trong giai đoạn khởi tạo.

Ví dụ, ứng dụng có thể có các thành phần sau:

| Thành phần | Công việc khi khởi tạo | Công việc khi lifecycle start |
|---|---|---|
| `DataSource` | Tạo cấu hình và connection pool object. | Có thể mở kết nối thật khi lấy connection hoặc khi pool khởi động. |
| HTTP client | Tạo client và cấu hình TLS/proxy. | Có thể bắt đầu worker, health polling hoặc kết nối persistent. |
| Message consumer | Tạo bean và đọc cấu hình subscription. | Kết nối broker, đăng ký consumer và bắt đầu nhận message. |
| Scheduled worker | Tạo scheduler hoặc lưu cấu hình lịch. | Đăng ký task định kỳ và bắt đầu chạy. |
| Cache loader | Tạo cache object và chính sách eviction. | Nạp dữ liệu từ database hoặc service. |

Nếu chạy thử mà ứng dụng vẫn cần database hoặc HTTP service ngay trong giai đoạn `onRefresh`, hãy xem lại bean nào thực hiện lời gọi đó. Có thể dependency đang kết nối đồng bộ trong constructor, `@PostConstruct`, `afterPropertiesSet()` hoặc một factory method.

Không phải mọi kết nối sớm đều sai. Một số ứng dụng cần kiểm tra credential, schema hoặc remote configuration trước khi tiếp tục. Mục tiêu là xác định kết nối nào thực sự cần thiết trước khi checkpoint và kết nối nào có thể được trì hoãn tới lifecycle start hoặc giai đoạn phục hồi sau restore.

### 5.1. Ví dụ bean khởi tạo và bean lifecycle

```java
import jakarta.annotation.PostConstruct;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class RemoteWorker implements SmartLifecycle {

    private volatile boolean running;

    public RemoteWorker() {
        // Constructor nên giữ việc khởi tạo ở mức cấu trúc.
    }

    @PostConstruct
    void initialize() {
        // Nếu đặt remote call đồng bộ ở đây, nó sẽ chạy trước onRefresh exit.
        System.out.println("RemoteWorker initialized");
    }

    @Override
    public void start() {
        // Với spring.context.exit=onRefresh, phương thức này chưa được gọi.
        // Có thể kết nối broker hoặc bắt đầu worker ở đây nếu đúng lifecycle.
        running = true;
        System.out.println("RemoteWorker started");
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
```

Khi chạy với `-Dspring.context.exit=onRefresh`, log `RemoteWorker initialized` có thể xuất hiện, nhưng `RemoteWorker started` sẽ không xuất hiện vì lifecycle start chưa diễn ra. Nếu đặt lời gọi broker trong `initialize()`, phép thử sẽ giúp phát hiện việc kết nối diễn ra quá sớm. Nếu chuyển thao tác sang `start()`, cần xác nhận thiết kế đó phù hợp với yêu cầu của ứng dụng và thời điểm CRaC checkpoint.

Đoạn code trên chỉ minh họa sự khác nhau giữa init callback và `SmartLifecycle.start()`. Một `SmartLifecycle` thực tế cần triển khai đầy đủ stop callback, timeout, dependency và xử lý lỗi theo nhu cầu ứng dụng.

### 5.2. Kiểm tra log và dấu vết kết nối

Khi chạy phép thử, nên quan sát:

- Log từ constructor, `@PostConstruct`, `InitializingBean` và factory method.
- Log hoặc metric từ connection pool, HTTP client và driver.
- Log phía database, broker hoặc dịch vụ HTTP về kết nối mới.
- Bean nào gọi remote service trong quá trình tạo ApplicationContext.
- Những tác vụ bất đồng bộ nào được khởi chạy từ init callback.

Nếu một bean khởi chạy thread nền rồi thread đó tự kết nối remote service, kết quả có thể không ổn định: `Runtime.halt(0)` có thể kết thúc tiến trình trước khi tác vụ bất đồng bộ hoàn thành. Để kiểm tra chính xác, hãy instrument nơi tạo task hoặc nơi mở connection, dùng test double/local service khi phù hợp và tránh dựa vào việc chờ log xuất hiện trong một khoảng thời gian ngắn.

## 6. Quy trình thực hành với Spring Boot

Có thể thực hiện phép thử theo trình tự sau:

1. Xác nhận ứng dụng dùng Spring Framework 6.1 trở lên và đang dùng `DefaultLifecycleProcessor` mặc định.
2. Tạo một cấu hình thử riêng, tránh dùng secret hoặc dữ liệu production không cần thiết.
3. Khởi chạy JAR với `-Dspring.context.exit=onRefresh`.
4. Thu log khởi tạo bean và theo dõi connection attempt tới database, broker, cache hoặc HTTP service.
5. Xác định lời gọi nào diễn ra trước `LifecycleProcessor.onRefresh`.
6. Phân loại dependency nào cần có trước checkpoint và dependency nào chỉ cần khi worker bắt đầu chạy.
7. Nếu phù hợp, chuyển công việc mở kết nối hoặc bắt đầu worker sang `SmartLifecycle.start()` hay một giai đoạn lifecycle có chủ đích.
8. Chạy lại phép thử để xác nhận giai đoạn khởi tạo không còn thực hiện kết nối không cần thiết.
9. Chạy ứng dụng ở chế độ bình thường để xác nhận lifecycle start, web server và chức năng nghiệp vụ vẫn hoạt động.

Kết quả mong đợi của phép thử là tiến trình thoát tại `onRefresh`, trước khi lifecycle start. Nếu process kết thúc với exit code `0`, hãy kết hợp log và dấu vết kết nối để xác định những gì đã chạy; không dùng riêng exit code làm tiêu chí xác nhận toàn bộ startup thành công.

## 7. So sánh `spring.context.exit` và `spring.context.checkpoint`

Hai property này dùng cùng lifecycle phase nhưng phục vụ hai mục tiêu khác nhau.

| Tiêu chí | `spring.context.exit=onRefresh` | `spring.context.checkpoint=onRefresh` |
|---|---|---|
| Mục đích | Thử giai đoạn khởi tạo rồi kết thúc JVM. | Tạo checkpoint tự động tại giai đoạn khởi tạo. |
| Có tạo checkpoint image? | Không. | Có, nếu runtime thực hiện checkpoint thành công. |
| Cần CRaC-enabled JVM? | Không. | Có. |
| Cần `org.crac:crac`? | Không. | Có. |
| Cần Linux/CRaC environment? | Không yêu cầu cho phép thử exit. | Cần môi trường checkpoint/restore được hỗ trợ. |
| Lifecycle start đã chạy? | Chưa. | Chưa tại thời điểm checkpoint được tạo. Sau restore, quá trình startup tiếp tục. |
| Cách dùng chính | Phát hiện công việc hoặc kết nối xảy ra quá sớm. | Fast-forward startup tới giai đoạn context đã khởi tạo để tạo checkpoint. |

Hai property không nên bật cùng lúc trong một lần chạy thử. Trong implementation mặc định, `checkpoint` được xử lý trước; khi checkpoint/restore trả về, `exit` vẫn có thể được kiểm tra và kết thúc JVM. Hãy chọn đúng một chế độ theo mục tiêu thử nghiệm.

## 8. Những giới hạn cần hiểu

`spring.context.exit=onRefresh` chỉ mô phỏng điểm kết thúc của quy trình startup tại lifecycle phase tương ứng. Nó không thay thế kiểm thử CRaC thực tế.

- Không xác nhận JVM có thể tạo checkpoint image.
- Không xác nhận CRIU hoặc kernel có thể restore tiến trình.
- Không chạy `Resource.beforeCheckpoint(...)` hay `Resource.afterRestore(...)` như một chu kỳ checkpoint/restore.
- Không kiểm tra các `SmartLifecycle.start()` callback vì chúng chưa được gọi.
- Không kiểm tra `ApplicationRunner`, `CommandLineRunner`, `ApplicationReadyEvent` hoặc request thật tới web server.
- Không đảm bảo các tác vụ bất đồng bộ đã hoàn tất trước khi JVM bị halt.
- Không chạy cleanup callback thông thường của Spring khi kết thúc.
- Không chứng minh cache, connection pool hoặc resource sẽ hoạt động sau restore.

Nếu cần xác nhận khả năng checkpoint/restore, hãy chạy với `spring.context.checkpoint=onRefresh` trên môi trường CRaC tương thích, sau đó kiểm thử các dependency và hành vi sau restore. Phép thử exit là bước chẩn đoán sớm để hiểu ranh giới khởi tạo, không phải bằng chứng cho restore thành công.

## 9. Các lỗi cấu hình thường gặp

**Đặt property trong `application.yml` nhưng ứng dụng vẫn chạy bình thường.** Property được đọc qua `SpringProperties`, không phải Spring Boot `Environment`. Hãy truyền `-Dspring.context.exit=onRefresh` lúc khởi chạy JVM hoặc dùng `spring.properties` theo cơ chế của Spring Framework.

**Dùng sai tên property.** `spring.context.exit` là property kết thúc JVM. `spring.context.checkpoint` là property yêu cầu CRaC checkpoint. Hai tên không thay thế nhau.

**Dùng giá trị không đúng.** Giá trị được nhận diện là `onRefresh`; giá trị khác không kích hoạt hành vi này. So sánh không phân biệt chữ hoa/chữ thường.

**Dùng Spring Framework cũ hơn 6.1.** Property này chưa có trong các phiên bản trước. Kiểm tra dependency thực tế thay vì chỉ kiểm tra source code của ứng dụng.

**Thay `DefaultLifecycleProcessor` bằng implementation tùy chỉnh.** Property được xử lý bởi implementation mặc định. Nếu ứng dụng cung cấp `LifecycleProcessor` khác, không nên kỳ vọng custom processor tự hiểu property này.

**Cho rằng đây là graceful shutdown.** Implementation gọi `Runtime.halt(0)`. Không dựa vào `@PreDestroy`, `ContextClosedEvent` hoặc shutdown hook để giải phóng tài nguyên trong lần chạy thử này.

**Cho rằng exit code 0 nghĩa ứng dụng đã sẵn sàng.** JVM kết thúc trước lifecycle start, runners và readiness. Cần diễn giải exit code trong đúng mục tiêu của phép thử.

## 10. Checklist khi thử giai đoạn khởi tạo

- [ ] Xác nhận Spring Framework 6.1+ trong dependency graph.
- [ ] Xác nhận đang sử dụng `DefaultLifecycleProcessor` mặc định.
- [ ] Truyền `-Dspring.context.exit=onRefresh` trước khi JVM khởi động.
- [ ] Dùng cấu hình thử nghiệm an toàn và tránh side effect production.
- [ ] Ghi nhận constructor, `@PostConstruct` và `afterPropertiesSet()` của non-lazy singleton.
- [ ] Kiểm tra kết nối database, broker, HTTP và remote configuration được mở ở giai đoạn nào.
- [ ] Phân biệt bean initialization với `Lifecycle`/`SmartLifecycle.start()`.
- [ ] Không kỳ vọng `ContextRefreshedEvent`, runners hoặc `ApplicationReadyEvent` được phát.
- [ ] Không dựa vào shutdown callback để dọn dẹp vì JVM bị halt tức thời.
- [ ] Xác định và instrument các tác vụ bất đồng bộ được khởi chạy trong init callback.
- [ ] Không dùng riêng exit code 0 làm bằng chứng startup hoàn chỉnh.
- [ ] Chạy lại ứng dụng bình thường để xác nhận lifecycle và web server hoạt động.
- [ ] Dùng `spring.context.checkpoint=onRefresh` trên môi trường CRaC riêng khi cần xác minh checkpoint thật.

## 11. Thuật ngữ cần nhớ

- **`spring.context.exit`:** Spring Framework property điều khiển việc kết thúc JVM tại một lifecycle phase xác định.
- **`onRefresh`:** giá trị yêu cầu thực hiện hành vi tại `LifecycleProcessor.onRefresh()`.
- **`DefaultLifecycleProcessor`:** implementation mặc định điều phối các bean `Lifecycle` và `SmartLifecycle` trong quá trình start/stop.
- **Bean initialization:** giai đoạn tạo bean, inject dependency và chạy các init callback.
- **Lifecycle start:** giai đoạn Spring gọi `start()` cho các bean lifecycle đủ điều kiện.
- **`SmartLifecycle`:** hợp đồng lifecycle có thêm phase, auto-start và callback dừng bất đồng bộ.
- **`ContextRefreshedEvent`:** event được phát sau giai đoạn refresh/lifecycle processor.
- **`Runtime.halt(0)`:** kết thúc JVM ngay lập tức với mã thoát 0 mà không chạy shutdown hooks.
- **`SpringProperties`:** cơ chế property cấp thấp của Spring Framework, đọc `spring.properties` và JVM system properties.
- **`spring.context.checkpoint`:** property khác dùng để yêu cầu checkpoint tự động tại `onRefresh` khi môi trường CRaC được hỗ trợ.

`spring.context.exit=onRefresh` là cách nhanh để quan sát ranh giới giữa khởi tạo ApplicationContext và khởi động các bean lifecycle trong Spring Boot. Hãy dùng nó để tìm những kết nối hoặc tác vụ từ xa xảy ra quá sớm, hiểu rõ những callback nào đã chạy và những giai đoạn nào chưa tới. Vì JVM bị kết thúc tức thời tại điểm này, hãy đọc kết quả như bằng chứng về giai đoạn khởi tạo, rồi dùng chế độ chạy bình thường và checkpoint CRaC thật để xác minh các giai đoạn tiếp theo.

## Tài liệu tham khảo

- [Spring Framework — JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html): mô tả chính thức `spring.context.exit=onRefresh`, vị trí trong `LifecycleProcessor.onRefresh` và mục đích kiểm tra kết nối từ xa trước khi bean được start.
- [Spring Framework — `DefaultLifecycleProcessor` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): property `EXIT_PROPERTY_NAME`, giá trị `ON_REFRESH_VALUE` và lifecycle processor.
- [Spring Framework — `SpringProperties` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/SpringProperties.html): cách Spring đọc file `spring.properties` và JVM system properties.
