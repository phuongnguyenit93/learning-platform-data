# Thứ tự repository và xử lý trùng khóa bằng order

Một hệ thống có thể cần nhiều nguồn cấu hình: repository Git dùng chung cho các dịch vụ, repository riêng cho từng ứng dụng, hoặc một kho bí mật như Vault. Spring Cloud Config Server có thể kết hợp nhiều `EnvironmentRepository` để tạo một Environment response. Khi các nguồn cùng khai báo một khóa, thứ tự repository quyết định giá trị nào được ưu tiên.

Với composite repository, thứ tự khai báo trong danh sách `spring.cloud.config.server.composite` quyết định độ ưu tiên: repository đứng trước có ưu tiên cao hơn và ghi đè giá trị trùng từ repository đứng sau. Khi kết hợp các backend theo profile riêng như Git và Vault, thuộc tính `order` điều khiển thứ tự; số `order` càng nhỏ thì độ ưu tiên càng cao. Hiểu đúng hai cách cấu hình này giúp tránh tình trạng một giá trị dùng chung vô tình ghi đè cấu hình riêng của ứng dụng, hoặc ngược lại.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của `CompositeEnvironmentRepository` trong Config Server.
- Cấu hình nhiều repository cùng loại trong composite profile.
- Sắp xếp ưu tiên bằng thứ tự danh sách composite và thuộc tính `order`.
- Dự đoán kết quả khi nhiều repository cùng khai báo một khóa.
- Đọc `propertySources` để xác định nguồn cung cấp giá trị hiệu lực.
- Kiểm soát label, lỗi backend, bí mật và thay đổi cấu hình trong môi trường nhiều repository.

## 1. Vì sao cần kết hợp nhiều repository?

Giả sử tổ chức có nhiều dịch vụ Spring Boot. Nhóm nền tảng duy trì các thiết lập dùng chung như logging, tracing và timeout mặc định. Mỗi nhóm sản phẩm có repository riêng để quản lý endpoint và cấu hình nghiệp vụ. Thông tin xác thực lại được lưu trong Vault.

Nếu chỉ dùng một repository lớn, quyền review và phát hành cấu hình có thể trở nên khó quản lý. Nếu mỗi dịch vụ tự duy trì toàn bộ cấu hình, các thiết lập chung dễ bị sao chép và lệch nhau. Kết hợp repository cho phép phân chia quyền sở hữu dữ liệu nhưng vẫn cung cấp một Environment thống nhất cho Config Client.

Ví dụ các nguồn:

| Repository | Nội dung | Chủ sở hữu |
|---|---|---|
| `platform-config` | Logging, tracing, timeout và thuộc tính nền | Nhóm nền tảng |
| `catalog-config` | Endpoint tìm kiếm, cache và cấu hình nghiệp vụ của catalog | Nhóm Catalog |
| Vault | Mật khẩu database, token và khóa bí mật | Nhóm bảo mật/vận hành |

Config Server truy vấn các repository theo application, profile và label, sau đó ghép các `propertySources` thành một Environment response. Mã ứng dụng vẫn đọc cùng một khóa qua `Environment` hoặc `@ConfigurationProperties`.

## 2. Composite Environment Repository là gì?

`EnvironmentRepository` là abstraction mà Config Server sử dụng để lấy cấu hình cho một application, profile và label. Composite repository kết hợp kết quả từ nhiều repository thành một Environment duy nhất.

Khi cần nhiều repository, có thể kích hoạt profile `composite` và khai báo danh sách backend trong `spring.cloud.config.server.composite`:

```yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: https://git.example.internal/platform/platform-config.git
          - type: git
            uri: https://git.example.internal/catalog/catalog-config.git
```

Ví dụ dùng hai Git repository. Có thể kết hợp các loại repository được Spring Cloud Config hỗ trợ, chẳng hạn Git, SVN hoặc native. Trường `type` cho biết backend nào cần được tạo cho từng phần tử.

Trong composite profile, thứ tự các phần tử trong danh sách là thứ tự ưu tiên. Repository đầu tiên có ưu tiên cao nhất. Nếu hai repository cùng có khóa `catalog.search.timeout`, giá trị trong repository đầu tiên được dùng; nếu repository đầu tiên không có khóa đó, giá trị có thể được lấy từ repository tiếp theo.

## 3. Thứ tự danh sách composite quyết định precedence

Giả sử hai repository chứa các giá trị sau:

```yaml
# platform-config/application.yml
catalog:
  search:
    timeout: 3s
    retry-count: 2
```

