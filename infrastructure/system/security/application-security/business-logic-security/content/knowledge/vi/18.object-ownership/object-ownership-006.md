# Lịch sử quyền sở hữu đối tượng (Ownership history)

Một cột owner hiện tại giúp xác định ai đang sở hữu đối tượng, nhưng không đủ để giải thích đối tượng đã đi qua những ai hoặc vì sao một hành động trước đây được chấp nhận.

Ví dụ, A lập đơn mua hàng rồi chuyển cho B. Sau đó B chuyển tiếp cho C. Nếu hệ thống chỉ còn `ownerId=C`, việc điều tra hành động của A và B sẽ thiếu ngữ cảnh. Nếu hệ thống lại cho bất kỳ người từng sở hữu được sửa đơn, lịch sử trở thành một đường cấp quyền ngoài ý muốn.

Bài học thuộc chương **Object Ownership** trong bảo mật logic nghiệp vụ. Trọng tâm là ghi nhận, bảo vệ và sử dụng lịch sử ownership để giải thích thay đổi mà vẫn giữ đúng quyền hiện tại, tenant, state machine, phê duyệt và transaction.

## 1. Phân biệt ownership hiện tại, lịch sử và nguồn gốc

| Dữ kiện | Câu hỏi nó trả lời |
|---|---|
| Chủ sở hữu hiện tại | Ai đang sở hữu đối tượng theo nguồn có thẩm quyền? |
| Lịch sử ownership | Quan hệ sở hữu đã thay đổi từ ai sang ai và theo căn cứ nào? |
| Người tạo hoặc người lập | Ai thực sự tạo bản ghi hoặc chuẩn bị nội dung? |
| Người được giao xử lý | Ai đang nhận một công việc cụ thể? |
| Lịch sử quyết định | Ai đã gửi, duyệt, từ chối hoặc thực thi trên nội dung nào? |

Các quan hệ có thể trùng nhưng không đồng nhất. Chuyển owner không được tự viết lại người tạo hoặc làm mất việc một người đã lập nội dung.

### 1.1. Ví dụ ba lần sở hữu

```text
Giai đoạn 1: A sở hữu đơn, ownershipEpoch = 1
Giai đoạn 2: B sở hữu đơn, ownershipEpoch = 2
Giai đoạn 3: C sở hữu đơn, ownershipEpoch = 3

createdBy vẫn là A
```

A từng sở hữu không tự tạo quyền hiện tại. B từng được phép sửa cũng không chứng minh mọi thay đổi sau này của B hợp lệ.

Khi xét một hành động quá khứ, cần nhìn ownership tại mốc liên quan cùng quyền, trạng thái, nội dung và chính sách đã được dùng. Lịch sử ownership là một nguồn dữ kiện, không phải toàn bộ quyết định phân quyền.

### 1.2. Giữ dấu vết phân tách nhiệm vụ

Nếu policy cấm người lập tự duyệt, chuyển owner từ A sang B không làm A trở thành người độc lập với nội dung do A lập.

Tương tự, chuyển lại cho A không xóa các hành động A đã làm trước đó. Các quy tắc liên quan cần dùng đúng chủ thể và lịch sử hành động, thay vì chỉ nhìn owner mới nhất.

Không coi việc thay owner như một cách đặt lại mọi phê duyệt, trách nhiệm hoặc quan hệ xung đột mà không có chính sách rõ.

## 2. Các bất biến của lịch sử ownership

Một thiết kế cần bảo vệ:

1. Mỗi thay đổi owner được chấp nhận có một bản ghi liên kết với đúng tenant và đối tượng.
2. Owner trước của lần chuyển phải khớp trạng thái được bảo vệ tại lúc chuyển.
3. Owner sau phải là chủ thể được phép nhận theo chính sách.
4. Thứ tự thay đổi có thể xác định trong phạm vi đối tượng.
5. Trạng thái owner hiện tại và bản ghi chuyển tương ứng được lưu nhất quán.
6. Một lần chuyển không xóa hoặc viết lại những quan hệ đã xảy ra.
7. Retry không tạo thêm một lần chuyển nghiệp vụ.
8. Lịch sử không tự cấp quyền hiện tại cho người từng sở hữu.
9. Người đọc, xuất hoặc sửa chữa lịch sử cần đúng thẩm quyền.
10. Dữ liệu không biết không được tự điền thành một lịch sử có vẻ đầy đủ.

Với mô hình một owner tại một thời điểm, cần tránh hai owner cùng có hiệu lực cho cùng phạm vi. Nếu nghiệp vụ thật sự hỗ trợ nhiều owner, phải mô hình hóa tập quan hệ và quy tắc quyền tương ứng, không diễn giải đó là hai lần chuyển đơn lẻ mâu thuẫn.

### 2.1. Scope của ownership cần có kiểu

Một quan hệ có thể gắn với:

```text
tenant + objectType + objectId + ownershipKind
```

Ví dụ, chủ sở hữu nghiệp vụ và đơn vị chịu chi phí có thể là hai quan hệ khác nhau. Chuyển đơn vị chịu chi phí không mặc nhiên là chuyển mọi quyền sở hữu.

Owner cũng có thể là người hoặc nhóm. Nên lưu loại chủ thể cùng định danh theo nguồn có thẩm quyền, không trộn ID nhóm với ID người trong một chuỗi không rõ nghĩa.

## 3. Mô hình dữ liệu: trạng thái hiện tại và sự kiện chuyển

Một lựa chọn là giữ trạng thái hiện tại trên đối tượng và ghi sự kiện thay đổi trong cùng transaction.

