# Schedule modification — Bảo vệ việc thay đổi lịch chạy

## 1. Vì sao sửa lịch là một thao tác nghiệp vụ nhạy cảm?

Một lịch chạy quyết định khi nào hệ thống đóng kỳ kế toán, chi trả cho merchant, hết hạn quyền truy cập hoặc thực hiện một đợt xử lý dữ liệu. Thay đổi thời điểm có thể làm thay đổi kết quả nghiệp vụ ngay cả khi loại job và mã xử lý không đổi.

Ví dụ, người có quyền sửa lịch có thể:

- Đẩy một đợt chi trả lên trước thời điểm hoàn tất phê duyệt.
- Tăng tần suất để tạo nhiều lần sử dụng hạn mức hoặc gây quá tải.
- Lùi vô hạn một tác vụ thu hồi quyền hoặc kiểm tra gian lận.
- Đổi múi giờ khiến tác vụ chạy ở ngày nghiệp vụ khác.
- Bật chạy bù để thực hiện hàng trăm kỳ mà người phê duyệt không dự kiến.
- Sửa phạm vi đối tượng cùng lúc sửa giờ chạy để tác vụ chạm tới dữ liệu ngoài quyền.

**Schedule modification** là thay đổi có kiểm soát đối với cấu hình lịch, có thể gồm quy tắc lặp, múi giờ, thời gian bắt đầu và kết thúc, trạng thái bật/tắt, chính sách chạy bù và giới hạn thực thi.

Trong bảo mật logic nghiệp vụ, mục tiêu là bảo đảm một thay đổi lịch chỉ có hiệu lực đúng quyền, đúng phạm vi đã được chấp thuận và không phá vỡ các business invariant. Lịch chạy được sửa thành công không đồng nghĩa các job đã tạo trước đó tự biến mất hoặc một lệnh bên ngoài đang chạy có thể bị thu hồi.

### Tình huống xuyên suốt

Nền tảng thanh toán có lịch `DAILY_PAYOUT` cho từng merchant, chạy lúc 09:00 theo `Asia/Ho_Chi_Minh`. Mỗi ngày nghiệp vụ chỉ được tạo một đợt chi trả chuẩn cho merchant đó.

Merchant muốn đổi sang 08:00 từ một ngày xác định. Việc sửa lịch phải giữ các quy tắc:

1. Chỉ người được phân quyền trong đúng tenant và merchant mới được đề nghị thay đổi.
2. Lịch chi trả quan trọng cần phê duyệt độc lập theo chính sách.
3. Thay đổi chỉ được áp dụng cho nội dung và thời điểm hiệu lực đã được chấp thuận.
4. Một ngày nghiệp vụ không được chi trả hai lần vì lịch cũ và mới cùng phát sinh occurrence.
5. Job đã nhận trách nhiệm hoặc đã gửi lệnh thanh toán phải được xử lý theo quy trình riêng.
6. Hạn mức, điều kiện giữ tiền và các bước phê duyệt giao dịch vẫn phải được kiểm tra khi chi trả.

Các quy tắc và mốc thời gian trong bài là ví dụ thiết kế, không phải một chính sách bắt buộc cho mọi hệ thống.

## 2. Mô hình dữ liệu: tách lịch, phiên bản và lần chạy

Không nên xem lịch là một dòng chỉ có `cronExpression` và `enabled`. Để xử lý thay đổi an toàn, cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Schedule | Danh tính ổn định của lịch trong một phạm vi nghiệp vụ | Lịch chi trả chuẩn của merchant M |
| Schedule revision | Một cấu hình lịch và khoảng hiệu lực đã được lưu | Revision 12 chạy 09:00, revision 13 chạy 08:00 |
| Change proposal | Đề nghị thay đổi, chưa mặc nhiên có quyền thực thi | Yêu cầu đổi giờ từ ngày D |
| Approval | Quyết định chấp thuận một nội dung cụ thể | Người duyệt, fingerprint, phạm vi, thời hạn |
| Occurrence | Một lần đến hạn hoặc kỳ mà lịch dự định xử lý | Đợt chi trả chuẩn của ngày D |
| Job | Công việc kỹ thuật thực hiện occurrence | Công việc trong hàng đợi |
| Attempt | Một lần thử chạy job | Lần đầu hoặc retry |
| Business effect | Tác động nghiệp vụ cần bảo vệ | Tạo đợt chi trả hoặc gửi lệnh thanh toán |

Revision cho biết lịch nào tạo ra kế hoạch. Nó không nên tự tạo ra quyền thực hiện lại một kỳ đã xử lý.

### 2.1. Khóa occurrence phải phản ánh nghiệp vụ

Với ví dụ chi trả một lần mỗi ngày:

~~~text
UNIQUE(tenantId, merchantId, payoutPurpose, businessDate)
~~~

Nếu khóa chỉ là `(scheduleId, revision, scheduledFor)`, việc đổi giờ có thể tạo một occurrence mới khác khóa nhưng vẫn chi trả lần thứ hai trong cùng ngày.

Ngược lại, hệ thống thật sự cho phép nhiều đợt trong ngày cần định danh thêm phiên hoặc loại đợt theo quy tắc được phê duyệt. Không chọn khóa quá rộng khiến các lần chạy hợp lệ bị chặn.

### 2.2. Phạm vi thay đổi phải tách khỏi payload thực thi

