# Webhook nhận được nhưng không ánh xạ đúng ứng dụng

Webhook có thể tới Config Server thành công nhưng không làm đúng Config Client refresh. Lỗi thường nằm ở bước chuyển đổi đường dẫn file đã thay đổi thành tên ứng dụng đích. Ví dụ, Git provider báo file trong thư mục con của monorepo, tên file khác quy ước application name, hoặc file dùng chung bị hiểu thành cấu hình riêng của một ứng dụng.

Để chẩn đoán, hãy tách luồng thành các bước: xác thực webhook, trích xuất danh sách đường dẫn, lọc đường dẫn, suy ra application/profile, phát sự kiện Bus và để client nhận sự kiện. HTTP 2xx chỉ cho biết request đã được endpoint xử lý ở mức HTTP; nó không chứng minh danh sách ứng dụng đích chính xác hoặc client đã refresh.

## 1. Luồng ánh xạ từ webhook tới Config Client

Khi Config Server có dependency **spring-cloud-config-monitor** và Spring Cloud Bus được kích hoạt, endpoint **/monitor** tiếp nhận webhook. Extractor hiểu payload riêng của Git provider và trả về danh sách file paths đã thay đổi. Config Server dùng các path này để xác định ứng dụng cần refresh rồi phát **RefreshRemoteApplicationEvent**.

~~~mermaid
flowchart TD
    A[Git provider webhook] --> B[POST /monitor]
    B --> C{Xác thực chữ ký hoặc token}
    C -->|Không hợp lệ| X[HTTP 403]
    C -->|Hợp lệ| D[PropertyPathNotificationExtractor]
    D --> E[Danh sách changed paths]
    E --> F[Lọc ignored paths và max-paths]
    F --> G[Ánh xạ path thành application targets]
    G --> H[RefreshRemoteApplicationEvent]
    H --> I[Spring Cloud Bus]
    I --> J[Config Client có destination phù hợp]
    J --> K[Client gọi Config Server và refresh]
~~~

Mỗi bước có một kiểu lỗi riêng:

| Bước | Dấu hiệu lỗi | Nơi kiểm tra |
|---|---|---|
| Xác thực webhook | HTTP 403 | Secret, signature/token header, provider validation |
| Trích xuất payload | Không có path hoặc extractor trả null | Event header, payload schema, provider extractor |
| Lọc path | File cấu hình bị bỏ qua hoặc vượt giới hạn | ignored-paths, max-paths, log cảnh báo |
| Ánh xạ application | Trả về sai tên hoặc không có target | Tên file, profile suffix, thư mục repository, application name |
| Phát Bus event | Có target nhưng client không nhận | Bus dependency, broker, Bus ID, destination |
| Client refresh | Client nhận sự kiện nhưng giá trị không đổi | Application/profile/label, Config Server response, bean refresh |

Không kết luận lỗi mapping chỉ từ việc không thấy giá trị mới trong bean. Trước hết phải xác nhận endpoint đã trích xuất path nào và đã tính ra target application nào.

## 2. Phân biệt tên file cấu hình với application name

Config Server phục vụ Environment theo ba tham số:

- **application**: mặc định lấy từ **spring.application.name** của client.
- **profile**: các profile đang hoạt động, thường lấy từ **spring.profiles.active**.
- **label**: branch, tag hoặc commit của backend có hỗ trợ version label.

Client có thể ghi đè các giá trị request bằng **spring.cloud.config.name**, **spring.cloud.config.profile** và **spring.cloud.config.label**. Vì vậy, khi webhook nhắm một application, cần so sánh tên target với định danh thực tế mà client dùng để tham gia Bus; đừng chỉ nhìn tên file hoặc URL repository.

Ví dụ client:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    active: production
  cloud:
    config:
      name: order-service
      profile: production
      label: main
~~~

Client này có service application name là **order-service** và yêu cầu Config Server trả cấu hình cho application **order-service**, profile **production**, label **main**.

