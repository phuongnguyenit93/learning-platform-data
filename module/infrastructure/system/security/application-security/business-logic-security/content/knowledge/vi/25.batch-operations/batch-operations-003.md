# Batch partial success — Thành công từng phần trong thao tác hàng loạt

## 1. Thành công từng phần là một hợp đồng, không phải một vòng lặp bắt lỗi

Một batch có thể chứa nhiều yêu cầu nghiệp vụ: duyệt hồ sơ, nhận lệnh chi, hoàn tiền hoặc cập nhật đơn hàng. Không phải mọi phần tử đều có cùng quyền truy cập, trạng thái hoặc mức hợp lệ.

Ví dụ người dùng gửi ba yêu cầu thực thi thanh toán:

- Phần tử A đủ điều kiện và được nhận.
- Phần tử B không thuộc phạm vi được phép xử lý.
- Phần tử C đủ điều kiện và được nhận.

Nếu API hỗ trợ **batch partial success**, A và C có thể tồn tại bền vững dù B bị từ chối. Hệ thống phải diễn đạt rõ điều đó và giúp client retry an toàn.

Một triển khai chỉ `for` từng phần tử, `catch Exception` rồi trả `successCount` dễ gây các lỗi bảo mật logic:

- Báo một phần thành công nhưng transaction cuối cùng rollback toàn bộ.
- Một phần tử bị trả lỗi trong khi đã tạo command hoặc hiệu ứng bên ngoài.
- Retry batch làm thực hiện lại A và C.
- Kiểm tra quyền phần tử đầu rồi dùng cho toàn danh sách.
- Hai phần tử cùng vượt kiểm tra hạn mức còn lại và nhận tổng số tiền quá giới hạn.
- Gộp timeout, thiếu quyền và chưa xử lý thành cùng một trạng thái thất bại.

Bài học dùng batch nhận yêu cầu thực thi lệnh chi để thiết kế ngữ nghĩa, transaction, idempotency và kiểm thử những tình huống đó.

## 2. Chọn đơn vị nguyên tử trước khi xử lý

| Mô hình | Đơn vị được nhận hoặc rollback | Hệ quả |
| --- | --- | --- |
| Toàn bộ hoặc không nhận | Cả batch trong phạm vi nguyên tử đã cam kết | Một lỗi làm phần được bảo vệ của cả batch không được nhận |
| Thành công từng phần | Mỗi item hoặc nhóm item được định nghĩa | Item đã commit không tự bị hủy vì item khác lỗi |
| Xử lý bất đồng bộ | Command hoặc item có vòng đời bền vững | Nhận batch không đồng nghĩa từng item đã thành công |
| Quy trình nhiều dịch vụ có bù | Từng bước có giao thức và nghĩa vụ riêng | Compensation không phải rollback cục bộ toàn batch |

Ví dụ của bài chọn mỗi item là một lần nhận command nguyên tử trong cơ sở dữ liệu cục bộ. Một item thành công nghĩa là command thực thi của nó đã được nhận, chưa có nghĩa tiền đã chuyển.

Không tự chuyển từ chế độ nguyên tử sang từng phần khi gặp lỗi. Nếu client kỳ vọng cả tập cùng được nhận, một fallback âm thầm tiếp tục từng item làm thay đổi ý nghĩa nghiệp vụ.

### 2.1. Có trường hợp không nên dùng partial success

Nếu các phần tử chỉ hợp lệ khi cùng tồn tại, cần đánh giá theo đơn vị lớn hơn. Ví dụ hai bước của một nghĩa vụ cân bằng không nên được chia thành hai giao dịch độc lập chỉ để tăng số phần tử báo thành công.

Partial success phù hợp khi nghiệp vụ chấp nhận kết quả không đồng đều và có cách theo dõi, phục hồi từng ý định. Tốc độ hoặc sự thuận tiện của code không tự quyết định được điều này.

## 3. Phân biệt nhận batch, nhận item và hoàn tất hiệu ứng

Trong ví dụ có ba lớp kết quả:

```text
Batch được đăng ký
  → từng item được nhận hoặc từ chối
    → execution command tiếp tục thực thi và đối soát
```

Các phát biểu cần giữ riêng:

| Phát biểu | Điều đã biết |
| --- | --- |
| Đã nhận batch | Manifest hoặc công việc điều phối được lưu theo hợp đồng |
| Item được chấp nhận | Command của item đã commit đủ điều kiện nhận |
| Payment đã thành công | Có bằng chứng hiệu ứng thanh toán hoàn tất |
| Batch xử lý item đã hoàn tất | Các item đều có kết quả ổn định theo hợp đồng điều phối |

Nếu item là action yêu cầu thực thi, kết quả nên mang nghĩa `ACCEPTED`, không gọi là `PAID` chỉ vì đã ghi outbox.

### 3.1. Trạng thái item

Một mô hình có thể dùng:

| Trạng thái hoặc outcome | Ý nghĩa |
| --- | --- |
| `PENDING` | Chưa có lần nhận xử lý hoàn tất |
| `PROCESSING` | Đang được worker hoặc tiến trình điều phối xử lý theo giao thức |
| `ACCEPTED` | Command được nhận bền vững, có operation reference |
| `REJECTED` | Có kết luận từ chối item và chưa nhận hiệu ứng tương ứng theo hợp đồng |
| `UNKNOWN` | Chưa đủ bằng chứng về kết quả, cần đọc lại hoặc đối soát |
| `SKIPPED` | Không xử lý theo một quyết định dừng hoặc hủy được định nghĩa rõ |

