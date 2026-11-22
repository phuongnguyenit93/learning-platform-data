# Cursor integrity — Bảo vệ tính toàn vẹn của cursor phân trang

## 1. Cursor là dữ liệu điều khiển truy vấn đi qua client

Một API phân trang có thể trả `nextCursor` để client lấy phần dữ liệu tiếp theo. Cursor có thể mang khóa cuối trang, bộ lọc, chiều sắp xếp, snapshot ID hoặc thông tin về một lượt duyệt.

Dù do server phát hành ban đầu, cursor quay lại qua một request do client kiểm soát. Người gọi có thể sửa, cắt, ghép, phát lại hoặc lấy cursor từ một tài khoản khác.

**Cursor integrity** là khả năng phát hiện những thay đổi ngoài thẩm quyền đối với dữ liệu điều khiển phân trang, đồng thời bảo đảm cursor được dùng đúng ngữ cảnh mà server đã phát hành.

Những lỗi có thể dẫn tới:

- Đổi tenant hoặc phạm vi truy vấn qua payload cursor.
- Dùng cursor của người có quyền rộng hơn để đọc dữ liệu.
- Giữ token cũ để thử dùng lại một snapshot quyền đã bị thu hồi.
- Đổi filter hoặc sort nhưng vẫn tiếp tục một lượt duyệt được thiết kế cho truy vấn khác.
- Tăng page size, sửa vị trí hoặc chọn một nhánh truy vấn ngoài hợp đồng.
- Làm bỏ sót hoặc lặp dữ liệu trong những quy trình phụ thuộc thứ tự duyệt.

Bài học dùng danh sách đề nghị thanh toán nhiều tenant để minh họa. Các định dạng và code dưới đây là thiết kế mẫu cần được tích hợp với policy của hệ thống, không phải một thư viện cursor hoàn chỉnh.

## 2. Tính toàn vẹn không phải quyền truy cập

Một cursor có MAC đúng chỉ chứng minh nó được tạo bởi bên giữ khóa tương ứng và nội dung được bảo vệ chưa bị thay theo cơ chế đó. Nó không tự chứng minh người cầm cursor hiện được đọc dữ liệu.

