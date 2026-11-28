# Nhiều label: hành vi dự phòng và hỗ trợ theo phiên bản

Trong Spring Cloud Config, `profile` và `label` xác định hai chiều khác nhau của cấu hình. Profile chọn nhóm cấu hình theo ngữ cảnh chạy như `dev`, `staging` hoặc `prod`; label chọn phiên bản của nguồn cấu hình, thường là nhánh, tag hoặc commit trong Git. Khi một ứng dụng cần thử nhiều phiên bản cấu hình, Config Client có thể nhận một danh sách label phân tách bằng dấu phẩy.

Điều cần chú ý là danh sách nhiều label có hai cách hoạt động tùy phiên bản và cấu hình. Cách mặc định cũ thử từng label cho đến khi có một label dùng được. Từ Spring Cloud Config 4.2.0, có thể yêu cầu client gửi toàn bộ danh sách trong một request để Config Server trả về property source của tất cả label. Hai cách này có ý nghĩa khác nhau khi một khóa xuất hiện ở nhiều label, vì vậy cần xác định rõ hành vi trước khi bật chế độ mới.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt profile với label và xác định vai trò của từng giá trị trong request Config Server.
- Giải thích cách Config Client xử lý danh sách label theo chế độ tương thích cũ.
- Sử dụng `spring.cloud.config.send-all-labels` từ Spring Cloud Config 4.2.0 để yêu cầu nhiều label trong một request.
- Xác định điều kiện tương thích giữa phiên bản Config Client và Config Server khi gửi tất cả label.
- Hiểu thứ tự ưu tiên khi nhiều label cùng cung cấp một khóa và kiểm tra kết quả hợp nhất.
- Cấu hình hành vi khi một label bị lỗi, phát hiện branch cũ còn trong bản clone cục bộ và thiết kế phương án dự phòng an toàn.

## 2. Profile và label là hai chiều riêng biệt

Config Server nhận yêu cầu theo dạng:

```text
/{application}/{profile}/{label}
```

- **Application** thường lấy từ `spring.application.name`, ví dụ `order-service`.
- **Profile** thường lấy từ các profile đang hoạt động của Spring Boot, ví dụ `prod`.
- **Label** là phiên bản của repository cấu hình, ví dụ nhánh `main`, tag `release-2026.11` hoặc commit ID.

Ví dụ, request:

```text
GET /order-service/prod/release-2026.11
```

nghĩa là lấy cấu hình của `order-service`, profile `prod`, tại label `release-2026.11`.

Profile quyết định nhóm cấu hình môi trường mà ứng dụng cần. Label quyết định phiên bản của bộ tệp cấu hình được đọc. Đổi profile từ `dev` sang `prod` không đồng nghĩa đổi branch Git; đổi label từ `main` sang một tag cũng không tự đổi profile.

Với Git backend, label có thể là branch, tag hoặc commit ID. Branch phù hợp cho phát triển vì nội dung thay đổi theo commit mới; tag hoặc commit ID phù hợp hơn khi cần tái lập chính xác cấu hình của một lần phát hành. Nếu tên branch có dấu `/`, khi đặt trong URL trực tiếp cần dùng dạng đặc biệt `(_)` theo quy tắc của Config Server, ví dụ `feature/orders` được biểu diễn là `feature(_)orders`.

## 3. Một label: chọn đúng một phiên bản cấu hình

Nếu client chỉ gửi một label, Config Server đọc cấu hình ở phiên bản đó. Ví dụ cấu hình Config Client:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026.11
```

Client yêu cầu cấu hình của `order-service` theo profile đang hoạt động và label `release-2026.11`. Đây là cách dễ kiểm soát khi mỗi môi trường được ghim vào một tag hoặc commit đã duyệt.

Nếu client không gửi label, Config Server dùng label mặc định được cấu hình ở server, chẳng hạn `spring.cloud.config.server.git.default-label` với Git backend. Label mặc định là giá trị dùng khi request không chỉ định label; nó không phải tự động là một mục dự phòng được nối vào mọi danh sách label.

## 4. Nhiều label theo hành vi tương thích cũ

Client có thể khai báo danh sách label phân tách bằng dấu phẩy:

```yaml
spring:
  cloud:
    config:
      label: "feature-orders,develop"
