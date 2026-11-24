# Theo dõi tuổi công việc, thời gian bị chặn và mức độ làm lại

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **work item age** (tuổi công việc), **blocked time** (thời gian bị chặn) và **rework** (làm lại) phản ánh những khía cạnh khác nhau của dòng công việc Agile.
2. Định nghĩa chính xác **đơn vị công việc, điểm bắt đầu, điểm hoàn tất, đồng hồ đo và chính sách blocked/rework** trước khi thu thập dữ liệu.
3. Tính và diễn giải tuổi công việc đang mở, thời gian bị chặn, tỷ lệ thời gian chặn và các tín hiệu làm lại mà **không đếm trùng khoảng thời gian hoặc làm sai mẫu số**.
4. Nhận diện công việc già đi bất thường, điểm nghẽn, phụ thuộc lặp lại và nguyên nhân làm lại bằng **bằng chứng cụ thể**, không chỉ suy luận từ dashboard.
5. Thiết kế buổi quản lý dòng công việc, bảng trực quan và **thử nghiệm cải tiến có guardrail** để đưa hạng mục tới trạng thái Done nhanh hơn, an toàn hơn.
6. Kết hợp số liệu với Scrum, Kanban, XP, chất lượng sản phẩm và phản hồi người dùng, đồng thời tránh biến chỉ số thành **thước đo năng suất hay công cụ quy trách nhiệm cá nhân**.

## 1. Ba tín hiệu cần nhìn cùng nhau

Trong Agile, đội có thể bận rộn cả tuần mà người dùng vẫn không nhận được tính năng mới. Hạng mục đã bắt đầu nhưng **đứng chờ review**, lỗi tích hợp khiến code phải **sửa rồi kiểm tra lại**, hoặc một yêu cầu bị chặn bởi quyết định chưa có người trả lời. Những điều này làm kéo dài thời gian giao giá trị, dù số giờ lập trình của mỗi người rất cao.

Ba tín hiệu bổ sung cho nhau:

| Tín hiệu | Câu hỏi chính | Thời điểm có ích | Ngộ nhận cần tránh |
| --- | --- | --- | --- |
| **Tuổi công việc – work item age** | Việc **chưa hoàn tất** đã đi trong workflow bao lâu? | Hằng ngày, ngay khi còn có thể cứu một hạng mục khỏi chậm trễ | Age cao nghĩa là người thực hiện chậm |
| **Thời gian bị chặn – blocked time** | Trong thời gian đó, việc **không thể tiến** do trở ngại được định nghĩa đã kéo dài bao lâu? | Khi gỡ blocker, điều phối phụ thuộc và cải tiến chính sách | Mọi thời gian chờ đều tự động được đánh dấu blocked |
| **Mức độ làm lại – rework** | Bao nhiêu công sức hoặc vòng xử lý đã phải lặp lại vì lỗi, hiểu sai hoặc thay đổi ngoài dự tính? | Khi tìm nguồn lãng phí chất lượng, review và tích hợp | Mọi thay đổi sau phản hồi đều là làm lại xấu |

Ví dụ một user story “Tiếp tục học” bắt đầu chín ngày trước, trong đó bị chặn bốn ngày vì API chưa thống nhất; khi đến kiểm thử lại phải sửa điều kiện phân quyền. **Age** cho biết việc đã lâu; **blocked time** cho biết một phần thời gian không thể tiến; **rework** cho biết một phần kết quả đã làm phải sửa. Ba tín hiệu giúp hỏi đúng **nguyên nhân hệ thống**, không kết luận chỉ bằng số ticket Done.

Các chỉ số này **không thay thế** WIP, throughput, cycle time, chất lượng, mục tiêu sản phẩm và outcome người dùng. Chúng giúp giải thích **vì sao** một số hạng mục kéo dài hoặc giao không ổn định.

### Một tình huống mở đầu

Nhóm phát triển nền tảng học trực tuyến có sáu hạng mục trong Sprint. Ba hạng mục đang code, hai hạng mục chờ review và một hạng mục chờ môi trường test. Một developer định kéo thêm user story vì code của mình đã viết xong.

Nếu quan sát flow, câu hỏi nên là:

> “Việc nào đang già nhất? Nó chờ ở đâu? Có thể giúp hoàn tất review/test hay gỡ phụ thuộc trước khi bắt đầu thêm không? Lần sửa gần nhất xảy ra do phát hiện điều gì quá muộn?”

Những câu hỏi này hướng đội tới **hoàn tất công việc có giá trị**, thay vì chỉ tối đa hóa mức bận rộn cục bộ.

## 2. Thiết lập ranh giới đo trước khi tính chỉ số

Mọi công thức đều có thể cho số đúng toán học nhưng **sai ý nghĩa nghiệp vụ** nếu các đội hiểu khác nhau về điểm bắt đầu, điểm kết thúc hoặc hạng mục được đếm.

### 2.1. Đơn vị công việc là gì?

Một hạng mục có thể là:

- **User story/Product Backlog Item**: lát cắt hành vi có giá trị, có điều kiện Done.
- **Bug**: một lỗi có thể kiểm tra và xử lý độc lập.
- **Spike/việc khám phá**: hoạt động giảm bất định có đầu ra kiến thức, không tự coi là Increment dùng được.
- **Yêu cầu hỗ trợ/sự cố**: công việc có chính sách ưu tiên, phản hồi và hoàn tất riêng.

Không nên trộn tất cả loại việc vào một thống kê rồi so sánh nhóm “đóng nhiều ticket hơn”. Một story có thể lớn hơn mười lỗi nhỏ; việc chia một ticket thành ba phần cũng có thể làm throughput tăng mà giá trị không đổi.

### 2.2. Chọn start point và finish point

Ví dụ workflow:

~~~text
Backlog -> Sẵn sàng -> Đang làm -> Review -> Kiểm thử/tích hợp -> Done
                          ^                                   ^
                          |                                   |
                 START cho cycle time/age          FINISH khi đạt chính sách Done
~~~

| Khái niệm | Quy ước minh họa | Rủi ro khi không rõ |
| --- | --- | --- |
| **Start point** | Item được kéo từ “Sẵn sàng” sang “Đang làm” | Age bị làm trẻ giả khi chuyển cột hoặc đổi người |
| **Finish point** | Item đã đáp ứng điều kiện hoàn tất và tích hợp cần thiết | “Code xong” bị tính là Done dù còn chờ test |
| **Đồng hồ** | Ngày lịch với mốc giờ và múi giờ xác định | So sánh sai vì bên dùng ngày làm việc, bên dùng ngày lịch |
| **Blocked policy** | Điều kiện không thể tiến, thời điểm bắt đầu và kết thúc blocker | Số bị chặn không nhất quán giữa người ghi |
| **Rework policy** | Loại việc làm lại được đếm, đơn vị và lý do | Chỉ số phản ánh cách ghi ticket hơn là chất lượng thật |
| **Lịch sử trạng thái** | Lưu thời điểm chuyển trạng thái và lần mở lại | Không phân biệt công việc mới, chờ hoặc tái xử lý |

### 2.3. Phân biệt tuổi công việc với lead time

**Work item age** thường tính từ lúc item đã được **bắt đầu** theo workflow đến hiện tại khi item **chưa Done**. Nếu người dùng chờ hai tuần trước khi đội kéo item vào làm, khoảng chờ trước đó **không nằm trong tuổi này** nếu start point là “Đang làm”.

Để trả lời “Khách hàng yêu cầu từ ngày nào tới ngày nào được giao?”, đội có thể cần **lead time** tính từ mốc nhận yêu cầu khác với cycle time/age. Luôn công khai mốc đo, không đưa dự báo cycle time để hứa về toàn bộ thời gian chờ của khách hàng.

## 3. Work item age: nhận diện rủi ro khi việc còn đang mở

**Work item age** là thời gian đã trôi qua kể từ khi hạng mục đi qua start point đến **thời điểm đo**, với điều kiện hạng mục **chưa hoàn tất**.

\[
\text{Work item age}(t) = t - t_{\text{start}}, \quad \text{với item chưa Done}
\]

Ví dụ nếu một story bắt đầu lúc **09:00 ngày 14/11/2026**, thời điểm kiểm tra là **09:00 ngày 23/11/2026**, tuổi của story là **9 ngày lịch**. Trong khoảng này có thể có làm việc, chờ, blocked, review và làm lại.

**Tuổi item không phải số ngày công của developer.** Một item có thể bị chặn toàn bộ hai ngày cuối tuần; nếu đội dùng ngày lịch thì hai ngày đó vẫn nằm trong tuổi. Có thể theo dõi ngày làm việc cho một mục tiêu cụ thể, nhưng phải giữ định nghĩa và lịch làm việc nhất quán.

### 3.1. Work item age khác cycle time

| Thuộc tính | Work item age | Cycle time |
| --- | --- | --- |
| Đối tượng | Item **đang mở** sau start point | Item **đã hoàn tất** |
| Kết thúc phép đo | Thời điểm kiểm tra hiện tại | Thời điểm Done |
| Giá trị có tiếp tục tăng? | Có, khi item vẫn chưa Done | Không, sau khi Done |
| Mục đích mạnh | Phát hiện nguy cơ và can thiệp **trước khi quá muộn** | Hiểu phân bố thời gian giao thực tế, dự báo với điều kiện |
| Có nên reset khi item từ review quay về code? | **Không** | Không; chỉ kết thúc ở Done thật |

Một story đã bắt đầu bảy ngày, bị trả lại từ Review về Đang làm, vẫn có **age bảy ngày**, không phải “mới một ngày” kể từ khi quay lại. Nếu reset age mỗi lần đổi cột, dashboard sẽ che mất thời gian thực tế mà khách hàng phải chờ.

### 3.2. Age là tín hiệu hành động, không phải án phạt

Một item 12 ngày có thể do:

- Phụ thuộc bên ngoài chưa phản hồi.
- Yêu cầu có nhiều trường hợp chưa được làm rõ.
- PR lớn, review chậm hoặc test flaky.
- Sự cố khẩn làm đội đổi ưu tiên.
- Item quá lớn nên khó đưa qua Done.

Không thể kết luận “người phụ trách kém năng suất” chỉ từ tuổi. **Câu hỏi đúng** là đội có thể giúp item tiến lên hoặc giảm rủi ro theo cách nào.

## 4. Dùng phân bố cycle time và SLE để đọc age

Nhìn tuổi 10 ngày có lớn không cần **một mốc tham chiếu**. Một cách hữu ích là xem phân bố cycle time của **các item tương đồng đã hoàn tất**.

### Ví dụ phân bố minh họa

