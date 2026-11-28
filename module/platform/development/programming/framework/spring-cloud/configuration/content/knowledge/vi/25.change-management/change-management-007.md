# Đổi đồng thời nhiều khóa và giới hạn về tính nguyên tử phân tán

Một thay đổi cấu hình thường gồm nhiều khóa có quan hệ với nhau. Ví dụ, đổi endpoint thanh toán có thể đồng thời cần đổi timeout, retry count, tên credential và cờ bật giao thức mới. Nếu chỉ một phần khóa được áp dụng, ứng dụng có thể kết nối tới endpoint mới bằng credential cũ hoặc dùng retry policy không tương thích.

Git giúp đóng gói nhiều file cấu hình trong một commit, và Config Server có thể trả các property source của một phiên bản cấu hình trong một Environment response. Tuy nhiên, điều đó không tạo ra một transaction phân tán bao trùm mọi Config Server replica, mọi Config Client, mọi bean và mọi request đang chạy. Mỗi lớp có thời điểm cập nhật và giới hạn riêng.

Thiết kế an toàn cần tách ba câu hỏi:

1. **Các khóa có được phát hành cùng một phiên bản nguồn không?** Đây là trách nhiệm của Git commit, tag/commit label và cách quản lý backend.
2. **Các instance có nhận cùng phiên bản không?** Đây là trách nhiệm của Config Server, refresh trigger, Bus và quy trình rollout.
3. **Ứng dụng có chuyển sang dùng bộ giá trị mới như một đơn vị không?** Đây là trách nhiệm của cách bind cấu hình, vòng đời bean và logic nghiệp vụ.

## 1. Ví dụ về thay đổi cần đồng bộ nhiều khóa

Giả sử `order-service` đang gọi payment gateway cũ:

```yaml
payment:
  endpoint: https://payments-v1.internal
  connect-timeout: 2s
  read-timeout: 5s
  max-retries: 2
  protocol: legacy
```

Nhóm phát triển chuyển sang gateway v2. Thay đổi cần đồng bộ ít nhất ba giá trị: endpoint, protocol và retry policy. Nếu endpoint mới chỉ hỗ trợ giao thức mới, áp dụng riêng `payment.endpoint` trước khi `payment.protocol` được đổi có thể làm request thất bại.

Một bộ cấu hình đích có thể là:

```yaml
payment:
  endpoint: https://payments-v2.internal
  connect-timeout: 1s
  read-timeout: 4s
  max-retries: 1
  protocol: v2
  config-release: payment-v2-2026-11
```

Các khóa trên tạo thành một **configuration change set**: chúng được review, kiểm thử và phát hành như một đơn vị. `config-release` là metadata do đội vận hành đặt để quan sát phiên bản logic; nó không thay thế Git commit SHA hoặc Config Server label.

## 2. Git commit cung cấp ranh giới nguyên tử ở tầng nguồn

Khi các file liên quan nằm trong cùng một Git repository, hãy cập nhật tất cả trong một commit. Git commit tham chiếu tới một tree snapshot; khi branch ref được cập nhật, người đọc thấy commit cũ hoặc commit mới, không thấy một commit chỉ chứa nửa số file được stage trong cùng change set.

Ví dụ repository:

```text
config-repo/
├── application.yml
├── order-service.yml
└── order-service-production.yml
```

Một pull request có thể cập nhật nhiều file:

```bash
git add order-service.yml order-service-production.yml
git commit -m "Move order service to payment gateway v2"
git push origin change/payment-gateway-v2
```

Sau review và merge, commit mới chứa toàn bộ thay đổi đã được phê duyệt. Với quy trình phát hành cần tái lập, gắn tag hoặc ghi lại commit SHA cụ thể:

```bash
git tag config-release-2026.11.27 <commit-sha>
git push origin config-release-2026.11.27
```

