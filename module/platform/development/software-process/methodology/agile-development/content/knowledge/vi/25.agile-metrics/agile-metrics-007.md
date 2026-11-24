# Đo lường Agile: Đọc biểu đồ dòng tích lũy cùng phân bố thời gian hoàn thành

Một nhóm phát triển phần mềm đăng ký workshop đang gặp tình huống quen thuộc: cuối tuần, bảng công việc có rất nhiều thẻ “đang làm”, nhưng Product Owner khó trả lời học viên **khi nào tính năng xem trạng thái đăng ký sẽ hoàn tất**. Báo cáo nhóm chỉ nêu số thẻ đã đóng trong Sprint và số story points. Một người nói nhóm bắt đầu nhiều việc hơn nên tiến độ tốt; người khác nói review đang nghẽn; người thứ ba nhìn vài story hoàn tất nhanh rồi khẳng định “hầu hết việc chỉ mất ba ngày”.

Ba kết luận này có thể đều thiếu bằng chứng. Để hiểu dòng công việc, nhóm cần nhìn **hạng mục đi vào, đi qua và ra khỏi hệ thống như thế nào**, đồng thời xem **thời gian hoàn thành của các hạng mục thực tế phân bố ra sao**, thay vì chỉ xem một số trung bình.

Hai công cụ bổ trợ nhau là:

- **Cumulative Flow Diagram (CFD) – biểu đồ dòng tích lũy:** hiển thị lượng công việc đã đi vào hệ thống, lượng đang ở từng trạng thái và lượng đã hoàn tất theo thời gian. Nó giúp nhìn xu hướng WIP, hàng chờ và dòng công việc có ổn định không.
- **Phân bố thời gian hoàn thành (cycle time distribution):** cho biết các hạng mục hoàn tất mất **bao lâu từ started đến finished** theo định nghĩa đã thống nhất, mức độ phân tán, đuôi dài và khả năng dự báo.

Bài thuộc mô-đun **AGILE_DEVELOPMENT**, hướng đến phản hồi sớm, bàn giao giá trị tăng dần, cải tiến liên tục và sử dụng user story, backlog, Scrum, Kanban, XP cũng như các số đo dòng công việc để phối hợp phù hợp. Trọng tâm là **đọc hai góc nhìn cùng nhau**: CFD cho thấy cấu trúc và chuyển động của dòng; phân bố cycle time cho thấy người dùng hoặc stakeholder có thể trải nghiệm thời gian chờ **khác nhau nhiều đến mức nào**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **CFD**, throughput chart, cycle time scatterplot, histogram, empirical cumulative distribution và aging WIP.
2. Nhận diện đường tích lũy và **dải trạng thái** trên CFD; đọc đúng WIP theo khoảng cách **theo trục dọc**.
3. Phân tích hình dạng các đường để nhận diện việc vào nhanh hơn việc ra, trạng thái ùn lại và thay đổi chính sách.
4. Tự lập một bảng CFD nhỏ từ lịch sử chuyển trạng thái, kiểm tra tổng số item và các ranh giới.
5. Tính **cycle time, work item age, WIP và throughput** từ dữ liệu có mốc started/finished rõ.
6. Đọc phân bố thời gian hoàn thành bằng **bảng tần suất, median, percentile, ECDF và scatterplot**, không đồng nhất một số trung bình với mọi trường hợp.
7. Diễn giải **Service Level Expectation (SLE)** bằng ngưỡng thời gian, tỷ lệ phần trăm và điều kiện dữ liệu.
8. Giải thích giới hạn của việc suy cycle time từ khoảng cách ngang trên CFD và các sai lầm của dữ liệu bị cắt cụt.
9. Kết hợp CFD, phân bố cycle time và **tuổi các item chưa hoàn tất** để quyết định nên hỗ trợ việc nào trước.
10. Đề xuất một cải tiến thực nghiệm dựa trên điểm nghẽn có khả năng kiểm chứng, không dùng biểu đồ để xếp hạng cá nhân.
11. Kết nối số đo dòng công việc với **giá trị sản phẩm, chất lượng, Product Goal, Scrum và các thực hành Kanban/XP**.
12. Tự thực hành một bộ dữ liệu và chuẩn bị cách trình bày cho nhóm/stakeholder.

## 2. Phải định nghĩa dòng công việc trước khi vẽ biểu đồ

### 2.1. Cùng một từ “hoàn tất” có thể chỉ nhiều mốc

Một user story có thể trải qua:

~~~text
Intake --> Ready --> Doing --> Review --> Verify --> Done
                    ^ STARTED                       ^ FINISHED
~~~

Trong DoW (*Definition of Workflow*) của ví dụ này:

- **Started:** thời điểm item được kéo từ Ready vào Doing theo chính sách pull.
- **Finished:** thời điểm item vượt điều kiện Done đã thống nhất.
- **WIP:** mọi item đã started nhưng chưa finished, gồm Doing, Review, Verify và cả các item bị chặn trong những trạng thái ấy.
- **Before started:** Intake và Ready, không thuộc WIP theo ranh giới này.
- **After finished:** Done; item hoàn tất không còn là WIP.

Trong hệ thống khác, Finished có thể là “đã đáp ứng Definition of Done, sẵn sàng bàn giao” hoặc “đã triển khai và xác minh với người dùng”. Không có một ranh giới duy nhất đúng cho mọi dịch vụ. **Điều cần thiết là ranh giới nhất quán và được công bố**.

### 2.2. Bốn flow metrics cơ bản

| Số đo | Định nghĩa theo luồng đã chọn | Trả lời câu hỏi |
| --- | --- | --- |
| **Work in Progress (WIP)** | Số item đã started nhưng chưa finished tại thời điểm quan sát | Đang có bao nhiêu việc đang mở? |
| **Throughput** | Số item finished trong một khoảng thời gian xác định | Trong khoảng ấy hoàn tất bao nhiêu việc? |
| **Work item age** | Thời gian từ started tới hiện tại của một item **chưa finished** | Việc đang mở này đã tồn tại bao lâu? |
| **Cycle time** | Thời gian từ started tới finished của một item **đã finished** | Một việc hoàn tất mất bao lâu? |

Các công thức khái niệm, với cùng đơn vị thời gian:

~~~text
cycle_time(item) = finished_at - started_at
work_item_age(item, now) = now - started_at    (khi chưa finished)
WIP(now) = số item đã started và chưa finished
throughput(period) = số item finished trong period
~~~

**Blocked không tự dừng đồng hồ**. Nếu item đang chờ review hoặc môi trường kiểm thử sau started, thời gian chờ vẫn là một phần cycle time. Nếu nhóm tự động “reset started” khi item bị kẹt, số liệu sẽ không còn phản ánh thời gian đi qua luồng thật.

### 2.3. Work item phải có nghĩa nhất quán

Nếu một nhóm đếm user story nhỏ và một dự án kéo dài sáu tháng như hai “item” bằng nhau, phân bố cycle time và throughput có thể trở nên khó diễn giải. Cần xác định:

- Loại item: user story, bug, thay đổi kỹ thuật, yêu cầu hỗ trợ hay spike.
- Mức kích thước: một lát cắt giá trị hay một epic bao nhiều story?
- Chính sách tách hoặc gộp item.
- Cách xử lý hủy, trùng lặp, reopen và chuyển qua dịch vụ khác.
- Dấu thời gian và đơn vị: ngày lịch, giờ hay ngày làm việc.

**Không cần mọi item giống hệt nhau**, nhưng khi dùng phân bố để dự báo, tập dữ liệu phải đủ tương đồng với hạng mục đang muốn dự báo, hoặc phải phân nhóm phù hợp.

### 2.4. Cycle time không nhất thiết là toàn bộ thời gian chờ của khách hàng

Giả sử yêu cầu gửi đến ngày 1, vào Ready ngày 2, bắt đầu Doing ngày 6, finished ngày 10:

- **Cycle time theo DoW này:** 10 − 6 = **4 ngày**.
- **Thời gian từ arrival đến finished:** 10 − 1 = **9 ngày**.

Nếu chỉ báo “hoàn tất trung bình 4 ngày” mà người dùng đã chờ 9 ngày, nhóm đang trả lời câu hỏi khác. Khi chia sẻ kết quả phải nêu **từ mốc nào đến mốc nào**, và cân nhắc đo thêm *customer lead time* nếu cần.

## 3. CFD hiển thị điều gì?

**Cumulative Flow Diagram** thể hiện số lượng work items tích lũy theo thời gian ở các ranh giới trạng thái. Bản CFD thường gặp là **biểu đồ diện tích xếp chồng**, trong đó mỗi dải màu biểu diễn số item đang ở một trạng thái vào thời điểm quan sát.

### 3.1. Hai trục và cách đọc

- **Trục X:** thời gian, chẳng hạn ngày làm việc hoặc cuối mỗi ngày lịch.
- **Trục Y:** số lượng work items, thường là số tích lũy tính đến thời điểm trên trục X.
- **Ranh giới dưới:** số item đã finished tính tích lũy, nếu Done được đặt ở đáy.
- **Ranh giới trên:** tổng số item đã started trong luồng từ đầu kỳ theo mô hình.
- **Dải ở giữa:** lượng item còn đang ở Doing, Review, Verify… tùy cách xếp dải.

**Thứ tự dải cần được xem trong chú giải**. Một CFD có thể đặt Done ở đáy, một biểu đồ khác dùng thứ tự khác; không thể nói “dải màu xanh là Review” nếu không có legend và định nghĩa trạng thái.

### 3.2. Minh họa bằng các ranh giới

~~~text
Số item tích lũy
^
|                /---------------------  Tổng đã STARTED
|             __/     Doing
|          __/--------------------------  Done + Verify + Review
|       __/     Review
|     _/-------------------------------  Done + Verify
|   _/       Verify
| _/-----------------------------------  Đã DONE (cộng dồn)
|/
+-------------------------------------> Thời gian

Tại cùng một thời điểm:
WIP = ranh giới trên - ranh giới đã Done
Dải Review = ranh giới ngay trên Review - ranh giới dưới Review
~~~

Đường vẽ chỉ mang tính khái niệm, không biểu diễn dữ liệu thật. Khi xây CFD từ bảng số liệu, thứ tự dải và giá trị từng đường phải được xác định rõ.

### 3.3. Ba câu hỏi mạnh nhất mà CFD giúp trả lời

1. **Tổng WIP có tích lũy không?** Khoảng cách thẳng đứng giữa “đã started” và “đã done” đang nở hay thu?
2. **Công việc dồn ở bước nào?** Một dải như Review hoặc Verify có dày lên liên tục không?
3. **Tốc độ hoàn tất có theo kịp tốc độ bắt đầu không?** Độ dốc đường Done thay đổi thế nào so với đường Started?

CFD cho thấy **mẫu hình và nơi cần điều tra**, nhưng không tự giải thích nguyên nhân. Một dải Review dày lên có thể do thiếu reviewer, thay đổi mức độ phức tạp, item quá lớn, lỗi tích hợp hoặc cách cập nhật trạng thái bị chậm.

