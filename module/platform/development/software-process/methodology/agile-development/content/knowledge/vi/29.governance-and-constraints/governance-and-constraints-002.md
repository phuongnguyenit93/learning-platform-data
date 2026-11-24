# Lập ngân sách theo khả năng học hỏi và giá trị cần kiểm chứng

## 1. Vì sao lập ngân sách cố định theo danh sách tính năng có thể tạo rủi ro?

Một tổ chức phát triển nền tảng học lập trình dự định đầu tư vào tính năng **“Tiếp tục học”**. Kế hoạch ban đầu gồm trang tổng quan cá nhân, nút mở lại bài gần nhất, email nhắc học, gợi ý bài tiếp theo và báo cáo tiến độ. Ban điều hành yêu cầu nhóm lập chi phí, ngày giao và cam kết hoàn tất toàn bộ danh sách trước khi cấp ngân sách.

Trong khi đó, nhóm sản phẩm mới chỉ có một số phản hồi rằng học viên thường bỏ dở khóa học. Họ chưa biết nguyên nhân chính là **khó tìm lại bài cũ, nội dung không phù hợp, lịch học bận rộn, lỗi lưu tiến độ hay yếu tố khác**.

Nếu cấp toàn bộ kinh phí cho một giải pháp chưa được kiểm chứng, tổ chức có thể:

- Chi nhiều tiền để phát triển các tính năng ít người cần.
- Tạo áp lực giữ nguyên phạm vi dù phản hồi sớm cho thấy giả thuyết sai.
- Đo mức hoàn thành bằng số hạng mục giao đúng kế hoạch thay vì thay đổi có ích với người học.
- Xem việc dừng một ý tưởng không hiệu quả là thất bại, trong khi **dừng sớm** có thể tránh lãng phí lớn.
- Cắt chi phí kiểm thử, bảo mật hoặc vận hành để “đủ ngân sách” vào cuối dự án.

Một cách tiếp cận phù hợp với **Agile** là cấp và điều chỉnh nguồn lực theo **những quyết định cần học hỏi, giá trị cần xác minh và rủi ro cần giảm**. Tổ chức vẫn lập ngân sách, vẫn kiểm soát chi phí và chịu trách nhiệm giải trình; điều thay đổi là **không mặc định một bản danh sách tính năng cố định chính là giá trị đã được chứng minh**.

Trong chương **Quản trị và ràng buộc**, thuộc module **AGILE_DEVELOPMENT**, bài học này liên kết các nguyên tắc phản hồi sớm, giao Increment nhỏ và cải tiến liên tục với cách quản trị đầu tư. Những thực hành như user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc giúp nhóm tạo bằng chứng để **tiếp tục, điều chỉnh hoặc dừng** khoản đầu tư một cách có trách nhiệm.

### Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt **ngân sách, dự báo, chi phí thực tế, nguồn lực cam kết và giá trị kỳ vọng**.
2. Giải thích cách chuyển từ tư duy **“trả tiền để hoàn tất phạm vi”** sang **“đầu tư có giới hạn để kiểm chứng giả thuyết và tạo outcome”**.
3. Thiết kế các **đợt cấp kinh phí có điều kiện** gắn với cột mốc học hỏi, Increment dùng được và bằng chứng giá trị.
4. Phân tích **bất định, mức rủi ro, chi phí chờ quyết định, khả năng đảo ngược và chi phí cơ hội** khi ưu tiên đầu tư.
5. Xây dựng một bản đề xuất thử nghiệm có **trần chi, thời hạn, owner, phép đo, guardrails và quyền quyết định**.
6. Dùng phản hồi từ Scrum, Kanban, XP và môi trường vận hành để cập nhật kế hoạch tài chính mà không bỏ kiểm soát bắt buộc.
7. Tránh các phản mẫu như **đồng nhất số story point với tiền, đo học hỏi bằng số cuộc phỏng vấn, hoặc tiếp tục chi vì đã chi nhiều**.

## 2. Các khái niệm tài chính cần phân biệt trước khi thảo luận Agile

| Khái niệm | Ý nghĩa trong bài | Ví dụ minh họa |
|---|---|---|
| **Budget — Ngân sách** | Giới hạn nguồn lực/chi phí được phép sử dụng trong phạm vi và thời kỳ được duyệt. | Tối đa 1,2 tỷ đồng cho một chương trình theo điều kiện quản trị. |
| **Funding — Cấp kinh phí** | Quyết định phân bổ hoặc cho phép sử dụng một phần nguồn lực. | Cho phép dùng tối đa 120 triệu đồng để khám phá vấn đề. |
| **Forecast — Dự báo** | Ước lượng chi phí, thời gian hoặc outcome có thể xảy ra dựa trên hiểu biết hiện tại. | Chi phí xây và thử một lát sản phẩm khoảng 180–240 triệu đồng. |
| **Actual cost — Chi phí thực tế** | Chi phí đã phát sinh và được ghi nhận theo quy tắc kế toán áp dụng. | Đã phát sinh 95 triệu đồng trong giai đoạn thử. |
| **Commitment — Cam kết chi** | Khoản nghĩa vụ/chi phí đã cam kết nhưng có thể chưa được ghi nhận là actual. | Hợp đồng dịch vụ thử nghiệm còn nghĩa vụ thanh toán 25 triệu đồng. |
| **Contingency — Dự phòng** | Phần ngân sách giữ lại cho tình huống chưa chắc, theo quyền và chính sách dùng dự phòng. | Quỹ dự phòng rủi ro tích hợp hoặc thay đổi chi phí đối tác. |
| **Runway** | Khoảng thời gian nhóm có thể duy trì với nguồn lực còn sẵn theo một mức chi tiêu xác định. | Nguồn lực khả dụng đủ duy trì nhóm khoảng vài tháng ở burn rate hiện tại. |
| **Outcome** | Hành vi, trải nghiệm hoặc trạng thái có giá trị được cải thiện. | Tỷ lệ học viên quay lại một hoạt động học có ý nghĩa tăng. |
| **Impact** | Lợi ích lớn hơn, dài hạn hơn mà outcome góp phần tạo nên. | Học viên nâng năng lực và hoàn thành lộ trình có chất lượng. |
| **Value at risk** | Giá trị hoặc thiệt hại có thể bị ảnh hưởng khi giả định sai hoặc xảy ra sự cố. | Tổn hại dữ liệu học viên, uy tín hoặc chất lượng dịch vụ. |

**Ngân sách được duyệt không đồng nghĩa tiền đã chi; dự báo không đồng nghĩa cam kết; Increment đã giao không đồng nghĩa outcome đã đạt.** Không phân biệt những trạng thái đó khiến nhóm ra quyết định sai.

### 2.1. Một khoản chi có thể hợp lý dù chưa tạo doanh thu ngay

Đầu tư cải thiện CI, sửa lỗi phân quyền, kiểm chứng accessibility hoặc giảm rủi ro mất dữ liệu có thể không làm doanh thu tăng ngay trong kỳ đo. Tuy nhiên, những khoản đó có thể bảo vệ giá trị người dùng, duy trì khả năng thay đổi và đáp ứng nghĩa vụ bắt buộc.

Vì vậy, **không dùng doanh thu ngắn hạn làm thước đo duy nhất cho mọi hạng mục**. Hãy xác định mục đích khoản đầu tư: khám phá, tạo giá trị, cải thiện chất lượng, giảm rủi ro hay duy trì năng lực dịch vụ.

### 2.2. Chi phí kế toán và chi phí quản trị không luôn trùng nhau

Một nhóm sản phẩm có lương nhân sự, hạ tầng, giấy phép, chi phí đối tác và chi phí vận hành. Cách phân loại thành **chi phí hoạt động, tài sản vốn hóa, hợp đồng hay chi phí nội bộ** phụ thuộc chế độ kế toán, chính sách và nghĩa vụ áp dụng.

Bài học này hướng tới **quyết định sản phẩm và quản trị Agile**, không đặt ra một chuẩn kế toán hoặc khuyến nghị pháp lý. Khi lập ngân sách thật, cần phối hợp tài chính, mua sắm, bảo mật và các bộ phận có thẩm quyền.

## 3. Đầu tư vào giả thuyết giá trị thay vì cam kết mù vào giải pháp

Trước khi xin cấp toàn bộ ngân sách cho một tập chức năng, nhóm nên biểu diễn **chuỗi giả thuyết tạo giá trị**:

~~~mermaid
flowchart TD
    A["Vấn đề người dùng và cơ hội"] --> B["Giả thuyết nguyên nhân"]
    B --> C["Giả thuyết giải pháp"]
    C --> D["Thử nghiệm có trần chi và thời hạn"]
    D --> E["Bằng chứng: hành vi, chất lượng, rủi ro"]
    E --> F{"Quyết định đầu tư"}
    F -->|Tiếp tục có điều kiện| G["Increment/lát giá trị tiếp theo"]
    F -->|Điều chỉnh| H["Đổi giả thuyết hoặc phạm vi"]
    F -->|Dừng| I["Bảo toàn nguồn lực, ghi bài học"]
    G --> J["Quan sát outcome khi sử dụng thật"]
    J --> E
    H --> B
~~~

Ví dụ:

> **Vấn đề:** nhiều học viên không quay lại sau khi ngắt quãng.
>
> **Giả thuyết:** một phần đáng kể bỏ dở vì khó tìm lại bài đang học.
>
> **Giải pháp thử:** hiển thị chính xác bài gần nhất và một hành động “Tiếp tục học” dễ truy cập.
>
> **Bằng chứng mong muốn:** học viên tìm lại đúng bài nhanh hơn và tỷ lệ quay lại hoạt động học có ý nghĩa trong bảy ngày tăng, trong khi lỗi mất tiến độ, quyền riêng tư và khả năng truy cập không suy giảm.

Nếu giả thuyết được bác bỏ, nhóm có thể thử hướng khác như cải thiện chất lượng nội dung hoặc sửa lỗi lưu tiến độ. **Ngân sách nên cho phép thay đổi đường đi tới Product Goal trong phạm vi thẩm quyền**, chứ không bắt mọi đồng đã duyệt phải biến thành tính năng ban đầu.

### 3.1. Một hoạt động học hỏi phải hỗ trợ quyết định

“Đã phỏng vấn 20 người” là **activity**. “Đã viết báo cáo 30 trang” là **output**. Những tín hiệu này hữu ích để theo dõi công việc nhưng **chưa đủ** để biện minh cho khoản đầu tư kế tiếp.

Một cột mốc học hỏi tốt cần trả lời:

- Giả thuyết nào đã được kiểm tra?
- Dữ liệu nào ủng hộ hoặc không ủng hộ?
- Độ tin cậy, giới hạn và mẫu quan sát ra sao?
- Quyết định nào đổi đi từ bằng chứng đó?
- Còn rủi ro nào phải kiểm chứng trước khi tăng ngân sách?

**Học hỏi có giá trị không phải số lượng thử nghiệm; đó là khả năng giảm bất định để ra quyết định tốt hơn.**

## 4. Những loại bất định làm thay đổi cách cấp ngân sách

Không phải mọi khoản đầu tư cần cùng một cơ chế kiểm chứng. Một bản sửa lỗi nghiêm trọng đã được xác nhận khác với giả thuyết thị trường hoàn toàn mới.

| Loại bất định | Câu hỏi | Thực hành phù hợp |
|---|---|---|
| **Desirability — Nhu cầu/giá trị** | Người dùng có thực sự cần giải pháp? | Phỏng vấn, quan sát, nguyên mẫu, thí điểm hợp lệ và đo outcome. |
| **Usability/accessibility — Khả năng sử dụng và tiếp cận** | Người dùng có hoàn tất tác vụ đúng và công bằng? | Thử hành trình, bàn phím, công nghệ hỗ trợ, đo lỗi/ma sát. |
| **Feasibility — Khả thi kỹ thuật** | Hệ thống có thực hiện đúng với giới hạn hiệu năng/dữ liệu không? | Spike, kiểm thử tích hợp, tải, kiến trúc thử có kiểm chứng. |
| **Viability — Tính khả thi kinh tế** | Lợi ích có đủ phù hợp chi phí và mục tiêu tổ chức? | Ước lượng chi phí vòng đời, giá trị biên, kịch bản kinh tế. |
| **Compliance/security — Nghĩa vụ và an toàn** | Điều gì bắt buộc phải đáp ứng? | Đánh giá yêu cầu, kiểm soát, thử xâm nhập/phân quyền khi thích hợp. |
| **Delivery/operability — Khả năng đưa vào sử dụng** | Có thể bàn giao và vận hành đáng tin cậy không? | CI/CD, quan sát, runbook, thử phục hồi và phụ thuộc. |
| **Adoption/causality — Mức tiếp cận và nguyên nhân** | Sử dụng có tạo outcome do giải pháp không? | Instrumentation, cohort, so sánh phù hợp, thí nghiệm khi an toàn. |

### 4.1. Câu hỏi quyết định nên đến trước công cụ