Giả sử 12 story tiêu chuẩn đã Done có cycle time, theo ngày lịch và cùng ranh giới đo:

~~~text
2, 3, 4, 4, 5, 6, 6, 7, 8, 9, 12, 15
~~~

- **Median:** Hai phần tử giữa là 6 và 6, trung vị **6 ngày**.
- **Min–max:** **2–15 ngày**.
- **P85 theo nearest-rank:** Vị trí \(\lceil 0,85 \times 12\rceil = 11\), phần tử thứ 11 là **12 ngày**.

Có thể phát biểu lịch sử:

> “Theo quy tắc tính P85 nearest-rank, trong mẫu 12 story đã hoàn thành, ít nhất 85% hoàn thành trong 12 ngày lịch hoặc ít hơn.”

**Không nên** tự suy ra xác suất rằng một story đang ở tuổi ngày thứ 10 sẽ có 85% khả năng xong trong hai ngày nữa. Đó là một câu hỏi có điều kiện về **thời gian còn lại của item chưa xong**, không được trả lời trực tiếp bằng phân vị tổng thể của các item đã Done.

### 4.1. Service Level Expectation

**Service Level Expectation (SLE)** là một kỳ vọng về thời gian đi qua workflow, có thể dựa trên phân bố lịch sử cùng loại và thường diễn đạt bằng **khoảng thời gian + mức kỳ vọng**.

Ví dụ tham khảo:

> “Đối với story tiêu chuẩn qua workflow này, chúng ta kỳ vọng khoảng 85% hạng mục hoàn thành trong tối đa 12 ngày lịch.”

Cần nêu nguồn, kỳ dữ liệu, số quan sát, điểm start/finish, phương pháp phân vị và điều kiện thay đổi. Đây **không phải SLA** và càng không phải cam kết chắc chắn cho từng item.

### 4.2. Một bảng ưu tiên hỗ trợ theo age

| Item đang mở | Tuổi | So với mốc SLE tham khảo 12 ngày | Việc đội nên hỏi |
| --- | ---: | --- | --- |
| A | 9 ngày | Đang tiến gần mốc | Có blocker hoặc review nào có thể xử lý ngay? |
| B | 3 ngày | Còn mới | Tiến triển có bình thường theo loại công việc không? |
| C | 12 ngày | Đã chạm mốc | Vì sao vẫn chưa Done, ai hỗ trợ được? |
| D | 5 ngày | Chưa gần mốc | Có rủi ro cao nào dù tuổi chưa lớn? |

**SLE là tín hiệu cho cuộc trao đổi**, không phải quy định “đến ngày thứ 12 phải đóng ticket bất kể chất lượng”.

## 5. Aging WIP: xem item đang già ở bước nào

**Aging WIP chart** thường đặt các item chưa Done theo **trạng thái trong workflow** và tuổi kể từ start point. Mục tiêu là nhận ra:

- Item nào **lâu nhất** mà vẫn đang mở.
- Những item có tuổi cao tập trung ở **Review, Test, Chờ đối tác** hay nơi khác.
- Item thuộc loại dịch vụ nào, có rủi ro đặc biệt không.
- Nhóm có đang mở thêm việc mới dù item cũ chưa hoàn tất không.

### Bảng aging WIP minh họa

~~~text
Snapshot: 23/11/2026 09:00 (UTC+07)

Item   Age (ngày)   Trạng thái          Tín hiệu
--------------------------------------------------------------
C           12      Chờ đối tác         Blocked, cần leo thang
A            9      Kiểm thử            Có hai blocker chồng nhau
D            5      Review              Cần hỗ trợ reviewer
B            3      Đang làm            Theo dõi bình thường
~~~

Một biểu đồ trực quan có thể tô mốc phần trăm SLE, nhưng không nên dùng **màu đỏ như kết luận người phụ trách sai**. Age chỉ báo **sự cấp thiết để kiểm tra**, và một bug bảo mật mới chỉ một ngày tuổi có thể cần ưu tiên hơn story thường đã mười ngày.

### 5.1. Work item age không dừng khi bị chặn

Nếu item chưa Done thì đồng hồ age **vẫn chạy**. Blocked time là **một thành phần thời gian cần phân tích**, không phải lý do loại bỏ tự động khỏi age hoặc giữ “age hữu hiệu” riêng rồi thay cho số gốc.

### 5.2. Không tự suy đoán tình trạng từ một chấm dữ liệu

Một item ở Review lâu có thể:

- Chưa sẵn sàng để review thật nhưng được chuyển cột sớm.
- Đang chờ một chuyên gia duy nhất.
- Có nhiều vòng trả lời comment.
- Bị thiếu test hoặc môi trường tích hợp.
- Được ưu tiên thấp sau sự cố khác.

Hãy xem **lịch sử chuyển trạng thái, blocker, PR, test và người tham gia**, thay vì chỉ suy từ vị trí của chấm trên biểu đồ.

## 6. Blocked là trạng thái gì?

Một hạng mục **blocked** khi có **trở ngại cụ thể khiến nó không thể tiến theo workflow như dự định** và đã đáp ứng chính sách đánh dấu blocked của đội.

Ví dụ:

- Chờ API hoặc quyết định nghiệp vụ mà không thể hoàn tất phần đang làm.
- Thiếu quyền truy cập cần thiết hoặc môi trường test không chạy được.
- Chờ dữ liệu/đối tác bắt buộc mà không có phương án tiếp tục an toàn.
- Phụ thuộc kỹ thuật chưa được tích hợp và không thể kiểm chứng.

### Blocked khác waiting?

**Không phải mọi thời gian chờ đều được gọi blocked**. Một PR chờ đến lượt review có thể là **hàng chờ bình thường trong workflow**; nếu chính sách đội đánh dấu blocked khi vượt một điều kiện cụ thể, lúc đó nó mới được ghi blocker.

Đội có thể theo dõi riêng:

| Tình huống | Cách ghi có thể hợp lý |
| --- | --- |
| PR nằm trong cột “Chờ review” bình thường | Thời gian ở trạng thái chờ, không tự blocked |
| PR cần người có thẩm quyền giải thích rủi ro mà không thể tiếp tục | Blocked do quyết định/kiến thức nếu thỏa chính sách |
| Chờ CI chạy một lượt bình thường | Thời gian pipeline, chưa chắc là blocker |
| CI lỗi nhiều giờ do môi trường hỏng, item không thể kiểm chứng | Blocked do môi trường |
| Đội tạm chuyển sang xử lý sự cố khẩn | Ghi rõ **interruption** hoặc blocked theo quy ước nhất quán, không che thời gian thực |

Điều quan trọng không phải dùng đúng một nhãn cho mọi nhóm, mà là **tách loại chờ và nguyên nhân**, để dữ liệu dẫn đến giải pháp phù hợp.

### Chính sách đánh dấu cần minh bạch

Nhóm cần xác định:

1. **Điều kiện bắt đầu**: khi nào item thực sự không tiến được?
2. **Mốc thời gian**: ghi từ lúc phát hiện trở ngại hay lúc nó bắt đầu có tác động? Nếu dùng mốc hồi tố, phải có bằng chứng.
3. **Người ghi và hỗ trợ**: ai có thể đánh dấu, ai phối hợp gỡ blocker?
4. **Nguyên nhân**: API, product decision, test environment, review, dữ liệu, quyền, sự cố?
5. **Cách đánh dấu kết thúc**: khi nào item đã có khả năng tiếp tục?
6. **Nhiều blocker đồng thời**: ghi nguyên nhân riêng nhưng tránh cộng trùng thời gian.

Nếu mọi item đều bị đánh dấu blocked ngay khi người thực hiện đi họp, chỉ số sẽ nhiều nhiễu. Nếu chỉ chờ quá ba ngày mới được ghi blocked, dữ liệu lại mất phần thời gian quan trọng. Chính sách nên phản ánh **quyết định mà đội muốn hỗ trợ**.

## 7. Tính blocked time bằng các khoảng thời gian

**Blocked time** là tổng thời gian trôi qua trong những khoảng item được đánh dấu **không thể tiến** theo chính sách, trong ranh giới đo đã chọn.

\[
\text{Blocked time} = \text{Độ dài hợp của các khoảng blocked hợp lệ}
\]

Từ **hợp (union)** quan trọng khi một item có **nhiều lý do chặn chồng lấp**.

### 7.1. Ví dụ một item có nhiều blocker

Item A bắt đầu lúc **09:00 ngày 14/11/2026**; thời điểm đo **09:00 ngày 23/11/2026**, age = **9 ngày**.

| Blocker | Bắt đầu | Kết thúc | Độ dài nếu xét riêng |
| --- | --- | --- | ---: |
| API chưa chốt quy tắc | 16/11 09:00 | 19/11 09:00 | 3 ngày |
| Thiếu môi trường tích hợp | 17/11 09:00 | 20/11 09:00 | 3 ngày |

Hai khoảng **chồng nhau từ 17/11 đến 19/11**. Không được cộng 3 + 3 = 6 ngày để nói item bị chặn sáu ngày thời gian thực.

~~~text
Ngày:      14  15  16  17  18  19  20  21  22  23
Age:       |------------------------------------>| 9 ngày
API:               |-----------|                    3 ngày
Môi trường:            |-----------|                 3 ngày
Hợp blocked:       16  |---------------| 20          4 ngày
~~~

**Blocked time theo thời gian thực** là từ **16/11 09:00 đến 20/11 09:00 = 4 ngày**, tức **96 giờ**. Có thể ghi **6 blocker-days theo lý do** để thấy tổng tải các nguyên nhân (3 + 3), nhưng phải đặt tên khác: đó **không phải 6 ngày item không tiến**.

### 7.2. Trường hợp nhiều blocker không chồng lấp

Item C từ **11/11 09:00 đến 23/11 09:00**, age = **12 ngày**:

- Chờ xác nhận API từ 12/11 đến 15/11: **3 ngày**.
- Chờ môi trường từ 18/11 đến 22/11: **4 ngày**.

Vì các khoảng không chồng lấp, blocked time = **3 + 4 = 7 ngày**.

### 7.3. Blocker chưa được gỡ

Nếu một blocker bắt đầu ngày 21/11 và đến lúc chụp snapshot 23/11 vẫn chưa gỡ, khoảng đo chỉ được tính **đến mốc snapshot**; không giả định ngày kết thúc trong tương lai.

Một record blocker có thể được lưu với **end_time rỗng**, rồi khi tính:

\[
\text{end thực dùng} = \min(\text{end nếu đã có, thời điểm snapshot})
\]

Chỉ tính phần giao với **[start point, finish point hoặc snapshot]**, tránh đếm thời gian trước khi item bắt đầu hoặc sau khi Done.

