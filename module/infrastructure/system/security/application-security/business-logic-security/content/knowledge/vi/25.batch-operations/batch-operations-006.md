# Batch duplicate handling: xử lý phần tử trùng trong thao tác hàng loạt

## 1. Một phần tử xuất hiện hai lần không được tạo hai quyền thực thi

Một API nhận batch phê duyệt hồ sơ. Người gọi đưa cùng hồ sơ vào hai dòng, backend xử lý từng dòng và ghi hai phiếu. Nếu quorum chỉ đếm số hàng `APPROVE`, một người có thể bị tính thành hai người duyệt độc lập.

Trong một batch hoàn tiền, lỗi tương tự có thể tạo hai operation cho cùng ý định. Gửi lại cả batch sau timeout hoặc đưa item cũ vào batch mới cũng có thể làm tác động bị lặp.

**Batch duplicate handling** là việc nhận diện và xử lý những lần xuất hiện trùng theo đúng ngữ nghĩa của hợp đồng, để một ý định không tạo tác động thêm ngoài số lần nghiệp vụ cho phép.

Không phải mọi phần tử có cùng target đều là duplicate. Hai giao dịch hợp lệ có thể cùng người nhận và số tiền; nhiều dòng cùng sản phẩm có thể biểu đạt số lượng; một đối tượng có thể nhận các action khác nhau theo workflow.

Vì vậy, câu hỏi đầu tiên không phải “dùng Set nào để xóa trùng?”, mà là:

```text
Điều gì làm hai item trở thành cùng một ý định,
và điều gì khiến nghiệp vụ cấm thực hiện thêm lần nữa?
```

Trong bảo vệ logic nghiệp vụ, cần giữ đồng thời tính đúng của quyền, trạng thái, quorum, quota, ledger và tác động ngoài hệ thống, kể cả khi batch bị gửi lại hoặc xử lý đồng thời.

## 2. Phân biệt các loại trùng và định danh

### 2.1. Những tình huống khác nhau

| Loại trùng | Ví dụ | Cơ chế cần xem xét |
|---|---|---|
| Trùng lần xuất hiện trong batch | Hai dòng cùng một item key và cùng lệnh | Hợp đồng nhận diện/gộp hoặc từ chối trong request |
| Retry cả batch | Mất response rồi gửi lại cùng manifest | Idempotency ở cấp batch |
| Retry item qua batch khác | Chia lại batch hoặc chỉ gửi phần chưa nhận kết quả | Idempotency ở cấp item độc lập vị trí/batch |
| Trùng ý nghĩa nghiệp vụ | Khác key nhưng cùng người duyệt cùng vòng | Uniqueness và invariant domain |
| Giao message lặp | Worker nhận lại cùng thông điệp | Chống trùng tại consumer/operation |
| Gửi tác động ngoài lại | Không nhận response từ cổng thanh toán | Operation ổn định, idempotency bên nhận và đối soát |

Một lớp không tự giải quyết tất cả lớp còn lại. Xóa dòng trùng trong bộ nhớ không bảo vệ hai request đến hai instance khác nhau.

### 2.2. Tách ID tương quan khỏi key ý định

Một hợp đồng có thể dùng:

- `clientItemId`: nhận diện lần xuất hiện để ghép response với dòng input; duy nhất trong một batch.
- `itemKey`: nhận diện cùng ý định của item khi retry, kể cả qua batch mới theo scope đã quy định.
- `batchKey`: nhận diện cùng request batch/manifest.
- `itemOperationId`: định danh server cho operation đã chấp nhận.
- Business key: định danh điều kiện duy nhất mà domain cần giữ, không phụ thuộc việc client đổi key.

Không dùng vị trí mảng làm item identity bền vững. Sau khi chia/gộp batch, vị trí có thể thay đổi dù ý định vẫn là một.

### 2.3. Chọn namespace rõ ràng

Ví dụ phạm vi item key của bài:

```text
tenant + actor principal + action + itemKey
```

