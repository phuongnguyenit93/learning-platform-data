# API key authentication

> **Chương:** API key  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Xác thực yêu cầu API bằng API key, từ phát hành và lưu trữ bí mật đến kiểm tra, phân quyền, luân chuyển, thu hồi và ứng phó khi khóa bị lộ.

## 1. API key authentication là gì?

**API key** là một giá trị bí mật do nhà cung cấp dịch vụ cấp cho một ứng dụng, tích hợp hoặc chủ thể để nhận diện yêu cầu gửi đến API. Khi client gửi key, server kiểm tra key có tồn tại, còn hiệu lực và thuộc tài khoản/tích hợp nào. Nếu hợp lệ, server có thể tiếp tục áp dụng chính sách truy cập, giới hạn lưu lượng và ghi nhận hoạt động.

API key thường là một **bearer credential**: bên nào sở hữu giá trị bí mật có thể trình nó để được nhận diện như chủ thể đã được cấp key. Vì vậy, nếu key bị sao chép, kẻ tấn công có thể dùng nó từ một client khác cho đến khi key hết hạn hoặc bị thu hồi.

API key thường phù hợp với:

- Tích hợp server-to-server có danh tính và chủ sở hữu rõ ràng.
- Script hoặc công cụ tự động gọi API theo phạm vi hẹp.
- Nhận diện một ứng dụng hoặc một dự án để áp dụng quota, thống kê và quản lý.
- Truy cập API trong môi trường mà key có thể được lưu và bảo vệ phía server.

API key **không tự chứng minh một con người đang trực tiếp sử dụng ứng dụng**, không tự mã hóa dữ liệu và không tự quyết định mọi quyền truy cập. API cần xác định chủ thể gắn với key rồi kiểm tra quyền trên tài nguyên cụ thể.

### Kết quả học tập

Sau bài này, người học có thể:

- Giải thích API key như một credential bí mật dạng bearer và phân biệt nó với mật khẩu, session token, OAuth access token và chứng chỉ.
- Thiết kế cách sinh, cấp phát, hiển thị, lưu trữ và xác minh API key.
- Đặt scope, quota, thời hạn và quyền tối thiểu cho từng key.
- Bảo vệ key trong client, đường truyền, log, kho bí mật và pipeline triển khai.
- Xây dựng quy trình rotation, revocation, audit và ứng phó khi key bị lộ.
- Nhận diện khi API key không phù hợp và cần dùng OAuth, workload identity hoặc mTLS.

## 2. API key đại diện cho ai?

Một API key chỉ hữu ích khi server biết nó thuộc về chủ thể nào và được cấp cho mục đích gì.

| Chủ thể được nhận diện | Ví dụ | Câu hỏi quản trị |
|---|---|---|
| Dự án/ứng dụng | Ứng dụng báo cáo gọi API dữ liệu | Chủ dự án nào chịu trách nhiệm? |
| Tích hợp đối tác | Hệ thống đối tác gửi đơn hàng | Key có giới hạn đúng đối tác và môi trường không? |
| Tài khoản dịch vụ | Job đồng bộ dữ liệu chạy theo lịch | Ai sở hữu service account và khi nào key bị thu hồi? |
| Người dùng hoặc tổ chức | Khách hàng tạo key trong dashboard | Key có đại diện cho tenant và quyền của người tạo không? |
| Môi trường triển khai | Key riêng cho staging và production | Có tránh dùng lẫn môi trường không? |

**Không nên dùng chung một key cho nhiều hệ thống hoặc nhiều nhóm** nếu cần khả năng thu hồi và truy vết độc lập. Nếu mười dịch vụ cùng dùng một key, khi một dịch vụ bị xâm nhập, tổ chức khó xác định nguồn lộ và phải thay key ở mọi nơi.

Một API key nên có metadata quản trị như:

- ID nội bộ và tiền tố nhận diện không bí mật.
- Chủ sở hữu, tenant, ứng dụng hoặc service account.
- Môi trường (development, staging, production).
- Scope/quyền được cấp và các giới hạn tài nguyên.
- Thời điểm tạo, hết hạn, thu hồi và sử dụng gần nhất.
- Người hoặc quy trình đã tạo, xoay vòng hay thu hồi key.

