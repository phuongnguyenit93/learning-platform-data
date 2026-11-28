# KV v1, KV v2 và cách ánh xạ context theo ứng dụng, profile

Spring Cloud Config Server có thể lấy cấu hình từ HashiCorp Vault thông qua Vault Key/Value (KV) secrets engine. Thay vì lưu mọi giá trị trong Git, nhóm vận hành có thể đặt secret theo từng ứng dụng và profile trong Vault. Config Server dùng application name, profile và label của request để tìm đúng context, sau đó tổng hợp các giá trị thành Environment cho Config Client.

Vault KV có hai phiên bản phổ biến. KV v1 lưu một giá trị hiện tại tại mỗi path và không quản lý lịch sử phiên bản. KV v2 lưu các version của secret, có metadata, soft delete và cơ chế kiểm soát ghi như Check-And-Set. Spring Cloud Config cần biết mount đang dùng KV v1 hay KV v2 để gọi đúng API. `kv-version` chọn phiên bản engine; label của Config Server có thể chọn version secret trong KV v2. Hai khái niệm này có vai trò khác nhau.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt data model và API path của Vault KV v1 với KV v2.
- Cấu hình Vault backend trong Spring Cloud Config Server.
- Ánh xạ application name, profile, default key và profile separator thành secret path.
- Hiểu cách Config Server kết hợp cấu hình riêng ứng dụng với cấu hình dùng chung.
- Dùng label để chọn version secret khi backend hỗ trợ.
- Cấp quyền đọc Vault theo path và workload identity của Config Server.
- Kiểm tra Environment response và xử lý lỗi khi context hoặc profile không khớp.

## 1. Vault KV là gì?

KV (Key/Value) secrets engine lưu một tập cặp khóa và giá trị tại một path. Ví dụ, context của `catalog-service` có thể chứa:

```yaml
spring:
  datasource:
    username: catalog_app
    password: ${vault-managed-value}
catalog:
  search:
    timeout: 2s
```

Trong Vault, các giá trị thường được ghi dưới dạng JSON key/value. Ví dụ CLI:

```bash
vault kv put secret/catalog-service,prod \
  spring.datasource.username=catalog_app \
  catalog.search.timeout=2s
```

Tên `secret` là mount path của KV engine. `catalog-service,prod` là path của context theo quy ước profile separator mặc định trong ví dụ. Vault không bắt buộc phải dùng tên mount `secret`; có thể mount engine dưới một tên khác.

Vault KV lưu dữ liệu tĩnh. Nó phù hợp với password ứng dụng, API key và cấu hình nhạy cảm do nhóm vận hành quản lý. Nếu cần credential ngắn hạn có lease và khả năng revoke tự động, hãy đánh giá các secrets engine động như Database hoặc PKI; KV không tự cấp lease cho từng giá trị.

## 2. Khác biệt giữa KV v1 và KV v2

KV v1 và KV v2 có cách lưu trữ và API khác nhau:

| Đặc điểm | KV v1 | KV v2 |
|---|---|---|
| Version history | Không có lịch sử version tích hợp | Có version cho mỗi lần ghi secret. |
| Data API path | `/v1/{mount}/{path}` | `/v1/{mount}/data/{path}` |
| Metadata API | Không có metadata version như KV v2 | `/v1/{mount}/metadata/{path}` |
| Xóa dữ liệu | Xóa giá trị tại path | Có soft delete theo version, undelete và destroy. |
| Check-And-Set | Không có CAS tích hợp | Có thể yêu cầu CAS để tránh ghi đè ngoài ý muốn. |
| Retention | Không có version retention | Có thể đặt `max_versions` và chính sách xóa version. |

KV v2 thêm lớp `data` trong API path và lưu metadata version riêng. Tuy nhiên, khi dùng Vault CLI, người vận hành vẫn thao tác theo logical path như `secret/catalog-service,prod`; CLI tự gọi API `data` phù hợp. Spring Cloud Config cũng xử lý khác biệt API dựa trên cấu hình `kv-version`.

### API path minh họa

Với mount `secret` và context `catalog-service,prod`:

