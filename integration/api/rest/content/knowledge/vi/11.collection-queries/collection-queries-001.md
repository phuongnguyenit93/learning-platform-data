# Lọc chính xác, lọc khoảng và kết hợp điều kiện

## 1. Từ truy vấn tập hợp đến hợp đồng lọc dữ liệu

Trong REST API, **collection resource** biểu diễn một tập tài nguyên cùng loại, chẳng hạn **/api/v1/orders** hoặc **/api/v1/products**. Client thường không cần tải toàn bộ collection, mà muốn nhận phần tử đáp ứng các điều kiện nghiệp vụ:

- Đơn hàng có trạng thái **PAID**.
- Đơn được tạo **từ đầu tháng đến trước đầu tháng tiếp theo**.
- Đơn có tổng tiền **từ 100.000 đến 500.000 VND**.
- Các điều kiện trên phải **đồng thời đúng** và kết quả trả về được phân trang.

Bài học **“Lọc chính xác, lọc khoảng và kết hợp điều kiện”** thuộc chương **Truy vấn tập hợp** của module **INTEGRATION_API_REST**. Mục tiêu là xây dựng hợp đồng REST API dựa trên resource, URI, phương thức và mã HTTP; sau đó hiện thực bằng Java/Spring, mô tả bằng OpenAPI và kiểm thử được tính đúng đắn, quyền truy cập, hiệu năng.

Một yêu cầu minh họa:

~~~http
GET /api/v1/orders?status=PAID&createdFrom=2026-11-01T00%3A00%3A00Z&createdBefore=2026-12-01T00%3A00%3A00Z&minTotal=100000&maxTotal=500000&page=0&size=20 HTTP/1.1
Host: api.example.com
Accept: application/json
Authorization: Bearer <access-token>
~~~

Ý nghĩa hợp đồng: trả về **tối đa 20 đơn được phép đọc** của người gọi, có trạng thái PAID, thời điểm tạo **lớn hơn hoặc bằng** 01/11/2026 00:00 UTC và **nhỏ hơn** 01/12/2026 00:00 UTC, tổng tiền nằm trong khoảng đóng từ 100.000 đến 500.000 VND. Các số tiền và trạng thái dùng trong bài là **giả định minh họa**.

Sau bài học, bạn cần có thể:

1. Thiết kế tham số cho **lọc chính xác** và giải thích so khớp kiểu dữ liệu.
2. Chọn quy ước **cận bao gồm/không bao gồm** cho khoảng ngày giờ, số tiền và số lượng.
3. Định nghĩa minh bạch cách kết hợp **AND**, **OR**, giá trị lặp, tham số vắng mặt và tham số sai.
4. Tổ chức phân trang/sắp xếp ổn định khi dữ liệu thay đổi.
5. Áp dụng bộ lọc phân quyền trong truy vấn, ngăn truy cập chéo tenant và SQL injection.
6. Hiện thực truy vấn động có kiểm soát với **Spring MVC + Spring Data JPA Specifications**.
7. Mô tả contract bằng **OpenAPI** và viết test kiểm tra cả đúng dữ liệu lẫn hiệu năng.

## 2. Bắt đầu từ collection URI và query parameter

Cách thiết kế phổ biến là dùng **GET** tới cùng collection, với query parameter biểu diễn điều kiện:

| URI | Ý nghĩa |
| --- | --- |
| **GET /api/v1/orders** | Liệt kê các đơn hàng người gọi có quyền xem, theo phân trang mặc định |
| **GET /api/v1/orders?status=PAID** | Lọc đơn có trạng thái chính xác là PAID |
| **GET /api/v1/orders?customerId=c-42** | Lọc theo khách hàng c-42 trong phạm vi người gọi được phép truy cập |
| **GET /api/v1/orders?minTotal=100000** | Tổng tiền từ 100.000 VND trở lên |
| **GET /api/v1/orders?createdFrom=...&createdBefore=...** | Lọc theo khoảng thời điểm tạo |
| **GET /api/v1/orders?status=PAID&minTotal=100000** | Chỉ trả đơn thỏa **cả hai** điều kiện |
| **GET /api/v1/orders?page=0&size=20** | Trang đầu tiên, nhiều nhất 20 phần tử |

Đây đều là thao tác **đọc** collection, phù hợp HTTP **GET**, không cần tạo endpoint riêng như **/orders/findPaidOrders** hoặc dùng POST chỉ vì có nhiều tham số.

### Vì sao dùng query parameter?

- Điều kiện lọc có thể là **tùy chọn**, kết hợp được và dễ bookmark/chia sẻ khi dữ liệu không nhạy cảm.
- Cùng một collection có hợp đồng đọc nhất quán, có thể tận dụng cache, conditional GET và giám sát.
- Client không cần biết cấu trúc bảng SQL hoặc cách tìm kiếm nội bộ.

**Query parameter không tự có ngữ nghĩa chuẩn cho lọc.** Ý nghĩa của **status**, **createdFrom**, **minTotal**, dấu phân cách, cận và cách kết hợp là **hợp đồng do API công bố**. Không nên giả định mọi framework hoặc server diễn giải giống nhau.

Giá trị query cần được **percent-encode** đúng cách. Với múi giờ có dấu cộng như **+07:00**, dấu **+** nên được mã hóa thành **%2B** nếu xuất hiện trong query; nhiều parser query dùng quy ước form encoding và sẽ coi dấu cộng chưa mã hóa là dấu cách.

## 3. Lọc chính xác: so khớp bằng nhau là gì?

**Exact-match filtering** kiểm tra một thuộc tính bằng giá trị đã cho sau khi parse và chuẩn hóa theo quy tắc của API.

Ví dụ:

~~~http
GET /api/v1/orders?status=PAID&customerId=c-42 HTTP/1.1
~~~

Với hợp đồng đang dùng, hai điều kiện này có nghĩa:

~~~sql
WHERE status = 'PAID'
  AND customer_id = 'c-42'
~~~

Trong truy vấn thực tế, **status** và **customerId** phải được truyền dưới dạng **tham số bind**, không nối chuỗi từ request vào SQL.

### Quy tắc từng kiểu dữ liệu

| Loại thuộc tính | Ví dụ | Cần quyết định |
| --- | --- | --- |
| Enum | **status=PAID** | Danh sách trạng thái hợp lệ, chữ hoa/thường, hành vi khi giá trị không tồn tại |
| ID | **customerId=c-42** | Kiểu UUID/chuỗi, có phân quyền đọc khách hàng này không |
| Boolean | **isArchived=false** | Chỉ chấp nhận true/false hay có dạng 1/0? Không nhập nhằng khi tham số vắng mặt |
| Chuỗi nghiệp vụ | **country=VN** | Có phân biệt hoa thường? Dùng mã chuẩn hay tên hiển thị? |
| Mã định danh ngoài | **externalRef=INV-2026-001** | Phân biệt hoa thường, dấu cách đầu/cuối và Unicode như thế nào? |
| Null hoặc chưa gán | **assigneeState=UNASSIGNED** | Thiết kế trạng thái lọc riêng thay vì nhầm giá trị thiếu với chuỗi rỗng |

