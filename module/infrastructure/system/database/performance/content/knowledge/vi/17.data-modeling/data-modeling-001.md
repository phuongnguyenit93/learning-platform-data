# Chọn kiểu dữ liệu theo miền giá trị và chi phí lưu trữ

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Xác định miền giá trị, độ chính xác và các quy tắc hợp lệ trước khi chọn kiểu dữ liệu cho một cột.
- So sánh chi phí lưu trữ của kiểu số, chuỗi, thời gian, UUID, JSON và dữ liệu nhị phân.
- Giải thích độ rộng hàng ảnh hưởng đến mật độ trang, bộ nhớ đệm, I/O và kích thước chỉ mục như thế nào.
- Tránh các lỗi về tràn số, làm tròn, múi giờ, collation, chuyển kiểu ngầm định và biểu diễn NULL.
- Thiết kế schema có kiểu dữ liệu phù hợp với truy vấn, ràng buộc và workload ghi/đọc thực tế.

## 1. Chọn kiểu dữ liệu là quyết định về ngữ nghĩa và hiệu năng

Kiểu dữ liệu mô tả miền giá trị mà một cột được phép chứa và cách hệ quản trị lưu, so sánh, tính toán, lập chỉ mục và truyền giá trị đó. Chọn kiểu dữ liệu vì thế ảnh hưởng trực tiếp đến tính đúng đắn của nghiệp vụ, dung lượng lưu trữ và chi phí xử lý.

Trong module DATABASE_PERFORMANCE, mô hình dữ liệu cần hỗ trợ các mục tiêu như giảm kích thước hàng, giữ chỉ mục gọn, hạn chế I/O, giúp bộ tối ưu ước lượng chính xác và tránh chuyển kiểu không cần thiết. Tuy nhiên, chọn kiểu quá hẹp chỉ để tiết kiệm vài byte có thể gây tràn số hoặc buộc phải đổi schema khi dữ liệu tăng.

Nguyên tắc là chọn kiểu nhỏ nhất vẫn biểu diễn an toàn toàn bộ miền giá trị hợp lệ trong vòng đời dự kiến của dữ liệu. Miền giá trị phải bao gồm cả giá trị biên, tăng trưởng, dữ liệu nhập từ hệ thống khác và yêu cầu tương lai đã biết.

Trước khi chọn kiểu, hãy trả lời:

- Giá trị có thể âm hay chỉ không âm?
- Giá trị nhỏ nhất và lớn nhất là bao nhiêu?
- Có phần thập phân không? Nếu có, cần bao nhiêu chữ số chính xác?
- Đơn vị đo là gì: đồng, xu, giây, mili giây, mét hay phần trăm?
- Có cần so sánh theo thứ tự, theo khoảng hoặc dùng làm khóa nối không?
- Dữ liệu có cần giữ nguyên định dạng người dùng nhập hay chỉ cần giữ giá trị chuẩn hóa?
- Có quy tắc về NULL, duy nhất, miền mã hoặc múi giờ không?

## 2. Miền giá trị và kiểu số nguyên

Kiểu số nguyên phù hợp với số đếm, định danh dạng số, số lượng, trạng thái mã hóa và các giá trị không có phần thập phân. Hãy chọn độ rộng dựa trên miền giá trị, không dựa trên số liệu hiện tại.

### Các độ rộng thường gặp

| Kiểu | Dung lượng dữ liệu thường gặp | Miền signed thường gặp |
| --- | ---: | --- |
| 8-bit integer | 1 byte | -128 đến 127 |
| 16-bit integer | 2 byte | -32.768 đến 32.767 |
| 32-bit integer | 4 byte | -2.147.483.648 đến 2.147.483.647 |
| 64-bit integer | 8 byte | khoảng -9,22 × 10^18 đến 9,22 × 10^18 |

Đây là độ rộng và miền giá trị điển hình. Tên kiểu, kiểu không dấu và chi tiết lưu trữ khác nhau giữa hệ quản trị.

| Hệ quản trị | Một số kiểu số nguyên |
| --- | --- |
| PostgreSQL | `smallint` (2 byte), `integer` (4 byte), `bigint` (8 byte) |
| MySQL | `TINYINT` (1 byte), `SMALLINT` (2), `MEDIUMINT` (3), `INT` (4), `BIGINT` (8); có `UNSIGNED` |
| SQL Server | `tinyint` (1 byte, không âm), `smallint` (2), `int` (4), `bigint` (8) |

### Không chọn kiểu quá hẹp

