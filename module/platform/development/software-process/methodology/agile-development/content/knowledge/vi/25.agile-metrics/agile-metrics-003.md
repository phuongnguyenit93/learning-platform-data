# Đo giá trị sản phẩm thông qua mục tiêu có thể kiểm chứng

Một nhóm phát triển nền tảng học trực tuyến hoàn thành tám user story trong Sprint, nâng tốc độ đóng ticket và triển khai nút **“Học tiếp”**. Báo cáo tiến độ rất tốt. Nhưng người học vẫn bỏ dở khóa vì khó tìm bài, còn nhóm không biết nút mới đã giúp ai quay lại học nhanh hơn hay chưa. Một nhóm khác chỉ phát hành một lát cắt nhỏ, song **giảm rõ rệt thời gian tìm lại bài**, không tăng lỗi tiến độ và được người học xác nhận hữu ích. Nhóm nào tạo giá trị hơn?

Khác biệt nằm ở chỗ **đầu ra không tự chứng minh kết quả**. Velocity, số story points, số tính năng, số ticket Done hay số lần triển khai giúp hiểu một phần tiến độ và khả năng giao hàng, nhưng không trả lời người dùng có được lợi không. Đo giá trị đòi hỏi làm rõ **ai cần thay đổi gì, tại sao, bằng chứng nào cho thấy thay đổi đó đã xảy ra, khi nào sẽ đánh giá và những giới hạn chất lượng nào không được đánh đổi**.

Bài thuộc chương **Đo lường Agile** của module **AGILE_DEVELOPMENT**. Chúng ta kết nối Product Goal, Sprint Goal, user story, backlog, phát hành tăng dần, Scrum, Kanban và các thực hành kỹ thuật XP để xây vòng **lập giả thuyết → tạo phần mềm an toàn → đo → học → điều chỉnh**. Thước đo là công cụ giúp ra quyết định, không phải đích đến của sản phẩm.

> **Ý chính:** Mục tiêu có thể kiểm chứng là một phát biểu về **kết quả có ích trong bối cảnh xác định**, đi kèm tiêu chuẩn quan sát, thời hạn, mức bất định và guardrails. Một danh sách chức năng cần xây chưa phải mục tiêu giá trị.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **activity, output, outcome và impact** khi đo lường phần mềm.
2. Viết mục tiêu sản phẩm có **đối tượng, hành vi mong muốn, baseline, target, thời hạn và guardrails**.
3. Chuyển vấn đề người dùng thành **giả thuyết giá trị, chỉ số và kế hoạch kiểm chứng**.
4. Định nghĩa metric bằng **numerator, denominator, population, đơn vị, cửa sổ thời gian, nguồn dữ liệu và cách loại trừ**.
5. Phân biệt leading/lagging indicators, số đo kết quả/số đo đầu vào và proxy metrics.
6. Tính và diễn giải **conversion, task success, retention, funnel, thời gian thực hiện tác vụ** với denominator rõ.
7. Nhận diện cạm bẫy **mẫu nhỏ, khác biệt cohort/segment, seasonality, thiên lệch và nhầm tương quan với nhân quả**.
8. Thiết kế vòng đo bằng dữ liệu sự kiện, nghiên cứu định tính, phát hành có kiểm soát và thực nghiệm khi khả thi.
9. Sử dụng số liệu để **tiếp tục, cải tiến, đổi hướng, dừng hoặc tìm hiểu thêm**, không biến metric thành KPI thao túng.
10. Kết nối đo giá trị với Scrum, Kanban, XP và các số đo engineering/flow mà không đồng nhất chúng.

## 2. Output không phải outcome, outcome chưa chắc là impact

| Khái niệm | Câu hỏi | Ví dụ nền tảng học trực tuyến | Không được suy ra |
| --- | --- | --- | --- |
| **Activity — hoạt động** | Nhóm đã làm gì? | Code, họp refinement, phỏng vấn người học, kiểm thử | Hoạt động nhiều là đã tạo giá trị |
| **Output — đầu ra** | Đã làm ra thứ gì? | Nút Học tiếp, API tiến độ, 5 PBIs Done | Có tính năng là người dùng đã được lợi |
| **Outcome — kết quả** | Hành vi/trạng thái người dùng thay đổi thế nào? | Người học mở đúng bài nhanh hơn, ít lần tìm nhầm hơn | Tác động học tập dài hạn đã chắc chắn tăng |
| **Impact — tác động dài hạn** | Có tiến bộ lớn hơn cho người dùng/tổ chức không? | Người học đạt mục tiêu học tập, kiến thức bền vững, sản phẩm đáng tin | Một tính năng duy nhất là nguyên nhân của toàn bộ tác động |

~~~mermaid
flowchart LR
    A["Vấn đề: khó tìm bài dở"] --> B["Giả thuyết giá trị"]
    B --> C["Output: Increment đạt Done"]
    C --> D["Exposure: người học được dùng"]
    D --> E["Outcome: tiếp tục đúng bài nhanh"]
    E --> F["Outcome kế tiếp: học có ích"]
    F --> G["Impact: đạt mục tiêu học tập"]
    E -. "Phản hồi để điều chỉnh" .-> B
~~~

Đường nối mô tả **giả thuyết về cơ chế tạo giá trị**, không chứng minh quan hệ nhân quả. Người học bấm nút nhanh có thể chưa học tốt hơn; phải tiếp tục xem bước kế tiếp. Đặc biệt, **thời gian ở trong ứng dụng nhiều hơn không luôn có nghĩa học được nhiều hơn**.

### Ví dụ đối lập

Nhóm A hoàn tất 15 ticket UI, nhưng tính năng chưa đến tay người học do chưa đủ kiểm thử phân quyền. Nhóm B hoàn tất ba story dọc, phát hành an toàn cho một nhóm thử và quan sát thấy tác vụ mở lại đúng bài được thực hiện tốt hơn. **Về output**, A có thể có nhiều ticket hơn; **về bằng chứng outcome**, B đang biết nhiều hơn. Tuy vậy, B vẫn phải kiểm tra chất lượng dữ liệu và mức đại diện của nhóm thử trước khi kết luận tác động rộng.

## 3. Giá trị phải được định nghĩa theo người nhận

“Giá trị” có thể là tiết kiệm thời gian, tăng khả năng đạt mục tiêu, giảm sai sót, tăng khả năng tiếp cận, bảo vệ quyền riêng tư, duy trì niềm tin hoặc hiệu quả kinh doanh bền vững.

| Người nhận giá trị | Vấn đề cần giải quyết | Bằng chứng khả dĩ | Rủi ro khi đo sai |
| --- | --- | --- | --- |
| **Học viên** | Khó quay lại bài, mất tiến độ, không rõ đang học tới đâu | Task success, thời gian tìm bài, lỗi checkpoint, phản hồi, tiến bộ học | Tối ưu click hoặc giờ mở app thay vì học có ích |
| **Giảng viên** | Khó phát hiện ai cần hỗ trợ | Độ chính xác tiến độ, thời gian tìm thông tin, hành động hỗ trợ | Dashboard nhiều chỉ số nhưng không dẫn tới hỗ trợ thật |
| **Đội hỗ trợ** | Nhiều sự cố tiến độ, xử lý chậm | Thời gian giải quyết, tỷ lệ sự cố tái diễn, phản hồi người học | Giảm ticket bằng cách làm khó việc báo lỗi |
| **Đơn vị đào tạo** | Khó biết học viên đạt chuẩn hay không | Kết quả đánh giá năng lực phù hợp, độ hoàn thành có điều kiện | Hạ độ khó để làm đẹp tỷ lệ đạt chứng chỉ |
| **Đơn vị cung cấp** | Khách hàng không nhận đủ lợi ích | Gia hạn dựa trên giá trị, tỷ lệ sử dụng hữu ích, chi phí phục vụ | Dùng thông báo gây nghiện để tăng engagement ngắn hạn |

Một mục tiêu tốt cần **chọn ai đang được phục vụ** và xem xét những người khác có thể bị ảnh hưởng. Ví dụ tăng số thông báo nhắc học có thể làm tăng lượt mở nhưng gây phiền. Vì vậy, cần **guardrails** về chất lượng, quyền riêng tư, dữ liệu và trải nghiệm.

### Proxy metric phải giữ đúng vị trí

Proxy là chỉ báo gián tiếp cho điều khó đo trực tiếp. **Tỷ lệ hoàn thành khóa học** có thể là proxy cho sự tiến bộ, nhưng việc bấm hoàn thành chưa chắc cho thấy kiến thức được hiểu. Một proxy hữu ích khi nhóm:

- Nêu rõ **tại sao** tin nó có liên hệ với giá trị.
- Có cách xem lại liên hệ đó bằng dữ liệu/nghiên cứu khác.
- Nhìn cả những tác động ngoài ý muốn, không chỉ con số mục tiêu.
- Không biến proxy thành định nghĩa duy nhất của giá trị.

## 4. Viết mục tiêu có thể kiểm chứng

| Cách phát biểu | Ví dụ | Vấn đề |
| --- | --- | --- |
| Khẩu hiệu | “Nâng trải nghiệm học tập.” | Không biết ai, trải nghiệm nào và kiểm chứng ra sao |
| Đầu ra | “Ra mắt nút Học tiếp trong Sprint này.” | Biết thứ sẽ xây, chưa biết lợi ích |
| Outcome định hướng | “Giúp học viên tìm lại bài dở dễ hơn.” | Gần nhu cầu nhưng thiếu điều kiện đo |
| Outcome kiểm chứng được | “Trong nhóm học viên đủ quyền và có bài đang dở, tăng tỷ lệ mở đúng bài trong 60 giây từ baseline đã xác minh tới target có ý nghĩa trong bốn tuần, không tăng lỗi checkpoint hoặc truy cập sai quyền.” | Có đối tượng, hành vi, tiêu chí, thời hạn, guardrails |

### Mẫu mô tả mục tiêu

~~~text
ĐỐI TƯỢNG:
  Ai có nhu cầu? Khi nào họ đủ điều kiện được tính?

GIÁ TRỊ / VẤN ĐỀ:
  Công việc nào người dùng muốn hoàn thành?

OUTCOME:
  Hành vi hoặc trạng thái nào cần thay đổi?

BASELINE:
  Mức hiện tại, cửa sổ quan sát, phương pháp và độ tin cậy.

TARGET & THỜI HẠN:
  Thay đổi bao nhiêu là có ý nghĩa? Khi nào sẽ đánh giá?

GUARDRAILS:
  Điều gì không được xấu đi, nhất là dữ liệu và bảo mật?

BẰNG CHỨNG & QUYẾT ĐỊNH:
  Thu thập thế nào, ai phân tích, kết quả nào khiến đổi hướng?
~~~