Metadata giúp server đưa ra quyết định và điều tra; **giá trị bí mật của key không được lưu trong metadata dạng đọc được**.

## 3. API key khác password, session token và OAuth access token

| Cơ chế | Mục đích chính | Vòng đời và đặc điểm |
|---|---|---|
| **Mật khẩu** | Người dùng chứng minh điều họ biết | Con người chọn; cần lưu verifier bằng password KDF chuyên dụng |
| **API key** | Nhận diện ứng dụng/tích hợp hoặc chủ thể gọi API | Thường do server sinh ngẫu nhiên; có thể sống lâu, cần scope và rotation |
| **Session cookie** | Duy trì trạng thái đăng nhập người dùng | Gắn với phiên; trình duyệt tự gửi theo cookie policy |
| **OAuth access token** | Cấp quyền truy cập tài nguyên theo authorization grant | Có scope, audience, thời hạn và cơ chế cấp/thu hồi theo giao thức |
| **Client certificate / mTLS** | Chứng minh quyền kiểm soát khóa riêng ở tầng TLS | Cần PKI, cấp phát, gia hạn và thu hồi chứng chỉ |
| **Workload identity** | Nhận diện workload/dịch vụ bằng danh tính có quản lý | Thường cấp credential ngắn hạn và tự động theo môi trường |

API key có thể được truyền như bearer secret trong header, nhưng không nên gọi nó là OAuth access token nếu nó không được cấp và kiểm tra theo OAuth. Một key tĩnh thường thiếu các đặc tính như audience, authorization grant, token exchange và vòng đời ngắn hạn mà hệ thống OAuth/workload identity có thể cung cấp.

### Khi nào nên cân nhắc phương thức khác?

- Ứng dụng di động hoặc web công khai không thể giữ bí mật lâu dài; không nhúng secret API key dùng chung vào mã client.
- Truy cập thay mặt người dùng cần consent, scope theo người dùng và khả năng thu hồi grant: cân nhắc OAuth/OIDC.
- Giao tiếp giữa workload trong hạ tầng có danh tính nền tảng: cân nhắc workload identity hoặc credential ngắn hạn.
- Dịch vụ cần xác thực lẫn nhau ở tầng kết nối: cân nhắc mTLS.
- API cần người dùng đăng nhập tương tác: dùng luồng xác thực người dùng phù hợp, không biến một API key tĩnh thành mật khẩu dùng chung.

## 4. Cấu trúc một API key

Một key thường gồm phần nhận diện và phần bí mật. Ví dụ định dạng minh họa:

~~~text
ak_live_7F3K9Q2M_<random-secret>
~~~

Trong đó:

- Tiền tố cho biết loại key hoặc môi trường; đây không phải bí mật.
- Key ID hoặc phần định danh giúp server tra cứu bản ghi.
- Phần secret ngẫu nhiên là giá trị phải được giữ kín.

Định dạng thực tế phụ thuộc sản phẩm. Tiền tố dễ nhận diện giúp phát hiện key trong log hoặc repository khi có công cụ scanning, nhưng **không thay thế entropy**. Không mã hóa tenant ID hoặc quyền nhạy cảm vào phần secret rồi tin dữ liệu đó mà không tra cứu và xác minh server-side.

### Sinh key

Key nên được sinh phía server bằng bộ tạo số ngẫu nhiên mật mã (CSPRNG). Ví dụ, 32 byte ngẫu nhiên tạo ra 256 bit entropy trước khi mã hóa biểu diễn. Không dùng timestamp, số tăng dần, UUID không phù hợp hoặc chuỗi tự ghép từ username và ngày tạo.

~~~typescript
// Pseudocode: dùng CSPRNG của nền tảng.
function generateApiKey() {
  const keyId = randomBytes(8).toString("hex");
  const secret = randomBytes(32).toString("base64url");
  return {
    keyId,
    secret,
    presentedKey: "ak_live_" + keyId + "_" + secret,
  };
}
~~~