Google AIP-158 cũng phân biệt rõ page token với authorization: token chỉ chỉ vị trí tiếp tục, request vẫn phải được kiểm tra quyền. [Google AIP-158: Pagination](https://google.aip.dev/158#opacity)

Cần giữ hai lớp:

```text
Cursor hợp lệ về cấu trúc, tính toàn vẹn và ràng buộc ngữ cảnh
AND request hiện tại có quyền đọc dữ liệu được trả về
```

Không lấy `tenantId`, role hoặc danh sách đơn vị trong cursor để thay thế nguồn quyền hiện tại. Những giá trị được bảo vệ có thể giúp phát hiện dùng sai ngữ cảnh, nhưng không tự trở thành một grant còn hiệu lực mãi.

### 2.1. Cursor không phải token thực hiện nghiệp vụ

Đọc đến cuối danh sách không chứng minh người dùng được duyệt hoặc thanh toán mọi phần tử. Một batch action được tạo từ kết quả phân trang vẫn phải kiểm tra action và đối tượng tại gate riêng.

Không dùng việc tiêu thụ cursor làm cơ chế duy nhất chống xử lý trùng hồ sơ. Replay trang là hành vi có thể cần thiết khi mất response; idempotency của hiệu ứng nghiệp vụ là vấn đề khác.

## 3. Base64, MAC, mã hóa và handle phía server

| Cách biểu diễn | Chống sửa nội dung như thế nào? | Có che nội dung không? |
| --- | --- | --- |
| JSON hoặc số offset trực tiếp | Không có bảo vệ tự thân | Không |
| Base64 của JSON | Chỉ đổi biểu diễn, không tạo tính toàn vẹn | Không |
| Payload kèm HMAC | Kiểm tra bằng khóa bí mật theo giao thức được thiết kế | Không |
| Mã hóa có xác thực | Bảo vệ nội dung và tính toàn vẹn theo cơ chế phù hợp | Có đối với bên không có khóa |
| Handle ngẫu nhiên tra trạng thái server | Client không trực tiếp sửa trạng thái được lưu; cần handle khó đoán và kho trạng thái được bảo vệ | Có thể che cấu trúc trạng thái khỏi client |

Ví dụ sau không an toàn nếu server tin nội dung sau decode:

```text
cursor = Base64({ tenantId: T, lastId: 100, pageSize: 50 })
```

Client có thể decode, thay giá trị và encode lại. Một hash không có khóa của chính payload cũng không ngăn người gọi tính lại hash sau khi sửa.

### 3.1. Đừng nhầm toàn vẹn với token không lộ cấu trúc

Phần HMAC của bài minh họa chống sửa, không che JSON hoặc bảo đảm client không nhìn thấy cấu trúc. Nó không tự đáp ứng một yêu cầu token phải che cấu trúc nội bộ hoặc dữ liệu nhạy cảm.

Nếu cần điều đó, chọn handle phía server hoặc một định dạng có bảo vệ phù hợp. Không đặt số tài khoản, secret hoặc dữ liệu nhạy cảm vào payload rồi cho rằng Base64 hay HMAC đã mã hóa chúng.

## 4. Ràng buộc cursor với ngữ cảnh nào?

Một payload minh họa sau khi kiểm tra tính toàn vẹn:

```json
{
  "audience": "payment-request-list:v1",
  "tenantId": "tenant-a",
  "subjectId": "subject-123",
  "scopeRevision": 42,
  "queryDigest": "digest-of-canonical-query",
  "sortId": "CREATED_DESC_ID_DESC",
  "direction": "NEXT",
  "position": {
    "createdAt": "2026-12-01T09:00:00.123456Z",
    "id": "3c8462f8-ad33-4cb1-897a-cc8acf595ae1"
  },
  "pageSizeCeiling": 100,
  "consistencyMode": "LIVE",
  "issuedAt": "2026-12-01T09:01:00Z",
  "expiresAt": "2026-12-01T09:16:00Z"
}
```

Các khoảng thời gian và giới hạn ở đây chỉ là ví dụ policy.

| Thành phần | Mục đích |
| --- | --- |
| Audience hoặc endpoint identity | Không dùng token của API khác như cursor ở đây |
| Tenant | Phát hiện dùng cursor ngoài tenant đang được kiểm tra |
| Chủ thể | Ràng buộc lượt duyệt với người gọi theo chính sách ví dụ |
| Scope revision | Phát hiện một số thay đổi quyền cần bắt đầu lại |
| Query digest | Ràng buộc bộ lọc và ngữ nghĩa truy vấn |
| Sort và direction | Không đổi dấu so sánh hoặc chiều duyệt ngoài hợp đồng |
| Position | Tiếp tục từ khóa đã phát hành |
| Page size ceiling | Giới hạn cho lượt duyệt, cùng giới hạn server hiện tại |
| Consistency mode | Không dùng cursor LIVE như một snapshot cố định |
| Thời gian | Giới hạn tuổi token và tài nguyên phụ thuộc |

Không phải mọi API đều phải dùng cùng tập field. Cần chọn đủ ràng buộc để việc lấy một cursor hợp lệ từ ngữ cảnh khác không thay đổi truy vấn ngoài ý muốn.

### 4.1. Subject binding là một lựa chọn chính sách

Ví dụ chốt cursor theo chủ thể chuẩn hóa. Một hệ thống có thể cho nhiều người dùng cùng một cursor nếu scope và hợp đồng thực sự cho phép, nhưng không được vô tình biến cursor của một người có quyền rộng thành quyền dùng chung.

Với service hoặc job export, cần xác định chủ thể, grant hoặc phạm vi công việc được ràng buộc thay vì bỏ trống kiểm tra.

## 5. Bộ lọc và page size cần canonical hóa đúng nghĩa

`queryDigest` cần được tính từ biểu diễn có cấu trúc đã được server xác thực, chẳng hạn:

```text
resource/action: PAYMENT_READ_SUMMARY
filters: state, khoảng thời gian, loại hồ sơ và những bộ lọc được hỗ trợ
sort: CREATED_DESC_ID_DESC
consistency mode và tham chiếu view nếu có
```

Không hash tùy tiện chuỗi query theo đúng thứ tự người dùng gõ rồi coi đó là toàn bộ ngữ nghĩa. Hai cách biểu diễn tương đương có thể cần cùng biểu diễn canonical; ngược lại, hai truy vấn khác nghĩa không được bị gộp.

Ví dụ chỉ sort một danh sách giá trị trước khi hash nếu danh sách đó có ngữ nghĩa tập hợp. Không sort những thành phần mà thứ tự là một phần của policy.

### 5.1. Không bỏ sót tham số làm thay đổi tập dữ liệu

Các tham số như `includeArchived`, loại hiển thị, chế độ ủy quyền hoặc scope được chọn có thể làm đổi kết quả. Nếu chúng thuộc hợp đồng tiếp tục cố định, phải được ràng buộc tương ứng.

Không để body hoặc query param chọn một nhánh truy vấn khác sau khi đã xác nhận cursor phù hợp.

### 5.2. Page size không được trở thành LIMIT tùy ý

Ví dụ cho phép đổi kích thước trang trong giới hạn hiện hành và `pageSizeCeiling` của lượt duyệt. Kích thước trang thực tế không nằm trong phần query digest cố định của lựa chọn này.

Có thể chọn một hợp đồng khác chốt page size cho cả lượt, nhưng cần nói rõ và kiểm thử. Trong mọi trường hợp, kiểm tra số nguyên, giá trị âm, giới hạn trên và phép tính `limit + 1` trước khi dựng query.

Không để `null`, overflow hoặc một giá trị đặc biệt biến thành truy vấn không giới hạn. Giới hạn mới chặt hơn của server vẫn cần được thực thi dù cursor cũ mang ceiling cao hơn.

## 6. Chọn khóa phân trang có thứ tự xác định

Giả sử danh sách sắp xếp:

```text
created_at DESC, id DESC
```

`id` là khóa phá hòa để những dòng cùng thời điểm vẫn có vị trí xác định. PostgreSQL lưu ý truy vấn LIMIT cần một thứ tự đủ xác định để tránh nhận các tập con không dự đoán được. [PostgreSQL: LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html)

Với các cột không null, một truy vấn trang tiếp theo có thể là:

```sql
SELECT p.id,
       p.created_at,
       p.display_reference,
       p.amount_minor,
       p.currency
FROM payment_request p
WHERE p.tenant_id = :verifiedTenantId
  AND p.org_unit_id = ANY(:authorizedUnitIds)
  AND p.state = :validatedState
  AND (p.created_at, p.id) < (:lastCreatedAt, :lastId)
ORDER BY p.created_at DESC, p.id DESC
LIMIT :fetchCount;
```

Đây là SQL minh họa cho PostgreSQL, với các giá trị được bind theo kiểu thích hợp, gồm mảng ID nếu dùng `ANY`. Trang đầu dùng biến thể query không có điều kiện position, không nhận một đoạn SQL tùy ý từ client.

Trong ví dụ, cặp khóa là duy nhất trong tenant, `created_at` và `id` không null, và các điều kiện scope đã được server xác định. Tập đơn vị được phép rỗng phải cho không có kết quả, không làm ứng dụng bỏ điều kiện lọc quyền.

### 6.1. Không dựng ORDER BY từ chuỗi cursor

Cursor chỉ mang một sort ID được hỗ trợ. Server ánh xạ sort ID sang một mẫu query đã kiểm soát; không nối tên cột, toán tử hoặc hướng sort tự do từ payload.

MAC đúng cũng không làm raw SQL trở thành một thiết kế tốt. Một lỗi ở đường phát hành token có thể tạo ra input nguy hiểm cho đường sử dụng nếu parser cho phép cấu trúc quá rộng.

### 6.2. Giữ nguyên độ chính xác của khóa

Position phải lấy từ giá trị server thực sự dùng để sắp xếp. Không đi qua JavaScript number hoặc cắt timestamp đến mili giây nếu dữ liệu lưu có độ chính xác khác.

Nếu có cột nullable, sort tùy locale hoặc collation, cần định nghĩa chúng trong ngữ nghĩa cursor và query. Không áp dụng phép so tuple minh họa cho mọi kiểu sắp xếp mà không thiết kế lại.

## 7. Lọc quyền trước khi giới hạn và phát hành cursor kế tiếp

Với page size N, một cách làm là query tối đa N+1 dòng đã qua predicate quyền. Trả N dòng đầu; nếu có dòng thêm thì phát cursor từ khóa của dòng cuối thực sự được trả.

```text
Query: tối đa N + 1 dòng được phép đọc.
Response: tối đa N dòng.
Next position: khóa của dòng thứ N đã trả, khi còn trang tiếp.
```

Không lấy khóa của dòng N+1 làm position kế tiếp rồi dùng điều kiện loại trừ nó, vì sẽ bỏ mất dòng đó.

### 7.1. Đừng dùng hàng ngoài quyền để tính hasNext

Nếu query lấy dữ liệu thô, LIMIT trước rồi mới lọc quyền, độ dài trang, hasNext hoặc cursor có thể phản ánh các dòng người dùng không được biết. Nó cũng có thể tạo trang rỗng trong khi vẫn còn dữ liệu được phép phía sau.

Tốt nhất đẩy predicate quyền có ngữ nghĩa tương đương vào query. Nếu mô hình bắt buộc kiểm tra sau, cần thiết kế rõ việc quét có giới hạn, vị trí tiếp tục, cách lấp trang và metadata không tiết lộ; không giả định lấy N dòng thô là đủ.

### 7.2. Count và trường dữ liệu cũng cần đúng scope

`totalCount`, số trạng thái, summary và liên kết export phải cùng tuân chính sách truy cập. Một trang không có dữ liệu tenant B nhưng count toàn hệ thống vẫn có thể làm lộ thông tin.

Quyền đọc summary không tự cho phép trả số tài khoản hoặc những quan hệ nhạy cảm trong object lồng nhau. Cursor integrity không thay field-level authorization.

## 8. Thiết kế envelope HMAC minh họa

Một định dạng có thể là:

```text
v1.<kid>.<payloadBase64Url>.<macBase64Url>
```

Trong đó:

```text
mac = HMAC-SHA-256(
    key_for_kid,
    ASCII("payment-list-cursor:v1:" + kid + "." + payloadBase64Url)
)
```

`kid` chỉ chọn trong key ring do server quản lý; nó không phải đường dẫn, URL hoặc yêu cầu tải một khóa tùy ý. Thuật toán được chốt trong phiên bản giao thức, không do payload chọn.

HMAC dùng khóa bí mật để kiểm tra toàn vẹn; Java có API `Mac` cho cơ chế này. [Java SE: Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)

### 8.1. Xác thực đúng chuỗi đã được bảo vệ

Tính MAC trên những segment có biểu diễn rõ ràng mà server đã phát hành. Không parse JSON, sửa hoặc serialize lại rồi mới đoán MAC của một biểu diễn khác.

Sau khi xác minh MAC vẫn cần parse nghiêm ngặt và kiểm tra schema, thời gian, loại khóa cùng ràng buộc ngữ cảnh. Token được một thành phần server tạo sai cũng không nên trở thành input vô giới hạn cho query.

### 8.2. Không dùng chung khóa tùy tiện

Phân biệt mục đích cursor với những loại token khác. Key ring, domain của dữ liệu MAC và ràng buộc audience cần ngăn token của một API hoặc môi trường khác được dùng ở đây.

Khóa phải đến từ nguồn quản lý bí mật phù hợp, không hard-code vào source hoặc phát cho client. Test có thể dùng khóa riêng cho fixture nhưng không dùng nó như cấu hình vận hành.

## 9. Ví dụ Java: xác minh tính toàn vẹn trước khi tin claims

Đoạn mã sau minh họa verifier của định dạng trên. `CursorKeyRing`, `StrictCursorJson`, `CursorClaims` và các exception cần được triển khai theo hợp đồng. Các giới hạn kích thước và TTL chỉ là ví dụ.

```java
public final class SignedCursorVerifier {
    private static final String VERSION = "v1";
    private static final String DOMAIN = "payment-list-cursor:v1:";
    private static final int MAX_TOKEN_CHARS = 4096;
    private static final int MAX_PAYLOAD_BYTES = 2048;
    private static final int MAC_BYTES = 32;
    private static final Duration MAX_TTL = Duration.ofMinutes(15);

    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private final CursorKeyRing keys;
    private final StrictCursorJson json;
    private final Clock clock;

    public SignedCursorVerifier(
            CursorKeyRing keys, StrictCursorJson json, Clock clock) {
        this.keys = keys;
        this.json = json;
        this.clock = clock;
    }

    public CursorClaims verify(String token) {
        if (token == null || token.isEmpty()
                || token.length() > MAX_TOKEN_CHARS) {
            throw new InvalidCursorException();
        }

        String[] parts = token.split("\\.", -1);
        if (parts.length != 4 || !VERSION.equals(parts[0])) {
            throw new InvalidCursorException();
        }

        String kid = parts[1];
        String payloadPart = parts[2];
        String macPart = parts[3];

        if (!kid.matches("[A-Za-z0-9_-]{1,32}")
                || !payloadPart.matches("[A-Za-z0-9_-]{1,2800}")
                || !macPart.matches("[A-Za-z0-9_-]{43}")) {
            throw new InvalidCursorException();
        }

        SecretKey key = keys.findVerificationKey(kid)
            .orElseThrow(InvalidCursorException::new);

        byte[] suppliedMac = decodeCanonical(macPart);
        if (suppliedMac.length != MAC_BYTES) {
            throw new InvalidCursorException();
        }

        byte[] expectedMac = hmac(key, kid, payloadPart);
        if (!MessageDigest.isEqual(expectedMac, suppliedMac)) {
            throw new InvalidCursorException();
        }

        byte[] payload = decodeCanonical(payloadPart);
        if (payload.length > MAX_PAYLOAD_BYTES) {
            throw new InvalidCursorException();
        }

        CursorClaims claims = json.readStrict(payload);
        claims.requireTemporalValidity(clock.instant(), MAX_TTL);
        claims.requireSupportedShapeAndSort();
        return claims;
    }

    private static byte[] decodeCanonical(String encoded) {
        try {
            byte[] decoded = DECODER.decode(encoded);
            if (!ENCODER.encodeToString(decoded).equals(encoded)) {
                throw new InvalidCursorException();
            }
            return decoded;
        } catch (IllegalArgumentException ex) {
            throw new InvalidCursorException();
        }
    }

    private static byte[] hmac(
            SecretKey key, String kid, String payloadPart) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] input = (DOMAIN + kid + "." + payloadPart)
                    .getBytes(StandardCharsets.US_ASCII);
            return mac.doFinal(input);
        } catch (GeneralSecurityException ex) {
            throw new CursorCryptoUnavailableException(ex);
        }
    }
}
```

Import tương ứng từ Java standard library cần được khai báo. Mỗi lần tính dùng một instance `Mac` riêng, tránh chia sẻ trạng thái tính toán mutable giữa các request.

Mẫu dùng `MessageDigest.isEqual()` để so MAC có kích thước đã giới hạn thay vì so chuỗi tag bằng một phép so tùy tiện. JDK mô tả việc tính so sánh không phụ thuộc nội dung hai digest theo implementation note của phương thức. [Java SE: MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D))

