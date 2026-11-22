# Sắp xếp nhiều trường và thứ tự ổn định

## 1. Vấn đề: cùng dữ liệu nhưng thứ tự trả về thay đổi

REST API thường cung cấp collection như **GET /v1/orders**, **GET /v1/products** hoặc **GET /v1/users**. Người dùng có thể muốn xem đơn hàng mới nhất, sản phẩm rẻ nhất hoặc nhân viên theo họ rồi đến tên. Khi collection có hàng nghìn bản ghi, API thường kết hợp **lọc, sắp xếp và phân trang** để trả một phần dữ liệu ở mỗi lần gọi.

Một API chỉ nói “sắp xếp theo ngày tạo giảm dần” vẫn chưa có thứ tự hoàn toàn xác định. Nhiều đơn hàng có thể được tạo cùng một mili giây; cơ sở dữ liệu được quyền trả các bản ghi có cùng giá trị ngày tạo theo thứ tự bất kỳ nếu câu truy vấn không có tiêu chí tiếp theo. Điều này dễ làm client thấy kết quả **đổi vị trí giữa các lần gọi**, xuất hiện **bản ghi trùng hoặc thiếu khi chuyển trang**, và khiến kiểm thử không ổn định.

Trong chương **Truy vấn tập hợp** của module **INTEGRATION_API_REST**, bài học này trình bày cách thiết kế **sắp xếp nhiều trường (multi-field sorting)** và **thứ tự ổn định (deterministic ordering)** như một phần của hợp đồng REST: từ query parameter, HTTP status, dữ liệu trả về đến Java/Spring, phân trang, cache, bảo mật, OpenAPI và kiểm thử.

Sau bài học, người học có thể:

1. Định nghĩa ngữ nghĩa thứ tự ưu tiên giữa nhiều khóa sắp xếp và chiều ASC/DESC.
2. Tạo thứ tự **toàn phần** bằng khóa phụ phá hòa (*tie-breaker*) duy nhất.
3. Thiết kế tham số sort có giới hạn, có whitelist, trả lỗi dễ hiểu và không để lộ trường dữ liệu nhạy cảm.
4. Phân biệt **thứ tự xác định trên một tập dữ liệu** với **tính nhất quán khi dữ liệu thay đổi giữa các trang**.
5. Thiết kế offset pagination và keyset/cursor pagination có cùng tiêu chí sắp xếp.
6. Xử lý NULL, collation, múi giờ, index và triển khai an toàn bằng Java/Spring Boot hoặc công nghệ tương đương.

## 2. Ví dụ xuyên suốt: truy vấn danh sách đơn hàng

Giả sử hệ thống bán hàng cung cấp:

~~~http
GET /v1/orders?status=PAID&sort=-createdAt,totalAmount&limit=20 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

API áp dụng ba điều kiện: chỉ trả đơn thuộc **tenant đã xác thực**, chỉ lấy **status = PAID**, và sắp xếp theo **createdAt giảm dần**, tiếp đến **totalAmount tăng dần**. Nếu hai đơn có cả ngày tạo và tổng tiền bằng nhau, hệ thống thêm **id tăng dần** để phá hòa.

Các bản ghi dưới đây là **dữ liệu giả định**; ID dùng ký hiệu ngắn cho dễ quan sát:

| ID | createdAt (UTC) | totalAmount (VND) | status |
|---|---|---:|---|
| o-103 | 2026-11-18T10:00:00Z | 200.000 | PAID |
| o-102 | 2026-11-18T10:00:00Z | 100.000 | PAID |
| o-101 | 2026-11-18T10:00:00Z | 100.000 | PAID |
| o-106 | 2026-11-18T09:59:00Z | 50.000 | PAID |
| o-104 | 2026-11-18T09:59:00Z | 50.000 | PAID |
| o-105 | 2026-11-18T09:58:00Z | 500.000 | PAID |

Nếu áp dụng đúng thứ tự **createdAt DESC, totalAmount ASC, id ASC**, kết quả là:

| Vị trí | ID | Vì sao đứng ở vị trí này? |
|---:|---|---|
| 1 | **o-101** | Ngày mới nhất, tiền thấp nhất trong nhóm cùng ngày, ID nhỏ hơn o-102 |
| 2 | **o-102** | Cùng ngày và tiền như o-101, nhưng ID lớn hơn |
| 3 | **o-103** | Cùng ngày mới nhất, tiền cao hơn |
| 4 | **o-104** | Ngày cũ hơn; tiền bằng o-106, ID nhỏ hơn |
| 5 | **o-106** | Cùng ngày và tiền như o-104, ID lớn hơn |
| 6 | **o-105** | Ngày cũ nhất |

Đây là kết quả **so sánh từ trái qua phải**: chỉ nhìn khóa tiếp theo khi các khóa trước bằng nhau. Nó **không phải** là ba lượt sắp xếp độc lập mà mỗi lượt thay thế thứ tự của lượt trước.

## 3. Hợp đồng REST cho nhiều khóa sắp xếp

### 3.1. Chọn một cú pháp rõ ràng

Ví dụ bài học chọn **một query parameter sort**, các khóa cách nhau bởi dấu phẩy:

~~~text
GET /v1/orders?sort=-createdAt,totalAmount
GET /v1/orders?sort=status,-createdAt
GET /v1/orders?sort=totalAmount
GET /v1/orders                         # mặc định: -createdAt
~~~

Quy ước:

- **Dấu trừ đứng đầu** một tên trường có nghĩa **DESC**.
- **Không có dấu trừ** nghĩa là **ASC**.
- **Thứ tự trường trong chuỗi** là thứ tự ưu tiên; khóa đầu tiên quyết định chính, khóa thứ hai chỉ dùng khi khóa trước bằng nhau.
- **Server luôn thêm id ASC** làm khóa phá hòa nếu client chưa được phép điều khiển khóa này.
- **Khóa trùng**, tên không được hỗ trợ, phần tử rỗng hoặc quá nhiều trường đều bị từ chối với **400 Bad Request**.

Như vậy, **sort=-createdAt,totalAmount** được chuẩn hóa thành **createdAt DESC, totalAmount ASC, id ASC**; trong ví dụ này client **không được gửi id trong sort**, vì đó là khóa kỹ thuật hệ thống thêm vào.

Một API khác có thể chọn **sort=createdAt:desc,totalAmount:asc** hoặc nhiều tham số sort lặp lại, nhưng không nên hỗ trợ nhiều cú pháp không thống nhất. Đặc biệt, đừng đổi ý nghĩa giữa **sort=a,b** và **sort=b,a** vì thứ tự khóa là một phần của hợp đồng.

### 3.2. Danh sách trường được phép

| Trường công khai | Kiểu dữ liệu | Hướng được hỗ trợ | Quy tắc |
|---|---|---|---|
| **createdAt** | Instant, không NULL | ASC/DESC | So sánh thời điểm UTC, cùng độ chính xác lưu ở DB |
| **totalAmount** | Decimal, không NULL | ASC/DESC | So sánh số tiền, không so sánh chuỗi định dạng có dấu phân cách |
| **status** | Enum, không NULL | ASC/DESC | Sắp theo mã ổn định hoặc thứ tự nghiệp vụ được công bố |
| **id** | UUID hoặc ID duy nhất, không NULL | Server áp dụng ASC | Khóa cuối bảo đảm không hòa toàn bộ |

**createdAt** trong REST là tên trường công khai. Nó có thể ánh xạ đến cột **created_at** trong SQL hoặc thuộc tính **createdAt** trong JPA, nhưng **không cho client tùy ý truyền tên cột**, đường dẫn association hoặc biểu thức SQL.

Một trường được phép **lọc** không nhất thiết được phép **sắp xếp**. Có thể cho filter theo customerId nhưng cấm sort theo customerEmail, token, số thẻ hoặc trường nội bộ, vì đó là thông tin nhạy cảm hoặc làm tăng chi phí truy vấn.

### 3.3. Response mô tả thứ tự đã áp dụng

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "items": [
    {
      "id": "o-101",
      "createdAt": "2026-11-18T10:00:00Z",
      "totalAmount": "100000",
      "status": "PAID"
    },
    {
      "id": "o-102",
      "createdAt": "2026-11-18T10:00:00Z",
      "totalAmount": "100000",
      "status": "PAID"
    }
  ],
  "appliedSort": [
    {"field": "createdAt", "direction": "DESC"},
    {"field": "totalAmount", "direction": "ASC"},
    {"field": "id", "direction": "ASC", "implicit": true}
  ],
  "nextCursor": "opaque-signed-cursor"
}
~~~

**appliedSort** không phải field chuẩn bắt buộc của REST, mà là cách công bố thứ tự thực tế để frontend và bên tích hợp dễ kiểm tra. **nextCursor** là token opaque do server cấp; ví dụ trên chỉ minh họa cấu trúc, chưa phải một cursor hợp lệ. Tài liệu API phải nêu rõ sort mặc định, trường hợp không có dữ liệu, trường null, pagination và thời hạn cursor.

### 3.4. Có nên tự động sửa tham số sai?

Không nên lặng lẽ bỏ qua **sort=-craetedAt** (gõ sai) rồi trả thứ tự mặc định. Client có thể tưởng dữ liệu đã được sắp xếp theo yêu cầu, dẫn đến lỗi khó phát hiện.

~~~http
GET /v1/orders?sort=-craetedAt HTTP/1.1

HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-sort",
  "title": "Bad Request",
  "status": 400,
  "detail": "Trường sắp xếp không được hỗ trợ.",
  "code": "INVALID_SORT",
  "allowedFields": ["createdAt", "totalAmount", "status"]
}
~~~

