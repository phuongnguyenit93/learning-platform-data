# Phối hợp nhiều nhóm: Đánh giá chi phí phối hợp khi thêm nhóm hoặc tầng quản lý

Một nền tảng đăng ký workshop đang được phát triển bởi hai nhóm: nhóm phụ trách đăng ký và dữ liệu, nhóm phụ trách trải nghiệm học viên. Tốc độ giao tính năng chưa đáp ứng nhu cầu; lãnh đạo cân nhắc lập nhóm tích hợp thứ ba và yêu cầu mọi thay đổi đi qua thêm một cấp phê duyệt. Ý định là tăng năng lực và giảm rủi ro. Tuy nhiên, một user story “Hiển thị chính xác trạng thái đăng ký” có thể phải chờ ba backlog, hai lần bàn giao API, một môi trường kiểm thử và hai chữ ký. Tất cả mọi người đều bận, nhưng người dùng vẫn chưa nhận được Increment hoàn chỉnh.

**Thêm nhóm hoặc tầng quản lý không tự động làm nhanh hơn hay chậm hơn.** Nhóm mới có thể sở hữu một miền giá trị độc lập, giảm quá tải chuyên môn hoặc tạo nền tảng dùng chung. Quản lý mới có thể giải quyết xung đột chiến lược, phát triển năng lực, phân quyền và kiểm soát rủi ro. Song mỗi ranh giới tổ chức mới cũng **có khả năng** tạo thêm giao tiếp, chờ quyết định, bàn giao, tích hợp và làm lại. Muốn đánh giá công bằng, phải so **lợi ích tăng thêm ở cấp sản phẩm** với **chi phí phối hợp ở cấp hệ thống**, không chỉ đếm người hay số cuộc họp.

Bài học này tập trung trực tiếp vào **đánh giá chi phí phối hợp khi thêm nhóm hoặc tầng quản lý** thuộc chương **Phối hợp nhiều nhóm**. Đây là phần của mô-đun **AGILE_DEVELOPMENT**: hiểu giá trị và nguyên tắc Agile để giao phần mềm sớm, liên tục, thích ứng nhờ phản hồi; thực hành user story, backlog, Scrum, Kanban, XP và số đo dòng công việc để phối hợp phù hợp. Các số liệu, tên nhóm và kết quả thử nghiệm bên dưới **đều là ví dụ giả định**, không phải bằng chứng thực tế của một doanh nghiệp hay quy luật dự báo chính xác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **năng lực thực thi**, **chi phí giao tiếp**, **chi phí bàn giao**, **thời gian chờ**, **chi phí tích hợp/làm lại** và **chi phí quản trị**.
2. Dùng số cặp kết nối tiềm năng **n(n − 1)/2** đúng giới hạn, không nhầm thành số cuộc họp hay công thức dự báo năng suất.
3. Vẽ bản đồ **phụ thuộc giữa các nhóm và các cấp quyết định**; phân loại phụ thuộc tuần tự, dùng chung tài nguyên, hai chiều và đồng bộ thời điểm.
4. Tính **đường găng (critical path)** trên một ví dụ có công việc song song và đánh giá ảnh hưởng của approval nối tiếp.
5. Phân biệt **person-hours** với **elapsed wait**, tránh cộng các đơn vị hoặc đếm chi phí hai lần.
6. Giải thích tại sao **queue, WIP, blocked time, work item age, throughput, cycle time** phản ánh chi phí phối hợp tốt hơn bảng điểm bận rộn.
7. Phân tích cả **lợi ích của quản lý** và khả năng một tầng phê duyệt mới tạo điểm nghẽn.
8. So sánh thêm team, thêm người, platform/self-service, thay ownership, tự động hóa contract tests, giảm WIP và ủy quyền.
9. Kết nối phương án tổ chức với Product Goal, Product Backlog, Definition of Done, Scrum, Kanban và XP.
10. Lập giả thuyết và một **thử nghiệm cải tiến tổ chức nhỏ**, có baseline, guardrails, giới hạn suy luận và điểm xem lại.
11. Diễn giải business case định lượng thận trọng, không coi mỗi story là một đơn vị giá trị bằng nhau.
12. Thực hành đề xuất lựa chọn tổ chức và trình bày rõ điều biết, chưa biết, đánh đổi, điều kiện đảo quyết định.

## 2. Chi phí phối hợp là gì?

### 2.1. Phối hợp là phương tiện tạo kết quả chung

Một thay đổi đăng ký workshop có thể cần người phụ trách sản phẩm, lập trình giao diện, nghiệp vụ đăng ký, cơ sở dữ liệu, kiểm thử và vận hành. Nếu họ không trao đổi, API có thể trả trạng thái PENDING trong khi giao diện hiển thị “Đã xác nhận”, hoặc hai request cùng tranh suất cuối khiến dữ liệu sai.

Do đó **không phải mọi cuộc họp, lần review hoặc tương tác giữa nhóm đều là lãng phí**. Review bảo mật có thể ngăn sự cố nghiêm trọng. Pair programming 30 phút có thể tránh nhiều ngày viết mã theo hai giả định. Mục tiêu là **giảm phối hợp không cần thiết và giảm độ trễ của những phối hợp bắt buộc**, vẫn giữ tính đúng và khả năng tạo giá trị.

### 2.2. Sáu nhóm chi phí nên tách riêng

| Loại | Hiện tượng quan sát | Cách đo phù hợp | Chú ý |
| --- | --- | --- | --- |
| **Giao tiếp trực tiếp** | Họp, workshop, trao đổi hợp đồng | Thời gian tham gia, person-hours, quyết định tạo ra | Có thể rất đáng giá |
| **Chờ phản hồi/quyết định** | Story, PR hoặc yêu cầu đứng yên | Elapsed blocked time, decision latency | Không đồng nghĩa người nhận đang không làm việc |
| **Bàn giao (handoff)** | Item qua nhiều team/backlog | Số điểm chuyển, độ trễ, lỗi thiếu bối cảnh | Nhiều handoff không nhất thiết độc lập |
| **Tích hợp/làm lại** | Sai contract, CI đỏ, sửa theo kết quả integration | Rework, integration defects, recovery time | Chất lượng và độ khó cần được xem cùng |
| **Quản trị/kiểm soát** | Phê duyệt, theo dõi rủi ro, phân bổ nguồn lực | Thời gian duyệt, tác động rủi ro ngăn được | Có phần bắt buộc về bảo mật/tuân thủ |
| **Nhận thức/chuyển ngữ cảnh** | Nhiều ownership, đổi ưu tiên, hỏi nhiều chuyên gia | WIP, phỏng vấn nhóm, phụ thuộc/key-person | Khó quy hết thành giờ hoặc tiền |

### 2.3. Phân biệt một lần tương tác có ích và một hàng chờ không cần thiết

Một cuộc họp liên team đáng giá khi:
- Giải được bất đồng quan trọng.
- Tạo ra hợp đồng và tiêu chí kiểm thử được các bên hiểu giống nhau.
- Phát hiện một rủi ro khó đảo ngược.
- Chọn quyết định hoặc một thí nghiệm có trách nhiệm.
- Kết quả được ghi để người khác không phải hỏi lại.

Một hàng chờ đáng xem xét khi:
- Mỗi story phải chờ cùng một người ký mà người đó không kiểm tra được rủi ro mới.
- Các nhóm truyền trạng thái qua nhiều cuộc họp nhưng không ai có quyền chốt.
- Một nhóm chỉ được phép chuyển công việc sang một nhóm khác dù có thể tự kiểm bằng contract test.
- Người có bối cảnh thực không được nói trực tiếp với người cần quyết.
- Một câu hỏi đơn giản bị chuyển qua nhiều tầng báo cáo.

**Chi phí phối hợp là chi phí của cách tổ chức luồng công việc**, không phải lỗi đạo đức của những cá nhân đang làm việc trong hệ thống đó.

## 3. Năng lực nhóm và tốc độ giao giá trị không tăng tuyến tính

### 3.1. Tối ưu cục bộ có thể làm hệ thống chậm

Giả sử:
- Team UI đã đóng 6 task theo Definition of Done nội bộ.
- Team API đóng 7 task, nhưng contract cho UI vẫn chưa chốt.
- Team QA có 9 item chờ môi trường tích hợp.
- Chưa có một lát cắt đăng ký hoàn chỉnh đủ điều kiện release.

Nếu chỉ xem throughput từng team, cả ba đều “năng suất”. Ở cấp sản phẩm, người dùng vẫn chưa trải nghiệm luồng đăng ký đáng tin. Cần phân biệt:

- **Hoàn tất cục bộ:** thành phần đã xong theo quy trình nội bộ.
- **Hoàn tất sản phẩm:** Increment tích hợp đáp ứng Definition of Done dùng chung.
- **Kết quả sản phẩm:** học viên nhận được giá trị và hệ thống giữ các bất biến quan trọng.

Đếm thêm người mà không thay cấu trúc phụ thuộc có thể **tăng số đầu việc bắt đầu nhanh hơn số đầu việc hoàn tất**.

### 3.2. Mô hình tư duy về năng lực

~~~text
Năng lực nhân sự và công cụ
    -> Năng lực thực hiện các phần việc
    -> Khả năng tích hợp, kiểm chứng và phát hành
    -> Increment có giá trị được bàn giao
    -> Phản hồi và kết quả người dùng
~~~