```text
KV v1: GET /v1/secret/catalog-service,prod
KV v2: GET /v1/secret/data/catalog-service,prod
```

Khi cấu hình Config Server, đặt `backend: secret` và `kv-version: 2`. Không tự thêm `/data` vào `backend`; đó là thành phần API path mà client Vault tự xử lý theo phiên bản engine.

## 3. Cấu hình Vault backend trong Config Server

Spring Cloud Config Server có Vault Environment Repository. Ví dụ cấu hình một Vault KV v2 mount:

```yaml
spring:
  cloud:
    config:
      server:
        vault:
          host: vault.internal.example
          port: 8200
          scheme: https
          backend: secret
          default-key: application
          profile-separator: ','
          kv-version: 2
          authentication: TOKEN
          token: ${CONFIG_SERVER_VAULT_TOKEN}
```

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò |
|---|---|
| `host`, `port`, `scheme` | Địa chỉ Vault API và giao thức kết nối. Production nên dùng HTTPS. |
| `backend` | Tên mount của KV engine, ví dụ `secret`. |
| `default-key` | Tên context dùng chung khi không có application-specific value; mặc định thường là `application`. |
| `profile-separator` | Ký tự nối application name với profile trong path; mặc định là dấu phẩy. |
| `kv-version` | Phiên bản KV engine, `1` hoặc `2`. |
| `authentication` | Cơ chế xác thực Config Server với Vault. |
| `token` | Token Vault nếu dùng phương thức TOKEN. |

`CONFIG_SERVER_VAULT_TOKEN` phải được cấp từ secret manager hoặc workload platform. Không đặt token thật trong Git, Dockerfile, image hoặc file cấu hình được commit. Tên thuộc tính và các phương thức xác thực khả dụng có thể thay đổi theo release train; đối chiếu phiên bản Spring Cloud Config đang dùng trước khi triển khai.

## 4. Ánh xạ application name và profile thành context path

Config Client thường khai báo tên ứng dụng bằng `spring.application.name`. Ví dụ:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:https://config.internal.example"
```

Khi client yêu cầu cấu hình cho profile `prod`, Config Server dùng tên ứng dụng và profile để tìm các context tương ứng trong Vault. Với `backend: secret`, `default-key: application` và `profile-separator: ','`, các path logic thường có dạng:

```text
secret/catalog-service,prod
secret/catalog-service
secret/application,prod
secret/application
```

Ý nghĩa:

- `secret/catalog-service,prod`: cấu hình riêng của `catalog-service` cho profile `prod`.
- `secret/catalog-service`: cấu hình mặc định riêng của ứng dụng.
- `secret/application,prod`: cấu hình dùng chung cho profile `prod`.
- `secret/application`: cấu hình dùng chung mặc định.

Các path này mô tả quy ước ánh xạ của Vault backend. Config Server có thể tạo nhiều `PropertySource` từ các context tìm được. Khi cùng một khóa xuất hiện ở nhiều context, hãy kiểm tra thứ tự `propertySources` trong Environment response của phiên bản đang chạy để xác nhận giá trị nào có ưu tiên cao nhất.

## 5. default-key và cấu hình dùng chung

`default-key` xác định tên context dùng chung thay cho tên ứng dụng. Giá trị mặc định thường là `application`. Nếu đặt:

```yaml
spring:
  cloud:
    config:
      server:
        vault:
          default-key: platform
```

thì context dùng chung sẽ dùng `platform`, ví dụ:

```text
secret/platform
secret/platform,prod
```

Điều này cho phép nhóm nền tảng duy trì giá trị mặc định chung mà không cần sao chép vào từng ứng dụng. Chỉ thay `default-key` khi đã thống nhất quy ước path với nhóm quản lý Vault và các client.

Một thiết kế thường gặp:

| Context | Nội dung phù hợp |
|---|---|
| `secret/application` | Cấu hình mặc định dùng chung cho mọi ứng dụng. |
| `secret/application,prod` | Giá trị chung cho các ứng dụng ở production. |
| `secret/catalog-service` | Cấu hình mặc định riêng Catalog. |
| `secret/catalog-service,prod` | Cấu hình riêng Catalog ở production. |

Không đưa mọi secret vào context chung nếu không phải mọi workload đều cần chúng. Cấu hình chung nên chứa giá trị thật sự dùng chung; secret riêng ứng dụng nên nằm trong path riêng để policy có thể giới hạn quyền đọc.

## 6. profile-separator và quy ước đặt tên

`profile-separator` xác định ký tự nối tên ứng dụng với profile. Mặc định là dấu phẩy. Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        vault:
          profile-separator: '-'
```