Danh sách **allowedFields** trong body phải chỉ chứa thông tin công khai được phép tiết lộ. Không đưa tên cột nội bộ, chuỗi SQL hoặc stack trace cho client.

## 4. Vì sao chỉ ORDER BY một trường chưa đủ?

Quan hệ cơ sở dữ liệu là một tập các hàng; **SQL không bảo đảm thứ tự hàng nếu thiếu ORDER BY**. Ngay cả khi có ORDER BY, các hàng có cùng giá trị ở toàn bộ biểu thức sắp xếp vẫn **chưa được định thứ tự** với nhau.

Ví dụ:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC;
~~~

Hai đơn cùng **created_at** có thể xuất hiện theo thứ tự khác nhau giữa các lần thực thi do cách truy cập index, parallel query, kế hoạch thực thi hoặc thay đổi dữ liệu. Việc “thử nhiều lần vẫn thấy giống nhau” không tạo nên bảo đảm hợp đồng.

### 4.1. Thứ tự toàn phần bằng khóa duy nhất

Khi sắp xếp nhiều trường, thêm một **khóa cuối cùng duy nhất**:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
ORDER BY
    created_at DESC,
    total_amount ASC,
    id ASC;
~~~

Với giả định **id duy nhất và không NULL**, mọi cặp hàng khác nhau đều phân biệt ở ít nhất một khóa. Do đó, trong **cùng snapshot dữ liệu**, kết quả có một thứ tự xác định.

**Không nhất thiết khóa cuối phải là ID toàn cục**: nếu query chỉ trả một tenant thì cặp **(tenant_id, local_order_number)** có thể đủ duy nhất khi tenant_id đã cố định. Nhưng khóa phá hòa phải **thực sự duy nhất trong tập kết quả**; không chọn status, updatedAt hoặc tên khách hàng vì chúng có thể trùng.

### 4.2. Khóa phá hòa phải ổn định

Khóa cuối nên:

- **Không đổi** trong vòng đời resource (ID bất biến là lựa chọn phổ biến).
- **Duy nhất** trong phạm vi query.
- Có **kiểu so sánh xác định** ở database (số, UUID, mã định danh được chuẩn hóa).
- Có thể tham gia index và truy vấn cursor nếu cần.
- Không chứa thông tin nhạy cảm không cần thiết; client có thể không thấy khóa thật, nhưng server vẫn dùng để phân trang.

Nếu một trường sắp xếp chính thường xuyên thay đổi như **updatedAt**, thứ tự vẫn xác định ở **một thời điểm**, nhưng bản ghi có thể di chuyển sang vị trí khác khi cập nhật. Khóa phá hòa không làm dữ liệu trở thành snapshot cố định giữa các HTTP request.

### 4.3. “Stable sort” có hai nghĩa dễ nhầm

Trong thuật toán, **stable sorting algorithm** giữ thứ tự ban đầu của những phần tử có khóa bằng nhau. Nhưng trong SQL, **thứ tự ban đầu của các hàng không được bảo đảm** nếu không có ORDER BY tương ứng.

Trong thiết kế REST, “thứ tự ổn định” ở bài này nghĩa là **deterministic total ordering**: với cùng dữ liệu, cùng filter, cùng quy tắc so sánh và cùng khóa phá hòa, các hàng được xác định vị trí tương đối. Nó **không ngụ ý** dữ liệu giữa nhiều request luôn không đổi, cũng không đảm bảo offset pagination chống trùng khi có ghi đồng thời.

## 5. Thứ tự nhiều trường là so sánh từ trái sang phải

Giả sử SQL:

~~~sql
ORDER BY status ASC, created_at DESC, total_amount ASC, id ASC
~~~

Cách hiểu:

1. So sánh **status** trước. Nếu hai đơn khác status, thứ tự do status quyết định; không xét các khóa sau.
2. Nếu cùng status, so sánh **created_at** từ mới đến cũ.
3. Nếu vẫn bằng nhau, so sánh **total_amount** từ thấp đến cao.
4. Nếu tất cả vẫn bằng nhau, so sánh **id** từ nhỏ đến lớn.

Đây là **lexicographic ordering**. Một hàng có status được xếp trước luôn đứng trước hàng có status được xếp sau, dù ngày tạo hoặc tổng tiền ở hàng đó lớn hay nhỏ đến đâu.

### 5.1. Nhiều trường không phải nhiều lượt sort riêng

Mã minh họa sau **không phải cách viết SQL**:

~~~text
sortBy(status)
sortBy(createdAt DESC)
sortBy(totalAmount)
~~~

Nếu các lượt sort là **không ổn định** hoặc thứ tự áp dụng không đúng, kết quả sẽ khác ý định ban đầu. Trong cơ sở dữ liệu, hãy biểu diễn cùng lúc tất cả khóa bằng một **ORDER BY** theo đúng mức ưu tiên. Trong Java xử lý collection **sau khi đã phân trang**, việc sort lại còn làm sai thứ tự toàn bộ tập kết quả.

### 5.2. Quy tắc cho giá trị bằng nhau

Một query không có **id ASC** cuối có thể cho:

~~~text
Trang 1: o-101, o-102
Trang 2: o-102, o-103
~~~

nếu các hàng được DB trả lại theo thứ tự khác nhau giữa hai request và phạm vi cắt trang đi qua nhóm khóa bằng nhau. Thêm khóa cuối duy nhất loại bỏ dạng **mơ hồ do hòa khóa** trong cùng dữ liệu, nhưng nếu có hàng mới chèn vào đầu danh sách giữa hai request, offset vẫn có thể trùng như sẽ phân tích sau.

## 6. NULL, chữ hoa/thường, dấu tiếng Việt và kiểu dữ liệu

Một hợp đồng sắp xếp chưa đầy đủ nếu chỉ nói ASC/DESC. Đầu tiên cần xác định **giá trị có thể NULL không, quy tắc so sánh chuỗi là gì, cùng một trường có kiểu dữ liệu thống nhất không**.

### 6.1. Chọn vị trí cho NULL rõ ràng

Ví dụ một collection nhân viên có **lastLoginAt** có thể NULL vì tài khoản chưa đăng nhập. Client muốn xem người đăng nhập gần đây nhất nhưng không muốn những người chưa đăng nhập đứng đầu.

~~~text
GET /v1/users?sort=-lastLoginAt

Chính sách công bố:
lastLoginAt DESC, NULLS LAST, id ASC
~~~

Vị trí của NULL trong ORDER BY có thể khác nhau giữa hệ quản trị database và chiều sắp xếp. Nếu hợp đồng yêu cầu **NULL luôn ở cuối** cho cả ASC và DESC, cần triển khai rõ ràng. Một cách diễn đạt SQL tương đối phổ biến:

~~~sql
SELECT id, last_login_at
FROM users
WHERE tenant_id = :tenantId
ORDER BY
  CASE WHEN last_login_at IS NULL THEN 1 ELSE 0 END ASC,
  last_login_at DESC,
  id ASC;
~~~

Một số database hỗ trợ **NULLS FIRST/NULLS LAST** trực tiếp; một số không hỗ trợ hoặc có khác biệt khi dùng index. Cách dùng CASE làm thứ tự rõ ràng hơn về ngữ nghĩa nhưng có thể khiến optimizer không tận dụng được index sẵn có. Nếu cần hiệu năng lớn, cân nhắc index biểu thức/cột phát sinh theo cơ sở dữ liệu đang dùng.

**Quan trọng với cursor:** giá trị NULL không thể so sánh bằng toán tử lớn hơn/nhỏ hơn theo cách thông thường vì các phép so sánh với NULL không trả TRUE. Cần tạo **null rank** hoặc nhánh điều kiện rõ ràng khi tính vị trí trang kế tiếp. Không sao chép máy móc điều kiện cursor của trường NOT NULL cho trường nullable.

### 6.2. Collation quyết định thứ tự chuỗi

Hai tên sau có thể có kết quả khác nhau tùy locale và collation:

~~~text
An, anh, Ánh, Bảo, Bình, Dũng, Đỗ
~~~

Collation có thể phân biệt hoặc bỏ qua chữ hoa/thường, dấu, quy tắc so sánh Unicode, và có thể thay đổi theo cấu hình DB/OS hoặc phiên bản thư viện. Vì vậy:

- Nếu endpoint hỗ trợ **sort=displayName**, công bố chính sách đủ rõ: nhạy hoặc không nhạy chữ hoa/dấu, locale (ví dụ tiếng Việt) nếu có yêu cầu.
- Không giả định **ORDER BY display_name** tự động có kết quả giống chức năng so sánh chuỗi ở Java hoặc frontend.
- Khi collation xem hai chuỗi là bằng nhau, vẫn cần **id** phá hòa.
- Nếu thay collation, tính đến **phiên bản cursor, index và thứ tự client quan sát**; cursor cũ có thể không còn hợp lệ.
- Tránh sắp xếp bằng giá trị hiển thị đã format (tiền có dấu chấm/phẩy, ngày địa phương) nếu dữ liệu gốc có kiểu số/thời gian.

### 6.3. Thời gian và decimal

**createdAt** nên được lưu như thời điểm có nghĩa rõ (chẳng hạn Instant/UTC) và so sánh theo giá trị thời gian, không theo chuỗi ngày đã format để hiển thị. Nếu client muốn **ngày theo múi giờ địa phương**, đó là yêu cầu truy vấn khác: phải quy đổi khoảng thời gian và công bố zone, không đổi ngầm ý nghĩa của sort.