### 9.1. Những việc helper phải làm thật sự

`StrictCursorJson` cần giới hạn schema, kiểu, độ sâu và xử lý field trùng hoặc không hỗ trợ theo hợp đồng. Không bật deserialize đa hình cho những kiểu tùy ý trong cursor.

`requireTemporalValidity()` cần kiểm tra thời điểm phát hành, hết hạn, TTL tối đa và mức sai lệch được policy cho phép. Không để một khoảng âm, overflow hoặc thời gian ở tương lai ngoài hợp đồng được coi là hợp lệ.

`requireSupportedShapeAndSort()` kiểm tra các enum, kiểu position, giới hạn và sự kết hợp được hỗ trợ. Những helper đó không được chỉ là tên gợi ý trong một implementation thực tế.

### 9.2. Verifier chưa cấp quyền đọc

Kết quả chỉ là claims đã qua những kiểm tra của codec. Caller vẫn phải đối chiếu audience, tenant, subject, query và scope hiện tại trước khi dùng position.

Không deserialize một `CursorClaims` từ request rồi gọi thẳng repository vì kiểu dữ liệu có tên “verified” hoặc “claims”. Đường tạo đối tượng và điểm thực thi mới quyết định mức tin cậy.

## 10. Tích hợp verifier vào endpoint danh sách