Giả sử một bảng hiện có 20.000 khách hàng. Dùng kiểu 16-bit cho customer_id có thể đủ ở thời điểm hiện tại nếu chỉ dùng số dương, nhưng miền signed chỉ đến 32.767. Khi hệ thống tăng trưởng, cột có thể chạm giới hạn và cần migration trên bảng lớn cùng các khóa ngoại, chỉ mục và hệ thống tích hợp.

Đối với khóa chính, hãy cân nhắc tốc độ tăng dữ liệu, thời gian tồn tại, số lượng bản ghi có thể nhập từ nhiều nguồn và khả năng hợp nhất dữ liệu. `bigint` tốn nhiều byte hơn `int`, nhưng có miền lớn và tránh một đợt thay đổi kiểu tốn kém sau này.

### Signed và unsigned

MySQL hỗ trợ kiểu số nguyên `UNSIGNED`, mở rộng miền không âm lên phía trên. PostgreSQL không có kiểu số nguyên unsigned tương đương trực tiếp; SQL Server `tinyint` là kiểu không âm, còn các kiểu integer lớn hơn là signed.

Không nên chọn unsigned chỉ vì cột thường không âm nếu ứng dụng cần tương thích với nhiều hệ quản trị. Có thể dùng kiểu signed cùng CHECK constraint `value >= 0` để diễn đạt quy tắc miền giá trị theo cách dễ di chuyển hơn.

Ví dụ:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
```

CHECK constraint bảo vệ miền dữ liệu ở phía cơ sở dữ liệu. Kiểu dữ liệu vẫn cần đủ rộng cho giá trị tối đa hợp lệ.

## 3. Số thập phân chính xác và số dấu phẩy động

Không phải mọi số có phần thập phân đều nên dùng cùng một kiểu.

### DECIMAL/NUMERIC cho giá trị cần chính xác

`DECIMAL(p, s)` hoặc `NUMERIC(p, s)` biểu diễn số thập phân với độ chính xác và scale được khai báo:

- `p` là tổng số chữ số có nghĩa được lưu.
- `s` là số chữ số ở bên phải dấu thập phân.

Ví dụ `DECIMAL(12, 2)` cho phép tối đa 12 chữ số, trong đó 2 chữ số ở phần thập phân. Đây thường là lựa chọn phù hợp cho tiền tệ, giá, thuế hoặc số đo cần quy tắc làm tròn xác định.

```sql
CREATE TABLE invoice_lines (
    line_id BIGINT PRIMARY KEY,
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price DECIMAL(19, 4) NOT NULL,
    line_total DECIMAL(19, 2) NOT NULL
);
```

Độ chính xác và dung lượng lưu trữ của DECIMAL/NUMERIC phụ thuộc hệ quản trị. Không nên giả định mọi sản phẩm lưu cùng một số byte cho cùng precision.

### FLOAT/REAL/DOUBLE cho giá trị gần đúng

Kiểu dấu phẩy động dùng biểu diễn nhị phân gần đúng. Nhiều số thập phân như 0,1 không thể biểu diễn chính xác trong dạng nhị phân hữu hạn, nên phép tính có thể tạo sai số nhỏ.

FLOAT/REAL/DOUBLE phù hợp với đo lường khoa học, mô phỏng, thống kê hoặc thuật toán chấp nhận sai số và cần miền động lớn. Chúng thường không phù hợp để lưu tiền cần đối soát chính xác.

Ví dụ:

```sql
-- Giá trị tiền cần chính xác
unit_price DECIMAL(19, 4) NOT NULL

