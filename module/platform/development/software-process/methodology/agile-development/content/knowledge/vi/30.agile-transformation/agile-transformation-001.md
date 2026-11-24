# Đánh giá vấn đề hiện tại trước khi lựa chọn cách thay đổi

## 1. Đừng bắt đầu chuyển đổi Agile bằng việc chọn framework

Một doanh nghiệp vận hành nền tảng học trực tuyến nhận thấy cứ mỗi lần thêm chức năng, đội phát triển phải mất nhiều tuần từ lúc Product Owner nêu nhu cầu tới khi học viên thật sự sử dụng. Lãnh đạo đề xuất: “Chúng ta sẽ chuyển đổi Agile; từ tháng sau mọi nhóm phải chạy Sprint hai tuần, có Daily Scrum và tính velocity”.

Nhưng nhóm kỹ thuật đưa ra một bức tranh khác:

- User story đôi khi bắt đầu khi quy tắc ghi danh chưa được xác nhận.
- Phần mềm đã viết xong phải chờ phê duyệt và môi trường kiểm thử chung.
- Những thay đổi về quyền học khó được kiểm tra tự động nên lỗi được phát hiện muộn.
- Product Owner nhận yêu cầu từ nhiều bên nhưng không có một thứ tự ưu tiên ổn định.
- Một số nhóm vốn phát hành nhỏ mỗi ngày; nhóm khác phải chờ API của nhà cung cấp.

Nếu áp một nhịp Sprint lên mọi đội mà không tìm hiểu những nguyên nhân ấy, tổ chức có thể **đổi tên cuộc họp và cột trên bảng**, trong khi học viên vẫn chờ lâu và lỗi vẫn lọt ra môi trường thực tế.

**Đánh giá hiện trạng trước chuyển đổi Agile** là quá trình thu thập và đối chiếu bằng chứng để hiểu **dòng tạo giá trị đang hoạt động như thế nào, vấn đề đáng giải quyết là gì, yếu tố nào góp phần tạo vấn đề và điều kiện nào giới hạn khả năng thay đổi**. Kết quả của nó không phải danh sách các thực hành “chưa đủ Agile”, mà là **những quyết định cải tiến có căn cứ**.

Trong module **AGILE_DEVELOPMENT**, mục đích là vận dụng các giá trị Agile để thích ứng qua phản hồi sớm, giao Increment tăng dần và cải tiến liên tục. User story, backlog, Scrum, Kanban, XP và chỉ số dòng công việc là **phương tiện**; việc chọn phương tiện phải xuất phát từ **vấn đề sản phẩm và hệ thống delivery đang cần giải quyết**.

> **Nguyên tắc cốt lõi:** Đừng hỏi trước “Chúng ta nên áp dụng Scrum hay Kanban?”. Hãy hỏi “Người dùng đang chờ giá trị ở đâu, chất lượng bị đe dọa vì sao, quyết định nào đến muộn và đâu là thay đổi nhỏ có thể kiểm chứng?”.

## 2. Phân biệt chuyển đổi Agile, áp dụng thực hành và cải tiến kết quả

**Agile transformation** thường chỉ những thay đổi ở cách tổ chức định hướng sản phẩm, làm việc, phân quyền, phối hợp, vận hành kỹ thuật và học hỏi nhằm tăng khả năng tạo giá trị trong điều kiện bất định. Đây không phải một danh hiệu đạt được sau khóa đào tạo hoặc sau khi đổi tên chức danh.

| Khía cạnh | Ví dụ hoạt động | Điều cần xem xét |
| --- | --- | --- |
| **Áp dụng nghi thức** | Tổ chức Daily Scrum, Sprint Planning, Retrospective | Những sự kiện có giúp minh bạch, kiểm tra và thích ứng không? |
| **Đổi cấu trúc tổ chức** | Lập các nhóm sản phẩm liên chức năng | Nhóm có đủ khả năng giao giá trị và quyền quyết định phù hợp không? |
| **Thay đổi delivery** | Tích hợp thường xuyên, chia lát nhỏ, thử nghiệm sớm | Lead time, lỗi và khả năng phát hành có cải thiện không? |
| **Thay đổi quản trị** | Trao quyền trong guardrails về dữ liệu, ngân sách và chất lượng | Quyết định có nhanh hơn mà vẫn an toàn không? |
| **Thay đổi tư duy sản phẩm** | Dùng giả thuyết outcome, phản hồi người dùng, điều chỉnh backlog | Nhóm có bớt xây những thứ không tạo giá trị không? |
| **Cải tiến liên tục** | Thử một chính sách WIP hoặc bổ sung contract test | Có bằng chứng vấn đề thực tế giảm và chất lượng được giữ không? |

Một nhóm có thể đang làm việc thích ứng tốt dù chưa dùng nhãn Scrum. Ngược lại, một nhóm có đầy đủ sự kiện Scrum nhưng vẫn phải đợi ba cấp phê duyệt cho mỗi thay đổi nhỏ có thể chưa giải quyết được **nút thắt quan trọng nhất**.

### Tránh đặt “trở nên Agile” thành một kết quả mơ hồ

“Đạt 90% mức trưởng thành Agile” không tự mô tả giá trị với học viên hoặc năng lực sản phẩm. Nếu dùng một mô hình đánh giá, phải giải thích **nó đánh giá điều gì và vì sao liên quan tới vấn đề**. Đừng coi điểm từ checklist là sự thật khách quan về hiệu quả tổ chức.

Một mục tiêu rõ hơn có thể là: **giảm thời gian từ nhu cầu đã được chấp nhận tới khi người học dùng được, đồng thời không tăng lỗi phân quyền và không làm kiệt sức nhóm**.

## 3. Từ triệu chứng đến cơ chế và giả thuyết nguyên nhân

Điều đầu tiên được nghe trong buổi khảo sát thường là **triệu chứng**. Không nên biến câu nói đầu tiên thành “nguyên nhân gốc” rồi mua công cụ hoặc tái cấu trúc tổ chức.

| Triệu chứng | Những cơ chế có thể góp phần | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| “Delivery luôn chậm” | Quá nhiều WIP, phụ thuộc API, phê duyệt nối tiếp, yêu cầu thay đổi muộn | Timestamp theo các bước, blocker, bản ghi quyết định |
| “Developers ước lượng sai” | Work quá lớn, scope chưa rõ, hàng đợi test hoặc biến động ưu tiên | Chênh lệch phạm vi, cycle-time distribution, nhu cầu làm lại |
| “QA tìm lỗi quá muộn” | Thiếu ví dụ nghiệp vụ, thiếu test đa tầng, môi trường kém ổn định | Lịch sử defect, CI, acceptance criteria, test data |
| “PO đổi ý liên tục” | Chưa xác nhận nhu cầu người học, nhiều stakeholder tranh quyền, ưu tiên mơ hồ | Product Goal, nguồn yêu cầu, quyết định backlog, phản hồi |
| “Daily Scrum tốn thời gian” | Cuộc họp bị biến thành báo cáo cá nhân, board không phản ánh thực tế | Quan sát mục đích buổi họp, blocker được gỡ hay không |
| “Các nhóm ít hợp tác” | Quyền quyết định không rõ, mục tiêu cục bộ, thiếu hợp đồng API | Decision log, phụ thuộc và thời gian chờ liên nhóm |
| “Không dám báo lỗi” | Trừng phạt, xếp hạng theo KPI, thiếu kênh phản hồi | Phỏng vấn an toàn, near miss, cách xử lý incident |

### Ba tầng cần phân biệt

1. **Sự kiện quan sát được:** một story chờ review bốn ngày.
2. **Cơ chế có thể giải thích:** reviewer đang có quá nhiều công việc dở dang; thay đổi quá lớn nên khó xem.
3. **Điều kiện hệ thống:** chính sách giao nhiều PBI song song, không có quyền ưu tiên review và phụ thuộc giữa đội chưa được nhận diện.

Điều kiện ở tầng ba chỉ là **giả thuyết** cho tới khi được đối chiếu với dữ liệu, người thực hiện và ví dụ thực tế.

### Đừng tự động quy nguyên nhân cho cá nhân

Một người không phản hồi pull request ngay có thể đang xử lý sự cố production, thiếu quyền chạy môi trường hoặc bị giao quá nhiều việc. Câu “reviewer thiếu trách nhiệm” ít giúp lựa chọn cách thay đổi hơn câu “hàng đợi review không có WIP limit và không có người thay thế khi reviewer trực incident”.

## 4. Xác định mục đích và phạm vi của đánh giá hiện trạng

Trước khi phỏng vấn hay lập dashboard, cần nêu **quyết định mà cuộc đánh giá sẽ hỗ trợ**. Đánh giá vô thời hạn dễ trở thành một dự án tư vấn lớn mà không đưa ra thay đổi nào.

### Một tuyên bố phạm vi mẫu

~~~text
Vấn đề cần hiểu:
  Học viên chờ quá lâu từ lúc nhu cầu cải tiến được chấp nhận
  đến lúc có thể sử dụng.

Phạm vi:
  Dòng delivery các user story tiêu chuẩn cho trải nghiệm học
  từ tiếp nhận nhu cầu tới availability của cohort mục tiêu.

Không nằm trong phạm vi đầu tiên:
  Toàn bộ hệ thống kế toán, hoạt động tuyển dụng, mọi loại incident.

Người cần tham gia:
  Product Owner, Developers, tester, vận hành, hỗ trợ người học,
  đại diện stakeholder và người có thẩm quyền về ràng buộc dữ liệu.

Câu hỏi ra quyết định:
  Nút nghẽn lớn nhất nằm ở làm rõ nhu cầu, WIP, kiểm thử,
  phối hợp, phát hành hay giới hạn tổ chức?

Bằng chứng cần có:
  Sơ đồ dòng giá trị, mẫu hạng mục thực tế, số liệu thời gian,
  lỗi/chất lượng và phản hồi từ người làm lẫn người học.

Kết quả mong đợi:
  Một số giả thuyết ưu tiên, rủi ro, thử nghiệm nhỏ và mốc đánh giá.
~~~

### Giữ phạm vi vừa đủ để có thể hành động

Đừng bắt đầu bằng tuyên bố “đánh giá tất cả phòng ban và mọi quá trình trong sáu tháng” nếu vấn đề ưu tiên là **thời gian chờ xác nhận quyền học**. Có thể chọn **một luồng giá trị đủ đại diện**, học được điều gì hiệu quả rồi mở rộng khi có căn cứ.

### Không thu thập những gì không cần

Không nhất thiết phải đọc toàn bộ lịch sử tin nhắn cá nhân, chấm từng Developer hay lấy hồ sơ người dùng thật. Ưu tiên **bản ghi công việc đã được phép truy cập, dữ liệu tổng hợp, quan sát cuộc họp và phỏng vấn có phạm vi**.