Target và nội dung lệnh tham gia fingerprint. Nếu cùng key lại chỉ tới hồ sơ khác, đó là xung đột nội dung, không phải một operation mới được phép tạo.

Business key cho phiếu duyệt có thể là:

```text
tenant + approvalRoundId + reviewerIdentityId
```

Trong mô hình một người chỉ được ghi một quyết định có hiệu lực trong vòng đó, key này bảo vệ cả trường hợp đổi item key hoặc dùng account khác nhưng cùng danh tính người. Mô hình nhiều bước hoặc cho sửa quyết định cần thiết kế tương ứng, không sao chép constraint một cách máy móc.

## 3. Chọn chính sách xử lý duplicate theo nghiệp vụ

| Chính sách | Hành vi | Khi có thể phù hợp |
|---|---|---|
| Từ chối | Duplicate khiến request hoặc item nhận lỗi rõ ràng | Batch cần input không mơ hồ; thao tác không có ý nghĩa lặp |
| Gộp cùng ý định | Một canonical item được thực thi; các lần xuất hiện tham chiếu cùng kết quả | Cùng item key và cùng nội dung đã chuẩn hóa |
| Tổng hợp đại lượng | Gộp số lượng theo rule, rồi kiểm tra giới hạn tổng | Dòng hàng cùng sản phẩm nếu hợp đồng cho phép |
| Giữ các lệnh riêng | Mỗi item là một ý định độc lập hợp lệ | Nhiều giao dịch hoặc action khác nhau có căn cứ riêng |

### 3.1. Không dùng first-wins hoặc last-wins cho nội dung xung đột

Cùng item key nhưng một dòng duyệt hồ sơ A và dòng kia duyệt B không được âm thầm chọn một dòng. Tương tự khi basis, version hoặc ghi chú có ý nghĩa khác nhau.

Nếu chọn theo thứ tự tùy ý, proxy, parser, worker hoặc một lần reorder có thể làm kết quả khác đi. Từ chối xung đột trước khi thực thi là một hợp đồng rõ hơn.

### 3.2. Không deduplicate chỉ bằng entity ID

Cùng tài khoản có thể nhận hai khoản chuyển hợp lệ cho hai hóa đơn. Cùng payment có thể có nhiều refund một phần nếu policy cho phép và tổng vẫn trong capacity.

Ngược lại, hai item có target ID khác nhau có thể cùng trỏ tới một nghĩa vụ qua alias hoặc nguồn liên kết. Domain cần kiểm tra các quan hệ có thẩm quyền, không chỉ chuỗi ID thô.

Fingerprint giống nhau cũng không tự chứng minh đó là cùng ý định nếu nghiệp vụ cho phép lặp cùng giá trị. Cần item identity hoặc căn cứ nghiệp vụ phân biệt.

### 3.3. Không tổng hợp command tiền như tổng hợp quantity

Gộp hai dòng mua cùng SKU thành tổng số lượng có thể hợp lệ, nhưng vẫn phải giữ đơn vị, giá theo bậc và hạn mức theo sản phẩm.

Hai yêu cầu hoàn tiền không được tùy tiện cộng, bỏ một dòng hoặc coi là retry chỉ vì cùng payment. Phải biết chúng là cùng ý định hay hai ý định riêng và kiểm tra capacity cho tổng tác động được chấp nhận.

## 4. Chuẩn hóa và fingerprint đúng ý nghĩa

### 4.1. Chuẩn hóa trước khi so lệnh, theo hợp đồng

Những vấn đề cần xác định gồm:

- ID có phân biệt hoa/thường hay không.
- Field vắng mặt và giá trị mặc định có tương đương không.
- Null, chuỗi rỗng và khoảng trắng trong note có cùng nghĩa không.
- Số tiền, loại tiền, scale và đơn vị được biểu diễn thế nào.
- Thứ tự mảng có mang ý nghĩa nghiệp vụ không.

