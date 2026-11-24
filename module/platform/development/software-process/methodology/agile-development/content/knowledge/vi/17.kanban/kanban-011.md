# Cải tiến luồng dựa trên dữ liệu và thử nghiệm

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **luồng công việc** (*workflow/flow*) và vì sao cải tiến Kanban phải hướng tới việc giao giá trị ổn định, không chỉ tăng số lượng công việc được bắt đầu.
2. Định nghĩa và đọc đúng các chỉ số **Work in Progress (WIP), throughput, cycle time và work item age**; biết khi nào cần quan sát lead time, phần trăm công việc bị chặn và Service Level Expectation (SLE).
3. Dùng bảng Kanban, biểu đồ luồng tích lũy (*Cumulative Flow Diagram – CFD*), biểu đồ cycle time và dữ liệu lịch sử để nhận diện **giả thuyết về điểm nghẽn**, thay vì vội kết luận từ một con số.
4. Thiết kế thử nghiệm cải tiến có **giả thuyết, thay đổi cụ thể, thời hạn quan sát, chỉ số thành công và giới hạn an toàn**.
5. Đánh giá kết quả thử nghiệm, phân biệt biến động tự nhiên với tác động có thể có của thay đổi; quyết định tiếp tục, điều chỉnh hoặc bỏ thử nghiệm.
6. Kết hợp quản lý luồng của Kanban với việc giao phần mềm tăng dần, user story, Scrum và thực hành kỹ thuật XP khi thích hợp.

## 1. Cải tiến luồng trong Kanban là gì?

Trong phát triển phần mềm, **luồng công việc** là cách các hạng mục đi từ một điểm bắt đầu đã định nghĩa đến trạng thái hoàn thành có ý nghĩa. Mỗi hạng mục có thể trải qua làm rõ yêu cầu, phát triển, review, kiểm thử, triển khai và xác nhận kết quả. Phần lớn thời gian trôi qua có thể nằm ở **chờ đợi, phụ thuộc, chuyển giao và làm lại**, chứ không chỉ ở thời gian lập trình.

**Cải tiến luồng dựa trên dữ liệu và thử nghiệm** là một chu trình:

1. Nhìn thấy cách công việc **thực sự** di chuyển.
2. Đo một số tín hiệu nhất quán về tốc độ, lượng việc đang làm và độ biến động.
3. Đặt giả thuyết về nguyên nhân gây chờ, nghẽn hoặc lỗi.
4. Thử một thay đổi nhỏ, có giới hạn và có thể kiểm tra.
5. Quan sát cả **thời gian giao hàng, chất lượng và giá trị người dùng**.
6. Giữ, điều chỉnh hoặc bỏ cách làm theo bằng chứng mới.

Mục tiêu không phải làm cho mọi người “bận 100%” hoặc làm thật nhiều ticket cùng lúc. Một hệ thống mà ai cũng bắt đầu việc mới nhưng rất ít việc hoàn tất thường có **WIP cao, thời gian chờ dài và phản hồi chậm**.

### Ví dụ mở đầu

Một nhóm phát triển nền tảng học trực tuyến nhận yêu cầu bổ sung chức năng **“Tiếp tục học”**. Bảng công việc cho thấy:

- Nhiều user story đã có code nhưng chờ review.
- Người kiểm thử thường nhận một lượng lớn việc vào cuối tuần.
- Nhóm tiếp tục kéo tính năng mới dù các tính năng cũ chưa tích hợp.
- Một số lỗi phân quyền chỉ được phát hiện sát ngày phát hành.

Nếu đội chỉ yêu cầu lập trình viên viết code nhanh hơn, điểm nghẽn ở review và kiểm thử vẫn tồn tại. Cải tiến Kanban đặt câu hỏi thực tế hơn:

> “Công việc bị chờ ở đâu, chờ vì sao, việc nào đang già đi, và thử thay đổi chính sách nào để **hoàn thành sớm hơn mà vẫn đáp ứng chất lượng**?”

Trong Kanban, có thể bắt đầu từ hệ thống hiện tại và **cải tiến tiến hóa**. Không cần thay toàn bộ cơ cấu tổ chức, vai trò hay công cụ ngay từ đầu.

## 2. Trước khi đo, phải định nghĩa luồng công việc

Dữ liệu chỉ có ý nghĩa khi mọi người thống nhất **cái gì được tính là công việc** và **thời điểm nào đánh dấu bắt đầu/kết thúc**. Nếu một nhóm tính cycle time từ lúc bắt đầu lập trình, nhóm khác tính từ khi tạo ticket, so sánh trực tiếp sẽ sai.

### 2.1. Ví dụ bảng Kanban

~~~text
Đề xuất       Sẵn sàng      Đang làm      Review        Kiểm thử      Hoàn tất
  nhiều         hàng chờ      WIP <= 3      WIP <= 2       WIP <= 2       đã Done
    |               |             |             |              |              |
    v               v             v             v              v              v
 [Story A] ------> [A] --------> [A] --------> [A] ----------> [A] ----------> [A]
 [Bug B  ] ------> [B] --------> [B] --------> [B] ----------> [B] ----------> [B]
~~~

Đây là **minh họa bố cục**, không phải một bảng hay mức giới hạn WIP bắt buộc. Một đội có thể chia thêm trạng thái chờ chuyên gia, triển khai, xác nhận sản xuất; đội khác có thể dùng ít cột hơn. Điều quan trọng là **các trạng thái phản ánh điểm cần quản lý dòng công việc**, không chỉ tổ chức để báo cáo.

### 2.2. Điểm bắt đầu và điểm kết thúc

Ví dụ, đội thỏa thuận:

| Khái niệm | Quy ước ví dụ | Vì sao cần rõ |
| --- | --- | --- |
| **Hạng mục được tính** | User story hoặc bug có thể hoàn tất độc lập, không tính từng subtask như hạng mục riêng | Tránh một người chia ticket nhỏ để làm đẹp throughput. |
| **Commitment/start point** | Khi hạng mục được kéo từ “Sẵn sàng” sang “Đang làm” | Xác định mốc bắt đầu cycle time và work item age. |
| **Finish point** | Khi hạng mục đáp ứng chính sách “Hoàn tất”, gồm kiểm thử/tích hợp cần thiết | Tránh tính việc “code xong” là giao xong. |
| **Blocked** | Hạng mục không thể tiến vì thông tin, môi trường, phụ thuộc hoặc lỗi | Cho thấy thời gian chờ và nguyên nhân. |
| **Reopened** | Hạng mục đã đánh dấu hoàn tất nhưng bị trả lại do chưa thỏa điều kiện | Cần chính sách ghi nhận nhất quán, không che làm lại. |

Nếu muốn đo **lead time từ yêu cầu khách hàng**, nhóm cần lưu cả thời điểm yêu cầu đi vào hệ thống. Lead time này thường bao gồm **thời gian chờ trước khi bắt đầu**, khác với cycle time tính từ điểm bắt đầu công việc.

### 2.3. Chính sách luồng cần minh bạch

Một bảng có cột chưa đủ để vận hành Kanban. Nhóm cần thống nhất:

- Điều kiện kéo một item vào “Sẵn sàng” và “Đang làm”.
- Ai có thể xác nhận quy tắc nghiệp vụ và tiêu chí chấp nhận.
- Giới hạn WIP áp dụng ở đâu, cách xử lý khi đạt giới hạn.
- Khi item bị chặn, cần hiển thị gì và ai tham gia gỡ chặn.
- Khi nào một item được xem là **Done**, kể cả test, chất lượng và tích hợp.
- Cách xử lý công việc khẩn khác với công việc thông thường.

Chính sách nên **rõ, có thể thảo luận và thay đổi có chủ đích**, không biến thành quy trình giấy tờ cứng nhắc. Nếu công việc là một bản thử kỹ thuật hay hoạt động khám phá, cần phân loại rõ để không vô tình so sánh với user story đã giao sản phẩm.

## 3. Bốn chỉ số dòng chảy cốt lõi

Có nhiều thước đo hỗ trợ Kanban; bốn chỉ số quan trọng để xem công việc di chuyển thường được dùng là **WIP, throughput, cycle time và work item age**.

### 3.1. Work in Progress (WIP)