## 4. Tự dựng CFD từ dữ liệu lịch sử: ví dụ xuyên suốt

Để đọc biểu đồ đúng, hãy bắt đầu với một bộ dữ liệu nhỏ có thể tái tạo bằng tay.

### 4.1. Quy ước dữ liệu

Nhóm workshop theo dõi tám user stories **A–H** qua các trạng thái:

~~~text
Ready (chưa started)
   -> Doing (STARTED)
   -> Review
   -> Verify
   -> Done (FINISHED)
~~~

Giả định:
- Mọi sự kiện được ghi vào các mốc **ngày số 1, 2, 3…**, cùng một giờ theo cùng múi giờ.
- Mỗi item đi theo thứ tự Doing → Review → Verify → Done, không quay lại trong bộ dữ liệu đơn giản này.
- Các snapshot được quan sát **cuối ngày**, sau khi tất cả sự kiện của ngày đó được ghi.
- Dữ liệu chỉ gồm tám item và **không có item từ trước kỳ đo**.
- Item trong Doing, Review, Verify đều tính WIP.
- Các con số **giả định phục vụ bài học**, không phải số đo một nhóm thực tế.

### 4.2. Nhật ký chuyển trạng thái

| Item | Started / vào Doing | Vào Review | Vào Verify | Finished / vào Done |
| --- | ---: | ---: | ---: | ---: |
| **A** | 1 | 2 | 3 | 3 |
| **B** | 1 | 3 | 4 | 5 |
| **C** | 2 | 4 | 5 | 6 |
| **D** | 3 | 5 | 6 | 7 |
| **E** | 4 | 6 | 8 | 9 |
| **F** | 5 | 7 | 8 | 10 |
| **G** | 6 | 9 | 11 | 12 |
| **H** | 8 | 10 | 12 | 13 |

Ví dụ: B bắt đầu ngày 1, vào Review ngày 3, vào Verify ngày 4 và finished ngày 5. Vì thế cycle time B là **5 − 1 = 4 ngày**. Hàng đợi Review/Verify vẫn nằm trong khoảng ấy.

### 4.3. Đếm trạng thái cuối từng ngày

| Ngày | Started cộng dồn | Doing | Review | Verify | Done cộng dồn | WIP |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 0 | 0 | 0 | 2 |
| 2 | 3 | 2 | 1 | 0 | 0 | 3 |
| 3 | 4 | 2 | 1 | 0 | 1 | 3 |
| 4 | 5 | 2 | 1 | 1 | 1 | 4 |
| 5 | 6 | 2 | 1 | 1 | 2 | 4 |
| 6 | 7 | 2 | 1 | 1 | 3 | 4 |
| 7 | 7 | 1 | 2 | 0 | 4 | 3 |
| 8 | 8 | 2 | 0 | 2 | 4 | 4 |
| 9 | 8 | 1 | 1 | 1 | 5 | 3 |
| 10 | 8 | 0 | 2 | 0 | 6 | 2 |
| 11 | 8 | 0 | 1 | 1 | 6 | 2 |
| 12 | 8 | 0 | 0 | 1 | 7 | 1 |
| 13 | 8 | 0 | 0 | 0 | 8 | 0 |

Kiểm tra từng hàng:

~~~text
Started cộng dồn = Doing + Review + Verify + Done cộng dồn
WIP = Doing + Review + Verify
WIP = Started cộng dồn - Done cộng dồn

Ví dụ ngày 7:
7 = 1 + 2 + 0 + 4
WIP = 1 + 2 + 0 = 3 = 7 - 4
~~~

Trong một hệ thống có hủy, chuyển dịch vụ, reopen hoặc item có từ trước kỳ, công thức bảo toàn cần bổ sung các kết quả/chuyển tiếp thích hợp. **Không được ép dữ liệu sai vào công thức để tạo biểu đồ đẹp.**

### 4.4. Từ đếm trạng thái đến ranh giới tích lũy

Đặt **Done ở đáy**, tiếp đến Verify, Review, Doing. Tạo bốn đường ranh giới:

~~~text
L0 = Done
L1 = Done + Verify
L2 = Done + Verify + Review
L3 = Done + Verify + Review + Doing = Started

Dải Verify = L1 - L0
Dải Review = L2 - L1
Dải Doing = L3 - L2
Tổng WIP   = L3 - L0
~~~

Bảng đường cho một số mốc:

| Ngày | L0: Done | L1: Done + Verify | L2: + Review | L3: Started | L3 − L0 = WIP |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 0 | 0 | 2 | 2 |
| 4 | 1 | 2 | 3 | 5 | 4 |
| 6 | 3 | 4 | 5 | 7 | 4 |
| 7 | 4 | 4 | 6 | 7 | 3 |
| 8 | 4 | 6 | 6 | 8 | 4 |
| 10 | 6 | 6 | 8 | 8 | 2 |
| 11 | 6 | 7 | 8 | 8 | 2 |
| 13 | 8 | 8 | 8 | 8 | 0 |

### 4.5. Sơ đồ đường ranh giới

Biểu đồ đường sau hiển thị **các ranh giới để người học thấy giá trị tích lũy**. CFD đúng nghĩa có thể **tô dải giữa những đường ấy** theo trạng thái. Theo thứ tự vẽ: Done (dưới cùng), Done + Verify, Done + Verify + Review, Started (trên cùng).

~~~mermaid
xychart-beta
    title "Ranh gioi CFD - 8 user stories gia dinh"
    x-axis "Ngay" [1,2,3,4,5,6,7,8,9,10,11,12,13]
    y-axis "So item" 0 --> 8
    line [0,0,1,1,2,3,4,4,5,6,6,7,8]
    line [0,0,1,2,3,4,4,6,6,6,7,8,8]
    line [0,1,2,3,4,5,6,6,7,8,8,8,8]
    line [2,3,4,5,6,7,7,8,8,8,8,8,8]
~~~

Lưu ý: tùy trình hiển thị, biểu đồ đường có thể không hiện chú giải bốn series; **bảng L0–L3 ở trên là nguồn giải thích chính xác**. Khi dùng phần mềm làm CFD thật, nên hiển thị chú giải và tô màu có khả năng phân biệt tốt.

### 4.6. Những điều đọc được ngay

- Ngày **6**, Started = 7, Done = 3, nên **WIP = 4**.
- Ngày **7**, có **2 item trong Review** vì L2 − L1 = 6 − 4 = 2; WIP tổng là 3.
- Ngày **8**, Verify có **2 item** vì L1 − L0 = 6 − 4 = 2; WIP tổng là 4.
- Ngày **10**, Doing = 0 nhưng Review = 2. **Không có việc mới đang ở Doing** không có nghĩa đã hết việc đang mở.
- Ngày **11**, Done không tăng so với ngày 10 dù WIP vẫn là 2. Nhóm nên kiểm tra vì sao **không có item finished trong ngày**, nhưng một ngày đứng yên chưa đủ chứng minh có nghẽn kéo dài.
- Ngày **13**, tám item đã finished, WIP = 0. Đây là kết quả của một **lô công việc hữu hạn**, không phải bằng chứng nhóm có dòng việc ổn định mãi mãi.

## 5. Đọc hình dạng CFD: dải dày, độ dốc và các đường hội tụ

### 5.1. Khoảng cách theo trục dọc biểu diễn lượng công việc

Nếu đường Started ở mức 30 và Done ở mức 18 tại cùng một thời điểm, **WIP = 12** theo mô hình hai ranh giới ấy. Nếu Review band dày 7, có bảy item đang thuộc trạng thái Review ở thời điểm đó.

Chú ý phân biệt:
- **Dải WIP dày:** nhiều item cùng đang mở.
- **Đường Done dốc:** nhiều item finished trong khoảng.
- **Đường Started dốc:** nhiều item mới được bắt đầu.
- **Khoảng cách Started–Done nở:** lượng việc bắt đầu đang vượt lượng việc hoàn tất trong khoảng quan sát.

Không nên nhầm **chiều cao của đường tích lũy** với **số item đang làm**. Đường Done tăng từ 18 lên 30 có thể cho biết 12 item hoàn tất, nhưng WIP phải đo bằng **khoảng cách giữa hai đường ở cùng thời điểm**.

### 5.2. Độ dốc của đường Done liên hệ throughput

Ví dụ:

~~~text
Done cuối tuần 1 = 24
Done cuối tuần 2 = 35

Throughput tuần 2 = 35 - 24 = 11 item
~~~

Cần định nghĩa thời gian và loại item. Nếu tuần sau Done là 39, throughput tuần sau là 4. Nhưng **một tuần thấp hơn không đủ kết luận năng lực kém đi**: cần xem loại việc, holidays, sự cố, cách ghi ngày kết thúc và biến động tự nhiên.

### 5.3. Đường Started tăng nhanh, Done tương đối phẳng

~~~text
Thời điểm t0: Started = 40, Done = 30 --> WIP = 10
Thời điểm t1: Started = 58, Done = 35 --> WIP = 23
~~~

Trong khoảng đó, nhóm **bắt đầu thêm 18 item nhưng chỉ hoàn tất thêm 5**, WIP tăng từ 10 lên 23. Các khả năng cần điều tra:
- Kéo việc mới vào quá nhanh.
- Item quá lớn hoặc thiếu thông tin.
- Review/test/release chưa đủ khả năng tiếp nhận.
- Có phụ thuộc bên ngoài hoặc sự cố.
- Chính sách started vừa thay đổi.
- Các loại item mới khác hẳn dữ liệu cũ.

Một cải tiến thử được có thể là **giới hạn công việc mới bắt đầu**, hỗ trợ review hoặc chia item nhỏ hơn. Nhưng phải xác định nguyên nhân thực tế trước, không chỉ yêu cầu “Done tăng nhanh lên”.

### 5.4. Đường Started và Done cùng tăng với độ dốc tương đương

Nếu trong nhiều khoảng cả hai đường tăng gần song song và chênh lệch dọc ổn định, **WIP có thể đang tương đối ổn định**. Điều đó thường dễ quản lý hơn WIP tăng vô hạn.

Tuy vậy, **WIP ổn định không tự động nghĩa thời gian hoàn thành ngắn, chất lượng tốt hoặc giá trị cao**. Một hệ thống có WIP ổn định 100 item vẫn có thể buộc khách hàng chờ rất lâu. Cần xem phân bố cycle time, throughput và outcome.

### 5.5. Một dải trung gian dày lên liên tục

Giả sử dải Review:

| Cuối kỳ | Item ở Review |
| --- | ---: |
| Kỳ 1 | 2 |
| Kỳ 2 | 4 |
| Kỳ 3 | 7 |
| Kỳ 4 | 11 |

