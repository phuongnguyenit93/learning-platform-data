# Phân biệt quay lui mã ứng dụng với phục hồi dữ liệu

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt rollback mã ứng dụng, rollback schema migration và phục hồi dữ liệu.
- Giải thích vì sao triển khai lại phiên bản ứng dụng cũ không tự đảo ngược dữ liệu đã bị thay đổi.
- Chọn giữa rollback ứng dụng, forward fix, restore từ backup, point-in-time recovery và phục hồi có chọn lọc.
- Đánh giá ảnh hưởng của các thao tác ghi dữ liệu sau khi phiên bản mới được triển khai.
- Thiết kế migration tương thích để phiên bản cũ và mới có thể cùng hoạt động trong giai đoạn chuyển tiếp.
- Xác định RPO, RTO, phạm vi phục hồi và cách xác minh tính nhất quán sau recovery.
- Tổ chức quyết định phục hồi trong pipeline CI/CD với quyền, bằng chứng, audit và kế hoạch diễn tập.

## 1. Vì sao phải phân biệt rollback mã và phục hồi dữ liệu?

Khi một lần phát hành gây lỗi, phản xạ thường gặp là quay ứng dụng về phiên bản trước. Đây là một biện pháp hữu ích, nhưng chỉ khôi phục mã và cấu hình ứng dụng về trạng thái trước đó. Nó không tự động đảo ngược những thay đổi đã xảy ra trong database, message queue, object storage hoặc hệ thống bên ngoài.

Ví dụ:

1. Phiên bản ứng dụng V2 được triển khai.
2. V2 ghi dữ liệu đơn hàng theo schema mới và chuyển trạng thái một số bản ghi.
3. Một lỗi được phát hiện.
4. Đội ngũ triển khai lại V1.
5. V1 không hiểu dữ liệu mà V2 đã ghi.

Ứng dụng đã quay lại phiên bản cũ, nhưng dữ liệu vẫn ở trạng thái mới. Nếu V1 đọc sai, ghi đè hoặc bỏ qua các trường mới, việc rollback mã có thể làm sự cố nghiêm trọng hơn.

Cũng có tình huống ngược lại: ứng dụng bị lỗi nhưng dữ liệu vẫn hợp lệ. Khi đó rollback mã có thể đủ để khôi phục dịch vụ; restore database sẽ tạo rủi ro mất các giao dịch hợp lệ phát sinh sau thời điểm backup.

Vì vậy cần phân biệt ba hoạt động:

| Hoạt động | Đối tượng được thay đổi | Mục tiêu |
|---|---|---|
| Application rollback | Binary, container image, package hoặc application revision | Quay ứng dụng về phiên bản đã biết là tốt |
| Schema migration rollback | Cấu trúc database hoặc schema version | Đảo ngược thay đổi cấu trúc nếu việc đó an toàn và khả thi |
| Data recovery | Bản ghi, database, volume, object hoặc event state | Khôi phục dữ liệu bị mất, hỏng hoặc thay đổi sai |

Ba hoạt động có thể cần phối hợp, nhưng không thay thế cho nhau.

Nguyên tắc cốt lõi:

> Quay lui mã chỉ thay đổi chương trình sẽ chạy. Phục hồi dữ liệu thay đổi trạng thái dữ liệu đã được ghi. Trước khi chọn hành động, phải xác định chính xác phần nào bị lỗi và những thay đổi nào đã xảy ra.

## 2. Những trạng thái nào có thể thay đổi trong một lần phát hành?

Một ứng dụng production thường không chỉ có một artifact. Hành vi của nó phụ thuộc vào nhiều loại trạng thái:

- **Application code:** JAR, binary, container image, package và thư viện được đóng gói.
- **Database schema:** bảng, cột, index, constraint, stored procedure và migration version.
- **Business data:** khách hàng, đơn hàng, thanh toán, tồn kho, quyền và trạng thái nghiệp vụ.
- **Event và message:** message trong broker, event log, consumer offset và trạng thái xử lý.
- **Object/file storage:** file tải lên, tài liệu, ảnh và blob.
- **Runtime configuration:** feature flag, endpoint, giới hạn và tham số nghiệp vụ.
- **External state:** giao dịch thanh toán, email đã gửi, webhook hoặc thao tác trên hệ thống đối tác.

Một release có thể thay đổi nhiều loại trạng thái cùng lúc. Ví dụ migration thêm cột, ứng dụng bắt đầu ghi cột mới, consumer xử lý event mới và một job nền chuyển đổi dữ liệu cũ.

Khi xảy ra sự cố, cần lập timeline:

1. Artifact và config nào đã được triển khai?
2. Migration nào đã chạy?
3. Từ thời điểm nào phiên bản mới bắt đầu ghi dữ liệu?
4. Có bao nhiêu bản ghi hoặc event đã bị thay đổi?
5. Những hệ thống bên ngoài nào đã nhận side effect?
6. Lỗi bắt đầu lúc nào và đã kéo dài bao lâu?
7. Có backup, transaction log hoặc event log nào bao phủ khoảng thời gian đó?

Không có timeline, đội ngũ dễ chọn một hành động phục hồi quá rộng hoặc làm mất dữ liệu hợp lệ.

## 3. Application rollback làm được gì và không làm được gì?

Application rollback thường thay phiên bản đang chạy bằng một artifact đã phát hành trước đó.

Ví dụ:

~~~text
Trước release:
  application = V1
  database schema = S1

Sau release:
  application = V2
  database schema = S2
  business data = D2

Rollback application:
  application = V1
  database schema = S2
  business data = D2
~~~

Kết quả cuối cùng không phải trạng thái ban đầu V1 + S1 + D1. Chỉ ứng dụng được quay về V1; schema và business data vẫn ở trạng thái đã thay đổi.

Application rollback phù hợp khi:

- Lỗi nằm trong code mới.
- Dữ liệu vẫn hợp lệ và tương thích với phiên bản cũ.
- Schema mới vẫn tương thích ngược.
- Các side effect đã tạo không gây hỏng dữ liệu khi phiên bản cũ tiếp tục chạy.
- Có artifact cũ đã được xác minh và còn khả năng triển khai.

Application rollback không đủ khi:

- Dữ liệu đã bị xóa hoặc ghi sai.
- Migration đã loại bỏ cột mà phiên bản cũ cần.
- Giá trị mới không thể được phiên bản cũ parse.
- Consumer đã xử lý event theo semantics mới.
- Một thao tác bên ngoài đã xảy ra và cần bù trừ.
- Lỗi bắt nguồn từ cấu hình hoặc trạng thái dữ liệu chứ không phải code.

Cần kiểm tra tương thích trước khi rollback. Việc image cũ còn trong registry chỉ chứng minh có thể tải lại image, không chứng minh ứng dụng cũ có thể chạy an toàn trên schema và dữ liệu hiện tại.

## 4. Phục hồi dữ liệu là gì?

Data recovery là quá trình đưa dữ liệu về trạng thái nhất quán và có thể sử dụng sau khi xảy ra mất mát, hỏng hoặc thay đổi ngoài ý muốn.

Nguồn phục hồi có thể gồm:

- Database backup đầy đủ.
- Incremental hoặc differential backup.
- Transaction log, write-ahead log hoặc binary log.
- Point-in-time recovery (PITR).
- Snapshot của volume hoặc storage.
- Event log hoặc message archive.
- Bản sao dữ liệu đã được kiểm chứng.
- Bản ghi audit hoặc nguồn dữ liệu chuẩn khác.

Phục hồi dữ liệu có thể được thực hiện ở nhiều phạm vi:

- Một bản ghi hoặc một nhóm bản ghi.
- Một bảng hoặc một partition.
- Một database.
- Một cluster hoặc một hệ thống lưu trữ.
- Một tập dữ liệu liên quan qua nhiều dịch vụ.

Phạm vi càng rộng thì khả năng khôi phục đồng bộ càng khó và nguy cơ ghi đè dữ liệu hợp lệ càng cao.

Restore từ backup thường đưa dữ liệu về một thời điểm trong quá khứ. Những thay đổi hợp lệ sau thời điểm đó có thể bị mất nếu không được replay hoặc đối chiếu. Vì vậy, không nên chọn restore toàn database chỉ vì một nhóm bản ghi bị lỗi nếu có thể phục hồi có chọn lọc.

## 5. Phân biệt schema rollback với data restore

Schema migration thay đổi cấu trúc hoặc quy tắc lưu trữ. Data migration thay đổi nội dung hoặc cách biểu diễn dữ liệu. Một migration có thể làm cả hai.

Ví dụ:

- Schema migration: thêm cột phone_number.
- Data migration: chuyển dữ liệu từ phone sang phone_number.
- Destructive schema migration: xóa cột phone cũ.
- Data transformation: chuẩn hóa định dạng số điện thoại và ghi đè giá trị cũ.

Các loại thao tác có khả năng đảo ngược khác nhau:

| Thao tác | Khả năng đảo ngược | Rủi ro |
|---|---|---|
| Thêm cột nullable | Thường dễ giữ lại hoặc bỏ nếu chưa có dữ liệu phụ thuộc | Thấp hơn nếu chưa được sử dụng |
| Thêm index | Có thể xóa index nếu không có phụ thuộc | Có thể ảnh hưởng hiệu năng trong lúc tạo/xóa |
| Thêm constraint | Có thể gỡ, nhưng dữ liệu đã được kiểm tra theo constraint | Có thể làm lộ dữ liệu không hợp lệ khi gỡ |
| Đổi tên cột | Có thể đổi lại nếu không có client phụ thuộc | Ứng dụng cũ/mới có thể không tương thích |
| Xóa cột | Không thể khôi phục nội dung chỉ bằng cách tạo lại cột | Mất dữ liệu |
| Gộp hoặc chuẩn hóa giá trị | Có thể mất thông tin ban đầu | Cần backup hoặc mapping để phục hồi |
| Xóa bản ghi | Có thể phục hồi từ log/backup nếu còn | Có thể mất giao dịch sau thời điểm backup |

Một script down migration không tự động chứng minh migration có thể đảo ngược. Nếu migration đã xóa dữ liệu hoặc gộp nhiều giá trị thành một, việc tạo lại cấu trúc cũ không khôi phục được thông tin đã mất.

Cần phân biệt:

- **Schema rollback:** thay đổi cấu trúc database về dạng trước.
- **Data rollback:** đảo ngược nội dung đã ghi.
- **Restore:** khôi phục từ một bản lưu hoặc log.
- **Forward migration:** tiến lên schema mới tương thích để sửa lỗi mà không quay về schema cũ.

Không phải release nào cũng cần down migration. Với thay đổi dữ liệu có tính mất mát, forward fix hoặc restore có chọn lọc thường an toàn hơn.

## 6. Tương thích ngược giúp rollback ứng dụng an toàn hơn

Một cách giảm rủi ro là thiết kế migration để phiên bản cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp.

Mô hình phổ biến là expand-and-contract:

1. **Expand:** thêm cấu trúc mới mà không xóa hoặc phá cấu trúc cũ.
2. **Deploy compatible code:** triển khai code có thể làm việc với cả cấu trúc cũ và mới.
3. **Backfill:** chuyển dữ liệu cũ sang cấu trúc mới theo batch có kiểm soát.
4. **Switch reads/writes:** chuyển ứng dụng sang đọc/ghi cấu trúc mới sau khi dữ liệu đã sẵn sàng.
5. **Observe:** xác minh không còn phụ thuộc vào cấu trúc cũ.
6. **Contract:** chỉ xóa cấu trúc cũ trong một release sau, khi rollback về code cũ không còn là yêu cầu.

Ví dụ đổi tên cột:

Không nên thực hiện một migration duy nhất xóa cột old_name và tạo cột new_name rồi triển khai code mới ngay lập tức.

Có thể chia thành:

- Release A: thêm new_name, giữ old_name.
- Release B: code ghi đồng thời hoặc đồng bộ có kiểm soát hai cột; đọc từ cột cũ hoặc có fallback.
- Backfill dữ liệu cũ sang new_name.
- Release C: chuyển đọc sang new_name và xác minh dữ liệu.
- Release D: sau thời gian quan sát và khi không còn phiên bản cũ, xóa old_name.

Ghi kép (dual-write) cũng có rủi ro: hai lần ghi có thể không cùng thành công. Nếu dùng, cần transaction phù hợp, outbox hoặc cơ chế reconcile để phát hiện lệch dữ liệu. Không nên chỉ thêm hai câu UPDATE trong code rồi coi dữ liệu luôn nhất quán.

Expand-and-contract tạo ra khoảng thời gian mà code cũ và mới có thể cùng tương tác với schema. Đây là điều kiện quan trọng cho rolling update, canary và application rollback.

## 7. Điều gì xảy ra với dữ liệu được ghi sau khi deploy?

Đây là câu hỏi quyết định khi lựa chọn rollback hay restore.

Giả sử V2 được triển khai lúc 10:00. Từ 10:00 đến 10:30, người dùng tạo 500 đơn hàng. Lúc 10:20, V2 có một lỗi khiến 20 đơn hàng bị ghi sai trạng thái.

Nếu restore database về 09:59, cả 500 đơn hàng hợp lệ cũng có thể biến mất. Nếu chỉ rollback application về V1, 20 đơn hàng sai vẫn còn.

Hai hành động giải quyết hai vấn đề khác nhau:

- Rollback application khôi phục logic xử lý request cho các request tiếp theo.
- Data recovery sửa hoặc khôi phục những bản ghi đã bị ảnh hưởng.

Có thể cần kết hợp:

1. Dừng hoặc hạn chế luồng ghi gây lỗi.
2. Quay ứng dụng về phiên bản tương thích hoặc triển khai forward fix.
3. Xác định tập bản ghi bị ảnh hưởng theo thời gian, release ID hoặc correlation ID.
4. Phục hồi bản ghi từ backup/log hoặc tái dựng từ nguồn chuẩn.
5. Replay các giao dịch hợp lệ bị bỏ sót nếu có thể.
6. Kiểm tra quan hệ và invariant nghiệp vụ.
7. Mở lại traffic ghi sau khi xác minh.