**WIP** là số hạng mục đã bắt đầu nhưng chưa hoàn thành tại thời điểm quan sát, theo ranh giới workflow đã định nghĩa.

Ví dụ hôm nay:

- Đang làm: 3 item.
- Review: 2 item.
- Kiểm thử: 2 item.
- Tổng WIP trong phạm vi này: **3 + 2 + 2 = 7 item**.

WIP cao có thể kéo theo đổi ngữ cảnh, chờ đợi, nhiều bàn giao và thời gian phản hồi dài. Nhưng **WIP thấp không tự động tốt** nếu đội đang thiếu việc có giá trị hoặc có chướng ngại ngăn mọi người tiếp tục.

### 3.2. Throughput

**Throughput** là số hạng mục đi qua điểm kết thúc trong một khoảng thời gian.

Ví dụ hoàn tất trong bốn tuần: **4, 5, 3, 4 item**. Tổng là **16 item**; trung bình **4 item/tuần** theo quy ước đếm của đội.

Thông tin này mô tả lịch sử, **không chứng minh** tuần sau chắc chắn xong đúng bốn item. Nếu nhóm thay đổi cách chia story, cơ cấu công việc hoặc định nghĩa Done thì throughput cũng có thể thay đổi mà năng lực thực chất không đổi.

### 3.3. Cycle time

**Cycle time** là thời gian trôi qua từ khi một hạng mục **bắt đầu** đến khi **hoàn thành**, theo mốc đã thống nhất.

Ví dụ:

> Story “Xử lý yêu cầu lưu tiến độ gửi lại” được kéo vào “Đang làm” sáng thứ Hai, kết thúc đúng tiêu chuẩn vào chiều thứ Sáu cùng tuần. Cycle time xấp xỉ năm ngày lịch nếu đội dùng đơn vị ngày lịch.

Cycle time bao gồm **thời gian chờ bên trong** workflow đã chọn: chờ review, chờ test, chờ môi trường và làm lại. Nó **không đồng nghĩa với tổng ngày công** mà các thành viên đã bỏ ra.

### 3.4. Work item age

**Work item age** là thời gian đã trôi qua kể từ khi một hạng mục **đang làm** bắt đầu cho đến **thời điểm hiện tại**. Chỉ số này chỉ áp dụng cho **hạng mục chưa hoàn thành**.

Nếu story A mới bắt đầu 2 ngày, story B đã bắt đầu 11 ngày mà vẫn chờ test, tuổi của B là một tín hiệu cần điều tra. Nó giúp đội **hành động khi việc còn đang mở**, thay vì chỉ phân tích cycle time sau khi việc đã hoàn thành.

### Bảng đối chiếu nhanh

| Chỉ số | Đơn vị thường dùng | Câu hỏi giúp trả lời | Ngộ nhận cần tránh |
| --- | --- | --- | --- |
| WIP | Số hạng mục tại một thời điểm | Có bao nhiêu việc đã khởi động nhưng chưa Done? | WIP càng thấp càng tốt trong mọi trường hợp. |
| Throughput | Hạng mục/tuần hoặc /tháng | Trong kỳ vừa qua, đội hoàn thành bao nhiêu việc? | Số ticket chính là giá trị khách hàng. |
| Cycle time | Ngày hoặc giờ cho một hạng mục đã xong | Việc hoàn tất mất bao lâu từ điểm bắt đầu? | Cycle time bằng giờ lập trình. |
| Work item age | Ngày hoặc giờ của việc đang mở | Việc nào đang già đi, có nguy cơ chậm bất thường? | Việc có tuổi cao chắc chắn là do người phụ trách kém. |

Không cần tối ưu từng chỉ số tách rời. **Mục tiêu cuối cùng** là dòng giá trị ổn định, có thể dự báo ở mức hữu ích, chất lượng tốt và đáp ứng nhu cầu khách hàng.

## 4. Dữ liệu ví dụ: đọc số liệu mà không kết luận quá nhanh

Một đội có số hạng mục hoàn thành trong sáu tuần (dữ liệu hoàn toàn giả định cho bài học):

| Tuần | Throughput (item) | WIP trung bình xấp xỉ | Vấn đề nổi bật |
| --- | ---: | ---: | --- |
| 1 | 4 | 10 | Review chờ lâu |
| 2 | 3 | 12 | Nhiều item bắt đầu mới |
| 3 | 5 | 11 | Test dồn vào cuối tuần |
| 4 | 4 | 10 | Chờ môi trường tích hợp |
| 5 | 3 | 12 | Có hai phụ thuộc bên ngoài |
| 6 | 5 | 11 | Review được hỗ trợ tốt hơn |
| **Tổng/trung bình** | **24 item / 4 item mỗi tuần** | **11 item** | Cần phân tích dòng chảy chi tiết |

Có thể thấy:

1. Throughput dao động **3–5 item/tuần**, không cố định.
2. WIP quanh **10–12 item**, trong khi trung bình giao bốn item mỗi tuần.
3. Các ghi chú cho thấy **nhiều điểm chờ khác nhau**; chưa có bằng chứng rằng nguyên nhân duy nhất là “thiếu nhân sự kiểm thử”.

Đội có thể dùng dữ liệu này để đặt câu hỏi, **không nên lập tức khẳng định** rằng giảm WIP xuống 6 sẽ giúp throughput tăng gấp đôi. Muốn kết luận nguyên nhân, cần tìm hiểu cấu trúc workflow, loại item, tuổi từng việc và thay đổi bối cảnh.

### 4.1. Minh họa Little's Law

Với một hệ thống dòng công việc **tương đối ổn định**, ranh giới đo nhất quán và không có tăng/giảm tồn đọng kéo dài, quan hệ trung bình thường được diễn đạt:

\[
\text{WIP trung bình} = \text{Throughput trung bình} \times \text{Cycle time trung bình}
\]

Hay:

\[
\text{Cycle time trung bình} = \frac{\text{WIP trung bình}}{\text{Throughput trung bình}}
\]

**Ví dụ giả định:** Nếu một hệ thống ổn định duy trì WIP trung bình là **10 item** và throughput **5 item/tuần**, cycle time trung bình tương ứng khoảng **10 / 5 = 2 tuần**.

Nhưng đây là **quan hệ trung bình khi các giả định áp dụng**, không phải công thức thần kỳ để dự báo từng story. Nếu backlog đang phình, cách đếm khác nhau, mẫu dữ liệu quá ngắn hoặc hệ thống chưa ổn định, áp dụng trực tiếp có thể gây hiểu lầm. Giảm WIP không bảo đảm throughput giữ nguyên; phải quan sát thực tế.

### 4.2. Ý nghĩa quản lý

Khi throughput ít thay đổi nhưng WIP liên tục tăng, thời gian hoàn tất trung bình **có nguy cơ dài hơn**. Một hướng thử có cơ sở là giảm việc bắt đầu mới và giúp hoàn tất item đang chờ; vẫn cần xác minh nguyên nhân và chất lượng.

## 5. Nhìn vào phân bố thay vì chỉ số trung bình

Cycle time của công việc phần mềm thường **không phân bố đều**. Nhiều hạng mục xong nhanh, nhưng vài hạng mục bị chặn có thể kéo rất dài. Giá trị trung bình vì vậy có thể che một “đuôi dài” của rủi ro.

### 5.1. Ví dụ mẫu cycle time

Giả sử 12 item hoàn thành có cycle time (ngày lịch):

~~~text
2, 3, 3, 4, 4, 5, 5, 6, 7, 9, 10, 14
~~~

- **Median (trung vị):** Hai giá trị giữa là 5 và 5, nên trung vị là **5 ngày**.
- **Giá trị thấp nhất/cao nhất:** **2 ngày** và **14 ngày**.
- **Phân vị 85% theo quy tắc nearest-rank:** Vị trí làm tròn lên của 0,85 × 12 = 10,2 là hạng 11; giá trị hạng 11 là **10 ngày**.

Theo đúng phương pháp phân vị vừa nêu, có thể nói **ít nhất 85% số item trong mẫu hoàn thành trong 10 ngày hoặc ít hơn**. Dù vậy, mẫu chỉ có **12 item**, nên không được tự diễn đạt kết quả thành bảo đảm “85% công việc tương lai chắc chắn xong trước 10 ngày”. Cách tính phân vị của công cụ thống kê khác cũng có thể nội suy và cho kết quả hơi khác; cần công khai cách tính nếu so sánh.