**Nếu chưa biết baseline, hãy viết “chưa đo — cần xác minh”, không điền một con số tưởng tượng.** Một Sprint chỉ tập trung thiết lập đo lường, quan sát vấn đề và thống nhất định nghĩa cũng có thể là bước học hỏi có ích.

## 5. Giả thuyết giá trị và chuỗi bằng chứng

> **Chúng tôi tin rằng** hiển thị nút Học tiếp cho học viên còn quyền và có bài học dở sẽ **giảm thời gian và số bước để mở đúng bài**, vì hiện họ phải tìm qua danh sách bài. **Chúng tôi sẽ kiểm chứng** bằng đo thời gian tác vụ, tỷ lệ mở đúng bài, quan sát người dùng và số liệu lỗi tiến độ. **Chúng tôi sẽ xem lại** sau khi có đủ dữ liệu cho nhóm thử trong cửa sổ đã chọn.

| Giả định | Bằng chứng cần tìm | Cách kiểm chứng | Hành động nếu không đúng |
| --- | --- | --- | --- |
| Khó tìm bài là vấn đề chính | Người dùng mất nhiều bước để quay lại bài | Phỏng vấn, quan sát tác vụ, phân tích hành trình | Xem lại vấn đề; có thể khó nội dung hay thiếu thời gian |
| Người học nhận ra nút | Người dùng đủ điều kiện thấy và hiểu nút | Usability test, events hợp lệ | Thay nhãn/vị trí/thiết kế |
| Nút giúp mở đúng bài nhanh | Tỷ lệ mở đúng bài, time-to-resume | Task success metric | Điều tra cache, checkpoint, luồng UI |
| Mở lại nhanh dẫn đến học có ích | Hoạt động học tiếp theo, cohort | Funnel/quan sát/đánh giá học | Kiểm tra giả thuyết khác thay vì làm thêm UI |
| Chất lượng được giữ | Lỗi dữ liệu, phân quyền và sự cố | Tests, exploratory checks, monitoring | Dừng rollout không an toàn, sửa rồi kiểm chứng lại |

Không xác nhận một giả thuyết **không nhất thiết là thất bại về học hỏi**: nhóm có thể kịp dừng đầu tư sai. Tuy nhiên, không được lấy câu “đã học được” thay cho việc đo có phương pháp, ra quyết định và giảm rủi ro.

## 6. Product Goal, Sprint Goal và OKR liên hệ ra sao?

Trong Scrum, **Product Goal** mô tả trạng thái tương lai mong muốn của sản phẩm và là commitment của Product Backlog; **Sprint Goal** là mục tiêu đơn nhất cho Sprint, commitment của Sprint Backlog. Chúng không được Scrum Guide quy định là danh sách KPI hoặc OKR bắt buộc.

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Product Goal** | Sản phẩm muốn tiến tới trạng thái nào? | “Học viên có thể quay lại hành trình học thuận tiện, đáng tin.” |
| **Sprint Goal** | Scrum Team cùng hướng tới mục tiêu gì trong Sprint này? | “Học viên đủ quyền mở lại đúng bài đang dở từ trang khóa học.” |
| **Product Backlog** | Những việc gì được sắp thứ tự để cải thiện sản phẩm? | Story Học tiếp, kiểm tra sai tiến độ, thử usability, đo funnel |
| **Increment + Definition of Done** | Phần mềm đã đủ chuẩn tích hợp và sử dụng chưa? | Luồng học tiếp đúng quyền và có test phù hợp |
| **Outcome metrics** | Kết quả người dùng có thay đổi không? | Tỷ lệ mở đúng bài, thời gian tác vụ, lỗi lưu |
| **OKR (nếu dùng)** | Objective và kết quả then chốt nào giúp đánh giá? | Objective học tiếp thuận tiện; KR là tác vụ thành công và chất lượng |

**OKR là một kỹ thuật quản lý mục tiêu có thể bổ trợ, không thay trách nhiệm Scrum.** Một Key Result như “Ra mắt nút Học tiếp” chủ yếu đo output, không phải outcome. Một Key Result tốt hơn có thể đo tỷ lệ mở đúng bài, nhưng vẫn cần định nghĩa, baseline và guardrails.

**Ví dụ số để minh họa cách đặt KR, không phải chuẩn ngành:** tăng task-success rate từ 50% lên 70% trong nhóm đủ điều kiện sau bốn tuần, giảm median time-to-resume từ 90 xuống 50 giây, đồng thời không tăng lỗi dữ liệu và không chấp nhận vi phạm phân quyền. Những ngưỡng này chỉ có ý nghĩa nếu được chọn từ baseline, nhu cầu và rủi ro thực.

## 7. Operational definition: một metric phải có mẫu số rõ

Hai nhóm cùng báo “conversion tăng” nhưng một nhóm tính **lượt bấm**, nhóm kia tính **người dùng duy nhất**; hai kết quả không thể so sánh trực tiếp.

### Mẫu metric contract

~~~text
METRIC: task_success_rate_60s
MỤC ĐÍCH: đo khả năng mở đúng bài trong 60 giây.
POPULATION: học viên đăng nhập, đủ quyền, có bài dở.
ĐƠN VỊ: lượt tác vụ hợp lệ (hoặc người duy nhất: chọn một).
NUMERATOR: số lượt mở đúng bài trong <=60 giây.
DENOMINATOR: tổng lượt tác vụ hợp lệ đã bắt đầu.
START: sự kiện bắt đầu tác vụ từ trang khóa học.
END: bài hợp lệ được mở, hoặc cửa sổ tác vụ hết hạn.
WINDOW: ví dụ 14 ngày sau khi exposure; múi giờ rõ.
SOURCES: course_view, continue_attempt, lesson_open,
         checkpoint_validation; có version cho event schema.
EXCLUSIONS: tài khoản thử, bot hoặc duplicate theo quy tắc rõ.
SEGMENTS: thiết bị, mạng, cohort, loại khóa học.
GUARDRAILS: lỗi checkpoint, truy cập sai quyền, crash.
OWNER: người chịu trách nhiệm định nghĩa và chất lượng dữ liệu.
~~~

Với tỷ lệ thành công của **tác vụ hợp lệ**, công thức là:

\[
\text{Task success rate}=\frac{\text{Số tác vụ đạt điều kiện thành công}}{\text{Tổng tác vụ hợp lệ}}\times100\%.
\]

Nếu quan sát **140 tác vụ hợp lệ** trong đó **98 tác vụ** mở đúng bài trong 60 giây:

\[
\frac{98}{140}\times100\%=70\%.
\]

Đây là **70% tác vụ được quan sát**, không tự đồng nghĩa 70% tất cả học viên đều thành công. Một người thực hiện 20 lần có thể chiếm trọng số lớn hơn 20 người làm một lần. Nếu muốn trả lời “bao nhiêu người được lợi”, phải chuyển đơn vị đo và denominator sang **người dùng duy nhất**, xác định hành vi nào đại diện cho thành công của họ.

### Vì sao định nghĩa phải sống cùng metric?

- **Đủ điều kiện:** người không có bài dở không thể được xem là thất bại của nút Học tiếp.
- **Thời gian:** lấy từ khi trang mở, khi người dùng nhấn nút hay khi bắt đầu tìm bài sẽ cho câu trả lời khác.
- **Đa thiết bị:** một người dùng trên hai thiết bị không tự thành hai người.
- **Sự kiện trùng:** retry hoặc gửi log hai lần cần có quy tắc deduplication.
- **Tracking lỗi:** event bị mất trên mạng yếu có thể làm tỷ lệ sai có hệ thống.

Định nghĩa vận hành cần được **phiên bản hóa** nếu cách tính thay đổi; không nối liền chuỗi thời gian như thể cùng một metric.

## 8. Baseline, target, threshold và guardrail

| Thành phần | Để làm gì? | Ví dụ |
| --- | --- | --- |
| **Baseline** | Mức hiện tại theo định nghĩa và cửa sổ rõ | 52% tác vụ đủ điều kiện mở đúng bài trong 60 giây |
| **Target** | Kết quả mong muốn với thời hạn | Phấn đấu đạt ít nhất 70% trong cửa sổ sau cải tiến |
| **Decision threshold** | Điều kiện kích hoạt hành động hoặc đánh giá tiếp | Nếu thấp hơn mức có ý nghĩa hoặc bằng chứng quá yếu, điều tra và chưa mở rộng |
| **Guardrail** | Điều không được đánh đổi | Không tăng lỗi mất checkpoint, không lộ quyền, dịch vụ đủ ổn định |

**Target không đến từ một con số đẹp.** Cần xem người dùng có nhận ra mức cải thiện, baseline có ổn định, độ biến thiên tự nhiên, tính khả thi và chi phí cơ hội. Guardrail phải tương xứng rủi ro; riêng vi phạm bảo mật nghiêm trọng không thể được “bù trừ” bằng tăng conversion.

### Điểm phần trăm khác phần trăm tương đối

Tỷ lệ tăng từ **50% lên 60%** là tăng **10 điểm phần trăm**, nhưng mức tăng tương đối là:

\[
\frac{60-50}{50}\times100\%=20\%.
\]

Vì vậy “tăng 20%” không đồng nghĩa tăng từ 50% lên 70%. Báo cáo cần ghi cả giá trị trước/sau và loại thay đổi.

## 9. Leading và lagging indicators: đo sớm, diễn giải đúng

| Tín hiệu | Có thể là leading indicator cho | Chưa đủ chứng minh |
| --- | --- | --- |
| Người dùng nhận ra nút Học tiếp | Khả năng bắt đầu hành trình | Có học được kiến thức |
| Mở đúng bài trong 60 giây | Giảm ma sát tác vụ | Duy trì học dài hạn |
| Học một phần có ý nghĩa sau khi mở bài | Buổi học được tiếp tục | Kết quả thi dài hạn |
| D7 retention của người học mới | Người dùng có quay lại sau một tuần | Việc quay lại là có ích cho mọi khóa học |
| Kết quả đánh giá năng lực phù hợp | Mức đạt mục tiêu học tập | Tác động nghề nghiệp tương lai |
| Gia hạn một học kỳ | Giá trị kinh doanh lâu hơn | Một thay đổi UI đơn lẻ đã gây ra gia hạn |

Phân loại leading/lagging **phụ thuộc mục tiêu**. Một chỉ số lagging đối với tác vụ tức thời có thể là leading đối với impact dài hạn. Dùng tín hiệu sớm để điều chỉnh, nhưng không tuyên bố tác động lâu dài từ vài lượt nhấn.

### Khi metric trở thành mục đích: Goodhart

- Tối ưu thời gian trong app bằng cách khiến thao tác rườm rà.
- Nâng tỷ lệ hoàn thành bằng cách hạ chuẩn đánh giá.
- Giảm ticket hỗ trợ bằng cách giấu nút hỗ trợ.
- Tăng velocity bằng cách chia vụn story hoặc giảm Definition of Done.