Một bottleneck ở hợp đồng, tích hợp hoặc phê duyệt có thể giới hạn dòng ra dù phần thực thi riêng lẻ có năng lực dư. Đây là **lăng kính hệ thống**, không phải công thức số học cho năng suất.

### 3.3. Chuyên môn hóa vừa có lợi vừa có chi phí

Chuyên môn hóa có thể:
- Giúp người có kỹ năng sâu giải quyết vấn đề khó.
- Giảm lặp lại công việc infrastructure.
- Tạo review độc lập cho quyết định rủi ro cao.
- Giúp quản lý năng lực và nghề nghiệp rõ hơn.

Nhưng chia một lát cắt giá trị thành các hàng chờ “frontend → backend → QA → ops” có thể:
- Buộc một story đi qua nhiều backlog.
- Gây tranh chấp ưu tiên.
- Đưa lỗi tích hợp tới cuối chu kỳ.
- Làm Product Owner khó biết khi nào Increment thật sự Done.

**Đánh giá ranh giới theo dòng giá trị, không chỉ theo sơ đồ phòng ban.**

## 4. Mô hình số cặp giao tiếp: n(n − 1)/2

### 4.1. Công thức và ý nghĩa chính xác

Nếu có **n nút** và mọi cặp nút **đều có khả năng trao đổi trực tiếp**, số cặp không thứ tự tối đa là:

~~~text
P(n) = n × (n − 1) / 2

P(4) = 4 × 3 / 2  = 6
P(7) = 7 × 6 / 2  = 21
P(8) = 8 × 7 / 2  = 28
~~~

Nếu lấy mỗi nhóm là một nút, từ **4 lên 7 nhóm** số **cặp nhóm tiềm năng** tăng từ 6 lên 21, tức thêm **15 cặp**, hay tăng **250% số cặp tiềm năng**.

**Không được kết luận số cuộc họp hoặc chi phí phối hợp tăng 250%.** Trong thực tế, không phải mọi nhóm cần làm việc với mọi nhóm; một contract rõ có thể làm tương tác giữa hai nhóm rất nhẹ; một cặp có phụ thuộc hai chiều sâu lại có thể tốn hơn nhiều cặp khác.

### 4.2. Dùng ma trận phụ thuộc thay cho đoán từ đầu người

Giả sử bốn nhóm:
- **A:** trải nghiệm học viên.
- **B:** đăng ký và sức chứa.
- **C:** thông báo.
- **D:** nền tảng và vận hành.

| Nhóm | A | B | C | D |
| --- | --- | --- | --- | --- |
| **A** | — | Cao | Trung bình | Thấp |
| **B** | Cao | — | Cao | Trung bình |
| **C** | Trung bình | Cao | — | Trung bình |
| **D** | Thấp | Trung bình | Trung bình | — |

Ma trận này **giả định** và mang tính định tính. Có thể chấm độ phụ thuộc bằng:
- Số story phải sửa đồng thời ở hai nơi.
- Số lần API contract thay đổi.
- Blocked time chờ nhóm kia.
- Số lần integration phải làm lại.
- Mức độ cùng chia sẻ dữ liệu/tài nguyên.
- Mức rủi ro khi một bên thay đổi độc lập.

Không tự biến “Cao = 3 điểm” thành ba ngày hay ba triệu đồng nếu chưa có mô hình được đo và kiểm chứng. Mục tiêu là tìm **các cạnh quan trọng cần điều tra**.

### 4.3. Một cạnh giao tiếp còn mang lợi ích

Hai nhóm trao đổi thường xuyên đôi khi là dấu hiệu **hợp tác tích cực**: cùng làm rõ vấn đề khó, bảo vệ hợp đồng hoặc chia sẻ chuyên môn. Đừng cắt mọi đường giao tiếp chỉ vì muốn sơ đồ thưa. Hãy hỏi **tương tác đó tạo ra hiểu biết hoặc kiểm soát rủi ro nào**.

## 5. Bản đồ phụ thuộc: bốn kiểu chi phối chi phí

| Kiểu | Mô tả | Ví dụ workshop | Chi phí có thể phát sinh |
| --- | --- | --- | --- |
| **Tuần tự** | B chỉ bắt đầu sau khi A giao đầu ra | UI chờ hợp đồng API | Thời gian chờ nối tiếp |
| **Dùng chung tài nguyên** | Nhiều team cần cùng người/môi trường | Hai team chờ một môi trường integration | Queue và tranh ưu tiên |
| **Hai chiều** | A và B liên tục điều chỉnh theo nhau | UI và API đổi ý nghĩa PENDING qua nhiều vòng | Rework và vòng hỏi–đáp |
| **Đồng bộ thời điểm** | Nhiều thay đổi phải đủ cùng lúc | Migration schema với các phiên bản client | Phát hành bị chặn, rủi ro tương thích |

Một thay đổi đơn giản có thể trở nên rất đắt nếu chạm cả bốn kiểu.

### 5.1. Lập sơ đồ dòng công việc

~~~mermaid
flowchart LR
    A[Product Backlog] --> B[Team UI]
    B --> C[Chờ API contract]
    C --> D[Team đăng ký]
    D --> E[Chờ tích hợp]
    E --> F[Kiểm thử]
    F --> G[Phê duyệt phát hành]
    G --> H[Increment cho học viên]
    H --> I[Phản hồi người dùng]
~~~

Đây là **một anti-pattern có thể xảy ra**, không phải mô hình bắt buộc. Nếu Team UI và Team đăng ký có thể cùng xây một vertical slice hoặc kiểm tra hợp đồng sớm, một số lần chờ sẽ biến mất.

### 5.2. Đọc bản đồ theo rủi ro, không theo số mũi tên

Các câu hỏi cần đặt:
1. Tại sao A phải chờ B?
2. Câu trả lời có thể được cung cấp sớm bằng **contract, example hoặc test** không?
3. Một yêu cầu được đặt vào hàng chờ nào và ai ưu tiên?
4. Nhóm nào có quyền đưa ra quyết định?
5. Nếu một bước chậm, có thể làm phần khác **song song** không?
6. Dữ liệu/kiến trúc có buộc hai bên thay đổi đồng thời không?
7. Có cần một kiểm soát an toàn độc lập ở ranh giới này không?
8. Những mũi tên nào chỉ xuất hiện vì cấu trúc tổ chức, không phải nhu cầu sản phẩm?

## 6. Critical path: phân biệt hoạt động song song với chờ nối tiếp

### 6.1. Một lịch giả định đủ để tính bằng tay

| Mã | Việc | Phụ thuộc | Thời gian thực hiện |
| --- | --- | --- | ---: |
| **A** | Chốt hợp đồng trạng thái | Không | 1 ngày |
| **B** | Xây API | A | 3 ngày |
| **C** | Xây UI | A | 2 ngày |
| **D** | Tích hợp và kiểm thử | B và C | 2 ngày |
| **E** | Kiểm chứng phát hành | D | 1 ngày |

Giả định mọi thời lượng là **ngày làm việc tương thích**, không có hàng chờ và công việc bắt đầu ngay khi đủ phụ thuộc.

~~~mermaid
flowchart LR
    A["A: Contract (1d)"] --> B["B: API (3d)"]
    A --> C["C: UI (2d)"]
    B --> D["D: Integration (2d)"]
    C --> D
    D --> E["E: Release validation (1d)"]
~~~

Đường găng là:

~~~text
A + max(B, C) + D + E
= 1 + max(3, 2) + 2 + 1
= 7 ngày làm việc
~~~

Không cộng **1 + 3 + 2 + 2 + 1 = 9 ngày** vì API và UI có thể thực hiện song song sau contract.

### 6.2. Một tầng duyệt mới làm gì?

Nếu sau E xuất hiện **hai phê duyệt nối tiếp**, mỗi lần chờ đúng một ngày làm việc, và không thể chồng lấn:

~~~text
Thời gian trước: 7 ngày
Đợi hai phê duyệt nối tiếp: +2 ngày
Thời gian mới: 9 ngày
Mức tăng theo mô hình: (9−7)/7 ≈ 28,6%
~~~

Đây là **kịch bản giả định**, không phải dự báo rằng thêm hai manager làm mọi dự án chậm 28,6%. Nếu một bước duyệt làm song song với E, tác động có thể nhỏ hơn. Nếu một bước duyệt ngăn một lỗi dữ liệu nghiêm trọng, phải xét **giá trị bảo vệ**.

### 6.3. Person-hours không bằng elapsed wait

Một phê duyệt có thể chỉ mất **10 phút công sức đọc** nhưng yêu cầu chờ trong inbox **một ngày làm việc**:

- **Effort:** 10 phút = 1/6 person-hour.
- **Elapsed wait:** 1 ngày trước khi item được phép tiếp tục.

Một cuộc họp có 8 người kéo dài 45 phút tiêu tốn **8 × 45/60 = 6 person-hours**, nhưng có thể giảm nhiều ngày chờ nếu giải quyết đúng vấn đề.

**Không cộng 6 person-hours với 2 ngày elapsed wait thành một số “chi phí giờ” duy nhất.** Hai loại số đo trả lời hai câu hỏi khác nhau. Cũng không mặc định một ngày chờ là tám giờ lao động bị mất: người bị chặn có thể làm việc hữu ích khác.

## 7. Queue, WIP và Little's Law: chi phí phối hợp tích lũy thế nào?

### 7.1. Khi việc đến nhanh hơn việc được giải quyết

