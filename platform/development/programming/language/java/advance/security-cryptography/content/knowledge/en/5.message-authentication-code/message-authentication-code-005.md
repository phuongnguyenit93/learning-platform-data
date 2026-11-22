# 5.5. Thống nhất dữ liệu đầu vào, thứ tự trường và định dạng tag giữa hai bên

Trong một hệ thống dùng **mã xác thực thông điệp (Message Authentication Code, MAC)**, việc cả hai phía cùng chọn `HmacSHA256` và cùng giữ một khóa bí mật vẫn **chưa đủ** để xác thực thành công. Phía gửi và phía nhận còn phải tính MAC trên **đúng cùng một dãy byte**, theo **cùng quy tắc sắp xếp trường và mã hóa**, rồi thống nhất **cách biểu diễn, truyền và kiểm tra authentication tag**.

Một lỗi tưởng nhỏ như đổi thứ tự hai trường JSON, dùng ký tự xuống dòng khác nhau, ghi số tiền ở định dạng khác, hoặc hiểu nhầm Base64 thường với Base64URL có thể làm hai phía tạo tag khác nhau. Nguy hiểm hơn, quy tắc ghép dữ liệu mơ hồ có thể khiến **hai thông điệp nghiệp vụ khác nhau tạo cùng chuỗi byte trước khi MAC**, dù bản thân HMAC hoàn toàn an toàn.

Mục tiêu của bài học:

- Xác định chính xác những byte phải được xác thực, các trường bắt buộc và ý nghĩa nghiệp vụ của từng trường.
- Thiết kế một định dạng đầu vào **xác định, không nhập nhằng** giữa hai ngôn ngữ/hệ thống.
- Quy định thứ tự trường, UTF-8, độ dài trường, kiểu số, version, domain và cách xử lý missing/null/empty.
- Phân biệt **tag thô dạng byte** với chuỗi hex/Base64/Base64URL trên đường truyền.
- Viết và kiểm tra một hợp đồng HMAC-SHA256 có **test vector tái lập** bằng Java 17+.
- Nhận diện các lỗi dẫn tới MAC mismatch, algorithm/key confusion, replay và thiếu phân quyền.

## 1. MAC tạo tag cho byte, không tạo tag cho “ý nghĩa” trừu tượng

Với khóa đối xứng bí mật `K` và thông điệp ở dạng byte `M`, thao tác có dạng:

\[
T = \operatorname{MAC}_{K}(M)
\]

Đối tác nhận sẽ tự tính `MAC_K(M_received)` rồi kiểm tra kết quả có phù hợp với tag nhận được hay không.

```text
Bên gửi                                         Bên nhận
--------                                        --------
Dữ liệu nghiệp vụ                               Dữ liệu nghiệp vụ
        |                                               |
Canonical encoding (quy tắc chung)            Canonical encoding (cùng quy tắc)
        |                                               |
Đúng dãy byte M                                Đúng dãy byte M'
        |                                               |
MAC(K, M)                                      MAC(K, M')
        |                                               |
Tag bytes T -------- wire encoding --------> Giải mã tag -> T'
                                                        |
                                               So sánh T' với MAC(K, M')
                                                        |
                                               Chỉ xử lý khi mọi kiểm tra đạt
```

Để xác thực thành công một cách có ý nghĩa, hai phía phải thống nhất ít nhất:

1. **Khóa và chính sách sử dụng khóa**: byte khóa nào, `keyId` nào, mục đích nào, ai được quyền giữ khóa và định danh nào gắn với khóa.
2. **Thuật toán và cấu hình**: chẳng hạn `HmacSHA256` cho tag đầy đủ 32 byte; quy tắc truncation nếu có.
3. **Input/schema**: những trường nào phải được bảo vệ (bao gồm tenant, tài nguyên, hành động, số tiền, requestId), thứ tự và kiểu dữ liệu.
4. **Canonical encoding**: đúng byte đầu vào, UTF-8, độ dài, integer endian, xử lý Unicode, JSON và null.
5. **Wire format của tag**: byte thô, hex, Base64 hay Base64URL; padding, độ dài, viết hoa/thường và nơi đặt tag.
6. **Version, ngữ cảnh và cách từ chối**: bản tin thuộc protocol nào; có chống replay, giới hạn thời gian, kiểm tra quyền và xử lý lỗi không.

**Tính xác định của HMAC**: với cùng thuật toán, cùng byte khóa và cùng byte thông điệp, tag sẽ trùng nhau. Nếu tag khác, đừng vội kết luận thuật toán sai; thường nên kiểm tra byte đã đưa vào MAC trước.

### 1.1. HMAC khác hash không khóa

`SHA-256(M)` là digest công khai; bất kỳ ai biết `M` đều có thể tính lại. `HMAC-SHA256(K, M)` sử dụng **bí mật `K`** theo một phép xây dựng MAC chuẩn, cho phép bên cũng giữ khóa kiểm tra tính toàn vẹn và nguồn tạo tag thuộc nhóm biết khóa.

Với khóa HMAC được chia sẻ cho nhiều dịch vụ, một tag đúng chứng minh **bản tin tương thích với khóa chia sẻ**, không xác định duy nhất dịch vụ nào đã tính tag. Muốn gắn với danh tính, bên nhận phải có ánh xạ khóa với principal và kiểm tra quyền nghiệp vụ. MAC không phải chữ ký số dùng public key, không có cơ chế xác minh công khai như chữ ký.

**AEAD** như AES-GCM cũng sinh authentication tag, nhưng tag GCM phụ thuộc cả nonce, ciphertext và AAD theo quy tắc AEAD. Không được lấy tag HMAC thay thế tag GCM, hoặc tự nghĩ “tag là một đoạn text nên hai tag nào cũng tương đương”.

