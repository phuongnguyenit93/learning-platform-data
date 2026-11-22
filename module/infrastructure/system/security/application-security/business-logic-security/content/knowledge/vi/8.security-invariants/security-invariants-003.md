# Ứng phó khi bất biến bị vi phạm — Invariant violation response

## 1. Phát hiện vi phạm phải dẫn tới một quyết định an toàn

Một bất biến bảo mật mô tả điều phải được giữ trong phạm vi nghiệp vụ xác định. Ví dụ:

- Tổng tiền hoàn không vượt phần được phép hoàn.
- Một bản duyệt chỉ áp dụng cho đúng phiên bản nội dung.
- Actor chỉ được thao tác trên đối tượng trong phạm vi quyền.
- Một nghĩa vụ thanh toán không tạo hai tác động trái phép.
- Số ghế đang sử dụng không vượt quyền lợi có hiệu lực theo chính sách.

Viết ra các điều kiện này mới là một phần của thiết kế. Hệ thống còn phải biết làm gì khi một kiểm tra không đạt.

**Invariant violation response** là hợp đồng phản ứng trước dấu hiệu một bất biến không được đáp ứng: từ chối hành động, hủy thay đổi chưa commit, ngăn tác động mới, ghi nhận bằng chứng, xác định hậu quả và phục hồi theo quy tắc.

Một thông báo lỗi hoặc dòng log không tự bảo vệ được bất biến. Quyết định cần trả lời:

1. Đây là yêu cầu cố vượt quy tắc hay dữ liệu hiện tại đã sai?
2. Có thay đổi nào đã commit chưa?
3. Có tác động ngoài nào đã xảy ra hoặc chưa rõ kết quả?
4. Còn hành động nào phải ngăn ngay?
5. Điều gì cần được lưu để đối soát và phục hồi?

Trong chương **Security Invariants**, bài này nối điều kiện cần giữ với hành vi thực thi và vận hành khi điều kiện đó thất bại.

## 2. Phân loại trước khi phản ứng

Không nên gộp mọi trường hợp vào một exception “invariant failed” rồi trả cùng một lỗi.

| Nhóm tình huống | Ví dụ | Phản ứng chính |
| --- | --- | --- |
| Yêu cầu không thỏa điều kiện | Xin hoàn 700.000 khi chỉ còn 300.000 được hoàn. | Từ chối, không tạo thêm nghĩa vụ hoặc tác động. |
| Xung đột do dữ liệu đã đổi | Hai request cùng dựa trên một phiên bản, một request thắng. | Từ chối hoặc đánh giá lại theo hợp đồng retry. |
| Cơ chế dữ liệu chặn ghi sai | Unique constraint từ chối operation trùng. | Rollback phù hợp, phân loại theo ngữ nghĩa constraint và yêu cầu. |
| Trạng thái đã lưu không nhất quán | Tổng đã hoàn và đang giữ lớn hơn hạn mức có thẩm quyền. | Chặn thay đổi có nguy cơ làm nặng thêm, lập sự cố và đối soát. |
| Tác động ngoài đã xảy ra trái quy tắc | Đối tác xác nhận hai khoản hoàn cho một nghĩa vụ. | Ngăn lặp tiếp, ghi nhận sự thật, phục hồi/bù trừ theo chính sách. |
| Kết quả ngoài chưa rõ | Timeout sau khi đã gửi lệnh hoàn. | Giữ operation và phần ngân sách phù hợp, truy vấn/đối soát. |
| Tín hiệu chưa đủ tin cậy | Hai bảng được đọc ở hai thời điểm khác nhau trông như lệch. | Xác minh bằng dữ liệu nhất quán, giới hạn rủi ro theo mức bằng chứng. |

### 2.1. Một lần chặn thành công chưa phải dữ liệu đã hỏng

Request bị từ chối trước khi tạo tác động có thể là bằng chứng cơ chế bảo vệ đang hoạt động. Nó không tự chứng minh đã có tổn thất.

Ngược lại, một lỗi nội bộ làm mất kiểm soát có thể nghiêm trọng dù caller chỉ nhận response thất bại. Cần quan sát dữ liệu và tác động, không suy ra từ mã HTTP.

### 2.2. Xung đột bình thường khác sự cố toàn vẹn

Số dòng cập nhật bằng không có thể chỉ là phiên bản cũ hoặc quota vừa hết. Không cần tạo một sự cố nghiêm trọng cho từng request thua cạnh tranh.

Nhưng nếu trạng thái bất khả thi đã được commit, đó không còn chỉ là “người dùng thao tác chưa đúng”. Hệ thống cần phản ứng ở mức dữ liệu và quy trình liên quan.

## 3. Ví dụ xuyên suốt: ngân sách hoàn tiền

Dùng mô hình minh họa:

- Mỗi phạm vi hoàn gắn với tenant, giao dịch gốc và loại tiền.
- Khoản được phép hoàn được xác lập từ dữ liệu có thẩm quyền.
- Khi chấp nhận một lệnh hoàn, server giữ ngân sách.
- Khi có xác nhận hoàn thành công, phần giữ chuyển thành phần đã hoàn.
- Chỉ giải phóng phần giữ khi có căn cứ thao tác không tạo tác động hoặc theo quy trình xử lý đã định nghĩa.

Đặt:

```text
C = refundableCapturedAmount
R = settledRefundAmount
H = reservedRefundAmount
```

Bất biến tại điểm chấp nhận tác động mới:

```text
C >= 0
R >= 0
H >= 0
R + H <= C
```