```text
BusinessObject:
    tenantId
    objectType
    objectId
    currentOwnerType
    currentOwnerId
    ownershipEpoch
    rowVersion
    contentRevision
    createdBy
```

Một sự kiện chuyển có thể gồm:

```text
OwnershipChanged:
    eventId
    tenantId
    objectType
    objectId
    ownershipKind
    fromOwnerType
    fromOwnerId
    toOwnerType
    toOwnerId
    fromEpoch
    toEpoch
    transferId
    actorId
    representedSubjectId nếu có
    authorityContextRef
    reasonCode hoặc tham chiếu lý do
    effectiveAt theo quy ước
    recordedAt
    policyVersion
    contentRevisionAtTransfer
```

Không phải hệ thống nào cũng cần đúng schema này. Điều quan trọng là giữ được nguồn, thứ tự và mối liên hệ với quyết định chuyển.

### 3.1. Mỗi loại version có mục đích riêng

| Giá trị | Mục đích |
|---|---|
| rowVersion | Phát hiện lần ghi cạnh tranh trên đối tượng |
| contentRevision | Nhận diện nội dung được xét duyệt hoặc thực thi |
| ownershipEpoch | Phân biệt các thế hệ ownership, kể cả khi quay lại cùng owner |
| policyVersion | Nhận diện quy tắc dùng cho một quyết định |
| eventId | Nhận diện một sự kiện để truyền và khử trùng lặp |

Sửa mô tả có thể tăng rowVersion mà không đổi owner. Chuyển owner có thể tăng ownershipEpoch mà không đổi giá trị nội dung được duyệt, nếu chính sách cho phép.

Tuy nhiên, nếu owner ảnh hưởng kế hoạch hoặc thẩm quyền phê duyệt, việc chuyển phải xử lý các ảnh hưởng đó theo quy trình; các cột version riêng không tự làm bất biến đúng.

### 3.2. Khoảng sở hữu để truy vấn

Từ nguồn sự kiện có thứ tự, có thể dựng các khoảng:

| Khoảng hiệu lực | Owner | Epoch |
|---|---|---|
| [t0, t1) | A | 1 |
| [t1, t2) | B | 2 |
| [t2, chưa có mốc kết thúc) | C | 3 |

Quy ước nửa mở giúp tại đúng t1 không đồng thời tính cả A và B là owner của quan hệ đơn.

Nếu dùng bảng khoảng làm projection, việc đóng khoảng trước có thể là một cập nhật projection có kiểm soát. Điều đó khác với sửa tùy ý sự kiện nguồn đã ghi nhận. Cần phân biệt rõ nguồn lịch sử với biểu diễn dẫn xuất.

Khoảng trống, chồng lấn hoặc thiếu mốc khởi tạo phải được xử lý theo mô hình. Không tự chọn “owner gần nhất” khi dữ liệu không đủ chứng minh.

## 4. Thời gian hiệu lực và thời gian ghi nhận

Có hai câu hỏi khác nhau:

```text
Ai được mô hình xác định là owner tại thời điểm T?

Tại thời điểm K, hệ thống đã ghi nhận thông tin gì
về owner ở thời điểm T?
```

Thời gian hiệu lực biểu thị quan hệ có ý nghĩa từ mốc nào. Thời gian ghi nhận cho biết thông tin được hệ thống tiếp nhận hoặc lưu lúc nào. Hai mốc có thể khác trong nhập liệu, sửa sai hoặc tích hợp đến muộn.

### 4.1. Thứ tự transaction quan trọng hơn timestamp tùy ý

Hai event có thể cùng timestamp theo độ phân giải lưu trữ hoặc được các node đóng dấu khác nhau. Nên dùng ownershipEpoch hoặc nguồn thứ tự có thẩm quyền để xác định diễn tiến của một đối tượng.

Một timestamp do ứng dụng lấy trước commit không tự chứng minh owner mới đã có thể được sử dụng tại mọi thời điểm trước khi commit. Nếu cần kết luận chính xác tới một mốc thời gian, cơ chế ghi và truy vấn phải cung cấp ngữ nghĩa đủ chặt.

Khi điều tra sát biên chuyển, cần liên kết hành động với epoch, version và mốc quyết định của transaction. Không kết luận vi phạm chỉ bằng cách so hai chuỗi giờ có độ chính xác hoặc nguồn khác nhau.

### 4.2. Đề nghị chuyển trong tương lai chưa phải lịch sử đã chuyển

Một đề nghị được ghi lúc 09:00, dự kiến chuyển lúc 12:00 không tự chứng minh việc chuyển đã xảy ra.

Trong mô hình chuyển tức thời của bài, chỉ khi giao dịch chuyển được chấp nhận và commit thì trạng thái hiện tại mới đổi. Nếu tác vụ dự kiến chạy muộn, cần giữ mốc dự kiến riêng và ghi đúng mốc thực thi theo quy ước.

Nếu nghiệp vụ yêu cầu ownership tự có hiệu lực đúng một mốc lịch dù job chưa chạy, cần một mô hình thời gian có thể thực thi điều đó nhất quán ở mọi đường đọc và ghi. Không kết hợp một bảng hiện tại chưa đổi với một lịch sử nói đã đổi mà không có nguồn thẩm quyền rõ.

### 4.3. Sửa thông tin quá khứ không tự cấp quyền hồi tố

Một chỉnh sửa nói rằng B đáng lẽ phải được ghi là owner từ hôm trước không chứng minh B đã có quyền trên hệ thống tại mọi thao tác hôm trước.