```yaml
# catalog-config/catalog-service-prod.yml
catalog:
  search:
    timeout: 2s
    base-url: https://search.prod.internal
```

Với cấu hình composite:

```yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: https://git.example.internal/catalog/catalog-config.git
          - type: git
            uri: https://git.example.internal/platform/platform-config.git
```

`catalog-config` đứng trước nên `catalog.search.timeout` có giá trị `2s`. Khóa `catalog.search.retry-count` không có trong repository riêng, vì vậy có thể nhận giá trị `2` từ `platform-config`. Khóa `catalog.search.base-url` chỉ có ở repository Catalog nên được lấy từ nguồn đó.

Nếu đổi thứ tự danh sách, `platform-config` sẽ đứng trước và `catalog.search.timeout` trở thành `3s`. Vì thế, chỉ một thay đổi thứ tự repository cũng có thể làm thay đổi hành vi của nhiều ứng dụng dù nội dung các tệp không đổi.

```text
Ưu tiên cao
    1. catalog-config   -> timeout = 2s
    2. platform-config  -> timeout = 3s
Ưu tiên thấp

Kết quả: catalog.search.timeout = 2s
```

Nên đặt repository chứa cấu hình chuyên biệt của ứng dụng trước repository cung cấp giá trị nền khi muốn ứng dụng có quyền ghi đè mặc định chung. Nếu tổ chức muốn một nguồn chính sách chung có quyền ưu tiên cao hơn, hãy đặt nguồn đó trước và ghi rõ quy tắc trong tài liệu vận hành.

## 4. Dùng order khi kích hoạt các backend theo profile riêng

Composite profile phù hợp khi cần nhiều repository, kể cả nhiều repository cùng loại. Nếu cần kết hợp các backend khác loại, ví dụ một Git repository và một Vault server, có thể kích hoạt các profile backend tương ứng và đặt `order` cho từng repository.

```yaml
spring:
  profiles:
    active: git,vault
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/catalog/catalog-config.git
          order: 2
        vault:
          host: vault.internal.example
          port: 8200
          scheme: https
          backend: secret
          default-key: application
          order: 1
```

Trong ví dụ này, Vault có `order: 1` và Git có `order: 2`. Số nhỏ hơn có độ ưu tiên cao hơn, vì vậy giá trị trùng trong Vault được ưu tiên hơn giá trị từ Git. Nếu muốn Git thắng khi trùng khóa, đặt Git có số `order` nhỏ hơn Vault.

Hai cách sắp xếp cần được phân biệt:

| Cách cấu hình | Phạm vi | Quy tắc ưu tiên |
|---|---|---|
| `spring.cloud.config.server.composite` | Danh sách repository trong composite profile | Phần tử đứng trước có ưu tiên cao hơn. |
| `order` | Các repository được kích hoạt bằng profile backend tương ứng | Số `order` nhỏ hơn có ưu tiên cao hơn. |

Hãy dùng các giá trị `order` khác nhau để tránh cấu hình mơ hồ. Không suy luận rằng `order` trong ví dụ Git/Vault là field cần đặt cho từng phần tử của danh sách composite; với composite profile, quy tắc được tài liệu hóa là thứ tự khai báo trong danh sách.

Nếu composite có Vault, request đến Config Server cần mang Vault token theo cơ chế xác thực đã cấu hình. Token phải được cấp an toàn cho client hoặc lớp gọi API; không ghi token vào repository hay log.

## 5. Hiểu cách xử lý khóa trùng

Khi Config Server ghép các repository, mỗi repository có thể trả về một hoặc nhiều `PropertySource`. Những nguồn này được sắp xếp theo độ ưu tiên. Nguồn đứng trước trong Environment response được kiểm tra trước khi Spring phân giải một khóa.

Ví dụ:

| Khóa | Repository ưu tiên cao | Repository ưu tiên thấp | Kết quả |
|---|---|---|---|
| `catalog.search.timeout` | `2s` | `3s` | `2s` |
| `catalog.search.retry-count` | Không khai báo | `2` | `2` |
| `catalog.search.base-url` | `https://search.prod.internal` | Không khai báo | `https://search.prod.internal` |
| `logging.level.root` | Không khai báo | `INFO` | `INFO` |

Spring không cộng, nối chuỗi hoặc hợp nhất giá trị của một khóa đơn giữa các repository. Với một khóa trùng, nguồn có ưu tiên cao nhất quyết định giá trị. Các khóa không trùng vẫn được lấy từ những repository còn lại.

Điều này cho phép chia cấu hình thành hai lớp:

- Repository nền cung cấp giá trị mặc định cho các ứng dụng.
- Repository riêng cung cấp hoặc ghi đè các giá trị dành cho một ứng dụng hay profile cụ thể.

Không nên khai báo cùng một khóa ở nhiều nơi nếu không có chủ đích. Mỗi khóa quan trọng cần có một nguồn sở hữu rõ ràng, và việc ghi đè phải được review như thay đổi hành vi ứng dụng.

## 6. Đọc propertySources để xác nhận thứ tự

Gọi Environment endpoint của Config Server với application, profile và label cần kiểm tra:

```bash
curl -H "Accept: application/json" \
  http://localhost:8888/catalog-service/prod/release-2026-11
```

Phản hồi thường có các trường `name`, `profiles`, `label`, `version` và `propertySources`. Mỗi phần tử `propertySources` có tên nguồn cùng map `source` chứa các khóa.

Ví dụ minh họa thứ tự:

```json
{
  "name": "catalog-service",
  "profiles": ["prod"],
  "label": "release-2026-11",
  "propertySources": [
    {
      "name": "catalog-config/catalog-service-prod.yml",
      "source": {
        "catalog.search.timeout": "2s"
      }
    },
    {
      "name": "platform-config/application.yml",
      "source": {
        "catalog.search.timeout": "3s",
        "catalog.search.retry-count": 2
      }
    }
  ]
}
```

Trong ví dụ, nguồn Catalog đứng trước và có ưu tiên cao hơn nguồn Platform. Khi hai nguồn cùng có `catalog.search.timeout`, kết quả là `2s`. Khi kiểm tra cấu hình, hãy xem cả tên nguồn lẫn thứ tự; chỉ tìm thấy khóa trong JSON chưa đủ để biết giá trị nào thắng.

Environment response của Config Server là cấu hình mà server tổng hợp. Config Client vẫn có thể có nguồn cấu hình cục bộ và các nguồn có độ ưu tiên khác. Nếu giá trị cuối cùng trong ứng dụng khác response, cần kiểm tra `Environment` ở client và các nguồn ghi đè cục bộ.

## 7. Profile và label phải phù hợp giữa các repository

Config Server yêu cầu các repository phục vụ cùng một application, profile và label. Với composite environment, các repository cần có label tương thích. Nếu request dùng label `release-2026-11` nhưng một repository không có nhánh hoặc tag tương ứng, toàn bộ yêu cầu composite có thể thất bại.

Ví dụ, nếu hai Git repository cùng tham gia composite, hãy duy trì tag phát hành cùng tên ở cả hai:

```text
platform-config:
  release-2026-11 -> commit a1b2c3d

catalog-config:
  release-2026-11 -> commit f4e5d6c
```

Hai tag có thể trỏ đến commit khác nhau vì mỗi repository quản lý nội dung riêng; điều quan trọng là label được yêu cầu phải tồn tại và đại diện cho một bộ phát hành tương thích ở tất cả nguồn. Nên tạo tag qua pipeline phát hành để tránh quên một repository.

Với composite environment, mọi repository tham gia cần hỗ trợ label được yêu cầu. Nếu request dùng label `release-2026-11` nhưng một repository không có branch/tag tương ứng hoặc backend đó không thể phân giải label, toàn bộ request có thể thất bại. Kiểm tra label trên tất cả backend trước khi phát hành.

Profile cũng phải được thiết kế nhất quán. Nếu ứng dụng yêu cầu `prod`, mỗi repository cần cung cấp cấu hình theo profile đó khi có dữ liệu tương ứng. Repository không có khóa cho một profile vẫn có thể đóng góp các khóa dùng chung; tuy nhiên, không nên dựa vào cấu hình thiếu ở một backend quan trọng.

## 8. Xử lý khi một repository bị lỗi

Theo hành vi mặc định, lỗi khi truy xuất một repository trong composite có thể làm toàn bộ Environment request thất bại. Điều này giúp tránh trả về một bộ cấu hình thiếu một phần mà ứng dụng tưởng là đầy đủ.

Có thể cấu hình `spring.cloud.config.server.fail-on-composite-error: false` để composite tiếp tục khi một repository lỗi:

```yaml
spring:
  cloud:
    config:
      server:
        fail-on-composite-error: false
```

Chỉ nên tắt fail-on-composite-error khi ứng dụng có thể hoạt động an toàn nếu thiếu một nguồn. Ví dụ, một repository metrics không bắt buộc có thể được xem là tùy chọn; repository chứa endpoint database hoặc chính sách bảo mật thường không nên bị bỏ qua âm thầm.