**Lọc chính xác** không phải tìm chuỗi con. **name=an** không mặc nhiên khớp **An Bình**, **Lan** hay các giá trị có ký tự tương tự. Nếu API hỗ trợ tìm kiếm tự do, nên thiết kế tham số riêng như **q=...**, nói rõ tokenization, không dấu/có dấu và ranking.

Đối với enum, có thể chuẩn hóa đầu vào thành chữ hoa trước khi so; nhưng nên chọn **một quy ước rõ ràng**. Nếu hệ thống chỉ chấp nhận **PAID**, yêu cầu **status=paid** có thể trả **400 Bad Request**. Nếu chấp nhận cả hai, tài liệu cần nói rõ cách chuẩn hóa.

### Vắng mặt, rỗng, null và giá trị không hợp lệ

Những request sau **không nhất thiết cùng nghĩa**:

~~~text
GET /api/v1/orders
GET /api/v1/orders?status=
GET /api/v1/orders?status=null
GET /api/v1/orders?status=UNKNOWN
~~~

Hợp đồng khuyến nghị:

- **Không có status**: **không áp điều kiện status**.
- **status=**: trả **400** nếu status không cho phép rỗng.
- **status=null**: trả **400** nếu **null** không phải enum hợp lệ; đừng tự hiểu là SQL NULL.
- **status=UNKNOWN**: trả **400** kèm thông tin giá trị enum được chấp nhận, nếu không được định nghĩa.
- Với field thực sự có thể NULL, cung cấp tham số/enum rõ ràng như **assigneeState=UNASSIGNED**, tránh nhiều cách diễn giải.

Việc tự động bỏ qua giá trị lọc sai có thể trả **nhiều dữ liệu hơn client dự định**, gây lỗi nghiệp vụ và có thể ảnh hưởng bảo mật. Đầu vào sai nên bị từ chối theo hợp đồng.

## 4. Lọc khoảng: cận dưới, cận trên và dấu bằng

**Range filtering** chọn phần tử có một thuộc tính nằm trong khoảng số hoặc khoảng thời gian.

Đối với tổng tiền:

~~~http
GET /api/v1/orders?minTotal=100000&maxTotal=500000 HTTP/1.1
~~~

Ta chọn một hợp đồng cụ thể:

- **minTotal** là cận dưới **bao gồm**, tương đương **total >= minTotal**.
- **maxTotal** là cận trên **bao gồm**, tương đương **total <= maxTotal**.
- Nếu chỉ gửi một cận, chỉ áp dụng cận đó.
- Nếu **minTotal > maxTotal**, trả **400 Bad Request**.
- Vì ví dụ dùng đơn vị **VND**, hai cận phải được so trên **cùng đơn vị tiền tệ**.

| Giá trị total | minTotal=100000, maxTotal=500000 | Kết quả |
| ---: | --- | --- |
| 99.999 | Dưới cận dưới | Loại |
| 100.000 | Bằng cận dưới | Nhận |
| 350.000 | Nằm trong khoảng | Nhận |
| 500.000 | Bằng cận trên | Nhận |
| 500.001 | Trên cận trên | Loại |

Không có quy tắc bắt buộc rằng **min/max** phải bao gồm. Nếu API chọn **lt/lte/gt/gte**, cần tài liệu hóa chính xác, ví dụ **price[gte]=100000&price[lt]=500000**; không đổi ngữ nghĩa cận giữa các endpoint.

### Số tiền và độ chính xác

Nếu tiền có phần lẻ, dùng kiểu **BigDecimal** hoặc số nguyên theo đơn vị nhỏ nhất; tránh so sánh tiền bằng **float/double** do sai số nhị phân. Với tập dữ liệu chứa nhiều tiền tệ, không được so một cận số với mọi currency rồi coi kết quả có cùng ý nghĩa: yêu cầu **currency=VND**, nhóm theo currency hoặc chuyển đổi theo chính sách tỷ giá đã phê duyệt.

## 5. Lọc thời gian: khoảng nửa mở [from, before)

Dùng **khoảng nửa mở** là một quy ước hữu ích cho timestamp:

~~~text
createdAt >= createdFrom
AND createdAt < createdBefore
~~~

Ví dụ lấy đơn trong tháng 11/2026 theo UTC:

~~~http
GET /api/v1/orders?createdFrom=2026-11-01T00%3A00%3A00Z&createdBefore=2026-12-01T00%3A00%3A00Z HTTP/1.1
~~~

Đây là khoảng **[2026-11-01T00:00:00Z, 2026-12-01T00:00:00Z)**.

| createdAt | Có được trả? | Lý do |
| --- | --- | --- |
| 2026-10-31T23:59:59Z | Không | Trước cận dưới |
| 2026-11-01T00:00:00Z | Có | Bằng cận dưới |
| 2026-11-30T23:59:59.999Z | Có | Trước cận trên |
| 2026-12-01T00:00:00Z | Không | Bằng cận trên loại trừ |

Khoảng nửa mở giúp ghép liên tiếp hai kỳ mà **không trùng bản ghi tại ranh giới**, đồng thời tránh cần đoán precision của database (milli/micro/nano giây). Ví dụ khoảng tháng 11 kết thúc đúng lúc tháng 12 bắt đầu.

### Chú ý vùng giờ và kiểu ngày

- Một **Instant** biểu diễn thời điểm tuyệt đối; ISO 8601/RFC 3339 với **Z** hoặc offset cho biết rõ thời điểm.
- Một **LocalDate** như **2026-11-18** chỉ là ngày lịch, **không tự chỉ định** thời điểm 00:00 UTC. Nếu API nhận **fromDate/toDate**, phải công bố vùng giờ nghiệp vụ và quy tắc đổi sang instant.
- “Hôm nay” theo người dùng tại Việt Nam không giống ngày UTC ở tất cả thời điểm.
- Khi nghiệp vụ tính ngày theo múi giờ có daylight saving time (DST), một ngày không phải lúc nào cũng dài đúng 24 giờ. Chuyển **đầu ngày địa phương** và **đầu ngày kế tiếp** sang instant sẽ đáng tin cậy hơn lấy thời điểm đầu + 24 giờ.
- Với ISO timestamp có offset khác UTC, parser nên quy về cùng instant để so sánh; không so theo chuỗi ký tự.

### Cách đặt tên tham số

Không nhất thiết phải dùng **createdFrom/createdBefore**, nhưng tên phải cho người gọi biết liệu cận trên có bao gồm hay không.

| Cách đặt tên | Ý nghĩa đề xuất |
| --- | --- |
| **createdFrom** | Bao gồm: createdAt >= thời điểm |
| **createdBefore** | Không bao gồm: createdAt < thời điểm |
| **createdUntil** | Dễ mơ hồ; cần nói rõ bao gồm hay không |
| **createdAt[gte]** | Cận dưới bao gồm |
| **createdAt[lt]** | Cận trên loại trừ |