Với separator là dấu gạch ngang, context production của Catalog có thể được ánh xạ thành:

```text
secret/catalog-service-prod
secret/application-prod
```

Separator cần thống nhất giữa Config Server và quy ước đặt path trong Vault. Nếu thay separator sau khi đã có dữ liệu, Config Server sẽ tìm path theo quy tắc mới; secret cũ có thể trở nên không được tìm thấy.

Tránh dùng tên application hoặc profile có ký tự làm path khó đọc, mơ hồ hoặc không phù hợp policy. Đặt tên ngắn, ổn định, chữ thường và dùng cùng quy ước giữa `spring.application.name`, profile triển khai, Vault path và policy.

## 7. Nhiều profile và precedence

Một ứng dụng có thể chạy với nhiều profile, ví dụ `prod,observability`. Config Client gửi danh sách profile đến Config Server. Vault backend sử dụng application và profile để tìm các context tương ứng; cách ghép profile phụ thuộc `profile-separator` và phiên bản backend.

Không nên tự giả định một context duy nhất sẽ đại diện cho mọi profile. Hãy kiểm tra path thực tế được truy vấn và `profiles`/`propertySources` trong Environment response. Nếu một khóa được định nghĩa ở cả context chung và context riêng, kết quả cuối cùng phụ thuộc thứ tự repository sources do Config Server trả về.

Ví dụ minh họa các giá trị:

| Context | `catalog.search.timeout` |
|---|---|
| `secret/application` | `5s` |
| `secret/application,prod` | `4s` |
| `secret/catalog-service` | `3s` |
| `secret/catalog-service,prod` | `2s` |

Mong muốn thường là giá trị riêng ứng dụng/profile (`2s`) ghi đè mặc định dùng chung (`5s`). Hãy xác nhận thứ tự nguồn thực tế bằng Environment API, thay vì chỉ dựa vào thứ tự path trong bảng minh họa. Khi một khóa nhạy cảm xuất hiện ở nhiều nơi, nên loại bỏ bản sao không cần thiết để giảm nhầm lẫn và rủi ro ghi đè.

## 8. KV v1: lưu một giá trị hiện tại tại mỗi path

KV v1 phù hợp với hệ thống đơn giản cần đọc secret theo path và không yêu cầu version history từ Vault. Ví dụ ghi secret:

```bash
vault secrets enable -path=secret kv

vault kv put secret/catalog-service,prod \
  spring.datasource.username=catalog_app \
  spring.datasource.password='replace-with-secret-from-secure-input'
```

Trong KV v1, mỗi path lưu một map key/value hiện tại. Khi cập nhật path, dữ liệu được ghi tại path đó thay thế nội dung theo semantics của thao tác write; nếu cần giữ lại các khóa cũ, hãy đọc và gửi lại đầy đủ map cần duy trì.

KV v1 không cung cấp version history tích hợp. Nếu ghi nhầm password hoặc xóa một key, khả năng khôi phục phụ thuộc backup hoặc hệ thống quản lý phiên bản bên ngoài. Cần có quy trình backup, audit và kiểm thử restore riêng.

## 9. KV v2: version, metadata và CAS

KV v2 phù hợp khi cần lịch sử secret, rollback theo version và kiểm soát ghi. Bật engine:

```bash
vault secrets enable -path=secret kv-v2
```

Ghi một version mới:

```bash
vault kv put secret/catalog-service,prod \
  spring.datasource.username=catalog_app \
  spring.datasource.password='replace-with-secret-from-secure-input'
```

Mỗi lần ghi tạo một version mới. Có thể xem metadata/version bằng lệnh Vault CLI phù hợp, ví dụ:

```bash
vault kv metadata get secret/catalog-service,prod
```

