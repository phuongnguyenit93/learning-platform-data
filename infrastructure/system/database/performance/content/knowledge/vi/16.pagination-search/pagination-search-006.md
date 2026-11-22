# Tìm kiếm kết hợp bộ lọc, sắp xếp và thiết kế chỉ mục

## Vì sao tìm kiếm cần được thiết kế như một đường truy cập hoàn chỉnh?

Một màn hình tìm kiếm thường kết hợp nhiều yêu cầu: giới hạn dữ liệu theo tenant hoặc người dùng, lọc theo trạng thái và danh mục, tìm theo từ khóa, sắp xếp theo thời gian hoặc mức độ liên quan, rồi chỉ trả về một trang nhỏ. Mỗi phần riêng lẻ có vẻ đơn giản, nhưng khi kết hợp, chúng quyết định số hàng phải đọc, số trang phải truy cập, lượng dữ liệu cần sắp xếp và chi phí duy trì chỉ mục.

Một truy vấn trả về 20 hàng không có nghĩa cơ sở dữ liệu chỉ đọc 20 hàng. Hệ quản trị có thể phải quét hàng trăm nghìn mục, lọc phần lớn dữ liệu, sắp xếp một tập lớn rồi mới lấy 20 hàng đầu. Khi người dùng chuyển sang trang sâu, OFFSET còn có thể buộc hệ quản trị đọc và bỏ qua tất cả hàng ở các trang trước.

Tối ưu tìm kiếm vì vậy phải nhìn đồng thời ba thành phần:

- **Bộ lọc (filter):** thu hẹp tập dữ liệu theo điều kiện nghiệp vụ và từ khóa.
- **Sắp xếp (sort):** xác định thứ tự ổn định, phù hợp với cách người dùng duyệt kết quả.
- **Phân trang (pagination):** giới hạn số hàng trả về và xác định vị trí tiếp tục.

Chỉ mục ghép (composite index) có thể hỗ trợ nhiều thành phần trong cùng một đường truy cập, nhưng thứ tự cột phải phù hợp với mẫu truy vấn. Không có một chỉ mục duy nhất tối ưu cho mọi tổ hợp bộ lọc và thứ tự sắp xếp. Cần dựa trên truy vấn phổ biến, độ chọn lọc, phân bố dữ liệu, execution plan và tải đọc/ghi thực tế.

Bài học này trình bày cách phân tích mẫu tìm kiếm, thiết kế chỉ mục ghép và chỉ mục bao phủ, lựa chọn OFFSET hoặc keyset pagination, xử lý từ khóa và bộ lọc tùy chọn, cũng như đo lường để xác nhận cải thiện.

## Mô hình hóa mẫu tìm kiếm trước khi tạo chỉ mục

### Xác định các điều kiện cố định và tùy chọn

Hãy ghi lại những điều kiện thường xuất hiện trong truy vấn:

- Điều kiện phạm vi dữ liệu luôn có, như tenant_id, organization_id hoặc owner_id.
- Điều kiện lọc thường gặp, như status, category_id, type hoặc created_at.
- Từ khóa tìm kiếm trên tên, mã, email hoặc nội dung.
- Điều kiện khoảng thời gian, giá trị số hoặc trạng thái hiệu lực.
- Thứ tự sắp xếp mặc định và các thứ tự người dùng có thể chọn.
- Kích thước trang, cách chuyển trang và yêu cầu nhảy đến trang bất kỳ.

Phân biệt điều kiện bắt buộc với điều kiện tùy chọn. Ví dụ tenant_id luôn được áp dụng, status có thể không được chọn, category_id có thể có một hoặc nhiều giá trị, còn keyword có thể rỗng. Những tổ hợp này tạo ra các hình dạng truy vấn khác nhau và có thể cần kế hoạch hoặc chỉ mục khác nhau.

### Xác định grain và tập kết quả

Trước khi tối ưu, xác định mỗi hàng kết quả đại diện cho một thực thể nào. Nếu truy vấn JOIN bảng sản phẩm với bảng ảnh hoặc bảng nhãn nhiều hàng cho mỗi sản phẩm, kết quả có thể bị nhân bản trước khi phân trang. Khi đó LIMIT 20 có thể trả về ít hơn 20 sản phẩm duy nhất hoặc làm các trang có nội dung lặp.

