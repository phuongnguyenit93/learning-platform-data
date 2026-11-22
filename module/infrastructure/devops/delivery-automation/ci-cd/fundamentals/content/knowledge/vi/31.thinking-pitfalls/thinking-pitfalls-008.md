# Mặc định quay lui ứng dụng cũng quay lui an toàn dữ liệu

## 1. Ngộ nhận này xuất hiện như thế nào?

Khi một bản phát hành mới gây lỗi, phản xạ thường thấy là đưa ứng dụng về phiên bản trước đó. Nhóm chọn lại image cũ, chạy lệnh deploy hoặc rollback release, thấy pod hoạt động và cho rằng hệ thống đã trở về trạng thái an toàn.

Giả định đó bỏ qua một sự thật: **ứng dụng và dữ liệu có vòng đời thay đổi khác nhau**. Đưa binary từ phiên bản N+1 về N chỉ thay đổi code đang chạy. Database có thể đã được migration, dữ liệu có thể đã được ghi theo định dạng mới, queue có thể chứa event mới và hệ thống bên ngoài có thể đã thực hiện side effect.

Ví dụ, phiên bản N+1 thêm trạng thái REFUNDED cho đơn hàng. Sau khi một số đơn được refund, nhóm triển khai lại N vì phát hiện lỗi ở màn hình báo cáo. Binary N chỉ hiểu PENDING, PAID và CANCELLED. Ứng dụng có thể khởi động bình thường nhưng lỗi khi đọc đơn hàng đã refund, hoặc tệ hơn, ánh xạ nhầm trạng thái và hiển thị sai thông tin tài chính.

Rollback thành công ở tầng triển khai không chứng minh dữ liệu còn tương thích với code cũ. Cần kiểm tra riêng cả khả năng đọc, ghi và giữ đúng ý nghĩa nghiệp vụ.

Trong module **DEVOPS_CI_CD_FUNDAMENTALS**, rollback là một phần của luồng phát hành có truy vết, quản lý artifact, môi trường, cổng chất lượng và xác minh sau triển khai. Cách nghĩ đúng phải bao gồm cả trạng thái dữ liệu mà release mới đã tạo ra.

## 2. Tách các trạng thái thường bị gọi chung là rollback

Từ rollback thường được dùng cho nhiều thao tác khác nhau:

| Thao tác | Điều thực sự thay đổi | Điều không tự động được khôi phục |
|---|---|---|
| Rollback ứng dụng | Image, binary hoặc code version đang chạy | Schema và dữ liệu đã ghi |
| Rollback cấu hình | Config hoặc feature flag | Side effect đã phát sinh |
| Rollback hạ tầng | Phiên bản manifest, chart hoặc resource | Dữ liệu persistent và trạng thái bên ngoài |
| Down migration | Schema được chuyển về cấu trúc trước | Dữ liệu bị xóa hoặc mất thông tin |
| Restore database | Database được đưa về một điểm khôi phục | Các giao dịch sau điểm đó và trạng thái hệ thống ngoài |
| Compensation | Tạo giao dịch bù để sửa tác động nghiệp vụ | Không nhất thiết xóa được lịch sử hành động ban đầu |
| Roll-forward | Phát hành bản sửa tiến về trạng thái đúng | Không khôi phục code cũ |

Các thao tác này có thể phối hợp trong một kế hoạch phục hồi, nhưng không thể coi là một lệnh duy nhất. Runbook phải ghi rõ từng trạng thái cần thay đổi, thứ tự thực hiện và bằng chứng xác minh.

## 3. Vì sao code cũ có thể không đọc được dữ liệu mới?

Ứng dụng thường chứa giả định về schema và dữ liệu:

- Cột nào tồn tại và có thể NULL hay không.
- Tập giá trị enum hoặc trạng thái hợp lệ.
- Kiểu dữ liệu, đơn vị đo và timezone.
- Tên field và cấu trúc JSON.
- Quan hệ giữa bảng, khóa và quy tắc unique.
- Event version mà consumer có thể giải mã.
- Cấu trúc session hoặc cache được serialize.
- Trình tự trạng thái nghiệp vụ được phép chuyển đổi.