Dải tăng liên tiếp cho thấy **tồn kho công việc tại bước Review** đang lớn lên. Nhóm nên kiểm tra:
- Có đủ khả năng review không?
- Item vào Review đủ nhỏ, đủ test và rõ mô tả chưa?
- Review có đang phụ thuộc một chuyên gia?
- Có nhiều lần phát hiện lỗi và quay lại Doing?
- Có thực chất là thời gian **chờ review**, nhưng bảng chỉ gộp vào “Review”?
- Tốc độ chuyển vào Review tăng vì một chiến dịch không thường lệ?
- Các thẻ có được cập nhật đúng lúc không?

Một dải dày là **tín hiệu**, không phải phép chẩn đoán tự động rằng reviewer đang làm việc chậm.

### 5.6. Dải trung gian co lại

Dải Review từ 11 về 3 có thể do:
- Nhóm xử lý xong hàng chờ.
- Item đã chuyển sang Verify và tiến tới Done.
- Chính sách trạng thái thay đổi hoặc dữ liệu được dọn lại.
- Item bị hủy/chuyển dịch vụ.
- Nhóm không còn bắt đầu nhiều việc mới.

Vì vậy cần xem **Done có tăng tương ứng không**, tổng Started, lịch sử chuyển trạng thái và quy tắc xử lý item, thay vì ca ngợi chỉ vì một dải màu mỏng đi.

### 5.7. Có thể nhìn thấy nút thắt nhưng chưa biết nguyên nhân

Một CFD không ghi trực tiếp:
- Người nào thiếu thời gian.
- Item khó đến mức nào.
- Thời gian đang **làm thật** và thời gian chờ trong cùng trạng thái.
- Người dùng có nhận giá trị không.
- Những item vẫn nằm ở Intake/Ready trước started.
- Lỗi phát hành, chất lượng và chi phí hỗ trợ.

Để hiểu sâu hơn có thể dùng **item-level history, blocked reason, review queue age, cycle time scatterplot, defect data, feedback người dùng** và trao đổi với nhóm.

## 6. Khoảng cách ngang trên CFD: đọc thận trọng

Một cách giải thích CFD thường thấy là lấy **khoảng cách ngang** giữa đường Started và Done tại một mức số lượng tích lũy để ước lượng thời gian công việc đi qua hệ thống.

Ví dụ: tại mức tích lũy **50**, đường Started đạt mức đó ở ngày 12, đường Done đạt mức đó ở ngày 19; khoảng ngang là **7 ngày**.

**Không nên khẳng định đây là cycle time của một item cụ thể.**

### 6.1. Vì sao chỉ là một cách ước lượng?

Hai đường theo số tích lũy có thể đánh dấu:
- **Item thứ 50 bắt đầu** ở ngày 12.
- **Item thứ 50 hoàn tất** ở ngày 19.

Nếu hạng mục **không hoàn tất theo đúng thứ tự bắt đầu**, hai sự kiện này có thể thuộc **hai item khác nhau**. Khi hệ thống có item size rất khác, vượt hàng, ưu tiên khẩn hoặc nhiều lớp dịch vụ, khoảng cách ngang không phải phép đo chính xác cho từng item.

Đường Started và Done cũng có thể thay độ dốc, khiến khoảng cách ngang thay đổi theo mức tích lũy và khoảng đo. Đây là tín hiệu về thời gian đi qua dòng ở cấp hệ thống, **không thay thế cycle time tính từ timestamp của mỗi item**.

### 6.2. Khi nào khoảng cách ngang hữu ích?

Khoảng ngang có thể cho **hình dung gần đúng** về khả năng chuyển đổi đầu vào thành đầu ra khi:
- Dòng công việc tương đối ổn định.
- Tập item và ranh giới không đổi.
- Không có nhiều hạng mục hủy hoặc chuyển dịch vụ ẩn.
- Không có sự xáo trộn thứ tự quá lớn, hoặc đã hiểu giới hạn.
- Nhóm chỉ dùng để nhận diện xu hướng, không gắn lời hứa cho item cụ thể.

Khi cần trả lời “85% story gần đây hoàn tất trong mấy ngày?” hoặc “item nào đang vượt thời gian thường thấy?”, phải dùng **dữ liệu per-item** và phân bố cycle time/age.

### 6.3. Thước đo nên lấy trực tiếp từ dữ liệu

~~~text
Một item:
    Start timestamp --> Finish timestamp --> Cycle time thực

Một CFD:
    Tổng đã started - tổng đã finished tại t --> WIP tại t

Một bộ nhiều item:
    [cycle_time_1, cycle_time_2, ...]
    --> histogram / scatterplot / ECDF / percentile
~~~

Đó là sự khác nhau giữa **đọc chuyển động tổng hợp** và **đọc thời gian thực của từng hạng mục**.

## 7. Phân bố thời gian hoàn thành là gì?

**Cycle time distribution** mô tả các giá trị cycle time của những item đã finished trong **tập công việc và khoảng thời gian được xác định**. Không chỉ hỏi “trung bình bao lâu?”, mà còn:

- Giá trị ngắn nhất và dài nhất là bao nhiêu?
- Nhiều item tập trung ở khoảng nào?
- Có đuôi dài vì vài hạng mục mất thời gian rất lâu không?
- Tỷ lệ hoàn tất trong 3, 5 hoặc 8 ngày là bao nhiêu?
- Một hạng mục đang mở 10 ngày có khác thường so với lịch sử không?
- Dữ liệu có đủ phù hợp để dự báo một item mới không?

### 7.1. Tính cycle time cho tám story A–H

Dựa trên bảng ở phần 4, tính theo **ngày lịch**, các mốc cùng giờ:

| Item | Started | Finished | Cycle time |
| --- | ---: | ---: | ---: |
| **A** | 1 | 3 | **2 ngày** |
| **B** | 1 | 5 | **4 ngày** |
| **C** | 2 | 6 | **4 ngày** |
| **D** | 3 | 7 | **4 ngày** |
| **E** | 4 | 9 | **5 ngày** |
| **F** | 5 | 10 | **5 ngày** |
| **G** | 6 | 12 | **6 ngày** |
| **H** | 8 | 13 | **5 ngày** |

Tập cycle time theo thứ tự finished là:

~~~text
[2, 4, 4, 4, 5, 5, 6, 5]

Sắp xếp tăng dần:
[2, 4, 4, 4, 5, 5, 5, 6]
~~~

Với dữ liệu minh họa này:
- **Min = 2 ngày**, **max = 6 ngày**.
- **Mean = (2 + 4 + 4 + 4 + 5 + 5 + 6 + 5) / 8 = 35/8 = 4,375 ngày**.
- **Median thông thường** của tám giá trị là trung bình vị trí thứ 4 và 5: **(4 + 5)/2 = 4,5 ngày**.

Một người chỉ báo “trung bình 4,375 ngày” có thể khiến stakeholder tưởng hầu hết story sẽ xong đúng khoảng ấy. Phân bố cho biết **có item 2 ngày nhưng cũng có item 6 ngày**, ngay cả trong ví dụ nhỏ khá đồng đều.

### 7.2. Histogram – số item theo khoảng thời gian

Histogram hoặc bảng tần suất cho biết **mỗi khoảng cycle time có bao nhiêu item**:

| Cycle time | Số item | Tỷ lệ của 8 item |
| ---: | ---: | ---: |
| 2 ngày | 1 | 12,5% |
| 3 ngày | 0 | 0% |
| 4 ngày | 3 | 37,5% |
| 5 ngày | 3 | 37,5% |
| 6 ngày | 1 | 12,5% |
| **Tổng** | **8** | **100%** |

~~~text
Số item
3 |       ### ###
2 |       ### ###
1 | ###   ### ### ###
0 +---------------------
    2     4   5   6      Cycle time (ngày)

Mỗi dấu # biểu diễn một item; khoảng 3 ngày có 0 item.
~~~

Histogram hữu ích để thấy **đỉnh, khoảng thường gặp và đuôi dài**. Nhưng cách chọn độ rộng bin có thể làm hình dạng trông khác nhau; dùng cùng quy ước khi so hai kỳ.

### 7.3. Tại sao không chỉ nhìn mean?

Giả sử một tập giả định khác có cycle time:

~~~text
[1, 2, 2, 3, 3, 3, 4, 22] ngày

Mean = 40/8 = 5 ngày
Median = (3 + 3)/2 = 3 ngày
Max = 22 ngày
~~~

Một item **22 ngày** kéo mean lên 5, trong khi đa số item xong trong 1–4 ngày. Với stakeholder muốn hiểu rủi ro trễ, câu chuyện “trung bình 5 ngày” chưa thể hiện đầy đủ **đuôi dài**. Cần tìm lý do item 22 ngày: block, phụ thuộc, phạm vi lớn, loại việc khác hay lỗi dữ liệu.

Không nên **xóa outlier chỉ để số liệu đẹp**. Nếu đó là công việc thật thuộc dịch vụ, thời gian dài là bằng chứng cần hiểu. Chỉ loại khi có chính sách dữ liệu rõ, ví dụ lỗi timestamp đã được sửa hoặc đó là một loại item cần tách nhóm.

## 8. ECDF và percentile: đọc tỷ lệ hoàn tất trong một ngưỡng

**Empirical Cumulative Distribution Function (ECDF)** trả lời: **Trong những item đã finished, có bao nhiêu phần trăm có cycle time nhỏ hơn hoặc bằng một ngưỡng?**

### 8.1. Công thức

~~~text
F(t) = số item finished có cycle_time <= t
       --------------------------------------
       tổng số item finished trong tập dữ liệu
~~~

Ví dụ tám story A–H:

| Ngưỡng t | Item finished có cycle time ≤ t | F(t) |
| ---: | ---: | ---: |
| 2 ngày | 1/8 | 12,5% |
| 3 ngày | 1/8 | 12,5% |
| 4 ngày | 4/8 | 50% |
| 5 ngày | 7/8 | 87,5% |
| 6 ngày | 8/8 | 100% |

Đọc bảng:
- **50%** item mẫu finished trong **4 ngày hoặc ít hơn**.
- **87,5%** item mẫu finished trong **5 ngày hoặc ít hơn**.
- **100%** item mẫu finished trong **6 ngày hoặc ít hơn**.

**Đây là mô tả lịch sử của đúng tám item**, không bảo đảm 100% item tương lai xong trong 6 ngày.

### 8.2. Một cách tính percentile minh họa

Có nhiều quy ước tính sample percentile, nên **phải nêu phương pháp**. Với cách **nearest-rank**:

~~~text
Sắp xếp N giá trị tăng dần.
Vị trí của percentile p = ceil(p * N)
(trong đó p được viết dạng 0..1).

N = 8; p = 0,85
Vị trí = ceil(0,85 * 8) = ceil(6,8) = 7
Giá trị thứ 7 trong [2,4,4,4,5,5,5,6] = 5 ngày
~~~

Vậy **percentile 85 theo nearest-rank = 5 ngày** trong ví dụ. Công cụ khác có thể dùng **nội suy** để tính percentile và cho một giá trị khác đôi chút. Vì vậy khi công bố percentile để dự báo, nên ghi phương pháp, đơn vị và tập dữ liệu.

