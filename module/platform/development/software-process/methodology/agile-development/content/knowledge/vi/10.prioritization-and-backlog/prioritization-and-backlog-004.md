# Cân bằng tính năng, lỗi, nợ kỹ thuật và hoạt động khám phá

> **Chương:** Ưu tiên và backlog  
> **Học phần:** AGILE_DEVELOPMENT — ứng dụng giá trị và nguyên tắc Agile để phản hồi sớm, giao phần mềm tăng dần và cải tiến liên tục; thực hành user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp.

Một Product Backlog không chỉ chứa các tính năng mà khách hàng nhìn thấy. Trong cùng một tuần, nhóm phần mềm có thể nhận yêu cầu thêm luồng thanh toán, phát hiện lỗi tạo đơn hàng trùng, nhận cảnh báo thư viện sắp hết hỗ trợ và cần khảo sát một API chưa rõ khả năng. Nếu chỉ ưu tiên tính năng, sản phẩm có thể tiến nhanh một thời gian rồi chậm lại vì lỗi và nợ kỹ thuật. Nếu chỉ sửa những điều “bên trong”, nhóm lại không tạo được giá trị đủ sớm cho người dùng. Nếu nghiên cứu mọi thứ thật kỹ trước khi xây, cơ hội học từ phần mềm chạy thật sẽ đến quá muộn.

**Bài toán ưu tiên thực sự là phân bổ năng lực khan hiếm giữa bốn loại đầu tư:** tạo giá trị mới, khôi phục chất lượng bị mất, bảo vệ khả năng thay đổi trong tương lai và giảm bất định trước khi cam kết. Cách cân bằng tốt cần dựa vào **Product Goal, bằng chứng, rủi ro, chi phí trì hoãn, mức khẩn cấp và năng lực thực tế**. Nó không thể giải bằng quy tắc “mỗi Sprint luôn dành đúng 20% cho nợ kỹ thuật” áp dụng cho mọi nhóm.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **tính năng**, **lỗi**, **nợ kỹ thuật** và **hoạt động khám phá** về nguồn tạo giá trị, kết quả mong đợi và tiêu chí hoàn tất.
2. Đánh giá chung các loại công việc bằng giá trị cho người dùng, độ khẩn cấp, rủi ro, mức tin cậy của bằng chứng, phụ thuộc và công sức.
3. Thiết lập chính sách xử lý lỗi khẩn cấp và quản lý nợ kỹ thuật mà không biến toàn bộ backlog thành hàng đợi khẩn cấp.
4. Sử dụng user story, Product Backlog, refinement, Sprint Goal, Kanban và các thực hành XP để tạo dòng công việc có thể dự báo.
5. Lập một kế hoạch năng lực minh họa, nêu rõ việc nào phải hoãn khi xuất hiện yêu cầu ngoài kế hoạch.
6. Chọn chỉ số để kiểm tra đồng thời **giá trị sản phẩm**, **chất lượng**, **khả năng học hỏi** và **sức khỏe dòng công việc**.

## 2. Bốn nhóm công việc phục vụ bốn loại giá trị

| Nhóm công việc | Câu hỏi trung tâm | Ví dụ | Đầu ra quan trọng |
| --- | --- | --- | --- |
| **Tính năng (feature)** | Khả năng mới nào giúp người dùng hoàn tất một công việc hoặc cải thiện kết quả? | Người dùng tự đổi lịch tư vấn. | Một lát cắt hoạt động được, có tiêu chí chấp nhận và đo kết quả sau giao. |
| **Lỗi (bug/defect)** | Hành vi hiện tại sai khác kỳ vọng ở đâu, gây tác động gì? | Hai yêu cầu đồng thời tạo cùng một khung giờ hẹn. | Hành vi đúng được khôi phục, kiểm thử hồi quy và xác nhận tác động đã được giải quyết. |
| **Nợ kỹ thuật (technical debt)** | Điều gì trong thiết kế, mã, kiểm thử hoặc hạ tầng làm thay đổi tương lai tốn kém/rủi ro hơn? | Logic đặt lịch bị lặp trong nhiều dịch vụ, không có kiểm thử cạnh tranh. | Rủi ro hoặc chi phí thay đổi được giảm, có tín hiệu kiểm chứng. |
| **Khám phá (discovery)** | Giả định nào chưa đủ bằng chứng để chọn giải pháp hoặc ưu tiên? | API đối tác có hỗ trợ idempotency khi timeout không? | Bằng chứng, kết luận, rủi ro còn lại và quyết định tiếp theo trong một timebox. |

Các nhóm này **không có ranh giới tuyệt đối**. Một lỗi nghiêm trọng có thể khiến nhóm phải refactor nền tảng; một tính năng mới có thể đòi hỏi spike kỹ thuật; công việc giảm nợ kỹ thuật có thể mở khóa tính năng quan trọng. Đừng mất thời gian tranh luận nhãn nếu **quyết định, giá trị và cách kiểm chứng** đã rõ.

### 2.1. Một công việc không nên bị đánh giá chỉ bằng mức độ dễ trình diễn

Demo tính năng mới thường trực quan hơn việc sửa lỗi race condition hoặc nâng cấp cơ chế khôi phục. Tuy vậy, việc ngăn mất dữ liệu có thể tạo giá trị lớn hơn một nút mới. “Người dùng không nhìn thấy” **không có nghĩa là không tạo giá trị**: người dùng cảm nhận sự ổn định, tốc độ, bảo mật và khả năng tiếp tục được đáp ứng nhu cầu.

Ngược lại, một đề xuất “nâng cấp kiến trúc cho sạch” chưa cho thấy tác động tới rủi ro, tốc độ thay đổi hay nghĩa vụ vận hành thì chưa có cơ sở ưu tiên cao chỉ vì tên gọi kỹ thuật.

### 2.2. Xem công việc như những khoản đầu tư khác thời điểm

- **Tính năng** thường nhắm tới lợi ích trực tiếp hoặc sớm cho người dùng và tổ chức.
- **Sửa lỗi** ngăn tổn thất hiện tại hoặc khôi phục lời hứa về chất lượng.
- **Giảm nợ kỹ thuật** giảm “lãi phải trả” khi thay đổi, nâng độ tin cậy và khả năng giao về sau.
- **Khám phá** mua thông tin để tránh đầu tư sai hoặc chọn phương án rủi ro.

Để cân bằng, nhóm cần hỏi **giá trị của việc làm ngay so với chi phí của việc để sau**, chứ không chỉ hỏi “hạng mục nào có nhiều người yêu cầu nhất?”.

## 3. Một Product Backlog minh bạch thay vì bốn hàng đợi cô lập

Trong Scrum, **Product Backlog** là danh sách có thứ tự những gì cần cải thiện sản phẩm; Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả backlog. Nó có thể chứa các Product Backlog Item liên quan tính năng, lỗi, hỗ trợ kỹ thuật hoặc giảm bất định khi những việc đó cần thiết cho sản phẩm. Scrum không quy định phải có bốn backlog riêng theo loại công việc.

Một nhóm có thể dùng **nhãn** để phân tích nhu cầu và phân bổ năng lực, nhưng nếu tính năng nằm trong bảng của Product Owner còn nợ kỹ thuật nằm trong bảng riêng không ai ưu tiên, hai danh sách dễ cạnh tranh ngầm. Một hệ thống minh bạch nên giúp cả nhóm hiểu **tổng năng lực đang dành vào đâu** và ai chịu trách nhiệm sắp thứ tự.

