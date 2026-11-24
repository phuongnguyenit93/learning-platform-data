# Import duplicate handling

## 1. Bản ghi trùng có thể trở thành lỗ hổng nghiệp vụ như thế nào?

Trong chương **Import Security** của module bảo vệ logic nghiệp vụ, xử lý trùng khi import không chỉ là loại bớt các dòng giống nhau. Mục tiêu là bảo đảm việc gửi lại, chia nhỏ hoặc chạy đồng thời một tập dữ liệu không tạo ra hiệu ứng mà nghiệp vụ không cho phép.

Ví dụ, một đối tác gửi tệp ghi nhận điểm thưởng. Dòng có mã sự kiện `reward-204` cộng 500 điểm cho khách hàng. Đối tác gửi lại tệp vì không nhận được kết quả. Nếu hệ thống coi mỗi lần import là một lần cộng mới, cùng sự kiện được áp dụng hai lần. Một người có quyền import cũng có thể cố ý đổi tên tệp, đổi thứ tự dòng hoặc tạo hai job đồng thời để khai thác lỗi này.

Ngược lại, loại trùng quá rộng cũng gây mất dữ liệu. Hai giao dịch hợp lệ cùng số tiền, cùng khách hàng và cùng ngày không nhất thiết là một giao dịch. Cần xác định **định danh đối tượng**, **định danh thao tác** và **chính sách xung đột** trước khi viết thuật toán loại trùng.

Bài học tập trung vào business invariants, quyền theo đối tượng, tính nguyên tử và idempotency trong xử lý trùng. Kiểm tra định dạng tệp là điều kiện đầu vào; nó không giải quyết việc một thao tác hợp lệ về cú pháp bị áp dụng nhiều lần.

## 2. Có nhiều loại trùng khác nhau

| Lớp trùng | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Request | Người dùng nhấn nút hai lần hoặc client retry | Đây có phải cùng yêu cầu tạo job không? |
| Tệp | Cùng nội dung được gửi lại với tên khác | Có được chạy lại tệp đó cho mục đích khác không? |
| Dòng trong một tệp | Hai dòng có cùng mã khách hàng | Bỏ qua, gộp, cập nhật hay từ chối? |
| Đối tượng nghiệp vụ | Khách hàng đã tồn tại trong tenant | Người import được tạo mới hay được cập nhật đối tượng đó? |
| Sự kiện/thao tác | Cùng mã cộng điểm xuất hiện ở hai tệp | Hiệu ứng này đã được commit chưa? |
| Công việc đồng thời | Hai worker xử lý cùng một khóa | Cơ chế nào phân xử và bảo vệ invariant? |

Không nên dùng một cờ `deduplicate=true` để che tất cả các khác biệt trên.

### 2.1. Trùng dữ liệu không đồng nghĩa trùng hiệu ứng

Hai dòng cùng `customerCode` có thể là hai cập nhật liên tiếp cho cùng một khách hàng. Hai dòng có payload khác nhau nhưng cùng `eventId` có thể là xung đột nguy hiểm: một sự kiện đã được dùng để cộng 500 điểm, sau đó được gửi lại thành 5.000 điểm.

Vì vậy, một kết quả “đã tồn tại” chưa đủ. Hệ thống phải phân biệt:

```text
Cùng khóa + cùng ý nghĩa thao tác   → có thể là replay hợp lệ.
Cùng khóa + khác ý nghĩa thao tác  → xung đột, không tự ghi đè.
Khác khóa + payload giống nhau     → có thể là hai thao tác hợp lệ.
```

### 2.2. Trùng tên tệp không phải định danh nghiệp vụ

Tên tệp, đường dẫn upload, số dòng và thời gian gửi không đủ ổn định để nhận diện một thao tác. Người gửi có thể đổi chúng dễ dàng. Số dòng hữu ích để chỉ vị trí lỗi, nhưng không phải định danh bền vững khi một sự kiện được gửi lại trong tệp khác.

## 3. Viết invariant trước khi chọn cách xử lý

Giả sử hệ thống import các lệnh cộng điểm do đối tác phát hành. Một tập invariant có thể là:

| Mã | Invariant |
|---|---|
| D1 | Một khóa đối tượng chỉ duy nhất trong đúng phạm vi tenant và nguồn dữ liệu đã định nghĩa |
| D2 | Một sự kiện nghiệp vụ chỉ tạo tối đa một hiệu ứng đã commit trong phạm vi định danh của nó |
| D3 | Cùng định danh thao tác nhưng payload khác phải thành xung đột, không phải cập nhật ngầm |
| D4 | Replay không được bỏ qua kiểm tra quyền hiện tại hoặc tiết lộ kết quả ngoài phạm vi được phép |
| D5 | Việc trùng khóa không tự cấp quyền cập nhật đối tượng đã tồn tại |
| D6 | Bản ghi chống lặp và thay đổi nghiệp vụ phải commit cùng nhau trong cùng ranh giới nguyên tử |
| D7 | Hai worker đồng thời không được cùng thắng quyền áp dụng một thao tác |
| D8 | Chính sách xử lý dòng trùng phải rõ ràng và không phụ thuộc ngẫu nhiên vào lịch chạy worker |

Ví dụ D2 không có nghĩa “mỗi khách hàng chỉ được cộng điểm một lần”. Phạm vi đúng là một sự kiện được định danh rõ ràng. Khách hàng vẫn có thể nhận điểm từ nhiều sự kiện hợp lệ khác nhau.

Nếu nghiệp vụ là tạo khách hàng thay vì cộng điểm, invariant có thể là “mỗi `externalCustomerId` của một nguồn chỉ ánh xạ tới một khách hàng trong tenant”. Đó là invariant về đối tượng, khác với invariant về số lần áp dụng sự kiện.

## 4. Thiết kế khóa định danh và chuẩn hóa

### 4.1. Khóa phải có phạm vi đúng

Một khóa thường cần nhiều thành phần:

```text
Khóa đối tượng:
  (tenantId, sourceSystem, externalCustomerId)

Khóa thao tác:
  (tenantId, sourceSystem, operationType, sourceEventId)

Khóa idempotency của API:
  (tenantId, subjectId, endpointOrAction, idempotencyKey)
```

`tenantId` và `sourceSystem` phải được ràng buộc từ ngữ cảnh mà server đã xác minh. Không cho người gửi tự đổi nguồn dữ liệu để né bản ghi chống lặp, trừ khi họ có quyền sử dụng nguồn đó và nghiệp vụ thực sự coi đó là một miền định danh khác.

Định danh sự kiện cũng phải ổn định ở phía tạo sự kiện. Nếu người gọi được tự tạo một `sourceEventId` mới cho mọi lần gửi, ledger chỉ chống lặp cùng ID; nó không tự ngăn một người cố tình tạo nhiều sự kiện giả khác ID. Nghiệp vụ vẫn cần nguồn phát đáng tin cậy, đối soát, hạn mức và kiểm tra tính hợp lệ của sự kiện.

### 4.2. Chuẩn hóa phải dựa trên hợp đồng dữ liệu

Ví dụ:

```text
" KH-001 " và "KH-001" có cùng khóa nếu quy tắc cho phép bỏ khoảng trắng ngoài.
"kh-001" và "KH-001" chỉ cùng khóa nếu mã không phân biệt hoa thường.
"00123" và "123" có thể là hai mã khác nhau nếu số 0 đầu có ý nghĩa.
```

Không tự áp dụng chuyển chữ thường, bỏ dấu hoặc đổi kiểu số cho mọi cột. Những biến đổi đó có thể gộp hai đối tượng khác nhau. Với Unicode, chọn quy tắc chuẩn hóa rõ ràng nếu miền dữ liệu cần; tên người hoặc tên doanh nghiệp thường không đủ làm khóa duy nhất.

Quy tắc chuẩn hóa trong parser, bộ kiểm tra trùng trong tệp và ràng buộc cơ sở dữ liệu phải nhất quán. Nếu ứng dụng so sánh phân biệt hoa thường còn database không phân biệt, kết quả import có thể phụ thuộc vào thời điểm chạm ràng buộc.