Trường hợp **createdFrom = createdBefore** nên trả một tập rỗng hoặc **400** theo hợp đồng. Trong bài này chọn **400** vì đây là khoảng rỗng không có ý nghĩa cho use case liệt kê tháng; ghi rõ trong OpenAPI để client không bất ngờ.

## 6. Kết hợp điều kiện AND: quy tắc mặc định của bài học

Khi client gửi nhiều tham số **khác trường**, quy ước của API này là **AND**: mỗi phần tử phải thỏa **mọi** điều kiện được cung cấp.

~~~http
GET /api/v1/orders?status=PAID&customerId=c-42&minTotal=100000&createdFrom=2026-11-01T00%3A00%3A00Z HTTP/1.1
~~~

Sơ đồ xử lý:

~~~mermaid
flowchart TD
    A[Collection orders của tenant hiện tại] --> B[Lọc status = PAID]
    B --> C[Lọc customerId = c-42]
    C --> D[Lọc total >= 100000]
    D --> E[Lọc createdAt >= createdFrom]
    E --> F[Sắp xếp ổn định]
    F --> G[Phân trang và trả response]
~~~

Biểu thức logic tương ứng:

~~~text
tenantId = authorizedTenant
AND status = PAID
AND customerId = c-42
AND total >= 100000
AND createdAt >= 2026-11-01T00:00:00Z
~~~

**Điều kiện tenant/ownership là ràng buộc bảo mật bắt buộc của server**, kể cả client không gửi filter tenant. Nó không thể bị ghi đè bởi tham số query tùy ý.

### Cùng một kết quả khi đổi thứ tự tham số?

Nếu contract coi các điều kiện **AND độc lập**, hai URI sau có cùng điều kiện logic:

~~~text
/orders?status=PAID&minTotal=100000
/orders?minTotal=100000&status=PAID
~~~

Thứ tự query parameter không nên quyết định thứ tự đánh giá về mặt kết quả. Tuy nhiên URI là chuỗi khác nhau nên cache, chữ ký URL và log có thể nhìn nhận khác nếu không chuẩn hóa; client nên dùng URI builder và không tự nối chuỗi.

## 7. OR, nhiều giá trị của một thuộc tính và nhóm điều kiện

AND dễ hiểu khi lọc nhiều trường, nhưng đôi khi người dùng cần **status là PAID hoặc SHIPPED**.

Một cách thiết kế là lặp lại **cùng tham số**:

~~~http
GET /api/v1/orders?status=PAID&status=SHIPPED HTTP/1.1
~~~

API **phải tự định nghĩa** rằng:

- **status** lặp lại nhiều lần được diễn giải thành **IN (PAID, SHIPPED)**, tức **OR trong cùng field**.
- Những nhóm field khác vẫn kết hợp **AND**.
- Giá trị trùng như **status=PAID&status=PAID** được khử trùng nếu hợp đồng cho phép.
- Không trộn lẫn mơ hồ giữa **status=PAID,SHIPPED** và tham số lặp nếu chưa công bố hỗ trợ cả hai.
- Giới hạn số phần tử, ví dụ tối đa 10 trạng thái nếu nghiệp vụ cho phép.

Biểu thức:

~~~text
(status = PAID OR status = SHIPPED)
AND customerId = c-42
AND createdAt >= createdFrom
AND createdAt < createdBefore
~~~

**Đừng suy diễn** rằng hai giá trị ở hai field khác nhau cũng là OR. Ví dụ **status=PAID&customerId=c-42** thường là AND theo hợp đồng này.

### OR phức tạp hơn

Nếu cần:

~~~text
(status = PAID AND total >= 100000)
OR (status = PENDING AND customerId = c-42)
~~~

Query parameter phẳng khó biểu diễn nhóm dấu ngoặc và ưu tiên toán tử rõ ràng. Có thể:

1. Tạo một số bộ lọc nghiệp vụ định sẵn như **view=MY_ACTIONABLE_ORDERS**.
2. Định nghĩa một cú pháp filter có grammar, allowlist và tài liệu hóa chặt chẽ.
3. Với truy vấn rất phức tạp, tạo resource tìm kiếm/tác vụ truy vấn bằng **POST /order-searches** hoặc endpoint tương tự, rồi trả kết quả qua URI thích hợp.

POST cho truy vấn không phải lựa chọn mặc định của GET collection; chỉ nên dùng khi bài toán cần request body phong phú, giới hạn URI, bảo mật tham số hoặc cần lưu tác vụ tìm kiếm. Nếu dùng POST, cần mô tả rõ cache, idempotency và phân trang.

## 8. Xử lý trường hợp rỗng, lặp và tham số không biết

Một hợp đồng lọc tốt quy định rõ hành vi trước dữ liệu không bình thường:

| Request | Hành vi đề xuất trong bài |
| --- | --- |
| **GET /orders** | Không lọc theo tham số tùy chọn; vẫn giới hạn quyền và phân trang |
| **?status=PAID** | Lọc chính xác theo PAID |
| **?status=** | **400 Bad Request** vì giá trị enum rỗng |
| **?status=PAID&status=SHIPPED** | OR theo status, nếu endpoint hỗ trợ multi-value |
| **?status=PAID&status=UNKNOWN** | **400**, không bỏ qua UNKNOWN rồi trả PAID |
| **?minTotal=500000&maxTotal=100000** | **400** vì khoảng số không hợp lệ |
| **?createdFrom=2026-12-01T00:00:00Z&createdBefore=2026-11-01T00:00:00Z** | **400** vì cận đảo |
| **?minTotal=abc** | **400** do sai kiểu số |
| **?createdFrom=not-a-date** | **400** do sai định dạng thời gian |
| **?page=-1** hoặc **?size=100000** | **400** theo giới hạn paging |
| **?secretField=anything** | **400** cho tham số không được hỗ trợ, nếu chọn chế độ strict |

Trong bài này chọn **strict validation** cho tham số không biết để phát hiện lỗi gõ nhầm của client. Một số framework mặc định bỏ qua query parameter lạ; muốn strict cần triển khai kiểm tra hoặc API gateway/validation phù hợp. Dù chọn strict hay ignore, hãy ghi rõ và kiểm thử; **không tuyên bố strict nếu implementation chưa làm**.

Một quy ước khác cần quyết định là tham số singleton bị lặp: ví dụ **minTotal=100000&minTotal=200000**. Nên trả **400** để tránh parser “lấy giá trị đầu/cuối” khác nhau giữa các tầng. Trường hợp này khác **status** được công bố là multi-value.

## 9. Phân trang và sắp xếp sau khi lọc

Collection có thể có hàng triệu bản ghi. Lọc không thay thế phân trang; server cần giới hạn kích thước trả về và cung cấp thứ tự ổn định.

Ví dụ:

~~~http
GET /api/v1/orders?status=PAID&createdFrom=2026-11-01T00%3A00%3A00Z&page=0&size=20 HTTP/1.1
~~~