| Thông tin cần có cho mỗi hạng mục | Vì sao hữu ích? |
| --- | --- |
| **Vấn đề/kết quả cần đạt** | Biết vì sao đáng làm và phần nào liên quan Product Goal. |
| **Loại công việc** | Giúp nhìn tỷ lệ nhu cầu và rủi ro, không phải để tự động quyết định thứ tự. |
| **Bằng chứng và mức tin cậy** | Phân biệt số liệu, phản hồi, nghĩa vụ và suy đoán. |
| **Tác động nếu hoãn** | Cho thấy tổn thất, giới hạn thời gian hoặc chi phí trì hoãn. |
| **Rủi ro/chỉ số bảo vệ** | Không tối ưu tính năng bằng cách làm xấu chất lượng và bảo mật. |
| **Công sức, phụ thuộc, khả năng chia nhỏ** | Hỗ trợ chọn lát cắt tạo kết quả sớm và kế hoạch khả thi. |
| **Tiêu chí hoàn tất/kiểm chứng** | Tránh đóng ticket nhưng chưa có hành vi đúng hoặc thông tin hữu ích. |
| **Người chịu trách nhiệm và thời điểm xem lại** | Đảm bảo hạng mục không nằm vô thời hạn trong backlog. |

**Lưu ý:** Một lỗi được phát hiện khi tính năng vẫn **chưa đạt Definition of Done** thường là việc phải hoàn tất để story đạt DoD; không nên tách sang “backlog lỗi của Sprint sau” rồi tự nhận tính năng đã Done. Lỗi sau phát hành có thể là hạng mục được ưu tiên theo tác động; nếu sự cố nghiêm trọng, nó cần quy trình ứng cứu riêng và tác động tới kế hoạch đang thực hiện.

## 4. Những tiêu chí chung để so sánh công việc khác loại

Khi một nhóm phải so “thêm tính năng A” với “sửa lỗi B” và “giảm nợ kỹ thuật C”, hãy đặt chúng cạnh nhau bằng **cùng bộ câu hỏi**:

| Tiêu chí | Câu hỏi cần trả lời | Ví dụ bằng chứng |
| --- | --- | --- |
| **Giá trị và mục tiêu** | Việc này giúp ai, cải thiện kết quả nào của Product Goal? | Tác vụ thành công, yêu cầu hỗ trợ, doanh thu hoặc thời gian thao tác. |
| **Mức độ tác động** | Bao nhiêu người/luồng bị ảnh hưởng, ảnh hưởng nặng đến đâu? | Số giao dịch lỗi, nhóm người dùng, mức mất dữ liệu, chi phí vận hành. |
| **Chi phí trì hoãn** | Nếu chờ thêm một tuần hoặc một Sprint, điều gì xảy ra? | Ngày API ngừng hỗ trợ, chi phí hỗ trợ lặp, rủi ro tăng, cơ hội bỏ lỡ. |
| **Rủi ro** | Hậu quả nếu không làm hoặc làm sai; khả năng khôi phục thế nào? | Sự cố, lỗ hổng, vi phạm nghĩa vụ, rủi ro triển khai. |
| **Mức tin cậy của bằng chứng** | Điều gì đã đo được, điều gì mới là giả định? | Telemetry, log, phỏng vấn, thử nghiệm, yêu cầu hợp đồng. |
| **Kích thước và phụ thuộc** | Có thể chia thành phần nhỏ, giao độc lập hay không? | Ước lượng tương đối, năng lực chuyên môn, phụ thuộc đội khác. |
| **Giá trị của thông tin** | Khảo sát nhỏ có giúp tránh đầu tư lớn sai hướng? | Một spike kiểm tra API trước khi viết cả bộ tích hợp. |
| **Tính đảo ngược** | Có thể thử và quay lại với chi phí nhỏ không? | Feature flag, rollout giới hạn, backup và kế hoạch rollback. |

**Ưu tiên là quyết định đa chiều.** Một lỗi bảo mật nghiêm trọng có thể phải xử lý ngay dù ước lượng lớn; một cải tiến giao diện có lợi rõ nhưng không cấp bách có thể chờ. Không dùng duy nhất “giá trị chia công sức” để vượt qua yêu cầu pháp lý, điều kiện an toàn hoặc mốc ngừng hỗ trợ cố định.

### 4.1. Phân biệt mức khẩn cấp với mức quan trọng

- **Quan trọng nhưng chưa gấp:** Chuẩn bị nâng cấp runtime trước khi hết hỗ trợ trong vài tháng, bổ sung kiểm thử cho khu vực hay lỗi.
- **Gấp và quan trọng:** Dữ liệu đặt lịch bị sai trên production hoặc lỗ hổng đang gây ảnh hưởng.
- **Gấp nhưng ít giá trị:** Yêu cầu đổi biểu tượng vì một cuộc demo sát ngày, chưa gắn với kết quả chính.
- **Ít gấp và ít giá trị:** Tùy biến màn hình chưa có bằng chứng nhu cầu.

Việc có hạn ngày không có nghĩa mọi thay đổi sát hạn đều quan trọng ngang nhau. Nhóm cần xác định **ai đặt hạn, hậu quả nếu trễ và khả năng thương lượng**.

### 4.2. Chi phí trì hoãn cần được hiểu theo thời gian

Giả sử sửa lỗi tính phí sai làm giảm tổn thất mỗi ngày; việc trì hoãn một tuần có thể gây chi phí lớn. Còn một chức năng mới có thể mang giá trị trong nhiều tháng, nhưng sự khác biệt giữa phát hành tuần này và tuần sau nhỏ hơn. Một nâng cấp bảo mật có thể chưa tạo ảnh hưởng hôm nay nhưng có ngày bắt buộc. Tất cả đều là các **đường chi phí theo thời gian khác nhau**.

Vì vậy, ngay cả khi hai mục được đánh giá “giá trị cao”, thời điểm nên làm cũng có thể khác.

## 5. Xử lý lỗi: ưu tiên theo tác động, không chỉ theo độ khó sửa

Lỗi cần được triage dựa trên **hành vi sai, phạm vi ảnh hưởng, mức độ nghiêm trọng, khả năng tái hiện, phương án xử lý tạm (workaround) và rủi ro kinh doanh/kỹ thuật**. Một lỗi khó tái hiện nhưng có thể làm mất dữ liệu không nên bị bỏ qua vì “chưa tái hiện được trên máy dev”.

### 5.1. Severity và priority là hai khái niệm khác nhau

- **Severity (mức độ nghiêm trọng):** Lỗi gây thiệt hại hoặc làm hỏng hành vi đến mức nào.
- **Priority (thứ tự ưu tiên):** Khi nào và bằng cách nào tổ chức nên xử lý so với các việc khác, xét cả người dùng, rủi ro và ràng buộc.

| Ví dụ | Severity | Cách suy nghĩ về ưu tiên |
| --- | --- | --- |
| Tài khoản có thể xem dữ liệu riêng tư của tài khoản khác. | Rất cao | Cần đánh giá và ứng cứu ngay theo chính sách an toàn. |
| Đơn hàng có thể bị tạo hai lần khi retry, gây thanh toán trùng. | Cao | Ưu tiên cao; có thể cần giảm ảnh hưởng ngay trước khi sửa hoàn chỉnh. |
| Màn hình trang trí bị lệch ở trình duyệt ít dùng. | Thấp | Có thể gom xử lý theo đợt sau nếu không ảnh hưởng thao tác quan trọng. |
| Lỗi hiển thị nhỏ xuất hiện trong buổi trình diễn hợp đồng có nghĩa vụ cụ thể. | Thấp về kỹ thuật | Có thể có ưu tiên kinh doanh theo hạn, nhưng không nâng severity một cách giả tạo. |

Tên cấp P0/P1/P2 và thời hạn phản hồi **phải theo chính sách của tổ chức**, không có một định nghĩa phổ quát từ Agile. Với các lỗi nghiêm trọng, cần phối hợp vận hành, bảo mật hoặc chăm sóc khách hàng theo đúng quyền hạn.

### 5.2. Quy trình triage thực tế