Khóa bắt buộc không nên để trống. Không trông đợi một unique constraint trên các cột có thể `NULL` sẽ tự thực thi invariant theo đúng ý nghiệp vụ; cần xác định quy tắc giá trị thiếu và hành vi của database đang dùng.

### 4.3. Dấu vân tay payload dùng để phát hiện xung đột

Với mỗi thao tác đã áp dụng, lưu dấu vân tay của payload theo dạng chuẩn:

```text
canonicalPayload = {
  schemaVersion,
  operationType,
  targetCustomerId,
  points,
  effectiveDate,
  businessReason
}
payloadFingerprint = hash(canonicalPayload)
```

Dạng chuẩn phải giữ mọi trường làm thay đổi ý nghĩa nghiệp vụ, kể cả đơn vị tiền, loại thao tác, đối tượng đích hoặc các tùy chọn mapping liên quan. Không chỉ hash các trường “quan trọng nhất” rồi bỏ qua một trường có thể đổi hiệu ứng.

Các thuộc tính vận chuyển như tên tệp hoặc số dòng thường không nên quyết định hai thao tác có cùng ý nghĩa hay không. Nhưng tùy chọn xử lý như `CREATE_ONLY` và `UPSERT` có thể làm thay đổi ý nghĩa, nên cần đưa vào định danh yêu cầu hoặc fingerprint thích hợp.

Hash hỗ trợ đối chiếu, không xác thực nguồn gửi và không thay thế kiểm tra quyền. Với dữ liệu rủi ro cao, có thể cần lưu thêm nội dung chuẩn hoặc bằng chứng đủ để đối soát thay vì chỉ giữ một digest không giải thích được.

## 5. Chọn chính sách xử lý trùng một cách tường minh

| Chính sách | Hành vi | Điều kiện cần kiểm soát |
|---|---|---|
| `REJECT` | Từ chối dòng hoặc nhóm có khóa trùng | Phải chỉ ra phạm vi bị từ chối và kết quả có được commit phần khác không |
| `SKIP_IDENTICAL` | Bỏ qua replay có cùng ý nghĩa | Phải so sánh payload, không chỉ thấy khóa đã tồn tại |
| `CREATE_ONLY` | Chỉ tạo khi đối tượng chưa tồn tại | Không âm thầm chuyển sang cập nhật khi gặp trùng |
| `UPDATE_EXISTING` | Chỉ cập nhật đối tượng đã có | Phải kiểm tra quyền trên đối tượng và các trường được sửa |
| `UPSERT` | Tạo hoặc cập nhật theo khóa | Hai nhánh có thể cần hai quyền và invariant khác nhau |
| `MERGE` | Gộp theo quy tắc nghiệp vụ | Cần quy tắc xác định, có kiểm thử; không mặc định cộng dồn mọi trường |

### 5.1. “Dòng cuối thắng” có thể biến thành thao túng

Tệp gồm hai dòng:

```csv
externalCustomerId,creditLimit
C-17,1000000
C-17,900000000
```

Nếu màn hình preview hiển thị dòng đầu nhưng worker dùng dòng cuối, người duyệt có thể phê duyệt một giá trị khác với giá trị thực sự áp dụng. Chạy song song còn khiến “dòng cuối” phụ thuộc vào thứ tự hoàn thành, không phải thứ tự trong tệp.

Với trường nhạy cảm, lựa chọn dễ giải thích là từ chối cả nhóm khóa trùng có payload khác nhau và yêu cầu người gửi làm rõ. Nếu chấp nhận một quy tắc ưu tiên, cần tính kết quả xác định trước khi duyệt và bind phê duyệt với đúng tập dữ liệu chuẩn hóa đó.

### 5.2. Gộp không có nghĩa là cộng dồn

`balance`, `inventory` hoặc `rewardPoints` có thể biểu diễn giá trị tuyệt đối hoặc một thay đổi. `SET points = 500` và `ADD points = 500` có hành vi replay rất khác nhau.