Sửa lịch không mặc nhiên được sửa loại job, người thụ hưởng, tenant, số tiền hoặc quyền chạy với service account khác. Những trường đó cần quyền và quy trình thay đổi tương ứng.

API nên có mô hình đầu vào dành riêng cho chỉnh lịch. Không ánh xạ tùy ý mọi field trong JSON vào thực thể lưu trữ, vì có thể làm lộ các trường nội bộ như `approvedBy`, `activeRevision`, `nextFireAt` hoặc `bypassApproval`.

## 3. Các business invariant khi sửa lịch

### 3.1. Đúng chủ thể, đúng đối tượng, đúng loại thay đổi

Quyền “xem lịch” khác quyền “đổi giờ”, “bật chạy bù”, “tạm dừng” hoặc “đổi múi giờ”. Mọi API cần kiểm tra quyền theo schedule, tenant, đối tượng đích và trường đang sửa.

Một người được đổi giờ trong khoảng cho phép không đương nhiên được chuyển lịch hàng ngày thành lịch chạy liên tục.

### 3.2. Không mất cập nhật hoặc ghi đè quyết định mới

Mọi thay đổi phải gắn với phiên bản kỳ vọng của schedule. Nếu hai người cùng đọc version 12, chỉ một thay đổi được commit trên nền version đó. Người còn lại cần xem lại trạng thái hiện tại, không được âm thầm ghi đè.

Việc kiểm tra version phải xảy ra trong cùng thao tác cập nhật có điều kiện hoặc transaction bảo vệ bản ghi. Chỉ so sánh version ở giao diện không ngăn được request đồng thời.

### 3.3. Phê duyệt gắn với nội dung bất biến

~~~text
ApprovedChange
    = scheduleId
      + baseVersion
      + normalizedScheduleSpec
      + effectiveAt
      + affectedScope
      + catchUpPolicy
      + approvalPolicy
~~~

Các thành phần làm thay đổi ý nghĩa phải được lưu hoặc ràng buộc bằng fingerprint. Sửa giờ, múi giờ, thời điểm hiệu lực hay chạy bù sau phê duyệt phải tạo một đề nghị mới hoặc yêu cầu phê duyệt lại theo chính sách.

Không dùng một cờ `approved=true` có thể tiếp tục tồn tại sau khi payload đã đổi.

### 3.4. Phiên bản cũ không được tiếp tục tạo việc ngoài khoảng hiệu lực

Một revision có khoảng hiệu lực rõ ràng, thường biểu diễn bằng khoảng nửa kín:

~~~text
effectiveFrom <= scheduledFor < effectiveTo
~~~

Revision mới thay thế phần tương lai theo chính sách. Các khoảng của cùng một lịch không được chồng lấn ngoài chủ đích đã được mô hình hóa. Scheduler dùng dữ liệu cũ phải bị chặn khi cố lưu hoặc nhận một occurrence không còn hợp lệ.

Sự kiện xóa cache hữu ích để giảm trễ, nhưng không phải bằng chứng rằng mọi scheduler đã ngừng dùng revision cũ.

### 3.5. Một thay đổi không tạo quyền bỏ qua giới hạn nghiệp vụ

Đổi giờ hoặc tạo occurrence mới không được bỏ qua phê duyệt thanh toán, hạn mức, số dư, quy tắc chống chi trả trùng hoặc trạng thái khóa của merchant.

Nếu có điều kiện “chỉ chạy sau thời điểm được phép”, worker phải kiểm tra tại server khi nhận việc hoặc tạo tác động. Việc message đã nằm trong queue không phải bằng chứng thời điểm thực thi đã hợp lệ.

### 3.6. Sửa lịch không được làm mất trách nhiệm với việc đã phát sinh

Hủy kế hoạch tương lai và xử lý job đang chạy là hai quyết định khác nhau. Không đổi tất cả job cũ sang `CANCELLED` chỉ để giao diện thể hiện rằng lịch mới đã có hiệu lực.

Cần giữ bằng chứng occurrence nào bị thay, occurrence nào đã nhận trách nhiệm, và tác động nào đã xảy ra hoặc chưa rõ kết quả.

## 4. Phân quyền và phê duyệt thay đổi

### 4.1. Quyền theo hành động và trường dữ liệu

Có thể phân quyền như sau:

| Thao tác | Kiểm soát cần xem xét |
| --- | --- |
| Đổi giờ trong khung được phép | Quyền chỉnh lịch của đối tượng, version và giới hạn tần suất |
| Đổi múi giờ hoặc ngày nghiệp vụ | Quyền riêng và xem trước tác động lên các kỳ |
| Tăng tần suất | Ngưỡng tần suất, ngân sách tài nguyên, giới hạn nghiệp vụ |
| Bật hoặc sửa chạy bù | Khoảng thời gian, số kỳ, công suất và phê duyệt phù hợp |
| Tạm dừng tác vụ nhạy cảm | Mức ưu tiên bảo vệ, thời hạn dừng, tuyến thông báo |
| Gia hạn hoặc lùi thời gian kết thúc | Quyền thay đổi thời hạn, không chỉ quyền sửa biểu thức lịch |
| Thay đổi người thụ hưởng hoặc job type | Quy trình nghiệp vụ riêng, không gộp vào quyền chỉnh giờ |
| Phê duyệt hoặc cưỡng chế áp dụng | Quyền độc lập, điều kiện ngoại lệ và audit |

