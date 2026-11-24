# Đo thời gian chu kỳ (cycle time), WIP và thông lượng

Một nhóm phát triển nền tảng học trực tuyến đã hoàn tất 12 user story trong Sprint vừa qua. Product Owner thấy số lượng hạng mục Done tăng và nghĩ rằng nhóm đang nhanh hơn. Nhưng Developers nhận thấy nhiều hạng mục phải chờ code review, kiểm thử tích hợp và quyết định về dữ liệu tiến độ học. Những PBI được bắt đầu đầu Sprint thường vẫn chưa hoàn tất khi Sprint Review đến; nhiều việc mới liên tục được mở thêm trong lúc việc cũ còn kẹt.

**“Đội đã làm được bao nhiêu?”** mới là một nửa câu hỏi. Để cải thiện dòng tạo giá trị, còn phải biết:

- **Một hạng mục đã bắt đầu mất bao lâu để hoàn tất?** — *Cycle time*.
- **Tại một thời điểm, có bao nhiêu hạng mục đang được xử lý nhưng chưa hoàn tất?** — *Work in Progress (WIP)*.
- **Trong một khoảng thời gian, có bao nhiêu hạng mục thực sự hoàn tất?** — *Throughput*.

Ba chỉ số này giúp nhóm quan sát dòng công việc thay vì chỉ dựa vào cảm giác “rất bận” hoặc “đóng nhiều ticket”. Nhưng **không chỉ số nào tự chứng minh sản phẩm tạo giá trị, đạt Definition of Done hoặc người dùng hài lòng**. Các phép đo chỉ đáng tin nếu nhóm xác định ranh giới đo thống nhất, kiểm tra chất lượng dữ liệu và thảo luận bối cảnh trước khi ra quyết định.

Bài học thuộc chương **Đo lường Agile** của mô-đun **AGILE_DEVELOPMENT**: hiểu giá trị và nguyên tắc Agile, thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Định nghĩa chính xác **cycle time, WIP và throughput**, gồm đơn vị đo, điểm bắt đầu/kết thúc và phạm vi hệ thống.
- Phân biệt **cycle time, lead time, work item age, blocked time, touch time** và **flow efficiency**.
- Tính cycle time cho từng hạng mục, throughput theo từng khoảng thời gian và WIP ở một thời điểm dựa trên dữ liệu ví dụ.
- Phân tích **trung vị, phân phối, phân vị và Service Level Expectation (SLE)** thay vì chỉ báo cáo trung bình.
- Giải thích mối liên hệ giữa WIP, throughput và cycle time qua **Little’s Law**, nêu những điều kiện và hạn chế khi áp dụng.
- Đọc **cumulative flow diagram (CFD)**, biểu đồ cycle time và xu hướng throughput để đặt câu hỏi về điểm nghẽn.
- Sử dụng **work item age** để xem một việc đang thực hiện có nguy cơ mắc kẹt trước khi nó Done.
- Đưa ra một **dự báo có điều kiện** từ throughput lịch sử, phân biệt dự báo với cam kết và deadline.
- Thiết kế cách đo phù hợp cho Scrum hoặc Kanban, giữ nguyên chất lượng Increment theo Definition of Done.
- Tránh những hành vi tối ưu sai như **tách ticket giả tạo, hạ tiêu chuẩn Done, cố giữ WIP đẹp bằng cách giấu công việc** hoặc xếp hạng cá nhân bằng số ticket.
- Đề xuất một thử nghiệm cải thiện dòng công việc và xác định tín hiệu đánh giá sau đó.

## 2. Đo luồng công việc để trả lời câu hỏi gì?

### 2.1. Dòng công việc không phải danh sách mọi hoạt động bận rộn

Một hạng mục có thể đi qua những trạng thái:

```text
Backlog -> Ready -> In Progress -> Review -> Verification -> Done
                       _____________ WIP ___________/
```

Sơ đồ chỉ là **ví dụ về workflow**; không có bộ cột cố định bắt buộc cho mọi nhóm. Hạng mục có thể chuyển giữa các trạng thái theo chính sách được công bố. Điểm quan trọng là từ khi một việc **bắt đầu được xử lý** tới lúc nó **thực sự hoàn tất** sẽ bao gồm cả thời gian làm, chờ review, chờ kiểm thử hoặc bị chặn.

Nhóm muốn biết:

1. **Khả năng hoàn tất:** các hạng mục đã qua ranh giới Done với tốc độ nào?
2. **Thời gian người yêu cầu phải chờ:** một việc mất bao lâu sau khi bắt đầu?
3. **Mức công việc mở song song:** có bao nhiêu việc chiếm sự chú ý và năng lực?
4. **Độ ổn định:** thời gian hoàn tất biến động thế nào giữa các hạng mục?
5. **Khả năng dự báo:** dựa trên dữ liệu hiện tại có thể nói gì về những hạng mục còn lại?
6. **Cải tiến:** hệ thống đang chờ ở đâu, điều gì đáng thử để giảm chờ?

### 2.2. Ba chỉ số trả lời ba câu hỏi khác nhau

| Chỉ số | Câu hỏi | Đơn vị ví dụ | Đối tượng đo |
| --- | --- | --- | --- |
| **Cycle time** | “Một hạng mục đã bắt đầu mất bao lâu để hoàn tất?” | Giờ hoặc ngày lịch trên mỗi hạng mục | Hạng mục **đã hoàn tất** |
| **WIP** | “Ngay bây giờ có bao nhiêu hạng mục đã bắt đầu nhưng chưa hoàn tất?” | Hạng mục tại một thời điểm | Hạng mục **đang mở trong luồng** |
| **Throughput** | “Trong kỳ này có bao nhiêu hạng mục hoàn tất?” | Hạng mục/ngày, hạng mục/tuần | Số lần vượt qua ranh giới **Done** |

Ví dụ một đội có **WIP = 8 hạng mục**, hoàn tất **5 hạng mục/tuần** và cycle time trung vị **9 ngày**. Ba số này có thể cùng tồn tại. Không thể suy ra chỉ từ đó rằng “mỗi Developer làm 1,6 ticket” hoặc “người dùng sẽ nhận được năm tính năng lớn mỗi tuần”.

### 2.3. Những gì ba chỉ số chưa nói

Chúng không trực tiếp trả lời:

- Người sử dụng có giải quyết đúng nhu cầu không?
- Chất lượng và bảo mật có đạt không?
- Các hạng mục có cùng kích thước/độ khó không?
- Bao nhiêu công việc đã bị hủy, tạm dừng hoặc chuyển trạng thái?
- Một lỗi production có ảnh hưởng nghiêm trọng đến người dùng không?
- Nhóm có đang bỏ qua công việc vận hành để tăng throughput phát triển không?
- Product Goal có tiến triển không?

Vì vậy, **đo flow phải kết hợp tín hiệu chất lượng và outcome**, không được dùng thay cho phản hồi sản phẩm.

## 3. Định nghĩa hệ thống đo trước khi thu thập số liệu

### 3.1. “Bắt đầu” và “hoàn tất” phải có quy tắc

Trong một nhóm, “bắt đầu” có thể là lúc PBI được chuyển vào cột `In Progress`, lúc Developer nhận xử lý hoặc lúc công việc đầu tiên được ghi nhận. Với cycle time, hãy chọn **một ranh giới thể hiện công việc thực sự đã được kéo vào hệ thống** và áp dụng nhất quán.

Tương tự, “hoàn tất” không nên chỉ là “đã viết xong mã” nếu hạng mục vẫn cần review, test và tích hợp. Ví dụ:

> **Start:** khi PBI được kéo từ `Ready` vào `In Progress` theo chính sách của nhóm.
> **Finish:** khi PBI đạt **Definition of Done**, đã tích hợp và được ghi `Done`.

Ranh giới này đo **thời gian dòng công việc từ bắt đầu phát triển đến Done**. Nếu muốn đo từ lúc khách hàng gửi yêu cầu hoặc từ lúc phát hành cho người dùng, đó là một phép đo khác và cần đặt tên rõ.

### 3.2. Chọn giờ hay ngày theo lịch?

Có thể dùng:

- **Giờ lịch liên tục:** phù hợp hệ thống nhiều sự kiện nhỏ.
- **Ngày lịch:** dễ so sánh các hạng mục phát triển kéo dài nhiều ngày.
- **Ngày làm việc:** đôi khi hữu ích nhưng cần lịch nghỉ, ngày lễ, múi giờ và chính sách xử lý công việc ngoài giờ rõ.

Không nên đo cycle time bằng ngày làm việc rồi đối chiếu thẳng với throughput theo ngày lịch mà không giải thích sự khác biệt. Trong bài này, ví dụ chính dùng **ngày lịch tương đối**, để tính toán nhất quán.

### 3.3. Định nghĩa “work item”

Đội cần nêu đang đếm gì:

- PBI đã đáp ứng DoD.
- Ticket sửa lỗi.
- Hạng mục hỗ trợ.
- Thay đổi triển khai.
- Lô công việc theo dịch vụ của nhóm.

**Một ticket không nhất thiết là một đơn vị giá trị hay nỗ lực tương đương ticket khác.** Nếu nhóm đổi cách chia PBI thành nhiều ticket nhỏ, throughput có thể tăng dù lượng giá trị giao không đổi.

### 3.4. Phân loại theo loại công việc khi cần

Một nhóm có thể theo dõi:

| Loại công việc | Ví dụ | Lý do phân nhóm |
| --- | --- | --- |
| **Tính năng** | Lát cắt “Tiếp tục bài học” | Đánh giá luồng tạo khả năng mới |
| **Bug** | Lỗi lưu tiến độ | Thấy ảnh hưởng của chất lượng đến năng lực |
| **Rủi ro/bảo mật** | Vá kiểm tra quyền truy cập | Không để loại công việc khẩn bị che |
| **Nợ kỹ thuật** | Refactor chính sách quyền truy cập | Theo dõi đầu tư giữ khả năng thay đổi |
| **Vận hành** | Sửa pipeline CI, hỗ trợ migration | Thấy năng lực thực của nhóm được sử dụng thế nào |

Phân loại hữu ích để **giải thích khác biệt**, không phải để tạo nhiều bảng thành tích và buộc từng loại phải có tốc độ bằng nhau.

## 4. Cycle time: thời gian chu kỳ của một hạng mục

### 4.1. Định nghĩa và công thức

Nếu một hạng mục bắt đầu tại thời điểm `S` và hoàn tất tại `F` theo cùng múi giờ/đơn vị:

```text
Cycle time của hạng mục = F - S

Ví dụ:
  bắt đầu: đầu ngày D3
  hoàn tất: đầu ngày D8
  cycle time = 8 - 3 = 5 ngày lịch
```

Đây là quy ước **mốc thời điểm**: hoàn tất đúng đầu ngày D8 thì không tính thêm cả ngày D8. Nếu công cụ đếm ngày bao gồm cả ngày bắt đầu và ngày kết thúc, số hiển thị có thể khác một đơn vị. Không so sánh các báo cáo dùng hai quy ước khác nhau mà không chuẩn hóa.

