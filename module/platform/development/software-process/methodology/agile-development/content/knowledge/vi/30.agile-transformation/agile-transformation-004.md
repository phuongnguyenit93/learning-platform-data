# Lựa chọn nhóm thí điểm cùng phạm vi thử nghiệm có thể học hỏi

Một tổ chức muốn “chuyển đổi sang Agile” nên chọn nhóm nào để thử trước? Nhóm xuất sắc nhất để dễ có báo cáo đẹp, nhóm đang khó khăn nhất để nhanh thấy thay đổi, hay nhóm đông nhất để chứng minh có thể mở rộng? Nếu chọn sai, sau ba tháng tổ chức có thể đã tổ chức rất nhiều Daily Scrum, mua công cụ quản lý backlog và đào tạo các vai trò mới, nhưng vẫn **không biết cách làm mới có giúp khách hàng nhận giá trị sớm hơn và đáng tin cậy hơn hay không**.

**Một thí điểm (pilot) chuyển đổi Agile tốt không phải buổi diễn tập một framework.** Đó là **thử nghiệm có chủ đích trong công việc thực**, được thiết kế để trả lời những câu hỏi đủ quan trọng về giá trị sản phẩm, khả năng phối hợp, chất lượng kỹ thuật, dòng công việc và những rào cản tổ chức. Thí điểm cần đủ nhỏ để quan sát và điều chỉnh, nhưng đủ thực để những điều học được có giá trị.

Bài thuộc chương **Chuyển đổi Agile** trong mô-đun **AGILE_DEVELOPMENT**. Nội dung áp dụng mục tiêu Agile: phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp.

**Mục tiêu học tập:** Sau bài này, bạn có thể:

- Phân biệt **mục đích học hỏi của pilot** với mục đích “chứng minh Agile luôn thành công”.
- Chọn nhóm thí điểm dựa trên **công việc thực, quyền chủ động, sự hỗ trợ, khả năng tích hợp/phát hành, mức phụ thuộc và tính đại diện**.
- Giải thích vì sao **nhóm thuận lợi nhất hoặc khó khăn nhất** đều có thể tạo kết luận sai nếu thiếu bối cảnh.
- Xác định phạm vi thử nghiệm theo **một vấn đề người dùng và lát cắt có giá trị**, không triển khai đồng loạt quá nhiều nghi thức.
- Viết **giả thuyết có thể bị bác bỏ**, baseline, chỉ số outcome, flow, quality và guardrail.
- Lựa chọn **Scrum, Kanban, XP hoặc kết hợp thực hành phù hợp** với loại công việc thay vì sao chép hình thức.
- Thiết kế **quyền quyết định, coaching, sự tham gia stakeholder và vòng phản hồi** để pilot có cơ hội học hỏi.
- Đánh giá khi nào nên **giữ, thay đổi, tạm dừng, kết thúc hoặc mở rộng** thí điểm và điều gì không nên suy rộng.

## 1. Thí điểm chuyển đổi Agile là gì?

**Chuyển đổi Agile** là quá trình cải thiện cách tổ chức nhận biết nhu cầu, chọn việc có giá trị, tạo và kiểm chứng phần mềm, phối hợp, học hỏi rồi thích ứng. Nó có thể liên quan tới **cấu trúc nhóm, quyền quyết định, Product Management, thực hành kỹ thuật, cách ưu tiên và chính sách vận hành**.

Một pilot là **phạm vi triển khai giới hạn**, trong đó tổ chức chủ động thay đổi một số cách làm và thu bằng chứng về kết quả. Nó không tự động là toàn bộ quá trình chuyển đổi.

| Cách nhìn | Câu hỏi | Dấu hiệu |
| --- | --- | --- |
| **Cài đặt nghi thức** | Có đủ Daily, Sprint Planning và bảng Scrum chưa? | Chỉ kiểm tra attendance, tên vai trò và tool |
| **Đào tạo nhận thức** | Mọi người hiểu các khái niệm Agile không? | Có ích nhưng chưa chứng minh thay đổi công việc thật |
| **Thí điểm để học** | Việc thay đổi cách phối hợp có giúp giao giá trị tốt hơn, giảm rủi ro và điều chỉnh nhanh hơn không? | Có giả thuyết, công việc thật, đo lường, phản hồi và quyết định |
| **Mở rộng có căn cứ** | Điều kiện nào phải có trước khi áp dụng cho các nhóm khác? | Nêu được cơ chế thành công, giới hạn và các rào cản tổ chức |

**Đích đến không phải “100% nhóm dùng Scrum”.** Một tổ chức có thể cần Scrum cho phát triển sản phẩm có Product Goal rõ, Kanban cho dòng yêu cầu liên tục, và thực hành XP để tăng khả năng tích hợp, kiểm thử và phát hành nhỏ. Giá trị đến từ **cách chọn và áp dụng có bằng chứng**, không từ số lượng thuật ngữ Agile trên sơ đồ tổ chức.

## 2. Bắt đầu từ vấn đề đáng giải quyết, không từ danh sách nghi thức

Một tuyên bố “Chúng ta cần Agile vì công ty khác đang làm” chưa đủ để chọn pilot. Hãy mô tả **đau điểm hiện tại và kết quả tổ chức cần thay đổi**.

### Bốn ví dụ về vấn đề có thật

| Hiện trạng | Vấn đề cần học | Kết quả muốn thấy |
| --- | --- | --- |
| Yêu cầu mất nhiều tuần mới có bản cho người dùng thử | Có quá nhiều chuyển giao hoặc lô công việc lớn? | Time to feedback ngắn hơn, chất lượng không giảm |
| Nhóm hoàn thành task nhưng giá trị sản phẩm thấp | Có hiểu sai nhu cầu hoặc backlog thiếu hướng ưu tiên? | Người dùng hoàn tất tác vụ quan trọng tốt hơn |
| Tích hợp thường xuyên thất bại | Thiếu CI, test hợp đồng, lát cắt dọc? | Increment dùng được và lỗi hồi quy giảm |
| Thay đổi ưu tiên làm mọi người chuyển ngữ cảnh liên tục | Quản lý WIP và quyền quyết định chưa rõ? | Ít hạng mục dở, công việc hoàn tất đều và nhịp bền vững hơn |

Một số vấn đề có thể do **quy tắc ngoài nhóm**: ngân sách khóa theo dự án, quy trình phê duyệt kéo dài, không có quyền phát hành, hoặc nhiều cấp phân công chồng chéo. **Đổi tên Project Manager thành Scrum Master không tự giải quyết chúng**.

### Viết bài toán theo ngôn ngữ quan sát

Thay vì:

> “Đội chưa đủ trưởng thành Agile.”

Nên làm rõ:

> “Từ khi một nhu cầu người học được ưu tiên đến khi có Increment có thể dùng để lấy phản hồi thường mất lâu; phần lớn thời gian nằm ở chờ tích hợp và quyết định. Nhóm muốn thử giảm quy mô lô, làm rõ Product Backlog và tích hợp sớm để rút ngắn vòng phản hồi mà vẫn bảo vệ dữ liệu học viên.”

Phát biểu thứ hai chỉ ra **đơn vị quan sát, cơ chế có thể thử và ràng buộc chất lượng**. Đây là nền tảng để chọn nhóm.

## 3. Phân biệt giả thuyết kết quả và giả thuyết cơ chế

Thí điểm tốt không chỉ nói “sau ba Sprint sẽ nhanh hơn”. Cần có ít nhất hai lớp giả thuyết.

**Giả thuyết kết quả (outcome hypothesis):**

> “Nếu người học nhận được những cải tiến nhỏ đáng tin cậy và được kiểm chứng sớm hơn, tỷ lệ tiếp tục học từ tiến độ đã lưu sẽ cải thiện, không làm tăng lỗi dữ liệu.”

**Giả thuyết cơ chế làm việc (process hypothesis):**

> “Nếu nhóm dùng một Product Backlog ưu tiên rõ, chia lát cắt dọc và kiểm thử tích hợp liên tục, thời gian chờ làm rõ/tích hợp sẽ giảm, khiến một Increment đạt Definition of Done đến được người học sớm hơn.”

Hai giả thuyết này có thể cho kết quả khác nhau:

- **Flow tốt hơn nhưng outcome chưa tăng:** Có thể giải pháp sản phẩm không phù hợp, người dùng chưa được tiếp xúc hoặc cửa sổ đo quá ngắn.
- **Outcome tăng nhưng sự cố tăng:** Không được xem là thành công bền vững nếu vi phạm guardrail.
- **Outcome chưa đổi và flow chưa cải thiện:** Có thể giả thuyết sai, thí điểm triển khai chưa đủ hoặc đang gặp rào cản tổ chức.
- **Flow cải thiện và chất lượng ổn định nhưng dữ liệu ít:** Có dấu hiệu tích cực, **chưa đủ bằng chứng để suy rộng**.

### Mẫu giả thuyết kiểm chứng được

~~~text
ĐỐI TƯỢNG:
  Nhóm phát triển chức năng lưu/khôi phục tiến độ
  cho người học có bài đang dở.

VẤN ĐỀ:
  Hạng mục chờ làm rõ, review và tích hợp lâu.

THAY ĐỔI THỬ:
  Một Product Backlog có thứ tự rõ, lát cắt dọc,
  kiểm thử hợp đồng và CI khi có thay đổi.

CƠ CHẾ DỰ ĐOÁN:
  Ít chuyển giao, ít làm lại và phát hiện lỗi sớm.

KẾT QUẢ MONG ĐỢI:
  Rút ngắn end-to-end lead time/time to feedback;
  người dùng có cơ hội kiểm chứng tính năng sớm hơn.

GUARDRAILS:
  Không tăng lỗi mất tiến độ, truy cập trái phép,
  gánh nặng làm ngoài giờ và sự cố nghiêm trọng.

ĐÁNH GIÁ:
  So với baseline theo cùng định nghĩa;
  ghi bối cảnh và những thay đổi khác cùng lúc.
~~~

**Đặt giả thuyết trước khi thấy số liệu** giúp tránh việc lựa con số thuận lợi rồi tuyên bố thí điểm thành công.

## 4. Thế nào là một nhóm thí điểm phù hợp?

Một nhóm thí điểm không cần hoàn hảo nhưng phải có **điều kiện để thực hiện thí nghiệm thật**. Chọn nhóm chỉ vì quản lý thích Agile hoặc vì nhân viên đã quen họp theo Scrum là chưa đủ.

### Những tiêu chí chọn nhóm

| Tiêu chí | Vì sao quan trọng? | Câu hỏi kiểm tra |
| --- | --- | --- |
| **Vấn đề và giá trị thực** | Pilot cần trả lời vấn đề đáng đầu tư | Nhóm có hành trình người dùng hoặc dịch vụ cần cải thiện? |
| **Năng lực giao Increment** | Chỉ hoàn thành task cục bộ khó đo giá trị | Có thể tích hợp và kiểm chứng một lát cắt end-to-end? |
| **Quyền quyết định phù hợp** | Không thể thử nếu mọi thay đổi phải qua nhiều cấp | Ai quyết định thứ tự công việc, cách làm và phát hành? |
| **Sự hỗ trợ của lãnh đạo** | Rào cản cấp tổ chức cần người có quyền xử lý | Ai có thể tháo blocker ngoài quyền nhóm? |
| **Tính tự nguyện và cam kết học hỏi** | Cải tiến cần sự tham gia trung thực | Nhóm có cơ hội thảo luận, phản biện và nêu rủi ro? |
| **Tính đại diện có chủ đích** | Kết quả phải giúp học về bối cảnh sẽ mở rộng | Nhóm giống/khác những nhóm tiếp theo ở điểm nào? |
| **Phụ thuộc có thể quản lý** | Quá nhiều phụ thuộc làm tín hiệu nhiễu | Có vài rủi ro thật để học, nhưng không bất khả thi? |
| **Đủ năng lực kỹ thuật và hỗ trợ** | Không bỏ chất lượng chỉ để “chạy Scrum” | Có test, CI, môi trường, hỗ trợ khi cần? |
| **Dữ liệu có thể quan sát** | Không thể kết luận nếu baseline hoặc outcome mơ hồ | Có cách đo flow, quality và phản hồi người dùng? |
| **An toàn và mức rủi ro phù hợp** | Pilot không được biến khách hàng thành đối tượng chịu lỗi không kiểm soát | Có guardrail, rollout an toàn, quyền dừng? |

**Không có nhóm “điểm tối đa” ở mọi tiêu chí.** Điều quan trọng là biết **điểm mạnh, điều thiếu và cách hỗ trợ**; một nhóm có điều kiện chưa tốt vẫn có thể phù hợp nếu rào cản chính là thứ tổ chức chủ động muốn học cách tháo.

## 5. Chọn nhóm đại diện, không “chọn đẹp”

Có ba kiểu lựa chọn thiếu cân bằng phổ biến:

1. **Nhóm xuất sắc nhất, ít phụ thuộc nhất:** Dễ có báo cáo thành công nhưng kết quả có thể không áp dụng cho nhóm thông thường đang bị chặn.
2. **Nhóm khó khăn nhất, thiếu quyền và đang xử lý khủng hoảng:** Nếu thí điểm thất bại, tổ chức khó phân biệt vấn đề của thực hành Agile với điều kiện ban đầu quá bất lợi.
3. **Nhóm đông nhất hoặc nổi tiếng nhất:** Có thể tạo nhiều chú ý nhưng độ phức tạp tổ chức khiến vòng học quá chậm.

### Cách tránh thiên lệch chọn mẫu

Hãy mô tả trước **“điều kiện mà phần lớn nhóm đích sẽ đối mặt”**: loại sản phẩm, mức phụ thuộc, kỹ năng, quyền triển khai, rủi ro chất lượng, khoảng cách địa lý và mức hỗ trợ lãnh đạo.

Sau đó chọn nhóm có thể:

- Giao một lát cắt thực trong phạm vi đo được.
- Có **vài rào cản điển hình**, đủ để học cách tháo.
- Có đủ quyền hoặc **lộ trình trao quyền** để không chờ vô hạn.
- Có năng lực và an toàn để thử điều chỉnh.
- Được xác nhận **điểm khác biệt** so với các nhóm tiếp theo.

