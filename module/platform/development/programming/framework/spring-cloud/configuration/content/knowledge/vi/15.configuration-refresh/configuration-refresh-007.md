# Khóa bị xóa, giá trị rỗng và những trường hợp không cập nhật như dự kiến

Khi cấu hình trong Git hoặc Config Server thay đổi, ứng dụng Spring Boot không phải lúc nào cũng lập tức phản ánh thay đổi đó. Một giá trị mới có thể chưa được client tải, một khóa đã xóa có thể để lộ giá trị từ nguồn ưu tiên thấp hơn, và một chuỗi rỗng không giống với thuộc tính bị xóa. Ngay cả khi `Environment` đã được làm mới, bean đang giữ giá trị cũ vẫn có thể cần được bind lại hoặc tạo lại.

Trong hệ thống Spring Cloud Configuration, cần phân biệt bốn bước: **cập nhật nguồn cấu hình, Config Server đọc revision mới, Config Client nạp lại Environment và bean trong ứng dụng áp dụng giá trị mới**. Nếu một bước chưa hoàn tất, kết quả quan sát được có thể khác mong đợi.

## 1. Bốn trạng thái khác nhau của một thuộc tính

Giả sử ứng dụng dùng khóa `acme.billing.api-key`. Khóa này có thể ở một trong các trạng thái sau:

| Trạng thái | Ví dụ YAML | Ý nghĩa |
| --- | --- | --- |
| Có giá trị | `api-key: abc123` | Property source cung cấp một giá trị cụ thể |
| Chuỗi rỗng | `api-key: ""` | Khóa tồn tại và giá trị là chuỗi có độ dài bằng 0 |
| Null | `api-key: null` hoặc `api-key:` | Giá trị được biểu diễn là null; cách resolver xử lý khác với chuỗi rỗng |
| Không khai báo | Xóa dòng `api-key` khỏi tài liệu | Property source đó không còn cung cấp khóa |

Các trạng thái này không thể dùng thay thế cho nhau. Chuỗi rỗng vẫn là một giá trị có thể ghi đè nguồn thấp hơn. Null thường được Spring property resolver xem như không có giá trị để phân giải, nên nguồn thấp hơn có thể được dùng. Khi xóa hẳn khóa, resolver cũng có thể tìm thấy giá trị cùng tên ở một `PropertySource` có độ ưu tiên thấp hơn.

Ví dụ local có:

```yaml
acme:
  billing:
    api-key: local-placeholder
```

Nếu Config Server có `api-key: ""`, giá trị rỗng từ nguồn remote có thể thắng giá trị local. Nếu Config Server trả null hoặc không còn khai báo khóa, giá trị local có thể xuất hiện trở lại tùy thứ tự nguồn và cách property source biểu diễn giá trị. Vì vậy, xóa khóa remote không nhất thiết làm thuộc tính biến mất hoàn toàn khỏi ứng dụng.

## 2. Chuỗi rỗng không phải là xóa khóa

Trong YAML, nên viết chuỗi rỗng một cách tường minh:

```yaml
acme:
  billing:
    banner: ""
```

Trong file `.properties`, chuỗi rỗng có thể được biểu diễn bằng:

```properties
acme.billing.banner=
```

Giá trị rỗng có thể hữu ích khi muốn chủ động xóa nội dung hiển thị hoặc ghi đè một giá trị mặc định bằng chuỗi rỗng. Nhưng nó cũng có thể gây lỗi nếu ứng dụng yêu cầu giá trị không được rỗng.

Ví dụ:

```java
@ConfigurationProperties(prefix = "acme.billing")
@Validated
public record BillingProperties(
        @NotBlank String banner,
        @NotNull Duration connectTimeout
) {}
```

Với `@NotBlank`, chuỗi rỗng hoặc chỉ có khoảng trắng không hợp lệ. Nếu cấu hình rỗng được bind vào bean và validation chạy, ứng dụng có thể báo lỗi thay vì tiếp tục với một banner trống. Nếu nghiệp vụ cho phép rỗng, hãy dùng kiểu khai báo và validation phù hợp, đồng thời định nghĩa rõ ý nghĩa của trạng thái rỗng.

