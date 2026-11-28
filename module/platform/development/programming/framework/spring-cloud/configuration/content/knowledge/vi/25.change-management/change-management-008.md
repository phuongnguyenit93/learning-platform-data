# Quay lại cấu hình trước và xác minh giá trị thực trên client

Khi một thay đổi cấu hình gây lỗi sau khi phát hành, nhóm vận hành cần đưa hệ thống về một bộ cấu hình đã biết là hoạt động tốt. Việc chọn lại Git revision hoặc revert commit mới chỉ khôi phục nguồn cấu hình; Config Server còn phải đọc được revision đó, Config Client phải nạp lại Environment và các thành phần đang chạy phải thực sự sử dụng giá trị đã khôi phục.

Vì vậy, rollback cấu hình có ba lớp cần xác nhận: **revision ở nguồn**, **giá trị Config Server trả về** và **giá trị cùng hành vi thực tế trên từng Config Client**. Bài viết hướng dẫn quy trình rollback bằng Git, ghim label cũ, kích hoạt refresh, kiểm tra từng instance và theo dõi sau khi khôi phục. Các ví dụ dùng Git backend của Spring Cloud Config; với Vault, native hoặc composite backend, cần bổ sung cách khôi phục version tương ứng của từng nguồn.

## 1. Phân biệt rollback nguồn cấu hình và rollback runtime

Một hệ thống có thể đã khôi phục Git nhưng client vẫn chạy giá trị cũ. Ngược lại, Config Server có thể trả giá trị cũ trong khi một số bean ở client vẫn giữ cấu hình mới đã bind trước đó.

| Lớp | Câu hỏi cần trả lời | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| Git/backend | Nguồn cấu hình đang trỏ đến revision nào? | Commit SHA, tag, version hoặc secret version |
| Config Server | Server có trả đúng bộ cấu hình đã chọn không? | Environment JSON, `version`, `propertySources` |
| Config Client | Client đã nạp đúng cấu hình chưa? | Environment, property source và release ID |
| Runtime component | Bean, pool hoặc client đang dùng giá trị nào? | Binding, trạng thái component và hành vi thực tế |
| Toàn cụm | Tất cả instance đã khôi phục chưa? | Kết quả kiểm tra theo từng instance và metric |

Một thao tác `git revert` không tự động làm mới các ứng dụng. Một request `/actuator/refresh` cũng không đảm bảo mọi bean đều thay đổi được trong runtime. Cần hoàn tất và xác minh từng lớp trước khi tuyên bố rollback thành công.

## 2. Chuẩn bị khả năng rollback trước khi phát hành

Rollback nhanh khi mỗi lần phát hành đều có thể truy vết và tái tạo. Với cấu hình trong Git, nên dùng tag bất biến hoặc ghi lại full commit SHA của bản đã triển khai.

Ví dụ file cấu hình có thể chứa mã phát hành không nhạy cảm:

~~~yaml
config:
  release-id: orders-prod-2026.11.03

orders:
  http:
    read-timeout: 8s
  retry:
    max-attempts: 3
~~~

`config.release-id` là metadata do quy trình release đặt ra. Nó giúp client báo đang dùng bộ cấu hình nào ngay cả khi người vận hành không có quyền đọc toàn bộ Environment. Không đặt password, token hoặc dữ liệu nhạy cảm trong release metadata.

Manifest release có thể ghi:

~~~yaml
release:
  id: orders-prod-2026.11.03
  application: orders-service
  profile: prod
  label: orders-prod-2026.11.03
  git-commit: 4b7f2b6d7b0e9c1a2f3d4e5f60718293a4b5c6d7
~~~

Manifest nên được lưu trong hệ thống release/audit phù hợp. Nó ghi lại label và commit đã triển khai, không thay thế việc kiểm tra Config Server thực tế đang phục vụ revision nào.

Trước khi phát hành, lưu lại:

- Application, profile và label được triển khai.
- Git commit SHA hoặc version của từng backend.
- Các key quan trọng có thể ảnh hưởng đến kết nối, timeout, retry, pool, feature flag hoặc bảo mật.
- Config Server replica và Config Client instance thuộc phạm vi thay đổi.
- Cách refresh, cách restart nếu bean không hỗ trợ refresh và tiêu chí xác nhận thành công.
- Revision trước đó cùng cách quay lại.

## 3. Chọn chiến lược rollback phù hợp

Có hai cách phổ biến khi dùng Git backend.

| Chiến lược | Cách thực hiện | Khi phù hợp |
| --- | --- | --- |
| Revert commit | Tạo commit mới đảo ngược thay đổi gây lỗi | Branch dùng chung, cần giữ lịch sử review/audit |
| Chọn lại label cũ | Client hoặc deployment yêu cầu tag/commit đã phát hành trước đó | Cần ghim một nhóm client về revision đã biết |
| Rollback bằng tag mới | Tạo tag rollback trỏ đến commit cũ theo chính sách tag bất biến | Muốn có tên release rõ ràng cho lần rollback |

Với branch dùng chung như `main`, thường nên dùng `git revert` để tạo commit mới. Cách này giữ lịch sử và tránh viết lại lịch sử branch mà các Config Server đang fetch. Tránh `git reset --hard` kết hợp force push trên branch được nhiều người hoặc hệ thống sử dụng; thao tác đó có thể làm các clone và quy trình release khác nhau hiểu lịch sử không nhất quán.

Nếu client đang ghim immutable tag, có thể triển khai lại label trước đó. Không di chuyển hoặc ghi đè tag release cũ; nếu cần một tên mới, tạo tag rollback riêng trỏ đến commit đã xác minh.

## 4. Rollback bằng git revert

Giả sử commit gây lỗi là `9c8d7e6`. Sau khi xác nhận commit đó chỉ chứa thay đổi cần đảo ngược, tạo revert commit:

~~~bash
git checkout main
git pull --ff-only origin main
git revert 9c8d7e6
git push origin main
~~~

Nếu commit chứa nhiều thay đổi không thể revert nguyên khối, tạo commit sửa cấu hình có chủ đích và review như một thay đổi mới. Với merge commit, cần xác định mainline parent trước khi dùng `git revert -m`; không chọn parent theo phỏng đoán.

Sau khi push:

1. Xác nhận commit revert đã xuất hiện trên remote.
2. Ghi lại SHA của commit mới.
3. Kiểm tra nội dung file đã trở về giá trị mong muốn.
4. Xác nhận webhook hoặc quy trình release đã kích hoạt Config Server fetch.
5. Kiểm tra từng Config Server trước khi refresh client.

Revert commit tạo ra một revision mới có nội dung cấu hình tương đương trạng thái cũ. Trường `version` của Config Server sẽ là SHA của revert commit, không phải SHA của commit lịch sử cũ mà nội dung được khôi phục.

## 5. Rollback bằng label đã phát hành trước

Nếu Config Client được cấu hình label tường minh, có thể yêu cầu lại tag cũ:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: orders-prod-2026.10.28
~~~

Có thể cấp label qua biến môi trường của deployment:

~~~text
SPRING_CLOUD_CONFIG_LABEL=orders-prod-2026.10.28
~~~

Cập nhật label trong manifest/deployment rồi khởi động lại hoặc triển khai lại client theo cách cấu hình Config Data của ứng dụng. Nếu label được cung cấp trước khi Config Data import chạy, client sẽ yêu cầu đúng revision đó. Không giả định thay đổi biến môi trường trong một container đang chạy sẽ tự thay đổi label đã dùng lúc khởi động.

Trước khi chuyển traffic, gọi Config Server với label cũ để xác nhận tag/commit tồn tại và trả đúng nội dung. Nếu dùng tag, bảo vệ tag khỏi bị xóa hoặc di chuyển. Nếu dùng commit SHA, ghi lại đầy đủ SHA và xác nhận Git backend của phiên bản đang chạy hỗ trợ label dạng revision đó.