Một response contract minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
~~~

~~~json
{
  "items": [
    {
      "id": "ord-105",
      "status": "PAID",
      "total": 145000,
      "currency": "VND",
      "createdAt": "2026-11-15T08:12:30Z"
    }
  ],
  "page": 0,
  "size": 20,
  "totalItems": 93,
  "sort": ["createdAt,desc", "id,desc"]
}
~~~

Đây là **ví dụ định dạng response của API**, không phải mặc định JSON của mọi phiên bản Spring Data. Nếu trả **totalItems**, backend có thể phải thực hiện truy vấn đếm tốn kém. Với tập dữ liệu rất lớn, có thể chọn response chỉ có **hasNext/nextCursor** và không cam kết total count.

### Thứ tự phải có khóa phá hòa

**ORDER BY created_at DESC** có thể không ổn định khi nhiều đơn có cùng timestamp. Dùng một khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Bộ lọc, sort và page phải được áp trên **cùng tập dữ liệu được phép xem**. Không nên lấy trang trước rồi mới lọc/loại record không có quyền: người dùng có thể nhận trang thiếu phần tử và totalItems sai, thậm chí lộ số lượng dữ liệu tenant khác.

### Offset và keyset pagination

- **Offset pagination:** **page=0&size=20**, đơn giản nhưng các trang sâu có thể chậm; khi có bản ghi mới được thêm/xóa giữa hai lần đọc, có thể thấy lặp hoặc bỏ sót phần tử.
- **Cursor/keyset pagination:** client gửi cursor chứa mốc **createdAt** và **id** của item cuối trang trước; phù hợp dữ liệu lớn và duyệt tiếp có thứ tự. Ví dụ khi sort giảm dần, điều kiện trang kế là **createdAt < lastCreatedAt OR (createdAt = lastCreatedAt AND id < lastId)**.
- Cursor cần được validate, giới hạn thời gian sống theo hợp đồng và **ràng buộc với bộ filter + sort + quyền**; không chấp nhận cursor được sửa tùy ý để bỏ qua tenant scope.

Khi dữ liệu đang thay đổi liên tục, cả keyset lẫn offset không mặc nhiên cung cấp **snapshot nhất quán xuyên nhiều trang**. Nếu cần báo cáo chính xác ở một mốc, phải thiết kế snapshot token, as-of query hoặc cơ chế xuất báo cáo riêng.

## 10. Bảo mật bộ lọc: phân quyền nằm trong truy vấn

Một vấn đề nghiêm trọng là để client chọn **tenantId** rồi tin giá trị đó:

~~~text
GET /api/v1/orders?tenantId=other-company
~~~

Nếu API cho phép caller chỉ định tenant, phải **kiểm tra quyền** đối với tenant đó; thông thường tenant ID được lấy từ session/token đã xác thực hoặc ngữ cảnh cấp quyền, không tin query do client gửi.

### Áp điều kiện bảo mật trước phân trang

Ví dụ hệ thống multi-tenant:

~~~sql
SELECT id, status, total, created_at
FROM orders
WHERE tenant_id = :authorized_tenant
  AND status = :status
  AND created_at >= :created_from
  AND created_at < :created_before
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

**authorized_tenant** phải xuất phát từ principal hoặc quyền đã được server xác minh. Các tham số query khác là dữ liệu của client đã parse và validate, được bind an toàn vào SQL.

Các giới hạn truy cập còn có thể gồm **owner_id**, **project membership**, phân quyền theo tài nguyên hoặc chính sách row-level security. Không lọc quyền bằng cách tải tất cả record rồi **filter trong Java**: ngoài chi phí lớn còn dễ để lộ tổng số bản ghi, thứ tự hoặc dữ liệu nhạy cảm.

### SQL injection và filter injection

Sai lầm:

~~~java
String sql = "SELECT * FROM orders WHERE status = '" + userStatus + "'";
~~~

Request như một chuỗi chứa dấu nháy và toán tử có thể làm thay đổi SQL. Dùng **bind parameter, JPA Criteria API/Specification hoặc prepared statement**.

Ngay cả khi giá trị đã được bind, không cho client truyền tên cột **sort** hoặc expression tùy ý vào query builder. Hãy dùng **allowlist** cho field lọc và sort. Một tham số như **sort=internalProfit** không được phép chỉ vì field đó có trong entity.

### Không đưa dữ liệu bí mật vào query

Query string thường có mặt trong access log, lịch sử trình duyệt, analytics và proxy telemetry. Không đặt password, access token, thông tin nhạy cảm hoặc mã cá nhân trong filter nếu không cần thiết. Với bộ lọc nhạy cảm, áp chính sách che log và cân nhắc hợp đồng truy vấn chuyên biệt.

## 11. Thiết kế SQL: biểu diễn điều kiện theo đúng kiểu dữ liệu

Khi mọi tham số đều có mặt, câu SQL minh họa có thể viết:

~~~sql
SELECT id, customer_id, status, total, currency, created_at
FROM orders
WHERE tenant_id = :authorized_tenant
  AND status = :status
  AND customer_id = :customer_id
  AND total >= :min_total
  AND total <= :max_total
  AND created_at >= :created_from
  AND created_at < :created_before
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

Các giá trị **:status**, **:min_total** và **:created_from** là bind parameters; kiểu của chúng phải tương thích với DB schema.

Trong ứng dụng thực tế, nhiều filter là tùy chọn. Có hai cách thường gặp:

1. **Thêm predicate có điều kiện** vào Criteria API, QueryDSL, Specification hoặc câu SQL được build với tham số bind.
2. Dùng mẫu **(:status IS NULL OR status = :status)**; đơn giản nhưng với một số database/kế hoạch thực thi có thể làm giảm khả năng chọn index và tối ưu truy vấn.

Khi số filter nhiều và bảng lớn, cách (1) thường cho phép tạo điều kiện cụ thể và tối ưu dễ hơn. Cần dùng **EXPLAIN/EXPLAIN ANALYZE** hoặc công cụ của DB engine trên dữ liệu đại diện; không kết luận chỉ từ số dòng code.

### Index theo mẫu truy vấn

Với bộ lọc tenant, status và thời điểm tạo, một index có thể đáng thử:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Index này **không chắc tối ưu cho mọi query**. Nếu bỏ status hoặc range total có độ chọn lọc cao, planner có thể chọn index khác. Thứ tự cột và nhu cầu index phụ thuộc thống kê dữ liệu, cardinality, phân bố tenant, tần suất truy vấn, chi phí ghi và engine.

Các nguyên tắc:

- Đo **selectivity** từng filter, ví dụ status PAID chiếm 90% có thể lọc kém.
- Ưu tiên index hỗ trợ ràng buộc tenant/ownership và cách sort thường dùng.
- Tránh tạo index cho mọi tổ hợp filter: tăng chi phí ghi, lưu trữ và bảo trì.
- Đặt giới hạn **size**, độ sâu phân trang và thời hạn thực thi để giảm nguy cơ query quá nặng.
- Nếu người dùng cần analytics phức tạp, cân nhắc read model/search index/data warehouse phù hợp thay vì mở rộng endpoint OLTP vô hạn.

