# Key storage

## 1. Vì sao lưu trữ API key là một bài toán bảo mật?

**API key** thường là một bearer credential: bên nào có được giá trị bí mật hợp lệ đều có thể trình nó để gọi API dưới danh nghĩa principal đã được gắn với khóa. Vì vậy, nơi tạo, hiển thị, lưu, sao lưu, sử dụng và ghi log API key đều trở thành một phần của ranh giới tin cậy.

Một sự cố phổ biến là API key bị đưa vào mã nguồn, file cấu hình, log CI/CD, ảnh chụp màn hình hoặc lịch sử terminal. Khi đó, dù server xác minh khóa bằng thuật toán tốt, người khác vẫn có thể dùng bản sao của khóa cho đến khi khóa bị hạn chế hoặc thu hồi.

Thiết kế lưu trữ phải trả lời hai câu hỏi khác nhau:

1. **Dịch vụ phát hành API key cần lưu gì để xác minh khóa người gọi gửi lên?** Với khóa ngẫu nhiên entropy cao, server thường chỉ cần lưu giá trị dẫn xuất một chiều để so khớp; không cần lưu secret ở dạng đọc lại được.
2. **Ứng dụng khách cần lưu gì để gọi API của bên thứ ba?** Ứng dụng phải lấy lại secret để gửi trong request, nên cần lưu bí mật theo cách có thể giải mã hoặc lấy từ secret manager/HSM; hash một chiều không đáp ứng được nhu cầu này.

Hai vai trò có mục tiêu khác nhau. Nhầm lẫn chúng có thể dẫn tới lưu secret không cần thiết ở server phát hành, hoặc không thể vận hành tích hợp vì đã băm mất khóa mà client cần sử dụng.

## 2. Phân biệt key ID, secret và metadata

Một API key có thể có dạng minh họa:

~~~text
ak_live_<key-id>.<secret>
         |         |
         |         +-- Giá trị bí mật, chỉ hiển thị khi cấp
         +------------ Định danh để tra bản ghi, không cấp quyền một mình
~~~

- **Key ID:** dùng để tra cứu bản ghi nhanh, nhận diện khóa trong giao diện quản trị và log. Nó không phải secret và không được xem là bằng chứng xác thực.
- **Secret:** chuỗi ngẫu nhiên có entropy cao, là phần cần bảo vệ như mật khẩu/token bearer.
- **Metadata:** principal, tenant, scope, môi trường, người tạo, mục đích, ngày tạo, ngày hết hạn, trạng thái thu hồi và thời điểm dùng gần nhất.

Không nên lưu toàn bộ secret trong metadata, tên hiển thị hoặc trường ghi chú. Giao diện quản trị chỉ cần hiển thị key ID hoặc vài ký tự cuối để người vận hành phân biệt khóa. Những ký tự này không được dùng thay cho xác minh danh tính hoặc hỗ trợ khôi phục.

## 3. Sinh secret và hiển thị một lần

API key nên được sinh từ **cryptographically secure pseudorandom number generator (CSPRNG)**, không dùng timestamp, ID tăng dần, tên ứng dụng hoặc hàm ngẫu nhiên không dành cho mật mã.

Ví dụ Node.js:

~~~ts
import { randomBytes } from "node:crypto";

function generateApiKey() {
  const keyId = randomBytes(12).toString("base64url");
  const secret = randomBytes(32).toString("base64url");
  return {
    keyId,
    secret,
    presentedKey: "ak_live_" + keyId + "." + secret
  };
}
~~~

32 byte ngẫu nhiên tương đương 256 bit entropy trước khi mã hóa Base64URL. Độ dài chuỗi không tự tạo entropy; chất lượng phụ thuộc nguồn ngẫu nhiên. Tiền tố môi trường như `ak_live_` hỗ trợ nhận diện và quét secret, nhưng không phải một cơ chế bảo mật.

Quy trình phát hành nên:

1. Xác minh người yêu cầu có quyền tạo key cho principal/tenant tương ứng.
2. Chọn scope tối thiểu, mục đích, môi trường và thời hạn.
3. Sinh key ID và secret bằng CSPRNG.
4. Lưu metadata cùng giá trị xác minh một chiều ở phía server (nếu đây là API do mình phát hành).
5. Hiển thị secret **một lần** qua kênh được bảo vệ, cho phép người dùng sao chép ngay vào secret manager.
6. Không gửi lại secret qua email, log, thông báo hoặc chức năng “show key” sau này.

