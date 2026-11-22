# Sort cost control — Kiểm soát chi phí sắp xếp

## 1. Vì sao sắp xếp là một ranh giới bảo vệ nghiệp vụ?

Một API tra cứu có thể không sửa bản ghi nào nhưng vẫn làm gián đoạn hoạt động kinh doanh. Người dùng được quyền xem hóa đơn có thể yêu cầu sắp xếp theo số dòng hàng, tổng tiền chưa đối soát hoặc lần cập nhật gần nhất của các giao dịch liên quan. Nếu mỗi lần mở trang buộc hệ thống đọc hàng triệu dòng, kết hợp nhiều bảng rồi mới chọn 25 kết quả, một tài khoản hợp lệ cũng có thể chiếm phần lớn tài nguyên phục vụ những người dùng khác.

**Sort cost control** là tập hợp quy tắc xác định yêu cầu sắp xếp nào được phép thực thi trong một ngân sách tài nguyên cụ thể, ở thời điểm nào và dưới giới hạn đồng thời nào. Bảo vệ này gắn trực tiếp với các cam kết nghiệp vụ: nhân viên vẫn tra cứu được công việc của mình, tenant lớn không làm tenant khác mất khả năng sử dụng, chức năng xuất báo cáo không chiếm toàn bộ năng lực giao dịch trực tuyến.

Ví dụ xuyên suốt bài là một hệ thống hóa đơn nhiều tenant. Người dùng chỉ được xem hóa đơn trong các đơn vị được cấp quyền. Màn hình tương tác hỗ trợ một số kiểu sort đã định nghĩa; báo cáo tổng hợp lớn có luồng xuất riêng. Các giới hạn số học trong bài chỉ minh họa cách xây dựng chính sách, cần được hiệu chỉnh bằng tải, dữ liệu và mục tiêu dịch vụ thực tế.

Ba câu hỏi phải được trả lời riêng:

1. Chủ thể này có quyền tra cứu tập đối tượng đó không?
2. Kiểu sort này có đúng ý nghĩa và được công bố cho chức năng đó không?
3. Công việc tạo ra bởi tổ hợp phạm vi, bộ lọc, sort và phân trang có nằm trong ngân sách được cấp không?

Trả lời đúng hai câu đầu chưa đủ cho câu thứ ba. Một trường sort nằm trong allowlist vẫn có thể rất đắt trên một tenant có dữ liệu lớn hoặc với một bộ lọc ít chọn lọc.

## 2. Mô hình lạm dụng: yêu cầu hợp lệ, công việc không được khống chế

Giả sử màn hình hóa đơn nhận yêu cầu:

```http
GET /api/invoices?sort=unreconciledAmount,desc&pageSize=25
```

`unreconciledAmount` là trường nghiệp vụ được phép hiển thị cho người dùng này. Tuy nhiên, backend tính trường đó bằng cách cộng các bút toán chưa đối soát của mọi hóa đơn trong phạm vi được xem. Không có bộ lọc thời gian bắt buộc, nên chi phí một trang có thể tương đương một báo cáo toàn kỳ.

Kẻ lạm dụng không cần gửi cú pháp SQL. Họ thay đổi khoảng thời gian, luân phiên các kiểu sort và mở nhiều yêu cầu đồng thời. Những yêu cầu đều khác cache key nên cache ít giúp ích. Sau khi gateway trả timeout, họ gửi lại; truy vấn cũ ở DB có thể vẫn đang chạy nếu ứng dụng chỉ ngừng chờ kết quả.

Chuỗi khuếch đại điển hình:

```text
Tài khoản hợp lệ
  -> chọn sort cần tổng hợp nhiều dữ liệu
  -> bỏ bộ lọc giúp thu hẹp tập ứng viên
  -> phát nhiều request hoặc nhiều mục trong một batch
  -> HTTP hết hạn nhưng công việc DB chưa kết thúc
  -> retry tạo thêm công việc
  -> pool kết nối, CPU hoặc I/O bị chiếm
  -> các luồng nghiệp vụ khác chậm hoặc thất bại
```

Tài sản cần bảo vệ gồm năng lực xử lý dùng chung, quyền truy cập dữ liệu, tính đúng đắn của tập kết quả và khả năng hoàn tất những nghiệp vụ quan trọng. Bảo vệ chi phí không được làm sai ba tài sản còn lại: không bỏ điều kiện tenant, không bỏ kiểm tra quyền và không trả một trang rỗng giả tạo để che timeout.

Một tình huống có thể xuất phát từ màn hình được viết chưa tốt hoặc người dùng vô tình mở nhiều tab. Cơ chế bảo vệ nên phản ứng theo công việc và ngân sách thực tế, không phụ thuộc vào việc suy đoán ý định của người gửi.

## 3. Nhận diện toàn bộ chi phí của một trang đã sắp xếp

Số dòng trả về là giới hạn đầu ra, không phải thước đo đầy đủ của công việc đầu vào. Khi xem xét một truy vấn, cần lần theo các bước trước và sau `ORDER BY`.

| Thành phần | Câu hỏi cần đặt ra | Ví dụ làm tăng chi phí |
|---|---|---|
| Xác định tập được xem | Phạm vi tenant, đơn vị và quyền đối tượng được áp dụng thế nào? | Kiểm tra quan hệ quyền trên tập ứng viên rất lớn |
| Tìm ứng viên | Có thể tìm đến vùng dữ liệu cần thiết không? | Bộ lọc rất rộng hoặc ít bản ghi khớp trong vùng phải duyệt |
| Join và tổng hợp | Mỗi đối tượng có bao nhiêu dòng liên quan? | Một hóa đơn có hàng nghìn bút toán |
| Tính khóa sort | Giá trị có sẵn hay phải tính lại? | Tổng có điều kiện, biểu thức văn bản, truy vấn con |
| Sắp thứ tự | Có đường đọc đúng thứ tự hay phải sort? | Sort tập trung sau khi kết hợp dữ liệu |
| Phân trang | Phải bỏ qua bao nhiêu ứng viên? | Offset sâu hoặc cursor không có đường truy cập phù hợp |
| Dựng phản hồi | Có nạp thêm dữ liệu hoặc đếm tổng không? | N+1, `totalCount`, facets và DTO quá rộng |
| Hủy và dọn dẹp | Khi hết hạn, công việc còn giữ gì? | Truy vấn đang chạy, transaction chưa rollback, kết nối chưa trả |

Có thể dùng mô hình tư duy:

```text
Chi phí request
  = xác thực/phân quyền + tìm ứng viên + join/tính khóa + sort
  + phân trang + metadata + dựng phản hồi + dọn dẹp
```

Đây không phải công thức cộng được trực tiếp thành mili giây. Nó giúp tránh tối ưu riêng bước sort rồi bỏ sót phần tổng hợp, số lượng truy vấn hoặc thời gian chờ kết nối.

