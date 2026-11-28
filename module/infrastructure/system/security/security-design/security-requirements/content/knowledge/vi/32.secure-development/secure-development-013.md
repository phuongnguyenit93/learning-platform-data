# Defect severity và SLA — Đặc tả mức độ lỗi và cam kết xử lý bảo mật

## 1. Vấn đề cần giải quyết

Một lỗi bảo mật chỉ có thể được quản lý nhất quán khi tổ chức biết nó nghiêm trọng đến đâu, ai chịu trách nhiệm, phải đạt mốc nào trước thời điểm nào và bằng chứng nào được dùng để kết luận đã hoàn tất.

Các câu như “lỗi Critical xử lý ngay” hoặc “lỗi High sửa trong hai tuần” còn thiếu nhiều quyết định: thời gian bắt đầu từ đâu, dùng giờ lịch hay giờ làm việc, “sửa” là merge code hay đã triển khai, đổi owner có đặt lại hạn không, và giảm severity có xóa việc đã quá hạn không?

Trong chương **Secure development**, thuộc module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, bài học chuyển mục tiêu kiểm soát rủi ro thành yêu cầu có thể đo và kiểm chứng. Phân loại lỗi, phản hồi, giảm thiểu, sửa, xác minh, audit và phục hồi phải liên kết với nhau trong vòng đời phát triển.

Sau bài học, người học cần có khả năng:

- Tách severity, priority, rủi ro, độ chắc chắn và trạng thái xử lý.
- Định nghĩa các mốc SLA, nguồn thời gian, lịch tính và điều kiện hoàn tất.
- Quản lý đổi severity, duplicate, chuyển đội, ngoại lệ và tạm dừng có kiểm soát.
- Nghiệm thu việc sửa trong đúng artifact, cấu hình và phạm vi triển khai.
- Thiết kế audit, metric, cảnh báo và kiểm thử logic deadline.

Các mức, ngân sách thời gian và ngưỡng trong bài là chính sách minh họa, không phải cam kết mặc định hay yêu cầu chung cho mọi tổ chức. Khi dùng cho một sản phẩm, phải được chủ rủi ro và các đội liên quan chốt theo phạm vi cụ thể.

## 2. Phân biệt severity, priority, risk và SLA

| Khái niệm | Câu hỏi chính | Điều không nên suy ra |
| --- | --- | --- |
| Severity | Nếu lỗi bị khai thác trong bối cảnh đã xác định, tác động và điều kiện nghiêm trọng thế nào? | Mọi lỗi cùng severity đều phải làm theo cùng thứ tự công việc |
| Priority | Hiện tại việc nào cần được xử lý trước, với mức khẩn cấp nào? | Một việc ít được ưu tiên hơn tự động có severity thấp hơn |
| Risk | Khả năng/hậu quả trong môi trường và thời gian cụ thể, có xét kiểm soát và phơi lộ | Một điểm severity của công cụ là toàn bộ quyết định rủi ro |
| Confidence | Bằng chứng đủ chắc chắn tới đâu? | Chưa xác minh xong nghĩa là không có tác động |
| Status | Công việc đang ở bước nào: mới nhận, triage, giảm thiểu, sửa, xác minh, chấp nhận rủi ro... | Đổi trạng thái bằng tay chứng minh milestone kỹ thuật đã đạt |
| SLA xử lý lỗi | Cam kết về mốc, thời hạn, phạm vi, điều kiện đạt và trách nhiệm | Một ngày hết hạn duy nhất mô tả đủ mọi pha xử lý |

Ở đây, SLA được dùng như cam kết xử lý đã được tổ chức xác định, có thể áp dụng nội bộ hoặc là một phần của thỏa thuận cụ thể. Một mục tiêu nội bộ và một cam kết đối ngoại có thể khác phạm vi và thẩm quyền; hệ thống cần ghi rõ đang áp dụng loại chính sách nào, không tự suy ra nghĩa vụ từ nhãn ticket.

Ví dụ, lỗi có severity Medium nhưng đang bị lạm dụng trong một luồng phơi lộ có thể cần priority cao và kích hoạt xử lý incident. Ngược lại, lỗi High ở một phạm vi chưa triển khai vẫn cần quản lý deadline và điều kiện release; việc chưa có lưu lượng không tự làm tác động tiềm năng trở thành Low.

Khi có dấu hiệu tấn công/sự cố đang diễn ra, quy trình containment và incident response chạy theo điều kiện riêng. SLA sửa vĩnh viễn 72 giờ trong ví dụ không cho phép chờ đủ 72 giờ mới ngăn tác hại đang xảy ra.

## 3. Xây dựng rubric severity có căn cứ

### 3.1. Các chiều cần đánh giá

Một đánh giá nên có ít nhất:

- Tác động tới tính bí mật, toàn vẹn, sẵn sàng và bất biến nghiệp vụ.
- Phạm vi tài nguyên, tenant, người dùng, môi trường và dữ liệu bị ảnh hưởng.
- Điều kiện tiếp cận: mạng, xác thực, quyền hiện có, thao tác người dùng hoặc cấu hình cần thiết.
- Khả năng đạt tới đường lỗi, độ phức tạp và giả định khai thác có bằng chứng.
- Kiểm soát đang thực sự có hiệu lực và giới hạn của chúng.
- Bằng chứng, phần chưa rõ, độ chắc chắn và owner xác minh.

Không chỉ chọn tác động cao nhất có thể tưởng tượng mà không giải thích đường đi và giả định. Cũng không giảm severity chỉ vì chưa có PoC hoàn chỉnh trong khi đã có bằng chứng đáng tin về một đường truy cập trái quyền.

Điểm số hoặc nhãn từ công cụ là một đầu vào. Nếu áp dụng một phương pháp chấm điểm, phải ghi phương pháp/phiên bản, các yếu tố đã chọn và cách ánh xạ sang severity của tổ chức. Không tự coi mọi scanner, mọi loại lỗi và mọi môi trường dùng cùng thang đo.

### 3.2. Rubric minh họa

| Mức | Mô tả định hướng trong policy ví dụ | Bằng chứng cần làm rõ |
| --- | --- | --- |
| Critical | Có đường khai thác đáng tin với tác động rất lớn tới quyền quản trị, dữ liệu/phạm vi rộng hoặc bất biến cốt lõi | Điều kiện truy cập, quyền thực tế đạt được, phạm vi, kiểm soát và mức phơi lộ |
| High | Có tác động đáng kể tới dữ liệu/quyền/chức năng quan trọng trong điều kiện đã xác định | Giới hạn tenant/object, quyền đầu vào, dữ liệu/tác dụng và điều kiện cần |
| Medium | Tác động hoặc khả năng khai thác bị giới hạn nhưng vẫn vi phạm yêu cầu bảo mật có ý nghĩa | Giới hạn được chứng minh, residual risk và cách kiểm soát có hiệu lực |
| Low | Tác động trực tiếp thấp trong bối cảnh đã đánh giá, thường cần xử lý tăng cường phòng vệ hoặc sai lệch hạn chế | Vì sao tác động thấp, giả định nào cần giữ và trigger đánh giá lại |
| Chưa xác định | Thiếu dữ liệu để chốt severity | Severity tạm thời theo nguyên tắc được duyệt, owner và hạn triage; không mặc định Low |

Đây là rubric để bắt đầu đặc tả, không phải bảng ánh xạ cứng từ tên lỗi. “Lỗi phân quyền” có thể có phạm vi rất khác nhau; “thiếu header” không tự xác định severity nếu chưa xét tác dụng và bối cảnh.

