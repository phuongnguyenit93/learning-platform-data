# Mô tả quy ước phân trang, thời gian, số và giá trị null

Một REST API có thể đúng HTTP, đúng JSON và vẫn gây lỗi tích hợp nếu tài liệu không nói rõ `page=1` là trang đầu tiên hay thứ hai, `2026-11-18T09:30:00` thuộc múi giờ nào, `9007199254740993` có thể được JavaScript đọc chính xác không, hoặc trường `address: null` nghĩa là “xóa địa chỉ” hay “giữ nguyên”. Các lỗi này thường không xuất hiện trong happy-path test; chúng xảy ra khi dữ liệu lớn, thay múi giờ, retry hoặc nâng cấp client.

Trong chương **Tài liệu và trải nghiệm** của module `INTEGRATION_API_REST`, bài học hướng dẫn **viết một hợp đồng dữ liệu có thể thực thi và kiểm thử được**. Trọng tâm là bốn nhóm quy ước phải nhất quán giữa URI, HTTP, OpenAPI, JSON, Java/Spring, cơ sở dữ liệu và SDK: **phân trang, thời gian, số, giá trị null**. Ví dụ dùng API quản lý đơn hàng, nhưng nguyên tắc áp dụng cho tài nguyên bất kỳ.

Sau bài học, người học có thể thiết kế tài liệu giúp client tự trả lời: request nào hợp lệ; dữ liệu có đơn vị gì; trường hợp không có giá trị được biểu diễn thế nào; phải làm gì ở trang cuối; lúc nào giá trị là một breaking change; và test nào bảo vệ những cam kết đó.

## 1. Biến quy ước thành hợp đồng công khai

**Đừng bắt client suy đoán từ một JSON mẫu.** Hãy mở đầu API reference bằng một bảng quy ước dùng chung, sau đó mô tả ngoại lệ ngay tại từng operation.

| Khía cạnh | Quy ước minh họa xuyên suốt | Điều cần ghi trong tài liệu |
| --- | --- | --- |
| Danh sách | `page` bắt đầu từ **0**, `size` mặc định **20**, tối đa **100** | Giá trị hợp lệ, thứ tự mặc định, trang rỗng, metadata |
| Thứ tự | `createdAt DESC, id DESC` | Tie-breaker để hai item cùng timestamp không đảo thứ tự |
| Liên kết trang | `hasNext` và `links.next` | Khi nào link là null/không có, giữ filter ra sao |
| API tải nhiều bản ghi | Có lựa chọn **cursor** với tham số `limit`, `after` | Không dùng lẫn cursor và page trên cùng request |
| Thời điểm | Chuỗi RFC 3339 có offset, **response chuẩn hóa UTC** với `Z` | Ví dụ, precision, loại thời gian, cách parse |
| Ngày lịch | `YYYY-MM-DD`, **không tự thêm timezone** | Ngày sinh, ngày bắt đầu/chấm công, không phải instant |
| Duration | ISO 8601, ví dụ `PT15M`; hoặc số với đơn vị rõ trong tên trường | Không dùng số trần mà không biết giây hay mili-giây |
| Số lượng | JSON integer và giới hạn business | Giá trị âm/0/giới hạn lớn nhất, overflow |
| Tiền | `amountMinorUnits` theo mã tiền; hoặc **decimal string** được công bố rõ | Currency, precision, rounding, range |
| Identifier | Chuỗi, dù ID trong database là `BIGINT` | Không dùng JSON number với ID vượt giới hạn JavaScript |
| Trường thiếu / null | Nghĩa riêng cho **response**, **POST**, **PUT**, **PATCH** | Không coi thiếu và null là giống nhau mọi nơi |
| Lỗi hợp đồng | 400/422/409/415 theo quy ước cùng `application/problem+json` | Mã lỗi ổn định và ví dụ |

Con số trên là **quyết định thiết kế cho API ví dụ**, không phải REST quy định mọi hệ thống phải chọn page từ 0 hoặc size tối đa 100. Sản phẩm có thể chọn cách khác, nhưng phải công bố một lần, lặp nhất quán và kiểm thử.

### Ví dụ hợp đồng list

~~~http
GET /v1/orders?page=0&size=2&status=CONFIRMED HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "data": [
    {
      "id": "order-102",
      "createdAt": "2026-11-18T09:15:30.123Z",
      "status": "CONFIRMED",
      "totalMinorUnits": 125000,
      "currency": "VND",
      "note": null
    },
    {
      "id": "order-101",
      "createdAt": "2026-11-18T09:15:29.500Z",
      "status": "CONFIRMED",
      "totalMinorUnits": 98000,
      "currency": "VND",
      "note": "Giao giờ hành chính"
    }
  ],
  "page": 0,
  "size": 2,
  "hasNext": true,
  "links": {
    "next": "/v1/orders?page=1&size=2&status=CONFIRMED"
  }
}
~~~

Ví dụ giả định còn ít nhất một đơn sau hai đơn đã liệt kê. `totalMinorUnits` là số nguyên đơn vị nhỏ nhất của đồng tiền được dùng; với VND trong hợp đồng ví dụ là đơn vị **đồng**. `note: null` nghĩa là **đơn không có ghi chú**, không phải ghi chú đã bị che vì thiếu quyền. Không có `totalCount` vì endpoint này không cam kết đếm tổng số.

Đừng bỏ một filter khi dựng link trang kế: nếu request có `status=CONFIRMED` mà `next` không chứa status, trang sau có thể là tập dữ liệu hoàn toàn khác.

## 2. Phân trang offset: page, size, sort và metadata

**Offset pagination** thường có hai biến thể: `page/size` hoặc `offset/limit`. Đừng pha trộn cách hiểu mà không công bố công thức. Bài này chọn:

\[
\mathrm{offset}=\mathrm{page}\times\mathrm{size},\qquad
\mathrm{page}\ge 0,\quad 1\le\mathrm{size}\le100.
\]

`page=0` lấy các item đầu; `page=1` bắt đầu từ item thứ `size+1` theo thứ tự đã chọn. `size` mặc định 20. Giá trị rỗng, không phải số, âm, 0 hoặc vượt giới hạn phải được xử lý nhất quán; không lặng lẽ chuyển `size=10000` thành 100 nếu hợp đồng nói sẽ báo lỗi.

| URL | Kết quả theo quy ước ví dụ |
| --- | --- |
| `/v1/orders` | Trang 0, size 20, sort mặc định |
| `/v1/orders?page=0&size=20` | Tương đương mặc định |
| `/v1/orders?page=1&size=20` | Tập 20 item tiếp theo, theo thứ tự cố định |
| `/v1/orders?page=9&size=20` khi chỉ có 30 item | `200 OK` với `data: []`, `hasNext: false` |
| `/v1/orders?page=-1` | 422 theo chính sách validation đã chọn |
| `/v1/orders?size=0` hoặc `size=101` | 422 |
| `/v1/orders?page=abc` | 400 vì không parse được kiểu số |
| `/v1/orders?size=10&size=50` | Phải có chính sách rõ: từ chối duplicate parameter hoặc parse theo quy tắc cố định |