Nếu cho phép tiếp tục khi một backend lỗi, cần có log và metric cho biết nguồn nào không truy cập được, đồng thời xác định rõ những khóa nào bị thiếu. Không coi một response HTTP thành công là bằng chứng rằng tất cả repository đã được đọc thành công.

## 9. Thiết kế thứ tự repository có chủ đích

Trước khi đặt thứ tự, hãy xác định chủ sở hữu và mục đích của từng lớp cấu hình:

| Lớp | Nội dung nên quản lý | Quy tắc ghi đè gợi ý |
|---|---|---|
| Chính sách tổ chức | Quy tắc bắt buộc, thiết lập bảo mật dùng chung | Chỉ đặt ưu tiên cao nếu tổ chức cần áp dụng đồng nhất. |
| Cấu hình riêng ứng dụng | URL, timeout, feature và tham số nghiệp vụ | Thường ưu tiên cao hơn giá trị mặc định dùng chung. |
| Cấu hình nền | Logging, metrics và giá trị mặc định | Ưu tiên thấp để ứng dụng có thể tùy chỉnh. |
| Secret store | Password, token và khóa bí mật | Tách khỏi Git; quy định rõ nguồn thắng khi trùng khóa. |

Một quy ước phổ biến là đặt cấu hình riêng ứng dụng trước cấu hình nền để giá trị ứng dụng thắng, còn secret store cung cấp các khóa nhạy cảm riêng. Nếu tổ chức muốn chính sách bảo mật không thể bị ứng dụng ghi đè, hãy thiết kế lớp chính sách với ưu tiên cao hơn và kiểm thử hành vi ở Config Client.

Không nên dùng precedence như một cơ chế phân quyền. `order` quyết định giá trị nào thắng khi nhiều nguồn có cùng khóa; nó không ngăn một client đọc repository mà nó đã được cấp quyền truy cập. Xác thực và phân quyền vẫn phải được thiết kế độc lập.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Giá trị chung ghi đè cấu hình riêng | Thứ tự composite đặt repository chung lên trước | Đổi thứ tự danh sách hoặc xác định lại chủ sở hữu khóa. |
| `order` không có tác dụng như dự kiến | Nhầm `order` với thứ tự danh sách composite hoặc đặt số lớn cho nguồn cần ưu tiên | Xác định kiểu cấu hình đang dùng; số nhỏ hơn có ưu tiên cao hơn khi dùng `order`. |
| Environment request thất bại | Một repository lỗi hoặc không hỗ trợ label được yêu cầu | Kiểm tra log từng backend, quyền truy cập và label. |
| Một số khóa bị thiếu | Repository chứa khóa không được truy cập hoặc profile không khớp | Kiểm tra `propertySources`, application và profile. |
| Config Server trả đúng nhưng client dùng giá trị khác | Nguồn cấu hình cục bộ ghi đè nguồn từ xa | Kiểm tra Environment và thứ tự PropertySource phía client. |
| Vault từ chối request | Thiếu token hoặc token hết hạn/không đủ quyền | Cấp token đúng phạm vi và kiểm tra chính sách Vault. |

Khi điều tra, nên bắt đầu từ response của Config Server, xác nhận từng repository có mặt và xem thứ tự `propertySources`. Sau đó mới kiểm tra nguồn cục bộ phía client. Tránh thay đổi đồng thời nội dung nhiều repository và thứ tự ưu tiên vì sẽ khó xác định nguyên nhân.

## 11. Kiểm thử thứ tự và xử lý trùng khóa

Một bộ kiểm thử tích hợp cho composite repository nên xác minh tối thiểu:

1. Config Server khởi động với đúng profile repository, ví dụ `composite` hoặc `git,vault`.
2. Mọi backend có thể truy cập và hỗ trợ application, profile, label cần kiểm tra.
3. Mỗi repository có ít nhất một khóa riêng để xác nhận dữ liệu được kết hợp.
4. Hai repository có cùng một khóa với giá trị khác nhau để xác nhận nguồn ưu tiên cao hơn thắng.
5. Khi một repository không có khóa, giá trị từ repository thấp hơn vẫn được cung cấp.
6. Khi một repository không truy cập được, kiểm tra hành vi fail-fast hoặc chính sách tiếp tục đã cấu hình.
7. Config Client nhận đúng giá trị cuối cùng sau khi các nguồn cục bộ được tính đến.

Ví dụ kiểm thử precedence:

```text
Repository A (priority cao): app.timeout = 2s
Repository B (priority thấp): app.timeout = 5s
Repository B: app.retry-count = 3

Kỳ vọng Environment:
app.timeout = 2s
app.retry-count = 3
```