Phiên bản mới có thể thay đổi một trong các giả định này. Database vẫn hoạt động và health check vẫn xanh, nhưng code cũ có thể đọc sai hoặc ghi dữ liệu không còn đáp ứng invariant.

Cần phân biệt ba kiểu lỗi:

1. **Lỗi cấu trúc:** query tham chiếu cột đã bị xóa hoặc constraint mới chặn lệnh ghi.
2. **Lỗi biểu diễn:** enum, JSON, serialization hoặc kiểu dữ liệu mới khiến parser cũ thất bại.
3. **Lỗi ngữ nghĩa:** code cũ đọc được giá trị nhưng hiểu sai ý nghĩa, ví dụ nhầm đơn vị tiền tệ hoặc trạng thái thanh toán.

Lỗi ngữ nghĩa thường khó phát hiện hơn vì không nhất thiết tạo exception. Một hệ thống có thể trả HTTP 200 nhưng tính sai số tiền hoặc hiển thị sai trạng thái đơn hàng.

## 4. Một release thay đổi nhiều trạng thái cùng lúc

Xem một release gồm các bước:

~~~mermaid
flowchart TD
    A["N đang chạy với schema S"] --> B["Migration mở rộng schema"]
    B --> C["Deploy N+1"]
    C --> D["N+1 ghi dữ liệu theo format mới"]
    D --> E["Backfill và chuyển traffic"]
    E --> F["Loại bỏ cấu trúc cũ"]
    F --> G["Sự cố: yêu cầu quay về N"]
~~~

Nếu sự cố xảy ra ngay sau bước C, schema có thể vẫn tương thích và chưa có dữ liệu mới. Rollback N có thể đơn giản.

Nếu sự cố xảy ra sau bước D hoặc E, dữ liệu mới có thể đã xuất hiện. Nếu bước F đã hoàn tất, schema cũ có thể không còn. Cùng một lệnh deploy phiên bản N sẽ có mức độ an toàn khác nhau tùy thời điểm release.

Do đó, quyết định rollback cần dựa trên trạng thái thực tế của migration, writer, dữ liệu và consumer, không chỉ dựa trên số phiên bản ứng dụng.

## 5. Ma trận tương thích giữa phiên bản ứng dụng và schema

Trước khi phát hành, cần biết phiên bản nào có thể chạy với trạng thái schema nào.

| Ứng dụng | Schema cũ | Schema mở rộng | Schema đã contract |
|---|---|---|---|
| N | Tương thích | Có thể tương thích nếu chỉ thêm cấu trúc và N bỏ qua được | Thường không tương thích nếu N cần cấu trúc đã xóa |
| N+1 | Có thể tương thích nếu hỗ trợ cả hai | Tương thích mục tiêu | Tương thích nếu code đã bỏ phụ thuộc cấu trúc cũ |

Ma trận này chỉ nói về schema. Còn cần ma trận dữ liệu:

| Dữ liệu đang tồn tại | N đọc được? | N+1 đọc được? | Điều cần xác minh |
|---|---|---|---|
| Giá trị cũ | Có theo hợp đồng cũ | Phải đọc được | Migration và mapping |
| Giá trị mới | Có thể không | Phải đọc được | Enum, parser, semantics |
| Bản ghi đã backfill | Có thể chỉ đọc bản cũ | Phải đọc được | Đối soát hai biểu diễn |
| Event mới trong queue | Có thể không | Phải đọc được | Consumer compatibility |
| Session/cache mới | Có thể không | Phải đọc được | Serializer và cache version |

Không nên đánh dấu rollback-safe chỉ vì schema còn cột cũ. Cần có bằng chứng rằng dữ liệu do N+1 tạo ra vẫn được N đọc và ghi đúng.

## 6. Những thay đổi dễ phá vỡ rollback