Không phải hệ thống nào cũng cần lưu tất cả trạng thái trung gian. Điều bắt buộc là không gộp chúng thành một cờ thất bại khiến client chọn sai cách retry.

Nếu không kết nối được cơ sở dữ liệu để xác nhận commit, hệ thống có thể chỉ trả được quan sát `UNKNOWN` mà chưa lưu được nó. Không ghi đè một kết quả `ACCEPTED` đã có bằng một kết luận từ chối mới.

### 3.2. Trạng thái batch

Có thể có `REGISTERED`, `RUNNING`, `COMPLETED` và `NEEDS_RECONCILIATION`. Trong ví dụ, batch chỉ hoàn tất bước xử lý item khi mọi phần tử có kết quả ổn định như ACCEPTED, REJECTED hoặc SKIPPED theo hợp đồng.

`COMPLETED` không có nghĩa mọi item được nhận, và không có nghĩa mọi payment đã trả xong. Nếu còn item chưa rõ kết quả, summary và trạng thái phải thể hiện nghĩa vụ đó.

## 4. Request cần định danh cả batch và từng ý định

Ví dụ:

```http
POST /payment-execution-batches
Authorization: Bearer <access-token>
Idempotency-Key: batch-2026-12-01-001
Content-Type: application/json

{
  "mode": "PARTIAL",
  "items": [
    {
      "clientItemId": "row-001",
      "itemIntentKey": "89a8ee21-6d99-471a-946c-3525802e8214",
      "paymentRequestId": "request-101",
      "expectedVersion": 18,
      "approvalRound": 3
    },
    {
      "clientItemId": "row-002",
      "itemIntentKey": "fe2c7386-d942-43ec-97ea-adbbd502af98",
      "paymentRequestId": "request-102",
      "expectedVersion": 9,
      "approvalRound": 2
    }
  ]
}
```

| Định danh | Vai trò |
| --- | --- |
| Batch idempotency key | Nhận diện lần đăng ký cùng manifest |
| `batchId` do server cấp | Tra cứu tiến độ và kết quả của batch đã đăng ký |
| `clientItemId` | Đối chiếu dòng trong manifest và giao diện |
| `itemIntentKey` | Nhận diện cùng ý định item qua retry, kể cả khi được gửi trong một batch khác theo hợp đồng |
| Operation hoặc execution ID | Theo dõi command nghiệp vụ đã được nhận |

`clientItemId` không tự là quyền truy cập hoặc khóa chống mọi hiệu ứng trùng. Vị trí mảng cũng không phải định danh bền vững khi người dùng sắp xếp lại danh sách.

### 4.1. Không nhận quyền hoặc kết quả tính toán từ payload batch

Tenant, actor thực tế, trạng thái phê duyệt và số tiền có thẩm quyền phải lấy từ những nguồn phù hợp. Một cờ `allApproved`, `skipItemAuthorization` hoặc tổng tiền client gửi không được thay kiểm tra từng đối tượng.

## 5. Kiểm tra ở cấp envelope và cấp item

### 5.1. Envelope không hợp lệ thì chưa bắt đầu nhận các item

Các lỗi có thể kiểm tra trước gồm:

- Mode không được hỗ trợ.
- Schema hoặc kiểu dữ liệu nền không đọc được.
- Số item vượt giới hạn được công bố.
- `clientItemId` trùng trong cùng manifest.
- `itemIntentKey` trùng trái hợp đồng trong cùng manifest.
- Danh sách lặp cùng target và action mà policy của batch không cho phép.

Ví dụ có thể từ chối toàn bộ envelope nếu nó không đủ rõ để định danh hoặc xử lý. Cần làm điều đó trước khi bắt đầu nhận item, thay vì xử lý vài dòng rồi mới phát hiện cấu trúc manifest mâu thuẫn.

Kiểm tra ID trùng trong payload không cần tiết lộ đối tượng có tồn tại. Các kiểm tra phụ thuộc đối tượng và quyền đọc phải được thực hiện trong phạm vi được phép.

### 5.2. Item không hợp lệ có kết quả riêng

Những vấn đề như sai scope, version cũ, thiếu approval hoặc trạng thái đã thay đổi được đánh giá tại gate của item theo policy.

Chấp nhận đăng ký batch không chứng minh mọi item đã được cấp quyền. Nếu API nhận xử lý bất đồng bộ, điều này cần được thể hiện rõ trong response và tài liệu.

### 5.3. Freeze manifest đã đăng ký

Sau khi nhận batch, lưu biểu diễn canonical hoặc digest và dữ liệu bất biến cần xử lý. Không để client thay item list của một `batchId` đang chạy mà vẫn dùng cùng một biên nhận.

Fingerprint batch cần bao gồm mode, các item và ngữ nghĩa thứ tự nếu thứ tự có ý nghĩa. Không tự sort trước khi hash nếu policy cam kết xử lý theo thứ tự người dùng gửi.

