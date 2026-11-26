# Đối soát projection

Projection và read model được cập nhật từ application events để phục vụ truy vấn nhanh. Vì việc cập nhật thường diễn ra bất đồng bộ, read model có thể trễ hơn dữ liệu ghi hoặc gặp sai lệch do event bị xử lý lặp, đến sai thứ tự, bị bỏ sót hay logic projection thay đổi. **Đối soát projection** là quy trình kiểm tra xem read model có còn phản ánh đúng nguồn dữ liệu có thẩm quyền theo các quy tắc nghiệp vụ đã định nghĩa hay không.

Đối soát giúp phát hiện drift trước khi người dùng hoặc hệ thống downstream dựa vào dữ liệu sai. Quy trình cần xác định nguồn so sánh, thời điểm dữ liệu được chụp, mức sai lệch được chấp nhận và cách sửa. Một phép so sánh hai bảng tại hai thời điểm khác nhau có thể tạo ra cảnh báo giả; vì vậy, watermark, snapshot và độ trễ event là những phần quan trọng của thiết kế.

## 1. Projection drift là gì?

Projection drift là trạng thái read model không còn khớp với dữ liệu mà nó phải biểu diễn. Sai lệch có thể xuất hiện ở một record, một aggregate, một nhóm dữ liệu hoặc toàn bộ projection.

Ví dụ, module Orders lưu trạng thái đơn hàng có thẩm quyền trong write model. Một projection phục vụ màn hình tổng hợp trạng thái đơn. Khi event OrderPaid không được xử lý, write model đã chuyển sang PAID nhưng read model vẫn hiển thị PENDING. Đây là một dạng drift.

Một số nguyên nhân thường gặp:

- Listener bị lỗi và publication chưa hoàn tất.
- Event bị giao lại nhưng handler không idempotent, làm tăng tổng tiền hoặc counter hai lần.
- Event đến sai thứ tự và handler áp dụng trạng thái cũ sau trạng thái mới.
- Một phiên bản projection có bug hoặc công thức tính sai.
- Event schema thay đổi nhưng consumer không deserialize hoặc upcast đúng.
- Dữ liệu được sửa trực tiếp ở write database mà không phát event tương ứng.
- Một lần migration hoặc rebuild không đọc đủ dữ liệu.
- Projection write thành công nhưng checkpoint hoặc offset được ghi không nhất quán.
- Cache hoặc index downstream chưa được cập nhật sau khi database projection đã đổi.

Không phải mọi khác biệt đều là drift. Projection có thể được thiết kế để chỉ chứa một tập trường hoặc một trạng thái rút gọn. Đối soát phải so sánh các giá trị có cùng ý nghĩa nghiệp vụ, không yêu cầu read model giống hệt cấu trúc write model.

## 2. Xác định nguồn có thẩm quyền

Trước khi đối soát, xác định đâu là nguồn dữ liệu có thẩm quyền cho từng thuộc tính. Read model thường là bản sao phục vụ truy vấn; khi có xung đột, không nên tự coi projection là nguồn đúng.

| Nguồn | Vai trò trong đối soát | Điều cần lưu ý |
|---|---|---|
| Write model / aggregate database | Nguồn hiện trạng có thẩm quyền cho trạng thái nghiệp vụ hiện tại | Có thể không lưu lịch sử của các trạng thái cũ |
| Event store hoặc event log đầy đủ | Nguồn để tái dựng trạng thái theo lịch sử event | Cần retention, thứ tự, schema cũ và quy tắc upcast |
| Kafka topic còn retention | Có thể dùng để đối chiếu hoặc replay trong phạm vi record còn lưu | Offset và retention không bảo đảm có toàn bộ lịch sử |
| Snapshot có checkpoint | Nguồn trạng thái tại một thời điểm kết hợp với event sau checkpoint | Phải biết snapshot đã bao gồm event nào |
| Projection hiện tại | Đối tượng được kiểm tra | Không dùng chính projection làm nguồn chuẩn để kết luận nó đúng |

**Spring Modulith Event Publication Registry** theo dõi publication của event tới listener và giúp phục hồi publication chưa hoàn tất. Registry không mặc định là event store đầy đủ. Không thể chỉ đọc registry để đối soát mọi trạng thái nghiệp vụ trong quá khứ nếu ứng dụng không lưu lịch sử event riêng.

Đối với projection hiện trạng, write model thường là nguồn so sánh phù hợp. Đối với projection lịch sử, cần event store, audit log hoặc archive có khả năng tái dựng. Đối với dữ liệu tổng hợp nhiều nguồn, có thể cần một quy tắc đối soát riêng cho từng phần của kết quả.

