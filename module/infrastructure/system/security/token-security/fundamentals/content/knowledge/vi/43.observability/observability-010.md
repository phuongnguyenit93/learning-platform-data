# Alert signature failure tăng

> **Chương:** Observability  
> **Phạm vi:** Quan sát và cảnh báo quá trình xác minh chữ ký access token trong hệ thống xác thực, phân quyền và OAuth 2.0/OIDC.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định chính xác sự kiện nào được tính là lỗi xác minh chữ ký JWT và phân biệt nó với các lỗi token khác.
2. Thiết kế metric, log và dashboard để phát hiện tỷ lệ signature failure tăng bất thường.
3. Viết cảnh báo Prometheus theo cả tỷ lệ lỗi và số lỗi tuyệt đối, có điều kiện chống nhiễu.
4. Phân tích nguyên nhân từ tấn công giả mạo token, cấu hình issuer/JWKS, xoay vòng khóa và lỗi tích hợp.
5. Xây dựng quy trình phản ứng sự cố mà vẫn giữ nguyên các kiểm tra mật mã và không làm lộ token hoặc dữ liệu nhạy cảm.

## 1. Alert signature failure tăng đang cảnh báo điều gì?

JWT dạng JWS có phần header, payload và chữ ký. Resource server xác minh chữ ký bằng khóa công khai hoặc khóa xác minh đã được cấu hình tin cậy. Chữ ký hợp lệ giúp phát hiện payload/header bị sửa và xác nhận token được ký bởi bên nắm khóa tương ứng.

**Signature failure** là trường hợp bước xác minh chữ ký mật mã thất bại: chữ ký không hợp lệ với dữ liệu ký và khóa xác minh đang được dùng. Ví dụ:

- Kẻ tấn công sửa `sub`, `scope` hoặc `tenant_id` trong payload rồi gửi lại token cũ.
- Client gửi JWT tự tạo hoặc ký bằng private key không được tin cậy.
- Resource server đang dùng sai public key do cấu hình hoặc phân phối JWKS sai.
- Token được ký bằng khóa mới nhưng cache JWKS vẫn giữ bộ khóa cũ.
- Các thành phần trung gian làm thay đổi token hoặc hệ thống ký và hệ thống xác minh không thống nhất thuật toán/khóa.

Cảnh báo “signature failure tăng” cho biết số lượng hoặc tỷ lệ lần xác minh chữ ký thất bại đã vượt ngưỡng quan sát. Đây là **tín hiệu cần điều tra**, chưa đủ để kết luận đang có tấn công. Một đợt xoay vòng khóa, triển khai cấu hình sai hoặc client lỗi cũng có thể tạo ra cùng biểu hiện.

### Phân biệt với các lỗi xác thực khác

Không gộp mọi token bị từ chối vào metric signature failure. Mỗi bước có nguyên nhân khác nhau:

| Nhóm lỗi | Ví dụ | Có tính là signature failure? |
| --- | --- | --- |
| Chữ ký không hợp lệ | Payload/header bị sửa, chữ ký không khớp khóa | Có |
| Không tìm thấy khóa | `kid` không có trong JWKS đã tin cậy | Không tự động tính; ghi nhận unknown key |
| Không tải được JWKS | Timeout, DNS/TLS hoặc HTTP lỗi khi lấy khóa | Không; đây là lỗi phụ thuộc khóa |
| Issuer mismatch | `iss` không khớp issuer được cấu hình | Không; đây là lỗi claim validation |
| Audience mismatch | `aud` không dành cho API | Không |
| Token hết hạn/chưa hiệu lực | `exp` hoặc `nbf` không hợp lệ | Không |
| Token sai định dạng | Thiếu segment, JSON/JOSE không parse được | Không |
| Thiếu scope/quyền | Token hợp lệ nhưng không đủ quyền | Không; thường là authorization failure |