Không suy ra phép toán từ tên cột. Ghi rõ loại thao tác. Với thay đổi cộng dồn, dùng định danh sự kiện và ledger để ngăn áp dụng lặp. Với cập nhật giá trị tuyệt đối, vẫn cần kiểm tra phiên bản hoặc thứ tự để một bản import cũ không ghi đè trạng thái mới.

## 6. Quyền theo đối tượng phải được kiểm tra ở cả hai nhánh

Một người có quyền tạo khách hàng chưa chắc được cập nhật mọi khách hàng đã tồn tại. Đây là lỗi thường gặp khi thêm `UPSERT` để import thuận tiện hơn:

```text
Nếu chưa tồn tại → kiểm tra CREATE → tạo.
Nếu đã tồn tại  → cập nhật ngay vì coi là xử lý trùng.
```

Nhánh thứ hai đã trở thành đường vòng authorization.

Luồng đúng cần xác minh tenant, quyền với nguồn dữ liệu, quyền thao tác và quyền với đối tượng đích. Với cập nhật, còn phải kiểm tra trường được phép sửa, trạng thái nghiệp vụ và điều kiện phê duyệt.

Khi gặp trùng với một đối tượng người gửi không được phép biết, không trả chi tiết như tên chủ sở hữu, email hoặc ID nội bộ. Có thể trả mã lỗi hạn chế thông tin như `ROW_NOT_APPLICABLE` theo quy ước API. Báo cáo lỗi cũng phải có quyền xem tương ứng.

Replay của thao tác cũ không được làm sống lại quyền đã bị thu hồi. Có thể ghi nhận nội bộ rằng sự kiện đã áp dụng, nhưng việc cho người gọi xem kết quả, tải báo cáo hoặc tiếp tục thao tác phải tuân theo quyền hiện tại.

## 7. Chống trùng ở nhiều tầng

### 7.1. Tầng API: chống tạo job lặp

Client có thể gửi `Idempotency-Key` khi tạo job. Server lưu khóa trong phạm vi tenant, subject và hành động, kèm fingerprint của yêu cầu.

```text
Cùng khóa + cùng yêu cầu → trả về job đã tạo nếu người gọi còn được phép xem.
Cùng khóa + yêu cầu khác → báo xung đột.
Khác khóa              → có thể tạo job khác, nhưng không được bỏ qua chống lặp nghiệp vụ.
```

Định nghĩa fingerprint cần bao gồm upload bất biến hoặc digest tệp, mapping, chế độ xử lý và các tùy chọn ảnh hưởng kết quả. Không dùng riêng tên tệp để nhận diện request.

### 7.2. Tầng tệp: nhận diện gửi lại cùng nội dung

Digest tệp hữu ích để thông báo “tệp này đã được xử lý” hoặc giảm công việc lặp. Nhưng:

- Cùng dữ liệu đổi thứ tự dòng có thể tạo digest khác.
- Đổi encoding hoặc xuống dòng có thể thay đổi byte mà không thay đổi ý nghĩa.
- Cùng byte với mapping khác có thể dẫn đến hiệu ứng khác.
- Cùng nội dung đôi khi được phép import lại cho một kỳ hoặc ngữ cảnh nghiệp vụ mới.

Vì vậy, digest tệp là tín hiệu ở tầng điều phối. Nó không thay thế khóa thao tác và ràng buộc ở tầng dữ liệu.

### 7.3. Tầng staging: gom nhóm và phát hiện xung đột trong tệp

Sau parse và chuẩn hóa, nhóm theo khóa nghiệp vụ. Đối chiếu các dòng có cùng khóa, lưu nguồn gốc dòng và kết quả quyết định.

Nếu tệp được chia chunk, kiểm tra trong từng chunk là chưa đủ. Hai dòng trùng có thể nằm ở hai chunk khác nhau. Có thể dùng bảng staging có chỉ mục theo khóa chuẩn, phân vùng xử lý theo khóa hoặc một bước gom nhóm toàn bộ trước khi apply. Chọn cách phù hợp quy mô nhưng phải bảo vệ cùng invariant.

### 7.4. Tầng database: điểm phân xử đồng thời