**Trang ngoài phạm vi thường không phải 404**: resource bộ sưu tập vẫn tồn tại; tập con đang hỏi không có phần tử. Hệ thống có thể chọn semantics khác nhưng phải ghi trong hợp đồng và test. Nếu hết dữ liệu, trả:

~~~json
{
  "data": [],
  "page": 9,
  "size": 20,
  "hasNext": false,
  "links": {"next": null}
}
~~~

### 2.1. Sort ổn định và khả năng thay đổi dữ liệu

`ORDER BY created_at DESC` **chưa đủ** nếu nhiều bản ghi có cùng `created_at`. Thêm khóa duy nhất `id DESC` để có thứ tự xác định; index và kiểu ID phải hỗ trợ thứ tự đã chọn. Khi cho client chọn sort, chỉ whitelist các field cho phép, quy định dấu `+/-` hoặc `field,asc` rõ ràng và tự thêm tie-breaker.

Offset không bảo đảm ảnh chụp bất biến: khi một order mới được chèn vào đầu danh sách giữa hai lần GET, item ở cuối trang trước có thể xuất hiện lại ở trang sau; khi item bị xóa, một item có thể bị bỏ qua. Đây là **đặc tính khi đọc tập dữ liệu đang đổi**, không phải lỗi JSON. Nếu yêu cầu snapshot, phải thiết kế mốc phiên bản, thời điểm chốt dữ liệu hoặc cơ chế nhất quán phù hợp, không chỉ thêm `ORDER BY`.

### 2.2. `hasNext`, `totalCount` và `Link`

Có hai kiểu contract phổ biến:

- **Có tổng số:** `totalElements`, `totalPages`, `page`, `size`; thường yêu cầu câu `COUNT` hoặc thống kê riêng. Phải nói tổng chính xác hay ước lượng, có áp cùng quyền/filter hay không.
- **Không có tổng:** `hasNext` và `next`; server có thể đọc `size+1` hàng để xác định còn trang tiếp. Phù hợp API list lớn và infinite scroll.

Ví dụ bài học chỉ cam kết **hasNext**, không có `totalCount`. Client không nên tự tạo “Trang 1/500” dựa trên số item hiện có. Nếu backend cung cấp tổng **ước lượng**, trường nên có tên và mô tả rõ (`estimatedTotalCount`), không giả vờ là con số chính xác.

Có thể cung cấp thêm HTTP `Link` theo quan hệ `rel="next"`:

~~~http
Link: </v1/orders?page=1&size=2&status=CONFIRMED>; rel="next"
~~~

Đây là cơ chế **tùy chọn**; tài liệu phải nói client đọc link ở body, header hay cả hai. Nếu body/header cùng tồn tại, chúng phải trỏ cùng trang. Khi không có trang tiếp, không phát link `next` (hoặc trả `links.next: null` theo schema cố định đã chọn). **Không đoán trang kế bằng cộng 1** nếu server dùng cursor.

### 2.3. Giới hạn size là phần của an toàn hệ thống

Page size rất lớn có thể gây tăng SQL rows, heap, thời gian serialize, băng thông và DB connection hold time. Nếu endpoint có quan hệ lồng hoặc `include=lines`, có thể đặt giới hạn riêng thấp hơn. `page × size` cũng có thể tràn kiểu số nguyên khi page rất lớn; validate trước và dùng kiểu đủ rộng cho phép nhân, hoặc giới hạn vùng offset hợp lý.

Security và privacy: `totalCount`/`hasNext` phải dựa trên **cùng phạm vi quyền** với dữ liệu trả về. Không để client suy ra số đơn của tenant khác qua count hoặc qua tốc độ query.

## 3. Cursor/keyset pagination: hợp đồng khác với offset

Với tập dữ liệu lớn hoặc người dùng cuộn liên tục, **cursor pagination** giúp tránh `OFFSET` quá sâu và giảm một số vấn đề trùng/thiếu khi có bản ghi mới. Nhưng cursor **không phải chỉ là page number mã hóa Base64**. Cursor thường lưu vị trí sau item cuối của trang trước, cùng thông tin xác định tập dữ liệu.

~~~http
GET /v1/orders?limit=2&status=CONFIRMED HTTP/1.1
Host: api.example.com
~~~

~~~json
{
  "data": [
    {"id":"order-102","createdAt":"2026-11-18T09:15:30.123Z"},
    {"id":"order-101","createdAt":"2026-11-18T09:15:29.500Z"}
  ],
  "hasNext": true,
  "nextCursor": "opaque-signed-cursor",
  "links": {
    "next": "/v1/orders?limit=2&status=CONFIRMED&after=opaque-signed-cursor"
  }
}
~~~

`opaque-signed-cursor` chỉ là ký hiệu trong tài liệu, không phải token có thể dùng thật. Server tạo cursor từ khóa sort cuối (ví dụ `createdAt` + `id`), các filter liên quan, phạm vi tenant và version/chính sách hết hạn; client chỉ lưu và gửi lại, **không tự sửa/giải mã**.

Ví dụ truy vấn PostgreSQL dưới cách sắp xếp `created_at DESC, id DESC`:

~~~sql
SELECT id, created_at, status, total_minor_units
FROM orders
WHERE tenant_id = :trusted_tenant
  AND status = :status
  AND (
    created_at < :cursor_created_at
    OR (created_at = :cursor_created_at AND id < :cursor_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Áp cùng sort/filter cho trang đầu, không có `after`. `id` phải có phép so sánh thứ tự phù hợp trong DB. Cursor phải được kiểm tra chữ ký/MAC hoặc lưu server-side, ràng buộc tenant, filters, sort, giới hạn/expiry theo chính sách; **Base64 không phải bảo mật**, và cursor không phải token cấp quyền.

| Chủ đề | Offset (`page/size`) | Cursor (`after/limit`) |
| --- | --- | --- |
| Truy cập trang số 50 | Dễ biểu diễn | Thường phải đi từ cursor trước hoặc dùng bookmark |
| Dữ liệu thêm vào đầu danh sách | Có thể trùng/thiếu item | Ổn định hơn nếu khóa sort bất biến |
| Trang sâu | `OFFSET` có thể tốn kém | Có thể tận dụng index theo sort/filter |
| Snapshot tuyệt đối | Không tự có | Cũng **không tự có** |
| Client contract | Index, size, sort, total/hasNext | Opaque token, expiry, next link, lỗi cursor |

Nếu chuyển endpoint từ offset sang cursor, đó thường là **breaking change** của query parameters và response, nên nên tạo endpoint hoặc version contract riêng. Tài liệu phải nêu rõ không dùng `page` cùng `after`; request cursor hết hạn hoặc không hợp lệ trả lỗi có cấu trúc (ví dụ 400 với `INVALID_CURSOR`), không trả dữ liệu của tenant khác hay leak nội dung token.

## 4. Thời gian: phân biệt instant, local date, local time, duration

JSON không có kiểu thời gian gốc; mọi giá trị thời gian chỉ là **chuỗi/số theo quy ước ứng dụng**. Một chuỗi `"2026-11-18T09:00:00"` không có `Z` hoặc offset, nên **không chỉ ra một instant toàn cầu duy nhất**.

| Kiểu dữ liệu nghiệp vụ | Ví dụ JSON | Java | Diễn giải |
| --- | --- | --- | --- |
| Thời điểm tuyệt đối (instant) | `"2026-11-18T09:15:30.123Z"` | `Instant` | Một thời điểm trên trục thời gian UTC |
| Cùng instant có offset khác | `"2026-11-18T16:15:30.123+07:00"` | `OffsetDateTime` → `Instant` | Cùng thời điểm với dòng trên |
| Ngày lịch | `"2026-11-18"` | `LocalDate` | Ngày, không phải 00:00 UTC |
| Giờ địa phương | `"09:30:00"` | `LocalTime` | Giờ trên đồng hồ, cần zone/ngày nếu chuyển thành instant |
| Múi giờ theo vùng | `"Asia/Ho_Chi_Minh"` | `ZoneId` | Dùng để tính thời gian theo lịch, quy tắc DST |
| Khoảng thời gian | `"PT15M"` | `Duration` | 15 phút theo ISO 8601 |
| Hạn chờ tính theo số | `"timeoutMillis": 2500` | `long` / `Duration.ofMillis` | Đơn vị phải ghi ngay tên/schema |

**Quy ước bài học:** trường `createdAt`/`updatedAt` là RFC 3339 date-time, response **chuẩn hóa UTC** có `Z`, với **ba chữ số phần thập phân giây** (precision millisecond). Client có thể gửi offset hợp lệ nếu endpoint cho phép thời gian đầu vào và server chuyển về instant. Nếu dự án chọn precision tới microsecond/nanosecond, phải ghi rõ và thống nhất code/DB, không để mỗi endpoint phát một kiểu.

~~~json
{
  "createdAt": "2026-11-18T09:15:30.123Z",
  "deliveryDate": "2026-11-20",
  "deliveryTime": "09:30:00",
  "deliveryZone": "Asia/Ho_Chi_Minh",
  "reservationTtl": "PT15M"
}
~~~

`deliveryDate` + `deliveryTime` + `deliveryZone` mới đủ để tính một lịch hẹn theo vùng, và vẫn phải có chính sách cho giờ địa phương **không tồn tại hoặc lặp lại** khi vùng thay đổi giờ mùa hè. Không tự mặc định `LocalDateTime` là UTC, cũng không dựa vào timezone của máy chủ đang chạy.

### 4.1. Chuẩn RFC 3339 và trường có timezone

Nên có **Z hoặc offset** trên mọi trường biểu diễn instant. Ví dụ:

~~~text
Hợp lệ theo hợp đồng (nhập instant):
2026-11-18T09:15:30.123Z
2026-11-18T16:15:30.123+07:00

Không đủ thông tin để xác định instant:
2026-11-18T09:15:30.123

Chỉ là ngày lịch:
2026-11-18
~~~

Khi hai giá trị có offset khác nhau nhưng chỉ cùng instant, so sánh/định danh chúng theo thời điểm UTC, không theo chuỗi ký tự. `2026-11-18T09:15:30.123Z` và `2026-11-18T16:15:30.123+07:00` bằng nhau về thời điểm. Hệ thống lưu “người dùng chọn 09:30 giờ địa phương ngày mai” thì cần giữ zone/calendar semantics, không chỉ lưu chuỗi UTC rồi hy vọng suy ngược được lịch.

**RFC 3339** là profile của ISO 8601; trong OpenAPI 3.1 có thể khai báo `type: string` + `format: date-time`. Cần biết nhiều JSON Schema validator chỉ coi `format` như annotation, không tự từ chối mọi chuỗi sai; phải test parser/runtime riêng. Với JavaScript, `Date` không đại diện đầy đủ cho local date hoặc ZonedDateTime; hãy parse `YYYY-MM-DD` thành ngày lịch trong UI đúng ngữ nghĩa, tránh lỗi lệch một ngày do tự convert sang UTC.

### 4.2. Chọn và kiểm thử precision

Nếu DB lưu tới microsecond nhưng API chỉ công bố millisecond, việc cắt precision có thể khiến hai event khác nhau có cùng `createdAt`. Khi phân trang, phải **thêm ID làm tie-breaker**. Nếu dùng timestamp làm version/ETag, cần có **version đơn điệu** độc lập thay vì dựa vào độ chính xác timestamp.

Trong Java:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;

Instant fromUtc = Instant.parse("2026-11-18T09:15:30.123Z");
Instant fromOffset =
    OffsetDateTime.parse("2026-11-18T16:15:30.123+07:00").toInstant();
assert fromUtc.equals(fromOffset);

LocalDate deliveryDate = LocalDate.parse("2026-11-20");
ZoneId customerZone = ZoneId.of("Asia/Ho_Chi_Minh");
Duration ttl = Duration.parse("PT15M");

// Khi hợp đồng yêu cầu CHÍNH XÁC 3 số thập phân giây:
DateTimeFormatter apiTimestamp = new DateTimeFormatterBuilder()
    .appendInstant(3)
    .toFormatter();
String serialized =
    apiTimestamp.format(fromUtc.truncatedTo(ChronoUnit.MILLIS));
// "2026-11-18T09:15:30.123Z"
~~~

Ví dụ cho thấy cách tạo định dạng **chủ động**; Jackson không nhất thiết tự áp formatter này cho mọi `Instant`. Nếu dùng Jackson serializer mặc định, kiểm tra output thật và cấu hình/tùy biến serializer khi hợp đồng đòi chính xác ba chữ số. Đừng yêu cầu client kiểm bằng regex ba chữ số nếu server có lúc trả `.1Z` hoặc `.123456Z`.

### 4.3. Cơ sở dữ liệu và thời gian HTTP

Với PostgreSQL, `TIMESTAMP WITH TIME ZONE` (`timestamptz`) phù hợp lưu instant; nó **không giữ lại tên vùng timezone ban đầu** như `Asia/Ho_Chi_Minh`. Nếu cần hiển thị lịch hẹn trong vùng đã chọn, lưu `ZoneId` hoặc thông tin lịch riêng. `TIMESTAMP WITHOUT TIME ZONE` biểu diễn thời gian không gắn zone; dùng phải có semantics rõ, tránh ánh xạ nhầm sang instant theo timezone máy chủ.

Phân biệt thời gian trong JSON với header HTTP:

- JSON `createdAt`: theo contract RFC 3339 của API.
- HTTP `Date` và `Last-Modified`: dạng HTTP-date theo chuẩn HTTP, **không dùng chuỗi JSON**.
- `Retry-After`: có thể là số giây hoặc HTTP-date; không phải `Duration` dạng `PT15M` nếu header mong đợi số giây.
- Timeout duration: biểu diễn `timeoutMillis` hoặc `PT2.5S` theo hợp đồng, tuyệt đối không dùng một số `timeout: 2500` không có đơn vị.

## 5. Số trong JSON: kiểu, precision, đơn vị và làm tròn

JSON có số (`number`) mà không có subtype `int64`/`decimal` được bảo toàn giống nhau ở mọi ngôn ngữ. Java có `long`, `BigInteger`, `double`, `BigDecimal`; JavaScript `Number` thông thường dùng IEEE-754 binary64. Điều đó tạo ra lỗi mất chính xác nếu API không định nghĩa phạm vi.

### 5.1. Giới hạn số nguyên an toàn khi dùng JavaScript

JavaScript `Number.MAX_SAFE_INTEGER` là **9.007.199.254.740.991** (`2^53-1`). Số nguyên `9.007.199.254.740.993` không được biểu diễn chính xác bởi kiểu Number thông thường.

~~~json
{
  "legacyOrderId": 9007199254740993,
  "quantity": 2
}
~~~

Nếu server Java viết `Long legacyOrderId` thành JSON number này, client JavaScript có thể đọc sai ID dù JSON vẫn hợp cú pháp. **Quy ước nên dùng:** ID là string, kể cả khi DB dùng `BIGINT`; các số đếm/lượng phải nằm trong phạm vi được công bố. Khi cần `int64` đầy đủ, hoặc dùng string decimal (`"9007199254740993"`) và parser chuyên dụng, hoặc thỏa thuận client dùng kiểu có độ chính xác tương ứng.

~~~json
{
  "id": "9007199254740993",
  "quantity": 2
}
~~~

`format: int64` của OpenAPI là gợi ý dạng số và codegen, **không tự chuyển JSON number thành chuỗi hoặc sửa precision của JavaScript**. Nếu hợp đồng chọn string cho ID, schema phải ghi `type: string`. Đừng dựa vào kiểu `long` trong Java để kết luận client nào cũng đọc đúng.

### 5.2. Tiền và decimal

Không dùng `double` cho phép cộng/trừ tiền khi yêu cầu tính chính xác thập phân:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal itemPrice = new BigDecimal("19.99");
BigDecimal tax = new BigDecimal("1.60");
BigDecimal total = itemPrice.add(tax); // 21.59, không sai số nhị phân.

// Rounding là QUY TẮC NGHIỆP VỤ, không phải chọn tùy tiện.
BigDecimal rounded = total.setScale(2, RoundingMode.HALF_EVEN);
~~~

Hai cách biểu diễn thường dùng trong REST:

| Cách | Ví dụ | Khi nào phù hợp | Điều phải công bố |
| --- | --- | --- | --- |
| **Số nguyên đơn vị nhỏ nhất** | `{"totalMinorUnits": 2159, "currency": "USD"}` | Thanh toán có minor unit xác định, giá trị nằm trong phạm vi integer an toàn cho client | Minor unit/exponent theo currency, dấu âm, ngưỡng overflow |
| **Chuỗi thập phân** | `{"amount": "21.59", "currency": "USD"}` | Cần precision cao, tương thích nhiều SDK, không mất trailing zeros | Quy tắc pattern, số chữ số tối đa, scale, rounding |

Không ngầm giả định tất cả tiền tệ có **hai** chữ số thập phân; quy ước về số đơn vị nhỏ nhất và scale phải gắn với mã tiền và chính sách sản phẩm. Ví dụ API đơn hàng dùng VND `totalMinorUnits` theo đơn vị đồng; ví dụ decimal USD dùng hai chữ số. Hai cách biểu diễn **không được trộn trong cùng trường** theo kiểu lúc number lúc string.

Không dùng `new BigDecimal(0.1)` để khởi tạo giá trị tiền chính xác từ một literal `double`; dùng `new BigDecimal("0.10")` hoặc parse chuỗi thập phân đã validate. Việc tính VAT, chiết khấu, cộng dồn hoặc phân bổ cents phải định nghĩa lúc nào làm tròn, theo chế độ nào và trả lời cho trường hợp âm/hoàn tiền.

### 5.3. Quy ước cho số khác

- **Quantity:** số nguyên, `minimum: 1`, `maximum` theo nghiệp vụ; `0` có thể nghĩa “xóa dòng” trong một API khác, nhưng phải ghi rõ.
- **Percentage/rate:** chọn `0..1` hay `0..100`; trường `discountRate: 0.15` khác `discountPercent: 15`. Dùng tên đơn vị rõ, không để client tự đoán.
- **Duration/size:** `timeoutMillis`, `sizeBytes`, `ratePerSecond`, không dùng field `time` hoặc `size` mơ hồ.
- **Số thập phân khoa học:** JSON cho phép dạng lũy thừa, nhưng nếu API tiền chỉ chấp nhận decimal string không có exponent thì phải công bố và validate điều đó.
- **NaN/Infinity:** không phải giá trị hợp lệ trong JSON chuẩn; không serialize `Double.NaN`/`Infinity` thành JSON number. Với phép tính không xác định, chọn error hoặc null theo contract.
- **Giá trị thiếu/overflow:** parse/validate rõ trước khi lưu; không để DB exception làm thành `500` cho một giới hạn đầu vào đã biết.

## 6. Giá trị thiếu, `null`, rỗng và giá trị mặc định

Trong JSON object, **không có property**, property bằng `null`, property bằng `""`, property bằng `[]` và property bằng `0` là **năm trạng thái khác nhau**. Tài liệu phải nói chúng mang nghĩa gì ở từng operation.

~~~json
{}
~~~

~~~json
{"note": null}
~~~

~~~json
{"note": ""}
~~~

~~~json
{"tags": []}
~~~

~~~json
{"quantity": 0}
~~~

### 6.1. Trong response: đừng dùng null để che quyền

Ví dụ API đơn hàng chọn `note` **luôn có mặt**, có thể null:

| Giá trị | Ý nghĩa theo hợp đồng minh họa |
| --- | --- |
| `"note": "Gọi trước khi giao"` | Có ghi chú |
| `"note": ""` | Chuỗi rỗng đã được lưu (nếu được phép); có thể chọn normalize thành null |
| `"note": null` | Không có ghi chú |
| Không có property `note` | **Không hợp lệ** cho representation này nếu schema đánh dấu required |

Nếu một field cần quyền bổ sung, có thể **không đưa field vào representation theo role** hoặc trả lỗi 403 cho thao tác riêng, nhưng không mặc định dùng `null` như tín hiệu “bạn không có quyền” nếu null vốn biểu diễn “không có dữ liệu”. Không để sự khác nhau giữa “không tồn tại” và “không được quyền biết” gây rò rỉ dữ liệu qua shape/count.

**Collection rỗng:** `"data": []` nghĩa là collection có 0 phần tử trong phạm vi truy vấn, không phải lỗi và không nên tùy tiện trả `null`. Với list endpoint, response JSON giữ cấu trúc ổn định `data: []`, metadata và link; không trả `204 No Content` lúc rỗng nhưng 200 lúc có dữ liệu nếu client mong JSON collection trong cả hai trường hợp.

### 6.2. Trong POST tạo mới

Hợp đồng ví dụ cho `POST /v1/customers`:

- `displayName` **bắt buộc** và không được null/blank; thiếu property → 422 (hoặc 400 theo quy ước API).
- `note` không bắt buộc: thiếu → không có ghi chú; `null` cũng → không có ghi chú nếu API cho phép; chuỗi → giá trị ghi chú.
- `tags` không bắt buộc: thiếu → mặc định mảng rỗng; gửi `null` → 422; gửi `[]` → mảng rỗng.

**Mặc định chỉ có ý nghĩa khi được công bố.** Không dùng Jackson biến mọi missing/null thành cùng một Java `null` rồi để service tự suy luận mơ hồ. Khi schema khai báo `default`, cần biết JSON Schema `default` thường là annotation, **không buộc validator tự chèn giá trị** vào body; server phải thực thi mặc định một cách chủ động và test.

### 6.3. Trong PUT cập nhật toàn bộ resource

PUT thường mang ý nghĩa thay thế **toàn bộ trạng thái của resource theo representation đã định nghĩa**. Khi thiết kế full replacement, phải nói trường thiếu có bị xóa, reset về default hay bị từ chối; **đừng xem PUT là PATCH** chỉ vì DTO chỉ chứa vài field. Nếu có thông tin do server quản lý (`createdAt`, owner, giá tính từ server), làm rõ field đó không được client thay thế.

Với chỉnh sửa đồng thời, `If-Match` + ETag và phản hồi `412 Precondition Failed` có thể giúp tránh lost update. Null semantics và concurrency semantics là hai vấn đề khác nhau nhưng thường xảy ra cùng lúc.

### 6.4. Trong PATCH: thiếu và null thường mang ý nghĩa trái nhau

Hãy phân biệt **JSON Merge Patch (RFC 7396)** và **JSON Patch (RFC 6902)**.

Với `Content-Type: application/merge-patch+json`:

~~~http
PATCH /v1/customers/cus-42 HTTP/1.1
Host: api.example.com
Content-Type: application/merge-patch+json
If-Match: "customer-v7"

{"note": null}
~~~

Theo JSON Merge Patch, property không có trong patch → **giữ nguyên**; property được đặt `null` → **xóa member** khỏi target object. API có thể ánh xạ hành động xóa đó thành “không còn ghi chú” trong domain. Merge Patch không thể dùng `null` để *gán một giá trị null JSON như dữ liệu* phân biệt với xóa; nếu cần phân biệt hai việc, chọn mô hình khác.

~~~json
{}
~~~

Patch rỗng trên object sẽ không thay đổi `note`. Nhưng:

~~~json
{"note": ""}
~~~

Đây là **gán chuỗi rỗng**, không phải xóa, nếu validation cho phép. Với array, JSON Merge Patch thay **toàn bộ array**, không merge từng phần tử.

Nếu muốn biểu đạt hành động riêng biệt, dùng JSON Patch:

~~~http
PATCH /v1/customers/cus-42 HTTP/1.1
Content-Type: application/json-patch+json
If-Match: "customer-v7"

[
  {"op": "replace", "path": "/note", "value": null}
]
~~~

JSON Patch `replace` có thể đặt JSON null làm giá trị; `remove` mới là thao tác xóa member:

~~~json
[{"op": "remove", "path": "/note"}]
~~~

**Lưu ý:** `replace` đòi đường dẫn tồn tại theo RFC 6902; nếu không có property `note`, server phải xử lý đúng lỗi hoặc dùng `add` phù hợp. Chỉ whitelist những path client có quyền sửa; không cho sửa `/tenantId`, `/balance` hoặc metadata nội bộ chỉ vì JSON Patch có cú pháp hợp lệ.

### 6.5. Java/Spring/Jackson: mất thông tin ở đâu?

Ví dụ DTO:

~~~java
public record CustomerPatch(String note) {}
~~~

Khi Jackson deserialize cả `{}` và `{"note":null}` vào DTO đơn giản này, ứng dụng thường thấy cùng một `note == null`. Như vậy **không phân biệt được “không sửa” và “xóa”**. Các giải pháp:

1. Xử lý patch bằng `JsonNode` hoặc thư viện triển khai RFC 7396/RFC 6902, có validate schema và field whitelist.
2. Dùng wrapper kiểu **undefined / null / value** (ví dụ một `JsonNullable<T>` được cấu hình đúng) để giữ ba trạng thái.
3. Dùng command DTO có cờ “field present” riêng nếu không áp dụng RFC patch chuẩn; ghi rõ semantics đặc thù của API.

Ví dụ phát hiện trạng thái bằng Jackson `JsonNode` (phác họa logic, chưa thay thế đầy đủ engine RFC 7396):

~~~java
import com.fasterxml.jackson.databind.JsonNode;

void applyNotePatch(JsonNode patch, Customer customer) {
    if (patch == null || !patch.isObject()) {
        throw new InvalidPatchException("Patch must be a JSON object");
    }

    // Không có property note → giữ nguyên.
    if (!patch.has("note")) {
        return;
    }

    JsonNode node = patch.get("note");
    if (node.isNull()) {
        customer.clearNote();  // Remove member theo Merge Patch.
    } else if (node.isTextual()) {
        customer.setNote(node.textValue());
    } else {
        throw new InvalidPatchException("note must be a string or null");
    }
}
~~~

Trong production, cần kiểm tra `If-Match`, quyền sửa resource/field, độ dài `note`, mọi field có trong patch và phản hồi `application/problem+json` phù hợp. Đừng nhận `Map<String,Object>` rồi copy thẳng vào entity (mass assignment). `InvalidPatchException` là exception nghiệp vụ minh họa, cần ánh xạ thành lỗi 400/422 theo hợp đồng.

**Serialization:** cấu hình `@JsonInclude(Include.NON_NULL)` hoặc global `spring.jackson.default-property-inclusion` có thể làm field null **biến mất khỏi response**. Nếu OpenAPI nói `note` required và nullable, phải bảo đảm serializer vẫn xuất `"note":null`; không bật `NON_NULL` một cách vô thức. Tương tự, `Optional<T>` trong DTO Java **không tự định nghĩa** thiếu/null cho JSON một cách rõ ràng.

## 7. OpenAPI 3.1: viết quy ước thành schema và description

Ví dụ dưới là **một tài liệu OpenAPI minh họa cho list offset**, dùng đúng quy ước từ các mục trước. Nó không chứa authentication/security scheme đầy đủ để tập trung vào dữ liệu; trong API thật cần khai báo `securitySchemes`, 401/403, 429 và các lỗi hạ tầng liên quan.

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders:
    get:
      operationId: listOrders
      summary: Liệt kê đơn hàng theo trang
      description: |
        page bắt đầu từ 0. Mặc định size=20, tối đa 100.
        Kết quả sắp theo createdAt DESC, id DESC.
        hasNext/links.next mô tả trang kế, không cam kết totalCount.
        createdAt là RFC 3339 UTC với độ chính xác millisecond.
        totalMinorUnits là số nguyên đơn vị nhỏ nhất của currency.
      parameters:
        - name: page
          in: query
          required: false
          description: Trang bắt đầu từ 0.
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          required: false
          description: Số bản ghi tối đa mỗi trang.
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [PENDING, CONFIRMED, CANCELLED]
      responses:
        '200':
          description: Trang danh sách, kể cả khi rỗng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderPage'
        '400':
          description: Query parameter không parse được
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '422':
          description: Giá trị tham số ngoài phạm vi
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
components:
  schemas:
    OrderPage:
      type: object
      required: [data, page, size, hasNext, links]
      additionalProperties: false
      properties:
        data:
          type: array
          items:
            $ref: '#/components/schemas/OrderSummary'
        page: {type: integer, minimum: 0}
        size: {type: integer, minimum: 1, maximum: 100}
        hasNext: {type: boolean}
        links:
          type: object
          required: [next]
          additionalProperties: false
          properties:
            next:
              type: [string, 'null']
              description: URL trang tiếp; null khi không có.
    OrderSummary:
      type: object
      required: [id, createdAt, status, totalMinorUnits, currency, note]
      additionalProperties: false
      properties:
        id:
          type: string
          description: Identifier luôn ở dạng string.
        createdAt:
          type: string
          format: date-time
          description: |
            RFC 3339, xuất UTC Z, chính xác 3 chữ số phần
            thập phân giây, ví dụ 2026-11-18T09:15:30.123Z.
          examples:
            - '2026-11-18T09:15:30.123Z'
        status:
          type: string
          enum: [PENDING, CONFIRMED, CANCELLED]
        totalMinorUnits:
          type: integer
          minimum: 0
          maximum: 9007199254740991
          description: Số nguyên an toàn với JS Number.
        currency:
          type: string
          enum: [VND]
          description: VND, minor unit là đồng trong API này.
        note:
          type: [string, 'null']
          maxLength: 500
          description: null nghĩa là chưa có ghi chú.
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
~~~

**Điểm cần đọc kỹ:**

- Với **OpenAPI 3.1**, cho phép null bằng `type: [string, 'null']`. Trong OpenAPI 3.0 có cách biểu diễn `nullable: true`; không copy cú pháp qua lại mà không kiểm tra tooling.
- `required` nói property phải **có mặt**, không tự đồng nghĩa “khác null”. Vì `note` required nhưng `type` gồm null, response phải có `note` và được phép là null.
- `default` trong JSON Schema chủ yếu có vai trò annotation; server phải áp default 0/20, test không được giả định validator tự điền.
- `format: date-time` không tự đảm bảo tất cả validator kiểm đủ offset, precision và UTC; cần test riêng tại HTTP/Jackson.
- `maximum: 9007199254740991` là ràng buộc ví dụ để JSON integer không vượt phạm vi JS Number an toàn; nếu muốn giá trị lớn hơn, đổi representation/SDK một cách có chủ đích.
- `additionalProperties: false` yêu cầu hợp đồng nghiêm ngặt. Nếu backend cho field mới vào response nhưng SDK cũ từ chối unknown fields, thay đổi có thể gây breaking change. Hãy chọn chính sách tương thích rõ.

Không biến OpenAPI thành nơi chỉ ghi tên field. **Description + examples + giới hạn + đơn vị + lỗi + yêu cầu security + hành vi trang cuối** là phần tạo nên developer experience.

## 8. Java/Spring: thực hiện hợp đồng phân trang

Đoạn dưới minh họa Spring MVC + Spring Data JPA với **offset pagination**, sort cố định và tenant lấy từ principal đã xác thực. Đây là các class/phần code độc lập ở mức bài học; domain/repository và security adapter được lược bớt nhưng bất biến được ghi rõ.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

record OrderSummary(
    String id,
    Instant createdAt,
    String status,
    long totalMinorUnits,
    String currency,
    String note
) {}

record PageLinks(String next) {}
record OrderPage(
    List<OrderSummary> data, int page, int size,
    boolean hasNext, PageLinks links
) {}

interface OrderSummaryReader {
    Slice<OrderSummary> findByTenantAndOptionalStatus(
        UUID trustedTenantId, String status, PageRequest pageable
    );
}

interface TrustedTenantResolver {
    UUID resolve(Authentication authentication);
}

@RestController
class OrdersQueryController {
    private final OrderSummaryReader reader;
    private final TrustedTenantResolver tenants;

    OrdersQueryController(
            OrderSummaryReader reader, TrustedTenantResolver tenants) {
        this.reader = reader;
        this.tenants = tenants;
    }

    @GetMapping("/v1/orders")
    public ResponseEntity<OrderPage> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String status,
            Authentication authentication) {

        if (page < 0 || size < 1 || size > 100) {
            throw new InvalidPageParameterException();
        }
        // Whitelist status trước khi đưa vào query; không nối SQL tùy ý.
        if (status != null
                && !List.of("PENDING","CONFIRMED","CANCELLED")
                        .contains(status)) {
            throw new InvalidPageParameterException();
        }

        UUID tenantId = tenants.resolve(authentication);
        Sort sort = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        );
        PageRequest pageable = PageRequest.of(page, size, sort);
        Slice<OrderSummary> result =
            reader.findByTenantAndOptionalStatus(tenantId, status, pageable);

        String next = null;
        if (result.hasNext()) {
            UriComponentsBuilder link =
                UriComponentsBuilder.fromPath("/v1/orders")
                    .queryParam("page", page + 1)
                    .queryParam("size", size);
            if (status != null) link.queryParam("status", status);
            next = link.build().encode().toUriString();
        }
        OrderPage body = new OrderPage(
            result.getContent(), page, size,
            result.hasNext(), new PageLinks(next)
        );
        return ResponseEntity.ok()
            .header("Cache-Control", "private, no-store")
            .body(body);
    }
}