```

Trước Spring Cloud Config 4.2.0, Config Client thử từng label bằng các request riêng đến Config Server. Client dừng khi một label đầu tiên lấy được cấu hình thành công. Nếu `feature-orders` không dùng được, client mới thử `develop`.

Đây là hành vi **dự phòng theo label**:

1. Thử `feature-orders`.
2. Nếu lần lấy cấu hình từ label đó thất bại, thử `develop`.
3. Khi một label thành công, dừng và sử dụng cấu hình từ label đó.

Hai label không được hợp nhất trong chế độ này. Nếu branch `feature-orders` tồn tại và Config Server trả về cấu hình thành công, client không tiếp tục lấy `develop` chỉ vì một khóa nào đó bị thiếu trong branch đầu tiên. Cơ chế này dự phòng việc chọn label, không phải cơ chế tìm từng khóa còn thiếu trong các branch sau.

Ví dụ, nhóm phát triển muốn dùng branch riêng khi branch đó có thể lấy được, nhưng vẫn chạy được trên `develop` khi branch riêng chưa được tạo. Danh sách `feature-orders,develop` phù hợp với ý định đó nếu client đang dùng chế độ thử tuần tự.

## 5. Gửi tất cả label trong một request từ phiên bản 4.2.0

Từ Spring Cloud Config 4.2.0, Config Client có thêm thuộc tính:

```yaml
spring:
  cloud:
    config:
      label: "develop,feature-orders"
      send-all-labels: true
```

Khi bật `spring.cloud.config.send-all-labels: true`, client gửi toàn bộ danh sách label trong một request. Config Server cũng phải chạy Spring Cloud Config 4.2.0 trở lên để hiểu danh sách và trả về một response chứa property source của tất cả label.

Ở chế độ này, các label được kết hợp thành nhiều property source. Với Git và SVN backend, label đứng sau có độ ưu tiên cao hơn label đứng trước khi cùng khai báo một khóa. Vì vậy, ví dụ `develop,feature-orders` dùng `develop` làm nền và cho phép `feature-orders` ghi đè các khóa trùng nhau.

Đây là **hợp nhất nhiều nguồn cấu hình**, khác với hành vi thử tuần tự. Một khóa có thể được lấy từ label nền nếu label ghi đè không định nghĩa khóa đó; nếu cả hai định nghĩa cùng khóa, giá trị ở label có độ ưu tiên cao hơn sẽ được dùng.

Thuộc tính `spring.cloud.config.send-all-labels` mặc định là `false`. Khi để mặc định, client vẫn giữ hành vi tương thích cũ và có thể làm việc với Config Server phiên bản trước 4.2.0.

## 6. Ma trận tương thích Client và Server

Việc gửi tất cả label cần kiểm tra cả phiên bản client lẫn server:

| Config Client | `send-all-labels` | Config Server | Hành vi |
| --- | --- | --- | --- |
| Trước 4.2.0 | Không có thuộc tính này | Bất kỳ phiên bản tương thích | Client thử từng label qua các request riêng; dừng ở label đầu tiên thành công |
| 4.2.0 trở lên | `false` hoặc không khai báo | Trước hoặc từ 4.2.0 | Giữ hành vi thử tuần tự để tương thích |
| 4.2.0 trở lên | `true` | 4.2.0 trở lên | Client gửi một request; server trả property source của tất cả label |
| 4.2.0 trở lên | `true` | Trước 4.2.0 | Không tương thích: server có thể xem chuỗi có dấu phẩy như một label duy nhất và không tách danh sách |

Không bật `send-all-labels` trước khi xác nhận phiên bản server. Nếu triển khai nhiều Config Server instance, hãy bảo đảm tất cả instance phục vụ client đều đã nâng cấp lên phiên bản hỗ trợ trước khi chuyển client sang chế độ gửi toàn bộ label.

## 7. Thứ tự label quyết định giá trị ghi đè

Khi dùng chế độ gửi tất cả label, thứ tự danh sách có ý nghĩa. Với Git và SVN backend, label sau ghi đè label trước đối với cùng một thuộc tính.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      label: "develop,feature-orders"
      send-all-labels: true
```

Giả sử cả hai label đều có khóa `order.retry.max-attempts`:

```yaml
# Trong label develop
order:
  retry:
    max-attempts: 2
```

```yaml
# Trong label feature-orders
order:
  retry:
    max-attempts: 4
```

Khi server hợp nhất các nguồn, giá trị `4` từ `feature-orders` có ưu tiên cao hơn giá trị `2` từ `develop`. Nếu `feature-orders` không khai báo một khóa khác, ví dụ `order.retry.backoff`, khóa đó vẫn có thể được lấy từ nguồn `develop`.

Do đó, khi chuyển từ chế độ thử tuần tự sang gửi tất cả label, không chỉ thêm `send-all-labels: true`. Cần xem lại thứ tự danh sách và các khóa trùng nhau. Với cùng danh sách `feature-orders,develop`, chế độ cũ dùng nguyên cấu hình `feature-orders` nếu nó thành công; chế độ mới cho phép `develop` ghi đè những khóa trùng của `feature-orders`.

## 8. Cấu hình server khi một label bị lỗi

Khi Config Server nhận request chứa nhiều label, server phải đọc từng label để tạo các property source. Với Git/SVN backend, nếu việc lấy một label gặp lỗi, hành vi mặc định là server trả lỗi mà không tiếp tục thử các label còn lại.

Nếu muốn server bỏ qua lỗi của một label và tiếp tục xử lý các label còn lại trước khi quyết định trả lỗi, có thể bật thuộc tính tương ứng trên Config Server.

Ví dụ với Git backend:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          continue-on-multiple-label-failure: true
```

Thuộc tính tương ứng với SVN backend là:

```yaml
spring:
  cloud:
    config:
      server:
        svn:
          continue-on-multiple-label-failure: true
```

Mặc định giá trị này là `false`. Thuộc tính có trong tài liệu Spring Cloud Config 4.2.x trở lên cho Git/SVN backend; hãy kiểm tra reference documentation đúng phiên bản trước khi dùng. Chỉ bật khi chính sách của nhóm cho phép bỏ qua label lỗi. Nếu một label bắt buộc cho phát hành bị sai tên hoặc không truy cập được, trả lỗi sớm có thể an toàn hơn việc âm thầm dùng cấu hình từ label khác.

Khi bật chế độ tiếp tục, hãy giám sát log và kiểm tra response để biết label nào đã được sử dụng. Không coi việc request thành công là bằng chứng rằng mọi label trong danh sách đều đã được đọc thành công.

## 9. Ví dụ cấu hình hoàn chỉnh ở Client và Server

### Config Client

Ví dụ dưới đây dùng Config Data API và chế độ hợp nhất nhiều label:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: "develop,feature-orders"
      send-all-labels: true
```

Điều kiện để ví dụ hoạt động theo cách hợp nhất là Config Client và Config Server đều dùng Spring Cloud Config 4.2.0 trở lên. Các phiên bản thực tế nên được quản lý qua Spring Cloud BOM tương thích với Spring Boot của dự án.

Nếu muốn giữ chế độ dự phòng cũ, bỏ `send-all-labels` hoặc đặt thành `false`:

```yaml
spring:
  cloud:
    config:
      label: "feature-orders,develop"
      send-all-labels: false
```

### Config Server

Ví dụ cấu hình server dùng Git:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
          continue-on-multiple-label-failure: false