Kiểm tra trước bằng `SELECT` chỉ giúp phản hồi sớm; unique constraint hoặc cơ chế tương đương mới phân xử được hai transaction cùng ghi.

SQL minh họa ràng buộc, cần điều chỉnh kiểu và cú pháp cho database thực tế:

```sql
CREATE TABLE imported_operation (
    tenant_id          VARCHAR(64)  NOT NULL,
    source_system      VARCHAR(64)  NOT NULL,
    operation_type     VARCHAR(64)  NOT NULL,
    source_event_id    VARCHAR(128) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    result_reference   VARCHAR(128) NOT NULL,
    applied_at         TIMESTAMP   NOT NULL,
    UNIQUE (tenant_id, source_system, operation_type, source_event_id)
);
```

Unique constraint bảo vệ tính duy nhất của khóa; nó chưa kiểm tra payload, quyền hoặc tính hợp lệ của hiệu ứng. Không dùng `ON CONFLICT DO NOTHING` như một cách biến mọi xung đột thành thành công mà không đối chiếu ý nghĩa.

## 8. Transaction: ledger và hiệu ứng phải đi cùng nhau

### 8.1. Hai thứ tự ghi riêng lẻ đều có lỗi

```text
Cộng điểm commit → ghi ledger lỗi
  → retry không thấy ledger, có thể cộng lần nữa.

Ghi ledger commit → cộng điểm lỗi
  → retry thấy ledger, có thể bỏ qua một hiệu ứng chưa từng xảy ra.
```

Trong một cơ sở dữ liệu giao dịch, đặt thay đổi nghiệp vụ, ledger và kết quả dòng trong cùng transaction của đơn vị apply. Nếu có phát sự kiện ra ngoài, ghi outbox trong transaction đó; việc gửi thực tế do bước sau thực hiện.

Một row lock, unique constraint hoặc thao tác claim phải bảo đảm chỉ một transaction giành quyền áp dụng cùng khóa. Đừng bắt lỗi unique rồi tiếp tục truy vấn ngay trong một transaction đã bị database đánh dấu thất bại; cần dùng cơ chế xung đột phù hợp hoặc rollback và đọc lại bằng transaction hợp lệ.

### 8.2. Mã giả Java minh họa

Ví dụ sau mô tả import sự kiện cộng điểm. Đây là mã giả, không phải implementation hoàn chỉnh. Giả định thay đổi điểm, ledger và outbox ở cùng database; quyền hiện hành được kiểm chứng trong ranh giới nhất quán của quyết định apply.

```java
ApplyResult applyReward(ImportContext context, CanonicalReward row) {
    return transactions.required(() -> {
        access.requireCurrentImportPermission(context);

        OperationKey key = OperationKey.of(
            context.verifiedTenantId(),
            context.verifiedSourceSystem(),
            "ADD_REWARD_POINTS",
            row.sourceEventId());

        // Repository phải phân xử đồng thời, không phải SELECT rồi INSERT tự do.
        // Trạng thái claim chưa hoàn tất không được commit độc lập với hiệu ứng.
        OperationClaim claim = ledger.claimOrLoadWithinTransaction(key);

        Customer customer = customers.lockByTenantAndExternalId(
            context.verifiedTenantId(), row.externalCustomerId());

        access.requireCanApplyReward(context.subject(), customer);

        String fingerprint = fingerprints.forReward(row, customer.id());

        if (claim.alreadyApplied()) {
            if (!claim.fingerprint().equals(fingerprint)) {
                throw new OperationPayloadConflict();
            }
            return ApplyResult.replayed(claim.authorizedResultReference());
        }

        businessRules.requireRewardEventAllowed(context, customer, row);
        customer.addRewardPoints(row.points());
        customers.save(customer);

        RewardEntry entry = rewardEntries.record(key, customer.id(), row.points());
        ledger.completeClaim(claim, fingerprint, entry.id());
        rowResults.markApplied(context.jobId(), row.rowId(), entry.id());
        outbox.appendRewardApplied(key, entry.id());

        return ApplyResult.applied(entry.id());
    });
}
```