Giả sử một hàng đợi review hợp đồng:
- Nhận **8 yêu cầu/tuần**.
- Có năng lực hoàn tất **6 yêu cầu/tuần**.
- Điều kiện, độ khó tương đối tương đồng và tốc độ này duy trì trong ví dụ.

~~~text
Tồn chờ tăng xấp xỉ = 8 − 6 = 2 yêu cầu/tuần
Sau 4 tuần: tăng thêm 4 × 2 = 8 yêu cầu
~~~

Không thể dùng thông tin này suy **thời gian chờ chính xác của từng item**; còn phụ thuộc lịch đến, ưu tiên, độ khó và cách phục vụ. Nhưng nó cho thấy hàng đợi không thể ổn định lâu dài khi tốc độ đến liên tục vượt tốc độ xử lý.

### 7.2. Vì sao kéo thêm việc mới làm tình hình xấu hơn?

Khi team UI chờ API nhưng vẫn mở thêm story, Team API có thể nhận nhiều yêu cầu song song. WIP tăng, reviewer phải chuyển ngữ cảnh liên tục, hợp đồng thay đổi giữa chừng và code tích hợp muộn. **Mọi nhóm đều có thể bận hơn trong khi cycle time cấp sản phẩm tăng.**

Một chính sách phù hợp có thể là:
- Giới hạn WIP ở nơi công việc đang tích tụ.
- Ưu tiên hoàn tất item gần Done thay vì mở mới.
- Tổ chức pairing để giải quyết hợp đồng khó.
- Đưa contract test vào CI.
- Tách những item quá lớn thành lát cắt giá trị có thể giao.

### 7.3. Little's Law có điều kiện

Trong một hệ thống **tương đối ổn định**, có ranh giới thống nhất và dữ liệu phù hợp:

~~~text
WIP trung bình ≈ throughput rate trung bình × cycle time trung bình

cycle time trung bình ≈ WIP trung bình / throughput rate trung bình
~~~

Ví dụ WIP trung bình là **12 item**, throughput trung bình **3 item/tuần**, thì cycle time trung bình tương ứng khoảng **12/3 = 4 tuần** trong điều kiện áp dụng.

Đây **không phải phép tính cho cycle time chính xác của mọi item** hoặc lệnh yêu cầu mỗi nhóm có WIP bằng 12. Không áp máy móc vào kỳ mà hàng chờ tăng vô hạn, ranh giới đo thay đổi hay một lô công việc ngắn chưa đạt trạng thái ổn định.

### 7.4. Chỉ số cần đọc chung

| Chỉ số | Câu hỏi | Giới hạn |
| --- | --- | --- |
| **WIP** | Có bao nhiêu item đã started chưa finished? | Không đo mức bận của cá nhân |
| **Work item age** | Item chưa Done đã chờ bao lâu? | Chưa phải cycle time cuối |
| **Throughput** | Bao nhiêu item finished trong kỳ? | Không tự đo giá trị hoặc độ khó |
| **Cycle time distribution** | Item hoàn tất mất bao lâu và biến động ra sao? | Chỉ gồm item đã finished |
| **Blocked time** | Item mất bao lâu vì phụ thuộc được ghi nhận? | Cần lý do và cách tính giờ lịch/làm việc |
| **Decision latency** | Từ đề xuất đủ thông tin đến lúc có quyết định mất bao lâu? | Phải phân biệt câu hỏi thiếu thông tin |
| **Integration rework** | Làm lại bao nhiêu do contract không khớp? | Phải xác định loại và mức độ |
| **Outcome** | Người dùng có nhận giá trị đúng và kịp thời? | Không suy nhân quả thiếu thiết kế đo |

**Một CFD dày ở Review là tín hiệu có hàng tồn**, chưa phải bằng chứng reviewer làm việc chậm. Cần nhìn item history và blocked reasons.

## 8. Thêm tầng quản lý: đánh giá cả lợi ích lẫn chi phí

### 8.1. Manager có thể tạo giá trị thực

Một vai trò quản lý có thể giúp:
- Xác định định hướng và ưu tiên đầu tư giữa sản phẩm.
- Phân bổ nguồn lực và phát triển năng lực.
- Coaching, tuyển dụng, xử lý xung đột và bảo vệ sức khỏe nhóm.
- Quản trị ngân sách, bảo mật, tuân thủ hoặc rủi ro dài hạn.
- Gỡ những trở ngại vượt quyền của từng team.
- Giảm tranh chấp quyết định giữa các vùng ownership.

Vì thế nhận định “mọi tầng quản lý đều là lãng phí” **không đúng**. Câu hỏi phải là: **cấp mới giải quyết việc nào đang không được giải quyết tốt và có thể kiểm chứng lợi ích đó không?**

### 8.2. Rủi ro của approval chain nối tiếp

Một thay đổi nhỏ có thể phải đi:
1. Developers trình team lead.
2. Team lead gửi manager.
3. Manager chuyển hội đồng.
4. Hội đồng hỏi lại Developers.
5. Câu hỏi và câu trả lời quay qua từng tầng.

Chi phí là **thời gian chờ + mất bối cảnh + vòng hỏi lại**, chứ không chỉ số phút từng người đọc. Khi người hiểu vấn đề nhất không trao đổi trực tiếp với người có quyền quyết, những câu hỏi đơn giản có thể trở thành phức tạp.

### 8.3. Phân quyền theo loại quyết định và mức rủi ro

| Quyết định | Nơi có thông tin trực tiếp | Cơ chế kiểm soát hợp lý |
| --- | --- | --- |
| Đổi tên biến, refactor nội bộ | Developers | Review và test kỹ thuật theo chuẩn |
| Cách triển khai PBI trong Sprint | Developers | Tự quản trong DoD và ràng buộc chung |
| Thứ tự Product Backlog của một sản phẩm | Product Owner | Tham vấn stakeholder và chiến lược |
| API contract dùng chung | Các nhóm owner của hợp đồng | Consultation, contract tests và người chốt khi bất đồng |
| Dữ liệu nhạy cảm hoặc thay chính sách quyền | Engineering và người có thẩm quyền an toàn | Review độc lập theo rủi ro |
| Ngân sách lớn, quyết định tổ chức khó đảo ngược | Lãnh đạo có thẩm quyền | Đánh giá tài chính/chiến lược |
| Sự cố production nghiêm trọng | Incident lead, on-call | Escalation theo runbook, không đợi phê duyệt thông thường |

Bảng này là **mẫu tư duy**, không thay yêu cầu pháp lý hoặc chính sách thực của tổ chức. Các quyết định **rủi ro thấp và dễ đảo ngược** thường nên được ủy quyền rõ, trong khi quyết định **bảo mật, dữ liệu hoặc chi phí lớn** có thể cần phê duyệt chuyên trách.

### 8.4. Hai chữ ký không nhất thiết mang hai lớp giá trị

Nếu hai cấp duyệt đọc cùng một checklist mà không có trách nhiệm hoặc tiêu chí khác nhau, cấp thứ hai có thể chỉ thêm queue. Nhưng nếu một review kiểm **phân quyền dữ liệu** và review còn lại kiểm **khả năng rollback**, hai góc nhìn có thể quan trọng.

Đặt câu hỏi:
- Mỗi bước duyệt ngăn lỗi/rủi ro cụ thể nào?
- Có thể chạy song song thay vì nối tiếp?
- Có thể tự động kiểm tra quy tắc lặp lại?
- Ai chịu trách nhiệm quyết định cuối?
- Có người thay thế nếu người duyệt vắng?
- Nếu bỏ bước, hậu quả gì có thể tăng?
- Có dữ liệu về lỗi đã ngăn hoặc rework đã giảm không?

Không có một tỷ lệ nhân viên/manager hoặc số tầng quản lý **chuẩn cho mọi sản phẩm**. Cần nhìn mức tự chủ, rủi ro, nhu cầu coaching và thực tế quyết định.

## 9. Đổi ranh giới nhóm để giảm phụ thuộc

### 9.1. Đơn vị tổ chức nên hướng tới lát cắt giá trị khi khả thi

Một team đa chức năng có thể chịu trách nhiệm giao **từ UI qua API đến test tích hợp** cho một lát cắt. Lợi ích là ít bàn giao hơn và có trách nhiệm Done rõ hơn. Nhưng một số năng lực chung hoặc chuyên gia hiếm không nhất thiết phải được nhân bản trong mọi team.

Có thể cân nhắc:
- Nhóm sở hữu **miền nghiệp vụ hoặc value stream** có ranh giới tương đối độc lập.
- Nhóm platform cung cấp khả năng tự phục vụ (CI, môi trường, observability).
- Nhóm hỗ trợ chuyên môn tạm thời nâng kỹ năng TDD/SRE/security.
- Collaboration trực tiếp có thời hạn cho một migration hoặc ranh giới khó.
- Contract-first và test tự động khi hai team phải thay đổi độc lập.

### 9.2. Các kiểu quan hệ có lợi khi dùng đúng

| Kiểu | Mục tiêu | Cách tránh bottleneck mới |
| --- | --- | --- |
| **Collaboration tạm thời** | Hai nhóm cùng khám phá vấn đề khó | Có mục tiêu, mốc kết thúc và ownership sau đó |
| **X-as-a-service** | Một nhóm cung cấp khả năng ổn định cho nhiều nhóm | Self-service, tài liệu, contract, SLE và đường hỗ trợ |
| **Facilitating** | Chuyển giao kỹ năng/chuyên môn hiếm | Coaching và hướng tới tự chủ, không duyệt mọi story |
| **Team theo miền sản phẩm** | Sở hữu kết quả end-to-end ở phạm vi rõ | API/data boundary, shared DoD và integration |
| **Nhóm xử lý sự cố/tái cấu trúc tạm thời** | Tập trung năng lực cho rủi ro đặc biệt | Exit criteria và cơ chế trả trách nhiệm |