Giải pháp: **bộ metric cân đối, guardrails, phản hồi định tính và xem lại tác dụng phụ**, tránh dùng một con số làm mục tiêu thưởng/phạt duy nhất.

## 10. Funnel: theo dõi hành trình thay vì chỉ số click

Ví dụ **giả định** có 1.000 lượt tác vụ đủ điều kiện:

| Bước | Số lượt còn lại | Tỷ lệ so với bước trước | Tỷ lệ từ đầu funnel |
| --- | ---: | ---: | ---: |
| Mở trang khóa học | 1.000 | — | 100% |
| Nhìn thấy nút Học tiếp | 900 | 90% | 90% |
| Nhấn nút | 720 | 80% | 72% |
| Mở đúng bài | 648 | 90% | 64,8% |
| Bắt đầu hoạt động học có ý nghĩa | 540 | 83,3% (làm tròn) | 54% |

Vì sao tỷ lệ từ 1.000 xuống 900? Có thể **UI không hiển thị**, **tracking lỗi**, **quyền truy cập khác**, **điều kiện bài dở được xác định sai**, hoặc người dùng đi theo luồng hợp lệ khác. Funnel gợi câu hỏi; nó **không tự chỉ ra nguyên nhân**.

Để tính đúng, cần làm rõ: unit là người hay lượt, thời gian giữa các bước tối đa bao lâu, event nào là “thấy nút”, deep links có bị loại không, nhấn hai lần có tính hai không, cohort đã được exposure thật chưa. Với nhiều đường đi hợp lệ, **task-success rate** có thể phù hợp hơn ép mọi hành trình theo một chuỗi click duy nhất.

## 11. Cohort, D7 retention và hành vi thực sự có ý nghĩa

**Cohort** là nhóm người được xác định bởi một mốc chung, như tuần đăng ký hoặc ngày đầu tiên sử dụng chức năng. **Retention** phải dựa trên một hành vi có nghĩa, không chỉ mở ứng dụng rồi đóng.

Giả sử cohort có 200 học viên bắt đầu khóa học tuần W, trong đó 80 người thực hiện một **hoạt động học được định nghĩa rõ** vào cửa sổ D7:

\[
\text{D7 retention}=\frac{80}{200}\times100\%=40\%.
\]

Định nghĩa D7 có thể là đúng ngày thứ bảy theo lịch, một cửa sổ 24 giờ quanh mốc 7 ngày hoặc cách khác; **phải công bố chính xác**. Cohort chưa đi qua đầy đủ cửa sổ theo dõi **không thể lấy làm mẫu D7 hoàn chỉnh**.

| So sánh | Giá trị | Cạm bẫy |
| --- | --- | --- |
| Người học bắt đầu trước và sau cải tiến | Theo dõi xu hướng | Mùa thi, marketing, cấu trúc khóa học đã đổi |
| Cohort có/không exposure | Nhìn kết quả khi có khả năng mới | Tự chọn vào nhóm làm xuất hiện thiên lệch |
| Người học mobile và desktop | Phát hiện trải nghiệm khác nhau | Một người có thể dùng cả hai |
| Khóa ngắn và khóa dài | Nhu cầu quay lại khác nhau | Retention thấp vì người học đã hoàn thành có thể là tốt |

**Người học hoàn thành khóa ngắn rồi không quay lại có thể đã đạt giá trị.** Đừng tự biến retention thành chỉ số tốt tuyệt đối. Phải đối chiếu với **công việc người dùng muốn làm**.

## 12. Phân bố và trải nghiệm ở “đuôi”: đừng chỉ dùng trung bình

Một thay đổi có thể giúp phần lớn người dùng nhưng làm những người mạng yếu chậm hơn đáng kể. Vì thế, bên cạnh tỷ lệ thành công, nên nhìn **thời gian phân bố, median và những trường hợp chậm bất thường**.

Giả sử thời gian mở bài (giây) của 10 tác vụ:

~~~text
12, 14, 15, 17, 20, 22, 26, 31, 70, 120
~~~

- **Median (trung vị)** = \((20+22)/2=21\) giây.
- **Mean (trung bình số học)** = \(347/10=34{,}7\) giây.
- **Hai trong mười tác vụ** mất trên 60 giây, tương đương 20%.
- Hai trường hợp chậm có thể là vấn đề mạng, dữ liệu hoặc một phân khúc khác; cần tìm hiểu.

| Thống kê | Hữu ích khi | Giới hạn |
| --- | --- | --- |
| **Mean** | Cần trung bình số học trong mục tiêu đã định | Nhạy với ngoại lệ hoặc phân bố lệch |
| **Median** | Muốn thấy trải nghiệm điển hình ít bị ảnh hưởng bởi đuôi dài | Che những trường hợp rất chậm |
| **P90/P95** | Muốn nhìn trải nghiệm ở nhóm chậm | Với mẫu nhỏ có thể rất không ổn định |
| **Success within threshold** | Có ngưỡng thời gian có ý nghĩa với tác vụ | Ngưỡng tùy tiện có thể bỏ qua cảm nhận thực |
| **Phân bố theo segment** | Phát hiện mobile/mạng yếu hoặc loại khóa khác | Phân khúc nhỏ dễ nhiễu và tăng rủi ro riêng tư |

**Không một thống kê nào tự nói toàn bộ sự thật.** Nếu tỉ lệ người dùng có trải nghiệm tệ tăng, trung vị không thay đổi cũng không thể coi là đã bảo đảm chất lượng. Cần xem cả phân bố, guardrails và tình huống cá nhân có mức ảnh hưởng lớn.

### Dữ liệu từ tác vụ và dữ liệu từ người dùng

Một người làm 30 tác vụ thường không nên có **trọng số bằng 30 người** khi mục tiêu là tỷ lệ học viên được lợi. Nếu hệ thống tính duration cho mỗi tác vụ, một nhóm người sử dụng rất thường xuyên có thể chi phối trung bình. Cần quyết định liệu tính **mỗi tác vụ**, **trung bình mỗi người**, **mỗi phiên**, hay **một cohort người dùng** là phù hợp với câu hỏi sản phẩm.

## 13. Phân nhóm và nguy cơ Simpson: tổng thể có thể đánh lừa

Metric tổng có thể giảm dù từng phân khúc đều cải thiện, chỉ vì **tỷ trọng phân khúc thay đổi**.

### Ví dụ có số liệu minh họa

| Phân khúc | Kỳ trước thành công / tổng | Tỷ lệ kỳ trước | Kỳ sau thành công / tổng | Tỷ lệ kỳ sau |
| --- | ---: | ---: | ---: | ---: |
| **Desktop** | 80/100 | 80% | 18/20 | 90% |
| **Mobile** | 20/100 | 20% | 80/200 | 40% |
| **Tổng** | 100/200 | 50% | 98/220 | 44,5% |

Tỷ lệ **cả hai nhóm tăng**, nhưng tỷ lệ tổng **giảm** vì ở kỳ sau mobile chiếm tỷ trọng lớn hơn. Đây là minh họa cho cách **cấu trúc mẫu làm thay đổi kết luận từ số tổng**.

Điều đó **không chứng minh** tính năng là nguyên nhân của cải thiện trong từng phân khúc. Còn có thể có mùa vụ, mức kinh nghiệm, bản ứng dụng, loại khóa học và thay đổi đo lường. Để hiểu giá trị thật, cần nhìn **kết quả theo nhóm, tỉ trọng mẫu, cách lấy mẫu và điều kiện tiếp xúc**.

### Những phân khúc nên xem xét

- Học viên mới và người học quay lại.
- Mobile, desktop và những thiết bị thực sự được hỗ trợ.
- Kết nối tốt/yếu khi có cách đo hợp lý và tôn trọng riêng tư.
- Khóa học ngắn/dài, tự chọn/bắt buộc, loại nội dung.
- Người đã đủ điều kiện thấy tính năng và người chưa được exposure.
- Cohort theo tuần/tháng bắt đầu học.

Không thu thập thuộc tính nhạy cảm chỉ vì dashboard trông thú vị. Mỗi phân khúc cần **mục đích, cơ sở hợp lệ, biện pháp bảo vệ và kích thước mẫu đủ tránh kết luận thiếu căn cứ**.

### Một thay đổi tốt cho trung bình có thể gây hại cho số ít

Khi tối ưu cho phần đông, cần kiểm tra những người có nhu cầu tiếp cận khác biệt, ví dụ người sử dụng bàn phím/trình đọc màn hình. Không có bằng chứng trên một nhóm nhỏ **không phải** bằng chứng nhóm ấy không bị ảnh hưởng. Có thể cần kiểm thử khả dụng/accessibility chuyên sâu hơn thay vì chỉ nhìn conversion trung bình.

## 14. Dữ liệu sự kiện: đo cái gì, khi nào và ở đâu?

Đo lường hành vi sản phẩm đòi hỏi **instrumentation**: sự kiện, định danh, timestamp và trạng thái được ghi đủ để trả lời câu hỏi, không thu thập vô hạn dữ liệu.

### Sơ đồ sự kiện minh họa

~~~mermaid
flowchart TD
    A["User đủ điều kiện<br/>mở trang khóa học"] --> B["course_view"]
    B --> C["continue_visible"]
    C --> D["continue_attempt"]
    D --> E{"Backend kiểm tra<br/>quyền và checkpoint"}
    E -->|Hợp lệ| F["lesson_open_success"]
    E -->|Không hợp lệ| G["lesson_open_failure<br/>mã lý do an toàn"]
    F --> H["Hành vi học tiếp<br/>được định nghĩa"]
    G --> I["Lỗi/feedback và cải tiến"]
~~~

### Event contract minh họa

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **event_name** | continue_attempt, lesson_open_success... | Có danh mục và cách đặt tên nhất quán |
| **event_version** | Phiên bản cấu trúc của event | Thay đổi schema phải được truy vết |
| **anonymous_actor_id** | ID phân tích đã được bảo vệ và có chính sách | Không mặc định ghi tên/email trong log |
| **task_id/session_id** | Nối các bước của cùng tác vụ khi hợp lệ | Chống nhầm người khi logout/login |
| **timestamp** | Thời điểm sự kiện, có múi giờ/nguồn đồng hồ | Đồng hồ thiết bị có thể sai, event đến muộn |
| **feature_exposure** | Được tiếp cận bản nào/flag nào | Không suy từ có code trên production là đã exposure |
| **result/status** | Thành công hoặc lý do thất bại | Không đưa token, nội dung nhạy cảm vào lỗi |
| **device_context** | Loại thiết bị theo mức cần thiết | Tránh fingerprinting quá mức |

**Phân biệt event được gửi với sự kiện thật đã xảy ra.** Một callback UI nói “click thành công” không tự chứng minh backend đã mở đúng bài hay dữ liệu đã ghi xuống. Đối với metric quan trọng, cần **nguồn xác nhận phù hợp** và cơ chế nối các sự kiện đúng.

