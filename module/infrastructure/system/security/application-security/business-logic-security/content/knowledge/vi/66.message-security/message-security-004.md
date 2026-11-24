# Message ordering — Bảo vệ thứ tự xử lý thông điệp

## 1. Thứ tự thông điệp có thể quyết định tính đúng đắn của nghiệp vụ

Một hệ thống có thể xác thực nguồn gửi, kiểm tra schema và chống message trùng nhưng vẫn thực hiện sai nghiệp vụ nếu xử lý thông điệp không đúng quan hệ trước sau.

Ví dụ một đơn hàng có chuỗi sự kiện:

~~~text
41. ShippingApproved
42. ShippingAuthorizationRevoked
43. OrderCancelled
~~~

Nếu kho nhận `OrderCancelled` trước, sau đó nhận `ShippingApproved` cũ và ghi trạng thái thành “được phép giao”, hệ thống có thể gửi hàng cho đơn đã hủy. Kẻ tấn công không nhất thiết phải giả mạo nội dung; họ có thể phát lại sự kiện hợp lệ cũ, kích hoạt retry hoặc lợi dụng đường xử lý bỏ qua một message lỗi.

**Message ordering** trong bảo mật logic nghiệp vụ là việc xác định quan hệ thứ tự có thẩm quyền và bảo vệ các chuyển trạng thái trước thông điệp đến sai thứ tự, trễ, thiếu, trùng hoặc được phát lại.

Mục tiêu không phải buộc mọi thông điệp trong toàn hệ thống đi qua một hàng duy nhất. Mục tiêu là giữ đúng thứ tự tại nơi nghiệp vụ yêu cầu, đồng thời kiểm tra điều kiện hiện tại trước các tác động quan trọng.

### Tình huống xuyên suốt

Order service quản lý quyền giao hàng của một đơn. Warehouse service nhận sự kiện để cập nhật mô hình đọc và chuẩn bị công việc giao hàng.

Các quy tắc ví dụ:

1. Chỉ giao hàng nếu quyền giao còn hợp lệ tại điểm hệ thống chấp nhận bắt đầu thực hiện.
2. Sự kiện phê duyệt cũ không được khôi phục quyền đã bị thu hồi hoặc trạng thái đã hủy.
3. Message thiếu không được bị bỏ qua bằng cách tự tăng con trỏ để “giải phóng hàng đợi”.
4. Replay để dựng lại dữ liệu không được tự tạo thêm lần giao hàng.
5. Thứ tự của một đơn không được bị nhầm với thứ tự của đơn khác hoặc tenant khác.

Trong bài, các số 41, 42, 43 là số thứ tự của luồng sự kiện có thẩm quyền cho một đơn, không phải timestamp và không mặc nhiên bằng version của bản ghi nghiệp vụ.

## 2. Phân biệt thứ tự vận chuyển, thứ tự xử lý và thứ tự nghiệp vụ

### 2.1. Message được giao trước chưa chắc hoàn tất trước

Một broker có thể giữ thứ tự trong một phạm vi nhất định, nhưng ứng dụng vẫn có thể xử lý đảo thứ tự:

~~~text
Consumer nhận:        A → B
Worker bắt đầu:      A → B
Worker hoàn tất:     B → A
Database commit:     B → A
~~~

Nguyên nhân có thể là xử lý song song, lời gọi ngoài có độ trễ khác nhau, retry hoặc chuyển message lỗi sang một tuyến khác.

Do đó, cần hỏi rõ đang bảo đảm thứ tự ở đâu: lúc publish, append vào log, giao cho consumer, bắt đầu xử lý hay commit tác động. Tính chất của một lớp không tự truyền sang các lớp còn lại.

### 2.2. Event và command mang ý nghĩa khác nhau

| Loại thông điệp | Ý nghĩa | Ví dụ | Cách đánh giá khi đến muộn |
| --- | --- | --- | --- |
| Event | Ghi nhận một sự thật đã xảy ra | Quyền giao hàng đã được chấp thuận ở một thời điểm | Giữ ý nghĩa lịch sử; không mặc nhiên còn là quyền hiện tại |
| Command | Đề nghị thực hiện một hành động | Hãy bắt đầu giao đơn này | Kiểm tra quyền, trạng thái, version và thời hạn trước khi chấp nhận |
| Snapshot | Mô tả trạng thái tại một mốc được xác định | Trạng thái đơn sau sequence 43 | Kiểm tra nguồn, mốc nhất quán và cách khởi tạo con trỏ |
| Notification | Thông báo để người hoặc dịch vụ biết | Đơn đã thay đổi | Không tự cấp quyền thực hiện tác động |

Một event tên `ShippingApproved` chứng minh có một lần phê duyệt nếu nguồn và nội dung hợp lệ. Nó không chứng minh quyền đó chưa bị thu hồi tại thời điểm consumer nhận.

Một command được gửi sớm cũng không được quyền chạy vô thời hạn nếu điều kiện chấp nhận đã hết hiệu lực.

### 2.3. Thứ tự toàn cục thường không phải yêu cầu thật

Hai đơn hàng độc lập có thể xử lý song song. Phạm vi thứ tự thường là một aggregate hoặc một luồng nghiệp vụ:

~~~text
(tenantId, aggregateType, aggregateId, streamEpoch)
~~~