Không nên tách microservices chỉ vì muốn nhóm độc lập. Nếu dữ liệu, transaction và contract đang dính chặt, việc tách có thể **chuyển chi phí từ repository sang network, distributed consistency và vận hành**.

### 9.3. Xem kiến trúc cùng cấu trúc tổ chức

Nếu mỗi user story đều phải sửa cùng lúc **bốn repository do bốn team quản lý**, hãy hỏi:
- Có thể đưa những phần thường cùng thay đổi vào một boundary không?
- Có thể ổn định API để bên tiêu thụ không phải chờ mỗi lần không?
- Có thể dùng schema compatibility và contract tests không?
- Có phải một shared component ôm quá nhiều trách nhiệm?
- Có cần rõ ownership của dữ liệu và tác dụng phụ không?

Đây là cách dùng **mối liên hệ giữa cấu trúc giao tiếp và kiến trúc phần mềm** làm tín hiệu, không phải định luật nói chính xác hiệu quả của một quyết định tổ chức.

## 10. Những phương án trước khi thêm nhóm hoặc cấp quản lý

| Phương án | Lợi ích tiềm năng | Chi phí và giới hạn | Khi nào nên thử |
| --- | --- | --- | --- |
| **Thêm nhóm giao giá trị độc lập** | Nhiều luồng có thể được xử lý song song | Onboarding, tích hợp, ưu tiên chung | Nhu cầu đủ độc lập và backlog phù hợp |
| **Thêm người trong nhóm hiện tại** | Bổ sung kỹ năng mà không tạo team boundary mới | Tăng tương tác và thời gian hòa nhập | Có công việc và mentor đủ hỗ trợ |
| **Thay ownership theo lát cắt** | Giảm handoff giữa silo | Đào tạo, chuyển quyền, rủi ro giai đoạn đầu | Story thường phải đi qua nhiều backlog |
| **Platform self-service** | Giảm lặp và dependency hạ tầng | Phải xây, duy trì và hỗ trợ internal product | Nhiều nhóm có nhu cầu dùng chung ổn định |
| **Facilitating team có thời hạn** | Tăng kỹ năng nhiều nhóm | Có thể thành approval team nếu thiếu exit plan | Thiếu chuyên môn kỹ thuật nhất thời |
| **Contract tests và CI** | Tìm lỗi sớm, giảm chờ kiểm tra thủ công | Đầu tư test và độ tin cậy pipeline | Rework do tích hợp/hợp đồng cao |
| **Giảm WIP, làm rõ pull policy** | Hoàn tất việc đang mở trước | Cần thay thói quen tổ chức | Hàng chờ review/integration nở |
| **Làm rõ/ủy quyền decision rights** | Giảm latency của quyết định rủi ro thấp | Cần ranh giới và guardrails | Nhiều bước ký lặp lại |
| **Thêm tầng quản lý có chức năng khác biệt** | Quản trị chiến lược và rủi ro, phát triển người | Chi phí và khả năng tăng approval chain | Nhu cầu vượt quyền/cơ cấu hiện tại |
| **Không đổi cơ cấu, thử nghiệm nhỏ** | Ít chi phí đảo ngược, có dữ liệu nhanh | Có thể chưa đủ cho nhu cầu lâu dài | Nguyên nhân còn chưa chắc |

Một nguyên tắc là **chẩn đoán đúng nút thắt trước khi chọn hình dạng tổ chức**. Nếu pipeline đỏ làm 10 người chờ, thêm 5 Developers không tự sửa pipeline.

## 11. Đo chi phí phối hợp bằng những đơn vị đúng

### 11.1. Một tuần làm việc giả định của ba nhóm

| Hoạt động | Người | Thời lượng/người | Công sức |
| --- | ---: | ---: | ---: |
| Họp chốt API contract | 6 | 45 phút | 4,5 person-hours |
| Chuẩn bị tài liệu trước họp | 3 | 30 phút | 1,5 person-hours |
| Làm lại vì hai cách hiểu khác | 2 | 3 giờ | 6 person-hours |
| **Tổng được ghi nhận** | | | **12 person-hours** |

Cách tính: **6×45/60 + 3×30/60 + 2×3 = 4,5 + 1,5 + 6 = 12**.

**Không được mặc định toàn bộ 12 giờ là lãng phí.** Họp và chuẩn bị có thể giảm lỗi; sáu giờ rework có thể do không kiểm chứng contract sớm. Cũng không nên cộng lại cùng sáu giờ rework nếu nó đã nằm trong effort của story.

### 11.2. Báo cáo riêng elapsed wait

Nếu một item chờ lần lượt:
- 1 ngày cho contract.
- 2 ngày cho môi trường tích hợp.
- 1 ngày cho phê duyệt.

Nếu cả ba **thật sự nối tiếp và nằm trên critical path**, chúng có thể kéo dài delivery tới **4 ngày làm việc**. Nếu chồng lấn với công việc khác, ảnh hưởng tới ngày hoàn tất thấp hơn.

Không thể cộng **12 person-hours + 4 ngày elapsed wait** thành một số giờ duy nhất. Cần báo rõ **effort để làm công việc** và **elapsed time người dùng phải chờ**.

### 11.3. Cost of delay là một câu hỏi thứ ba

Cost of delay là **giá trị bị mất hoặc rủi ro gia tăng vì kết quả đến muộn**:
- Sửa lỗi phân quyền muộn có thể kéo dài rủi ro.
- Ra mắt đăng ký sau ngày mở workshop có thể làm mất cơ hội.
- Một thay đổi nhỏ ít khẩn cấp có thể không mất nhiều giá trị nếu chậm vài ngày.

Không đơn giản lấy số ngày chờ nhân lương Developers để tuyên bố đã định giá **cost of delay**. Cần dữ liệu sản phẩm, kịch bản, mức bất định và thời điểm.

## 12. Business case minh họa: thêm năm Developers và một team

### 12.1. Mô hình tăng năng lực có chi phí phối hợp

Giả sử:
- Hai team hiện có tổng cộng **10 Developers**.
- Giao trung bình **12 user stories tương đối tương đồng mỗi tháng**, cùng Definition of Done.
- Dự kiến thêm **5 Developers** thành team thứ ba.
- Nếu hoàn toàn độc lập, team mới có thể đóng góp **6 item/tháng**.
- Phụ thuộc mới khiến mất tương đương **2 item/tháng**; rework tích hợp mất thêm tương đương **1 item/tháng**.

~~~text
Throughput hiện tại:                           12 item/tháng
Năng lực tăng thêm giả định:                  + 6 item/tháng
Tác động phối hợp giả định:                   − 2 item/tháng
Tác động rework giả định:                     − 1 item/tháng
---------------------------------------------------------
Throughput hiệu dụng của kịch bản:              15 item/tháng
Tăng ròng:                                       3 item/tháng
~~~

Số Developers tăng **(15−10)/10 = 50%**, throughput giả định tăng **(15−12)/12 = 25%**. Đây **không phải một quy luật hiệu suất 50%**: các số +6, −2, −1 được đặt ra để luyện đánh giá, chưa đo từ một đội thật.

### 12.2. Một phép tính tài chính có giới hạn

Nếu **chi phí đầy đủ giả định** của mỗi Developers là 60 triệu đồng/tháng:
- Nhân sự tăng thêm: **5 × 60 = 300 triệu đồng/tháng**.
- Theo kịch bản, item tăng ròng: **3 item/tháng**.
- Tỷ số mang tính mô tả: **300/3 = 100 triệu đồng chi phí nhân sự tăng thêm cho mỗi item tăng ròng trong kịch bản**.

**Đây không phải ROI hay giá trị thực của một story.** Item khác nhau về giá trị, độ khó, hỗ trợ, chi phí vận hành và rủi ro. Chưa tính onboarding, dụng cụ, chi phí chuyển đổi hoặc giá trị sản phẩm mang lại. Không được dùng tỷ số này để chấm năng suất cá nhân.

### 12.3. Phương án cạnh tranh: giảm phụ thuộc với đội hình cũ

Một phương án khác giữ 10 Developers, đầu tư vào CI, contract tests và self-service. Giả sử throughput sau thời gian chuyển đổi có thể tăng **từ 12 lên 14 item/tháng**, nhưng cần đầu tư công cụ, học kỹ năng và duy trì.

Chưa thể kết luận phương án **14 item** chắc chắn tốt hơn phương án **15 item**. Cần so:
- Nhu cầu thực tế và Product Goal.
- Giá trị của các item tăng thêm.
- Thời gian đạt được năng lực mới.
- Tính độc lập của các luồng công việc.
- Mức rủi ro nếu giữ nguyên.
- Chi phí vận hành dài hạn.
- Độ tin cậy và sức bền đội.

### 12.4. Dùng kịch bản thay vì một lời hứa chính xác

| Kịch bản | Đặc điểm | Câu hỏi cần kiểm |
| --- | --- | --- |
| **Tốt** | Team mới sở hữu một miền ít phụ thuộc, chất lượng ổn | Backlog có đủ luồng độc lập không? |
| **Cơ sở** | Năng lực tăng nhưng có handoff và integration rework | Đo được chờ, lỗi và capacity thực không? |
| **Xấu** | Team mới cần phê duyệt liên tục, thiếu ownership, CI không ổn | Cần thay boundary hoặc dừng phương án không? |