### 4.2. Cycle time gồm những khoảng chờ nào?

Một PBI minh họa:

| Giai đoạn trong ranh giới đã chọn | Thời gian |
| --- | ---: |
| Developer thực hiện phần chính | 1 ngày |
| Chờ reviewer rảnh | 3 ngày |
| Review và sửa nhận xét | 0,5 ngày |
| Chờ môi trường tích hợp | 1 ngày |
| Kiểm thử và tích hợp hoàn tất | 0,5 ngày |
| **Tổng cycle time** | **6 ngày** |

Tổng thời gian “chạm vào việc” minh họa là **2 ngày**, thời gian chờ **4 ngày**. Đây là ví dụ để thấy **cycle time không phải effort của Developer**. Nếu đội chỉ đo thời gian lập trình, họ có thể bỏ qua phần lớn thời gian người dùng phải chờ.

### 4.3. Phân biệt cycle time và lead time

Hai thuật ngữ dễ bị dùng khác nhau giữa Kanban, Lean và các công cụ. Một quy ước phổ biến:

- **Lead time:** từ lúc có yêu cầu hoặc lúc cam kết xử lý đến khi hoàn tất.
- **Cycle time:** từ lúc công việc **thực sự bắt đầu** đến khi hoàn tất.

Ví dụ một yêu cầu có mặt trong backlog 10 ngày rồi được kéo vào In Progress; sau đó mất 6 ngày để đạt Done.

```text
Ngày 0       Ngày 10          Ngày 16
  |-------------|----------------|
  Nhận yêu cầu  Bắt đầu         Done

Lead time (từ yêu cầu): 16 ngày
Cycle time (từ bắt đầu): 6 ngày
Thời gian trước khi bắt đầu: 10 ngày
```

Nếu nhóm dùng thuật ngữ khác, cần công bố rõ **cặp mốc nào đang được đo**, không tranh luận chỉ vì nhãn.

### 4.4. Cycle time khác elapsed time, touch time và effort

| Thuật ngữ | Nói về | Ví dụ |
| --- | --- | --- |
| **Elapsed time** | Khoảng thời gian thực tế giữa hai mốc | 6 ngày lịch |
| **Cycle time** | Elapsed time giữa mốc Start và Done đã công bố | 6 ngày lịch từ In Progress tới Done |
| **Touch time / active time** | Khoảng thực sự có thao tác tạo hoặc kiểm chứng công việc | Khoảng 2 ngày làm việc thực tế |
| **Blocked/waiting time** | Khoảng việc đang trong luồng nhưng không thể tiến triển | 4 ngày chờ review/môi trường |
| **Effort** | Công sức bỏ ra, có thể cộng của nhiều người | 3 người × 2 giờ = 6 người-giờ |
| **Lead time** | Khoảng thời gian người yêu cầu chờ theo mốc chọn | 16 ngày tính từ khi yêu cầu được ghi nhận |

Một hạng mục được hai Developer cùng làm trong một ngày có thể tốn **2 người-ngày effort**, nhưng cycle time vẫn khoảng **một ngày**, không phải hai. Những đại lượng này trả lời câu hỏi khác nhau.

## 5. Đọc phân phối cycle time: đừng chỉ dùng trung bình

### 5.1. Vì sao trung bình có thể che vấn đề?

Giả sử năm hạng mục mất lần lượt **2, 3, 3, 4, 18 ngày**.

- **Trung bình:** (2 + 3 + 3 + 4 + 18) / 5 = **6 ngày**.
- **Trung vị:** **3 ngày**.
- **Giá trị dài nhất:** **18 ngày**.

Nếu chỉ nói “trung bình 6 ngày”, người nghe có thể không biết đa số việc xong nhanh nhưng có một việc mắc kẹt rất lâu. Một trường hợp 18 ngày có thể là:

- Sự cố phụ thuộc bên ngoài.
- Hạng mục lớn hơn hẳn.
- Thay đổi yêu cầu.
- Chờ quyết định dữ liệu hoặc bảo mật.
- Một lỗi cần điều tra nhiều tầng.

**Phân phối và các trường hợp đuôi dài** thường cung cấp tín hiệu cải tiến tốt hơn một số trung bình đơn lẻ.

### 5.2. Percentile là gì?

Phân vị cho biết **tỷ lệ hạng mục đã hoàn tất có cycle time không vượt quá một ngưỡng** trong mẫu được xét. Ví dụ “85% hạng mục đã Done trong vòng 10 ngày” là một thông tin mô tả lịch sử, nếu dữ liệu và ranh giới đo nhất quán.

Với các mẫu nhỏ, cách tính percentile của công cụ có thể khác nhau (nội suy hoặc xếp hạng gần nhất). Phải nói rõ **phương pháp**, và không diễn giải một mẫu 10 việc là quy luật chắc chắn cho tương lai.

### 5.3. Service Level Expectation (SLE)

Trong hướng dẫn Kanban, **SLE** là kỳ vọng về khoảng thời gian để một hạng mục đi từ Start tới Finish, thường diễn đạt dưới dạng:

> “Chúng tôi kỳ vọng **85%** hạng mục loại này được hoàn tất trong **10 ngày lịch hoặc ít hơn**, dựa trên quan sát lịch sử và điều kiện hiện tại.”

SLE là **kỳ vọng có xác suất**, không phải lời hứa rằng mọi việc chắc chắn xong trong 10 ngày. Nên dùng SLE để:

- Thảo luận kỳ vọng với người yêu cầu.
- Nhận biết hạng mục đang già đi bất thường.
- Tìm những trường hợp tắc nghẽn cần hỗ trợ.
- Xem lại chính sách làm việc và năng lực hệ thống.

Nếu chưa có dữ liệu lịch sử phù hợp, nhóm có thể bắt đầu bằng **phán đoán tạm thời có ghi giả định** và điều chỉnh khi đã có bằng chứng.

### 5.4. Cẩn trọng với những hạng mục chưa hoàn tất

Một báo cáo chỉ lấy cycle time của các việc Done sẽ **không nhìn thấy đầy đủ công việc đang mở rất lâu**. Nếu nhóm hoàn thành nhiều việc nhỏ và để vài việc lớn kẹt nhiều tuần, trung bình các việc Done có thể đẹp lên trong khi WIP già hóa.

Vì vậy, nên xem **work item age của việc đang mở** cùng với **phân phối cycle time của việc đã hoàn tất**.

## 6. WIP: số hạng mục đang được thực hiện

### 6.1. Định nghĩa theo thời điểm

**Work in Progress (WIP)** là số hạng mục **đã bắt đầu nhưng chưa hoàn tất** tại thời điểm quan sát, theo ranh giới workflow mà nhóm công bố.

```text
WIP tại thời điểm t =
  số hạng mục có Start <= t
  và chưa có Finish <= t
```

Cách diễn đạt tương đương cho dữ liệu có mốc thời gian:

```text
WIP(t) = số item thỏa Start <= t < Finish,
         cộng các item đã Start nhưng chưa có Finish.
```

Hai cách chỉ tương đương khi trạng thái không có những ngoại lệ chưa được định nghĩa, chẳng hạn hạng mục đã hủy hoặc chuyển khỏi hệ thống. Đội cần có chính sách riêng cho những tình huống đó.

### 6.2. Blocked vẫn là WIP

Một hạng mục đã bắt đầu nhưng chờ quyết định, chờ review hoặc chờ hệ thống ngoài thường vẫn thuộc WIP, bởi nó:

- Chưa mang lại Increment Done.
- Vẫn cần chú ý và điều phối.
- Có thể gây chuyển ngữ cảnh.
- Đang làm tăng thời gian người yêu cầu chờ.

**Không được chuyển một item bị chặn về Backlog chỉ để giảm số WIP trên dashboard** khi đội thực chất vẫn cam kết xử lý nó. Nếu công việc thật sự được **hủy hoặc trả lại trạng thái chưa bắt đầu**, cần công bố cách ghi sự kiện ấy, không xóa lịch sử tùy tiện.

### 6.3. WIP và WIP limit khác nhau

- **WIP thực tế:** có bao nhiêu item đang mở trong vùng đo.
- **WIP limit:** chính sách giới hạn số việc có thể mở trong một trạng thái hoặc toàn hệ thống.

Ví dụ cột `In Progress` có WIP limit = 3 nhưng đang có bốn item. Đây là tín hiệu cần trao đổi: có sự cố khẩn, chính sách chưa rõ, hạng mục bị ẩn hay đội đang mở quá nhiều việc?

**WIP limit không phải công cụ trừng phạt**. Mục đích là thúc đẩy nhóm **hoàn tất việc cũ, tập trung hỗ trợ điểm nghẽn và giảm chuyển ngữ cảnh**. Có ngoại lệ cần được công bố và xem lại, đặc biệt với sự cố khẩn cấp.

### 6.4. Tại sao WIP cao thường đi cùng chờ lâu?

Khi nhóm mở quá nhiều việc cùng lúc:

- Mỗi hạng mục phải chia sẻ thời gian Developer, reviewer và môi trường.
- Những người đang giúp xử lý việc A có thể bị gọi sang B rồi C.
- Review và kiểm thử tạo hàng chờ.
- Những quyết định còn mở giữ nhiều ngữ cảnh trong đầu.
- Tích hợp bị dồn thành lô lớn.

Không thể nói **mọi** hệ thống WIP cao đều do “lười hoàn tất”; WIP có thể tăng vì dịch vụ ngoài chậm hoặc nhu cầu đến đột ngột. Nhưng WIP là **một tín hiệu sớm để hỏi dòng đang bị nghẽn ở đâu**.

### 6.5. Giới hạn WIP ở đâu?

Có thể có giới hạn:

- Tại từng cột như `In Progress` hoặc `Review`.
- Cho toàn bộ vùng từ Start tới Done.
- Theo một loại công việc hoặc nhóm năng lực cụ thể.
- Theo một chính sách dịch vụ cho việc khẩn cấp.

Giới hạn cục bộ phải phù hợp **toàn bộ luồng**. Nếu chỉ giảm WIP ở In Progress bằng cách chuyển hàng trăm việc sang Review, tổng WIP không thực sự giảm. Hãy nhìn cả **WIP theo trạng thái và WIP toàn hệ thống**.

## 7. Throughput: số hạng mục thực sự hoàn tất

### 7.1. Định nghĩa theo khoảng thời gian

**Throughput** là **số hạng mục đi qua ranh giới Finish/Done** trong một khoảng thời gian xác định.

```text
Throughput trong [A, B) =
  số item có thời điểm Finish >= A và Finish < B

Ví dụ:
  tuần 1: 6 item Done
  tuần 2: 8 item Done
  tuần 3: 5 item Done
```

Khi báo cáo theo ngày/tuần, hãy nêu rõ **múi giờ và quy tắc kỳ**. Với hạng mục hoàn tất đúng lúc chuyển kỳ, phải có chính sách nhất quán để không đếm hai lần hoặc bỏ sót.