Ghi rõ nguồn có thẩm quyền trong tài liệu vận hành. Nếu một trường có nguồn chuẩn khác với trường còn lại, quy tắc phải thể hiện điều đó thay vì chọn một bảng chung cho tất cả.

## 3. Chọn phạm vi và mức đối soát

Không phải lúc nào cũng cần quét toàn bộ projection. Có thể tổ chức nhiều mức:

| Mức | Phạm vi | Mục đích |
|---|---|---|
| Kiểm tra nhanh | Số lượng record, tổng hợp, checkpoint và tuổi dữ liệu | Phát hiện bất thường lớn với chi phí thấp |
| Đối soát theo phân vùng | Một tenant, ngày, partition hoặc nhóm aggregate | Khoanh vùng drift và giới hạn tải |
| Đối soát theo aggregate | So sánh trạng thái từng đơn hàng, tài khoản hoặc reservation | Xác định record cụ thể bị sai |
| Đối soát toàn bộ | Quét toàn bộ tập dữ liệu theo snapshot nhất quán | Xác nhận mức độ chính xác tổng thể hoặc sau migration |

Có thể chạy kiểm tra tổng hợp thường xuyên và chạy đối soát chi tiết theo lịch. Khi có cảnh báo, mở rộng phạm vi từ nhóm dữ liệu bị ảnh hưởng sang record cụ thể để tìm nguyên nhân.

Định nghĩa trước những trường cần so sánh. Ví dụ, projection OrderSummary có thể cần khớp order ID, trạng thái, tổng tiền, currency và aggregate version. Các trường hiển thị như label, mô tả hoặc giá trị được format có thể có quy tắc so sánh riêng.

## 4. Xử lý eventual consistency và watermark

Trong hệ thống event-driven, write model và projection không nhất thiết cập nhật cùng một thời điểm. Nếu đối soát ngay sau khi write transaction commit, event có thể chưa được listener xử lý. Kết quả so sánh sẽ báo thiếu dữ liệu dù hệ thống đang hoạt động đúng.

Cần định nghĩa watermark hoặc thời điểm mà hai phía có thể được so sánh công bằng. Watermark biểu thị giới hạn dữ liệu đã được xử lý hoặc một vị trí có thể xác định trong luồng event.

Ví dụ:

~~~text
Write model commits event e101
          |
          v
Event publication recorded
          |
          v
Listener receives e101
          |
          v
Projection updated through e101
          |
          v
Projection checkpoint advances to e101
          |
          v
Reconciliation compares state at compatible watermark
~~~

Với Kafka, watermark có thể là offset theo từng partition. Với event store theo aggregate, có thể là stream version. Với database có snapshot, có thể dùng transaction snapshot hoặc một mốc thời gian được xác định cùng checkpoint. Không coi offset của các partition khác nhau là một sequence toàn cục.

Một quy trình đối soát có thể:

1. Ghi nhận watermark nguồn hoặc checkpoint cần kiểm tra.
2. Xác định projection đã xử lý tới watermark nào.
3. Chờ hoặc đánh dấu các aggregate chưa bắt kịp là pending.
4. Chỉ so sánh phần dữ liệu đã đủ điều kiện.
5. Ghi lại watermark và thời điểm đối soát để lần sau có thể tái hiện kết quả.

Nếu projection không lưu checkpoint theo aggregate hoặc partition, có thể cần thêm metadata để biết dữ liệu nào đã được xử lý. Trạng thái publication incomplete trong Event Publication Registry hữu ích để điều tra listener còn lỗi, nhưng không thay thế checkpoint tổng hợp của toàn bộ read model.

## 5. So sánh dữ liệu theo khóa nghiệp vụ

Đối soát theo record nên dùng khóa ổn định, ví dụ order ID hoặc account ID. Tránh ghép dữ liệu bằng tên hiển thị, email hoặc trường có thể thay đổi.

Một phép so sánh có thể chia thành ba nhóm:

- **Thiếu ở projection:** nguồn có record nhưng read model chưa có.
- **Thừa ở projection:** read model có record nhưng nguồn hiện tại không còn hoặc record không thuộc phạm vi projection.
- **Khác giá trị:** cùng khóa nhưng một hoặc nhiều thuộc tính khác nhau.

Ví dụ SQL so sánh trạng thái đơn hàng:

~~~sql
SELECT
    source.order_id,
    source.status AS source_status,
    projection.status AS projection_status,
    source.version AS source_version,
    projection.last_event_version AS projection_version