Ví dụ, token có `iss` đúng nhưng chữ ký không khớp public key tin cậy là signature failure. Token có chữ ký hợp lệ nhưng `iss` sai là issuer validation failure. Hai trường hợp cần metric và runbook riêng.

Nếu thư viện JWT ném ngoại lệ tổng quát, không phân loại mọi `JwtException` thành signature failure. Cần phân loại theo bước thất bại hoặc nguyên nhân cụ thể của decoder; nếu chưa xác định được, ghi `verification_error` để tránh làm sai số liệu.

### Dòng xử lý cần quan sát

~~~mermaid
flowchart TD
    A["Request có Bearer token"] --> B["Parse JOSE header"]
    B -->|Malformed| M["Token format failure"]
    B --> C["Tìm khóa trong tập JWKS tin cậy"]
    C -->|Không có kid| K["Unknown signing key"]
    C -->|JWKS lỗi| J["JWKS dependency failure"]
    C -->|Có khóa| D["Xác minh chữ ký"]
    D -->|Không khớp| S["Signature failure"]
    D -->|Hợp lệ| E["Kiểm tra iss, aud, exp, nbf"]
    E -->|Claim sai| V["Claim validation failure"]
    E -->|Hợp lệ| F["Kiểm tra scope và quyền"]
    F -->|Thiếu quyền| P["Authorization failure"]
    F -->|Được phép| G["Thực thi nghiệp vụ"]
~~~

Sơ đồ thể hiện các nhóm quan sát độc lập. Trình tự nội bộ chính xác có thể khác tùy thư viện và cấu hình; điều quan trọng là metric phản ánh đúng bước thực tế thất bại.

## 2. Thiết kế metric cho signature verification

Metric phải trả lời được bốn câu hỏi:

- Có bao nhiêu lần xác minh chữ ký?
- Bao nhiêu lần thành công và thất bại?
- Tỷ lệ lỗi đang tăng ở service hoặc issuer nào?
- Sự thay đổi có đi cùng lỗi JWKS, triển khai mới hay ảnh hưởng đến request hợp lệ không?

Một counter có thể được định nghĩa như sau:

~~~text
token_signature_verifications_total{
  service="orders-api",
  environment="production",
  issuer_id="corporate-idp",
  outcome="failure"
} 27
~~~

Các nhãn gợi ý:

| Nhãn | Mục đích | Quy tắc |
| --- | --- | --- |
| `service` | Resource server đang xác minh token | Dùng tên service chuẩn |
| `environment` | Môi trường chạy | Ví dụ production, staging |
| `issuer_id` | Mã issuer từ cấu hình đã phê duyệt | Dùng ID ổn định, không lấy URL tùy ý từ token |
| `outcome` | success hoặc failure | Tập giá trị nhỏ, cố định |
| `reason` | Nhóm nguyên nhân đã chuẩn hóa | Ví dụ invalid_signature; chỉ thêm nếu metric cần phân tích nguyên nhân |

Counter tăng một lần cho mỗi lần xác minh chữ ký thực sự. Không tăng counter này khi token lỗi định dạng, không tìm được khóa hoặc thất bại ở bước kiểm tra `iss`/`aud`. Có thể có counter riêng `token_verification_failures_total{stage,reason}` cho toàn bộ pipeline.

**Tránh cardinality không giới hạn.** Không dùng `sub`, `jti`, token, tenant ID tùy ý, địa chỉ IP, URL request đầy đủ hoặc giá trị `iss` do client gửi làm nhãn metric. Các giá trị đó có thể tạo hàng triệu time series, làm Prometheus tốn bộ nhớ và khiến truy vấn cảnh báo chậm. Nếu cần điều tra, đưa dữ liệu đã được lọc vào log có kiểm soát.

`kid` cũng nên được ghi trong log/debug event có sampling khi cần, thay vì mặc định làm nhãn metric. Trong một số hệ thống có tập key ID giới hạn và quản trị chặt, có thể cân nhắc metric riêng, nhưng phải theo dõi cardinality trước khi triển khai.

