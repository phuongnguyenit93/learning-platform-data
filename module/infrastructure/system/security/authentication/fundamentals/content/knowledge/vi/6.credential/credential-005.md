# API key credential

## 1. API key là gì và xác thực được điều gì?

**API key** là một giá trị được hệ thống phát hành để bên gọi API trình ra như **credential (thông tin xác thực)**. Khi nhận yêu cầu, dịch vụ kiểm tra API key rồi ánh xạ nó đến một chủ thể được quản lý, thường là ứng dụng, dịch vụ, công việc tự động hoặc tài khoản tích hợp (*integration account*).

Ví dụ: một dịch vụ tổng hợp báo cáo cần đọc số liệu từ API nội bộ mỗi đêm. Thay vì sử dụng mật khẩu của một nhân viên, quản trị viên cấp API key riêng cho tác vụ. API kiểm tra khóa để biết yêu cầu đang sử dụng credential của tác vụ báo cáo.

Điều quan trọng là phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **API key** | Giá trị bí mật hoặc định danh được dùng trong cơ chế xác thực API. | Khóa do hệ thống quản trị tích hợp cấp. |
| **Principal** | Danh tính mà hệ thống gắn cho credential. | Dịch vụ `nightly-report` thuộc tenant A. |
| **Authentication** | Kiểm tra bên gọi có đưa ra credential hợp lệ không. | Giá trị API key khớp bản ghi đang hoạt động. |
| **Authorization** | Quyết định principal được làm gì với tài nguyên nào. | Chỉ có quyền `reports:read` trên tenant A. |
| **Session/token** | Cơ chế đại diện cho lần xác thực hoặc quyền truy cập trong một khoảng thời gian. | Access token có thời hạn được cấp sau một luồng xác thực khác. |

**Một API key hợp lệ không chứng minh người cụ thể đang trực tiếp gọi API.** Nếu khóa bị sao chép, người nắm được bản sao có thể sử dụng nó như chủ thể được gắn với khóa, trừ khi hệ thống còn các kiểm soát ràng buộc bổ sung. Vì vậy, API key phù hợp nhất khi bên sử dụng có khả năng bảo vệ bí mật và hệ thống có chính sách phát hành, phân quyền, giám sát, thu hồi rõ ràng.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, API key là một ví dụ điển hình để học về ranh giới tin cậy giữa credential, xác thực, quyền, phiên, chống replay, phòng ngừa lạm dụng và khôi phục khi bị lộ khóa.

## 2. Các kiểu API key và cấu trúc khóa

Thuật ngữ “API key” được nhiều nền tảng sử dụng cho các thiết kế khác nhau. Cần đọc **hợp đồng bảo mật cụ thể** của nhà cung cấp, thay vì mặc định mọi key có cơ chế giống nhau.

### 2.1. Opaque bearer key

Kiểu phổ biến nhất là một chuỗi đủ ngẫu nhiên được gửi kèm mỗi yêu cầu. Máy chủ ánh xạ chuỗi đó đến principal và metadata. Đây là **bearer credential**: ai nắm khóa hợp lệ đều có thể trình khóa.

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.test
Authorization: ApiKey <API_KEY>
~~~

Ví dụ này minh họa một **quy ước header do API tự định nghĩa**. Một số hệ thống dùng `X-API-Key` hoặc `Authorization: Bearer ...`; client phải dùng đúng giao thức được tài liệu API quy định. Tên header không tự quyết định độ an toàn của credential.

### 2.2. Key ID và secret tách biệt

Để thuận tiện tra cứu và thu hồi, khóa có thể có cấu trúc:

~~~text
ak_live_<key-id>.<random-secret>
         └─ công khai để tra cứu
                  └─ bí mật dùng làm bằng chứng
~~~

Ví dụ cấu trúc trên chỉ có tính minh họa. `key-id` là **định danh tra cứu**, không tự nó cấp quyền. Phần `random-secret` phải có độ ngẫu nhiên đủ lớn và được giữ kín. Tiền tố như `ak_live_` giúp người quản trị và công cụ quét bí mật nhận diện loại khóa, môi trường hoặc mục đích; nó không thay cho kiểm tra phạm vi và issuer.

Hệ thống có thể hiển thị vài ký tự cuối của khóa cho mục đích nhận diện trên trang quản trị. **Đoạn hiển thị này không được xem là credential** và không nên dùng làm mã xác minh trong hỗ trợ khách hàng.

### 2.3. Publishable key và identifier không bí mật

Một số nền tảng đặt tên “public/publishable API key” cho định danh dự án hoặc cấu hình được phép xuất hiện trong trình duyệt. Những giá trị này **không phải bí mật xác thực có thể cấp đặc quyền máy chủ**. Các hành động nhạy cảm vẫn cần kiểm tra quyền bằng credential hoặc cơ chế khác.

