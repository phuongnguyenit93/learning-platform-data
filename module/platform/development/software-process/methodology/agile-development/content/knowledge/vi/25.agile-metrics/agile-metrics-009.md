# Hiểu vận tốc trong bối cảnh của từng nhóm và cách ước lượng

Một nhóm phát triển nền tảng học Java đang dùng Scrum. Trong buổi Sprint Review, quản lý hỏi: “Sprint trước nhóm A đạt 42 story points, nhóm B chỉ đạt 23. Có phải nhóm A năng suất gần gấp đôi nhóm B không?” Một người khác đề xuất tăng mục tiêu của nhóm B lên 40 points ngay Sprint tới để “nâng hiệu suất”.

Các câu hỏi nghe có vẻ hợp lý vì đều dùng con số. Tuy nhiên, **story points không có đơn vị chung giữa các nhóm**, và **velocity không đo giá trị, chất lượng hay nỗ lực của từng người**. Hai nhóm có thể ước lượng cùng một công việc theo hai thang khác nhau, có độ dài Sprint khác nhau, rủi ro khác nhau và tiêu chuẩn hoàn tất khác nhau. Nếu dùng velocity để xếp hạng, nhóm rất dễ thay cách cho điểm, chia ticket và báo cáo tiến độ chỉ để đạt mục tiêu số — trong khi người học vẫn chưa nhận được phần mềm tốt hơn.

Velocity thực sự hữu ích khi trả lời câu hỏi khác:

> “Dựa trên cách nhóm này ước lượng và lịch sử những phần công việc đã hoàn tất, nhóm có thể **dự báo có điều kiện** phạm vi công việc trong những Sprint sắp tới như thế nào?”

Bài **“Hiểu vận tốc trong bối cảnh của từng nhóm và cách ước lượng”** thuộc chương **Đo lường Agile** của module **AGILE_DEVELOPMENT**. Module hướng đến hiểu giá trị, nguyên tắc Agile và phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần, cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Vì vậy, bài không dừng ở cách cộng điểm: chúng ta sẽ học cách **ước lượng để hỗ trợ quyết định**, sử dụng velocity đúng giới hạn và kết hợp với **chất lượng, flow metrics và kết quả người dùng**.

Sau bài học, bạn có thể:

1. Định nghĩa **velocity**, story points, relative estimation và phân biệt chúng với capacity, effort, throughput, cycle time, forecast và commitment.
2. Tính velocity theo một quy ước nhất quán, chỉ ghi nhận công việc **thật sự đạt Definition of Done** và tránh đếm trùng.
3. Hiểu vì sao velocity chỉ mang ý nghĩa **bên trong bối cảnh của nhóm**, không có thang chuẩn để so sánh nhóm hoặc cá nhân.
4. Thực hành ước lượng tương đối qua **reference stories, Planning Poker và thảo luận bất định**.
5. Nhận diện lúc nên **chia nhỏ Product Backlog Item**, làm rõ acceptance criteria hoặc thử một **spike** trước khi ước lượng.
6. Sử dụng velocity lịch sử để tạo **dự báo phạm vi/thời gian có giả định và mức bất định rõ**.
7. Điều chỉnh lập kế hoạch khi có nghỉ phép, sự cố, thay đổi thành viên, phụ thuộc hoặc thay Definition of Done.
8. So sánh velocity với **throughput, WIP, cycle time, work item age và chỉ số giá trị/chất lượng** để tránh tối ưu sai.
9. Phát hiện những cách dùng sai: biến estimate thành deadline, thổi points, tính điểm cho việc chưa Done, hoặc dùng points chấm KPI nhân sự.
10. Lập một cuộc trao đổi thực tế với Product Owner và stakeholder bằng dữ liệu trung thực thay vì một cam kết giả chính xác.

## 1. Velocity là gì?

**Velocity (vận tốc của nhóm)** trong cách thực hành Agile phổ biến là **tổng đơn vị ước lượng của những Product Backlog Items (PBIs) hoặc user stories đã hoàn tất trong một khoảng lặp** — thường là một Sprint, theo quy ước của chính nhóm đó.

Khi nhóm dùng **story points** và thống nhất **chỉ tính PBI đạt Definition of Done (DoD)**, có thể viết:

\[
V_s = \sum_{i \in D_s} P_i
\]

Trong đó:

- \(V_s\): velocity thực tế của Sprint \(s\).
- \(D_s\): tập các PBI đạt DoD trong Sprint \(s\), theo chính sách đếm của nhóm.
- \(P_i\): số story points nhóm gán cho PBI \(i\).

**Ví dụ:** Sprint có năm PBI được chọn với 3, 5, 8, 5 và 2 points. Cuối Sprint, những PBI 3, 5, 5 và 2 points **đạt DoD**; PBI 8 points chưa hoàn thành.

\[
V = 3+5+5+2 = 15\ \text{points}
\]

Velocity là **15**, không phải 23. Điểm của PBI 8 points **không được tính một phần** chỉ vì đã code “80%”. Việc hoàn tất và tích hợp theo DoD quan trọng hơn tỷ lệ tiến độ tự khai.

### 1.1. Velocity đo điều gì?

Nó mô tả **lượng công việc theo quy ước ước lượng nội bộ đã hoàn tất** trong một Sprint. Khi được thu nhất quán qua nhiều Sprint, velocity có thể cung cấp một **tín hiệu quá khứ** cho cuộc trao đổi về phạm vi tiếp theo.

### 1.2. Velocity không đo điều gì?

Velocity **không trực tiếp đo**:

- Số giờ một người đã làm việc.
- Năng suất hoặc năng lực của một cá nhân.
- Giá trị kinh doanh mà người dùng đã nhận.
- Chất lượng kỹ thuật, độ tin cậy hoặc bảo mật.
- Tốc độ phát hành hay tốc độ nhận phản hồi người dùng.
- Hiệu quả tuyệt đối có thể so sánh giữa các nhóm.
- Cam kết chắc chắn cho Sprint hoặc ngày release kế tiếp.

Một nhóm có thể hoàn tất 30 points tính năng ít người dùng, trong khi nhóm khác hoàn tất 15 points sửa đúng một lỗi quan trọng làm học viên không thể nộp bài. Không thể suy từ 30 > 15 rằng nhóm đầu tạo giá trị lớn hơn.

### 1.3. Scrum có bắt buộc dùng velocity không?

**Không.** Scrum Guide 2020 không quy định phải dùng story points hoặc velocity. Scrum xác định accountabilities, events, artifacts và commitments; cách ước lượng, chia nhỏ và dự báo là những **kỹ thuật hỗ trợ** có thể được nhóm lựa chọn.

Nhóm sử dụng Scrum có thể dùng velocity nếu nó giúp Sprint Planning và Product Backlog management. Nhóm khác có thể dùng throughput và cycle time, đặc biệt khi các mục công việc tương đối đồng dạng và dữ liệu dòng công việc đáng tin cậy.

## 2. Phân biệt story points, effort, time và capacity

Những khái niệm có liên hệ, nhưng **không thể thay thế cho nhau**.

| Khái niệm | Câu hỏi nó giúp trả lời | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Story points** | So với các PBI nhóm từng biết, PBI này có quy mô tương đối thế nào? | Story A 3 points, story B 8 points trong cùng nhóm. | Không có đơn vị vật lý chung; không tự bằng giờ. |
| **Effort (công sức)** | Cần khoảng bao nhiêu nỗ lực làm việc? | Kiểm thử và tích hợp cần nhiều bước phối hợp. | Có thể không phản ánh thời gian chờ và lịch. |
| **Duration (thời gian trôi qua)** | Từ lúc bắt đầu đến lúc hoàn tất mất bao lâu? | PBI mất 6 ngày lịch từ Develop tới Done. | Có thể gồm chờ review, môi trường, phụ thuộc. |
| **Capacity (năng lực sẵn có)** | Trong Sprint tới nhóm có bao nhiêu khả năng thực hiện công việc? | Hai Developers nghỉ phép, có trực sự cố. | Không chuyển tuyến tính thành points nếu chưa có dữ liệu. |
| **Velocity** | Theo cách ước lượng nội bộ, Sprint trước hoàn tất bao nhiêu điểm? | 18 points đạt DoD. | Là quan sát quá khứ, không phải mục tiêu phải đạt. |
| **Throughput** | Hoàn tất được bao nhiêu mục trong một khoảng thời gian? | 6 PBI đạt Done trong tuần. | Số mục bị ảnh hưởng bởi kích thước/chính sách chia mục. |
| **Cycle time** | Mỗi mục từ Started tới Done mất bao lâu? | Trung vị 5 ngày làm việc. | Phải định nghĩa rõ Started/Done. |
| **Forecast (dự báo)** | Với dữ liệu và giả định hiện tại, điều gì có khả năng xảy ra? | Khoảng 3–5 Sprint cho một phạm vi có điều kiện. | Cần nêu mức bất định và điều kiện thay đổi. |
| **Commitment/cam kết** | Nhóm hướng tới mục tiêu nào và trách nhiệm gì? | Sprint Goal: học viên mở lại đúng bài học dở. | Không đồng nhất với “mọi PBI chọn vào Sprint đều phải xong bằng mọi giá”. |

### 2.1. Story points không phải “giờ trá hình”

Có nhóm định nghĩa story points dựa trên **effort tương đối**, có nhóm cân nhắc thêm **độ phức tạp và bất định**. Không có một phép quy đổi chính thức kiểu:

> 1 story point = 1 giờ lập trình, hay 1 point = 1 ngày công.

Nếu một nhóm tự dùng đơn vị thời gian ước lượng thì phải gọi và dùng nó minh bạch; **đừng gọi là points rồi tính như giờ** vì sẽ khiến các thành viên và stakeholder tưởng độ chính xác cao hơn thực tế.

### 2.2. “Velocity 20” không cho biết nhóm có thể làm bao nhiêu giờ

Một Sprint có thể gồm việc học công nghệ, review, xử lý sự cố, hỗ trợ vận hành, cải tiến CI và làm rõ nghiệp vụ. Các hoạt động ấy có thể thiết yếu nhưng không phải lúc nào được biểu diễn bằng PBI có points. Vì thế, velocity **không phải bảng chấm công**, và tăng velocity không đồng nghĩa tăng giờ làm.

### 2.3. Capacity ảnh hưởng dự báo nhưng không phải điểm tự sinh

Nếu một người nghỉ ba ngày, nhóm có thể có capacity thấp hơn. Tuy vậy, không thể tự khẳng định “nghỉ 20% ngày nên velocity chính xác giảm 20%”. Nhiều công việc cần phối hợp, có chờ đợi, người khác hỗ trợ, hoặc phụ thuộc không tuyến tính.

**Thực hành tốt:** dùng thông tin capacity cùng lịch sử tương tự, mức bất định và hiểu biết về loại việc để trao đổi phạm vi, không ép một công thức cơ học.

## 3. Story points là thang đo cục bộ của từng nhóm

Hãy tưởng tượng hai nhóm đánh giá cùng một yêu cầu: “Học viên có thể mở lại video tại vị trí đã dừng”.