1. **Xác nhận tác động:** Ai bị ảnh hưởng, bao nhiêu lượt, loại dữ liệu nào, có workaround không?
2. **Kiểm soát thiệt hại khi cần:** Tắt feature flag, rollback, chặn luồng nguy hiểm hoặc chuyển về phương án an toàn theo playbook.
3. **Ghi bằng chứng:** Phiên bản, thời điểm, bước tái hiện, log đã loại dữ liệu nhạy cảm, độ tin cậy và trạng thái.
4. **Quyết định ưu tiên và chủ sở hữu:** Ai điều phối sự cố, ai sửa, ai thông báo, cách xử lý công việc đang dở?
5. **Sửa và kiểm chứng:** Thử trường hợp gây lỗi, kiểm thử hồi quy, đánh giá tác động ngược, triển khai theo rủi ro.
6. **Học sau sự cố:** Xem vì sao không phát hiện sớm, cần cải tiến kiểm thử/giám sát hoặc kiến trúc nào.

Lỗi tồn tại không đồng nghĩa lúc nào cũng phải “dừng mọi tính năng”. Nhưng khi **ảnh hưởng tính toàn vẹn, bảo mật hoặc khả năng sử dụng cốt lõi**, trì hoãn cần có lý do rất rõ, cùng biện pháp kiểm soát rủi ro.

### 5.3. Phân biệt lỗi, thay đổi yêu cầu và cải tiến

Nếu hệ thống không đáp ứng **hành vi đã cam kết/đã chấp nhận**, đó là lỗi. Nếu bên liên quan muốn một hành vi mới khác với điều đã thống nhất, đó có thể là **thay đổi yêu cầu**. Nếu bản thân tiêu chí ban đầu mơ hồ, cần trao đổi để làm rõ vấn đề và quyết định. Không nên dùng nhãn “bug” để ép việc mới vào hàng khẩn; cũng không dùng nhãn “enhancement” để né khắc phục hành vi nguy hiểm.

## 6. Nợ kỹ thuật: nhìn thấy cả chi phí hiện tại và “lãi” trong tương lai

**Nợ kỹ thuật** là cách nói về những lựa chọn hoặc thiếu sót kỹ thuật khiến việc phát triển, vận hành hay thay đổi hệ thống về sau tốn công và rủi ro hơn. Nợ có thể **chủ động** chấp nhận trong một bối cảnh có thời hạn, hoặc **vô tình** tích tụ do thiếu kiến thức, áp lực và hệ thống cũ. Không phải mọi code cũ, mọi việc refactor hay mọi sở thích đổi công nghệ đều là nợ kỹ thuật cần ưu tiên.

Ví dụ trong sản phẩm đặt lịch:

- Một logic kiểm tra giờ trống bị lặp ở ba service khiến mỗi thay đổi phải sửa nhiều nơi.
- Bộ kiểm thử thiếu trường hợp request đồng thời khiến lỗi trùng lịch tái xuất.
- Hệ thống thiếu metric và cảnh báo, làm phát hiện sự cố muộn.
- Một thư viện quan trọng đã gần hết hỗ trợ và tăng rủi ro bảo mật, tương thích.
- Pipeline deploy thủ công dễ sai, kéo dài thời gian khôi phục.

### 6.1. Mô tả nợ kỹ thuật bằng hậu quả có thể kiểm chứng

Một đề xuất hữu ích không chỉ viết “refactor module đặt lịch”. Hãy ghi:

| Nội dung | Ví dụ |
| --- | --- |
| **Hiện trạng** | Có ba nơi triển khai quy tắc kiểm tra giờ trống khác nhau. |
| **Tác động quan sát được** | Hai trong bốn thay đổi gần đây phải sửa nhiều nơi; một lần bỏ sót tạo lỗi hồi quy. |
| **Rủi ro nếu tiếp tục** | Các lần thêm loại lịch mới dễ không nhất quán; cycle time tăng. |
| **Hành động nhỏ đề xuất** | Gom quy tắc dùng chung, bổ sung kiểm thử hợp đồng và cạnh tranh đồng thời. |
| **Chi phí/điều kiện** | Thực hiện theo lát cắt an toàn, cần giữ tương thích API hiện hành. |
| **Tín hiệu thành công** | Ít nơi phải sửa cho cùng quy tắc; kiểm thử hồi quy đạt; không tăng lỗi production. |

Cách mô tả này giúp Product Owner và Developers thảo luận về **giá trị giảm rủi ro và tăng khả năng giao**, thay vì tranh luận “có nên cho kỹ thuật làm việc riêng hay không”.

### 6.2. Không phải mọi khoản nợ đều có cùng mức cần trả

| Nhóm tình huống | Cách cân nhắc |
| --- | --- |
| Nợ trong khu vực sắp phải thay đổi nhiều, đã gây lỗi hoặc chậm đáng kể | Nên giải quyết trước hoặc cùng lúc với feature liên quan. |
| Nợ đang gây rủi ro an toàn, hết hỗ trợ hoặc nguy cơ mất dữ liệu | Ưu tiên theo mức rủi ro/nghĩa vụ; có thể cần xử lý ngay. |
| Nợ trong khu vực ổn định, rất ít thay đổi và rủi ro thấp | Có thể ghi nhận, theo dõi và không đầu tư lớn ngay. |
| Đề xuất “viết lại toàn bộ cho sạch” chưa có phương án giảm rủi ro | Cần chia nhỏ, đo tác động và so với lựa chọn cải tiến cục bộ. |

**Không có nghĩa vụ trả mọi khoản nợ ngay lập tức.** Mục tiêu là quản lý tổng chi phí sở hữu và khả năng thay đổi. Một số nợ có thể được chấp nhận trong giai đoạn thử nghiệm, nhưng phải biết **điểm nào khiến nó không còn chấp nhận được**.

### 6.3. Kết hợp trả nợ với công việc sản phẩm

Các cách làm thường hiệu quả:

1. **Boy Scout Rule:** Khi chạm một khu vực mã, cải thiện một phần nhỏ liên quan và an toàn, nếu không làm tăng rủi ro phạm vi.
2. **Refactor theo lát cắt:** Bảo vệ hành vi cũ bằng kiểm thử, cải tiến phần cần cho tính năng kế tiếp, tích hợp thường xuyên.
3. **Nâng cấp có chủ đích:** Đặt mốc thời gian trước khi hết hỗ trợ, dùng rollout giới hạn và kế hoạch rollback.
4. **Hạng mục nền tảng riêng có kết quả:** Khi thay đổi lớn hơn một feature, định nghĩa giá trị mở khóa, phạm vi và tiêu chí hoàn tất rõ.

Trong XP, **TDD, CI, refactoring, pair programming và thiết kế đơn giản** giúp giữ chi phí thay đổi thấp. Đây là thực hành phòng ngừa nợ, bên cạnh những công việc trả khoản nợ đã phát sinh.

## 7. Khám phá: ưu tiên thông tin trước khi ưu tiên giải pháp lớn

**Discovery** giúp hiểu nhu cầu, khả năng sử dụng, tính khả thi kỹ thuật và tính khả thi kinh doanh/vận hành. Nó có thể gồm phỏng vấn, quan sát, thử prototype, phân tích dữ liệu, khảo sát hợp đồng API và **spike có timebox**.

Ví dụ, nhóm muốn thêm thanh toán một chạm nhưng chưa biết đối tác hỗ trợ retry an toàn. Xây toàn bộ UI và backend trước khi kiểm tra khả năng API có thể tạo nhiều việc phải làm lại. Một spike kỹ thuật hai ngày để thử các tình huống idempotency có thể giúp chọn thiết kế hoặc điều chỉnh phạm vi.

### 7.1. Khi nào nên đưa discovery lên trước feature?