### 7.4. Nguyên tắc nhất quán

- Dùng cùng **múi giờ và định dạng timestamp** khi lưu; có thể lưu UTC và hiển thị theo múi giờ đội.
- Tính bằng **thời gian thực** hoặc **thời gian làm việc** theo chính sách, không trộn.
- Không cộng hai khoảng **trùng thời điểm** như hai ngày khác nhau.
- Không reset blocker history khi item đổi người phụ trách hay quay lại code.
- Phân biệt **duration của nguyên nhân** với **duration item thực sự bị chặn**.

## 8. Các chỉ số blocked nên theo dõi

Chỉ một con số “tổng blocked time” chưa đủ cho cải tiến. Có thể kết hợp:

| Chỉ số | Cách hiểu hoặc công thức | Quyết định có ích |
| --- | --- | --- |
| **Blocked duration/item** | Độ dài hợp của các khoảng blocked của từng item | Item nào đang bị chặn nghiêm trọng? |
| **Blocked age hiện tại** | Với blocker đang mở, thời gian từ lúc nó bắt đầu đến snapshot | Phụ thuộc nào cần leo thang ngay? |
| **Blocker count/item** | Số sự kiện blocker theo chính sách | Một item bị ngắt quãng nhiều lần không? |
| **% item từng bị chặn** | Số item có ít nhất một blocker / tổng item trong cùng tập quan sát | Chặn có phổ biến không? |
| **Blocked-time ratio/item** | Blocked duration / age hoặc cycle time cùng item | Bao nhiêu phần thời gian thực của item nằm trong blocked? |
| **Thời gian theo nguyên nhân** | Phân bố duration API, review, test, quyết định... | Nguồn chặn nào đáng điều tra? |
| **Hàng chờ blocker đang mở** | Số blocker/item chưa được giải quyết tại snapshot | Có cần điều phối hoặc bổ sung quyền quyết định? |

### 8.1. Tỷ lệ thời gian bị chặn

Với item A age **9 ngày**, blocked time **4 ngày**:

\[
\text{Blocked ratio}_A = \frac{4}{9}\times100\% \approx 44,4\%
\]

Với item C age **12 ngày**, blocked time **7 ngày**:

\[
\text{Blocked ratio}_C = \frac{7}{12}\times100\% \approx 58,3\%
\]

Phần thời gian **không bị đánh dấu blocked** không đồng nghĩa toàn bộ là thời gian lập trình chủ động; nó còn bao gồm chờ bình thường, review, test, phối hợp và những blocker chưa được ghi.

### 8.2. Mẫu số khác nhau cho mục đích khác nhau

| Câu hỏi | Mẫu số hợp lý |
| --- | --- |
| Trong số item đang mở, bao nhiêu item **hiện đang blocked**? | Tổng item đang mở tại cùng snapshot |
| Trong số item hoàn thành tháng này, bao nhiêu item **từng blocked**? | Tổng item hoàn thành tháng đó với cùng quy tắc đo |
| Với item đã Done, phần thời gian blocked là bao nhiêu? | Cycle time của **chính item đó** |
| Với item đang mở, blocked chiếm bao nhiêu phần tuổi? | Age của **chính item đó** |

Không lấy blocked time của **nhóm item đang mở** chia cycle time của **nhóm đã Done** rồi gọi một “tỷ lệ blocked chuẩn”. Tập quan sát và đơn vị không tương thích.

### 8.3. Tổng hợp có thể gây lệch

Giả sử item A blocked 4/9 ngày, item C blocked 7/12 ngày. Có thể:

- Lấy **trung bình tỷ lệ từng item**: \((44,4\% + 58,3\%)/2 \approx 51,4\%\).
- Lấy **tỷ lệ tổng thời gian**: \((4+7)/(9+12) \approx 52,4\%\).

Hai cách **khác ý nghĩa** và đều chịu ảnh hưởng của cách chọn mẫu. Tỷ lệ theo tổng thời gian cho item dài trọng số lớn hơn. Khi công bố phải nêu cách tính, không chọn cách nào cho kết quả đẹp hơn.

## 9. Các lý do blocked và hướng hành động

Một taxonomy nguyên nhân có ích khi đủ **ngắn, rõ và dẫn đến hành động**:

| Nhóm nguyên nhân | Ví dụ | Câu hỏi nguyên nhân | Thử nghiệm có thể cân nhắc |
| --- | --- | --- | --- |
| **Product/decision** | Quy tắc “bài gần nhất” chưa chốt | Có ai có quyền quyết định, có ví dụ đủ rõ không? | Refinement, Example Mapping, quyết định theo timebox |
| **External dependency** | API đối tác chưa cung cấp hợp đồng | Có thể làm contract test/stub, giảm phụ thuộc hoặc thương lượng thứ tự? | Làm rõ hợp đồng sớm, tích hợp tăng dần |
| **Review/approval** | Chờ người duyệt PR hoặc phê duyệt quyền | Có một điểm sở hữu duy nhất hoặc PR quá lớn không? | PR nhỏ, pair/swarm, reviewer dự phòng phù hợp |
| **Test environment/CI** | Pipeline flaky, môi trường lỗi | Có vấn đề độ ổn định và quyền sửa môi trường không? | Cải tiến CI, dữ liệu test ổn định, contract test |
| **Technical integration** | Schema/API không tương thích | Lỗi được phát hiện quá muộn hay thiếu test tích hợp? | CI, contract test, integration test sớm |
| **Knowledge gap** | Chỉ một người hiểu module tiến độ | Có thể luân phiên và pairing để giảm phụ thuộc? | Pairing, runbook, review chéo |
| **Security/compliance** | Chờ xác nhận phân quyền bắt buộc | Điều kiện nào cần được giải thích và bằng chứng nào thiếu? | Threat review sớm, mô tả ranh giới và test |
| **Operational interruption** | Sự cố production chiếm năng lực của đội | Cách dành năng lực và đặt expedite có rõ không? | Chính sách khẩn, minh bạch tác động và WIP |

**Nguyên nhân phải có bằng chứng**, không chỉ là lựa chọn trong dropdown. Nếu một item luôn chọn “Other”, có thể taxonomy thiếu hoặc đội không muốn nói thật vì cảm thấy bị đánh giá.

## 10. Rework: “làm lại” có nghĩa gì trong Agile?

**Rework** là việc phải làm lại, sửa hoặc lặp một phần công việc **đã được thực hiện trước đó** vì kết quả không đạt điều cần đạt, có lỗi, hiểu sai hoặc một thay đổi ngoài dự kiến làm phần trước không còn dùng được.

Ví dụ:

- Test phát hiện code chọn bài gần nhất nhưng **không kiểm tra quyền học**, phải sửa logic và kiểm thử lại.
- Pull request bị trả về nhiều lần do **hợp đồng API chưa thống nhất**.
- Migration dữ liệu phải làm lại vì quy tắc chuyển đổi cũ bị hiểu sai.
- Một lỗi đã được đánh dấu Done nhưng xuất hiện lại vì thay đổi chưa sửa nguyên nhân gốc.

### Đừng gọi mọi vòng lặp là lãng phí

Agile chủ động học qua feedback. Các thay đổi sau khi người dùng thử một Increment **có thể là phát triển yêu cầu mới có giá trị**, không phải lỗi chất lượng của phần trước.

| Tình huống | Phân loại thường phù hợp | Vì sao |
| --- | --- | --- |
| Sửa bug khiến tính năng không đáp ứng acceptance criteria đã xác nhận | **Rework do lỗi/thiếu kiểm chứng** | Kết quả ban đầu chưa đạt yêu cầu đã biết |
| Sửa logic vì Product Owner mới làm rõ một quy tắc cần biết từ trước | **Rework do hiểu sai/thiếu rõ** nếu đã phải bỏ kết quả cũ | Cần xem nguồn và thời điểm thông tin |
| Khách hàng dùng bản đầu rồi đề nghị chức năng video mới | **Nhu cầu mới** / phát triển tiếp, chưa chắc rework | Tính năng mới không tự biến Increment trước thành sai |
| Refactor khi vẫn giữ hành vi và giảm trùng lặp tri thức | **Cải tiến kỹ thuật có chủ đích**, không tự động rework xấu | Tạo khả năng thay đổi, cần xem lý do |
| Sửa test flaky do chính test viết thiếu ổn định | Có thể là **rework của test/CI** | Tốn công và làm giảm độ tin cậy phản hồi |
| Sửa do tiêu chuẩn pháp lý đã có nhưng bị bỏ qua | **Rework do thiếu tuân thủ** | Điều kiện bắt buộc đã tồn tại |
| Phát hiện rủi ro mới trong khám phá chủ động trước cam kết | **Học hỏi/khám phá** có thể là đầu ra mong muốn | Không nên trừng phạt vì đã phát hiện bất định sớm |

Chính sách phân loại phải giúp đội **học nguyên nhân**, không khiến mọi thay đổi trong Scrum/Kanban/XP bị dán nhãn “kém hiệu quả”.

## 11. Phân loại nguyên nhân rework

Nếu muốn đo rework có ý nghĩa, đội có thể nhóm theo **nguyên nhân có thể cải tiến**:

1. **Yêu cầu/tiêu chí chưa rõ:** Các bên có cách hiểu khác, thiếu ví dụ ngoại lệ.
2. **Lỗi logic/kiểm thử:** Implement sai hành vi đã biết hoặc thiếu test rủi ro quan trọng.
3. **Lỗi tích hợp/hợp đồng:** API, schema, phiên bản, dữ liệu và môi trường khác giả định.
4. **Vấn đề review/thiết kế:** Quyết định cấu trúc gây hiểu nhầm hoặc thay đổi ngoài phạm vi cần tách.
5. **Vấn đề kiểm thử tự động:** Test flaky, dữ liệu môi trường không ổn định.
6. **Thay đổi bối cảnh hợp lệ:** Thay đổi ưu tiên/luật/đối tác sau khi đã làm; cần phân biệt với lỗi hiểu sai.
7. **Khác/chưa phân loại:** Chưa đủ bằng chứng, cần điều tra thay vì buộc phải chọn một nguyên nhân.

### Đặt câu hỏi sau một vòng làm lại

- Điều gì cho biết kết quả cũ **không thể dùng**?
- Tiêu chí đó đã được biết vào thời điểm bắt đầu chưa?
- Có test, review hay ví dụ nào đáng lẽ phát hiện sớm không?
- Sự cố xảy ra vì lỗi kỹ thuật, đổi yêu cầu hay thay đổi bên ngoài?
- Chi phí làm lại là **sửa code**, **làm lại test**, **chờ review**, hay cả ba?
- Thay đổi quy trình nhỏ nào có thể giảm tần suất lặp lại?