Không dùng chuỗi rỗng như một quy ước xóa khóa nếu các consumer chưa thống nhất cách xử lý. Một thành phần có thể hiểu `""` là tắt tính năng, thành phần khác có thể coi đó là giá trị hợp lệ nhưng không mong muốn.

## 3. Null, khóa bị xóa và fallback từ nguồn thấp hơn

Spring `Environment` phân giải thuộc tính qua nhiều `PropertySource` theo thứ tự ưu tiên. Khi một nguồn ưu tiên cao không còn cung cấp giá trị, resolver có thể tiếp tục tìm ở nguồn thấp hơn.

Ví dụ có hai nguồn:

```yaml
# Config Server: billing-api-prod.yml
acme:
  billing:
    connect-timeout: 4s
```

```yaml
# Config Client: application.yml
acme:
  billing:
    connect-timeout: 2s
```

Ban đầu, nguồn remote có độ ưu tiên cao hơn và ứng dụng nhận `4s`. Sau khi xóa `connect-timeout` khỏi Git, Config Server không còn cung cấp khóa đó trong property source remote. Nếu local vẫn có `2s`, giá trị local có thể trở thành giá trị được chọn sau lần nạp cấu hình thành công.

Đây là fallback có chủ đích theo thứ tự nguồn, không nhất thiết là dữ liệu remote cũ còn sót lại. Để biết trường hợp nào đang xảy ra, hãy kiểm tra `propertySources` của Config Server và `PropertySource` phía client.

Null cần được kiểm tra cẩn thận. Spring property resolution thông thường không dùng giá trị null trong một property source để ghi đè giá trị ở nguồn thấp hơn; null thường được xem như không cung cấp giá trị. Cách biểu diễn null trong YAML, JSON, backend và phiên bản Config Server có thể ảnh hưởng response, vì vậy hãy kiểm tra JSON `Environment` thực tế thay vì chỉ nhìn nội dung Git.

## 4. Xóa khóa trong Git nhưng ứng dụng vẫn thấy giá trị cũ

Có một số nguyên nhân phổ biến:

1. **Config Server chưa đọc commit mới:** Git working copy chưa fetch revision mới, hoặc `refresh-rate` chưa đến thời điểm cho phép cập nhật.
2. **Client chưa refresh:** Config Server đã trả dữ liệu mới nhưng client vẫn giữ `Environment` cũ.
3. **Nguồn khác còn khai báo khóa:** local file, biến môi trường, system property hoặc một repository trong composite vẫn cung cấp cùng tên khóa.
4. **Bean giữ trạng thái cũ:** `Environment` đã đổi nhưng bean được tạo trước đó chưa được rebind hoặc tạo lại.
5. **Giá trị được cache trong ứng dụng:** code đã đọc thuộc tính một lần rồi lưu vào field, singleton hoặc cache riêng.
6. **Label hoặc profile không đúng:** client đang đọc branch, tag, commit hoặc profile khác với nơi vừa xóa khóa.

Vì vậy, không nên bắt đầu bằng cách restart toàn bộ hệ thống. Hãy xác định thay đổi dừng ở tầng nào: Git, Config Server, Config Client `Environment` hay bean tiêu thụ cấu hình.

## 5. Phân biệt refresh Config Server và refresh Config Client

Hai thao tác thường bị nhầm:

| Thành phần | Việc cần làm | Câu hỏi xác minh |
| --- | --- | --- |
| Git backend của Config Server | Fetch/đọc revision mới theo chính sách Git backend | Response Config Server đã có commit và property source mới chưa? |
| Config Client | Tải lại nguồn cấu hình và cập nhật `Environment` | Client đã nhận thay đổi hoặc danh sách khóa thay đổi chưa? |
| Bean trong ứng dụng | Rebind hoặc tạo lại bean cần cấu hình mới | Code đang sử dụng giá trị mới hay vẫn giữ object cũ? |

Một lần gọi `/actuator/refresh` ở client không tự bảo đảm Config Server đã fetch commit mới từ Git. Nếu Config Server vẫn trả revision cũ, client có refresh thành công cũng chỉ nhận lại dữ liệu cũ. Ngược lại, Git và Config Server đã cập nhật không có nghĩa mọi client đang chạy tự động nhận thay đổi.