Nếu màn hình cần một hàng mỗi sản phẩm, hãy đảm bảo truy vấn giữ đúng grain trước khi phân trang. Có thể dùng EXISTS để kiểm tra sự tồn tại của nhãn, tổng hợp bảng con trước khi JOIN hoặc chọn một ảnh đại diện theo quy tắc xác định. Phân trang sau một JOIN làm nhân bản hàng sẽ tạo kết quả khó dự đoán.

### Lập ma trận truy vấn đại diện

Một ma trận nhỏ giúp tránh thiết kế chỉ mục theo một câu SQL đơn lẻ:

| Mẫu truy vấn | Bộ lọc | Thứ tự | Kiểu truy cập cần xem xét |
|---|---|---|---|
| Danh sách mặc định | tenant, status | created_at mới nhất | Chỉ mục ghép theo tenant/status/thời gian |
| Tìm theo danh mục | tenant, category, status | created_at mới nhất | Chỉ mục có category và thứ tự thời gian |
| Tra cứu mã chính xác | tenant, product_code | Không cần sort hoặc theo mã | Tìm kiếm bằng khóa duy nhất/ghép |
| Tìm tên theo tiền tố | tenant, name prefix | name tăng dần | B-tree phù hợp collation và prefix |
| Tìm kiếm toàn văn | tenant, nội dung | relevance hoặc ngày | Full-text/trigram và chiến lược sort phù hợp |
| Lọc khoảng thời gian | tenant, created_at range | created_at | Range scan trên thời gian |
| Trang sâu | Bộ lọc cố định | created_at, id | Keyset pagination nếu phù hợp |

Ma trận cần được xây dựng từ telemetry, query fingerprint hoặc trace thực tế. Không tối ưu một tổ hợp bộ lọc hiếm gặp nếu nó làm tăng đáng kể chi phí ghi và dung lượng chỉ mục trong khi truy vấn phổ biến vẫn chậm.

## Cách chỉ mục ghép hỗ trợ lọc và sắp xếp

### Nguyên tắc tiền tố trái của B-tree

Với chỉ mục B-tree ghép trên (A, B, C), nhiều hệ quản trị có thể tìm kiếm hiệu quả theo tiền tố trái: A, A kết hợp B, hoặc A kết hợp B và C. Điều kiện chỉ trên C thường không thể định vị một vùng liên tục bằng phần đầu của chỉ mục, dù một số optimizer có chiến lược bổ sung như skip scan.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC, order_id DESC);
~~~

Chỉ mục này có thể phù hợp với truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Khi tenant_id và status được cố định bằng phép so sánh bằng, các hàng trong vùng khóa tương ứng được sắp theo created_at và order_id. Hệ quản trị có thể đọc từ đầu vùng chỉ mục theo thứ tự mong muốn và dừng sau khi lấy đủ hàng, nếu kế hoạch và điều kiện thực tế cho phép.

Cú pháp giới hạn hàng khác nhau giữa hệ quản trị: PostgreSQL/MySQL thường dùng LIMIT, SQL Server dùng TOP hoặc OFFSET/FETCH, còn FETCH FIRST có ở một số sản phẩm. Ví dụ trên dùng cú pháp SQL chuẩn ở mức minh họa; hãy điều chỉnh theo hệ quản trị.

### Thứ tự cột không có quy tắc máy móc

Một quy tắc khởi đầu thường dùng là đặt các cột có điều kiện bằng trước cột phạm vi hoặc cột sắp xếp. Nhưng thứ tự cuối cùng phụ thuộc toàn bộ mẫu truy vấn:

- Các cột luôn được lọc bằng có thể đứng đầu để thu hẹp vùng chỉ mục.
- Cột dùng điều kiện khoảng thường ảnh hưởng khả năng sử dụng các cột phía sau để tiếp tục thu hẹp seek range.
- Cột ORDER BY cần nằm ở vị trí và chiều sắp xếp phù hợp để tránh sort.
- Nếu một bộ lọc tùy chọn bị bỏ qua, cột đó đứng trước cột sắp xếp có thể khiến chỉ mục không cung cấp thứ tự toàn cục cần thiết.
- Độ chọn lọc có ích để ước lượng lượng dữ liệu, nhưng không nên chỉ xếp cột theo độ chọn lọc cao nhất.

Ví dụ, chỉ mục (tenant_id, status, created_at) hỗ trợ tốt khi status luôn được cố định. Nếu status không được truyền, các hàng của tenant có thể được nhóm theo status trước rồi mới theo created_at; chỉ mục không nhất thiết trả về toàn bộ tenant theo created_at toàn cục mà không sort.

