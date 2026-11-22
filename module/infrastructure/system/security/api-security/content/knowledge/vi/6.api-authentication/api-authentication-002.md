# API key cho client identification và quota

API key là một credential thường dùng để nhận diện ứng dụng hoặc hệ thống gọi API. Nó giúp nhà cung cấp biết request đến từ client nào, áp dụng quota, thống kê mức sử dụng và quản lý quyền truy cập theo từng tích hợp. Tuy nhiên, API key không tự chứng minh người dùng cuối là ai và cũng không thay thế toàn bộ cơ chế phân quyền của API.

Thiết kế an toàn cần trả lời được bốn câu hỏi: key đại diện cho client nào, client được phép làm gì, client còn bao nhiêu hạn mức và làm thế nào để thu hồi key khi không còn tin cậy. Nếu chỉ tạo một chuỗi bí mật rồi kiểm tra chuỗi đó ở gateway, hệ thống có thể gặp rủi ro rò rỉ credential, chia sẻ key giữa nhiều ứng dụng, vượt quota hoặc cấp quyền rộng hơn nhu cầu.

## 1. API key giải quyết bài toán nào?

API key là một giá trị do nhà cung cấp phát hành cho một ứng dụng, dịch vụ hoặc tích hợp. Client gửi key trong request để API nhận diện credential đã đăng ký và tra cứu metadata tương ứng.

Ví dụ:

```http
GET /v1/catalog/items HTTP/1.1
Host: api.example.com
X-API-Key: ak_live_k8f3m2q1.VERY_LONG_RANDOM_SECRET
Accept: application/json
```

Từ key đã xác minh, hệ thống có thể xác định client, project, môi trường, tenant được gắn với tích hợp, scope được cấp và chính sách quota. Key cũng có thể hỗ trợ đo lường mức sử dụng hoặc tính phí theo hợp đồng.

API key thường phù hợp với các trường hợp:

- Nhận diện một ứng dụng gọi API công khai hoặc API dành cho đối tác.
- Theo dõi mức sử dụng theo client hoặc project.
- Áp dụng quota, rate limit và chính sách truy cập cho từng tích hợp.
- Quản lý vòng đời credential riêng cho từng hệ thống gọi API.
- Cấp quyền có phạm vi hẹp cho một workload khi mô hình xác thực phù hợp.

API key không nên được xem là danh tính của người dùng cuối. Một ứng dụng có thể phục vụ hàng nghìn người dùng nhưng chỉ dùng một key ở backend. API key khi đó nhận diện ứng dụng, còn danh tính và quyền của từng người dùng cần được xác minh bằng cơ chế riêng như OAuth 2.0/OIDC access token hoặc session đã được bảo vệ.

## 2. Phân biệt client identification, authentication và authorization

Các khái niệm này liên quan nhưng trả lời những câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Client identification | Request đến từ tích hợp hoặc ứng dụng nào? | `client_id=partner-reporting` |
| Client authentication | Client có chứng minh được quyền sở hữu credential đã đăng ký không? | Key bí mật khớp với key record còn hiệu lực |
| User authentication | Người dùng cuối là ai? | Access token có `sub=user-123` |
| Authorization | Chủ thể được phép thực hiện hành động nào trên tài nguyên nào? | Client có scope `reports:read` và người dùng được xem báo cáo thuộc tenant của họ |
| Quota / rate limit | Client hoặc tenant còn được sử dụng bao nhiêu? | 100.000 request mỗi tháng và tối đa 20 request mỗi giây |

API key có thể là một phương thức xác thực client dựa trên việc chứng minh quyền sở hữu secret. Nhưng khi key chỉ được dùng để gắn nhãn request hoặc đo usage, không nên diễn giải nó như bằng chứng đầy đủ rằng người dùng được phép truy cập mọi dữ liệu mà API cung cấp.

Ví dụ, một đối tác có key hợp lệ vẫn chỉ nên đọc các endpoint được cấp scope. Nếu request truy cập đơn hàng của một người dùng, API còn phải kiểm tra quyền trên chính đơn hàng đó và tenant liên quan. Không được suy ra quyền sở hữu dữ liệu chỉ từ việc key hợp lệ.

## 3. Thiết kế key riêng cho từng client

### 3.1. Không dùng một key chung cho nhiều tích hợp