Nếu chưa biết học viên có gặp khó vì tìm lại bài không, **chi tiền dựng một hệ thống gợi ý AI lớn** có thể là thử nghiệm quá đắt. Một số cuộc quan sát có phương pháp và nguyên mẫu có thể giúp loại bớt giả thuyết với chi phí thấp hơn.

Nếu đã biết lỗi mất dữ liệu đang xảy ra, **không nên kéo dài khám phá chỉ để đạt chỉ tiêu phỏng vấn**. Lúc này, cần ưu tiên sửa và kiểm chứng an toàn theo rủi ro.

### 4.2. Không phải mọi rủi ro đều được phép “thử với người dùng thật”

Một tổ chức có thể kiểm tra thông điệp giao diện qua A/B test hợp lệ, nhưng không nên cố ý giữ lỗ hổng lộ dữ liệu cho nhóm đối chứng chỉ để tính hiệu quả. **Bảo vệ an toàn, quyền riêng tư và nghĩa vụ pháp lý có thể là ràng buộc không được đánh đổi**, bất kể giả thuyết kinh tế hấp dẫn đến đâu.

## 5. Phân biệt tài trợ dự án đầu ra và tài trợ năng lực tạo giá trị

### 5.1. Tài trợ theo danh sách đầu ra

Một cách truyền thống:

> “Cấp 800 triệu đồng để bàn giao 12 tính năng theo tài liệu vào ngày đã định.”

Ưu điểm có thể là dễ lập lịch, ký hợp đồng hoặc tổ chức hoạt động có phạm vi tương đối ổn định. Hạn chế là **quyết định có thể bị khóa vào danh sách giải pháp**, ngay cả khi người dùng phản hồi khác dự kiến.

### 5.2. Tài trợ theo mục tiêu và năng lực

Một cách tiếp cận khác:

> “Dành một trần ngân sách và năng lực nhóm trong giai đoạn xác định để cải thiện việc học viên quay lại học, với các checkpoint dựa trên outcome, chất lượng và mức bất định đã giảm.”

Tổ chức có thể cấp kinh phí cho một **đội sản phẩm ổn định** thay vì luôn lập dự án mới cho từng tính năng; Product Owner và stakeholders sắp backlog để tối đa hóa giá trị theo Product Goal. Cách này có thể giảm thời gian thay đội hình và tăng trách nhiệm xuyên suốt sản phẩm.

Tuy nhiên:

- Tài trợ đội lâu dài **không có nghĩa cấp tiền vô thời hạn**.
- Sự ổn định đội không thay thế checkpoint tài chính và trách nhiệm giải trình.
- Một phạm vi hợp đồng cố định vẫn có thể cần phương án nghiệm thu rõ.
- Những khoản đầu tư an toàn hoặc hạ tầng bắt buộc không nhất thiết có outcome thương mại trực tiếp trong ngắn hạn.

### 5.3. So sánh để chọn cơ chế phù hợp

| Bối cảnh | Cơ chế tài trợ có thể phù hợp | Điều cần lưu ý |
|---|---|---|
| Thay đổi tính năng còn nhiều bất định | Trần khám phá nhỏ, rồi cấp theo bằng chứng. | Không ép chốt mọi chức năng trước khi có học hỏi. |
| Sản phẩm duy trì liên tục | Năng lực đội ổn định trong ngân sách theo kỳ, checkpoint outcome. | Quản trị burn rate, giá trị và chất lượng lâu dài. |
| Công việc có đầu ra kiểm chứng rõ, phụ thuộc ổn định | Phạm vi/mốc tài chính theo hợp đồng hoặc gói việc. | Có điều khoản xử lý thay đổi và tiêu chuẩn nghiệm thu. |
| Yêu cầu pháp lý/bảo mật bắt buộc | Kinh phí tuân thủ với mốc kiểm chứng, quyền và thời hạn rõ. | Không đặt nghĩa vụ bắt buộc vào hàng chờ thí nghiệm giá trị tùy chọn. |
| Nâng cấp nền tảng nhiều đội dùng | Funding theo năng lực chung, adoption và giảm nút thắt/rủi ro. | Phân biệt đầu ra kỹ thuật với lợi ích thực của đội tiêu thụ. |
| Khai phá cơ hội kinh doanh chưa có bằng chứng | Khoản đầu tư nhỏ cho nghiên cứu/smoke test/giả thuyết. | Đặt tiêu chí dừng trước khi chi lớn. |

**Agile không yêu cầu bỏ kế hoạch ngân sách năm hoặc hủy mọi hợp đồng cố định.** Tư duy Agile giúp phần **phạm vi và giả thuyết còn bất định** được kiểm soát bằng phản hồi và quyết định tăng dần.

## 6. Nguyên tắc cấp kinh phí theo từng đợt có điều kiện

Một cách tổ chức hữu ích là **incremental funding**: phân bổ kinh phí cho các giai đoạn có quyết định rõ, thay vì mặc nhiên sử dụng hết tổng ngân sách.

### 6.1. Một khung ba giai đoạn

| Giai đoạn | Mục tiêu chính | Bằng chứng để ra quyết định tiếp |
|---|---|---|
| **Khám phá** | Xác định vấn đề và những giả thuyết có rủi ro cao nhất. | Dữ liệu người dùng, mức ảnh hưởng, nguyên nhân khả dĩ, ràng buộc. |
| **Thí điểm có kiểm soát** | Kiểm chứng một lát giải pháp có thể sử dụng, với chất lượng phù hợp. | Adoption, hành vi, hiệu năng, bảo mật, accessibility, chi phí vận hành. |
| **Mở rộng hoặc đổi hướng** | Gia tăng giá trị nếu bằng chứng đủ mạnh; điều chỉnh/dừng nếu không. | Outcome qua đủ cửa sổ, chi phí biên, rủi ro, năng lực hỗ trợ và khả năng duy trì. |

Mỗi giai đoạn cần:

1. **Người có quyền quyết định** có thẩm quyền tài chính thực.
2. **Giới hạn chi và thời hạn** được phê duyệt.
3. **Những câu hỏi học hỏi chính**, không chỉ danh sách công việc.
4. **Điều kiện chất lượng và pháp lý bắt buộc**.
5. **Bằng chứng và ngưỡng xem xét** có định nghĩa đủ rõ.
6. **Các phương án**: tiếp tục, sửa phạm vi, thử thêm, dừng hoặc tái phân bổ.

### 6.2. Cấp tiếp không phải thưởng cho người báo số đẹp

Nếu nhóm chỉ được cấp tiền khi báo một giả thuyết “đúng”, họ có động cơ bỏ qua tín hiệu phản bác. Một cơ chế trưởng thành đánh giá **chất lượng bằng chứng và quyết định**, kể cả khi quyết định tốt nhất là không tiếp tục.

Ví dụ, giai đoạn khám phá có thể hoàn tất thành công khi chứng minh rằng **nguyên nhân bỏ học chủ yếu không liên quan nút tiếp tục**, nhờ vậy tổ chức tránh chi ngân sách lớn cho giải pháp sai.

### 6.3. Không biến checkpoint thành hàng chờ phê duyệt mới

Nếu nhóm cần xin phê duyệt chi tiết cho từng user story, mỗi vòng học hỏi lại chậm vài tuần. Có thể **ủy quyền trong trần ngân sách, phạm vi rủi ro và chính sách đã duyệt**, chỉ yêu cầu cấp quyết định cao hơn khi vượt ngưỡng.

Thời điểm checkpoint nên căn cứ **mức tiêu tiền, độ bất định và rủi ro**, không tổ chức một buổi họp nghi thức sau mọi commit hoặc mọi Sprint.

## 7. Learning milestone: cột mốc phải giúp quyết định, không chỉ chứng minh bận rộn

Một **learning milestone** mô tả bằng chứng nào cần có trước khi tổ chức tăng mức đầu tư.

### 7.1. Cột mốc yếu và cột mốc mạnh

| Cột mốc yếu | Cột mốc mạnh hơn |
|---|---|
| “Phỏng vấn 20 học viên.” | “Có đủ bằng chứng để xác định nguyên nhân trọng yếu của việc không quay lại, kèm các giả thuyết đã bị bác bỏ và mức tin cậy.” |
| “Làm prototype trong hai tuần.” | “Người dùng mục tiêu thử hoàn tất luồng tìm bài cũ; nhóm quan sát ma sát và xác định có đáng xây Increment không.” |
| “Đóng 15 story.” | “Increment tích hợp, đạt DoD và đủ điều kiện mở thử để học về một hành vi cụ thể.” |
| “Triển khai 5 lần.” | “Nhóm có thể đưa thay đổi nhỏ an toàn và thu phản hồi mà không làm tăng sự cố không chấp nhận.” |
| “Dashboard đã hoàn tất.” | “Định nghĩa chỉ số, nguồn dữ liệu và guardrails đủ tin để hỗ trợ quyết định mở rộng hoặc sửa giải pháp.” |
| “Chi hết kinh phí nghiên cứu.” | “Các giả định quan trọng được đánh giá, kết quả bất định được nêu rõ và có khuyến nghị tiếp theo.” |

### 7.2. Một milestone tốt có tiêu chí hủy

Trước khi thử, nhóm cần hỏi:

- Nếu kết quả **không cải thiện**, điều gì sẽ khiến ta dừng?
- Nếu hiệu quả nhỏ hơn chi phí, có thay đổi phạm vi để giảm chi không?
- Nếu dữ liệu yếu, có đáng chi thêm để đo hay nên chuyển sang giả thuyết khác?
- Nếu guardrail xấu đi, có phải dừng ngay và bảo vệ người dùng không?
- Ai có quyền thực hiện quyết định và báo lại cho tài chính/stakeholder?

**Một milestone không có khả năng dẫn tới quyết định “dừng” dễ trở thành nghi thức hợp thức hóa khoản chi đã định sẵn.**

## 8. Lập ngân sách theo độ lớn của điều chưa biết

Một nguyên tắc thực dụng là **chi khoản nhỏ nhất đủ để đạt bằng chứng cần thiết cho quyết định kế tiếp**, với các ràng buộc an toàn đầy đủ. Điều này khác với việc luôn chọn giải pháp rẻ nhất bất kể chất lượng.

### 8.1. Những cấp độ kiểm chứng minh họa

| Câu hỏi | Cách kiểm chứng có thể thử | Lý do chưa nên đầu tư lớn |
|---|---|---|
| Học viên có khó tìm bài cũ không? | Quan sát hành trình, phỏng vấn có cấu trúc, phân tích dữ liệu hiện có. | Có thể nguyên nhân nằm nơi khác. |
| Nút tiếp tục có giúp? | Nguyên mẫu tương tác, kiểm thử khả năng dùng và accessibility. | Không cần ngay hệ thống gợi ý phức tạp. |
| Có thể khôi phục tiến độ đúng? | Spike, integration test và tình huống lỗi mạng. | Nên giảm rủi ro dữ liệu trước mở rộng. |
| Người dùng có thật sự học tiếp? | Increment đủ chất lượng mở thử cho phạm vi được phép, đo cohort. | Click nút không đủ chứng minh outcome. |
| Có nên mở rộng toàn hệ thống? | Đánh giá outcome, guardrails, chi phí biên và vận hành. | Mở rộng có thể làm tải và chi phí thay đổi phi tuyến. |

### 8.2. Spike không được tự động xem là sản phẩm sẵn sàng

Một **spike** là hoạt động khám phá kỹ thuật có giới hạn để giảm bất định. Prototype có thể không đáp ứng toàn bộ tiêu chuẩn production; không được lén đưa nó tới người dùng thật khi thiếu những kiểm soát bắt buộc.

Đầu ra đáng mong đợi từ spike là **bằng chứng, các lựa chọn, mức rủi ro còn lại và quyết định kế tiếp**, không phải số dòng mã hoặc số ngày đã dùng.

### 8.3. Khi nào thử nghiệm nhỏ không còn rẻ?

Một thử nghiệm có vẻ nhỏ về mã nhưng đòi hỏi tích hợp với dữ liệu nhạy cảm, xin phép pháp lý, huấn luyện hỗ trợ khách hàng hoặc thay đổi migration có thể mang chi phí lớn. Đánh giá **tổng chi phí thực tế và hậu quả có thể xảy ra**, không chỉ chi phí lập trình.

## 9. Một ngân sách có giới hạn nhưng có quyền đổi thứ tự backlog

Giả sử hội đồng duyệt một **trần đầu tư giả định 1.200 triệu đồng (1,2 tỷ)** trong thời kỳ xác định cho sáng kiến giúp học viên duy trì tiến độ. Trần này **không phải** cam kết sẽ chi đủ.

| Nhóm phân bổ quản trị minh họa | Trần dự kiến (triệu đồng) | Mục đích |
|---|---:|---|
| Khám phá vấn đề và xây baseline | 120 | Nghiên cứu, đo hiện trạng, xác định rủi ro. |
| Thí điểm một lát sản phẩm | 240 | Increment đủ chất lượng, kiểm chứng hành vi có kiểm soát. |
| Mở rộng có điều kiện khi có bằng chứng | 420 | Mở phạm vi, tối ưu và hỗ trợ sản phẩm khi được duyệt. |
| Chất lượng, bảo mật và vận hành xuyên suốt | 240 | CI, kiểm thử, quan sát, quyền riêng tư, khả năng phục hồi. |
| Dự phòng được kiểm soát | 180 | Rủi ro và biến động được phép xử lý theo thẩm quyền. |
| **Tổng trần** | **1.200** | **Không đồng nghĩa đã được phép sử dụng mọi khoản ngay**. |