Chú ý **sample median** thường được tính trung bình hai giá trị giữa khi N chẵn (ở đây 4,5 ngày); điều đó không giống quy tắc nearest-rank p50, vốn có thể chọn một giá trị quan sát. Đừng nhầm hai quy ước.

### 8.3. Diễn giải tỷ lệ đúng cách

Câu tốt:

> “Trong tám story cùng loại đã finished của dữ liệu minh họa, **7/8 story (87,5%)** hoàn tất trong **5 ngày lịch hoặc ít hơn** kể từ Started theo DoW đã nêu.”

Câu không tốt:

> “Mọi story chắc chắn hoàn tất sau 5 ngày vì p85 là 5.”

**Một percentile không phải deadline chắc chắn cho từng item**. Càng ít dữ liệu, biến động theo kích thước item, loại công việc hoặc giai đoạn, độ chắc chắn của dự báo càng hạn chế.

## 9. Service Level Expectation (SLE) và dự báo có điều kiện

**Service Level Expectation (SLE)** trong ngữ cảnh Kanban là **một kỳ vọng về thời gian work item đi từ started đến finished**, thường được phát biểu bằng **một ngưỡng thời gian kèm tỷ lệ phần trăm**.

Ví dụ:

> “Dựa trên dữ liệu lịch sử của các user story tương tự, khoảng **85%** item finished trong **5 ngày lịch hoặc ít hơn** kể từ thời điểm Started.”

Câu này có thể được dùng khi tập dữ liệu phù hợp. Với **tám item minh họa** ở đây, nhóm **không nên tuyên bố đã có mô hình dự báo đáng tin** chỉ vì có thể tính ra một percentile. Có thể tạm dùng làm bài tập đọc dữ liệu và tiếp tục thu thập lịch sử.

### 9.1. Những thành phần phải công bố

| Thành phần | Điều cần ghi rõ | Ví dụ |
| --- | --- | --- |
| **Dịch vụ** | Dòng công việc nào đang được đo? | User story phát triển tính năng workshop |
| **Started** | Sự kiện bắt đầu nào? | Kéo từ Ready vào Doing |
| **Finished** | Sự kiện hoàn tất nào? | Đạt điều kiện Done đã thống nhất |
| **Loại item** | Story, bug, incident, yêu cầu… | User story cùng mức lát cắt |
| **Tỷ lệ** | Bao nhiêu phần trăm? | 85% |
| **Ngưỡng** | Trong bao nhiêu thời gian? | 5 ngày lịch |
| **Nguồn dữ liệu** | Khoảng lịch sử và cỡ mẫu | Một số tuần gần đây, có kiểm tra dữ liệu |
| **Giới hạn** | Những trường hợp có thể khác | Bug khẩn, item quá lớn, thay DoW, kỳ nghỉ |

### 9.2. SLE không phải SLA hay deadline

- **SLE:** kỳ vọng xác suất dùng để thảo luận và dự báo, không tự động là nghĩa vụ hợp đồng.
- **SLA (Service Level Agreement):** thỏa thuận mức dịch vụ có thể kèm cam kết, điều kiện và trách nhiệm cụ thể.
- **Deadline:** mốc bắt buộc hoặc mục tiêu của một hạng mục; có thể cần ứng phó đặc biệt.

Một story có cycle time 7 ngày khi SLE là “85% trong 5 ngày” **không tự động là vi phạm hợp đồng**. Nó là một item nằm ngoài mức kỳ vọng của phần lớn dữ liệu, cần xem nguyên nhân và ảnh hưởng.

### 9.3. Đừng suy “p85 = 5” từ dữ liệu không tương đồng

Nếu tuần trước nhóm xử lý những story giao diện rất nhỏ, tuần sau cần migration dữ liệu phức tạp hoặc bug production nguy hiểm, **phân bố lịch sử có thể không phù hợp**.

Có thể phân nhóm theo:
- Loại item.
- Lớp dịch vụ (*class of service*) khi khác thật sự.
- Quy mô hạng mục hoặc đặc tính công việc đã được định nghĩa.
- Phụ thuộc và ranh giới chất lượng.
- Giai đoạn có chính sách làm việc khác.

Cẩn thận không chia nhỏ dữ liệu đến mức mỗi nhóm chỉ còn vài item và percentile lại thiếu độ tin cậy.

### 9.4. SLE giúp điều hành item đang mở

Nếu SLE tham khảo là 85% trong 5 ngày, một item đang có **work item age = 6 ngày** nên được kiểm tra:
- Đang ở trạng thái nào?
- Có blocker hoặc sự phụ thuộc nào?
- Cần giúp review, kiểm thử hay làm rõ nghiệp vụ?
- Có thay đổi phạm vi khiến item không còn giống tập lịch sử?
- Cần cập nhật người liên quan về bất định và phương án xử lý nào?

Một item **age lớn không phải bằng chứng một người làm việc kém**. SLE là tín hiệu giúp đội **tập trung hoàn tất và cộng tác**.

## 10. Cycle time scatterplot: xem thời gian hoàn thành biến động theo thời điểm nào

**Scatterplot** đặt mỗi item đã finished thành một điểm:
- **Trục X:** ngày hoặc thời điểm item finished (hoặc started, nhưng phải ghi rõ).
- **Trục Y:** cycle time của item ấy.
- **Mỗi điểm:** một work item.

Với tám story:

| Finished ngày | Item | Cycle time |
| ---: | --- | ---: |
| 3 | A | 2 |
| 5 | B | 4 |
| 6 | C | 4 |
| 7 | D | 4 |
| 9 | E | 5 |
| 10 | F | 5 |
| 12 | G | 6 |
| 13 | H | 5 |

Sơ đồ minh họa:

~~~text
Cycle time (ngày)
6 |                         G
5 |                   E  F        H
4 |       B  C  D
3 |
2 | A
1 |
  +-----------------------------------> Finished (ngày)
    3   5  6  7   9 10   12 13
~~~

### 10.1. Điều cần quan sát

- **Độ phân tán:** các điểm có tụ trong khoảng 4–5 ngày hay trải rộng?
- **Xu hướng:** ở giai đoạn sau item có mất thời gian dài hơn trước không?
- **Ngoại lệ:** có item đặc biệt lâu cần phân tích không?
- **Điểm dữ liệu thiếu:** có những item chưa finished bị loại khỏi scatterplot không?
- **Chính sách:** có thay Started/Finished hoặc DoD trong kỳ không?
- **Loại việc:** các điểm cao có phải một loại bug phức tạp riêng không?

Bộ dữ liệu tám item này có xu hướng các item hoàn tất sau có cycle time lớn hơn, nhưng **cỡ mẫu nhỏ và hệ thống là một lô được khởi tạo rồi hoàn tất**, nên không được tuyên bố nhóm “đang chậm dần” như một kết luận chung.

### 10.2. Scatterplot và histogram trả lời khác nhau

| Công cụ | Nhìn thấy tốt | Không trực tiếp trả lời |
| --- | --- | --- |
| **Histogram** | Bao nhiêu item ở mỗi khoảng cycle time? | Những item đó finished vào ngày nào? |
| **ECDF** | Bao nhiêu phần trăm finished trong ngưỡng t? | Điều gì gây chậm? |
| **Scatterplot** | Cycle time phân tán thế nào theo thời điểm finished? | Tổng số đang làm và hàng chờ từng bước? |
| **CFD** | WIP và trạng thái tích lũy thay đổi thế nào? | Percentile chính xác của cycle time per-item? |
| **Aging WIP** | Item đang mở nào đã già và ở đâu? | Cycle time cuối cùng của item chưa done? |

**Kết hợp công cụ thay vì tìm một biểu đồ làm mọi việc.**

## 11. Work item age: phần dễ bị che bởi phân bố item đã hoàn tất

Cycle time chỉ xuất hiện **sau khi item finished**. Nếu một số item bị chặn lâu, chúng có thể **không có mặt** trong phân bố cycle time của kỳ hiện tại.

Đó là một vấn đề khi nhóm chỉ nhìn những hạng mục đã hoàn tất rồi nói “mọi thứ đang nhanh”.

### 11.1. Ví dụ item còn mở tại ngày 11

Theo bảng A–H, cuối ngày 11 có:
- **G:** started ngày 6, chưa finished cho đến ngày 12. Age tại cùng mốc giờ ngày 11 là **11 − 6 = 5 ngày**.
- **H:** started ngày 8, chưa finished cho đến ngày 13. Age tại cùng mốc giờ ngày 11 là **11 − 8 = 3 ngày**.

Tại thời điểm ngày 11, **WIP = 2**. Hai item này **không được đưa vào phân bố cycle time của các item đã finished tính đến ngày 11**, nhưng phải được quan sát bằng work item age.

Nếu dùng dữ liệu biết tương lai để nói “G cycle time 6 ngày” tại ngày 11, nhóm đã dùng thông tin chưa xảy ra khi ra quyết định. Tại ngày 11 chỉ biết **G age = 5** và kết quả cuối còn bất định.

### 11.2. Aging WIP giúp ưu tiên gỡ chặn

Một bảng aging WIP có thể hiển thị:

| Item đang mở | Trạng thái | Started | Age hiện tại | Vấn đề cần hỏi |
| --- | --- | --- | --- | --- |
| G | Verify | Ngày 6 | 5 ngày | Có phụ thuộc môi trường hoặc lỗi kiểm thử? |
| H | Review | Ngày 8 | 3 ngày | Còn chờ reviewer hay đang review? |

Nên:
1. Xem item có age lớn hơn so với lịch sử của **loại công việc tương tự**.
2. Hỏi blocker và bước để hoàn tất.
3. Ưu tiên giúp item cũ đi qua dòng trước khi kéo thêm việc mới.
4. Cập nhật dự báo cho stakeholder khi cần.
5. Tránh dùng tuổi item để quy lỗi cho một thành viên.

### 11.3. Bias khi chỉ xem completed items

Giả sử tháng này có:
- 10 item nhỏ finished trong 1–3 ngày.
- 5 item lớn đã started nhưng đang mở từ 20 ngày.

Nếu chỉ lấy **10 item đã finished**, báo cáo “p85 rất thấp” có thể khiến stakeholder tưởng toàn bộ luồng đang trơn tru. Trong khi đó **5 item rất già đang nằm ngoài phân bố**. Đây là vấn đề **dữ liệu chưa có thời điểm kết thúc**, đôi khi gọi là *right-censoring* trong phân tích thời gian.

Đối với điều hành Agile, cách tối thiểu là **xem song song cycle time của completed items và tuổi WIP hiện tại**. Những phương pháp thống kê survival analysis cần thiết kế dữ liệu, điều kiện và chuyên môn riêng; không mặc định áp chúng chỉ từ một bảng ticket.

### 11.4. Không dùng work item age như cycle time cuối cùng