### 3.3. Severity tạm thời và quyền thay đổi

Khi chưa đủ thông tin, cần severity tạm thời cùng phần giả định. Policy phải nêu cách chọn mức bảo thủ phù hợp và thời hạn triage; không giữ trạng thái “chưa xác định” vô hạn để không có deadline.

Một finding được hạ severity phải có căn cứ và quyền phê duyệt tương ứng. Không giảm mức chỉ vì sắp quá hạn, chưa có nhân sự hoặc nhà cung cấp chưa có bản vá. Các lý do đó ảnh hưởng kế hoạch xử lý/ngoại lệ, không tự làm tác động kỹ thuật nhỏ đi.

Cần giữ lịch sử severity cũ/mới, actor, thời điểm, căn cứ và tác động tới deadline. Khi sai phân loại ban đầu được sửa, không ghi đè lịch sử như thể mức cũ chưa từng tồn tại.

## 4. Mô hình đe dọa đối với quy trình xử lý lỗi

### 4.1. Tài sản và giả định

Tài sản là độ tin cậy của quyết định rủi ro, khả năng xử lý đúng hạn, bằng chứng khắc phục và dữ liệu nhạy cảm trong hồ sơ lỗi. Sai quy trình có thể làm lỗi nghiêm trọng tồn tại lâu hoặc tạo báo cáo tuân thủ không phản ánh thực tế.

Giả định có thể có sai sót nhập liệu, chậm luân chuyển, công cụ đồng bộ trễ hoặc người có quyền hạn chế tìm cách làm dashboard đẹp hơn. Không cần một kẻ tấn công chiếm hệ thống để xảy ra việc reset deadline, đóng lỗi thiếu bằng chứng hoặc làm mất owner.

| Risk ID | Kịch bản | Hậu quả | Hướng yêu cầu |
| --- | --- | --- | --- |
| SLR-01 | Chờ xác minh/PoC rồi mới tạo mốc bắt đầu | Che thời gian lỗi đã được biết | Anchor có nguồn tin cậy, ghi cả intake và sự kiện phát hiện liên quan |
| SLR-02 | Severity chưa rõ bị mặc định Low hoặc pending vô hạn | Trì hoãn xử lý lỗi có thể nghiêm trọng | Mức tạm thời, hạn triage và escalation |
| SLR-03 | Chuyển đội, rescan, merge duplicate hoặc import ticket đặt lại đồng hồ | Gia hạn mà không có quyết định rủi ro | Giữ anchor/lịch sử/phạm vi và quy tắc gộp |
| SLR-04 | Hạ severity khi sắp quá hạn | Làm mất vi phạm hoặc giảm áp lực khắc phục trái căn cứ | Phê duyệt, audit và deadline không tự nới |
| SLR-05 | Dùng giờ làm việc khi policy yêu cầu giờ lịch | Tính hạn sai, nhất là cuối tuần hoặc đổi múi giờ | Lịch/đơn vị/timezone có phiên bản và kiểm thử biên |
| SLR-06 | Đổi status fixed khi mới merge code | Lỗi vẫn tồn tại trong artifact/deployment | Milestone có bằng chứng và phạm vi closure |
| SLR-07 | Có mitigation hoặc accepted risk rồi coi đã sửa vĩnh viễn | Che residual risk và nghĩa vụ còn lại | Tách containment, fix, verification và exception |
| SLR-08 | Pause không thời hạn hoặc cộng trùng khoảng pause | Deadline bị kéo dài không kiểm soát | Quyền pause, khoảng thời gian, clock áp dụng và hợp khoảng không trùng |
| SLR-09 | Reopen/regression tạo ticket mới không liên kết | Mất lịch sử và tuổi rủi ro | Quy tắc mở lại và exposure mới có bằng chứng |
| SLR-10 | Cảnh báo trễ, không có owner hoặc đồng bộ lỗi | Quá hạn không ai xử lý | Routing, thời hạn cảnh báo, retry và escalation |
| SLR-11 | Restore làm mất policy revision hoặc lịch sử breach | Đánh giá sai nghĩa vụ và báo cáo | Bảo toàn sự kiện, version policy và tính lại có kiểm soát |
| SLR-12 | Log/ticket lộ credential, PoC hoặc dữ liệu khách hàng | Mở rộng rủi ro từ chính hệ thống quản lý lỗi | Phân quyền và tối thiểu hóa bằng chứng |

### 4.2. Các bất biến

1. Mọi deadline áp dụng phải có anchor, policy revision, phạm vi và milestone đạt có thể giải thích.
2. Chuyển trạng thái, đổi owner hoặc tái tạo finding không tự làm thời gian đã trôi qua biến mất.
3. Không chốt severity hoặc closure chỉ để giảm số lỗi/quá hạn mà thiếu căn cứ.
4. Mitigation, chấp nhận rủi ro và fixed được phân biệt trong cả workflow lẫn metric.
5. Quyết định thay đổi hạn có quyền và audit; lịch sử vi phạm không bị xóa âm thầm.

## 5. Định nghĩa các mốc SLA

### 5.1. Tách các milestone

| Mốc | Điều kiện đạt minh họa | Chưa đủ để coi là đạt |
| --- | --- | --- |
| Acknowledged | Hệ thống/đội chịu trách nhiệm xác nhận tiếp nhận và có owner/định tuyến đúng theo hợp đồng | Email tự động không có nơi chịu trách nhiệm nếu policy yêu cầu owner thực |
| Triaged | Xác định phạm vi ban đầu, severity/căn cứ, phần chưa rõ, owner và kế hoạch bước tiếp theo | Chỉ đổi nhãn sang In Progress |
| Contained/mitigated | Biện pháp giảm tác hại đã áp dụng và kiểm chứng trong phạm vi đã cam kết | Có kế hoạch hoặc cấu hình chưa được deploy |
| Fix available | Có bản sửa có thể đưa vào kiểm chứng | Commit/PR chưa chứng minh artifact hoặc hành vi đã đúng |
| Fix verified | Bản sửa đáp ứng tiêu chí bảo mật/nghiệp vụ qua kiểm tra được yêu cầu trên đúng đối tượng | Test chạy với bản khác hoặc chỉ có lời xác nhận của người sửa |
| Deployed/remediated | Phạm vi triển khai/nhánh hỗ trợ đã xử lý theo hợp đồng, có bằng chứng | Artifact mới đã build nhưng production còn bản cũ |
| Closed | Lý do closure và các milestone/phạm vi tương ứng đủ bằng chứng, được người có quyền xác nhận | Đánh dấu Done mà không nêu fixed, not affected, duplicate hay accepted risk |

Không phải mọi defect đều có cùng milestone containment, nhưng policy phải nói khi nào áp dụng và điều kiện nào cho phép ghi không áp dụng. Không dùng `N/A` để né một nghĩa vụ vốn đang cần thực hiện.

### 5.2. Anchor và nguồn thời gian

Ghi riêng thời điểm nhận báo cáo, thời điểm phát hiện đáng tin, thời điểm tạo ticket, triage và các milestone. Trong ví dụ, `T0` là thời điểm sớm nhất có bằng chứng tin cậy rằng ứng viên lỗi trong phạm vi đã được hệ thống tiếp nhận/quan sát; không đợi đến khi khai thác được hoàn chỉnh hoặc được gán đúng đội mới bắt đầu.