-- Nhiệt độ đo có thể chấp nhận sai số theo yêu cầu ứng dụng
temperature DOUBLE PRECISION
```

### Lưu tiền bằng số nguyên đơn vị nhỏ nhất

Một thiết kế khác là lưu tiền dưới dạng số nguyên theo đơn vị nhỏ nhất, chẳng hạn xu hoặc đồng tùy loại tiền. Cách này tránh sai số dấu phẩy động nhưng cần quy định đơn vị, số chữ số thập phân theo từng currency và quy tắc làm tròn.

Không nên mặc định mọi loại tiền có cùng hai chữ số thập phân. Nếu hệ thống hỗ trợ nhiều currency, cần lưu mã tiền tệ và quy tắc scale phù hợp. Dùng DECIMAL thường đơn giản hơn khi phép tính tài chính cần precision/scale rõ ràng.

### Kiểm soát tràn số và làm tròn

Tràn số có thể xảy ra không chỉ ở cột mà cả biểu thức trung gian. Ví dụ, `quantity * unit_price` có thể vượt precision của kiểu kết quả nếu quantity lớn hoặc scale không đủ.

Hãy kiểm tra:

- Precision và scale của từng toán hạng.
- Kiểu kết quả của phép nhân, chia, SUM và AVG trong hệ quản trị.
- Quy tắc làm tròn ở từng bước và tại thời điểm lưu.
- Giá trị tối đa theo nghiệp vụ, không chỉ theo dữ liệu hiện có.
- Hành vi khi giá trị vượt miền: báo lỗi, làm tròn hay cắt bớt theo hệ quản trị và cấu hình.

## 4. BOOLEAN, mã trạng thái và ENUM

Giá trị đúng/sai nên dùng kiểu BOOLEAN hoặc kiểu tương đương nếu hệ quản trị hỗ trợ. Tránh lưu `true`, `false`, `yes`, `no`, `1`, `0` dưới dạng chuỗi tùy tiện vì làm tăng dung lượng và khiến điều kiện so sánh dễ không nhất quán.

Không phải hệ quản trị nào cũng có cùng kiểu Boolean vật lý. PostgreSQL có `boolean`; SQL Server thường dùng `bit`; MySQL có alias `BOOL`/`BOOLEAN` dựa trên `TINYINT(1)`. Hãy dùng kiểu và quy tắc của nền tảng đích.

Với tập trạng thái nhỏ, có thể dùng mã số hoặc chuỗi ngắn kết hợp CHECK constraint hoặc bảng tham chiếu:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
);
```

ENUM có thể tiết kiệm không gian hoặc bảo đảm tập giá trị trong một số hệ quản trị, nhưng cách thêm/sắp xếp giá trị và tính di động khác nhau. Nếu trạng thái thay đổi thường xuyên, cần mô tả metadata, có bản dịch hoặc có quan hệ nghiệp vụ riêng, bảng danh mục thường linh hoạt hơn.

Không nên dùng số nguyên không có bảng ánh xạ rõ ràng để mã hóa trạng thái. Khi đọc dữ liệu hoặc phân tích log, mã `3` không có ý nghĩa nếu không biết nó đại diện cho trạng thái nào.

## 5. Chọn kiểu chuỗi theo độ dài và ngữ nghĩa

Kiểu chuỗi cần phản ánh độ dài tối đa, bộ ký tự, cách so sánh và cách xử lý khoảng trắng.

### CHAR và VARCHAR

- `CHAR(n)` biểu diễn chuỗi độ dài cố định và có thể đệm khoảng trắng theo quy tắc hệ quản trị.
- `VARCHAR(n)` biểu diễn chuỗi có độ dài thay đổi, với giới hạn độ dài khai báo.
- `TEXT` hoặc kiểu chuỗi lớn phù hợp với nội dung dài, nhưng cần xem giới hạn và khả năng lập chỉ mục của sản phẩm.

Không có quy tắc rằng CHAR luôn nhanh hơn VARCHAR. Với dữ liệu có độ dài thay đổi, VARCHAR thường tránh lưu phần đệm không cần thiết. CHAR có thể phù hợp với mã có độ dài cố định, nhưng cần hiểu ngữ nghĩa so sánh khoảng trắng.

Trong PostgreSQL, `text` và `varchar` có hành vi lưu trữ tương tự cho phần lớn trường hợp; giới hạn `varchar(n)` chủ yếu là ràng buộc độ dài. SQL Server phân biệt `char`/`varchar` với `nchar`/`nvarchar`; kiểu Unicode có cách tính dung lượng riêng. MySQL phụ thuộc charset và collation của cột/bảng.

### Unicode và charset

Nếu dữ liệu có thể chứa tiếng Việt hoặc nhiều ngôn ngữ, hãy chọn bộ ký tự hỗ trợ đầy đủ Unicode. Không giả định một ký tự luôn chiếm một byte. UTF-8 dùng từ 1 đến 4 byte cho mỗi code point; UTF-16 thường dùng 2 hoặc 4 byte.

Độ dài `VARCHAR(n)` có thể được tính theo ký tự hoặc byte tùy hệ quản trị và charset. Cần kiểm tra tài liệu sản phẩm, đặc biệt khi tích hợp dữ liệu từ nhiều hệ thống.

### Collation và so sánh

Collation quyết định quy tắc so sánh và sắp xếp chuỗi, ví dụ phân biệt hoa/thường, dấu và thứ tự từ điển. Hai cột có collation khác nhau có thể gây chuyển đổi hoặc làm truy vấn JOIN/ORDER BY phức tạp.

Chọn collation theo quy tắc nghiệp vụ và thống nhất giữa các cột thường JOIN hoặc so sánh. Đừng thay collation chỉ để ép một chỉ mục được dùng vì điều đó có thể thay đổi ngữ nghĩa tìm kiếm.

