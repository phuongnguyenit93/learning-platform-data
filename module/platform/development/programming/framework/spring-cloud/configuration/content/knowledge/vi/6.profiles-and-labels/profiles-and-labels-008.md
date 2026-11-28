# Tách môi trường triển khai khỏi chiến lược phân nhánh mã nguồn

Khi nhiều ứng dụng Spring Boot dùng Spring Cloud Config, hai câu hỏi thường xuất hiện cùng lúc: ứng dụng đang chạy với bộ cấu hình nào và bộ cấu hình đó lấy từ phiên bản nào trong Git? Spring Cloud Config giải quyết hai câu hỏi bằng hai thông tin riêng biệt: **profile** chọn biến thể cấu hình theo môi trường hoặc mục đích chạy; **label** chọn revision của kho cấu hình, thường là branch, tag hoặc commit.

Tách bạch hai khái niệm này giúp cùng một bản build của ứng dụng có thể chạy ở dev, staging và production với cấu hình phù hợp, đồng thời cho phép đội ngũ phát hành và quay lui cấu hình theo lịch sử Git. Profile không phải tên branch; label cũng không phải tên môi trường. Chúng phối hợp để xác định chính xác tập property source mà Config Server trả về.

## 1. Phân biệt profile và label

| Khía cạnh | Profile | Label |
| --- | --- | --- |
| Trả lời câu hỏi | Ứng dụng cần cấu hình theo môi trường hoặc chế độ nào? | Cần lấy cấu hình từ phiên bản nào của repository? |
| Ví dụ | `dev`, `staging`, `prod`, `test` | `main`, `release-2026.11`, tag hoặc commit SHA |
| Nơi được khai báo | `spring.profiles.active` hoặc cơ chế kích hoạt profile tương ứng | `spring.cloud.config.label` ở Config Client; `default-label` ở Config Server |
| Tác động | Chọn các file cấu hình chung và riêng có hậu tố profile | Chọn branch, tag hoặc revision Git mà server đọc |
| Thay đổi khi nào | Khi triển khai cùng ứng dụng vào môi trường/chế độ khác | Khi cần nâng cấp, ghim hoặc quay lui phiên bản cấu hình |

Ví dụ, một instance của `orders-service` có thể yêu cầu:

- Application: `orders-service`
- Profile: `prod`
- Label: `release-2026.11`

Nghĩa là Config Server tìm cấu hình cho ứng dụng `orders-service`, áp dụng các file phù hợp với profile `prod`, trong revision `release-2026.11` của Git repository.

Có thể mô tả kết quả bằng tổ hợp:

```text
(application, profile, label)
(orders-service, prod, release-2026.11)
```

Nếu thay profile thành `staging`, server chọn biến thể cấu hình staging trong cùng revision. Nếu thay label thành một commit khác, server đọc phiên bản repository khác nhưng vẫn có thể dùng profile `prod`.

## 2. Tổ chức repository theo profile

Một cách phổ biến là giữ cấu hình của các môi trường trong cùng một branch, dùng tên file để thể hiện phạm vi. Ví dụ:

```text
config-repo/
├── application.yml
├── application-dev.yml
├── application-staging.yml
├── application-prod.yml
├── orders-service.yml
├── orders-service-dev.yml
├── orders-service-prod.yml
├── payment-service.yml
└── payment-service-prod.yml
```

Các file có vai trò như sau:

- `application.yml`: thuộc tính dùng chung cho các ứng dụng, không phụ thuộc profile.
- `application-prod.yml`: thuộc tính dùng chung khi các ứng dụng chạy profile `prod`.
- `orders-service.yml`: cấu hình mặc định riêng cho ứng dụng đơn hàng.
- `orders-service-prod.yml`: cấu hình riêng cho `orders-service` khi chạy profile `prod`.
- `payment-service-prod.yml`: cấu hình riêng cho `payment-service` ở profile `prod`.

Ví dụ, `application.yml` chứa giá trị mặc định an toàn:

```yaml
platform:
  connect-timeout: 2s
  observability:
    metrics-enabled: true
```

`application-dev.yml` điều chỉnh một số giá trị cho môi trường phát triển:

```yaml
platform:
  observability:
    metrics-enabled: true

feature:
  mock-payment-provider: true
```