Trong PostgreSQL, index phù hợp có thể cung cấp thứ tự cho `ORDER BY ... LIMIT`; khi phải sort tường minh, hệ thống vẫn có thể phải xét tập dữ liệu đủ điều kiện để tìm những dòng đầu. Vì vậy, `LIMIT 25` không bảo đảm chỉ xử lý 25 dòng. [PostgreSQL: Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html)

Một thuật toán giữ top-N có thể giảm lượng dữ liệu phải giữ để sắp thứ tự, nhưng không tự loại bỏ công việc đọc ứng viên hay tính khóa sort cho chúng. Cần phân biệt giảm bộ nhớ của bước chọn top-N với giới hạn tổng công việc của request.

## 4. Viết bất biến trước khi đặt các con số giới hạn

Bất biến giúp xác định hành vi phải đúng ngay cả khi bộ tối ưu chọn kế hoạch khác hoặc dữ liệu tăng nhiều lần.

- **Phạm vi dữ liệu bất biến:** mọi truy vấn chính, truy vấn đếm, cache và export chỉ sử dụng phạm vi được cấp quyền cho chủ thể hiện tại.
- **Chi phí do server quyết định:** client không được tự khai báo yêu cầu là rẻ, đổi lớp ưu tiên hoặc nâng trần tài nguyên bằng tham số.
- **Ngân sách bao trùm request:** thời gian chờ, truy vấn phụ và dựng phản hồi không được âm thầm nhận lại một ngân sách đầy đủ cho mỗi bước.
- **Số công việc đang chạy có giới hạn:** giới hạn đồng thời phản ánh công việc thực sự còn sử dụng tài nguyên, kể cả sau khi phía HTTP đã ngừng chờ.
- **Thất bại có ý nghĩa rõ ràng:** quá ngân sách không được biến thành thành công với tập dữ liệu thiếu hoặc thứ tự khác mà hợp đồng không cho phép.
- **Từ chối không tạo đường vòng:** một sort đắt bị chặn không được tự động chạy lại dưới tài khoản hệ thống hay bỏ bộ lọc để dùng kế hoạch nhanh hơn.

Quyền quản trị có thể cho phép phạm vi dữ liệu lớn hơn, nhưng không đồng nghĩa với tài nguyên vô hạn. Nếu cần hỗ trợ một luồng đặc biệt, server cấp một hồ sơ ngân sách rõ ràng, giới hạn tác vụ và điều kiện sử dụng của hồ sơ đó.

Ví dụ bất biến có thể kiểm chứng:

> Một yêu cầu tra cứu tương tác chỉ được thực thi sau khi có slot phù hợp; mọi SQL của yêu cầu giữ nguyên phạm vi phân quyền; khi hết hạn, hệ thống không khởi tạo thêm truy vấn lấy dữ liệu và không trả slot đang chạy trước khi công việc DB kết thúc hoặc được chuyển sang cơ chế dọn dẹp có kiểm soát.

Bất biến này mạnh hơn việc đặt một timeout ở controller. Nó mô tả cả điều kiện bắt đầu lẫn điều kiện kết thúc công việc.

## 5. Biến kiểu sort thành một kế hoạch có chính sách chi phí

Allowlist nên ánh xạ tên công khai sang một kế hoạch do server sở hữu. Kế hoạch chứa thứ tự SQL cố định hoặc cấu trúc truy vấn đã kiểm soát, ý nghĩa nghiệp vụ, điều kiện dùng và hồ sơ ngân sách. Không nhận SQL, tên hàm hoặc nhãn chi phí từ client.

| Mã kế hoạch minh họa | Cách lấy khóa | Điều kiện dùng trên màn hình tương tác | Hướng xử lý khi ngoài điều kiện |
|---|---|---|---|
| `CREATED_DESC_V1` | Thời điểm tạo và ID | Phạm vi hợp lệ, page size hữu hạn | Từ chối yêu cầu phân trang vượt hợp đồng |
| `DUE_DATE_ASC_V1` | Ngày đến hạn và ID | Bộ lọc trạng thái/ngày theo hồ sơ đã đo | Yêu cầu thu hẹp điều kiện |
| `UNRECONCILED_DESC_V2` | Tổng hợp bút toán | Chỉ phạm vi và khoảng thời gian đã được đánh giá | Đề xuất luồng export được cấp quyền |
| `LAST_ACTIVITY_DESC_V1` | Read model đã cập nhật | Chấp nhận độ trễ dữ liệu đã công bố | Từ chối nếu chức năng cần dữ liệu tức thời |

Có thể gắn nhãn nội bộ như `INDEXED_KEYSET`, `FILTERED_SORT`, `AGGREGATE_SORT` để phân nhóm công việc. Đây là phân loại chính sách của ứng dụng, không phải cam kết rằng optimizer luôn dùng index hoặc luôn giữ cùng một kế hoạch vật lý.

Điều kiện chi phí phải xét tổ hợp đầu vào. Sort theo ngày trên một đơn vị nhỏ khác với cùng sort đó trên toàn bộ hàng nghìn đơn vị mà một người quản trị được xem. Bộ lọc `status=OPEN` cũng có thể rất hẹp ở tenant này và bao phủ phần lớn dữ liệu ở tenant khác.

Không chỉ đếm số trường trong `ORDER BY`. Một trường tính từ nhiều bảng có thể đắt hơn ba cột có sẵn. Ngược lại, mở thêm một tổ hợp chiều sort có thể phá khả năng dùng thứ tự của index dù từng trường riêng lẻ đều hợp lệ.

Khi thay đổi cách tính hoặc chiến lược truy vấn, cập nhật phiên bản kế hoạch và đo lại. Tên trường công khai có thể giữ nguyên trong khi chi phí và điều kiện sử dụng cần thay đổi có kiểm soát.

## 6. Giới hạn hình dạng yêu cầu trước khi chiếm tài nguyên đắt

Một hồ sơ tra cứu tương tác có thể quy định như sau:

| Thuộc tính | Giá trị minh họa | Mục đích |
|---|---|---|
| Page size | Mặc định 25, tối đa 100 | Giới hạn dữ liệu dựng và truyền cho một trang |
| Số khóa sort do client chọn | Tối đa 2 trong tổ hợp đã hỗ trợ | Tránh tổ hợp không được đánh giá |
| Phân trang sâu | Dùng cursor; offset chỉ cho vùng nông đã định nghĩa | Hạn chế công việc bỏ qua kết quả |
| Sort tổng hợp trực tuyến | Bắt buộc khoảng thời gian hữu hạn và phạm vi phù hợp | Hạn chế tập ứng viên cần tính |
| Deadline toàn request | 1.200 ms | Bao gồm thời gian chờ và xử lý |
| Trần một statement lấy dữ liệu | 750 ms, đồng thời không vượt thời gian còn lại | Chặn một truy vấn chiếm dụng kéo dài |
| Chờ admission | Tối đa 150 ms và không vượt deadline còn lại | Giữ hàng chờ hữu hạn |
| Ngân sách dọn dẹp dự kiến | 100 ms trong kế hoạch thời gian | Dành dư địa cho kết thúc và xử lý phản hồi |