Nếu màn hình có hai mẫu phổ biến: lọc tenant/status rồi sắp xếp theo ngày, và lọc tenant rồi sắp xếp theo ngày bất kể status, có thể cần hai chỉ mục khác nhau hoặc một chiến lược truy vấn khác. Hãy đo tần suất và chi phí của cả hai trước khi quyết định.

### Điều kiện bằng, điều kiện khoảng và ORDER BY

Giả sử truy vấn có:

~~~sql
WHERE tenant_id = :tenant
  AND status = :status
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC, order_id DESC
~~~

Một chỉ mục ứng viên có thể là:

~~~sql
(tenant_id, status, created_at DESC, order_id DESC)
~~~

Hai cột đầu được cố định bằng; created_at dùng khoảng; order_id giúp thứ tự ổn định khi thời gian trùng. Tùy engine, chỉ mục có thể hỗ trợ cả phạm vi và thứ tự. Cần xác minh kế hoạch vì khả năng tận dụng các cột sau điều kiện range và hướng scan khác nhau giữa hệ quản trị.

Nếu ORDER BY dùng cột không có trong chỉ mục hoặc thứ tự cột không phù hợp, hệ quản trị có thể phải sort. Sort có thể tốn CPU, bộ nhớ và vùng lưu trữ tạm, đặc biệt khi bộ lọc không chọn lọc.

## Kết hợp từ khóa tìm kiếm với bộ lọc

### Tìm kiếm chính xác

Với mã định danh hoặc email chuẩn hóa, phép so sánh bằng thường dễ tận dụng B-tree:

~~~sql
SELECT product_id, product_code, product_name
FROM products
WHERE tenant_id = :tenant_id
  AND product_code = :product_code;
~~~

Nếu product_code chỉ duy nhất trong tenant, một unique index ghép trên (tenant_id, product_code) vừa hỗ trợ tìm kiếm vừa thể hiện ràng buộc dữ liệu. Ràng buộc UNIQUE cần phản ánh đúng quy tắc nghiệp vụ và cách xử lý NULL của hệ quản trị.

### Tìm kiếm theo tiền tố

Tìm kiếm prefix có dạng:

~~~sql
WHERE product_name LIKE 'wireless%'
~~~

Một B-tree có thể hỗ trợ tìm tiền tố trong những điều kiện nhất định, phụ thuộc collation, kiểu so sánh, operator class và hệ quản trị. Nếu collation hoặc cách so sánh không phù hợp, có thể cần cấu hình hoặc loại chỉ mục khác.

Tìm kiếm chứa chuỗi ở giữa hoặc cuối:

~~~sql
WHERE product_name LIKE '%wireless%'
~~~

thường không thể định vị hiệu quả bằng B-tree thông thường vì không có tiền tố cố định. Hệ quản trị có thể phải quét nhiều hàng hoặc dùng loại chỉ mục chuyên biệt như trigram, full-text hay search index.

Không thay đổi semantics tìm kiếm chỉ để dùng được B-tree. Tìm tiền tố và tìm chuỗi ở mọi vị trí là hai yêu cầu khác nhau.

### Tìm kiếm toàn văn và tìm kiếm gần đúng

Nếu người dùng tìm nhiều từ, cần stemming, xếp hạng mức độ liên quan hoặc tìm gần đúng, B-tree thông thường thường không phải công cụ phù hợp. Hãy xem xét:

- Full-text index cho tìm kiếm theo token, từ và cấu hình ngôn ngữ.
- Trigram hoặc index tương tự cho tìm kiếm chuỗi con và độ tương đồng nếu hệ quản trị hỗ trợ.
- Search engine chuyên dụng khi cần phân tích ngôn ngữ, ranking, gợi ý hoặc phân tán tải tìm kiếm lớn.

Các loại chỉ mục này có cách kết hợp filter và sort riêng. Có thể cần lọc tenant/status sau khi lấy ứng viên, hoặc dùng cấu trúc hỗ trợ filter metadata. Đánh giá số ứng viên, độ chính xác, độ trễ, chi phí đồng bộ và tính nhất quán dữ liệu.

### Chuẩn hóa chuỗi và collation