Không được lấy một khóa được thiết kế để công khai rồi dùng như bằng chứng duy nhất cho việc đọc dữ liệu riêng tư hay thực hiện thanh toán.

### 2.4. API key dùng cho ký yêu cầu

Trong một thiết kế khác, client không gửi bí mật nguyên văn. Client dùng khóa bí mật để tạo **HMAC/chữ ký yêu cầu**; server kiểm tra chữ ký, timestamp, nonce và nội dung đã ký. Đây là **xác thực yêu cầu dựa trên khóa chia sẻ** và có mô hình chống replay khác với bearer key. Không nên gọi hai biến thể này là tương đương chỉ vì đều dùng “API key”.

## 3. Mô hình ranh giới tin cậy của một lời gọi API

~~~mermaid
sequenceDiagram
    participant C as Client/service gọi
    participant G as API gateway
    participant K as Kho metadata khóa
    participant A as Dịch vụ ứng dụng
    participant P as Bộ kiểm tra quyền
    C->>G: HTTPS + API key
    G->>G: Kiểm tra định dạng, credential và giới hạn truy cập
    G->>K: Tra khóa, kiểm tra trạng thái và expiry
    K-->>G: Principal, tenant, scope, key ID
    G->>A: Danh tính đã xác thực qua kênh tin cậy
    A->>P: Principal + hành động + tài nguyên
    P-->>A: Cho phép hoặc từ chối
    A-->>C: Phản hồi API
~~~

Sơ đồ mô tả một phương án có gateway kiểm tra API key. Nếu ứng dụng trực tiếp kiểm tra khóa thì cùng các trách nhiệm vẫn phải được bảo đảm.

Các điểm cần lưu ý:

1. **Client → gateway/API:** HTTPS/TLS bảo vệ bí mật trên đường truyền; phải xác thực đúng server và tránh chuyển key sang domain ngoài ý muốn.
2. **Gateway → kho khóa:** dịch vụ kiểm tra khóa cần quyền tra cứu tối thiểu, bảo vệ khóa mã hóa/HMAC phía server và không log bí mật thô.
3. **Gateway → ứng dụng:** nếu gateway truyền thông tin principal bằng header nội bộ, ứng dụng chỉ tin header do **gateway đáng tin** tạo ra. Gateway phải loại bỏ hoặc ghi đè header giả mạo từ Internet; kết nối nội bộ phải được kiểm soát/xác thực.
4. **Ứng dụng → tài nguyên:** authentication thành công chỉ cung cấp principal và ngữ cảnh, còn authorization phải kiểm tra tenant, scope, trạng thái và từng tài nguyên.
5. **Nhật ký/giám sát:** log dùng `key-id` hoặc mã định danh an toàn, tuyệt đối tránh ghi toàn bộ secret và header chứa nó.

Đặc biệt, một API key có quyền `reports:read` ở tenant A **không được** đọc dữ liệu tenant B dù ID của bản ghi bị đoán đúng.

## 4. Phát hành API key an toàn

Một quy trình cấp khóa thường gồm **xác thực người/đơn vị yêu cầu**, **kiểm tra quyền được tạo khóa**, **gắn khóa với principal**, **xác định scope**, **sinh secret ngẫu nhiên**, **lưu bằng chứng kiểm tra**, rồi **hiển thị bí mật qua một kênh an toàn**.

### 4.1. Độ ngẫu nhiên và không gian khóa

API key bí mật phải được sinh từ **bộ sinh số ngẫu nhiên an toàn về mặt mật mã (CSPRNG)**, không từ timestamp, số tăng dần, địa chỉ email, UUID cấu hình kém hoặc hàm `Math.random()`.

Ví dụ, 32 byte ngẫu nhiên chứa **256 bit entropy** trước khi mã hóa. Nếu biểu diễn bằng Base64URL, phần secret thường dài khoảng 43 ký tự, nhưng **độ dài chuỗi không thay cho entropy**. Với các dịch vụ có yêu cầu thấp hơn, ít nhất 128 bit entropy ngẫu nhiên vẫn là một mốc thiết kế thực tiễn phổ biến cho bearer secret; việc chọn số bit cụ thể cần phù hợp chính sách và mô hình rủi ro.

Ví dụ Node.js/TypeScript minh họa tạo key ID và secret:

~~~ts
import { randomBytes } from "node:crypto";

function generateApiKey() {
  // Key ID phục vụ tra cứu; secret là bằng chứng phải giữ kín.
  const keyId = randomBytes(12).toString("base64url");
  const secret = randomBytes(32).toString("base64url");
  return {
    keyId,
    secret,
    presentedKey: "ak_live_" + keyId + "." + secret,
  };
}
~~~