Các giá trị trên không phải cấu hình khuyến nghị dùng nguyên trạng. Hồ sơ chỉ có ý nghĩa nếu đã xem xét mức tải, khả năng hủy, thời gian dọn dẹp và hành vi của database/driver đang dùng. Khoảng dự phòng dọn dẹp cũng không phải lời hứa rằng mọi sự cố mạng sẽ được xử lý xong trong đúng 100 ms.

Validator cần từ chối số âm, số vượt miền, giá trị quá lớn, trùng khóa mâu thuẫn và cú pháp không hỗ trợ. Đặc biệt, không để `pageSize=0`, `-1`, `null` hoặc tràn số trở thành quy ước ngầm “không giới hạn”. Nếu dùng cách lấy thêm một dòng để xác định `hasNext`, chỉ tính `pageSize + 1` sau khi đã xác nhận miền giá trị nhỏ và hữu hạn.

Giới hạn độ rộng phạm vi phải được áp dụng sau khi giải quyết quyền. Không tin `tenantId`, danh sách đơn vị hoặc vai trò do client khai báo. Khi một người dùng được phép xem nhiều đơn vị nhưng hồ sơ tương tác chỉ phục vụ một phần phạm vi, trả lỗi yêu cầu chọn phạm vi hẹp hơn; không âm thầm cắt bớt đơn vị rồi trình bày kết quả như đầy đủ.

Việc chuẩn hóa tham số giúp các biểu diễn tương đương đi vào cùng một chính sách. Tuy nhiên, không dùng chuẩn hóa để bỏ một điều kiện ảnh hưởng ý nghĩa hoặc quyền truy cập chỉ vì điều kiện đó làm truy vấn chậm.

## 7. Thiết kế đường truy cập phù hợp với phạm vi được phép

Giả sử mỗi hóa đơn có `tenant_id`, `org_unit_id`, `created_at` và `id`, trong đó hai khóa cuối không null. Một truy vấn trang tiếp theo cho đúng một đơn vị có thể có dạng:

```sql
SELECT i.id, i.created_at, i.invoice_number, i.total_amount
FROM invoice i
WHERE i.tenant_id = :tenant_id
  AND i.org_unit_id = :org_unit_id
  AND EXISTS (
      SELECT 1
      FROM actor_unit_permission p
      WHERE p.tenant_id = i.tenant_id
        AND p.org_unit_id = i.org_unit_id
        AND p.actor_id = :actor_id
        AND p.can_read_invoice = TRUE
  )
  AND (i.created_at, i.id) < (:cursor_created_at, :cursor_id)
ORDER BY i.created_at DESC, i.id DESC
LIMIT :fetch_size;
```

Ở đây các giá trị được bind, `actor_id` và tenant lấy từ ngữ cảnh tin cậy, còn `fetch_size` đã bị chặn bởi hợp đồng. Trang đầu dùng một mẫu truy vấn đã định nghĩa không có điều kiện cursor. Các điều kiện trạng thái, thời gian hoặc quyền đối tượng bổ sung của sản phẩm vẫn phải được giữ nguyên trong cả hai mẫu.

Một index ứng viên để đánh giá:

```sql
CREATE INDEX invoice_tenant_unit_created_id_idx
    ON invoice (tenant_id, org_unit_id, created_at DESC, id DESC);
```

Đây là ví dụ thiết kế, không phải chỉ dẫn chạy DDL trên hệ thống đang hoạt động. Nó cần được đánh giá cùng kích thước index, chi phí ghi, phân bố dữ liệu và các điều kiện phân quyền thực tế. Truy vấn quyền cũng cần đường truy cập thích hợp; index trên hóa đơn không tự giải quyết mọi chi phí trong `EXISTS`.

Nếu thay điều kiện một đơn vị bằng `org_unit_id = ANY(:unit_ids)`, không được suy ra index trên tự cung cấp một luồng toàn cục đã sắp theo `created_at`. Thành phần `org_unit_id` đứng trước tạo nhiều nhóm thứ tự; việc gộp kết quả giữa các nhóm có thể cần công việc bổ sung. Đo riêng truy vấn một đơn vị, nhiều đơn vị và phạm vi rất rộng.

Cursor cần gắn với tenant, phạm vi quyền, bộ lọc, kế hoạch sort và phiên bản thích hợp để không thể tái sử dụng sang ngữ cảnh khác. Dùng ID làm khóa phân xử giúp thứ tự xác định hơn khi thời điểm tạo trùng nhau. Nếu có giá trị null, cần định nghĩa thứ tự null và điều kiện tiếp diễn tương ứng thay vì áp dụng nguyên xi phép so sánh tuple trên.

Keyset pagination có thể giảm công việc của offset sâu khi đường truy cập phù hợp. Nó không chứng minh số dòng được xét là hữu hạn nhỏ trong mọi tình huống: điều kiện quyền ít khớp, khóa tính toán hay bộ lọc bất lợi vẫn có thể làm một trang rất đắt.

## 8. Kiểm soát sort dựa trên join, tổng hợp và read model

Xét kiểu sort theo tiền chưa đối soát:

```sql
SELECT i.id, SUM(e.unreconciled_amount) AS outstanding
FROM invoice i
JOIN ledger_entry e
  ON e.tenant_id = i.tenant_id
 AND e.invoice_id = i.id
WHERE i.tenant_id = :tenant_id
  AND i.org_unit_id = :authorized_unit_id
  AND i.created_at >= :from_time
  AND i.created_at < :to_time
  -- Các điều kiện quyền đối tượng thực tế phải nằm trong truy vấn.
GROUP BY i.id
ORDER BY outstanding DESC, i.id DESC
LIMIT :fetch_size;
```

Đoạn SQL chỉ làm rõ nơi phát sinh công việc, chưa phải repository hoàn chỉnh. Trước khi lấy top-N, hệ thống có thể phải đọc và cộng nhiều bút toán. Số hóa đơn trả về không phản ánh số bút toán đã xử lý. Cũng cần xác định ý nghĩa của hóa đơn không có bút toán, tiền âm, tiền tệ khác nhau và dữ liệu đang được cập nhật; tối ưu chi phí không được làm đổi các quy tắc này.

Có ba hướng thường cần cân nhắc:

1. Thu hẹp tập ứng viên bằng điều kiện nghiệp vụ có ý nghĩa, chẳng hạn một kỳ kế toán và một đơn vị đã chọn.
2. Duy trì tổng được tính sẵn hoặc read model để phục vụ chính kiểu tra cứu này.
3. Chuyển nhu cầu báo cáo lớn sang một tác vụ nền có quyền và ngân sách riêng.

