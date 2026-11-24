# Token cleanup schedule

## 1. Lịch dọn token giải quyết vấn đề gì?

Trong khôi phục tài khoản, token đặt lại mật khẩu, token tiếp tục xác minh MFA và các quyền tạm phục vụ đăng ký lại passkey có thể tạo ra nhiều bản ghi tồn tại sau khi hết giá trị sử dụng. Token cleanup schedule là lịch và cơ chế xử lý những dữ liệu đã đủ điều kiện dọn, nhằm giới hạn lượng dữ liệu nhạy cảm lưu lại và duy trì khả năng vận hành của kho token.

Một thiết kế tốt trả lời được: dữ liệu nào được dọn, từ thời điểm nào, theo lô bao nhiêu, có phụ thuộc nào phải giữ và điều gì xảy ra khi tác vụ chạy chậm hoặc bị gián đoạn. “Chạy DELETE mỗi đêm” chưa thể hiện đầy đủ những quyết định đó.

OWASP yêu cầu token khôi phục dùng một lần và hết hạn sau thời gian phù hợp. Lịch dọn hỗ trợ quản lý dữ liệu phía sau; hiệu lực token vẫn phải được kiểm tra tại endpoint sử dụng. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 2. Tách thời hạn quyền khỏi thời điểm xóa dữ liệu

Cần phân biệt ba hoạt động:

| Hoạt động | Mục tiêu | Thời điểm quyết định |
| --- | --- | --- |
| Kiểm tra hiệu lực | Chặn token hết hạn, đã dùng hoặc bị thu hồi | Mỗi lần token được trình lên |
| Chuẩn hóa vòng đời | Ghi nhận `EXPIRED` và sự kiện liên quan nếu cần | Khi endpoint hoặc worker phát hiện đến hạn |
| Dọn dữ liệu | Xóa verifier, payload giao nhận hoặc metadata đủ điều kiện | Theo chính sách lưu giữ và phụ thuộc |

Ví dụ token hết hạn lúc `10:10:00Z`, worker ghi nhận `EXPIRED` lúc `10:10:18Z`, còn bản ghi được dọn vào hôm sau. Token không được dùng trong khoảng 18 giây chờ worker hoặc khoảng thời gian giữ metadata sau đó.

Với token opaque tra cứu qua kho dữ liệu, endpoint phải từ chối khi bản ghi không tồn tại. Không có nhánh “không tìm thấy vì đã dọn nên cho phép dựa trên token”. Việc dọn cũng không được tạo lại bản ghi `ISSUED` khi người dùng trình bí mật cũ.

Token cleanup không đồng nghĩa với khóa tài khoản, đổi mật khẩu, gỡ MFA hoặc đăng xuất mọi phiên. Những thay đổi bảo mật đó cần được quyết định bởi luồng khôi phục và chính sách riêng.

## 3. Xác định đơn vị dữ liệu và thời gian lưu riêng

Không áp một thời gian lưu duy nhất cho mọi dữ liệu quanh token:

| Loại dữ liệu | Điều kiện dọn cần xem xét |
| --- | --- |
| Token thô trong hàng đợi gửi | Hết nhu cầu gửi/retry, bị hủy hoặc token không còn được phép giao |
| Verifier và metadata token | Vòng đời đã kết thúc, hết thời gian lưu, không còn phụ thuộc bắt buộc |
| Recovery grant hoặc session hạn chế | Chính quyền đó đã hết hiệu lực hoặc bị thu hồi, theo lịch riêng |
| Outbox và thông điệp chờ xử lý | Đã hoàn tất hợp đồng giao nhận hoặc được xử lý ngoại lệ có kiểm soát |
| Dấu chống replay/idempotency | Đã đi qua cửa sổ replay và retry mà giao thức còn chấp nhận |
| Audit | Theo chính sách truy vết riêng, chỉ giữ các trường cần thiết |

Một payload email có token thô nên có lịch ngừng retry và dọn phù hợp, thay vì được giữ lâu chỉ vì metadata phục vụ audit còn cần. Ngược lại, xóa verifier không nên kéo theo xóa toàn bộ audit của một lần khôi phục đáng ngờ.