Đây là mã giả. Hàm randomBytes phải đến từ API mật mã của nền tảng và phải thất bại an toàn nếu nguồn ngẫu nhiên không sẵn sàng. Không dùng hàm random thông thường phục vụ giao diện hoặc mô phỏng.

### Hiển thị một lần

Khi tạo key, dashboard có thể hiển thị secret đầy đủ **một lần** để chủ sở hữu sao chép vào secret manager. Sau khi đóng màn hình, server không thể đọc lại secret từ database nếu chỉ lưu verifier. Người dùng cần tạo key mới nếu làm mất giá trị ban đầu.

Không gửi key qua email, chat, ticket hỗ trợ hoặc log. Nếu cần cấp key cho đối tác, dùng kênh trao đổi bí mật được phê duyệt và xác nhận người nhận.

## 5. Lưu trữ API key phía server

Khác mật khẩu do con người chọn, API key được sinh ngẫu nhiên với entropy cao. Vì vậy, cách lưu verifier có thể khác password storage:

- Không lưu secret đầy đủ ở dạng rõ trong database.
- Lưu key ID/prefix để tìm bản ghi.
- Lưu digest của secret hoặc verifier phù hợp để so sánh khi nhận key.
- Giới hạn quyền đọc bảng key và bảo vệ backup.
- Lưu metadata scope, owner, expiry, status và audit riêng.

Với key 256 bit ngẫu nhiên, dùng hash mật mã nhanh như SHA-256 để tạo digest thường phù hợp vì việc vét cạn không gian khóa là không thực tế. Có thể dùng HMAC với khóa server-side được quản lý riêng nếu mô hình đe dọa yêu cầu bảo vệ bổ sung khi chỉ database bị lộ. Không cần dùng Argon2id/bcrypt như mật khẩu con người cho secret ngẫu nhiên dài; chi phí chậm có thể làm endpoint xác minh dễ bị DoS mà không đem lại lợi ích tương xứng.

### Schema minh họa

~~~sql
CREATE TABLE api_key (
    key_id          VARCHAR(32) PRIMARY KEY,
    secret_digest   BINARY(32) NOT NULL,
    owner_id        BIGINT NOT NULL,
    environment     VARCHAR(20) NOT NULL,
    scopes          TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP,
    revoked_at      TIMESTAMP,
    last_used_at    TIMESTAMP
);
~~~

Đây là schema khái niệm. Kiểu dữ liệu, digest format và mô hình scope cần theo hệ thống thực tế. Nếu dùng HMAC, lưu key version/reference chứ không lưu pepper cạnh digest; quản lý khóa HMAC trong secret manager/KMS và có kế hoạch rotation.

### Hash hay HMAC?

| Phương pháp | Đặc điểm | Lưu ý |
|---|---|---|
| SHA-256(secret) | Digest không cần khóa bí mật bổ sung | Phù hợp với secret có entropy cao và được sinh ngẫu nhiên đúng cách |
| HMAC-SHA-256(serverPepper, secret) | Cần bí mật server-side để tính verifier | Bảo vệ thêm nếu chỉ database bị lộ; tăng yêu cầu quản lý và xoay khóa |
| Password KDF chậm | Tốn CPU/bộ nhớ cho mỗi lần xác minh | Thường dành cho mật khẩu con người; không cần thiết cho API key entropy cao |

Điều kiện quan trọng là secret phải thực sự ngẫu nhiên và đủ dài. Nếu người dùng tự chọn API key dễ đoán, các giả định về digest nhanh không còn đúng.

## 6. Truyền API key trong request

Key phải được gửi qua HTTPS/TLS. Cách phổ biến là dùng header:

~~~http
GET /v1/reports
Authorization: Bearer ak_live_<key-id>_<secret>
~~~

Một số API dùng header riêng như X-API-Key. Dù chọn header nào, server cần bảo đảm proxy, gateway và middleware không ghi giá trị key vào log.

### Không đặt key trong URL

Không gửi API key qua query string hoặc path:

~~~http
GET /v1/reports?api_key=secret-value
~~~

URL có thể bị ghi vào access log, browser history, analytics, cache, hệ thống giám sát và header Referer. Header cũng có thể bị log nếu cấu hình sai, nhưng dễ kiểm soát redaction tập trung hơn. Không dùng URL làm nơi chứa secret.