Với nguồn bên ngoài, timestamp họ tự khai không mặc nhiên là thời gian nhận của tổ chức. Với scanner nội bộ, có thể dùng sự kiện quan sát được xác thực nếu hợp đồng quy định. Tạo ticket trễ phải giữ được mốc tin cậy trước đó khi có bằng chứng.

Báo cáo chưa đủ dữ liệu cần được ghi phần thiếu, owner yêu cầu bổ sung và trạng thái tạm thời. Trong thời gian triage, không mặc định đặt đồng hồ về thời điểm bổ sung cuối cùng. Spam hoặc bản ghi không thuộc quy trình cần được phân loại bằng lý do riêng, không trộn với defect đang chờ xác minh.

Dùng thời gian lịch chuẩn để lưu thời điểm liên hệ thống và hiển thị theo timezone có offset. Đo độ trễ nội bộ nên dùng nguồn thời lượng phù hợp; không cho người xử lý sửa timestamp hoàn tất bằng một field tự nhập để backdate việc đạt SLA.

### 5.3. Giờ lịch và giờ làm việc

Ví dụ trong bài dùng giờ lịch: 1 ngày = 24 giờ, không tự bỏ cuối tuần hoặc ngày nghỉ. Deadline lưu dưới dạng thời điểm tuyệt đối; timezone giao diện không thay đổi thời điểm đó.

Nếu một tổ chức dùng lịch làm việc, phải chốt timezone, giờ mở/đóng, ngày nghỉ, phiên bản lịch, quy tắc ngoài giờ và cách xử lý thay đổi lịch. “Ba ngày làm việc” không thể được thực hiện bằng phép cộng 72 giờ mà vẫn tuyên bố đúng hợp đồng.

Không làm tròn timestamp để che biên. Ví dụ quy tắc nghiệm thu có thể là: hoàn tất có bằng chứng tại `completed_at <= due_at` thì đúng hạn; nếu chưa hoàn tất và `now > due_at` thì quá hạn. Điều kiện bằng đúng deadline phải nhất quán trong code, API, dashboard và báo cáo.

## 6. Chính sách thời hạn minh họa

Tất cả các ngân sách trong bảng tính từ `T0` cho cùng phạm vi, theo giờ lịch. Chúng không cộng nối tiếp nhau; triage mất một giờ không tự cộng thêm một giờ vào deadline fix.

| Severity | Acknowledge | Triage | Containment/mitigation khi áp dụng | Remediation đã kiểm chứng trong phạm vi cam kết |
| --- | --- | --- | --- | --- |
| Critical | 15 phút | 1 giờ | 4 giờ | 72 giờ |
| High | 4 giờ | 24 giờ | 3 ngày | 14 ngày |
| Medium | 24 giờ | 5 ngày | 10 ngày | 30 ngày |
| Low | 5 ngày | 10 ngày | Theo kế hoạch được phê duyệt nếu cần | 90 ngày |

Đối với lỗi có tác hại đang diễn ra, quy trình incident có thể yêu cầu hành động sớm hơn các mốc trên. Priority hoặc incident clock bổ sung không được dùng để làm chậm clock khắc phục đã có.

Policy phải nêu “remediation đã kiểm chứng” bao gồm những môi trường/nhánh hỗ trợ nào, ai xác minh và bằng chứng gì. Một nhóm có thể dùng deadline khác nhau cho artifact đã sửa và deployment đã xử lý; nếu vậy phải đặt tên và lưu hai milestone riêng.

Ví dụ `T0 = 2026-11-27T08:00:00Z`, lỗi Critical có deadline remediation là `2026-11-30T08:00:00Z`. Hiển thị tại UTC+07:00 là 15:00 cùng các ngày tương ứng; đó vẫn là cùng hai thời điểm tuyệt đối, không phải thêm bảy giờ vào ngân sách.

## 7. Bộ yêu cầu kiểm chứng được

Các yêu cầu dưới đây sử dụng policy minh họa ở mục 6. Mỗi sản phẩm phải xác nhận owner, phạm vi, phiên bản lịch và bằng chứng trước khi áp dụng.

| ID | Yêu cầu | Owner | Bằng chứng đạt |
| --- | --- | --- | --- |
| DSLA-01 | Mỗi loại defect phải có phạm vi, owner, các milestone áp dụng, ngân sách và điều kiện đạt/closure được phê duyệt. | Chủ sản phẩm/bảo mật | Hồ sơ đủ trường; thiếu policy/owner bị phát hiện và định tuyến, không thành không có deadline |
| DSLA-02 | Severity phải dựa trên rubric có phiên bản, ghi tác động, điều kiện, phạm vi, kiểm soát, căn cứ và confidence. | Triage/bảo mật | Hai case cùng rubric có lý do phân loại giải thích được; không chỉ sao nhãn scanner |
| DSLA-03 | Severity chưa chốt phải có mức tạm thời, owner và hạn triage; không mặc định Low hoặc pending vô hạn. | Triage | Case thiếu PoC nhưng có tín hiệu đáng tin được xử lý theo mức tạm thời và clock tương ứng |
| DSLA-04 | Priority và quy trình incident phải tách khỏi severity/SLA; tác hại đang diễn ra có trigger containment riêng. | Ứng phó/chủ sản phẩm | Case active abuse được đưa vào luồng ứng phó mà không đợi deadline fix dài hơn |
| DSLA-05 | T0 phải có nguồn/thời điểm tin cậy, giữ liên kết intake/quan sát/ticket; không tự dời khi triage, import hay bổ sung thông tin. | Nền tảng quản lý lỗi | Tạo ticket muộn hoặc đồng bộ trễ không làm mất anchor có bằng chứng; sửa anchor có quyền và audit |
| DSLA-06 | Policy phải nêu đơn vị giờ lịch/làm việc, timezone, lịch có phiên bản, precision và quy tắc biên. | Nền tảng/owner policy | Test timezone, cuối tuần/lịch và completed_at đúng/ngay ngoài deadline theo hợp đồng |
| DSLA-07 | Milestone chỉ đạt bằng chứng được quy định cho đúng đối tượng/phạm vi; status do người dùng đổi không tự tạo proof hoàn tất. | QA/chủ sản phẩm | Đổi Done, merge PR hoặc nhập ngày hoàn tất không làm clock đạt nếu thiếu artifact/test/deployment proof |
| DSLA-08 | Nâng severity không reset T0; với clock còn mở trong ví dụ, deadline mới là min(hạn đang có, T0 + ngân sách mức mới). Hạ mức không tự nới hạn/xóa lịch sử. | Triage/chủ rủi ro | Test nâng/hạ mức, hạn mới đã qua và quyền sửa; giữ revision cũ/mới cùng lý do |
| DSLA-09 | Chuyển đội, duplicate, merge/split và rescan phải giữ anchor, lịch sử và nghĩa vụ theo từng phạm vi bị ảnh hưởng. | Chủ sản phẩm/nền tảng | Duplicate có T0 sớm hơn không bị gộp mất; đổi assignee không đặt lại due |
| DSLA-10 | Mitigation đã xác minh chỉ hoàn tất clock tương ứng; không tự dừng deadline fix/remediation hoặc đổi thành fixed. | Ứng dụng/bảo mật | Tắt tính năng đã kiểm chứng có thể đạt containment, nhưng clock sửa vĩnh viễn còn mở theo policy |
| DSLA-11 | Exception/accepted risk phải có thẩm quyền, phạm vi, căn cứ, residual risk, biện pháp bù, thời hạn và trigger xem lại; không được báo như fixed đúng hạn. | Chủ rủi ro | Exception sai phạm vi/hết hạn không tự có hiệu lực; metric phân biệt chấp nhận rủi ro với đã khắc phục |
| DSLA-12 | Pause chỉ theo điều kiện được duyệt, ghi clock áp dụng, bắt đầu/kết thúc, actor và lý do; hợp các khoảng trùng, không cộng hai lần hoặc xóa breach quá khứ. | Owner policy/nền tảng | Pending vendor không tự pause; khoảng overlap và pause mở vô hạn bị xử lý đúng hợp đồng |
| DSLA-13 | Closure fixed phải liên kết bản sửa, kiểm thử bảo mật/nghiệp vụ và artifact/deployment/nhánh hỗ trợ theo phạm vi. | QA/release | Source đã sửa nhưng production còn bản lỗi không được báo hoàn tất toàn bộ |
| DSLA-14 | Reopen phải phân biệt chưa sửa thật với regression/exposure mới đã có bằng chứng; giữ liên kết và lịch sử thay vì tạo ticket mới để xóa tuổi lỗi. | Chủ sản phẩm/QA | Mở lại sau closure sai giữ nghĩa vụ cũ; regression có episode mới theo policy và vẫn truy vết được lịch sử |
| DSLA-15 | Có cảnh báo trước hạn và escalation khi quá hạn; ví dụ kiểm tra clock mỗi 5 phút, phát cảnh báo quá hạn trong 10 phút từ khi đủ điều kiện phát hiện theo nguồn thời gian. | Vận hành/nền tảng | Tiêm deadline qua hạn, mất owner hoặc delivery lỗi; cảnh báo/routing/escalation có bằng chứng đúng hạn |
| DSLA-16 | Audit và metric phải giữ policy/clock/severity revision, bằng chứng milestone, exception/pause và lịch sử breach; không lộ secret/PoC/dữ liệu dư thừa. | Nền tảng/bảo mật | Tái dựng được quyết định; sửa severity hoặc đóng ticket không làm mất sự kiện đã quá hạn |
| DSLA-17 | API/workflow phải kiểm soát ai được đổi severity, anchor, milestone, pause, exception và closure; lỗi tracker/policy service không tự dừng đồng hồ. | IAM/nền tảng | Tài khoản quyền thấp và lỗi đồng bộ không tạo được closure/extension trái quyền hoặc trạng thái không có nghĩa vụ |
| DSLA-18 | Restore/import và thay policy phải bảo toàn sự kiện cùng revision, tính lại có kiểm soát và kiểm thử biên; không tự lấy ngày import làm T0 mới. | Nền tảng/vận hành | Restore cho deadline/lịch sử phù hợp; rebaseline hợp lệ được ghi riêng, không ghi đè nghĩa vụ cũ |