Nếu đặt **spring.cloud.config.name** thành danh sách nhiều tên, chẳng hạn tên ứng dụng cộng thêm một nhóm cấu hình dùng chung, thì đó là danh sách tên nguồn cấu hình client yêu cầu. Nó không tự biến tên file dùng chung thành Bus destination cho tất cả client tiêu thụ file đó. Hãy kiểm tra riêng:

1. **spring.application.name** của tiến trình client.
2. **spring.cloud.config.name** được dùng khi gọi Config Server.
3. Tên target mà **/monitor** trả về.
4. Destination và Bus ID của client.

Không đặt application name bắt đầu bằng tiền tố dành riêng **application-**; tài liệu Config Client cảnh báo cách đặt tên này có thể gây vấn đề khi phân giải property source.

## 3. Quy tắc mặc định: tên file gợi ý ứng dụng đích

Với Git, SVN hoặc native repository, Config Server mặc định dùng tên file để suy ra ứng dụng bị ảnh hưởng. Ví dụ:

- **order-service.yml** nhắm application **order-service**.
- **application.yml** là cấu hình chung, nhắm tất cả ứng dụng.
- **application-production.yml** là cấu hình chung cho profile production.
- **order-service-production.yml** là file riêng cho application **order-service** và profile production.

Quy tắc này dựa trên tên file và quy ước application/profile. Webhook không đọc nội dung YAML để tìm **spring.application.name**; nó dựa vào đường dẫn file được extractor trả về.

### Ví dụ mapping cơ bản

| File thay đổi | Target dự kiến | Ý nghĩa |
|---|---|---|
| order-service.yml | order-service | Cấu hình mặc định của order-service |
| order-service-production.yml | order-service:production và có thể có candidate theo quy tắc tên file của phiên bản | Cấu hình riêng theo profile |
| inventory-service.yml | inventory-service | Cấu hình mặc định của inventory-service |
| application.yml | * | Cấu hình dùng chung cho tất cả ứng dụng |
| application-production.yml | *:production | Cấu hình chung theo profile production |

Ký hiệu * là wildcard destination, không phải tên một service cụ thể. Nó có thể làm nhiều client nhận sự kiện. Vì vậy, nếu một file chỉ dùng cho một nhóm ứng dụng, không nên đặt nó theo tên file toàn cục application trừ khi muốn refresh rộng.

## 4. Dấu gạch nối có thể tạo nhiều candidate application/profile

Tên file profile-specific dùng dấu gạch nối để phân tách application và profile, ví dụ **order-service-production.yml**. Nhưng application name cũng thường chứa dấu gạch nối. Endpoint monitor phải suy đoán ranh giới giữa hai phần.

Trong các phiên bản có logic **guessServiceName**, một path như **foo-local-dev.yml** có thể tạo nhiều candidate:

| Path | Candidate có thể được suy ra |
|---|---|
| foo.yml | foo |
| application.yml | * |
| application-local.yml | *:local |
| foo-local.yml | foo:local, foo-local |
| foo-local-dev.yml | foo:local-dev, foo-local:dev, foo-local-dev |

Điều này giúp hỗ trợ cả tên ứng dụng và profile có dấu gạch nối, nhưng có thể phát nhiều event hơn dự kiến. Một file **order-service-production.yml** có thể bị hiểu theo nhiều cách nếu hệ thống có các application name gần giống nhau.

Khi gặp refresh nhầm:

1. Xem danh sách target mà **/monitor** trả về.
2. Đối chiếu từng candidate với **spring.application.name** của client đang chạy.
3. Kiểm tra profile suffix có nằm trong danh sách profile thật của hệ thống hay không.
4. Nếu application name chứa dấu gạch nối và quy tắc suy đoán không đủ chính xác, dùng quy ước tên file rõ ràng hoặc triển khai mapping tùy chỉnh.

Không giả định một file có dấu gạch nối chỉ tạo ra một target. Hành vi chi tiết có thể thay đổi theo phiên bản Spring Cloud Config; hãy kiểm thử bằng đúng release train đang triển khai.