Không lowercase mọi ID mờ hoặc sắp xếp mọi array nếu cách đó làm thay đổi nghĩa. Không dùng dữ liệu hiển thị như tên người để nhận diện reviewer.

### 4.2. Fingerprint chỉ bao phủ ý định ổn định

Fingerprint item nên gồm target, action và đầu vào có ý nghĩa theo contract. Không thêm timestamp xử lý hiện tại hay một role snapshot thay đổi ở mỗi retry rồi khiến cùng lệnh bị coi là khác nội dung.

Credential có thể đổi giữa các lần gọi; authorization vẫn phải kiểm tra hiện tại, nhưng không nên lưu token thô trong fingerprint/log như dữ liệu nghiệp vụ.

Fingerprint do server tính từ dữ liệu đã parse/chuẩn hóa. Một hash client tự khai không thay kiểm tra nội dung thực tế.

### 4.3. Manifest batch và fingerprint item là hai hợp đồng

Mẫu của bài coi thứ tự input và `clientItemId` là một phần manifest batch. Đổi thứ tự hoặc tập item với cùng batch key được xem là đổi nội dung.

Fingerprint item không chứa vị trí mảng hoặc batch key. Vì vậy, cùng item key/nội dung có thể được nhận diện khi client gửi lại trong một batch mới.

Một dự án có thể chọn manifest không phụ thuộc thứ tự, nhưng cần định nghĩa cách ghép response ổn định. Không để hai lớp tự chọn hai cách hiểu.

## 5. Ví dụ hợp đồng batch duyệt

### 5.1. Input có ID lần xuất hiện và key ý định riêng

```http
POST /tenants/{tenantId}/expense-requests/batch-approval-decisions
Content-Type: application/json
Idempotency-Key: batch-request-key

{
  "items": [
    {
      "clientItemId": "line-1",
      "itemKey": "approval-001",
      "expenseId": "expense-17",
      "approvalRoundId": "round-4",
      "basisPackageId": "basis-7",
      "expectedVersion": 12
    },
    {
      "clientItemId": "line-2",
      "itemKey": "approval-001",
      "expenseId": "expense-17",
      "approvalRoundId": "round-4",
      "basisPackageId": "basis-7",
      "expectedVersion": 12
    },
    {
      "clientItemId": "line-3",
      "itemKey": "approval-002",
      "expenseId": "expense-18",
      "approvalRoundId": "round-5",
      "basisPackageId": "basis-8",
      "expectedVersion": 9
    }
  ]
}
```

Mẫu chọn các quy tắc:

1. `clientItemId` lặp là lỗi cấu trúc batch.
2. Cùng item key và cùng nội dung chuẩn hóa được gộp thành một canonical item.
3. Cùng item key khác nội dung là xung đột bị phát hiện trước thực thi.
4. Khác item key vẫn phải qua uniqueness và policy nghiệp vụ.
5. Tenant và actor lấy từ ngữ cảnh đã xác minh, không được thay bởi từng item.

Đây là lựa chọn hợp đồng minh họa, không phải hành vi bắt buộc của mọi batch API.

### 5.2. Response giữ thông tin từng lần xuất hiện

Với mô hình từng phần, một kết quả có thể là:

```json
{
  "batchOperationId": "batch-op-91",
  "inputItemCount": 3,
  "canonicalItemCount": 2,
  "results": [
    {
      "clientItemId": "line-1",
      "outcome": "APPLIED",
      "decisionId": "decision-81"
    },
    {
      "clientItemId": "line-2",
      "outcome": "COALESCED",
      "canonicalItemId": "line-1",
      "decisionId": "decision-81"
    },
    {
      "clientItemId": "line-3",
      "outcome": "REJECTED",
      "code": "RESOURCE_NOT_AVAILABLE"
    }
  ]
}
```

Hai dòng đầu chỉ có một decision. Không dùng số dòng success để tăng quorum hoặc tính số tác động đã tạo.