Nếu tìm kiếm không phân biệt hoa thường hoặc dấu, hãy xác định quy tắc nghiệp vụ và collation. Việc dùng LOWER(column) hoặc hàm chuẩn hóa trong WHERE có thể làm chỉ mục thông thường không được dùng như mong đợi. Có thể dùng expression index, generated column hoặc collation phù hợp nếu được hỗ trợ.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX ix_products_name_lower
ON products (lower(product_name));
~~~

Truy vấn cần dùng biểu thức tương thích. Expression index làm tăng chi phí ghi và dung lượng, vì vậy chỉ tạo khi workload chứng minh có lợi.

## Phân trang bằng OFFSET và LIMIT

### Cách hoạt động của OFFSET

Phân trang offset thường được viết:

~~~sql
SELECT product_id, product_name, created_at
FROM products
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, product_id DESC
LIMIT 50 OFFSET 5000;
~~~

Hệ quản trị cần tìm và bỏ qua khoảng 5.000 hàng đầu tiên theo thứ tự trước khi trả 50 hàng tiếp theo. Với offset lớn, chi phí có thể tăng theo độ sâu trang, dù có chỉ mục hỗ trợ thứ tự. Nếu truy vấn còn phải sort một tập lớn trước khi áp dụng LIMIT, chi phí còn cao hơn.

OFFSET phù hợp khi:

- Kết quả nhỏ hoặc số trang không sâu.
- Người dùng cần nhảy đến trang bất kỳ.
- Số lượng dữ liệu và độ trễ cho phép.
- Có yêu cầu giao diện hiển thị tổng số trang hoặc số bản ghi chính xác.

Nếu cần trang sâu trên bảng lớn, hãy đo thời gian ở nhiều offset, chẳng hạn trang đầu, trang 20, trang 200 và trang 2.000. Không suy ra hiệu năng trang sâu từ trang đầu.

### ORDER BY phải xác định duy nhất

Phân trang yêu cầu một thứ tự ổn định. Nếu chỉ ORDER BY created_at và nhiều hàng cùng timestamp, ranh giới trang có thể thay đổi giữa các lần chạy. Thêm khóa duy nhất làm tiêu chí phụ:

~~~sql
ORDER BY created_at DESC, product_id DESC
~~~

Khóa phụ giúp xác định thứ tự toàn phần. Nó không đảm bảo snapshot ổn định khi dữ liệu được thêm, xóa hoặc cập nhật giữa các yêu cầu trang; nhưng nó loại bỏ sự mơ hồ do các giá trị sort trùng nhau trong cùng trạng thái dữ liệu.

### Vấn đề khi dữ liệu thay đổi giữa các trang

Với OFFSET, nếu có hàng mới được chèn trước vị trí offset giữa hai lần lấy trang, một số hàng có thể bị lặp hoặc bị bỏ qua. Nếu hàng bị xóa, các vị trí cũng dịch chuyển.

Có thể dùng transaction với snapshot isolation cho một phiên duyệt cần tính nhất quán cao, nhưng giữ transaction mở lâu có thể tạo áp lực version store, MVCC cleanup hoặc khóa tùy hệ quản trị. Đối với API phân trang thông thường, cần xác định mức nhất quán chấp nhận được và tránh giữ transaction dài chỉ để người dùng lật trang.

## Keyset pagination (seek method)

### Ý tưởng

Keyset pagination dùng giá trị sắp xếp của hàng cuối trang trước làm cursor. Trang tiếp theo yêu cầu các hàng đứng sau cursor theo đúng thứ tự, thay vì bỏ qua một số lượng hàng lớn.

Với thứ tự giảm dần theo created_at và product_id, trang đầu:

~~~sql
SELECT product_id, product_name, created_at
FROM products
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, product_id DESC
LIMIT 50;
~~~

Giả sử hàng cuối có created_at = :last_created_at và product_id = :last_product_id. Trang tiếp theo:

~~~sql
SELECT product_id, product_name, created_at
FROM products
WHERE tenant_id = :tenant_id
  AND (
       created_at < :last_created_at
       OR (
           created_at = :last_created_at
           AND product_id < :last_product_id
       )
  )
ORDER BY created_at DESC, product_id DESC
LIMIT 50;
~~~

Điều kiện cursor khớp với thứ tự sắp xếp. Với thứ tự tăng dần, toán tử so sánh cần đảo chiều. Với nhiều cột sort, phải xây dựng điều kiện từ điển tương ứng, giữ đúng chiều ASC/DESC của từng cột.