Một nguyên nhân có thể thuộc nhiều nhóm. Nếu muốn tổng hợp tỷ trọng, đội cần chính sách chọn **nguyên nhân chính** hoặc chấp nhận nhãn đa nguyên nhân nhưng **không cộng tỷ lệ như các nhóm loại trừ nhau**.

## 12. Đo mức độ làm lại bằng những tín hiệu nào?

Không có một thước đo rework phổ quát của Agile. Tùy quyết định cần hỗ trợ, đội có thể dùng:

| Chỉ số | Định nghĩa ví dụ | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Rework occurrence/item** | Item có ít nhất một vòng quay lại do nguyên nhân được định nghĩa | Thấy loại việc dễ phải sửa | Có thể bỏ qua quy mô và số giờ sửa |
| **Rework count/item** | Số vòng làm lại thực sự theo chính sách | Tìm item bị lặp nhiều lần | Một vòng nhỏ và một vòng lớn bị đếm như nhau |
| **Rework effort** | Tổng giờ công thực tế dành cho các bước làm lại, khi có dữ liệu đủ đáng tin | Thấy chi phí năng lực | Ghi giờ có sai số và có thể khuyến khích báo cáo đối phó |
| **Rework effort ratio** | Giờ công làm lại / tổng giờ công cùng phạm vi, cùng kỳ | Theo dõi tỷ trọng năng lực | Phải định nghĩa mẫu số, không suy ra nguyên nhân tự động |
| **Reopened rate** | Item đã được tính Done rồi bị mở lại / item Done cùng tập quan sát | Tín hiệu lỗi thoát qua cổng Done | Không phát hiện vòng sửa trước khi Done; dễ bị thay đổi chính sách reopen |
| **Review return rate** | PR/item phải sửa sau review / PR/item review trong cùng kỳ | Xem chất lượng chuẩn bị và phản hồi | Reviewer kỹ hơn có thể làm số tăng mà chất lượng phát hiện tốt hơn |
| **Defect escape rate** | Lỗi tìm sau một mốc kiểm soát / tập hợp lỗi theo định nghĩa | Xem khuyết tật phát hiện muộn | Phụ thuộc độ phủ quan sát và cách đếm lỗi |
| **Time in rework state** | Thời gian item ở vòng làm lại | Xem độ trễ dòng việc do vòng lặp | Gồm chờ, chưa phải giờ công chủ động |

### 12.1. Ví dụ rework effort ratio

Giả sử một đội **có dữ liệu giờ công đủ nhất quán** trong một giai đoạn:

- Tổng 60 giờ công liên quan các item đã chọn.
- Trong đó 12 giờ là sửa lại kết quả chưa đáp ứng điều đã xác nhận.

\[
\text{Rework effort ratio}=\frac{12}{60}\times100\%=20\%
\]

**20%** không tự chứng minh đội kém năng lực. Cần xem phần làm lại vì lỗi khó tránh, yêu cầu mơ hồ, bug phát hiện sớm hoặc thay đổi ngoài dự tính; cũng cần biết giờ công có bị báo thiếu hay không.

### 12.2. Ví dụ reopened rate

Trong một kỳ có **20 item Done** theo chính sách và **4 item trong cùng tập bị mở lại** do không đạt tiêu chuẩn Done:

\[
\text{Reopened rate}=\frac{4}{20}\times100\%=20\%
\]

Đây chỉ là chỉ số theo cách đo đã chọn. Nếu item được mở lại sau nhiều kỳ, phải nêu **cohort Done và cửa sổ theo dõi**. Không được đếm một item Done hai lần rồi chia không nhất quán.

### 12.3. Không dùng dòng code bị sửa làm chỉ số rework duy nhất

Số dòng thay đổi có thể phản ánh **format, refactor có ích, code generation hoặc thay đổi tên**, không tương đương số giờ mất hay mức tác động. Trong một bug nhỏ, một dòng code có thể gây hậu quả dữ liệu lớn; trong refactor chủ động, hàng trăm dòng sửa có thể giảm chi phí duy trì.

## 13. Theo dõi các vòng lặp của một item

Khi cần đo rework, workflow nên ghi được **sự kiện quay lại** và **lý do**, nhưng không nhất thiết cần tạo thêm một cột cố định “Rework” cho mọi trường hợp.

~~~mermaid
flowchart LR
    A["Đang làm"] --> B["Review"]
    B --> C["Kiểm thử / tích hợp"]
    C --> D["Done theo chính sách"]
    B -- "Cần sửa" --> E["Làm lại: lý do + bằng chứng"]
    C -- "Test thất bại" --> E
    E --> A
    D -- "Phát hiện chưa đạt Done" --> F["Reopened có lưu lịch sử"]
    F --> A
~~~

### Một quy tắc phân biệt quan trọng

- **Review trả về trước khi Done:** Đây là **vòng sửa trong cùng item**, không phải “reopened từ Done”.
- **Item đã Done, rồi phát hiện chưa đáp ứng điều kiện Done:** Có thể ghi **reopened**, theo chính sách.
- **Increment đã đúng với yêu cầu cũ, sau đó có yêu cầu mới:** Thường tạo **item mới**, không mở lại ticket cũ chỉ để giữ dòng lịch sử.

Nếu board chỉ lưu cột cuối cùng mà không có lịch sử chuyển trạng thái, số vòng làm lại **không thể tái dựng chính xác**. Không nên tự ước lượng từ số comment PR rồi báo như số đo chắc chắn.

## 14. Thiết kế dữ liệu sự kiện để đo chính xác

Một hệ thống quản lý công việc có thể lưu lịch sử chuyển trạng thái và các sự kiện blocker/rework. Dữ liệu tối thiểu nên phục vụ **câu hỏi cải tiến**, không thu thập quá nhiều thông tin cá nhân.

### 14.1. Sự kiện trạng thái

| Trường | Ý nghĩa |
| --- | --- |
| item_id | ID item ổn định, không thay đổi khi chuyển cột |
| event_id | ID sự kiện để loại bản ghi trùng |
| event_time | Thời điểm sự kiện trong UTC hoặc chuẩn nhất quán |
| event_type | STARTED, STATE_CHANGED, BLOCKED, UNBLOCKED, REWORK_STARTED, REWORK_ENDED, DONE, REOPENED... |
| from_state / to_state | Trạng thái trước/sau nếu áp dụng |
| reason_code | Nhóm nguyên nhân theo chính sách; có thể để rỗng nếu không áp dụng |
| workflow_version | Phiên bản chính sách cột/start/finish nếu workflow đã thay đổi |
| note_ref | Liên kết tới bằng chứng/thảo luận cần thiết, hạn chế sao chép dữ liệu nhạy cảm |

Các tên sự kiện chỉ là **đề xuất minh họa**. Không có event schema bắt buộc chung cho Scrum hay Kanban.

### 14.2. Ví dụ một bản ghi blocker

~~~json
{
  "item_id": "AGILE-142",
  "blocker_id": "BLK-02",
  "reason_code": "EXTERNAL_API",
  "started_at": "2026-11-16T02:00:00Z",
  "ended_at": "2026-11-19T02:00:00Z",
  "status": "RESOLVED"
}
~~~

Ở Việt Nam (UTC+07), **02:00 UTC tương ứng 09:00 giờ địa phương** cùng ngày. Ví dụ trên chỉ minh họa kỹ thuật timestamp, không chứa dữ liệu thật.

### 14.3. Cách đo chồng lấp

Một thuật toán khái niệm tính blocked time:

~~~text
Input:
  work_start, work_end_or_snapshot
  danh sách blocker interval [start, end)

1. Với mỗi khoảng:
   - Nếu end rỗng: dùng snapshot hiện tại.
   - Giới hạn start/end trong [work_start, work_end_or_snapshot).
   - Bỏ khoảng không có độ dài dương.
2. Sắp xếp các khoảng theo start tăng dần.
3. Hợp nhất các khoảng giao nhau hoặc tiếp giáp.
4. Cộng độ dài của các khoảng sau hợp nhất.

Output:
  blocked_duration thực tế (không cộng trùng thời gian)
~~~

Các khoảng **nửa mở [start, end)** giúp tránh vấn đề đếm một mốc chung hai lần. Nếu muốn phân tích **tổng duration theo lý do**, phải tính báo cáo riêng; tổng theo lý do có thể lớn hơn blocked duration item khi hai lý do trùng thời gian.

### 14.4. Kiểm tra dữ liệu đầu vào

- Không có blocker kết thúc trước thời điểm bắt đầu.
- Không có DONE trước START theo cùng workflow.
- Một item có ID ổn định và các event không bị nhân đôi do retry.
- Khi quay lại từ Done, có lưu lý do và cửa sổ theo dõi.
- Khi đổi tên trạng thái, mapping lịch sử còn giải thích được.
- Khi item bị hủy/loại khỏi phạm vi, chính sách thống kê được ghi rõ.

Đừng cố tạo dashboard chính xác đến từng phút khi đội chỉ cập nhật thủ công cuối ngày; cần **phù hợp độ chính xác của dữ liệu**.

## 15. Bộ dữ liệu xuyên suốt: đọc age, blocked và rework

Giả sử snapshot lúc **09:00 ngày 23/11/2026, UTC+07**. Đội dùng **ngày lịch**, item bắt đầu từ “Đang làm” và hoàn thành khi đạt chính sách Done.

### 15.1. Item đang mở

| Item | Bắt đầu (09:00) | Trạng thái hiện tại | Age | Blocked time theo hợp khoảng | Vòng rework trước Done |
| --- | --- | --- | ---: | ---: | ---: |
| **A – Tiếp tục học** | 14/11 | Kiểm thử | **9 ngày** | **4 ngày** | 1 |
| **B – Sửa nhãn giao diện** | 20/11 | Đang làm | **3 ngày** | **0 ngày** | 0 |
| **C – Tích hợp API tiến độ** | 11/11 | Chờ đối tác | **12 ngày** | **7 ngày** | 2 |
| **D – Đối soát tiến độ** | 18/11 | Review | **5 ngày** | **1 ngày** | 0 |

Tổng WIP trong phạm vi đang mở là **4 item**. Các item này **chưa có cycle time hoàn thành**, vì chưa Done.

Blocked ratio lần lượt:

- A: **4/9 ≈ 44,4%**.
- B: **0/3 = 0%**.
- C: **7/12 ≈ 58,3%**.
- D: **1/5 = 20%**.

**Lưu ý:** Ngay cả B có blocked ratio 0% vẫn có thể chờ review bình thường hoặc gặp rủi ro chưa được đánh dấu. Tỷ lệ 0% chỉ nói **không có khoảng blocked được ghi theo chính sách**, không chứng minh không có chờ.