Nếu trả receipt cũ khi replay cả batch, trạng thái `APPLIED` trong receipt mô tả lần thực thi gốc, không có nghĩa mỗi lần nhận response lại có tác động mới. Có thể bổ sung metadata replay theo hợp đồng; không cộng lại các response để thống kê operation nghiệp vụ.

### 5.3. Các outcome cần tách biệt

Phân biệt đã áp dụng, dùng lại kết quả, gộp cùng ý định, đang xử lý, xung đột key, đã có quyết định theo business key và bị từ chối quyền/domain.

Không báo mọi trường hợp là `SUCCESS` rồi buộc client đoán item nào đã tạo tác động. Không trả decision hoặc note nhạy cảm chỉ để giải thích duplicate ngoài phạm vi người gọi được xem.

## 6. Minh họa Java: phát hiện trùng trong một request

Đoạn sau minh họa bước tiền xử lý. Các kiểu như `NormalizedApproval` và `CanonicalItem` là hợp đồng của ứng dụng, không phải thư viện có sẵn.

```java
CanonicalBatch canonicalize(
        ActorContext actor,
        List<ApprovalItemInput> items) {

    batchRules.requireAllowedInputSize(items);
    Set<String> occurrenceIds = new HashSet<>();
    Map<ItemKey, CanonicalItem> canonical = new LinkedHashMap<>();

    for (ApprovalItemInput input : items) {
        batchRules.validateItemShape(input);

        if (!occurrenceIds.add(input.clientItemId())) {
            throw new BatchInputException("DUPLICATE_CLIENT_ITEM_ID");
        }

        ItemKey key = new ItemKey(
                actor.tenantId(), actor.principalId(),
                "RECORD_EXPENSE_APPROVAL", input.itemKey());

        NormalizedApproval command = normalizer.normalizeApproval(input);
        CanonicalItem previous = canonical.get(key);

        if (previous == null) {
            canonical.put(key, CanonicalItem.first(
                    key, command, input.clientItemId()));
        } else if (!previous.command().equals(command)) {
            throw new BatchInputException("ITEM_KEY_PAYLOAD_CONFLICT");
        } else {
            canonical.put(key, previous.withOccurrence(input.clientItemId()));
        }
    }

    return CanonicalBatch.freeze(canonical.values());
}
```

Các điều kiện cần hiểu:

- Size được kiểm tra trên toàn bộ số lần xuất hiện, không đợi gộp còn ít item mới giới hạn tài nguyên.
- `normalizeApproval` không đưa `clientItemId` hay vị trí vào ý định nghiệp vụ, nhưng giữ target, basis/vòng, version và các field có ý nghĩa.
- `equals` của command chuẩn hóa phải phản ánh contract, không so object identity hoặc bỏ sót field đặc quyền.
- Ngữ cảnh tenant/actor không do từng item tự khai.
- Bước này không thực hiện approval và không tải/tiết lộ hồ sơ ngoài quyền.
- Các item chỉ được xử lý sau khi tiền kiểm tra cấu trúc hoàn tất theo mô hình đã chọn.

Map trong bộ nhớ chỉ ngăn trùng trong lần gọi này. Nó không chứng minh chống trùng giữa các request, process hoặc các lần khởi động lại.

## 7. Chống trùng bền vững bằng ledger và invariant

### 7.1. Tách ba hàng rào

| Hàng rào | Điều bảo vệ | Điều chưa tự bảo vệ |
|---|---|---|
| Canonicalization trong request | Trùng/xung đột ngay trong manifest | Hai batch đồng thời hoặc retry sau crash |
| Item idempotency ledger | Cùng key và ý định qua nhiều lần gọi | Client đổi key để thực hiện cùng điều domain cấm |
| Business constraint/ledger | Số lần thực hiện hợp lệ của nghĩa vụ | Quyền hiện tại hoặc khả năng được xem kết quả |

Ví dụ ràng buộc theo mô hình của bài:

```sql
UNIQUE (tenant_id, actor_principal_id, action_name, item_key)

UNIQUE (tenant_id, approval_round_id, reviewer_identity_id)
```

Ràng buộc thứ nhất đi cùng fingerprint đã lưu; key tồn tại với payload khác không được ghi đè. Ràng buộc thứ hai ngăn cùng reviewer được tính nhiều lần trong vòng theo policy đã chọn.

Hai account có thể có ledger item riêng nhưng cùng reviewer identity vẫn phải bị giới hạn bởi business rule. Ngược lại, cùng chuỗi item key ở hai tenant không được làm trả nhầm kết quả.

### 7.2. Đơn vị local transaction cho canonical item

Với xử lý ngắn trong một cơ sở dữ liệu, một luồng có thể là:

```text
bắt đầu transaction
→ nhận diện/ghi claim item key có uniqueness
→ nếu có kết quả: kiểm tra quyền nhận và trả replay theo contract
→ nếu key khác fingerprint: xung đột, không thực hiện
→ nạp/khóa hồ sơ đúng tenant
→ kiểm tra quyền, maker–checker, basis, vòng, trạng thái, version
→ ghi decision và cập nhật tiến trình có điều kiện
→ ghi kết quả item, audit thành công và outbox bắt buộc
→ commit
```

Trong mô hình này, claim, tác động DB và kết quả cần nguyên tử. Không commit ledger `SUCCEEDED` trước khi decision thật commit, hoặc commit decision rồi bỏ mất khả năng nhận diện retry.

Nếu gặp business duplicate qua key khác, contract có thể trả `ALREADY_RECORDED` sau kiểm tra quyền nhận kết quả, hoặc trả conflict. Không ghi thêm một phiếu, không giả rằng note mới đã sửa quyết định cũ và không tăng quorum.

### 7.3. Không chỉ SELECT rồi INSERT không bảo vệ cạnh tranh

Hai transaction đều có thể thấy chưa có ledger/decision rồi cùng ghi. Cần uniqueness, khóa hoặc cơ chế nguyên tử phù hợp, và xử lý kết quả cạnh tranh như một phần contract.

Khóa cache trong một instance không bảo vệ instance khác. Khóa theo item key cũng không tự bảo vệ hai key khác nhau cùng tác động một hồ sơ hoặc reviewer identity.

### 7.4. Thứ tự khóa và deadlock

Batch nhiều đối tượng có thể khóa chéo nhau. Có thể chuẩn hóa thứ tự khóa trên các tài nguyên nghiệp vụ phù hợp và giữ transaction gọn theo thiết kế.

Retry sau deadlock không được bỏ authorization/guards hoặc tự chấp nhận basis mới. Vẫn là cùng ý định cần được đánh giá đúng sau rollback, không phải lý do sinh thêm tác động với key mới.

## 8. Batch nguyên tử và batch từng phần

### 8.1. Toàn bộ hoặc không phần nào

Nếu contract yêu cầu nguyên tử, các canonical item cùng thay đổi phải nằm trong phạm vi có thể commit/rollback đúng bảo đảm. Không dùng transaction riêng cho từng item rồi báo ở cuối như thể toàn batch đã rollback.

Kết quả item `SUCCEEDED` không được tồn tại như sự thật độc lập nếu outer transaction đã rollback toàn bộ. Outbox cần cùng ranh giới; không gửi tác động ngoài hệ thống trong lúc vẫn hứa có thể rollback tất cả.

Nếu batch đi qua nhiều cơ sở dữ liệu hoặc hệ thống ngoài, phải mô tả workflow/compensation thực tế. Một request HTTP duy nhất không tạo transaction nguyên tử toàn cục.

### 8.2. Xử lý từng phần

Mỗi canonical item có kết quả và transaction phù hợp. Những lần xuất hiện đã gộp tham chiếu cùng outcome, không chạy lại vì chúng nằm ở vị trí khác.

