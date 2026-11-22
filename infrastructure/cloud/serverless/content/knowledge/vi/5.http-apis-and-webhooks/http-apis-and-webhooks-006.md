# Thiết kế phân trang, lọc dữ liệu và phiên bản API

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Thiết kế endpoint HTTP trả về tập dữ liệu lớn theo từng phần.
- Chọn offset hoặc cursor/keyset pagination dựa trên dữ liệu và cách client duyệt.
- Xây dựng filter và sort an toàn, dễ hiểu, có giới hạn.
- Thiết kế phiên bản API và thay đổi contract có kiểm soát.
- Áp dụng các nguyên tắc này cho Java function được kích hoạt bởi HTTP trong môi trường serverless.

## 1. Vì sao API danh sách cần phân trang?

Giả sử ứng dụng quản lý đơn hàng có endpoint:

~~~http
GET /orders
~~~

Khi hệ thống chỉ có vài chục đơn hàng, trả toàn bộ danh sách có thể vẫn hoạt động. Khi số lượng tăng lên hàng triệu, cách làm đó gây ra nhiều vấn đề:

- Response lớn làm tăng thời gian truyền, bộ nhớ và chi phí xử lý.
- Function phải đọc và serialize nhiều bản ghi dù client chỉ hiển thị một phần.
- Truy vấn nặng chiếm connection database lâu hơn và ảnh hưởng request khác.
- Client khó tìm đúng dữ liệu nếu không thể lọc theo trạng thái, thời gian hoặc khách hàng.
- Thay đổi cấu trúc response có thể phá vỡ các client đang sử dụng API.

Một API danh sách thường cần ba khả năng đi cùng nhau:

1. **Phân trang (pagination):** chia kết quả thành các phần nhỏ và cho phép lấy tiếp.
2. **Lọc và sắp xếp (filtering and sorting):** xác định tập dữ liệu và thứ tự trả về.
3. **Quản lý phiên bản (API versioning):** thay đổi hợp đồng mà vẫn kiểm soát ảnh hưởng đến client hiện tại.

Trong serverless, các yêu cầu này liên quan đến thời gian thực thi, concurrency và chi phí. Mỗi HTTP request có thể kích hoạt một Java function mới. Request tải quá nhiều bản ghi tiêu thụ bộ nhớ, kéo dài invocation và làm tăng tải database.

Ví dụ xuyên suốt bài là API quản lý đơn hàng. Client cần xem danh sách, lọc theo trạng thái hoặc thời gian tạo, sắp xếp theo ngày và chuyển sang phần kết quả tiếp theo.

## 2. Thiết kế hợp đồng endpoint danh sách

Một endpoint có thể bắt đầu bằng contract:

~~~http
GET /v1/orders?limit=25&status=PAID&sort=-createdAt
Accept: application/json
~~~

Ý nghĩa:

- `/v1/orders`: danh sách đơn hàng thuộc phiên bản API 1.
- `limit=25`: yêu cầu tối đa 25 phần tử.
- `status=PAID`: chỉ lấy đơn đã thanh toán.
- `sort=-createdAt`: sắp xếp ngày tạo giảm dần.
- `Accept`: định dạng response client có thể xử lý.

Một request có thêm khoảng thời gian:

~~~http
GET /v1/orders?limit=25&status=PAID&createdAfter=2026-01-01T00%3A00%3A00Z&createdBefore=2026-02-01T00%3A00%3A00Z&sort=-createdAt,id
~~~

Tên tham số là một phần của public contract. Hãy dùng tên nhất quán, mô tả rõ kiểu dữ liệu, giá trị mặc định, giới hạn và cách kết hợp điều kiện. Tránh để client phải đoán `size` có phải số bản ghi, `page` bắt đầu từ 0 hay 1, hoặc `date` là ngày địa phương hay thời điểm UTC.

### 2.1. Các tham số phân trang

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| `limit` | Số bản ghi tối đa trong một trang | `limit=25` |
| `offset` | Số bản ghi bỏ qua trước khi lấy kết quả | `offset=50` |
| `cursor` | Token để tiếp tục từ vị trí đã đọc | `cursor=eyJ...` |
| `page` | Số thứ tự trang theo quy ước API | `page=3` |
| `pageSize` | Số phần tử mong muốn trong một trang | `pageSize=25` |

Không nhất thiết hỗ trợ tất cả các tham số. Một contract nên chọn một kiểu phân trang chính để client không vô tình gửi cả `offset` lẫn `cursor` với ý nghĩa xung đột.

Đặt `limit` mặc định hợp lý và một mức tối đa phía server, ví dụ mặc định 20 và tối đa 100. Giá trị cụ thể cần dựa trên kích thước bản ghi, hiệu năng database và giới hạn nền tảng. Server phải kiểm tra và giới hạn giá trị client gửi; không để `limit=1000000` tạo ra truy vấn không kiểm soát.

### 2.2. Hợp đồng response

Một response phân trang có thể có cấu trúc:

~~~json
{
  "data": [
    {
      "id": "ord_1024",
      "status": "PAID",
      "total": 125000,
      "createdAt": "2026-01-15T10:20:30Z"
    }
  ],
  "page": {
    "limit": 25,
    "nextCursor": "eyJ2IjoxLCJrZXkiOi...",
    "hasMore": true
  },
  "links": {
    "next": "/v1/orders?limit=25&cursor=eyJ2IjoxLCJrZXkiOi..."
  }
}
~~~

`data` chứa các bản ghi của trang hiện tại. `page` mô tả cách tiếp tục. `links.next` là URL tương đối hoặc tuyệt đối mà client có thể gọi tiếp. Với trang cuối, `nextCursor` và `next` có thể là `null`, còn `hasMore` là `false`.

Không bắt buộc phải trả cả `nextCursor` lẫn `links.next`; hãy chọn contract nhất quán. Nếu cung cấp link, server nên tạo URL từ các tham số đã chuẩn hóa và giữ lại filter/sort có hiệu lực để trang kế tiếp vẫn truy vấn cùng tập kết quả.