Đoạn mã chỉ tạo giá trị; **không phải toàn bộ quy trình cấp phát**. Khi triển khai thực tế còn cần xác minh principal được phép tạo khóa, gắn scope/tenant, lưu metadata, xử lý xung đột ID và quản lý bí mật server.

### 4.2. Ai được phép cấp khóa?

Không nên để tài khoản bình thường tự tạo khóa có quyền cao hơn quyền nó có. Một cơ chế cấp khóa an toàn thường có:

- Kiểm tra `key:create` hoặc quyền quản lý tích hợp theo vai trò/tenant.
- Chọn **principal riêng cho tích hợp** thay vì chia sẻ key của quản trị viên hoặc người dùng cá nhân.
- Chỉ chọn scope tối thiểu, giới hạn tài nguyên, môi trường và thời hạn.
- Xác thực lại hoặc yêu cầu phê duyệt đối với việc cấp khóa đặc quyền, theo rủi ro.
- Ghi nhận ai cấp, cấp cho hệ thống nào, vì mục đích gì và ai chịu trách nhiệm thu hồi.

Nếu tổ chức thay người vận hành, quyền của tích hợp cần được duy trì hoặc thu hồi theo **chủ sở hữu thực tế**, tránh key “mồ côi” không ai quản lý.

## 5. Lưu trữ và xác minh secret phía máy chủ

Đối với **bearer key ngẫu nhiên có entropy cao**, máy chủ thường **không cần lưu secret ở dạng có thể đọc lại**. Có thể lưu giá trị dẫn xuất một chiều để kiểm tra khóa được trình ra. Các lựa chọn gồm hash mật mã của khóa ngẫu nhiên hoặc HMAC với khóa bí mật phía server (*pepper*). HMAC giúp bảo vệ thêm trong kịch bản kho dữ liệu chứa bản ghi khóa bị lộ nhưng pepper vẫn an toàn.

Một bản ghi lưu trữ có thể gồm:

| Trường | Mục đích |
| --- | --- |
| `keyId` | Tra đúng bản ghi mà không quét toàn bộ dữ liệu. |
| `secretMac` | Giá trị HMAC của secret để so khớp, không lưu nguyên secret. |
| `pepperVersion` | Cho phép quản lý phiên bản khóa HMAC phía server. |
| `principalId` và `tenantId` | Định danh của tích hợp và phạm vi tổ chức. |
| `scopes` và ràng buộc tài nguyên | Giới hạn quyền tối thiểu. |
| `createdAt`, `expiresAt`, `revokedAt` | Quản lý vòng đời và thu hồi. |
| `lastUsedAt`, metadata kiểm toán | Phát hiện khóa không còn sử dụng, điều tra sự cố. |

**Pepper phải lưu ở secret manager/KMS hoặc môi trường bảo vệ tương đương, tách khỏi cơ sở dữ liệu lưu key.** Không hard-code pepper trong mã nguồn; mất pepper có thể khiến việc xác minh tất cả các khóa phụ thuộc phiên bản đó bị ảnh hưởng. Nếu dùng hash thông thường, cần hiểu rằng nó chỉ là giá trị kiểm tra của secret ngẫu nhiên; mã hóa có thể giải ngược chỉ nên dùng khi thực sự cần truy xuất lại khóa cho một giao thức khác.

Đoạn mã sau minh họa **lõi kiểm tra** sau khi cơ chế phát hành đã lưu HMAC tương ứng; phần truy vấn, xử lý lỗi và hạn chế tốc độ phải được triển khai phù hợp:

~~~ts
import { createHmac, timingSafeEqual } from "node:crypto";

interface StoredKey {
  keyId: string;
  secretMacHex: string; // 64 ký tự hex cho HMAC-SHA256
  principalId: string;
  tenantId: string;
  scopes: string[];
  expiresAt: Date;
  revokedAt: Date | null;
}

function macForSecret(secret: string, pepper: Buffer): Buffer {
  return createHmac("sha256", pepper)
    .update("api-key-v1:", "utf8")
    .update(secret, "utf8")
    .digest();
}

function verifyPresentedKey(
  presented: string,
  record: StoredKey | null,
  pepper: Buffer,
  now: Date
): { principalId: string; tenantId: string; scopes: string[] } | null {
  const match = /^ak_live_([A-Za-z0-9_-]{16})\.([A-Za-z0-9_-]{43})$/.exec(presented);
  if (!match || !record || record.keyId !== match[1]) return null;

  const candidate = macForSecret(match[2], pepper);
  const stored = Buffer.from(record.secretMacHex, "hex");
  if (stored.length !== candidate.length) return null; // Bản ghi lỗi định dạng
  if (!timingSafeEqual(candidate, stored)) return null;
  if (record.revokedAt || now >= record.expiresAt) return null;

  return {
    principalId: record.principalId,
    tenantId: record.tenantId,
    scopes: record.scopes,
  };
}
~~~