Read model cần định nghĩa độ trễ, cơ chế cập nhật, khôi phục khi sai lệch và quan hệ với quyền truy cập hiện tại. Một bảng tổng hợp nhanh nhưng chỉ được phân vùng theo tenant chưa đủ nếu quyền đọc hóa đơn còn phụ thuộc đơn vị hay chủ sở hữu.

Không giới hạn trước một tập 1.000 hóa đơn theo ngày rồi sort theo tiền chưa đối soát nếu hợp đồng yêu cầu top hóa đơn trên toàn phạm vi. Cách làm đó thay bài toán và có thể trả sai kết quả. Nếu sản phẩm muốn “xếp hạng trong các hóa đơn mới nhất”, phải công bố rõ tập cơ sở đó trong ngữ nghĩa chức năng.

Tương tự, không bỏ join quyền hoặc đổi sang dữ liệu cache toàn tenant để cứu thời gian phản hồi. Tối ưu hợp lệ phải giữ nguyên tập dữ liệu được phép và ý nghĩa xếp hạng đã cam kết.

## 9. Dùng kế hoạch thực thi làm bằng chứng, không dùng làm lời bảo đảm

Nên đánh giá từng mẫu truy vấn với các kích thước tenant và dạng dữ liệu khác nhau: tenant nhỏ, tenant lớn, một đơn vị có nhiều dữ liệu, nhiều đơn vị nhỏ, bộ lọc khớp phần lớn dữ liệu và bộ lọc có rất ít kết quả. Một trang không có kết quả đôi khi vẫn tốn kém vì cần tìm hết vùng có thể chứa ứng viên.

Trong môi trường kiểm soát, có thể phân tích truy vấn đại diện:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM invoice i
WHERE ...
ORDER BY ...
LIMIT ...;
```

Dấu `...` là phần cần thay bằng mẫu SQL thực sự đã xác định và tham số thử nghiệm hợp lệ. `EXPLAIN ANALYZE` thực thi câu lệnh để thu số đo; không chạy nó như một bước “kiểm tra rẻ” cho mọi yêu cầu tùy ý của client. Dùng dữ liệu thử nghiệm được phép, giới hạn tài nguyên và kế hoạch quan sát phù hợp. [PostgreSQL: EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)

Khi đọc kế hoạch, tìm nơi phải xử lý nhiều dữ liệu trước khi trả trang đầu, fan-out của join, số vòng lặp, chênh lệch ước lượng với thực tế, bước sort và hoạt động I/O tạm. Không cộng máy móc mọi con số của các node: cần hiểu node cha, node con và số lần thực thi.

Giá trị `cost` của optimizer dùng đơn vị ước lượng theo mô hình planner; nó không phải mili giây và không phải trần tài nguyên đã được thực thi. Ước lượng số dòng đầu ra tại một node cũng khác với tổng dữ liệu đã đi qua hoặc bị lọc trên toàn kế hoạch. [PostgreSQL: Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)

Có thể dùng thông tin kế hoạch và benchmark để xây dựng hồ sơ chi phí cho các mẫu đã biết. Không nên xem một lần `EXPLAIN` là cơ chế admission bảo đảm an toàn cho mọi tổ hợp tham số. Thống kê, cache, dữ liệu, prepared plan và mức cạnh tranh có thể khiến thời gian thực tế khác nhiều.

Mục tiêu kiểm chứng là một hành vi có giới hạn trên dữ liệu đại diện và dưới mức đồng thời dự kiến. Tránh ràng buộc kiểm thử vào đúng một tên node của optimizer hoặc một ngưỡng thời gian cực nhỏ chỉ đạt được trên máy cá nhân.

## 10. Kết hợp ngân sách tần suất, trọng số và số tác vụ đang chạy

Rate limit theo số request chỉ giải quyết một phần vấn đề. Mười truy vấn sort có tổng hợp lớn có thể tiêu thụ nhiều tài nguyên hơn hàng trăm truy vấn đọc một trang theo index. Ngược lại, giới hạn đồng thời không ngăn một tenant liên tục phát công việc ngay khi slot vừa trống.

Một cơ chế admission có thể kết hợp:

| Lớp | Điều kiện cần kiểm soát | Khi không đáp ứng |
|---|---|---|
| Hợp đồng đầu vào | Phạm vi, số khóa sort, kích thước trang, cursor | Từ chối trước SQL lấy dữ liệu |
| Hồ sơ chi phí | Mẫu truy vấn đủ điều kiện chạy tương tác | Yêu cầu thu hẹp hoặc dùng chức năng khác |
| Ngân sách theo thời gian | Điểm chi phí theo tenant và chủ thể | Từ chối có thời gian chờ lại phù hợp |
| Giới hạn đồng thời theo tenant | Số công việc thực sự còn hoạt động | Chờ hữu hạn hoặc từ chối |
| Giới hạn đồng thời toàn dịch vụ | Năng lực chia sẻ và phần dự phòng | Chặn tải mới theo chính sách công bằng |
| Giới hạn thực thi | Deadline và trần cho từng statement | Hủy, dọn dẹp và trả lỗi rõ ràng |

Trọng số là ước lượng do server gán cho hồ sơ, không phải hóa đơn CPU chính xác. Cần hiệu chỉnh theo số đo, đồng thời giữ các giới hạn thực thi vì vẫn có trường hợp ước lượng thấp hơn thực tế. Nếu một batch chứa nhiều phép tìm kiếm độc lập, tính chi phí và số công việc theo từng phép; không xem toàn batch chỉ là một request rẻ.

Lấy slot trước khi mượn kết nối để chạy truy vấn nghiệp vụ. Hàng chờ phải có độ dài và thời gian chờ hữu hạn; không giữ một transaction mở chỉ để chờ lượt. Bản thân bước tra quyền hoặc đọc cấu hình nếu dùng DB cũng cần đường truy cập và ngân sách riêng, tránh biến nó thành cửa tiêu thụ không giới hạn trước admission.

Một `Semaphore` trong JVM chỉ giới hạn tiến trình đó. Khi có nhiều replica, giới hạn “4 truy vấn mỗi tenant” không tự trở thành giới hạn toàn cụm. Có thể dùng bộ điều phối chung hoặc phân bổ hạn mức rõ ràng theo node, nhưng phải nói đúng phạm vi bảo đảm và xử lý khi node chết, mất liên lạc hoặc lease hết hạn.

Giới hạn toàn cục cũng cần chừa năng lực cho luồng quan trọng và cách phân chia công bằng. Không cho tenant tự nâng ưu tiên bằng `priority=high`, đổi header hay gắn nhãn “admin query”. Danh tính tenant, gói dịch vụ và hồ sơ thực thi phải được giải quyết ở server.

## 11. Bộ nhớ và tệp tạm: tăng hạn mức không thay thế kiểm soát tải

Một phản ứng dễ gặp khi sort chậm là tăng bộ nhớ cho mỗi truy vấn. Nếu nhiều công việc chạy đồng thời, thay đổi đó có thể chuyển từ sort dùng đĩa sang áp lực bộ nhớ toàn hệ thống.

Trong PostgreSQL, `work_mem` áp dụng cho từng thao tác sort/hash trước khi chuyển sang tệp tạm; một truy vấn có thể có nhiều thao tác như vậy, và nhiều phiên hoạt động làm nhu cầu bộ nhớ cộng dồn. Không thể coi nó là hạn mức bộ nhớ duy nhất cho toàn request hoặc toàn tenant. [PostgreSQL: Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html)

Để hình dung áp lực, có thể dùng mô hình thô:

```text
Áp lực bộ nhớ từ nhóm công việc
  phụ thuộc vào số công việc đồng thời
  × số thao tác cần bộ nhớ trong mỗi kế hoạch
  × ngân sách của từng thao tác
  + worker song song và các phần bộ nhớ khác
