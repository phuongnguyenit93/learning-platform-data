# Kiểm chứng API bằng `curl` mà không làm lộ giá trị bí mật

Spring Cloud Config Server cung cấp cấu hình cho ứng dụng qua HTTP API. Khi kiểm tra API, người vận hành cần xác nhận đúng ứng dụng, profile, label, trạng thái HTTP và các property source được trả về. Response có thể chứa mật khẩu, token hoặc thông tin nội bộ, vì vậy một lệnh `curl` tiện lợi nhưng in toàn bộ response ra terminal, log CI hoặc ticket có thể làm lộ dữ liệu nhạy cảm.

Mục tiêu của kiểm chứng an toàn là thu thập đủ bằng chứng để biết request có thành công và cấu hình có đúng cấu trúc hay không, đồng thời giữ response trong vùng lưu trữ được bảo vệ và chỉ kiểm tra những thông tin cần thiết. Không cần in giá trị bí mật để chứng minh một key có mặt hoặc API trả về đúng bộ cấu hình.

## 1. Xác định endpoint cần kiểm tra

Endpoint Environment phổ biến của Config Server có dạng:

```text
/{application}/{profile}/{label}
```

Trong đó:

- `application` là tên ứng dụng, thường khớp với `spring.application.name` của Config Client.
- `profile` là một hoặc nhiều profile mà client yêu cầu, ví dụ `staging` hoặc `production`.
- `label` xác định phiên bản backend, thường là branch, tag hoặc commit khi dùng Git.

Ví dụ kiểm tra cấu hình production của `order-service` tại tag `config-release-2026.11.0`:

```text
https://config.example.internal/order-service/production/config-release-2026.11.0
```

Request cần dùng đúng application, profile và label của môi trường đang điều tra. Gọi sai profile hoặc label có thể trả về một bộ cấu hình hợp lệ nhưng không phải bộ mà instance production đang sử dụng.

Config Server cũng có thể cung cấp các endpoint theo định dạng file như YAML hoặc properties tùy phiên bản và cách cấu hình. Với kiểm tra tự động, endpoint Environment trả JSON thường thuận tiện hơn vì có cấu trúc `name`, `profiles`, `label`, `version` và `propertySources`. Cần xác minh endpoint và định dạng trên đúng phiên bản Spring Cloud Config của hệ thống.

## 2. Chuẩn bị xác thực và TLS

Trước khi gọi API, hãy xác định cơ chế xác thực mà Config Server yêu cầu: HTTP Basic, Bearer token, client certificate hoặc cơ chế do reverse proxy/API gateway cung cấp. Dùng danh tính chỉ có quyền đọc cấu hình cần kiểm tra.

Với HTTP Basic, có thể yêu cầu `curl` hỏi mật khẩu tương tác bằng cách chỉ truyền username:

```bash
curl --user "$CONFIG_USER" \
  --url "https://config.example.internal/order-service/production/config-release-2026.11.0"
```

Khi không truyền phần password, `curl` có thể hỏi mật khẩu trong terminal tương tác. Không viết `--user username:password` với mật khẩu thật trong câu lệnh vì nội dung có thể xuất hiện trong shell history, danh sách tiến trình hoặc log công cụ.

Trong pipeline không tương tác, dùng credential được cấp từ secret manager hoặc file cấu hình xác thực có quyền truy cập hạn chế. Với Basic Auth, file netrc được provision riêng cho job có thể có dạng:

```text
machine config.example.internal
login CONFIG_USER
password CONFIG_PASSWORD
```

Các giá trị trên chỉ là placeholder. File thật phải được tạo từ secret store bên ngoài repository, chỉ job cần thiết mới đọc được và có quyền tương đương `0600` trên hệ thống Unix-like. Truyền đường dẫn bằng `--netrc-file "$CURL_NETRC"`; không in nội dung file và không upload nó thành artifact CI. Với Bearer token, có thể dùng `--config` chứa header đã được provision an toàn.

Luôn xác minh chứng thư TLS của server. Nếu dùng CA nội bộ, cung cấp CA hợp lệ bằng `--cacert /path/to/internal-ca.pem`. Không dùng `-k` hoặc `--insecure` để bỏ kiểm tra chứng thư trong quy trình vận hành; cách đó làm mất khả năng xác thực endpoint và có thể khiến credential gửi tới máy chủ giả mạo.

Nếu hệ thống dùng mutual TLS, có thể truyền đường dẫn tới client certificate và private key được bảo vệ bằng `--cert` và `--key`. Không đưa nội dung private key vào câu lệnh, tài liệu hoặc log.

## 3. Gọi API và chỉ in trạng thái HTTP

Để tránh in response body, dùng `--output` ghi body vào file tạm có quyền truy cập riêng và `--write-out` chỉ in mã trạng thái HTTP. Ví dụ dưới đây dùng Bash:

```bash
set +x
umask 077
response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT

url="https://config.example.internal/order-service/production/config-release-2026.11.0"

if http_status="$(curl \
  --silent \
  --show-error \
  --fail \
  --connect-timeout 5 \
  --max-time 15 \
  --netrc-file "$CURL_NETRC" \
  --header 'Accept: application/json' \
  --output "$response_file" \
  --write-out '%{http_code}' \
  "$url")"; then
  printf 'Config API request succeeded (HTTP %s)\n' "$http_status"
else
  printf 'Config API request failed (HTTP %s)\n' "$http_status" >&2
  exit 1
fi
```

Các điểm quan trọng:

- `--silent --show-error` tắt progress meter nhưng vẫn hiển thị lỗi kết nối cần thiết.
- `--fail` làm `curl` trả mã lỗi với HTTP 4xx/5xx; response body không được in ra terminal.
- `--output` giữ response trong file thay vì stdout.
- `--write-out '%{http_code}'` chỉ xuất mã trạng thái.
- `umask 077` giúp file tạm được tạo với quyền truy cập hạn chế trên hệ thống Unix-like.
- `trap` xóa file tạm khi script kết thúc bình thường hoặc nhận tín hiệu được xử lý.

Response file vẫn là dữ liệu nhạy cảm. Chỉ dùng vùng lưu trữ tạm được bảo vệ, không đặt nó trong thư mục chia sẻ, không đính kèm vào ticket và không lưu như artifact CI. Xóa file không đảm bảo ghi đè vật lý dữ liệu trên SSD hoặc snapshot; môi trường xử lý cần có chính sách lưu trữ phù hợp.

Nếu muốn xác minh cả content type, có thể thêm `%{content_type}` vào `--write-out`, nhưng chỉ in metadata cần thiết. Tránh in toàn bộ response headers nếu không cần vì header cũng có thể chứa cookie hoặc thông tin xác thực.

## 4. Kiểm tra JSON mà không in giá trị

Response Environment thường có dạng rút gọn như sau:

```json
{
  "name": "order-service",
  "profiles": ["production"],
  "label": "config-release-2026.11.0",
  "version": "a1b2c3d4",
  "propertySources": [
    {
      "name": ".../order-service-production.yml",
      "source": {
        "checkout.timeout": "2s",
        "spring.datasource.password": "REDACTED"
      }
    }
  ]
}
```

Response thực tế có thể có nhiều property source và nhiều trường khác. Không dùng `jq .`, `cat`, `type` hoặc `Get-Content` để in toàn bộ response khi nó có thể chứa secret.

Có thể dùng `jq` để kiểm tra cấu trúc và chỉ xuất kết quả boolean:

```bash
# Xác nhận có ít nhất một property source
jq -e '(.propertySources | type == "array") and (.propertySources | length > 0)' \
  "$response_file" >/dev/null

# Xác nhận key cần thiết tồn tại mà không đọc/in giá trị của key
if jq -e 'any(.propertySources[]?.source?; has("checkout.timeout"))' \
  "$response_file" >/dev/null; then
  echo "checkout.timeout is present"
else
  echo "checkout.timeout is missing" >&2
  exit 1
fi

# Chỉ kiểm tra sự hiện diện của secret key, không xuất secret value
jq -e 'any(.propertySources[]?.source?; has("spring.datasource.password"))' \
  "$response_file" >/dev/null
```

Phép kiểm tra cuối chỉ xác nhận key có mặt. Nó không chứng minh secret có giá trị hợp lệ, còn hạn hay có thể đăng nhập được. Muốn kiểm tra khả năng kết nối, hãy dùng một health check hoặc smoke test có kiểm soát, không in credential và không ghi nó vào log.

Nếu cần kiểm tra application, profile và label, có thể so sánh các trường metadata không nhạy cảm:

```bash
jq -e '
  .name == "order-service" and
  (.profiles | index("production") != null) and
  .label == "config-release-2026.11.0"
' "$response_file" >/dev/null
```

Đoạn lệnh chỉ trả exit code. Pipeline có thể báo request metadata đúng hoặc sai mà không xuất nội dung property source.

## 5. Kiểm tra một giá trị không nhạy cảm theo allowlist

Đôi khi cần xác nhận giá trị cấu hình cụ thể, chẳng hạn feature flag hoặc timeout. Chỉ đọc các key được xác định trước là không nhạy cảm và được phép hiển thị.

Ví dụ:

```bash
jq -r '
  .propertySources[]?.source? |
  select(has("checkout.timeout")) |
  .["checkout.timeout"]
' "$response_file" | head -n 1
```