- **Nhóm Alpha** quen dùng tập tham chiếu trong đó một lát lưu tiến độ đầu cuối thường khoảng **5 points**.
- **Nhóm Beta** có thang tham chiếu khác và coi lát tương tự là **13 points**.

Cả hai có thể nhất quán và hữu ích với chính mình. Sự khác biệt **không chứng minh** nhóm Beta làm chậm hơn hay Alpha giỏi hơn.

### Vì sao điểm khác nhau?

1. **Bộ story tham chiếu khác:** nhóm dựa vào những việc đã làm khác nhau.
2. **Cách hiểu điểm khác:** trọng tâm effort, complexity, uncertainty có thể được định nghĩa khác.
3. **Hệ thống khác:** mã cũ, CI, dữ liệu, quyền truy cập và phụ thuộc không giống nhau.
4. **Ranh giới story khác:** một nhóm tính cả luồng đầu cuối, nhóm khác cắt phạm vi khác.
5. **Definition of Done khác:** mức kiểm thử, tích hợp và tài liệu có thể không giống.
6. **Kinh nghiệm và hiểu miền khác:** nhóm quen nghiệp vụ có mức bất định thấp hơn.
7. **Thang điểm khác:** ngay cả khi cùng dùng 1–2–3–5–8–13, ý nghĩa tương đối chưa chắc giống.

### 3.1. Ví dụ hai nhóm có velocity rất khác

| Nhóm | Velocity lịch sử | Cách dùng points | Kết luận đúng |
| --- | ---: | --- | --- |
| **Alpha** | Khoảng 18–24 points/Sprint | Tập story tham chiếu Alpha, DoD Alpha. | Dùng để dự báo có điều kiện cho Alpha. |
| **Beta** | Khoảng 32–45 points/Sprint | Tập story tham chiếu Beta, DoD Beta. | Dùng để dự báo có điều kiện cho Beta. |

**Không được kết luận:** Beta năng suất gấp đôi Alpha. Points không phải đơn vị chung, và hai nhóm có thể phục vụ mục tiêu hoặc rủi ro khác nhau.

**Có thể hỏi có ích hơn:** “Mỗi nhóm có thể giao Increment chất lượng và nhận phản hồi tới người dùng sớm hơn thế nào, trong bối cảnh chính họ?”

### 3.2. Cùng một nhóm cũng có thể mất tính so sánh theo thời gian

Velocity qua nhiều Sprint đáng tin hơn nếu:

- Sprint có độ dài tương đối ổn định.
- Chính sách ước lượng và đếm Done nhất quán.
- Cấu trúc và capacity nhóm không biến động quá lớn.
- Loại công việc không đổi đột ngột.
- Definition of Done được duy trì rõ.
- Backlog được chia theo quy tắc tương đối nhất quán.

Nếu nhóm đổi từ Sprint hai tuần sang một tuần, thay nửa thành viên, tách một service lớn hoặc bổ sung kiểm soát bảo mật mới, dữ liệu cũ **có thể cần phân đoạn lại**, không lấy trung bình chung một cách máy móc.

## 4. Ước lượng để ra quyết định, không để tạo lời hứa

Mục tiêu hữu ích của ước lượng là giảm bất định ở những quyết định có ý nghĩa:

- PBI này đã đủ nhỏ để đưa vào một Sprint chưa?
- Có cần hỏi thêm nghiệp vụ hay thử kỹ thuật trước không?
- Những hạng mục nào có khả năng hoàn tất cùng nhau với capacity hiện tại?
- Phạm vi nào phù hợp để kiểm chứng giả thuyết giá trị sớm?
- Có rủi ro phụ thuộc hoặc kiểm thử làm forecast kém tin cậy không?
- Nếu cần một mốc phát hành, có những lựa chọn giảm phạm vi nào?

**Ước lượng không phải cam kết rằng thế giới sẽ diễn ra như con số ban đầu.**

Một con số 8 points giúp nhóm thảo luận. Nếu biến nó thành “8 points phải xong trước thứ Sáu”, nhóm có thể:

- Giấu việc mới phát hiện.
- Bỏ trường hợp biên hoặc hạ DoD.
- Chia công việc giả tạo để báo điểm đẹp.
- Tăng điểm ước lượng nhằm tạo bộ đệm.
- Né công việc có giá trị nhưng bất định cao.

Đó là lý do cần giữ **ước lượng, mục tiêu, dự báo, deadline và trạng thái Done** là những khái niệm riêng.

### 4.1. Ước lượng không thay thế phân chia công việc

Một story 34 points có thể là tín hiệu “quá nhiều điều chưa biết”. Phản ứng tốt thường không phải họp để thống nhất xem nó là 34 hay 40, mà hỏi:

> “Có hành vi nhỏ nào hoàn chỉnh từ đầu đến cuối giúp chúng ta kiểm chứng giả định quan trọng sớm hơn không?”

Chia lát dọc tốt có thể cải thiện cả độ rõ ước lượng lẫn khả năng giao giá trị.

## 5. Cách thiết lập thang ước lượng tương đối

Một nhóm có thể chọn **thang Fibonacci gần đúng** như 1, 2, 3, 5, 8, 13, 21 hoặc cách phân loại XS/S/M/L/XL. Khoảng cách tăng dần nhắc rằng **bất định thường tăng theo kích thước**, không đáng tranh luận giả chính xác kiểu 8 hay 8,5 points.

Thang điểm không phải chuẩn của Scrum và không có đơn vị toàn tổ chức.

### 5.1. Chọn reference stories

Một cách đơn giản:

1. Chọn 2–4 PBI đã hoàn tất và nhóm nhớ rõ công việc thực tế.
2. Kiểm tra những PBI đó có cùng Definition of Done và loại việc đủ tương đồng.
3. Đồng thuận một quy ước tương đối, ví dụ “PBI lưu trạng thái một lựa chọn có kiểm thử đầu cuối = 3 points”.
4. Ghi **điều kiện/độ phức tạp** làm PBI này thành 3 để có điểm tựa thảo luận.
5. Dùng những PBI tham chiếu để so hạng mục mới.
6. Khi sản phẩm thay đổi lớn, xem lại bộ tham chiếu thay vì giả định nó bất biến.

### 5.2. Bộ tham chiếu minh họa cho nền tảng học

| PBI đã Done hoặc được mô tả rõ | Điểm tham chiếu | Vì sao (trong giả định của nhóm này) |
| --- | ---: | --- |
| Người học nhìn thấy trạng thái “chưa có tiến độ” đúng quyền ở trang hiện có. | **2** | Hành vi nhỏ, dữ liệu đơn giản, đường kiểm thử đã sẵn. |
| Người học lưu và xem lại một trạng thái chọn bài trong phạm vi một tài khoản. | **3** | Có ghi/đọc dữ liệu, lỗi và kiểm tra quyền cơ bản. |
| Người học tiếp tục một video tại vị trí đã lưu qua các phiên đăng nhập. | **5** | Gồm UI, API, dữ liệu, quyền, xử lý không có tiến độ và kiểm thử đầu cuối. |
| Người học đồng bộ vị trí video giữa hai thiết bị với quy tắc xung đột rõ. | **8** | Nhiều đường tương tác, trạng thái cạnh tranh, thêm kiểm thử tích hợp. |
| Hỗ trợ xem offline và đồng bộ tiến độ sau khi kết nối lại. | **13 hoặc cần chia** | Nhiều bất định, trạng thái lỗi và độ phức tạp dữ liệu cao. |

**Các điểm trên chỉ là giả định học tập cho một nhóm minh họa.** Không dùng chúng làm chuẩn đánh giá cho nhóm khác hoặc làm công thức “mọi user story video = 5 points”.

### 5.3. DoD phải được tính vào ý nghĩa của ước lượng

Khi nhóm nói “lát này 5 points”, nó phải bao gồm công việc cần thiết để **đạt DoD**: thiết kế phù hợp, code, review, kiểm thử, tích hợp, xử lý lỗi và tài liệu/vận hành bắt buộc.

Không được ước lượng “chỉ code 5 points” rồi biến kiểm thử thành việc ngoài cam kết hoặc đẩy sang Sprint sau chỉ để points đẹp.

## 6. Planning Poker: biến bất đồng điểm thành thông tin

**Planning Poker** là kỹ thuật tạo cuộc trao đổi về phạm vi và bất định, không phải trò thi xem ai đoán đúng số của người nhiều kinh nghiệm nhất.

### Một vòng Planning Poker

1. **Product Owner hoặc người hiểu nghiệp vụ** giải thích mục tiêu, hành vi, dữ liệu và các tiêu chí quan trọng.
2. Developers hỏi về ranh giới, lỗi, phụ thuộc, DoD và những gì đã biết.
3. Mỗi người suy nghĩ và chọn một điểm **độc lập**.
4. Mọi người mở điểm **cùng lúc**, tránh bị neo bởi người nói trước.
5. Người đưa điểm thấp/cao giải thích giả định.
6. Cả nhóm sửa hiểu biết, bổ sung câu hỏi, chia lát hoặc chọn spike nếu cần.
7. Ước lượng lại khi đủ thông tin; ghi giả định còn mở và mức tự tin.

~~~mermaid
flowchart TD
    A["Mô tả PBI và mục tiêu người dùng"] --> B["Làm rõ acceptance criteria, DoD, phụ thuộc"]
    B --> C["Mỗi người chọn ước lượng độc lập"]
    C --> D["Hiển thị đồng thời"]
    D --> E{"Có khác biệt đáng kể?"}
    E -->|"Có"| F["Nghe giả định của người điểm cao/thấp"]
    F --> G{"PBI đã đủ rõ và nhỏ?"}
    G -->|"Chưa"| H["Hỏi lại PO, chia lát hoặc thử spike"]
    H --> B
    G -->|"Rồi"| C
    E -->|"Không"| I["Ghi estimate và giả định"]
    I --> J["Sẵn sàng xem xét lựa chọn phạm vi"]
~~~

### 6.1. Ví dụ bất đồng 3–5–8

PBI: “Học viên có thể mở lại video đã dừng.”

| Thành viên | Ước lượng | Giả định họ đang dùng |
| --- | ---: | --- |
| A | 3 | Chỉ khôi phục vị trí trong một phiên đăng nhập, API đã có. |
| B | 5 | Phải lưu qua các phiên, bao gồm quyền truy cập và trường hợp chưa có dữ liệu. |
| C | 8 | Phải đồng bộ nhiều thiết bị và xử lý vị trí xung đột. |

Không nên **lấy trung bình \((3+5+8)/3 \approx 5,33\)** rồi coi tranh luận đã xong. Ba người đang hình dung **ba phạm vi khác nhau**.

Sau trao đổi, nhóm có thể chốt **lát V1**: “Khôi phục vị trí cho một video qua các phiên đăng nhập, chưa có đồng bộ cạnh tranh nhiều thiết bị; đầy đủ kiểm tra quyền, lỗi và DoD”. Khi đó chọn **5 points** theo bộ tham chiếu riêng, còn đồng bộ đa thiết bị được nêu thành một lát sau để ưu tiên dựa trên giá trị.

### 6.2. Bất đồng không phải thất bại của ước lượng

