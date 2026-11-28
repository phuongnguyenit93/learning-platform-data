# Sai tên ứng dụng, profile, label hoặc vị trí tệp cấu hình

Khi Config Client không nhận được cấu hình mong đợi, nguyên nhân thường nằm ở một trong bốn đầu vào: application name, profile, label hoặc vị trí file trong repository. Các giá trị này xác định Config Server sẽ tìm context nào và lấy revision nào. Chỉ cần một giá trị sai, server có thể trả Environment rỗng, trả cấu hình của ứng dụng khác hoặc không tìm thấy file dù Git repository vẫn truy cập bình thường.

Cách chẩn đoán đáng tin cậy là kiểm tra request trực tiếp trên Config Server trước, sau đó đối chiếu metadata và **propertySources** trong response, rồi mới kiểm tra Config Client. Không nên sửa đồng thời tên file, profile và label vì sẽ làm mất dấu nguyên nhân ban đầu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Đọc đúng endpoint Environment API của Config Server.
- Phân biệt application name, profile và label.
- Tìm file cấu hình theo quy ước đặt tên và search path.
- Kiểm tra cấu hình chung, cấu hình riêng ứng dụng và cấu hình theo profile.
- Dùng **propertySources** và **version** để xác định file/revision thực sự được nạp.
- Phân loại lỗi 404, Environment rỗng, sai profile và sai label.
- Lập runbook chẩn đoán mà không làm lộ secret.

## 1. Bốn đầu vào quyết định Config Server tìm gì

Một request Config Server thường có dạng:

```text
GET /{application}/{profile}[/{label}]
```

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **application** | Tên ứng dụng cần lấy cấu hình | **catalog-service** |
| **profile** | Profile hoặc danh sách profile cần áp dụng | **prod**, **prod,metrics** |
| **label** | Nhánh, tag hoặc commit được chọn ở backend có hỗ trợ | **config-release-2026.11** |
| File/search path | Vị trí Config Server tìm file trong repository | **catalog-service-prod.yml**, **config/catalog/** |

Ví dụ request đầy đủ:

```bash
curl -i "https://config.internal.example/catalog-service/prod/config-release-2026.11"
```

Request trên yêu cầu cấu hình cho application **catalog-service**, profile **prod**, tại label **config-release-2026.11**. Nếu request sai một trong ba thành phần đầu, việc tìm file có thể không cho kết quả như mong muốn.

File path là bước tiếp theo: dù application/profile/label đúng, file vẫn không được nạp nếu nó nằm ngoài search path hoặc không tuân theo tên mà backend đang tìm.

## 2. Xác định application name mà client thực sự gửi

Thông thường, Config Client lấy application name từ **spring.application.name**:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:https://config.internal.example"
```

Tên này được dùng để tạo request đến Config Server. Tên file cấu hình theo ứng dụng phải khớp với application name theo quy ước của backend, ví dụ **catalog-service.yml** hoặc **catalog-service-prod.yml**.

Config Client cũng có thể cấu hình **spring.cloud.config.name** để chỉ định tên context khác. Khi thuộc tính này được đặt, cần kiểm tra giá trị cuối cùng mà client dùng thay vì chỉ nhìn **spring.application.name**.

Ví dụ cố ý dùng tên context khác:

```yaml
spring:
  application:
    name: catalog-api
  cloud:
    config:
      name: catalog-service
```

Trong trường hợp này, request có thể tìm cấu hình theo **catalog-service**. Nếu repository chỉ có **catalog-api.yml**, file đó có thể không được chọn.

Các điểm cần kiểm tra:

- **spring.application.name** có được đặt ở đúng ứng dụng không?
- Có biến môi trường hoặc tham số dòng lệnh ghi đè tên ứng dụng không?
- Có cấu hình **spring.cloud.config.name** không?
- Tên trong request URL có đúng với tên file/context trong Git không?
- Có khác biệt dấu gạch ngang, dấu gạch dưới hoặc chữ hoa/chữ thường không?

Trên filesystem Linux, tên file có phân biệt chữ hoa/chữ thường. **Catalog-Service.yml** và **catalog-service.yml** có thể là hai tên khác nhau.

## 3. Kiểm tra profile được gửi

Config Client thường dùng profile đang hoạt động để yêu cầu cấu hình. Ví dụ:

```yaml
spring:
  application:
    name: catalog-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal.example"
```

Client có thể cấu hình profile yêu cầu rõ ràng bằng **spring.cloud.config.profile**. Nếu thuộc tính này được đặt, hãy xác minh nó có phù hợp với profile mà bạn nghĩ ứng dụng đang chạy hay không.

Các tình huống thường gây nhầm lẫn:

- Máy local đang chạy **dev** nhưng deployment manifest bật **prod**.
- Profile được đặt bằng biến môi trường **SPRING_PROFILES_ACTIVE**.
- Có nhiều profile đang active, ví dụ **prod,metrics**.
- **spring.cloud.config.profile** ghi đè profile dự định.
- Một profile được kích hoạt theo group hoặc cấu hình triển khai khác.

Có thể xem profile thực tế trong log khởi động hoặc metadata của Environment response. Không nên suy ra profile chỉ từ tên namespace hoặc tên deployment.

### Nhiều profile

Ví dụ request với hai profile:

```bash
curl -i "https://config.internal.example/catalog-service/prod,metrics"
```

Config Server sẽ tổng hợp các nguồn theo profile được yêu cầu. Các file profile-specific có thể cùng đóng góp property. Hãy đọc trường **profiles** trong response và thứ tự **propertySources** để biết server đã xử lý những profile nào.

Không tự ý thêm profile vào URL để “thử cho đến khi chạy”. Mỗi profile có thể thay đổi endpoint, credential hoặc feature flag; chỉ yêu cầu profile mà deployment thực sự dự định sử dụng.

## 4. Kiểm tra label: branch, tag hay commit

Label xác định revision backend mà Config Server sử dụng. Với Git backend, label thường là branch, tag hoặc commit ID mà Git có thể phân giải.

Config Client có thể ghim label:

```yaml
spring:
  cloud:
    config:
      label: config-release-2026.11
```

Nếu không đặt label, Config Server dùng default label của backend. Giá trị default có thể khác theo cấu hình và phiên bản, vì vậy không nên giả định nó luôn là **main** hoặc **master**.

Chẩn đoán label:

1. Kiểm tra **spring.cloud.config.label** ở client.
2. Kiểm tra label trong URL Environment API.
3. Xác nhận branch/tag/commit tồn tại trên remote repository.
4. Xác nhận Config Server có quyền fetch ref đó.
5. So sánh trường **label** và **version** trong Environment response.
6. Kiểm tra các Config Server replica có cùng revision hay không.

Có thể xác minh tag/branch ở phía Git:

```bash
git ls-remote --heads --tags https://git.example.internal/platform/config-repo.git
```

Nếu dùng commit SHA, bảo đảm commit vẫn có thể được fetch từ remote và không bị loại khỏi lịch sử mà server có thể truy cập. Với release production, tag được bảo vệ hoặc commit SHA đã được ghi trong release manifest giúp tái hiện cấu hình dễ hơn branch có thể di chuyển.

### Label có dấu gạch chéo

Branch name có thể chứa dấu slash, ví dụ **release/2026.11**. Khi dùng label như một path segment, cần xử lý URL encoding và reverse proxy path decoding đúng cách. Nếu proxy loại bỏ hoặc giải mã slash trước khi request tới Config Server, server có thể nhận sai label. Dùng tag tên đơn giản, không chứa slash, thường dễ vận hành hơn.

## 5. Quy ước tên file cấu hình trong Git backend

Với Git backend mặc định, Config Server tìm các file cấu hình theo application và profile. Một repository đơn giản có thể có cấu trúc:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── catalog-service.yml
├── catalog-service-prod.yml
├── inventory-service.yml
└── inventory-service-prod.yml
```

Ý nghĩa:

| File | Phạm vi |
|---|---|
| **application.yml** | Cấu hình chung cho mọi ứng dụng/profile. |
| **application-prod.yml** | Cấu hình chung cho profile **prod**. |
| **catalog-service.yml** | Cấu hình mặc định của Catalog. |
| **catalog-service-prod.yml** | Cấu hình Catalog cho profile **prod**. |
| **inventory-service.yml** | Cấu hình mặc định của Inventory. |
| **inventory-service-prod.yml** | Cấu hình Inventory cho profile **prod**. |

Ví dụ, request **/catalog-service/prod** có thể tổng hợp các file chung và riêng tương ứng. Không cần tạo mọi file cho mọi ứng dụng; chỉ tạo file khi có thuộc tính cần định nghĩa.