Ví dụ: cùng một đơn có thứ tự riêng; một đơn khác có thể tiến triển độc lập.

Nếu một thao tác phụ thuộc nhiều đối tượng, chẳng hạn đơn hàng, thanh toán và tồn kho, cần mô hình hóa điều kiện phối hợp. Không thể so sequence 20 của payment với sequence 15 của order rồi kết luận cái nào xảy ra trước.

## 3. Mô hình đe dọa và business invariant

### 3.1. Những cách thứ tự bị lợi dụng

Một người dùng hoặc tài khoản nội bộ có thể:

- Phát lại event phê duyệt sau event thu hồi.
- Gửi command cũ sau khi đối tượng đã chuyển trạng thái.
- Tạo nhiều request đồng thời để các producer ghi một thứ tự không nhất quán.
- Khiến message quan trọng thất bại để message sau đi qua đường bỏ lỗi.
- Phát message có sequence rất lớn để làm consumer bỏ qua hoặc giữ một buffer khổng lồ.
- Đổi khóa phân vùng hoặc tenant để tách các sự kiện của cùng đối tượng.
- Dùng thao tác replay quản trị để chạy lại tác động đã hoàn tất.

Sự cố mạng, worker chết và vận hành sai cũng có thể tạo cùng điều kiện. Kiểm soát tốt phải xử lý cả tấn công chủ động lẫn lỗi thông thường.

### 3.2. Không làm lùi trạng thái vì dữ liệu cũ

Với một projection yêu cầu áp dụng đầy đủ luồng theo sequence:

~~~text
lastAppliedSequence chỉ tăng theo các sự kiện hợp lệ đã áp dụng.
Không dùng event cũ để ghi đè một trạng thái mới hơn.
~~~

Tuy nhiên, điều này không có nghĩa mọi sự kiện đến muộn đều bị bỏ. Có những sự thật đến muộn nhưng cần hạch toán hoặc điều chỉnh. Cần phân biệt event lịch sử chưa được áp dụng với event đã áp dụng rồi, và phân biệt projection toàn phần với thuật toán cộng dồn hoặc điều chỉnh.

### 3.3. Không bỏ qua prerequisite

Nếu event N yêu cầu đã có N-1, consumer không được áp dụng N chỉ vì nó đến trước. Trường hợp thiếu cần được lưu, chờ, truy hồi hoặc đối soát theo quy trình.

Một message lỗi ở giữa luồng không được biến thành quyền tiếp tục thực hiện những bước phụ thuộc vào nó.

### 3.4. Thứ tự không thay thế kiểm tra trạng thái

Dù đã xử lý đúng 41 rồi 42 rồi 43, consumer có thể từng nhìn thấy trạng thái “được giao” ở bước 41. Điều đó không đủ để tạo một tác động không thể thu hồi nếu Order service hiện đã hủy đơn.

Phải có một điểm chấp nhận hành động được tuần tự hóa với việc thu hồi hoặc hủy. Thứ tự sao chép lịch sử và quyền thực hiện tác động là hai điều cần bảo vệ riêng.

### 3.5. Không chấp nhận danh tính luồng do người gửi tùy ý khai

Sequence, tenant, aggregate ID và epoch phải được gắn với nguồn được xác thực và hợp đồng phát sự kiện. Một trường `sequence=999999` trong JSON không phải bằng chứng đó là phiên bản mới nhất.

Consumer cần giới hạn kích thước, schema và phạm vi trước khi dành tài nguyên cho message. Đừng để một nguồn không có quyền tạo hàng nghìn luồng giả hoặc buffer vô hạn.

## 4. Thiết kế định danh và sequence đúng nghĩa

Một envelope nội bộ có thể gồm:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt_order_0043",
  "eventType": "OrderCancelled",
  "producer": "order-service",
  "tenantId": "tenant_42",
  "aggregateType": "ORDER",
  "aggregateId": "order_781",
  "streamEpoch": "epoch_1",
  "streamSequence": 43,
  "aggregateVersion": 19,
  "occurredAt": "2026-11-22T03:15:00Z",
  "correlationId": "workflow_902",
  "causationId": "cmd_cancel_81"
}
~~~

Các trường có nhiệm vụ khác nhau:

| Trường | Công dụng | Không nên dùng thay cho |
| --- | --- | --- |
| `eventId` | Nhận diện cùng sự kiện khi giao lại | Sequence hoặc quyền nghiệp vụ |
| `streamSequence` | Thứ tự trong luồng được định nghĩa | Thứ tự của aggregate khác |
| `aggregateVersion` | Version trạng thái ở nguồn theo hợp đồng | Số event nếu mỗi thay đổi không sinh đúng một event |
| `streamEpoch` | Phân biệt thế hệ luồng khi có chuyển đổi được kiểm soát | Cách tự động bỏ qua mọi sequence cũ |
| `occurredAt` | Thời điểm sự việc theo nguồn | Bộ đếm thứ tự đáng tin cậy |
| `correlationId` | Truy vết cùng quy trình | Bằng chứng đủ prerequisite |
| `causationId` | Liên hệ nguyên nhân theo mô hình phát sự kiện | Quyền thực thi một command mới |

### 4.1. Sequence phải được cấp cùng transaction nghiệp vụ