### Ví dụ cách tính bằng giả mã SQL

~~~sql
-- Minh họa khái niệm, KHÔNG chạy trực tiếp.
-- eligible_tasks đã lọc tài khoản thử, trùng lặp và điều kiện quyền.
SELECT
  COUNT(*) AS eligible_tasks,
  SUM(CASE WHEN opened_correct_lesson = TRUE
            AND elapsed_seconds <= 60
           THEN 1 ELSE 0 END) AS successes,
  100.0 * SUM(CASE WHEN opened_correct_lesson = TRUE
                    AND elapsed_seconds <= 60
                   THEN 1 ELSE 0 END)
       / NULLIF(COUNT(*), 0) AS success_rate_percent
FROM eligible_tasks
WHERE task_start >= :window_start
  AND task_start < :window_end;
~~~

Trước khi diễn giải truy vấn, cần biết **bảng eligible_tasks được tạo thế nào**, độ chính xác elapsed_seconds và hành vi khi một task thiếu sự kiện kết thúc. Nếu chỉ tính các task có event thành công, denominator sẽ bị thiên lệch tăng.

## 15. Chất lượng dữ liệu trước khi ra quyết định

**Dashboard đẹp có thể hiển thị những số liệu sai.** Kênh ghi sự kiện có thể mất dữ liệu khi mạng yếu, ghi trùng do retry, đổi tên event không đồng bộ giữa web và mobile, hoặc gắn sai cohort.

### Bảng kiểm tra chất lượng dữ liệu

| Lỗi dữ liệu | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| **Missing events** | Số tác vụ ghi nhận ít bất thường so với log backend | Đối chiếu nguồn, kiểm tra trình duyệt/mạng và điều kiện consent |
| **Duplicate events** | Một lần nhấn tạo nhiều bản ghi | Khóa idempotency hoặc dedup theo quy tắc đã xác định |
| **Schema drift** | Một phiên bản app gửi tên/trường mới | Version schema, kiểm tra tương thích và giám sát |
| **Clock skew / late arrivals** | Event tới sau hoặc timestamp không theo thứ tự | Chính sách event time/processing time, cửa sổ cập nhật |
| **Bot/test accounts** | Nhiều tác vụ lặp không đại diện | Loại trừ có tài liệu, tránh xóa nhầm người dùng thật |
| **Wrong eligibility** | Người không có bài dở vẫn nằm trong denominator | Xác nhận điều kiện ở backend hoặc nguồn đủ tin cậy |
| **Sample selection bias** | Chỉ những người bật tính năng mới được đo | Ghi rõ cách exposure và cách đối chiếu |
| **Metric definition changed** | Tỷ lệ “tăng vọt” đúng ngày cập nhật tracking | Chú thích sự kiện, so sánh định nghĩa mới và cũ |

### Ba bước kiểm tra tối thiểu trước khi công bố “đã đạt mục tiêu”

1. **Định nghĩa:** numerator, denominator, cửa sổ và population có nhất quán?
2. **Dữ liệu:** có thiếu, trùng, sai timestamp, thay đổi event schema hay lệch segment?
3. **Diễn giải:** mức cải thiện lớn hơn biến động thông thường không, và guardrails có ổn?

Nếu tracking chưa đáng tin, kết luận phù hợp có thể là **“chưa đủ bằng chứng”**. Đây là kết luận trung thực, tốt hơn tuyên bố tăng 30% từ dữ liệu sai.

## 16. Kiểm chứng nhân quả: A/B testing và thí nghiệm

Một dashboard cho thấy sau khi ra nút Học tiếp, tỷ lệ tiếp tục học tăng. Nhưng có thể cùng thời điểm nhà trường mở chiến dịch nhắc học hoặc học kỳ vừa bắt đầu. **Thay đổi cùng thời điểm không chứng minh nút là nguyên nhân**.

Khi khả thi và an toàn, một **thử nghiệm ngẫu nhiên có đối chứng** giúp tách bớt các nguyên nhân bên ngoài.

### Thiết kế thử nghiệm minh họa

| Thành phần | Thiết kế ví dụ |
| --- | --- |
| **Giả thuyết** | Nút Học tiếp giúp học viên đủ điều kiện mở đúng bài trong 60 giây thường xuyên hơn |
| **Population** | Người dùng được phép tham gia, có bài đang dở, trong phạm vi hỗ trợ |
| **Đơn vị randomization** | Người dùng, nếu cần giữ trải nghiệm nhất quán qua nhiều phiên |
| **Control** | Trải nghiệm hiện hành, vẫn đầy đủ an toàn và quyền truy cập |
| **Treatment** | Có nút Học tiếp mới |
| **Primary outcome** | Tỷ lệ mở đúng bài trong 60 giây theo một đơn vị đã định |
| **Guardrails** | Lỗi checkpoint, quyền riêng tư, crash, khả dụng thiết yếu |
| **Observation window** | Đủ để người dùng có cơ hội trải nghiệm; nêu thời gian trước |
| **Stop criteria** | Sự cố an toàn, mất dữ liệu, vượt guardrail hoặc kết thúc kế hoạch |

### Ví dụ kết quả đơn giản

Giả sử phân bổ ngẫu nhiên hợp lệ và đủ điều kiện:

| Nhóm | Số người đáp ứng tiêu chí | Tổng số người đã có cơ hội | Tỷ lệ |
| --- | ---: | ---: | ---: |
| Control | 300 | 500 | 60% |
| Treatment | 360 | 500 | 72% |

**Chênh lệch quan sát được** = **12 điểm phần trăm**, mức tăng tương đối so với control = \( (72-60)/60 \times100\%=20\% \). Đây là ví dụ **số học**, không phải kết luận thống kê rằng treatment chắc chắn làm tăng outcome 12 điểm phần trăm trong toàn bộ dân số.

### Những điều phải xét trước khi kết luận

- **Randomization thật:** có phân bổ người dùng phù hợp và nhất quán qua thiết bị không?
- **Sample ratio mismatch:** số người giữa nhóm có chênh lệch bất thường do lỗi triển khai hay lọc?
- **Exposure thật:** có người ở treatment nhưng chưa từng đủ cơ hội nhìn tính năng?
- **Mức độ độc lập:** một người nhiều phiên không phải nhiều quan sát độc lập khi đơn vị randomization là người.
- **Khoảng tin cậy và độ lớn hiệu ứng:** cần nhìn độ bất định, không chỉ một p-value.
- **Mẫu và thời gian:** có đủ dữ liệu để thấy một mức thay đổi có ý nghĩa không?
- **Đa chỉ số và nhìn dữ liệu liên tục:** chọn kết quả đẹp nhất trong hàng chục metric hoặc dừng thử ngay khi thấy p-value nhỏ có thể tăng dương tính giả.
- **Tác động không mong muốn:** metric chính tăng nhưng lỗi dữ liệu hay ảnh hưởng nhóm dễ tổn thương có xấu đi?

Không phải mọi vấn đề đều phù hợp thử nghiệm ngẫu nhiên. **Quy tắc bảo mật bắt buộc không thể được bỏ cho nhóm control** để “đo tác động”. Với thay đổi có nguy cơ gây hại, cần thực nghiệm phù hợp và **thiết kế bảo vệ**.

## 17. Nếu không A/B test được: quan sát có cấu trúc

Nhiều đội chỉ có ít người dùng, phạm vi triển khai theo hợp đồng, hoặc không thể phân nhóm ngẫu nhiên. Khi đó vẫn có thể học bằng **đo trước/sau, cohort có thể so sánh, thử nghiệm từng giai đoạn, nghiên cứu tác vụ, nhật ký vận hành và phản hồi định tính**.

### Một khung phân tích before/after có trách nhiệm

1. **Định nghĩa cùng metric:** không thay numerator/denominator ở giữa rồi so sánh như cùng thước đo.
2. **Chọn cửa sổ phù hợp:** xét ngày trong tuần, kỳ thi, kỳ nghỉ và chu kỳ học.
3. **Ghi những thay đổi đồng thời:** marketing, thay đổi chương trình học, lỗi dịch vụ, đổi đối tượng dùng.
4. **Xem trend trước thay đổi:** kết quả có đang tăng/giảm từ trước không?
5. **Phân khúc và cohort:** thành phần người dùng có khác nhau?
6. **Đối chiếu bằng chứng độc lập:** usability sessions, phản hồi hỗ trợ, lỗi kỹ thuật, học viên thực.
7. **Nêu giới hạn kết luận:** “phù hợp với giả thuyết” khác “đã chứng minh hoàn toàn do tính năng”.

### Ví dụ diễn giải đúng mức

**Không nên viết:** “Nút Học tiếp khiến retention tăng 15%.”

**Có thể viết:** “Trong bốn tuần sau khi triển khai, D7 retention đo theo cùng định nghĩa tăng từ 40% lên 46% trong cohort mới; đồng thời có chiến dịch nhắc học và thay đổi lịch khai giảng. Kết quả là tín hiệu khả quan nhưng chưa tách được tác động của nút mới; cần quan sát thêm hoặc thiết kế so sánh phù hợp.”

Đây không phải né tránh trách nhiệm. Nó giúp lãnh đạo **đầu tư đúng mức dựa trên độ chắc chắn thật**, thay vì biến tương quan thành nguyên nhân để khóa roadmap.

## 18. Độ bất định và ý nghĩa thực tiễn

Mọi tỷ lệ đo trên một tập người dùng hữu hạn đều có **độ bất định**. Một mức tăng 2 điểm phần trăm có thể rất quan trọng trên sản phẩm lớn; mức tăng 20 điểm phần trăm trên 5 lượt tác vụ có thể chưa đáng tin.

### Tín hiệu và kết luận

| Tình huống | Cách đọc phù hợp |
| --- | --- |
| 4/5 tác vụ thành công sau thay đổi | Có thể là phát hiện hữu ích, nhưng mẫu nhỏ để suy rộng |
| 800/1.000 tác vụ thành công với nguồn dữ liệu ổn định | Có thông tin nhiều hơn, vẫn cần xét tính đại diện và quan hệ nhân quả |
| Một nhóm cải thiện nhưng nhóm khác xấu đi | Xem phân khúc, tác động và guardrails trước khi mở rộng |
| Chênh lệch nhỏ nhưng ảnh hưởng chi phí lớn | Xem ý nghĩa kinh tế/thực tiễn và rủi ro, không chỉ ý nghĩa thống kê |
| Không thấy khác biệt rõ | Có thể không có hiệu ứng đáng kể **hoặc** thí nghiệm thiếu lực đo |

Đừng thay **thống kê** bằng cảm giác, cũng đừng dùng một test thống kê để khỏi suy nghĩ về **giá trị thật**. Cần trả lời hai câu hỏi: “Bằng chứng cho thấy điều gì?” và “Nếu điều đó đúng, nó có quan trọng với người dùng không?”.

