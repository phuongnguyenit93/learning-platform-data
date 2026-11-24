# Nhận diện giới hạn của công cụ và điều chỉnh cách cộng tác trong nhóm Agile phân tán

> **Thông điệp cốt lõi:** Chat, họp video, tài liệu chia sẻ, bảng công việc, kho mã nguồn và CI/CD giúp nhóm phân tán phối hợp, nhưng **không công cụ nào tự tạo ra hiểu biết chung, quyền quyết định rõ, niềm tin hoặc Increment chất lượng**. Một nhóm Agile hiệu quả cần biết **công cụ nào giữ loại thông tin gì, điều gì dễ bị mất hoặc hiểu sai, khi nào nên trao đổi đồng bộ, khi nào nên bất đồng bộ và phản hồi phải đi tới người có thể hành động như thế nào**. Điều chỉnh **cách cộng tác** quan trọng hơn việc liên tục thay ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **giới hạn kỹ thuật của công cụ** với **giới hạn về tương tác, tổ chức, ngôn ngữ, thời gian và quyền quyết định** trong nhóm phân tán.
2. Đánh giá điểm mạnh và giới hạn của **chat, video call, tài liệu chung, bảng backlog/Kanban, Git/pull request, CI/CD, dashboard, công cụ thiết kế và trợ lý AI** theo mục đích cộng tác.
3. Quyết định khi nào nên dùng **trao đổi đồng bộ, bất đồng bộ hoặc kết hợp**, dựa trên độ mơ hồ, mức khẩn, mức rủi ro và số múi giờ.
4. Thiết kế **working agreements** cho kênh thông tin, thời gian phản hồi, bàn giao, xử lý blocker, quyết định và thông báo khẩn mà không tạo văn hóa phải trực tuyến 24/7.
5. Viết một **handoff note, yêu cầu phản hồi có cấu trúc và decision log/ADR** để giữ bối cảnh không phụ thuộc người có mặt trong cuộc họp.
6. Thực hành **Scrum Events** và quản lý **Product Backlog, Sprint Goal, Definition of Done** khi thành viên không thể tham dự cùng một giờ.
7. Sử dụng **WIP, work item age, cycle time, throughput** để nhận ra điểm nghẽn cộng tác mà không biến chúng thành chỉ số giám sát cá nhân.
8. Nhận biết rủi ro **bảo mật, riêng tư, quyền truy cập, truy cập cho người khuyết tật, dịch ngôn ngữ, chất lượng dữ liệu và việc dùng AI** trong công cụ nhóm.
9. Phân tích tình huống thay đổi hợp đồng UI–API bị thất lạc giữa các múi giờ, rồi đề xuất phương án cải tiến và thước đo kiểm chứng.

## 2. Tình huống mở đầu: có đủ công cụ nhưng thông tin vẫn thất lạc

Một Scrum Team phát triển nền tảng học trực tuyến có thành viên làm việc ở Việt Nam, châu Âu và Bắc Mỹ. Đội đang xây khả năng **lưu và tiếp tục tiến độ bài học**.

Product Owner và Tester đã thảo luận trường hợp mất mạng trong cuộc gọi video. Một Developer backend không thể dự vì đó là ngoài giờ làm việc tại nơi họ sống. Trong buổi họp, nhóm quyết định API phải phân biệt:

- **CONFIRMED:** hệ thống có bằng chứng hợp lệ rằng tiến độ đã lưu.
- **FAILED:** có kết quả thất bại rõ.
- **UNKNOWN:** kết nối gián đoạn nên chưa biết chắc kết quả.

Nhưng sau buổi họp:

1. Quyết định nằm trong phần chat của cuộc gọi, không được cập nhật vào acceptance criteria hoặc hợp đồng API.
2. Một người đánh dấu ticket **“Done”** vì code xử lý đường thành công đã viết xong, dù Definition of Done chưa đạt.
3. Developer frontend đọc một tin nhắn cũ và tiếp tục giả định API chỉ có hai trạng thái.
4. Pull request đã được merge nhưng một số integration tests không chạy vì môi trường chung bị lỗi.
5. Đến lần kiểm tra xuyên hệ thống, UI hiển thị **“Đã lưu”** cả khi API không có xác nhận đáng tin.

Nhóm có **chat, video, tài liệu, board, Git và CI** nhưng vẫn giao tiếp sai. Vấn đề không chỉ là “dùng công cụ chưa tốt”, mà là:

- Quyết định có ý nghĩa **không được ghi tại nơi những người không dự họp có thể tìm thấy**.
- Nhóm chưa thống nhất **nguồn tham chiếu có thẩm quyền** cho trạng thái API.
- Từ “Done” trong chat/ticket bị nhầm với **Increment đáp ứng Definition of Done**.
- Không có **handoff rõ ràng** khi công việc chuyển qua múi giờ.
- Hệ thống phản hồi kỹ thuật chưa được tổ chức để báo lỗi tới đúng người kịp thời.

Một hướng cải tiến không nhất thiết là mua ứng dụng mới. Nhóm có thể giữ công cụ hiện tại, **quy định cách chuyển quyết định từ video sang tài liệu/PR, cách bàn giao theo ca, và điều kiện để công việc thật sự được đánh dấu Done**.

## 3. Bản chất giới hạn của công cụ cộng tác

### 3.1. Công cụ hỗ trợ một phần của cộng tác, không thay thế cộng tác

| Khả năng cần có | Công cụ có thể hỗ trợ | Điều vẫn cần con người/thỏa thuận |
|---|---|---|
| **Trao đổi** | Chat, video, bình luận tài liệu | Ai cần biết, nội dung có rõ, kênh nào phù hợp |
| **Hiểu biết chung** | Tài liệu, ví dụ, bản vẽ, ghi hình | Các bên có thực sự cùng hiểu thuật ngữ và ngoại lệ |
| **Ra quyết định** | Biểu quyết, log quyết định, review | Ai có thẩm quyền, đánh đổi và khi nào xem lại |
| **Điều phối công việc** | Backlog, Kanban board, lịch | Thứ tự ưu tiên, năng lực, WIP, phụ thuộc, blocker |
| **Chất lượng kỹ thuật** | Git, tests, CI/CD, quan sát | Hành vi nào phải đạt, DoD, ai xử lý lỗi |
| **Học hỏi** | Dashboard, khảo sát, Retrospective | Diễn giải dữ liệu và hành động cải tiến |
| **Niềm tin** | Tin nhắn rõ, cập nhật minh bạch | Tôn trọng, trách nhiệm, phản hồi công bằng, nhịp làm bền vững |

**Có chức năng trong ứng dụng không đồng nghĩa đã có quy trình làm việc.** Ví dụ công cụ chat hỗ trợ gắn thẻ người, nhưng nhóm vẫn phải xác định **khi nào gắn thẻ là hợp lý và người được gắn thẻ cần phản hồi điều gì**.

### 3.2. Năm loại giới hạn cần nhận diện

1. **Giới hạn biểu đạt:** tin nhắn ngắn có thể thiếu bối cảnh, thuật ngữ đa nghĩa, cảm xúc hoặc ngữ điệu bị hiểu sai.
2. **Giới hạn thời gian:** người nhận ở múi giờ khác không thể phản hồi ngay; cuộc gọi trực tiếp có chi phí đồng bộ cao.
3. **Giới hạn khả năng truy tìm:** quyết định nằm trong luồng chat, ghi hình dài hoặc nhiều nơi; người mới không biết đâu là phiên bản hiện hành.
4. **Giới hạn quyền và độ tin cậy:** quyền truy cập, sự cố nhà cung cấp, dữ liệu nhạy cảm, trạng thái đồng bộ không chính xác.
5. **Giới hạn tổ chức:** công cụ không giải quyết Product Owner chưa rõ thứ tự ưu tiên, review không có người chịu trách nhiệm hoặc DoD bị hiểu khác nhau.

Nên hỏi **“Giới hạn nào đang tạo rủi ro?”** trước khi kết luận “cần đổi phần mềm”.

### 3.3. Thông tin không chỉ có một mức độ bền vững

| Loại thông tin | Ví dụ | Mức lưu giữ/khả năng truy xuất cần có |
|---|---|---|
| Trao đổi nhanh | “Tôi đang kiểm tra test đỏ.” | Có thể ngắn hạn, không phải quyết định |
| Cảnh báo có hành động | “CI của PR-42 đỏ ở contract test, cần xem trước merge.” | Dễ thấy, có người nhận và liên kết kết quả |
| Quyết định nghiệp vụ | “UNKNOWN không được hiển thị Đã lưu.” | Ghi ở acceptance criteria/quy tắc sản phẩm và thông báo liên quan |
| Quyết định kiến trúc | “Dùng trạng thái UNKNOWN trong hợp đồng API phiên bản mới.” | ADR/spec/contract, có bối cảnh và hệ quả |
| Trạng thái công việc | “PBI chưa đạt DoD vì còn lỗi integration.” | Board phản ánh đúng, có blocker |
| Bằng chứng chất lượng | “Commit này qua các bộ test bắt buộc.” | Kết quả CI gắn với commit/build |
| Sự kiện vận hành | “Lỗi lưu gia tăng sau rollout.” | Hệ thống giám sát/sự cố có phân quyền và lưu trữ phù hợp |

Một cuộc họp có thể tạo ra nhiều loại thông tin. Không cần ghi mọi câu nói, nhưng **những quyết định tác động tới người không dự phải đi vào nơi có thẩm quyền và dễ tìm**.

## 4. Bản đồ công cụ: dùng đúng điểm mạnh, biết giới hạn

### 4.1. Bảng chọn công cụ theo nhu cầu

| Công cụ | Phù hợp nhất | Giới hạn dễ gặp | Điều chỉnh cách cộng tác |
|---|---|---|---|
| **Chat nhóm** | Câu hỏi ngắn, phối hợp tức thời, báo blocker | Luồng trôi nhanh, thiếu ngữ cảnh, áp lực phản hồi | Dùng thread, liên kết ticket, kết luận đưa về tài liệu quyết định |
| **Video/voice call** | Vấn đề mơ hồ, bất đồng cần khám phá, pairing | Phụ thuộc giờ trùng nhau, người vắng mất bối cảnh, “meeting fatigue” | Agenda, tài liệu trước họp, quyết định và hành động sau họp |
| **Tài liệu cộng tác** | Đặc tả, quyết định, onboarding, kế hoạch cần đọc lại | Dễ lỗi thời, nhiều bản sao, khó biết ai phê duyệt | Owner, ngày cập nhật, link nguồn, lịch xem lại khi thay đổi |
| **Issue/backlog/Kanban board** | Thứ tự, trạng thái, WIP, blocker, phụ thuộc | Thẻ đẹp không chứng minh công việc đã Done; có thể thành báo cáo hình thức | Workflow rõ, DoD, policy kéo việc, link code/test |
| **Git/PR/code review** | Thay đổi code, thảo luận kỹ thuật gắn diff, traceability | Review chậm qua múi giờ, comment dễ thành tranh luận dài | PR nhỏ, mô tả ý định, tiêu chí review và escalation |
| **CI/CD** | Phản hồi build/test/integration và phát hành | Test thiếu, flaky, phản hồi muộn, alert mù | Chạy checks phù hợp, điều tra lỗi, chịu trách nhiệm khi đỏ |
| **Whiteboard/diagram** | Khám phá quy trình, event flow, mô hình domain | Phác thảo chưa phải thỏa thuận; ảnh có thể mất ngữ cảnh | Chốt thuật ngữ, ảnh/link kèm quyết định được kiểm chứng |
| **Dashboard/analytics** | Quan sát flow, quality, outcome | Số liệu sai định nghĩa, dùng giám sát cá nhân, bỏ ngữ cảnh | Ghi nguồn, mẫu số, phân khúc, xem cùng phản hồi định tính |
| **Email** | Trao đổi chính thức/đối tác, thông tin cần lưu theo chính sách | Chậm, luồng người nhận đứt đoạn, nhiều bản đính kèm | Chủ đề rõ, hành động, hạn theo múi giờ, link thay attachment bản sao |
| **Trợ lý AI/biên dịch/tóm tắt** | Gợi ý bản thảo, dịch sơ bộ, rút ý, tra cứu nội dung được phép | Có thể sai, bỏ ngoại lệ, tạo quyết định không tồn tại, rủi ro dữ liệu | Con người xác nhận, kiểm soát quyền và nguồn, không dùng như người quyết định |

Không có bảng “công cụ A luôn tốt hơn B”. **Cách dùng phù hợp hành vi** quan trọng hơn logo ứng dụng.

### 4.2. Chat: nhanh nhưng rất dễ biến tin nhắn thành quyết định vô hình

Ưu điểm:

- Hỏi nhanh một vấn đề đang chặn.
- Gửi liên kết PR, log lỗi, nhắc người phụ trách.
- Giữ trao đổi liên tục mà không phải tổ chức cuộc họp.

Rủi ro:

- Người ở múi giờ khác thức dậy thấy **hàng trăm tin nhắn**.
- Quyết định nằm trong một thread mà ticket/contract chưa cập nhật.
- Biểu tượng 👍 bị hiểu là **đã phê duyệt yêu cầu hoặc chất lượng**.
- Thông báo liên tục làm mất thời gian tập trung và tạo áp lực luôn có mặt.

**Chính sách ví dụ:** chat là kênh **tín hiệu và điều phối**, không phải nơi lưu cuối cùng của quyết định nghiệp vụ. Khi một thread chốt quy tắc “UNKNOWN không được báo thành công”, người có trách nhiệm cập nhật acceptance criteria/API contract và gửi liên kết trở lại.

### 4.3. Họp video: độ giàu trao đổi cao nhưng tốn giờ trùng nhau

Cuộc gọi trực tiếp giúp giải thích tranh luận phức tạp, cùng đọc lỗi, làm rõ nhiều giả định. Tuy vậy:

- Người ở ngoài giờ bị loại khỏi quyết định quan trọng.
- Chất lượng mạng/âm thanh tạo bất bình đẳng khi phát biểu.
- Người ít nói hoặc dùng ngôn ngữ thứ hai có thể khó chen vào.
- Ghi hình dài khó tìm kiếm; ghi hình có thể chứa dữ liệu nhạy cảm.

**Điều chỉnh:** gửi vấn đề và ví dụ trước; ghi rõ quyết định, điểm chưa rõ, chủ sở hữu và thời điểm đánh giá. Chỉ ghi hình khi có mục đích và quyền hợp lệ, không mặc định ghi mọi cuộc họp.

### 4.4. Tài liệu chung: dễ truy tìm nhưng không tự đúng và không tự cập nhật

Tài liệu có ưu thế lưu bối cảnh cho người khác múi giờ. Nhưng khi có **ba phiên bản API spec** hoặc trang wiki không có ngày cập nhật, người đọc không biết cái nào đáng tin.

Quy tắc thực hành:

- Mỗi loại quyết định có **nơi chuẩn** để tìm.
- Trang có **mục đích, người chịu trách nhiệm cập nhật, trạng thái, liên kết tới ticket/PR**.
- Khi thay đổi, **cập nhật nguồn hiện hành**, không chỉ bình luận trên tài liệu cũ.
- Đánh dấu nội dung **đề xuất / đang xem xét / đã quyết / hết hiệu lực**.
- Có quá trình kiểm tra lại tài liệu quan trọng theo thay đổi code/sản phẩm.

**Một nguồn tham chiếu cho từng loại sự thật** tốt hơn ép mọi nội dung vào một công cụ duy nhất.

### 4.5. Board: hiển thị dòng công việc chứ không chứng minh chất lượng

Bảng có thể nói một PBI ở cột Done, nhưng không biết code đã tích hợp, kiểm thử liên quan đã qua hay chưa nếu nhóm không gắn **Definition of Done** vào chính sách chuyển trạng thái.

Một số câu hỏi:

- Cột **Ready** có nghĩa gì? Cần acceptance examples rõ tới đâu?
- **In Progress** được tính từ khi nào?
- **Blocked** có hiển thị nguyên nhân, người hỗ trợ và thời gian chờ?
- **Review/Verify** là hoạt động của cả nhóm hay “đẩy cho QA”?
- **Done** có áp dụng DoD thật hay chỉ “xong code”?
- Các PBI chờ qua múi giờ có tuổi công việc được nhìn thấy không?

**Board có ý nghĩa nếu là mô hình đủ trung thực của công việc**, không chỉ giao diện để báo cáo tiến độ cho quản lý.

### 4.6. Git và CI: bằng chứng kỹ thuật mạnh, nhưng không thay thế thỏa thuận sản phẩm

Git giúp bảo tồn lịch sử code, PR tạo không gian review và CI báo một số kiểm tra kỹ thuật. Tuy nhiên:

- Một PR được approve không đồng nghĩa đã đạt **acceptance criteria** hoặc DoD.
- CI xanh chỉ chứng minh **những checks đã chạy** trong bối cảnh xác định.
- Test có thể bỏ qua trường hợp lỗi hoặc phụ thuộc dịch vụ thật.
- Review xuyên múi giờ dễ tạo vòng đợi dài nếu PR quá lớn.

**Thực hành:** PR nhỏ, mô tả quyết định và tác động, kèm test/ảnh/contract khi cần, review theo thời gian đã thống nhất; giữ chất lượng ngay cả khi có áp lực giao nhanh.

### 4.7. Trợ lý AI: hỗ trợ cộng tác nhưng không là “người tham dự đã hiểu”

AI có thể tóm tắt họp, gợi ý Gherkin, dịch đoạn tài liệu hoặc lập nháp handoff. Nhưng bản tóm tắt có thể:

- Bỏ mất câu **“chưa được quyết định”**.
- Biến đề xuất cá nhân thành **quyết định chung**.
- Dịch sai từ nghiệp vụ như *confirmed*, *accepted*, *Done*.
- Chèn chi tiết không xuất hiện trong nguồn.
- Lộ thông tin nếu đưa dữ liệu công ty/khách hàng vào công cụ không được cho phép.

Nhóm phải **đối chiếu với nguồn, xác nhận bởi người có thẩm quyền và tuân thủ chính sách dữ liệu**. Trợ lý không thay Product Owner, Developers, Scrum Master, security reviewer hay người có trách nhiệm quyết định.

## 5. Chọn đồng bộ, bất đồng bộ hoặc kết hợp

### 5.1. Phân biệt độ trễ chấp nhận được và độ mơ hồ

**Bất đồng bộ (async)** phù hợp khi người nhận có thể đọc, suy nghĩ, phản hồi trong giờ làm việc của mình và nội dung đủ rõ để không cần tương tác nhiều lượt tức thì.

**Đồng bộ (sync)** phù hợp khi vấn đề có nhiều giả định chồng chéo, cần phản hồi hai chiều nhanh hoặc cần cùng nhau xử lý sự cố.

**Kết hợp** thường là lựa chọn tốt cho vấn đề phức tạp: gửi vấn đề/đề xuất trước bằng tài liệu → họp ngắn để xử lý bất đồng → ghi quyết định và hành động để người vắng mặt tiếp tục.

| Tình huống | Cách mặc định phù hợp | Lý do |
|---|---|---|
| Cập nhật trạng thái PBI thông thường | **Async** trong board/ticket | Truy tìm được, không cần mọi người cùng online |
| Xin review PR nhỏ có mô tả rõ | **Async** trong PR | Bình luận gắn diff và người nhận đọc đúng giờ làm |
| Chọn tên trường API có hai phương án đã mô tả | **Async trước; sync ngắn nếu bất đồng** | Tránh họp khi có thể quyết định bằng ví dụ |
| Làm rõ một user story nhiều quy tắc chưa thống nhất | **Sync có chuẩn bị + quyết định async** | BDD/Three Amigos giúp phát hiện giả định nhanh |
| Pair debug một lỗi race condition khó tái hiện | **Sync có mục tiêu, thời lượng giới hạn** | Chia sẻ màn hình và suy luận tương tác có giá trị |
| Phản hồi Sprint Review của stakeholder không cùng giờ | **Kết hợp**: tài liệu, demo, câu hỏi trước; trao đổi tại thời điểm phù hợp | Tránh chỉ người có mặt quyết định |
| Sự cố production đang gây tác động lớn | **Kênh ứng cứu chuyên trách**, có gọi trực tiếp khi chính sách yêu cầu | Cần phối hợp nhanh, rõ người chịu trách nhiệm |
| Công bố thay đổi policy sau khi quyết định | **Async bền vững** kèm link nguồn | Người vắng mặt phải đọc được |

**Không biến “async-first” thành “không bao giờ họp”**, cũng không biến “chúng tôi Agile” thành “phải online mọi lúc”.

### 5.2. Bốn câu hỏi chọn kênh

1. **Độ mơ hồ:** có bao nhiêu cách hiểu, câu hỏi cần trả lời qua nhiều lượt?
2. **Mức độ khẩn/tác động:** nếu chờ tới giờ làm việc tiếp theo, người dùng hoặc Sprint Goal có bị hại đáng kể không?
3. **Khả năng mô tả:** có thể viết một thông điệp đủ ngữ cảnh, ví dụ và đề xuất không?
4. **Chi phí đồng bộ:** bao nhiêu người phải đổi giờ, mất thời gian tập trung hoặc bị loại khỏi quyết định?

Nếu câu hỏi được viết rõ và có thể chờ một ngày làm việc, dùng async. Nếu nhóm mất một ngày để gửi mười tin nhắn mà vẫn hiểu khác nhau, thử một cuộc gọi **ngắn, có agenda và có ghi quyết định**.

### 5.3. Thời gian chồng lấn không phải quyền đòi hỏi hiện diện toàn ngày

Một nhóm gồm người làm việc tại múi giờ **UTC+7, UTC+1 và UTC−5** trong một tuần minh họa. Khoảng giờ trùng nhau có thể rất ngắn hoặc không có, tùy lịch cá nhân. Múi giờ thực tế có thể thay đổi theo **daylight saving time** ở một số khu vực.

Quy tắc tốt:

- Tôn trọng **giờ làm việc thực tế và ngày nghỉ của từng người**.
- Khi đề xuất lịch, ghi **múi giờ có định danh vùng** và ngày cụ thể; đừng cố định một chênh lệch UTC cả năm khi khu vực có đổi giờ.
- Dùng một ít thời gian trùng nhau cho **khó khăn mơ hồ, quyết định tác động lớn, pairing cần thiết**, không để mọi cuộc cập nhật chiếm giờ đó.
- Luân phiên giờ họp khi có sự bất tiện không thể tránh; đừng để một vùng phải họp đêm mãi.
- Có cơ chế đọc và bình luận sau họp; **vắng họp không có nghĩa đồng ý**.
- Xác định chính sách on-call nếu công việc có yêu cầu ứng cứu ngoài giờ, tách khỏi trao đổi thường ngày.

Đặt kỳ vọng “phản hồi trước 17:00 giờ của tôi” với người ở nửa kia thế giới thường không hợp lý. Hãy dùng **giờ làm việc của người nhận, hạn cụ thể và mức tác động**.

### 5.4. Hội thoại cần kết quả, không chỉ có mặt

Một cuộc họp đồng bộ nên trả lời:

| Trước họp | Trong họp | Sau họp |
|---|---|---|
| Vấn đề, mục tiêu, các lựa chọn, ví dụ, tài liệu cần đọc | Làm rõ giả định, đánh đổi, điểm bất đồng, quyết định hoặc câu hỏi còn mở | Cập nhật nơi lưu quyết định, ticket, API contract; gửi link và chủ sở hữu |

Nếu không có kết luận, cũng ghi **“chưa quyết định”** cùng câu hỏi còn thiếu, người cần xác minh và mốc quay lại. Tránh để người vắng mặt tưởng một kết luận đã được chốt.

### 5.5. Quy tắc “escalation” khi không có câu trả lời

Với PBI đang chờ một quyết định:

1. Gửi câu hỏi **có bối cảnh và lựa chọn rõ**, gắn ticket.
2. Nêu **khi nào cần câu trả lời để công việc không bị chặn**, bằng thời điểm cụ thể có múi giờ.
3. Nếu đến mốc mà chưa có thông tin, **hiển thị Blocked** và báo qua kênh/đầu mối đã thỏa thuận.
4. Tìm **công việc khác an toàn** hoặc giảm phạm vi, không tự chọn chính sách nghiệp vụ rủi ro cao.
5. Không coi sự im lặng là đồng ý trừ khi có **chính sách rõ và phù hợp** cho quyết định ít rủi ro.

Sự cố đang gây hại có thể cần **quy trình ứng cứu riêng**, không đợi theo nhịp hỏi đáp thông thường.

## 6. Viết thông điệp bất đồng bộ đủ để người khác hành động

### 6.1. Một tin nhắn “cần review gấp” thiếu thông tin gì?

Ví dụ kém:

> “@Alex review giúp PR này ASAP, tôi cần merge hôm nay.”

Người nhận không biết:

- Mục tiêu PR là gì?
- Phần nào có rủi ro, cần kiểm tra?
- Build/CI đã đạt hay chưa?
- Có quyết định nghiệp vụ nào cần xác nhận không?
- “Hôm nay” là theo múi giờ của ai?
- Nếu người nhận đang nghỉ, ai có thể hỗ trợ đúng thẩm quyền?

### 6.2. Mẫu yêu cầu có cấu trúc

~~~text
CHỦ ĐỀ: Review thay đổi trạng thái lưu tiến độ — PR #42
MỤC TIÊU: Không hiển thị "Đã lưu" khi API trả UNKNOWN.
NGỮ CẢNH: Quyết định nghiệp vụ ở AC-07 và hợp đồng API v2.
ĐÃ LÀM: Tách enum, thêm unit tests và contract test cho UNKNOWN.
BẰNG CHỨNG: CI fast checks đạt; integration test X đang chờ môi trường.
RỦI RO / ĐIỂM CẦN XEM: Tương thích với frontend phiên bản cũ.
CẦN PHẢN HỒI: Xác nhận mapping và backward compatibility,
  không yêu cầu duyệt toàn bộ UI.
MỐC MONG MUỐN: Trước khi bắt đầu lượt triển khai kế tiếp
  (ghi ngày/giờ với múi giờ cụ thể trong công cụ).
NẾU BỊ CHẶN: Gắn trạng thái Blocked, báo người điều phối review.
LIÊN KẾT: PR #42, PBI LEARN-42, API contract và log kiểm thử.
~~~

Thông điệp này có thể dài hơn một câu chat, nhưng **giảm các lượt hỏi lại**, giúp người khác tự bắt đầu công việc và bảo vệ khoảng tập trung.

### 6.3. Cấu trúc phù hợp cho nhiều loại yêu cầu

| Loại | Thông tin tối thiểu |
|---|---|
| **Hỏi nghiệp vụ** | Người dùng, quy tắc, ví dụ chính/phản ví dụ, quyết định cần người có thẩm quyền |
| **Xin review code** | Ý định, phạm vi diff, rủi ro, test, câu hỏi cụ thể, link |
| **Bàn giao công việc** | Trạng thái, phần đã kiểm chứng, việc còn lại, blocker, người nhận, bước tiếp |
| **Báo CI đỏ** | Commit/build, test lỗi, tác động, bằng chứng, người đang điều tra |
| **Đề xuất thay đổi backlog** | Product Goal, tín hiệu mới, lựa chọn, giá trị, chi phí cơ hội |
| **Thông tin sự cố** | Tác động, mức nghiêm trọng theo chính sách, trạng thái ứng cứu, người điều phối, kênh riêng |