### 5.2. Xây Service Level Expectation (SLE)

Một **Service Level Expectation (SLE)** là kỳ vọng về **khoảng thời gian một hạng mục thường cần để đi qua workflow**, thường được mô tả bằng **thời gian và xác suất kỳ vọng**, tốt nhất được dựa trên dữ liệu cycle time lịch sử có liên quan.

Ví dụ mang tính thảo luận:

> “Với loại story thông thường theo workflow hiện tại, khoảng 85% hạng mục lịch sử đã hoàn thành trong tối đa 10 ngày lịch.”

Nhóm có thể tạm dùng mốc đó để chủ động hỏi khi một story đang làm đến ngày thứ 8–9. Nhưng cần ghi rõ **loại hạng mục, mốc bắt đầu/kết thúc, cỡ mẫu và điều kiện thay đổi**.

**SLE không đồng nghĩa SLA.** SLA (*Service Level Agreement*) là thỏa thuận mức dịch vụ có thể có nghĩa vụ bên ngoài; còn SLE là kỳ vọng dự báo phục vụ quản lý luồng. Đừng quảng bá số liệu lịch sử hạn chế thành cam kết hợp đồng.

### 5.3. Dùng work item age để hành động sớm

Giả sử đội dùng SLE tham khảo **85% trong 10 ngày** và có các item đang mở:

| Item | Tuổi hiện tại | Trạng thái | Câu hỏi cần hành động |
| --- | ---: | --- | --- |
| A – Sửa nhãn lỗi | 2 ngày | Đang làm | Có trở ngại nào chưa hiển thị không? |
| B – Kiểm tra quyền học | 7 ngày | Review | Review còn cần thông tin gì để hoàn tất? |
| C – Xử lý gửi request trùng | 9 ngày | Kiểm thử | Có thể cùng kiểm tra và giải quyết trước khi quá mốc tham chiếu không? |
| D – Tích hợp báo cáo | 12 ngày | Bị chặn bởi đối tác | Cần leo thang phụ thuộc, chia lại phạm vi hoặc thương lượng kỳ vọng ra sao? |

Mốc SLE là tín hiệu để **xem xét và hỗ trợ**, không phải “cứ quá 10 ngày là nhân viên vi phạm”. Một item 12 ngày có thể gặp phụ thuộc thật; mục tiêu là tìm **cách cải thiện hệ thống**, không tìm người chịu lỗi.

## 6. Đọc bảng Kanban và các biểu đồ dòng công việc

Một bảng Kanban tốt cho thấy **trạng thái hiện tại**; các biểu đồ thời gian giúp thấy **xu hướng và biến động**. Không cần công cụ phức tạp: dữ liệu ngày bắt đầu/kết thúc nhất quán và các phép vẽ đơn giản đã có thể hỗ trợ nhiều quyết định.

### 6.1. Cumulative Flow Diagram (CFD)

**CFD** biểu diễn số lượng hạng mục tích lũy ở những trạng thái của workflow qua thời gian. Khi đọc các dải màu tương ứng:

- Dải ở một trạng thái **rộng dần** có thể là dấu hiệu lượng công việc chờ hoặc tồn đọng trong trạng thái đó tăng.
- Các đường biên tăng theo thời gian phản ánh dòng hạng mục được nhập và hoàn thành.
- Sự thay đổi độ dốc hoặc khoảng cách giữa các dải cần được xem cùng dữ liệu WIP, throughput và bối cảnh.

Ví dụ diễn giải:

> Nếu phần “Chờ review” mở rộng qua ba tuần trong khi “Hoàn tất” tăng chậm, nhóm có **giả thuyết** rằng việc review đang bị nghẽn hoặc việc kéo vào quá nhanh.

CFD **không tự nói nguyên nhân**. Có thể do thiếu reviewer, PR quá lớn, tiêu chí chưa rõ, môi trường lỗi hoặc nhóm nhập quá nhiều việc mới. Cần kiểm tra ticket cụ thể và trao đổi với người làm.

### 6.2. Biểu đồ cycle time và phân vị

Biểu đồ thể hiện cycle time của từng item theo ngày hoàn tất giúp nhóm nhìn:

- Có nhiều item thời gian ngắn nhưng vài item kéo rất dài?
- Độ biến động tăng sau một lần thay đổi chính sách?
- Loại công việc nào có cycle time khác nhau?
- Có tác động của chờ kiểm thử, release hay phụ thuộc theo từng đợt?

Đừng chỉ lấy **một item nhanh nhất** rồi xem đó là chuẩn để thúc ép những item khác. Cần nhìn phân bố đủ dài và bối cảnh thực tế.

### 6.3. Throughput run chart

Biểu đồ số item Done theo tuần cho thấy nhịp giao hàng và biến động. Nó giúp thảo luận năng lực dự báo, nhưng phải kiểm tra xem nhóm có vừa **chia ticket nhỏ hơn**, đổi Definition of Done hay trộn thêm nhiều lỗi nhỏ vào số liệu không.

### 6.4. Bảng tuổi công việc đang mở

Bảng liệt kê item đang mở, số ngày từ start point và trạng thái blocked thường hữu ích ngay trong Daily Scrum hoặc buổi quản lý dòng công việc:

~~~text
Việc đang mở        Tuổi        Cần hành động
---------------------------------------------------------
C - gửi request     9 ngày      Hỗ trợ test tích hợp
D - báo cáo API    12 ngày      Liên hệ đối tác, xem lại phạm vi
B - quyền học       7 ngày      Pair review để hoàn tất
~~~

Đây không phải bảng “ai chậm nhất”; nó giúp **ưu tiên hoàn tất công việc có nguy cơ già đi**, thay vì chỉ bàn việc mới để khởi động.

## 7. Chẩn đoán điểm nghẽn trước khi chọn giải pháp

Các dấu hiệu về flow cần được diễn giải thành **giả thuyết có thể kiểm chứng**:

| Quan sát | Giả thuyết có thể có | Bằng chứng nên xem thêm |
| --- | --- | --- |
| Review tồn nhiều item, tuổi cao | Reviewer quá tải; pull request quá lớn hoặc khó hiểu | Thời gian chờ review; kích thước PR; số lần phải sửa và lý do. |
| Test dồn vào cuối Sprint | Đội giao hàng theo đợt, thiếu tích hợp sớm | Ngày code hoàn tất và ngày test bắt đầu; tình trạng pipeline. |
| WIP tăng nhưng throughput không tăng | Bắt đầu quá nhiều việc hoặc đang chờ phụ thuộc | Số item bị chặn, tuổi công việc, phân bổ ở từng cột. |
| Cycle time kéo dài cho story tích hợp | API đối tác thiếu ổn định hoặc hợp đồng chưa rõ | Nhật ký lỗi tích hợp, contract test, thời gian chờ. |
| Throughput tăng nhưng lỗi sản xuất tăng | Định nghĩa Done/kiểm thử bị nới, tăng nợ chất lượng | DoD, lỗi escape, thời gian sửa lại và phản hồi người dùng. |
| Nhiều item mở lại sau khi Done | Điều kiện hoàn tất không rõ hoặc test thiếu phạm vi | Nguyên nhân reopen, tiêu chí chấp nhận, khả năng hồi quy. |
| SLE thường xuyên không đạt ở một loại việc | Công việc không đồng nhất hoặc có đuôi dài do phụ thuộc | Phân nhóm item, cycle time theo loại, thời gian blocked. |

### Đặt câu hỏi theo chuỗi nguyên nhân

Ví dụ, “review chậm”:

1. Có bao nhiêu item chờ review và đã chờ bao lâu?
2. PR nào lớn hoặc chạm nhiều hệ thống? Vì sao?
3. Người review có đủ ngữ cảnh, test và thời gian không?
4. Có tiêu chí nào khiến item bị trả đi trả lại?
5. Nếu rút ngắn PR và dành năng lực review hàng ngày, điểm chờ có giảm không?

