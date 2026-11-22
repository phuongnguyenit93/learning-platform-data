# Tải JSON hoặc YAML từ endpoint tài liệu đang chạy

Springdoc-openapi tạo OpenAPI document từ controller, model, cấu hình và Swagger annotations của ứng dụng Spring Boot. Khi ứng dụng đang chạy, document có thể được lấy trực tiếp qua HTTP endpoint. Theo cấu hình mặc định, endpoint JSON là `/v3/api-docs`, còn endpoint YAML là `/v3/api-docs.yaml`.

Việc tải trực tiếp từ endpoint đang chạy hữu ích khi cần kiểm tra hợp đồng API của một môi trường, lưu artifact để review, đưa đặc tả vào pipeline CI hoặc chuyển tài liệu cho công cụ sinh SDK. Cần gọi đúng endpoint, đúng group, xác thực nếu tài liệu được bảo vệ và kiểm tra nội dung sau khi tải để tránh lưu trang lỗi HTML dưới tên file JSON/YAML.

## 1. Endpoint tài liệu mặc định

Khi dùng springdoc-openapi với Spring MVC hoặc WebFlux, các endpoint thường gặp là:

| Nội dung | Endpoint mặc định |
|---|---|
| OpenAPI JSON | `/v3/api-docs` |
| OpenAPI YAML | `/v3/api-docs.yaml` |
| OpenAPI JSON của group | `/v3/api-docs/{group-name}` |
| OpenAPI YAML của group | `/v3/api-docs.yaml/{group-name}` |
| Swagger UI entry | `/swagger-ui.html` |
| Swagger UI assets | `/swagger-ui/**` |
| Swagger UI config | `/v3/api-docs/swagger-config` |

Ví dụ khi ứng dụng chạy ở cổng 8080:

~~~text
http://localhost:8080/v3/api-docs
http://localhost:8080/v3/api-docs.yaml
http://localhost:8080/swagger-ui.html
~~~

Hai endpoint đầu trả về OpenAPI document ở hai định dạng khác nhau. Swagger UI là giao diện trình bày và tương tác với tài liệu; URL Swagger UI không phải file đặc tả JSON/YAML để lưu trực tiếp.

Các URL trên là mặc định. Ứng dụng có thể thay đổi `springdoc.api-docs.path`, context path, WebFlux base path hoặc được đặt sau reverse proxy có prefix. Khi đó phải dùng URL public thực tế của môi trường.

## 2. Điều kiện để tải được tài liệu

Trước khi gọi endpoint, xác nhận:

1. Ứng dụng Spring Boot đã khởi động và đang lắng nghe đúng host/port.
2. Project có springdoc starter tương ứng với Spring MVC hoặc WebFlux.
3. API docs đang được bật.
4. Proxy/gateway định tuyến endpoint tài liệu đến ứng dụng.
5. Security policy cho phép tài khoản hoặc token của bạn đọc tài liệu.
6. Bạn đang gọi đúng group và đúng base path nếu ứng dụng có cấu hình riêng.

Có thể bật hoặc tắt endpoint API docs bằng cấu hình:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

Nếu đặt `enabled: false`, endpoint OpenAPI không được cung cấp theo cấu hình đó. Thuộc tính `springdoc.swagger-ui.enabled` điều khiển Swagger UI riêng; tắt UI không tự động tắt endpoint JSON/YAML.

Ví dụ chỉ tắt giao diện nhưng vẫn cho phép tải đặc tả:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Ngược lại, nếu API docs bị tắt, Swagger UI không có document để tải dù trang giao diện có thể vẫn được cấu hình. Hãy kiểm tra cả hai thành phần theo đúng mục đích triển khai.

## 3. Tải JSON bằng curl

Lệnh đơn giản để lưu OpenAPI JSON vào file:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Các tùy chọn:

- `-f` làm curl trả lỗi khi HTTP status là 400 trở lên.
- `-S` hiển thị thông báo lỗi khi lệnh thất bại.
- `-o openapi.json` ghi response body vào file thay vì in ra terminal.

Nếu ứng dụng chuyển hướng URL, có thể thêm `-L` để theo redirect:

~~~bash
curl -fSL http://localhost:8080/v3/api-docs -o openapi.json
~~~

Không nên bỏ `-f` trong script export mà không kiểm tra status code. Nếu server trả trang đăng nhập hoặc trang lỗi với HTTP 200, curl vẫn có thể lưu nội dung đó vào file. Vì vậy cần xác minh JSON sau khi tải.

## 4. Tải YAML bằng curl

YAML có endpoint riêng, thường thêm hậu tố `.yaml`:

~~~bash
curl -fS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
~~~

Không đổi tên file JSON thành `openapi.yaml` để tạo YAML. Phần mở rộng file không chuyển đổi nội dung; phải gọi endpoint YAML hoặc dùng một công cụ chuyển đổi có kiểm soát.

JSON và YAML biểu diễn cùng một OpenAPI document. Khác biệt chủ yếu nằm ở cú pháp serialization; cấu trúc `openapi`, `info`, `servers`, `paths`, `components` và các operation vẫn mang cùng ý nghĩa.

## 5. Tải JSON và YAML trong một lần chạy

Một script shell có thể tải cả hai định dạng:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8080"
OUTPUT_DIR="build/openapi"

mkdir -p "$OUTPUT_DIR"

curl -fS "$BASE_URL/v3/api-docs" \
  -o "$OUTPUT_DIR/openapi.json"

curl -fS "$BASE_URL/v3/api-docs.yaml" \
  -o "$OUTPUT_DIR/openapi.yaml"
~~~

`set -e` khiến script dừng khi lệnh tải thất bại. Điều này ngăn pipeline tiếp tục đóng gói hoặc phát hành artifact chưa được tạo thành công.

Nếu dùng script trong CI, hãy truyền base URL bằng biến môi trường hoặc tham số pipeline. Không ghi cứng URL local khi cùng script cần chạy ở test hoặc production.

## 6. Tải file trên Windows PowerShell

Trong PowerShell, có thể dùng `Invoke-WebRequest`:

~~~powershell
$BaseUrl = "http://localhost:8080"
Invoke-WebRequest -Uri "$BaseUrl/v3/api-docs" -OutFile ".\openapi.json"
Invoke-WebRequest -Uri "$BaseUrl/v3/api-docs.yaml" -OutFile ".\openapi.yaml"
~~~

Trên Windows, `curl` có thể là alias của `Invoke-WebRequest` trong một số phiên bản PowerShell. Nếu muốn chạy chương trình curl thực, gọi rõ `curl.exe`:

~~~powershell
curl.exe -fS "http://localhost:8080/v3/api-docs" -o ".\openapi.json"
curl.exe -fS "http://localhost:8080/v3/api-docs.yaml" -o ".\openapi.yaml"
~~~

Với pipeline, hãy cấu hình xử lý lỗi để bước sau chỉ chạy khi request thành công.

## 7. Tải tài liệu khi endpoint yêu cầu Bearer token

API docs có thể được bảo vệ bằng Spring Security. Khi endpoint yêu cầu access token, gửi token trong header Authorization:

~~~bash
curl -fS \
  -H "Authorization: Bearer $OPENAPI_TOKEN" \
  http://localhost:8080/v3/api-docs \
  -o openapi.json
~~~

Biến `OPENAPI_TOKEN` nên được cấp từ secret store của môi trường hoặc secret variable của CI. Không ghi token trực tiếp vào source code, file YAML được commit hoặc log pipeline.

PowerShell:

~~~powershell
$Headers = @{ Authorization = "Bearer $env:OPENAPI_TOKEN" }
Invoke-WebRequest -Uri "https://test.example.com/v3/api-docs" -Headers $Headers -OutFile ".\openapi-test.json"
~~~

Nếu dùng HTTP Basic, API key hoặc cơ chế xác thực khác, header phải theo security scheme thực tế của ứng dụng. Không mặc định mọi endpoint docs đều dùng Bearer token.

## 8. Tải tài liệu theo group

Khi ứng dụng khai báo nhiều `GroupedOpenApi`, mỗi group có document riêng. Ví dụ:

~~~java
@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .pathsToExclude("/api/internal/**")
                .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
                .group("admin")
                .pathsToMatch("/admin/**")
                .build();
    }
}
~~~

Với tên group là `public` và `admin`, endpoint mặc định thường có dạng:

~~~text
/v3/api-docs/public
/v3/api-docs.yaml/public
/v3/api-docs/admin
/v3/api-docs.yaml/admin
~~~

Tải group public:

~~~bash
curl -fS http://localhost:8080/v3/api-docs/public -o openapi-public.json
curl -fS http://localhost:8080/v3/api-docs.yaml/public -o openapi-public.yaml
~~~

Tên group trong URL phải khớp chính xác với giá trị `group(...)`. Nếu group không tồn tại hoặc proxy chưa route URL group, server có thể trả 404.

Group chỉ quyết định operation nào xuất hiện trong document tương ứng. Nó không tự bảo vệ endpoint runtime và cũng không tự giới hạn ai được tải document; cần cấu hình Spring Security riêng nếu tài liệu group có phạm vi truy cập hạn chế.

## 9. Tải từ endpoint đã đổi bằng springdoc.api-docs.path

Có thể đổi đường dẫn API docs:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

Khi thay đổi path, endpoint JSON mặc định được chuyển sang path đã cấu hình. Endpoint YAML thường dùng hậu tố `.yaml` tương ứng. Với cấu hình trên, kiểm tra các URL:

~~~text
/openapi
/openapi.yaml
~~~

Nếu ứng dụng có group, kiểm tra cả endpoint group theo path mới. Với cấu hình path là `/openapi`, các dạng thường dùng là `/openapi/{group}` cho JSON và `/openapi.yaml/{group}` cho YAML. Xác nhận trên đúng phiên bản springdoc đang chạy.

Sau khi đổi path, cập nhật script tải artifact, reverse proxy hoặc ingress route, Spring Security request matcher, Swagger UI config URL nếu được khai báo tường minh và các monitoring check có tham chiếu endpoint docs.

## 10. Phân biệt endpoint JSON/YAML với Swagger UI

Swagger UI là ứng dụng web để xem và thử API. Nó thường tải cấu hình từ `/v3/api-docs/swagger-config`, sau đó lấy OpenAPI JSON từ endpoint spec được cấu hình.

| URL | Mục đích | Có phải file đặc tả trực tiếp? |
|---|---|---|
| `/swagger-ui.html` | Trang vào Swagger UI | Không |
| `/swagger-ui/index.html` | Trang giao diện Swagger UI | Không |
| `/v3/api-docs/swagger-config` | Cấu hình cho Swagger UI | Không |
| `/v3/api-docs` | OpenAPI JSON | Có |
| `/v3/api-docs.yaml` | OpenAPI YAML | Có |

Nếu muốn lưu artifact để review hoặc đưa vào code generator, tải endpoint JSON/YAML. Không tải HTML của Swagger UI rồi đổi phần mở rộng thành `.json`.

## 11. Xác nhận file JSON tải về hợp lệ

Sau khi tải, dùng `jq` để parse JSON:

~~~bash
jq empty openapi.json
~~~

Nếu file là JSON hợp lệ, lệnh kết thúc thành công và không in nội dung. Kiểm tra trường phiên bản:

~~~bash
jq -r '.openapi' openapi.json
~~~

Kiểm tra metadata và danh sách path:

~~~bash
jq '.info' openapi.json
jq '.paths | keys' openapi.json
~~~

Nếu `jq` báo lỗi parse, hãy kiểm tra server có trả HTML đăng nhập/trang lỗi, URL có redirect, response có bị proxy thay thế/cắt cụt hoặc file có bị ghi đè bởi bước khác trong pipeline không.

## 12. Xác nhận file YAML tải về

YAML cần được đọc bằng YAML parser. Nếu môi trường đã cài `yq` phiên bản hỗ trợ YAML, có thể kiểm tra:

~~~bash
yq '.openapi' openapi.yaml
yq '.info' openapi.yaml
yq '.paths | keys' openapi.yaml
~~~