Khi client gửi lại phần chưa rõ, giữ item key/nội dung nếu vẫn là cùng ý định. Batch mới có thể có batch key mới, nhưng không được làm item thành lệnh mới chỉ vì đổi manifest.

Nếu sửa nội dung sau conflict, xác định đó là ý định mới theo hợp đồng. Không ghi đè payload đã gắn với item key cũ.

### 8.3. Một batch có thể chồng lấn batch khác

Batch A chứa E1, E2; batch B chứa E2, E3. Chỉ batch-level idempotency sẽ không bảo vệ E2 nếu hai batch có key khác nhau.

Item ledger và business invariant phải làm E2 được xử lý đúng số lần. Outcome của E1/E3 vẫn theo chế độ nguyên tử/từng phần đã chọn, không bị suy từ một cờ chung.

### 8.4. Tính quota theo đúng đại lượng

Giới hạn kích thước request thường tính toàn bộ input để chống quá tải. Giới hạn tiền, quyền lợi hoặc số quyết định cần dựa trên các tác động logic được chấp nhận theo rule.

Không dùng số dòng response thành công để tính số người duyệt. Không loại nhầm các giao dịch hợp lệ riêng biệt khỏi một giới hạn tổng chỉ vì chúng có cùng target hoặc số tiền.

## 9. Async, crash và tác động bên ngoài

### 9.1. IN_PROGRESS không có nghĩa được chạy lại ngay

Với job dài, có thể commit claim trước khi worker thực hiện. Khi đó cần state, lease hoặc version xử lý phù hợp, chẳng hạn đang xử lý, thành công, thất bại xác định hoặc chưa rõ kết quả.

Đây là mô hình khác với transaction local ngắn ở phần 7. Claim tồn tại nhưng worker ngừng hoạt động không tự chứng minh chưa có tác động.

### 9.2. Lease hết hạn không xóa tác động của worker cũ

Một worker có thể gửi lệnh rồi bị treo. Worker mới nhận lease, trong khi worker cũ vẫn có thể chạy tiếp.

Fencing/version giúp ngăn ghi kết quả cũ trong phạm vi nơi nó được kiểm tra. Nó không tự ngăn hai lời gọi mạng nếu bên nhận không kiểm tra fencing hoặc không có cơ chế chống trùng phù hợp.

Giữ operation/attempt ID ổn định cho cùng lần phát thực thi theo hợp đồng. Không tạo attempt mới chỉ vì lease cũ hết hạn trong khi kết quả bên ngoài chưa rõ.

### 9.3. Outbox và consumer cần chống trùng theo nghĩa nghiệp vụ

Outbox giúp không mất ý định phát sau commit, nhưng thông điệp có thể được gửi lại. Consumer chỉ nhớ `messageId` có thể chưa đủ nếu hai message ID khác nhau mang cùng một nghĩa vụ.

Đối chiếu tenant, aggregate, operation và business key cần thiết. Không để hai event “đã ghi phiếu” cùng trỏ một decision bị tính thành hai phiếu độc lập.

### 9.4. Timeout ngoài hệ thống là trạng thái chưa rõ

Nếu cổng hoàn tiền đã xử lý nhưng response bị mất, tạo item key hoặc operation mới có thể hoàn hai lần. Cần tra cứu/đối soát cùng operation hoặc gửi lại với định danh chống trùng được bên nhận hỗ trợ.

Không mặc định exception mạng là `FAILED_FINAL`. Chỉ cho phép một attempt mới khi có đủ căn cứ theo hợp đồng tích hợp và domain.

### 9.5. Hết hạn cache/ledger không có nghĩa chưa từng thực hiện

Retention của idempotency key phải phù hợp vòng đời retry và nguy cơ gửi lại. Nếu đã dọn receipt, business ledger/constraint vẫn có thể cần giữ dấu vết để ngăn tác động trùng.

Không xóa mọi căn cứ rồi tuyên bố cùng key cũ chắc chắn là ý định mới. API cần nêu giới hạn bảo đảm khi dữ liệu chống trùng đã hết vòng đời.