Một số API trả thêm `totalItems` hoặc `totalPages`. Đây là thông tin hữu ích cho giao diện kiểu “trang 2 trên 14”, nhưng việc đếm chính xác có thể tốn kém trên tập dữ liệu lớn. Chỉ cung cấp khi có nhu cầu thực tế và có thể đáp ứng chi phí truy vấn. Với cursor pagination, `hasMore` thường đủ cho nút “Tải thêm”.

## 3. Phân trang offset

Offset pagination dùng vị trí bắt đầu và số lượng bản ghi cần lấy. Ví dụ:

~~~http
GET /v1/orders?limit=20&offset=40
~~~

Server có thể thực hiện truy vấn tương đương:

~~~sql
SELECT id, status, total, created_at
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT :limit
OFFSET :offset;
~~~

Request này bỏ qua 40 bản ghi đầu rồi trả tối đa 20 bản ghi tiếp theo.

### 3.1. Ưu điểm và giới hạn

Offset dễ hiểu và dễ triển khai. Client có thể nhảy đến một vị trí bất kỳ, tính trang từ số trang và hiển thị tổng số trang nếu server cung cấp tổng số bản ghi. Nó phù hợp với tập dữ liệu vừa phải, bảng quản trị nội bộ hoặc màn hình cần điều hướng trực tiếp đến trang cụ thể.

Tuy nhiên, vị trí offset có thể thay đổi khi dữ liệu được thêm hoặc xóa. Giả sử client đã đọc trang đầu, sau đó có 3 đơn hàng mới được chèn vào đầu danh sách theo thứ tự ngày tạo giảm dần. Khi client gọi trang kế tiếp bằng `offset=20`, một số bản ghi có thể xuất hiện lại vì vị trí của chúng đã dịch chuyển. Nếu một bản ghi bị xóa trước vị trí offset, client có thể bỏ qua một bản ghi chưa đọc.

Offset sâu cũng có thể đắt. Database có thể phải duyệt và bỏ qua nhiều dòng trước khi trả phần dữ liệu cần thiết. `OFFSET 500000 LIMIT 20` thường tốn hơn nhiều so với lấy 20 bản ghi đầu tiên, đặc biệt khi truy vấn không có index phù hợp.

Nếu chọn offset:

- Luôn dùng `ORDER BY` rõ ràng và có khóa phụ duy nhất để kết quả ổn định.
- Giới hạn `limit` và `offset`; từ chối giá trị âm hoặc vượt giới hạn công bố.
- Tạo index phù hợp với điều kiện lọc và thứ tự sắp xếp thường dùng.
- Xác định cách xử lý dữ liệu thay đổi giữa hai request và mô tả trong tài liệu API.
- Tránh hứa hẹn rằng các trang tạo thành snapshot bất biến nếu hệ thống không thực sự giữ snapshot đó.

Ví dụ `ORDER BY created_at DESC, id DESC` ổn định hơn `ORDER BY created_at DESC` vì nhiều bản ghi có thể cùng thời điểm tạo. `id` đóng vai trò tie-breaker để xác định thứ tự giữa các bản ghi có cùng `created_at`.

Nếu nghiệp vụ yêu cầu người dùng xuất một tập dữ liệu nhất quán tại một thời điểm, phân trang offset thông thường chưa đủ. Cần cân nhắc snapshot, transaction isolation phù hợp, bản xuất bất đồng bộ hoặc một mốc dữ liệu cố định.

## 4. Phân trang cursor và keyset

Cursor pagination dùng một token để chỉ ra vị trí tiếp tục. Client không cần tính offset. Ví dụ:

~~~http
GET /v1/orders?limit=20&cursor=eyJ2IjoxLCJjcmVhdGVkQXQiOi...
~~~

Giả sử thứ tự là `created_at DESC, id DESC`. Sau khi trả trang đầu, server tạo cursor dựa trên cặp giá trị của bản ghi cuối cùng. Trang sau truy vấn các bản ghi nằm sau điểm neo đó:

~~~sql
SELECT id, status, total, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Cú pháp so sánh tuple có thể khác giữa các hệ quản trị cơ sở dữ liệu. Có thể viết tương đương bằng điều kiện `created_at < :last_created_at OR (created_at = :last_created_at AND id < :last_id)`.

Server lấy `limit + 1` bản ghi để biết có còn dữ liệu hay không. Nếu có nhiều hơn `limit`, server trả `limit` bản ghi đầu và tạo cursor từ bản ghi cuối cùng đã trả. Cách này tránh phải chạy truy vấn đếm riêng chỉ để biết có trang kế tiếp.

### 4.1. Vì sao cursor ổn định hơn?

Cursor dựa vào giá trị sắp xếp của bản ghi cuối cùng, nên các bản ghi mới được thêm trước điểm neo thường không làm dịch chuyển vị trí tiếp tục như offset. Truy vấn keyset cũng có thể tận dụng index để tìm từ điểm neo thay vì bỏ qua một số lượng lớn bản ghi.

Tuy vậy, cursor không tự tạo snapshot. Nếu bản ghi bị xóa, thay đổi field sắp xếp hoặc thay đổi trạng thái khiến nó không còn thỏa filter, tập kết quả giữa các request vẫn có thể thay đổi. Nếu cần snapshot tuyệt đối, phải thiết kế thêm mốc dữ liệu hoặc cơ chế snapshot.

Cursor pagination phù hợp với feed, lịch sử giao dịch, danh sách hoạt động và tập dữ liệu lớn được duyệt tuần tự. Nó kém thuận tiện khi client cần nhảy thẳng đến trang 50 hoặc yêu cầu số trang chính xác.

### 4.2. Cursor nên là token opaque

Client chỉ nên xem cursor là chuỗi để gửi lại cho server, không cần đọc hoặc tự tạo nội dung bên trong. Token có thể mã hóa Base64 URL-safe một payload chứa:

- Phiên bản định dạng cursor.
- Giá trị sắp xếp của bản ghi cuối trang.
- Thứ tự sắp xếp và các filter liên quan.
- Mốc dữ liệu hoặc thời gian hết hạn nếu cần.
- Thông tin ràng buộc với tenant hoặc phạm vi truy vấn.