Token dành cho nhập thủ công và token link dài có thể có thời gian hiệu lực khác nhau. Tuy nhiên, khác biệt đó không tự xác định thời gian giữ outbox, tombstone hoặc bản sao lưu. Mỗi nhóm cần một lý do lưu cụ thể.

## 4. Tính mốc đủ điều kiện dọn

Một mô hình dữ liệu minh họa có các trường:

```text
status             : ISSUED | CONSUMED | EXPIRED | REVOKED | SUPERSEDED
expires_at         : hạn sử dụng tuyệt đối của token
effective_end_at   : thời điểm quyền thực sự kết thúc
terminal_recorded_at: lúc hệ thống ghi nhận trạng thái cuối
purge_after        : mốc sớm nhất cho phép xét dọn
retention_hold     : có đang được giữ phục vụ xử lý riêng hay không
retention_policy   : phiên bản chính sách dùng để tính mốc lưu
```

Với hết hạn tự nhiên, `effective_end_at` có thể bằng `expires_at`; với token đã dùng hoặc thu hồi trước hạn, nó là thời điểm chuyển trạng thái tương ứng. `terminal_recorded_at` có thể muộn hơn, đặc biệt khi worker bị gián đoạn.

Chính sách phải chọn rõ tính thời gian lưu metadata từ mốc kết thúc quyền hay từ mốc ghi nhận. Nếu việc điều tra cần dữ liệu tối thiểu sau khi hệ thống phát hiện sự kiện, tính hoàn toàn từ `expires_at` có thể khiến bản ghi được dọn ngay lúc vừa được phát hiện muộn.

Ví dụ công thức, với các mốc được định nghĩa bởi chính sách:

```text
metadata_not_before = chosen_retention_origin + metadata_retention
purge_after = max(metadata_not_before, replay_protection_not_before)

eligible = terminal_status
           AND purge_after <= trusted_cutoff
           AND retention_hold == false
           AND required_dependencies_are_satisfied
```

Các phụ thuộc phải được kiểm tra tại lúc dọn, vì một timestamp đã tính trước không tự phản ánh trạng thái outbox hay yêu cầu giữ mới được đặt. Thiếu `purge_after` hoặc chính sách không hợp lệ nên đưa bản ghi vào diện cần xử lý, không mặc định là đủ điều kiện xóa.

Với token ký tự chứa đủ thông tin và được xác minh độc lập, bản ghi thu hồi có thể là điều kiện đang ngăn token hoạt động. Xóa dấu thu hồi quá sớm có thể làm token cũ được chấp nhận trở lại. Cần giữ cơ chế chặn đến hết cửa sổ hiệu lực và sai lệch thời gian mà verifier thực sự cho phép.

## 5. Chọn nhịp chạy và công suất theo tải thực tế

Các tham số thường cần cấu hình gồm:

| Tham số | Ý nghĩa |
| --- | --- |
| Chu kỳ kích hoạt | Khoảng cách giữa các lần đánh thức worker |
| `batch_size` | Giới hạn số bản ghi trong một giao dịch |
| Số lô hoặc ngân sách thời gian | Ngăn một lượt chạy chiếm tài nguyên vô hạn |
| Timeout và giới hạn retry | Giữ tác vụ có thể dừng và phục hồi |
| Giới hạn theo tenant/shard | Tránh một phạm vi nhiều dữ liệu chiếm hết công suất |

Giả sử trung bình có 20 bản ghi mỗi giây mới đủ điều kiện dọn. Nếu thực tế một worker commit bốn lô, mỗi lô 500 bản ghi trong mỗi khoảng 60 giây, công suất trung bình là:

```text
mu = 4 * 500 / 60 ≈ 33,3 bản ghi/giây
lambda = 20 bản ghi/giây
```

Công suất trung bình cao hơn tốc độ dữ liệu đến tạo dư địa xử lý tồn đọng, nhưng còn phải xét thời gian truy vấn, tải đỉnh và phụ thuộc khiến một số hàng chưa được dọn. Các con số chỉ minh họa cách tính, không phải cấu hình chuẩn.