### 7.1. Mẫu đặc tả chi tiết cho deadline remediation

```text
ID: DSLA-08 / clock remediation
Mục tiêu: thay severity không làm reset tuổi rủi ro trong cùng phạm vi
Anchor: T0 từ sự kiện đáng tin theo DSLA-05
Đơn vị: thời gian lịch, lưu deadline như một Instant
Ngân sách: theo severity và policy revision được áp dụng
Khi nâng severity và clock còn mở:
  candidate_due = T0 + budget(new_severity)
  effective_due = min(existing_due, candidate_due)
Nếu effective_due đã qua và milestone chưa đạt:
  - Ghi trạng thái overdue, định tuyến/escalate theo policy
  - Không cấp lại một ngân sách mới từ thời điểm đổi severity
Khi hạ severity:
  - Cần căn cứ/quyền theo policy
  - Không tự nới existing_due hoặc xóa breach history
Owner: triage, chủ rủi ro và nền tảng quản lý lỗi
Bằng chứng: T0, severity revisions, ngân sách, due trước/sau và milestone proof
```

Policy phải nêu cách xử lý milestone đã hoàn tất khi sửa phân loại ban đầu. Không âm thầm viết lại timestamp hoặc kết quả lịch sử; nếu cần điều chỉnh cách đo do sai dữ liệu, lưu quyết định sửa có căn cứ và các góc nhìn trước/sau.

## 8. Clock, chuyển trạng thái và ngoại lệ

### 8.1. Một ticket có thể có nhiều clock

```text
Intake / quan sát đáng tin → T0
           |
           +→ acknowledge clock
           +→ triage clock
           +→ containment clock nếu áp dụng
           +→ remediation/verification/deployment clocks theo phạm vi
```

Clock không nhất thiết chạy nối tiếp. Hoàn tất triage không đặt T0 mới cho remediation nếu policy nói mọi ngân sách tính từ T0. Một milestone có thể đạt trong khi clock khác quá hạn.

Workflow có thể gồm New, Triaging, Assigned, Mitigating, Fixing, Verifying, Deployed và Closed. Accepted Risk, Not Affected và Duplicate là những disposition khác cần có căn cứ, không phải các cách viết khác của Fixed.

### 8.2. Pause: mặc định không tự dừng

Policy ví dụ mặc định không có pause tự động. Thiếu nhân sự, chờ vendor, chờ cửa sổ triển khai hoặc tracker mất kết nối không tự dừng thời gian. Nếu được phép pause đặc biệt, phải nêu clock nào, thẩm quyền nào, điều kiện bắt đầu/kết thúc, thời lượng tối đa và cách theo dõi rủi ro trong lúc chờ.

Đối với clock có pause hợp lệ, có thể mô tả thời gian thực thi nghĩa vụ:

```text
active_elapsed(t)
  = elapsed(T0, t)
    - duration(union(valid_pause_intervals) intersect [T0, t])

due = thời điểm sớm nhất active_elapsed(t) đạt ngân sách của clock
```

Chỉ các khoảng đã hợp lệ theo policy mới được đưa vào phép tính. Khoảng pause kết thúc mở cần có giới hạn và điều kiện tự đánh giá lại; không coi một cờ Paused là giấy phép trì hoãn vô hạn.

Ví dụ clock có ngân sách 4 giờ từ 08:00 cùng ngày, theo giờ lịch. Hai khoảng pause được phép là 09:00–10:00 và 09:30–10:30. Hợp của chúng dài 1 giờ 30 phút, nên deadline là 13:30; không cộng trùng thành 14:00.

Phê duyệt sau khi đã quá hạn không xóa sự kiện breach đã xảy ra. Nếu có điều chỉnh lịch/anchor vì dữ liệu đo ban đầu sai, đó là một correction có căn cứ và audit, khác với việc phê duyệt rủi ro sau deadline.

### 8.3. Mitigation và accepted risk

Mitigation phải có tiêu chí kiểm chứng: đã deploy ở phạm vi nào, chặn đường tác động nào, còn residual risk gì, theo dõi ra sao và điều gì làm nó mất hiệu lực. Có một WAF rule trên giấy hoặc tắt feature ở test chưa chứng minh production đã được giảm thiểu.

Accepted risk cần phạm vi và thời hạn cùng chủ rủi ro có thẩm quyền. Nếu deadline được điều chỉnh bằng quy trình được phép, lưu cả deadline gốc và deadline/điều kiện mới; báo cáo phải phân biệt approved exception với remediation đúng hạn.