**totalAmount** cần kiểu decimal chính xác hoặc số nguyên đơn vị nhỏ nhất, không biến thành VARCHAR để sắp xếp. Nếu lưu chuỗi **"100"**, **"20"**, phép so sánh chuỗi có thể xếp "100" trước "20" dù số 100 lớn hơn 20. Đơn nhiều tiền tệ cần chính sách riêng: sắp xếp tổng tiền thô khác tiền đã quy đổi, và không thể so giá trị 100 USD với 100 VND nếu nghiệp vụ chưa định nghĩa quy đổi.

### 6.4. Thứ tự cho enum không nên dựa vào tình cờ

Với **status**, có ít nhất hai cách sắp xếp:

| Cách | Ví dụ | Hệ quả |
|---|---|---|
| Theo mã chữ | CANCELLED, PAID, PENDING | Dễ giải thích, nhưng đổi mã ảnh hưởng thứ tự |
| Theo mức ưu tiên nghiệp vụ | PENDING, PAID, CANCELLED | Cần **statusRank** được định nghĩa, version và mapping rõ |

Nếu dùng thứ tự nghiệp vụ, backend có thể sắp theo biểu thức CASE hoặc cột rank riêng, nhưng API vẫn công bố tên sort là **status**. Không để thứ tự ordinal của enum Java tự trở thành hợp đồng công khai vì việc thêm enum mới hoặc đổi vị trí enum có thể làm thứ tự thay đổi.

## 7. Offset pagination: khóa phá hòa cần thiết nhưng chưa đủ

Offset pagination phổ biến vì đơn giản:

~~~text
GET /v1/orders?sort=-createdAt,totalAmount&limit=2&offset=0
GET /v1/orders?sort=-createdAt,totalAmount&limit=2&offset=2
~~~

SQL tương ứng:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, total_amount ASC, id ASC
LIMIT :limit OFFSET :offset;
~~~

**Mỗi trang phải dùng cùng filter và ORDER BY đầy đủ**, nếu không ranh giới trang không có ý nghĩa. Khi tập dữ liệu không đổi, thêm id cuối giúp client đi qua trang 1, 2, 3 theo một thứ tự duy nhất.

### 7.1. Vẫn có thể trùng khi dữ liệu thay đổi

Giả sử collection được sắp từ mới đến cũ, page size = 2:

~~~text
Thời điểm T1: [o-10, o-09, o-08, o-07]
Trang 1, offset 0: [o-10, o-09]

Sau đó có o-11 mới:
Thời điểm T2: [o-11, o-10, o-09, o-08, o-07]
Trang 2, offset 2: [o-09, o-08]
~~~

**o-09 xuất hiện hai lần**, dù mỗi câu SQL đều có khóa phá hòa duy nhất. Nguyên nhân là OFFSET đếm vị trí từ đầu tập dữ liệu **ở từng thời điểm**. Nếu một bản ghi bị xóa trước vị trí trang, client có thể **bỏ sót** bản ghi khác theo cơ chế tương tự.

Vì vậy cần phân biệt:

1. **Deterministic order:** cùng tập bản ghi và cùng quy tắc so sánh → cùng vị trí tương đối.
2. **Stable pagination across requests:** nhiều trang đọc ra một snapshot nhất quán hoặc có chiến lược con trỏ phù hợp khi có thay đổi.

Khóa id giải quyết vấn đề (1); **không tự giải quyết hoàn toàn vấn đề (2)**.

### 7.2. Chi phí offset lớn

Với OFFSET = 500.000, database thường phải đi qua hoặc xử lý số lượng lớn hàng trước khi trả 20 hàng tiếp theo. Cách thực thi thực tế phụ thuộc index, bộ lọc và query planner, nhưng offset sâu thường ngày càng tốn CPU/I/O.

Offset có thể phù hợp với:

- Bảng quản trị dữ liệu nhỏ, ít thay đổi và cần nhảy tới trang số bất kỳ.
- Báo cáo tĩnh hoặc dữ liệu có snapshot riêng.
- Tập kết quả giới hạn có index tốt và offset tối đa được kiểm soát.

Nên áp dụng **max limit, max offset/page**, index và metrics độ trễ; không dùng offset sâu vô hạn với collection cập nhật liên tục mà kỳ vọng không trùng/thiếu.

## 8. Keyset/cursor pagination: tiếp tục sau một bộ khóa

Thay vì ghi “bỏ qua N hàng”, **keyset pagination** lưu bộ giá trị sắp xếp của hàng cuối trang trước, rồi hỏi database: **những hàng đứng sau bộ khóa đó theo cùng thứ tự là gì?**

Ví dụ thứ tự cố định:

~~~sql
ORDER BY created_at DESC, total_amount ASC, id ASC
~~~

Trang đầu:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'PAID'
ORDER BY created_at DESC, total_amount ASC, id ASC
LIMIT :limitPlusOne;
~~~

Với cursor cuối chứa **(createdAt = :lastCreatedAt, totalAmount = :lastTotalAmount, id = :lastId)**, trang tiếp theo:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'PAID'
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND total_amount > :lastTotalAmount
      )
      OR (
          created_at = :lastCreatedAt
          AND total_amount = :lastTotalAmount
          AND id > :lastId
      )
  )
ORDER BY created_at DESC, total_amount ASC, id ASC
LIMIT :limitPlusOne;
~~~

Lý do dùng các dấu khác nhau:

- **createdAt DESC:** những hàng đứng sau có createdAt **nhỏ hơn**, nên dùng dấu **<**.
- Khi createdAt bằng nhau, **totalAmount ASC:** những hàng đứng sau có tiền **lớn hơn**, nên dùng dấu **>**.
- Khi hai khóa trên bằng nhau, **id ASC:** hàng đứng sau có id **lớn hơn**, nên dùng dấu **>**.

Nếu đảo chiều một trường trong ORDER BY, **toán tử so sánh ở nhánh cursor tương ứng cũng phải đảo**. Không thể dùng một biểu thức WHERE cố định cho mọi cấu hình sort. Các trường trong ví dụ cursor đều **NOT NULL**; với trường nullable, áp dụng quy tắc null rank ở Mục 6.

### 8.1. Lấy limit + 1 để biết còn trang

Nếu client yêu cầu **limit=20**, truy vấn **21 hàng**. Server trả tối đa 20, và chỉ tạo **nextCursor** khi có hàng thứ 21. Giá trị khóa trong nextCursor lấy từ **hàng thứ 20 đã thực sự trả**, không lấy hàng phụ thứ 21.

Quy trình:

~~~text
Đọc và xác minh cursor (nếu có)
  -> xác thực/ủy quyền tenant
  -> áp cùng filter, sort và điều kiện "sau cursor"
  -> query tối đa limit + 1 hàng
  -> có hàng thừa? trả 20 và cursor của hàng 20
  -> không có hàng thừa? trả tất cả và nextCursor = null
~~~

Đây là cách phổ biến, nhưng không phải duy nhất. Nếu client cần **trang trước**, phải thiết kế riêng cursor ngược, đảo điều kiện so sánh và đảo thứ tự lại trước khi trả response. Không nên tạo previousCursor chỉ bằng cách trừ offset của một cursor.

### 8.2. Cursor là hợp đồng opaque

Một cursor có thể bao gồm:

~~~json
{
  "version": 1,
  "sort": [
    ["createdAt", "DESC"],
    ["totalAmount", "ASC"],
    ["id", "ASC"]
  ],
  "last": {
    "createdAt": "2026-11-18T10:00:00Z",
    "totalAmount": "100000",
    "id": "o-102"
  },
  "filterDigest": "sha256-of-canonical-filters",
  "scopeDigest": "digest-of-tenant-and-permission-scope",
  "expiresAt": "2026-11-18T10:15:00Z"
}
~~~

Ví dụ là **payload logic**, không phải token thực và không phải đề nghị trả JSON này cho client. Một triển khai có thể **mã hóa thành token ký HMAC** hoặc tham chiếu đến cursor lưu ở server:

- Client nhận **opaque string**, không tự xây/sửa hoặc suy luận cấu trúc.
- Server xác thực **chữ ký/toàn vẹn**, version, thời hạn, bộ lọc, thứ tự sắp xếp và **phạm vi tenant/quyền** ở lần gọi tiếp theo.
- Chữ ký chỉ bảo vệ **toàn vẹn**, không bảo đảm **bí mật**. Nếu cursor mang thông tin nhạy cảm cần tránh để lộ, dùng mã hóa có xác thực hoặc token tra cứu phía server.
- Nếu sort, filter, principal/scope hoặc dữ liệu hợp đồng đã khác, trả **400 với mã INVALID_CURSOR** hoặc lỗi được công bố; không lặng lẽ trả trang của scope khác.
- Kể cả cursor hợp lệ, **mỗi request vẫn phải xác thực và phân quyền**. Cursor không phải vé truy cập vượt quyền hoặc credential.

### 8.3. Keyset tốt hơn offset ở điểm nào?

Giả sử trang 1 trả **[o-10, o-09]** theo thứ tự giảm dần và cursor lưu khóa của **o-09**. Một đơn mới **o-11** xuất hiện trước o-10; trang 2 dùng điều kiện **nhỏ hơn khóa o-09**, nên thường tiếp tục **[o-08, o-07]** thay vì lặp o-09.

Tuy nhiên, keyset không mặc định cung cấp **snapshot nhất quán qua nhiều request**:

- Nếu một hàng chưa trả bị sửa **sort key**, nó có thể di chuyển qua ranh giới cursor và bị bỏ qua hoặc xuất hiện theo hướng khác.
- Nếu một hàng đã trả bị sửa sort key để nằm **phía sau cursor**, nó có thể xuất hiện lần nữa.
- Nếu backfill tạo một hàng có sort key cũ nằm sau cursor, client có thể thấy nó ở trang sau dù nó chưa có ở T1.
- Nếu hàng bị xóa giữa hai request, nó đương nhiên biến mất khỏi tập kết quả tiếp theo.

