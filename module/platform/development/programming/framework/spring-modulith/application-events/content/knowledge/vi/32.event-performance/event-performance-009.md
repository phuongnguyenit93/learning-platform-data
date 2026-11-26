# Tối ưu truy vấn registry

Event Publication Registry lưu trạng thái giao application event tới từng listener. Khi số event và listener tăng, registry trở thành một phần quan trọng của đường xử lý: ứng dụng ghi publication trong transaction nguồn, cập nhật trạng thái khi listener hoàn tất, truy vấn publication chưa hoàn tất để phục hồi và có thể dọn các bản ghi đã hoàn thành theo chính sách lưu giữ.

Nếu truy vấn registry quét quá nhiều hàng, tải database tăng, thời gian khởi động/phục hồi kéo dài và các thao tác cập nhật publication có thể tranh chấp với truy vấn nền. Tối ưu cần bắt đầu từ workload thực tế: ứng dụng thường tìm publication chưa hoàn tất, lọc theo listener, resubmit event cũ hay dọn dữ liệu hoàn tất? Mỗi truy vấn có điều kiện lọc, thứ tự và tần suất khác nhau nên cần chiến lược index và retention phù hợp.

Bài này trình bày cách đo và tối ưu truy vấn Event Publication Registry trong Spring Modulith, cách thiết kế index theo query pattern, phân trang và xử lý batch, giảm tranh chấp transaction, quản lý dữ liệu hoàn tất và xác minh hiệu quả mà không làm sai semantics phục hồi event.

## 1. Registry lưu gì và vì sao truy vấn có thể chậm?

Khi một application event được publish tới các transactional listener, Spring Modulith ghi nhận publication tương ứng cho từng listener. Một event có ba listener có thể tạo ba publication độc lập. Mỗi publication có vòng đời riêng: được tạo, listener xử lý và publication được đánh dấu hoàn tất.

Registry vì vậy không chỉ lưu một hàng cho mỗi event. Số hàng có thể tăng theo:

- Số event được publish.
- Số listener đăng ký nhận mỗi event.
- Tỷ lệ listener thất bại hoặc chưa hoàn tất.
- Thời gian giữ publication đã hoàn tất.
- Số lần resubmit và cách implementation ghi nhận trạng thái.

Các workload phổ biến:

| Truy vấn | Mục đích | Đặc điểm tải |
|---|---|---|
| Tìm publication chưa hoàn tất | Phục hồi listener sau lỗi hoặc restart | Thường cần lọc trạng thái và đọc định kỳ |
| Lọc publication theo listener | Điều tra listener cụ thể hoặc resubmit có chọn lọc | Có thể cần lọc listener và sắp xếp theo thời gian |
| Tìm publication quá cũ | Phát hiện event bị kẹt | Thường lọc trạng thái chưa hoàn tất và tuổi |
| Xóa publication đã hoàn tất quá thời hạn | Giữ kích thước registry ổn định | Thường lọc theo thời điểm hoàn tất |
| Đọc publication theo khoảng thời gian | Vận hành, audit hoặc thống kê | Có thể đọc nhiều hàng và payload lớn |

Truy vấn chậm thường xuất hiện khi bảng tăng liên tục nhưng index không khớp điều kiện lọc, truy vấn lấy payload lớn dù chỉ cần đếm, cleanup quét cả bảng hoặc tác vụ phục hồi đọc toàn bộ publication chưa hoàn tất trong một lần.

## 2. Bắt đầu từ query pattern, không bắt đầu từ index

Index chỉ có ích khi phục vụ truy vấn thực tế. Trước khi thêm index, hãy xác định các câu hỏi:

1. Registry implementation đang dùng là JDBC, JPA, MongoDB hay implementation khác?
2. Truy vấn nào chạy thường xuyên: incomplete publications, resubmit, cleanup hay thống kê?
3. Điều kiện lọc có gồm listener ID, trạng thái, publication time hoặc completion time không?
4. Truy vấn cần thứ tự nào và có giới hạn số hàng không?
5. Payload có được tải trong cùng truy vấn hay chỉ cần ID/trạng thái?
6. Tỷ lệ publication chưa hoàn tất so với tổng số hàng là bao nhiêu?
7. Bản ghi hoàn tất được giữ trong bao lâu?

