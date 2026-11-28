# Phục vụ tệp cấu hình thuần văn bản và giới hạn sử dụng

Spring Cloud Config Server cung cấp API để client lấy tập thuộc tính đã được tổng hợp theo ứng dụng, profile và label. Ngoài API `Environment`, server còn có thể phục vụ trực tiếp một tệp thuần văn bản nằm trong backend repository. Cách này hữu ích với những tài nguyên cấu hình cần giữ nguyên nội dung như `logback-spring.xml`, `banner.txt`, template hoặc một tệp cấu hình định dạng riêng.

API tệp thuần văn bản giúp client tải đúng một tệp theo phiên bản cấu hình đã chọn. Nó không thay thế API `Environment`, không biến Config Server thành kho lưu trữ tệp nhị phân và không tự áp dụng nội dung tải về vào ứng dụng. Nhóm cần xác định rõ client nào được đọc tệp, tệp có kích thước phù hợp hay không và cách bảo vệ endpoint khỏi truy cập quá mức.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt API `Environment` với API phục vụ tệp thuần văn bản.
- Gọi endpoint `/{application}/{profile}/{label}/{path}` để lấy một tệp từ backend.
- Tổ chức tệp trong Git và dùng application, profile, label để chọn phiên bản.
- Tải nội dung về bằng curl hoặc PowerShell và kiểm tra phản hồi HTTP.
- Hiểu phạm vi và giới hạn của endpoint tệp thuần văn bản.
- Thiết kế xác thực, phân quyền, giới hạn dung lượng, tần suất và cache phù hợp.

## Hai cách lấy dữ liệu từ Config Server

Config Server cung cấp hai kiểu truy cập có mục đích khác nhau:

| API | Ví dụ đường dẫn | Kết quả |
|---|---|---|
| Environment API | `/{application}/{profile}/{label}` | Tập `Environment` dạng JSON, gồm các property source được tổng hợp từ repository |
| Environment ở định dạng cụ thể | `/{application}-{profile}.yml` hoặc endpoint tương ứng theo định dạng | Các thuộc tính được render thành YAML, properties hoặc định dạng được hỗ trợ |
| Plain-text resource API | `/{application}/{profile}/{label}/{path}` | Nội dung của một tệp được chọn trong backend repository |

Environment API phù hợp khi ứng dụng muốn bind nhiều thuộc tính vào `Environment` hoặc `@ConfigurationProperties`. Plain-text resource API phù hợp khi một thành phần cần tải một tệp cụ thể theo định dạng riêng, chẳng hạn cấu hình logging hoặc template.

Ví dụ, ứng dụng `order-service` có thể dùng Environment API để lấy URL database và timeout, đồng thời dùng plain-text resource API để tải `logback-spring.xml`. Hai yêu cầu cùng xác định application, profile và label nên có thể lấy dữ liệu từ cùng phiên bản repository.

## Cấu trúc endpoint tệp thuần văn bản

Đường dẫn có dạng:

```text
GET /{application}/{profile}/{label}/{path}
```

Trong đó:

- `application`: tên ứng dụng, thường tương ứng với `spring.application.name` của Config Client.
- `profile`: profile cần chọn, ví dụ `dev`, `test` hoặc `prod`.
- `label`: branch, tag hoặc commit trong backend Git.
- `path`: đường dẫn tương đối đến tệp cần phục vụ trong repository, tính theo cấu trúc backend và các `search-paths` đã cấu hình.

Ví dụ, yêu cầu sau lấy `logback-spring.xml` cho `order-service`, profile `prod`, label `main`:

```text
GET http://localhost:8888/order-service/prod/main/logback-spring.xml
```

Các thành phần application, profile và label giúp server xác định nguồn cấu hình; phần path chọn tệp cụ thể. Vì vậy, cùng một tên tệp có thể có nội dung khác nhau ở các profile hoặc label khác nhau.

## Chuẩn bị tệp trong Git repository

Giả sử Config Server đang dùng Git backend và repository có cấu trúc:

```text
platform-config/
├── application.yml
├── order-service.yml
├── order-service-prod.yml
└── logback-spring.xml
```