`application-prod.yml` bật chính sách production:

```yaml
platform:
  observability:
    metrics-enabled: true

feature:
  mock-payment-provider: false
```

Cấu hình riêng cho ứng dụng có thể được đặt ở `orders-service.yml`:

```yaml
orders:
  retry:
    max-attempts: 2
  http:
    read-timeout: 5s
```

Và `orders-service-prod.yml`:

```yaml
orders:
  retry:
    max-attempts: 4
  http:
    read-timeout: 10s
```

Cách đặt tên này thể hiện hai trục độc lập: phạm vi ứng dụng (`application` hoặc tên service) và profile. Nhóm vận hành có thể nhìn vào file để hiểu một thuộc tính áp dụng cho tất cả dịch vụ hay chỉ một dịch vụ trong một môi trường cụ thể.

Không nên tạo file riêng cho từng tổ hợp nếu nội dung không khác nhau. Bắt đầu từ cấu hình chung, sau đó chỉ ghi đè các giá trị thực sự cần khác biệt. Cách này giảm trùng lặp và giúp review thay đổi dễ dàng hơn.

## 3. Kích hoạt profile ở Config Client

Profile là thông tin của ứng dụng client. Với Config Data import trong Spring Boot hiện đại, có thể khai báo profile trong `application.yml`:

```yaml
spring:
  application:
    name: orders-service
  profiles:
    active: dev
  config:
    import: "configserver:http://config-server:8888"
```

Khi chạy staging, cùng image có thể nhận biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=staging
```

Với production:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Cấu hình qua biến môi trường thường phù hợp với container hoặc nền tảng triển khai, vì không cần đóng gói một artifact khác cho mỗi môi trường. Cần bảo đảm profile được xác định đủ sớm để Config Client gửi đúng request khi nạp cấu hình từ xa.

Có thể khai báo nhiều profile đang hoạt động, ví dụ `prod,observability`. Khi đó ứng dụng nhận các file cấu hình tương ứng với cả hai profile. Thứ tự profile có thể ảnh hưởng đến giá trị cuối cùng nếu nhiều profile cùng định nghĩa một key; profile được xử lý sau có thể ghi đè profile trước theo quy tắc của Spring Boot. Hãy giới hạn số profile kết hợp và kiểm tra response của Config Server khi nhiều profile cùng được dùng.

Spring Boot còn hỗ trợ profile group để gom các profile nhỏ thành một nhóm dễ vận hành. Ví dụ:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - observability
        - messaging
```

Khi kích hoạt `production`, các profile thành viên cũng được kích hoạt. Cách này giúp một môi trường có thể bật đồng bộ các nhóm cấu hình liên quan. Nên đặt tên group phản ánh mục đích rõ ràng và tránh để group kéo theo các thiết lập thử nghiệm ngoài ý muốn.

Lưu ý: `spring.profiles.active` và `spring.profiles.default` là thuộc tính dùng để xác định profile, không nên đặt trong tài liệu cấu hình chỉ được kích hoạt sau khi profile đã được chọn. Hãy khai báo chúng ở nguồn cấu hình không phụ thuộc profile, hoặc truyền từ môi trường triển khai.

## 4. Label chọn phiên bản Git

Label là tên revision mà Config Server dùng để đọc repository. Với Git backend, label thường là:

- Tên branch, ví dụ `main` hoặc `release/2026.11`.
- Tên tag, ví dụ `config-v2.4.0`.
- Commit SHA để ghim vào một revision cụ thể.

Config Server có thể khai báo label mặc định:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
```

Config Client có thể chọn label bằng:

```yaml
spring:
  cloud:
    config:
      label: config-v2.4.0
