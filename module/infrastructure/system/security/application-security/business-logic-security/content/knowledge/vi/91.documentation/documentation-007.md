# Lịch sử thay đổi quy tắc nghiệp vụ (Rule change history)

Trong chương **Documentation** của module bảo vệ logic nghiệp vụ, **rule change history** là hồ sơ có cấu trúc về việc một quy tắc đã thay đổi như thế nào, vì sao thay đổi, ai có thẩm quyền chấp thuận, áp dụng cho phạm vi nào và từ mốc nào. Lịch sử này giúp giải thích một quyết định nghiệp vụ trong quá khứ mà không phải suy đoán từ code hoặc cấu hình hiện tại.

Đối với business logic security, việc đổi hạn mức, quyền theo đối tượng, số bước phê duyệt, state machine hoặc semantics idempotency đều có thể làm thay đổi hành động nào được phép. Nếu không giữ được lịch sử và liên kết tới quyết định thực thi, đội phát triển khó phân biệt một giao dịch hợp lệ theo chính sách cũ với hành động đã bỏ qua kiểm soát, hoặc một thay đổi chính sách với một lỗi hiện thực.

Bài học dùng chính sách số người phê duyệt khoản hoàn tiền làm ví dụ tổng hợp. Các thời điểm, định danh, ngưỡng và phiên bản bên dưới phục vụ minh họa; chúng không phải chính sách bắt buộc cho mọi hệ thống tài chính. Các quyết định thay đổi thực tế cần do chủ thể nghiệp vụ có thẩm quyền xác nhận.

## 1. Lịch sử quy tắc cần trả lời những câu hỏi nào?

### 1.1. Từ một dòng changelog đến một quyết định có thể tái hiện

Một dòng “đã tăng cường kiểm soát hoàn tiền” chưa đủ. Hồ sơ cần trả lời:

- Quy tắc nào thay đổi, phiên bản trước và sau là gì?
- Nội dung bắt buộc thay đổi ở đâu; những điều kiện nào tiếp tục áp dụng?
- Thay đổi nhằm xử lý rủi ro, yêu cầu nghiệp vụ hoặc sai lệch nào?
- Ai đề xuất, ai phê duyệt và ai/cơ chế nào kích hoạt?
- Phạm vi là tenant, loại tài khoản, currency, kênh hay action nào?
- Mốc nào chọn phiên bản: tạo intent, duyệt, chấp nhận thực hiện hay phát lệnh?
- Intent đang xử lý, approval cũ, retry và callback được tiếp tục thế nào?
- Release, cấu hình, schema, bằng chứng và test nào hỗ trợ việc triển khai?
- Nếu cần dừng/rollback, điều kiện và hậu quả dữ liệu được xử lý ra sao?

Lịch sử tốt cho phép đi từ **một action cụ thể → phiên bản quy tắc đã áp dụng → căn cứ chọn phiên bản → nội dung được chấp thuận → hiện thực và bằng chứng tương ứng**.

### 1.2. Không thay thế các nguồn lịch sử khác

| Nguồn | Nội dung chính | Điều không thể tự suy ra |
|---|---|---|
| Rule catalog | Ý nghĩa và cấu trúc quy tắc ở các phiên bản được quản lý | Chưa cho biết một action thực tế đã dùng phiên bản nào |
| Rule change history | Chênh lệch, lý do, thẩm quyền, hiệu lực và cách chuyển tiếp | Chưa chứng minh mọi node đã thực thi đúng phiên bản |
| Deployment history | Phần mềm nào được đưa lên phạm vi nào | Deploy code hỗ trợ chưa đồng nghĩa policy đã kích hoạt |
| Configuration history | Tham số/cấu hình thay đổi thế nào | Một diff không tự chứng minh thay đổi đã được phép |
| Business audit | Subject, đối tượng, quyết định và hiệu ứng của action cụ thể | Log `ALLOW` chưa chứng minh quy tắc áp dụng đúng hoặc đầy đủ |
| Hồ sơ quyết định thiết kế | Vì sao chọn một cách bảo vệ và đánh đổi nào | Không thay thế kiểm thử và bằng chứng vận hành |

Liên kết các nguồn bằng định danh và phiên bản thay vì chép một bản tóm tắt rồi làm mất đường truy về bằng chứng gốc.

## 2. Phân biệt thay đổi nghiệp vụ với sửa lỗi hiện thực

### 2.1. Các loại thay đổi cần ghi nhận khác nhau

| Loại | Ví dụ | Điều cần mô tả |
|---|---|---|
| Thay đổi chính sách | Giảm ngưỡng cần hai người duyệt từ trên 50.000 xuống trên 30.000 VND | Hành vi được phép mới, mốc hiệu lực, phạm vi và chuyển tiếp |
| Bổ sung quy tắc | Yêu cầu quyền theo đối tượng cho một nghiệp vụ mới | Mục tiêu, action/resource, nguồn dữ liệu và đường thực thi |
| Sửa lỗi hiện thực | Code chỉ kiểm tra `APPROVED`, bỏ qua ràng buộc snapshot vốn đã bắt buộc | Quy tắc đúng đã tồn tại, release sửa lỗi và tập action có thể vi phạm |
| Thay đổi kỹ thuật | Đổi từ khóa hàng sang cập nhật có điều kiện nhưng giữ cùng bất biến | Bằng chứng semantics không đổi, test đồng thời và ranh giới transaction |
| Làm rõ tài liệu | Bổ sung ví dụ bằng ngưỡng, không đổi ý nghĩa đã được phê chuẩn | Phần được làm rõ và căn cứ rằng không có thay đổi chính sách |
| Sửa hồ sơ lịch sử | Bổ sung một bản ghi kích hoạt bị ghi nhận muộn | Thời điểm sự kiện thực, thời điểm bổ sung và nguồn xác minh |