**Tất cả các khoản trên là ví dụ học tập**, không phản ánh ngân sách, đơn giá hay chính sách của doanh nghiệp thật.

### 9.1. Đừng hiểu “chất lượng xuyên suốt” là giai đoạn cuối

Khoản 240 triệu cho chất lượng/vận hành được **lập kế hoạch xuyên suốt** các giai đoạn, không phải chờ thí điểm xong mới được kiểm thử bảo mật hoặc triển khai an toàn. Những kiểm soát thiết yếu vẫn phải có từ Increment đầu.

Nếu các chi phí chất lượng cần thiết lớn hơn dự tính, tổ chức cần **điều chỉnh phạm vi, nguồn lực hoặc quyết định đầu tư một cách minh bạch**; không tự bỏ tiêu chuẩn để giữ bảng chi đúng đẹp.

### 9.2. Tiền trong tổng trần khác tiền đã được giải phóng

Một chính sách có thể quy định:

- Đợt khám phá được phép dùng đến **120 triệu** theo hạn và mục tiêu rõ.
- Đợt thí điểm **chưa tự động được cấp**; phải xem bằng chứng và khả năng vận hành.
- Phần mở rộng chỉ được giải phóng theo quyết định mới.
- Chi phí an toàn bắt buộc có đường phê duyệt phù hợp, không chờ đến khi sản phẩm có doanh thu.
- Dự phòng 180 triệu có owner và điều kiện sử dụng riêng.

Đây là **một cách tổ chức thẩm quyền**, không phải bắt buộc của Scrum hay Agile.

## 10. Theo dõi số đã chi, số đã cam kết và số còn có thể quyết định

Giả sử trong trần 1.200 triệu đồng:

- Đã phát sinh và ghi nhận **410 triệu**.
- Có nghĩa vụ chi **65 triệu** chưa ghi nhận là actual.
- Chưa có khoản nào khác được tính trùng vào hai mục trên.

~~~text
Tổng trần được duyệt                        = 1.200 triệu
Actual đã ghi nhận                          =   410 triệu
Commitment chưa ghi nhận                    =    65 triệu
Phần còn lại theo trần sau hai khoản trên   =   725 triệu

1.200 - 410 - 65 = 725 (triệu đồng)
~~~

**725 triệu đồng không tự động là “tiền rảnh được chi ngay”.** Trong đó có thể có khoản dự phòng, ngân sách chưa được giải phóng, nghĩa vụ khác chưa cập nhật hoặc mức chi cần duyệt lại. Bảng quản trị cần thêm thông tin:

| Trường theo dõi | Ý nghĩa |
|---|---|
| Trần toàn kỳ | Giới hạn đầu tư đã duyệt. |
| Đã cấp cho giai đoạn hiện tại | Phần có thể sử dụng theo thẩm quyền. |
| Actual | Chi phí đã phát sinh và được ghi nhận đúng quy tắc. |
| Committed | Khoản nghĩa vụ dự kiến theo hợp đồng/đơn đặt hàng, không tính trùng actual. |
| Forecast to complete | Dự báo nguồn lực còn cần để đạt outcome hoặc mốc tiếp theo. |
| Contingency còn lại | Phần dự phòng và điều kiện mở dự phòng. |
| Unreleased envelope | Phần trần chưa được quyền sử dụng. |
| Variance và nguyên nhân | Khác biệt giữa dự tính và thực tế cùng bối cảnh. |

### 10.1. Burn rate và runway

Nếu một đội có **nguồn lực khả dụng thực sự 360 triệu đồng** và đang chi bình quân **90 triệu đồng/tháng**, phép chia đơn giản cho:

~~~text
Runway minh họa = 360 / 90 = 4 tháng
~~~

Đây chỉ là phép tính theo mức tiêu hao không đổi. Runway thật thay đổi theo hợp đồng, ngày thanh toán, cơ cấu nhân sự, chi phí hạ tầng, cam kết đã có và khả năng tiếp cận tiền. **Không được dùng tổng ngân sách chưa giải phóng làm nguồn lực khả dụng** khi tính runway.

### 10.2. Budget variance không tự nói khoản đầu tư tốt hay xấu

Chi ít hơn kế hoạch có thể là tiết kiệm do học được rằng không cần chức năng, nhưng cũng có thể vì không có người làm hoặc chậm đạt giá trị. Chi nhiều hơn dự báo có thể là sai quản trị, hoặc do một yêu cầu bảo mật bắt buộc mới lộ ra.

Vì vậy, cần xem **chi phí cùng bằng chứng tiến bộ về giá trị, rủi ro và năng lực bàn giao**, không chỉ số phần trăm dùng ngân sách.

## 11. Quyền quyết định và governance: linh hoạt phải đi cùng trách nhiệm giải trình

**Governance** không đồng nghĩa với nhiều cửa phê duyệt; nó là cách thiết lập mục tiêu, quyền quyết định, ràng buộc, kiểm soát rủi ro và trách nhiệm giải trình. Trong mô hình cấp ngân sách theo học hỏi, cần làm rõ:

| Quyết định | Người/nhóm có thể tham gia | Điều không nên để mơ hồ |
|---|---|---|
| **Chiến lược và trần đầu tư** | Ban lãnh đạo, bộ phận tài chính và chủ sở hữu danh mục theo tổ chức. | Ai có quyền duyệt/tăng trần hoặc thay đổi mục tiêu? |
| **Giá trị và thứ tự Product Backlog** | Product Owner theo accountability Scrum, phối hợp stakeholders. | Ai quyết định ưu tiên để tối đa hóa giá trị sản phẩm? |
| **Cách triển khai kỹ thuật** | Developers/đội kỹ thuật theo trách nhiệm và chính sách. | Ai chịu trách nhiệm chất lượng, kiến trúc và giải pháp? |
| **Bảo mật, pháp lý, dữ liệu** | Chuyên gia và người có thẩm quyền theo quy định. | Kiểm soát nào không thể tự ý bỏ, ai duyệt ngoại lệ hợp lệ? |
| **Dùng dự phòng hoặc vượt ngưỡng** | Cấp được ủy quyền theo chính sách tài chính. | Ngưỡng nào cần trình lại? |
| **Tiếp tục/đổi hướng/dừng giai đoạn** | Người có quyền quyết định đầu tư, dựa trên đề xuất và bằng chứng từ nhóm. | Cần thông tin nào, khi nào quyết định và ai thông báo? |
| **Ghi nhận chi phí và hợp đồng** | Tài chính/mua sắm và bên có thẩm quyền. | Cách phân loại, nghiệm thu và nghĩa vụ ghi nhận? |

### 11.1. Không nhầm vai trò Product Owner với người duyệt mọi khoản tiền

Trong Scrum, **Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog**, nhưng điều đó không tự trao quyền phê duyệt mọi khoản chi vượt chính sách tổ chức. Cần có **delegation of authority (ủy quyền quyết định)** rõ ràng và không áp đặt một cấu trúc công ty duy nhất lên Scrum.

### 11.2. Một RACI hay ma trận quyết định chỉ hữu ích nếu đi kèm quyền thực

Nếu bản đồ trách nhiệm ghi Product Owner chịu trách nhiệm outcome nhưng người này không thể tiếp cận dữ liệu hoặc thay đổi thứ tự backlog trong phạm vi cho phép, mô hình dễ trở thành hình thức.

Hãy bảo đảm:

- Người quyết định có thông tin và quyền phù hợp.
- Đội có không gian thử nghiệm trong trần đã duyệt.
- Các rủi ro bắt buộc có chủ thể chịu trách nhiệm.
- Đường tăng cấp khi vượt trần hoặc mâu thuẫn ưu tiên rõ ràng.
- Quyết định và bằng chứng được ghi tại nguồn dễ truy vết.

## 12. Xác định “đủ bằng chứng” cho một quyết định cấp tiếp

Một checkpoint tốt nên **được định nghĩa trước khi nhóm biết kết quả** để giảm nguy cơ thay tiêu chuẩn theo số liệu vừa xuất hiện.

### 12.1. Bốn câu hỏi nền tảng

1. **Giá trị:** người dùng có thực sự được lợi ở hành vi quan trọng không?
2. **Khả thi:** hệ thống có thực hiện ổn định, an toàn và có khả năng truy cập trong phạm vi định mở rộng không?
3. **Kinh tế:** lợi ích tiềm năng, chi phí biên và rủi ro có còn phù hợp trần đầu tư?
4. **Bằng chứng:** số liệu có đủ mẫu, đủ cửa sổ, định nghĩa ổn định và giới hạn được nêu rõ không?

### 12.2. Ví dụ decision gate cho tính năng “Tiếp tục học”

| Trường | Quy ước minh họa |
|---|---|
| **Primary outcome** | Tỷ lệ học viên đủ điều kiện hoàn thành ít nhất một hoạt động học có ý nghĩa trong bảy ngày. |
| **Baseline** | Đo trên cohort đã trưởng thành, cùng định nghĩa. |
| **Chỉ số hỗ trợ** | Tỷ lệ nhìn thấy nút, tỷ lệ mở đúng bài, thời gian tìm lại bài. |
| **Guardrails** | Không tăng lỗi mất tiến độ, truy cập trái quyền, rào cản bàn phím hoặc độ trễ không chấp nhận được. |
| **Chi phí** | Actual, commitment và forecast tới mốc tiếp theo còn trong quyền được duyệt. |
| **Độ tin cậy** | Đủ cửa sổ và bằng chứng để không hiểu sai một biến động ngẫu nhiên; có phân tích nhóm người dùng liên quan. |
| **Quyết định** | Tiếp tục, điều chỉnh, thu thêm bằng chứng hoặc dừng; ghi lý do và người có thẩm quyền. |

Đừng đặt một tỷ lệ cải thiện cố định cho mọi sản phẩm. Ngưỡng mục tiêu phải phản ánh **baseline, hiệu ứng tối thiểu có ý nghĩa, chi phí, rủi ro và thiết kế kiểm chứng**.

### 12.3. Dữ liệu chưa chắc cần được nói thật

Nếu chỉ có 18 học viên thử chức năng và 3 người báo thấy hữu ích, không thể suy ra tỷ lệ người dùng toàn hệ thống hưởng lợi tương ứng. Trong báo cáo hãy ghi **phạm vi, giới hạn và câu hỏi còn mở**.

Tài trợ theo học hỏi khuyến khích công khai **negative evidence** (bằng chứng phản bác) thay vì biến mọi kiểm tra thành câu chuyện thành công.

## 13. Phép đo outcome: tránh biến hoạt động thành giá trị giả

Với sản phẩm học trực tuyến, có thể phân biệt:

| Tầng | Ví dụ chỉ số | Câu hỏi thực sự trả lời |
|---|---|---|
| **Hoạt động** | Số người được phỏng vấn, số lần refinement, giờ phát triển. | Đã thực hiện những việc gì? |
| **Đầu ra** | User story Done, số Increment, tính năng đã release. | Đã tạo được khả năng gì? |
| **Tiếp cận/adoption** | Tỷ lệ học viên đủ điều kiện nhìn thấy và dùng tính năng. | Giải pháp có được tiếp cận không? |
| **Outcome gần** | Thời gian tìm bài cũ giảm, tỷ lệ mở đúng bài tăng. | Trải nghiệm trực tiếp có tốt lên? |
| **Outcome sản phẩm** | Tỷ lệ quay lại hoạt động học có ý nghĩa trong bảy ngày. | Hành vi liên quan Product Goal có đổi? |
| **Impact dài hạn** | Duy trì kiến thức hoặc hoàn thành lộ trình có chất lượng. | Sản phẩm góp phần tạo lợi ích dài hạn nào? |
| **Guardrail** | Lỗi mất tiến độ, truy cập sai quyền, độ trễ, phàn nàn của nhóm dùng công nghệ hỗ trợ. | Việc cải thiện chỉ số chính có gây hại không? |

### 13.1. Ví dụ định nghĩa tỷ lệ quay lại

~~~text
Tỷ lệ quay lại học có ý nghĩa trong 7 ngày =
  Số học viên đủ điều kiện thực sự hoàn thành >= 1 hoạt động
  học được xác minh trong cửa sổ 7 ngày
  / Tổng số học viên đủ điều kiện đã có đủ 7 ngày quan sát
  × 100%
~~~

Phải quy định **“đủ điều kiện”**, mốc bắt đầu cửa sổ, đơn vị đếm người duy nhất, loại trừ tài khoản thử và cách xử lý thiếu/trùng sự kiện. Không thể so sánh hai cohort nếu một bên tính lượt click còn bên kia tính người thực sự hoàn thành.