### Metric bổ trợ

| Metric | Ý nghĩa |
| --- | --- |
| `token_signature_verifications_total` | Số lần xác minh chữ ký, phân biệt thành công/thất bại |
| `token_verification_failures_total` | Lỗi xác thực theo stage và reason đã chuẩn hóa |
| `jwks_fetch_total` | Số lần tải JWKS thành công/thất bại |
| `jwks_fetch_duration_seconds` | Độ trễ lấy JWKS |
| `jwks_cache_entries` | Số khóa hiện có trong cache, nếu thư viện cung cấp |
| `http_server_requests_total` | Lưu lượng và status của API |
| `authentication_requests_total` | Tổng request đi qua xác thực, dùng đối chiếu với signature verification |

Metric cụ thể phụ thuộc khả năng instrument của thư viện. Đặt tên và semantics rõ ràng trong hợp đồng telemetry nội bộ để dashboard giữa các service so sánh được.

## 3. Tính tỷ lệ lỗi và đặt ngưỡng cảnh báo

Số lỗi tuyệt đối và tỷ lệ lỗi trả lời hai câu hỏi khác nhau:

- **Số lỗi tuyệt đối** phát hiện burst đáng kể, kể cả khi lưu lượng cao khiến tỷ lệ nhỏ.
- **Tỷ lệ lỗi** phát hiện chất lượng xác minh xấu đi so với tổng số lần xác minh, kể cả khi traffic biến động.

Công thức cơ bản:

~~~text
failure ratio = signature verification failures / all signature verification attempts
~~~

Tỷ lệ phải dùng cùng một tập counter, cùng nhóm service/environment/issuer và cùng khoảng thời gian. Không chia cho tổng HTTP request nếu nhiều endpoint không dùng bearer token; mẫu số đó làm tỷ lệ sai lệch.

### Ví dụ PromQL

Giả sử counter `token_signature_verifications_total` tăng cho cả hai outcome success và failure:

~~~promql
sum by (service, environment, issuer_id) (
  rate(token_signature_verifications_total{outcome="failure"}[5m])
)
/
clamp_min(
  sum by (service, environment, issuer_id) (
    rate(token_signature_verifications_total[5m])
  ),
  1e-9
)
~~~

Truy vấn trên cho tỷ lệ signature failure theo service, môi trường và issuer trong cửa sổ 5 phút. `clamp_min` tránh phép chia cho 0; nó không thay thế điều kiện lưu lượng tối thiểu.

Để kiểm tra số lượng lỗi trong cùng cửa sổ:

~~~promql
sum by (service, environment, issuer_id) (
  increase(token_signature_verifications_total{outcome="failure"}[5m])
)
~~~

Có thể dùng hai điều kiện để tránh cảnh báo do một vài token sai lẻ tẻ khi lưu lượng rất thấp.

### Ví dụ Prometheus alert rules

Ngưỡng dưới đây chỉ là **giá trị minh họa để bắt đầu hiệu chỉnh**. Mỗi hệ thống cần đo baseline, lưu lượng, mức độ nhạy cảm và tác động người dùng trước khi áp dụng production.

~~~yaml
groups:
  - name: token-signature-alerts
    rules:
      - alert: JwtSignatureFailureRatioHigh
        expr: |
          (
            sum by (service, environment, issuer_id) (
              rate(token_signature_verifications_total{outcome="failure"}[5m])
            )
            /
            clamp_min(
              sum by (service, environment, issuer_id) (
                rate(token_signature_verifications_total[5m])
              ),
              1e-9
            )
          ) > 0.02
          and on (service, environment, issuer_id)
          sum by (service, environment, issuer_id) (
            increase(token_signature_verifications_total[5m])
          ) > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "JWT signature failure ratio tăng"
          description: "Tỷ lệ signature verification failure vượt 2% trong ít nhất 5 phút."

      - alert: JwtSignatureFailureBurst
        expr: |
          sum by (service, environment, issuer_id) (
            increase(token_signature_verifications_total{outcome="failure"}[5m])
          ) >= 20
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "JWT signature failure xuất hiện thành burst"
          description: "Có ít nhất 20 lần xác minh chữ ký thất bại trong cửa sổ 5 phút."