Không biến mọi bug thành “quy tắc cũ cho phép”. Nếu chính sách đã yêu cầu approval khớp amount nhưng code bỏ qua, giao dịch sai amount có thể đã vi phạm ngay ở thời điểm ấy. Release vá lỗi không phải mốc mà hành vi sai mới bắt đầu bị cấm.

Ngược lại, nếu một ngưỡng mới chỉ được áp dụng từ hôm nay, không tự dùng ngưỡng ấy để gắn nhãn vi phạm cho mọi giao dịch trước đó. Cần xét đúng hợp đồng đã có hiệu lực cùng các kiểm soát bắt buộc khác.

### 2.2. Giữ riêng ý nghĩa, tham số và hiện thực

Một thay đổi có thể tác động đồng thời nhiều lớp:

```text
rule ID và rule version:        ý nghĩa điều kiện bắt buộc
policy/config version:         giá trị và phạm vi áp dụng
schema/snapshot version:       cách biểu diễn dữ liệu để đánh giá
code release:                  hiện thực đọc và thực thi các phiên bản đó
activation event:              xác nhận áp dụng trong phạm vi thực tế
business decision reference:   action nào đã dùng tổ hợp tương ứng
```

Không dùng duy nhất Git commit hoặc một số release để thay thế tất cả các lớp. Một release có thể hỗ trợ nhiều policy; một policy có thể được kích hoạt theo tenant vào các thời điểm khác nhau.

## 3. Chốt các loại thời gian và phạm vi hiệu lực

### 3.1. Những mốc thường bị nhầm

| Mốc | Ý nghĩa |
|---|---|
| `proposedAt` | Thay đổi được đề xuất |
| `approvedAt` | Chủ thể có thẩm quyền chấp thuận thay đổi |
| `deployedAt` | Code/cấu hình hỗ trợ đã được đưa tới phạm vi triển khai |
| `effectiveFrom` | Mốc bắt đầu hiệu lực theo hợp đồng đã chọn |
| `decisionAt` | Mốc đánh giá được lưu với quyết định nghiệp vụ |
| `committedAt` | Mốc thay đổi local commit, theo cơ chế quan sát có sẵn |
| `recordedAt` | Hồ sơ lịch sử được ghi vào hệ thống quản lý |
| `observedAt` | Một nguồn bằng chứng được quan sát/thu thập |

Đề xuất được duyệt chưa có nghĩa đã triển khai; triển khai xong chưa có nghĩa đã kích hoạt. `recordedAt` cũng không tự là thời điểm quy tắc bắt đầu có hiệu lực.

Nêu rõ múi giờ và semantics của cửa sổ, ví dụ `[effectiveFrom, effectiveToExclusive)`. Timestamp từ nhiều hệ thống có thể lệch hoặc mô tả thời điểm nhận thay vì thời điểm xảy ra. Khi có, dùng version/sequence và quan hệ nhân quả để bổ trợ, đồng thời giữ phần không chắc chắn.

### 3.2. Xác định chính xác mốc chọn phiên bản

Trong ví dụ của bài, phiên bản được chọn theo `decisionAt` từ nguồn thời gian có thẩm quyền, được lấy khi kiểm tra điều kiện trong transaction chấp nhận thực hiện. Version đã chọn và snapshot đầu vào được lưu cùng quyết định bền vững. Timestamp do client gửi, thời điểm tạo draft hoặc thời điểm message vào queue không thay thế mốc này.

`decisionAt` khác thời điểm phản hồi hoặc commit quan sát được. Một transaction có thể đánh giá trước ranh giới hiệu lực rồi commit sau đó. Theo hợp đồng minh họa này, phải giải thích nó bằng mốc đánh giá đã lưu, không tự đổi version theo thời gian nhận phản hồi.

Nếu nghiệp vụ đòi hỏi mọi commit sau một mốc phải dùng chính sách mới, cần thiết kế cơ chế phối hợp/kiểm tra hiệu lực phù hợp tại ranh giới ấy và ghi đúng hợp đồng đó. Việc đổi tên một timestamp thành `acceptedAt` không tự tạo ra bảo đảm đồng thời giữa kích hoạt chính sách và mọi transaction.

### 3.3. Phạm vi chọn phiên bản phải không mơ hồ

Cần mô tả tenant, action, loại đối tượng, currency, kênh và quan hệ ưu tiên giữa các policy nếu có. Nếu vừa có rule chung vừa có override cho tenant, phải có cách chọn xác định và test cho chồng lấn/thiếu cấu hình.

Không chọn “version lớn nhất” hoặc “record được ghi gần nhất” mà bỏ qua thời gian và phạm vi. Nếu có hai cấu hình cùng khẳng định đang áp dụng nhưng hợp đồng không giải quyết được xung đột, đó là ngoại lệ cấu hình, không phải lý do tự chọn một phiên bản ít hạn chế hơn.

## 4. Ví dụ xuyên suốt: đổi ngưỡng số người phê duyệt