### 6.1. Xóa hoặc đổi tên cột

Nếu N truy vấn cột status_text và migration của N+1 đã DROP cột này, N có thể lỗi ngay khi chạy query. Thêm cột mới trước và giữ cột cũ qua một khoảng tương thích giúp tránh tình huống này.

### 6.2. Thêm enum hoặc trạng thái mới

N có thể dùng enum đóng và parse trực tiếp từ database. Một giá trị mới như REFUNDED có thể gây exception. Nếu có default branch, cần xác minh nó có bảo toàn nghiệp vụ hay chỉ che lỗi.

### 6.3. Đổi kiểu hoặc đơn vị

Chuyển tiền từ đơn vị nhỏ sang đơn vị lớn, đổi timezone, precision hoặc cách mã hóa ID có thể khiến code cũ tính sai dù truy vấn vẫn chạy.

### 6.4. Đổi JSON hoặc serialized object

N có thể từ chối field mới, không đọc được kiểu mới hoặc yêu cầu field đã bị bỏ. Java native serialization còn có thể phụ thuộc class name và serialVersionUID.

### 6.5. Thay đổi quan hệ và constraint

Nếu N+1 chuyển dữ liệu sang bảng mới rồi ngừng cập nhật bảng cũ, N có thể đọc dữ liệu stale. Constraint mới cũng có thể khiến lệnh INSERT/UPDATE của N thất bại.

### 6.6. Event và message mới

Rollback producer không xóa message đã phát. Consumer N có thể nhận event version mới trong queue và lỗi khi deserialize. Phải tính cả backlog, retry queue và dead-letter queue.

### 6.7. Cache và session

Cache có thể chứa payload mới mà N không đọc được. Session đang hoạt động có thể bị lỗi khi N deserialize. Xóa cache chỉ an toàn nếu đó là dữ liệu dẫn xuất có thể tái tạo và đã hiểu tác động tới người dùng.

## 7. Expand-contract giữ khả năng chạy phiên bản cũ

Một chiến lược phổ biến là expand-contract:

1. **Expand:** thêm cột, bảng hoặc field mới mà chưa xóa cấu trúc cũ.
2. **Deploy compatible code:** triển khai phiên bản hiểu được cả trạng thái cũ và mới.
3. **Backfill:** chuyển dữ liệu theo batch, có checkpoint và đối soát.
4. **Switch:** chuyển reader/writer sang cấu trúc mới.
5. **Compatibility window:** giữ cấu trúc và dữ liệu cũ đủ lâu để có thể quay lui.
6. **Contract:** chỉ xóa cấu trúc cũ khi đã xác nhận không còn consumer cần nó.

~~~mermaid
flowchart TD
    A["Schema cũ"] --> B["Expand: thêm cấu trúc mới"]
    B --> C["Deploy code tương thích"]
    C --> D["Backfill và đối soát"]
    D --> E["Switch sang cấu trúc mới"]
    E --> F["Giữ rollback window"]
    F --> G{"Còn cần chạy N?"}
    G -- "Có" --> H["Giữ schema và dữ liệu tương thích"]
    G -- "Không" --> I["Contract trong release riêng"]
~~~

Expand-contract không tự bảo đảm rollback. Code mới vẫn có thể ghi giá trị mà code cũ không hiểu. Cần kết hợp chiến lược schema với chiến lược dữ liệu, event và feature flag.

## 8. Ví dụ migration an toàn hơn

Giả sử bảng orders có cột legacy_status và muốn chuyển sang normalized_status.

Bước expand có thể thêm cột nullable:

~~~sql
ALTER TABLE orders
ADD COLUMN normalized_status VARCHAR(40);
~~~

Phiên bản tương thích có thể đọc normalized_status khi đã có giá trị và fallback về legacy_status trong thời gian chuyển tiếp. Writer cần cập nhật hai biểu diễn theo một quy tắc nhất quán.

Sau đó backfill theo batch:

~~~sql
UPDATE orders
SET normalized_status = map_legacy_status(legacy_status)
WHERE normalized_status IS NULL;
~~~

Đây là SQL minh họa; hàm mapping cần được định nghĩa, kiểm thử và xử lý rõ những giá trị không thể chuyển đổi. Không chạy một UPDATE khổng lồ trên bảng lớn nếu nó có thể tạo lock, transaction dài hoặc tải database vượt ngưỡng.

Sau khi đối soát số lượng và semantics, phiên bản mới có thể chuyển sang đọc cột mới. Cột cũ chỉ được xóa trong một release riêng sau khi rollback window kết thúc và không còn consumer nào phụ thuộc.

## 9. Dual-write không phải bảo đảm tự động

Dual-write thường được dùng để duy trì hai biểu diễn trong thời gian chuyển đổi. Nhưng nếu cập nhật hai nơi không nằm trong cùng transaction hoặc có nhiều writer, hai bản có thể lệch nhau.

Ví dụ các writer bị bỏ sót:

- API chính.
- Worker xử lý queue.
- Batch job ban đêm.
- Công cụ admin.
- Integration từ hệ thống khác.
- Script vận hành thủ công.

Nếu một writer chỉ cập nhật normalized_status, phiên bản N có thể đọc legacy_status cũ. Cần inventory mọi writer, kiểm thử tất cả đường ghi, đo mismatch và có reconciliation.

Khi hai hệ thống lưu trữ độc lập, không nên giả định hai lần ghi sẽ cùng thành công. Cần cân nhắc transactional outbox, CDC, retry idempotent và một nguồn dữ liệu chuẩn được xác định cho từng giai đoạn.

## 10. Feature flag chỉ kiểm soát dữ liệu mới

Feature flag có thể ngăn N+1 tạo thêm giá trị mới trong thời gian nhóm cần giữ khả năng rollback. Ví dụ, code mới đã được deploy nhưng chưa bật trạng thái REFUNDED.

Tuy nhiên, tắt flag không xóa các bản ghi REFUNDED đã tồn tại. Nó cũng không tự chuyển dữ liệu về format cũ, không xóa event trong queue và không hoàn tác payment đã thực hiện.

Cần phân biệt:

- **Disable future writes:** ngăn phát sinh thêm dữ liệu mới.
- **Compatibility conversion:** chuyển hoặc cung cấp adapter để code cũ hiểu dữ liệu đã tồn tại.
- **Compensation:** sửa tác động nghiệp vụ ở hệ thống bên ngoài.
- **Rollback application:** đưa code cũ trở lại nếu các điều kiện tương thích đạt.

Feature flag là một công cụ kiểm soát rollout, không phải nút hoàn tác dữ liệu.

## 11. Down migration không đồng nghĩa phục hồi dữ liệu

Một down migration có thể tái tạo tên cột hoặc cấu trúc bảng, nhưng không nhất thiết khôi phục được dữ liệu đã mất.

Ví dụ:

- Hai trạng thái mới được gộp thành một trạng thái cũ.
- Cột cũ đã bị xóa sau khi dữ liệu được chuyển.
- Precision đã bị làm tròn.
- Một field JSON đã bị loại bỏ.
- Các bản ghi đã được hợp nhất.
- Khóa hoặc quan hệ đã thay đổi.

Nếu chuyển đổi là mất thông tin, down migration không thể suy ra dữ liệu ban đầu. Việc chạy migration ngược có thể tạo ra giá trị giả hoặc làm sai nghiệp vụ.

Chỉ dùng down migration khi đã chứng minh phép biến đổi có thể đảo ngược và dữ liệu phát sinh trong thời gian chạy phiên bản mới vẫn nằm trong miền giá trị hợp lệ của schema cũ. Với thay đổi phá hủy hoặc không đảo ngược, thường an toàn hơn khi giữ schema mở rộng và roll-forward.

## 12. Restore database không phải nút rollback thông thường