Tránh biến công cụ **5 Whys** thành buổi tìm người gây lỗi. Một nguyên nhân có thể nằm ở chính sách nhận việc, cấu trúc đội, chất lượng code, yêu cầu chưa rõ hoặc môi trường; thường là **nhiều yếu tố cùng tác động**.

## 8. Thiết kế thử nghiệm cải tiến có căn cứ

Một thay đổi quy trình nên được coi là **thử nghiệm học hỏi**, không tự động là “best practice” áp dụng vĩnh viễn.

### 8.1. Mẫu giả thuyết

> **Nếu** chúng ta [thay đổi chính sách/cách phối hợp] **vì** dữ liệu cho thấy [vấn đề], **thì** [tín hiệu về luồng] có thể cải thiện trong [khoảng quan sát], **đồng thời** [chất lượng/giá trị] không giảm. Chúng ta sẽ **kiểm tra bằng** [dữ liệu và cách so sánh], rồi quyết định [giữ/điều chỉnh/bỏ].

Ví dụ:

> “Nếu giới hạn tổng số story đang phát triển và chờ review, đồng thời dành thời gian hoàn tất item già nhất trước khi kéo việc mới, thì cycle time và tuổi công việc đang mở có thể giảm trong bốn tuần. Chúng ta sẽ theo dõi phân bố cycle time, throughput, tỷ lệ bị chặn và lỗi thoát ra môi trường sử dụng; nếu chất lượng hoặc khả năng phục vụ việc khẩn xấu đi, phải điều chỉnh.”

### 8.2. Sáu thành phần của một thử nghiệm

| Thành phần | Cần ghi | Ví dụ |
| --- | --- | --- |
| **Vấn đề và dữ liệu nền** | Chuyện gì đang diễn ra, trong kỳ nào, đo theo mốc nào? | WIP khoảng 11; cycle time nhiều item dài; review chờ tăng. |
| **Giả thuyết** | Thay đổi cụ thể sẽ tác động chỉ số nào và vì sao? | Ít việc cùng lúc giúp giảm chờ review và chuyển ngữ cảnh. |
| **Can thiệp** | Chính sách mới, đội/loại item áp dụng, điểm bắt đầu | Không kéo item mới nếu cột “Đang làm” đầy; hỗ trợ review trước. |
| **Khoảng quan sát** | Bao lâu và khi nào xem lại; đủ dữ liệu chưa? | Bốn tuần là ví dụ; điều chỉnh theo throughput và nhịp làm việc thực tế. |
| **Guardrail** | Điều không được làm xấu đi | Lỗi nghiêm trọng, tiêu chuẩn Done, độ trễ xử lý sự cố khẩn. |
| **Quyết định sau thử** | Giữ, sửa, bỏ hay điều tra tiếp trên cơ sở nào? | Xem phân bố, item già, chất lượng và phản hồi của đội. |

### 8.3. Các nguyên tắc để thử nghiệm đáng tin hơn

- **Chỉ thay một vài yếu tố trọng tâm** mỗi lần khi khả thi; nếu thay mọi chính sách cùng lúc sẽ khó hiểu nguyên nhân.
- **Ghi điều kiện ban đầu** trước khi thay đổi, không chọn mốc “trước” có số liệu xấu bất thường để tô đẹp kết quả.
- **Giữ quy tắc đo nhất quán**; nếu buộc đổi cách đếm item, ghi rõ để không so sánh sai.
- **Quan sát tác dụng phụ**: tốc độ tăng nhưng lỗi tăng, việc khẩn bị bỏ qua, hoặc thành viên phải làm thêm giờ liên tục đều là vấn đề.
- **Không diễn giải tương quan thành nhân quả chắc chắn** khi không có đối chứng và có nhiều yếu tố thay đổi.
- **Dừng hoặc điều chỉnh sớm nếu có rủi ro an toàn**, không cố chạy hết thời gian thử khi dữ liệu bị hỏng hoặc người dùng chịu ảnh hưởng nghiêm trọng.

Thử nghiệm cải tiến không nhất thiết phải là A/B test ngẫu nhiên. Nhiều thay đổi quy trình chỉ có thể thử ở quy mô một đội. Khi đó, hãy trung thực về **giới hạn bằng chứng** và cân nhắc thử tiếp trước khi nhân rộng.

## 9. Thử nghiệm 1: giới hạn WIP và ưu tiên hoàn tất

### 9.1. Vấn đề

Đội có bốn developer, một tester luân phiên hỗ trợ, nhưng cùng lúc mở 12 story. Hầu hết story cần review và test của cùng vài người; các item bị chờ lâu, nhiều việc bị chuyển ngữ cảnh.

### 9.2. Giả thuyết

Nếu giảm lượng việc **đã bắt đầu nhưng chưa Done** và giúp nhau hoàn tất, cycle time có thể giảm vì ít thời gian chờ tại những bước có năng lực hạn chế.

### 9.3. Chính sách thử

Giả sử đội thống nhất trong ba tuần:

1. Giới hạn **Đang làm: 3 item** và **Review: 2 item** (chỉ là ví dụ, không có con số chuẩn).
2. Khi cột Review đã đủ, mọi người **không tiếp tục đẩy thêm item vào đó**; tìm cách giúp review, chia nhỏ thay đổi hoặc giải quyết trở ngại.
3. Chọn item có **tuổi cao và rủi ro lớn** để hỗ trợ hoàn tất trước khi kéo thêm việc.
4. Mọi người có thể **swarm/pair** trên một hạng mục nếu điều đó giúp gỡ nghẽn tốt hơn việc ai cũng mở ticket mới.
5. Giữ chính sách xử lý sự cố khẩn và điều kiện chất lượng bắt buộc riêng, không để WIP limit cản khôi phục dịch vụ.

### 9.4. Theo dõi

| Tín hiệu | Điều muốn quan sát |
| --- | --- |
| WIP trung bình | Có giảm thực chất hay chỉ đổi cột để che việc chưa Done? |
| Work item age | Các item già có được gỡ chặn và hoàn tất sớm hơn? |
| Phân bố cycle time | Median và đuôi dài có ngắn lại sau đủ mẫu phù hợp? |
| Throughput | Có giữ được hoặc tăng hợp lý mà không thêm áp lực quá mức? |
| Chất lượng | Có tăng lỗi production, việc mở lại hoặc workarounds không? |
| Phản hồi đội | Chính sách có tạo điều kiện phối hợp hay khiến người có việc bị bỏ không? |

### 9.5. Điều không nên kết luận

Nếu tuần đầu throughput **giảm**, không nhất thiết thử nghiệm thất bại: đội có thể đang hoàn tất những item tồn lâu thay vì đóng các item nhỏ mới. Ngược lại, throughput tăng ngay chưa chứng minh giảm WIP là nguyên nhân duy nhất. Hãy theo dõi **đủ chu kỳ** và xem cả trạng thái tồn đọng.

**WIP limit không phải chỉ tiêu để “luôn đầy cột”.** Khi cột đã đạt giới hạn, câu hỏi đúng là **có thể giúp đưa công việc tiến lên không**, không phải “làm sao chuyển số sang cột khác để được kéo tiếp?”.

## 10. Thử nghiệm 2: giảm chờ review và kiểm thử

### 10.1. Quan sát

Bảng cho thấy item thường mất 2 ngày lập trình nhưng chờ 6–8 ngày để được review và kiểm thử. Vấn đề chính có thể không nằm ở tốc độ viết code.

### 10.2. Các cách thử có thể chọn

| Can thiệp nhỏ | Giả thuyết | Cách xác minh |
| --- | --- | --- |
| **Dành khung thời gian review thường xuyên** | Item không phải chờ đến cuối tuần | Đo thời gian từ “sẵn sàng review” đến được review. |
| **PR nhỏ hơn và mô tả tiêu chí rõ** | Reviewer hiểu nhanh hơn, ít vòng sửa | Xem thời gian review, số lần trả lại và lỗi tích hợp. |
| **Pairing trước khi bàn giao** | Phát hiện vấn đề sớm, giảm vòng làm lại | Quan sát số lỗi review, cycle time và chất lượng. |
| **Kiểm thử tích hợp sớm** | Không dồn lỗi API vào cuối Sprint | Đo tuổi item ở “Kiểm thử” và tỷ lệ lỗi xuất hiện muộn. |
| **Swarm tại cột đang nghẽn** | Tận dụng năng lực đa kỹ năng để hoàn tất | Xem thời gian chờ, WIP và tác động lên công việc khác. |