Nếu một người nghĩ “2” và người khác nghĩ “13”, đó là một **tín hiệu phát hiện hiểu khác về yêu cầu hoặc rủi ro**. Giá trị của Planning Poker nằm nhiều ở cuộc thảo luận này hơn ở con số sau cùng.

### 6.3. Tránh Planning Poker hình thức

- Không ép người ít kinh nghiệm đổi điểm chỉ vì người nhiều kinh nghiệm nói trước.
- Không kéo dài tranh luận nhiều giờ về chênh lệch nhỏ không ảnh hưởng quyết định.
- Không buộc chấm điểm mọi task chi tiết; tập trung mức công việc cần dự báo.
- Không đưa ra con số khi thông tin quan trọng còn thiếu và không ghi giả định.
- Không dùng kết quả bỏ phiếu làm hợp đồng cá nhân.

## 7. Ước lượng một user story đầu cuối: ví dụ Gherkin

Giả sử nhóm muốn thực hiện PBI:

> **Là** học viên đã được cấp quyền xem khóa Java, **tôi muốn** mở lại một video ở vị trí đã lưu, **để** không phải tìm đoạn đang học lần trước.

Để ước lượng hợp lý, nhóm cần thống nhất **phạm vi hành vi** hơn là liệt kê kỹ thuật ngay từ đầu.

~~~gherkin
Feature: Tiếp tục video đã xem dở

Scenario: Có vị trí đã lưu hợp lệ
  Given học viên đã đăng nhập và có quyền xem "Bài A"
  And hệ thống đã lưu vị trí 05:20 cho học viên trong "Bài A"
  When học viên mở lại "Bài A" trong một phiên đăng nhập khác
  Then video có thể tiếp tục ở vị trí 05:20 theo sai số đã thỏa thuận
  And không hiển thị vị trí của học viên khác

Scenario: Chưa có tiến độ
  Given học viên có quyền xem "Bài A"
  And chưa có tiến độ lưu cho học viên trong "Bài A"
  When học viên mở "Bài A"
  Then video bắt đầu từ đầu
  And không thông báo sai rằng đã khôi phục tiến độ

Scenario: Không có quyền xem video
  Given một tài khoản không được quyền xem "Bài A"
  When tài khoản đó yêu cầu vị trí đã lưu của "Bài A"
  Then hệ thống từ chối theo chính sách
  And không tiết lộ dữ liệu tiến độ riêng tư

Scenario: Không lưu được vị trí
  Given học viên có quyền xem video
  And hệ thống gặp lỗi khi ghi tiến độ
  When ứng dụng gửi yêu cầu lưu vị trí
  Then không thông báo lưu thành công sai sự thật
  And cung cấp trạng thái và hướng xử lý phù hợp
~~~

Khi bàn về points, Developers có thể xem:

- UI hiện có cần thay gì?
- API và lưu dữ liệu đã có chưa?
- Chính sách quyền có sẵn hay có đường mới?
- Cần kiểm thử tích hợp ở cấp nào?
- Ngữ nghĩa “vị trí hợp lệ” đã rõ chưa?
- Có trường hợp đồng thời hoặc thiết bị khác nằm trong phạm vi không?
- Đạt DoD cần thêm công việc vận hành/tài liệu nào?

Nếu sau trao đổi nhóm vẫn thấy nhiều bất định, **câu trả lời không nhất thiết là “chọn nhiều points hơn”**. Có thể chọn một spike kỹ thuật ngắn, làm rõ hợp đồng hoặc chia lát trước khi đưa vào Sprint.

## 8. Chia nhỏ PBI trước khi cố tăng độ chính xác ước lượng

Càng nhiều quy tắc, phụ thuộc và trường hợp lỗi trong cùng PBI, estimate càng dễ dao động. **Chia lát dọc** vừa giúp ước lượng dễ hơn, vừa giúp tạo Increment sớm hơn.

### Ví dụ từ epic “Học tiếp trên mọi thiết bị”

| Lát | Giá trị người dùng | Ước lượng tham khảo nội bộ |
| --- | --- | ---: |
| **V1** | Mở lại một video tại vị trí đã lưu qua các phiên đăng nhập; quyền, lỗi và DoD đầy đủ. | 5 |
| **V2** | Từ trang chủ mở nhanh bài đang học dở. | 3 |
| **V3** | Đồng bộ giữa hai thiết bị với quy tắc xung đột. | 8 |
| **V4** | Hỗ trợ offline và đồng bộ an toàn khi có mạng. | 13 hoặc chia tiếp |

Điểm chỉ giúp nhóm minh họa. Điều quan trọng hơn là **V1 có thể dùng được** và giúp thu phản hồi trước khi đầu tư V3–V4.

### 8.1. Đừng chia theo lớp kỹ thuật rồi gọi mỗi phần là một story giá trị

**Chia ngang yếu:**

- Database: 3 points.
- Backend API: 5 points.
- Frontend: 5 points.
- QA/tích hợp: 3 points.

Đến cuối ba phần đầu, người học có thể vẫn không dùng được. Tổng 16 points của các task **không tự bằng** một Increment đầu cuối. Cách chia ngang có thể hữu ích cho việc phối hợp **bên trong PBI**, nhưng nên giữ một đơn vị tiến bộ có thể tích hợp và đạt DoD.

### 8.2. Cắt phạm vi không phải bỏ kiểm soát cần thiết

V1 chưa cần đồng bộ offline, nhưng vẫn phải kiểm tra quyền và xử lý lỗi trong những trường hợp được hỗ trợ. Không nên để “phân quyền và kiểm thử sau” thành một lát kế tiếp chỉ để V1 có ít points hơn.

### 8.3. Một story lớn làm forecast kém ổn định

Nếu nhóm thường hoàn tất những PBI 2–8 points nhưng đưa vào Sprint một PBI 34 points, việc nó đạt hay không đạt DoD có thể khiến velocity Sprint dao động mạnh. Cách tốt hơn thường là **chia thành các lát tạo giá trị và giảm bất định**, không phải hứa một con số chắc chắn hơn.

## 9. Tính velocity theo một quy ước rõ ràng

Một nhóm cần nhất quán ở ít nhất các điểm:

1. **Đơn vị:** points, không phải giờ.
2. **Phạm vi:** những PBI nào được ước lượng và đưa vào thống kê.
3. **Điểm hoàn tất:** DoD và mốc đếm Done.
4. **Thời gian:** Sprint nào, độ dài bao nhiêu.
5. **Chính sách với PBI tách/gộp:** tránh đếm trùng và thay cách tính ngầm.
6. **Thay đổi cách ước lượng:** phải chú thích khi làm mất tính so sánh.
7. **Công việc không dự kiến:** cách biểu diễn incident, bug, support và kỹ thuật cần thiết.

### 9.1. Bảng tính một Sprint

| PBI | Estimate của nhóm | Kết quả cuối Sprint | Points được ghi vào velocity |
| --- | ---: | --- | ---: |
| V1 – Khôi phục vị trí video qua các phiên | 5 | Đạt DoD | 5 |
| V2 – Nút “Học tiếp” trên trang chủ | 3 | Đạt DoD | 3 |
| B1 – Sửa lỗi kết quả bài kiểm tra trái quyền | 5 | Đạt DoD | 5 |
| T1 – Cải thiện luồng báo lỗi cho phép nộp đáp án | 2 | Đạt DoD | 2 |
| V3 – Đồng bộ đa thiết bị | 8 | Chưa đạt DoD | 0 |
| **Tổng** | **23** | **4/5 PBI Done** | **15** |

Nếu tất cả bốn PBI đầu tuân theo DoD, velocity theo quy ước là **15 points**. Việc V3 đã code 7/8 task không tạo 7 points được công nhận.

### 9.2. PBI chưa Done đi sang Sprint sau

V3 chưa Done có thể được hoàn thiện trong Sprint sau hoặc được thương lượng lại phạm vi. Không được **ghi 6 points Sprint này rồi thêm 8 points Sprint sau** cho cùng một phần giá trị đã ước lượng 8, vì như vậy đếm trùng.

Một quy tắc thực hành đơn giản là **ghi toàn bộ điểm của PBI ở Sprint nó đạt DoD**. Nếu nhóm tách PBI thành các lát mới có thể sử dụng, cần xác định lại phạm vi và estimates **minh bạch, không tính trùng phần đã hoàn tất**.

### 9.3. PBI đạt DoD không nhất thiết đã release

Velocity có thể được ghi khi PBI thực sự thuộc Increment đạt DoD, tùy quy ước nhóm, **không cần chờ Sprint Review hoặc một release rộng**. Tuy nhiên, nếu DoD của sản phẩm có yêu cầu triển khai hoặc kiểm tra vận hành cụ thể, nhóm vẫn phải đáp ứng nó. Nên theo dõi riêng khoảng **Done → Released → Feedback Observed** để tránh cho rằng points tăng đồng nghĩa người dùng đã nhận giá trị.

## 10. Dữ liệu lịch sử: nhìn chuỗi và phân bố, không chỉ một Sprint

Giả sử một Scrum Team dùng Sprint hai tuần, DoD và thang estimate tương đối nhất quán, đã ghi velocity năm Sprint:

| Sprint | Velocity thực tế | Tình huống minh họa |
| --- | ---: | --- |
| **S1** | 18 | Nhịp làm việc thông thường. |
| **S2** | 22 | Ít phụ thuộc ngoài, nhiều PBI nhỏ Done. |
| **S3** | 20 | Nhịp bình thường. |
| **S4** | 24 | Một số PBI lớn từ Sprint trước đạt DoD. |
| **S5** | 16 | Môi trường tích hợp gặp sự cố và có nghỉ phép. |
| **Tổng** | **100** | Năm Sprint. |

Velocity trung bình quan sát:

\[
\bar{V}=\frac{18+22+20+24+16}{5}=20
\]

Sắp xếp các quan sát: **16, 18, 20, 22, 24**, nên:

- **Trung vị:** 20 points/Sprint.
- **Nhỏ nhất/lớn nhất trong mẫu:** 16–24 points/Sprint.
- **Biên độ quan sát:** 8 points.

**Giải thích đúng:** trong năm Sprint có điều kiện tương đối giống nhau này, nhóm hoàn tất **trung bình 20 points/Sprint**. Khoảng 16–24 là **dải quan sát**, **không phải** khoảng dự báo 80%, 90% hay 95%. Với năm quan sát, không có cơ sở tự gán một mức tin cậy thống kê.

### 10.1. Tại sao không lấy Sprint cao nhất làm “năng lực thật”?

S4 đạt 24 có thể nhờ vài PBI bắt đầu từ Sprint trước chỉ vừa đạt DoD trong S4; hoặc một tình huống thuận lợi hiếm gặp. Ép 24 thành **mục tiêu tối thiểu** của mọi Sprint sẽ biến một quan sát thuận lợi thành áp lực cơ học.

### 10.2. Tại sao không tự động coi Sprint thấp nhất là thất bại?

S5 hoàn tất 16 points có thể vì nhóm ưu tiên xử lý một lỗi quan trọng không được đo bằng điểm, giữ chất lượng hoặc giải quyết rủi ro. Velocity thấp hơn chỉ là **tín hiệu để hỏi**, không tự chứng minh kém hiệu quả.

