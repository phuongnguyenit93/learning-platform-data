# Bộ ba application, profile và label trong truy vấn cấu hình

Spring Cloud Config Client lấy cấu hình từ Config Server bằng một yêu cầu xác định ba thông tin: **application**, **profile** và **label**. Ba thành phần này cho Config Server biết cần cấu hình cho ứng dụng nào, trong môi trường nào và tại phiên bản nào của kho cấu hình. Khi tổ chức đúng bộ ba, nhiều ứng dụng Spring Boot có thể dùng chung một Git repository mà vẫn nhận được cấu hình riêng theo dịch vụ, môi trường và lần phát hành.

## 1. Cấu trúc của một truy vấn Config Server

Config Server cung cấp REST endpoint theo dạng:

```text
/{application}/{profile}/{label}
```

Ví dụ:

```text
GET http://config-server:8888/billing-api/prod/release-2026
```

Truy vấn này yêu cầu cấu hình cho ứng dụng `billing-api`, profile `prod`, tại label `release-2026`. Endpoint trả về một đối tượng `Environment` gồm metadata và danh sách `propertySources` mà client có thể nạp vào Spring `Environment`.

| Thành phần | Ý nghĩa | Thuộc tính phía Config Client |
| --- | --- | --- |
| `application` | Tên ứng dụng hoặc nhóm cấu hình cần lấy | `spring.application.name`; có thể ghi đè bằng `spring.cloud.config.name` |
| `profile` | Môi trường hoặc tập profile đang hoạt động | `spring.profiles.active`; có thể ghi đè bằng `spring.cloud.config.profile` |
| `label` | Nhánh, tag hoặc commit của kho cấu hình | `spring.cloud.config.label` |

Nếu không chỉ định tên riêng cho Config Client, `spring.application.name` là tên ứng dụng được dùng để truy vấn. Nếu không có profile đang hoạt động, client thường truy vấn profile `default`. Khi không chỉ định label, Config Server dùng label mặc định do server cấu hình. Không nên dựa vào giá trị mặc định ngầm định giữa các môi trường; hãy khai báo rõ bộ ba khi cần tái lập chính xác cấu hình của một bản phát hành.

## 2. Application: chọn cấu hình theo dịch vụ

`application` định danh ứng dụng cần nhận cấu hình. Giá trị phổ biến là `spring.application.name` trong từng dịch vụ:

```yaml
spring:
  application:
    name: billing-api
```

Với tên này, Config Client yêu cầu các tệp dùng chung và tệp dành cho `billing-api`. Một dịch vụ khác, chẳng hạn `inventory-api`, sẽ gửi tên ứng dụng khác và nhận phần cấu hình tương ứng.

Có thể đặt tên truy vấn riêng bằng `spring.cloud.config.name`. Thuộc tính này hữu ích khi một tiến trình cần lấy cấu hình theo tên khác với tên ứng dụng hiển thị trong hệ thống. Chỉ nên dùng khi có chủ đích rõ ràng, bởi tên truy vấn không khớp với tên tệp trong Git là nguyên nhân thường gặp khiến một ứng dụng nhận thiếu cấu hình.

Ví dụ repository có cấu trúc:

```text
config-repo/
├── application.yml
├── billing-api.yml
├── inventory-api.yml
└── reporting-api.yml
```

`application.yml` cung cấp giá trị dùng chung cho các ứng dụng. Các tệp `billing-api.yml`, `inventory-api.yml` và `reporting-api.yml` chứa cấu hình riêng của từng dịch vụ. Nhờ vậy, những thuộc tính như URL dịch vụ dùng chung hoặc mức log mặc định có thể được quản trị tập trung, còn thông số kết nối riêng vẫn nằm trong tệp của ứng dụng tương ứng.

## 3. Profile: chọn cấu hình theo môi trường

`profile` biểu thị nhóm cấu hình mà ứng dụng đang kích hoạt, thường tương ứng với môi trường như `dev`, `test`, `staging` hoặc `prod`. Client lấy danh sách profile đang hoạt động từ `spring.profiles.active`, trừ khi được ghi đè bằng `spring.cloud.config.profile`.

