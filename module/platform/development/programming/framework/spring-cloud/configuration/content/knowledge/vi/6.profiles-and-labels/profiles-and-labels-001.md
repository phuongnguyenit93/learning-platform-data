# Phân biệt Spring profile với Git branch, tag và commit

Khi dùng Spring Cloud Config, một yêu cầu cấu hình có ba thành phần: tên ứng dụng (`application`), Spring profile (`profile`) và Git label (`label`). Hai khái niệm thường bị nhầm là profile và label. **Spring profile chọn nhóm cấu hình theo môi trường hoặc năng lực chạy; Git label chọn phiên bản của kho cấu hình.** Một profile không phải là một nhánh Git, và một nhánh Git không thay thế được profile.

Hiểu đúng sự khác biệt này giúp một dịch vụ có thể chạy ở `dev`, `test` hoặc `prod` trên cùng một revision cấu hình, đồng thời cho phép nhóm phát hành chọn một phiên bản cấu hình đã được kiểm thử và có thể quay lui.

## 1. Ba thành phần của truy vấn Config Server

Config Server cung cấp endpoint theo dạng:

```text
/{application}/{profile}/{label}
```

Ví dụ:

```text
GET http://config-server:8888/billing-api/prod/release-2026
```

Yêu cầu này có nghĩa là lấy cấu hình cho ứng dụng `billing-api`, trong Spring profile `prod`, từ Git label `release-2026`.

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| `application` | Cấu hình dành cho dịch vụ nào? | `billing-api` |
| `profile` | Dịch vụ chạy với nhóm cấu hình nào? | `prod`, `dev`, `test` |
| `label` | Đọc cấu hình ở revision Git nào? | `main`, `release-2026`, commit SHA |

Ba thành phần độc lập về ý nghĩa. `billing-api/prod/main` và `billing-api/dev/main` dùng cùng nhánh Git nhưng lấy cấu hình cho hai profile khác nhau. `billing-api/prod/release-2026` và `billing-api/prod/main` dùng cùng profile nhưng có thể lấy nội dung cấu hình từ hai revision Git khác nhau.

## 2. Spring profile chọn nhóm cấu hình

Spring profile là cơ chế của Spring Framework và Spring Boot để kích hoạt các bean hoặc tài liệu cấu hình phù hợp với một ngữ cảnh chạy. Tên profile thường biểu diễn môi trường như `dev`, `test`, `staging`, `prod`, hoặc một năng lực triển khai như `cloud` hay `local-mock`.

Có thể kích hoạt profile trong `application.yml`:

```yaml
spring:
  profiles:
    active: prod
```

Hoặc truyền khi chạy ứng dụng:

```bash
java -jar billing-api.jar --spring.profiles.active=prod
```

Khi Config Client lấy cấu hình từ xa, danh sách profile đang hoạt động được dùng làm tham số profile của yêu cầu. Có thể ghi đè riêng profile truy vấn bằng `spring.cloud.config.profile` khi có chủ đích rõ ràng.

Một ứng dụng có thể kích hoạt nhiều profile, ví dụ `prod,cloud`. Spring và Config Server kết hợp các nguồn cấu hình tương ứng; thứ tự profile có ý nghĩa khi nhiều nguồn cùng khai báo một khóa. Vì vậy, nên thống nhất thứ tự profile giữa các môi trường và kiểm tra phản hồi `Environment` để biết các property source đã được nạp.

Profile cũng có thể điều khiển bean bằng `@Profile`:

```java
@Configuration
public class PaymentConfiguration {
    @Bean
    @Profile("dev")
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway livePaymentGateway() {
        return new LivePaymentGateway();
    }
}
```

Ví dụ này cho thấy profile là ngữ cảnh chạy của ứng dụng. Nó có thể chọn bean, giá trị cấu hình hoặc tài liệu YAML phù hợp; nó không xác định Git đang đọc nhánh hay commit nào.

## 3. Git branch, tag và commit chọn revision

Git label cho Config Server biết cần đọc repository tại revision nào. Với backend Git, label thường có thể là tên nhánh, tên tag hoặc mã commit.

**Branch (nhánh)** là dòng phát triển có thể tiếp tục nhận commit. Ví dụ `main` hoặc `release/2026`. Khi nhánh tiến lên, cùng một truy vấn có thể trả về cấu hình mới ở lần gọi sau. Nhánh phù hợp với môi trường phát triển liên tục, nhưng không tự bảo đảm một lần triển khai luôn nhận cùng nội dung.

**Tag** là tên tham chiếu thường được dùng để đánh dấu một bản phát hành hoặc mốc đã kiểm thử, ví dụ `config-v2.4.0`. Theo quy trình tốt, tag phát hành được bảo vệ và không di chuyển. Tuy nhiên, Git cho phép quản trị viên thay đổi tag; tính bất biến phải được bảo đảm bằng chính sách repository và quyền truy cập.

**Commit** là một revision cụ thể, được nhận diện bằng mã hash. Dùng commit SHA giúp truy vấn trỏ tới đúng nội dung đã được ghi nhận, kể cả khi nhánh tiếp tục thay đổi. Đây là lựa chọn phù hợp khi cần tái lập chính xác một lần triển khai hoặc điều tra sự cố.