## 2. “Cùng dữ liệu” nhưng byte khác nhau

MAC nhìn **byte**, không hiểu cấu trúc đối tượng, JSON, ý nghĩa số tiền hoặc người dùng. Các cặp hiển thị “gần giống” dưới đây có thể tạo byte khác nhau:

| Cùng ý định nghiệp vụ nhưng khác biểu diễn | Ví dụ | Tác động |
| --- | --- | --- |
| Thứ tự thuộc tính JSON | `{"amount":100,"currency":"USD"}` và `{"currency":"USD","amount":100}` | Nếu ký byte JSON thô, tag khác |
| Khoảng trắng JSON | `{"a":1}` và `{ "a": 1 }` | Byte khác dù object logic tương đương |
| Dấu xuống dòng | LF `\n` và CRLF `\r\n` | Hash/MAC khác |
| Encoding | UTF-8 và UTF-16LE | Byte khác |
| Unicode tổ hợp | `é` (U+00E9) và `e` + U+0301 | Có thể hiển thị giống nhau nhưng UTF-8 khác |
| Số tiền | `1`, `1.0`, `01`, `1e0` | String khác; nếu dùng JSON number còn có khác biệt kiểu/làm tròn |
| Thời gian | `2026-10-31T12:00:00Z` và `2026-10-31T19:00:00+07:00` | Cùng thời điểm nhưng string khác |
| Base64 | `+`/`/`/`=` so với `-`/`_` không padding | Cùng dữ liệu nhị phân có thể thành wire text khác |
| Null/missing/empty | Không có trường, `null`, `""` | Thường là ba trạng thái nghiệp vụ khác nhau |
| URL | `/a%2Fb` và `/a/b`; query order khác | Có thể có semantics khác qua proxy/router |
| HTTP header | Trình tự, viết hoa tên, khoảng trắng, header được gộp | Canonical string có thể khác |

Ví dụ:

```json
{"tenant":"shop-1","amount":1299}
```

và

```json
{
  "amount": 1299,
  "tenant": "shop-1"
}
```

có thể là cùng object nghiệp vụ, nhưng không là cùng chuỗi byte. Nếu phía gửi MAC trên JSON đã format còn phía nhận parse rồi serialize lại theo thứ tự khác, HMAC sẽ không khớp.

Có **hai chiến lược đúng** nhưng phải chọn một cách nhất quán:

- **MAC đúng byte đã gửi:** bên nhận tính trên đúng payload bytes được truyền và không serialize lại trước khi xác minh. Cần quy định rõ lúc nào byte được lấy, ví dụ trước/sau compression hay content transformation. Cách này tránh phải canonicalize lại JSON nhưng MAC vẫn phải bao phủ đầy đủ ngữ cảnh bên ngoài body nếu nghiệp vụ cần.
- **MAC trên canonical representation:** cả hai phía chuyển dữ liệu logic thành đúng một encoding theo schema đã công bố. Chọn binary length-prefix, CBOR deterministic profile hoặc quy tắc canonical JSON phù hợp; cả hai bên phải cùng thực hiện.

Không tự pha trộn hai chiến lược, chẳng hạn sender ký raw JSON còn receiver ký object đã parse.

## 3. Thứ tự trường và cách ngăn nhập nhằng

Một quy tắc nguy hiểm là nối chuỗi trực tiếp:

```text
M = tenantId + requestId

tenantId = "ab"; requestId = "c"   -> "abc"
tenantId = "a";  requestId = "bc"  -> "abc"
```

Hai bản tin **khác nhau** tạo **cùng byte input**. Vì thế chúng sẽ có cùng HMAC với cùng khóa, **không cần phá HMAC hay tìm collision mật mã**. Đây là lỗi định dạng trước khi tính MAC.

Nối trường bằng dấu phân cách đơn giản cũng chưa chắc an toàn nếu dấu ấy có thể xuất hiện trong dữ liệu. Ví dụ:

```text
tenantId + "|" + requestId

("a|b", "c") -> "a|b|c"
("a", "b|c") -> "a|b|c"
```

Những giải pháp tốt:

1. **Độ dài trước trường (length prefix):** ghi độ dài byte cố định 4 byte rồi ghi đúng số byte đó; parser có thể đọc lại ranh giới.
2. **Mã hóa cấu trúc có chuẩn:** dùng deterministic CBOR / canonical JSON profile được chỉ định và kiểm thử chéo.
3. **Delimiter + escape chặt chẽ:** chỉ nếu protocol công bố escape rules một nghĩa và kiểm thử đầy đủ, tránh tự nghĩ escaping.
4. **Trường có kiểu/độ rộng cố định:** integer 64-bit, version byte, boolean 0/1, enum có miền giá trị giới hạn.

### 3.1. Hợp đồng binary cụ thể cho ví dụ payment

Ta chọn một profile minh họa `PAYMENTS-HMAC-V1`, bao gồm các trường theo đúng thứ tự:

| Vị trí | Trường | Encoding | Ghi chú |
| --- | --- | --- | --- |
| 1 | `version` | 1 byte giá trị `0x01` | Cố định theo phiên bản protocol |
| 2 | `domain` | 4-byte length + UTF-8 bytes của `payments.request` | Không cho dùng cùng tag trong protocol khác |
| 3 | `tenantId` | 4-byte length + UTF-8 bytes | Ràng buộc tenant |
| 4 | `requestId` | 4-byte length + UTF-8 bytes | Dùng ở lớp replay/idempotency |
| 5 | `amountMinor` | Integer signed 64-bit, **big-endian**, chính xác 8 byte | 1299 nghĩa là 12,99 đơn vị khi tiền tệ có 2 chữ số thập phân |
| 6 | `currency` | 4-byte length + UTF-8 bytes | Ví dụ `USD`, chuẩn hóa/kiểm tra theo policy |
| 7 | `tag` | **Không** nằm trong MAC input | Tính HMAC sau khi đã serialize 6 trường trên |

