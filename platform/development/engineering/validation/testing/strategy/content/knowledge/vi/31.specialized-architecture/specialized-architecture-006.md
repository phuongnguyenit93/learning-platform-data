# Kiểm thử chuyển đổi schema, dữ liệu và phiên bản ứng dụng

Một thay đổi kiến trúc thường không chỉ thay đổi mã nguồn. Khi hệ thống cần thêm cột, đổi kiểu dữ liệu, tách bảng, chuyển database, chuẩn hóa dữ liệu hoặc thay đổi cách ứng dụng đọc và ghi, nhiều phiên bản ứng dụng và cấu trúc dữ liệu có thể cùng tồn tại trong một khoảng thời gian. Nếu migration chạy sai, dữ liệu có thể bị mất, quan hệ bị phá vỡ, ứng dụng cũ không còn hoạt động hoặc quá trình triển khai không thể rollback an toàn.

Kiểm thử chuyển đổi schema, dữ liệu và phiên bản ứng dụng nhằm chứng minh rằng cấu trúc mới, dữ liệu sau chuyển đổi và các phiên bản ứng dụng liên quan tương thích trong từng giai đoạn phát hành. Việc kiểm thử cần xác minh tính đúng đắn của dữ liệu, khả năng đọc/ghi, hiệu năng migration, tính an toàn khi chạy lại hoặc gián đoạn, và phương án phục hồi. Một migration hoàn tất mà ứng dụng không thể sử dụng dữ liệu mới vẫn là thất bại; một ứng dụng mới chạy được trên schema mới nhưng phiên bản cũ bị hỏng trong giai đoạn rolling deployment cũng là rủi ro cần ngăn chặn.

## 1. Phân biệt schema migration, data migration và application version transition

Ba loại chuyển đổi thường đi cùng nhau nhưng cần được kiểm tra riêng:

- **Schema migration:** thay đổi cấu trúc lưu trữ như bảng, cột, kiểu dữ liệu, index, constraint, view, trigger, partition hoặc quan hệ.
- **Data migration:** biến đổi dữ liệu hiện có sang biểu diễn hoặc quy tắc mới, ví dụ chuẩn hóa mã quốc gia, tách trường địa chỉ, chuyển đơn vị tiền tệ hoặc gộp bản ghi.
- **Application version transition:** triển khai các phiên bản ứng dụng có cách đọc, ghi hoặc diễn giải dữ liệu khác nhau. Trong giai đoạn chuyển tiếp, nhiều phiên bản có thể cùng truy cập một database, queue hoặc event store.

Ví dụ, thay trường customer.full_name bằng first_name và last_name gồm thay đổi schema, chuyển dữ liệu cũ sang hai trường mới và cập nhật ứng dụng để đọc/ghi cấu trúc mới. Nếu ứng dụng cũ vẫn chạy trong lúc triển khai, nó có thể chỉ biết trường full_name; ứng dụng mới có thể chỉ biết hai trường mới. Vì vậy, chỉ kiểm tra migration trên database trống là chưa đủ.

Cần lập bản đồ phụ thuộc giữa schema, dữ liệu và phiên bản ứng dụng. Với mỗi thay đổi, xác định thành phần nào đọc, ghi, validate hoặc phát sự kiện dựa trên cấu trúc đó.

## 2. Xác định phạm vi và rủi ro chuyển đổi

Trước khi thiết kế test, làm rõ:

- Database, schema, bảng, collection, topic hoặc kho dữ liệu nào bị thay đổi?
- Dữ liệu hiện có có bao nhiêu bản ghi, kích thước và phân bố ra sao?
- Ứng dụng, worker, batch job, báo cáo và consumer nào sử dụng cấu trúc liên quan?
- Phiên bản cũ và mới sẽ cùng tồn tại trong bao lâu?
- Có yêu cầu downtime, read-only window hoặc triển khai không gián đoạn không?
- Migration có chạy một lần, theo batch, online hay qua pipeline riêng?
- Có dữ liệu nhạy cảm, yêu cầu lưu giữ, xóa hoặc kiểm toán không?
- Có thể rollback schema và dữ liệu không, hay phải roll-forward?
- Nếu migration dừng giữa chừng, có thể tiếp tục an toàn không?
- Những chỉ số nào xác nhận dữ liệu và ứng dụng đã chuyển đổi đúng?

Phân loại rủi ro theo hậu quả. Mất dữ liệu, sai số dư, phá vỡ phân quyền hoặc không thể khôi phục thường có mức rủi ro cao hơn thay đổi index không ảnh hưởng nghiệp vụ. Ưu tiên kiểm thử sâu cho dữ liệu tài chính, trạng thái đơn hàng, quyền tenant, dữ liệu định danh và các bảng có quan hệ rộng.