Base64 chỉ là encoding, không phải mã hóa bảo mật. Nếu payload chứa dữ liệu nhạy cảm, hãy mã hóa bằng cơ chế phù hợp. Để chống sửa cursor, có thể ký payload bằng HMAC hoặc chữ ký số. Server xác minh chữ ký trước khi dùng dữ liệu cursor trong truy vấn.

Không tin `tenantId`, quyền truy cập hay điều kiện bảo mật chỉ vì chúng nằm trong cursor. Server vẫn phải lấy danh tính từ context xác thực của request và áp dụng authorization ở mọi trang. Cursor cần được ràng buộc với phạm vi người dùng/tenant hiện tại để không thể dùng token của tenant khác.

Nếu cursor không hợp lệ, sai phiên bản hoặc không khớp filter/sort hiện tại, trả lỗi client rõ ràng, thường là `400 Bad Request`. Nếu token hết hạn theo chính sách, thông báo rằng client cần bắt đầu lại từ trang đầu. Không đưa SQL, tên index hoặc thông tin nội bộ vào nội dung lỗi.

### 4.3. Chọn offset hay cursor?

| Tiêu chí | Offset | Cursor/keyset |
|---|---|---|
| Dễ triển khai và giải thích | Cao | Cần thiết kế token và điểm neo |
| Nhảy đến trang bất kỳ | Thuận tiện | Không thuận tiện |
| Tập dữ liệu rất lớn | Offset sâu có thể chậm | Thường hiệu quả hơn nếu có index |
| Dữ liệu thay đổi liên tục | Có thể lặp hoặc bỏ sót giữa các trang | Ít bị dịch chuyển do bản ghi mới ở trước điểm neo |
| Tổng số trang | Có thể kết hợp `COUNT` | Thường không cung cấp tổng trang |
| Duyệt tuần tự | Tốt | Rất phù hợp |
| Feed hoặc lịch sử giao dịch | Có thể dùng ở quy mô nhỏ | Thường là lựa chọn tốt |

Không có quy tắc bắt buộc rằng mọi API phải dùng cursor. Chọn theo cách client duyệt dữ liệu và đặc tính truy vấn thực tế. Một hệ thống có thể dùng offset cho bảng quản trị nhỏ và cursor cho feed lớn, miễn là mỗi endpoint công bố contract rõ ràng.

## 5. Lọc dữ liệu có kiểm soát

Filter cho phép client thu hẹp tập kết quả. Ví dụ:

~~~http
GET /v1/orders?status=PAID&customerId=cus_42&createdAfter=2026-01-01T00%3A00%3A00Z
~~~

Server chỉ trả các đơn hàng đáp ứng điều kiện được định nghĩa. Hãy công bố rõ filter nào được hỗ trợ, kiểu dữ liệu, phép so sánh và cách kết hợp nhiều điều kiện.

### 5.1. Thiết kế tên và ngữ nghĩa filter

| Tham số | Kiểu | Ý nghĩa |
|---|---|---|
| `status` | Enum hoặc giá trị lặp | Trạng thái đơn hàng |
| `customerId` | Chuỗi định danh | Đơn hàng của khách hàng |
| `createdAfter` | ISO 8601 timestamp | Tạo sau thời điểm này |
| `createdBefore` | ISO 8601 timestamp | Tạo trước thời điểm này |
| `minTotal` | Số thập phân | Tổng tiền tối thiểu |
| `maxTotal` | Số thập phân | Tổng tiền tối đa |
| `q` | Chuỗi | Tìm kiếm theo quy tắc được công bố |

Cần định nghĩa rõ biên thời gian. Ví dụ, `createdAfter` có thể là điều kiện `created_at >= value`, còn `createdBefore` là `created_at < value`. Dùng khoảng nửa mở `[from, to)` giúp hai khoảng liên tiếp không bị chồng lấn. Hãy ghi rõ quy tắc này trong tài liệu.

Timestamp nên dùng định dạng có múi giờ, thường là ISO 8601 với `Z` cho UTC hoặc offset tường minh. Không âm thầm diễn giải `2026-01-01T09:00:00` như UTC nếu chuỗi không có timezone.

Nếu cho phép nhiều giá trị của cùng một filter, hãy chọn quy ước rõ ràng:

~~~http
GET /v1/orders?status=PAID&status=SHIPPED
~~~

Ở đây, hai giá trị `status` có thể được hiểu là OR trong cùng một trường, còn các trường khác kết hợp bằng AND. Ví dụ: `(status = PAID OR status = SHIPPED) AND customerId = cus_42`. Một API khác có thể chọn cú pháp `status=PAID,SHIPPED`; điều quan trọng là phải tài liệu hóa và parse nhất quán.

### 5.2. Chỉ cho phép filter được hỗ trợ

Không lấy tên field tùy ý từ query string rồi ghép thẳng vào SQL. Ví dụ sau rất nguy hiểm:

~~~java
String sql = "SELECT * FROM orders WHERE " + request.getParameter("field")
        + " = ?";
~~~

Giá trị bind parameter bảo vệ phần value, nhưng không bảo vệ tên cột hoặc biểu thức SQL được nối từ đầu vào. Kẻ gọi có thể truyền tên cột, toán tử hoặc biểu thức không mong muốn.

Thay vào đó, dùng allowlist cho field và operator:

~~~java
enum OrderFilterField {
    STATUS,
    CUSTOMER_ID,
    CREATED_AT,
    TOTAL
}
~~~

Sau khi parse, chuyển từng field hợp lệ thành predicate được xây dựng từ code đã kiểm soát. Luôn dùng prepared statement hoặc API query parameterized cho giá trị. Nếu hỗ trợ sort động, tên cột và hướng sort cũng phải đi qua allowlist riêng.

### 5.3. Xác thực filter

Server nên kiểm tra:

- Giá trị enum có thuộc tập được hỗ trợ không.
- `minTotal` có nhỏ hơn hoặc bằng `maxTotal` không.
- `createdAfter` có đứng trước `createdBefore` không.
- Chuỗi tìm kiếm có vượt giới hạn độ dài không.
- Số lượng filter, số giá trị lặp và độ phức tạp truy vấn có trong giới hạn không.
- Filter có phù hợp với quyền truy cập của người gọi không.

