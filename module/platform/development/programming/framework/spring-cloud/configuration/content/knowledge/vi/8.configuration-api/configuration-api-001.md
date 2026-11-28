# Truy vấn Environment theo /{application}/{profile}/{label}

Spring Cloud Config Server cung cấp cấu hình qua một REST API. Khi cần kiểm tra bộ cấu hình mà một dịch vụ sẽ nhận, ta có thể gửi yêu cầu theo ba thông tin: tên ứng dụng, profile và label. Endpoint chính có dạng `/{application}/{profile}[/{label}]` và trả về một đối tượng Environment chứa danh sách `propertySources` đã được Config Server tổng hợp từ backend cấu hình, thường là Git.

Ví dụ, dịch vụ `catalog-service` chạy với profile `prod` và sử dụng revision `release-2026-11` có thể được truy vấn bằng `/catalog-service/prod/release-2026-11`. Phản hồi cho biết Config Server đã tìm thấy những nguồn nào, nguồn nào chứa thuộc tính cần dùng và revision nào được backend trả về. Đây là cách hữu ích để kiểm tra cấu hình trước khi khởi động client hoặc điều tra sai lệch giữa các môi trường.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cấu trúc endpoint `/{application}/{profile}/{label}`.
- Gửi yêu cầu Environment API cho một ứng dụng, một profile hoặc nhiều profile.
- Đọc các trường `name`, `profiles`, `label`, `version`, `state` và `propertySources` trong phản hồi.
- Phân biệt Environment do Config Server trả về với Environment cuối cùng trong Config Client.
- Truy vấn cấu hình theo label và định dạng JSON, YAML hoặc properties.
- Chẩn đoán cấu hình thiếu, sai profile, sai label và lỗi truy cập API.
- Bảo vệ endpoint vì phản hồi có thể chứa thông tin cấu hình nhạy cảm.

## 1. Cấu trúc endpoint Environment

Endpoint chính của Spring Cloud Config Server có dạng:

```text
/{application}/{profile}[/{label}]
```

Ba phần có ý nghĩa như sau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `application` | Tên ứng dụng cần lấy cấu hình | `catalog-service` |
| `profile` | Một hoặc nhiều profile cần áp dụng | `prod` hoặc `prod,observability` |
| `label` | Nhánh, tag hoặc revision của backend cấu hình | `release-2026-11` |

Ví dụ với Config Server chạy tại `localhost:8888`:

```text
GET http://localhost:8888/catalog-service/prod/release-2026-11
```

Nếu bỏ label, Config Server dùng label mặc định được cấu hình ở server. Giá trị mặc định phụ thuộc backend và cấu hình triển khai; không nên giả định mọi server đều dùng `main` hoặc `master`.

`application` thường tương ứng với `spring.application.name` của Config Client. `profile` thường được lấy từ active profiles của Spring Boot. `label` chọn phiên bản của repository cấu hình. Khi ba giá trị này khớp với cấu trúc repository, Config Server có thể tổng hợp cấu hình chung và cấu hình riêng cho ứng dụng.

## 2. Truy vấn một ứng dụng với một profile

Giả sử Git repository cấu hình có các tệp:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── catalog-service.yml
└── catalog-service-prod.yml
```

Ta muốn xem cấu hình của `catalog-service` ở production trên label `release-2026-11`:

```bash
curl -H "Accept: application/json" \
  http://localhost:8888/catalog-service/prod/release-2026-11
```

Yêu cầu này chỉ định rõ cả application, profile và label. Config Server sử dụng chúng để tìm các nguồn phù hợp trong backend, rồi trả về một Environment. Nếu không chỉ định label:

```bash
curl -H "Accept: application/json" \
  http://localhost:8888/catalog-service/prod