Không giả định tên bảng, cột hoặc SQL giống nhau giữa các phiên bản Spring Modulith và persistence implementation. Hãy xem schema/migration và SQL thực tế do phiên bản đang dùng tạo ra. Các ví dụ index trong bài là mẫu thiết kế theo ý nghĩa cột; cần ánh xạ sang schema thật trước khi triển khai.

## 3. Đo baseline trước khi thay đổi

Ghi nhận baseline để biết truy vấn nào cần tối ưu và tránh thêm index không cần thiết.

Các số liệu hữu ích:

- Tổng số publication.
- Số publication chưa hoàn tất.
- Số publication hoàn tất theo ngày/tuần.
- Tuổi publication chưa hoàn tất lâu nhất.
- Số hàng được đọc và số hàng trả về cho mỗi truy vấn.
- P50/P95/P99 latency của truy vấn registry.
- Thời gian cleanup và số hàng bị xóa mỗi batch.
- Database CPU, I/O, buffer hit, lock wait và connection pool usage.
- Kích thước bảng, index và payload trung bình.

Ví dụ bảng baseline:

| Chỉ số | Giá trị cần ghi nhận |
|---|---|
| Tổng publication | Số hàng hiện tại |
| Incomplete publication | Số hàng completion chưa có giá trị |
| Incomplete ratio | Incomplete / total |
| Oldest incomplete age | Tuổi bản ghi chưa hoàn tất lâu nhất |
| Query latency | P50/P95/P99 theo loại truy vấn |
| Rows scanned / returned | Mức độ chọn lọc của truy vấn |
| Cleanup throughput | Hàng được dọn mỗi giây hoặc mỗi batch |
| Index size | Dung lượng index và mức tăng theo thời gian |

Lấy số liệu trong điều kiện tải đại diện. Một bảng nhỏ trên môi trường local có thể dùng sequential scan nhanh hơn index; khi dữ liệu lớn hơn, query plan có thể thay đổi hoàn toàn.

## 4. Tối ưu truy vấn publication chưa hoàn tất

Truy vấn incomplete publication thường là đường quan trọng nhất cho phục hồi. Điều kiện logic thường tương đương với việc tìm các publication chưa có thời điểm hoàn tất. Tuy nhiên, phải xác nhận predicate và thứ tự thực tế của implementation đang dùng.

Nếu workload thường tìm mọi publication chưa hoàn tất, index nên giúp database bỏ qua phần lớn bản ghi đã hoàn tất. Với PostgreSQL, partial index là một lựa chọn nếu điều kiện của truy vấn khớp với predicate của index:

~~~sql
-- Mẫu minh họa, thay tên bảng/cột bằng schema thực tế.
CREATE INDEX CONCURRENTLY idx_publication_incomplete_age
    ON event_publication (publication_date, id)
    WHERE completion_date IS NULL;
~~~

Nếu truy vấn thường lọc thêm listener, có thể cần index có listener đứng trước thời gian:

~~~sql
-- Chỉ dùng nếu query thường lọc listener_id.
CREATE INDEX CONCURRENTLY idx_publication_incomplete_listener_age
    ON event_publication (listener_id, publication_date, id)
    WHERE completion_date IS NULL;
~~~

Không tạo cả hai index theo thói quen. Chọn theo query pattern, cardinality và execution plan. Nếu truy vấn không lọc listener, index bắt đầu bằng listener_id có thể không hiệu quả cho việc tìm toàn bộ incomplete publication theo thời gian.

Với database không hỗ trợ partial index, có thể dùng composite index bắt đầu bằng cột trạng thái phù hợp, nhưng hiệu quả phụ thuộc kiểu dữ liệu, độ chọn lọc và optimizer. Không nên thêm cột boolean trạng thái mới nếu implementation không quản lý trạng thái đó một cách nhất quán.

### 4.1. Thứ tự cột trong composite index

Thứ tự cột ảnh hưởng việc database có thể dùng prefix của index. Một quy tắc thực hành:

- Đặt cột equality filter có độ chọn lọc phù hợp trước.
- Đặt cột range như publication time sau các cột equality.
- Thêm ID làm tie-breaker nếu query cần thứ tự ổn định.
- Tránh đưa payload lớn vào index.
- Xem xét chiều ASC/DESC nếu query có ORDER BY cụ thể và database hỗ trợ tối ưu tương ứng.

Ví dụ truy vấn listener cụ thể có thể lọc listener_id bằng equality, sau đó lấy publication cũ nhất theo publication_date. Index gồm listener_id, publication_date và id có thể phù hợp hơn index chỉ theo publication_date. Query toàn cục lại có thể cần index khác.

