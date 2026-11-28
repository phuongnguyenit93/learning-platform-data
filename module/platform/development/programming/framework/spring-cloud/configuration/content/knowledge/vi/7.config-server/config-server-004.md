# Kiểm tra cấu hình được phân giải qua yêu cầu HTTP đầu tiên

Sau khi khởi động Spring Cloud Config Server và kết nối nó với kho cấu hình Git, bước kiểm tra đầu tiên là gửi một yêu cầu HTTP trực tiếp đến server. Yêu cầu này cho biết Config Server có đọc được repository hay không, đã chọn đúng ứng dụng, profile và label hay chưa, đồng thời trả về những property source nào để tạo nên cấu hình cuối cùng.

Kiểm tra ở tầng HTTP giúp tách lỗi của kho cấu hình và Config Server khỏi lỗi của Config Client. Nếu response đã thiếu key hoặc chứa giá trị không mong đợi, cần xem lại repository, profile, label và thứ tự nguồn cấu hình trước khi điều tra bean trong ứng dụng.

## 1. Điều kiện trước khi gửi yêu cầu

Giả sử môi trường có các thành phần sau:

- Config Server chạy tại `http://localhost:8888`.
- Git repository chứa cấu hình đã được Config Server đọc.
- Ứng dụng cần kiểm tra có tên `order-service`.
- Profile đang kiểm tra là `dev`.
- Label Git cần đọc là `main`.

Một repository minh họa có thể chứa các tệp:

```text
config-repo/
├── application.yml
├── application-dev.yml
├── order-service.yml
└── order-service-dev.yml
```

Ví dụ nội dung:

```yaml
# application.yml
app:
  support-email: support@example.com
  request-timeout: 3s
```

```yaml
# application-dev.yml
app:
  environment-name: development
```

```yaml
# order-service.yml
service:
  display-name: Order Service
  max-items-per-order: 20
```

```yaml
# order-service-dev.yml
app:
  request-timeout: 5s
```

Trong ví dụ này, cấu hình chung cung cấp email hỗ trợ và timeout mặc định; profile `dev` xác định tên môi trường; `order-service` bổ sung tên dịch vụ và giới hạn đơn hàng; tệp riêng theo profile ghi đè timeout cho ứng dụng này.

Config Server cần được bật bằng `@EnableConfigServer` và có backend Git hợp lệ. Ví dụ cấu hình tối thiểu:

```yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: "file:///D:/workspace/config-repo"
          default-label: main
          clone-on-start: true
```

Thay URI bằng vị trí repository thực tế. Với repository remote, dùng URL HTTPS/SSH và cấp credential an toàn cho Config Server. Tất cả thay đổi cần được commit vào đúng Git ref mà server đang đọc. `clone-on-start` giúp phát hiện sớm một số lỗi truy cập repository khi server khởi động.

## 2. Cấu trúc yêu cầu HTTP đầu tiên

Config Server cung cấp endpoint Environment có dạng:

```text
/{application}/{profile}/{label}
```

Ba thành phần trong đường dẫn quyết định bộ cấu hình cần phân giải:

| Thành phần | Giá trị ví dụ | Vai trò |
|---|---|---|
| `application` | `order-service` | Chọn cấu hình dùng chung và cấu hình riêng của ứng dụng |
| `profile` | `dev` | Chọn các giá trị gắn với môi trường hoặc profile Spring đang hoạt động |
| `label` | `main` | Chọn branch, tag hoặc Git ref cần đọc |

Gửi yêu cầu:

```text
GET http://localhost:8888/order-service/dev/main
```

Trên PowerShell, dùng `Invoke-RestMethod` để nhận JSON đã được chuyển thành object:

```powershell
$url = "http://localhost:8888/order-service/dev/main"
$result = Invoke-RestMethod -Method Get -Uri $url
$result | ConvertTo-Json -Depth 20
```

Trên Linux, macOS hoặc terminal có curl:

```bash
curl -i "http://localhost:8888/order-service/dev/main"
```