Không cần commit theo từng key. Nếu cập nhật endpoint, timeout và retry policy thành ba commit độc lập, Config Server hoặc client có thể quan sát các trạng thái trung gian giữa các lần fetch/refresh. Một commit cho toàn bộ change set làm giảm nguy cơ đó ở tầng repository.

### Ranh giới của bảo đảm từ Git

Git chỉ cung cấp snapshot nhất quán trong phạm vi một repository và một commit. Nếu các khóa nằm trong hai repository độc lập, không có một Git commit duy nhất bao trùm cả hai. Nếu composite Config Server đọc nhiều repository, từng repository có thể được fetch ở thời điểm khác nhau và đang ở commit khác nhau.

Vì vậy, một commit đơn là cách tốt để gom thay đổi trong một repo, nhưng không phải transaction phân tán giữa Git, Vault, Consul, database và mọi ứng dụng.

## 3. Dùng label bất biến để xác định phiên bản cấu hình

Config Server phục vụ cấu hình theo application, profile và label. Với Git backend, label có thể là branch, tag hoặc commit ID. Branch như `main` là tham chiếu có thể di chuyển; cùng một URL có thể trả nội dung khác ở hai thời điểm.

Khi cần rollout có kiểm soát, dùng tag release hoặc commit SHA đã xác định thay cho việc chỉ dựa vào branch mutable. Ví dụ client có thể chọn label qua:

```yaml
spring:
  cloud:
    config:
      label: config-release-2026.11.27
```

Hoặc đặt label theo environment variable của deployment:

```text
SPRING_CLOUD_CONFIG_LABEL=config-release-2026.11.27
```

Một label release nên được quản lý như bất biến sau khi phát hành. Nếu tag bị di chuyển hoặc branch tiếp tục thay đổi, các lần refresh sau có thể nhận nội dung khác với lần kiểm thử trước.

Config Server Git backend có thuộc tính `spring.cloud.config.server.git.refresh-rate`. Giá trị mặc định `0` có nghĩa server fetch dữ liệu Git mỗi khi có request; giá trị dương giới hạn tần suất fetch theo số giây; giá trị âm tắt refresh. Nếu bật cache/fetch interval, sau khi commit mới đã được push, Config Server có thể chưa nhìn thấy ngay nội dung mới. Cần kiểm tra cấu hình backend và response thực tế trước khi refresh client.

## 4. Một Environment response không phải transaction toàn hệ thống

Config Server trả về một Environment gồm các property source được xác định theo application, profile và label. Nếu các khóa liên quan nằm trong cùng snapshot của một Git repository và request đọc đúng label đó, server có thể trả chúng trong cùng response.

Điều này hữu ích vì client có thể tải một bộ cấu hình đã được đóng gói cùng phiên bản nguồn. Nhưng vẫn có các giới hạn:

- Một request khác có thể tới Config Server replica đang có trạng thái fetch/cache khác.
- Một composite Environment có thể gồm nhiều repository hoặc backend có vòng đời cập nhật độc lập.
- Các Config Client không gửi request refresh cùng một thời điểm.
- Mỗi client có thể dùng application, profile hoặc label khác nhau.
- Một response thành công không bảo đảm mọi property source đều chứa các key bắt buộc về mặt nghiệp vụ.

Environment response là một kết quả đọc cấu hình, không phải distributed transaction đã khóa tất cả nguồn và client.

## 5. Composite repositories không có một commit chung

Giả sử Config Server ghép ba nguồn:

| Nguồn | Nội dung | Phiên bản độc lập |
|---|---|---|
| Git platform | Endpoint chung và cờ tính năng | Commit `P42` |
| Git order-service | Payment endpoint, timeout và retry | Commit `O18` |
| Vault KV | API credential | KV version `V7` |

Một Environment response có thể chứa property source từ cả ba nguồn, nhưng Git commit `P42`, Git commit `O18` và Vault version `V7` không được cập nhật bằng một transaction chung. Nếu một nguồn đã lên phiên bản mới còn nguồn khác chưa sẵn sàng, Config Server có thể tổng hợp một tổ hợp version không tương thích.