Không dùng cùng một phép đếm để gọi “đã sửa đúng hạn” cho cả fixed, false positive, duplicate và accepted risk. Mỗi disposition trả lời một câu hỏi khác nhau và có bằng chứng khác nhau.

### 8.4. Duplicate, split và reopen

Khi gộp duplicate, giữ các quan sát ban đầu và chọn anchor phù hợp cho mỗi phạm vi theo policy. Ticket được tạo sau không được làm mất mốc sớm hơn đã có bằng chứng. Khi split thành nhiều đội/đối tượng, lưu liên kết và clock tương ứng; không tự cấp thời gian mới cho toàn bộ scope cũ.

Nếu lỗi được đóng nhầm hoặc fix chưa có hiệu lực thật, reopen giữ nghĩa vụ/lịch sử cũ. Nếu đã xác minh khắc phục xong rồi một thay đổi khác gây regression mới, có thể tạo episode/exposure mới với anchor có bằng chứng, nhưng phải liên kết lỗi cũ và giữ lịch sử. Chỉ đổi số ticket không đủ để khẳng định đây là một lỗi mới.

Với phạm vi mới được phát hiện sau, cần ghi thời điểm/căn cứ riêng và kiểm tra có bằng chứng sớm hơn hay không. Không gộp mù mọi sản phẩm vào cùng ngày bắt đầu trước khi chúng tồn tại, cũng không dùng phát hiện muộn để xóa nghĩa vụ đã biết của phạm vi cũ.

## 9. Triển khai tính deadline và audit

### 9.1. Dữ liệu nên được quản lý như sự kiện có nguồn

Tối thiểu cần defect ID, scope/episode, T0 cùng evidence/source, severity/priority/confidence revisions, owner history, policy/calendar revision, từng clock/budget/due, pause/exception decisions, milestone proof và trạng thái triển khai.

Sự kiện quan trọng cần actor hoặc danh tính tiến trình, occurred_at có căn cứ, received_at, lý do và version trước/sau. Không tin một timestamp do client tự nhập để ghi milestone đúng hạn. Nếu bằng chứng hệ thống đáng tin đến trễ, quy trình correction phải xác minh timestamp thực, giữ lịch sử tiếp nhận và đánh dấu kết quả đo đã được điều chỉnh.

Một event cảnh báo đã được gửi và kết luận thực sự vi phạm SLA là hai dữ kiện có thể cần phân biệt khi sửa lỗi đo. Lưu dấu vết correction thay vì xóa log gốc; đồng thời không tiếp tục báo một vi phạm sai đã được chứng minh chỉ vì trước đó có cảnh báo.

### 9.2. Ví dụ Java cho clock giờ lịch không pause

Đoạn mã JDK 17 minh họa deadline tuyệt đối, điều kiện biên và việc siết hạn khi nâng severity. Các thời điểm đầu vào phải do lớp nghiệp vụ xác minh; đoạn mã không tự xác thực bằng chứng hoặc quyền sửa dữ liệu.

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class DefectSlaClock {
    public enum State { OPEN, MET_ON_TIME, MET_LATE, OVERDUE }

    public static Instant dueAt(Instant anchor, Duration budget) {
        Objects.requireNonNull(anchor);
        Objects.requireNonNull(budget);
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }
        return anchor.plus(budget);
    }

    public static State evaluate(
            Instant anchor, Duration budget, Instant now,
            Instant verifiedCompletedAt) {
        Objects.requireNonNull(now);
        Instant due = dueAt(anchor, budget);
        if (now.isBefore(anchor)) {
            throw new IllegalArgumentException("Current time precedes anchor");
        }
        if (verifiedCompletedAt != null) {
            if (verifiedCompletedAt.isBefore(anchor)
                    || verifiedCompletedAt.isAfter(now)) {
                throw new IllegalArgumentException("Invalid completion time");
            }
            return verifiedCompletedAt.isAfter(due)
                    ? State.MET_LATE : State.MET_ON_TIME;
        }
        return now.isAfter(due) ? State.OVERDUE : State.OPEN;
    }

    public static Instant tightenedDue(
            Instant existingDue, Instant anchor, Duration newBudget) {
        Objects.requireNonNull(existingDue);
        Instant candidate = dueAt(anchor, newBudget);
        return candidate.isBefore(existingDue) ? candidate : existingDue;
    }
}
```

`Duration.ofHours(72)` là 72 giờ lịch; không đại diện cho ba ngày làm việc. Khi `verifiedCompletedAt` bằng due, kết quả là MET_ON_TIME. Khi chưa hoàn tất và now bằng due, ví dụ vẫn trả OPEN tại đúng thời điểm biên; ngay sau due mới OVERDUE theo quy tắc đã công bố.

Code không hỗ trợ pause, lịch làm việc, nhiều scope/episode, quyền điều chỉnh hoặc lưu lịch sử breach. Không áp trực tiếp nó cho policy khác rồi coi kết quả là đúng. `tightenedDue` cũng không cấp quyền đổi severity hoặc áp dụng lại cho mọi milestone đã hoàn tất.

Bằng chứng thời gian không hợp lệ hoặc phép tính vượt miền hỗ trợ phải được phân loại lỗi dữ liệu/cấu hình để xử lý, không catch rồi trả MET_ON_TIME. Khi completion muộn làm state chuyển từ OVERDUE sang MET_LATE, lịch sử quá hạn vẫn cần được lưu ở lớp sự kiện; việc đã hoàn tất không làm vi phạm trước đó biến mất.

## 10. Ví dụ xuyên suốt và các ranh giới

### 10.1. Nâng severity không cấp lại 72 giờ

Giả sử cùng một phạm vi có `T0 = 2026-11-27T08:00:00Z`, ban đầu là High. Deadline remediation theo policy là `2026-12-11T08:00:00Z`.

Đến `2026-11-29T20:00:00Z`, bằng chứng xác nhận mức Critical cho lỗi thuộc phạm vi đã biết từ T0. Với quy tắc siết clock đang mở:

```text
candidate_due = T0 + 72 giờ = 2026-11-30T08:00:00Z
effective_due = min(2026-12-11T08:00:00Z, candidate_due)
              = 2026-11-30T08:00:00Z