Các giá trị phải cùng phạm vi và loại tiền.

### 3.1. Yêu cầu vượt phần còn lại

Nếu:

```text
C = 1.000.000
R =   600.000
H =   100.000
```

thì phần còn được giữ là 300.000. Lệnh mới xin 400.000 phải bị từ chối trước khi tạo nghĩa vụ hoàn mới.

Trạng thái ban đầu vẫn hợp lệ. Đây là một hành động không được phép đi tiếp.

### 3.2. Dữ liệu đã vi phạm

Nếu một snapshot có thẩm quyền cho thấy:

```text
C = 1.000.000
R =   800.000
H =   400.000
```

thì tổng đã vượt 200.000 trước khi xét lệnh mới.

Chỉ trả “không đủ hạn mức” cho caller là chưa đủ. Hệ thống cần tìm hiểu vì sao trạng thái này tồn tại, liệu H có trùng, R có bị cộng hai lần hay bên ngoài đã thực sự hoàn vượt.

Không tự sửa bằng cách đặt H về 200.000 hoặc R về 600.000 để phương trình trông hợp lệ. Các con số có thể đang đại diện cho nghĩa vụ hoặc tác động thật.

### 3.3. Phân biệt mô hình quyết định với sự thật bên ngoài

Bất biến dùng để ngăn chấp nhận tác động sai. Nếu tác động sai đã xảy ra ở bên ngoài, hệ thống vẫn phải ghi nhận sự thật đó.

Một constraint cục bộ không cho phép số tổng vượt ngưỡng không phải lý do để bỏ một xác nhận hoàn tiền thật. Có thể cần sổ sự kiện/quan sát ngoài, bản ghi chênh lệch và quy trình điều chỉnh có kiểm soát, trong khi aggregate bị cách ly.

Không làm dữ liệu “đẹp” bằng cách che hoặc loại bỏ hậu quả đã xảy ra. Bất biến vẫn được coi là đã vi phạm cho đến khi nguyên nhân và chênh lệch được xử lý theo mô hình được chấp nhận.

## 4. Phát hiện dựa trên bằng chứng nhất quán

Một kiểm tra cần nói rõ:

```text
invariantCode
aggregate / resource scope
expected relation
observed values
businessVersion / rowVersion
source references
observation time
effect state
```

### 4.1. Các điểm phát hiện

| Điểm | Bảo đảm có thể có | Điều còn phải làm |
| --- | --- | --- |
| Validation command | Chặn đầu vào sai miền hoặc thiếu dữ kiện. | Phân quyền và kiểm tra trạng thái có thẩm quyền. |
| Domain guard | Từ chối chuyển đổi trái quy tắc. | Bảo vệ điều kiện tới lúc ghi. |
| Atomic update/constraint | Chặn một số ghi sai khi cạnh tranh. | Phân loại kết quả và rollback đúng phạm vi. |
| Consumer | Phát hiện message không khớp hoặc tác động lặp. | Không retry mù quáng, bảo vệ side effect. |
| Đối soát | Phát hiện dữ liệu đã commit lệch với sổ hoặc nguồn ngoài. | Cách ly và sửa qua quy trình kiểm soát. |
| Giám sát | Báo dấu hiệu bất thường. | Xác minh trước khi kết luận và chọn mức ứng phó. |

Một lỗi xuất hiện ở database không tự cho biết nguyên nhân là tấn công, bug hay xung đột bình thường. Cần ngữ nghĩa nghiệp vụ.

### 4.2. Tránh kết luận từ ảnh chụp dữ liệu lệch thời điểm

Nếu đọc tổng reservation trước một transaction và đọc counter sau transaction đó, phép so sánh có thể trông sai dù mỗi trạng thái commit đều đúng.

Đối soát cần dùng snapshot/mốc nhất quán thích hợp. Với nhiều service, cần hiểu độ trễ projection, phiên bản hoặc watermark trước khi coi mọi khác biệt là vi phạm.

Nếu thiếu căn cứ mà hành động tiếp theo có rủi ro cao, có thể tạm giữ hành động đó để xác minh. Không để thiếu bằng chứng biến thành quyền tiếp tục vô điều kiện.

### 4.3. Dấu hiệu do client gửi không tự kích hoạt ứng phó đặc quyền

Một field, header hoặc thông báo lỗi từ đối tác có thể là đầu vào cần điều tra. Nó không tự có quyền yêu cầu khóa tenant khác, bỏ quota hoặc thay số dư.

Các hành động cách ly và phục hồi cần dựa trên bằng chứng server kiểm chứng, phạm vi phù hợp và chính sách có thẩm quyền. Nếu không, cơ chế ứng phó có thể bị lợi dụng để gây gián đoạn.

## 5. Thiết kế hợp đồng phản hồi

Một phản hồi cho caller nên:

- Nói rõ yêu cầu đã được chấp nhận hay chưa.
- Cho biết cần sửa dữ liệu, tải lại phiên bản, chờ hay tra cứu operation.
- Không tiết lộ dữ liệu ngoài quyền.
- Không khẳng định thành công/thất bại của tác động ngoài khi chưa biết.
- Có tham chiếu hỗ trợ truy vết khi phù hợp.

Ví dụ:

```json
{
  "code": "REFUND_ALLOWANCE_EXCEEDED",
  "message": "Yêu cầu vượt phần được phép hoàn.",
  "requestReference": "req-demo-17"
}
```

