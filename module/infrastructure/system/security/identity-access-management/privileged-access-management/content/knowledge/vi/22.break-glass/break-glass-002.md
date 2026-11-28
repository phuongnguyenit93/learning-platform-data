# Điều kiện kích hoạt

## 1. Kích hoạt break-glass là một quyết định có giới hạn

Break-glass là cơ chế truy cập khẩn cấp được chuẩn bị để xử lý tình huống đường quản trị thông thường không đáp ứng được nhu cầu khôi phục hoặc ứng phó quan trọng. Trong quản lý truy cập đặc quyền (Privileged Access Management, PAM), cơ chế này có thể phục vụ sự cố của IdP, PAM, quy trình kích hoạt quyền hoặc một thành phần phụ thuộc.

Điều kiện kích hoạt phải trả lời: tình huống nào được phép dùng, ai có thẩm quyền, công việc nào cần thực hiện, bằng đường nào và khi nào phải kết thúc. Việc một tài khoản có sẵn quyền khẩn cấp không có nghĩa mọi người giữ credential đều được sử dụng tùy ý.

Sau bài học, người học có thể:

- Phân biệt nhu cầu khẩn cấp thực sự với sự bất tiện của quy trình thông thường.
- Xây dựng tiêu chí kích hoạt dựa trên tác động, thời gian và khả năng của đường truy cập bình thường.
- Xác định thẩm quyền cùng nhánh xử lý khi hệ thống phê duyệt hoặc liên lạc bị ảnh hưởng.
- Giới hạn phạm vi, thời gian và bằng chứng cho một lần sử dụng.
- Kiểm thử quyết định kích hoạt và điều kiện kết thúc trong môi trường được phép.

Các mức sự cố, thời lượng, vai trò và biểu mẫu trong bài là ví dụ thiết kế. Chúng cần được chủ sở hữu dịch vụ và kiểm soát truy cập cụ thể hóa cho tổ chức.

## 2. Tình huống: PAM không mở được phiên trong lúc dịch vụ cần khôi phục

Dịch vụ payment đang gián đoạn. Người trực ca được phân công cần thực hiện tác vụ khôi phục trên app-pay-01, nhưng broker PAM không tạo được phiên. Một đường khẩn cấp đã được chuẩn bị cho đúng hệ thống và người đủ điều kiện.

Không nên chỉ dựa vào câu “PAM lỗi” để kích hoạt. Cần xác định tác động của dịch vụ, tác vụ cần quyền, tình trạng đường bình thường và lý do không thể chờ theo thời gian đáp ứng đã được định nghĩa.

Nếu broker chỉ lỗi với một client nhưng một đường quản trị bình thường khác vẫn hoạt động, đủ an toàn và đáp ứng thời gian cần thiết, có thể sử dụng đường đó. Nếu lỗi làm mất toàn bộ khả năng thực hiện tác vụ khôi phục cần thiết, điều kiện break-glass có thể được xem xét theo policy.

Quyết định không cho phép mở rộng từ “khôi phục payment-worker trên một máy” thành “dùng mọi quyền quản trị trong suốt ca”. Phạm vi khẩn cấp phải gắn với mục đích đã được xác định.

## 3. Các loại tình huống có thể cần xem xét

| Nhóm tình huống | Vấn đề cần xác minh | Phạm vi khôi phục có thể liên quan |
|---|---|---|
| Đường danh tính không khả dụng | Không thể xác thực bằng đường quản trị thông thường | Khôi phục truy cập hoặc thực hiện tác vụ quan trọng qua đường độc lập đã chuẩn bị |
| Workflow PAM/PIM bị khóa | Không thể kích hoạt quyền hợp lệ do phụ thuộc bị lỗi | Sửa cấu hình hoặc phục hồi khả năng kích hoạt |
| Policy sai gây lockout | Những quản trị viên cần thiết không thể sửa lỗi bằng đường thường | Khôi phục cấu hình truy cập trong phạm vi được phép |
| Thành phần danh tính bị nghi xâm nhập | Đường thường có thể không còn đủ tin cậy dù vẫn hoạt động | Ứng phó theo đường khẩn cấp đã được thiết kế cho tình huống đó |
| Sự cố nghiêm trọng cần thao tác kịp thời | Chậm truy cập làm tăng tác động vượt ngưỡng tổ chức chấp nhận | Tác vụ khống chế hoặc khôi phục được xác định |