### 7.2. Không dùng effort hoặc story points để thay throughput item

Nếu đội hoàn tất:

- Hai PBI 3 điểm.
- Một PBI 8 điểm.
- Một PBI 13 điểm.

Thì **throughput theo PBI** là **4 item**, còn **tổng story points** theo cách ước lượng ấy là **27 điểm**. Chúng khác đơn vị và mục đích.

Story points thường được dùng để trao đổi độ lớn tương đối trong một số nhóm Scrum. Chúng không phải phép đo khách quan về giá trị hay công sức và không thể so trực tiếp giữa các đội. **Throughput item** cũng không xóa khác biệt kích thước; nếu dùng nó để dự báo, nhóm phải hiểu cách chia việc và sự biến động lịch sử.

### 7.3. Throughput có thể biến động

Ví dụ lịch sử tám tuần:

| Tuần | Item Done |
| --- | ---: |
| 1 | 6 |
| 2 | 8 |
| 3 | 7 |
| 4 | 9 |
| 5 | 5 |
| 6 | 8 |
| 7 | 7 |
| 8 | 6 |
| **Tổng** | **56** |

**Trung bình:** 56 / 8 = **7 item/tuần**. Nhưng có tuần chỉ **5**, có tuần **9**. Nếu dùng một số “7” làm cam kết cứng, nhóm đang bỏ qua độ biến động.

Thông tin hữu ích hơn: trong bối cảnh và cách chia việc này, lịch sử gần đây nằm khoảng **5–9 item/tuần**, với trung bình 7. Không được biến khoảng quan sát nhỏ ấy thành một **khoảng tin cậy thống kê** khi chưa có phân tích và dữ liệu phù hợp.

### 7.4. Không thưởng cho việc tách ticket giả tạo

Nếu một PBI đáng ra là một lát cắt có giá trị bị tách thành mười ticket “đổi tên biến”, throughput có thể tăng từ 1 lên 10 mà người dùng không nhận thêm giá trị. Vì vậy:

- Gắn Finish với tiêu chuẩn Done thực.
- Giữ chính sách chia hạng mục nhất quán.
- Phân loại loại công việc khi cần.
- Xem chất lượng và outcome.
- Không dùng throughput làm **chỉ tiêu cá nhân**.

## 8. Một bộ dữ liệu đầy đủ để tính ba chỉ số

Chúng ta dùng **10 hạng mục giả định** thuộc một đội xây tính năng học tập. Các ngày D1, D2, ... là **mốc đầu ngày lịch tương đối**. Ví dụ D1 → D3 nghĩa là **2 ngày**, không tính thêm một ngày ở D3.

### 8.1. Bảng sự kiện Start và Finish

| Item | Bắt đầu | Hoàn tất | Cycle time (ngày lịch) | Loại công việc |
| --- | --- | --- | ---: | --- |
| A | D1 | D3 | 2 | Lát cắt tiến độ |
| B | D1 | D5 | 4 | Kiểm thử API |
| C | D2 | D6 | 4 | Sửa lỗi |
| D | D3 | D8 | 5 | Lát cắt giao diện |
| E | D5 | D9 | 4 | Sửa lỗi |
| F | D6 | D11 | 5 | Cải tiến kỹ thuật |
| G | D8 | D12 | 4 | Lát cắt dữ liệu |
| H | D10 | D14 | 4 | Lát cắt giao diện |
| I | D11 | D17 | 6 | Tích hợp API |
| J | D13 | D18 | 5 | Lát cắt bảo mật |

Trong ví dụ, **tất cả đều đã hoàn tất** tại thời điểm sau D18. Các số có mục đích dạy tính toán; không phải thống kê của nhóm hay sản phẩm thật.

### 8.2. Tính cycle time

Tập thời gian:

```text
A=2, B=4, C=4, D=5, E=4,
F=5, G=4, H=4, I=6, J=5

Tổng = 2 + 4 + 4 + 5 + 4 + 5 + 4 + 4 + 6 + 5
     = 43 ngày-item

Trung bình = 43 / 10 = 4,3 ngày/item

Sắp xếp:
2, 4, 4, 4, 4, 4, 5, 5, 5, 6

Trung vị = (vị trí 5 + vị trí 6) / 2
         = (4 + 4) / 2 = 4 ngày
```

Chú ý: trung vị là **4 ngày** theo tập này, không phải 4,5 ngày. Nếu dữ liệu đổi, phải tính lại, không suy từ cảm giác.

### 8.3. Tính WIP tại đầu ngày D12

Quy tắc một item đang WIP tại mốc `t`:

> Đã bắt đầu tại hoặc trước `t` và chưa hoàn tất tại mốc ấy.

Tại **đầu D12**:

- **H:** Start D10, Finish D14 → **đang mở**.
- **I:** Start D11, Finish D17 → **đang mở**.
- **G:** Finish D12 → **đã hoàn tất tại đúng đầu D12**, không còn WIP.
- **J:** Start D13 → **chưa bắt đầu**.

Các item A–F đã Done.

Vậy:

```text
WIP tại đầu D12 = 2 item (H và I)

Work item age của H = D12 - D10 = 2 ngày
Work item age của I = D12 - D11 = 1 ngày
```

WIP là **ảnh chụp tại một thời điểm**, không phải “số item từng có trong tuần”. Nếu muốn WIP bình quân phải lấy các mẫu WIP theo một quy tắc thời gian rõ, hoặc tính từ khoảng thời gian thực sự item tồn tại trong luồng.

### 8.4. Tính throughput theo ba tuần tương đối

Quy định ba kỳ không chồng lấn:

- **Tuần 1:** những Finish tại D1 đến trước D8.
- **Tuần 2:** Finish tại D8 đến trước D15.
- **Tuần 3:** Finish tại D15 đến trước D22.

| Kỳ | Item hoàn tất trong kỳ | Throughput |
| --- | --- | ---: |
| D1 ≤ Finish < D8 | A (D3), B (D5), C (D6) | **3** |
| D8 ≤ Finish < D15 | D (D8), E (D9), F (D11), G (D12), H (D14) | **5** |
| D15 ≤ Finish < D22 | I (D17), J (D18) | **2** |
| **Ba kỳ** | **10 item** | **10** |

Trung bình minh họa: 10/3 ≈ **3,33 item/tuần** qua ba kỳ. Vì kỳ cuối chỉ có hai item trong ví dụ và hệ thống dừng ở D18, không nên coi 3,33 là năng lực ổn định đã được chứng minh.

### 8.5. SLE từ mẫu lịch sử này

Theo cách tính **nearest-rank** trên 10 thời gian đã hoàn tất, vị trí phân vị 85 là:

```text
ceil(0,85 × 10) = ceil(8,5) = vị trí 9
Giá trị ở vị trí 9 của dãy đã sắp xếp = 5 ngày
```

Trong mẫu này, **9/10 item = 90%** có cycle time **≤ 5 ngày**. Có thể đề xuất câu SLE **tạm thời** như “kỳ vọng ít nhất 85% item thuộc loại này hoàn tất trong khoảng 5 ngày lịch hoặc ít hơn”, nhưng **10 item là mẫu rất nhỏ** và nhiều loại công việc đang bị trộn chung. Trước khi dùng để ra quyết định bên ngoài, đội cần thêm dữ liệu phù hợp và xem tính ổn định.

### 8.6. Điều không được suy ra

Từ 10 item trên, **không** được kết luận:

- Mọi item tương lai chắc chắn Done trong 6 ngày.
- Mỗi Developer có năng suất 3,33 item/tuần.
- Mọi loại công việc có cùng kích thước.
- Đội đang làm đúng thứ có giá trị nhất.
- Không có item rất cũ vì trung bình chỉ 4,3 ngày.
- Một tuần ít item là do “thiếu cố gắng”.
- Cycle time 4,3 ngày chứng minh release sẽ diễn ra sau đúng 4,3 ngày.

Một bộ dữ liệu chỉ có ích nếu câu hỏi **phù hợp với định nghĩa và tính đại diện** của nó.

## 9. Work item age: phát hiện chờ lâu trước khi Done

### 9.1. Vì sao cần chỉ số của việc chưa hoàn tất?

**Cycle time chỉ có giá trị hoàn chỉnh sau khi hạng mục đi qua Finish**. Khi một PBI đang ở Review ngày thứ 12 mà chưa Done, nó chưa xuất hiện trong phân phối cycle time của các item đã hoàn tất, dù có thể đang là rủi ro quan trọng nhất.

**Work item age** là khoảng thời gian đã trôi qua từ Start của một hạng mục **chưa hoàn tất** tới thời điểm hiện tại.

```text
Work item age(t) = t - Start
áp dụng cho item đã Start nhưng chưa Finish tại t
```

Nếu một item bắt đầu đầu D4, tới đầu D10 vẫn chưa Done, age của nó là **6 ngày**. Đây **không** phải cycle time cuối cùng của item đó, vì nó chưa hoàn tất.

### 9.2. Kết hợp age với SLE

Giả sử nhóm có SLE tạm thời “85% item loại này Done trong ≤ 8 ngày”. Một item age **7 ngày** nên được xem xét sớm: nó còn chờ gì, có thể hỗ trợ không, có ngoại lệ quan trọng không?

Một item age **9 ngày** không có nghĩa người phụ trách “làm sai” hay “thất bại 100%”. Nó là tín hiệu về **một hạng mục đã vượt ngưỡng kỳ vọng**, cần điều tra nguyên nhân và trao đổi lại dự báo.

### 9.3. Kỹ thuật aging WIP

Một cuộc trao đổi ngắn trên bảng công việc có thể hỏi:

1. Item nào đang **già nhất**?
2. Item nào gần hoặc đã vượt SLE?
3. Đang chờ ai, hệ thống nào, quyết định hay kiểm chứng gì?
4. Có người khác hỗ trợ để **hoàn tất việc cũ** trước khi kéo việc mới không?
5. Có phải hạng mục quá lớn, nên làm rõ lát cắt có thể Done an toàn?
6. Có cần thông báo người yêu cầu về bất định hoặc thay đổi kỳ vọng?

**Đừng dùng tuổi công việc để ép người làm nhanh bất chấp DoD**. Nếu cần xử lý một blocker thật, ưu tiên gỡ nguyên nhân hệ thống.

## 10. Quan hệ giữa WIP, throughput và cycle time

### 10.1. Little’s Law ở dạng thực hành

Một hệ thống dòng công việc ổn định trong những điều kiện phù hợp có thể được mô tả bằng **Little’s Law**:

```text
Average WIP = Average throughput rate × Average cycle time

Tương đương:
Average cycle time = Average WIP / Average throughput rate
```

Cần dùng **đơn vị nhất quán**. Nếu throughput đo bằng item/tuần, cycle time phải tính bằng tuần; nhân lại cho kết quả item.

Ví dụ minh họa **một hệ thống giả định ổn định**:

```text
WIP bình quân = 6 item
Throughput bình quân = 3 item/tuần

Cycle time bình quân tương ứng:
6 item / (3 item/tuần) = 2 tuần
```