## 3. Xây dựng baseline và dữ liệu kiểm thử đại diện

Migration phải được kiểm tra trên dữ liệu gần với thực tế. Dataset quá nhỏ hoặc quá sạch có thể bỏ qua vấn đề về dữ liệu cũ, giá trị null, ký tự đặc biệt, bản ghi trùng, quan hệ thiếu và khối lượng lớn.

Một bộ dữ liệu kiểm thử nên bao gồm:

- Bản ghi hợp lệ theo schema hiện tại.
- Giá trị null, rỗng, mặc định và giá trị biên.
- Bản ghi trùng hoặc gần trùng theo quy tắc nghiệp vụ.
- Quan hệ cha-con, khóa ngoại và bản ghi tham chiếu.
- Dữ liệu lịch sử từ nhiều phiên bản ứng dụng.
- Giá trị cũ đã bị deprecated nhưng vẫn còn tồn tại.
- Ký tự Unicode, timezone, locale và định dạng khác nhau.
- Dữ liệu lớn hoặc phân bố lệch để đánh giá hiệu năng.
- Bản ghi bị xóa mềm, lưu trữ hoặc đánh dấu không hoạt động.
- Dữ liệu có trạng thái chuyển tiếp hoặc không nhất quán cần xử lý.

Không sao chép dữ liệu nhạy cảm từ production vào môi trường kiểm thử nếu chưa có cơ chế bảo vệ được phê duyệt. Ưu tiên dữ liệu tổng hợp hoặc dữ liệu đã được xử lý phù hợp. Ghi lại nguồn, phiên bản và cách tạo dataset để có thể tái hiện kết quả.

Trước migration, lưu baseline cần thiết: số lượng bản ghi, số lượng theo trạng thái, tổng hợp nghiệp vụ, checksum hoặc hash theo nhóm và các quan hệ quan trọng. Không phải lúc nào checksum toàn bộ cũng phù hợp; cần chọn phép đối chiếu có ý nghĩa và tránh làm lộ dữ liệu.

## 4. Kiểm thử tính đúng đắn của schema sau migration

Sau khi migration chạy, xác minh cấu trúc thực tế so với schema mong muốn.

Các điểm cần kiểm tra:

- Bảng, cột, collection và kiểu dữ liệu đã được tạo, đổi hoặc xóa đúng chưa?
- Nullability, default, unique constraint và foreign key có đúng không?
- Index, partition, view, trigger và stored procedure có tồn tại và đúng định nghĩa không?
- Độ dài, precision, scale và collation có phù hợp dữ liệu không?
- Quyền truy cập và ownership của object có còn đúng không?
- Migration có để lại object tạm hoặc cấu trúc không còn dùng không?
- ORM mapping, generated client và schema registry có đồng bộ không?
- Các consumer có thể deserialize cấu trúc mới không?

Nên kiểm tra bằng metadata của database hoặc schema diff, không chỉ dựa vào việc migration command trả exit code thành công. Với hệ thống dùng nhiều database engine hoặc version, xác minh trên đúng engine và cấu hình mục tiêu vì hành vi DDL có thể khác nhau.

Một thay đổi schema có thể hợp lệ về cú pháp nhưng không đáp ứng quy tắc nghiệp vụ. Ví dụ, cột amount đổi từ integer sang decimal cần kiểm tra precision, scale và cách làm tròn; kiểm tra kiểu dữ liệu đơn thuần chưa chứng minh số tiền được bảo toàn.

## 5. Kiểm thử tính toàn vẹn và đúng đắn của dữ liệu

Sau data migration, cần chứng minh dữ liệu mới tương đương về ý nghĩa với dữ liệu cũ theo quy tắc chuyển đổi.

Các phép xác minh thường dùng:

- So sánh số lượng bản ghi trước và sau theo phạm vi.
- Đối chiếu tổng hợp theo nhóm, trạng thái hoặc khoảng thời gian.
- Kiểm tra khóa chính không bị mất hoặc tạo trùng ngoài dự kiến.
- Kiểm tra quan hệ và khóa ngoại.
- Xác minh không có giá trị ngoài miền cho phép.
- Kiểm tra bản ghi đã chuyển đổi đúng quy tắc.
- Đối chiếu các tổng nghiệp vụ như số lượng đơn, số dư hoặc tổng tiền.
- Xác minh dữ liệu bị loại bỏ hoặc gộp có lý do và dấu vết.
- Kiểm tra timestamp, timezone, đơn vị đo và định dạng.
- Kiểm tra dữ liệu mới có thể được ứng dụng đọc và cập nhật.