Cần giữ được thông tin trước chỉnh sửa, căn cứ, người sửa và cách hiểu lịch sử sau sửa. Đánh giá một quyết định quá khứ còn phụ thuộc những dữ kiện mà hệ thống thực sự dùng tại mốc quyết định đó.

Không viết lại effectiveAt để hợp thức hóa một hành động đã bị chặn hoặc một lần duyệt sai thẩm quyền.

## 5. Ghi thay đổi owner và lịch sử trong cùng transaction

Trong ví dụ đơn mua hàng, hành động chuyển chỉ được chấp nhận khi trạng thái cho phép, người gọi có quyền chuyển và người nhận đủ điều kiện trong tenant.

Luồng điển hình:

1. Xác thực người gọi và tenant.
2. Tải đối tượng theo đúng phạm vi, áp dụng kiểm soát cạnh tranh.
3. Nhận diện retry theo hợp đồng và kiểm tra quyền đọc biên nhận nếu trả kết quả cũ.
4. Với lệnh mới, kiểm tra quyền chuyển, trạng thái, version và epoch.
5. Xác minh người nhận cùng các quyết định hoặc chấp nhận bắt buộc.
6. Chụp owner trước, thực hiện thay đổi và tạo sự kiện từ dữ liệu máy chủ.
7. Lưu đối tượng, sự kiện, kết quả lệnh và outbox trong cùng transaction cục bộ.
8. Commit rồi mới công bố thành công.

Nếu ghi lịch sử thất bại, không được để owner đã đổi mà không có dấu vết theo hợp đồng. Nếu cập nhật owner thất bại, không được giữ một sự kiện báo đã chuyển thành công.

### 5.1. Ví dụ Java

Đoạn mã là mã giả theo cú pháp Java. Các cổng transaction, phân quyền, lịch sử và idempotency cần triển khai theo hợp đồng thực tế.

```java
TransferReceipt transferOwnership(
        TransferCommand command,
        ActorContext actor) {

    return transactions.required(() -> {
        memberships.requireActiveTenantAccess(actor);

        PurchaseRequest request = requests
                .findForUpdate(actor.tenantId(), command.requestId())
                .orElseThrow(ResourceNotFound::new);

        CommandClaim claim = commandLog.claimOrReplay(
                actor, "TRANSFER_PURCHASE_REQUEST_OWNERSHIP",
                command.idempotencyKey(), fingerprintOf(command));

        if (claim.isCompletedReplay()) {
            TransferReceipt receipt = claim.savedTransferReceipt();
            receiptPolicy.requireMayRead(actor, receipt);
            return receipt;
        }

        authorizer.requireMayTransferOwnership(actor, request);

        request.requireVersion(command.expectedVersion());
        request.requireOwnershipEpoch(command.expectedOwnershipEpoch());
        request.requireState(RequestState.DRAFT);

        OwnerReference recipient = owners.resolveEligiblePerson(
                actor.tenantId(), command.recipientId());

        transferPolicy.requireAllowed(
                actor, request, recipient, command.transferIntentId());

        if (request.currentOwner().equals(recipient)) {
            throw new BusinessRuleViolation("ALREADY_CURRENT_OWNER");
        }

        OwnershipSnapshot before = request.immutableOwnershipSnapshot();

        request.transferTo(recipient);
        request.advanceOwnershipEpoch();

        OwnershipChanged event = ownershipEventsFactory.changed(
                eventIds.newId(),
                claim.commandId(),
                before,
                request.immutableOwnershipSnapshot(),
                actor,
                command.reason(),
                transferPolicy.currentPolicyReference(),
                clock.instant());

        int changed = requests.saveOwnershipIfUnchanged(request, before);

        if (changed != 1) {
            throw new ConcurrentChange();
        }

        ownershipEvents.append(event);
        outbox.appendOwnershipChanged(event.id());

        TransferReceipt receipt = TransferReceipt.completed(
                event.transferId(), request.ownershipEpoch());

        commandLog.complete(claim, receipt);
        return receipt;
    });
}
```

Các hợp đồng cần có:

- `actor` từ ngữ cảnh xác thực và ánh xạ danh tính đáng tin cậy, không từ các trường tự khai.
- Phân quyền mới dựa trên owner hiện tại và quyền chuyển cụ thể; không tự cho phép chỉ vì caller từng xuất hiện trong lịch sử.
- `resolveEligiblePerson` kiểm tra người nhận theo tenant và chính sách, không chấp nhận một ID toàn cục chưa xác minh.
- `transferIntentId`, nếu được yêu cầu, phải trỏ tới đề nghị và chấp nhận đúng đối tượng, owner nguồn, người nhận, epoch và phạm vi. Sự tồn tại của một đề nghị bất kỳ không đủ.
- Snapshot trước là bất biến. Nó không giữ tham chiếu mutable có thể bị đổi cùng entity.
- `saveOwnershipIfUnchanged` bảo vệ tenant, owner trước, epoch, version và trạng thái liên quan.
- Đối tượng, sự kiện, outbox và command log dùng cùng transaction minh họa; kết quả chỉ trả sau commit.
- Sự kiện được dựng từ thay đổi thực tế, gồm owner trước và sau, chủ thể thực hiện, căn cứ và phiên bản. Lý do người dùng nhập được lưu như lời giải thích, không như bằng chứng thẩm quyền.
- Nguồn membership, chính sách hoặc người nhận bên ngoài cần cơ chế hiệu lực và nhất quán tương ứng. Khóa riêng đối tượng không tự khóa mọi nguồn đó.