Không nên thay tất cả năm cách cùng lúc mà không có lý do. Ví dụ, đội có thể thử **PR nhỏ và review hằng ngày** trước; nếu vẫn chờ vì môi trường test không ổn định, chuyển trọng tâm sang **ổn định CI và môi trường**.

### 10.3. Đầu ra cần đạt

Một thử nghiệm có ích kết thúc bằng nhận định:

> “Vấn đề chờ review giảm hay chưa? Dữ liệu nào hỗ trợ? Có phát sinh lỗi hoặc chi phí không mong muốn? Chính sách nào tiếp tục, chính sách nào cần đổi?”

Nó **không** chỉ kết thúc bằng “đã tổ chức thêm cuộc họp review”.

## 11. Thử nghiệm 3: hiển thị và gỡ công việc bị chặn

Một hạng mục có thể tồn rất lâu vì chờ quyết định nghiệp vụ, môi trường, dữ liệu hoặc nhà cung cấp. Nếu bảng chỉ có cột “Đang làm” mà không biết nguyên nhân, đội dễ đưa ra ước lượng sai hoặc cho rằng vấn đề thuộc cá nhân.

### Chính sách blocked minh bạch

- Đánh dấu **blocked** ngay khi item không thể tiến theo chính sách.
- Ghi lý do ngắn, thời điểm bắt đầu bị chặn và **người/nhóm có thể giúp giải quyết**.
- Phân biệt blocked vì quyết định nghiệp vụ, lỗi môi trường, phụ thuộc đối tác, thiếu test hoặc chờ quyền truy cập.
- Đưa việc có **work item age cao** và mức tác động lớn vào cuộc trao đổi quản lý flow.
- Khi gỡ chặn, ghi kết quả để nhận diện loại trở ngại lặp lại.

### Ví dụ

~~~text
Item: Đồng bộ tiến độ từ thiết bị khác
Trạng thái: Blocked trong cột Kiểm thử
Tuổi item: 11 ngày
Nguyên nhân: API đối tác chưa có hành vi rõ khi gửi cập nhật lặp
Tác động: Chưa thể xác minh tính toàn vẹn dữ liệu
Người phối hợp: Developer API, Product Owner, QA, đầu mối đối tác
Hành động: Contract test và xác nhận quy tắc xung đột
Điểm xem lại: Lần quản lý dòng công việc tiếp theo
~~~

**Giảm “thời gian blocked”** có thể cần làm rõ yêu cầu hoặc cải tiến kỹ thuật chứ không chỉ đặt WIP limit. Hãy phân tích loại phụ thuộc để chọn thử nghiệm đúng nguyên nhân.

## 12. Chính sách khẩn và phân loại công việc

Không phải mọi item có độ khẩn hoặc tổn thất do chậm trễ như nhau. Một lỗi mất dữ liệu cần phản ứng khác với một yêu cầu đổi nhãn giao diện. Kanban cho phép nhóm dùng **chính sách dịch vụ rõ ràng**, có thể phân biệt việc khẩn, ngày cố định hoặc việc tiêu chuẩn.

### Ví dụ một số loại dịch vụ

| Loại | Tình huống | Chính sách minh họa |
| --- | --- | --- |
| **Tiêu chuẩn** | User story thông thường | Kéo theo thứ tự ưu tiên và năng lực; tuân thủ WIP limit. |
| **Khẩn (expedite)** | Lỗi mất dữ liệu, sự cố bảo mật nghiêm trọng | Có cơ chế xử lý ưu tiên, minh bạch việc bị gián đoạn, không tạo vô số “làn khẩn”. |
| **Ngày cố định** | Cổng kiểm định hay mốc sự kiện bên ngoài | Nhận diện sớm phụ thuộc, bằng chứng và ngày phải quyết định. |
| **Nghiên cứu/giảm rủi ro** | Spike về API chưa rõ | Giới hạn thời gian và đầu ra kiến thức, không trộn lẫn với Increment đã giao. |

Những tên phân loại chỉ là **ví dụ chính sách**, không có nghĩa mọi đội Kanban phải áp dụng đúng các lớp đó. Cần làm rõ quyền quyết định “khẩn”, điều kiện đưa vào và cách xử lý ảnh hưởng lên những item đang mở.

### Tránh lạm dụng expedite

Nếu 40% công việc đều mang nhãn “khẩn”, đó là dấu hiệu chính sách ưu tiên hoặc kế hoạch năng lực cần được đánh giá lại. Một lane expedite hữu ích khi thực sự **hiếm, có tiêu chí và có người chịu trách nhiệm**; nếu không nó trở thành cách vượt hàng chờ thường xuyên làm giảm tính dự báo.

## 13. Feedback loops: chọn nhịp kiểm tra phù hợp

Kanban không buộc đội phải sử dụng đúng các sự kiện Scrum. Tuy vậy, muốn cải tiến dựa trên dữ liệu cần **những nhịp phản hồi** để quan sát và ra quyết định. Nhịp có thể là hằng ngày, hằng tuần hoặc theo mức biến động dòng việc.

| Vòng phản hồi | Câu hỏi phù hợp | Quyết định điển hình |
| --- | --- | --- |
| **Quan sát flow ngắn hằng ngày** | Item nào đang già hoặc bị chặn? Có đang kéo quá WIP limit? | Giúp hoàn tất, gỡ chặn, ngừng kéo thêm việc. |
| **Bổ sung/chọn việc (replenishment)** | Hạng mục nào nên đi vào dòng việc tiếp theo? Có đủ thông tin và năng lực? | Đưa việc phù hợp vào “Sẵn sàng”, đổi thứ tự hoặc cần khám phá thêm. |
| **Xem chất lượng dịch vụ/dữ liệu flow** | Throughput, cycle time, SLE và lỗi đang biến động thế nào? | Điều chỉnh kỳ vọng, chính sách và phụ thuộc. |
| **Review giá trị với khách hàng** | Sản phẩm giao có giải quyết đúng nhu cầu? | Điều chỉnh Product Backlog hoặc ưu tiên cơ hội khác. |
| **Họp cải tiến có trọng tâm** | Thử nghiệm vừa qua có giúp hệ thống tốt hơn không? | Giữ, sửa, bỏ thử nghiệm và chọn vấn đề tiếp theo. |

Không cần biến mọi vòng phản hồi thành **một cuộc họp dài riêng**. Đội có thể lồng vào nhịp hiện có miễn quyết định, thông tin và người có quyền hành động được minh bạch.

### Mỗi lần kiểm tra cần kết thúc bằng hành động

Ví dụ:

> “Ba item đang ở tuổi 9–12 ngày, trong đó hai item chờ quyết định hợp đồng API. Hôm nay không kéo thêm story liên quan API; nhóm phối hợp người có thẩm quyền chốt quy tắc. Chúng ta sẽ kiểm tra lại trạng thái vào ngày mai.”

Thông điệp này hữu ích hơn việc đọc từng ticket mà không thay đổi cách xử lý.

## 14. Từ dữ liệu flow đến dự báo có trách nhiệm

Kanban hỗ trợ **dự báo dòng công việc** dựa trên dữ liệu lịch sử, nhưng không biến dự báo thành bảo đảm.

### 14.1. Dự báo sơ bộ từ throughput

Giả sử đội hoàn tất **4, 5, 3, 4, 4, 4 item** trong sáu tuần, trung bình **24 / 6 = 4 item/tuần**. Nếu còn **12 item tương tự** và năng lực không đổi:

- Kịch bản theo nhịp trung bình là **12 / 4 = 3 tuần**.
- Với nhịp **3 item/tuần** là **4 tuần**.
- Với nhịp **5 item/tuần** là **2,4 tuần**.

Đây chỉ là **kịch bản số học**, không phải “xác suất 85% xong sau ba tuần”. Độ tin cậy phụ thuộc sự tương đồng về kích thước item, cách chia story, quy tắc Done, dữ liệu và điều kiện tương lai.

### 14.2. Khi nào có thể dùng mô phỏng?