```

Mô hình này không phải phép tính dung lượng chính xác hay một giới hạn đã được cưỡng chế. Nó nhắc rằng thay một cấu hình cục bộ cần được đánh giá dưới tải đồng thời, không chỉ đo một truy vấn chạy đơn lẻ.

Spill ra tệp tạm giúp một số công việc tiếp tục xử lý nhưng tạo thêm I/O và dung lượng tạm. Nếu nhiều tenant cùng kích hoạt sort lớn, đĩa dùng chung có thể thành nút nghẽn. Cần theo dõi mức dùng tài nguyên, cấu hình giới hạn phù hợp với khả năng nền tảng và xác định cách cô lập những công việc lớn.

Không cho tham số HTTP đặt `work_mem`, bật song song hay tăng timeout tùy ý. Mỗi hồ sơ được server quản lý chỉ nhận cấu hình đã được đánh giá. Mọi cấu hình theo kết nối còn phải tuân thủ vòng đời pool; một request không được để lại thiết lập làm request sau nhận ngân sách sai.

## 12. Deadline toàn request và timeout ở database phải phối hợp

Một request có thể mất thời gian ở admission, lấy kết nối, chạy SQL, lấy metadata và dựng DTO. Nếu mỗi bước được cấp mới 750 ms, tổng thời gian có thể vượt xa giới hạn dự kiến. Dùng một deadline do server tạo từ đầu, rồi tính ngân sách còn lại trước mỗi bước có thể tiêu tốn thời gian.

Trong PostgreSQL, `statement_timeout` giới hạn từng statement; giá trị `0` tắt giới hạn đó. `lock_timeout` chỉ áp dụng khi chờ lấy lock và không thay thế giới hạn thời gian xử lý toàn câu lệnh. Vì vậy, phải phân biệt hai loại timeout và không chuyển ngân sách đã hết thành số `0`. [PostgreSQL: Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)

Ví dụ trong một transaction thực sự:

```sql
BEGIN READ ONLY;

SELECT set_config('statement_timeout', '750ms', true),
       set_config('lock_timeout', '100ms', true);

-- Thực thi mẫu SELECT đã kiểm soát, có đầy đủ điều kiện quyền.

COMMIT;
```

Các giá trị minh họa ở trên cần được thay bằng mức nhỏ hơn giữa trần hồ sơ và thời gian còn lại. Trong mã ứng dụng, tên thiết lập là hằng số; giá trị timeout được server tạo với đơn vị rõ ràng rồi bind vào lời gọi. Không nối nguyên văn giá trị client vào SQL cấu hình.

Đối số `true` của `set_config` làm thiết lập chỉ có hiệu lực trong transaction hiện tại. Do đó cần thực hiện trên đúng kết nối đang tham gia transaction; nếu chạy riêng trong autocommit rồi mới lấy kết nối khác để truy vấn, thiết lập không bảo vệ câu lệnh mong muốn. [PostgreSQL: Configuration Settings Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-SET)

Quy trình cần xử lý các điểm sau:

- Trước mỗi statement lấy dữ liệu, tính lại phần thời gian còn lại; truy vấn đếm không được nhận lại trọn ngân sách ban đầu.
- Khi phần thời gian dùng được nhỏ hơn một mili giây, từ chối bước mới; không làm tròn xuống `0` rồi vô tình tắt timeout.
- Dành dư địa cho round trip cấu hình, truyền dữ liệu và dọn dẹp. Timeout của DB không bao gồm toàn bộ thời gian chờ trong ứng dụng.
- Giới hạn cả thời gian lấy kết nối và thời gian chờ slot bằng ngân sách còn lại, không chỉ thời gian chạy SQL.
- Khi statement bị hủy và transaction lỗi, rollback theo cơ chế quản lý transaction; không bắt lỗi rồi tiếp tục query trong transaction đã hỏng.
- Phối hợp với cơ chế hủy của driver và deadline ứng dụng. Một thiết lập timeout tại DB không tự giải quyết mất kết nối mạng hoặc một luồng ứng dụng đã ngừng chờ.

Một deadline dùng đồng hồ đơn điệu cho thời lượng trong cùng tiến trình giúp tránh ảnh hưởng của việc chỉnh giờ hệ thống. Client có thể yêu cầu chờ ít hơn nếu API hỗ trợ, nhưng không được nâng trần do server quyết định.

## 13. Phác thảo Java: điều phối trước transaction, ngân sách trên đúng kết nối

Các đoạn mã sau minh họa cách phân chia trách nhiệm, không phải thư viện hoàn chỉnh. Những kiểu như `SearchPlanner`, `SortAdmission`, `WorkLifecycle`, repository và cơ chế gắn timeout cần được cài đặt theo driver, transaction manager và hạ tầng thực tế.

Đầu tiên là một bộ đếm thời gian còn lại. Ví dụ cố ý giới hạn miền thời lượng ở 30 giây để giữ phép chuyển đổi nhỏ và rõ ràng; đây là giới hạn của ví dụ, không phải tiêu chuẩn của mọi chức năng tìm kiếm.

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class SearchDeadline {
    private final long startedAtNanos;
    private final long budgetNanos;

    public SearchDeadline(Duration budget) {
        if (budget.isZero() || budget.isNegative()
                || budget.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException("Invalid search deadline");
        }
        this.startedAtNanos = System.nanoTime();
        this.budgetNanos = budget.toNanos();
    }

    public long statementMillis(long ceilingMs, long reserveMs) {
        if (ceilingMs < 1 || ceilingMs > 30_000
                || reserveMs < 0 || reserveMs > 30_000) {
            throw new IllegalArgumentException("Invalid query budget");
        }

        long elapsed = System.nanoTime() - startedAtNanos;
        long usableNanos = budgetNanos - elapsed
                - TimeUnit.MILLISECONDS.toNanos(reserveMs);
        long remainingMs = TimeUnit.NANOSECONDS.toMillis(usableNanos);
        if (remainingMs < 1) {
            throw new SearchDeadlineExceeded();
        }
        return Math.min(ceilingMs, remainingMs);
    }

    public void requireRemaining() {
        if (System.nanoTime() - startedAtNanos >= budgetNanos) {
            throw new SearchDeadlineExceeded();
        }
    }

    public static final class SearchDeadlineExceeded
            extends RuntimeException {
    }
}
```