## 19. Instrumentation và quyền riêng tư: đo vừa đủ

Muốn cá nhân hóa hoặc quan sát tốt không có nghĩa được tự do thu thập mọi dữ liệu học tập. Kết quả học, tiến độ, hành vi đọc và thông tin tài khoản có thể nhạy cảm trong ngữ cảnh.

### Nguyên tắc thực hành

- **Mục đích rõ:** chỉ thu trường cần cho câu hỏi sản phẩm, an toàn và vận hành có căn cứ.
- **Giảm dữ liệu:** ưu tiên tổng hợp, định danh đã được bảo vệ và chỉ số không cần nội dung cá nhân.
- **Quyền và kiểm soát:** tuân thủ chính sách, nghĩa vụ pháp lý, đồng ý/cơ sở hợp lệ khi cần.
- **Bảo vệ:** mã hóa, giới hạn truy cập, chính sách lưu/xóa và tránh ghi dữ liệu nhạy cảm trong log.
- **Minh bạch:** người dùng không bị dẫn dắt sai về mục đích theo dõi.
- **Giới hạn phân khúc:** tránh kết luận về cá nhân từ nhóm quá nhỏ hoặc đưa dữ liệu có thể nhận diện vào dashboard rộng.
- **Kiểm tra tính công bằng:** việc tối ưu có ảnh hưởng xấu tới người ít có dữ liệu/thiết bị cũ hoặc nhu cầu accessibility không?

### Ví dụ

Để đo thời gian tìm lại bài, có thể cần timestamp bắt đầu tác vụ và event mở thành công, **không cần lưu nội dung toàn bộ ghi chú cá nhân trong bài**. Nếu log cần thông tin để gỡ lỗi checkpoint, hãy chọn dữ liệu tối thiểu và có chính sách hạn chế truy cập.

## 20. Guardrails về chất lượng và outcome ngoài ý muốn

Một tính năng đạt tỷ lệ click cao nhưng làm mất tiến độ hoặc lộ dữ liệu học viên **không phải thành công**. Mỗi mục tiêu giá trị cần những giới hạn liên quan.

| Mục tiêu chính | Guardrails cần cân nhắc | Hành động khi vi phạm |
| --- | --- | --- |
| Tăng tỷ lệ Học tiếp thành công | Lỗi checkpoint, mở sai bài, phân quyền | Tạm dừng rollout nguy hiểm, điều tra và xử lý |
| Tăng tốc độ hoàn thành tác vụ | Không làm giảm khả dụng trên thiết bị hỗ trợ | Phân khúc, kiểm tra đuôi phân bố, sửa UI |
| Tăng D7 retention | Không spam thông báo, không gây áp lực không lành mạnh | Giảm thông báo, đánh giá trải nghiệm và opt-out |
| Tăng hoàn thành khóa học | Không làm giảm độ tin cậy đánh giá năng lực | Kiểm tra độ khó, gian lận, chất lượng kiến thức |
| Giảm ticket hỗ trợ | Không làm khó việc tìm hỗ trợ hoặc bỏ lọt sự cố | Theo dõi khảo sát và kênh phản hồi độc lập |

### Dữ liệu “không thấy lỗi” chưa chứng minh tuyệt đối an toàn

Giả sử sau rollout nhỏ **chưa thấy sự cố rò rỉ dữ liệu**. Đây là thông tin tốt, nhưng có thể do mẫu nhỏ hoặc khả năng phát hiện yếu. Rủi ro bảo mật cần **kiểm thử quyền, threat modeling, review kỹ thuật và giám sát thích hợp**, không chờ sự cố thật xuất hiện như cách đo duy nhất.

Đối với các điều kiện bắt buộc, **Definition of Done và chính sách release** không thể bị hạ vì primary metric đẹp. Một phép đánh đổi “thêm 5% conversion để chấp nhận lộ dữ liệu” không phù hợp.

## 21. Kỹ thuật giao hàng và đo dòng công việc khác đo giá trị

Nhóm cần cả số đo **khả năng giao phần mềm** và số đo **người dùng được lợi**, nhưng không nên gộp chúng.

| Số đo | Trả lời câu hỏi | Không tự chứng minh |
| --- | --- | --- |
| **Velocity/story points** | Nhóm Sprint có thể sử dụng lịch sử ước lượng nội bộ thế nào? | Giá trị sản phẩm hay năng suất cá nhân |
| **Throughput** | Có bao nhiêu work items đạt Done trong một khoảng? | Mỗi item có mức giá trị tương đương |
| **Cycle time** | Từ start đến finish của work item mất bao lâu? | Người dùng có thích giải pháp không |
| **WIP / work item age** | Có nhiều việc dở và tắc nghẽn ở đâu? | Chúng ta đang làm đúng vấn đề |
| **Deployment frequency** | Thay đổi đến production thường xuyên ra sao? | Tính năng đã bật hoặc người dùng nhận giá trị |
| **Change lead time** | Đưa một thay đổi kỹ thuật từ mốc được xác định đến production mất bao lâu? | Ý tưởng tạo tác động ngay sau deploy |
| **Change failure/recovery** | Đưa thay đổi lên có đáng tin và phục hồi nhanh không? | Kết quả học tập hoặc sự hài lòng đã tốt |
| **Task success / retention / outcome** | Người dùng thay đổi hành vi hữu ích thế nào? | Đội đã giao hàng hiệu quả mà không cần xem chi phí/rủi ro |

Một nhóm có thể **đẩy throughput lên** bằng cách chia story thành nhiều task nhỏ, trong khi người học vẫn đợi một luồng dùng được. Ngược lại, tỷ lệ thành công tăng nhưng mọi thay đổi mất nhiều tháng có thể cho thấy **nút thắt flow**. Cần đọc các metric như **các góc nhìn bổ trợ**, không coi một số đo đơn lẻ là sức khỏe toàn bộ sản phẩm.

### Liên hệ định luật Little một cách thận trọng

Trong hệ thống dòng công việc đủ ổn định, có ranh giới và đơn vị nhất quán:

\[
\text{Average WIP}\approx \text{Average Throughput Rate}\times\text{Average Cycle Time}.
\]

Đây là quan hệ trung bình phục vụ **hiểu flow**, không phải công thức dự báo giá trị. Giảm cycle time bằng cách bỏ bảo mật có thể khiến số flow đẹp hơn nhưng giá trị sản phẩm giảm nghiêm trọng.

## 22. Hướng từ Product Goal tới một bộ thước đo cân đối

Một dashboard có hàng chục biểu đồ không nhất thiết hỗ trợ quyết định tốt. Nên xây **một cây mục tiêu và metric có quan hệ rõ**, mỗi chỉ số trả lời một câu hỏi.

~~~mermaid
flowchart TD
    A["Product Goal<br/>học viên học tiếp thuận tiện, tin cậy"] --> B["Outcome chính<br/>mở đúng bài nhanh và an toàn"]
    B --> C["Task success rate"]
    B --> D["Time-to-resume"]
    A --> E["Outcome theo thời gian<br/>học viên tiếp tục hoạt động học hữu ích"]
    E --> F["Meaningful return / cohort"]
    A --> G["Guardrails"]
    G --> H["Lỗi dữ liệu tiến độ"]
    G --> I["Quyền truy cập và an toàn"]
    G --> J["Khả dụng và ổn định"]
    A --> K["Khả năng giao thay đổi"]
    K --> L["Cycle time / WIP<br/>và độ tin cậy pipeline"]
~~~

### Primary metric và diagnostic metrics

**Primary metric** phải gắn gần nhất với outcome đang ưu tiên. **Diagnostic metrics** giúp tìm nơi vấn đề xảy ra, ví dụ funnel, độ trễ API, tỷ lệ nhìn thấy nút và thời gian phản hồi. **Guardrails** ngăn đạt mục tiêu bằng cách gây hại.

| Vai trò của chỉ số | Ví dụ cho mục tiêu Học tiếp | Quyết định có thể hỗ trợ |
| --- | --- | --- |
| **Primary outcome** | Tỷ lệ tác vụ mở đúng bài trong 60 giây | Hành vi có cải thiện đủ có ý nghĩa không? |
| **Diagnostic** | Tỷ lệ thấy nút, click-to-open latency, lỗi checkpoint | Vấn đề nằm ở discoverability, UI, API hay dữ liệu? |
| **Longer-term outcome** | Meaningful D7 return của cohort phù hợp | Cải thiện tác vụ có đi cùng giá trị học tiếp không? |
| **Quality guardrail** | Lỗi tiến độ, quyền truy cập, crash | Có cần tạm dừng rollout hoặc sửa trước không? |
| **Delivery health** | Work item age, CI reliability, cycle time | Nhóm có thể thử và học từ thay đổi đủ nhanh không? |

### Có nên chọn một North Star Metric?

Một số sản phẩm chọn **North Star Metric** — thước đo đại diện cho giá trị cốt lõi mà khách hàng thường xuyên nhận được. Ví dụ với nền tảng học có thể là **số học viên thực hiện một hoạt động học có ý nghĩa trong tuần**, nhưng nó chỉ là một ứng viên cần kiểm chứng.

Không phải mọi sản phẩm nên dùng đúng một North Star, nhất là khi có nhiều nhóm người dùng và nghĩa vụ quan trọng. Một metric trung tâm **không được thay thế** các thước đo chất lượng, tác động học tập và quyền riêng tư. Chọn North Star vì nó giúp phối hợp quyết định, không vì phong trào đặt tên.

## 23. Case study xuyên suốt: từ ý tưởng “Học tiếp” tới quyết định sản phẩm

Đây là **bài tập giả định** với các con số minh họa. Mục tiêu là thực hành cách lập mục tiêu, chọn metric và diễn giải bằng chứng; không phải báo cáo nghiên cứu thực nghiệm.

### 23.1. Bối cảnh

Một nền tảng có các khóa ngắn và dài. Nhiều học viên nói rằng sau vài ngày không học, họ quên vị trí bài đang dở. Product Owner muốn nhóm xây trang “Tiến độ học tập” đầy đủ; Developers đề nghị thử một nút nhỏ “Học tiếp” trước.

**Vấn đề cần khám phá:** Người học thật sự bỏ cuộc vì khó tìm bài, vì không hiểu bài hay vì những lý do khác? Nếu giải quyết được việc tìm bài, điều gì có thể thay đổi?

### 23.2. Phát biểu giả thuyết

> “Đối với học viên đã đăng nhập, còn quyền và có một bài đang dở, nếu đưa nút Học tiếp lên trang khóa học thì họ sẽ tìm và mở đúng bài nhanh hơn. Dấu hiệu ban đầu là tỷ lệ tác vụ thành công trong 60 giây tăng; kết quả theo sau là nhiều người tiếp tục một hoạt động học hữu ích. Chúng ta phải giữ tính đúng đắn checkpoint, bảo mật và khả năng dùng trên thiết bị trong phạm vi hỗ trợ.”