Restore hoặc point-in-time recovery (PITR) đưa database về một thời điểm trong quá khứ. Điều đó có thể làm mất các giao dịch hợp lệ đã được ghi sau thời điểm phục hồi.

Trước khi restore cần xác định:

- Mốc thời gian hoặc recovery point chính xác.
- Các giao dịch sau mốc đó có thể bị mất.
- Hệ thống nào đã nhận side effect dựa trên dữ liệu sau mốc đó.
- Queue và consumer có cần pause hoặc replay không.
- Có thể đối soát và tái tạo các giao dịch hợp lệ hay không.
- Mục tiêu RPO/RTO và người có thẩm quyền phê duyệt.

Không nên restore production database chỉ để làm cho code cũ chạy được nếu chưa có kế hoạch bảo toàn giao dịch mới. Có thể cần restore vào môi trường tạm để trích xuất dữ liệu hoặc kiểm chứng, rồi chọn roll-forward/compensation cho production.

Backup là một khả năng phục hồi, không phải bản sao của thao tác rollback ứng dụng.

## 13. Side effect bên ngoài không tự biến mất

Một phiên bản mới có thể đã:

- Capture hoặc refund thanh toán.
- Gửi email/SMS.
- Phát webhook hoặc message.
- Tạo tài nguyên cloud.
- Xuất file sang đối tác.
- Kích hoạt workflow kế toán hoặc fulfillment.

Đưa binary cũ trở lại không đảo ngược những hành động đó. Cần quy trình compensation phù hợp với nghiệp vụ, idempotency key và đối soát trạng thái với nhà cung cấp.

Ví dụ, nếu payment provider đã capture tiền, không được xóa bản ghi giao dịch để làm code cũ hết lỗi. Cần gọi API refund theo quy trình nghiệp vụ, ghi nhận kết quả và giữ correlation ID để truy vết.

## 14. Chọn rollback hay roll-forward?

Rollback không phải luôn là lựa chọn an toàn nhất. Cần đánh giá loại lỗi, trạng thái dữ liệu và khả năng tương thích.

| Tình huống | Hướng xử lý thường phù hợp |
|---|---|
| Lỗi chỉ nằm trong code, schema và dữ liệu vẫn tương thích | Rollback binary |
| Schema chỉ được expand, chưa có giá trị mới không tương thích | Rollback sau compatibility check |
| Dữ liệu mới đã ghi và code cũ không hiểu | Tắt nguồn phát sinh mới, adapter hoặc roll-forward |
| Schema cũ đã bị contract | Recreate/restore có kiểm soát hoặc roll-forward; không chỉ đổi binary |
| Chuyển đổi dữ liệu mất thông tin | Roll-forward hoặc compensation |
| Side effect đã xảy ra bên ngoài | Compensation và reconciliation |
| Chưa biết migration hoặc dữ liệu đã thay đổi thế nào | Dừng thao tác tự động, thu thập bằng chứng trước |

Quyết định cần tính đến tác động người dùng, tính đúng đắn dữ liệu, thời gian phục hồi và nguy cơ làm tình trạng nghiêm trọng hơn. Một bản vá tiến lên có thể phục hồi nhanh và an toàn hơn việc ép phiên bản cũ xử lý dữ liệu mới.

## 15. Quy trình ra quyết định trước khi rollback

Trước khi triển khai lại phiên bản cũ:

1. Xác định artifact cũ bằng version và digest; không build lại một binary gần giống.
2. Ghi lại release ID, commit, schema version và migration đã chạy.
3. Xác định thời điểm N+1 bắt đầu ghi dữ liệu mới.
4. Kiểm tra enum, JSON, kiểu dữ liệu, semantics và quan hệ.
5. Liệt kê API, worker, batch và consumer có thể tiếp tục ghi.
6. Kiểm tra queue backlog, cache, session và external side effect.
7. Chạy binary N trên schema và fixture đại diện cho dữ liệu do N+1 tạo.
8. Xác minh cả read path lẫn write path và invariant nghiệp vụ.
9. Chọn rollback, adapter, compensation hoặc roll-forward.
10. Ghi người phê duyệt, lý do, phạm vi, bằng chứng và kế hoạch xác minh.