Không nên restore toàn bộ database chỉ để sửa một tập nhỏ bản ghi nếu dữ liệu hợp lệ khác đã phát sinh sau đó.

## 8. Các lựa chọn phục hồi dữ liệu

### 8.1. Restore từ full backup

Full backup lưu một bản sao dữ liệu tại thời điểm tạo. Khi restore, hệ thống có thể quay lại trạng thái của backup đó.

Phù hợp khi:

- Toàn bộ database hoặc volume bị hỏng.
- Cần dựng lại môi trường từ một điểm đã biết.
- Các phương án phục hồi chi tiết khác không khả thi.

Hạn chế:

- Thay đổi sau thời điểm backup có thể mất.
- Restore database lớn có thể mất nhiều thời gian.
- Có thể cần replay transaction log để giảm lượng dữ liệu mất.
- Phải xác minh tính nhất quán giữa database và các hệ thống liên quan.

### 8.2. Point-in-time recovery

PITR dùng backup nền cùng transaction log hoặc log tương đương để khôi phục đến một thời điểm được chọn.

Ví dụ:

- Backup nền được tạo lúc 00:00.
- Transaction log được lưu liên tục.
- Lỗi xóa dữ liệu xảy ra lúc 14:32.
- Có thể dựng database đến thời điểm ngay trước thao tác lỗi nếu log và nền tảng hỗ trợ.

PITR hữu ích khi cần chọn mốc phục hồi chính xác hơn backup định kỳ. Tuy nhiên, phục hồi đến thời điểm trước lỗi có thể bỏ mất giao dịch hợp lệ xảy ra sau mốc đó.

Một quy trình thường dùng là restore vào một instance hoặc database tạm, trích xuất dữ liệu cần thiết, đối chiếu rồi mới đưa phần dữ liệu đã kiểm chứng về hệ thống chính. Không phải lúc nào cũng cần thay thế toàn bộ database production bằng bản PITR.

### 8.3. Phục hồi có chọn lọc

Selective recovery chỉ khôi phục bản ghi hoặc phạm vi bị ảnh hưởng.

Ví dụ:

- Lấy lại một nhóm customer bị ghi nhầm trạng thái.
- Phục hồi một partition hoặc một bảng.
- So sánh bản ghi production với bản restore tạm.
- Tạo script sửa dữ liệu theo danh sách ID đã xác định.

Cách này hạn chế mất dữ liệu hợp lệ nhưng cần hiểu quan hệ dữ liệu và invariant. Phục hồi một bảng có thể làm sai foreign key, số dư tổng hợp hoặc trạng thái liên quan ở dịch vụ khác.

### 8.4. Replay từ event log hoặc nguồn chuẩn

Nếu hệ thống có event log, audit log hoặc nguồn dữ liệu chuẩn, có thể tái dựng trạng thái bằng cách replay sự kiện hợp lệ.

Cần kiểm tra:

- Event có đầy đủ và đúng thứ tự không?
- Có event trùng lặp không?
- Consumer có idempotent không?
- Event schema có tương thích với code replay không?
- Side effect bên ngoài có được chặn hoặc xử lý riêng không?
- Có thể xác định offset hoặc checkpoint an toàn không?

Replay không phải chỉ chạy lại mọi message. Nếu consumer gửi thanh toán hoặc email, replay mù quáng có thể lặp side effect. Cần idempotency key, deduplication hoặc chế độ replay không phát sinh tác động ngoài ý muốn.

### 8.5. Forward fix hoặc compensating transaction

Đôi khi dữ liệu không thể khôi phục nguyên trạng một cách an toàn. Có thể cần sửa trạng thái hiện tại bằng một thay đổi tiến về phía trước.

- **Forward fix:** sửa code hoặc migration để xử lý đúng dữ liệu đang tồn tại.
- **Compensating transaction:** tạo một giao dịch mới bù trừ cho tác động của giao dịch trước, ví dụ hoàn tiền thay vì xóa lịch sử thanh toán.

Compensation không xóa lịch sử sự kiện. Nó tạo một hành động mới để đưa trạng thái nghiệp vụ về kết quả mong muốn, đồng thời giữ audit.

## 9. RPO và RTO ảnh hưởng đến quyết định phục hồi

Hai mục tiêu quan trọng:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường biểu diễn bằng khoảng thời gian.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ hoặc năng lực xử lý sau sự cố.