### 23.3. Chọn metric contract

| Thành phần | Quy định minh họa |
| --- | --- |
| **Population** | Học viên đăng nhập, đủ quyền, có ít nhất một bài dở hợp lệ |
| **Task start** | Từ khi người dùng bắt đầu nhiệm vụ tìm bài trong trang khóa học |
| **Task success** | Đúng bài hợp lệ mở trong không quá 60 giây |
| **Đơn vị** | Một tác vụ hợp lệ; kèm kết quả theo người dùng để tránh lệch do dùng nhiều |
| **Baseline window** | Hai tuần quan sát trước khi thêm nút, cùng điều kiện |
| **Target window** | Bốn tuần sau exposure có kiểm soát; cohort đủ thời gian |
| **Primary metric** | Task success in 60 seconds |
| **Diagnostics** | Nút visible, attempt, mở đúng bài, elapsed time, error reasons |
| **Guardrails** | Lỗi checkpoint, sai quyền, crash, usability/accessibility |
| **Owner** | Product Owner quyết định mục tiêu/giá trị, Developers cùng chuyên môn phân tích dữ liệu bảo đảm kỹ thuật đo |

### 23.4. Kiểm tra baseline

Giả sử nghiên cứu tác vụ và event tracking đã được đối chiếu đủ tin cậy:

| Kỳ quan sát | Thành công / tác vụ hợp lệ | Tỷ lệ | Trung vị thời gian |
| --- | ---: | ---: | ---: |
| **Trước cải tiến** | 120/240 | 50% | 92 giây |
| **Sau cải tiến, nhóm thử** | 168/240 | 70% | 49 giây |

Tỷ lệ thành công tăng từ 50% lên 70%, tức **20 điểm phần trăm**, hay **40% tương đối** so với baseline. Trung vị giảm 43 giây. Đây là **chênh lệch mô tả**, chưa mặc nhiên là tác động nhân quả do nút mới vì còn phụ thuộc mẫu, mùa vụ và điều kiện đo.

### 23.5. Không dừng ở metric chính

Nhóm cũng kiểm tra:

- Người học mobile mạng yếu có cải thiện tương ứng không?
- Những lỗi checkpoint bị ghi đè hoặc không lưu có xuất hiện thêm?
- Nút có hoạt động bằng bàn phím/trình đọc màn hình trong phạm vi hỗ trợ?
- Có người nhấn nút nhưng không bắt đầu học do bài quá khó?
- Lượt hỗ trợ liên quan mất tiến độ và quyền học có thay đổi?

Giả sử metric chính cải thiện nhưng một nhóm người học mobile báo trạng thái “Đã lưu” sai. Đây là **guardrail nghiêm trọng** cần xử lý trước khi tuyên bố sản phẩm thành công hoặc tăng exposure.

### 23.6. Diễn giải kết quả theo nhóm

Ví dụ:

| Nhóm | Kỳ trước | Kỳ sau | Câu hỏi tiếp |
| --- | ---: | ---: | --- |
| **Desktop hợp lệ** | 60% thành công | 82% | Người học có cần ít bước hơn hay chỉ đổi cách tracking? |
| **Mobile hợp lệ** | 42% | 58% | Vì sao vẫn thấp; UI, tốc độ mạng hay độ chính xác dữ liệu? |
| **Người dùng mới** | 40% | 55% | Có nhận ra ý nghĩa của nút chưa? |
| **Người dùng lâu năm** | 64% | 78% | Có thiên lệch do đã quen điều hướng cũ không? |

Đây là **các số giả định độc lập**, không phải bảng đã tính toán khớp với mẫu ở trên. Trước khi công bố kết quả chính thức, phân khúc phải **được tính từ cùng tập dữ liệu với các denominator cụ thể**; không cộng các tỷ lệ đã làm tròn để suy ra tỷ lệ tổng.

### 23.7. Phản hồi định tính làm thay đổi backlog

Trong phiên quan sát, một số học viên vẫn mở sai bài vì khóa học có nhiều bài đang dở, còn nút chưa nói rõ sẽ mở bài nào. Product Owner và Developers có thể ưu tiên:

1. Hiển thị tên bài sẽ mở, nếu phù hợp với quyền riêng tư và bố cục.
2. Làm rõ quy tắc chọn bài và kiểm thử các trường hợp có nhiều checkpoint.
3. Thử phản hồi thiết kế trên mobile trước khi mở rộng.
4. Đo task success/guardrails lại theo cùng định nghĩa.

**Một phát hiện định tính có thể giải thích nguyên nhân của thay đổi định lượng**, còn metric giúp xem vấn đề đó phổ biến tới đâu trong tập người dùng đủ điều kiện.

### 23.8. Kết quả theo sau cần cửa sổ dài hơn

Giả sử D7 meaningful return tăng từ 40% lên 43% trong kỳ sau. Chênh lệch 3 điểm phần trăm là **tín hiệu cần nghiên cứu**, không đủ để tự khẳng định nút Học tiếp cải thiện khả năng học dài hạn. Cần xem cohort, chiến dịch nhắc học, lịch khai giảng, độ khó khóa và khoảng bất định.

Không nên giữ nguyên roadmap đồng bộ đa thiết bị chỉ vì đã định trước. Nếu phản hồi cho thấy vấn đề lớn nhất là khó chọn bài tiếp theo, nhóm cần **thương lượng lại thứ tự backlog** bằng bằng chứng.

### 23.9. Kết luận đúng mức

Một báo cáo có trách nhiệm có thể viết:

> “Trong cửa sổ thử nghiệm đã chọn, nhóm người dùng hợp lệ có cải thiện tỷ lệ mở đúng bài và trung vị thời gian tác vụ. Một vấn đề trạng thái lưu trên mobile cần xử lý trước khi mở rộng. D7 meaningful return mới có tín hiệu nhỏ, chưa đủ để quy kết nhân quả. Đề nghị sửa guardrail, kiểm tra lại trên mobile, sau đó mở rộng có kiểm soát để tiếp tục đánh giá.”

Đây là **dùng metric để quyết định**, không dùng metric để trang trí cho một quyết định đã được chốt sẵn.

## 24. Nhịp đo và nhịp ra quyết định

Không phải số đo nào cũng cần xem mỗi giờ. Nhịp kiểm tra nên theo **rủi ro, thời gian thu được bằng chứng và người có quyền hành động**.

| Nhịp / trigger | Thứ nên xem | Người phối hợp | Quyết định có thể đưa ra |
| --- | --- | --- | --- |
| **Ngay sau deploy / phát hành** | Lỗi dữ liệu, quyền, crash, tình trạng dịch vụ | Developers, vận hành, bảo mật khi cần | Dừng rollout, rollback/roll-forward, sửa sự cố |
| **Hằng ngày khi có người dùng** | Funnel cơ bản, tracking bất thường, work item age | Product/engineering/data | Điều tra event, nút thắt hoặc lỗi |
| **Theo Sprint hoặc một vòng phản hồi ngắn** | Outcome gần, phản hồi định tính, tiến triển Sprint Goal | Scrum Team và bên liên quan phù hợp | Điều chỉnh Sprint Backlog trong phạm vi mục tiêu, tinh chỉnh Product Backlog |
| **Theo cohort đủ thời gian** | D7/D30, completion, tác động tới hành vi học | Product Owner, nghiên cứu, dữ liệu | Tiếp tục/đổi hướng ưu tiên, mở rộng hay dừng |
| **Theo chu kỳ chiến lược** | Product Goal, kết quả dài hạn, chi phí và tác động | Các bên quyết định sản phẩm/tổ chức | Chọn mục tiêu mới, phân bổ năng lực, hủy giả thuyết |

### Không nhầm dashboard “real time” với khả năng ra quyết định

Retention D30 cần người dùng trải qua **đủ 30 ngày**; xem biểu đồ D30 mỗi 5 phút không làm bằng chứng đến sớm hơn. Ngược lại, sai quyền truy cập là vấn đề phải phản ứng **ngay**. Hãy ghép mỗi metric với **cửa sổ tạo bằng chứng và độ khẩn của hành động**.

### Quy trình đánh giá theo giả thuyết

~~~text
1. Mục tiêu có thay đổi thực tế và guardrails có đạt không?
2. Dữ liệu có đủ tin cậy, đủ đại diện và đủ thời gian không?
3. Độ lớn thay đổi có ý nghĩa với người dùng không?
4. Còn giải thích thay thế nào chưa kiểm chứng?
5. Cần ra quyết định gì ngay: sửa, giữ, mở rộng, thử thêm hay dừng?
6. Ai sở hữu hành động và khi nào sẽ đánh giá lại?
~~~

Hãy ghi **decision log ngắn**: giả thuyết, bằng chứng, mức bất định, hành động và điều kiện xem lại. Không cần biến nó thành thủ tục nặng cho mọi thay đổi nhỏ, nhưng những quyết định đầu tư lớn cần có dấu vết học hỏi.

## 25. Kết hợp đo giá trị với Scrum, Kanban và XP

### Scrum: đo để kiểm tra và thích ứng, không thay Sprint Goal

Một Scrum Team có thể bắt đầu Sprint Planning bằng câu hỏi:

> “Trong Sprint này, chúng ta có thể tạo Increment nào giúp học viên tiếp tục đúng bài, và bằng chứng sớm nào cho biết cách tiếp cận có ích?”

Developers tạo Increment đạt **Definition of Done**, có telemetry phù hợp khi cần. Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm, sắp xếp Product Backlog và cùng các bên liên quan học từ outcome. Sprint Review giúp kiểm tra sản phẩm và điều chỉnh hướng; **không phải đợi Sprint Review mới được phát hành một Increment đạt chuẩn**.

Các số đo outcome giúp làm rõ **hướng sản phẩm**, còn Sprint Goal giúp phối hợp các công việc trong một Sprint. Không biến Sprint Goal thành “tăng conversion 20% chắc chắn trong hai tuần” khi outcome cần thời gian dài hoặc phụ thuộc hành vi bên ngoài chưa thể kiểm chứng.

### Kanban: quản lý dòng học hỏi và đưa giả thuyết tới bằng chứng

Một workflow có thể gồm:

~~~text
Giả thuyết cần kiểm tra
    → Ready
    → Thiết kế phép thử / làm lát cắt
    → Kiểm chứng kỹ thuật
    → Exposure an toàn
    → Đo / đánh giá
    → Quyết định
~~~

Đây là workflow minh họa, không phải bộ cột Kanban bắt buộc. Nhóm có thể quản lý **WIP, throughput, cycle time và work item age** để tránh bắt đầu quá nhiều thử nghiệm nhưng không kết thúc được vòng học. **Khép vòng học** có ý nghĩa hơn chỉ chuyển thẻ “Đã làm tính năng” sang Done khi chưa ai xem phản hồi.

