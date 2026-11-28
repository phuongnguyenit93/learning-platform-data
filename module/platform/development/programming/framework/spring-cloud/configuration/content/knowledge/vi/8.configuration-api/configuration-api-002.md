# Đọc propertySources, profiles, label, version và state trong phản hồi

Khi gọi Config Server, HTTP response cho biết nhiều hơn các giá trị cấu hình. Đối tượng `Environment` còn mô tả ứng dụng được truy vấn, các profile đã áp dụng, Git label và thông tin phiên bản của nguồn cấu hình. Danh sách `propertySources` cho biết từng tệp hoặc nguồn đã đóng góp thuộc tính nào và thứ tự ưu tiên của chúng. Đọc được các trường này giúp xác nhận client đang lấy đúng cấu hình, tìm nguồn của một giá trị và điều tra vì sao một khóa bị ghi đè.

## 1. Gọi API và nhận đối tượng Environment

Endpoint chính của Config Server có dạng:

```text
GET /{application}/{profile}/{label}
```

Ví dụ truy vấn cấu hình production của `billing-api` tại Git label `release-2026`:

```bash
curl -i "http://localhost:8888/billing-api/prod/release-2026"
```

Server trả về một đối tượng `Environment` ở định dạng JSON. Cấu trúc rút gọn thường có các trường:

```json
{
  "name": "billing-api",
  "profiles": ["prod"],
  "label": "release-2026",
  "version": "a1b2c3d4e5f6...",
  "state": null,
  "propertySources": [
    {
      "name": ".../billing-api-prod.yml",
      "source": {
        "acme.billing.connect-timeout": "4s",
        "acme.billing.retry.max-attempts": 5
      }
    },
    {
      "name": ".../billing-api.yml",
      "source": {
        "acme.billing.connect-timeout": "2s",
        "acme.billing.retry.max-attempts": 3
      }
    },
    {
      "name": ".../application.yml",
      "source": {
        "acme.billing.currency": "VND"
      }
    }
  ]
}
```

Đây là ví dụ minh họa; tên nguồn, kiểu giá trị và metadata thực tế phụ thuộc repository, backend và phiên bản Spring Cloud Config. Không phải backend nào cũng cung cấp đủ `version` hoặc `state`.

## 2. Ý nghĩa của các trường metadata

| Trường | Ý nghĩa | Cách sử dụng khi kiểm tra |
| --- | --- | --- |
| `name` | Tên application mà server xử lý | Xác nhận client truy vấn đúng dịch vụ |
| `profiles` | Danh sách profile được áp dụng cho yêu cầu | Xác nhận môi trường và thứ tự các profile |
| `label` | Label cấu hình được yêu cầu hoặc được server giải quyết | Xác nhận nhánh, tag hoặc revision mà server đã dùng |
| `version` | Thông tin phiên bản của nguồn cấu hình; với Git thường là commit ID | Ghi nhận revision để truy vết và tái lập |
| `state` | Metadata trạng thái do repository/backend cung cấp | Xem như dấu hiệu bổ sung nếu backend hỗ trợ; không mặc định nó là commit ID |
| `propertySources` | Danh sách nguồn cấu hình cùng các thuộc tính mỗi nguồn cung cấp | Xác định nguồn gốc và thứ tự ưu tiên của từng khóa |

`name`, `profiles` và `label` giúp kiểm tra bộ ba truy vấn. `version` và `state` cung cấp thông tin về trạng thái backend. Các trường metadata này không thay thế việc kiểm tra giá trị cuối cùng đã được bind trong Config Client.

### Profiles

`profiles` là một mảng vì client có thể yêu cầu nhiều profile, ví dụ `prod,cloud`. Giá trị này cho biết các profile liên quan đến phản hồi. Thứ tự profile có thể ảnh hưởng đến kết quả khi nhiều profile cùng định nghĩa một khóa. Khi điều tra, hãy so sánh mảng `profiles` trong response với `spring.profiles.active` và `spring.cloud.config.profile` ở client.

### Label

`label` xác định revision được dùng để tìm các tệp cấu hình trong backend hỗ trợ versioning, thường là Git branch, tag hoặc commit. Nếu client không gửi label, Config Server có thể dùng label mặc định được cấu hình ở server. Vì vậy, hãy đọc giá trị trả về thay vì chỉ dựa vào giả định về mặc định. Nếu label không như mong đợi, kiểm tra `spring.cloud.config.label` ở client và `spring.cloud.config.server.git.default-label` ở server.

### Version và state

Với Git backend, `version` thường chứa mã commit mà Config Server đã đọc. Lưu giá trị này cùng metadata triển khai để có thể xác định chính xác revision cấu hình. Nếu `version` là `null`, có thể backend không cung cấp thông tin phiên bản hoặc server không lấy được metadata version theo cách backend đó hỗ trợ.