Nếu caller không được biết giao dịch tồn tại hoặc số tiền cụ thể, response cần tuân theo chính sách đó. Không trả toàn bộ snapshot nội bộ chỉ để giải thích một lần từ chối.

### 5.1. Mã lỗi giao thức cần đúng ngữ nghĩa

Tùy hợp đồng API, có thể phân biệt:

| Tình huống | Ví dụ nhóm phản hồi |
| --- | --- |
| Input sai cấu trúc/miền | Lỗi đầu vào có thể sửa. |
| Không có quyền | Từ chối truy cập hoặc phản hồi không tiết lộ tồn tại đối tượng. |
| Phiên bản/trạng thái xung đột | Yêu cầu tải lại hoặc xử lý xung đột. |
| Cùng idempotency key nhưng khác nội dung | Xung đột định danh yêu cầu. |
| Aggregate đang cách ly | Tạm chưa thể thực hiện hành động, có tham chiếu phù hợp. |
| Lỗi bất ngờ | Lỗi server, không tiết lộ chi tiết nhạy cảm. |
| Operation đang chờ kết quả ngoài | Trạng thái đang xử lý/chưa rõ theo hợp đồng tra cứu. |

Không map mọi exception thành thành công hoặc mọi constraint thành cùng một lỗi xung đột. Mã HTTP là một phần giao tiếp; bất biến được bảo vệ bằng hành vi dữ liệu và tác động.

## 6. Khi chưa commit: từ chối và rollback đúng phạm vi

Nếu lỗi được phát hiện trước khi commit và chưa có tác động ngoài:

1. Dừng các bước nghiệp vụ phụ thuộc điều kiện không đạt.
2. Không tạo thêm operation hoặc phát lệnh ngoài.
3. Rollback những thay đổi cục bộ thuộc quyết định thất bại.
4. Trả phản hồi theo loại lỗi.
5. Ghi tín hiệu từ chối hoặc sự cố theo chính sách.

Ví dụ, giữ ngân sách thành công nhưng tạo refund operation thất bại phải rollback cả phần giữ. Nếu không, người dùng bị mất ngân sách dù không có operation để theo dõi.

### 6.1. Exception chỉ hữu ích khi transaction thực sự rollback

Cần kiểm tra hành vi thật của framework/driver:

- Các thao tác có cùng transaction và connection thích hợp không.
- Exception có bị catch rồi làm transaction commit ngoài ý định không.
- Có thao tác async hoặc kết nối khác nằm ngoài ranh giới không.
- Có lời gọi ngoài đã chạy trước khi lỗi xuất hiện không.

Một annotation hoặc tên hàm `transactional` không thay thế các bảo đảm thực tế.

### 6.2. Không tiếp tục sau khi bảo đảm đã thất bại

Nếu cập nhật có điều kiện không tác động đúng một hàng, không tiếp tục gọi đối tác như thể đã giữ được ngân sách.

Nếu database đã đánh dấu transaction thất bại theo semantics của nó, không âm thầm bỏ qua rồi cố ghi những thay đổi khác. Phải xử lý theo giao thức transaction của hệ quản trị đang dùng.

Với unique constraint, cần phân biệt retry cùng nội dung với key bị dùng cho nội dung khác. Một lần chèn trùng không tự chứng minh có thể trả kết quả thành công bất kỳ.

## 7. Phác thảo xử lý lệnh hoàn tiền trong Java

Ví dụ sau minh họa phân biệt lỗi yêu cầu với phát hiện trạng thái đã lưu không nhất quán:

```java
// Minh họa kiến trúc; các abstraction cần được hiện thực đúng bảo đảm mô tả.
record RefundCommand(
    long amountMinor,
    String currency,
    String idempotencyKey
) {}

RefundAccepted requestRefund(
        Actor actor, UUID tenantId, UUID paymentId, RefundCommand command) {

    try {
        return transaction.required(() -> {
            RefundBudget budget = budgets.loadForUpdate(tenantId, paymentId)
                .orElseThrow(NotFound::new);

            access.requireCanRequestRefund(actor, budget);
            commandPolicy.requireValidAmountAndCurrency(command, budget);

            // Kiểm tra snapshot cục bộ có thẩm quyền trong phạm vi đã định nghĩa.
            integrity.requireConsistentStoredBudget(budget);
            controlGate.requireOpenForNewRefund(budget.scope());

            IdempotencyClaim claim = idempotency.claim(
                actor, budget.scope(), command.idempotencyKey(),
                fingerprints.of(paymentId, command)
            );

            if (claim.isCompletedWithSamePayload()) {
                return claim.savedResult();
            }

            // Vượt phần còn lại là lỗi nghiệp vụ dự kiến, không phải bằng
            // chứng rằng trạng thái hiện tại đã hỏng.
            BudgetReservation reservation = budget.reserveOrReject(
                command.amountMinor()
            );

            RefundOperation operation = operations.create(
                actor, budget, reservation
            );
            budgets.save(budget);
            operations.insert(operation);
            outbox.appendRefundRequested(operation);
            audit.appendRefundAccepted(actor, operation);

            RefundAccepted result = RefundAccepted.from(operation);
            idempotency.complete(claim, result);
            return result;
        });

    } catch (StoredInvariantViolation violation) {
        // Theo hợp đồng ví dụ, transaction.required đã rollback trước khi ném ra.
        IncidentReceipt incident = incidents.recordAfterRollbackAndRequestContainment(
            violation.safeEvidence()
        );
        throw new AggregateTemporarilyUnavailable(incident.publicReference());
    }
}
```

### 7.1. Những điều đoạn mã cần bảo đảm