Nếu query không hợp lệ, trả `400 Bad Request` kèm chi tiết field nào sai và giá trị nào được chấp nhận. Không tự bỏ qua filter sai vì client có thể tưởng dữ liệu đã được lọc đúng trong khi server trả nhiều bản ghi hơn mong đợi.

### 5.4. Bảo mật và phạm vi dữ liệu

Filter không thay thế authorization. Một client có thể gửi `customerId` của người khác; server phải xác định caller có quyền đọc dữ liệu đó hay không. Với hệ thống multi-tenant, điều kiện tenant cần được áp dụng từ authentication context ở server, không phụ thuộc query parameter do client gửi.

Tương tự, phân trang không phải ranh giới bảo mật. Server phải áp dụng quyền truy cập trước khi tính trang, đếm bản ghi hoặc tạo cursor. Nếu đếm tổng trước khi lọc theo quyền, API có thể làm lộ số lượng bản ghi của tenant khác.

Các filter tìm kiếm tự do cũng cần giới hạn độ tốn kém. Full-text search, wildcard đầu chuỗi, regex tùy ý hoặc join nhiều bảng có thể gây tải lớn. Hãy công bố kiểu tìm kiếm được hỗ trợ và đặt timeout, giới hạn độ dài, rate limit hoặc cơ chế tìm kiếm chuyên dụng khi cần.

## 6. Sắp xếp ổn định và tương thích với phân trang

Filter quyết định bản ghi nào được chọn; sort quyết định thứ tự trả về. Hai phần này liên quan trực tiếp đến pagination. Một cursor chỉ có ý nghĩa khi server biết chính xác thứ tự mà nó đang tiếp tục.

### 6.1. Chỉ cho phép trường sắp xếp đã công bố

Ví dụ:

~~~http
GET /v1/orders?sort=-createdAt,id
~~~

Quy ước trong ví dụ:

- Dấu `-` trước field nghĩa là giảm dần.
- Field không có dấu `-` nghĩa là tăng dần.
- Nhiều field được phân tách bằng dấu phẩy.
- Server chỉ chấp nhận field đã công bố, ví dụ `createdAt`, `total` và `id`.

Không nối trực tiếp chuỗi sort từ client vào SQL. Dùng allowlist ánh xạ tên API sang cột database:

| Tên API | Cột nội bộ | Có cho phép sort? |
|---|---|---|
| `createdAt` | `created_at` | Có |
| `total` | `total_amount` | Có |
| `id` | `id` | Có |
| `customerEmail` | `customer_email` | Không, nếu chưa được công bố |

Tên cột nội bộ có thể khác tên field public. Việc ánh xạ qua enum hoặc cấu hình cố định tránh SQL injection và giúp API không vô tình công khai cấu trúc database.

### 6.2. Thứ tự phải xác định duy nhất

Một truy vấn chỉ sắp xếp theo `created_at DESC` có thể trả các bản ghi cùng timestamp theo thứ tự không xác định. Khi phân trang, một bản ghi có thể bị lặp hoặc bỏ qua nếu database chọn thứ tự khác giữa hai lần chạy.

Thêm khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Nếu client yêu cầu `sort=-createdAt`, server có thể tự bổ sung `id DESC` vào cuối thứ tự nội bộ. Cần mô tả rằng tie-breaker này được áp dụng để đảm bảo thứ tự ổn định.

Cursor phải chứa đủ giá trị của toàn bộ sort key. Nếu sort theo `created_at DESC, id DESC`, cursor chỉ lưu `created_at` là chưa đủ; nó cần cả `id` để xác định điểm tiếp tục khi nhiều bản ghi có cùng timestamp.

### 6.3. Null và index

Nếu field cho phép `NULL`, hãy định nghĩa null đứng trước hay sau khi sort tăng/giảm. Hành vi mặc định của database có thể khác nhau. Nếu cursor dựa trên field nullable, biểu thức so sánh phải xử lý null rõ ràng; trong một số trường hợp nên chọn sort key không nullable.

Index nên phù hợp với truy vấn phổ biến. Ví dụ truy vấn theo tenant, trạng thái và ngày tạo có thể cần index kết hợp như `(tenant_id, status, created_at, id)`. Không tạo index cho mọi tổ hợp filter có thể có; điều đó làm tăng chi phí ghi và lưu trữ. Hãy dựa vào query plan và số liệu thực tế để chọn.

Nếu cho phép nhiều tổ hợp sort/filter, giới hạn số tổ hợp được hỗ trợ hoặc xác định query pattern quan trọng. Một API linh hoạt quá mức có thể khiến database không có index phù hợp cho request phổ biến.

## 7. Ví dụ triển khai trong Java

Trong serverless, HTTP adapter nhận request từ API Gateway, HTTP trigger hoặc nền tảng tương đương. Adapter đọc query parameter, xác thực đầu vào, gọi service và chuyển kết quả thành HTTP response. Logic phân trang nên nằm trong lớp service/repository để có thể kiểm thử độc lập với nhà cung cấp cloud.

### 7.1. Kiểu dữ liệu của request và response

Đoạn code sau minh họa các kiểu dữ liệu Java cho cursor pagination. Đây là ví dụ khung, cần bổ sung parser, serializer và adapter theo framework hoặc nền tảng đang dùng.

~~~java
import java.time.Instant;
import java.util.List;

public record OrderFilter(
    String status,
    String customerId,
    Instant createdAfter,
    Instant createdBefore
) {}

public enum OrderSortField {
    CREATED_AT,
    TOTAL,
    ID
}

public enum SortDirection {
    ASC,
    DESC
}

public record SortTerm(
    OrderSortField field,
    SortDirection direction
) {}

public record CursorPageRequest(
    int limit,
    String cursor,
    List<SortTerm> sort
) {}

public record PageMetadata(
    int limit,
    String nextCursor,
    boolean hasMore
) {}

public record PageResponse<T>(
    List<T> data,
    PageMetadata page
) {}
~~~

Dùng enum cho sort field và direction giúp lớp truy vấn làm việc với giá trị đã được kiểm tra. Query parameter chỉ được chuyển thành enum sau khi đối chiếu allowlist. Không để tên cột tùy ý đi xuyên suốt từ HTTP request đến repository.