**Không phải lúc nào cũng cần điền biểu mẫu đầy đủ.** Một câu hỏi nhỏ đã rõ có thể chỉ cần tin nhắn. Mức cấu trúc tăng theo **độ mơ hồ, mức rủi ro và chi phí chờ**.

### 6.4. Tránh ngôn ngữ dễ hiểu sai

Một số từ nên định nghĩa:

| Cụm từ mơ hồ | Cách nói rõ hơn |
|---|---|
| “Xong rồi.” | “Code đã viết; chưa đạt DoD vì integration test X chưa chạy.” |
| “Đã duyệt.” | “Tôi đã review logic backend; approval nghiệp vụ/quality gate vẫn chờ.” |
| “Sớm thôi.” | “Dự kiến sau khi dependency Y có phiên bản test ổn định; chưa phải cam kết ngày.” |
| “Gấp.” | “Sự cố đang ảnh hưởng người học; áp dụng kênh ứng cứu mức P1 theo quy trình.” |
| “Đã lưu.” | “API có xác nhận lưu hợp lệ theo hợp đồng, không chỉ nhận request.” |
| “Không có phản hồi.” | “Chưa nhận phản hồi từ người có thẩm quyền; không coi là đồng ý.” |

Khi nhóm sử dụng nhiều ngôn ngữ, xây **glossary nghiệp vụ ngắn**. Từ *Done*, *approved*, *released*, *saved* có thể mang ý nghĩa khác nhau giữa kỹ thuật, sản phẩm và vận hành.

## 7. Bàn giao xuyên múi giờ như một thiết kế công việc

### 7.1. “Follow-the-sun” không có nghĩa luôn có người làm và không ai nghỉ

Một lợi thế của nhóm phân tán là có thể tiếp nối việc qua nhiều khung giờ. Nhưng **bàn giao yếu** thường làm mỗi lượt mất thời gian khôi phục bối cảnh, và công việc có thể quay đi quay lại giữa hai vùng.

Không nên áp dụng follow-the-sun cho mọi PBI. Nó phù hợp hơn khi:

- Công việc có **ranh giới và bước tiếp rõ**.
- Người tiếp nhận có đủ **quyền, tài liệu, môi trường và khả năng kiểm chứng**.
- Có giá trị thật từ việc rút ngắn **thời gian chờ**.
- Việc chuyển giao **không làm tăng lỗi và chi phí hiểu lại** lớn hơn lợi ích.

Với thiết kế phức tạp chưa thống nhất, **giữ sự liên tục về người thực hiện** hoặc cùng thảo luận một phần có thể hiệu quả hơn chuyển qua lại mỗi ngày.

### 7.2. Checklist bàn giao một PBI

1. **Mục tiêu:** PBI góp gì cho Sprint Goal/Product Goal?
2. **Phạm vi hiện tại:** phần nào đang làm, phần nào cố ý chưa làm?
3. **Trạng thái thật:** đã hoàn thành code gì, test nào đã chạy, còn gì chưa đạt DoD?
4. **Bằng chứng:** commit, PR, pipeline, log/ảnh phù hợp, tài liệu quyết định.
5. **Rủi ro và giả định:** có điều kiện chưa được xác nhận không?
6. **Blocker/phụ thuộc:** chờ ai, chờ kết quả nào và từ khi nào?
7. **Bước tiếp có thể làm:** một hoặc hai hành động cụ thể, thứ tự và điều kiện.
8. **Người nhận/đầu mối:** ai có thể tiếp tục, ai quyết định vấn đề nghiệp vụ?
9. **Thời điểm:** giờ làm việc/mốc đánh giá tiếp, không gợi ý phải trực 24/7.
10. **Điều kiện Done:** acceptance criteria và Definition of Done nào còn thiếu?

### 7.3. Ví dụ handoff note

~~~yaml
# Handoff minh họa, không phải schema bắt buộc của một công cụ.
pbi: "LEARN-42 — Phản hồi trạng thái lưu tiến độ"
sprint_goal: "Người học tiếp tục bài với trạng thái lưu đáng tin"
current_state: "Đang tích hợp, chưa Done"
done_so_far:
  - "Backend hỗ trợ CONFIRMED, FAILED, UNKNOWN"
  - "Unit tests và contract tests đã được thêm"
evidence:
  pr: "PR #42"
  ci: "Fast checks xanh; integration test chờ môi trường"
  specification: "Acceptance criteria AC-07 và API contract v2"
next_actions:
  - "Chạy integration test khi môi trường hoạt động"
  - "Kiểm tra frontend hiển thị UNKNOWN đúng theo AC-07"
blocked_by: "Môi trường thử dùng chung đang không khả dụng"
risks:
  - "Frontend cũ có thể không nhận biết trạng thái UNKNOWN"
decision_needed: "Product Owner xác nhận thông điệp cho người học"
handoff_to: "Người nhận đã đồng ý tiếp tục trong giờ làm của họ"
quality_state: "Chưa đạt Definition of Done"
review_point: "Khi môi trường được khôi phục hoặc tại đồng bộ phù hợp kế tiếp"
~~~

Không nhất thiết tạo một file YAML. Dùng một **comment có cấu trúc trong PBI/PR** cũng được, miễn người nhận tìm được và trạng thái được cập nhật.

### 7.4. Tiếp nhận bàn giao cũng là công việc

Người nhận nên:

- Xác nhận **mình hiểu mục tiêu và bước tiếp**, không chỉ nhấn biểu tượng 👍.
- Đọc nguồn quyết định và kiểm tra bằng chứng thay vì tin tin nhắn “đã qua test”.
- Nêu điều kiện **không thể tiếp tục an toàn**, chẳng hạn thiếu quyền hoặc không có môi trường.
- Ghi lại thay đổi mới để lượt kế tiếp không phải điều tra từ đầu.
- Không merge/deploy chỉ vì người giao đang ngủ nếu quality gates hoặc thẩm quyền chưa đủ.

Một handoff tốt làm **giảm thời gian khôi phục ngữ cảnh**, không biến người nhận thành người chịu trách nhiệm cho một quyết định mà họ chưa thể xác minh.

## 8. Working agreements: quy tắc cộng tác thay vì giả định ngầm

### 8.1. Working agreement là gì?

**Working agreement** là thỏa thuận của nhóm về cách giao tiếp, ra quyết định, quản lý luồng việc và hỗ trợ nhau. Nó không phải hợp đồng lao động, không thay chính sách bảo mật/pháp lý và không làm thay các accountability chính thức trong Scrum.

Một working agreement tốt:

- Cụ thể đủ để có thể làm theo.
- Được người thực hiện cùng tham gia xây dựng.
- Nhất quán với Product Goal, chất lượng và các ràng buộc tổ chức.
- Có thể được **kiểm tra và điều chỉnh trong Retrospective**.
- Không đòi hỏi **luôn online hoặc phản hồi ban đêm** ngoài thỏa thuận ứng cứu chính đáng.

### 8.2. Mẫu thỏa thuận nhóm phân tán

| Tình huống | Chính sách minh họa | Lý do |
|---|---|---|
| Cập nhật trạng thái công việc | Cập nhật PBI/board khi đổi trạng thái, không chỉ báo trên chat | Trạng thái truy xuất được |
| Quyết định ảnh hưởng API | Có contract/spec hoặc ADR liên kết từ PBI và PR | Người vắng họp hiểu cùng phiên bản |
| PR review thường lệ | Người nhận phản hồi theo **ngày làm việc địa phương** trong nhịp đã thỏa thuận | Không tạo kỳ vọng trực đêm |
| Blocker quá nhịp phản hồi | Đánh dấu Blocked, nêu tác động, nhờ đầu mối được chỉ định | Không để việc chờ vô hình |
| Cần họp | Đưa agenda/tài liệu trước; ghi quyết định sau | Tiết kiệm giờ trùng nhau |
| Thời gian tập trung | Dùng async cho cập nhật không khẩn; tôn trọng trạng thái bận | Giảm chuyển ngữ cảnh |
| Hành vi “Done” | Tuân thủ Definition of Done; ticket phải liên kết bằng chứng cần thiết | Chống báo tiến độ giả |
| Sự cố ngoài giờ | Dùng kênh on-call/incident đã được quy định | Phân biệt khẩn thật với cập nhật thường |
| Thông tin nhạy cảm | Chỉ dùng công cụ/kênh được tổ chức cho phép | Bảo vệ người dùng và doanh nghiệp |
| Xem lại thỏa thuận | Kiểm tra sau vài Sprint hoặc khi có thay đổi nhóm lớn | Thích ứng theo bằng chứng |

Đây là **mẫu**. Nhóm phải điều chỉnh theo khả năng làm việc thực tế và chính sách của tổ chức.

### 8.3. Tránh biến SLA giao tiếp thành áp lực vô hình

Ví dụ chính sách chưa tốt:

> “Mọi tin nhắn phải được trả lời trong 15 phút.”

Nó tạo văn hóa **liên tục gián đoạn**, thiếu phù hợp với công việc cần tập trung và bất công với người khác múi giờ.

Chính sách tốt hơn:

- **Thông tin bình thường:** phản hồi ở giờ làm việc địa phương theo nhịp nhóm đã thống nhất.
- **Blocker có hạn:** ghi mốc cần quyết định và mức ảnh hưởng; nếu không được phản hồi thì escalation.
- **Sự cố khẩn:** đi theo cơ chế ứng cứu trực với người được phân công, không thông báo đại trà.

Nguyên tắc là **phản hồi có thể dự báo**, không phải **phản hồi liên tục và tức thì**.

### 8.4. Quy tắc công bằng giữa các múi giờ

Nhóm nên xem:

- Những ai luôn phải họp sớm hoặc muộn?
- Quyết định quan trọng có thường được đưa ra khi một vùng không thể dự?
- Người giao tiếp bằng ngôn ngữ thứ hai có thời gian đọc và chuẩn bị?
- Người chăm sóc gia đình hoặc có nhu cầu hỗ trợ đặc biệt có bị bất lợi?
- Ghi chú và các kênh async có chất lượng tương đương thông tin truyền miệng?

**Công bằng không phải ai cũng dự mọi cuộc họp**, mà là cơ hội tiếp cận thông tin, góp ý và quyết định theo trách nhiệm không bị phụ thuộc bất hợp lý vào địa điểm.

## 9. Ghi quyết định và xác lập trách nhiệm giữa các công cụ

### 9.1. Một quyết định có nhiều điểm tiếp xúc

Giả sử nhóm quyết định bổ sung trạng thái **UNKNOWN** cho API lưu tiến độ. Thông tin có thể xuất hiện ở:

- Cuộc họp Three Amigos để làm rõ hành vi người học.
- Tài liệu acceptance criteria về thông điệp khi chưa biết kết quả.
- API contract định nghĩa trạng thái trả về.
- ADR nêu lý do thiết kế và tương thích.
- Product Backlog Item ghi phạm vi và điều kiện chấp nhận.
- PR và test mô tả implementation.
- Release notes khi hợp đồng ảnh hưởng consumer.

**Không nhất thiết sao chép toàn văn vào bảy nơi.** Có thể đặt **nguồn hiện hành** cho từng loại thông tin và dùng liên kết tham chiếu hai chiều. Khi một điều thay đổi, người thực hiện phải biết **nơi nào là đối tượng cần cập nhật trước**.

### 9.2. Quy tắc chọn nguồn tham chiếu

| Câu hỏi | Nguồn có thẩm quyền nên được nhóm thống nhất | Điều cần tránh |
|---|---|---|
| Product Goal hiện tại là gì? | Thông tin Product Goal do Product Owner quản lý, dễ tìm từ Product Backlog | Một slide kế hoạch cũ được coi là mới nhất |
| PBI nào ưu tiên trước? | Product Backlog được sắp thứ tự | Tin nhắn riêng từ stakeholder vượt thứ tự mà không làm rõ |
| Khi nào PBI được chấp nhận về hành vi? | Acceptance criteria/ví dụ đã thống nhất | Một lời hứa trong họp không được cập nhật |
| Khi nào Increment Done? | Definition of Done đang áp dụng và bằng chứng chất lượng | Chỉ có trạng thái “code done” |
| API trả trạng thái gì? | API contract/spec được version và review | Một ảnh chụp màn hình chat |
| Vì sao chọn phương án kỹ thuật? | ADR ngắn hoặc ghi quyết định liên kết PR | Tìm lại qua lịch sử chat nhiều tháng |
| Code hiện tại làm gì? | Phiên bản code, test và build được xác định | Wiki tự động được coi là chân lý dù đã cũ |
| Sự cố đã được giải quyết chưa? | Hệ thống incident/monitoring đúng quyền và quy trình | “Hình như ổn rồi” trong chat |

**Nguồn tham chiếu không có nghĩa không bao giờ sai.** Khi nhận thấy không khớp code, test hoặc hành vi thật, nhóm phải **phát hiện lệch, xác minh và cập nhật** chứ không tiếp tục theo tài liệu lỗi thời.

### 9.3. ADR: quyết định kỹ thuật cần ngữ cảnh

Một **Architecture Decision Record (ADR)** đơn giản thường có bối cảnh, quyết định, lựa chọn khác, hậu quả và trạng thái. Trong nhóm phân tán, ADR có ích khi người không dự cuộc họp phải hiểu **vì sao một phương án được chọn**, không chỉ biết “đã chọn gì”.

~~~markdown
# ADR-012: Biểu diễn kết quả lưu chưa xác định

Trạng thái: Đã quyết (minh họa)

## Bối cảnh
Khi request lưu bị timeout, frontend không thể kết luận
backend đã ghi dữ liệu hay chưa. Hai trạng thái success/fail
không thể hiện đúng trường hợp này.

## Quyết định
API trả ba trạng thái nghiệp vụ CONFIRMED, FAILED, UNKNOWN
theo hợp đồng được version. Frontend không thông báo "Đã lưu"
khi nhận UNKNOWN.