Nếu có đủ lịch sử liên quan, đội có thể dùng phân vị cycle time hoặc mô phỏng theo mẫu throughput (ví dụ Monte Carlo) để xây dựng **dự báo xác suất có điều kiện**. Cần minh bạch:

1. Các quan sát lịch sử có đại diện cho công việc sắp tới không?
2. Các item còn lại có kích thước/loại tương tự không?
3. Dòng công việc có đổi WIP, người thực hiện, chính sách Done hoặc phụ thuộc không?
4. Có công việc tồn lâu hoặc rủi ro hiếm mà mô hình chưa phản ánh không?
5. Mốc hoàn thành và phương pháp tính xác suất được định nghĩa thế nào?

Một mô hình tinh vi với dữ liệu không phù hợp có thể **kém đáng tin hơn một khoảng ước lượng có điều kiện đơn giản**.

### 14.3. Không đánh đồng lead time và cycle time

Đối tác hỏi “Sau khi gửi yêu cầu, bao lâu tôi nhận được tính năng?” có thể cần **lead time từ lúc yêu cầu được ghi nhận**, bao gồm chờ ưu tiên. Trong khi đội đang theo dõi cycle time chỉ từ lúc kéo việc vào “Đang làm”. Nếu bỏ thời gian chờ trước khi bắt đầu, dự báo cho đối tác sẽ lạc quan sai.

Luôn nói rõ **điểm bắt đầu, điểm kết thúc, loại việc và điều kiện dự báo**.

## 15. Tình huống hoàn chỉnh: cải tiến luồng của đội nền tảng học tập

### 15.1. Bối cảnh

Đội phụ trách chức năng học tập, hỗ trợ sửa lỗi và cải tiến nền tảng. Họ dùng bảng:

> Sẵn sàng → Đang làm → Review → Kiểm thử → Hoàn tất

Đội nhận phản hồi rằng nhiều chức năng hoàn thành muộn, đặc biệt khi cần API tiến độ. Trong bốn tuần đầu, nhóm đo theo cùng định nghĩa Done:

| Tuần | Throughput | WIP trung bình | Ghi chú |
| --- | ---: | ---: | --- |
| 1 | 5 | 11 | Nhiều review đến cùng lúc |
| 2 | 4 | 10 | Chờ test tích hợp |
| 3 | 6 | 12 | Có lỗi gửi request lặp |
| 4 | 5 | 11 | Hai item phụ thuộc đội API |
| **Tổng/trung bình** | **20 / 5 item mỗi tuần** | **11 item** | Dữ liệu nền để đặt câu hỏi |

Phỏng vấn ngắn trong đội cho thấy **nhiều người nhận thêm story mới khi item cũ chờ review/test**. Tuy nhiên, đó mới là giả thuyết về nguyên nhân, chưa phải bằng chứng quan hệ nhân quả.

### 15.2. Xác định mục tiêu cải tiến

Đội không đặt mục tiêu “đóng được thật nhiều ticket”. Họ xác định:

> “Giảm thời gian từ lúc bắt đầu đến lúc giao các thay đổi nhỏ của luồng học tập, ưu tiên hoàn tất ổn định, không tăng lỗi phân quyền hoặc mất tiến độ.”

Các guardrail gồm:

- Không bỏ bước kiểm thử quan trọng hoặc hạ Definition of Done nếu đội dùng Scrum.
- Không cho phép truy cập dữ liệu của tài khoản khác.
- Không trì hoãn xử lý sự cố mất dữ liệu chỉ vì WIP limit.
- Theo dõi lỗi sản xuất và công việc phải làm lại.

### 15.3. Thử nghiệm đầu tiên

Nhóm chọn **giới hạn WIP ở Đang làm và Review**, đồng thời có chính sách “khi Review đầy, ưu tiên hỗ trợ review và test trước khi kéo thêm”.

Họ thử trong bốn tuần tiếp theo với điều kiện các loại item và mốc đo được giữ tương đối nhất quán. Trong quá trình thử, đội ghi tuổi từng item và nguyên nhân blocked.

### 15.4. Kết quả giả định

| Tín hiệu | Bốn tuần trước | Bốn tuần thử nghiệm | Cách diễn giải thận trọng |
| --- | --- | --- | --- |
| Throughput | 20 item | 24 item | Tăng từ 5 lên 6 item/tuần trong mẫu ngắn. |
| WIP trung bình | 11 item | 8 item | Công việc đồng thời giảm. |
| Cycle time trung vị | 10 ngày | 7 ngày | Cần xem cả phân bố và tuổi item chưa hoàn thành. |
| Số item bị chặn lâu | 5 | 3 | Cần kiểm tra loại item và nguyên nhân chặn. |
| Lỗi nghiêm trọng thoát ra sản xuất | 1 | 1 | Không thấy tăng trong mẫu, nhưng mẫu quá nhỏ để kết luận đã an toàn hơn. |

**Các số liệu đều giả định**. Chúng cho thấy thay đổi có vẻ hứa hẹn, nhưng **chưa chứng minh** giảm WIP là nguyên nhân duy nhất khiến cycle time giảm:

- Có thể Sprint/tháng sau có nhiều story nhỏ hơn.
- Một phụ thuộc API đã được nhà cung cấp giải quyết.
- Nhân sự có thêm thời gian hoặc không có sự cố khẩn.
- Các item chưa hoàn thành từ kỳ trước vẫn có tuổi cao.

Đội cần xem từng item, phân bố cycle time, thời gian blocked, chất lượng và tiếp tục theo dõi qua thêm chu kỳ phù hợp.

### 15.5. Quyết định sau thử

Một kết luận có trách nhiệm:

> “Dữ liệu bốn tuần gợi ý giới hạn WIP và hỗ trợ review thường xuyên đã giúp đội hoàn tất ổn định hơn. Chúng ta giữ chính sách ở mức thử nghiệm thêm một chu kỳ, bổ sung ghi nguyên nhân blocked và phân loại hạng mục tích hợp API để xem các trường hợp cycle time dài. Không thay đổi DoD hay chính sách xử lý sự cố khẩn.”

**Đầu ra của thử nghiệm là một quyết định có căn cứ**, không chỉ là bảng thống kê đẹp.

### 15.6. Lần cải tiến tiếp theo

Sau khi WIP ổn định hơn, nhóm thấy phần lớn item quá SLE đều liên quan tới **contract API chưa rõ**. Họ có thể thử:

1. Trao đổi quy tắc và ví dụ giữa sản phẩm – developer – tester trước khi bắt đầu tích hợp.
2. Viết contract test sớm với đội API.
3. Chỉ kéo story tích hợp khi phụ thuộc tối thiểu đã rõ, trừ trường hợp mục đích là một spike để khám phá.
4. Quan sát thời gian chờ và tỷ lệ làm lại của nhóm story đó.

Như vậy, cải tiến mang tính **tiến hóa**: một lần thay đổi giúp làm rõ vấn đề kế tiếp, không có giả định rằng chỉ cần áp dụng WIP limit là giải quyết xong mọi điểm nghẽn.

## 16. Gắn cải tiến dòng công việc với giá trị và chất lượng

Không nên để các chỉ số flow trở thành **mục tiêu tự thân**. Một đội có thể tăng throughput bằng cách chia một story thành hàng chục ticket nhỏ, hoặc rút ngắn cycle time bằng cách đóng ticket khi code vừa được merge. Các con số cải thiện, nhưng người dùng chưa có thêm giá trị.

### Phân biệt output, flow, quality và outcome

| Nhóm chỉ số | Ví dụ | Giới hạn |
| --- | --- | --- |
| **Output** | Số tính năng, số ticket hoặc release | Không tự chứng minh người dùng được lợi. |
| **Flow** | WIP, throughput, cycle time, work item age | Mô tả khả năng giao và nút thắt, không tự đo giá trị. |
| **Quality** | Lỗi thoát ra sản xuất, lỗi lặp lại, kiểm thử, tính toàn vẹn dữ liệu | Cần định nghĩa mức nghiêm trọng và phạm vi. |
| **Outcome** | Tỷ lệ học viên mở lại đúng bài, thời gian tìm bài, phản hồi thực tế | Có thể cần thời gian đo và tách yếu tố gây nhiễu. |

