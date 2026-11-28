# Tương thích cấu hình giữa phiên bản ứng dụng cũ và mới

Trong một đợt rolling deployment, các instance của ứng dụng không được thay thế cùng một lúc. Một phần instance có thể vẫn chạy phiên bản cũ trong khi phiên bản mới đã bắt đầu nhận traffic. Nếu Config Repository thay đổi key, kiểu dữ liệu hoặc cấu trúc cấu hình ngay lúc này, hai phiên bản có thể đọc cùng một bộ cấu hình theo cách khác nhau và gây lỗi khó tái hiện.

Quản trị tương thích cấu hình cần bảo đảm phiên bản cũ và mới cùng hoạt động trong khoảng chuyển tiếp. Cách làm phổ biến là expand–migrate–contract: trước tiên mở rộng cấu hình để cả hai phiên bản hiểu được; sau đó chuyển dần ứng dụng và dữ liệu sang quy ước mới; cuối cùng mới loại bỏ key cũ khi không còn instance hoặc bản phát hành cần nó. Config Server cung cấp cấu hình theo application, profile và label, nhưng quy trình phát hành phải chủ động bảo đảm từng phiên bản nhận được bộ key tương thích.

## 1. Vì sao cấu hình cũng cần tương thích phiên bản?

Ứng dụng và cấu hình được phát hành độc lập. Một thay đổi trong Config Repository có thể được đọc bởi nhiều phiên bản ứng dụng đang chạy:

~~~mermaid
flowchart TD
    R[Config Repository thay đổi] --> CS[Config Server]
    CS --> O[Instance phiên bản cũ]
    CS --> N[Instance phiên bản mới]
    O --> C{Có hiểu cấu hình mới?}
    N --> D{Có hiểu cấu hình cũ?}
    C -->|Không| E[Lỗi binding hoặc hành vi sai]
    D -->|Không| E
    C -->|Có| F[Rolling deployment an toàn]
    D -->|Có| F
~~~

Ví dụ, phiên bản cũ đọc key orders.timeout-seconds, còn phiên bản mới đọc orders.timeout. Nếu đổi tên key trong một commit duy nhất, instance cũ có thể nhận giá trị mặc định hoặc không có giá trị timeout; instance mới có thể không khởi động nếu key mới chưa được cung cấp.

Các loại thay đổi thường ảnh hưởng đến tương thích:

- Thêm key mới mà phiên bản cũ không biết.
- Xóa hoặc đổi tên key đang được phiên bản cũ sử dụng.
- Đổi kiểu dữ liệu, đơn vị đo hoặc định dạng giá trị.
- Đổi cấu trúc map/list hoặc cách biểu diễn object lồng nhau.
- Thu hẹp tập giá trị hợp lệ của enum hoặc feature flag.
- Thay đổi ý nghĩa nghiệp vụ của key dù tên và kiểu không đổi.
- Thay đổi profile, label hoặc property source khiến một phiên bản nhận bộ cấu hình khác.

Không phải mọi thay đổi cấu hình đều tương thích chỉ vì ứng dụng vẫn parse được YAML. Giá trị có thể bind thành công nhưng làm thay đổi hành vi nghiệp vụ.

## 2. Phân loại thay đổi theo mức độ tương thích