`claimOrLoadWithinTransaction` cần có thiết kế cụ thể cho database: khóa bản ghi đã tồn tại, insert có ràng buộc duy nhất hoặc một hình thức phân xử tương đương. Nếu thua tranh chấp, luồng phải đọc kết quả đã commit của bên thắng bằng transaction hợp lệ rồi so sánh payload; không được coi một claim chưa commit là bằng chứng hiệu ứng đã hoàn tất.

Mã giả không tự giải quyết mọi kiểu deadlock. Toàn hệ thống phải dùng thứ tự khóa nhất quán và retry transaction khi phù hợp. Fingerprint cũng cần ràng buộc đúng mapping đối tượng để việc đổi ánh xạ external ID không biến replay thành thao tác lên đối tượng khác.

### 8.3. Với hệ thống bên ngoài

Outbox giúp không mất ý định gửi thông điệp sau commit, nhưng thông điệp có thể được gửi lại. Hệ thống nhận cần idempotency theo định danh sự kiện, hoặc hợp đồng xử lý tương đương.

Không thể suy từ “ledger nội bộ không trùng” rằng một cổng thanh toán, dịch vụ kho hoặc dịch vụ gửi thư chỉ thực hiện đúng một lần. Ranh giới chống lặp phải theo hiệu ứng thực tế và giao thức giữa các bên.

## 9. State machine, retry và dữ liệu đến muộn

Kết quả dòng nên phân biệt rõ:

```text
PENDING → APPLIED
        → REPLAYED_IDENTICAL
        → REJECTED_DUPLICATE_CONFLICT
        → REJECTED_FORBIDDEN
        → REJECTED_BUSINESS_RULE
        → RETRYABLE_FAILURE
```

`REPLAYED_IDENTICAL` nghĩa là hiệu ứng tương ứng đã được xác nhận commit trước đó; không phải “gặp bất kỳ lỗi unique nào”. Không dùng trạng thái này cho một dòng chưa biết hiệu ứng trước đã xảy ra hay chưa.

### 9.1. Retry không tạo định danh mới cho thao tác cũ

Nếu retry dùng `sourceEventId` mới, hệ thống sẽ coi đó là sự kiện khác. Job retry có thể có ID mới để quản lý vận hành, nhưng phải giữ định danh nghiệp vụ gốc và bằng chứng liên hệ với lần trước.

Với kết quả commit chưa rõ do mất kết nối, tra ledger bằng khóa ổn định trước khi quyết định áp dụng lại. Không suy rằng timeout nghĩa là transaction đã rollback.

### 9.2. Bản cập nhật cũ không được thắng chỉ vì đến sau

Giả sử hai bản cập nhật cùng khách hàng có phiên bản nguồn 10 và 11. Phiên bản 11 được import trước, rồi phiên bản 10 đến muộn. Chống trùng theo `eventId` không tự ngăn phiên bản 10 ghi đè dữ liệu mới.

Cần invariant bổ sung về thứ tự hoặc phiên bản đối tượng, chẳng hạn chỉ chấp nhận cập nhật khi phiên bản nguồn lớn hơn phiên bản đã áp dụng và đáp ứng điều kiện đồng thời. Hai payload khác nhau cùng phiên bản phải là xung đột để đối soát, không chọn bản đến sau ngẫu nhiên.

### 9.3. Không sửa dữ liệu nguồn dưới phê duyệt cũ

Nếu preview đã được duyệt, tệp, mapping, chính sách trùng và dạng dữ liệu chuẩn phải được cố định bằng phiên bản hoặc digest phù hợp. Thay đổi một dòng trùng, sửa chế độ từ `CREATE_ONLY` sang `UPSERT` hoặc thay quy tắc ưu tiên có thể thay đổi hiệu ứng; cần duyệt lại khi policy yêu cầu.

## 10. Tấn công logic thường gặp

### 10.1. Gửi lại với tên tệp hoặc thứ tự khác

Kẻ lạm dụng đổi tên tệp hoặc đảo thứ tự dòng để vượt kiểm tra digest tệp. Nếu chỉ chống trùng ở tầng upload, sự kiện có thể được áp dụng lại.