Keyset chủ yếu giúp **duyệt tiếp theo khóa**, giảm chi phí offset sâu và giảm lệch do **chèn ở phía trước**. Nếu yêu cầu xuất ra **đúng một snapshot không thiếu, không trùng** (đối soát tài chính, export chính thức), phải thiết kế **snapshot/materialized result, version dữ liệu, transaction snapshot được duy trì hoặc watermark bất biến** phù hợp; không chỉ thêm cursor rồi gọi là “exactly once”.

### 8.4. Khi nào cần snapshot?

| Nhu cầu | Phương án thường phù hợp | Điều cần nhớ |
|---|---|---|
| Danh sách đơn trong UI, cập nhật liên tục | Keyset/cursor với khóa ổn định | Kết quả là luồng dữ liệu theo thời điểm; cho phép nội dung mới ở đầu |
| Bảng quản trị nhỏ có nút “Trang 4” | Offset/limit có tie-breaker | Dễ nhảy trang; có thể thay đổi vị trí khi dữ liệu biến động |
| Export toàn bộ dữ liệu để đối soát | Job tạo snapshot hoặc kết quả xuất cố định | Cần mốc dữ liệu và kiểm toán, không dựa vào hàng loạt request UI |
| Infinite scrolling danh mục sản phẩm | Cursor với filter/sort đã cố định | Nếu sort theo điểm số thay đổi thường xuyên, cần cân nhắc version/snapshot |
| Danh sách theo thời điểm tạo bất biến | Cursor theo createdAt + id | Chèn trước ranh giới ít gây trùng hơn offset |

## 9. Tương tác giữa lọc, phân quyền và sắp xếp

**Thứ tự áp dụng về mặt logic:** xác định tập resource được phép xem, áp dụng filter hợp lệ, sắp xếp toàn bộ tập đó, rồi phân trang. Việc lọc theo tenant **sau khi lấy một trang** là lỗi cả về dữ liệu lẫn bảo mật.

~~~sql
SELECT id, created_at, total_amount, status
FROM orders
WHERE tenant_id = :authenticatedTenantId
  AND status = :requestedStatus
ORDER BY created_at DESC, total_amount ASC, id ASC
LIMIT :limit;
~~~

**authenticatedTenantId** phải lấy từ danh tính đã được xác minh, không được tin query param hoặc header tự do do client gửi. Nếu còn quyền theo owner/organization hoặc dữ liệu chia sẻ, biểu thức truy vấn phải bao gồm ranh giới nhìn thấy tương ứng.

### 9.1. Bộ lọc thuộc danh tính cursor

Nếu trang 1 dùng **status=PAID**, trang 2 đổi thành **status=PENDING** nhưng tiếp tục gửi cursor của PAID, giá trị khóa cuối không còn ý nghĩa đối với cùng tập dữ liệu. Server nên buộc **filter + sort + phạm vi quyền** của cursor tương thích với request mới, hoặc đưa toàn bộ filter/sort vào token đã xác thực và chỉ nhận lại token đó theo hợp đồng.

### 9.2. Sort không được là kênh suy luận thông tin

Ngay cả khi response không trả trường nhạy cảm, cho client sắp theo **salary**, **riskScore**, **internalPriority**, **lastViewedByAdmin** có thể làm lộ thứ tự tương đối hoặc ảnh hưởng thông tin suy luận. Quyền được đọc resource **không mặc nhiên** cho quyền sắp theo mọi trường của entity.

Hãy có **whitelist riêng cho từng collection và vai trò**; nếu sort yêu cầu một trường mà principal không được phép dùng, từ chối theo hợp đồng. Đừng để lỗi nêu tên cột database bị cấm hoặc tạo chênh lệch response có thể dò bảng nội bộ.

### 9.3. Phân trang phải nhất quán về phạm vi

Ngoài câu query chính, count hoặc **hasMore** cũng phải được tính trên **cùng tập quyền và filter**. Trả tổng số đơn của toàn hệ thống trong response tenant-scoped là rò rỉ dữ liệu. Với cursor, không cần trả totalCount nếu truy vấn đếm quá đắt hoặc không có snapshot phù hợp.

## 10. SQL, index và hiệu năng của sắp xếp nhiều trường

Multi-field ORDER BY có thể khiến database phải **sort rất nhiều hàng** nếu không có index thích hợp. Điều kiện WHERE, chiều của từng trường, độ chọn lọc, NULL, collation và kiểu dữ liệu ảnh hưởng kế hoạch thực thi.

### 10.1. Index theo filter và sort chủ đạo

Với truy vấn thường gặp:

~~~sql
SELECT id, created_at, total_amount, status
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, total_amount ASC, id ASC
LIMIT 21;
~~~

Một index có thể cân nhắc trên hệ quản trị cho phép khai báo chiều:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_amount_id
ON orders (
  tenant_id,
  status,
  created_at DESC,
  total_amount ASC,
  id ASC
);
~~~

**Vì sao thứ tự cột này?** tenant_id và status dùng điều kiện bằng, tiếp theo là ba khóa ORDER BY. Khi index và planner hỗ trợ, DB có thể duyệt các bản ghi theo thứ tự cần thiết mà giảm nhu cầu sort riêng. Một index theo nhiều trường không tự động tối ưu **mọi hoán vị sắp xếp**; đổi từ createdAt DESC sang totalAmount ASC làm khóa ưu tiên có thể cần index khác.

Điểm cần đo khi triển khai:

- **EXPLAIN/EXPLAIN ANALYZE** hoặc công cụ tương đương: query có index scan theo thứ tự hay tạo bước sort lớn?
- Latency **p50/p95/p99** ở page đầu và trang sâu; có ảnh hưởng khi tenant lớn không?
- Số hàng/byte đọc, memory cho sort, tình trạng spill ra disk, buffer cache và IO.
- Chi phí **ghi và lưu trữ index**: thêm index giúp đọc nhưng tăng dung lượng, tốc độ cập nhật và bảo trì.
- Thống kê dữ liệu, mức phân bố status và cardinality của tenant; cùng index có thể phù hợp tenant nhỏ nhưng không phù hợp tenant lớn.

**Không thiết kế index bằng cách nhân mọi tổ hợp field/direction.** Với API mở hàng chục sort combination, số index rất lớn. Hãy phân tích sort thực sự phổ biến, giới hạn chiều/tổ hợp được hỗ trợ khi cần, và đánh đổi UX với chi phí.

### 10.2. Mixed directions và khả năng duyệt index

Thứ tự **created_at DESC, total_amount ASC, id ASC** có chiều hỗn hợp. Một số database có thể duyệt index ngược cho trường hợp **đảo toàn bộ chiều**, nhưng không thể dựa vào khả năng đó để giả định mọi tổ hợp ASC/DESC đều dùng được index cũ. Cần kiểm tra thực tế theo từng DB/version.

Các trường hợp sort biểu thức như **LOWER(display_name)**, tính điểm xếp hạng hoặc CASE cho NULL/rank có thể cần index biểu thức/cột đã chuẩn hóa. Đừng xây query bằng **ORDER BY <chuỗi từ client>**; chỉ dùng những biểu thức cố định trong whitelist và parameter binding cho **giá trị dữ liệu**.

### 10.3. Tránh sort ngoài database sau khi đã limit

Sai về logic:

~~~text
rows = SELECT ... FROM orders LIMIT 20
sort rows by totalAmount and createdAt in Java
return rows
~~~

Hai mươi hàng được lấy ra **trước khi sắp xếp toàn tập**, nên có thể thiếu nhiều hàng đáng lẽ phải thuộc top 20. Đúng hơn là **WHERE → ORDER BY đầy đủ → LIMIT/cursor → map DTO**. Sắp xếp trong Java chỉ phù hợp nếu ứng dụng **đã có toàn bộ tập đủ nhỏ** trong memory và chủ động định nghĩa hành vi đó, không phải cách xử lý collection lớn theo trang.

### 10.4. Phân trang với join và bản ghi nhân đôi

Ví dụ GET /orders có thể join sang order_items, làm một order xuất hiện nhiều dòng. Nếu LIMIT áp lên kết quả join, một order có 5 item có thể chiếm 5 vị trí và làm sai phân trang.

Giải pháp thường gặp:

1. Phân trang trên **ID của resource gốc** theo thứ tự chuẩn với các điều kiện thích hợp.
2. Lấy representation/order items của những ID được chọn bằng truy vấn thứ hai.
3. Khôi phục đúng thứ tự ID đã chọn khi ghép DTO, không mặc định query thứ hai trả cùng thứ tự.

Hoặc chọn chiến lược JOIN/fetch/CTE phù hợp với DB và ORM. Điều quan trọng là mỗi **resource trong collection phải tương ứng một phần tử**, và khóa sắp xếp phải có nghĩa nhất quán ở mức resource, không nhân số phần tử vì relation.

## 11. Java/Spring Boot: parse và whitelist sort một cách tường minh

Ví dụ dùng **Java 17+, Spring Boot 3, Spring Data JPA**. Mục tiêu là minh họa một hợp đồng cụ thể, không yêu cầu mọi hệ thống dùng đúng Java hay repository này.

### 11.1. Parser chấp nhận đúng grammar công bố

Đoạn sau tạo Sort từ chuỗi **-createdAt,totalAmount**, giới hạn ba khóa do client chọn và **luôn thêm id ASC**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.data.domain.Sort;

public final class OrderSortParser {
    private static final Map<String, String> ALLOWED = Map.of(
        "createdAt", "createdAt",
        "totalAmount", "totalAmount",
        "status", "status"
    );

    private OrderSortParser() {}