FROM orders AS source
LEFT JOIN order_summary_projection AS projection
    ON projection.order_id = source.order_id
WHERE projection.order_id IS NULL
   OR source.status <> projection.status
   OR source.version <> projection.last_event_version;
~~~

Đây là truy vấn minh họa. Tên bảng, kiểu version và quy tắc null cần điều chỉnh theo schema thực tế. Muốn phát hiện record thừa ở projection, cần thêm phép so sánh chiều ngược lại hoặc dùng FULL OUTER JOIN nếu database hỗ trợ.

Với bảng lớn, không nên chạy một truy vấn full scan không giới hạn trong giờ cao điểm. Chia theo range khóa hoặc tenant, dùng index phù hợp, giới hạn batch và theo dõi thời gian truy vấn. Nếu hai bảng nằm ở các hệ thống khác nhau, có thể export checksum hoặc tập khóa theo batch rồi so sánh ở một job điều phối.

## 6. Đối soát dữ liệu tổng hợp

Projection thường chứa dữ liệu đã tổng hợp, ví dụ số đơn theo trạng thái, tổng doanh thu theo ngày hoặc số lượng hàng tồn theo kho. Khi đó, so sánh từng record có thể tốn kém; có thể bắt đầu bằng các invariant tổng hợp.

Ví dụ:

~~~sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM order_summary_projection
GROUP BY status;
~~~

Kết quả được so sánh với phép tổng hợp tương ứng từ nguồn có thẩm quyền trong cùng phạm vi thời gian và watermark.

Một số invariant thường hữu ích:

- Tổng số record theo nhóm trạng thái.
- Tổng số tiền theo currency; không cộng các currency khác nhau nếu chưa có quy tắc quy đổi.
- Tổng số lượng theo kho hoặc sản phẩm.
- Min/max timestamp hoặc version.
- Số lượng record có trường bắt buộc bị null.
- Số khóa duy nhất và số khóa trùng.

Checksum hoặc hash theo nhóm có thể giúp khoanh vùng nhanh. Tuy nhiên, checksum chỉ cho biết hai tập dữ liệu có khả năng khác nhau; nó không giải thích record nào sai. Khi checksum lệch, tiếp tục chia nhỏ phạm vi hoặc so sánh theo khóa để tìm sai khác.

Đảm bảo phép tổng hợp ở hai phía có cùng quy tắc về null, rounding, timezone, soft delete và trạng thái đã hủy. Nếu một phía tính theo UTC day còn phía kia theo local day, tổng theo ngày có thể lệch dù từng event đều đúng.

## 7. Phân loại sai lệch trước khi sửa

Không nên tự động ghi đè projection ngay khi phát hiện một khác biệt. Trước hết, phân loại nguyên nhân:

| Loại sai lệch | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Projection lag | Projection có version thấp hơn nguồn và event vẫn đang chờ | Kiểm tra consumer/listener lag, publication incomplete và retry |
| Missing event | Nguồn đã đổi nhưng projection không có thay đổi tương ứng | Kiểm tra transaction publish, registry, transport và offset |
| Duplicate application | Counter hoặc tổng tiền cao hơn nguồn | Kiểm tra event ID, idempotency và redelivery |
| Out-of-order event | Trạng thái hoặc version bị lùi | Kiểm tra key, partition, aggregate sequence và handler |
| Mapping/calculation bug | Nhiều record sai cùng một công thức | Kiểm tra projection mapper và phiên bản logic |
| Schema incompatibility | Một nhóm event không được đọc hoặc chuyển đổi | Kiểm tra serializer, consumer version và upcaster |
| Source mutation ngoài luồng event | Write model đổi nhưng không có event tương ứng | Kiểm tra quy trình cập nhật dữ liệu và audit |
| Stale cache/index | Database projection đúng nhưng API hoặc search trả dữ liệu cũ | Kiểm tra cache invalidation và downstream indexer |

Một sai lệch chỉ do projection lag thường có thể tự biến mất sau khi listener xử lý xong. Một sai lệch do bug mapping cần sửa logic và có thể yêu cầu rebuild. Một sai lệch do dữ liệu nguồn bị sửa thủ công cần xử lý ở quy trình nguồn và phát event bù phù hợp.

Ghi lại loại sai lệch, số record, watermark và bằng chứng trước khi repair. Điều này giúp phân biệt sự cố mới với drift lặp lại từ cùng một nguyên nhân.

## 8. Repair projection có kiểm soát