Khi dùng Git backend, kiểm tra thêm `spring.cloud.config.server.git.refresh-rate`. Giá trị này điều tiết khoảng thời gian tối thiểu giữa các lần cập nhật remote khi repository được truy cập; nó không phải lịch fetch nền độc lập. Cần bảo đảm request kiểm tra sau commit thực sự đi qua thời điểm fetch phù hợp hoặc dùng cơ chế cập nhật được thiết kế cho triển khai.

## 6. Làm mới Environment ở Config Client

Với Spring Cloud Context và Config Client, endpoint Actuator `/actuator/refresh` có thể yêu cầu ứng dụng làm mới `Environment`. Sau khi bật endpoint, có thể gọi:

```bash
curl -X POST http://localhost:8081/actuator/refresh
```

Cấu hình phơi bày endpoint trong môi trường được bảo vệ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
```

Endpoint refresh thường trả về danh sách khóa thay đổi được phát hiện. Cần xem kết quả và log của đúng phiên bản để biết thay đổi đã được nhận. Danh sách rỗng có thể có nghĩa các giá trị so sánh được không thay đổi; nó không chứng minh mọi bean trong ứng dụng đã được tạo lại.

Endpoint này có quyền tác động tới runtime configuration. Chỉ phơi bày trong mạng tin cậy, yêu cầu xác thực và phân quyền, giới hạn truy cập, đồng thời tránh để người dùng không được phép kích hoạt refresh.

## 7. Bean nào nhận được thay đổi?

Sau khi `Environment` được làm mới, khả năng bean phản ánh giá trị mới phụ thuộc cách bean được tạo và giữ trạng thái.

### `@ConfigurationProperties`

Các bean `@ConfigurationProperties` được Spring Cloud hỗ trợ rebind khi refresh event xảy ra. Tuy nhiên, cần kiểm tra kiểu bean, cách đăng ký và cơ chế binding đang dùng. Bean mutable có setter và bean immutable/constructor-bound có vòng đời khác nhau; đừng mặc định mọi object đều được cập nhật giống nhau khi một khóa bị xóa.

### `@RefreshScope`

Với bean cần được tạo lại để áp dụng cấu hình mới, có thể dùng `@RefreshScope` nếu loại bean và cấu hình Spring Cloud hỗ trợ:

```java
@Component
@RefreshScope
public class BillingEndpointClient {
    private final URI endpoint;

    public BillingEndpointClient(
            @Value("${acme.billing.endpoint}") URI endpoint) {
        this.endpoint = endpoint;
    }