### 13.2. Guardrail có thể làm thay đổi quyết định đầu tư

Giả sử tỷ lệ quay lại học tăng nhưng 3% giao dịch khôi phục tiến độ trả bài sai. Tổ chức không nên mở rộng chỉ vì **primary outcome** đẹp hơn; lỗi dữ liệu có thể gây mất niềm tin hoặc thiệt hại học tập.

**Giá trị được kiểm chứng phải là giá trị có thể cung cấp trong giới hạn an toàn và chất lượng đã thỏa thuận.**

## 14. Outcome tăng không chứng minh khoản đầu tư gây ra toàn bộ mức tăng

Giả sử tỷ lệ quay lại học của một cohort tăng từ **24% lên 32%** sau khi mở thử:

~~~text
Thay đổi tuyệt đối = 32% - 24% = 8 điểm phần trăm
Thay đổi tương đối = (32 - 24) / 24 × 100% ≈ 33,3%
~~~

Con số trên **chỉ là ví dụ giả định**. Nó chưa chứng minh tính năng “Tiếp tục học” tạo ra toàn bộ mức tăng. Hai giai đoạn có thể khác về mùa thi, nội dung khóa, chiến dịch nhắc học, nhóm người dùng hoặc công cụ tracking.

### 14.1. Khi đánh giá, cần xem ít nhất

- **Cohort:** những người có cơ hội tương đương để đạt outcome không?
- **Cửa sổ:** tất cả người được đo đã có đủ bảy ngày quan sát chưa?
- **Định nghĩa dữ liệu:** event “học có ý nghĩa” có được ghi thống nhất không?
- **Phân khúc:** kết quả có xấu đi với thiết bị cũ hoặc người dùng có nhu cầu truy cập đặc biệt không?
- **Tác động ngoài:** nội dung, thông báo, giá cả hoặc lịch học thay đổi cùng lúc không?
- **Độ không chắc chắn:** cỡ mẫu và biến thiên có cho phép kết luận tương xứng không?

### 14.2. Thử nghiệm có kiểm soát khi phù hợp

A/B test ngẫu nhiên hợp lệ có thể hỗ trợ ước lượng tác động của một thay đổi UI rủi ro thấp, nếu tổ chức có cơ sở pháp lý/đạo đức và năng lực thiết kế thử nghiệm. Nhưng không phải mọi khoản đầu tư cần hoặc được phép A/B test.

**Không giữ lại bản sửa lỗi an toàn bắt buộc cho nhóm đối chứng chỉ để chứng minh ROI**. Với hoạt động giảm rủi ro, bằng chứng có thể đến từ kiểm chứng kỹ thuật, đánh giá kiểm soát và quan sát chất lượng thích hợp.

## 15. Cost of delay: giá của việc chờ, nhưng đừng bịa độ chính xác

**Cost of Delay (CoD)** là cách tư duy về **giá trị bị mất hoặc thiệt hại tăng khi trì hoãn một cơ hội hoặc biện pháp khắc phục**. Nó giúp nhóm so sánh những việc có độ nhạy thời gian khác nhau.

Ví dụ:

- Mỗi tuần chậm sửa một lỗi nghiêm trọng có thể kéo dài tác động tới người dùng.
- Chậm ra tính năng phục vụ một kỳ thi có thể làm lỡ cửa sổ giá trị.
- Chậm thử giả thuyết có thể khiến đội tiếp tục đầu tư vào hướng sai.
- Trì hoãn một công cụ nội bộ gây lặp thao tác có thể tiếp tục tiêu tốn năng lực.

### 15.1. Cost of delay không phải lúc nào cũng quy được ra tiền

Một trường hợp ảnh hưởng quyền riêng tư hoặc an toàn không nên chỉ được xếp thứ tự bằng **doanh thu dự kiến mỗi ngày**. Một số hậu quả có ngưỡng không thể đánh đổi hoặc khó định giá đáng tin.

Nếu số liệu yếu, có thể thảo luận **mức độ khẩn, cửa sổ cơ hội, độ rủi ro và thứ tự tương đối**, ghi rõ cơ sở giả định thay vì trình bày một con số tiền chính xác giả tạo.

### 15.2. Ví dụ tính đơn giản, chỉ để luyện tư duy

Giả sử một lỗi buộc bộ phận hỗ trợ xử lý thủ công thêm **100 yêu cầu mỗi tháng**, mỗi yêu cầu tiêu tốn thêm **12 phút làm việc**. Năng lực bổ sung là:

~~~text
100 yêu cầu × 12 phút = 1.200 phút/tháng
                         = 20 giờ làm việc/tháng
~~~

Nếu chi phí nhân công phân bổ giả định là **200.000 đồng/giờ**:

~~~text
Giá trị năng lực giải phóng tối đa theo giả định =
  20 giờ × 200.000 đồng/giờ
  = 4.000.000 đồng/tháng
~~~

**Đây không tự động là 4 triệu đồng tiết kiệm tiền mặt.** Năng lực được giải phóng có thể dùng vào hỗ trợ tốt hơn mà không làm giảm chi phí tiền lương; số yêu cầu cũng có thể biến động, và các chi phí sửa/duy trì giải pháp chưa được tính.

### 15.3. Ưu tiên theo chi phí chờ và khả năng tạo bằng chứng sớm

Một thử nghiệm 20 triệu đồng trong một tuần có thể đáng làm trước một hạng mục 300 triệu đồng nếu nó **giải quyết bất định trọng yếu** để quyết định có nên đầu tư 300 triệu hay không. Nhưng nếu thử nghiệm nhỏ không kiểm tra được rủi ro thực, nó chỉ tạo ảo giác tiết kiệm.

**Tối ưu quyết định và dòng tạo giá trị**, không mặc định “rẻ và nhanh” luôn tốt.

## 16. Ước lượng ROI, điểm hòa vốn và chi phí cơ hội có trách nhiệm

Khi có dữ liệu đủ tin, tổ chức có thể dùng những phép tính kinh tế đơn giản để thảo luận, với giả định rõ.

### 16.1. Ví dụ hoàn vốn từ năng lực được giải phóng

Giả sử một tự động hóa đối soát có:

- Chi phí triển khai ban đầu: **80 triệu đồng**.
- Khả năng giải phóng: **160 giờ/tháng**.
- Chi phí phân bổ giả định: **200.000 đồng/giờ**.
- Chi phí duy trì bổ sung và thay đổi quy trình: **chưa đưa vào** phép tính.

~~~text
Giá trị năng lực giả định mỗi tháng =
  160 giờ × 200.000 đồng = 32.000.000 đồng

Thời gian hoàn vốn lý thuyết nếu toàn bộ giá trị quy đổi được =
  80.000.000 / 32.000.000 = 2,5 tháng
~~~

**Không nên báo “đã tiết kiệm 32 triệu tiền mặt mỗi tháng”** trừ khi có bằng chứng tài chính phù hợp. Nếu việc tự động hóa chỉ chuyển con người sang nhiệm vụ khác, lợi ích có thể là năng lực, tốc độ hoặc chất lượng, không phải chi phí thực giảm. Còn cần tính bảo trì, công cụ, độ ổn định và các khoản cơ hội.

### 16.2. Giá trị kỳ vọng chỉ tốt bằng các xác suất giả định

Một mô hình có thể ước lượng **expected value** của nhiều hướng đầu tư bằng xác suất và mức giá trị khả dĩ. Tuy nhiên, với sản phẩm mới ít dữ liệu, việc ghi “xác suất thành công 73,4%” thường không có cơ sở.

Hãy:

1. Nêu rõ các **kịch bản** tốt, cơ sở và xấu.
2. Dùng phạm vi ước lượng thay vì một điểm số chắc chắn khi dữ liệu yếu.
3. Chỉ dùng xác suất nếu có cơ sở hoặc nhận định chuyên gia được gắn mức tin cậy.
4. Cập nhật giả định khi xuất hiện bằng chứng mới.
5. Không che nghĩa vụ bắt buộc trong giá trị trung bình kỳ vọng.

### 16.3. Chi phí cơ hội: mỗi quyết định “có” cũng là một quyết định “không”

Khi một đội ổn định dành ba Sprint xây báo cáo nâng cao chưa được kiểm chứng, họ không còn cùng năng lực đó để sửa lỗi mất tiến độ hoặc cải thiện trải nghiệm đăng ký. **Opportunity cost** là giá trị của phương án tốt nhất bị bỏ qua trong phạm vi nguồn lực hạn chế.

Đánh giá đầu tư cần hỏi **“Nếu không làm việc này, chúng ta có thể làm gì có giá trị/rủi ro quan trọng hơn?”**, không chỉ “việc này có vẻ hữu ích không?”.

## 17. Real options: giữ quyền chọn khi thông tin còn thiếu

Một cách tư duy gần với tài trợ tăng dần là **real options**: trong điều kiện bất định, việc giữ khả năng **trì hoãn một cam kết khó đảo ngược** có thể có giá trị, miễn không bỏ lỡ cơ hội hoặc nghĩa vụ quan trọng.

Ví dụ:

- Chưa mua hợp đồng hạ tầng dài hạn nếu số người dùng thí điểm còn quá nhỏ.
- Chưa chuyển toàn bộ cơ sở dữ liệu sang kiến trúc mới nếu chưa kiểm tra được nút thắt.
- Chưa xây mười tính năng khi mới có bằng chứng một hành vi cốt lõi.
- Đầu tư vào kiến trúc tương thích giúp mở rộng dần sau khi outcome đạt.

### 17.1. Một khoản tiền nhỏ có thể mua quyền quyết định tốt hơn

Giả sử tổ chức có thể:

1. **Cam kết 500 triệu đồng ngay** để xây bộ giải pháp lớn với nhiều giả định chưa được kiểm chứng.
2. **Chi 40 triệu đồng trước** cho nghiên cứu và nguyên mẫu, rồi quyết định có tiếp tục khoản lớn hay không.

Phương án thứ hai có thể tốt nếu thử nghiệm thực sự giúp **phân biệt các lựa chọn đầu tư**. Nếu kết quả nghiên cứu không đủ tin hoặc khoản chờ thêm gây mất cơ hội đáng kể, nó có thể không đáng giá.

**Không nên xem “luôn trì hoãn quyết định lớn” là chân lý.** Một cơ hội có tính mùa vụ hoặc một yêu cầu bảo mật bắt buộc có thể yêu cầu hành động đúng hạn dù một số bất định còn tồn tại.

### 17.2. Các quyết định khó đảo ngược cần bằng chứng mạnh hơn

| Loại quyết định | Mức đảo ngược tương đối | Hàm ý ngân sách |
|---|---|---|
| Đổi thứ tự hai PBI chưa bắt đầu | Dễ, trong phạm vi thẩm quyền. | Có thể thích ứng thường xuyên. |
| Thử nguyên mẫu trên dữ liệu giả | Thường dễ nếu kiểm soát phạm vi. | Dùng trần nhỏ để học. |
| Mở một lát tính năng qua feature flag | Có thể đảo về hành vi trước, nhưng phải xét dữ liệu. | Cần kiểm thử, quan sát và tiêu chí tắt. |
| Ký hợp đồng dài hạn không thể hủy | Khó, phụ thuộc điều khoản. | Cần đánh giá nghĩa vụ và tính linh hoạt. |
| Migration dữ liệu làm mất khả năng tương thích | Có thể rất khó đảo ngược. | Cần chứng cứ kỹ thuật, sao lưu và kế hoạch phục hồi. |
| Mở dịch vụ ở phạm vi lớn có dữ liệu nhạy cảm | Có thể gây hậu quả khó khắc phục. | Cần kiểm soát bắt buộc trước khi mở rộng. |

**Đảo ngược một deploy không có nghĩa dữ liệu và tác động tới người dùng cũng tự đảo ngược.** Chi phí rủi ro cần tính cả các hậu quả khó thu hồi.

## 18. Rolling-wave planning: dự báo nhiều kỳ nhưng chỉ chi tiết phần gần

**Rolling-wave planning** là cách lập kế hoạch theo nhiều tầng thời gian: phần sắp làm được mô tả chi tiết hơn, phần xa giữ ở mức giả thuyết và dự báo có thể thay đổi.

Một mô hình:

| Tầm nhìn | Nội dung nên rõ | Mức linh hoạt |
|---|---|---|
| **12 tháng** | Mục tiêu chiến lược, trần ngân sách, năng lực và nghĩa vụ bắt buộc. | Điều chỉnh theo thay đổi bối cảnh trong quy trình duyệt. |
| **Quý tới** | Kết quả mong muốn, rủi ro lớn, các quyết định đầu tư và phạm vi nguồn lực. | Sắp lại ưu tiên khi có bằng chứng. |
| **Vài Sprint/tuần tới** | PBI đủ hiểu để bắt đầu, kiểm chứng cần thiết, phụ thuộc và mốc học hỏi. | Điều chỉnh nội dung và cách thực hiện theo phản hồi. |
| **Hàng ngày/qua flow** | Công việc đang làm, blocker, kiểm thử, tình trạng chất lượng. | Developers/đội tự quản trong mục tiêu và thẩm quyền. |