Tên file phải khớp application name và profile. Các lỗi dễ gặp:

- Dùng **catalog.yml** trong khi application name là **catalog-service**.
- Đặt **catalog-service-production.yml** trong khi client yêu cầu profile **prod**.
- Đặt sai phần mở rộng, ví dụ **.yaml.txt**.
- File nằm ở thư mục không nằm trong search path.
- File được commit vào branch khác với label client đang yêu cầu.
- File tồn tại local nhưng chưa được push lên remote.

## 6. Hiểu thứ tự ưu tiên của file và PropertySource

Config Server trả một Environment chứa danh sách **propertySources**. Mỗi nguồn thường có tên cho biết file hoặc context đã đóng góp thuộc tính. Danh sách này quan trọng khi cùng một key được khai báo ở nhiều file.

Ví dụ:

```yaml
# application.yml
catalog:
  search:
    timeout: 5s
```

```yaml
# catalog-service-prod.yml
catalog:
  search:
    timeout: 2s
```

Khi request cho **catalog-service** và **prod**, nguồn riêng ứng dụng/profile thường có độ ưu tiên cao hơn nguồn chung. Giá trị hiệu lực có thể là **2s**.

Trong Environment response, xem phần tử đầu của **propertySources** trước; các nguồn được liệt kê theo thứ tự ưu tiên. Tên và thứ tự cụ thể phụ thuộc backend và cách tổng hợp nguồn, vì vậy hãy kiểm tra response thật thay vì chỉ dựa vào tên file.

Ví dụ response rút gọn:

```json
{
  "name": "catalog-service",
  "profiles": ["prod"],
  "label": "config-release-2026.11",
  "version": "4f2c9a7d8e6b1c0a",
  "propertySources": [
    {
      "name": "https://git.example/config-repo/catalog-service-prod.yml",
      "source": {
        "catalog.search.timeout": "2s"
      }
    },
    {
      "name": "https://git.example/config-repo/application.yml",
      "source": {
        "catalog.search.timeout": "5s"
      }
    }
  ]
}
```

Khi kiểm tra response thực tế, không copy toàn bộ **source** vào ticket hoặc log nếu nó có password, token hoặc dữ liệu nhạy cảm. Chỉ ghi tên property và giá trị không nhạy cảm cần đối chiếu.

## 7. Kiểm tra search-paths của Git backend

Nếu file nằm trong thư mục con, Config Server cần tìm đúng thư mục đó. Thuộc tính **spring.cloud.config.server.git.search-paths** cho phép khai báo một hoặc nhiều đường dẫn tương đối với repository.

Ví dụ repository:

```text
config-repo/
├── shared/
│   └── application.yml
└── services/
    ├── catalog/
    │   ├── catalog-service.yml
    │   └── catalog-service-prod.yml
    └── inventory/
        ├── inventory-service.yml
        └── inventory-service-prod.yml
```

Cấu hình search paths:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          search-paths:
            - shared
            - services/catalog
            - services/inventory