Không truyền số `0` sang database có ý nghĩa quan trọng hơn việc cố ép mọi trạng thái vào một giá trị timeout. Khi không còn ngân sách, nhánh đúng là ngừng tạo công việc mới. Các bộ phận chờ slot và kết nối cũng cần dùng thời gian còn lại từ cùng deadline, dù ví dụ trên chỉ đưa ra phương thức tính cho statement.

Lớp điều phối không mở transaction chứa thời gian chờ admission:

```java
@Service
public class BudgetedInvoiceSearch {
    private final SearchPlanner planner;
    private final SortAdmission admission;
    private final WorkLifecycle lifecycle;
    private final InvoiceSearchRunner runner;

    public BudgetedInvoiceSearch(SearchPlanner planner,
            SortAdmission admission, WorkLifecycle lifecycle,
            InvoiceSearchRunner runner) {
        this.planner = planner;
        this.admission = admission;
        this.lifecycle = lifecycle;
        this.runner = runner;
    }

    public InvoicePage search(Actor actor, SearchInput input) {
        var deadline = new SearchDeadline(Duration.ofMillis(1_200));
        SearchPlan plan = planner.authorizeAndPlan(actor, input, deadline);
        SortWorkLease lease = admission.acquire(plan, deadline);

        return lifecycle.execute(lease,
                () -> runner.fetch(plan, deadline, lease));
    }
}
```

`authorizeAndPlan` phải xác định tenant, phạm vi được xem, mẫu sort, page size và hồ sơ chi phí bằng dữ liệu tin cậy. Các bước có truy cập kho dữ liệu bên trong nó cũng cần được giới hạn. `SearchPlan` là cấu trúc bất biến và không chứa SQL tùy ý từ client. Nếu quyền có thể bị thu hồi trong lúc chờ, repository phải áp dụng chính sách hiệu lực quyền hiện hành, chẳng hạn điều kiện quyền trong SQL hoặc kiểm tra phiên bản theo thiết kế của hệ thống.

Runner là một bean khác để lời gọi đi qua transaction proxy:

```java
@Service
public class InvoiceSearchRunner {
    private final PgQueryBudgets queryBudgets;
    private final InvoiceSearchRepository repository;
    private final InvoicePageFactory pageFactory;

    public InvoiceSearchRunner(PgQueryBudgets queryBudgets,
            InvoiceSearchRepository repository,
            InvoicePageFactory pageFactory) {
        this.queryBudgets = queryBudgets;
        this.repository = repository;
        this.pageFactory = pageFactory;
    }

    @Transactional(readOnly = true, rollbackFor = Exception.class)
    public InvoicePage fetch(SearchPlan plan, SearchDeadline deadline,
            SortWorkLease lease) {
        long statementMs = deadline.statementMillis(
                plan.budget().statementCeilingMs(),
                plan.budget().cleanupReserveMs());

        queryBudgets.installOnCurrentTransaction(statementMs,
                Math.min(statementMs, 100L));
        deadline.requireRemaining();

        var rows = repository.fetchAuthorized(plan,
                plan.pageSize() + 1, deadline, lease);
        InvoicePage page = pageFactory.materialize(rows, plan);
        deadline.requireRemaining();
        return page;
    }
}
```

Trong chế độ proxy mặc định của Spring, gọi một phương thức trong cùng đối tượng không tự đi qua transaction interceptor. Việc tách runner giúp ranh giới transaction trong ví dụ rõ ràng, với điều kiện bean và transaction management được cấu hình đúng. [Spring Framework: Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)

Những hợp đồng phải có trong phần cài đặt còn thiếu:

1. `installOnCurrentTransaction` dùng đúng kết nối của transaction manager, bind thời lượng có đơn vị, không thay thiết lập session dùng chung. Thời gian cấu hình và lấy kết nối phải được tính vào deadline; repository cần kiểm tra lại phần còn lại trước khi phát lệnh.
2. Repository chỉ chọn mẫu truy vấn đã kiểm soát, giữ đầy đủ tenant/quyền và đăng ký statement đang hoạt động với chủ thể quản lý việc hủy. Nếu có nhiều SQL, áp dụng lại ngân sách trước từng lệnh.
3. `materialize` dựng đủ DTO khi tài nguyên còn thuộc công việc hiện tại; không trả lazy stream để tiếp tục đọc DB sau khi transaction hoặc lease đã kết thúc.
4. `WorkLifecycle.execute` giữ quyền sở hữu lease qua kết thúc transaction và dọn dẹp. Khi chưa xác định được DB đã dừng, nó chuyển quyền sở hữu cho bộ xử lý dọn dẹp có giới hạn; không mặc định trả slot chỉ vì callback ném lỗi.
5. Cơ chế read-only và các quyền DB cần được cấu hình, xác minh riêng; annotation trong ví dụ không thay thế điều kiện phân quyền và không phải giới hạn chi phí.

Phần khó nằm ở các hợp đồng này. Chỉ sao chép annotation và đặt một `try/finally` trả semaphore sẽ chưa tạo ra cơ chế kiểm soát chi phí đúng khi xảy ra hủy hoặc lỗi kết nối.

## 14. Giữ slot đến khi công việc thực sự kết thúc

Cần phân biệt ba sự kiện: phía HTTP ngừng chờ, ứng dụng gửi yêu cầu hủy và database xác nhận công việc đã kết thúc. Chúng có thể xảy ra ở những thời điểm khác nhau.

Một vòng đời khái niệm:

```text
ĐÃ CHẤP NHẬN -> ĐANG CHẠY -> ĐÃ DỪNG -> ĐÃ DỌN DẸP -> TRẢ SLOT
                      |
                      +-> ĐÃ YÊU CẦU HỦY -> CHỜ XÁC NHẬN DỪNG
                                               |
                                               +-> ĐÃ DỌN DẸP -> TRẢ SLOT
```

Nếu HTTP timeout ngay ở trạng thái “đã yêu cầu hủy”, giải phóng slot lập tức sẽ cho phép công việc mới bắt đầu trong khi công việc cũ vẫn chạy. Sau nhiều vòng, giới hạn bề ngoài là 4 nhưng DB có thể đang xử lý nhiều hơn đáng kể.

Quy trình lỗi cần có chủ thể chịu trách nhiệm cho statement, transaction, kết nối và lease. Khi driver xác nhận kết thúc, thực hiện rollback hoặc hoàn tất transaction đúng cách rồi trả kết nối an toàn. Nếu không thể xác nhận trạng thái kết nối, áp dụng cơ chế loại bỏ hoặc đóng kết nối mà pool/driver hỗ trợ và theo dõi phần công việc còn chưa rõ ở phía DB. Không đưa một kết nối có trạng thái chưa xác định trở lại phục vụ request khác.