### Không dùng một nhóm để “đại diện cho tất cả”

Một đội phát triển sản phẩm web có Product Owner và pipeline tốt **không tự đại diện** cho đội chịu yêu cầu pháp lý phức tạp hoặc đội xử lý incident 24/7. Khi suy rộng, nên nói:

> “Cơ chế chia lát cắt và tích hợp sớm có dấu hiệu phù hợp với nhóm có tính năng người dùng, quyền release và pipeline tương tự. Chưa có bằng chứng nó hoạt động cùng cách trong nhóm phải chờ đối tác hoặc xử lý yêu cầu đến liên tục.”

Pilot tốt tạo **điều kiện áp dụng và giới hạn**, không tạo tuyên bố “công thức Agile chuẩn cho toàn công ty”.

## 6. Ma trận đánh giá nhóm ứng viên

Một ma trận ngắn giúp các bên giải thích lựa chọn bằng bằng chứng thay vì danh tiếng của trưởng nhóm. Không biến nó thành bài kiểm tra năng lực nhân sự.

### Thang mô tả 1–3 (minh họa)

- **1 — Chưa có điều kiện thiết yếu:** Ví dụ không có quyền kiểm chứng hoặc không thể tiếp cận phản hồi người dùng.
- **2 — Có thể thí điểm nếu bổ sung hỗ trợ:** Ví dụ còn một phụ thuộc tích hợp nhưng có người chịu trách nhiệm xử lý.
- **3 — Điều kiện tương đối rõ:** Có khả năng thử trong phạm vi đã nêu với rủi ro quản lý được.

Ví dụ giả định cho ba nhóm:

| Tiêu chí | Nhóm A: tính năng học | Nhóm B: vận hành nền tảng | Nhóm C: migration dữ liệu |
| --- | ---: | ---: | ---: |
| Vấn đề/kết quả có thể quan sát | 3 | 3 | 2 |
| Có lát cắt thực để thử | 3 | 2 | 1 |
| Quyền quyết định và hỗ trợ | 2 | 2 | 1 |
| Phụ thuộc có thể quản lý | 2 | 2 | 1 |
| Năng lực chất lượng/an toàn | 3 | 3 | 2 |
| Có thể nhận phản hồi tương đối sớm | 3 | 2 | 1 |
| **Tổng minh họa** | **16** | **14** | **8** |

**Các điểm này không phải phép đo khách quan hay bảng xếp hạng đội.** Nhóm A có thể là pilot ban đầu phù hợp để học về phát triển lát cắt có giá trị; nhóm B có thể phù hợp cho pilot **Kanban/dòng sự cố** với câu hỏi khác; nhóm C không nên bị ép thử ngay nếu thay đổi dữ liệu khó đảo ngược chưa có cơ chế an toàn.

### Hỏi sâu hơn tổng điểm

- Nếu nhóm A được chọn, **rào cản nào cần lãnh đạo hỗ trợ** để pilot không thất bại vì thiếu quyền?
- Nhóm B có **mục tiêu học khác** nên cần một pilot riêng, thay vì so cùng outcome với A?
- Nhóm C cần làm gì để trở thành **ứng viên an toàn** trong tương lai?
- Nhóm A có quá thuận lợi so với những nhóm định mở rộng không?

**Không tự động chọn điểm cao nhất**. Một điều kiện bắt buộc như bảo mật, khả năng dùng Increment hay quyền tham gia phản hồi **không thể được bù chỉ bằng điểm cao ở tiêu chí khác**.

## 7. Cam kết hỗ trợ tổ chức trước khi bắt đầu

Một lỗi chuyển đổi Agile là **giao trách nhiệm cải tiến cho team nhưng giữ nguyên mọi rào cản ngoài quyền team**. Ví dụ tổ chức yêu cầu phát hành liên tục nhưng vẫn bắt chờ hội đồng phê duyệt mỗi tháng, hoặc yêu cầu Sprint Goal ổn định nhưng mỗi cấp quản lý tự ý chen việc bất kỳ lúc nào.

### Những cam kết nên làm rõ

| Cam kết | Vì sao cần | Dấu hiệu kiểm chứng |
| --- | --- | --- |
| **Quyền ưu tiên sản phẩm** | Tránh nhiều người giao danh sách xung đột | Có người chịu trách nhiệm sắp thứ tự backlog và giải thích trade-off |
| **Bảo vệ năng lực pilot** | Không dùng mọi người vừa làm pilot vừa nhận toàn bộ việc cũ | Có thỏa thuận năng lực, on-call và sự cố |
| **Quyền điều chỉnh workflow** | Không thể thử WIP limit hoặc cải thiện review nếu phải chờ mọi cấp | Nhóm có phạm vi tự quyết đã thống nhất |
| **Tháo blocker ngoài nhóm** | Phụ thuộc hạ tầng, quyền release, chính sách ngân sách | Có người có thẩm quyền phản hồi trong cửa sổ hợp lý |
| **Hỗ trợ kỹ thuật** | Chất lượng cần CI, test, môi trường và chuyên môn | Có nguồn lực thực, không chỉ khóa học |
| **An toàn thử nghiệm** | Báo lỗi phải được khuyến khích thay vì giấu | Có cơ chế dừng và post-incident review không đổ lỗi |
| **Thời gian để học** | Không thể kết luận từ một tuần hoặc một cuộc họp | Có các mốc kiểm tra và thời gian quan sát phù hợp |

### Lãnh đạo không chỉ “mở màn pilot”

Những hành động có ích gồm:

- Không dùng **velocity, số commit hay số giờ online** làm KPI thưởng phạt của cá nhân trong pilot.
- Công khai **điều kiện và quyền hạn** đã trao cho nhóm.
- Nhìn backlog cấp tổ chức để **loại bỏ yêu cầu ưu tiên mâu thuẫn**.
- Tham gia giải quyết trở ngại thuộc quyền mình thay vì yêu cầu Scrum Master “tự lo”.
- Chấp nhận kết quả thí điểm có thể **phản bác giả thuyết ban đầu**.

**Một pilot mà chỉ được phép “báo thành công” không phải thí nghiệm học hỏi đáng tin.**

## 8. Chọn ranh giới nhóm và sản phẩm phù hợp

Để học về phát triển phần mềm tăng dần, cần một phạm vi mà **người dùng có thể nhận lợi ích của một Increment** hoặc ít nhất có thể kiểm chứng một kết quả nghiệp vụ xác định.

### Những phạm vi quá hẹp

- Chỉ thử Daily Scrum cho một nhóm viết tài liệu kỹ thuật, không có quyền đổi cách nhận công việc.
- Chỉ “đưa ticket lên board” nhưng không được thay đổi WIP hoặc thứ tự.
- Chỉ làm API nội bộ, không biết client nào sử dụng hoặc khi nào tích hợp.
- Chỉ đào tạo user story mà không có Product Owner/người nghiệp vụ để trả lời.

Những hoạt động này có thể là **bước chuẩn bị**, nhưng khó đủ để đánh giá kết quả chuyển đổi Agile end-to-end.

### Những phạm vi quá rộng

- Cùng lúc thay toàn bộ sơ đồ tổ chức, quy trình ngân sách, kiến trúc và công cụ của hàng chục nhóm.
- Đổi framework, chính sách release và đo lường trong một ngày nhưng không có baseline.
- Thử nhiều “thực hành mới” đến mức khi kết quả thay đổi **không biết cơ chế nào có tác dụng**.

### Ranh giới vừa đủ

Một lựa chọn tốt thường là:

> “Một nhóm hoặc tập người phối hợp có khả năng tạo ra **một lát cắt sản phẩm tích hợp**, nhận phản hồi từ người dùng/stakeholder có thực và điều chỉnh cách làm qua vài vòng ngắn, trong những chính sách chất lượng có thể kiểm chứng.”

Nếu team phụ thuộc một đơn vị khác để giao, cần đưa **ranh giới phụ thuộc ấy vào kế hoạch thí điểm**: hợp đồng, môi trường, thời gian chờ và người tháo. Không giả vờ team có toàn quyền end-to-end khi họ không có.

### Scrum cụ thể có yêu cầu riêng

Theo **Scrum Guide 2020**, Scrum Team là một đơn vị **tự quản, đa kỹ năng**, bao gồm **Product Owner, Scrum Master và Developers**, thường gồm **10 người hoặc ít hơn** và tập trung một Product Goal. Nếu nhiều Scrum Team cùng làm **một sản phẩm**, họ chia sẻ **một Product Goal, Product Backlog, Product Owner và Definition of Done**.

Điều này không bắt buộc mọi pilot phải chọn Scrum. Nhưng nếu gọi thí điểm là **Scrum pilot**, nên giữ nguyên các accountabilities, events, artifacts và commitments chính, không tự thay thế bằng hệ thống báo cáo task theo tên Scrum.

## 9. Chọn phạm vi theo một lát cắt có giá trị, không theo phòng ban

**Ví dụ:** Người học có bài đang dở thường phải tìm lại vị trí khi đăng nhập. Một số đội đề xuất pilot “xây lại toàn bộ nền tảng học”, trong khi nhóm khác đề xuất chỉ “dùng bảng Scrum cho nhóm backend”.

Một lựa chọn có thể học hỏi hơn:

> **Pilot:** Cải thiện hành trình “đã học dở → lưu tiến độ đáng tin cậy → quay lại đúng vị trí” trên một nhóm bài học có kết nối, với dữ liệu an toàn, phản hồi người dùng và khả năng phát hành theo phạm vi đã thống nhất.

### Một lát cắt dọc gồm gì?

~~~text
Người học hoàn tất một bước
  -> Giao diện gửi yêu cầu lưu
  -> Dịch vụ xác nhận trạng thái đúng hợp đồng
  -> Dữ liệu được ghi bền vững theo yêu cầu
  -> Người học mở lại với cùng tài khoản
  -> Khôi phục đúng tiến độ đã xác nhận
  -> Quan sát thành công/lỗi và phản hồi
~~~

Lát cắt không cần hỗ trợ mọi loại khóa học, offline đa thiết bị hay mọi chiến lược xung đột ngay từ đầu. Nhưng nó **phải đủ đúng và an toàn** theo các ràng buộc hiện tại: phân quyền, lưu dữ liệu, xử lý lỗi và kiểm thử.

### Bảng phạm vi có chủ đích

| Trong phạm vi pilot | Ngoài phạm vi ở vòng đầu | Lý do |
| --- | --- | --- |
| Một hành trình lưu/khôi phục có kết nối | Đồng bộ offline ở nhiều thiết bị | Chưa phải nhu cầu đã được xác nhận cho lát cắt |
| Hợp đồng trạng thái lưu có ý nghĩa rõ | Framework plugin cho mọi chính sách tiến độ | Tránh xây khả năng suy đoán |
| Tích hợp với xác thực và lưu trữ hiện có | Thay thế toàn bộ hệ thống dữ liệu | Giảm rủi ro migration không cần thiết |
| Unit/integration tests và DoD | Tự động hóa mọi kiểm thử giả định tương lai | Chọn kiểm chứng phù hợp rủi ro |
| Một nhóm người học được tiếp xúc có kiểm soát | Bật cho toàn bộ người dùng từ ngày đầu | Có thời gian quan sát và cơ chế dừng |
| Outcome/quality/flow metrics | Dashboard xếp hạng từng Developer | Đo cải tiến hệ thống, không giám sát cá nhân |

**Ngoài phạm vi hiện tại không phải lời hứa “không bao giờ làm”.** Product Backlog có thể được điều chỉnh khi có bằng chứng và nhu cầu mới. Nếu rủi ro đã biết khiến một phần “ngoài phạm vi” phải giải quyết sớm để an toàn, hãy cập nhật ranh giới thay vì viện cớ YAGNI.

## 10. Phạm vi pilot gồm cả thay đổi cách làm và phần sản phẩm cần kiểm chứng

Một số dự án thí điểm chỉ nêu “phát triển tính năng X” nhưng không nói **đang thử điều gì trong cách làm**. Một số khác chỉ nêu “bắt đầu dùng Scrum” nhưng không có kết quả sản phẩm. Cần kết nối hai lớp.

### Hai backlog hoặc hai lớp công việc?

Trong Scrum, **Product Backlog** có thứ tự phục vụ cải thiện sản phẩm. Các hoạt động cải tiến quy trình như **thử WIP limit, điều chỉnh cách refinement hoặc cải thiện CI** có thể được quản lý theo cách phù hợp và cần được thấy rõ về năng lực, nhưng không nên tự tạo một “backlog thứ hai” tranh quyền ưu tiên sản phẩm. Những cải tiến kỹ thuật ảnh hưởng sản phẩm có thể là Product Backlog Item nếu phù hợp quyết định Product Owner và bối cảnh.

| Lớp | Nội dung pilot | Kết quả cần kiểm chứng |
| --- | --- | --- |
| **Sản phẩm** | Lát cắt tiếp tục học đáng tin cậy | Học viên tiếp tục được, lỗi không tăng |
| **Dòng công việc** | Chia PBI nhỏ, giới hạn WIP, giảm chờ review/tích hợp | Cycle time, Work Item Age và time to feedback |
| **Kỹ thuật** | TDD/BDD ở ranh giới quan trọng, CI, contract tests | Lỗi hồi quy, tính đúng tích hợp, khả năng phát hành |
| **Cộng tác** | PO và Developers làm rõ ví dụ sớm; quyết định được ghi chung | Ít hỏi lại và làm lại do hiểu sai |
| **Tổ chức** | Có đường tháo blocker môi trường, phân quyền release | Giảm chờ ngoài quyền nhóm |
| **Học hỏi** | Quan sát người học, Sprint Review hoặc vòng phản hồi phù hợp | Product Backlog được điều chỉnh bằng bằng chứng |

### Giới hạn số thay đổi cùng lúc

Thay đồng thời tất cả công cụ, cấu trúc team, công nghệ và chính sách dễ làm **khó diễn giải kết quả**. Tuy nhiên, cũng đừng thay đổi một nghi thức quá nhỏ đến mức **không thể tác động tới vấn đề thực**.