### 10.3. Có nên vẽ đường xu hướng?

Có thể vẽ chuỗi velocity để phát hiện thay đổi đáng chú ý, nhưng tránh:

- Diễn giải mọi dao động là xu hướng.
- Đặt mục tiêu đường phải tăng đều qua thời gian.
- So sánh đường giữa các nhóm có scale khác nhau.
- Gán chắc nguyên nhân chỉ bằng hình dạng biểu đồ.

Velocity của một nhóm khỏe mạnh **không cần tăng vô hạn**. Nếu các lát được chia nhất quán và nhóm giao giá trị bền vững, một mức velocity tương đối ổn định có thể hoàn toàn hợp lý.

## 11. Forecast cho Sprint tới bằng velocity và hiểu biết bối cảnh

Giả sử S6 có những PBI đã đủ hiểu:

| PBI ứng viên | Điểm nội bộ |
| --- | ---: |
| V1 – Tiếp tục video qua phiên đăng nhập | 5 |
| V2 – Nút “Học tiếp” | 3 |
| B2 – Sửa hiển thị lỗi nộp bài | 3 |
| V3 – Đồng bộ hai thiết bị | 8 |
| O1 – Cải thiện telemetry cho nộp bài | 2 |
| **Tổng ứng viên** | **21** |

Nhóm có trung bình quá khứ khoảng **20 points**, nhưng một thành viên sẽ nghỉ phép và có sự cố đang theo dõi. Một forecast thực tế không phải “21 gần 20 nên chắc chắn làm xong”. Nhóm cần xem **Sprint Goal, capacity, thứ tự ưu tiên, phụ thuộc, kích thước PBI 8 points và thời gian kiểm thử**.

### 11.1. Cách trao đổi trong Sprint Planning

- **Product Owner** trao đổi vì sao các PBI có giá trị, lựa chọn và thứ tự ưu tiên.
- **Developers** xem dữ liệu trước đây, capacity, DoD, phụ thuộc và chọn những PBIs họ cho là khả thi.
- Cả Scrum Team hình thành **Sprint Goal**, Developers lập **Sprint Backlog** và kế hoạch.
- Nếu một PBI 8 points nhiều bất định, có thể **chia dọc** hoặc hoãn một phần để giữ mục tiêu rõ.

Một lựa chọn minh họa có thể là **V1 (5), V2 (3), B2 (3), O1 (2)** = **13 points**, thay vì kéo cả V3 8 points khi capacity và phụ thuộc chưa chắc chắn. Điều đó **không có nghĩa nhóm phải đạt 13 điểm mới thành công**; điều cần xem là Sprint Goal và Increment đạt DoD.

### 11.2. Một forecast nên trình bày thế nào?

> “Lịch sử gần đây trung bình 20 points/Sprint, với dải quan sát 16–24 trong năm Sprint. Sprint tới capacity thấp hơn và V3 có rủi ro tích hợp. Developers đang cân nhắc ưu tiên lát V1/V2 và sửa lỗi nộp bài để đạt Sprint Goal; phạm vi còn lại sẽ được thích ứng khi có thông tin mới. Đây là kế hoạch dựa trên dữ liệu, không phải bảo đảm hoàn tất một số điểm cố định.”

Đây là cách trình bày trung thực hơn nhiều so với “S6 bắt buộc đạt 24 points”.

## 12. Forecast nhiều Sprint: phép tính thô và điều nó không chứng minh

Giả sử Product Backlog có một nhóm PBI **đã được ước lượng tương đối theo thang hiện tại**, với tổng **70 points**, và velocity lịch sử trung bình 20 points/Sprint.

Phép tính minh họa:

\[
\frac{70}{20}=3{,}5\ \text{Sprint}
\]

Nếu cần số Sprint trọn để hoàn tất toàn bộ phạm vi **theo giả định ổn định hoàn toàn**, phép làm tròn lên cho **khoảng bốn Sprint**.

**Không nên phát biểu:** “Chắc chắn release trong bốn Sprint” hoặc “4 Sprint là deadline mà nhóm đã hứa.”

### 12.1. Giả định ẩn trong phép chia

- Tổng backlog **70 points** tương đối ổn định; không thêm/bỏ phạm vi lớn.
- Các PBI được ước lượng bằng **thang nhất quán** và đủ rõ.
- Velocity sắp tới đủ giống lịch sử.
- Sprint có độ dài và năng lực gần giống nhau.
- Không xuất hiện phụ thuộc, sự cố hoặc ràng buộc mới đáng kể.
- DoD và điều kiện chất lượng không bị thay.
- Mọi PBI đều có thể hoàn tất/tích hợp theo từng phần, không còn một khối công việc “gần xong” lớn.
- Release có điều kiện riêng; hoàn tất các PBI chưa tự đồng nghĩa đã mở tới người dùng.

### 12.2. Vì sao cần nói về phạm vi và mức bất định?

Nếu backlog có các PBI ước lượng rất thô hoặc các yêu cầu mới xuất hiện theo phản hồi học viên, tổng **70 points** có thể thay đổi. Forecast tốt phải nhắc **điều kiện đổi dự báo** và những lựa chọn điều chỉnh giá trị.

Một câu báo cáo tốt:

> “Với phạm vi 70 points được hiểu hiện tại và dữ liệu lịch sử của nhóm, mốc khoảng bốn Sprint là một phép tính thô để thảo luận. Chúng tôi sẽ cập nhật sau mỗi Sprint khi backlog, capacity và rủi ro rõ hơn. Chúng ta có thể ưu tiên release một lát có giá trị trước khi toàn bộ 70 points Done.”

### 12.3. Không biến dải quá khứ thành xác suất tùy tiện

Nếu năm Sprint nằm trong 16–24 points, không thể khẳng định “với 90% khả năng nhóm sẽ đạt 16–24”. Muốn dự báo có xác suất cần **mô hình, dữ liệu phù hợp, giả định và kiểm định** rõ, đồng thời đủ số quan sát và cách xử lý biến động.

Một biểu đồ hoặc công cụ Monte Carlo không tự làm forecast đáng tin nếu đầu vào thiếu nhất quán hoặc ít dữ liệu.

## 13. Dự báo khi có deadline thực: thương lượng phạm vi, không ép points

Một số mốc là thật: quy định có hiệu lực, sự kiện ra mắt, hợp đồng, thay đổi nền tảng bên ngoài. **Agile không xóa deadline thực tế.** Vấn đề là **không biến estimate thành nghĩa vụ hoàn tất mọi scope bất kể thông tin mới**.

### Ví dụ: cần ra mắt tính năng “Học tiếp” trước ngày khai giảng

Tổ chức có mốc khai giảng cố định. Backlog gồm:

- **Bắt buộc cho trải nghiệm cốt lõi:** mở lại video có quyền, dữ liệu đúng, xử lý lỗi.
- **Rất có giá trị:** liên kết “Học tiếp” trên trang chủ.
- **Có thể trì hoãn:** đồng bộ offline phức tạp, thống kê nâng cao.
- **Điều kiện không được bỏ:** bảo mật, quyền truy cập, kiểm thử và khả năng vận hành liên quan.

Thảo luận phù hợp:

1. Xác định **mốc cố định và lý do**, ai có thẩm quyền.
2. Xếp thứ tự **kết quả quan trọng nhất**.
3. Dùng velocity/capacity/flow data để thảo luận khả thi và bất định.
4. Chia lát có thể dùng và **release sớm** khi đạt DoD/điều kiện release.
5. Nếu dữ liệu cho thấy toàn bộ phạm vi không khả thi, **điều chỉnh phạm vi hoặc phương án phát hành**.
6. Nếu rủi ro vẫn cao, thông báo sớm lựa chọn và tác động, không đến ngày cuối mới thừa nhận.

**Không nên lựa chọn:** bỏ kiểm thử quyền, tăng điểm ước lượng để che rủi ro, ép làm thêm giờ liên tục hoặc buộc nhóm cam kết điều chưa có bằng chứng.

### 13.1. Cam kết đúng trong Scrum

Trong Scrum, **Sprint Goal** là commitment gắn với Sprint Backlog. Developers làm việc hướng mục tiêu, kiểm tra và thích ứng mỗi ngày. Việc chọn các PBI trong Sprint Planning là **forecast về công việc** để đạt mục tiêu, không phải một hợp đồng phải hoàn tất từng PBI bằng mọi giá.

Nếu công việc bất ngờ, Scrum Team trao đổi và thích ứng trong giới hạn Sprint Goal và DoD. Velocity **không thay thế** trách nhiệm tạo Increment có giá trị và minh bạch rủi ro.

## 14. Story points và công việc không dự kiến: tránh điểm mù

Trong phát triển thực tế, nhóm không chỉ làm user stories dự kiến:

- Lỗi production hoặc sự cố khẩn.
- Kiểm thử hồi quy và bảo vệ dữ liệu.
- Bảo trì môi trường CI.
- Review, hỗ trợ nhóm khác và gỡ trở ngại.
- Đào tạo, giảm phụ thuộc một người, chia sẻ kiến thức.
- Refactoring cần thiết cho một lát giá trị.
- Phát hiện yêu cầu mới và trao đổi với người dùng.

Nếu velocity chỉ đếm một số PBI, nhiều công việc thiết yếu **không hiện thành points**. Không thể từ đó kết luận những thành viên hỗ trợ production ít đóng góp.

### 14.1. Có nên cho bug hoặc technical work points?

Không có một quy tắc chung bắt buộc. Có thể:

- Nếu bug/technical work được quản lý như PBI có phạm vi rõ và đạt DoD, nhóm **có thể ước lượng** theo quy ước nhất quán.
- Nếu công việc nhỏ, thường xuyên hoặc khó dự báo, nhóm **có thể không dùng points**, mà xem capacity hoặc throughput/loại việc.
- Các việc kỹ thuật **bên trong một PBI** để đạt DoD không nên bị tính thêm points riêng chỉ để nhân đôi kết quả.
- Công việc khẩn cần được **hiển thị và tính đến khi forecast**, dù có hay không có points.

**Điều quan trọng:** công bố chính sách trước khi đọc velocity, không thay cách đếm giữa Sprint chỉ để con số đạt mục tiêu.

### 14.2. Ví dụ ảnh hưởng sự cố

S4 nhóm đạt 24 points; S5 chỉ 16. Nếu S5 có một sự cố dữ liệu lớn khiến Developers phải ưu tiên khắc phục, velocity thấp **không tự chứng minh năng lực giảm**. Sự cố có thể là công việc rất có giá trị để bảo vệ người dùng, dù không được ước lượng bằng points.

Nhóm cần xem **thời gian xử lý incident, mức độ rủi ro, chất lượng sau khắc phục, phụ thuộc và phần Product Goal bị ảnh hưởng**, không chỉ điểm Sprint.

## 15. Khi PBI được chia, đổi hoặc ước lượng lại

Quy ước điểm cần đủ linh hoạt khi học được điều mới, nhưng tránh làm số liệu bị thao túng.

### 15.1. Trước Sprint