| Loại thay đổi | Rủi ro với phiên bản cũ | Cách triển khai an toàn |
|---|---|---|
| Thêm key tùy chọn có default | Thường thấp nếu code cũ bỏ qua key lạ | Thêm key trước, kiểm tra binding và default |
| Thêm key bắt buộc | Cao nếu phiên bản cũ hoặc mới chưa có giá trị | Triển khai code có fallback trước khi yêu cầu key |
| Đổi tên key | Cao vì một phiên bản có thể không đọc tên còn lại | Duy trì cả key cũ và mới trong giai đoạn chuyển tiếp |
| Xóa key | Cao nếu instance cũ vẫn đọc key đó | Chỉ xóa sau khi toàn bộ instance cũ đã dừng |
| Đổi kiểu dữ liệu | Cao vì binding hoặc logic có thể lỗi | Thêm key mới với kiểu mới, chuyển code, rồi bỏ key cũ |
| Đổi đơn vị đo | Rất cao vì cùng kiểu số nhưng khác ý nghĩa | Dùng tên key thể hiện đơn vị hoặc chuyển đổi tường minh |
| Mở rộng enum | Có thể làm code cũ lỗi nếu switch không có nhánh mặc định | Đảm bảo code cũ xử lý giá trị không nhận diện |
| Đổi ý nghĩa key | Rất cao vì không nhất thiết phát hiện được qua validation | Tạo key mới và tài liệu hóa semantics |

Với thay đổi có rủi ro, hãy tạo key mới thay vì âm thầm đổi ý nghĩa của key cũ. Tên key nên mô tả đơn vị và phạm vi để tránh cách hiểu khác nhau giữa các phiên bản.

## 3. Dùng expand–migrate–contract

Quy trình có ba giai đoạn:

1. **Expand:** bổ sung cấu hình mới nhưng vẫn giữ cấu hình cũ. Triển khai code mới có thể đọc cả hai dạng.
2. **Migrate:** chuyển dần instance, dữ liệu và quy trình vận hành sang key mới. Theo dõi xem còn instance nào đọc key cũ hay không.
3. **Contract:** chỉ sau khi không còn consumer cũ, xóa key cũ và loại bỏ nhánh tương thích khỏi code.

~~~mermaid
flowchart LR
    A[Expand: thêm key mới, giữ key cũ] --> B[Migrate: deploy code mới]
    B --> C[Theo dõi và xác nhận không còn consumer cũ]
    C --> D[Contract: xóa key cũ]
~~~

Mỗi giai đoạn nên là một thay đổi có thể review, kiểm thử và rollback độc lập. Không gộp cả ba giai đoạn vào một lần phát hành nếu hệ thống có nhiều replica hoặc nhiều dịch vụ phụ thuộc.

## 4. Ví dụ đổi tên property mà vẫn hỗ trợ phiên bản cũ

Giả sử cấu hình cũ dùng số giây:

~~~yaml
orders:
  timeout-seconds: 3
~~~

Phiên bản mới muốn dùng kiểu Duration:

~~~yaml
orders:
  timeout: 3s
~~~

Không nên xóa timeout-seconds ngay khi triển khai phiên bản mới. Giai đoạn expand cung cấp cả hai key:

~~~yaml
orders:
  timeout-seconds: 3
  timeout: 3s
~~~

Phiên bản cũ tiếp tục đọc timeout-seconds; phiên bản mới đọc timeout. Trong giai đoạn này, quy trình thay đổi cấu hình phải cập nhật cả hai giá trị để chúng biểu diễn cùng một thời lượng. Nếu hai key lệch nhau, hai nhóm instance có thể có hành vi khác nhau dù đang chạy cùng một release cấu hình.

Code mới có thể đọc key mới và hỗ trợ fallback sang key cũ trong thời gian chuyển tiếp:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public class OrderProperties {

    private Duration timeout;
    private Integer timeoutSeconds;

    public Duration effectiveTimeout() {
        if (timeout != null) {
            return timeout;
        }
        if (timeoutSeconds != null) {
            return Duration.ofSeconds(timeoutSeconds);
        }
        return Duration.ofSeconds(3);
    }

    // getters và setters
}
~~~

Khi triển khai hoàn tất và đã xác nhận không còn phiên bản cũ, có thể xóa timeout-seconds trong một thay đổi riêng. Sau đó, một release code tiếp theo có thể loại bỏ fallback và field cũ.

Nếu dùng constructor binding hoặc record immutable, hãy thiết kế constructor/mapper có thể xử lý cả hai key trong giai đoạn chuyển tiếp. Không giả định hai property cùng tồn tại sẽ tự động được hợp nhất thành một field.