Trong đó:
- Mỗi length prefix là unsigned không âm được biểu diễn bằng `writeInt` 4 byte big-endian và bị giới hạn tối đa **65.535 byte** ở ví dụ.
- `writeLong` của Java dùng **8 byte big-endian**. Ngôn ngữ khác phải tuân thủ cùng số byte và signed representation; không gửi số tiền dạng `double` hay chuỗi theo locale.
- Chuỗi được mã hóa bằng `StandardCharsets.UTF_8`. Trong minh họa, không thực hiện Unicode normalization ngầm. Hệ thống thật phải định nghĩa rõ policy chấp nhận/reject/normalize đầu vào trước khi serialize.
- `version` và `domain` làm rõ thông điệp này thuộc dạng “payment request, v1”, tránh cùng một chuỗi byte bị hiểu thành thông điệp loại khác (cross-protocol confusion).
- Các giá trị `tenantId` và `requestId` **phải được phía nhận kiểm tra với danh tính và trạng thái nghiệp vụ đáng tin**, không coi những giá trị client khai báo là tự động có quyền.

Sơ đồ byte:

```text
01
00000010 | UTF-8("payments.request")
00000008 | UTF-8("tenant-A")
00000005 | UTF-8("req-7")
0000000000000513
00000003 | UTF-8("USD")
   |
   +--> HMAC-SHA256(K, all preceding bytes) => 32 tag bytes
```

Độ dài `0x10 = 16` byte cho `payments.request`; `0x08 = 8` cho `tenant-A`; `0x05 = 5` cho `req-7`; `0x0513 = 1299` trong trường số 8 byte.

Cặp input cố định sẽ dùng làm test vector:

```text
version = 1
domain = payments.request
tenantId = tenant-A
requestId = req-7
amountMinor = 1299
currency = USD
key = UTF-8("0123456789abcdef0123456789abcdef")  // only for a public demo

Canonical input (hex):
01000000107061796d656e74732e726571756573740000000874656e616e742d41000000057265712d37000000000000051300000003555344
```

**Không dùng khóa cố định công khai này trong sản phẩm.** Nó là fixture để hai phía có thể so sánh từng byte trong bài học, tương tự một test vector.

### 3.2. Nguyên tắc với dữ liệu thiếu và kiểu dữ liệu

Định nghĩa protocol cần trả lời từng trường:

- Trường **bắt buộc** thiếu thì từ chối trước khi tính/kiểm tra; không tự coi bằng chuỗi rỗng.
- Nếu **nullable** có ý nghĩa, phải thêm byte đánh dấu trạng thái hoặc một encoding quy định rõ khác biệt `absent/null/value`.
- Nếu cho phép **mảng**, phải ghi count và encoding của từng phần tử, công bố thứ tự có nghĩa hay phải sort. Nếu sort, dùng cùng comparator theo byte/chuẩn, không dựa vào locale mỗi máy.
- Nếu cho phép **map**, phải quy định thứ tự key, cách xử lý duplicate key và Unicode. Không dùng thứ tự lặp của `HashMap` làm wire contract.
- Nếu có **số thập phân**, chọn đơn vị nhỏ nhất dạng integer (`amountMinor`) hoặc dạng decimal canonical rõ ràng; không phụ thuộc `BigDecimal.toString()` ở các hệ khác khi chưa có hợp đồng.
- Với **thời gian**, ưu tiên epoch UTC theo đơn vị xác định, chẳng hạn signed int64 milliseconds; nếu chọn ISO 8601, bắt buộc một dạng chính xác cùng fractional digits/timezone.

Dữ liệu ngoài miền hợp lệ phải bị từ chối có kiểm soát. **Canonicalization không thay thế schema validation hoặc kiểm tra quyền.**

## 4. Đối với JSON và HTTP, cần quyết định miền byte được ký

### 4.1. Có thể dùng JSON, nhưng cần một profile cụ thể

Nếu chọn canonical JSON, không chỉ nói chung “sort keys”. Cần công bố cụ thể chuẩn, ví dụ **JSON Canonicalization Scheme (JCS, RFC 8785)** khi phù hợp: quy tắc về property order, serialization của string và number, và các ràng buộc JSON/I-JSON. JSON interop còn cần chú ý độ chính xác số nguyên lớn vượt miền biểu diễn chính xác của IEEE 754, duplicate property, Unicode, escape sequences và kiểu dữ liệu.

Ví dụ truyền thống:

```json
{"currency":"USD","amount":1299,"requestId":"req-7"}
```

Tránh giả định một framework serializer Java hoặc JavaScript bất kỳ sẽ tạo byte giống nhau chỉ vì cả hai cho kết quả JSON có vẻ tương đương. Nếu chọn JCS, dùng implementation tuân thủ chuẩn và test vector giao tiếp. Nếu yêu cầu số nguyên 64 bit chính xác giữa Java và JavaScript, có thể phải biểu diễn theo **chuỗi số dạng chuẩn** hoặc dùng định dạng binary có hỗ trợ số nguyên xác định.

Đặc biệt, khi verify chữ ký/MAC trên raw JSON, parser ứng dụng **không nên chấp nhận các dạng nhập nhằng** (như duplicate property khác cách xử lý) khiến byte được xác thực và object thực thi có ngữ nghĩa khác nhau.

### 4.2. Đối với HTTP request

Khi xác thực API bằng MAC, “ký body” chỉ là một phần. Hợp đồng cần chỉ rõ những thông tin nào ảnh hưởng đến ý nghĩa request:

- Method (`POST` hay `GET`) và path, route, query parameter nào được bao gồm?
- Host, tenant, resourceId, user/service principal, content type và body nào phải bảo vệ?
- Có timestamp, nonce hoặc requestId được bảo vệ bằng MAC không?
- Chính xác body bytes ở lớp nào: sau parsing, trước compression hay sau reverse proxy transformation?
- Nếu một proxy đổi header ordering, rewrite URL hay convert line endings, hai bên có còn dùng cùng canonical representation không?

Không ký mọi header không kiểm soát rồi hy vọng client/server đồng ý, vì proxy có thể thêm/bớt header. Cũng không ký thiếu dữ liệu có ý nghĩa: nếu MAC chỉ bảo vệ body nhưng route chuyển từ `/orders` sang `/refunds` mà không được ràng buộc, bên nhận có thể hiểu request theo một hành động khác.

Với HTTP, nên cân nhắc dùng chuẩn request-signature phù hợp và công bố rõ canonicalization profile. Nếu thiết kế giao thức nội bộ riêng, phải có fixture từ cả hai phía và test các biến thể proxy/HTTP stack.

## 5. Tag bytes và tag trên đường truyền

Với **HMAC-SHA256 đầy đủ**, kết quả `Mac.doFinal(...)` gồm **32 byte = 256 bit**. Các cách biểu diễn cùng tag:

| Cách biểu diễn | Kích thước đối với tag 32 byte | Đặc điểm |
| --- | --- | --- |
| Raw bytes | 32 byte | Phù hợp binary protocol; không phải UTF-8 text tùy ý |
| Hex lowercase | 64 ký tự ASCII | Dễ đọc/debug, tốn dung lượng gấp đôi raw |
| Base64 chuẩn có padding | 44 ký tự (thường kết thúc `=`) | Dùng ký tự `+` và `/`, có padding |
| Base64URL không padding | 43 ký tự ASCII | Dùng `-` và `_`, thuận tiện URL/header |

Vì **cùng một dãy 32 byte** có nhiều cách mã hóa, hai phía cần thống nhất:

1. Dạng wire được phép (ví dụ Base64URL không padding), đúng bảng chữ cái và quy tắc padding.
2. Case của chuỗi hex; có cho phép chữ hoa không? Nếu có phải quy định nhất quán.
3. Độ dài tag sau giải mã (ví dụ **đúng 32 byte**). Không so sánh độ dài string để thay thế kiểm tra byte.
4. Có cho phép whitespace, xuống dòng, tiền tố `0x` hay ký tự phân cách không? Nên chọn dạng canonical duy nhất và từ chối định dạng khác.
5. Chuỗi tag được truyền ở trường nào, có phần khác cùng tên hoặc duplicate header không, có bị URL/form decoding biến đổi không?
6. Chính sách từ chối tag sai/hết hạn và phản hồi lỗi không tiết lộ chi tiết nội bộ.

**Đừng bao giờ** chuyển raw tag bytes bằng `new String(tagBytes, UTF_8)`: tag là dữ liệu nhị phân không bảo đảm tạo thành UTF-8 hợp lệ. Cũng đừng so sánh chuỗi hex bên gửi với chuỗi Base64 bên nhận: phải decode theo đúng profile trước khi so sánh.

### 5.1. Có nên rút ngắn HMAC tag?

Một số protocol quy định tag bị truncate còn `t` bit để tiết kiệm băng thông. Đây là **quyết định protocol** có hậu quả về độ khó giả mạo; không phải chuyện “cắt vài ký tự Base64 cho gọn”. Nếu truncate, phải quy định chính xác số **bit/byte đầu**, quy tắc encoding, độ dài tối thiểu, giới hạn số lần thử và threat model. Với thiết kế mới, ưu tiên **full 32-byte HMAC-SHA256** khi không có lý do chuẩn hóa đặc biệt để rút ngắn.

Nếu đối thủ có nhiều lần thử online với tag ngắn, cơ hội đoán đúng tăng theo số lần thử. Giới hạn rate, timeout, kiểm tra nonce/replay và xử lý thất bại an toàn vẫn cần thiết. Không chấp nhận client tự quyết định độ dài tag rồi server so sánh bao nhiêu byte client cung cấp.

### 5.2. Kiểm tra tag an toàn

Về nguyên tắc, verify:

1. Kiểm tra framing, format, độ dài, thuật toán/phiên bản được cho phép; từ chối dữ liệu malformed.
2. Xác định khóa đúng từ nguồn tin cậy và cấu hình chính sách; **không tin keyId tự khai như bằng chứng danh tính**.
3. Tự serialize đúng canonical bytes từ dữ liệu được phép xử lý.
4. Tính lại HMAC trên toàn bộ bytes, dùng API so sánh byte theo thời gian ít phụ thuộc nội dung, như `MessageDigest.isEqual(...)`, khi hai digest đã có độ dài mong đợi.
5. Chỉ sau khi MAC đúng mới xét freshness/replay và quyền nghiệp vụ trước khi tạo side effect.

Tránh `String.equals(...)` hoặc `Arrays.equals(...)` làm cơ chế so sánh cuối cùng giữa **tag kỳ vọng và tag bí mật do client gửi**, vì timing của phép so sánh thông thường có thể phụ thuộc nội dung/điểm lệch. Vẫn có các yêu cầu khác về xác thực, xử lý lỗi và mạng; một phép so sánh an toàn không bảo đảm toàn bộ giao thức không rò rỉ thông tin.

## 6. Java 17+: test vector HMAC trên binary canonical encoding

Ví dụ sau cố định thuật toán, thứ tự và format; kết quả HMAC trên một request giống nhau phải tái lập được giữa các hệ triển khai.