Với lịch thu hồi quyền, người hưởng lợi không nên được tự lùi hạn chỉ vì họ là người sở hữu đối tượng. Object ownership không đồng nghĩa được quyền sửa mọi thuộc tính kiểm soát của đối tượng.

### 4.2. Maker-checker cho lịch có tác động lớn

Một luồng có thể là:

~~~text
DRAFT → PENDING_APPROVAL → APPROVED → COMMITTED
                         ↘ REJECTED
                         ↘ EXPIRED
~~~

`COMMITTED` ở đây nghĩa là revision và khoảng hiệu lực đã được lưu có thẩm quyền; revision có thể chỉ bắt đầu áp dụng trong tương lai. Không nhầm trạng thái đề nghị với trạng thái job.

Người phê duyệt cần thấy cấu hình cũ, cấu hình mới, thời điểm hiệu lực, các lần chạy dự kiến bị thêm hoặc bỏ, chính sách chạy bù và phạm vi đối tượng. Màn hình chỉ hiển thị “đổi cron” không đủ để đánh giá tác động.

Nếu yêu cầu hai người khác nhau, server phải so sánh danh tính thực hiện và phê duyệt. Không chỉ ẩn nút tự duyệt trên giao diện.

### 4.3. Kiểm tra lại trước khi commit

Phê duyệt không thể dùng vô thời hạn trên một trạng thái nền đã thay đổi. Trước khi commit cần kiểm tra:

- Schedule vẫn ở base version được phê duyệt.
- Nội dung chuẩn hóa và phạm vi vẫn khớp với quyết định phê duyệt.
- Quyết định chưa hết hạn hoặc bị thu hồi.
- Người duyệt đáp ứng chính sách hiệu lực của quyết định.
- Các điều kiện nghiệp vụ hiện tại vẫn cho phép thay đổi.

Nếu thay đổi version làm đề nghị không còn phù hợp, trả xung đột và yêu cầu đánh giá lại. Không tự gộp một thay đổi nhạy cảm vào phiên bản mới chỉ để giảm bước thao tác.

## 5. Kiểm tra ý nghĩa thời gian, không chỉ cú pháp

Một biểu thức lịch hợp lệ về cú pháp vẫn có thể tạo ra kế hoạch nguy hiểm. Cần kiểm tra kết quả thực tế trong một khoảng xem trước được giới hạn.

### 5.1. Các thuộc tính phải được kiểm tra cùng nhau

Một cấu hình chuẩn hóa có thể gồm:

~~~json
{
  "scheduleType": "DAILY_LOCAL_TIME",
  "localTime": "08:00",
  "timeZone": "Asia/Ho_Chi_Minh",
  "startDate": "2026-11-24",
  "endDate": null,
  "misfirePolicy": "SKIP",
  "catchUpPolicy": "NONE",
  "maxOccurrencesPerBusinessDay": 1
}
~~~

Đây là ví dụ mô hình khai báo theo nghiệp vụ. Không phải hệ thống nào cũng cần cho người dùng nhập cron tự do. Nếu dùng cron, cú pháp, số trường và cách diễn giải phải thuộc một dialect xác định của hệ thống; không lấy kết quả parse ở trình duyệt làm quyết định có thẩm quyền.

Server cần kiểm tra:

- Loại lịch, miền giá trị, múi giờ và quan hệ ngày bắt đầu/kết thúc.
- Tần suất tối đa, khoảng cách tối thiểu nếu có và số lần chạy trong chân trời xem trước.
- Khung giờ được phép, ngày nghiệp vụ, ngày nghỉ theo chính sách.
- Giới hạn chạy bù và hành vi khi scheduler bỏ lỡ thời điểm.
- Chi phí dự kiến và giới hạn đối tượng mà một lần chạy được chạm tới.
- Điều kiện riêng của loại nghiệp vụ, chẳng hạn không chạy trước thời điểm chốt dữ liệu.

Giới hạn độ dài đầu vào, số kỳ xem trước và thời gian tính toán để biểu thức hoặc khoảng thời gian lớn không chiếm hết tài nguyên của API.

### 5.2. Một lần mỗi ngày khác với cách nhau ít nhất 24 giờ

Đổi từ 09:00 ngày D sang 08:00 ngày D+1 tạo khoảng cách 23 giờ.

Nếu invariant là “một đợt chi trả mỗi ngày nghiệp vụ”, thay đổi có thể hợp lệ. Nếu invariant là “hai đợt cách nhau ít nhất 24 giờ”, thay đổi này chưa đủ điều kiện.

Cần mô hình hóa điều kiện thật và kiểm tra trên mốc thời gian tương ứng. Không dùng số ngày trên lịch để suy ra khoảng thời gian đã trôi qua, hoặc ngược lại.

### 5.3. Múi giờ và các thời điểm không tồn tại hoặc xuất hiện hai lần

Với lịch theo giờ địa phương, cần lưu múi giờ cùng ý định giờ địa phương và tính các thời điểm thực thi cụ thể theo quy tắc của múi giờ đó.

Một số múi giờ có chuyển đổi giờ theo mùa, khiến một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Chính sách phải nói rõ bỏ qua, dời giờ hay chọn lần nào, và dùng định danh occurrence đủ rõ để không chạy trùng ngoài ý định.