## 5. Không đổi kiểu hoặc đơn vị tại cùng một key

Một lỗi khó phát hiện là giữ nguyên tên key nhưng thay đổi ý nghĩa. Ví dụ:

~~~yaml
# Phiên bản cũ: giá trị tính bằng giây
http:
  connect-timeout: 5
~~~

~~~yaml
# Phiên bản mới: giá trị tính bằng mili giây
http:
  connect-timeout: 5
~~~

YAML vẫn parse và Java vẫn có thể bind vào số nguyên, nhưng thời lượng thay đổi từ 5 giây thành 5 mili giây. Đây là breaking change về semantics.

Nên biểu diễn đơn vị trong tên key hoặc dùng kiểu có đơn vị:

~~~yaml
http:
  connect-timeout: 5s
~~~

hoặc:

~~~yaml
http:
  connect-timeout-millis: 5000
~~~

Nếu chuyển từ key số sang Duration, giữ key cũ trong giai đoạn chuyển tiếp và xác nhận phép chuyển đổi tương đương. Thêm validation để từ chối giá trị âm, bằng không nếu không hợp lệ, hoặc vượt giới hạn vận hành.

## 6. Thêm key mới mà không làm hỏng phiên bản cũ

Thêm property thường tương thích nếu phiên bản cũ bỏ qua key không biết và key mới có default hợp lý. Tuy nhiên, có thể có trường hợp code dùng binding nghiêm ngặt, validation yêu cầu mọi field hoặc cấu hình mới làm thay đổi một component dùng chung.

Ví dụ thêm giới hạn số item:

~~~yaml
orders:
  max-items: 100
~~~

Phiên bản mới khai báo:

~~~java
import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "orders")
@Validated
public class OrderProperties {