Nếu hai producer cùng được cập nhật một đơn, việc cấp sequence phải được tuần tự hóa với chuyển trạng thái bằng khóa, version hoặc cơ chế nhất quán tương đương.

Một mẫu thường dùng:

~~~text
Trong cùng transaction:
    Kiểm tra command và trạng thái hiện tại
    → Chuyển trạng thái đơn
    → Cấp sequence của luồng
    → Ghi event vào outbox
    → Commit
~~~

Outbox tránh khoảng trống giữa commit nghiệp vụ và publish. Publisher vẫn có thể giao lại hoặc phát sai thứ tự nếu chạy song song không có kiểm soát; sequence giúp consumer phát hiện chứ không tự làm vận chuyển đúng thứ tự.

Không cấp sequence bằng một bộ đếm rời rạc rồi giả định chắc chắn không có khoảng trống khi transaction rollback. Nếu giao thức yêu cầu liền mạch, nguồn phải đáp ứng hoặc định nghĩa rõ cách giải thích khoảng trống.

### 4.2. Một aggregate version có thể tương ứng nhiều event

Một transaction có thể thay đổi aggregate một lần nhưng phát nhiều event. Nếu dùng aggregate version như sequence liền mạch, consumer có thể coi event thứ hai là trùng và bỏ mất nó.

Cần một hợp đồng rõ: sequence theo từng event, cặp version và thứ tự trong transaction, hoặc cơ chế đóng gói tương đương. Không tự suy ra từ tên field.

### 4.3. Luồng đã lọc không nhất thiết có số liên tiếp

Nếu consumer chỉ đăng ký `OrderCancelled`, nó không nhận các event 41 và 42. Không được yêu cầu nó chờ đủ mọi số của một luồng mà nó không được cấp toàn bộ.

Các lựa chọn gồm nhận đầy đủ luồng cần thiết, dùng sequence riêng cho feed đã lọc, nhận watermark có ý nghĩa rõ, hoặc đọc trạng thái hiện tại từ nguồn. Thiết kế phải chọn trước; không biến mọi khoảng trống thành lỗi an ninh rồi chặn vô hạn.

## 5. Consumer áp dụng luồng đầy đủ theo thứ tự

Phần này giả sử consumer nhận đầy đủ một luồng có sequence liền mạch theo hợp đồng. Các feed đã lọc cần dùng cơ chế phù hợp như đã nêu ở phần trước.

### 5.1. Dữ liệu tối thiểu

Consumer thường cần:

~~~text
StreamCursor:
    consumerName, tenantId, aggregateId, streamEpoch
    lastAppliedSequence, projectionVersion

Inbox:
    eventId, streamIdentity, streamSequence
    payloadFingerprint, processingState
    payload hoặc tham chiếu bền vững tới payload

GapRecord:
    streamIdentity, expectedSequence, firstObservedAt
    bufferedCount, recoveryState
~~~

Ràng buộc hữu ích gồm unique theo event ID trong phạm vi nguồn và unique theo danh tính luồng cùng sequence. Cần xác định phạm vi event ID thay vì mặc định mọi producer đều dùng ID toàn cục.

Nếu cùng sequence nhưng khác event ID hoặc nội dung, không coi đó là một lần giao lại bình thường. Có thể có lỗi nguồn, sai định tuyến hoặc can thiệp dữ liệu; dừng tiến triển của luồng liên quan và đối soát bằng chứng.

### 5.2. Ba trường hợp của sequence

Với `lastAppliedSequence = 40`:

| Message nhận được | Phân loại | Xử lý |
| --- | --- | --- |
| Sequence 41 | Phần tử tiếp theo | Áp dụng nếu danh tính, schema và điều kiện đều hợp lệ |
| Sequence 43 | Có khoảng trống | Lưu chờ bền vững, tìm 41 và 42; chưa cập nhật projection tới 43 |
| Sequence 39 hoặc 40 | Cũ hoặc giao lại | Đối chiếu bằng chứng đã áp dụng; không ghi đè trạng thái mới |

Nếu message cũ không còn đủ bằng chứng nhận diện vì dữ liệu inbox đã được dọn, xử lý theo chính sách đối soát và retention. Không tự kết luận nội dung bất kỳ có sequence thấp đều là bản sao hợp lệ.

### 5.3. Mã giả cho ranh giới transaction

Đoạn sau là mã giả theo phong cách Java cho cập nhật projection cục bộ, không thực hiện giao hàng hoặc gọi hệ thống ngoài.

~~~java
HandleResult handleOrderEvent(RawMessage raw) {
    VerifiedEvent event = ingress.verifySourceSchemaAndScope(raw);

    HandleResult result = transaction.execute(() -> {
        StreamCursor cursor = cursors.lockFor(event.streamIdentity());
        lineage.requireExpectedEpoch(cursor, event);

        // Chống trùng theo event và phát hiện xung đột cùng sequence.
        InboxRecord record = inbox.receiveOrLoadAndVerify(event);

        if (record.isApplied()) {
            return HandleResult.alreadyApplied();
        }

        long expected = cursor.lastAppliedSequence() + 1;

        if (event.streamSequence() < expected) {
            return reconciliation.recordUnverifiedOldEvent(record, cursor);
        }

        if (event.streamSequence() > expected) {
            if (!gapPolicy.canBuffer(cursor, event)) {
                return quarantine.recordGapOverflow(record, cursor);
            }
            inbox.markBuffered(record);
            gaps.recordMissingRange(cursor, event);
            return HandleResult.durablyBuffered();
        }

        // Chỉ cập nhật dữ liệu trong cùng database transaction.
        projection.applyNext(event);
        inbox.markApplied(record);
        cursor.advanceTo(event.streamSequence());

        // Đánh thức bộ xử lý phần đã buffer sau khi commit.
        outbox.append(DrainBufferedStreamRequested.forCursor(cursor));
        return HandleResult.applied();
    });

    // Chỉ xác nhận với broker khi phần việc tương ứng đã được lưu bền vững.
    return result;
}
~~~