    public static Sort parse(String raw) {
        String value = raw == null ? "-createdAt" : raw;

        if (value.isBlank() || value.length() > 120) {
            throw new InvalidSortException();
        }

        // -1 giữ cả phần tử rỗng: "createdAt," phải bị từ chối.
        String[] tokens = value.split(",", -1);
        if (tokens.length > 3) {
            throw new InvalidSortException();
        }

        List<Sort.Order> orders = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (String token : tokens) {
            boolean desc = token.startsWith("-");
            String publicName = desc ? token.substring(1) : token;
            String entityProperty = ALLOWED.get(publicName);

            if (entityProperty == null || !seen.add(publicName)) {
                throw new InvalidSortException();
            }

            orders.add(new Sort.Order(
                desc ? Sort.Direction.DESC : Sort.Direction.ASC,
                entityProperty
            ));
        }

        // id không nằm trong whitelist client: không thể bị lặp.
        orders.add(Sort.Order.asc("id"));
        return Sort.by(orders);
    }
}
~~~

**InvalidSortException** là exception ứng dụng cần khai báo và ánh xạ sang **400 Bad Request**. Parser cố ý từ chối tên có khoảng trắng, tên lạ, trùng khóa, dấu phẩy cuối và cú pháp pha trộn không được công bố. Cách parser đơn giản này dựa vào giả định **các cột được phép đều NOT NULL** và JPA mapping có tên property tương ứng.

Không nên cho client truyền **id** rồi thêm id một lần nữa, vì có thể gây ORDER BY mâu thuẫn. Bài này chọn **id là khóa ẩn do server quyết định**; nếu dự án muốn cho client điều khiển id, phải thay parser để thêm khóa phá hòa **chỉ khi chưa có khóa duy nhất** và công bố rõ hướng.

### 11.2. Áp sort trong truy vấn thuộc tenant

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    Slice<OrderEntity> findByTenantIdAndStatus(
        UUID tenantId,
        OrderStatus status,
        Pageable pageable
    );
}
~~~

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderQueryController {
    private final OrderRepository orders;
    private final OrderMapper mapper;

    OrderQueryController(OrderRepository orders, OrderMapper mapper) {
        this.orders = orders;
        this.mapper = mapper;
    }

    @GetMapping
    ResponseEntity<OrderPage> list(
            @RequestParam(defaultValue = "PAID") OrderStatus status,
            @RequestParam(required = false) String sort,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int limit,
            @AuthenticationPrincipal Jwt jwt) {

        if (page < 0 || page > 200 || limit < 1 || limit > 100) {
            throw new InvalidPaginationException();
        }
        UUID tenantId = requireValidatedTenantId(jwt);
        Sort order = OrderSortParser.parse(sort);
        Pageable pageable = PageRequest.of(page, limit, order);

        Slice<OrderEntity> result = orders.findByTenantIdAndStatus(
            tenantId, status, pageable
        );

        OrderPage response = new OrderPage(
            result.getContent().stream().map(mapper::toDto).toList(),
            result.hasNext(),
            page,
            limit
        );

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(response);
    }
}
~~~

Các lớp **OrderEntity**, **OrderMapper**, **OrderPage**, **InvalidPaginationException**, **requireValidatedTenantId** và cấu hình bảo mật là thành phần giả định phải bổ sung. API demo này sử dụng **page index kiểu offset** qua Pageable, khác API cursor ở ví dụ đầu. Khi triển khai, chọn **một giao diện pagination công khai rõ ràng** hoặc cung cấp hai chế độ có quy tắc loại trừ; đừng để client gửi page và cursor mâu thuẫn.

**Slice** thường phù hợp khi chỉ cần **hasNext** mà không cần count của toàn bộ tập, giảm nhu cầu truy vấn đếm so với Page trong nhiều cấu hình Spring Data. Nếu response cần totalElements/totalPages, dùng Page hoặc query đếm riêng theo cùng quyền/filter và cân nhắc chi phí.

### 11.3. Tầng bảo mật và xử lý lỗi

Hàm **requireValidatedTenantId** chỉ là placeholder cho cơ chế định danh: token phải được xác thực chữ ký, issuer, audience, hạn dùng và claim tenant theo policy. Nếu claim thiếu/sai, hệ thống phải từ chối ở **tầng xác thực** hoặc trả lỗi có kiểm soát, không chọn tenant mặc định.

~~~java
@RestControllerAdvice
class QueryProblemHandler {
    @ExceptionHandler({
        InvalidSortException.class,
        InvalidPaginationException.class
    })
    ResponseEntity<ProblemDetail> badQuery(RuntimeException error) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Tham số truy vấn không hợp lệ."
        );
        body.setType(URI.create(
            "https://api.example.com/problems/invalid-query"
        ));
        return ResponseEntity.badRequest()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

Ở đây exception không làm lộ cú pháp SQL, entity private hay stack trace. Có thể thêm **code=INVALID_SORT** và danh sách sort fields công khai nếu có nhu cầu phục hồi lỗi phía client. Thiếu token hoặc token không hợp lệ thuộc **401** của Spring Security; thiếu quyền trên collection có thể là **403** hoặc 404 theo chính sách nhìn thấy parent.

### 11.4. Vì sao không nhận trực tiếp Sort do client điều khiển?

Spring Data hỗ trợ ánh xạ tham số sort vào **Pageable** rất tiện lợi, nhưng nếu ứng dụng để client tự gửi tên property/path không được giới hạn, họ có thể yêu cầu sắp theo field nội bộ, association không mong đợi hoặc làm query tốn tài nguyên. ORM có thể thực hiện validation riêng, nhưng **không thay thế whitelist ở cấp hợp đồng API**.

Parser whitelist giúp:

- Cố định **tên trường công khai** và ánh xạ một chiều sang thuộc tính entity.
- Giới hạn số khóa và chiều được phép.
- Bảo đảm luôn có **id** phá hòa.
- Ngăn API tình cờ làm lộ schema và truy vấn qua các quan hệ không được duyệt.
- Cho phép version hóa hợp đồng nếu sau này thêm hoặc bỏ trường sắp xếp.

Nếu cần sắp theo computed field như **totalAmountConverted**, dùng mapping đã xét duyệt trong service/query; không ghép SQL từ chuỗi nhận trực tiếp.

## 12. Triển khai keyset với tổ hợp sort cố định

Không phải mọi sort động được Spring Data.Pageable hỗ trợ đều chuyển sang cursor bằng một phép biến đổi đơn giản. Với keyset, cần tạo **predicate theo đúng bộ field và chiều**, xử lý NULL/collation, và index phù hợp.

Một chiến lược an toàn là **chỉ hỗ trợ một vài tổ hợp sort được công bố cho chế độ cursor**. Ví dụ API:

~~~text
GET /v1/orders?status=PAID&sort=-createdAt,totalAmount&limit=20
GET /v1/orders?status=PAID&sort=-createdAt,totalAmount&limit=20&cursor=<opaque>
~~~

Chế độ cursor chọn SQL cố định theo contract, dùng **bind parameters** cho giá trị:

~~~java
@Repository
class OrderCursorRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final RowMapper<OrderRow> mapper;

    private static final String FIRST_PAGE = """
        SELECT id, created_at, total_amount, status
        FROM orders
        WHERE tenant_id = :tenantId AND status = :status
        ORDER BY created_at DESC, total_amount ASC, id ASC
        LIMIT :maxRows
        """;

    private static final String NEXT_PAGE = """
        SELECT id, created_at, total_amount, status
        FROM orders
        WHERE tenant_id = :tenantId
          AND status = :status
          AND (
               created_at < :lastCreatedAt
            OR (created_at = :lastCreatedAt
                AND total_amount > :lastAmount)
            OR (created_at = :lastCreatedAt
                AND total_amount = :lastAmount
                AND id > :lastId)
          )
        ORDER BY created_at DESC, total_amount ASC, id ASC
        LIMIT :maxRows
        """;

    OrderCursorRepository(
            NamedParameterJdbcTemplate jdbc,
            RowMapper<OrderRow> mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    List<OrderRow> query(
            UUID tenantId,
            String status,
            int limit,
            CursorPosition position) {

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("tenantId", tenantId)
            .addValue("status", status)
            .addValue("maxRows", limit + 1);

        if (position != null) {
            params.addValue(
                "lastCreatedAt",
                Timestamp.from(position.createdAt())
            );
            params.addValue("lastAmount", position.totalAmount());
            params.addValue("lastId", position.id());
        }

        return jdbc.query(
            position == null ? FIRST_PAGE : NEXT_PAGE,
            params,
            mapper
        );
    }
}
~~~

Ví dụ giả định **PostgreSQL hoặc DB hỗ trợ cú pháp LIMIT và các kiểu so sánh nêu trên**, với created_at, total_amount, id đều **NOT NULL**; CursorPosition có **Instant createdAt, BigDecimal totalAmount, UUID id**; OrderRow và mapper cần được định nghĩa. Trong triển khai thực tế phải kiểm chứng JDBC driver xử lý UTC, precision và UUID theo cách mong đợi.

**Không có nội dung cursor nào được đưa trực tiếp vào SQL template.** Tầng API cần giải mã/kiểm tra cursor từ token đã ký, đối chiếu tenant/status/sort/expiry, rồi truyền **các giá trị đã parse** cho repository. SQL template áp dụng một thứ tự **cố định**, nhờ vậy không tồn tại nhánh ORDER BY xây trực tiếp từ input.

Nếu ứng dụng bắt buộc hỗ trợ mọi tổ hợp sort động, có thể xây **một biểu diễn sort có kiểu và whitelist** cùng bộ tạo predicate theo hướng ASC/DESC/NULL, hoặc dùng DSL như Criteria/QueryDSL. Cần test kỹ tính tương đương giữa ORDER BY và điều kiện “sau cursor” cho mỗi tổ hợp; không ghép thủ công tùy tiện.