Index không bảo đảm thứ tự nếu query không có ORDER BY. Luôn khai báo thứ tự cần thiết trong query thay vì dựa vào thứ tự vật lý của index.

## 5. Tối ưu truy vấn publication hoàn tất và cleanup

Publication đã hoàn tất thường chiếm phần lớn dữ liệu sau thời gian chạy dài. Nếu chính sách cho phép xóa chúng sau một khoảng retention, truy vấn cleanup thường lọc theo completion time.

Một index theo thời điểm hoàn tất có thể giúp tìm các bản ghi quá hạn:

~~~sql
-- Mẫu minh họa cho cleanup theo completion time.
CREATE INDEX CONCURRENTLY idx_publication_completed_at
    ON event_publication (completion_date, id)
    WHERE completion_date IS NOT NULL;
~~~

Nếu database không hỗ trợ partial index, cân nhắc composite index trên completion time và ID. Cần đo lợi ích so với chi phí ghi thêm index cho mỗi publication.

Cleanup nên xóa theo batch giới hạn thay vì xóa hàng triệu bản ghi trong một transaction dài. Một mẫu PostgreSQL minh họa:

~~~sql
WITH candidates AS (
    SELECT id
    FROM event_publication
    WHERE completion_date < :retention_cutoff
    ORDER BY completion_date, id
    LIMIT :batch_size
)
DELETE FROM event_publication p
USING candidates c
WHERE p.id = c.id;
~~~

Tên bảng/cột chỉ là minh họa; không chạy SQL trực tiếp lên bảng do Spring Modulith quản lý nếu API cleanup công khai của phiên bản hiện tại đã đáp ứng nhu cầu. Ưu tiên API được hỗ trợ để framework duy trì semantics và tương thích schema.

Không xóa publication chưa hoàn tất chỉ vì chúng cũ. Publication cũ có thể là dấu hiệu listener đang lỗi và cần điều tra. Chính sách retention phải phân biệt rõ publication hoàn tất với publication đang chờ phục hồi.

## 6. Dùng API registry thay vì tự truy vấn bảng nội bộ

Spring Modulith cung cấp abstraction để truy vấn và resubmit publication chưa hoàn tất, chẳng hạn API IncompleteEventPublications. Các API cụ thể có thể thay đổi theo phiên bản; cần đối chiếu tài liệu và dependency đang dùng.

Ứng dụng nên dùng API công khai để:

- Liệt kê publication chưa hoàn tất.
- Resubmit theo điều kiện được API hỗ trợ.
- Xóa publication hoàn tất theo chính sách retention nếu implementation cung cấp chức năng đó.
- Truy vấn trạng thái phục vụ quy trình vận hành.

Không để business service phụ thuộc trực tiếp vào tên bảng hoặc cột nội bộ của JDBC implementation. Việc query thẳng schema nội bộ có thể hỏng khi nâng cấp Spring Modulith hoặc đổi persistence implementation.

Truy vấn SQL trực tiếp có thể hữu ích cho DBA và quan sát read-only, nhưng phải được xem là phụ thuộc vào schema cụ thể. Nếu cần một truy vấn tùy chỉnh trong ứng dụng, hãy đặt nó sau adapter/repository riêng, ghi rõ phiên bản schema được hỗ trợ và có migration/test tương ứng.

## 7. Phân trang và xử lý theo batch

Một tác vụ phục hồi hoặc báo cáo không nên tải toàn bộ registry vào bộ nhớ. Khi số publication lớn, dùng batch nhỏ để giới hạn memory, thời gian transaction và lượng dữ liệu đọc.

Nếu API công khai hỗ trợ giới hạn/pagination, hãy dùng API đó. Nếu đang thiết kế một repository riêng cho dữ liệu vận hành, keyset pagination thường phù hợp hơn offset pagination cho tập dữ liệu lớn.

Ví dụ keyset theo cặp thời gian và ID:

~~~sql
SELECT id, publication_date, listener_id
FROM event_publication
WHERE completion_date IS NULL
  AND (publication_date, id) > (:last_date, :last_id)
ORDER BY publication_date, id
LIMIT :batch_size;
~~~

Cặp publication_date và id tạo thứ tự ổn định khi nhiều publication có cùng timestamp. Điều kiện cursor phải khớp với ORDER BY và index. Với database không hỗ trợ row-value comparison, viết điều kiện tương đương bằng các nhánh so sánh.