### 4.1. Nội dung trước và sau

Quy tắc có ID bền vững `BLS-REF-APPROVAL-COUNT`, áp dụng cho action chấp nhận thực hiện hoàn tiền bằng VND của `tenant-A`:

| Nội dung | Version 1 | Version 2 |
|---|---|---|
| Ngưỡng một người duyệt | `0 < amount <= 50.000` | `0 < amount <= 30.000` |
| Trên ngưỡng | Cần ít nhất hai người duyệt độc lập đủ thẩm quyền | Cần ít nhất hai người duyệt độc lập đủ thẩm quyền |
| Ràng buộc snapshot | Mọi approval được tính phải duyệt đúng nội dung/version | Giữ nguyên yêu cầu này |
| Phân tách nhiệm vụ | Người tạo không được tính là người duyệt | Giữ nguyên yêu cầu này |
| Mốc chọn version | `decisionAt` tại transaction chấp nhận | Giữ cùng mốc, dùng cửa sổ hiệu lực mới |

“Hai người” phải được xác định theo danh tính nghiệp vụ có hiệu lực và quy tắc ủy quyền/phân tách nhiệm vụ của hệ thống, không chỉ hai dòng approval hoặc hai session. Quyền và hạn mức của người duyệt cần bằng chứng tại các mốc mà hợp đồng yêu cầu.

Version 2 bắt đầu áp dụng lúc `2026-11-01T10:00:00Z` cho phạm vi minh họa. Các số tiền đều theo biểu diễn chính xác một đồng VND trong fixture. Quy tắc về quyền đối tượng, hạn mức tiền, state machine và chống trùng vẫn áp dụng; đủ số người duyệt không thay thế chúng.

### 4.2. Chuyển tiếp cho intent và approval cũ

Hợp đồng chuyển tiếp được chọn trong ví dụ:

1. Intent chưa được chấp nhận thực hiện phải đáp ứng version tại `decisionAt` của lần quyết định chấp nhận.
2. Approval cũ có thể được tính nếu đúng snapshot và đáp ứng các điều kiện người duyệt vẫn được hợp đồng cho phép sử dụng; version 2 không tự xóa hoặc sửa approval lịch sử.
3. Intent đã được chấp nhận theo version 1 giữ snapshot và phiên bản quyết định đó khi worker tiếp tục xử lý.
4. Retry để tra cứu/nhận lại kết quả chấp nhận cũ không biến thành một quyết định mới theo version 2; quyền truy cập kết quả vẫn phải được kiểm tra.
5. Bất kỳ lệnh tiền mới, chỉnh nội dung hoặc xử lý ngoại lệ nào cũng phải theo hợp đồng dành cho action tương ứng, không viện dẫn version cũ để mở quyền chung.

Do đó, intent 40.000 mới có một approval nhưng chưa được chấp nhận trước mốc sẽ cần đủ điều kiện version 2. Intent 40.000 đã được chấp nhận theo version 1 trước mốc không tự biến thành giao dịch trái phép chỉ vì worker chạy muộn.

Nếu tổ chức muốn dừng cả intent đã chấp nhận nhưng chưa gửi, đó là hợp đồng chuyển tiếp khác cần ghi rõ: kiểm tra nào chặn dispatch, xử lý reservation ra sao và điều gì xảy ra khi provider đã nhận lệnh. Không thể giả định đổi ngưỡng sẽ thu hồi được hiệu ứng đã phát ra ngoài.

### 4.3. Timeline minh họa

| Mốc UTC | Sự kiện | Kết luận theo hợp đồng ví dụ |
|---|---|---|
| 09:00 | Chấp thuận thay đổi ngưỡng | Có thẩm quyền đổi; chưa tự chứng minh đã kích hoạt |
| 09:30 | Deploy code hỗ trợ version 2 | Chuẩn bị thực thi; version áp dụng vẫn theo hiệu lực/phạm vi |
| 09:59:58 | Quyết định chấp nhận `refund-A` 40.000, một approval hợp lệ, dùng v1 | Có thể được chấp nhận nếu mọi quy tắc khác cũng đạt |
| 10:00:00 | Bắt đầu cửa sổ hiệu lực v2 cho `tenant-A` | Quyết định mới tại mốc này dùng v2 |
| 10:00:01 | `refund-B` 40.000 chưa chấp nhận, mới có một approval | Chưa đủ số người duyệt theo v2; không tạo công việc thực hiện |
| 10:02 | Worker xử lý snapshot đã chấp nhận của `refund-A` | Giữ quyết định v1, không tự sinh intent hoặc reservation mới |

Đây là thứ tự minh họa trong nguồn thời gian của fixture. Khi dựng lịch sử thực tế, cần bằng chứng về các mốc đánh giá, phiên bản và kích hoạt, không chỉ dựa vào thứ tự các dòng log từ nhiều máy.

## 5. Cấu trúc một hồ sơ thay đổi

### 5.1. Các trường cần có