```

server sẽ chọn label mặc định. Khi cần tái tạo chính xác một lần phát hành, nên truyền label bất biến như tag hoặc commit thay vì phụ thuộc vào nhánh mặc định có thể thay đổi theo thời gian.

## 3. Đọc cấu trúc phản hồi Environment

Phản hồi JSON thường có cấu trúc tổng quát như sau:

```json
{
  "name": "catalog-service",
  "profiles": ["prod"],
  "label": "release-2026-11",
  "version": "a1b2c3d4e5f6",
  "state": null,
  "propertySources": [
    {
      "name": "https://git.example/config-repo/catalog-service-prod.yml",
      "source": {
        "catalog.search.base-url": "https://search.prod.internal",
        "catalog.search.connect-timeout": "2s"
      }
    },
    {
      "name": "https://git.example/config-repo/application.yml",
      "source": {
        "catalog.search.enabled": true,
        "catalog.cache.ttl": "60s"
      }
    }
  ]
}
```

Đây là ví dụ minh họa; tên nguồn, giá trị, thứ tự và các trường tùy chọn trong phản hồi thực tế phụ thuộc backend, phiên bản và cấu hình server.

| Trường | Ý nghĩa |
|---|---|
| `name` | Application name mà Config Server đã xử lý. |
| `profiles` | Danh sách profile được dùng để tạo Environment. |
| `label` | Label được dùng để truy vấn backend; có thể rỗng hoặc `null` tùy cấu hình. |
| `version` | Thông tin phiên bản từ backend, thường là commit ID với Git backend. |
| `state` | Thông tin trạng thái do backend cung cấp; có thể là `null`. |
| `propertySources` | Danh sách các nguồn cấu hình được tổng hợp. |

Mỗi phần tử `propertySources` thường có:

- `name`: tên hoặc vị trí nguồn, hữu ích để biết giá trị đến từ tệp hay backend nào.
- `source`: map các khóa và giá trị cấu hình mà nguồn cung cấp.

Ví dụ, khóa `catalog.search.base-url` nằm trong `source` của `catalog-service-prod.yml`. Các nguồn được sắp xếp theo độ ưu tiên: nguồn đứng đầu danh sách có ưu tiên cao nhất. Khi một khóa xuất hiện ở nhiều nguồn, hãy đọc thứ tự thực tế của phản hồi thay vì chỉ tìm thấy khóa ở đâu đó trong JSON.

## 4. Truy vấn nhiều profile

Phần `profile` có thể chứa nhiều profile, phân tách bằng dấu phẩy:

```bash
curl -H "Accept: application/json" \
  http://localhost:8888/catalog-service/prod,observability/release-2026-11
```

Config Server sẽ tổng hợp cấu hình cho `prod` và `observability` cùng cấu hình chung, nếu các nguồn tương ứng tồn tại. Trong phản hồi, trường `profiles` cho biết danh sách profile đã được xử lý.

Điều này hữu ích khi ứng dụng cần nhiều lớp cấu hình, chẳng hạn `prod` cho endpoint và tài nguyên production, `observability` cho logging, metrics hoặc tracing. Tuy nhiên, nếu nhiều profile cùng định nghĩa một khóa, thứ tự tổng hợp có thể làm thay đổi giá trị cuối cùng. Hãy kiểm tra `propertySources` để biết nguồn nào đứng trước và nguồn nào đứng sau.

Profile group là khái niệm phía Spring Boot Client. Khi client kích hoạt group, các profile thành viên được phân giải theo cấu hình ứng dụng. Nếu cần kiểm tra yêu cầu thực tế, hãy xem danh sách profile trong phản hồi và log của Config Client. Không suy luận từ tên group rằng Config Server đã nhận chính xác mọi thành viên nếu chưa kiểm tra.

## 5. Label chọn revision cấu hình

Label thường đại diện cho nhánh, tag hoặc commit trong Git backend. Ví dụ:

```text
/catalog-service/prod/main
/catalog-service/prod/release-2026-11
/catalog-service/prod/a1b2c3d4e5f6
```

Các label trên có thể trả về các giá trị khác nhau dù application và profile giống nhau. Nhánh `main` thường thay đổi theo commit mới; tag phát hành hoặc commit ID giúp xác định bộ cấu hình ổn định hơn.

Config Server có thể được cấu hình label mặc định bằng thuộc tính phía server, ví dụ `spring.cloud.config.server.git.default-label`. Client có thể chọn label bằng `spring.cloud.config.label`:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026-11
```