## 5. Repository dùng thư mục con hoặc monorepo

Một lỗi phổ biến là tổ chức cấu hình theo thư mục:

~~~text
config-repo/
├── services/
│   ├── order-service/
│   │   └── application.yml
│   └── inventory-service/
│       └── application.yml
└── shared/
    └── application.yml
~~~

Đường dẫn Git provider gửi có thể là:

~~~text
services/order-service/application.yml
~~~

Trong khi đó, logic mặc định của monitor suy ra target từ tên file. Nếu tên file cuối cùng là **application.yml**, nó có thể bị hiểu là cấu hình chung và tạo wildcard *, dù thư mục cha là order-service.

Đây là khác biệt quan trọng giữa:

- **Cách Config Server tìm file:** có thể dùng search path, thư mục hoặc placeholder {application}.
- **Cách Config Monitor suy ra client cần refresh:** dựa trên changed path và quy tắc target của monitor.

Hai cơ chế này không tự động dùng chung một bảng ánh xạ thư mục. Config Server có thể đọc đúng file trong services/order-service/, nhưng monitor vẫn suy ra sai application từ basename application.yml.

### Cách khắc phục

- Dùng tên file mang application rõ ràng, ví dụ **order-service.yml** và **order-service-production.yml**.
- Nếu giữ cấu trúc thư mục, tạo một mapping tường minh từ repository path sang application target.
- Dùng custom endpoint hoặc lớp phát **RefreshRemoteApplicationEvent** nếu cần target chính xác theo metadata thư mục.
- Viết integration test cho cả file trong thư mục con và file dùng chung.

Không nên đổi tất cả application.yml thành file riêng chỉ để tránh wildcard nếu các ứng dụng thực sự cần kế thừa cấu hình chung. Hãy giữ ý nghĩa của cấu hình dùng chung và sửa lớp mapping.

## 6. File dùng chung không đồng nghĩa với nhóm consumer

Giả sử nhiều client khai báo thêm tên cấu hình common:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      name: order-service,common
~~~

Client có thể đọc property source từ common.yml, nhưng webhook thay đổi common.yml có thể suy ra target là application common. Nếu không có client nào mang Bus application name common, các client thực tế đang tiêu thụ file đó có thể không nhận refresh.

Có ba cách thiết kế:

1. Đưa key thực sự dùng chung vào application.yml để thay đổi tạo wildcard refresh.
2. Dùng custom mapping để ánh xạ common.yml tới danh sách consumer đã đăng ký.
3. Dùng endpoint phát sự kiện có target pattern rõ ràng cho nhóm ứng dụng cần refresh.

Nếu chỉ một nhóm service dùng common.yml, wildcard toàn fleet có thể gây refresh thừa. Trong trường hợp đó, mapping consumer rõ ràng thường phù hợp hơn.

## 7. Kiểm tra payload và PropertyPathNotificationExtractor

Các Git provider không gửi payload giống nhau. GitHub thường gửi header **X-GitHub-Event: push** và JSON body có danh sách commit. GitLab, Gitea, Gitee, Gogs và Bitbucket có header hoặc cấu trúc payload riêng.

Spring Cloud Config Monitor hỗ trợ extractor cho các provider phổ biến. Extractor nhận headers và payload, sau đó trả về **PropertyPathNotification** chứa danh sách changed paths. Interface **PropertyPathNotificationExtractor** cho phép thay thế hoặc bổ sung cách diễn giải payload.

Khi event tới nhưng không có target, kiểm tra:

- Provider có gửi đúng loại event, ví dụ push, không phải issue/comment event.
- Header event có đúng tên và đúng giá trị theo provider.
- Payload có chứa commit hoặc change records không.
- Extractor có đọc cả file added, modified và removed không.
- Có nhiều commit trong một delivery nhưng extractor chỉ đọc commit đầu tiên không.
- Có xử lý rename theo cả path cũ và path mới không.
- Extractor có loại bỏ path trùng mà vẫn giữ thứ tự kiểm tra được không.