## 6. Kiểm tra Config Server đã đọc revision rollback

Config Server cung cấp Environment endpoint theo application, profile và label:

~~~bash
curl --fail --silent --show-error \
  https://config.internal.example/orders-service/prod/orders-prod-2026.10.28
~~~

Với Git backend, response JSON thường có trường `version` cho biết revision Git đã được dùng. Ví dụ response rút gọn:

~~~json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "label": "orders-prod-2026.10.28",
  "version": "4b7f2b6d7b0e9c1a2f3d4e5f60718293a4b5c6d7",
  "propertySources": [
    {
      "name": "https://git.example.com/platform/config-repo.git/orders-service-prod.yml",
      "source": {
        "config.release-id": "orders-prod-2026.10.28",
        "orders.http.read-timeout": "8s",
        "orders.retry.max-attempts": 3
      }
    }
  ]
}
~~~

Đây là response minh họa; tên property source và giá trị thực phụ thuộc repository. Kiểm tra:

- `name` đúng application.
- `profiles` đúng profile.
- `label` đúng label rollback.
- `version` khớp commit trong manifest.
- `propertySources` chứa file và key dự kiến.
- Giá trị không nhạy cảm khớp với bản đã biết là tốt.

Không lưu toàn bộ Environment response nếu nó có secret đã được Config Server giải mã. Có thể trích xuất metadata an toàn bằng `jq`:

~~~bash
curl --fail --silent --show-error \
  https://config.internal.example/orders-service/prod/orders-prod-2026.10.28 \
  | jq '{name, profiles, label, version, sources: [.propertySources[].name]}'
~~~

Trường `version` có ý nghĩa với Git backend. Với Vault, native hoặc backend khác, cần dùng version identifier riêng; không giả định mọi repository đều trả cùng metadata Git.

## 7. Kiểm tra từng Config Server replica

Nếu có nhiều Config Server sau load balancer, một request qua địa chỉ chung không đủ chứng minh tất cả node đã đồng bộ. Gọi trực tiếp từng node:

~~~bash
curl --fail --silent --show-error \
  http://config-server-a.internal:8888/orders-service/prod/orders-prod-2026.10.28

curl --fail --silent --show-error \
  http://config-server-b.internal:8888/orders-service/prod/orders-prod-2026.10.28
~~~

So sánh `version`, `label`, `profiles` và danh sách property source. Nếu node A đã fetch commit revert còn node B vẫn trả revision cũ, rút node B khỏi load balancer hoặc đánh dấu unready cho đến khi fetch thành công và parity được xác nhận.

Nếu node chưa thấy commit mới, kiểm tra Git URI, credential, network, TLS, `basedir`, log fetch và `refresh-rate`. Không sửa file trong local clone bằng tay để ép kết quả. Local clone là dữ liệu làm việc của backend; hãy để Git remote là nguồn có thẩm quyền.

## 8. Kích hoạt Config Client nạp lại cấu hình

Sau khi Config Server đã trả đúng revision rollback, client cần nạp lại Environment.

Có ba cách thường gặp:

| Cách | Phạm vi | Khi dùng |
| --- | --- | --- |
| `POST /actuator/refresh` | Một Config Client instance | Kiểm thử hoặc refresh thủ công một instance |
| `POST /actuator/busrefresh` | Các ứng dụng tham gia Spring Cloud Bus, theo cơ chế định tuyến của phiên bản | Refresh diện rộng hoặc theo destination được hỗ trợ |
| Rolling restart/rollout | Instance được triển khai lại | Bean hoặc thành phần không hỗ trợ refresh an toàn |

Refresh một instance:

~~~bash
curl --fail --silent --show-error -X POST \
  https://orders-1.internal/actuator/refresh
~~~

Phát refresh qua Bus từ một ứng dụng đã tham gia Bus:

~~~bash
curl --fail --silent --show-error -X POST \
  https://orders-1.internal/actuator/busrefresh