Các helper phải xử lý unique conflict, khóa và bản ghi đồng thời đúng với cơ sở dữ liệu. Nếu phát hiện xung đột và rollback transaction, bằng chứng cách ly hoặc cảnh báo cần được lưu qua đường xử lý lỗi phù hợp; không giả định log nằm trong transaction rollback vẫn tồn tại.

Consumer chỉ acknowledge message khi đã áp dụng hoặc chuyển trách nhiệm sang một buffer, hàng đợi đối soát hay vùng cách ly bền vững có cơ chế tiếp tục xử lý. Nếu chỉ để message trong RAM rồi acknowledge, tiến trình chết có thể làm mất prerequisite.

### 5.4. “Đã nhận” khác “đã áp dụng”

Message 43 có thể đã được lưu trong inbox nhưng chưa áp dụng. Khi 41 và 42 tới, bộ drain phải tiếp tục xử lý 43.

Không dùng một cờ `seen=true` để bỏ qua mọi message đã nằm trong inbox. Cần phân biệt ít nhất các ý nghĩa `RECEIVED`, `BUFFERED`, `APPLIED` và `QUARANTINED` theo mô hình của hệ thống.

Tương tự, broker acknowledge không đồng nghĩa một effect nghiệp vụ đã hoàn tất.

### 5.5. Cursor, projection và inbox phải nhất quán

Nếu cập nhật projection rồi chết trước khi lưu cursor, retry có thể áp dụng lại. Nếu tăng cursor trước khi cập nhật projection, lần retry có thể bỏ qua phần chưa làm.

Với dữ liệu nằm trong cùng cơ sở dữ liệu, đặt việc áp dụng event, trạng thái inbox, cursor và outbox liên quan trong cùng transaction. Các consumer song song của cùng luồng cần được tuần tự hóa bằng khóa hoặc cập nhật có điều kiện.

Giới hạn số event drain trong một lần để một luồng lớn không giữ tài nguyên quá lâu. Sau khi commit, có thể tiếp tục theo lô nhỏ với cursor hiện tại.

## 6. Khoảng trống, buffer và khôi phục luồng

### 6.1. Không chờ vô hạn và không tự nhảy sequence

Khi nhận 43 trong lúc đang chờ 41, cần ghi thời điểm phát hiện khoảng trống, số message chờ và trạng thái phục hồi.

Chính sách có thể:

1. Chờ trong khoảng ngắn phù hợp độ trễ bình thường.
2. Yêu cầu nguồn phát lại phần thiếu hoặc đọc từ log có thẩm quyền.
3. Khi vượt hạn, chuyển luồng sang trạng thái cần can thiệp và phát cảnh báo.
4. Tiếp tục các luồng độc lập trong giới hạn tài nguyên.
5. Khôi phục bằng replay hoặc snapshot có kiểm soát.

Không sửa `lastAppliedSequence = 42` chỉ để event 43 được chạy. Thao tác đó đang tuyên bố rằng 41 và 42 đã được xử lý dù chưa có bằng chứng.

### 6.2. Dead-letter không xóa quan hệ phụ thuộc

Nếu event 42 không đọc được schema và bị chuyển sang dead-letter, event 43 có thể vẫn phụ thuộc vào nó. Đưa message lỗi ra khỏi queue không làm prerequisite tự hoàn tất.

Cần biết luồng nào bị chặn, ai xử lý, khả năng bổ sung decoder hoặc cách truy hồi trạng thái. Không đặt tùy chọn “skip poison message” chung cho mọi event trong một quy trình có thứ tự bắt buộc.

### 6.3. Giới hạn tài nguyên chờ

Buffer cần giới hạn theo số message, tổng dung lượng, độ lệch sequence và tuổi chờ, với phân bổ theo tenant hoặc luồng phù hợp.

Một event có sequence rất xa không được khiến consumer cấp phát bộ nhớ tương ứng với toàn bộ khoảng trống. Có thể ghi nhận khoảng thiếu gọn và cách ly phần vượt ngưỡng.

Áp dụng backpressure hoặc hạn chế nguồn có vấn đề, đồng thời giữ khả năng xử lý các luồng độc lập. Không để một đơn hàng lỗi chặn mọi đơn của toàn hệ thống nếu nghiệp vụ không đòi hỏi thứ tự toàn cục.

### 6.4. Khởi tạo lại từ snapshot

Một snapshot dùng để phục hồi phải xác định:

- Nguồn và danh tính luồng được tin cậy.
- State tương ứng với high-watermark nào.
- Epoch và version schema.
- Cách bảo đảm snapshot và watermark nhất quán.
- Cách tiếp tục nhận các event sau mốc đó.