### TLS không xử lý mọi rủi ro

TLS bảo vệ dữ liệu khi truyền giữa các điểm kết thúc TLS. Nếu key bị lộ trong mã nguồn, log, trình duyệt, thiết bị hoặc secret manager bị xâm nhập thì HTTPS không thu hồi được key. Cũng cần xem xét proxy chấm dứt TLS, service mesh, gateway và đường truyền nội bộ.

## 7. Xác minh API key ở server

Luồng xác minh điển hình:

1. Nhận key từ header được quy định.
2. Kiểm tra định dạng và kích thước đầu vào trước khi xử lý.
3. Tách key ID/prefix và secret.
4. Tra bản ghi theo key ID; không tìm kiếm toàn bộ database bằng secret thô.
5. Tính digest/HMAC theo phiên bản lưu trữ và so sánh an toàn.
6. Kiểm tra trạng thái, thời hạn, môi trường, chủ sở hữu và chính sách key.
7. Tạo principal nội bộ từ bản ghi đáng tin cậy.
8. Kiểm tra scope và quyền đối với route, tenant, tài nguyên, hành động cụ thể.
9. Áp dụng quota/rate limit và ghi audit đã loại bỏ secret.
10. Chỉ thực hiện thao tác nếu tất cả điều kiện đạt.

~~~mermaid
flowchart TD
    C["Client gửi API key qua HTTPS"] --> H["Đọc header và kiểm tra định dạng"]
    H --> I["Tách key ID và secret"]
    I --> L["Tra bản ghi key theo ID"]
    L --> V{"Digest hợp lệ?"}
    V -->|"Không"| N["401: không xác thực"]
    V -->|"Có"| S{"Key active, đúng môi trường, chưa hết hạn?"}
    S -->|"Không"| N
    S -->|"Có"| P["Tạo principal từ metadata server"]
    P --> A{"Có scope và quyền trên tài nguyên?"}
    A -->|"Không"| F["403: không được phép"]
    A -->|"Có"| Q["Quota / rate limit / audit"]
    Q --> R["Thực hiện API"]
~~~

### Mã giả xác minh

~~~typescript
async function authenticateApiKey(presentedKey) {
  const parsed = parseApiKey(presentedKey);
  if (!parsed) return { ok: false };

  const record = await findKeyById(parsed.keyId);
  if (!record) return { ok: false };

  const candidateDigest = digestSecret(parsed.secret, record.digestVersion);
  if (!constantTimeEqual(candidateDigest, record.secretDigest)) {
    return { ok: false };
  }

  if (record.revokedAt || isExpired(record.expiresAt)) {
    return { ok: false };
  }
  if (record.environment !== requestEnvironment()) {
    return { ok: false };
  }

  return {
    ok: true,
    principal: {
      ownerId: record.ownerId,
      keyId: record.keyId,
      scopes: record.scopes,
    },
  };
}
~~~

Mã giả minh họa trách nhiệm, không phải thư viện bảo mật hoàn chỉnh. parseApiKey phải giới hạn đầu vào; digestSecret phải dùng thuật toán/phiên bản cấu hình tin cậy; constantTimeEqual phải đến từ thư viện phù hợp. Trong triển khai thật, trạng thái, scope và quyền phải được kiểm tra theo dữ liệu server mới nhất hoặc cơ chế cache có giới hạn độ trễ.

### 401 và 403

- **401 Unauthorized:** không có key, key sai, hết hạn, bị thu hồi hoặc không xác thực được.
- **403 Forbidden:** key hợp lệ nhưng không có scope/quyền thực hiện hành động.

Phản hồi cần tránh tiết lộ chi tiết giúp dò key hoặc tài khoản. Không trả secret, digest hay thông tin nội bộ trong lỗi.

## 8. Xác thực không đồng nghĩa phân quyền

API key trả lời câu hỏi **“yêu cầu này gắn với key/chủ thể nào?”**. Phân quyền trả lời **“chủ thể đó được phép làm gì trên tài nguyên nào?”**.