~~~

Các endpoint cần được expose, xác thực và phân quyền trước khi gọi. Không mở chúng công khai. Nếu hệ thống dùng webhook `/monitor`, webhook có thể phát refresh event sau commit revert; xác nhận event đã được nhận trước khi gửi thêm một lần bus refresh để tránh refresh trùng không cần thiết.

Refresh cập nhật Environment và làm mới các bean hỗ trợ rebind hoặc refresh scope. Nó không phải một giao dịch nguyên tử cho mọi bean. Nếu thuộc tính được capture lúc khởi tạo trong một singleton không hỗ trợ refresh, hoặc thành phần cần restart để áp dụng, phải rollout lại instance.

## 9. Xác minh giá trị hiệu lực trong Config Client

Config Server trả đúng revision chưa có nghĩa client đã áp dụng. Trên từng client instance, kiểm tra Environment bằng Actuator:

~~~bash
curl --fail --silent --show-error \
  https://orders-1.internal/actuator/env/orders.http.read-timeout
~~~

Endpoint `/actuator/env/{property}` có thể cho biết giá trị và property source đang cung cấp key, tùy phiên bản Spring Boot và cấu hình sanitization. Kiểm tra cả:

- Giá trị hiệu lực hiện tại.
- Property source đang thắng.
- Origin hoặc nguồn khai báo nếu có.
- Có biến môi trường, system property hoặc command line ghi đè hay không.

Nếu giá trị khác Config Server, xem danh sách property source và các nguồn ưu tiên cao hơn. Ví dụ `ORDERS_HTTP_READTIMEOUT` có thể ghi đè giá trị remote tùy chính sách override đang cấu hình. Đừng kết luận client đã rollback chỉ vì Config Server trả đúng response.

Actuator `env` có thể tiết lộ tên key, đường dẫn nội bộ hoặc dữ liệu nhạy cảm. Chỉ expose trong mạng quản trị, bật xác thực/phân quyền và giữ sanitization. Không tắt sanitization để xem password; kiểm tra sự hiện diện hoặc xác thực kết nối bằng một thao tác an toàn.

## 10. Kiểm tra bean đã binding giá trị rollback

Nếu ứng dụng dùng `@ConfigurationProperties`, kiểm tra bean đã nhận giá trị mong muốn. Actuator `configprops` có thể hiển thị thông tin binding:

~~~bash
curl --fail --silent --show-error \
  https://orders-1.internal/actuator/configprops
~~~

Ví dụ bean:

~~~java
@ConfigurationProperties(prefix = "orders.http")
public record OrdersHttpProperties(
        Duration connectTimeout,
        Duration readTimeout) {
}
~~~

Với bean thuộc `@RefreshScope`, target cũ được invalidate khi refresh scope được làm mới; target mới được tạo khi proxy được gọi lần tiếp theo. Với bean singleton thông thường, không nên mặc định field đã capture từ Environment sẽ tự thay đổi.

Có thể kiểm tra một thuộc tính không nhạy cảm qua một endpoint nội bộ được bảo vệ hoặc metric có nhãn release ID. Tránh tạo endpoint trả toàn bộ bean cấu hình hoặc secret. Mục tiêu là xác nhận giá trị có hiệu lực, không sao chép dữ liệu bí mật ra ngoài.

## 11. Xác minh hành vi thực tế của ứng dụng

Giá trị trong Environment và bean binding là hai bằng chứng quan trọng, nhưng với thay đổi có ảnh hưởng vận hành, cần kiểm tra cả hành vi.

Ví dụ:

| Loại cấu hình rollback | Kiểm tra hành vi |
| --- | --- |
| Timeout HTTP | Gọi dependency thử nghiệm và kiểm tra timeout/latency trong giới hạn an toàn |
| Retry count | Quan sát số lần thử trong một tình huống lỗi được kiểm soát |
| Feature flag | Gọi luồng chức năng tương ứng và xác nhận nhánh cũ hoạt động |
| Connection pool | Kiểm tra pool metrics và tạo connection mới |
| Database credential | Xác nhận kết nối mới thành công, không in username/password nhạy cảm |
| Log level | Đọc `/actuator/loggers/{logger-name}` và xác nhận mức hiệu lực |
| Rate limit | Gửi request thử với client test và kiểm tra ngưỡng/HTTP 429 |

Không tạo tải lớn hoặc cố tình gây lỗi trên production để kiểm tra. Dùng canary, synthetic check hoặc traffic thử nghiệm có giới hạn. Với secret, xác minh thành công bằng thao tác xác thực, không log giá trị.

## 12. Kiểm tra toàn bộ Config Client instance

Trong hệ thống nhiều replica, cần xác minh từng instance thay vì chỉ gọi qua load balancer. Một instance có thể chưa nhận Bus event, đang offline lúc refresh hoặc vẫn giữ bean cũ.

Có thể dùng release ID an toàn trong cấu hình:

~~~yaml
config:
  release-id: orders-prod-2026.10.28
~~~

Mỗi instance có thể xuất release ID qua metric hoặc endpoint chẩn đoán được bảo vệ. So sánh kết quả với revision đích:

| Instance | Config release ID | Environment | Runtime behavior | Trạng thái |
| --- | --- | --- | --- | --- |
| orders-1 | orders-prod-2026.10.28 | Đúng | Đúng | Đã xác minh |
| orders-2 | orders-prod-2026.10.28 | Đúng | Đúng | Đã xác minh |
| orders-3 | orders-prod-2026.11.03 | Cũ | Chưa xác minh | Cần xử lý |

Nếu một instance không phản hồi hoặc không thể xác minh, không tính nó là đã rollback. Có thể rút instance khỏi load balancer, restart/refresh theo quy trình và kiểm tra lại trước khi đưa trở lại.

## 13. Xử lý khi Config Server đúng nhưng client vẫn sai

Nếu endpoint Config Server trả đúng revision mà client vẫn dùng giá trị mới, kiểm tra lần lượt:

1. Client có thực sự kết nối đúng Config Server cluster không?
2. Client có yêu cầu đúng application, profile và label không?
3. Client đã nhận refresh event hoặc được gọi refresh chưa?
4. Environment trên client có property source remote mới không?
5. Có environment variable, JVM property, command line hoặc local file ghi đè không?
6. Bean có hỗ trợ rebind/refresh không?
7. Thành phần giữ state như DataSource, HTTP client, cache hoặc executor có cần tạo lại không?
8. Client có đang nhận request từ một instance khác chưa rollback không?

Nếu một bean không thể refresh an toàn, dùng rolling restart để bảo đảm tiến trình mới khởi tạo từ revision rollback. Trước khi restart, xác nhận Config Server cluster đã phục vụ đúng revision để instance mới không nạp lại cấu hình lỗi.

## 14. Rollback với Vault, native và composite repository

Git revert chỉ khôi phục phần cấu hình nằm trong Git. Nếu Environment được tổng hợp từ nhiều backend, cần khôi phục từng nguồn.

| Backend | Cách rollback |
| --- | --- |
| Git | Revert commit, dùng immutable tag hoặc commit SHA cũ |
| Native classpath | Triển khai lại image/JAR chứa cấu hình trước |
| Native filesystem | Chuyển mount sang snapshot/thư mục version trước |
| Vault KV v2 | Chọn/ghi lại secret version đã được phê duyệt theo quy trình |
| Composite Git + Vault | Khôi phục cả Git revision và Vault secret version |

Git label không ghim Vault KV version. Một Config Server có thể trả Git revision cũ nhưng vẫn đọc secret mới từ Vault. Release manifest cần ghi nhận version của từng backend để rollback đúng toàn bộ Environment.