```

`default-label` là label server sử dụng khi client không chỉ định label. `clone-on-start` giúp phát hiện sớm lỗi kết nối hoặc cấu hình repository khi server khởi động. `continue-on-multiple-label-failure` được đặt rõ thành `false` để server trả lỗi khi một label trong request nhiều label không lấy được.

Không đưa username, password, token hoặc private key vào tệp YAML trong Git. Cấp credential cho Config Server qua biến môi trường, secret manager hoặc cơ chế bảo mật của nền tảng triển khai.

## 10. Kiểm tra request và property source

Khi thay đổi danh sách label, hãy kiểm tra trực tiếp API của Config Server trước khi khởi động toàn bộ ứng dụng.

Với một label:

```bash
curl "http://localhost:8888/order-service/prod/develop"
```

Với nhiều label:

```bash
curl "http://localhost:8888/order-service/prod/develop,feature-orders"
```

Response dạng `Environment` cho biết danh sách `propertySources` được trả về. Kiểm tra:

- Request dùng đúng application, profile và label.
- Response chứa các property source mong muốn.
- Tên property source cho thấy nguồn nào đến từ label nào.
- Các khóa trùng nhau có giá trị hiệu lực đúng theo thứ tự ưu tiên.
- Một label không hợp lệ có làm request thất bại theo chính sách server đã chọn hay không.

Sau đó kiểm tra từ phía Config Client bằng endpoint chẩn đoán `Environment` của Spring Boot Actuator nếu được bật và bảo vệ phù hợp. Endpoint chẩn đoán có thể tiết lộ thông tin cấu hình, do đó chỉ cấp quyền truy cập cho người có trách nhiệm và che các giá trị nhạy cảm.

Nếu branch có dấu `/`, khi gọi URL trực tiếp hãy thay dấu `/` trong label bằng `(_)`, ví dụ:

```text
GET /order-service/prod/feature(_)orders
```

Với cấu hình property `spring.cloud.config.label`, hãy xác minh cách client mã hóa label và request thực tế bằng log hoặc công cụ quan sát HTTP phù hợp.

## 11. Branch bị xóa nhưng vẫn còn trong bản clone cục bộ

Config Server dùng Git backend thường duy trì một bản clone cục bộ của repository. Nếu branch bị xóa ở remote, branch đó có thể vẫn còn trong bản clone của Config Server và tiếp tục được resolve cho đến khi bản clone được tái tạo, chẳng hạn khi server khởi động lại, hoặc khi cơ chế dọn branch không còn được theo dõi được bật.

Tình huống này có thể làm danh sách fallback hoạt động khác mong đợi. Ví dụ client gửi:

```yaml
spring:
  cloud:
    config:
      label: "deleted-feature,main"
```

Nhóm đã xóa `deleted-feature` khỏi remote, nhưng Config Server vẫn còn branch cũ trong bản clone. Client có thể lấy cấu hình từ branch cũ thay vì đi tiếp đến `main`.

Với Git backend, có thể cấu hình:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          delete-untracked-branches: true
```

Thiết lập này yêu cầu Config Server xóa các branch cục bộ không còn được theo dõi từ remote khi đồng bộ repository. Hãy đánh giá tác động với chính sách cache và cách triển khai nhiều instance trước khi bật.

## 12. Chọn chiến lược label cho từng môi trường

Không nên dùng cùng một chiến lược label cho mọi môi trường nếu yêu cầu tái lập khác nhau.

| Môi trường | Chiến lược gợi ý | Lý do |
| --- | --- | --- |
| Máy phát triển cá nhân | Branch cá nhân, có thể dự phòng `develop` ở chế độ thử tuần tự | Cho phép thử cấu hình chưa merge |
| Tích hợp | Branch `develop` hoặc label tích hợp đã thống nhất | Các nhóm kiểm thử thay đổi đang được hợp nhất |
| Staging | Tag hoặc commit ứng viên phát hành | Giúp kiểm thử đúng bộ cấu hình dự kiến đưa lên production |
| Production | Tag hoặc commit bất biến đã được duyệt | Tái lập được cấu hình và quay lui chính xác |

Nếu dùng nhiều label để hợp nhất, hãy ghi rõ label nền, label override và thứ tự ưu tiên. Nếu dùng nhiều label làm dự phòng tuần tự, hãy ghi rõ label nào được thử trước và điều kiện nào khiến client chuyển sang label tiếp theo.

Đối với production, tránh để một branch thay đổi liên tục trở thành nguồn ghi đè không được kiểm soát. Khi cần khôi phục, ưu tiên ghim client vào tag hoặc commit đã xác minh, sau đó refresh hoặc rollout theo quy trình vận hành.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Profile và label đều là tên môi trường | Profile chọn nhóm cấu hình; label chọn phiên bản repository |
| Danh sách label luôn hợp nhất các file | Trước 4.2.0 hoặc khi `send-all-labels=false`, client thử từng label và dừng ở label đầu tiên thành công |
| Label đầu tiên luôn ghi đè label sau | Trong chế độ hợp nhất với Git/SVN, label sau có độ ưu tiên cao hơn label trước |
| Client 4.2+ có thể gửi tất cả label đến mọi server | Server cũng cần phiên bản 4.2.0 trở lên để xử lý danh sách trong một request |
| `send-all-labels=true` là mặc định | Giá trị mặc định là `false` |
| Một label lỗi thì server tự động bỏ qua | Với Git/SVN, mặc định server trả lỗi; cần cấu hình `continue-on-multiple-label-failure` để tiếp tục |
| Xóa branch ở remote là client sẽ không còn lấy được branch đó | Bản clone cục bộ của Config Server có thể vẫn giữ branch cũ nếu chưa được dọn |
| Label mặc định là label dự phòng cuối cùng của mọi danh sách | `default-label` được dùng khi request không chỉ định label; không nên xem nó như mục dự phòng tự động trong danh sách |