Nếu người dùng làm mất secret, quy trình đúng thường là tạo key mới và thu hồi key cũ. Không cần khôi phục plaintext từ database của hệ thống phát hành.

## 4. Lưu ở phía server phát hành: hash hay HMAC?

Khi server nhận API key, nó cần xác minh secret được trình có khớp với secret đã cấp không. Vì API key ngẫu nhiên có entropy cao, server có thể lưu **hash mật mã** hoặc **HMAC có khóa bí mật phía server** thay cho secret gốc.

### 4.1. Hash một chiều cho secret ngẫu nhiên

Server có thể lưu digest của secret ngẫu nhiên, chẳng hạn SHA-256, rồi tính digest của secret nhận được và so sánh. Đây là trường hợp khác với mật khẩu do người dùng tự chọn:

- Mật khẩu con người thường có entropy thấp; cần password hashing chậm, có salt như Argon2id để làm tăng chi phí đoán.
- API key sinh ngẫu nhiên với entropy cao không dễ bị vét cạn như mật khẩu; hash mật mã phù hợp có thể dùng làm verifier.

Không dùng quy tắc lưu API key ngẫu nhiên để thay cho quy tắc lưu mật khẩu. Cũng không nên dùng một hash nhanh cho secret có cấu trúc dễ đoán hoặc do con người tự chọn.

### 4.2. HMAC với pepper/secret phía server

Một lựa chọn khác là lưu HMAC của secret bằng khóa bí mật phía server (thường gọi là pepper hoặc verifier key). Khóa HMAC được lưu trong KMS/HSM hoặc secret manager, tách khỏi database chứa bản ghi API key.

Ưu điểm: nếu database bị sao chép nhưng pepper vẫn được bảo vệ, attacker không thể tự tính verifier cho các giá trị đoán được chỉ từ bản ghi database. HMAC cũng giúp quản lý phiên bản khóa xác minh.

Giới hạn: nếu cả database và pepper bị lộ, lợi ích bổ sung này mất đi. Pepper cần được bảo vệ, phân quyền truy cập, sao lưu/khôi phục có kiểm soát và xoay vòng theo kế hoạch. Không hard-code pepper trong source code hoặc đặt cùng bảng dữ liệu.

### 4.3. Bản ghi xác minh minh họa

| Trường | Mục đích |
| --- | --- |
| `keyId` | Tra cứu bản ghi mà không cần quét secret. |
| `secretMac` hoặc `secretHash` | Giá trị xác minh một chiều, không phải secret gốc. |
| `verifierKeyVersion` | Chọn đúng phiên bản pepper/HMAC key. |
| `principalId`, `tenantId` | Gắn key với đúng chủ thể và tổ chức. |
| `scopes`, `resourceConstraints` | Giới hạn quyền. |
| `createdAt`, `expiresAt`, `revokedAt` | Quản lý vòng đời. |
| `createdBy`, `purpose`, `environment` | Truy nguyên trách nhiệm và phạm vi sử dụng. |
| `lastUsedAt`, `lastUsedFrom` | Hỗ trợ giám sát; cần cân nhắc quyền riêng tư và độ chính xác của IP. |

Ví dụ cấu trúc dữ liệu ứng dụng:

~~~json
{
  "keyId": "base64url-key-id",
  "secretMac": "hex-hmac-digest",
  "verifierKeyVersion": "api-key-verifier-v3",
  "principalId": "svc-reporting",
  "tenantId": "tenant-a",
  "scopes": ["reports:read"],
  "createdAt": "2026-11-22T10:00:00Z",
  "expiresAt": "2027-02-22T10:00:00Z",
  "revokedAt": null
}
~~~

Không đưa secret plaintext vào bản ghi này. Cần bảo vệ quyền ghi vì attacker sửa principal, tenant, scope hoặc verifier digest có thể thay đổi quyền mà không cần biết secret gốc.

## 5. Ví dụ tạo và xác minh HMAC verifier

Ví dụ dưới đây minh họa phía **dịch vụ phát hành**. Secret được sinh ngẫu nhiên, chỉ trả cho người dùng lúc tạo. Database lưu HMAC digest và phiên bản pepper.

~~~ts
import {
  createHmac,
  randomBytes,
  timingSafeEqual
} from "node:crypto";