Nếu một PBI từ 8 được làm rõ và tách thành hai lát 3 và 5, nhóm có thể **ước lượng lại theo phạm vi mới**, xác nhận mỗi lát có thể sử dụng và đạt DoD. Đừng cố bắt tổng điểm mới phải bằng chính xác 8 bằng mọi giá: ước lượng tương đối không phải quy tắc bảo toàn số học.

Tuy nhiên, cần **ghi nhận thay đổi phạm vi**, để forecast và lịch sử không bị diễn giải sai.

### 15.2. Trong Sprint

Nếu phát hiện PBI quá lớn hoặc phụ thuộc không giải quyết được:

- Developers thảo luận với PO về điều chỉnh **phạm vi Sprint Backlog** mà vẫn hướng Sprint Goal.
- Có thể tách một lát **thật sự có thể Done** và đưa phần còn lại về Product Backlog để sắp xếp lại.
- Ghi points cho phần **thật sự đã đạt DoD**, theo ước lượng phạm vi rõ của lát mới; không đếm trùng phần chưa Done.
- Không tạo một ticket “đã làm 70%” rồi gán điểm để hợp thức hóa tiến độ.

### 15.3. Sau Sprint

Không nên tùy tiện **điều chỉnh points của PBI đã Done** để giải thích vì sao Sprint “phải đạt chỉ tiêu”. Nếu ước lượng sai, hãy **học từ giả định sai** và cập nhật cách ước lượng hoặc bộ tham chiếu cho tương lai.

### 15.4. Khi nhóm đổi thang điểm

Nếu nhóm chuyển từ thang 1–2–3–5–8 sang thang khác hoặc đổi cách hiểu points, các velocity trước/sau **không còn so trực tiếp như cùng một đơn vị**. Cần chú thích mốc thay đổi, tạo baseline mới và tránh lấy tỷ lệ points giữa hai giai đoạn làm “tăng năng suất”.

## 16. Velocity và throughput: hai góc nhìn khác nhau

**Velocity** cộng đơn vị ước lượng của các PBI Done. **Throughput** đếm số mục Done trong một khoảng thời gian. Hai chỉ số đều là **đầu ra của hệ thống làm việc**, nhưng có cơ sở và sai lệch khác nhau.

### Ví dụ cùng một Sprint

| PBI đạt DoD | Story points |
| --- | ---: |
| A | 5 |
| B | 3 |
| C | 2 |
| D | 8 |
| **Tổng** | **18** |

- **Velocity:** 18 points trong Sprint.
- **Throughput:** 4 PBI trong Sprint.

Nếu Sprint sau nhóm chia một PBI lớn thành ba lát thật sự có giá trị và Done, throughput có thể tăng vì **đơn vị đếm nhỏ hơn** dù lượng kết quả không trực tiếp gấp ba. Tương tự, nếu nhóm đổi points của mọi PBI từ 5 thành 10, velocity tăng mà công việc thực tế không thay đổi.

### 16.1. Khi nào throughput phù hợp hơn?

Throughput hữu ích khi:

- Các work items được chia **tương đối đồng dạng và có chính sách Done rõ**.
- Nhóm muốn dự báo từ khả năng hoàn tất thay vì thảo luận points.
- Công việc đến liên tục, phù hợp quản lý luồng Kanban.
- Cần phát hiện tác động của WIP, blocked time và kích thước lô.

Nếu work items dao động từ thay một nhãn nhỏ đến xây phân hệ lớn, throughput đơn thuần có thể rất khó so sánh; hãy **phân loại việc hoặc cải thiện cách chia**.

### 16.2. Có phải phải chọn một trong hai?

Không. Nhóm có thể dùng cả hai nếu mỗi chỉ số giúp một quyết định khác nhau. Nhưng **đừng duy trì hai hệ ước lượng gây tốn thời gian** chỉ vì dashboard cần nhiều số. Nếu throughput và cycle time đã đủ hỗ trợ forecast, nhóm có thể không cần points.

## 17. Kết hợp cycle time, WIP và work item age để nhìn nguyên nhân

Velocity trả lời **“đã Done bao nhiêu điểm?”**. Nó không cho biết nhiều về **“đang chờ ở đâu, vì sao?”**

| Flow metric | Định nghĩa thực hành | Câu hỏi hỗ trợ |
| --- | --- | --- |
| **Cycle time** | Thời gian từ Started đến Done trong một Definition of Workflow thống nhất. | Một PBI thường mất bao lâu để hoàn tất? |
| **Lead time** | Thời gian từ mốc yêu cầu được xác định đến mốc hoàn tất theo chính sách nhóm. | Người dùng/stakeholder phải chờ bao lâu từ lúc có nhu cầu? |
| **WIP** | Số mục đã bắt đầu nhưng chưa Done. | Có quá nhiều việc dở khiến luồng bị nghẽn không? |
| **Work item age** | Tuổi của mục **chưa Done** tính từ Started. | Mục nào có nguy cơ nằm quá lâu? |
| **Blocked time** | Thời gian mục không thể tiến vì phụ thuộc/điều kiện cụ thể. | Review, môi trường, quyết định hoặc kiểm thử đang chặn bao lâu? |
| **Throughput** | Số mục đạt Done trong khoảng quan sát. | Hệ thống hoàn tất bao nhiêu mục thực tế? |
| **Velocity** | Tổng points của các PBI đạt DoD trong Sprint. | Dữ liệu quá khứ hỗ trợ forecast bằng points ra sao? |

### 17.1. Ví dụ velocity giảm vì hàng chờ

Một nhóm có ba PBI 5, 8 và 8 points; cuối Sprint chỉ PBI 5 Done, hai PBI 8 points đang chờ review và kiểm thử. Velocity Sprint = **5**.

Điều cần điều tra không phải “ai lười” mà là:

- Các PBI 8 có quá lớn chưa chia được không?
- Review có bị đầy WIP?
- Môi trường kiểm thử đã sẵn sàng?
- Các điểm phụ thuộc có được nêu sớm?
- Developers có thể phối hợp hoàn tất thay vì bắt đầu thêm việc mới?

Nếu tập trung hỗ trợ các mục đang gần Done, Sprint sau có thể thấy points tăng vì **những PBI đã bắt đầu trước đó được hoàn tất**. Đó không hẳn là đột biến năng suất; cần nhìn **cycle time và work item age** để hiểu.

### 17.2. Little's Law chỉ dùng khi điều kiện phù hợp

Ở hệ thống đủ ổn định và cùng một ranh giới đo, quan hệ gần đúng:

\[
\overline{WIP} \approx \lambda \times \overline{CycleTime}
\]

với \(\lambda\) là **throughput trung bình theo cùng đơn vị thời gian**, không phải story points.

Ví dụ một luồng ổn định có trung bình **10 PBI đang dở** và hoàn tất **2 PBI/tuần**, thì thời gian trung bình trong luồng tương ứng khoảng:

\[
\overline{CycleTime}\approx\frac{10}{2}=5\ \text{tuần}
\]

Đây là ví dụ minh họa về quan hệ cấp hệ thống, **không dự báo một story cụ thể chắc chắn mất năm tuần**. Nếu WIP tăng liên tục, work items khác cỡ hoặc hệ thống không ổn định, phép suy luận trực tiếp có thể gây hiểu nhầm.

### 17.3. SLE trong Kanban khác deadline cá nhân

**Service Level Expectation (SLE)** là kỳ vọng dựa trên dữ liệu về thời gian một mục có thể hoàn tất, thường thể hiện bằng **khoảng thời gian và tỷ lệ mục lịch sử**.

Ví dụ minh họa: “Trong mẫu lịch sử tương thích, 85% PBI loại này đạt Done trong tối đa 8 ngày làm việc”. Đây là **kỳ vọng để theo dõi rủi ro và quản lý luồng**, không phải lời hứa mỗi cá nhân phải xong trước ngày thứ tám.

## 18. Từ velocity tới phạm vi release: cần nhìn giá trị và bất định

Một Product Backlog có thể chứa 100 points, nhưng không phải 100 points đều có giá trị ngang nhau hoặc phải Done cùng lúc mới có thể release.

### Ví dụ Product Goal “Học tiếp”

| Nhóm phạm vi | Giá trị/ràng buộc | Cách quyết định |
| --- | --- | --- |
| **Khôi phục vị trí video đúng quyền** | Trải nghiệm cốt lõi, không được sai dữ liệu. | Ưu tiên một lát đầu cuối đạt DoD. |
| **Đường vào “Học tiếp” rõ trên trang chủ** | Giúp người học tìm lại bài nhanh. | Có thể đưa sớm để nhận phản hồi. |
| **Đồng bộ đa thiết bị** | Có ích khi người học dùng nhiều thiết bị. | Ưu tiên sau khi hiểu mức nhu cầu và rủi ro. |
| **Offline** | Phù hợp một số đối tượng/môi trường. | Chỉ đầu tư khi có bằng chứng giá trị và năng lực vận hành. |
| **Báo cáo chi tiết cho giảng viên** | Có thể phục vụ mục tiêu khác. | Không mặc định gộp với release đầu. |

Velocity giúp cuộc trao đổi **liệu một số lát có thể hoàn tất trong thời gian dự kiến**. Nó không quyết định **lát nào đáng làm**. Đó là cuộc trao đổi về Product Goal, giá trị, rủi ro và thứ tự Product Backlog.

### 18.1. Phân biệt Done – Deployed – Released – Feedback Observed

~~~mermaid
flowchart LR
    A["PBI được làm rõ và ước lượng"] --> B["Started / In Progress"]
    B --> C["Đạt DoD: Increment có thể sử dụng"]
    C --> D["Deployed: đã đưa lên môi trường"]
    D --> E["Released: mở cho nhóm người dùng"]
    E --> F["Feedback Observed: có dữ liệu/phản hồi"]
    F --> G["Cập nhật Product Backlog / quyết định"]
~~~

Dòng chảy trên chỉ là **mô hình minh họa**: trong thực tế có thể deploy trước khi hoàn tất bật tính năng hoặc kiểm thử theo pipeline, và các trạng thái có thể được thiết kế khác. Quan trọng là **không nhập bốn khái niệm thành một**.

Velocity thường tập trung vào mốc **Done** theo quy ước của nhóm. Nếu Done đạt nhanh nhưng release luôn chờ ba tuần và không ai xem phản hồi, velocity tăng vẫn **chưa cải thiện vòng học hỏi của sản phẩm**.

## 19. Kết hợp Velocity với chất lượng và outcome

**Số đo Agile tốt hỗ trợ quyết định, không chỉ quản lý đầu ra.** Một bảng nhìn đủ cần cân bằng ít nhất ba góc:

| Góc nhìn | Câu hỏi | Tín hiệu gợi ý |
| --- | --- | --- |
| **Khả năng hoàn tất/flow** | Phần mềm có di chuyển tới Done đều và ít tắc không? | Velocity, throughput, cycle time, WIP, work item age. |
| **Chất lượng và an toàn** | Thay đổi có đúng, bảo mật và vận hành ổn không? | Lỗi sau release, sự cố nghiêm trọng, test failure, DoD, khả năng khôi phục. |
| **Giá trị và phản hồi** | Người dùng có làm được điều họ cần và đạt kết quả tốt hơn không? | Tỷ lệ hoàn tất tác vụ, phản hồi định tính, giảm lỗi sử dụng, mức sử dụng đúng mục đích. |