## 5. Bắt đầu từ người nhận giá trị và nhu cầu thực sự

Nếu chỉ hỏi các phòng ban về hiệu suất nội bộ, nhóm có thể bỏ quên **người dùng đang chờ và kết quả mà họ quan tâm**.

### Những câu hỏi khám phá

- Người dùng nào chịu tác động: học viên, giảng viên, quản trị khóa hay bộ phận hỗ trợ?
- Họ đang cố hoàn thành **hành trình** gì, tại thời điểm nào?
- Vấn đề nào quan trọng với họ: không tìm được bài, không đăng nhập, trạng thái đăng ký khó hiểu hay chậm phản hồi?
- Có bằng chứng nào về mức độ phổ biến và hậu quả?
- Tổ chức đang quyết định dựa trên phản hồi sớm hay chỉ phản hồi sau đợt phát hành lớn?
- Nếu delivery nhanh hơn nhưng hành trình vẫn sai quyền hoặc khó dùng, kết quả có chấp nhận được không?

### Ví dụ làm rõ nhu cầu

Stakeholder đề nghị “thêm nút AI gợi ý học tiếp”, nhưng phỏng vấn học viên cho thấy nhiều người chỉ cần **mở đúng bài chưa hoàn thành**. Nhóm có thể xác định **cơ hội sản phẩm** là “giảm số lần người học phải tự tìm bài”, thay vì mặc định dự án phải dùng AI.

Điều này giúp tránh một kiểu chuyển đổi hình thức khác: Scrum Team giao nhiều Increment nhỏ nhưng **đều phục vụ một giả định chưa được xác minh**.

### Phân biệt nhu cầu, giải pháp và outcome

| Tầng | Ví dụ | Cần kiểm chứng |
| --- | --- | --- |
| **Nhu cầu/ngữ cảnh** | Học viên trở lại sau nhiều ngày, không nhớ bài tiếp theo | Phỏng vấn, quan sát hành trình, phản hồi hỗ trợ |
| **Giả thuyết giải pháp** | Một nút “Tiếp tục học” có thể giúp | Thử nghiệm có phạm vi, tiêu chí chấp nhận |
| **Output** | API và UI được giao, đạt DoD | Kiểm thử kỹ thuật và acceptance |
| **Outcome** | Học viên đủ điều kiện mở đúng bài nhanh hơn | Dữ liệu hành vi có định nghĩa, phản hồi người dùng |
| **Guardrail** | Người chưa ACTIVE không được xem nội dung hạn chế | Security/API tests, vận hành, xử lý lỗi |

Khi đánh giá hiện trạng, nên đo cả **dòng tạo giá trị và khả năng nhận biết giá trị có xuất hiện hay không**.

## 6. Chọn đơn vị phân tích: dòng giá trị end-to-end

Một tổ chức thường chia công việc theo phòng ban: sản phẩm, UX, backend, frontend, QA, bảo mật, vận hành. Nhưng người học chỉ quan tâm **tính năng dùng được**. Bởi vậy, cần xem **value stream (dòng giá trị)** đi xuyên các nhóm.

### Sơ đồ hiện trạng minh họa

~~~mermaid
flowchart LR
    A["Phản hồi học viên"] --> B["Tiếp nhận / phân loại"]
    B --> C["Làm rõ nhu cầu"]
    C --> D["Chờ quyết định ưu tiên"]
    D --> E["Thiết kế và phát triển"]
    E --> F["Review / tích hợp"]
    F --> G["Kiểm thử và sửa"]
    G --> H["Chờ release / approval"]
    H --> I["Học viên có thể dùng"]
    I --> J["Đo kết quả / nhận phản hồi"]
    G -. "Thiếu yêu cầu" .-> C
    F -. "Hợp đồng chưa thống nhất" .-> E
~~~

Đây là **giả định quy trình cần xác minh**, không phải sơ đồ được tạo bằng cách chép SOP. Hãy theo **một vài user story thật** để thấy chúng đã đi qua những bước nào, quay lại bao nhiêu lần, chờ ai quyết và bị chặn vì đâu.

### Các ranh giới cần ghi rõ

- **Điểm bắt đầu:** yêu cầu được gửi, được tiếp nhận hợp lệ, được cam kết hay bắt đầu làm?
- **Điểm kết thúc:** code xong, đạt Definition of Done, deploy lên production hay học viên mục tiêu có thể dùng?
- **Đơn vị công việc:** user story, PBI, bug, incident hay task kỹ thuật?
- **Nhóm người dùng:** tất cả hay một cohort được bật feature flag?
- **Khoảng quan sát:** dữ liệu mấy tuần, có kỳ nghỉ, sự cố đặc biệt hoặc đợt khai giảng không?

Nếu ranh giới không rõ, cuộc tranh luận “chúng ta làm nhanh hay chậm” sẽ thiếu cơ sở.

### Đừng coi task kỹ thuật là toàn bộ giá trị

Một UI task được đánh Done trong hai ngày không có nghĩa người học có thể dùng hành trình, nếu API và kiểm tra quyền vẫn chưa đạt DoD. Đánh giá end-to-end nên gắn với **lát có ý nghĩa cho người dùng**, không chỉ số task của từng phòng.

## 7. Value Stream Mapping: nhìn cả thời gian xử lý lẫn thời gian chờ

**Value Stream Mapping (VSM)** giúp mô tả các bước tạo giá trị, bàn giao và chờ đợi. Đừng chỉ ghi sơ đồ lý tưởng trên giấy; hãy dùng timestamp, lịch sử ticket, trao đổi với người thực hiện và một số ví dụ thực tế.

### Một bảng thời gian minh họa

Giả sử một nhóm theo dõi một dòng từ **request accepted tới available**, đo theo **ngày lịch**. Để minh họa, các khoảng dưới đây **không chồng lấp** và cộng được thành một hành trình:

| Đoạn công việc | Thời gian làm trực tiếp | Thời gian chờ | Tổng thời gian |
| --- | ---: | ---: | ---: |
| Tiếp nhận và làm rõ ban đầu | 0,5 ngày | 1,5 ngày | 2 ngày |
| Refinement và xác nhận nghiệp vụ | 1 ngày | 2 ngày | 3 ngày |
| Chờ ưu tiên/năng lực thực hiện | 0 ngày | 5 ngày | 5 ngày |
| Phát triển | 2 ngày | 2 ngày | 4 ngày |
| Review và kiểm thử tích hợp | 1,5 ngày | 4,5 ngày | 6 ngày |
| Chờ phát hành và bật cho cohort | 0,5 ngày | 2,5 ngày | 3 ngày |
| **Tổng** | **5,5 ngày** | **17,5 ngày** | **23 ngày** |

~~~text
Tổng lead time minh họa = 23 ngày lịch
Tổng thời gian làm trực tiếp = 5,5 ngày
Tổng thời gian chờ = 17,5 ngày
Tỷ trọng thời gian chờ = 17,5 / 23 × 100% ≈ 76,1%
~~~

**76,1% không có nghĩa mọi thời gian chờ đều là lãng phí hoặc có thể xóa.** Một số phê duyệt an toàn hoặc đợt kiểm tra bắt buộc có giá trị. Cần hỏi **chờ vì sao, có thể làm sớm/song song/chuẩn hóa hay không, và việc rút ngắn có tạo rủi ro gì**.

### Tại sao không tối ưu ngay bước viết code?

Giảm thời gian phát triển từ hai ngày xuống một ngày sẽ giúp ít hơn việc xử lý một hàng đợi review kéo dài nhiều ngày, nếu hàng đợi đó là nút nghẽn chính. Nhưng cũng không được mặc định hàng đợi dài là lỗi của người review: có thể PR quá lớn, môi trường kém ổn định hoặc thiếu chính sách ưu tiên.

### Hỏi người trực tiếp làm việc

Sơ đồ dữ liệu có thể nói “Review: 6 ngày” nhưng người thực hiện biết trong đó có **ba ngày chờ môi trường, một ngày chờ người nghiệp vụ xác nhận và hai ngày xử lý kỹ thuật**. Đối chiếu **dữ liệu định lượng và câu chuyện thật** giúp chọn can thiệp đúng.

## 8. Đo lead time, cycle time, WIP và work item age đúng phạm vi

Chuyển đổi Agile thường dùng các chỉ số flow, nhưng **chỉ số không tự chẩn đoán nguyên nhân**. Mọi phép đo cần định nghĩa và được đọc trong bối cảnh.

| Chỉ số | Một cách định nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Request lead time** | Yêu cầu được tiếp nhận hợp lệ → khả năng tới người dùng mục tiêu | Người yêu cầu phải chờ bao lâu? |
| **Commitment lead time** | Nhóm chấp nhận thực hiện → kết quả được giao | Sau khi cam kết, hệ thống mất bao lâu? |
| **Cycle time** | Bắt đầu thực hiện → Done được xác định rõ | Công việc đã bắt đầu đi tới hoàn tất nhanh đến đâu? |
| **Work item age** | Bắt đầu theo ranh giới đã chọn → thời điểm hiện tại, với item chưa xong | Hạng mục nào đang già và có nguy cơ kẹt? |
| **WIP** | Số item đang trong phạm vi công việc dở dang đã định nghĩa | Hệ thống có bắt đầu quá nhiều việc không? |
| **Throughput** | Số item hoàn tất theo định nghĩa mỗi khoảng | Hệ thống đang hoàn thành bao nhiêu item? |
| **Blocked time** | Tổng thời gian chờ do điều kiện cản trở đã ghi nhận | Phụ thuộc nào gây chờ đáng chú ý? |
| **Flow distribution/P85** | Phân phối thời gian của các item cùng loại đã xong | Có đuôi kéo dài; độ tin cậy của thời gian phục vụ ra sao? |

### Ví dụ đọc phân phối thay vì chỉ trung bình

Mười hai user story cùng loại có thời gian từ **commitment tới availability** theo ngày lịch:

~~~text
4, 5, 6, 7, 7, 9, 11, 12, 14, 17, 21, 32

Tổng = 145 ngày
Mean = 145 / 12 ≈ 12,1 ngày
Median = (9 + 11) / 2 = 10 ngày
P85 theo nearest-rank:
  ceil(0,85 × 12) = 11
  Quan sát thứ 11 = 21 ngày
~~~

Một story kéo dài **32 ngày** làm trung bình cao hơn trung vị. Không nên nói “story mới chắc chắn xong trong 12 ngày”. Mười hai mẫu còn quá ít để xây một dự báo chắc chắn, đặc biệt khi loại việc và nhu cầu thay đổi.

