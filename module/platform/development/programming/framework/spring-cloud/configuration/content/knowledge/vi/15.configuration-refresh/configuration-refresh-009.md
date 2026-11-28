# Xử lý cấu hình mới không hợp lệ mà không làm hỏng luồng đang chạy

Spring Cloud Config cho phép thay đổi cấu hình tập trung mà không cần đóng gói lại ứng dụng. Nhưng một thay đổi có cú pháp YAML hợp lệ vẫn có thể chứa giá trị sai: timeout âm, URL không truy cập được, giới hạn retry quá lớn, tên queue không tồn tại hoặc một nhóm thuộc tính mâu thuẫn với nhau. Nếu client nạp và áp dụng ngay cấu hình đó, luồng xử lý đang chạy có thể phát sinh lỗi hoặc một số bean không thể khởi tạo lại.

Muốn cập nhật an toàn, cần coi cấu hình mới là một ứng viên cần được kiểm tra trước khi kích hoạt. Quy trình nên có ba giai đoạn: chuẩn bị ứng viên, xác thực đầy đủ, rồi mới chuyển ứng dụng sang dùng phiên bản mới. Khi ứng viên không hợp lệ, hệ thống tiếp tục dùng cấu hình đã được xác nhận gần nhất và dừng phát tán thay đổi. Với những thành phần không hỗ trợ chuyển đổi nguyên tử, cần có kế hoạch rollback hoặc restart có kiểm soát.

Bài học này tập trung vào cách bảo vệ luồng đang chạy khi cấu hình mới không hợp lệ trong hệ thống Spring Cloud Config. Bạn sẽ phân biệt lỗi cú pháp và lỗi ngữ nghĩa, xác thực thuộc tính bằng Spring Boot, hiểu giới hạn của refresh và <code>@RefreshScope</code>, thiết kế quy trình canary, giữ phiên bản cấu hình tốt gần nhất và xử lý rollback khi cập nhật thất bại.

Sau bài học, bạn có thể:

- Nhận diện cấu hình sai ở mức cú pháp, kiểu dữ liệu, ràng buộc và khả năng vận hành.
- Xác thực cấu hình trước khi hợp nhất hoặc phát hành lên Config Server.
- Dùng <code>@ConfigurationProperties</code> và Bean Validation để kiểm tra thuộc tính.
- Hiểu vì sao refresh không phải giao dịch nguyên tử cho toàn bộ ứng dụng.
- Thiết kế bước kiểm tra ứng viên trước khi chuyển luồng xử lý sang cấu hình mới.
- Triển khai canary, theo dõi kết quả và rollback về phiên bản đã xác nhận.
- Bảo vệ secret và tránh làm lộ giá trị cấu hình trong log khi xử lý lỗi.

## 1. Cấu hình mới hợp lệ về cú pháp vẫn có thể làm hỏng ứng dụng

Config Server có thể đọc YAML thành công và trả HTTP 200, nhưng điều đó chỉ chứng minh server đã tạo được Environment cho request. Nó không chứng minh các giá trị phù hợp với quy tắc nghiệp vụ hoặc tài nguyên thật của client.

Ví dụ cấu hình:

~~~yaml
orders:
  reservation:
    timeout: -5s
    max-attempts: 500
    endpoint: https://inventory.invalid.internal
~~~

YAML trên có cú pháp hợp lệ. Tuy nhiên:

- Timeout âm không có ý nghĩa cho lời gọi mạng.
- 500 lần retry có thể làm tăng tải và kéo dài hàng đợi.
- Hostname có thể không tồn tại hoặc không thể truy cập từ môi trường triển khai.

Cần phân biệt các lớp lỗi:

| Lớp lỗi | Ví dụ | Nơi nên phát hiện |
|---|---|---|
| Cú pháp | YAML sai indent, tab không hợp lệ, dấu nháy chưa đóng | CI/parser trước khi merge |
| Kiểu dữ liệu | <code>timeout: fast</code> trong khi ứng dụng cần <code>Duration</code> | Binder và kiểm thử khởi động |
| Ràng buộc đơn thuộc tính | Timeout bằng 0, số lần retry âm | Bean Validation |
| Ràng buộc liên thuộc tính | <code>min-pool-size</code> lớn hơn <code>max-pool-size</code> | Validator nghiệp vụ |
| Tương thích | Tên thuộc tính đã bị xóa hoặc đổi kiểu ở phiên bản app mới | Kiểm thử theo phiên bản ứng dụng |
| Khả năng vận hành | URL đúng định dạng nhưng DNS hoặc dịch vụ đích không hoạt động | Canary và health/functional check |
| Tác động khi áp dụng | Pool không thể tái tạo, bean mới không khởi tạo được | Kiểm thử refresh và rollout |

Vì vậy, không nên dùng duy nhất HTTP status của Config Server làm tiêu chí chấp nhận cấu hình.

## 2. Quy trình ba giai đoạn: chuẩn bị, xác thực, kích hoạt

Một quy trình an toàn có thể được mô tả như sau:

~~~mermaid
flowchart TD
    A["Tạo thay đổi cấu hình"] --> B["Parse và kiểm tra schema"]
    B --> C{"Cú pháp hợp lệ?"}
    C -->|Không| X["Từ chối thay đổi"]
    C -->|Có| D["Bind vào model cấu hình"]
    D --> E["Validate kiểu, giới hạn và quan hệ"]
    E --> F{"Ứng viên hợp lệ?"}
    F -->|Không| X
    F -->|Có| G["Kiểm thử tích hợp / tài nguyên phụ thuộc"]
    G --> H{"Canary đạt?"}
    H -->|Không| X
    H -->|Có| I["Promote phiên bản cấu hình"]
    I --> J["Refresh theo phạm vi"]
    J --> K["Theo dõi và xác nhận"]
    K --> L{"Luồng ổn định?"}
    L -->|Có| M["Giữ phiên bản mới"]
    L -->|Không| N["Rollback về last-known-good"]
~~~

Ba giai đoạn có ý nghĩa:

1. **Prepare:** tạo candidate từ commit, tag hoặc nguồn cấu hình riêng. Chưa thay đổi cấu hình đang phục vụ traffic production.
2. **Validate:** kiểm tra cú pháp, bind, validation, ràng buộc liên thuộc tính, kết nối phụ thuộc và hành vi trên một instance canary.
3. **Activate:** chỉ sau khi đạt điều kiện mới promote phiên bản và refresh các client theo kế hoạch.

Nếu candidate thất bại ở bất kỳ bước nào, dừng quy trình. Không gửi refresh toàn hệ thống và không đổi label production sang candidate lỗi.

## 3. Phát hiện lỗi trước khi cấu hình tới client

Kiểm tra sớm rẻ hơn nhiều so với phát hiện sau khi các instance đã nạp cấu hình.

### Kiểm tra ở repository

Pipeline CI cho config repository nên thực hiện:

- Parse tất cả YAML/Properties để phát hiện lỗi định dạng.
- Kiểm tra tên file, application, profile và label theo quy ước.
- Kiểm tra khóa bắt buộc và kiểu giá trị.
- Phát hiện khóa không còn được ứng dụng hỗ trợ.
- Quét secret dạng rõ và credential vô tình bị commit.
- So sánh thay đổi với phiên bản trước để nhận diện thuộc tính có phạm vi ảnh hưởng rộng.

Parser chỉ kiểm tra được cấu trúc tài liệu. Nó không biết <code>orders.reservation.timeout</code> phải lớn hơn 0 hay URL phải trỏ tới dịch vụ nào.

### Kiểm tra bằng đúng phiên bản ứng dụng

Dùng artifact hoặc container của phiên bản ứng dụng sẽ chạy để nạp candidate trong môi trường kiểm thử. Việc này phát hiện khác biệt giữa các phiên bản: một khóa có thể hợp lệ với bản app mới nhưng không được bản app cũ nhận diện, hoặc ngược lại.

Một kiểm tra tích hợp nên:

1. Lấy candidate theo đúng application/profile/label.
2. Nạp property source vào một Spring context kiểm thử độc lập.
3. Bind các nhóm <code>@ConfigurationProperties</code>.
4. Chạy Bean Validation và validator nghiệp vụ.
5. Kiểm tra các dependency quan trọng bằng test phù hợp.
6. Chỉ trả PASS khi tất cả điều kiện bắt buộc thành công.

Không khởi động context kiểm thử bằng cách ghi candidate vào Environment production đang chạy. Việc xác thực cần diễn ra trong context riêng hoặc một tiến trình kiểm tra riêng để không làm thay đổi trạng thái phục vụ traffic.

## 4. Dùng @ConfigurationProperties và Bean Validation

Nhóm thuộc tính có cấu trúc nên được gom bằng <code>@ConfigurationProperties</code>. Có thể kết hợp Jakarta Bean Validation để kiểm tra các giá trị cơ bản ngay khi bind.

Ví dụ:

~~~yaml
orders:
  reservation:
    endpoint: https://inventory.internal
    timeout: 2s
    max-attempts: 3
~~~

~~~java
@ConfigurationProperties(prefix = "orders.reservation")
@Validated
public class ReservationProperties {

    @NotNull
    private URI endpoint;

    @NotNull
    private Duration timeout;

    @Min(1)
    @Max(5)
    private int maxAttempts;

    // getters và setters
}
~~~

Các annotation có ý nghĩa:

- <code>@NotNull</code>: giá trị bắt buộc phải tồn tại.
- <code>@Min</code> và <code>@Max</code>: giới hạn miền giá trị cho số lần thử.
- <code>@Validated</code>: kích hoạt validation cho nhóm cấu hình được bind.

<code>@Positive</code> trong Jakarta Bean Validation chủ yếu hỗ trợ các kiểu số; không gắn trực tiếp annotation này lên <code>Duration</code>. Với duration, dùng custom constraint hoặc kiểm tra <code>isZero()</code> và <code>isNegative()</code> trong validator của nhóm cấu hình.

Dự án cần dependency Bean Validation phù hợp, thường là <code>spring-boot-starter-validation</code>, và phải đăng ký properties class bằng <code>@ConfigurationPropertiesScan</code> hoặc <code>@EnableConfigurationProperties</code>.

### Kiểm tra quan hệ giữa nhiều thuộc tính

Có những quy tắc không thể diễn đạt bằng annotation đơn giản:

- <code>min-pool-size</code> phải nhỏ hơn hoặc bằng <code>max-pool-size</code>.
- <code>connect-timeout</code> phải nhỏ hơn <code>read-timeout</code>.
- Nếu <code>enabled=true</code>, endpoint và credential phải được cung cấp.
- Nếu bật retry, tổng thời gian retry phải nằm trong giới hạn SLA.

Có thể viết class-level constraint hoặc validator chuyên biệt. Ví dụ minh họa kiểm tra pool:

~~~java
public void validatePool(int minSize, int maxSize) {
    if (minSize < 1 || maxSize < minSize || maxSize > 100) {
        throw new IllegalArgumentException(
            "Pool size configuration is outside the allowed range"
        );
    }
}
~~~

Thông báo lỗi chỉ nên nêu tên thuộc tính và quy tắc bị vi phạm. Không đưa password, token hoặc nội dung secret vào exception.

### Validation không thay thế kiểm tra tài nguyên thật

Một URL có thể parse thành <code>URI</code> và vẫn không truy cập được. Một tên queue có thể là chuỗi hợp lệ nhưng chưa tồn tại. Vì thế, sau validation cấu trúc cần có test tích hợp hoặc canary kiểm tra dependency quan trọng theo cách an toàn, có timeout và giới hạn tải.

## 5. Không coi refresh là giao dịch nguyên tử

Trong Spring Cloud Config, client có thể nạp lại cấu hình bằng endpoint refresh hoặc nhận refresh event qua Spring Cloud Bus. Tuy nhiên, refresh không phải một transaction bao trùm toàn bộ Environment, mọi bean và mọi instance.