Microsoft nêu các ví dụ emergency access như federation không khả dụng, phương thức xác thực thông thường không sử dụng được hoặc quy trình kích hoạt role bị lockout. Những ví dụ này cho thấy cần chuẩn bị cho lỗi của cả công nghệ lẫn phụ thuộc vận hành; chúng không tự tạo quyền sử dụng khẩn cấp cho mọi trường hợp tương tự. [Hướng dẫn emergency access của Microsoft](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access).

Không phải mọi incident đều cần break-glass. Một sự cố nghiêm trọng vẫn có thể được xử lý qua đường bình thường nếu đường đó còn tin cậy và đáp ứng nhu cầu. Ngược lại, đường đăng nhập còn hoạt động không tự có nghĩa nó phù hợp khi chính hệ thống danh tính đang bị điều tra.

## 4. Bộ tiêu chí kích hoạt theo công việc

Một lần sử dụng có thể chỉ được cho phép khi các nhóm điều kiện sau đã được đáp ứng theo policy:

1. **Có nhu cầu đủ nghiêm trọng hoặc đủ khẩn cấp:** tác động hiện tại hoặc sắp xảy ra thuộc tiêu chí tổ chức đã định nghĩa.
2. **Có tác vụ cần thiết và cụ thể:** biết quyền được dùng để khống chế, khôi phục hoặc bảo vệ điều gì.
3. **Đường thông thường không phù hợp:** không khả dụng, không còn đủ tin cậy hoặc không đáp ứng thời gian xử lý được phép.
4. **Đúng chủ thể và thẩm quyền:** người thực hiện cùng người ra quyết định đáp ứng quy trình đã được cho phép.
5. **Có đường khẩn cấp phù hợp:** khả năng truy cập đã được chuẩn bị, còn sử dụng được và không phụ thuộc sai vào thành phần đang lỗi.
6. **Có giới hạn và trách nhiệm:** phạm vi, thời hạn, điều kiện dừng, ghi nhận và đối chiếu được xác định.

Không dùng một phép tính điểm đơn giản để bù trừ các điều kiện cấm. Ví dụ, tác động rất cao không tự hợp thức hóa việc một người không có thẩm quyền sử dụng credential của người khác.

Một số dữ liệu có thể chưa đầy đủ lúc đầu. Policy cần nêu thông tin tối thiểu cho quyết định, phần nào được bổ sung sau và ai chịu trách nhiệm. “Chưa có toàn bộ nguyên nhân gốc” khác với “chưa xác minh được ai đang yêu cầu quyền”.

## 5. Xác định tác động và tính khẩn cấp

Tác động có thể liên quan đến dịch vụ trọng yếu, nguy cơ mất dữ liệu, khả năng tiếp tục lan rộng của một sự cố hoặc mất khả năng kiểm soát truy cập. Tổ chức nên định nghĩa ngưỡng bằng tiêu chí nghiệp vụ và kỹ thuật có thể quan sát.

Không chỉ dựa vào người yêu cầu tự đánh dấu mức cao nhất. Nên có căn cứ như tình trạng dịch vụ, sự kiện giám sát, xác nhận của người điều phối hoặc thông tin từ đội ứng phó.

Tính khẩn cấp cần gắn với cửa sổ ra quyết định. Nếu tác vụ có thể đợi quy trình cấp quyền thông thường mà không làm vượt mức tác động cho phép, break-glass thường chưa phải lựa chọn cần thiết.

Tuy nhiên, không buộc người vận hành thử mọi cách có thể tưởng tượng hoặc chờ hết một thời gian cố định trong khi tác động đang tăng nhanh. Quy trình nên có tập kiểm tra ngắn, thời gian giới hạn và thẩm quyền chuyển nhánh rõ ràng.

Có thể ghi lập luận quyết định như sau:

```text
Tác động đã quan sát:
  Dịch vụ quan trọng không đáp ứng; cần thực hiện tác vụ khôi phục đã xác định.

Hệ quả của việc chờ:
  Dự kiến vượt cửa sổ xử lý được người điều phối cho phép.

Đường thông thường:
  Chưa thể tạo phiên; các kiểm tra tối thiểu cho thấy vấn đề tại thành phần liên quan.

Phạm vi khẩn cấp đề xuất:
  Chỉ tác vụ khôi phục trên tài nguyên đã chỉ định, có mốc đánh giá lại.
```

Đây là lập luận phải được đối chiếu theo tình huống, không phải mẫu câu sao chép để mọi yêu cầu tự đạt điều kiện.

## 6. Kiểm tra đường thông thường trước khi chuyển nhánh

Tập kiểm tra tối thiểu nên được định nghĩa trước theo kiến trúc. Có thể gồm khả năng xác thực, nhận phê duyệt, kích hoạt quyền, lấy credential và mở phiên đến đúng tài nguyên.

Phân biệt những trường hợp sau:

| Quan sát | Ý nghĩa cần xem xét | Có tự đủ để kích hoạt không? |
|---|---|---|
| Một người nhập sai mật khẩu | Có thể là lỗi cá nhân hoặc vấn đề tài khoản | Không |
| Một authenticator bị mất nhưng phương thức dự phòng còn dùng được | Có thể xử lý bằng đường đã cho phép | Không tự động |
| Yêu cầu bị từ chối vì không có quyền | Có thể là kiểm soát hoạt động đúng | Không |
| Broker không mở được phiên cho tài nguyên cần khôi phục | Có thể là lỗi đường quản trị liên quan | Cần xét tác động, đường thay thế và thẩm quyền |
| IdP bị nghi xâm nhập | Có thể không nên tiếp tục tin đường thường | Cần quyết định ứng phó và đường độc lập phù hợp |
| Phê duyệt thông thường đang chờ nhưng không có tác động khẩn cấp | Chưa chứng minh cần vượt workflow | Không |

Không biến break-glass thành cách xử lý một lần từ chối đúng policy. Nếu người dùng cần quyền mới cho công việc thường lệ, đi theo luồng cấp quyền hoặc ngoại lệ phù hợp, không dùng tài khoản khẩn cấp để tự tạo quyền.

Ghi các kiểm tra đã làm, kết quả và thời điểm. Trong sự cố, một bản ghi ngắn nhưng có căn cứ hữu ích hơn một câu chung chung “đã thử tất cả”.

## 7. Đường khẩn cấp phải phù hợp với kiểu sự cố

Tính độc lập là tương đối với một failure mode cụ thể. Một đường dự phòng vẫn cần IdP ngoài tổ chức sẽ không giải quyết sự cố chính IdP đó.