`-i` hiển thị cả HTTP status và response headers. Nếu dùng PowerShell, `curl` có thể là alias của `Invoke-WebRequest`; gọi `curl.exe` nếu muốn dùng đúng chương trình curl.

Label có thể được bỏ khỏi URL nếu muốn Config Server dùng `default-label` đã cấu hình. Trong giai đoạn kiểm tra, nên truyền label rõ ràng để biết chính xác phiên bản repository đang được yêu cầu.

## 3. Đọc response Environment

Khi yêu cầu thành công, Config Server trả về một đối tượng Environment ở dạng JSON. Cấu trúc rút gọn thường có dạng:

```json
{
  "name": "order-service",
  "profiles": ["dev"],
  "label": "main",
  "version": "<git-commit-id>",
  "state": null,
  "propertySources": [
    {
      "name": "file:D:/workspace/config-repo/order-service-dev.yml",
      "source": {
        "app.request-timeout": "5s"
      }
    },
    {
      "name": "file:D:/workspace/config-repo/order-service.yml",
      "source": {
        "service.display-name": "Order Service",
        "service.max-items-per-order": 20
      }
    },
    {
      "name": "file:D:/workspace/config-repo/application-dev.yml",
      "source": {
        "app.environment-name": "development"
      }
    },
    {
      "name": "file:D:/workspace/config-repo/application.yml",
      "source": {
        "app.support-email": "support@example.com",
        "app.request-timeout": "3s"
      }
    }
  ]
}
```

Đây là ví dụ minh họa cấu trúc; tên nguồn và cách biểu diễn giá trị cụ thể phụ thuộc backend và phiên bản. Các trường quan trọng:

- `name`: application mà server đã xử lý.
- `profiles`: danh sách profile được dùng để phân giải cấu hình.
- `label`: Git ref được yêu cầu hoặc được chọn.
- `version`: phiên bản commit nếu backend cung cấp thông tin đó.
- `propertySources`: danh sách các nguồn cấu hình tham gia kết quả.
- `propertySources[].name`: tên hoặc vị trí của nguồn, hữu ích để xác định key đến từ tệp nào.
- `propertySources[].source`: các key và giá trị trong nguồn tương ứng.

Danh sách `propertySources` được sắp theo độ ưu tiên; nguồn đứng trước có ưu tiên cao hơn nguồn đứng sau khi cùng khai báo một key. Vì thế, trong ví dụ trên, `app.request-timeout` có giá trị hiệu lực là `5s` từ `order-service-dev.yml`, còn giá trị `3s` ở `application.yml` là baseline bị ghi đè. Các key không bị ghi đè vẫn được kế thừa từ nguồn thấp hơn.

Không phải response nào cũng có đủ mọi trường hoặc có cùng số lượng property source. Nếu một key không xuất hiện, có thể tệp không được tìm thấy, key không được khai báo, profile/label không đúng hoặc backend không trả về nguồn như dự kiến.

## 4. Xác minh ba thông tin định tuyến

Đừng chỉ kiểm tra xem response có HTTP 200 hay không. Hãy xác nhận các trường định tuyến khớp với ý định triển khai:

1. `name` phải là `order-service`.
2. `profiles` phải bao gồm `dev`.
3. `label` phải là `main` hoặc label cụ thể đã yêu cầu.
4. `version` nên được ghi nhận khi cần truy vết chính xác commit được phục vụ.

Ví dụ kiểm tra nhanh trong PowerShell:

```powershell
if ($result.name -ne "order-service") {
    throw "Config Server returned an unexpected application name"
}

if ($result.profiles -notcontains "dev") {
    throw "The expected dev profile is missing"
}

if ($result.label -ne "main") {
    throw "Config Server did not resolve the requested label"
}
```

Nếu một trong các thông tin không đúng, dừng việc đánh giá giá trị property cho đến khi xác định đúng đích cấu hình. Một response hợp lệ về mặt HTTP vẫn có thể là response cho sai ứng dụng hoặc sai profile.

## 5. Kiểm tra giá trị và nguồn ghi đè

Với ví dụ ở trên, có thể kiểm tra các key quan trọng bằng PowerShell:

```powershell
$allSources = $result.propertySources

foreach ($propertySource in $allSources) {
    $propertySource.source.PSObject.Properties |
        Where-Object { $_.Name -in @(
            "app.request-timeout",
            "app.support-email",
            "app.environment-name",
            "service.display-name",
            "service.max-items-per-order"
        ) } |
        ForEach-Object {
            [PSCustomObject]@{
                Key = $_.Name
                Value = $_.Value
                Source = $propertySource.name
            }
        }
}
```

Đoạn lệnh hiển thị key, giá trị và nguồn xuất hiện của key trong từng property source. Một key có thể xuất hiện nhiều lần; hãy đọc danh sách theo thứ tự ưu tiên để xác định giá trị thắng. Không in các key chứa mật khẩu, token hoặc dữ liệu bí mật vào terminal được chia sẻ, log CI hay ảnh chụp màn hình.

Để xác nhận kết quả kỳ vọng của ví dụ:

| Key | Giá trị hiệu lực dự kiến | Nguồn dự kiến |
|---|---|---|
| `app.request-timeout` | `5s` | `order-service-dev.yml` |
| `app.support-email` | `support@example.com` | `application.yml` |
| `app.environment-name` | `development` | `application-dev.yml` |
| `service.display-name` | `Order Service` | `order-service.yml` |
| `service.max-items-per-order` | `20` | `order-service.yml` |

Config Server response cho biết các property source được server phân giải. Giá trị cuối cùng trong ứng dụng còn chịu ảnh hưởng bởi các nguồn cấu hình phía client như biến môi trường, JVM system property, command-line argument, cấu hình local và chính sách override của Spring Cloud Config. Vì vậy, khi HTTP response đúng nhưng ứng dụng dùng giá trị khác, cần kiểm tra `Environment` của client và thứ tự ưu tiên tại đó.

## 6. Kiểm tra bằng định dạng YAML hoặc properties

Ngoài JSON Environment, Config Server hỗ trợ lấy cấu hình theo định dạng tệp. Ví dụ YAML:

```text
GET http://localhost:8888/order-service-dev.yml
```

Với curl:

```bash
curl -i "http://localhost:8888/order-service-dev.yml"
```

Có thể yêu cầu định dạng properties bằng endpoint tương ứng:

```text
GET http://localhost:8888/order-service-dev.properties
```

Định dạng tệp tiện để đọc nhanh các giá trị đã kết hợp. Endpoint Environment JSON phù hợp hơn khi cần xem metadata `name`, `profiles`, `label`, `version` và từng `propertySources`. Khi điều tra nguồn ghi đè, ưu tiên xem Environment thay vì chỉ đọc tệp đã kết hợp.

## 7. Thử thay đổi application, profile và label

Để hiểu mỗi thành phần đường dẫn tác động thế nào, thay từng giá trị một và gửi lại request.

**Đổi application:** gọi `/catalog-service/dev/main`. Server sẽ tìm cấu hình chung và cấu hình dành cho `catalog-service`. Nếu chưa có tệp riêng, có thể chỉ thấy các nguồn dùng chung.

**Đổi profile:** gọi `/order-service/prod/main`. Server sẽ tìm `application-prod.yml` và `order-service-prod.yml` cùng các nguồn phù hợp khác. So sánh `profiles` và property sources với request dùng `dev`.

**Đổi label:** gọi `/order-service/dev/release-2026.11`. Label phải tồn tại trong repository và server phải đọc được Git ref đó. Có thể dùng branch hoặc tag theo quy trình phát hành. Production nên ghim vào một label được kiểm soát thay vì phụ thuộc một nhánh phát triển luôn thay đổi.

Ví dụ gọi một label cụ thể bằng PowerShell:

```powershell
$label = "release-2026.11"
$url = "http://localhost:8888/order-service/dev/$label"
$releaseConfig = Invoke-RestMethod -Method Get -Uri $url
$releaseConfig | Select-Object name, profiles, label, version
```