Để ví dụ đồng nhất, **khi phát hành** phải lưu `secretMacHex = macForSecret(secret, pepper).toString("hex")`, và khi kiểm tra phải tra bản ghi theo `keyId` đã tách từ key. Regex ở ví dụ tương ứng với key ID sinh từ 12 byte và secret sinh từ 32 byte của mục trước. Đây là mã **minh họa**, chưa bao gồm tra cứu bất đồng bộ, lỗi hạ tầng, khóa/phiên bản pepper, hạn chế tốc độ, chống enumeration qua timing hay chính sách quyền.

Lưu ý thực hành:

- Dùng so sánh cố định thời gian như `timingSafeEqual` cho MAC cùng độ dài; so sánh secret thô bằng toán tử chuỗi thông thường có thể tạo khác biệt timing.
- Không tiết lộ “key ID không tồn tại”, “key hết hạn” hay “secret sai” trong phản hồi công khai; có thể dùng `401 Unauthorized` chung, ghi nguyên nhân chi tiết vào log nội bộ không chứa secret.
- Giới hạn kích thước header trước khi xử lý và chuẩn hóa **đúng theo giao thức đã định**; không tùy ý bỏ ký tự, đổi chữ hoa/thường hay cắt khoảng trắng bên trong secret.
- Xử lý lỗi truy vấn kho khóa hoặc không tải được pepper theo nguyên tắc **fail closed**; không cho truy cập khi không thể kiểm tra.
- Kiểm tra phạm vi quyền **sau khi** có principal hợp lệ và vẫn phải kiểm tra lại trên từng tài nguyên/hành động.

API key được sinh ngẫu nhiên khác mật khẩu do con người chọn: mật khẩu thường có entropy thấp và cần cơ chế băm mật khẩu chậm, có salt như Argon2id. Với **secret API key thực sự ngẫu nhiên, entropy cao**, HMAC-SHA-256 hoặc hash mật mã phù hợp có thể được dùng theo mô hình lưu trữ đã thiết kế; không suy diễn cách lưu API key sang cách lưu mật khẩu.

## 6. Sử dụng và truyền API key đúng cách

**Chỉ gửi API key qua HTTPS/TLS** tới đúng API được tin cậy. Với bearer key, thường đặt trong HTTP request header theo giao thức do server quy định; đừng đặt trong URL query, path hoặc fragment.

Ví dụ không nên làm:

~~~http
GET /v1/reports?api_key=<SECRET> HTTP/1.1
Host: api.example.test
~~~

URL có thể xuất hiện trong access log, lịch sử trình duyệt, proxy, công cụ phân tích hoặc bị chia sẻ qua ảnh chụp và báo cáo lỗi. Đặt trong header giúp tránh một số đường lộ khóa, nhưng **header vẫn có thể bị log hoặc quan sát ở các điểm kết thúc TLS**. Do đó phải cấu hình hệ thống ghi log để che/loại bỏ credential.

Một số nguyên tắc vận hành:

1. **Server-side only đối với secret đặc quyền:** không nhúng vào JavaScript phân phối cho trình duyệt, bundle ứng dụng di động hoặc mã nguồn công khai. Người sử dụng có thể trích xuất các giá trị đã được phân phối đến thiết bị của họ.
2. **Lưu ở kho bí mật:** triển khai bằng secret manager hoặc cơ chế bí mật của môi trường chạy; hạn chế ai có thể đọc và phân biệt môi trường phát triển, thử nghiệm, sản xuất.
3. **Không để trong repo, file cấu hình công khai hoặc log:** bật quét secret, che giá trị trong error report và công cụ quan sát, tránh in request headers khi debug.
4. **Không tự chuyển tiếp sang host khác:** client HTTP phải kiểm soát redirect; một số thư viện có chính sách khác nhau về việc giữ header khi đổi origin.
5. **Đối với proxy/gateway:** chỉ tin header xác thực đã kiểm tra từ thành phần đáng tin; xử lý header trùng lặp và giới hạn độ dài để tránh khác biệt cách diễn giải giữa các tầng.
6. **Bảo vệ hạ tầng runtime:** nếu máy chủ, container hoặc CI job bị chiếm, biến môi trường và kho bí mật đã mount có thể bị đọc. Secret manager giảm rủi ro phát tán và giúp quản trị vòng đời, nhưng không thay cho bảo mật runtime.

Một API key được triển khai trong phần mềm của khách hàng cuối **không thể** xem là bí mật vĩnh viễn. Nếu kiến trúc bắt buộc client không tin cậy gọi API, hãy thiết kế cơ chế truy cập dành cho public client như ủy quyền người dùng, token ngắn hạn và kiểm soát quyền phía server, thay vì trao cho client một khóa đặc quyền dùng chung.