```

Nếu Config Server chỉ tìm ở repository root, file trong **services/catalog** có thể không được phát hiện. Đối chiếu search path với vị trí thật của file trong commit được chọn.

Search paths cũng có thể dùng placeholder như **{application}**, **{profile}** hoặc **{label}** theo khả năng của Git backend:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          search-paths:
            - '{application}'
            - '{application}/{profile}'
```

Khi dùng placeholder, kiểm tra đường dẫn được mở rộng có tồn tại trong repository. Một path chứa tên profile có thể không tồn tại cho profile khác; cần bảo đảm cấu trúc thư mục và quy tắc fallback phù hợp.

## 8. Kiểm tra Native backend và vị trí file trên filesystem

Nếu Config Server dùng Native Environment Repository, file được đọc từ filesystem hoặc classpath thay vì Git. Cấu hình thường có dạng:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/opt/config-repo
            - file:/opt/config-repo/{application}
```

Kiểm tra:

- Profile **native** đã được kích hoạt trên Config Server chưa?
- Đường dẫn tuyệt đối có tồn tại trong container/VM chạy Config Server không?
- User chạy process có quyền đọc file không?
- Volume đã mount vào đúng container path chưa?
- Placeholder **{application}** hoặc **{profile}** có tạo ra thư mục đúng không?
- File được cập nhật trong volume thực sự là file mà process đang đọc không?

Đường dẫn trên máy developer không nhất thiết tồn tại trong container. Ví dụ **C:\configs** trên Windows không tương đương **/opt/config-repo** trong Linux container.

Nếu dùng classpath location, file phải nằm trong artifact/classpath theo đúng cấu trúc build. Thay file trên máy chủ mà không cập nhật artifact có thể không thay đổi nguồn cấu hình mà server đang đọc.

## 9. Dùng Environment API để xác minh độc lập

Trước khi kiểm tra Config Client, gọi trực tiếp Config Server với đúng application, profile và label:

```bash
curl -i -H "Accept: application/json" "https://config.internal.example/catalog-service/prod/config-release-2026.11"
```

Đọc các trường sau:

| Trường | Cần xác minh |
|---|---|
| **name** | Có đúng application yêu cầu không? |
| **profiles** | Có đúng profile và thứ tự profile không? |
| **label** | Có đúng label được yêu cầu không? |
| **version** | Có phải revision dự kiến không? |
| **propertySources** | Có file/context mong đợi không? |
| **propertySources[].name** | Nguồn có trỏ đến đúng file/path không? |

HTTP 200 không luôn có nghĩa file ứng dụng đã được tìm thấy. Một số cấu hình Config Server cho phép trả Environment rỗng khi không tìm thấy nguồn. Hãy xem **propertySources** có rỗng không và kiểm tra thuộc tính **spring.cloud.config.server.accept-empty** nếu cần thay đổi hành vi trả kết quả rỗng.

Nếu server trả đúng Environment API, nhưng client vẫn dùng giá trị cũ, chuyển sang kiểm tra client request, profile runtime, Config Data import, cache và refresh lifecycle. Đừng tiếp tục di chuyển file trong Git khi response của server đã đúng.

## 10. Kiểm tra cấu hình Config Client

Ví dụ Config Client dùng Config Data import:

```yaml
spring:
  application:
    name: catalog-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: config-release-2026.11