Nếu extractor trả về danh sách rỗng, endpoint không có đường dẫn để suy ra application. Nếu extractor trả path không đúng, endpoint có thể nhắm sai service hoặc wildcard.

## 8. Mẫu custom extractor cho payload GitHub

Ví dụ dưới đây minh họa extractor chỉ xử lý GitHub push và lấy các path được thêm, sửa hoặc xóa. Spring Cloud Config đã có extractor GitHub tích hợp; chỉ cần viết extractor riêng khi payload đã tùy biến hoặc cần chuẩn hóa dữ liệu theo quy ước nội bộ.

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.cloud.config.monitor.PropertyPathNotification;
import org.springframework.cloud.config.monitor.PropertyPathNotificationExtractor;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class LabGitHubPathExtractor implements PropertyPathNotificationExtractor {

    @Override
    public PropertyPathNotification extract(
            HttpHeaders headers,
            Map<String, Object> payload) {

        if (!"push".equalsIgnoreCase(headers.getFirst("X-GitHub-Event"))) {
            return null;
        }

        Object rawCommits = payload.get("commits");
        if (!(rawCommits instanceof Collection<?> commits)) {
            return null;
        }

        Set<String> paths = new LinkedHashSet<>();
        for (Object rawCommit : commits) {
            if (!(rawCommit instanceof Map<?, ?> commit)) {
                continue;
            }

            for (String field : List.of("added", "modified", "removed")) {
                Object rawPaths = commit.get(field);
                if (!(rawPaths instanceof Collection<?> values)) {
                    continue;
                }

                for (Object value : values) {
                    if (value instanceof String path && !path.isBlank()) {
                        paths.add(path);
                    }
                }
            }
        }

        if (paths.isEmpty()) {
            return null;
        }
        return new PropertyPathNotification(paths.toArray(String[]::new));
    }
}
~~~

Các điểm cần giữ:

- Extractor chỉ xử lý đúng provider/event mà nó hiểu.
- Trả null khi payload không thuộc extractor để extractor khác có cơ hội xử lý.
- Không giả định mọi commit payload đều có đủ ba collection added/modified/removed.
- Thu thập cả file bị xóa; xóa file cũng có thể làm thay đổi Environment.
- Dùng tập có thứ tự để kết quả test và log ổn định.
- Không tin path từ payload để truy cập filesystem tùy ý.

Extractor ở trên chỉ chuẩn hóa payload thành danh sách đường dẫn. Nó chưa thay đổi quy tắc suy ra application của **PropertyPathEndpoint**.

## 9. Mapping tùy chỉnh cho monorepo

Nếu repository tổ chức file theo thư mục và basename không thể hiện application, cần một bảng ánh xạ có chủ đích. Ví dụ:

~~~text
services/order-service/config/application.yml
services/inventory-service/config/application.yml
shared/payment/application.yml
~~~

Một bảng mapping có thể là:

| Repository path | Application target |
|---|---|
| services/order-service/config/application.yml | order-service |
| services/inventory-service/config/application.yml | inventory-service |
| shared/payment/application.yml | order-service, checkout-service |

Có hai hướng triển khai:

**Chuẩn hóa path trước khi đưa vào endpoint mặc định:** custom extractor có thể biến các path đã xác thực thành tên file canonical như order-service.yml, nếu quy ước và hành vi của endpoint hiện tại hỗ trợ chính xác cách này. Phải kiểm thử để chắc chắn không tạo thêm candidate ngoài ý muốn.

**Tự triển khai lớp mapping và phát event:** tạo endpoint/handler riêng nhận **PropertyPathNotification**, tra bảng path-to-application, rồi phát **RefreshRemoteApplicationEvent** cho đúng target. Cách này phù hợp khi một path ánh xạ tới nhiều consumer, có thư mục lồng nhau hoặc có quy tắc theo repository/ref.