Offset pagination với offset rất lớn có thể phải đọc và bỏ qua nhiều hàng trước khi trả batch. Keyset pagination bắt đầu từ vị trí cursor nên thường ổn định hơn khi đi sâu vào tập dữ liệu.

Tuy nhiên, không tự triển khai keyset query trên bảng registry nội bộ chỉ để thay thế API framework. Hãy dùng nó cho repository riêng hoặc báo cáo read-only khi schema và quyền truy cập được quản lý rõ.

### 7.1. Chọn batch size

Batch quá nhỏ tạo nhiều round trip và overhead; batch quá lớn làm tăng memory, lock duration và thời gian phục hồi mỗi lần chạy.

Chọn batch size bằng thử nghiệm tải:

- Bắt đầu với batch vừa phải.
- Đo thời gian đọc, xử lý và cập nhật mỗi batch.
- Theo dõi database CPU, I/O và connection pool.
- Giảm batch nếu transaction kéo dài hoặc listener tạo tải đột biến.
- Tăng batch từ từ nếu database còn dư năng lực và throughput chưa đạt mục tiêu.

Không đặt batch size cố định cho mọi môi trường nếu dữ liệu và năng lực database khác nhau. Cần có giới hạn tối đa để cấu hình sai không tạo một truy vấn quá lớn.

## 8. Giảm chi phí đọc payload

Publication record có thể chứa serialized event. Payload lớn làm tăng I/O, memory và chi phí deserialize, đặc biệt khi truy vấn chỉ nhằm đếm số incomplete publication hoặc tìm tuổi bản ghi.

Tách hai loại nhu cầu:

- Query metadata: đếm, lọc theo listener/trạng thái/thời gian, đo tuổi backlog.
- Query nội dung: tải payload để resubmit hoặc điều tra một publication cụ thể.

Với metadata dashboard, chỉ chọn các cột cần thiết nếu API/adapter cho phép. Tránh SELECT toàn bộ payload cho một báo cáo count hoặc age. Với resubmit, payload là cần thiết nhưng nên tải theo batch có giới hạn.

Không đưa payload vào covering index. Payload có thể lớn và thay đổi cách lưu trữ của database; index nên chứa khóa lọc/sắp xếp và có thể một số cột nhỏ thực sự cần cho query.

Nếu payload rất lớn, xem xét kích thước event contract. Event nên mang dữ liệu đủ cho listener nhưng không nhất thiết chứa toàn bộ aggregate hoặc binary blob. Dữ liệu tham chiếu lớn có thể được lưu ở nơi phù hợp, nhưng phải cân nhắc khả năng replay và tính bất biến của dữ liệu được tham chiếu.

## 9. Quản lý retention để giới hạn kích thước registry

Registry không phải event store đầy đủ. Publication record phục vụ theo dõi giao event tới listener. Nếu cần lưu lịch sử event dài hạn, hãy dùng event store, audit log hoặc archive riêng với chính sách retention phù hợp.

Đối với publication đã hoàn tất:

- Xác định thời gian lưu dựa trên nhu cầu điều tra và vận hành.
- Dọn theo batch để tránh transaction dài.
- Theo dõi số hàng bị xóa và thời gian cleanup.
- Chạy cleanup ở tần suất phù hợp với tốc độ phát sinh event.
- Xác minh backup, audit và yêu cầu lưu trữ trước khi xóa.

Đối với publication chưa hoàn tất:

- Không áp dụng retention cleanup thông thường.
- Theo dõi tuổi bản ghi và listener liên quan.
- Resubmit sau khi sửa nguyên nhân theo chính sách.
- Chỉ xóa hoặc đóng trạng thái khi có quy trình vận hành được phê duyệt và đã xác định kết quả nghiệp vụ.

Nếu completed publication được giữ vô thời hạn, bảng và index sẽ tiếp tục tăng. Nếu xóa quá sớm, đội vận hành có thể mất dấu vết cần thiết để điều tra. Chọn retention dựa trên SLA, thời gian phát hiện sự cố và nhu cầu audit thực tế.

## 10. Tránh tranh chấp giữa query, listener và cleanup

Registry được ghi liên tục khi publish event và khi listener hoàn tất. Query phục hồi, cleanup và báo cáo có thể chạy đồng thời với các thao tác ghi này.

Các nguyên tắc:

- Giữ transaction đọc/ghi ngắn.
- Không giữ database lock trong lúc gọi HTTP hoặc broker.
- Chạy cleanup theo batch nhỏ.
- Tránh chạy nhiều job cleanup hoặc resubmit toàn bảng đồng thời.
- Dùng scheduler/leader coordination hoặc distributed lock nếu nhiều instance có thể khởi chạy cùng một job vận hành.
- Theo dõi lock wait, deadlock và transaction age.

Nếu hai instance cùng chạy một quy trình resubmit, một publication có thể bị giao lại nhiều lần tùy semantics của implementation và cơ chế claim. Không giả định API tự bảo đảm một worker duy nhất nếu tài liệu phiên bản không nêu rõ. Hãy kiểm tra hành vi concurrency, dùng cơ chế điều phối phù hợp và giữ listener idempotent.

Một transaction dài có thể giữ snapshot cũ và làm tăng áp lực vacuum hoặc lock. Không mở transaction bao trùm cả việc quét registry, gọi listener và chờ dependency bên ngoài.

## 11. Chỉ mục phụ trợ cho báo cáo và cảnh báo

Các dashboard thường cần các truy vấn tổng hợp như:

- Đếm incomplete publication theo listener.
- Tìm publication chưa hoàn tất cũ nhất.
- Đếm publication hoàn tất trong một khoảng thời gian.
- Tính số publication tạo mới theo giờ/ngày.

Nếu các truy vấn này chạy thường xuyên trên bảng lớn, index phù hợp có thể giảm scan. Tuy nhiên, COUNT(*) trên tập incomplete rất lớn vẫn có thể tốn tài nguyên dù có index; cân nhắc metric định kỳ hoặc bảng tổng hợp nếu dashboard cần cập nhật liên tục.

Không chạy truy vấn tổng hợp nặng trên primary database theo chu kỳ quá ngắn. Có thể:

- Thu thập metric định kỳ với tần suất phù hợp.
- Cache số liệu vận hành trong thời gian ngắn nếu chấp nhận độ trễ.
- Dùng read replica cho báo cáo khi topology hỗ trợ.
- Dùng bảng tổng hợp riêng được cập nhật incremental.

Metric là số liệu quan sát, không phải nguồn sự thật để quyết định publication nào cần resubmit. Khi thực hiện thao tác phục hồi, hãy đọc trạng thái hiện tại từ registry qua API được hỗ trợ.

## 12. Đọc execution plan và xác minh index

Sau khi thêm hoặc thay index, hãy so sánh execution plan trước và sau với dữ liệu đại diện. Với PostgreSQL, EXPLAIN ANALYZE BUFFERS cho biết thời gian thực thi, số hàng thực tế và hoạt động buffer. Với database khác, dùng công cụ tương ứng.

Kiểm tra:

- Có index scan hoặc bitmap scan phù hợp không?
- Số hàng ước lượng có gần số hàng thực tế không?
- Rows removed by filter có quá lớn không?
- Có sort lớn ngoài index không?
- Có heap/table fetch quá nhiều không?
- Buffer reads và I/O có giảm không?
- Query latency P95/P99 có cải thiện dưới tải không?

Index scan không phải lúc nào cũng nhanh hơn sequential scan. Nếu predicate trả về phần lớn bảng, sequential scan có thể là lựa chọn đúng của optimizer. Mục tiêu là giảm tổng chi phí của workload, không phải ép mọi truy vấn dùng index.

Sau khi tạo index, cập nhật statistics theo cơ chế database. Với PostgreSQL, ANALYZE giúp planner có thống kê mới; vacuum/maintenance cần được theo dõi khi cleanup xóa nhiều hàng.

## 13. Cân bằng chi phí đọc và ghi

Mỗi index bổ sung làm tăng chi phí INSERT, UPDATE, DELETE và dung lượng lưu trữ. Registry có thể ghi một publication khi event được publish và cập nhật completion khi listener hoàn tất. Quá nhiều index làm chậm chính đường xử lý event mà ta muốn tối ưu.

Trước khi thêm index:

1. Xác định query nào chiếm phần lớn thời gian hoặc tài nguyên.
2. Xác định index hiện có và mức độ sử dụng.
3. Ước lượng số publication ghi mỗi giây.
4. Ước lượng kích thước index mới.
5. Đo chi phí ghi trước và sau.
6. Xóa index trùng lặp hoặc không còn được dùng chỉ sau khi có bằng chứng và kế hoạch an toàn.

