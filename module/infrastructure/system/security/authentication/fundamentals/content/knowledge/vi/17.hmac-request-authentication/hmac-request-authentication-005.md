# Timestamp và nonce

## 1. Vì sao HMAC request authentication cần timestamp và nonce?

**HMAC request authentication** cho phép client chứng minh một request được tạo bởi bên đang kiểm soát secret đã chia sẻ với server. Client tính mã xác thực thông điệp (MAC) trên dữ liệu request; server tính lại MAC bằng secret tương ứng và so sánh. Nếu MAC hợp lệ, server có căn cứ tin rằng nội dung được ký đã được tạo bởi một bên có khả năng sử dụng khóa.

Tuy nhiên, một request có MAC hợp lệ vẫn có thể bị kẻ tấn công ghi lại rồi gửi lại. HMAC kiểm tra **tính toàn vẹn và tính xác thực của nội dung đã ký**; bản thân HMAC không biết request này mới hay đã được chấp nhận trước đó.

Hai thành phần thường được dùng để xử lý vấn đề này:

- **Timestamp:** cho biết thời điểm client tạo request, giúp server giới hạn cửa sổ thời gian chấp nhận.
- **Nonce (number used once):** giá trị dùng một lần cho từng request hoặc từng lần thử, giúp server nhận biết một thông điệp đã được sử dụng trước đó.

Hai giá trị này phải được đưa vào dữ liệu được ký. Nếu attacker sửa timestamp hoặc nonce mà chữ ký không bao phủ các trường đó, họ có thể thay giá trị để né kiểm tra freshness.

| Thành phần | Câu hỏi được trả lời | Giới hạn |
| --- | --- | --- |
| HMAC | Request có được tạo bởi bên kiểm soát secret và nội dung có bị sửa không? | Không tự phát hiện request bị gửi lại. |
| Timestamp | Request có nằm trong cửa sổ thời gian được phép không? | Một request vẫn có thể bị phát lại trong cửa sổ đó. |
| Nonce | Request này đã được chấp nhận trước đó chưa? | Cần lưu trạng thái và kiểm tra dùng một lần một cách nguyên tử. |
| Idempotency key | Retry cùng một thao tác nghiệp vụ có tránh tạo tác động trùng không? | Không thay authentication hoặc replay protection. |

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, timestamp và nonce là hai yếu tố quan trọng để phòng chống replay trong xác thực request máy-máy. Chúng phải được thiết kế cùng canonicalization, quản lý khóa, authorization, đồng hồ hệ thống và trạng thái dùng một lần.

## 2. Mô hình một request được ký

Một API có thể định nghĩa các header minh họa:

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.test
X-API-Key-Id: key_7f21
X-Request-Timestamp: 1795341600
X-Request-Nonce: 4x2k...base64url-random...
X-Request-Signature: <base64url-hmac>
Content-Type: application/json

{"amount":250000,"currency":"VND","recipient":"merchant-42"}
~~~

Đây là **quy ước minh họa do ứng dụng tự định nghĩa**, không phải tên header hoặc chuẩn giao thức phổ quát. Hợp đồng thực tế cần xác định chính xác định dạng timestamp, nonce, chữ ký, cách canonicalize và phạm vi request được ký.

Một transcript có thể bao gồm:

~~~text
request_signature = HMAC-SHA256(
  secret,
  canonical(
    protocol_version,
    key_id,
    audience,
    HTTP_method,
    raw_path_and_query,
    content_type,
    body_hash,
    timestamp,
    nonce
  )
)
~~~

Trong đó:

- `protocol_version` ngăn diễn giải nhầm giữa các phiên bản quy tắc ký.
- `key_id` giúp server tra khóa đúng; nó không phải secret nhưng cần được ràng buộc vào chữ ký.
- `audience` xác định dịch vụ nhận request, giúp hạn chế chuyển chữ ký sang API khác.
- Method, path và query ràng buộc chữ ký với thao tác và endpoint cụ thể.
- `body_hash` ràng buộc chữ ký với đúng nội dung body.
- Timestamp và nonce cung cấp freshness và khả năng phát hiện dùng lại.

**Không ký riêng timestamp và nonce rồi bỏ qua phần còn lại của request.** Nếu body hoặc path không được ký, attacker có thể giữ nguyên chữ ký nhưng thay đổi số tiền, người nhận hoặc endpoint.