Một lựa chọn cân bằng là **một gói thực hành có cơ chế liên quan rõ**, ví dụ: làm rõ backlog + chia lát cắt + CI sớm để giảm thời gian từ yêu cầu tới Increment. Ghi những thay đổi đi cùng nhau và không tuyên bố một thực hành đơn lẻ gây ra toàn bộ kết quả nếu không có thiết kế kiểm chứng phù hợp.

## 11. Chọn kiểu thử nghiệm: không mọi thay đổi đều “safe to fail”

**Safe-to-fail experiment** là một thử nghiệm có giới hạn để nếu giả thuyết sai, tổ chức vẫn kiểm soát được hậu quả và thu được hiểu biết. “Safe to fail” **không đồng nghĩa** được phép làm hỏng dữ liệu người dùng, bỏ bảo mật hoặc bỏ qua nghĩa vụ pháp lý.

### Phân loại mức rủi ro

| Mức | Ví dụ thay đổi | Cách kiểm soát |
| --- | --- | --- |
| **Dễ đảo ngược, tác động nhỏ** | Thử board theo dòng việc, đổi format refinement | Có baseline, trao đổi và xem lại |
| **Tác động workflow liên nhóm** | Đổi chính sách kéo việc/WIP, đổi cách nhận yêu cầu khẩn | Thống nhất quyền quyết định, xem tải và phụ thuộc |
| **Tác động hành vi người dùng** | Thay đổi thông báo trạng thái lưu | Đáp ứng DoD, test và rollout phù hợp |
| **Tác động dữ liệu/kiến trúc khó đảo ngược** | Migration schema tiến độ, đổi định danh tài khoản | Nghiên cứu, test chuyển đổi, sao lưu/phục hồi và quyền phê duyệt phù hợp |
| **Rủi ro bảo mật hoặc an toàn nghiêm trọng** | Bỏ kiểm soát quyền để tăng tốc | Không triển khai như một pilot; phải bảo vệ yêu cầu bắt buộc |

### Cần kế hoạch ứng phó

~~~text
THỬ NGHIỆM:
  Cho một nhóm người học đủ điều kiện dùng hành trình tiếp tục mới.

ĐIỀU KIỆN BẬT:
  Increment đạt DoD, test quan trọng và telemetry hợp lệ.

GUARDRAILS:
  Không để lộ dữ liệu, không báo lưu thành công sai,
  độ tin cậy và hiệu năng theo tiêu chuẩn đã thống nhất.

KÊNH PHÁT HIỆN:
  Monitoring, lỗi ứng dụng, phản hồi hỗ trợ, kiểm chứng dữ liệu.

QUYỀN DỪNG:
  Vai trò xử lý sự cố/rollout theo chính sách hiện có.

KHI CÓ SỰ CỐ:
  Giảm phạm vi/tắt khả năng khi phù hợp;
  bảo vệ, khôi phục dữ liệu theo quy trình,
  thông báo và điều tra nguyên nhân.

ĐIỀU KIỆN MỞ RỘNG:
  Guardrails đạt và có đủ bằng chứng cho quyết định tiếp.
~~~

**Tắt feature flag không tự khôi phục dữ liệu đã ghi sai.** Chọn cách phát hành an toàn phải tính tới những thay đổi khó đảo ngược và khả năng phục hồi, không chỉ nút on/off.

## 12. Baseline: biết “trước khi thử” trông thế nào

Nếu không có baseline, một báo cáo “cycle time sau pilot là 6 ngày” không cho biết đây là cải thiện hay suy giảm. Baseline cần **đủ nhất quán** về đơn vị đo, workflow và khoảng quan sát.

### Những tín hiệu nên ghi trước pilot

| Góc nhìn | Ví dụ baseline | Điều kiện đọc số |
| --- | --- | --- |
| **Product outcome** | Tỷ lệ người đủ điều kiện quay lại đúng tiến độ | Cohort, cửa sổ 7 ngày, exposure và cách xác minh |
| **Flow** | Phân phối cycle time, throughput, WIP, Work Item Age | Started/Done, loại công việc, ngày lịch/ngày làm việc |
| **Chờ và phụ thuộc** | Thời gian chờ làm rõ, review, môi trường, release | Nguyên nhân blocked và điểm chuyển giao |
| **Chất lượng** | Lỗi sau phát hành, lỗi hồi quy, severity | Mức sử dụng và khả năng phát hiện lỗi |
| **Độ tin cậy** | Tỷ lệ lưu/đọc thành công, sự cố và thời gian phục hồi | Hợp đồng kỹ thuật, SLI/SLO phù hợp |
| **Bền vững** | Gánh nặng on-call, interrupt, làm ngoài giờ lặp lại | Dữ liệu tổng hợp, tự nguyện và tôn trọng riêng tư |
| **Tốc độ học** | Từ nhu cầu đến lúc có phản hồi sử dụng đáng tin | Phân biệt release và outcome đủ cửa sổ |

### Không cần dữ liệu “hoàn hảo” để bắt đầu

Nếu công cụ hiện tại không ghi Work Item Age, nhóm có thể **định nghĩa từ hôm nay** và quan sát trong những Sprint đầu, ghi rõ không có baseline lịch sử. Không được tự dựng con số để lấp khoảng trống.

Khi dữ liệu ít, dùng thêm **bản đồ hành trình, phỏng vấn, phân tích incident và ví dụ nghiệp vụ**. Nêu mức bất định thay vì chờ một hệ analytics khổng lồ mới bắt đầu học.

### Đừng đo nhầm điểm kết thúc

| Đại lượng | Ranh giới ví dụ |
| --- | --- |
| **Cycle time của PBI** | Từ khi vào “Đang thực hiện” tới khi đáp ứng DoD |
| **Delivery lead time** | Từ khi nhu cầu được chọn/ưu tiên tới lúc có Increment sử dụng được |
| **Time to release** | Từ lúc chọn thay đổi tới lúc bật cho người dùng thực |
| **Time to feedback** | Từ lúc giả thuyết hình thành tới khi có dữ liệu/nhận xét đủ dùng |
| **Outcome window** | Ví dụ bảy ngày sau khi người đủ điều kiện được tiếp xúc |

Không dùng một từ “lead time” cho cả năm phép đo rồi so sánh tùy ý. **Thống nhất mốc bắt đầu, kết thúc và đối tượng** trước.

## 13. Bộ chỉ số pilot nhỏ nhưng cân bằng

Không cần bắt nhóm theo dõi hàng chục KPI. Một bộ vài tín hiệu có thể trả lời ba câu hỏi: **người dùng có hưởng lợi không, nhóm có giao giá trị sớm hơn không, chất lượng và nhịp làm việc có bền vững không?**

### Mẫu scorecard

| Loại | Chỉ số/câu hỏi | Vai trò |
| --- | --- | --- |
| **Outcome chính** | Tỷ lệ học viên đủ điều kiện tiếp tục thành công trong 7 ngày | Kiểm tra giá trị |
| **Flow chính** | End-to-end lead time hoặc cycle time của lát cắt cùng loại | Kiểm tra tốc độ dòng việc |
| **Phụ thuộc** | Thời gian blocked và Work Item Age | Tìm cơ chế gây chậm |
| **Chất lượng** | Lỗi mất tiến độ, lỗi hồi quy, test hợp đồng | Guardrail và chẩn đoán |
| **Độ tin cậy** | SLI lưu/đọc, incident severity, recovery time | Guardrail vận hành |
| **Nhịp bền vững** | Interrupt/on-call, feedback tự nguyện về tải công việc | Tránh tăng tốc bằng làm thêm giờ |
| **Học hỏi** | Thời gian tới phản hồi, số quyết định backlog có bằng chứng | Kiểm tra năng lực thích ứng |

### Phân biệt metric kết quả và metric hoạt động

- **“Đã tổ chức 10 Sprint Planning”** là dấu hiệu hoạt động, không chứng minh có Sprint Goal hữu ích.
- **“Đã hoàn thành 150 story points”** là dữ liệu ước lượng/hoàn tất nội bộ, không phải giá trị người dùng.
- **“Tỷ lệ tiếp tục học tăng và lỗi không tăng”** là dấu hiệu kết quả có ích nếu đo đúng và hiểu giới hạn.
- **“Câu hỏi API được làm rõ sớm, thời gian blocked giảm”** có thể giải thích một cơ chế cải tiến.

**Không biến outcome thành KPI thưởng phạt cá nhân.** Tối ưu hành vi qua chỉ số cứng có thể dẫn tới thay cách đếm hoặc giấu lỗi, làm thí điểm mất khả năng học.

## 14. Định nghĩa một chỉ số để các bên hiểu giống nhau

Một **metric contract** giúp Product Owner, Developers, vận hành và stakeholder tránh tranh luận chỉ vì mỗi người dùng mẫu số khác.

### Ví dụ hợp đồng đo “tiếp tục học thành công”

| Trường | Ví dụ |
| --- | --- |
| **Tên** | Successful Resume Within 7 Days |
| **Đơn vị** | Người học đủ điều kiện, không phải lượt bấm |
| **Điều kiện vào cohort** | Có bài chưa hoàn tất trước thời điểm được đưa vào phạm vi quan sát |
| **Tử số** | Số người đủ điều kiện có ít nhất một lần tiếp tục đúng tiến độ được xác nhận trong bảy ngày |
| **Mẫu số** | Tổng số người đủ điều kiện thuộc cohort đã đủ bảy ngày |
| **Bắt đầu quan sát** | Thời điểm vào cohort hoặc phân trải nghiệm đã định trước |
| **Dữ liệu nguồn** | Sự kiện exposure, kết quả đọc/ghi và sự kiện bắt đầu học tiếp |
| **Ngoại lệ** | Chỉ theo các quy tắc loại trừ đã định trước và có lý do |
| **Guardrails** | Lỗi dữ liệu, phân quyền, độ trễ và sự cố ảnh hưởng người dùng |
| **Giới hạn** | Người dùng không được tiếp xúc/telemetry thiếu có thể làm sai lệch phân tích |

Tính:

\[
\text{Tỷ lệ tiếp tục thành công}
=\frac{\text{Số người đủ điều kiện tiếp tục thành công trong 7 ngày}}
{\text{Tổng số người đủ điều kiện trong cohort đầy đủ}}
\times100\%.
\]

**Không tự chọn chỉ những người đã nhấn nút mới làm mẫu số** nếu mục tiêu là đánh giá tác động lên toàn bộ nhóm đủ điều kiện. Khi đó bạn đã bỏ qua người không tìm thấy, không hiểu hoặc không sử dụng tính năng.

### Chất lượng dữ liệu

Các nhóm cần kiểm tra:

1. Event “đã lưu” có đúng chỉ ghi sau xác nhận?
2. Retry, double click hoặc đồng bộ thiết bị có tạo sự kiện trùng?
3. Log từ client có bị thiếu vì mạng hoặc cơ chế chặn tracking?
4. Thời điểm theo múi giờ nào? Sự kiện đến muộn xử lý ra sao?
5. Ai có quyền xem dữ liệu? Có thu thập trường cá nhân không cần thiết?

**Mã định danh giả danh vẫn có thể là dữ liệu cá nhân nếu liên kết ngược được**; phải tuân thủ chính sách quyền riêng tư, mục đích đo, giới hạn truy cập và lưu giữ.

## 15. Từ flow metrics đến bài học về tổ chức công việc

Kanban cung cấp những phép đo hữu ích để hiểu điều gì thực sự thay đổi:

- **WIP (Work in Progress):** Số hạng mục đã bắt đầu nhưng chưa Done.
- **Throughput:** Số hạng mục hoàn thành trong một khoảng, theo đơn vị thống nhất.
- **Cycle time:** Thời gian từ Started tới Done trong workflow.
- **Work Item Age:** Tuổi của một hạng mục đang mở tính từ Started.

### Ví dụ số liệu minh họa

Trước pilot, năm story cùng loại hoàn thành với cycle time **3, 5, 7, 9, 16 ngày**:

- Trung bình = (3 + 5 + 7 + 9 + 16)/5 = **8 ngày**.
- Trung vị = **7 ngày**.
- Story 16 ngày có thể là trường hợp bị chặn cần hiểu sâu hơn.

Sau pilot, năm story hoàn thành trong **3, 4, 5, 6, 7 ngày**:

- Trung bình = **5 ngày**.
- Trung vị = **5 ngày**.

**Có dấu hiệu thời gian hoàn tất trong ví dụ ngắn hơn**, nhưng chỉ **năm mẫu mỗi kỳ** không đủ để kết luận chắc chắn. Cần kiểm tra loại story, cách chia ticket, thay đổi ranh giới Started/Done, năng lực nhóm, sự cố và các hạng mục **chưa hoàn thành đang bị kẹt**.

### Work Item Age giúp thấy việc chưa Done

Nếu có một PBI đã mở **20 ngày** và chưa Done, nó không xuất hiện trong cycle time của những PBI đã hoàn thành. Không được loại nó khỏi thảo luận rồi kết luận “nhóm nhanh hơn”. Cần xem **Work Item Age, blocked time và WIP** trong cùng kỳ.

### Định luật Little như quan hệ trung bình

Với một hệ thống dòng công việc có ranh giới đo đồng nhất và trạng thái đủ ổn định:

\[
\text{WIP trung bình}
=\text{Throughput trung bình}\times\text{Cycle time trung bình}.
\]

Nếu WIP trung bình là **12 hạng mục** và throughput trung bình **3 hạng mục/tuần**, quan hệ tương ứng cycle time trung bình **4 tuần**. Nhưng **giảm WIP limit không bảo đảm throughput giữ nguyên hoặc mọi PBI xong trong bốn tuần**. Đây là quan hệ thống kê có điều kiện, không phải công thức ra cam kết cứng.

## 16. Đo kết quả người dùng mà không nhầm tương quan với nhân quả

Giả sử tỷ lệ học viên đủ điều kiện tiếp tục học tăng từ **42% trước pilot lên 49% sau pilot**. Số liệu này cho thấy **chênh lệch quan sát được 7 điểm phần trăm** theo cùng cách đo, nhưng chưa chứng minh mọi cải thiện do pilot.

Những yếu tố có thể thay đổi cùng lúc:

- Chiến dịch nhắc học, thay đổi học phí hoặc nội dung.
- Mùa thi, kỳ nghỉ hoặc thành phần người học mới.
- Phiên bản ứng dụng và mức tiếp xúc tính năng.
- Sửa công cụ đo hoặc thay cách xác định thành công.
- Một nhóm người dùng tích cực được ưu tiên thí điểm.

### Những mức bằng chứng khác nhau

| Phương pháp | Hữu ích để | Không đủ để |
| --- | --- | --- |
| **Trước/sau** | Thấy thay đổi và đặt giả thuyết | Quy kết nguyên nhân chắc chắn |
| **Phân tích cohort/segment** | Hiểu nhóm nào có khác biệt | Loại hết thiên lệch không quan sát |
| **Phỏng vấn/usability test** | Hiểu cách sử dụng, hiểu lầm, động lực | Suy rộng tỷ lệ toàn thị trường từ ít người |
| **A/B ngẫu nhiên có kiểm soát** | Ước lượng tác động trong điều kiện thiết kế hợp lệ | Tự đảm bảo mọi guardrail hoặc ngoại suy mọi phân khúc |
| **Canary/gradual rollout** | Kiểm soát phạm vi rủi ro khi phát hành | Tự chứng minh nhân quả |
| **Incident/quality analysis** | Kiểm chứng độ tin cậy và nguyên nhân lỗi | Tự đo giá trị sản phẩm dài hạn |

Một pilot chuyển đổi quy trình rất khó **ngẫu nhiên hóa toàn bộ cách làm của một tổ chức**; nhiều thay đổi thường xảy ra cùng lúc. Vì vậy, kết quả nên được diễn giải theo **cơ chế, tính hợp lý, dữ liệu đa nguồn và giới hạn suy rộng**, không tuyên bố tác động nhân quả tuyệt đối từ một biểu đồ.

### Khi kết quả không phù hợp kỳ vọng

Nếu flow cải thiện nhưng người học vẫn không quay lại, đây là **thông tin cần học**, không nhất thiết lý do chấm dứt mọi thực hành. Có thể đội đang giao đúng sản phẩm nhanh hơn nhưng **giải pháp vẫn không chạm nhu cầu**, hoặc cần thời gian/điều kiện tiếp xúc khác. Product Owner cần điều chỉnh giả thuyết giá trị, nhóm kỹ thuật giữ điều đã giúp tăng chất lượng nếu có bằng chứng.

## 17. Thiết kế thời lượng và các vòng học của pilot

Một pilot cần **các vòng đủ ngắn để sửa cách làm trước khi chi phí tích lũy quá lớn**, đồng thời đủ thời gian cho quan sát có ý nghĩa. Không có quy tắc chung “pilot phải đúng 90 ngày” hoặc “chỉ cần hai Sprint”.

### Hai loại thời gian cần tách

1. **Thời gian triển khai cách làm:** Cần để nhóm hiểu quy ước mới, thay đổi workflow, có kiểm thử/CI phù hợp và giao một số lát cắt thực.
2. **Thời gian đo kết quả:** Một outcome như người học quay lại trong 28 ngày **không thể kết luận sau ba ngày**; cần cửa sổ quan sát tương xứng.

Với bài học, ta dùng **ví dụ kế hoạch bốn Sprint, mỗi Sprint hai tuần**, hoàn toàn chỉ là một lịch minh họa. Với Scrum, một Sprint có độ dài **một tháng hoặc ngắn hơn**; pilot có thể dùng nhịp phù hợp thực tế.

### Một lịch pilot minh họa

| Giai đoạn | Trọng tâm | Bằng chứng/đầu ra cần có |
| --- | --- | --- |
| **Trước Sprint 1** | Chốt vấn đề, nhóm, quyền, phạm vi và baseline | Pilot charter ngắn, Product Goal, metric contract, guardrails |
| **Sprint 1** | Tạo lát cắt nhỏ, kiểm tra backlog và môi trường tích hợp | Increment đạt DoD hoặc blocker có nguyên nhân và người tháo |
| **Sprint 2** | Phản hồi sớm, làm rõ ví dụ, cải thiện CI/WIP nếu cần | Thời gian chờ, lỗi và những điều đã học |
| **Sprint 3** | Tích hợp và phát hành có kiểm soát theo điều kiện an toàn | Phản hồi người dùng, mức tiếp xúc, quality signals |
| **Sprint 4** | Kiểm tra kết quả/các hạn chế, quyết định điều chỉnh | Baseline so sánh có bối cảnh, quyết định vòng tiếp |
| **Sau pilot khi cần** | Hoàn tất cửa sổ outcome dài hơn | Kết luận bổ sung, không tự đóng câu hỏi chưa đủ dữ liệu |

**Không ép mọi mục tiêu phải nằm gọn trong bốn Sprint.** Nếu Sprint 1 gặp sự cố bảo mật, cần ưu tiên xử lý ngay; nếu outcome cần 28 ngày, báo cáo cuối pilot có thể nêu trạng thái **chưa đủ bằng chứng** và thời điểm xem tiếp, không bịa kết luận.

### Ba mốc kiểm tra

- **Điều kiện an toàn:** Có phải dừng ngay để bảo vệ người dùng hoặc nhân viên?
- **Điều kiện học hỏi:** Có đang thu được dữ liệu đúng để kiểm tra giả thuyết?
- **Điều kiện thay đổi phạm vi:** Có nên điều chỉnh backlog/lát cắt khi hiểu biết mới xuất hiện?

Một pilot có tính thích ứng nên **cho phép thay đổi cách làm và thứ tự công việc khi có bằng chứng**, nhưng vẫn ghi những thay đổi ấy để phân tích sau.

## 18. Vòng phản hồi ở ba cấp

Agile không thể hiện thực chỉ bằng một cuộc họp tổng kết cuối chương trình. Pilot cần **nhịp kiểm tra ở đúng nơi có thông tin và trách nhiệm**, không tạo thêm ba tầng báo cáo.

~~~mermaid
flowchart TD
    A["Nhóm: công việc, test, CI, blocked items"] --> B["Increment và phản hồi người dùng"]
    B --> C["Product Goal, ưu tiên, giả thuyết giá trị"]
    C --> D["Tổ chức: quyền, phụ thuộc, chính sách, năng lực"]
    D --> E["Tháo rào cản / thay đổi điều kiện làm việc"]
    E --> A
    B --> A
    C --> B
~~~

| Cấp học hỏi | Câu hỏi chính | Hành động hợp lý |
| --- | --- | --- |
| **Nhóm/engineering** | Thay đổi nhỏ có đáp ứng DoD, tích hợp và giảm chờ? | TDD/BDD, CI, refactoring, WIP, phối hợp |
| **Sản phẩm/người dùng** | Lát cắt có giá trị, được dùng và tạo outcome? | Điều chỉnh Product Backlog, ví dụ, rollout |
| **Tổ chức** | Chính sách hay cơ cấu nào đang cản khả năng giao/học? | Trao quyền, thay phê duyệt, đầu tư năng lực, giảm phụ thuộc |

### Phân biệt thông tin và quyết định

Một dashboard cho thấy Work Item Age tăng chỉ là **tín hiệu cần điều tra**, không tự động chứng minh nhóm thiếu nỗ lực. Product Owner có thể thay thứ tự Product Backlog dựa trên giá trị; Developers có thể thay cách thực hiện; lãnh đạo có thể phải giải quyết rào cản mà team không có quyền.

**Không biến mọi câu hỏi thành quyết định của một “ban chuyển đổi Agile”**. Nếu nhóm phải xin phép hội đồng để thay cách refinement hoặc review code ít rủi ro, pilot có thể tạo thêm hàng đợi thay vì tăng khả năng thích ứng.

## 19. Nếu chọn Scrum: thí điểm để thực hành minh bạch, kiểm tra và thích ứng

Scrum có cấu trúc accountabilities, events, artifacts và commitments. Áp dụng Scrum có ý nghĩa khi nhóm có **một sản phẩm hoặc phạm vi sản phẩm rõ, Product Goal có giá trị và cần phát triển Increment theo vòng lặp**.

### Accountabilities không phải chức danh hình thức

| Accountability | Trong pilot cần kiểm chứng điều gì? | Phản mẫu |
| --- | --- | --- |
| **Product Owner** | Có thể tối đa hóa giá trị, quản lý Product Backlog và kết nối phản hồi stakeholder? | Chỉ viết ticket do nhiều cấp quản lý giao |
| **Developers** | Tự quản kế hoạch triển khai, tạo Increment đạt DoD và điều chỉnh theo Sprint Goal? | Nhận phân công task chi tiết từ quản lý hằng ngày |
| **Scrum Master** | Hỗ trợ hiểu Scrum, tăng hiệu quả Scrum Team, tháo trở ngại phù hợp? | Chỉ kiểm đếm attendance hoặc làm thư ký họp |

### Events có mục đích

| Event | Câu hỏi học hỏi ở pilot |
| --- | --- |
| **Sprint Planning** | Sprint Goal có liên kết với Product Goal và năng lực thực không? |
| **Daily Scrum** | Developers có kiểm tra tiến độ hướng Sprint Goal và điều chỉnh kế hoạch không? |
| **Sprint Review** | Scrum Team và stakeholder có kiểm tra Increment và điều chỉnh hướng sản phẩm bằng phản hồi không? |
| **Sprint Retrospective** | Nhóm có cải thiện chất lượng và hiệu quả, có thử nghiệm cụ thể không? |

**Definition of Done** bảo vệ việc gọi Increment là hoàn thành. Một PBI code xong nhưng chưa kiểm thử/tích hợp theo DoD **không nên được tính là Increment hoàn tất** chỉ để Sprint chart đẹp.

### Không biến pilot Scrum thành học thuộc checklist

Đội có thể tuân thủ thời điểm và cấu trúc event nhưng không đưa bất kỳ câu hỏi khó nào vào Sprint Review, hoặc không có quyền thay đổi backlog. Trong trường hợp đó, **việc học hỏi chưa xảy ra** dù lịch họp rất đều.

Scrum Guide 2020 nêu timebox tối đa cho Sprint một tháng: Sprint Planning **8 giờ**, Sprint Review **4 giờ**, Sprint Retrospective **3 giờ**, Daily Scrum **15 phút**. Chúng **không phải thời lượng bắt buộc dùng hết**, cũng không thay mục đích của từng event.

## 20. Nếu chọn Kanban: pilot cho luồng yêu cầu liên tục và nút thắt

Với nhóm vận hành hoặc hỗ trợ nhiều dòng yêu cầu đến liên tục, **Kanban** có thể là hướng phù hợp hơn việc ép mọi yêu cầu vào cam kết Sprint cố định. Kanban cũng có thể bổ trợ Scrum.

### Một pilot Kanban thực dụng

1. **Định nghĩa workflow hiện tại**, từ lúc nhận yêu cầu đủ điều kiện tới Done.
2. **Trực quan hóa toàn bộ công việc** bao gồm sự cố, lỗi, hỗ trợ và cải tiến.
3. Nêu **chính sách kéo công việc, mức ưu tiên, điều kiện expedite và tiêu chí Done**.
4. Đo **WIP, throughput, cycle time, Work Item Age** và thời gian blocked.
5. Thử giới hạn WIP phù hợp; hỗ trợ công việc gần Done trước khi mở thêm việc.
6. Kiểm tra chất lượng và nhịp bền vững, không tối ưu flow bằng việc giấu ticket lỗi.
7. Xem **SLE (Service Level Expectation)** theo dữ liệu lịch sử, ghi phạm vi và độ tin cậy.

### Ví dụ

Một nhóm xử lý yêu cầu vận hành đang có 18 hạng mục mở và throughput 3/tuần. Trong điều kiện **tương đối ổn định, cùng loại đơn vị**, quan hệ theo Little's Law tương ứng cycle time trung bình **6 tuần**.

Nếu pilot giảm WIP còn 12 và throughput **vẫn giữ 3/tuần**, cycle time trung bình tương ứng **4 tuần**. Đây là **một phép minh họa có điều kiện**, không chứng minh giới hạn WIP sẽ tự động giữ throughput hoặc mọi yêu cầu hoàn tất sau bốn tuần.

### Giữ kiểm tra chất lượng

Một dòng vận hành có thể giảm thời gian đóng ticket bằng cách chuyển lỗi sang trạng thái “chờ người khác” hoặc đóng trước khi kiểm chứng. Điều này **không phải flow thực sự tốt hơn**. Hãy giữ ranh giới Done và cách đếm lỗi minh bạch.

## 21. XP và năng lực kỹ thuật không thể bị bỏ quên

Chuyển đổi Agile thường thất bại khi chỉ đổi các event mà **năng lực tạo Increment đáng tin cậy** vẫn yếu. Những thực hành XP có thể hỗ trợ:

| Thực hành | Cơ chế tác động | Tín hiệu có thể quan sát |
| --- | --- | --- |
| **TDD** | Kiểm thử hành vi nhỏ trước/sát lúc hiện thực, tạo phản hồi nhanh | Lỗi hồi quy, khả năng refactor an toàn |
| **BDD/Example Mapping** | Nghiệp vụ, phát triển và kiểm thử làm rõ ví dụ | Ít làm lại vì hiểu sai, acceptance rõ |
| **Continuous Integration** | Tích hợp thay đổi nhỏ thường xuyên | Lỗi tích hợp được phát hiện sớm |
| **Refactoring** | Giữ cấu trúc dễ hiểu và dễ thay đổi | Chi phí sửa/rủi ro hồi quy giảm theo bối cảnh |
| **Pair programming** | Phản biện thiết kế, chia sẻ hiểu biết | Bớt phụ thuộc chuyên gia, phát hiện sai sớm |
| **Small releases** | Giảm lô thay đổi, nhận phản hồi người dùng nhanh hơn | Time to feedback, sự cố và khả năng phục hồi |

**TDD không tự động làm mọi thứ đúng**; test phải có assertion tốt, ranh giới tích hợp và các yêu cầu chất lượng khác phải được bảo vệ. **CI xanh cũng không tự chứng minh** dữ liệu đã lưu bền vững, phân quyền đúng hoặc người dùng đã đạt outcome.

### Có nên đổi toàn bộ công nghệ trong pilot?