Với REST API, label nằm ở phần cuối của endpoint. Nếu tên nhánh có dấu `/`, cần xử lý URL encoding và cấu hình đường dẫn phù hợp với proxy/server để slash không bị hiểu nhầm thành một segment khác. Khi có thể, tag phát hành với tên đơn giản giúp URL dễ đọc và dễ truy vết hơn.

## 6. Truy vấn bằng các định dạng khác

Environment endpoint có thể được truy cập dưới dạng JSON, YAML hoặc properties thông qua các URL theo quy ước của Config Server. Các dạng phổ biến gồm:

| Định dạng | Endpoint minh họa |
|---|---|
| Environment JSON | `/catalog-service/prod/release-2026-11` |
| YAML dùng label mặc định | `/catalog-service-prod.yml` |
| YAML với label cụ thể | `/release-2026-11/catalog-service-prod.yml` |
| Properties dùng label mặc định | `/catalog-service-prod.properties` |
| Properties với label cụ thể | `/release-2026-11/catalog-service-prod.properties` |
| JSON theo tên file | `/catalog-service-prod.json` |

Với YAML:

```bash
curl http://localhost:8888/catalog-service-prod.yml
```

Với properties:

```bash
curl http://localhost:8888/catalog-service-prod.properties
```

Các endpoint theo định dạng file là cách thuận tiện để đọc cấu hình đã được chuyển đổi sang một representation cụ thể. Khi cần kiểm tra đầy đủ metadata như `profiles`, `label`, `version` và từng `propertySources`, hãy dùng Environment endpoint JSON.

Một endpoint khác có dạng `/{application}/{profile}/{label}/{path}` cho phép truy xuất tài nguyên trong repository cấu hình, chẳng hạn một tệp được lưu cùng repository. Đây là thao tác lấy resource theo đường dẫn; nó khác với việc đọc map thuộc tính đã được tổng hợp trong Environment.

## 7. Phân biệt Environment phía Server và Environment phía Client

REST response của Config Server là kết quả tổng hợp các nguồn mà server tìm được cho application, profile và label. Sau khi Config Client nhận response, các property source từ xa được đưa vào `Environment` của ứng dụng.

Environment cuối cùng tại client còn có thể chứa nguồn cục bộ như:

- Biến môi trường của tiến trình.
- Thuộc tính hệ thống JVM.
- Tham số dòng lệnh.
- `application.yml` và các tệp profile-specific được nạp tại client.
- Nguồn thuộc tính được đăng ký bởi framework, test hoặc thành phần hạ tầng.

Vì vậy, giá trị trả về từ Config Server chưa chắc là giá trị cuối cùng mà bean đọc được. Cách kết hợp và ghi đè phụ thuộc thứ tự nguồn, cơ chế Config Data hay bootstrap được dùng, phiên bản Spring Cloud và các tùy chọn override.

Khi cần xác định giá trị ứng dụng thật sự sử dụng, hãy kiểm tra cả hai phía:

1. Gọi Environment endpoint để biết Config Server trả về gì.
2. Kiểm tra active profiles và các property source của client.
3. Đọc giá trị cuối cùng bằng `Environment.getProperty("catalog.search.base-url")`.
4. Xác định nguồn có độ ưu tiên cao nhất đang cung cấp khóa đó.

Không kết luận Config Server sai chỉ vì giá trị cuối cùng của client khác JSON server trả về; trước hết hãy kiểm tra các nguồn cục bộ và chính sách ghi đè.

## 8. Cấu hình Config Client tương ứng

