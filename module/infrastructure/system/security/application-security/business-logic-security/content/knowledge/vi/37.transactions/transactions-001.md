# Business transaction boundary

## 1. Ranh giới giao dịch nghiệp vụ là gì?

**Ranh giới giao dịch nghiệp vụ** xác định phần công việc nào phải được chấp nhận hoặc hủy bỏ như một đơn vị để các quy tắc nghiệp vụ vẫn đúng.

Trong module bảo mật logic nghiệp vụ, câu hỏi quan trọng không chỉ là “đã thêm transaction chưa?” mà là:

> Khi một bước thất bại hoặc có yêu cầu đồng thời, hệ thống có thể để lại trạng thái đã commit nào vi phạm quyền, phê duyệt, số lượng, số dư hoặc quy tắc chỉ thực hiện một lần?

Ví dụ chuyển điểm giữa hai ví: nếu đã trừ điểm ví nguồn nhưng chưa cộng ví đích, việc chỉ báo lỗi cho client không khôi phục được tính đúng của dữ liệu. Nếu chỉ cộng điểm mà không trừ, người gọi có thể nhận thêm lợi ích.

Một ranh giới đúng phải bao phủ những thay đổi cần đi cùng nhau, đồng thời xác định cách bảo vệ dữ liệu quyết định trước thay đổi đồng thời.

Sau bài học, bạn có thể:

- Tách quy trình nghiệp vụ dài khỏi transaction cơ sở dữ liệu ngắn.
- Suy ra ranh giới transaction từ bất biến và các trạng thái thất bại.
- Đặt transaction tại tầng điều phối use case thay vì chia nhỏ theo từng lệnh ghi.
- Phối hợp transaction với quyền theo đối tượng, state machine và idempotency.
- Nhận diện giới hạn của rollback với message, cache và dịch vụ bên ngoài.
- Thiết kế kiểm thử để chứng minh không có trạng thái trung gian sai bị commit.

## 2. Phân biệt ba phạm vi thường bị gọi chung là “transaction”

| Phạm vi | Ví dụ | Đặc điểm |
|---|---|---|
| Quy trình nghiệp vụ | Tạo yêu cầu, chờ phê duyệt, thực thi, đối soát | Có thể kéo dài qua nhiều request và nhiều ngày |
| Bước nghiệp vụ nguyên tử | Thực thi một yêu cầu chuyển điểm đã được duyệt | Những thay đổi cục bộ bắt buộc phải thành công hoặc thất bại cùng nhau |
| Transaction cơ sở dữ liệu | BEGIN đến COMMIT hoặc ROLLBACK trên tài nguyên tham gia | Cơ chế kỹ thuật để bảo vệ một phần hoặc toàn bộ bước nguyên tử |

Một quy trình có thể gồm nhiều transaction:

~~~text
Transaction A: tạo yêu cầu chuyển điểm ở trạng thái DRAFT.
Transaction B: phê duyệt đúng nội dung và phiên bản.
Transaction C: thực thi chuyển điểm.
Transaction D: consumer ghi nhận thông báo đã xử lý.
~~~

Không giữ transaction A mở trong lúc chờ người quản lý phê duyệt. Thời gian giữa các bước phải được biểu diễn bằng trạng thái bền vững, phiên bản và dữ liệu phê duyệt.

Cũng không mặc định một HTTP request là một transaction. Một request có thể chỉ đọc dữ liệu, tiếp nhận một công việc bất đồng bộ hoặc điều phối nhiều bước có ranh giới khác nhau. Ngược lại, nhiều repository call có thể phải nằm trong cùng một transaction.