- Giả định có **mức bất định cao** và nếu sai sẽ gây chi phí hoặc rủi ro lớn.
- Chỉ cần một phép thử nhỏ có thể loại bỏ nhiều phương án đầu tư tốn kém.
- Cần làm rõ người dùng thật sự gặp vấn đề gì trước khi chốt chức năng.
- Có phụ thuộc hệ thống/đối tác chưa xác nhận, ảnh hưởng lớn tới kế hoạch giao.

Nếu tính năng nhỏ, dễ đảo ngược và có thể giao an toàn để lấy phản hồi, **không nhất thiết phải tạo một spike riêng**. Giao lát cắt nhỏ và quan sát kết quả cũng là cách học hỏi.

### 7.2. Một discovery item phải có cách kết thúc

| Thành phần | Ví dụ |
| --- | --- |
| **Quyết định bị chặn** | Có thể dùng API đối tác để đặt lịch mà không tạo trùng khi retry không? |
| **Giả định** | API hỗ trợ idempotency key hoặc truy vấn trạng thái sau timeout. |
| **Câu hỏi kiểm chứng** | Kết quả API trong trường hợp gửi lại, đồng thời, timeout? |
| **Timebox** | Tối đa hai ngày, kết thúc bằng báo cáo trong ngày thứ hai. |
| **Phạm vi** | Đọc hợp đồng, thử với dữ liệu sandbox; chưa viết hệ thống production. |
| **Tiêu chí dừng** | Có đủ bằng chứng chọn phương án hoặc hết timebox, ghi rõ điều chưa biết. |
| **Đầu ra** | Bằng chứng, đánh đổi, rủi ro còn lại, đề xuất thay đổi Product Backlog. |

**Timebox không bảo đảm sẽ tìm được câu trả lời**, nhưng bảo đảm nhóm dừng để xem lại giá trị của việc nghiên cứu. Một hạng mục “nghiên cứu công nghệ” kéo dài vô hạn, không có quyết định nào được hỗ trợ, là tín hiệu cần điều chỉnh.

### 7.3. Phân biệt kết quả học hỏi với Increment

Một prototype hoặc báo cáo spike có thể rất hữu ích để giảm bất định, nhưng **không tự động là phần mềm sản phẩm đã Done**. Scrum yêu cầu Increment đáp ứng Definition of Done. Mã thử nghiệm có thể cố ý bỏ qua một số yêu cầu để khảo sát nhanh; nếu dùng lại cho production, phải được đánh giá và hoàn thiện theo chuẩn chất lượng, bảo mật, vận hành.

Khám phá tốt có thể cho kết luận **“chưa làm”**: bằng chứng không ủng hộ giả thuyết, nên không xây feature đề xuất. Điều đó giúp nhóm tránh chi phí cơ hội và bảo trì dài hạn.

## 8. Các cách hỗ trợ sắp thứ tự: dùng để thảo luận, không để máy móc xếp hạng

Không có một công thức chung nào chuyển mọi loại công việc thành thứ tự đúng. Công cụ định tính hoặc định lượng giúp **phơi bày giả định và đánh đổi**.

### 8.1. Ma trận giá trị – công sức

Nhóm có thể đặt công việc theo tác động kỳ vọng và công sức tương đối:

| Nhóm | Gợi ý |
| --- | --- |
| **Giá trị cao, công sức thấp** | Thường xem xét làm sớm nếu không bị chặn và không xung đột nghĩa vụ khác. |
| **Giá trị cao, công sức cao** | Chia lát cắt, kiểm tra phụ thuộc và chọn lần giao đầu tiên tạo bằng chứng. |
| **Giá trị thấp, công sức thấp** | Có thể để sau; không nên chiếm WIP chỉ vì làm nhanh. |
| **Giá trị thấp, công sức cao** | Cân nhắc loại bỏ hoặc tìm giả định cần kiểm chứng trước. |

**Giới hạn:** Ma trận không xử lý tốt ngày bắt buộc, rủi ro mất dữ liệu hay chi phí trì hoãn tăng nhanh. Cần bổ sung các tiêu chí ở phần 4.

### 8.2. Cost of Delay và WSJF

**Cost of Delay** là giá trị hoặc tổn thất liên quan tới việc trì hoãn một hạng mục theo thời gian. Một kỹ thuật hỗ trợ so sánh là **Weighted Shortest Job First (WSJF)**: lấy một ước lượng tương đối về chi phí trì hoãn chia cho kích thước công việc. Trong một số cách triển khai, chi phí trì hoãn được xấp xỉ qua **giá trị kinh doanh, độ cấp bách theo thời gian và khả năng giảm rủi ro/mở cơ hội**.

Ví dụ **điểm tương đối giả định**, chỉ nhằm minh họa phép so sánh:

| Hạng mục | Chi phí trì hoãn tương đối | Kích thước tương đối | Tỉ số tham khảo |
| --- | ---: | ---: | ---: |
| Sửa lỗi xác nhận đặt lịch bị thất bại thường xuyên | 15 | 3 | 5,0 |
| Thử API để tránh kiến trúc sai | 10 | 2 | 5,0 |
| Tạo khả năng tự hủy lịch | 12 | 6 | 2,0 |
| Đổi giao diện trang trí | 3 | 3 | 1,0 |

Điểm số **không phải tiền thật, xác suất lỗi hay cam kết chính xác**. Các ước lượng dạng thang tương đối không luôn chia tỷ lệ tuyến tính; đội ngũ cần trao đổi nguồn dữ liệu và nhạy cảm với giả định. Hai mục cùng tỉ số 5,0 có thể được chọn khác nhau vì một mục có hạn pháp lý, phụ thuộc hoặc rủi ro cao hơn. Với sự cố an toàn khẩn cấp, **quy trình ứng cứu và nghĩa vụ bắt buộc** được ưu tiên theo chính sách, không chờ chấm WSJF.

### 8.3. MoSCoW và giới hạn của nhãn “Must”

MoSCoW chia nhu cầu thành **Must have**, **Should have**, **Could have**, **Won't have (for now)** trong một phạm vi thời gian/mục tiêu xác định. Nó hữu ích khi phải thương lượng phạm vi ở ngày giao cố định. Tuy vậy:

- “Must” phải gắn với điều kiện không thể phát hành hoặc không thể đạt kết quả tối thiểu nếu thiếu.
- Nếu 90% backlog đều được gắn Must, công cụ không còn giúp phân biệt ưu tiên.
- Nợ kỹ thuật hoặc bảo mật có thể là Must khi cần đạt chuẩn chất lượng và nghĩa vụ.
- Hạng mục Won't for now không có nghĩa ý tưởng vĩnh viễn vô giá trị; cần định nghĩa điều kiện xem lại.

### 8.4. Không dùng điểm số để che quyết định trách nhiệm

Trong Scrum, Product Owner chịu trách nhiệm sắp thứ tự Product Backlog; Developers cung cấp hiểu biết về kích thước, rủi ro, khả năng thực hiện, chất lượng và phụ thuộc. Những người hiểu nghiệp vụ, bảo mật, vận hành và người dùng đóng góp bằng chứng. Bảng điểm chỉ hỗ trợ đối thoại. **Một người đưa ra công thức** không tự động có quyền thay thế quyết định của các trách nhiệm đã được xác định.

## 9. Kế hoạch phân bổ năng lực: bảo vệ cả giá trị lẫn khả năng phản hồi

Không nên ép mọi Sprint phân bổ cùng một tỷ lệ phần trăm theo loại. Hãy bắt đầu bằng năng lực khả dụng, nhu cầu thực tế và rủi ro. Với nhóm bảo trì hệ thống lõi có nhiều sự cố, phần dành cho sửa lỗi/ổn định có thể lớn; nhóm làm sản phẩm mới ở giai đoạn khám phá có thể đầu tư nhiều hơn cho discovery.

### 9.1. Xác định năng lực thật, không tính 100% thời gian là làm feature