## 3. Timestamp: giới hạn tuổi của request

Timestamp thường biểu diễn thời điểm client tạo request theo Unix time (số giây hoặc mili giây kể từ epoch UTC). Server dùng đồng hồ của mình để kiểm tra request có đủ mới hay không.

Ví dụ, server chấp nhận sai lệch tối đa 300 giây:

~~~text
server_now = thời gian hiện tại của server (giây)
request_time = timestamp đã được ký trong request

accept_time = abs(server_now - request_time) <= 300
~~~

Con số 300 giây chỉ là ví dụ. Cửa sổ thực tế phải cân bằng giữa sai lệch đồng hồ, độ trễ mạng, thời gian xử lý và mức rủi ro. Cửa sổ càng rộng, request cũ càng có thời gian bị phát lại.

### 3.1. Timestamp phải được xác thực

Server chỉ được dùng timestamp sau khi kiểm tra rằng nó nằm trong dữ liệu HMAC hợp lệ. Nếu timestamp không được ký, attacker có thể thay timestamp cũ thành thời điểm hiện tại rồi gửi lại request.

Trình tự xử lý thường là:

1. Parse timestamp theo định dạng cố định, giới hạn độ dài và loại bỏ cách biểu diễn nhập nhằng.
2. Tra key ID và lấy secret còn hiệu lực.
3. Tạo lại canonical request từ dữ liệu nhận thực tế.
4. Xác minh HMAC bao gồm timestamp.
5. So sánh timestamp đã xác thực với đồng hồ server.
6. Chỉ tiếp tục nếu timestamp nằm trong cửa sổ chấp nhận.

Một số hệ thống có thể kiểm tra định dạng và giới hạn sơ bộ trước bước xác minh HMAC để giảm tải, nhưng không được xem timestamp do client gửi là thời gian đáng tin cho đến khi chữ ký hợp lệ.

### 3.2. Chọn đơn vị và định dạng thống nhất

Các lỗi thường gặp:

- Client gửi mili giây, server hiểu là giây, khiến request bị coi là ở tương lai rất xa.
- Một node làm tròn timestamp, node khác giữ phần mili giây.
- Dùng chuỗi thời gian có timezone khác nhau nhưng canonicalization không thống nhất.
- Chấp nhận nhiều định dạng số hoặc ký hiệu khoa học, tạo ra nhiều cách diễn giải cùng một giá trị.

Nên quy định rõ một định dạng duy nhất, ví dụ số nguyên Unix time tính bằng giây, không dấu, không phần thập phân. Cả hai phía phải ký và xác minh cùng chuỗi byte đã quy định. Nếu dùng RFC 3339, cần chuẩn hóa chính xác timezone và độ chính xác trước khi ký.

### 3.3. Đồng bộ đồng hồ

Timestamp chỉ hữu ích nếu đồng hồ các hệ thống đủ gần nhau. Client có thể chạy trên máy ảo, container, thiết bị di động hoặc môi trường bị sleep; server có thể có nhiều node và vùng địa lý.

Biện pháp vận hành:

- Đồng bộ đồng hồ máy chủ bằng nguồn thời gian đáng tin cậy, theo dõi độ lệch và cảnh báo khi vượt ngưỡng.
- Theo dõi sai lệch đồng hồ client qua lỗi xác thực, nhưng không tự động nới cửa sổ vô hạn cho từng client.
- Dùng cửa sổ vừa đủ với độ trễ thực tế; tránh cửa sổ quá lớn chỉ để che vấn đề đồng bộ.
- Dùng đồng hồ wall-clock đã đồng bộ để so timestamp tuyệt đối; đồng hồ monotonic phù hợp đo khoảng thời gian trong một tiến trình, không thay cho Unix timestamp giữa các máy.
- Xử lý trường hợp server clock nhảy lùi/nhảy tiến và đảm bảo các node có chính sách nhất quán.

Nếu một request đến quá sớm hoặc quá muộn, server nên từ chối với phản hồi chung và log mã lỗi nội bộ đủ để điều tra. Không tiết lộ secret, expected MAC hoặc dữ liệu xác thực nhạy cảm.

## 4. Nonce: nhận biết request đã được dùng

Nonce là giá trị dùng một lần trong phạm vi giao thức. Với HMAC request authentication, client thường tạo nonce ngẫu nhiên cho mỗi request, đưa nonce vào transcript được ký và gửi nó cùng request.