type IssuedKey = {
  keyId: string;
  presentedKey: string; // Chỉ trả về một lần khi cấp
  secretMacHex: string; // Chỉ lưu phía server
};

function macSecret(secret: string, pepper: Buffer): Buffer {
  return createHmac("sha256", pepper)
    .update("api-key-verifier-v1:", "utf8")
    .update(secret, "utf8")
    .digest();
}

function issueKey(pepper: Buffer): IssuedKey {
  const keyId = randomBytes(12).toString("base64url");
  const secret = randomBytes(32).toString("base64url");
  const secretMacHex = macSecret(secret, pepper).toString("hex");

  return {
    keyId,
    presentedKey: "ak_live_" + keyId + "." + secret,
    secretMacHex
  };
}

function verifySecret(
  presentedSecret: string,
  storedMacHex: string,
  pepper: Buffer
): boolean {
  const candidate = macSecret(presentedSecret, pepper);
  const stored = Buffer.from(storedMacHex, "hex");
  if (stored.length !== candidate.length) return false;
  return timingSafeEqual(candidate, stored);
}
~~~

Đây là phần lõi minh họa; hệ thống thực tế cần tra bản ghi theo key ID, xác minh định dạng/độ dài, trạng thái thu hồi, thời hạn, principal, tenant và scope. Khi so sánh digest, kiểm tra độ dài trước khi gọi hàm so sánh cố định thời gian. Không dùng phép so sánh chuỗi thông thường cho MAC nếu có thể làm lộ khác biệt thời gian.

Khi phát hành, cần lưu `secretMacHex` cùng phiên bản pepper trong bản ghi. Khi xác minh, server phải tải đúng pepper version từ kho bí mật, không nhận tên phiên bản do client tự chọn. Nếu không tải được pepper hoặc database không thể kiểm tra trạng thái, endpoint nhạy cảm nên từ chối theo nguyên tắc **fail closed**.

## 6. Lưu API key ở phía ứng dụng khách

Một ứng dụng backend gọi API của bên thứ ba cần sử dụng lại secret trong mỗi request. Vì vậy, ứng dụng tiêu thụ phải giữ secret ở một nơi có thể cấp cho workload được phép dùng.

Ưu tiên theo thứ tự phù hợp kiến trúc:

1. **Secret manager chuyên dụng:** dịch vụ quản lý bí mật có phân quyền theo workload, audit, version, rotation và khả năng cấp secret lúc chạy.
2. **KMS/HSM hoặc envelope encryption:** ứng dụng lưu ciphertext; khóa mã hóa dữ liệu (DEK) được bảo vệ bởi khóa gốc (KEK) trong KMS/HSM.
3. **Cơ chế secret của nền tảng chạy:** ví dụ secret store của orchestrator hoặc dịch vụ cloud, với RBAC và audit được cấu hình đúng.
4. **File cấu hình cục bộ có bảo vệ:** chỉ dùng khi môi trường không có lựa chọn tốt hơn; giới hạn ACL, quyền đọc, backup, thời hạn và người vận hành.

Không nên lưu secret trong source code, file cấu hình được commit, frontend bundle, URL, wiki, ticket, chat hoặc biến môi trường được ghi lại trong log. Biến môi trường có thể thuận tiện cho ứng dụng, nhưng vẫn có thể bị đọc qua process inspection, dump, crash report hoặc quyền quản trị runtime; cần bảo vệ môi trường chạy và giới hạn ai có quyền xem.

### 6.1. Envelope encryption khi phải lưu ciphertext

Nếu ứng dụng phải lưu API key có thể giải mã để gọi upstream, dùng envelope encryption:

~~~mermaid
flowchart TD
    K["KMS/HSM giữ KEK"] --> W["Mở hoặc tạo DEK"]
    W --> E["DEK mã hóa API key -> ciphertext"]
    E --> DB["Database lưu ciphertext + wrapped DEK + metadata"]
    DB --> R["Workload được phép đọc bản ghi"]
    R --> K
    K --> D["KMS unwrap DEK theo quyền"]
    D --> P["Giải mã secret trong bộ nhớ tiến trình"]
    P --> API["Gọi upstream qua TLS"]
~~~

Quy trình cần:

- Khóa KEK không nằm trong cùng database với ciphertext.
- Mỗi workload chỉ được decrypt những secret mà nó cần.
- Gắn encryption context/AAD với secret ID, tenant và mục đích để ngăn ciphertext bị tráo giữa bản ghi hoặc tenant.
- Có phiên bản thuật toán và khóa để hỗ trợ rotation/re-encryption.
- Giới hạn thời gian secret tồn tại trong bộ nhớ, tránh log hoặc ghi ra file tạm.
- Audit thao tác decrypt, nhưng log chỉ metadata cần thiết chứ không log plaintext.

Mã hóa lưu trữ không loại bỏ rủi ro khi ứng dụng đang sử dụng secret. Nếu attacker chiếm tiến trình có quyền decrypt, họ có thể lấy secret ở bộ nhớ hoặc gọi KMS dưới danh nghĩa workload. Vì vậy, phân quyền runtime và bảo vệ endpoint vẫn rất quan trọng.

## 7. Quản lý quyền truy cập vào kho secret

Không phải mọi nhân viên hoặc service đều cần đọc mọi API key. Áp dụng **least privilege** ở cả lớp quản trị và runtime:

| Đối tượng | Quyền nên có |
| --- | --- |
| Người tạo key | Tạo khóa cho principal/tenant được phép; xem secret đúng một lần lúc cấp. |
| Quản trị tích hợp | Xem metadata, scope và trạng thái; thu hồi hoặc rotate theo quy trình. |
| Workload tiêu thụ | Đọc đúng secret cần thiết cho chức năng của workload. |
| Nhân viên hỗ trợ | Xem key ID và metadata hạn chế; không xem plaintext secret. |
| Security/audit | Xem sự kiện, người cấp, thời điểm và hoạt động truy cập; không cần secret. |
| Database operator | Quản lý database nhưng không mặc nhiên có quyền truy cập pepper/KEK. |

Tách quyền giữa người có thể tạo key, người phê duyệt quyền cao và người vận hành hệ thống khi rủi ro yêu cầu. Với API key có scope nhạy cảm như thanh toán hoặc quản trị, nên có step-up, phê duyệt độc lập, thời hạn ngắn hơn hoặc ràng buộc môi trường.

Secret manager cần kiểm soát danh tính workload. Tránh một credential quản trị chung được chia sẻ cho nhiều máy; nếu một máy bị chiếm, mọi secret dùng chung có thể bị lộ và khó xác định nguồn sự cố.

## 8. Không để API key lọt vào log, telemetry và bản sao lưu

Các đường lộ thường không nằm trong database chính:

- HTTP access log ghi toàn bộ header `Authorization` hoặc `X-API-Key`.
- Debug log in request object, exception hoặc cấu hình.
- APM, tracing, crash report và error analytics thu thập header/body.
- CI/CD log in biến môi trường hoặc command line.
- Browser history, URL, proxy, shell history và file tạm.
- Ảnh chụp dashboard hoặc ticket hỗ trợ chứa secret.
- Backup database, snapshot volume và bản dump được lưu ở tài khoản khác.

Kiểm soát nên gồm:

1. Redact các header và field chứa credential ở gateway, proxy, application logger và APM.
2. Không log request/response nguyên bản khi có khả năng chứa secret; dùng allowlist field an toàn.
3. Quét secret trong repository và pipeline; khi phát hiện key thật, thu hồi/rotate thay vì chỉ xóa chuỗi khỏi commit mới.
4. Kiểm soát truy cập log, backup và snapshot; mã hóa, audit, thời hạn lưu giữ và quy trình xóa bản sao.
5. Không đưa secret vào command line vì có thể lộ qua process list hoặc shell history; dùng secret injection phù hợp.
6. Kiểm tra redirect của HTTP client và không chuyển header xác thực sang origin khác.

Che secret trên giao diện sau khi tạo chỉ giúp giảm rủi ro nhìn thấy; nó không thu hồi những bản sao đã được copy hoặc ghi ở nơi khác.

## 9. Rotation, versioning và thu hồi

Key storage phải hỗ trợ thay khóa mà không tạo khoảng trống bảo mật hoặc làm dịch vụ ngừng hoạt động ngoài kế hoạch.

~~~mermaid
stateDiagram-v2
    [*] --> Created: Sinh secret và lưu verifier
    Created --> Active: Phân phối an toàn
    Active --> Rotating: Tạo key mới
    Rotating --> Active: Workload đã chuyển
    Active --> Revoked: Thu hồi
    Rotating --> Revoked: Thu hồi key cũ
    Active --> Expired: Hết hạn
    Expired --> [*]
    Revoked --> [*]