## 7. Authentication bằng API key không thay authorization

Sau khi xác minh API key, backend thường có các dữ liệu: `principalId`, `tenantId`, `keyId`, `scopes` và trạng thái credential. Từ đó backend **phải kiểm tra quyền theo hành động và tài nguyên**.

Ví dụ, key A có scope `orders:read` thuộc tenant `store-a`. Nó được phép đọc đơn hàng của `store-a` nhưng không được sửa đơn hàng hoặc truy cập đơn hàng của `store-b`. Việc client sửa ID trong đường dẫn hoặc body không được làm thay đổi phạm vi tin cậy.

~~~ts
// Pseudocode: middleware trước đó đã xác thực API key.
async function getOrder(request, response) {
  const auth = request.apiPrincipal;
  const order = await orders.findById(request.params.orderId);
  if (!order) return response.sendStatus(404);

  const sameTenant = order.tenantId === auth.tenantId;
  const canRead = auth.scopes.includes("orders:read");
  if (!sameTenant || !canRead) return response.sendStatus(403);

  return response.json(order);
}
~~~

Đây là ví dụ rút gọn; hệ thống thực tế còn cần kiểm tra principal đang hoạt động, chính sách sở hữu, trạng thái tài nguyên và các điều kiện nghiệp vụ. Một số API trả `404` thay vì `403` để tránh tiết lộ sự tồn tại của tài nguyên.

Scope của key nên đáp ứng **least privilege**:

| Hành động | Ví dụ scope | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Xem báo cáo | `reports:read` | Đúng tenant và đúng báo cáo được phép. |
| Gửi dữ liệu đo lường | `metrics:write` | Chỉ ghi vào nguồn dữ liệu/namespace được cấp. |
| Đọc trạng thái đơn hàng | `orders:read` | Quan hệ sở hữu đơn hàng, trạng thái tài khoản. |
| Tạo lệnh thanh toán | `payments:create` | Quyền trên nguồn tiền, hạn mức, nghiệp vụ, cơ chế phê duyệt. |
| Quản trị key | `keys:manage` | Kiểm soát cấp quyền, xác thực lại, phân tách trách nhiệm khi cần. |

Hạn chế theo IP, mạng riêng, môi trường hoặc quota có thể giúp giảm rủi ro nhưng là **lớp kiểm soát bổ sung**. Địa chỉ IP không phải bằng chứng danh tính đáng tin trong mọi trường hợp, đặc biệt khi qua NAT, proxy hoặc hạ tầng động.

## 8. Mối đe dọa, replay và giới hạn của API key

API key kiểu bearer có đặc điểm cốt lõi: **nếu secret bị lộ, attacker có thể gửi lại nó** khi còn hợp lệ. TLS ngăn một số kiểu nghe lén trên đường truyền, nhưng không giải quyết khóa lộ từ kho bí mật, mã nguồn, CI, log, proxy hoặc máy đã bị xâm nhập.

| Mối đe dọa | Ví dụ | Kiểm soát chính |
| --- | --- | --- |
| Rò rỉ khóa trong repo hoặc log | Khóa được commit lên Git hoặc ghi vào access log. | Secret scanning, redaction, thu hồi ngay, phát hành lại, quản lý secret. |
| Đoán hoặc dò key | Attacker thử nhiều chuỗi key. | CSPRNG, entropy cao, rate limiting, giám sát hành vi. |
| Replay sau khi bị lấy cắp | Attacker trình lại cùng bearer key trên máy khác. | Giới hạn thời hạn/scope, thu hồi, phát hiện bất thường; ký yêu cầu kèm nonce/timestamp nếu cần chống replay ở mức yêu cầu. |
| Phishing/social engineering | Người vận hành gửi secret cho trang hỗ trợ giả. | Quy trình cấp khóa, đào tạo, secret không bao giờ cần gửi lại cho support; thu hồi khi nghi lộ. |
| Lạm dụng key hợp lệ | Tích hợp gọi API quá nhanh hoặc ngoài mục đích. | Quota/rate limit theo principal, key, tenant; giám sát và chính sách quyền. |
| Chiếm máy chủ client | Attacker đọc biến môi trường hoặc bộ nhớ chứa key. | Cách ly runtime, quyền tối thiểu, secret manager, rotate/revoke, bảo vệ hạ tầng. |
| Quyền quá rộng | Key đọc dữ liệu toàn bộ tenant hoặc là quản trị viên mặc định. | Key riêng cho từng tích hợp, scope, ràng buộc tài nguyên, phê duyệt đặc quyền. |
| Khóa không được thu hồi | Tích hợp ngừng dùng nhưng key tồn tại nhiều năm. | Expiry, định kỳ rà soát, thống kê lần dùng cuối và cơ chế revoke. |