### Lưu số điện thoại, mã bưu chính và định danh

Những giá trị trông giống số nhưng không dùng để tính toán nên lưu dạng chuỗi:

- Số điện thoại có thể có dấu `+`, mã quốc gia và số 0 ở đầu.
- Mã bưu chính có thể chứa chữ và số 0 ở đầu.
- Mã đơn hàng có thể có tiền tố hoặc dấu phân cách.
- Số tài khoản có thể dài hơn miền số nguyên hoặc cần giữ nguyên định dạng.

Nếu lưu dưới kiểu số, số 0 ở đầu có thể mất và phép tính số học không có ý nghĩa nghiệp vụ.

## 6. Ngày giờ, múi giờ và độ chính xác

Ngày giờ cần phân biệt thời điểm tuyệt đối với ngày giờ địa phương.

- **DATE:** ngày lịch, không có thời gian trong ngày.
- **TIME:** giờ trong ngày, không gắn với ngày.
- **TIMESTAMP/DATETIME:** ngày và giờ; ý nghĩa múi giờ phụ thuộc hệ quản trị và kiểu cụ thể.
- **Timestamp with time zone / datetimeoffset:** kiểu có ngữ nghĩa liên quan đến múi giờ hoặc offset theo cách riêng của hệ quản trị.

### Lưu thời điểm tuyệt đối

Với thời điểm sự kiện như thanh toán thành công, đăng nhập hoặc gửi thông báo, thường cần lưu một instant có thể quy đổi nhất quán. Một quy ước phổ biến là nhận đầu vào có múi giờ, chuẩn hóa về UTC ở tầng ứng dụng hoặc hệ quản trị, và hiển thị theo múi giờ người dùng.

PostgreSQL `timestamp with time zone` (`timestamptz`) lưu thời điểm theo chuẩn nội bộ và hiển thị theo timezone của session; nó không giữ nguyên tên múi giờ ban đầu mà người dùng nhập. `timestamp without time zone` chỉ là ngày giờ địa phương không gắn timezone.

MySQL `TIMESTAMP` có chuyển đổi giữa timezone session và giá trị UTC nội bộ theo quy tắc của sản phẩm; `DATETIME` lưu giá trị ngày giờ mà không tự chuyển đổi theo timezone session.

SQL Server có `datetime2` không lưu offset; `datetimeoffset` lưu ngày giờ cùng offset. Offset không đồng nghĩa với tên vùng múi giờ có quy tắc DST.

### Lưu lịch địa phương

Lịch hẹn như 9 giờ sáng ngày 15 tháng 5 tại một thành phố là một local date-time gắn với vùng múi giờ. Nếu chỉ lưu một timestamp UTC mà không giữ zone, có thể mất ý nghĩa khi quy tắc DST hoặc lịch địa phương thay đổi.

Với lịch tương lai, cân nhắc lưu cả local date-time và mã vùng múi giờ IANA như `Asia/Ho_Chi_Minh`, cùng chính sách xử lý khi quy tắc múi giờ thay đổi. Với sự kiện đã xảy ra, lưu instant UTC thường là cần thiết để đối chiếu thứ tự và thời điểm.

### Độ chính xác thời gian

Không phải mọi hệ quản trị có cùng precision. Một số kiểu lưu microsecond, một số kiểu có độ chính xác khác hoặc cho phép chỉ định fractional seconds precision. Chọn độ chính xác theo nguồn dữ liệu và yêu cầu nghiệp vụ; không cần lưu nanosecond nếu thiết bị chỉ đo đến millisecond.

Đối với khoảng thời gian, dùng kiểu interval/duration nếu hệ quản trị và nghiệp vụ phù hợp, hoặc lưu số nguyên với đơn vị rõ ràng. Không lưu thời lượng dưới dạng chuỗi như `"00:05:30"` nếu cần cộng/trừ và lọc theo khoảng thường xuyên.

## 7. UUID và khóa định danh

UUID là định danh 128-bit, thường chiếm 16 byte ở dạng nhị phân. Dạng chuỗi có dấu gạch ngang thường dài 36 ký tự, chưa tính overhead của kiểu chuỗi và collation.

Ví dụ UUID có thể hữu ích khi cần tạo ID ở nhiều dịch vụ hoặc nhiều nút mà không cần xin số tuần tự từ một cơ sở dữ liệu trung tâm. Tuy nhiên, UUID không tự động tốt hơn BIGINT.