### Đừng bỏ các item đang mắc kẹt

Nếu dashboard chỉ tính story đã Done, các story kẹt ở Review/Test trong ba tuần **không xuất hiện trong biểu đồ cycle time hoàn tất**. Cần nhìn **Work Item Age** của việc đang mở và những yêu cầu chưa được quyết định.

### Little's Law chỉ dùng khi ranh giới nhất quán

~~~text
Average WIP ≈ Average throughput × Average time in system
~~~

Ví dụ, trong một luồng ổn định có WIP trung bình 9 item và throughput 3 item/tuần, thời gian trung bình **trong chính luồng đó** xấp xỉ 3 tuần. Không được lấy WIP từ **In Progress tới Done** rồi tuyên bố đã đo thời gian từ **lúc học viên gửi yêu cầu tới production**.

Những chỉ số flow cần được xem cùng **chất lượng, nhu cầu và năng lực**, không dùng để xếp hạng từng Developer hoặc tăng velocity bằng cách nâng story points.

## 9. Đánh giá chất lượng và năng lực phản hồi kỹ thuật

Một tổ chức có thể chuyển PBI sang Done nhanh nhưng lỗi quyền, dữ liệu và khả năng khôi phục vẫn không đáng tin. Vì vậy, **chẩn đoán khả năng giao an toàn** là một phần của đánh giá hiện trạng.

### Các câu hỏi theo lớp

| Lớp | Câu hỏi | Bằng chứng gợi ý |
| --- | --- | --- |
| **Nghiệp vụ** | Acceptance criteria có các trường hợp chính, âm và biên? | User story, ví dụ ba bên/Three Amigos, bug do hiểu sai |
| **Unit/component** | Quy tắc thuần có được kiểm tra nhanh, đáng tin? | Test suite, phản hồi local, lỗi hồi quy |
| **Contract/API** | Thay đổi một bên có phá consumer khác không? | Contract tests, versioning, sự cố tương thích |
| **Integration/data** | Transaction, concurrency và migration có được bảo vệ? | Test tích hợp, lỗi dữ liệu, tình huống rollback |
| **Security/privacy** | Quyền được kiểm tra ở máy chủ và dữ liệu dùng đúng phạm vi? | API/security tests, chính sách, risk review |
| **CI/CD** | Có thể tích hợp thường xuyên và biết sớm test đỏ? | Độ trễ CI, độ flaky, thời gian fix, release logs |
| **Observability** | Production có cho biết lỗi kỹ thuật và lỗi nghiệp vụ? | Logs/metrics/traces, incident, support |
| **DoD và release** | Done có nghĩa Increment dùng được hay chỉ code complete? | Chính sách DoD, trạng thái release, bằng chứng chất lượng |

### Đếm defect cần cẩn trọng

Một incident có thể tạo nhiều báo cáo hỗ trợ; nhiều báo cáo chưa chắc là nhiều **defect duy nhất**. Số lỗi production tăng đôi khi phản ánh **phát hiện tốt hơn** sau khi cải thiện telemetry. Do đó, cần xem severity, người bị ảnh hưởng, thời gian phát hiện/khôi phục và định nghĩa cách đếm.

### Chất lượng không phải “bước cuối của QA”

Nếu quyền truy cập chỉ được kiểm tra thủ công trước release, việc thêm một vai trò QA vào cuối chuỗi chưa chắc xử lý nguyên nhân. Một giải pháp có thể là làm rõ quy tắc sớm và tự động hóa API/security tests ngay trong CI. Nhưng cần xem **rủi ro thực tế** trước khi chọn kỹ thuật.

### Không đặt chỉ tiêu coverage một cách cơ học

100% line coverage không bảo đảm test bắt được hai yêu cầu ghi danh đồng thời tạo hai bản ghi, hoặc người không có quyền xem dữ liệu của người khác. Đánh giá nên xác định **bất biến quan trọng chưa được kiểm tra**, thay vì chỉ số dòng lệnh được chạy.

## 10. Đánh giá discovery, user story và cách ra quyết định sản phẩm

Nhiều tổ chức tập trung cải thiện delivery nhưng không xem **chúng ta có đang chọn đúng vấn đề để giải quyết không**.

### Những câu hỏi cần quan sát

- Product Goal có rõ **giá trị và trạng thái tương lai của sản phẩm** không?
- Product Backlog có một thứ tự minh bạch hay mỗi stakeholder đẩy việc riêng?
- Học viên, giảng viên và hỗ trợ được tham gia phản hồi như thế nào?
- User story có đủ ví dụ để người nghiệp vụ và Developers hiểu cùng một hành vi?
- Những ý tưởng lớn có được chia thành **lát giá trị dọc có thể học hỏi** không?
- Có phân biệt **discovery** (điều gì đáng làm) với **delivery** (xây và kiểm tra) mà vẫn liên thông không?
- Khi phát hiện giả thuyết sai, Product Owner và nhóm có được điều chỉnh thứ tự backlog không?

### Ví dụ sự hiểu sai làm chậm delivery

Story ghi “Là học viên, tôi muốn ghi danh nhanh”. Developers hiểu là khi nhấn nút lập tức có quyền học. Product Owner lại nghĩ với khóa cần duyệt thì yêu cầu phải ở trạng thái **PENDING** trước khi người có thẩm quyền xác nhận **ACTIVE**.

Nếu không làm rõ sớm, nhóm có thể xây một luồng hoàn chỉnh nhưng sai nghiệp vụ. Đánh giá hiện trạng cần xem **điểm câu hỏi được phát hiện, ai có quyền trả lời và thời gian chờ quyết định**, không chỉ ước lượng code.

### Một vài ví dụ chấp nhận có thể dùng để chẩn đoán

~~~gherkin
Feature: Ghi danh khóa học cần xét duyệt

  Scenario: Học viên gửi yêu cầu ghi danh
    Given học viên đã đăng nhập và khóa yêu cầu xét duyệt
    When học viên gửi yêu cầu ghi danh hợp lệ
    Then hệ thống ghi nhận trạng thái PENDING
    And không cấp quyền truy cập nội dung bị hạn chế

  Scenario: Người đã được duyệt có quyền học
    Given học viên có đăng ký ACTIVE và đáp ứng điều kiện truy cập
    When học viên yêu cầu mở một bài học được phép
    Then hệ thống cấp nội dung theo chính sách

  Scenario: Người chưa được duyệt truy cập trực tiếp
    Given học viên có đăng ký PENDING
    When học viên gửi yêu cầu API mở bài bị hạn chế
    Then hệ thống từ chối cấp nội dung
~~~

Các kịch bản trên **chỉ là ví dụ**, cần người nghiệp vụ xác nhận. Chúng minh họa rằng một phần “delivery chậm” có thể do **thiếu ví dụ và thẩm quyền quyết định**, không phải do thiếu Scrum events.

## 11. Đánh giá tổ chức: quyền quyết định, phụ thuộc và quản trị

Tự chủ của nhóm cần đi cùng **mục tiêu, giới hạn và trách nhiệm giải trình**. Nếu mọi việc đều phải xin phép, giao giá trị chậm. Nếu nhóm tự bỏ qua an toàn và hợp đồng, rủi ro tăng.

### Bản đồ quyền quyết định

| Loại quyết định | Câu hỏi chẩn đoán |
| --- | --- |
| **Thứ tự Product Backlog** | Ai có quyền chốt? Có nhiều đầu mối cùng ra lệnh hay không? |
| **Cách chia lát và triển khai kỹ thuật** | Developers được tự quản như thế nào trong DoD và ranh giới chất lượng? |
| **Quy tắc nghiệp vụ** | Ai xác nhận PENDING/ACTIVE, hoàn thành bài hay quyền của giảng viên? |
| **Hợp đồng liên nhóm** | Ai có quyền thay đổi API, bên tiêu thụ được báo trước ra sao? |
| **Bảo mật và dữ liệu** | Điều gì bắt buộc, ai có quyền xét ngoại lệ? |
| **Ngân sách và mua dịch vụ ngoài** | Hạn mức nào được trao, quyết định nào cần thẩm quyền tài chính? |
| **Release và khôi phục** | Ai có quyền bật flag, dừng rollout, rollback hoặc xử lý incident? |
| **Cải tiến quy trình** | Nhóm có quyền thay đổi WIP, cách review và chuẩn kỹ thuật trong giới hạn nào? |

### Tìm chính sách ngầm

Một quy trình trên tài liệu có thể ghi **“Developer tự quyết kỹ thuật”**, nhưng thực tế mỗi PR phải chờ một quản lý duyệt. Hoặc Product Owner có tên trên backlog, trong khi stakeholder gửi trực tiếp task cho từng Developer. Hãy kiểm tra **công việc thật và hành vi quyết định thật**, không chỉ sơ đồ tổ chức.

### Không mặc định mọi bước phê duyệt đều là lãng phí

Kiểm soát quyền truy cập, dữ liệu cá nhân, tài chính và các nghĩa vụ hợp đồng có thể là **ràng buộc bắt buộc**. Vấn đề chẩn đoán là kiểm soát nào cần thiết, kiểm soát nào trùng lặp, có thể dùng kiểm tra tự động/risk-based review và có đường escalation rõ không.

Không nên tự đưa ra kết luận pháp lý từ một buổi workshop. Khi phạm vi đánh giá chạm chính sách dữ liệu hoặc nghĩa vụ ngoài, hãy tham vấn **người có thẩm quyền và chuyên môn phù hợp**.

## 12. Khả năng cộng tác và an toàn tâm lý là một phần của hiện trạng

Các hệ thống đo flow có thể nhìn thấy thời gian chờ; chúng khó nhìn thấy **lý do người có thông tin không lên tiếng**.

### Cần quan sát điều gì?

- Người mới có thể hỏi **“tôi chưa hiểu”** mà không bị coi thường?
- Một tester có thể báo lỗi quyền ngay trước release mà không bị trách là cản tiến độ?
- Người ở múi giờ khác có thời gian góp ý trước khi quyết định quan trọng được chốt?
- Các Developers có thể phản biện thiết kế của người có thâm niên bằng bằng chứng?
- Retrospective có tạo action thực thi được hay chỉ báo cáo cho quản lý?
- Người gặp blocker có kênh yêu cầu trợ giúp và người chốt phù hợp?
- Các bên có **cùng định nghĩa Ready, Done, severity, ưu tiên** không?

### Kết hợp nhiều hình thức thu thập

Có thể dùng phỏng vấn 1:1, quan sát họp, khảo sát tự nguyện và thảo luận nhóm nhỏ. Tuy nhiên, **không được hứa ẩn danh tuyệt đối** trong một nhóm vài người; cũng không nên chia kết quả khảo sát quá chi tiết khiến thành viên bị nhận diện.