Không nên sửa **PropertyPathEndpoint** bằng cách copy mã nguồn của một phiên bản cũ rồi giữ lâu dài mà không theo dõi nâng cấp. Nếu cần thay đổi endpoint mặc định, phải pin phiên bản, viết test tương thích và kiểm tra khác biệt khi nâng Spring Cloud Config.

## 10. Dùng form path để kiểm tra target độc lập với Git provider

Spring Cloud Config cho phép POST form-encoded tới **/monitor** với tham số **path={application}**. Giá trị này là application pattern, có thể chứa wildcard; nó không phải Git file path.

Ví dụ nhắm một client:

~~~bash
curl --include \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data "path=order-service" \
  http://localhost:8888/monitor
~~~

Ví dụ nhắm mọi ứng dụng:

~~~bash
curl --include \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data "path=*" \
  http://localhost:8888/monitor
~~~

Đây là phép thử hữu ích để tách lỗi:

- Nếu POST path=order-service tạo target đúng và client refresh, Bus có thể hoạt động; hãy tập trung kiểm tra provider payload/extractor/file-path mapping.
- Nếu form path cũng không tạo refresh, kiểm tra Bus, destination, bảo mật endpoint và client subscription.
- Nếu response trả target đúng nhưng chỉ một số replica refresh, kiểm tra Bus consumer và trạng thái từng instance.

Endpoint này vẫn phải được bảo vệ. Không mở **/monitor** công khai hoặc cho phép người không tin cậy gửi wildcard refresh.

## 11. Kiểm tra ignored paths và giới hạn số path

Config Server hỗ trợ bỏ qua các path bằng **spring.cloud.config.server.monitor.ignored-paths**. Mỗi regular expression được so khớp với toàn bộ webhook path. Path bị ignore sẽ bị loại trước khi xác định application cần refresh.

Ví dụ:

~~~yaml
spring:
  cloud:
    config:
      server:
        monitor:
          ignored-paths:
            - "docs/.*"
            - ".*\\.md"
            - "scripts/.*"
          max-paths: 50
~~~

Mặc định Config Server xử lý tối đa 20 paths trong một notification. Nếu push chứa nhiều hơn giới hạn, các path còn lại không được xử lý và warning được ghi log. Một file cấu hình ở vị trí sau danh sách có thể bị bỏ qua dù webhook payload có chứa file đó.

Khi chỉ một ứng dụng không refresh trong commit lớn:

1. Đếm số changed paths trong payload.
2. Kiểm tra **max-paths**.
3. Tìm warning về path vượt giới hạn.
4. Kiểm tra regex **ignored-paths** có khớp cả path thư mục con hoặc tên file không.
5. Tạm tăng giới hạn trong staging để xác nhận nguyên nhân.

Không tăng **max-paths** vô hạn mà không đánh giá tải Bus và số client bị ảnh hưởng. Tốt hơn là loại tài liệu/build files và chia nhỏ change set nếu phù hợp.

## 12. Kiểm tra target từ response của /monitor

Khi POST webhook, Config Server có thể trả danh sách application target được suy ra. Đây là bằng chứng hữu ích nhất để xác nhận mapping trước khi điều tra client.

Ví dụ response mong muốn cho file order-service-production.yml có thể là:

~~~json
[
  "order-service:production"
]
~~~

Nếu response là:

~~~json
[
  "*"
]
~~~

thì endpoint đang coi path là file chung hoặc extractor đã trả một path không mang tên ứng dụng.

Nếu response chứa:

~~~json
[
  "order-service:production",
  "order-service-production",
  "order"
]
~~~

hãy xác minh các candidate này có phải do quy tắc phân tích dấu gạch nối của phiên bản đang dùng hay không. Danh sách target không nên được suy ra từ tên file bằng cảm tính; cần chạy test với đúng endpoint và phiên bản.