**Quyết định đầu tư cần assumptions, phạm vi, điều kiện kiểm tra và mốc xem lại**, không chỉ con số tăng người.

## 13. Khi thêm nhóm thật sự tạo giá trị

Một nhóm mới hợp lý hơn khi:

1. Có **dòng nhu cầu tương đối độc lập** và dài hạn, không chỉ một lô task tạm thời.
2. Team có thể chịu trách nhiệm **lát cắt giá trị** với Definition of Done rõ.
3. Nhu cầu chuyên môn mới không thể giải quyết hiệu quả bằng đào tạo hoặc platform chung.
4. Data/API boundaries đủ rõ để không yêu cầu sửa đồng thời nhiều nơi cho mọi story.
5. Có Product Goal/ưu tiên sản phẩm thống nhất ở cấp thích hợp.
6. Các nhóm có quyền kỹ thuật trong phạm vi ownership, không phải xin phép mọi thay đổi.
7. CI, contract tests và môi trường tích hợp đủ đáng tin.
8. Tổ chức có khả năng onboarding mà không làm toàn bộ team cũ đình trệ.
9. Có chính sách xử lý sự cố và ownership sau release.
10. Lợi ích được xem theo **outcome + quality + flow**, không chỉ số ticket.

### 13.1. Team hỗ trợ chuyên môn khác team approval

Một nhóm hỗ trợ kỹ thuật có thể dạy cách triển khai security tests, TDD hoặc observability rồi để các nhóm tự thực hiện theo guardrails. Nếu nhóm hỗ trợ lại bắt mọi PR gửi qua để “ký”, rủi ro tạo hàng chờ lớn.

Đầu ra tốt của nhóm hỗ trợ có thể là **giảm dependency vào chính nhóm đó** theo thời gian, không phải nhận mãi càng nhiều ticket.

### 13.2. Platform team phải hướng tới self-service

Nếu mọi nhóm chờ platform team tạo môi trường test thủ công, việc có platform team chưa chắc giảm chi phí. Cần:
- API/công cụ rõ.
- Tài liệu và ví dụ chạy được.
- Quyền dùng self-service phù hợp.
- SLE/đường hỗ trợ cho trường hợp đặc biệt.
- Contract/versioning và quy tắc rollback.
- Ownership vận hành rõ.

## 14. Khi thêm tầng quản lý là lựa chọn hợp lý

Một tầng quản lý có thể hợp lý khi:
- Quyền phân bổ ngân sách giữa nhiều sản phẩm chưa có đầu mối.
- Xung đột mục tiêu chiến lược vượt khả năng quyết của từng Product Owner/team.
- Có nhu cầu phát triển kỹ năng, tuyển dụng và chăm sóc đội ngũ vượt sức quản lý hiện tại.
- Rủi ro pháp lý, an toàn hoặc vận hành cần trách nhiệm độc lập.
- Những trở ngại giữa các bộ phận lặp lại vì thiếu người có quyền giải quyết.
- Quản trị hiện tại đang gây quyết định **không rõ trách nhiệm**, chứ không chỉ quyết định chậm.

**Tầng mới cần có nhiệm vụ và kết quả khác biệt**, không chỉ thêm một chữ ký trung gian.

### 14.1. Decision rights nên được mô tả trước

~~~text
Loại quyết định:
- Ai chuẩn bị bằng chứng và trực tiếp làm?
- Ai có quyền chốt?
- Ai bắt buộc được tham vấn?
- Ai chỉ cần được thông báo?
- Khi nào vượt ranh giới ủy quyền?
- Tiêu chí phê duyệt độc lập là gì?
- Mốc cần quyết; backup khi người phụ trách vắng?
- Điều kiện escalation và nơi ghi kết quả?
~~~

Đối với quyết định nhiều nhóm và rủi ro lớn, có thể dùng decision log hoặc ADR. Không nên tạo ADR cho mỗi đổi tên biến. Mục tiêu là **quyền rõ, quyết định nhanh vừa đủ, kiểm soát rủi ro phù hợp**.

### 14.2. Đo outcome của quản lý mới

- Thời gian ra quyết định quan trọng có giảm không?
- Xung đột ưu tiên có được giải quyết thay vì chuyển vòng quanh không?
- Những quyết định rủi ro thấp đã được ủy quyền chưa?
- Chất lượng và khả năng xử lý sự cố có được bảo vệ không?
- Các nhóm có tự chủ, học hỏi và bền vững hơn không?
- Số lần leo thang cùng vấn đề có giảm không?
- Product Goal có tiến triển tốt hơn không?

Một tầng mới tạo thêm báo cáo nhưng không cải thiện những kết quả ấy **cần được xem lại**.

## 15. Scrum khi nhiều Scrum Teams làm cùng một sản phẩm

### 15.1. Một sản phẩm cần sự minh bạch về giá trị và chất lượng

Theo Scrum Guide 2020, khi **nhiều Scrum Teams cùng làm một sản phẩm**, họ cùng chia sẻ **Product Goal, Product Backlog và Product Owner**, đồng thời **cùng định nghĩa và tuân thủ một Definition of Done**. Điều này giúp tránh một team coi “Done” là đã merge, team khác coi “Done” là đã chạy unit test, trong khi chưa có Increment tích hợp.

Cần lưu ý **ranh giới sản phẩm**: các nhóm làm các sản phẩm khác nhau có thể có Product Goals và Product Backlogs riêng. Không áp một mô hình tổ chức duy nhất cho toàn công ty nếu đó là những sản phẩm khác nhau.

### 15.2. Những thực hành phối hợp có ích

- Refinement làm rõ các PBI có dependency lớn trước Sprint Planning.
- Các Developers cùng nhận diện rủi ro tích hợp, contract và DoD.
- Tạo Increment tích hợp thường xuyên, không dồn sang “integration Sprint”.
- Cùng kiểm tra tiến triển tới Product Goal thay vì chỉ báo cáo story points của mỗi team.
- Dùng Sprint Review để nhìn kết quả và phản hồi stakeholder, không biến thành cổng phê duyệt bắt buộc cho mọi release.
- Dùng Retrospective để xem wait, handoff, CI và chất lượng, chọn thử nghiệm cải tiến.

### 15.3. Không biến coordination meeting thành tầng quản lý mới

Một buổi đồng bộ liên team có thể hữu ích để giải quyết blocker chung. Các hình thức như **Scrum of Scrums** có thể được dùng nếu phù hợp, nhưng **không phải event bắt buộc trong Scrum Guide 2020**. Cuộc họp nên có **vấn đề, người có khả năng giải quyết, quyết định và action**; không chỉ từng nhóm đọc lại status.

## 16. Kanban và XP giảm chi phí phối hợp

### 16.1. Kanban: làm hiện ra hàng chờ ngoài nhóm

Một workflow có thể là:

~~~text
Ready -> Doing -> External dependency -> Integration -> Verify -> Done
                  |                    |
                  +-- Blocked: API      +-- Blocked: environment
                  +-- Blocked: approval
~~~

Nhóm cần công bố Started/Finished, xử lý blocked, WIP policy và điều kiện Done. Một item đã started rồi bị chặn **vẫn là WIP** theo ranh giới ấy, không nên chuyển về Ready chỉ để dashboard đẹp.

Có thể xem:
- Work item age và item đang blocked.
- Cycle time distribution và đuôi dài.
- Throughput cấp sản phẩm.
- CFD cho các dải Review/Integration/Waiting.
- Service Level Expectation cho loại yêu cầu review tiêu chuẩn nếu có lịch sử phù hợp.

**SLE là kỳ vọng theo phân bố, không tự động là SLA hoặc bảo đảm mọi yêu cầu sẽ hoàn tất trong ngưỡng.**

### 16.2. XP và kỹ thuật tích hợp liên tục

Một số thực hành hữu ích:
- **TDD:** mã hóa hành vi nghiệp vụ và regression tests.
- **Contract tests:** kiểm tra API/event giữa nhóm.
- **Continuous integration:** tích hợp sớm, tránh phát hiện sai hợp đồng cuối Sprint.
- **Pair programming:** giải quyết vấn đề phức tạp trực tiếp, chia sẻ kiến thức.
- **Simple design/refactoring:** giảm coupling không cần thiết.
- **Small releases:** tạo vòng phản hồi sớm, giảm quy mô lỗi.
- **Collective ownership phù hợp:** tránh mọi thay đổi phải chờ một chuyên gia.

### 16.3. Ví dụ hợp đồng có thể kiểm tra

~~~gherkin
Tính năng: Trạng thái đăng ký workshop

  Tình huống: PENDING không có nghĩa đã giữ chỗ
    Cho trước một yêu cầu đăng ký ở trạng thái PENDING
    Khi client lấy thông tin trạng thái
    Thì API trả trạng thái nghiệp vụ PENDING
    Và client không hiển thị "Đã xác nhận chỗ"

  Tình huống: API timeout
    Cho trước việc lấy trạng thái không thành công
    Khi client hiển thị phản hồi
    Thì client không tự suy đoán rằng đăng ký đã CONFIRMED
~~~

Đây là **đặc tả minh họa**, chưa chứng minh hệ thống thật đã an toàn. Vẫn cần test quyền, tích hợp, transaction và tình huống đồng thời nếu rủi ro liên quan.

## 17. Nhóm phân tán và chi phí giao tiếp qua múi giờ