Không thử nghiệm binary cũ trực tiếp trên production data nếu chưa cô lập side effect. Có thể dùng bản sao dữ liệu đã được bảo vệ hoặc môi trường rehearsal gần với production.

## 16. Thực hiện rollback có kiểm soát

Khi đã có bằng chứng tương thích:

1. Dừng hoặc giới hạn writer tạo thêm dữ liệu mới không tương thích.
2. Pause worker/consumer nếu chúng có thể xử lý message mới bằng code cũ.
3. Ghi lại trạng thái database và release hiện tại.
4. Triển khai artifact cũ đã được xác minh.
5. Giữ schema mở rộng nếu code cũ có thể bỏ qua cấu trúc mới.
6. Chạy health check và smoke test cho luồng nghiệp vụ trọng yếu.
7. Kiểm tra message backlog, cache, session và external side effect.
8. Đối soát các invariant dữ liệu.
9. Mở lại traffic và worker theo từng bước.
10. Theo dõi error rate, latency, mismatch và retry sau chuyển đổi.

Không tự động chạy down migration cùng lúc đổi binary. Migration schema là quyết định riêng, cần đánh giá khả năng đảo ngược và ảnh hưởng dữ liệu.

## 17. Xác minh sau rollback

Một deployment có trạng thái healthy không có nghĩa dữ liệu đã đúng.

Cần xác minh ít nhất:

- Artifact digest đang chạy đúng bản đã chọn.
- Query của phiên bản cũ không tham chiếu cấu trúc đã mất.
- Không tăng lỗi enum parse hoặc deserialize.
- Bản ghi mới do N+1 tạo vẫn được đọc đúng.
- Writer cũ không bỏ sót dữ liệu hoặc phá invariant.
- Số lượng và tổng hợp nghiệp vụ khớp với kỳ vọng.
- Worker và consumer xử lý được backlog.
- Không phát sinh side effect trùng.
- Cache/session được đọc hoặc tái tạo an toàn.
- SLI/SLO và error budget trở lại mức chấp nhận được.

Nên so sánh trước/sau rollback và lưu bằng chứng theo release ID. Nếu HTTP error giảm nhưng số giao dịch sai hoặc mismatch tăng, hệ thống chưa phục hồi.

## 18. Kiểm thử khả năng rollback trước release

Đừng chờ production có sự cố mới kiểm tra binary cũ.

Một ma trận kiểm thử hữu ích:

| Kiểm thử | Đầu vào | Kết quả mong đợi |
|---|---|---|
| N + expanded schema | Schema chỉ thêm cấu trúc mới | N vẫn hoạt động |
| N + dữ liệu do N+1 ghi | Fixture chứa enum/JSON/format mới | N đọc đúng hoặc từ chối có kiểm soát theo policy |
| N write path | N ghi vào schema mở rộng | Không làm hỏng dữ liệu mới |
| Old consumer + new event | Message do N+1 phát | Consumer đọc được hoặc cách ly rõ ràng |
| Partial backfill | Chỉ một phần record đã chuyển | Không làm mất dữ liệu |
| Retry/replay | Message được giao lại | Không nhân đôi side effect |
| Rollback rehearsal | Binary cũ, schema và cấu hình mục tiêu | Runbook hoàn tất trong RTO |

Cần chạy binary cũ thực sự với database engine/version mục tiêu. Unit test mô phỏng enum parser không thay thế được integration test với schema và dữ liệu thật đại diện.

## 19. Đưa rollback compatibility vào CI/CD gate

Pipeline có thể kiểm tra khả năng chạy phiên bản trước trên trạng thái dữ liệu mà release mới có thể tạo.