Một response rỗng thường cho thấy extractor không tạo notification, path không tạo ra target hoặc endpoint không phát được sự kiện theo cấu hình hiện tại. Hãy đọc log để xác định bước nào đã dừng.

HTTP 200 với danh sách target đúng vẫn chưa chứng minh client đã refresh. Cần kiểm tra log phát Bus event, broker và client event listener.

## 13. Xác minh Bus và định danh client

**RefreshRemoteApplicationEvent** chỉ được truyền qua Spring Cloud Bus khi Bus được kích hoạt ở cả Config Server và ứng dụng client. Nếu webhook mapping đúng nhưng client không nhận sự kiện, kiểm tra:

- Config Server có Bus starter và cấu hình broker đúng không.
- Config Client có Bus starter tương ứng và kết nối cùng broker không.
- Bus ID của mỗi instance có duy nhất và ổn định theo quy ước không.
- Destination trong event có khớp **spring.application.name** của client không.
- Event có bị giới hạn theo destination hoặc namespace không.
- Broker có lỗi publish/consume, queue binding hoặc ACL không.
- Client có log nhận **RefreshRemoteApplicationEvent** không.

Đừng nhầm tên cấu hình mà client đọc với tên client nhận event. Một service có thể đọc **application.yml** và **common.yml**, nhưng Bus destination vẫn cần nhắm đúng service instance/application.

## 14. Xác minh Config Server thực sự có cấu hình mới

Ngay cả khi client nhận đúng refresh event, client vẫn có thể nhận giá trị cũ nếu Config Server đang phục vụ branch, label hoặc cache cũ.

Gọi trực tiếp endpoint Environment:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8888/order-service/production/main
~~~

Kiểm tra:

- Application trong URL có đúng tên client yêu cầu không.
- Profile có đúng profile đang hoạt động không.
- Label có đúng branch/tag/commit vừa cập nhật không.
- **propertySources** có file mới và giá trị mong đợi không.
- Git backend đã fetch commit mới chưa.
- Client có cấu hình **spring.cloud.config.name** hoặc label riêng làm request khác không.

Nếu Environment response đã đúng nhưng client vẫn dùng giá trị cũ, chuyển sang kiểm tra event nhận được, refresh lifecycle và bean. Nếu response đã cũ, xử lý Git fetch/cache/label trước khi gửi refresh lặp lại.

## 15. Phân biệt lỗi xác thực với lỗi ánh xạ

Các phiên bản Spring Cloud Config hiện hành có webhook secret validation theo provider. Nếu signature/token không hợp lệ, **/monitor** có thể trả HTTP 403 trước khi extractor xử lý path. Một request bị từ chối không phải lỗi mapping application.

| Kết quả | Hướng chẩn đoán |
|---|---|
| HTTP 403 | Xác minh provider secret, signature/token header và validation settings |
| HTTP 2xx, response target rỗng | Kiểm tra event header, payload extractor, changed paths, ignored paths và tên file |
| HTTP 2xx, response target sai | Kiểm tra quy tắc filename/profile, thư mục con, dấu gạch nối và mapping tùy chỉnh |
| HTTP 2xx, target đúng, không client nào refresh | Kiểm tra Bus trên server/client, broker và destination |
| Chỉ một phần client refresh | Kiểm tra target pattern, Bus consumer, client app name và replica health |
| Client refresh nhưng giá trị không đổi | Kiểm tra Config Server Environment, label, Git fetch và property source precedence |

Không tắt xác thực webhook để xử lý lỗi mapping. Hãy dùng một payload kiểm thử có chữ ký hợp lệ hoặc POST form path trong mạng quản trị được bảo vệ.

## 16. Kiểm thử mapping tự động

Mỗi quy ước repository nên có test cho path → target. Bộ test tối thiểu cần bao gồm:

| Input path | Target mong đợi |
|---|---|
| order-service.yml | order-service |
| order-service-production.yml | Target profile production đã thống nhất |
| application.yml | Wildcard toàn ứng dụng |
| application-production.yml | Wildcard profile production |
| services/order-service/application.yml | Target order-service nếu dùng mapping monorepo tùy chỉnh |
| docs/README.md | Không có refresh target |
| scripts/build.yml | Không có refresh target nếu bị ignore |
| order-service-production.yml đã xóa | Vẫn phải tạo refresh target cho ứng dụng bị ảnh hưởng |

Test extractor nên kiểm tra:

- Header event đúng/sai.
- Payload thiếu commits.
- Một delivery có nhiều commit.
- File added, modified, removed.
- Path trùng lặp.
- Path có thư mục con.
- Path không thuộc repository cấu hình.
- Số lượng path vượt max-paths.

Test mapping nên kiểm tra:

- Tên application có dấu gạch nối.
- Profile có dấu gạch nối.
- Tên file application dùng chung.
- Tên file profile-specific.
- Case sensitivity và dấu phân cách.
- Tất cả target trả về phải thuộc allowlist application đã biết.

Không chỉ assert extractor trả về đúng path. Cần có integration test gọi **PropertyPathEndpoint** hoặc endpoint monitor thật để xác nhận danh sách application cuối cùng.

## 17. Quy trình xử lý sự cố theo thứ tự

Khi nhận báo cáo webhook đã tới nhưng sai ứng dụng refresh, thực hiện theo thứ tự:

1. Ghi nhận delivery ID, repository, ref, event type và thời điểm.
2. Kiểm tra HTTP status và xác thực webhook.
3. Lấy payload đã loại bỏ secret/token; xác nhận changed paths.
4. Kiểm tra extractor có trả đủ path added/modified/removed không.
5. Kiểm tra ignored-paths và max-paths.
6. Xem danh sách target trả về từ /monitor.
7. So sánh target với spring.application.name và Bus ID của client.
8. Nếu target sai, sửa naming convention hoặc mapping monorepo.
9. Nếu target đúng, kiểm tra Bus publish/consume và broker.
10. Nếu client nhận event, gọi Config Server Environment endpoint để xác minh cấu hình mới.
11. Xác nhận bean/runtime đã áp dụng giá trị mới; nếu cần, xử lý refresh scope hoặc restart.
12. Lưu regression test cho payload và mapping đã gây sự cố.

Không gửi lại webhook nhiều lần trước khi biết target đang sai ở bước nào. Nếu mapping sai, retry chỉ lặp lại cùng một event sai.

## 18. Ma trận triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| Webhook HTTP 403 | Secret hoặc signature sai | Cấu hình đúng cơ chế xác thực của provider |
| HTTP 2xx nhưng target rỗng | Header event không được extractor nhận diện hoặc payload thiếu commit paths | Kiểm tra provider event, extractor và fixture payload |
| File trong thư mục service tạo wildcard | Basename là application.yml | Dùng mapping monorepo hoặc canonical application filename |
| File common.yml chỉ nhắm service common | Tên nguồn dùng chung bị hiểu là client application | Map tới consumer cụ thể hoặc dùng application-wide config |
| Một file có dấu gạch nối refresh nhiều app | Endpoint tạo nhiều candidate application/profile | Dùng quy ước tên rõ ràng hoặc mapping tùy chỉnh |
| File bị ignore | Regex khớp toàn bộ webhook path | Sửa regex sau khi kiểm tra full path |
| Chỉ một số file trong push được xử lý | Vượt max-paths | Tăng giới hạn hợp lý hoặc tách change set |
| Target đúng nhưng client không nhận | Bus chưa bật ở client/server hoặc destination sai | Kiểm tra Bus starter, broker và client application name |
| Client nhận event nhưng cấu hình cũ | Config Server chưa fetch đúng commit/label | Xác minh Environment response và Git refresh |
| Chỉ profile production không refresh | Profile suffix hoặc application/profile mapping không đúng | Kiểm tra file name, active profiles và target có profile |
| File bị xóa không refresh | Custom extractor bỏ qua removed | Bổ sung removed paths vào notification |
| Monorepo đổi một file làm mọi service refresh | Extractor trả basename application.yml | Ánh xạ path thư mục sang app target rõ ràng |