Tệp `logback-spring.xml` chứa cấu hình logging cần phân phối:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Đây là tệp văn bản thông thường, có thể được review và quản lý phiên bản cùng repository. Nếu mỗi ứng dụng cần nội dung riêng, có thể đặt tệp trong thư mục riêng hoặc dùng `search-paths` để server tìm đúng vị trí. Tránh lưu mật khẩu, token, private key hoặc nội dung nhạy cảm trong tệp được phục vụ công khai qua endpoint này.

Nếu repository được tổ chức theo thư mục ứng dụng:

```text
platform-config/
├── shared/
│   └── banner.txt
└── order-service/
    └── logback-spring.xml
```

Config Server có thể khai báo:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          search-paths:
            - shared
            - '{application}'
```

Khi đó, đường dẫn tệp được tìm trong các search path phù hợp. Hãy xác nhận vị trí bằng cách gọi API thực tế sau khi thay đổi cấu trúc repository; không giả định một đường dẫn tương đối luôn được resolve giống nhau khi `search-paths` thay đổi.

## Gọi API bằng curl

Để xem nội dung và status code, dùng `curl -i`:

```bash
curl -i \
  http://localhost:8888/order-service/prod/main/logback-spring.xml
```

Để lưu nội dung về file cục bộ:

```bash
curl --fail --show-error \
  --output logback-spring.xml \
  http://localhost:8888/order-service/prod/main/logback-spring.xml