### XP: năng lực kỹ thuật để thay đổi giả thuyết nhanh và an toàn

Các thực hành **TDD, CI, refactoring, pair programming, simple design và small releases** giúp một giả thuyết mới được đưa thành phần mềm đáng tin với chi phí thay đổi thấp hơn. Kiểm thử chấp nhận bảo vệ quy tắc đã hiểu; kiểm thử khám phá giúp tìm khoảng trống. **Tự động hóa giao hàng không chứng minh giá trị**, nhưng giúp rút ngắn thời gian từ ý tưởng tới bằng chứng.

### Ba loại câu hỏi bổ trợ

| Câu hỏi | Thực hành hữu ích | Ví dụ |
| --- | --- | --- |
| **Ta đang giải quyết đúng vấn đề?** | Nghiên cứu người dùng, Product Goal, outcome metrics | Người học có thật sự khó tìm bài không? |
| **Ta có thể giao thay đổi an toàn?** | XP, Definition of Done, CI, testing, rollout | Nút Học tiếp có bảo vệ checkpoint và quyền? |
| **Ta có thể học và thay đổi đủ nhanh?** | Scrum feedback events, Kanban flow, metrics, cohort review | Bao lâu từ giả thuyết tới dữ liệu đáng tin để quyết định? |

## 26. Những phản mẫu phổ biến khi đo giá trị

### 26.1. “Velocity tăng nghĩa là giá trị tăng”

Story points là ước lượng nội bộ, không phải đơn vị giá trị khách hàng. **Cải thiện:** xem outcome người dùng song song với khả năng giao việc; không so sánh velocity giữa nhóm để xếp hạng.

### 26.2. “Ra mắt 10 features là đã hoàn thành Product Goal”

Số features là output. **Cải thiện:** xác nhận người dùng có sử dụng, hoàn thành tác vụ và nhận lợi ích đáng tin không.

### 26.3. “Mục tiêu là tăng engagement càng nhiều càng tốt”

Thời gian trong app có thể tăng do khó tìm chức năng hoặc thiết kế gây phụ thuộc. **Cải thiện:** xác định **hoạt động học có ý nghĩa** và các guardrails về trải nghiệm.

### 26.4. “Đã lên target thì phải đạt bằng mọi cách”

Khi thưởng/phạt theo metric, nhóm có thể thay denominator, chọn mẫu hoặc hạ chất lượng. **Cải thiện:** minh bạch định nghĩa, kiểm tra tác động và giữ mục tiêu học hỏi.

### 26.5. “Tăng 10% và tăng 10 điểm phần trăm giống nhau”

Hai phép đo khác nhau. **Cải thiện:** báo baseline, target và cách tính tăng tương đối/tuyệt đối.

### 26.6. “Dashboard xanh tức là mọi nhóm người dùng đều tốt”

Metric tổng che vấn đề theo thiết bị hoặc cohort. **Cải thiện:** xem phân khúc và phân bố, đặc biệt nhóm có khả năng gặp rào cản tiếp cận.

### 26.7. “Có tương quan thì chắc là tính năng gây ra”

Seasonality, marketing hoặc thay đổi mẫu có thể giải thích. **Cải thiện:** thử nghiệm có đối chứng khi phù hợp, hoặc before/after có kiểm soát và ghi giới hạn.

### 26.8. “Chỉ lấy dữ liệu những người đã hoàn thành”

Lấy người đã thành công làm denominator sẽ thổi phồng task success. **Cải thiện:** thu đủ những người/tác vụ **có cơ hội thất bại** theo quy tắc đã định.

### 26.9. “D7 của cohort mới chưa qua 7 ngày vẫn tính bình thường”

Cohort chưa đủ thời gian tạo **right censoring** và làm sai tỷ lệ. **Cải thiện:** chỉ báo cáo cohort đủ cửa sổ hoặc dùng phương pháp xử lý dữ liệu chưa quan sát được phù hợp.

### 26.10. “Một p-value đẹp là kết luận”

Chạy thử nhiều metric, nhiều lần nhìn giữa chừng hoặc sample quá nhỏ có thể gây sai lầm. **Cải thiện:** xác định metric, ngưỡng và phương pháp trước; xem khoảng bất định, ý nghĩa thực và guardrails.

### 26.11. “Chúng ta cần thu mọi dữ liệu người học để tối ưu”

Thu quá mức gây rủi ro và có thể không giúp câu hỏi sản phẩm. **Cải thiện:** data minimization, mục đích rõ, quyền truy cập, retention policy, kiểm tra riêng tư.

### 26.12. “Không có lỗi được báo nghĩa là không có lỗi”

Người dùng có thể không phát hiện hoặc không có kênh báo. **Cải thiện:** automated tests, exploratory testing, monitoring và xem độ nhạy của hệ thống phát hiện.

### 26.13. “Cứ tăng tỷ lệ hoàn thành bằng cách cho qua bài dễ hơn”

Metric được tối ưu trong khi năng lực thật giảm. **Cải thiện:** giữ chuẩn đánh giá và đối chiếu với kết quả học đáng tin.

### 26.14. “Mọi sản phẩm phải dùng chung một North Star”

Một số sản phẩm đa nhóm người dùng hoặc nhiều nghĩa vụ không thể tóm trong một con số. **Cải thiện:** chọn metric phục vụ câu hỏi sản phẩm và nhóm guardrails, không ép theo mẫu.

### 26.15. “Đo xong mà không đổi gì vẫn là data-driven”

Thu dữ liệu nhiều nhưng roadmap không thay đổi tức là vòng phản hồi chưa hoàn chỉnh. **Cải thiện:** mỗi lần review quan trọng phải có quyết định và người chịu trách nhiệm.

### 26.16. “Chỉ xem metric cuối tháng”

Một sự cố dữ liệu có thể gây hại ngay. **Cải thiện:** tách nhịp cảnh báo an toàn theo thời gian phù hợp khỏi nhịp đo outcome dài hạn.

## 27. Workshop 75 phút: thiết kế mục tiêu và bằng chứng

Đây là **bài thực hành gợi ý**, không phải một sự kiện bắt buộc của Scrum, Kanban hoặc XP.

| Bước | Thời lượng | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Chọn vấn đề** | 10 phút | Người hiểu sản phẩm nêu người dùng và công việc khó khăn | Problem statement có bằng chứng ban đầu |
| **2. Viết giả thuyết** | 10 phút | Nêu cơ chế từ giải pháp tới outcome | Hypothesis và những giả định có thể sai |
| **3. Chọn metric** | 15 phút | Xác định numerator, denominator, đơn vị, event, cửa sổ | Metric contract |
| **4. Baseline/target** | 10 phút | Xem dữ liệu hiện có hoặc nêu kế hoạch đo baseline | Mốc hiện tại, ngưỡng có ý nghĩa hoặc mục cần xác minh |
| **5. Guardrails** | 10 phút | Xác định chất lượng, an toàn và tác dụng phụ | Ngưỡng dừng, tests/monitoring cần có |
| **6. Kế hoạch học** | 10 phút | Chọn rollout/thử nghiệm/quan sát người dùng | Cửa sổ bằng chứng, owner, hạn chế nhân quả |
| **7. Quyết định** | 10 phút | Giả lập kết quả tốt/xấu/mơ hồ | Continue/change/stop/learn-more rules |

**Tình huống:** “Người học có bài đang dở không muốn lục tìm thủ công. Nhóm dự định thêm nút Học tiếp.”

Nhóm thực hành cần trả lời:

1. Nếu người học không có bài dở, họ có thuộc denominator không?
2. Một người bấm ba lần được tính ba người hay một người?
3. Định nghĩa “mở đúng bài” dựa vào đâu và bao lâu là có ý nghĩa?
4. Có thể tăng click nhưng tăng lỗi checkpoint không?
5. Nếu retention chưa đủ cửa sổ, có kết luận gì ngay từ task-success?
6. Bằng chứng nào khiến nhóm không xây tiếp một trang tiến độ phức tạp?
7. Ai được quyết định đổi thứ tự Product Backlog và điều kiện nào bảo vệ Done?

**Tiêu chí đạt:** không phải tạo nhiều metrics nhất, mà **định nghĩa được một giả thuyết có thể bác bỏ, bằng chứng tin cậy, guardrails và hành động sau khi học**.

## 28. Bài tập tính toán và diễn giải

### Bài tập A — Output, outcome hay impact?

Phân loại và giải thích:

1. “Deploy tính năng Học tiếp cho 10% người dùng.”
2. “Thời gian mở đúng bài giảm từ median 95 xuống 55 giây.”
3. “Số học viên hoàn thành chuẩn năng lực trong học kỳ tăng.”
4. “Developers đóng được 20 ticket.”
5. “Một nhóm học viên xác nhận nút mới giúp họ quay lại bài dễ hơn.”

**Gợi ý:** (1) là delivery/exposure, (4) là output; (2) và (5) là bằng chứng outcome ở mức khác nhau; (3) gần impact về kết quả học nhưng cần kiểm tra cách đo và nguyên nhân.

### Bài tập B — Tính task-success rate

Có 300 lượt tác vụ được ghi. Trong đó 40 lượt thuộc tài khoản thử, 20 lượt thuộc người không có bài đang dở (không đủ điều kiện), và có 180 lượt hợp lệ mở đúng bài trong 60 giây.

1. Denominator hợp lệ là bao nhiêu?
2. Tỷ lệ thành công là bao nhiêu?
3. Vì sao chưa được kết luận “75% học viên thành công”?

**Gợi ý:** Denominator = \(300-40-20=240\); tỷ lệ = \(180/240=75\%\). Đơn vị là **lượt**, không phải người; cần xét người lặp và độ tin cậy tracking.

### Bài tập C — Điểm phần trăm và tăng tương đối

Conversion tăng từ 25% lên 30%.

- Tăng bao nhiêu **điểm phần trăm**?
- Tăng bao nhiêu **phần trăm tương đối**?
- Khi báo cáo cho Product Owner, câu nào tránh hiểu nhầm?

**Gợi ý:** 5 điểm phần trăm và 20% tương đối. Viết “từ 25% lên 30%, tăng 5 điểm phần trăm (20% tương đối)”.

### Bài tập D — Đọc funnel

Có 800 tác vụ đủ điều kiện; 640 lượt thấy nút, 480 lượt nhấn, 432 lượt mở đúng bài.

1. Tỷ lệ thấy nút so với đầu funnel?
2. Tỷ lệ nhấn sau khi thấy?
3. Tỷ lệ mở đúng bài sau khi nhấn?
4. Tỷ lệ mở đúng bài từ đầu funnel?
5. Có thể kết luận nguyên nhân rơi rụng ở bước nào chỉ từ bảng này không?

**Gợi ý:** 80%, 75%, 90%, 54%; bảng cho biết bước giảm chứ chưa xác định nguyên nhân.

### Bài tập E — Cohort retention