Theo [tài liệu Transactions của PostgreSQL](https://www.postgresql.org/docs/current/tutorial-transactions.html), transaction gom các bước thành một thao tác toàn bộ hoặc không bước nào; BEGIN, COMMIT và ROLLBACK điều khiển khối đó. Đặc tính này chỉ có ích khi những bước cần đi cùng nhau thực sự tham gia đúng transaction.

## 3. Bắt đầu từ bất biến: chuyển 30 điểm giữa hai ví

### 3.1. Dữ liệu và hợp đồng

Giả sử tất cả dữ liệu cốt lõi nằm trong cùng một database có hỗ trợ transaction:

| Dữ liệu | Trước khi thực thi |
|---|---|
| Tenant | T-1 |
| Yêu cầu chuyển | TI-42 |
| Trạng thái yêu cầu | APPROVED |
| Phiên bản được duyệt | 7 |
| Ví nguồn A | 100 điểm |
| Ví đích B | 20 điểm |
| Lượng điểm được duyệt | 30 điểm |
| Người thực thi | Có quyền trên ví nguồn và yêu cầu TI-42 |

Để ví dụ đơn giản, hệ thống không thu phí, không có chuyển đổi đơn vị và không có giao dịch khác làm thay đổi hai ví trong phần minh họa kết quả.

Sau khi thực thi:

~~~text
A = 70
B = 50
A + B = 120
~~~

Các bất biến cần giữ:

1. Lượng chuyển là số nguyên dương, lấy từ nội dung được duyệt.
2. Hai ví thuộc phạm vi tenant và loại điểm hợp lệ.
3. Ví nguồn không âm.
4. Một yêu cầu được duyệt chỉ tạo một operation chuyển điểm thành công.
5. Hai phía của một operation được ghi nhận nhất quán.
6. Trạng thái COMPLETED chỉ xuất hiện cùng dữ liệu chuyển điểm đã hoàn tất.
7. Một lần gửi lại không trừ hoặc cộng điểm thêm lần nữa.
8. Người gọi không thể dùng ID của ví hoặc yêu cầu khác để vượt quyền.

Đối với một operation, có thể kiểm tra:

~~~text
delta_nguon = -30
delta_dich  = +30
delta_nguon + delta_dich = 0
~~~

Công thức bảo toàn chỉ áp dụng trong phạm vi đã nêu. Với hệ thống có phí hoặc có thao tác phát hành điểm, cần đưa tài khoản phí hoặc nguồn phát hành vào mô hình; không dùng công thức giản lược để kết luận dữ liệu sai.

### 3.2. Những thay đổi nào phải commit cùng nhau?

Trong thiết kế minh họa, một lần thực thi thành công bao gồm:

- Gắn command với một operation ổn định để nhận diện retry.
- Trừ điểm nguồn.
- Cộng điểm đích.
- Ghi hai vế lịch sử chuyển điểm.
- Chuyển TI-42 từ APPROVED sang COMPLETED.
- Lưu kết quả command.
- Ghi outbox event nếu việc phát thông báo là nghĩa vụ bền vững của operation.

Nếu ghi lịch sử chuyển điểm hoặc hoàn thiện trạng thái thất bại, không được giữ lại phần trừ/cộng đã làm.

Một email có thể được gửi sau. Nhưng nếu hệ thống yêu cầu chắc chắn có công việc gửi email cho mọi operation thành công, ý định gửi email phải được lưu bền vững cùng transaction; việc giao email có thể diễn ra ở transaction khác.

## 4. Ranh giới quá nhỏ tạo lỗ hổng như thế nào?

### 4.1. Mỗi repository call tự commit

~~~java
// Minh họa cách chia ranh giới sai.
walletRepository.debitAndCommit(sourceId, amount);
walletRepository.creditAndCommit(targetId, amount);
transferRepository.markCompletedAndCommit(intentId);
~~~

Nếu bước thứ hai thất bại, điểm ví nguồn đã bị trừ và không còn nằm trong transaction có thể rollback.

Nếu cố “sửa” bằng một lệnh cộng lại ngoài transaction, lệnh bù cũng có thể thất bại hoặc bị chạy nhiều lần. Đó đã trở thành một quy trình phục hồi cần thiết kế riêng, không còn là rollback của transaction ban đầu.

### 4.2. Trạng thái hoàn tất được ghi độc lập

~~~text
Transaction A: đánh dấu COMPLETED.
Transaction B: trừ và cộng điểm.
~~~

Nếu transaction B thất bại, lịch sử nói đã hoàn tất trong khi điểm chưa chuyển.

Đảo thứ tự cũng không đủ:

~~~text
Transaction A: chuyển điểm.
Transaction B: đánh dấu COMPLETED.
~~~

Nếu B thất bại, yêu cầu vẫn trông như chưa thực thi. Một retry có thể chuyển điểm lần nữa nếu chỉ kiểm tra trạng thái đó.

### 4.3. Dấu chống trùng nằm ngoài transaction nghiệp vụ

Hai kiểu lỗi đối xứng:

~~~text
Ghi "đã xử lý" trước -> chết trước khi chuyển điểm -> mất thao tác hợp lệ.

Chuyển điểm trước -> chết trước khi ghi "đã xử lý" -> retry có thể chuyển thêm.
~~~

Dữ liệu chống trùng và kết quả nghiệp vụ phải được phối hợp bằng một ranh giới nguyên tử phù hợp. Một dấu trong cache không thay thế được mối liên hệ bền vững giữa command và operation.

## 5. Ranh giới quá lớn cũng gây vấn đề

Một transaction ôm toàn bộ request có thể giữ connection và khóa trong lúc:

- Chờ phản hồi HTTP từ một hệ thống khác.
- Upload tệp hoặc chạy xử lý CPU dài.
- Chờ người dùng xác nhận.
- Gửi email.
- Ngủ để đợi một công việc bất đồng bộ.

Hệ quả có thể là giữ khóa lâu, cạn pool, timeout và làm các thao tác trên cùng tài nguyên khó tiến triển. Người gọi có thể làm tình trạng này xấu hơn bằng nhiều yêu cầu hợp lệ nhưng xử lý chậm.

Nguyên tắc thực hành là giữ transaction **đủ rộng để bảo vệ bất biến, đủ ngắn để không chờ công việc không cần nguyên tử**.

Không đạt điều đó bằng cách đưa các bước bắt buộc ra ngoài. Hãy chuyển việc có thể trì hoãn thành công việc bền vững hoặc tách quy trình thành các bước có trạng thái rõ ràng.

Một cách phân chia:

| Trước transaction | Trong transaction | Sau khi commit |
|---|---|---|
| Xác thực thông tin đầu vào | Đọc dữ liệu nghiệp vụ có thẩm quyền | Trả kết quả đã được commit |
| Kiểm tra cấu trúc request | Kiểm tra điều kiện động và quyền theo chính sách | Worker xử lý công việc từ outbox |
| Giới hạn kích thước, định dạng | Bảo vệ tranh chấp, cập nhật dữ liệu liên quan | Truy vấn tiến độ hoặc đối soát |
| Chuẩn hóa command | Lưu kết quả, dấu chống trùng và ý định phát event | Thực hiện phần tích hợp theo giao thức riêng |

Một kiểm tra cấu trúc có thể làm sớm. Một kiểm tra “ví còn đủ điểm”, “yêu cầu vẫn được duyệt” hoặc “người gọi còn sở hữu ví” cần gắn với dữ liệu và cơ chế điều phối tại điểm quyết định.

## 6. Vẽ ranh giới trước khi viết annotation

Một bước thực thi TI-42 có thể được mô hình hóa như sau:

~~~mermaid
flowchart TD
    A[Nhận command đã xác thực] --> B[Chuẩn hóa và kiểm tra cấu trúc]
    B --> C
    subgraph TX[Transaction thực thi chuyển điểm]
        C[Chiếm hoặc tìm command key] --> D{Đã có kết quả?}
        D -->|Có| E[Kiểm tra nội dung và quyền đọc]
        D -->|Chưa| F[Đọc và khóa yêu cầu được duyệt]
        F --> G[Khóa ví và kiểm tra quyền, số điểm, đơn vị]
        G --> H[Trừ nguồn và cộng đích]
        H --> I[Ghi operation và hai vế lịch sử]
        I --> J[Hoàn tất yêu cầu, receipt và outbox]
    end
    E --> K[Commit hoặc kết thúc nhánh đọc]
    J --> K
    K --> L[Trả kết quả]
    K --> M[Worker xử lý outbox sau commit]
~~~

Các thao tác ghi trong khối phải cùng tham gia một transaction trên tài nguyên dự kiến. Nếu lỗi xảy ra trước commit, không có phần chuyển điểm nào được giữ lại.

Điểm cần ghi rõ trong thiết kế:

~~~text
Người sở hữu boundary: use case ExecuteApprovedPointTransfer.

Điều kiện đầu vào:
- Caller đã được xác thực.
- Command có cấu trúc hợp lệ.

Dữ liệu cần bảo vệ:
- Command receipt.
- Yêu cầu và snapshot được phê duyệt.
- Hai ví.
- Operation, lịch sử và outbox.

Điểm có hiệu lực:
- Commit thành công của transaction sở hữu boundary.

Kết quả thất bại:
- Không thay đổi số điểm, trạng thái thực thi hay dữ liệu thành công.

Công việc ngoài boundary:
- Giao thông báo và các phần tích hợp độc lập.
~~~

Nếu use case tham gia một transaction bên ngoài đang tồn tại, điểm commit nằm ở boundary bên ngoài đó. Việc một method bên trong đã return chưa có nghĩa toàn bộ công việc đã commit.

## 7. Atomicity không tự ngăn mọi thao tác đồng thời

### 7.1. Có transaction nhưng vẫn quyết định theo dữ liệu cũ

Giả sử ví A có 50 điểm. Hai transaction mỗi transaction muốn chuyển 40 điểm:

~~~text
T1 đọc A = 50.
T2 đọc A = 50.
T1 kết luận đủ điểm.
T2 kết luận đủ điểm.
T1 trừ 40.
T2 cũng trừ 40 dựa trên quyết định cũ.
~~~

Gom debit, credit và lịch sử của từng yêu cầu vào transaction mới chỉ giải quyết việc các bước của một yêu cầu đi cùng nhau. Còn phải bảo vệ quy tắc A không âm trước hai yêu cầu.

Một phép cập nhật có điều kiện có thể bảo vệ việc tiêu thụ trên dòng ví nguồn:

~~~sql
UPDATE point_wallet
SET balance = balance - :amount
WHERE tenant_id = :tenant_id
  AND id = :source_wallet_id
  AND owner_id = :actor_id
  AND unit = :unit
  AND balance >= :amount
  AND :amount > 0;
~~~

Chỉ khi số dòng cập nhật bằng 1 mới tiếp tục. Nếu bằng 0, không được cộng điểm đích rồi coi như đã chuyển thành công.

Ở PostgreSQL với Read Committed, UPDATE tranh chấp trên một dòng có thể chờ transaction trước, rồi đánh giá lại điều kiện WHERE trên phiên bản đã được cập nhật. Tài liệu cũng nêu rằng hai SELECT trong cùng transaction có thể thấy các snapshot khác nhau. Xem [Transaction Isolation của PostgreSQL](https://www.postgresql.org/docs/current/transaction-iso.html).

Không suy rộng một điều kiện trên dòng ví thành bảo đảm cho mọi dữ liệu liên quan. Ví dụ nó không tự bảo vệ tổng hạn mức nằm ở nhiều dòng khác.

### 7.2. Chọn cơ chế theo bất biến

| Cơ chế | Cách dùng điển hình | Phần cần chú ý |
|---|---|---|
| Conditional UPDATE | Trừ điểm nếu còn đủ; chuyển trạng thái nếu phiên bản khớp | Phải kiểm tra số dòng cập nhật |
| Khóa bi quan | Đọc và quyết định dựa trên các dòng đã khóa | Đủ phạm vi khóa, thứ tự khóa và thời gian giữ khóa |
| Optimistic version | Phát hiện một đối tượng đã thay đổi từ lần đọc trước | Mọi đường sửa liên quan phải tham gia quy tắc version |
| Unique hoặc check constraint | Một operation cho một intent; balance không âm | Cần đúng phạm vi tenant và đúng quy tắc nghiệp vụ |
| Serializable | Bảo vệ lịch thực thi trước một số bất biến phức tạp | Có thể cần retry toàn transaction theo hợp đồng của database |
| Dòng hạn mức/reservation chung | Nhiều thao tác cùng tiêu thụ một ngân sách | Tất cả đường tiêu thụ và giải phóng phải phối hợp |

Một ví dụ về bất biến tổng hợp: hạn mức của một nhóm là 50 điểm; hai transaction cùng đọc tổng đã giữ bằng 0 rồi mỗi transaction chèn một reservation 40 điểm vào hai dòng khác nhau. Hai dòng riêng đều hợp lệ nhưng tổng là 80.

Khóa một dòng reservation bất kỳ hoặc dùng version chỉ trên từng reservation không giải quyết được tổng hạn mức. Cần một cơ chế chung cho phạm vi nhóm hoặc isolation thích hợp, cùng logic xử lý xung đột.

### 7.3. Khóa hai ví theo thứ tự thống nhất

Nếu T1 khóa A rồi chờ B, còn T2 khóa B rồi chờ A, có thể xảy ra deadlock.

Với các luồng dùng khóa ví, quy ước có thể là lấy danh sách ID ví theo thứ tự tăng dần rồi khóa lần lượt từng ví theo thứ tự đó. Áp dụng nhất quán cho mọi luồng chạm các tài nguyên liên quan, không chỉ một method.

Thứ tự khóa tốt làm giảm các vòng chờ có thể tránh được, nhưng vẫn cần timeout và xử lý deadlock. Không hứa rằng sắp xếp hai ID sẽ loại bỏ mọi deadlock trong một hệ thống còn nhiều loại khóa khác.

## 8. Ví dụ Java/Spring đặt boundary tại use case

Đoạn mã dưới đây là **mã khung** để thể hiện trách nhiệm và ranh giới. Các repository, kiểu dữ liệu và authorization service là hợp đồng minh họa, không phải một dự án có thể chạy độc lập.

Giả định:

- Tất cả repository cốt lõi dùng cùng database và pointsTransactionManager.
- Lời gọi từ controller đi qua Spring bean proxy.
- caller được tạo từ ngữ cảnh xác thực đáng tin cậy.
- Yêu cầu được duyệt lưu nguồn, đích, lượng điểm, đơn vị và phiên bản.
- Quyền ví nguồn trong ví dụ dựa vào owner_id trên chính dòng ví được khóa.
- Các exception từ chối nghiệp vụ trong ví dụ làm rollback phần thực thi.

~~~java
@Service
public class PointTransferService {
    private final ReceiptRepository receipts;
    private final TransferIntentRepository intents;
    private final WalletRepository wallets;
    private final TransferRepository transfers;
    private final LedgerRepository ledger;
    private final OutboxRepository outbox;
    private final AuthorizationService authorization;

    // Constructor injection được lược bỏ để tập trung vào boundary.

    @Transactional(
        transactionManager = "pointsTransactionManager",
        rollbackFor = Exception.class
    )
    public TransferReceipt execute(
        AuthenticatedCaller caller,
        ExecuteTransferCommand command
    ) {
        command.validateShape();

        CommandScope scope = CommandScope.of(
            caller.tenantId(),
            caller.principalId(),
            "EXECUTE_POINT_TRANSFER"
        );

        CommandFingerprint fingerprint =
            CommandFingerprint.from(scope, command);

        // Phải là claim nguyên tử có ràng buộc duy nhất,
        // không phải exists() rồi insert() không được bảo vệ.
        ReceiptClaim claim = receipts.claimOrLoad(
            scope, command.idempotencyKey(), fingerprint
        );

        if (claim.isExisting()) {
            authorization.requireMayRead(
                caller, claim.operationReference()
            );
            claim.requireSameFingerprint(fingerprint);
            return claim.completedReceipt();
        }

        TransferIntent intent = intents.findForUpdate(
            caller.tenantId(), command.intentId()
        );

        intent.requireApprovedVersion(command.expectedVersion());
        intent.requirePositiveAmount();
        intent.requireDistinctWallets();

        WalletPair pair = wallets.lockPairInIdOrder(
            caller.tenantId(),
            intent.sourceWalletId(),
            intent.targetWalletId()
        );

        authorization.requireMayExecute(caller, intent, pair);
        pair.requireSameUnit(intent.unit());

        UUID operationId = UUID.randomUUID();

        transfers.insertOperation(
            operationId, caller.tenantId(), intent
        );

        int debited = wallets.debitIfEnough(
            caller.tenantId(),
            intent.sourceWalletId(),
            caller.principalId(),
            intent.amount(),
            intent.unit()
        );

        if (debited != 1) {
            throw new TransferRejectedException(
                "Ví nguồn không đáp ứng điều kiện chuyển"
            );
        }

        int credited = wallets.credit(
            caller.tenantId(),
            intent.targetWalletId(),
            intent.amount(),
            intent.unit()
        );

        if (credited != 1) {
            throw new TransferRejectedException(
                "Ví đích không đáp ứng điều kiện nhận"
            );
        }

        ledger.appendPair(operationId, caller.tenantId(), intent);

        int completed = intents.completeIfApprovedVersion(
            caller.tenantId(),
            intent.id(),
            command.expectedVersion(),
            operationId
        );

        if (completed != 1) {
            throw new TransferConflictException(
                "Yêu cầu không còn ở phiên bản được phép thực thi"
            );
        }

        outbox.appendTransferCompleted(
            operationId, caller.tenantId(), intent
        );

        return receipts.complete(claim, operationId);
    }
}
~~~

Các hợp đồng repository cần được triển khai thật:

- claimOrLoad phân xử key bằng thao tác nguyên tử và unique constraint. Nếu có transaction khác đang claim, phải chờ có giới hạn hoặc trả xung đột phù hợp, không trả một receipt chưa hoàn thiện như thành công.
- findForUpdate đọc đúng tenant và giữ khóa đến cuối transaction.
- lockPairInIdOrder khóa hai ví theo thứ tự thống nhất, xác minh cả hai tồn tại trong tenant và ánh xạ đúng vai trò nguồn/đích.
- Các phép debit, credit và complete trả số dòng thực sự thay đổi.
- insertOperation có unique constraint theo tenant và intent.
- appendPair ghi cả hai vế trong transaction hiện tại.
- complete lưu fingerprint, liên kết operation và kết quả để lần retry nhận lại cùng operation.
- Không repository nào tự mở connection ngoài cơ chế tham gia transaction hoặc tự commit riêng.

Chuyển trạng thái có thể dùng:

~~~sql
UPDATE transfer_intent
SET state = 'COMPLETED',
    operation_id = :operation_id,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :intent_id
  AND state = 'APPROVED'
  AND version = :expected_version
  AND approved_version = :expected_version;
~~~

Trong mô hình này, việc sửa nội dung liên quan phải tăng version và làm mất hiệu lực phê duyệt hoặc yêu cầu duyệt lại. Câu UPDATE không thể tự bảo vệ nếu các đường sửa khác âm thầm thay số điểm mà không tham gia quy tắc phiên bản.

Giá trị được trả từ thân method chỉ tới controller sau khi transaction interceptor hoàn tất công việc của nó, nếu đây là transaction ngoài cùng. Commit vẫn có thể thất bại sau câu return trong thân method. Không chuyển một lỗi commit thành phản hồi thành công.

## 9. Quyền và phê duyệt nằm ở đâu trong boundary?

### 9.1. Kiểm tra sớm để từ chối nhanh, kiểm tra có thẩm quyền để quyết định

Xác thực token, kiểm tra định dạng và một số giới hạn request có thể diễn ra trước khi mở transaction.

Nhưng những điều kiện thay đổi theo dữ liệu cần được xét tại điểm quyết định:

- Người gọi có quyền trên đúng ví và đúng yêu cầu không?
- TI-42 còn APPROVED không?
- Nội dung hiện tại có đúng snapshot được duyệt không?
- Ví còn đủ điểm không?
- Intent đã có operation thành công chưa?

Việc các kiểm tra này nằm “bên trong transaction” chưa đủ nếu chúng đọc dữ liệu có thể bị đổi mà không có cơ chế phối hợp.

### 9.2. Dữ liệu quyền ở dòng khác hoặc hệ thống khác

Ví dụ owner_id nằm trên dòng ví đã khóa, nên một thao tác đổi owner có tuân thủ cùng cơ chế dữ liệu phải tranh chấp với khóa đó.

Nếu quyền nằm ở bảng ACL, cache hoặc một dịch vụ chính sách bên ngoài, khóa ví không tự khóa quyền. Cần xác định chính sách có hiệu lực tại thời điểm nào và cơ chế bảo vệ phù hợp: khóa dòng quyền liên quan, kiểm tra revision có phối hợp, hoặc dùng một ủy quyền bất biến có phạm vi và thời hạn rõ ràng.

Hợp đồng phải nói rõ điều gì xảy ra nếu thu hồi quyền đồng thời với thực thi. Test phải tạo đúng thứ tự có hiệu lực đã chọn, thay vì cho rằng một lần đọc quyền cũ luôn còn đúng đến commit.

### 9.3. Không để client tự dựng dữ liệu được phê duyệt

Client có thể gửi intent ID và expectedVersion, nhưng nguồn, đích, lượng điểm và đơn vị có thẩm quyền phải gắn với nội dung được duyệt do server quản lý.

Một transaction bao trùm nhiều câu SQL vẫn có thể thực hiện toàn bộ một lệnh trái quyền hoặc sai số điểm nếu dữ liệu đầu vào được tin sai.

## 10. Những chi tiết Spring có thể làm boundary thực tế khác thiết kế

### 10.1. Annotation phải được hạ tầng transaction áp dụng

Trong proxy mode, lời gọi phải đi qua proxy. Một method trong cùng đối tượng gọi trực tiếp method khác của chính nó không kích hoạt transaction interceptor cho lời gọi bên trong chỉ vì method đó có annotation. Xem [Using @Transactional của Spring](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

Vì vậy, việc nhìn thấy @Transactional trong source chưa chứng minh boundary hoạt động. Kiểm thử rollback qua đường gọi thực tế mới phát hiện được trường hợp annotation bị bỏ qua.

Cũng cần chọn đúng transaction manager. Hai repository trỏ tới hai datasource độc lập không tự tham gia cùng một local transaction vì cùng được gọi từ một service.

### 10.2. Rollback phụ thuộc cách lỗi đi qua boundary

Với cấu hình mặc định thông thường, Spring rollback khi RuntimeException hoặc Error thoát ra, còn checked exception cần quy tắc rollback tương ứng. Ứng dụng có thể cấu hình khác; cần kiểm tra cấu hình thực tế. Xem [Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

Mã khung dùng rollbackFor = Exception.class để thể hiện rằng checked exception cũng làm hủy bước thực thi theo hợp đồng đã chọn.

Một lỗi thường gặp là tự nuốt exception:

~~~java
@Transactional
public Result transfer(Command command) {
    debit(command);

    try {
        verifyBusinessCondition(command);
        credit(command);
    } catch (BusinessRuleException e) {
        return Result.rejected();
    }

    return Result.completed();
}
~~~

Nếu exception bị bắt trước khi interceptor thấy nó, và chưa có cơ chế nào đánh dấu rollback-only, transaction có thể commit phần debit. Trả một đối tượng rejected không tự yêu cầu rollback.

Nếu một lời gọi bên trong đã đánh dấu rollback-only hoặc tài nguyên đã rơi vào trạng thái lỗi, việc bắt exception cũng không biến transaction thành có thể commit an toàn. Cần bảo toàn nguyên nhân và xử lý đúng boundary.

### 10.3. Propagation có thể giữ nguyên hoặc tách ranh giới

| Chế độ | Ý nghĩa cơ bản |
|---|---|
| REQUIRED | Tham gia transaction hiện có hoặc mở transaction nếu chưa có |
| REQUIRES_NEW | Dùng transaction vật lý độc lập |
| NESTED | Dùng savepoint khi transaction manager và tài nguyên hỗ trợ |

Đây là các khác biệt được giải thích trong [Transaction Propagation của Spring](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

Nếu debit chạy trong REQUIRES_NEW rồi transaction ngoài thất bại, phần debit đã commit riêng không bị transaction ngoài rollback. Không dùng cách tách đó cho hai nửa bắt buộc nguyên tử.

Một bản ghi audit về lần thử bị từ chối có thể được thiết kế để tồn tại độc lập. Tuy nhiên, nó phải mô tả đúng “đã thử” hoặc “bị từ chối”, không phải “chuyển điểm thành công”.

Savepoint không phải giấy phép bỏ qua bước bắt buộc. Không được rollback riêng credit rồi commit debit nếu hợp đồng yêu cầu hai phía đi cùng nhau.

### 10.4. Flush chưa phải commit

Trong ORM, flush có thể gửi SQL xuống database trước khi transaction kết thúc. Dữ liệu vẫn có thể bị rollback sau đó.

Một lệnh save trả về hoặc entity có ID chưa chứng minh rằng commit đã thành công. Constraint hoặc lỗi kết nối cũng có thể chỉ xuất hiện ở mốc muộn hơn.

Không phát thông báo “đã hoàn tất” ra ngoài chỉ dựa vào việc một repository call chưa ném lỗi.

### 10.5. Tác vụ ở thread khác cần boundary riêng

Với mô hình transaction imperative gắn với thread, tạo tác vụ trong executor không tự làm tác vụ đó tham gia transaction của thread gọi.

Nếu tách debit và credit sang hai worker rồi trả kết quả sớm, không còn cơ sở để coi chúng là cùng một local transaction.

Nếu cần xử lý bất đồng bộ, hãy tiếp nhận một operation bền vững trước, rồi để worker thực hiện bước nghiệp vụ trong boundary rõ ràng của worker. Tác vụ bất đồng bộ cần mang theo danh tính operation và ngữ cảnh được phép, không dựa vào ngữ cảnh ngầm của request cũ.

## 11. Transaction và idempotency giải quyết hai câu hỏi khác nhau

Transaction trả lời:

> Các bước của lần thực thi này có cùng được giữ lại hay cùng bị hủy không?

Idempotency trả lời:

> Khi cùng ý định được gửi hoặc xử lý lại, có bị áp dụng thêm tác dụng không?

Một transaction có thể chuyển điểm hoàn toàn nhất quán nhưng chạy lại lần thứ hai vì mất phản hồi. Ngược lại, một idempotency key được nhớ trong cache không làm hai phép cập nhật đã commit riêng trở nên nguyên tử.

Trong ví dụ:

~~~text
Unique theo (tenant, caller scope, command type, key)
    -> một danh tính command trong phạm vi API.

Unique theo (tenant, intent)
    -> một operation cho yêu cầu được duyệt.

Transaction thực thi
    -> receipt, operation, hai ví, lịch sử, trạng thái và outbox đi cùng nhau.
~~~

Cùng key nhưng fingerprint khác phải được xử lý là xung đột theo hợp đồng, không thay nội dung command cũ.

Key mới cho TI-42 đã hoàn tất không được tạo operation thứ hai. Ràng buộc theo intent bảo vệ trường hợp người gọi cố tránh lớp chống trùng API bằng cách đổi key.

Khi có deadlock hoặc lỗi đồng thời được phép retry, retry cả đơn vị công việc trong transaction mới và giữ danh tính command ổn định. Không chỉ chạy lại câu credit hoặc một đoạn tùy ý của thuật toán.

Nếu mất kết nối lúc commit, client có thể chưa biết commit đã xảy ra hay chưa. Đó là tình trạng kết quả chưa rõ, không tự chứng minh rollback. Cần tra cứu hoặc gửi lại cùng command qua cơ chế chống trùng và phân xử tranh chấp, thay vì tạo một ý định mới.

## 12. Khi bước nghiệp vụ vượt ra ngoài một database

### 12.1. Local transaction không bao trùm tùy ý mọi tài nguyên

Ví dụ sau không nguyên tử chỉ nhờ annotation:

~~~java
@Transactional
public void completeOrder(Order order) {
    repository.markCompleted(order);
    remotePaymentClient.capture(order.paymentReference());
    emailClient.sendConfirmation(order);
}
~~~

Nếu dịch vụ thanh toán đã thu tiền nhưng transaction database rollback, database không tự thu hồi lời gọi bên ngoài.

Nếu database commit rồi việc gửi email thất bại, không thể rollback commit đã hoàn tất bằng một exception ở bước gửi email sau đó.

Tương tự, một local transaction không tự rollback được thay đổi đã gửi tới cache hoặc message broker độc lập. Muốn nhiều tài nguyên tham gia một giao thức transaction chung phải có hỗ trợ và cấu hình thực tế; không suy ra điều đó từ annotation.

### 12.2. Outbox tạo ranh giới giữa quyết định và giao việc

Một thiết kế thường dùng:

~~~text
Transaction nghiệp vụ:
  - Cập nhật dữ liệu có thẩm quyền.
  - Lưu operation và trạng thái.
  - Ghi outbox event.
  - Commit.

Worker:
  - Đọc công việc đã commit.
  - Gửi tới nơi nhận.
  - Retry hoặc đối soát theo operation ID.
  - Ghi nhận tiến độ theo boundary riêng.
~~~

Nếu transaction nghiệp vụ rollback, không có event thành công tương ứng để worker gửi.

Nếu worker chết sau khi gửi nhưng trước khi ghi nhận đã gửi, message có thể được giao lại. Consumer cần chống áp dụng trùng tác dụng theo operation hoặc danh tính nghiệp vụ thích hợp.

Callback sau commit có thể giúp kích hoạt công việc nhanh, nhưng không tự bảo đảm giao việc bền vững: tiến trình vẫn có thể chết giữa commit và callback/gửi. Khi nghĩa vụ không được phép mất, phải có nguồn công việc bền vững để phục hồi.

### 12.3. Quy trình nhiều bước cần trạng thái và bù trừ rõ ràng

Nếu việc hoàn tất đơn hàng cần thu tiền và giữ tài nguyên ở các hệ thống độc lập, quy trình có thể có:

~~~text
PENDING -> RESOURCE_RESERVED -> PAYMENT_PENDING -> COMPLETED
                                  |
                                  v
                         RECONCILIATION_REQUIRED
~~~

Mỗi bước có boundary riêng. Khi thất bại, một bước bù trừ như giải phóng reservation hoặc hoàn tiền là thao tác nghiệp vụ mới, có thể cần retry và có thể chưa hoàn tất ngay.

Bù trừ không đồng nghĩa thời gian quay ngược về trước transaction. Lịch sử “đã thu rồi hoàn” khác “chưa thu”, và hệ thống phải biểu đạt trung thực điều đó.

Không đánh dấu COMPLETED sớm khi mới chỉ ghi ý định gọi nhà cung cấp. Cần phân biệt trạng thái đã tiếp nhận, đang xử lý và đã có kết quả cuối.

## 13. Quy trình xác định boundary cho một use case

Có thể áp dụng sáu bước:

1. **Viết bất biến.** Ví dụ không âm, đúng nội dung được duyệt, một operation cho một intent, hai vế lịch sử khớp nhau.
2. **Liệt kê dữ liệu quyết định và dữ liệu thay đổi.** Bao gồm quyền, phiên bản, hạn mức và dấu chống trùng.
3. **Đặt lỗi giữa mọi cặp bước.** Hỏi điều gì còn lại nếu tiến trình chết hoặc một câu ghi thất bại.
4. **Chọn nhóm bắt buộc nguyên tử.** Đưa chúng vào cùng transaction nếu tài nguyên cho phép.
5. **Bổ sung cơ chế điều phối đồng thời.** Khóa, điều kiện cập nhật, version và constraint phải tương ứng với từng bất biến.
6. **Tách phần ngoài phạm vi thành workflow.** Có operation ID, trạng thái, nguồn công việc bền vững và cách phục hồi.

Sau đó xác minh boundary thực tế ở runtime: đường gọi qua proxy, transaction manager, datasource, propagation và chính sách rollback.

Không dùng kích thước class, số repository hoặc ranh giới HTTP làm tiêu chí duy nhất. Một use case nhỏ có thể cần nhiều bảng trong cùng transaction; một quy trình lớn có thể cần nhiều transaction ngắn.

## 14. Kiểm thử ranh giới giao dịch

### 14.1. Fault injection tại từng mốc

Với dữ liệu ban đầu A = 100, B = 20, TI-42 = APPROVED, hãy chủ động gây lỗi ở các mốc sau:

| Mốc gây lỗi trước commit | Kết quả sau rollback cần kiểm tra |
|---|---|
| Sau khi claim command key | Không có receipt thành công hoặc operation bị bỏ dở đã commit |
| Sau khi trừ A | A = 100, B = 20 |
| Sau khi cộng B | Cả hai ví trở về giá trị ban đầu |
| Khi ghi vế lịch sử thứ hai | Không giữ vế thứ nhất hoặc thay đổi ví |
| Sau khi cập nhật trạng thái | TI-42 vẫn APPROVED ở phiên bản ban đầu |
| Khi ghi outbox hoặc hoàn thiện receipt | Không có chuyển điểm thành công bị tách khỏi dữ liệu bắt buộc |

Trong ví dụ, các dữ liệu thành công đều nằm trong cùng transaction nên không được tồn tại nửa chừng. Log về một attempt thất bại có thể vẫn tồn tại nếu đó là thiết kế audit riêng.

Sau mỗi lỗi, gửi một yêu cầu hợp lệ tiếp theo để kiểm tra tài nguyên không bị tiêu thụ vĩnh viễn hoặc bị kẹt ở trạng thái “đang xử lý” sai.

### 14.2. Kiểm thử đồng thời và vượt quyền

Bổ sung:

- Hai request cùng key: cùng một operation, không chuyển hai lần.
- Hai key khác nhau cho cùng TI-42: nhiều nhất một lần thực thi.
- Hai intent cùng tiêu thụ ví không đủ cho cả hai: không âm, không tạo lịch sử giả.
- Thay đổi nội dung sau phê duyệt: không thực thi bằng phê duyệt cũ sai phạm vi.
- Thu hồi quyền hoặc đổi chủ sở hữu: xử lý theo thứ tự có hiệu lực mà hợp đồng quy định.
- Ví đích thuộc tenant khác: không chuyển điểm dù người gọi biết ID.
- Hai ví khác nhau, hai thao tác hợp lệ: không bị tuần tự hóa toàn hệ thống bởi một khóa có phạm vi quá rộng.

Với tranh chấp, dùng điểm đồng bộ hoặc lịch thực thi có bằng chứng. Không xem hai task được submit gần nhau là bằng chứng đã tạo đúng race.

### 14.3. Đọc trạng thái từ ngoài transaction đã kết thúc

Kiểm tra dữ liệu qua connection hoặc persistence context mới sau khi transaction thực sự commit hay rollback. Đừng chỉ nhìn entity đang được cache trong session của test.

Nếu framework test tự mở một transaction bao quanh ca kiểm thử, nó có thể làm method được gọi chỉ tham gia transaction ngoài và chưa bao giờ commit ở mốc bạn nghĩ. Tách fixture đã commit, lời gọi use case và bước xác minh để quan sát đúng boundary.

Mock repository hữu ích cho nhánh điều khiển, nhưng không chứng minh được rollback thật, unique conflict, row lock hoặc isolation của database.

### 14.4. Kiểm thử phần sau commit riêng

Sau commit, cố tình dừng worker, giao lại event và làm nơi nhận phản hồi chậm. Xác minh:

- Công việc cần giao không bị mất.
- Retry giữ nguyên danh tính operation.
- Không áp dụng trùng tác dụng nghiệp vụ.
- Trạng thái chưa rõ không bị ghi thành thành công hoặc thất bại cuối cùng thiếu căn cứ.

Không gộp “transaction database đúng” với “toàn bộ workflow đã hoàn tất”. Đây là hai tầng bằng chứng khác nhau.

## 15. Bài tập thực hành

### Bài tập 1: Chọn nhóm nguyên tử

Một lệnh chốt đơn gồm kiểm tra phê duyệt, giữ hàng, lưu đơn đã chốt, ghi outbox, gửi email và cập nhật chỉ mục tìm kiếm.

Giả sử đơn, tồn kho và outbox dùng chung database. Hãy chỉ ra phần nào cần chung transaction, phần nào xử lý sau commit, và dữ liệu nào bảo đảm việc xử lý sau commit không bị quên.

### Bài tập 2: Tìm lỗi propagation

Service ngoài gọi debit với REQUIRES_NEW, rồi gọi credit trong transaction ngoài. credit ném lỗi.

Mô tả trạng thái đã commit và giải thích vì sao rollback transaction ngoài không đủ. Thiết kế lại boundary theo bất biến của chuyển điểm.

### Bài tập 3: Kiểm tra quyền đang thay đổi

Quyền thực thi nằm ở bảng ACL riêng, còn service chỉ khóa dòng ví.

Thiết kế một lịch có A đọc quyền, B thu hồi quyền rồi commit, A tiếp tục. Chọn hợp đồng về thời điểm quyền có hiệu lực và nêu cơ chế bảo vệ cần bổ sung.

### Bài tập 4: Phục hồi khi chưa biết commit

Client mất kết nối đúng lúc commit. Nó không biết TI-42 đã được thực thi hay chưa.

Thiết kế cách tra cứu hoặc retry mà không tạo thêm operation, đồng thời vẫn cho phép một transaction thực sự rollback được thực thi lại hợp lệ.

## 16. Điểm cần nhớ

Ranh giới giao dịch nghiệp vụ được suy ra từ những điều phải luôn đúng và những trạng thái thất bại không được phép tồn tại.

Trong ví dụ chuyển điểm, debit, credit, lịch sử, trạng thái, kết quả command và nghĩa vụ phát event phải được phối hợp trong cùng bước nguyên tử. Khóa, phiên bản, quyền và constraint bảo vệ quyết định trước tranh chấp; idempotency bảo vệ việc gửi lại; workflow có trạng thái bảo vệ phần vượt ra ngoài database.

Một annotation chỉ là cách khai báo. Bằng chứng của boundary đúng là sau lỗi, retry và thao tác đồng thời, dữ liệu đã commit vẫn giữ được hợp đồng nghiệp vụ.