Không có nghĩa “mỗi item sẽ Done chính xác sau hai tuần”. Đây là **quan hệ về trung bình dài hạn** dưới điều kiện áp dụng, không phải phương trình cam kết cho từng PBI.

### 10.2. Điều kiện và giả định quan trọng

Khi dùng Little’s Law để diễn giải dòng Agile, phải đặc biệt chú ý:

- **Ranh giới hệ thống thống nhất:** WIP, Start/Finish và throughput xét cùng tập hạng mục.
- **Tính ổn định tương đối trong cửa sổ đo:** không liên tục tích lũy WIP mà throughput vẫn không theo kịp.
- **Không mất dấu công việc:** item vào/ra hệ thống, bị hủy hoặc chuyển dòng phải được xử lý rõ.
- **Khoảng quan sát đủ hữu ích:** tránh lấy một ngày lạ làm bình quân dài hạn.
- **Cùng loại công việc hoặc phân nhóm thích hợp:** biến động kích thước và chính sách có thể làm quan hệ khó dự báo.
- **Không dùng số liệu bị chỉnh để đạt KPI:** sự tin cậy của dữ liệu là điều kiện cơ bản.

Về toán học, Little’s Law là quan hệ rất rộng cho hệ thống dòng ổn định khi được định nghĩa đúng; **ứng dụng thực tế để dự báo** vẫn đòi hỏi kiểm tra tính đại diện, độ biến động và ranh giới đo.

### 10.3. Giảm WIP có thể giảm chờ, nhưng không phải phép màu

Nếu throughput giữ tương đối ổn định và WIP bình quân giảm, Little’s Law gợi ý cycle time bình quân có thể giảm. Tuy nhiên:

- Nếu giảm WIP bằng cách ngừng hỗ trợ hoặc bỏ qua việc bị chặn, throughput có thể giảm.
- Nếu một bottleneck thật không được xử lý, giảm WIP ở cột khác có thể không cải thiện toàn luồng.
- Nếu thay đổi loại công việc, so sánh trước–sau có thể không còn cùng điều kiện.
- Nếu bỏ kiểm thử, cycle time đẹp hơn nhưng người dùng chịu lỗi nhiều hơn.

Do đó hãy **giới hạn WIP có chủ đích, quan sát hệ thống và bảo vệ chất lượng**.

### 10.4. Không dùng Little’s Law như công thức ước lượng mọi story

Ví dụ nhóm có WIP bình quân 6, throughput 3/tuần và cycle time bình quân 2 tuần. Một PBI mới phức tạp, bị phụ thuộc đối tác và cần migration **không được bảo đảm** cũng mất hai tuần.

Quan hệ trung bình hỗ trợ **thảo luận năng lực của hệ thống**, không thay đánh giá những rủi ro đặc thù.

## 11. Đọc biểu đồ dòng công việc

### 11.1. Cumulative Flow Diagram (CFD)

**CFD** thường thể hiện số hạng mục tích lũy theo thời gian, tách bởi trạng thái workflow. Nó giúp quan sát:

- Mức WIP qua **khoảng cách giữa đường bắt đầu và đường hoàn tất** theo cùng ranh giới.
- Tốc độ số hạng mục hoàn tất qua độ dốc của đường Done.
- Giai đoạn nào tích lũy hàng chờ khi một dải trạng thái mở rộng.
- Dòng có ổn định hơn sau khi nhóm thay đổi WIP limit hoặc chính sách không.

Ví dụ sơ đồ khái niệm:

```text
Số item tích lũy
^
|                           Started  /------
|                      ____/         /
|                 ____/    WIP      /
|            ____/                 /
|       ____/  Done          _____/
|  ____/                 ___/
|_/_____________________/________________> Thời gian

Khoảng cách giữa Started và Done thể hiện WIP tồn đọng
theo định nghĩa ranh giới đang dùng.
```

Trong CFD thực tế, biểu đồ thường có các **dải trạng thái xếp chồng**. Hình ASCII chỉ gợi ý việc quan sát xu hướng, không thay một CFD có số liệu.

### 11.2. Cách đặt câu hỏi với CFD

- **Dải Review phình ra:** có đủ reviewer, test hay quyền quyết định không?
- **Đường Started tăng nhanh hơn Done:** nhóm đang mở nhiều việc hơn khả năng hoàn tất?
- **Hai đường tương đối song song:** WIP có ổn định hơn không?
- **Đường Done phẳng kéo dài:** blocker, sự cố, công việc lớn hay thiếu dữ liệu ghi Done?
- **Dải Verification dày bất thường:** kiểm thử tích hợp hoặc môi trường có đang nghẽn?
- **Đường Done nhảy một lần lớn:** nhóm đã dồn nhiều item tới ngày cuối Sprint hay chỉ cách cập nhật công cụ chưa chính xác?

Không kết luận từ hình một mình; **đọc board, xem item cụ thể và hỏi người đang thực hiện**.

### 11.3. Scatterplot cycle time

Một biểu đồ điểm có thể đặt:

- Trục ngang: thời điểm Finish.
- Trục dọc: cycle time của item đã Done.
- Mỗi chấm: một item hoàn tất.

Những chấm nằm rất cao biểu thị thời gian kéo dài; xu hướng chấm dịch xuống có thể gợi ý cải thiện. Nhưng phải xem có phải nhóm đã **thay đổi cách tách item hoặc loại công việc**.

### 11.4. Biểu đồ throughput theo tuần

Biểu đồ cột số item Done mỗi tuần có thể cho thấy độ biến động và xu hướng. Đừng chỉ tạo đường mục tiêu thẳng đẹp. Khi tuần thấp bất thường, hãy xem:

- Có ít ngày làm việc không?
- Nhiều incident bất ngờ?
- Item lớn hơn hoặc phụ thuộc nhiều hơn?
- Môi trường hoặc review bị chặn?
- Có thay đổi Definition of Done?
- Việc Done bị cập nhật trễ trên công cụ?

**Đồ thị không thay thế cuộc trao đổi về nguyên nhân và cách cải tiến.**

## 12. Các mẫu vấn đề thường gặp khi ba chỉ số biến động

| Quan sát | Giả thuyết cần kiểm tra | Thử nghiệm có thể làm |
| --- | --- | --- |
| **WIP tăng, throughput gần như giữ nguyên** | Nhóm mở thêm việc nhưng bottleneck không đổi | Giảm kéo việc mới, tập trung hoàn tất, tìm điểm chờ |
| **Cycle time tăng, throughput giảm** | Review, môi trường hoặc phụ thuộc đang nghẽn; cũng có thể item lớn hơn | Xem item lâu nhất, chia lát cắt, sửa bottleneck |
| **Throughput tăng, lỗi hồi quy tăng** | Có thể tách ticket quá nhỏ hoặc hạ chất lượng | Kiểm tra DoD, test, outcome và phân loại việc |
| **Throughput giảm một tuần, WIP ổn định** | Có thể biến động bình thường hoặc hạng mục dài hơn | So nhiều kỳ, phân phối và loại công việc |
| **Cycle time của item Done giảm nhưng WIP già tăng** | Việc nhỏ xong trước, việc lớn bị mắc lại | Theo dõi age, xử lý item già và blocker |
| **WIP thấp, throughput cũng thấp** | Không đủ năng lực, thiếu đầu vào Ready hoặc blocker | Xem điểm chờ; không tự động tăng WIP |
| **WIP cao ở Review** | Reviewer duy nhất, PR lớn, quy tắc review chưa rõ | Pairing, PR nhỏ, tự động hóa format, phân quyền reviewer |
| **WIP thấp, cycle time ổn, user không hài lòng** | Hệ thống nhanh nhưng làm sai điều có giá trị | Khám phá nhu cầu, xem Product Goal và validation |
| **Throughput cao ở cuối Sprint, rất thấp trước đó** | Công việc/kiểm chứng bị dồn lô, cập nhật trạng thái trễ | Chia PBI nhỏ, tích hợp đều, xem DoD liên tục |

Bảng là **gợi ý điều tra**, không khẳng định nguyên nhân nhân quả từ ba số. Cùng một dấu hiệu có thể do nhiều cơ chế tạo ra.

## 13. Cải thiện dòng bằng giới hạn WIP và tập trung hoàn tất

### 13.1. “Stop starting, start finishing”

Một nguyên tắc thực hành trong Kanban là **ưu tiên hoàn tất việc đang làm** thay vì liên tục mở thêm khi đầu vào còn quá nhiều.

Ví dụ:

- Cột Review đang có bốn PR, chỉ một người review.
- In Progress có hai Developer rảnh, họ định mở hai PBI mới.
- Thay vào đó nhóm kiểm tra có thể pairing xử lý review, bổ sung test và gỡ blocker để đưa các PBI hiện có đến Done.

Không phải lúc nào Developers cũng có thể trực tiếp review khu vực chuyên môn cao, nhưng họ có thể giúp **giảm khối lượng chuẩn bị, tái hiện lỗi, chia PR, viết kiểm chứng hoặc tổ chức tri thức**.

### 13.2. Giới hạn WIP không làm mất quyền xử lý khẩn cấp

Một chính sách có thể quy định:

> “Toàn hệ thống từ In Progress tới Done giới hạn thông thường 5 item. Nếu có sự cố bảo mật khẩn, được mở một item loại expedite theo quyết định chung; chúng ta ghi tác động đến những việc đang mở và xem lại sau khi xử lý.”

Mục tiêu là **minh bạch ngoại lệ**. Không được để một hàng ưu tiên khẩn cấp vô hạn làm mọi hạng mục bình thường già đi mãi.

### 13.3. Chia PBI theo giá trị đầu-cuối

Một PBI “hệ thống học cá nhân hóa toàn diện” có thể kéo dài vì phụ thuộc nhiều phần. Chia theo lát cắt thực:

1. Học viên tiếp tục bài gần nhất trên cùng thiết bị, đúng quyền.
2. Học viên thấy tiến độ cơ bản của khóa.
3. Học viên đồng bộ tiến độ giữa hai thiết bị.
4. Học viên nhận gợi ý học tiếp có thể tắt.

Mỗi lát cắt được chọn phải **đáp ứng Definition of Done** và có hành vi dùng được. Không chia “API Done”, “UI Done”, “DB Done” rồi cộng ba ticket vào throughput sản phẩm khi chưa có tính năng hoạt động đầu-cuối.

### 13.4. Swarming có chủ đích

Khi một item đang gần Done và bị chặn, đội có thể tập trung hai hoặc ba thành viên hỗ trợ:

- Một người tái hiện lỗi.
- Một người bổ sung integration test.
- Một người xem hợp đồng API.
- Cả nhóm xác nhận thay đổi đủ DoD.

**Swarming không phải tập trung mọi người vào một công việc dù họ không giúp được**. Hãy xem nút nghẽn cụ thể và năng lực cần thiết.

## 14. Dự báo bằng throughput lịch sử

### 14.1. Phân biệt forecast và commitment