class InvalidPageParameterException extends RuntimeException {}
~~~

**Điều phải bổ sung khi đưa vào production:**

1. `OrderSummaryReader` phải được triển khai bằng query projection có điều kiện `tenant_id` lấy từ principal. `TrustedTenantResolver` phải kiểm tra xác thực và quyền theo tenant; không nhận tenant ID trực tiếp từ header/query parameter của client.
2. `Slice` thường có thể biết `hasNext` bằng cách lấy thêm một row, nhưng không trả chính xác `totalCount`. `PageRequest.of(page,size)` tính offset theo `page × size`; **không** tự đổi size thành `size+1` trong `PageRequest` vì sẽ làm sai offset của trang sau.
3. `InvalidPageParameterException` cần `@RestControllerAdvice` ánh xạ ra HTTP **422** cùng `application/problem+json` và mã `INVALID_PAGINATION`. Query `page=abc` không parse được trước khi chạy method, Spring thường trả 400; kiểm thử nó tách biệt.
4. Khi `page` cực lớn, `page + 1` hoặc tính offset có thể overflow. Validate phạm vi page/cursor và kiểm tra khả năng DB xử lý trước khi truy vấn. Nếu DB không hỗ trợ trang sâu, trả lỗi theo hợp đồng hoặc cung cấp cursor endpoint.
5. DTO `String note` phải được serialize thành JSON null khi không có ghi chú; không bật `NON_NULL` cho representation này. `Instant createdAt` phải được serialize UTC với millisecond precision theo hợp đồng, không chỉ dựa vào output mặc định của Jackson.
6. Nếu client cần truy cập bằng URL tuyệt đối, dựng link từ **public base URL đã tin cậy**, không mù quáng dùng `Host`/`Forwarded` do client Internet tự gửi để tránh host-header injection. Relative URL như ví dụ là một lựa chọn hợp lệ nếu docs nói rõ.