~~~

Rule đầu cảnh báo khi tỷ lệ vượt 2% và có hơn 100 lần xác minh trong 5 phút. Rule thứ hai bắt burst tối thiểu 20 lỗi trong 5 phút. Đây là hai tín hiệu bổ sung; không nên xem các con số này là chuẩn áp dụng cho mọi hệ thống.

Khi hiệu chỉnh:

1. Thu thập baseline theo giờ cao điểm/thấp điểm, service và issuer trong một khoảng thời gian đủ đại diện.
2. Chọn ngưỡng dựa trên tỷ lệ lỗi bình thường, mức chịu lỗi và tác động của một lần xác thực thất bại.
3. Dùng `for` để loại bỏ spike rất ngắn, nhưng không đặt thời gian dài đến mức bỏ lỡ tấn công hoặc sự cố đang lan rộng.
4. Đặt severity khác nhau cho cảnh báo sớm và cảnh báo ảnh hưởng đăng nhập/API diện rộng.
5. Kiểm tra rule với dữ liệu mô phỏng: traffic thấp, traffic cao, burst ngắn, lỗi kéo dài và counter reset sau restart.

Với service ít traffic, điều kiện “hơn 100 lần xác minh” có thể khiến cảnh báo tỷ lệ không bao giờ kích hoạt. Khi đó dùng ngưỡng số lỗi tuyệt đối hoặc đánh giá theo cửa sổ dài hơn. Với service traffic lớn, tỷ lệ nhỏ nhưng số lỗi tuyệt đối rất cao vẫn có thể gây tác động lớn.

### Baseline động và cảnh báo theo thay đổi

Ngưỡng cố định dễ vận hành nhưng có thể không phù hợp với chu kỳ traffic. Hệ thống lớn có thể bổ sung so sánh với baseline cùng khung giờ trong các ngày trước hoặc mô hình phát hiện bất thường. Dù dùng cách nào, cần giữ một ngưỡng tối thiểu để tránh cảnh báo do nhiễu thống kê ở traffic thấp.

Không tạo alert riêng cho từng `sub`, tenant hoặc client ID tùy ý. Hãy nhóm theo service, environment và issuer ID đã cấu hình. Nếu một issuer duy nhất bị lỗi trên mọi resource server, alert có thể được tương quan ở dashboard hoặc hệ thống incident management.

## 4. Log sự kiện xác minh có cấu trúc

Metric cho biết xu hướng; log giúp điều tra một lần thất bại cụ thể. Một sự kiện nên có các trường tối thiểu:

~~~json
{
  "timestamp": "2026-11-23T10:15:30Z",
  "level": "WARN",
  "event": "token_signature_verification_failed",
  "service": "orders-api",
  "environment": "production",
  "issuer_id": "corporate-idp",
  "failure_class": "invalid_signature",
  "key_id_present": true,
  "request_id": "req-7f31",
  "route": "/api/orders/{orderId}",
  "http_status": 401
}
~~~

Đây là log minh họa; các trường thực tế phải theo schema log của hệ thống. Có thể thêm phiên bản ứng dụng, vùng triển khai, cache state hoặc trạng thái JWKS fetch nếu cần để xác định phạm vi ảnh hưởng.

**Không ghi**:

- Header `Authorization` hoặc chuỗi Bearer token.
- JWT đầy đủ, refresh token, cookie phiên hoặc secret.
- Toàn bộ payload/claims nếu có dữ liệu cá nhân, tenant hoặc thông tin nội bộ.
- Private key, nội dung JWK bí mật hoặc thông tin xác thực tới JWKS endpoint.