- **Estimate:** đánh giá sơ bộ độ lớn hoặc công sức, có bất định.
- **Forecast:** dự đoán tương lai dựa trên dữ liệu, mô hình và giả định.
- **Goal/target:** kết quả đội muốn hướng tới.
- **Deadline:** mốc thời gian cần lưu ý, có thể do ràng buộc bên ngoài.
- **Commitment:** lời cam kết về mục tiêu hay nghĩa vụ cụ thể theo ngữ cảnh, không phải toàn bộ dự báo đều chắc chắn.

Một dự báo kiểu “21 item còn lại sẽ xong trong ba tuần” chỉ đáng tin nếu điều kiện và biến động được nêu rõ. **Không nên biến số trung bình thành hợp đồng không thay đổi**.

### 14.2. Ví dụ dự báo thô từ tám tuần

Dùng dãy throughput: **6, 8, 7, 9, 5, 8, 7, 6** item/tuần.

- Tổng: 56.
- Trung bình: 7 item/tuần.
- Số item còn lại giả định: 21.
- Ước tính tuyến tính thô: 21 / 7 = **3 tuần**.

Nhưng nếu tuần tới chỉ hoàn tất 5 item, ba tuần sẽ được 15; nếu mỗi tuần hoàn tất 9 item, cần ít nhất ba tuần để đạt 21. Khi có nhiều rủi ro, một cuộc trao đổi **“khoảng ba đến năm tuần trong điều kiện throughput còn tương tự”** có thể trung thực hơn một ngày giao hàng cố định, dù khoảng này **không phải khoảng tin cậy được tính thống kê**.

### 14.3. Tại sao dự báo bằng số item có hạn chế?

- Item có kích thước khác nhau.
- Có thể có công việc chưa thấy trong backlog.
- Yêu cầu có thể đổi.
- Có loại việc khẩn làm giảm năng lực còn lại.
- Việc cũ đang WIP có thể rất lớn hoặc già.
- Nhân sự, môi trường hoặc DoD có thể thay đổi.
- Cách ghi Done có thể không nhất quán.

Dự báo hữu ích khi làm rõ **phạm vi, điều kiện và mức bất định**, không phải khi che chúng.

### 14.4. Monte Carlo theo throughput: khi dữ liệu đủ

Một phương pháp thường dùng trong dự báo flow là **mô phỏng Monte Carlo**:

1. Chọn dữ liệu throughput lịch sử phù hợp với loại công việc và điều kiện gần đây.
2. Lấy mẫu các mức throughput theo kỳ để tạo nhiều kịch bản tương lai.
3. Trong mỗi kịch bản, cộng item Done cho tới khi đủ số item còn lại.
4. Ghi nhận số kỳ cần thiết.
5. Xem phân phối kết quả: ví dụ mốc 50%, 85% hoặc 95% tùy cách trao đổi rủi ro.

Mô phỏng **không tự đảm bảo dự báo đúng**. Nếu dữ liệu lịch sử không đại diện, workflow đổi, WIP đang già hoặc nhu cầu tới liên tục, số lượng vòng mô phỏng lớn vẫn chỉ tạo ra **một dự báo có nhiều chữ số nhưng sai giả định**.

### 14.5. Dự báo ngày giao hàng khác dự báo hoàn tất item

Nếu DoD kết thúc trước release, throughput của PBI Done không tự trả lời “khi nào tất cả người dùng nhận tính năng”. Cần xét:

- Kiểm chứng phát hành có điều kiện.
- Deployment và release cadence.
- Feature flag hoặc rollout theo nhóm.
- Migration dữ liệu, tuân thủ và khả năng hỗ trợ.
- Thời gian người dùng thực sự tiếp cận tính năng.

**Flow forecast và release plan cần kết nối nhưng không được đánh đồng.**

## 15. Cycle time, WIP và throughput trong Scrum

### 15.1. Scrum không quy định bộ ba chỉ số này là luật bắt buộc

*Scrum Guide 2020* mô tả Scrum Team, các sự kiện, artifacts và commitments. Nó không bắt buộc nhóm phải dùng một dashboard cycle time/WIP/throughput cụ thể. Tuy nhiên, nhóm Scrum **có thể dùng các tín hiệu flow để hỗ trợ kiểm tra và thích ứng**, đặc biệt khi muốn giảm công việc dở dang.

### 15.2. Sprint Planning: cân nhắc năng lực và độ biến động

Khi chọn PBI cho Sprint, Developers có thể xem:

- Trong các Sprint gần đây, bao nhiêu PBI đạt DoD?
- Hạng mục đang WIP có age nào đáng lo?
- Có điểm nghẽn review/test nào thường lặp lại?
- Có công việc bắt buộc như bảo mật, vận hành hoặc nâng cấp kỹ thuật?
- Có nên giảm số PBI mở cùng lúc để tăng cơ hội hoàn tất?

**Sprint Goal quan trọng hơn việc lấp đầy tất cả năng lực bằng ticket.** Không dùng throughput lịch sử để ép số story phải Done dù điều kiện thay đổi.

### 15.3. Daily Scrum: tập trung luồng và Sprint Goal

Một cuộc trao đổi Daily Scrum có thể hỏi:

- Item nào gần hoàn tất và cần hỗ trợ để đạt DoD?
- Item nào già nhất so với SLE/kỳ vọng?
- Có blocker nào khiến Sprint Goal rủi ro?
- Có nên tạm ngừng kéo việc mới để gỡ một điểm nghẽn?
- Developers cần thay đổi kế hoạch Sprint Backlog ra sao?

Thước đo flow có thể **nâng chất lượng cuộc thảo luận**, nhưng không thay thế quyền tự quản của Developers.

### 15.4. Sprint Review: kết nối với giá trị

Product Owner và stakeholder xem:

- Increment nào đã đạt DoD?
- Các thay đổi có giải quyết nhu cầu người dùng không?
- Điều gì trong môi trường sản phẩm đã thay đổi?
- Có phản hồi mới khiến Product Backlog phải điều chỉnh không?
- Những rủi ro nào còn cần xử lý?

Throughput cao không tự chứng minh Product Goal tiến triển. Một Sprint chỉ hoàn tất ít PBI nhưng xử lý một vấn đề an toàn trọng yếu có thể tạo giá trị lớn hơn Sprint đóng nhiều nhiệm vụ nhỏ.

### 15.5. Sprint Retrospective: thử nghiệm cải thiện luồng

Ví dụ một Retrospective phát hiện:

- WIP nhiều nhất tập trung ở Review.
- Các item già hơn SLE đều chờ một reviewer.
- Việc chia PBI đang quá lớn.
- CI đôi lúc mất hàng giờ chạy lại vì flaky tests.

Nhóm chọn một thử nghiệm như **pair review sớm và tách PR nhỏ**, rồi xem tác động lên **age, cycle time, throughput và lỗi hồi quy** qua vài Sprint. Không nên kết luận hiệu quả chỉ vì một tuần có nhiều ticket Done.

## 16. Trong Kanban: ba chỉ số gắn với một hệ thống rõ ràng

### 16.1. Bốn flow metrics trong Kanban Guide

*The Kanban Guide* mô tả một tập **flow metrics tối thiểu**:

1. **WIP:** số work item đã bắt đầu nhưng chưa hoàn tất.
2. **Throughput:** số work item hoàn tất trong đơn vị thời gian.
3. **Work Item Age:** thời gian đã trôi qua của item đang WIP.
4. **Cycle Time:** thời gian item đã hoàn tất mất từ Start đến Finish.

Bài này tập trung vào **ba chỉ số theo tiêu đề** và dùng **work item age** để bù góc nhìn về việc chưa Done.

### 16.2. Definition of Workflow (DoW) giúp phép đo nhất quán

Trong Kanban, một **Definition of Workflow** cần làm rõ những điểm như:

- Những work item nào thuộc luồng?
- Khi nào được coi là **Started**?
- Khi nào được coi là **Finished**?
- Các trạng thái và cách chúng liên hệ nhau.
- Cách kiểm soát WIP.
- Chính sách công việc đi qua luồng.
- SLE của hệ thống, khi có dữ liệu/giả định phù hợp.

Khi ranh giới Start/Finish không rõ, mọi biểu đồ về cycle time, age và throughput đều có thể bị diễn giải sai.

### 16.3. Flow không phải “luôn luôn trơn tru”

Một hệ thống thực sẽ có công việc khẩn, phụ thuộc ngoài, nghỉ lễ và những item phức tạp. Kanban không yêu cầu dòng phải **không bao giờ bị gián đoạn**; nó khuyến khích làm **trạng thái và chính sách minh bạch**, quan sát tác động và cải tiến bằng dữ liệu.

### 16.4. Kết hợp Kanban với Scrum

Một Scrum Team có thể dùng bảng Kanban và flow metrics **trong Sprint** mà không loại bỏ Sprint Goal, Sprint Review hoặc Definition of Done. Tương tự, nhóm Kanban không dùng Sprint vẫn có thể đặt các lịch review sản phẩm và cải tiến phù hợp.

Không nên biến câu hỏi “Scrum hay Kanban?” thành lựa chọn máy móc. **Hãy xác định vấn đề phối hợp đang cần giải quyết**.

## 17. XP và thực hành kỹ thuật tác động tới các chỉ số flow

### 17.1. Test tự động và CI có thể giảm thời gian chờ

Các thực hành XP như TDD/test-first, Continuous Integration, refactoring và pair programming giúp:

- Phát hiện lỗi sát lúc viết mã.
- Hạn chế nhánh kéo dài và xung đột tích hợp.
- Giữ mã dễ sửa để không phải chờ một chuyên gia duy nhất.
- Làm PR nhỏ hơn, review dễ hơn.
- Tăng khả năng đạt Definition of Done ngay trong vòng phát triển.

Tác động có thể là **cycle time giảm và throughput ổn định hơn**, nhưng chỉ khi các thực hành được triển khai phù hợp và các điểm nghẽn thật được xử lý.

### 17.2. Một CI nhanh nhưng thiếu kiểm chứng không phải cải tiến

Nếu nhóm tắt API integration tests để pipeline từ 30 phút còn 5 phút, nhưng sau đó lỗi quyền truy cập lọt production, **thời gian phản hồi nhanh hơn không đồng nghĩa dòng giá trị tốt hơn**.

Khi đánh giá, cần nhìn:

- Những kiểm tra bắt buộc còn chạy không?
- Flaky tests đã được giải quyết thật không?
- Lỗi hồi quy hoặc sự cố có tăng không?
- Increment vẫn đáp ứng DoD không?
- Người dùng có được bảo vệ không?

### 17.3. Collective code ownership giảm phụ thuộc người

Nếu mọi PBI phải chờ đúng tác giả của module, WIP có thể tăng vì những hạng mục mở chờ chuyên gia. Pairing, hướng dẫn chung và coding standards có thể giúp thêm người có khả năng sửa/an toàn review phần mã quan trọng.

Không nghĩa “ai cũng được sửa mọi phần tùy ý”; với module bảo mật, thanh toán hoặc dữ liệu nhạy cảm vẫn cần **review và quyền truy cập phù hợp**.