    @Min(1)
    private int maxItems = 50;

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
~~~

Nếu key chưa có trong Config Server, default 50 vẫn giúp phiên bản mới khởi động. Trước khi phát hành, cần thống nhất default giữa code và remote config để tránh khác biệt giữa môi trường local, staging và production.

## 7. Profile và label trong giai đoạn chuyển phiên bản

Config Server nhận request theo application, profile và label:

~~~text
/{application}/{profile}/{label}
~~~

Ba thành phần này có thể hỗ trợ triển khai tương thích:

- Application xác định bộ cấu hình của dịch vụ.
- Profile xác định môi trường hoặc nhóm hành vi.
- Label xác định phiên bản cấu hình trong backend, thường là Git branch, tag hoặc ref.

Ví dụ client phiên bản cũ và mới có thể tạm thời dùng hai label riêng:

~~~yaml
# Cấu hình triển khai cho phiên bản cũ
spring:
  cloud:
    config:
      label: app-v1-compatible
~~~

~~~yaml
# Cấu hình triển khai cho phiên bản mới
spring:
  cloud:
    config:
      label: app-v2
~~~

Đây là một chiến lược tách cấu hình theo phiên bản; nó làm tăng số label cần quản lý và phải bảo đảm các bản sửa lỗi bảo mật hoặc cấu hình chung được đưa vào cả hai nhánh khi còn hỗ trợ. Label không tự động được suy ra từ version của artifact. Deployment phải truyền đúng label cho từng nhóm instance.

Thông thường, giữ một label chung với tập key tương thích sẽ đơn giản hơn. Chỉ tách label khi có lý do rõ ràng, ví dụ hai phiên bản cần giá trị không thể cùng tồn tại hoặc cần thử nghiệm canary độc lập.

Không dùng profile để thay thế version compatibility. Profile mô tả môi trường/hành vi; application version và config label là các chiều quản lý khác nhau.

## 8. Ma trận tương thích trước khi phát hành

Trước một thay đổi có ảnh hưởng, lập ma trận giữa phiên bản ứng dụng và phiên bản cấu hình:

| Ứng dụng | Cấu hình expand | Cấu hình mới sau migrate | Cấu hình contract |
|---|---|---|---|
| App v1 | Đọc key cũ | Đọc key cũ | Không tương thích nếu key cũ đã xóa |
| App v2 có fallback | Đọc key mới hoặc fallback cũ | Đọc key mới | Đọc key mới |
| App v2 không fallback | Có thể lỗi nếu key mới chưa có | Đọc key mới | Đọc key mới |

Chỉ phát hành cấu hình contract khi không còn App v1 và không còn job, worker, batch process hoặc phiên bản rollback cần key cũ. Một deployment có thể còn consumer cũ ngoài cụm HTTP chính.

Ma trận cũng nên xét profile và label:

| Trục | Câu hỏi cần trả lời |
|---|---|
| Application | Dịch vụ nào đọc property? |
| App version | Phiên bản code nào đang chạy hoặc có thể rollback? |
| Profile | Những môi trường nào dùng property? |
| Label | Những Git ref/config revision nào còn được triển khai? |
| Instance | Còn replica hoặc worker cũ nào chưa thay thế? |
| Consumer | Có batch job, scheduler hoặc integration nào dùng key này? |

## 9. Quản lý cấu hình chung khi nhiều dịch vụ nâng cấp khác thời điểm

Các file application.yml và application-{profile}.yml có thể ảnh hưởng nhiều dịch vụ. Một thay đổi trong cấu hình chung có thể an toàn với dịch vụ A nhưng phá vỡ dịch vụ B vì chúng đang ở các phiên bản code khác nhau.

Đối với key dùng chung:

- Duy trì semantics ổn định trong thời gian các dịch vụ nâng cấp khác nhau.
- Khi cần thay đổi không tương thích, thêm key mới có namespace rõ ràng hoặc chuyển dần từng ứng dụng.
- Không xóa key chung khi còn một dịch vụ được hỗ trợ sử dụng nó.
- Theo dõi consumer theo application, không chỉ theo repository commit.
- Nếu một dịch vụ cần semantics mới sớm hơn, cân nhắc cấu hình riêng theo application thay vì đổi ngay key chung.

Ví dụ cấu hình chung giữ cả hai key:

~~~yaml
application:
  retry:
    max-attempts: 3
    max-retries: 3
~~~

Trong ví dụ, hai key chỉ là minh họa cho giai đoạn đổi tên. Phải xác định rõ chúng có cùng ý nghĩa và cùng cách tính hay không. Không giữ hai key song song nếu semantics khác nhau mà không có quy tắc ưu tiên được tài liệu hóa.

## 10. Validation và kiểm thử hợp đồng cấu hình

Nên xem property schema như một hợp đồng giữa nhóm quản lý cấu hình và nhóm phát triển ứng dụng. Hợp đồng có thể ghi:

- Tên key và namespace.
- Kiểu dữ liệu, đơn vị và miền giá trị.
- Có bắt buộc hay không.
- Giá trị default.
- Phiên bản đầu tiên hỗ trợ key.
- Phiên bản dự kiến ngừng hỗ trợ key.
- Owner và mục đích nghiệp vụ.

Kiểm thử cấu hình ở nhiều lớp:

1. Parse YAML/properties để phát hiện lỗi cú pháp.
2. Bind vào ConfigurationProperties của phiên bản ứng dụng tương ứng.
3. Chạy validation để phát hiện giá trị ngoài miền.
4. Kiểm tra các key trùng hoặc alias cũ/mới có cùng giá trị hiệu lực.
5. Gọi Config Server với đúng application/profile/label.
6. Chạy smoke test trên bản dựng cũ và mới với cùng bộ cấu hình expand.
7. Kiểm tra refresh nếu ứng dụng hỗ trợ cập nhật runtime.

Một kiểm thử hợp đồng có thể chạy cả hai version artifact trong CI hoặc môi trường staging với cùng một fixture cấu hình. Điều này giúp phát hiện việc phiên bản mới đã xóa field cũ quá sớm hoặc phiên bản cũ không chấp nhận một giá trị mới.

## 11. Rollout canary và rolling deployment

Khi thay đổi cấu hình có ảnh hưởng hành vi, nên triển khai theo phạm vi nhỏ:

1. Commit cấu hình expand, review diff và kiểm tra binding.
2. Đưa phiên bản ứng dụng mới vào một nhóm canary.
3. Xác minh canary đọc đúng key và hoạt động với cấu hình đang dùng.
4. Tăng dần tỷ lệ instance mới, đồng thời theo dõi error rate, latency và nghiệp vụ.
5. Chờ đến khi mọi instance, worker và job đã chuyển phiên bản.
6. Chỉ sau đó mới phát hành cấu hình contract loại bỏ key cũ.

Nếu dùng Spring Cloud Bus hoặc endpoint refresh, phải tính đến instance đang chạy phiên bản cũ có thể nhận thay đổi ngay khi event được phát. Một cấu hình chỉ tương thích với code mới không được broadcast khi còn code cũ đang hoạt động.

Đối với key ảnh hưởng đến hành vi quan trọng, có thể dùng feature flag để tách triển khai code khỏi thời điểm bật hành vi. Flag cũng cần default an toàn và phải tương thích với các version đang chạy.

## 12. Rollback cấu hình và ứng dụng

Rollback cần xét cả artifact và config label. Có thể rollback code nhưng vẫn giữ cấu hình mới nếu cấu hình đó tương thích ngược; cũng có thể phải rollback cả hai nếu semantics đã thay đổi.

Trước khi phát hành, xác định:

- Phiên bản code nào có thể rollback.
- Label/commit cấu hình tương ứng với từng phiên bản.
- Key nào cần giữ để phiên bản cũ khởi động.
- Thay đổi nào đã tạo side effect không thể đảo ngược.
- Có cần phát refresh event sau khi quay lại label trước không.

Ví dụ: App v2 đọc key orders.timeout, App v1 chỉ đọc orders.timeout-seconds. Nếu rollback App v1, cấu hình phải tiếp tục có key cũ hoặc deployment phải đổi sang label chứa key đó. Chỉ rollback image mà không kiểm tra Config Server có thể làm ứng dụng cũ khởi động thiếu timeout.

Rollback cũng không tự hoàn tác dữ liệu nghiệp vụ đã được ghi bằng schema mới. Nếu cấu hình điều khiển định dạng message hoặc schema database, phải có kế hoạch tương thích dữ liệu riêng.

## 13. Quy trình review và phê duyệt thay đổi

Mỗi thay đổi cấu hình nên có thông tin đủ để người review đánh giá tác động:

| Nội dung trong change request | Điều cần ghi |
|---|---|
| Mục đích | Vì sao cần thay đổi và hành vi mong đợi |
| Phạm vi | Application, profile, label và môi trường bị ảnh hưởng |
| Keys | Key thêm, sửa, xóa; kiểu dữ liệu và đơn vị |
| Compatibility | Phiên bản code cũ/mới nào đọc được cấu hình |
| Validation | Kiểm thử binding, giá trị biên và smoke test |
| Rollout | Thứ tự canary, rolling deployment và refresh |
| Rollback | Commit/label trước, điều kiện kích hoạt và người chịu trách nhiệm |
| Audit | Người đề xuất, reviewer, người phê duyệt và thời điểm triển khai |

Tách người tạo thay đổi khỏi người phê duyệt đối với cấu hình production quan trọng. Không đưa secret plaintext vào pull request; chỉ review tên key, nguồn secret và thay đổi quyền truy cập. Thay đổi policy hoặc secret path cũng cần review vì nó có thể làm client mất quyền đọc dù nội dung cấu hình không đổi.

## 14. Theo dõi consumer cũ trước khi contract

Không nên dựa vào cảm giác rằng rollout đã hoàn tất. Cần bằng chứng:

- Metrics hoặc inventory cho biết phiên bản ứng dụng đang chạy.
- Danh sách replica, worker, scheduler và batch job còn hoạt động.
- Log hoặc telemetry cho biết key cũ còn được đọc hay không, nếu ứng dụng có instrumentation phù hợp.
- Lịch sử deployment và rollback window.
- Các môi trường staging, production và disaster recovery đã chuyển đổi.
- Các bản release được hỗ trợ có thể vẫn được khôi phục.

Nếu chưa xác định được consumer, giữ key cũ thêm một chu kỳ phát hành hoặc xây instrumentation trước khi xóa. Chi phí giữ một alias cấu hình thường thấp hơn sự cố do xóa key quá sớm.

## 15. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Instance cũ dùng default thay vì giá trị mong muốn | Key cũ đã bị xóa hoặc đổi tên | Khôi phục key cũ và phát hành theo expand–migrate–contract |
| App mới không bind được property | Key mới chưa có, sai kiểu hoặc validation quá chặt | Bổ sung giá trị tương thích và kiểm tra ConfigurationProperties |
| Hai nhóm instance có hành vi khác nhau | Alias cũ/mới lệch giá trị hoặc semantics không đồng nhất | So sánh remote property sources và giá trị hiệu lực |
| Rolling deployment thất bại | Cấu hình contract được phát hành khi còn instance cũ | Khôi phục key cũ hoặc label tương thích |
| Rollback code nhưng app không khởi động | Cấu hình hiện tại chỉ hỗ trợ version mới | Khôi phục config label tương ứng hoặc giữ alias cũ |
| Một profile bị lỗi nhưng profile khác chạy | Thiếu key ở application-profile context | Kiểm tra mọi profile/label được triển khai |
| Client nhận config mới ngay giữa rollout | Bus refresh được broadcast khi code cũ còn chạy | Chỉ phát event khi cấu hình tương thích với toàn bộ instance |
| Giá trị parse được nhưng hành vi sai | Đổi đơn vị hoặc ý nghĩa mà không đổi tên key | Tạo key mới, chuyển đổi tường minh và kiểm thử nghiệp vụ |

## 16. Checklist tương thích trước phát hành

- [ ] Đã phân loại key thêm, sửa, đổi tên, đổi kiểu và xóa.
- [ ] Đã ghi rõ đơn vị và semantics của từng property.
- [ ] Cấu hình expand vẫn hỗ trợ phiên bản ứng dụng cũ.
- [ ] Phiên bản mới có fallback hoặc default trong giai đoạn chuyển tiếp.
- [ ] Các key cũ/mới cùng tồn tại có giá trị tương đương.
- [ ] Đã kiểm thử binding với artifact cũ và mới.
- [ ] Đã kiểm tra application, profile và label liên quan.
- [ ] Đã rollout canary và theo dõi hành vi.
- [ ] Không broadcast refresh cấu hình breaking khi còn instance cũ.
- [ ] Đã xác nhận không còn worker/job/consumer cũ trước khi xóa key.
- [ ] Có config label/commit và artifact rollback tương ứng.
- [ ] Có reviewer, approver, audit và kế hoạch rollback.

Tương thích cấu hình là hợp đồng giữa Config Repository và mọi phiên bản ứng dụng còn được triển khai hoặc hỗ trợ rollback. Dùng expand–migrate–contract, giữ key cũ trong thời gian chuyển tiếp, kiểm thử cùng một bộ cấu hình trên nhiều artifact và chỉ contract khi đã xác nhận hết consumer cũ. Nhờ đó, Config Server có thể phân phối cấu hình trong suốt rolling deployment mà không buộc tất cả ứng dụng phải nâng cấp đồng thời.