| Git label | Có thay đổi khi có commit mới trên nhánh? | Trường hợp sử dụng |
| --- | --- | --- |
| `main` (branch) | Có | Phát triển liên tục, môi trường tích hợp |
| `release/2026` (branch) | Có, khi nhánh nhận commit | Kiểm thử và chuẩn bị phát hành |
| `config-v2.4.0` (tag) | Không theo quy ước; cần bảo vệ tag | Đánh dấu cấu hình của một bản phát hành |
| `a1b2c3d4...` (commit) | Không, commit là revision đã tạo | Tái lập hoặc quay về đúng snapshot |

Config Server có thể dùng label mặc định do server cấu hình nếu client không gửi label. Với Git backend, thuộc tính `spring.cloud.config.server.git.default-label` xác định label mặc định trong các phiên bản hỗ trợ thuộc tính này. Hệ thống production nên khai báo label tường minh để tránh phụ thuộc vào mặc định khác nhau giữa các môi trường hoặc lần nâng cấp.

## 4. Cấu trúc repository kết hợp application và profile

Một repository có thể giữ cấu hình dùng chung, cấu hình riêng theo ứng dụng và cấu hình theo profile trong cùng một revision Git:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── application-dev.yml
├── billing-api.yml
├── billing-api-prod.yml
├── billing-api-dev.yml
├── inventory-api.yml
└── inventory-api-prod.yml
```

- `application.yml`: giá trị mặc định dùng chung cho các ứng dụng.
- `application-prod.yml`: giá trị chung cho profile `prod`.
- `billing-api.yml`: cấu hình riêng cho `billing-api`.
- `billing-api-prod.yml`: cấu hình riêng cho `billing-api` khi chạy profile `prod`.
- `inventory-api-prod.yml`: cấu hình riêng cho `inventory-api` trong profile `prod`.

Ví dụ `application-prod.yml` có thể đặt mức log mặc định và endpoint quan sát chung; `billing-api-prod.yml` đặt pool kết nối hoặc timeout riêng cho dịch vụ thanh toán. Cách tổ chức này cho phép nhiều ứng dụng dùng chung một Git label mà vẫn có cấu hình riêng theo ứng dụng và profile.

Khi chuyển từ label `main` sang tag `config-v2.4.0`, Config Server đọc lại cùng các tệp theo cấu trúc trên tại revision được chọn. Profile `prod` vẫn có ý nghĩa như cũ; label chỉ thay đổi phiên bản nội dung của những tệp đó.

## 5. Khai báo profile và label ở Config Client

Ví dụ Config Client dùng Spring Boot Config Data import:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod
  cloud:
    config:
      label: config-v2.4.0
  config:
    import: "configserver:http://config-server:8888"
```

Trong cấu hình này:

- `spring.application.name` chọn `billing-api`.
- `spring.profiles.active` chọn profile `prod`.
- `spring.cloud.config.label` chọn Git label `config-v2.4.0`.
- `spring.config.import` chỉ ra Config Server mà client cần liên hệ.

Nếu cấu hình từ xa là tùy chọn, có thể dùng `optional:configserver:...` trong `spring.config.import`. Khi cấu hình từ xa là điều kiện bắt buộc để ứng dụng hoạt động, nên để import bắt buộc để lỗi kết nối hoặc thiếu cấu hình được phát hiện ngay khi khởi động.

Có thể đặt label bằng biến môi trường trong container:

```bash
SPRING_CLOUD_CONFIG_LABEL=config-v2.4.0
```

Đối với triển khai cần tái lập, pipeline nên truyền label từ metadata của bản phát hành. Không nên để từng máy tự chọn `main` hoặc một nhánh cá nhân vì kết quả có thể khác nhau theo thời điểm.

## 6. Ví dụ: cùng profile, khác Git label

Giả sử `billing-api` chạy profile `prod`. Nhóm phát triển đã kiểm thử cấu hình trên nhánh `release/2026`; sau đó tạo tag `config-v2.4.0` tại commit đã được phê duyệt.

| Truy vấn | Kết quả mong đợi |
| --- | --- |
| `/billing-api/prod/release%2F2026` | Cấu hình production tại trạng thái hiện tại của nhánh `release/2026` |
| `/billing-api/prod/config-v2.4.0` | Cấu hình production tại tag phát hành `config-v2.4.0` |
| `/billing-api/prod/a1b2c3d4...` | Cấu hình production tại commit cụ thể |

Các yêu cầu trên đều dùng profile `prod`; chỉ revision Git thay đổi. Nếu nhánh `release/2026` nhận một commit mới, lần truy vấn tiếp theo có thể nhận cấu hình mới. Tag hoặc commit vẫn trỏ tới revision cũ, miễn là tag được bảo vệ và commit còn trong repository.

## 7. Ví dụ: cùng Git label, khác profile

Giả sử Config Server đọc Git label `config-v2.4.0`. Hai ứng dụng có thể truy vấn:

```text
/billing-api/dev/config-v2.4.0
/billing-api/prod/config-v2.4.0
```