Nếu cần liên kết log, dùng request ID/trace ID ngẫu nhiên do hệ thống tạo. Không dùng token `jti` hoặc `sub` làm correlation ID mặc định. Địa chỉ IP có thể cần cho điều tra bảo mật, nhưng phải được xử lý theo chính sách dữ liệu, quyền truy cập, thời hạn lưu và quy định áp dụng.

Đối với burst lớn, log mỗi lần thất bại có thể gây quá tải và làm tăng chi phí. Có thể áp dụng sampling có kiểm soát hoặc ghi đầy đủ trong một khoảng thời gian ngắn khi incident được xác nhận; counter vẫn phải đếm đầy đủ để alert không phụ thuộc sampling. Không sampling mất các sự kiện quan trọng như thay đổi khóa hoặc cấu hình issuer.

## 5. Dashboard giúp xác định phạm vi

Một dashboard hữu ích cần hiển thị xu hướng và đối chiếu với các thành phần phụ thuộc:

| Panel | Câu hỏi cần trả lời |
| --- | --- |
| Signature attempts | Lưu lượng xác minh có tăng/giảm bất thường không? |
| Signature failure count | Số lỗi tuyệt đối đang là bao nhiêu? |
| Signature failure ratio | Tỷ lệ lỗi thay đổi khi traffic tăng thế nào? |
| Failure class breakdown | Lỗi thật sự là invalid signature, unknown key hay JWKS unavailable? |
| Per service / issuer | Chỉ một service/issuer bị ảnh hưởng hay toàn hệ thống? |
| JWKS fetch errors/latency | Resource server có lấy được khóa mới không? |
| 401/403 rate | Lỗi xác minh có làm tăng request bị từ chối không? |
| Login/API success rate | Người dùng hợp lệ có bị ảnh hưởng không? |
| Deployment / key rotation markers | Lỗi có trùng thời điểm triển khai hoặc xoay vòng khóa không? |

Dùng cùng trục thời gian cho alert, deploy, thay đổi cấu hình và sự kiện key rotation. Điều này giúp phân biệt một đợt traffic độc hại với lỗi phát sinh sau khi đổi JWKS URI hoặc public key.

Dashboard không nên hiển thị token thô. Các bộ lọc nên giới hạn ở environment, service, issuer ID và failure class đã chuẩn hóa.

## 6. Phân tích nguyên nhân khi alert kích hoạt

Bắt đầu từ phạm vi, thời điểm và nhóm lỗi. Không giả định mọi signature failure đều là tấn công.

### 6.1. Kiểm tra phạm vi ảnh hưởng

- Xác định alert thuộc service, environment và issuer ID nào.
- So sánh số lần xác minh, failure ratio, 401 rate và tỷ lệ request thành công.
- Kiểm tra lỗi có xuất hiện đồng thời trên nhiều instance, zone hoặc service dùng chung issuer không.
- Đối chiếu thời điểm bắt đầu với deployment, cấu hình, thay đổi network, cache/JWKS và lịch xoay vòng khóa.
- Kiểm tra log theo request ID và failure class; không lấy token từ log để thử giải mã thủ công.

Nếu chỉ một instance lỗi sau khi rollout, khả năng cấu hình hoặc cache cục bộ cần được kiểm tra. Nếu nhiều service cùng issuer đồng loạt lỗi, xem xét thay đổi khóa, JWKS endpoint hoặc issuer provider.

### 6.2. Kiểm tra JWKS và xoay vòng khóa

Một tình huống phổ biến:

1. Authorization server bắt đầu ký bằng khóa mới.
2. Resource server vẫn giữ JWKS cũ trong cache hoặc không tải được JWKS mới.
3. Token mới có chữ ký hợp lệ với khóa mới nhưng resource server chưa có public key tương ứng.
4. Nếu thư viện phân loại thành unknown key thì số unknown-key tăng; nếu đã chọn nhầm khóa và verify thất bại thì invalid-signature có thể tăng.

Kiểm tra:

- JWKS endpoint có sẵn sàng, TLS hợp lệ và trả về bộ khóa đúng không?
- Khóa mới đã được công bố trước khi bắt đầu ký chưa?
- Cache TTL, refresh-on-unknown-kid và cơ chế retry có phù hợp không?
- Các instance có nhận cùng cấu hình và cùng tập khóa không?
- Khóa cũ có được giữ trong khoảng overlap đủ dài cho token còn hiệu lực không?

Không xóa toàn bộ cache hoặc ép refresh liên tục trên mỗi token lạ. Điều đó có thể tạo request storm tới issuer. Cần cơ chế refresh có giới hạn, cache hợp lý và backoff.

### 6.3. Kiểm tra thay đổi cấu hình và thư viện

Các thay đổi có thể làm signature failure tăng:

- Resource server trỏ nhầm JWKS URI hoặc dùng public key của môi trường khác.
- Issuer A và issuer B bị gán nhầm bộ khóa.
- Thuật toán ký/xác minh không thống nhất hoặc cấu hình thuật toán cho phép bị thay đổi.
- Token bị proxy, gateway hoặc middleware thay đổi trước khi tới decoder.
- Nâng cấp thư viện làm thay đổi cách chọn key, parse JOSE header hoặc xử lý JWK.

Kiểm tra cấu hình đã triển khai và phiên bản artifact; so sánh một instance tốt với instance lỗi. Không nới lỏng kiểm tra chữ ký để khắc phục nhanh.

### 6.4. Dấu hiệu có thể liên quan đến tấn công

Các dấu hiệu cần điều tra sâu hơn:

- Số token có chữ ký sai tăng đột ngột, không trùng lịch deploy/key rotation.
- Nhiều client hoặc nguồn mạng gửi token có cấu trúc tương tự nhưng chữ ký sai.
- Có nỗ lực sửa claim như scope, role hoặc tenant trong payload.
- Tần suất thử token sai tăng theo endpoint nhạy cảm hoặc một API cụ thể.
- Lỗi xuất hiện cùng các hành vi dò quét, credential stuffing hoặc lạm dụng endpoint khác.

Signature failure tự nó không xác định danh tính attacker. Tương quan với rate limit, WAF, audit log và telemetry mạng theo quyền truy cập được kiểm soát. Không kết luận một người dùng cụ thể là attacker chỉ dựa trên một token lỗi.

### 6.5. Không nhầm lỗi đồng hồ với lỗi chữ ký

Clock skew thường làm token bị từ chối do `exp`, `nbf` hoặc chính sách thời gian; nó không trực tiếp làm chữ ký mật mã sai nếu bytes và khóa không đổi. Nếu alert signature failure tăng, không chỉnh clock skew như biện pháp đầu tiên. Hãy kiểm tra đúng failure class và timestamp validation metric riêng.

## 7. Quy trình phản ứng sự cố

Một runbook ngắn giúp đội vận hành phản ứng nhất quán:

1. **Xác nhận alert:** kiểm tra metric thô, cửa sổ thời gian, số lỗi, tỷ lệ và điều kiện traffic tối thiểu.
2. **Đánh giá tác động:** xác định request hợp lệ có bị từ chối không, phạm vi service/issuer, ảnh hưởng login và API quan trọng.
3. **Phân loại nguyên nhân:** invalid signature, unknown key, JWKS unavailable, cấu hình sai hay hành vi đáng ngờ.
4. **Đối chiếu thay đổi:** kiểm tra deploy, key rotation, JWKS, issuer config, gateway và phiên bản thư viện.
5. **Giảm thiểu có kiểm soát:** khôi phục cấu hình/khóa đã xác minh hoặc khắc phục JWKS/cache; áp dụng rate limit cho nguồn lạm dụng khi có căn cứ.
6. **Xác minh phục hồi:** theo dõi failure ratio, success rate, 401, JWKS fetch và request hợp lệ qua ít nhất một chu kỳ traffic đại diện.
7. **Ghi nhận hậu kiểm:** nguyên nhân gốc, thời gian ảnh hưởng, cách phát hiện, hành động khắc phục và cải tiến alert/runbook.