Ví dụ, một key thuộc dự án A có scope reports:read. Điều đó không tự cho phép key đọc mọi báo cáo của mọi khách hàng. API vẫn phải kiểm tra:

- Key có thuộc tenant sở hữu tài nguyên không?
- Scope có cho phép hành động read không?
- Người sở hữu key có quyền trên đối tượng cụ thể không?
- Tài nguyên có đang ở trạng thái cho phép truy cập không?
- Có giới hạn theo môi trường, vùng dữ liệu hoặc chính sách tổ chức không?

### Quyền tối thiểu

Mỗi key chỉ nên có quyền cần thiết cho một tác vụ. Tránh key mặc định có quyền quản trị hoặc admin:* trên mọi API. Ví dụ:

| Key | Scope đề xuất | Không nên cấp |
|---|---|---|
| Job đọc báo cáo hàng ngày | reports:read cho dự án được chỉ định | users:write, admin:* |
| Webhook nhận trạng thái đơn hàng | orders:read hoặc quyền nhận webhook riêng | Quyền đọc toàn bộ khách hàng |
| Script tạo bản ghi đồng bộ | records:create trong một tenant | Xóa hoặc xuất toàn bộ dữ liệu |
| Công cụ quản trị | Scope riêng, thời hạn ngắn, step-up/phê duyệt nếu cần | Key dùng chung lâu dài cho cả nhóm |

Scope nên được kiểm tra ở server, gắn với tài nguyên và tenant. Không tin danh sách scope client gửi kèm request.

## 9. Bảo vệ API key ở phía client

Khả năng bảo vệ key phụ thuộc loại client:

| Client | Có thể giữ secret lâu dài không? | Hướng thiết kế |
|---|---|---|
| Backend do tổ chức quản lý | Có thể, nếu dùng secret manager và quyền tối thiểu | Key riêng theo service/môi trường, rotation, audit |
| Script chạy trên máy chủ | Có thể trong giới hạn môi trường | Secret manager, file permission, tránh command history/log |
| Trình duyệt JavaScript công khai | Không | Không nhúng secret; dùng backend trung gian hoặc luồng OAuth phù hợp |
| Ứng dụng mobile phân phối rộng | Không thể bảo đảm bí mật chung | Dùng user authentication/OAuth, attestation hoặc backend theo kiến trúc |
| Ứng dụng desktop phân phối cho khách hàng | Không thể coi binary là kho bí mật | Cấp credential theo người dùng/thiết bị, token ngắn hạn và quyền hẹp |
| CI/CD pipeline | Có thể nếu secret store được bảo vệ | Secret masking, scope theo pipeline, rotation và giới hạn runner |

Mã đã minify, obfuscate hoặc đóng gói không biến secret thành bí mật. Người dùng có thể trích key từ bundle, APK, IPA, binary, memory hoặc network request. CORS cũng không bảo vệ một API key đã nhúng trong client; CORS chủ yếu là chính sách trình duyệt, không ngăn client tùy ý gọi API.

### Cách giảm rủi ro

- Để backend giữ key và gọi dịch vụ bên ngoài thay cho browser/mobile.
- Nếu cần xác thực người dùng, dùng OAuth/OIDC flow phù hợp; tránh một key dùng chung cho tất cả người cài ứng dụng.
- Dùng token ngắn hạn có scope hẹp được cấp từ backend hoặc hệ thống identity.
- Tách key theo môi trường, service và đối tác.
- Không đưa secret vào source code, repository, build artifact hoặc file cấu hình được phát hành công khai.
- Bảo vệ secret trong secret manager/KMS; giới hạn quyền đọc và theo dõi truy cập.
- Tránh truyền key trong tham số dòng lệnh nếu shell history/process listing có thể làm lộ; ưu tiên cơ chế secret injection an toàn của nền tảng.

Một số sản phẩm có **publishable key** được thiết kế để xuất hiện trong client. Loại key này chỉ an toàn nếu server coi nó là định danh công khai, giới hạn chức năng và không cấp quyền bí mật. Không nhầm publishable key với secret key.

## 10. Rotation, expiry và revocation