## 6. Phân quyền phải áp dụng cho từng item

Một quyền `BATCH_EXECUTION_REQUEST` chỉ cho phép sử dụng cơ chế hàng loạt, không tự cấp quyền trên mọi payment request trong danh sách.

Với mỗi item cần kiểm tra:

```text
đúng_tenant
AND đúng_đối_tượng_và_quan_hệ
AND có_quyền_action
AND thỏa_phân_tách_nhiệm_vụ
AND đúng_version_và_vòng_duyệt
AND đủ_bằng_chứng_tại_gate
AND đủ_hạn_mức_hoặc_tài_nguyên_cần_thiết
```

Một batch có thể chứa ID khác tenant ở dòng cuối. Không chỉ kiểm tra phần tử đầu hoặc query một tập object rồi bỏ qua những ID không trả về mà vẫn báo toàn bộ thành công.

### 6.1. Quyền có thể thay đổi trong khi batch chạy

Ví dụ chọn hợp đồng đánh giá quyền hiện tại tại gate từng item. Nếu quyền bị thu hồi giữa chừng, các item đã được nhận vẫn là công việc có lịch sử riêng; những item mới cần bị xử lý theo quyền hiện tại và chính sách dừng hoặc từ chối tương ứng.

Một hệ thống có thể dùng permit cấp cho cả manifest, nhưng permit phải ràng buộc phạm vi, nội dung, thời hạn và cơ chế thu hồi rõ ràng. Một lần kiểm tra role đầu vòng lặp không tự tạo ra bảo đảm đó.

### 6.2. Quyền đọc kết quả là một quyết định khác

Biết batch ID hoặc item key không thay thế quyền đọc. Summary, chi tiết và file export đều cần tuân chính sách truy cập hiện tại.

Nếu một item đã ACCEPTED nhưng caller không còn được đọc chi tiết, hệ thống có thể che phần trả về theo policy; không được sửa kết quả nghiệp vụ đã lưu thành REJECTED rồi ngụ ý command chưa từng được nhận.

## 7. Thiết kế transaction cho partial success

Một kiến trúc dễ giải thích là:

```text
Transaction đăng ký batch:
  lưu manifest và các item ban đầu
COMMIT

Transaction item A:
  kiểm tra quyền và điều kiện
  nhận command A + kết quả item A + audit + outbox
COMMIT

Transaction item B:
  kiểm tra và phát hiện không đủ điều kiện
ROLLBACK phần nhận hiệu ứng của B

Transaction ghi kết luận B nếu vẫn chưa được xử lý:
  lưu REJECTED và lỗi an toàn
COMMIT
```

Nếu A đã commit, lỗi B không tự rollback A. Đây là ngữ nghĩa được chọn, không phải một tình trạng lỗi cần che đi bằng một response chung.

### 7.1. Vì sao bắt lỗi trong một transaction lớn dễ sai?

Nếu mọi item cùng tham gia một transaction vật lý, việc một scope đánh dấu rollback-only có thể khiến commit ngoài cùng thất bại dù code đã bắt lỗi và cộng số thành công. Trong Spring, đây là tình huống có thể dẫn đến `UnexpectedRollbackException` với propagation cùng tham gia transaction. [Spring: Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)

Mặt khác, nếu bắt một domain exception mà không làm rollback phần dữ liệu đã ghi, code có thể commit nửa item rồi trả REJECTED. Cả hai đều sai với hợp đồng nguyên tử từng item.

### 7.2. Transaction mới phải thực sự độc lập