~~~mermaid
flowchart TD
    A["Pull request và migration"] --> B["Schema compatibility test"]
    A --> C["Data mapping/semantics test"]
    A --> D["Event contract test"]
    B --> E["Build artifact N+1"]
    C --> E
    D --> E
    E --> F["Tạo fixture từ format N+1"]
    F --> G["Chạy binary N trên schema và fixture mới"]
    G --> H{"N đọc/ghi an toàn?"}
    H -- "Không" --> I["Chặn rollback claim hoặc yêu cầu forward recovery plan"]
    H -- "Có" --> J["Lưu compatibility evidence"]
    J --> K["Cho phép release theo policy"]
~~~

Một compatibility report có thể ghi:

- Artifact digest của N và N+1.
- Database migration version.
- Schema fingerprint.
- Fixture/data format version.
- Kết quả read/write test của N.
- Event schema và consumer version.
- Các giới hạn rollback đã biết.
- Kế hoạch roll-forward nếu không tương thích.

Nếu test không đạt, release vẫn có thể được xem xét theo một policy khác, nhưng phải công khai rằng rollback về N không được bảo đảm và có phương án phục hồi thay thế đã được review.

## 20. Quản lý rollback window và artifact cũ

Rollback window là khoảng thời gian tổ chức cam kết có thể đưa phiên bản trước trở lại theo quy trình đã kiểm chứng.

Thời hạn này cần dựa trên:

- Chu kỳ phát hiện lỗi.
- Thời gian tồn tại của queue message.
- Lịch chạy batch hoặc báo cáo ít thường xuyên.
- Thời gian quan sát canary/production.
- Vòng đời hỗ trợ artifact.
- Thời gian cần để điều tra security finding.

Giữ artifact cũ bất biến theo digest. Lưu cả release manifest, schema/migration version, cấu hình cần thiết và kết quả compatibility test. Không nên chỉ giữ tag dễ bị ghi đè hoặc dựa vào việc build lại source cũ sau nhiều tháng.

Hết rollback window không có nghĩa hệ thống không thể phục hồi. Nó có nghĩa phương án quay lại binary trước không còn được cam kết là an toàn; khi đó cần dựa vào roll-forward, backup/PITR hoặc compensation đã được diễn tập.

## 21. Ví dụ thực tế: trạng thái REFUNDED

Giả sử N chỉ biết PENDING, PAID và CANCELLED. N+1 thêm REFUNDED sau khi refund thành công.

Nếu N+1 có lỗi và nhóm rollback về N:

- Database vẫn trả về dòng đơn hàng.
- Parser enum của N có thể ném exception.
- API đọc đơn hàng refund có thể trả 500.
- Worker cũ có thể retry message không tương thích.
- Dashboard có thể báo số liệu thiếu nếu chỉ đếm ba trạng thái cũ.

Các quyết định hợp lý:

**Trước khi bật tính năng:** nếu cần giữ khả năng rollback về N, phải có bản N hiểu unknown status hoặc adapter an toàn. Nếu không có cách tương thích, chưa bật tính năng tạo giá trị mới trong rollback window.

**Sau khi đã ghi REFUNDED:** không map tùy tiện thành CANCELLED hoặc PAID chỉ để parser cũ không lỗi. Giữ nguyên sự thật nghiệp vụ, dừng phát sinh mới nếu cần và phát hành bản sửa có thể đọc dữ liệu đó.

**Nếu cần khôi phục dịch vụ nhanh:** ưu tiên một bản sửa tương thích hoặc roll-forward. Việc xóa bản ghi refund có thể che lỗi giao diện nhưng sẽ làm sai lịch sử thanh toán.

## 22. Những anti-pattern thường gặp