Với phép chuyển đổi có mất thông tin theo chủ đích, cần định nghĩa rõ dữ liệu nào được gộp, làm tròn, loại bỏ hoặc ẩn danh và ai phê duyệt. Không coi mọi chênh lệch số lượng là lỗi nếu quy tắc migration cho phép loại bản ghi không hợp lệ; tuy nhiên, mọi chênh lệch phải giải thích được và có báo cáo.

Ví dụ, khi tách địa chỉ thành nhiều trường, kiểm tra các trường hợp thiếu số nhà, địa chỉ nhiều dòng, ký tự Unicode và dữ liệu không theo định dạng chuẩn. Một phép tách chạy thành công về kỹ thuật nhưng chuyển nhầm nội dung giữa tỉnh và quận vẫn là lỗi dữ liệu.

## 6. Kiểm thử tương thích giữa phiên bản ứng dụng và schema

Trong rolling deployment hoặc khi nhiều service được triển khai độc lập, ứng dụng cũ và mới có thể cùng truy cập schema trong một khoảng thời gian. Cần xác định ma trận tương thích.

| Phiên bản ứng dụng | Schema cũ | Schema mở rộng | Schema cuối |
|---|---|---|---|
| App N-1 | Hoạt động theo baseline | Phải tiếp tục hoạt động trong giai đoạn tương thích nếu rollout yêu cầu | Không cần hỗ trợ sau khi đã loại bỏ phiên bản cũ |
| App N | Chỉ hỗ trợ nếu thiết kế có backward compatibility | Hoạt động với cấu trúc mới | Hoạt động theo thiết kế cuối |
| Worker/consumer N-1 | Đọc/ghi theo hợp đồng cũ | Phải xử lý trường mới hoặc message mới an toàn trong giai đoạn cùng chạy | Có thể không tương thích nếu đã ngừng phiên bản cũ |
| Worker/consumer N | Chỉ hỗ trợ schema cũ nếu có thiết kế tương thích | Hoạt động với schema mở rộng | Hoạt động theo hợp đồng cuối |

Ma trận thực tế cần thay bằng các phiên bản và giai đoạn triển khai của hệ thống. Không phải mọi tổ hợp đều cần được hỗ trợ, nhưng các tổ hợp có thể xuất hiện trong rollout phải được kiểm tra hoặc loại trừ bằng cơ chế triển khai rõ ràng.

Các câu hỏi quan trọng:

- App cũ có đọc được schema sau bước mở rộng không?
- App mới có hoạt động trước khi backfill hoàn tất không?
- App cũ và mới có thể ghi cùng một bản ghi mà không ghi đè hoặc mất cập nhật không?
- Worker cũ có hiểu message được tạo bởi producer mới không?
- API và event có giữ tương thích ngược trong cửa sổ chuyển tiếp không?
- Phiên bản cũ có thể chạy lại sau khi một phần dữ liệu đã được chuyển đổi không?

Kiểm thử cả đọc và ghi. Một ứng dụng cũ có thể đọc được cột mới nhưng không ghi giá trị cần thiết; ứng dụng mới có thể ghi trường mới nhưng khiến ứng dụng cũ diễn giải sai trạng thái.

## 7. Dùng chiến lược Expand-Contract cho thay đổi không gián đoạn

Expand-contract là cách chia migration thành các bước tương thích để ứng dụng cũ và mới có thể cùng hoạt động trong giai đoạn chuyển tiếp.

Ví dụ đổi full_name thành first_name và last_name:

1. **Expand:** thêm hai cột mới, giữ full_name.
2. Triển khai ứng dụng có thể đọc dữ liệu cũ và mới; khi ghi, cập nhật cả hai dạng hoặc dùng cơ chế đồng bộ được kiểm soát.
3. **Backfill:** chuyển dữ liệu hiện tại từ full_name sang hai cột mới theo batch.
4. Xác minh dữ liệu và chuyển ứng dụng sang đọc trường mới.
5. Ngừng ghi full_name sau khi không còn phiên bản hoặc consumer phụ thuộc.
6. **Contract:** xóa trường cũ và mã tương thích trong một thay đổi riêng sau khi xác nhận an toàn.

Trong từng bước, xác định phiên bản ứng dụng nào có thể chạy, dữ liệu nào đã chuyển và điều kiện để đi tiếp. Không xóa cấu trúc cũ ngay khi ứng dụng mới vừa triển khai vì worker, batch hoặc instance cũ có thể vẫn sử dụng nó.

Nếu dùng dual-write, cần kiểm thử tình huống một lần ghi thành công và lần ghi còn lại thất bại, thứ tự ghi, retry và xử lý sai lệch. Dual-write không tự bảo đảm hai dạng dữ liệu luôn đồng nhất.

## 8. Kiểm thử backfill và migration theo batch