Một số hệ quản trị hỗ trợ so sánh row-value như (created_at, product_id) < (:last_created_at, :last_product_id), nhưng khả năng dùng chỉ mục và hỗ trợ chiều sắp xếp hỗn hợp khác nhau. Dạng OR tường minh ở trên dễ hiểu hơn nhưng vẫn cần kiểm tra execution plan.

### Chọn khóa cursor ổn định

Cursor nên bao gồm toàn bộ cột ORDER BY cần để xác định thứ tự duy nhất. Nếu sort theo created_at DESC, product_id DESC thì cursor phải chứa cả hai giá trị. Chỉ lưu created_at có thể làm mất hoặc lặp hàng khi nhiều bản ghi cùng thời điểm.

Ưu tiên cột sort:

- Không NULL hoặc có quy tắc NULL rõ ràng.
- Ít thay đổi sau khi bản ghi được tạo.
- Có thể so sánh nhất quán giữa các lần gọi.
- Có chỉ mục hỗ trợ cùng bộ lọc và thứ tự.
- Không làm lộ dữ liệu nhạy cảm khi cursor được gửi qua API.

Nếu cột sort có thể thay đổi giữa các trang, một hàng có thể di chuyển qua ranh giới cursor. Với yêu cầu duyệt ổn định, hãy cân nhắc snapshot/version token hoặc dùng khóa sắp xếp bất biến.

### Keyset có những giới hạn nào?

Keyset pagination rất phù hợp cho nút “Tiếp theo” và luồng duyệt liên tục trên tập dữ liệu lớn. Tuy nhiên:

- Không thuận tiện để nhảy thẳng đến trang 500 nếu không có cursor tương ứng.
- Cần lưu hoặc gửi cursor của trang trước.
- Cursor phải được bảo vệ và gắn với bộ lọc, tenant và thứ tự đã dùng.
- Thay đổi bộ lọc hoặc sort phải tạo cursor mới.
- Dữ liệu thay đổi vẫn có thể ảnh hưởng tính nhất quán nếu không dùng snapshot hoặc quy tắc phù hợp.
- Điều kiện cursor phức tạp với nhiều cột ASC/DESC hoặc NULL cần được thiết kế cẩn thận.

Keyset giảm chi phí bỏ qua hàng ở trang sâu, nhưng không làm truy vấn miễn phí. Nếu bộ lọc rất ít chọn lọc hoặc từ khóa yêu cầu full-text ranking, hệ quản trị vẫn phải tìm và xếp hạng nhiều ứng viên.

## Thiết kế chỉ mục cho filter + sort + pagination

### Ví dụ danh sách sản phẩm

Giả sử bảng products có các cột:

- tenant_id: phạm vi dữ liệu.
- status: trạng thái sản phẩm.
- category_id: danh mục.
- created_at: thời điểm tạo.
- product_id: khóa duy nhất.
- product_name và price: dữ liệu hiển thị.

Màn hình phổ biến lọc theo tenant và status, tùy chọn category, sắp xếp mới nhất trước, mỗi trang 50 hàng.

Chỉ mục ứng viên cho truy vấn có category:

~~~sql
CREATE INDEX ix_products_tenant_status_category_created
ON products (
    tenant_id,
    status,
    category_id,
    created_at DESC,
    product_id DESC
);
~~~

Chỉ mục này phù hợp khi ba điều kiện đầu được cố định bằng và truy vấn cần thứ tự theo thời gian trong phạm vi đó. Nếu category là tùy chọn, chỉ mục có category đứng trước created_at có thể không cung cấp thứ tự toàn cục theo created_at cho truy vấn bỏ category.

Một chỉ mục khác cho danh sách không lọc category có thể là:

~~~sql
CREATE INDEX ix_products_tenant_status_created
ON products (
    tenant_id,
    status,
    created_at DESC,
    product_id DESC
);
~~~

Hai chỉ mục có chi phí lưu trữ và duy trì riêng. Không tạo cả hai nếu workload hiếm hoặc chi phí ghi quá cao. Dùng query stats để xác định tổ hợp nào chiếm nhiều thời gian và lượt gọi.

### Chỉ mục bao phủ (covering index)

Nếu truy vấn chỉ trả về product_id, created_at, product_name và price, có thể cân nhắc bao phủ các cột này để giảm truy xuất về bảng. Cách khai báo phụ thuộc hệ quản trị. Ví dụ PostgreSQL:

~~~sql
CREATE INDEX ix_products_tenant_status_created_cover
ON products (tenant_id, status, created_at DESC, product_id DESC)
INCLUDE (product_name, price);
~~~

INCLUDE giữ các cột bổ sung ở phần payload của chỉ mục trong PostgreSQL và SQL Server, với cú pháp/giới hạn khác nhau. MySQL có cách thiết kế covering index dựa trên việc các cột cần thiết đều nằm trong chỉ mục; không dùng cú pháp INCLUDE như thể mọi hệ quản trị đều hỗ trợ.

Chỉ mục bao phủ giúp giảm lookup trong một số tình huống nhưng làm chỉ mục rộng hơn. Cột product_name có thể dài; đưa nhiều cột lớn vào chỉ mục có thể làm tăng dung lượng, giảm số trang trong cache và tăng chi phí INSERT/UPDATE/DELETE. Chỉ đưa cột cần thiết và có lợi ích đo được vào chỉ mục.

### Chỉ mục cho nhiều kiểu sort

Nếu người dùng được chọn sắp xếp theo created_at, price hoặc product_name, một chỉ mục không thể tối ưu mọi thứ. Có thể cần:

- Một chỉ mục cho thứ tự mặc định phổ biến.
- Một chỉ mục riêng cho sort theo giá nếu tần suất và độ trễ đáng kể.
- Chấp nhận sort cho các lựa chọn hiếm.
- Giới hạn các tùy chọn sort để tránh tạo quá nhiều chỉ mục.

Không cho phép client truyền tên cột hoặc hướng sort tùy ý vào SQL. Hãy ánh xạ các lựa chọn được hỗ trợ sang danh sách cột cố định trong ứng dụng để tránh SQL injection và để kiểm soát workload.

## Bộ lọc tùy chọn và truy vấn động

### Mẫu điều kiện OR cho tham số tùy chọn

Một mẫu thường gặp:

~~~sql
WHERE tenant_id = :tenant_id
  AND (:status IS NULL OR status = :status)
  AND (:category_id IS NULL OR category_id = :category_id)
~~~

Cách viết này tiện cho ứng dụng, nhưng các điều kiện OR kết hợp tham số NULL có thể làm optimizer khó ước lượng và chọn đường truy cập tối ưu cho mọi trường hợp. Một kế hoạch phù hợp khi status được truyền có thể không phù hợp khi status là NULL.

Các lựa chọn:

- Tạo các hình dạng truy vấn riêng cho những tổ hợp filter phổ biến.
- Dùng dynamic SQL có tham số hóa, chỉ thêm điều kiện thực sự được chọn.
- Dùng stored procedure hoặc cơ chế của hệ quản trị để hỗ trợ recompilation khi có bằng chứng parameter sensitivity.
- Giữ một truy vấn chung nếu optimizer xử lý tốt và đo cho thấy đủ hiệu quả.

Dynamic SQL phải dùng bind parameter cho giá trị. Chỉ tên cột và hướng sort được ánh xạ từ whitelist cố định; không nối trực tiếp dữ liệu người dùng vào chuỗi SQL.

### Parameter sniffing và độ chọn lọc

Một tham số có thể khớp 5 hàng, tham số khác khớp 500.000 hàng. Kế hoạch được tối ưu dựa trên một giá trị tham số hoặc thống kê có thể không phù hợp cho mọi lần chạy. Đây là vấn đề parameter sensitivity/parameter sniffing ở một số hệ quản trị.

Khi thấy cùng fingerprint có độ trễ biến động mạnh theo tham số:

- So sánh kế hoạch và số hàng thực tế của các nhóm giá trị.
- Kiểm tra histogram và dữ liệu skew.
- Xem query store hoặc thống kê kế hoạch nếu hệ quản trị hỗ trợ.
- Cân nhắc tách query shape, cập nhật thống kê hoặc dùng cơ chế tối ưu tham số phù hợp.
- Không ép một kế hoạch cố định trước khi hiểu các nhóm cardinality.

## Đếm tổng số kết quả và lấy trang tiếp theo

### COUNT(*) có thể là một truy vấn tốn kém riêng

Giao diện thường muốn hiển thị “1–50 trên 125.430 kết quả”. Để có con số chính xác, ứng dụng có thể chạy COUNT(*) với cùng điều kiện filter. Truy vấn đếm có thể phải quét nhiều hàng hoặc chỉ mục, dù truy vấn trang chỉ lấy 50 hàng đầu tiên.