Dùng khoảng thời gian giữa các lượt chạy thực tế để tính công suất. Nếu scheduler chờ thêm một phút sau khi job hoàn tất, chu kỳ thực tế còn gồm thời gian job chạy. Không dùng cấu hình “60 giây” để suy ra công suất mà bỏ qua phần thời gian đó.

Nhịp chạy ngắn thường giúp giảm lượng dữ liệu đủ điều kiện còn lưu và chia nhỏ tải. Nhịp quá dày với truy vấn thiếu chỉ mục lại có thể làm tốn tài nguyên. Chọn điểm bắt đầu theo mục tiêu vận hành, rồi điều chỉnh bằng thời gian chạy, backlog và tải DB.

## 6. Một lượt dọn có giới hạn

Mã giả cho worker:

```text
on scheduled activation:
    establish authorized tenant/shard scope
    set run budget and maximum batch size

    while run budget remains:
        cutoff = trusted_database_time()
        begin short transaction
            select and lock an eligible batch
            recheck lifecycle, hold and dependency rules
            delete or minimize permitted token data
            record minimal cleanup evidence
        commit

        if no rows were processed:
            stop this run

    report committed counts, duration and outstanding blockers
```

Tác vụ chuẩn hóa `ISSUED` đã quá hạn có thể chạy trước hoặc ở một worker riêng. Nếu cần phát sự kiện hết hạn, nó phải ghi trạng thái cùng outbox bền vững trước khi bản ghi đủ điều kiện bị dọn. Không xóa trực tiếp `ISSUED` quá hạn rồi hy vọng có thể dựng lại sự kiện từ dữ liệu đã mất.

Mỗi lô nên là một giao dịch ngắn. Không mở một giao dịch bao trùm hàng triệu token hoặc gọi dịch vụ email bên ngoài trong lúc giữ khóa hàng. Khi hết ngân sách lượt chạy, worker dừng giữa các lô đã commit và tiếp tục ở lần kích hoạt sau.

Lịch quét nên dựa trên điều kiện đủ hạn hiện tại, không chỉ trên khoảng “kể từ lần chạy gần nhất”. Nếu bỏ lỡ lịch hoặc tiến trình dừng, lần sau vẫn tìm được các hàng cũ chưa dọn.

## 7. Ví dụ xóa theo lô trong PostgreSQL

Ví dụ sau dành cho mô hình token opaque có bản ghi bắt buộc khi xác minh. `:tenant_id`, `:cutoff` và `:batch_size` là tham số được tầng truy cập dữ liệu bind, không phải phép nối chuỗi SQL. `batch_size` phải là số nguyên dương có giới hạn, không được là `NULL`.

```sql
WITH candidates AS (
    SELECT t.id
    FROM recovery_token AS t
    WHERE t.tenant_id = :tenant_id
      AND t.status IN ('CONSUMED', 'EXPIRED', 'REVOKED', 'SUPERSEDED')
      AND t.purge_after <= :cutoff
      AND t.retention_hold = false
      AND NOT EXISTS (
          SELECT 1
          FROM recovery_outbox AS e
          WHERE e.tenant_id = t.tenant_id
            AND e.token_id = t.id
            AND e.delivery_state <> 'PUBLISHED'
      )
    ORDER BY t.purge_after, t.id
    LIMIT :batch_size
    FOR UPDATE OF t SKIP LOCKED
)
DELETE FROM recovery_token AS t
USING candidates AS c
WHERE t.id = c.id
  AND t.tenant_id = :tenant_id
RETURNING t.id;
```

Schema minh họa giả định các trường trạng thái và hold không được `NULL`, token ID là duy nhất, và các phụ thuộc ngoài outbox đã được giải quyết theo chính sách. `PUBLISHED` ở đây nghĩa là hoàn tất nghĩa vụ giao nhận của producer theo hợp đồng đã chọn; nó không tự chứng minh mọi consumer đã xử lý xong.

Nếu khóa ngoại vẫn buộc giữ token, câu lệnh sẽ thất bại thay vì tự giải quyết phụ thuộc. Cần thiết kế vòng đời quan hệ trước: giữ audit/outbox tối thiểu độc lập khi phù hợp, hoặc dọn quan hệ con đúng phạm vi. Không thêm `ON DELETE CASCADE` chỉ để tránh lỗi nếu điều đó làm mất event hoặc dấu vết cần giữ.

