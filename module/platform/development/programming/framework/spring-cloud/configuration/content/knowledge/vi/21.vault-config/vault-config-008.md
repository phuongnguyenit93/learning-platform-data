# Phân biệt gia hạn bí mật với làm mới bean đang sử dụng bí mật

Một ứng dụng Spring Boot có thể lấy mật khẩu database, API token hoặc credential động từ HashiCorp Vault. Các secret này có vòng đời riêng do Vault quản lý; trong khi đó, bean Spring đang sử dụng chúng có vòng đời do ứng dụng quản lý. Hai vòng đời liên quan nhưng không đồng nhất.

**Gia hạn lease** giúp kéo dài thời gian hiệu lực của một secret động. **Làm mới bean** cập nhật đối tượng trong Spring để nó sử dụng giá trị cấu hình mới. Một lease được gia hạn thành công không có nghĩa bean phải được tạo lại; ngược lại, refresh bean không tự gia hạn lease trong Vault.

Phân biệt rõ hai thao tác này giúp tránh tình huống ứng dụng dùng credential đã hết hạn, tạo connection pool mới quá sớm hoặc tưởng rằng endpoint refresh đã xử lý xong vòng đời secret. Bài viết giải thích dynamic secrets và KV secrets, lease renewal, secret rotation, Spring Cloud Vault, `@RefreshScope`, Config Server, connection pool và quy trình phối hợp khi credential thay đổi.

## 1. Ba khái niệm có vòng đời khác nhau

Cần phân biệt ba thao tác thường bị gọi chung là “refresh secret”:

| Thao tác | Thành phần quản lý | Điều gì thay đổi? |
| --- | --- | --- |
| **Lease renewal** | Vault và lease lifecycle manager | Gia hạn thời gian sử dụng của lease hiện tại; thường giữ nguyên credential |
| **Secret rotation/reissue** | Vault secret engine hoặc quy trình quản trị secret | Tạo credential mới hoặc thay giá trị secret; có thể phát sinh lease mới |
| **Bean refresh** | Spring Cloud Context và ứng dụng | Làm mới Environment/rebind hoặc tạo lại target bean để ứng dụng dùng cấu hình mới |

Ví dụ với database credentials do Vault Database Secrets Engine cấp:

- Vault tạo username/password tạm thời cùng `lease_id`, thời lượng lease và cờ `renewable`.
- Nếu lease có thể gia hạn, Vault kéo dài thời hạn của lease hiện tại. Username/password thường không đổi.
- Khi cần credential mới, ứng dụng hoặc integration yêu cầu secret mới; Vault cấp một cặp credential khác và một lease mới.
- Nếu bean hoặc connection pool đang giữ credential cũ, ứng dụng cần một quy trình cập nhật để dùng credential mới và xử lý an toàn các kết nối cũ.

Lease renewal không phải thao tác thay password. Bean refresh cũng không phải lệnh renew lease. Có thể cần cả hai khi secret được thay mới, nhưng mỗi thao tác giải quyết một phần khác nhau.

## 2. Luồng tổng thể giữa Vault và Spring

Vault quản lý thời hạn và quyền sử dụng secret. Spring quản lý cách giá trị được nạp vào Environment, binding vào bean và được sử dụng trong request.

~~~mermaid
flowchart TD
    V[Vault secret engine] -->|issue credential + lease| L[Lease lifecycle manager]
    L -->|renew lease| V
    L -->|rotation / new secret event| P[Secret property source]
    P --> E[Spring Environment]
    E -->|bind / rebind| B[Spring bean]
    R[Refresh event / Bus] --> E
    R --> S[@RefreshScope target invalidation]
    S -->|next invocation| B
    B --> D[DataSource / API client]
~~~

Có thể nhìn luồng thành hai nhánh:

- Nhánh Vault: cấp secret, quản lý lease, gia hạn hoặc cấp credential mới.
- Nhánh Spring: nhận giá trị, cập nhật Environment và làm cho bean đang chạy sử dụng phiên bản phù hợp.