Bộ dọn dẹp không được có hàng chờ vô hạn. Khi số công việc chưa xác định tăng, hệ thống phải hạn chế nhận việc mới, cảnh báo và kích hoạt cơ chế đối soát phù hợp. Việc node mất liên lạc hoặc lease phân tán hết TTL cũng không tự chứng minh truy vấn trên DB đã dừng; thiết kế admission phải tính đến trường hợp đó.

Không dùng việc `Future.cancel(...)` trả về hoặc socket HTTP đã đóng làm bằng chứng duy nhất. Kiểm chứng bằng trạng thái thực thi, vòng đời transaction/kết nối và số công việc còn hoạt động ở tầng DB trong thử nghiệm có kiểm soát.

## 15. Kết quả, metadata, cache và export phải cùng tuân thủ ngân sách

Một trang lấy dữ liệu nhanh vẫn có thể đi kèm câu đếm tổng rất đắt. Đặt `totalCount` chạy vô điều kiện sau truy vấn chính sẽ làm ngân sách sort bị vượt qua bằng một thành phần phụ của phản hồi.

Nên định nghĩa rõ hợp đồng:

- `hasNext` có thể được suy ra từ việc lấy thêm một dòng nếu phương thức phân trang hỗ trợ; cách này không cung cấp tổng số kết quả.
- `totalCount` chính xác chỉ được thực hiện trong ngân sách và phạm vi quyền đã định nghĩa.
- Giá trị ước lượng, dữ liệu trễ hoặc việc không trả tổng phải có ngữ nghĩa rõ ràng trong API, không giả làm số đếm chính xác.
- Facets, thống kê phụ, dữ liệu mở rộng và truy vấn làm giàu DTO đều được tính vào công việc của request.

Khi không hoàn tất trong ngân sách, trả lỗi có mã ổn định như `SEARCH_DEADLINE_EXCEEDED` hoặc `SEARCH_TOO_EXPENSIVE_FOR_INTERACTIVE`. Đây là mã minh họa. Phân biệt với tham số sai, kiểu sort không hỗ trợ và hệ thống tạm hết slot. Không trả `200` cùng danh sách rỗng để người dùng hiểu nhầm rằng không có hóa đơn nào phù hợp.

Nếu hợp đồng cho phép một kiểu giảm chất lượng kết quả, chẳng hạn bỏ metadata tùy chọn, cần thiết kế từ đầu để không tiếp tục dùng transaction đã lỗi. Không tự đổi sang thứ tự mặc định, bỏ lọc hoặc trả một tập con chưa hoàn chỉnh sau timeout.

Cache có thể giảm công việc lặp lại nhưng không thay thế admission. Khóa cache và việc tái sử dụng cần phản ánh tenant, phạm vi quyền, bộ lọc, sort, phân trang và phiên bản dữ liệu/chính sách liên quan; quyền bị thu hồi phải có cơ chế làm mất hiệu lực hoặc kiểm tra lại phù hợp. Trả kết quả cache cũng không cho phép bỏ kiểm tra quyền cần thiết. Ngân sách không nên phụ thuộc vào giả định mọi yêu cầu sẽ cache hit.

Luồng export lớn là một chức năng nghiệp vụ riêng, cần quyền export, phạm vi dữ liệu, hạn mức job, thời gian lưu, giới hạn worker và ngân sách DB. Khi đề xuất export cho một yêu cầu quá đắt, không tự tạo job chỉ vì màn hình tra cứu thất bại. Sau khi người dùng thực hiện hành động export được phép, việc gửi lại cùng lệnh cần tránh tạo nhiều job đắt trùng nhau bằng cơ chế idempotency được định nghĩa rõ.

Thông báo “đã tiếp nhận export” chỉ xác nhận job được chấp nhận. Trạng thái hoàn tất phải phản ánh kết quả thật; lỗi ngân sách của worker không được biến thành tệp báo cáo thiếu dữ liệu mang nhãn thành công.

## 16. Kiểm thử tình huống lạm dụng và điều kiện thất bại

Các tình huống dưới đây là kế hoạch kiểm thử cho hệ thống triển khai cơ chế này, không phải kết quả đo của các đoạn mã minh họa. Chuẩn bị một yêu cầu đối chứng hợp lệ, có session và quyền đúng, để chứng minh các trường hợp bị chặn bởi chính sách chi phí thay vì thất bại sớm do xác thực hoặc một bộ lọc bảo vệ khác.

| Tình huống | Cách kích hoạt | Kết quả cần quan sát |
|---|---|---|
| Trang nhỏ hợp lệ | Sort rẻ, phạm vi được phép, đủ slot | Trả đúng thứ tự và tập dữ liệu; slot được hoàn trả |
| Trường hợp lệ nhưng tổ hợp đắt | Sort tổng hợp thiếu điều kiện thu hẹp | Từ chối trước truy vấn lấy dữ liệu đắt, không tự chạy export |
| Kích thước trang bất thường | Âm, quá lớn, tràn số, giá trị sentinel không hỗ trợ | Lỗi tham số; không biến thành truy vấn không giới hạn |
| Sort nhiều hoặc biểu thức tùy ý | Thêm nhiều khóa, tên hàm, biểu thức SQL | Không vượt qua registry/kế hoạch đã định nghĩa |
| Offset sâu | Yêu cầu vượt vùng hợp đồng cho phép | Từ chối hoặc yêu cầu cursor theo hợp đồng |
| Phạm vi quyền rất rộng | Một chủ thể được cấp nhiều đơn vị | Áp dụng đúng hồ sơ chi phí cho phạm vi rộng |
| Đổi ngữ cảnh cursor | Dùng cursor của tenant, bộ lọc hoặc quyền khác | Từ chối, không mở rộng phạm vi dữ liệu |
| Tenant A tạo tải cao | Nhiều yêu cầu đắt dưới các tài khoản của A | Chặn theo tenant và tổng tải, giữ phần năng lực của B theo chính sách |
| Nhiều replica | Cùng tenant phát tải vào các node khác nhau | Giới hạn đúng phạm vi đã công bố, không chỉ đúng trên một JVM |
| Timeout ở HTTP | Ngừng chờ khi DB còn xử lý | Vẫn theo dõi, hủy và giữ quyền sở hữu công việc đến lúc dọn dẹp |
| Hết ngân sách dưới 1 ms | Cố bắt đầu statement tiếp theo | Từ chối, không cài timeout bằng `0` |
| Metadata vượt ngân sách | Trang đầu đã tiêu thụ gần hết thời gian | Không cấp mới trọn ngân sách cho count/facets |
| Tái sử dụng kết nối pool | Request đặt timeout rồi commit hoặc rollback | Request sau không thừa hưởng thiết lập cục bộ của request trước |
| Hủy hoặc rollback lỗi | Giả lập lỗi driver/mạng trong môi trường thử nghiệm | Kết nối và lease có chủ thể xử lý, không âm thầm quay lại pool |
| Gửi lại export | Cùng lệnh được gửi lại do mất phản hồi | Không tạo nhiều job ngoài quy tắc idempotency |