```

`--fail` giúp curl trả lỗi khi server phản hồi HTTP 4xx hoặc 5xx, còn `--output` ghi body vào file. Sau khi tải, kiểm tra nội dung và status trước khi dùng trong ứng dụng. Không ghi đè trực tiếp file đang được ứng dụng sử dụng nếu chưa có quy trình cập nhật an toàn.

Nếu Config Server yêu cầu xác thực, truyền credential bằng cơ chế phù hợp với môi trường. Không nhúng token dài hạn vào URL vì URL thường xuất hiện trong access log, lịch sử shell và công cụ giám sát.

## Gọi API bằng PowerShell

Trên Windows PowerShell, có thể tải tệp bằng `Invoke-WebRequest`:

```powershell
$uri = 'http://localhost:8888/order-service/prod/main/logback-spring.xml'
Invoke-WebRequest -Uri $uri -OutFile '.\logback-spring.xml'
```

Nếu cần xem status và header trước khi lưu, có thể thực hiện request rồi kiểm tra `StatusCode`, `Headers` và `Content` theo cách phù hợp với phiên bản PowerShell. Khi nhận 404, kiểm tra application, profile, label, path và `search-paths`; khi nhận 401/403, kiểm tra xác thực và quyền truy cập.

## Sử dụng profile và label để chọn tệp

Giả sử repository có các nhánh hoặc tag sau:

```text
main
release/2026.11
```

Client có thể lấy tệp theo phiên bản:

```text
GET /order-service/dev/main/logback-spring.xml
GET /order-service/prod/release-2026.11/logback-spring.xml
```

Trong ví dụ thứ hai, `release-2026.11` là label minh họa. Label thực tế phải tồn tại trong repository. Nếu label chứa dấu `/`, cần tuân theo quy tắc mã hóa label của phiên bản Spring Cloud Config và reverse proxy; kiểm thử URL từ đúng đường mạng của client.

Sử dụng tag hoặc commit cụ thể khi cần tái lập nội dung đã phát hành. Branch như `main` thường thay đổi theo thời gian, nên cùng một URL có thể trả về nội dung mới sau khi repository được cập nhật. Muốn đảm bảo các instance cùng nhận một nội dung, hãy thống nhất label/commit trong quy trình triển khai.

## Nội dung được phục vụ và trách nhiệm của client

Plain-text resource API trả về nội dung tệp được chọn. Client cần tự quyết định cách lưu, parse hoặc nạp tệp đó. Ví dụ:

- Ứng dụng logging tải `logback-spring.xml` và cấu hình logging theo cơ chế khởi động của ứng dụng.
- Một thành phần giao diện tải `banner.txt` để hiển thị thông báo.
- Một service tải template văn bản theo label phát hành rồi dùng template engine để xử lý.

Endpoint này không tự động hợp nhất nội dung tệp thành `Environment` của Spring, không tự thay thế cơ chế `@ConfigurationProperties` và không đảm bảo mọi thư viện bên trong ứng dụng tự reload khi file được tải mới. Client phải triển khai logic nạp lại, kiểm tra định dạng và xử lý lỗi phù hợp.

Nếu nội dung là YAML hoặc properties cần được Spring bind như cấu hình ứng dụng, hãy cân nhắc dùng Environment API. Dùng plain-text endpoint khi cần nội dung tệp nguyên dạng cho một consumer cụ thể.

## Giới hạn chức năng của endpoint

Plain-text resource API có phạm vi rõ ràng:

- **Chỉ đọc:** endpoint phục vụ nội dung từ backend repository; không dùng nó để upload, sửa hoặc commit file vào Git.
- **Một tài nguyên theo mỗi request:** client chỉ định một path cho mỗi lần tải; endpoint không phải API truy vấn dữ liệu hàng loạt.
- **Phụ thuộc backend:** file phải tồn tại trong repository/label và nằm trong phạm vi tìm kiếm của cấu hình backend.
- **Theo context yêu cầu:** application, profile và label ảnh hưởng đến nguồn và phiên bản được chọn.
- **Dành cho văn bản:** không dùng endpoint như kênh phân phối binary lớn, archive, model hoặc dataset.
- **Không thay thế secret manager:** việc một file có thể được tải qua HTTP không có nghĩa nó phù hợp để chứa credential hoặc private key.

Spring Cloud Config không cung cấp một con số quota kích thước hay rate limit duy nhất áp dụng cho mọi triển khai. Giới hạn thực tế phụ thuộc phiên bản, backend, tài nguyên máy chủ, HTTP server, reverse proxy/API gateway và cấu hình mạng của hệ thống. Nhóm vận hành cần đặt giới hạn rõ ràng tại lớp triển khai.

## Giới hạn dung lượng và hiệu năng

Tệp văn bản nên nhỏ, cần thiết cho ứng dụng và thay đổi theo quy trình phát hành. Khi một tệp lớn, mỗi request sẽ tiêu thụ băng thông, bộ nhớ đệm và tài nguyên xử lý của Config Server cùng các lớp proxy.

Các biện pháp nên áp dụng:

- Đặt giới hạn dung lượng response ở reverse proxy hoặc API gateway theo kích thước tệp hợp lý của hệ thống.
- Cấu hình timeout và giới hạn kết nối đồng thời để một số request chậm không chiếm hết tài nguyên.
- Tránh tải cùng một tệp lặp lại ở mọi request nghiệp vụ; cache theo application/profile/label/path hoặc tải một lần trong vòng đời phù hợp.
- Dùng label bất biến cho nội dung phát hành để cache không vô tình giữ nội dung sai phiên bản.
- Chuyển file lớn, binary hoặc dữ liệu thay đổi thường xuyên sang object storage/artifact repository.
- Theo dõi response size, latency, số request, tỷ lệ 4xx/5xx và dung lượng repository clone.

Cache cần có chính sách hết hạn hoặc khóa theo label/commit. Nếu cache chỉ dựa vào path mà bỏ qua profile hoặc label, client có thể nhận nội dung của môi trường hay phiên bản khác. Không cache phản hồi nhạy cảm trong shared cache nếu chưa thiết kế phân vùng và kiểm soát quyền phù hợp.

## Giới hạn tần suất và kiểm soát truy cập

Config Server thường là dịch vụ dùng chung. Nếu nhiều client hoặc người dùng có thể gọi endpoint tự do, một vòng lặp tải file có thể làm tăng tải hoặc làm lộ dữ liệu cấu hình. Hãy áp dụng các kiểm soát ở lớp bảo vệ:

- Yêu cầu TLS cho kết nối qua mạng không tin cậy.
- Bật xác thực và phân quyền ở Config Server hoặc gateway; giới hạn ai được đọc application/profile/label cụ thể.
- Đặt rate limit và quota theo client, workload identity hoặc nhóm ứng dụng tại API gateway/reverse proxy.
- Giới hạn request size và response size phù hợp; theo dõi timeout và concurrent requests.
- Chỉ công khai các route cần thiết; không mở rộng quyền truy cập chỉ vì endpoint trả về văn bản.
- Ghi access log với thông tin nhận diện client, path, status và response size; không ghi body chứa bí mật.

Đặc biệt, không cho phép người dùng cuối tự do thay `application`, `profile`, `label` hoặc `path` nếu họ không được quyền đọc các tài nguyên đó. Nếu endpoint đứng sau API gateway, kiểm tra gateway có giữ nguyên hoặc xác thực lại danh tính client thay vì tin một header do người gọi tự gửi hay không.

## Xử lý lỗi HTTP

Khi gọi endpoint, cần phân biệt lỗi truy cập, lỗi xác thực và lỗi tài nguyên:

| HTTP status | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `200 OK` | Tệp được tìm thấy và trả về | Kiểm tra body, content type và label/commit |
| `400 Bad Request` | Request không hợp lệ hoặc tham số không được xử lý | Kiểm tra URL encoding, application/profile/label/path |
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực | Kiểm tra credential và cơ chế xác thực |
| `403 Forbidden` | Danh tính đã xác thực nhưng không có quyền | Kiểm tra policy theo ứng dụng, môi trường và tài nguyên |
| `404 Not Found` | Không tìm thấy tệp hoặc route tương ứng | Kiểm tra path, search paths, tên file, label và repository |
| `5xx` | Lỗi phía server/backend | Kiểm tra Git backend, log server, timeout và trạng thái hạ tầng |

Status cụ thể còn phụ thuộc security filter, reverse proxy và phiên bản triển khai. Không suy ra rằng mọi lỗi 404 đều là file không tồn tại nếu gateway có chính sách che giấu tài nguyên bị cấm.

## Kiểm thử và vận hành an toàn

Trước khi phát hành một tệp qua API, kiểm tra các trường hợp sau:

1. Tệp tồn tại ở đúng path trong repository và label dự kiến.
2. Request với application/profile/label đúng trả về nội dung chính xác.
3. Request với label cũ trả về phiên bản cũ có chủ đích; label mới trả về nội dung mới.
4. Request không có quyền bị từ chối theo chính sách, không làm lộ nội dung qua lỗi hoặc log.
5. Tệp vượt giới hạn dung lượng bị từ chối hoặc xử lý theo chính sách gateway đã định.
6. Tần suất request cao được giới hạn và được ghi nhận trong metric.
7. Client xử lý được timeout, 404, 401/403 và phản hồi không hợp lệ.
8. Quy trình rollback có thể chuyển về label/commit trước và xác nhận nội dung sau rollback.

Ví dụ kiểm tra nhanh bằng curl:

```bash
curl --fail --show-error \
  --output /tmp/logback-spring.xml \
  http://localhost:8888/order-service/prod/main/logback-spring.xml

wc -c /tmp/logback-spring.xml
```

Lệnh `wc -c` giúp quan sát kích thước tệp sau khi tải. Đây là kiểm tra thủ công đơn giản; trong pipeline nên có bước xác minh checksum hoặc nội dung mong đợi và giới hạn kích thước được cấu hình theo chính sách.

## Kết luận

Plain-text resource API của Spring Cloud Config phục vụ một tệp văn bản từ backend theo application, profile, label và path. Endpoint `/{application}/{profile}/{label}/{path}` phù hợp với tài nguyên như logging configuration, banner hoặc template cần được quản lý phiên bản cùng repository.

Hãy dùng Environment API cho các thuộc tính cần được Spring tổng hợp và bind; dùng plain-text endpoint cho tệp cần được client tải và xử lý riêng. Vì Config Server không áp đặt một quota kích thước hay rate limit chung cho mọi môi trường, nhóm triển khai cần chủ động bảo vệ endpoint, giới hạn response, kiểm soát tần suất, cache theo đúng phiên bản và chuyển binary/dữ liệu lớn sang hệ thống lưu trữ chuyên dụng.