Nếu ứng dụng kết nối Vault trực tiếp bằng Spring Cloud Vault, tiến trình ứng dụng có thể quản lý lease của secret mà nó lấy. Nếu Config Server là thành phần duy nhất kết nối Vault, lease lifecycle thuộc tiến trình Config Server hoặc integration phía server; Config Client chỉ nhận cấu hình do Config Server phân phối. Phải xác định rõ thành phần nào thực sự gọi Vault trước khi thiết kế refresh.

## 3. Dynamic secret và lease trong Vault

Dynamic secret được Vault tạo theo yêu cầu thông qua một secret engine. Ví dụ, Database Secrets Engine có thể tạo database user riêng cho một ứng dụng hoặc workload. Vault trả về dữ liệu cùng metadata lease:

~~~json
{
  "lease_id": "database/creds/orders-service/<lease-id>",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "username": "<generated-user>",
    "password": "<generated-password>"
  }
}
~~~

Đây là response minh họa; không phải giá trị để sử dụng thực tế. `lease_duration` là thời lượng lease tính bằng giây. `renewable` cho biết lease có thể được gia hạn hay không. `lease_id` định danh lease mà Vault dùng để renew hoặc revoke.

Khi Vault tạo credential động, database thường được cấu hình để credential đó có quyền và thời hạn phù hợp. Khi lease hết hạn hoặc bị revoke, Vault có thể thu hồi credential tại database. Vì vậy, ứng dụng phải quản lý thời điểm hết hạn và không tiếp tục mở kết nối mới bằng credential đã bị thu hồi.

Một lease có thể có giới hạn tối đa. Dù lease renewable, Vault vẫn có thể từ chối gia hạn khi chạm max TTL, khi token xác thực hết hạn hoặc khi policy không còn cho phép. Renewal không bảo đảm secret có thể tồn tại vô hạn.

## 4. Gia hạn lease làm gì?

Gia hạn lease yêu cầu Vault kéo dài thời gian hiệu lực của lease đang tồn tại. Với dynamic database credentials, thao tác này thường giữ nguyên username/password và chỉ cập nhật thời hạn lease.

Ví dụ:

- Vault cấp credential tại thời điểm 09:00 với lease duration 60 phút.
- Lease lifecycle manager gửi yêu cầu gia hạn trước khi hết hạn.
- Vault chấp nhận và cấp thêm thời gian sử dụng cho lease.
- Ứng dụng tiếp tục dùng cùng credential; không cần tạo lại bean chỉ vì lease duration đã được kéo dài.

Gia hạn chỉ thành công khi lease renewable, caller có quyền renew và các giới hạn TTL cho phép. Nếu Vault từ chối renewal, hệ thống cần chuẩn bị lấy credential mới hoặc dừng sử dụng credential trước khi nó bị thu hồi.

Không nên ghi lease ID hoặc request renew chứa lease ID vào log. Lease ID là dữ liệu nhạy cảm; tùy loại lease và cấu hình Vault, người có nó cùng quyền cần thiết có thể thực hiện thao tác trên lease.

## 5. Rotation hoặc cấp credential mới làm gì?

Rotation thay đổi credential được sử dụng. Với dynamic secret, cách thường gặp là yêu cầu Vault cấp một credential mới, sau đó chuyển ứng dụng sang dùng credential đó. Lease mới có ID và thời hạn riêng. Credential cũ có thể tiếp tục hợp lệ trong giai đoạn chuyển tiếp hoặc bị revoke theo chính sách.

Với secret tĩnh, rotation có thể là cập nhật password hoặc token tại hệ thống đích rồi ghi giá trị mới vào Vault. Đây là quy trình thay đổi secret, không phải renew một lease dynamic.

Một quy trình rotation an toàn cần phối hợp:

1. Tạo credential mới và xác nhận hệ thống đích chấp nhận nó.
2. Đưa secret mới vào nguồn cấu hình mà ứng dụng sử dụng.
3. Làm mới Environment hoặc nạp lại secret.
4. Tạo mới hoặc cập nhật bean/client/connection pool đang giữ credential.
5. Kiểm tra kết nối mới hoạt động.
6. Chờ các request và transaction đang dùng credential cũ hoàn tất.
7. Thu hồi credential cũ khi không còn workload nào cần nó.