| Nhóm | Nội dung |
|---|---|
| Danh tính | Change ID, rule ID, version trước/sau, liên kết quy tắc bị thay thế |
| Nội dung | Phát biểu trước/sau, diff tham số có đơn vị, điều kiện bằng ngưỡng, trường không đổi có liên quan |
| Lý do | Rủi ro/yêu cầu/sự cố nguồn, loại thay đổi và mục tiêu mong đợi |
| Thẩm quyền | Người/vai trò đề xuất, phê duyệt, kích hoạt và căn cứ quyền |
| Hiệu lực | Mốc chọn version, cửa sổ hiệu lực, timezone, tenant/action/currency/kênh |
| Chuyển tiếp | Intent đang chạy, approval cũ, retry/callback, dữ liệu thiếu và ngoại lệ |
| Triển khai | Release, config/schema version, cách kích hoạt, tương thích nhiều phiên bản và điều kiện rollback |
| Xác minh | Test ID, kết quả, bằng chứng kích hoạt và theo dõi sau thay đổi |
| Truy vết | Bản ghi gốc, thời điểm ghi nhận, người/cơ chế ghi, tham chiếu bằng chứng và sửa đổi liên quan |

Không cần chép mọi log vào hồ sơ. Tham chiếu phải đủ cụ thể để người có quyền mở được nguồn tương ứng; tránh đưa credential, token hoặc dữ liệu cá nhân không cần thiết vào lịch sử.

### 5.2. Hồ sơ tổng hợp minh họa

```json
{
  "changeId": "RULE-CHANGE-27",
  "ruleId": "BLS-REF-APPROVAL-COUNT",
  "changeType": "POLICY_CHANGE",
  "fromRuleVersion": 1,
  "toRuleVersion": 2,
  "scope": {
    "tenantId": "tenant-A",
    "action": "ACCEPT_REFUND_EXECUTION",
    "currency": "VND"
  },
  "parameterChange": {
    "name": "singleApproverLimitMinor",
    "before": 50000,
    "after": 30000,
    "comparison": "amount <= limit"
  },
  "selectionPoint": "decisionAt trong transaction chấp nhận",
  "approvedAt": "2026-11-01T09:00:00Z",
  "effectiveFrom": "2026-11-01T10:00:00Z",
  "recordedAt": "2026-11-01T10:02:00Z",
  "reasonRef": "risk-decision-14",
  "approvalRef": "policy-approval-19",
  "releaseRef": "refund-service-release-27",
  "configVersion": "refund-policy-config-12",
  "transitionContractRef": "refund-transition-27",
  "activationEvidenceRef": "activation-tenant-A-27",
  "verificationRefs": ["rule-test-run-27", "post-activation-check-27"]
}
```

Đây là bản tổng hợp sau khi đã có sự kiện kích hoạt; bản đề xuất trước đó cần được phân biệt với bằng chứng áp dụng thực tế. Mọi tham chiếu trong ví dụ là định danh tổng hợp, không phải kết quả triển khai thật.

Một mục lịch sử cũng cần trạng thái có định nghĩa, chẳng hạn dự thảo, đã duyệt, đã lên lịch, đã kích hoạt hoặc đã bị thay thế. Trạng thái quản lý thay đổi khác trạng thái refund intent; không dùng cùng tên mà bỏ semantics.

## 6. Liên kết lịch sử với quyết định nghiệp vụ

### 6.1. Những gì cần lưu tại mốc áp dụng

Với một quyết định chấp nhận, cần đủ dữ liệu để giải thích lựa chọn:

```text
action/intent identity và tenant/resource
    + action type, amount, currency, contentVersion
    + decisionAt và nguồn thời gian theo hợp đồng
    + rule/policy/config version đã chọn
    + approval snapshot và danh tính/ủy quyền liên quan
    + kết quả đánh giá và lý do từ chối/chấp nhận
    + transaction, reservation và outbox đã commit nếu được chấp nhận
```

Không nhất thiết lưu bản sao toàn bộ catalog vào từng sự kiện. Có thể lưu tham chiếu đến snapshot quy tắc được quản lý, miễn là phiên bản ấy còn truy xuất được theo chính sách và không bị ghi đè mất nghĩa.

Lưu version nhưng không lưu đầu vào có thẩm quyền vẫn có thể không tái hiện được quyết định: amount, quan hệ tenant hoặc approval hiện tại có thể đã đổi. Lưu payload client mà không biết dữ liệu nào được server chấp nhận cũng chưa đủ.

### 6.2. Chọn và ghi nhận version trong ranh giới phù hợp

Mã giả cho mô hình chấp nhận trong một database:

```text
BEGIN TRANSACTION
    xác_minh_quyền_truy_cập_action_và_đối_tượng()
    kiểm_tra_danh_tính_nghiệp_vụ_và_yêu_cầu_lặp()
    nếu đây là yêu_cầu_tra_lại_quyết_định_đã_commit:
        trả_tham_chiếu_quyết_định_cũ_theo_hợp_đồng()
    ngược_lại:
        đọc/kiểm_tra_version_dữ_liệu_cần_bảo_vệ()
        decisionAt = lấy_mốc_đánh_giá_có_thẩm_quyền()
        policy = chọn_duy_nhất_theo_scope_và_decisionAt()
        kiểm_tra_nội_dung_approval_số_người_duyệt_state_và_hạn_mức()
        lưu_snapshot_quyết_định_và_policy_version()
        ghi_reservation_và_outbox_đúng_một_lần()
COMMIT
```

Đây là giao thức logic cần được hiện thực bằng khóa/version/ràng buộc phù hợp, không phải bảo đảm tự có chỉ vì ghi `BEGIN TRANSACTION`. Nếu policy nằm ở dịch vụ khác, cần mô tả tính nhất quán, snapshot cấu hình và bằng chứng chọn version giữa các phía. Không coi transaction local là nguyên tử với mọi dịch vụ hoặc provider.