### 15.2. Item đã hoàn thành

| Item | Bắt đầu | Done | Cycle time | Blocked time | Rework |
| --- | --- | --- | ---: | ---: | --- |
| **E – Sửa lỗi tiến độ** | 10/11 09:00 | 17/11 09:00 | **7 ngày** | **2 ngày** | 1 vòng trước Done |
| **F – Cải thiện trạng thái rỗng** | 12/11 09:00 | 16/11 09:00 | **4 ngày** | **0 ngày** | 0 vòng |

Tỷ lệ blocked trong cycle time: E **2/7 ≈ 28,6%**, F **0/4 = 0%**. Mẫu chỉ hai item Done **không đủ** để kết luận tốc độ giao điển hình hay dự báo tin cậy cho tương lai.

### 15.3. Phân tích chung

Nhìn bảng, có thể thấy:

1. **C** là item già nhất và blocked nhiều nhất; cần xem **ai đang có quyền giải quyết phụ thuộc API**, mức ảnh hưởng và cách giảm phạm vi.
2. **A** có hai blocker chồng lấp; cần đánh giá **khi một blocker được gỡ, blocker còn lại có ngăn item tiến hay không**.
3. **C** có hai vòng rework; cần hỏi nguyên nhân cùng nhau: hợp đồng API thiếu rõ hay test tích hợp phát hiện muộn?
4. **D** đang Review; blocker một ngày không giải thích toàn bộ age năm ngày. Có thể có chờ thông thường hoặc công việc khác.
5. Không thể kết luận rằng “WIP 4 là đúng”, “age 12 là thất bại” hoặc “C do người phụ trách làm chậm” chỉ từ bảng.

## 16. Đọc mối quan hệ giữa age, blocked và rework

Ba tín hiệu thường xuất hiện cùng nhau nhưng **không phải quan hệ nhân quả tự động**.

### Kịch bản 1 — Age cao, blocked cao, rework thấp

Ví dụ story chờ hợp đồng API sáu ngày nhưng code chưa phải sửa nhiều.

**Giả thuyết:** Phụ thuộc và quyền quyết định đang làm chậm flow.

**Cần xem:** Timeline blocker, phản hồi đối tác, khả năng sử dụng contract test/mock có giới hạn, có việc nào khác có thể hoàn tất an toàn.

### Kịch bản 2 — Age cao, blocked thấp, rework cao

Ví dụ story nhiều lần bị trả lại từ Review/Test nhưng không đánh dấu blocked.

**Giả thuyết:** Tiêu chí chấp nhận chưa rõ, thiếu test, PR lớn hoặc chất lượng tích hợp.

**Cần xem:** Lý do rework, vòng trả lại, lỗi kỹ thuật, chính sách Done và những câu hỏi nghiệp vụ chưa chốt.

### Kịch bản 3 — Age cao, blocked thấp, rework thấp

Có thể item quá lớn, được triển khai theo một batch dài, hoặc đang ở hàng chờ không bị đánh dấu blocked. Cần kiểm tra **kích thước, thời gian từng trạng thái và khả năng chia lát cắt**.

### Kịch bản 4 — Age thấp nhưng rủi ro rất cao

Một bug lộ dữ liệu mới được phát hiện hôm nay có age thấp. Tuy nhiên mức nghiêm trọng khiến nó cần được xử lý **trước nhiều story già hơn**. Quyết định phải kết hợp **giá trị, mức rủi ro và chính sách dịch vụ**.

### Kịch bản 5 — Blocked giảm nhưng rework tăng

Đội bỏ bước làm rõ và review để item “không bị chặn”, rồi phải sửa sau test hoặc production. Dashboard blocked time đẹp hơn nhưng **chất lượng và tổng chi phí thay đổi có thể xấu đi**. Phải xem cả hai chỉ số và guardrail.

## 17. Trực quan hóa ba tín hiệu

### 17.1. Aging WIP chart

Trục ngang là trạng thái công việc; trục dọc là tuổi từ start point. Mỗi chấm là một item đang mở. Có thể đặt các đường tham chiếu từ phân bố cycle time lịch sử cho **cùng loại item**.

**Ứng dụng:** Phát hiện item ở Review hoặc Test đã lâu, không chỉ các item “Đang làm” gần đây.

### 17.2. Blocker timeline

Hiển thị các dải thời gian blocker theo từng item, có màu hoặc nhãn theo nguyên nhân.

~~~text
Item A:  START |-- work --|======= blocked =======|-- test --| SNAPSHOT
                         API --------
                            ENV -----------

Item C:  START |-- block API --|-- work --|-- block ENV --| SNAPSHOT
~~~

Khi hai nguyên nhân chồng nhau, timeline giúp đội biết **gỡ một nguyên nhân chưa đủ**. Cần hiển thị timestamp thật nếu tính blocked duration; sơ đồ trên chỉ mô tả ý tưởng.

### 17.3. Rework loop / chuyển trạng thái

Theo dõi các lần:

> Đang làm → Review → Đang làm → Review → Test → Đang làm → Test → Done.

Hãy ghi **vì sao vòng quay lại xảy ra**, không chỉ số mũi tên. Một vòng sửa nhỏ do review đúng lúc có thể ngăn lỗi production lớn, vì vậy **số vòng review tăng không tự đồng nghĩa chất lượng xấu**.

### 17.4. Biểu đồ xu hướng theo tuần

Có thể xem:

- Phân bố cycle time của item **đã Done** theo ngày hoàn tất.
- WIP và age của item **đang mở** theo snapshot.
- Tổng và phân bố blocked duration theo **nhóm nguyên nhân**.
- Tỷ lệ item có rework hoặc reopened theo **cohort và chính sách nhất quán**.

Không nên đặt các đường có **mẫu số và đơn vị khác nhau** trên cùng trục rồi so trực tiếp như một con số đo cùng hiện tượng.

## 18. Đưa số liệu vào Daily Scrum hoặc buổi quản lý flow

Một cuộc họp theo luồng nên đi từ **việc cần hành động**, không phải lượt báo cáo cá nhân:

1. Item nào đang ở **tuổi cao hoặc vượt kỳ vọng**?
2. Item nào **hiện blocked**, vì sao và cần ai phối hợp?
3. Có bao nhiêu việc đang Review/Test cần giúp để **hoàn tất**?
4. Những vòng rework gần đây có chỉ ra **điều kiện chất lượng hoặc yêu cầu bị hiểu sai**?
5. Có nguy cơ đối với **Sprint Goal, Product Goal hoặc dịch vụ khách hàng** không?
6. Hành động rõ nhất trước buổi kiểm tra tiếp theo là gì?

### Ví dụ cuộc trao đổi ngắn

> **Developer:** “Item C đã 12 ngày, trong đó bảy ngày blocked. Đối tác chưa trả lời quy tắc ghi tiến độ khi request đến trễ.”
>
> **Product Owner/đầu mối sản phẩm:** “Tôi sẽ phối hợp đầu mối đối tác chốt ví dụ nghiệp vụ trong hôm nay. Nếu không có câu trả lời, mình xem lại lát cắt nào có thể giao độc lập.”
>
> **Tester:** “Hai vòng rework trước đều vì xử lý request trùng. Tôi đề xuất viết contract test cho trường hợp đó sau khi quy tắc được chốt.”
>
> **Developer khác:** “Tôi sẽ giúp kiểm tra hợp đồng và review PR hiện có thay vì kéo một story mới.”

Cuộc họp có **quyết định, người phối hợp và điểm xem lại**. Điều này có giá trị hơn việc từng người đọc “hôm qua làm gì, hôm nay làm gì” mà không thay đổi flow.

### Không áp đặt Daily Scrum lên mọi đội

Trong Scrum, **Daily Scrum là sự kiện 15 phút cho Developers** để kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog. Dữ liệu age/blocked/rework có thể giúp hoạt động này, nhưng không biến nó thành cuộc họp chỉ báo cáo KPI.

Đội flow-first theo Kanban có thể tổ chức buổi điều phối hằng ngày theo nhu cầu, không cần gọi đó là Daily Scrum nếu không thực hành Scrum đầy đủ.

## 19. Chẩn đoán nguyên nhân hệ thống thay vì quy lỗi

### 19.1. Dùng câu hỏi “vì sao” có kiểm chứng

Ví dụ:

> “Vì sao item bị trả lại ba lần?”

Không nên dừng ở câu “developer viết sai”. Hỏi tiếp:

- Tiêu chí chấp nhận có ví dụ về quyền truy cập không?
- Có test tích hợp thực hiện trên session đổi tài khoản không?
- Reviewer có đủ ngữ cảnh và năng lực không?
- PR có quá lớn, lỗi được phát hiện chỉ ở cuối?
- API đối tác có hợp đồng phù hợp không?
- Có cần đổi Definition of Done/chính sách kiểm chứng hay không?

**5 Whys** có thể giúp tìm hiểu chuỗi nguyên nhân, nhưng không bảo đảm luôn có một “nguyên nhân gốc” duy nhất. Nhiều vấn đề Agile do **nhiều yếu tố tương tác**.

### 19.2. Bảng từ tín hiệu tới thử nghiệm

| Quan sát | Giả thuyết | Thử nghiệm nhỏ | Bằng chứng cần xem |
| --- | --- | --- | --- |
| Item già và blocked do review | Reviewer quá tải hoặc PR lớn | Pair/swarm review, chia PR nhỏ hợp lý | Age ở Review, blocked duration, lỗi bỏ sót |
| Blocked vì API đối tác lặp lại | Hợp đồng được làm rõ quá muộn | Ví dụ trước khi kéo việc, contract test | Số blocker API, rework tích hợp, cycle time |
| Rework do phân quyền cao | Test trường hợp âm tính được viết muộn | Example Mapping + test auth sớm | Lỗi review/test, lỗi thoát ra production |
| Reopened tăng sau Done | DoD hoặc kiểm tra tích hợp chưa đủ | Kiểm tra DoD, tích hợp thường xuyên, review độc lập | Reopened theo cohort và chất lượng |
| Age cao nhưng không có blocked | Item quá lớn hoặc hàng chờ không hiển thị | Chia lát cắt, minh bạch trạng thái chờ | Phân bố age, throughput, thời gian trạng thái |
| Blocked giảm nhưng lỗi tăng | Đội bỏ bước an toàn để nhanh hơn | Khôi phục guardrail, đo nguyên nhân | Lỗi nghiêm trọng, rework, outcome |

**Cải tiến là giả thuyết phải kiểm chứng**, không phải tự động chọn giải pháp “thuê thêm người” hoặc “họp nhiều hơn”.