## 12. Java/Spring: định nghĩa hợp đồng query

Ví dụ dùng **Spring Boot 3.x, Java 17+ và Spring Data JPA**. Giả định entity **OrderEntity** có các field: **id**, **tenantId**, **customerId**, **status**, **total** (BigDecimal), **currency**, **createdAt** (Instant). Vì bài tập dùng VND, cận total được diễn đạt trong đơn vị VND.

### 12.1. DTO của bộ lọc và kết quả

~~~java
public enum OrderStatus {
    PENDING, PAID, SHIPPED, CANCELLED
}

public record OrderFilter(
        OrderStatus status,
        String customerId,
        Instant createdFrom,
        Instant createdBefore,
        BigDecimal minTotal,
        BigDecimal maxTotal
) {}

public record OrderView(
        String id,
        OrderStatus status,
        BigDecimal total,
        String currency,
        Instant createdAt
) {}

public record OrderPageResponse(
        List<OrderView> items,
        int page,
        int size,
        long totalItems
) {}
~~~

**OrderFilter** không chứa tenantId do client tự cung cấp. Scope bảo mật sẽ được suy ra từ authentication và chuyển vào tầng query một cách độc lập.

### 12.2. Controller kiểm tra kiểu và khoảng

~~~java
@RestController
@RequestMapping("/api/v1/orders")
@Validated
public class OrderQueryController {

    private final OrderQueryService service;
    private final TenantAccess tenantAccess;

    public OrderQueryController(
            OrderQueryService service,
            TenantAccess tenantAccess) {
        this.service = service;
        this.tenantAccess = tenantAccess;
    }

    @GetMapping
    public OrderPageResponse list(
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false) String customerId,
            @RequestParam(required = false)
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                Instant createdFrom,
            @RequestParam(required = false)
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                Instant createdBefore,
            @RequestParam(required = false) BigDecimal minTotal,
            @RequestParam(required = false) BigDecimal maxTotal,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            Authentication authentication) {

        if (createdFrom != null && createdBefore != null
                && !createdFrom.isBefore(createdBefore)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "createdFrom phải trước createdBefore");
        }

        if (minTotal != null && minTotal.signum() < 0
                || maxTotal != null && maxTotal.signum() < 0
                || minTotal != null && maxTotal != null
                    && minTotal.compareTo(maxTotal) > 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Khoảng total không hợp lệ");
        }

        String tenantId = tenantAccess.authorizedTenantId(authentication);
        OrderFilter filter = new OrderFilter(
                status, customerId, createdFrom, createdBefore,
                minTotal, maxTotal);

        return service.find(tenantId, filter, page, size);
    }
}
~~~

Các import cho MVC, Validation, BigDecimal, Instant và Security được lược bỏ để tập trung vào contract. **TenantAccess** là thành phần ứng dụng tự cài đặt: nó chỉ trả tenant đang được principal phép truy cập; không lấy tenantId mù quáng từ request. Nếu tài khoản được quyền thao tác nhiều tenant, cần hợp đồng chọn tenant và kiểm tra membership rõ ràng.

Code này minh họa **một status chính xác**, kết hợp AND với các field khác. Để hỗ trợ **nhiều status có OR**, cần mở rộng contract và controller nhận danh sách giá trị lặp với validation riêng. **Strict rejection của unknown/duplicated singleton parameters** ở phần 8 cũng phải được cài thêm, vì Spring MVC mặc định không tự bảo đảm đúng chính sách strict đã đề xuất.

**Chú ý validation:** Trong production cần kiểm tra chuỗi **customerId** không rỗng, đúng độ dài/định dạng; giới hạn precision và scale của BigDecimal; chuẩn hóa thông báo lỗi khi enum/Instant không parse được. Nếu dùng @Min/@Max trên tham số controller, cần bật hỗ trợ method validation phù hợp phiên bản Spring.

### 12.3. Repository và Specification xây predicate động

~~~java
public interface OrderRepository extends
        JpaRepository<OrderEntity, UUID>,
        JpaSpecificationExecutor<OrderEntity> {
}
~~~

Ví dụ service:

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderPageResponse find(
            String tenantId, OrderFilter f, int page, int size) {

        Specification<OrderEntity> spec = (root, query, cb) ->
                cb.equal(root.get("tenantId"), tenantId);

        if (f.status() != null) {
            spec = spec.and((root, query, cb) ->
                    cb.equal(root.get("status"), f.status()));
        }
        if (f.customerId() != null) {
            spec = spec.and((root, query, cb) ->
                    cb.equal(root.get("customerId"), f.customerId()));
        }
        if (f.createdFrom() != null) {
            spec = spec.and((root, query, cb) ->
                    cb.greaterThanOrEqualTo(
                        root.<Instant>get("createdAt"),
                        f.createdFrom()));
        }
        if (f.createdBefore() != null) {
            spec = spec.and((root, query, cb) ->
                    cb.lessThan(
                        root.<Instant>get("createdAt"),
                        f.createdBefore()));
        }
        if (f.minTotal() != null) {
            spec = spec.and((root, query, cb) ->
                    cb.greaterThanOrEqualTo(
                        root.<BigDecimal>get("total"), f.minTotal()));
        }
        if (f.maxTotal() != null) {
            spec = spec.and((root, query, cb) ->
                    cb.lessThanOrEqualTo(
                        root.<BigDecimal>get("total"), f.maxTotal()));
        }

        Sort order = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));

        Page<OrderEntity> found = repository.findAll(
                spec, PageRequest.of(page, size, order));

        List<OrderView> items = found.getContent().stream()
                .map(entity -> new OrderView(
                        entity.getId().toString(),
                        entity.getStatus(),
                        entity.getTotal(),
                        entity.getCurrency(),
                        entity.getCreatedAt()))
                .toList();

        return new OrderPageResponse(
                items, page, size, found.getTotalElements());
    }
}
~~~

Cách ghép predicate minh họa hai bất biến:

1. **tenantId được gắn trước tất cả filter tùy chọn**, vì đó là điều kiện phân quyền từ server.
2. Mỗi filter mới được nối bằng **AND**; từ này trở đi code và OpenAPI phải giữ đúng ngữ nghĩa đó.

Đây là code học thuật, cần bổ sung import, entity/repository thực tế, **validation**, handler **Problem Details**, security configuration và kiểm thử tích hợp trước khi chạy. Với volume lớn, truy vấn **COUNT** do Page thực hiện có thể tốn kém; cân nhắc Slice hoặc cursor. Nếu API có nhiều trạng thái, dùng predicate **root.get("status").in(statuses)** với danh sách đã parse và giới hạn, tránh viết SQL động từ chuỗi thô.

## 13. Thiết kế response và xử lý lỗi