Ví dụ, một dịch vụ có RPO 5 phút cần cơ chế backup/log đủ để giới hạn dữ liệu mất trong khoảng đó. RTO 30 phút yêu cầu quy trình restore, kiểm tra và chuyển traffic có thể hoàn tất trong thời gian tương ứng.

RPO/RTO không tự động được đáp ứng chỉ vì có backup. Cần đo:

- Tần suất và độ trễ backup.
- Mức độ đầy đủ của transaction log.
- Thời gian restore theo kích thước dữ liệu thực.
- Thời gian kiểm tra consistency.
- Thời gian DNS/routing hoặc failover.
- Thời gian replay dữ liệu và xử lý backlog.
- Thời gian xác minh nghiệp vụ trước khi mở lại traffic.

Một chiến lược backup có thể đáp ứng RPO nhưng không đáp ứng RTO nếu restore mất quá lâu. Ngược lại, snapshot có thể restore nhanh nhưng khoảng cách giữa các snapshot làm mất quá nhiều giao dịch.

## 10. Bảo đảm tính nhất quán giữa các hệ thống

Một ứng dụng có thể ghi dữ liệu vào nhiều nơi:

- Database chính.
- Read replica.
- Message broker.
- Search index.
- Cache.
- Object storage.
- Dịch vụ thanh toán hoặc CRM bên ngoài.

Nếu chỉ restore database chính, các hệ thống khác có thể vẫn giữ trạng thái mới hoặc trạng thái không đồng bộ.

Ví dụ:

1. Database ghi order thành PAID.
2. Event OrderPaid được gửi lên broker.
3. Consumer cập nhật kho và gửi thông báo.
4. Sau đó database được restore về trước khi order chuyển sang PAID.
5. Broker và hệ thống kho vẫn giữ event đã xử lý.

Lúc này các hệ thống không còn cùng một trạng thái. Phục hồi cần có kế hoạch reconcile hoặc replay phù hợp.

Các cơ chế hỗ trợ:

- Transactional outbox để liên kết ghi database với phát event.
- Idempotent consumer để xử lý message trùng an toàn.
- Correlation ID và event ID để truy vết.
- Reconciliation job để so sánh trạng thái giữa các hệ thống.
- Saga hoặc compensating action cho quy trình nhiều dịch vụ.
- Checkpoint và offset được ghi nhận khi replay.

Không có một transaction database đơn lẻ nào thường bao trùm tất cả hệ thống bên ngoài. Cần thiết kế quy trình phục hồi theo từng bounded context và quan hệ nghiệp vụ.

## 11. Quy trình quyết định: rollback code, forward fix hay data recovery?

Khi phát hiện release gây sự cố, không nên chọn ngay restore database hoặc rollback application. Hãy đánh giá theo trình tự:

1. **Containment:** ngăn lỗi tiếp tục lan rộng; dừng rollout, tắt feature flag hoặc hạn chế thao tác ghi nếu cần.
2. **Classify:** xác định lỗi nằm ở code, schema, data, config, dependency hay hệ thống bên ngoài.
3. **Assess compatibility:** phiên bản ứng dụng trước có tương thích với schema và dữ liệu hiện tại không?
4. **Measure impact:** xác định thời gian, phạm vi bản ghi, người dùng và side effect bị ảnh hưởng.
5. **Choose recovery path:** application rollback, forward fix, migration correction, selective restore, PITR hoặc compensation.
6. **Preserve evidence:** giữ log, audit, snapshot và bản sao dữ liệu phục vụ điều tra.
7. **Execute with controls:** dùng runbook, quyền phù hợp, backup trước thao tác phá hủy và xác nhận phạm vi.
8. **Verify:** kiểm tra schema, dữ liệu, quan hệ và invariant nghiệp vụ.
9. **Resume traffic:** chỉ mở lại luồng ghi khi điều kiện an toàn đã đạt.
10. **Record:** ghi lại quyết định, actor, mốc thời gian, dữ liệu đã phục hồi và phần còn sai lệch.

~~~mermaid
flowchart TD
    A["Release gây sự cố"] --> B["Contain: dừng rollout / giới hạn ghi"]
    B --> C["Phân loại code, schema, data, config, external state"]
    C --> D{"Dữ liệu có bị sai hoặc mất?"}
    D -- "Không" --> E{"Code cũ tương thích trạng thái hiện tại?"}
    E -- "Có" --> F["Rollback application"]
    E -- "Không" --> G["Forward fix / migration tương thích"]
    D -- "Có" --> H["Xác định phạm vi và timeline dữ liệu"]
    H --> I{"Có thể sửa chọn lọc hoặc replay?"}
    I -- "Có" --> J["Selective recovery / compensation"]
    I -- "Không" --> K["Restore tạm từ backup / PITR"]
    K --> L["Trích xuất, đối chiếu và reconcile"]
    J --> M["Verify schema, data và nghiệp vụ"]
    L --> M
    F --> N["Post-recovery verification"]
    G --> N
    M --> N
    N --> O["Mở lại traffic và ghi audit"]