Kiểm thử chi phí cần dữ liệu đủ để thể hiện tính chất của truy vấn. Một bảng vài chục dòng thường không bộc lộ scan lớn, fan-out, spill hoặc khác biệt giữa tenant nhỏ và lớn. Dùng bộ dữ liệu được phép với phân bố phù hợp, và chạy trong môi trường có trần tài nguyên để thử nghiệm không trở thành sự cố thật.

Với kiểm thử tải, đo cả thời gian phản hồi, số truy vấn đang hoạt động, thời gian chờ admission, số kết nối đang mượn và lượng công việc còn lại sau khi client ngắt. Kiểm tra tải đã trở về trạng thái dự kiến sau đợt thử; HTTP trả lỗi nhanh trong khi DB vẫn bận không phải là kết quả đạt.

Kiểm thử đúng dữ liệu cần dùng tập ổn định có khóa sort trùng nhau, trang cuối và phạm vi không có quyền. Duyệt các trang để xác nhận không mất hoặc lặp bản ghi do điều kiện cursor sai trong tập dữ liệu cố định. Nếu dữ liệu thay đổi trong lúc phân trang, đánh giá theo hợp đồng nhất quán mà sản phẩm thực sự cam kết, không tự giả định có snapshot xuyên mọi request.

Kiểm thử lỗi còn phải xác nhận không có cơ chế “cứu truy vấn” bỏ tenant, bỏ ACL, dùng tài khoản đặc quyền hoặc khởi tạo tác vụ nền ngoài ý muốn. Các lỗi trên đường tra cứu không được tạo ra lệnh nghiệp vụ thay đổi trạng thái hóa đơn.

## 17. Quan sát, hiệu chỉnh và triển khai thay đổi

Theo dõi theo mã kế hoạch và hồ sơ chi phí thay vì chỉ gộp toàn bộ endpoint. Một tỷ lệ trung bình tốt có thể che việc một nhóm sort đang gây timeout cho các tenant lớn.

Những tín hiệu hữu ích gồm:

- Mã kế hoạch, phiên bản chính sách, lớp chi phí và dạng phạm vi đã chuẩn hóa.
- Số lần từ chối theo lý do: hợp đồng, điều kiện chi phí, quota, hết slot hoặc hết deadline.
- Thời gian chờ slot, chờ kết nối, thực thi SQL, dựng phản hồi và dọn dẹp.
- Số công việc đang chạy, đang chờ hủy và chưa xác định trạng thái kết thúc.
- Dấu hiệu I/O tạm, áp lực bộ nhớ, số truy vấn phụ và sai lệch giữa chi phí dự kiến với số đo thực tế.
- Mức phân chia tài nguyên giữa tenant và ảnh hưởng đến các luồng nghiệp vụ quan trọng.

Không ghi nguyên bộ lọc nhạy cảm, nội dung hóa đơn hay toàn bộ query plan vào phản hồi lỗi công khai. Dùng mã truy vết, mã kế hoạch và định danh tenant được xử lý theo chính sách log. Khi thu kế hoạch để phân tích nội bộ, kiểm soát quyền truy cập và dữ liệu giá trị có thể xuất hiện trong đó.

Cần phân biệt một chỉ số ứng dụng tự đặt như “rows scanned” với ý nghĩa từng chỉ số thực tế của database. Số dòng trả về ở một node không tự bằng số dòng đã đọc trên toàn truy vấn. Khi so sánh lượng công việc với số kết quả, dùng định nghĩa đo nhất quán và ghi rõ phạm vi đo.

Hiệu chỉnh hồ sơ dựa trên dữ liệu đại diện và tải đồng thời. Triển khai thay đổi theo từng nhóm kế hoạch hoặc phạm vi phù hợp, theo dõi tỷ lệ từ chối của yêu cầu hợp lệ và có khả năng quay lại chính sách trước. Việc thêm index, thay read model hay đổi giới hạn đều cần xem tác động đến ghi dữ liệu, độ trễ cập nhật và tài nguyên dùng chung.

Không tăng toàn bộ timeout chỉ để giảm số lỗi đang thấy. Nếu thời gian chờ và công việc tồn đọng đang tăng, nâng trần có thể làm slot bị giữ lâu hơn. Quyết định tăng ngân sách phải dựa trên nguyên nhân, năng lực thực tế và mức phục vụ cần bảo đảm.

## 18. Bài tập áp dụng và điểm tự kiểm tra

Giả sử hệ thống có ba kiểu sort: ngày tạo, ngày đến hạn và tổng tiền chưa đối soát. Một nhân viên chỉ xem một đơn vị, còn quản trị tenant được xem toàn bộ đơn vị. Hãy lập bảng chính sách cho từng tổ hợp kiểu sort và phạm vi, nêu rõ điều kiện chạy tương tác, trường hợp yêu cầu thu hẹp và trường hợp có thể dùng export.

Tiếp theo, thiết kế một kịch bản trong đó 20 request cùng hết hạn ở phía HTTP trong khi DB vẫn xử lý. Chỉ ra thành phần nào sở hữu từng statement, transaction, kết nối và slot ở mỗi bước. Nếu câu trả lời là “controller đã trả lỗi nên không cần quản lý nữa”, vòng đời công việc còn thiếu một phần quan trọng.

Trước khi coi thiết kế đủ để triển khai, cần trả lời được:

1. Trường sort hợp lệ nhưng đắt được nhận diện bằng điều kiện server nào?
2. Một page nhỏ có thể tạo scan, join hoặc tổng hợp lớn ở đâu?
3. Điều kiện quyền có được giữ trong query chính, metadata, cache và export không?
4. Đã giới hạn riêng tần suất, trọng số, đồng thời, hàng chờ và thời gian thực thi chưa?
5. Giới hạn đồng thời có hiệu lực trên một JVM, một node hay toàn cụm?
6. Khi client ngắt hoặc deadline hết, ai xác nhận DB đã dừng và ai dọn tài nguyên?
7. Có đường nào làm ngân sách hết trở thành timeout bằng `0`, hoặc đặt lại ngân sách cho truy vấn phụ không?
8. Một yêu cầu bị từ chối có được báo đúng ý nghĩa, không giả làm kết quả đầy đủ không?
9. Bằng chứng nào cho thấy tenant gây tải cao không lấy mất phần năng lực đã dành cho tenant khác?

Một thiết kế bảo vệ tốt cho phép truy vấn hữu ích hoạt động trong giới hạn rõ ràng và có thể quan sát. Chi phí phải được kiểm soát từ lúc hình thành công việc đến khi tài nguyên thực sự được trả lại, trong khi quyền truy cập và ý nghĩa nghiệp vụ của kết quả luôn được giữ nguyên.