Tạo tệp `MacWireDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MacWireDemo {
    record Payment(String tenantId, String requestId, long amountMinor, String currency) {}

    // Public demo key for reproducing a test vector; never use in production.
    private static final byte[] KEY = "0123456789abcdef0123456789abcdef"
            .getBytes(StandardCharsets.UTF_8);

    private static void field(DataOutputStream out, String value) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > 65_535) throw new IllegalArgumentException("field too long");
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static byte[] canonical(Payment p) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeByte(1);                    // protocol version
            field(out, "payments.request");      // domain separation
            field(out, p.tenantId());
            field(out, p.requestId());
            out.writeLong(p.amountMinor());      // 8 bytes, big endian
            field(out, p.currency());
        }
        return buffer.toByteArray();
    }

    static byte[] hmac(Payment p) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(KEY, "HmacSHA256"));
        return mac.doFinal(canonical(p));
    }

    static String base64url(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    static boolean verify(Payment p, String wireTag) throws Exception {
        byte[] received;
        try {
            received = Base64.getUrlDecoder().decode(wireTag);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
        if (received.length != 32 || !base64url(received).equals(wireTag)) return false;
        return MessageDigest.isEqual(hmac(p), received);
    }

    public static void main(String[] args) throws Exception {
        Payment original = new Payment("tenant-A", "req-7", 1299, "USD");
        String tag = base64url(hmac(original));
        System.out.println("Input hex: " + HexFormat.of().formatHex(canonical(original)));
        System.out.println("Tag (base64url): " + tag);
        System.out.println("Tag bytes: " + Base64.getUrlDecoder().decode(tag).length);
        System.out.println("Original verified: " + verify(original, tag));
        System.out.println("Amount changed verified: "
                + verify(new Payment("tenant-A", "req-7", 1399, "USD"), tag));
        System.out.println("Tenant changed verified: "
                + verify(new Payment("tenant-B", "req-7", 1299, "USD"), tag));
        System.out.println("Malformed tag verified: " + verify(original, "invalid+tag"));
        System.out.println("Same request replay verified: " + verify(original, tag));
    }
}
```

Biên dịch và chạy:

```bash
javac MacWireDemo.java
java MacWireDemo
```

Stdout chính xác của ví dụ với JDK 17+:

```text
Input hex: 01000000107061796d656e74732e726571756573740000000874656e616e742d41000000057265712d37000000000000051300000003555344
Tag (base64url): nEOzXhbbnYCVX0rn1leWKWA-OR9mZLAraX4FJOfZArU
Tag bytes: 32
Original verified: true
Amount changed verified: false
Tenant changed verified: false
Malformed tag verified: false
Same request replay verified: true
```

**Giải thích những điểm thiết yếu:**

- `canonical()` là **hợp đồng byte**, không phải serialization ngầm của Java record. DataOutputStream ghi theo thứ tự cố định; `writeInt` là length prefix 4 byte, `writeLong` là số 8 byte big-endian.
- `field()` dùng UTF-8 byte length, **không dùng Java `String.length()`** vì `String.length()` đếm UTF-16 code units. Với các ký tự ngoài ASCII, số byte UTF-8 thường khác độ dài chuỗi Java.
- `Mac.getInstance("HmacSHA256")` tính **HMAC-SHA256**; `SecretKeySpec` chỉ biểu diễn key bytes và tên thuật toán, không tự bảo vệ khóa khỏi lộ.
- `base64url()` thống nhất URL-safe alphabet và bỏ padding. Bên nhận decode, kiểm tra đúng 32 byte và mã hóa lại để yêu cầu **canonical wire representation** trước khi so sánh.
- `MessageDigest.isEqual(...)` so sánh **tag bytes**, không so sánh chuỗi biểu diễn hoặc bản tin text.
- Thay số tiền từ 1299 thành 1399, hoặc đổi tenant, tạo input MAC khác nên verify `false`.
- `"invalid+tag"` chứa ký tự `+` không thuộc alphabet Base64URL, bị từ chối. Các dạng wire sai encoding/length cũng phải bị từ chối.
- **Đáng chú ý:** dòng `Same request replay verified: true` là **đúng**. HMAC không tự chống replay. Hai request giống hệt nhau cho cùng tag; server thật phải xử lý `requestId` theo cơ chế freshness, chống replay hoặc idempotency có trạng thái.
- Khóa hardcoded, business validation chưa hoàn chỉnh và không có replay store vì ví dụ nhằm chứng minh **byte contract và tag format**. Trong môi trường thật, lấy khóa từ hệ thống quản lý bí mật, kiểm tra miền giá trị đầu vào và áp quyền/giới hạn thời gian.

### 6.1. Cách tạo test vector cho hệ thống thứ hai

Gửi cho đội implement bằng ngôn ngữ khác **đầy đủ**:

1. Phiên bản protocol và định dạng byte ở bảng phần 3, gồm byte order và length prefix.
2. Dữ liệu đầu vào đúng giá trị: `tenant-A`, `req-7`, integer `1299`, `USD`.
3. Khóa demo đúng **32 ASCII byte**, không phải hex-decoded key: `0123456789abcdef0123456789abcdef`.
4. Canonical input ở dạng hex: cả chuỗi phải khớp chính xác trước khi tính HMAC.
5. Tag HMAC-SHA256 ở dạng Base64URL **không padding**: `nEOzXhbbnYCVX0rn1leWKWA-OR9mZLAraX4FJOfZArU`.
6. Test âm: đổi amount/tenant, sai key, sai version, đảo thứ tự trường, tag sai format và tag sai độ dài.

Khi một bên không tạo đúng tag, bước đầu tiên là so sánh **hex của canonical bytes**, rồi mới xét key bytes, thuật toán và tag encoding. Không nên “sửa cho chạy” bằng cách trim, sort hoặc chuyển Base64/hex ngầm trên server.