### Dữ liệu khảo sát không phải chẩn đoán cá nhân

Một câu hỏi như “Tôi có thể nêu rủi ro ảnh hưởng người dùng mà không bị làm nhục” có thể cung cấp tín hiệu về môi trường hợp tác. Không dùng kết quả để chấm **“nhân viên A thiếu tư duy Agile”**. Nếu phát hiện hành vi quấy rối, trả đũa hoặc vi phạm nghiêm trọng, cần kênh xử lý phù hợp, không ép người bị ảnh hưởng công khai chi tiết trong Retrospective.

## 13. Thu thập dữ liệu bằng cách nào để không làm sai bức tranh?

Không nên dựa trên **một dashboard duy nhất**, cũng không nên chỉ phỏng vấn người quản lý. Một cách thực tế là **triangulation (đối chiếu nhiều nguồn độc lập)**.

### Ba nguồn bằng chứng bổ sung nhau

1. **Dấu vết công việc:** timestamps, trạng thái PBI, thay đổi scope, PR, CI, release, incidents.
2. **Người tham gia thực tế:** Product Owner, Developers, tester, vận hành, hỗ trợ, stakeholder và người học khi phù hợp.
3. **Quan sát/đi theo một ca cụ thể:** xem một user story đi qua bàn giao, review và sự kiện release ra sao.

| Nguồn | Lợi ích | Giới hạn |
| --- | --- | --- |
| **Issue tracker** | Có lịch sử việc, blocker, chuyển trạng thái | Done có thể được đánh muộn/sớm, trạng thái không theo thực tế |
| **Git/CI/release logs** | Thấy thay đổi, tích hợp, test và triển khai | Một commit không đồng nhất một PBI hay một giá trị người dùng |
| **Support/incident data** | Thấy lỗi và khó khăn thực tế | Nhiều người bị ảnh hưởng không báo; một lỗi có nhiều ticket |
| **Product analytics** | Quan sát hành vi sử dụng sản phẩm | Có thể thiếu người dùng không được theo dõi, phải tôn trọng dữ liệu |
| **Phỏng vấn** | Giải thích cơ chế, phụ thuộc và thỏa thuận ngầm | Ký ức có thể thiên lệch; cần đối chiếu |
| **Workshop trực quan luồng** | Giúp các nhóm hiểu cùng một hành trình | Người có quyền lực có thể thống trị cuộc trao đổi |
| **Khảo sát** | Có tín hiệu về cộng tác và trải nghiệm làm việc | Mẫu nhỏ, thiên lệch trả lời và rủi ro riêng tư |

### Tránh chọn dữ liệu để chứng minh kết luận đã có

Nếu lãnh đạo muốn chứng minh đội cần Scrum, việc chỉ chọn vài story có chờ đầu Sprint có thể bỏ qua phần lớn thời gian nằm ở **phê duyệt release**. Dữ liệu nên trả lời câu hỏi, **không phục vụ hợp thức hóa giải pháp đã chốt**.

### Ghi rõ những gì chưa biết

Ví dụ “Chưa có timestamp reliable từ lúc user yêu cầu tới lúc PO chấp nhận”; không nên suy ra lead time với độ chính xác một chữ số thập phân. Có thể bổ sung một sự kiện đo vào luồng rồi thu dữ liệu mới trước khi tuyên bố xu hướng.

## 14. Phỏng vấn và workshop chẩn đoán mà không biến thành buổi buộc tội

Một workshop tốt giúp nhóm **tạo bản đồ chung và bộc lộ các khác biệt về thực tế**. Người điều phối cần tránh để người có chức danh cao định nghĩa nguyên nhân thay cho những người trực tiếp làm.

### Mẫu câu hỏi phỏng vấn theo vai trò

| Nhóm người | Câu hỏi mở hữu ích |
| --- | --- |
| **Học viên/hỗ trợ** | Lúc nào người dùng không đạt mục tiêu? Khi cần sửa lỗi, phản hồi quay về đội phát triển ra sao? |
| **Product Owner** | Điều gì khiến một PBI khó ưu tiên hoặc khó chốt? Khi nào biết giả thuyết sản phẩm sai? |
| **Developers** | Story nào gần đây bị chặn lâu nhất? Có thể tự quyết điều gì? Test/CI phản hồi ra sao? |
| **Tester/QA** | Lỗi thường được phát hiện ở giai đoạn nào? Những tình huống nào khó tái hiện? |
| **Vận hành** | Release nào phải chờ? Khi có lỗi, làm sao phát hiện, giảm tác động và khôi phục? |
| **Bảo mật/compliance** | Ràng buộc nào bắt buộc? Có cách đánh giá theo rủi ro thay vì duyệt mọi đổi tên biến? |
| **Lãnh đạo/stakeholder** | Kết quả mong muốn nào quan trọng? Giới hạn ngân sách, trách nhiệm và thẩm quyền là gì? |

### Workshop 60–90 phút minh họa

1. **Nêu mục tiêu và an toàn:** đánh giá hệ thống, không xếp hạng cá nhân.
2. **Chọn một PBI thực:** đi từ yêu cầu tới availability.
3. **Vẽ các bước và vòng lặp:** bao gồm chờ quyết định, làm lại, kiểm thử và release.
4. **Đánh dấu dữ liệu và bất định:** điều gì có timestamp, điều gì mới là giả thuyết.
5. **Nghe từ vai trò khác nhau:** người nghiệp vụ, Developers, tester, vận hành đều có cơ hội.
6. **Chọn vài vấn đề đáng kiểm chứng:** không vội biểu quyết “framework thắng”.
7. **Ghi owner cho bước thu thêm bằng chứng** và mốc xem lại.

### Một workshop không nên tạo cảm giác có tất cả câu trả lời

Sau cuộc họp, có thể còn mâu thuẫn: PO nói story chờ API, Developers nói story chờ quy tắc nghiệp vụ. Hãy cùng xem **một hoặc hai hạng mục thật** rồi xác nhận lịch sử. Không biến bất đồng thành đánh giá về đạo đức hay thái độ của người khác.

## 15. Dùng 5 Whys, sơ đồ nhân quả và giả thuyết có thể bác bỏ

Sau khi thấy nơi công việc chậm, cần hỏi **vì sao** và liệu nguyên nhân được đề xuất có đủ bằng chứng không.

### Ví dụ chuỗi câu hỏi về chờ review

1. Vì sao story lâu Done? Vì chờ PR review gần bốn ngày.
2. Vì sao PR chờ lâu? Người đủ chuyên môn đang xử lý nhiều PR và incident cùng lúc.
3. Vì sao quá nhiều PR chờ một người? Nhóm không phân phối kiến thức ở module quyền học.
4. Vì sao kiến thức tập trung? Những thay đổi quan trọng trước đây thường do một người sở hữu, thiếu pairing/tài liệu.
5. Vì sao chưa cải thiện? Mục tiêu delivery chỉ đếm story code complete, không nhìn **hàng đợi và năng lực hoàn tất end-to-end**.

Đây là **chuỗi nguyên nhân minh họa cần xác minh**. Một hệ thống thật có thể còn yếu tố khác: PR quá lớn, test flaky, thiếu công cụ, yêu cầu bảo mật hoặc review không được ưu tiên. 5 Whys không bắt buộc luôn dừng đúng câu hỏi thứ năm, cũng không chứng minh nhân quả.

### Chuyển thành giả thuyết thực nghiệm

> “Nếu dùng pairing/knowledge sharing và review ưu tiên PR nhỏ cho module quyền học, thời gian chờ review của story cùng loại sẽ giảm, **mà không tăng lỗi hồi quy hay vi phạm DoD**”.

Giả thuyết này có thể **bị bác bỏ**. Nếu thử rồi số liệu không giảm, nhóm cần điều chỉnh hướng điều tra, không cố tuyên bố thành công vì đã tổ chức pairing.

### Sơ đồ nhiều nhóm nguyên nhân

~~~mermaid
flowchart TD
    A["Triệu chứng: lead time dài và lỗi phát hiện muộn"] --> B["Nhu cầu: ưu tiên/AC chưa rõ"]
    A --> C["Flow: WIP, chờ review và release"]
    A --> D["Kỹ thuật: CI/test/integration"]
    A --> E["Tổ chức: quyền quyết định, phụ thuộc"]
    A --> F["Dữ liệu: legacy, cache, concurrency"]
    A --> G["Cộng tác: phản hồi muộn, thiếu an toàn nói lỗi"]
    B --> H["Chọn giả thuyết có thể kiểm chứng"]
    C --> H
    D --> H
    E --> H
    F --> H
    G --> H
    H --> I["Thử thay đổi có guardrail"]
~~~

### Phân biệt nguyên nhân lỗi với nguyên nhân lỗi bị phát hiện muộn

Một defect đăng ký trùng có thể xuất phát từ **hai request đồng thời** và thiếu ràng buộc DB. Việc nó lọt production có thể do **unit test chỉ chạy tuần tự** và không có integration test. Cải tiến cần xử lý **cả cơ chế tạo sai lệch và lớp phản hồi bị thiếu**, chứ không chỉ yêu cầu QA “kiểm thử cẩn thận hơn”.

## 16. Đánh giá mức sẵn sàng thay đổi và những ràng buộc thực tế

Một biện pháp được đề xuất có thể đúng về kỹ thuật nhưng không thể triển khai ngay vì **quyền hạn, hợp đồng, dữ liệu, thời gian hoặc năng lực tổ chức**.

### Câu hỏi chuẩn bị

| Lĩnh vực | Cần hỏi | Ví dụ giới hạn |
| --- | --- | --- |
| **Sponsorship/định hướng** | Có ai chịu trách nhiệm về kết quả và tháo blocker ngoài quyền nhóm? | Không ai có quyền đổi quy trình phê duyệt liên phòng |
| **Năng lực** | Nhóm có đủ thời gian cho delivery, vận hành và thử cải tiến? | Đang trực khai giảng, khó làm đổi nền tảng lớn |
| **Kiến trúc/hạ tầng** | Có thể tích hợp tự động và tạo môi trường test đáng tin? | Database dùng chung, chưa có fixture an toàn |
| **Dữ liệu** | Có hạn chế truy cập, xử lý và sử dụng dữ liệu cá nhân? | Không thể copy dữ liệu học viên production về máy cá nhân |
| **Bảo mật/tuân thủ** | Ràng buộc nào là bắt buộc, ai được phép thay đổi chính sách? | Kiểm tra quyền phải ở máy chủ |
| **Hợp đồng/phụ thuộc** | Đối tác hoặc client hiện tại dùng API nào? | Không thể xóa trường JSON cũ tức thì |
| **Kỹ năng và quyền quyết định** | Nhóm có đủ kiến thức/được quyền tự quyết? | Mọi thay đổi API cần đội khác xác nhận |
| **Văn hóa phản hồi** | Mọi người có thể thừa nhận chưa biết, nêu lỗi và đề xuất sửa? | KPI cá nhân đang khuyến khích giấu blocker |

