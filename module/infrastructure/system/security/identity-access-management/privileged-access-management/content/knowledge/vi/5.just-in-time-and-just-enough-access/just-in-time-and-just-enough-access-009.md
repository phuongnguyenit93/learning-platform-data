# Gia hạn JIT có kiểm soát

Just-in-Time (JIT) cấp quyền đặc biệt trong một khoảng thời gian xác định để thực hiện nhiệm vụ cụ thể. Khi công việc chưa hoàn tất, nhu cầu kéo dài thời gian có thể hợp lệ, nhưng thao tác gia hạn cũng là một quyết định cấp quyền mới: hệ thống cho phép người dùng hoặc workload tiếp tục tác động lên tài nguyên nhạy cảm lâu hơn dự kiến.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), gia hạn có kiểm soát phải gắn thời hạn bổ sung với nhu cầu còn tồn tại, trạng thái rủi ro hiện tại, phạm vi quyền tối thiểu và khả năng thu hồi thực tế. Điều này áp dụng cho phiên quản trị, quyền truy cập hạ tầng, nhóm đặc quyền tạm thời và quyền của tài khoản dịch vụ khi cơ chế cấp quyền hỗ trợ thời hạn.

Trong chương **JIT và JEA**, cần giữ hai ràng buộc đồng thời: JIT giới hạn thời gian; Just Enough Administration (JEA) giới hạn những hành động được phép. Gia hạn thời gian không mặc nhiên mở thêm lệnh, máy chủ, dữ liệu hoặc quyền lấy credential từ vault.

## 1. Gia hạn là quyết định tiếp tục cấp quyền

Giả sử kỹ sư trực ca được quyền khởi động lại một dịch vụ trên `APP-PAY-02` từ 09:00 đến 09:30. Đến 09:20, việc xác minh kết quả còn cần thêm mười lăm phút. Hệ thống có thể xem xét đổi mốc hết hạn từ 09:30 sang 09:45, với điều kiện nhu cầu, người dùng, tài nguyên và mức quyền vẫn phù hợp.

Không thể chỉ dựa vào việc người dùng đang có một phiên hoạt động. Hoạt động liên tục có thể phản ánh công việc hợp lệ, nhưng cũng có thể là thao tác ngoài nhiệm vụ hoặc phiên đã bị chiếm quyền.

| Tình huống | Cách xử lý phù hợp | Lý do |
| --- | --- | --- |
| Công việc cũ chưa xong, phạm vi không đổi, quyền còn hiệu lực | Xem xét gia hạn theo chính sách | Nhu cầu tiếp tục có thể kiểm chứng được |
| Cần thêm máy chủ, lệnh hoặc loại quyền | Yêu cầu cấp quyền mới hoặc đánh giá lại phạm vi riêng | Đây là thay đổi quyền, không chỉ đổi thời gian |
| Quyền đã hết hạn | Kết thúc quyền cũ; đánh giá yêu cầu mới | Không hồi tố để che khoảng thời gian không còn quyền |
| Đang xử lý sự cố và cần vượt giới hạn thông thường | Dùng quy trình ngoại lệ hoặc break-glass được quy định | Tránh âm thầm phá giới hạn tích lũy |
| Có tín hiệu nghi ngờ tài khoản bị chiếm quyền | Từ chối gia hạn và kích hoạt xử lý phù hợp | Phê duyệt trước đó không bảo đảm trạng thái hiện tại an toàn |

Cần phân biệt **đủ điều kiện được yêu cầu quyền**, **quyền đã kích hoạt**, **phiên đăng nhập** và **credential hoặc token được dùng ở đích**. Kéo dài tính đủ điều kiện không đồng nghĩa đã gia hạn phiên; đổi thời hạn trên một bản ghi PAM cũng không bảo đảm token ở tài nguyên đích thay đổi theo.

## 2. Xác định hợp đồng thời gian

Một chính sách gia hạn nên xác định rõ các mốc:

- `t_start`: thời điểm bắt đầu của lần cấp quyền ban đầu.
- `expires_at`: mốc hết hạn đang có hiệu lực.
- `requested_expires_at`: mốc hết hạn người dùng muốn đạt tới.
- `max_single_extension`: thời lượng được bổ sung tối đa trong một lần.
- `absolute_deadline`: giới hạn cuối cùng của toàn bộ lần cấp quyền.
- `extension_count`: số lần gia hạn đã thực sự áp dụng thành công.
- `renewal_window`: khoảng thời gian cho phép gửi yêu cầu trước khi hết hạn.

Ví dụ, một lần cấp quyền có thể được duy trì tối đa chín mươi phút tính từ `t_start`, mỗi lần gia hạn tối đa mười lăm phút và chỉ cho phép hai lần gia hạn. Đây là các giá trị minh họa; hệ thống cần chọn giới hạn theo tác vụ, mức rủi ro và khả năng vận hành.

### 2.1. Phân biệt cộng thêm thời lượng và đặt lại TTL

Nếu thời hạn hiện tại là 09:30, yêu cầu bổ sung mười lăm phút có thể có nghĩa là mốc mới 09:45. Nếu giao diện lại diễn giải thành “mười lăm phút tính từ hiện tại”, một yêu cầu ở 09:20 sẽ tạo ra mốc 09:35. Hai cách hiểu tạo kết quả khác nhau.

Vì vậy, cần hiển thị và ghi nhận **mốc hết hạn hiện tại**, **mốc đề nghị** và **thời lượng tăng thêm**. Tránh dùng một nút “thêm 15 phút” mà không xác định rõ mốc tính.

Một mô hình đặt giới hạn có thể biểu diễn như sau:

```text
absolute_deadline = min(
    t_start + max_total_lifetime,
    approved_change_window_end,
    task_deadline
)

requested_expires_at > expires_at
requested_expires_at - expires_at <= max_single_extension
requested_expires_at <= absolute_deadline
extension_count + 1 <= max_extensions
```

Chỉ đưa các mốc cửa sổ thay đổi hoặc hạn nhiệm vụ vào phép tính khi chính sách thực sự sử dụng chúng. Nếu một điều kiện bắt buộc không có dữ liệu đáng tin cậy, hệ thống cần từ chối hoặc chuyển sang xử lý ngoại lệ theo quy định.

### 2.2. Giữ nguyên mốc bắt đầu ban đầu

Không đặt lại `t_start` sau mỗi lần gia hạn. Nếu mỗi lần đều khởi tạo một khoảng thời gian tối đa mới, người dùng có thể duy trì quyền gần như liên tục dù từng lần gia hạn rất ngắn.

Giới hạn theo một lần cấp quyền cũng có thể bị vô hiệu hóa bằng cách tạo liên tiếp các yêu cầu mới cho cùng công việc. Với quyền rủi ro cao, nên đối chiếu thêm lịch sử theo người dùng, nhiệm vụ và tài sản trong khoảng thời gian phù hợp. Nhu cầu truy cập thường xuyên cần được đánh giá lại cách tổ chức công việc và vai trò.

### 2.3. Dùng thời gian của hệ thống có thẩm quyền

Các mốc hết hạn phải dựa trên đồng hồ phía hệ thống cấp quyền và thành phần cưỡng chế, có đồng bộ thời gian và định dạng không gây nhầm múi giờ. Có thể lưu UTC rồi chuyển đổi khi hiển thị cho người dùng.

Người dùng gửi yêu cầu trước hạn không có nghĩa hệ thống được phép áp dụng sau hạn. Cần kiểm tra lại hiệu lực ngay trước thời điểm cập nhật và tại điểm thực thi. Thời gian chờ phê duyệt hoặc lỗi mạng không tự tạo ra khoảng ân hạn.

## 3. Tái đánh giá trước khi đồng ý

Một yêu cầu gia hạn nên kèm lý do công việc còn dang dở, kết quả đã đạt được, phần việc còn lại, thời lượng cần thêm và tham chiếu tới nhiệm vụ hoặc sự cố. Câu mô tả “cần thêm thời gian” thường không đủ để người duyệt đánh giá.