### 8.1. Tách parsing error và validation error bằng Problem Details

Ví dụ khi `size=101`:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-pagination",
  "title": "Tham số phân trang không hợp lệ",
  "status": 422,
  "detail": "size phải từ 1 đến 100; page phải lớn hơn hoặc bằng 0.",
  "code": "INVALID_PAGINATION"
}
~~~

Khi `page=abc`, body có thể dùng `400` và `code: INVALID_PARAMETER_TYPE`. RFC 9457 định nghĩa các member chuẩn `type`, `title`, `status`, `detail`, `instance`; `code` là extension của API. Không trả nguyên cursor bí mật, SQL hay stack trace trong `detail`. Với endpoint bị yêu cầu đăng nhập, 401/403 phải được xử lý ở security layer; không bỏ xác thực chỉ để client nhận 422.

## 9. Kiểm thử contract: happy path chưa đủ

Một client SDK có thể pass test với page 0 và một vài số nhỏ mà vẫn sai khi gặp edge case. Hãy viết **contract tests** từ bảng quy ước thay vì chỉ kiểm tra dữ liệu mẫu.

| Nhóm | Ca thử | Bất biến cần kiểm |
| --- | --- | --- |
| Offset | Bỏ page/size; page 0, 1; size 1, 100 | Default và chỉ số chính xác |
| Validation | page âm, size 0/101, page không phải số, param lặp | HTTP 400/422 + Problem Details theo quy ước |
| Trang cuối | Không còn phần tử; page quá xa | `data: []`, `hasNext: false`, `links.next: null` |
| Sort | Nhiều order cùng timestamp; chạy lại query | Thứ tự ổn định với ID tie-breaker |
| Filter + next | `status=CONFIRMED` và size 2 | Link next giữ status, size và các filter cần thiết |
| Cursor | Cursor hết hạn, bị sửa, dùng chéo tenant/filter | Từ chối an toàn, không lộ nội dung token |
| Instant | UTC Z và offset `+07:00` biểu diễn cùng thời điểm | Parser tạo cùng `Instant` |
| Precision | Millisecond 000/123/999; nanosecond input | Output đúng số chữ số đã công bố, chính sách truncate/round rõ |
| Date-only | Ngày có thay đổi DST ở một số vùng | Không biến `YYYY-MM-DD` thành ngày khác khi đổi timezone |
| Integer | 0, 1, giới hạn tối đa, lớn hơn 2^53-1 | Giới hạn hoặc string representation đúng |
| Money | 19.99 + 1.60; rounding, currency, âm | Decimal/đơn vị nhỏ nhất chính xác |
| Null | Field thiếu, `null`, `""`, `[]`, 0 | Hành vi đúng cho POST/PUT/PATCH/response |
| JSON Merge Patch | Không có note, note=null, note="" | Giữ nguyên / xóa / ghi chuỗi rỗng |
| JSON Patch | `remove`, `replace` null, path thiếu | Đúng semantics RFC 6902 |
| Security | Filter tenant, field nhạy cảm, cursor giả | Không vượt quyền, không rò metadata |
| Compatibility | Thêm optional field; đổi enum/default/null | Bắt breaking change với SDK/client cũ |