Khi request lọc hợp lệ nhưng **không có kết quả**, câu trả lời thông thường là **200 OK với danh sách rỗng**, không phải 404:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalItems": 0
}
~~~

**404 Not Found** thường phù hợp khi **URI tài nguyên cụ thể** không tồn tại, ví dụ **GET /orders/ord-404**, chứ không phải vì tập hợp sau lọc không có phần tử.

| Tình huống | Mã HTTP phù hợp | Gợi ý |
| --- | --- | --- |
| Filter hợp lệ và có kết quả | **200 OK** | Danh sách + metadata phân trang |
| Filter hợp lệ nhưng tập rỗng | **200 OK** | items là mảng rỗng |
| Sai kiểu, enum lạ, khoảng đảo, size vượt giới hạn | **400 Bad Request** | Thông báo tên parameter và điều kiện |
| Chưa xác thực | **401 Unauthorized** | Thực hiện theo scheme xác thực |
| Không có quyền xem collection/tenant | **403 Forbidden** hoặc 404 theo chính sách che giấu | Không đưa dữ liệu hoặc tổng count của tenant khác |
| Bị giới hạn tần suất | **429 Too Many Requests** | Có thể gửi Retry-After |
| Quá tải hoặc dependency tạm ngừng | **503 Service Unavailable** | Có thể gửi Retry-After, không xem như lỗi filter |
| Yêu cầu truy vấn vượt giới hạn ứng dụng | **400** với mô tả hạn chế hoặc lỗi được contract định nghĩa | Không dùng 500 chung chung nếu chủ động từ chối |

### Problem Details cho lỗi filter

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "https://api.example.com/problems/invalid-filter",
  "title": "Invalid filter",
  "status": 400,
  "detail": "createdFrom phải trước createdBefore",
  "invalidParams": [
    {
      "name": "createdBefore",
      "reason": "Cận trên phải lớn hơn createdFrom"
    }
  ]
}
~~~

**Problem Details (RFC 9457)** cung cấp cấu trúc lỗi nhất quán; **invalidParams** trong ví dụ là **extension do API tự định nghĩa**, không phải field bắt buộc của chuẩn. Tránh phản hồi stack trace, SQL và thông tin nội bộ.

## 14. OpenAPI mô tả chính xác filter, kiểu và cận

Ví dụ OpenAPI 3.1 rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Orders Collection API
  version: 1.0.0
paths:
  /api/v1/orders:
    get:
      summary: Liệt kê đơn hàng có lọc và phân trang
      description: >
        Các filter trên các trường khác nhau kết hợp bằng AND.
        createdFrom bao gồm; createdBefore không bao gồm.
        minTotal và maxTotal đều bao gồm; tiền tính bằng VND.
        Kết quả chỉ gồm các đơn mà người gọi được phép xem.
      parameters:
        - in: query
          name: status
          description: Trạng thái chính xác (một giá trị)
          schema:
            type: string
            enum: [PENDING, PAID, SHIPPED, CANCELLED]
        - in: query
          name: customerId
          description: ID khách hàng chính xác trong phạm vi có quyền
          schema: { type: string, maxLength: 80 }
        - in: query
          name: createdFrom
          description: Timestamp cận dưới bao gồm
          schema: { type: string, format: date-time }
        - in: query
          name: createdBefore
          description: Timestamp cận trên loại trừ
          schema: { type: string, format: date-time }
        - in: query
          name: minTotal
          description: Cận dưới tiền VND bao gồm
          schema: { type: number, minimum: 0 }
        - in: query
          name: maxTotal
          description: Cận trên tiền VND bao gồm
          schema: { type: number, minimum: 0 }
        - in: query
          name: page
          schema: { type: integer, minimum: 0, default: 0 }
        - in: query
          name: size
          schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
      responses:
        '200':
          description: Danh sách khớp filter, có thể rỗng
          content:
            application/json:
              schema:
                type: object
                required: [items, page, size, totalItems]
                properties:
                  items:
                    type: array
                    items:
                      type: object
                      required: [id, status, total, currency, createdAt]
                      properties:
                        id: { type: string }
                        status: { type: string }
                        total: { type: number }
                        currency: { type: string }
                        createdAt: { type: string, format: date-time }
                  page: { type: integer }
                  size: { type: integer }
                  totalItems: { type: integer, format: int64 }
        '400':
          description: Filter hoặc phân trang không hợp lệ
          content:
            application/problem+json:
              schema: { type: object }
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
~~~

Bảng ở phần 7 đề cập **multi-value status** như một phương án mở rộng, nhưng **OpenAPI trên cố ý chỉ hỗ trợ một status**, khớp với ví dụ Java ở phần 12. Khi thêm multi-value, cập nhật controller, parser, validation, tests và OpenAPI đồng thời. Trong OpenAPI, tham số dạng array có thể dùng **style: form, explode: true** để biểu diễn **status=PAID&status=SHIPPED**.

Ngoài schema, tài liệu triển khai thực tế nên chỉ ra **các ví dụ URI**, giới hạn độ dài filter, khả năng cache, chính sách unknown parameters và yêu cầu xác thực. Đừng để docs nói lọc OR trong khi code lại lấy một giá trị.

## 15. Kiểm thử API: dữ liệu, khoảng, kết hợp và phân quyền

### 15.1. Chuẩn bị tập dữ liệu nhỏ nhưng đủ ranh giới

Giả sử server đang phục vụ tenant T1 và có các đơn sau:

| ID | Tenant | Status | Total (VND) | CreatedAt UTC |
| --- | --- | --- | ---: | --- |
| o-01 | T1 | PAID | 100.000 | 2026-11-01T00:00:00Z |
| o-02 | T1 | PAID | 300.000 | 2026-11-18T12:00:00Z |
| o-03 | T1 | PENDING | 300.000 | 2026-11-20T07:00:00Z |
| o-04 | T1 | PAID | 500.000 | 2026-11-30T23:59:59Z |
| o-05 | T1 | PAID | 500.001 | 2026-11-28T05:00:00Z |
| o-06 | T1 | PAID | 400.000 | 2026-12-01T00:00:00Z |
| o-07 | T2 | PAID | 200.000 | 2026-11-18T12:00:00Z |

Với request:

~~~text
GET /api/v1/orders
    ?status=PAID
    &createdFrom=2026-11-01T00:00:00Z
    &createdBefore=2026-12-01T00:00:00Z
    &minTotal=100000
    &maxTotal=500000
~~~

Sau khi percent-encode đúng và xác thực caller ở T1, tập kết quả phải gồm **o-01, o-02, o-04**, theo sort **createdAt DESC, id DESC** là **o-04, o-02, o-01**. Các bản ghi còn lại bị loại vì trạng thái, khoảng tiền, mốc thời gian hoặc tenant không phù hợp.

### 15.2. Ma trận test nên có