Không nên biến roadmap 12 tháng thành một lời hứa rằng **từng story và ngày hoàn thành sẽ không đổi**. Ngược lại, “Agile nên không dự báo gì” cũng không giúp tổ chức quản lý nguồn lực, hợp đồng hay nghĩa vụ.

### 18.1. Dự báo theo khoảng khi độ bất định lớn

Giả sử cần làm một lát tích hợp mới mà chưa hiểu hết đối tác:

> Dự báo sơ bộ 6–10 tuần và 140–220 triệu đồng, tùy mức tương thích API và kiểm thử dữ liệu; sau một spike có giới hạn, nhóm sẽ cập nhật khoảng này.

Cách nói này minh bạch hơn so với một con số **8 tuần, 180 triệu đồng chắc chắn**, nếu thông tin hiện chưa đủ để bảo đảm.

### 18.2. Điều chỉnh forecast không đồng nghĩa thay budget tự ý

Khi phát hiện forecast tăng vượt ngưỡng, team nên:

1. Nêu **nguyên nhân mới được biết** và bằng chứng.
2. Cho thấy **ảnh hưởng tới chi phí, thời gian, phạm vi và chất lượng**.
3. Đề xuất các lựa chọn: giảm phạm vi, đổi phương án, đầu tư thêm hoặc dừng.
4. Trình người có thẩm quyền nếu vượt trần/điều kiện đã duyệt.
5. Cập nhật baseline dự báo với lịch sử thay đổi minh bạch; không sửa âm thầm dự báo cũ để xóa dấu vết.

## 19. Năng lực đội ổn định và chi phí vòng đời

Một sản phẩm được duy trì qua nhiều Sprint cần chi phí cho **khám phá, phát triển, kiểm thử, vận hành, hỗ trợ, bảo mật và cải tiến**, chứ không chỉ chi phí làm tính năng đầu tiên.

### 19.1. Xem tổng chi phí vòng đời

| Nhóm chi phí | Ví dụ | Rủi ro khi bị bỏ qua |
|---|---|---|
| **Discovery** | Nghiên cứu người dùng, thử nguyên mẫu, phân tích hiện trạng. | Xây sai giải pháp. |
| **Delivery** | Phát triển, thiết kế, tích hợp, test. | Dự báo thiếu năng lực thực. |
| **Quality/security** | Kiểm thử phân quyền, accessibility, hiệu năng, bảo vệ dữ liệu. | Rủi ro cho người dùng và nghĩa vụ. |
| **Operations** | Hạ tầng, telemetry, lưu trữ, backup, trực sự cố, hỗ trợ. | Chi phí sử dụng thực tăng ngoài dự báo. |
| **Maintenance** | Refactoring, cập nhật phụ thuộc, giảm nợ kỹ thuật. | Khả năng thay đổi suy giảm. |
| **Migration/decommission** | Chuyển dữ liệu, hỗ trợ phiên bản cũ, ngừng dịch vụ cũ. | Bị khóa vào chi phí duy trì nhiều hệ thống. |
| **Governance/procurement** | Thẩm định, quyền, kiểm toán, hợp đồng, báo cáo. | Thiếu dự toán thời gian và nghĩa vụ. |

Nếu một thí điểm có chi phí triển khai thấp nhưng mỗi tháng tiêu tốn hạ tầng và công hỗ trợ lớn, kết luận kinh tế cần được cập nhật **trước khi mở rộng**.

### 19.2. Không coi story points là đơn vị tiền

Một đội ước lượng story points để hỗ trợ dự báo tương đối. Tuy nhiên:

- Point không có giá trị tiền cố định.
- Các đội có cách ước lượng và chia PBI khác nhau.
- Tăng velocity không chứng minh ROI tăng.
- Không thể kết luận “một point có giá 2 triệu đồng” như một tỷ giá đáng tin giữa các team.

Có thể dự báo năng lực qua **throughput, cycle time, quy mô hạng mục và lịch sử của chính đội**; kết hợp chi phí năng lực theo kỳ để tạo forecast, kèm giới hạn. Nhưng **không biến ước lượng cục bộ thành thước đo giá trị kinh doanh**.

### 19.3. Bảo vệ năng lực xử lý việc không nằm trong roadmap

Một đội vận hành dịch vụ thật luôn có:

- Lỗi cần khắc phục.
- Yêu cầu bảo mật hoặc tuân thủ phát sinh.
- Sự cố production và phục hồi.
- Hỗ trợ người dùng.
- Nâng cấp thành phần để duy trì khả năng thay đổi.

Nếu toàn bộ ngân sách và lịch chỉ dành cho tính năng, những việc trên trở thành “ngoại lệ” bị che giấu. Khi lập kế hoạch, cần **dự trù năng lực cho công việc bất định** và có chính sách ưu tiên, không nhất thiết một tỷ lệ chung cho mọi sản phẩm.

## 20. Scrum: kết nối Product Goal, Increment và quyết định đầu tư

Scrum là một framework cho phát triển thích ứng dựa trên **empiricism và lean thinking**, chứ không phải quy trình lập ngân sách tài chính. Có thể dùng các artifact và sự kiện Scrum để tạo bằng chứng cho quản trị đầu tư.

| Thành phần Scrum | Tín hiệu liên quan đầu tư | Cảnh giác |
|---|---|---|
| **Product Goal** | Kết quả dài hơn mà sản phẩm hướng tới. | Đừng thay bằng danh sách tính năng đã cấp tiền. |
| **Product Backlog** | Những thay đổi cần làm để cải thiện sản phẩm, được sắp thứ tự theo giá trị/rủi ro. | Không khóa mọi mục từ đầu năm khi bằng chứng thay đổi. |
| **Sprint Goal** | Mục tiêu có giá trị cho Sprint. | Không nhất thiết phải mô tả kết quả thương mại ngay trong 1 Sprint. |
| **Increment và DoD** | Phần sản phẩm tích hợp, dùng được theo tiêu chuẩn chất lượng. | “Done” không đồng nghĩa đã release hoặc outcome đã xảy ra. |
| **Sprint Review** | Bằng chứng từ Increment, người dùng và bối cảnh mới để thích ứng. | Không biến thành lễ nghiệm thu tài chính cho mọi ticket. |
| **Sprint Retrospective** | Cải tiến hệ thống làm việc, chất lượng và năng lực tạo giá trị. | Đừng chỉ đếm số action mà không đo hiệu quả. |

### 20.1. Trách nhiệm vẫn rõ

- **Product Owner:** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog.
- **Developers:** chịu trách nhiệm tạo Increment dùng được, lập kế hoạch thực hiện và đáp ứng Definition of Done.
- **Scrum Master:** hỗ trợ hiệu quả Scrum Team và cách vận dụng Scrum.
- **Người có thẩm quyền tài chính:** phê duyệt/điều chỉnh vốn theo chính sách của tổ chức.

Việc tài trợ theo outcome **không thay đổi tự động** những accountability của Scrum hoặc cơ cấu pháp lý của tổ chức.

### 20.2. Sprint Review có thể hỗ trợ investment review

Ví dụ, tại Sprint Review team cho thấy:

- Một Increment “Tiếp tục học” dùng được theo DoD.
- Người dùng thử tìm lại bài nhanh hơn trong phạm vi quan sát.
- Chưa đủ bảy ngày để đo kết quả quay lại của toàn cohort.
- Còn lỗi hiển thị trên một loại thiết bị cần khắc phục.

Người quyết định đầu tư có thể tham gia thảo luận và **chưa giải phóng khoản mở rộng** cho tới khi bằng chứng đủ, đồng thời cho phép các công việc cần thiết để hoàn tất chất lượng. **Sprint Review không bị biến thành một hợp đồng yêu cầu phải đạt ROI mỗi Sprint.**

## 21. Kanban: làm rõ flow, nút thắt và khả năng dự báo chi phí

Kanban giúp đội thấy số hạng mục đang dở, thời gian hoàn thành và điểm công việc bị chặn. Những tín hiệu đó có thể hỗ trợ dự báo **khả năng sử dụng năng lực đã được tài trợ**.

### 21.1. Những phép đo hữu ích

| Tín hiệu | Câu hỏi cho quản trị năng lực |
|---|---|
| **WIP** | Đội có mở quá nhiều việc so với khả năng hoàn thành không? |
| **Cycle time** | Từ lúc bắt đầu tới Done mất bao lâu, phân phối có ổn định không? |
| **Throughput** | Có bao nhiêu hạng mục hoàn thành trong khoảng đo? |
| **Work item age** | Việc đang dở nào đã chờ quá lâu và cần gỡ? |
| **Blocked time** | Năng lực bị giữ ở phụ thuộc hoặc quyết định nào? |
| **Flow efficiency (khi đo được)** | Thời gian chủ động và chờ được phân loại ra sao? |
| **SLE** | Có thể dự báo khoảng thời gian hoàn thành theo lịch sử/loại việc không? |

Nếu cycle time tăng do chờ kiểm duyệt quyền truy cập, **thêm nhà phát triển** có thể không giải quyết được nút thắt. Quản trị ngân sách cần dựa trên **hệ thống dòng công việc** thay vì giả định số người tăng tuyến tính với số tính năng giao.

### 21.2. Dùng phân phối, không chỉ trung bình

Giả sử nhóm đã hoàn thành 30 PBI loại tương đương trong 12 tuần; trung vị cycle time là 8 ngày làm việc nhưng một số mất 25 ngày. Một forecast chỉ dựa trên trung vị **có thể che phần đuôi phân phối**.

Nhóm có thể dùng dữ liệu lịch sử và mô phỏng phù hợp để đưa ra **khoảng dự báo**, nhưng cần xem độ đồng nhất của loại việc, WIP, tình trạng phụ thuộc, ngày nghỉ và rủi ro. Dữ liệu mẫu nhỏ không đủ để tạo cảm giác xác suất chính xác quá mức.

### 21.3. Chia nhỏ lát giá trị giúp điều chỉnh ngân sách

Khi PBI nhỏ, tích hợp và dùng được sớm, nhóm có thể thu phản hồi trước khi tiêu phần lớn trần. Tuy nhiên, **chia nhỏ về mặt ticket** mà không tạo Increment dùng được hoặc không học thêm điều gì chỉ làm throughput đẹp giả.

## 22. XP và DevOps: đầu tư vào năng lực thay đổi an toàn

Những thực hành kỹ thuật của XP và DevOps thường tạo **giá trị gián tiếp**: giảm lỗi, giảm thời gian phản hồi, giúp thay đổi trong tương lai ít rủi ro hơn.

### 22.1. Khi nào nên cấp kinh phí cho cải tiến kỹ thuật?

Ví dụ, pipeline tích hợp mất nhiều giờ và thường thất bại ngẫu nhiên. Developers mất thời gian chờ, việc tích hợp dồn cuối Sprint và release mang rủi ro lớn.

Một khoản đầu tư cải tiến CI có thể được đề xuất với:

- **Hiện trạng:** thời gian chờ CI, tỷ lệ flaky tests, thời gian nhánh chung đỏ.
- **Hành động:** thử tối ưu bước chậm nhất và sửa test không đáng tin.
- **Output:** pipeline mới chạy ổn, có kết quả kiểm chứng.
- **Process outcome:** thời gian chờ và lỗi tích hợp muộn giảm.
- **Product guardrail:** không bỏ kiểm tra bảo mật, dữ liệu hoặc chất lượng bắt buộc.
- **Giá trị xa hơn:** đội có thể giao phần giá trị nhỏ và sửa lỗi nhanh hơn.

### 22.2. Đừng lấy số lượng bài test làm ROI

Một bộ 500 test mới nhưng không kiểm tra lỗi trọng yếu có thể tạo gánh nặng lớn mà không giảm rủi ro. **Chọn phép đo liên quan mục tiêu**, như lỗi cùng loại được phát hiện trước release, thời gian chẩn đoán, khả năng phục hồi và độ tin cậy của pipeline.

### 22.3. DevOps không phải lý do bỏ dự toán vận hành

Việc triển khai thường xuyên có thể giúp học sớm hơn, nhưng production vẫn cần giám sát, hạ tầng, backup, hỗ trợ và ứng phó. Nếu ngân sách chỉ mua công xây tính năng, khả năng mở rộng dịch vụ có thể sớm bị giới hạn.

## 23. Ràng buộc pháp lý, hợp đồng và an toàn: phần nào không thể linh hoạt?

Agile tạo khả năng thích ứng **trong những giới hạn hợp lệ**. Không nên diễn giải “phản hồi trước thay đổi” thành quyền bỏ qua trách nhiệm pháp lý, an toàn, hợp đồng hay kiểm toán.

### 23.1. Phân biệt ràng buộc bắt buộc và lựa chọn quản trị