### 17.4. Technical debt có thể biểu hiện qua flow

Một khu vực mã lặp lại quy tắc nghiệp vụ, thiếu test, coupling cao hoặc migration khó có thể làm những PBI chạm vào nó **mất nhiều ngày hơn**. Cycle time và blocked time có thể là tín hiệu, nhưng **không tự chứng minh nguyên nhân là nợ kỹ thuật**. Cần xem hotspot, test, lịch sử sự cố và bối cảnh từng item.

## 18. Tình huống xuyên suốt: cải thiện luồng “Tiếp tục bài học”

### 18.1. Bối cảnh giả định

Một nhóm phát triển nền tảng học trực tuyến muốn giảm thời gian học viên tìm lại bài đang dở. Product Owner đã ưu tiên một lát cắt đầu, bao gồm:

- Hiển thị nút Tiếp tục.
- Lấy đúng tiến độ theo tài khoản.
- Kiểm tra quyền truy cập khóa.
- Xử lý khi đã hoàn tất toàn bộ khóa.
- Kiểm chứng hành vi trên thiết bị mục tiêu.

Nhóm Scrum có Sprint hai tuần. Trong ba Sprint gần đây, một số PBI mất lâu hơn dự kiến vì **chờ review và môi trường kiểm thử**. Mỗi Developer thường mở thêm việc mới khi việc hiện tại chưa được review.

Đây là **tình huống minh họa**, không phải thống kê thực.

### 18.2. Bước đầu: thống nhất ranh giới đo

Đội đồng thuận:

> **Start:** khi PBI được kéo vào `In Progress`.
> **Finish:** khi Increment tương ứng đạt Definition of Done và ticket được đánh dấu `Done`.

Họ theo dõi:

- WIP tổng từ In Progress tới Done.
- WIP theo từng trạng thái.
- Work item age của item đang mở.
- Cycle time theo ngày lịch cho item Done.
- Throughput theo tuần.
- Lỗi hồi quy, sự cố phân quyền và số PBI chưa đạt DoD.

### 18.3. Quan sát ban đầu

Một tuần minh họa:

| Tín hiệu | Quan sát |
| --- | --- |
| WIP cao nhất trong tuần | 11 item |
| WIP tại Review cuối tuần | 5 item |
| Throughput tuần | 4 item Done |
| Cycle time trung vị của các item Done trong kỳ | 9 ngày lịch |
| Một item đang mở | Age 16 ngày |
| Lỗi phân quyền mới phát hiện | 1 lỗi cần xử lý |
| Phản hồi người dùng | Một số học viên vẫn mở nhầm bài |

Không thể kết luận “Review là nguyên nhân duy nhất” chỉ từ bảng, nhưng **năm item ở Review** và item age **16 ngày** là điểm điều tra hợp lý.

### 18.4. Đội tìm cơ chế gây chờ

Qua xem từng PBI:

- Nhiều PR chứa cả đổi giao diện, sửa API và format toàn bộ file.
- Một người duy nhất review module phân quyền.
- CI có test dùng thời gian thực nên đôi lúc flaky.
- Developers chỉ bàn về acceptance criteria với PO sau khi viết mã.
- Hạng mục “đồng bộ đa thiết bị” quá lớn so với lát cắt cần thiết ngay.

Các nguyên nhân này tạo **hàng chờ, làm lại và rủi ro chất lượng**, chứ không chỉ phản ánh “năng suất người viết mã thấp”.

### 18.5. Thử nghiệm một Sprint

Đội chọn ba thay đổi có phạm vi rõ:

1. **Giới hạn WIP toàn luồng:** thử mức giới hạn tương ứng năng lực hiện có, ngoại lệ cho sự cố khẩn được công bố.
2. **Ưu tiên hoàn tất PBI đã mở:** Developers phối hợp review, viết integration test và gỡ blocker trước khi kéo thêm.
3. **Chia PR và PBI nhỏ hơn:** mỗi lát cắt mang hành vi sử dụng được, CI/DoD vẫn đầy đủ; người hiểu phân quyền pairing để chuyển giao tri thức.

Không được giảm tiêu chuẩn kiểm tra quyền truy cập để cải thiện số cycle time.

### 18.6. Các tín hiệu sau thử nghiệm

Giả sử qua ba Sprint tiếp theo, dữ liệu minh họa:

| Tín hiệu | Trước | Sau thử nghiệm |
| --- | ---: | ---: |
| WIP cao nhất (item) | 11 | 7 |
| Throughput trung bình mỗi tuần | 4 | 5 |
| Cycle time trung vị (ngày lịch) | 9 | 6 |
| Item có age vượt SLE | 4 | 2 |
| Lỗi hồi quy ghi nhận trong kỳ | 1 | 1 |

Nhìn sơ bộ, có tín hiệu **dòng công việc ổn định hơn**, nhưng không thể quy toàn bộ cải thiện cho WIP limit, vì đồng thời có pairing, PR nhỏ, thay đổi loại PBI và kết quả còn ít kỳ.

Đội cần hỏi:

- Cách đếm item và ranh giới Done có giữ nguyên không?
- Các PBI trước và sau có cùng loại/kích thước tương đối không?
- Có thời gian nghỉ, incident hoặc thay đổi nhân sự không?
- Lỗi phân quyền có thực sự được xử lý, không chỉ tạm không xảy ra?
- Người học có tiếp tục đúng bài nhanh hơn không?

### 18.7. Không đánh đổi giá trị lấy biểu đồ đẹp

Nếu Developer đề xuất đổi các PBI khó sang “Blocked ngoài WIP” để dashboard giảm từ 11 xuống 6, nhóm phải hỏi có thật sự **hủy hoặc rút cam kết xử lý** không. Nếu item vẫn đang được xử lý, việc ẩn nó làm mất thông tin quan trọng.

Tương tự, nếu chia một user story thành năm ticket riêng mà không có hành vi sử dụng được, throughput cao hơn chưa chứng minh giá trị. **Chỉ số tốt là công cụ để phát hiện vấn đề và thử cải tiến, không phải mục tiêu để thao túng dữ liệu.**

### 18.8. Kết nối flow với Product Goal

Dù cycle time giảm, Product Owner vẫn cần kiểm chứng:

- Học viên có tìm đúng bài nhanh hơn không?
- Người học đổi tài khoản có còn thấy dữ liệu của người khác không?
- Khi mất quyền truy cập, hệ thống có từ chối đúng không?
- Người dùng có tin vào trạng thái tiến độ của mình không?
- Những PBI tiếp theo có còn ưu tiên đúng nhu cầu học không?

**Dòng công việc hiệu quả là điều kiện hỗ trợ giá trị; nó không thay thế việc xác định và kiểm chứng giá trị.**

## 19. Thiết kế dữ liệu sự kiện cho dashboard đáng tin

### 19.1. Nên lưu những mốc nào?

Tùy công cụ quản lý công việc, tối thiểu cần có:

| Trường dữ liệu | Mục đích |
| --- | --- |
| `item_id` | Nhận diện duy nhất item, tránh đếm trùng |
| `work_item_type` | Phân tích theo loại công việc khi cần |
| `started_at` | Mốc vào hệ thống theo Definition of Workflow |
| `finished_at` | Mốc hoàn tất theo tiêu chuẩn Done |
| `state_changes` | Lịch sử chuyển trạng thái để xem waiting/blocked time |
| `cancelled_at` hoặc lý do rút bỏ | Phân biệt việc bị hủy với Done |
| `team/service` | Xác định phạm vi đo nhất quán |
| `policy_version` hoặc ghi chú thay đổi | Biết khi nào định nghĩa workflow/DoD đổi |

Nên có thêm cách xem rủi ro, nhãn phụ thuộc và dữ liệu về chất lượng ở mức phù hợp, nhưng **không thu thập dữ liệu cá nhân không cần thiết**. Các chỉ số flow cần phục vụ cải tiến hệ thống, không giám sát từng phút hoạt động của cá nhân.

### 19.2. Ví dụ giả mã tính các chỉ số

```text
cycleTime(item):
    require item.finishedAt exists
    return item.finishedAt - item.startedAt

wip(atTime):
    return count(items where
      item.startedAt <= atTime
      and (item.finishedAt is null
           or item.finishedAt > atTime)
      and item is inside defined workflow)

throughput(fromInclusive, toExclusive):
    return count(items where
      item.finishedAt >= fromInclusive
      and item.finishedAt < toExclusive
      and item meets Done policy)

workItemAge(item, atTime):
    require item.startedAt <= atTime
    require item not finished at atTime
    return atTime - item.startedAt
```

Đây là **giả mã khái niệm**, không phải triển khai production. Việc hủy, mở lại, chuyển team và đổi trạng thái phải có quy tắc riêng trước khi cho kết quả đáng tin.

### 19.3. Ví dụ SQL cho throughput theo ngày

Giả sử bảng `work_items` có `finished_at` ở dạng timestamp, dùng thời gian UTC và chỉ lưu hạng mục đạt Done:

```sql
SELECT
    CAST(finished_at AS DATE) AS finish_date,
    COUNT(*) AS finished_items
FROM work_items
WHERE finished_at >= :from_inclusive
  AND finished_at < :to_exclusive
  AND status = 'DONE'
GROUP BY CAST(finished_at AS DATE)
ORDER BY finish_date;
```

Đoạn này là **ví dụ cú pháp mang tính minh họa**; parameter binding, cú pháp ép kiểu, múi giờ, cách lưu lịch sử và tình huống item Done rồi được mở lại còn tùy DBMS và mô hình dữ liệu. Truy vấn trạng thái cuối có thể **bỏ sót item đã Done rồi reopened** nếu không lưu event history. Vì vậy, nếu muốn đo chính xác các lần hoàn tất trong kỳ, có thể cần một bảng sự kiện chuyển trạng thái được định nghĩa rõ.

### 19.4. Vấn đề dữ liệu thường gặp

- Item chuyển qua Done nhiều lần làm **đếm trùng**.
- Item Done rồi reopen, nhưng hệ thống **mất dấu lần hoàn tất ban đầu**.
- Đổi tên trạng thái giữa các Sprint làm ranh giới thay đổi.
- Item bị kéo về Backlog để ẩn WIP.
- Các team dùng cùng cột `Done` nhưng tiêu chuẩn chất lượng khác nhau.
- Công việc bắt đầu trước khi tạo ticket, làm cycle time thấp giả.
- Ngày giờ dùng múi giờ khác nhau.
- Item được clone hoặc split nhưng lịch sử không liên kết.
- Dữ liệu bị sửa sau kỳ báo cáo mà không có lịch sử thay đổi.

**Một dashboard đẹp với dữ liệu ranh giới sai có thể gây hại hơn chưa có dashboard.**

## 20. Xây dashboard tối giản nhưng đủ giúp quyết định

### 20.1. Cấu trúc đề xuất

Một dashboard đội có thể gồm:

1. **WIP hiện tại** và WIP theo trạng thái.
2. **Danh sách item đang già nhất**, age và blocker.
3. **Phân phối cycle time** theo các item Done gần đây, có trung vị, phân vị và SLE.
4. **Throughput theo tuần** trong một khoảng thời gian phù hợp.
5. **CFD hoặc quan sát hàng chờ** nếu đội muốn phân tích điểm nghẽn.
6. **Chỉ số chất lượng** như lỗi hồi quy, CI không ổn định và điều kiện DoD.
7. **Bối cảnh sản phẩm** như outcome, loại hạng mục, thay đổi chính sách và sự cố.

Không cần hiển thị 20 KPI trên một màn hình chỉ vì công cụ hỗ trợ. Mỗi chỉ số nên có **một câu hỏi ra quyết định cụ thể**.

### 20.2. Bảng minh họa đọc nhanh

| Câu hỏi của nhóm | Xem ở đâu | Hành động có thể xuất hiện |
| --- | --- | --- |
| “Hiện có gì đang mở quá lâu?” | Work item age và blocked notes | Gỡ blocker, hỗ trợ hoàn tất, trao đổi rủi ro |
| “Đội có mở nhiều hơn hoàn tất?” | WIP và đường Started/Done trên CFD | Giới hạn kéo việc mới, xử lý điểm nghẽn |
| “Thời gian hoàn tất có ổn định không?” | Phân phối cycle time, SLE | Phân tích item đuôi dài, kiểm tra chính sách |
| “Khả năng hoàn tất mỗi tuần biến động thế nào?” | Throughput theo tuần | Dự báo có điều kiện, điều chỉnh phạm vi |
| “Tốc độ cải thiện có làm chất lượng kém đi?” | DoD, lỗi hồi quy, kiểm chứng API | Dừng tối ưu sai, tăng rào chắn phù hợp |
| “Người dùng nhận giá trị nhanh hơn chưa?” | Outcome và thời gian release/feedback | Điều chỉnh sản phẩm, backlog và nhịp phát hành |

### 20.3. Đặt mốc baseline và mốc xem lại

Khi thay đổi WIP limit, đội nên ghi:

- **Trước thử nghiệm:** các chỉ số được tính thế nào và trong bao lâu?
- **Giả thuyết:** cơ chế nào sẽ giảm chờ?
- **Thử nghiệm:** chính sách nào thay đổi, trong phạm vi nào?
- **Guardrails:** điều kiện nào không được đánh đổi?
- **Mốc xem lại:** sau bao nhiêu Sprint/tuần, khi có đủ dữ liệu nào?
- **Quyết định:** giữ, điều chỉnh, mở rộng hay dừng thử nghiệm?

Không nên thay định nghĩa “Done” giữa hai kỳ rồi nói cycle time đã cải thiện 30%.

## 21. Các sai lầm thường gặp khi đo cycle time, WIP và throughput

| Anti-pattern | Vì sao nguy hiểm | Cách làm đúng hơn |
| --- | --- | --- |
| “Cycle time chỉ tính thời gian Developer đang gõ mã.” | Bỏ thời gian chờ trong luồng người dùng phải chịu. | Chọn Start/Finish rõ, gồm thời gian ở Review/Verification. |
| “Ticket vào Backlog là đã Start.” | Dễ trộn chờ ưu tiên với thời gian thực hiện. | Phân biệt lead time và cycle time bằng mốc khác nhau. |
| “Mỗi item cùng kích thước nên đếm là đủ.” | PBI khác loại và độ phức tạp. | Phân loại, xem phân phối và chính sách chia lát cắt. |
| “WIP chỉ tính việc có ai đang gõ mã.” | Loại bỏ blocker khỏi bức tranh. | Tính việc đã Start chưa Done, gồm blocked. |
| “Muốn WIP đẹp, đưa việc chờ về Backlog.” | Che thời gian chờ và trách nhiệm. | Công khai blocked state và xử lý rút bỏ thật nếu có. |
| “Cứ hạ WIP xuống 1 là nhanh nhất.” | Có thể làm người rảnh và throughput giảm trong một số hệ thống. | Chọn giới hạn theo năng lực, phụ thuộc và thực nghiệm. |
| “WIP limit là chỉ tiêu kỷ luật cá nhân.” | Khuyến khích giấu công việc, đổ lỗi. | Dùng như chính sách dòng công việc của cả nhóm. |
| “Throughput tăng nghĩa là giá trị tăng.” | Đếm ticket không đo outcome. | Kết hợp Product Goal, DoD và phản hồi người dùng. |
| “Tách một PBI thành 10 việc nhỏ để đạt KPI.” | Số item thay đổi nhưng giá trị có thể không đổi. | Giữ đơn vị đo và lát cắt giá trị nhất quán. |
| “Cycle time trung bình thấp nghĩa là không có việc kẹt.” | Trung bình Done bỏ qua công việc chưa hoàn tất. | Xem age của WIP và phân phối các item Done. |
| “85% trong 10 ngày nghĩa là mọi việc sẽ xong trong 10 ngày.” | SLE là kỳ vọng xác suất, không bảo đảm tuyệt đối. | Trao đổi rủi ro và dự báo có điều kiện. |
| “Little’s Law là công thức cam kết deadline cho mọi PBI.” | Quan hệ trung bình không dự báo từng trường hợp. | Kiểm tra ổn định, ranh giới và độ biến động. |
| “Có thể so cycle time của hai đội theo bảng xếp hạng.” | Workflow, loại việc, DoD và rủi ro có thể khác. | Dùng dữ liệu để cải tiến nội bộ, tránh so sánh đơn giản. |
| “Khi throughput thấp, mở thêm thật nhiều việc.” | Có thể tăng WIP và cycle time. | Xem nút nghẽn, hoàn tất việc cũ, giới hạn WIP. |
| “Bỏ test bảo mật để tăng số item Done.” | Làm hại người dùng và đánh tráo Done. | Tuân thủ DoD và kiểm chứng rủi ro bắt buộc. |
| “Một Sprint có nhiều điểm story hơn là năng suất cao hơn.” | Story points là quy ước tương đối, có thể thay đổi. | Quan sát flow, chất lượng và giá trị thay vì chỉ điểm. |
| “Forecast 7 item/tuần nghĩa là đúng 21 item sau 3 tuần.” | Throughput biến động và backlog thay đổi. | Dùng khoảng và giả định, cập nhật theo dữ liệu mới. |
| “Tất cả vấn đề đều do Developers chậm.” | Có thể nghẽn ở review, môi trường, quy trình quyết định. | Tìm nguyên nhân ở toàn hệ thống. |
| “Dashboard phải càng nhiều số càng tốt.” | Gây nhiễu và tối ưu sai câu hỏi. | Chọn tín hiệu hỗ trợ quyết định cụ thể. |
| “Flow metrics chứng minh người dùng hài lòng.” | Thước đo dòng không đo giá trị trực tiếp. | Kết hợp outcome và phản hồi người dùng. |

## 22. Checklist áp dụng trong nhóm Agile

### 22.1. Trước khi bắt đầu đo

- [ ] Đã xác định **work item** được đếm là gì.
- [ ] Có ranh giới **Start và Finish** rõ và nhất quán.
- [ ] Biết Finish có tương đương **Definition of Done** của sản phẩm không.
- [ ] Đã quyết định dùng giờ/ngày lịch/ngày làm việc và múi giờ.
- [ ] Có cách xử lý **blocked, cancelled, reopened, split** và item chuyển team.
- [ ] Biết ai sẽ dùng dữ liệu, để ra quyết định gì.
- [ ] Không đặt KPI xếp hạng cá nhân bằng số ticket.
- [ ] Có kế hoạch bảo vệ dữ liệu và tránh thu thập thông tin không cần thiết.

### 22.2. Khi tính và đọc số liệu

- [ ] Cycle time được lấy từ các item Done có Start/Finish hợp lệ.
- [ ] WIP tính cả việc đã bắt đầu nhưng bị chặn.
- [ ] Throughput đếm các item vượt Finish trong kỳ nhất quán.
- [ ] Xem **phân phối/trung vị và các item đuôi dài**, không chỉ trung bình.
- [ ] Xem **work item age** của các item chưa Done.
- [ ] Nếu dùng SLE, biết dữ liệu và phương pháp percentile.
- [ ] Khi so trước–sau, xem có thay đổi cách chia việc, DoD hoặc thành phần team không.
- [ ] Khi dùng Little’s Law, kiểm tra ranh giới và tính ổn định.
- [ ] Không suy ra quan hệ nhân quả chỉ từ biểu đồ.
- [ ] Kết hợp tín hiệu chất lượng và giá trị sản phẩm.

### 22.3. Khi dùng chỉ số để cải tiến

- [ ] Đã xác định **điểm nghẽn cụ thể** có bằng chứng.
- [ ] Chọn một thử nghiệm nhỏ như giảm WIP, pairing review hoặc cải thiện CI.
- [ ] Có người theo dõi và mốc xem lại.
- [ ] Không hạ tiêu chuẩn DoD để làm đẹp cycle time/throughput.
- [ ] Khi có sự cố, chính sách ưu tiên được công bố minh bạch.
- [ ] Số liệu giúp trao đổi và học hỏi, không dùng để đổ lỗi.
- [ ] Sau thử nghiệm, có quyết định giữ, sửa hoặc dừng dựa trên bằng chứng.

## 23. Bài tập thực hành

### Bài tập 1 — Tính ba chỉ số từ dữ liệu

Dùng bảng 10 item ở mục 8:

1. Tính cycle time của D, F, I và J.
2. Tính trung bình và trung vị cycle time.
3. Tính WIP tại **đầu D12** và liệt kê item đang mở.
4. Tính throughput trong ba kỳ D1–D7, D8–D14 và D15–D21.
5. Giải thích vì sao J không thuộc WIP ở D12 dù sau đó đã hoàn tất trong tập dữ liệu.

### Bài tập 2 — Phân biệt cycle time và lead time

Một PBI được ghi vào backlog đầu D1, chuyển In Progress đầu D9 và đạt Done đầu D15. Hãy tính:

- Lead time từ khi ghi yêu cầu.
- Cycle time từ khi thực sự bắt đầu.
- Thời gian chờ trước khi bắt đầu.
- Vì sao người dùng có thể thấy thời gian chờ khác số cycle time dashboard?

### Bài tập 3 — Phân phối và SLE

Một nhóm có cycle time của 10 item đã hoàn tất: **2, 4, 4, 4, 4, 4, 5, 5, 5, 6** ngày.

1. Tính trung bình, trung vị và giá trị cao nhất.
2. Tính phân vị 85 theo **nearest-rank**.
3. Có bao nhiêu item trong mẫu hoàn tất ≤ 5 ngày?
4. Vì sao không thể tuyên bố “mọi item chắc chắn hoàn tất trong năm ngày”?
5. Cần thêm dữ liệu gì trước khi công bố SLE cho bên ngoài?

### Bài tập 4 — WIP limit và việc bị chặn

Bảng có `In Progress` WIP limit = 3. Hiện cột có hai item đang code và một item blocked chờ môi trường. Một Developer rảnh muốn kéo PBI mới vào.