| Nhóm điều kiện | Nội dung cần xác minh | Khi điều kiện không còn đạt |
| --- | --- | --- |
| Danh tính | Tài khoản còn hợp lệ, chưa bị khóa hoặc thu hồi | Từ chối; xử lý quyền đang hoạt động theo chính sách |
| Xác thực | Mức bảo đảm và độ mới của xác thực đáp ứng yêu cầu | Yêu cầu xác thực tăng cường nếu chính sách cho phép |
| Thiết bị và phiên | Thiết bị được phép, phiên không có dấu hiệu rủi ro mới | Chặn gia hạn hoặc chuyển xử lý sự cố |
| Nhiệm vụ | Phiếu còn mở, người dùng còn được phân công | Từ chối nếu nhu cầu không còn tồn tại |
| Phạm vi | Vai trò, hành động và tài sản không tăng so với phạm vi đã duyệt | Chuyển thành yêu cầu đánh giá quyền mới |
| Thời gian | Chưa hết hạn, còn trong giới hạn tích lũy và cửa sổ được phép | Từ chối hoặc dùng quy trình ngoại lệ rõ ràng |
| Phê duyệt | Đúng người duyệt, không tự duyệt, còn phù hợp với yêu cầu | Không áp dụng khi thiếu phê duyệt bắt buộc |
| Khả năng cưỡng chế | Hệ thống đích có thể áp dụng và xác minh thời hạn | Không báo thành công chỉ dựa vào bản ghi nội bộ |

Việc yêu cầu xác thực lại không thay thế cho phê duyệt công việc. Ngược lại, người quản lý đồng ý cũng không thay thế cho kiểm tra danh tính và trạng thái rủi ro.

Đối với tài khoản dịch vụ hoặc workload, không áp dụng máy móc việc yêu cầu MFA tương tác. Cần dựa vào danh tính workload, ràng buộc môi trường thực thi, nguồn yêu cầu đáng tin cậy và chính sách do chủ sở hữu dịch vụ quản lý.

## 4. Phê duyệt gắn với đúng nội dung yêu cầu

Người duyệt cần thấy tối thiểu ai đang có quyền, quyền gì, trên tài sản nào, đã sử dụng bao lâu, còn công việc gì và mốc hết hạn mới được đề nghị. Quyết định nên gắn với một phiên bản cụ thể của yêu cầu.

Nếu người yêu cầu thay đổi mốc hết hạn, danh sách tài sản hoặc loại quyền sau phê duyệt, không dùng lại quyết định cũ một cách mặc định. Hệ thống phải xác định thay đổi nào làm mất hiệu lực phê duyệt và yêu cầu đánh giá lại.

Có thể thiết kế các nhánh khác nhau:

- Tác vụ rủi ro thấp, phạm vi rất hẹp: tự động quyết định theo chính sách đã được phê duyệt trước, nếu mọi điều kiện vẫn đạt.
- Tác vụ quản trị thông thường: một người duyệt độc lập kiểm tra phần việc còn lại và thời hạn bổ sung.
- Tác vụ có tác động lớn: cần thêm người có thẩm quyền về tài sản hoặc an ninh theo cơ chế phân tách nhiệm vụ.

Tự động hóa có kiểm soát vẫn phải lưu điều kiện đã xét và phiên bản chính sách. Không xem việc có hoạt động bàn phím, phiên còn kết nối hoặc một tác vụ tự gửi heartbeat là đủ lý do để gia hạn.

Người phê duyệt không nên có khả năng bỏ qua giới hạn cứng bằng một thao tác phê duyệt thông thường. Nếu có ngoại lệ, phải biểu diễn thành loại quyết định riêng, với thẩm quyền, lý do, thời hạn và bằng chứng riêng.

## 5. Vòng đời yêu cầu gia hạn

Nên theo dõi riêng trạng thái của **lần cấp quyền** và trạng thái của **yêu cầu gia hạn**. Trong lúc yêu cầu đang chờ, quyền cũ chỉ có hiệu lực đến mốc hết hạn cũ.