Có nhiều chương trình cùng tên `yq` với cú pháp khác nhau. Hãy dùng đúng tài liệu của bản đã cài. Một cách khác là chuyển YAML sang JSON bằng parser phù hợp rồi kiểm tra trường `openapi` và `paths`.

Không chỉ kiểm tra file tồn tại hoặc có dung lượng lớn hơn 0. Trang HTML lỗi cũng là một file không rỗng. Cần parse nội dung và xác nhận có cấu trúc OpenAPI.

## 13. Kiểm tra HTTP status và response headers

Khi debug export, lưu cả response headers:

~~~bash
curl -sS -D openapi-headers.txt \
  -o openapi.json \
  -w "HTTP %{http_code}\nContent-Type: %{content_type}\n" \
  http://localhost:8080/v3/api-docs
~~~

Các thông tin cần xem: HTTP status, `Content-Type`, redirect Location, response JSON/YAML hay HTML và header cache/proxy có làm trả bản tài liệu cũ không.

| Status | Diễn giải có thể gặp | Hướng xử lý |
|---|---|---|
| 200 | Đã trả document | Parse và xác minh nội dung |
| 301/302/307/308 | URL được redirect | Kiểm tra Location và dùng redirect có chủ đích |
| 401 | Thiếu hoặc sai thông tin xác thực | Cấp credential/token phù hợp |
| 403 | Đã xác thực nhưng không có quyền | Kiểm tra authorization rule |
| 404 | Sai path, group hoặc proxy route | Kiểm tra docs path và group name |
| 500 | Lỗi khi tạo document hoặc lỗi ứng dụng | Xem log ứng dụng tại thời điểm request |

HTTP 200 chưa đảm bảo nội dung là OpenAPI. Một reverse proxy hoặc identity gateway có thể trả trang đăng nhập với status 200; parser JSON/YAML sẽ phát hiện trường hợp này.

## 14. Tải qua reverse proxy hoặc context path

Nếu ứng dụng chạy phía sau proxy với public prefix, URL tải tài liệu phải dùng đường dẫn mà client có thể truy cập. Ví dụ public base URL:

~~~text
https://test.example.com/order-service
~~~

Các endpoint public có thể là:

~~~text
https://test.example.com/order-service/v3/api-docs
https://test.example.com/order-service/v3/api-docs.yaml
~~~

Proxy có thể giữ nguyên prefix hoặc gỡ prefix trước khi chuyển request đến ứng dụng. Vì vậy, URL upstream không nhất thiết giống URL public. Hãy kiểm tra cấu hình proxy, forwarded headers và context path theo topology thực tế.

Nếu ứng dụng MVC có `server.servlet.context-path` hoặc WebFlux có `spring.webflux.base-path`, các endpoint docs thường nằm dưới base path đó. Không ghép prefix hai lần giữa proxy và ứng dụng.

## 15. Chọn môi trường khi export

Không nên mặc định document tải từ local giống hoàn toàn với test hoặc production. Mỗi môi trường có thể khác profile Spring, controller/bean theo profile, group/filter, security scheme, server URL, context path, proxy prefix, Jackson và validation.

| Môi trường | Base URL ví dụ | Artifact |
|---|---|---|
| Local | `http://localhost:8080` | `openapi-local.json` |
| Test | `https://test.example.com/order-service` | `openapi-test.json` |
| Production | `https://api.example.com` | `openapi-prod.json` |

Nếu mục tiêu là kiểm tra hợp đồng đang chạy ở test, hãy tải từ test endpoint. Tài liệu sinh từ local có thể không phản ánh đúng cấu hình, profile hoặc operation của test.

## 16. Đặt tên và lưu artifact có thể truy vết

Trong CI, nên đặt tên file thể hiện môi trường, group và phiên bản build:

~~~text
artifacts/
  openapi/
    openapi-public-test.json
    openapi-public-test.yaml
    openapi-admin-test.json
~~~

Có thể đưa commit SHA hoặc build number vào tên artifact, ví dụ `openapi-public-test-<build-id>.json`. Tên file cần giúp truy vết document được tải từ môi trường nào và thời điểm/build nào. Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào tên file hay metadata.