Với cơ chế Config Data hiện đại, client cần dependency `spring-cloud-starter-config` tương thích với release train của dự án và khai báo import:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026-11
```

Profile được chọn từ môi trường chạy, ví dụ:

```bash
SPRING_PROFILES_ACTIVE=prod,observability java -jar catalog-service.jar
```

Các thuộc tính chính phía client:

| Thuộc tính | Công dụng |
|---|---|
| `spring.application.name` | Tên application dùng để yêu cầu cấu hình; có thể được thay bằng `spring.cloud.config.name` khi cần. |
| `spring.profiles.active` | Chọn profile của ứng dụng và thường là profile được gửi đến Config Server. |
| `spring.cloud.config.profile` | Cho phép chỉ định profile dùng cho yêu cầu Config Server trong trường hợp cần tách biệt; phải kiểm thử cẩn thận với active profiles phía client. |
| `spring.cloud.config.label` | Chọn label/revision của backend. |
| `spring.config.import` | Khai báo địa chỉ Config Server trong Config Data integration. |

Trong các hệ thống cũ dùng bootstrap context, các thuộc tính và thời điểm tải có thể khác. Cần xác định phiên bản Spring Boot/Spring Cloud trước khi áp dụng cấu hình. Không trộn hướng dẫn `bootstrap.yml` cũ với Config Data import mà không hiểu rõ cơ chế đang bật.

## 9. Chẩn đoán khi truy vấn trả về dữ liệu không mong đợi

Khi Environment response thiếu khóa hoặc trả về sai giá trị, kiểm tra theo trình tự:

1. **Application:** xác nhận đúng `spring.application.name` hoặc tên được client override. Tên này phải khớp với quy ước tệp trong repository.
2. **Profile:** xác nhận profile được gửi, kể cả danh sách nhiều profile và profile phụ.
3. **Label:** xác nhận nhánh, tag hoặc commit tồn tại trong backend Git và Config Server có quyền đọc.
4. **File naming:** kiểm tra `application.yml`, `application-{profile}.yml`, `{application}.yml` và `{application}-{profile}.yml` được đặt đúng tên.
5. **Search locations:** xác nhận Config Server đang tìm đúng thư mục hoặc search path.
6. **Property sources:** xem `name` và `source` của từng phần tử, đặc biệt thứ tự các nguồn chứa cùng một khóa.
7. **Client overrides:** nếu JSON đúng nhưng ứng dụng sai, kiểm tra nguồn cục bộ và thứ tự ưu tiên phía client.

Ví dụ gọi endpoint:

```bash
curl -i \
  http://localhost:8888/catalog-service/prod/release-2026-11
```

Tùy cấu hình server, khi không tìm thấy application hoặc nguồn cấu hình, API có thể trả về Environment rỗng hoặc lỗi HTTP. Thuộc tính server `spring.cloud.config.server.accept-empty` điều khiển việc có chấp nhận kết quả rỗng hay trả lỗi khi không tìm thấy cấu hình. Hãy xem cả status code lẫn nội dung response; đừng chỉ dựa vào việc `curl` nhận được một JSON.

Các lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| HTTP 404 | Server không chấp nhận Environment rỗng, sai application/profile/label hoặc route không tồn tại | Kiểm tra URL, tên file, label và `accept-empty`. |
| Environment rỗng | Không có tệp phù hợp hoặc search path không trỏ đến thư mục chứa cấu hình | Kiểm tra backend Git, search locations và tên tệp. |
| Sai giá trị | Khóa trùng ở nhiều nguồn hoặc nhầm label/profile | So sánh `propertySources` và revision. |
| Không truy cập được | DNS, port, TLS, proxy hoặc Config Server chưa sẵn sàng | Kiểm tra kết nối và log server. |
| 401/403 | Thiếu thông tin xác thực hoặc không đủ quyền | Kiểm tra danh tính client và chính sách bảo mật. |

## 10. Bảo vệ Environment API

Environment response có thể chứa toàn bộ giá trị cấu hình mà client được phép đọc, bao gồm endpoint nội bộ và thông tin xác thực nếu repository được tổ chức không an toàn. Vì vậy, REST API phải được bảo vệ như một giao diện quản trị cấu hình.

- Bật HTTPS/TLS giữa Config Client, công cụ vận hành và Config Server.
- Bật xác thực và phân quyền; cấp quyền đọc theo workload hoặc nhóm ứng dụng.
- Không công khai endpoint cấu hình ra Internet nếu không có nhu cầu và biện pháp bảo vệ tương ứng.
- Không commit secret vào Git; dùng secret store hoặc cơ chế mã hóa có quản lý khóa phù hợp.
- Tránh đưa response đầy đủ vào log, ticket hoặc hệ thống giám sát công khai.
- Giới hạn quyền truy cập endpoint tài nguyên và endpoint Actuator liên quan.

Ví dụ gọi API có bearer token được cấp từ môi trường shell:

```bash
curl -H "Authorization: Bearer ${CONFIG_SERVER_TOKEN}" \
  -H "Accept: application/json" \
  https://config.example.internal/catalog-service/prod/release-2026-11