    public URI endpoint() {
        return endpoint;
    }
}
```

Refresh scope dùng proxy và cache target bean. Khi refresh, target cũ bị loại khỏi cache; target mới thường được tạo khi proxy được gọi tiếp theo. Vì vậy, thời điểm refresh scope invalidation và thời điểm bean thực sự được khởi tạo lại có thể khác nhau.

Không phải mọi bean đều có thể làm mới an toàn. Một số tài nguyên như connection pool, thread pool hoặc client có lifecycle phức tạp cần chiến lược thay thế riêng. Kiểm tra danh sách loại bean không thể refresh trong phiên bản Spring Cloud đang dùng và thử nghiệm hành vi đóng/mở tài nguyên.

### `@Value` và giá trị được cache trong code

`@Value` được inject khi bean được tạo. Nếu bean không thuộc refresh scope, trường đã inject có thể tiếp tục giữ giá trị cũ dù `Environment` đã thay đổi. Tương tự, code gọi `environment.getProperty(...)` rồi lưu kết quả vào một field sẽ không tự cập nhật field đó. Cần dùng cơ chế rebind/tạo lại phù hợp hoặc đọc giá trị động từ một thành phần có lifecycle được kiểm soát.

## 8. Vì sao xóa khóa có thể không đặt lại giá trị mặc định?

Giả sử bean có giá trị khởi tạo:

```java
@Component
public class BillingSettings {
    private Duration timeout = Duration.ofSeconds(2);

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public Duration getTimeout() {
        return timeout;
    }
}
```

Lần bind đầu tiên, remote đặt `timeout: 5s`. Sau đó khóa bị xóa. Nếu quá trình cập nhật chỉ không còn gọi setter cho thuộc tính đó, object hiện hữu có thể giữ lại giá trị đã được gán trước đó. Kết quả cụ thể phụ thuộc binder, kiểu bean, cách rebind và phiên bản; không nên dựa vào giả định rằng mọi trường hợp xóa khóa đều tự chạy lại initializer.

Để có hành vi xác định, hãy:

- Khai báo fallback rõ ràng ở nguồn cấu hình thấp hơn nếu muốn quay về giá trị đó.
- Dùng `@ConfigurationProperties` với default/constructor phù hợp và kiểm tra rebind sau khi xóa khóa.
- Tạo lại bean qua refresh scope khi bean cần khởi tạo lại từ `Environment`.
- Viết kiểm thử xác nhận giá trị sau khi key bị xóa, không chỉ sau khi key đổi từ giá trị A sang B.
- Nếu thuộc tính bắt buộc, dùng validation để từ chối trạng thái thiếu thay vì giữ giá trị cũ âm thầm.

## 9. Spring Cloud Bus và refresh nhiều instance

`/actuator/refresh` thường làm mới một instance. Trong hệ thống nhiều instance, có thể dùng Spring Cloud Bus để phát sự kiện refresh tới các ứng dụng liên quan:

```bash
curl -X POST http://billing-api-1:8081/actuator/busrefresh
```

Bus yêu cầu broker và dependency tương ứng, chẳng hạn RabbitMQ hoặc Kafka, cùng cấu hình kết nối. Endpoint `busrefresh` phát sự kiện qua message broker; các instance nhận sự kiện sẽ thực hiện quá trình refresh cục bộ và tải lại cấu hình theo cơ chế của chúng.

Bus không gửi toàn bộ giá trị cấu hình mới như một payload thay thế Config Server. Nó chủ yếu phân phối tín hiệu refresh; từng client vẫn phải liên hệ nguồn cấu hình và cập nhật `Environment` của mình. Nếu Config Server hoặc Git backend vẫn đang trả revision cũ, mọi client có thể refresh nhưng vẫn nhận dữ liệu cũ.

Khi dùng Bus, cần bảo vệ broker, xác thực endpoint, giới hạn destination và quan sát trạng thái từng instance. Không nên giả định một HTTP 200 từ instance gửi sự kiện đồng nghĩa mọi instance đã xử lý thành công.

## 10. Kiểm tra theo từng lớp khi giá trị không đổi

Hãy thực hiện theo trình tự sau:

1. **Git:** xác nhận commit đã được push lên đúng branch/tag và chứa thay đổi hoặc thao tác xóa khóa.
2. **Config Server:** gọi `/{application}/{profile}/{label}` trực tiếp; kiểm tra `version`, `profiles`, `label` và `propertySources`.
3. **Property source:** xác định khóa còn xuất hiện ở repository nào, đặc biệt nếu dùng composite repository.
4. **Config Client:** gọi refresh trên một instance thử nghiệm; kiểm tra kết quả trả về và log Config Data/ContextRefresher.
5. **Environment:** kiểm tra nguồn cung cấp khóa và giá trị cuối cùng bằng Actuator `env` đã được bảo vệ.
6. **Bean:** kiểm tra `@ConfigurationProperties`, `@Value`, refresh scope và các cache nội bộ.
7. **Nhiều instance:** so sánh revision và trạng thái refresh giữa các instance; nếu dùng Bus, xác minh từng consumer đã nhận sự kiện.

Ví dụ, Config Server response đã không còn `acme.billing.banner`, nhưng `/actuator/env` ở client vẫn cho thấy giá trị đó. Nguyên nhân có thể là local file hoặc environment variable còn cung cấp khóa. Nếu `Environment` đã không còn khóa nhưng API nghiệp vụ vẫn trả banner cũ, hãy kiểm tra bean hoặc cache đang giữ trạng thái.

## 11. Ma trận kiểm thử cho giá trị và khóa

Nên kiểm tra tối thiểu các trường hợp sau trên một ứng dụng staging:

| Thay đổi ở Config Server | Kết quả cần xác minh trong Environment | Kết quả cần xác minh trong bean |
| --- | --- | --- |
| `timeout: 2s` thành `timeout: 5s` | Giá trị mới có mặt và nguồn đúng | Bean nhận `5s` sau refresh |
| Xóa `timeout` khỏi remote, local có `2s` | Giá trị local có thể xuất hiện lại | Bean nhận fallback theo thiết kế |
| Xóa `timeout` khỏi mọi nguồn | Khóa không còn hoặc trả null/default theo cách truy vấn | Validation hoặc default được áp dụng rõ ràng |
| Đặt `timeout: ""` | Giá trị là chuỗi rỗng; conversion có thể thất bại với `Duration` | Bean báo lỗi hoặc xử lý theo quy ước |
| Đặt `timeout: null` | Xác minh null có được xem như không cung cấp giá trị | Kiểm tra fallback/validation |
| Thay đổi khóa nhưng không refresh client | Config Server mới, client có thể còn giá trị cũ | Bean chưa đổi |
| Refresh Environment nhưng bean không refresh | Environment mới | Bean/cache có thể vẫn giữ giá trị cũ |
| Dùng Bus với nhiều instance | Mỗi client cần nhận được revision mới | Kiểm tra kết quả trên từng instance |

Lưu lại request, response metadata, property source, thời gian refresh và kết quả bean. Không dùng bí mật thật trong test và không đưa giá trị nhạy cảm vào log.

## 12. Những trường hợp cần restart thay vì refresh

Refresh không thay thế mọi loại thay đổi cấu hình. Các thuộc tính ảnh hưởng đến cấu trúc khởi động, tạo bean hoặc thành phần không hỗ trợ refresh có thể cần restart hoặc rollout mới.

Ví dụ:

- Thay đổi cổng server, cấu trúc listener hoặc các thuộc tính chỉ được đọc khi startup.
- Thay đổi cấu hình tạo connection pool hoặc tài nguyên không thể đóng/mở an toàn khi refresh.
- Thay đổi profile active sau khi ứng dụng đã khởi động; profile activation không đơn giản tương đương với nạp lại một giá trị thông thường.
- Thay đổi thuộc tính mà thư viện bên thứ ba chỉ đọc một lần lúc tạo object và không có API cập nhật.

Hãy phân loại thuộc tính trước khi chọn refresh. Với thuộc tính cần restart, pipeline nên triển khai lại instance theo rolling update, kiểm tra readiness và bảo đảm instance mới đã nhận đúng revision trước khi đưa vào phục vụ.

## 13. Checklist xử lý khóa bị xóa hoặc giá trị rỗng

- [ ] Xác nhận thay đổi đã có trong Git commit đúng label.
- [ ] Xác nhận Config Server trả về revision mới và property source không còn khóa cần xóa.
- [ ] Kiểm tra các nguồn thấp hơn có cung cấp fallback cùng khóa hay không.
- [ ] Phân biệt chuỗi rỗng, null và không khai báo.
- [ ] Kiểm tra Config Client đã refresh `Environment` hay chưa.
- [ ] Kiểm tra bean đã rebind hoặc refresh scope target đã được tạo lại chưa.
- [ ] Kiểm tra `@Value`, cache và trạng thái được giữ trong singleton.
- [ ] Dùng validation cho thuộc tính bắt buộc và default rõ ràng cho thuộc tính tùy chọn.
- [ ] Nếu dùng Bus, xác minh từng instance nhận sự kiện và tải đúng revision.
- [ ] Restart/rollout đối với thuộc tính không hỗ trợ refresh.
- [ ] Bảo vệ endpoint refresh, Actuator, broker và log.

Khi một khóa bị xóa hoặc được đặt thành rỗng, điều quan trọng là biết nó còn tồn tại ở nguồn nào và bean nào đang tiêu thụ giá trị đó. Kiểm tra tuần tự Git, Config Server, Config Client `Environment` và bean runtime sẽ giúp phân biệt fallback hợp lệ, refresh chưa hoàn tất và trạng thái cũ bị giữ lại, từ đó chọn đúng cách xử lý thay vì thay đổi cấu hình một cách thử-sai.