Đổi múi giờ có thể làm đổi ngày nghiệp vụ dù giờ hiển thị giống nhau. Thay đổi dữ liệu quy tắc múi giờ cũng có thể ảnh hưởng lịch tương lai; đây là một thay đổi vận hành cần kiểm soát và đánh giá lại kế hoạch khi có ảnh hưởng.

### 5.4. Thời điểm hiệu lực và thời gian đã qua

`effectiveAt` được server kiểm tra theo chính sách và nguồn thời gian tin cậy. Không nhận thời điểm quá khứ rồi tự động diễn giải thành “chạy tất cả các kỳ đã lỡ”.

Với thay đổi chỉ áp dụng tương lai, một chính sách có thể yêu cầu khoảng đệm từ lúc commit tới lúc có hiệu lực. Nếu người dùng muốn chạy bù, cần một yêu cầu rõ ràng với phạm vi và số kỳ được phép.

Cần xác định chính xác ranh giới, chẳng hạn revision mới áp dụng cho các thời điểm dự kiến từ `effectiveAt` trở đi. Kỳ đã đến hạn trước ranh giới được xử lý theo chính sách tồn đọng riêng, không bị xóa hoặc chạy lại một cách ngầm định.

## 6. Luồng thay đổi an toàn từ API tới revision

### 6.1. Request chỉ chứa trường người gọi được phép sửa

Ví dụ đề nghị thay đổi:

~~~http
POST /schedules/sch_318/change-proposals
Content-Type: application/json

{
  "expectedVersion": 12,
  "idempotencyKey": "change-merchant-time-781",
  "newSpec": {
    "scheduleType": "DAILY_LOCAL_TIME",
    "localTime": "08:00",
    "timeZone": "Asia/Ho_Chi_Minh",
    "catchUpPolicy": "NONE"
  },
  "effectiveAt": "2026-11-24T00:00:00+07:00",
  "reason": "Điều chỉnh giờ vận hành đã được thống nhất"
}
~~~

Tenant và đối tượng được kiểm tra từ phiên cùng dữ liệu server. Không cho người gọi tự đặt người phê duyệt, trạng thái chấp thuận hoặc trường thời gian tính sẵn như `nextFireAt`.

Nếu dùng PATCH, phải định nghĩa rõ ý nghĩa của field bị thiếu, field `null` và giá trị rỗng. Chẳng hạn `endDate: null` có thể mang nghĩa bỏ giới hạn kết thúc, là thay đổi có tác động lớn chứ không phải chi tiết định dạng.

Các trường bị cấm cần bị từ chối hoặc được xử lý theo hợp đồng đầu vào rõ ràng. Không lưu chúng bằng cơ chế mass assignment.

### 6.2. Xem trước phải thể hiện chênh lệch

Kết quả xem trước nên cho biết:

- Cấu hình cũ và mới sau chuẩn hóa.
- Các lần chạy được thêm, bỏ hoặc dời trong khoảng được hiển thị.
- Ngày nghiệp vụ bị tác động và occurrence đã tồn tại.
- Số kỳ có thể được chạy bù cùng giới hạn.
- Các invariant không thỏa mãn hoặc điều kiện cần phê duyệt.
- Version dữ liệu nền và thời điểm tính.

Xem trước không phải khóa giữ toàn bộ hệ thống. Kết quả có thể trở nên cũ khi schedule hoặc occurrence thay đổi; bước commit vẫn phải kiểm tra lại điều kiện có thẩm quyền.

### 6.3. Commit nguyên tử và ghi sự kiện bền vững

Mã sau là mã giả theo phong cách Java cho một đề nghị đã được phê duyệt. Các hàm khóa, dedup và repository cần được triển khai phù hợp với cơ sở dữ liệu.

~~~java
ChangeReceipt commitScheduleChange(Actor actor, CommitCommand command) {
    return transaction.execute(() -> {
        TenantId tenantId = authorization.resolveTenant(actor);

        ChangeProposal proposal = proposals.lockByTenantAndId(
            tenantId, command.proposalId()
        );
        authorization.requireCanCommitChange(actor, proposal);

        CommandSlot slot = commandDedup.claimOrLoad(
            tenantId, actor.requesterScope(), "COMMIT_SCHEDULE_CHANGE",
            command.idempotencyKey(), proposal.approvedFingerprint()
        );
        if (slot.isCompleted()) {
            authorization.requireCanViewSchedule(actor, proposal.scheduleId());
            return slot.previousReceipt();
        }

        Schedule schedule = schedules.lockByTenantAndId(
            tenantId, proposal.scheduleId()
        );
        concurrency.requireVersion(schedule, proposal.baseVersion());
        approvals.requireValidFor(proposal, schedule, actor);

        ScheduleSpec spec = validation.revalidateApprovedSpec(proposal);
        policy.requireAllowedEffectiveAt(proposal.effectiveAt());
        policy.requireBusinessInvariants(schedule, spec, proposal);
        timeline.requireNoConflictingCommittedChange(schedule, proposal);

        // Cập nhật khoảng hiệu lực và thêm revision trong cùng transaction.
        ScheduleRevision revision = timeline.commitRevision(
            schedule, spec, proposal.effectiveAt()
        );
        schedule.incrementVersion();
        proposals.markCommitted(proposal, revision.id());

        audit.recordScheduleDiff(actor, schedule, proposal, revision);
        outbox.append(ScheduleRevisionCommitted.from(schedule, revision));

        ChangeReceipt receipt = ChangeReceipt.committed(
            schedule.id(), revision.id(), revision.effectiveFrom()
        );
        commandDedup.complete(slot, receipt);
        return receipt;
    });
}
~~~