Một luồng minh họa:

```text
1. Xác thực actor và tenant đang yêu cầu.
2. Kiểm tra quyền đọc danh sách và dựng read scope hiện tại.
3. Validate, canonical hóa filter, sort và giới hạn trang.
4. Nếu có cursor:
     xác minh envelope và thời gian
     đối chiếu audience, tenant, subject và query
     kiểm tra scope revision theo hợp đồng
     lấy position có kiểu được hỗ trợ
5. Query với quyền hiện tại và position đã kiểm tra.
6. Lấy tối đa N+1 dòng được phép, trả N dòng.
7. Nếu còn trang, server tạo cursor mới từ dòng cuối đã trả.
```

Các claims mới được tạo từ dữ liệu và ngữ cảnh server, không sao chép nguyên object cursor do client gửi. Position phải lấy từ kết quả query, không từ một giá trị “last seen” tùy ý trong body.

### 10.1. Cùng filter và scope cho data lẫn metadata

Repository không được nhận một cursor có tenant A rồi bỏ predicate tenant vì cho rằng MAC đã đủ. Tenant có thẩm quyền vẫn đến từ ngữ cảnh request đã kiểm tra.

Nếu có count hoặc hasNext, chúng phải tương thích với tập dữ liệu đã được cấp quyền. Các tham số client làm rộng quyền không được lẫn với filter nghiệp vụ chỉ có tác dụng thu hẹp kết quả.