## Lựa chọn đã cân nhắc
- Ánh xạ timeout thành FAILED: có thể sai nếu dữ liệu đã ghi.
- Ánh xạ timeout thành CONFIRMED: tạo thông báo sai.
- Dùng UNKNOWN: giữ sự bất định, yêu cầu UI xử lý rõ.

## Hệ quả
- Cần cập nhật API contract, UI, test và tài liệu vận hành.
- Consumer cũ cần chiến lược tương thích phù hợp.
- Cơ chế đối soát sau timeout cần quyết định tiếp theo.

## Câu hỏi chưa giải quyết
Khi nối mạng trở lại, người học và hệ thống đối soát thế nào?

## Liên kết
PBI LEARN-42, acceptance criteria AC-07, PR #42.
~~~

Đây là **mẫu minh họa**, không phải quyết định có thật của sản phẩm. Một ADR có thể dài một trang, không nhất thiết tạo hồ sơ đồ sộ.

### 9.4. Quyền quyết định không biến mất vì làm việc từ xa

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog, gồm thứ tự PBI.
- **Developers** chịu trách nhiệm tạo Increment có thể sử dụng mỗi Sprint, giữ chất lượng theo DoD và thích ứng kế hoạch trong Sprint.
- **Scrum Master** chịu trách nhiệm về hiệu quả Scrum Team và giúp Scrum được hiểu/áp dụng, hỗ trợ gỡ trở ngại.

Không nên diễn giải “mọi người có quyền bình luận tài liệu” thành “bất kỳ ai cũng có thể quyết định ưu tiên sản phẩm”. Tương tự, một người gắn nhãn **approved** trong PR không tự có quyền thay acceptance criteria hoặc bỏ kiểm soát an toàn.

Tổ chức có thể có thêm thẩm quyền về **bảo mật, quyền riêng tư, pháp lý, vận hành hoặc hợp đồng**, cần được tôn trọng bên cạnh accountabilities Scrum.

### 9.5. Thỏa thuận về “đã quyết”, “đang đề xuất” và “đã xem”

Một tài liệu có thể có các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| **Draft / đề xuất** | Đang xin góp ý, chưa đủ căn cứ để dùng làm chính sách |
| **Under review / đang xem xét** | Có người có thẩm quyền/các bên liên quan đang kiểm tra |
| **Accepted / đã quyết** | Quyết định có hiệu lực trong phạm vi ghi rõ |
| **Superseded / bị thay thế** | Đã có quyết định mới; phải liên kết phiên bản thay thế |
| **Deprecated / ngừng áp dụng dần** | Cần kế hoạch chuyển đổi nếu người dùng hoặc hệ thống còn phụ thuộc |

Việc **đã đọc tài liệu** không phải lúc nào là **đã đồng ý**. Việc **không bình luận** cũng không tự thành đồng ý, nhất là khi người nhận không có cơ hội xem trong giờ làm việc.

### 9.6. Decision log ngắn cho vấn đề sản phẩm

~~~text
Decision: PRODUCT-021
Mục tiêu: Người học tiếp tục bài đáng tin sau gián đoạn.
Vấn đề: UI báo đã lưu dù API chưa xác nhận trong timeout.
Quyết định: Không hiện "Đã lưu" ở trạng thái UNKNOWN.
Người có accountability: Product Owner xác nhận hành vi nghiệp vụ;
  Developers chịu trách nhiệm thiết kế và thực hiện kỹ thuật.
Bằng chứng: Ví dụ thất bại đã được mô tả và tái hiện trong môi trường thử.
Đánh đổi: Cần thông điệp trạng thái mới, test và hỗ trợ phiên bản cũ.
Điều chưa rõ: Chính sách đối soát và retry khi mạng khôi phục.
Hành động: Cập nhật AC, API contract, UI, tests.
Mốc xem lại: Khi thử nghiệm với người học mạng không ổn định.
~~~

Decision log có ích khi nó **ngắn, đúng nguồn và dễ tìm**. Nếu ai cũng phải điền 30 trường cho một quyết định nhỏ, nhóm có thể chuyển ngược về quyết định miệng.

## 10. Hợp tác kỹ thuật qua pull request và CI/CD

### 10.1. PR review xuyên múi giờ là một hàng chờ thật

Một Developer Việt Nam mở PR lúc cuối giờ; Reviewer ở Bắc Mỹ có thể chỉ bắt đầu xem khi người viết đã nghỉ. Nếu PR lớn và thiếu bối cảnh, vòng hỏi–đáp có thể kéo dài qua vài ngày.

Một số cải tiến:

- Chia thay đổi thành **PR nhỏ có mục đích rõ**, không tách bất hợp lý làm mất khả năng chạy.
- Viết **mô tả thay đổi, ảnh hưởng, kiểm thử và câu hỏi reviewer cần trả lời**.
- Cân nhắc **pairing trực tiếp** cho thiết kế khó trước khi viết PR lớn.
- Dùng **review rotation/capacity** để tránh một người luôn làm nút cổ chai.
- Xem **work item age và thời gian chờ review**, không chỉ số comment.
- Khi PR bị chặn nhiều lượt, thử cuộc gọi ngắn trong khung giờ phù hợp, ghi lại kết luận trên PR.

Đừng ép reviewer duyệt nhanh bằng cách bỏ kiểm tra quan trọng. **Giảm kích thước thay đổi và rõ mục đích** thường hiệu quả hơn thêm áp lực.

### 10.2. Một PR tốt giúp reviewer làm việc độc lập

~~~text
PR: Thêm UNKNOWN cho API lưu tiến độ

WHY
  Tránh thông báo thành công giả khi kết quả lưu chưa đáng tin.

WHAT
  - Thêm trạng thái UNKNOWN.
  - Cập nhật mapper và contract.
  - Không đổi cơ chế retry ở PR này.

ACCEPTANCE / EVIDENCE
  - AC-07: UNKNOWN không hiện "Đã lưu".
  - Unit tests: CONFIRMED, FAILED, UNKNOWN.
  - Contract tests: phiên bản API mới có trạng thái đúng.
  - Integration tests: kết quả/điều kiện cụ thể và trạng thái hiện tại.

RISK
  Consumer phiên bản cũ không biết UNKNOWN.

NEED REVIEW
  Kiểm tra mapping và tương thích; ý nghĩa nghiệp vụ đã được
  chốt trong AC-07, không quyết lại từ đầu qua comment PR.

LINKS
  PBI, API contract, ADR.
~~~

Mục tiêu là **giảm thời gian người khác tái dựng bối cảnh**, không ép tất cả PR phải dài như tài liệu thiết kế.

### 10.3. CI là phản hồi chung của đội, không phải công việc của “người cuối cùng online”

Khi CI đỏ sau merge:

- Cần biết **build/commit nào, test nào thất bại và mức rủi ro**.
- Có chính sách xử lý **mainline đỏ**, không để build không đáng tin qua nhiều múi giờ.
- Phân biệt **lỗi sản phẩm, flaky test và vấn đề hạ tầng**.
- Test không ổn định cần điều tra, **không chỉ rerun tới khi xanh**.
- Không coi green check của một job là bằng chứng **Definition of Done đã đạt** nếu còn các điều kiện chưa được xác minh.

Nhóm có thể dùng **build ownership theo thay đổi** và cơ chế ứng cứu hỗ trợ qua giờ làm, nhưng không biến mọi thành viên thành on-call ngầm.

### 10.4. Trunk-based, nhánh ngắn và feature flags

Khi có nhiều múi giờ, nhánh sống lâu có thể dẫn đến xung đột tích hợp, nhiều giả định khác nhau và merge khó.

Một chiến lược phù hợp khi điều kiện cho phép:

- Tích hợp **thường xuyên với thay đổi nhỏ, có kiểm thử**.
- Tách **code đã tích hợp** khỏi **tính năng đã mở cho người dùng** bằng feature flags khi cần.
- Kiểm tra cả trạng thái bật/tắt có rủi ro.
- Có chính sách **dọn cờ** khi không còn cần.
- Giữ các migration/data changes tương thích hoặc có kế hoạch chuyển đổi phù hợp.

**Feature flag không tự làm phần mềm an toàn**, và branch nhỏ không thay thế test. Chọn quy trình version-control phù hợp architecture, kiểm soát và nhu cầu thực tế.

### 10.5. Pairing và ensemble programming khi thật sự có giá trị

Một phiên pairing/ensemble đồng bộ có thể rất hữu ích cho:

- Debug lỗi đồng thời phức tạp.
- Làm rõ ranh giới service và test.
- Chia sẻ kiến thức module chỉ một người hiểu.
- Onboarding một thành viên mới.

Nhưng nếu phiên kéo dài ngoài giờ của một người, hiệu quả dài hạn có thể giảm. Thực hành:

1. Xác định **vấn đề và kết quả cần đạt**.
2. Đặt **khung thời gian hợp lý**.
3. Chọn người cần tham gia, không mời tất cả chỉ để “cùng biết”.
4. Sau phiên, cập nhật test/PR/decision log hoặc handoff.
5. Khi không đủ giờ trùng, dùng **video ngắn, ghi chú có ví dụ và cặp tiếp nối** thay vì bắt buộc call.

### 10.6. TDD, BDD và ATDD nối hai nhóm công việc khác nhau

| Thực hành | Điều hỗ trợ trong nhóm phân tán |
|---|---|
| **TDD** | Unit/component tests nhỏ cung cấp phản hồi kỹ thuật ngay tại nơi code được viết |
| **BDD Discovery** | Hội thoại về ví dụ nghiệp vụ giúp các vùng tránh hiểu khác nhau “đã lưu” |
| **ATDD** | Acceptance examples được thống nhất trước code, làm điểm tham chiếu cho người không dự họp |
| **Contract tests** | Consumer/provider có bằng chứng tự động về interface đã thống nhất |
| **CI** | Tập hợp tín hiệu kỹ thuật có thể đọc lại bất đồng bộ, gắn với commit/build |
| **Definition of Done** | Cùng một chuẩn hoàn thành, tránh mỗi múi giờ có định nghĩa Done riêng |

Một file Gherkin hoặc bộ test xanh **không tự chứng minh người dùng cần đúng tính năng**, nhưng chúng làm cho điều đã được thống nhất dễ kiểm chứng khi nhóm làm việc không đồng thời.

## 11. Điều chỉnh Scrum Events cho nhóm phân tán

### 11.1. Không đổi bản chất Scrum chỉ vì đổi hình thức giao tiếp

Scrum có các accountabilities, events, artifacts và commitments. Công cụ hoặc cách tổ chức remote **không thay ý nghĩa** của chúng:

- **Product Backlog → Product Goal**.
- **Sprint Backlog → Sprint Goal**.
- **Increment → Definition of Done**.

Đội có thể dùng video, board, tài liệu và trao đổi bất đồng bộ để hỗ trợ; nhưng **không nhầm việc đăng bản cập nhật trên chat với việc tự động đạt mục đích của từng Scrum Event**.

### 11.2. Sprint Planning

Thách thức: người tham dự không cùng thời gian, PBI thiếu rõ, thảo luận kéo dài.

Thực hành:

- Product Owner làm rõ **vì sao Sprint có giá trị**, PBI được sắp thứ tự theo Product Goal.
- Gửi trước mục tiêu, dữ liệu năng lực, phụ thuộc và những PBI có khả năng được chọn.
- Dùng **trao đổi đồng bộ có mục tiêu** để hình thành Sprint Goal, lựa chọn PBI và kế hoạch phù hợp.
- Developers kiểm tra **khả năng thực tế**: giờ trùng, người nghỉ, review/CI qua múi giờ, công việc hỗ trợ.
- Kết quả được ghi trong Sprint Backlog và những nơi liên quan để người không dự một phần hiểu kế hoạch.

Không biến Planning thành chỉ việc “Product Owner điền ticket rồi các vùng tự nhận”. **Sprint Goal là mục tiêu chung**, không phải ba danh sách giao hàng rời rạc theo địa phương.

### 11.3. Daily Scrum

Theo Scrum Guide, Daily Scrum là sự kiện **15 phút dành cho Developers** để kiểm tra tiến độ hướng Sprint Goal và thích ứng Sprint Backlog.

Nhóm phân tán có thể:

- Đặt cuộc gặp trong giờ trùng hợp lý nếu khả thi.
- Thu thông tin async trước để cuộc gặp không chỉ đọc trạng thái từng người.
- Tập trung vào **mục tiêu, công việc bị chặn, thay đổi kế hoạch**, không báo cáo cá nhân cho quản lý.
- Nếu không có giờ chung phù hợp, cần thiết kế **cơ chế phối hợp có mục đích tương đương**, đồng thời thận trọng khi tuyên bố đó chính là Daily Scrum theo khuôn khổ Scrum.
- Khi bất định cao, tổ chức trao đổi bổ sung giữa những người cần thiết, không đợi một lần/ngày mới được phối hợp.

**Điểm cốt lõi:** cập nhật status trên board không tự thay thế **cuộc kiểm tra và điều chỉnh kế hoạch của Developers**.

### 11.4. Sprint Review

Sprint Review là nơi Scrum Team và stakeholders **kiểm tra kết quả Sprint và bối cảnh thay đổi, hợp tác về những việc cần làm tiếp**, không chỉ xem demo để “ký duyệt”.

Với stakeholders ở nhiều vùng:

- Có thể cung cấp **demo được kiểm soát, ghi chú, môi trường xem phù hợp** trước.
- Thu câu hỏi/nhận xét async từ người không thể dự.
- Dành thời gian tương tác đồng bộ cho **ý nghĩa dữ liệu, outcome, đánh đổi và hướng ưu tiên**.
- Product Owner cập nhật Product Backlog dựa trên thông tin mới.
- Không coi mọi emoji reaction hoặc một survey là **đại diện đầy đủ cho stakeholder**.