Không nhất thiết phải đếm chính xác ở mọi lần tải. Tùy trải nghiệm, có thể:

- Chỉ hiển thị nút “Có trang tiếp theo”.
- Lấy page_size + 1 hàng để biết còn dữ liệu.
- Hiển thị số lượng ước lượng hoặc kết quả đếm được cache.
- Chỉ đếm chính xác khi người dùng yêu cầu.
- Dùng thống kê hoặc bảng tổng hợp nếu nghiệp vụ chấp nhận độ trễ cập nhật.

Nếu cần count chính xác, đo riêng truy vấn count và xem chỉ mục có hỗ trợ điều kiện lọc hay không. Không mặc định nó rẻ chỉ vì không trả về cột dữ liệu.

### Lấy thêm một hàng để biết còn trang tiếp theo

Một cách phổ biến là yêu cầu page_size + 1 hàng. Nếu trang có 51 hàng khi page_size là 50, ứng dụng trả 50 hàng đầu và đánh dấu has_more = true. Hàng thứ 51 chỉ dùng để xác định còn kết quả.

Với keyset, truy vấn vẫn bắt đầu sau cursor của trang trước và giới hạn 51 hàng. Cách này thường tránh được COUNT(*) trên toàn bộ tập kết quả.

## Những lỗi hiệu năng và tính đúng đắn thường gặp

- **Chỉ mục không khớp bộ lọc:** truy vấn phải đọc nhiều hàng rồi mới loại bỏ.
- **Chỉ mục có cột tùy chọn đứng trước sort key:** khi bỏ bộ lọc đó, thứ tự toàn cục có thể không còn phù hợp.
- **ORDER BY không duy nhất:** các trang có thể lặp hoặc bỏ sót hàng ngay cả khi dữ liệu ít thay đổi.
- **OFFSET sâu:** hệ quản trị phải đi qua và bỏ qua nhiều hàng trước khi trả trang cần lấy.
- **JOIN làm nhân bản hàng trước LIMIT:** trang có ít thực thể duy nhất hơn dự kiến.
- **LIKE có wildcard đầu:** B-tree thông thường thường không thể định vị theo tiền tố.
- **Hàm trên cột hoặc implicit conversion:** làm giảm khả năng sử dụng chỉ mục.
- **SELECT *:** đọc và truyền nhiều dữ liệu không cần thiết, làm chỉ mục bao phủ khó hơn.
- **COUNT(*) luôn chạy cùng truy vấn trang:** tạo thêm chi phí dù giao diện không cần số chính xác.
- **Quá nhiều chỉ mục:** tăng thời gian ghi, dung lượng, cache pressure và bảo trì.
- **Không kiểm tra nhiều giá trị tham số:** một kế hoạch tốt cho tenant nhỏ có thể rất kém cho tenant lớn.
- **Cursor không gắn với filter/sort:** trang tiếp theo có thể tiếp tục từ một vị trí không còn tương thích với truy vấn.

## Quy trình đo và kiểm chứng

Khi tối ưu một màn hình tìm kiếm, hãy thực hiện theo các bước:

1. **Thu thập workload.** Ghi query fingerprint, tần suất, bộ lọc được chọn, giá trị tham số đại diện, kích thước trang và độ sâu trang.
2. **Xác định SLI.** Đo p50/p95/p99, timeout, throughput và tỷ lệ truy vấn thành công; tách truy vấn trang khỏi truy vấn count.
3. **Lấy baseline.** Ghi execution plan, estimated/actual rows, logical reads, physical/buffer reads, CPU, elapsed time, sort và spill.
4. **Phân tích selectivity.** Xác định bộ lọc nào thu hẹp dữ liệu nhiều nhất, dữ liệu có skew hay không và tham số nào gây kế hoạch khác biệt.
5. **Kiểm tra thứ tự.** Xác định ORDER BY có duy nhất không, có khớp tiền tố chỉ mục không và có phát sinh sort không.
6. **So sánh pagination.** Đo trang đầu và trang sâu bằng OFFSET; so sánh với keyset trên cùng điều kiện và thứ tự.
7. **Đề xuất chỉ mục theo query shape.** Xem xét composite index, covering index, full-text/trigram hoặc expression index khi phù hợp.
8. **Thử một thay đổi chính.** Dùng dữ liệu và workload đại diện, giữ các điều kiện đo tương đương.
9. **Kiểm tra tác động phụ.** Đo INSERT/UPDATE/DELETE, dung lượng chỉ mục, cache, lock wait và các truy vấn khác.
10. **Theo dõi sau triển khai.** Quan sát đủ giờ cao điểm và nhóm tham số khác nhau để phát hiện hồi quy.