Mỗi client hoặc workload cần có credential riêng. Nếu nhiều ứng dụng dùng chung một key, hệ thống khó xác định nguồn request, khó đặt quota công bằng và không thể thu hồi riêng một tích hợp khi secret bị lộ.

Nên tách key theo:

- Client hoặc đối tác cụ thể.
- Project hoặc tenant theo mô hình cung cấp dịch vụ.
- Môi trường như development, staging và production.
- Mục đích sử dụng hoặc nhóm API có mức rủi ro khác nhau.

Ví dụ, `partner-a-reporting-prod` và `partner-a-billing-prod` nên có key riêng nếu chúng có chủ sở hữu, quyền hoặc hạn mức khác nhau. Key staging không được chấp nhận ở production và ngược lại.

### 3.2. Tách public identifier khỏi secret

Một định dạng key có thể chứa phần nhận diện công khai và phần bí mật:

```text
ak_live_<key-id>.<secret>
```

- `ak_live_` cho biết loại key và môi trường.
- `<key-id>` là mã ngẫu nhiên hoặc định danh không bí mật để tìm record trong kho dữ liệu.
- `<secret>` là phần bí mật chứng minh client đang sở hữu credential.

Public identifier giúp tra cứu nhanh mà không phải dò toàn bộ kho key. Nó không được dùng một mình để xác thực. Nếu chỉ có key ID mà không có secret tương ứng, request phải bị từ chối.

Secret cần được tạo bằng bộ sinh số ngẫu nhiên mật mã an toàn (CSPRNG), có entropy đủ lớn. Với credential do hệ thống tự phát hành, nên dùng ít nhất 128 bit entropy; 256 bit là lựa chọn phù hợp khi chi phí lưu trữ và truyền tải không đáng kể. Không tạo key từ tên ứng dụng, email, timestamp, số thứ tự hoặc chuỗi dễ đoán.

Ví dụ dưới đây chỉ minh họa cấu trúc, không phải credential dùng thật:

```text
ak_live_k8f3m2q1.7jQm...random-secret...xP9w
```

### 3.3. Lưu metadata và digest thay vì secret nguyên bản

Kho dữ liệu có thể lưu các trường như:

| Trường | Mục đích |
|---|---|
| `key_id` | Tra cứu key record; không phải secret |
| `client_id` | Client hoặc tích hợp sở hữu key |
| `tenant_id` / `project_id` | Phạm vi dữ liệu hoặc project được gắn với client |
| `secret_digest` | Digest của secret để xác minh key được gửi lên |
| `scopes` | Nhóm hành động hoặc API được cấp |
| `environment` | Môi trường key được phép sử dụng |
| `status` | Active, revoked, expired hoặc suspended |
| `created_at`, `expires_at`, `revoked_at` | Theo dõi vòng đời key |
| `last_used_at` | Hỗ trợ vận hành và phát hiện key không còn sử dụng |
| `quota_policy_id` | Chính sách quota được áp dụng |
| `owner` / `description` | Chủ sở hữu và mục đích tích hợp |

Secret chỉ nên hiển thị một lần khi tạo key. Sau đó, giao diện quản trị chỉ hiển thị key ID, prefix hoặc vài ký tự đầu/cuối để người vận hành nhận diện. Nếu người dùng làm mất secret, quy trình đúng là tạo key mới và xoay vòng, không thể khôi phục secret từ digest.

Vì key được tạo ngẫu nhiên với entropy cao, có thể lưu SHA-256 digest để tra cứu và so sánh. Một lựa chọn khác là HMAC-SHA-256 với pepper được lưu riêng trong secret manager hoặc KMS. Pepper cần được quản lý và xoay vòng có kế hoạch. Nếu cho phép người dùng tự đặt key có entropy thấp, phải xử lý nó như mật khẩu và dùng hàm dẫn xuất khóa chậm phù hợp; không áp dụng cách lưu đơn giản dành cho secret ngẫu nhiên.

## 4. Truyền API key an toàn

### 4.1. Dùng HTTPS và header

Chỉ gửi API key qua kết nối HTTPS đã xác minh chứng thư máy chủ. TLS bảo vệ credential trên đường truyền và giúp client xác nhận đang kết nối đến máy chủ dự kiến.

Ưu tiên gửi key trong header, ví dụ:

```http
X-API-Key: <api-key>
```

Hoặc dùng scheme riêng trong `Authorization` nếu hợp đồng API quy định rõ:

```http
Authorization: ApiKey <api-key>
```

Không đặt key trong query string:

```http
GET /v1/reports?api_key=<api-key>
```

URL có thể xuất hiện trong access log, lịch sử trình duyệt, proxy, hệ thống phân tích, cache hoặc header `Referer`. Việc dùng HTTPS không loại bỏ rủi ro URL bị ghi lại ở các thành phần đầu cuối.

Không gửi key trong body của request không liên quan đến việc cấp hoặc xoay vòng credential. Cũng không lưu key vào cookie hoặc local storage của trình duyệt như thể đó là một bí mật bền vững.

### 4.2. Không để secret xuất hiện trong log và telemetry

API gateway, reverse proxy, APM, tracing, error report và log ứng dụng có thể ghi header theo cấu hình mặc định. Cần cấu hình che hoặc loại bỏ `X-API-Key` và `Authorization` trước khi dữ liệu rời khỏi tiến trình xử lý request.

Không ghi secret vào:

- Access log, application log, distributed trace hoặc metric label.
- Exception message, debug dump hoặc log request/response đầy đủ.
- URL, screenshot, ticket hỗ trợ hoặc tài liệu hướng dẫn.
- Analytics event, công cụ replay phiên hoặc hệ thống giám sát bên thứ ba.

Khi cần điều tra, ghi `key_id`, `client_id`, endpoint, thời điểm và kết quả xác thực. Các mã định danh này đủ để truy vết mà không tiết lộ credential.

## 5. Xác minh API key trong request pipeline

Quy trình xác minh nên được thực hiện ở một lớp dùng chung như API gateway, authentication filter hoặc middleware để mọi endpoint cần key áp dụng nhất quán.

Một luồng cơ bản:

1. Đọc key từ header được quy định; từ chối nếu thiếu hoặc có nhiều giá trị không hợp lệ.
2. Phân tích prefix, key ID và secret theo đúng định dạng.
3. Tra cứu record bằng key ID.
4. Kiểm tra trạng thái, môi trường, thời hạn và phạm vi sử dụng.
5. Tính digest của secret nhận được và so sánh với digest đã lưu bằng phép so sánh an toàn về thời gian.
6. Tạo client principal từ metadata phía máy chủ.
7. Chuyển principal cho bước authorization và quota.

Ví dụ Java minh họa phần xác minh secret bằng HMAC:

```java
public ClientPrincipal authenticate(String presentedKey) {
    ParsedApiKey parsed = apiKeyParser.parse(presentedKey);
    if (parsed == null) {
        throw new InvalidApiKeyException();
    }

    ApiKeyRecord record = apiKeyRepository.findByKeyId(parsed.keyId())
            .orElseThrow(InvalidApiKeyException::new);

    if (!record.isActive()
            || record.isExpired(clock.instant())
            || !record.environment().equals(currentEnvironment)) {
        throw new InvalidApiKeyException();
    }

    byte[] candidate = hmacSha256(keyPepper, parsed.secret());
    if (!MessageDigest.isEqual(candidate, record.secretDigest())) {
        throw new InvalidApiKeyException();
    }

    return new ClientPrincipal(
            record.clientId(),
            record.tenantId(),
            record.scopes(),
            record.keyId());
}
```

Đây là ví dụ khung; `keyPepper` cần được lấy từ secret manager, `hmacSha256` phải dùng thuật toán và encoding nhất quán với lúc tạo key, còn parser phải giới hạn độ dài đầu vào. Không đưa secret hoặc giá trị key nhận được vào exception message.

Sau khi xác thực client, authorization vẫn phải được thực hiện riêng:

```java
authorizationService.requireScope(client, "reports:read");
authorizationService.requireCanReadReport(client, report);
quotaService.consume(client.quotaSubject(), "reports.read", 1);
```

`client` ở đây là principal được tạo từ record phía máy chủ. Không lấy `client_id`, `tenant_id`, scope hoặc quota từ header tùy ý do người gọi tự khai báo.

## 6. API key không thay thế phân quyền và danh tính người dùng

Một key hợp lệ chỉ cho biết request có credential thuộc về một client đã đăng ký. API vẫn cần kiểm tra:

- Client có được phép gọi endpoint và HTTP method này không?
- Scope hoặc quyền chức năng nào đã được cấp?
- Client được truy cập tenant, project hoặc nhóm dữ liệu nào?
- Người dùng cuối, nếu có, có quyền trên đối tượng cụ thể không?
- Trường dữ liệu trả về có phù hợp với quyền của chủ thể không?
- Hành động có hợp lệ theo trạng thái nghiệp vụ hiện tại không?