Nếu server trả về lỗi không tìm thấy label, kiểm tra tên branch/tag, quyền đọc Git và cấu hình `default-label`. Đừng kết luận label đã được triển khai chỉ vì nó tồn tại trong giao diện Git; Config Server phải truy cập được ref đó.

## 8. Phân biệt lỗi HTTP và lỗi phân giải cấu hình

Khi gọi endpoint đầu tiên, hãy quan sát cả HTTP status và nội dung response:

| Kết quả | Ý nghĩa có thể có | Việc cần kiểm tra |
|---|---|---|
| `200 OK` và đủ property | Server đã trả Environment | Xác minh application, profile, label, version và thứ tự property source |
| `200 OK` nhưng thiếu key | Server xử lý request nhưng không tìm thấy key trong các nguồn phù hợp | Kiểm tra tên tệp, key, profile và label |
| `404 Not Found` | Endpoint hoặc tài nguyên được yêu cầu không được tìm thấy | Kiểm tra URL, application/profile/label và log server |
| `5xx` | Server gặp lỗi khi đọc hoặc xử lý backend | Kiểm tra Git URI, credential, quyền truy cập, kết nối mạng và log Config Server |
| Timeout hoặc không kết nối được | Server chưa chạy, sai host/port hoặc kết nối mạng bị chặn | Kiểm tra tiến trình, port, DNS, firewall và đường mạng từ client |

Mã lỗi cụ thể có thể thay đổi theo phiên bản và backend. Hãy dùng response body và log Config Server để xác định nguyên nhân thực tế; không suy ra chắc chắn lỗi Git chỉ từ một status code.

Các lỗi thường gặp:

- **Sai application:** `spring.application.name` ở client không khớp tên tệp cấu hình.
- **Sai profile:** client yêu cầu `dev` nhưng dữ liệu chỉ có trong `prod`, hoặc ngược lại.
- **Sai label:** client yêu cầu nhánh/tag chưa tồn tại hoặc server không có quyền đọc.
- **Chưa commit thay đổi:** repository làm việc có file mới nhưng Git ref mà server đọc chưa chứa commit đó.
- **Server giữ bản clone cũ:** backend chưa fetch phiên bản mới theo cấu hình; kiểm tra cache, refresh interval hoặc restart trong môi trường local.
- **Sai thứ tự nguồn:** giá trị bị một property source có ưu tiên cao hơn ghi đè.
- **Lỗi YAML:** cấu trúc thụt lề hoặc kiểu dữ liệu không hợp lệ khiến server không thể phân tích tệp.

## 9. Quy trình kiểm tra có thể lặp lại

Mỗi lần thay đổi cấu hình, có thể thực hiện quy trình ngắn sau:

1. Kiểm tra commit và Git ref có chứa thay đổi.
2. Xác nhận Config Server truy cập được repository và phục vụ đúng label.
3. Gửi `GET /{application}/{profile}/{label}` với ba tham số rõ ràng.
4. Kiểm tra HTTP status, `name`, `profiles`, `label` và `version`.
5. Đọc `propertySources`, tìm key quan trọng và xác định nguồn thắng theo thứ tự ưu tiên.
6. Kiểm tra cấu hình hiệu lực ở client nếu kết quả trong ứng dụng khác với response server.
7. Lưu lại label/commit và kết quả xác minh phục vụ truy vết hoặc rollback.

Đối với production, cần xác thực người gọi và bảo vệ đường truyền HTTPS/TLS. Endpoint Config Server có thể trả về thông tin nội bộ hoặc secret nếu repository được tổ chức sai; giới hạn quyền đọc, không commit bí mật dạng rõ và không đưa response đầy đủ vào log công khai. Khi kiểm tra, chỉ hiển thị những key không nhạy cảm cần thiết.

Yêu cầu HTTP đầu tiên là phép kiểm tra quan trọng để xác nhận Config Server đã phân giải cấu hình theo đúng application, profile và label. Khi đọc được metadata cùng danh sách property source, người vận hành có thể xác định cấu hình đến từ tệp nào, giá trị nào đang ghi đè và nên điều tra tiếp ở Git, Config Server hay Config Client.