### 6.2. Cùng data model nhưng khác thứ tự = khác MAC input

Giả sử một client viết các trường theo thứ tự `tenantId, requestId, currency, amountMinor`, trong khi server viết `tenantId, requestId, amountMinor, currency`. Dù chúng có cùng giá trị nghiệp vụ, byte sẽ khác nhau; tag từ client không thể xác minh theo quy tắc server.

Tương tự, nếu client ghi length prefix 4 byte theo little-endian còn server đọc big-endian, parser có thể hiểu độ dài sai hoặc xác minh HMAC trên byte khác. **Endian là một phần của giao thức**, không phải chi tiết để runtime tự chọn.

Không sửa vấn đề bằng việc cho server thử nhiều thứ tự, nhiều kiểu encoding hoặc nhiều thuật toán đến khi có một tag đúng. Cơ chế “thử mọi cách” có thể mở ra các biểu diễn nhập nhằng và làm mất ý nghĩa version/security policy.

## 7. Ranh giới giữa canonicalization, integrity, identity và replay

### 7.1. MAC chứng minh những byte được bảo vệ, không chứng minh mọi điều

Tag chỉ có thể bảo vệ **các trường thực sự đã đưa vào input**. Nếu amount được ký nhưng currency không ký, đối thủ có thể tìm cách đổi `USD` sang tiền tệ khác mà tag không phát hiện nếu server không ràng buộc currency bằng nơi khác.

Ví dụ trong hệ thống nhiều tenant:
- `tenantId` phải nằm trong input MAC **và** server phải kiểm tra tenant đó được phép dùng khóa/principal hiện tại.
- `resourceId` hoặc route định hướng quyền cũng nên được ràng buộc nếu chúng ảnh hưởng đến nghiệp vụ.
- Các thành phần như `keyId` và `algorithm` nếu truyền trong envelope phải đi theo profile tin cậy: keyId dùng tra khóa đã cấp quyền, algorithm được lựa chọn bằng allowlist/chính sách server; không cho client ép giải mã/verify bằng thuật toán khác.
- `version` phải được xác thực hoặc nằm trong signed/MAC input để ngăn đổi cách diễn giải payload mà vẫn giữ tag.

**Dữ liệu được bảo vệ toàn vẹn chưa chắc là dữ liệu đáng tin về nghiệp vụ.** Nếu client hợp lệ dùng khóa HMAC nhưng không có quyền thanh toán cho tenant khác, MAC vẫn có thể đúng; authorization phải độc lập kiểm tra quyền.

### 7.2. MAC hợp lệ không tự chứng minh request là mới

Hình dung một lệnh chuyển tiền có cùng `tenantId`, `requestId`, `amountMinor` và tag được gửi hai lần. Cả hai lần có thể vượt qua HMAC. Server phải kiểm tra request đã được xử lý hay chưa.

Các cơ chế thường phối hợp:
- **Request ID/idempotency key:** ghi nhận trong kho trạng thái với phạm vi principal/tenant; nhiều lần gửi cùng lệnh trả kết quả đã xử lý hoặc bị từ chối theo hợp đồng.
- **Timestamp + allowed clock skew:** đặt trong MAC input; từ chối request quá hạn nhưng timestamp một mình không ngăn replay bên trong cửa sổ thời gian.
- **Nonce hoặc sequence number:** đưa vào MAC input; receiver theo dõi tính duy nhất/thứ tự phù hợp (và xử lý retry/chạy nhiều instance).
- **Token dùng một lần hoặc challenge-response** khi workflow cần bảo đảm freshness mạnh hơn.

Trong hệ thống phân tán, replay store cần atomicity/consistency; nếu hai server xử lý đồng thời một `requestId` mà chỉ kiểm tra bằng cache cục bộ, lệnh có thể chạy hai lần dù MAC đúng.

## 8. Versioning, rotation và tương thích nhiều phiên bản

Giao thức MAC phải có **định danh phiên bản rõ ràng**. Khi thêm trường `merchantId`, đổi precision của `amountMinor` hoặc chuyển từ text delimiter sang length-prefix, cần tạo profile mới chứ không âm thầm thay encoding của v1.

Ví dụ envelope để mô tả thành phần truyền, không phải byte contract cuối cùng:

```json
{
  "version": 1,
  "keyId": "payments-prod-2026-10",
  "tenantId": "tenant-A",
  "requestId": "req-7",
  "amountMinor": 1299,
  "currency": "USD",
  "tag": "nEOzXhbbnYCVX0rn1leWKWA-OR9mZLAraX4FJOfZArU"
}
```

Tag ở trên là **test vector cho khóa demo, domain và canonical bytes của phần 6**, không phải tag do khóa production tương ứng với ví dụ `keyId` tạo. Trường `keyId` trong envelope chỉ minh họa metadata định tuyến; trong một profile production có key rotation, phải công bố cách `keyId` được bind vào input MAC và cách receiver ánh xạ nó tới đúng khóa tin cậy. **Không dùng envelope minh họa làm yêu cầu triển khai nguyên xi.**

Khi chuyển phiên bản:
1. Ghi hồ sơ độc lập cho v1/v2: algorithms, fields, byte order, domain, tag length, encoding.
2. Server chỉ chấp nhận các phiên bản được policy cho phép; xác thực version trong MAC input.
3. Map `keyId` tới khóa có scope, chủ thể, trạng thái và thuật toán được phép; hạn chế đợt chấp nhận đồng thời nhiều key cũ.
4. Duy trì tập test vectors cho mỗi version và test các trường hợp không hợp lệ.
5. Có thời điểm kết thúc support version/khóa cũ; tránh fallback tự động khi verify thất bại.