Nếu revoke credential cũ trước khi mọi instance chuyển đổi, các request đang mở kết nối mới có thể thất bại. Với database, cần xác định cách database xử lý session hiện có khi user bị revoke hoặc drop.

## 6. KV secret không giống dynamic secret

Không phải mọi secret trong Vault đều có lease.

| Loại secret | Ví dụ | Có lease như dynamic secret? | Cơ chế thay đổi |
| --- | --- | --- | --- |
| KV v1/v2 | API key, password được quản trị thủ công | Thông thường không | Ghi version/giá trị mới và kích hoạt ứng dụng nạp lại |
| Dynamic database secret | Username/password do Database Secrets Engine tạo | Có | Renew lease hoặc yêu cầu credential mới |
| Dynamic cloud credential | Credential tạm thời từ secret engine tương ứng | Có thể có | Renew hoặc reissue tùy engine và lease |
| Vault token | Token xác thực workload | Có thể có TTL và renewable riêng | Renew token hoặc cấp token mới theo auth method |

KV v2 có version cho từng lần ghi, nhưng version đó không phải lease. Không thể gọi renew lease để kéo dài giá trị KV như một dynamic database credential. Muốn thay KV secret, ghi version mới; sau đó cần cơ chế để property source và bean của ứng dụng nhận giá trị mới.

Cũng cần phân biệt lease của secret với TTL của Vault token dùng để xác thực. Token hết hạn có thể khiến ứng dụng không còn quyền đọc hoặc renew secret; gia hạn token không đồng nghĩa gia hạn lease của secret. Mỗi loại credential có policy và lifecycle riêng.

## 7. Spring Cloud Vault quản lý lease như thế nào?

Spring Cloud Vault tích hợp với Spring Vault để đọc secret và quản lý lease cho những nguồn có lease. Cơ chế lease lifecycle có thể theo dõi lease được cấp, gia hạn lease renewable và xử lý việc cấp lại secret khi cần, tùy loại backend, phiên bản và cấu hình lifecycle.

Ví dụ cấu hình ứng dụng dùng Vault và Database Secrets Engine:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    vault:
      uri: https://vault.internal.example
      authentication: KUBERNETES
      kubernetes:
        role: orders-service
      database:
        enabled: true
        backend: database
        role: orders-service
        username-property: spring.datasource.username
        password-property: spring.datasource.password
      config:
        lifecycle:
          enabled: true
          min-renewal: 10s
          expiry-threshold: 1m
~~~

Các thuộc tính minh họa cho thấy:

- Ứng dụng xác thực với Vault bằng Kubernetes auth.
- Database Secrets Engine được bật và dùng role `orders-service`.
- Username/password được đưa vào các property tương ứng để Spring Boot cấu hình datasource.
- Lifecycle management được bật cho phần cấu hình Vault mà integration hỗ trợ.

Cấu trúc và phạm vi áp dụng của lifecycle properties có thể khác theo phiên bản Spring Cloud Vault/Spring Vault. Trước khi dùng, đối chiếu đúng release train và tài liệu phiên bản đang triển khai; không sao chép cấu hình từ một major version khác mà không kiểm tra. Nếu dùng Config Server Vault backend thay vì client kết nối Vault trực tiếp, hãy xác định lifecycle manager được khởi tạo ở phía server và kiểm tra backend có hỗ trợ lease lifecycle cho loại secret đang dùng.

Ứng dụng cần quyền Vault phù hợp với secret path và thao tác lease cần thiết. Với Kubernetes auth, dùng role và service account riêng cho workload; không dùng root token trong ứng dụng.

## 8. Lease lifecycle và bean lifecycle là hai cơ chế riêng

Spring Cloud Vault/Spring Vault quản lý lease ở tầng truy cập Vault. Spring Cloud Context quản lý refresh Environment và bean. Có thể hình dung:

- Lease manager chịu trách nhiệm renew/revoke hoặc yêu cầu secret mới theo lease.
- Property source/Environment là nơi giá trị được cung cấp cho Spring.
- `@ConfigurationProperties` hoặc `@Value` đưa giá trị vào đối tượng ứng dụng.
- `@RefreshScope` giúp tạo lại target bean khi scope được refresh.
- DataSource hoặc API client phải có quy trình thay credential và quản lý tài nguyên riêng.