### Đừng lấy đánh giá “readiness” làm cớ trì hoãn vô thời hạn

Không cần chờ mọi điều kiện hoàn hảo để thử một cải tiến nhỏ, an toàn và có thể đảo ngược. Ví dụ, dù chưa có CI lý tưởng, nhóm vẫn có thể **làm rõ acceptance criteria trước khi code** và ghi thời gian chờ nghiệp vụ. Điều quan trọng là **phạm vi thử không vượt guardrails**.

### Không dùng một điểm tổng hợp để che xung đột

Tổ chức được chấm “7/10 về Agile readiness” nhưng **chưa có người chịu trách nhiệm bảo mật dữ liệu** thì con số tổng thể không đủ hỗ trợ quyết định phát hành. Các rủi ro không thể đánh đổi phải được nêu riêng với người có thẩm quyền phù hợp.

## 17. Chọn vấn đề ưu tiên trước khi chọn giải pháp

Sau giai đoạn chẩn đoán, nhóm thường có nhiều phát hiện. Cần ưu tiên dựa trên **tác động và khả năng học được điều có ích**, không theo mức độ dễ thấy của một cuộc họp hoặc sức thuyết phục của người có quyền lực.

### Ma trận ưu tiên minh họa

| Vấn đề hiện trạng | Tác động | Bằng chứng/độ bất định | Khả năng thử | Hướng xử lý |
| --- | --- | --- | --- | --- |
| **Lỗi cấp sai quyền cho PENDING** | Có thể nghiêm trọng, không thể chấp nhận | Cần xác nhận phạm vi và cơ chế ngay | Có test API/incident process | **Ứng phó ngay**, không chờ thử nghiệm transformation |
| **Nhiều story chờ quy tắc nghiệp vụ** | Lead time, rework cao | 8/14 story có blocker được ghi nhận, chưa rõ vì sao | Có thể thử Three Amigos | Chọn thử nhỏ và đo |
| **PR chờ review lâu** | Chậm Done, tích hợp muộn | Có timestamp nhưng thiếu phân loại | Có thể thử WIP/PR nhỏ | Chọn giả thuyết và kiểm chứng |
| **Đổi toàn bộ công cụ quản lý việc** | Lợi ích chưa rõ | Chủ yếu là cảm nhận của một nhóm | Chi phí chuyển cao | Chưa ưu tiên, cần chứng minh vấn đề do công cụ |
| **Đồng bộ tiến độ cache thiếu test** | Nguy cơ sai dữ liệu người học | Có defect tái hiện được | Có thể bổ sung integration test | Ưu tiên phòng ngừa |
| **Mỗi team có nghi thức khác nhau** | Chưa thấy tác động trực tiếp | Chỉ khác hình thức | Dễ áp bộ quy tắc chung | Chưa coi là vấn đề nếu kết quả vẫn tốt |

### Một cách xếp thứ tự hợp lý

1. **Rủi ro bắt buộc/đang gây hại** được xử lý theo quy trình phù hợp trước.
2. **Điểm nghẽn end-to-end có ảnh hưởng lớn** được ưu tiên khảo sát và giảm.
3. **Giả thuyết có thể thử nhỏ** được chọn để học sớm, thay vì dự án thay đổi lớn cùng lúc.
4. **Ý tưởng chưa có bằng chứng vấn đề** được giữ ở nơi đề xuất, không gán thành công việc đã cam kết.

Đây không phải thuật toán chấm điểm cứng. Cần xem **phạm vi quyền, giá trị, chất lượng và năng lực** trước khi chọn.

## 18. Chọn Scrum, Kanban, XP hay kết hợp sau khi đã chẩn đoán

Không có một framework là đáp án cho mọi tổ chức. Mỗi cách tiếp cận hỗ trợ một tập vấn đề; lựa chọn phải gắn với **cơ chế đang cần cải thiện**.

| Hiện trạng nổi bật | Thực hành có thể hữu ích | Vì sao | Điều không tự giải quyết |
| --- | --- | --- | --- |
| **Sản phẩm phức tạp, nhu cầu biến động, khó xác định giá trị trước** | **Scrum** với Product Goal, Sprint Goal, Increment, Review và Retrospective đúng mục đích | Tạo nhịp empiricism, minh bạch và thích ứng | Tự nó không cung cấp CI, TDD hay quyền quyết định tổ chức |
| **Nhiều loại việc đến liên tục, tồn đọng, chờ đợi không ổn định** | **Kanban**: trực quan hóa flow, explicit policies, WIP, work item age, SLE | Thấy và điều chỉnh hàng đợi theo dữ liệu | Không tự giải quyết quy tắc sản phẩm mơ hồ |
| **Lỗi hồi quy, mã khó đổi, tích hợp muộn** | **XP**: TDD, CI, refactoring, pairing, thiết kế đơn giản | Tăng phản hồi kỹ thuật và an toàn thay đổi | Không thay thế quản trị sản phẩm hoặc chính sách dữ liệu |
| **Đầu-cuối có quá nhiều chờ và bàn giao** | **Lean/VSM**, tối ưu dòng giá trị, giảm batch size | Chỉ ra tối ưu cục bộ và chờ không cần thiết | Không tự cung cấp cấu trúc team hay test tự động |
| **Yêu cầu chưa rõ, nhiều rework nghiệp vụ** | **User story, ATDD/Three Amigos, discovery–delivery** | Thống nhất ví dụ trước khi code | Không tự làm mất quyền phê duyệt hoặc deadline ngoài |
| **Ràng buộc pháp lý/bảo mật phức tạp** | Quản trị theo rủi ro, guardrails, contract tests, kiểm soát tích hợp | Giúp trao quyền trong phạm vi an toàn | Không thể bỏ nghĩa vụ bắt buộc chỉ vì đổi framework |
| **Nhóm phân tán khó nghe được phản hồi** | Working Agreement, async RFC, decision log, facilitation | Tăng cơ hội đóng góp và minh bạch quyết định | Không thay thế xử lý hành vi gây hại hoặc rủi ro quyền |

### Scrum và Kanban không nhất thiết loại trừ nhau

Một Scrum Team có thể dùng **các thực hành Kanban** để cải thiện flow trong Sprint, đồng thời dùng **TDD/CI/refactoring từ XP** để duy trì chất lượng. Nhưng cần giữ các accountability, events và commitments của Scrum nếu tổ chức nói đang áp dụng Scrum theo Scrum Guide.

### Không áp dụng XP như một danh sách khẩu hiệu

Nếu không có môi trường test hoặc các kiểm thử hiện tại thường thất bại ngẫu nhiên, ra lệnh “mọi nhóm phải TDD 100% từ tuần sau” có thể tạo áp lực mà không cải thiện phản hồi. Hãy thử trên **một module có rủi ro/giá trị rõ**, đầu tư kỹ năng và kiểm tra hiệu quả.

### Không bắt mọi đội có cùng nhịp

Một nhóm sản phẩm cần khám phá và giao Increment theo Sprint có thể khác nhóm vận hành xử lý sự cố liên tục. Mục tiêu tổ chức nên là **dòng giá trị và phối hợp**, không phải tất cả bảng phải cùng số cột và mọi cuộc họp cùng thời lượng.

## 19. Từ phát hiện tới giả thuyết và thử nghiệm nhỏ có guardrails

Chẩn đoán chỉ tạo giá trị khi dẫn tới **thay đổi có thể kiểm chứng trong công việc thật**.

### Mẫu Improvement Experiment

~~~text
ID / vấn đề:
Nguồn quan sát và baseline:
Ảnh hưởng tới người dùng / flow / chất lượng:
Giả thuyết cơ chế:
Thay đổi dự định thử:
Phạm vi / loại công việc / cohort:
Owner theo dõi và người phối hợp:
Quyền cần có / phụ thuộc cần chốt:
Thời điểm bắt đầu và xem lại:
Bằng chứng thực hiện action:
Outcome / flow metric với ranh giới rõ:
Guardrails bắt buộc:
Tiêu chí giữ, điều chỉnh hoặc dừng:
Điều chưa biết:
~~~

### Ví dụ: giảm câu hỏi nghiệp vụ muộn

**Quan sát:** trong 14 story gần đây, tám story bị chặn vì chưa hiểu trạng thái ghi danh hoặc quyền học.

**Giả thuyết:** nếu người nghiệp vụ, Developer và tester thống nhất một số ví dụ chấp nhận trước khi bắt đầu các story rủi ro cao, ít story sẽ bị chặn khi đang làm.

**Thử nghiệm:** dùng phiên Three Amigos ngắn cho **năm user story rủi ro cao** trong hai tuần; không bắt mọi task kỹ thuật tham gia nghi thức dài.

**Bằng chứng thực hiện:** năm story có ví dụ Gherkin/decision table và người xác nhận quy tắc.

**Outcome kỳ vọng:** số story bị chặn bởi thiếu quy tắc giảm, thời gian chờ quyết định giảm; chưa đặt phần trăm giảm chắc chắn.

**Guardrails:** không làm tăng thời gian chuẩn bị quá mức; không tạo cảm giác story đã Ready dù còn rủi ro bảo mật; DoD không giảm.

**Mốc xem lại:** sau khi đủ story đi qua luồng, nhóm đối chiếu dữ liệu và quyết định **giữ, điều chỉnh hoặc dừng**.

### Đừng gọi “đã tổ chức năm buổi” là thành công

Đó mới là **output**. Nếu story vẫn bị chặn ở cùng nơi hoặc nhiều câu hỏi phải hỏi lại, nhóm cần tìm nguyên nhân khác như **người quyết định không có thẩm quyền, phụ thuộc liên nhóm hoặc thiếu dữ liệu test**.

## 20. Một lộ trình thay đổi theo năng lực thay vì “big bang”

Đánh giá hiện trạng không bắt buộc tạo một kế hoạch chuyển đổi nhiều năm. Với phạm vi vừa đủ, có thể xây một **chuỗi bước học hỏi ngắn**, mỗi bước tạo thông tin cho quyết định tiếp theo.

### Ba giai đoạn minh họa, không phải công thức cứng