Nếu item chưa finished và age đã 12 ngày, cycle time cuối cùng sẽ **ít nhất ở mức 12 ngày nếu tiếp tục trong cùng hệ thống**, nhưng ta **chưa biết ngày hoàn tất**. Không được nhập 12 như một cycle time đã finished trong histogram hoặc ECDF.

Ngược lại, cũng không được xóa item đang kẹt khỏi WIP để làm đẹp các biểu đồ.

## 12. Hiểu Little's Law mà không biến nó thành công thức ra lệnh

Một quan hệ quan trọng trong hệ thống dòng công việc ổn định là **Little's Law**:

~~~text
WIP trung bình ≈ Throughput rate trung bình × Cycle time trung bình

Hay:
Cycle time trung bình ≈ WIP trung bình / Throughput rate trung bình
~~~

Quan hệ này hữu ích trong **điều kiện hệ thống và khoảng quan sát phù hợp**: các ranh giới nhất quán, lượng đầu vào/đầu ra không tăng tồn kho vô hạn, cách đo đơn vị nhất quán và có dữ liệu đủ đại diện.

### 12.1. Ví dụ riêng cho hệ thống tương đối ổn định

Giả sử một dịch vụ đã hoạt động tương đối ổn định trong một khoảng quan sát đủ dài:
- Throughput trung bình: **5 item/tuần**.
- Cycle time trung bình: **2 tuần**.

Khi các điều kiện áp dụng của Little's Law được đáp ứng, **WIP trung bình kỳ vọng khoảng 5 × 2 = 10 item**.

Điều đó **không phải luật yêu cầu đội phải có WIP = 10**. Nếu WIP tăng lên 20 trong khi throughput vẫn khoảng 5 item/tuần và không có thay đổi bối cảnh lớn, cycle time có nguy cơ dài hơn; nhóm nên điều tra sự tích lũy.

### 12.2. Vì sao không áp cơ học vào bộ A–H?

Bộ A–H là một **đợt khởi tạo hữu hạn rồi kết thúc**, không phải hệ thống ổn định lâu dài:
- Đầu kỳ Started tăng.
- Cuối kỳ ngừng nhận thêm việc.
- WIP quay về 0.

Không nên lấy một snapshot WIP ngày 6 rồi chia cho throughput của toàn bộ 13 ngày để tuyên bố có “cycle time chuẩn xác theo Little's Law”. Cần hiểu mẫu thời gian và điều kiện ổn định.

### 12.3. Giảm WIP không tự tạo giá trị nếu không thay nguyên nhân

Giảm WIP có thể hỗ trợ tập trung và giảm thời gian chờ. Nhưng:
- Giới hạn quá thấp có thể để năng lực hữu ích bị nhàn rỗi khi phụ thuộc hoàn toàn độc lập.
- Không thể giảm cycle time bằng cách đổi nhãn Started/Finished cho đẹp.
- Một hệ thống có WIP nhỏ nhưng chất lượng tồi vẫn phải làm lại.
- Nếu người dùng chờ ở Intake/Ready rất lâu, cycle time nội bộ ngắn không giải quyết lead time tổng.

Dùng Little's Law như **một lăng kính đặt câu hỏi**, không phải KPI để ép từng cá nhân “hoàn tất nhanh gấp đôi”.

## 13. Đọc CFD và phân bố cùng nhau: một ma trận chẩn đoán

Hai công cụ cung cấp thông tin khác nhau. Kết hợp chúng giúp tránh chẩn đoán sai.

| CFD quan sát | Cycle time distribution | Điều có thể đang xảy ra | Cần kiểm chứng thêm |
| --- | --- | --- | --- |
| **WIP nở liên tục** | Đuôi dài hơn | Bắt đầu quá nhiều, hàng chờ tăng hoặc block | Aging WIP, Review/Verify, loại item và phụ thuộc |
| **WIP ổn định** | Đuôi dài dai dẳng | Hệ thống ổn định về lượng nhưng nhiều item vẫn chờ lâu | Quy tắc ưu tiên, size, công việc ngoài luồng |
| **Review band dày lên** | Nhiều item finished chậm | Review có thể là điểm nghẽn | Thời gian chờ vs thời gian review, test và reviewer |
| **Done dốc hơn, WIP giảm** | Phân bố ngắn hơn | Có thể hoàn tất nhanh hơn | Chất lượng, loại item, DoW và Product Goal có đổi? |
| **Done tăng** | Phân bố không đổi hoặc xấu hơn | Có thể chỉ tăng lượng item/hậu quả tăng công sức | WIP, sự cố, tính đúng và loại item |
| **Ít thay đổi các đường** | Không nhiều điểm mới | Dòng việc có thể đứng, hoặc đơn giản ít demand | Arrival, nguồn yêu cầu, item đang mở |
| **WIP thấp** | Một số item rất già | Một vài hạng mục tồn đọng có thể không thấy trên histogram | Work item age, blocked reasons, dữ liệu chưa finished |
| **Dải mỏng đột ngột** | Phân bố thay đổi bất thường | Có thể đổi chính sách, đóng bulk hoặc di chuyển ticket | Lịch sử trạng thái, timestamp và cancellation |

### 13.1. Quy trình đọc biểu đồ trong một cuộc review 15 phút

1. **Phạm vi:** Dịch vụ nào? Loại item, ranh giới Started/Finished và kỳ đo nào?
2. **CFD:** Đường Started và Done có đang tách xa? Dải nào dày lên? Khi nào điều đó bắt đầu?
3. **Throughput:** Số item finished theo khoảng có biến động lớn không?
4. **Cycle time:** Histogram/ECDF cho biết bao nhiêu phần trăm finished trong ngưỡng, đuôi dài thế nào?
5. **Aging WIP:** Các item chưa xong có age cao nằm ở bước nào?
6. **Bối cảnh:** Có bug production, nghỉ lễ, đổi DoD, release lớn hoặc dữ liệu thiếu không?
7. **Hành động:** Một thử nghiệm cải tiến nhỏ, có owner, điều kiện đo và thời điểm xem lại.
8. **Giá trị:** Cải tiến dòng công việc có giúp người dùng nhận được tính năng đúng và đáng tin không?

### 13.2. Đặt vấn đề bằng câu hỏi thay vì chỉ số

Thay vì: “Review dày, mọi người phải review nhanh hơn.”

Nên hỏi: “Trong ba tuần, Review band tăng từ 3 lên 10 item và cycle time p85 của các story cùng loại cũng tăng. Những item nào đang chờ, lý do là gì, WIP policy hiện tại có đang khiến Developers tiếp tục kéo việc mới khi Review đầy không?”

Câu hỏi thứ hai **nêu bằng chứng, giữ mở giả thuyết và dẫn tới hành động**.

## 14. Data quality: biểu đồ đúng phải bắt đầu từ sự kiện đáng tin

Một CFD đẹp nhưng dữ liệu sai có thể gây quyết định tệ hơn việc không có biểu đồ.

### 14.1. Các trường dữ liệu quan trọng

Với một bảng item lịch sử, tối thiểu nên có:
- **item_id** ổn định.
- **item_type** và dịch vụ/luồng.
- **started_at** theo ranh giới DoW.
- **finished_at** nếu đã finished.
- **status transitions** (thời điểm vào/ra trạng thái).
- **outcome** như completed, cancelled, duplicate, rejected theo chính sách.
- **blocked intervals** hoặc nguyên nhân khi cần điều tra.
- **version của DoW/DoD** khi chính sách thay đổi.
- **thời gian và múi giờ** ghi nhận.

Dữ liệu có thể lấy từ hệ thống theo dõi công việc, nhưng việc trạng thái thay đổi trong tool **không bảo đảm hành vi thực đã diễn ra đúng lúc**.

### 14.2. Các kiểm tra tính nhất quán

~~~text
Với item đã finished:
    started_at phải có và không sau finished_at.

Tại một snapshot của luồng đơn giản:
    Started cumulative = WIP + Finished cumulative
    (nếu không có cancellation/reopen/chuyển luồng và baseline = 0).

Ở mỗi snapshot:
    WIP = tổng các trạng thái đã started chưa finished.

Trong một tập đo:
    item_id không được đếm trùng như hai item hoàn tất
    nếu không có chính sách tạo item mới hợp lệ.

Về thời gian:
    cùng timezone, cùng cách quy đổi ngày lịch/ngày làm việc.
~~~

Với hệ thống phức tạp, công thức bảo toàn cần ghi riêng **các đầu vào/đầu ra ngoài phạm vi**, không gượng ép mọi item hủy thành “completed”.

### 14.3. Những vấn đề dữ liệu điển hình

| Tình huống | Biểu đồ có thể bị sai thế nào? | Cách xử lý |
| --- | --- | --- |
| Chuyển thẻ sang Done cuối ngày thứ Sáu dù hoàn tất từ thứ Ba | Throughput bị dồn vào thứ Sáu, cycle time dài giả tạo | Ghi sự kiện đúng lúc, quy ước timestamp |
| Chuyển blocked từ Review về Ready trước Started | WIP và tuổi item thấp giả | Giữ dấu Started, đánh dấu blocked theo chính sách |
| Reset Started khi item quay về Doing | Cycle time ngắn giả | Giữ lịch sử hoặc tạo item mới theo quy tắc rõ |
| Đếm “Closed – Duplicate” là Done của dịch vụ phát triển | Throughput tăng không tạo giá trị | Tách các loại kết quả |
| Xóa item Done khỏi hệ thống | Đường Done tích lũy có thể giảm sai | Dùng lịch sử completion events hoặc snapshot đúng |
| Nhiều item đã started trước kỳ đo | Đường trên/dưới thiếu baseline | Mang theo tồn đầu kỳ hoặc thiết kế khoảng đo phù hợp |
| Đổi DoD từ “merge” sang “deployed” | Cycle time thay dù tốc độ thực chưa chắc đổi | Ghi version/điểm gãy, không so trực tiếp |
| Merging/splitting ticket ở giữa luồng | Item count và size đổi | Chính sách lineage, loại item và cách tính |
| Dùng ngày làm việc cho vài item, ngày lịch cho item khác | Phân bố sai đơn vị | Chuẩn hóa và ghi cách tính |
| Thiếu trạng thái phụ thuộc | Dải Doing che thời gian chờ | Thêm blocked/queue signal khi hữu ích |
| Bulk import dữ liệu cũ | Started nhảy vọt giả | Phân biệt thời điểm thực và thời điểm nhập hệ thống |

### 14.4. Reopen làm CFD phức tạp hơn

Nếu item đã Done được mở lại:
- Một CFD dựa **vào trạng thái hiện tại** có thể khiến Done giảm ở snapshot sau, mâu thuẫn cách hiểu “cộng dồn hoàn tất”.
- Một CFD dựa **vào sự kiện hoàn tất bất biến** có thể đếm item như finished dù nó đang được làm lại.
- Nếu mỗi lần reopen được đếm như một completion mới, throughput có thể tăng giả.