Chỉ dùng cách này khi `checkout.timeout` đã được phân loại là an toàn để hiển thị. Không áp dụng cách lấy value chung cho mọi key, không xuất cả object `source` và không dùng allowlist chứa mật khẩu, token, private key hoặc dữ liệu cá nhân.

Với kiểm tra tự động, tốt hơn là so sánh với giá trị mong đợi mà không in giá trị thực:

```bash
if jq -e 'any(.propertySources[]?.source?; .["checkout.timeout"] == "2s")' \
  "$response_file" >/dev/null; then
  echo "checkout.timeout matches expected value"
else
  echo "checkout.timeout differs from expected value" >&2
  exit 1
fi
```

Nếu giá trị có thể được biểu diễn bằng nhiều kiểu JSON, chẳng hạn boolean hoặc number, hãy kiểm tra đúng kiểu dữ liệu mà Config Server thực tế trả về. Không ép tất cả thành chuỗi nếu điều đó che giấu lỗi schema.

## 6. Hiểu response và mã trạng thái HTTP

| Trạng thái | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `200` | Config Server xử lý request thành công | Kiểm tra metadata và property source cần thiết |
| `400` | Request không hợp lệ hoặc tham số không được chấp nhận | Kiểm tra URL, application, profile, label và định dạng |
| `401` | Chưa xác thực hoặc credential không hợp lệ | Kiểm tra danh tính và cơ chế authentication |
| `403` | Đã xác thực nhưng không có quyền | Kiểm tra authorization, ACL hoặc policy |
| `404` | Không tìm thấy tài nguyên/cấu hình theo request | Kiểm tra tên ứng dụng, profile, label và backend path |
| `5xx` | Lỗi phía Config Server hoặc backend phụ thuộc | Kiểm tra server log đã được bảo vệ, Git/secret backend và health |
| Timeout/connection error | Không kết nối được hoặc server phản hồi quá chậm | Kiểm tra DNS, network, TLS, timeout và tính sẵn sàng |

Không nên kết luận `200` đồng nghĩa ứng dụng đã sử dụng đúng cấu hình. `200` chỉ cho biết API đã trả response thành công. Cần kiểm tra metadata, property source và sau đó kiểm chứng client nếu đang điều tra giá trị cuối cùng tại runtime.

Endpoint health như `/actuator/health` có thể cho biết trạng thái của Config Server, nhưng không xác nhận request cho một application/profile/label cụ thể sẽ trả đúng cấu hình. Hãy kiểm tra cả health và endpoint cấu hình khi điều tra sự cố.

## 7. Phân biệt cấu hình Config Server trả về và giá trị cuối ở Client

Response từ Config Server cho biết các property source server cung cấp. Khi khởi động, Config Client còn có thể nhận các nguồn cấu hình khác như file local, biến môi trường, system properties và tham số dòng lệnh. Thứ tự ưu tiên cuối cùng phụ thuộc vào cơ chế Config Data và các tùy chọn override đang dùng.

Vì vậy, khi Config Server trả `checkout.timeout=2s` nhưng ứng dụng hoạt động như thể timeout là `5s`, hãy kiểm tra Environment cuối ở client. Có thể một biến môi trường hoặc tham số khởi chạy đang có độ ưu tiên cao hơn remote source. Đừng giải quyết bằng cách in toàn bộ `/actuator/env`; hãy truy vấn có giới hạn, bảo vệ endpoint và chỉ kiểm tra metadata hoặc key không nhạy cảm cần thiết.

Các endpoint Actuator `env` và `configprops` có thể tiết lộ cấu hình nhạy cảm. Trong production, cần giới hạn exposure, authentication và authorization, cấu hình masking phù hợp, đồng thời tránh ghi response của chúng vào log hoặc hệ thống quan sát công khai.

## 8. Những lệnh và thói quen cần tránh

| Thói quen | Rủi ro | Cách thay thế |
|---|---|---|
| `curl -v` hoặc `--trace` | Có thể ghi header, thông tin xác thực và dữ liệu trao đổi vào log | Chỉ in status/content type bằng `--write-out` |
| `curl -i` | In response headers cùng body ra terminal | Dùng `--output` cho body và chỉ xuất metadata cần thiết |
| `curl ... | tee response.json` | Sao chép response nhạy cảm vào terminal và file log | Ghi body vào file tạm có quyền hạn chế |
| `jq . response.json` | In toàn bộ property values | Dùng `jq -e` để kiểm tra boolean hoặc metadata allowlist |
| `curl -u user:password` | Lộ credential trong history hoặc process arguments | Prompt tương tác hoặc dùng credential file được bảo vệ |
| Đặt token trong URL/query string | URL có thể xuất hiện trong proxy log, history và telemetry | Dùng Authorization header qua cơ chế credential an toàn |
| `curl -k` | Bỏ xác minh danh tính server | Dùng CA tin cậy qua `--cacert` |
| Bật `set -x` trong script | Lệnh sau khi mở rộng biến có thể bị ghi vào log | Tắt shell tracing khi xử lý credential và response nhạy cảm |
| Upload response làm CI artifact | Người có quyền tải artifact có thể đọc secrets | Chỉ giữ file tạm trong job và xóa sau kiểm tra |