| Trạng thái yêu cầu | Ý nghĩa | Có kéo dài quyền chưa? |
| --- | --- | --- |
| `REQUESTED` | Đã tiếp nhận đề nghị | Chưa |
| `APPROVED` | Đã có quyết định phù hợp với nội dung yêu cầu | Chưa |
| `APPLYING` | Đang cập nhật các thành phần cưỡng chế liên quan | Chưa được coi là hoàn tất |
| `APPLIED` | Đã xác minh thời hạn mới được áp dụng theo hợp đồng hệ thống | Có, trong phạm vi đã xác nhận |
| `REJECTED` | Không đáp ứng chính sách hoặc không được duyệt | Không |
| `EXPIRED` | Yêu cầu không còn áp dụng được vì đã qua hạn | Không |
| `RECONCILIATION_REQUIRED` | Kết quả cập nhật chưa xác định hoặc các hệ thống không nhất quán | Phải đối soát; không báo thành công |

Tên trạng thái là ví dụ thiết kế, không phải chuẩn chung của các sản phẩm PAM.

Một lần cấp quyền ở trạng thái bị thu hồi không được phục hồi bởi kết quả gia hạn đến muộn. Nếu quyền hết hạn trong khi đang chờ duyệt, yêu cầu gia hạn phải kết thúc theo chính sách; nhu cầu tiếp tục được chuyển sang yêu cầu cấp quyền mới.

### 5.1. Trình tự áp dụng

1. Nhận yêu cầu với định danh chống trùng, mã lần cấp quyền và mốc hết hạn đề nghị.
2. Đọc trạng thái hiện tại từ nguồn có thẩm quyền; xác minh người gọi, nhiệm vụ, phạm vi và thời hạn.
3. Thu thập phê duyệt hoặc đánh giá chính sách tự động theo mức rủi ro.
4. Ngay trước khi áp dụng, kiểm tra lại hiệu lực của quyền, phiên bản chính sách, phê duyệt và trạng thái rủi ro.
5. Cập nhật thời hạn tại những thành phần thực sự quyết định truy cập theo cơ chế an toàn của nền tảng.
6. Đọc lại hoặc xác minh kết quả theo hợp đồng tích hợp, rồi ghi nhận lần gia hạn đã áp dụng.
7. Thông báo mốc hết hạn mới đã xác nhận và tiếp tục giám sát, thu hồi khi đến hạn hoặc khi có điều kiện thu hồi sớm.

Nếu chỉ cập nhật thời gian trên giao diện mà nhóm, token, phiên hoặc quyền ở đích không tuân theo, quy trình chưa hoàn thành.

### 5.2. Minh họa quyết định chính sách

Đoạn giả mã dưới đây chỉ minh họa bước đánh giá. Nó không tạo ra một giao dịch nguyên tử giữa cơ sở dữ liệu PAM và các hệ thống đích.

```text
evaluate_extension(grant, request, context, policy, now):
    require grant.state == ACTIVE
    require now < grant.expires_at
    require request.expected_revision == grant.revision
    require request.scope_fingerprint == grant.scope_fingerprint
    require identity_and_risk_checks_pass(context, policy)
    require approval_matches_request(request, context, policy)
    require task_is_still_valid(context)
    require inside_renewal_window(now, grant, policy)

    proposed_end = request.requested_expires_at
    require proposed_end > grant.expires_at
    require proposed_end - grant.expires_at <= policy.max_single_extension
    require proposed_end <= compute_absolute_deadline(grant, context, policy)
    require grant.extension_count < policy.max_extensions

    return AuthorizedIntent(
        grant_id = grant.id,
        expected_revision = grant.revision,
        old_end = grant.expires_at,
        new_end = proposed_end,
        request_id = request.id,
        policy_version = policy.version
    )
```

Kết quả đánh giá phải gắn với đúng phiên bản quyền và nội dung yêu cầu. Trước khi cập nhật, thành phần thực thi phải phát hiện nếu quyền đã bị sửa, thu hồi hoặc hết hạn sau bước đánh giá. Một quyết định chấp thuận cũ không phải giấy phép cập nhật vô thời hạn.

## 6. Xử lý yêu cầu đồng thời và lỗi tích hợp

### 6.1. Hai yêu cầu gia hạn cùng lúc