### 7.2. Service điều phối truy vấn

Ví dụ service:

~~~java
public final class OrderQueryService {
    private static final int DEFAULT_LIMIT = 20;
    private static final int MAX_LIMIT = 100;

    private final OrderRepository repository;
    private final CursorCodec cursorCodec;

    public OrderQueryService(
            OrderRepository repository,
            CursorCodec cursorCodec) {
        this.repository = repository;
        this.cursorCodec = cursorCodec;
    }

    public PageResponse<OrderView> search(
            OrderFilter filter,
            Integer requestedLimit,
            String cursorToken,
            List<SortTerm> requestedSort,
            RequestIdentity identity) {

        int limit = requestedLimit == null
                ? DEFAULT_LIMIT
                : requestedLimit;

        if (limit < 1 || limit > MAX_LIMIT) {
            throw new InvalidQueryException(
                    "limit must be between 1 and " + MAX_LIMIT);
        }

        validateFilter(filter);
        List<SortTerm> sort = normalizeSort(requestedSort);

        CursorPosition position = cursorToken == null
                ? null
                : cursorCodec.decodeAndVerify(
                        cursorToken, filter, sort, identity);

        List<OrderView> rows = repository.findPage(
                identity.tenantId(),
                filter,
                sort,
                position,
                limit + 1);

        boolean hasMore = rows.size() > limit;
        List<OrderView> data = hasMore
                ? rows.subList(0, limit)
                : rows;

        String nextCursor = null;
        if (hasMore && !data.isEmpty()) {
            OrderView last = data.get(data.size() - 1);
            nextCursor = cursorCodec.encode(
                    last, filter, sort, identity);
        }

        return new PageResponse<>(
                data,
                new PageMetadata(limit, nextCursor, hasMore));
    }

    private void validateFilter(OrderFilter filter) {
        if (filter.createdAfter() != null
                && filter.createdBefore() != null
                && !filter.createdAfter().isBefore(filter.createdBefore())) {
            throw new InvalidQueryException(
                    "createdAfter must be earlier than createdBefore");
        }
    }

    private List<SortTerm> normalizeSort(List<SortTerm> requested) {
        // Parse allowlist, áp dụng sort mặc định và thêm ID làm tie-breaker.
        return OrderSortPolicy.normalize(requested);
    }
}
~~~

Các kiểu `OrderRepository`, `CursorCodec`, `CursorPosition`, `OrderView`, `RequestIdentity`, `InvalidQueryException` và `OrderSortPolicy` là thành phần minh họa. Trong triển khai thật:

- `CursorCodec` phải xác minh chữ ký, version, filter/sort binding và phạm vi identity trước khi giải mã vị trí.
- `RequestIdentity` lấy tenant và người dùng từ authentication context đã xác minh.
- `OrderRepository` phải thêm điều kiện tenant và quyền truy cập vào truy vấn.
- `findPage` phải dùng parameterized query và thứ tự ổn định.
- `OrderSortPolicy` chỉ ánh xạ enum sang cột đã được cho phép.
- Repository chỉ lấy `limit + 1` bản ghi để xác định `hasMore`, không tải toàn bộ tập kết quả.

Một chi tiết quan trọng: `rows.subList(0, limit)` trong ví dụ chỉ an toàn sau khi đã xác nhận `rows.size() > limit`. Khi repository trả ít hơn hoặc bằng limit, service sử dụng toàn bộ danh sách. Với dữ liệu lớn, repository nên trả một collection có kích thước giới hạn; không materialize toàn bộ kết quả rồi mới cắt trang.

### 7.3. HTTP adapter và mã trạng thái

Adapter có thể chuyển request thành service call và trả `200 OK` với `PageResponse`. Một số lỗi thường gặp:

| Tình huống | HTTP status | Cách phản hồi |
|---|---:|---|
| Query hợp lệ, có hoặc không có dữ liệu | `200 OK` | Trả `data` và metadata phân trang |
| Tham số sai, cursor hỏng, sort không hỗ trợ | `400 Bad Request` | Nêu tham số và quy tắc hợp lệ |
| Chưa xác thực | `401 Unauthorized` | Yêu cầu xác thực |
| Đã xác thực nhưng không có quyền | `403 Forbidden` | Không tiết lộ dữ liệu bị cấm |
| Tài nguyên cụ thể không tồn tại | `404 Not Found` | Dùng cho endpoint tài nguyên đơn |
| Vượt rate limit | `429 Too Many Requests` | Có thể kèm `Retry-After` |
| Dịch vụ phụ thuộc tạm thời không sẵn sàng | `503 Service Unavailable` | Có thể kèm hướng dẫn retry |

Danh sách rỗng thường là response thành công với `data: []`, không phải `404`. `404` phù hợp khi tài nguyên được yêu cầu không tồn tại hoặc không thể được tiết lộ cho caller theo chính sách bảo mật.

Đối với lỗi validation, có thể dùng định dạng `application/problem+json` theo Problem Details của HTTP. Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/invalid-query",
  "title": "Invalid query parameter",
  "status": 400,
  "detail": "The requested sort field is not supported.",
  "errors": [
    {
      "field": "sort",
      "message": "Allowed fields: createdAt, total, id."
    }
  ]
}
~~~

Không trả stack trace, SQL, tên bảng hoặc dữ liệu nội bộ trong lỗi gửi cho client. Ghi chi tiết kỹ thuật ở log có kiểm soát và dùng correlation ID để liên kết request với log.

## 8. Phiên bản API là gì?

API contract gồm endpoint, method, request parameters, headers, schema response, mã trạng thái và ngữ nghĩa xử lý. Khi thay đổi một phần contract, client đang tích hợp có thể bị ảnh hưởng.

Ví dụ, API v1 trả:

~~~json
{
  "id": "ord_1024",
  "total": 125000
}
~~~

Một phiên bản mới có thể muốn đổi `total` thành một object tiền tệ:

~~~json
{
  "id": "ord_1024",
  "amount": {
    "value": 125000,
    "currency": "VND"
  }
}
~~~