KV v2 hỗ trợ Check-And-Set (CAS) để ngăn một writer ghi đè nếu version hiện tại không còn là version mà writer mong đợi. Ví dụ:

```bash
vault kv put -cas=3 secret/catalog-service,prod \
  spring.datasource.username=catalog_app
```

CAS giúp phát hiện cập nhật đồng thời, nhưng writer vẫn cần gửi đầy đủ dữ liệu cần giữ lại theo semantics của lệnh ghi. Không coi CAS là cơ chế phân quyền; policy vẫn quyết định ai được read, create, update, delete hoặc destroy.

KV v2 có thể soft-delete một version, undelete version đã soft-delete hoặc destroy version vĩnh viễn. Lệnh `vault kv delete` thường soft-delete version hiện tại; `vault kv destroy` hủy nội dung của version chỉ định. Xóa metadata path có thể xóa toàn bộ lịch sử version, nên cần quyền rất hạn chế.

## 10. Label và version của KV v2

Config Server REST endpoint có dạng:

```text
/{application}/{profile}[/{label}]
```

Với Vault KV v2, label có thể được dùng để chọn version của secret thay vì luôn đọc version mới nhất. Ví dụ request:

```bash
curl https://config.internal.example/catalog-service/prod/3
```

Trong ví dụ, label `3` biểu thị version secret cần đọc theo hỗ trợ của Vault backend. Cần dùng label phù hợp với version tồn tại ở các path mà request cần truy cập. Không nhầm label của Vault KV v2 với Git branch hoặc tag; chúng là các khái niệm khác nhau.

KV v1 không có version history tích hợp, vì vậy không thể cung cấp semantics version như KV v2. Nếu ứng dụng cần rollback cấu hình theo label, hãy dùng KV v2 hoặc một cơ chế versioning bên ngoài đã được thiết kế rõ.

Trong production, nên ghi lại application, profile, label và version Vault đã phát hành. Khi cần rollback, chuyển request về version đã xác minh hoặc phát hành version secret mới chứa dữ liệu khôi phục, tùy chính sách và khả năng của backend.

## 11. Cấu hình Config Server với KV v1 và KV v2

Chỉ khác phiên bản KV trong thuộc tính `kv-version`; các thuộc tính kết nối và ánh xạ context vẫn theo cùng một quy ước.

KV v1:

```yaml
spring:
  cloud:
    config:
      server:
        vault:
          host: vault.internal.example
          port: 8200
          scheme: https
          backend: secret
          default-key: application
          profile-separator: ','
          kv-version: 1
          authentication: TOKEN
          token: ${CONFIG_SERVER_VAULT_TOKEN}
```

KV v2:

```yaml
spring:
  cloud:
    config:
      server:
        vault:
          host: vault.internal.example
          port: 8200
          scheme: https
          backend: secret
          default-key: application
          profile-separator: ','
          kv-version: 2
          authentication: TOKEN
          token: ${CONFIG_SERVER_VAULT_TOKEN}
```

Không đặt `kv-version: 2` nếu mount thực tế đang chạy KV v1. Khi không khớp, Config Server gọi sai API path và có thể nhận lỗi 404 hoặc lỗi định dạng response. Hãy xác nhận loại engine tại mount path trước khi bật backend.

## 12. Xác thực Config Server với Vault

Config Server là workload truy cập Vault. Token hoặc credential dùng cho Vault phải thuộc về Config Server, không phải Config Client. Client chỉ gọi Config Server; Config Server đọc secret theo policy được cấp.

Một số phương thức xác thực thường dùng tùy phiên bản và môi trường:

| Phương thức | Trường hợp sử dụng | Lưu ý |
|---|---|---|
| Token | Môi trường nhỏ hoặc tích hợp đã có token cấp sẵn | Token cần TTL, policy hẹp và rotation. |
| AppRole | Workload server cần xác thực bằng Role ID/Secret ID | Secret ID phải được cấp an toàn, có thể giới hạn thời gian/số lần dùng. |
| Kubernetes auth | Config Server chạy trong Kubernetes | Dùng service account identity và Vault role/policy tương ứng. |
| Cloud IAM auth | Workload chạy trên cloud có identity provider được Vault hỗ trợ | Ưu tiên workload identity thay cho key tĩnh khi khả dụng. |