Có ba hướng khắc phục phổ biến:

1. **Retry hoặc resubmit:** phù hợp khi publication chưa hoàn tất do lỗi tạm thời và event còn hợp lệ.
2. **Reapply event hoặc cập nhật lại một aggregate:** phù hợp khi có nguồn lịch sử đáng tin cậy và handler có thể chạy lại an toàn.
3. **Rebuild generation:** phù hợp khi logic projection thay đổi, nhiều record sai hoặc không thể sửa từng record một cách đáng tin cậy.

Không cập nhật ngược write model chỉ để làm cho nó khớp với projection. Read model là dữ liệu dẫn xuất; nếu projection sai, sửa projection từ nguồn chuẩn. Nếu nguồn chuẩn sai, sửa qua nghiệp vụ hoặc quy trình quản trị dữ liệu tương ứng rồi phát event/audit theo quy định.

Repair cần idempotent và có audit. Mỗi lần sửa nên lưu:

- Reconciliation run ID.
- Projection name và generation.
- Aggregate/key bị ảnh hưởng.
- Giá trị trước và sau.
- Nguồn hoặc event dùng để tái tính.
- Lý do, thời điểm và người hoặc job thực hiện.
- Kết quả xác minh sau repair.

Với thay đổi nhiều record, nên tạo generation mới, rebuild, validate và cutover thay vì ghi đè trực tiếp bảng đang phục vụ query. Cách này giúp rollback nếu kết quả sửa không đạt yêu cầu.

## 9. Thiết kế reconciliation job

Một job đối soát có thể được tách thành các bước:

~~~text
Schedule / manual trigger
          |
          v
Create reconciliation run
          |
          v
Choose scope and watermark
          |
          v
Read authoritative source
          |
          v
Compare with projection
          |
          v
Classify discrepancies
          |
          +---- No drift ----> Mark run successful
          |
          +---- Drift found --> Persist discrepancy report
                                    |
                                    v
                              Repair policy
                                    |
                                    v
                              Verify again
~~~

Job cần lưu trạng thái để có thể tiếp tục hoặc điều tra sau khi process dừng. Một bảng run metadata có thể như sau:

~~~sql
CREATE TABLE projection_reconciliation_run (
    run_id VARCHAR(40) PRIMARY KEY,
    projection_name VARCHAR(100) NOT NULL,
    scope_key VARCHAR(200),
    source_watermark VARCHAR(300),
    projection_watermark VARCHAR(300),
    status VARCHAR(30) NOT NULL,
    mismatch_count BIGINT NOT NULL DEFAULT 0,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);
~~~

Một bảng discrepancy riêng có thể lưu khóa bị lệch, loại sai lệch, giá trị hoặc checksum hai phía và trạng thái repair. Không nhất thiết lưu toàn bộ payload nghiệp vụ; chỉ lưu đủ dữ liệu để điều tra mà không sao chép thông tin nhạy cảm không cần thiết.

Job nên có chế độ **report-only** trước khi bật auto-repair. Trong giai đoạn đầu, thu thập kết quả và xác minh quy tắc so sánh. Sau khi hiểu các loại sai lệch và mức độ an toàn, mới bật repair cho những trường hợp có thể xử lý tự động.

## 10. Đối soát định kỳ và theo yêu cầu

Đối soát có thể chạy theo lịch hoặc được kích hoạt bởi sự cố:

- **Định kỳ:** kiểm tra toàn bộ hoặc theo partition trong khoảng thời gian xác định để phát hiện drift tích lũy.
- **Theo sự kiện:** chạy lại đối soát cho aggregate có dấu hiệu bất thường, ví dụ sau retry hoặc khi support báo dữ liệu sai.
- **Sau triển khai:** kiểm tra projection sau khi thay listener, mapper, schema hoặc cách tính.
- **Sau rebuild/migration:** xác nhận generation mới khớp với nguồn và đạt watermark.
- **Theo yêu cầu vận hành:** chạy report-only cho một tenant hoặc một nhóm dữ liệu cần kiểm tra.

Tần suất phụ thuộc SLA và chi phí. Projection phục vụ số dư hoặc tồn kho có thể cần đối soát thường xuyên hơn một dashboard phân tích không yêu cầu cập nhật tức thời. Không đặt lịch quá dày nếu truy vấn đối soát cạnh tranh tài nguyên với workload nghiệp vụ.