Backfill là quá trình chuyển đổi dữ liệu đã tồn tại. Với bảng lớn, thường cần xử lý theo batch để giảm lock, tải và thời gian gián đoạn.

Cần kiểm thử:

- Kích thước batch và thời gian xử lý.
- Thứ tự phân trang hoặc checkpoint.
- Bản ghi được thêm hoặc cập nhật trong khi backfill chạy.
- Retry khi batch thất bại.
- Chạy lại batch đã hoàn tất.
- Tiếp tục từ checkpoint sau khi tiến trình bị dừng.
- Bản ghi lỗi hoặc không đủ dữ liệu.
- Giới hạn CPU, memory, I/O và connection.
- Tác động đến truy vấn của ứng dụng đang hoạt động.
- Đối chiếu số lượng và trạng thái sau từng batch.

Migration nên có khả năng tiếp tục hoặc chạy lại an toàn theo thiết kế. Nếu chạy lại có thể nhân đôi dữ liệu, ghi đè thay đổi mới hoặc tạo side effect, cần có khóa idempotency, checkpoint hoặc trạng thái xử lý.

Với dữ liệu thay đổi đồng thời, xác định chiến lược xử lý write mới trong lúc backfill: tạm dừng ghi, dual-write, change data capture hoặc một cơ chế đồng bộ khác. Kiểm thử race condition và bảo đảm bản cập nhật mới không bị backfill cũ ghi đè.

## 9. Kiểm thử migration có tính idempotent và khả năng tiếp tục

Migration có thể bị gián đoạn do timeout, mất kết nối, hết dung lượng hoặc tiến trình bị dừng. Cần biết trạng thái sau khi lỗi và cách tiếp tục.

Các kịch bản:

- Chạy migration lần đầu trên schema nguồn.
- Chạy lại sau khi đã hoàn tất.
- Dừng giữa một batch rồi tiếp tục.
- Mất kết nối database trong lúc cập nhật.
- Tiến trình chết sau khi ghi dữ liệu nhưng trước khi ghi checkpoint.
- Một bản ghi không hợp lệ làm batch lỗi.
- Hai tiến trình vô tình khởi chạy cùng migration.
- Migration chạy trên database đã có một phần thay đổi.
- Thứ tự migration bị sai hoặc thiếu phiên bản trước đó.

Idempotent nghĩa là thực hiện lại thao tác không tạo tác dụng phụ ngoài dự kiến. Không phải mọi migration đều tự nhiên idempotent; nếu không thể chạy lại, cần cơ chế khóa, trạng thái và hướng phục hồi rõ ràng.

Sau khi gián đoạn, xác minh dữ liệu đã commit, checkpoint, transaction và trạng thái migration ledger. Không chỉ kiểm tra tiến trình có chạy lại thành công; phải đối chiếu kết quả cuối để phát hiện bản ghi thiếu hoặc bị xử lý hai lần.

## 10. Kiểm thử rollback, roll-forward và khả năng phục hồi dữ liệu

Rollback schema và rollback dữ liệu có thể khó hơn rollback ứng dụng. Một migration đã xóa hoặc gộp dữ liệu có thể không đảo ngược được nếu không lưu bản gốc hoặc quy tắc phục hồi.

Trước migration, xác định:

- Có thể rollback DDL không và trên database engine mục tiêu?
- Có thể phục hồi dữ liệu từ backup hoặc snapshot không?
- Thay đổi đã phát sinh sau migration có được bảo toàn khi phục hồi không?
- Phiên bản ứng dụng cũ có thể đọc dữ liệu đã chuyển đổi không?
- Có cần roll-forward bằng migration sửa lỗi không?
- Thời gian phục hồi và lượng dữ liệu có thể mất có đáp ứng mục tiêu không?
- Ai có quyền quyết định và thực hiện rollback/restore?

Kiểm thử trên bản sao đại diện:

1. Tạo snapshot hoặc backup theo quy trình.
2. Chạy migration.
3. Tạo một số giao dịch mới sau migration.
4. Mô phỏng lỗi cần phục hồi.
5. Thực hiện rollback hoặc restore theo runbook.
6. Đối chiếu dữ liệu trước và sau phục hồi.
7. Xác minh ứng dụng, worker và tích hợp hoạt động.
8. Ghi thời gian, dữ liệu mất (nếu có) và giới hạn.

Restore backup có thể làm mất các giao dịch được ghi sau thời điểm backup. Vì vậy, cần có kế hoạch replay, reconciliation hoặc roll-forward để bảo toàn dữ liệu mới. Không được coi “backup tồn tại” là bằng chứng rằng khôi phục đã được kiểm chứng.

## 11. Kiểm thử tương thích API, event và consumer

Schema database chỉ là một phần của hợp đồng dữ liệu. Hệ thống phân tán còn có API, message, event, file export và schema registry.