Không sao chép token vào Config Client, không đặt token trong Git và không dùng root token cho ứng dụng. Cấp một danh tính riêng cho mỗi Config Server environment để có thể thu hồi quyền độc lập.

## 13. Policy Vault theo application và profile

Policy cần cho phép Config Server đọc đúng các path cần thiết. Ví dụ minh họa với KV v1 mount `secret`:

```hcl
path "secret/catalog-service*" {
  capabilities = ["read"]
}

path "secret/application*" {
  capabilities = ["read"]
}
```

Với KV v2, API data path có thêm segment `data`:

```hcl
path "secret/data/catalog-service*" {
  capabilities = ["read"]
}

path "secret/data/application*" {
  capabilities = ["read"]
}
```

Đây là policy minh họa cho Config Server cần đọc cấu hình Catalog và context dùng chung. Trong môi trường thật, hãy thu hẹp wildcard theo path và profile thực tế. Nếu backend hoặc tính năng đang dùng cần truy cập metadata endpoint, cấp thêm quyền metadata tối thiểu theo tài liệu Vault tương ứng; không cấp `list`, `create`, `update`, `delete` hoặc `sudo` nếu workload chỉ cần đọc.

Lưu ý: Vault policy đánh giá API path, không phải logical path hiển thị trong lệnh CLI. Với KV v2, đọc dữ liệu cần quyền trên `secret/data/...`; quyền metadata là một path khác. Kiểm thử policy bằng token của Config Server trước khi triển khai.

## 14. TLS, namespace và phân tách môi trường

Kết nối Config Server đến Vault cần được bảo vệ bằng TLS. Config Server phải xác minh certificate và hostname của Vault; không dùng chế độ bỏ qua xác minh SSL trong production để xử lý lỗi CA.

Nếu dùng Vault Enterprise, namespace có thể được cấu hình để request đi đúng tenant/namespace. Namespace không thay thế policy; workload vẫn cần policy đọc path trong namespace đó.

Tách mount hoặc namespace theo môi trường giúp giảm blast radius:

```text
secret-dev/...
secret-test/...
secret-prod/...
```

Hoặc dùng namespace và policy riêng cho dev, test, production. Không dùng cùng token có quyền đọc mọi môi trường cho tất cả Config Server instance. Nếu một ứng dụng test bị xâm nhập, danh tính của nó không nên có khả năng đọc secret production.

## 15. Kiểm tra Environment response và path được ánh xạ

Sau khi cấu hình Vault backend, gọi Environment endpoint của Config Server:

```bash
curl -H "Accept: application/json" \
  https://config.internal.example/catalog-service/prod
```

Kiểm tra các trường `name`, `profiles`, `label`, `version` và `propertySources`. Mỗi `propertySource.name` giúp nhận diện context hoặc path đã đóng góp dữ liệu; `source` chứa các khóa được trả về.

Quy trình kiểm tra:

1. Xác nhận `spring.application.name` đúng với application path trong Vault.
2. Xác nhận active profile và profile separator.
3. Xác nhận `backend` trỏ đúng mount path và `kv-version` khớp engine.
4. Kiểm tra Config Server có quyền đọc path application-specific và default-key.
5. Kiểm tra label/version nếu request có label.
6. Đọc thứ tự `propertySources` và xác nhận khóa trùng được ưu tiên đúng.
7. Kiểm tra Config Client có nguồn local nào ghi đè giá trị từ Config Server hay không.

Không dump toàn bộ `source` vào log vì response có thể chứa password, token hoặc endpoint nội bộ. Khi chẩn đoán, chỉ ghi tên path, profile, label, version và tên khóa cần kiểm tra; che giá trị nhạy cảm.