Không nhất thiết. Nếu tổ chức đang dùng Java và một hệ thống CI phù hợp, thường có thể **bắt đầu bằng cải thiện kiểm thử, chia lát cắt và hợp đồng tích hợp** thay vì thay stack công nghệ chỉ để “trở nên Agile”. Nếu công cụ hiện tại thật sự là nút thắt, hãy ghi giả thuyết kỹ thuật và thử nghiệm có giới hạn.

## 22. Coaching, vai trò thay đổi và an toàn tâm lý

Một nhóm có thể biết Scrum Guide nhưng vẫn chưa quen **đưa câu hỏi chưa rõ lên bàn, tự quản quyết định kỹ thuật và cùng chịu trách nhiệm Increment**. Coaching có ích khi giúp mọi người **nhìn thấy vấn đề và thực hành năng lực mới**, không phải đi kiểm tra ai “đúng Agile” nhất.

### Những hình thức hỗ trợ

- **Teaching:** Giải thích vai trò, Scrum events, Kanban metrics hoặc quy tắc kiểm thử khi cần.
- **Mentoring:** Chia sẻ kinh nghiệm và ví dụ lựa chọn thực hành từ bối cảnh tương tự.
- **Coaching:** Đặt câu hỏi giúp nhóm tự phân tích hệ thống, quyết định và học từ phản hồi.
- **Facilitation:** Giúp thảo luận có mục đích, đủ góc nhìn và ra quyết định đúng trách nhiệm.
- **Technical enablement:** Ghép cặp về CI, BDD, test và release engineering, không chỉ dạy kỹ năng họp.

### Tránh biến thí điểm thành cuộc thi thành tích

- Không dùng **mức độ “Agile maturity” mơ hồ** để đánh giá đạo đức hoặc phẩm chất cá nhân.
- Không chấm điểm người ít phát biểu trong Retrospective là thiếu hợp tác.
- Không che sự cố để giữ chỉ số pilot đẹp.
- Không yêu cầu mọi người cung cấp thông tin sức khỏe hoặc đời sống riêng để giải thích quá tải.
- Không tự động quay lại mọi cuộc họp, đặc biệt Retrospective, khi chưa làm rõ mục đích, quyền và chính sách.

**An toàn tâm lý không đồng nghĩa né trách nhiệm.** Nhóm vẫn cần đáp ứng Definition of Done, kiểm tra dữ liệu, nói thật về chất lượng và xử lý rủi ro. Nhưng có thể báo “thử nghiệm chưa hiệu quả” mà không bị trừng phạt thì tổ chức mới học được.

## 23. Lãnh đạo, stakeholder và các nhóm ngoài pilot

Một pilot không tồn tại trong chân không. Product Owner có thể cần stakeholder xác nhận giá trị, Developers cần môi trường tích hợp, bộ phận an toàn cần bảo vệ rủi ro, còn lãnh đạo cần hiểu pilot **đang kiểm chứng điều gì**.

### Bản đồ ảnh hưởng

| Bên liên quan | Họ có thể đóng góp gì? | Điều không nên làm |
| --- | --- | --- |
| **Người dùng/đại diện nghiệp vụ** | Vấn đề thật, phản hồi, kiểm chứng giải pháp | Chỉ xuất hiện trong buổi khởi động |
| **Product Owner** | Product Goal, thứ tự Product Backlog, quyết định trade-off giá trị | Nhận danh sách ưu tiên đối kháng từ mọi sếp mà không có quyền lựa chọn |
| **Developers và test/engineering** | Cách làm, DoD, CI, an toàn, rủi ro kỹ thuật | Bị giao task theo giờ từ một ban chuyển đổi |
| **Scrum Master/coach nếu áp dụng** | Hỗ trợ minh bạch, tự quản, cải tiến và tháo blocker | Làm người kiểm soát tuân thủ nghi thức |
| **Vận hành/bảo mật/dữ liệu** | Quan sát, khả năng phục hồi, tiêu chuẩn bắt buộc | Phê duyệt thủ công mọi thay đổi nhỏ không có rủi ro |
| **Lãnh đạo** | Trao quyền, bảo vệ năng lực, giải quyết ràng buộc tổ chức | Chỉ yêu cầu “tăng velocity” |
| **Nhóm phụ thuộc** | Hợp đồng API, dịch vụ dùng chung và cam kết hỗ trợ | Trở thành hàng đợi vô hạn không có người chịu trách nhiệm |

### Một thỏa thuận hỗ trợ tối thiểu

~~~text
PILOT:
  Thử cải thiện dòng phát triển lát cắt tiếp tục học.

NGƯỜI ĐIỀU PHỐI VỀ GIÁ TRỊ:
  Product Owner chịu trách nhiệm Product Backlog.

QUYỀN CỦA DEVELOPERS:
  Tổ chức thực hiện, kiểm thử, tích hợp và cải tiến kỹ thuật
  trong các tiêu chuẩn an toàn đã thống nhất.

NGƯỜI THÁO RÀO CẢN TỔ CHỨC:
  Vai trò lãnh đạo được giao xử lý quyền release,
  môi trường và xung đột ưu tiên ngoài team.

STAKHOLDER:
  Cung cấp phản hồi đủ sớm và tham gia kiểm tra Increment.

ĐIỀU KIỆN DỪNG:
  Theo chính sách sự cố và guardrail về dữ liệu/an toàn.

MỐC XEM LẠI:
  Cuối mỗi vòng ngắn và tổng kết khi đủ bằng chứng.
~~~

Đừng tạo thêm một vai trò **có quyền phủ quyết mọi quyết định kỹ thuật** chỉ để “quản trị Agile”. Mục tiêu là **quyền quyết định rõ và thời gian phản hồi ngắn**, không mở rộng cơ chế phê duyệt.

## 24. Ghi quyết định và thay đổi phạm vi trong suốt pilot

Một pilot thích ứng **không phải kế hoạch đóng băng**, nhưng cũng không có nghĩa đổi mục tiêu hoặc chỉ số mỗi tuần mà không ghi lý do.

### Một bản ghi thay đổi ngắn

~~~text
NGÀY / VÒNG:
  Sprint 2.

BẰNG CHỨNG:
  Nhiều người dùng không hiểu thông báo "Đang đồng bộ";
  ghi nhận lỗi khi mạng chập chờn.

GIẢ THUYẾT BỊ THÁCH THỨC:
  Chỉ có thể tăng giá trị bằng việc thêm offline đa thiết bị.

QUYẾT ĐỊNH:
  Ưu tiên làm rõ trạng thái lưu và kiểm chứng độ tin cậy;
  chưa mở rộng phạm vi offline.

ĐIỀU GIỮ NGUYÊN:
  Product Goal, tiêu chuẩn DoD và guardrail dữ liệu.

ĐIỀU CẦN ĐO TIẾP:
  Tỷ lệ khôi phục đúng, sự cố lưu và phản hồi người học.

NGƯỜI CHỊU TRÁCH NHIỆM:
  Product Owner điều chỉnh backlog;
  Developers chọn cách kiểm chứng và hiện thực.
~~~

Khi tổng kết, có thể phân biệt kết quả đến từ **lát cắt sản phẩm thay đổi**, **workflow thay đổi**, **điều kiện tổ chức thay đổi** hay yếu tố bên ngoài. Thí điểm không cần chứng minh tác động của từng thực hành riêng lẻ bằng một con số chính xác nếu thiết kế không cho phép.

### Tránh hai cực đoan

- **Không bao giờ đổi phạm vi:** Tiếp tục xây đúng kế hoạch dù người dùng phản hồi nhu cầu khác.
- **Đổi không có kỷ luật:** Mỗi yêu cầu stakeholder mới lập tức thay giả thuyết, metric và năng lực, khiến nhóm không còn học được gì.

Giữ **Product Goal và tiêu chuẩn chất lượng** làm điểm tựa; điều chỉnh cách đi theo phản hồi, ghi trade-off và cập nhật dự báo.

## 25. Case study xuyên suốt: chọn pilot cho nền tảng học trực tuyến

**Bối cảnh giả định:** Một tổ chức có ba nhóm ứng viên:

- **Nhóm A — phát triển tính năng học:** Phát triển hành trình lưu/khôi phục tiến độ. Có Product Owner hiểu người học, hệ thống đang được sử dụng, CI cơ bản, nhưng phải chờ API và môi trường tích hợp.
- **Nhóm B — vận hành nền tảng:** Tiếp nhận incident, yêu cầu hỗ trợ và thay đổi hạ tầng liên tục. Có đo sự cố và khả năng phục hồi, nhưng công việc khó chia thành Sprint Goal ổn định.
- **Nhóm C — migration dữ liệu:** Thực hiện chuyển đổi dữ liệu quy mô lớn với một số quyết định khó đảo ngược. Quyền phê duyệt, bảo mật và phương án phục hồi chưa được làm rõ.

Ban lãnh đạo muốn sau hai tháng biết **nên thay đổi cách tổ chức công việc như thế nào để người học nhận giá trị nhanh hơn mà vẫn an toàn**.

### 25.1. Sai lầm trong đề xuất ban đầu

Một kế hoạch đề xuất:

> “Chọn nhóm A vì họ giỏi nhất, tổ chức đủ bốn Scrum event, mua phần mềm quản lý mới, yêu cầu velocity tăng 30% sau bốn Sprint. Nếu đạt, triển khai Scrum toàn công ty.”

Đề xuất này thiếu:

- **Vấn đề người học** và outcome cần cải thiện.
- Đơn vị đo giá trị thay cho story points.
- Sự khác biệt giữa nhóm A với B/C.
- Cơ chế giải quyết chờ API và môi trường.
- Guardrail chất lượng và quyền dừng.
- Điều kiện xác định nên giữ, sửa hoặc dừng cách làm.

**Velocity tăng 30% cũng không chứng minh hiệu quả Agile tăng 30%**; points là ước lượng tương đối theo quy ước đội, không phải năng suất hoặc giá trị chuẩn hóa.

### 25.2. Chọn nhóm A có điều kiện

Nhóm A được chọn làm **pilot ban đầu về phát triển sản phẩm tăng dần**, không phải vì “dễ thắng nhất” mà vì có:

1. **Hành trình người dùng thật** có vấn đề cần giải quyết.
2. **Khả năng tạo lát cắt end-to-end** nếu ranh giới API được hỗ trợ.
3. **Product Owner** có thể xác nhận ưu tiên và phản hồi.
4. **Dữ liệu và cách thử** trong phạm vi người dùng phù hợp.
5. **Điều kiện chất lượng** có thể kiểm chứng với CI/test hiện có được cải tiến.
6. **Phụ thuộc điển hình** đủ để học về rào cản tổ chức, không phải môi trường được dàn dựng hoàn hảo.

Điều kiện bắt đầu: lãnh đạo thống nhất **đường tháo blocker môi trường tích hợp**, giảm yêu cầu chen ngang không có ưu tiên rõ, và không dùng velocity để đánh giá cá nhân.

Nhóm B chưa bị đánh giá là “ít Agile hơn”: họ có thể được xem xét cho **một pilot Kanban riêng** về WIP, tuổi yêu cầu, incident và độ tin cậy. Nhóm C cần làm rõ **phương án migration an toàn** trước khi dùng làm nơi thử thay đổi quy trình có tác động dữ liệu lớn.

### 25.3. Pilot charter một trang

~~~text
TÊN:
  Học nhanh về cách giao cải tiến lưu tiến độ đáng tin cậy.

ĐỘI THÍ ĐIỂM:
  Nhóm phát triển tính năng học và những người phụ thuộc
  cần thiết ở ranh giới xác thực, dữ liệu, môi trường.

PRODUCT GOAL:
  Học viên quay lại bài đang học mà không mất tiến độ.

VẤN ĐỀ HIỆN TẠI:
  Nhu cầu chờ làm rõ và tích hợp; Increment tới người học muộn.

GIẢ THUYẾT:
  Backlog ưu tiên theo giá trị + lát cắt dọc + CI/test tích hợp
  giúp giảm chờ và nhận phản hồi sớm hơn.

PHẠM VI:
  Lưu/khôi phục trên cùng tài khoản, có kết nối,
  trạng thái lưu đúng, quyền truy cập được bảo vệ.

CHƯA GỒM:
  Đồng bộ offline đa thiết bị và thay toàn bộ nền tảng dữ liệu.

CHỈ SỐ CHÍNH:
  End-to-end time to feedback của lát cắt tương tự,
  tỷ lệ tiếp tục học thành công ở cohort đủ điều kiện.

GUARDRAILS:
  Lỗi mất dữ liệu, truy cập trái phép, độ tin cậy,
  gánh nặng trực sự cố/làm ngoài giờ.

NGƯỜI HỖ TRỢ:
  Product Owner về giá trị; Developers về cách thực hiện;
  người có thẩm quyền tháo rào cản tổ chức;
  coaching/engineering support theo nhu cầu.

NHỊP HỌC:
  Kiểm tra mỗi Sprint; tổng kết sau bốn Sprint minh họa;
  đánh giá outcome dài hơn khi đủ cửa sổ.

QUYẾT ĐỊNH CÓ THỂ CÓ:
  Giữ, điều chỉnh, mở rộng có điều kiện, dừng hoặc thử khác.
~~~

### 25.4. Một baseline giả định

Giả sử đội có dữ liệu cho những lát cắt **tương đối cùng loại**, với ranh giới đo nhất quán:

| Tín hiệu | Baseline | Ý nghĩa |
| --- | ---: | --- |
| End-to-end delivery lead time điển hình theo mẫu quan sát | 24 ngày lịch | Cần xem phân phối và biến thiên, không chỉ một số |
| Thời gian chờ tích hợp trong một lát cắt mẫu | 8 ngày | Có dấu hiệu nút thắt |
| Số PBI đang làm (WIP) trung bình | 11 | Có thể quá nhiều so với năng lực hoàn tất |
| Tỷ lệ học viên đủ điều kiện tiếp tục thành công | 42% | Chỉ số outcome, cần cohort/cửa sổ rõ |
| Số lỗi sau phát hành mức trung bình trở lên trong kỳ | 7 | Cần xem độ nghiêm trọng và mức sử dụng |
| Sự cố phải xử lý ngoài giờ trong kỳ | 5 | Tín hiệu tải vận hành, không dùng để phạt người ứng cứu |