Để giảm rủi ro:

- Ưu tiên đặt các khóa cần thay đổi đồng thời trong cùng repository hoặc cùng backend có snapshot/version rõ ràng.
- Nếu buộc phải dùng nhiều backend, lập release manifest ghi rõ phiên bản mong đợi của từng nguồn.
- Đưa secret mới vào Vault trước khi cấu hình tham chiếu secret đó được phát hành.
- Chỉ phát refresh sau khi tất cả backend cần thiết đã được xác minh.
- Kiểm tra giá trị/metadata không nhạy cảm từ Environment response; không in secret để đối chiếu.

Ví dụ manifest logic:

```yaml
config-release: payment-v2-2026-11
required-sources:
  platform-config: P42
  order-config: O18
  payment-secret-version: V7
```

Manifest này chỉ có ý nghĩa nếu pipeline hoặc ứng dụng kiểm tra nó. Chỉ ghi metadata vào YAML không tự tạo ra transaction hay bảo đảm backend đã đồng bộ.

## 6. Refresh là thao tác riêng trên từng Config Client

Sau khi Config Server đã phục vụ đúng change set, client cần được yêu cầu refresh. Với một instance, Spring Cloud Context có thể nạp lại Environment qua `/actuator/refresh`. Với nhiều instance, Spring Cloud Bus có thể phát sự kiện qua broker bằng `/actuator/busrefresh`.

Ví dụ expose endpoint Bus refresh:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
```

Gửi yêu cầu refresh:

```bash
curl --fail --silent --show-error \
  --request POST \
  https://order-service.internal/actuator/busrefresh
```

Endpoint phải được bảo vệ bằng authentication, authorization và mạng quản trị. Bus truyền tín hiệu refresh; các client sau đó truy vấn Config Server để lấy Environment. Bus không gửi một snapshot cấu hình đã được khóa chung cho toàn bộ fleet.

### Vì sao refresh hàng loạt không nguyên tử?

- Broker phân phối sự kiện bất đồng bộ.
- Instance có thể đang offline, mất kết nối broker hoặc xử lý sự kiện chậm.
- Mỗi instance gọi Config Server ở thời điểm khác nhau.
- Instance có thể nhận response từ Config Server replica hoặc backend cache khác nhau.
- Một số bean có thể refresh thành công trong khi bean khác không hỗ trợ refresh hoặc khởi tạo lại thất bại.

HTTP request tới `/actuator/busrefresh` thành công chỉ xác nhận endpoint đã xử lý việc phát sự kiện theo cơ chế Bus; nó không phải bằng chứng tất cả instance đã áp dụng cấu hình mới.

## 7. Environment và bean cũng có giới hạn nguyên tử

Khi client refresh, Spring Cloud Context cập nhật Environment và phát sự kiện thay đổi. Các bean `@ConfigurationProperties` được hỗ trợ có thể được rebind. Bean `@RefreshScope` có target cache được xóa để target mới được tạo khi truy cập.

Tuy nhiên, không phải mọi singleton đều được xây dựng lại. Field `@Value` trong một singleton thông thường có thể tiếp tục giữ giá trị đã inject lúc khởi tạo. Một thành phần đã mở connection hoặc khởi tạo pool có thể cần thao tác tái tạo riêng.

Nếu một nghiệp vụ đọc nhiều bean cấu hình trong khi refresh diễn ra, không nên mặc định toàn bộ bean sẽ chuyển sang snapshot mới cùng một thời điểm. Với yêu cầu nhất quán chặt, hãy gom các khóa liên quan vào một đối tượng cấu hình bất biến và thay thế tham chiếu của đối tượng đó như một thao tác duy nhất sau khi validate.

## 8. Gom các khóa liên quan thành một configuration object

Thay vì để nhiều service đọc rời rạc từng key, gom các giá trị có quan hệ vào một namespace:

```yaml
payment:
  config-release: payment-v2-2026-11
  endpoint: https://payments-v2.internal
  protocol: v2
  connect-timeout: 1s
  read-timeout: 4s
  max-retries: 1