Mã giả quy định chuyển sang cùng owner bằng một lệnh mới là không có thay đổi hợp lệ để ghi. Retry đúng lệnh đã hoàn tất được xử lý trước nhánh đó.

### 5.2. Biên nhận retry không mở quyền với toàn đối tượng

A có thể mất ownership sau khi chuyển thành công cho B. Nếu A mất phản hồi, quyền xem biên nhận của chính lệnh chuyển cần được định nghĩa riêng.

Trong ví dụ, policy có thể cho người gửi đọc một biên nhận giới hạn với transferId và epoch kết quả. Điều đó không cho A tiếp tục đọc nội dung đơn hoặc các lần chuyển về sau.

Nếu tổ chức không cấp quyền đọc biên nhận trong một trường hợp, replay cũng phải tuân thủ chính sách đó. Idempotency key không tự trở thành thông tin xác thực.

### 5.3. Cập nhật có điều kiện

Một phép ghi phần hiện tại có thể có dạng:

```sql
UPDATE purchase_request
SET owner_type = :validated_new_owner_type,
    owner_id = :validated_new_owner_id,
    ownership_epoch = ownership_epoch + 1,
    row_version = row_version + 1
WHERE tenant_id = :authorized_tenant_id
  AND id = :request_id
  AND owner_type = :expected_old_owner_type
  AND owner_id = :expected_old_owner_id
  AND ownership_epoch = :expected_ownership_epoch
  AND row_version = :expected_row_version
  AND state = 'DRAFT';
```

Các placeholder là tham số bind. Chỉ chấp nhận đúng một hàng được cập nhật; nếu không, rollback những thay đổi liên quan và xử lý xung đột theo hợp đồng.

Một ràng buộc duy nhất theo tenant, loại đối tượng, ID và `toEpoch` có thể ngăn hai sự kiện nguồn cùng chiếm một thế hệ ownership. Định danh event và lệnh vẫn cần ngữ nghĩa riêng.

## 6. Dùng lịch sử đúng mục đích khi phân quyền

### 6.1. Quyền hiện tại dùng quan hệ hiện tại

Một lỗi nguy hiểm:

```java
// Người từng sở hữu có thể tiếp tục sửa mãi.
if (history.existsOwner(resourceId, actor.subjectId())) {
    allowUpdate();
}
```

Trong mô hình một owner hiện tại, nhánh sửa của chủ sở hữu cần kiểm tra nguồn hiện tại:

```text
đúng tenant
AND currentOwner khớp subject
AND action được phép
AND trạng thái và điều kiện nghiệp vụ hợp lệ
AND dữ liệu được bảo vệ trước cạnh tranh
```

Nếu người từng sở hữu được giữ một quyền đọc lịch sử hoặc xem quyết định của họ, hãy mô hình hóa grant đó riêng, với hành động và phạm vi rõ. Không dùng nó để cho phép sửa hoặc chuyển tiếp.

### 6.2. Owner tại thời điểm T chỉ là một dữ kiện

Khi xem một quyết định cũ, biết A sở hữu tại T chưa đủ để nói A được duyệt:

- Role và assignment có thể không cho phép action.
- Hạn mức hoặc phạm vi đơn vị có thể không đạt.
- A có thể là người lập nên vi phạm phân tách nhiệm vụ.
- Đối tượng có thể ở trạng thái không cho phép hành động.
- Quyết định có thể gắn với revision khác.
- Có thể có một quyền đại diện hợp lệ cần xét riêng.

Ngược lại, một người không phải owner vẫn có thể được giao duyệt theo chính sách. Không dùng lịch sử ownership làm thước đo duy nhất cho mọi hành động quá khứ.

### 6.3. Lịch sử nhóm không tự chứng minh lịch sử thành viên

Nếu owner là nhóm G tại T, việc U là thành viên G hôm nay không chứng minh U là thành viên tại T.

Để giải thích hành động cũ, cần bằng chứng membership hoặc quyết định phân quyền tương ứng với mốc đó nếu policy phụ thuộc nó. Không lấy danh sách thành viên mới nhất để tự lấp ngữ cảnh đã mất.

Điều này cũng áp dụng cho vai trò, ủy quyền và quan hệ tổ chức. Cần lưu hoặc tham chiếu đủ dữ kiện lịch sử theo nhu cầu kiểm chứng đã xác định.

## 7. Cạnh tranh, thế hệ ownership và truyền sự kiện

### 7.1. Hai lần chuyển đồng thời

Nếu A chuyển cho B và một lệnh khác cùng lúc chuyển cho C, cả hai không được thành công từ cùng một owner và epoch nếu mô hình chỉ có một lần chuyển kế tiếp.

Khóa hoặc version phải làm chỉ một phép chuyển thắng. Lệnh còn lại đọc lại hoặc bị từ chối; không tự đổi owner nguồn của lệnh cũ thành owner mới để tiếp tục chuyển mà người dùng chưa xác nhận.

Mọi đường ghi, gồm công cụ quản trị và tác vụ nhập dữ liệu, phải tuân thủ cùng giao thức. Handler an toàn không bảo vệ được một đường `UPDATE owner` bỏ qua lịch sử.

### 7.2. Trường hợp A → B → A

Xét:

```text
A, epoch 1
    → B, epoch 2
    → A, epoch 3
```

Một lệnh, link có quyền hạn chế hoặc grant cũ gắn với epoch 1 không tự có hiệu lực lại ở epoch 3 chỉ vì ownerId lại là A.