Nếu xóa `total` ngay trên endpoint mà client cũ đang gọi, client có thể lỗi khi đọc response. API versioning tạo ranh giới để client lựa chọn contract mà họ đã tích hợp.

Không phải mọi thay đổi đều cần phiên bản mới. Việc thêm một field response tùy chọn thường có thể tương thích với client được thiết kế để bỏ qua field chưa biết. Tuy nhiên, một số client deserialize JSON theo schema strict hoặc dùng switch exhaustive trên enum nên ngay cả thay đổi tưởng là bổ sung cũng có thể gây lỗi. Hãy đánh giá cách client tiêu thụ contract trước khi phân loại thay đổi.

## 9. Chọn cách biểu diễn phiên bản API

Có ba cách thường gặp để client chọn phiên bản.

### 9.1. Phiên bản trong URL path

~~~http
GET /v1/orders
GET /v2/orders
~~~

Đây là cách dễ quan sát, dễ ghi log và dễ cấu hình route trên API Gateway. Hai phiên bản có thể chạy song song trong một khoảng thời gian. Client thấy rõ phiên bản đang gọi ngay trong URL.

Đổi lại, version trở thành một phần của URL tài nguyên. Khi triển khai nhiều phiên bản, nhóm cần quản lý route, tài liệu và thời gian hỗ trợ cho từng phiên bản. Với API công khai, cách này thường dễ hiểu và dễ vận hành.

### 9.2. Phiên bản trong HTTP header

~~~http
GET /orders
X-API-Version: 2
~~~

URL không đổi; server chọn contract dựa trên header. Cách này giữ URL gọn nhưng phiên bản ít hiển thị hơn trong log và khi debug thủ công. Cache hoặc CDN phải phân biệt response theo header này; nếu không, client có thể nhận response của phiên bản khác. Khi cache theo header, cần cấu hình `Vary: X-API-Version`.

Tên header như `X-API-Version` là quy ước riêng của API. Hãy định nghĩa rõ giá trị mặc định và hành vi khi header không có hoặc chứa phiên bản không được hỗ trợ.

### 9.3. Phiên bản qua media type

Client có thể chọn representation bằng `Accept`:

~~~http
GET /orders
Accept: application/vnd.example.orders.v2+json
~~~

Cách này gắn phiên bản với representation của tài nguyên và phù hợp khi hệ thống cần content negotiation. Tuy nhiên, client, gateway, tài liệu và cache phải hiểu media type cụ thể. Nó có thể phức tạp hơn mức cần thiết cho một API đơn giản.

### 9.4. Nên chọn cách nào?

| Cách | Điểm mạnh | Điểm cần quản lý |
|---|---|---|
| URL path (`/v1`) | Rõ ràng, dễ debug, route và tài liệu dễ tìm | URL có version, cần quản lý nhiều route |
| Header | URL ổn định, tách version khỏi đường dẫn tài nguyên | Cache, gateway và log phải xét header |
| Media type | Thể hiện representation và content negotiation | Client và tooling cần hỗ trợ media type |
| Query parameter (`?version=2`) | Dễ thử nhanh | Dễ bị bỏ sót, thường không phải lựa chọn tốt cho contract dài hạn |

Chọn một cách chính và dùng nhất quán trong toàn bộ API. Đối với API công khai hoặc API nội bộ có nhiều client, version trong path thường là lựa chọn dễ hiểu. Tránh để cùng một API có endpoint này chọn version bằng path, endpoint khác bằng header mà không có lý do rõ ràng.

Không nên tạo phiên bản mới cho mỗi lần deploy. Version biểu thị thay đổi contract có ảnh hưởng đến client, không phải số build, số release nội bộ hay phiên bản của function runtime.

## 10. Thay đổi tương thích và không tương thích

### 10.1. Những thay đổi thường có thể tương thích

Các thay đổi sau thường ít gây ảnh hưởng nếu client được thiết kế để bỏ qua dữ liệu chưa biết:

- Thêm field response tùy chọn.
- Thêm một endpoint mới.
- Thêm query parameter tùy chọn có mặc định hợp lý.
- Thêm link hoặc metadata response mà client không bắt buộc phải hiểu.

Tuy nhiên, không được giả định mọi client đều tolerant. Một client deserialize JSON theo schema strict có thể lỗi khi gặp field mới. Một client dùng switch exhaustive trên enum có thể lỗi khi server thêm giá trị enum. Hãy kiểm tra cách client thực tế xử lý response.

### 10.2. Những thay đổi thường cần version mới

Các thay đổi sau có nguy cơ phá vỡ client:

- Xóa hoặc đổi tên field response đang được sử dụng.
- Đổi kiểu dữ liệu, đơn vị hoặc ý nghĩa của field.
- Thêm request field bắt buộc mà client cũ không gửi.
- Đổi cách diễn giải filter, sort, pagination hoặc giá trị mặc định.
- Đổi cấu trúc response envelope hoặc định dạng lỗi.
- Thay đổi quyền truy cập hoặc quy tắc nghiệp vụ theo cách làm request cũ có kết quả khác.
- Xóa giá trị enum hoặc thay đổi ý nghĩa giá trị hiện có.

Ví dụ, đổi `total` từ số tiền VND sang số tiền tính bằng đơn vị nhỏ nhất mà không đổi tên field là thay đổi ngữ nghĩa dù JSON schema vẫn là number. Client có thể tiếp tục chạy nhưng hiển thị sai số tiền. Thay đổi ngữ nghĩa đôi khi nguy hiểm hơn thay đổi kiểu dữ liệu vì lỗi không xuất hiện ngay.

### 10.3. Giữ các contract độc lập

Nếu có `/v1/orders` và `/v2/orders`, mỗi route cần có schema và hành vi xác định. Không để `/v1` trả response v2 chỉ vì backend đã được refactor. Có thể dùng chung domain service hoặc repository, nhưng adapter/mapper của từng version chịu trách nhiệm chuyển domain model sang contract tương ứng.

Ví dụ:

~~~text
HTTP /v1/orders
    -> V1 request mapper
    -> OrderQueryService
    -> V1 response mapper