```

Đối chiếu các giá trị client với request đã kiểm tra trực tiếp:

- **spring.application.name** hoặc **spring.cloud.config.name**.
- **spring.profiles.active** hoặc **spring.cloud.config.profile**.
- **spring.cloud.config.label**.
- URL trong **spring.config.import** hoặc **spring.cloud.config.uri**.
- Có **optional:** trước **configserver:** hay không.

Nếu import dùng **optional:configserver:**, ứng dụng có thể tiếp tục khởi động khi Config Server không truy cập được. Điều này hữu ích ở local nếu có cấu hình dự phòng, nhưng production có thể khởi động với cấu hình thiếu. Khi ứng dụng cần cấu hình trung tâm để hoạt động đúng, hãy cân nhắc import bắt buộc và fail-fast phù hợp.

Với cơ chế bootstrap legacy, một số thuộc tính Config Client được đặt trong **bootstrap.yml** hoặc bootstrap context. Đừng trộn cấu hình legacy với Config Data import nếu chưa xác định cơ chế khởi động của dự án.

## 11. Triệu chứng và nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| HTTP 404 | Sai application/profile/label, endpoint hoặc file không được tìm thấy | Gọi Environment API với từng giá trị rõ ràng; kiểm tra backend và search path. |
| HTTP 200 nhưng **propertySources** rỗng | Không có file phù hợp hoặc backend cho phép empty Environment | Kiểm tra tên file, label, profile, path và **accept-empty**. |
| Có cấu hình chung nhưng thiếu cấu hình ứng dụng | Tên application sai hoặc file riêng đặt sai vị trí | So sánh **name** trong response với tên file. |
| Có cấu hình mặc định nhưng thiếu cấu hình **prod** | Profile request không phải **prod** hoặc file profile-specific sai tên | Kiểm tra **profiles** và tên **\*-prod.yml**. |
| Nhận giá trị của profile khác | Active profile bị ghi đè hoặc nhiều profile đang cùng hoạt động | Kiểm tra môi trường chạy và **profiles** response. |
| File tồn tại trong Git nhưng không được nạp | File nằm ngoài **search-paths** hoặc sai branch/tag | Kiểm tra path trong commit được chọn và cấu hình search path. |
| Đúng file nhưng giá trị cũ thắng | Property key xuất hiện trong nguồn có ưu tiên cao hơn | Kiểm tra thứ tự **propertySources** và nguồn ghi đè. |
| Một Config Server trả đúng, server khác trả sai | Replica khác revision, search path hoặc cấu hình backend | So sánh **version**, **label** và cấu hình server. |
| Local chạy đúng, container chạy sai | Biến môi trường, profile hoặc mount path khác | Kiểm tra cấu hình runtime trong container. |

## 12. Chẩn đoán theo thứ tự, không sửa nhiều thứ cùng lúc

Thực hiện theo trình tự sau để thu hẹp phạm vi:

1. **Ghi lại request thực tế.** Xác định host, application, profile và label.
2. **Gọi Environment API trực tiếp.** Dùng cùng ba tham số và lưu response đã che giá trị nhạy cảm.
3. **Kiểm tra metadata.** So sánh **name**, **profiles**, **label** và **version**.
4. **Kiểm tra nguồn.** Đọc **propertySources[].name** để biết file/path đã được nạp.
5. **Kiểm tra Git revision.** Xác nhận file tồn tại trong commit/tag mà server đã checkout.
6. **Kiểm tra search path.** Đối chiếu **search-paths** hoặc **search-locations** với đường dẫn file.
7. **Kiểm tra precedence.** Tìm key trùng trong nguồn có ưu tiên cao hơn.
8. **Kiểm tra Config Client.** Xác minh tên, profile, label, URL và cơ chế import.
9. **So sánh replica.** Gọi từng Config Server instance để phát hiện lệch revision.
10. **Chỉ sửa một nguyên nhân mỗi lần.** Gọi lại cùng request để xác nhận kết quả trước khi refresh client.

Cách này giữ được bằng chứng trước/sau và giúp tránh sửa nhầm cấu hình đang hoạt động.

## 13. Runbook với một ví dụ cụ thể

Giả sử **catalog-service** cần profile **prod**, label **release-2026.11**, nhưng response không có **catalog.search.timeout**.

**Bước 1: gọi đúng request**

```bash
curl -sS "https://config.internal.example/catalog-service/prod/release-2026.11"
```

**Bước 2: xác minh metadata**

- **name** phải là **catalog-service**.
- **profiles** phải chứa **prod**.
- **label** phải là **release-2026.11**.
- **version** phải khớp commit đã phát hành.

**Bước 3: tìm file trong repository**

Kiểm tra commit tương ứng có file **catalog-service-prod.yml** hoặc file profile tương đương trong một thư mục thuộc **search-paths**.

**Bước 4: kiểm tra nguồn chung và nguồn riêng**

Nếu **catalog.search.timeout** có trong **application.yml** nhưng không có trong **catalog-service-prod.yml**, giá trị chung có thể vẫn được trả. Nếu key có ở nhiều nguồn, xác định nguồn nào đứng trước trong **propertySources**.

**Bước 5: kiểm tra client**

So sánh **spring.application.name**, active profile và **spring.cloud.config.label** của process đang chạy với request đã gọi thủ công.

**Bước 6: xác nhận sau sửa**

Gọi lại cùng Environment API. Chỉ sau khi response có đúng property và revision mới, mới yêu cầu client refresh hoặc rollout theo quy trình.

## 14. Log và thông tin chẩn đoán an toàn

Có thể tăng mức log cho Config Server trong thời gian điều tra:

```yaml
logging:
  level:
    org.springframework.cloud.config.server: DEBUG
    org.springframework.cloud.config.client: DEBUG
