# Xuất từng nhóm và xác minh đúng tập endpoint

Một ứng dụng Spring Boot có thể công bố nhiều OpenAPI document bằng `GroupedOpenApi`: tài liệu public cho đối tác, tài liệu nội bộ cho đội phát triển hoặc tài liệu quản trị cho vận hành. Khi đưa tài liệu vào CI, cần xuất đúng document của từng nhóm và xác minh tập operation trong document khớp với phạm vi đã thống nhất.

Chỉ kiểm tra endpoint `/v3/api-docs` mặc định là chưa đủ. Endpoint này có thể không đại diện cho các nhóm được công bố riêng. Một nhóm public có thể vô tình chứa endpoint nội bộ do filter chồng lấn; ngược lại, một endpoint mới có thể bị thiếu khỏi tài liệu mà build vẫn thành công. Cách kiểm tra đáng tin cậy là lưu danh sách kỳ vọng theo từng group id, trích xuất cặp HTTP method và path từ OpenAPI JSON rồi so sánh chính xác trong CI.

## 1. Tạo các nhóm tài liệu có định danh ổn định

Ví dụ ứng dụng có hai nhóm: `public-v1` và `internal-v1`:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
            .group("internal-v1")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/public/**")
            .build();
    }
}
```

`group(...)` là định danh được dùng trong URL export. Nó không phải tên bean Java và cũng không phải `info.title` của OpenAPI document. Hãy đặt group id ngắn, ổn định và dễ dùng trong tên artifact, manifest và pipeline.

Filter có thể dựa trên path, package controller hoặc kết hợp nhiều điều kiện. Nếu một operation khớp nhiều nhóm, operation đó có thể xuất hiện trong nhiều document. Đây có thể là chủ ý, nhưng phải được thể hiện trong manifest của từng nhóm. `GroupedOpenApi` phân chia nội dung tài liệu; nó không tự bảo vệ URL tải document.

## 2. URL JSON và YAML của từng nhóm

Với base path mặc định, springdoc cung cấp document theo group id:

| Document | URL |
| --- | --- |
| OpenAPI JSON mặc định | `/v3/api-docs` |
| OpenAPI YAML mặc định | `/v3/api-docs.yaml` |
| JSON của `public-v1` | `/v3/api-docs/public-v1` |
| YAML của `public-v1` | `/v3/api-docs/public-v1.yaml` |
| JSON của `internal-v1` | `/v3/api-docs/internal-v1` |
| YAML của `internal-v1` | `/v3/api-docs/internal-v1.yaml` |

JSON và YAML là hai cách biểu diễn cùng một OpenAPI document. Trong CI, JSON thuận tiện cho việc phân tích bằng `jq`; YAML thuận tiện cho review và lưu trữ nếu đội dự án dùng YAML làm artifact công bố.

Nếu ứng dụng thay đổi `springdoc.api-docs.path`, URL nhóm cũng dùng base path mới. Ví dụ:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
```

Khi đó URL JSON của nhóm là `/internal/openapi/public-v1`, YAML là `/internal/openapi/public-v1.yaml`. Nếu có `server.servlet.context-path` hoặc prefix từ reverse proxy, dùng URL public đầy đủ mà pipeline có thể truy cập.

## 3. Xuất từng nhóm thành artifact riêng

Đặt tên file theo group id để tránh ghi đè document của nhóm khác:

```text
build/openapi/
  public-v1.json
  public-v1.yaml
  internal-v1.json
  internal-v1.yaml
```

Ví dụ dùng `curl` trong Bash:

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${DOCS_BASE_URL:?Set DOCS_BASE_URL to the running application URL}"
BASE_URL="${DOCS_BASE_URL%/}"

auth_args=()
if [[ -n "${DOCS_TOKEN:-}" ]]; then
  auth_args+=(--header "Authorization: Bearer ${DOCS_TOKEN}")
fi

mkdir -p build/openapi

download_document() {
  local url="$1"
  local output="$2"
  local status

  status="$(curl --fail --silent --show-error \
    "${auth_args[@]}" \
    --output "$output" \
    --write-out '%{http_code}' \
    "$url")"

  if [[ "$status" != "200" ]]; then
    printf 'Expected HTTP 200 from %s, received %s\n' "$url" "$status" >&2
    return 1
  fi
}

for group in public-v1 internal-v1; do
  download_document \
    "${BASE_URL}/v3/api-docs/${group}" \
    "build/openapi/${group}.json"

  download_document \
    "${BASE_URL}/v3/api-docs/${group}.yaml" \
    "build/openapi/${group}.yaml"
done
```

`DOCS_BASE_URL` là URL của ứng dụng đang chạy trong job CI hoặc môi trường export. Nếu endpoint tài liệu yêu cầu bearer token, cấp `DOCS_TOKEN` từ secret store của CI. Không bật shell tracing (`set -x`) khi xử lý token và không in header Authorization ra log. Nếu tài liệu public không cần xác thực, để `DOCS_TOKEN` rỗng.

`curl --fail` làm job thất bại khi server trả HTTP error như `401`, `403` hoặc `404`. Nhờ vậy pipeline không lưu một trang đăng nhập hoặc trang lỗi HTML với tên file `.json` rồi coi đó là tài liệu hợp lệ.

Hàm download_document yêu cầu status 200 và không tự đi theo redirect. Điều này giúp phát hiện URL sai hoặc redirect đến trang đăng nhập; đồng thời tránh chuyển tiếp header bearer đến host khác trong một redirect. Nếu hệ thống có redirect hợp lệ, hãy cấu hình URL đích cuối cùng trong DOCS_BASE_URL thay vì bật theo redirect một cách mù quáng.

## 4. Kiểm tra document tải về trước khi so sánh

Sau khi export, xác nhận mỗi file JSON là OpenAPI document hợp lệ ở mức cấu trúc cơ bản:

```bash
for group in public-v1 internal-v1; do
  jq -e '
    (.openapi | type == "string") and
    (.paths | type == "object")
  ' "build/openapi/${group}.json" >/dev/null
done
```

Kiểm tra này phát hiện JSON sai cú pháp, response HTML hoặc document thiếu `openapi`/`paths`. Nó chưa thay thế OpenAPI validator: một JSON có cấu trúc cơ bản đúng vẫn có thể chứa `$ref` hỏng, schema không hợp lệ hoặc metadata sai.

Nếu cần kiểm tra YAML, dùng YAML parser hoặc OpenAPI linter đã được pin phiên bản trong CI. Tránh dùng một lệnh `yq` chung mà không xác nhận đó là implementation và cú pháp phù hợp với runner của dự án.

## 5. Lưu manifest tập endpoint kỳ vọng cho từng nhóm

Manifest nên ghi một operation trên mỗi dòng theo dạng `HTTP_METHOD path`. Ví dụ:

`ci/openapi/expected-public-v1.txt`:

```text
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

`ci/openapi/expected-internal-v1.txt`:

```text
DELETE /api/admin/orders/{id}
GET /api/admin/audit-events
GET /api/internal/health
```

Manifest mô tả đúng những operation được phép xuất hiện trong từng document. Dùng path template như `{id}` đúng với OpenAPI; không thay bằng một giá trị ID cụ thể. Sắp xếp các dòng theo thứ tự ổn định và không để dòng trùng lặp.

Danh sách này là allowlist hợp đồng của nhóm. Nếu endpoint bị thiếu, CI phát hiện thiếu dòng. Nếu endpoint ngoài phạm vi xuất hiện, CI phát hiện dòng thừa. Cả hai trường hợp đều cần được review: có thể code/filter sai, hoặc manifest cần cập nhật vì thay đổi API đã được phê duyệt.

## 6. Trích xuất HTTP method và path bằng `jq`

OpenAPI đặt các endpoint trong object `paths`. Mỗi path chứa một hoặc nhiều operation theo HTTP method. Có thể trích xuất chính xác cặp method/path bằng:

```bash
jq -r '
  (.paths // {})
  | to_entries[]
  | . as $path
  | $path.value
  | to_entries[]
  | select(.key | test("^(get|put|post|delete|patch|options|head|trace)$"))
  | "\(.key | ascii_upcase) \($path.key)"
' build/openapi/public-v1.json \
  | LC_ALL=C sort -u
```

Kết quả có dạng:

```text
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

Chỉ các khóa operation HTTP được tính. Các thuộc tính khác của Path Item như `parameters`, `servers`, `summary`, `description` hoặc `$ref` không bị hiểu nhầm thành endpoint. Việc ghép cả method và path cũng phân biệt được `GET /orders` với `POST /orders`.

## 7. So sánh chính xác trong CI

Tạo file endpoint thực tế từ JSON rồi dùng `diff` với manifest:

```bash
for group in public-v1 internal-v1; do
  expected="ci/openapi/expected-${group}.txt"
  actual="build/openapi/${group}.actual.txt"

  test -f "$expected"

  jq -r '
    (.paths // {})
    | to_entries[]
    | . as $path
    | $path.value
    | to_entries[]
    | select(.key | test("^(get|put|post|delete|patch|options|head|trace)$"))
    | "\(.key | ascii_upcase) \($path.key)"
  ' "build/openapi/${group}.json" \
    | LC_ALL=C sort -u > "$actual"

  LC_ALL=C sort -c "$expected"
  diff -u "$expected" "$actual"
done
```

`diff` trả exit code khác `0` nếu hai tập khác nhau, khiến job CI thất bại khi dùng `set -e`. Output cho biết operation nào bị thiếu hoặc xuất hiện ngoài dự kiến. `sort -c` xác nhận manifest đã được sắp xếp theo cùng locale trước khi so sánh.

Nên giữ manifest trong repository cùng thay đổi API. Khi thêm operation mới, cập nhật manifest trong cùng pull request và để reviewer đánh giá endpoint đó có thuộc nhóm được công bố hay không. Không tự động ghi đè manifest bằng output vừa export; làm vậy sẽ khiến kiểm tra allowlist mất ý nghĩa.

## 8. Ví dụ kết quả khi tập endpoint sai

Giả sử manifest public kỳ vọng:

```text
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

Nhưng document thực tế có thêm endpoint nội bộ:

```text
DELETE /api/admin/orders/{id}
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

`diff -u` sẽ báo dòng `DELETE /api/admin/orders/{id}` là phần thừa. Đây là tín hiệu cần điều tra `pathsToMatch`, `pathsToExclude`, package filter hoặc customizer của nhóm public. Chỉ xóa dòng khỏi artifact sau khi đã sửa nguồn tạo document và chạy lại export.

Nếu endpoint `/api/public/products/{id}` bị thiếu, diff báo phần thiếu. Kiểm tra controller mapping, filter path/package, annotation ẩn và điều kiện auto-configuration. Không sửa manifest để chấp nhận thiếu endpoint nếu chưa xác nhận đó là thay đổi hợp đồng có chủ đích.

## 9. Xử lý nhóm có filter chồng lấn

Một operation có thể xuất hiện trong nhiều group nếu nhiều filter cùng khớp. Ví dụ `/api/public/catalog` có thể được đưa vào cả `public-v1` và `all-v1`. Điều này không nhất thiết là lỗi.

Hãy tạo manifest riêng cho từng group:

| Group | Manifest kỳ vọng | Quy tắc |
| --- | --- | --- |
| `public-v1` | Chỉ endpoint public | Không chứa route nội bộ hoặc quản trị. |
| `internal-v1` | Endpoint nội bộ và quản trị được phép | Không tự động chứa route public nếu không có mục đích. |
| `all-v1` | Toàn bộ API được chọn công bố | Có thể bao gồm endpoint thuộc các nhóm khác. |

Không giả định các group là các tập rời nhau. Nếu cần chúng không giao nhau, thêm kiểm tra giao giữa manifest hoặc actual endpoint set. Nếu overlap là chủ ý, ghi rõ trong manifest và review thay đổi ở cả những group bị ảnh hưởng.

## 10. Kiểm tra thêm operation ID, schema và security

So sánh method/path xác nhận tập endpoint, nhưng chưa kiểm tra toàn bộ hợp đồng. Có thể bổ sung các bước CI khác:

- **Operation ID:** xác nhận `operationId` không trùng trong một document để client generator tạo tên method ổn định.
- **Schema:** kiểm tra kiểu, required, enum, format và validation metadata.
- **References:** xác nhận mọi `$ref` trỏ đến component hợp lệ.
- **Security:** xác nhận group public không vô tình công bố operation với yêu cầu bảo mật sai hoặc thiếu.
- **Media type và response:** kiểm tra `requestBody`, `content`, status code và headers.
- **Compatibility:** so sánh document với phiên bản đã phát hành để phát hiện breaking change.

Nên dùng OpenAPI validator/linter và công cụ diff chuyên dụng đã pin phiên bản. Exact endpoint manifest và OpenAPI contract diff giải quyết hai câu hỏi khác nhau: endpoint nào có mặt, và chi tiết hợp đồng của endpoint có thay đổi tương thích hay không.

## 11. Bảo vệ tài liệu khi export từ môi trường chạy

CI có thể cần gọi endpoint tài liệu từ ứng dụng đang chạy. Nếu một group chỉ dành cho nội bộ, pipeline phải dùng credential có quyền đọc đúng group đó. Không mở tất cả `/v3/api-docs/**` ra Internet chỉ để CI lấy artifact.

Một số lưu ý:

- Dùng service account hoặc token ngắn hạn có quyền đọc tài liệu cần export.
- Lưu token trong secret store của CI, không commit vào script hoặc manifest.
- Không bật shell tracing khi token nằm trong biến môi trường.
- Tải từng group bằng URL cụ thể; không suy luận rằng group bị ẩn khỏi Swagger UI thì endpoint đã được bảo vệ.
- Nếu API docs path được tùy chỉnh, cấu hình base URL trong CI theo path thực tế.
- Với reverse proxy, dùng URL public mà runner có thể truy cập và kiểm tra forwarded prefix.
- Không publish artifact internal vào kho artifact public; phân quyền ở bước lưu trữ cũng quan trọng như phân quyền endpoint tải.

Nếu pipeline chạy trong cùng network với service, có thể export qua URL nội bộ. Dù vậy, vẫn cần kiểm tra document đúng group và đúng build version; việc gọi được endpoint nội bộ không bảo đảm request đến đúng instance.

## 12. Kiểm thử export bằng Spring Boot test

Ngoài việc export từ ứng dụng đang chạy, có thể kiểm tra từng group trong test context. Ví dụ với MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupExportTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicGroupContainsOnlyExpectedOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/public/catalog'].get").exists())
            .andExpect(jsonPath("$.paths['/api/admin/orders/{id}']").doesNotExist());
    }

    @Test
    void internalGroupContainsAdminOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/admin/orders/{id}'].delete").exists());
    }
}
```

Đây là ví dụ kiểm tra một vài path quan trọng trong test context. Manifest + `jq` + `diff` ở CI mới xác minh toàn bộ tập method/path của document được export. Nếu endpoint docs được bảo vệ trong test, cấu hình authentication hoặc test security phù hợp; không tắt security production chỉ để test export.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Export group trả `404` | Group id không tồn tại hoặc URL base path sai | Kiểm tra `.group(...)`, `springdoc.api-docs.path` và context path. |
| Export group trả `401`/`403` | CI thiếu credential hoặc authority đọc docs | Cấp token/service account đúng quyền qua secret store. |
| File `.json` thực chất là HTML | Server redirect/login hoặc proxy trả trang lỗi | Dùng `curl --fail`, kiểm tra status và `Content-Type`. |
| JSON tải được nhưng `jq` lỗi | Response không phải JSON hợp lệ hoặc file rỗng | Kiểm tra body và request URL trước khi chạy diff. |
| Group public có endpoint nội bộ | Filter chồng lấn, exclude sai hoặc customizer thêm operation | So sánh manifest, kiểm tra filter và sửa cấu hình nhóm. |
| Group thiếu endpoint vừa thêm | Controller không được scan hoặc path không khớp filter | Kiểm tra mapping, package/path filter và annotation ẩn. |
| JSON đúng nhưng YAML không tải được | URL YAML sai, proxy/security chưa route hậu tố `.yaml` | Kiểm tra `${group}.yaml` và matcher/gateway. |
| Diff luôn thất bại dù cùng endpoint | Manifest chưa sort, khác chữ hoa method hoặc path template | Chuẩn hóa method uppercase, path nguyên dạng và locale sort. |
| Diff không phát hiện thay đổi schema | Manifest chỉ kiểm tra method/path | Thêm OpenAPI validator và contract diff. |
| Artifact nhóm nội bộ bị publish công khai | Pipeline dùng chung nơi lưu artifact | Tách job, repository hoặc quyền đọc theo nhóm tài liệu. |
| Tài liệu từ instance cũ | CI gọi nhầm URL, pod hoặc deployment chưa cập nhật | Kiểm tra build/version và readiness trước khi export. |

## 14. Checklist cho pipeline

Trước khi đánh dấu export thành công, xác nhận:

1. Group id trong danh sách export khớp bean `GroupedOpenApi` hoặc `springdoc.group-configs`.
2. JSON và YAML được tải từ đúng URL của từng group.
3. HTTP error làm job thất bại; response không phải document không được lưu như artifact hợp lệ.
4. JSON parse được và có `openapi` cùng `paths`.
5. Manifest kỳ vọng tồn tại, được sort và review trong repository.
6. Tập `HTTP_METHOD path` thực tế bằng chính xác manifest của từng group.
7. Group overlap được kiểm tra và chấp nhận có chủ đích.
8. OpenAPI validator/linter kiểm tra schema, `$ref`, security và response.
9. Artifact được đặt tên theo group id và build version.
10. Tài liệu nội bộ chỉ được lưu trong nơi có quyền truy cập phù hợp.

## 15. Nguyên tắc áp dụng

- Export `/v3/api-docs/{group}` và `/v3/api-docs/{group}.yaml` cho từng group cần phát hành.
- Dùng group id ổn định để đặt tên artifact và manifest.
- Dùng JSON làm đầu vào máy có thể phân tích; lưu YAML nếu quy trình review cần định dạng dễ đọc.
- Duy trì allowlist `HTTP_METHOD path` riêng cho từng group.
- Trích xuất operation từ `paths` bằng parser JSON, không grep chuỗi trong file.
- Dùng `diff` để phát hiện cả endpoint thiếu và endpoint thừa.
- Không tự động cập nhật manifest từ document vừa export; yêu cầu review thay đổi hợp đồng.
- Xem filter overlap là hành vi cần xác nhận, không giả định group loại trừ nhau.
- Bổ sung OpenAPI lint/contract diff để kiểm tra schema và compatibility ngoài tập endpoint.
- Bảo vệ endpoint export, token CI và artifact nội bộ theo đúng quyền.

Xuất từng nhóm giúp tạo artifact OpenAPI đúng phạm vi công bố; manifest endpoint giúp CI kiểm tra chính xác operation nào được phép xuất hiện. Khi pipeline tải riêng JSON/YAML theo group id, trích xuất cặp method/path và so sánh bằng `diff`, thay đổi ngoài dự kiến sẽ bị phát hiện trước khi tài liệu được phát hành. Kết hợp bước này với OpenAPI validation và quản lý quyền artifact giúp tài liệu của từng nhóm ổn định, có thể review và phù hợp với phạm vi API đã thống nhất.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Multiple OpenAPI Definitions / GroupedOpenApi](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – API Docs and YAML configuration](https://springdoc.org/)
- [OpenAPI Specification – Paths Object](https://spec.openapis.org/oas/latest.html#paths-object)
- [jq Manual](https://jqlang.org/manual/)