Đây là lý do cần thế hệ ownership khi chính sách ràng buộc quyền hoặc ý định với một lần sở hữu cụ thể. So sánh ownerId một mình không phân biệt được hai giai đoạn.

ExpectedEpoch từ client là điều kiện phát hiện ngữ cảnh cũ, không phải bằng chứng quyền. Máy chủ vẫn lấy epoch hiện tại từ nguồn có thẩm quyền và kiểm tra đầy đủ các ranh giới.

### 7.3. Event giao lại hoặc đến sai thứ tự

Outbox có thể truyền cùng event nhiều lần. Consumer cần khử trùng lặp theo eventId và giữ thứ tự ownership theo mô hình.

Nếu projection đã ở epoch 5 mà nhận event cũ của epoch 3, không được đổi owner ngược lại. Nếu nhận epoch 7 khi mới có 5, cần chờ, lấy bổ sung hoặc tái dựng từ nguồn theo giao thức.

Hai event khác nhau cùng tuyên bố một `toEpoch` không nên bị coi là hai bản sao bình thường. Cần phát hiện mâu thuẫn, thay vì chọn ngẫu nhiên owner cuối.

Một projection đang trễ có thể phục vụ hiển thị với trạng thái phù hợp. Nó không tự là nguồn đủ mới để cấp quyền ghi nhạy cảm nếu hợp đồng yêu cầu quan hệ hiện tại chặt chẽ.

### 7.4. Retry không tạo một lần chuyển mới

Cùng scope, cùng idempotency key và fingerprint phải liên kết với cùng kết quả lệnh. Fingerprint cần bao phủ đối tượng, người nhận, version, epoch và những trường ảnh hưởng ý nghĩa.

Cùng key nhưng đổi người nhận hoặc transferIntentId phải được phát hiện theo hợp đồng. Khóa khác vẫn phải chịu version, epoch và mọi điều kiện chuyển.

Nếu kết quả commit chưa rõ, đối soát trước khi thực hiện lại. Không ghi thêm một sự kiện đổi owner chỉ vì client chưa nhận được phản hồi.

## 8. Đối tượng con, nhóm và ảnh hưởng của việc chuyển

### 8.1. Ownership kế thừa từ parent

Một attachment có thể kế thừa quyền từ đơn mua hàng. Khi owner của đơn đổi, quyền hiện tại với attachment có thể đổi theo mà không cần giả rằng từng attachment đã được chuyển riêng.

Cần ghi rõ cơ chế kế thừa và giữ tham chiếu parent đủ tin cậy. Nếu attachment được chuyển sang parent khác, lịch sử quan hệ parent cũng ảnh hưởng việc trả lời ai có quyền tại thời điểm trước đó.

Không dùng parent hiện tại để suy ra ownership của child ở mọi thời điểm quá khứ. Khi điều tra, có thể cần cả lịch sử liên kết và lịch sử owner của parent.

Nếu child có owner độc lập, chuyển root không được tự thay owner của child ngoài chính sách. Hai mô hình cần được phân biệt rõ trong schema và handler.

### 8.2. Owner là nhóm

Chuyển đối tượng từ người A sang nhóm G không có nghĩa mọi thành viên G đều trở thành owner cá nhân trong lịch sử.

Lịch sử ownership nên ghi quan hệ tới G. Việc một thành viên được làm action nào thuộc chính sách thành viên và vai trò của nhóm tại mốc tương ứng.

Nếu nhóm bị đổi tên, giải thể hoặc hợp nhất, cần giữ định danh và nguồn gốc đủ để giải thích quan hệ cũ. Không thay ID nhóm lịch sử bằng tên của một nhóm mới chỉ vì có cùng nhãn hiển thị.

### 8.3. Phê duyệt, phân công và quyền phụ thuộc

Chuyển owner có thể ảnh hưởng:

| Thành phần | Câu hỏi cần quyết định |
|---|---|
| Quyết định phê duyệt đang có | Owner có phải thuộc tính ảnh hưởng ý nghĩa hoặc thẩm quyền của quyết định không? |
| Người được giao xử lý | Giữ nguyên, giao lại hay yêu cầu xác nhận? |
| Grant chia sẻ hoặc ủy quyền | Chúng gắn với đối tượng hay một epoch ownership cụ thể? |
| Tài liệu và báo cáo đã tạo | Quyền hiện tại có còn cho phép chủ cũ nhận dữ liệu không? |
| Execution đang chờ | Quyền được chấp nhận tại mốc trước hay cần kiểm tra lại? |

Lịch sử phải ghi hoặc liên kết được các quyết định có ý nghĩa này. Không tự coi mọi quyền phụ thuộc đều còn hiệu lực, cũng không xóa mọi quyết định cũ như thể chúng chưa từng xảy ra.

Một sự kiện transfer có thể là căn cứ để bắt đầu các công việc theo sau, nhưng audit cần phân biệt đã yêu cầu xử lý với đã xử lý xong. Outbox không tự chứng minh mọi cache hoặc hệ thống ngoài đã cập nhật.

### 8.4. Chuyển xuyên tenant là luồng khác

Đổi owner trong tenant không mặc nhiên cho phép chuyển dữ liệu sang tenant khác.

Nếu nghiệp vụ hỗ trợ chuyển hoặc sao chép xuyên tenant, cần thẩm quyền, ánh xạ danh tính, liên kết nguồn và chính sách dữ liệu riêng. Lịch sử thuộc tenant nguồn cũng cần quyền truy cập phù hợp; không sao chép toàn bộ thông tin nhạy cảm cho tenant đích chỉ để giữ một nhãn nguồn gốc.