Một nhóm mới ở khu vực khác có thể bổ sung chuyên môn và giờ làm việc, nhưng **chênh múi giờ có thể biến một câu hỏi nhỏ thành nhiều ngày lịch** nếu thiếu handoff tốt.

Mô hình phối hợp:
1. **Async trước:** story, API contract, dữ liệu, expected/actual, test và câu hỏi được ghi rõ.
2. **Sync khi cần:** huddle có đúng người để quyết vấn đề mơ hồ, rủi ro hoặc khẩn cấp.
3. **Async sau:** ghi rationale, owner, action, deadline và nơi xem lại.
4. **Handoff:** người nhận biết next step, điều chưa kiểm, các rủi ro và nguồn bằng chứng.
5. **Incident:** dùng on-call và escalation theo mức nghiêm trọng, không kỳ vọng mọi người trực 24/7.

Không coi **thời gian không phản hồi khi người nhận đang nghỉ** là thiếu trách nhiệm. Khi đo cần phân biệt **elapsed calendar time** ảnh hưởng ngày giao với **response time trong giờ làm việc**.

## 18. Tình huống xuyên suốt: thêm Team Integration có giải quyết nút thắt?

### 18.1. Product Goal và hai nhóm hiện tại

- **Team Enrollment:** quy tắc đăng ký, sức chứa và dữ liệu.
- **Team Experience:** giao diện, trạng thái và trải nghiệm học viên.
- **Product Goal:** học viên có thể đăng ký, biết kết quả chính xác và không bị xác nhận vượt sức chứa.

Vấn đề quan sát: nhiều story đụng UI và API, PR chờ contract review, lỗi tích hợp phát hiện muộn. Một đề xuất là thêm **Team Integration** và **manager duyệt hợp đồng**.

### 18.2. Sơ đồ của một phương án rủi ro

~~~mermaid
flowchart TD
    PO[Product Backlog] --> EX[Team Experience]
    PO --> EN[Team Enrollment]
    EX --> IN[Team Integration queue]
    EN --> IN
    IN --> AP[Management approval]
    AP --> REL[Release và phản hồi học viên]
~~~

Nếu mọi story bắt buộc đi qua Integration queue rồi Approval queue, nhóm mới có thể **tạo hai điểm chờ nối tiếp**, mặc dù mọi người đều có năng lực. Nhưng nếu Team Integration tạo tự động hóa và phục vụ như platform, nó có thể **giảm chờ thay vì tạo chờ**.

### 18.3. Baseline bốn tuần (dữ liệu giả định)

| Tín hiệu | Baseline giả định | Lưu ý |
| --- | ---: | --- |
| Product throughput | 12 user stories Done/tháng | Cùng DoD, loại item tương đối tương đồng |
| WIP trung bình | 15 item | Started/Finished rõ |
| Cycle time p85 | 14 ngày lịch | Cần mẫu và cách tính nhất quán |
| Median blocked time chờ API contract | 2 ngày làm việc | Chỉ tính items có block loại này |
| Item đang chờ integration cuối kỳ | 7 | Một snapshot, không phản ánh toàn bộ xu hướng |
| Integration defects sau merge | 5 | Phân loại mức nghiêm trọng |
| Incident nghiêm trọng sau release | 1 | Mẫu rất nhỏ, không suy xác suất |

### 18.4. Ba lựa chọn thực tế

**A. Tạo Team Integration như một cổng bắt buộc.** Có sở hữu kiểm thử rõ, nhưng mỗi story cần bàn giao và xếp hàng, cộng manager approval.

**B. Giữ hai nhóm, nâng năng lực CI và contract tests.** Hai nhóm tiếp tục sở hữu Increment tích hợp, thêm môi trường kiểm thử tin cậy, pairing ở ranh giới khó, tự động hóa kiểm tra và làm rõ decision rights.

**C. Có nhóm hỗ trợ năng lực tích hợp/platform self-service.** Nhóm mới xây tooling, hướng dẫn và mẫu test cho các team, nhưng **không giữ quyền “Done” của mọi story**. Có mốc xem lại tính cần thiết sau khi năng lực lan tỏa.

Không có đáp án tốt nhất khi chưa biết **nguyên nhân nghẽn**. Nếu test fail vì hạ tầng dùng chung thiếu năng lực, C có thể hữu ích. Nếu lỗi phát sinh vì hai team không thống nhất API contract, B có thể đủ. Nếu có luồng sản phẩm độc lập mới, một **team giao giá trị độc lập** có thể hợp lý hơn cả ba.

### 18.5. Thử nghiệm trước khi tái tổ chức lớn

Một thử nghiệm bốn tuần minh họa:

1. Chọn luồng user stories thường xuyên chạm hai nhóm.
2. Thống nhất contract PENDING/CONFIRMED và các bất biến dữ liệu.
3. Đưa contract/integration tests vào CI.
4. Giới hạn WIP ở hàng chờ review/integration theo chính sách thử.
5. Chỉ rõ ai có quyền quyết hợp đồng và lúc nào cần escalation.
6. Ghi item-level blocked time, decision latency, cycle time và lỗi.
7. Bảo vệ DoD, quyền dữ liệu và khả năng rollback.
8. Lấy phản hồi học viên khi Increment được giao.
9. Sau thử, xem kết quả và nguyên nhân chưa giải quyết.
10. Quyết định có cần platform capacity hoặc đội mới thật không.

Thời gian bốn tuần **chỉ là ví dụ**, có thể không đủ số item để đánh giá một percentile đáng tin.

### 18.6. Dữ liệu sau thử và giới hạn kết luận

Giả sử có bảng sau, **hoàn toàn giả định**:

| Tín hiệu | Trước | Sau |
| --- | ---: | ---: |
| Product throughput | 12 | 14 item/tháng |
| WIP trung bình | 15 | 11 |
| Cycle time p85 | 14 | 11 ngày lịch |
| Median blocked time chờ contract | 2 | 1 ngày làm việc |
| Integration defects | 5 | 2 |
| Incident nghiêm trọng | 1 | 1 |

Nhóm có thể nói:
- Throughput tăng **2 item/tháng** trong hai kỳ được so.
- WIP trung bình giảm **4 item**.
- p85 cycle time giảm **3 ngày lịch**.
- Median blocked wait giảm **1 ngày làm việc**.
- Integration defects giảm **3**.
- Incident nghiêm trọng **chưa thấy giảm** trong mẫu cực nhỏ.

Nhưng **chưa thể khẳng định mọi thay đổi do riêng thử nghiệm**. Cần xem loại story, kỳ nghỉ, incident, biến động nhu cầu, DoD, chất lượng dữ liệu, độ ổn định CI và phản hồi thực của người dùng.

### 18.7. Quyết định có điều kiện

Một đề xuất có trách nhiệm có thể là:

> “Chúng ta chưa tạo cổng phê duyệt mới cho mọi story. Việc đưa contract tests vào CI có tín hiệu giảm chờ nên sẽ tiếp tục thử và giữ DoD. Nếu vẫn tồn một capability dùng chung khó duy trì, sẽ đánh giá platform team hướng self-service với SLE rõ. Nếu backlog cho thấy nhiều luồng giá trị thật sự độc lập, sẽ cân nhắc thêm team sở hữu miền riêng. Mỗi thay đổi phải có owner, guardrails và mốc xem lại.”

Đó là cách **học từ dữ liệu**, không mặc định giữ hay phủ nhận việc thêm nhóm về lâu dài.

## 19. Thiết kế thí nghiệm tổ chức có bằng chứng

### 19.1. Từ giả định mơ hồ đến giả thuyết

Câu yếu: “Thêm đội sẽ nhanh hơn.”

Câu có thể kiểm chứng hơn:

> “Nếu công việc phát triển trạng thái đăng ký có contract tests và hai nhóm tự tích hợp thay vì chờ cổng duyệt chung, những item cùng loại dự kiến giảm blocked time và cycle time, trong khi tỷ lệ lỗi dữ liệu và quyền truy cập không tăng. Chúng tôi sẽ theo dõi qua một khoảng đủ dữ liệu, ghi rõ thay đổi về loại item, và quyết định tiếp dựa trên kết quả.”

Cần bổ sung **baseline, điều kiện thành công, owner và giới hạn** để thí nghiệm đáng tin.

### 19.2. Bộ dữ liệu tối thiểu

- **Flow:** WIP, throughput, work item age, cycle time distribution.
- **Dependencies:** số handoff per item, blocked reasons và elapsed wait.
- **Decisions:** thời điểm cần quyết, người có quyền, decision latency.
- **Quality:** lỗi tích hợp, lỗi sau release, CI reliability, rework.
- **Product:** số Increment hữu ích, phản hồi và Product Goal outcome.
- **People:** đổi ca, cognitive load, sự phụ thuộc một người, sức làm việc bền vững.
- **Cost:** thời gian onboarding, công cụ, vận hành, chi phí tổ chức.

Không nên dùng thời gian online hoặc thời gian phản hồi từng tin nhắn để **xếp hạng cá nhân**. Đo cấu trúc hệ thống để cải thiện, không tạo văn hóa giám sát.

### 19.3. Biến gây nhiễu khi so trước/sau

Số liệu có thể đổi vì:
- Loại và kích thước work items khác nhau.
- Product Backlog ưu tiên việc khó hơn.
- Người mới đang onboarding.
- Nghỉ lễ hoặc incident production.
- Tăng mức chất lượng của DoD.
- Thay cách đếm item hoặc thời điểm Finished.
- Thay hệ thống CI hoặc môi trường release.
- Nhu cầu khách hàng theo mùa.