Nhóm cần chính sách: reopen trước khi thật sự đạt DoD là **chưa hoàn tất**, bug mới sau phát hành có thể là **work item khác liên kết**, và các sửa dữ liệu phải giữ lịch sử. **Không có công thức CFD duy nhất hoạt động đúng cho mọi chính sách reopen nếu chưa định nghĩa kết quả.**

### 14.5. Bảo vệ dữ liệu khi làm dashboard

Để đọc dòng công việc, thường không cần đưa lên dashboard công khai:
- Tên từng cá nhân cùng thông tin về sự cố riêng tư.
- Nội dung ticket chứa dữ liệu khách hàng.
- Email/số điện thoại học viên.
- Các trường nhạy cảm trong log hoặc phân loại đối tượng.

Ưu tiên biểu đồ cấp nhóm, mã item và metadata vừa đủ cho mục đích điều hành. Việc đánh giá hiệu quả cá nhân chỉ bằng cycle time thường **dễ bị bóp méo** bởi độ khó, phụ thuộc và việc hỗ trợ người khác.

## 15. Phân biệt mô hình dòng tích lũy với nguồn dữ liệu chưa đầy đủ

### 15.1. Snapshot và event log khác nhau

**Snapshot cuối ngày:** biết mỗi item ở trạng thái nào khi kết thúc ngày. Nó có thể dựng CFD theo ngày, nhưng không phản ánh các lần chuyển nhiều trạng thái trong cùng ngày.

**Event log:** biết chính xác thời điểm item vào từng trạng thái. Có thể tái dựng snapshot, cycle time và phân tích sâu hơn, nếu dữ liệu đầy đủ và timestamp đáng tin.

Ví dụ một item bắt đầu Doing buổi sáng, chuyển Review buổi trưa, rồi Done buổi chiều. Một snapshot cuối ngày chỉ ghi **Done**. Để tính cycle time dưới một ngày hoặc thời gian Review, cần **event log hoặc dấu mốc trực tiếp**, không thể suy từ snapshot.

### 15.2. Định nghĩa thời điểm quan sát

Với CFD theo ngày:
- Chọn **múi giờ nhất quán**.
- Chốt thời điểm snapshot, ví dụ 23:59 hoặc cuối ngày làm việc đã thống nhất.
- Giữ ngày cuối tuần nếu dùng **ngày lịch**, hoặc giải thích cách bỏ ngày không làm việc.
- Ghi sự kiện trước/sau snapshot rõ ràng.

Không nên kết hợp “snapshot cuối ngày lịch” với cycle time tính theo “chỉ số ngày làm việc” mà không nói rõ người đọc đang so hai loại thời gian khác nhau.

### 15.3. Cách dựng bảng dữ liệu mẫu không cần công cụ đắt tiền

1. Xuất danh sách item và lịch sử chuyển trạng thái của **một luồng rõ**.
2. Chuẩn hóa Started/Finished và loại item.
3. Tạo các mốc ngày quan sát.
4. Ở mỗi mốc, đếm số item trong từng trạng thái đã started chưa finished.
5. Tính Done cộng dồn và Started cộng dồn theo chính sách.
6. Tính các ranh giới L0–L3 rồi vẽ vùng xếp chồng.
7. Với mỗi item finished, tính cycle time từ hai timestamp thực.
8. Vẽ histogram, ECDF hoặc scatterplot.
9. Với item chưa finished, tính work item age tại cùng thời điểm.
10. Kiểm tra một số item thủ công để xác nhận sự kiện phản ánh đúng thực tế.

Không cần viết một hệ thống analytics riêng trước khi nhóm hiểu **những câu hỏi cần trả lời**.

## 16. Kết nối số đo dòng với Scrum, Kanban, XP và giá trị người dùng

### 16.1. Kanban: cải thiện cách công việc đi qua hệ thống

Kanban nhấn mạnh:
- Định nghĩa workflow, started và finished.
- Trực quan hóa công việc và các trạng thái.
- Kiểm soát **WIP**.
- Quản lý item đang già đi.
- Quan sát **throughput, cycle time, work item age**.
- Dùng dữ liệu để thử cải tiến chính sách và tăng khả năng dự báo.

CFD là công cụ nhìn **dòng tích lũy**; phân bố cycle time giúp thiết lập kỳ vọng có điều kiện. Không có quy định mọi nhóm Kanban phải dùng cùng bộ cột hoặc cùng ngưỡng thời gian.

### 16.2. Scrum: flow metrics bổ sung chứ không thay thế Scrum

Trong Scrum:
- **Product Goal** định hướng giá trị sản phẩm.
- **Product Backlog** do Product Owner quản lý hiệu quả và sắp thứ tự.
- **Sprint Goal** giúp Developers tập trung vào mục tiêu của Sprint.
- **Definition of Done** bảo đảm Increment đáp ứng chất lượng đã thống nhất.
- **Sprint Review** kiểm tra kết quả và học từ stakeholder.
- **Sprint Retrospective** kiểm tra cách làm việc, tìm cải tiến.

CFD có thể cho thấy story dồn ở Review cuối Sprint; phân bố cycle time cho thấy hạng mục hoàn tất mất thời gian khác nhau thế nào. Nhưng **Scrum không quy định phải có CFD hay một mức p85 cụ thể**.

Nếu định nghĩa Finished = đạt DoD, thì mọi item trong phân bố phải dựa cùng tiêu chuẩn. Không được giảm DoD để làm đường Done dốc hơn vào ngày cuối Sprint.

### 16.3. Velocity khác throughput và cycle time

| Chỉ số | Đơn vị thường gặp | Mục đích hợp lý | Không dùng để suy trực tiếp |
| --- | --- | --- | --- |
| **Velocity** | Story points finished/Sprint, nếu nhóm dùng points | Tham khảo lịch sử lập kế hoạch trong nhóm | Năng suất cá nhân, giá trị người dùng, giờ công tuyệt đối |
| **Throughput** | Số item finished/khoảng | Nhìn khả năng hoàn tất của một luồng | Giá trị mỗi item hoặc chất lượng nếu không đo thêm |
| **Cycle time** | Giờ/ngày/tuần từ Started đến Finished | Thời gian item đi qua luồng | Tổng lead time từ yêu cầu nếu Started nằm sau arrival |
| **WIP** | Số item đang mở | Mức tồn và khả năng tập trung | Mức bận của từng cá nhân |
| **Outcome metric** | Tỷ lệ hoàn thành mục tiêu, lỗi nghiệp vụ, phản hồi… | Người dùng có nhận giá trị? | Nguyên nhân chắc chắn nếu không có thiết kế đo phù hợp |

Nếu nhóm đóng 20 story rất nhỏ thay vì 5 story lớn, throughput tăng nhưng chưa đủ nói năng lực hoặc giá trị tăng. Cần hiểu tập item, size, chất lượng và mục tiêu.

### 16.4. XP và chất lượng ảnh hưởng tới phân bố

Các thực hành XP như **TDD, CI, pair programming, refactoring, small releases** có thể giúp giảm lỗi phát hiện muộn, giảm việc làm lại và làm cho các hạng mục dễ đi qua dòng hơn.

Nhưng:
- Khi mới bổ sung test hoặc nâng DoD, cycle time có thể tăng trong ngắn hạn.
- Test xanh không tự đồng nghĩa người dùng nhận giá trị.
- Giảm cycle time bằng cách bỏ kiểm thử có thể gây nhiều sự cố sau phát hành.
- Độ khó item, sự cố và phụ thuộc cũng làm phân bố biến động.

Muốn đánh giá cải tiến kỹ thuật, nên xem **flow + quality + outcome**, không chỉ một percentile.

### 16.5. Không tối ưu biểu đồ thay cho người dùng

Bài toán thực của nhóm workshop là học viên **có thể đăng ký đúng chỗ và hiểu trạng thái**. Dòng công việc nhanh hơn chỉ đáng giá nếu:
- Phần mềm giữ quy tắc sức chứa.
- Không lộ dữ liệu.
- Ít lỗi nghiêm trọng hơn.
- Người dùng nhận được Increment có ích sớm và thường xuyên hơn.
- Khả năng giao hàng có thể duy trì qua nhiều vòng.

**Một CFD “đẹp” không bù được sản phẩm xác nhận sai chỗ.**

## 17. Tình huống thực hành: nhóm workshop tìm nguyên nhân giao hàng chậm

### 17.1. Vấn đề

Trong sáu tuần, Product Owner nhận phản hồi rằng các thay đổi về trạng thái đăng ký được bàn giao thất thường. Developers báo “chúng ta vẫn đóng nhiều story”, nhưng Support thấy đôi khi học viên phải chờ lâu để được sửa lỗi hiển thị.

Nhóm thu được dữ liệu **giả định**:

| Tín hiệu | Ba tuần đầu | Ba tuần sau |
| --- | ---: | ---: |
| Throughput trung bình/tuần | 9 item | 9 item |
| WIP tại cuối giai đoạn | 10 item | 18 item |
| Số item ở Review | 3 | 9 |
| Cycle time p85 theo cùng phương pháp | 7 ngày | 12 ngày |
| Lỗi nghiêm trọng sau bàn giao | 1 | 2 |
| Item có age vượt SLE đang mở | 2 | 6 |

Đọc có trách nhiệm:
- Throughput trung bình **không tăng** dù WIP lớn hơn.
- Dải Review dày hơn gợi ý tồn kho có thể đang tăng ở bước này.
- Cycle time p85 tăng gợi ý đuôi thời gian hoàn tất dài hơn.
- Số item đang già đi tăng là tín hiệu cần chú ý ngoài histogram.
- Chất lượng cần được xem cùng vì lỗi sau bàn giao cũng tăng.

Nhưng số liệu **chưa chứng minh Review là nguyên nhân duy nhất**. Có thể trong ba tuần sau nhóm xử lý user stories lớn hơn, một phiên bản test mới tạo thêm bước kiểm tra hoặc xảy ra gián đoạn.

### 17.2. Điều tra ngắn thay vì quy lỗi

Nhóm chọn một mẫu item đang ở Review:
- Ba item chờ reviewer chuyên về phân quyền.
- Hai item chưa có test tích hợp đủ để review có ý nghĩa.
- Bốn item đã review sơ bộ nhưng còn phụ thuộc làm rõ trạng thái.

Cách làm:
1. Phân biệt **chờ Review** và **Review đang tiến hành**.
2. Xem WIP policy có để Developers kéo item mới khi Review đầy không.
3. Pairing/chia sẻ hiểu biết ở vùng mã phân quyền.
4. Thêm test cho các tình huống lặp lại theo rủi ro.
5. Chọn một giới hạn WIP thử và quy tắc hỗ trợ hoàn tất.
6. Theo dõi quality guardrails và phản hồi người dùng sau thay đổi.

Các số phân loại là **giả định của tình huống**, dùng để chỉ ra dữ liệu cần thu, không phải mô tả thực một nhóm.