PostgreSQL hỗ trợ dùng CTE chọn lô kết hợp `DELETE ... USING`; bản thân `DELETE` không có `LIMIT`. `RETURNING` cung cấp những hàng thực sự bị xóa để tính kết quả xử lý. [Nguồn: PostgreSQL DELETE](https://www.postgresql.org/docs/current/sql-delete.html).

## 8. Chỉ mục và xử lý đồng thời

Một chỉ mục minh họa cho truy vấn theo tenant:

```sql
CREATE INDEX recovery_token_cleanup_idx
    ON recovery_token (tenant_id, purge_after, id)
    WHERE status IN ('CONSUMED', 'EXPIRED', 'REVOKED', 'SUPERSEDED')
      AND retention_hold = false;
```

Truy vấn phụ thuộc outbox cũng cần đường truy cập phù hợp với tenant, token ID và trạng thái giao nhận. Chỉ giới hạn số hàng bị xóa chưa chắc giới hạn được số hàng phải đọc; một bảng lớn thiếu chỉ mục vẫn có thể bị quét nặng trong mỗi lượt chạy.

`SKIP LOCKED` cho phép bỏ qua hàng đang bị khóa, hữu ích khi nhiều worker cùng lấy việc. Nó không cung cấp một ảnh chụp đầy đủ để kết luận toàn bộ kho đã hết backlog. Một lô không trả hàng có thể là do các hàng còn lại đang bị worker khác giữ. [Nguồn: PostgreSQL SELECT — Locking Clause](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE).

Trong mô hình SQL ở trên, các nghĩa vụ outbox được tạo nguyên tử với chuyển trạng thái vòng đời và không được tạo mới sau khi token đã vào trạng thái cuối. Nếu hệ thống cho thêm phụ thuộc muộn, cần giao thức khóa và đọc lại phù hợp; không giả định `NOT EXISTS` trên một snapshot tự ngăn mọi thao tác ghi ở bảng khác.

Endpoint tiêu thụ token, worker ghi nhận hết hạn và worker dọn phải thống nhất cách khóa hoặc kiểm tra phiên bản. Nếu endpoint lấy khóa token còn hợp lệ trước, cleanup không thể xóa token đó như một hàng đã kết thúc. Nếu cleanup đã xóa một hàng thực sự đủ điều kiện trước, endpoint phải từ chối do không tìm thấy bản ghi.

Tránh phân trang bằng `OFFSET` trên tập hàng đang bị xóa vì vị trí dịch chuyển sau mỗi lô. Có thể lặp lấy lô đủ điều kiện đầu tiên theo khóa ổn định. Nếu dùng cursor theo `(purge_after, id)`, phải có lượt quét lại để không bỏ sót hàng từng bị khóa hoặc vừa được bỏ hold với mốc cũ.

## 9. Scheduler trong môi trường nhiều instance

Một lịch cục bộ thường chạy trên từng instance cài đặt lịch đó. Nếu ứng dụng có nhiều replica, không nên mặc định job chỉ chạy một lần trên toàn cụm.

Có thể chọn một trong hai hướng:

| Cách điều phối | Điều kiện để an toàn |
| --- | --- |
| Một worker điều phối tại mỗi thời điểm | Cơ chế nhận quyền có lease/khóa phù hợp, có phục hồi khi worker chết |
| Nhiều worker chia lô | Khóa hàng hoặc nhận việc nguyên tử, giới hạn tài nguyên và thao tác có thể lặp |

Lease hết hạn không chứng minh tiến trình cũ đã dừng. Nếu chỉ dựa vào lease để cho phép tác vụ phá hủy, cần cơ chế ngăn chủ sở hữu cũ tiếp tục thực thi hoặc một giao thức dữ liệu vẫn an toàn khi hai worker chồng lấn. Lô xóa có khóa và điều kiện đúng giúp giới hạn nguy cơ này.

Job khởi động sau triển khai hoặc sự cố nên có giới hạn công suất. Không cho mọi replica đồng loạt quét toàn kho để “bù lịch”. Có thể phân shard, thêm jitter vào thời điểm kích hoạt và giới hạn số lô đang chạy đồng thời.

Nếu lịch dùng giờ theo ngày, cần cấu hình múi giờ rõ ràng. Các mốc hiệu lực và dọn được lưu dưới dạng thời điểm tuyệt đối, thường biểu diễn UTC. Đồng hồ phục vụ tính mốc phải được đồng bộ và theo dõi; lỗi đồng hồ đi nhanh có thể làm dọn sớm, nên không được bù bằng cách bỏ mọi điều kiện giữ dữ liệu.

## 10. Outbox, grant và dấu chống replay cần lịch phối hợp

Trước khi dọn token, cần biết thành phần nào còn phụ thuộc vào dữ liệu đó. Có thể cho event mang metadata tối thiểu đủ để consumer xử lý mà không phải đọc lại một token đã hết vòng đời. Không đính kèm token thô hoặc digest vào event chỉ để tránh giữ hàng nguồn.

Nếu consumer bắt buộc đọc bản ghi token, thời gian lưu phải bao phủ hợp đồng xử lý thực tế hoặc có cơ chế xác nhận phù hợp. Xóa ngay sau khi producer publish không đủ trong trường hợp này. Một event đang retry không nên bị đổi thành `PUBLISHED` chỉ để mở đường cho cleanup.

Outbox kẹt cần có cảnh báo và quy trình giải quyết, không giữ bí mật vô hạn cũng không bỏ qua lỗi. Có thể tách metadata cần đối soát khỏi payload chứa bí mật, rồi dọn từng phần theo chính sách riêng.

Recovery grant đã được cấp có thể còn hạn sau khi token gốc được tiêu thụ. Hệ thống cần chọn rõ grant có phụ thuộc trực tiếp vào hàng token hay có bản ghi quyền độc lập. Cleanup phải giữ được ràng buộc giao dịch và khả năng thu hồi của grant; không xóa cascade khiến quyền tạm thay đổi ngoài thiết kế.

Dấu dedupe của consumer và idempotency của endpoint cũng không nên bị dọn sớm hơn cửa sổ giao lại mà hệ thống cho phép. Nếu broker phát lại một event sau khi dấu chống trùng đã mất, tác dụng phụ có thể xảy ra lần nữa. Thời gian lưu của các thành phần này cần được phối hợp với chính sách replay.

## 11. Gián đoạn, retry và việc xóa một phần

| Điểm xảy ra lỗi | Cách tiếp tục |
| --- | --- |
| Tiến trình dừng trước commit lô | Giao dịch rollback; hàng còn đủ điều kiện được xét lại |
| Commit thành công nhưng mất phản hồi | Chạy lại điều kiện dọn; hàng đã xóa không xuất hiện nữa |
| Hết timeout hoặc gặp deadlock | Rollback lô, retry có giới hạn và backoff phù hợp |
| Kho dữ liệu không truy cập được | Giữ nguyên dữ liệu, ghi nhận job thất bại và thử lại sau |
| Một tenant có phụ thuộc kẹt | Tách nguyên nhân và phạm vi, tiếp tục tenant khác nếu điều phối cho phép |
| Một hàng liên tục bị khóa | Theo dõi tuổi tồn đọng và chủ thể giữ khóa, không xem nó là đã dọn |

Chỉ cộng số lượng xóa vào kết quả thành công sau khi giao dịch commit. `RETURNING` từ câu lệnh chưa commit không phải bằng chứng dữ liệu đã được dọn bền vững. Nếu cần audit từng lô bền vững, ghi audit tối thiểu trong cùng giao dịch hoặc bằng cơ chế có hợp đồng phục hồi rõ.

Tác vụ dọn nên có thể chạy lại dựa trên điều kiện hiện tại. Không cần một cờ “đã chạy hôm nay” duy nhất khiến lần chạy dở ngăn mọi lần tiếp theo trong ngày.

Khả năng dọn bị gián đoạn không được kéo dài quyền token: endpoint vẫn kiểm tra trạng thái và thời hạn. Nếu chính kho trạng thái cần cho quyết định quyền bị lỗi, endpoint không được tiếp tục thay đổi tài khoản dựa trên suy đoán từ cache.

## 12. Bản sao dữ liệu và bảo trì dung lượng

Xóa hàng trên DB chính không chứng minh token đã biến mất khỏi replica, snapshot, bản sao lưu, WAL, cache hoặc hàng đợi gửi. Từng lớp cần cơ chế hết hạn và quản lý truy cập tương ứng.

Trong PostgreSQL, `DELETE` không lập tức loại bỏ phiên bản hàng cũ khỏi vùng lưu trữ do MVCC. Vacuum giúp thu hồi không gian cho tái sử dụng; vacuum thông thường cũng không nhất thiết trả toàn bộ không gian về hệ điều hành. Vì vậy, giảm số hàng hiện hữu và giảm kích thước tệp trên đĩa là hai việc khác nhau. [Nguồn: PostgreSQL Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-SPACE-RECOVERY).

Cần theo dõi tác động xóa lên I/O, các phiên bản hàng chết, WAL và độ trễ replica. Không gọi `VACUUM FULL` trong mỗi lượt cleanup nhỏ: thao tác này có yêu cầu khóa và chi phí khác với xóa theo lô. Việc bảo trì DB cần được điều phối theo tải thực tế. [Nguồn: PostgreSQL Vacuuming Basics](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-BASICS).

Nếu dùng partition theo thời gian, chỉ bỏ một partition khi mọi hàng trong đó đều đủ điều kiện theo vòng đời, hold và phụ thuộc. Partition dựa trên ngày phát hành chưa chắc phản ánh ngày được phép dọn, đặc biệt khi các loại token có thời gian lưu khác nhau.

Khôi phục backup có thể đưa token đã dùng về trạng thái `ISSUED` hoặc phục hồi dấu quyền đã bị thu hồi. Trước khi mở lại recovery, cần đối soát dấu tiêu thụ/thu hồi từ nguồn còn đáng tin hoặc vô hiệu phạm vi token bị ảnh hưởng theo cơ chế được verifier kiểm tra. Không chỉ chạy cleanup rồi coi snapshot đã an toàn.

## 13. Quan sát được tiến độ và nguyên nhân chưa dọn

Một job “chạy thành công” nhưng xóa 0 hàng trong nhiều ngày có thể đang gặp lỗi điều kiện hoặc tất cả dữ liệu bị kẹt ở một phụ thuộc. Cần quan sát cả hoạt động job lẫn tình trạng dữ liệu.

Các chỉ số hữu ích gồm:

- Thời điểm kích hoạt gần nhất và thời điểm commit thành công gần nhất.
- Số hàng xét, số hàng thực sự dọn, số lô commit và thời gian từng lô.
- Số hàng đủ điều kiện còn tồn và tuổi trễ của hàng cũ nhất.
- Số hàng bị giữ do hold, outbox, grant, khóa hoặc dữ liệu chính sách không hợp lệ.
- Tỷ lệ lỗi, timeout, retry cùng tải DB và độ trễ replica liên quan.

Độ trễ dọn có thể tính từ `now - purge_after` cho các hàng đã đủ mốc nhưng còn tồn. Phải phân biệt hàng đủ mốc nhưng đang được giữ hợp lệ với hàng có thể dọn mà worker chưa xử lý, để cảnh báo phản ánh đúng nguyên nhân.

Log theo lô nên ghi run ID, phạm vi tenant/shard được phép, phiên bản chính sách, cutoff và số hàng đã commit. Không log token thô, verifier hoặc URL chứa bí mật; hạn chế ghi từng định danh nếu số lượng lớn hoặc không có nhu cầu điều tra.

Nếu backlog tăng, cần xác định do thiếu công suất, truy vấn chậm, khóa kéo dài hay phụ thuộc bị kẹt trước khi tăng tần suất. Tăng số worker khi DB đang quá tải có thể làm tiến độ chậm hơn. Lịch dọn có thể điều chỉnh, còn điều kiện về hiệu lực token, quyền được giữ và phụ thuộc dữ liệu phải tiếp tục được thực thi.