~~~

Quy trình rotation có kiểm soát:

1. Tạo key mới, metadata và scope phù hợp; phân phối qua secret manager.
2. Cấu hình workload dùng version mới; xác nhận kết nối thành công.
3. Theo dõi lần sử dụng cuối của key cũ và lỗi xác thực.
4. Thu hồi key cũ ngay khi đã chuyển đổi xong; không giữ hai key hợp lệ vô thời hạn.
5. Cập nhật tài liệu, chủ sở hữu và lịch rotation tiếp theo.

Nếu key bị lộ, **thu hồi trước rồi điều tra và cấp thay thế** theo quy trình ứng phó. Tìm nơi lộ trong repo, log, CI, backup, máy chạy và ticket; kiểm tra các request bất thường; giới hạn quyền hoặc khóa principal khi cần.

Nếu dùng HMAC pepper hoặc KEK, phải quản lý phiên bản riêng:

- Verifier record lưu phiên bản pepper đã dùng để tạo MAC.
- Server chỉ tải phiên bản được phép từ secret manager/KMS.
- Rotation pepper có thể cần giữ nhiều phiên bản trong giai đoạn chuyển tiếp hoặc tính lại verifier nếu có secret plaintext ở nguồn tin cậy; không thể tính HMAC mới từ digest cũ.
- Rotation KEK có thể rewrap DEK mà không cần giải mã toàn bộ API key, tùy thiết kế envelope encryption.
- Thu hồi key API và rotation khóa mã hóa là hai quy trình khác nhau; không nhầm một việc với việc còn lại.

## 10. Backup, restore và tính sẵn sàng

Database metadata, verifier HMAC, ciphertext, wrapped DEK và secret manager có yêu cầu backup khác nhau:

- **Verifier phía server:** cần backup database và bảo đảm pepper version còn truy cập được để xác minh các key đang hoạt động.
- **Secret client dạng ciphertext:** cần backup ciphertext, wrapped DEK và metadata; đồng thời bảo đảm KMS/KEK có kế hoạch phục hồi và quyền decrypt được kiểm soát.
- **Secret manager:** cần dự phòng vùng/region hoặc quy trình khôi phục phù hợp, nhưng không tạo bản sao plaintext tùy tiện.
- **Trạng thái thu hồi:** restore snapshot cũ không được làm sống lại key đã bị revoke. Cần lưu/đồng bộ trạng thái thu hồi hoặc đối chiếu nhật ký thay đổi sau thời điểm backup.

Kiểm thử restore phải bao gồm việc xác minh một key đã thu hồi vẫn bị từ chối. Nếu sau khi khôi phục backup cũ, key bị lộ trước đó lại hoạt động, quy trình backup/restore đã phá vỡ bảo đảm bảo mật.

## 11. Ví dụ kiến trúc: API key gọi dịch vụ thanh toán

Một backend thương mại điện tử cần dùng API key để gọi nhà cung cấp thanh toán.

**Ở nhà cung cấp (issuer/verifier):**

- Sinh secret ngẫu nhiên và key ID.
- Lưu HMAC verifier cùng metadata principal, merchant ID, scope, expiry và revoke state.
- Chỉ hiển thị secret một lần khi cấp.
- Mỗi request được xác thực, kiểm tra quyền trên merchant/resource, hạn mức và trạng thái key.

**Ở ứng dụng thương mại điện tử (consumer):**

- Lưu secret trong secret manager theo workload production.
- Chỉ service thanh toán được phép đọc secret; nhân viên vận hành chỉ xem metadata.
- Lấy secret lúc chạy, gửi qua HTTPS theo header nhà cung cấp quy định.
- Redact header khỏi log và tracing.
- Rotation bằng cách tạo key mới, deploy secret version mới, kiểm tra request rồi thu hồi key cũ.

~~~text
Secret manager
      |
      | cấp secret cho workload có identity hợp lệ
      v
Payment service
      |
      | HTTPS + API key trong header
      v
Payment provider
      |
      | key ID -> verifier record -> principal/merchant/scope
      v
Authentication -> Authorization -> Business rules -> Audit
~~~