Giả sử thời hạn hiện tại là 09:30, số lần gia hạn đã dùng bằng không. Hai yêu cầu cùng đọc trạng thái đó rồi cùng đề nghị thêm mười lăm phút. Nếu mỗi tiến trình tự cộng thời lượng hoặc tự tăng bộ đếm mà không kiểm soát đồng thời, hệ thống có thể cộng hai lần hoặc ghi đè kết quả của nhau.

Các cơ chế thường cần có gồm:

- Khóa ngắn hoặc cập nhật có điều kiện theo `revision` để phát hiện trạng thái đã đổi.
- Mã yêu cầu ổn định và cơ chế idempotency để gửi lại cùng một yêu cầu không gia hạn thêm lần nữa.
- Ràng buộc idempotency với người gọi, lần cấp quyền và nội dung; từ chối nếu cùng mã nhưng nội dung khác.
- Dùng mốc hết hạn tuyệt đối đã duyệt khi gọi lại API, nếu nền tảng hỗ trợ, thay vì lặp lệnh “cộng thêm thời gian”.
- Kiểm tra lại giới hạn tích lũy và số lần gia hạn khi xác nhận kết quả.

Không giữ một khóa cơ sở dữ liệu trong suốt thời gian chờ người duyệt. Yêu cầu chờ cần lưu phiên bản tham chiếu; khi quay lại phải phát hiện thay đổi và đánh giá lại.

### 6.2. Phê duyệt chậm hoặc cập nhật sát giờ hết hạn

Người dùng gửi yêu cầu lúc 09:29, nhưng quyền hết hạn lúc 09:30 và người duyệt đồng ý lúc 09:31. Đây không còn là gia hạn một quyền đang hoạt động. Hệ thống không được đổi thời gian trong quá khứ để làm cho khoảng gián đoạn có vẻ hợp lệ.

Đối với yêu cầu sát hạn, cần dành đủ thời gian cho phê duyệt và áp dụng. Cửa sổ gửi yêu cầu giúp hạn chế tình huống này, nhưng không thay thế kiểm tra thời gian tại điểm cập nhật.

Nếu cập nhật hệ thống đích có thể kéo dài qua thời hạn cũ, hợp đồng tích hợp phải xác định rõ khi nào quyết định còn được chấp nhận, cách từ chối quyết định đã cũ và cách xử lý trạng thái không chắc chắn. Không giả định việc đã bắt đầu gọi API trước hạn là đủ để tiếp tục quyền sau hạn.

### 6.3. Timeout không chứng minh thao tác thất bại

Sau khi gửi cập nhật, hệ thống PAM có thể nhận timeout dù hệ thống đích đã áp dụng. Nếu gửi lại một lệnh cộng thêm thời lượng, quyền có thể bị kéo dài quá mức.

Trong tình huống này, cần truy vấn theo định danh thao tác hoặc đọc lại trạng thái đích, sử dụng khả năng idempotency của nền tảng và đối soát thời hạn mong muốn với thời hạn thực tế. Nếu chưa biết kết quả, hiển thị trạng thái chưa xác định thay vì khẳng định thành công hoặc tự thử lặp vô hạn.

Cũng có thể xảy ra tình huống đích đã gia hạn nhưng việc ghi nhận tại PAM thất bại. Bộ đối soát cần phát hiện quyền tồn tại quá bản ghi cho phép. Nếu không thể khôi phục trạng thái nhất quán trong giới hạn an toàn đã định, kích hoạt quy trình thu hồi hoặc cô lập phù hợp và báo cho người chịu trách nhiệm.

Việc bù trừ cũng phải dựa trên phiên bản hiện tại. Không dùng dữ liệu cũ để ghi đè một quyết định thu hồi hoặc một thay đổi hợp lệ mới hơn.

## 7. Cưỡng chế thời hạn ở các lớp truy cập

Cần lập bản đồ quyền từ yêu cầu PAM đến nơi tài nguyên thực sự chấp nhận hành động. Mỗi cơ chế có cách hết hạn và thu hồi khác nhau.