## 20. Thử nghiệm 1: ưu tiên hoàn tất và giảm WIP

### 20.1. Bối cảnh

Đội có nhiều story đang làm song song, review và test bị nghẽn. Tuổi hạng mục cao, nhưng developers tiếp tục kéo việc mới khi vừa viết xong code.

### 20.2. Giả thuyết

> “Nếu giảm việc bắt đầu mới và hỗ trợ hoàn tất item già ở Review/Test trước, chúng ta có thể giảm cycle time và age của hạng mục đang mở mà không tăng rework hay lỗi production.”

### 20.3. Chính sách thử

- Minh bạch điểm start/finish và WIP.
- Đặt giới hạn WIP thử nghiệm ở “Đang làm”/“Review” dựa trên năng lực thật, không sao chép mức của đội khác.
- Khi cột đạt giới hạn, ưu tiên review, test, gỡ blocker hoặc chia việc cho dễ hoàn tất.
- Với item già, xác định rủi ro và hành động cụ thể trước khi kéo thêm item.
- Giữ cơ chế xử lý sự cố khẩn và chất lượng bắt buộc, không bỏ DoD.

### 20.4. Đo kết quả

- **Work item age:** Các item tồn lâu có được xử lý?
- **Cycle time:** Phân bố của item mới Done có thay đổi sau đủ kỳ?
- **Blocked:** Có giảm số lần chờ và duration ở Review/Test?
- **Rework:** Có phát sinh nhiều vòng sửa vì đẩy nhanh review không?
- **Guardrail:** Lỗi sản xuất, overtime, chất lượng test và khả năng phục vụ việc khẩn.

**Một tuần throughput giảm chưa chắc là thất bại** nếu đội đang giải quyết item già bị tồn. Ngược lại, throughput tăng đột biến do đóng nhiều bug nhỏ không chứng minh chính sách WIP là nguyên nhân.

## 21. Thử nghiệm 2: giảm blocker và rework do hợp đồng API

### 21.1. Bối cảnh

Một phần lớn các item tích hợp tiến độ chờ bên đối tác xác nhận contract. Khi bắt đầu code lại phát hiện quy tắc “request nào thắng” chưa rõ, phải sửa nhiều lần.

### 21.2. Cách thử

1. Trong refinement, Product Owner/người có quyền quyết định cùng developer và tester làm rõ vài ví dụ nghiệp vụ.
2. Định nghĩa **các tình huống về idempotency, request đến muộn, quyền truy cập và lỗi API**.
3. Viết **contract test** và một ví dụ tích hợp trước khi triển khai một phần lớn.
4. Kéo user story vào “Đang làm” khi **đủ điều kiện bắt đầu** theo chính sách; nếu cần khám phá, tạo spike giới hạn rõ đầu ra.
5. Pair ở phần bất định, tích hợp qua CI sớm và giữ DoD.

### 21.3. Dữ liệu cần xem

| Tín hiệu | Điều muốn biết |
| --- | --- |
| Blocker loại API | Số lần và thời gian chờ theo loại công việc có giảm? |
| Rework do contract | Có bớt vòng sửa vì hiểu sai/hợp đồng đổi sau khi code? |
| Age item tích hợp | Item có tiến đến Done ổn định hơn không? |
| Integration test / CI | Lỗi được phát hiện sớm hơn và có giảm flaky? |
| Chất lượng người dùng | Có sai tiến độ hoặc lộ quyền không? |
| Phản hồi đối tác | Hợp đồng và quyền quyết định đã rõ hơn chưa? |

### 21.4. Một kết luận có trách nhiệm

Nếu blocked duration giảm nhưng rework vẫn cao, có thể hợp đồng đã được phản hồi nhanh hơn nhưng **yêu cầu nghiệp vụ và test chưa đủ rõ**. Đội cần điều tra điều mới học được, không đơn giản kết luận thử nghiệm “thành công 100%”.

## 22. Tình huống xuyên suốt: cải tiến luồng “Tiếp tục học”

### 22.1. Bối cảnh

Một Scrum Team phát triển nền tảng học tập, có **Product Goal** là giúp học viên tiếp tục học đáng tin cậy trên thiết bị thường dùng. Sprint Goal đang hướng tới:

> “Học viên đã đăng nhập mở được đúng bài gần nhất còn quyền, với trạng thái lỗi và lưu tiến độ rõ.”

Đội bắt đầu thấy nhiều story ở trạng thái Review/Test nhưng rất ít phần mềm được tích hợp đủ điều kiện Done.

### 22.2. Dữ liệu bốn tuần đầu (giả định)

| Tuần | Throughput Done | WIP trung bình | Item từng blocked | Tín hiệu rework |
| --- | ---: | ---: | ---: | --- |
| 1 | 4 | 10 | 3 | Hai vòng sửa API |
| 2 | 3 | 12 | 4 | Một PR bị trả vì thiếu phân quyền |
| 3 | 5 | 11 | 3 | Test tích hợp không ổn định |
| 4 | 4 | 11 | 4 | Hai item sửa lại sau review |
| **Tổng/trung bình** | **16 Done / 4 mỗi tuần** | **11** | Các kỳ không tự được cộng thành số item duy nhất | Cần phân loại có chính sách |

Với các con số này, chưa có cơ sở kết luận Scrum đang sai hoặc team thiếu một developer. Cần xem tuổi item đang mở, blocker cụ thể, loại rework và khác biệt giữa item.

### 22.3. Phân tích sâu một snapshot

Ngày 23/11, item C tích hợp API đã **12 ngày**, blocked **7 ngày**, có **hai vòng làm lại** trước Done. Nhóm tìm thấy:

- Quy tắc “cập nhật muộn từ thiết bị offline” chưa có ví dụ được xác nhận.
- Contract test giữa ứng dụng và API đối tác thiếu trường hợp xung đột.
- Người review duy nhất cho module này phải xử lý sự cố production.

Đây là **ba giả thuyết có liên hệ**, chưa chứng minh một nguyên nhân duy nhất. Nhóm trao đổi với người liên quan và kiểm tra các sự kiện thực tế.

### 22.4. Quyết định thử nghiệm

Trong bốn tuần tiếp theo:

1. Chia story tích hợp API thành lát cắt có thể kiểm chứng độc lập.
2. Chốt ví dụ nghiệp vụ/contract trước khi kéo phần phụ thuộc lớn vào “Đang làm”.
3. Pair developer hiểu API và người hiểu test/định danh để chia sẻ tri thức.
4. Giới hạn WIP trong Review và xử lý item già trước khi bắt đầu thêm.
5. Ghi blocker theo nguyên nhân, lưu sự kiện rework với dấu thời gian.
6. Giữ DoD, test phân quyền và chính sách xử lý dữ liệu an toàn.

### 22.5. Kết quả giả định

| Chỉ số | Bốn tuần trước | Bốn tuần thử | Cách diễn giải |
| --- | ---: | ---: | --- |
| Throughput | 16 item | 19 item | Có tín hiệu tăng, cần kiểm tra loại item |
| WIP trung bình | 11 | 8 | Lượng việc đồng thời giảm |
| Cycle time trung vị | 10 ngày | 8 ngày | Phân bố có thể dịch chuyển, cần xem đuôi dài |
| Median blocked duration của item từng blocked | 4 ngày | 2 ngày | Cần xem số item và chính sách ghi blocker |
| Item có rework / item Done | 8/16 = 50% | 6/19 ≈ 31,6% | Mẫu ngắn, định nghĩa phải nhất quán |
| Lỗi nghiêm trọng thoát ra production | 1 | 1 | Không đủ dữ liệu để kết luận rủi ro giảm |

Các số đều **giả định**. Không thể kết luận giảm WIP hoặc pairing **chắc chắn** là nguyên nhân khiến cycle time và rework giảm, vì cùng thời kỳ có thể đối tác cập nhật API hoặc tỷ lệ bug nhỏ tăng.

### 22.6. Đánh giá sau thử nghiệm

Một kết luận phù hợp:

> “Dữ liệu bốn tuần cho thấy tín hiệu luồng tích cực: WIP và trung vị cycle time giảm, blocker được giải quyết nhanh hơn trong những item đã được ghi nhận. Tuy nhiên, chúng ta cần kiểm tra tuổi của item còn mở, cách đếm rework và lỗi dữ liệu nghiêm trọng trước khi mở rộng chính sách. Chu kỳ sau sẽ tập trung riêng vào contract test và năng lực reviewer dự phòng.”

Đội giữ được **quyền được học từ bằng chứng**, không buộc phải tuyên bố đã tìm ra “quy trình tối ưu”.

## 23. Kết hợp với Scrum, Kanban và XP

### 23.1. Scrum: hướng về Sprint Goal và Increment

Trong Scrum:

- **Sprint Planning** giúp Scrum Team làm rõ Sprint Goal và chọn phần việc có thể hoàn tất theo DoD.
- **Daily Scrum** giúp Developers kiểm tra tiến triển hướng Sprint Goal; age, blocked và rework có thể làm rõ rủi ro, giúp điều chỉnh Sprint Backlog.
- **Sprint Review** kiểm tra Increment thực tế, phản hồi và hướng sản phẩm, không chỉ báo cáo số story Done.
- **Sprint Retrospective** giúp xem những vòng làm lại và blocker có thể giảm bằng cải tiến chất lượng, cộng tác hoặc kỹ thuật.

Một Product Backlog Item chưa đáp ứng **Definition of Done** không được xem là một phần của Increment hoàn thành. Không chuyển item chưa test hoặc đang lỗi sang Done chỉ để age nhỏ lại.

### 23.2. Kanban: quản lý dòng chảy, không chỉ chuyển cột

Kanban hỗ trợ:

- **Minh bạch workflow**, điểm start/finish và chính sách công việc.
- **Kiểm soát WIP**, kéo việc theo năng lực thay vì bắt đầu tất cả.
- **Quản lý flow** bằng age, cycle time, throughput, blocked và những tín hiệu phù hợp.
- **Vòng phản hồi** để xem trở ngại và quyết định thay đổi.
- **Cải tiến tiến hóa** bằng thử nghiệm có kiểm chứng.

Kanban không bắt buộc Sprint hoặc số WIP limit cố định. Scrum Team cũng có thể sử dụng thực hành Kanban mà không bỏ các yếu tố chính thức của Scrum.

### 23.3. XP: giảm rework nhờ kỹ thuật phản hồi nhanh

Một số thực hành XP hữu ích:

| Thực hành | Vấn đề có thể giảm | Bằng chứng cần xem |
| --- | --- | --- |
| **TDD / kiểm thử tự động** | Lỗi logic được phát hiện muộn, vòng làm lại lớn | Lỗi review/test, chất lượng test, rework do logic |
| **Continuous Integration** | Lỗi tích hợp kéo dài và blocker pipeline | Thời gian pipeline, lỗi tích hợp, cycle time |
| **Pair programming** | Thiếu hiểu biết ở phần code khó, chỉ một người sửa được | Khả năng review/tiếp tục việc, thời gian chờ, chất lượng |
| **Refactoring** | Thiết kế khó thay đổi, trùng quy tắc gây sửa nhiều nơi | Rework và lỗi hồi quy, chi phí thay đổi về sau |
| **Simple Design / YAGNI** | Quá nhiều tầng/khả năng chưa cần gây review/test nặng | Kích thước lát cắt, lead time, kết quả người dùng |
| **Small releases** | Lỗi chỉ được phát hiện khi tích hợp lô lớn | Feedback sớm, số lỗi tích hợp, khả năng rollback |

**Không có kỹ thuật nào tự động loại bỏ mọi rework.** Một số làm lại là phản hồi có ích; mục tiêu là giảm những vòng sửa **đáng lẽ có thể phát hiện sớm**, đồng thời tăng khả năng thay đổi an toàn.

## 24. Dự báo và SLE: đừng “sửa” age để làm đẹp dữ liệu

Nếu đội dùng phân bố cycle time để dự báo, dữ liệu chỉ hữu ích khi cách đo ổn định và item được đưa tới Done thật.

### Những thủ thuật làm sai dự báo

- Chuyển item từ “Đang làm” về “Sẵn sàng” mỗi lần blocked để **reset start date**.
- Đóng item rồi mở ticket mới cho cùng vấn đề để age trông trẻ.
- Đánh dấu “Done” sau code merge dù test/DoD chưa đạt.
- Tách một item già thành nhiều ticket nhỏ nhưng **không lưu lịch sử và quan hệ**.
- Bỏ item quá lâu khỏi báo cáo vì “không đại diện”, nhưng vẫn xem mẫu còn lại như toàn bộ dòng công việc.

Những thao tác thay đổi tập quan sát và làm **cycle time/SLE lạc quan giả**.

### Nếu thật sự đổi phạm vi

Trong phát triển phần mềm, chia một story lớn thành lát cắt nhỏ có thể **đúng và có ích**. Khi đó:

1. Ghi rõ phần nào bị loại, phần nào được giữ và vì sao.
2. Lưu liên kết đến item gốc, thời gian đã tiêu tốn và phụ thuộc.
3. Định nghĩa cách tính thống kê trước/sau khi chia, không tự chọn cách cho số tốt.
4. Không coi một ticket mới là bằng chứng khách hàng **chưa từng chờ**.
5. Giao từng lát cắt chỉ khi đạt điều kiện Done, không cắt phạm vi bằng cách bỏ bảo mật hoặc dữ liệu cần thiết.

### Về dự báo thời gian còn lại

Khi item đã ở tuổi 10 ngày và SLE lịch sử là P85 trong 12 ngày, **không thể kết luận “còn hai ngày chắc chắn xong”**. Nếu muốn dự báo có điều kiện cho những item chưa hoàn tất, cần phương pháp xử lý **item đang mở/censored**, loại công việc và độ bất định phù hợp, không áp dụng nguyên xi phân vị các item đã Done.

## 25. Guardrail, đạo đức đo lường và tác dụng phụ

Các chỉ số flow rất dễ bị tối ưu sai nếu dùng để **so sánh cá nhân, áp đặt thưởng phạt hoặc làm đẹp KPI**.

### Guardrail nên giữ

- **Definition of Done/chính sách chất lượng** không được hạ vì muốn age/cycle time ngắn.
- **Lỗi dữ liệu, phân quyền, bảo mật và an toàn** được ưu tiên theo mức rủi ro, không chỉ theo số ngày.
- **Không ép overtime** để giảm blocked/rework trong tuần rồi tăng lỗi và kiệt sức về sau.
- **Không che blocker** bằng cách đổi nhãn hoặc né ghi nguyên nhân.
- **Không dùng rework rate để chê người đặt câu hỏi/viết thêm test**: phát hiện và sửa sớm có thể bảo vệ người dùng.
- **Không ghi nhận nội dung nhạy cảm vào blocker note** hoặc hồ sơ lỗi khi không cần thiết.
- **Không công khai bảng xếp hạng “ai có item già nhất”**; tập trung vào khả năng hợp tác và gỡ chặn của hệ thống.

### Những số khác cần xem cùng

| Tín hiệu bổ trợ | Vì sao cần? |
| --- | --- |
| **Throughput và WIP** | Biết hệ thống có hoàn tất việc ổn định không |
| **Cycle time đã Done** | So với tuổi item mở và xem phân bố giao |
| **Lỗi nghiêm trọng thoát ra production** | Phát hiện “nhanh hơn” nhưng bỏ test |
| **Sự cố, thời gian khôi phục, tính toàn vẹn dữ liệu** | Xem hệ quả thực tế của chất lượng |
| **Phản hồi người dùng và outcome** | Biết Increment giao được có giải quyết nhu cầu không |
| **Khả năng duy trì nhịp làm việc** | Tránh đạt số đẹp bằng làm thêm giờ |

Nhóm chỉ cần đo những thứ **thực sự hỗ trợ quyết định**. Bảng điều khiển nhiều chỉ số nhưng không ai biết hành động gì có thể tốn chi phí hơn giá trị nó mang lại.

## 26. Những sai lầm thường gặp

| Sai lầm | Vì sao không ổn | Cách sửa |
| --- | --- | --- |
| **Gọi age là cycle time của item chưa Done** | Cycle time chỉ xác định tại mốc hoàn tất | Gọi đúng **work item age** cho item mở |
| **Reset age khi item đổi cột hoặc đổi người** | Che thời gian thực tế đang chờ | Giữ mốc start ổn định, lưu lịch sử |
| **Lấy P85 đã Done làm xác suất còn lại** | Nhầm phân bố tổng thể với phân bố có điều kiện | Dùng SLE như tín hiệu hành động, dự báo còn lại đúng phương pháp |
| **Cộng các blocker chồng lấp** | Tính blocked time vượt thời gian thực | Hợp nhất interval trước khi cộng |
| **Gọi mọi trạng thái chờ là blocked** | Mất phân biệt hàng chờ thông thường và trở ngại | Định nghĩa blocked policy và thời gian trạng thái |
| **Chỉ đo blocker đã gỡ** | Bỏ qua những blocker hiện tồn lâu nhất | Theo dõi blocker còn mở với snapshot |
| **Không ghi thời gian/múi giờ** | Duration sai, đặc biệt khi nhiều đội phối hợp | Chuẩn hóa timestamp và đơn vị |
| **Blocked = 0 tức không có chờ** | Có thể không ghi blocker hoặc ở hàng chờ bình thường | Xem cả thời gian từng trạng thái và lịch sử |
| **Mọi phản hồi làm đổi code là rework xấu** | Trừng phạt học hỏi và tiến hóa sản phẩm | Phân loại sửa lỗi/hiểu sai/nhu cầu mới/refactor |
| **Chỉ đếm reopened từ Done** | Bỏ sót vòng sửa trước khi hoàn tất | Theo dõi rework loop và lý do riêng |
| **Dùng số comment PR làm rework** | Comment có thể là hỏi, góp ý nhỏ hoặc học hỏi | Xác định hành vi làm lại có bằng chứng |
| **Cộng nhãn nguyên nhân như nhóm loại trừ nhau** | Một vòng có thể có nhiều nguyên nhân | Có nguyên nhân chính hoặc báo phân nhóm không độc quyền |
| **Tỷ lệ rework không ghi mẫu số** | Không biết tính theo giờ, item hay vòng | Ghi công thức, tập quan sát và kỳ |
| **So sánh nhóm có loại item khác nhau** | Khác biệt có thể do độ lớn/độ rủi ro | Phân loại phù hợp và giải thích bối cảnh |
| **Chỉ xem trung bình** | Item đuôi dài bị che | Xem phân bố, tuổi item già nhất, phân vị |
| **Hạ DoD để giảm cycle time** | Số đẹp nhưng chất lượng xấu | Bảo vệ DoD và guardrail |
| **Coi item già nhất là lỗi của một người** | Sai bản chất hệ thống, khuyến khích che lỗi | Hỏi phụ thuộc, phối hợp và cơ hội hỗ trợ |
| **Thử thay đổi nhiều thứ rồi khẳng định nhân quả** | Không biết biến nào tạo tác động | Ghi thay đổi đồng thời, quan sát nhiều kỳ |
| **Chỉ thu thập số liệu, không thay đổi cách làm** | Dashboard không tạo giá trị | Chọn giả thuyết, hành động, người phụ trách và điểm xem lại |

## 27. Bài tập thực hành

### Bài tập 1 — Phân biệt work item age và cycle time

Ngày 23/11/2026 lúc 09:00, story A đã bắt đầu từ 14/11/2026 lúc 09:00 nhưng chưa Done. Story B bắt đầu 10/11/2026 và Done 17/11/2026 cùng giờ.

**Yêu cầu:** Tính tuổi của A và cycle time của B. Giải thích vì sao không thể tính “cycle time cuối cùng” của A ở thời điểm này.

**Gợi ý đáp án:** A **age 9 ngày**, B **cycle time 7 ngày**. A đang mở nên thời gian cuối cùng chưa xác định.

### Bài tập 2 — Hai blocker chồng lấp

Item có hai blocker:

- B1: 16/11 09:00 tới 19/11 09:00.
- B2: 17/11 09:00 tới 20/11 09:00.

**Yêu cầu:** Tính tổng thời gian theo lý do và blocked time thực của item. Vì sao hai con số khác nhau?

**Gợi ý đáp án:** Mỗi blocker **3 ngày**, tổng duration theo lý do **6 blocker-days**, nhưng khoảng hợp thực **4 ngày** do chồng lấp.

### Bài tập 3 — Tính blocked ratio

Item A age 9 ngày, blocked 4 ngày; item C age 12 ngày, blocked 7 ngày.

**Yêu cầu:** Tính ratio của từng item, trung bình tỷ lệ và tỷ lệ theo tổng thời gian. Giải thích ý nghĩa khác nhau.

**Gợi ý:** A **44,4%**, C **58,3%**; trung bình tỷ lệ khoảng **51,4%**, tỷ lệ tổng thời gian khoảng **52,4%**. Không nói phần còn lại đều là “thời gian code”.

### Bài tập 4 — Xây chính sách blocked

Một đội có PR chờ review một ngày, môi trường CI lỗi nhiều giờ, đối tác chưa trả lời API và sự cố production chen vào Sprint.