| Giai đoạn | Trọng tâm | Dấu hiệu nên có trước khi mở rộng |
| --- | --- | --- |
| **Hiểu hiện trạng** | Chọn value stream, dữ liệu, phỏng vấn, map flow, vấn đề/ràng buộc | Một số nguyên nhân có bằng chứng, các khoảng chưa biết được ghi rõ |
| **Thử cải tiến có phạm vi** | Thay chính sách WIP, bổ sung acceptance tests, sửa CI hoặc cơ chế quyết định | Có người sở hữu, guardrails, baseline và phản hồi thực tế |
| **Điều chỉnh/nhân rộng** | Giữ biện pháp có hiệu quả, đào tạo, cập nhật quản trị và liên nhóm | Lợi ích còn thấy trong bối cảnh mới, chi phí và rủi ro chấp nhận được |

Nếu cần một lịch điều phối, tổ chức có thể dùng mốc **30–60–90 ngày** cho các đợt xem lại, nhưng **không được coi đây là độ dài bắt buộc**. Một lỗi bảo mật cần xử lý ngay; một thay đổi cấu trúc liên nhóm có thể cần thời gian thử và tuân thủ dài hơn.

### Quản lý thay đổi cũng cần Product Backlog của chính nó?

Nhóm có thể dùng một **Improvement Backlog** gọn để minh bạch vấn đề, thử nghiệm, người phụ trách, bằng chứng và quyết định. Không nhất thiết phải tạo bộ máy báo cáo riêng nếu hạng mục cải tiến có thể nằm trong công việc hằng ngày/Sprint Backlog hoặc board Kanban.

### Không nhân rộng chỉ vì một pilot có số đẹp

Thử nghiệm trên đội nhỏ có dữ liệu sạch và quyền quyết định đầy đủ có thể hoạt động khác ở đội bị ràng buộc nhà cung cấp. Trước khi nhân rộng, cần xem **điều kiện dẫn tới thành công có tồn tại ở nơi mới không**, guardrails có phù hợp không và cần điều chỉnh những gì.

## 21. Case study: nền tảng học muốn “chuyển đổi Agile toàn công ty”

### 21.1. Bối cảnh

Một doanh nghiệp phát triển nền tảng quản lý khóa học. Đội có Product Owner, Developers, người kiểm thử, vận hành, hỗ trợ học viên; một số quyết định dữ liệu liên quan bộ phận an toàn thông tin và người quản lý ngân sách.

Ban đầu lãnh đạo muốn:

- Tất cả đội dùng Sprint hai tuần.
- Mọi thành viên báo story points hằng ngày.
- QA ký duyệt ở cuối mỗi Sprint.
- Mọi thay đổi sản phẩm phải có một quản lý cuối cùng phê duyệt.

Người phụ trách đánh giá đề xuất **chưa chọn cách triển khai** mà bắt đầu từ ba user story đã đi qua nhiều bước và vài incident gần đây.

### 21.2. Bằng chứng hiện trạng giả định

Đây là **dữ liệu minh họa**, không phải một benchmark của ngành:

| Tín hiệu | Quan sát hiện trạng | Điều chưa kết luận |
| --- | --- | --- |
| **15 story tiêu chuẩn trong sáu tuần** | Median request-accepted → availability là 21 ngày lịch; P85 được công cụ nhóm báo là 38 ngày | Chưa rõ phân phối ổn định hay không |
| **Tình trạng chờ** | Nhiều story chờ quyết định nghiệp vụ và test liên nhóm | Chưa biết tỷ trọng từng nguyên nhân trên toàn bộ sản phẩm |
| **Làm lại** | 7/15 story có ghi nhận yêu cầu làm rõ/sửa điều kiện sau khi bắt đầu | Chưa phân loại rework do học hỏi có giá trị hay do hiểu sai |
| **CI** | Test tích hợp đa phiên chỉ chạy thủ công sát release | Chưa xác định chi phí tự động hóa và độ ổn định |
| **Release** | Một số Increment đạt DoD nhưng chờ lịch bật feature flag | Cần phân biệt DoD với availability |
| **Escaped defects** | 3 defect được xác nhận trong cửa sổ đo đã chọn | Chưa đủ cơ sở kết luận xu hướng hay so team |
| **Quyền quyết định** | Quy tắc quyền học và lịch release được chốt qua nhiều kênh | Chưa có một decision log chung đáng tin |

**Không thể lấy median/P85 ở bảng làm cam kết cho PBI sắp tới.** Chúng chỉ tạo hướng điều tra ban đầu; cần xác nhận số liệu, cách tính phân vị và loại việc.

### 21.3. Đi theo một story thực

Story “Tiếp tục học cho khóa tuyến tính” có chuỗi sự kiện:

~~~mermaid
flowchart TD
    A["Product Owner tiếp nhận nhu cầu"] --> B["Story chờ rõ quy tắc quyền học"]
    B --> C["Developers làm UI và API"]
    C --> D["Đợi đội Identity xác nhận contract"]
    D --> E["Test tích hợp phát hiện trường hợp PENDING"]
    E --> F["Sửa quyền + bổ sung test"]
    F --> G["Increment đạt DoD"]
    G --> H["Chờ lịch release và bật flag"]
    H --> I["Học viên dùng được"]
~~~

Khi đi theo câu chuyện, nhóm thấy phần lập trình **không phải toàn bộ thời gian chờ**. Một số vấn đề đến từ cách chốt nghiệp vụ và phối hợp quyền học, một số đến từ kiểm thử, một số đến từ chính sách release.

### 21.4. Ba giả thuyết thay vì một gói framework

| Giả thuyết | Thử nhỏ | Điều quan sát |
| --- | --- | --- |
| **Quy tắc được làm rõ trước sẽ giảm rework** | Three Amigos cho story liên quan quyền/trạng thái | Blocker nghiệp vụ, số vòng sửa, thời gian chuẩn bị |
| **Contract/security tests sớm sẽ giảm lỗi muộn** | CI chạy API contract và test từ chối PENDING | Test phát hiện sai lệch, độ ổn định CI, escaped defects |
| **Giảm WIP/chờ review sẽ giảm cycle time** | Chính sách hoàn tất trước khi mở thêm việc, giới hạn hàng đợi review | Work item age, distribution, quality guardrail |

Không nên tự động cài một hệ thống đo velocity nếu nút nghẽn thực tế nằm ở **quyền quyết định và integration**.

### 21.5. Quyết định pilot

Nhóm chọn một luồng có ranh giới đủ rõ: **user story tiêu chuẩn về ghi danh/tiếp tục học**. Product Owner xác nhận mục tiêu và điều kiện nghiệp vụ; Developers tự chọn kỹ thuật; người có thẩm quyền bảo mật tham vấn những thay đổi ảnh hưởng quyền; vận hành xác định cách rollout và khôi phục.

**Mục tiêu thử** không phải “trở thành đội Agile chuẩn”, mà là:

> “Phát hiện sớm các sai lệch nghiệp vụ và tích hợp, giúp học viên nhận được những lát giá trị an toàn hơn, với thời gian chờ ít hơn”.

### 21.6. Một bảng kết quả giả định sau pilot

Giả sử sau một giai đoạn thử, nhóm có **12 story cùng loại được giao**, median lead time 17 ngày lịch và P85 28 ngày theo cùng công cụ/quy ước; chỉ có 1 defect được xác nhận trong cửa sổ đo tương ứng.

| Tín hiệu | Trước thử | Sau thử | Cách đọc đúng |
| --- | ---: | ---: | --- |
| Median lead time | 21 ngày | 17 ngày | Giảm 4 ngày (~19% tương đối) trong mẫu quan sát |
| P85 lead time | 38 ngày | 28 ngày | Đuôi chậm có vẻ ngắn hơn; mẫu còn nhỏ |
| Defect được phát hiện sau release | 3 | 1 | Chưa đủ để kết luận về xu hướng lâu dài |
| Số story được quan sát | 15 | 12 | Hai tập có thể khác độ khó, nhu cầu và lưu lượng |

**Không thể suy ra** những thay đổi thử nghiệm là nguyên nhân duy nhất. Cần kiểm tra cùng định nghĩa, tương đồng của story, số lượng hạng mục chưa xong, mùa khai giảng, thay đổi nhân sự và mức độ quan sát lỗi.

### 21.7. Kết luận có trách nhiệm

Nhóm có tín hiệu tích cực để **tiếp tục hoặc mở rộng có điều kiện** một số thực hành. Nếu còn lỗi quyền nghiêm trọng, việc giữ guardrail an toàn quan trọng hơn vài ngày giảm lead time. Tổ chức có thể quyết định **không áp một bộ nghi thức giống nhau lên mọi team**, mà cho từng value stream chọn cách vận hành trong ranh giới quản trị chung.

## 22. Đo thành công của chuyển đổi mà không chơi trò “đạt KPI”

Một chương trình thay đổi có thể làm đẹp dashboard mà không cải thiện giá trị. Do đó cần **bộ thước đo cân bằng** và cách đọc dữ liệu có trách nhiệm.

| Góc nhìn | Chỉ báo ví dụ | Bẫy cần tránh |
| --- | --- | --- |
| **Giá trị người dùng** | Tỷ lệ học viên đủ điều kiện mở đúng bài, trải nghiệm được xác nhận | Chỉ đếm tính năng đã phát hành |
| **Flow** | Lead/cycle time, WIP, throughput, work item age | Đổi điểm bắt đầu hoặc đẩy task chưa xong ra khỏi dữ liệu |
| **Chất lượng** | Lỗi lọt theo severity, contract failures, khả năng khôi phục | Chỉ đếm số bug, khuyến khích giấu báo cáo |
| **Khả năng học** | Thời gian từ giả thuyết tới phản hồi, số quyết định điều chỉnh vì bằng chứng | Đếm số cuộc thử nghiệm mà không xem bài học |
| **Cộng tác** | Thời gian chờ quyết định, blocker liên nhóm, phản hồi an toàn tâm lý tự nguyện | Xếp hạng cá nhân bằng số tin nhắn hoặc số lần nói |
| **Bền vững** | Gánh nặng trực, làm thêm giờ, độ ổn định đội | Tăng tốc bằng kiệt sức |
| **Quản trị và rủi ro** | Guardrails, quyền quyết định rõ, sự cố dữ liệu | Xem mọi phê duyệt bị xóa là thành công |

### Chỉ báo đầu ra và kết quả

~~~text
Output của thay đổi:
  - Đã tạo board với WIP limit
  - Đã chạy 5 buổi Three Amigos
  - Đã thêm contract tests

Outcome cần quan sát:
  - Story ít bị chặn vì thiếu quy tắc
  - API ít phá hợp đồng hơn trong các thay đổi liên quan
  - Lead time từ nhu cầu tới availability có độ tin cậy tốt hơn