### 19.1. Ví dụ “velocity tăng nhưng sản phẩm xấu đi”

Một nhóm tăng từ 20 lên 30 points/Sprint sau khi bỏ kiểm thử tích hợp và chuyển DoD thành “đã merge code”. Lỗi sau release tăng và việc khắc phục chiếm nhiều Sprint tiếp theo.

Không thể coi đó là cải tiến velocity có ý nghĩa. Nhóm đã **đổi định nghĩa đầu ra**, phá điều kiện chất lượng và chuyển công việc sang tương lai.

### 19.2. Ví dụ “velocity thấp nhưng kết quả có giá trị”

Nhóm giảm từ 20 xuống 14 points khi ưu tiên sửa một lỗi phân quyền nghiêm trọng, đồng thời viết kiểm thử hồi quy và cải thiện kiểm soát truy cập. Nếu lỗi được xử lý an toàn và giảm rủi ro người dùng, việc chỉ nhìn 14 points có thể **đánh giá thấp đóng góp thực tế**.

### 19.3. Chỉ số không tự tạo nguyên nhân

Nếu velocity tăng và lỗi giảm cùng thời điểm, chưa thể kết luận **chính velocity tăng gây giảm lỗi**. Có thể nhóm đổi loại việc, cải thiện pipeline, tích hợp sớm hoặc có các yếu tố khác. Cần phân tích bối cảnh và cơ chế tác động.

## 20. Tác hại của việc biến velocity thành KPI xếp hạng

Velocity dễ bị sai lệch khi bị biến thành **chỉ tiêu thưởng phạt**.

### Vòng lặp áp lực số liệu

~~~mermaid
flowchart TD
    A["Áp mục tiêu points bắt buộc / xếp hạng nhóm"] --> B["Tăng áp lực làm đẹp con số"]
    B --> C["Nâng điểm ước lượng hoặc chia ticket vụn"]
    B --> D["Giảm kiểm thử / đẩy việc khó sang Sprint sau"]
    C --> E["Velocity báo cáo tăng"]
    D --> E
    E --> F["Stakeholder tưởng năng lực đã tăng"]
    F --> A
    D --> G["Lỗi, rework và nợ kỹ thuật tăng"]
    G --> H["Khả năng giao giá trị giảm"]
~~~

Đây là một **rủi ro hành vi**, không phải khẳng định mọi nhóm bị đo đều chắc chắn gian lận. Nhưng khi con số trở thành mục tiêu, cách nhóm **định nghĩa, ước lượng và chia công việc** có thể thay đổi để đạt số mà không tạo giá trị.

### Những cách dùng sai thường gặp

| Cách dùng sai | Điều có thể xảy ra | Cách thay thế |
| --- | --- | --- |
| **So velocity giữa các nhóm.** | Thang points và DoD khác nhau; đánh giá không công bằng. | Đánh giá outcome, chất lượng và khả năng giao của từng nhóm theo bối cảnh. |
| **Dùng điểm làm KPI cá nhân.** | Giấu hỗ trợ cộng tác, tranh task, tăng points. | Feedback hiệu quả công việc dựa trên đóng góp, hành vi và kết quả có ngữ cảnh. |
| **Bắt velocity tăng qua từng Sprint.** | Thổi estimate hoặc hạ DoD. | Theo dõi ổn định, nút thắt và khả năng tạo giá trị. |
| **Lấy points làm năng suất tuyệt đối.** | Coi points là giờ hoặc sản lượng vật lý. | Chú thích đơn vị cục bộ và mục đích forecast. |
| **Chấm điểm cho PBI “80% Done”.** | Báo tiến độ ảo; làm mờ điều kiện hoàn tất. | Chỉ ghi Done khi đạt DoD theo chính sách nhất quán. |
| **Tăng estimate sau khi Done.** | Lịch sử thay đổi để đạt target. | Ghi bài học về bất định, cải thiện estimate tương lai. |
| **Tính thêm points cho từng task cùng PBI.** | Đếm trùng công việc tạo một kết quả. | Định nghĩa cấp đếm và loại bỏ double count. |
| **Đánh giá Scrum Master qua velocity tăng.** | Khuyến khích tối ưu số báo cáo hơn hiệu quả Scrum. | Xem khả năng tháo trở ngại, minh bạch và cải tiến kết quả nhóm. |
| **Coi velocity là deadline.** | Ép đội hứa phạm vi chưa đủ hiểu. | Forecast với giả định và lựa chọn phạm vi theo ưu tiên. |
| **Dùng points dự báo tiền lương/chi phí đơn lẻ.** | Gán đơn vị tiền/giờ không có cơ sở. | Dự toán chi phí từ năng lực, thời gian, rủi ro và hợp đồng thật. |

### Câu hỏi giúp chuyển cuộc trò chuyện

Thay vì hỏi **“Tại sao nhóm chỉ làm 15 points?”**, hãy hỏi:

> “Có phần giá trị nào đã đạt DoD? Mục nào bị chặn? Điều gì nhóm học được? Nên điều chỉnh kế hoạch và cơ chế phối hợp thế nào để người dùng nhận giá trị sớm và an toàn hơn?”

## 21. Khi nào không nên dùng story points/velocity?

Có những trường hợp **chi phí ước lượng lớn hơn lợi ích**:

- Mục công việc nhỏ, tương đối đồng dạng và throughput/cycle time đã đủ hỗ trợ forecast.
- Công việc đến liên tục, khó chia theo Sprint nhưng có Definition of Workflow rõ.
- Nhóm mới đang biến points thành tranh luận dài mà không học thêm điều gì.
- Phần lớn công việc là incident/maintenance với độ bất định cao và phạm vi biến đổi nhanh.
- Stakeholder dùng velocity để gây áp lực, khiến dữ liệu bị biến dạng.
- Nhóm không thể duy trì quy ước estimate ổn định, hoặc vừa thay cấu trúc lớn cần baseline mới.

### 21.1. No-estimates không có nghĩa không dự báo

Một nhóm có thể bỏ points nhưng vẫn:

1. Chia việc thành mục đủ nhỏ và có DoD.
2. Theo dõi Started, Done, cycle time, WIP, blocked time.
3. Dùng throughput lịch sử cho loại việc tương tự.
4. Thảo luận scope, rủi ro, phụ thuộc và capacity.
5. Cập nhật forecast theo dữ liệu mới.

**Không cần story points** khác hoàn toàn với **không biết đang làm gì hoặc khi nào có thể nhận kết quả**.

### 21.2. Đo lường dòng công việc cũng có thể bị thao túng

Nếu chỉ thưởng theo throughput, nhóm có thể chia ticket vụn để tăng số Done. Nếu chỉ thưởng theo cycle time, nhóm có thể trì hoãn thời điểm bấm Started. Vì thế, bất kỳ số đo nào cũng cần **định nghĩa rõ, minh bạch và đi cùng chất lượng/outcome**.

## 22. Dùng velocity trong Sprint Planning mà không làm hại Sprint Goal

Một quy trình thực dụng, không biến Sprint Planning thành bài thi số học:

1. **Xem Product Goal và Sprint Goal ứng viên.** Vì sao những kết quả này quan trọng cho người dùng?
2. **Xem Product Backlog có thứ tự.** PO làm rõ những PBI cần thiết để đạt mục tiêu.
3. **Xem dữ liệu đã hoàn tất của nhóm.** Velocity gần đây, loại công việc, điểm nghẽn và mức bất định.
4. **Xem capacity Sprint tới.** Nghỉ phép, trực sự cố, phụ thuộc, lịch vận hành và công việc chất lượng.
5. **Làm rõ và chia những PBI quá lớn.** Tránh kéo việc không thể kiểm chứng.
6. **Developers chọn những PBI mà họ cho là khả thi** để đạt Sprint Goal.
7. **Lập kế hoạch** bao gồm kiểm thử, tích hợp, DoD và cách xử lý phụ thuộc.
8. **Kiểm tra và thích ứng trong Sprint** khi học được thông tin mới, không coi con số points là bất biến.

### Lời thoại minh họa

**Product Owner:** “Mục tiêu là học viên mở lại được bài đang học. Tôi muốn V1 và V2 sớm vì có phản hồi lớp thử tuần sau.”

**Developer A:** “Lịch sử khoảng 20 points/Sprint, nhưng hai người sẽ hỗ trợ sự cố. V3 có rủi ro đồng bộ lớn, tôi đề xuất không kéo V3 ngay.”

**Developer B:** “V1 đã được làm rõ gồm phân quyền, lỗi và kiểm thử. Chúng ta có thể hoàn tất V1/V2 cùng sửa lỗi nộp bài, rồi xem còn năng lực cho lát khác.”

**Scrum Master:** “Review đang là nút thắt; hãy thống nhất cách hỗ trợ PR gần Done thay vì mở thêm nhiều việc.”

**PO:** “Tôi đồng ý ưu tiên mục tiêu 'Học tiếp' có thể dùng được. Nếu xuất hiện sự cố, chúng ta trao đổi tác động sớm và điều chỉnh phạm vi minh bạch.”

Không ai phải nói “Chúng tôi cam kết đúng 20 points”. Cuộc trao đổi sử dụng **velocity như tín hiệu**, nhưng quyết định dựa trên **mục tiêu, chất lượng, capacity và rủi ro**.

## 23. Các trường hợp biên cần chú ý khi đọc velocity

### 23.1. Sprint có PBI lớn hoàn tất sau nhiều Sprint

Nếu một PBI 13 points được bắt đầu ở S1 và chỉ đạt DoD ở S3, theo quy ước chỉ tính Done, S1/S2 có thể không ghi điểm cho PBI ấy và S3 ghi 13. Đồ thị velocity dao động dù công việc đã được thực hiện rải qua thời gian.

**Hướng cải thiện:** chia lát nhỏ có giá trị và xem cycle time/WIP thay vì gán điểm hoàn tất một phần.

### 23.2. Nhóm mới chưa có lịch sử

Không có dữ liệu đáng tin để tính velocity trung bình. Hãy sử dụng PBI nhỏ, hiểu biết về capacity, giả định công khai và vài Sprint đầu làm mốc quan sát. **Đừng lấy velocity của nhóm khác làm chuẩn** để ép nhóm mới.

### 23.3. Đổi thành viên hoặc kỹ năng quan trọng

Nếu một người nắm toàn bộ hạ tầng nghỉ dài ngày, lịch sử cũ có thể không còn phản ánh khả năng giải quyết phụ thuộc. Dùng forecast thận trọng, chia sẻ kiến thức và xử lý nút thắt; **không quy đổi số người tuyến tính thành points**.

### 23.4. Nâng Definition of Done

Khi nhóm thêm kiểm thử bảo mật bắt buộc hoặc cải thiện chuẩn chất lượng, velocity có thể thấp tạm thời. Không nên coi việc bảo vệ người dùng là “năng suất giảm” và bỏ điều kiện đó để số tăng. Chú thích mốc đổi DoD và đánh giá tổng thể chất lượng/flow.