### Các hành động không được dùng để “chữa cháy”

- Bỏ qua xác minh chữ ký hoặc chấp nhận token không chữ ký.
- Chấp nhận mọi issuer hoặc tải JWKS từ URL do token tùy ý cung cấp.
- Chuyển sang thuật toán yếu hơn chỉ để token qua được decoder.
- Tắt xác thực toàn bộ API mà không có phương án kiểm soát được phê duyệt.
- Ghi token đầy đủ vào log hoặc gửi token qua chat/ticket để debug.

Nếu nghi ngờ private signing key bị lộ, xử lý như sự cố khóa: phối hợp với chủ sở hữu authorization server để dừng ký bằng khóa bị ảnh hưởng, công bố khóa thay thế, loại bỏ khóa bị xâm phạm khỏi tập tin cậy theo kế hoạch, đánh giá token/session đã phát hành và áp dụng thu hồi phù hợp. Chỉ xóa khóa sau khi xác định ảnh hưởng tới token hợp lệ và hoàn tất phương án chuyển đổi; thay đổi vội vàng có thể làm toàn bộ người dùng bị đăng xuất.

## 8. Ví dụ tình huống: lỗi tăng sau key rotation

**Bối cảnh:** Orders API bình thường có failure ratio dưới 0,1%. Sau 10:00, metric invalid-signature tăng lên 8%, đồng thời 401 tăng. Lỗi xuất hiện trên mọi instance của production và chỉ với issuer corporate-idp.

**Điều tra:**

- Dashboard cho thấy unknown-key cũng tăng ngay trước invalid-signature.
- JWKS endpoint vẫn truy cập được, nhưng cache ở một số instance chưa refresh.
- Authorization server bắt đầu ký bằng key ID mới sớm hơn thời điểm dự kiến.
- Một số instance chưa nhận được bản cấu hình JWKS mới hoặc refresh bị giới hạn bởi cache policy.

**Khắc phục:**

1. Xác nhận public key mới qua kênh cấu hình tin cậy.
2. Công bố/đồng bộ JWKS và kiểm tra mọi instance có thể tải khóa mới.
3. Áp dụng refresh có giới hạn, tránh xóa cache đồng loạt gây tải đột biến.
4. Duy trì khóa cũ trong thời gian overlap phù hợp với TTL access token và chính sách issuer.
5. Xác nhận token mới và token còn hiệu lực ký bằng khóa cũ đều được xử lý theo kế hoạch.
6. Theo dõi signature failure, unknown-key, JWKS fetch và tỷ lệ request hợp lệ trở về baseline.

**Bài học:** lịch key rotation phải phối hợp giữa issuer và resource server; publish key mới trước khi dùng để ký, có overlap, quan sát cache và có kiểm thử rollout.

## 9. Kiểm thử metric và alert

Không chỉ kiểm tra biểu thức PromQL bằng mắt. Hãy tạo dữ liệu mô phỏng hoặc test instrumentation để xác nhận metric và alert phản ánh đúng semantics.