thời gian còn lại tại lúc nâng mức = 12 giờ
```

Không đặt due thành 72 giờ kể từ lúc đổi nhãn. Nếu candidate_due đã ở quá khứ, kết quả là overdue cần escalation, không phải một lý do để chọn anchor mới. Nếu xuất hiện tín hiệu sự cố mới, có thể mở thêm incident/containment clock theo policy nhưng không làm lùi nghĩa vụ remediation đang có.

### 10.2. Mitigation đúng hạn nhưng remediation trễ

Trong một fixture độc lập, lỗi Critical có cùng T0. Biện pháp containment được xác minh ở `2026-11-27T11:00:00Z`, tức sau 3 giờ, đạt ngân sách 4 giờ.

Bản sửa được merge sau 48 giờ, nhưng phạm vi deployment chỉ được xác minh hoàn tất ở `2026-11-30T16:00:00Z`, tức sau 80 giờ. Nếu milestone remediation của hợp đồng bao gồm deployment và có hạn 72 giờ, kết quả là remediation muộn 8 giờ, dù containment đã đạt và PR merge trước deadline.

Cần lưu cả hai kết quả. Không báo mọi SLA của ticket đều đạt chỉ vì đã giảm thiểu; cũng không bỏ công nhận containment đúng hạn chỉ vì bản sửa vĩnh viễn tới muộn.

### 10.3. Biên thời gian và scope

| Fixture | Kết quả theo clock 72 giờ từ T0 |
| --- | --- |
| Completion có bằng chứng đúng `2026-11-30T08:00:00Z` | MET_ON_TIME |
| Completion tại deadline cộng 1 nanosecond, now không trước completion | MET_LATE; không cắt phần lẻ để làm tròn về đúng hạn |
| Chưa completion, now sau deadline | OVERDUE |
| Status Done nhưng không có milestone proof | Không tạo completion; clock vẫn được đánh giá từ bằng chứng thực |
| Artifact B đã sửa, deployment A còn thuộc phạm vi cam kết | Chưa đạt milestone deployment/remediation toàn phạm vi |
| Giao diện đổi sang UTC+07:00 | Thay cách hiển thị, không thay Instant hoặc ngân sách |

## 11. Cảnh báo, escalation và đo hiệu quả

### 11.1. Cảnh báo trước hạn và quá hạn

Có thể đặt ngưỡng cảnh báo khi tiêu thụ 75% và 90% ngân sách clock, cùng escalation khi quá hạn. Với clock có pause hợp lệ, tỷ lệ phải theo thời gian được policy tính, không tự dùng elapsed thô rồi đưa ra kết luận khác dashboard.

Ví dụ nền tảng kiểm tra mỗi 5 phút và hoàn thành phát/routing cảnh báo trong 5 phút tiếp theo, nhằm đáp ứng mục tiêu không quá 10 phút từ khi clock thực sự quá hạn theo nguồn thời gian được tin cậy. Đây là độ trễ phát hiện/thông báo, không phải 10 phút được cộng thêm vào SLA xử lý lỗi.

Cảnh báo cần nêu clock nào, due/anchor, mức độ, phạm vi, owner và hành động cần thiết. Nếu owner thiếu hoặc routing thất bại, cần hàng đợi/retry/escalation có owner dự phòng; không coi phát một event mà không ai nhận được là đã xử lý trách nhiệm.

Để tránh lặp vô hạn, có thể khử trùng theo defect/scope/clock, revision và ngưỡng cảnh báo. Nhưng việc khử trùng không được làm mất escalation mới khi severity/phạm vi thay đổi. Cần quan sát cả scheduler, queue thông báo và lỗi delivery.

### 11.2. Mẫu số metric phải rõ

Đối với một kỳ báo cáo đã kết thúc, có thể chọn cohort là tất cả clock remediation áp dụng có due trong kỳ theo quy tắc đo đã công bố:

```text
on_time_rate
  = số clock trong cohort có remediation được xác minh tại hoặc trước due
    / tổng số clock áp dụng trong cohort