Không đưa token, password hoặc nội dung response vào tên file, commit message, issue, chat hay ảnh chụp màn hình. Khi cần báo lỗi, chỉ ghi endpoint đã loại bỏ thông tin nhạy cảm, application/profile/label, HTTP status và request correlation ID nếu có.

## 9. Ví dụ script kiểm tra an toàn hoàn chỉnh

Ví dụ Bash sau kiểm tra response JSON của một ứng dụng. Script chỉ in status và kết quả boolean; response body được giữ trong file tạm có quyền hạn chế và được xóa khi kết thúc.

```bash
#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077

application="order-service"
profile="production"
label="config-release-2026.11.0"
base_url="https://config.example.internal"
response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT

url="${base_url}/${application}/${profile}/${label}"

if http_status="$(curl \
  --silent \
  --show-error \
  --fail \
  --connect-timeout 5 \
  --max-time 15 \
  --netrc-file "$CURL_NETRC" \
  --header 'Accept: application/json' \
  --output "$response_file" \
  --write-out '%{http_code}' \
  "$url")"; then
  printf 'HTTP %s\n' "$http_status"
else
  printf 'Config API request failed (HTTP %s)\n' "$http_status" >&2
  exit 1
fi

jq -e '
  (.propertySources | type == "array") and
  (.propertySources | length > 0) and
  (.name == "order-service") and
  (.profiles | index("production") != null) and
  (.label == "config-release-2026.11.0") and
  any(.propertySources[]?.source?; has("checkout.timeout"))
' "$response_file" >/dev/null

printf 'Config metadata and required property checks passed\n'
```

Trong CI, `CURL_NETRC` phải trỏ tới netrc file được cấp từ secret store và chỉ job đó đọc được. Nếu dùng Bearer token, cấp header qua curl config file được bảo vệ hoặc cơ chế credential an toàn của runner. Không ghi token trực tiếp vào script hoặc biến lệnh được in ra log.

Script chỉ chứng minh API trả JSON có property source, đúng metadata và có key `checkout.timeout`. Nó không kiểm tra giá trị timeout có hợp lệ về nghiệp vụ hay client đã áp dụng nó. Các kiểm tra đó cần bước riêng và chỉ được phép hiển thị giá trị thuộc allowlist.

## 10. Checklist trước khi chia sẻ kết quả kiểm tra

Trước khi gửi log hoặc báo cáo cho nhóm khác, xác nhận:

- [ ] URL không chứa password, token hoặc query secret.
- [ ] Đã dùng HTTPS và xác minh certificate.
- [ ] Credential được lấy từ nguồn bảo vệ, không viết trực tiếp vào lệnh.
- [ ] Không bật verbose/trace hoặc shell tracing khi xử lý dữ liệu nhạy cảm.
- [ ] Response body không được in vào terminal, CI log hoặc chat.
- [ ] File response tạm có quyền truy cập hạn chế và được dọn sau kiểm tra.
- [ ] Chỉ kiểm tra metadata, sự hiện diện key hoặc giá trị trong allowlist.
- [ ] Đã phân biệt response Config Server với Environment cuối của Client.
- [ ] Endpoint Actuator và log được bảo vệ nếu cần kiểm tra phía client.

## 11. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Xác định đúng endpoint Config Server theo application, profile và label.
- Gọi API bằng `curl` với xác thực và TLS phù hợp.
- Chỉ xuất mã trạng thái và metadata HTTP trong khi giữ response body ở vùng tạm được bảo vệ.
- Dùng `jq` kiểm tra cấu trúc, metadata và sự hiện diện của key mà không in secret value.
- Phân biệt lỗi HTTP, lỗi xác thực, lỗi phân quyền, lỗi backend và timeout.
- Giải thích vì sao response của Config Server có thể khác Environment cuối ở Config Client.
- Nhận diện các lệnh nguy hiểm như `-v`, `-i`, `tee`, `jq .`, `-k` và `set -x` khi xử lý cấu hình nhạy cảm.

**Tự kiểm tra:** Config Server trả `200` cho `order-service/production/config-release-2026.11.0`, nhưng nhóm cần xác nhận `spring.datasource.password` có mặt mà không để lộ giá trị. Hãy đề xuất cách lưu response, câu lệnh kiểm tra sự hiện diện key, thông tin nào có thể ghi vào CI log và những bước cần kiểm tra thêm nếu ứng dụng vẫn kết nối database thất bại.