## 19. Checklist cấu hình và vận hành

- [ ] Đã xác định webhook provider và đúng loại event cần nhận.
- [ ] spring-cloud-config-monitor được thêm vào Config Server.
- [ ] Spring Cloud Bus được cấu hình ở cả Config Server và client.
- [ ] Webhook secret validation hoạt động và không bị tắt để né lỗi.
- [ ] Extractor nhận đúng header/payload của provider.
- [ ] Extractor thu thập added, modified và removed paths.
- [ ] Repository path được chuẩn hóa theo một quy ước đã tài liệu hóa.
- [ ] File chung application*.yml được hiểu là wildcard có chủ đích.
- [ ] Tên application và profile trong file khớp với client.
- [ ] Đã kiểm thử tên application/profile có dấu gạch nối.
- [ ] Đã kiểm tra thư mục con/monorepo không làm basename biến thành wildcard ngoài ý muốn.
- [ ] ignored-paths không loại file cấu hình hợp lệ.
- [ ] max-paths đủ cho kích thước commit thường gặp và có cảnh báo khi vượt giới hạn.
- [ ] Danh sách target của /monitor được kiểm tra trong test.
- [ ] Target khớp spring.application.name/Bus destination của client.
- [ ] Config Server Environment endpoint trả đúng application/profile/label.
- [ ] Có log correlation từ delivery ID tới target, Bus event và client refresh.
- [ ] Không log webhook secret, signature, access token hoặc nội dung secret.

## 20. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Mô tả luồng từ webhook payload qua extractor tới application target và Bus event.
- Phân biệt webhook được nhận với webhook được ánh xạ đúng ứng dụng.
- Giải thích quy tắc mặc định dùng tên file để suy ra application và profile.
- Nhận diện ảnh hưởng của application.yml, profile suffix, dấu gạch nối và thư mục con.
- Phân biệt spring.application.name với spring.cloud.config.name.
- Dùng response /monitor để kiểm tra danh sách target.
- Viết custom PropertyPathNotificationExtractor cho payload tùy chỉnh.
- Thiết kế mapping riêng cho monorepo và file dùng chung.
- Kiểm tra ignored paths, max paths, Bus destination và client refresh.
- Xây dựng regression test cho các path mapping dễ gây refresh nhầm.

**Tự kiểm tra:** Repository có file services/order-service/config/application-production.yml. Webhook được xác thực và endpoint /monitor trả HTTP 200 nhưng danh sách target là *. Client có spring.application.name=order-service và đang chạy profile production. Hãy giải thích vì sao basename có thể dẫn tới wildcard, các bước xác minh extractor/path mapping, hai cách sửa phù hợp cho monorepo, và cách chứng minh chỉ order-service nhận refresh.

## Tài liệu tham khảo

- [Spring Cloud Config — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/server/push-notifications-and-bus.html)
- [Spring Cloud Config — Environment Repository and Application/Profile Mapping](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Cloud Config Client — Application, Profile and Label](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config — PropertyPathNotificationExtractor interface](https://github.com/spring-cloud/spring-cloud-config/blob/main/spring-cloud-config-monitor/src/main/java/org/springframework/cloud/config/monitor/PropertyPathNotificationExtractor.java)
- [Spring Cloud Config — PropertyPathEndpoint implementation](https://github.com/spring-cloud/spring-cloud-config/blob/main/spring-cloud-config-monitor/src/main/java/org/springframework/cloud/config/monitor/PropertyPathEndpoint.java)
- [Spring Cloud Config — PropertyPathEndpoint tests](https://github.com/spring-cloud/spring-cloud-config/blob/main/spring-cloud-config-monitor/src/test/java/org/springframework/cloud/config/monitor/PropertyPathEndpointTests.java)