### 8.1. Vì sao chỉ thêm timestamp vào request chưa đủ?

Nếu bearer key vẫn được gửi nguyên văn và server chỉ kiểm tra timestamp không có bảo vệ tính toàn vẹn, attacker có khóa có thể tạo timestamp mới. Ngay cả chữ ký HMAC với timestamp vẫn có thể bị phát lại **trong cửa sổ thời gian cho phép** nếu không có cơ chế chống dùng lặp.

### 8.2. Khi cần ký yêu cầu

Với hệ thống cần ràng buộc yêu cầu với method, path, body và thời điểm, có thể chọn giao thức ký yêu cầu được thiết kế và kiểm thử kỹ:

~~~text
Client gửi:
  key_id, timestamp, nonce, body, signature

signature = HMAC(secret,
  canonical(method, path, query, body_hash, timestamp, nonce))

Server:
  1. Tra key_id và chính sách principal.
  2. Kiểm tra timestamp trong cửa sổ được phép.
  3. Tạo lại canonical request và kiểm tra HMAC.
  4. Từ chối nonce đã dùng, lưu nonce trong thời hạn phù hợp.
  5. Kiểm tra quyền và thực thi nghiệp vụ.
~~~

Ở mô hình này, phải thống nhất cách chuẩn hóa method, path, query, header, body; kiểm tra chữ ký an toàn; chống dùng lại nonce bằng kho trạng thái nhất quán; quản lý sai lệch đồng hồ; bảo vệ khóa phía client; và có **idempotency** cho thao tác có thể gửi lại vì lỗi mạng. Các thiếu sót về canonicalization, lưu nonce hoặc thao tác đồng thời có thể tạo lỗ hổng. Nên dùng giao thức/thư viện có thiết kế bảo mật rõ ràng thay vì tự tạo biến thể tùy hứng.

**Ký yêu cầu không làm secret đã bị đánh cắp trở nên an toàn.** Ai chiếm được secret vẫn có thể ký yêu cầu mới, trừ khi còn ràng buộc bằng một yếu tố/khóa được bảo vệ khác. Với những trường hợp cần chống sao chép credential, cân nhắc khóa bất đối xứng, mTLS hoặc token ràng buộc người gửi (*sender-constrained token*) phù hợp kiến trúc.

## 9. Vòng đời: tạo, phân phối, sử dụng, xoay vòng, thu hồi

~~~mermaid
stateDiagram-v2
    [*] --> Issued: Được cấp theo chính sách
    Issued --> Active: Client cấu hình thành công
    Active --> Rotating: Cần thay key
    Rotating --> Active: Key mới hoạt động
    Active --> Revoked: Thu hồi thủ công/sự cố
    Rotating --> Revoked: Thu hồi key cũ
    Active --> Expired: Hết hạn
    Issued --> Revoked: Hủy trước khi dùng
    Expired --> [*]
    Revoked --> [*]
~~~

**Phát hành:** người dùng có quyền tạo yêu cầu một key mới với principal, tenant, scope và thời hạn rõ ràng. Hệ thống sinh secret từ CSPRNG, lưu giá trị dẫn xuất và **chỉ hiển thị secret khi phát hành** qua kênh được bảo vệ. Nếu mất secret, quy trình an toàn thường là **cấp key khác**, không “xem lại” bản plaintext từ cơ sở dữ liệu.

**Phân phối:** đưa key vào secret manager của hệ thống tiêu thụ qua kênh có kiểm soát, tránh gửi trong chat, email hoặc tài liệu chia sẻ. Không cấp cùng một key cho hàng chục dịch vụ khiến khó quy trách nhiệm và khó thu hồi từng bên.

**Sử dụng:** ghi nhận `keyId`, principal, kết quả, nguồn truy cập, thời điểm và hành vi bất thường trong log phù hợp; không ghi secret. Có hạn mức theo key/principal/tenant, cảnh báo khi xuất hiện vị trí, workload hoặc mô hình sử dụng khác thường.

**Xoay vòng (rotation) chủ động:**

1. Tạo key mới có phạm vi và principal phù hợp; đặt thời hạn chồng lấn có kiểm soát khi cần.
2. Cấu hình bên gọi sử dụng key mới qua secret manager/deployment an toàn.
3. Xác nhận các yêu cầu của hệ thống đang dùng key mới; giám sát lỗi xác thực và `lastUsedAt` của key cũ.
4. Thu hồi key cũ ngay khi chuyển đổi hoàn tất, tránh để giai đoạn hai key hợp lệ kéo dài vô hạn.