Một quan hệ lịch sử tại tenant A không cấp quyền sửa hoặc đọc đối tượng mới ở tenant B. Cần giữ scope trong mọi định danh và truy vấn.

## 9. Bảo vệ và sửa chữa lịch sử

### 9.1. Không cho sửa lịch sử qua endpoint cập nhật thông thường

DTO sửa bản nháp hoặc chuyển owner không nên nhận danh sách lịch sử do client cung cấp. Những trường như fromOwner, actorId, epoch và recordedAt cần do nguồn có thẩm quyền xác định.

Tài khoản ghi sự kiện không nên mặc nhiên có quyền chỉnh hoặc xóa mọi bản ghi cũ. Công cụ quản trị cần đường sửa chữa có phạm vi, căn cứ và audit riêng.

Không thể khẳng định một bảng bất biến chỉ vì ứng dụng không có nút sửa. Quyền cơ sở dữ liệu, quyền vận hành, bản sao và khả năng kiểm chứng cần tương ứng với mô hình đe dọa.

### 9.2. Sửa sai bằng bản ghi có quan hệ rõ ràng

Một cách sửa là thêm sự kiện chỉ ra bản ghi hoặc khoảng nào sai, thông tin đề nghị sửa, căn cứ và người chấp nhận.

Cần phân biệt:

```text
chuyển ownership mới trong hiện tại

với

sửa cách ghi nhận một sự kiện quá khứ
```

Sự kiện sửa cần thứ tự và version theo mô hình, không được giả thành một lần chuyển đã thực sự xảy ra từ trước.

Nếu chỉnh sửa ảnh hưởng owner hiện tại, phần thay đổi hiện tại vẫn phải qua thẩm quyền và giao thức nhất quán tương ứng. Không dùng một chức năng “sửa lịch sử” để âm thầm đổi quyền hiện tại.

Việc dựng lại view lịch sử sau sửa có thể cần biết cả mốc hiệu lực và mốc thông tin được ghi nhận. Không xóa dấu vết trước sửa rồi làm như hệ thống luôn biết dữ kiện mới.

### 9.3. Nhập dữ liệu và baseline

Khi chuyển dữ liệu từ hệ thống cũ, có thể chỉ biết owner hiện tại mà không có chuỗi thay đổi đầy đủ.

Nên ghi một baseline có nguồn gốc rõ, ví dụ:

```text
OWNERSHIP_BASELINE_IMPORTED

Owner được xác nhận tại mốc nhập: B
Nguồn: tham chiếu lô dữ liệu có thẩm quyền
Lịch sử trước mốc này: chưa đủ dữ kiện
```

Không tự sinh các lần chuyển từ A sang B nếu không có bằng chứng. Cũng không lấy ngày tạo bản ghi làm ngày B bắt đầu sở hữu chỉ vì đó là timestamp duy nhất còn lại.

Nếu nhập được lịch sử đầy đủ, cần kiểm tra thứ tự, tenant, ánh xạ chủ thể, độ chính xác thời gian và các quan hệ chồng lấn. Dữ liệu mâu thuẫn phải được nhận diện, không tự chọn một owner theo tên sắp xếp.

### 9.4. Danh tính thay đổi hoặc bị xóa

Tên hiển thị có thể đổi, tài khoản có thể đóng và dữ liệu cá nhân có thể được xử lý theo chính sách lưu giữ.

Cần giữ định danh hoặc tham chiếu ổn định phù hợp để không gán hành động cũ cho một người mới dùng lại username. Nhãn hiển thị không nên là khóa phân quyền.

Việc giữ nhãn tại thời điểm trước hay tra nhãn hiện tại phải được quyết định theo nhu cầu và chính sách dữ liệu. Nếu một phần thông tin không còn được giữ, công cụ lịch sử cần phản ánh giới hạn đó thay vì tự điền một danh tính suy đoán.

## 10. Truy vấn, hiển thị và đối soát lịch sử

### 10.1. Quyền đọc lịch sử là một action riêng

Lịch sử có thể tiết lộ nhân sự, quan hệ tổ chức, lý do chuyển và hoạt động nội bộ. Người được đọc nội dung hiện tại chưa chắc được xem mọi trường lịch sử.

Một truy vấn luồng chuyển có thể có dạng:

```sql
SELECT event_id,
       from_owner_type,
       from_owner_id,
       to_owner_type,
       to_owner_id,
       from_epoch,
       to_epoch,
       effective_at,
       recorded_at
FROM ownership_change
WHERE tenant_id = :authorized_tenant_id
  AND object_type = :authorized_object_type
  AND object_id = :authorized_object_id
ORDER BY to_epoch;
```

Các tham số có tiền tố authorized biểu thị phạm vi đã được kiểm tra phía máy chủ. Truy vấn không tự thay thế quyền xem lịch sử của đối tượng.

Nếu có sự kiện sửa, baseline hoặc nhiều loại quan hệ, view lịch sử đầy đủ cần áp dụng ngữ nghĩa tương ứng. Chỉ ORDER BY timestamp hoặc chọn dòng cuối không tự giải quyết những trường hợp đó.

### 10.2. Không để giao diện làm mất ý nghĩa

Một timeline nên phân biệt:

- Chuyển đã được chấp nhận.
- Đề nghị đang chờ hoặc đã bị từ chối.
- Mốc dự kiến và mốc thực thi.
- Sửa thông tin lịch sử.
- Baseline nhập dữ liệu.
- Dữ liệu chưa đủ hoặc projection đang trễ.