| Đặc điểm | BIGINT tăng tuần tự | UUID ngẫu nhiên |
| --- | --- | --- |
| Dung lượng khóa | Thường 8 byte | 16 byte dạng nhị phân; chuỗi hiển thị dài hơn |
| Khả năng tạo phân tán | Cần cơ chế cấp ID hoặc phân vùng dải | Có thể tạo độc lập với xác suất trùng rất thấp |
| Thứ tự chèn B-tree | Thường có locality tốt khi tăng tuần tự | UUID ngẫu nhiên có thể chèn vào nhiều vùng của cây |
| Kích thước chỉ mục phụ | Khóa nhỏ hơn thường giúp chỉ mục gọn | Khóa rộng có thể làm chỉ mục phụ lớn hơn |

UUID ngẫu nhiên như UUIDv4 có thể làm tăng page split và giảm locality khi dùng làm clustered key hoặc khóa chính của cấu trúc lưu trữ theo B-tree. UUID có thứ tự thời gian như UUIDv7 có thể cải thiện locality chèn so với UUID ngẫu nhiên thuần túy, nhưng vẫn rộng hơn BIGINT và cần kiểm tra cách triển khai.

Nếu dùng UUID, hãy lưu bằng kiểu UUID/native hoặc dạng nhị phân 16 byte khi hệ quản trị hỗ trợ, thay vì chuỗi 36 ký tự trong mọi chỉ mục. Với MySQL có thể dùng `BINARY(16)` và quy ước byte order nhất quán. Không đổi byte order tùy tiện giữa các dịch vụ.

## 8. JSON, XML và dữ liệu bán cấu trúc

JSON phù hợp cho payload linh hoạt, thuộc tính thay đổi theo loại đối tượng hoặc dữ liệu cần lưu cùng nhau như một tài liệu. Nhưng nếu trường JSON được dùng thường xuyên để lọc, JOIN, sắp xếp, phân vùng hoặc ràng buộc, cần cân nhắc đưa trường đó thành cột có kiểu rõ ràng.

Ví dụ:

```sql
CREATE TABLE events (
    event_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    payload JSON
);
```

`tenant_id`, `event_type` và `occurred_at` là thuộc tính ổn định phục vụ lọc và phân tích nên có thể đặt thành cột. `payload` giữ phần thuộc tính mở rộng.

Chỉ mục trên JSON có chi phí riêng và phụ thuộc toán tử, operator class hoặc cơ chế generated/computed column của hệ quản trị. Không nên tạo chỉ mục toàn bộ payload nếu truy vấn chỉ dùng một scalar; chỉ mục chuyên biệt có thể lớn và tốn chi phí cập nhật.

XML hoặc kiểu tài liệu khác cũng cần cân nhắc tương tự: chọn kiểu native khi cần thao tác cấu trúc và công cụ hỗ trợ tốt; dùng văn bản khi chỉ cần lưu nguyên nội dung, nhưng phải kiểm soát encoding và validation ở tầng phù hợp.

## 9. BINARY, BLOB và dữ liệu lớn

Dữ liệu nhị phân như ảnh, tệp, nội dung mã hóa hoặc payload nén có thể lưu trong BLOB/BYTEA/VARBINARY hoặc hệ thống lưu trữ đối tượng bên ngoài.

Lưu dữ liệu lớn trong hàng có thể làm hàng rộng, tăng I/O và làm các truy vấn chỉ cần metadata phải đọc qua nhiều trang hơn nếu truy vấn lấy payload không cần thiết. Nhiều hệ quản trị có cơ chế lưu dữ liệu lớn ngoài hàng hoặc overflow, nhưng truy cập payload vẫn có thể phát sinh I/O bổ sung.

Cân nhắc lưu metadata trong cơ sở dữ liệu và nội dung lớn trong object storage khi:

- Payload rất lớn và thường được tải theo luồng.
- Cần phân phối qua CDN hoặc chính sách vòng đời lưu trữ riêng.
- Backup/restore của database không nên gánh toàn bộ dung lượng file.
- Ứng dụng có thể quản lý tham chiếu, quyền truy cập và tính nhất quán giữa metadata với object.

Lưu ngoài cơ sở dữ liệu làm phát sinh bài toán nhất quán phân tán: bản ghi có thể tồn tại nhưng file chưa tải lên hoặc file đã bị xóa nhưng metadata còn. Cần thiết kế trạng thái upload, retry, cleanup và idempotency.

Nếu lưu BLOB trong database, dùng kiểu có giới hạn phù hợp, không lấy payload trong truy vấn danh sách và cân nhắc phân vùng hoặc bảng riêng cho dữ liệu lớn.

## 10. NULL, DEFAULT và ràng buộc miền giá trị