```

Một `@ConfigurationProperties` object giúp khai báo kiểu và validation tập trung:

```java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public class PaymentProperties {

    @NotNull
    private URI endpoint;

    @NotNull
    private String protocol;

    @NotNull
    private Duration connectTimeout;

    @NotNull
    private Duration readTimeout;

    @Min(0)
    private int maxRetries;

    private String configRelease;

    // Getters and setters omitted for brevity.
}
```

Đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Validation cần kiểm tra các quan hệ giữa field, ví dụ protocol `v2` chỉ được phép với endpoint hỗ trợ v2 và retry count nằm trong giới hạn đã định.

Gom key dưới một prefix không tự đảm bảo atomicity toàn ứng dụng, nhưng làm rõ change set và giúp validate đầy đủ trước khi thành phần nghiệp vụ dùng cấu hình.

## 9. Dùng immutable snapshot để đổi nhiều giá trị cùng lúc

Khi một request nghiệp vụ phải thấy một bộ payment settings nhất quán, có thể xây dựng một object bất biến rồi thay thế một tham chiếu duy nhất sau khi kiểm tra thành công.

Ví dụ minh họa ý tưởng:

```java
import java.net.URI;
import java.time.Duration;

public record PaymentPolicy(
        String release,
        URI endpoint,
        String protocol,
        Duration connectTimeout,
        Duration readTimeout,
        int maxRetries) {
}
```

```java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class PaymentPolicySnapshot {

    private final AtomicReference<PaymentPolicy> current =
        new AtomicReference<>(new PaymentPolicy(
            "payment-v1", URI.create("https://payments-v1.internal"),
            "legacy", Duration.ofSeconds(2), Duration.ofSeconds(5), 2));

    public PaymentPolicy current() {
        return current.get();
    }

    public void replace(PaymentPolicy validatedPolicy) {
        current.set(validatedPolicy);
    }
}
```

Quy trình cập nhật:

1. Đọc toàn bộ nhóm key từ Environment mới.
2. Tạo một `PaymentPolicy` mới.
3. Validate URL, protocol, timeout, retry count và các quan hệ liên quan.
4. Nếu hợp lệ, gọi `replace()` một lần để chuyển tham chiếu sang snapshot mới.
5. Nếu không hợp lệ, giữ snapshot hiện tại và báo lỗi/health status để operator xử lý.

Mỗi request nghiệp vụ nên đọc snapshot một lần ở đầu request rồi dùng cùng object đó trong toàn bộ xử lý. Nếu đọc `current()` nhiều lần giữa một request, request có thể thấy hai snapshot khác nhau nếu refresh xảy ra giữa chừng.

Đây là pattern ứng dụng tự triển khai, không phải hành vi mặc định mà Spring Cloud Config tự cung cấp. Cần tích hợp nó với sự kiện refresh và cơ chế xử lý lỗi của ứng dụng.

## 10. Phát hành theo staged rollout

Khi không có transaction phân tán, cách kiểm soát thực tế là giảm phạm vi mỗi bước và xác minh trước khi mở rộng.

Một quy trình an toàn có thể là:

1. **Prepare:** xác định toàn bộ key liên quan, backend, application/profile và các bean chịu ảnh hưởng.
2. **Validate source:** cập nhật change set trong Git, chạy kiểm tra schema/format và review một lần.
3. **Publish version:** merge commit, tạo tag hoặc ghi lại commit SHA bất biến.
4. **Verify Config Server:** gọi endpoint với đúng application/profile/label; xác nhận metadata/version và các key không nhạy cảm.
5. **Verify backend set:** nếu có Git + Vault hoặc nhiều repository, kiểm tra tất cả version trong release manifest.
6. **Canary:** refresh một instance thử nghiệm hoặc một nhóm nhỏ.
7. **Validate runtime:** kiểm tra Environment, bean, health, log và giao dịch nghiệp vụ.
8. **Expand:** refresh theo từng nhóm/zone hoặc rollout có kiểm soát.
9. **Reconcile:** tìm các instance chưa xác nhận release ID mới; retry hoặc restart chúng.
10. **Close:** chỉ kết thúc phát hành khi toàn bộ instance mục tiêu ở trạng thái đã xác minh hoặc được loại khỏi traffic.

Staged rollout không biến thay đổi thành atomic, nhưng giúp giới hạn blast radius và làm rõ instance nào đã chuyển phiên bản.

## 11. Tạo hàng rào tương thích bằng expand-contract

Khi thay đổi cấu hình gắn với thay đổi code hoặc schema bên ngoài, đừng yêu cầu mọi ứng dụng chuyển cùng một lúc. Dùng chiến lược expand-contract để các phiên bản cũ và mới có thể cùng tồn tại trong thời gian rollout.

Ví dụ đổi tên key `payment.endpoint` thành `payment.base-url`:

**Giai đoạn expand:** phát hành code hiểu cả key cũ và key mới; cấu hình cung cấp cả hai với cùng giá trị.

```yaml
payment:
  endpoint: https://payments-v2.internal
  base-url: https://payments-v2.internal