Khi lease được gia hạn thành công và credential không đổi, thường không cần refresh bean chỉ để cập nhật thời hạn lease. Ứng dụng tiếp tục dùng cùng username/password.

Khi secret được rotate hoặc cấp mới, giá trị trong property source phải được cập nhật và bean đang giữ bản sao credential phải được rebind hoặc tạo lại. Không giả định mọi lease event tự động làm mới mọi bean. Hành vi cập nhật Environment phụ thuộc integration, loại property source và phiên bản. Hãy kiểm tra event thực tế và thiết kế bước refresh bean rõ ràng.

Ngược lại, gọi `POST /actuator/refresh` không phải thao tác renew lease trong Vault. Nó làm mới cấu hình phía ứng dụng theo cơ chế Spring Cloud Context; nếu Vault integration không yêu cầu hoặc xử lý lease mới, endpoint này không tự thay thế quy trình lease management.

## 9. Bean singleton có thể giữ credential cũ

Ví dụ một service nhận password qua constructor:

~~~java
@Service
public class LegacyDatabaseClient {

    private final String username;
    private final String password;

    public LegacyDatabaseClient(
            @Value("${spring.datasource.username}") String username,
            @Value("${spring.datasource.password}") String password) {
        this.username = username;
        this.password = password;
    }

    public void executeQuery() {
        // Sử dụng credential đã capture lúc bean được tạo.
    }
}
~~~

Bean singleton được tạo một lần trong application context. Nếu Environment nhận password mới nhưng bean không được rebind hoặc tạo lại, field `password` vẫn giữ giá trị cũ.

Đây là lý do phải phân biệt “secret source đã đổi” với “bean đã nhận secret mới”. Kiểm tra Vault hoặc Config Server trả giá trị mới chưa đủ; cần xác nhận thành phần đang kết nối database hoặc API thực sự dùng credential mới.

Với cấu hình bất biến, có thể dùng `@ConfigurationProperties` để binding theo nhóm. Nếu nhóm thuộc tính cần cập nhật động, cần chọn cơ chế rebind/refresh scope và kiểm soát việc thay thế tài nguyên được tạo từ những thuộc tính đó.

## 10. Dùng @RefreshScope khi bean có thể được tạo lại

Ví dụ một client API được tạo từ endpoint và token:

~~~java
@Configuration
public class ProviderClientConfiguration {

    @Bean
    @RefreshScope
    ProviderClient providerClient(Environment environment) {
        String baseUrl = environment.getRequiredProperty(
                "payment.provider.base-url");
        String token = environment.getRequiredProperty(
                "payment.provider.api-token");

        return ProviderClient.builder()
                .baseUrl(baseUrl)
                .apiToken(token)
                .build();
    }
}
~~~

Bean được inject qua scoped proxy. Khi refresh scope bị invalidate, target cũ bị loại khỏi cache; lần gọi tiếp theo tạo target mới và đọc giá trị hiện tại từ Environment.

Để cơ chế này có tác dụng, phải có bước cập nhật Environment trước hoặc trong chu trình refresh. Với client lấy secret trực tiếp từ Vault, cần xác nhận property source đã nhận secret mới. Với client lấy qua Config Server, Config Server phải trả secret mới trước khi Config Client refresh.

Không phải mọi bean đều phù hợp với `@RefreshScope`. Bean quản lý thread pool, socket, connection pool hoặc tài nguyên dài hạn cần xử lý đóng tài nguyên và request đang sử dụng. Tạo lại target có thể đóng resource cũ; hãy kiểm tra semantics của thư viện và thiết kế graceful replacement.

## 11. Đặc biệt thận trọng với DataSource và connection pool

Database credentials thường được capture khi connection pool được tạo. Khi password mới xuất hiện, thay field trong một bean properties không tự đổi credential mà pool dùng để mở connection mới.

Có thể cần tạo pool mới với credential mới rồi chuyển traffic sang pool đó. Trình tự an toàn thường gồm:

1. Giữ pool cũ hoạt động trong lúc tạo pool mới.
2. Kiểm tra pool mới có thể lấy connection bằng credential mới.
3. Chuyển request mới sang pool mới.
4. Chờ transaction và request đang dùng pool cũ hoàn tất.
5. Đóng pool cũ và thu hồi credential cũ sau khi chuyển đổi hoàn tất.