### 10.2. Khi scope revision thay đổi

Ví dụ chọn bắt đầu lại lượt duyệt nếu revision quyền liên quan thay đổi. Revision chỉ có giá trị nếu nó bao phủ đúng những phụ thuộc mà chính sách dựa vào.

Nếu ACL của một đối tượng đổi mà không làm revision tổng đổi, predicate quyền hiện tại vẫn phải chặn đối tượng đó. Không dùng một con số revision chưa đủ phụ thuộc làm lý do bỏ kiểm tra dữ liệu.

## 11. Tính toàn vẹn không tạo snapshot dữ liệu

Một cursor không bị sửa vẫn có thể trả kết quả khác khi dữ liệu đổi giữa các request.

Trong chế độ LIVE:

- Hồ sơ có thể bị xóa hoặc đổi trạng thái.
- Quyền trên hồ sơ có thể thay đổi.
- Một khóa sort mutable có thể làm hồ sơ đi qua vị trí đã duyệt.
- Một row commit muộn có thể xuất hiện sau khi trang đầu đã được trả.

Keyset pagination với sort phù hợp giúp xác định cách tiếp tục, nhưng không tự bảo đảm một ảnh chụp bất biến của toàn bộ tập kết quả.

### 11.1. Mốc trên không phải một snapshot đầy đủ

Có thể ràng buộc một upper bound để hạn chế các dòng mới phía trên đầu danh sách. Tuy nhiên, nó không tự giải quyết update, delete, thay filter do trạng thái hoặc row đã có khóa trong khoảng nhưng commit muộn.