| Loại ràng buộc | Ví dụ | Cách kết hợp với Agile |
|---|---|---|
| **Pháp lý/quy định** | Bảo vệ dữ liệu, nghĩa vụ thông báo hoặc lưu giữ theo luật áp dụng. | Làm rõ từ sớm với chuyên gia, thiết kế/kiểm chứng trong từng Increment. |
| **An toàn và bảo mật** | Phân quyền, bảo vệ secrets, quản lý lỗ hổng, khả năng phục hồi bắt buộc. | Đưa vào Definition of Done và gate rủi ro tương xứng; không “bù sau release” nếu không được phép. |
| **Hợp đồng** | Trần chi, phương thức nghiệm thu, điều kiện thay đổi phạm vi. | Cấu trúc bằng chứng và cơ chế change control rõ. |
| **Tài chính/kế toán** | Quyền duyệt chi, phân loại chi phí, kỳ báo cáo. | Dự báo cập nhật thường xuyên nhưng ghi nhận đúng chính sách. |
| **Mua sắm** | Quy trình lựa chọn nhà cung cấp, thời hạn hợp đồng, điều kiện hủy. | Xem lead time mua sắm như phụ thuộc trong kế hoạch. |
| **Kiểm toán/truy vết** | Phải có bằng chứng quyết định và kiểm soát. | Lưu artifact, log quyết định, kiểm thử và phê duyệt ở nơi chuẩn. |
| **Chính sách nội bộ có thể thay đổi** | Tầng phê duyệt nhỏ, biểu mẫu, cuộc họp thường lệ. | Cải tiến nếu gây chậm và có quyền điều chỉnh. |

### 23.2. Thay đổi được quy định không có nghĩa tất cả scope phải cố định

Một dự án phải đáp ứng một tiêu chuẩn bảo mật có thể giữ nguyên **kết quả tuân thủ bắt buộc**, nhưng vẫn thử nhiều cách kỹ thuật khác nhau để đạt kết quả đó. Nhóm có thể chia công việc thành các lát được kiểm chứng và cập nhật forecast dựa trên phát hiện.

Không có “miễn trừ Agile” đối với nghĩa vụ bắt buộc. Khi thực tế phát sinh xung đột, cần **đưa ra người có thẩm quyền và tham vấn chuyên môn**, không tự chọn bỏ qua điều kiện khó.

### 23.3. Kiểm toán không nhất thiết cần báo cáo dày

Một chuỗi evidence có thể gồm:

- Product Goal và lý do chọn ưu tiên.
- PBI/acceptance criteria và Definition of Done.
- Các quyết định ngân sách và quyền phê duyệt.
- Kết quả CI/test và bằng chứng chất lượng.
- Mốc release, cấu hình và quan sát sản phẩm.
- Kết quả checkpoint, biến động chi phí và quyết định tiếp theo.

Khi quản lý nhất quán, những artifact đó có thể giảm việc phải **viết lại báo cáo từ đầu** để chứng minh điều đã làm. Tuy nhiên, yêu cầu hồ sơ cụ thể phải được kiểm tra theo chế độ thực tế.

## 24. Hợp đồng cố định và nhà cung cấp: linh hoạt phần được phép

Không phải mọi tổ chức trực tiếp sở hữu đội phát triển. Nhiều sản phẩm dùng đối tác theo hợp đồng có giá, thời hạn và phạm vi ràng buộc.

### 24.1. Ba lựa chọn cấu trúc hợp đồng thường gặp

| Cách cấu trúc | Ưu điểm có thể có | Rủi ro/điều kiện cần quản trị |
|---|---|---|
| **Fixed scope, fixed price** | Dễ xác định đầu ra và giá trong phạm vi ổn định. | Khó thay đổi giả thuyết; cần cơ chế change request và nghiệm thu đúng. |
| **Time & materials với trần/điểm kiểm tra** | Có thể điều chỉnh backlog và khám phá theo năng lực. | Cần minh bạch giờ/chi phí, tiêu chuẩn chất lượng và quyết định giá trị. |
| **Outcome/milestone-based trong phạm vi phù hợp** | Gắn thanh toán với kết quả có thể xác minh. | Phải chọn outcome trong mức kiểm soát hợp lý của các bên, tránh incentive sai. |

Không có hình thức nào tự động “Agile hơn” trong mọi hoàn cảnh. Quyền thay đổi backlog, sở hữu IP, dữ liệu, nghiệm thu, nghĩa vụ an toàn và cách xử lý tranh chấp phụ thuộc văn bản hợp đồng cụ thể.

### 24.2. Không ép nhà cung cấp chịu trách nhiệm cho tác động ngoài quyền kiểm soát

Ví dụ, một nhà cung cấp giao phần mềm có thể chịu trách nhiệm **chất lượng API, độ sẵn sàng theo hợp đồng hoặc tiêu chí nghiệm thu đã thống nhất**, nhưng tỷ lệ hoàn thành khóa học có thể chịu ảnh hưởng bởi nội dung, chiến dịch marketing và chính sách giáo dục mà họ không kiểm soát.

Nếu thưởng/phạt chỉ dựa trên outcome rộng, nhà cung cấp có thể tìm cách thao túng dữ liệu hoặc tránh nhóm người dùng khó. Nên thỏa thuận **phạm vi kiểm soát, cách đo, guardrails và cơ chế cộng tác**, có tư vấn pháp lý/tài chính khi áp dụng thật.

### 24.3. Hợp đồng cố định vẫn có thể có phản hồi sớm

Trong phạm vi quyền được phép, có thể:

- Chia nghiệm thu thành Increment tích hợp có giá trị.
- Tổ chức phản hồi sớm về ví dụ hành vi và dữ liệu thử.
- Làm rõ tiêu chí chất lượng từ đầu.
- Có cơ chế thay đổi hợp đồng khi giả thuyết sai hoặc yêu cầu mới xuất hiện.
- Tách phần tùy chọn khỏi phần bắt buộc khi thiết kế scope.

**Điều chỉnh cách làm bên trong phạm vi được duyệt** khác với tự ý thay đổi nghĩa vụ hợp đồng.

## 25. Portfolio governance: phân bổ vốn giữa nhiều cơ hội có mức bằng chứng khác nhau

Khi tổ chức có nhiều sản phẩm hoặc sáng kiến, câu hỏi không chỉ là “sáng kiến này có nên tiếp tục?” mà còn là **“nên dành nguồn lực giới hạn cho cơ hội nào trong danh mục?”**

Một danh mục có thể cần cân bằng:

- **Duy trì:** vận hành dịch vụ hiện tại và xử lý nghĩa vụ bắt buộc.
- **Cải thiện:** tăng giá trị hoặc độ tin cậy của sản phẩm đang có.
- **Khám phá:** giảm bất định cho cơ hội mới.
- **Chuyển đổi:** đầu tư hạ tầng/nền tảng dài hạn để mở khả năng tương lai.

### 25.1. Minh họa các quyết định khác nhau

| Sáng kiến | Trạng thái bằng chứng | Quyết định phù hợp có thể có |
|---|---|---|
| Sửa lỗi học viên truy cập sai tiến độ người khác | Rủi ro bảo mật đã xác nhận. | Ưu tiên kiểm soát/khắc phục theo nghĩa vụ, không chờ ROI thí điểm. |
| Nút “Tiếp tục học” | Đã có tín hiệu ma sát, chưa chứng minh outcome. | Cấp thử nhỏ và đo có kiểm soát. |
| Hệ thống gợi ý bài học phức tạp | Giả thuyết giá trị và khả thi còn yếu. | Thu bằng chứng, spike hoặc trì hoãn cam kết lớn. |
| Cải thiện pipeline CI nhiều nhóm dùng | Có blocked time và lỗi tích hợp đo được. | Thử cải tiến nền tảng, theo dõi adoption và flow của đội tiêu thụ. |
| Báo cáo nâng cao ít người sử dụng | Đã release nhưng adoption/outcome thấp. | Nghiên cứu nguyên nhân, thay đổi/dừng đầu tư. |

### 25.2. Không dùng một bảng điểm ROI duy nhất cho mọi loại việc

Một khoản sửa lỗ hổng nghiêm trọng, một thử nghiệm thị trường và một cải tiến accessibility **có giá trị và nghĩa vụ khác nhau**. Nếu buộc mọi thứ quy ra doanh thu quý tới, tổ chức có thể đầu tư thiếu vào rủi ro dài hạn và công bằng tiếp cận.

Các nhóm đầu tư có thể cần **cửa quyết định và mức bằng chứng khác nhau**, nhưng phải được giải thích rõ ràng và có trách nhiệm giải trình.

### 25.3. Giữ chi phí cơ hội nhìn thấy

Nếu một đội không thể thực hiện đồng thời ba sáng kiến, việc duy trì cả ba ở trạng thái WIP kéo dài sẽ làm chậm học hỏi. Portfolio cần cân nhắc **dừng hoặc tạm hoãn** cơ hội có bằng chứng yếu để giải phóng năng lực, thay vì chỉ mở thêm dự án và “để tất cả cùng tiến”.

## 26. Case study: lập ngân sách cho giải pháp giúp học viên quay lại học

**Toàn bộ tổ chức, số liệu, khoản tiền và kết quả trong case study dưới đây đều là giả định phục vụ học tập.** Đây không phải tư vấn tài chính, kế hoạch cho dự án thật hay bằng chứng khoa học về hiệu quả sản phẩm.

### 26.1. Đặt vấn đề trước đề xuất giải pháp

Một nền tảng có tỷ lệ học viên quay lại hoạt động học có ý nghĩa trong bảy ngày là **24%** theo định nghĩa đang sử dụng. Ban lãnh đạo muốn cải thiện vì số người bỏ dở lộ trình cao.

Đội sản phẩm đề xuất một gói chức năng:

1. Nút “Tiếp tục học”.
2. Đồng bộ tiến độ giữa thiết bị.
3. Email nhắc học.
4. Gợi ý bài tiếp theo.
5. Báo cáo hành trình cá nhân.

Nhưng dữ liệu chưa cho thấy mỗi tính năng sẽ đóng góp bao nhiêu. Nếu lập ngân sách ngay cho toàn bộ, tổ chức khó thay đổi đường đi khi học được rằng vấn đề chính là lỗi lưu tiến độ.

### 26.2. Đề xuất đầu tư ban đầu

Đội trình **trần tổng 1,2 tỷ đồng**, chia theo phạm vi quản trị ở mục 9. Quyết định trước mắt chỉ là **cho phép bắt đầu giai đoạn khám phá tối đa 120 triệu đồng**, không phải giải ngân toàn bộ 1,2 tỷ.

| Điều kiện khám phá | Cách xác minh |
|---|---|
| Có hiểu biết đáng tin về những điểm làm học viên không quay lại. | Quan sát hành trình và nghiên cứu người dùng có phân khúc phù hợp. |
| Có baseline outcome nhất quán. | Kiểm tra định nghĩa người đủ điều kiện, sự kiện học có ý nghĩa và cửa sổ bảy ngày. |
| Biết các rủi ro dữ liệu/tiếp cận và hệ thống cần giải quyết. | Kiểm chứng tiến độ lưu/khôi phục, quyền truy cập và hành vi trên thiết bị mục tiêu. |
| Có các lựa chọn thử kế tiếp và chi phí dự báo. | So sánh lát giá trị và giả định còn thiếu. |
| Có bằng chứng để quyết định. | Hội đồng/owner có thẩm quyền nhận báo cáo **tiếp tục, sửa hướng hoặc dừng**. |

### 26.3. Kết quả khám phá giả định

Sau một giai đoạn nghiên cứu có kiểm soát:

- Nhiều học viên muốn tiếp tục bài gần nhất nhưng mất thời gian tìm lại.
- Một nhóm gặp lỗi lưu tiến độ ở thiết bị khác.
- Email nhắc học không phải mong muốn của một số phân khúc và có rủi ro làm phiền.
- Nhu cầu về gợi ý bài học nâng cao chưa được chứng minh.

**Quyết định:** không xây toàn bộ năm chức năng ngay. Ưu tiên lát **khôi phục đúng tiến độ + nút tiếp tục** với kiểm chứng đa thiết bị và accessibility; giữ email và gợi ý trong Product Backlog để xem lại sau.

Đây là lợi ích tài chính của **quyền đổi hướng trước khi tiền được cam kết**.

### 26.4. Kế hoạch thí điểm có điều kiện

Trong trần dự kiến **240 triệu đồng** cho thí điểm, nhóm muốn kiểm chứng:

- Học viên đủ điều kiện có tìm lại bài nhanh hơn không?
- Tỷ lệ quay lại hoạt động học có ý nghĩa sau bảy ngày thay đổi thế nào?
- Tiến độ có được khôi phục **đúng, nhất quán và có quyền truy cập phù hợp** không?
- Người dùng bàn phím hoặc công nghệ hỗ trợ có hoàn tất luồng không?
- Độ trễ và lỗi sau triển khai có nằm trong mục tiêu vận hành không?
- Chi phí duy trì mỗi người dùng hoạt động có tăng ngoài dự báo không?

Thí điểm phải đạt Definition of Done và các tiêu chuẩn bắt buộc **trước khi mở phạm vi được phép**. Nếu hạng mục chưa đủ an toàn hoặc chưa có dữ liệu đo tin cậy, nhóm không nên đánh dấu “thí điểm thành công” chỉ vì tiến độ kỹ thuật đúng lịch.