Ví dụ Node.js:

~~~ts
import { randomBytes } from "node:crypto";

const nonce = randomBytes(32).toString("base64url");
// 32 byte ngẫu nhiên = 256 bit entropy trước khi mã hóa.
~~~

Nonce nên được tạo bằng CSPRNG. Không dùng timestamp, số tăng dần dễ đoán, tên máy, request body hash đơn thuần hoặc `Math.random()` làm nonce bảo mật.

### 4.1. Nonce cần duy nhất trong phạm vi nào?

Một lựa chọn phổ biến là yêu cầu nonce duy nhất theo key ID:

~~~text
UNIQUE(key_id, nonce)
~~~

Khi một key ký nhiều request, nonce không được lặp lại trong thời gian server còn chấp nhận request mang timestamp tương ứng. Có thể chọn phạm vi rộng hơn nếu nhiều key của cùng một principal chia sẻ không gian nonce; điều quan trọng là phạm vi phải được định nghĩa rõ và được áp dụng nhất quán ở mọi node.

Nếu chỉ kiểm tra nonce theo endpoint, một request bị ký cho endpoint A có thể được phát lại ở endpoint B nếu phần audience/path không được ràng buộc đúng. Ràng buộc nonce theo key ID trên toàn bộ phạm vi API thường dễ suy luận và an toàn hơn, miễn là hệ thống chia sẻ trạng thái phù hợp.

### 4.2. Nonce phải được ký

Nonce phải nằm trong canonical request. Nếu không, attacker có thể lấy một request đã ký, thay nonce bằng giá trị chưa từng dùng và gửi lại mà HMAC vẫn hợp lệ.

Tương tự, key ID, audience, timestamp, method, path, query và body hash cũng cần được ràng buộc theo đúng giao thức. Trường nào ảnh hưởng tới việc xác thực hoặc xử lý request thì phải được ký hoặc lấy từ ngữ cảnh tin cậy phía server.

### 4.3. Nonce ngẫu nhiên không tự chống replay

Chỉ sinh nonce mới ở client là chưa đủ. Server phải ghi nhận nonce đã chấp nhận và từ chối lần xuất hiện tiếp theo. Nếu server không lưu trạng thái, nó không thể biết nonce đã được dùng.

Với request ký bằng HMAC, nonce thường do client sinh. Một số giao thức challenge–response lại để server sinh challenge/nonce. Hai mô hình có thể cùng chống replay nhưng bên tạo giá trị và cách ràng buộc flow khác nhau; cần theo thiết kế giao thức cụ thể.

## 5. Kết hợp timestamp và nonce

Timestamp và nonce giải quyết hai phần bổ sung cho nhau:

- Timestamp giới hạn **khoảng thời gian** request có thể được chấp nhận.
- Nonce giúp phát hiện **cùng một request/bằng chứng** đã được chấp nhận trước đó.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as API server
    participant R as Replay store
    C->>C: Sinh timestamp và nonce mới
    C->>C: Ký method/path/body/timestamp/nonce
    C->>S: Request + key ID + timestamp + nonce + MAC
    S->>S: Tra key, canonicalize và xác minh MAC
    S->>S: Kiểm tra timestamp với server clock
    S->>R: Insert (key ID, nonce) nếu chưa tồn tại
    alt Nonce mới và request còn hạn
        R-->>S: Insert thành công
        S->>S: Kiểm tra principal, scope và quyền
        S-->>C: Xử lý request
    else Timestamp quá hạn hoặc nonce đã dùng
        R-->>S: Từ chối
        S-->>C: Authentication failed
    end
~~~

Ví dụ:

~~~text
Request A:
  timestamp = 10:00:00
  nonce = N1
  MAC = HMAC(secret, request + 10:00:00 + N1)

Server xác minh MAC, timestamp và ghi N1 vào replay store.

Attacker gửi lại nguyên Request A:
  MAC vẫn đúng
  timestamp có thể vẫn nằm trong cửa sổ
  nonce N1 đã tồn tại -> từ chối

Attacker sửa timestamp hoặc nonce:
  transcript thay đổi -> MAC không còn đúng -> từ chối
~~~