### 9.1. JUnit: kiểm chứng thời gian và số

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;

class ApiConventionsTest {
    @Test
    void differentOffsetsRepresentSameInstant() {
        Instant utc = Instant.parse("2026-11-18T09:15:30.123Z");
        Instant plusSeven =
            OffsetDateTime.parse("2026-11-18T16:15:30.123+07:00")
                .toInstant();
        assertEquals(utc, plusSeven);
    }

    @Test
    void decimalMoneyIsExact() {
        BigDecimal total = new BigDecimal("19.99")
            .add(new BigDecimal("1.60"));
        assertEquals(new BigDecimal("21.59"), total);
    }

    @Test
    void javascriptSafeIntegerBoundaryIsExplicit() {
        long maxSafe = 9_007_199_254_740_991L;
        long unsafe = maxSafe + 2L;
        assertTrue(unsafe > maxSafe);
        // Không gửi unsafe dưới dạng JSON number cho JS Number client.
        assertEquals("9007199254740993", Long.toString(unsafe));
    }
}
~~~

Test trên kiểm mô hình dữ liệu Java; để bảo đảm **JSON thực sự đúng**, cần thêm Jackson serialization test/HTTP response test. Ví dụ output của `Instant` có thể không luôn có đúng ba chữ số nếu serializer khác được sử dụng.