```

**Giai đoạn migrate:** rollout code mới tới tất cả instance và xác nhận không còn instance chỉ hiểu key cũ.

**Giai đoạn contract:** sau khi toàn bộ workload đã chuyển, xóa key cũ trong một change set riêng.

Tương tự, khi đổi database schema, trước tiên thêm cột/field mới và giữ tương thích với code cũ; sau khi mọi client đã chuyển, mới xóa cấu trúc cũ. Refresh cấu hình không thể thay thế migration transaction của database.

## 12. Xử lý thay đổi có secret hoặc dynamic credential

Nếu change set thay cả endpoint lẫn credential, thứ tự chuẩn bị rất quan trọng. Secret mới cần tồn tại và có policy đọc hợp lệ trước khi client nhận cấu hình tham chiếu nó.

Một trình tự thường an toàn:

1. Tạo credential mới ở hệ thống đích và cấp quyền tối thiểu.
2. Lưu secret mới trong Vault/secret manager và xác nhận Config Server hoặc workload identity có thể đọc.
3. Cập nhật cấu hình tham chiếu secret mới trong Git hoặc nguồn có thẩm quyền.
4. Kiểm tra Environment mà không in giá trị secret.
5. Canary refresh, kiểm tra kết nối bằng credential mới.
6. Mở rộng rollout.
7. Chỉ thu hồi credential cũ sau khi xác nhận không còn instance sử dụng.

Không commit plaintext secret vào Git để giữ tính nguyên tử của change set. Git commit nên chứa reference hoặc ciphertext theo mô hình mã hóa đã chọn; quyền đọc và rotation secret vẫn thuộc hệ thống quản lý secret.

## 13. Rollback nhiều khóa

Nếu thay đổi gây lỗi, rollback nên khôi phục một snapshot đã biết là tốt, thay vì sửa từng key ngược lại theo nhiều request.

Với Git:

- Chọn tag/commit release trước đó hoặc revert commit gây lỗi.
- Xác nhận Config Server phục vụ đúng phiên bản rollback.
- Refresh canary trước, sau đó mở rộng tới các instance còn lại.
- Theo dõi release ID và trạng thái runtime.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      label: config-release-2026.11.20
```

Đây là ví dụ client pin lại tag cũ. Nếu dùng branch mutable, revert commit tạo ra một commit mới; không nên force-push lịch sử production trừ khi chính sách repository cho phép và mọi consumer đã được đánh giá.

Rollback cấu hình chỉ khôi phục các giá trị cấu hình. Nó không tự rollback database migration, dữ liệu đã ghi, request đang xử lý hoặc side effect ở payment gateway. Các thay đổi đó cần kế hoạch tương thích/compensation riêng.