Xoay khóa và nâng cấp format là hai việc khác nhau. Một payload v1 có thể còn cần khóa v1 trong cửa sổ tương thích, nhưng server không nên nới lỏng canonicalization để cho “hầu hết client cũ chạy được”.

## 9. Kiểm thử giao tiếp hai bên: kiểm tra gì?

Tối thiểu nên có test matrix theo nhóm:

| Nhóm | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Golden vector | Cùng key, cùng input, cùng version | Input hex và tag khớp 100% |
| Trường/thứ tự | Đảo `tenantId` và `requestId`, đổi amount/currency | Tag không xác minh theo profile v1 |
| Ranh giới | `("ab","c")` vs `("a","bc")` | Canonical bytes khác |
| Unicode | NFC/NFD, emoji, chuỗi rỗng, ký tự kết hợp | Theo policy; length tính bằng byte UTF-8 |
| Encoding | LF/CRLF, UTF-8/UTF-16, BOM | Từ chối/không khớp nếu không đúng profile |
| Số | Negative, overflow, 1.0 vs 1, big-/little-endian | Parser/schema rõ ràng; không chuyển kiểu âm thầm |
| Tag format | Hex thay Base64URL, padding, ký tự lạ, whitespace, sai length | Từ chối |
| Key/algorithm | Sai key, keyId revoked, thuật toán không cho phép | Từ chối |
| Protocol | Sai version, domain hoặc message type | Từ chối |
| Replay | Gửi lại request hợp lệ | Từ chối hoặc trả kết quả idempotent theo nghiệp vụ |
| Authorization | HMAC đúng nhưng tenant/resource không thuộc principal | Từ chối |
| Concurrency | Hai request cùng ID tới hai instance | Không tạo side effect hai lần |

**Test giao tiếp chéo ngôn ngữ:** ít nhất một bộ golden vector do hai implementation độc lập tính. Không chỉ kiểm tra rằng client Java tự verify được MAC do chính Java tạo: test này sẽ bỏ sót lỗi mà Java và đối tác dùng cách serialize khác nhau.

### 9.1. Phân tích từng byte khi gặp mismatch

Trình tự debug thực dụng, giữ bí mật khóa và dữ liệu nhạy cảm:

1. Xác nhận hai phía thực sự dùng **cùng profile** (version, domain, algorithm, tag length, encoding).
2. So sánh schema/validation và các trường được chọn đưa vào MAC; lưu ý route, tenant và requestId.
3. So sánh **độ dài và canonical input bytes** trong môi trường thử nghiệm dùng fixture không nhạy cảm. Nếu bytes khác, tìm điểm khác đầu tiên: delimiter, UTF-8, endianness, thứ tự, newline, số, escape.
4. Nếu bytes trùng, kiểm tra cách nạp khóa (raw text bytes so với hex/Base64 decoded bytes), key version và cách dẫn xuất khóa. **Không log production key** để debug.
5. Nếu MAC bytes trùng mà tag text không trùng, kiểm tra Base64/Base64URL/hex, padding, chữ hoa/thường và whitespace.
6. Nếu tag đúng nhưng request bị từ chối, xem chính sách thời gian, replay/idempotency, mapping identity, quyền và validation; đừng bỏ qua kiểm tra chỉ để “qua test”.

Trong production, chỉ ghi log thông tin cần thiết để định vị lỗi như profile id, độ dài input, tên nhóm trường, mã lỗi, correlation ID. Không log key, tag nhạy cảm khi không cần, body chứa dữ liệu cá nhân hoặc dữ liệu thanh toán. Hash của dữ liệu nhạy cảm cũng có thể lộ thông tin nếu đầu vào ít entropy; không coi logging digest là tự động an toàn.

## 10. Các lỗi điển hình và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Client ký JSON gốc, server ký JSON đã parse rồi serialize lại | Byte khác do thứ tự/spacing | Cùng ký raw bytes hoặc áp canonical profile |
| Nối `tenantId + requestId` mà không phân cách | Hai cặp trường khác nhau cùng input | Length prefix/serialization không nhập nhằng |
| Dùng delimiter mà không escape | `a\|b` gây nhập nhằng | Length prefix hoặc quy tắc escape chuẩn |
| Dùng `String.length()` ghi độ dài cho chuỗi UTF-8 | Độ dài UTF-16 không bằng byte length | Lấy `value.getBytes(UTF_8).length` |
| Một phía ghi 1299 là 4 byte little-endian, phía kia ghi 8 byte big-endian | Kiểu và thứ tự byte khác | Thống nhất width, signedness, endian |
| String có Unicode tổ hợp khác | Input bytes khác | Chốt chính sách normalization và canonical encoding |
| Một phía nhận `null` là trống, phía kia bỏ trường | Schema khác | Định nghĩa absent/null/empty riêng |
| Server nhận cả truncated tag tùy độ dài client gửi | Tag length không ràng buộc | Kiểm tra độ dài cố định và profile |
| Phía gửi xuất hex, phía nhận giải Base64 | Wire tag sai codec | Một encoding canonical và test vector |
| So sánh tag bằng string thông thường | Có thể tạo timing leak | Decode, kiểm tra length, so sánh bytes bằng API phù hợp |
| Cho phép client tự chọn `alg` hoặc tự gán `keyId` | Algorithm/key confusion | Server allowlist, registry khóa và scope |
| Chỉ ký body, không ký tenant/action | MAC không bao phủ nghiệp vụ | Bind đủ context vào input, kiểm tra quyền |
| Nhận tag đúng nhưng xử lý lại giao dịch | Thiếu replay/idempotency | Trạng thái atomic theo principal/requestId |
| Chọn lại nhiều schema tới khi một tag pass | Fallback nhập nhằng | Version chặt, chỉ thử cấu hình được định nghĩa |
| Test chỉ toàn positive case | Bỏ lọt tamper, replay, encoding lỗi | Test vector âm và test giao tiếp chéo nền tảng |