Guardrails:
  - Không tăng lỗi quyền/mất dữ liệu
  - Không bỏ DoD hay kiểm thử bắt buộc
  - Không tạo gánh nặng họp và trực không bền vững
~~~

### Tránh các số đo kích thích hành vi sai

Nếu thưởng cho **velocity cao**, nhóm có thể tăng điểm story. Nếu thưởng vì **“zero defects”**, nhóm có thể không báo lỗi. Nếu KPI bắt buộc tất cả đội có cùng **Scrum maturity score**, nhiều người sẽ tô xanh checklist trong khi nút nghẽn còn nguyên.

Tốt hơn nên hỏi **“Chúng ta học được điều gì, thay đổi nào có bằng chứng cải thiện và rủi ro nào còn tồn tại?”**

## 23. Những phản mẫu cần tránh khi đánh giá và lựa chọn thay đổi

| Phản mẫu | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| **Chọn Scrum ngay trước khi tìm hiểu vấn đề** | Đổi lịch họp, không giảm hàng đợi và rework | Đánh giá value stream, rủi ro, nhu cầu trước |
| **Đánh giá dựa trên checklist nghi thức** | Coi người không làm đúng khuôn là kém Agile | Gắn đánh giá với value, flow, quality và learning |
| **Chỉ hỏi lãnh đạo** | Bỏ sót phụ thuộc và công việc thực tế | Phỏng vấn người trực tiếp làm, hỗ trợ và người dùng |
| **Chỉ hỏi Developers** | Bỏ qua quyết định sản phẩm, vận hành và nghĩa vụ | Có góc nhìn end-to-end |
| **Chỉ lấy dashboard** | Không thấy chính sách ngầm và lý do chờ | Quan sát hạng mục thật, triangulate |
| **Chỉ tin phỏng vấn** | Ký ức và nhận định có thể thiên lệch | Đối chiếu timestamp và trường hợp thực |
| **Gọi mọi thời gian chờ là lãng phí** | Dễ xóa kiểm soát an toàn có ích | Phân biệt chờ cần thiết và chờ có thể cải thiện |
| **Trộn lead time với cycle time** | So sánh sai và dự báo sai | Định nghĩa start/end, loại item và ngày đo |
| **Chỉ tính item Done** | Bỏ những việc già đang kẹt | Xem Work Item Age và intake age |
| **Xem test coverage là chất lượng toàn diện** | Bỏ sót API, dữ liệu, bảo mật, concurrency | Kiểm tra theo rủi ro nhiều tầng |
| **Đổ lỗi cho QA khi defect lọt** | Giấu vấn đề, không sửa nguyên nhân hệ thống | Postmortem dựa trên bằng chứng và lớp phòng vệ |
| **Dùng điểm maturity để xếp hạng nhóm** | Khuyến khích làm đẹp báo cáo | Dùng dữ liệu cải tiến nội bộ, có bối cảnh |
| **Bắt mọi team cùng bộ nghi thức** | Không phù hợp luồng sản phẩm, vận hành và hỗ trợ | Chọn thực hành theo vấn đề, giữ mục tiêu chung |
| **Bắt đầu quá nhiều thí nghiệm** | WIP cao, khó biết thay đổi nào có ích | Chọn ít, có owner, guardrails và mốc review |
| **Không có quyền quyết định** | Thử nghiệm bị treo, nhóm mất tự chủ | Làm rõ authority và escalation |
| **Bỏ chuẩn tuân thủ để giảm lead time** | Tăng rủi ro dữ liệu/hợp đồng | Governance risk-based và kiểm tra thích hợp |
| **Có action nhưng không xem hiệu quả** | Hoàn tất hoạt động, không chứng minh cải tiến | Theo dõi output, outcome và guardrail |
| **Tuyên bố thành công từ mẫu quá nhỏ** | Nhầm tương quan với nhân quả | Ghi độ bất định, kiểm tra bối cảnh, theo dõi tiếp |
| **Không xem người dùng sau rollout** | Giao nhanh thứ không hữu ích | Kết hợp analytics, feedback và Product Goal |
| **Chuyển đổi bằng mệnh lệnh và trừng phạt** | Giảm an toàn tâm lý, người làm giấu rủi ro | Minh bạch mục tiêu, mời phản hồi, hỗ trợ thay đổi |
| **Đổi tool thay vì đổi chính sách** | Quy trình chờ như cũ trong phần mềm mới | Xác định điểm nghẽn cụ thể, thử chính sách trước |

### Dấu hiệu để dừng và xem lại chương trình thay đổi

Nếu chất lượng giảm, sự cố bảo mật xuất hiện, nhóm liên tục phải làm ngoài giờ hoặc người dùng không còn nhận được giá trị, cần xem lại **giả thuyết thay đổi và ranh giới an toàn**, không tiếp tục chỉ vì lộ trình transformation đã được công bố.

## 24. Mẫu tài liệu Current-State Assessment tối giản

Một kết quả đánh giá hữu ích nên đủ ngắn để người có quyền quyết định **đọc, kiểm tra bằng chứng và chọn thử nghiệm**.

~~~text
TÊN VALUE STREAM:
Người dùng / nhu cầu / bối cảnh:
Mục tiêu đánh giá và quyết định cần hỗ trợ:
Phạm vi bao gồm / không bao gồm:

1. HIỆN TRẠNG ĐƯỢC XÁC NHẬN
   - Sơ đồ các bước thực tế từ đầu tới cuối:
   - Ranh giới start/end và loại item:
   - Số lượng quan sát, thời gian, nguồn dữ liệu:
   - Lead/cycle time, WIP, throughput, aging, blocked time:
   - Lỗi/chất lượng, phản hồi người dùng:
   - Các ràng buộc bắt buộc:

2. NHỮNG ĐIỀU CHƯA BIẾT
   - Dữ liệu còn thiếu:
   - Những nhận định giữa các vai trò đang khác nhau:
   - Rủi ro khi diễn giải:

3. VẤN ĐỀ ƯU TIÊN
   - Triệu chứng và tác động:
   - Giả thuyết nguyên nhân / bằng chứng hỗ trợ:
   - Điều có thể bác bỏ giả thuyết:

4. PHƯƠNG ÁN CẢI TIẾN
   - Thử nghiệm nhỏ:
   - Người theo dõi và quyền quyết định:
   - Thời điểm thử, mốc xem lại:
   - Outcome/flow và guardrails:
   - Phụ thuộc / điều kiện cần:

5. QUYẾT ĐỊNH SAU THỬ
   - Bằng chứng thực hiện và kết quả:
   - Điều chưa chắc / tác dụng phụ:
   - Giữ / Điều chỉnh / Dừng / Thu thêm bằng chứng:
   - Người chịu trách nhiệm bước tiếp:
~~~

### Không viết “nguyên nhân gốc” khi chưa xác minh

Trong phần vấn đề, dùng nhãn như **“giả thuyết về cơ chế”**, **“bằng chứng hỗ trợ”** và **“điều chưa biết”** khi phù hợp. Một báo cáo có các giới hạn rõ ràng thường giúp ra quyết định tốt hơn tài liệu khẳng định chắc chắn nhưng thiếu dữ liệu.

### Không cần mua phần mềm để có tài liệu này

Một bảng công việc, tài liệu chung và lịch sử CI/release đang có có thể đủ cho giai đoạn đầu. Công cụ mới nên giải quyết **một vấn đề đã được chứng minh**, không phải điều kiện bắt buộc để bắt đầu học hỏi.

## 25. Bài thực hành: chẩn đoán trước khi quyết định “chuyển sang Scrum”

### 25.1. Bối cảnh

Một nhóm phát triển nền tảng học có mười thành viên. Lãnh đạo yêu cầu áp dụng Scrum từ Sprint tới vì “giao tính năng chậm và QA thường phát hiện lỗi sát release”.

Nhóm thu được thông tin sau:

1. Trong **14 user story tiêu chuẩn gần đây**, có **8 story bị chặn** do chưa xác nhận quy tắc nghiệp vụ sau khi bắt đầu.
2. Median **work-start → DoD** là **12 ngày lịch** theo định nghĩa của nhóm; chưa có dữ liệu đủ tin cậy cho request → availability.
3. Một phần lớn thời gian nằm trong hàng đợi Review/Test; chưa có timestamp chi tiết để tách chờ code review với chờ môi trường.
4. Hầu hết code được merge vào cuối chu kỳ, integration test thường chạy thủ công.
5. Có **hai lỗi cấp quyền** được phát hiện sau release; một lỗi liên quan trạng thái PENDING.
6. Product Owner nhận yêu cầu trực tiếp từ nhiều stakeholder, thứ tự backlog thay đổi nhưng không có quyết định được ghi lại.
7. Nhóm vận hành cần đáp ứng nghĩa vụ kiểm tra dữ liệu trước khi mở rộng rollout.
8. Một số Developers đề nghị dùng Kanban với WIP limit; người khác muốn bắt đầu TDD.
9. Stakeholder muốn mọi PR được một người quản lý ký duyệt để “bảo đảm trách nhiệm”.
10. Một số thành viên ở múi giờ khác ngại nói trong cuộc họp nhưng viết bình luận kỹ thuật rất rõ trong issue.

### 25.2. Nhiệm vụ

1. Viết **mục đích đánh giá** dưới dạng câu hỏi ra quyết định thay vì tên framework.
2. Liệt kê **năm triệu chứng** có bằng chứng và **ba điều chưa biết** cần đo thêm.
3. Chọn **điểm bắt đầu/kết thúc** cho hai metric: lead time người dùng và cycle time thực hiện.
4. Tính tỷ lệ story trong mẫu bị chặn do quy tắc nghiệp vụ; giải thích giới hạn của mẫu.
5. Vẽ hoặc mô tả sơ đồ value stream từ yêu cầu tới học viên có thể dùng.
6. Đặt **ba giả thuyết nguyên nhân** có thể kiểm tra bằng bằng chứng.
7. Chọn **không quá hai thử nghiệm đầu tiên**, nêu phạm vi, owner và mốc xem lại.
8. Đề xuất một **outcome metric**, hai **flow/quality metrics** và ít nhất hai **guardrails**.
9. Phân biệt vấn đề nào cần **ứng phó ngay** với vấn đề có thể thử cải tiến.
10. Giải thích vì sao chỉ áp Sprint hai tuần **chưa chắc** xử lý vấn đề.
11. Trình bày cách dùng Scrum, Kanban hoặc XP **theo vấn đề** thay vì theo phong trào.
12. Nêu cách xử lý yêu cầu “mọi PR phải ký duyệt quản lý” trong phạm vi quản trị thích hợp.