Nếu dùng `@RefreshScope` trực tiếp trên DataSource, việc invalidate target có thể gọi destroy method và đóng pool cũ. Điều đó có thể ảnh hưởng request đang sử dụng connection. Không mặc định rằng refresh scope tự thực hiện drain hoặc handover an toàn.

Với môi trường production, cân nhắc một pool manager có khả năng thay thế pool có kiểm soát, rolling restart từng instance hoặc triển khai hai credential có thời gian overlap. Nếu database chỉ cho phép một password hoạt động tại một thời điểm, cần phối hợp thứ tự đổi password và rollout để tránh khoảng trống kết nối.

## 12. Khi Config Server là trung gian lấy secret từ Vault

Trong kiến trúc tập trung, Config Server có thể kết nối Vault và Git rồi trả Environment cho nhiều Config Client. Khi đó, cần phân biệt tiến trình sở hữu lease:

- Config Server là tiến trình gọi Vault, vì vậy Vault authentication, policy và lease lifecycle thuộc phạm vi server/backend.
- Config Client không có lease ID Vault nếu nó chỉ nhận property từ Config Server.
- Client chỉ biết rằng Config Server cung cấp một giá trị cấu hình; nó cần refresh Environment và bean khi giá trị đó thay đổi.
- Nếu Config Server dùng Vault backend có hỗ trợ lease lifecycle, kiểm tra cách backend xử lý renewal/rotation ở phiên bản đang chạy. Không suy luận rằng mọi composite repository tự động phát event refresh cho tất cả client khi lease thay đổi.

Ví dụ cấu hình composite Git và Vault có thể đặt các thuộc tính không nhạy cảm trong Git và secret trong Vault. Config Server trả kết quả hợp nhất cho client. Trong mô hình này, tránh cấp Vault token cho từng client nếu không cần; nhưng phải giới hạn quyền đọc Config Server theo application/profile vì server có thể trả plaintext secret.

Khi Vault cấp secret mới, cần có cơ chế để Config Server nhìn thấy giá trị mới, sau đó client mới có thể lấy nó. Một webhook Git không tự thông báo thay đổi Vault KV hoặc dynamic secret. Với thay đổi bắt nguồn từ Vault, cần sự kiện/refresh hoặc cơ chế kiểm tra riêng cho Vault backend.

## 13. Trình tự phối hợp khi secret được thay mới

Một quy trình rotation có thể chia thành các mốc để không nhầm lease với bean:

| Giai đoạn | Vault | Spring Environment | Bean / connection |
| --- | --- | --- | --- |
| Ban đầu | Cấp credential A và lease A | Chứa credential A | Đang dùng credential A |
| Gia hạn | Renew lease A | Giá trị vẫn là A | Tiếp tục dùng A |
| Cấp mới | Cấp credential B và lease B | Chưa chắc đã nhận B | Vẫn dùng A |
| Cập nhật cấu hình | Lease B còn hiệu lực | Property source cập nhật B | Bean có thể vẫn giữ A |
| Refresh bean | Không nhất thiết có thao tác Vault | Đã chứa B | Target mới sử dụng B |
| Chuyển đổi hoàn tất | Lease A có thể được revoke | Giá trị hiện hành là B | Kết nối mới dùng B; kết nối cũ đã drain |

Các bước thực tế:

1. Xác định secret là dynamic lease hay KV static value.
2. Xác nhận lease hiện tại có renewable không, TTL còn bao lâu và max TTL là gì.
3. Nếu chỉ cần kéo dài thời gian, để lease manager renew; không tạo bean mới không cần thiết.
4. Nếu cần thay credential, yêu cầu Vault cấp secret mới hoặc cập nhật KV theo quy trình.
5. Xác nhận property source mà ứng dụng dùng đã nhận giá trị mới.
6. Validate cấu hình và tạo bean/client/pool mới.
7. Kiểm tra kết nối bằng credential mới.
8. Drain request/connection cũ rồi mới revoke lease hoặc credential cũ.
9. Ghi nhận lease/secret version và revision cấu hình mà từng instance đang dùng, không ghi giá trị secret.