Nếu timestamp hết cửa sổ, server có thể từ chối trước khi tra replay store. Nếu request còn trong cửa sổ nhưng nonce đã được tiêu thụ, server phải từ chối dù HMAC đúng.

## 6. Lưu trạng thái chống replay và tính nguyên tử

Server cần một replay store để ghi nhận các nonce đã được chấp nhận. Có thể dùng database có unique constraint, Redis với thao tác set-if-absent hoặc một kho trạng thái phân tán phù hợp.

Một bản ghi khái niệm:

| Trường | Ý nghĩa |
| --- | --- |
| `keyId` | Key ID đã ký request. |
| `nonce` | Nonce của request. |
| `acceptedAt` | Thời điểm server chấp nhận. |
| `expiresAt` | Thời điểm có thể xóa bản ghi mà không mở lại cửa sổ replay. |
| `requestId` | Mã tương quan để log/điều tra, không phải secret. |

Điểm bắt buộc là thao tác **kiểm tra chưa tồn tại và ghi nhận phải nguyên tử**. Mô hình sai:

~~~text
if not exists(keyId, nonce):
    insert(keyId, nonce)
    accept()
~~~

Hai request đồng thời có thể cùng thấy nonce chưa tồn tại rồi cùng được chấp nhận. Mô hình đúng phải dựa trên một thao tác nguyên tử như:

~~~text
insert-if-absent(keyId, nonce, expiresAt)
  -> success: request đầu tiên chiếm nonce
  -> duplicate: nonce đã được dùng, từ chối
~~~

Trong SQL, có thể dùng unique index trên key_id và nonce rồi xử lý lỗi duplicate key. Với Redis, có thể dùng lệnh SET có điều kiện NX và TTL. Cần kiểm tra đặc tính nhất quán và độ bền của kho lưu trữ được chọn; không giả định một cache eventual-consistent luôn đủ để chống replay trên nhiều region.

### 6.1. TTL phải bao phủ cửa sổ chấp nhận

Giả sử server chấp nhận timestamp trong khoảng ±W giây. Một request có timestamp ở tương lai gần vẫn có thể được chấp nhận trong một khoảng thời gian dài hơn kể từ lần đầu nó đến. Do đó, không nên đặt TTL replay record cố định quá ngắn tính từ thời điểm nhận request.

Một cách tính an toàn về khái niệm:

~~~text
replay_record_expires_at >= request_timestamp + allowed_window + safety_margin
~~~

Trong đó safety margin bao gồm độ lệch đồng hồ và biên vận hành được chính sách cho phép. Nếu bản ghi nonce bị xóa trong khi timestamp của request vẫn còn nằm trong cửa sổ chấp nhận, cùng request có thể được phát lại và được nhận lần nữa.

### 6.2. Không để kho replay thành điểm bỏ qua kiểm tra

Nếu replay store không khả dụng, server không thể xác định nonce đã dùng hay chưa. Với endpoint nhạy cảm, nên **fail closed**: từ chối tạm thời thay vì bỏ qua chống replay. Có thể dùng nhiều node hoặc vùng dự phòng, nhưng mọi node xác minh cùng credential phải chia sẻ trạng thái chống lặp theo chính sách nhất quán.

## 7. Trình tự xử lý phía server

Một pipeline tham khảo:

1. Kiểm tra kích thước và định dạng header; từ chối request có trường thiếu, quá dài hoặc biểu diễn không hợp lệ.
2. Tra key ID và kiểm tra key còn hoạt động, đúng môi trường và audience.
3. Parse timestamp theo định dạng cố định; kiểm tra phạm vi giá trị.
4. Tạo canonical request từ method, authority/audience, raw path/query, body bytes hoặc body hash và các header được quy định.
5. Tính lại HMAC và so sánh theo cách không để lộ khác biệt timing.
6. Kiểm tra timestamp đã được xác thực có nằm trong cửa sổ cho phép so với đồng hồ server không.
7. Atomically claim nonce trong replay store với TTL đủ dài.
8. Ánh xạ key sang principal; kiểm tra tenant, scope, trạng thái tài khoản và authorization trên tài nguyên/hành động.
9. Thực hiện nghiệp vụ, áp dụng idempotency nếu cần và ghi audit event không chứa secret.

Một số hệ thống có thể tra key ID trước khi parse timestamp để lấy verifier; một số kiểm tra định dạng trước để giảm tải. Thứ tự chi tiết có thể khác, nhưng không được thực hiện nghiệp vụ trước khi xác minh MAC, freshness, nonce và quyền.