Nếu buổi Review chỉ có một vùng tham dự, cần chủ động để những người bị ảnh hưởng vẫn có đường góp ý **trước quyết định quan trọng khi điều kiện cho phép**.

### 11.5. Sprint Retrospective

Retrospective giúp Scrum Team cải thiện **chất lượng và hiệu quả**. Nhóm phân tán nên xem:

- Cuộc họp nào khiến một số vùng thường xuyên thiệt thòi?
- Thông tin gì bị mất khi đổi múi giờ?
- PR hoặc quyết định nào phải chờ quá lâu?
- Có trường hợp im lặng bị hiểu thành đồng ý?
- Board có phản ánh blocker thật?
- Môi trường/CI có làm tăng việc lặp hay áp lực cuối Sprint?

Đừng chỉ đề xuất **“giao tiếp nhiều hơn”**. Thử **“cập nhật decision log sau mỗi thảo luận hợp đồng API; mọi PBI thay contract phải liên kết bản spec hiện hành”** và đo xem lỗi hiểu sai có giảm không.

### 11.6. Phân biệt trạng thái và trách nhiệm

| Trạng thái/tín hiệu | Chưa đủ để kết luận | Cần xác nhận thêm |
|---|---|---|
| “Ticket Done” | Increment đã Done | DoD, tích hợp, bằng chứng kiểm thử |
| “PR Approved” | Tính năng đáp ứng nghiệp vụ | Acceptance criteria và các yêu cầu chất lượng |
| “Meeting Held” | Mọi người cùng hiểu quyết định | Quyết định đã được ghi/đọc và điểm chưa rõ |
| “Daily Update Posted” | Sprint Goal được kiểm tra và kế hoạch được thích ứng | Developers đã thảo luận/điều chỉnh hướng mục tiêu |
| “Demo Watched” | Product Goal đạt | Phản hồi stakeholder và outcome khi có dữ liệu |
| “CI Green” | Không có lỗi hoặc rủi ro | Các checks đã chạy và giới hạn kiểm tra |

## 12. Kanban, Lean và XP khi công việc đi qua múi giờ

### 12.1. Kanban cho thấy thời gian chờ ẩn

Các phép đo nền tảng trong Kanban:

- **WIP:** hạng mục đã bắt đầu nhưng chưa Done.
- **Throughput:** số hạng mục Done trong một khoảng thời gian.
- **Cycle time:** thời gian từ bắt đầu tới Done của việc đã hoàn thành.
- **Work item age:** thời gian việc đang mở đã tồn tại từ lúc bắt đầu.

Trong nhóm phân tán, một hạng mục có thể không ai “làm dở” về kỹ thuật, nhưng **đang chờ phản hồi ở múi giờ khác**. Nếu workflow không có trạng thái **Blocked/Waiting for Decision/Waiting for Review**, đội có thể tưởng vấn đề là tốc độ code.

### 12.2. Ví dụ đo vòng chờ review

Giả sử có bốn PR đã hoàn thành review:

| PR | Thời gian chờ phản hồi đầu | Điều kiện |
|---|---:|---|
| PR-A | 3 giờ | Review trong cùng khung giờ |
| PR-B | 18 giờ | Người nhận ở vùng khác, PR nhỏ và rõ |
| PR-C | 52 giờ | PR lớn, thiếu mô tả và cần trao đổi nhiều lượt |
| PR-D | 7 giờ | Review rotation có người phù hợp |

Các số trên **hoàn toàn minh họa**. Không nên kết luận người review PR-C **làm việc kém**. Cần xem kích thước PR, số dependency, ngày nghỉ, mức rủi ro và ai có quyền review. Thước đo nên phục vụ **cải thiện luồng công việc**, không xếp hạng cá nhân.

### 12.3. WIP limit và chính sách pull

Một nhóm liên tục mở PBI mới trong khi nhiều việc chờ review/test có thể tăng **work item age** và rủi ro tích hợp.

Nhóm có thể thử:

1. Giới hạn **số PBI đang làm**, tùy năng lực và loại việc.
2. Khi chạm giới hạn, ưu tiên **hỗ trợ hoàn tất** PBI gần Done trước khi kéo việc mới.
3. Hiển thị **Blocked** với nguyên nhân và đầu mối, không giấu hạng mục khỏi WIP.
4. Định nghĩa **chính sách ngoại lệ cho sự cố khẩn** và tác động tới việc đang mở.
5. Xem lại cycle time/work item age và chất lượng, không chỉ throughput.

Không có **một số WIP chuẩn** áp cho mọi đội. Giảm WIP có thể hữu ích nhưng không thay việc làm rõ quyền quyết định hoặc cải thiện môi trường CI.

### 12.4. Lean: giảm chuyển giao không tạo giá trị

Lean khuyến khích nhìn toàn **dòng tạo giá trị**, giảm lãng phí và cải tiến liên tục. Trong nhóm phân tán, lãng phí có thể là:

- Gửi qua lại một câu hỏi vì mỗi lần thiếu ngữ cảnh.
- Copy cùng thông tin vào năm công cụ nhưng không biết bản nào đúng.
- Họp trạng thái lặp lại những điều đã có trên board.
- Chờ người duy nhất có quyền review dù những người khác đủ năng lực.
- Tái hiện lỗi từ đầu vì không có handoff/log phù hợp.
- Viết lại code do API spec thay đổi mà consumer không biết.

**Giảm handoff không có nghĩa cấm phân công hoặc làm việc phân tán.** Mục tiêu là giảm **chuyển giao thiếu bối cảnh và chờ không cần thiết**.

### 12.5. XP làm thay đổi kỹ thuật trở nên dễ phối hợp hơn

Thực hành XP có thể bổ trợ:

| Thực hành | Rủi ro nhóm phân tán được giảm |
|---|---|
| **TDD** | Người khác có thể chạy test và hiểu hành vi nhỏ khi nhận code |
| **Pair programming** | Chia tri thức giữa vùng, giải quyết điểm khó cần cộng tác sâu |
| **Collective code ownership** | Giảm phụ thuộc một cá nhân luôn phải online |
| **Coding standards** | PR dễ đọc, giảm khác biệt phong cách không cần thiết |
| **Refactoring và simple design** | Code dễ thay đổi khi phản hồi sản phẩm tới từ các vùng khác nhau |
| **Continuous Integration** | Phát hiện xung đột sớm, có bằng chứng chung |
| **Small releases** | Thử lát cắt nhỏ và nhận phản hồi người dùng sớm |
| **Sustainable pace** | Tránh “follow-the-sun” biến thành trực liên tục |

Thực hành có lợi khi được triển khai như **một hệ hỗ trợ nhau**; không phải cứ bật CI là mọi xung đột tổ chức biến mất.

## 13. Khả năng tiếp cận, ngôn ngữ và sự công bằng trong cộng tác

### 13.1. “Có thể mở công cụ” chưa chắc “có thể tham gia”

Một người có quyền vào video call nhưng âm thanh kém, không đọc được nội dung bảng dùng chia sẻ màn hình hoặc phải dịch trong khi người khác nói rất nhanh sẽ khó đóng góp.

Nhóm nên kiểm tra:

- Có thể **tham gia bằng bàn phím hoặc công nghệ hỗ trợ** không?
- Tài liệu có cấu trúc heading, liên kết diễn đạt rõ và đủ tương phản không?
- Video có **phụ đề hoặc transcript phù hợp** khi công cụ và quyền riêng tư cho phép không?
- Tài liệu quan trọng có thể xem **không cần có mặt tại thời điểm họp** không?
- Người dùng ngôn ngữ thứ hai có **thời gian đọc câu hỏi trước** và viết ý kiến sau không?
- Người có mạng yếu có **cách nhận tài liệu nhẹ hơn** hoặc tham gia bằng âm thanh/chữ không?

Không cần thu thập hoặc tiết lộ thông tin sức khỏe riêng tư của ai để đặt ra **nguyên tắc bao trùm**. Khi một người cần điều chỉnh riêng, trao đổi với họ qua kênh phù hợp và tôn trọng quyền riêng tư.

### 13.2. Ngôn ngữ đơn giản tốt hơn thuật ngữ “cao siêu”

Ví dụ một nhóm đa ngôn ngữ đang thảo luận “confirmed save”. Có thể xuất hiện ba cách hiểu:

1. Request đã tới API.
2. Database đã trả thành công.
3. Người học có thể mở lại tiến độ theo hợp đồng sản phẩm.

Nhóm cần **glossary và acceptance examples** để xác định điều nào thực sự được bảo đảm. Từ dễ hiểu nhưng mơ hồ nguy hiểm hơn từ kỹ thuật được định nghĩa rõ.

Khi viết:

- Dùng câu ngắn, chủ ngữ và hành động rõ.
- Tránh viết tắt không giải thích.
- Dùng **ví dụ đối lập**: khi nào được báo “Đã lưu”, khi nào không.
- Phân biệt **đã quyết, đang đề xuất, chưa rõ**.
- Kèm dữ liệu và ảnh minh họa với **mô tả bằng chữ** để người không nhìn ảnh vẫn hiểu.

### 13.3. Dịch tự động là bản nháp

Máy dịch có thể hỗ trợ nhóm hiểu nhanh, nhưng cần người có chuyên môn xác nhận:

| Thuật ngữ | Sai lệch có thể gặp |
|---|---|
| **Done** | Bị dịch thành “đã hoàn thành code” thay vì đạt Definition of Done |
| **Accepted** | Nhầm nghiệm thu nghiệp vụ với PR approval |
| **Committed** | Nhầm mục tiêu/commitment trong Scrum với cam kết ngày giao cố định |
| **Unknown** | Bị hiểu là lỗi thất bại rõ ràng |
| **Blocked** | Bị hiểu là không có ai làm thay vì có phụ thuộc chưa giải quyết |

Với quy tắc nghiệp vụ, bảo mật và hợp đồng, bản dịch cần **đối chiếu nguồn và người chịu trách nhiệm**, không dùng như chính sách đã chốt chỉ vì văn bản trông trôi chảy.

### 13.4. Tôn trọng giờ làm việc cũng là yếu tố chất lượng

Nếu một thành viên phải thức khuya họp ba lần/tuần, nhịp làm việc có thể thiếu bền vững. Hậu quả có thể là:

- Khả năng review và ra quyết định giảm.
- Lỗi kỹ thuật hoặc hiểu nhầm tăng.
- Người đó ít phát biểu, dễ bỏ qua rủi ro.
- Nhóm mất người có kiến thức quan trọng về lâu dài.

Đây không chỉ là phúc lợi; **nó tác động trực tiếp tới chất lượng và khả năng phản hồi Agile**.

Một nhóm tốt cần đánh giá **chi phí họp và sự bất tiện phân bổ thế nào**, không chỉ tổng số buổi họp.

## 14. Bảo mật, quyền riêng tư và giới hạn vận hành của công cụ

### 14.1. Mỗi công cụ tạo thêm nơi dữ liệu có thể tồn tại

Trong nhóm phân tán, một ảnh lỗi có thể chứa tên người học, email, token, đường dẫn nội bộ hoặc dữ liệu nhạy cảm. Nếu ảnh được dán sang chat, slide, ghi hình, tài liệu ngoài hoặc công cụ AI không được cấp phép, phạm vi lưu trữ và người có thể xem **đã thay đổi**.

Một số quy tắc:

- Chỉ chia sẻ **dữ liệu tối thiểu cần thiết** cho mục đích.
- Che/ẩn thông tin nhạy cảm trước khi đưa vào ticket, PR hoặc demo.
- Kiểm tra **quyền truy cập của người nhận và khách bên ngoài**, không chỉ thấy “có link”.
- Hiểu **chính sách lưu giữ, xóa, xuất và vùng lưu trữ** áp dụng cho tài liệu/ghi hình/log.
- Không gửi secret, khóa truy cập hay thông tin khách hàng vào công cụ không được phép.
- Với AI hoặc dịch tự động, xem **chính sách sử dụng dữ liệu, quyền truy cập và yêu cầu phê duyệt**.

Không thể giải quyết rủi ro chỉ bằng lời nhắc “đừng gửi dữ liệu nhạy cảm”. Nhóm cần **cấu hình, quyền, quy trình và kiểm tra** phù hợp.

### 14.2. Quyền xem và quyền quyết định là hai chuyện khác nhau

Một người có quyền sửa API contract không nhất thiết có quyền thay đổi quy tắc sản phẩm. Một người có quyền merge có thể vẫn cần tuân thủ quality gates và chính sách bảo mật.

Cần phân biệt:

1. **Quyền truy cập công cụ:** xem, sửa, bình luận, approve, deploy.
2. **Trách nhiệm công việc:** ai cung cấp thông tin, ai thực hiện, ai phối hợp.
3. **Thẩm quyền quyết định:** người nào có accountability hoặc quyền phê duyệt theo quy trình.
4. **Bằng chứng tuân thủ:** quyết định/test/review có được ghi phù hợp không?

Không nên coi “có quyền nhấn nút” là “được phép bỏ qua thỏa thuận và chất lượng”.

### 14.3. Sự cố công cụ: cần phương án thay thế có kiểm soát

Các sự cố có thể xảy ra:

- Chat hoặc video không truy cập được.
- Công cụ board bị gián đoạn, thông tin trạng thái không cập nhật.
- Kho mã nguồn/CI tạm ngưng.
- Tài liệu không còn khả dụng hoặc bị khóa quyền.
- Dashboard lệch dữ liệu do thay đổi instrumentation.

Đừng mặc định **đổi sang ứng dụng cá nhân bất kỳ** là cách khắc phục an toàn. Nhóm nên xác định trước:

| Sự cố | Phương án phản ứng có thể thỏa thuận | Điều không nên làm |
|---|---|---|
| Video call mất kết nối | Gửi agenda và câu hỏi bằng kênh đã được phép, đặt lại trao đổi phù hợp | Tuyên bố người vắng đồng ý với quyết định |
| Chat ngừng hoạt động | Dùng kênh thông báo dự phòng được tổ chức cho phép | Gửi dữ liệu khách hàng qua tài khoản cá nhân |
| Board không truy cập được | Ghi tạm trạng thái tối thiểu ở nơi dự phòng hợp lệ; đồng bộ lại sau | Đánh dấu mọi việc Done bằng trí nhớ |
| CI không khả dụng | Tạm dừng hoặc giới hạn merge/release theo chính sách, ghi kiểm tra chưa có | Coi CI không chạy là “đạt” |
| API spec không tìm thấy | Giữ công việc cần hợp đồng ở trạng thái cần xác minh | Tự chọn hợp đồng mới để kịp giờ |
| Dashboard sai dữ liệu | Công bố sự cố đo lường, đối chiếu nguồn, sửa định nghĩa | Tái ưu tiên sản phẩm chỉ dựa trên chỉ số sai |

Mức khẩn và quyền quyết định phụ thuộc sản phẩm. Một outage của công cụ video thường khác outage của công cụ xử lý sự cố bảo mật.

### 14.4. Kế hoạch khôi phục bối cảnh sau gián đoạn

Khi công cụ trở lại, đừng chỉ mở lại tab:

1. Kiểm tra **những thay đổi/ quyết định diễn ra trong thời gian gián đoạn**.
2. Đối chiếu trạng thái công việc với commit, test, chủ sở hữu.
3. Cập nhật ticket/spec/decision log **một lần đúng nguồn**, giải quyết mâu thuẫn.
4. Thông báo các quyết định có ảnh hưởng tới người đã vắng mặt.
5. Kiểm tra những guardrails và quality gates không được chạy trong gián đoạn.
6. Học từ sự cố: cần cải thiện dự phòng, quyền truy cập hay phản hồi nào?

Điều này tránh việc hai vùng tiếp tục từ **hai phiên bản thực tế khác nhau** sau khi công cụ bị lỗi.

### 14.5. Khi nào cần hành động đồng bộ khẩn cấp?

Không phải mọi thông báo đỏ đều là sự cố. Phân loại theo rủi ro:

- **Lỗi PR chưa merge:** thường xử lý trong quy trình review/CI.
- **Build mainline đỏ:** cần chính sách khôi phục luồng tích hợp, không để kéo dài vô hình.
- **Production lỗi có ảnh hưởng người dùng:** theo incident process, có người điều phối và liên lạc thích hợp.
- **Mất dữ liệu/lộ quyền:** kích hoạt quy trình an toàn và thông báo đúng thẩm quyền.

Nếu người đang ngủ không nằm trong ca ứng cứu, đừng mặc định họ phải nhận điện thoại. Thiết lập **trách nhiệm on-call và cơ chế chuyển giao** thay vì áp áp lực cho toàn nhóm.

## 15. Case study xuyên suốt: quyết định API bị thất lạc giữa ba vùng

### 15.1. Bối cảnh sản phẩm và nhóm

Một Scrum Team của nền tảng học trực tuyến có:

- **Product Owner** làm việc tại Việt Nam, quản lý Product Backlog và tiếp nhận phản hồi người học.
- **Developers** phụ trách frontend, API, database và kiểm thử sống ở ba vùng có giờ làm việc chồng lấn hạn chế.
- **Scrum Master** hỗ trợ hiệu quả nhóm và gỡ trở ngại cộng tác.
- Một số chuyên gia bảo mật/vận hành chỉ tham gia khi rủi ro liên quan.

**Product Goal:** “Người học có thể học tiếp bài đang dở đáng tin cậy trong điều kiện được sản phẩm hỗ trợ.”

**Sprint Goal:** “Người học nhận trạng thái lưu phù hợp và có thể tiếp tục bài sau khi hệ thống xác nhận tiến độ.”

Giải pháp đi qua UI, API và database. Nhóm có chat, video call, một công cụ backlog, Git/PR, CI và tài liệu kỹ thuật.

### 15.2. Sự kiện trong Sprint A

| Mốc | Sự kiện | Công cụ có mặt | Vấn đề cộng tác |
|---|---|---|---|
| Ngày 1 | Thảo luận trong video về khi nào báo “Đã lưu” | Video + chat | Người backend không dự; quyết định chỉ nằm trong chat |
| Ngày 2 | API bắt đầu code theo hai trạng thái thành công/thất bại | Git, ticket | API contract chưa được cập nhật |
| Ngày 3 | Frontend đọc thread cũ và xây thông báo theo hai trạng thái | Chat, Git | Có hai cách hiểu trong cùng PBI |
| Ngày 5 | Tester nêu trường hợp timeout không biết kết quả | Ticket comment | Câu hỏi chưa có người có thẩm quyền xác nhận |
| Ngày 6 | PR backend được review nhưng test tích hợp chờ môi trường | Git, CI | Approval bị hiểu là “đã xong” |
| Ngày 7 | Board chuyển PBI sang Done | Board | Chưa có bằng chứng DoD đạt |
| Ngày 8 | E2E phát hiện UI báo thành công giả | CI/E2E | Lỗi phát hiện muộn, nhiều phần cần sửa |
| Ngày 9–10 | Team làm lại contract, UI và test; Sprint Goal bị ảnh hưởng | Nhiều công cụ | Handoff lặp, áp lực cuối Sprint |

Các mốc là **dữ liệu giả định** để thực hành phân tích. Không có bằng chứng rằng một cá nhân đơn lẻ gây ra toàn bộ vấn đề.

### 15.3. Phân tích: công cụ nào không đáp ứng nhu cầu nào?

| Công cụ | Đã giúp gì? | Giới hạn trong tình huống | Thay đổi cách dùng |
|---|---|---|---|
| Video | Giải thích nhanh ngoại lệ nghiệp vụ | Người không dự mất quyết định | Ghi quyết định/điểm chưa rõ ở tài liệu hiện hành |
| Chat | Trao đổi tức thời và nhắc người | Thread trôi, thiếu nguồn tham chiếu | Chỉ dùng để báo/link, không coi là bản hợp đồng chính |
| Backlog | Theo dõi PBI và Sprint | Cột Done không gắn với DoD | Thể hiện blockers, acceptance criteria, chuẩn chuyển trạng thái |
| API spec | Có nơi mô tả hợp đồng | Chưa được cập nhật trước code | Version hóa, link PBI/ADR/PR và quy định người cập nhật |
| PR | Review diff và thảo luận code | Thiếu context; approval bị nhầm nghiệm thu | Mô tả why/what/risk/tests, ghi rõ review scope |
| CI | Tìm sai lệch kỹ thuật | Test tích hợp muộn và môi trường thiếu ổn định | Contract tests sớm, dữ liệu thử cô lập, theo dõi việc chưa chạy |
| Handoff | Có tin nhắn “xong backend” | Không biết status chất lượng thật | Mẫu bàn giao trạng thái, bằng chứng và bước tiếp |

**Vấn đề không được sửa bằng cách thêm một kênh chat mới.** Nhóm phải thiết kế **luồng quyết định và bằng chứng xuyên qua công cụ**.

### 15.4. Câu hỏi tìm điều kiện hệ thống

Thay vì nói “Người backend không đi họp nên không hiểu”, retrospective đặt câu hỏi:

1. Tại sao quyết định quan trọng phụ thuộc vào một buổi họp ngoài giờ làm của một vùng?
2. Tại sao kết luận không có **nguồn tham chiếu bền vững**?
3. Khi contract thay đổi, ai có trách nhiệm cập nhật consumer và test?
4. Vì sao ticket Done trong khi DoD chưa đạt, và ai nhận tín hiệu này?
5. Review/CI đã đưa ra bằng chứng gì và **không đưa ra bằng chứng gì**?
6. Một handoff có thể cung cấp thông tin gì để người nhận tiếp tục an toàn?
7. Có phải work item age tăng vì chờ quyết định hoặc môi trường test?

Những câu hỏi này giúp nhóm xem **điều kiện làm việc** thay vì coi vấn đề là thiếu nỗ lực.

### 15.5. Working agreements cho Sprint B

Nhóm chọn một **thử nghiệm hai Sprint minh họa**:

| Thỏa thuận thử nghiệm | Người phối hợp | Bằng chứng kỳ vọng |
|---|---|---|
| Mọi thay đổi hành vi API có acceptance example thành công và lỗi trước implementation | Product Owner + Developers/Tester | PBI có link tới ví dụ đã thống nhất |
| Quyết định ảnh hưởng consumer ghi tại API contract/ADR, chat chỉ báo link | Người đề xuất thay đổi + reviewer liên quan | Không còn hai bản contract tự nhận là hiện hành |
| PR đổi API phải kèm test/đánh giá tương thích | Developers | Review phát hiện consumer break sớm |
| PBI không được chuyển Done khi integration checks bắt buộc chưa đạt | Developers, theo DoD | Trạng thái board minh bạch |
| Mỗi lượt bàn giao ghi trạng thái thật, bằng chứng và bước tiếp | Người giao, người nhận | Ít lượt hỏi lại để khôi phục context |
| Blocker quyết định kéo dài qua nhịp đã thống nhất được làm hiển thị | Người phát hiện, Scrum Master hỗ trợ | Work item age ở trạng thái chờ giảm |
| Cuộc họp yêu cầu quyết định gửi agenda trước và có kết luận sau | Người tổ chức | Người không tham dự vẫn tìm được kết luận |

Không cần áp dụng thêm mười công cụ. Nhóm có thể dùng **tài liệu, ticket và PR hiện có**.

### 15.6. Một lát cắt kỹ thuật cụ thể

Đội mô tả hành vi:

~~~gherkin
Feature: Người học nhận đúng trạng thái lưu tiến độ

  Scenario: Đã lưu thành công có xác nhận
    Given người học đang ở một bài hợp lệ
    When dịch vụ xác nhận tiến độ đã được lưu
    Then giao diện hiển thị "Đã lưu"

  Scenario: Kết quả lưu chưa xác định
    Given yêu cầu lưu đã được gửi
    When kết nối ngắt trước khi nhận kết quả đáng tin
    Then giao diện không khẳng định "Đã lưu"
    And giao diện cho biết trạng thái chưa xác định phù hợp
~~~

Các bước trên là ví dụ Gherkin có mục đích thảo luận. Muốn thực thi cần **step definitions, dữ liệu thử và môi trường phù hợp**. Chính sách retry/đối soát sau timeout vẫn phải được làm rõ nếu còn ngoài phạm vi.

Để giảm sai khác giữa múi giờ:

1. Product Owner xác nhận **ý nghĩa nghiệp vụ** trong acceptance criteria.
2. Developers cập nhật **API contract** và test liên quan.
3. Frontend và backend review **cùng contract hiện hành**.
4. Contract/integration tests chạy trong CI phù hợp.
5. Người nhận handoff thấy **trạng thái chưa Done** nếu còn điều kiện chất lượng.
6. Sprint Review xem Increment đã đạt DoD và phản hồi người học.

### 15.7. Đo hiệu quả thử nghiệm

Ví dụ các tín hiệu **giả định, không phải dữ liệu thực**:

| Tín hiệu | Sprint A | Sprint B | Điều cần đọc thận trọng |
|---|---:|---:|---|
| PR đổi API phải hỏi lại vì thiếu context | 9 | 4 | Loại PR và độ phức tạp có tương đương? |
| PBI chờ quyết định API quá hai ngày làm việc | 5 | 2 | Có chuyển việc sang nơi không được đo? |
| Lỗi hiểu sai contract phát hiện cuối Sprint | 3 | 1 | Có tăng kiểm tra sớm và ghi nhận chính xác? |
| PBI chuyển Done dù thiếu kiểm tra bắt buộc | 2 | 0 | Định nghĩa DoD có giữ nguyên không? |
| Cuộc họp quan trọng chỉ một vùng dự | 4 | 2 | Người ngoài cuộc có cơ hội góp ý thật không? |
| Sự cố lưu tiến độ từ người dùng | Chưa đủ dữ liệu | Chưa đủ dữ liệu | Chưa kết luận outcome hoặc độ an toàn tăng |

**Hai Sprint không chứng minh quan hệ nhân quả**. Số PBI, độ phức tạp và lịch nghỉ có thể khác. Nhóm xem thêm **phản hồi định tính**, chất lượng sau phát hành, tải công việc và mức công bằng giữa các múi giờ.

### 15.8. Quyết định sau thử nghiệm

Nhóm có thể nhận thấy:

- Contract tests và quyết định có link giúp người vắng họp nắm thông tin nhanh hơn.
- PR nhỏ làm review rõ hơn nhưng một số thay đổi phức tạp vẫn cần pairing.
- Board phản ánh trạng thái thật hơn; số PBI “Done” có thể giảm tạm thời nếu trước đây báo Done quá sớm.
- Vẫn còn phụ thuộc một Reviewer ở vùng khác, cần luân chuyển tri thức hoặc cải tiến chính sách.

Kết luận phù hợp là **giữ cách làm hữu ích, điều chỉnh điểm nghẽn còn lại và tiếp tục quan sát**, không tuyên bố “đã giải quyết mọi vấn đề remote”.

## 16. Đo hiệu quả cộng tác mà không giám sát cá nhân

### 16.1. Mục tiêu đo là cải thiện hệ thống