Khi thay đổi cấu trúc, kiểm tra:

- Producer cũ có tạo message consumer mới đọc được không?
- Producer mới có phát trường hoặc enum mà consumer cũ không hiểu không?
- Trường bắt buộc mới có default hoặc chiến lược chuyển tiếp không?
- Consumer có bỏ qua trường không biết theo đúng hợp đồng không?
- Event replay có thể xử lý dữ liệu lịch sử không?
- Schema version có được ghi nhận và kiểm tra không?
- File export/import có giữ định dạng tương thích không?
- Consumer có idempotent khi nhận lại message trong quá trình chuyển đổi không?

Một thay đổi enum thường nguy hiểm nếu consumer cũ dùng logic exhaustive và không có nhánh fallback. Thêm giá trị mới có thể phá vỡ consumer dù schema vẫn hợp lệ. Cần kiểm thử contract ở cả phía producer và consumer, đặc biệt trong giai đoạn nhiều phiên bản cùng tồn tại.

## 12. Kiểm thử hiệu năng và tác động vận hành của migration

Migration có thể đúng về dữ liệu nhưng gây lock kéo dài, tăng latency hoặc làm cạn tài nguyên. Cần đo tác động dưới quy mô gần thực tế.

Các chỉ số nên theo dõi:

- Thời gian hoàn tất migration và từng batch.
- Tốc độ xử lý bản ghi.
- CPU, memory, disk I/O và network.
- Lock wait, deadlock và thời gian transaction.
- Replication lag và độ trễ đồng bộ.
- Query latency và error rate của ứng dụng đang hoạt động.
- Queue depth và consumer lag.
- Dung lượng tạm, log và WAL/binlog.
- Tỷ lệ retry và batch thất bại.

Kiểm thử trên dữ liệu đại diện về kích thước và phân bố. DDL có thể có hành vi lock khác nhau tùy engine và version; cần xác minh đúng phiên bản database mục tiêu. Với migration online, thử nghiệm khi ứng dụng đang đọc/ghi để quan sát ảnh hưởng thực tế.

Đặt ngưỡng dừng và cơ chế throttling. Nếu migration làm suy giảm dịch vụ vượt mức cho phép, cần giảm tốc độ hoặc dừng an toàn thay vì tiếp tục chỉ để đạt thời gian dự kiến.

## 13. Kiểm thử dữ liệu biên, chuyển đổi mất thông tin và quy tắc nghiệp vụ

Một migration có thể chuyển đổi thành công phần lớn dữ liệu nhưng sai ở những trường hợp ít gặp. Cần thiết kế test theo quy tắc nghiệp vụ, không chỉ theo kiểu dữ liệu.

Ví dụ khi đổi tiền từ integer đơn vị nhỏ nhất sang decimal:

- Kiểm tra giá trị âm, bằng không và giá trị lớn.
- Kiểm tra precision và scale.
- Kiểm tra làm tròn và quy tắc tiền tệ.
- Kiểm tra null hoặc giá trị cũ không hợp lệ.
- Đối chiếu tổng tiền theo tài khoản và giao dịch.
- Xác minh báo cáo và API diễn giải đúng đơn vị mới.

Khi hợp nhất hai trường hoặc nhiều bản ghi, cần kiểm tra quy tắc ưu tiên khi dữ liệu mâu thuẫn, cách giữ lịch sử và cách xử lý bản ghi trùng. Nếu migration làm mất thông tin, cần phê duyệt rõ, ghi audit và lưu dữ liệu nguồn theo chính sách.

Với dữ liệu thời gian, kiểm tra timezone, daylight saving, độ chính xác timestamp và thứ tự sự kiện. Với chuỗi, kiểm tra Unicode normalization, collation và độ dài. Với ID, kiểm tra format, tính duy nhất và quan hệ tham chiếu.

## 14. Kiểm thử quyền truy cập và bảo vệ dữ liệu trong quá trình chuyển đổi

Migration thường chạy bằng tài khoản có quyền cao và có thể truy cập lượng dữ liệu lớn. Vì vậy, cần kiểm tra cả bảo mật của quá trình.

- Tài khoản migration có quyền tối thiểu cần thiết.
- Secret không xuất hiện trong log, command output hoặc artifact.
- Quyền đọc/ghi sau migration vẫn đúng theo role và tenant.
- Row-level security, policy, grant và ownership không bị mất.
- Dữ liệu nhạy cảm không bị ghi vào bảng tạm hoặc log không bảo vệ.
- Backup, snapshot và bản sao kiểm thử được bảo vệ.
- Audit log ghi nhận người thực hiện, thời điểm và phiên bản migration.
- Quyền tạm thời được thu hồi sau khi hoàn tất.
- Migration không vô tình mở rộng quyền của ứng dụng.