NULL biểu thị thiếu hoặc chưa biết giá trị, không đồng nghĩa với 0, chuỗi rỗng hay FALSE. Việc cho phép NULL ảnh hưởng logic truy vấn, thống kê và cách tính toán.

Hãy quyết định rõ:

- Cột có bắt buộc phải có giá trị không? Nếu có, dùng NOT NULL.
- Giá trị mặc định có thực sự là giá trị nghiệp vụ không, hay chỉ che việc ứng dụng bỏ sót dữ liệu?
- NULL có nghĩa là chưa biết, không áp dụng hay chưa được cung cấp? Nếu các nghĩa khác nhau, cần mô hình hóa rõ.
- Có CHECK, UNIQUE hoặc FOREIGN KEY nào cần để bảo vệ miền dữ liệu không?

Ví dụ:

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    weight_kg DECIMAL(10, 3),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    price DECIMAL(19, 2) NOT NULL CHECK (price >= 0)
);
```

`weight_kg` có thể NULL nếu chưa biết cân nặng; `is_active` có mặc định TRUE nếu đó là quy tắc nghiệp vụ; `price` bắt buộc và không âm. Không nên đặt DEFAULT 0 cho cân nặng chỉ để tránh NULL nếu 0 có nghĩa sản phẩm thực sự không có khối lượng.

NULL cũng ảnh hưởng chỉ mục và phép nối. Hành vi UNIQUE với nhiều NULL khác nhau giữa hệ quản trị và tùy loại chỉ mục; cần kiểm tra sản phẩm. Khi JOIN bằng `=`, NULL không khớp NULL theo logic SQL thông thường.

## 11. Kiểu dữ liệu ảnh hưởng độ rộng hàng và mật độ trang

Cơ sở dữ liệu thường đọc/ghi theo page hoặc block. Khi hàng rộng, mỗi trang chứa được ít hàng hơn, bảng cần nhiều trang hơn và buffer cache giữ được ít bản ghi hơn.

Ví dụ, một bảng có các cột:

- `id BIGINT`.
- `status VARCHAR(20)`.
- `created_at TIMESTAMP`.
- `description TEXT`.
- `payload JSON`.

Nếu phần lớn truy vấn chỉ cần `id`, `status` và `created_at`, việc thường xuyên dùng `SELECT *` có thể làm ứng dụng đọc và truyền cả description/payload không cần thiết. Tách payload ít dùng sang bảng chi tiết hoặc truy vấn theo hai bước có thể giảm chi phí của luồng danh sách.

Độ rộng hàng ảnh hưởng:

- Số hàng có thể chứa trong mỗi trang.
- Tổng số page của bảng và chỉ mục.
- Số trang cần đọc cho table scan hoặc range scan.
- Cache footprint và xác suất giữ trang nóng.
- Lượng dữ liệu phải ghi vào transaction log/WAL khi insert hoặc update.
- Chi phí truyền kết quả qua mạng và giải mã ở ứng dụng.

Không thể tính chính xác dung lượng hàng chỉ bằng cộng độ rộng khai báo của các cột. Còn có row header, null bitmap, alignment, offset/slot, padding, biến độ dài, nén, phiên bản hàng và cơ chế lưu dữ liệu ngoài hàng. Hãy dùng công cụ thống kê của hệ quản trị để đo kích thước thực.

## 12. Kiểu dữ liệu ảnh hưởng kích thước chỉ mục

Chỉ mục thường lưu khóa và row locator hoặc các cột được bao phủ. Khóa rộng làm giảm số mục trên một trang, có thể tăng chiều cao cây, dung lượng chỉ mục và số page cần đọc.

Ví dụ, nếu một bảng dùng UUID chuỗi làm khóa chính và nhiều chỉ mục phụ phải mang khóa này làm row locator, dung lượng chỉ mục phụ có thể lớn hơn đáng kể so với dùng một khóa 64-bit. Chi tiết phụ thuộc cách hệ quản trị tổ chức bảng và secondary index.

Đối với composite index, mỗi cột thêm vào làm mục chỉ mục rộng hơn. Thêm cột chỉ để bao phủ một truy vấn ít chạy có thể làm tăng chi phí INSERT/UPDATE trên mọi giao dịch.

Chọn kiểu dữ liệu nhất quán giữa các cột JOIN và khóa ngoại. Nếu một phía dùng BIGINT còn phía kia dùng VARCHAR, hệ quản trị có thể phải chuyển kiểu, ảnh hưởng index access và cardinality estimate. Đồng nhất kiểu, độ dài và collation giúp phép nối rõ ràng hơn.

## 13. Chuyển kiểu ngầm định và khả năng dùng chỉ mục

Khi hai toán hạng khác kiểu, hệ quản trị có thể thực hiện implicit conversion. Vị trí chuyển đổi có thể làm thay đổi khả năng sử dụng chỉ mục.

Ví dụ, nếu `customer_id` là BIGINT nhưng ứng dụng bind tham số dưới dạng chuỗi, hệ quản trị có thể phải chuyển kiểu. Hành vi cụ thể tùy sản phẩm và quy tắc ưu tiên kiểu.

Ưu tiên:

- Bind tham số bằng đúng kiểu tương ứng với cột.
- Dùng cùng kiểu cho khóa chính và khóa ngoại.
- Tránh bọc cột có chỉ mục trong CAST hoặc hàm nếu không cần thiết.
- Nếu phải tìm theo biểu thức chuẩn hóa, cân nhắc expression index hoặc generated/computed column.
- Kiểm tra actual execution plan để xác nhận seek/scan và cảnh báo conversion.

Ví dụ:

```sql
-- Cột customer_id là BIGINT: truyền tham số kiểu BIGINT
SELECT order_id
FROM orders
WHERE customer_id = ?;