Số liệu trên không tự giải thích nguyên nhân. Nhóm bổ sung value stream map và phỏng vấn người liên quan để hiểu **những khoảng chờ thật**.

### 25.5. Sprint 1: học cách tạo một lát cắt đúng

Nhóm:

- Làm rõ user story cùng Product Owner qua **ví dụ nghiệp vụ**.
- Viết test cho **không báo lưu thành công khi chưa xác nhận**.
- Tích hợp đọc/ghi với kiểm soát quyền và dữ liệu mẫu an toàn.
- Nhận diện API contract đang thiếu định nghĩa trạng thái pending.
- Không mở thêm nhiều PBI khi một lát cắt gần Done đang chờ tích hợp.

Một kết quả có thể là **chưa đạt DoD** vì hợp đồng API chưa rõ. Đó không phải dấu hiệu nên “đánh dấu Done để báo cáo đẹp”; cần ghi blocker, quyền quyết định và tác động để tổ chức tháo.

### 25.6. Sprint 2: học về phụ thuộc và phản hồi kỹ thuật

Nhóm thử:

- Một nguồn Product Backlog có thứ tự và yêu cầu rõ.
- Contract tests giữa UI và API.
- Ghép cặp giữa người nắm hai ranh giới kỹ thuật.
- CI chạy thường xuyên khi có thay đổi nhỏ.
- Chia lát cắt để kiểm thử end-to-end sớm hơn.

Nhóm đo **thời gian blocked, Work Item Age và lỗi tích hợp** chứ không chỉ số build đã chạy. Nếu môi trường chung vẫn chờ nhiều ngày, người được giao hỗ trợ tổ chức phải cùng giải quyết; pilot không thể tự “tăng động lực” để vượt một quyền truy cập bị khóa.

### 25.7. Sprint 3: có Increment đáng tin và phản hồi người học

Khi đủ DoD, nhóm phát hành thí điểm theo chính sách an toàn và xác minh:

- Người học có thật sự tiếp xúc với tính năng không.
- Trạng thái lưu thể hiện đúng, kể cả timeout hoặc phản hồi muộn.
- Tỷ lệ khôi phục đúng, sự cố và dữ liệu đo lường có đáng tin không.
- Học viên thấy thông điệp có dễ hiểu hay không.

Nếu lỗi dữ liệu vượt ngưỡng an toàn, nhóm **dừng/thu hẹp và điều tra theo quy trình**, không chạy tiếp chỉ để có “pilot bốn Sprint đẹp”.

### 25.8. Sprint 4: xem lại và chọn bước kế tiếp

Giả sử sau nhiều lát cắt, dữ liệu minh họa được ghi:

| Tín hiệu | Trước | Sau | Cách đọc thận trọng |
| --- | ---: | ---: | --- |
| Delivery lead time điển hình cùng định nghĩa | 24 ngày | 16 ngày | Dấu hiệu tốc độ giao tốt hơn, cần xem phân phối |
| Chờ tích hợp trong lát cắt mẫu | 8 ngày | 3 ngày | Có thể là cơ chế cải thiện quan trọng |
| WIP trung bình | 11 | 7 | Có dấu hiệu ít việc dở hơn |
| Tỷ lệ học viên tiếp tục thành công | 42% | 47% | Chênh 5 điểm phần trăm; chưa quy kết nhân quả |
| Lỗi sau phát hành mức trung bình trở lên | 7 | 5 | Cần so mức tiếp xúc, severity và ghi nhận |
| Sự cố xử lý ngoài giờ | 5 | 3 | Cần xem ảnh hưởng và cách ghi số liệu |

**Không thể kết luận tất cả chuyển biến là do Scrum hoặc CI**. Có thể cùng lúc nhóm làm loại story dễ hơn, môi trường ổn định hơn hoặc kỳ học thay đổi. Nhưng nhóm có bằng chứng để hỏi tiếp **điều kiện nào đã làm giảm chờ và điều gì vẫn bất định**.

### 25.9. Kết luận hợp lý cho case study

Một báo cáo tốt có thể nói:

> “Trong phạm vi giả định, nhóm đã thử phát triển lát cắt dọc và tích hợp sớm trong công việc thật. Các chỉ số flow có dấu hiệu tốt hơn, chất lượng không có tín hiệu suy giảm theo cách đo hiện tại, outcome người học có hướng tích cực nhưng cần xác minh thêm. Rào cản cần giải quyết tiếp là quyền release và dữ liệu phản hồi sau sử dụng. Chúng tôi đề xuất duy trì các thực hành giúp giảm chờ, quan sát thêm và thử trong một bối cảnh tương tự trước khi mở rộng.”

**Bài học:** Thí điểm thành công không nhất thiết chứng minh mọi chỉ số đều tăng. Nó cần **giúp tổ chức đưa ra quyết định tiếp theo tốt hơn từ bằng chứng**, bao gồm điều chưa biết và điều kiện áp dụng.

## 26. Đánh giá pilot sau khi đã có kết quả: không chỉ “đạt hay trượt”

Một thí điểm cần trả lời **mình đã học gì** trước khi quyết định nhân rộng. Có thể dùng một ma trận:

| Tình trạng | Diễn giải | Hướng quyết định |
| --- | --- | --- |
| Outcome cải thiện, flow tốt hơn, guardrails đạt và đo lường đủ tin | Dấu hiệu phù hợp để tiếp tục | Giữ, mở rộng từng bước tới bối cảnh tương tự |
| Flow tốt hơn nhưng outcome chưa đổi | Có thể giải pháp sản phẩm chưa đúng, exposure thấp hoặc cửa sổ ngắn | Giữ cải tiến flow có ích, sửa giả thuyết giá trị |
| Outcome tăng nhưng lỗi hoặc gánh nặng on-call vượt guardrail | Giá trị tổng thể có thể bị tổn hại | Dừng/thu hẹp thay đổi gây hại, khắc phục và kiểm chứng |
| Kết quả chưa rõ, dữ liệu thiếu | Chưa đủ cơ sở kết luận | Sửa instrumentation, quan sát thêm với giới hạn rõ |
| Bị chặn chủ yếu do chính sách ngoài nhóm | Pilot đang kiểm chứng rào cản tổ chức | Lãnh đạo sửa điều kiện, đừng đổ lỗi nhóm |
| Thực hành không phù hợp loại việc | Ví dụ Sprint Goal cố định cho dòng incident liên tục | Cân nhắc Kanban/thực hành khác phù hợp hơn |
| Đã học đủ rằng một giả thuyết sai | Tạo được kiến thức để tránh đầu tư sai | Kết thúc hoặc chuyển hướng có lý do |

### Bảy câu hỏi tổng kết

1. **Giả thuyết nào được củng cố hoặc bị thách thức?** Phân biệt điều đã quan sát và cách giải thích.
2. **Người dùng có hưởng lợi thật không?** Nếu chưa có exposure đủ, chưa kết luận.
3. **Chất lượng và an toàn có được giữ không?** Guardrail không phải đồ trang trí.
4. **Điểm chờ nào đã giảm?** Có thể giải thích cơ chế bằng dữ liệu và lời người làm việc?
5. **Nhịp làm việc có bền vững không?** Có dùng làm thêm giờ để tạo kết quả đẹp?
6. **Điều kiện tổ chức nào bắt buộc có?** Product Owner, quyền ưu tiên, môi trường, phê duyệt, coaching?
7. **Những nhóm khác giống/khác nhóm thí điểm ở đâu?** Mức suy rộng có giới hạn nào?

### Không đánh đồng “kết thúc pilot” với “hết trách nhiệm”

Khi Product Backlog Item đã Done, **outcome dài hạn** vẫn có thể cần tiếp tục quan sát. Khi pilot kết thúc, cần xác định ai theo dõi **những cửa sổ đo còn mở và những cải tiến đã cam kết**, để kiến thức không biến mất khi đóng báo cáo.

## 27. Khi nào mở rộng, và mở rộng điều gì?

**Nhân rộng thành công** không nhất thiết là áp đặt toàn bộ bộ nghi thức lên mọi nhóm. Nên mở rộng **những cơ chế đã có lý do và điều kiện phù hợp**.

### Mô hình mở rộng có căn cứ

~~~mermaid
flowchart TD
    A["Pilot: nhóm và kết quả thực"] --> B["Điều đã học + guardrail + giới hạn"]
    B --> C{"Có đủ điều kiện để áp dụng ở bối cảnh tiếp?"}
    C -->|Chưa| D["Giải quyết điều kiện thiếu / thử lại nhỏ"]
    C -->|Có| E["Chọn nhóm kế tiếp có khác biệt đã biết"]
    E --> F["Điều chỉnh thực hành theo loại công việc"]
    F --> G["Đo baseline và kết quả mới"]
    G --> H["Xem lại cơ chế và giới hạn suy rộng"]
    H --> B
    D --> A
~~~

### Một bảng điều kiện nhân rộng

| Điều kiện cần xem | Ví dụ câu hỏi |
| --- | --- |
| **Loại công việc tương tự** | Nhóm kế tiếp làm tính năng theo Product Goal hay xử lý incident liên tục? |
| **Khả năng giao Increment** | Có tự tích hợp/phát hành lát cắt hay vẫn phải chờ nhiều nhóm? |
| **Quyền ưu tiên** | Có Product Owner/người có quyền quyết định giá trị phù hợp? |
| **Chất lượng kỹ thuật** | CI, test, môi trường và DoD có đủ để bảo vệ thay đổi? |
| **Năng lực coaching** | Có người hỗ trợ thực hành và giải quyết hiểu lầm khi mới bắt đầu? |
| **Ràng buộc tổ chức** | Quy trình phê duyệt hoặc ngân sách có khác nhóm pilot? |
| **Đo lường** | Có baseline, nguồn dữ liệu và quyền sử dụng phù hợp? |
| **An toàn/bền vững** | Guardrails, tải vận hành và quyền dừng có rõ? |

### Mở rộng từng phần, không nhân bản “bộ công cụ”

Giả sử nhóm A học được rằng **contract tests và refinement với ví dụ nghiệp vụ** giúp giảm chờ tích hợp. Nhóm kế tiếp cũng có nhiều phụ thuộc API có thể thử hai cơ chế này mà **không cần sao chép chính xác cấu trúc Daily Scrum, phần mềm bảng hay tên cột** của A.

Ngược lại, nhóm B vận hành có thể học từ A về **minh bạch công việc và chất lượng**, nhưng chọn Kanban để quản lý WIP và các yêu cầu khẩn. **Không gọi B thiếu Agile vì không dùng cùng nhịp Sprint**, nếu cách phối hợp của B tạo giá trị và thích ứng phù hợp.

### Dấu hiệu cần thí điểm lần hai thay vì mở toàn bộ

- Nhóm đầu có **quyền tự chủ đặc biệt** mà phần lớn tổ chức không có.
- Phần lớn kết quả đến từ một **chuyên gia giỏi hiếm**, chưa có cơ chế chia sẻ kiến thức.
- Thành công chỉ dựa vào **một kỳ ít mẫu**.
- Có rủi ro an toàn hoặc dữ liệu chưa giải quyết.
- Các nhóm kế tiếp có **loại công việc khác căn bản**.
- Quy trình ngân sách/hợp đồng bên ngoài khiến phản hồi chậm mà pilot chưa gặp.

Trong các trường hợp đó, pilot thứ hai giúp tìm **điều kiện chuyển giao kiến thức**, không phải “thử lại vì pilot đầu thất bại”.

## 28. Những phản mẫu khi chọn nhóm và phạm vi pilot

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Chọn nhóm dễ nhất để chắc thắng** | Kết quả khó suy rộng | Ghi khác biệt với nhóm đích, chọn có điều kiện đại diện |
| **Chọn nhóm đang khủng hoảng nghiêm trọng** | Không phân biệt nguyên nhân thất bại | Bảo đảm quyền, an toàn và hỗ trợ trước |
| **Chọn nhóm đông nhất để gây chú ý** | Chi phí phối hợp lớn, học chậm | Bắt đầu với dòng giá trị có ranh giới rõ |
| **Pilot chỉ thay tên cuộc họp** | Không giải quyết vấn đề sản phẩm | Có outcome và cơ chế làm việc cần thử |
| **Pilot chỉ là khóa đào tạo** | Kiến thức chưa được kiểm chứng trong việc thật | Bổ sung lát cắt thực và vòng phản hồi |
| **Chỉ làm API không có đường tích hợp** | Không đo được kết quả người dùng | Lát cắt dọc hoặc ranh giới tích hợp rõ |
| **Thay toàn bộ tổ chức trong một đợt** | Không biết điều gì gây thay đổi, rủi ro cao | Chia phạm vi và giới hạn thử |
| **Không có Product Owner/quyền ưu tiên thực** | Nhiều danh sách công việc xung đột | Làm rõ accountability và trade-off |
| **Lãnh đạo chỉ tài trợ cuộc họp mở màn** | Blocker tổ chức không ai xử lý | Cam kết tháo rào cản theo quyền |
| **Giữ nguyên hàng chờ release không xét tới** | Nhóm giao code nhanh nhưng time to value không đổi | Đo end-to-end và xử lý điểm nghẽn |
| **Không có baseline, bịa số liệu hồi tố** | Kết luận không đáng tin | Định nghĩa từ hiện tại, nêu khoảng thiếu |
| **Đặt velocity tăng X% là thành công** | Khuyến khích nâng points hoặc bỏ chất lượng | Outcome, flow, quality và guardrail |
| **So velocity giữa các nhóm** | Thang ước lượng khác nhau | Dùng để planning nội bộ khi hữu ích |
| **Story code xong là Done** | Lỗi/tích hợp dồn về sau | Tôn trọng Definition of Done |
| **Bỏ test để phát hành sớm** | Đổi tốc độ lấy rủi ro dữ liệu | CI, test, rollout và phục hồi phù hợp |
| **Mở rộng khi chỉ số chính tăng nhưng lỗi tăng** | Gây hại người dùng | Guardrail là điều kiện quyết định thật |
| **Đổi giả thuyết sau khi nhìn số đẹp** | Không thể kiểm chứng khách quan | Ghi trước và ghi mọi thay đổi có lý do |
| **Đóng pilot khi outcome chưa đủ cửa sổ** | Tuyên bố thành công/thất bại sớm | Theo dõi kết quả còn mở |
| **Không được phép báo “pilot chưa hiệu quả”** | Mọi báo cáo thiên lệch | Khen thưởng học hỏi trung thực, không che lỗi |
| **Làm ngoài giờ liên tục để có biểu đồ tốt** | Nhịp không bền, lỗi dễ tăng | Xem on-call, interruptions và năng lực |
| **Dùng survey “sức khỏe” để chấm cá nhân** | Mất tin cậy và riêng tư | Phản hồi tự nguyện, tổng hợp an toàn |
| **Coi Scrum là một loại vé chứng nhận** | Thực hành mang tính nghi thức | Kiểm tra mục đích event và Increment |
| **Ép mọi dòng công việc thành Sprint** | Incident/urgent work phá kế hoạch liên tục | Chọn Scrum, Kanban hoặc kết hợp phù hợp |
| **Dùng coach làm người kiểm tra kỷ luật** | Giảm tự quản, ngại phản biện | Coaching/facilitation để học, không áp đặt |
| **Mọi quyết định phải qua ban Agile** | Thêm cấp phê duyệt, time to feedback tăng | Trao quyền theo rủi ro và trách nhiệm |
| **Pilot thành công nên nhân nguyên nghi thức** | Không phù hợp bối cảnh đội khác | Mở rộng cơ chế và điều kiện, không chỉ tên họp |
| **Không ghi những gì chưa biết** | Người sau tin giả thuyết thành sự thật | Ghi evidence, limits, next experiments |
| **Dùng công cụ mới như bằng chứng thành công** | Chi phí tăng nhưng giá trị chưa tăng | Đo kết quả công việc, không số tính năng tool |
| **Bỏ những tiếng nói phê bình** | Mất thông tin rủi ro và ý tưởng mới | Tạo kênh phản biện và kiểm chứng |
| **Không xác định người tiếp nối** | Kết quả pilot chết sau báo cáo | Trách nhiệm follow-up và Product Backlog rõ |