### 12.1. Trường nullable trong cursor

Giả sử sắp theo **lastLoginAt DESC NULLS LAST, id ASC**. Với cursor đang ở một hàng **lastLoginAt khác NULL**, các hàng phía sau gồm:

~~~sql
(
   last_login_at < :lastLoginAt
   OR last_login_at IS NULL
   OR (last_login_at = :lastLoginAt AND id > :lastId)
)
~~~

Khi cursor đã ở một hàng **lastLoginAt NULL**, các hàng tiếp theo phải là:

~~~sql
last_login_at IS NULL AND id > :lastId
~~~

Hai nhánh này chỉ đúng cho **DESC + NULLS LAST + id ASC**; nếu đảo chiều hoặc null policy, phải thay predicate. Đây là lý do nên **định nghĩa bộ sort được hỗ trợ có chủ đích** ở API cursor, thay vì mặc định mọi sort đều hoạt động.

## 13. Hợp đồng OpenAPI và mã trạng thái HTTP

REST không bắt buộc API phải dùng tên query parameter **sort**, cú pháp dấu trừ hay hình thức response đặc biệt. Khi đã chọn, hãy ghi thành **hợp đồng công khai** để client và server thống nhất.

### 13.1. Mã trạng thái nên xử lý

| Tình huống | HTTP status gợi ý | Ý nghĩa |
|---|---|---|
| Sort/filter hợp lệ, có kết quả | **200 OK** | Trả danh sách và metadata phân trang |
| Sort/filter hợp lệ, không có hàng nào | **200 OK** | Trả **items: []**, thường không phải 404 |
| Sort field không nằm whitelist | **400 Bad Request** | Cú pháp/ngữ nghĩa tham số truy vấn không hợp lệ |
| Sort trùng trường hoặc vượt số khóa tối đa | **400 Bad Request** | Từ chối thay vì tự bỏ bớt trường |
| Cursor hỏng, quá hạn, không khớp sort/filter/scope | **400 Bad Request** theo hợp đồng này | Có mã lỗi như INVALID_CURSOR; không tự đọc sang tenant khác |
| Limit/page vượt giới hạn | **400 Bad Request** | Giảm query quá tốn tài nguyên |
| Endpoint cần token nhưng thiếu/sai token | **401 Unauthorized** | Có WWW-Authenticate challenge phù hợp |
| Đã xác thực nhưng không được xem collection | **403 Forbidden** hoặc **404** theo chính sách | Không làm lộ resource cha nếu phải ẩn |
| Người gọi bị giới hạn tần suất | **429 Too Many Requests** | Có thể kèm Retry-After |
| Backend tìm kiếm/database tạm thời không phục vụ | **503 Service Unavailable** | Lỗi phía dịch vụ; không giả thành 400 |

**200 với items rỗng** là kết quả bình thường cho một collection đã biết mà bộ lọc không tìm thấy hàng. **404** phù hợp hơn nếu URI cha như /teams/{teamId}/members không có hoặc không được tiết lộ; cần phân biệt collection tồn tại nhưng **không có member** với **team không được truy cập**.

### 13.2. OpenAPI 3.1 cho collection có cursor

Ví dụ dưới đây mô tả biến thể **cursor** sử dụng tổ hợp sort được hỗ trợ **-createdAt,totalAmount**. Các ví dụ Java Pageable theo page và parser đa khóa ở phần trước minh họa **khả năng khác của cùng miền nghiệp vụ**. Nếu sản phẩm hỗ trợ cả cursor và offset, phải thống nhất rõ phương thức lựa chọn chế độ, tham số loại trừ nhau và các sort combination được hỗ trợ trước khi phát hành.

~~~yaml
openapi: 3.1.0
info:
  title: Order Query API
  version: 1.0.0
paths:
  /v1/orders:
    get:
      operationId: listOrders
      summary: Danh sách đơn hàng thuộc phạm vi được phép xem
      description: >
        Biến thể cursor: sắp xếp theo createdAt DESC,
        totalAmount ASC, id ASC (id được thêm ngầm).
        Cursor gắn với filter, sort và phạm vi xác thực.
      security:
        - bearerAuth: []
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [PAID, PENDING, CANCELLED]
            default: PAID
        - name: sort
          in: query
          required: false
          description: >
            Chế độ cursor này hỗ trợ duy nhất -createdAt,totalAmount.
            Một biến thể offset khác có thể hỗ trợ thêm tổ hợp.
          schema:
            type: string
            enum: ["-createdAt,totalAmount"]
            default: "-createdAt,totalAmount"
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: cursor
          in: query
          required: false
          description: Opaque cursor nhận từ nextCursor của trang trước
          schema:
            type: string
            maxLength: 2048
      responses:
        "200":
          description: Trang đơn hàng đã sắp xếp
          headers:
            Cache-Control:
              schema:
                type: string
                example: no-store
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderPage"
        "400":
          description: Query, sort, limit hoặc cursor không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "401":
          description: Không có thông tin xác thực hợp lệ
          headers:
            WWW-Authenticate:
              schema:
                type: string
        "403":
          description: Principal không được liệt kê đơn
        "429":
          description: Vượt giới hạn truy vấn
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Order:
      type: object
      required: [id, createdAt, totalAmount, status]
      properties:
        id:
          type: string
        createdAt:
          type: string
          format: date-time
        totalAmount:
          type: string
          description: Decimal của số tiền trong đơn vị tiền quy định
        status:
          type: string
    SortTerm:
      type: object
      required: [field, direction]
      properties:
        field:
          type: string
        direction:
          type: string
          enum: [ASC, DESC]
        implicit:
          type: boolean
    OrderPage:
      type: object
      required: [items, appliedSort, nextCursor]
      properties:
        items:
          type: array
          items:
            $ref: "#/components/schemas/Order"
        appliedSort:
          type: array
          items:
            $ref: "#/components/schemas/SortTerm"
        nextCursor:
          type:
            - string
            - "null"
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        code:
          type: string
~~~

**Đừng sao chép nguyên schema của biến thể cursor rồi dùng cho tất cả tổ hợp sort** nếu backend chưa có predicate đúng cho từng tổ hợp. Một API production có thể triển khai cursor theo bộ sort giới hạn, offset cho một số sort khác, hoặc thiết kế builder tổng quát đã được test đầy đủ.

### 13.3. Cache và điều kiện GET

GET vẫn là phương thức **safe** về semantics dù có tham số sắp xếp; nó không được sửa dữ liệu chỉ để sắp xếp. Tuy nhiên, response của GET collection thường phụ thuộc **tenant, principal, filter, sort và cursor**, vì thế:

- Với đơn hàng riêng tư, ví dụ sử dụng **Cache-Control: no-store** để tránh lưu response có dữ liệu nhạy cảm ở shared cache.
- Với collection công khai, có thể cache theo **toàn bộ tập query parameter có ý nghĩa** (sort, filter, limit, cursor, locale), có TTL phù hợp; không dùng cùng cache key cho các sort khác nhau.
- Nếu cache cho response phụ thuộc danh tính, phải bảo đảm phân tách principal/tenant và tuân thủ header; thường đơn giản hơn là không dùng shared cache cho loại dữ liệu này.
- Nếu cung cấp **ETag cho collection**, validator phải phản ánh representation của **trang cụ thể**: filter, sort, dữ liệu hiện tại và phạm vi, chứ không chỉ timestamp chung của bảng.
- **304 Not Modified** chỉ phù hợp nếu đã xác định đúng representation được phép xem và cache validator hợp lệ; không dùng phản hồi điều kiện làm đường vòng tiết lộ tài nguyên tenant khác.

Lưu ý: **Cache-Control: no-store** là chính sách thận trọng cho dữ liệu riêng tư, không phải yêu cầu bắt buộc của mọi REST API. Nếu ứng dụng có lý do cache private cho từng người dùng, cần thiết kế rõ quyền truy cập, thời hạn và vô hiệu hóa khi quyền thay đổi.

## 14. Kiểm thử hợp đồng sort, phân trang và phân quyền

### 14.1. Ma trận kiểm thử

| Test | Đầu vào / tình huống | Kỳ vọng |
|---|---|---|
| S01 | Không truyền sort | Dùng mặc định **createdAt DESC, id ASC** |
| S02 | sort=-createdAt,totalAmount | Đúng ưu tiên DESC, ASC và **id ASC** |
| S03 | Nhiều hàng có cùng createdAt, totalAmount | Thứ tự id duy nhất, lặp lại truy vấn cho kết quả cùng thứ tự khi tập không đổi |
| S04 | sort=status,-createdAt | Status là khóa chính; createdAt chỉ phá hòa trong cùng status |
| S05 | sort=totalAmount | Tổng tiền sắp theo **số**, không theo chuỗi |
| S06 | sort=unknownField | **400**, mã INVALID_SORT |
| S07 | sort=-createdAt,createdAt | **400** vì trùng khóa dù khác chiều |
| S08 | sort=createdAt, hoặc sort= | **400** vì token rỗng |
| S09 | sort có biểu thức SQL hoặc nested path không cho phép | **400**, không thực thi biểu thức do client gửi |
| S10 | Trường sort chứa NULL với NULLS LAST đã định nghĩa | NULL đứng cuối ở cả ASC và DESC; id phá hòa giữa NULL |
| S11 | Sort theo tên có dấu/hoa thường | Đúng collation được công bố; có test trên DB thật |
| P01 | Offset hai trang khi tập không đổi | Không trùng/thiếu; ghép đúng thứ tự toàn phần |
| P02 | Chèn hàng ở đầu trước khi gọi offset trang sau | Test thể hiện **có thể trùng**; không tuyên bố offset loại bỏ lỗi này |
| P03 | Keyset với nhiều hàng hòa khóa | Ghép hai trang đúng tất cả hàng trong tập bất biến, không trùng |
| P04 | Cursor với sort/filter khác trang đầu | Từ chối INVALID_CURSOR |
| P05 | Cursor của tenant A gửi bởi tenant B | Không trả dữ liệu tenant A |
| P06 | Cursor bị sửa chữ ký/phiên bản, hết hạn | 400 theo hợp đồng, không fallback thành trang đầu |
| P07 | limit = 0 hoặc vượt tối đa | 400; không chạy query vô hạn |
| P08 | Dataset có bản ghi sửa sort key giữa hai trang | Chứng minh giới hạn snapshot; xác định hành vi sản phẩm |
| A01 | Caller chưa xác thực | 401, challenge phù hợp |
| A02 | Hai tenant cùng filter/sort/cursor tương tự | Mỗi tenant chỉ thấy hàng của mình |
| A03 | Sort theo trường nhạy cảm bị cấm | Bị từ chối và không tiết lộ schema |
| C01 | Public cache cho hai sort khác nhau | Không dùng nhầm cache entry; response đúng thứ tự |