Vì vậy **before/after là bằng chứng quan sát**, chưa chứng minh quan hệ nhân quả. Cần công bố cỡ mẫu, kỳ, ranh giới và những thay đổi đồng thời.

### 19.4. Guardrails không được hy sinh

Một thí nghiệm để tăng throughput **không được đánh đổi**:
- Bất biến không xác nhận vượt sức chứa.
- Quyền dữ liệu và bảo mật.
- Definition of Done và chất lượng Increment.
- Khả năng khôi phục sự cố.
- Sức làm việc bền vững.
- Tính minh bạch về ownership và Product Goal.

Nếu guardrail nghiêm trọng thất bại, phải **dừng/điều chỉnh trước khi mở rộng thay đổi tổ chức**, không chờ chỉ số throughput đẹp lên.

## 20. Các sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Giả định thêm 50% người tạo 50% output | Không tính phụ thuộc và onboarding | Mô hình giả thuyết, đo flow/outcome |
| Dùng n(n−1)/2 làm số cuộc họp | Chỉ là số cặp tiềm năng | Xem mạng phụ thuộc thực |
| Gọi mọi giao tiếp là lãng phí | Mất feedback, review và an toàn | Đo giá trị quyết định/kiểm soát |
| Chỉ đo giờ họp | Bỏ hàng chờ và làm lại | Đo effort, wait và rework riêng |
| Cộng mọi thời gian song song | Sai critical path | Vẽ dependency graph |
| Tối ưu throughput mỗi team | Chưa chắc có Increment | Đo Done cấp sản phẩm |
| Mở nhiều story để ai cũng bận | WIP và queue tăng | Giới hạn WIP, ưu tiên hoàn tất |
| Team tích hợp thành cổng cho mọi việc | Tạo backlog mới | Tự động hóa, self-service |
| Bắt mọi PR qua manager | Queue không tương xứng rủi ro | Ủy quyền và review theo rủi ro |
| Bỏ review bảo mật để nhanh | Tăng nguy cơ dữ liệu | Giữ guardrails phù hợp |
| Không có decision owner | Tranh luận không ai chốt | Ghi rõ quyền và escalation |
| Tách microservice cho mỗi team | Tăng vận hành và distributed coupling | Chọn boundary dựa domain/data |
| Mọi team cùng sửa contract không rõ | Rework liên tục | Contract-first, compatibility tests |
| Dùng một chuyên gia trong mọi quyết định | Key-person bottleneck | Coaching, pairing, quyền thay thế |
| Lấy story count làm giá trị tiền | Item khác giá trị/kích thước | Product outcome và cost of delay |
| Không tính onboarding | Business case quá lạc quan | Kịch bản theo thời gian |
| Xóa blocked item khỏi WIP | Dashboard đẹp giả tạo | Giữ dữ liệu trung thực |
| Chỉ nhìn completed items | Bỏ item già đang kẹt | Xem work item age |
| Tuyên bố thành công từ hai kỳ ngắn | Bỏ qua biến gây nhiễu | Ghi giới hạn và quan sát tiếp |
| Tăng cuộc họp status liên team | Giảm thời gian làm sâu | Họp đúng điểm cần quyết |
| Thêm manager chỉ để có tầng báo cáo | Không giải quyết nguyên nhân | Chức năng và outcome đo được |
| Chỉ đo tốc độ, bỏ lỗi | Thúc đẩy giao phần mềm không an toàn | DoD, quality, recovery |
| Cấu trúc tổ chức không có review trigger | Giữ chi phí dù nhu cầu đổi | Decision log, thử nghiệm và điểm xem lại |

## 21. Bài thực hành có đáp án định hướng

### 21.1. Bài A – Tính số cặp giao tiếp (10 phút)

Một sản phẩm tăng từ **4 nhóm lên 7 nhóm**.

1. Tính số cặp nhóm tiềm năng trước/sau.
2. Tính phần tăng tuyệt đối và tỷ lệ phần trăm.
3. Giải thích vì sao không thể suy số cuộc họp tăng tương ứng.
4. Nêu ba loại bằng chứng cần thu.

**Đáp án:** P(4) = **6**, P(7) = **21**, tăng **15 cặp**, tương đương **250% trên số cặp ban đầu**. Đó là **cơ hội kết nối**, không phải quan sát; cần dependency edges, blocked time và integration/rework data.

### 21.2. Bài B – Person-hours và chờ quyết định (10 phút)

Có cuộc họp 8 người, 45 phút. Sau đó một story chờ approval hai ngày làm việc; người duyệt thực sự đọc 15 phút.

1. Công sức họp?
2. Công sức duyệt?
3. Có được lấy hai ngày chờ nhân tám người để báo lãng phí?
4. Khi nào approval làm lùi ngày giao?

**Đáp án:** Họp **8 × 45/60 = 6 person-hours**; duyệt **15/60 = 0,25 person-hour**. Hai ngày là **elapsed wait**, không tự thành person-days bị lãng phí. Nó lùi ngày giao nếu nằm trên đường găng và không thể chồng lấn.

### 21.3. Bài C – Đường găng (15 phút)

A = 1 ngày; B = 3 ngày sau A; C = 2 ngày sau A; D = 2 ngày sau B và C; E = 1 ngày sau D.

1. Tổng thời gian theo sơ đồ?
2. Hai approval 1 ngày mỗi cái, nối tiếp sau E: tổng mới?
3. Một approval chạy song song E, approval còn lại sau cả E và duyệt đầu: tổng mới?
4. Vì sao không cộng B + C?

**Đáp án:** **7 ngày**, **9 ngày**, **8 ngày** theo các giả định đã nêu. B/C song song nên lấy **max(3,2)**.

### 21.4. Bài D – Hàng chờ review (10 phút)

Có 8 yêu cầu review đến mỗi tuần, xử lý 6 yêu cầu mỗi tuần. Điều kiện không đổi.

1. Tồn tăng bao nhiêu sau bốn tuần?
2. Nếu thêm team gửi request nhưng capacity review không đổi thì sao?
3. Có suy được thời gian hoàn tất từng request không?
4. Nêu hai thử nghiệm cải tiến.

**Đáp án:** Tăng khoảng **(8−6)×4 = 8 yêu cầu**. Tồn tăng nhanh hơn nếu đầu vào tăng; không đủ dữ liệu suy thời gian từng yêu cầu. Có thể thử **tự động hóa contract tests, self-service, ủy quyền rủi ro thấp, WIP policy** tùy nguyên nhân.

### 21.5. Bài E – Business case thêm team (15 phút)

Hai team có 10 Developers và throughput 12 item/tháng. Thêm 5 Developers với giả định +6 item/tháng công suất, −2 do phối hợp và −1 do làm lại.

1. Tính throughput mới.
2. Tính phần trăm tăng người và throughput.
3. Nếu mỗi người có chi phí đầy đủ giả định 60 triệu/tháng, chi phí tăng?
4. Có kết luận ngay phương án tốt/xấu được không?
5. Cần outcome/quality nào?

**Đáp án:** **15 item/tháng**, số người tăng **50%**, throughput tăng **25%**, chi phí nhân sự giả định tăng **300 triệu/tháng**. Không đủ quyết định vì giả định chưa kiểm, item khác giá trị, còn onboarding và Product Goal.

### 21.6. Bài F – Cấp quản lý mới nên duyệt điều gì? (15 phút)

Xét:
- Đổi nhãn giao diện.
- Sửa API contract dùng chung.
- Đổi quyền xem dữ liệu cá nhân.
- Đầu tư hạ tầng vượt ngân sách.

Hãy đề xuất **ai có quyền quyết, ai phải tham vấn, khi nào cần phê duyệt độc lập và điều kiện escalation**.

**Gợi ý:** Việc ít rủi ro có thể ủy quyền trong guardrails. Quyền dữ liệu hoặc ngân sách lớn cần cơ chế đúng thẩm quyền. Không thêm manager để ký mọi PR.

### 21.7. Bài G – Vẽ ma trận phụ thuộc (20 phút)

Với bốn nhóm UI, Enrollment, Notifications, Platform:
1. Chọn ba story gần nhất (hoặc dữ liệu giả).
2. Vẽ cạnh phụ thuộc thật, không phải mọi cặp tiềm năng.
3. Ghi blocked time, reason và contract.
4. Chọn cạnh có thể giảm bằng test, tự phục vụ hoặc đổi boundary.
5. Chọn một rủi ro không được bỏ qua.
6. Đề xuất thử nghiệm nhỏ và thời hạn xem lại.

**Đáp án định hướng:** Ma trận có **giải thích cho mỗi cạnh quan trọng**, không chỉ một bảng điểm không nguồn.

### 21.8. Bài H – Thử nghiệm cấu trúc tổ chức (20 phút)

CFD cho thấy Review band tăng, cycle time p85 dài hơn, throughput không tăng. Lãnh đạo đề xuất thêm nhóm QA và một manager.

Viết đề xuất gồm:
- Product Goal bị ảnh hưởng.
- Ba nguyên nhân có thể kiểm chứng.
- Baseline WIP, age, blocked time, quality.
- Một thử nghiệm cải tiến trước tái tổ chức.
- Guardrails.
- Điều kiện thêm team/manager và điều kiện không thêm.
- Owner và ngày quyết định tiếp.