## 8. Ví dụ TypeScript: tạo request có timestamp và nonce

Đoạn mã dưới đây minh họa một client backend tạo request. Quy ước canonicalization là ví dụ riêng của ứng dụng; hai phía phải triển khai giống hệt và kiểm thử bằng test vector chung.

~~~ts
import {
  createHash,
  createHmac,
  randomBytes
} from "node:crypto";

function encodeFields(parts: (string | Buffer)[]): Buffer {
  const chunks: Buffer[] = [];

  for (const part of parts) {
    const value = Buffer.isBuffer(part)
      ? part
      : Buffer.from(part, "utf8");
    const length = Buffer.alloc(4);
    length.writeUInt32BE(value.length, 0);
    chunks.push(length, value);
  }

  return Buffer.concat(chunks);
}

function signRequest(input: {
  keyId: string;
  secret: Buffer;
  audience: string;
  method: string;
  rawTarget: string;
  contentType: string;
  body: Buffer;
}) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const nonce = randomBytes(32).toString("base64url");
  const bodyHash = createHash("sha256").update(input.body).digest();

  const canonical = encodeFields([
    "hmac-request-v1",
    input.keyId,
    input.audience,
    input.method.toUpperCase(),
    input.rawTarget,
    input.contentType,
    bodyHash,
    timestamp,
    nonce
  ]);

  const signature = createHmac("sha256", input.secret)
    .update(canonical)
    .digest("base64url");

  return {
    timestamp,
    nonce,
    signature
  };
}
~~~

Điểm cần giữ nhất quán:

- `rawTarget` phải đúng chuỗi path/query thực sự gửi; không để proxy hoặc client tự chuẩn hóa khác nhau sau khi ký.
- `bodyHash` phải được tính trên đúng bytes gửi đi. Nếu serialize JSON sau khi ký, body có thể khác bytes đã được ký.
- `audience` phải là định danh API server đã cấu hình, không phải giá trị client tự chọn tùy ý.
- Key ID, method, content type, body hash, timestamp và nonce đều nằm trong transcript.
- Secret phải lấy từ secret manager/runtime an toàn, không hard-code hoặc log.

Đây là minh họa cho một giao thức HMAC tùy chỉnh, không thay thế thư viện hoặc chuẩn request-signing đã được đánh giá.

## 9. Ví dụ kiểm tra phía server

Pseudocode dưới đây cho thấy các quyết định quan trọng. Các hàm lưu trữ, canonicalization và authorization là phần phụ thuộc hạ tầng:

~~~ts
async function authenticateSignedRequest(req) {
  validateHeaderLengthsAndFormats(req);

  const key = await loadActiveKey(req.keyId);
  if (!key) return unauthorized();

  const timestamp = parseCanonicalUnixSeconds(req.timestamp);
  if (timestamp === null) return unauthorized();

  const canonical = canonicalizeActualRequest({
    keyId: req.keyId,
    audience: EXPECTED_AUDIENCE,
    method: req.method,
    rawTarget: req.rawTarget,
    contentType: req.contentType,
    body: req.rawBody,
    timestamp: req.timestamp,
    nonce: req.nonce
  });

  if (!verifyHmacConstantTime(key.secret, canonical, req.signature)) {
    return unauthorized();
  }

  const now = Math.floor(Date.now() / 1000);
  const windowSeconds = 300;
  if (Math.abs(now - timestamp) > windowSeconds) {
    return unauthorized();
  }

  const expiresAt = timestamp + windowSeconds + CLOCK_SAFETY_MARGIN;
  const firstUse = await replayStore.insertIfAbsent({
    keyId: req.keyId,
    nonce: req.nonce,
    expiresAt
  });
  if (!firstUse) return unauthorized();

  const principal = await resolveCurrentPrincipal(key);
  return authorizeAndExecute(req, principal);
}
~~~

Ví dụ dùng 300 giây chỉ để minh họa. Server thực tế cần giới hạn nonce length/charset, xác minh chữ ký và key state, kiểm tra body bytes, đồng hồ và TTL. `insertIfAbsent` phải nguyên tử và chia sẻ trạng thái giữa các node có thể nhận request. Không nên tự viết hàm HMAC so sánh bằng phép so sánh chuỗi thông thường.