## 16. Lỗi thường gặp khi ánh xạ Vault context

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| 404 hoặc không tìm thấy secret | Sai backend mount, application, profile hoặc separator | So sánh path logical trong Vault với application/profile của request. |
| Lỗi API path khi dùng KV v2 | `kv-version` không khớp mount hoặc tự thêm `/data` vào backend | Đặt backend là mount path và `kv-version: 2`. |
| 403 permission denied | Token thiếu quyền read trên API path | Kiểm tra policy `secret/data/...` với KV v2 hoặc `secret/...` với KV v1. |
| Có cấu hình chung nhưng thiếu cấu hình riêng | Sai application name hoặc path riêng chưa được tạo | Kiểm tra `spring.application.name` và context `catalog-service,...`. |
| Giá trị từ profile khác thắng | Separator, active profiles hoặc thứ tự PropertySource không như dự kiến | Kiểm tra profiles và response `propertySources`. |
| Label không đọc được | KV v1 không có version hoặc version KV v2 không tồn tại | Xác nhận engine version và version secret tại path. |
| Config Server không xác thực được | Token hết hạn, AppRole/Kubernetes role sai hoặc namespace không khớp | Kiểm tra auth method, identity và audit log Vault. |
| TLS handshake lỗi | CA/hostname/certificate không hợp lệ | Cấu hình trust đúng; không tắt certificate validation. |

Hãy kiểm tra theo thứ tự: kết nối TLS → xác thực Vault → policy → mount/engine version → application/profile path → label/version → property source precedence. Trình tự này giúp tách lỗi kết nối khỏi lỗi ánh xạ context.

## 17. Quản lý secret lifecycle và rollback

Với KV v2, version history hỗ trợ kiểm tra và khôi phục giá trị trước đó. Tuy nhiên, rollback secret không tự động đồng nghĩa rollback an toàn cho ứng dụng. Một password cũ có thể đã bị revoke ở database; một token cũ có thể đã hết hạn hoặc bị thu hồi.

Quy trình phát hành nên gồm:

1. Review thay đổi secret và xác định application/profile path bị ảnh hưởng.
2. Ghi version mới trong Vault và giữ metadata phù hợp.
3. Kiểm tra Config Server đọc được version mới bằng một Environment request.
4. Phát refresh đến client theo rollout/canary đã định.
5. Kiểm tra health, kết nối database/API và lỗi xác thực.
6. Nếu cần rollback, xác minh secret version cũ còn hợp lệ ở hệ thống đích trước khi chọn lại version.
7. Ghi nhận version, người thay đổi và thời điểm triển khai mà không ghi plaintext.

Đặt `max_versions` và retention phù hợp để giữ đủ lịch sử cần thiết nhưng không lưu dữ liệu nhạy cảm lâu hơn chính sách. Hạn chế quyền `destroy` và xóa metadata vì đây là thao tác khó hoặc không thể khôi phục.

## 18. Những điểm cần ghi nhớ

- Vault KV v1 lưu một giá trị hiện tại tại path; KV v2 có version history, metadata, soft delete và CAS.
- Với KV v2, API data path có segment `/data/`; cấu hình Config Server vẫn dùng mount path trong `backend` và chọn `kv-version: 2`.
- Config Server ánh xạ application, profile, `default-key` và `profile-separator` thành các Vault context path.
- `default-key` thường là `application`, dùng cho cấu hình chung; application-specific path dành cho cấu hình riêng.
- Label có thể chọn version secret với KV v2; không nhầm label này với Git branch/tag.
- Config Server là workload xác thực với Vault; Config Client không cần giữ Vault token.
- Policy phải cấp đúng quyền read trên API path: KV v1 và KV v2 có path khác nhau.
- Xác nhận `propertySources`, version và path thực tế trước khi refresh client.
- Bảo vệ Vault bằng TLS, workload identity, policy tối thiểu, audit và quy trình rotation/rollback.

Khi tổ chức Vault context theo application và profile, một Config Server có thể phân phối cấu hình riêng và cấu hình dùng chung mà không buộc các ứng dụng phải biết cấu trúc nội bộ của Vault. Chọn đúng KV version, separator, policy và label giúp quá trình lấy secret có thể dự đoán, kiểm tra và rollback theo từng lần phát hành.

## Tài liệu tham khảo

- [Spring Cloud Config – Vault Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/vault-backend.html)
- [HashiCorp Vault – KV Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/kv)
- [HashiCorp Vault – KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault – Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