Năng lực khả dụng phải xét:

- Số ngày làm việc thực tế, nghỉ phép và các cuộc họp cần thiết.
- Công việc hỗ trợ khách hàng, trực sự cố, review và bảo trì theo lịch.
- Năng lực kỹ năng: không phải mọi người đều có thể thay nhau làm một loại việc.
- Độ bất định và lịch sử công việc đột xuất.
- Giới hạn WIP và thời gian chờ ngoài nhóm.

**Ví dụ giả định:** Nhóm bốn người có Sprint hai tuần, tổng thời gian lịch khoảng 40 người-ngày; sau khi trừ hoạt động chung và năng lực hỗ trợ thường xuyên, nhóm ước tính **32 người-ngày có thể lập kế hoạch cho các hạng mục**. Đây chỉ là một phép tính minh họa, không phải công thức năng suất.

### 9.2. Đặt năng lực cạnh các loại nhu cầu

| Hạng mục minh họa | Loại | Cơ sở ưu tiên | Công sức dự báo |
| --- | --- | --- | ---: |
| **B1 — Sửa lỗi đặt trùng khi retry** | Lỗi | Có tác động tới tính đúng đắn, rủi ro khách hàng và hỗ trợ | 5 người-ngày |
| **D1 — Kiểm thử cạnh tranh và đơn giản hóa logic giờ trống** | Nợ kỹ thuật / chất lượng | Giảm lỗi tái phát, hỗ trợ các lần đổi lịch sau | 6 người-ngày |
| **E1 — Spike API thay đổi lịch của đối tác** | Khám phá | Chặn quyết định thiết kế luồng đổi lịch | 3 người-ngày |
| **F1 — Lát cắt cho khách tự đổi lịch cơ bản** | Tính năng | Giảm cuộc gọi hỗ trợ và cải thiện trải nghiệm | 10 người-ngày |
| **F2 — Tùy biến màu sắc lịch** | Tính năng | Lợi ích hiện chưa có bằng chứng mạnh | 7 người-ngày |

Nhóm có thể dự kiến xử lý **B1 + D1 + E1 + F1 = 24 người-ngày**, giữ **8 người-ngày linh hoạt** trong dự báo năng lực 32 cho hỗ trợ/sự cố phát sinh và biến động công sức. **F2 chưa được đưa vào kế hoạch hiện tại.**

Đây không phải lời khuyên “luôn để đúng 25% dự phòng”. Khả năng dự phòng nên được điều chỉnh bằng dữ liệu lịch sử và mức bất định. Từng người-ngày chỉ là ước lượng tổng hợp; phụ thuộc, kỹ năng và năng lực review có thể khiến tổng công sức nhỏ vẫn không hoàn tất được trong lịch.

### 9.3. Sắp việc theo kết quả, không nhận danh sách cứng

Nếu nhóm dùng Scrum, hãy hỏi **Sprint Goal** có thể là gì thay vì tự động “cam kết đủ 24 người-ngày”. Ví dụ:

> **Sprint Goal minh họa:** “Luồng đặt và đổi lịch cơ bản có thể được kiểm chứng an toàn trên nhóm người dùng thử, không tạo lịch trùng khi gửi lại.”

Trong Sprint Planning, Scrum Team thống nhất mục tiêu có giá trị; Developers chọn các Product Backlog Item phù hợp để thực hiện và lập kế hoạch. Nếu E1 cho thấy API không hỗ trợ phương án F1 dự kiến, nhóm có thể thương lượng phạm vi với Product Owner để vẫn tiến tới Sprint Goal hoặc minh bạch trở ngại. **Không hạ Definition of Done** để ép F1 “xong”.

Nếu nhóm dùng Kanban, bốn loại việc cùng đi qua workflow rõ ràng, chính sách kéo việc và WIP limit. Một hạng mục khẩn cấp thực sự có thể theo chính sách riêng, nhưng việc mở nhiều mục mới không làm luồng hoàn tất nhanh hơn.

### 9.4. Khi xuất hiện thêm sự cố ngoài kế hoạch

Giả sử giữa Sprint xảy ra sự cố thanh toán liên quan tới luồng đặt lịch và cần khoảng **6 người-ngày** khắc phục, chưa tính tác động gián đoạn. Nhóm cần:

1. Kích hoạt chính sách ứng cứu và giảm thiệt hại theo thẩm quyền.
2. Kiểm tra năng lực còn lại, WIP hiện tại, phụ thuộc và tác động tới Sprint Goal.
3. Trao đổi với Product Owner về việc hoãn/làm nhỏ hạng mục khác; giữ chất lượng.
4. Cập nhật dự báo và thông tin cho bên liên quan; phân biệt sự cố đã kiểm soát với sửa lỗi gốc.
5. Sau đó kiểm tra nguyên nhân và xem có cần một khoản đầu tư kỹ thuật để tránh tái diễn.

Không nên cộng “6 người-ngày sự cố” lên kế hoạch đã đầy rồi đòi giữ nguyên ngày giao tất cả mọi thứ. Đây là lúc **thích ứng dựa trên dữ liệu và công khai đánh đổi**.

## 10. Chính sách xử lý việc ngoài kế hoạch và việc khẩn cấp

Một nhóm có thể định nghĩa các **lớp dịch vụ (classes of service)** hoặc chính sách ưu tiên riêng cho luồng công việc để tránh mỗi yêu cầu mới đều trở thành trường hợp ngoại lệ. Ví dụ:

| Lớp gợi ý | Điều kiện | Cách xử lý |
| --- | --- | --- |
| **Khẩn cấp thực sự (expedite)** | Sự cố nghiêm trọng đang ảnh hưởng dịch vụ, an toàn hoặc dữ liệu; đạt tiêu chí do tổ chức định nghĩa | Có người điều phối theo quyền hạn; giảm thiệt hại ngay; công khai việc bị gián đoạn. |
| **Có ngày hạn cố định** | API sẽ ngừng hỗ trợ hoặc nghĩa vụ hợp đồng/pháp lý có hạn | Lập kế hoạch đủ sớm theo rủi ro trễ hạn và phụ thuộc. |
| **Tiêu chuẩn** | Feature, lỗi thông thường, nợ kỹ thuật có giá trị nhưng không khẩn cấp | Sắp thứ tự chung, kéo khi có năng lực và ưu tiên hoàn tất. |
| **Khám phá/timebox** | Cần thông tin để quyết định việc lớn | Có câu hỏi, timebox, đầu ra và điểm chốt; quản lý WIP như công việc khác. |

Phân loại trên là **một chính sách có thể chọn**, không phải bộ lớp dịch vụ Agile bắt buộc. Nếu mọi thứ bị gắn nhãn “expedite”, lớp khẩn cấp mất ý nghĩa và công việc đang làm không bao giờ xong. Nhóm cần định kỳ xem tỷ lệ việc khẩn cấp, nguyên nhân và tác động lên cycle time.

### 10.1. Quy trình chuyển hướng minh bạch

~~~mermaid
flowchart TD
    A["Yêu cầu mới / lỗi / phát hiện rủi ro"] --> B["Làm rõ tác động và bằng chứng"]
    B --> C{"Có sự cố / nghĩa vụ khẩn cấp theo chính sách?"}
    C -->|Có| D["Ứng cứu hoặc xử lý hạn bắt buộc theo thẩm quyền"]
    C -->|Không| E["So giá trị, chi phí trì hoãn, rủi ro, công sức"]
    E --> F{"Có đủ thông tin để chọn?"}
    F -->|Chưa| G["Khám phá nhỏ có timebox hoặc làm rõ yêu cầu"]
    F -->|Có| H["Sắp thứ tự Product Backlog / workflow"]
    G --> H
    D --> I["Cập nhật tác động lên công việc hiện tại"]
    H --> I
    I --> J["Chọn lát cắt, kiểm thử, giao và đo kết quả"]
    J --> K["Học từ dữ liệu và xem lại thứ tự"]
    K --> B