- Actor được dựng từ cơ chế xác thực, không từ body.
- Quyền gắn đúng tenant và giao dịch.
- Kiểm tra trạng thái dùng snapshot phù hợp; các đường sửa budget phối hợp cùng giao thức khóa/phiên bản.
- Claim idempotency có ràng buộc duy nhất, phát hiện khác nội dung và chỉ cho bên có quyền xử lý tiếp tục.
- Giữ ngân sách, operation và outbox commit cùng nhau.
- Kết quả `RefundAccepted` chỉ nói lệnh đã được chấp nhận, chưa nói bên ngoài đã hoàn tiền.
- Lỗi vượt hạn mức được xử lý như từ chối nghiệp vụ.
- `StoredInvariantViolation` chỉ được tạo từ kiểm tra có ý nghĩa đã xác định, không từ chuỗi caller tự gửi.

Các lỗi khác như validation, quyền hoặc xung đột được ánh xạ ở lớp xử lý lỗi của ứng dụng theo hợp đồng. Ví dụ này không có nghĩa chỉ loại exception được catch mới cần được quan sát.

### 7.2. Ghi sự cố sau rollback là một ranh giới riêng

Bản ghi sự cố trong ví dụ được lưu sau khi transaction nghiệp vụ đã rollback. Nó không tự nguyên tử với quyết định nghiệp vụ ban đầu.

Cần xác định:

- Cơ chế lưu sự cố có transaction/độ bền phù hợp.
- Nếu ghi sự cố thất bại, request vẫn không được chuyển sang thực hiện hoàn tiền.
- Không trả tham chiếu “đã ghi sự cố” nếu thực tế chưa lưu bền vững.
- Có tín hiệu vận hành dự phòng phù hợp khi kênh ghi sự cố gặp lỗi.
- Yêu cầu cách ly được thực thi ở những điểm tạo tác động cần thiết.

Tên `requestContainment` chỉ biểu thị yêu cầu ứng phó. Nó không chứng minh mọi worker hoặc lệnh đã gửi ra ngoài lập tức ngừng.

Nếu sản phẩm cần ghi gate và incident nguyên tử ngay khi phát hiện, có thể thiết kế một nhánh riêng phát hiện trước các ghi nghiệp vụ, lưu control state và incident theo transaction thích hợp rồi trả lỗi sau commit. Phải bảo đảm nhánh đó không vô tình commit một phần thay đổi tài chính.

## 8. Khi dữ liệu đã commit: cách ly có phạm vi

Rollback transaction hiện tại không xóa được những thay đổi đã commit trước đó.

Một luồng ứng phó có thể là:

1. Lưu bằng chứng đủ để xác định aggregate và thời điểm/phiên bản.
2. Chặn hành động mới có thể làm chênh lệch tăng.
3. Kiểm tra các operation đang chờ và đang chạy.
4. Đối chiếu nguồn có thẩm quyền.
5. Lập kế hoạch sửa/bù trừ.
6. Kiểm tra lại trước khi mở luồng.

### 8.1. Gate cần nằm ở nơi quyết định tác động

Một cờ “đang điều tra” chỉ có ý nghĩa bảo vệ nếu API, worker, batch và công cụ liên quan đều kiểm tra đúng lúc.

Ví dụ, khóa API tạo lệnh mới chưa ngăn worker tiếp tục gửi các lệnh đã xếp hàng. Cần quyết định lệnh nào được giữ lại, lệnh nào đã có cam kết cần xử lý và lệnh nào đã ra ngoài không thể dừng trực tiếp.

Quyền đọc trạng thái hoặc xem biên nhận trong phạm vi hợp lệ có thể vẫn được giữ để hỗ trợ đối soát. Cách ly đường tạo tác động không cần đồng nghĩa xóa mọi khả năng quan sát.

### 8.2. Chọn phạm vi nhỏ nhất đủ ngăn lan rộng

Nếu chứng cứ chỉ ra một payment aggregate bị lệch, có thể cách ly payment đó trước. Nếu nguyên nhân nằm ở budget chung, một code path hoặc nguồn cấp quyền, phạm vi cần rộng hơn.

Không chọn phạm vi chỉ theo cảm giác:

- Quá hẹp có thể để lỗi tiếp tục ở các đối tượng khác.
- Quá rộng có thể làm gián đoạn dịch vụ không cần thiết.
- Tự động cách ly toàn hệ thống từ một tín hiệu chưa kiểm chứng có thể bị lạm dụng.

Cần ghi lý do, mức bằng chứng, người/cơ chế chịu trách nhiệm và điều kiện mở lại.

### 8.3. Cách ly không được làm mất sự thật mới

Trong lúc aggregate bị khóa tạo lệnh mới, hệ thống vẫn có thể nhận xác nhận thật từ các lệnh đã gửi trước đó.

Đường ghi nhận sự thật, audit và đối soát cần tiếp tục theo cơ chế an toàn. Không bỏ message thành công chỉ vì việc áp vào projection hiện tại làm lộ một bất biến đã bị phá.

Có thể đưa message vào nhánh chờ xử lý đặc biệt, lưu tham chiếu bền vững và trạng thái chưa áp dụng. Không xác nhận đã hoàn tất xử lý nếu dữ kiện cần thiết bị mất.

## 9. Tác động bên ngoài và kết quả chưa rõ

Một hợp đồng ứng phó nên phân loại trạng thái tác động:

| Điều đã biết | Hành vi phù hợp |
| --- | --- |
| Chưa commit và chưa gửi lệnh ngoài | Rollback và từ chối; không có nghĩa vụ mới. |
| Đã commit ý định nhưng chưa gửi | Có thể tạm giữ dispatch theo chính sách và kiểm tra lại. |
| Đã gửi nhưng chưa biết kết quả | Giữ cùng operation, tra cứu/đối soát; không tự giải phóng nghĩa vụ. |
| Đã xác nhận không có tác động theo hợp đồng | Kết thúc thất bại và trả phần ngân sách được phép. |
| Đã xác nhận thành công | Ghi nhận thành công thực tế, kể cả khi cần mở sự cố. |
| Đã có tác động trái quy tắc | Ngăn lặp thêm, xác định phạm vi và thực hiện bù trừ được phê duyệt theo chính sách. |

### 9.1. Timeout không chứng minh thất bại nghiệp vụ

Nếu đối tác đã hoàn tiền nhưng response bị mất, đặt operation thành `FAILED` rồi trả ngân sách có thể cho phép một lệnh hoàn mới, làm hậu quả tăng.

Cần trạng thái như `OUTCOME_UNKNOWN` hoặc `RECONCILING`, tùy mô hình. Phần giữ vẫn phản ánh nghĩa vụ có thể đã tồn tại.

Đối soát dùng mã thao tác ổn định và cơ chế tra cứu/idempotency của bên ngoài. Không tạo ID mới chỉ để có một lần gọi “sạch”.

### 9.2. Bù trừ là hành động mới

Một khoản hoàn sai không tự bị đảo ngược bằng rollback database. Thu hồi tiền, điều chỉnh nghĩa vụ hoặc xử lý với khách hàng là những quy trình nghiệp vụ riêng.

Bù trừ cần:

- Đối tượng và căn cứ rõ.
- Quyền hoặc phê duyệt phù hợp.
- Định danh chống thực hiện lặp.
- Theo dõi thất bại/kết quả chưa rõ của chính hành động bù trừ.
- Dấu vết liên kết với tác động gốc.

Không mặc định mọi tác động đều có thể bù trừ hoàn toàn.

## 10. Retry và xử lý đồng thời khi đang có vi phạm

### 10.1. Phân loại lỗi trước khi retry

| Loại | Hướng xử lý |
| --- | --- |
| Input hoặc quyền không hợp lệ | Caller phải sửa hoặc được cấp đúng quyền; không retry mù. |
| Phiên bản cũ | Tải lại và đánh giá lại ý định theo hợp đồng. |
| Deadlock/lỗi giao dịch có thể thử lại | Retry toàn quyết định phù hợp, gồm kiểm tra điều kiện và idempotency. |
| Trạng thái đã lưu bất khả thi | Dừng luồng liên quan, không lặp vô hạn cùng thao tác. |
| Message sai nội dung hoặc không còn áp dụng | Từ chối/đưa sang nhánh xử lý lỗi có theo dõi. |
| Kết quả ngoài chưa rõ | Tra cứu/đối soát cùng operation, không tạo nghĩa vụ mới. |

Một message làm lộ dữ liệu hỏng không nên liên tục chiếm worker chỉ vì consumer luôn retry. Cần lưu trạng thái chờ xử lý, mã lý do và cơ chế tiếp tục sau khi sửa.

### 10.2. Cách ly và sửa cũng có race condition

Trong khi tiến trình đối soát đọc dữ liệu, một worker có thể đang cập nhật cùng aggregate.

Một kế hoạch sửa cần:

- Gate hoặc quyền sở hữu xử lý phù hợp.
- Phiên bản/mốc dữ liệu được dùng.
- Điều kiện khi ghi để phát hiện trạng thái đã đổi.
- Danh sách operation đang chạy hoặc chưa rõ.
- Hành vi nếu phát hiện cập nhật mới.

Không đọc snapshot lúc 10:00 rồi ghi đè lúc 10:05 như thể không có gì thay đổi.

### 10.3. Idempotency tiếp tục áp dụng trong phục hồi

Retry tác vụ sửa, áp sự kiện hoặc bù trừ không được:

- Cộng lại R hai lần.
- Trả H hai lần.
- Tạo thêm khoản bù trừ.
- Phát nhiều tác động cuối cho cùng quyết định.
- Mở lại gate khi vẫn còn bước bắt buộc chưa xong.

Cần định danh cho incident, kế hoạch sửa và từng operation phục hồi. Correlation ID hỗ trợ truy vết nhưng không tự là khóa nghiệp vụ chống lặp.

## 11. Audit và cảnh báo phải phản ánh đúng điều đã xảy ra

Nên phân biệt các sự kiện:

```text
REQUEST_REJECTED
CONCURRENT_UPDATE_CONFLICT
WRITE_BLOCKED_BY_CONSTRAINT
STORED_INVARIANT_VIOLATION_DETECTED
EXTERNAL_OUTCOME_UNKNOWN
CONTAINMENT_REQUESTED
CONTAINMENT_ACTIVATED
REPAIR_APPLIED
INVARIANT_REVERIFIED
CONTROL_GATE_REOPENED
```

Tên có thể khác, nhưng đừng gộp “đã yêu cầu cách ly” với “đã cách ly xong”, hoặc “đã từ chối request” với “đã phát sinh thiệt hại”.

### 11.1. Audit trong transaction rollback cũng bị rollback

Nếu ghi sự kiện từ chối vào cùng transaction rồi rollback, bản ghi audit đó có thể không còn.