## 11. Checklist thiết kế một profile MAC có thể triển khai

Trước khi hai đội bắt đầu code, viết thành văn bản **một hợp đồng kiểm chứng được**:

- **Purpose:** giao thức xác thực loại bản tin nào, danh tính nào, tenant nào, cấp quyền nào; giới hạn những bảo đảm của MAC.
- **Version/domain:** byte version, domain separation, algorithm, danh sách phiên bản được phép.
- **Keys:** nguồn sinh/lưu, độ dài byte, danh tính sở hữu, vòng đời, `keyId`, cách chọn key an toàn và policy rotation.
- **Input fields:** danh sách có thứ tự, bắt buộc/tùy chọn, phạm vi giá trị và các trường nghiệp vụ được bảo vệ.
- **Canonical encoding:** UTF-8/Unicode policy, length prefix, integer width/endian, decimal/time, null/missing/empty, thứ tự map/list, JSON hoặc binary format.
- **Tag:** raw length, algorithm, truncation policy, encoding, padding/case và vị trí trong request.
- **Verification:** chuẩn hóa/validate ở đâu, fail closed khi sai tag, so sánh an toàn, duplicate field/header xử lý ra sao.
- **Freshness và quyền:** timestamp/nonce/requestId, replay store, idempotency, binding với principal và authorization từng operation.
- **Conformance:** golden vectors được chạy bởi cả hai phía, negative cases, hành vi version/rotation/error có tài liệu.

### Câu hỏi ôn tập

**1. Hai phía đều dùng đúng HMAC-SHA256 và cùng khóa nhưng tag khác. Có phải HMAC bị lỗi?**

Không. Hãy kiểm tra canonical input bytes trước: serialization, trường, thứ tự, UTF-8, số, newline, version. Sau đó mới kiểm tra key bytes và wire tag encoding.

**2. Vì sao ký `tenantId + requestId` không có delimiter là nguy hiểm, ngay cả khi HMAC vẫn rất mạnh?**

Vì các cặp giá trị khác nhau có thể tạo **cùng byte đầu vào** (ví dụ `ab`+`c` và `a`+`bc`). Bản tin khác nhau theo nghiệp vụ lại có MAC bằng nhau theo thiết kế; lỗi ở encoding chứ không phải tấn công HMAC.

**3. Khi hai trường JSON đổi thứ tự, MAC có bắt buộc giống nhau không?**

Nếu MAC tính trên raw JSON bytes thì **khác**. Nếu cả hai dùng đúng một canonical JSON profile đưa về cùng bytes thì **giống** cho dữ liệu được định nghĩa là tương đương. Không có hành vi ngầm định độc lập với profile.

**4. Một tag HMAC-SHA256 đầy đủ dài bao nhiêu? Chuỗi Base64URL không padding dài bao nhiêu?**

Raw tag dài **32 byte**. Với 32 byte, Base64URL không padding dài **43 ký tự ASCII**. Chuỗi hex tương ứng dài **64 ký tự**.

**5. Vì sao server vẫn phải kiểm tra requestId sau khi MAC hợp lệ?**

Vì attacker có thể gửi lại **nguyên request và tag**. HMAC không phát hiện tính mới; cần chống replay/idempotency có trạng thái và kiểm tra quyền nghiệp vụ.

**6. Có thể chỉ kiểm tra HMAC đúng rồi cho tenant của payload toàn quyền không?**

Không. Một bên có khóa có thể tạo tag hợp lệ cho dữ liệu mà họ không có quyền thực hiện. Server phải ràng buộc khóa với principal tin cậy và kiểm tra authorization của principal trên tenant/action/resource cụ thể.

**7. Trong ví dụ Java, vì sao cần dùng `writeInt(bytes.length)`, không dùng `writeInt(value.length())`?**

`DataOutputStream` ghi length theo byte để parser đọc đúng ranh giới. `String.length()` đếm UTF-16 code units và không đồng nhất với số byte UTF-8 khi có ký tự ngoài ASCII.

**8. Muốn thêm trường mới vào thông điệp MAC, có nên thử cả format cũ và format mới cho từng request đến khi verify thành công?**

Không. Phải công bố version/schema mới, xác thực version trong MAC input, kiểm soát chính sách chấp nhận. Thử nhiều cách tùy tiện dễ gây nhập nhằng và suy yếu protocol.

## 12. Kết luận

Một MAC chỉ xác thực **đúng những byte mà hai bên đã thống nhất**. Độ mạnh của HMAC-SHA256 không bù được việc ghép trường nhập nhằng, serialize JSON khác nhau, mất field nghiệp vụ, nhầm tag encoding hay tin một request hợp lệ được phép thực thi lại.

Hợp đồng liên thông cần rõ từ **ngữ nghĩa dữ liệu → thứ tự/kiểu trường → canonical byte encoding → thuật toán/khóa → raw tag → wire tag → xác minh và chính sách ứng dụng**. Một test vector ghi đủ **key demo, canonical input hex và expected tag** là cách nhanh nhất để chứng minh hai phía hiểu giống nhau trước khi xử lý dữ liệu thật.

### Tài liệu tham khảo

- RFC 2104 — *HMAC: Keyed-Hashing for Message Authentication*: https://www.rfc-editor.org/rfc/rfc2104
- RFC 4231 — *Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512*: https://www.rfc-editor.org/rfc/rfc4231
- RFC 8785 — *JSON Canonicalization Scheme (JCS)*: https://www.rfc-editor.org/rfc/rfc8785
- Java SE 17, `javax.crypto.Mac`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
- Java SE 17, `java.io.DataOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html
- Java SE 17, `java.util.Base64`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html
- Java SE 17, `java.security.MessageDigest`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