Idempotency phải có unique constraint trong phạm vi đã chọn, so sánh fingerprint và xử lý request đồng thời. Cùng key nhưng nội dung khác không được tạo revision mới. Nhánh trả kết quả cũ vẫn phải kiểm tra quyền xem.

Một thiết kế đơn giản có thể chỉ cho phép một thay đổi tương lai chưa có hiệu lực trên mỗi schedule. Nếu cho phép nhiều thay đổi, cần mô hình timeline và quy tắc xung đột tương ứng; không để các revision đã phê duyệt chồng lấn ngẫu nhiên.

Revision, khoảng hiệu lực, version, trạng thái đề nghị, audit và outbox phải commit nhất quán. Nếu transaction rollback, không phát thông báo khẳng định thay đổi đã được chấp nhận.

### 6.4. Không phụ thuộc một lần gọi xóa cache

Sau commit, publisher gửi sự kiện để các scheduler làm mới dữ liệu. Publisher có thể chết hoặc sự kiện có thể được giao lại; vì vậy nên có outbox và consumer idempotent.

Điều kiện an toàn không được phụ thuộc vào việc “đã gọi refresh tất cả node”. Khi scheduler lưu occurrence hoặc worker nhận việc, cần kiểm tra bản ghi có thẩm quyền để chặn revision không hợp lệ.

Nếu revision tương lai đã commit, khoảng hiệu lực phải đủ để quyết định đúng ngay cả khi tiến trình cập nhật trạng thái hiển thị sang “đang áp dụng” bị chậm.

## 7. Race giữa sửa lịch và scheduler tạo occurrence

### 7.1. Tình huống điển hình

~~~text
T1: Scheduler A đọc revision 12, giờ chạy 09:00.
T2: API commit revision 13, giờ chạy 08:00 từ ngày D.
T3: Scheduler A dùng snapshot cũ để tạo occurrence 09:00 ngày D.
T4: Scheduler B tạo occurrence 08:00 ngày D theo revision mới.
~~~

Nếu mỗi scheduler chỉ tin snapshot trong bộ nhớ, cùng ngày có thể xuất hiện hai công việc. Cần kiểm soát cả lúc lập kế hoạch lẫn lúc nhận thực thi.

### 7.2. Lưu occurrence dưới điều kiện có thẩm quyền

Khi materialize occurrence, scheduler cần một thao tác được bảo vệ bằng transaction, khóa hoặc điều kiện tương đương:

1. Đọc timeline và version hiện tại của schedule.
2. Xác minh revision được dùng còn áp dụng cho thời điểm dự kiến.
3. Xác định business key của kỳ, không chỉ thời điểm kỹ thuật.
4. Tạo occurrence bằng ràng buộc duy nhất hoặc cập nhật kế hoạch hiện có theo quy tắc.
5. Ghi sự kiện đưa job vào hàng đợi theo cùng ranh giới bền vững.

Nếu version đã thay đổi so với snapshot dùng để tính, scheduler phải tính lại hoặc xác minh lại trước khi ghi. Không ghi tiếp rồi hy vọng lần chạy trùng sẽ tự bị bỏ qua.

### 7.3. Occurrence đã lập kế hoạch cần được đối chiếu lại

Nếu occurrence của ngày D đã tồn tại ở 09:00 nhưng còn ở trạng thái `PLANNED`, hệ thống có thể dời sang 08:00 theo thay đổi đã chấp thuận. Việc dời cần cập nhật revision, thời điểm và `planVersion` một cách có điều kiện.

Message cũ mang plan version trước đó phải bị worker bỏ qua hoặc đưa đi đối soát với bản ghi hiện tại. Không cho message cũ ghi đè thời điểm mới.

Nếu không thể quét và cập nhật mọi occurrence tương lai trong transaction chỉnh lịch, có thể dùng cơ chế đối chiếu dần. Trong thời gian đó, kiểm tra ở lúc nhận job phải ngăn kế hoạch không còn hợp lệ. “Đang chờ reconcile” không được đồng nghĩa cho phép chạy cả kế hoạch cũ và mới.

### 7.4. Không nhét revision vào khóa để né xung đột

Nếu occurrence mới xung đột với business key đang tồn tại, cần xem trạng thái của occurrence đó:

- Còn lập kế hoạch: có thể replan bằng chuyển trạng thái được phép.
- Đã nhận trách nhiệm: áp dụng chính sách xử lý công việc đang chạy.
- Đã thành công: không tạo thêm tác động cùng kỳ.
- Kết quả chưa xác định: đối soát trước khi quyết định.
- Đã hủy trước tác động: chỉ tạo lại hoặc mở lại theo quy tắc có audit.

Thêm revision vào khóa chỉ để insert không còn báo lỗi có thể che đi lỗi nghiệp vụ thay vì giải quyết nó.

## 8. Job đã tạo hoặc đang chạy phải được xử lý riêng