Tùy yêu cầu, có thể dùng kênh log có độ bền phù hợp, transaction riêng sau rollback hoặc một thiết kế lưu quyết định trước khi phát tác động. Mỗi cách có ranh giới lỗi riêng cần được hiểu.

Outbox nằm trong transaction bị rollback cũng không giúp giữ lại một sự kiện từ chối của transaction đó. Không mô tả nó như bảo đảm ghi log mọi thất bại.

### 11.2. Giữ bằng chứng đủ dùng, không lộ thêm tài sản

Thông tin hữu ích có thể gồm:

- Actor đã kiểm chứng và service thực thi.
- Tenant/aggregate trong phạm vi sự cố.
- Mã invariant, phiên bản và quan hệ không đạt.
- Operation, nguồn sự kiện và trạng thái tác động.
- Giá trị quan sát cần thiết, có kiểm soát truy cập.
- Thời điểm, policy version và correlation reference.
- Quyết định containment/repair và người hoặc cơ chế chịu trách nhiệm.

Không đưa token, secret hoặc toàn bộ payload nhạy cảm vào response hay log thông thường.

### 11.3. Cảnh báo theo ý nghĩa và mức độ

Một request vượt hạn mức có thể chỉ tăng metric từ chối. Trạng thái đã commit sai hoặc nguồn quyền bị phá có thể cần cảnh báo ưu tiên cao.

Có thể gom tín hiệu lặp theo incident/aggregate để giảm nhiễu, nhưng vẫn phải giữ được quy mô và diễn biến. Không im lặng bỏ lỗi vì “đã có một cảnh báo” nếu phạm vi đang mở rộng.

## 12. Sửa dữ liệu bằng một kế hoạch có thể kiểm tra

Mục tiêu phục hồi là đưa mô hình trở lại phản ánh đúng sự thật và giữ được quy tắc, đồng thời xử lý nguyên nhân. Mục tiêu không phải chỉ làm biểu thức kiểm tra trả về true.

Một kế hoạch sửa nên có:

```text
incidentReference
affectedScope
sourceOfTruthReferences
snapshotVersion
identifiedCause / remainingUncertainty
proposedChanges
expectedBeforeAfter
invariantsToRecheck
externalEffectsAndPendingOperations
authorization / approvalReference
repairOperationId
stopConditions
reopenCriteria
```

### 12.1. Phân biệt sổ nghiệp vụ và projection

Nếu counter là projection từ các operation có thẩm quyền, có thể cần tính lại từ sổ đúng và sửa projection theo phiên bản.

Nếu chính sổ chứa bản ghi trùng hoặc sai, chỉ tính lại counter từ cùng sổ đó chưa sửa được nguyên nhân. Cần xác định bản ghi nào có căn cứ, bản ghi nào cần điều chỉnh và cách giữ lịch sử.

Không xóa lịch sử tài chính hoặc quyết định chỉ để số tổng khớp. Có thể cần bản ghi điều chỉnh liên kết với sự kiện gốc theo mô hình kế toán/nghiệp vụ của sản phẩm.

### 12.2. Chạy lại cùng kế hoạch không được sửa hai lần

Một repair operation có thể bị retry sau timeout. Cần biết nó chưa chạy, đang chạy hay đã commit.

Dùng định danh ổn định, điều kiện phiên bản và kết quả đã lưu phù hợp. Nếu snapshot đã thay đổi, dừng để đánh giá lại, thay vì ép áp thay đổi cũ.

### 12.3. Thẩm quyền sửa phải tách khỏi quyền thao tác thường

Quyền yêu cầu hoàn không mặc nhiên cho phép sửa sổ, tăng hạn mức hoặc mở lại aggregate.

Nếu cần phê duyệt cho kế hoạch sửa, nó phải gắn với đúng phạm vi, nội dung và phiên bản. Thay số tiền hoặc tenant sau khi duyệt phải tuân theo quy tắc duyệt lại.

Đường repair có thể cần xử lý trạng thái ngoại lệ mà luồng bình thường không cho phép. Điều đó không trao quyền bỏ mọi constraint hoặc chạy mọi câu lệnh tùy ý; cần một phạm vi được xác lập và dấu vết đủ giải thích.

### 12.4. Tiêu chí mở lại

Trước khi gỡ gate, cần xác định:

- Dữ liệu phản ánh đúng nguồn có thẩm quyền.
- Các bất biến liên quan đã được kiểm tra ở mốc nhất quán.
- Operation đang chờ/chưa rõ đã có hướng xử lý.
- Nguyên nhân hoặc đường tạo vi phạm đã được chặn theo phạm vi cần thiết.
- Retry/message cũ không thể tái tạo lỗi.
- Kết quả sửa và quyền mở lại đã được ghi nhận.

Nếu chỉ sửa dữ liệu mà code path còn lỗi, request tiếp theo có thể làm lệch lại ngay.

## 13. Diễn tập tình huống từ phát hiện tới phục hồi

Trở lại snapshot:

```text
C = 1.000.000
R =   800.000
H =   400.000
```

### Trường hợp A: counter giữ ngân sách bị cộng trùng

Đối soát xác nhận:

- Bên ngoài thực sự đã hoàn 800.000.
- Chỉ có một nghĩa vụ đang chờ 200.000.
- Counter H chứa thêm 200.000 do một sự kiện đã bị áp hai lần.
- Chưa có thêm tác động ngoài từ phần sai.

Luồng xử lý:

1. Giữ gate ngăn tạo nghĩa vụ mới trên aggregate.
2. Lưu tham chiếu operation/sự kiện đã bị áp lặp.
3. Sửa nguyên nhân chống trùng hoặc chặn đường đó.
4. Áp kế hoạch điều chỉnh projection có phiên bản và audit.
5. Xác nhận H phản ánh 200.000 thật.
6. Kiểm tra lại `R + H = C` và sự nhất quán với sổ.
7. Xử lý message tồn đọng rồi mở gate theo tiêu chí.

Mở gate không tạo thêm ngân sách. Với R = 800.000 và H = 200.000, yêu cầu hoàn mới dương vẫn phải bị từ chối vì không còn phần được phép.

### Trường hợp B: bên ngoài đã hoàn vượt thật

Đối soát xác nhận bên ngoài đã hoàn tổng 1.200.000, trong khi căn cứ cho phép chỉ là 1.000.000.

Không sửa bằng cách:

- Đặt R xuống 1.000.000.
- Tăng C lên 1.200.000 mà không có căn cứ thu tiền/quyền lợi tương ứng.
- Bỏ xác nhận của khoản vượt.
- Đổi trạng thái thành thất bại để che việc tiền đã ra ngoài.

Cần ghi nhận chênh lệch thật, giữ ngăn tác động mới và xử lý hậu quả theo quy trình. Nếu projection bình thường không biểu diễn được trạng thái ngoại lệ, phải có sổ quan sát/chênh lệch và đường xử lý được kiểm soát để không mất sự thật.

Bất biến nghiệp vụ đã bị phá. Chỉ có thể kết luận phục hồi khi nghĩa vụ, hậu quả và mô hình dữ liệu đã được xử lý theo chính sách có căn cứ; một lần cập nhật counter cho vừa constraint không đủ.

### Trường hợp C: chưa biết khoản 200.000 cuối đã hoàn chưa

Nếu đã gửi lệnh nhưng chưa có kết quả xác định:

- Giữ operation gốc và trạng thái chưa rõ.
- Không trả phần giữ như thể chắc chắn thất bại.
- Không tạo operation thay thế với ID mới.
- Tra cứu hoặc đối soát theo hợp đồng tích hợp.
- Chỉ chuyển phần giữ sang đã hoàn hoặc giải phóng khi đủ căn cứ.

Một quá trình điều tra có thể phát hiện cả lỗi projection lẫn kết quả ngoài chưa rõ. Cần giải quyết từng phần với bằng chứng riêng.

## 14. Kiểm thử hợp đồng phản ứng

Mỗi kiểm thử cần mô tả điều kiện ban đầu, thời điểm phát hiện, trạng thái tác động và dữ liệu cuối cùng.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Input hoặc quyền không hợp lệ | Không tạo operation/tác động, không lộ snapshot ngoài quyền. |
| Actor ngoài quyền cố kích hoạt kiểm tra aggregate | Không thể dùng endpoint để cách ly đối tượng của người khác bằng dữ kiện tự khai. |
| Yêu cầu vượt phần còn lại | Từ chối nhưng không kết luận dữ liệu đang hợp lệ là đã hỏng. |
| Phiên bản cũ | Không tạo tác động từ quyết định đã mất hiệu lực. |
| Atomic update không thành công | Không tiếp tục gửi lệnh ngoài. |
| Unique key trùng cùng nội dung | Trả/xử lý cùng operation theo hợp đồng và quyền hiện hành. |
| Unique key trùng khác nội dung | Không trả một kết quả thành công sai ý nghĩa. |
| Lỗi sau giữ ngân sách, trước tạo operation | Phần giữ và các ghi liên quan rollback phù hợp. |
| Lỗi trước commit outbox | Không để quyết định commit thiếu ý định cần phát. |
| Response bị mất sau commit | Retry không nhân operation hoặc tác động. |
| Snapshot đã vi phạm | Phát hiện đúng phạm vi, chặn thay đổi làm nặng thêm và tạo bằng chứng phù hợp. |
| Sai lệch do đọc lệch thời điểm | Cơ chế xác minh không biến nó thành kết luận hỏng dữ liệu vô căn cứ. |
| Chỉ API bị khóa còn worker đang chạy | Kiểm thử phát hiện đường tạo tác động chưa chịu gate. |
| Ghi sự cố sau rollback thất bại | Không chuyển sang thực hiện nghiệp vụ; không báo giả đã lưu/cách ly. |
| Audit nằm trong transaction bị rollback | Không nhầm nó với dấu vết đã bền vững. |
| Timeout sau gửi lệnh ngoài | Không đánh dấu chắc chắn thất bại hoặc trả ngân sách sớm. |
| Xác nhận ngoài làm lộ khoản vượt | Giữ sự thật và đường xử lý, không bỏ message để counter đẹp. |
| Hủy/hoàn tất/repair lặp | Không cộng hoặc trả ngân sách hai lần. |
| Repair cạnh tranh với cập nhật mới | Phát hiện phiên bản đổi, không ghi đè snapshot cũ. |
| Mở gate rồi nhận message cũ | Không tái tạo vi phạm hoặc lặp tác động. |

### 14.1. Tạo lỗi đúng vị trí

Mô phỏng tiến trình dừng hoặc lỗi tại ranh giới:

```text
sau kiểm tra
sau giữ ngân sách
sau tạo operation
trước/sau commit
sau gửi ra ngoài
trước ghi kết quả
trong lúc cách ly
trong lúc sửa
trước mở gate
```

Một kiểm thử chỉ ném exception ngay đầu hàm không xác nhận được rollback hoặc kết quả của những bước đã diễn ra.