```

Chỉ bật DEBUG trong khoảng thời gian cần thiết và kiểm tra nội dung log trước khi chia sẻ. Không bật logging body hoặc dump toàn bộ Environment nếu có secret.

Thông tin hữu ích để ghi nhận:

- Request path gồm application, profile và label.
- Config Server instance nhận request.
- Git commit/version hoặc revision backend.
- Tên **propertySources** và file path.
- HTTP status và exception type.
- Thời gian truy cập backend.

Không ghi:

- Password, API token, private key.
- Toàn bộ response **source** có thể chứa secret.
- Authorization header hoặc webhook secret.
- URL có userinfo/credential nhúng trong đó.

Khi gửi log cho nhóm khác, che host nội bộ hoặc thông tin định danh nếu chính sách bảo mật yêu cầu.

## 15. Checklist trước khi kết luận lỗi

- [ ] Application name trong request khớp **spring.application.name** hoặc **spring.cloud.config.name**.
- [ ] Profile trong request khớp profile runtime.
- [ ] Label tồn tại và trỏ đến revision dự kiến.
- [ ] File có tên và extension đúng.
- [ ] File nằm trong Git revision đã được Config Server checkout.
- [ ] Git **search-paths** hoặc Native **search-locations** bao phủ thư mục chứa file.
- [ ] Config Server response có đúng **name**, **profiles**, **label**, **version**.
- [ ] **propertySources** có nguồn mong đợi.
- [ ] Thứ tự property source không làm một key khác ghi đè.
- [ ] Các Config Server replica trả cùng revision.
- [ ] Config Client dùng đúng URL/import và không bỏ qua nguồn bắt buộc.
- [ ] Log và response được chia sẻ đã che secret.

## 16. Những điểm cần ghi nhớ

- Application name chọn bộ file/context theo ứng dụng; profile chọn cấu hình theo môi trường/chức năng; label chọn revision backend.
- **spring.application.name** thường là tên application Config Client yêu cầu; **spring.cloud.config.name** có thể thay đổi tên context.
- Profile thực tế cần được xác minh từ runtime và trường **profiles** trong response.
- Label có thể là branch, tag hoặc commit; nên dùng tag/revision đã được phê duyệt cho release.
- **application.yml** là nguồn chung; file theo application/profile bổ sung hoặc ghi đè theo thứ tự PropertySource.
- Git **search-paths** và Native **search-locations** quyết định nơi Config Server tìm file.
- HTTP 200 không đảm bảo có file phù hợp; luôn kiểm tra **propertySources**.
- **version** giúp xác định revision thực tế, còn **label** cho biết reference được yêu cầu.
- Khi Config Server trả đúng response nhưng client sai, chuyển sang điều tra Config Client và refresh lifecycle.
- Chỉ thay đổi một đầu vào mỗi lần và xác minh lại cùng request để giữ được nguyên nhân.

## Tài liệu tham khảo

- [Spring Cloud Config – Server Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Cloud Config – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config – Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)