**Yêu cầu:** Viết một chính sách blocked ngắn:

- Điều kiện bắt đầu và kết thúc.
- Thời điểm ghi và ai có quyền hỗ trợ.
- Nhóm nguyên nhân phù hợp.
- Cách phân biệt blocked, hàng chờ bình thường và gián đoạn khẩn.
- Dữ liệu tối thiểu để xác minh.

### Bài tập 5 — Phân loại rework

Cho sáu trường hợp:

1. Sửa bug không đúng acceptance criteria đã được xác nhận.
2. Bổ sung tính năng mới sau khi người dùng dùng Increment cũ.
3. Test thất bại do contract API hiểu sai.
4. Refactor chủ động để giảm trùng lặp nhưng không đổi hành vi.
5. Mở lại ticket đã Done vì tính năng vẫn đọc sai tài khoản.
6. Chạy một spike có mục tiêu để học về công nghệ mới, rồi bỏ prototype.

**Yêu cầu:** Phân loại rework do lỗi, phát triển mới, refactor và khám phá; nêu trường hợp nào có thể phụ thuộc chính sách đo.

**Gợi ý:** Không biến mọi thay đổi/khám phá thành rework xấu.

### Bài tập 6 — Tính effort ratio và reopened rate

Một đội ghi 60 giờ công trong một phạm vi thống nhất, trong đó 12 giờ là sửa lại lỗi đã có yêu cầu rõ. Trong kỳ có 20 item Done, bốn item trong chính cohort đó bị mở lại vì chưa đạt Done.

**Yêu cầu:** Tính hai tỷ lệ và chỉ ra ba giới hạn khi dùng để so sánh giữa các đội.

**Gợi ý đáp án:** Rework effort ratio **20%**, reopened rate **20%**. Cần xét cách ghi giờ, kỳ theo dõi, chính sách Done/reopen và loại item.

### Bài tập 7 — Đọc bảng aging WIP

Snapshot có:

| Item | Age | Blocked | Rework | Trạng thái |
| --- | ---: | ---: | ---: | --- |
| A | 9 ngày | 4 ngày | 1 | Test |
| B | 3 ngày | 0 ngày | 0 | Đang làm |
| C | 12 ngày | 7 ngày | 2 | Chờ API |
| D | 5 ngày | 1 ngày | 0 | Review |

**Yêu cầu:** Đề xuất thứ tự **điều tra/hỗ trợ**, không đơn giản thứ tự phải hoàn tất; nêu dữ liệu còn thiếu để quyết định, nhất là nguy cơ và Sprint Goal.

**Gợi ý:** C có tín hiệu rõ cần gỡ phụ thuộc; A cần xem hai blocker; một bug nghiêm trọng mới có thể vượt cả hai.

### Bài tập 8 — Phân tích nguyên nhân rework

Một PR bị trả về ba lần:

- Lần 1 thiếu trường hợp phân quyền.
- Lần 2 lỗi khi retry request.
- Lần 3 test tích hợp lỗi do schema API khác.

**Yêu cầu:** Vẽ chuỗi nguyên nhân có thể có, đề xuất ba thực hành **Example Mapping, contract test, TDD/CI hoặc pairing**, giải thích tác dụng của từng thực hành và cách đo sau thử.

### Bài tập 9 — Thiết kế thí nghiệm WIP

Đội đang có nhiều story ở Review/Test, item già nhưng ít người giúp review.

**Yêu cầu:** Viết giả thuyết, chính sách giảm WIP và hỗ trợ hoàn tất trong bốn tuần; chỉ số age/blocked/rework cần xem; guardrail chất lượng và điều kiện dừng thử nghiệm.

**Gợi ý:** Đừng chọn việc đóng ticket nhanh bằng cách bỏ kiểm thử. Đừng vội xem tuần đầu throughput giảm là thất bại.

### Bài tập 10 — Bảo vệ cách đo khỏi tối ưu giả

Một quản lý yêu cầu: “Mọi item quá 10 ngày phải đóng và tạo ticket mới để dashboard sạch; mọi blocked time bị trừ khỏi age.”

**Yêu cầu:** Giải thích tác hại đối với cycle time, SLE, sự minh bạch và người dùng. Đề xuất cách trình bày cả **age gốc, blocked duration, trạng thái hiện tại và rủi ro**.

### Bài tập 11 — Dữ liệu không đủ

Bạn chỉ có cột trạng thái hiện tại và ngày tạo ticket; không có thời điểm START, các mốc blocker hoặc lịch sử reopen.

**Yêu cầu:** Nêu chỉ số nào có thể và **không thể** tính đáng tin từ dữ liệu đó. Đề xuất sự kiện tối thiểu cần bổ sung, không tự bịa giờ bắt đầu.

### Bài tập 12 — Tổng hợp số liệu thành một quyết định

Trong bốn tuần thử nghiệm, WIP giảm từ 11 xuống 8; median cycle time giảm 10 xuống 8 ngày; median blocked time của item từng blocked giảm 4 xuống 2 ngày; tỷ lệ item có rework giảm từ 8/16 xuống 6/19. Cùng kỳ đối tác cũng sửa API.

**Yêu cầu:** Viết nhận định 150–200 từ gồm **quan sát**, **điều chưa thể kết luận**, **nguồn gây nhiễu**, **chất lượng cần bảo vệ** và **thử nghiệm tiếp**.

**Gợi ý:** Không quy toàn bộ cải thiện cho một thay đổi; kiểm tra item chưa Done, cỡ mẫu, chính sách ghi và lỗi nghiêm trọng.

## 28. Checklist sử dụng ba tín hiệu một cách có trách nhiệm

- [ ] Đã xác định **item được đếm, start point, finish point và đơn vị thời gian**?
- [ ] Work item age chỉ áp dụng cho item **chưa Done**, không gọi nhầm cycle time?
- [ ] Start time được giữ nguyên khi item chuyển cột, bị chặn hoặc quay lại code?
- [ ] Dữ liệu cycle time tham chiếu thuộc **loại việc và workflow tương đồng**?
- [ ] SLE có cách tính, cỡ mẫu, khoảng thời gian và giới hạn diễn giải?
- [ ] Không dùng P85 để tuyên bố chắc chắn “còn bao nhiêu ngày” với item già?
- [ ] Chính sách blocked phân biệt trở ngại cụ thể với chờ bình thường?
- [ ] Blocker đang mở có người phối hợp, nguyên nhân và hành động xem lại?
- [ ] Các khoảng blocked **chồng lấp đã được hợp nhất** khi tính blocked time thực?
- [ ] Đã phân biệt duration theo nguyên nhân với thời gian thực item bị chặn?
- [ ] Đồng hồ, múi giờ, ngày lịch/ngày làm việc và mốc snapshot nhất quán?
- [ ] Tỷ lệ blocked có **tử số, mẫu số và tập quan sát** rõ?
- [ ] Đã ghi các vòng làm lại trước Done, không chỉ số ticket reopened?
- [ ] Có phân biệt rework do lỗi/hiểu sai với cải tiến/refactor hoặc nhu cầu mới?
- [ ] Cách đo rework nêu rõ dùng số vòng, giờ công hay tỷ lệ item?
- [ ] Bằng chứng về **nguyên nhân** đã được kiểm tra, không chỉ chọn nhãn trên board?
- [ ] Có xem cả các item già chưa Done, không chỉ các item hoàn thành nhanh?
- [ ] Đã kết hợp age, blocked, rework với WIP, throughput, cycle time và chất lượng?
- [ ] Quyết định ưu tiên có xét Product Goal, Sprint Goal, tác động và mức khẩn?
- [ ] Đã chọn thử nghiệm nhỏ có giả thuyết, khoảng quan sát và guardrail?
- [ ] Không hạ Definition of Done, bỏ test hoặc reset ticket để số liệu đẹp?
- [ ] Không dùng chỉ số để xếp hạng, trừng phạt hoặc giám sát từng cá nhân?
- [ ] Có hành động, người phối hợp và thời điểm xem lại sau khi đọc dashboard?
- [ ] Khi đánh giá trước/sau đã xét thay đổi workflow, loại item, nhân sự và phụ thuộc?

Checklist là công cụ cho **đối thoại và cải tiến dòng công việc**, không phải thủ tục bắt buộc giống nhau cho mọi tổ chức. Đội nên bắt đầu bằng những tín hiệu giúp giải quyết trở ngại thực, tránh tăng chi phí đo lường không phục vụ quyết định.

## 29. Tổng kết

- **Work item age** đo thời gian trôi qua của **việc đang mở**, tính từ start point đến snapshot. Nó giúp phát hiện sớm nguy cơ và hỗ trợ hoàn tất trước khi item trở thành một trường hợp cycle time kéo dài.
- **Blocked time** đo thời gian thực một item không thể tiến theo **chính sách blocked**. Khi nhiều blocker đồng thời, phải **hợp các khoảng thời gian**; không cộng trùng.
- **Rework** đo những vòng sửa/làm lại cần thiết, nhưng **không phải mọi thay đổi do phản hồi đều xấu**. Cần phân biệt lỗi, hiểu sai, thay đổi hợp lệ, refactoring và hoạt động học hỏi.
- **Định nghĩa phép đo quan trọng hơn độ đẹp của biểu đồ:** Điểm start/finish, loại item, timestamp, mẫu số, chính sách reopen và blocker phải nhất quán.
- **Đọc ba tín hiệu cùng nhau và cùng chất lượng:** Age cao có thể do chờ; blocked giảm không có ích nếu rework và lỗi production tăng; throughput tăng không chứng minh giá trị người dùng tốt hơn.
- **SLE và phân bố lịch sử hỗ trợ cuộc trao đổi**, không phải lời hứa chắc chắn về thời gian còn lại của một item đang già.
- **Scrum, Kanban và XP bổ sung nhau**: Scrum cung cấp mục tiêu và cơ chế thực nghiệm; Kanban giúp minh bạch flow và quản lý WIP; XP hỗ trợ phản hồi kỹ thuật sớm, giảm lỗi tích hợp và rework có thể tránh.
- **Mục đích đo lường Agile là giúp đội học và hành động:** Gỡ phụ thuộc, làm rõ yêu cầu, kiểm thử sớm, chia lát cắt phù hợp, bảo vệ DoD và giao giá trị ổn định, thay vì đổ lỗi cho cá nhân.

Khi thấy một user story đã mở lâu và phải sửa nhiều lần, hãy hỏi: **“Nó đã già bao lâu, thực sự bị chặn ở khoảng nào, vì sao phải làm lại, có thể thay đổi hệ thống làm việc thế nào để những item tiếp theo hoàn tất sớm và an toàn hơn?”**