Khi không xác định được một policy bắt buộc duy nhất, không tự chọn bản cũ hoặc ít kiểm soát hơn. Hợp đồng phải quy định từ chối chấp nhận/chờ xử lý phù hợp và giữ bằng chứng về lỗi cấu hình.

## 7. Tái dựng một quyết định cũ bằng lịch sử quy tắc

### 7.1. Quy trình rà soát chỉ đọc

Để kiểm tra một action trong quá khứ:

1. Xác định intent/action/attempt, tenant, resource và các hiệu ứng liên quan. Không chỉ tìm theo `traceId`, amount hoặc IP.
2. Thu thập snapshot đầu vào và quyết định đã commit, bao gồm version mà action ghi nhận đã sử dụng.
3. Lấy hồ sơ hiệu lực, phạm vi và hợp đồng chuyển tiếp để xác minh version ấy có đúng là phiên bản phải dùng không.
4. Đọc nội dung quy tắc, tham số và schema của đúng phiên bản; kiểm tra quyền/phê duyệt tại các mốc được quy định.
5. Đối chiếu kết quả thực thi, reservation, outbox, provider và posting theo mục đích rà soát.
6. Ghi kết luận theo từng kiểm soát, khoảng trống bằng chứng và ngoại lệ cần xử lý.

Action tự ghi `ruleVersion=1` là bằng chứng về lựa chọn mà hệ thống đã ghi nhận, không tự chứng minh lựa chọn đó đúng. Nếu phạm vi và `decisionAt` yêu cầu version 2 nhưng node dùng version 1, lịch sử giúp phát hiện sai lệch ấy.

Tương tự, code đã deploy một bản mới không đủ để kết luận một action đã dùng policy mới. Cần nối phiên bản hiện thực, cấu hình, kích hoạt và quyết định cụ thể.

### 7.2. Tách tái dựng lịch sử với đánh giá giả định

| Hoạt động | Câu hỏi | Cách ghi kết quả |
|---|---|---|
| Đánh giá theo quy tắc thực sự phải áp dụng lúc đó | Action có đáp ứng hợp đồng có hiệu lực trong phạm vi của nó không? | Kết luận lịch sử, kèm nguồn và khoảng trống bằng chứng |
| Kiểm tra lựa chọn version | Hệ thống có chọn đúng rule/policy theo mốc và phạm vi không? | Đúng lựa chọn hoặc ngoại lệ chọn sai |
| Đánh giá giả định bằng policy mới | Nếu gặp chính sách mới, cùng dữ liệu sẽ được xử lý thế nào? | Ghi rõ là giả định, dùng hỗ trợ phân tích tác động |
| Replay nghiệp vụ | Có thực hiện lại lệnh hoặc tạo hiệu ứng mới không? | Là hành động riêng, cần quyền, điều kiện và chống lặp riêng |

Một hàm đánh giá thuần trên snapshot có thể hỗ trợ tái dựng mà không phát lệnh tiền. Không chạy lại handler có side effect chỉ để xem “lần trước sẽ ra gì”. Đặc biệt, replay outbox hoặc callback có thể làm thay đổi dữ liệu nếu cơ chế idempotency hoặc thời hạn bảo vệ không còn như trước.

Kết quả không đạt theo policy mới không tự là vi phạm trong quá khứ. Kết quả đạt theo policy cũ cũng không phủ định một vi phạm khác như sai tenant, sửa amount sau duyệt hoặc tạo hai hiệu ứng cho một intent.

### 7.3. Khi thiếu version hoặc thiếu snapshot

Có thể tìm bằng chứng từ config snapshot, nhật ký kích hoạt, deployment history hoặc audit liên quan để thu hẹp phiên bản. Ghi rõ nguồn, mức chắc chắn và các lựa chọn còn khả dĩ; không tự gán version hiện tại cho mọi record thiếu metadata.

Nếu không đủ dữ liệu chứng minh điều kiện bắt buộc, kết luận là chưa đủ bằng chứng trong phạm vi đó. Nếu đã có bằng chứng chắc chắn về một vi phạm khác gắn đúng action, khoảng trống version không tự xóa vi phạm đã xác nhận. Giữ riêng điều đã chứng minh, điều suy luận và điều còn chưa biết.

## 8. Triển khai nhiều phiên bản và rollback

### 8.1. Chuẩn bị tương thích trước khi kích hoạt

Trước mốc hiệu lực, xác định các đường có thể chấp nhận nghiệp vụ: API công khai, API quản trị, batch, internal service và các công cụ vận hành. Mỗi đường cần hỗ trợ version/schema cần thiết hoặc được chặn đúng phạm vi trong thời gian chuyển đổi.

Trong ví dụ giảm ngưỡng, một node cũ chỉ biết giới hạn 50.000 có thể tiếp tục cho qua khoản 40.000 với một approval sau mốc version 2. Deploy code mới lên một phần node rồi cập nhật policy toàn cục mà không có bảo vệ tương thích sẽ tạo hành vi phụ thuộc vào node nhận request.

Hồ sơ thay đổi cần chỉ ra:

- Code nào có thể đọc/đánh giá từng policy và snapshot schema.
- Phạm vi nào đã sẵn sàng, phạm vi nào còn bị giới hạn chấp nhận.
- Cách xác nhận cấu hình thực tế ở các đường thực thi, không chỉ trạng thái của công cụ deploy.
- Điều kiện bắt đầu kích hoạt, tín hiệu phát hiện sai version và cách dừng an toàn.
- Cách worker xử lý intent đã được chấp nhận theo các phiên bản trước.

Nếu rollout theo tenant hoặc nhóm, giữ bằng chứng kích hoạt cho từng phạm vi. Một cờ `enabled=true` không có scope hoặc lịch sử có thể khiến không tái hiện được tenant nào đã áp dụng vào thời điểm nào.

### 8.2. Rollback kỹ thuật khác khôi phục chính sách cũ

Rollback binary không tự làm policy version 2 hết hiệu lực. Nếu binary cũ không hỗ trợ policy đang áp dụng, cần kế hoạch tương thích hoặc chặn chấp nhận mới trong phạm vi ảnh hưởng; không âm thầm hạ kiểm soát xuống version 1.

Nếu chủ thể có thẩm quyền quyết định thay đổi chính sách trở lại semantics trước, ghi một thay đổi mới với mốc hiệu lực, lý do và chuyển tiếp rõ ràng. Không xóa đoạn lịch sử version 2 hoặc sửa mọi action từng dùng v2 thành v1. Có thể dùng version mới kế tiếp để biểu diễn việc quay lại hành vi cũ, đồng thời giữ đường truy tới quyết định phục hồi chính sách.

Quyết định rollback cũng cần xét approval/snapshot mới, schema mới, các reservation đang tồn tại và message đã commit. Tiền đã đi ra ngoài không được hoàn tác chỉ bằng rollback database hoặc phần mềm; cần đối soát và nghiệp vụ sửa hậu quả theo thẩm quyền.

### 8.3. Giữ an toàn khi phải dừng chấp nhận

Tạm dừng action chấp nhận mới không nhất thiết dừng mọi callback, tra cứu hoặc ghi nhận kết quả. Cần giữ các đường cần thiết để biết hiệu ứng của lệnh đã gửi và phản ánh đúng vào sổ theo hợp đồng.

Không giải phóng reservation của intent chưa rõ kết quả chỉ vì policy bị tắt. Không tạo key hoặc intent mới để “chuyển” một lệnh đang xử lý sang version khác. Hồ sơ thay đổi cần ghi rõ công việc nào tiếp tục, công việc nào bị giữ và điều kiện để tiếp quản an toàn.

## 9. Giữ toàn vẹn lịch sử và sửa thông tin ghi nhận muộn

### 9.1. Giữ bản gốc và bổ sung quan hệ sửa đổi

Hồ sơ đã có hiệu lực nên được quản lý để phát hiện sửa/xóa trái phép và giữ được nguồn gốc. Có thể dùng bản ghi bổ sung, lịch sử phiên bản hoặc cơ chế lưu phù hợp; điều quan trọng là không làm mất nội dung và thẩm quyền của các quyết định trước.

Ví dụ một sự kiện kích hoạt thực tế xảy ra lúc 10:00 nhưng hồ sơ tổng hợp chỉ được bổ sung lúc 10:07. Ghi cả mốc sự kiện đã xác minh và mốc ghi nhận 10:07, kèm bằng chứng. Không sửa timestamp để tạo cảm giác hồ sơ đã tồn tại đầy đủ từ 10:00.

Hai câu hỏi cần được phân biệt:

- Sau khi có đủ bằng chứng, hiện nay ta xác định quy tắc nào đã thực sự có hiệu lực lúc 10:03?
- Tại thời điểm 10:03, hệ thống/người rà soát đã biết gì từ hồ sơ đã được ghi nhận khi ấy?

Sự khác nhau giữa hiệu lực và thời điểm ghi nhận giúp giải thích lỗi quan sát hoặc hồ sơ đến muộn. Nó không cho phép tạo phê duyệt hồi tố để hợp thức hóa thay đổi vốn chưa có thẩm quyền.

### 9.2. Phân biệt dữ liệu gốc với chỉ mục hiện hành

Một trang “policy đang áp dụng” hoặc chỉ mục tra cứu có thể được cập nhật để hiển thị version hiện hành. Nó không nên là nơi duy nhất giữ lịch sử. Khi một version mới thay thế version cũ, khoảng hiệu lực có thể được dựng thành một view từ các sự kiện chuyển tiếp, miễn là vẫn truy được các bản ghi nguồn và quy tắc dựng view.

Nếu phát hiện một mốc bị nhập sai, bổ sung correction liên kết tới record gốc, nêu giá trị cũ/mới, lý do, thẩm quyền và nguồn xác minh. Nếu correction làm thay đổi tập action được đánh giá, cần tạo kết quả rà soát cập nhật và giữ quan hệ với kết luận trước, thay vì xóa âm thầm ngoại lệ.

### 9.3. Quyền truy cập và tính toàn vẹn có giới hạn cụ thể

Quyền sửa code/config không mặc nhiên là quyền phê chuẩn chính sách. Tách các khả năng đề xuất, duyệt, kích hoạt, sửa hồ sơ và rà soát theo mô hình kiểm soát thực tế. Quyền khẩn cấp cần có phạm vi, lý do, dấu vết và kiểm tra sau sử dụng theo quy trình đã được phép.