Nếu hiển thị tên người hiện tại cho một định danh lịch sử, cần tránh khiến người đọc hiểu đó chắc chắn là nhãn được dùng tại thời điểm cũ.

Không dùng biểu tượng “chủ sở hữu cũ” làm dấu hiệu có thể tiếp tục sửa. Các nút hành động phải dựa trên quyền hiện tại và vẫn được kiểm tra lại ở máy chủ.

### 10.3. Đối soát giữa trạng thái và nguồn lịch sử

Có thể kiểm tra:

| Kiểm tra | Bất thường cần xem xét |
|---|---|
| Owner và epoch hiện tại khớp sự kiện chuyển đã áp dụng mới nhất | Có thể có đường cập nhật bỏ lịch sử |
| fromOwner và fromEpoch khớp chuỗi trước | Chuyển dựa trên trạng thái cũ hoặc dữ liệu nguồn mâu thuẫn |
| toEpoch duy nhất trong phạm vi | Event trùng nghĩa hoặc ghi cạnh tranh sai |
| Tenant và quan hệ đối tượng nhất quán | Liên kết sai tenant hoặc sai loại đối tượng |
| Các khoảng theo mô hình không chồng lấn trái phép | Sai thời gian hiệu lực hoặc sai dựng projection |
| Quyết định chuyển có căn cứ tương ứng | Thiếu phê chuẩn hoặc chấp nhận mà policy yêu cầu |
| Event truyền đi khớp nguồn | Mất event, chuyển chậm hoặc khác nội dung |

Cần đối chiếu trên mốc dữ liệu nhất quán. Đọc trạng thái hiện tại trước một transfer rồi đọc lịch sử sau transfer có thể tạo cảnh báo giả.

Một projection tập trung chưa nhận đủ event không tự chứng minh lịch sử nguồn bị xóa. Cần xét độ trễ và đối soát với nguồn có thẩm quyền.

### 10.4. Tái dựng không thực thi lại

Công cụ dựng timeline hoặc rebuild projection chỉ nên tạo view theo hợp đồng. Nó không được chuyển owner thật, phát lại lời mời nhận hoặc thực hiện hành động tài chính chỉ vì đọc lại sự kiện cũ.

Nếu hệ thống dùng sự kiện cho cả projection và tác dụng nghiệp vụ, các consumer cần cơ chế khử trùng lặp và đường replay phù hợp. Mỗi sự kiện lịch sử không phải một lệnh mới có quyền hiện tại.

## 11. Cache, quyền phụ thuộc và dữ liệu xuất

Một quyết định quyền có thể được ràng buộc với ownershipEpoch. Khi owner đổi, các kết quả cho phép dựa trên epoch cũ cần được xử lý theo bảo đảm nhất quán đã chọn.

Khóa cache có epoch chỉ có ích nếu hệ thống biết epoch hiện tại từ nguồn đủ mới. Không lấy epoch cũ trong cache rồi dùng nó để tự xác nhận cache vẫn hợp lệ.

Với tài nguyên con kế thừa quyền, cache cần biết sự phụ thuộc vào root hoặc có cơ chế vô hiệu tương ứng. Đổi owner ở root mà không ảnh hưởng cache child có thể giữ quyền cho chủ cũ.

Tệp lịch sử hoặc báo cáo cũng là dữ liệu cần phân quyền. Người từng sở hữu không tự được tải mọi bản xuất về đối tượng sau khi chuyển.

Nếu một link hoặc quyền tải được ràng buộc với một epoch, cần thực thi ràng buộc tại đường truy cập theo hợp đồng. Chỉ ghi epoch trong tên tệp không làm link tự hết quyền.

Audit việc đọc hoặc xuất lịch sử nhạy cảm nên ghi đủ đối tượng, tenant, người truy cập và phạm vi, nhưng không sao chép toàn bộ nội dung nhạy cảm vào log.

## 12. Kiểm thử tính đúng đắn của lịch sử ownership

### 12.1. Dữ liệu kiểm thử cần có

Chuẩn bị nhiều tenant, người và nhóm với các trường hợp:

- Người tạo vẫn là owner.
- Người tạo đã chuyển cho người khác.
- Một đối tượng chuyển qua nhiều owner.
- Ownership quay lại cùng người nhưng epoch mới.
- Nhóm đổi thành viên sau một hành động cũ.
- Dữ liệu chỉ có baseline, không có lịch sử trước đó.
- Cùng ID đối tượng cục bộ xuất hiện ở hai tenant.

Nếu mọi dữ liệu test đều có createdBy bằng owner hiện tại, lỗi dùng nhầm quan hệ có thể không bị phát hiện.