Biện pháp là định danh thao tác ổn định ở tầng nghiệp vụ, không phụ thuộc vị trí trong tệp.

### 10.2. Khai thác nhánh upsert để sửa đối tượng ngoài quyền

Người dùng chỉ có quyền tạo mới nhưng import mã khách hàng đã tồn tại. Server chuyển sang nhánh update và ghi đè hạn mức hoặc chủ sở hữu.

Biện pháp là tách quyền tạo và cập nhật, kiểm tra theo đối tượng và trường, không coi trùng khóa là một ngoại lệ authorization.

### 10.3. Gửi cùng ID nhưng tăng giá trị

Một sự kiện cộng 500 điểm đã áp dụng được gửi lại thành 5.000 điểm với cùng mã. Nếu `UPSERT` trên ledger hoặc bảng nghiệp vụ tự ghi đè, lịch sử và hiệu ứng không còn nhất quán.

Biện pháp là giữ thao tác đã commit bất biến theo định danh, so sánh payload và tạo nghiệp vụ điều chỉnh riêng nếu thật sự cần sửa.

### 10.4. Chạy song song để qua kiểm tra tồn tại

Hai job cùng kiểm tra chưa thấy bản ghi rồi cùng tạo hoặc cộng điểm. Unique constraint bảo vệ đối tượng, còn ledger và transaction bảo vệ hiệu ứng.

Không dùng khóa trong bộ nhớ một process như bảo đảm duy nhất nếu hệ thống có nhiều instance hoặc worker.

### 10.5. Trộn tenant hoặc nguồn dữ liệu

Nếu tenant không nằm trong khóa và điều kiện truy vấn, một bản ghi có thể bị gộp sai với tenant khác. Nếu nguồn dữ liệu do client tùy ý khai báo, họ có thể đổi nguồn để tránh ledger.

Biện pháp là phạm vi định danh rõ ràng, ngữ cảnh đã xác minh và kiểm tra quyền sử dụng nguồn.

## 11. Ma trận kiểm thử

Chuẩn bị hai tenant, nhiều người dùng có quyền tạo/cập nhật khác nhau, hai nguồn dữ liệu và một sự kiện cộng điểm đã được áp dụng. Với bài toán cộng điểm, kiểm tra số dư cuối cùng và số bút toán, không chỉ số dòng import báo thành công.

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Cùng dòng xuất hiện hai lần trong một tệp | Kết quả theo chính sách đã định; không cộng hiệu ứng hai lần |
| Cùng event ở hai chunk khác nhau | Cơ chế chống trùng vẫn có hiệu lực toàn job |
| Cùng event ở hai job khác nhau | Chỉ một hiệu ứng commit; lần sau nhận replay phù hợp |
| Cùng khóa, payload khác | Báo xung đột; không ghi đè hiệu ứng cũ |
| Hai event khác ID, cùng số tiền/điểm | Không loại nhầm nếu cả hai là sự kiện hợp lệ |
| Cùng mã đối tượng ở hai tenant | Không gộp nhầm hoặc tiết lộ dữ liệu tenant khác |
| Giả mạo source system | Từ chối nếu người gửi không được dùng nguồn đó |
| Khác biểu diễn được coi là cùng khóa | Parser, staging và database đưa ra cùng quyết định |
| Mã có số 0 đầu | Không gộp sai nếu hợp đồng coi là hai mã khác nhau |
| Người có quyền create gặp đối tượng đã tồn tại | Không được update nếu thiếu quyền tương ứng |
| Replay sau khi bị thu hồi quyền | Không áp dụng mới, không trả kết quả vượt quyền |
| Cùng Idempotency-Key nhưng khác mapping | Phát hiện xung đột yêu cầu |
| Hai worker cùng sự kiện | Chỉ một bên tạo hiệu ứng; bên còn lại đọc kết quả commit |
| Crash sau thay đổi nghiệp vụ nhưng trước ledger trong transaction | Cả hai rollback hoặc cùng commit; không có trạng thái lệch |
| Mất kết nối sau commit | Retry đối soát được ledger và không tạo hiệu ứng thứ hai |
| Cập nhật nguồn cũ đến sau bản mới | Không ghi đè trái quy tắc phiên bản |
| Outbox gửi lại cùng sự kiện | Hệ thống nhận không tạo hiệu ứng ngoài hợp đồng chống lặp |