```

Hoặc truyền qua biến môi trường:

```bash
SPRING_CLOUD_CONFIG_LABEL=config-v2.4.0
```

Client có thể yêu cầu trực tiếp endpoint Config Server theo dạng:

```text
/{application}/{profile}/{label}
```

Ví dụ:

```bash
curl http://localhost:8888/orders-service/prod/config-v2.4.0
```

Response Environment cho biết application, profiles, label và các property source được trả về. Tùy backend và cấu hình, response có thể bao gồm revision Git. Đây là căn cứ để xác nhận server đã đọc đúng phiên bản repository.

Một branch có thể tiếp tục nhận commit mới, vì vậy cùng label `main` ở hai thời điểm có thể trả nội dung khác nhau. Tag đã phát hành hoặc commit SHA giúp ghim chính xác nội dung hơn. Với môi trường production, nên lưu lại label hoặc commit thực tế mà từng đợt triển khai sử dụng để có thể truy vết và rollback.

Nếu label là branch có dấu gạch chéo, chẳng hạn `release/2026.11`, cần chú ý cách biểu diễn label trong URL path. Spring Cloud Config hỗ trợ cách mã hóa dấu gạch chéo thành `(_)` trong path, ví dụ:

```text
/orders-service/prod/release(_)2026.11
```

Khi cấu hình qua client property, vẫn dùng tên label branch thực tế. Cách biểu diễn URL chỉ nhằm tránh dấu `/` bị hiểu là dấu phân cách path. Hãy kiểm tra endpoint theo phiên bản Spring Cloud Config đang chạy nếu sử dụng label có ký tự đặc biệt.

## 5. Profile và label phối hợp trong một lần triển khai

Profile và label được gửi cùng nhau để xác định tập cấu hình. Bảng sau minh họa một chính sách triển khai:

| Ứng dụng | Môi trường | Profile | Label |
| --- | --- | --- | --- |
| `orders-service` | Phát triển | `dev` | `main` |
| `orders-service` | Kiểm thử tích hợp | `staging` | `config-v2.4.0-rc1` |
| `orders-service` | Production | `prod` | `config-v2.4.0` |
| `payment-service` | Production | `prod` | `config-v2.4.0` |

Hai ứng dụng có thể dùng cùng label nhưng vẫn nhận cấu hình riêng vì application name khác nhau. Một ứng dụng cũng có thể dùng cùng profile `prod` qua nhiều lần phát hành, nhưng label thay đổi khi phiên bản cấu hình được nâng cấp.

Đối với môi trường staging, nhóm có thể thử một label candidate trước. Khi cấu hình đã được kiểm chứng, tạo tag phát hành và triển khai production với tag đó. Cách này cho phép kiểm soát chính xác revision mà không cần tạo một branch tên `prod` chỉ để đại diện cho môi trường.

Ví dụ, một deployment manifest có thể truyền các thông tin độc lập:

```yaml
env:
  - name: SPRING_APPLICATION_NAME
    value: orders-service
  - name: SPRING_PROFILES_ACTIVE
    value: prod
  - name: SPRING_CLOUD_CONFIG_LABEL
    value: config-v2.4.0
  - name: SPRING_CONFIG_IMPORT
    value: configserver:http://config-server:8888