```

Mẫu số phải bao gồm clock chưa đóng nhưng đã quá hạn; chỉ đếm ticket đã đóng sẽ tạo sai lệch có lợi khi các lỗi khó vẫn đang mở. Với kỳ chưa kết thúc, cần phân biệt pending chưa tới hạn với đã vi phạm, không gọi mọi clock chưa hoàn tất là trễ.

Exception/accepted risk không được đưa vào tử số “đã sửa đúng hạn”. Báo riêng số có ngoại lệ hợp lệ, quá hạn chưa có ngoại lệ, fixed muộn, not affected và duplicate theo quy tắc đếm được công bố. Duplicate có thể được loại khỏi số defect duy nhất nhưng nghĩa vụ/phạm vi của case gốc không được mất.

Nếu policy cho phép pause hoặc rebaseline deadline, báo cáo phải nêu đang dùng deadline nào, revision nào và hiển thị số lượng/lý do điều chỉnh. Nên có góc nhìn deadline gốc cùng kết quả theo deadline có hiệu lực để tránh giấu mức độ thay đổi nghĩa vụ.

Có thể đo thời gian acknowledge/triage/containment/remediation, tuổi lỗi đang mở, thời gian quá hạn, phân vị thời gian xử lý và tỷ lệ reopen. Không dùng trung bình duy nhất để che vài lỗi rất cũ. Severity phân tích ở thời điểm nào cũng phải rõ; không tính lại lịch sử như thể mọi ticket luôn mang severity hiện tại.

### 11.3. Diễn giải kết quả

Một nhóm có tỷ lệ fixed đúng hạn cao nhưng nhiều accepted risk sắp hết hạn hoặc nhiều scope chưa có owner vẫn có thể còn rủi ro lớn. Một nhóm có nhiều ticket Low được đóng nhanh không tự bù được việc một Critical kéo dài.

Metric đo quy trình hỗ trợ quyết định, không thay đánh giá rủi ro. Cần xem tác động, phạm vi, chất lượng bằng chứng, phần chưa biết và tình trạng deployment cùng các tỷ lệ.

## 12. Bảo vệ workflow, dữ liệu và phục hồi

### 12.1. Quyền và thay đổi có kiểm soát

API/UI cần phân biệt quyền tạo/nhận lỗi, gán owner, đánh giá severity, phê duyệt giảm mức, chỉnh anchor, xác nhận milestone, pause và chấp nhận rủi ro. Một người được sửa nội dung mô tả không mặc nhiên được kéo dài due hoặc ghi mình đã verify fix.

Milestone proof nên có nguồn, đối tượng, phiên bản/artifact, kết quả kiểm tra, phạm vi deployment và danh tính người/hệ thống xác minh. Quyền đọc chứng cứ cần phù hợp độ nhạy, tránh đưa token, payload thật, dữ liệu khách hàng hoặc PoC không cần thiết vào log công khai.

Với cập nhật đồng thời, dùng cơ chế version/transaction phù hợp để không làm mất severity revision, owner hoặc deadline chặt hơn. Một request cũ không được ghi đè due mới bằng dữ liệu cache. Quyết định, audit và nghĩa vụ phát cảnh báo nên được lưu nhất quán hoặc có cơ chế phục hồi không mất sự kiện.

### 12.2. Lỗi hệ thống không phải pause mặc định

Tracker/policy service lỗi không làm rủi ro dừng tồn tại. Cần giữ intake/sự kiện bằng cơ chế bền vững thích hợp, cảnh báo mất khả năng quan sát và khôi phục các clock với anchor gốc.

Nếu nguồn thời gian không đủ tin cậy, không tự khẳng định mọi milestone đều đúng hạn hoặc sửa timestamp để hết cảnh báo. Ghi sự cố thời gian, thu thập bằng chứng đáng tin và hiệu chỉnh kết quả đo có audit. UTC là cách biểu diễn, không tự chứng minh đồng hồ chính xác.

Khi restore/import, giữ policy/calendar revision và sự kiện áp dụng tại thời điểm quyết định. Nếu tổ chức thay policy cho case đang mở, phải có migration/rebaseline được phê duyệt, lưu cách tính trước/sau và không tự reset T0. Không lấy ngày import làm ngày first-seen mới.

Lịch sử breach, exception, pause và bằng chứng closure là dữ liệu cần khôi phục cùng ticket. Chỉ có bản ghi status cuối không đủ tái dựng nghĩa vụ hoặc kết luận đã đúng hạn.

## 13. Ma trận kiểm thử nghiệm thu

Sử dụng thời gian kiểm soát, hồ sơ lỗi tổng hợp và nguồn bằng chứng thử. Kiểm tra cả quyết định của API, trạng thái lưu trữ, audit, cảnh báo và phạm vi triển khai, không chỉ màu trên dashboard.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-DSLA-01 | Báo cáo có tín hiệu rủi ro đáng tin nhưng chưa đủ PoC; đổi rubric/confidence | Có severity tạm thời, owner/hạn triage và căn cứ; không rơi vào Low/pending vô hạn | DSLA-01, 02, 03 |
| T-DSLA-02 | Scanner/intake có sự kiện tin cậy trước thời điểm tạo ticket; client tự khai một timestamp khác | Chọn anchor đúng nguồn; giữ intake/observation/create riêng, không tin field tự khai để thay T0 | DSLA-05 |
| T-DSLA-03 | Clock giờ lịch đi qua cuối tuần; hiển thị cùng Instant ở timezone khác; fixture riêng dùng lịch làm việc có version | Tính theo đúng policy/lịch; timezone hiển thị không đổi due, lịch làm việc không bị thay bằng cộng giờ lịch tùy tiện | DSLA-06 |
| T-DSLA-04 | Completion đúng due, sau due 1 ns, now đúng/sau due, completion trước anchor hoặc ở tương lai | Quyết định đúng điều kiện biên/precision; dữ liệu sai không bị làm tròn hoặc trả đúng hạn | DSLA-06, 07 |
| T-DSLA-05 | Đổi status Done, merge PR hoặc nhập completed_at nhưng thiếu artifact/test/deployment proof | Không tạo milestone đạt trái hợp đồng; quyền verify và bằng chứng được kiểm tra | DSLA-07, 13, 17 |
| T-DSLA-06 | Nâng High lên Critical trong cùng scope, giữ T0; candidate due mới đã qua trong một lượt khác | Dùng min của due cũ và T0 + ngân sách mới; overdue được ghi/escalate, không cấp lại 72 giờ | DSLA-08 |
| T-DSLA-07 | Người không có quyền hạ severity hoặc actor có quyền sửa dữ liệu phân loại | Thay trái quyền bị chặn; sửa hợp lệ có căn cứ/revision, không tự xóa breach hoặc nới due | DSLA-02, 08, 16, 17 |
| T-DSLA-08 | Chuyển assignee/đội, merge duplicate có T0 sớm hơn, split scope và rescan | Giữ đúng anchor/nghĩa vụ/lịch sử từng scope; không reset khi tạo ticket mới | DSLA-09 |
| T-DSLA-09 | Pending vendor không có phê duyệt; hai pause được phép 09:00–10:00 và 09:30–10:30 trên clock 4 giờ từ 08:00 | Pending không tự pause; hợp khoảng cho due 13:30; pause quá giới hạn hoặc không đúng clock bị phát hiện | DSLA-12 |
| T-DSLA-10 | Accepted risk sai phạm vi/hết hạn hoặc phê duyệt sau breach | Không áp ngoại lệ trái quyền; không tính như fixed đúng hạn hoặc xóa breach đã có | DSLA-11, 16 |
| T-DSLA-11 | Containment đạt sau 3 giờ nhưng remediation/deployment đạt sau 80 giờ trong clock Critical 72 giờ | Containment đạt riêng; remediation muộn 8 giờ, không dùng merge/mitigation thay milestone deployment | DSLA-10, 13 |
| T-DSLA-12 | Reopen do fix chưa hiệu lực; lượt khác là regression sau closure đã xác minh | Case đầu giữ nghĩa vụ cũ; episode mới chỉ có anchor mới theo căn cứ/policy và vẫn liên kết lịch sử | DSLA-14 |
| T-DSLA-13 | Hai request đồng thời đổi severity/due; request cache cũ thử ghi đè; quyền thấp sửa anchor/pause | Không mất revision hoặc ghi đè hạn chặt hơn bằng dữ liệu cũ; kiểm soát quyền và audit đúng | DSLA-08, 17 |
| T-DSLA-14 | Clock vượt ngưỡng/cận hạn/quá hạn, owner thiếu, scheduler/queue/delivery lỗi | Cảnh báo/escalation đáp ứng hợp đồng 5/10 phút khi điều kiện hệ thống được bảo đảm; lỗi quan sát/delivery được phát hiện và xử lý | DSLA-15, 17 |
| T-DSLA-15 | Restore/import dữ liệu cũ, thay policy/calendar và mất kết nối tracker | Khôi phục anchor/revision/event history, không dùng ngày import hoặc outage làm pause tự động | DSLA-05, 18 |
| T-DSLA-16 | Cohort kỳ đã kết thúc có fixed đúng hạn, fixed muộn, open overdue, accepted risk và duplicate | Mẫu số/tử số theo chính sách công bố; không bỏ open overdue hoặc gộp accepted risk vào fixed đúng hạn | DSLA-11, 16 |
| T-DSLA-17 | Chứng cứ chứa dữ liệu nhạy cảm, người đọc không có quyền, log/debug dump hồ sơ | Không lộ secret/PoC/dữ liệu dư thừa; audit đủ nguồn/actor/reason mà không phát tán nội dung nhạy cảm | DSLA-16, 17 |
| T-DSLA-18 | Defect hợp lệ, severity/policy/owner rõ, các proof và deployment đủ trước due | Clock tương ứng đạt đúng hạn, closure có lý do và truy vết; test dương tính không bị chặn vô điều kiện | DSLA-01, 07, 13, 18 |

### 13.1. Acceptance criteria theo Given–When–Then

**AC-01 — Anchor không bị dời vì luân chuyển.** Given sự kiện đáng tin trong scope tại `2026-11-27T08:00:00Z`. When ticket được tạo sau, đổi đội hoặc gộp duplicate. Then T0 và các nghĩa vụ đã biết vẫn liên kết về sự kiện phù hợp; due không tự bắt đầu từ thời điểm gán đội. Các thay đổi có actor/reason/revision.

**AC-02 — Severity tạm thời và siết hạn.** Given case chưa đủ căn cứ chốt nhưng có tín hiệu đáng tin. When intake/triage. Then có mức tạm thời và deadline theo policy, không pending vô hạn. Với clock remediation High còn mở ở ví dụ 10.1, When nâng lên Critical. Then due là `2026-11-30T08:00:00Z`, không phải 72 giờ sau thời điểm đổi nhãn.

**AC-03 — Đúng biên và đúng bằng chứng.** Given clock 72 giờ từ T0 và proof được xác minh cho đúng milestone. When completion bằng due. Then đúng hạn. When completion sau due 1 ns. Then muộn; không làm tròn để chuyển kết quả. Khi chỉ có status Done hoặc timestamp tự khai, Then không tạo proof hoàn tất hợp lệ.

**AC-04 — Pause/exception không làm mất rủi ro.** Given policy mặc định không pause. When ticket ở trạng thái chờ vendor. Then clock vẫn chạy. Với các pause được phép ở fixture 4 giờ, Then due được tính theo hợp khoảng là 13:30. Accepted risk/exception được báo riêng, có scope/expiry và không được tính như đã sửa đúng hạn hoặc xóa vi phạm trước đó.

**AC-05 — Hoàn tất theo milestone và scope.** Given containment có proof đúng hạn nhưng deployment chứa fix chưa hoàn tất trong hạn remediation. When hệ thống đánh giá. Then giữ kết quả containment đạt riêng và remediation chưa đạt/muộn tương ứng. Chỉ đóng fixed cho phạm vi đã đủ proof; artifact/nhánh/instance còn lỗi được giữ nghĩa vụ/owner theo hợp đồng.

**AC-06 — Báo cáo và phục hồi trung thực.** Given cohort có open overdue và accepted risk, cùng lịch sử severity/pause/clock. When báo cáo kỳ hoặc restore/import. Then metric giữ mẫu số đúng quy tắc, accepted risk không trở thành fixed, anchor/revision không bị reset và correction có căn cứ được lưu riêng. API/nhãn trạng thái không được ghi đè lịch sử như thể vi phạm chưa từng xảy ra.

### 13.2. Bằng chứng cần lưu

Lưu fixture event/anchor, nguồn và độ chắc chắn, scope/episode, policy/calendar revision, severity history, due trước/sau, pause/exception decisions, milestone proof, artifact/deployment references và trạng thái audit/cảnh báo/metric thực tế.

Với kiểm thử deadline, cần kiểm soát precision và nguồn thời gian, không dùng ngủ chờ nhiều ngày. Với workflow, cần thử API/quyền/concurrency và bằng chứng bị thiếu. Với restore, đối chiếu các liên kết và clock tính lại, không chỉ xem ticket có xuất hiện trở lại.

Unit test hàm cộng thời gian không chứng minh workflow có quyền đúng hoặc fix đã được triển khai. Ngược lại, một dashboard hiển thị đúng không chứng minh dữ liệu anchor/milestone đầu vào đáng tin. Cần cả logic tính và chuỗi bằng chứng.

## 14. Truy vết trong vòng đời phát triển

```text
Mục tiêu xử lý rủi ro đúng mức, đúng hạn và đúng phạm vi
  → SLR-xx: anchor bị dời, severity bị hạ sai, status không có proof, pause/exception sai
  → DSLA-xx: rubric + clock + owner + điều kiện đạt + audit
  → Intake/triage registry + workflow có quyền + evidence + deadline engine
  → T-DSLA-xx và AC-xx
  → Cảnh báo, remediation, deployment verification, báo cáo và phục hồi