HTTP /v2/orders
    -> V2 request mapper
    -> OrderQueryService
    -> V2 response mapper
~~~

Cách tổ chức này giúp nhóm thay đổi model nội bộ mà không buộc mọi client nâng cấp cùng lúc. Không nên nhân đôi toàn bộ business logic nếu hai phiên bản chỉ khác representation; giữ phần nghiệp vụ dùng chung ở service/domain layer.

## 11. Deprecation và vòng đời phiên bản

Khi phát hành v2, client v1 không nhất thiết phải ngừng hoạt động ngay. Một quy trình chuyển đổi rõ ràng nên gồm:

1. Công bố phiên bản mới và lý do thay đổi.
2. Cung cấp tài liệu migration, ví dụ request/response trước và sau.
3. Thông báo ngày ngừng hỗ trợ dự kiến và khoảng thời gian chuyển đổi.
4. Theo dõi request theo API version và client/application ID để biết ai còn dùng phiên bản cũ.
5. Hỗ trợ client chuyển đổi và xác minh hành vi trên môi trường thử nghiệm.
6. Ngừng phiên bản cũ theo chính sách đã công bố, sau khi đánh giá tác động.

HTTP có thể dùng các header `Deprecation` và `Sunset` để báo trạng thái vòng đời. `Deprecation` cho biết API đã bị đánh dấu deprecated; `Sunset` có thể nêu thời điểm dự kiến tài nguyên không còn khả dụng. Header chỉ là tín hiệu cho client; chúng không thay thế thông báo, tài liệu và kế hoạch hỗ trợ.

Không nên âm thầm redirect v1 sang v2 nếu semantics hoặc schema khác nhau. Redirect có thể khiến client nhận response không tương thích hoặc làm thay đổi phương thức request trong một số tình huống. Nếu version cũ đã ngừng, hãy phản hồi theo chính sách đã công bố và hướng client đến tài liệu nâng cấp.

## 12. Cache, link và trải nghiệm client

### 12.1. Cache response GET

GET thường phù hợp với HTTP caching nếu dữ liệu và quyền truy cập cho phép. Server có thể trả `ETag` dựa trên representation của trang. Client gửi `If-None-Match`; nếu representation chưa đổi, server trả `304 Not Modified` và không gửi lại body.

Cache key phải xét các yếu tố làm thay đổi response: path, query parameters, version header hoặc media type, và danh tính nếu response được cache riêng theo người dùng. Với version trong header, cân nhắc `Vary: X-API-Version`. Với content negotiation, cân nhắc `Vary: Accept`.

Không cache công khai response chứa dữ liệu riêng tư hoặc dữ liệu theo tenant. Dùng `Cache-Control: private` hoặc `no-store` tùy chính sách. Không để CDN dùng chung cache entry giữa hai tenant chỉ vì URL và query giống nhau.

### 12.2. Link trang kế tiếp

Nếu response có `links.next`, client nên dùng URL đó để tiếp tục thay vì tự ghép cursor và filter. Điều này giúp server thay đổi cách encode cursor hoặc bổ sung tham số mà không buộc mọi client cập nhật.

Một link phải giữ đúng version, filter, sort và limit có hiệu lực. URL query cần được percent-encode đúng cách. Không đặt token bí mật hoặc thông tin cá nhân không cần thiết trong URL vì URL có thể xuất hiện trong access log, browser history hoặc hệ thống analytics.

### 12.3. Không giả định trang kế tiếp luôn tồn tại

Client phải xử lý:

- `nextCursor` vắng mặt hoặc `null`.
- Cursor hết hạn hoặc không còn hợp lệ.
- Một trang trả `data: []` do dữ liệu đã thay đổi.
- Lỗi mạng hoặc `429`/`503` khi tải trang tiếp theo.
- Người dùng thay đổi filter/sort trong lúc đang duyệt.

Khi filter hoặc sort thay đổi, client nên bắt đầu lại từ trang đầu. Không tái sử dụng cursor cũ cho truy vấn mới, trừ khi API định nghĩa rõ rằng cursor có thể dùng với tập điều kiện đó.

## 13. Thiết kế API cho môi trường serverless

Java function được kích hoạt bởi HTTP thường có vòng đời invocation ngắn và có thể chạy đồng thời trên nhiều instance. Thiết kế API cần tính đến các giới hạn của nền tảng:

- **Giới hạn kích thước trang:** đặt default và maximum limit để một request không đọc quá nhiều bản ghi.
- **Thời gian truy vấn:** đặt timeout cho database/query; không để request chờ một phép đếm hoặc tìm kiếm không giới hạn.
- **Connection pool:** concurrency của function có thể tăng nhanh hơn khả năng mở connection của database. Cần giới hạn concurrency, tái sử dụng client phù hợp và đặt pool size theo giới hạn hệ thống.
- **Bộ nhớ:** chỉ lấy các cột cần thiết, tránh tải toàn bộ entity graph hoặc serialize quan hệ không cần thiết.
- **Cold start:** giữ phần khởi tạo nhẹ; không tạo kết nối database hoặc đọc metadata đắt tiền lặp lại nếu nền tảng cho phép tái sử dụng an toàn giữa invocation.
- **Rate limit và backpressure:** bảo vệ database khi có nhiều client tải trang đồng thời hoặc liên tục tăng page size.
- **Chi phí:** mỗi trang là một invocation và có thể là một hoặc nhiều truy vấn. Cân bằng kích thước trang với số lần gọi, thời gian xử lý và dữ liệu truyền.

Nếu người dùng cần tải hàng trăm nghìn hoặc hàng triệu bản ghi, API phân trang tương tác có thể không phải công cụ phù hợp. Hãy cân nhắc endpoint tạo export job bất đồng bộ: request khởi tạo công việc, function/worker tạo file theo batch, lưu vào object storage và thông báo khi hoàn tất. Client tải file đã tạo thay vì giữ một HTTP invocation mở quá lâu.

## 14. Tài liệu hóa contract

OpenAPI nên mô tả rõ:

- Method, path và version.
- Query parameter, kiểu dữ liệu, giá trị mặc định và giới hạn.
- Các filter/sort được hỗ trợ và cách kết hợp điều kiện.
- Response schema cho trang có dữ liệu và trang cuối.
- Cursor là opaque token, cách client gửi lại và lỗi khi token không hợp lệ.
- Các HTTP status và error schema.
- Phiên bản được hỗ trợ, deprecated và thời điểm sunset.
- Ví dụ request/response cho từng luồng phổ biến.

Đừng chỉ ghi `cursor: string`. Tài liệu cần nói client không được giải mã hoặc tự sửa token, phải dùng cursor cùng filter/sort mà server đã cấp, và phải bắt đầu lại nếu truy vấn thay đổi.

Một ví dụ contract tốt giúp client biết chính xác họ có thể gửi gì, nhận gì và xử lý tình huống lỗi ra sao. Điều này giảm sự phụ thuộc vào trao đổi riêng giữa nhóm API và từng nhóm tích hợp.

## 15. Kiểm thử phân trang, filter và versioning

Kiểm thử happy path là chưa đủ. Nên bao phủ các trường hợp sau:

- Trang đầu, trang giữa, trang cuối và tập kết quả rỗng.
- `limit` mặc định, `limit` tối đa, giá trị âm, 0 và giá trị vượt giới hạn.
- Nhiều bản ghi có cùng sort key; xác nhận tie-breaker tạo thứ tự ổn định.
- Bản ghi được thêm hoặc xóa giữa hai request offset/cursor.
- Cursor bị sửa, hết hạn, sai version hoặc dùng với filter/sort khác.
- Filter enum không hợp lệ, khoảng thời gian đảo ngược và nhiều giá trị lặp.
- Tên sort không nằm trong allowlist và chuỗi đầu vào có ký tự đặc biệt.
- Caller không có quyền với tenant hoặc customer được yêu cầu.
- V1 và v2 trả đúng schema, lỗi và semantics riêng.
- Client v1 tiếp tục hoạt động khi v2 được phát hành.
- Cache không trả nhầm dữ liệu giữa version hoặc tenant.
- Query plan và thời gian truy vấn vẫn phù hợp ở offset sâu hoặc khi dữ liệu tăng lớn.

Với cursor pagination, hãy kiểm thử các bản ghi có timestamp trùng nhau để chắc chắn không bỏ sót hoặc lặp bản ghi do thiếu tie-breaker. Với filter, hãy kiểm tra cả trường hợp filter làm giảm kết quả về 0. Với versioning, contract test giúp phát hiện thay đổi vô tình trong response.

## 16. Tự kiểm tra

**Câu 1.** Vì sao một API danh sách không nên trả toàn bộ bản ghi?

**Gợi ý trả lời:** Response lớn làm tăng bộ nhớ, thời gian xử lý, chi phí truyền dữ liệu và tải database. Phân trang giới hạn công việc của mỗi request và giúp client duyệt dữ liệu theo nhu cầu.

**Câu 2.** Offset và cursor khác nhau thế nào khi dữ liệu liên tục được thêm mới?

**Gợi ý trả lời:** Offset dựa trên vị trí nên bản ghi mới ở trước có thể làm dịch chuyển trang và gây lặp/bỏ sót. Cursor dựa trên sort key của bản ghi cuối nên ít bị ảnh hưởng bởi bản ghi mới ở trước điểm neo, nhưng không tự tạo snapshot.

**Câu 3.** Vì sao cursor cần chứa mọi sort key và có chữ ký?

**Gợi ý trả lời:** Mọi sort key giúp xác định điểm tiếp tục duy nhất, kể cả khi nhiều bản ghi có cùng giá trị. Chữ ký giúp phát hiện token bị sửa trước khi dùng các giá trị đó trong truy vấn.

**Câu 4.** Vì sao không được ghép trực tiếp sort field từ query string vào SQL?

**Gợi ý trả lời:** Bind parameter bảo vệ giá trị nhưng không bảo vệ tên cột hoặc biểu thức được nối vào câu SQL. Cần allowlist field/direction và dùng parameterized query cho value.

**Câu 5.** Khi nào một thay đổi API cần version mới?

**Gợi ý trả lời:** Khi thay đổi có thể phá vỡ client như xóa/đổi tên field, đổi kiểu hoặc ý nghĩa, thêm request field bắt buộc, đổi cấu trúc response hoặc semantics của pagination/filter. Thêm field tùy chọn có thể tương thích nhưng vẫn cần kiểm tra client strict.

**Bài tập tình huống:** API đơn hàng hiện dùng `/v1/orders`, trả `total` dưới dạng số và phân trang bằng offset. Số bản ghi tăng lên hàng chục triệu; client mobile muốn tải thêm theo kiểu feed; nhóm sản phẩm cũng muốn trả tiền tệ theo cấu trúc `{value, currency}`. Hãy đề xuất contract v2, cách phân trang, quy tắc sort, cách chuyển client cũ và các kiểm thử cần có.

**Gợi ý:** V2 có thể dùng cursor/keyset với thứ tự ổn định `createdAt DESC, id DESC`, trả `nextCursor` và `hasMore`, đồng thời biểu diễn tiền tệ trong object. V1 tiếp tục giữ semantics và response cũ trong thời gian chuyển đổi. V2 cần giới hạn limit, ký và ràng buộc cursor với filter/sort/tenant, tài liệu hóa lỗi, theo dõi mức sử dụng v1 và công bố thời điểm sunset. Kiểm thử cursor với timestamp trùng, dữ liệu thay đổi giữa các trang, quyền tenant, schema từng version và hành vi client khi cursor hết hạn.

## Kết luận

Phân trang giới hạn khối lượng công việc của mỗi request; filter và sort xác định tập dữ liệu cũng như thứ tự ổn định; API versioning giúp thay đổi contract có kiểm soát. Offset đơn giản và phù hợp với tập dữ liệu vừa phải hoặc cần nhảy trang. Cursor/keyset thường phù hợp hơn với tập dữ liệu lớn được duyệt tuần tự, nhưng cần sort key ổn định và token được xác minh. Trong Java serverless, cần đặt giới hạn truy vấn, bảo vệ database trước concurrency, kiểm tra quyền ở mọi trang và duy trì contract rõ ràng cho từng phiên bản.