| Test | Kết quả cần chứng minh |
| --- | --- |
| Exact status=PAID | Chỉ trả status PAID, không trả PENDING |
| Exact customerId | Chỉ trả đúng customer ID được phép |
| minTotal=maxTotal=100000 | Trả những record đúng 100.000 khi dùng cận bao gồm |
| total dưới min và trên max | Bị loại chính xác |
| createdAt đúng createdFrom | Được nhận |
| createdAt đúng createdBefore | Bị loại |
| createdFrom >= createdBefore | 400 theo contract của bài |
| minTotal > maxTotal | 400, không trả tất cả |
| status=UNKNOWN hoặc minTotal=abc | 400 và lỗi chỉ rõ parameter |
| Không có filter | 200 và pagination mặc định trong tenant |
| Filter hợp lệ, không có kết quả | 200 với items rỗng |
| Kết hợp status + date + amount | Đúng **giao** của các tập điều kiện |
| Bản ghi cùng timestamp ở ranh giới trang | Sắp xếp ổn định theo id tie-breaker |
| T2 có bản ghi khớp mọi filter khác | T1 không đọc được dữ liệu/total count của T2 |
| Query parameter lạ hoặc singleton lặp | Bị từ chối đúng nếu API cam kết strict |
| Filter nhiều status | Chỉ test khi có contract, controller và OpenAPI hỗ trợ multi-value |
| Dữ liệu thay đổi trong lúc phân trang | Hành vi nhất quán với contract, không hứa snapshot nếu chưa cung cấp |
| Query trên dataset lớn | Độ trễ, số row scan và giới hạn tài nguyên nằm trong SLO |

### 15.3. Ví dụ MockMvc tập trung vào giao điểm điều kiện