Nếu backend bị chiếm và attacker đọc được secret từ bộ nhớ, HMAC verifier ở phía nhà cung cấp không ngăn attacker sử dụng khóa. Khi đó cần thu hồi/rotate, bảo vệ runtime, giới hạn scope, hạn mức và giám sát. Lưu verifier một chiều bảo vệ database phía issuer; secret manager bảo vệ bản secret cần dùng ở consumer. Hai lớp giải quyết hai rủi ro khác nhau.

## 12. Những lỗi lưu trữ thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Lưu secret plaintext trong database phát hành | Lộ database kéo theo toàn bộ key có thể dùng ngay. | Lưu hash/HMAC verifier với entropy cao; chỉ hiển thị secret lúc cấp. |
| Lưu pepper cạnh database | Attacker lấy cả verifier và pepper. | Tách pepper vào KMS/HSM/secret manager, phân quyền riêng. |
| Dùng hash nhanh cho password do người dùng chọn | Dễ bị đoán ngoại tuyến. | Dùng password hashing chậm có salt; phân biệt password với API key ngẫu nhiên. |
| Chỉ lưu hash ở consumer cần gọi upstream | Không thể khôi phục secret để gửi request. | Lưu ciphertext bằng envelope encryption hoặc dùng secret manager. |
| Nhúng API key vào frontend hoặc source code | Người dùng hoặc attacker lấy được key. | Dùng backend proxy/ủy quyền người dùng và secret manager. |
| Ghi key vào URL/log/tracing | Secret lan sang nhiều hệ thống. | Header đúng giao thức, redaction và allowlist logging. |
| Dùng một key chung cho nhiều service | Khó xác định nguồn lộ và thu hồi riêng. | Key riêng theo workload, tenant, môi trường và mục đích. |
| Cho nhân viên hỗ trợ xem plaintext key | Mở rộng số người có thể lấy secret. | Hiển thị metadata/key ID; rotate khi mất secret. |
| Rotation nhưng không thu hồi key cũ | Cửa sổ tấn công kéo dài. | Theo dõi chuyển đổi và revoke theo deadline. |
| Restore backup làm sống lại key đã thu hồi | Credential bị lộ tiếp tục hoạt động. | Đồng bộ trạng thái revoke và kiểm thử restore. |

## 13. Checklist thiết kế key storage

Trước khi đưa API key vào production, hãy kiểm tra:

1. Đây là hệ thống **phát hành/xác minh key** hay **ứng dụng tiêu thụ key**? Nhu cầu lưu trữ đã được phân biệt rõ chưa?
2. Secret có được sinh bằng CSPRNG với entropy đủ cao không?
3. Secret chỉ hiển thị một lần, có key ID riêng và metadata không chứa plaintext không?
4. Issuer có lưu verifier một chiều phù hợp (hash/HMAC) thay vì secret có thể đọc lại không?
5. Pepper/HMAC key có nằm ngoài database, được quản lý phiên bản và phân quyền qua KMS/HSM/secret manager không?
6. Consumer có lưu secret trong vault hoặc envelope encryption, với quyền đọc theo workload không?
7. Runtime có tránh log, URL, command line, dump, telemetry và file tạm chứa secret không?
8. Có least privilege, tách quyền tạo/duyệt/đọc secret và audit thao tác decrypt không?
9. Có expiry, rotation, revoke, cảnh báo sử dụng bất thường và quy trình xử lý lộ key không?
10. Backup/restore có giữ được trạng thái revoke và khả năng truy cập pepper/KEK mà không làm sống lại key cũ không?
11. Scope, tenant, principal và môi trường có được kiểm tra sau khi key được xác minh không?
12. Khi secret manager/KMS/database không khả dụng, endpoint nhạy cảm có fail closed và có quy trình khôi phục không?

**Kết luận:** Lưu trữ API key an toàn bắt đầu bằng việc xác định hệ thống đang phát hành hay đang tiêu thụ khóa. Issuer thường chỉ cần lưu verifier một chiều cho secret ngẫu nhiên và bảo vệ pepper tách biệt; consumer cần một kho bí mật hoặc ciphertext được mã hóa để lấy secret khi gọi upstream. Cả hai phía đều phải kiểm soát quyền truy cập, log, backup, rotation và thu hồi. Một API key chỉ an toàn khi toàn bộ nơi tạo, lưu, sử dụng và vận hành nó được bảo vệ theo đúng vai trò.