```

Không ghi token thật trực tiếp vào script được commit hoặc lệnh có thể lưu trong lịch sử dùng chung. Với Basic Authentication, cũng cần tránh đặt mật khẩu thật trong tài liệu hoặc log lệnh.

## 11. Quy trình kiểm tra cấu hình trước phát hành

Environment API có thể được đưa vào bước xác minh trước khi triển khai:

1. Chọn đúng application name, profile và label của release.
2. Gọi endpoint JSON từ môi trường có quyền truy cập Config Server.
3. Xác nhận status HTTP thành công và `name`, `profiles`, `label` đúng kỳ vọng.
4. Kiểm tra các khóa bắt buộc có mặt trong `propertySources`.
5. Xác nhận các nguồn có khóa trùng nhau được sắp xếp theo quy tắc mong muốn.
6. Kiểm tra response không chứa secret được đưa vào repository nhầm.
7. Lưu application, profile, label và version/revision để truy vết lần triển khai.

Việc kiểm tra có thể dùng script CI hoặc smoke test có quyền đọc cấu hình. Script nên kiểm tra tên khóa và điều kiện cần thiết, tránh in toàn bộ giá trị nhạy cảm ra log pipeline.

## 12. Ví dụ tổng hợp

Giả sử `catalog-service` cần cấu hình production và observability từ Git tag `release-2026-11`. Gọi:

```bash
curl -H "Accept: application/json" \
  https://config.example.internal/catalog-service/prod,observability/release-2026-11
```

Kết quả cần xác nhận:

- `name` là `catalog-service`.
- `profiles` bao gồm `prod` và `observability`.
- `label` là `release-2026-11`.
- `version` phản ánh revision backend nếu backend cung cấp thông tin này.
- `propertySources` có cấu hình chung và cấu hình riêng phù hợp với application/profile.
- Các khóa như `catalog.search.base-url` có giá trị mong đợi và không bị một nguồn ưu tiên khác ghi đè ngoài ý muốn.

Sau khi xác nhận server response, khởi động Config Client với cùng application name, active profiles và label. Nếu giá trị cuối cùng trong ứng dụng vẫn khác response, kiểm tra các nguồn cấu hình cục bộ và chính sách override trước khi thay đổi repository Git.

## 13. Những điểm cần ghi nhớ

- Endpoint Environment chính có dạng `/{application}/{profile}[/{label}]`.
- Application name chọn dịch vụ; profile chọn nhóm cấu hình; label chọn revision của backend.
- Nhiều profile được phân tách bằng dấu phẩy và có thể ảnh hưởng đến thứ tự kết hợp nguồn.
- JSON Environment mô tả `name`, `profiles`, `label`, `version`, `state` và danh sách `propertySources`.
- Thứ tự `propertySources` quan trọng khi cùng một khóa xuất hiện ở nhiều nguồn.
- Environment từ Config Server khác với Environment cuối cùng phía client vì client còn có nguồn cấu hình cục bộ.
- Bảo vệ API, kiểm tra HTTP status và không để lộ secret khi truy vấn hoặc ghi log.

Khi đọc được Environment response, bạn có thể lần theo nguồn gốc của từng giá trị và xác nhận Config Server đang phân phối cấu hình nào cho một ứng dụng, profile và revision cụ thể. Đây là bước quan trọng để kiểm soát thay đổi cấu hình tập trung và điều tra sự cố giữa các môi trường.