Digest hoặc chữ ký giúp kiểm tra tính toàn vẹn/nguồn theo cơ chế tin cậy được thiết kế. Chúng không tự chứng minh nội dung chính sách đúng, người phê duyệt đủ thẩm quyền hay mọi node đã tuân theo. Nếu cùng một chủ thể có thể sửa cả nguồn và bằng chứng đối chiếu mà không có dấu vết, cần nêu giới hạn và cơ chế kiểm soát tương ứng.

Lịch sử nên đủ phục vụ tái hiện trong phạm vi lưu giữ đã quy định, đồng thời giới hạn dữ liệu nhạy cảm. Một liên kết tới snapshot đã bị xóa hoặc file mà người rà soát không có cách truy cập được phép có thể làm mất khả năng kiểm chứng.

## 10. Kiểm thử thay đổi và khả năng truy vết

### 10.1. Các ca cần xét cho ví dụ đổi ngưỡng

| Kịch bản | Kết quả kỳ vọng theo hợp đồng minh họa |
|---|---|
| `decisionAt` ngay trước 10:00, amount 40.000, một approval hợp lệ | Chọn v1; có thể chấp nhận nếu mọi quy tắc khác đạt |
| `decisionAt` đúng 10:00, amount 40.000, một approval | Chọn v2; chưa đủ số người duyệt, không tạo công việc thực hiện từ lần thử |
| V2, amount đúng 30.000, một approval | Đạt điều kiện số người duyệt; kiểm tra các điều kiện còn lại |
| V2, amount 30.001, một approval | Chưa đủ theo ngưỡng mới |
| V1, amount 50.000 và 50.001 | Xác minh chính xác dấu `<=` và nhánh trên ngưỡng của v1 |
| Intent 40.000 có một approval trước mốc nhưng chấp nhận sau mốc | Chọn v2 và đòi đủ điều kiện mới; thời điểm tạo/duyệt không thay mốc lựa chọn |
| Intent đã commit theo v1, worker chạy sau mốc | Dùng snapshot/quyết định đã chấp nhận; không áp lại ngưỡng như một action mới |
| Retry cùng key/nội dung cho quyết định đã commit v1 | Tra lại cùng quyết định theo hợp đồng; không tạo reservation hoặc hiệu ứng trùng |
| Key mới nhưng cùng intent đã chấp nhận | Không dùng key mới để nhân nghiệp vụ hoặc đổi version của quyết định cũ |
| Hai approval từ cùng danh tính nghiệp vụ qua hai session | Không tính thành hai người độc lập khi hợp đồng cấm điều đó |
| Tenant ngoài phạm vi pilot | Áp dụng version đúng scope; không tự nhận cấu hình pilot |
| Hai policy cùng khớp mà không có quy tắc ưu tiên hợp lệ | Phát hiện xung đột; không chọn tùy ý bản ít kiểm soát hơn |
| Node cũ và mới cùng nhận request sau kích hoạt | Kết quả chọn policy đúng hợp đồng hoặc node không tương thích bị chặn chấp nhận |
| Provider đã thành công nhưng worker mất phản hồi khi rollout | Giữ identity/reservation và đối soát kết quả; không gửi lệnh thay thế vì đổi policy |

Các mốc “ngay trước/đúng/ngay sau” cần được điều khiển trong fixture bằng nguồn thời gian phù hợp. Không chỉ đổi đồng hồ ở client rồi cho rằng đã kiểm tra mốc đánh giá có thẩm quyền của server.

### 10.2. Test lịch sử, không chỉ test quyết định hiện tại

Sau mỗi kịch bản, kiểm tra quyết định đã lưu có rule/policy/config version đúng, snapshot đầu vào đủ dùng, liên kết approval rõ và các record đã commit khớp nhau. Với yêu cầu bị chặn, kiểm tra không có reservation/outbox hoặc hiệu ứng riêng được tạo từ lần thử ấy; chỉ assert mã lỗi là chưa đủ.

Thử cập nhật policy sang phiên bản tiếp theo rồi tái dựng quyết định cũ từ snapshot. Kết quả lịch sử phải còn giải thích được dù policy hiện tại đổi. Thử làm thiếu snapshot/version để xác minh quy trình báo khoảng trống thay vì mặc định đánh giá bằng bản mới nhất.

Thử thêm correction ghi nhận muộn. Báo cáo mới cần thể hiện căn cứ và khác biệt, giữ kết luận cũ có liên kết, đồng thời xác định những action cần rà soát lại nếu phạm vi hiệu lực thay đổi.

### 10.3. Test cuộc đua và gián đoạn tại mốc chuyển tiếp

Cho transaction chấp nhận bắt đầu trước mốc nhưng lấy `decisionAt` sau mốc; nó phải chọn v2 trong mô hình này. Cho transaction lấy `decisionAt` trước mốc rồi commit sau mốc; phải kiểm tra đúng hợp đồng đã chọn về thời điểm đánh giá, snapshot và tính nhất quán, thay vì tự dùng thời điểm phản hồi.

Tạo điểm dừng để policy/config có thể được cập nhật trong lúc request đang xử lý. Kiểm tra giao thức snapshot/version có ngăn việc lấy ngưỡng từ v1 nhưng lưu nhãn v2 hoặc dùng số người duyệt từ hai snapshot khác nhau không. Một log version đúng nhưng dữ liệu đánh giá trộn nhiều phiên bản vẫn là sai lệch.