~~~

Sơ đồ là khung quyết định. Trong sự cố thực tế, có thể cần thực hiện nhiều nhánh phối hợp, ví dụ rollback application trước để dừng ghi sai, sau đó selective recovery cho các bản ghi đã bị ảnh hưởng.

## 12. Migration an toàn trong pipeline CI/CD

Migration cần được quản lý như một thay đổi phát hành có tác động đến trạng thái dữ liệu.

Trước khi chạy migration, pipeline nên kiểm tra:

- Migration version đã tồn tại hay đã chạy chưa.
- Migration có idempotent hoặc có cách phát hiện chạy một phần không.
- Có backup hoặc recovery point phù hợp không.
- Migration có khóa bảng lâu hoặc ảnh hưởng hiệu năng không.
- Ứng dụng đang chạy có tương thích với schema mới không.
- Có nhiều phiên bản ứng dụng cùng truy cập database không.
- Migration có thao tác phá hủy hoặc chuyển đổi mất thông tin không.
- Có kế hoạch phục hồi và người chịu trách nhiệm không.

Với migration rủi ro cao, nên tách khỏi bước deploy ứng dụng để có thể review, kiểm tra và quan sát riêng.

Một thứ tự tham khảo:

1. Tạo backup hoặc xác nhận recovery point.
2. Kiểm tra migration trên bản sao dữ liệu đại diện.
3. Apply migration tương thích theo giai đoạn.
4. Xác minh schema và dữ liệu.
5. Triển khai application artifact.
6. Theo dõi hành vi và metric.
7. Chỉ chạy contract migration khi không còn phiên bản cũ cần cấu trúc cũ.

Không nên để pipeline tự động chạy một migration phá hủy ngay khi merge mà không có gate phù hợp. Tự động hóa cần có điều kiện rõ ràng, giới hạn thời gian và cách dừng an toàn.

## 13. Ví dụ: xử lý release thêm trường dữ liệu mới

Giả sử V2 thêm trường normalized_email để lưu email đã chuẩn hóa. V2 bắt đầu đọc trường mới và ghi đồng thời email cũ cùng email chuẩn hóa.

Một rollout thiếu an toàn có thể:

1. Thêm trường mới.
2. Xóa trường email cũ.
3. Deploy V2.
4. Phát hiện V2 lỗi.
5. Rollback V1.
6. V1 không tìm thấy trường email cũ.

Một quy trình an toàn hơn:

**Giai đoạn 1 — Expand**

- Thêm normalized_email, giữ email cũ.
- Kiểm tra schema và index.
- Chưa xóa dữ liệu cũ.

**Giai đoạn 2 — Compatible release**

- Triển khai V2 có thể đọc fallback từ email cũ.
- Ghi normalized_email theo quy tắc đã kiểm tra.
- Giữ khả năng V1 tiếp tục hoạt động.

**Giai đoạn 3 — Backfill và verify**

- Chuyển dữ liệu cũ theo batch.
- Ghi checkpoint để có thể tiếp tục sau lỗi.
- Đếm số bản ghi chưa chuyển.
- So sánh giá trị và kiểm tra duplicate hoặc constraint.

**Giai đoạn 4 — Switch**

- Chuyển đọc sang normalized_email.
- Theo dõi lỗi và kết quả nghiệp vụ.
- Giữ email cũ trong thời gian rollback được hỗ trợ.

**Giai đoạn 5 — Contract**

- Chỉ xóa email cũ sau khi xác nhận không còn phiên bản hoặc consumer nào phụ thuộc.
- Thực hiện trong một release riêng.
- Cập nhật recovery plan vì rollback về code cũ có thể không còn được hỗ trợ sau bước này.

Nếu V2 gặp lỗi trước giai đoạn contract, có thể rollback code về V1 trong khi vẫn giữ schema mở rộng. Nếu dữ liệu normalized_email bị ghi sai, cần sửa hoặc backfill lại dữ liệu; rollback code không tự sửa các giá trị đó.

## 14. Phục hồi có chọn lọc: các bước cần kiểm soát

Selective recovery có thể giảm mất dữ liệu, nhưng cần xác định chính xác bản ghi nào bị ảnh hưởng.

Một quy trình có thể gồm:

1. Dừng job hoặc code gây lỗi để không tạo thêm bản ghi sai.
2. Xác định release ID, thời gian và điều kiện lọc bản ghi.
3. Tạo snapshot hoặc restore bản sao vào môi trường cô lập.
4. So sánh dữ liệu hiện tại với bản phục hồi.
5. Tạo danh sách bản ghi cần sửa và bản ghi cần giữ.
6. Xác minh quan hệ foreign key, số dư, aggregate và invariant.
7. Review script sửa dữ liệu và chạy dry-run.
8. Áp dụng theo batch có checkpoint.
9. Đối chiếu số lượng trước/sau và ghi audit.
10. Chạy reconciliation với queue, search index và dịch vụ liên quan.

Không nên chạy câu lệnh UPDATE hoặc DELETE diện rộng ngay trong production chỉ dựa vào một truy vấn đếm sơ bộ. Với dữ liệu quan trọng, cần có bản sao, phạm vi rõ, kiểm tra kết quả và khả năng tiếp tục hoặc dừng theo batch.

Nếu dữ liệu bị lỗi có thể được xác định bằng event ID hoặc correlation ID, hãy dùng định danh đó thay vì chỉ dựa vào timestamp. Đồng hồ giữa nhiều hệ thống có thể lệch, và một khoảng thời gian rộng có thể bao gồm cả giao dịch hợp lệ.

## 15. Backup chỉ có giá trị khi đã kiểm tra khả năng restore

Có backup không đồng nghĩa có khả năng phục hồi.

Cần kiểm tra:

- Backup có hoàn tất và không bị lỗi không?
- Có thể đọc và giải mã backup không?
- Encryption key có còn truy cập được không?
- Backup có nằm trong failure domain khác không?
- Retention có đủ dài để phát hiện lỗi muộn không?
- Transaction log có liên tục và không bị thiếu đoạn không?
- Restore có đạt RTO không?
- Dữ liệu sau restore có đạt consistency check không?
- Ứng dụng có tương thích với schema được phục hồi không?

Nên diễn tập restore định kỳ trên môi trường cô lập. Đo thời gian thực tế từ lúc bắt đầu đến khi dữ liệu được xác minh, không chỉ đo thời gian tải file backup.

Backup cũng cần được bảo vệ khỏi việc bị xóa hoặc mã hóa bởi cùng một tài khoản có quyền quản trị production. Có thể dùng immutable backup, retention lock hoặc quyền tách biệt tùy nền tảng.

## 16. Quyền và audit trong quá trình phục hồi

Data recovery có thể gây tác động lớn hơn một lần deploy bình thường. Quyền cần được giới hạn theo loại thao tác.

Ví dụ:

| Vai trò | Quyền gợi ý |
|---|---|
| Developer | Đọc log và yêu cầu phục hồi; không tự restore production |
| Database operator | Thực hiện thao tác database theo runbook và change control |
| Incident commander | Điều phối quyết định và phạm vi phục hồi |
| Security/compliance | Giám sát audit và yêu cầu bảo toàn bằng chứng |
| CI workload | Chỉ chạy migration hoặc recovery task đã được cho phép, với identity riêng |

Một recovery record nên có:

- Incident hoặc change ID.
- Actor và workload identity.
- Thời điểm bắt đầu/kết thúc.
- Database, table, partition hoặc resource bị tác động.
- Backup ID, log position hoặc PITR timestamp.
- Artifact và schema version liên quan.
- Phạm vi bản ghi được phục hồi.
- Số lượng bản ghi trước/sau.
- Kết quả consistency check.
- Các thao tác bù trừ hoặc replay.
- Trạng thái cuối và rủi ro còn lại.

Không ghi dữ liệu cá nhân hoặc secret không cần thiết vào log phục hồi. Audit cần đủ thông tin để truy vết mà không tạo thêm nơi lưu trữ nhạy cảm.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Cho rằng rollback image sẽ rollback database | Dữ liệu mới vẫn tồn tại và có thể không tương thích | Đánh giá riêng code, schema và data |
| Chạy down migration ngay khi deploy lỗi | Có thể xóa dữ liệu hoặc làm hỏng trạng thái hiện tại | Kiểm tra khả năng đảo ngược và tác động trước |
| Restore toàn database cho một nhóm bản ghi sai | Mất giao dịch hợp lệ sau backup | Dùng selective recovery khi khả thi |
| Không giữ backup trước migration phá hủy | Không có điểm phục hồi đáng tin | Tạo và xác minh recovery point |
| Build lại artifact khi rollback | Có thể không khôi phục đúng binary đã chạy trước | Dùng artifact cũ theo digest |
| Không kiểm tra compatibility của code cũ | Phiên bản cũ có thể không đọc schema mới | Dùng expand-and-contract và compatibility test |
| Replay message không idempotent | Lặp thanh toán, email hoặc side effect | Deduplication, idempotency và replay mode |
| Chỉ restore database, bỏ qua queue/cache/storage | Trạng thái giữa hệ thống không nhất quán | Lập kế hoạch reconcile toàn bộ state |
| Không diễn tập restore | RTO thực tế có thể vượt mục tiêu | Restore drill và đo thời gian |
| Không ghi phạm vi phục hồi | Không thể chứng minh dữ liệu nào đã thay đổi | Recovery audit và reconciliation report |