### 23.5. Thay Sprint length

Một Sprint một tuần và Sprint hai tuần **không có cùng cửa sổ**. Không so điểm tuyệt đối như cùng điều kiện; nếu cần dùng dữ liệu lịch sử, phải phân đoạn hoặc điều chỉnh mô hình với giả định rõ. Dù vậy, **đơn giản nhân đôi points từ một tuần sang hai tuần** không tự đảm bảo dự báo.

### 23.6. Nhiều nhóm cùng làm một sản phẩm

Mỗi nhóm có thể có points riêng cho mục đích lập kế hoạch. Nếu nhiều Scrum Teams cùng một sản phẩm, cần giữ Product Goal/Product Backlog/Product Owner và DoD chung theo Scrum; **không cần đồng nhất story points** để kiểm soát value. Muốn dự báo liên nhóm cần xử lý phụ thuộc, phạm vi và số đo hệ thống thay vì chỉ cộng points khác thang.

### 23.7. Có defect hoặc incident nghiêm trọng

Incident có thể làm Sprint Goal gặp rủi ro. Ghi minh bạch, xử lý theo thẩm quyền và chính sách, sau đó xem ảnh hưởng tới forecast. Việc ứng cứu rủi ro quan trọng **không trở thành vô giá trị vì không được chấm points**.

## 24. Mẫu báo cáo velocity không gây hiểu nhầm

~~~text
NHÓM / SẢN PHẨM:
  Nhóm sở hữu dữ liệu; người đọc và mục đích forecast.

KHOẢNG ĐO:
  Sprint nào, độ dài, ngày bắt đầu/kết thúc.

QUY ƯỚC:
  Điểm do nhóm ước lượng, phạm vi PBI được tính, chỉ tính Done theo DoD.
  Có thay đổi scale/DoD/chính sách đếm từ kỳ trước không?

DỮ LIỆU QUÁ KHỨ:
  S1=18, S2=22, S3=20, S4=24, S5=16.
  Trung bình=20; trung vị=20; dải quan sát=16–24.

BỐI CẢNH:
  Nghỉ phép, công việc khẩn, phụ thuộc, môi trường kiểm thử, PBI lớn.

SPRINT GOAL VÀ GIÁ TRỊ:
  Kết quả người dùng đang ưu tiên; Increment đã đạt DoD.

FORECAST HIỆN TẠI:
  Phạm vi ứng viên, giả định, bất định, lựa chọn chia lát hoặc giảm scope.
  Không diễn đạt thành cam kết tuyệt đối hoặc KPI points.

CHỈ SỐ BỔ TRỢ:
  WIP, cycle time, blocked time, lỗi/sự cố, phản hồi người dùng.

ĐIỀU HỌC ĐƯỢC:
  Điều gì làm dự báo lệch? Đã tháo trở ngại nào?

HÀNH ĐỘNG TIẾP:
  Điều chỉnh backlog, kiểm thử, cách chia lát, chính sách luồng hoặc forecast.
~~~

### 24.1. Một cách trình bày ngắn gọn với stakeholder

> “Nhóm sử dụng points như thang tương đối nội bộ. Năm Sprint gần nhất hoàn tất 16–24 points, trung bình 20. Sprint tới có ít capacity hơn và một PBI còn rủi ro tích hợp; chúng tôi sẽ ưu tiên lát 'Học tiếp' đạt DoD và cập nhật forecast sau khi thử tích hợp. Những con số này không dùng để so sánh nhóm khác hoặc đánh giá cá nhân. Chúng ta cũng theo dõi lỗi, cycle time và phản hồi học viên để biết việc giao hàng thực sự có hiệu quả hay không.”

## 25. Bài tập thực hành: tính velocity và dự báo có điều kiện

Một nhóm Scrum xây sản phẩm **đặt lịch tư vấn học tập** với Sprint hai tuần, dùng story points ước lượng tương đối. DoD gồm kiểm thử đặt lịch không trùng, quyền truy cập, xử lý lỗi và tích hợp.

Dữ liệu năm Sprint trước:

| Sprint | PBI đã Done (points) | PBI chưa Done | Ghi chú |
| --- | --- | --- | --- |
| **S1** | 5 + 3 + 8 | 5 | Nhịp thông thường. |
| **S2** | 8 + 5 + 3 + 2 | 8 | Một PR chờ review. |
| **S3** | 5 + 8 + 5 + 3 | 13 | Phát hiện phụ thuộc với hệ thống lịch. |
| **S4** | 8 + 5 + 8 | 3 | Một lỗi production cần khắc phục. |
| **S5** | 3 + 5 + 5 + 2 | 8 | Một người nghỉ phép; kiểm thử tích hợp chậm. |

Sprint S6 đang cân nhắc:

| PBI | Điểm nội bộ | Phạm vi |
| --- | ---: | --- |
| **A** | 5 | Người học xem các khung giờ có quyền đặt. |
| **B** | 8 | Đặt một lịch hợp lệ và ngăn trùng trong đồng thời. |
| **C** | 3 | Hiển thị lỗi rõ khi khung giờ đã có người đặt. |
| **D** | 5 | Gửi xác nhận sau khi đặt lịch thành công. |
| **E** | 8 | Đồng bộ lịch với hệ thống ngoài còn thiếu hợp đồng. |

S6 có hai người nghỉ một phần Sprint; PBI E còn phụ thuộc vào đối tác. Product Owner muốn người học **đặt được một lịch hợp lệ và thấy kết quả rõ ràng** để thử với một lớp nhỏ.

### Câu hỏi

1. Tính velocity của từng Sprint S1–S5, không tính PBI chưa Done.
2. Tính trung bình, trung vị và dải quan sát. Có nên gọi dải đó là khoảng tin cậy 90% không?
3. Nếu cộng tất cả PBIs A–E, tổng points là bao nhiêu? Có nên kéo hết chỉ vì gần trung bình lịch sử?
4. Xác định Sprint Goal có ý nghĩa cho S6 và đề xuất phạm vi ứng viên.
5. PBI B có những điều kiện chất lượng nào bắt buộc ngay trong lát đầu?
6. PBI E chưa rõ hợp đồng ngoài. Nên làm gì trước khi cố chốt estimate?
7. S6 hoàn tất A, B và C; D chưa Done. Velocity là bao nhiêu? Có được tính “D 90% x 5 points” không?
8. S6 gặp một sự cố an toàn dữ liệu không ước lượng bằng points. Nên diễn giải velocity ra sao?
9. Stakeholder yêu cầu S7 phải đạt 30 points vì “đội mạnh phải tăng đều”. Bạn sẽ trả lời thế nào?
10. Nếu dùng throughput thay velocity, cần bổ sung những định nghĩa/dữ liệu nào?
11. Đề xuất hai số đo flow, hai guardrails chất lượng và một outcome sản phẩm.
12. Viết một forecast hai đến ba câu cho stakeholder, có nêu giả định và mức bất định.

## 26. Hướng giải tham khảo

### 26.1. Tính điểm đã Done

- **S1:** 5 + 3 + 8 = **16**.
- **S2:** 8 + 5 + 3 + 2 = **18**.
- **S3:** 5 + 8 + 5 + 3 = **21**.
- **S4:** 8 + 5 + 8 = **21**.
- **S5:** 3 + 5 + 5 + 2 = **15**.

Tổng:

\[
16+18+21+21+15=91
\]

Trung bình:

\[
\bar{V}=\frac{91}{5}=18{,}2\ \text{points/Sprint}
\]

Sắp xếp: **15, 16, 18, 21, 21**, nên **trung vị là 18**, **dải quan sát 15–21**.

Không được gọi 15–21 là **khoảng tin cậy 90%**. Đây chỉ là giá trị nhỏ nhất/lớn nhất trong năm quan sát, với các bối cảnh khác nhau.

### 26.2. Tổng phạm vi và Sprint Goal

A–E có tổng:

\[
5+8+3+5+8=29\ \text{points}
\]

29 points **lớn hơn nhiều** trung bình 18,2 của năm Sprint. Với nghỉ phép và phụ thuộc ngoài, kéo tất cả vào Sprint như cam kết là không hợp lý.

**Sprint Goal ứng viên:**

> “Người học có thể chọn một khung giờ được phép, đặt một lịch không bị trùng và nhận phản hồi đặt lịch rõ để nhóm thử luồng đầu cuối với một lớp học viên.”

Các PBI **A (5), B (8), C (3)** = **16 points** có thể tạo một lát đầu cuối theo giả định dữ liệu và hệ thống đã đủ rõ. Developers phải đánh giá lại rủi ro thực tế; không có quy tắc cứng rằng 16 chắc chắn hoàn tất.

PBI D có thể cân nhắc khi capacity/độ ưu tiên phù hợp, còn E nên được làm rõ hợp đồng và giá trị trước khi kéo vào.

### 26.3. Chất lượng không được hoãn của B

- Không tạo hai lịch trái quy tắc khi có hai yêu cầu cạnh tranh.
- Kiểm tra quyền đối với lịch và thông tin liên quan.
- Bảo toàn tính toàn vẹn dữ liệu và giao dịch.
- Xử lý lỗi và thử lại phù hợp, không thông báo thành công giả.
- Có kiểm thử các trường hợp biên quan trọng và tích hợp đạt DoD.

Không nên cắt “kiểm tra đồng thời” thành story sau nếu việc đặt lịch hợp lệ **bắt buộc ngăn trùng ngay từ đầu**.

### 26.4. Bất định của E

PBI E còn thiếu hợp đồng hệ thống ngoài. Nhóm có thể:

- Xin tài liệu và làm rõ ranh giới dữ liệu, lỗi, quyền, SLA/phụ thuộc.
- Chạy spike tích hợp có thời hạn để giảm bất định.
- Chia thành lát đầu có khả năng kiểm chứng.
- Trình bày forecast với giả định và phương án không phụ thuộc E.

Không nên chọn một con số points rất lớn rồi coi mọi rủi ro đã được giải quyết.

### 26.5. S6 thực tế

Nếu A, B, C đạt DoD và D chưa Done, theo quy ước:

\[
V_{S6}=5+8+3=16\ \text{points}
\]

**Không** ghi 4,5 points cho D vì “90% đã làm”, không ghi thêm points cho các task nội bộ. Nếu sự cố quan trọng chiếm capacity, cần minh bạch đóng góp khắc phục và tác động tới Sprint Goal; velocity không mô tả đầy đủ giá trị của Sprint.

### 26.6. Trả lời yêu cầu “30 points là chỉ tiêu”

> “Points là thang tương đối nội bộ, không phải năng suất tuyệt đối. Năm Sprint gần nhất nhóm Done 15–21 points, trung bình 18,2 trong những điều kiện khác nhau. Ép mục tiêu 30 sẽ không làm capacity tăng tự động và có thể khuyến khích hạ DoD hoặc thổi estimates. Chúng tôi đề xuất tập trung vào Increment đặt lịch an toàn, quan sát blockers, chất lượng và phản hồi học viên, rồi cập nhật dự báo khi có thêm dữ liệu.”

### 26.7. Throughput, flow và outcome