~~~

Điểm quyết định quan trọng là **khi thêm việc phải nhìn thấy việc nào sẽ chờ**. Tính minh bạch này giảm xung đột giữa người yêu cầu tính năng, Developers và vận hành.

## 11. Scrum, Kanban và XP bổ sung nhau thế nào?

| Nhu cầu | Scrum có thể giúp | Kanban có thể giúp | XP có thể giúp |
| --- | --- | --- | --- |
| Tập trung một kết quả ngắn hạn | Product Goal, Sprint Goal, Sprint Planning và Review | Chính sách chọn việc, hướng kết quả và làm hiện rõ luồng | Chia lát cắt nhỏ, tích hợp thường xuyên |
| Sắp thứ tự công việc khác loại | Product Backlog có thứ tự, trách nhiệm Product Owner, refinement | Trực quan hóa ưu tiên, pull và lớp dịch vụ khi phù hợp | Cung cấp thông tin kỹ thuật và rủi ro để ưu tiên |
| Xử lý lỗi ngoài kế hoạch | Làm rõ tác động tới Sprint Goal; thương lượng phạm vi và giữ chất lượng | Nhìn WIP, chính sách expedite, công việc bị chặn | Kiểm thử hồi quy, CI, refactoring để sửa an toàn |
| Kiểm soát nợ kỹ thuật | Đưa nhu cầu giảm nợ vào Product Backlog theo giá trị sản phẩm; DoD | Theo dõi tắc nghẽn, công việc cải tiến, cycle time | TDD, CI, refactoring, thiết kế đơn giản, pair programming |
| Giảm bất định | Refinement, thí nghiệm phục vụ mục tiêu và Review | Timebox, hiển thị khám phá trong dòng, WIP | Spike kỹ thuật nhỏ và thử nghiệm tích hợp |
| Cải tiến liên tục | Sprint Retrospective | Các vòng phản hồi để điều chỉnh workflow và chính sách | Thực hành chất lượng, phản hồi nhanh ở cấp mã |

**Không đánh đồng Scrum với chỉ làm tính năng theo Sprint**, Kanban với chỉ sửa bug, hoặc XP với chỉ viết test. Cả ba có thể bổ trợ cho một hệ thống làm việc chung nếu nhóm hiểu vấn đề và giới hạn của từng thực hành.

### 11.1. Trách nhiệm quyết định trong Scrum

Theo Scrum Guide 2020:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị của sản phẩm và quản lý hiệu quả Product Backlog, bao gồm truyền đạt mục tiêu và sắp thứ tự các mục.
- **Developers** chịu trách nhiệm tạo kế hoạch cho Sprint, duy trì chất lượng bằng Definition of Done, điều chỉnh kế hoạch hằng ngày và tạo Increment có giá trị.
- **Scrum Master** hỗ trợ nhóm và tổ chức hiểu, vận dụng Scrum hiệu quả, có thể giúp xử lý trở ngại và cải tiến cách phối hợp.

Người làm sản phẩm không nên tự áp đặt giải pháp kỹ thuật bất chấp rủi ro; người kỹ thuật không nên tự ưu tiên một dự án viết lại lớn mà không làm rõ giá trị và tác động với Product Owner. Trong công việc có nghĩa vụ vận hành, bảo mật hoặc hợp đồng, cần tôn trọng quyền hạn chuyên môn và cơ chế ra quyết định của tổ chức.

### 11.2. Chất lượng không phải ngân sách có thể cắt tùy ý

Đôi khi nhóm nói “Sprint này dành 0% cho kiểm thử để làm nhiều feature hơn”. Nhưng **kiểm thử cần để đạt DoD** không phải một loại việc tùy chọn ngang với backlog cải tiến. Tương tự, xử lý quyền truy cập đúng và dữ liệu cá nhân là điều kiện bắt buộc của hệ thống phù hợp. Phân bổ năng lực cho nợ kỹ thuật nên nói về **cải tiến bổ sung có giá trị** ngoài chuẩn chất lượng tối thiểu, thay vì coi mọi kiểm thử là khoản “nợ kỹ thuật có thể hoãn”.

## 12. Đo lường cân bằng bằng kết quả, dòng công việc và chất lượng

Nếu chỉ đếm số feature giao được, nhóm sẽ có động cơ dời lỗi và nợ kỹ thuật. Nếu chỉ đếm số bug sửa được, nhóm có thể ưu tiên lỗi nhỏ dễ đóng. Nếu chỉ đếm số spike, nhóm có thể nghiên cứu mãi mà không quyết định.

Một bảng theo dõi tốt có ít chỉ số nhưng trả lời được **quyết định thực tế**:

| Góc nhìn | Chỉ số/tín hiệu tham khảo | Cần tránh suy diễn |
| --- | --- | --- |
| **Giá trị sản phẩm** | Tỷ lệ hoàn tất tác vụ, thời gian người dùng thực hiện việc, sử dụng tính năng, yêu cầu hỗ trợ, mục tiêu kinh doanh | Số tính năng lớn không chứng minh người dùng nhận nhiều giá trị hơn. |
| **Chất lượng và độ tin cậy** | Tỷ lệ lỗi, lỗi nghiêm trọng lặp lại, thời gian khôi phục, độ trễ, mức đạt SLO | Số bug mở ít có thể do ghi nhận kém chứ không phải hệ thống ít lỗi. |
| **Dòng công việc** | Lead time, cycle time, throughput, WIP, thời gian bị chặn | Kích thước ticket và mốc đo khác nhau làm so sánh thiếu ý nghĩa. |
| **Khả năng thay đổi** | Lỗi hồi quy, tần suất triển khai phù hợp, thời gian đưa thay đổi tới production, điểm nghẽn review/CI | Nhanh hơn chưa chắc tốt nếu tỷ lệ lỗi tăng. |
| **Nợ kỹ thuật** | Thời gian sửa khu vực thay đổi thường xuyên, sự cố do cấu trúc, thời gian CI, thư viện hết hỗ trợ | Không biến số dòng refactor thành thước đo giá trị. |
| **Khám phá** | Giả định được xác minh/bác bỏ, quyết định backlog được điều chỉnh, timebox và độ rõ của rủi ro còn lại | Nhiều buổi phỏng vấn hoặc nhiều báo cáo chưa chứng minh có học hỏi hữu ích. |
| **Tải ngoài kế hoạch** | Tỷ trọng năng lực bị sự cố chiếm dụng, số lần expedite, WIP bị ngắt | Cần hiểu loại sự cố, mức ảnh hưởng và cách đo; không đổ lỗi cá nhân. |

**Ví dụ sử dụng dữ liệu:** Nếu tỷ trọng công việc khẩn cấp tăng và cycle time feature kéo dài, nhóm cần xem vì sao sự cố xuất hiện, chỗ nào thiếu kiểm thử hoặc giám sát. Một khoản đầu tư giảm nợ kỹ thuật có thể được ưu tiên để bảo vệ khả năng giao trong các Sprint tiếp theo. Ngược lại, nếu sản phẩm ổn định nhưng các tính năng ít người dùng, vấn đề có thể nằm ở discovery và lựa chọn giá trị.

### 12.1. Phân biệt các chỉ số dòng công việc

- **Lead time:** Thời gian từ một mốc bắt đầu thống nhất (chẳng hạn khi yêu cầu được chấp nhận) đến mốc hoàn tất thống nhất.
- **Cycle time:** Thời gian từ khi bắt đầu xử lý thực sự tới khi hoàn tất theo định nghĩa nhóm.
- **Throughput:** Số hạng mục hoàn tất trong khoảng thời gian, với cách chia việc tương đối nhất quán.
- **WIP:** Những hạng mục đã bắt đầu nhưng chưa hoàn tất tại thời điểm quan sát.