### 25.3. Lời giải tham khảo – câu hỏi và ranh giới

**Mục đích đánh giá:** “Vì sao user story từ lúc được chấp nhận phục vụ tới lúc học viên có thể dùng mất lâu và lỗi quyền lại phát hiện muộn? Đâu là thay đổi nhỏ giúp giảm chờ, hiểu đúng yêu cầu và bảo vệ DoD?”

**Ranh giới đề nghị:**

- **Customer/request lead time:** yêu cầu được tiếp nhận hợp lệ (hoặc được chấp nhận phục vụ theo chính sách rõ) → khả năng thực sự có mặt cho cohort học viên mục tiêu; tính theo ngày lịch.
- **Cycle time thực hiện:** work started theo chính sách nhóm → Increment đạt Definition of Done.
- **Release waiting time:** DoD → availability, đo riêng nếu muốn thấy bước chờ phát hành.

Không được lấy median 12 ngày cycle time để tuyên bố “người dùng chỉ phải chờ 12 ngày”, vì còn các bước trước Work Started và sau DoD.

**Tỷ lệ có blocker nghiệp vụ trong mẫu:**

~~~text
8 / 14 × 100% ≈ 57,1%
~~~

Đây là **tỷ lệ của 14 story được quan sát**, không phải xác suất chính xác cho mọi story tương lai. Cần làm rõ “bị chặn” được ghi khi nào, mức độ nghiêm trọng, loại story và nguồn dữ liệu.

### 25.4. Lời giải tham khảo – giả thuyết

**Giả thuyết A:** acceptance criteria chưa được thống nhất trước Work Started khiến nhiều story phải chờ. Kiểm tra bằng cách đọc mẫu story, thời điểm đặt câu hỏi, người chốt và thời gian chờ.

**Giả thuyết B:** nhiều WIP cùng các PR lớn làm Review/Test thành nút thắt. Kiểm tra WIP, tuổi item, thời điểm Ready for Review, feedback đầu tiên và thời gian ở môi trường tích hợp.

**Giả thuyết C:** thiếu kiểm thử API/security và tích hợp sớm khiến lỗi quyền được tìm gần release. Kiểm tra DoD, test suite, lịch merge và lịch sử escaped defects.

Đây là **ba giả thuyết khác nhau có thể cùng đúng**, không phải một cuộc thi chọn nguyên nhân duy nhất. Vấn đề backlog thay đổi và quyền quyết định mơ hồ cũng có thể là một giả thuyết bổ sung cần xem theo bằng chứng.

### 25.5. Hai thử nghiệm đầu tiên khả thi

| Thành phần | Thử A: làm rõ nghiệp vụ trước | Thử B: tích hợp/test sớm |
| --- | --- | --- |
| **Vấn đề** | Nhiều story bị chặn vì thiếu quy tắc | Lỗi quyền xuất hiện gần release |
| **Hành động** | Thử Three Amigos 20 phút với 5 story rủi ro nghiệp vụ cao | Thêm API test cho PENDING/ACTIVE và chạy trong CI ở module liên quan |
| **Owner** | Đại diện PO/Developer đầu mối, tester phối hợp | Developer đầu mối, tester/CI phối hợp |
| **Phạm vi** | Các story quyền học/ghi danh sắp triển khai | Một hợp đồng API quyền học có rủi ro xác định |
| **Bằng chứng thực hiện** | Ví dụ chấp nhận, câu hỏi còn mở và người có quyền chốt | Test phát hiện sai quyền khi cố tái hiện, pipeline chạy ổn định |
| **Outcome kỳ vọng** | Ít blocker nghiệp vụ đến muộn | Phát hiện rủi ro quyền trước release |
| **Guardrail** | Không tăng nghi thức quá mức, không bỏ kiểm tra bắt buộc | Không giảm DoD, không phát hành quyền sai |
| **Mốc xem lại** | Sau khi các story thử đi qua luồng và có dữ liệu | Sau khi test chạy ổn định và quan sát thay đổi liên quan |

Nhóm có thể chọn thí nghiệm Kanban WIP/review thay cho một trong hai thử trên nếu bằng chứng cho thấy **hàng đợi là nút nghẽn lớn nhất**. Không có một đáp án framework bắt buộc.

### 25.6. Giải quyết những quyết định khó

**Hai lỗi quyền:** trước hết cần xác minh và giảm tác động theo chính sách bảo mật/sự cố, thêm test tái hiện và xem dữ liệu nào bị ảnh hưởng. Không chờ chương trình transformation mới bắt đầu sửa.

**Yêu cầu mọi PR phải ký duyệt quản lý:** hỏi điều gì trong sự cố trước đã không được phát hiện; phân loại thay đổi theo rủi ro. Có thể dùng **code review theo chuyên môn, API/security tests bắt buộc, contract tests và escalation khi vượt quyền** thay vì đặt một người quản lý thành hàng đợi cho mọi PR. Nếu chính sách tổ chức đã bắt buộc, nhóm phải tuân thủ và đề xuất điều chỉnh với người có thẩm quyền.

**Nhóm phân tán:** cho tài liệu và kênh phản hồi trước quyết định, ghi rõ người chốt, không coi im lặng ngoài giờ là đồng ý. Kênh góp ý phải giúp thông tin tác động tới quyết định thật.

**Scrum/Kanban/XP:** Scrum có thể hữu ích khi nhóm cần Product Goal, Sprint Goal và nhịp phản hồi sản phẩm; Kanban hữu ích để nhìn WIP/aging và giảm chờ; XP cung cấp TDD, CI, refactoring để giảm lỗi hồi quy. Các thực hành có thể **bổ trợ nhau**, nhưng phải triển khai theo mục tiêu và năng lực thực tế.

### 25.7. Bản tóm tắt khuyến nghị mẫu

> **Phát hiện:** hệ thống chậm có dấu hiệu đến từ yêu cầu chưa rõ, tích hợp muộn và hàng đợi Review/Test; dữ liệu customer lead time còn thiếu. **Ưu tiên:** bảo vệ quyền học ngay; thử làm rõ acceptance criteria và kiểm thử API sớm; ghi timestamp để xác minh nơi chờ. **Chưa quyết định:** có cần thay framework toàn công ty hay đổi công cụ không. **Cách kiểm tra:** sau một số story đủ tương đồng, so sánh blocker, work item age, lead/cycle time, chất lượng và phản hồi người dùng. **Guardrail:** DoD, quyền, dữ liệu và nhịp làm việc bền vững không bị đánh đổi.

Đây là kết quả đánh giá **hữu ích hơn** một câu kết luận “đội đạt maturity 2/5 nên phải áp dụng Scrum”.

## 26. Checklist trước khi lựa chọn cách thay đổi

- [ ] Đã ghi rõ **vấn đề người dùng hoặc dòng giá trị** cần cải thiện, thay vì đặt mục tiêu “trở nên Agile”?
- [ ] Có phân biệt **nghi thức Agile, thay đổi cấu trúc và outcome thực sự**?
- [ ] Phạm vi đánh giá và **quyết định cần hỗ trợ** đã được nêu rõ?
- [ ] Đã xác định **đơn vị công việc, điểm bắt đầu/kết thúc, loại việc và cohort**?
- [ ] Có sơ đồ **value stream thực tế**, bao gồm chờ, rework, tích hợp và release?
- [ ] Đã đối chiếu **dữ liệu công việc, người thực hiện và trường hợp thực tế**?
- [ ] Những chỉ số lead/cycle time, WIP, throughput, aging có **định nghĩa nhất quán**?
- [ ] Có xem **item chưa Done và hàng đợi cũ**, không chỉ những story giao được?
- [ ] Có phân biệt **triệu chứng, cơ chế, nguyên nhân giả thuyết và bằng chứng**?
- [ ] Những khoảng chưa biết và giới hạn dữ liệu được ghi minh bạch?
- [ ] Có đánh giá **phản hồi người dùng, Product Goal, backlog và acceptance criteria**?
- [ ] Có đánh giá **DoD, CI, test đa tầng, chất lượng, lỗi sau release và khả năng khôi phục**?
- [ ] Có xem **quyền quyết định, phụ thuộc liên nhóm, governance và ràng buộc bắt buộc**?
- [ ] Việc phỏng vấn/khảo sát bảo vệ **an toàn tâm lý và thông tin riêng tư**?
- [ ] Vấn đề đang gây rủi ro dữ liệu/bảo mật được **xử lý ngay**, không chờ lộ trình Agile?
- [ ] Trước khi chọn giải pháp, đã nêu **giả thuyết có thể bác bỏ và cách kiểm tra**?
- [ ] Việc ưu tiên dựa trên **tác động, rủi ro, độ bất định và khả năng thử**, không theo sở thích cá nhân?
- [ ] Scrum, Kanban, XP, Lean và ATDD được xem như **phương tiện cho từng loại vấn đề**?
- [ ] Tránh áp **một framework, độ dài Sprint hoặc công cụ giống nhau** lên mọi đội mà chưa xem bối cảnh?
- [ ] Thử nghiệm đầu tiên có **phạm vi nhỏ, owner, quyền quyết định, mốc xem lại**?
- [ ] Có **đường cơ sở, tín hiệu output, outcome và guardrails** phù hợp?
- [ ] Không dùng velocity, story points, số cuộc họp hoặc điểm maturity làm bằng chứng duy nhất của thành công?
- [ ] Các kết luận trước/sau có ghi **kích thước mẫu, định nghĩa và yếu tố gây nhiễu**?
- [ ] Nếu thử nghiệm không hiệu quả, có cơ chế **điều chỉnh/dừng mà vẫn học được điều có ích**?
- [ ] Nếu pilot có ích, đã kiểm tra **điều kiện nhân rộng** và tác dụng phụ với những đội khác?
- [ ] Người dùng, chất lượng và khả năng làm việc bền vững vẫn là tiêu chí sau khi thay đổi?

**Ghi nhớ:** **Chuyển đổi Agile bắt đầu bằng việc hiểu hệ thống hiện tại, không bắt đầu bằng việc chọn một framework hay đổi tên các cuộc họp.** Hãy đi theo một dòng giá trị thực, xác định ranh giới đo, xem thời gian chờ, chất lượng, quyền quyết định, nhu cầu người dùng và những điều chưa biết. Từ đó chọn **một vài giả thuyết thay đổi có thể kiểm chứng**, thử trên phạm vi an toàn, đo cả flow–outcome–quality và điều chỉnh theo phản hồi. Cách tiếp cận này giúp Scrum, Kanban, XP và Lean trở thành **công cụ để giao sản phẩm tăng dần, học sớm và cải tiến liên tục**, thay vì mục đích tự thân của một chương trình chuyển đổi.
