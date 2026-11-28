# Giới hạn làm mới trong Spring AOT và native image

Spring Cloud Config giúp ứng dụng lấy cấu hình tập trung khi khởi động và trong một số mô hình có thể làm mới cấu hình khi ứng dụng đang chạy. `@RefreshScope`, refresh endpoint và Spring Cloud Bus thường được dùng để cập nhật giá trị mà không cần restart toàn bộ tiến trình. Tuy nhiên, **cơ chế refresh động của Spring Cloud Context không được hỗ trợ khi ứng dụng dùng Spring AOT transformations hoặc native image theo mô hình được tài liệu Spring Cloud quy định**.

Điểm cần phân biệt là nạp cấu hình ban đầu và thay đổi cấu hình sau khi ứng dụng đã khởi động. Một ứng dụng AOT/native vẫn có thể cần lấy cấu hình từ Config Server trong giai đoạn khởi động, tùy phiên bản và khả năng tương thích của các thành phần. Nhưng không nên thiết kế ứng dụng dựa trên việc thay đổi động bean graph, rebind hoặc tái tạo bean bằng `@RefreshScope` sau khi đã khởi động trong môi trường AOT/native.

## 1. AOT và native image thay đổi mô hình khởi chạy như thế nào?

Trong ứng dụng Spring Boot JVM thông thường, nhiều hoạt động framework được thực hiện lúc runtime. Spring có thể quét classpath, xử lý annotation, tạo bean definition, thiết lập proxy và khởi tạo bean trong quá trình chạy ứng dụng.

Với **Ahead-of-Time (AOT) processing**, Spring phân tích ứng dụng ở build time và tạo mã hoặc metadata phục vụ quá trình khởi động. Mục tiêu là giảm công việc runtime, tối ưu startup và hỗ trợ native compilation.

Với **GraalVM Native Image**, ứng dụng được biên dịch thành executable native. Quá trình build phân tích những lớp, phương thức, reflection, proxy và tài nguyên có thể cần thiết. Những hành vi động không được khai báo hoặc không thể dự đoán tại build time có thể không khả dụng như trên JVM thông thường.

| Mô hình | Đặc điểm chính | Tác động tới cấu hình |
| --- | --- | --- |
| Spring Boot JVM thông thường | Nhiều thao tác framework diễn ra ở runtime | Có thể dùng các cơ chế refresh được Spring Cloud hỗ trợ |
| Spring AOT trên JVM | Một phần cấu hình và mã khởi tạo được chuẩn bị ở build time | Cần tuân theo giới hạn AOT của framework và thư viện |
| Native image | Executable được tạo ở build time theo phân tích closed-world | Không thể mặc định mọi thay đổi bean/runtime động đều khả dụng |

Native image không chỉ là một cách đóng gói JAR nhanh hơn. Nó thay đổi những gì runtime có thể khám phá và khởi tạo. Vì vậy, các tính năng dựa vào thay đổi context hoặc bean definition sau khi build cần được kiểm tra riêng.

## 2. Vì sao refresh động bị giới hạn?

Spring Cloud Context cung cấp `ContextRefresher` và `@RefreshScope` để cập nhật cấu hình trong một ứng dụng đang chạy. Với ứng dụng JVM thông thường, refresh có thể làm mới `Environment`, phát sự kiện và làm mới target của các bean thuộc refresh scope.

`@RefreshScope` thường hoạt động thông qua scoped proxy và cache target bean. Khi refresh xảy ra, target hiện tại có thể bị loại khỏi cache; lần gọi tiếp theo tạo target mới và đọc giá trị cấu hình hiện tại. Cơ chế này phụ thuộc vào lifecycle và khả năng quản lý bean động ở runtime.

Trong AOT/native, Spring đã phân tích và chuẩn bị cấu trúc ứng dụng trước khi executable chạy. Thay đổi động cấu trúc bean hoặc thực hiện quy trình context refresh tổng quát không nằm trong mô hình được hỗ trợ. Vì vậy, tài liệu Spring Cloud yêu cầu tắt refresh scope khi dùng Spring AOT transformations bằng thuộc tính:

```properties
spring.cloud.refresh.enabled=false
```

Hoặc trong YAML:

```yaml
spring:
  cloud:
    refresh:
      enabled: false
```

Đặt thuộc tính này trong cấu hình được nạp khi khởi động hoặc trong cấu hình build/deployment phù hợp. Hãy kiểm tra phiên bản Spring Cloud đang dùng để xác nhận chính xác các tính năng bị vô hiệu hóa. Không nên giả định chỉ cần biên dịch thành native image là `@RefreshScope` sẽ tiếp tục hoạt động như trên JVM.