**Khi nghi key bị lộ:** ưu tiên vô hiệu hóa hoặc hạn chế key ngay theo chính sách ứng phó sự cố, cấp key thay thế, tìm nơi lộ (repo, log, CI, runtime), kiểm tra hoạt động bất thường và khắc phục đường rò rỉ. Chỉ xóa commit khỏi nhánh hiện tại **không** làm key đã lộ an toàn trở lại: người khác có thể đã sao chép khóa.

**Hết hạn và thu hồi:** trường `expiresAt` phải được kiểm tra ở nơi thực hiện xác thực. `revokedAt` phải có hiệu lực theo cơ chế nhất quán trong toàn bộ cụm API. Nếu gateway cache trạng thái key, cần quy định TTL hoặc cơ chế invalidation phù hợp mục tiêu thu hồi; không được tuyên bố “thu hồi ngay lập tức” khi thực tế key vẫn còn được chấp nhận trong cache.

## 10. Chọn API key hay cơ chế khác?

API key hữu ích khi **dịch vụ đến dịch vụ** hoặc một tích hợp bên thứ ba có thể giữ bí mật, cần kiểm soát đơn giản, giới hạn scope và quản lý vòng đời rõ ràng. Nhưng nó không phù hợp để giải quyết mọi bài toán đăng nhập hoặc ủy quyền.

| Cơ chế | Điểm phù hợp | Hạn chế / lưu ý |
| --- | --- | --- |
| **Static bearer API key** | Tích hợp backend đơn giản, principal cố định, phạm vi hẹp. | Secret có thể bị sao chép; thường sống lâu hơn access token; cần rotation và revoke. |
| **OAuth 2.0 client credentials** | Máy-máy cần access token có thời hạn, scope/audience rõ, hệ sinh thái ủy quyền tập trung. | Vẫn cần bảo vệ client secret/private key; API phải xác minh token và quyền đúng cách. |
| **OAuth 2.0 authorization code + PKCE** | Ứng dụng truy cập tài nguyên thay mặt người dùng sau luồng ủy quyền. | Cần triển khai đúng redirect URI, state, PKCE, token lifecycle; không dùng API key chung thay sự đồng ý của người dùng. |
| **mTLS / chứng chỉ client** | Xác thực thiết bị/dịch vụ qua sở hữu khóa riêng trong TLS. | Cần quản lý CA, chứng chỉ, khóa, gia hạn và thu hồi; vẫn cần authorization. |
| **HMAC signed requests** | Ràng buộc request với nội dung, thời gian và nonce trong mô hình khóa chia sẻ. | Khó thiết kế canonicalization và chống replay; secret bị chiếm vẫn ký được yêu cầu mới. |
| **Passkey/WebAuthn** | Xác thực người dùng chống phishing theo origin/RP ID. | Chủ yếu cho xác thực tương tác; không thay trực tiếp cho credential máy-máy. |

Ví dụ: một trình duyệt gọi API riêng cho từng người dùng không nên được nhúng “master API key” để đọc mọi dữ liệu. Hệ thống phù hợp hơn với cơ chế xác thực/ủy quyền người dùng, token có phạm vi rõ và kiểm tra quyền trên từng tài nguyên. Với tích hợp backend cố định, API key riêng và scope hẹp có thể đủ khi các rủi ro đã được kiểm soát.

## 11. Ví dụ thiết kế: dịch vụ đồng bộ đơn hàng

Một doanh nghiệp có ứng dụng `sync-orders` chạy mỗi 5 phút và cần **chỉ đọc đơn hàng** từ API. Hệ thống có ba tenant: A, B và C.

**Thiết kế đề xuất:**

- Tạo principal riêng `svc-sync-orders-a` thuộc tenant A; không dùng key từ tài khoản quản trị.
- Phát hành một API key ngẫu nhiên với scope `orders:read`, giới hạn tenant A, thời hạn theo chính sách và ghi người/tổ chức chịu trách nhiệm.
- Lưu secret vào secret manager của job. Job gửi key qua HTTPS đến đúng API trong header đã quy ước.
- Gateway/API tra `keyId`, kiểm tra MAC, trạng thái, thời hạn và xác định principal; ứng dụng kiểm tra scope và tenant trên **từng đơn hàng**.
- Áp quota/rate limit cho principal hoặc key, ghi `keyId`, dấu thời gian, kết quả và thống kê sử dụng; loại bỏ secret khỏi log.
- Triển khai quy trình rotate có giai đoạn chuyển đổi ngắn, theo dõi lần sử dụng cuối và thu hồi key cũ.

Giả sử ai đó đoán được ID đơn hàng thuộc tenant B rồi gọi `GET /orders/<id-B>` bằng key của tenant A. API phải **từ chối** dù credential hợp lệ, vì principal chỉ có quyền trên tenant A. Đây là kiểm tra quyền đối tượng, độc lập với mức ngẫu nhiên của khóa.