## 17. Dùng biến môi trường trong script export

Không hard-code base URL vào script nếu cùng một script cần chạy trên nhiều môi trường:

~~~bash
#!/usr/bin/env bash
set -eo pipefail

if [ -z "$API_BASE_URL" ]; then
  echo "API_BASE_URL is required" >&2
  exit 1
fi

OUTPUT_DIR="build/openapi"
mkdir -p "$OUTPUT_DIR"

curl -fS "$API_BASE_URL/v3/api-docs" -o "$OUTPUT_DIR/openapi.json"
curl -fS "$API_BASE_URL/v3/api-docs.yaml" -o "$OUTPUT_DIR/openapi.yaml"

jq -e '.openapi and .paths' "$OUTPUT_DIR/openapi.json" > /dev/null
~~~

Đoạn script yêu cầu `API_BASE_URL` phải được khai báo, tải hai định dạng và kiểm tra một số trường cốt lõi trong JSON. Kiểm tra này chỉ là sanity check; nó không thay thế OpenAPI validator.

Nếu endpoint yêu cầu token, thêm Authorization header từ secret variable của CI. Tránh bật shell tracing như `set -x` trong đoạn xử lý secret vì token có thể bị ghi vào log.

## 18. Tự động tải đặc tả trong CI

Một pipeline cơ bản có thể thực hiện theo thứ tự:

1. Khởi động ứng dụng hoặc triển khai ứng dụng đến môi trường kiểm thử.
2. Chờ health check báo ứng dụng sẵn sàng.
3. Gọi endpoint JSON/YAML.
4. Kiểm tra HTTP status và parse file.
5. Chạy OpenAPI validator hoặc contract checks.
6. Lưu file thành build artifact.
7. Dùng artifact ở bước generate SDK, so sánh breaking change hoặc publish developer portal.

Không tải tài liệu ngay khi process vừa được tạo nếu ứng dụng chưa sẵn sàng. Hãy chờ health endpoint hoặc dùng cơ chế readiness của nền tảng để tránh lỗi kết nối ngẫu nhiên.

Ví dụ đoạn shell sau khi ứng dụng đã sẵn sàng:

~~~bash
set -euo pipefail
mkdir -p build/openapi

curl --retry 10 --retry-connrefused --retry-delay 2 -fS \
  "$API_BASE_URL/v3/api-docs" \
  -o build/openapi/openapi.json

jq -e '.openapi and (.paths | type == "object")' \
  build/openapi/openapi.json > /dev/null
~~~

Retry chỉ nên dùng cho lỗi khởi động tạm thời. Nếu nhận 401, 403 hoặc 404 do cấu hình sai, pipeline cần báo lỗi để sửa nguyên nhân thay vì lặp vô hạn.

## 19. So sánh tài liệu tải từ hai lần build

Khi đã lưu OpenAPI artifact, có thể so sánh với bản của build trước để phát hiện operation mới/bị xóa, thay đổi request parameter/body, response status/schema, field required, enum, giới hạn dữ liệu, security requirement hoặc server URL.

Không nên chỉ so sánh byte của JSON/YAML vì thứ tự key, format hoặc metadata không ảnh hưởng hợp đồng có thể thay đổi. Dùng công cụ diff OpenAPI hiểu cấu trúc document và quy tắc compatibility của dự án.