Nếu replay store lỗi, endpoint nhạy cảm phải từ chối theo fail-closed. Nếu việc ghi nonce thành công nhưng xử lý nghiệp vụ thất bại, client không nên gửi lại nguyên request với nonce cũ; nó tạo timestamp/nonce mới và dùng idempotency key để server biết đó là retry cùng một thao tác.

## 10. Timestamp, nonce và idempotency key khác nhau thế nào?

Ba giá trị này thường cùng xuất hiện trong API nhưng có mục tiêu riêng:

| Giá trị | Ai tạo? | Có dùng lại không? | Mục tiêu |
| --- | --- | --- | --- |
| Timestamp | Client hoặc bên ký request | Có thể giống nhau giữa nhiều request trong cùng giây. | Giới hạn tuổi request. |
| Nonce | Thường client tạo bằng CSPRNG cho mỗi request | Không được dùng lại trong phạm vi replay policy. | Nhận biết request đã được chấp nhận. |
| Idempotency key | Client tạo cho một ý định nghiệp vụ | Có thể giữ nguyên qua các lần retry cùng ý định. | Tránh thực thi tác động nghiệp vụ nhiều lần. |

Ví dụ: client gửi yêu cầu tạo thanh toán nhưng timeout trước khi nhận phản hồi. Request đầu đã tiêu thụ nonce N1. Khi retry, client tạo timestamp mới và nonce N2, nhưng giữ idempotency key I1. Server xác thực request mới, thấy I1 đã được xử lý với cùng principal và payload, rồi trả kết quả đã lưu thay vì tạo giao dịch lần hai.

Idempotency key cần được ràng buộc với principal, endpoint và payload; server phải lưu trạng thái xử lý và kết quả một cách nhất quán. Nó không thay HMAC, timestamp hoặc nonce.

## 11. Các lỗi thiết kế phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ ký body, không ký timestamp/nonce | Attacker có thể sửa freshness field mà MAC vẫn đúng. | Ký toàn bộ trường xác thực và nội dung có ảnh hưởng. |
| Chỉ dùng timestamp | Request cũ vẫn bị phát lại trong cửa sổ. | Kết hợp nonce và replay store. |
| Chỉ sinh nonce ở client, server không lưu | Server không biết nonce đã dùng. | Atomically ghi nhận nonce sau xác minh MAC. |
| Nonce dùng timestamp hoặc Math.random() | Giá trị có thể trùng hoặc dự đoán. | CSPRNG với entropy đủ cao. |
| TTL replay record quá ngắn | Nonce bị xóa trong khi request còn được chấp nhận. | Tính TTL theo timestamp + cửa sổ + safety margin. |
| Check-then-insert không nguyên tử | Hai request đồng thời cùng được chấp nhận. | Unique constraint hoặc insert-if-absent nguyên tử. |
| Mỗi API node có replay cache riêng | Request phát lại đến node khác vẫn qua. | Dùng trạng thái chia sẻ/nhất quán hoặc partition đúng phạm vi. |
| Nới cửa sổ timestamp quá rộng | Tăng thời gian replay. | Đồng bộ clock và chọn cửa sổ theo độ trễ thực tế. |
| Không ràng buộc audience/path/method/body | Chữ ký có thể bị chuyển sang endpoint hoặc nội dung khác. | Canonicalize và ký toàn bộ request context. |
| Gửi lại nonce cũ khi retry | Request hợp lệ bị từ chối hoặc client xử lý sai. | Nonce mới cho mỗi request; idempotency key giữ nguyên cho cùng thao tác. |
| Fail-open khi replay store lỗi | Không còn kiểm soát dùng lại. | Fail closed với endpoint cần chống replay. |
| Log timestamp/nonce cùng secret/signature nhạy cảm không kiểm soát | Tăng dữ liệu hỗ trợ attacker và rủi ro lộ credential. | Redact secret, giới hạn log và chỉ lưu metadata điều tra cần thiết. |

## 12. Mô hình hóa threat và vận hành nhiều node

Khi đánh giá một hệ thống HMAC request authentication, hãy xác định:

| Câu hỏi | Lý do |
| --- | --- |
| Attacker có thể quan sát request ở đâu? | Proxy, log, tracing, CI, máy client hoặc queue có thể làm lộ request đã ký. |
| Request được chấp nhận trong bao lâu? | Quyết định cửa sổ timestamp và thời gian lưu nonce. |
| Nonce duy nhất theo key, principal hay endpoint? | Quyết định phạm vi replay cache và cách phân vùng dữ liệu. |
| Mọi node có dùng chung trạng thái nonce không? | Tránh replay chuyển qua node/region khác. |
| Đồng hồ lệch tối đa bao nhiêu? | Đặt cửa sổ thời gian và safety margin. |
| Khi store/KMS/time service lỗi thì sao? | Tránh fail-open ngoài ý muốn. |
| Retry hợp lệ được xử lý thế nào? | Phân biệt replay với idempotency. |
| Key bị lộ thì phản ứng ra sao? | Nonce không ngăn attacker tạo request mới nếu họ có secret. |

Trong hệ thống phân tán, cần quan tâm:

- **Race condition:** hai node cùng nhận một nonce gần như đồng thời. Unique constraint hoặc atomic insert phải bảo đảm chỉ một request thắng.
- **Eventual consistency:** node A đã ghi nonce nhưng node B chưa thấy. Cần kho dữ liệu có mức nhất quán phù hợp, không chỉ dựa vào cache cục bộ.
- **Clock skew:** các node dùng thời gian khác nhau có thể chấp nhận khác nhau. Giám sát đồng hồ và thống nhất policy.
- **TTL và cleanup:** tác vụ dọn dữ liệu không được xóa nonce trước khi request tương ứng hết cửa sổ hợp lệ.
- **Backup/restore:** khôi phục snapshot cũ không được làm sống lại nonce đã dùng trong khi request vẫn có thể được chấp nhận.
- **Lạm dụng lưu trữ:** attacker có thể gửi nhiều request có MAC hợp lệ bằng key bị chiếm để làm tăng replay store. Giới hạn tốc độ theo key/principal và quota.

Nếu attacker chỉ có một request đã ký, nonce và timestamp giúp ngăn phát lại. Nếu attacker đã chiếm secret, họ có thể tạo timestamp mới, nonce mới và MAC mới. Khi đó cần thu hồi key, giới hạn scope, bảo vệ runtime và điều tra nguồn lộ; replay store không phải biện pháp thay thế.

## 13. Checklist triển khai

Trước khi đưa HMAC request authentication lên production, hãy kiểm tra:

1. Timestamp có định dạng và đơn vị duy nhất, được đưa vào dữ liệu HMAC không?
2. Server so timestamp với đồng hồ tin cậy của mình, có cửa sổ vừa đủ và giám sát clock skew không?
3. Nonce có được sinh bằng CSPRNG, đủ entropy và khác nhau cho từng request không?
4. Nonce có nằm trong canonical request và được ràng buộc với key ID, audience, method, path, query và body không?
5. Server có xác minh HMAC trước khi chấp nhận timestamp/nonce và trước khi chạy nghiệp vụ không?
6. Replay store có thao tác insert-if-absent nguyên tử, unique scope rõ và chia sẻ giữa các node không?
7. TTL có kéo dài ít nhất tới hết cửa sổ timestamp cộng safety margin không?
8. Endpoint nhạy cảm có fail closed khi không thể kiểm tra replay store không?
9. Retry có dùng nonce mới nhưng idempotency key phù hợp cho cùng thao tác không?
10. Log có tránh secret, chữ ký nhạy cảm và dữ liệu không cần thiết không?
11. Có rate limit, quota, cảnh báo replay và quy trình revoke/rotate khi key bị lộ không?
12. Có test vector chung và kiểm thử request hợp lệ, timestamp cũ/tương lai, nonce trùng, sửa body, sửa path, race condition và failover nhiều node không?

**Kết luận:** Timestamp giới hạn tuổi của request; nonce giúp server nhận biết một request đã được sử dụng; HMAC ràng buộc cả hai với nội dung và ngữ cảnh request. Chống replay chỉ hiệu quả khi server kiểm tra thời gian bằng đồng hồ tin cậy, xác minh MAC, tiêu thụ nonce nguyên tử và giữ trạng thái đủ lâu trên mọi node. Retry nghiệp vụ cần idempotency riêng. Nếu secret bị chiếm, attacker vẫn có thể tạo request mới, nên hệ thống còn phải bảo vệ khóa, giới hạn quyền và có quy trình thu hồi.