Nếu credential cũ sắp hết hạn nhưng credential mới chưa được áp dụng, cần cảnh báo và có chính sách fail-safe. Không đợi đến thời điểm Vault thu hồi credential mới bắt đầu refresh bean.

## 14. Nhiều instance và thời điểm chuyển đổi khác nhau

Spring Cloud Bus có thể phát refresh event đến nhiều instance, nhưng mỗi instance xử lý bất đồng bộ. Một instance có thể đã nhận secret mới trong khi instance khác vẫn đang dùng credential cũ.

Với dynamic database credentials, việc revoke lease cũ ngay sau khi phát Bus event có thể làm những instance chưa chuyển đổi mất khả năng tạo kết nối mới. Vì vậy:

- Dùng khoảng thời gian overlap nếu secret engine và hệ thống đích cho phép.
- Theo dõi revision hoặc secret generation của từng instance.
- Chỉ revoke credential cũ khi đủ instance đã xác nhận dùng credential mới.
- Nếu không thể overlap credential, dùng rolling restart hoặc quy trình điều phối traffic để kiểm soát thời điểm chuyển đổi.
- Xác định hành vi khi một instance offline trong lúc rotation diễn ra; instance đó phải lấy credential hiện tại khi quay lại, không dùng secret đã hết hạn.

Không có một transaction toàn cluster giữa Vault lease rotation, Spring Environment refresh và connection pool replacement. Cần quan sát trạng thái từng instance thay vì coi HTTP 200 từ endpoint Bus là xác nhận mọi ứng dụng đã chuyển đổi.

## 15. Kiểm thử riêng lease renewal và bean refresh

Hai cơ chế cần hai nhóm kiểm thử khác nhau.

**Kiểm thử lease lifecycle:**

1. Dùng Vault dev/test với Database Secrets Engine hoặc một secret engine hỗ trợ lease.
2. Lấy secret và ghi nhận TTL, renewable flag cùng metadata an toàn.
3. Xác nhận lease manager gia hạn trước khi hết hạn.
4. Kiểm tra TTL mới và xác nhận credential không đổi nếu thao tác chỉ là renewal.
5. Thử trường hợp lease không renewable hoặc vượt max TTL để xác nhận fallback/rotation.
6. Xác nhận lease ID không xuất hiện trong log.

**Kiểm thử bean lifecycle:**

1. Khởi động ứng dụng với credential A.
2. Xác nhận bean/client/pool đang dùng A.
3. Cập nhật property source thành credential B.
4. Phát refresh event hoặc gọi endpoint refresh phù hợp.
5. Xác nhận bean mới dùng B.
6. Kiểm tra request đang chạy với bean cũ có được hoàn tất an toàn không.
7. Xác nhận tài nguyên cũ được đóng sau khi drain.
8. Kiểm tra lỗi cấu hình mới không làm mất snapshot/connection đang hoạt động ngoài dự kiến.

Có thể dùng một bean chẩn đoán chỉ trả về generation hoặc fingerprint không thể đảo ngược của credential để xác nhận thay đổi, thay vì in password. Fingerprint cũng cần được xử lý thận trọng nếu secret có entropy thấp; tốt hơn là dùng revision ID do pipeline hoặc secret manager cấp.

## 16. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Lease renewal thất bại | Lease không renewable, token hết hạn, policy thiếu quyền hoặc chạm max TTL | Kiểm tra lease metadata, Vault auth và policy; chuẩn bị cấp secret mới |
| Vault đã renew nhưng bean vẫn lỗi | Bean giữ credential cũ hoặc lỗi không liên quan đến TTL | Xác nhận credential, kết nối và bean lifecycle; không refresh chỉ vì renewal |
| Lease hết hạn, connection mới thất bại | Ứng dụng không lấy credential mới trước khi Vault revoke credential cũ | Tạo cảnh báo theo TTL và kiểm thử rotation sớm |
| Vault đã cấp secret mới nhưng client vẫn dùng giá trị cũ | Property source chưa cập nhật hoặc client chưa refresh | Kiểm tra backend, Environment và event refresh |
| Refresh thành công nhưng datasource lỗi | Pool cũ chưa được thay an toàn hoặc credential mới không có quyền | Kiểm tra pool lifecycle và thử kết nối mới trước khi chuyển traffic |
| Một số replica vẫn dùng secret cũ | Bus event bị bỏ lỡ hoặc instance offline | Theo dõi generation từng replica và buộc instance lấy cấu hình hiện hành |
| KV secret không tự đổi | KV không có lease lifecycle như dynamic secret | Ghi version mới và kích hoạt cơ chế reload/refresh |
| Config Server đọc Vault được nhưng client không dùng secret mới | Server chưa refresh backend hoặc client chưa fetch Environment mới | Kiểm tra riêng trạng thái server và client |
| Revoke credential cũ làm gián đoạn request | Thu hồi trước khi connection/request cũ hoàn tất | Dùng overlap, drain và chỉ revoke sau xác nhận |