API key tĩnh có thể sống lâu nên cần vòng đời quản trị rõ ràng.

### Rotation

Rotation là thay key cũ bằng key mới theo kế hoạch:

1. Tạo key mới với cùng scope hoặc scope đã được rà soát lại.
2. Phân phối secret mới đến secret manager của client qua kênh an toàn.
3. Cập nhật client và xác nhận request bằng key mới thành công.
4. Theo dõi việc sử dụng key cũ trong một khoảng chuyển tiếp có giới hạn.
5. Thu hồi key cũ sau khi xác nhận không còn client hợp lệ dùng nó.
6. Ghi audit và lưu kết quả rotation.

Không để hai key cùng hoạt động vô thời hạn chỉ vì việc chuyển đổi chưa được hoàn tất. Nếu key cũ bị lộ, rút ngắn hoặc bỏ qua thời gian chuyển tiếp theo quy trình sự cố.

### Expiry

Đặt thời hạn cho key theo mục đích và rủi ro. Key tạm thời cho một lần di chuyển dữ liệu có thể sống ngắn; key tích hợp lâu dài cần lịch rà soát và rotation. Thời hạn dài không phải lý do để bỏ qua giám sát.

### Revocation

Thu hồi khi:

- Người sở hữu hoặc ứng dụng không còn cần key.
- Nhân viên/đối tác thay đổi vai trò hoặc chấm dứt quan hệ.
- Phát hiện key trong repository, log, ticket hoặc thiết bị bị mất.
- Có hành vi bất thường hoặc nghi ngờ truy cập trái phép.
- Scope hoặc chính sách đã thay đổi.

Server phải kiểm tra trạng thái thu hồi ở mỗi request hoặc dùng cache có thời hạn và cơ chế invalidation đủ nhanh. Nếu cache trạng thái key quá lâu, key đã thu hồi có thể vẫn hoạt động cho đến khi cache hết hạn.

### Trạng thái vòng đời

~~~mermaid
stateDiagram-v2
    [*] --> Created: Sinh key
    Created --> Active: Chủ sở hữu nhận và cấu hình
    Active --> Active: Sử dụng hợp lệ
    Active --> Expiring: Gần hết hạn
    Expiring --> Active: Gia hạn theo chính sách
    Expiring --> Revoked: Kết thúc vòng đời
    Active --> Revoked: Thu hồi / nghi lộ
    Revoked --> [*]
~~~

Không tái kích hoạt key đã bị lộ chỉ bằng cách bỏ cờ revoked. Hãy tạo key mới, phân phối lại và điều tra phạm vi sử dụng key cũ.

## 11. Rate limit, quota và giám sát

API key cho phép hệ thống gắn lưu lượng với một chủ thể, nhưng quota không thay thế authorization.

Các giới hạn có thể áp dụng:

- Theo key ID, owner, tenant, route hoặc loại thao tác.
- Theo thời gian, burst và mức đồng thời.
- Theo số bản ghi hoặc dung lượng dữ liệu được đọc/ghi.
- Theo môi trường hoặc nhóm API.
- Theo tín hiệu rủi ro như IP, thiết bị hoặc vị trí bất thường.

Không dùng secret đầy đủ làm nhãn metric hoặc log. Dùng key ID không bí mật, owner ID và correlation ID. Cẩn trọng khi ghi IP hoặc thông tin thiết bị vì chúng có thể là dữ liệu nhạy cảm.

### Dấu hiệu bất thường

| Tín hiệu | Khả năng cần điều tra |
|---|---|
| Key dùng từ IP/ASN hoặc vùng chưa từng thấy | Secret bị sao chép hoặc client mới |
| Tăng đột ngột request 401/403 | Key bị thử đoán hoặc cấu hình sai |
| Key chỉ đọc báo cáo nhưng gọi endpoint ghi/xóa | Lạm dụng scope hoặc lỗi phân quyền |
| Lưu lượng tăng bất thường | Key bị lộ, job lỗi hoặc abuse |
| Key production xuất hiện trong staging/public repo | Rò rỉ secret |
| Key tiếp tục hoạt động sau khi owner rời tổ chức | Quy trình offboarding/rotation thiếu |