## 14. Quy trình chuyển từ thử tuần tự sang hợp nhất nhiều label

Khi nâng cấp lên Spring Cloud Config 4.2.0 trở lên và muốn bật `send-all-labels`, hãy thực hiện theo trình tự:

1. Kiểm tra Spring Cloud Config Client và tất cả Config Server instance đều ở phiên bản 4.2.0 trở lên.
2. Xác nhận release train tương thích với dòng Spring Boot đang dùng.
3. Liệt kê mọi nơi khai báo `spring.cloud.config.label` và xác định ý nghĩa hiện tại của từng danh sách.
4. So sánh hành vi cũ (first successful label) với hành vi mới (hợp nhất property source của tất cả label).
5. Kiểm tra các khóa trùng nhau và sắp xếp label theo thứ tự ưu tiên mong muốn.
6. Quyết định cách xử lý khi một label không lấy được; chỉ bật `continue-on-multiple-label-failure` nếu chấp nhận bỏ qua label lỗi.
7. Kiểm tra branch đã xóa còn trong bản clone và chính sách `delete-untracked-branches`.
8. Thử API nhiều label và xác nhận property source, giá trị cuối cùng trong `Environment`.
9. Triển khai trước ở môi trường thử nghiệm, quan sát log và kết quả nạp cấu hình.
10. Ghi lại thay đổi hành vi và thứ tự label trong tài liệu vận hành.

Không chuyển đổi chỉ bằng cách bật một thuộc tính. Cùng một danh sách label có thể tạo ra cấu hình hiệu lực khác nhau khi chuyển từ chế độ thử tuần tự sang chế độ hợp nhất.

## 15. Checklist vận hành nhiều label

- [ ] Đã phân biệt rõ profile và label trong cấu hình client.
- [ ] Đã ghi danh sách label theo đúng thứ tự mong muốn.
- [ ] Đã xác định đang dùng chế độ thử tuần tự hay gửi tất cả label.
- [ ] Nếu bật `send-all-labels`, Config Client và Config Server đều từ 4.2.0 trở lên.
- [ ] Đã kiểm tra các khóa trùng nhau và nguồn có độ ưu tiên cao hơn.
- [ ] Đã chọn chính sách khi một label bị lỗi.
- [ ] Đã kiểm tra branch bị xóa ở remote nhưng còn trong bản clone cục bộ.
- [ ] Đã kiểm tra response `Environment` và property source thực tế.
- [ ] Đã ghim label bất biến cho các môi trường cần tái lập.
- [ ] Đã cập nhật tài liệu và quy trình quay lui khi thay đổi chế độ label.

Nhiều label có thể phục vụ hai nhu cầu khác nhau: dự phòng khi một phiên bản cấu hình không có sẵn, hoặc hợp nhất nhiều lớp cấu hình có thứ tự ưu tiên. Hãy chọn đúng chế độ theo phiên bản Spring Cloud Config, đồng bộ client/server và kiểm tra property source thực tế để ứng dụng nhận đúng cấu hình mong muốn.

## 16. Tài liệu tham khảo

- [Spring Cloud Config Client — Requesting Multiple Labels](https://docs.spring.io/spring-cloud-config/reference/client.html#_requesting_multiple_labels)
- [Spring Cloud Config 4.2 — Client Reference](https://docs.spring.io/spring-cloud-config/reference/4.2/client.html)
- [Spring Cloud Config — Version Control Backend Filesystem Use](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/version-control-backend-filesystem-use.html)
- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