### 26.5. Dữ liệu giả định sau thí điểm

Giả sử hai cohort đều có **1.000 học viên đủ điều kiện đã trưởng thành đủ bảy ngày**:

| Chỉ số | Cohort baseline | Cohort thí điểm |
|---|---:|---:|
| Người đủ điều kiện | 1.000 | 1.000 |
| Hoàn thành ít nhất một hoạt động học có ý nghĩa trong bảy ngày | 240 | 320 |
| Tỷ lệ outcome | 24% | 32% |
| Lỗi mở sai tiến độ được ghi nhận theo cơ chế kiểm tra | Có trường hợp được phát hiện | Giảm trong phạm vi quan sát |
| Rào cản truy cập trong hành trình mục tiêu | Một số vấn đề đã xác nhận | Các vấn đề cản trở đã biết được sửa và kiểm tra lại |

Từ 24% lên 32% là **8 điểm phần trăm**. Dù vậy, báo cáo phải cho biết các cohort khác nhau ở đâu, có thay đổi mùa vụ hoặc truyền thông không, nguồn dữ liệu và giới hạn của phép so sánh.

Đội có thể xem kết quả là **tín hiệu đáng đầu tư thẩm định tiếp**, không vội gắn toàn bộ chênh lệch cho một nút giao diện.

### 26.6. Một báo cáo tài chính tại checkpoint giả định

Sau một số phần việc đã được duyệt, kế toán và quản trị xác nhận:

| Hạng mục theo dõi | Triệu đồng |
|---|---:|
| Trần đầu tư toàn kỳ | 1.200 |
| Actual đã phát sinh | 410 |
| Commitment chưa nằm trong actual | 65 |
| Phần còn lại theo trần sau hai khoản | 725 |
| Trần riêng của giai đoạn mở rộng dự kiến | 420 |
| Dự phòng trong envelope ban đầu | 180 |

**Không được cộng khoản 420 và 180 vào 725 như tiền mới:** các khoản là **phân bổ nằm bên trong trần 1.200 triệu**, không phải các nguồn ngân sách bổ sung. Trước khi cấp giai đoạn mới cần kiểm tra trần, mức đã giải phóng, chi phí đã cam kết, forecast và quyền phê duyệt.

### 26.7. Ba phương án quyết định tiếp theo

**Phương án A — Mở rộng có kiểm soát:** nếu kết quả tương đối đáng tin, guardrails ổn và chi phí biên chấp nhận được, giải phóng thêm một phần trần mở rộng để kiểm tra quy mô lớn hơn.

**Phương án B — Điều chỉnh và đo tiếp:** nếu outcome có tín hiệu nhưng đo lường yếu hoặc nhóm thiết bị cũ còn lỗi, ưu tiên sửa chất lượng, đo lại cohort hoặc đổi giải pháp trước khi chi lớn.

**Phương án C — Dừng/tái phân bổ:** nếu người dùng không có lợi ích đủ ý nghĩa hoặc chi phí/thiệt hại vượt mức chấp nhận, dừng hướng này, ghi bài học và xem phương án khác phục vụ Product Goal.

**Không có nghĩa nhóm bắt buộc chọn A vì đã tiêu một khoản lớn.** Tiền đã chi là dữ kiện để giải trình, không phải lý do kinh tế hợp lệ để tiếp tục đổ tiền vào giả thuyết yếu.

### 26.8. Hậu kiểm khoản đầu tư phải xem cả những gì đã không xây

Giá trị của giai đoạn khám phá có thể là tránh làm email nhắc học gây phiền hoặc một hệ thống gợi ý chưa có nhu cầu, đồng thời nhận ra vấn đề khôi phục tiến độ cần sửa trước.

Tuy nhiên, **không được ghi tùy tiện toàn bộ chi phí các tính năng chưa xây thành “tiền đã tiết kiệm”** nếu chưa có kế hoạch cam kết, giá dự toán đáng tin và phương án thay thế. Có thể báo cáo **nguồn lực chưa cam kết được giữ lại để tái quyết định**, chính xác hơn một tuyên bố lợi nhuận đã hiện thực hóa.

## 27. Khi giả thuyết không đúng: dừng, pivot hay tiếp tục nghiên cứu?

Một trong những quyết định khó nhất là **không tiếp tục**. Tổ chức thường cảm thấy dừng đồng nghĩa thừa nhận sai lầm vì đã dùng nhiều thời gian và ngân sách. Đây là rủi ro **sunk cost fallacy — ngụy biện chi phí chìm**.

### 27.1. Nhìn về quyết định tương lai

Hãy hỏi:

- **Từ hôm nay**, chi thêm bao nhiêu để đạt outcome có khả năng xảy ra?
- Có phương án thay thế nào dùng nguồn lực tốt hơn?
- Rủi ro chưa giải quyết nào sẽ tăng nếu tiếp tục?
- Có bằng chứng nào mới có thể đổi quyết định?
- Nếu dừng, chi phí đóng dự án, vận hành và nghĩa vụ hợp đồng còn lại là gì?

**Chi phí đã phát sinh không thể lấy lại** vẫn cần ghi nhận và giải trình, nhưng lựa chọn tiếp tục nên dựa trên lợi ích, rủi ro và chi phí **từ thời điểm quyết định trở đi**.

### 27.2. Phân biệt các lựa chọn

| Lựa chọn | Khi nào cân nhắc? | Bước cần thực hiện |
|---|---|---|
| **Persevere — Tiếp tục** | Bằng chứng giá trị đủ mạnh, chi phí/rủi ro chấp nhận và còn cơ hội cải thiện. | Cấp phần vốn thích hợp, đặt milestone và guardrails tiếp theo. |
| **Pivot — Đổi giả thuyết/cách tiếp cận** | Vấn đề người dùng còn quan trọng nhưng giải pháp ban đầu không hiệu quả. | Cập nhật Product Goal/backlog nếu cần theo thẩm quyền, định nghĩa thử nghiệm mới. |
| **Pause — Tạm dừng** | Thiếu dữ liệu hoặc phải đợi một điều kiện ngoài; thời gian chờ hợp lý. | Ghi điều kiện mở lại, người phụ trách và chi phí giữ trạng thái. |
| **Stop — Dừng** | Giá trị yếu, rủi ro cao, chi phí vượt lợi ích hoặc cơ hội khác tốt hơn. | Thu hồi nguồn lực, xử lý cam kết/hạ tầng/dữ liệu và lưu bài học. |
| **Mandatory remediation — Khắc phục bắt buộc** | Nghĩa vụ an toàn/tuân thủ cần được xử lý. | Thực hiện theo thẩm quyền và mức rủi ro, không trì hoãn vì ROI ngắn hạn. |

### 27.3. Dừng cũng tốn chi phí và cần quản trị

Khi dừng một thí điểm đã dùng dữ liệu thật, cần có kế hoạch **xóa/giữ dữ liệu đúng quy định, xử lý người dùng đã tham gia, kết thúc hợp đồng, hoàn nguyên quyền và giám sát những ảnh hưởng còn lại**. Không nên nghĩ “không viết mã nữa” đồng nghĩa không có chi phí thoát.

## 28. Báo cáo investment review gọn nhưng đủ quyết định

Một bản review đầu tư theo học hỏi nên trả lời **điều đã thử, điều đã học, chi phí còn lại, rủi ro và quyết định đề xuất**.

~~~text
INVESTMENT REVIEW — VÍ DỤ MINH HỌA

Product Goal:
  Giúp học viên quay lại học có ý nghĩa dễ dàng và đáng tin.

Giả thuyết:
  Khôi phục đúng bài gần nhất và giảm ma sát sẽ cải thiện
  hành vi quay lại trong vòng 7 ngày.

Funding:
  Tổng trần toàn kỳ: 1.200 triệu đồng.
  Actual: 410 triệu; committed chưa tính actual: 65 triệu.
  Không tự động được dùng phần trần chưa giải phóng.

Output:
  Increment Tiếp tục học đạt DoD trong phạm vi thí điểm.

Learning / outcome:
  Cohort giả định: 24% -> 32% học viên đủ điều kiện có
  hoạt động học có ý nghĩa trong 7 ngày.
  Đã sửa những lỗi truy cập và khôi phục tiến độ được biết.

Giới hạn bằng chứng:
  Cohort có thể khác về nội dung và mùa vụ.
  Chưa đủ dữ liệu impact dài hạn và mức tải khi mở rộng.

Guardrails:
  Không được lộ dữ liệu; không bỏ qua tiêu chuẩn
  accessibility, tính đúng tiến độ và khả năng vận hành.

Quyết định cần:
  Cho phép mở rộng nhỏ có kiểm soát, sửa lỗi trước khi tăng
  phạm vi, hoặc dừng/đổi hướng nếu bằng chứng không đủ.

Recommendation:
  Chỉ giải phóng khoản vốn kế tiếp khi có owner phê duyệt,
  forecast cập nhật, phạm vi và mốc kiểm chứng rõ.
~~~

### 28.1. Những thông tin nên có trong cuộc họp

1. **Điểm quyết định:** cần duyệt việc gì và theo thẩm quyền nào?
2. **Bằng chứng chính:** dữ liệu, người dùng, chất lượng, rủi ro, giới hạn.
3. **Tình trạng tài chính:** actual, committed, forecast, trần và dự phòng.
4. **Các lựa chọn:** tiếp tục, giảm scope, thử thêm, dừng, và hệ quả của mỗi lựa chọn.
5. **Quyết định và điều kiện:** người phê duyệt, giới hạn mới, milestone kế tiếp.

Không nên biến investment review thành yêu cầu đội “trình diễn thật nhiều màn hình đẹp”, vì nó làm lệch động lực khỏi câu hỏi **khoản chi tiếp theo có đáng thực hiện hay không**.

## 29. Các phản mẫu khi lập ngân sách Agile

| Phản mẫu | Tác hại | Cách thực hành tốt hơn |
|---|---|---|
| **Cấp hết tiền ngay khi giả thuyết còn yếu.** | Khóa nguồn lực vào giải pháp chưa biết giá trị. | Trần khám phá nhỏ, checkpoint theo bằng chứng. |
| **Yêu cầu khóa mọi user story trước khi phê duyệt mục tiêu.** | Khó thích ứng với phản hồi mới. | Khóa ràng buộc thiết yếu, giữ backlog giải pháp đủ linh hoạt. |
| **Không có trần ngân sách vì “Agile luôn thay đổi”.** | Mất kiểm soát và trách nhiệm tài chính. | Có trần, phạm vi ủy quyền, forecast cập nhật và escalation. |
| **Đồng nhất “đã release” với “đạt outcome”.** | Tiếp tục đầu tư dù người dùng không được lợi. | Đo adoption, hành vi và guardrails. |
| **Đếm số phỏng vấn là bằng chứng học hỏi.** | Tối ưu hoạt động thay vì giảm bất định. | Ghi giả thuyết, kết quả và quyết định được thay đổi. |
| **Chỉ cấp tiền cho kết luận tích cực.** | Khuyến khích giấu dữ liệu phản bác. | Đánh giá chất lượng thử nghiệm và quyền dừng đúng lúc. |
| **Chia ngân sách thành các cổng duyệt quá nhỏ.** | Tốn thời gian chờ hơn lợi ích kiểm soát. | Ủy quyền trong trần và rủi ro đã được phê duyệt. |
| **Cho rằng số tiền chưa chi là tiền tự do dùng.** | Vượt giới hạn hoặc dùng mất dự phòng. | Tách envelope, released, actual, commitment và restricted reserve. |
| **Lấy story points đổi trực tiếp ra đồng.** | Dùng thước đo tương đối như tỷ giá. | Dự báo qua năng lực, dữ liệu flow và chi phí thực. |
| **Hạ DoD để không vượt ngân sách.** | Gây rủi ro chất lượng, nợ kỹ thuật và thiệt hại. | Giảm phạm vi hoặc xin quyết định đầu tư lại. |
| **Bỏ chi phí vận hành sau launch.** | Thí điểm rẻ nhưng mở rộng không bền vững. | Tính tổng chi phí vòng đời và chi phí biên. |
| **Báo forecast như cam kết chắc chắn khi dữ liệu yếu.** | Tạo kỳ vọng sai, che bất định. | Dùng khoảng, giả định, mốc cập nhật và mức tin cậy. |
| **Báo “tiết kiệm tiền mặt” từ giờ làm được giải phóng.** | Phóng đại lợi ích tài chính. | Phân biệt năng lực tiết kiệm, chi phí thực giảm và outcome. |
| **Tiếp tục vì đã tiêu nhiều (sunk cost).** | Lãng phí thêm nguồn lực. | Đánh giá lợi ích/rủi ro tương lai, chi phí thoát và cơ hội khác. |
| **Dùng ROI quý tới cho mọi đầu tư an toàn.** | Thiếu đầu tư vào nghĩa vụ và độ tin cậy. | Phân loại công việc theo mục tiêu/ràng buộc phù hợp. |
| **Xem cost of delay như con số chính xác dù không có dữ liệu.** | Ưu tiên bằng độ chính xác giả. | Công khai giả định, kịch bản và mức tin cậy. |
| **Biến Sprint Review thành nơi phê duyệt từng task.** | Mất giá trị kiểm tra sản phẩm và phản hồi. | Dùng bằng chứng Scrum hỗ trợ investment governance, không thay thế framework. |
| **Thí nghiệm gây hại để chứng minh lợi ích.** | Vi phạm an toàn/quyền riêng tư. | Giữ guardrails và kiểm soát không thể đánh đổi. |
| **Tăng WIP vì nhiều dự án đã được duyệt.** | Mọi thứ chậm, chi phí chuyển ngữ cảnh tăng. | Cân đối năng lực, giới hạn WIP và sẵn sàng dừng/hoãn. |
| **Đổi target sau khi biết số để báo thành công.** | Bằng chứng bị chọn lọc. | Ghi tiêu chí trước, minh bạch khi phải điều chỉnh. |