~~~java
@Test
void filtersByExactStatusAndInclusiveExclusiveRange() throws Exception {
    mockMvc.perform(get("/api/v1/orders")
            .param("status", "PAID")
            .param("createdFrom", "2026-11-01T00:00:00Z")
            .param("createdBefore", "2026-12-01T00:00:00Z")
            .param("minTotal", "100000")
            .param("maxTotal", "500000")
            .param("page", "0")
            .param("size", "20"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(3))
        .andExpect(jsonPath("$.items[0].id").value("o-04"))
        .andExpect(jsonPath("$.items[1].id").value("o-02"))
        .andExpect(jsonPath("$.items[2].id").value("o-01"));
}
~~~

Ví dụ giả định dữ liệu fixture ở trên được nạp và caller đã được **xác thực là tenant T1**. Trong project Spring Security thật, cần gắn principal/token test phù hợp; không tắt phân quyền để làm test pass.

Thêm test âm tính:

~~~java
@Test
void rejectsReversedDateRange() throws Exception {
    mockMvc.perform(get("/api/v1/orders")
            .param("createdFrom", "2026-12-01T00:00:00Z")
            .param("createdBefore", "2026-11-01T00:00:00Z"))
        .andExpect(status().isBadRequest());
}

@Test
void returnsEmptyPageForValidFilterWithNoMatches() throws Exception {
    mockMvc.perform(get("/api/v1/orders")
            .param("status", "CANCELLED"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(0));
}
~~~

Các test trên là ví dụ hợp đồng, cần import và fixture thực tế. Để chứng minh isolation đa tenant, kiểm thử tích hợp qua database thật hoặc container DB tương thích, kiểm tra cả nội dung **items** lẫn **totalItems**; kiểm thử đơn vị của controller không đủ để phát hiện query thiếu điều kiện tenant.

## 16. Hiệu năng, caching và quan sát trong production

### 16.1. Bộ lọc có thể tạo tải lớn

Một request size 100 không có nghĩa database chỉ đọc 100 row. Truy vấn có thể scan nhiều triệu bản ghi mới lấy được các row phù hợp. Với dữ liệu lớn cần theo dõi:

- **p95/p99 latency** theo nhóm filter.
- Số row scanned, execution plan, index usage, slow queries.
- Năng lực CPU/IO database, memory sort, lock contention, connection pool.
- Số trang truy cập sâu, kích thước page, tần suất count query.
- Số lượng request do client gửi và tần suất retry.

Cần áp giới hạn size, rate limit và timeout; chặn những phép lọc hoặc sort quá đắt nếu không phù hợp SLO. Với hệ thống có full-text search, phân tích nhiều trường hoặc tổng hợp phức tạp, có thể tách sang read model/search engine để không làm quá tải database giao dịch.

### 16.2. Cache của kết quả lọc

GET thường có thể cache về mặt phương thức, nhưng **có nên cache hay không** phụ thuộc vào dữ liệu và quyền. Collection đơn hàng chứa thông tin riêng tư: nên chọn **Cache-Control: private** hoặc **no-store** tùy mức nhạy cảm và yêu cầu ứng dụng. Ví dụ response ở phần 9 dùng **private, no-store** để minh họa không lưu kết quả.

Nếu cache kết quả filter tại backend, khóa cache ít nhất phải tính đến:

- Bộ lọc được chuẩn hóa: status, cận thời gian/số, customerId.
- Page/cursor và sort.
- Tenant, phạm vi quyền và các thông số ảnh hưởng representation.
- Phiên bản dữ liệu hoặc quy tắc invalidation khi đơn thay đổi.

**Không dùng chung cache giữa hai tenant** chỉ vì URL filter giống nhau. Các ETag/conditional GET cho collection cần phản ánh **cả representation theo query và quyền**, không dùng ETag của một resource riêng lẻ để validator cho mọi kết quả tìm kiếm.

### 16.3. Logging an toàn

Có thể ghi lại **tên filter**, cardinality kết quả, thời gian truy vấn và ID tương quan; che hoặc băm giá trị nhạy cảm theo chính sách. Tránh đưa toàn bộ query chứa dữ liệu cá nhân vào log công khai. Metrics gắn raw customerId hoặc search string làm label có thể gây **high cardinality**, tăng chi phí và giảm chất lượng giám sát.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Không xác định AND/OR | Client hiểu sai tập kết quả | Công bố các field khác là AND, multi-value cùng field là OR nếu hỗ trợ |
| Tên cận mơ hồ | Trùng hoặc thiếu record ở thời điểm giáp ranh | Dùng createdFrom bao gồm, createdBefore loại trừ |
| So timestamp bằng chuỗi | Sai múi giờ/offset và thứ tự | Parse về Instant, so bằng kiểu thời gian |
| Dùng float cho tiền | Sai ranh giới so sánh | Dùng BigDecimal/đơn vị nhỏ nhất, quy định currency |
| Bỏ qua enum/parameter sai | Trả quá nhiều kết quả ngoài ý muốn | Validate và trả lỗi 400 nhất quán |
| Kết quả rỗng trả 404 | Client nhầm collection không tồn tại | Trả 200 với items rỗng |
| Lọc sau khi phân trang | Thiếu kết quả, total sai và dễ rò dữ liệu | Lọc quyền/nghiệp vụ trước sort/pagination tại DB |
| Cho caller tự chọn tenantId không kiểm quyền | Truy cập chéo tenant | Tenant scope từ principal đã xác minh |
| Nối chuỗi SQL với đầu vào | SQL injection | Bind parameter, Specifications/Criteria |
| Sort theo tên cột tự do | Lộ field, query khó kiểm soát | Allowlist field sort và giới hạn query |
| Chỉ sort theo timestamp | Trang không ổn định khi timestamp trùng | Thêm unique tie-breaker |
| Không xem execution plan | Query chậm khi dữ liệu tăng | Index có đo đạc, load test và giám sát |
| Caching kết quả riêng tư dùng chung | Lộ dữ liệu giữa người dùng | Khóa cache theo quyền/tenant hoặc không cache |
| OpenAPI nói hỗ trợ multi-value, code chỉ nhận singleton | Client và server bất đồng | Đồng bộ parser, docs và contract tests |

## 18. Bài thực hành: truy vấn sản phẩm trong cửa hàng

Một API bán hàng có collection **GET /api/v1/products** với dữ liệu:

- **id**, **category**, **brand**, **status** (ACTIVE/INACTIVE).
- **price** theo VND, **createdAt** là timestamp UTC.
- **stockQuantity**, **merchantId**; sản phẩm chỉ hiển thị khi người dùng có quyền truy cập theo phạm vi kinh doanh.
- Số lượng sản phẩm lên đến vài triệu, được thêm và cập nhật liên tục.

Yêu cầu của client: lọc sản phẩm ACTIVE trong hai category khác nhau, giá từ **50.000 tới 300.000 VND**, được tạo trong tháng 11/2026, sắp xếp mới nhất trước, mỗi trang 25 sản phẩm. Người dùng quản trị của một merchant chỉ được xem hàng thuộc merchant đã được cấp quyền.

### Nhiệm vụ

1. **Thiết kế URI:** chọn tên query parameter cho category, status, minPrice, maxPrice, createdFrom, createdBefore, page/size. Công bố ngữ nghĩa AND/OR và cách mã hóa URL.
2. **Định nghĩa ranh giới:** cho biết sản phẩm giá đúng 50.000/300.000 và createdAt đúng 01/11 hoặc 01/12 có được nhận không; giải thích vì sao chọn khoảng thời gian nửa mở.
3. **Lập bảng truth table:** ít nhất tám sản phẩm, bao gồm giá/timestamp ở đúng cận, status khác, merchant khác, một sản phẩm nằm ngoài category; liệt kê tập ID được trả.
4. **Thiết kế lỗi:** hành vi khi minPrice > maxPrice, datetime sai, status không biết, category lặp nhiều lần, size > 100 và tham số lạ.
5. **Viết SQL tham số hóa:** bảo đảm bộ lọc merchant quyền được gắn trước khi sort/pagination; đề xuất index theo mẫu truy vấn thường dùng.
6. **Viết Spring controller/service:** dùng DTO, validate, Specifications hoặc Criteria API và PageRequest với sắp xếp ổn định.
7. **Viết OpenAPI:** mô tả enum, khoảng bao gồm/loại trừ, multi-value category, size tối đa, response 200 rỗng và Problem Details 400.
8. **Viết test:** exact match, range boundaries, AND/OR, tenant/merchant isolation, pagination, field lạ và load test trên dataset đại diện.
9. **Phân tích hiệu năng:** chọn offset hoặc cursor theo nhu cầu; kiểm tra count query, index, cache và dữ liệu thay đổi giữa các trang.

**Sản phẩm cần nộp:** URI và hợp đồng filter, bảng dữ liệu kiểm chứng, sơ đồ điều kiện logic, mã Java/Spring, OpenAPI, test cases và nhận xét về bảo mật/hiệu năng.

### Tiêu chí tự đánh giá

Một bài làm tốt cần giữ các bất biến:

- **Lọc đúng nghĩa:** exact match không tự chuyển thành full-text search; cận số/thời gian có quy tắc rõ; mọi field kết hợp đúng AND/OR.
- **Lọc đúng phạm vi:** tất cả kết quả và total count chỉ gồm tài nguyên mà caller được phép xem; dữ liệu nhạy cảm không lọt qua cache hoặc lỗi.
- **Lọc ổn định:** có sort theo khóa duy nhất, page size hợp lý, xử lý biến động dữ liệu nhất quán với hợp đồng.
- **Lọc kiểm chứng được:** OpenAPI, code, các lỗi và test cùng một ngữ nghĩa, có bằng chứng hiệu năng.

## 19. Checklist trước khi công bố endpoint lọc collection

| Câu hỏi | Chỉ coi là đạt khi |
| --- | --- |
| Đã thống nhất ý nghĩa của từng query parameter? | Biết field, kiểu, enum và cách normalize |
| Có phân biệt exact match và tìm kiếm văn bản? | Hợp đồng không nhập nhằng |
| Khoảng số/thời gian có cận rõ? | Chỉ rõ >=, >, <= hoặc < cho từng tham số |
| Có xác định vùng giờ cho lọc date? | ISO instant/offset hoặc timezone nghiệp vụ được công bố |
| Quy tắc AND/OR có rõ? | Có ví dụ kết hợp và nhóm multi-value |
| Đã xử lý null, vắng mặt, rỗng và sai kiểu? | Có kết quả/error thống nhất và test |
| Điều kiện phân quyền gắn vào truy vấn? | Không lọt dữ liệu hay số lượng của tenant/merchant khác |
| Query builder an toàn? | Bind parameters, allowlist field lọc/sort |
| Sort có ổn định? | Có tie-breaker theo khóa duy nhất |
| Page size, offset/cursor có giới hạn? | Không thể tải vô hạn hoặc quét dữ liệu tùy ý |
| Response và lỗi có hợp đồng rõ? | 200 kèm danh sách (có thể rỗng), 400 Problem Details khi sai filter |
| OpenAPI có phản ánh đúng code? | Schema, tên field, kiểu, cận và multi-value được kiểm thử |
| Có đo tải và kiểm tra index? | EXPLAIN/load test trên dữ liệu đại diện |
| Có kiểm soát cache và telemetry? | Không rò dữ liệu, không tạo metric cardinality quá cao |

## 20. Kết luận

**Lọc collection** là một phần quan trọng của hợp đồng REST API. Một endpoint GET hữu ích phải trả lời rõ: **các trường nào được lọc chính xác, khoảng nào bao gồm hay loại trừ ranh giới, các điều kiện kết hợp AND/OR ra sao, người gọi được phép thấy những tài nguyên nào và thứ tự phân trang được đảm bảo thế nào**.

Quy trình thiết kế hiệu quả là **định nghĩa ngữ nghĩa filter → chọn kiểu và cận → kiểm tra quyền → dựng predicate an toàn → sắp xếp và phân trang ổn định → mô tả OpenAPI → kiểm thử ranh giới và hiệu năng**. Khi hợp đồng và implementation cùng tuân thủ quy tắc đó, client nhận kết quả có thể giải thích được, còn server có khả năng vận hành truy vấn an toàn ngay cả khi dữ liệu tiếp tục tăng.