Một số hành vi thường gặp:

- Config Client tải lại property source và cập nhật Environment.
- Spring phát sự kiện thay đổi Environment cho các thành phần liên quan.
- Các bean <code>@ConfigurationProperties</code> có thể được rebind theo cơ chế của Spring Cloud Context.
- Bean trong <code>@RefreshScope</code> bị loại khỏi cache scope; target mới được tạo lại khi có lời gọi tiếp theo.
- Bean không thuộc refresh scope hoặc đã sao chép giá trị sang một object khác có thể vẫn giữ snapshot cũ.

Điều này tạo ra một số giới hạn:

1. Một số bean có thể đã nhận giá trị mới trong khi bean khác chưa được tạo lại.
2. Target của refresh-scoped bean có thể chỉ được khởi tạo khi request tiếp theo tới proxy.
3. Nếu target mới không tạo được vì candidate sai, request đi qua proxy có thể gặp lỗi lúc runtime.
4. Nhiều instance nhận refresh ở các thời điểm khác nhau; không có giao dịch phân tán đảm bảo tất cả cùng đổi tại một thời điểm.
5. Một số tài nguyên như connection pool hoặc HTTP client có thể cần quy trình đóng, tạo và chuyển đổi riêng.

Do đó, gọi <code>/actuator/refresh</code> thành công không chứng minh toàn bộ luồng nghiệp vụ đã chuyển sang cấu hình mới an toàn.

## 6. @RefreshScope có ích nhưng không phải cơ chế giữ cấu hình tốt gần nhất

Ví dụ:

~~~java
@Component
@RefreshScope
public class InventoryGateway {

    private final RestClient restClient;

    public InventoryGateway(ReservationProperties properties) {
        this.restClient = RestClient.builder()
            .baseUrl(properties.getEndpoint().toString())
            .build();
    }

    public String reserve() {
        return restClient.get()
            .uri("/reservations")
            .retrieve()
            .body(String.class);
    }
}
~~~

<code>@RefreshScope</code> đặt bean sau một scoped proxy. Khi refresh scope bị làm mới, target được cache sẽ bị loại bỏ. Lần gọi sau có thể tạo target mới từ cấu hình hiện tại.

Nếu cấu hình mới khiến constructor hoặc quá trình tạo target thất bại, proxy không tự khôi phục target cũ như một rollback giao dịch. Các lời gọi sau có thể tiếp tục lỗi cho tới khi cấu hình được sửa và bean được tạo lại thành công.

Cần phân biệt:

- Refresh scope giúp tạo lại bean khi cấu hình thay đổi.
- Validation giúp phát hiện giá trị không hợp lệ.
- Rollback giúp đưa ứng dụng về một phiên bản cấu hình đã được xác nhận.
- Atomic swap giúp một luồng xử lý chuyển từ snapshot cũ sang snapshot mới tại một điểm có kiểm soát.

Bốn việc này giải quyết các vấn đề khác nhau. Chỉ thêm <code>@RefreshScope</code> không bảo đảm cấu hình sai sẽ bị từ chối mà trạng thái cũ vẫn hoạt động.

## 7. Chuẩn bị candidate trong context riêng

Một cách an toàn là xác thực candidate trong một tiến trình hoặc Spring context độc lập trước khi đưa nó vào production.

Ví dụ về luồng kiểm tra:

~~~text
Config repository / candidate label
        |
        v
Config Server endpoint cho candidate
        |
        v
Validation process / isolated Spring context
        |
        +--> Parse YAML / Properties
        +--> Bind @ConfigurationProperties
        +--> Bean Validation
        +--> Cross-field validation
        +--> Integration checks
        |
        v
PASS / REJECT
~~~

Validation process dùng đúng phiên bản ứng dụng và cùng quy tắc binding với production. Nó không gọi endpoint refresh của instance đang phục vụ traffic.

Có thể dùng một job CI, một container kiểm thử hoặc một instance canary riêng. Cần lưu kết quả kiểm tra cùng candidate ID, commit/label, phiên bản ứng dụng và thời điểm xác thực để có thể truy vết.