Ví dụ cấu hình của `billing-api` có thể được tổ chức như sau:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── billing-api.yml
└── billing-api-prod.yml
```

- `application.yml`: giá trị dùng chung cho các ứng dụng và profile.
- `application-prod.yml`: giá trị dùng chung khi các ứng dụng chạy với profile `prod`.
- `billing-api.yml`: giá trị riêng của `billing-api`.
- `billing-api-prod.yml`: giá trị riêng của `billing-api` trong profile `prod`.

Ví dụ, cấu hình `billing-api-prod.yml` có thể đặt kích thước pool kết nối lớn hơn cấu hình mặc định, trong khi `application-prod.yml` đặt mức log chung cho các dịch vụ production. Việc tách theo profile giúp cùng một ứng dụng dùng bộ cấu hình phù hợp với môi trường mà không phải duy trì nhiều bản sao mã nguồn.

Một client có thể gửi nhiều profile phân tách bằng dấu phẩy, ví dụ `prod,cloud`. Config Server kết hợp các nguồn cấu hình tương ứng. Thứ tự profile có ảnh hưởng khi nhiều profile cùng khai báo một khóa; profile được xét sau có thể ghi đè giá trị của profile trước. Hãy kiểm tra thứ tự `propertySources` trong phản hồi để xác nhận kết quả trên phiên bản Spring Cloud Config đang vận hành.

Không nên dùng profile để biểu diễn mọi khác biệt giữa các khách hàng hoặc từng instance. Profile nên mô tả nhóm cấu hình có ý nghĩa ổn định, chẳng hạn môi trường chạy hoặc một năng lực triển khai. Những khác biệt theo từng dịch vụ nên đặt trong tệp ứng dụng, còn giá trị riêng của từng instance thường phù hợp hơn với biến môi trường hoặc secret store.

## 4. Label: chọn phiên bản của kho cấu hình

`label` xác định phiên bản mà Config Server đọc trong backend Git. Label có thể là:

- Tên nhánh, ví dụ `main` hoặc `release/2026`.
- Tên tag, ví dụ `billing-v2.4.0`.
- Mã commit, dùng để trỏ tới một revision cụ thể.

Ví dụ, `release-2026` có thể là nhánh hoặc tag chứa cấu hình đã được kiểm thử cho đợt phát hành. Client đặt:

```yaml
spring:
  cloud:
    config:
      label: release-2026
```

Nếu không gửi label, Config Server dùng label mặc định do server thiết lập, ví dụ qua `spring.cloud.config.server.git.default-label`. Giá trị mặc định có thể khác nhau theo phiên bản và cấu hình triển khai. Vì vậy, hệ thống production nên chọn label tường minh và bảo đảm label đó tồn tại trên repository.

Nhánh Git có thể thay đổi khi có commit mới. Nếu nhiều dịch vụ cùng đọc một nhánh đang phát triển, chúng có thể nhận các revision cấu hình khác nhau ở những thời điểm khác nhau. Tag bất biến hoặc commit ID giúp gắn một bản phát hành ứng dụng với một revision cấu hình có thể truy vết và tái tạo. Khi dùng tag, cần áp dụng quy trình bảo vệ tag để tránh bị di chuyển hoặc ghi đè ngoài ý muốn.

## 5. Khai báo bộ ba ở Config Client

Với Spring Boot dùng Config Data import, client có thể khai báo tên ứng dụng, profile và label trong cấu hình khởi động:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod,cloud
  cloud:
    config:
      label: release-2026
  config:
    import: "optional:configserver:http://config-server:8888"
```

Trong ví dụ này, Config Client gửi `billing-api` làm application, `prod,cloud` làm profile và `release-2026` làm label. Có thể khai báo riêng `spring.cloud.config.name` hoặc `spring.cloud.config.profile` nếu cần ghi đè tên ứng dụng hay danh sách profile được dùng cho truy vấn Config Server.

Tiền tố `optional:` cho phép ứng dụng tiếp tục khởi động khi Config Server không truy cập được hoặc không cung cấp cấu hình. Cách này thích hợp khi cấu hình từ xa là tùy chọn. Nếu ứng dụng cần cấu hình tập trung để hoạt động an toàn, hãy bỏ `optional:` để lỗi nạp cấu hình được phát hiện ngay lúc khởi động.

Không nên nhầm ba tham số truy vấn với các nguồn ghi đè thuộc tính. Application, profile và label quyết định **tập cấu hình nào được lấy**. Sau khi phản hồi được nạp, Spring Boot vẫn hợp nhất các property source theo quy tắc ưu tiên của `Environment`. Vì thế, việc một giá trị nằm trong Git không tự động có nghĩa nó luôn thắng biến môi trường hoặc cấu hình cục bộ.

## 6. Quan sát phản hồi và kiểm tra truy vấn

Có thể gọi trực tiếp endpoint để kiểm tra Config Server đang trả về cấu hình nào:

```bash
curl -i "http://localhost:8888/billing-api/prod,cloud/release-2026"
```

Phản hồi JSON có dạng khái quát như sau:

```json
{
  "name": "billing-api",
  "profiles": ["prod", "cloud"],
  "label": "release-2026",
  "version": "a1b2c3d4",
  "propertySources": [
    {
      "name": ".../billing-api-prod.yml",
      "source": {
        "acme.billing.connect-timeout": "4s"
      }
    },
    {
      "name": ".../application.yml",
      "source": {
        "acme.billing.connect-timeout": "2s"
      }
    }
  ]
}
```

Đây là ví dụ minh họa cấu trúc; tên property source và thứ tự thực tế phụ thuộc backend, phiên bản và cách cấu hình Config Server. Hãy đọc `name`, `profiles`, `label` và `version` để xác nhận server đã xử lý đúng bộ ba. Sau đó xem từng `propertySources` để biết khóa được khai báo ở đâu và nguồn nào có ưu tiên cao hơn. Khi có hai nguồn cùng khai báo một khóa, thứ tự trong phản hồi giúp giải thích giá trị được chọn.

Các dấu hiệu thường gặp:

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Không tìm thấy cấu hình của ứng dụng | `spring.application.name`, `spring.cloud.config.name` và tên tệp trong repository |
| Nhận giá trị của môi trường khác | `spring.profiles.active` và `spring.cloud.config.profile` |
| Nhận cấu hình cũ hoặc thiếu khóa mới | `spring.cloud.config.label`, revision Git và thời điểm cập nhật repository |
| Giá trị không như mong đợi dù phản hồi có khóa | Thứ tự `propertySources` và các nguồn cấu hình khác trong client `Environment` |
| Client không tải được cấu hình | URL Config Server, xác thực, quyền đọc repository và label có tồn tại hay không |

## 7. Quản trị bộ ba trong hệ thống nhiều dịch vụ

Trong một hệ thống có nhiều ứng dụng, nên chuẩn hóa cách đặt tên để giảm lỗi vận hành:

1. Dùng một `spring.application.name` ổn định cho mỗi dịch vụ và đặt tên tệp Git khớp với tên đó.
2. Thống nhất danh sách profile giữa các môi trường triển khai; tránh tạo nhiều profile gần giống nhau nhưng không có ranh giới trách nhiệm rõ ràng.
3. Chọn label theo chính sách phát hành. Có thể dùng nhánh cho phát triển liên tục và tag hoặc commit cụ thể cho các bản phát hành cần tái lập.
4. Ghi nhận application, profile, label và Git revision trong log khởi động hoặc metadata triển khai để hỗ trợ truy vết.
5. Kiểm thử truy vấn của từng dịch vụ với đúng profile và label trước khi rollout.

Git repository nên được bảo vệ bằng quyền truy cập tối thiểu và quy trình review thay đổi. Không lưu mật khẩu, token hoặc private key ở dạng rõ trong các tệp cấu hình. Nếu cần phân phối bí mật, hãy dùng cơ chế mã hóa của Config Server hoặc tích hợp secret manager phù hợp; bảo vệ kết nối tới Config Server bằng TLS và xác thực.

Thay đổi một tệp trong Git không tự động thay đổi `Environment` của các tiến trình client đang chạy. Ứng dụng cần tải lại cấu hình theo cơ chế được triển khai, chẳng hạn restart, refresh endpoint hoặc phát sự kiện qua Spring Cloud Bus. Khi rollout một cấu hình mới, hãy xác định rõ label mà các client cần đọc, thời điểm refresh và cách quay lại revision trước nếu có lỗi.

## 8. Quy trình xác minh trước khi phát hành

Trước khi triển khai một dịch vụ, có thể kiểm tra theo trình tự:

1. Xác nhận `spring.application.name` khớp với tên ứng dụng trong repository.
2. Xác nhận profile đang hoạt động đúng với môi trường đích và không bị `spring.cloud.config.profile` ghi đè ngoài dự kiến.
3. Xác nhận label là nhánh, tag hoặc commit tồn tại và chứa đúng thay đổi đã review.
4. Gọi endpoint `/{application}/{profile}/{label}` để xem metadata và property source.
5. Kiểm tra các khóa quan trọng, giá trị mặc định, nguồn ghi đè và bí mật đã được bảo vệ.
6. Xác nhận kế hoạch refresh hoặc restart để client nhận revision mới.

Khi application, profile và label được quản trị nhất quán, Config Server có thể phục vụ cấu hình dùng chung cho nhiều dịch vụ, đồng thời giữ được khác biệt theo môi trường và phiên bản phát hành. Bộ ba này cũng tạo ra một điểm truy vết rõ ràng để giải thích vì sao một ứng dụng nhận đúng tập cấu hình tại một thời điểm cụ thể.