Không nên chỉ assert response có **20 item**. Bộ kiểm thử cần kiểm tra **thứ tự từng ID**, trường hòa, ranh giới giữa các trang, trạng thái HTTP, header cache và quyền với query tham số đã được chuẩn hóa.

### 14.2. Unit test parser

Ví dụ JUnit 5 cho parser ở Mục 11:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Sort;

class OrderSortParserTest {

    @Test
    void appendsUniqueTieBreaker() {
        Sort sort = OrderSortParser.parse("-createdAt,totalAmount");
        List<Sort.Order> orders = sort.stream().toList();

        assertEquals(3, orders.size());
        assertEquals("createdAt", orders.get(0).getProperty());
        assertEquals(Sort.Direction.DESC, orders.get(0).getDirection());
        assertEquals("totalAmount", orders.get(1).getProperty());
        assertEquals(Sort.Direction.ASC, orders.get(1).getDirection());
        assertEquals("id", orders.get(2).getProperty());
        assertEquals(Sort.Direction.ASC, orders.get(2).getDirection());
    }

    @Test
    void defaultsToNewestThenId() {
        List<Sort.Order> orders = OrderSortParser.parse(null)
            .stream().toList();
        assertEquals(List.of("createdAt", "id"),
            orders.stream().map(Sort.Order::getProperty).toList());
    }

    @Test
    void rejectsUnknownRepeatedOrEmptyField() {
        assertThrows(InvalidSortException.class,
            () -> OrderSortParser.parse("internalRiskScore"));
        assertThrows(InvalidSortException.class,
            () -> OrderSortParser.parse("createdAt,-createdAt"));
        assertThrows(InvalidSortException.class,
            () -> OrderSortParser.parse("createdAt,"));
    }
}
~~~

Các test này chỉ kiểm tra **grammar và xây dựng Sort**, chưa chứng minh database trả hàng đúng. Nếu mapping JPA, collation hoặc index không phù hợp, parser vẫn có thể pass mà API sai thực tế.

### 14.3. Contract test với Spring MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderQueryApiTest {
    @Autowired MockMvc mvc;

    @Test
    void rejectsUnsupportedSort() throws Exception {
        mvc.perform(
                get("/v1/orders")
                    .with(jwt().jwt(j -> j.claim("tenant_id", "tenant-a")))
                    .param("sort", "totalAmount;DROP TABLE orders")
            )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void rejectsTooManySortKeys() throws Exception {
        mvc.perform(
                get("/v1/orders")
                    .with(jwt().jwt(j -> j.claim("tenant_id", "tenant-a")))
                    .param(
                        "sort",
                        "createdAt,totalAmount,status,unknown"
                    )
            )
            .andExpect(status().isBadRequest());
    }
}
~~~

Đây là **test minh họa**; class cần import JUnit, Spring Test, Spring Security Test và fixture. Test dùng jwt() giả lập principal nên **không kiểm chứng chữ ký/issuer/audience/expiry của token thật**. Phải có test bảo mật tích hợp riêng để bảo đảm tenant_id đến từ danh tính hợp lệ, không do client giả mạo.

### 14.4. Integration test trên database thật

Để kiểm tra **SQL/JPA ORDER BY** và cursor, seed nhiều bản ghi có **cùng createdAt, cùng totalAmount**, sau đó:

1. Thực hiện truy vấn theo các sort được hỗ trợ và xác minh **toàn bộ chuỗi ID**.
2. Chạy lại trên cùng dữ liệu, xác minh kết quả không đổi.
3. Lặp với page size = 1, 2, 3, 20 và các bộ khóa hòa nằm ngay tại ranh giới trang.
4. Ghép tất cả trang **cursor** trong một tập dữ liệu bất biến, so sánh với kết quả query đầy đủ sử dụng đúng ORDER BY: mỗi ID xuất hiện **đúng một lần** và không thiếu ID.
5. Với tập dữ liệu chứa NULL, chữ tiếng Việt và ngày có độ chính xác cao, kiểm tra trên **cùng hệ quản trị/collation** dự kiến chạy production; một DB test in-memory có thể cho kết quả khác.
6. Dùng EXPLAIN để đo index, tăng số lượng hàng và quan sát latency/memory/IO; không chỉ test tính đúng ở 10 hàng.
7. Kiểm tra quyền tenant khi query **page 2** và khi gửi lại cursor của người dùng khác.

Một **property-based test** cũng hữu ích: tạo ngẫu nhiên nhiều bản ghi có khả năng hòa khóa cao, so sánh thứ tự từ SQL với một comparator tham chiếu đã xác định; sau đó ghép các trang cursor để chứng minh điều kiện “sau cursor” đồng nhất với ORDER BY **khi tập dữ liệu giữ nguyên**.

## 15. Bài tập thiết kế và lời giải gợi ý

### Bài tập A — Sắp xếp nhiều khóa

Cho một tập sản phẩm trong **cùng category** và **cùng tenant**, với ID là chuỗi được so sánh theo thứ tự chữ/số nhất quán:

| ID | rating | price |
|---|---:|---:|
| p-04 | 4.8 | 300 |
| p-02 | 4.9 | 250 |
| p-03 | 4.8 | 200 |
| p-01 | 4.9 | 250 |
| p-05 | 4.8 | 200 |

API nhận:

~~~text
GET /v1/products?sort=-rating,price&limit=3
~~~

**Yêu cầu:** xác định thứ tự đầy đủ sau khi server thêm id ASC, ba ID trang đầu và bộ khóa của hàng cuối để tạo cursor.

**Lời giải:**

| Vị trí | ID | rating | price |
|---:|---|---:|---:|
| 1 | p-01 | 4.9 | 250 |
| 2 | p-02 | 4.9 | 250 |
| 3 | p-03 | 4.8 | 200 |
| 4 | p-05 | 4.8 | 200 |
| 5 | p-04 | 4.8 | 300 |

Thứ tự là **rating DESC, price ASC, id ASC**. Trang đầu trả **p-01, p-02, p-03**, cursor sau trang đầu lưu **(rating=4.8, price=200, id=p-03)**, đồng thời gắn filter/sort/scope và bảo vệ token. Dùng chính **hàng thứ ba đã trả** làm ranh giới, không dùng p-05 là hàng thừa khi truy vấn limit + 1.

### Bài tập B — Viết điều kiện keyset cho chiều hỗn hợp

Một API có:

~~~sql
ORDER BY rating DESC, price ASC, id ASC
~~~

Cả ba trường đều **NOT NULL**. Cursor cuối của trang trước có **lastRating, lastPrice, lastId**. Hãy viết điều kiện SQL lấy các hàng ở phía sau.

**Lời giải:**

~~~sql
WHERE tenant_id = :tenantId
  AND category_id = :categoryId
  AND (
       rating < :lastRating
    OR (
         rating = :lastRating
         AND price > :lastPrice
       )
    OR (
         rating = :lastRating
         AND price = :lastPrice
         AND id > :lastId
       )
  )
ORDER BY rating DESC, price ASC, id ASC
LIMIT :limitPlusOne;
~~~

**Giải thích:** rating giảm nên giá trị nhỏ hơn nằm sau; price tăng nên giá trị lớn hơn nằm sau; id tăng nên ID lớn hơn nằm sau nếu hai khóa trước bằng nhau. Bộ lọc category/tenant **phải giữ nguyên** giữa các trang. Nếu price có thể NULL, điều kiện cần thêm quy tắc null rank và không còn đúng nguyên xi.

### Bài tập C — Hai trang bị trùng dù có id ASC

Collection đang có thứ tự:

~~~text
[o-09, o-08, o-07, o-06]
~~~

Client gọi trang 1 với limit=2, offset=0 và nhận **o-09, o-08**. Sau đó, đơn mới **o-10** được thêm vào đầu danh sách. Client gọi offset=2.

**Câu hỏi:** trang 2 trả gì? id ASC làm khóa phụ có ngăn lỗi không? Nếu chuyển sang cursor thì khác gì?

**Lời giải:** tập mới là **[o-10, o-09, o-08, o-07, o-06]**, nên offset=2 trả **o-08, o-07**; o-08 bị lặp. Khóa phụ id chỉ làm thứ tự xác định trên **mỗi tập tại thời điểm truy vấn**, không giữ snapshot giữa hai request. Với cursor lưu bộ khóa của **o-08** và các sort key không thay đổi, trang kế tiếp dùng điều kiện “sau o-08”, thường trả **o-07, o-06**, không bị ảnh hưởng bởi o-10 mới ở đầu.