Trong mô hình minh họa, mỗi item chạy bằng một bean riêng với `REQUIRES_NEW`; các nghiệp vụ con phải tham gia transaction item, không tự commit một phần độc lập. [Spring: PROPAGATION_REQUIRES_NEW](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html#tx-propagation-requires-new)

Nếu dùng savepoint hoặc nested transaction, cần nhớ những item chưa trở thành các commit độc lập trước commit transaction ngoài cùng. Đừng mô tả kết quả tạm thời như đã bền vững theo mô hình từng item của bài.

## 8. Ví dụ Java: điều phối ngoài transaction của item

### 8.1. Giả định

Các đoạn mã sau là thiết kế minh họa, không phải một ứng dụng batch hoàn chỉnh:

- Batch đã được đăng ký và manifest đã commit.
- Orchestrator không giữ một transaction bao ngoài toàn batch.
- Actor được lấy từ ngữ cảnh hoặc bằng chứng khởi tạo được bảo vệ, không từ một field tùy ý trong item.
- Command, kết quả item, reservation cục bộ, audit và outbox của lần nhận dùng chung cơ sở dữ liệu cùng transaction manager.
- Không gọi nhà cung cấp chuyển tiền trong transaction item.
- Action engine giữ đầy đủ quyền và bất biến như endpoint đơn.

### 8.2. Orchestrator

```java
@Service
public class PartialBatchOrchestrator {
    private final BatchManifestRepository manifests;
    private final BatchItemExecutor executor;
    private final BatchRejectionRecorder rejectionRecorder;
    private final BatchOutcomeObserver outcomeObserver;
    private final BatchProgressService progress;
    private final BatchResultReader results;

    // Constructor injection được lược bỏ.
    // Method này không giữ transaction bao ngoài toàn batch.
    public BatchResult process(VerifiedActor actor, UUID batchId) {
        BatchManifest manifest = manifests.loadAuthorizedImmutable(
                actor, batchId);

        for (BatchItemRef item : manifest.itemsInDeclaredOrder()) {
            try {
                executor.acceptOne(actor, item);
            } catch (DefinitiveItemRejection ex) {
                // Lời gọi bean transactional đã kết thúc trước khi vào đây.
                rejectionRecorder.recordUnlessAlreadyResolved(
                        actor, item, ex.safeError());
            } catch (Exception ex) {
                // Không tự coi lỗi hạ tầng là item chắc chắn chưa được nhận.
                outcomeObserver.resolveOrMarkUnknown(actor, item, ex);
                if (outcomeObserver.mustStopProcessing()) {
                    break;
                }
            }
        }

        progress.recomputeFromDurableItems(actor.tenantId(), batchId);
        return results.readAuthorized(actor, batchId);
    }
}
```

Các dependency `final` cần constructor thực tế. Những helper về lỗi, dừng và quyền phải có hợp đồng cụ thể; không để `catch Exception` biến mọi sự cố thành một REJECTED rồi tiếp tục vô hạn.

Nếu nguồn dữ liệu đang lỗi hàng loạt, có thể cần dừng điều phối và giữ các item chưa chạy là PENDING. Không có bằng chứng đánh giá item thì không được bịa một lỗi validation cho item đó.

`DefinitiveItemRejection` chỉ nên dùng khi có cơ sở rằng lần nhận tương ứng chưa commit và không có hiệu ứng ngoài transaction chưa được giải quyết. Nếu rollback hoặc commit không xác định, phải đi vào quan sát hoặc đối soát.

### 8.3. Executor của một item

```java
@Service
public class BatchItemExecutor {
    private final BatchItemRepository items;
    private final BatchExecutionAuthorization authorization;
    private final PaymentExecutionEngine executionEngine;
    private final BatchAuditRepository audits;

    // Constructor injection được lược bỏ.

    @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            rollbackFor = Exception.class)
    public InternalItemReceipt acceptOne(
            VerifiedActor actor,
            BatchItemRef itemRef) {

        BatchItem item = items.lockForExecution(
                actor.tenantId(), itemRef.batchId(), itemRef.itemId())
            .orElseThrow(BatchItemNotFoundException::new);

        authorization.requireProcessingAuthority(actor, item);

        if (item.hasStableOutcome()) {
            return item.internalReceipt();
        }
        item.requireProcessable();

        // Phải tham gia chính transaction item này.
        // Bên trong có authorization, version, approval, quota,
        // idempotency và ràng buộc nghĩa vụ nghiệp vụ của action đơn.
        AcceptedExecution execution =
                executionEngine.acceptInCurrentTransaction(
                        actor,
                        item.immutableCommand(),
                        item.itemIntentKey());

        items.markAccepted(item, execution);
        audits.appendItemAccepted(actor, item, execution);
        return InternalItemReceipt.accepted(item.id(), execution.id());
    }
}
```

`internalReceipt()` là kết quả nội bộ cho điều phối. Trước khi trả qua API, reader vẫn phải áp dụng quyền công bố hiện tại; không coi việc có outcome ổn định là quyền đọc mọi dữ liệu liên quan.

Action engine cần cùng transaction và transaction manager. Có thể dùng một hợp đồng yêu cầu transaction hiện hữu ở lớp đó để phát hiện gọi sai. Nếu nó tự commit command bằng transaction khác rồi việc ghi item lỗi, bảo đảm nguyên tử giữa command và outcome item của ví dụ không còn đúng.

### 8.4. Bean riêng và ranh giới proxy

Với Spring proxy thông thường, lời gọi nội bộ trong cùng instance không tự kích hoạt transaction của method được gọi. Cần để lời gọi đi qua bean được quản lý như thiết kế minh họa hoặc dùng cơ chế transaction tường minh phù hợp. [Spring: Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)

Không chỉ thêm `REQUIRES_NEW` vào một private helper rồi giả định mỗi vòng lặp đã commit riêng.

## 9. Ghi kết quả từ chối không được ghi đè thành công cạnh tranh

Sau khi transaction item B rollback, một transaction riêng có thể ghi REJECTED để batch reader thấy kết quả bền vững. Nhưng giữa hai bước, một worker khác có thể đã nhận lại cùng item.

Một lịch nguy hiểm:

```text
T1 gặp lỗi domain, rollback item.
T2 xử lý lại item và commit ACCEPTED.
T1 mở transaction ghi lỗi, ghi đè item thành REJECTED.
```

Recorder cần khóa hoặc cập nhật có điều kiện, đọc outcome hiện tại và không ghi đè một kết quả đã được giải quyết. Nếu đã ACCEPTED, giữ operation reference tương ứng.

Với lỗi quanh commit, observer phải đọc lại item và ledger command bằng định danh ổn định. Nếu chưa xác nhận được, giữ nghĩa vụ đối soát hoặc trả UNKNOWN; không tạo một command mới để thử xem có thành công không.

### 9.1. Không suy từ exception thành kết quả vật lý

Một lỗi kết nối có thể xảy ra trước commit, sau commit hoặc khi client chưa nhận được kết quả. Chỉ lớp có đủ bằng chứng mới được kết luận chưa nhận.

Không bắt mọi exception rồi lưu `REJECTED: INVALID_INPUT`. Làm vậy vừa sai sự thật vừa khiến người dùng sửa payload và tạo ý định mới khi command cũ có thể đã tồn tại.

### 9.2. Nếu observer cũng không ghi được

Khi cơ sở dữ liệu không sẵn sàng, không thể hứa đã lưu UNKNOWN hoặc REJECTED. Có thể cần phản hồi chưa xác định kèm batch ID, cơ chế retry hoặc vận hành đối soát.

Dữ liệu ổn định phải được đọc lại khi hệ thống phục hồi. Một lỗi ghi trạng thái lỗi không được làm mất định danh batch hoặc item đã được nhận trước đó.

## 10. Hai lớp idempotency và một lớp bất biến nghiệp vụ

### 10.1. Idempotency batch

Một phạm vi có thể là:

```text
UNIQUE(tenant_id, initiating_subject_id, batch_action, batch_key)
```

Cùng key và cùng manifest trả lại batch đã đăng ký. Cùng key nhưng đổi mode, item, thứ tự có ý nghĩa hoặc dữ liệu quyết định ý định phải bị xử lý như xung đột theo hợp đồng.

### 10.2. Idempotency item

Một phạm vi minh họa:

```text
UNIQUE(tenant_id, initiating_subject_id, item_action, item_intent_key)
```

Fingerprint item ràng buộc target, expected version, vòng duyệt và dữ liệu liên quan. Không có batch ID trong phạm vi này để cùng một intent có thể được nhận diện khi được retry ở batch khác.

Nếu chọn một phạm vi khác, cần nêu rõ. Chỉ dùng `batchId + rowIndex` có thể chống lặp trong một lần chạy nhưng không nhận ra cùng ý định khi client tạo batch mới hoặc sắp xếp lại mảng.

### 10.3. Bất biến theo nghĩa vụ

Người dùng có thể cố đổi cả batch key và item key. Vì vậy vẫn cần ràng buộc ở nghiệp vụ, chẳng hạn một payment intent chỉ có một lệnh thanh toán chính trong mô hình ví dụ.

Idempotency theo actor không tự ngăn hai actor khác nhau nhận cùng nghĩa vụ nếu không có lớp ràng buộc này. Với thanh toán nhiều phần, mô hình phải bảo vệ số tiền còn được nhận xử lý thay vì áp dụng một điều kiện duy nhất không phù hợp.

### 10.4. Replay không tạo thêm phần sử dụng

Một item trả lại execution ID cũ không được giữ chỗ quota lần nữa, tạo thêm outbox thanh toán hoặc tăng số command mới.

Summary có thể đếm một dòng có outcome ACCEPTED dù đó là kết quả replay. Nếu cần đo hiệu ứng mới, dùng một chỉ số được định nghĩa riêng; không suy số lệnh mới từ số dòng response thành công.

## 11. Hạn mức dùng chung và thứ tự nhận item

Giả sử quota còn 100, hai item lần lượt cần 70 và 50. Cả hai có thể hợp lệ riêng lẻ nhưng không thể cùng giữ chỗ trong giới hạn đó.

```text
Nếu item 70 được nhận trước: còn 30, item 50 không đủ điều kiện.
Nếu item 50 được nhận trước: còn 50, item 70 không đủ điều kiện.
```

Partial success chấp nhận kết quả như vậy khi policy cho phép, nhưng phải xác định có cam kết thứ tự hoặc ưu tiên không. Chạy song song có thể làm phần được nhận khác với thứ tự mảng.

### 11.1. Không kiểm tra quota một lần rồi ghi nhiều lần

Phần sử dụng phải được giữ chỗ bằng transaction, khóa hoặc cập nhật có điều kiện phù hợp cho từng lần nhận. Mọi endpoint đơn và batch cùng dùng quota phải tuân thủ cùng bất biến.

Nếu lấy tổng từ payload, bỏ qua những phần đang được nhận xử lý hoặc chỉ kiểm tra số đã hoàn tất, các batch cạnh tranh có thể cùng vượt qua.

Số tiền cần từ nguồn có thẩm quyền và đúng tiền tệ. Không cộng các đồng tiền khác nhau thành một số tổng không có ngữ nghĩa, và phải kiểm soát giới hạn biểu diễn khi tính tổng.

### 11.2. Thứ tự khóa và giới hạn song song

Quota, item và đối tượng nghiệp vụ có thể cần nhiều khóa. Thiết kế thứ tự khóa tương thích giữa các đường để giảm deadlock; xử lý lỗi cạnh tranh bằng retry hữu hạn đúng command.

Transaction độc lập không có nghĩa tài nguyên cơ sở dữ liệu vô hạn. Nếu giữ transaction ngoài rồi mở nhiều `REQUIRES_NEW`, connection và lock của scope ngoài có thể còn bị giữ; cần quản lý pool và mức song song phù hợp. [Spring: Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)

Mô hình orchestrator của bài tránh transaction bao ngoài, nhưng vẫn phải giới hạn số worker và thời gian giữ transaction item.

## 12. Response cần cho biết chính xác phần nào đã được nhận

Ví dụ một batch đã giải quyết hết các item:

```json
{
  "batchId": "batch-123",
  "mode": "PARTIAL",
  "state": "COMPLETED",
  "summary": {
    "requested": 3,
    "accepted": 2,
    "rejected": 1,
    "pending": 0,
    "unknown": 0
  },
  "results": [
    {
      "clientItemId": "row-001",
      "outcome": "ACCEPTED",
      "executionRequestId": "exec-101"
    },
    {
      "clientItemId": "row-002",
      "outcome": "REJECTED",
      "error": {
        "code": "ITEM_NOT_ACCESSIBLE",
        "recovery": "REVIEW_ACCESS_OR_REMOVE_ITEM"
      }
    },
    {
      "clientItemId": "row-003",
      "outcome": "ACCEPTED",
      "executionRequestId": "exec-103"
    }
  ]
}
```

Có thể trả một response thành công ở cấp envelope khi nó đang cung cấp đúng kết quả từng phần. Nếu mới đăng ký công việc bất đồng bộ, response nên diễn đạt đang chờ xử lý và cung cấp đường đọc trạng thái theo hợp đồng, không bịa kết quả cuối.

### 12.1. Lỗi item cần hướng phục hồi đúng

| Nhóm lỗi | Hành động phù hợp |
| --- | --- |
| Thiếu quyền hoặc ngoài scope | Không tự retry để hy vọng được phép; cần quyền hoặc bỏ item |
| Dữ liệu nghiệp vụ không đạt | Sửa dữ liệu và tạo ý định mới theo hợp đồng sau khi biết lần trước chưa nhận |
| Version cũ | Tải lại đối tượng và xác nhận lại nội dung |
| Lỗi tạm thời chưa tạo hiệu ứng, có bằng chứng rõ | Retry đúng command theo chính sách |
| UNKNOWN | Tra cứu hoặc đối soát bằng cùng định danh, không tự đổi key |
| PENDING | Tiếp tục hoặc chờ xử lý item hiện có, không suy là đã bị từ chối |

Không để client chỉ nhìn một cờ `retryable` mà không biết phải dùng cùng nội dung, key nào hoặc có cần đọc operation trước không.

### 12.2. Summary là kết quả dẫn xuất

Tính summary từ các item bền vững hoặc một projection được cập nhật idempotent. `acceptedCount++` trên mỗi lần callback hoặc retry có thể đếm hai lần cùng item.

Khi có pagination hoặc quyền đọc bị giới hạn, summary và dữ liệu trả về phải tuân chính sách công bố. Việc che dữ liệu không được thay đổi outcome nghiệp vụ đã ghi nhận.

## 13. Retry chỉ phần chưa được giải quyết

Một chiến lược an toàn:

1. Đọc lại batch bằng batch ID và quyền hiện tại.
2. Với ACCEPTED, theo dõi operation hiện có; không tạo lại ý định.
3. Với UNKNOWN, đối soát hoặc retry đúng item intent theo giao thức hỗ trợ.
4. Với PENDING, tiếp tục item đã đăng ký nếu hệ thống cho phép.
5. Với REJECTED, phân biệt cần sửa dữ liệu, đọc lại version hay thay đổi quyền.
6. Khi tạo một intent đã sửa, dùng key mới theo hợp đồng, không gắn payload khác vào intent đã được nhận.

Không dựa vào response cuối cùng client đã nhìn thấy để quyết định dữ liệu server. Client có thể mất response sau khi một số item đã commit.

### 13.1. Retry trong batch mới

Nếu hệ thống cho phép, giữ item intent key cho cùng ý định để ledger nhận ra command cũ. Batch key mới chỉ định danh manifest mới, không xóa lịch sử item.

Không gửi lại tất cả phần tử với tất cả key mới chỉ vì một dòng thất bại. Ràng buộc nghiệp vụ vẫn cần bảo vệ trước hành vi đó nhưng không nên để client mặc định tạo tình huống trùng.

### 13.2. Item đã bị từ chối có được đánh giá lại không?

Cần chọn rõ outcome REJECTED có được lưu cố định cho intent đó hay được phép thử lại trong một số trường hợp. Một lỗi tạm thời không nên bị lưu vĩnh viễn như lỗi nghiệp vụ nếu hợp đồng muốn retry.

Khi sửa input, thay expected version hoặc tạo điều kiện nghiệp vụ mới, thường đã có một ý định cần ràng buộc nội dung mới. Chính sách key và result ledger phải phản ánh đúng lựa chọn đó.

## 14. Dừng, hủy và xử lý sự cố giữa batch

### 14.1. Client ngắt kết nối

Một số item có thể đã commit trước khi kết nối bị mất. Không tự rollback chúng bằng cách đặt state về trước hoặc giải phóng tài nguyên không có bằng chứng.

Batch và manifest bền vững giúp client hoặc worker đọc lại và tiếp tục đúng những item chưa giải quyết. Không tạo một batch hoàn toàn mới ngoài ý muốn chỉ vì response không tới nơi.

### 14.2. Dừng do lỗi hạ tầng

Nếu không thể lấy nguồn policy, dữ liệu hoặc kết nối cần thiết, có thể dừng và để phần chưa chạy ở trạng thái thể hiện đúng sự thật. Không đánh dấu toàn bộ phần còn lại là input sai.

Nếu hệ thống không có khả năng tự phục hồi an toàn, chuyển trạng thái cần xử lý theo vận hành cùng định danh item và evidence cần thiết.

### 14.3. Hủy batch

Hủy điều phối có thể chặn những item chưa được nhận, nhưng không đồng nghĩa hủy các command ACCEPTED. Những command đó cần quy trình hủy hoặc compensation riêng nếu nghiệp vụ hỗ trợ.

Có thể đánh dấu item chưa xử lý là SKIPPED với lý do hủy, nhưng không gọi nó là một lỗi validation. Những item đã ACCEPTED vẫn giữ operation reference và lịch sử trách nhiệm.

### 14.4. Không tạo một saga ngầm

Nếu người dùng muốn đảo những item đã thành công vì item khác lỗi, đó là một quy trình bù riêng với quyền, giới hạn, idempotency và khả năng thất bại. Nó không còn là lời hứa “partial success thì phần thành công tự biến mất”.

## 15. Giới hạn tài nguyên, quan sát và audit

### 15.1. Batch làm tăng tải không chỉ theo số request

Một request chứa hàng nghìn item có thể tạo hàng nghìn lần kiểm tra quyền, khóa, audit và command. Cần giới hạn kích thước, tổng chi phí và mức song song theo phạm vi phù hợp.

Rate limit chỉ đếm request có thể không phản ánh tác động. Những giới hạn theo số item hoặc nghiệp vụ cần được tính tại server và không thay thế quyền trên từng đối tượng.

### 15.2. Audit cần cả batch và item

Giữ được batch ID, client item ID, item intent key hoặc tham chiếu an toàn, actor gốc, tenant, action, target, policy revision, gate, outcome và operation ID.

Audit thành công của item phải phản ánh commit của chính item. Đừng ghi “batch thành công” trước khi biết các commit đã xảy ra thế nào.

Những lần thử bị từ chối cần được phân biệt với command đã nhận. Không ghi token hoặc toàn bộ dữ liệu thanh toán nhạy cảm chỉ để hỗ trợ đối chiếu hàng loạt.

### 15.3. Các tín hiệu cần theo dõi

| Tín hiệu | Điều cần điều tra |
| --- | --- |
| Summary không khớp số item bền vững | Projection bị đếm lặp hoặc cập nhật không nhất quán |
| Item REJECTED nhưng có execution command được nhận | Có lỗi ranh giới transaction hoặc recorder ghi đè |
| UNKNOWN tồn đọng | Cơ chế tra cứu, commit observation hoặc provider đang có vấn đề |
| Batch mới tạo nhiều command cho cùng intent | Phạm vi idempotency hoặc ràng buộc nghiệp vụ thiếu |
| Lỗi ngoài tenant tập trung ở vài dòng | Có thể trộn scope, client lỗi hoặc dò đối tượng |
| Pool cạn khi tăng song song | Transaction và giới hạn worker cần được xem xét |
| Nhiều item chưa xử lý bị báo validation fail | Có thể đang phân loại lỗi hạ tầng sai |

## 16. Kiểm thử partial success bằng lỗi có kiểm soát

### 16.1. Kịch bản nền

Chuẩn bị ba item độc lập: A hợp lệ, B vi phạm một rule xác định, C hợp lệ. Với chế độ PARTIAL, chứng minh:

- A và C có command cùng outcome ACCEPTED đã commit.
- B không có command hoặc reservation không hợp lệ còn lại.
- Summary phản ánh hai ACCEPTED, một REJECTED.
- Không có lời khẳng định mọi payment đã hoàn tất nếu mới nhận command.

Actor, payload và những tiền đề không thuộc mục tiêu test phải hợp lệ. Nếu mọi item đều bị authentication hoặc schema chặn, test chưa chạm vào partial success.

### 16.2. Tiêm lỗi tại từng ranh giới

| Điểm lỗi | Kết quả cần chứng minh |
| --- | --- |
| Trước khi nhận B | A vẫn bền vững, B chưa được nhận |
| B đã ghi một phần nhưng audit hoặc outbox bắt buộc lỗi | Toàn bộ phần nhận của B rollback, A không bị rollback theo |
| B commit nhưng mất response | Tra cứu hoặc retry nhận ra operation cũ, không tạo command mới |
| Process dừng trước C | C còn chưa xử lý, không bị bịa thành validation fail |
| Ghi REJECTED cạnh tranh với một worker đã ACCEPTED | Recorder không ghi đè kết quả thành công |
| Summary update thất bại | Các item đã commit không bị mất hoặc thực hiện lại; projection có thể dựng lại |
| Cơ sở dữ liệu không sẵn sàng quanh commit | Không khẳng định NOT_ACCEPTED khi chưa có bằng chứng |

Đọc lại dữ liệu bằng ranh giới transaction phù hợp. Test bao ngoài trong một transaction tự rollback có thể che việc các item có thật sự commit độc lập hay không.

### 16.3. Idempotency và bản sao item

1. Retry cùng batch key và manifest trả batch cũ.
2. Cùng batch key nhưng đổi nội dung bị xung đột.
3. Cùng item intent trong batch mới không tạo command hoặc giữ quota thêm.
4. Đổi key không vượt ràng buộc cùng payment intent bị giới hạn.
5. Duplicate client item ID hoặc target trái hợp đồng bị phát hiện trước nhận item.
6. Summary không tăng thêm khi giao lại outcome hoặc callback.
7. Mất quyền đọc không làm ledger đổi ACCEPTED thành REJECTED.

### 16.4. Quyền và concurrency

Dùng transaction hoặc worker độc lập với barrier hoặc latch để điều khiển lịch:

```text
A. Hai item cạnh tranh phần quota còn lại không đủ cho cả hai.
   Kết quả: tổng phần được nhận và giữ chỗ không vượt giới hạn.

B. Hai worker nhận cùng item hoặc cùng intent ở hai batch.
   Kết quả: chỉ có hiệu ứng được phép và operation reference nhất quán.

C. Quyền hoặc approval bị thu hồi giữa các item.
   Kết quả: mỗi gate tuân theo policy đã chọn;
   không dùng role snapshot ban đầu như quyền vô thời hạn.

D. Transaction item thất bại rồi recorder gặp một outcome mới hơn.
   Kết quả: không ghi đè thành công đã commit.
```

Không dùng `sleep` làm bằng chứng đã kiểm thử một cuộc đua. Kiểm tra command, quota, assignment scope, audit và outbox, không chỉ response.

### 16.5. Kiểm thử transaction wiring

Chứng minh lời gọi thực sự đi qua bean transaction, từng item có commit độc lập và action engine tham gia đúng transaction item. Kiểm tra cấu hình rollback cho các exception được dùng.

Mock action engine trả receipt không chứng minh atomicity giữa command và outcome item. Với những bảo đảm này cần integration test trên engine dữ liệu và transaction manager phù hợp.

## 17. Các lỗi thiết kế cần tránh

| Cách làm | Vì sao sai với partial success | Hướng thay thế |
| --- | --- | --- |
| Một transaction lớn, catch rồi cộng successCount | Commit cuối có thể rollback cả những phần báo thành công | Đơn vị transaction phù hợp hợp đồng |
| Item ghi command bằng transaction khác với outcome | Dễ có command đã nhận nhưng item báo chưa nhận | Command và outcome cùng commit hoặc giao thức đối soát rõ |
| Mọi exception thành REJECTED | Có thể đã commit hoặc chưa đánh giá gì | Phân loại chắc chắn, pending và unknown |
| Recorder lỗi ghi đè một outcome mới | Làm mất sự thật của command đã nhận | Khóa hoặc cập nhật có điều kiện và đọc lại |
| Chỉ idempotency ở cấp batch | Batch mới thực hiện lại item cũ | Key theo item intent và ràng buộc nghĩa vụ |
| Chỉ kiểm tra quyền item đầu | Bỏ lọt đối tượng khác scope | Guard cho từng item |
| Quota check một lần rồi chạy song song | Các phần tử cùng tiêu một phần còn lại | Giữ chỗ nguyên tử theo lần nhận |
| Chỉ đếm request để giới hạn tải | Một request có thể nhân khối lượng lớn | Giới hạn item, chi phí và mức song song |
| Client ngắt là coi chưa có gì xảy ra | Một số item đã commit | Manifest và kết quả bền vững để đọc lại |
| Hủy batch là xóa mọi hiệu ứng | Command đã nhận có vòng đời riêng | Hủy điều phối và compensation tách biệt |
| Summary tăng trên mọi retry | Đếm trùng item hoặc command | Projection idempotent từ dữ liệu bền vững |
| ACCEPTED được hiển thị là PAID | Nhầm nhận command với hoàn tất hiệu ứng | Trạng thái theo đúng giai đoạn nghiệp vụ |

## 18. Bài tập thiết kế

Thiết kế batch nhận thực thi các lệnh chi nhiều đơn vị trong cùng tenant. API hỗ trợ PARTIAL, mỗi item có version và vòng duyệt riêng, dùng quota chung và có thể được worker xử lý bất đồng bộ.

Hãy mô tả:

1. Đơn vị nguyên tử là item hay một nhóm item, và điều gì được gọi là ACCEPTED?
2. Envelope nào bị từ chối trước mọi xử lý, lỗi nào trở thành kết quả từng item?
3. Batch key, client item ID, item intent key và execution ID khác nhau ra sao?
4. Command, outcome item, quota, audit và outbox được commit cùng nhau thế nào?
5. Recorder xử lý ra sao nếu một worker khác đã commit trước lúc ghi kết luận từ chối?
6. Khi mất response hoặc chưa rõ commit, client và worker tra cứu hoặc retry bằng định danh nào?
7. Quyền thay đổi, quota cạnh tranh và thứ tự item ảnh hưởng kết quả thế nào?
8. Những test nào chứng minh A và C thành công, B thất bại, rồi retry không tạo lại A hoặc C?

Một thiết kế đạt yêu cầu phải giữ được sự thật của từng lần nhận nghiệp vụ: phần nào đã commit, phần nào chưa được nhận, phần nào chưa rõ và cách tiếp tục mà không nhân đôi hiệu ứng hoặc bỏ qua quyền trên từng đối tượng.