Nên giữ một bài test cố định cho thứ tự repository. Khi ai đó đổi vị trí một backend hoặc sửa `order`, test sẽ phát hiện nếu kết quả của khóa quan trọng thay đổi.

## 12. Bảo vệ dữ liệu và quản trị thay đổi

Kết hợp nhiều repository không làm giảm yêu cầu bảo mật. Mỗi nguồn cần quyền đọc riêng, và phản hồi Environment có thể tổng hợp dữ liệu từ tất cả nguồn mà client được phép truy cập.

- Dùng secret store cho mật khẩu, token và khóa bí mật; không đưa chúng vào Git.
- Cấp quyền đọc từng repository theo workload và nhóm ứng dụng.
- Với Vault, giới hạn token theo path và policy; không dùng token quản trị chung.
- Bảo vệ Config Server bằng TLS và xác thực client.
- Không ghi toàn bộ `propertySources` vào log nếu có thể chứa secret.
- Review thay đổi về thứ tự repository như thay đổi mã nguồn vì một dòng YAML có thể đổi giá trị hiệu lực của nhiều dịch vụ.
- Gắn label/revision phát hành rõ ràng cho các repository và có quy trình rollback đồng bộ.

Một thay đổi thứ tự có thể thay đổi nhiều khóa cùng lúc. Vì vậy, pull request thay đổi danh sách composite hoặc `order` cần nêu rõ khóa nào có khả năng bị ảnh hưởng, ứng dụng nào sử dụng chúng và cách xác minh sau triển khai.

## 13. Ví dụ tổng hợp

`catalog-service` cần cấu hình riêng, cấu hình nền của tổ chức và một số secret. Nhóm nền tảng và nhóm Catalog dùng hai Git repository; secret được lấy từ Vault. Một cấu hình minh họa dùng composite cho hai Git repository:

```yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: https://git.example.internal/catalog/catalog-config.git
          - type: git
            uri: https://git.example.internal/platform/platform-config.git
```

Trong trường hợp này, repository Catalog đứng trước để giá trị riêng ứng dụng thắng cấu hình nền khi trùng khóa. Nếu cần kết hợp thêm Vault, có thể chuyển sang cấu hình các backend theo profile tương ứng và đặt `order` rõ ràng, hoặc thiết kế cách kết hợp phù hợp với phiên bản Spring Cloud Config đang sử dụng. Cần bảo đảm label tương thích giữa các nguồn và xác thực Vault cho từng request.

Khi truy vấn `/catalog-service/prod/release-2026-11`, Config Server tổng hợp cấu hình cho application `catalog-service`, profile `prod` và label `release-2026-11`. Nhóm kiểm tra Environment response để xác nhận `catalog-config` đứng trước `platform-config`, các khóa nghiệp vụ có giá trị đúng và các khóa mặc định vẫn được lấy từ nguồn nền. Sau đó, kiểm tra Config Client để chắc chắn không có nguồn cục bộ ghi đè ngoài dự kiến.

## 14. Những điểm cần ghi nhớ

- Composite Environment Repository kết hợp nhiều `EnvironmentRepository` thành một Environment response.
- Với profile `composite`, repository được khai báo trước trong danh sách có ưu tiên cao hơn.
- Khi kích hoạt các backend theo profile riêng, `order` điều khiển precedence; số nhỏ hơn có ưu tiên cao hơn.
- Khóa trùng được giải quyết bằng nguồn có ưu tiên cao nhất; khóa không trùng vẫn được lấy từ các nguồn còn lại.
- Các repository cần hỗ trợ label tương thích; thiếu label ở một nguồn có thể làm request composite thất bại.
- Lỗi một backend mặc định có thể làm cả composite request thất bại; chỉ cho phép bỏ qua lỗi khi ứng dụng có thể hoạt động an toàn.
- Kiểm tra `propertySources`, xác thực mọi backend và review thay đổi thứ tự như thay đổi hành vi ứng dụng.

Thiết kế thứ tự repository rõ ràng giúp tổ chức chia quyền sở hữu cấu hình mà vẫn tạo được một Environment nhất quán cho mỗi ứng dụng. Khi kiểm soát được precedence, label và lỗi backend, nhóm có thể mở rộng Config Server sang nhiều nguồn mà vẫn dự đoán được giá trị cuối cùng mà Spring Boot Client nhận được.

## Tài liệu tham khảo

- [Spring Cloud Config – Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html)
- [Spring Cloud Config – Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