| Cơ chế | Điều cần làm rõ khi gia hạn | Điều cần làm rõ khi hết hạn |
| --- | --- | --- |
| Thành viên nhóm đặc quyền tạm thời | Thời hạn được cập nhật ở đâu; có sao chép hoặc cache không | Xóa nhóm có ảnh hưởng thế nào đến token và phiên đã mở |
| Phiên qua gateway hoặc proxy PAM | Thành phần nào điều khiển thời lượng phiên; có đồng bộ với quyền đích không | Gateway có kết thúc phiên và ngăn kết nối lại đúng hạn không |
| Token ngắn hạn | Token có thể đổi hạn hay phải cấp token mới | Token cũ còn giá trị bao lâu; có cơ chế thu hồi hoặc kiểm tra trực tuyến không |
| Lease credential hoặc bí mật động | Lease nào được gia hạn; backend đích nhận thay đổi ra sao | Hết lease có thu hồi quyền ở đích hay chỉ kết thúc bản ghi quản lý |
| Endpoint JEA | Người dùng được vào endpoint nào và tập lệnh hiệu lực ra sao | Phiên đang mở có tiếp tục dùng được sau khi quyền truy cập bị gỡ không |
| Workload chạy dài | Danh tính workload nào được phép tiếp tục, tác vụ nào còn hợp lệ | Tiến trình đang chạy hoặc kết nối đã thiết lập có bị dừng không |

Với một số token mang thời hạn được ký bên trong, không thể chỉ sửa bản ghi để token cũ có mốc hết hạn mới. Hệ thống có thể phải cấp token khác theo quy trình được hỗ trợ. Nếu tồn tại đồng thời token cũ và mới, cần tính cả khoảng chồng lấn và khả năng sử dụng lại token cũ.

Một lease trong vault và quyền thực tế của credential trên hệ thống đích là hai trạng thái cần đối chiếu. Không giả định rằng đổi TTL trong vault luôn làm cho hệ điều hành, cơ sở dữ liệu hoặc API đích áp dụng thời hạn tương ứng.

Cũng không cần luân chuyển mọi mật khẩu sau mỗi lần gia hạn chỉ vì đó là tài khoản đặc quyền. Luân chuyển phải theo vòng đời credential và chính sách của cơ chế sử dụng. Khi có nghi ngờ lộ bí mật hoặc thu hồi một credential dùng chung, cần xác định các phiên, dịch vụ và kết nối bị ảnh hưởng để xử lý nhất quán.

Quan trọng nhất là không đánh đồng hết quyền với dừng mọi công việc đã bắt đầu. Một tiến trình, truy vấn hoặc thao tác triển khai có thể tiếp tục sau khi quyền khởi tạo nó hết hạn. Chính sách phải xác định có cho phép tác vụ đang chạy hoàn tất hay cần hủy, ai chịu trách nhiệm và giới hạn tác động còn lại.

## 8. Ví dụ: kéo dài tác vụ xử lý sự cố dịch vụ

Giả sử kỹ sư trực ca cần xử lý sự cố trên `APP-PAY-02`. Vai trò JEA chỉ cho xem trạng thái và khởi động lại dịch vụ `ContosoBillingAgent`; không cho sửa tệp thực thi, thay cấu hình bảo mật hoặc lấy credential dịch vụ.

Chính sách minh họa:

- Lần cấp quyền bắt đầu lúc 09:00 và hết hạn ban đầu lúc 09:30.
- Mỗi lần được bổ sung tối đa mười lăm phút.
- Toàn bộ lần cấp quyền không được kéo dài quá 10:30, tức chín mươi phút từ lúc bắt đầu.
- Tối đa hai lần gia hạn thành công.
- Chỉ tiếp nhận đề nghị trong mười lăm phút cuối của thời hạn hiện hành.
- Cần một người duyệt độc lập và nhiệm vụ xử lý sự cố còn mở.

Các mốc dưới đây được hiển thị trong cùng một múi giờ để dễ theo dõi.