## 3. Tách nạp cấu hình ban đầu khỏi refresh sau khởi động

Config Client có thể lấy cấu hình từ Config Server trong giai đoạn Config Data khi ứng dụng khởi động:

```yaml
spring:
  application:
    name: billing-api
  config:
    import: "configserver:https://config-server.internal:8888"
  cloud:
    refresh:
      enabled: false
```

Ví dụ này thể hiện hai việc độc lập:

- `spring.config.import` khai báo nguồn cấu hình cần nạp trong quá trình khởi động.
- `spring.cloud.refresh.enabled=false` tắt cơ chế refresh scope theo giới hạn AOT.

Nếu Config Server không khả dụng trong lúc khởi động, ứng dụng vẫn chịu chính sách import đã khai báo. Import bắt buộc sẽ làm startup thất bại khi không nạp được nguồn; tiền tố `optional:` cho phép tiếp tục với các nguồn còn lại nếu fallback an toàn.

Không nên hiểu việc tắt refresh scope là tắt toàn bộ Config Client hoặc không thể đọc cấu hình từ xa lúc startup. Cần kiểm tra tính tương thích của đúng Spring Boot, Spring Cloud release train và cách đóng gói native image đang triển khai.

## 4. Những tính năng cần đánh giá lại trong AOT/native

| Tính năng | JVM thông thường | AOT/native |
| --- | --- | --- |
| Đọc cấu hình local lúc startup | Được hỗ trợ | Được hỗ trợ theo Config Data/AOT của phiên bản |
| Lấy cấu hình Config Server lúc startup | Được hỗ trợ | Phụ thuộc hỗ trợ của phiên bản và dependency; cần kiểm thử native executable |
| `@RefreshScope` để tạo lại target sau refresh | Có thể sử dụng khi bean và phiên bản hỗ trợ | Không được hỗ trợ với Spring AOT transformations; cần tắt refresh scope |
| Làm mới context/bean graph tổng quát | Có giới hạn theo loại bean và framework | Không được giả định khả dụng sau AOT transformation |
| Spring Cloud Bus phát sự kiện refresh | Có thể phát và xử lý sự kiện | Sự kiện có thể được truyền, nhưng không làm cho refresh động trở thành tính năng được hỗ trợ trong AOT/native |
| Restart/rollout instance | Được hỗ trợ | Là cách cập nhật cấu hình runtime phù hợp và dễ dự đoán |

Bảng này là hướng dẫn kiến trúc. Hỗ trợ chi tiết của Config Client, endpoint, AOT processing và native runtime thay đổi theo phiên bản. Hãy dùng ma trận tương thích và tài liệu của release train cụ thể trước khi chốt cấu hình build.

## 5. Vì sao Spring Cloud Bus không giải quyết được giới hạn này?

Spring Cloud Bus truyền sự kiện qua broker như RabbitMQ hoặc Kafka. Một sự kiện `RefreshRemoteApplicationEvent` có thể báo cho các instance rằng cần kiểm tra và làm mới cấu hình.

Trong ứng dụng JVM thông thường, client nhận sự kiện có thể chạy quy trình refresh được hỗ trợ. Nhưng Bus chỉ giải quyết **phân phối tín hiệu**; nó không thay đổi khả năng runtime của ứng dụng nhận sự kiện. Nếu refresh scope và context refresh không được hỗ trợ trong AOT/native, việc nhận được sự kiện Bus không làm cho bean có thể được tái tạo động.

Với ứng dụng AOT/native, nên dùng sự kiện hoặc pipeline để khởi động quy trình rollout instance mới thay vì kỳ vọng `busrefresh` sẽ thay đổi bean hiện hữu. Nếu vẫn bật Bus cho mục đích khác, cần tách rõ loại sự kiện được hỗ trợ với refresh cấu hình và không quảng bá endpoint như một cơ chế cập nhật runtime cho native executable.

## 6. Thiết kế ứng dụng AOT/native theo cấu hình bất biến trong vòng đời instance

Một mô hình dễ vận hành là coi cấu hình được đọc ở startup là cấu hình cố định trong suốt vòng đời instance. Khi cần thay đổi, pipeline tạo instance mới với cùng phiên bản executable nhưng nhận revision cấu hình mới, sau đó thay instance cũ theo rolling deployment.

Ví dụ, Config Server lưu:

```yaml
acme:
  billing:
    endpoint: https://billing-v2.internal.example
    connect-timeout: 4s
    retry:
      max-attempts: 5
```