Các chỉ số phải được diễn giải trong bối cảnh. Thêm một sự cố phức tạp có thể làm cycle time trung bình tăng dù nhóm đã xử lý đúng ưu tiên. Nên xem phân bố và xu hướng, không chỉ một con số trung bình.

### 12.2. DORA và khả năng giao thay đổi

Nghiên cứu **DORA** cung cấp nhóm chỉ số và kiến thức về năng lực giao phần mềm, như thời gian đưa thay đổi tới production, tần suất triển khai, tỷ lệ thất bại khi thay đổi và khả năng phục hồi. Chúng hữu ích để xem đầu tư kỹ thuật có giúp giao thay đổi **nhanh và đáng tin** hơn không. Chỉ số delivery phải đứng bên cạnh **outcome sản phẩm**; triển khai nhiều lần không tự chứng minh sản phẩm hữu ích.

## 13. Những ngộ nhận làm sai lệch ưu tiên

| Ngộ nhận | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “Chỉ tính năng mới tạo giá trị.” | Lỗi và nợ tích tụ; tốc độ phát triển về sau giảm. | Gắn chất lượng, giảm rủi ro và khả năng thay đổi với giá trị sản phẩm. |
| “Bug nào cũng ưu tiên hơn feature.” | Lỗi nhỏ chiếm hết năng lực, mục tiêu sản phẩm bị đình trệ. | Triage theo tác động và mức khẩn cấp, có chính sách xử lý phù hợp. |
| “Sửa lỗi sau khi story Done vẫn được, tách ticket sau.” | Increment không đạt chuẩn, báo cáo sai chất lượng. | Giữ DoD, sửa hành vi cần thiết trước khi coi công việc Done. |
| “Mọi nợ kỹ thuật đều cần trả ngay.” | Có thể đầu tư vào khu vực ít thay đổi thay vì mục tiêu quan trọng. | Ưu tiên theo rủi ro, chi phí thay đổi và giá trị mở khóa. |
| “Nợ kỹ thuật chỉ do lập trình viên thiếu kỷ luật.” | Đổ lỗi, bỏ qua áp lực hệ thống và quyết định sản phẩm. | Xem nguyên nhân tổ chức, phụ thuộc, DoD, kiến trúc và cơ chế ưu tiên. |
| “Discovery chỉ làm trước dự án.” | Xây nhiều chức năng dựa trên giả định chưa được kiểm chứng. | Khám phá liên tục, timebox những giả định có ảnh hưởng lớn. |
| “Spike nào cũng cần code để chứng minh.” | Tốn công xây prototype khi câu hỏi thực ra là nhu cầu người dùng. | Chọn đúng phương pháp: quan sát, phỏng vấn, phân tích hoặc thử kỹ thuật. |
| “Đã phân bổ 20% cho tech debt thì không cần xem lại.” | Tỷ lệ cứng không phù hợp khi rủi ro và nhu cầu đổi. | Sử dụng dữ liệu nhu cầu, chất lượng, công việc khẩn và mục tiêu để điều chỉnh. |
| “Một công thức cho ra thứ tự khách quan tuyệt đối.” | Điểm số che rủi ro bảo mật, nghĩa vụ và bằng chứng yếu. | Dùng điểm làm đầu vào thảo luận; ghi lý do và quyền quyết định rõ. |
| “Thêm việc gấp không ảnh hưởng tiến độ việc khác.” | WIP tăng, chuyển ngữ cảnh và dự báo không đáng tin. | Công khai việc bị hoãn, giảm phạm vi hoặc điều chỉnh kế hoạch. |
| “Đo năng suất bằng story point hoặc số bug đóng.” | Đội ngũ tối ưu nhãn và điểm thay vì giá trị. | Dùng các chỉ số làm tín hiệu cải tiến hệ thống, không xếp hạng cá nhân. |

## 14. Bài tập thực hành

### Tình huống A — Feature quan trọng và lỗi nghiêm trọng cạnh tranh năng lực

Nhóm muốn phát hành khả năng tự đổi lịch vào thứ Sáu. Thứ Ba, phát hiện luồng đặt lịch hiện tại có nguy cơ tạo lịch trùng khi mạng chậm. Product Owner cho rằng tính năng mới đã được quảng bá nên phải ưu tiên; Developers lo rủi ro dữ liệu.

**Câu hỏi:**

1. Cần xác minh ảnh hưởng và mức khẩn cấp của lỗi như thế nào?
2. Điều nào là chuẩn chất lượng/điều kiện an toàn, điều nào là chức năng mới có thể thương lượng?
3. Có cách chia nhỏ phát hành để bảo vệ mục tiêu không?
4. Ai cần tham gia quyết định và thông báo tác động tới lịch?

**Hướng xử lý tham khảo:** Kiểm tra số trường hợp bị ảnh hưởng, khả năng mất dữ liệu, phương án tắt/rollback và kiểm thử tái hiện. Nếu rủi ro nghiêm trọng, ưu tiên kiểm soát thiệt hại và sửa lỗi. Trao đổi với Product Owner và người chịu trách nhiệm phát hành về việc giảm phạm vi tính năng mới, trì hoãn hoặc rollout giới hạn. Không coi nguy cơ tạo lịch trùng là lỗi trang trí có thể để sau chỉ vì ngày quảng bá.

### Tình huống B — Đề xuất viết lại hệ thống

Một kỹ sư muốn viết lại toàn bộ module đặt lịch vì code “không sạch”. Nhóm đang có backlog tính năng giá trị cao và chưa có dữ liệu đo số lần thay đổi gây lỗi ở module này.

**Câu hỏi:**

1. Thông tin nào cần bổ sung để đánh giá khoản nợ?
2. Có thể chọn lát cắt kỹ thuật nhỏ, đo rủi ro và giảm chi phí thay vì viết lại hết không?
3. Làm sao so khoản đầu tư này với các feature hiện tại?

**Hướng xử lý tham khảo:** Thu thập lịch sử lỗi, thời gian thay đổi, phạm vi test, khu vực hay phải sửa, vấn đề vận hành và phụ thuộc. Thử viết kiểm thử bảo vệ hành vi rồi refactor phần sẽ dùng cho tính năng kế tiếp. Chỉ cân nhắc viết lại lớn khi có luận cứ giá trị, kế hoạch chuyển đổi, thử nghiệm và phương án khôi phục.

### Tình huống C — Mọi việc đều được đánh dấu khẩn cấp

Nhóm Kanban có bảng “Đang làm” đầy, hàng đợi Review tăng. Bộ phận kinh doanh, hỗ trợ và vận hành đều yêu cầu được gắn nhãn expedite. Cycle time tăng trong bốn tuần liên tiếp.

**Câu hỏi:**

1. Cần định nghĩa lại chính sách expedite theo dấu hiệu nào?
2. Có nên kéo thêm việc vào “Đang làm” để chứng tỏ nhóm phản ứng nhanh?
3. Cần xem chỉ số nào sau khi thay đổi chính sách?

**Hướng xử lý tham khảo:** Thống nhất tiêu chí khẩn cấp theo ảnh hưởng, nghĩa vụ và rủi ro. Đặt WIP limit phù hợp, ưu tiên hoàn tất việc đang bị chặn và phân loại ngày hạn cố định riêng. Theo dõi số lần expedite, thời gian chờ Review, WIP, phân bố cycle time và lỗi; cải tiến chính sách qua các vòng phản hồi.

### Tình huống D — Feature lớn dựa trên giả định yếu

Một công ty muốn đầu tư sáu tuần vào chatbot vì tin rằng người dùng sẽ thích. Số liệu hỗ trợ hiện cho thấy nhiều câu hỏi liên quan trạng thái đơn hàng, nhưng chưa biết người dùng muốn hội thoại hay trang tự phục vụ.