```

| Mục tiêu | Yêu cầu | Kiểm chứng tiêu biểu |
| --- | --- | --- |
| Phân loại có căn cứ và không pending vô hạn | DSLA-01, 02, 03, 04 | T-DSLA-01, 07; AC-02 |
| Anchor/lịch/biên thời gian đúng | DSLA-05, 06 | T-DSLA-02, 03, 04; AC-01, 03 |
| Không reset khi đổi trạng thái/phạm vi | DSLA-08, 09, 14 | T-DSLA-06, 08, 12, 13; AC-01, 02 |
| Mitigation/exception/pause khác với fixed | DSLA-10, 11, 12 | T-DSLA-09, 10, 11; AC-04, 05 |
| Hoàn tất có bằng chứng đúng scope | DSLA-07, 13 | T-DSLA-05, 11, 18; AC-03, 05 |
| Cảnh báo, metric, quyền và khôi phục đáng tin | DSLA-15, 16, 17, 18 | T-DSLA-13, 14, 15, 16, 17; AC-06 |

Khi đổi rubric, ngân sách, lịch, workflow, yêu cầu proof hoặc quyền phê duyệt, phải kiểm tra tác động tới clock đang mở và báo cáo lịch sử. Cần nêu thay đổi áp dụng cho case mới hay có migration cho case cũ, không để một cập nhật cấu hình âm thầm đổi mọi nghĩa vụ.

## 15. Lỗi thường gặp và bài tập áp dụng

| Cách làm | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Critical xử lý ngay.” | Không có milestone, anchor hoặc điều kiện đạt | Ngân sách theo từng pha, owner và bằng chứng cụ thể |
| “Severity thấp vì chưa có PoC.” | Có thể nhầm confidence thấp với tác động thấp | Mức tạm thời, giả định và hạn triage có kiểm soát |
| “Chuyển đội thì bắt đầu lại SLA.” | Xóa thời gian rủi ro đã tồn tại | Giữ anchor và lịch sử nghĩa vụ |
| “Nâng Critical thì có thêm 72 giờ từ bây giờ.” | Có thể gia hạn lỗi đã được biết | Quy tắc siết deadline clock đang mở theo anchor/policy |
| “Tắt feature là đã sửa xong.” | Có thể mới containment hoặc mitigation tạm thời | Giữ residual risk và clock sửa vĩnh viễn theo hợp đồng |
| “Merge code trước due là đúng hạn.” | Chưa chứng minh fix verified/deployed trong scope | Milestone riêng và proof cho artifact/deployment |
| “Accepted risk là closed fixed.” | Nhầm quyết định rủi ro với khắc phục | Disposition/metric riêng, scope/expiry và trách nhiệm |
| “Paused hai lần thì cộng cả hai khoảng.” | Overlap có thể bị cộng trùng | Tính hợp các khoảng hợp lệ cho đúng clock |
| “Chỉ tính ticket đã đóng để đo đúng hạn.” | Bỏ open overdue và tạo survivor bias | Cohort/mẫu số rõ, phân biệt pending/overdue/exception |
| “Restore ticket mới là có SLA mới.” | Làm mất anchor, policy và breach history | Bảo toàn event/revision, correction có audit |

Một đội đặt mọi lỗi chưa xác minh thành Low. T0 lấy từ ngày đội phát triển nhận ticket, dù scanner đã ghi nhận trước đó. Khi gần deadline, đội hạ severity hoặc chuyển sang Pending Vendor để pause. Họ đóng Fixed khi PR merge, chưa kiểm tra production. Dashboard chỉ đo ticket đã đóng, và restore dữ liệu lấy ngày import làm ngày tạo lỗi.

Hãy thực hiện:

1. Nêu ít nhất sáu rủi ro quy trình và bất biến bị vi phạm.
2. Thiết kế rubric severity có impact, điều kiện, scope, kiểm soát và confidence; phân biệt priority.
3. Định nghĩa T0, từng milestone, đơn vị thời gian, lịch và proof hoàn tất.
4. Viết sáu yêu cầu có ID, owner, điều kiện đạt, lỗi và bằng chứng nghiệm thu.
5. Thiết kế xử lý nâng/hạ severity, duplicate, pause overlap, accepted risk và reopen.
6. Đề xuất metric giữ open overdue/exception cùng kiểm soát tránh mất lịch sử.
7. Nêu các test cho timezone, biên deadline, completion thiếu proof, concurrency và restore/import.

Trước khi chấp nhận đặc tả, kiểm tra:

- Severity, priority, confidence và status có ý nghĩa riêng và owner rõ không?
- Rubric, policy/calendar revision, anchor và nguồn thời gian có được ghi không?
- Deadline có định nghĩa đúng milestone/phạm vi, đơn vị và biên không?
- Chưa xác định, chuyển đội, duplicate, rescan và import có tránh reset tuổi lỗi không?
- Nâng/hạ severity có căn cứ, quyền và quy tắc deadline/lịch sử không?
- Mitigation, pause, accepted risk và fixed có điều kiện/bằng chứng/metric riêng không?
- Closure có test/artifact/deployment proof theo phạm vi đã cam kết không?
- Reopen/regression và scope mới có liên kết lịch sử cùng anchor có căn cứ không?
- Cảnh báo, routing và mất quan sát có ngân sách/owner/escalation không?
- API, audit, correction, metric và restore có được kiểm thử để không che vi phạm không?

Severity và SLA có giá trị khi chúng dẫn tới hành động cùng bằng chứng đúng phạm vi, đồng thời giữ được sự thật về thời gian rủi ro thay vì chỉ thay nhãn ticket.