| Ngộ nhận hoặc hành vi | Hệ quả | Cách sửa |
|---|---|---|
| Rollback binary là rollback toàn hệ thống | Database và side effect vẫn ở trạng thái mới | Đánh giá từng lớp trạng thái |
| Migration luôn có thể chạy ngược | Dữ liệu mất thông tin không thể tái tạo | Kiểm tra tính đảo ngược trước khi chạy |
| Schema còn cột cũ là đủ | Giá trị mới có thể không được code cũ hiểu | Test dữ liệu và semantics |
| Tắt feature flag sẽ hoàn tác dữ liệu | Record và event mới vẫn tồn tại | Chặn ghi mới, chuyển đổi hoặc roll-forward |
| Restore backup là thao tác nhanh và vô hại | Mất giao dịch sau recovery point | Đánh giá RPO, replay và đối soát |
| Health check xanh chứng minh dữ liệu đúng | Sai nghiệp vụ vẫn có thể tồn tại | Kiểm tra invariant và luồng đọc/ghi |
| Chỉ kiểm thử phiên bản mới | Không biết phiên bản cũ có chạy được không | Test binary cũ trên schema/fixture mới |
| Rollback ngay khi alert phát | Có thể làm lỗi nặng hơn | Chạy preflight và decision matrix |
| Build lại artifact cũ khi sự cố | Binary có thể khác bản đã chạy | Dùng artifact bất biến theo digest |
| Bỏ qua queue và external system | Consumer hoặc side effect tiếp tục lỗi | Pause, reconcile và compensation |

## 23. Checklist trước khi tuyên bố rollback an toàn

**Ứng dụng và schema**

- [ ] Artifact cũ được xác định bằng digest.
- [ ] Migration đã chạy được liệt kê đầy đủ.
- [ ] Schema hiện tại tương thích với binary cũ.
- [ ] Cấu trúc cũ chưa bị contract hoặc có kế hoạch khôi phục rõ ràng.
- [ ] JDK/runtime, config, secret và permission còn phù hợp.

**Dữ liệu và nghiệp vụ**

- [ ] Đã xác định dữ liệu mới do phiên bản hiện tại tạo.
- [ ] Enum, JSON, kiểu dữ liệu và semantics được kiểm tra.
- [ ] Read path và write path của phiên bản cũ đã được thử.
- [ ] Invariant và số liệu nghiệp vụ vẫn đúng.
- [ ] Backfill/dual-write đã được đối soát.

**Hệ thống phụ thuộc**

- [ ] Queue, backlog và dead-letter được đánh giá.
- [ ] Cache và session tương thích hoặc có kế hoạch xử lý.
- [ ] External side effect có compensation/reconciliation.
- [ ] Writer và consumer được dừng/mở lại theo trình tự.

**Thực hiện và bằng chứng**

- [ ] Có quyết định rollback hay roll-forward.
- [ ] Không chạy down migration phá hủy dữ liệu một cách tự động.
- [ ] Có runbook, người phê duyệt và điều kiện dừng.
- [ ] Có smoke test và post-rollback verification.
- [ ] Có release ID, migration version và evidence được lưu.

## 24. Kết luận

Rollback ứng dụng chỉ đưa code về phiên bản trước. Nó không tự đảo schema, dữ liệu, event trong queue, cache, session hoặc side effect đã xảy ra ở hệ thống bên ngoài. Vì vậy, giả định rằng rollback binary đồng nghĩa dữ liệu an toàn là một lỗi tư duy có thể làm sự cố nghiêm trọng hơn.

Muốn giữ khả năng quay lui, cần thiết kế expand-contract, duy trì tương thích giữa các phiên bản, kiểm soát thời điểm phát sinh giá trị mới, lưu artifact bất biến và kiểm thử binary cũ trên schema cùng dữ liệu do bản mới tạo. Khi dữ liệu đã thay đổi không thể đảo ngược, roll-forward hoặc compensation thường là hướng phục hồi phù hợp hơn.

Một quyết định rollback tốt dựa trên trạng thái thực tế và bằng chứng: migration nào đã chạy, dữ liệu nào đã được ghi, consumer nào còn hoạt động và invariant nào cần được xác minh. Hãy xem rollback là một quy trình phục hồi nhiều lớp có điều kiện, không phải một nút đưa toàn hệ thống trở về quá khứ.