Nếu key bị in vào log CI, đội vận hành cần coi đó là sự cố lộ credential: thu hồi/đổi khóa, kiểm tra các lần gọi phát sinh và sửa bước logging. Sửa tên key hoặc thay ký tự hiển thị trong dashboard không giải quyết bản sao đã lộ.

## 12. Các lỗi thiết kế thường gặp

| Ngộ nhận hoặc lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| “Key có tên khó đoán nên không cần ngẫu nhiên mạnh.” | Khóa dự đoán được có thể bị dò. | Sinh bằng CSPRNG, đủ entropy. |
| “API key giống password của người dùng.” | Lẫn lộn chủ thể, vòng đời và chính sách lưu trữ. | Thiết kế principal tích hợp, secret ngẫu nhiên, scope/expiry/revoke riêng. |
| “Có key là được gọi mọi endpoint.” | Privilege escalation và truy cập chéo tenant. | Xác thực riêng, phân quyền theo hành động và tài nguyên. |
| “Chỉ cần HTTPS là không thể bị lộ key.” | Repo, log, CI, máy khách vẫn có thể lộ. | Secret manager, logging hygiene, quét và rotate. |
| “Đưa key vào query cho tiện debug.” | URL có thể bị ghi và chia sẻ rộng. | Gửi theo header/giao thức phù hợp; chặn log credential. |
| “Dùng cùng một key cho mọi môi trường và dịch vụ.” | Sự cố ở một nơi mở quyền rộng; khó thu hồi từng bên. | Phân tách theo dịch vụ, tenant, môi trường, mục đích. |
| “Thêm timestamp là đã chống replay.” | Khóa bị lộ vẫn dùng lại hoặc tạo timestamp mới. | Chọn giao thức ký đúng, nonce, kiểm tra độ mới và giới hạn quyền. |
| “Đổi key trên dashboard là đủ.” | Key cũ vẫn có thể hợp lệ trong cache/instance khác. | Kiểm tra hiệu lực thu hồi trên toàn đường xác thực. |
| “Secret của app mobile là bí mật.” | Bản app phân phối cho người dùng có thể bị phân tích. | Không nhúng key đặc quyền vào client không tin cậy. |
| “Chỉ khóa người dùng là đủ thu hồi mọi key.” | API key gắn principal dịch vụ có thể tiếp tục hoạt động. | Định nghĩa vòng đời và quan hệ thu hồi rõ theo principal/key. |

## 13. Checklist khi thiết kế API key credential

Trước khi đưa một luồng sử dụng API key lên production, hãy xác minh:

1. **Danh tính:** key được gắn với principal nào, thuộc tenant nào, ai có quyền tạo và thu hồi?
2. **Bí mật:** secret được tạo bằng CSPRNG với entropy đủ cao và không được thiết kế từ dữ liệu có thể dự đoán?
3. **Lưu trữ:** server có tránh giữ plaintext không cần thiết, bảo vệ HMAC/hash và bí mật pepper thích hợp?
4. **Phân phối:** key được cấp qua kênh an toàn, đưa vào secret manager và không xuất hiện trong repo, URL, client bundle hoặc log?
5. **Xác minh:** mỗi request có kiểm tra đúng key, trạng thái thu hồi, thời hạn, ngữ cảnh issuer/môi trường và tình trạng principal?
6. **Quyền:** có scope hẹp và authorization trên từng hành động/tài nguyên/tenant?
7. **Lạm dụng:** có giới hạn tốc độ, quota, phát hiện bất thường và phản hồi lỗi tránh tiết lộ thông tin nhạy cảm?
8. **Replay:** có hiểu bearer key vẫn bị phát lại nếu lộ và cần cơ chế ký yêu cầu hoặc ràng buộc khóa khi mô hình rủi ro yêu cầu?
9. **Vòng đời:** có thời hạn, thống kê sử dụng, rotate, revoke, thu hồi tức thời ở mức chính sách thực sự đáp ứng và xử lý sự cố lộ key?
10. **Kiến trúc:** có chắc bên giữ secret là môi trường đủ tin cậy, và API key là cơ chế phù hợp hơn OAuth, mTLS hoặc xác thực người dùng?

**Kết luận:** API key là một credential hữu ích cho tích hợp API, nhưng bằng chứng nó cung cấp thường chỉ là **quyền sở hữu hoặc biết một secret đã gắn với principal**. Hệ thống an toàn phải bảo vệ toàn bộ vòng đời của secret, giới hạn quyền theo ngữ cảnh, chống lạm dụng, giám sát và thu hồi khi cần. Đặc biệt, **API key hợp lệ không đồng nghĩa mọi yêu cầu hợp lệ**, và bearer API key bị lộ có thể bị replay cho tới khi bị hạn chế hoặc vô hiệu hóa.