### 12.2. Ma trận tình huống

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Chuyển hợp lệ A sang B | Trạng thái hiện tại và sự kiện khớp trước, sau, tenant và epoch |
| Người không có quyền gửi lệnh chuyển | Không đổi owner hoặc tạo lịch sử thành công |
| Client khai fromOwner hoặc actorId giả | Sự kiện dùng dữ liệu máy chủ và danh tính thực |
| Người nhận thuộc tenant khác ngoài luồng được phép | Không tạo liên kết ownership sai phạm vi |
| Chuyển sang cùng owner bằng lệnh mới | Không ghi một lần thay đổi giả theo hợp đồng ví dụ |
| Retry cùng lệnh sau mất phản hồi | Cùng kết quả, không tăng epoch hoặc thêm transfer |
| Cùng khóa nhưng đổi người nhận | Phát hiện dùng khóa cho lệnh khác |
| A đã chuyển cho B rồi thử sửa | Không cho phép chỉ vì A từng sở hữu |
| A → B → A, dùng grant hoặc lệnh epoch đầu | Không khôi phục quyền cũ chỉ vì ownerId trùng lại |
| A là người lập rồi chuyển cho B | Quy tắc chống A tự duyệt vẫn giữ đúng nguồn gốc |
| Nhóm G sở hữu tại T, U chỉ mới gia nhập G | Không dùng membership hiện tại để chứng minh quyền tại T |
| Đề nghị chuyển đang chờ hoặc chưa tới mốc thực thi | Không hiển thị như thay đổi hiện tại đã hoàn tất |
| Event cũ đến sau event mới | Projection không đổi owner ngược |
| Hai event khác nhau chiếm cùng toEpoch | Nhận diện mâu thuẫn, không chọn ngẫu nhiên |
| Thiếu lịch sử trước baseline | Hiển thị giới hạn dữ kiện, không tự bịa owner cũ |
| Đọc lịch sử đối tượng tenant khác | Không trả nội dung hoặc metadata ngoài quyền |
| Sửa thông tin quá khứ có thẩm quyền | Giữ căn cứ và dấu vết sửa, không giả thành quyền hồi tố |
| Tái dựng projection | Không tạo lời mời nhận, transfer thật hoặc tác dụng ngoài ý muốn |

### 12.3. Cạnh tranh và điểm chèn lỗi

Các ca tích hợp quan trọng:

1. Hai lệnh chuyển cùng xuất phát từ một owner và epoch.
2. Chuyển owner đồng thời với sửa nội dung.
3. Chuyển owner đồng thời với gửi hoặc quyết định phê duyệt theo phạm vi policy.
4. Lỗi sau cập nhật owner nhưng trước append sự kiện.
5. Lỗi sau append sự kiện nhưng trước ghi outbox hoặc command log.
6. Commit thành công rồi mất phản hồi.
7. Consumer nhận event giao lại, sai thứ tự hoặc thiếu một epoch.
8. Đối soát trong lúc một transfer mới đang commit.
9. Chuyển root trong khi tài nguyên con đang được truy cập bằng cache.

Với trường hợp transaction thất bại, trạng thái và lịch sử phải rollback cùng nhau theo mô hình. Với commit chưa rõ, đối soát trước khi lặp tác dụng.

Kiểm thử khóa và transaction cần cơ sở dữ liệu có đặc tính tương ứng triển khai. Một mock luôn trả owner A không chứng minh được khả năng bảo vệ trước chuyển đồng thời.

### 12.4. Kiểm tra điều không được thay đổi khi từ chối

```text
owner hiện tại và ownershipEpoch không đổi bởi lệnh thất bại
rowVersion không tăng dở dang
createdBy và nguồn gốc nội dung được giữ nguyên
không append sự kiện báo đã chuyển thành công
không phát outbox cho một transfer chưa được chấp nhận
không thay quyền child ngoài chính sách
không xóa quyết định hoặc lịch sử đã tồn tại
không trả chi tiết lịch sử ngoài scope trong lỗi
```

Một dấu vết về lần thử bị chặn có thể được ghi riêng. Nó không được nhầm với một lần chuyển owner đã thành công.

### 12.5. Kiểm chứng timeline và nguồn hiện tại

Với cùng một ảnh chụp dữ liệu có thẩm quyền:

- Mỗi event chuyển kế tiếp khớp owner và epoch trước.
- Epoch của lần sở hữu mới không bị dùng hai lần trong cùng phạm vi.
- Owner hiện tại khớp đầu chuỗi đã áp dụng.
- Truy vấn tại mốc biên tuân thủ quy ước khoảng.
- View sau sửa vẫn phân biệt được điều đã được biết trước và sau chỉnh sửa.
- Baseline không bị diễn giải thành lịch sử đầy đủ từ ngày tạo đối tượng.
- Các query quyền hiện tại không dùng “từng sở hữu” thay cho “đang sở hữu”.

Nếu lịch sử có dữ kiện không đủ hoặc mâu thuẫn, công cụ cần thể hiện vấn đề thay vì tạo một timeline có vẻ chắc chắn.

## 13. Bài tập áp dụng

Thiết kế lịch sử ownership cho đơn mua hàng có thể chuyển giữa người và nhóm trong cùng tenant.

1. Xác định owner hiện tại, người tạo, người được giao và quan hệ nào cần lịch sử riêng.
2. Thiết kế sự kiện chuyển cùng version và epoch cần dùng.
3. Chọn quy ước thời gian hiệu lực, thời gian ghi nhận và cách xử lý mốc sát commit.
4. Vẽ transaction cập nhật owner, ghi lịch sử, outbox và kết quả idempotency.
5. Định nghĩa quyền đọc hiện tại, quyền đọc lịch sử và biên nhận của người chuyển cũ.
6. Mô tả ảnh hưởng tới child, phê duyệt, grant, cache và execution.
7. Xử lý baseline nhập dữ liệu, sửa sai và danh tính không còn hoạt động.
8. Viết ca A → B → A, hai lần chuyển đồng thời và event cũ đến muộn.
9. Chọn các kiểm tra đối soát giúp phát hiện một đường cập nhật owner bỏ qua lịch sử.

Một lịch sử ownership đáng tin cần cho biết quan hệ đã thay đổi thế nào và căn cứ nào làm thay đổi đó được chấp nhận. Nó phải giúp giải thích quá khứ mà không tự mở quyền hiện tại, đồng thời giữ nguyên nguồn gốc, tenant và các bất biến của quy trình nghiệp vụ.