### 17.3. Thử nghiệm cải tiến có mốc

Ví dụ hypothesis:

> “Nếu trong hai tuần tới nhóm giới hạn số item mới started khi Review đầy và bổ sung pairing ở vùng phân quyền, số item chờ review lâu sẽ giảm, trong khi DoD và lỗi sau bàn giao không xấu đi.”

Để kiểm tra:
- **Baseline:** số item ở Review, work item age, throughput, cycle time distribution của item cùng loại, lỗi sau phát hành.
- **Can thiệp:** chính sách WIP và pairing, không bỏ test.
- **Khoảng thử:** đủ để quan sát một số item hoàn tất và item còn mở; hai tuần chỉ là ví dụ.
- **Đánh giá:** dải Review, WIP, percentile, tuổi item còn mở và chất lượng.
- **Biến gây nhiễu:** thay đổi loại việc, nghỉ phép, incident hoặc định nghĩa Done.
- **Quyết định tiếp:** giữ/chỉnh/dừng thử, ghi điều chưa thể kết luận.

Đây là **một thử nghiệm về hệ thống công việc**, không phải “đặt chỉ tiêu mọi người phải review nhanh hơn 20%”.

### 17.4. Cách báo cáo stakeholder

Một thông điệp rõ có thể là:

> “Hiện throughput của hai giai đoạn tương đương, nhưng số việc đang mở và tồn ở Review tăng. Phân bố cycle time của nhóm item cùng loại có đuôi dài hơn, còn nhiều item đang mở đã lớn tuổi. Nhóm đang thử chính sách hạn chế bắt đầu việc mới khi Review đầy, đồng thời cải thiện kiểm thử và chia sẻ kiến thức. Chúng tôi sẽ xem cả số việc hoàn tất, thời gian, lỗi và phản hồi người dùng trước khi kết luận có cải thiện.”

Thông điệp này không hứa rằng tất cả story sẽ xong trong một ngưỡng khi dữ liệu chưa đủ, nhưng cho stakeholder thấy **tín hiệu, giả thuyết và hành động cụ thể**.

## 18. Các lỗi diễn giải thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nhìn chiều cao đường Started và gọi đó là WIP | Đó là số tích lũy, không phải số đang làm | WIP = Started − Finished theo cùng ranh giới và thời điểm |
| Nhìn chiều dày Review và kết luận reviewer làm chậm | Dải chỉ cho thấy tồn kho, không phải nguyên nhân | Xem queue, block, size và lịch sử |
| Dùng khoảng ngang CFD như cycle time của từng item | Item thứ N started không chắc là item thứ N finished | Tính per-item từ timestamps |
| Chỉ báo cycle time trung bình | Che độ phân tán và đuôi dài | Thêm median, histogram/ECDF/percentile |
| Coi p85 là deadline chắc chắn | Percentile mô tả phân bố, không bảo đảm item cá biệt | Phát biểu ngưỡng và tỷ lệ, điều kiện dữ liệu |
| Tính percentile không công bố phương pháp | Nearest-rank và interpolation có thể khác | Ghi phương pháp, cỡ mẫu, đơn vị |
| Dùng 8 item để dự báo như dữ liệu lớn | Mẫu rất ít, dễ bị một item chi phối | Công bố hạn chế và tiếp tục thu dữ liệu |
| Chỉ xem item đã Done | Bỏ qua item rất lâu chưa finished | Xem aging WIP song song |
| Xóa outlier vì trông xấu | Che rủi ro thật | Điều tra và chỉ tách loại có căn cứ |
| So cycle time khi một kỳ đo từ Ready, kỳ khác từ Doing | Ranh giới khác tạo chênh lệch giả | Chuẩn hóa hoặc tách giai đoạn |
| Đếm cancel/duplicate như giá trị bàn giao | Throughput bị thổi phồng | Quy định outcome và cách tính |
| Bulk-close vào thứ Sáu | Tạo nhịp Done ảo | Ghi sự kiện thực và kiểm dữ liệu |
| Lấy tăng throughput làm bằng chứng tăng giá trị | Item size/quality có thể khác | Gắn Product Goal, outcome, defects |
| Tối ưu WIP bằng cách chuyển blocked ra khỏi luồng | Biểu đồ đẹp, người dùng vẫn chờ | Giữ item trong WIP theo DoW |
| Nhận diện một nút thắt từ một snapshot | Biến động ngày thường có thể không đại diện | Xem nhiều kỳ và item history |
| Áp Little's Law vào một lô hữu hạn mới bắt đầu | Không bảo đảm điều kiện ổn định | Dùng khi phạm vi và điều kiện phù hợp |
| Xếp hạng Developers bằng cycle time cá nhân | Độ khó, phụ thuộc và hỗ trợ không tương đương | Dùng số đo cấp hệ thống để học |
| Dùng ngày lịch lẫn ngày làm việc | Tính toán không cùng đơn vị | Ghi chuẩn thời gian trước khi đo |
| Thay DoD để tăng đường Done | Giảm chất lượng, số liệu giả cải thiện | Giữ guardrail và ghi thay đổi chính sách |
| Dùng số liệu mà không có câu hỏi quyết định | Dashboard nhiều nhưng không giúp cải tiến | Gắn tín hiệu với giả thuyết, hành động và mốc xem lại |

## 19. Bài thực hành có đáp án định hướng

### 19.1. Bài A – Đọc WIP từ ranh giới CFD (10 phút)

Một CFD có Done ở đáy và Started ở trên cùng. Cuối các ngày:

| Ngày | Started cộng dồn | Done cộng dồn |
| ---: | ---: | ---: |
| 1 | 15 | 10 |
| 2 | 20 | 12 |
| 3 | 28 | 14 |
| 4 | 34 | 20 |
| 5 | 39 | 29 |

Yêu cầu:
1. Tính WIP từng ngày.
2. Ngày nào WIP tăng mạnh nhất?
3. Throughput trong khoảng từ cuối ngày 3 tới cuối ngày 5 là bao nhiêu?
4. Có thể kết luận số item Review đã tăng không?
5. Nếu user story đã started trước kỳ, cần kiểm tra gì trong nguồn dữ liệu?

**Đáp án:**
- WIP = **5, 8, 14, 14, 10**.
- Từ ngày 2 sang 3, WIP tăng **6** là mức tăng lớn nhất.
- Throughput từ cuối ngày 3 tới cuối ngày 5 = **29 − 14 = 15 item**, nếu không có cách đóng đặc biệt.
- **Không thể biết Review riêng** khi chỉ có Started và Done; cần thêm đường/dải trạng thái.
- Kiểm tra baseline, ranh giới, outcome và tính nhất quán đầu kỳ.

### 19.2. Bài B – Phân tích một dải nghẽn (10 phút)

Biểu đồ cho thấy Review band tăng từ 2 lên 10 item trong ba tuần. Throughput không tăng.

Hãy nêu:
1. Ba giả thuyết nguyên nhân.
2. Ba dữ liệu cần xem thêm.
3. Một hành động cải tiến nhỏ không hạ chất lượng.
4. Điều kiện nào khiến bạn đổi giả thuyết?
5. Vì sao không nên đánh giá một reviewer theo dải Review?

**Gợi ý:** review thiếu khả năng, item quá lớn, test/requirement chưa đủ rõ; xem blocked reason, lịch sử chuyển trạng thái, review queue age, size, nhân sự phụ thuộc và DoD. Thử pairing/hạn chế start mới và quan sát kết quả.

### 19.3. Bài C – Dựng bảng tần suất và ECDF (15 phút)

Cho tám cycle times theo ngày lịch:

~~~text
[2, 4, 4, 4, 5, 5, 6, 5]
~~~

Yêu cầu:
1. Sắp xếp tăng dần.
2. Tính min, max, mean, median.
3. Tính tỷ lệ hoàn tất trong **4 ngày hoặc ít hơn**.
4. Tính tỷ lệ hoàn tất trong **5 ngày hoặc ít hơn**.
5. Tính p85 theo nearest-rank.
6. Viết câu dự báo cẩn trọng đúng với mẫu.

**Đáp án:** Sắp xếp **[2,4,4,4,5,5,5,6]**; min 2; max 6; mean **4,375**; median **4,5**; ≤4 ngày **4/8 = 50%**; ≤5 ngày **7/8 = 87,5%**; nearest-rank p85 là giá trị thứ 7, **5 ngày**. Dữ liệu chỉ mô tả **tám item đã hoàn tất**.

### 19.4. Bài D – Kết hợp cycle time và work item age (15 phút)

Tại thời điểm ngày 11 của bộ A–H:
1. Những item nào chưa finished?
2. WIP bằng bao nhiêu?
3. Tuổi G và H bằng bao nhiêu ngày?
4. Có thể đưa G và H vào histogram của các item finished tại ngày 11 không?
5. Nếu một item đang age 12 ngày còn p85 lịch sử là 5 ngày, nên làm gì?

**Đáp án:** G và H; **WIP = 2**; G age **5 ngày** (11 − 6), H age **3 ngày** (11 − 8). Chúng **chưa có cycle time cuối cùng** tại ngày 11. Item age 12 ngày cần kiểm tra blocker, phạm vi, khả năng hỗ trợ và cập nhật dự báo; không tự kết luận có lỗi cá nhân.

### 19.5. Bài E – Lý do hai biểu đồ có thể không thống nhất (15 phút)

Một dashboard cho thấy WIP giảm mạnh từ 18 xuống 6 trong một ngày, nhưng throughput chỉ tăng hai item.

Hãy đề xuất ít nhất bốn khả năng:
- Item bị hủy hoặc chuyển qua workflow khác.
- Bộ lọc/loại item thay đổi.
- Started point được sửa.
- Công cụ bulk-move những thẻ chưa hoàn tất.
- Một số item reopen hoặc được gộp.
- Cách ghi dữ liệu bị thiếu.
- Một thay đổi thực sự trong quá trình xử lý.

Giải thích cần xem lịch sử event và chính sách nào để phân biệt. **Không ép kết luận “năng suất tăng vượt bậc” từ một điểm dữ liệu.**

### 19.6. Bài F – Tính throughput và WIP giả định bằng Little's Law (10 phút)

Một hệ thống có dữ liệu nhiều kỳ, vận hành tương đối ổn định:
- Throughput trung bình **6 item/tuần**.
- Cycle time trung bình **1,5 tuần**.

1. Theo quan hệ Little's Law ở điều kiện áp dụng, WIP trung bình khoảng bao nhiêu?
2. Nếu dashboard có WIP 25 ở một ngày, có thể kết luận vi phạm ngay không?
3. Điều gì xảy ra nếu throughput giữ nguyên còn WIP tăng kéo dài?
4. Vì sao không dùng công thức để ép mỗi người làm nhanh hơn?