## 20. Lỗi thường gặp khi tải JSON/YAML

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/v3/api-docs` trả 404 | Chưa có springdoc, API docs bị tắt hoặc sai context path | Kiểm tra starter, `springdoc.api-docs.enabled` và base path |
| JSON tải được nhưng YAML 404 | Proxy chưa route hậu tố .yaml hoặc custom path khác | Kiểm tra endpoint YAML của ứng dụng và proxy |
| Group endpoint trả 404 | Group name sai hoặc chưa khai báo group | Kiểm tra `GroupedOpenApi` và URL group |
| File JSON thực chất là HTML | Redirect/login page hoặc proxy error page | Kiểm tra status, Location, Content-Type và parse JSON |
| File rỗng hoặc bị cắt | Kết nối gián đoạn hoặc proxy giới hạn response | Kiểm tra curl exit code, log proxy và response size |
| HTTP 401 | Thiếu token/credential | Gửi đúng Authorization header |
| HTTP 403 | Tài khoản không có quyền xem tài liệu | Điều chỉnh role/authority theo chính sách |
| Swagger UI hoạt động nhưng curl bị từ chối | Browser và shell dùng credential/session khác nhau | Cấu hình xác thực cho script export |
| Tải nhầm tài liệu của môi trường khác | Base URL lấy từ biến môi trường sai | In base URL không chứa secret và xác minh môi trường |
| OpenAPI có path thiếu prefix | Forwarded headers hoặc proxy rewrite chưa đúng | Kiểm tra `servers`, `paths` và request public |
| CI dùng file cũ | Bước export không chạy hoặc output directory giữ artifact cũ | Dùng workspace sạch hoặc kiểm tra timestamp/build id |
| Đổi file .json thành .yaml nhưng parser lỗi | Chỉ đổi tên file, không chuyển serialization | Tải endpoint YAML hoặc dùng converter |

## 21. Checklist trước khi dùng artifact

- [ ] Đã chọn đúng base URL và môi trường.
- [ ] Ứng dụng đang sẵn sàng nhận request.
- [ ] Đã gọi đúng endpoint JSON hoặc YAML.
- [ ] Đã chọn đúng group nếu ứng dụng có nhiều document.
- [ ] Đã gửi credential qua secret variable nếu endpoint được bảo vệ.
- [ ] HTTP status là thành công.
- [ ] File không rỗng và parse được.
- [ ] Trường `openapi` có phiên bản mong đợi.
- [ ] `info`, `paths` và `components` có nội dung phù hợp.
- [ ] `servers` không trỏ đến localhost hoặc hostname nội bộ ngoài ý muốn.
- [ ] Artifact được đặt tên và lưu theo build/môi trường để truy vết.

## 22. Nguyên tắc thiết kế

- Dùng `/v3/api-docs` để tải JSON và `/v3/api-docs.yaml` để tải YAML theo mặc định.
- Dùng endpoint group khi cần tài liệu cho một tập operation cụ thể.
- Phân biệt Swagger UI, Swagger config và OpenAPI document.
- Kiểm tra custom docs path, context path, WebFlux base path và proxy prefix.
- Tải từ đúng môi trường mà hợp đồng cần đại diện.
- Gửi credential qua secret store hoặc biến môi trường, không hard-code.
- Kiểm tra HTTP status, response headers và nội dung file sau khi tải.
- Không xem file tồn tại hoặc HTTP 200 là bằng chứng document hợp lệ.
- Lưu artifact có tên truy vết được và dùng OpenAPI-aware diff/validator trong CI.
- Giữ Swagger UI và endpoint JSON/YAML bật/tắt độc lập theo nhu cầu triển khai.

## Kết luận

Khi ứng dụng Spring Boot đang chạy với springdoc-openapi, có thể tải trực tiếp OpenAPI JSON từ `/v3/api-docs` và YAML từ `/v3/api-docs.yaml`. Với nhiều document, dùng endpoint theo group; nếu đổi docs path, context path hoặc đặt ứng dụng sau proxy, hãy gọi URL public đã cấu hình. Dùng curl hoặc PowerShell để lưu file, gửi credential an toàn khi cần và xác minh status cùng nội dung bằng parser. Trong CI, chỉ lưu và sử dụng artifact sau khi tải thành công, parse hợp lệ và xác nhận đúng môi trường, group cùng phiên bản OpenAPI.

## Tài liệu tham khảo

- [springdoc-openapi v2 FAQ: nhóm OpenAPI và endpoint group](https://springdoc.org/v2/faq.html)
- [springdoc-openapi Core Properties: `springdoc.api-docs.path` và `springdoc.api-docs.enabled`](https://springdoc.org/core-properties.html)
- [springdoc-openapi issue #1600: endpoint YAML cho một group](https://github.com/springdoc/springdoc-openapi/issues/1600)