## 10. Authorization, dữ liệu kết quả và quan sát

### 10.1. Duplicate không miễn kiểm tra quyền

Các canonical item cần authorization trên đúng đối tượng. Gộp những lần xuất hiện thực sự cùng lệnh trong cùng ngữ cảnh không có nghĩa được kiểm tra item đầu rồi cho toàn batch đi qua.

Khi trả replay hoặc `ALREADY_RECORDED`, kiểm tra quyền nhận kết quả hiện tại. Một item key, batch ID hoặc decision ID không phải credential.

Nếu account/ownership thay đổi, không tự chia sẻ mọi receipt giữa các ngữ cảnh chỉ vì chúng được liên kết cùng người. Mô hình quyền truy cập quyết định điều đó.

### 10.2. Không lộ đối tượng qua thông báo duplicate

Phản hồi như “hồ sơ thuộc tenant B đã được người C duyệt” có thể làm lộ dữ liệu. Với item ngoài scope, dùng lỗi theo chính sách tiết lộ mà không trả baseline riêng tư.

Một batch status endpoint cũng cần quyền. Không coi batch ID khó đoán là đủ để tải toàn bộ kết quả hoặc note của các item.

### 10.3. Đếm đúng các lớp trong metrics/audit

Phân biệt:

```text
số lần xuất hiện input
số canonical item
số replay/coalesced/conflict
số decision hoặc operation nghiệp vụ riêng biệt
số lần giao message hoặc gọi mạng
```

Các con số không thay thế nhau. Để audit một item, cần nối được batch occurrence, canonical operation, business decision và những lần truyền liên quan.

Ghi actor thực tế, tenant, action, fingerprint/reference cần thiết và outcome. Không log token, credential hoặc nguyên payload nhạy cảm chỉ để phân tích trùng.

### 10.4. Giới hạn tài nguyên trước và sau dedup

Giới hạn kích thước body, số item, độ dài key, cấu trúc lồng nhau và chi phí tra cứu. Một triệu dòng giống nhau vẫn có thể gây quá tải dù cuối cùng chỉ còn một canonical item.

Nếu dùng fingerprint/hash, cần biểu diễn ổn định và cơ chế đủ tin cậy cho mục đích đó. Không để dữ liệu do người gọi khai trở thành bằng chứng đã kiểm tra hoặc quyền vượt giới hạn.

## 11. Kiểm thử batch duplicate handling

| Tình huống | Kỳ vọng |
|---|---|
| Lặp `clientItemId` trong manifest | Lỗi theo hợp đồng trước thực thi |
| Cùng item key, cùng payload, khác vị trí | Một canonical execution; kết quả liên kết rõ cho các lần xuất hiện |
| Cùng key nhưng khác target/basis/version/nội dung có ý nghĩa | Conflict, không first-wins/last-wins ngầm |
| Khác key nhưng cùng reviewer/vòng bị giới hạn | Không thêm người/phiếu độc lập trái policy |
| Hai giao dịch hợp lệ giống số tiền/người nhận nhưng khác nghĩa vụ | Không bị xóa nhầm chỉ vì fingerprint giá trị giống nhau |
| Cùng sản phẩm chia nhiều dòng | Tổng hợp hoặc giữ dòng đúng contract, không vượt giới hạn tổng |
| Retry toàn batch sau commit nhưng mất response | Không tạo thêm tác động; receipt đúng ý nghĩa lịch sử |
| Retry subset trong batch mới với item key cũ | Nhận diện được kết quả item theo scope đã định |
| Hai batch khác key chồng lấn cùng item/ý định | Item ledger/business invariant bảo vệ ngoài batch scope |
| Hai instance cùng xử lý một key chưa có | Constraint/giao thức nguyên tử ngăn thực thi lặp trái hợp đồng |
| Atomic batch lỗi ở item cuối | Không để success ledger, decision hoặc outbox phần đầu commit trái cam kết |
| Batch từng phần có item thất bại | Item đã thành công không bị chạy lại khi retry phần còn lại |
| Worker crash sau tác động ngoài nhưng trước lưu kết quả | Không tạo attempt mới khi kết quả cũ chưa được giải quyết |
| Message lặp hoặc message ID khác cùng nghĩa vụ | Không nhân đôi decision/operation nghiệp vụ |
| Item key trùng giữa tenant/chủ thể khác | Không trả nhầm receipt hoặc chặn nhau ngoài contract |
| Replay sau khi mất quyền xem | Không lộ kết quả cũ vượt quyền hiện tại |
| Idempotency receipt hết retention | Hành vi đúng giới hạn đã công bố, không quên invariant còn phải giữ |
| Batch hợp lệ không có trùng hoặc có các ý định riêng hợp lệ | Được xử lý, không chặn quá mức |