## 14. Theo dõi mức độ đồng bộ giữa các instance

Để biết một thay đổi nhiều khóa đã được áp dụng tới đâu, mỗi ứng dụng nên công bố metadata không nhạy cảm:

- `config-release` hoặc release ID.
- Git commit SHA/label được Config Server phục vụ nếu có.
- Application name và active profiles.
- Thời điểm refresh thành công gần nhất.
- Trạng thái validation của configuration snapshot.
- Trạng thái health sau khi tạo lại bean/tài nguyên.

Không cần expose toàn bộ Environment. Có thể tạo health indicator hoặc metric chỉ trả release ID và trạng thái validation. Endpoint Actuator nhạy cảm phải được bảo vệ.

Một bảng rollout có thể ghi nhận:

| Instance | Release mong đợi | Release đang dùng | Trạng thái |
|---|---|---|---|
| `order-0` | `payment-v2-2026-11` | `payment-v2-2026-11` | Đã xác minh |
| `order-1` | `payment-v2-2026-11` | `payment-v1` | Chưa refresh |
| `order-2` | `payment-v2-2026-11` | `payment-v2-2026-11` | Đã xác minh |

Trong ví dụ, không nên đóng phát hành chỉ vì Bus endpoint trả thành công. `order-1` vẫn cần được refresh hoặc restart và xác minh trước khi kết thúc rollout.

## 15. Những giới hạn cần nhớ

| Lớp | Có thể bảo đảm điều gì? | Không tự bảo đảm điều gì? |
|---|---|---|
| Một Git commit | Các file được commit cùng nằm trong một tree snapshot | Nhiều Git repository, Vault và hệ thống ngoài cùng đổi trong một transaction |
| Git label/commit SHA | Chỉ rõ phiên bản nguồn có thể tái lập | Config Server replica đã fetch cùng lúc hoặc client đã dùng phiên bản đó |
| Một Config Server Environment response | Trả các property source được server tổng hợp cho một request | Các backend độc lập có cùng release transaction hoặc mọi request tương lai đều giống nhau |
| Một client refresh | Cập nhật Environment của tiến trình theo cơ chế refresh | Mọi bean và request đang chạy chuyển phiên bản đồng thời |
| `@RefreshScope` | Tạo lại target khi scope cache bị làm mới và bean được truy cập | Tái tạo an toàn mọi tài nguyên hoặc transaction trên toàn ApplicationContext |
| Spring Cloud Bus | Phân phối tín hiệu tới các node tham gia Bus | Tất cả node đã nhận, refresh thành công và dùng cùng snapshot tại cùng thời điểm |
| Staged rollout | Giới hạn phạm vi và xác minh theo từng nhóm | Không có khoảng thời gian hệ thống chứa nhiều release khác nhau |

Nếu nghiệp vụ yêu cầu không bao giờ có hai phiên bản cấu hình hoạt động đồng thời, cần một cơ chế điều phối ở tầng ứng dụng: dừng nhận traffic, drain request, chuyển toàn bộ instance qua barrier/version gate rồi mở traffic lại. Điều này có thể giảm availability trong thời gian chuyển đổi; phải cân nhắc SLO và khả năng rollback.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Client thấy endpoint mới nhưng protocol vẫn cũ | Các khóa được phát hành ở commit khác nhau hoặc nhiều property source có precedence khác | Gom change set vào một commit và kiểm tra toàn bộ Environment response |
| Một số replica dùng bộ khóa mới, số khác dùng bộ cũ | Bus event chưa tới, refresh lỗi hoặc replica Config Server lệch phiên bản | Theo dõi release ID từng instance, refresh/restart bù và kiểm tra backend version |
| Config Server trả dữ liệu cũ sau khi Git đã merge | Git fetch/cache chưa cập nhật hoặc client yêu cầu label cũ | Kiểm tra `refreshRate`, label và response trực tiếp từ từng Config Server replica |
| Git đã đồng bộ nhưng secret Vault chưa có | Nhiều backend không có transaction chung | Tạo/kiểm tra secret trước, sau đó mới phát hành config tham chiếu |
| Refresh thành công nhưng bean vẫn giữ giá trị cũ | Bean không hỗ trợ rebinding hoặc đang giữ state đã khởi tạo | Dùng configuration snapshot, `@RefreshScope` phù hợp hoặc restart |
| Rollback endpoint nhưng credential cũ đã bị thu hồi | Rollback cấu hình không rollback hệ thống secret/đích | Giữ credential cũ trong thời gian chuyển đổi hoặc phát hành compensation có kiểm soát |
| Một key bị xóa nhưng giá trị cũ vẫn tồn tại trong ứng dụng | Property source khác hoặc bean không reset như mong đợi | Kiểm tra Environment, default và quy tắc rebind của phiên bản đang dùng |
| Bus endpoint trả thành công nhưng rollout vẫn chưa hoàn tất | Publish event không phải xác nhận từng client | Kiểm tra release ID/health từng instance và xử lý node chưa hội tụ |