### 14.2. Quan sát cả side effect

Kiểm tra:

- Số operation và reservation.
- Giá trị budget và phiên bản.
- Inbox/outbox.
- Số lệnh ngoài và operation ID tương ứng.
- Audit/sự cố đã thực sự được lưu.
- Gate và quyền tiếp tục của worker.
- Dữ kiện nào còn ở trạng thái chưa rõ.

Response lỗi nhưng lệnh ngoài đã phát không phải bằng chứng “đã ngăn vi phạm”.

Các bảo đảm khóa, constraint, isolation và rollback cần được kiểm tra ở mức tích hợp với database phù hợp. Mock repository không chứng minh được hành vi cạnh tranh thực tế.

## 15. Những cách ứng phó dễ làm hậu quả nặng hơn

| Cách xử lý | Vì sao sai | Hướng xử lý phù hợp |
| --- | --- | --- |
| Catch mọi lỗi rồi trả thành công | Caller không biết ý định có được nhận; che trạng thái thật. | Phân loại lỗi và trạng thái tác động. |
| Log rồi tiếp tục | Điều kiện bảo vệ đã mất nhưng tác động vẫn xảy ra. | Dừng bước phụ thuộc và rollback/containment phù hợp. |
| Retry mọi exception | Có thể nhân tác động hoặc tạo vòng lặp trên dữ liệu hỏng. | Chỉ retry theo loại lỗi và cùng định danh. |
| Clamp counter về 0 hoặc về hạn mức | Che nghĩa vụ và sự thật thay vì sửa nguyên nhân. | Đối soát và điều chỉnh có căn cứ. |
| Trả ngân sách khi timeout | Có thể cấp lại phần đã được dùng bên ngoài. | Giữ trạng thái chưa rõ và đối soát. |
| Đưa audit vào transaction rồi rollback | Mất chính bằng chứng thất bại cần theo dõi. | Thiết kế độ bền và ranh giới ghi nhận rõ. |
| Khóa API rồi coi đã ngăn xong | Worker, batch hoặc lệnh đang bay vẫn có thể tạo tác động. | Áp gate và kiểm tra theo toàn bộ đường liên quan. |
| Tự khóa toàn tenant từ một request bất thường | Có thể gây gián đoạn ngoài phạm vi bằng chứng. | Chọn phạm vi dựa trên dữ kiện được kiểm chứng. |
| Xóa message không áp dụng được | Mất bằng chứng và có thể mất sự thật bên ngoài. | Lưu trạng thái lỗi/chờ xử lý bền vững phù hợp. |
| Sửa tay rồi mở ngay | Nguyên nhân hoặc message cũ có thể làm lệch lại. | Có kế hoạch sửa và tiêu chí mở lại. |

Không phải mọi vi phạm đều do actor độc hại. Bug, dữ liệu chuyển đổi, cấu hình hoặc sự kiện trùng cũng có thể gây ra cùng hậu quả. Việc quy trách nhiệm cần bằng chứng riêng với việc ngăn tác động.

## 16. Bài tập áp dụng

Một service có quy tắc mỗi đơn chỉ được hoàn tối đa số đã thu. Khi tổng vượt hạn mức, handler:

```text
1. Ghi log trong transaction hiện tại.
2. Đặt reservedRefundAmount = 0.
3. Catch exception và trả "refund failed".
4. Worker tự tạo operation ID mới rồi retry sau một phút.
```

Hãy thiết kế lại:

1. Phân biệt request mới vượt hạn mức với dữ liệu đã lưu bị lệch.
2. Chọn phản ứng khi chưa commit và chưa gửi lệnh ngoài.
3. Xử lý trường hợp đã gửi lệnh nhưng kết quả chưa rõ.
4. Xác định những dữ kiện cần lưu sau rollback.
5. Thiết kế gate cho API, worker và đường batch.
6. Viết kế hoạch sửa có snapshot version, operation ID và tiêu chí mở lại.
7. Viết một kiểm thử audit rollback, một kiểm thử timeout ngoài và một kiểm thử repair lặp.
8. Giải thích vì sao không được đặt counter về 0 để làm kiểm tra qua.

Gợi ý tự đánh giá:

- Không biến thiếu thông tin thành kết luận chắc chắn thất bại.
- Không để ngoại lệ hoặc phản hồi lỗi che side effect đã xảy ra.
- Không tăng quyền bằng dữ liệu caller tự khai.
- Giữ đúng nghĩa vụ và sự thật trong lúc cách ly.
- Mọi lần sửa/bù trừ đều có căn cứ và chống lặp.
- Mở lại dựa trên trạng thái đã xác minh, không chỉ vì một cảnh báo đã được đóng.

## 17. Những điểm cần ghi nhớ

Ứng phó với bất biến cần bắt đầu từ **loại vi phạm, thời điểm phát hiện và trạng thái tác động**. Từ chối một request chưa được nhận, rollback một transaction, cách ly dữ liệu đã sai và đối soát kết quả ngoài là những quyết định khác nhau.

Phản ứng tốt vừa ngăn hậu quả tăng, vừa giữ được sự thật để phục hồi. Không xóa nghĩa vụ, bỏ sự kiện thật hoặc sửa counter tùy ý chỉ để điều kiện kiểm tra trả về đúng.

Hợp đồng đầy đủ nối **phát hiện → dừng/rollback → containment → bằng chứng → đối soát/repair → kiểm tra lại → mở lại**, với quyền hạn, phiên bản và idempotency phù hợp ở từng bước.