## 18. Checklist phân biệt rollback và data recovery

Khi một release gặp sự cố, hãy kiểm tra:

- [ ] Đã xác định lỗi nằm ở code, schema, business data, config hay external state.
- [ ] Đã dừng hoặc giới hạn thao tác tiếp tục gây lỗi.
- [ ] Đã ghi timeline của release, migration và các lần ghi dữ liệu.
- [ ] Đã xác minh phiên bản ứng dụng cũ có tương thích schema hiện tại.
- [ ] Đã xác định dữ liệu hợp lệ phát sinh sau thời điểm backup.
- [ ] Đã chọn đúng phạm vi: bản ghi, bảng, database hoặc toàn hệ thống.
- [ ] Đã xác định backup, transaction log hoặc nguồn replay phù hợp.
- [ ] Đã đánh giá RPO và RTO thực tế.
- [ ] Đã xem xét side effect ở queue, cache, storage và hệ thống ngoài.
- [ ] Đã có snapshot hoặc recovery point trước thao tác phá hủy.
- [ ] Script phục hồi có dry-run, giới hạn phạm vi và checkpoint.
- [ ] Có quyền và approval phù hợp cho thao tác production.
- [ ] Đã kiểm tra consistency và invariant nghiệp vụ sau phục hồi.
- [ ] Đã reconcile hoặc replay dữ liệu liên hệ thống.
- [ ] Đã xác minh artifact/config/schema thực tế trước khi mở lại traffic.
- [ ] Đã lưu audit, bằng chứng và rủi ro còn lại.

## 19. Bài tập tự đánh giá

Một release V3 của dịch vụ đơn hàng được triển khai lúc 09:00. Migration chuyển trường order_status sang mô hình trạng thái mới. Từ 09:00 đến 09:30, hệ thống nhận 1.200 đơn hàng. Lúc 09:20 phát hiện V3 gán sai trạng thái cho 40 đơn. Đội ngũ có backup lúc 08:00 và transaction log đến thời điểm hiện tại. Phiên bản V2 vẫn còn trong registry, nhưng V2 chỉ hiểu schema cũ. Một số event OrderPaid đã được gửi đến message broker và consumer kho đã xử lý.

Hãy đề xuất kế hoạch:

1. Việc đầu tiên để ngăn lỗi tiếp tục phát sinh là gì?
2. Có thể rollback thẳng V2 không? Điều kiện nào cần kiểm tra?
3. Vì sao restore toàn database về 08:00 có thể làm mất dữ liệu hợp lệ?
4. Có thể dùng PITR để tạo bản database tạm và trích xuất 40 đơn sai không?
5. Cần đối chiếu những gì trước khi sửa các bản ghi production?
6. Event OrderPaid đã được xử lý cần reconcile hoặc bù trừ ra sao?
7. Có nên replay toàn bộ message từ backup không? Vì sao?
8. Cần kiểm tra schema và invariant nào trước khi mở lại traffic?
9. Audit record cần lưu những bằng chứng gì?

Một phương án tốt thường dừng luồng gây lỗi, đánh giá tương thích ứng dụng và schema, phục hồi có chọn lọc từ bản PITR tạm, đối chiếu side effect ở broker và consumer, rồi xác minh toàn bộ trạng thái nghiệp vụ. Quyết định cuối cùng cần dựa trên dữ liệu thực tế và khả năng phục hồi đã kiểm chứng.

## Kết luận

Rollback mã ứng dụng và phục hồi dữ liệu giải quyết hai lớp trạng thái khác nhau. Rollback đưa chương trình về phiên bản cũ; data recovery khôi phục hoặc sửa những thay đổi đã ghi trong database, queue, storage và hệ thống liên quan. Schema migration rollback là một hoạt động riêng và có thể không đảo ngược được nếu dữ liệu đã bị xóa hoặc biến đổi mất thông tin.

Trong CI/CD, hãy thiết kế migration tương thích theo giai đoạn, giữ artifact cũ theo digest, có backup và transaction log phù hợp, xác định RPO/RTO, đồng thời diễn tập restore. Khi xảy ra sự cố, cần dừng tác động, dựng timeline, chọn phạm vi phục hồi nhỏ nhất có thể, đối chiếu dữ liệu và side effect, rồi xác minh trước khi mở lại traffic. Cách tiếp cận này giúp khôi phục dịch vụ mà vẫn bảo toàn tối đa những giao dịch hợp lệ đã phát sinh.