| Ca kiểm thử | Tác động mô phỏng | Kết quả mong đợi |
| --- | --- | --- |
| OBS-SIG-01 | Token hợp lệ, chữ ký hợp lệ | Counter success tăng |
| OBS-SIG-02 | Token bị sửa payload sau khi ký | Counter invalid signature tăng |
| OBS-SIG-03 | Issuer claim sai nhưng chữ ký hợp lệ | Claim validation tăng, signature failure không tăng |
| OBS-SIG-04 | Không tìm thấy `kid` trong JWKS | Unknown-key tăng riêng |
| OBS-SIG-05 | JWKS endpoint timeout | JWKS dependency failure tăng |
| OBS-SIG-06 | Token hết hạn | Timestamp validation failure tăng |
| OBS-SIG-07 | Burst signature failure vượt ngưỡng | Alert burst firing |
| OBS-SIG-08 | Failure ratio vượt ngưỡng và đủ traffic | Alert ratio firing |
| OBS-SIG-09 | Vài lỗi rời rạc khi traffic rất thấp | Alert ratio không firing do thiếu traffic |
| OBS-SIG-10 | Counter reset sau restart | Rate/increase xử lý reset đúng |
| OBS-SIG-11 | Log sampling bật | Counter vẫn đếm đầy đủ; log không chứa token |
| OBS-SIG-12 | Thêm giá trị issuer/subject ngẫu nhiên | Không tạo metric label cardinality không giới hạn |

Kiểm tra cả tình huống alert được resolve sau khi tỷ lệ lỗi trở về bình thường. Xác minh thông báo alert chứa service, environment, issuer ID, failure ratio, số lỗi, link dashboard và runbook; không đính kèm token hoặc claim nhạy cảm.

## 10. Bài tập thực hành

**Tình huống:** Trong 5 phút, Orders API ghi nhận 300 lần xác minh chữ ký; 45 lần thất bại. Trong cùng thời điểm, 10 lần token có `iss` sai và 8 lần token hết hạn. JWKS endpoint vẫn hoạt động.

1. Tính signature failure ratio nếu 45 lần là các lần verify chữ ký thất bại.
2. Vì sao 10 issuer mismatch và 8 expired token không được cộng vào tử số signature failure?
3. Đề xuất hai metric bổ sung để phân biệt lỗi khóa với lỗi claim validation.
4. Nếu lỗi bắt đầu ngay sau key rotation, bạn kiểm tra những dữ kiện nào trước?
5. Nêu ba trường log an toàn để hỗ trợ điều tra và ba dữ liệu không được ghi.

**Gợi ý đáp án:**

1. 45 / 300 = 15%.
2. Chúng thất bại ở bước kiểm tra claim/thời gian sau khi chữ ký đã được xác minh; gộp chúng sẽ làm sai semantics của alert.
3. Theo dõi unknown-key/JWKS fetch failure và issuer/timestamp validation failure riêng.
4. Kiểm tra thời điểm publish JWKS, key ID mới, cache/refresh trên từng instance, overlap giữa khóa cũ và mới, và thời điểm issuer bắt đầu ký bằng khóa mới.
5. Log có thể ghi service, issuer ID cấu hình, failure class, request ID; không ghi Authorization header, JWT/refresh token hoặc secret/private key.

## Ghi nhớ

- Signature failure là lỗi xác minh chữ ký mật mã; tách biệt với issuer, audience, thời hạn, định dạng, unknown key và thiếu quyền.
- Theo dõi cả số lỗi tuyệt đối lẫn tỷ lệ lỗi, luôn dùng mẫu số là số lần xác minh chữ ký trong cùng phạm vi.
- Dùng nhãn metric có cardinality thấp; không đưa token, subject, tenant tùy ý hoặc claim do client kiểm soát vào label.
- Kết hợp metric, log có cấu trúc, dashboard, deploy marker và telemetry JWKS để tìm nguyên nhân.
- Xoay vòng khóa cần có overlap và đồng bộ JWKS/cache; không nới lỏng xác minh chữ ký để xử lý alert.
- Runbook phải xác nhận tác động, phân loại lỗi, khắc phục có kiểm soát và kiểm chứng phục hồi.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [Prometheus — Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