Khi cần thay `connect-timeout` từ `4s` thành `6s`:

1. Review và merge thay đổi vào Git repository cấu hình.
2. Chọn branch, tag hoặc commit label rõ ràng cho lần rollout.
3. Khởi động instance AOT/native mới; Config Client nạp cấu hình trong startup.
4. Kiểm tra metadata application, profile, label và Git revision, sau đó kiểm tra giá trị đã bind.
5. Chờ readiness và health check của instance mới thành công.
6. Chuyển traffic sang instance mới rồi loại bỏ instance cũ.

Quy trình này tạo ra dấu vết rõ ràng giữa phiên bản ứng dụng và revision cấu hình. Nó cũng cho phép rollback bằng cách triển khai lại instance với label/revision đã được kiểm chứng trước đó.

## 7. Ví dụ cấu hình và bean không dùng RefreshScope

Đối với ứng dụng native, ưu tiên `@ConfigurationProperties` thông thường để bind cấu hình lúc startup:

```java
@ConfigurationProperties(prefix = "acme.billing")
@Validated
public record BillingProperties(
        @NotNull URI endpoint,
        @NotNull Duration connectTimeout,
        @Min(1) int retryMaxAttempts
) {}
```

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class BillingApplication {
    public static void main(String[] args) {
        SpringApplication.run(BillingApplication.class, args);
    }
}
```

Bean nhận giá trị đã được nạp trước khi context hoàn tất startup. Không đặt `@RefreshScope` lên bean nếu ứng dụng cần tuân thủ giới hạn AOT/native. Nếu cấu hình thay đổi, triển khai instance mới để bind lại toàn bộ cấu hình một cách nhất quán.

Đối với thuộc tính có thể thay đổi thường xuyên mà không muốn restart ứng dụng, cân nhắc tách chúng thành dữ liệu nghiệp vụ được đọc qua một service/API có hợp đồng runtime rõ ràng, thay vì coi chúng là Spring bean configuration cần refresh. Ví dụ, feature flag có thể được đọc từ một dịch vụ flag chuyên biệt với client hỗ trợ native và cache policy được xác định rõ. Cách này cần được thiết kế, bảo mật và kiểm thử độc lập.

## 8. Kiểm tra dependency và cấu hình trước AOT processing

Trước khi build AOT hoặc native image, rà soát các thành phần có liên quan tới refresh:

- Tìm các annotation `@RefreshScope` trên bean và cấu hình.
- Kiểm tra `spring.cloud.refresh.enabled` có được đặt thành `false` trong cấu hình dùng cho AOT hay không.
- Xác nhận không có pipeline hoặc health check phụ thuộc vào `/actuator/refresh` hoặc `/actuator/busrefresh` để cập nhật bean.
- Kiểm tra các dependency Spring Cloud theo đúng release train tương thích.
- Xác định các bean cần runtime proxy, reflection hoặc dynamic registration và kiểm tra chúng có được AOT hỗ trợ không.

Có thể tìm annotation trong mã nguồn bằng lệnh tìm kiếm của dự án, ví dụ:

```bash
rg "@RefreshScope|RefreshScope|ContextRefresher|busrefresh" src
```

Nếu ứng dụng có nhiều module, hãy tìm trong các module thực sự được đóng gói vào executable. Sau khi rà soát, build AOT và native image theo plugin/toolchain của dự án; không suy luận rằng JVM test thành công đồng nghĩa native executable sẽ có cùng hành vi.

## 9. Kiểm thử trên JVM, AOT và native executable

Nên có ma trận kiểm thử riêng vì ba chế độ có đặc tính khác nhau:

| Kiểm thử | JVM thường | AOT JVM | Native image |
| --- | --- | --- | --- |
| Khởi động với cấu hình local | Có | Có | Có |
| Nạp Config Server qua import | Kiểm tra | Kiểm tra | Kiểm tra trực tiếp executable |
| Giá trị `@ConfigurationProperties` ban đầu | Kiểm tra | Kiểm tra | Kiểm tra |
| Refresh endpoint thay đổi Environment | Kiểm tra theo thiết kế | Không dựa vào context refresh | Không dựa vào context refresh |
| `@RefreshScope` tái tạo bean | Kiểm tra trên JVM nếu được hỗ trợ | Không dùng trong AOT transformations | Không dùng trong native theo giới hạn refresh |
| Rollout instance với revision mới | Kiểm tra | Kiểm tra | Kiểm tra |

Quy trình thử nghiệm đề xuất:

1. Build và chạy ứng dụng JVM thông thường để xác nhận cấu hình ban đầu.
2. Bật AOT processing, đặt `spring.cloud.refresh.enabled=false` và build lại.
3. Kiểm tra startup, binding và validation trong AOT mode.
4. Build native executable bằng toolchain tương thích.
5. Chạy native executable với Config Server thật hoặc môi trường kiểm thử tương đương.
6. Thay đổi Git label/revision và khởi động một instance mới để xác nhận cấu hình mới được nạp.
7. Kiểm tra pipeline rollout và rollback thay vì gọi refresh để cập nhật bean của instance cũ.

Kết quả cần lưu gồm phiên bản JDK, Spring Boot, Spring Cloud, native build toolchain, Git revision cấu hình, profile, label và log startup. Không đưa secret vào log hoặc artifact kiểm thử.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| AOT build báo lỗi liên quan refresh scope | Ứng dụng còn bật refresh scope hoặc bean dùng tính năng không hỗ trợ | Đặt `spring.cloud.refresh.enabled=false`, rà soát `@RefreshScope` và build lại |
| Native image chạy nhưng bean không nhận giá trị mới sau refresh | Runtime refresh không được hỗ trợ trong mô hình AOT/native | Dùng restart/rollout để nạp cấu hình mới |
| Bus event đã phát nhưng instance không đổi cấu hình | Event transport thành công không đồng nghĩa bean refresh khả dụng | Thiết kế Bus kích hoạt rollout hoặc xử lý tác vụ được hỗ trợ |
| Config Server có revision mới nhưng instance cũ vẫn giữ giá trị | Instance đã nạp cấu hình ở startup và không refresh runtime | Tạo instance mới với revision mới |
| Native startup không lấy được cấu hình | URI, DNS, TLS, credential hoặc Config Client/version chưa tương thích | Kiểm tra startup log, dependency và khả năng kết nối từ môi trường native |
| Chạy JVM thành công nhưng native lỗi | Khác biệt AOT, reflection, proxy, resource hoặc runtime hint | Kiểm tra native build report và kiểm thử executable thực tế |

## 11. Bảo mật và quản trị thay đổi

Với mô hình restart/rollout, cấu hình mới được nạp trong startup của instance mới. Vì vậy, pipeline cần xác định revision cấu hình được phép dùng và kiểm tra nguồn đó trước khi chuyển traffic.

- Bảo vệ Config Server bằng TLS và xác thực.
- Cấp credential đọc tối thiểu cho Config Client; truyền secret qua secret manager hoặc nền tảng triển khai.
- Gắn Git label/revision vào metadata của release để truy vết.
- Kiểm tra validation và readiness trước khi đưa instance mới vào phục vụ.
- Dùng rolling deployment để giảm gián đoạn; chuẩn bị rollback về revision cấu hình đã biết.
- Không để endpoint refresh hoặc Bus event tạo cảm giác rằng native instance đã cập nhật cấu hình khi thực tế không có cơ chế hỗ trợ.

## 12. Checklist trước khi triển khai AOT/native

- [ ] Xác nhận phiên bản Spring Boot và Spring Cloud hỗ trợ AOT/native theo yêu cầu dự án.
- [ ] Tìm và đánh giá mọi `@RefreshScope`, `ContextRefresher` và endpoint refresh.
- [ ] Đặt `spring.cloud.refresh.enabled=false` cho AOT transformations theo hướng dẫn Spring Cloud.
- [ ] Không dựa vào `/actuator/refresh` hoặc Spring Cloud Bus để tái tạo bean runtime.
- [ ] Xác nhận Config Client có thể nạp cấu hình ban đầu ở startup trong native executable.
- [ ] Dùng `@ConfigurationProperties` và validation cho cấu hình startup.
- [ ] Kiểm thử revision mới bằng cách khởi động instance mới.
- [ ] Thiết lập readiness, rolling deployment và rollback.
- [ ] Ghi nhận application, profile, label, Git revision và phiên bản executable.
- [ ] Bảo vệ credential, endpoint và log cấu hình.

Trong ứng dụng Spring AOT và native image, nên xem cấu hình Spring là đầu vào của một lần khởi động. Config Server vẫn có thể đóng vai trò nguồn cấu hình tập trung ở startup nếu phiên bản và dependency hỗ trợ, nhưng refresh động dựa trên `@RefreshScope` và context refresh không phải chiến lược được hỗ trợ. Tổ chức cập nhật qua instance mới, kiểm tra readiness và rollout có kiểm soát sẽ tạo hành vi dễ dự đoán và có thể truy vết hơn.