Ví dụ, giảm cycle time của tính năng “Tiếp tục học” có thể giúp nhóm nhận phản hồi nhanh hơn; nhưng nếu học viên vẫn khó tìm nút hoặc tiến độ bị mất, hệ thống chưa thực sự đạt mục tiêu sản phẩm.

### Guardrail bắt buộc

- **Không giảm chất lượng để có số liệu tốt:** Công việc chỉ Done khi đạt chính sách chất lượng đã thỏa thuận.
- **Không che trạng thái blocked:** Di chuyển item sang cột khác để làm đẹp WIP làm hỏng dữ liệu.
- **Không phạt cá nhân vì work item age:** Tuổi item thể hiện tính chất hệ thống và phụ thuộc.
- **Không ép người làm thêm giờ để giữ throughput:** Đây là giải pháp thiếu bền vững, có thể gây lỗi và kiệt sức.
- **Không bỏ qua việc khẩn:** Cần chính sách có thể kiểm toán và cơ chế ứng phó với sự cố.

Cải tiến tốt giúp **đội dự báo và giao giá trị bền vững hơn**, không phải chỉ giúp dashboard trông đẹp hơn.

## 17. Kết hợp Kanban, Scrum và thực hành XP

Kanban và Scrum không nhất thiết loại trừ nhau. Scrum thiết lập một khung cho trách nhiệm, sự kiện, tạo tác và cam kết; Kanban cung cấp góc nhìn về **dòng công việc** có thể hỗ trợ Scrum Team nếu phù hợp. XP hỗ trợ khả năng giao phần mềm chất lượng với phản hồi kỹ thuật nhanh.

| Cách tiếp cận | Đóng góp cho cải tiến dựa trên dữ liệu | Ví dụ thực hành |
| --- | --- | --- |
| **Kanban** | Minh bạch workflow, chính sách kéo việc, WIP, tuổi item, cycle time, throughput và cải tiến tiến hóa | Giới hạn việc đang làm, tập trung gỡ item già và bị chặn. |
| **Scrum** | Sprint Goal tạo sự tập trung; Daily Scrum kiểm tra tiến triển; Sprint Review và Retrospective cung cấp phản hồi | Trong Sprint, xem bảng flow để biết item nào đe dọa Sprint Goal. |
| **XP** | CI, TDD, refactor, pair programming, kiểm thử tự động giảm chi phí thay đổi và phản hồi lỗi muộn | Thử CI/contract test để giảm thời gian chờ kiểm thử và lỗi tích hợp. |

### Dùng dữ liệu flow trong Scrum

Một Scrum Team có thể quan sát work item age trong Daily Scrum để thấy hạng mục đang tiến gần Sprint Goal hay bị chặn. Tại Sprint Retrospective, đội phân tích cycle time và thời gian chờ để chọn một thử nghiệm cải tiến. Tại Sprint Review, đội xem Increment thực tế cùng phản hồi để quyết định sản phẩm cần thay đổi gì.

Kanban **không bắt buộc thêm các vai trò, sự kiện hoặc artefact mới** lên Scrum, và không có số WIP limit phổ quát. Các công cụ quản lý flow nên hỗ trợ **giá trị và minh bạch**, không làm nặng hệ thống bằng nghi thức.

### Khi nào Kanban là cách tổ chức chính?

Một đội xử lý hỗ trợ sản phẩm, lỗi vận hành hoặc yêu cầu đến liên tục có thể dùng Kanban để quản lý dòng công việc mà không cần Sprint cố định. Họ vẫn cần mục tiêu phục vụ khách hàng, chính sách rõ, kiểm soát chất lượng và nhịp cải tiến. Không phải mọi tình huống Agile đều phải dùng Scrum.

## 18. Các sai lầm thường gặp khi “cải tiến theo số liệu”

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| **Đo gì có sẵn thay vì điều cần biết** | Ticket count không phản ánh điểm nghẽn hoặc giá trị | Bắt đầu từ quyết định cần hỗ trợ, rồi chọn chỉ số phù hợp. |
| **Không định nghĩa start/finish** | Cycle time của các kỳ hoặc nhóm không thể so sánh | Ghi rõ ranh giới workflow và đơn vị đo. |
| **Chỉ xem số trung bình** | Che item đuôi dài và nguy cơ chậm bất thường | Xem phân bố, median/phân vị và work item age. |
| **Coi SLE là SLA chắc chắn** | Hứa quá mức với khách hàng | Nêu mức kỳ vọng, cơ sở dữ liệu và giới hạn; thỏa thuận riêng khi có SLA. |
| **Coi CFD là bằng chứng nguyên nhân** | Dải review rộng chưa chắc do thiếu reviewer | Kiểm tra ticket, thời gian chờ và phản hồi trực tiếp của đội. |
| **Giảm WIP bằng cách đổi nhãn trạng thái** | Số liệu đẹp giả, vấn đề còn nguyên | Gắn WIP với trạng thái thật và chính sách minh bạch. |
| **Bắt đầu càng nhiều việc càng tốt** | Tăng đổi ngữ cảnh, thời gian chờ và lỗi tích hợp | Ưu tiên hoàn tất; hỗ trợ item bị chặn và WIP có kiểm soát. |
| **Làm quá nhiều thử nghiệm cùng lúc** | Khó biết thay đổi nào gây tác động | Chọn giả thuyết trọng tâm; ghi các thay đổi đồng thời. |
| **Thấy một tuần tốt rồi tuyên bố thành công** | Biến động tự nhiên hoặc công việc khác loại gây sai kết luận | Quan sát nhiều kỳ, xem phân bố và bối cảnh. |
| **Tăng throughput bằng cách chia ticket hình thức** | Số lượng tăng nhưng giá trị không đổi | Đo item có ranh giới nhất quán và kiểm tra outcome. |
| **Phớt lờ lỗi và nợ chất lượng** | Giao nhanh hơn trên giấy nhưng làm lại nhiều hơn | Bảo vệ DoD, test và guardrail chất lượng. |
| **Dùng chỉ số để xếp hạng cá nhân/đội** | Khuyến khích tối ưu số, che lỗi, giảm hợp tác | Dùng để cải tiến hệ thống và hỗ trợ trao đổi, không đổ lỗi. |
| **Tạo chính sách khẩn cho mọi việc** | Dòng thường xuyên bị gián đoạn, kỳ vọng không còn đáng tin | Có tiêu chí expedite rõ và kiểm tra tần suất sử dụng. |
| **Không biến dữ liệu thành quyết định** | Dashboard nhiều nhưng quy trình không đổi | Kết thúc mỗi buổi kiểm tra bằng hành động và điểm xem lại. |

## 19. Bài tập thực hành

### Bài tập 1 — Tính và đọc bốn chỉ số cốt lõi

Một đội có:

- 3 item ở “Đang làm”, 2 item ở “Review”, 1 item ở “Kiểm thử”.
- Trong bốn tuần vừa qua, hoàn tất 4, 6, 3 và 5 item.
- Story A bắt đầu 8 ngày trước, hiện vẫn chờ review.
- Story B đã hoàn tất sau 5 ngày từ lúc bắt đầu.

**Yêu cầu:** Tính WIP, throughput trung bình, work item age của A và cycle time của B. Giải thích vì sao **không thể lấy tuổi của A làm cycle time cuối cùng**.

**Gợi ý đáp án:** WIP = **6 item**; throughput trung bình = **18 / 4 = 4,5 item/tuần**; A có age **8 ngày** và vẫn tăng khi chưa Done; B có cycle time **5 ngày**. Tất cả phụ thuộc quy ước start/finish nhất quán.

### Bài tập 2 — Đọc dữ liệu cycle time

Dữ liệu ngày lịch của 12 item đã hoàn thành:

~~~text
2, 3, 3, 4, 4, 5, 5, 6, 7, 9, 10, 14
~~~

**Yêu cầu:** Tính median, giá trị lớn nhất và P85 theo phương pháp nearest-rank. Viết một câu SLE tham khảo có nêu điều kiện. Giải thích vì sao không thể tuyên bố 85% item tương lai chắc chắn hoàn tất trong cùng thời gian.

**Gợi ý đáp án:** Median **5 ngày**, max **14 ngày**, P85 **10 ngày** theo quy tắc nearest-rank. Mẫu nhỏ; cần xác nhận hạng mục và workflow có tương đồng trong tương lai không.