Nếu hệ thống có nhiều loại client hoặc phiên bản ứng dụng khác nhau, candidate phải được kiểm tra với mọi nhóm client còn được hỗ trợ. Một cấu hình có thể hợp lệ với service mới nhưng phá service cũ vẫn đang chạy.

## 8. Giữ cấu hình runtime dưới dạng snapshot bất biến

Với các luồng quan trọng, có thể tránh để từng request đọc trực tiếp nhiều property rời rạc. Thay vào đó, gom các giá trị liên quan vào một snapshot bất biến và thay snapshot sau khi candidate được xác thực.

Ví dụ:

~~~java
public record RuntimeReservationPolicy(
        URI endpoint,
        Duration timeout,
        int maxAttempts) {
}
~~~

Một provider giữ snapshot đang hoạt động:

~~~java
@Component
public class ReservationPolicyProvider {

    private final AtomicReference<RuntimeReservationPolicy> active;

    public ReservationPolicyProvider(RuntimeReservationPolicy initial) {
        this.active = new AtomicReference<>(initial);
    }

    public RuntimeReservationPolicy current() {
        return active.get();
    }

    public void activate(RuntimeReservationPolicy candidate) {
        validate(candidate);
        active.set(candidate);
    }

    private void validate(RuntimeReservationPolicy candidate) {
        if (candidate.endpoint() == null
                || candidate.timeout() == null
                || candidate.timeout().isZero()
                || candidate.timeout().isNegative()
                || candidate.maxAttempts() < 1
                || candidate.maxAttempts() > 5) {
            throw new IllegalArgumentException(
                "Invalid reservation policy"
            );
        }
    }
}
~~~

Trong ví dụ, <code>AtomicReference.set</code> thay snapshot bằng một thao tác nguyên tử. Mỗi request đọc một snapshot và dùng nhất quán các giá trị thuộc snapshot đó. Request đã giữ tham chiếu tới snapshot cũ có thể hoàn tất bằng cấu hình cũ; request tiếp theo đọc snapshot mới.

Đây là mẫu thiết kế phía ứng dụng, không phải hành vi tự động mà Spring Cloud Config cung cấp. Phần lấy candidate và chuyển thành <code>RuntimeReservationPolicy</code> phải được thực hiện riêng, sau khi candidate đã được bind và validate trong context an toàn.

Nếu cấu hình gồm nhiều nhóm liên quan, nên gom những giá trị cần chuyển cùng nhau vào một snapshot tổng thể. Nếu cập nhật từng field riêng lẻ, request có thể đọc kết hợp giữa giá trị cũ và mới.

### Chuẩn bị tài nguyên trước khi đổi snapshot

Một số thay đổi cần tạo tài nguyên mới, chẳng hạn connection pool hoặc HTTP client. Quy trình có thể là:

1. Bind candidate vào object mới.
2. Validate tất cả thuộc tính.
3. Tạo tài nguyên mới và kiểm tra kết nối.
4. Nếu bước nào thất bại, đóng tài nguyên candidate và giữ snapshot hiện tại.
5. Nếu tất cả thành công, atomically swap snapshot và resource holder.
6. Cho request đang dùng resource cũ hoàn tất.
7. Đóng resource cũ sau khi không còn request tham chiếu.

Đây là cách chuyển đổi có chuẩn bị. Cần thiết kế quản lý vòng đời resource và concurrency phù hợp với ứng dụng; không đóng pool cũ ngay sau khi đổi tham chiếu nếu request đang chạy vẫn dùng nó.

## 9. Canary trước khi refresh diện rộng

Sau khi candidate vượt qua CI, vẫn nên áp dụng trước cho một instance hoặc một nhóm nhỏ. Canary kiểm tra những yếu tố không thể xác minh hoàn toàn bằng parser và unit test, như DNS, quyền truy cập, TLS, tải thực tế và khả năng tương thích với dependency.

Một quy trình:

1. Ghim candidate vào commit hoặc label riêng.
2. Khởi chạy một canary instance hoặc một nhóm không nhận toàn bộ traffic.
3. Lấy cấu hình candidate và validate.
4. Chuyển traffic thử nghiệm hoặc chạy smoke test.
5. Theo dõi lỗi, latency, timeout, pool usage và dependency health.
6. Chỉ promote khi vượt ngưỡng đã định trước.
7. Sau đó mới refresh các instance còn lại theo batch.

Không dùng một instance canary đang nhận toàn bộ traffic làm nơi thử các thay đổi có thể làm hỏng cấu hình kết nối hoặc xử lý nghiệp vụ. Cần có cách giới hạn traffic và quay lại phiên bản tốt gần nhất.

### Ví dụ ngưỡng promotion

| Chỉ số | Điều kiện ví dụ |
|---|---|
| Validation | Tất cả ràng buộc bắt buộc PASS |
| Startup/readiness | Instance canary READY |
| Lỗi nghiệp vụ | Không tăng vượt ngưỡng đã định |
| HTTP 5xx | Không tăng đáng kể so với baseline |
| Timeout | Không vượt SLO |
| Dependency health | Database, queue và downstream đều hoạt động |
| Thời gian quan sát | Đủ dài để bao phủ luồng quan trọng |

Ngưỡng cụ thể phải dựa trên SLO và lưu lượng của hệ thống. Không dùng một con số chung cho mọi dịch vụ.

## 10. Quản lý phiên bản last-known-good

Mỗi lần phát hành cấu hình nên có thể truy vết về commit hoặc tag. Ghi nhận phiên bản đang chạy giúp rollback nhanh và tránh phụ thuộc vào nhánh thay đổi liên tục.

Ví dụ:

| Trạng thái | Config label | Ý nghĩa |
|---|---|---|
| Đang phục vụ | <code>config-2026.11.20</code> | Phiên bản đã được xác nhận |
| Candidate | <code>config-2026.11.27-rc1</code> | Đang kiểm thử |
| Last-known-good | <code>config-2026.11.20</code> | Phiên bản dùng để phục hồi |
| Candidate bị từ chối | <code>config-2026.11.27-rc1</code> | Không promote |

Một quy trình release nên lưu:

- Commit hoặc tag cấu hình.
- Phiên bản ứng dụng đã được kiểm thử.
- Application và profile áp dụng.
- Kết quả validation và canary.
- Thời điểm refresh.
- Danh sách instance đã nhận phiên bản.
- Người hoặc pipeline phê duyệt.
- Phiên bản last-known-good để rollback.

Tránh để production chỉ trỏ tới một nhánh như <code>main</code> nếu cần tái lập chính xác cấu hình tại thời điểm sự cố. Tag hoặc commit bất biến giúp biết instance nào đang dùng nội dung nào.

## 11. Rollback khi candidate đã được refresh

Nếu candidate không hợp lệ nhưng chưa được promote, chỉ cần từ chối thay đổi và giữ phiên bản production hiện tại.

Nếu candidate đã tới một số client, cần phục hồi có kiểm soát:

1. Dừng refresh hoặc phát tán candidate tới các instance còn lại.
2. Xác định instance nào đã nhận candidate và instance nào vẫn dùng bản cũ.
3. Trỏ Config Server hoặc deployment về last-known-good commit/tag.
4. Xác nhận endpoint Config Server trả đúng property source cũ.
5. Gửi refresh lại tới các instance đã nhận candidate, hoặc triển khai lại nếu cần.
6. Kiểm tra Environment và bean sau rollback.
7. Chạy smoke test và xác nhận readiness trước khi mở lại traffic.
8. Ghi nhận nguyên nhân, phạm vi ảnh hưởng và bước kiểm tra còn thiếu.

Việc revert Git không tự động đổi Environment đang chạy trong client. Client phải lấy lại cấu hình hoặc được restart theo cơ chế triển khai. Nếu refresh trước đó đã làm một số bean đổi và một số bean chưa đổi, không giả định rollback sẽ tự khôi phục đồng bộ mọi trạng thái. Có thể cần restart một batch instance bằng label last-known-good để đưa chúng về cùng trạng thái đã biết.