Tuần W có 500 học viên mới, nhưng mới 100 người đã đi qua đủ cửa sổ D7. Trong 100 người đó có 42 người quay lại làm một hoạt động học có nghĩa.

1. Vì sao không được tính \(42/500\) như D7 retention hoàn chỉnh?
2. Với tập đã đủ cửa sổ, tỷ lệ là bao nhiêu?
3. Hạn chế của kết quả trên là gì?

**Gợi ý:** Chỉ 100 người có đủ thời gian, nên tỷ lệ mô tả là **42%** trên nhóm đã trưởng thành; nếu thời điểm tham gia có tương quan khác biệt, cần kiểm tra cách chia cohort/cửa sổ.

### Bài tập F — Guardrail bị vi phạm

Một thử nghiệm báo tỷ lệ mở bài nhanh tăng 15 điểm phần trăm, nhưng canary ghi nhận một số tài khoản có thể đọc checkpoint của tài khoản khác.

1. Có được tiếp tục mở rộng chỉ vì primary metric tốt không?
2. Ai cần phối hợp và kiểm tra gì?
3. Có thể kết luận lỗi được giải quyết sau khi rollback code không?

**Gợi ý:** Không. Phải dừng/giới hạn rollout theo chính sách, xử lý quyền và dữ liệu, xác minh tác động; rollback code không tự xử lý mọi dữ liệu đã bị ảnh hưởng.

### Bài tập G — Tương quan với nhân quả

Sau khi ra nút Học tiếp, D7 retention tăng 5 điểm phần trăm. Cùng lúc trường tổ chức chiến dịch nhắc học và các khóa học đầu năm học bắt đầu.

Đề xuất **ba giải thích khác** và **hai cách kiểm chứng tiếp**. Nêu phát biểu kết luận trung thực trước khi có kết quả tiếp theo.

**Gợi ý:** Mùa vụ, chiến dịch, thành phần cohort, tracking thay đổi; có thể dùng thiết kế thí nghiệm có kiểm soát khi phù hợp và phân tích cohort/trend có cấu trúc, kèm quan sát người học.

### Bài tập H — Kết hợp với Scrum và Kanban

Scrum Team đã đạt Sprint Goal về Increment Học tiếp; Kanban board nội bộ cho thấy nhiều thay đổi còn chờ deploy. Product Owner muốn biết nhóm đã đạt Product Goal hay chưa.

Hãy tách ba nhóm thông tin:

1. **Increment/Done và khả năng phát hành**.
2. **Flow kỹ thuật** (WIP, age, cycle time, hàng đợi deploy).
3. **Outcome người học** và cửa sổ cần đo.

Giải thích vì sao Sprint Goal đạt không tự chứng minh Product Goal dài hạn đã hoàn thành.

## 29. Checklist kiểm tra một mục tiêu giá trị

- [ ] Mục tiêu mô tả **người dùng hoặc đối tượng nhận giá trị**, không chỉ nhóm tính năng.
- [ ] Có một **vấn đề hoặc cơ hội cụ thể** được hỗ trợ bằng bằng chứng ban đầu.
- [ ] Phân biệt **activity, output, outcome và impact** trong báo cáo.
- [ ] Giả thuyết nêu **cơ chế tại sao** một thay đổi có thể cải thiện kết quả.
- [ ] Mục tiêu có **outcome có thể quan sát**, không chỉ hoàn tất tính năng.
- [ ] Metric có **numerator/denominator, đơn vị, population, event và time window** rõ.
- [ ] Có baseline thật hoặc kế hoạch đo baseline được ghi rõ.
- [ ] Target có lý do và thời hạn, không phải số tròn tùy tiện.
- [ ] Có **guardrails về chất lượng, dữ liệu, bảo mật và tác dụng phụ**.
- [ ] Đơn vị lượt tác vụ, phiên và người dùng **không bị trộn**.
- [ ] Cohort đã đi qua đủ cửa sổ retention trước khi tính.
- [ ] Có phân khúc thích hợp, xem cả phân bố và nhóm trải nghiệm xấu.
- [ ] Tracking có kiểm tra missing/duplicate events, phiên bản schema và sai lệch thời gian.
- [ ] Các sự kiện và dữ liệu người dùng được thu thập tối thiểu, bảo vệ quyền riêng tư.
- [ ] Chỉ số leading không được tự xem là impact cuối cùng.
- [ ] Kết quả định lượng được đối chiếu với phản hồi định tính khi cần.
- [ ] So sánh trước/sau có chú thích thay đổi về mùa vụ, marketing, cohort và môi trường.
- [ ] Khi dùng A/B test, đã làm rõ randomization, exposure, guardrails và độ bất định.
- [ ] Không dùng p-value hay số mẫu nhỏ như bằng chứng chắc chắn tuyệt đối.
- [ ] Số đo flow/velocity/deploy không thay thế outcome sản phẩm.
- [ ] Nếu dùng Scrum, Product Goal, Sprint Goal và Definition of Done được giữ đúng nghĩa.
- [ ] Nếu dùng Kanban, flow metrics hỗ trợ khả năng học hỏi thay vì mục tiêu đóng thật nhiều thẻ.
- [ ] Các kỹ thuật XP giúp triển khai an toàn để kiểm chứng giả thuyết nhanh hơn.
- [ ] Kết quả đo dẫn đến **quyết định cụ thể**: giữ, sửa, mở rộng, tìm hiểu thêm hoặc dừng.
- [ ] Có owner, mốc xem lại và giả định cần được kiểm chứng tiếp.
- [ ] Không dùng một metric làm công cụ thưởng/phạt dẫn tới thao túng hành vi.

## 30. Mẫu báo cáo một trang để ra quyết định

~~~text
PRODUCT GOAL:
  [Trạng thái tương lai mong muốn của sản phẩm]

HYPOTHESIS:
  [Đối tượng] đang gặp [vấn đề].
  Nếu [lát cắt/giải pháp] thì [outcome] sẽ thay đổi vì [cơ chế].

PRIMARY METRIC:
  [Tên, định nghĩa vận hành, đơn vị, population, cửa sổ]

BASELINE / TARGET:
  [Số liệu có căn cứ + lý do chọn ngưỡng]

QUALITY GUARDRAILS:
  [Dữ liệu, quyền, ổn định, khả dụng, trải nghiệm]

EVIDENCE:
  [Giá trị quan sát, denominator, cohort, segments,
   độ tin cậy dữ liệu, định tính và giới hạn nhân quả]

DECISION:
  [Tiếp tục / đổi / dừng / thử thêm] + lý do

NEXT ACTION:
  [Owner, việc cần làm, thời điểm đánh giá lại]
~~~

### Một bảng điều hành minh họa

| Thông tin | Kỳ trước | Kỳ hiện tại | Trạng thái diễn giải |
| --- | ---: | ---: | --- |
| Task success 60s | 50% | 70% | Tín hiệu tốt, cần bảo đảm cùng population và phân tích nhân quả |
| Median time-to-resume | 92 giây | 49 giây | Ít ma sát hơn trong mẫu đã đo |
| Mobile task success | 42% | 58% | Có tiến bộ nhưng còn thua desktop; cần điều tra |
| Lỗi checkpoint | Theo baseline riêng | Theo kỳ hiện tại | Chỉ đánh giá sau khi kiểm tra nguồn và ngưỡng rủi ro |
| D7 meaningful return | 40% | 43% | Tín hiệu nhỏ, chưa đủ để khẳng định tác động |
| WIP/flow đến release | Theo workflow thật | Theo workflow thật | Đo năng lực giao, không thay outcome |

Những số trên **không phải một báo cáo thực có dữ liệu đồng bộ**; chúng chỉ minh họa cách đặt các câu hỏi cạnh nhau. Khi triển khai thực tế phải gắn mỗi giá trị với **cùng nguồn, cửa sổ, định nghĩa và kích thước mẫu cụ thể**; không được sao chép bảng giả định này để làm báo cáo dự án.

## 31. Tài liệu đọc tiếp và tổng kết

- [Agile Manifesto](https://agilemanifesto.org/): các giá trị về phần mềm hoạt động, hợp tác, phản hồi và thích ứng với thay đổi.
- [The Scrum Guide](https://scrumguides.org/): Product Goal, Sprint Goal, Increment, Definition of Done và các sự kiện kiểm tra/thích ứng.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, cycle time, work item age và Service Level Expectation.
- [DORA](https://dora.dev/): nghiên cứu năng lực giao phần mềm, tốc độ và độ ổn định; hữu ích để phân biệt engineering metrics với product outcomes.
- Eric Ries, *The Lean Startup* (2011): build–measure–learn, giả thuyết giá trị, học hỏi đã được kiểm chứng và các quyết định thay đổi hướng.
- Teresa Torres, *Continuous Discovery Habits* (2021): cơ hội người dùng, outcome và nghiên cứu liên tục cùng đội sản phẩm.
- Jeff Patton, *User Story Mapping* (2014): phân chia lát cắt tạo giá trị và học từ phát hành tăng dần.
- Dan Olsen, *The Lean Product Playbook* (2015): product-market fit, giả thuyết, đo kết quả và phương pháp học từ người dùng.
- Ronald A. Fisher và các tài liệu hiện đại về thiết kế thí nghiệm/ngẫu nhiên: nền tảng cho việc phân biệt chênh lệch quan sát với bằng chứng nhân quả.
- [Google SRE Books](https://sre.google/books/): đo reliability, SLI/SLO, vận hành và guardrails khi thay đổi phần mềm.

**Tổng kết:** Đo giá trị sản phẩm trong Agile bắt đầu từ **vấn đề và kết quả có ích đối với con người**, không bắt đầu từ số lượng story points hay dashboard. Một mục tiêu có thể kiểm chứng cần **giả thuyết rõ, đơn vị đo và denominator đúng, baseline, target có ý nghĩa, cửa sổ đánh giá, guardrails và mức bất định được công bố trung thực**.

Các chỉ số về **flow, chất lượng kỹ thuật và tốc độ phát hành** giúp nhóm giao và học nhanh hơn; chúng không thay thế **bằng chứng người dùng được lợi**. Các phương pháp định tính, cohort, funnel, phân khúc và thử nghiệm giúp thấy những gì số tổng che giấu, nhưng phải được dùng có phương pháp và bảo vệ dữ liệu.

**Điểm cốt lõi:** **Đo để học và ra quyết định, không đo để làm đẹp thành tích.** Khi dữ liệu cho thấy giả thuyết đúng, nhóm có thể tiếp tục hoặc mở rộng an toàn. Khi giả thuyết sai hoặc bằng chứng chưa đủ, nhóm chủ động điều chỉnh Product Backlog, thử giải pháp khác hoặc dừng việc không tạo giá trị. Đó là cách đo lường giúp Agile thực sự **thích ứng bằng phản hồi sớm và cải tiến liên tục**.