## 29. Bài thực hành: chọn pilot có thể học hỏi

Các ví dụ đều **giả định**. Không yêu cầu người học chọn đáp án “Agile luôn đúng”; cần trình bày **bằng chứng, tiêu chí lựa chọn, giả thuyết có thể sai và điều kiện bảo vệ chất lượng**.

### Bài 1 — Phân biệt thí điểm thật với cài đặt nghi thức

Tổ chức có ba đề xuất:

1. “Trong 30 ngày, mọi Developer phải tham dự Daily và cập nhật ticket đúng giờ.”
2. “Trong bốn Sprint, nhóm thử chia lát cắt dọc, tích hợp sớm và nhận phản hồi người học; đo time to feedback, lỗi dữ liệu và WIP.”
3. “Đào tạo 200 nhân viên về Agile Manifesto và tổ chức bài kiểm tra cuối khóa.”

**Yêu cầu:** Xếp từng đề xuất vào **thay đổi nghi thức**, **thí điểm tạo bằng chứng** hoặc **đào tạo**, rồi nói điều cần bổ sung để chúng hỗ trợ một chương trình chuyển đổi hữu ích.

**Gợi ý:** Đề xuất (2) có đủ cơ sở để trở thành pilot khi làm rõ ranh giới, baseline, người hỗ trợ và guardrails. (1) và (3) có thể là hoạt động hỗ trợ nhưng **không đủ một mình** để kết luận về kết quả Agile.

### Bài 2 — Chọn nhóm dựa trên tiêu chí, không dựa danh tiếng

Ba nhóm:

- **A:** Tính năng học, một Product Owner rõ, phản hồi người dùng tiếp cận được, có một phụ thuộc API.
- **B:** Vận hành, nhiều incident mỗi ngày, công việc thay đổi liên tục, có dữ liệu thời gian phục hồi.
- **C:** Migration dữ liệu, nhiều bước phê duyệt và rủi ro chuyển đổi khó đảo ngược.

Hãy:

1. Chọn nhóm thích hợp cho **pilot phát triển Increment theo Scrum** và nêu điều kiện cần hỗ trợ.
2. Chọn nhóm có thể phù hợp cho **pilot Kanban/flow**, giải thích vì sao.
3. Nêu lý do **chưa nên ép** một nhóm thực hiện thay đổi rủi ro cao khi chưa có phương án bảo vệ dữ liệu.
4. Ghi **giới hạn suy rộng** từ nhóm A sang B/C.

**Định hướng:** A có thể phù hợp Scrum, B phù hợp xem Kanban cho dòng yêu cầu liên tục, C cần tiêu chuẩn migration an toàn. Đây không phải phán xét năng lực con người.

### Bài 3 — Viết giả thuyết kết quả và cơ chế

**Vấn đề:** Học viên phải tìm lại vị trí, các PBI liên quan tiến độ thường chờ tích hợp và làm rõ API.

Viết:

- Một **outcome hypothesis** về hành vi người học.
- Một **process hypothesis** về cách cải thiện workflow.
- Chỉ số chính, một tín hiệu chẩn đoán và ít nhất hai guardrails.
- Một tình huống có thể **bác bỏ** hoặc làm yếu mỗi giả thuyết.

**Gợi ý:** Nếu code và Increment đến người dùng nhanh hơn nhưng người học vẫn không thấy tính năng, kết quả đó thách thức **cơ chế tạo giá trị**, không tự động thách thức mọi thực hành kỹ thuật.

### Bài 4 — Giới hạn phạm vi vertical slice

Danh sách đề xuất:

1. Lưu tiến độ bài tuyến tính với xác nhận đúng.
2. Kiểm soát quyền truy cập giữa hai học viên.
3. Khôi phục tiến độ hợp lệ khi quay lại.
4. Plugin framework cho mọi loại khóa học tương lai.
5. Offline đa thiết bị chưa có nhu cầu được xác nhận.
6. Kiểm thử tích hợp đọc/ghi.
7. Thay toàn bộ database của sản phẩm.
8. Quan sát lỗi sau phát hành.

**Nhiệm vụ:** Phân loại **cần trong lát cắt hiện tại**, **cần thêm bằng chứng**, **cần điều tra rủi ro/điều kiện hiện tại**. Giải thích vì sao bảo mật và dữ liệu không phải “tính năng có thể hoãn cho sau pilot”.

**Định hướng:** (1), (2), (3), (6), (8) có lý do hiện tại; (4) và (5) có dấu hiệu suy đoán; (7) cần chứng minh việc đổi cơ sở dữ liệu là bắt buộc chứ không tự động triển khai.

### Bài 5 — Xây pilot charter một trang

Điền mẫu:

~~~text
PILOT NAME:
  ...

VẤN ĐỀ & NGƯỜI DÙNG:
  ...

PRODUCT GOAL:
  ...

NHÓM ĐƯỢC CHỌN:
  ...

VÌ SAO NHÓM NÀY:
  ...

GIẢ THUYẾT:
  ...

LÁT CẮT SẢN PHẨM:
  ...

THAY ĐỔI CÁCH LÀM:
  ...

BASELINE:
  ...

OUTCOME & FLOW:
  ...

GUARDRAILS:
  ...

QUYỀN QUYẾT ĐỊNH VÀ HỖ TRỢ:
  ...

ĐIỀU KIỆN DỪNG / XEM LẠI:
  ...

GIỚI HẠN SUY RỘNG:
  ...
~~~

**Tiêu chí:** Charter không được chỉ ghi “đào tạo Scrum và tăng velocity”. Phải có vấn đề có thể quan sát, ranh giới thời gian, điều kiện chất lượng và trách nhiệm rõ.

### Bài 6 — Đọc số liệu flow với mẫu nhỏ

Trước pilot, cycle time năm story tương tự là **3, 5, 7, 9, 16 ngày**. Sau pilot là **3, 4, 5, 6, 7 ngày**.

**Yêu cầu:**

1. Tính mean và median của từng kỳ.
2. Nếu có một story đang mở 20 ngày, báo cáo chỉ dựa trên story đã Done có gì sai?
3. Có thể nói “Scrum làm giảm cycle time 37,5%” chắc chắn không? Vì sao?
4. Nêu hai thay đổi dữ liệu có thể khiến hai kỳ không còn so sánh công bằng.

**Đáp án tham khảo:** Trước: mean **8 ngày**, median **7 ngày**; sau: mean **5 ngày**, median **5 ngày**. Mean giảm **37,5% theo phép tính minh họa**, nhưng không đủ cơ sở quy kết nhân quả cho Scrum. Cần xem Work Item Age, ranh giới đo, loại story, cỡ mẫu và yếu tố đồng thời.

### Bài 7 — Tính WIP với Little's Law nhưng không hứa quá mức

Giả sử workflow tương đối ổn định: WIP trung bình **12**, throughput **3 hạng mục/tuần**.

1. Cycle time trung bình tương ứng?
2. Nếu WIP giảm còn 9 và throughput **thực sự vẫn 3/tuần**, cycle time trung bình tương ứng?
3. Vì sao chỉ “giới hạn WIP = 9” không bảo đảm toàn bộ PBI xong trong 3 tuần?
4. Nếu WIP đo task nhưng throughput đo user story, phép tính có còn hợp lệ?

**Đáp án tham khảo:** **4 tuần** và **3 tuần** trong giả định có điều kiện. Không dùng khi đơn vị/ranh giới không tương thích hoặc hệ thống thay đổi mạnh.

### Bài 8 — Outcome tăng nhưng quality guardrail bị vượt

Tỷ lệ tiếp tục học thành công tăng từ **42% lên 49%**, nhưng một thay đổi mới làm tăng lỗi mất tiến độ nghiêm trọng.

Hãy:

- Tính thay đổi **điểm phần trăm** và tương đối.
- Giải thích tại sao không thể gọi mọi cải thiện là do pilot chỉ từ trước/sau.
- Đề xuất **hành động ngay** về an toàn theo chính sách và những bước học hỏi tiếp theo.
- Nêu điều kiện để tiếp tục/mở rộng rollout.

**Đáp án tham khảo:** Tăng **7 điểm phần trăm**, tương đối **khoảng 16,7%** so với 42%. Guardrail dữ liệu nghiêm trọng phải được xử lý trước khi mở rộng; cần kiểm chứng nguyên nhân và chất lượng đo.

### Bài 9 — Làm rõ các phụ thuộc ngoài quyền nhóm

Nhóm pilot có CI tốt nhưng phải chờ:

- Quyết định ưu tiên từ ba cấp khác nhau.
- Môi trường test chung trong hai tuần.
- Phê duyệt bảo mật mà tiêu chí chưa được công bố.

**Nhiệm vụ:** Lập bảng **blocker – người có quyền giải quyết – thay đổi cần thử – chỉ số kiểm chứng**. Phân biệt **kiểm soát bắt buộc không được bỏ** với **chờ do tổ chức công việc chưa hiệu quả**.

**Tiêu chí:** Không chỉ trả lời “Scrum Master tháo mọi blocker”. Một số quyết định phải do Product Owner, Developers, người phụ trách môi trường hoặc lãnh đạo có thẩm quyền thực hiện.

### Bài 10 — Chọn thực hành phù hợp loại việc

Ba dòng công việc:

| Dòng công việc | Đặc điểm | Hướng thí điểm bạn chọn |
| --- | --- | --- |
| Phát triển tính năng người học | Product Goal, có cơ hội giao Increment lặp | ... |
| Vận hành/incident liên tục | Đến ngẫu nhiên, mức khẩn khác nhau | ... |
| Tích hợp API thường lỗi | Nhiều thay đổi nhỏ cần kiểm chứng kỹ thuật | ... |

**Yêu cầu:** Đề xuất **Scrum, Kanban, XP hoặc thực hành bổ trợ** và mô tả điều muốn học. Có thể chọn kết hợp, nhưng phải giải thích cơ chế, không chỉ tên framework.

### Bài 11 — Đánh giá kết quả rồi quyết định mở rộng

Pilot có dữ liệu minh họa:

- Lead time điển hình giảm **24 → 16 ngày**.
- Thời gian chờ tích hợp giảm **8 → 3 ngày**.
- Outcome người học **42% → 47%**.
- Lỗi mức trung bình trở lên **7 → 5**.
- Sự cố ngoài giờ **5 → 3**.
- Một phần người học vẫn chưa được tiếp xúc với tính năng.

**Hãy viết một kết luận 150–250 từ**:

1. Điều gì có dấu hiệu tốt hơn?
2. Điều gì còn thiếu để quy kết tác động?
3. Guardrails có đủ dữ liệu và rủi ro nào cần xem?
4. Điều kiện cần cho nhóm thứ hai?
5. Có nên triển khai cùng bộ Scrum events cho cả nhóm vận hành không?

**Định hướng:** Số liệu là tín hiệu để ra quyết định **có điều kiện**. Không tuyên bố tất cả thay đổi do Scrum và không nhân bản toàn bộ nghi thức.

### Bài 12 — Thiết kế pilot thất bại một cách có ích

Giả sử nhóm được chọn không thể phát hành vì quyền release nằm ở một hội đồng chỉ họp hằng tháng. Những cải tiến trong team chưa ảnh hưởng time to feedback.

**Yêu cầu:**

- Pilot đã **thất bại ở giả thuyết nào**, và điều gì vẫn có thể học?
- Những điều kiện tổ chức nào cần thay đổi?
- Có nên thay thành viên, bỏ Scrum hay **đổi cơ chế phê duyệt phù hợp rủi ro** trước?
- Thiết kế lại lần thử tiếp theo sao cho **không bỏ kiểm soát an toàn**.

**Điểm đánh giá:** Nhìn **rào cản hệ thống**, không dùng thất bại để đổ lỗi cho nhóm hoặc buộc báo cáo thành công.

### Bài 13 — Bảo vệ nhịp bền vững và quyền riêng tư

Lãnh đạo muốn đo “sự nhiệt huyết Agile” bằng số phút mỗi người online, số tin nhắn hằng ngày và giờ bật camera.

**Nhiệm vụ:**