Tài liệu AWS phân biệt cấu hình emergency access qua federation trực tiếp khi IAM Identity Center không khả dụng nhưng IAM data plane và IdP bên ngoài vẫn hoạt động. Nếu không muốn phụ thuộc IdP đó, cần đánh giá thiết kế break-glass tương ứng khác. Đây là ví dụ cho thấy phải đọc rõ giả định hoạt động của từng đường. [Hướng dẫn emergency access của AWS](https://docs.aws.amazon.com/singlesignon/latest/userguide/emergency-access.html).

Trước kích hoạt, kiểm tra đường đã chọn có giải quyết đúng phụ thuộc đang lỗi không:

- Credential có lấy được nếu vault thông thường đang không khả dụng không?
- Người ra quyết định có truy cập được kênh liên lạc dự phòng không?
- Thiết bị và phương thức xác thực còn đáp ứng được luồng khẩn cấp không?
- Đường mạng có cùng điểm lỗi với đường bình thường không?
- Vai trò khẩn cấp có cần kích hoạt qua chính workflow đang hỏng không?

Các vấn đề này cần được chuẩn bị và diễn tập trước. Không giả định có thể tạo mọi role hoặc lấy mọi bí mật sau khi quyền quản trị đã bị khóa.

Nếu đường dự phòng cũng không đáp ứng, chuyển theo phương án khôi phục hoặc hỗ trợ đã được cho phép. Không tự tìm cách chiếm hoặc mở rộng quyền ngoài phạm vi chỉ vì nhánh khẩn cấp đầu tiên không hoạt động.

## 8. Thẩm quyền kích hoạt và vai trò trong sự kiện

Một thiết kế có thể phân biệt người phát hiện/yêu cầu, người điều phối sự cố, người có thẩm quyền chấp thuận sử dụng và người thực hiện. Vai trò có thể do cùng người đảm nhiệm ở một số trường hợp được policy cho phép, nhưng phải ghi rõ.

Với thao tác đặc biệt nhạy cảm, có thể yêu cầu người kiểm tra độc lập hoặc hai người tham gia sử dụng theo cơ chế được hỗ trợ. Không đặt điều kiện nhiều người một cách hình thức nếu trong tình huống dự kiến không ai có thể đáp ứng và không có nhánh thay thế.

Cần tách ba loại quyết định:

| Loại | Ý nghĩa |
|---|---|
| Cho phép từ trước bằng policy | Xác định ai được hành động trong tình huống và giới hạn cụ thể |
| Chấp thuận từng sự kiện | Xác nhận lần sử dụng này đáp ứng điều kiện và phạm vi |
| Xem xét sau sử dụng | Đối chiếu quyết định, hành động và kết quả, tìm sai lệch và cải tiến |

Xem xét sau sự kiện không tự biến một lần dùng không được cho phép thành có phê duyệt trước. Ngược lại, nếu policy đã cho phép một người đủ điều kiện hành động trong nhánh khẩn cấp cuối cùng, không nên đòi thêm một approval thông thường vốn đang không thể thực hiện rồi làm nhánh đó vô dụng.

Nhánh cuối cùng cần được thiết kế rõ: loại sự cố, người được hành động, mức quyền tối đa, cách báo và mốc liên hệ lại. Đây là thẩm quyền được quy định trước, không phải người thực hiện tự tạo quyền khi tình huống xảy ra.

## 9. Phạm vi kích hoạt phải đủ cho tác vụ, không rộng tùy ý

Một lần kích hoạt nên xác định tối thiểu:

- Hệ thống, tenant, tài nguyên hoặc miền quản trị liên quan.
- Mục tiêu khôi phục hoặc khống chế và tác vụ dự kiến.
- Tài khoản, role hoặc credential được sử dụng.
- Người thực hiện và căn cứ thẩm quyền.
- Thời điểm bắt đầu, thời hạn hoặc mốc đánh giá lại.
- Điều kiện phải dừng, mở rộng phạm vi hoặc chuyển người chịu trách nhiệm.

Nếu tài khoản khẩn cấp có quyền kỹ thuật rộng do yêu cầu khôi phục nền tảng, phạm vi nhiệm vụ vẫn phải được giới hạn và giám sát. Không gọi tài khoản đó là least privilege tuyệt đối nếu nó còn nhiều quyền hơn tác vụ hiện tại.

Khi có lựa chọn capability hẹp hơn đáp ứng được nhu cầu, nên dùng lựa chọn đó theo kiến trúc đã chuẩn bị. Nhưng không giả định mọi nền tảng có thể cấp quyền JEA hoặc JIT trong khi chính hệ thống cấp quyền đang lỗi.

Phạm vi mới cần được đánh giá lại. Khôi phục một policy truy cập không tự cho phép đọc dữ liệu nghiệp vụ không liên quan hoặc tạo credential dài hạn cho công việc về sau.

## 10. Xác thực và thiết bị khi sử dụng khẩn cấp

Break-glass không mặc định đồng nghĩa bỏ MFA. Có thể cần phương thức mạnh có phụ thuộc khác đường thường, thiết bị quản trị được chuẩn bị và cách giữ credential phù hợp.

Hướng dẫn Microsoft về emergency access đề cập sử dụng phương thức xác thực mạnh khác với tài khoản quản trị thông thường và kiểm soát các phụ thuộc có thể gây lockout. Vì vậy, thiết kế cần xác định điều gì được thay đổi trong nhánh khẩn cấp, không mô tả chung là “tắt hết kiểm soát”. [Yêu cầu đối với emergency access](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access).

Trước sử dụng, xác minh đúng chủ thể và đường nhận credential. Một tin nhắn khẩn cấp từ tài khoản lạ không đủ để chuyển bí mật. Nếu kênh danh tính thông thường không còn tin cậy, dùng quy trình xác minh dự phòng đã được cho phép.

Nếu nghi máy trạm bị xâm nhập, không nạp thêm credential khẩn cấp lên máy đó chỉ vì công việc gấp. Chọn môi trường quản trị theo phương án đã thiết kế hoặc chuyển người có khả năng sử dụng đường phù hợp.

Không đưa giá trị password, private key, OTP hoặc mã khôi phục vào hồ sơ kích hoạt. Hồ sơ chỉ cần tham chiếu được quản lý và bằng chứng trách nhiệm, không cần bản sao bí mật.

## 11. Bằng chứng tối thiểu ngay khi kích hoạt

Một bản ghi có thể ngắn ở thời điểm bắt đầu nhưng phải đủ để giải thích quyết định. Ví dụ sau là mô hình nội bộ, không phải payload sản phẩm:

```json
{
  "activation_id": "BG-LAB-2202",
  "incident_reference": "INC-LAB-711",
  "trigger_type": "normal-access-path-unavailable",
  "observed_impact": "Critical service recovery requires an administrative action",
  "normal_path_evidence_reference": "diag-lab-711",
  "authority_reference": "emergency-policy-v4-section-b",
  "decision_owner": "incident-commander-lab",
  "executor_reference": "operator-an",
  "emergency_path_reference": "approved-recovery-path-a",
  "target_scope": ["asset-app-pay-01"],
  "task_scope": "approved-service-recovery-task",
  "review_deadline_reference": "server-managed-review-point-711",
  "notification_reference": "incident-channel-event-42"
}
```

Các field cần được xác minh theo quy trình. Một chuỗi `authority_reference` do client tự điền không tự chứng minh thẩm quyền; nó là điểm nối tới policy hoặc quyết định cần đối chiếu.

Nếu ITSM không hoạt động và policy cho phép ghi nhận qua kênh dự phòng, có thể dùng định danh tạm thời được quản lý rồi đối soát sau. Không bịa một ticket đã được phê duyệt hoặc để mất lịch sử vì chưa có hệ thống nhập liệu chính.

Nên lưu thời điểm, căn cứ, người quyết định và phần chưa biết lúc đó. Khi bổ sung thông tin, giữ lịch sử thay đổi thay vì viết lại quyết định ban đầu như thể mọi dữ kiện đều đã rõ.

## 12. Mô hình quyết định kích hoạt

Mã giả dưới đây thể hiện luồng trách nhiệm, không cấp quyền thực tế và không thay thế một policy engine:

```text
function assessEmergencyActivation(event, operator, verifiedContext):
    if normalTrustedPathMeetsRequiredResponseNeed(event, verifiedContext):
        return USE_NORMAL_PATH

    if not eventMeetsApprovedEmergencyCriteria(event, verifiedContext):
        return NOT_ELIGIBLE_FOR_BREAK_GLASS

    if not specificNecessaryTaskDefined(event):
        return CLARIFY_SCOPE_OR_ESCALATE

    if not operatorIsAuthorizedForEmergencyPath(operator, event):
        return ESCALATE_TO_AUTHORIZED_PERSON

    authority = resolveApplicableDecisionAuthority(event, verifiedContext)
    if authority is UNKNOWN:
        return FOLLOW_PREDEFINED_LAST_RESORT_OR_STOP

    path = selectPreparedPathForFailureMode(event, verifiedContext)
    if not pathIsUsableAndAppropriate(path, event):
        return FOLLOW_APPROVED_RECOVERY_ALTERNATIVE

    if not boundedScopeAndReviewPointDefined(event):
        return DEFINE_REQUIRED_BOUNDARIES

    recordActivationBasisAndNotify(event, operator, authority, path)
    return AUTHORIZE_BOUNDED_EMERGENCY_USE
```

Tên `FOLLOW_PREDEFINED_LAST_RESORT_OR_STOP` không cho phép người thực hiện tự quyết có một ngoại lệ vô hạn. Nó chỉ biểu diễn hai nhánh phải được định nghĩa từ trước: có nhánh cuối cùng phù hợp thì áp dụng đúng điều kiện; không có thẩm quyền thì chuyển theo quy trình khôi phục/điều phối được cho phép.

Kết quả cho phép sử dụng khẩn cấp không đồng nghĩa tác vụ đã thành công. Cần tiếp tục quản lý phiên, bằng chứng hành động và điều kiện kết thúc.

## 13. Tình huống không đủ căn cứ kích hoạt

| Yêu cầu | Vì sao chưa đủ | Hướng phù hợp |
|---|---|---|
| “Quy trình duyệt lâu” | Chưa có tác động khẩn cấp hoặc thất bại đường truy cập | Điều phối phê duyệt theo workflow |
| “Tôi cần quyền cao hơn role hiện tại” | Có thể là nhu cầu cấp quyền thường lệ | Đánh giá quyền và phạm vi công việc |
| “Tôi quên authenticator” | Có thể còn đường dự phòng hợp lệ | Khôi phục phương thức theo quy trình |
| “Sắp hết hạn bàn giao” | Áp lực tiến độ không tự tạo thẩm quyền khẩn cấp | Điều phối công việc và người chịu trách nhiệm |
| “Tôi là quản trị viên nên được dùng tài khoản này” | Chưa xác định điều kiện và phạm vi sử dụng | Đối chiếu policy và trách nhiệm |
| “Đã có incident nên dùng mọi quyền” | Incident chưa định nghĩa tác vụ và giới hạn | Làm rõ mục tiêu và quyền cần thiết |

Một lần bị chặn do tài khoản hoặc thiết bị không đáp ứng policy cần được điều tra đúng nguyên nhân. Không xem việc đi qua một kiểm soát đang hoạt động đúng là thất bại nền tảng để hợp thức hóa bypass.

Nếu xuất hiện thông tin mới làm tăng tác động, có thể đánh giá lại. Quyết định “chưa đủ điều kiện” không phải cấm vĩnh viễn; nó phản ánh dữ liệu và thẩm quyền tại thời điểm đó.

## 14. Thời hạn, đánh giá lại và điều kiện dừng

Kích hoạt phải có mốc xem lại phù hợp với công việc. Không có một thời lượng chung cho mọi incident, nhưng không nên cho phép một lần kích hoạt không có điểm kiểm tra tiếp theo.

Các điều kiện đánh giá lại có thể gồm tác vụ không còn đủ, cần thêm tài nguyên, hết mốc thời gian, chuyển người thực hiện hoặc xuất hiện dấu hiệu đường khẩn cấp không còn tin cậy.

Nên dừng hoặc chuyển lại đường thường khi đã khôi phục khả năng quản trị cần thiết, mục tiêu khẩn cấp hoàn thành hoặc thẩm quyền sử dụng kết thúc. Nếu cần tiếp tục, ghi căn cứ cho phần gia hạn hoặc phạm vi mới.

Phân biệt thời hạn nhiệm vụ với trạng thái sẵn sàng của tài khoản khôi phục. Một số kiến trúc cần tài khoản khẩn cấp tồn tại và sẵn sàng lâu dài. Đóng incident không có nghĩa tùy tiện xóa hoặc vô hiệu hóa mọi đường khôi phục; cần kết thúc lần sử dụng, xử lý phiên, quyền tạm và credential theo thiết kế.

Nếu bí mật đã được tiết lộ hoặc có khả năng mất kiểm soát, đánh giá việc luân chuyển và các phụ thuộc. Đừng coi nhãn “incident closed” là bằng chứng credential đã được xử lý.

## 15. Giám sát và đối chiếu sau sử dụng

Mỗi lần dùng đường khẩn cấp cần được nhìn thấy bởi người có trách nhiệm. Nếu hệ thống cảnh báo chính bị ảnh hưởng, cần kênh ghi nhận và thông báo dự phòng đã được thiết kế, không im lặng bỏ qua.

Đối chiếu sau sử dụng nên xác định:

- Điều kiện kích hoạt có phù hợp với policy và dữ kiện lúc đó không?
- Người quyết định và người thực hiện có đúng thẩm quyền không?
- Hành động thực tế có nằm trong mục tiêu và phạm vi đã cho phép không?
- Có quyền, phiên, token, thay đổi hoặc credential nào còn phải xử lý không?
- Điểm lỗi nào khiến phải dùng break-glass và cần cải tiến điều gì?

Việc điều tra phải dựa trên bằng chứng, không mặc định mọi sử dụng khẩn cấp đều là lạm dụng. Ngược lại, một kết quả khôi phục thành công cũng không tự chứng minh mọi hành động đã đúng phạm vi.

NIST SP 800-61 Rev. 3 đặt hoạt động chuẩn bị, phát hiện, ứng phó và khôi phục trong quản lý rủi ro rộng hơn. Với break-glass, cách áp dụng hữu ích là đưa bài học từ lần sử dụng trở lại policy, đường khôi phục và kế hoạch diễn tập, thay vì chỉ lưu một biên bản rồi kết thúc. [Hướng dẫn incident response của NIST](https://csrc.nist.gov/pubs/sp/800/61/r3/final).

## 16. Kiểm thử tiêu chí bằng tabletop và lab

Diễn tập không phải sự cố thật. Cần có kế hoạch, người biết việc diễn tập, tài nguyên được phép và cách phân loại cảnh báo phát sinh. Không tạo gián đoạn production chỉ để xem có đủ điều kiện kích hoạt hay không.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Dịch vụ quan trọng gián đoạn, đường thường lỗi, đúng người và đúng đường dự phòng | Có thể cho phép phạm vi khẩn cấp theo policy |
| Chỉ một người lỗi đăng nhập, đường thường khác đáp ứng nhu cầu | Không tự kích hoạt break-glass |
| Bị từ chối đúng quyền trong công việc thường lệ | Chuyển luồng cấp quyền, không dùng tài khoản khẩn cấp |
| IAM Identity Center lỗi nhưng đường dự phòng vẫn cần IdP cũng đang lỗi | Phát hiện đường không phù hợp failure mode |
| Hệ thống phê duyệt chính không dùng được | Áp đúng nhánh thẩm quyền dự phòng, không tự bỏ quy trình |
| ITSM không hoạt động nhưng policy cho phép hồ sơ tạm | Ghi nhận tối thiểu qua kênh được phép và đối soát sau |
| Người yêu cầu ngoài danh sách được phép | Chuyển người có thẩm quyền, không giao credential tùy ý |
| Phạm vi cần mở rộng sau khi bắt đầu | Đánh giá và ghi quyết định mới phù hợp |
| Đường bình thường phục hồi trong lúc thao tác | Đánh giá kết thúc hoặc chuyển về đường thường |
| Mốc thời gian hết nhưng công việc chưa hoàn thành | Đánh giá lại, không tự kéo dài vô hạn |
| Đường khẩn cấp bị nghi mất tin cậy | Dừng hoặc chuyển theo phương án được cho phép |
| Tác vụ hoàn thành nhưng token/quyền tạm còn tồn tại | Phát hiện và xử lý trước khi đóng lần sử dụng |

Bằng chứng diễn tập cần cho thấy chất lượng quyết định, không chỉ việc đăng nhập được. Có thể một đường kỹ thuật hoạt động nhưng chưa đủ người có thẩm quyền, hoặc một điều kiện kích hoạt đúng nhưng runbook lại phụ thuộc chính thành phần đang lỗi.

## 17. Thực hành xây dựng điều kiện kích hoạt

Chọn một failure mode cụ thể trong lab, chẳng hạn broker PAM không tạo được phiên khi cần khôi phục dịch vụ giả lập. Xác định tác động, tác vụ cần thiết, kiểm tra đường thường và mốc thời gian quyết định.

Viết tiêu chí cho phép và không cho phép, danh sách vai trò có thẩm quyền, nhánh liên lạc dự phòng và giới hạn sử dụng. Mô tả đường khẩn cấp cùng các giả định mà nó cần để hoạt động.

Cuối cùng, chạy tabletop với một kịch bản đủ điều kiện và một kịch bản chỉ có sự bất tiện. Kết quả đạt yêu cầu khi người tham gia có thể đưa ra quyết định nhất quán, giữ đúng thẩm quyền, xác định phạm vi hữu ích và biết rõ khi nào phải kết thúc hoặc đánh giá lại.