### 11.1. Kiểm tra dữ liệu và tác động

Đếm decision bằng định danh/danh tính có hiệu lực, không chỉ số kết quả `APPLIED`. Với quorum, kiểm tra duplicate không biến một người thành nhiều người.

Với tiền, quan sát logical operation, ledger và cổng tác động. Nhiều lần truyền cùng operation có chống trùng không tự là nhiều khoản chi; hai operation khác nhau cho cùng nghĩa vụ bị cấm mới là vấn đề cần phát hiện.

### 11.2. Kiểm thử canonicalization theo hợp đồng

Thử null/vắng mặt, scale tiền, khoảng trắng, ID phân biệt hoa/thường và thứ tự manifest. Kỳ vọng phải dựa trên định nghĩa domain, không tự giả định mọi biểu diễn trông giống nhau đều tương đương.

Đổi các field chỉ để tương quan không được thay fingerprint ý định nếu contract đã loại chúng. Đổi target hoặc basis phải được phát hiện nếu dùng lại cùng item key.

### 11.3. Race và lỗi có điều khiển

Dùng hai transaction/kết nối riêng, điểm đồng bộ và timeout hữu hạn để tái hiện cùng đọc “chưa có” rồi cùng ghi. Mock một map local không chứng minh uniqueness hoặc rollback thực tế.

Chèn lỗi trước commit, sau commit trước response, sau gửi message và sau bên ngoài thực hiện trước khi worker nhận kết quả. Kiểm tra có thể tiếp tục đúng operation mà không thêm tác động trái phép.

## 12. Tự rà soát hợp đồng xử lý trùng

Trước khi triển khai một batch command, hãy trả lời:

1. “Trùng” nghĩa là cùng lần xuất hiện, key ý định hay nghĩa vụ nghiệp vụ?
2. ID tương quan, batch key, item key và business key có được tách rõ không?
3. Canonicalization/fingerprint có giữ đầy đủ ý nghĩa và tránh gộp nhầm giao dịch hợp lệ không?
4. Cùng key khác payload được từ chối rõ hay bị chọn một dòng ngầm?
5. Retry item qua batch mới có còn được nhận diện không?
6. Constraint/transaction nào bảo vệ hai instance và hai key khác nhau cùng tác động một nghĩa vụ?
7. Chế độ nguyên tử/từng phần có khớp với ledger, outbox và response không?
8. Crash, lease hết hạn và timeout ngoài hệ thống có thể làm tạo attempt mới quá sớm không?
9. Replay/result query có kiểm tra quyền hiện tại và tránh rò rỉ dữ liệu không?
10. Metrics và test có đếm tác động nghiệp vụ riêng biệt thay vì số dòng hay số lần gửi không?

Xử lý duplicate đúng nghĩa là giữ được số lần thực hiện mà nghiệp vụ cho phép qua mọi lần xuất hiện và gửi lại. Việc xóa phần tử trùng trong một mảng chỉ là bước nhỏ; quyền, căn cứ, transaction và định danh tác động phải tiếp tục bảo vệ cùng bất biến ở các lớp phía sau.