Không quảng bá một timestamp watermark đơn giản như bảo đảm đã thấy đúng mọi hồ sơ tại một thời điểm nếu thiết kế không chứng minh được điều đó.

### 11.2. Khi cần kết quả cố định

Có thể cần một read view hoặc danh sách ID, version được vật hóa và quản lý phía server. Cursor chứa tham chiếu view cùng position; mỗi lần dùng phải kiểm tra view thuộc đúng scope, còn hạn và caller được phép đọc.

Snapshot dữ liệu không tự chụp quyền truy cập vĩnh viễn. Chính sách phải xác định xử lý thu hồi quyền ra sao, đặc biệt với export hoặc dữ liệu nhạy cảm.

Giữ một transaction và connection mở qua nhiều request cũng có chi phí vận hành; không nên vô tình tạo nghĩa vụ tài nguyên dài hạn chỉ để có vẻ phân trang nhất quán.

## 12. Replay, hết hạn và key rotation

### 12.1. Replay có thể hợp lệ

Client có thể retry cùng cursor khi mất response. Nếu API là đọc, không nhất thiết phải biến cursor thành token chỉ dùng một lần.

Trong LIVE mode, retry có thể thấy dữ liệu hiện tại khác nếu hợp đồng cho phép. Trong snapshot mode, kết quả cần tuân theo read view. Không dùng lại cursor làm cơ chế chống tạo approval hoặc thanh toán trùng.

### 12.2. Đừng tự kéo dài tuổi lượt duyệt mãi

Nếu cần TTL tuyệt đối cho một lượt, giữ `issuedAt` và `expiresAt` gốc khi phát cursor tiếp theo. Không đặt deadline mới ở mỗi trang rồi cho client giữ read view sống vô hạn bằng cách liên tục đọc.

Có thể chọn mô hình gia hạn khác nếu policy cho phép, nhưng phải giới hạn và quản lý tài nguyên tương ứng. Thời gian do server quyết định; client không được tự thêm TTL.

### 12.3. Xoay khóa

Key ring có thể có khóa đang phát hành và những khóa còn được phép xác minh trong thời gian chuyển tiếp. Thời gian giữ khóa xác minh cần phù hợp TTL token và chính sách xử lý sự cố khóa.

Khi khóa bị loại bỏ hoặc token quá hạn, trả lỗi hoặc yêu cầu bắt đầu lại theo hợp đồng. Không fallback sang decode Base64 không xác minh để giữ client cũ tiếp tục chạy.

Không nhận thuật toán hoặc nguồn tải khóa từ cursor. `kid` là selector giới hạn trong cấu hình được tin cậy, không là quyền chọn một cơ chế xác minh yếu hơn.

## 13. Lỗi cursor cần dừng đúng, không mở rộng truy vấn

Một lỗi công khai có thể là:

```json
{
  "code": "INVALID_CURSOR",
  "message": "Không thể tiếp tục với cursor này. Hãy tải lại danh sách."
}
```

Không cần tiết lộ token sai vì tenant nào, subject nào hoặc vị trí đó có tồn tại không. Chi tiết có thể được ghi nội bộ theo quyền điều tra.

### 13.1. Không có cursor khác với cursor hỏng

Request không có cursor có thể là trang đầu. Một cursor được cung cấp nhưng hỏng không nên âm thầm trở thành trang đầu, mất filter hoặc bỏ điều kiện quyền.

Nếu API cho phép client bắt đầu lại, đó phải là một request rõ ràng với scope và filter được kiểm tra như bình thường.

### 13.2. Lỗi khóa hoặc hạ tầng không phải lỗi do người dùng sửa

Nếu không có key do hệ thống cấu hình sai hoặc crypto provider không hoạt động, cần phân loại sự cố phù hợp và không bỏ kiểm tra toàn vẹn. Ví dụ code giữ lỗi crypto riêng thay vì coi mọi exception là một token có thể được xử lý theo cách ít kiểm tra hơn.

### 13.3. Giới hạn trước xử lý tốn kém

Giới hạn độ dài cursor, số segment, kích thước decode và độ phức tạp JSON. Kiểm tra tham số lặp hoặc cách decode URL có thể làm các lớp hiểu khác nhau theo chính sách của endpoint.

Không dùng cursor để nối SQL hoặc tạo một giá trị LIMIT không giới hạn, kể cả khi nó vượt qua một lớp kiểm tra cú pháp.

## 14. Cache, link và dữ liệu chẩn đoán

### 14.1. Cache cần đủ ngữ cảnh

Cache response chỉ theo cursor có thể trả dữ liệu được tính dưới quyền cũ hoặc cho một actor khác nếu thiết kế không ràng buộc đủ. Cache cần giữ action, tenant, chủ thể hoặc scope, query và những revision cần thiết theo hợp đồng.

Ngay cả khi token có subject ID, quyền hiện tại vẫn có thể bị thu hồi. TTL cache không tự bảo đảm giới hạn thu hồi của hệ thống.