### Khi nào nên restart thay vì refresh?

Ưu tiên restart có kiểm soát nếu:

- Bean hoặc thư viện không hỗ trợ cập nhật an toàn lúc runtime.
- Không xác định được thành phần nào đã nhận candidate.
- Connection pool hoặc tài nguyên native đang ở trạng thái không nhất quán.
- Refresh đã gây lỗi tạo bean và không thể xác minh target cũ còn hoạt động.
- Cần bảo đảm toàn bộ process nạp cùng một config label.

Rolling restart với readiness gate thường dễ chứng minh trạng thái hơn việc cố sửa một Environment đã bị cập nhật một phần.

## 12. Phối hợp refresh endpoint và Spring Cloud Bus

Config Client có thể nhận thay đổi bằng endpoint refresh được bảo vệ, ví dụ:

~~~http
POST /actuator/refresh
~~~

Spring Cloud Bus có thể phát tán refresh event tới nhiều instance qua broker. Ví dụ endpoint thường gặp:

~~~http
POST /actuator/busrefresh
~~~

Tên endpoint, dependency và cách expose phụ thuộc phiên bản Spring Cloud. Cả hai cơ chế đều cần xác thực, phân quyền và giới hạn mạng.

Không nên phát <code>busrefresh</code> ngay sau mỗi commit mà chưa có bước validation. Bus có thể khiến nhiều instance cùng nạp candidate lỗi, làm phạm vi ảnh hưởng tăng nhanh.

Một trình tự phù hợp:

1. CI xác thực candidate.
2. Canary nhận candidate và kiểm tra.
3. Promote phiên bản cấu hình.
4. Refresh theo batch hoặc dùng Bus khi đã sẵn sàng phát tán.
5. Theo dõi instance nhận phiên bản mới.
6. Dừng đợt rollout nếu metric vượt ngưỡng.

Bus giải quyết việc phân phối event; nó không xác thực tính đúng đắn của nội dung và không cung cấp rollback giao dịch cho toàn bộ ứng dụng.

## 13. Xử lý secret và cấu hình nhạy cảm khi validation thất bại

Candidate có thể chứa password, token, certificate hoặc URL có credential. Khi validation thất bại:

- Không log toàn bộ Environment hoặc <code>PropertySource</code>.
- Không đưa giá trị secret vào exception message.
- Không lưu response Config Server nguyên bản vào CI artifact công khai.
- Chỉ log tên khóa, nguồn, loại lỗi và candidate ID.
- Mask hoặc loại bỏ trường nhạy cảm trong báo cáo.
- Giữ quyền truy cập audit và Actuator ở phạm vi tối thiểu.

Nếu secret mới không hợp lệ, ví dụ credential database không kết nối được, giữ secret đang hoạt động nếu quy trình cho phép. Với rotation, nên dùng chiến lược overlap: tạo credential mới, xác minh kết nối bằng credential mới, chuyển workload, rồi mới thu hồi credential cũ. Không thu hồi credential cũ trước khi các instance đã chuyển đổi thành công, trừ khi đang xử lý sự cố lộ lọt cần revoke khẩn cấp.

## 14. Chẩn đoán khi refresh làm luồng xử lý lỗi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Config Server trả HTTP 200 nhưng refresh gây lỗi | Giá trị hợp lệ về cú pháp nhưng sai kiểu hoặc sai ràng buộc | Kiểm tra bind và validation bằng đúng app version |
| <code>/actuator/refresh</code> báo lỗi | Không parse được source, lỗi bind hoặc lỗi refresh listener | Giữ rollout, xem exception đã mask và xác định phase thất bại |
| Refresh trả về nhưng request sau đó lỗi | Refresh-scoped target được tạo lại và candidate không hợp lệ | Ngừng traffic canary, rollback về last-known-good |
| Một số instance tốt, một số instance lỗi | Refresh không đồng thời hoặc instance dùng label khác nhau | So sánh config version và trạng thái từng instance |
| Bean có giá trị mới nhưng connection pool vẫn cũ | Tài nguyên không được tái tạo hoặc bean giữ snapshot | Kiểm tra lifecycle và cách cập nhật resource |
| Rollback Git nhưng client vẫn lỗi | Client chưa refresh hoặc bean/resource chưa được tạo lại | Re-fetch cấu hình và restart theo batch nếu cần |
| Validation pass nhưng endpoint không truy cập được | DNS, TLS, firewall hoặc downstream chưa sẵn sàng | Canary connectivity test và readiness check |
| Secret mới bị từ chối | Sai policy, secret chưa đồng bộ hoặc credential chưa active | Kiểm tra bằng danh tính runtime, không log secret |