Với tập dữ liệu lớn, có thể chạy incremental reconciliation trên phần dữ liệu thay đổi từ lần chạy trước, đồng thời chạy full reconciliation thưa hơn để phát hiện drift bị bỏ sót. Incremental cần một nguồn change tracking đáng tin cậy; chỉ dựa vào updatedAt có thể bỏ sót cập nhật nếu đồng hồ hoặc precision không đồng nhất.

## 11. Quan sát và cảnh báo

Đối soát chỉ có ích khi kết quả được theo dõi và chuyển thành hành động. Nên quan sát:

| Chỉ số | Ý nghĩa |
|---|---|
| Reconciliation run status | Tỷ lệ run thành công, thất bại hoặc bị gián đoạn |
| Records scanned | Phạm vi dữ liệu đã kiểm tra |
| Mismatch count/rate | Số lượng và tỷ lệ sai lệch |
| Mismatch by category | Phân bố lag, missing, duplicate, out-of-order hoặc mapping |
| Oldest projection lag | Độ trễ lâu nhất của read model |
| Repair success rate | Tỷ lệ repair đã được xác minh |
| Reconciliation duration | Chi phí và thời gian đối soát |
| Unresolved discrepancy age | Sai lệch chưa xử lý đã tồn tại bao lâu |

Cảnh báo cần dựa trên ngưỡng có ý nghĩa nghiệp vụ. Một mismatch đơn lẻ có thể là lag trong cửa sổ eventual consistency; mismatch kéo dài sau watermark hoặc tăng nhanh theo thời gian cần được điều tra. Với projection quan trọng, cảnh báo khi run không hoàn thành hoặc dữ liệu vượt SLA stale.

Log nên có run ID, projection name, generation, scope, watermark, key, discrepancy category và repair ID. Không ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log.

## 12. Kiểm thử đối soát

Kiểm thử cần bao gồm cả tình huống đúng và các dạng drift:

1. Tạo write model và projection khớp nhau; reconciliation không báo mismatch.
2. Cố ý bỏ một record ở projection; job phát hiện missing projection row.
3. Tạo record thừa; job phát hiện orphan row.
4. Thay đổi trạng thái hoặc amount; job báo đúng field khác nhau.
5. Tạo projection lag trước watermark; job đánh dấu pending hoặc chờ thay vì kết luận sai ngay.
6. Giao lại cùng event; handler idempotent và reconciliation không phát hiện tổng bị nhân đôi.
7. Gửi event sai thứ tự; version check phát hiện hoặc ngăn trạng thái bị lùi.
8. Chạy repair rồi đối soát lại; mismatch đã xử lý biến mất và audit được lưu.
9. Mô phỏng job dừng giữa batch; lần chạy tiếp theo tiếp tục hoặc khởi động lại theo checkpoint an toàn.
10. Kiểm tra report-only không thay đổi dữ liệu projection hoặc write model.

Với phép tính tiền, so sánh theo quy tắc decimal và rounding đã công bố. Với timestamp, chuẩn hóa timezone và precision trước khi so sánh. Tránh dùng chuỗi format theo locale hoặc so sánh floating point bằng phép bằng tuyệt đối nếu dữ liệu được biểu diễn theo số gần đúng.

## 13. Checklist trước khi đưa vào production

Trước khi bật reconciliation job, xác nhận:

- Projection và từng trường có nguồn dữ liệu có thẩm quyền rõ ràng.
- Phạm vi và tần suất đối soát phù hợp với SLA và tải hệ thống.
- Watermark hoặc snapshot bảo đảm hai phía được so sánh ở trạng thái tương thích.
- Quy tắc so sánh xử lý đúng null, timezone, decimal, rounding, soft delete và version.
- Sai lệch được phân loại trước khi chọn retry, repair hay rebuild.
- Auto-repair chỉ bật cho trường hợp đã chứng minh an toàn và idempotent.
- Mọi repair có audit, run ID và khả năng xác minh lại.
- Job có checkpoint, batch limit, timeout và cơ chế tránh chạy trùng.
- Metric, cảnh báo, dashboard và owner xử lý discrepancy đã được xác định.
- Có quy trình report-only, rollback và escalation cho sai lệch không thể tự động sửa.

Đối soát projection là vòng kiểm soát chất lượng cho read model được cập nhật bằng event. Khi so sánh đúng nguồn, dùng watermark tương thích, phân loại nguyên nhân và repair có audit, ứng dụng có thể phát hiện drift sớm mà không làm ảnh hưởng dữ liệu nghiệp vụ có thẩm quyền. Kết quả đối soát cũng cung cấp bằng chứng để quyết định khi nào cần retry, sửa projection riêng lẻ hoặc rebuild toàn bộ generation.