Nếu state lấy ở một thời điểm còn watermark lấy ở thời điểm khác, consumer có thể bỏ qua event chưa có trong state hoặc áp dụng lặp.

Nạp snapshot để dựng projection không có nghĩa chạy lại mọi tác động trong lịch sử. Những nghĩa vụ bên ngoài chưa hoàn tất cần được đối soát bằng effect record riêng.

## 7. Đúng thứ tự vẫn cần chấp nhận hành động tại nguồn có thẩm quyền

### 7.1. Projection lịch sử không phải giấy phép hiện tại

Giả sử consumer đã buffer event 43 nhưng đang áp dụng 41 để lấp khoảng trống. Sau bước 41, projection tạm thể hiện “đã được phê duyệt giao”.

Nếu mỗi lần projection vào trạng thái đó đều gọi hãng vận chuyển, hệ thống có thể giao một đơn mà nguồn hiện đã hủy. Ngay cả khi chưa nhìn thấy 43, consumer cũng không thể chứng minh không có quyết định thu hồi nào đã commit ở nguồn.

Vì vậy, không nối một bước dựng lại lịch sử trực tiếp với tác động không thể thu hồi. Event có thể kích hoạt đề nghị xử lý; quyền tạo tác động phải được chấp nhận theo điều kiện hiện tại.

### 7.2. Tuần tự hóa chấp nhận giao hàng với hủy đơn

Một thiết kế có thể đặt tại Order service một thao tác `reserveDispatch`:

~~~text
Trong một transaction có thẩm quyền:
    Khóa hoặc kiểm tra version đơn
    → Kiểm tra quyền giao còn hợp lệ
    → Kiểm tra chưa hủy, chưa có dispatch cùng quyền lợi
    → Tạo reservation/effect intent duy nhất
    → Chuyển sang DISPATCH_RESERVED
    → Ghi outbox
    → Commit
~~~

Command phát sinh từ phê duyệt cũ có thể mang expected version. Nếu nguồn đã thu hồi hoặc hủy, command không còn thỏa điều kiện và phải bị từ chối hoặc yêu cầu đánh giá lại.

Cả thao tác hủy lẫn nhận giao phải tuân thủ cùng ranh giới nhất quán. Khi hai thao tác chạy đồng thời:

- Nếu hủy được chấp nhận trước, reservation giao phải thất bại.
- Nếu reservation giao được chấp nhận trước, yêu cầu hủy tiếp theo phải theo chính sách cho giai đoạn đó, chẳng hạn `CANCEL_REQUESTED`, dừng giao hoặc bù trừ có kiểm soát.

Không hứa rằng thay đổi trạng thái sau khi một lệnh đã phát ra ngoài sẽ thu hồi tức thì được mọi tác động. Điểm không thể thu hồi và ý nghĩa “hủy thành công” phải được định nghĩa rõ.

### 7.3. Không giữ transaction chờ mạng để tạo cảm giác nguyên tử

Reservation và outbox có thể commit cục bộ; worker gọi hãng vận chuyển sau đó với effect key ổn định. Không giữ khóa cơ sở dữ liệu trong suốt một lời gọi mạng rồi coi đó là transaction chung với bên ngoài.

Nếu lời gọi timeout sau khi có thể đã tạo vận đơn, xử lý kết quả không xác định và đối soát. Không tạo reservation hoặc effect key mới chỉ vì message được giao lại.

### 7.4. Trạng thái hết hạn phải được kiểm tra nơi sử dụng

Với quyền truy cập hoặc ưu đãi có thời hạn, kiểm tra thời hạn ở server trước khi chấp nhận sử dụng. Event hết hạn bị giao muộn không được kéo dài quyền chỉ vì projection chưa cập nhật.

Event order hỗ trợ đồng bộ trạng thái; điều kiện bảo vệ cần thiết vẫn phải nằm ở nơi có quyền quyết định sử dụng quyền lợi.

## 8. Quan hệ nhân quả giữa nhiều aggregate

Payment service có thể phát `PaymentCaptured`, còn Order service quản lý quyền giao. Hai luồng có sequence độc lập.

Không giải quyết bằng cách gộp timestamp của hai dịch vụ rồi sắp xếp. Cần xác định bằng chứng và điều kiện phối hợp, chẳng hạn:

~~~text
Cho phép chuyển đơn sang READY_TO_SHIP khi:
    thanh toán được xác minh cho đúng đơn, tenant và tiền tệ
    AND số tiền đáp ứng chính sách
    AND tồn kho được giữ hợp lệ nếu nghiệp vụ yêu cầu
    AND đơn chưa bị hủy
    AND quyết định phê duyệt còn hiệu lực
~~~

Order service có thể lưu tham chiếu bằng chứng và dùng saga hoặc workflow với trạng thái rõ. Message đến trước được lưu chờ hoặc đánh giá lại khi prerequisite có mặt.

`correlationId` chỉ giúp tìm các message liên quan. Nó không chứng minh một khoản thanh toán thuộc đúng khách hàng, đủ tiền hoặc chưa bị đảo.