### 14.2. Cursor có thể xuất hiện ngoài body

Cursor trong query string có thể đi vào access log, lịch sử hoặc đường dẫn được chia sẻ. HMAC không mã hóa payload, nên thiết kế nội dung cần xét đúng mức lộ thông tin.

Không coi cursor là bí mật thay access token, nhưng cũng không vì nó không phải credential mà ghi nguyên mọi token vào những kênh không cần thiết. Có thể log fingerprint phục vụ đối chiếu, cùng actor, route và reason code đã kiểm soát.

### 14.3. Không biến integrity thành lời hứa chống mọi trích xuất

Người được cấp quyền có thể tiếp tục phân trang để đọc tập dữ liệu họ được phép xem. MAC không tự là quota export hoặc cơ chế ngăn mọi hình thức thu thập dữ liệu.

Nếu cần giới hạn khối lượng hoặc tần suất, phải có policy và thực thi riêng ở server, không dựa vào việc định dạng cursor khó đoán.

## 15. Kiểm thử codec và ràng buộc ngữ cảnh

### 15.1. Mutation token

Từ một token hợp lệ do fixture phát hành, kiểm tra:

| Mutation | Kết quả cần chứng minh |
| --- | --- |
| Đổi tenant hoặc subject trong payload mà không tính MAC mới | Bị từ chối |
| Đổi position, expiry, ceiling hoặc query digest | Bị phát hiện thay đổi |
| Ghép payload và MAC từ hai token | Không được chấp nhận |
| Thêm segment, ký tự không hỗ trợ hoặc token rất lớn | Lỗi có kiểm soát trước truy vấn dữ liệu |
| `kid` lạ, bị loại bỏ hoặc có dạng đường dẫn | Không lấy khóa tùy ý hoặc bỏ xác minh |
| Thay version hoặc đưa thuật toán tự chọn | Không downgrade sang cơ chế khác |
| Base64 không canonical hoặc tag sai kích thước | Xử lý đúng hợp đồng verifier |
| JSON trùng field hoặc kiểu không hỗ trợ | Không tạo claims mơ hồ |

Không chỉ serialize một object claims đã sửa bằng chính signer test rồi kết luận tampering bị chặn. Test sửa trái phép cần dùng token mà attacker không có khả năng tạo MAC hợp lệ.

### 15.2. Token hợp lệ nhưng sai ngữ cảnh

1. Cursor của tenant A được dùng khi active tenant là B.
2. Cursor của người A được gửi bởi người B trong mô hình subject-bound.
3. Cursor của API hoặc action khác được dùng ở danh sách payment.
4. Thay filter làm đổi tập kết quả nhưng giữ token cũ.
5. Thay sort hoặc direction mà không có cursor tương ứng.
6. Scope revision đổi hoặc quyền bị thu hồi sau trang đầu.
7. Snapshot ID hợp lệ nhưng thuộc scope khác.
8. Tăng page size vượt ceiling hoặc giới hạn server hiện tại.

MAC đúng không làm các trường hợp này được phép. Cần kiểm tra cả dữ liệu, count, hasNext và response lỗi để không rò thông tin ngoài quyền.

### 15.3. Thời gian và khóa

Dùng clock điều khiển được để test trước, đúng và sau hạn, issuedAt bất hợp lệ và TTL vượt giới hạn. Kiểm tra cursor trang tiếp không tự kéo dài TTL tuyệt đối nếu policy chốt tuổi lượt.

Test khóa cũ trong cửa sổ xác minh, khóa đã ngừng và sự cố key ring. Không biến lỗi hạ tầng thành fallback không bảo vệ.

## 16. Kiểm thử query, tính đầy đủ và thay đổi đồng thời

### 16.1. Dataset cố định

Tạo dữ liệu có nhiều dòng cùng `created_at`, các tenant và scope khác nhau. Với một scope cố định, duyệt hết và xác nhận:

```text
hợp các dòng đã trả = tập dòng được phép theo query
không có dòng lặp trái hợp đồng
thứ tự khớp sort được khai báo
không có dòng tenant hoặc scope khác
```

Thử page size 1, trang vừa đủ N dòng, N+1 dòng và cuối tập. Kiểm tra cursor được tạo từ dòng cuối đã trả, không từ dòng nhìn trước bị loại khỏi response.

### 16.2. Độ chính xác và ranh giới

Kiểm tra các timestamp sát nhau theo độ chính xác thực tế của cơ sở dữ liệu và driver. Không làm tròn key qua client hoặc serializer rồi bỏ sót những dòng có khóa khác nhau ở phần bị cắt.

Nếu hỗ trợ null hoặc nhiều sort, mỗi loại cần test riêng về toán tử tiếp tục, chiều và thứ tự. Không dùng test của sort giảm dần cho một sort tăng dần mà chưa đổi điều kiện.