Chẩn đoán theo hai câu hỏi độc lập: Vault có còn duy trì hiệu lực secret không; và bean đang phục vụ request có đang dùng credential hiện hành không. Trả lời cả hai bằng metadata, revision và trạng thái kết nối, không bằng cách in secret.

## 17. Bảo mật và quan sát vòng đời secret

Lease metadata, lease ID, token Vault và giá trị secret đều cần được bảo vệ. Một số nguyên tắc:

- Không log secret, Vault token, lease ID hoặc request/response body của API Vault.
- Cấp policy tối thiểu: workload chỉ đọc path cần thiết và chỉ renew/revoke lease trong phạm vi được phép.
- Dùng Kubernetes auth, AppRole hoặc workload identity thay cho root token.
- Bảo vệ kết nối tới Vault bằng TLS và xác minh chứng thư.
- Theo dõi TTL còn lại, số lần renew thất bại, số secret rotation và thời gian chuyển đổi bean.
- Gắn revision/generation không nhạy cảm vào log và metric để truy vết.
- Bảo vệ Actuator `env`, `configprops`, `refresh` và Bus endpoint bằng xác thực/phân quyền.
- Không lưu plaintext trong Git, image, log, crash dump hoặc artifact CI.
- Có quy trình revoke khẩn cấp và kiểm tra các instance còn dùng credential cũ.

Không cấp quyền revoke rộng cho mọi ứng dụng chỉ vì chúng cần sử dụng secret. Thông thường, lease lifecycle manager hoặc workload identity chuyên trách mới cần quyền renew/revoke. Client chỉ nên có quyền cần thiết để đọc hoặc sử dụng secret theo kiến trúc đã chọn.

## 18. Nguyên tắc thiết kế

- Xác định secret là dynamic lease, KV static value, Vault token hay credential do hệ thống khác quản lý.
- Dùng renewal để kéo dài lease hiện tại; dùng rotation/reissue khi cần credential mới.
- Không tạo lại bean chỉ vì lease được gia hạn nếu credential không đổi.
- Không coi `@RefreshScope` hoặc `/actuator/refresh` là cơ chế gia hạn Vault lease.
- Chỉ refresh/rebind bean sau khi Environment đã nhận secret mới.
- Với DataSource và connection pool, thiết kế pool replacement, drain và revoke theo trình tự.
- Theo dõi từng instance khi refresh qua Bus; không giả định chuyển đổi toàn cụm là đồng bộ.
- Ghi nhận lease TTL, secret version và config generation nhưng không ghi giá trị bí mật.
- Kiểm thử renewal thất bại, rotation, refresh bean và rollback độc lập.
- Xác định rõ tiến trình nào kết nối Vault: Config Server hay từng Config Client.

Gia hạn lease bảo đảm secret động tiếp tục có hiệu lực theo chính sách Vault; làm mới bean bảo đảm đối tượng Spring sử dụng giá trị cấu hình phù hợp. Khi chỉ renew lease, credential thường giữ nguyên và bean không cần tạo lại. Khi secret được rotate hoặc cấp mới, cần cập nhật property source, refresh bean/client và chuyển connection một cách an toàn trước khi thu hồi credential cũ. Quản lý riêng hai vòng đời này giúp ứng dụng tránh dùng secret hết hạn và tránh gián đoạn khi thay đổi credential trong môi trường nhiều instance.