Khi có sự kiện muộn làm thay đổi kết luận trước đó, cần chuyển trạng thái hoặc nghiệp vụ bù trừ theo quyền. Không tự xóa sự thật cũ để làm lịch sử trông như đã luôn đúng thứ tự.

## 9. Chọn chiến lược ordering theo ý nghĩa dữ liệu

Không phải mọi consumer đều cần cùng một thuật toán.

| Chiến lược | Phù hợp khi | Điều kiện cần giữ |
| --- | --- | --- |
| Áp dụng liền mạch theo luồng | Các chuyển trạng thái phụ thuộc thứ tự và consumer nhận đầy đủ luồng | Sequence đúng hợp đồng, buffer khoảng trống, transaction cho cursor |
| Nhận snapshot mới hơn | Chỉ cần trạng thái hiện tại đầy đủ | Version từ nguồn có thẩm quyền, snapshot tự đủ, không bỏ mất nghĩa vụ riêng |
| Cập nhật giao hoán | Kết quả độc lập thứ tự của các phần tử hợp lệ | Mỗi phần tử có định danh chống trùng; mọi invariant liên quan cũng được bảo vệ |
| Command với expected version | Nguồn có thẩm quyền quyết định một chuyển trạng thái | Kiểm tra quyền, version, điều kiện và idempotency trong cùng ranh giới |
| Workflow chờ prerequisite | Quy trình phụ thuộc nhiều luồng độc lập | Bằng chứng đúng đối tượng, trạng thái chờ, timeout và bù trừ rõ ràng |

### 9.1. Khi nào có thể bỏ bản cập nhật cũ?

Nếu mỗi message là snapshot đầy đủ của một hồ sơ hiển thị, có version tăng đơn điệu từ nguồn và không chứa nghĩa vụ tác động riêng, consumer có thể chỉ giữ snapshot mới nhất.

Điều này khác với các event delta như “trừ 100 đơn vị” rồi “cộng 20 đơn vị”. Bỏ event cũ chỉ vì đã thấy version cao có thể làm sai số dư.

Tombstone xóa cũng cần ngữ nghĩa version tương ứng. Một bản snapshot cũ đến sau không được làm sống lại đối tượng đã xóa hoặc quyền đã bị thu hồi.

### 9.2. Giao hoán không có nghĩa bỏ mọi kiểm soát

Cộng các phần tử độc lập có thể không phụ thuộc thứ tự, nhưng vẫn phải chống cộng trùng. Nếu nghiệp vụ cấm số dư âm hoặc có hạn mức tại từng thời điểm, việc các phép cộng cuối cùng giao hoán không đủ để bỏ kiểm tra tuần tự ở nơi chấp nhận giao dịch.

Chỉ dùng chiến lược này khi có thể giải thích rõ điều gì độc lập thứ tự và invariant nào được bảo vệ ở lớp khác.

### 9.3. Không dùng timestamp làm quy tắc thắng mặc định

Các máy có thể lệch đồng hồ. Event có thể được tạo trước nhưng publish sau, hoặc ghi nhận muộn một sự thật xảy ra sớm hơn. Client cũng có thể tự khai thời điểm.

Cần tách thời điểm xảy ra, thời điểm nguồn ghi nhận và thời điểm consumer nhận. “Timestamp lớn nhất thắng” chỉ phù hợp nếu đó là chính sách dữ liệu đã được thiết kế và có nguồn thời gian đáng tin cậy tương ứng.

Không dùng thời điểm nhận làm thứ tự phê duyệt, thu hồi hoặc hạch toán.

### 9.4. Event cũ vẫn có thể là sự thật cần xử lý

Một kết quả thanh toán được xác nhận muộn vẫn có thể tạo nghĩa vụ đối soát. Không vứt bỏ nó chỉ vì quá một TTL dành cho lệnh yêu cầu hành động.

Thời hạn command có thể giới hạn lúc được chấp nhận thực thi. Thời gian lưu và giá trị của event lịch sử cần được thiết kế riêng. Nếu một fact đến muộn làm phát sinh điều chỉnh, dùng nghiệp vụ điều chỉnh có audit thay vì cố chèn nó vào quá khứ rồi chạy lại mọi tác động.

## 10. Định tuyến, song song hóa và thế hệ luồng

### 10.1. Giữ cùng đối tượng trong cùng miền điều phối

Khóa định tuyến thường cần được tạo từ định danh ổn định như tenant và aggregate. Người dùng không được tùy ý đổi routing key để khiến hai event của cùng đơn đi qua các đường không phối hợp.

Cần kiểm tra quan hệ giữa routing metadata và envelope. Một trường `producer` trong JSON không thay thế danh tính kết nối hoặc cơ chế xác thực nguồn.

Nếu phụ thuộc bảo đảm của broker, phải hiểu phạm vi thực tế của nó: cấu hình producer, phân vùng, cách giao cho consumer và hành vi khi retry hoặc tái phân công. Không suy ra “cùng topic” là có thứ tự toàn cục.

### 10.2. Tuần tự trong một luồng, song song giữa các luồng

Có thể phân phối nhiều đơn cho nhiều worker trong khi chỉ cho một worker cập nhật cursor của một đơn tại một thời điểm.

Dùng khóa trong bộ nhớ chỉ bảo vệ cùng tiến trình. Nếu nhiều máy có thể xử lý một luồng, cần khóa, version hoặc cơ chế điều phối tại nơi có thẩm quyền.