1. Giải thích vì sao các proxy này **không chứng minh giá trị hoặc chất lượng**.
2. Đề xuất chỉ số **hệ thống công việc** như WIP, blocked time, on-call và quality.
3. Đề xuất một cách nhận phản hồi đội **tự nguyện, không quy lỗi và không nhận diện cá nhân**.
4. Phân biệt tình huống thật cần ứng phó sự cố ngoài giờ với yêu cầu “luôn online” vô hạn.

### Bài 14 — Chọn thử nghiệm kế tiếp sau phản hồi người dùng

Người học đã dùng tính năng tiếp tục học nhưng phàn nàn “Đang đồng bộ” khó hiểu. Một stakeholder yêu cầu lập tức triển khai offline đa thiết bị; một người khác muốn ưu tiên sửa thông báo.

**Yêu cầu:**

- Đặt hai giả thuyết giá trị tương ứng.
- Nêu tín hiệu người dùng và rủi ro cần kiểm chứng cho mỗi lựa chọn.
- Giải thích **ai có trách nhiệm thứ tự Product Backlog**, ai chọn cách kỹ thuật.
- Đề xuất một lát cắt tiếp theo không phá Product Goal.
- Ghi thời điểm/điều kiện xem lại.

**Gợi ý:** Phản hồi mới có thể làm thay đổi thứ tự, không chứng minh rằng mọi tính năng roadmap cũ đều vô ích. Hãy so giá trị, rủi ro và chi phí cơ hội.

### Bài 15 — Thiết kế quyết định nhân rộng theo điều kiện

Bạn được giao đề xuất nhóm pilot thứ hai với bốn ứng viên khác nhau về **loại việc, quyền release, công cụ CI và nguồn phản hồi**.

Hãy xây ma trận đánh giá:

| Tiêu chí | Nhóm tiếp theo A | Nhóm tiếp theo B | Nhóm tiếp theo C |
| --- | --- | --- | --- |
| Vấn đề người dùng/khách hàng | ... | ... | ... |
| Có đơn vị giá trị và cơ hội kiểm chứng | ... | ... | ... |
| Quyền quyết định và hỗ trợ tổ chức | ... | ... | ... |
| Rủi ro dữ liệu/chất lượng | ... | ... | ... |
| Phụ thuộc và tính đại diện | ... | ... | ... |
| Baseline và telemetry | ... | ... | ... |
| Thực hành có thể chuyển giao | ... | ... | ... |

**Kết luận cần nêu:** Chọn một nhóm, **điều kiện bắt đầu**, điều không nên sao chép từ pilot đầu và điều gì có thể làm bạn **đổi quyết định**.

## 30. Checklist lựa chọn nhóm thí điểm và phạm vi thử nghiệm

### A. Mục đích và vấn đề

- [ ] Có **vấn đề thật** về giá trị, chất lượng, thời gian giao hoặc khả năng thích ứng.
- [ ] Đã phân biệt **thí điểm học hỏi** với đào tạo hay cài đặt nghi thức.
- [ ] Có **Product Goal hoặc kết quả khách hàng cụ thể**, không chỉ mục tiêu tăng điểm Agile.
- [ ] Giả thuyết nêu **thay đổi cách làm → cơ chế → kết quả**, có thể bị bác bỏ.
- [ ] Chỉ số outcome và phạm vi người dùng được định nghĩa trước khi thấy số liệu.

### B. Lựa chọn nhóm

- [ ] Nhóm có **công việc và vấn đề thật** trong phạm vi có thể quan sát.
- [ ] Có khả năng tạo hoặc phối hợp tạo **một lát cắt có giá trị và đủ chất lượng**.
- [ ] Có **Product Owner/người chịu trách nhiệm giá trị** và đường phản hồi nghiệp vụ phù hợp.
- [ ] Có điều kiện **tự quản cách làm** trong ràng buộc hiện tại, hoặc lộ trình trao quyền rõ.
- [ ] Có người có **quyền tháo blocker ngoài nhóm** và cam kết hỗ trợ.
- [ ] Rủi ro bảo mật, dữ liệu và vận hành **được quản lý**, không bị bỏ qua vì muốn thử nhanh.
- [ ] Nhóm được chọn **không chỉ vì dễ tạo báo cáo đẹp hoặc nổi tiếng**.
- [ ] Những khác biệt so với **các nhóm có thể mở rộng** đã được ghi.
- [ ] Thành viên có cơ hội góp ý, nêu bất đồng và báo lỗi **mà không bị trừng phạt**.

### C. Phạm vi và thỏa thuận pilot

- [ ] Lát cắt có **ranh giới, tiêu chí Done và người dùng mục tiêu** rõ.
- [ ] Đã phân biệt **trong phạm vi, ngoài phạm vi và những rủi ro cần điều tra**.
- [ ] Không xây trọn framework hoặc kiến trúc tương lai chỉ vì muốn “future-proof”.
- [ ] Không hoãn kiểm thử, phân quyền và chất lượng bắt buộc theo lý do YAGNI.
- [ ] Thay đổi cách làm được chọn **vừa đủ** để kiểm tra cơ chế chính.
- [ ] Mỗi thực hành Scrum/Kanban/XP được chọn **vì phù hợp loại công việc**, không chỉ theo danh sách.
- [ ] Đường phụ thuộc API, môi trường, phát hành và quyết định **được đưa vào phạm vi quan sát**.
- [ ] Quyền quyết định về **Product Backlog, kỹ thuật và sự cố** có phân định rõ.
- [ ] Có **điều kiện dừng/thu hẹp**, người có quyền và cách xử lý dữ liệu khi có sự cố.

### D. Dữ liệu và đánh giá

- [ ] Có baseline hoặc ghi rõ **baseline chưa có** và bắt đầu đo từ đâu.
- [ ] Flow metrics có **đơn vị, ranh giới Started/Done và thời gian** nhất quán.
- [ ] Work Item Age và blocked work vẫn **hiển thị khi chưa Done**.
- [ ] Outcome metric có **tử số, mẫu số, cohort và cửa sổ quan sát**.
- [ ] Test/CI, lỗi tích hợp và guardrails chất lượng được kiểm chứng.
- [ ] Dữ liệu telemetry có xử lý **trùng, thiếu, đến muộn và quyền riêng tư**.
- [ ] Nhịp pilot đủ để giao lát cắt, nhưng outcome dài hơn có **kế hoạch quan sát tiếp**.
- [ ] Không dùng story points, commit, thời gian online làm KPI xếp hạng cá nhân.
- [ ] Có chỗ ghi **điều đã quan sát, giả thuyết, giới hạn và quyết định**.
- [ ] Kết luận không tự quy kết nhân quả từ trước/sau đơn thuần.

### E. Học hỏi và mở rộng

- [ ] Có nhịp kiểm tra và thích ứng ở **nhóm, sản phẩm và tổ chức** khi cần.
- [ ] Lãnh đạo sẵn sàng sửa **rào cản chính sách hoặc cấu trúc**, không chỉ yêu cầu nhóm nỗ lực hơn.
- [ ] Điều chỉnh phạm vi/giả thuyết được ghi **minh bạch và có lý do**.
- [ ] Bằng chứng sai kỳ vọng vẫn được sử dụng, không bị giấu.
- [ ] Đã phân biệt **cơ chế nào có thể chuyển giao** và điều kiện đặc thù của nhóm đầu.
- [ ] Nhóm tiếp theo được chọn theo **câu hỏi học mới và rủi ro**, không tự nhân bản nghi thức.
- [ ] Có người phụ trách **theo dõi outcome còn mở và cải tiến chưa hoàn tất**.
- [ ] Tiêu chí thành công bao gồm **giá trị, chất lượng, khả năng thích ứng và tính bền vững**, không chỉ tiến độ triển khai framework.

## 31. Câu hỏi ôn tập

1. Thí điểm chuyển đổi Agile khác việc cài đặt nghi thức Scrum như thế nào?
2. Vì sao không nên đánh giá pilot bằng số người đã được đào tạo hoặc số Daily đã họp?
3. Những loại vấn đề nào đáng dùng một pilot để tìm hiểu?
4. Giả thuyết outcome và giả thuyết cơ chế làm việc khác nhau thế nào?
5. Vì sao giả thuyết phải có khả năng sai và được xác định trước khi quan sát?
6. Những tiêu chí nào quan trọng nhất khi chọn nhóm thí điểm đầu tiên?
7. Vì sao chọn chỉ nhóm mạnh nhất có thể khiến kết quả khó suy rộng?
8. Vì sao chọn nhóm đang khủng hoảng và thiếu quyền có thể khiến pilot khó học?
9. Ma trận chọn nhóm nên được dùng như công cụ đối thoại hay như bảng xếp hạng nhân viên?
10. Những tiêu chí nào không thể bù bằng tổng điểm cao nếu chưa đáp ứng?
11. Lãnh đạo cần cam kết những gì ngoài việc phát biểu khởi động?
12. Vì sao nhóm không có quyền thay thứ tự công việc hoặc phát hành dễ gặp vấn đề khi thí điểm Agile?
13. Thế nào là phạm vi pilot quá hẹp hoặc quá rộng?
14. Lát cắt dọc có giá trị khác task backend/frontend riêng lẻ ra sao?
15. Vì sao pilot cần cả phạm vi sản phẩm lẫn thay đổi cách làm?
16. Có nên thay mọi công cụ, cơ cấu và công nghệ cùng lúc không? Giải thích giới hạn học hỏi.
17. Safe-to-fail khác việc chấp nhận gây hại dữ liệu hoặc bỏ bảo mật ra sao?
18. Vì sao tắt feature flag chưa chắc sửa được dữ liệu đã lưu sai?
19. Baseline giúp đội đánh giá điều gì, và phải làm gì khi chưa có baseline?
20. Vì sao phải phân biệt cycle time, delivery lead time và time to feedback?
21. Outcome chính khác metric chẩn đoán và guardrail thế nào?
22. Metric contract cần những trường nào để tránh mỗi nhóm tính một kiểu?
23. Vì sao chỉ phân tích người bấm nút mới có thể gây sai lệch?
24. WIP, throughput, cycle time và Work Item Age đo những khía cạnh gì?
25. Làm sao một story chưa Done 20 ngày có thể bị ẩn khỏi cycle time trung bình?
26. Định luật Little áp dụng trong những điều kiện nào và vì sao không dùng để hứa ngày hoàn thành từng PBI?
27. Vì sao outcome trước/sau tăng chưa chứng minh pilot là nguyên nhân duy nhất?
28. Khi flow cải thiện nhưng outcome chưa đổi, đội nên học gì tiếp?
29. Khi outcome tăng nhưng lỗi dữ liệu vượt guardrail, cần làm gì?
30. Vì sao một cửa sổ outcome 28 ngày không nên bị ép kết luận sau ba ngày?
31. Scrum pilot cần giữ những accountabilities, events và commitments cốt lõi nào?
32. Scrum Team có bao nhiêu accountabilities và ý nghĩa của Product Goal/DoD?
33. Những dòng công việc nào có thể phù hợp với Kanban hơn việc ép vào Sprint Goal cố định?
34. Những thực hành XP nào làm tăng khả năng giao Increment đáng tin?
35. Coaching khác kiểm soát tuân thủ và đánh giá cá nhân như thế nào?
36. Vì sao an toàn tâm lý quan trọng để pilot có thể ghi nhận kết quả bất lợi?
37. Các rào cản nào cần người ngoài team có quyền giải quyết?
38. Làm sao ghi một quyết định thay đổi backlog mà không làm mất khả năng diễn giải pilot?
39. Trong case study, vì sao nhóm A được chọn có điều kiện mà không đồng nghĩa nhóm B/C kém hơn?
40. Vì sao chờ hợp đồng và môi trường là dữ liệu học hỏi về tổ chức, không đơn thuần về kỹ năng cá nhân?
41. Những giới hạn nào cần nêu khi baseline 24 ngày và sau pilot 16 ngày?
42. Phần nào của kết quả pilot có thể chuyển sang nhóm khác mà không sao chép toàn bộ nghi thức?
43. Vì sao không nên dùng pilot thành công để áp đặt Scrum lên nhóm vận hành nhiều incident?
44. Khi nào nên làm pilot thứ hai thay vì mở rộng ngay trên diện rộng?
45. Vì sao kết thúc pilot vẫn cần người theo dõi outcome hoặc cam kết còn mở?
46. Làm sao biết một thử nghiệm đang giải quyết rào cản hệ thống thay vì chỉ làm dashboard đẹp?
47. Nếu số lượng lỗi báo cáo giảm, những nguyên nhân nào ngoài chất lượng tốt hơn cần kiểm tra?
48. Vì sao story points/velocity không phải đơn vị so năng suất giữa các đội?
49. Những thước đo nào giúp bảo vệ nhịp làm việc bền vững của nhóm thí điểm?
50. Điều kiện nào giúp tổ chức kết luận **pilot đã tạo ra học hỏi có thể hành động** dù giả thuyết ban đầu không được xác nhận?

**Ghi nhớ:** **Lựa chọn nhóm thí điểm Agile không phải tìm nơi dễ làm báo cáo thành công nhất.** Hãy bắt đầu bằng vấn đề người dùng và rào cản dòng giá trị, chọn nhóm có công việc thật, đủ quyền, năng lực chất lượng, sự hỗ trợ và tính đại diện có chủ đích. Giới hạn pilot vào **lát cắt có giá trị và một gói thay đổi cách làm có cơ chế rõ**, đặt giả thuyết có thể sai, baseline, outcome, flow metrics và **guardrails an toàn/bền vững**. Áp dụng Scrum, Kanban, XP theo loại công việc; giữ quyền tự quản, kiểm tra Increment và phản hồi người dùng qua các vòng ngắn; cho phép thay đổi khi có bằng chứng mà vẫn ghi lý do. Sau thí điểm, **mở rộng những cơ chế hữu ích trong điều kiện phù hợp**, không ép mọi nhóm nhận một bộ nghi thức giống nhau. Một pilot đáng giá khi nó giúp tổ chức **học nhanh hơn, giao giá trị đáng tin cậy hơn và đưa ra quyết định tốt hơn về bước chuyển đổi tiếp theo**, kể cả khi kết quả ban đầu không như kỳ vọng.