```

Một image ứng dụng đã build và kiểm thử có thể được promote qua dev, staging và production. Môi trường triển khai quyết định profile; pipeline phát hành cấu hình quyết định label. Điều này giúp giảm sai khác do build riêng cho từng môi trường và tạo lịch sử cấu hình rõ ràng.

## 6. Thứ tự ưu tiên khi có nhiều file cùng khai báo một key

Một key có thể xuất hiện trong nhiều file. Config Server tạo các property source dựa trên application và profile; thứ tự các nguồn quyết định giá trị nào được ưu tiên. Theo cách tổ chức thông thường, mức độ cụ thể tăng dần từ cấu hình chung đến cấu hình riêng cho ứng dụng và profile:

1. `application.yml`: cấu hình chung mặc định.
2. `application-{profile}.yml`: cấu hình chung cho profile.
3. `{application}.yml`: cấu hình mặc định riêng cho ứng dụng.
4. `{application}-{profile}.yml`: cấu hình riêng cho ứng dụng và profile.

Ví dụ, cùng key `orders.http.read-timeout` có thể được khai báo trong cấu hình chung và cấu hình riêng của ứng dụng. File cụ thể hơn thường được ưu tiên. Với nhiều profile hoạt động, nhiều property source profile-specific có thể cùng tham gia.

Đây là thứ tự ở phía Config Server khi tạo Environment từ repository. Sau đó Config Client còn kết hợp remote property source với các nguồn khác như local config, biến môi trường, system property và command-line arguments. Vì vậy, giá trị cuối cùng mà bean nhận được có thể khác giá trị bạn thấy trong một file Git cụ thể.

Để chẩn đoán, kiểm tra endpoint đúng application/profile/label và xem danh sách `propertySources` theo thứ tự. Ở client, dùng Actuator `env` hoặc `configprops` trong môi trường được bảo vệ để xác định giá trị và nguồn gốc. Không mở các endpoint chẩn đoán này ra internet hoặc để chúng hiển thị secret.

## 7. Vì sao không nên đồng nhất profile với branch

Một cách làm đôi khi được áp dụng là tạo branch `dev`, `staging`, `prod` và coi mỗi branch là một môi trường. Cách này có thể hoạt động, nhưng nó trộn hai loại quyết định:

- Profile mô tả biến thể cấu hình mà ứng dụng cần tại thời điểm chạy.
- Branch quản lý lịch sử thay đổi và luồng cộng tác trên mã nguồn hoặc repository cấu hình.

Nếu mỗi môi trường có một branch riêng, một thay đổi dùng chung có thể phải merge qua nhiều branch. Các branch dễ bị lệch nhau, phát sinh merge conflict và khó xác định một giá trị production khác staging vì lý do gì. Cấu hình mới cũng có thể được đưa vào một branch nhưng bị quên không merge sang branch còn lại.

Một chiến lược thường dễ quản lý hơn là:

- Giữ một branch tích hợp chính cho repository cấu hình.
- Dùng các file profile-specific để thể hiện khác biệt môi trường.
- Review thay đổi qua pull request.
- Tạo tag hoặc ghi nhận commit khi phát hành một bộ cấu hình.
- Truyền label đã phê duyệt vào deployment manifest.
- Dùng branch dài hạn riêng khi thực sự cần duy trì một dòng release hoặc phiên bản ứng dụng cũ.

Branch per environment vẫn có thể là lựa chọn có chủ đích nếu quy trình tổ chức yêu cầu các luồng phê duyệt hoặc quyền ghi tách biệt. Tuy nhiên, cần có quy tắc đồng bộ thay đổi, người chịu trách nhiệm merge và cách xác định revision đang chạy. Không nên dùng branch chỉ vì muốn đặt tên cho môi trường; profile đã đảm nhiệm vai trò đó.

## 8. Một quy trình phát hành cấu hình có thể truy vết

Một quy trình đơn giản có thể chia thành các bước:

1. **Tạo thay đổi**: sửa file cấu hình chung hoặc file profile-specific trong một branch làm việc.
2. **Review**: kiểm tra phạm vi ảnh hưởng, giá trị mặc định, secret và khả năng tương thích với ứng dụng.
3. **Kiểm thử**: triển khai lên môi trường dev hoặc staging với profile tương ứng và label candidate.
4. **Phê duyệt**: xác nhận hành vi, log, metric và các phụ thuộc khi ứng dụng nhận cấu hình.
5. **Đánh dấu phiên bản**: tạo tag hoặc ghi nhận commit bất biến cho bộ cấu hình đã được duyệt.
6. **Promote**: cập nhật label trong deployment manifest của production, giữ nguyên artifact ứng dụng nếu không cần build lại.
7. **Theo dõi**: ghi nhận revision mà Config Server trả về và kiểm tra từng instance đã nạp đúng cấu hình.
8. **Rollback**: chuyển deployment về tag hoặc commit trước đó và kích hoạt quy trình refresh/rollout tương ứng.

Ví dụ, pipeline có thể dùng:

```text
dev       -> profile=dev       label=main
staging   -> profile=staging   label=config-v2.4.0-rc1
production-> profile=prod      label=config-v2.4.0
```

Label candidate và label phát hành có thể trỏ đến nội dung giống nhau tại thời điểm promote, nhưng tag phát hành cần được bảo vệ để không bị di chuyển sang commit khác. Nếu sử dụng commit SHA, pipeline có thể ghi trực tiếp SHA vào metadata của lần triển khai.

## 9. Những lỗi thường gặp khi phối hợp profile và label

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Client nhận cấu hình dev trong production | `SPRING_PROFILES_ACTIVE` sai hoặc profile mặc định được kích hoạt | Kiểm tra environment của container và response Environment |
| Server trả cấu hình từ branch không mong muốn | Client không đặt label và server dùng default-label | Kiểm tra `spring.cloud.config.label` và `default-label` |
| Tag mới không xuất hiện | Tag không tồn tại trong repository mà server đang đọc hoặc client vẫn yêu cầu label cũ | Kiểm tra Git ref và endpoint Config Server |
| Một thuộc tính bị ghi đè ngoài dự kiến | Nhiều file hoặc property source cùng khai báo key | Kiểm tra thứ tự `propertySources` và nguồn ở phía client |
| Hai ứng dụng nhận cùng giá trị riêng | Tên file không khớp `spring.application.name` hoặc file chỉ đặt ở phạm vi application | Kiểm tra application name và endpoint tương ứng |
| Profile kết hợp cho kết quả khó đoán | Nhiều profile cùng định nghĩa key hoặc thứ tự active profile không như mong đợi | Giảm profile không cần thiết và kiểm tra response |
| Không tái hiện được cấu hình của lần deploy cũ | Dùng branch thay đổi liên tục mà không lưu commit/revision | Ghi lại tag hoặc commit đã dùng khi phát hành |
| Label có dấu gạch chéo không truy cập được | Dấu `/` bị phân tích như path separator | Dùng cách mã hóa label trong URL theo quy tắc Config Server |

Khi có sự cố, ghi nhận đủ ba giá trị application, profile và label của instance. Sau đó gọi Config Server với chính tổ hợp đó, so sánh revision và property source, rồi kiểm tra Environment phía client. Cách truy vết này khoanh vùng được lỗi thuộc lựa chọn profile, lựa chọn Git revision hay precedence sau khi nạp.

## 10. Bảo mật và quản trị thay đổi theo môi trường

Profile và label giúp chọn cấu hình, nhưng không thay thế cơ chế bảo mật. Không lưu mật khẩu, token, private key hoặc chứng thư nhạy cảm dạng rõ trong các file profile. Dùng secret manager hoặc cơ chế mã hóa phù hợp; kiểm soát quyền đọc repository, quyền tạo tag và quyền thay đổi deployment manifest.

Production nên dùng label bất biến hoặc được bảo vệ, có review trước khi phát hành. Không cho phép quy trình triển khai tự động trỏ production vào một branch thay đổi liên tục nếu không có kiểm soát revision. Ghi lại người phê duyệt, commit, tag, profile và thời điểm áp dụng để hỗ trợ audit và rollback.

Khi một thay đổi profile ảnh hưởng đến retry, timeout, pool kết nối hoặc feature flag, cần đánh giá tác động tải và hành vi của ứng dụng. Việc cập nhật label hoặc commit trong Git không tự làm các instance đang chạy nhận giá trị mới. Phải kết hợp với refresh, Spring Cloud Bus hoặc rollout lại theo quy trình vận hành. Sau refresh, kiểm tra từng instance đã sử dụng revision mong muốn.

## 11. Nguyên tắc lựa chọn trong thực tế

- Dùng profile để thể hiện môi trường hoặc chế độ chạy, ví dụ `dev`, `staging`, `prod`.
- Dùng label để xác định revision Git, ví dụ branch tích hợp, tag phát hành hoặc commit SHA.
- Để cấu hình dùng chung ở `application.yml`, chỉ ghi đè ở file profile hoặc file ứng dụng khi có nhu cầu thực.
- Dùng cùng artifact ứng dụng qua các môi trường khi có thể; truyền profile và label từ pipeline triển khai.
- Ghim production vào revision đã được phê duyệt và lưu lại revision thực tế từng instance đã nạp.
- Chỉ duy trì branch riêng cho môi trường khi có lý do về release governance và có quy trình đồng bộ rõ ràng.
- Kiểm tra cả property source từ Config Server lẫn các nguồn phía client để hiểu giá trị cuối cùng.
- Kết hợp review, kiểm thử, bảo vệ secret, refresh và rollback trong quy trình thay đổi cấu hình.

Khi tách profile khỏi label, nhóm phát triển có thể thay đổi môi trường chạy mà không cần đổi chiến lược branch, đồng thời nâng cấp hoặc quay lui phiên bản cấu hình mà không phải đổi tên môi trường. Profile xác định biến thể cấu hình cần dùng; label xác định phiên bản Git cung cấp biến thể đó. Hai lựa chọn độc lập nhưng phối hợp với application name để Config Server trả đúng bộ cấu hình cho từng ứng dụng.