**Đáp án:** 6 × 1,5 = **9 item WIP trung bình** theo giả định ổn định. Một snapshot 25 chưa đủ vì có thể là biến động hoặc thay đổi phạm vi; cần xem xu hướng và data quality. Nếu WIP tăng kéo dài mà throughput không đổi, thời gian hoàn tất có thể dài hơn trong hệ thống tương ứng.

### 19.7. Bài G – Phân biệt SLE với cam kết (10 phút)

Nhóm có dữ liệu lịch sử tương đối phù hợp và phát biểu: **85% item hoàn tất trong 8 ngày lịch hoặc ít hơn**.

Hãy trả lời:
1. Nó nói gì về 15% item còn lại?
2. Item age 9 ngày có đồng nghĩa một nhân viên vi phạm hợp đồng không?
3. Nếu Product Owner cần chắc chắn giao một tính năng trước ngày tổ chức workshop, có thể chỉ dùng SLE không?
4. SLE có cần làm lại khi nhóm đổi từ “merge” sang “deployed” làm Finished không?

**Gợi ý:** SLE là kỳ vọng xác suất, không bảo đảm mọi item. Với deadline thực, cần xét phụ thuộc, phạm vi, rủi ro, năng lực, phương án dự phòng và cam kết liên quan. Khi đổi Finished, dữ liệu và cách diễn giải **phải được cập nhật**.

### 19.8. Bài H – Thiết kế dashboard của một nhóm (20 phút)

Nhóm tự chọn một dịch vụ phát triển phần mềm và tạo bản nháp dashboard gồm:
- CFD với chú giải dải trạng thái và Started/Finished.
- Throughput theo tuần.
- Cycle time scatterplot.
- Histogram hoặc ECDF với percentile có phương pháp.
- Aging WIP của item chưa finished.
- Loại item, kỳ, đơn vị thời gian và phiên bản DoW.
- Một quality guardrail và một outcome người dùng.
- Một câu hỏi điều hành mà dashboard phải giúp trả lời.

Yêu cầu người khác xem dashboard **không được giải thích trước** rồi trả lời:
1. WIP có đang nở không?
2. Dải nào cần điều tra?
3. 85% item mẫu finished trong bao lâu?
4. Item đang mở nào có age cao?
5. Có đủ bằng chứng để thay đổi quy trình không?
6. Những điều **chưa thể kết luận** là gì?

Nếu người đọc không thể trả lời hoặc hiểu nhầm mẫu số, cần sửa cách đặt tên, chú giải và định nghĩa.

### 19.9. Bài I – Chọn một thử nghiệm cải tiến (15 phút)

CFD cho thấy Review band tăng, scatterplot có nhiều item dài ngày và aging WIP cho thấy ba item lớn tuổi chờ reviewer.

Hãy viết:
- Giả thuyết và dữ liệu hỗ trợ.
- Can thiệp nhỏ trong hai tuần.
- Owner của chính sách và cách phối hợp.
- Metric trước/sau về WIP, Review wait, cycle time và lỗi.
- Tác dụng phụ cần theo dõi.
- Mốc xem lại và điều kiện giữ/chỉnh/dừng thử.

Không sử dụng yêu cầu “mỗi người phải tăng 30% throughput” như biện pháp mặc định.

### 19.10. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Ranh giới và dữ liệu** | Không rõ Started/Finished | Tính số đo theo mốc nhất quán | Xử lý baseline, cancellation, reopen và chính sách đổi |
| **Đọc CFD** | Nhầm đường tích lũy thành WIP | Đọc dải, WIP và độ dốc đúng | Nhìn biến động qua nhiều kỳ, đặt giả thuyết có căn cứ |
| **Đọc phân bố** | Chỉ xem mean | Có histogram, median, ECDF, percentile | Hiểu đuôi dài, cỡ mẫu, bias và phương pháp |
| **Aging WIP** | Bỏ qua việc chưa hoàn tất | Theo dõi tuổi item và blocker | Kết hợp SLE và ưu tiên hoàn tất không đổ lỗi |
| **Dự báo** | Coi p85 là deadline chắc chắn | Nêu xác suất, ngưỡng, tập dữ liệu | Biết trường hợp dữ liệu không còn áp dụng |
| **Cải tiến Agile** | Dùng metric xếp hạng người | Chọn một can thiệp và đo lại | Kết hợp flow, chất lượng, Product Goal và phản hồi |

## 20. Biểu mẫu có thể dùng ngay

### 20.1. Mẫu định nghĩa dữ liệu cho dashboard

~~~text
Dịch vụ / workflow:
Đối tượng nhận giá trị:
Work item type:
Kích thước/mức phân rã item:
Started = sự kiện:
Finished = sự kiện:
Các trạng thái giữa Started và Finished:
Blocked có tính WIP không:
Cancellation / duplicate / reopen được xử lý thế nào:
Snapshot hay event log:
Timezone:
Đơn vị cycle time: giờ / ngày lịch / ngày làm việc:
Khoảng dữ liệu, bộ lọc và số item:
Phiên bản DoW/DoD:
Owner và ngày kiểm tra chất lượng dữ liệu:
~~~

### 20.2. Mẫu đọc CFD trong 10 phút

~~~text
Khoảng thời gian và đối tượng:
Started đầu kỳ/cuối kỳ:
Done đầu kỳ/cuối kỳ:
WIP đầu kỳ/cuối kỳ:
Throughput trong kỳ:
Dải trạng thái nở:
Dải trạng thái thu:
Item age đáng chú ý:
Có thay đổi chính sách/bulk edit không:
Ba giả thuyết nguyên nhân:
Dữ liệu cần kiểm thêm:
Quyết định tạm và mốc xem lại:
~~~

### 20.3. Mẫu đọc phân bố cycle time

~~~text
Loại item và ranh giới:
Số item finished trong mẫu:
Min / Max:
Mean:
Median:
Percentile và phương pháp tính:
Tỷ lệ hoàn tất <= ngưỡng:
Các outliers và lý do nếu biết:
Có item còn mở bị loại khỏi phân bố không:
Aging WIP hiện tại:
Đơn vị thời gian:
Những thay đổi DoW/DoD trong kỳ:
SLE phù hợp hay chưa, vì sao:
Các giới hạn khi sử dụng để dự báo:
~~~

### 20.4. Mẫu đề xuất cải tiến dòng công việc

~~~text
Vấn đề theo Product Goal:
Tín hiệu CFD:
Tín hiệu cycle time/ECDF:
Tín hiệu aging WIP:
Dữ liệu về chất lượng và outcome:
Giả thuyết cần kiểm:
Can thiệp nhỏ:
Chính sách WIP/Review/Verify liên quan:
Thời gian và owner thử:
Baseline và ngưỡng theo dõi:
Tác dụng phụ/guardrails:
Cách xử lý nếu can thiệp làm xấu đi:
Kết quả sau thử:
Quyết định giữ/chỉnh/dừng:
~~~

Biểu mẫu không phải quy định bắt buộc của Scrum hoặc Kanban. Chúng chỉ hữu ích nếu giúp nhóm **nhìn đúng vấn đề, đưa ra lựa chọn và học từ kết quả**.

## 21. Checklist trước khi dùng CFD và phân bố thời gian để ra quyết định

**Dòng công việc và tính đúng của dữ liệu:**

- [ ] Mọi người hiểu loại work item nào đang được đo.
- [ ] Started và Finished là sự kiện rõ, không thay đổi âm thầm.
- [ ] Trạng thái giữa Started và Finished được ghi nhất quán.
- [ ] Blocked vẫn tính WIP theo chính sách; thời gian chờ không bị xóa.
- [ ] Mốc thời gian dùng cùng múi giờ và đơn vị.
- [ ] Cancellation, duplicate, reopen và item chuyển dịch vụ có quy tắc riêng.
- [ ] Tồn đầu kỳ và item đã started từ trước được xử lý đúng.
- [ ] Một vài item được đối chiếu thủ công với lịch sử thật.

**Đọc CFD:**

- [ ] Biết trục X, trục Y, chú giải và thứ tự các dải.
- [ ] WIP được đọc theo khoảng cách **dọc** giữa Started và Done.
- [ ] Dải trạng thái được tính bằng chênh lệch hai đường kề nhau.
- [ ] Throughput đọc từ mức tăng của Done trong khoảng.
- [ ] Không suy một nguyên nhân chỉ từ dải đang dày.
- [ ] Khoảng ngang được diễn giải thận trọng, không gán nhầm cho cycle time per-item.
- [ ] Các đường tăng giảm bất thường được kiểm tra cùng thay đổi dữ liệu/chính sách.

**Đọc phân bố cycle time:**

- [ ] Có dữ liệu per-item started/finished, không chỉ hình CFD.
- [ ] Histogram hoặc bảng tần suất thể hiện cả phần đuôi dài.
- [ ] Median, mean và percentile được diễn giải đúng mục đích.
- [ ] Phương pháp tính percentile, mẫu, loại item và kỳ được công bố.
- [ ] ECDF trả lời đúng “bao nhiêu phần trăm trong ≤ t”.
- [ ] SLE có tỷ lệ, ngưỡng, đơn vị và điều kiện phù hợp.
- [ ] Không hứa mọi item đạt ngưỡng của p85/p95.
- [ ] Item chưa finished được xem qua **work item age**, không âm thầm bỏ qua.
- [ ] Cỡ mẫu nhỏ và thay đổi loại việc được ghi thành giới hạn dự báo.

**Cải tiến có trách nhiệm:**

- [ ] Tín hiệu CFD, distribution và aging WIP được đọc cùng nhau.
- [ ] Nhóm có giả thuyết, cách kiểm chứng và một can thiệp nhỏ.
- [ ] Không dùng velocity, throughput hay cycle time để chấm điểm cá nhân.
- [ ] Khi thay DoD hoặc Definition of Workflow, nhóm giải thích điểm gãy dữ liệu.
- [ ] Guardrails về lỗi, quyền, chất lượng và dữ liệu không bị hy sinh cho số liệu đẹp.
- [ ] Kết quả người dùng và Product Goal được xem cùng hiệu quả dòng việc.
- [ ] Nhóm có mốc xem lại để giữ, điều chỉnh hoặc ngừng cải tiến.

**Kết luận:** **CFD và phân bố cycle time là hai góc nhìn bổ trợ**. CFD giúp thấy **công việc đang tích lũy ở đâu, WIP có nở không và dòng ra có theo kịp dòng vào không**. Histogram, ECDF, percentile và scatterplot giúp biết **một item đã hoàn tất thực sự mất bao lâu và mức độ biến động lớn đến đâu**. Aging WIP bảo đảm những item đang kẹt không bị che khỏi câu chuyện chỉ vì chúng chưa có cycle time. Khi thống nhất ranh giới, bảo vệ chất lượng dữ liệu và kiểm tra số đo cùng giá trị sản phẩm, nhóm Agile có thể **dự báo thận trọng hơn, hoàn tất việc có ích thường xuyên hơn và cải tiến trên bằng chứng thay vì cảm giác**.