### 9.2. MockMvc: response và lỗi phân trang

Đoạn trích dẫn dưới giả định `MockMvc` đã được cấu hình, controller/service được mock để trả dữ liệu phù hợp, và Spring Security Test cấp principal có quyền. Kiểm tra HTTP:

~~~java
@Test
void invalidPageSizeReturnsProblemDetail() throws Exception {
    mockMvc.perform(get("/v1/orders")
            .with(jwt()) // Cần claim tenant hợp lệ với security adapter.
            .param("page", "0")
            .param("size", "101"))
        .andExpect(status().is(422))
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.valueOf("application/problem+json")))
        .andExpect(jsonPath("$.status").value(422))
        .andExpect(jsonPath("$.code").value("INVALID_PAGINATION"));
}

@Test
void pageIsZeroBasedAndEmptyResultHasStableShape() throws Exception {
    // Mock OrderSummaryReader trả Slice.empty() theo query hợp lệ.
    mockMvc.perform(get("/v1/orders")
            .with(jwt())
            .param("page", "9")
            .param("size", "20"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.page").value(9))
        .andExpect(jsonPath("$.size").value(20))
        .andExpect(jsonPath("$.data").isArray())
        .andExpect(jsonPath("$.data").isEmpty())
        .andExpect(jsonPath("$.hasNext").value(false))
        .andExpect(jsonPath("$.links.next").value(
            org.hamcrest.Matchers.nullValue()));
}
~~~

Import cần có tùy test context: `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.*`, `SecurityMockMvcRequestPostProcessors.jwt`, `MediaType` và JUnit `@Test`. Test đầu chỉ pass khi thực sự triển khai `@RestControllerAdvice` cho `InvalidPageParameterException`; snippet service/controller phía trên **không tự ánh xạ exception sang 422**. Nếu Spring Security được bật, thiếu token/claim có thể khiến test nhận 401/403 trước validation; xử lý đúng security test fixture, không tắt bảo mật production.

### 9.3. Test sự khác biệt giữa missing và null qua HTTP

Với PATCH dùng JSON Merge Patch, test nên có cùng resource ban đầu:

~~~text
Ban đầu:                 note = "Gọi trước khi giao"
PATCH {}                 → note vẫn "Gọi trước khi giao"
PATCH {"note":null}      → note bị xóa/không còn ghi chú
PATCH {"note":""}        → note thành "" nếu hợp đồng cho phép
PATCH {"note":123}       → 422, không thay đổi resource
PATCH {"ownerId":"..."}  → từ chối sửa field không được phép
PATCH If-Match sai       → 412, không ghi đè thay đổi khác
~~~

Kiểm cả **persistence state** lẫn response; test controller response 200 chưa chứng minh dữ liệu có được ghi đúng. Với HTTP 412, kiểm xem server thực sự áp precondition trước khi sửa resource. Với response nullable, test Jackson có thực sự tạo `"note":null` chứ không bỏ trường:

~~~json
{"id":"order-102","note":null}
~~~

Nếu response body thiếu `note` trong khi schema ghi `required`, contract test phải báo lỗi, dù cả hai hình thức trông giống nhau ở một số client.

## 10. Khả năng tương thích và developer experience

Những thay đổi tưởng nhỏ về quy ước là **breaking changes** nếu client đã dựa vào hành vi cũ:

| Thay đổi | Ảnh hưởng |
| --- | --- |
| Page từ 0-based thành 1-based | Client đi sai trang, trùng/thiếu item |
| Mặc định size 20 → 100 | Tăng tải, thay UX, thời gian request |
| Sort thay đổi mà không thông báo | Cursor/bookmark và danh sách có thứ tự khác |
| `totalCount` biến mất | UI page count/SDK cũ có thể lỗi |
| Offset chuyển thành cursor | Tham số, metadata, cách điều hướng khác |
| Timestamp không offset chuyển sang UTC | Client parse chuỗi khác, dữ liệu lịch có thể lệch |
| Precision milliseconds → nanoseconds | Regex/client SDK/parser có thể bị vỡ |
| ID number → string | Cần migration kiểu dữ liệu client và codegen |
| Amount integer → decimal string | Client phải đổi parser, đơn vị và format |
| `note` từ nullable required → omitted optional | SDK deserialize và ý nghĩa “không có dữ liệu” đổi |
| JSON Merge Patch `null` xóa field → gán JSON null | Thay đổi thao tác cập nhật dữ liệu |

Để API dễ dùng, mỗi endpoint nên có: **ví dụ request copy được**, example success và error; bảng parameters với default/min/max; schema bắt buộc/nullability; policy timezone/precision; unit/rounding; mô tả sort/page/cursor; cách retry và idempotency khi cần; authorization; danh sách status code; link đến changelog và chính sách versioning.

**Cách tổ chức tài liệu hiệu quả:** Một trang “API conventions” làm nguồn tham chiếu, nhưng mỗi endpoint vẫn phải link hoặc tóm tắt quy ước quan trọng ngay tại chỗ. Đừng bắt người tích hợp đọc 15 trang khác để biết `size` tối đa 100. Hãy sinh SDK và docs từ cùng hợp đồng OpenAPI đã review, nhưng kiểm tra output thực tế của server; một spec đẹp không bảo đảm implementation đang làm đúng.

### Checklist review hợp đồng trước khi phát hành

1. Page bắt đầu từ đâu, size/default/max bao nhiêu, sort có tie-breaker hay không?
2. Trang cuối trả gì, link next giữ mọi filter chứ, count là chính xác hay ước lượng?
3. Cursor có opaque, ràng buộc tenant/filter/expiry và an toàn khi bị giả mạo không?
4. Mỗi trường thời gian là **instant, local date, local time hay duration**? Có offset, zone, precision và ví dụ không?
5. Số có unit, range và representation ổn định cho JavaScript/Java không? Tiền có currency, scale và rounding?
6. Schema phân biệt **required / nullable / optional**, và serializer có tạo JSON đúng không?
7. POST/PUT/PATCH có cùng semantics cho missing/null/empty không, hay đã mô tả khác nhau theo operation?
8. OpenAPI và Problem Details khớp status, content type, mã lỗi, field path, quyền?
9. Contract tests có edge cases, regression và test chéo client/platform không?
10. Bất kỳ thay đổi quy ước nào đã được đánh giá **backward compatibility** và thông báo phù hợp chưa?

## 11. Bài tập thực hành

**Bài 1 — Sửa hợp đồng phân trang.** Một API trả `GET /v1/orders?page=1&size=20` nhưng không nói page bắt đầu từ 0 hay 1; response chỉ có `items` và `total=120`. Hãy viết lại tài liệu: page base, default/max, sort và tie-breaker, total chính xác hay ước lượng, trang rỗng, link `next`, status lỗi và cách giữ bộ lọc. Thêm 5 test contract.

**Bài 2 — Chọn offset hay cursor.** Sản phẩm có 10 triệu event theo `createdAt DESC`, ghi mới liên tục. So sánh `OFFSET 500000` và keyset/cursor, đề xuất URI, opaque token và security. Giải thích vì sao cursor vẫn không tự bảo đảm snapshot nhất quán nếu sort key thay đổi.

**Bài 3 — Quy ước thời gian.** Client gửi `2026-11-18T16:15:30.123+07:00`, server lưu instant UTC, API trả `2026-11-18T09:15:30.123Z`. Hãy chứng minh đây là cùng thời điểm, rồi giải thích tại sao `deliveryDate: "2026-11-18"` không nên tự chuyển thành UTC timestamp nếu nghiệp vụ chỉ quan tâm đến ngày lịch. Viết JUnit test cho parsing/serialization precision.

**Bài 4 — JSON number và tiền.** API Java trả `{"invoiceId":9007199254740993,"total":19.99}`. Nêu hai rủi ro khi client JavaScript đọc dữ liệu. Đề xuất biểu diễn mới dùng ID string và một trong hai cách money: minor-unit integer hoặc decimal string có currency; ghi giới hạn/rounding và test bằng `BigDecimal`.

**Bài 5 — Null và patch semantics.** Resource khách hàng có `note="A"`. Lập ma trận kết quả cho `PATCH {}`, `PATCH {"note":null}`, `PATCH {"note":""}`, `JSON Patch remove`, `JSON Patch replace null`, `PUT` thiếu note. Nêu điểm nào phụ thuộc hợp đồng ứng dụng, điểm nào được RFC 7396/6902 quy định. Viết test chứng minh DTO `String note` đơn giản không giữ được phân biệt missing và null.

**Gợi ý tự kiểm tra:** Bài 1 phải định nghĩa rõ contract, không lấy ví dụ JSON làm quy chuẩn duy nhất. Bài 2: cursor dựa trên sort key ổn định, token bảo vệ và phạm vi tenant/filter; không tự tạo snapshot. Bài 3: hai thời gian có offset khác nhau nhưng là cùng instant; date-only giữ ngữ nghĩa lịch. Bài 4: số nguyên vượt `2^53-1` không an toàn với JS Number, `double` không nên làm arithmetic tiền. Bài 5: Merge Patch thiếu → không đổi, null → xóa member; JSON Patch remove khác replace null; PUT thiếu field cần chính sách full replacement rõ ràng.