Không tự động kết luận có tấn công từ một tín hiệu đơn lẻ. Kết hợp dữ liệu, áp dụng biện pháp phù hợp và cho phép chủ sở hữu xác minh hoạt động hợp lệ.

## 12. Replay và request signing

API key dạng bearer có thể bị sử dụng lại nếu kẻ tấn công lấy được secret. TLS giảm nguy cơ nghe lén trên đường truyền, nhưng không bảo vệ khi secret bị lộ ở client, log hoặc endpoint.

Với API có yêu cầu cao hơn, hệ thống có thể dùng **request signing**: client ký nội dung request bằng bí mật hoặc khóa riêng, kèm timestamp, nonce và digest body. Server xác minh chữ ký, cửa sổ thời gian và nonce chưa được dùng. Cách này có thể làm giảm replay hoặc sửa đổi request nếu thiết kế đúng.

Tuy nhiên, request signing phức tạp:

- Client và server phải chuẩn hóa canonical request giống hệt nhau.
- Phải định nghĩa rõ header nào, path, query, body digest và timestamp tham gia chữ ký.
- Nonce cần được lưu/kiểm tra chống dùng lại trong cửa sổ phù hợp.
- Đồng hồ lệch, proxy và retry có thể gây lỗi.
- Nếu khóa ký bị đánh cắp, kẻ tấn công vẫn có thể ký request mới.

Không tự thiết kế giao thức ký request nếu đã có chuẩn hoặc giải pháp được nền tảng hỗ trợ. HMAC signing không thay thế TLS; vẫn cần TLS để bảo vệ dữ liệu và chống nghe lén.

## 13. Ứng phó khi API key bị lộ

Khi key xuất hiện trong repository công khai, log, ticket hoặc thiết bị bị mất, giả định rằng bất kỳ ai thấy được nó đều có thể sử dụng.

### Quy trình xử lý

1. **Xác định key:** dùng prefix/key ID hoặc nguồn phát hiện; không sao chép secret vào ticket điều tra.
2. **Đánh giá phạm vi:** chủ sở hữu, môi trường, scope, tài nguyên và thời điểm có thể bị lộ.
3. **Chặn truy cập:** thu hồi key hoặc giảm quyền ngay theo mức độ sự cố; không chờ điều tra hoàn tất nếu nguy cơ đang diễn ra.
4. **Cấp key mới:** tạo secret mới, phân phối qua secret manager/kênh an toàn và cập nhật client.
5. **Rà soát hoạt động:** request, dữ liệu đọc/ghi, thay đổi quyền, tạo key con và hành vi bất thường.
6. **Kiểm tra điểm rò rỉ:** repository, CI logs, artifacts, shell history, application logs, crash dump và backup.
7. **Làm sạch và ngăn tái diễn:** xóa secret khỏi vị trí không cần thiết, bật secret scanning, giảm quyền và cải thiện quy trình.
8. **Ghi audit và thông báo:** theo chính sách tổ chức, hợp đồng và yêu cầu pháp lý áp dụng.

Xóa key khỏi commit mới nhất không làm secret biến mất khỏi lịch sử Git, fork, cache hoặc bản clone. Cần thu hồi key trước, sau đó xử lý lịch sử và bản sao theo quy trình.

### Key bị lộ nhưng không thấy request bất thường

Không có log bất thường không chứng minh key chưa bị sử dụng. Log có thể thiếu, bị xóa hoặc không ghi đúng dữ liệu. Nếu key đã được công khai, ưu tiên thu hồi và thay thế; điều tra song song.

## 14. Ví dụ thực tế: job đồng bộ dữ liệu

**Bối cảnh:** Một job chạy mỗi giờ trên server để đọc báo cáo từ dịch vụ đối tác. Đối tác cấp API key cho dự án. Job chỉ cần quyền đọc báo cáo của tenant công ty.

### Thiết kế