Kiểm thử đồng thời nên dùng barrier hoặc điểm dừng điều khiển được để hai transaction cùng tiến vào vùng tranh chấp. Xác nhận ledger, bản ghi nghiệp vụ, kết quả dòng và outbox cùng nhất quán. Một test chỉ gửi tuần tự không phát hiện được lỗi `SELECT` rồi `INSERT`.

Kiểm thử lỗi nên đặt điểm thất bại trước commit, sau commit nhưng trước khi ghi nhận response, và khi gửi thông điệp ra ngoài. Các điểm này có ý nghĩa khác nhau đối với quyết định retry.

## 12. Kết quả import và audit phải giải thích được

Không gộp các kết quả sau thành một con số “thành công”:

```text
appliedCount                 → hiệu ứng mới đã commit
replayedIdenticalCount       → thao tác trước đã commit, không áp dụng lại
duplicateConflictCount       → cùng khóa nhưng ý nghĩa khác
rejectedCount                → từ chối theo quyền hoặc invariant khác
retryableFailureCount        → chưa hoàn tất, có thể thử lại theo quy trình
```

Các nhóm đếm phải có định nghĩa không chồng lấn đối với đơn vị xử lý đã chọn. Khi một nhóm khóa chứa nhiều dòng đầu vào, báo rõ số dòng và số thao tác chuẩn hóa để người dùng không nhầm hai đại lượng.

Audit nên có tenant, subject, nguồn dữ liệu, job ID, dòng hoặc nhóm dòng, khóa thao tác, fingerprint/phiên bản quy tắc, quyết định và tham chiếu kết quả. Không ghi toàn bộ dữ liệu cá nhân chỉ để giải thích trùng. Báo cáo lỗi cũng là dữ liệu cần kiểm soát quyền và thời hạn lưu.

Ledger chống lặp không nên bị xóa tùy tiện cùng tệp upload. Nếu ledger hết hạn trước thời gian một sự kiện có thể được gửi lại, replay cũ có thể tạo hiệu ứng mới. Cần chính sách retention hoặc dấu vết thay thế phù hợp vòng đời nghiệp vụ, khả năng đối soát và yêu cầu bảo vệ dữ liệu.

## 13. Bài tập thiết kế

Một hệ thống import điều chỉnh tồn kho có ba cột `warehouseCode`, `eventId`, `quantityDelta`. Mỗi tệp được chia thành nhiều chunk. Hiện tại server dùng digest tệp để chống gửi lại và thực hiện `stock = stock + quantityDelta` cho mọi dòng hợp lệ.

Hãy thiết kế lại để đáp ứng:

1. Cùng sự kiện không được tăng tồn kho lần thứ hai dù đổi tên tệp, đổi thứ tự hoặc gửi từ job khác.
2. Cùng event ID nhưng thay đổi kho hoặc số lượng phải thành xung đột.
3. Người dùng chỉ được điều chỉnh kho trong phạm vi hiện tại được cấp quyền.
4. Hai worker đồng thời và retry sau timeout không phá invariant.
5. Nếu thay đổi số lượng của một sự kiện đã áp dụng, phải có nghiệp vụ điều chỉnh mới được kiểm soát.

Một hướng giải hợp lý là xác định phạm vi event ID theo tenant và nguồn đã xác minh; lưu fingerprint gồm kho, loại thao tác và số lượng; phân xử bằng ràng buộc duy nhất; commit ledger, thay đổi tồn kho và outbox cùng nhau; đồng thời kiểm tra quyền trên kho tại thời điểm apply.

Thiết kế đạt yêu cầu cần giải thích được: **“Đây là thao tác mới hay một lần gửi lại, và bằng chứng nào bảo đảm cùng thao tác không tạo thêm hiệu ứng?”** Câu trả lời phải tồn tại trong dữ liệu, transaction và policy thực sự được thực thi.