Khi có worker cũ tiếp tục sau khi lease hết hạn, fence hoặc cập nhật có điều kiện ngăn ghi stale ở kho kiểm tra chúng. Nếu có lời gọi ngoài, cần kiểm soát tác động riêng; ordering nội bộ không tự chặn được request đã phát đi.

### 10.3. Epoch không phải nút bỏ lịch sử

Một lần migration có thể đổi cách đánh số hoặc chuyển nguồn phát. Nếu sequence bắt đầu lại, cần định danh thế hệ và quy trình chuyển đổi có thẩm quyền.

Consumer không được tự chấp nhận epoch mới chỉ vì message có timestamp mới hơn. Cần biết thế hệ nào được phép, trạng thái khởi tạo, watermark bàn giao và cách xử lý phần cũ còn đang truyền.

Bản ghi của epoch cũ đến muộn không được ghi đè state ở epoch mới. Cũng không được dùng epoch mới để chạy lại các quyền lợi hoặc giao dịch đã có tác động; khóa nghiệp vụ có thể cần tồn tại xuyên qua nhiều thế hệ kỹ thuật.

### 10.4. Retention và khôi phục ảnh hưởng bằng chứng thứ tự

Nếu inbox, log nguồn hoặc cursor bị dọn không đồng bộ, consumer có thể mất khả năng phân biệt bản sao với sự kiện chưa xử lý.

Chính sách retention phải phù hợp cửa sổ replay, đối soát và thời gian có thể phục hồi. Có thể giữ bằng chứng tối thiểu hoặc snapshot đáng tin cậy, nhưng không xóa lớp cuối cùng đang chứng minh tác động đã được thực hiện.

Sau khi phục hồi bản sao lưu cũ, không mặc định cursor thấp đồng nghĩa mọi tác động sau đó chưa xảy ra. Hệ thống ngoài có thể đã hoàn tất giao hàng hoặc thanh toán. Cần đối soát effect record và bằng chứng phía nhận trước khi cho phép replay tạo tác động.

## 11. Kiểm thử tình huống tấn công logic

Kiểm thử nên điều khiển được thứ tự giao, thời điểm commit, retry, khoảng trống và trạng thái ở nguồn có thẩm quyền.

| Tình huống | Cách kích hoạt | Kết quả cần chứng minh |
| --- | --- | --- |
| Thu hồi đến trước phê duyệt | Giao 42 rồi 41 trong luồng đầy đủ | Không dùng phê duyệt cũ để khôi phục quyền hiện tại |
| Hủy đến trước các event còn thiếu | Giao 43, 41, 42 | Buffer và drain đúng; không tạo giao hàng từ trạng thái lịch sử trung gian |
| Trùng event | Giao lại cùng event ID và nội dung | Không áp dụng projection hoặc effect thêm lần nữa |
| Cùng sequence khác nội dung | Phát hai event mâu thuẫn cho cùng slot | Cách ly hoặc dừng luồng, không chọn ngẫu nhiên một bản |
| Sequence quá xa | Gửi số rất lớn so với cursor | Không nhảy cursor hoặc cấp phát buffer không giới hạn |
| Thiếu event ở giữa | Giữ lại 42 nhưng giao 43 | Luồng phụ thuộc chờ và có phục hồi, không tự coi prerequisite đã hoàn tất |
| Event giữa luồng vào dead-letter | Làm 42 lỗi schema | Không cho 43 bỏ qua phụ thuộc bằng đường skip chung |
| Feed chỉ nhận một số event | Không đăng ký 41 và 42 | Không áp dụng thuật toán liền mạch sai hợp đồng; có cơ chế feed phù hợp |
| Hai consumer cùng một luồng | Cho cùng đọc cursor 40 | Chỉ một cập nhật hợp lệ, cursor và projection không lệch |
| Song song hoàn tất đảo thứ tự | Cho 42 hoàn tất trước 41 | Kiểm soát commit ngăn áp dụng sai thứ tự |
| Chết giữa cập nhật dữ liệu | Dừng sau thay projection nhưng trước cursor | Transaction giữ tất cả hoặc rollback; retry không áp dụng lặp |
| Chết sau lưu buffer | Acknowledge rồi dừng tiến trình | Buffer bền vững còn và có tiến trình tiếp tục xử lý |
| Replay dựng projection | Phát lại toàn bộ lịch sử trong môi trường phục hồi | Không gửi lại lệnh giao hàng hay thanh toán chỉ vì rebuild |
| Command dùng approval cũ | Nguồn đã hủy nhưng consumer chưa cập nhật | Nguồn từ chối reservation theo trạng thái hoặc version hiện tại |
| Hủy đua với nhận giao | Hai request vào cùng ranh giới chấp nhận | Kết quả theo thứ tự commit và chính sách điểm tác động |
| Nhiều aggregate | Payment đến trước Order hoặc ngược lại | Workflow xác minh prerequisite, không so sequence khác miền |
| Sửa tenant hoặc routing key | Envelope và tuyến không khớp | Không cập nhật luồng ngoài phạm vi hoặc tạo luồng giả có quyền |
| Event epoch cũ | Giao lại sau chuyển đổi thế hệ | Không làm lùi trạng thái hoặc tái tạo quyền lợi |
| Epoch mới không được phép | Gửi epoch tùy ý để reset cursor | Bị chặn theo lineage có thẩm quyền |
| Timestamp sai lệch | Đưa event cũ có giờ lớn hơn | Không thắng chỉ nhờ timestamp |
| Sự thật tài chính đến muộn | Fact hợp lệ vượt thời hạn command thông thường | Đối soát đúng nghĩa vụ, không vứt bỏ theo TTL sai mục đích |
| Snapshot không nhất quán | State và watermark lệch nhau | Không chấp nhận như điểm khởi tạo đáng tin cậy |
| Khôi phục DB cũ | Cursor thấp hơn tác động đã có ở bên ngoài | Không phát lại mù quáng; có đối soát trước tác động |
| Một luồng bị kẹt | Tạo gap dài ở một đơn | Không làm cạn tài nguyên và chặn mọi luồng độc lập |