| Thời điểm | Sự kiện | Kết quả theo chính sách minh họa |
| --- | --- | --- |
| 09:20 | Đề nghị đổi mốc hết hạn từ 09:30 sang 09:45, kèm phần việc còn lại | Được đưa vào đánh giá |
| 09:24 | Đủ phê duyệt, điều kiện còn đạt, đích xác nhận mốc 09:45 | Ghi lần gia hạn thứ nhất |
| 09:40 | Đề nghị đổi mốc hết hạn từ 09:45 sang 10:00 | Có thể được xét vì còn trong cửa sổ, số lần và giới hạn tổng |
| 09:43 | Đích xác nhận mốc 10:00 sau khi kiểm tra lại điều kiện | Ghi lần gia hạn thứ hai |
| 09:55 | Đề nghị tiếp tục tới 10:15 | Từ chối gia hạn thông thường vì đã đủ hai lần |
| 10:00 | Chưa có quyết định ngoại lệ hợp lệ | Thực hiện hết hạn và thu hồi theo cơ chế đã thiết kế |

Giới hạn 10:30 là một trần bổ sung, không phải cam kết người dùng luôn được dùng đến 10:30. Mọi điều kiện phải đồng thời đạt; chạm giới hạn số lần vẫn phải dừng dù chưa chạm trần thời gian.

Nếu tại 09:40 kỹ sư cần quyền sửa cấu hình hoặc thêm máy chủ `DB-PAY-01`, yêu cầu đó phải được đánh giá như thay đổi phạm vi. Không ghép quyền mới vào lần gia hạn của vai trò đang có.

Nếu công việc hoàn tất lúc 09:35, nên kết thúc quyền sớm theo workflow thay vì giữ đến hết 09:45. Mốc hết hạn là giới hạn tối đa được sử dụng, không phải thời gian bắt buộc phải duy trì quyền.

## 9. Bằng chứng cho từng lần gia hạn

Một bản ghi quyết định có giá trị kiểm toán cần nối được yêu cầu ban đầu, lần gia hạn và trạng thái thực tế ở đích. Nên lưu:

- Định danh lần cấp quyền, yêu cầu gia hạn và phiên hoặc workload liên quan.
- Người yêu cầu, người được hưởng quyền, người duyệt hoặc chính sách tự động đã quyết định.
- Lý do, mã nhiệm vụ và bằng chứng phần việc còn dang dở.
- Phạm vi vai trò, hành động, tài sản và dấu vết phiên bản phạm vi đã được duyệt.
- Mốc bắt đầu ban đầu, thời hạn cũ, thời hạn đề nghị và thời hạn thực tế được xác nhận.
- Số lần gia hạn và thời lượng tích lũy trước, sau thay đổi.
- Mốc gửi, phê duyệt, áp dụng, đọc lại và kết thúc hoặc thu hồi.
- Kết quả các điều kiện quan trọng, phiên bản chính sách và lý do từ chối.
- Định danh thao tác ở hệ thống đích và tham chiếu tới log phiên hoặc sự kiện thực thi.

Giữ riêng thời hạn đề nghị và thời hạn đã xác nhận. Nếu hệ thống đích áp dụng một mốc khác với mốc được phép, cần ghi nhận sai lệch và xử lý theo hợp đồng tích hợp; không tự đổi bản ghi phê duyệt để làm hai giá trị trông khớp nhau.

Không đưa mật khẩu, token hoặc nội dung bí mật vào log. Bằng chứng phải được bảo vệ khỏi sửa hoặc xóa bởi chính vai trò đang được theo dõi, với quyền xem phù hợp vì lý do và dữ liệu chẩn đoán có thể chứa thông tin nhạy cảm.

Một chuỗi sự kiện chỉ ghi “người duyệt đã đồng ý” chưa chứng minh quyền đã được gia hạn đúng, và cũng chưa chứng minh quyền đã bị thu hồi đúng hạn. Cần đối chiếu với thành phần thực thi và trạng thái tài nguyên.

## 10. Các tình huống cần kiểm chứng

Bảng dưới đây gợi ý những trường hợp cần kiểm thử khi triển khai hoặc thay đổi cơ chế gia hạn. Đây là tiêu chí thiết kế; kết quả thực tế phải được xác minh trên môi trường và nền tảng sử dụng.