| Nhóm tín hiệu | Ví dụ | Câu hỏi | Nguy cơ nếu dùng sai |
|---|---|---|---|
| **Luồng công việc** | WIP, work item age, cycle time, throughput | Có giảm thời gian chờ vô hình không? | Biến throughput thành điểm nhân viên |
| **Review và quyết định** | Thời gian tới phản hồi hữu ích, quyết định chờ quá nhịp | Người khác vùng có bị kẹt vì thiếu thông tin? | Ép phản hồi tức thời cả ngoài giờ |
| **Chất lượng** | Lỗi hợp đồng, CI flaky, PBI thiếu DoD, lỗi production | Hiểu sai được phát hiện sớm hơn không? | Tăng test chỉ để đẹp số |
| **Tài liệu và bối cảnh** | Số lần hỏi lại vì thiếu spec, số quyết định không truy tìm được | Ngôn ngữ chung và handoff có tốt hơn? | Viết tài liệu quá mức để đạt KPI |
| **Công bằng** | Giờ họp ngoài giờ, cơ hội đóng góp, phản hồi bị bỏ qua | Gánh nặng có dồn vào một vùng không? | Theo dõi cá nhân xâm phạm riêng tư |
| **Nhịp bền vững** | Làm thêm giờ, gián đoạn, quá tải on-call | Cách cộng tác có duy trì lâu dài không? | Dùng dữ liệu nhạy cảm làm đánh giá cá nhân |
| **Outcome sản phẩm** | Lỗi mất tiến độ, tỷ lệ quay lại bài | Chất lượng phối hợp có giúp người dùng không? | Suy nguyên nhân từ một phép đo trước–sau |

Không đặt KPI như “mọi người phải gửi 50 tin nhắn mỗi ngày”, “người nào phản hồi PR chậm nhất sẽ bị phạt”. Chúng khuyến khích **hoạt động nhìn thấy được**, không phải giá trị.

### 16.2. Phân biệt thời gian chờ do múi giờ với thời gian chờ do thiếu ngữ cảnh

Một yêu cầu PR mở cuối giờ địa phương có thể đợi tới sáng hôm sau của người review mà **không có vấn đề quản lý**. Ngược lại, PR thiếu test và bối cảnh có thể tạo ba lượt hỏi qua ba múi giờ, khiến work item age tăng nhiều ngày.

Có thể phân loại:

- **Chờ nhịp làm việc hợp lý:** người nhận đang ngoài giờ, lịch đã được thống nhất.
- **Chờ quyết định:** chưa có người có thẩm quyền hoặc chưa rõ câu hỏi.
- **Chờ kỹ thuật:** môi trường/CI/dependency không dùng được.
- **Chờ do kích thước việc:** PR/PBI lớn, phụ thuộc nhiều phần.
- **Chờ do giao tiếp:** yêu cầu thiếu ngữ cảnh, nguồn tham chiếu mâu thuẫn.

Mục tiêu không phải loại bỏ **mọi khoảng chờ**, mà giảm những chờ đợi **có thể phòng ngừa và làm giảm giá trị**.

### 16.3. Thử nghiệm cải tiến cộng tác

~~~yaml
# Mẫu cải tiến minh họa; điều chỉnh theo chính sách và công cụ của nhóm.
experiment_id: REMOTE-COLLAB-04
problem: "Quyết định API thất lạc và PR review bị chờ nhiều lượt"
hypothesis: >
  Nếu mỗi thay đổi hợp đồng có ví dụ chấp nhận và link contract hiện hành,
  PR có mô tả rủi ro/test, thì số lần hỏi lại và lỗi contract muộn sẽ giảm.
scope: "Những PBI thay đổi API tiến độ trong hai Sprint thử nghiệm"
actions:
  - "Chốt kết luận nghiệp vụ trong acceptance criteria"
  - "Ghi hợp đồng trong spec versioned, không chỉ chat"
  - "Dùng mô tả PR có why/what/risk/evidence"
  - "Bàn giao trạng thái chưa Done và blocker có link"
signals:
  - "Số vòng hỏi lại do thiếu bối cảnh"
  - "Work item age của PBI chờ review/decision"
  - "Lỗi sai contract phát hiện sau tích hợp"
guardrails:
  - "Không hạ Definition of Done"
  - "Không tăng họp ngoài giờ hoặc tải on-call bất hợp lý"
  - "Không đưa dữ liệu nhạy cảm sang công cụ không được phép"
review_point: "Retrospective sau thử nghiệm"
decision_options: ["Giữ", "Điều chỉnh", "Dừng"]
~~~

### 16.4. Đọc dữ liệu trước–sau cẩn thận

Giả sử PR wait time giảm nhưng bug production tăng. Nhóm cần hỏi:

- Có bỏ review chất lượng để đạt tốc độ không?
- PR nhỏ hơn có thực sự được tích hợp/test đầy đủ?
- Có thay đổi phức tạp hơn trong giai đoạn mới?
- Có sự cố công cụ hoặc sản phẩm không liên quan?
- Số liệu thời gian chờ có cùng mốc tính và cùng loại việc không?

**Không đánh đổi chất lượng và nhịp làm bền vững chỉ để giảm một chỉ số trung gian.**

## 17. Những ngộ nhận và phản mẫu phổ biến

| Ngộ nhận / phản mẫu | Tại sao gây hại? | Cách điều chỉnh |
|---|---|---|
| “Mua thêm công cụ sẽ giải quyết giao tiếp.” | Giới hạn về quyền quyết định, bối cảnh, năng lực vẫn còn; thêm nguồn thông tin mới | Làm rõ vấn đề và working agreements trước khi đổi công cụ |
| “Có chat thì không cần tài liệu.” | Quyết định trôi trong luồng tin nhắn, người vắng mặt khó tìm | Ghi quyết định vào nguồn tham chiếu, dùng chat gửi link |
| “Ghi hình mọi cuộc họp là có tài liệu.” | Video dài khó tra, thiếu kết luận, có rủi ro riêng tư | Tóm tắt quyết định và hành động, ghi hình có mục đích và quyền phù hợp |
| “Không vào họp nghĩa là đồng ý.” | Loại người khác múi giờ khỏi quyết định quan trọng | Gửi ngữ cảnh trước, có kênh góp ý và ghi quyết định sau |
| “Async-first tức là không bao giờ gặp nhau.” | Tranh luận phức tạp kéo dài nhiều ngày bằng chat | Sync chọn lọc khi độ mơ hồ và rủi ro cao |
| “Agile nghĩa là phải online ngay khi có tin nhắn.” | Gián đoạn và làm việc ngoài giờ liên tục | Kỳ vọng phản hồi theo giờ làm, escalation theo mức tác động |
| “Nhóm phân tán chỉ cần gửi status mỗi ngày.” | Board/chat không bảo đảm kiểm tra Sprint Goal | Developers chủ động kiểm tra kế hoạch, blocker và điều chỉnh |
| “Một PR approved tức là tính năng Done.” | Code review không thay acceptance criteria và DoD | Gắn evidence/test/DoD với PBI và Increment |
| “CI xanh nghĩa là mọi thứ đều đúng.” | Chỉ những checks đã chạy được kiểm chứng | Bổ sung kiểm tra rủi ro và quan sát sản phẩm |
| “CI đỏ nhưng reviewer nói ổn thì vẫn merge.” | Mất bảo vệ chất lượng, che rủi ro | Dùng quality gates và quy trình ngoại lệ có thẩm quyền |
| “Mọi việc đều chuyển qua múi giờ tiếp theo được.” | Chuyển giao liên tục gây mất ngữ cảnh và lỗi | Chọn follow-the-sun khi công việc có ranh giới rõ |
| “Handoff chỉ cần nhắn 'xong rồi'.” | Người nhận không biết test, blocker và bước tiếp | Ghi bối cảnh, trạng thái thật, bằng chứng, rủi ro, owner |
| “Kênh công khai thì ai cũng tự biết.” | Người khác không biết thread nào quan trọng hoặc không đủ quyền truy cập | Thông báo có chủ đích, link nguồn và người nhận rõ |
| “Mọi quyết định đều cần 100% đồng thuận.” | Có thể trì hoãn vô hạn, không rõ accountability | Tham vấn đúng người và tôn trọng thẩm quyền quyết định |
| “Có quyền edit là có quyền quyết định.” | Nhầm permission công cụ với trách nhiệm sản phẩm/chất lượng | Phân biệt quyền truy cập và thẩm quyền thực |
| “Tài liệu càng nhiều càng tốt.” | Tài liệu lỗi thời, trùng bản, tốn công cập nhật | Nguồn tham chiếu theo loại quyết định, nội dung vừa đủ |
| “Board Done nghĩa là DoD đã đạt.” | Trạng thái bị biến thành báo cáo hình thức | Chính sách chuyển trạng thái phản ánh DoD và bằng chứng |
| “Người ở vùng khác review chậm là thiếu nhiệt tình.” | Bỏ qua lịch làm việc, ngày nghỉ, kích thước PR | Đo thời gian chờ theo bối cảnh và giảm thiếu ngữ cảnh |
| “Có thể đo năng suất bằng số tin nhắn hoặc commit.” | Khuyến khích hoạt động ồn ào và gaming | Đo flow, chất lượng và outcome ở cấp hệ thống |
| “Công cụ dịch không bao giờ sai nghĩa nghiệp vụ.” | Các từ Done, approved, saved, committed dễ bị dịch lệch | Glossary, ví dụ, người có chuyên môn xác nhận |
| “AI summary có thể chốt quyết định hộ nhóm.” | Có thể bỏ ngoại lệ hoặc tạo kết luận không tồn tại | Kiểm chứng nguồn, người có thẩm quyền duyệt |
| “Link tài liệu có nghĩa mọi người đều truy cập được.” | Quyền, thiết bị, mạng và khả năng tiếp cận khác nhau | Kiểm tra quyền xem và phương án tiếp cận phù hợp |
| “Công cụ ngoài không được dùng thì cứ dùng tài khoản cá nhân.” | Rủi ro quyền riêng tư, bí mật và quản trị | Chỉ dùng nền tảng được phép, có phương án dự phòng |
| “Họp tối khuya cố định là cái giá phải trả khi remote.” | Bất công và thiếu bền vững | Luân phiên lịch, tăng async, dùng giờ trùng cho việc có giá trị cao |
| “Remote retrospective chỉ cần vote emoji.” | Không khám phá điều kiện hoặc thử nghiệm cải tiến | Kết hợp dữ liệu, thảo luận, quyết định có owner và mốc xem lại |
| “Thêm feature flag là không cần kiểm thử phát hành.” | Trạng thái bật/tắt và migration vẫn có rủi ro | Kiểm tra theo rủi ro, rollout, rollback và DoD |
| “Giảm thời gian review là mục tiêu lớn nhất.” | Có thể tạo merge vội, lỗi production tăng | Cân bằng độ trễ, chất lượng, khả năng bảo trì và nhịp bền vững |

## 18. Checklist điều chỉnh cách cộng tác cho đội phân tán

### 18.1. Mục tiêu và trạng thái công việc

1. **Product Goal** và Sprint Goal có được tìm thấy từ nơi chung, không phụ thuộc lời nói trong họp?
2. Product Backlog có **thứ tự** và người chịu accountability rõ?
3. PBI có acceptance criteria hoặc ví dụ đủ để người ở vùng khác hiểu?
4. Board có **Definition of Workflow**, blocker, phụ thuộc và chính sách Done?
5. Các thành viên có phân biệt **code xong, PR approved, Increment đạt DoD, release và outcome**?
6. Work item age của việc đang chờ quyết định/review có được nhìn thấy?

### 18.2. Thông tin và quyết định

7. Với từng loại thông tin quan trọng, nhóm có biết **nguồn tham chiếu hiện hành**?
8. Quyết định từ video/chat có được đưa về tài liệu/spec/ticket phù hợp?
9. Tài liệu có trạng thái **draft/approved/superseded**, owner và liên kết phiên bản không?
10. Các quyết định chưa rõ có được đánh dấu **chưa quyết**, không tự coi im lặng là đồng ý?
11. AI summaries hoặc bản dịch có được kiểm tra khi tác động tới nghiệp vụ hoặc bảo mật?
12. Có glossary cho từ dễ nhầm như **Done, saved, approved, committed**?

### 18.3. Sync/async và múi giờ

13. Cuộc họp đồng bộ có **mục tiêu rõ** và dùng giờ trùng nhau cho vấn đề cần trao đổi trực tiếp?
14. Agenda, ví dụ và câu hỏi có được gửi trước khi cần quyết định?
15. Người vắng mặt có thể đọc kết luận và góp ý theo trách nhiệm?
16. Có chính sách **phản hồi theo giờ làm địa phương**, ngày nghỉ, múi giờ cụ thể?
17. Lịch họp có tránh đặt gánh nặng ngoài giờ mãi vào một vùng?
18. Blocker và sự cố khẩn có **đầu mối/escalation** khác với cập nhật thường?

### 18.4. Bàn giao, kỹ thuật và chất lượng

19. Handoff có **mục tiêu, trạng thái, evidence, rủi ro, blocker, bước tiếp và người nhận**?
20. PR có **ý định, phạm vi, test, rủi ro và câu hỏi review** vừa đủ?
21. Có chính sách xử lý **CI đỏ, flaky tests, môi trường không khả dụng**?
22. Các thay đổi contract/API có **kiểm tra tương thích** giữa consumer và provider?
23. Có nhịp tích hợp nhỏ và review phù hợp để giảm branch sống lâu và chờ qua múi giờ?
24. Có giữ DoD và các kiểm soát bảo mật/dữ liệu bắt buộc khi áp lực giao hàng tăng?

### 18.5. An toàn, tiếp cận và cải tiến

25. Quyền truy cập và chia sẻ dữ liệu trong chat/ghi hình/log/AI có đúng chính sách?
26. Có cách tham gia cho người mạng yếu, dùng ngôn ngữ thứ hai hoặc cần hỗ trợ tiếp cận?
27. Nhóm có kênh riêng an toàn cho vấn đề nhạy cảm và cơ chế xử lý phù hợp?
28. Có phương án liên lạc và bảo toàn trạng thái khi công cụ bị gián đoạn?
29. Chỉ số flow/review được dùng để **cải thiện hệ thống**, không giám sát cá nhân?
30. Retrospective có chọn **thử nghiệm nhỏ, owner, tín hiệu, guardrail và mốc xem lại**?