Với dynamic Vault secret có lease, không khôi phục một lease đã hết hạn bằng cách chọn Git commit cũ. Cần cấp hoặc renew credential theo lifecycle của Vault, sau đó cập nhật bean/client sử dụng secret. Rollback cấu hình và rollback credential là hai quy trình phối hợp nhưng độc lập.

## 15. Theo dõi sau khi rollback

Sau khi các instance đã nhận cấu hình cũ, theo dõi đủ lâu để phát hiện lỗi xuất hiện trễ:

- Tỷ lệ lỗi HTTP và exception.
- Latency, timeout và retry rate.
- Kết nối database, pool utilization và lỗi xác thực.
- Tỷ lệ request bị giới hạn.
- Log volume sau khi khôi phục log level.
- Revision/release ID trên từng Config Server và Config Client.
- Số instance chưa xác nhận refresh hoặc đang offline.

Giữ lại commit gây lỗi và commit rollback trong lịch sử để phục vụ phân tích. Ghi nhận thời điểm bắt đầu sự cố, thời điểm rollback, thời gian từng instance chuyển revision và tác động đến người dùng. Không xóa log hoặc audit chỉ để làm sạch lịch sử sự cố.

Khi đã ổn định, mở một thay đổi riêng để sửa nguyên nhân gốc và phát hành lại theo quy trình review. Không vội áp dụng lại cấu hình gây lỗi chỉ vì rollback đã thành công.

## 16. Quy trình rollback chuẩn

Một playbook ngắn có thể được dùng trong incident:

1. Xác định application, profile, label, key và revision gây lỗi.
2. Tạm dừng các thay đổi cấu hình mới trong phạm vi ảnh hưởng.
3. Chọn revision trước đã biết là tốt từ manifest release.
4. Revert commit hoặc cập nhật deployment về immutable label cũ.
5. Xác nhận Git remote và Config Server từng node trả đúng revision.
6. Đảm bảo mọi Config Server replica đạt parity trước khi phục vụ client.
7. Gọi refresh một instance canary hoặc triển khai lại canary.
8. Kiểm tra Environment, bean binding và hành vi thực tế trên canary.
9. Refresh qua Bus hoặc rolling restart phần còn lại.
10. Kiểm tra từng Config Client instance và loại instance lệch khỏi load balancer.
11. Theo dõi metric/log, xác nhận hệ thống ổn định.
12. Ghi lại kết quả, revision và thời điểm hoàn tất rollback.

Nếu bước kiểm tra canary thất bại, dừng mở rộng rollout và đánh giá lại revision hoặc phạm vi rollback. Không coi một HTTP 200 từ `/actuator/refresh` hay `/actuator/busrefresh` là bằng chứng cuối cùng.

## 17. Nguyên tắc vận hành

- Ghi lại full commit SHA, label và release ID của mọi lần phát hành.
- Dùng Git revert hoặc immutable tag để khôi phục; tránh force push branch dùng chung.
- Xác nhận Config Server trả đúng revision trước khi refresh client.
- Kiểm tra từng Config Server replica, không chỉ qua load balancer.
- Refresh hoặc restart Config Client theo khả năng cập nhật thực tế của bean.
- Xác minh Environment, property source và giá trị đã bind.
- Kiểm tra hành vi runtime đối với timeout, retry, feature flag, pool và secret.
- Theo dõi từng client instance cho đến khi tất cả đạt revision đích.
- Với composite backend, rollback version của từng nguồn.
- Không để Actuator hoặc response chứa secret bị expose trong quá trình chẩn đoán.
- Chỉ kết thúc incident khi đã xác nhận giá trị thực và hành vi ổn định trên phạm vi instance cần thiết.

Rollback cấu hình hoàn tất khi nguồn đã quay về revision được chọn, Config Server trả đúng nội dung, Config Client đã nhận giá trị đó và thành phần runtime thực sự hoạt động theo cấu hình mong muốn. Ghi nhận revision, kiểm tra từng node và xác minh hành vi giúp nhóm tránh nhầm lẫn giữa “đã revert Git” với “toàn hệ thống đã khôi phục”.