| Trạng thái công việc | Chính sách có thể áp dụng | Điều không được suy diễn |
| --- | --- | --- |
| Chưa tạo occurrence | Sinh theo timeline hiện tại | Snapshot cũ vẫn được dùng tùy ý |
| `PLANNED`, chưa nhận trách nhiệm | Dời hoặc hủy có điều kiện theo revision mới | Queue message tự biến mất khi sửa schedule |
| `CLAIMED`, chưa tạo tác động | Kiểm tra lại kế hoạch; thu hồi hoặc tiếp tục theo chính sách | Thu hồi lease đồng nghĩa worker cũ đã dừng |
| Đã gửi lệnh ra ngoài | Giữ bằng chứng và xử lý theo hợp đồng bên ngoài | Đổi giờ có thể hoàn tác một lệnh đã gửi |
| `SUCCEEDED` | Giữ lịch sử, bảo vệ business key | Sửa lịch được quyền chạy lại cùng kỳ |
| `UNKNOWN` | Đối soát, duy trì nghĩa vụ liên quan | Chưa thấy thành công nghĩa là chắc chắn chưa có tác động |

Lúc nhận job, worker cần kiểm tra occurrence, plan version, thời điểm được phép và các invariant hiện tại. Thao tác nhận phải nguyên tử để tránh hai worker cùng nhận một slot.

Nếu dùng lease hoặc fencing token, chúng chỉ bảo vệ nơi thực sự kiểm tra token. Một cổng thanh toán không biết token nội bộ vẫn cần effect key hoặc cơ chế chống tác động trùng riêng.

Với công việc đã được nhận trước ranh giới thay đổi, hệ thống cần công bố chính sách rõ: tiếp tục nghĩa vụ đã chấp thuận, hay yêu cầu kiểm tra lại trước điểm tác động. Không trông chờ một thông báo đổi lịch đến kịp mọi worker đang chạy.

## 9. Chạy bù, tạm dừng và khôi phục lịch

### 9.1. Phân biệt đổi lịch với yêu cầu chạy bù

Misfire là tình huống hệ thống bỏ lỡ thời điểm dự kiến, chẳng hạn scheduler ngừng hoạt động. Chính sách xử lý có thể là bỏ kỳ, gộp thành một lần hoặc thực hiện các kỳ trong giới hạn.

Việc sửa lịch không được tự động cấp quyền chạy bù mọi thời điểm quá khứ. Một yêu cầu chạy bù nên xác định riêng:

~~~text
scheduleId
revision hoặc quyết định nghiệp vụ được dùng
khoảng kỳ được phép
mục đích chạy bù
số occurrence tối đa
giới hạn tốc độ và công suất
người yêu cầu, người phê duyệt
~~~

Mỗi kỳ vẫn phải có business key ổn định. Phát lại một yêu cầu chạy bù không được tạo lại các kỳ đã thành công.

Nếu dữ liệu đầu vào hoặc chính sách tính toán của kỳ quá khứ khác hiện tại, cần xác định snapshot hoặc phiên bản nghiệp vụ dùng để xử lý. Chọn “revision hiện tại” không tự chứng minh đó là cách đúng để xử lý mọi kỳ cũ.

### 9.2. Bật lại lịch không đồng nghĩa chạy tất cả phần tồn đọng

Khi bỏ tạm dừng, cần quyết định rõ:

- Tiếp tục từ kỳ tiếp theo.
- Xử lý một số kỳ còn đủ điều kiện.
- Tạo một yêu cầu chạy bù cần phê duyệt.

Giới hạn phải áp dụng ở server, kể cả khi người dùng gọi trực tiếp API. Thay đổi hàng loạt rồi bật lại không được vượt qua ngân sách chạy bù của tenant.

### 9.3. Không để chỉnh lịch vô hiệu hóa kiểm soát thời hạn

Với lịch thu hồi quyền, khóa tài khoản hoặc hết hạn tài nguyên, kiểm soát truy cập nên đánh giá hạn hiệu lực ở nơi sử dụng quyền nếu đó là invariant của hệ thống. Không chỉ dựa vào một job sẽ chạy sau để xóa quyền.

Nếu job dọn quyền bị trễ, một quyền đã hết hạn vẫn phải bị từ chối tại điểm kiểm tra theo chính sách. Như vậy, sửa hoặc tạm dừng scheduler không trở thành cách kéo dài quyền ngoài thời hạn.

Việc tạm dừng một lịch bảo vệ cần có thời hạn và cơ chế theo dõi phù hợp. Nếu cho phép ngoại lệ khẩn cấp, lưu ngoại lệ như một quyết định riêng có phạm vi, thay vì sửa âm thầm cấu hình để không ai nhận ra kiểm soát đã bị trì hoãn.

## 10. Các đường lạm dụng qua API và cấu hình

### 10.1. Sửa trường nội bộ hoặc vượt phạm vi

Các giá trị như `approvedBy`, `tenantId`, `jobType`, `runAs`, `activeRevision` và `nextFireAt` không được trở thành trường tự do trong endpoint đổi giờ.

Client có thể đề nghị thời điểm và cấu hình được phép. Server tự xác định trạng thái phê duyệt, revision, quyền thực thi và thời điểm kế tiếp từ dữ liệu đã kiểm chứng.

Cần bảo vệ cả các API phụ trợ: xem trước, sao chép lịch, tạo template, sửa hàng loạt, bật/tắt và nút “chạy ngay”. Sao chép một lịch rồi bật nó có thể tạo tác động trùng nếu business key chỉ gắn với schedule ID.

### 10.2. Churn revision và cạn tài nguyên

Kẻ tấn công có quyền hạn chế có thể sửa giờ liên tục để gây tái lập kế hoạch, phát nhiều sự kiện làm mới hoặc tạo tải tính toán.