Dừng worker sau commit local nhưng trước ACK, rồi khởi động với release mới. Xác minh công việc cũ vẫn đọc được, không đổi payload và không tạo thêm hiệu ứng. Giữ lịch sử fake provider độc lập để phát hiện khoản hoàn trùng; reset cả provider lẫn local sẽ làm mất điều kiện cần kiểm tra.

## 11. Đọc một kết quả rà soát thay đổi

### 11.1. Ví dụ phân loại action

| Action tổng hợp | Bằng chứng | Kết luận có thể đưa ra |
|---|---|---|
| A: 40.000, một người duyệt, `decisionAt` 09:59:58, v1 | Đủ bằng chứng scope, snapshot, quyền và mọi điều kiện khác | Có thể hợp lệ theo v1; worker chạy sau 10:00 không tự làm action sai |
| B: 40.000, một người duyệt, `decisionAt` 10:00:01, v2, bị chặn | Không có reservation/outbox/hiệu ứng từ lần thử | Kiểm soát ngưỡng mới chặn đúng trường hợp chưa đủ điều kiện |
| C: 40.000, một người duyệt, `decisionAt` 10:00:01, v1, được chấp nhận | Scope chắc chắn thuộc v2; node dùng cấu hình cũ | Đã xác nhận chọn sai policy; cần đánh giá tác động thực tế và phạm vi action tương tự |
| D: 40.000, thiếu version và thiếu snapshot quyền/phê duyệt | Chỉ còn trạng thái hiện tại | Chưa đủ bằng chứng cho điều kiện còn thiếu; không suy ra hợp lệ chỉ từ trạng thái |

Đối với C, tiếp tục tách quyết định chấp nhận khỏi hiệu ứng tiền. Có thể đã commit reservation nhưng chưa gửi, đã gửi nhưng chưa rõ kết quả hoặc provider đã thành công. Lịch sử chính sách giúp xác định sai lệch quyết định; kết luận tác động còn cần bằng chứng transaction và provider.

### 11.2. Những cách ghi lịch sử dễ gây hiểu sai

- Chỉ ghi “v2 an toàn hơn”, không lưu phát biểu/giá trị trước và sau.
- Dùng ngày deploy làm mốc hiệu lực cho mọi tenant dù kích hoạt thực tế khác nhau.
- Chọn policy theo timestamp client hoặc thời điểm tạo draft để giữ ngưỡng cũ.
- Chỉ lưu config hiện tại, làm mất khả năng tái hiện các quyết định trước.
- Ghi rule version đúng nhưng thực tế đọc tham số từ cache cũ hoặc nhiều snapshot.
- Gọi lỗi bỏ kiểm tra bắt buộc là “chính sách cũ”, khiến vi phạm bị hợp thức hóa.
- Áp policy mới hồi tố lên mọi action cũ mà không xét hợp đồng chuyển tiếp.
- Coi rollback code là rollback chính sách, dữ liệu và hiệu ứng bên ngoài.
- Sửa hồ sơ gốc hoặc timestamp để che việc ghi nhận/phê duyệt muộn.
- Không kiểm tra admin API, batch và worker, khiến cùng mốc có nhiều cách cấp phép khác nhau.

## 12. Bài thực hành: dựng lịch sử có thể kiểm tra lại

Với fixture đổi ngưỡng 50.000 xuống 30.000 VND:

1. Viết nội dung v1/v2, điều kiện bằng ngưỡng, phạm vi và mốc chọn phiên bản có nguồn thời gian rõ.
2. Lập hồ sơ thay đổi có lý do, thẩm quyền, release/config/schema liên quan, bằng chứng kích hoạt và hợp đồng chuyển tiếp.
3. Tạo các intent trước/sau mốc, gồm một intent đã chấp nhận v1 nhưng còn chờ worker và một intent chỉ mới được duyệt trước mốc.
4. Kiểm tra cả ngưỡng, quyền theo đối tượng, người duyệt độc lập, snapshot nội dung, hạn mức và state machine; không để thay đổi ngưỡng thay thế các kiểm soát khác.
5. Thực hiện retry/restart qua mốc rollout; xác minh version đã chọn, reservation, outbox và lịch sử provider không bị nhân hoặc đổi ý nghĩa.
6. Mô phỏng node dùng cấu hình cũ và một action thiếu version. Lập kết luận riêng cho sai lệch đã xác nhận và khoảng trống bằng chứng.
7. Bổ sung một correction về thời điểm ghi nhận; giữ record gốc và nêu những kết luận phải cập nhật.
8. Lập kế hoạch rollback kỹ thuật và phương án thay đổi chính sách riêng, bao gồm xử lý dữ liệu/công việc đang chạy.
9. Tái dựng action A bằng đúng snapshot quá khứ, rồi đánh giá giả định cùng dữ liệu dưới v2; ghi rõ hai mục đích và không phát sinh side effect.

Sản phẩm gồm hồ sơ thay đổi, timeline hiệu lực/kích hoạt/ghi nhận, bảng ánh xạ action tới phiên bản và bằng chứng, cùng kết quả kiểm thử chuyển tiếp. Một lịch sử sử dụng được phải giúp người có quyền xác định **quy tắc nào thực sự phải áp dụng, hệ thống đã áp dụng quy tắc nào, và bằng chứng nào giải thích sự giống hoặc khác nhau giữa hai điều đó**.