Không tạo index riêng cho mọi field. Index có chi phí bảo trì, và một composite index có thể phục vụ nhiều query nếu prefix phù hợp. Ngược lại, một index quá rộng có thể không phục vụ tốt query có điều kiện lọc khác nhau.

## 14. Triển khai index an toàn

Với bảng lớn, tạo index có thể gây tải hoặc khóa ghi tùy database và phương thức tạo. Hãy dùng cơ chế online/concurrent index phù hợp với hệ quản trị.

Ví dụ PostgreSQL hỗ trợ CREATE INDEX CONCURRENTLY để giảm chặn ghi, nhưng câu lệnh này có giới hạn riêng và không chạy trong transaction block thông thường. Với database khác, cách online index khác nhau.

Một kế hoạch triển khai nên gồm:

- Kiểm tra dung lượng đĩa và tải I/O.
- Xác minh index có trùng với index hiện tại không.
- Tạo index theo cơ chế online được database hỗ trợ.
- Theo dõi tiến trình và lỗi build index.
- Kiểm tra execution plan sau khi index sẵn sàng.
- Theo dõi write latency và dung lượng index.
- Có kế hoạch rollback nếu index gây chi phí ghi không chấp nhận được.

Không sửa schema do Spring Modulith quản lý mà không có migration rõ ràng. Nếu dùng schema migration riêng, cần đảm bảo nâng cấp ứng dụng và persistence implementation vẫn tương thích.

## 15. Tối ưu theo từng persistence implementation

Không có một chiến lược SQL duy nhất cho mọi registry store.

**JDBC:** truy vấn và index phụ thuộc schema quan hệ do implementation/migration tạo ra. Có thể dùng execution plan, partial/composite index, batch cleanup và keyset pagination cho truy vấn tùy chỉnh được quản lý.

**JPA:** ngoài index database, cần xem SQL ORM sinh ra, fetch strategy và kích thước persistence context. Tránh tải hàng loạt entity có payload lớn chỉ để thống kê. Dùng projection DTO hoặc query metadata khi repository tùy chỉnh cho phép.

**MongoDB:** index cần khớp filter và sort của query; compound index và thứ tự field ảnh hưởng khả năng dùng index. Theo dõi explain executionStats, documents examined và keys examined. Tránh tạo index nhiều field không phục vụ query thực tế.

**Implementation khác:** dùng công cụ phân tích query của store tương ứng, xem xét consistency, pagination và chi phí index theo semantics của nó.

Dù dùng store nào, ứng dụng nên ưu tiên abstraction công khai của Spring Modulith cho các thao tác publication. Tối ưu storage-specific cần được cô lập để việc đổi implementation không làm lan phụ thuộc vào schema tới các module nghiệp vụ.

## 16. Quan sát hiệu năng registry

Một registry được tối ưu cần có số liệu để phát hiện khi workload thay đổi.

Các metric nên theo dõi:

- Tổng publication và số incomplete publication.
- Incomplete count theo listener.
- Tuổi incomplete publication lâu nhất.
- Publication tạo mới và hoàn tất mỗi phút.
- Query latency theo nhóm truy vấn.
- Số hàng đọc/trả về và cleanup throughput.
- Thời gian resubmit và tỷ lệ listener hoàn tất sau resubmit.
- Database CPU, I/O, connection pool, lock wait và deadlock.
- Kích thước bảng/index và tốc độ tăng dữ liệu.

Không dùng eventId hoặc correlationId làm label metric vì cardinality không giới hạn. Có thể dùng listener ID hoặc nhóm event type nếu tập giá trị được kiểm soát; định danh chi tiết nên nằm trong log/traces.

Cảnh báo khi incomplete count tăng liên tục, oldest age vượt SLA, cleanup không theo kịp tốc độ ghi hoặc query latency tăng đột biến. Một registry có nhiều publication chưa hoàn tất không nhất thiết do query chậm; cần phân biệt backlog do listener lỗi với backlog do database query.

## 17. Kiểm thử tối ưu truy vấn

Kiểm thử hiệu năng cần dữ liệu gần với phân phối production. Một bảng vài trăm hàng không thể đại diện cho registry có hàng triệu publication và tỷ lệ incomplete rất thấp.

Các kịch bản nên đo:

| Kịch bản | Điều cần xác minh |
|---|---|
| Tỷ lệ incomplete thấp | Query tìm publication chờ không quét quá nhiều dữ liệu |
| Một listener có backlog lớn | Lọc theo listener có kế hoạch truy vấn phù hợp |
| Nhiều publication cùng timestamp | Phân trang có thứ tự ổn định, không bỏ sót |
| Cleanup lượng lớn | Batch xóa giới hạn transaction và lock |
| Payload lớn | Query metadata không tải payload không cần thiết |
| Publish đồng thời với cleanup | Không làm tăng lỗi hoặc lock wait bất thường |
| Nhiều instance phục hồi | Không tạo tải truy vấn/resubmit không kiểm soát |
| Bảng tăng theo thời gian | Latency và index size vẫn trong giới hạn |
| Nâng cấp Spring Modulith | Query/API và schema vẫn tương thích |

So sánh baseline và sau tối ưu dưới cùng dữ liệu, concurrency và cấu hình database. Đo cả read latency lẫn write latency; một index có thể làm query nhanh hơn nhưng khiến publish/complete chậm hơn.

Không dùng benchmark chỉ đo một câu SELECT cô lập. Workload thực tế gồm INSERT publication, UPDATE completion, query incomplete, resubmit và cleanup cùng lúc.

## 18. Các lỗi tối ưu thường gặp

**Tạo index trước khi xem query plan.** Index có thể không được dùng hoặc làm tăng chi phí ghi. Bắt đầu từ query pattern và baseline.

**Giả định schema giống nhau giữa mọi phiên bản.** Tên bảng/cột và SQL phụ thuộc persistence implementation. Đọc migration và query thực tế của phiên bản đang chạy.

**Dùng index chỉ theo trạng thái nhưng quên thứ tự.** Query cần lọc và ORDER BY có thể vẫn phải sort nhiều hàng. Thiết kế composite index theo predicate và sort.

**Tạo quá nhiều index.** INSERT/UPDATE/DELETE chậm và dung lượng tăng. Chỉ giữ index có lợi ích đo được.

**Tải payload cho dashboard.** Tăng I/O và memory. Dùng query metadata hoặc metric tổng hợp.

**Cleanup toàn bảng trong một transaction.** Tạo lock, WAL/undo lớn và ảnh hưởng listener. Xóa theo batch và giữ incomplete publication.

**Dùng OFFSET lớn.** Database phải bỏ qua nhiều hàng khi phân trang sâu. Dùng keyset cho repository tùy chỉnh khi phù hợp.

**Chạy nhiều job resubmit đồng thời.** Tăng tải và có thể tạo delivery trùng. Điều phối job và giữ listener idempotent.

**Query trực tiếp bảng nội bộ trong business code.** Tạo phụ thuộc schema và làm nâng cấp khó khăn. Dùng API registry công khai.

**Xóa publication hoàn tất quá sớm.** Mất dữ liệu điều tra. Chọn retention dựa trên nhu cầu vận hành và audit.

## 19. Quy trình tối ưu registry

Khi registry bắt đầu chậm, thực hiện theo trình tự:

1. Đo tổng số publication, incomplete ratio và tuổi backlog.
2. Thu thập query latency, execution plan, rows scanned và database I/O.
3. Xác định query pattern chiếm phần lớn chi phí.
4. Đối chiếu schema/migration và index hiện có của đúng persistence implementation.
5. Thiết kế một thay đổi nhỏ: index, batch, pagination hoặc retention.
6. Đo cả read path lẫn write path trên dữ liệu đại diện.
7. Triển khai index/migration theo cơ chế online phù hợp.
8. Theo dõi query latency, publication throughput, lock wait và backlog sau rollout.
9. Điều chỉnh batch/cleanup cadence nếu dữ liệu hoàn tất tăng nhanh.
10. Ghi lại query plan và số liệu baseline để so sánh ở lần nâng cấp tiếp theo.

Tối ưu truy vấn registry là bài toán cân bằng giữa truy vấn phục hồi nhanh, ghi publication ít tốn kém và lưu trữ có kiểm soát. Với Spring Modulith, hãy dùng API publication được hỗ trợ cho thao tác ứng dụng, tối ưu index theo query thực tế của persistence implementation, xử lý theo batch và giữ publication chưa hoàn tất cho tới khi có kết quả rõ ràng. Khi đo cả query plan, read/write latency, backlog và retention, registry có thể mở rộng mà không làm giảm độ tin cậy của giao event.