### Bài tập D — NULLS LAST và cursor

Một API xếp **lastLoginAt DESC NULLS LAST, id ASC**, và trang đầu kết thúc tại **user-15** có lastLoginAt NULL. Một user **user-16** cũng có lastLoginAt NULL.

**Câu hỏi:** trang sau có được dùng **lastLoginAt < NULL** không? Điều kiện đúng là gì?

**Lời giải:** phép so sánh với NULL thông thường không trả TRUE, nên **lastLoginAt < NULL** không tìm đúng các hàng. Khi cursor đã ở nhóm NULL, chỉ chọn các hàng **lastLoginAt IS NULL AND id > :lastId**; vì vậy user-16 nằm sau user-15 theo id ASC. Nếu cursor chưa ở nhóm NULL, phải xét cả **những ngày cũ hơn, các hàng NULL và tie-break ID**.

### Bài tập E — API nhiều tenant và whitelist

Ứng dụng quản trị cho phép người dùng chọn:

~~~text
GET /v1/employees?sort=-performanceScore,salary
~~~

Employee API trả id, displayName, department và status, nhưng không trả salary/performanceScore cho nhân viên thường. Một developer đề xuất chỉ bỏ hai trường này khỏi JSON rồi vẫn cho sort.

**Câu hỏi:** có bảo mật không? Thiết kế chính sách nào phù hợp?

**Lời giải:** vẫn có thể lộ **thứ tự tương đối theo salary/performanceScore** dù field không có trong body. Cần whitelist sort theo quyền truy cập, ví dụ nhân viên thường chỉ sort theo displayName/department/createdAt; nhà quản lý được phân quyền có thể xem và sort theo trường nhạy cảm trong phạm vi cho phép. Đồng thời lọc nhân viên theo tenant và ACL **trước khi sort/paginate**, giới hạn limit/offset và ngăn cursor dùng lại giữa principal khác.

### Bài tập F — Chọn pagination theo yêu cầu nghiệp vụ

Một API hiển thị bảng giao dịch realtime, còn một job cuối ngày xuất **toàn bộ giao dịch đúng một lần** để đối soát.

**Câu hỏi:** có nên dùng một endpoint GET với offset cho cả hai?

**Lời giải:** bảng UI có thể dùng **cursor theo khóa bất biến** hoặc offset nếu chấp nhận thay đổi vị trí; kết quả đọc theo nhiều thời điểm không cần là một snapshot duy nhất. Job đối soát nên tạo **snapshot/export job** theo một mốc dữ liệu rõ, có ID, trạng thái, kiểm tra đầy đủ số bản ghi và checksum khi cần. **Keyset pagination không tự bảo đảm snapshot tuyệt đối**, nhất là khi các khóa sort bị sửa hoặc có dữ liệu nhập trễ.

## 16. Các phản mẫu và cách sửa

| Phản mẫu | Tác động | Cách sửa |
|---|---|---|
| GET collection không có ORDER BY nhưng UI luôn giả định dữ liệu “mới nhất” | Thứ tự phụ thuộc kế hoạch truy vấn | Công bố sort mặc định và thực hiện ORDER BY |
| ORDER BY created_at DESC dù nhiều hàng cùng thời điểm | Thứ tự giữa hàng hòa khóa không được đảm bảo | Thêm khóa duy nhất như id ASC |
| Server bỏ qua field sort sai và trả 200 | Client không nhận ra lỗi | 400 với INVALID_SORT |
| Nhận raw tên field/biểu thức SQL từ query | Truy vấn khó kiểm soát, có thể lộ schema hoặc tạo lỗ hổng khi ghép SQL | Whitelist và mapping field công khai |
| Cho sort theo mọi thuộc tính entity | Lộ thứ tự theo dữ liệu nhạy cảm, query đắt | Whitelist theo collection/vai trò |
| Dùng string để sort số tiền | "100" có thể đứng trước "20" | Kiểu decimal/numeric đúng |
| Bỏ qua collation và NULL | Thứ tự khác nhau giữa môi trường | Công bố quy tắc; test DB production-like |
| Sort trong Java **sau LIMIT** | Không chọn đúng top N của toàn tập | ORDER BY ở DB trước LIMIT |
| OFFSET sâu không giới hạn | Query chậm, tải DB tăng | Giới hạn độ sâu hoặc dùng keyset |
| Nghĩ thêm id cuối làm offset chịu được mọi insert/delete | Trùng/thiếu giữa các trang khi tập thay đổi | Cursor hoặc snapshot tùy yêu cầu |
| Dùng cùng predicate cursor cho ASC và DESC | Bỏ sót/trùng hàng | Tạo điều kiện “sau cursor” theo từng chiều |
| Dùng phép lớn hơn/nhỏ hơn với NULL trong cursor | Không lấy đúng nhóm NULL | Null rank hoặc nhánh NULL riêng |
| Cursor chỉ mã hóa base64, không xác minh scope/chữ ký | Người dùng chỉnh bộ khóa hoặc truy xuất chéo tenant | Ký/mã hóa phù hợp, kiểm tra filter/sort/scope/expiry |
| Cursor dùng lại khi bộ lọc đổi | Chuyển trang sai tập kết quả | Ràng buộc cursor với filter và policy |
| Lọc quyền sau khi đã LIMIT | Trang thiếu dữ liệu, lộ số lượng ngoài scope | WHERE tenant/ACL trước ORDER BY/LIMIT |
| JOIN one-to-many rồi LIMIT trên dòng join | Một resource xuất hiện nhiều lần, trang bị méo | Phân trang ID của resource gốc |
| Tạo index cho mọi hoán vị sort | Tốn storage/ghi, khó vận hành | Chọn bộ sort phổ biến, đo bằng EXPLAIN |
| Hứa cursor không bao giờ trùng/thiếu khi dữ liệu biến động | Hợp đồng quá mức thực tế | Nêu giới hạn keyset; snapshot khi cần |
| CDN dùng cùng cache key cho mọi sort/tenant | Trả sai thứ tự hoặc lộ dữ liệu | Cache key đầy đủ, no-store với dữ liệu riêng tư |

## 17. Checklist trước khi công bố API

- [ ] Đã xác định **sort mặc định** khi client không gửi tham số.
- [ ] Cú pháp nhiều trường và ý nghĩa ASC/DESC được ghi trong tài liệu.
- [ ] Có **khóa phá hòa duy nhất, ổn định** ở cuối mọi ORDER BY dùng để phân trang.
- [ ] Whitelist trường, số khóa tối đa, chiều được hỗ trợ và lỗi **400** cho sort sai.
- [ ] Không cho client điều khiển SQL expression, property path hoặc field nhạy cảm tùy ý.
- [ ] Đã công bố cách sắp **NULL, chuỗi, collation, enum, số tiền và thời gian** khi chúng là sort key.
- [ ] Filter/tenant/ACL được áp trước ORDER BY và LIMIT, trên cả query count nếu có.
- [ ] Offset pagination được dùng với hiểu biết về **trùng/thiếu khi tập dữ liệu thay đổi**.
- [ ] Nếu dùng keyset, điều kiện tiếp tục khớp **tất cả khóa và chiều** của ORDER BY.
- [ ] Cursor có version, hạn dùng, bảo vệ toàn vẹn và ràng buộc với **sort/filter/principal hoặc scope**.
- [ ] Cursor có thể chứa giá trị sort nhạy cảm đã được xử lý theo chính sách bảo mật; không coi chữ ký là mã hóa.
- [ ] Nếu nghiệp vụ yêu cầu snapshot cố định, đã thiết kế **snapshot/export/watermark** thay vì chỉ dựa vào cursor.
- [ ] Có limit/page/offset tối đa; index đã được đo với truy vấn và tải đại diện.
- [ ] JOIN/aggregation không nhân đôi một resource trong collection phân trang.
- [ ] Response trả mã **200 với items rỗng** cho collection hợp lệ nhưng không có kết quả.
- [ ] Có OpenAPI cho filter/sort/pagination, schema lỗi và cách dùng nextCursor.
- [ ] Có test tie-breaker, NULL/collation, nhiều trang, cursor bị sửa hoặc đổi scope, phân quyền và cache.
- [ ] Quan sát p95/p99, index usage, số query tốn tài nguyên, rate limit và tỷ lệ invalid sort/cursor.

### Tài liệu tiêu chuẩn tham khảo

- **RFC 9110 — HTTP Semantics:** ngữ nghĩa GET và mã trạng thái HTTP. [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)
- **RFC 3986 — Uniform Resource Identifier:** cấu trúc URI/query component; cú pháp sort ở bài là **quy ước của API**. [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986)
- **RFC 9457 — Problem Details for HTTP APIs:** body lỗi nhất quán theo **application/problem+json**. [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
- **OpenAPI Specification 3.1:** mô tả query parameter, schema, security và các response. [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0)
- **Tài liệu SQL và Spring Data của hệ thống đang triển khai:** kiểm tra semantics **NULL, collation, index, pageable, slice và cursor** theo database, driver và phiên bản cụ thể.

**Điểm cần ghi nhớ:** thứ tự ổn định của một REST collection đòi hỏi **ORDER BY đầy đủ và khóa phá hòa duy nhất**, chứ không chỉ ghi một trường sort trong URL. Khi dữ liệu thay đổi giữa các request, **deterministic sorting** và **pagination consistency** là hai bài toán riêng: offset, cursor và snapshot phục vụ những nhu cầu khác nhau. Hợp đồng tốt làm rõ cả hai, rồi bảo vệ chúng bằng whitelist, phân quyền, index, cache policy và kiểm thử.