`state` là trường metadata bổ sung do repository implementation có thể sử dụng để cung cấp thông tin trạng thái. Giá trị có thể là `null`, trống hoặc mang ý nghĩa riêng theo backend. Không nên suy luận rằng `state` luôn bằng branch, tag hay commit SHA. Khi cần dùng trường này trong tự động hóa, hãy xác minh semantics của backend và phiên bản đang triển khai; nếu không có hợp đồng cụ thể, chỉ ghi nhận nó như metadata quan sát được.

## 3. Đọc propertySources và thứ tự ưu tiên

`propertySources` là mảng các nguồn cấu hình. Mỗi phần tử thường có:

- `name`: tên hoặc vị trí nguồn, thường giúp nhận diện tệp trong Git hay nguồn cấu hình khác.
- `source`: map các khóa và giá trị được cung cấp bởi nguồn đó.

Các nguồn trong phản hồi Config Server được sắp theo thứ tự ưu tiên: nguồn đứng trước có độ ưu tiên cao hơn nguồn đứng sau. Trong ví dụ trên, `billing-api-prod.yml` được xét trước `billing-api.yml`, rồi đến `application.yml`. Nếu cả ba tệp cùng khai báo `acme.billing.connect-timeout`, giá trị từ nguồn ưu tiên cao nhất sẽ được chọn trong kết quả hợp nhất.

Ví dụ các tệp trong Git:

```yaml
# application.yml
acme:
  billing:
    connect-timeout: 1s
    currency: VND
```

```yaml
# billing-api.yml
acme:
  billing:
    connect-timeout: 2s
```

```yaml
# billing-api-prod.yml
acme:
  billing:
    connect-timeout: 4s
```

Với truy vấn `/billing-api/prod/release-2026`, giá trị `connect-timeout` từ tệp profile-specific có thể ghi đè giá trị của tệp ứng dụng và tệp dùng chung. Thuộc tính `currency` chỉ được khai báo trong `application.yml`, vì vậy vẫn được cung cấp từ nguồn dùng chung.

Thứ tự này giải thích cách các nguồn mà Config Server trả về được hợp nhất. Khi Config Client nạp response vào Spring `Environment`, các nguồn cục bộ, biến môi trường, system property hoặc tham số dòng lệnh vẫn có thể có độ ưu tiên cao hơn tùy cơ chế nạp và phiên bản. Do đó, đừng kết luận giá trị cuối cùng của ứng dụng chỉ từ một tệp Git; cần kiểm tra cả response và môi trường của client.

## 4. Nhiều profile và nhiều nguồn

Client có thể yêu cầu nhiều profile:

```yaml
spring:
  profiles:
    active: prod,cloud
```

Config Server sẽ tìm các nguồn phù hợp với application và tập profile đó. Nếu hai profile cùng khai báo một khóa, thứ tự profile và thứ tự property source trong response giúp giải thích giá trị được chọn. Không nên đoán thứ tự bằng tên tệp; hãy đọc chính mảng `propertySources` mà server trả về.

Ví dụ repository có thể gồm:

```text
application.yml
application-prod.yml
application-cloud.yml
billing-api.yml
billing-api-prod.yml
billing-api-cloud.yml
```

Một response có thể có nhiều property source hơn khi client yêu cầu nhiều profile. Mỗi nguồn có thể cung cấp một phần thuộc tính; không nhất thiết mọi tệp đều định nghĩa cùng một khóa. Khi có khóa trùng, vị trí của nguồn trong danh sách là manh mối quan trọng để xác định giá trị thắng tại tầng Config Server.

## 5. Kiểm tra response bằng công cụ dòng lệnh

Có thể dùng `curl` để lấy toàn bộ JSON:

```bash
curl -s "http://localhost:8888/billing-api/prod/release-2026"
```

Nếu có `jq`, lọc metadata trước:

```bash
curl -s "http://localhost:8888/billing-api/prod/release-2026" \
  | jq '{name, profiles, label, version, state}'
```

Liệt kê tên và khóa của từng property source:

```bash
curl -s "http://localhost:8888/billing-api/prod/release-2026" \
  | jq '.propertySources[] | {name, keys: (.source | keys)}'
```

Tìm các nguồn khai báo một khóa cụ thể:

```bash
curl -s "http://localhost:8888/billing-api/prod/release-2026" \
  | jq '.propertySources[] | select(.source["acme.billing.connect-timeout"] != null)'
```

Những lệnh này giúp biết khóa xuất hiện ở nguồn nào và giá trị từng nguồn cung cấp. Không nên đưa toàn bộ response có bí mật vào ticket, log chia sẻ hoặc terminal ghi hình. Nếu response chứa dữ liệu nhạy cảm, chỉ trích xuất metadata và tên khóa cần thiết, đồng thời che giá trị trước khi chia sẻ.