**Câu hỏi:**

1. Giả định lớn nhất là gì và sai thì mất gì?
2. Một discovery timebox nhỏ có thể dùng phương pháp nào?
3. Khi nào kết luận “không làm chatbot” lại là thành công?

**Hướng xử lý tham khảo:** Quan sát tác vụ hỗ trợ thật, kiểm tra chủ đề câu hỏi lặp, phỏng vấn có mục đích và thử prototype đơn giản theo tiêu chí thành công rõ. So một trang tra cứu tự phục vụ với phương án hội thoại trên chất lượng giải quyết vấn đề, chi phí và quyền riêng tư. Không phát triển chatbot nếu bằng chứng cho thấy lựa chọn khác tạo giá trị tốt hơn.

### Bài tập nhóm — Lập thứ tự một backlog hỗn hợp

Chọn ít nhất một hạng mục mỗi loại. Điền bảng:

| Hạng mục | Giá trị/tác động | Mức khẩn cấp và chi phí trì hoãn | Bằng chứng còn thiếu | Kích thước/phụ thuộc | Quyết định và lý do |
| --- | --- | --- | --- | --- | --- |
| Feature | ... | ... | ... | ... | ... |
| Bug | ... | ... | ... | ... | ... |
| Nợ kỹ thuật | ... | ... | ... | ... | ... |
| Discovery | ... | ... | ... | ... | ... |

Sau đó hỏi: **Nếu ngày mai phát sinh một sự cố thật sự khẩn cấp, việc nào sẽ hoãn?** Nhóm nên giải thích được không chỉ **thứ tự**, mà cả **chi phí cơ hội, giả định và điều kiện xem lại**.

## 15. Mẫu buổi refinement và quyết định ưu tiên

Một cuộc trao đổi ngắn có thể đi theo các bước:

1. **Nhắc Product Goal/kết quả đang ưu tiên** và ràng buộc không được vi phạm.
2. **Nhìn tín hiệu thực tế:** Chỉ số sản phẩm, lỗi đang ảnh hưởng, điểm nghẽn, cảnh báo chất lượng và giả định chưa được kiểm chứng.
3. **Triage hạng mục mới:** Đó là lỗi, tính năng, giảm nợ hay khảo sát? Có trường hợp khẩn cấp theo chính sách không?
4. **Làm rõ giá trị và bằng chứng:** Mục tiêu, người dùng, chi phí trì hoãn và mức tin cậy.
5. **Chia nhỏ/cân nhắc phụ thuộc:** Có lát cắt sớm hoặc khảo sát timebox giúp giảm rủi ro không?
6. **Xếp thứ tự và kiểm tra năng lực:** Công việc nào sẽ không được bắt đầu hoặc phải dừng khi ưu tiên đổi?
7. **Chốt và giao tiếp:** Ai quyết định, ai thực hiện, tiêu chí hoàn tất và thời điểm xem lại?

Mẫu ghi quyết định:

~~~text
Mục tiêu sản phẩm        : Khách đặt và đổi lịch tin cậy, ít cần tổng đài.
Tín hiệu mới             : Có lỗi tạo lịch trùng khi retry.
Tác động                 : Ảnh hưởng tính đúng đắn; mức độ đang được xác minh.
Các lựa chọn             : Sửa ngay / chặn chức năng rủi ro / trì hoãn feature.
Giá trị và chi phí hoãn  : Giảm giao dịch lỗi, hỗ trợ và mất lòng tin.
Phụ thuộc / năng lực     : Cần backend, QA, vận hành; ảnh hưởng F1.
Quyết định               : Ưu tiên giảm thiệt hại và sửa lỗi; điều chỉnh F1.
Người chịu trách nhiệm   : ...
Tiêu chí hoàn tất        : Không tạo lịch trùng trong các trường hợp kiểm thử;
                           kiểm tra hồi quy và quan sát sau triển khai.
Thời điểm xem lại        : Sau khi kiểm chứng tác động và kết quả sửa.
~~~

Đây là mẫu linh hoạt, không phải thủ tục phải điền cho mọi ticket nhỏ. Nhóm cần **quyết định rõ, thông tin đủ dùng và khả năng kiểm chứng**, tránh tạo báo cáo phức tạp hơn chính công việc.

## 16. Checklist kiểm tra cân bằng backlog

- [ ] Product Goal và kết quả mong muốn đủ rõ để so các loại việc khác nhau.
- [ ] Tính năng, lỗi, nợ kỹ thuật và khám phá đều **hiển thị** trong kế hoạch năng lực.
- [ ] Lỗi được triage theo tác động và rủi ro; có chính sách sự cố khẩn cấp.
- [ ] Không coi một story chưa đạt DoD là Done rồi đẩy lỗi sang vòng sau.
- [ ] Nợ kỹ thuật được diễn đạt bằng chi phí, rủi ro hoặc khả năng mở khóa giá trị.
- [ ] Spike/discovery có câu hỏi quyết định, timebox, tiêu chí dừng và đầu ra.
- [ ] Hạng mục có bằng chứng, mức tin cậy và chi phí trì hoãn tương xứng với rủi ro.
- [ ] Những việc lớn đã được cân nhắc chia nhỏ để giao hoặc học sớm.
- [ ] Khi thêm việc, có quyết định minh bạch về việc sẽ hoãn hoặc giảm phạm vi.
- [ ] Chất lượng, bảo mật và nghĩa vụ bắt buộc được giữ trong Definition of Done/chính sách.
- [ ] WIP và năng lực thực tế được kiểm tra; không phụ thuộc vào làm thêm giờ thường xuyên.
- [ ] Có chỉ số outcome, chất lượng và dòng công việc để xem lại quyết định.
- [ ] Product Owner, Developers, vận hành và bên liên quan hiểu trách nhiệm của mình.

## 17. Ghi nhớ

**Cân bằng backlog là cân bằng cách tạo và bảo vệ giá trị trong những khoảng thời gian khác nhau.** Tính năng mang lại khả năng mới; lỗi cần được sửa theo tác động; nợ kỹ thuật ảnh hưởng khả năng thay đổi và độ tin cậy về sau; khám phá giúp tránh đầu tư lớn dựa trên giả định sai. Không một loại nào mặc nhiên “luôn quan trọng nhất”, nhưng sự cố an toàn, nghĩa vụ bắt buộc và tiêu chuẩn chất lượng cần được xử lý theo ràng buộc rõ ràng.

Nhóm Agile tốt không phải nhóm giao nhiều story nhất trong mỗi Sprint. Đó là nhóm **biết vì sao mình làm việc này trước việc kia, giao được lát cắt hữu ích và an toàn, học từ phản hồi, nhìn thấy công việc đang tắc và cập nhật kế hoạch minh bạch**. Scrum giúp gắn ưu tiên với mục tiêu và trách nhiệm; Kanban giúp thấy và quản lý dòng công việc; XP giúp giữ chi phí thay đổi thấp bằng kỷ luật kỹ thuật.

### Tài liệu nền tảng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — ưu tiên phần mềm hoạt động được, cộng tác và đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao giá trị sớm, kỹ thuật xuất sắc, đơn giản và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Backlog, trách nhiệm Product Owner/Developers, Sprint Goal và Definition of Done.
- [The Kanban Guide](https://kanbanguides.org/) — workflow, WIP, các thước đo dòng và cải tiến có phản hồi.
- [Agile Alliance — Technical Debt](https://agilealliance.org/glossary/technical-debt/) — thuật ngữ và bối cảnh của nợ kỹ thuật.
- [Agile Alliance — Spike](https://agilealliance.org/glossary/spike/) — công việc tìm hiểu một bất định có giới hạn.
- [DORA](https://dora.dev/) — nghiên cứu về khả năng giao phần mềm nhanh và đáng tin cậy.