Hãy giải thích:

- WIP thực tại cột bằng bao nhiêu?
- Vì sao blocked vẫn được tính?
- Những hành động nào giúp nhóm hoàn tất việc cũ?
- Khi nào có thể áp dụng ngoại lệ và cần công bố điều gì?
- Vì sao không nên đưa item blocked về Backlog chỉ để giữ WIP đẹp?

### Bài tập 5 — Little’s Law và điều kiện áp dụng

Một hệ thống ổn định có WIP bình quân 12 item và throughput bình quân 4 item/tuần.

1. Tính cycle time bình quân theo Little’s Law.
2. Nếu WIP bình quân giảm còn 8 item mà throughput không đổi, cycle time bình quân tương ứng là bao nhiêu?
3. Nêu năm điều kiện hoặc rủi ro khi dùng mối liên hệ này.
4. Vì sao không được nói mọi item mới chắc chắn Done sau số tuần vừa tính?

### Bài tập 6 — Forecast theo throughput

Dãy throughput tám tuần: **6, 8, 7, 9, 5, 8, 7, 6** item.

1. Tính tổng, trung bình, min và max.
2. Nếu còn 21 item tương tự, ước tính tuyến tính thô bao nhiêu tuần?
3. Đưa ra cách diễn đạt dự báo có điều kiện, không dùng một deadline chắc chắn.
4. Nêu các trường hợp làm lịch sử không còn đại diện.
5. Giải thích khi nào mô phỏng Monte Carlo có ích và giới hạn của nó.

### Bài tập 7 — Phát hiện tắc nghẽn qua CFD

Một CFD cho thấy dải Review dày lên liên tục, đường Done gần như phẳng, còn đường Started tiếp tục tăng. Hãy:

- Nêu ba giả thuyết cần kiểm tra.
- Đề xuất hai thử nghiệm cải tiến không hạ chất lượng.
- Xác định số liệu cần theo dõi sau thử nghiệm.
- Giải thích vì sao hình CFD chưa đủ để kết luận nguyên nhân.

### Bài tập 8 — Scrum và flow metrics

Trong Sprint hai tuần, đội có sáu PBI đang mở vào ngày cuối; hai PBI đã viết mã xong nhưng chưa đạt DoD. Product Owner muốn đánh dấu Done để tăng throughput.

Hãy trả lời:

- Những PBI nào được tính vào throughput theo Finish đã thống nhất?
- Vì sao “code complete” chưa phải Increment Done?
- Developers nên làm gì để tránh dồn verification cuối Sprint?
- Daily Scrum và Retrospective có thể dùng WIP/age thế nào?
- Sprint Goal và Product Goal nên được thảo luận ra sao?

### Bài tập 9 — Phát hiện KPI sai

Một nhóm sau khi áp đặt “mỗi người phải Done 10 ticket/tuần” đã tăng throughput 60%. Tuy nhiên, số lỗi hồi quy và thời gian support cũng tăng.

Hãy phân tích:

- Cách đếm nào có thể đã thay đổi?
- Dữ liệu gì cần kiểm tra trước khi kết luận?
- Vì sao KPI này tạo động cơ thao túng?
- Đề xuất một bộ tín hiệu cân bằng flow, chất lượng và outcome.
- Viết một nguyên tắc dùng metric để học thay vì trừng phạt.

### Bài tập 10 — Thiết kế dashboard

Thiết kế dashboard cho nhóm làm nền tảng học trực tuyến gồm:

- WIP toàn luồng và theo trạng thái.
- Aging WIP.
- Cycle time trung vị/phân phối và SLE.
- Throughput theo tuần.
- Chỉ số chất lượng bắt buộc.
- Một outcome người học.

Với mỗi chỉ số, ghi **câu hỏi cần trả lời, nguồn dữ liệu, ranh giới đo, tần suất xem và quyết định có thể đưa ra**.

### Bài tập 11 — Thử nghiệm cải tiến trong hai Sprint

Một đội có WIP = 14, throughput 5 item/tuần, một số item age hơn 20 ngày. Hãy đề xuất một thử nghiệm nhỏ về WIP limit hoặc review pairing:

1. Viết giả thuyết cải tiến.
2. Chọn cách đo baseline.
3. Nêu chính sách xử lý item blocked và ngoại lệ khẩn.
4. Ghi rào chắn DoD và lỗi hồi quy.
5. Xác định khi nào và dựa trên điều gì nên giữ, điều chỉnh hoặc dừng thử nghiệm.

### Bài tập 12 — So sánh hai nhóm có workflow khác nhau

Nhóm A đếm ticket kỹ thuật nhỏ từ lúc Developer nhận việc đến lúc merge. Nhóm B đếm PBI đầu-cuối từ In Progress đến khi đạt DoD. Nhóm A báo cycle time 2 ngày, nhóm B báo 8 ngày.

Hãy giải thích **vì sao không được xếp hạng năng suất hai nhóm trực tiếp** từ hai con số này. Đề xuất cách làm rõ đơn vị, chính sách, loại việc và mục tiêu sử dụng số liệu.

## 24. Hướng dẫn tự kiểm đáp án chọn lọc

Phần này giúp người học đối chiếu phép tính, **không thay thế giải thích bối cảnh và giới hạn của số liệu**.

### 24.1. Bài tập 1

- D: D3 → D8 = **5 ngày**.
- F: D6 → D11 = **5 ngày**.
- I: D11 → D17 = **6 ngày**.
- J: D13 → D18 = **5 ngày**.
- Trung bình: **4,3 ngày**; trung vị: **4 ngày**.
- WIP đầu D12: **H và I**, tức **2 item**.
- Throughput ba kỳ: **3, 5, 2 item**.
- J chưa Start tại D12 nên không thuộc WIP thời điểm ấy.

### 24.2. Bài tập 2

- Lead time: D1 → D15 = **14 ngày**.
- Cycle time: D9 → D15 = **6 ngày**.
- Thời gian chờ trước khi Start: D1 → D9 = **8 ngày**.

Kết quả phụ thuộc quy ước dùng **mốc đầu ngày** như đề bài, không cộng cả hai ngày biên.

### 24.3. Bài tập 3

- Tổng thời gian: 43 ngày-item; trung bình **4,3 ngày**.
- Trung vị **4 ngày**, max **6 ngày**.
- Nearest-rank P85: vị trí `ceil(8,5) = 9`, giá trị **5 ngày**.
- **9/10 item** hoàn tất trong ≤ 5 ngày.
- Mẫu nhỏ, có thể chưa đại diện; ngưỡng không bảo đảm cho mọi trường hợp.

### 24.4. Bài tập 5

- WIP = 12, throughput = 4 item/tuần → cycle time bình quân tương ứng **3 tuần**.
- WIP = 8, throughput vẫn 4 item/tuần → tương ứng **2 tuần**.
- Đây là quan hệ trung bình của hệ thống dưới điều kiện phù hợp, không bảo đảm cho từng PBI.

### 24.5. Bài tập 6

- Tổng: **56 item**, trung bình **7 item/tuần**.
- Min: **5**, max: **9** item/tuần.
- 21/7 = **3 tuần** theo ước tính tuyến tính thô.
- Dự báo chỉ đáng trao đổi nếu cách chia item, năng lực và điều kiện luồng còn tương tự; cần xét biến động và rủi ro khác.

## 25. Tóm tắt kiến thức cốt lõi

**Cycle time** đo thời gian một hạng mục đi từ Start tới Finish theo ranh giới đã công bố. **WIP** cho biết bao nhiêu hạng mục đã bắt đầu nhưng chưa hoàn tất ở một thời điểm. **Throughput** đếm số hạng mục hoàn tất trong một kỳ. Cả ba đều cần **định nghĩa work item, mốc thời gian, đơn vị và chính sách Done nhất quán**.

Ba chỉ số cho phép nhìn hệ thống từ những góc khác nhau: cycle time phản ánh thời gian hoàn tất, WIP phản ánh mức công việc dở dang, throughput phản ánh khả năng hoàn tất theo kỳ. **Work item age** bổ sung góc nhìn của những việc chưa Done; **phân phối cycle time và SLE** giúp thảo luận kỳ vọng có bất định; **Little’s Law** liên hệ các giá trị trung bình trong hệ thống ổn định, không dự báo chắc chắn cho từng PBI.

Khi sử dụng trong Scrum hoặc Kanban, hãy dùng flow metrics để **làm lộ điểm nghẽn, giới hạn WIP, ưu tiên hoàn tất việc cũ, kiểm tra khả năng giao Increment và cải tiến cách phối hợp**. Các thực hành XP như kiểm thử, CI và refactoring giúp giảm chờ kỹ thuật nhưng không tự giải quyết vấn đề sản phẩm sai hướng.

**Đo lường Agile không phải thi đua ai đóng nhiều ticket nhất.** Những quyết định tốt nhất kết hợp **flow metrics, Definition of Done, chất lượng, khả năng phát hành và outcome người dùng**, sử dụng số liệu như tín hiệu để học hỏi, dự báo có điều kiện và cải tiến liên tục.

## Tài liệu tham khảo

1. [The Kanban Guide](https://kanbanguides.org/english/) — định nghĩa Work in Progress, throughput, work item age, cycle time, Definition of Workflow và Service Level Expectation.
2. [Kanban University — The Official Guide to the Kanban Method](https://kanban.university/kanban-guide/) — thực hành quản lý luồng công việc, WIP, chính sách rõ và cải tiến liên tục.
3. Daniel S. Vacanti, *Actionable Agile Metrics for Predictability: An Introduction* (2015) — cycle time, throughput, CFD và cách đọc dự báo dòng công việc.
4. Daniel S. Vacanti, *When Will It Be Done? Lean-Agile Forecasting to Answer Your Customers' Most Important Question* (2017) — dự báo trên throughput/cycle time và bất định.
5. John D. C. Little, “A Proof for the Queuing Formula: L = λW”, *Operations Research* 9(3), 1961 — nền tảng Little’s Law cho hệ thống dòng.
6. Donald G. Reinertsen, *The Principles of Product Development Flow: Second Generation Lean Product Development* (2009) — quản lý lô công việc, hàng chờ, độ biến động và quyết định trong dòng sản phẩm.
7. [The Scrum Guide](https://scrumguides.org/scrum-guide.html), bản tháng 11/2020 — Product Backlog, Sprint Goal, Increment, Definition of Done và nhịp kiểm tra thích ứng.
8. [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao phần mềm hữu ích sớm, thích ứng qua phản hồi và cải tiến liên tục.
9. [Agile Alliance — Kanban](https://agilealliance.org/glossary/kanban/) — tổng quan việc trực quan hóa, giới hạn công việc đang làm và quản lý luồng.
10. Kent Beck & Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004) — thực hành kiểm thử, tích hợp, refactoring và giao phần mềm nhỏ.
11. [DORA — DevOps Research and Assessment](https://dora.dev/) — các nghiên cứu về hiệu quả giao phần mềm và cách nhìn hệ thống thay vì chỉ đo hoạt động cá nhân.