**Gợi ý:** phân biệt thiếu chuyên môn với nghẽn do workflow hoặc test. Thêm người chỉ hữu ích khi giải đúng hạn chế thực tế.

### 21.9. Bài I – So sánh phương án ngắn gọn (15 phút)

Lập bảng hai phương án:
- A: Team Integration mới, mọi story qua approval.
- B: Contract tests và CI chung, teams sở hữu Done tích hợp.

Hãy so:
- Dependency mới/giảm.
- Thời gian chờ dự kiến.
- Chi phí học và vận hành.
- Rủi ro dữ liệu.
- Khả năng làm việc độc lập.
- Phương pháp kiểm chứng.
- Điều kiện dừng/đảo quyết định.

Không dùng số cặp giao tiếp làm lý do duy nhất chọn B.

### 21.10. Bài J – Trình bày kết luận với stakeholder (15 phút)

Soạn một memo ngắn trả lời:
- Chúng ta biết gì và chưa biết gì?
- Vì sao local team throughput khác product throughput?
- Một nhóm/tầng mới sẽ giải quyết vấn đề nào?
- Những handoff/approval nào mới có thể xuất hiện?
- Lợi ích và cost of delay nào chưa được định lượng?
- Thử nghiệm ít đảo ngược nào nên làm trước?
- Dữ liệu nào sẽ quyết định giữ/đổi đề xuất?

### 21.11. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Chi phí phối hợp** | Trộn mọi chi phí thành một số giờ | Phân biệt person-hours, wait, rework | Hiểu critical path và giá trị bảo vệ rủi ro |
| **Kết nối nhóm** | Coi P(n) là số cuộc họp | Tính P(n) và giới hạn đúng | Vẽ dependency graph thật |
| **Flow** | Chỉ xem team velocity | Đo product throughput, WIP, cycle time | Kết hợp age, quality và outcome |
| **Quản lý** | Mặc định cần ký mọi thay đổi | Quyền quyết theo mức rủi ro | Giảm queue, tăng tự chủ, kiểm chứng lợi ích |
| **Cơ cấu** | Thêm người theo cảm giác | So phương án ownership/platform/automation | Thử có điều kiện, tính chi phí chuyển đổi |
| **Agile** | Chỉ tăng output task | Gắn DoD và Product Goal | Thích ứng trên bằng chứng, giao giá trị bền vững |

## 22. Biểu mẫu dùng ngay

### 22.1. Phiếu ghi một phụ thuộc liên team

~~~text
Product Goal / hạng mục:
Team A / Team B:
Đầu ra cần từ team khác:
Loại phụ thuộc: tuần tự / shared / hai chiều / đồng bộ:
Nguồn hợp đồng và người sở hữu:
Started/Finished theo workflow:
Thời điểm bắt đầu/thoát blocked:
Elapsed wait và bối cảnh giờ làm:
Person-hours phối hợp trực tiếp (nếu cần):
Rework hoặc lỗi tích hợp:
Ai quyết định cuối:
Cơ chế escalation:
Rủi ro nếu bỏ bước review:
Đề xuất giảm phụ thuộc:
Điều kiện kiểm chứng:
~~~

### 22.2. Bảng so sánh thay đổi tổ chức

~~~text
Vấn đề và Product Goal:
Dữ liệu flow/quality hiện tại:
Ranh giới sản phẩm và DoD:
Nút thắt/queue quan sát được:
Giả thuyết nguyên nhân:
Phương án A:
Phương án B:
Phương án C (nếu cần):
Cho từng phương án:
- Lợi ích dự kiến
- Handoff/decision layers tăng hoặc giảm
- Ranh giới team và contract
- Chi phí chuyển đổi/onboarding
- Chi phí vận hành dài hạn
- Guardrails dữ liệu, quyền, chất lượng
- Điều chưa biết
- Cách thử và mốc xem lại
Decision owner:
~~~

### 22.3. Phiếu quyền quyết định

~~~text
Loại quyết định:
Phạm vi ảnh hưởng:
Người trực tiếp thực hiện:
Người có quyền quyết cuối:
Các bên bắt buộc tham vấn:
Những người chỉ cần thông báo:
Ngưỡng cần review độc lập:
Quy tắc ủy quyền:
Thời điểm cần quyết:
Backup khi người quyết vắng:
Cơ chế escalation:
Decision log / ADR:
Điều kiện xem lại:
~~~

### 22.4. Phiếu thử nghiệm giảm chi phí phối hợp

~~~text
Experiment ID:
Product Goal và công việc thuộc phạm vi:
Baseline: WIP, throughput, cycle time, age:
Baseline: blocked wait, handoff, decision latency:
Baseline: integration defects/incident:
Giả thuyết:
Can thiệp nhỏ:
Owner và nhóm tham gia:
Ngày bắt đầu/kết thúc dự kiến:
Những biến gây nhiễu cần ghi:
Guardrails và điều kiện dừng:
Dữ liệu sau thử, cỡ mẫu, giới hạn:
Quyết định giữ/chỉnh/dừng/mở rộng:
Mốc kiểm lại:
~~~

### 22.5. Phiếu hậu kiểm sau thay đổi cơ cấu

~~~text
Cấu trúc trước và sau:
Mục tiêu của thay đổi:
Ngày áp dụng và chi phí chuyển đổi:
Team ownership và dependencies mới:
Approval steps và decision rights:
Throughput, WIP, cycle time distribution:
Work item age và blocked time:
Integration/quality incidents:
Feedback người dùng và outcome:
Phản hồi team về tính bền vững:
Những thay đổi khác trong cùng kỳ:
Điều có thể kết luận và chưa thể kết luận:
Giữ/điều chỉnh/đảo quyết định:
~~~

Biểu mẫu là **công cụ học và đưa ra quyết định**, không phải thủ tục bắt buộc của Scrum. Chỉ dùng mức chi tiết tương xứng với mức tác động của lựa chọn.

## 23. Checklist trước khi thêm nhóm hoặc tầng quản lý

**Hiểu vấn đề:**

- [ ] Product Goal và giá trị người dùng đang bị chậm được nêu rõ.
- [ ] Phân biệt output từng nhóm với Increment thực sự Done.
- [ ] Work item, Started, Finished và DoD được định nghĩa nhất quán.
- [ ] Có dữ liệu WIP, throughput, cycle time và work item age.
- [ ] Đã quan sát các hàng chờ review, integration, approval và rework.
- [ ] Đã phân biệt thiếu năng lực thực thi với nút thắt do workflow.
- [ ] Các giả định quan trọng đã được ghi riêng với dữ kiện quan sát.

**Đánh giá chi phí:**

- [ ] n(n−1)/2 chỉ được dùng như số cặp kết nối tiềm năng.
- [ ] Có dependency graph/ma trận phụ thuộc thực tế.
- [ ] Phân biệt person-hours và elapsed wait.
- [ ] Không cộng các hoạt động song song thành đường găng giả.
- [ ] Giá trị giảm rủi ro của review được xem cùng chi phí chờ.
- [ ] Chi phí onboarding, công cụ, vận hành và chuyển đổi được xem xét.
- [ ] Throughput hoặc story points không bị coi là giá trị tiền tự thân.

**Thiết kế nhóm/quản trị:**

- [ ] Team mới có dòng giá trị/capability và ownership rõ.
- [ ] Không tạo cổng mới cho mọi story nếu có thể tự phục vụ.
- [ ] API/data contract và tích hợp đủ khả năng kiểm chứng.
- [ ] Có thể dùng collaboration tạm thay cho tầng cố định khi phù hợp.
- [ ] Tầng quản lý mới có chức năng và outcome khác biệt.
- [ ] Quyết định rủi ro thấp được ủy quyền trong guardrails phù hợp.
- [ ] Những kiểm soát bắt buộc về dữ liệu, bảo mật và an toàn được giữ.
- [ ] Có decision owner và escalation khi bất đồng liên team.
- [ ] Nhiều Scrum Teams cùng sản phẩm thống nhất Product Goal, backlog và DoD.
- [ ] CI, contract tests, pairing và WIP policy được cân nhắc trước tăng approval.

**Kiểm chứng và cải tiến:**

- [ ] Đã so ít nhất hai phương án, không chỉ “thêm người hay không”.
- [ ] Có baseline, giả thuyết, cách đo và thời hạn thử.
- [ ] Guardrails về chất lượng, người dùng và sức làm việc bền vững rõ.
- [ ] Có điều kiện giữ, điều chỉnh hoặc đảo quyết định.
- [ ] Không tuyên bố quan hệ nhân quả từ một bảng trước/sau rất ngắn.
- [ ] Kết quả được xem theo **product flow, quality và outcome**, không chỉ KPI của từng team.

**Kết luận:** Thêm nhóm hoặc tầng quản lý là **một quyết định thiết kế hệ thống làm việc**. Lợi ích có thể đến từ tăng chuyên môn, mở luồng giá trị độc lập, phân quyền và bảo vệ rủi ro. Chi phí có thể đến từ bàn giao, hàng chờ, quyết định nối tiếp, tích hợp và làm lại. Cách đánh giá có trách nhiệm là **vẽ phụ thuộc thật, tách công sức khỏi thời gian chờ, nhìn critical path và flow metrics, so các phương án, rồi thử thay đổi ít đảo ngược với guardrails**. Khi lấy Product Goal, chất lượng và phản hồi sớm làm chuẩn, nhiều nhóm có thể cộng tác để giao phần mềm tốt hơn mà không biến chính sự phối hợp thành nút thắt mới.