## 30. Lộ trình áp dụng vào tổ chức

### Bước 1 — Làm rõ mục tiêu và giới hạn không thể đánh đổi

Xác định Product Goal hoặc mục tiêu danh mục, trần theo kỳ, những yêu cầu bắt buộc về dữ liệu, hợp đồng và an toàn. Không cần có toàn bộ user story, nhưng phải biết **mức vốn và quyền đang có**.

### Bước 2 — Vẽ các giả thuyết tạo giá trị

Phân biệt vấn đề người dùng, giả thuyết nguyên nhân, giải pháp có thể thử, outcome và impact. Liệt kê những điều sẽ khiến một lựa chọn trở nên **không đáng đầu tư**.

### Bước 3 — Chọn rủi ro lớn nhất cần học trước

Hỏi loại bất định nào đang quyết định việc có nên chi thêm. Ưu tiên cách thử **đủ tin cậy và chi phí tương xứng**; không biến mọi câu hỏi thành một dự án kỹ thuật lớn.

### Bước 4 — Tạo đề xuất đợt kinh phí đầu

Mô tả trần, thời hạn, người có quyền, nguồn lực, mục tiêu học hỏi, output tối thiểu, tiêu chuẩn chất lượng và quyết định ở checkpoint.

### Bước 5 — Tạo bằng chứng qua Increment và đo lường

Sử dụng user story, backlog, Scrum/Kanban/XP và DevOps để giao phần giá trị nhỏ đủ chất lượng. Quan sát outcome người dùng và năng lực vận hành; phân biệt output với hiệu quả.

### Bước 6 — Xem actual, commitment và forecast

Kiểm tra số phát sinh, nghĩa vụ còn lại, burn rate, chi phí vận hành, phần trần chưa giải phóng và dự phòng. Không lấy chỉ số velocity làm số tiền đã tạo giá trị.

### Bước 7 — Ra quyết định có căn cứ

So sánh các phương án tiếp tục, đổi hướng, giảm phạm vi hoặc dừng; kiểm tra guardrails và ràng buộc. Ghi quyết định, giả định, người phê duyệt và milestone tiếp theo.

### Bước 8 — Cải tiến cơ chế quản trị

Theo dõi thời gian chờ phê duyệt, chất lượng dự báo, số quyết định được thay đổi nhờ bằng chứng, rủi ro chất lượng và tác động tới đội. Loại bỏ tầng thủ tục không tăng khả năng kiểm soát hoặc học hỏi.

## 31. Bài tập thực hành: quyết định một khoản cấp kinh phí tiếp theo

**Tình huống giả định:** ban điều hành có trần 600 triệu đồng cho một cơ hội cải thiện tỷ lệ học viên quay lại. Đội đã được duyệt 80 triệu đồng để khám phá; đã chi 65 triệu và có cam kết 10 triệu chưa ghi nhận. Các kết quả:

- Phần lớn học viên được hỏi muốn tìm lại đúng bài cũ dễ hơn.
- Nguyên mẫu có tín hiệu tốt, nhưng mẫu mới có 12 người.
- Hệ thống hiện có lỗi ghi tiến độ khi đổi thiết bị.
- Đề xuất xây tính năng toàn diện là 400 triệu, chưa tính đầy đủ vận hành và kiểm thử tải.
- Một lựa chọn khác là sửa lỗi tiến độ và thử một lát nhỏ với forecast 120–180 triệu.

### Bài tập 1 — Phân loại nguồn lực

**Câu hỏi:** còn bao nhiêu theo trần sau actual và commitment chưa trùng?

~~~text
600 - 65 - 10 = 525 triệu đồng
~~~

**Diễn giải:** 525 triệu là **phần trần còn lại sau hai khoản** trong ví dụ, không chứng minh toàn bộ số đó đã được giải phóng để chi; còn cần xét dự phòng, quyền và khoản nghĩa vụ khác.

### Bài tập 2 — Chọn rủi ro cần kiểm chứng tiếp

**Gợi ý:** lỗi khôi phục tiến độ là rủi ro về tính đúng dữ liệu và trải nghiệm. Trước khi mở rộng, cần kiểm tra/cải thiện khả năng lưu và đọc đúng trạng thái. Chưa đủ căn cứ cho đầu tư hệ thống gợi ý lớn chỉ từ 12 người thử nguyên mẫu.

### Bài tập 3 — Viết một learning milestone

Ví dụ:

> Với một lát “Tiếp tục học” và khôi phục tiến độ đã đạt các tiêu chuẩn chất lượng, đo xem học viên thuộc cohort thí điểm có mở đúng bài và hoàn thành hoạt động học có ý nghĩa dễ hơn không; ghi rõ mẫu, thời gian, các trường hợp bị loại trừ và guardrails trước khi quyết định mở rộng.

**Vì sao tốt hơn “làm xong 8 story”?** Nó nối đầu ra với câu hỏi giá trị và điều kiện ra quyết định.

### Bài tập 4 — Viết một guardrail ngân sách và chất lượng

**Gợi ý:** không giải phóng phần vốn chưa được duyệt; không mở cho người dùng nếu còn lỗi tiến độ không chấp nhận, phân quyền sai hoặc luồng chính không đáp ứng tiêu chuẩn khả năng truy cập áp dụng.

### Bài tập 5 — Ra quyết định khi outcome không thay đổi

Giả sử sau thí điểm đủ cửa sổ, tỷ lệ quay lại hầu như không đổi nhưng thời gian tìm bài giảm rõ.

**Gợi ý:** giá trị giảm ma sát có thể có thật, nhưng giả thuyết nó làm tăng quay lại chưa được xác nhận. Nên nghiên cứu nguyên nhân bỏ học khác, cân đối chi phí duy trì và cân nhắc có cần đổi hướng. **Không gắn nhãn thành công toàn diện bằng một proxy đơn lẻ**.

### Bài tập 6 — Phản biện câu nói “chúng ta đã chi 300 triệu nên phải làm đến cùng”

**Gợi ý:** khoản đã chi cần được ghi nhận và học từ nó, nhưng quyết định hiện tại phải so sánh **chi phí còn phải bỏ ra, lợi ích/rủi ro có thể đạt và phương án thay thế**. Nếu tiếp tục gây tổn thất kỳ vọng lớn hơn, dừng có thể là quyết định quản trị tốt.

### Bài tập 7 — Xác định ai có quyền quyết định

**Gợi ý:** Product Owner chịu trách nhiệm giá trị và thứ tự Product Backlog theo Scrum; người được tổ chức ủy quyền tài chính quyết định cấp vốn vượt ngưỡng; kỹ sư chịu trách nhiệm chất lượng kỹ thuật; bảo mật/pháp lý có thẩm quyền với những kiểm soát bắt buộc theo chính sách. Không mặc định một người có toàn bộ các quyền này.

## 32. Checklist cho đề xuất ngân sách theo học hỏi

### Về vấn đề và bằng chứng

- [ ] Đã nói rõ **vấn đề người dùng hoặc rủi ro cần giải quyết**, không chỉ giải pháp muốn xây?
- [ ] Có giả thuyết từ output tới outcome và impact phù hợp?
- [ ] Đã ghi những giả định trọng yếu chưa được kiểm chứng?
- [ ] Có cách kiểm tra giả thuyết ít tốn kém hơn trước cam kết lớn?
- [ ] Các phát hiện trái kỳ vọng có được ghi nhận và có thể dẫn tới đổi hướng/dừng?

### Về trần và chi phí

- [ ] Trần ngân sách, kỳ áp dụng, nguồn và quyền phê duyệt đã rõ?
- [ ] Phân biệt **budget, funding released, forecast, actual, commitment và contingency**?
- [ ] Chi phí chất lượng, bảo mật, accessibility, vận hành, hỗ trợ và kết thúc có được xét?
- [ ] Có forecast dạng khoảng/giả định khi độ bất định lớn?
- [ ] Nếu actual hoặc forecast vượt ngưỡng, có đường quyết định đúng thẩm quyền?
- [ ] Có tính đến chi phí cơ hội và nguồn lực đang bị giữ ở nhiều công việc dở?
- [ ] Không tự xem ngân sách chưa giải phóng là tiền khả dụng?

### Về learning milestone

- [ ] Mỗi đợt vốn có **câu hỏi học hỏi cụ thể**?
- [ ] Có đầu ra đủ chất lượng để thu bằng chứng, không chỉ “đóng ticket”?
- [ ] Phép đo có đối tượng, tử số/mẫu số, cửa sổ, baseline và nguồn dữ liệu?
- [ ] Có điều kiện để **tiếp tục, sửa, đo tiếp, tạm dừng hoặc dừng**?
- [ ] Có guardrails cho an toàn, bảo mật, quyền riêng tư, khả năng truy cập và vận hành?
- [ ] Đã phân biệt tín hiệu adoption với outcome và impact?
- [ ] Có ghi giới hạn về cỡ mẫu, nguyên nhân và độ không chắc chắn?

### Về quyền và governance

- [ ] Product Owner, Developers, người duyệt kinh phí và chuyên gia kiểm soát biết ranh giới quyền?
- [ ] Đội có quyền thích ứng backlog trong giới hạn được giao?
- [ ] Những quyết định khó đảo ngược có bằng chứng và kiểm soát phù hợp?
- [ ] Hợp đồng, luật, quy định và chính sách kế toán có được tôn trọng?
- [ ] Số bước phê duyệt có tương xứng giá trị kiểm soát, không gây chờ bất hợp lý?
- [ ] Lịch checkpoint phù hợp mức tiêu tiền, rủi ro và thời gian trưởng thành outcome?
- [ ] Quyết định và nguyên nhân được ghi lại để kiểm toán/học hỏi?

### Về tính bền vững

- [ ] Năng lực nhóm có cân đối giữa khám phá, delivery, chất lượng và vận hành?
- [ ] Không dùng target tài chính để buộc bỏ Definition of Done?
- [ ] Có chiến lược dừng an toàn, xử lý dữ liệu, hợp đồng và nghĩa vụ còn lại?
- [ ] Có định kỳ xem lại mục tiêu và chi phí khi giả định thay đổi?
- [ ] Đánh giá thành công bằng **giá trị đã kiểm chứng và quyết định đầu tư tốt hơn**, không bằng tỷ lệ tiêu hết tiền?

Checklist là công cụ thảo luận, **không phải quy trình phê duyệt tài chính, pháp lý hay kiểm toán áp dụng tự động cho mọi doanh nghiệp**.

## 33. Kết luận

**Lập ngân sách theo khả năng học hỏi và giá trị cần kiểm chứng** không có nghĩa bỏ ngân sách hay thay thế quản trị bằng cảm giác. Đó là cách **đặt giới hạn chi tiêu và quyền quyết định rõ ràng**, nhưng dành không gian để điều chỉnh giải pháp theo bằng chứng từ người dùng, chất lượng kỹ thuật, rủi ro và chi phí thực.

Một khoản đầu tư tốt có thể tạo ra Increment hữu ích, mở đường cho outcome bền vững, **hoặc giúp tổ chức phát hiện sớm rằng giả thuyết không đúng và dừng trước khi cam kết nguồn lực lớn hơn**. Cột mốc học hỏi chỉ có ý nghĩa khi chúng thay đổi quyết định. Việc release nhiều tính năng, dùng hết ngân sách hoặc tăng story points không tự chứng minh giá trị.

Trong **AGILE_DEVELOPMENT**, Product Goal và Product Backlog giúp ưu tiên giá trị; Scrum tạo nhịp kiểm tra–thích ứng; Kanban làm minh bạch flow và nút thắt; XP và DevOps giúp thay đổi an toàn và phản hồi sớm. Khi kết hợp với trần ngân sách, forecast cập nhật, nguồn lực được cấp theo giai đoạn, guardrails và trách nhiệm quyết định rõ, tổ chức có thể **đầu tư đủ để học, tăng cam kết khi có bằng chứng và giữ quyền đổi hướng trước khi chi phí sai lầm trở nên quá lớn**.