Biện pháp có thể gồm giới hạn tốc độ thay đổi theo tenant và chủ thể, số đề nghị chờ, số occurrence xem trước, số kỳ chạy bù và ngân sách xử lý. Hạn chế thao tác lặp không được làm mất audit hoặc tự cho qua thay đổi chưa kiểm tra.

Mức độ ưu tiên không nên chỉ lấy từ request. Người gọi không được tự gán “khẩn cấp” để bỏ qua hàng đợi phê duyệt hoặc vượt giới hạn tài nguyên.

### 10.3. Dời lịch để né điều kiện nghiệp vụ

Nếu báo cáo, kiểm tra gian lận hoặc phê duyệt được kỳ vọng hoàn tất trước chi trả, worker chi trả phải kiểm tra bằng chứng hoàn tất cần thiết. Không chỉ tin rằng “lịch luôn đặt sau giờ kiểm tra”.

Tương tự, deadline phê duyệt, thời gian giữ tiền hoặc thời hạn quyền phải là điều kiện ở nghiệp vụ tương ứng. Một người đổi giờ không được vô tình hoặc cố ý biến giả định thời gian thành lỗ hổng bỏ qua quy trình.

### 10.4. Xóa và tạo lại lịch

Xóa schedule rồi tạo schedule mới có thể vượt lớp chống trùng nếu toàn bộ lịch sử gắn với ID kỹ thuật cũ. Business key phải tiếp tục bảo vệ đối tượng và kỳ mà nghiệp vụ quan tâm.

Lưu lịch sử đủ để biết một kỳ đã được xử lý bởi lịch nào. Nếu có thao tác thay thế lịch, nó phải liên kết lịch cũ và mới theo quy tắc, không xóa bằng chứng chỉ để tránh xung đột.

## 11. Kiểm thử tình huống tấn công logic

Kiểm thử cần quan sát revision, timeline, occurrence, job và tác động cuối cùng. Một response thành công không chứng minh lịch cũ đã mất quyền tạo công việc.

| Tình huống | Cách kích hoạt | Kết quả cần chứng minh |
| --- | --- | --- |
| Sửa lịch chéo tenant | Đổi schedule ID hoặc đối tượng trong request | Không đọc, xem trước, sửa hoặc phê duyệt ngoài quyền |
| Mass assignment | Thêm `approvedBy`, `runAs`, `nextFireAt` | Trường nội bộ không được client điều khiển |
| Quyền sửa giờ bị mở rộng | Dùng cùng endpoint để bật chạy bù hoặc đổi job type | Kiểm tra quyền theo trường và hành động |
| Tự phê duyệt | Người đề nghị gọi thẳng API approve | Bị chặn nếu chính sách yêu cầu độc lập |
| Sửa sau phê duyệt | Đổi múi giờ, hiệu lực hoặc catch-up sau khi approve | Fingerprint không khớp, phải đánh giá lại |
| Hai thay đổi đồng thời | Hai request dùng cùng expected version | Không mất cập nhật, chỉ thay đổi hợp lệ được commit |
| Retry commit | Cùng key và payload gửi nhiều lần | Một revision và một kết quả logic |
| Dùng lại key sai nội dung | Cùng key với đề nghị hoặc cấu hình khác | Từ chối xung đột |
| Hiệu lực quá khứ | Gửi `effectiveAt` cũ để kích hoạt chạy bù | Không tự thực thi các kỳ chưa được chấp thuận |
| Quá dày hoặc quá lớn | Biểu thức hợp lệ nhưng sinh quá nhiều kỳ | Bị giới hạn theo chính sách và ngân sách |
| Múi giờ làm đổi ngày | Giữ giờ, đổi timezone | Xem trước và kiểm tra lại business date |
| Giờ địa phương đặc biệt | Kỳ rơi vào giờ không tồn tại hoặc lặp lại | Tuân thủ chính sách đã định nghĩa, không trùng ngoài ý định |
| Scheduler giữ cache cũ | Commit revision mới rồi để node cũ materialize | Điều kiện lưu chặn hoặc tính lại kế hoạch cũ |
| Occurrence đã đưa vào queue | Đổi giờ sau khi message cũ được gửi | Worker kiểm tra plan version và thời điểm hiện tại |
| Đổi giờ giữa ngày | Kỳ cũ đã thành công, lịch mới còn một giờ chạy cùng ngày | Business key chặn chi trả lần hai |
| Hủy đua với claim | Worker nhận job trong lúc replan hoặc cancel | Kết quả theo chuyển trạng thái nguyên tử và chính sách điểm tác động |
| Lệnh ngoài chưa rõ kết quả | Đổi lịch khi job timeout sau khi gửi thanh toán | Đối soát, không coi thay đổi lịch là bằng chứng lệnh chưa chạy |
| Bật lại sau nhiều ngày | Resume lịch có backlog lớn | Chính sách catch-up và giới hạn được giữ |
| Clone hoặc tạo lại lịch | Lịch mới nhắm cùng merchant và kỳ | Không vượt invariant bằng schedule ID mới |
| Mất sự kiện làm mới | Dừng publisher hoặc bỏ một thông báo cache | Kiểm tra có thẩm quyền vẫn chặn kế hoạch không hợp lệ |
| Cố lùi kiểm soát thời hạn | Dời job thu hồi quyền | Quyền hết hạn vẫn bị từ chối tại nơi sử dụng theo chính sách |
| Khôi phục phiên bản cũ | Thử cập nhật lại cấu hình cũ để rollback | Tạo thay đổi mới có version và phê duyệt, không quay lùi lịch sử |