Khi điều tra, ghi nhận candidate ID, config label/commit, application/profile, instance ID, thời điểm refresh và phase thất bại. Tránh thu thập giá trị bí mật để tái hiện lỗi.

## 15. Kịch bản thực tế: timeout mới không hợp lệ

Giả sử <code>orders-service</code> đang dùng:

~~~yaml
orders:
  reservation:
    timeout: 2s
    max-attempts: 2
~~~

Nhóm đề xuất candidate:

~~~yaml
orders:
  reservation:
    timeout: -1s
    max-attempts: 20
~~~

Quy trình an toàn:

1. Pull request thay đổi config được CI parse thành công.
2. Candidate được bind vào <code>ReservationProperties</code>.
3. Custom validator cho <code>Duration</code> phát hiện timeout âm; <code>@Max(5)</code> phát hiện số lần thử vượt giới hạn.
4. CI đánh dấu REJECTED và không promote label production.
5. Không gửi <code>/actuator/refresh</code> hoặc <code>busrefresh</code>.
6. Các instance production tiếp tục dùng phiên bản cấu hình last-known-good.
7. Nhóm sửa candidate, chạy lại validation và canary trước khi phát hành.

Nếu candidate đã bị refresh vào một canary và target mới không tạo được, đưa canary ra khỏi traffic, khôi phục label tốt và refresh/restart canary để xác nhận trạng thái. Chỉ sau khi canary ổn định mới mở lại traffic và tiếp tục rollout.

## 16. Checklist bảo vệ luồng đang chạy

- [ ] Candidate có ID và version Git/label có thể truy vết.
- [ ] YAML/Properties được parse trong CI trước khi merge.
- [ ] Cấu hình được bind bằng đúng phiên bản ứng dụng sẽ chạy.
- [ ] Có Bean Validation cho thuộc tính bắt buộc và giới hạn cơ bản.
- [ ] Có validator cho ràng buộc liên thuộc tính.
- [ ] Có integration check cho DNS, TLS, database, queue hoặc downstream quan trọng.
- [ ] Candidate được kiểm thử trong context riêng, không làm thay đổi Environment production.
- [ ] Có canary và ngưỡng promotion rõ ràng.
- [ ] Không phát tán refresh trước khi candidate được phê duyệt.
- [ ] Hiểu rõ giới hạn không nguyên tử của refresh và <code>@RefreshScope</code>.
- [ ] Với luồng quan trọng, cấu hình runtime được chuyển bằng snapshot đã validate.
- [ ] Có last-known-good label/commit và quy trình rollback đã diễn tập.
- [ ] Biết khi nào phải restart thay vì tiếp tục refresh.
- [ ] Theo dõi config version, refresh success/failure và lỗi nghiệp vụ theo instance.
- [ ] Không log hoặc lưu secret trong output validation và chẩn đoán.

Cấu hình mới không hợp lệ cần bị chặn trước khi trở thành trạng thái đang phục vụ. Spring Cloud Config cung cấp cơ chế lấy và làm mới property source; nó không tự bảo đảm validation nghiệp vụ, chuyển đổi nguyên tử hoặc rollback mọi bean. Kết hợp CI validation, bind và kiểm tra ràng buộc, candidate context riêng, canary, snapshot runtime và last-known-good giúp hệ thống từ chối thay đổi lỗi mà vẫn duy trì luồng đang chạy với cấu hình đã được xác nhận.