Kiểm thử transaction và concurrency cần dùng cơ sở dữ liệu thực tế của hệ thống. Bộ giả lập vận chuyển nên cho phép giao lại, đảo thứ tự, trì hoãn và làm lỗi tại điểm xác định.

Sau mỗi kịch bản, kiểm tra cả cursor, inbox, buffer, projection, trạng thái nguồn và số effect thực tế. Một projection cuối cùng đúng không đủ nếu trong quá trình xử lý hệ thống đã giao hàng sai một lần.

## 12. Quan sát và xử lý khi luồng mất thứ tự

### 12.1. Chỉ số hữu ích

Theo dõi ít nhất các nhóm sau:

- Số message đến sai thứ tự, giao lại và xung đột danh tính.
- Số luồng đang có gap, tuổi gap cũ nhất và số phần tử đang buffer.
- Thời gian từ nhận event tới áp dụng, theo tenant và loại nghiệp vụ.
- Số message cần đối soát, cách ly hoặc đang ở dead-letter.
- Số command bị từ chối vì version cũ hoặc quyền đã bị thu hồi.
- Số lần đổi epoch, nạp snapshot và replay quản trị.
- Chênh lệch giữa trạng thái nguồn, projection và tác động bên ngoài.

Nhiều message đến sai thứ tự không tự chứng minh bị tấn công. Có thể là hành vi vận chuyển bình thường. Ngược lại, cùng sequence khác nội dung hoặc nhiều lần cố reset epoch cần được điều tra theo mức độ rủi ro.

Log cần nối được nguồn đã xác thực, tenant, aggregate, epoch, sequence, event ID, correlation ID và quyết định xử lý. Không ghi token hoặc dữ liệu nhạy cảm không cần thiết.

### 12.2. Quy trình phục hồi có kiểm soát

Khi một luồng bị chặn hoặc có dấu hiệu sai thứ tự:

1. Xác định đúng luồng và phạm vi tác động; hạn chế hành động nguy hiểm của luồng đó khi cần.
2. Đối chiếu hợp đồng feed: đầy đủ hay đã lọc, sequence được cấp theo cách nào.
3. Kiểm tra log nguồn, outbox, broker, inbox và dead-letter để tìm phần thiếu hoặc xung đột.
4. Xác minh trạng thái hiện tại và các tác động đã có, đặc biệt với hệ thống ngoài.
5. Replay phần thiếu hoặc nạp snapshot nhất quán qua quy trình được cấp quyền.
6. Tiếp tục drain bằng kiểm tra sequence và invariant như đường xử lý thường.
7. Ghi người thao tác, lý do, mốc phục hồi và bằng chứng kết quả.

Không sửa cursor bằng tay để làm biểu đồ hết đỏ. Nếu cần bỏ qua một phần dữ liệu do chính sách nghiệp vụ cho phép, phải có quyết định được ghi nhận, giải thích trạng thái thay thế và xử lý các nghĩa vụ liên quan. Đó không còn là một thao tác kỹ thuật vô hại.

## 13. Đi qua ví dụ 43 → 41 → 42

Giả sử projection đang ở sequence 40, trong khi Order service đã commit hủy đơn ở 43.

1. Consumer nhận 43, xác thực nguồn và lưu `BUFFERED`. Cursor vẫn là 40.
2. Consumer nhận 41, áp dụng vào projection trong transaction và đưa cursor lên 41.
3. Nếu quá trình này tạo một đề nghị chuẩn bị giao, đề nghị đó phải đi qua nguồn chấp nhận có thẩm quyền. Order service hiện đã hủy nên không cấp reservation.
4. Consumer nhận 42, áp dụng thu hồi và tăng cursor lên 42.
5. Bộ drain lấy 43 đã lưu, áp dụng hủy và đưa cursor lên 43.
6. Bản sao của 41 đến sau được đối chiếu như event đã áp dụng; không ghi đè trạng thái hủy.
7. Một lần rebuild projection sau đó cũng không tạo thêm lệnh giao hàng.

Điểm bảo vệ là sự kết hợp của hai lớp: projection tiến triển theo hợp đồng của luồng, còn tác động mới chỉ được chấp nhận khi điều kiện hiện tại cho phép. Ordering, idempotency, quyền theo đối tượng và state machine cùng giữ cho một message hợp lệ trong quá khứ không trở thành quyền thực hiện sai nghiệp vụ ở hiện tại.