Nếu dùng throughput, cần thống nhất **đơn vị PBI**, điểm Started/Done, chính sách tách/gộp và phân loại công việc; xem số PBI Done, WIP, cycle time, đặc biệt với PBI quá khác kích thước.

Tín hiệu gợi ý:

- **Flow:** cycle time từ Started tới Done, blocked time chờ review/hệ thống ngoài.
- **Chất lượng:** số lịch trùng trái quy tắc, số sự cố truy cập dữ liệu trái quyền hoặc lỗi xác nhận.
- **Outcome:** tỷ lệ học viên hoàn tất được một lịch tư vấn hợp lệ trong bài thử/luồng thật có định nghĩa rõ.

### 26.8. Forecast mẫu

> “Nhóm có velocity trung bình 18,2 points/Sprint trên năm Sprint, dải quan sát 15–21, không phải khoảng xác suất bảo đảm. Do S6 nghỉ phép và E phụ thuộc hợp đồng ngoài, Developers sẽ xem khả năng hoàn tất lát A–B–C trước; D/E được cân nhắc theo capacity và thông tin mới. Chúng tôi giữ kiểm thử không trùng lịch, phân quyền và DoD, cập nhật phạm vi sau khi có kết quả tích hợp và phản hồi học viên.”

## 27. Tự kiểm tra kiến thức

**Câu 1.** Velocity là gì khi nhóm dùng story points?

**Đáp án:** Tổng points của những PBIs đạt DoD trong Sprint theo một quy ước nhất quán, dùng như tín hiệu lịch sử nội bộ cho dự báo và học hỏi.

**Câu 2.** Có thể dùng velocity nhóm A = 40 và nhóm B = 20 để kết luận A năng suất gấp đôi không?

**Đáp án:** Không. Story points không có đơn vị chung giữa các nhóm; phạm vi, thang ước lượng, DoD và bối cảnh có thể khác.

**Câu 3.** PBI 8 points đã code 90% nhưng chưa qua kiểm thử DoD. Có tính 7,2 points không?

**Đáp án:** Không theo quy ước chỉ ghi PBI Done. Cần hoàn tất, hoặc tách một lát có giá trị đạt DoD và ghi nhận minh bạch theo phạm vi mới không đếm trùng.

**Câu 4.** Scrum Guide có bắt buộc story points hoặc velocity không?

**Đáp án:** Không. Chúng là kỹ thuật tùy chọn để hỗ trợ ước lượng và dự báo.

**Câu 5.** Vì sao Planning Poker nên nghe người ước lượng điểm cao/thấp?

**Đáp án:** Khác biệt thường bộc lộ giả định về phạm vi, rủi ro hoặc DoD; việc chia sẻ giúp nhóm hiểu PBI thay vì chỉ thống nhất con số.

**Câu 6.** Nếu nhóm thường đạt 20 points/Sprint, có thể coi 20 là cam kết Sprint tới không?

**Đáp án:** Không. Đó là quan sát lịch sử; capacity, PBI, phụ thuộc và rủi ro khác có thể làm kết quả thay đổi. Sprint Goal và DoD vẫn là trọng tâm.

**Câu 7.** Velocity giảm khi nhóm ưu tiên sửa lỗi phân quyền khẩn. Có chắc nhóm làm việc kém hơn không?

**Đáp án:** Không. Phải xem giá trị bảo vệ người dùng, công việc không points, chất lượng và ảnh hưởng tới các mục khác.

**Câu 8.** Trung bình 20 và dải quan sát 16–24 qua năm Sprint có phải khoảng dự báo 90%?

**Đáp án:** Không. Chỉ là thống kê mô tả từ năm quan sát; không có mức xác suất được chứng minh.

**Câu 9.** Story points và giờ có phép quy đổi chung không?

**Đáp án:** Không. Points là thang tương đối nội bộ theo quy ước nhóm, không tự bằng giờ hoặc ngày công.

**Câu 10.** Khi nào throughput có thể phù hợp hơn velocity?

**Đáp án:** Khi các mục được chia tương đối đồng dạng, có Definition of Workflow rõ, dữ liệu Started/Done đáng tin và cần dự báo dòng công việc hơn là tranh luận points.

**Câu 11.** Vì sao cần xem cycle time và WIP cùng velocity?

**Đáp án:** Velocity không chỉ ra hàng chờ hoặc tuổi công việc. Cycle time/WIP giúp thấy nút thắt và nguyên nhân nhiều mục chưa Done.

**Câu 12.** Nếu nhóm tăng velocity bằng cách bỏ kiểm thử tích hợp, đó có phải cải tiến Agile không?

**Đáp án:** Không. Việc thay DoD để tăng điểm phá chất lượng và khiến số liệu không còn so sánh công bằng; cần bảo vệ Increment có thể sử dụng.

**Câu 13.** Product Owner có nên dùng velocity để ra thứ tự Product Backlog thay cho giá trị không?

**Đáp án:** Không. Velocity hỗ trợ dự báo khả thi; thứ tự backlog cần dựa trên Product Goal, giá trị, rủi ro, phụ thuộc và phản hồi thực tế.

**Câu 14.** Nếu chưa có lịch sử velocity, nhóm mới nên làm gì?

**Đáp án:** Chia lát nhỏ, trao đổi giả định/capacity, hoàn tất Increment rồi tích lũy dữ liệu của chính nhóm; không mượn points của nhóm khác làm năng suất chuẩn.

**Câu 15.** Một nhóm Kanban không dùng Sprint hoặc points có thể dự báo không?

**Đáp án:** Có. Có thể dùng throughput, cycle time, WIP, SLE và những giả định về loại việc và năng lực để đưa forecast có điều kiện.

## 28. Checklist dùng velocity có trách nhiệm

### Trước khi ước lượng

- [ ] Biết **câu hỏi ra quyết định** nào cần estimate; không ước lượng chỉ để lấp bảng báo cáo.
- [ ] Product Backlog Item gắn với hành vi/người dùng hoặc kết quả rõ ràng.
- [ ] Acceptance criteria đủ để thảo luận phạm vi, gồm lỗi/rủi ro thiết yếu.
- [ ] DoD và điều kiện chất lượng đã rõ; estimate không chỉ tính giờ code.
- [ ] Có reference stories phù hợp và thang points nội bộ được hiểu chung.
- [ ] Nếu PBI quá lớn/bất định, đã xem chia lát hoặc spike.
- [ ] Mọi người có thể nêu giả định khác nhau mà không bị ép theo cấp bậc.

### Khi ghi velocity

- [ ] Chỉ đếm PBI thật sự đạt Done theo quy ước và DoD.
- [ ] Không ghi một phần points cho việc “gần xong”.
- [ ] Không đếm trùng task hoặc PBI được tách/gộp.
- [ ] Các thay đổi thang points, cấu trúc nhóm, DoD và Sprint length được chú thích.
- [ ] Công việc khẩn, defect và cải tiến kỹ thuật được hiển thị, không bị xóa khỏi câu chuyện vì thiếu points.
- [ ] Không so points giữa các nhóm hoặc cá nhân.

### Khi dự báo

- [ ] Dùng **nhiều Sprint**, xem phân bố và các ngoại lệ, không chỉ Sprint cao nhất.
- [ ] Nêu capacity, nghỉ phép, phụ thuộc và loại việc sắp tới.
- [ ] Giữ giả định của phép tính và công bố mức bất định.
- [ ] Không tự gán mức tin cậy thống kê từ vài quan sát.
- [ ] Cân nhắc giảm phạm vi hoặc release một lát có giá trị thay vì ép toàn bộ scope.
- [ ] Sprint Goal và Product Goal vẫn quan trọng hơn mục tiêu points.

### Khi đánh giá cải tiến

- [ ] Nhìn thêm throughput, cycle time, WIP và blocked time.
- [ ] Kiểm tra lỗi sau release, bảo mật và chất lượng Increment.
- [ ] Thu phản hồi về hành vi/kết quả người dùng, không chỉ output.
- [ ] Không hạ DoD hoặc thổi estimate để tăng velocity.
- [ ] Dùng số liệu để hỗ trợ nhóm tháo trở ngại, không tạo bảng xếp hạng năng suất.
- [ ] Cập nhật forecast, backlog và cách làm khi thông tin mới xuất hiện.

Checklist là công cụ trao đổi, không phải quy trình phê duyệt bắt buộc cho mọi ước lượng nhỏ. **Mục tiêu là giúp nhóm quyết định và học tốt hơn.**

## 29. Ghi nhớ trọng tâm

- **Velocity là dữ liệu về công việc theo thang ước lượng nội bộ đã đạt DoD**, thường đo theo Sprint; nó không đo năng suất cá nhân hay giá trị sản phẩm.
- **Scrum không bắt buộc story points hoặc velocity.** Nhóm chọn kỹ thuật ước lượng nếu nó giúp ra quyết định thực tế.
- **Points là tương đối và phụ thuộc bối cảnh nhóm.** Không so velocity giữa các nhóm hoặc tự quy đổi points sang giờ.
- **Ước lượng nhằm phát hiện bất định và hỗ trợ lựa chọn.** Planning Poker hữu ích nhất khi phơi bày giả định khác nhau, không phải khi tìm con số “đúng tuyệt đối”.
- **Chia lát dọc trước khi cố ước lượng chính xác hơn.** Một PBI nhỏ, đủ dùng và có DoD rõ giúp giảm rủi ro và nhận phản hồi sớm.
- **Velocity chỉ tính công việc thật sự Done theo chính sách nhất quán.** Không tính phần trăm hoàn thành, không đếm trùng hoặc tăng điểm hồi tố để đạt KPI.
- **Dùng chuỗi nhiều Sprint và bối cảnh**, không lấy Sprint cao nhất làm mức phải đạt. Một dải quá khứ không phải khoảng tin cậy có xác suất.
- **Forecast là dự báo có điều kiện** từ scope, capacity, dữ liệu, phụ thuộc và rủi ro; không tự biến thành deadline hay cam kết mọi ticket.
- **Khi có mốc thật, thương lượng phạm vi và thứ tự giá trị**, không cắt kiểm thử, phân quyền hoặc tiêu chuẩn Done để chạy theo điểm.
- **Velocity cần đi cùng flow metrics, chất lượng và outcome.** Throughput, cycle time, WIP và work item age chỉ ra nút thắt mà tổng points không thấy.
- **No-estimates vẫn có thể dự báo** bằng dữ liệu luồng và chính sách rõ; không cần points nếu chi phí của chúng vượt lợi ích.
- **Đo lường là công cụ học hỏi và cải tiến hệ thống**, không phải mục tiêu buộc người khác tối ưu số báo cáo.

Khi sử dụng velocity, hãy luôn tự hỏi: **“Con số này giúp nhóm chúng ta đưa ra quyết định tốt hơn về giá trị, chất lượng và khả năng hoàn tất hay đang khiến mọi người phải bảo vệ một mục tiêu điểm số?”**. Dùng nó như một tín hiệu lịch sử có giới hạn, kết hợp việc chia lát nhỏ, phản hồi sớm và cải tiến dòng công việc, nhóm sẽ dự báo trung thực hơn và phát triển phần mềm thích ứng bền vững hơn.