Ví dụ, key của đối tác báo cáo có thể được cấp `reports:read` nhưng không được gọi `payments:refund`. Ngay cả khi client có `orders:read`, API vẫn phải giới hạn truy vấn theo tenant và kiểm tra quyền trên từng đơn hàng nếu chính sách yêu cầu.

Không sử dụng một key dùng chung để đại diện cho mọi người dùng cuối rồi ghi nhận các thao tác như thể key cho biết ai đã thực hiện. Nếu nghiệp vụ cần phân quyền theo người dùng, hãy yêu cầu access token của người dùng hoặc một cơ chế ủy quyền tương đương. Có thể kết hợp API key để nhận diện ứng dụng và OAuth access token để nhận diện người dùng cùng quyền được ủy quyền.

Với workload nội bộ hoặc tích hợp có yêu cầu xác thực mạnh, cân nhắc mTLS hoặc workload identity. API key là một bearer secret: bất kỳ bên nào lấy được key đều có thể thử sử dụng nó trong phạm vi mà key được cấp. Key không tự ràng buộc request với một máy chủ cụ thể và cũng không cung cấp chữ ký cho nội dung request.

## 7. Thiết kế quota và rate limit theo client

### 7.1. Phân biệt quota với rate limit

Quota và rate limit thường được dùng cùng nhau nhưng kiểm soát hai khía cạnh khác nhau:

| Cơ chế | Mục tiêu | Ví dụ |
|---|---|---|
| Quota | Giới hạn tổng mức sử dụng trong một chu kỳ hoặc ngân sách | 100.000 request mỗi tháng |
| Rate limit | Giới hạn tốc độ request trong một khoảng thời gian ngắn | Tối đa 20 request mỗi giây |
| Concurrency limit | Giới hạn số tác vụ đang chạy đồng thời | Tối đa 5 tác vụ xuất báo cáo |
| Payload / resource limit | Giới hạn chi phí của một request hoặc lượng tài nguyên tạo ra | Tối đa 10 MB mỗi lần tải lên |

Một client có thể còn quota tháng nhưng vẫn vượt rate limit trong vài giây. Ngược lại, client có tốc độ thấp vẫn có thể tiêu thụ hết quota tháng nếu gọi liên tục.

### 7.2. Chọn đúng khóa quota

Có thể áp dụng giới hạn theo một hoặc nhiều chiều:

- `key_id`: giới hạn riêng cho từng credential.
- `client_id`: tổng mức sử dụng của một tích hợp, kể cả khi client có nhiều key.
- `tenant_id` hoặc `project_id`: giới hạn tổng cho một khách hàng hoặc project.
- Endpoint hoặc nhóm thao tác: phản ánh chi phí khác nhau giữa đọc danh mục và xuất dữ liệu lớn.
- Người dùng cuối: áp dụng khi request có danh tính người dùng đã được xác thực.

Nếu chỉ giới hạn theo key, client có thể tạo nhiều key rồi cộng dồn hạn mức. Nếu hợp đồng bán quota theo tenant hoặc project, cần có bộ đếm tổng hợp ở cấp đó. Có thể đồng thời giữ quota theo client và rate limit theo key để ngăn một credential bị lạm dụng.

Không nên dùng IP làm định danh duy nhất cho quota khách hàng. Nhiều client có thể dùng chung NAT hoặc proxy; một client cũng có thể thay đổi IP. IP có thể là tín hiệu bổ sung cho chống lạm dụng, không thay thế định danh client đã xác thực.

### 7.3. Cập nhật bộ đếm an toàn khi có request đồng thời

Trong môi trường nhiều API instance, bộ đếm trong bộ nhớ của từng máy không đủ để thực thi một quota chung. Các instance có thể chấp nhận nhiều request hơn giới hạn dự kiến hoặc mất bộ đếm sau khi khởi động lại.

Nên dùng kho đếm dùng chung hoặc một lớp quota chuyên trách. Thao tác kiểm tra và tiêu thụ hạn mức phải nguyên tử để nhiều request đồng thời không cùng nhìn thấy quota còn lại rồi đều được chấp nhận. Với Redis, có thể dùng Lua script hoặc cơ chế atomic phù hợp; với cơ sở dữ liệu quan hệ, có thể dùng transaction và cập nhật có điều kiện.

Chính sách cần xác định rõ:

- Cửa sổ tính quota và thời điểm reset.
- Request nào được tính: request thành công, mọi request đã xác thực hay từng loại thao tác.
- Trọng số của thao tác có chi phí khác nhau.
- Hành vi với request retry và idempotency key.
- Cách xử lý khi kho quota không truy cập được.
- Cách đồng bộ quota giữa các vùng hoặc cụm triển khai.

Nếu quota là một phần của hợp đồng tính phí, phải có cách đối soát và audit đủ tin cậy. Không chỉ dựa vào metric có thể bị mất hoặc sampling để tính số lượng giao dịch tính phí.

### 7.4. Phản hồi khi vượt giới hạn

Khi client vượt rate limit hoặc quota, API thường trả `429 Too Many Requests`. Nếu có thể, cung cấp thời điểm hoặc khoảng chờ để client biết khi nào nên thử lại:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/quota-exceeded",
  "title": "Request limit exceeded",
  "status": 429,
  "detail": "The client has reached the current request limit."
}
```

Không trả thông tin nội bộ như số key khác, quota của tenant khác hoặc cấu trúc kho đếm. Client nên tôn trọng `Retry-After`, dùng exponential backoff có jitter và tránh retry liên tục khi chưa đến thời điểm được phép.

## 8. Cấp phát, xoay vòng và thu hồi key

API key có vòng đời riêng và cần được quản lý như một credential thực sự.

### 8.1. Cấp phát

Khi tạo key, hệ thống nên:

1. Xác minh người yêu cầu có quyền quản lý client hoặc project.
2. Ghi nhận mục đích, owner, môi trường, scope và quota cần thiết.
3. Sinh key ID và secret bằng CSPRNG.
4. Lưu digest và metadata; không lưu secret nguyên bản.
5. Hiển thị secret một lần qua kênh quản trị được bảo vệ.
6. Ghi audit event về việc tạo key mà không ghi secret.

Không tự động cấp quyền quản trị hoặc quota không giới hạn cho key mới. Dùng quyền tối thiểu và hạn mức phù hợp với nhu cầu đã xác nhận.

### 8.2. Xoay vòng

Khi cần xoay vòng, cấp key mới trước, cập nhật secret ở client, xác minh request mới hoạt động rồi thu hồi key cũ. Trong khoảng chuyển đổi, có thể cho phép hai key cùng tồn tại trong thời gian ngắn nếu rủi ro chấp nhận được. Mỗi key vẫn cần được nhận diện riêng để quan sát việc chuyển đổi.

Không kéo dài vô hạn thời gian chấp nhận key cũ. Đặt thời hạn cụ thể, cảnh báo owner trước khi hết hạn và tự động vô hiệu hóa khi tới hạn nếu chính sách quy định.

### 8.3. Thu hồi

Khi key bị lộ, owner không còn hợp lệ hoặc tích hợp kết thúc, phải có khả năng thu hồi theo `key_id` mà không ảnh hưởng các client khác. Nếu hệ thống cache trạng thái key, cần xác định thời gian tối đa cache có thể giữ trạng thái active và cách vô hiệu hóa cache khi thu hồi.

Với sự cố rò rỉ, ưu tiên thu hồi ngay và điều tra request đã dùng key trong khoảng thời gian nghi ngờ. Không chỉ xóa key khỏi giao diện quản trị; phải cập nhật nguồn xác thực mà mọi API instance thực sự sử dụng.

## 9. Rủi ro khi đưa key vào ứng dụng công khai

Secret nhúng trong JavaScript chạy trên trình duyệt, ứng dụng mobile, extension hoặc mã nguồn phân phối cho người dùng có thể bị trích xuất. Obfuscation, mã hóa trong binary hoặc biến môi trường build không biến secret thành bí mật nếu client phải giải mã và sử dụng nó.

Vì vậy:

- Không nhúng API key có quyền truy cập dữ liệu nhạy cảm hoặc quota lớn vào frontend hay ứng dụng phân phối công khai.
- Đưa lời gọi cần secret qua backend do tổ chức kiểm soát; backend xác thực người dùng và áp dụng authorization trước khi gọi dịch vụ phía sau.
- Nếu nhà cung cấp buộc phải dùng public key ở trình duyệt, chỉ cấp quyền rất hẹp cho dữ liệu công khai, giới hạn theo origin khi phù hợp và đặt quota thấp. Origin restriction là lớp giảm lạm dụng, không phải bằng chứng bí mật tuyệt đối.
- Với ứng dụng mobile, không xem package signature hoặc obfuscation là cách bảo vệ secret lâu dài. Dùng cơ chế xác thực người dùng và token ngắn hạn phù hợp.
- Theo dõi mức sử dụng bất thường để phát hiện key bị sao chép hoặc chia sẻ ngoài dự kiến.

Một API key công khai có thể hữu ích cho nhận diện ứng dụng và đo usage, nhưng không được dùng làm ranh giới duy nhất để bảo vệ dữ liệu riêng tư.

## 10. Giám sát và kiểm thử

### 10.1. Giám sát theo key ID và client

Các chỉ số và sự kiện nên hỗ trợ phát hiện bất thường mà không lộ secret:

- Số request theo `client_id`, `key_id`, endpoint, môi trường và kết quả.
- Tỷ lệ xác thực thất bại, key hết hạn hoặc key đã bị thu hồi.
- Tốc độ tiêu thụ quota và số lần nhận `429`.
- Thay đổi IP, vùng địa lý hoặc user agent bất thường nếu tín hiệu này phù hợp với loại client.
- Key lâu không sử dụng, key sắp hết hạn và key chưa có owner rõ ràng.
- Các lần tạo, xoay vòng, thay scope, đổi quota và thu hồi key.

Không ghi giá trị key vào metric label hoặc log. Tránh tạo nhãn metric có cardinality quá cao; có thể dùng dashboard hoặc sự kiện bảo mật có kiểm soát để tra cứu theo từng key ID.

### 10.2. Ma trận kiểm thử

| Tình huống | Kết quả cần xác minh |
|---|---|
| Không gửi key | Request bị từ chối theo hợp đồng API |
| Key sai định dạng hoặc secret không khớp | Bị từ chối và không tiết lộ key ID hợp lệ |
| Key đã hết hạn hoặc bị thu hồi | Bị từ chối trên mọi API instance |
| Dùng key staging ở production | Bị từ chối do sai môi trường |
| Key hợp lệ nhưng thiếu scope | Bị từ chối ở bước authorization |
| Key có scope đúng nhưng truy cập đối tượng ngoài tenant | Không đọc hoặc sửa được đối tượng |
| Key bị gửi trong query string | Không được hỗ trợ; log và gateway không lưu secret |
| Hai key thuộc cùng client | Quota tổng ở cấp client/tenant vẫn được áp dụng đúng |
| Nhiều request đồng thời sát ngưỡng | Không vượt giới hạn ngoài sai số đã định nghĩa |
| Key bị thu hồi khi cache còn active | Thời gian chấp nhận sau thu hồi nằm trong giới hạn chính sách |
| Secret xuất hiện trong exception hoặc trace | Không có secret trong log, trace hay telemetry |
| Key bị lộ và được xoay vòng | Key mới hoạt động, key cũ bị vô hiệu hóa đúng thời điểm |

Nên kiểm thử cả luồng thành công và các tình huống đồng thời, nhiều instance, lỗi kho quota, lỗi secret manager và thu hồi key. Một unit test cho hàm so sánh digest không chứng minh toàn bộ gateway và các API backend đều thực thi chính sách giống nhau.

## 11. Nguyên tắc triển khai

Khi thiết kế API key, hãy bắt đầu từ nhu cầu nhận diện client và mô hình sử dụng. Cấp key riêng theo client, project và môi trường; tạo secret ngẫu nhiên đủ mạnh; chỉ lưu digest; truyền qua HTTPS header; che secret khỏi log; và có quy trình cấp phát, xoay vòng, hết hạn, thu hồi rõ ràng.

Sau khi xác thực key, tạo client principal từ metadata phía máy chủ. Dùng principal đó để kiểm tra scope, tenant, quyền trên đối tượng và quota. Đặt quota ở cấp phản ánh đúng hợp đồng, đồng thời có giới hạn tốc độ để chống burst và lạm dụng. Nếu request cần đại diện cho người dùng cuối, xác thực người dùng bằng cơ chế phù hợp và kết hợp danh tính đó với client identity.

**API key giúp hệ thống biết client nào đang gọi và áp dụng chính sách sử dụng tương ứng. Bảo mật chỉ hoàn chỉnh khi key được quản lý như một secret, quyền được kiểm tra ở từng endpoint và từng đối tượng, còn quota được thực thi nhất quán trên toàn hệ thống.**