## 17. Checklist phát hành change set nhiều khóa

- [ ] Đã liệt kê toàn bộ key có quan hệ và application/profile bị ảnh hưởng.
- [ ] Các file cùng repository được cập nhật trong một Git commit.
- [ ] Đã review diff tổng thể và chạy kiểm tra schema/format.
- [ ] Đã gắn tag hoặc ghi nhận commit SHA bất biến cho release.
- [ ] Nếu dùng nhiều backend, đã ghi manifest phiên bản mong đợi của từng nguồn.
- [ ] Secret mới đã tồn tại, có policy đúng và được kiểm tra trước khi client tham chiếu.
- [ ] Config Server replica đều phục vụ đúng application/profile/label/release.
- [ ] Đã xác định refresh hay restart cho từng bean/tài nguyên.
- [ ] Đã kiểm thử cấu hình mới và rollback trên staging.
- [ ] Đã canary một instance/nhóm nhỏ trước khi mở rộng.
- [ ] Có metric/health để biết release ID đang dùng ở từng instance.
- [ ] Có quy trình refresh/restart bù cho instance bỏ lỡ Bus event.
- [ ] Có rollback snapshot và kế hoạch cho side effect ngoài cấu hình.
- [ ] Chỉ đóng phát hành khi mọi instance mục tiêu đã xác minh hoặc được loại khỏi traffic.

## 18. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Giải thích vì sao nhiều khóa liên quan nên được phát hành trong cùng một change set.
- Phân biệt tính nguyên tử của Git commit với tính nguyên tử của Config Server, client refresh và toàn fleet.
- Dùng tag/commit label bất biến để xác định phiên bản cấu hình.
- Phân tích rủi ro khi composite repository ghép nhiều backend có version độc lập.
- Giải thích vì sao Spring Cloud Bus không phải distributed transaction hoặc barrier.
- Gom các khóa liên quan vào một configuration object và validate trước khi áp dụng.
- Dùng immutable snapshot để chuyển bộ cấu hình trong một thao tác ở tầng ứng dụng.
- Thiết kế canary, staged rollout, expand-contract và rollback.
- Theo dõi release ID để phát hiện instance chưa hội tụ.

**Tự kiểm tra:** Một thay đổi cần cập nhật `payment.endpoint`, `payment.protocol`, `payment.max-retries` trong Git và một credential trong Vault. Hai trong năm replica đã refresh thành công, một replica mất kết nối Bus và hai replica còn lại chưa xử lý sự kiện. Hãy giải thích vì sao Git commit không tạo transaction với Vault hoặc năm client, đề xuất thứ tự phát hành an toàn, cách dùng release manifest/canary/health verification và điều kiện để kết thúc rollout.

## Tài liệu tham khảo

- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Cloud Context — Environment Changes and Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Bus — Bus Refresh Endpoint](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)