| Tình huống | Hành vi mong muốn |
| --- | --- |
| Gia hạn hợp lệ trước hạn, phạm vi không đổi | Chỉ cập nhật tới mốc đã duyệt; có xác minh tại đích |
| Người dùng yêu cầu sớm hơn cửa sổ được phép | Từ chối theo chính sách; không mở rộng TTL |
| Mốc mới vượt trần tích lũy hoặc số lần cho phép | Không áp dụng qua luồng gia hạn thông thường |
| Người yêu cầu đồng thời là người duyệt khi không được phép tự duyệt | Phê duyệt không hợp lệ |
| Nội dung yêu cầu đổi sau phê duyệt | Không sử dụng lại quyết định cũ cho nội dung mới |
| Quyền hết hạn trong lúc chờ | Yêu cầu cũ kết thúc; không hồi tố thời hạn |
| Hai yêu cầu cập nhật cùng phiên bản | Phát hiện xung đột, không cộng dồn ngoài quyết định |
| Gửi lại cùng yêu cầu do mất phản hồi | Không tăng thời hạn hoặc bộ đếm thêm lần nữa |
| Cùng mã idempotency nhưng khác nội dung | Bị từ chối do không khớp yêu cầu |
| Thu hồi quyền diễn ra đồng thời với gia hạn | Kết quả gia hạn đến muộn không phục hồi quyền đã thu hồi |
| Đích đã cập nhật nhưng phản hồi bị mất | Đối soát kết quả, không lặp thao tác cộng thời lượng tùy ý |
| PAM hoặc dịch vụ phê duyệt không sẵn sàng | Không ngầm gia hạn; cơ chế hết hạn cũ tiếp tục được cưỡng chế theo thiết kế |
| Gỡ nhóm hoặc hết TTL nhưng phiên, token vẫn còn | Phát hiện và xử lý khả năng truy cập còn tồn tại |
| Workload tự yêu cầu gia hạn liên tục | Vẫn bị ràng buộc bởi danh tính, nhiệm vụ và giới hạn tổng |

Khi kiểm chứng, cần xem cả giao diện người dùng, bản ghi PAM và khả năng thao tác thực tế ở đích. Một giao diện hiển thị “Expired” không đủ nếu phiên quản trị vẫn thực hiện được hành động sau hạn.

## 11. Giám sát để tránh biến JIT thành quyền thường trực

Các chỉ số hữu ích gồm tỷ lệ lần cấp quyền cần gia hạn, số lần liên tiếp theo người và tài sản, thời gian chờ phê duyệt, lượng yêu cầu chạm giới hạn, thời gian từ hết hạn đến thu hồi thực tế và số trường hợp trạng thái PAM không khớp đích.

Tần suất gia hạn cao cần được xem cùng nguyên nhân. Thời lượng ban đầu có thể quá ngắn, quy trình vận hành có bước chờ không cần thiết, vai trò có thể chưa phù hợp hoặc có người đang cố giữ quyền lâu hơn nhiệm vụ yêu cầu. Không tự động tăng mọi TTL chỉ để giảm số yêu cầu.

Với tác vụ của tài khoản dịch vụ, cần phân biệt một công việc có thời lượng hữu hạn với một dịch vụ vốn phải hoạt động liên tục. Gia hạn vô hạn một quyền JIT để nuôi dịch vụ chạy thường xuyên che giấu nhu cầu thiết kế danh tính workload, quyền tối thiểu và vòng đời credential phù hợp.

Khi cần ngoại lệ khẩn cấp, dùng workflow đã quy định với người chịu trách nhiệm, phạm vi và thời hạn cụ thể, giám sát và rà soát sau sử dụng. Không dùng lỗi phê duyệt, mất kết nối hoặc công việc chưa xong làm cơ chế gia hạn mặc định.

Gia hạn JIT được kiểm soát khi thời gian bổ sung có lý do kiểm chứng được, quyết định đúng thẩm quyền, giới hạn tích lũy rõ ràng và thời hạn được cưỡng chế tại nơi quyền thực sự được sử dụng. Phạm vi JEA, bảo vệ credential, giám sát phiên và bằng chứng thu hồi phải tiếp tục được duy trì trong toàn bộ thời gian đó.