Cả hai lấy dữ liệu từ cùng revision Git. Yêu cầu thứ nhất lấy các nguồn phù hợp với profile `dev`, còn yêu cầu thứ hai lấy các nguồn phù hợp với profile `prod`. Ví dụ, cùng một tệp `billing-api-prod.yml` tại revision đó chứa endpoint và timeout production, trong khi `billing-api-dev.yml` chứa endpoint dịch vụ giả lập và mức log chi tiết hơn.

Điều này cũng cho thấy không cần tạo một nhánh Git riêng cho mỗi môi trường. Có thể quản lý khác biệt môi trường bằng profile và tệp profile-specific, sau đó dùng label để cố định revision của toàn bộ repository.

## 8. Quy tắc lựa chọn cho phát triển và phát hành

Một cách tổ chức thực tế là:

1. Dùng profile để biểu diễn môi trường hoặc nhóm hành vi của ứng dụng, ví dụ `dev`, `test`, `prod`.
2. Dùng branch để phát triển và tích hợp thay đổi cấu hình trong một dòng công việc.
3. Dùng tag đã được bảo vệ hoặc commit SHA để cố định cấu hình cho bản phát hành cần tái lập.
4. Giữ các tệp cấu hình của nhiều ứng dụng trong cùng repository nếu chúng cần được review và phát hành đồng bộ; tách repository khi ranh giới quyền truy cập hoặc vòng đời thay đổi khác nhau.
5. Ghi nhận cả profile và Git revision thực tế khi triển khai để biết ứng dụng đã nhận cấu hình nào.

Không nên đặt tên profile là `release-2026` chỉ để biểu diễn phiên bản cấu hình; cũng không nên tạo branch `prod` rồi xem nó như Spring profile. Hai cách này làm lẫn lộn ngữ cảnh chạy với lịch sử phiên bản, khiến việc kiểm thử, truy vết và quay lui khó hơn.

## 9. Kiểm tra cấu hình mà Config Server trả về

Có thể gọi trực tiếp endpoint để xác nhận bộ ba đã được xử lý đúng:

```bash
curl -i "http://localhost:8888/billing-api/prod/config-v2.4.0"
```

Đọc các trường `name`, `profiles`, `label`, `version` và `propertySources` trong phản hồi JSON. `profiles` cho biết profile được yêu cầu; `label` và `version` giúp xác định revision Git mà server đã đọc; `propertySources` cho biết các tệp cấu hình được kết hợp. Nếu label có dấu `/`, cần mã hóa dấu phân cách trong URL theo quy tắc của endpoint và proxy đang dùng, hoặc chọn tên label không chứa dấu `/` để đơn giản hóa vận hành.

Khi giá trị cuối cùng trong ứng dụng không đúng như mong đợi, cần kiểm tra hai lớp riêng biệt:

- Config Server đã trả về đúng application, profile, label và property source chưa?
- Sau khi client nạp phản hồi, property source nào có độ ưu tiên cao nhất trong Spring `Environment`?

Một truy vấn đúng không bảo đảm mọi giá trị trong ứng dụng đều đến từ Git; biến môi trường, tham số dòng lệnh và các nguồn khác có thể ghi đè. Relaxed binding chỉ ánh xạ cách viết tên thuộc tính, không quyết định revision Git hoặc thứ tự ưu tiên nguồn.

## 10. Quay lui và tái lập cấu hình

Khi một thay đổi cấu hình gây lỗi, label xác định cách quay lui:

- Nếu đang dùng branch, có thể revert commit gây lỗi hoặc chuyển client về tag/commit đã được kiểm thử.
- Nếu đang dùng tag phát hành, triển khai lại ứng dụng với tag trước đó, đồng thời giữ nguyên profile cần chạy.
- Nếu cần điều tra chính xác, dùng commit SHA đã ghi nhận để truy vấn lại cùng snapshot.

Sau khi đổi label, client đang chạy không tự động thay đổi cấu hình chỉ vì Git có revision mới. Cần triển khai lại, refresh hoặc phát sự kiện qua Spring Cloud Bus tùy kiến trúc và cách cấu hình ứng dụng. Hãy xác định rõ cơ chế cập nhật, kiểm tra các bean có hỗ trợ refresh và chuẩn bị cách quay lại revision ổn định.

Với mỗi lần phát hành, nên ghi lại tối thiểu: tên ứng dụng, danh sách profile, Config Server label, Git revision thực tế, phiên bản ứng dụng và thời điểm triển khai. Không ghi bí mật vào metadata hoặc log. Những thông tin này tạo thành dấu vết đủ rõ để nhóm biết một instance đã chạy với ngữ cảnh nào và cấu hình từ revision nào.

Khi phân biệt rõ profile và Git label, nhóm có thể quản lý môi trường chạy và vòng đời cấu hình một cách độc lập. Profile giúp chọn hành vi phù hợp với môi trường; branch, tag và commit giúp kiểm soát phiên bản cấu hình được phân phối. Kết hợp cả hai tạo ra quy trình triển khai dễ kiểm thử, truy vết và quay lui hơn.