## 6. So sánh response giữa hai lần triển khai

Khi một ứng dụng nhận cấu hình khác với lần trước, hãy lưu metadata của hai response và so sánh:

| Trường | Dấu hiệu cần chú ý |
| --- | --- |
| `name` | Application có bị đổi do cấu hình triển khai không? |
| `profiles` | Có profile mới, thiếu profile hoặc thay đổi thứ tự không? |
| `label` | Client có chuyển từ branch sang tag hoặc commit khác không? |
| `version` | Git commit có thay đổi giữa hai lần lấy cấu hình không? |
| `state` | Backend có cung cấp state marker khác không? |
| `propertySources` | Có tệp mới, tệp mất đi, khóa mới hoặc thứ tự nguồn thay đổi không? |

Nếu `version` thay đổi, nội dung Git mà server đọc có thể đã thay đổi. Nếu `version` không đổi nhưng `profiles` khác, tập tệp được chọn có thể khác dù revision Git giống nhau. Nếu metadata giống nhau nhưng ứng dụng vẫn dùng giá trị khác, kiểm tra các property source khác ở phía client và trạng thái refresh của bean.

## 7. Chẩn đoán lỗi theo từng trường

| Triệu chứng trong response hoặc ứng dụng | Kiểm tra tiếp |
| --- | --- |
| `name` không đúng | `spring.application.name` và `spring.cloud.config.name` |
| `profiles` không đúng | `spring.profiles.active`, `spring.cloud.config.profile` và cách kích hoạt profile theo môi trường |
| `label` khác dự kiến | `spring.cloud.config.label`, label mặc định server và label có tồn tại trong repository |
| `version` là `null` hoặc không đổi | Backend có hỗ trợ metadata version không, Git fetch/clone có cập nhật đúng revision không |
| `state` trống hoặc khác dự kiến | Kiểm tra tài liệu của `EnvironmentRepository`/backend cụ thể; không diễn giải theo quy tắc Git nếu backend không cam kết |
| Thiếu property source | Tên tệp, profile, search paths, label, quyền đọc và trạng thái repository |
| Giá trị trùng khóa không đúng | Thứ tự `propertySources` và các nguồn ưu tiên cao hơn ở Config Client |

Nên bắt đầu từ response của Config Server. Nếu metadata và property source đã đúng, tiếp tục kiểm tra cách Config Client nạp response, thứ tự `Environment` và bean `@ConfigurationProperties` đã bind. Cách tách lớp này giúp phân biệt lỗi truy vấn nguồn với lỗi ghi đè hoặc chuyển đổi giá trị trong ứng dụng.

## 8. Ghi nhận metadata và bảo vệ dữ liệu

Trong mỗi lần triển khai, nên ghi nhận `name`, `profiles`, `label`, `version` và thời điểm client tải cấu hình. Những trường này giúp liên hệ instance ứng dụng với tập cấu hình và revision Git đã dùng. Có thể ghi `state` nếu backend cung cấp và nhóm đã xác định ý nghĩa của nó.

`propertySources` có thể chứa endpoint nội bộ, tên người dùng, khóa hoặc dữ liệu nhạy cảm. Hãy giới hạn quyền truy cập Config Server, dùng TLS và xác thực, bảo vệ log, đồng thời không công khai Actuator hay endpoint cấu hình cho người dùng không được phép. Khi chia sẻ kết quả điều tra, chỉ lưu tên nguồn và các khóa cần thiết; che hoặc loại bỏ giá trị bí mật.

## 9. Quy trình đọc một response

Khi kiểm tra một yêu cầu cấu hình, thực hiện theo thứ tự:

1. Gọi endpoint đúng `/{application}/{profile}/{label}` và kiểm tra HTTP status.
2. Đọc `name`, `profiles` và `label` để xác nhận server đã xử lý đúng bộ ba truy vấn.
3. Ghi nhận `version` và `state` nếu backend cung cấp; với Git, dùng `version` để truy vết commit khi có giá trị.
4. Duyệt `propertySources` từ đầu đến cuối, kiểm tra `name`, các khóa và thứ tự ưu tiên.
5. Với khóa bị ghi đè, xác định nguồn đầu tiên cung cấp khóa đó.
6. Nếu giá trị trong ứng dụng khác response, kiểm tra property source phía client, relaxed binding, conversion và refresh.
7. Che dữ liệu nhạy cảm trước khi lưu hoặc chia sẻ kết quả kiểm tra.

Đọc đúng metadata cùng danh sách `propertySources` cho phép nhóm biết Config Server đã trả về cấu hình nào, từ đâu và theo revision nào. Khi kết hợp với việc kiểm tra `Environment` ở Config Client, quá trình điều tra cấu hình trở nên rõ ràng và có thể lặp lại.