### Bài tập 3 — Tìm giả thuyết điểm nghẽn

Đội có WIP tăng từ 7 lên 14 item trong ba tuần, throughput vẫn dao động 3–5 item/tuần, và cột Review mở rộng trên CFD.

**Yêu cầu:** Nêu ít nhất **ba giả thuyết khác nhau**. Với mỗi giả thuyết, chỉ rõ **dữ liệu hoặc quan sát cần thu thập** trước khi quyết định cải tiến.

**Gợi ý:** Reviewer thiếu thời gian; PR quá lớn; tiêu chí nghiệm thu thiếu rõ; test pipeline không ổn định; đội kéo việc mới quá nhanh. Không kết luận chỉ từ CFD.

### Bài tập 4 — Thiết kế thử nghiệm WIP limit

Đội đang có 12 item mở, nhiều item chờ review và test. Một người đề nghị giới hạn Đang làm = 3, Review = 2.

**Yêu cầu:** Viết giả thuyết, chính sách thử, khoảng quan sát, chỉ số chính, hai guardrail và tiêu chí quyết định sau thử. Nêu cách xử lý khi có sự cố sản xuất khẩn.

**Gợi ý:** Không biến mục tiêu thành “cột phải luôn đầy”; thử chính sách **hoàn tất trước khi bắt đầu thêm**, theo dõi cycle time, age và lỗi.

### Bài tập 5 — Đánh giá kết quả trước/sau

Trước thử nghiệm: throughput 20 item/4 tuần, WIP trung bình 11, median cycle time 10 ngày. Sau thử nghiệm: throughput 24 item/4 tuần, WIP trung bình 8, median 7 ngày. Cùng kỳ, nhà cung cấp cũng sửa lỗi API thường gây chờ.

**Yêu cầu:** Viết đoạn đánh giá khoảng 150–200 từ, phân biệt điều dữ liệu cho thấy, điều chưa thể kết luận, tác động của thay đổi đồng thời và hành động tiếp theo.

**Gợi ý:** Có tín hiệu tích cực nhưng chưa chứng minh nguyên nhân. Cần xem phân bố, item chưa Done, loại công việc, chất lượng và kết quả nhiều chu kỳ.

### Bài tập 6 — Phân biệt SLE và SLA

Đội có lịch sử 85% ticket sửa lỗi tiêu chuẩn hoàn thành trong 10 ngày. Một quản lý muốn nói với khách hàng: “Chúng tôi cam kết mọi lỗi đều xong trong 10 ngày.”

**Yêu cầu:** Giải thích vấn đề, viết lại phát biểu có trách nhiệm và đề xuất thông tin cần có nếu tổ chức thật sự muốn ký SLA.

**Gợi ý:** SLE dựa trên phân bố lịch sử và có điều kiện. SLA đòi hỏi phạm vi, mức dịch vụ, cách đo, ngoại lệ, nghĩa vụ và cơ chế xử lý được thống nhất; không biến phân vị thành lời hứa tuyệt đối.

### Bài tập 7 — Kết hợp Scrum, Kanban và XP

Một Scrum Team có Sprint Goal là “Học viên tiếp tục bài học mà không mất tiến độ”. Trong Sprint:

- Nhiều story chờ review.
- API đối tác đổi hợp đồng.
- Có lỗi nghiêm trọng về phân quyền.
- Các PR thường tích hợp sát cuối Sprint.

**Yêu cầu:** Lập kế hoạch hành động trong 24 giờ đầu và một thử nghiệm cải tiến cho Sprint tiếp theo. Chỉ ra cách sử dụng Sprint Goal, WIP, work item age, contract test, CI và Definition of Done.

**Gợi ý:** Xử lý an toàn và rủi ro sản phẩm trước; minh bạch trạng thái; không tự kéo thêm item trong lúc tích hợp hỏng. Retrospective chọn thay đổi có thể kiểm chứng.

## 20. Checklist trước khi công bố “đã cải tiến luồng”

- [ ] Điểm bắt đầu, điểm kết thúc và loại work item đã được định nghĩa nhất quán?
- [ ] Bảng phản ánh **trạng thái thật**, gồm blocked, review, test và hoàn tất?
- [ ] Đội có theo dõi **WIP, throughput, cycle time và work item age** theo nhu cầu?
- [ ] Có xem **phân bố**, item đuôi dài và công việc đang mở thay vì chỉ trung bình?
- [ ] SLE (nếu dùng) nêu rõ thời gian, mức kỳ vọng, loại việc và cơ sở dữ liệu?
- [ ] Những tín hiệu CFD hay dashboard đã được kiểm tra cùng ticket và phản hồi của người làm?
- [ ] Vấn đề được viết thành **giả thuyết nguyên nhân**, chưa vội kết luận chắc chắn?
- [ ] Thử nghiệm có **can thiệp cụ thể, khoảng quan sát, chỉ số và điểm xem lại**?
- [ ] Quy tắc WIP và pull có giúp hoàn tất việc, không chỉ thay đổi số trên bảng?
- [ ] Việc bị chặn có nguyên nhân, người phối hợp và hành động rõ?
- [ ] Có chính sách xử lý khẩn và tránh lạm dụng nhãn expedite?
- [ ] Không hạ **chất lượng, bảo mật, dữ liệu, test hoặc DoD** để cải thiện số liệu?
- [ ] Có xem cả **outcome người dùng** lẫn tốc độ xử lý công việc?
- [ ] Khi so sánh trước/sau, đã ghi nhận thay đổi về loại item, nhân sự, API hoặc điều kiện khác?
- [ ] Kết quả được dùng để **giữ, điều chỉnh hoặc bỏ** thử nghiệm, không chỉ làm báo cáo?
- [ ] Các chỉ số được dùng để cải tiến hệ thống, không dùng để xếp hạng hay đổ lỗi cá nhân?

Checklist hỗ trợ thảo luận; nhóm nhỏ có thể chọn vài tín hiệu quan trọng thay vì đo mọi thứ. Độ phức tạp của hệ thống đo lường không nên vượt quá giá trị của quyết định nó hỗ trợ.

## 21. Tổng kết

- **Kanban cải tiến luồng bằng minh bạch, giới hạn công việc đang làm, quản lý dòng chảy, chính sách rõ và phản hồi thường xuyên.** Cách làm phù hợp là tiến hóa từ thực tế, không thay toàn bộ quy trình để trông giống một mẫu bảng.
- **Bốn tín hiệu flow quan trọng:** WIP cho thấy lượng việc đang làm; throughput cho thấy nhịp hoàn thành; cycle time mô tả việc đã hoàn thành mất bao lâu; work item age giúp phát hiện sớm những việc chưa xong đang già đi.
- **Đọc phân bố và điều kiện đo:** Median, phân vị, SLE, CFD và Little's Law đều có giả định; không tự biến xu hướng ngắn hạn thành lời hứa chắc chắn.
- **Dữ liệu tạo câu hỏi, thử nghiệm tạo kiến thức:** Chọn một điểm nghẽn, nêu giả thuyết, thử thay đổi nhỏ, kiểm tra kết quả và guardrail, rồi quyết định bước tiếp.
- **Ưu tiên hoàn tất hơn bắt đầu:** WIP limit, swarming, review sớm, contract test và cải tiến CI có thể giúp giảm chờ; chỉ giữ cách làm nếu thực tế ủng hộ.
- **Không tối ưu số liệu mà bỏ giá trị:** Throughput tăng không tự chứng minh sản phẩm tốt hơn; cần xem chất lượng, phản hồi người dùng và tác động thật.
- **Kanban có thể kết hợp Scrum và XP:** Dữ liệu flow hỗ trợ Sprint Goal và Retrospective; các thực hành kỹ thuật giúp giảm lỗi, cải thiện khả năng giao phần mềm tăng dần.

Khi thấy một bảng Kanban có nhiều ticket nhưng ít giá trị được giao, hãy hỏi: **“Công việc đang chờ ở đâu, bằng chứng nào cho thấy điều đó, chúng ta có thể thử thay đổi nhỏ nào và sẽ kiểm tra tác động của nó ra sao?”**