| Thành phần | Lựa chọn |
|---|---|
| Chủ thể | Service account riêng cho job |
| Key | Sinh ngẫu nhiên phía đối tác, key ID + secret |
| Lưu trữ | Secret manager của môi trường chạy |
| Truyền | Authorization header qua HTTPS |
| Scope | Chỉ reports:read trong tenant được chỉ định |
| Quota | Giới hạn request và dung lượng theo lịch chạy |
| Rotation | Tạo key mới, cập nhật secret manager, xác nhận rồi thu hồi key cũ |
| Audit | Key ID, owner, route, thời điểm và kết quả; không log secret |

### Pseudocode phía client

~~~typescript
async function syncReports() {
  const apiKey = await secretManager.get("partner-reporting-api-key");

  const response = await fetch("https://api.partner.example/v1/reports", {
    method: "GET",
    headers: {
      "Authorization": "Bearer " + apiKey,
      "Accept": "application/json",
    },
  });

  if (response.status === 401) {
    throw new Error("API credential invalid or revoked");
  }
  if (response.status === 403) {
    throw new Error("API key does not have required permission");
  }
  if (!response.ok) {
    throw new Error("Partner API request failed");
  }

  return response.json();
}
~~~

Ví dụ minh họa. Trong ứng dụng thật, cần xử lý retry/backoff, timeout, giới hạn kích thước response, redaction header trong tracing và lỗi từ secret manager. Không in apiKey ra console khi debug.

### Khi job chuyển sang một nền tảng mới

Không sao chép key production vào file cấu hình của repository mới. Tạo quyền truy cập secret manager cho workload mới, cấp key riêng nếu mô hình đối tác cho phép, kiểm thử trong staging, sau đó chuyển traffic và thu hồi key của workload cũ. Nếu đối tác hỗ trợ workload identity hoặc OAuth client credentials, đánh giá việc thay key tĩnh bằng credential ngắn hạn.

## 15. Checklist thiết kế API key

- [ ] Mỗi key có owner, mục đích, môi trường và scope rõ ràng.
- [ ] Key được sinh bằng CSPRNG, có entropy cao và không do người dùng tự đặt.
- [ ] Secret chỉ hiển thị một lần; server không lưu secret dạng rõ.
- [ ] Database lưu key ID/prefix, digest/verifier và metadata quản trị.
- [ ] Digest nhanh chỉ dùng khi secret có entropy cao; pepper/HMAC được quản lý riêng nếu cần.
- [ ] Key truyền qua HTTPS trong header; không đặt trong URL.
- [ ] Proxy, gateway, tracing, error reporting và log đã redaction header chứa key.
- [ ] Client công khai không chứa secret dùng chung; backend giữ bí mật trong secret manager.
- [ ] Key có scope tối thiểu, quota, rate limit và kiểm tra quyền theo tài nguyên/tenant.
- [ ] Key có expiry hoặc lịch rà soát, rotation và revocation.
- [ ] Trạng thái revoked có hiệu lực đủ nhanh ở mọi API instance/cache.
- [ ] Có audit tạo, sử dụng, thay đổi scope, rotation và thu hồi.
- [ ] Có quy trình xử lý khi key lộ; thu hồi trước khi làm sạch bản sao.
- [ ] Kiểm thử key sai, hết hạn, thu hồi, sai môi trường, thiếu scope và vượt quota.
- [ ] Đánh giá OAuth, workload identity hoặc mTLS khi key tĩnh không còn phù hợp.

## Ghi nhớ

API key là một **bí mật bearer** giúp server nhận diện ứng dụng, tích hợp hoặc chủ thể gọi API. Key cần được sinh ngẫu nhiên, chỉ hiển thị một lần, lưu dưới dạng verifier, truyền qua TLS trong header, giới hạn scope và có vòng đời rotation/revocation rõ ràng.

Giá trị key hợp lệ chỉ trả lời “ai đang trình credential này?”. Server vẫn phải kiểm tra chủ thể được phép làm gì trên tài nguyên cụ thể. Khi key bị lộ, hãy thu hồi và cấp key mới, điều tra hoạt động, xử lý mọi vị trí rò rỉ và giảm quyền. Với client công khai hoặc hệ thống cần credential ngắn hạn và danh tính workload mạnh hơn, hãy cân nhắc OAuth hoặc workload identity thay vì nhúng một secret dùng chung.