Nếu thay đổi schema liên quan tenant hoặc quyền, phải kiểm tra dữ liệu giữa các tenant không bị trộn. Kiểm thử bằng các vai trò khác nhau và xác minh cả truy vấn trực tiếp lẫn luồng API sử dụng dữ liệu sau migration.

## 15. Thiết kế test suite cho migration

Một bộ kiểm thử migration nên có nhiều lớp:

| Lớp kiểm thử | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test cho transform | Kiểm tra quy tắc biến đổi dữ liệu nhỏ | Chuyển định dạng ngày, tách tên |
| Schema test | Xác minh cấu trúc và constraint | Kiểu cột, index, khóa ngoại |
| Migration integration test | Chạy migration trên database thật hoặc engine tương thích | Upgrade từ schema N lên N+1 |
| Data reconciliation test | Đối chiếu dữ liệu trước/sau | Count, aggregate, relationship |
| Version compatibility test | Kiểm tra ứng dụng cũ/mới cùng schema | App N-1 với schema expand |
| Failure/restart test | Kiểm tra gián đoạn và chạy lại | Dừng giữa batch rồi resume |
| Performance test | Đánh giá lock và tài nguyên | Backfill trên dataset lớn |
| Security test | Kiểm tra quyền và dữ liệu nhạy cảm | Tenant isolation, migration role |
| Recovery test | Kiểm chứng rollback/restore/roll-forward | Restore snapshot và đối soát |

Tách test nhanh trong pull request khỏi migration test quy mô lớn nếu chi phí môi trường cao. Tuy nhiên, migration bắt buộc phải có gate phù hợp trước release. Có thể chạy test schema và transform trên mỗi thay đổi, còn test dữ liệu lớn, hiệu năng và restore chạy trên môi trường chuyên biệt theo lịch hoặc trước release quan trọng.

## 16. Tích hợp kiểm thử migration vào CI/CD

Một pipeline có thể tổ chức như sau:

~~~text
Validate migration files
    |
    v
Build application and migration artifact
    |
    v
Create disposable database from source schema
    |
    v
Load representative fixture / snapshot
    |
    v
Run upgrade migration
    |
    +--> Verify schema
    |
    +--> Reconcile data
    |
    +--> Test old/new application compatibility
    |
    +--> Test restart/idempotency where applicable
    |
    v
Run application smoke and integration tests
    |
    v
Publish migration evidence and approval gate
~~~

Các bước cụ thể phụ thuộc nền tảng CI và database. Môi trường migration test nên được tạo mới hoặc reset có kiểm soát để kết quả lặp lại. Không dùng database dùng chung mà một pipeline khác có thể thay đổi giữa chừng.

Artifact migration cần gắn với commit và phiên bản ứng dụng. Báo cáo nên nêu schema nguồn, schema đích, dataset, số bản ghi, thời gian chạy, chênh lệch được giải thích, phiên bản database và kết quả tương thích.

## 17. Phối hợp rollout giữa migration và ứng dụng

Triển khai migration và ứng dụng cần có thứ tự rõ. Một kế hoạch thường gặp:

1. Backup hoặc snapshot và xác minh khả năng restore.
2. Chạy bước expand tương thích.
3. Xác minh schema mở rộng.
4. Triển khai ứng dụng có khả năng đọc/ghi tương thích.
5. Chạy backfill và theo dõi tiến độ.
6. Đối chiếu dữ liệu và xử lý bản ghi lỗi.
7. Chuyển ứng dụng sang cấu trúc mới.
8. Theo dõi tất cả consumer, worker và batch job.
9. Ngừng phiên bản cũ và xác minh không còn truy cập cấu trúc cũ.
10. Chạy bước contract để loại bỏ cấu trúc cũ khi đủ điều kiện.

Trong thực tế, các bước có thể xen kẽ tùy kiến trúc. Điều quan trọng là mỗi bước có điều kiện vào/ra, người sở hữu và cách phục hồi. Không thực hiện bước contract chỉ vì ứng dụng chính đã cập nhật; cần xác nhận worker, báo cáo, script vận hành và consumer ngoài cũng đã chuyển đổi.

## 18. Quản lý phát hiện, sai lệch và quyết định go/no-go

Trong quá trình migration, cần ghi lại phát hiện và quyết định theo mức độ ảnh hưởng.

Một báo cáo nên gồm:

- Migration ID, commit và phiên bản ứng dụng.
- Schema nguồn và schema đích.
- Dataset và thời điểm tạo snapshot.
- Số lượng bản ghi trước/sau và phép đối chiếu.
- Các chênh lệch đã giải thích hoặc chưa giải thích.
- Thời gian, tài nguyên và lock.
- Phiên bản ứng dụng/worker đã được kiểm tra.
- Lỗi, batch retry và trạng thái tiếp tục.
- Kết quả rollback/restore nếu đã diễn tập.
- Rủi ro còn lại, người sở hữu và phê duyệt.

Điều kiện go/no-go nên được định nghĩa trước. Ví dụ, không có chênh lệch dữ liệu quan trọng chưa giải thích; phiên bản cũ còn trong cửa sổ triển khai vẫn hoạt động; migration hoàn tất trong giới hạn tài nguyên; backup/restore có bằng chứng; và các gate bảo mật bắt buộc đạt.

Nếu có chênh lệch nhỏ được chấp nhận theo quy tắc, phải ghi rõ tiêu chí và người phê duyệt. Không bỏ qua sai lệch chỉ để kịp cửa sổ release.

## 19. Ví dụ: chuyển đổi trường trạng thái đơn hàng

Một hệ thống đang lưu status dạng chuỗi tự do như new, paid, shipped, cancelled. Nhóm muốn chuẩn hóa thành mã trạng thái và thêm bảng lịch sử trạng thái.

### Thiết kế thay đổi

- Thêm status_code và bảng order_status_history.
- Giữ status cũ trong giai đoạn chuyển tiếp.
- Ứng dụng mới đọc status_code nếu có, nếu chưa thì dùng quy tắc fallback.
- Khi ghi, cập nhật cấu trúc mới và duy trì tương thích với phiên bản cũ theo cơ chế được thiết kế.
- Backfill dữ liệu cũ thành mã chuẩn và tạo lịch sử ban đầu theo quy tắc.
- Sau khi mọi consumer chuyển sang cấu trúc mới, loại bỏ status cũ trong một release riêng.

### Kịch bản kiểm thử

1. Chạy migration trên dataset có đủ trạng thái hợp lệ, giá trị lạ, null và bản ghi lịch sử.
2. Đối chiếu số lượng đơn hàng theo từng trạng thái trước và sau.
3. Xác minh mapping new, paid, shipped, cancelled và cách xử lý giá trị không nhận diện.
4. Chạy ứng dụng cũ trên schema mở rộng.
5. Chạy ứng dụng mới trước và sau backfill.
6. Gửi cập nhật trạng thái trong lúc backfill để kiểm tra race condition.
7. Dừng tiến trình giữa batch rồi chạy tiếp.
8. Kiểm tra event và báo cáo vẫn diễn giải đúng trạng thái.
9. Khôi phục snapshot trên môi trường thử nghiệm và đối chiếu dữ liệu.
10. Chỉ contract schema sau khi không còn consumer dùng trường cũ.

Nếu một bản ghi có trạng thái không nhận diện, nhóm cần quy tắc xử lý rõ như đưa vào danh sách cần điều tra hoặc ánh xạ theo quyết định nghiệp vụ. Không tự động gán về new vì có thể làm sai trạng thái đơn hàng và báo cáo.

## 20. Các sai lầm thường gặp khi kiểm thử chuyển đổi

- **Chỉ chạy migration trên database trống:** bỏ sót dữ liệu lịch sử và trường hợp biên.
- **Chỉ kiểm tra lệnh migration thành công:** không xác minh schema, dữ liệu và hành vi ứng dụng.
- **Không kiểm tra phiên bản cũ:** gây lỗi trong rolling deployment.
- **Xóa cấu trúc cũ quá sớm:** worker, batch hoặc báo cáo vẫn phụ thuộc.
- **Không thử gián đoạn:** migration không thể tiếp tục hoặc tạo dữ liệu trùng khi chạy lại.
- **Không đo tác động hiệu năng:** lock và backfill làm suy giảm dịch vụ.
- **Tin rằng rollback ứng dụng khôi phục dữ liệu:** dữ liệu đã chuyển đổi hoặc side effect có thể không đảo ngược.
- **Không đối chiếu nghiệp vụ:** count bằng nhau nhưng giá trị hoặc trạng thái đã sai.
- **Dùng dữ liệu production không bảo vệ:** tạo rủi ro quyền riêng tư và bảo mật.
- **Không kiểm tra consumer ngoài ứng dụng chính:** API, queue, report hoặc batch bị phá vỡ.
- **Không lưu bằng chứng:** không thể giải thích chênh lệch hoặc tái hiện sự cố.

## 21. Quy trình kiểm thử chuyển đổi schema, dữ liệu và phiên bản

Có thể áp dụng quy trình tổng hợp:

1. **Lập bản đồ phụ thuộc:** xác định schema, dữ liệu, producer, consumer, worker và phiên bản ứng dụng.
2. **Đánh giá rủi ro:** xác định dữ liệu quan trọng, yêu cầu downtime, tương thích và phục hồi.
3. **Chuẩn bị baseline:** tạo snapshot/dataset đại diện và ghi số liệu trước migration.
4. **Thiết kế các bước chuyển đổi:** expand, backfill, switch và contract; nêu điều kiện từng bước.
5. **Thiết kế ma trận tương thích:** xác định tổ hợp phiên bản ứng dụng và schema cần hỗ trợ.
6. **Kiểm thử schema và transform:** xác minh cấu trúc, mapping, constraint và quy tắc nghiệp vụ.
7. **Kiểm thử vận hành migration:** batch, retry, idempotency, restart, lock và hiệu năng.
8. **Kiểm thử phục hồi:** diễn tập rollback, restore hoặc roll-forward trên bản sao.
9. **Tích hợp CI/CD:** tự động hóa gate, lưu bằng chứng và gắn với artifact.
10. **Rollout có kiểm soát:** triển khai theo thứ tự, theo dõi và đối chiếu dữ liệu.
11. **Contract và đóng chuyển đổi:** chỉ loại bỏ cấu trúc cũ khi mọi consumer đã chuyển.
12. **Theo dõi sau phát hành:** kiểm tra lỗi dữ liệu, latency, queue, đối soát và khả năng phục hồi.

~~~mermaid
flowchart TD
    A["Lập bản đồ schema, dữ liệu và consumer"] --> B["Baseline và đánh giá rủi ro"]
    B --> C["Thiết kế expand / backfill / switch / contract"]
    C --> D["Kiểm thử schema và quy tắc chuyển đổi"]
    D --> E["Kiểm thử tương thích phiên bản cũ/mới"]
    E --> F["Kiểm thử restart, hiệu năng và phục hồi"]
    F --> G{"Bằng chứng đạt?"}
    G -->|Không| H["Sửa migration hoặc kế hoạch phục hồi"]
    H --> D
    G -->|Có| I["Triển khai expand và ứng dụng tương thích"]
    I --> J["Backfill và đối chiếu dữ liệu"]
    J --> K["Chuyển consumer sang cấu trúc mới"]
    K --> L["Xác minh không còn phụ thuộc cũ"]
    L --> M["Contract và theo dõi sau phát hành"]
~~~

## 22. Checklist kiểm thử chuyển đổi schema, dữ liệu và phiên bản ứng dụng

Trước khi phê duyệt migration hoặc release liên quan, hãy kiểm tra:

- Phạm vi schema, dataset, ứng dụng và consumer đã được lập bản đồ chưa?
- Dataset kiểm thử có đại diện cho dữ liệu lịch sử, giá trị biên và quy mô thực tế không?
- Baseline về số lượng, quan hệ và tổng hợp nghiệp vụ đã được lưu chưa?
- Schema sau migration có đúng kiểu, constraint, index, quyền và object không?
- Dữ liệu có được đối chiếu theo quy tắc nghiệp vụ, không chỉ theo số lượng không?
- Phiên bản cũ và mới có được kiểm tra trong các giai đoạn cùng tồn tại không?
- Expand-contract và thời điểm loại bỏ cấu trúc cũ đã rõ chưa?
- Backfill có checkpoint, retry, idempotency và xử lý bản ghi lỗi không?
- Có kiểm thử cập nhật đồng thời và race condition trong khi migration chạy không?
- Migration có được thử khi gián đoạn, chạy lại và tiếp tục không?
- Lock, replication lag, tài nguyên và latency ứng dụng có nằm trong giới hạn không?
- API, event, queue, report và consumer có tương thích không?
- Backup, restore, rollback hoặc roll-forward đã được diễn tập chưa?
- Quyền migration, secret, audit và dữ liệu nhạy cảm được bảo vệ không?
- Gate go/no-go, người phê duyệt và phương án xử lý sai lệch đã được xác định chưa?
- Có bằng chứng cho thấy mọi consumer đã rời cấu trúc cũ trước contract không?

Kiểm thử chuyển đổi schema, dữ liệu và phiên bản ứng dụng phải chứng minh cả ba phần cùng đúng: cấu trúc mới hợp lệ, dữ liệu giữ nguyên ý nghĩa theo quy tắc và mọi phiên bản được phép cùng tồn tại đều hoạt động an toàn. Khi migration được chia giai đoạn, kiểm tra trên dữ liệu đại diện, thử gián đoạn và phục hồi, đồng thời liên kết bằng chứng với từng phiên bản, nhóm có thể giảm nguy cơ mất dữ liệu và triển khai không tương thích. Chỉ loại bỏ cấu trúc cũ sau khi đã xác minh toàn bộ consumer và phương án phục hồi theo đúng kế hoạch.