-- Tránh chuyển cột trong điều kiện nếu không cần
SELECT order_id
FROM orders
WHERE CAST(customer_id AS VARCHAR(30)) = ?;
```

Không phải mọi CAST đều làm mất index; một số hệ quản trị có thể tối ưu hoặc có thể dùng chỉ mục biểu thức. Nhưng chuyển đổi không cần thiết làm truy vấn khó dự đoán và có thể ảnh hưởng ước lượng.

## 14. Ví dụ thiết kế schema theo miền giá trị

Giả sử hệ thống thương mại điện tử cần lưu khách hàng, đơn hàng và chi tiết hàng hóa. Một thiết kế minh họa cho PostgreSQL:

```sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    phone VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_number SMALLINT NOT NULL CHECK (line_number > 0),
    product_id BIGINT NOT NULL,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 4) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_number)
);
```

Những quyết định chính:

- Khóa định danh BIGINT có miền tăng trưởng lớn và dùng cùng kiểu ở các FK.
- Email là chuỗi vì không dùng cho phép tính; giới hạn 320 cần được xác nhận theo chính sách sản phẩm.
- Phone là chuỗi để giữ dấu cộng, mã quốc gia và số 0 đầu.
- Thời điểm tạo dùng TIMESTAMPTZ vì cần biểu diễn một instant.
- Status dùng chuỗi ngắn cùng CHECK để dữ liệu có tập giá trị hợp lệ.
- Currency code lưu riêng vì số tiền cần biết đơn vị tiền.
- Quantity và unit price dùng NUMERIC với scale theo nghiệp vụ.
- line_number dùng SMALLINT chỉ khi số dòng tối đa trong một đơn được giới hạn chắc chắn; nếu không, chọn kiểu rộng hơn.

Đây là ví dụ định hướng, không phải schema dùng trực tiếp cho mọi hệ thống. Cần xác nhận độ dài email, số dòng mỗi đơn, quy tắc tiền tệ, chính sách định danh và phiên bản PostgreSQL.

## 15. Quy trình chọn kiểu dữ liệu

1. **Mô tả miền nghiệp vụ.** Ghi giá trị nhỏ nhất/lớn nhất, đơn vị, độ chính xác, định dạng và khả năng thiếu dữ liệu.
2. **Xác định thao tác.** Cột được tính toán, so sánh bằng, lọc theo khoảng, sắp xếp, JOIN hay chỉ hiển thị?
3. **Chọn kiểu có ngữ nghĩa đúng.** Số đếm dùng integer; tiền dùng DECIMAL/NUMERIC hoặc minor-unit integer theo quy tắc; thời điểm dùng kiểu có timezone phù hợp.
4. **Ước lượng tăng trưởng.** Xem số bản ghi tối đa, tuổi thọ dữ liệu, tích hợp nhiều nguồn và giới hạn ID.
5. **Tính chi phí hàng và chỉ mục.** Xem độ rộng cột, khóa chính, row locator, composite index và payload lớn.
6. **Thiết lập ràng buộc.** Dùng NOT NULL, CHECK, UNIQUE và FOREIGN KEY để bảo vệ miền dữ liệu.
7. **Kiểm tra tương thích hệ quản trị.** Xem độ rộng vật lý, precision, charset, collation, timezone và hành vi chuyển kiểu.
8. **Kiểm tra driver và ứng dụng.** Bind tham số đúng kiểu, giữ precision khi serialize và không chuyển ngày giờ qua local timezone ngoài ý muốn.
9. **Đo workload đại diện.** So sánh page count, index size, logical/physical reads, CPU, throughput và độ trễ.
10. **Theo dõi dữ liệu thực.** Kiểm tra phân bố, giá trị gần giới hạn, NULL, độ dài chuỗi và tăng trưởng theo thời gian.

## 16. Những sai lầm thường gặp

- **Chọn integer quá nhỏ theo dữ liệu hiện tại.** Có thể chạm giới hạn khi hệ thống tăng trưởng và cần migration phức tạp.
- **Dùng FLOAT cho tiền.** Sai số nhị phân có thể làm lệch phép tính và đối soát.
- **Dùng kiểu số cho số điện thoại hoặc mã có số 0 đầu.** Định dạng bị mất và phép tính không có ý nghĩa.
- **Lưu ngày giờ địa phương như thể là instant UTC.** Có thể gây lệch thời gian khi người dùng ở múi giờ khác hoặc khi quy tắc DST thay đổi.
- **Dùng VARCHAR cho mọi thứ.** Kiểu chuỗi không bảo vệ miền giá trị và có thể làm mất khả năng tính toán, ràng buộc hoặc sắp xếp đúng.
- **Dùng CHAR với chuỗi biến độ dài.** Padding và quy tắc so sánh khoảng trắng có thể gây bất ngờ.
- **Lưu UUID dưới dạng chuỗi trong mọi chỉ mục.** Có thể làm khóa và chỉ mục rộng hơn cần thiết.
- **Nhét mọi thuộc tính vào JSON.** Trường thường xuyên JOIN, lọc hoặc ràng buộc có thể nên là cột quan hệ.
- **Chọn precision/scale tùy tiện.** Phép tính trung gian có thể tràn hoặc làm tròn ngoài ý muốn.
- **Không thống nhất kiểu giữa FK và PK.** Có thể phát sinh chuyển kiểu và làm giảm hiệu quả JOIN.
- **Tối ưu byte nhưng bỏ qua chi phí migration.** Một kiểu hẹp hơn không đáng nếu sớm phải thay đổi trên bảng và chỉ mục lớn.
- **Cho rằng độ rộng khai báo bằng dung lượng thực.** Header, alignment, NULL, biến độ dài và cơ chế lưu trữ làm kích thước thực khác đi.

## 17. Danh sách kiểm tra trước khi tạo hoặc thay đổi cột

- [ ] Miền giá trị hợp lệ và giá trị biên đã được xác định.
- [ ] Kiểu số nguyên đủ rộng cho tăng trưởng dự kiến.
- [ ] Tiền và số thập phân cần chính xác dùng precision/scale phù hợp.
- [ ] Đơn vị đo và quy tắc làm tròn được ghi rõ.
- [ ] Chuỗi hỗ trợ Unicode và có độ dài phù hợp.
- [ ] Collation phù hợp với quy tắc so sánh nghiệp vụ.
- [ ] Ngày giờ phân biệt rõ DATE, local time và instant có timezone.
- [ ] UUID hoặc khóa số được chọn theo khả năng tạo ID, locality và kích thước chỉ mục.
- [ ] Trường JSON thường xuyên truy vấn được cân nhắc tách thành cột hoặc lập chỉ mục phù hợp.
- [ ] Payload lớn được truy xuất có chọn lọc và có chiến lược lưu trữ.
- [ ] NULL, DEFAULT, CHECK, UNIQUE và FK diễn đạt đúng quy tắc dữ liệu.
- [ ] Kiểu của PK, FK và tham số ứng dụng tương thích.
- [ ] Đã đo kích thước hàng, chỉ mục, page count và tác động lên cache/I/O.
- [ ] Đã đánh giá chi phí migration và tương thích dữ liệu cũ.

## Kết luận

Chọn kiểu dữ liệu theo miền giá trị giúp bảo vệ tính đúng đắn và tránh giới hạn sớm; chọn kiểu có kích thước phù hợp giúp giảm độ rộng hàng, dung lượng chỉ mục, áp lực cache và I/O. Hãy phân biệt số nguyên với số thập phân chính xác, số gần đúng, chuỗi định danh, thời điểm tuyệt đối, JSON và payload nhị phân. Đồng thời thống nhất kiểu giữa các khóa, xác định NULL và collation, kiểm soát precision và timezone. Cuối cùng, kiểm tra kích thước vật lý và execution plan trên workload đại diện để cân bằng chi phí lưu trữ với khả năng tăng trưởng và bảo trì.