Không kết luận chỉ từ việc kế hoạch đổi từ Scan sang Seek. Hãy xem số hàng đọc, số trang, sort, thời gian, CPU và độ trễ thực tế. Một Index Seek trả về hàng trăm nghìn mục vẫn có thể đắt hơn một scan tuần tự.

## Ví dụ tổng hợp: danh sách đơn hàng có lọc và phân trang

Giả sử API hiển thị đơn hàng trong một tenant, cho phép lọc status, sắp xếp mới nhất trước và tải từng trang 50 hàng. Truy vấn có dạng:

~~~sql
SELECT order_id, status, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Một chỉ mục ứng viên:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC, order_id DESC);
~~~

Trang tiếp theo dùng cursor:

~~~sql
SELECT order_id, status, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
       created_at < :last_created_at
       OR (
           created_at = :last_created_at
           AND order_id < :last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Nếu status tùy chọn, truy vấn không có status có thể cần chỉ mục khác bắt đầu bằng tenant_id rồi đến created_at và order_id. Quyết định dựa trên tỷ lệ sử dụng filter và chi phí tổng thể. Nếu một tenant có lượng đơn lớn hơn nhiều tenant khác, cần kiểm tra skew và kế hoạch cho cả hai nhóm.

Sau khi thay đổi, so sánh:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| p95 trang đầu | 180 ms | 42 ms |
| p95 trang sâu | 1.250 ms | 55 ms |
| Logical reads | 24.000 | 1.100 |
| Rows read để trả 50 hàng | 80.000 | 52 |
| Sort spill | Có | Không |
| Chi phí ghi | Baseline | Tăng do chỉ mục mới |

Các số liệu chỉ minh họa cách trình bày. Cần đo thực tế với nhiều tenant, trạng thái, thời điểm, kích thước trang và mức tải. Nếu dữ liệu thay đổi giữa các lần gọi, hãy kiểm tra tính nhất quán và hành vi của cursor; nếu dùng full-text ranking, cần đánh giá riêng cách phân trang theo điểm relevance.

## Checklist thiết kế tìm kiếm và phân trang

- [ ] Xác định các query shape phổ biến và bộ lọc bắt buộc/tùy chọn.
- [ ] Xác định grain kết quả để JOIN không nhân bản thực thể trước phân trang.
- [ ] Chọn thứ tự sort ổn định, có khóa duy nhất làm tie-breaker.
- [ ] Kiểm tra tiền tố trái và thứ tự cột của composite index.
- [ ] Đánh giá điều kiện bằng, điều kiện khoảng và khả năng cung cấp ORDER BY.
- [ ] Chọn B-tree, full-text, trigram hoặc expression index theo loại tìm kiếm.
- [ ] Kiểm tra collation, kiểu tham số và SARGability.
- [ ] So sánh OFFSET với keyset cho các trang sâu.
- [ ] Bảo đảm cursor gắn với filter, sort và phạm vi tenant.
- [ ] Cân nhắc page_size + 1 thay cho COUNT(*) chính xác khi phù hợp.
- [ ] Chỉ thêm cột bao phủ khi lợi ích đọc lớn hơn chi phí ghi và lưu trữ.
- [ ] Đo p95/p99, rows read, logical reads, sort, spill và tác động workload ghi.
- [ ] Kiểm chứng kết quả dữ liệu và tính ổn định giữa các trang.

Thiết kế tìm kiếm hiệu quả không chỉ là tạo một chỉ mục cho từng cột lọc. Cần hiểu tổ hợp bộ lọc, thứ tự sắp xếp và cách phân trang mà ứng dụng thực sự sử dụng. Chỉ mục ghép phù hợp có thể giúp hệ quản trị định vị đúng vùng dữ liệu, trả kết quả theo thứ tự và dừng sớm; keyset pagination giúp tránh chi phí bỏ qua hàng ở trang sâu. Kết hợp execution plan với số liệu tải và kiểm chứng tính đúng đắn sẽ giúp cải thiện độ trễ mà vẫn kiểm soát chi phí ghi, dung lượng và độ phức tạp vận hành.