Checklist này là **công cụ rà soát**, không phải quy định phải tick đủ 30 ô cho mọi PBI. Chọn những điều tương xứng rủi ro và điều kiện thực tế.

## 19. Bài tập thực hành

### Bài tập 1 — Phân biệt khả năng và giới hạn công cụ

Một đội có công cụ chat, video, wiki, Kanban board, Git và CI. Hãy nối từng nhu cầu với **nơi phù hợp nhất để ghi kết quả**, đồng thời nêu **một giới hạn** của nơi đó:

1. Quyết định rằng timeout không được báo “Đã lưu”.
2. Trạng thái PBI đang chờ test tích hợp.
3. Mô tả ý định và rủi ro của thay đổi code.
4. Bằng chứng unit/contract tests cho một commit.
5. Câu hỏi khẩn để phối hợp ứng cứu production.
6. Giải thích vì sao nhóm chọn một phiên bản API cụ thể.

**Gợi ý:** một vấn đề có thể cần **trao đổi ở chat/video** nhưng **kết luận ở nơi khác**; không chọn một công cụ làm nơi lưu mọi thứ.

### Bài tập 2 — Chọn sync, async hoặc kết hợp

Phân loại từng trường hợp và giải thích:

- A. Cần review PR đổi tên biến, có test và mô tả rõ.
- B. Product Owner, Tester và Developer bất đồng về cách xử lý thanh toán timeout.
- C. Một người muốn báo đã cập nhật tài liệu hướng dẫn.
- D. Người dùng đang mất dữ liệu diện rộng, cần khôi phục.
- E. Nhóm cần quyết định hướng kiến trúc có ba phương án và nhiều đánh đổi.
- F. Stakeholder khác vùng muốn góp ý sau Sprint Review.

**Yêu cầu:** chọn cách cộng tác, nơi ghi kết luận, người cần quyết định và mức khẩn. Đừng chỉ trả lời “gọi video nhanh hơn”.

### Bài tập 3 — Sửa thông điệp bất đồng bộ thiếu bối cảnh

Tin nhắn ban đầu:

> “@Dev xem lại API gấp nhé. Có vẻ sai. Xong báo mình.”

**Yêu cầu:** viết lại tin nhắn gồm:

~~~text
Mục tiêu / vấn đề:
Hành vi mong muốn:
Bằng chứng hiện có:
Rủi ro và tác động:
Liên kết PBI/PR/CI/spec:
Câu hỏi cụ thể cần người nhận:
Mốc phản hồi theo giờ làm/múi giờ phù hợp:
Nếu bị chặn:
~~~

**Gợi ý:** thay “có vẻ sai” bằng một ví dụ có thể tái hiện và chỉ rõ trạng thái chưa chắc chắn.

### Bài tập 4 — Thiết kế một handoff xuyên múi giờ

Developer ở Việt Nam kết thúc giờ làm khi PR cho trạng thái UNKNOWN còn chờ kiểm thử API–database. Người tiếp nhận ở châu Âu sẽ bắt đầu sau.

**Yêu cầu:**

1. Viết một handoff note có mục tiêu, trạng thái thật, test đã chạy và chưa chạy, blocker.
2. Nêu người có thẩm quyền quyết định câu chữ UI.
3. Chỉ ra việc nào người nhận có thể làm ngay và việc nào **không thể làm an toàn** nếu thiếu thông tin.
4. Phân biệt **code done** với **Definition of Done**.
5. Nêu một dấu hiệu cho thấy handoff đã cải thiện trong một vài Sprint.

### Bài tập 5 — Quyết định API bị thất lạc

Trong một cuộc gọi video, nhóm quyết định thêm trạng thái UNKNOWN. Backend không dự; frontend đọc thread cũ và vẫn dùng hai trạng thái.

**Yêu cầu:**

- Vẽ dòng thông tin **trước và sau cải tiến** bằng sơ đồ hoặc bảng.
- Chọn nơi lưu acceptance criteria, API contract và quyết định kiến trúc.
- Đề xuất một contract test phát hiện lệch sớm.
- Nêu một chính sách để **người không dự họp có thể góp ý hợp lý**.
- Giải thích tại sao chỉ ghi hình cuộc họp không đủ.

### Bài tập 6 — Phân tích điểm nghẽn review theo Kanban

Một nhóm có 10 PBI đang mở. Bốn PR đang chờ review; một PR đã chờ ba ngày làm việc vì thiếu context, hai PR chờ một người duy nhất có quyền approve.

**Yêu cầu:**

1. Phân biệt WIP, work item age, cycle time và throughput.
2. Chỉ ra ít nhất ba điều kiện khiến hàng chờ tăng.
3. Đề xuất hai thử nghiệm giảm chờ mà không hạ review quality.
4. Nêu một tín hiệu bảo vệ về lỗi production hoặc chất lượng.
5. Giải thích vì sao không nên dùng thời gian review để đánh giá riêng một cá nhân.

### Bài tập 7 — Thiết kế working agreements

Đội gồm người làm việc trong các vùng khác nhau, có ít giờ trùng nhau và thường xuyên bị nhắn ngoài giờ.

Hãy hoàn thành:

~~~text
Mục tiêu cộng tác:
Kênh chat cho thông tin thường:
Nơi lưu quyết định nghiệp vụ:
Nơi lưu quyết định kỹ thuật:
Nơi xem PBI / DoD / blocker:
Khi nào dùng họp đồng bộ:
Kỳ vọng phản hồi trong giờ làm địa phương:
Escalation cho blocker:
Kênh ứng cứu sự cố:
Chính sách PR review:
Quy tắc handoff:
Quy tắc dữ liệu và AI:
Phương án khi công cụ bị gián đoạn:
Mốc thử nghiệm và xem lại:
~~~

**Gợi ý:** các quy tắc nên **cụ thể và khả thi**, không phải “mọi người giao tiếp tốt hơn”.

### Bài tập 8 — Scrum Events trong nhóm phân tán

Sprint Planning chỉ có một nửa Developers dự; Daily Scrum biến thành báo cáo cho quản lý; Sprint Review chỉ có một vùng stakeholder xem demo.

**Yêu cầu:**

1. Chỉ ra mục đích nào của từng Scrum Event có nguy cơ bị mất.
2. Đề xuất cách chuẩn bị async và tương tác sync đủ cần thiết.
3. Làm rõ Product Owner, Developers và Scrum Master chịu trách nhiệm gì.
4. Nêu cách giữ Sprint Goal và Definition of Done hiển thị.
5. Nêu ít nhất một cách để người khác múi giờ **đóng góp thật**, không chỉ được gửi ghi hình.

### Bài tập 9 — Công cụ AI tóm tắt sai quyết định

Một trợ lý AI tạo meeting summary:

> “Nhóm đồng ý coi mọi timeout là lưu thất bại và tự động retry.”

Nhưng cuộc họp thực tế chỉ mới thống nhất **“timeout chưa biết kết quả phải hiển thị UNKNOWN”**, còn cơ chế retry chưa quyết định.

**Yêu cầu:**

- Nêu rủi ro khi phát tán summary như quyết định chính thức.
- Viết nội dung đính chính có phân biệt **đã quyết/chưa rõ**.
- Xác định người có thẩm quyền xác nhận quy tắc và nơi cập nhật.
- Đề xuất một cách kiểm chứng bản tóm tắt trước khi gửi.
- Nêu biện pháp bảo vệ dữ liệu khi sử dụng trợ lý.

### Bài tập 10 — Cộng tác khi công cụ bị gián đoạn

Kho mã nguồn và CI không khả dụng trong một buổi làm việc. Một người đề nghị gửi patch qua email cá nhân và merge khi dịch vụ trở lại, bỏ qua kiểm tra vì cần giao đúng hạn.

**Yêu cầu:**

1. Nêu những rủi ro về bảo mật, lịch sử thay đổi và chất lượng.
2. Đề xuất phản ứng phù hợp với policy của đội.
3. Chỉ ra điều gì có thể làm offline hoặc bằng công cụ dự phòng **được phép**.
4. Nêu cách đối chiếu trạng thái sau khi hệ thống khôi phục.
5. Giải thích vì sao “CI không chạy” **không đồng nghĩa CI đạt**.

### Bài tập 11 — Công bằng thời gian họp và khả năng tiếp cận

Một nhóm có cuộc gọi cố định khiến thành viên ở một vùng thường xuyên phải dự lúc tối muộn; người khác nghe âm thanh kém và ít phát biểu bằng ngôn ngữ thứ hai.

**Yêu cầu:** thiết kế phương án:

- Giảm số cuộc họp chỉ để cập nhật status.
- Luân phiên lịch khi không thể tránh chênh lệch giờ.
- Gửi tài liệu/thu câu hỏi trước.
- Cung cấp ghi chú, mô tả hình ảnh hoặc phương tiện tiếp cận phù hợp.
- Bảo vệ quyền riêng tư và không ép mọi người bật camera.
- Đo kết quả về khả năng tham gia và tải công việc, không giám sát cá nhân.

### Bài tập 12 — Lập thử nghiệm cải tiến thực tế

Chọn một vấn đề trong nhóm của bạn: PR chờ lâu, yêu cầu thất lạc, video họp tốn nhiều giờ, CI không tin cậy hoặc ticket Done sai.

Viết thẻ thử nghiệm:

~~~text
Product Goal / Sprint Goal liên quan:
Vấn đề quan sát được:
Sự kiện và dữ liệu nền:
Giới hạn của công cụ hiện tại:
Điều kiện tổ chức / múi giờ liên quan:
Giả thuyết nguyên nhân:
Thay đổi cách cộng tác sẽ thử:
Công cụ hiện có được dùng lại như thế nào:
Người phối hợp và trách nhiệm quyết định:
Phạm vi và thời gian thử:
Tín hiệu về flow:
Tín hiệu về chất lượng:
Tín hiệu công bằng / nhịp bền vững:
Guardrails về DoD, bảo mật, quyền riêng tư:
Điểm xem lại:
Điều kiện giữ, sửa hoặc dừng:
~~~

**Tự đánh giá:** đề xuất của bạn có giải thích **giới hạn cụ thể nào đang gây tổn thất**, cách đổi hợp đồng cộng tác ra sao và **bằng chứng nào cho thấy sự thay đổi có ích**, hay chỉ đề nghị cài thêm một công cụ?

## 20. Tổng kết

Trong một nhóm Agile phân tán, **khả năng dùng công cụ** và **khả năng cộng tác** có liên quan nhưng không đồng nhất. Những nguyên tắc quan trọng:

1. **Nhìn đúng giới hạn:** chat dễ trôi, video cần thời gian trùng, tài liệu có thể lỗi thời, board có thể phản ánh sai Done, PR có thể bị chờ, CI có thể thiếu hoặc không đáng tin, AI có thể tóm tắt sai.
2. **Chọn kênh theo mục tiêu:** async cho thông tin có thể đọc và trả lời độc lập; sync cho điều mơ hồ hoặc phối hợp cần thiết; kết hợp để quyết định vừa nhanh vừa truy tìm được.
3. **Quyết định phải có nơi sống:** ghi nguồn hiện hành, thẩm quyền, trạng thái, điều còn chưa rõ và liên kết với PBI/contract/PR; không dựa vào một lời nói trong video.
4. **Bàn giao phải giữ ngữ cảnh:** mục tiêu, trạng thái thật, bằng chứng, rủi ro, blocker và bước tiếp rõ để người khác múi giờ tiếp tục an toàn.
5. **Working agreements bảo vệ sự dự báo được:** quy tắc phản hồi, giờ làm, review, escalation và khẩn cấp cần thực tế và công bằng, không biến nhóm thành on-call 24/7.
6. **Giữ chất lượng Agile:** Product Goal, Sprint Goal, acceptance criteria và Definition of Done không được thay bằng các badge của công cụ; test/CI là bằng chứng có giới hạn.
7. **Dùng flow để tìm điểm nghẽn:** WIP, work item age, cycle time và throughput giúp nhận ra chờ quyết định/review, không phải thước đo hiệu suất cá nhân.
8. **Bảo vệ dữ liệu và khả năng tham gia:** quyền truy cập, ghi hình, thông tin nhạy cảm, công nghệ hỗ trợ, ngôn ngữ và AI đều là yếu tố cần thiết kế có chủ đích.
9. **Cải tiến theo bằng chứng:** thay một quy tắc cộng tác nhỏ, đo tác dụng và tác động phụ rồi giữ, sửa hoặc dừng; đừng mặc định mua công cụ mới là tiến bộ.

> **Câu hỏi ghi nhớ:** “Nếu một đồng đội ở múi giờ khác chỉ có thể đọc thông tin sau khi tôi kết thúc ngày làm việc, họ có biết **điều gì đã được quyết, vì sao, bằng chứng nào tin được, việc gì còn thiếu và bước tiếp an toàn là gì** — mà không phải hỏi lại toàn bộ từ đầu không?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — accountabilities, Sprint Goal, Product Goal, Definition of Done và mục đích các Scrum Events.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giao tiếp, cộng tác, phản hồi và nhịp phát triển bền vững.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, work item age, throughput, cycle time và điều chỉnh cách làm bằng phản hồi.
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — tích hợp thường xuyên và cơ chế phản hồi kỹ thuật đáng tin.
- [Martin Fowler — Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) — phối hợp việc tích hợp và phát hành theo mức rủi ro.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — TDD, pair programming, collective ownership, CI và small releases.
- [W3C Web Accessibility Initiative (WAI)](https://www.w3.org/WAI/) — nguyên tắc thiết kế nội dung và công cụ có khả năng tiếp cận.
- [Google SRE — Postmortem Culture](https://sre.google/sre-book/postmortem-culture/) — điều tra sự cố và học hỏi không đổ lỗi trong hệ thống có nhiều người tham gia.