Kiểm thử concurrency nên chạy trên cơ sở dữ liệu thật của hệ thống và điều khiển được thời điểm đọc snapshot, commit revision, materialize và claim. Với thời gian, nên dùng nguồn thời gian có thể điều khiển trong kiểm thử để đặt chính xác trước, tại và sau `effectiveAt`.

Không cần chờ nhiều giờ theo đồng hồ thực để kiểm tra một ranh giới ngày. Điều cần chứng minh là cách hệ thống phân loại kỳ và chuyển trạng thái tại các mốc đó.

## 12. Audit, đo lường và đối soát sau thay đổi

### 12.1. Bằng chứng cần nối được

Mỗi thay đổi nên truy được:

~~~text
scheduleId
  ├── proposalId + người đề nghị + lý do + baseVersion
  ├── diff cấu hình đã chuẩn hóa + fingerprint
  ├── quyết định phê duyệt + người duyệt + thời hạn
  ├── revisionId + khoảng hiệu lực + version sau commit
  ├── eventId + lịch sử gửi sự kiện thay đổi
  └── occurrence bị dời, bỏ, giữ lại hoặc cần đối soát
        └── job, attempt và business effect liên quan
~~~

Giữ thời điểm đề nghị, phê duyệt, commit và hiệu lực thành các dữ liệu khác nhau. Không ghi đè lịch sử cũ bằng cấu hình mới rồi mất khả năng giải thích vì sao một occurrence được tạo.

Quyền chỉnh lịch không nên cho phép sửa hoặc xóa bằng chứng phê duyệt và kết quả thực thi. Thời hạn lưu phải phù hợp với thời gian có thể phát lại, hậu kiểm và đối soát nghiệp vụ.

### 12.2. Chỉ số phản ánh tính đúng đắn

Các chỉ số hữu ích gồm:

- Số thay đổi bị từ chối do quyền, version, fingerprint hoặc invariant.
- Thời gian từ commit tới khi các scheduler quan sát revision mới.
- Số lần materialize hoặc claim bị chặn vì kế hoạch cũ.
- Số occurrence tương lai còn cần reconcile.
- Số kỳ bị bỏ lỡ, số kỳ chạy bù và công suất bị giới hạn.
- Số business key xung đột và số tác động trùng thực sự.
- Tuổi của công việc kết quả không xác định hoặc chưa xử lý.
- Số lịch nhạy cảm bị tạm dừng quá thời hạn được phép.

Một lần node dùng cache cũ nhưng bị chặn trước khi tạo tác động cho thấy lớp kiểm soát đã hoạt động. Cần phân biệt nó với trường hợp đã chi trả trùng.

### 12.3. Đối soát không được hợp thức hóa dữ liệu sai

Tác vụ đối soát có thể tìm occurrence nằm ngoài khoảng revision, plan version cũ, cùng kỳ có nhiều công việc hoặc lịch đã thay nhưng còn backlog không rõ cách xử lý.

Khi sửa sai, lưu quyết định và bằng chứng. Không thay `scheduledFor` của một tác động đã xảy ra chỉ để nó trông phù hợp với revision mới. Mốc dự kiến, mốc thực tế và thời điểm phát hiện cần được giữ riêng.

## 13. Xử lý sự cố và rollback có kiểm soát

Nếu một thay đổi lịch có dấu hiệu sai:

1. Xác định tenant, schedule, revision và các kỳ bị ảnh hưởng.
2. Giới hạn việc tạo hoặc nhận công việc mới trong đúng phạm vi có rủi ro.
3. Kiểm tra occurrence nào mới lập kế hoạch, đã nhận trách nhiệm, đã thành công hoặc chưa rõ kết quả.
4. Đối soát tác động ngoài trước khi phát lại hay tạo kỳ thay thế.
5. Tạo một thay đổi sửa chữa với version hiện tại, lý do và phê duyệt phù hợp.
6. Reconcile kế hoạch tương lai, đồng thời theo dõi các nghĩa vụ cũ chưa hoàn tất.
7. Kiểm tra lại business invariant và lưu kết quả xử lý.

Rollback cấu hình không phải xóa revision mới rồi đặt số version về giá trị cũ. Đó là một thay đổi tiếp theo, có timeline và hiệu lực riêng. Các lệnh đã gửi hoặc kỳ đã xử lý không tự bị hoàn tác khi cấu hình quay về giờ trước đó.

Trong ví dụ đổi giờ chi trả từ 09:00 sang 08:00, một kết quả đúng có thể là: revision mới được chấp thuận cho ngày D, occurrence chưa chạy của ngày D được replan có điều kiện, message cũ không còn đủ plan version để thực thi, và merchant vẫn chỉ có một đợt chi trả chuẩn trong ngày. Nếu kỳ đó đã thành công, hệ thống giữ bằng chứng và chặn đợt thứ hai thay vì tạo một occurrence mới theo giờ mới.

Bảo vệ thay đổi lịch cần nối quyền cấu hình với trạng thái thực thi. Revision, khoảng hiệu lực, phê duyệt, business key và kiểm tra tại lúc nhận việc giúp việc sửa thời gian không trở thành con đường vượt quy trình hoặc tạo tác động ngoài ý định đã được chấp thuận.