### 16.3. Quyền trước LIMIT và metadata

Đặt các dòng không được phép xen giữa dòng được phép để phát hiện việc LIMIT trước rồi lọc sau. Kiểm tra trang ngắn, hasNext và count không phản ánh nhầm hàng ngoài quyền.

Nếu có hậu kiểm được thiết kế riêng, test giới hạn quét và cách tiếp tục của chính cơ chế đó. Không kết luận thuật toán tương đương chỉ vì một dataset nhỏ tình cờ cho cùng kết quả.

### 16.4. Thay đổi giữa các trang

Chèn, sửa, xóa, đổi trạng thái và thu hồi quyền có kiểm soát giữa hai request. Kỳ vọng phải đúng mode:

- LIVE không được hứa một snapshot bất biến mà thiết kế không cung cấp.
- Snapshot mode phải giữ đúng read view theo hợp đồng.
- Cả hai mode không được dùng cursor cũ để mở lại dữ liệu ngoài quyền hiện tại, trừ một cơ chế cấp quyền snapshot riêng đã được thiết kế rõ.

Dùng các điểm đồng bộ hoặc thao tác được điều khiển giữa các request. Không dựa vào sleep để hy vọng một row commit đúng lúc.

## 17. Những lỗi thiết kế cần tránh

| Cách làm | Vì sao tạo vấn đề | Hướng thay thế |
| --- | --- | --- |
| Base64 là đủ chống sửa | Caller có thể decode và encode lại | MAC, cơ chế xác thực phù hợp hoặc trạng thái server |
| Hash payload không có khóa | Caller có thể tính lại hash | Cơ chế toàn vẹn có nguồn thẩm quyền |
| MAC đúng thì lấy tenant trong token làm quyền | Token hợp lệ có thể thuộc ngữ cảnh khác hoặc quyền đã đổi | Đối chiếu context và kiểm tra quyền hiện tại |
| Cursor chứa role cũ để bỏ authorization | Kéo dài quyền ngoài hợp đồng thu hồi | Predicate và policy tại request hiện tại |
| Nối sort hoặc SQL từ cursor | Mở khả năng dựng query ngoài kiểm soát | Sort ID giới hạn và bind giá trị có kiểu |
| Sort không có khóa phá hòa | Có thể lặp hoặc bỏ dòng cùng giá trị sort | Thứ tự đủ xác định |
| Lấy dòng nhìn trước làm next position | Bỏ mất một dòng ở trang sau | Position của dòng cuối thực sự được trả |
| LIMIT trước rồi bỏ hàng ngoài quyền | Trang và metadata có thể sai hoặc lộ thông tin | Query quyền tương đương hoặc cơ chế hậu kiểm được thiết kế đầy đủ |
| Cursor hỏng thì bỏ filter và quay trang đầu | Lỗi integrity làm đổi phạm vi | Dừng rõ ràng và yêu cầu restart có chủ ý |
| Gia hạn expiry ở mỗi trang ngoài policy | Lượt hoặc read view có thể sống vô hạn | TTL được quản lý theo hợp đồng |
| Key lỗi thì chấp nhận định dạng cũ không MAC | Mở đường downgrade | Fail closed và xử lý sự cố khóa riêng |
| Cursor ký đúng nên coi là snapshot | Không giải quyết dữ liệu đổi giữa request | Mode nhất quán và read view phù hợp |

## 18. Bài tập thiết kế

Thiết kế danh sách đề nghị thanh toán nhiều tenant, có scope theo đơn vị, filter trạng thái và sort `created_at DESC, id DESC`. API trả cursor tiếp theo và cho phép thay page size trong một giới hạn do server chốt.

Hãy mô tả:

1. Cursor mang những dữ liệu nào và field nào phải ràng buộc với context hiện tại?
2. Cơ chế nào bảo vệ toàn vẹn, và nó có che nội dung token không?
3. Canonical query gồm những thành phần nào, còn page size được xử lý ra sao?
4. Predicate quyền được áp dụng ở đâu trước LIMIT, count và hasNext?
5. Khóa cuối trang được giữ đúng độ chính xác và thứ tự như thế nào?
6. Token còn MAC hợp lệ nhưng quyền hoặc scope đổi sẽ được xử lý ra sao?
7. Hợp đồng là LIVE hay snapshot, và những biến động nào được phép giữa các trang?
8. Những test nào chứng minh sửa token, đổi tenant, replay hoặc key rotation không mở rộng quyền và không làm mất dòng trái hợp đồng?

Một thiết kế đạt yêu cầu phải bảo vệ được dữ liệu điều khiển phân trang, giữ đúng phạm vi truy vấn và không biến một dấu mốc tiếp tục đọc thành quyền truy cập hoặc một lời hứa nhất quán mà hệ thống chưa thực sự cung cấp.
