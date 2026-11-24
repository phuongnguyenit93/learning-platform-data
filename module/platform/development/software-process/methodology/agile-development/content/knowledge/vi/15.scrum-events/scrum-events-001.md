# Sprint như nhịp chứa các hoạt động và sự kiện Scrum

> **Chương:** Sự kiện Scrum  
> **Học phần:** **AGILE_DEVELOPMENT** — tìm hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc phù hợp với bối cảnh.

Một nhóm có thể họp mỗi sáng, lên kế hoạch hai tuần một lần và trình diễn chức năng mới vào cuối kỳ, nhưng chưa chắc đã vận dụng Scrum hiệu quả. Điều cốt lõi không phải số cuộc họp mà là **một nhịp làm việc có mục tiêu, tạo Increment sử dụng được, kiểm tra bằng chứng thực tế và thích ứng**.

Trong **Scrum Guide 2020**, **Sprint** là “nhịp tim” của Scrum, nơi ý tưởng được biến thành giá trị. Sprint đồng thời là **một sự kiện có giới hạn thời gian** và là **khung bao chứa các sự kiện Scrum còn lại**: Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective. Những hoạt động tạo sản phẩm như refinement, thiết kế, lập trình, kiểm thử, tích hợp và phát hành cũng diễn ra trong Sprint nhưng **không tự động trở thành sự kiện Scrum chính thức**.

Nắm được cấu trúc này giúp nhóm trả lời đúng những câu hỏi rất thực tế: Sprint bắt đầu và kết thúc khi nào? Vì sao cần Sprint Goal? Khi nào nên phát hành phần mềm? Phải làm gì nếu phát hiện lỗi hoặc yêu cầu mới giữa Sprint? Tại sao Sprint Review khác Sprint Retrospective? Bài học sẽ lần lượt giải thích, rồi nối toàn bộ thành một ví dụ hai tuần.

## 1. Kết quả học tập

Sau khi học, bạn có thể:

1. Giải thích Sprint là **sự kiện bao trùm**, có thời lượng cố định **không quá một tháng** và diễn ra liên tiếp.
2. Phân biệt **năm sự kiện Scrum chính thức** với những hoạt động kỹ thuật, cộng tác và làm rõ backlog diễn ra bên trong Sprint.
3. Nêu đúng mục đích, người tham gia cốt lõi, thời điểm, timebox và kết quả mong đợi của Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective.
4. Giải thích quan hệ giữa **Product Backlog – Product Goal**, **Sprint Backlog – Sprint Goal**, **Increment – Definition of Done**.
5. Vận dụng nhịp Sprint để giao phần mềm tăng dần, nhận phản hồi sớm, duy trì chất lượng và điều chỉnh kế hoạch khi có dữ liệu mới.
6. Thiết kế một lịch Sprint minh họa có tính tới công việc thật, không biến Scrum thành chuỗi cuộc họp hoặc cam kết số lượng ticket cứng.

## 2. Sprint là gì trong Scrum?

### 2.1. Nhịp đều đặn để biến ý tưởng thành giá trị

**Sprint** là một sự kiện có **timebox cố định, dài một tháng hoặc ngắn hơn**, được dùng nhất quán để tạo nhịp. Khi một Sprint kết thúc, **Sprint tiếp theo bắt đầu ngay**, không cần một giai đoạn riêng “đợi duyệt Sprint cũ” hay “nghỉ giữa các Sprint” như một bước quy trình bắt buộc.

Trong Sprint, Scrum Team làm tất cả công việc cần thiết để tiến tới Product Goal, từ lập kế hoạch, phát triển, kiểm tra, tương tác với bên liên quan tới cải tiến cách làm. Nhịp Sprint tạo các cơ hội **minh bạch – kiểm tra – thích ứng** liên tục thay vì chỉ đánh giá dự án khi đã gần hoàn thành.

Một Sprint có thể kéo dài một tuần, hai tuần, ba tuần hoặc một tháng, tùy hoàn cảnh. Scrum Guide chỉ định **giới hạn trên một tháng**, không bắt buộc mọi nhóm phải dùng hai tuần. Độ dài ổn định giúp tạo tính nhất quán; nếu cần thay đổi độ dài, nhóm nên xem xét lý do và tác động tới nhịp kiểm tra thay vì đổi liên tục theo cảm tính.

### 2.2. Vì sao Sprint không chỉ là “hạn chót”?

Nếu chỉ nhìn Sprint là một khung thời gian để đóng ticket, nhóm dễ có các hành vi:

- Nhận nhiều hạng mục vào đầu kỳ và đánh dấu “gần xong” ở cuối kỳ.
- Đưa kiểm thử, sửa lỗi hoặc tích hợp sang Sprint sau để số ticket hoàn tất trông đẹp hơn.
- Chỉ trình diễn cho stakeholder khi toàn bộ tính năng lớn đã làm xong.
- Ngừng lắng nghe phản hồi giữa Sprint vì “đã khóa kế hoạch”.
- Coi Sprint Review là buổi nghiệm thu hành chính và Retrospective là một cuộc họp tùy chọn.

**Sprint tốt phải tạo ra cơ hội học và giá trị.** Nó có mục tiêu ngắn hạn, kế hoạch có thể thích ứng, một hoặc nhiều Increment đáp ứng Definition of Done và những hoạt động kiểm tra kết quả để điều chỉnh bước tiếp theo.

### 2.3. Có bao nhiêu sự kiện Scrum?

Scrum có **năm sự kiện**: **Sprint** và **bốn sự kiện bên trong Sprint**. Đây không phải “bốn cuộc họp cộng thêm một khoảng thời gian” theo cách hiểu tùy tiện, bởi Sprint cũng có mục đích, giới hạn và quy tắc rõ.

| Sự kiện | Vị trí trong nhịp | Chức năng chính |
| --- | --- | --- |
| **Sprint** | Bao trùm toàn bộ nhịp làm việc | Biến ý tưởng thành giá trị trong một khoảng thời gian đủ ngắn để kiểm soát rủi ro. |
| **Sprint Planning** | Mở đầu Sprint | Trả lời vì sao Sprint có giá trị, làm gì và sẽ bắt đầu làm như thế nào. |
| **Daily Scrum** | Mỗi ngày làm việc của Sprint | Developers kiểm tra tiến độ tới Sprint Goal và điều chỉnh Sprint Backlog khi cần. |
| **Sprint Review** | Gần cuối Sprint | Scrum Team và stakeholder kiểm tra kết quả Sprint và xác định cách thích ứng sản phẩm. |
| **Sprint Retrospective** | Kết thúc Sprint | Scrum Team kiểm tra cách làm và lên kế hoạch nâng chất lượng, hiệu quả. |

Thứ tự quan trọng: **Sprint Review diễn ra trước Sprint Retrospective**, và **Sprint Retrospective kết thúc Sprint**. Một Sprint mới không cần chờ biên bản được ký duyệt từ Review.

## 3. Bức tranh toàn cảnh: những gì diễn ra bên trong Sprint

~~~mermaid
flowchart TD
    A["Product Goal và Product Backlog có thứ tự"] --> B["Sprint bắt đầu"]
    B --> C["Sprint Planning: Vì sao? Cái gì? Làm thế nào?"]
    C --> D["Sprint Goal và Sprint Backlog"]
    D --> E["Làm việc hướng tới Sprint Goal"]
    E --> F["Daily Scrum: kiểm tra và điều chỉnh"]
    F --> E
    E --> G["Increment đáp ứng Definition of Done"]
    G --> H["Có thể phát hành giá trị trong Sprint"]
    G --> I["Sprint Review: kiểm tra kết quả và bối cảnh"]
    I --> J["Sprint Retrospective: cải tiến cách làm"]
    J --> K["Sprint kết thúc"]
    K --> L["Sprint kế tiếp bắt đầu ngay"]
    L --> C
    I -. "Phản hồi, điều chỉnh thứ tự" .-> A
~~~

Sơ đồ làm nổi bật luồng chính nhưng **không phải quy định chỉ được hoàn tất Increment sau Daily Scrum cuối cùng**. Developers có thể tạo Increment bất cứ khi nào một Product Backlog Item đạt Definition of Done; sản phẩm có thể được phát hành nhiều lần trong cùng Sprint. Refinement, kiểm thử, trao đổi với khách hàng và gỡ trở ngại diễn ra song song với công việc tạo Increment.

### 3.1. Các hoạt động trong Sprint nhưng không phải sự kiện chính thức

Những việc sau rất quan trọng, song Scrum Guide **không gọi chúng là sự kiện Scrum riêng**:

- **Product Backlog refinement:** chia nhỏ, làm rõ và bổ sung chi tiết cho các mục backlog; là hoạt động liên tục khi cần.
- **Discovery:** quan sát người dùng, kiểm chứng giả định và làm prototype/thử nghiệm có giới hạn.
- **Thiết kế, lập trình, kiểm thử:** xây lát cắt dọc hoàn chỉnh, xử lý trường hợp biên và lỗi hồi quy.
- **Code review, pair programming, continuous integration, refactoring:** thực hành kỹ thuật có thể dùng theo bối cảnh.
- **Họp ngắn giải quyết vấn đề:** làm rõ nghiệp vụ, phối hợp xử lý phụ thuộc, lập kế hoạch kỹ thuật chi tiết.
- **Triển khai, phát hành, giám sát, hỗ trợ vận hành:** đưa giá trị tới người dùng và theo dõi hành vi thực tế.

Các hoạt động này có thể xuất hiện nhiều lần hoặc vào những thời điểm khác nhau trong Sprint. Không cần gọi mọi cuộc trao đổi 15 phút là một sự kiện mới của Scrum; đồng thời không được coi chúng là “việc ngoài Sprint” nên không tính tới năng lực.

### 3.2. Hai loại phản hồi cùng tồn tại

**Phản hồi ngắn ở cấp kỹ thuật:** kiểm thử tự động, CI, review, quan sát log và xử lý lỗi giúp phát hiện vấn đề trong vài phút hoặc vài giờ.

**Phản hồi ở cấp sản phẩm và cách làm:** Increment, dữ liệu sử dụng, Sprint Review và Retrospective giúp xem liệu nhóm tạo đúng giá trị và cộng tác hiệu quả không.

Nhịp Sprint có ích khi **liên kết các vòng phản hồi đó**. Chờ đến Sprint Review mới tích hợp mã hoặc mới kiểm tra chất lượng là lãng phí cơ hội học sớm.

## 4. Các giới hạn của Sprint cần giữ đúng

Scrum Guide 2020 nêu những ràng buộc cốt lõi trong Sprint:

1. **Không thực hiện thay đổi làm nguy hiểm Sprint Goal.**
2. **Chất lượng không được giảm.**
3. **Product Backlog được làm rõ khi cần.**
4. **Phạm vi có thể được làm rõ và thương lượng lại với Product Owner khi học thêm.**

Những điều này giúp nhóm thích ứng mà vẫn giữ định hướng. Chúng không có nghĩa mọi story đã chọn từ đầu bất di bất dịch, cũng không cho phép thêm yêu cầu vô hạn chỉ vì Agile đón nhận thay đổi.

### 4.1. Sprint Goal được bảo vệ, phạm vi có thể linh hoạt

Giả sử Sprint Goal là:

> “Khách có thể đặt một lịch tư vấn hợp lệ và nhận xác nhận rõ ràng.”

Khi làm việc, nhóm phát hiện kịch bản mạng timeout có thể tạo lịch trùng. Điều cần giữ là **đặt lịch hợp lệ**. Developers có thể cùng Product Owner làm rõ phạm vi, hoãn một mục phụ không cần cho mục tiêu, đồng thời bổ sung xử lý và kiểm thử cần thiết.

Ngược lại, nếu một bên liên quan muốn chen chức năng phân tích doanh thu không liên quan, Product Owner cần xem thứ tự Product Backlog và tác động tới mục tiêu. Scrum không coi thay đổi ưu tiên mới là lý do tự động phá Sprint Goal.

### 4.2. Chất lượng không phải chỗ để bù thời gian

Một Increment cần đáp ứng Definition of Done (DoD) của sản phẩm. Nếu DoD yêu cầu kiểm thử, bảo mật, tích hợp hoặc tiêu chuẩn vận hành liên quan, nhóm không thể bỏ phần đó chỉ để đánh dấu story “Done” trước khi Sprint kết thúc.

Giảm phạm vi **có thể** là quyết định tốt. Giao một luồng đặt lịch đúng và an toàn trước khi thêm bộ lọc nâng cao là ví dụ. Nhưng bỏ kiểm soát chống lịch trùng ở hệ thống lưu trữ để giao sớm **không phải** chia nhỏ có trách nhiệm.

### 4.3. Sprint bị hủy khi nào?

Một Sprint có thể được **hủy nếu Sprint Goal trở nên lỗi thời**. Theo Scrum Guide, **chỉ Product Owner có thẩm quyền hủy Sprint**; điều đó không có nghĩa Product Owner nên làm vậy mỗi khi có ý tưởng mới hoặc một story bị trễ.

Ví dụ, nhóm đang làm một tính năng dựa trên quy định cũ nhưng quy định mới khiến Sprint Goal không còn giá trị. Product Owner có thể xem xét hủy Sprint và lập lại định hướng. Đây là quyết định có chi phí; thường cần trao đổi rõ với các bên liên quan.

**Không nên hủy Sprint** chỉ vì một ước lượng sai, một story phức tạp hơn dự kiến hoặc cần thay đổi thứ tự công việc trong khi Sprint Goal vẫn có ý nghĩa. Những tình huống đó nên được xử lý bằng minh bạch, điều chỉnh kế hoạch và thương lượng phạm vi.

## 5. Sprint Planning — mở đầu Sprint bằng mục đích và kế hoạch

**Sprint Planning** khởi động Sprint bằng cách đặt nền tảng cho công việc của toàn bộ Scrum Team. Sự kiện có ba chủ đề theo Scrum Guide:

1. **Why — Vì sao Sprint này có giá trị?**
2. **What — Có thể hoàn tất những gì trong Sprint này?**
3. **How — Công việc được chọn sẽ được thực hiện như thế nào?**

### 5.1. Ai tham gia, kết quả là gì?

**Toàn bộ Scrum Team** tham gia: Product Owner, Scrum Master và Developers. Nhóm có thể mời người khác tham gia để cung cấp lời khuyên cần thiết. Product Owner bảo đảm người tham gia sẵn sàng trao đổi về những Product Backlog Item quan trọng và liên hệ của chúng tới Product Goal.

Kết quả Sprint Planning là **Sprint Backlog**, bao gồm:

- **Sprint Goal:** tại sao Sprint có giá trị.
- **Các Product Backlog Item được chọn:** dự kiến tạo gì trong Sprint.
- **Kế hoạch thực hiện có thể hành động:** cách Developers định bắt đầu chuyển các mục thành Increment.

Scrum Team tạo Sprint Goal trong Sprint Planning; **Developers** lựa chọn lượng công việc có thể thực hiện và quyết định cách thực hiện công việc đó. Sprint Backlog do **Developers** tạo và cập nhật trong Sprint; nó không phải một tài liệu quản lý áp đặt rồi khóa lại.

### 5.2. Timebox và ví dụ

Sprint Planning có timebox **tối đa 8 giờ cho Sprint một tháng**; với Sprint ngắn hơn, sự kiện thường ngắn hơn. Con số 8 giờ là **giới hạn**, không phải thời lượng bắt buộc phải họp đủ.

**Ví dụ Sprint hai tuần:**

| Chủ đề | Câu hỏi cụ thể | Kết quả mong đợi |
| --- | --- | --- |
| Why | Bằng chứng nào cho thấy người dùng cần xác nhận đặt lịch rõ hơn? | Sprint Goal gắn với kết quả khách hàng. |
| What | Những lát cắt UI–API–dữ liệu nào đủ giá trị? Năng lực thực tế và phụ thuộc? | Backlog Item được chọn theo mục tiêu, có dự báo khả thi. |
| How | Kiểm thử trường hợp gửi lặp thế nào? Ai phối hợp với API đối tác? | Kế hoạch ban đầu, cách kiểm chứng chất lượng và phụ thuộc nổi bật. |

**Phản mẫu:** Sprint Planning chỉ gồm Product Owner đọc danh sách 30 ticket, hỏi “ai nhận việc nào?” rồi yêu cầu tất cả ký cam kết số lượng story. Cách đó làm yếu mục tiêu chung, giảm khả năng Developers tự quản lý và tăng động cơ che trở ngại.

### 5.3. Sprint Goal không phải một danh sách nhiều mục tiêu cạnh tranh

Một câu như “làm tìm kiếm, thanh toán, báo cáo, đổi màu giao diện và nâng cấp runtime” là **danh sách công việc**, không tự động thành Sprint Goal rõ ràng.

Mục tiêu tốt hơn:

> “Người dùng hoàn tất một đơn đặt lịch hợp lệ từ màn hình chọn giờ đến xác nhận mà không tạo lịch trùng.”

Sprint Goal tạo sự thống nhất để nhóm chọn việc và thương lượng điều gì có thể hoãn khi phát hiện bất định mới. Không có quy tắc mọi Sprint Goal phải đo bằng một KPI duy nhất, nhưng nhóm cần biết **kết quả nào là trọng tâm chung**.

## 6. Trong Sprint — làm việc thật, tạo Increment và kiểm tra liên tục

Khoảng giữa Sprint Planning và Sprint Review **không phải vùng trống chỉ chứa Daily Scrum**. Đây là thời gian nhóm làm phần lớn công việc phát triển, cộng tác, xử lý vấn đề và tạo Increment.

### 6.1. Một lát cắt dọc đi qua nhiều hoạt động

Để người dùng đặt được lịch, nhóm có thể cần:

1. Thảo luận user story và tiêu chí chấp nhận với người hiểu nghiệp vụ.
2. Thiết kế trải nghiệm chọn giờ trống và trạng thái xác nhận.
3. Thực hiện API và ràng buộc dữ liệu tránh đặt trùng.
4. Viết kiểm thử đơn vị, tích hợp và trường hợp cạnh tranh đồng thời.
5. Review code, tích hợp qua CI và kiểm tra trên môi trường phù hợp.
6. Xác nhận hạng mục đã đạt DoD trước khi gọi là Done.
7. Phát hành có kiểm soát hoặc đưa Increment sẵn sàng phát hành theo chiến lược sản phẩm.
8. Quan sát phản hồi người dùng và cập nhật giả định cho các bước tiếp theo.

Đó là công việc tạo sản phẩm, không phải các sự kiện Scrum bổ sung. Chúng có thể song song hoặc lặp lại tùy khả năng, phụ thuộc và WIP.

### 6.2. Increment có thể xuất hiện giữa Sprint

Theo Scrum Guide, một **Increment** được hình thành khi một Product Backlog Item đáp ứng DoD và tích hợp với các Increment trước đó; những Increment này phải hoạt động cùng nhau. **Có thể tạo nhiều Increment trong cùng Sprint**.

**Sprint Review không phải cổng cho phép phát hành.** Increment có thể được giao cho stakeholder trước khi Sprint kết thúc nếu điều kiện chất lượng và quy trình phát hành đã được đáp ứng. Với nhiều sản phẩm, CI/CD, rollout giới hạn và giám sát giúp rút ngắn thời gian từ hoàn tất đến phản hồi. Nhưng Scrum **không bắt buộc** mỗi đội phải triển khai production hằng ngày.

**Phân biệt bốn mốc dễ nhầm:**

| Mốc | Đặc điểm |
| --- | --- |
| **Hoàn thành một tác vụ kỹ thuật** | Một phần code, thiết kế hoặc kiểm thử đã được thực hiện; chưa chứng minh hạng mục Done. |
| **Product Backlog Item đạt DoD** | Hành vi đáp ứng chuẩn chất lượng và tích hợp, góp phần tạo Increment. |
| **Triển khai (deploy)** | Phần mềm được đưa lên một môi trường nhất định; không bảo đảm đã mở cho người dùng. |
| **Phát hành (release)** | Giá trị được cung cấp tới đối tượng sử dụng theo quyết định và kiểm soát cần thiết. |

Đừng đợi Sprint Review mới kiểm thử tích hợp, cũng đừng gọi một prototype chưa đạt DoD là Increment đã hoàn tất.

## 7. Daily Scrum — điểm kiểm tra ngắn mỗi ngày làm việc

**Daily Scrum** là sự kiện **15 phút** dành cho **Developers** của Scrum Team, tổ chức **mỗi ngày làm việc của Sprint**, thường ở cùng thời gian và địa điểm để giảm phức tạp. Mục đích là **kiểm tra tiến độ tới Sprint Goal và điều chỉnh Sprint Backlog khi cần**, tạo kế hoạch có thể hành động cho ngày làm việc tiếp theo.

### 7.1. Daily Scrum không phải cuộc họp báo cáo lên quản lý

Người tham gia cốt lõi là **Developers**. Nếu Product Owner hoặc Scrum Master trực tiếp làm một hạng mục trong Sprint Backlog, họ có thể tham gia với tư cách **Developers**. Scrum Master không bắt buộc phải đứng điều phối hoặc yêu cầu từng người báo cáo ba câu cố định.

Hình thức được Developers quyết định, miễn là sự kiện tạo **tiến bộ hướng Sprint Goal**. Nhóm có thể đi từ bảng công việc, từ mục gần Done hoặc từ trở ngại quan trọng nhất.

### 7.2. Ví dụ một Daily Scrum hữu ích

~~~text
Sprint Goal: Khách đặt một lịch hợp lệ và nhận kết quả rõ ràng.

Developer A: Luồng xác nhận đã tích hợp, nhưng test gửi hai request cùng lúc lỗi.
Developer B: Tôi có thể hỗ trợ kiểm tra giao dịch dữ liệu trước khi kéo việc mới.
Developer C: API sandbox đang timeout; tôi ghi bằng chứng và thử lại có kiểm soát.
Nhóm:        Ưu tiên giải quyết hai điểm chặn. Chưa mở thêm bộ lọc địa điểm.
             Nếu phụ thuộc tiếp tục ảnh hưởng Sprint Goal, trao đổi với PO.
~~~

Đây không phải cuộc họp báo cáo chi tiết giải pháp. Nhóm có thể tổ chức một buổi trao đổi kỹ thuật **sau Daily Scrum** với đúng người cần tham gia. Daily Scrum nên ngắn và tập trung vào điều chỉnh kế hoạch.

### 7.3. Các tín hiệu giúp Daily Scrum có ích

- Mỗi người hiểu Sprint Goal và biết việc nào ảnh hưởng nó.
- Những việc gần Done được ưu tiên hoàn tất thay vì mở thêm nhiều việc.
- Các hạng mục bị chặn được nêu sớm, có bước tháo gỡ.
- Sprint Backlog phản ánh kế hoạch Developers thực sự đang dùng.
- Mức độ chi tiết phù hợp, không biến 15 phút thành buổi điều tra lỗi.

**Lưu ý:** Daily Scrum là một trong những cơ hội kiểm tra và thích ứng. Developers **không bị giới hạn chỉ được điều chỉnh kế hoạch mỗi ngày một lần**; họ thường phải phối hợp và điều chỉnh công việc cả ngày khi có thông tin mới.

## 8. Sprint Review — xem kết quả Sprint và thích ứng hướng sản phẩm

**Sprint Review** diễn ra gần cuối Sprint. Mục đích chính là **kiểm tra kết quả Sprint và xác định những thích ứng tiếp theo**. Scrum Team trình bày kết quả công việc cho các stakeholder quan trọng; cùng trao đổi về tiến độ hướng tới Product Goal và những thay đổi của môi trường.

### 8.1. Không chỉ là demo hoặc nghiệm thu

Một Sprint Review hiệu quả nên có:

1. **Increment thật** hoặc các kết quả đã đạt DoD, có thể kiểm chứng hành vi.
2. **Thông tin về Product Goal:** tính năng mới giúp người dùng được gì, kết quả nào chưa rõ?
3. **Phản hồi từ stakeholder:** nhu cầu, hành vi thị trường, nghĩa vụ và rủi ro mới.
4. **Trao đổi hướng đi:** thứ tự Product Backlog, thử nghiệm tiếp theo, những việc nên dừng hoặc điều chỉnh.

Một bản trình diễn giao diện đẹp **không thay thế** phần mềm thực sự hoàn tất và đáp ứng DoD. Các phần chưa đạt DoD cần được nói rõ tình trạng, không trình bày như Increment Done.

### 8.2. Timebox và người tham gia

Sprint Review có timebox **tối đa 4 giờ cho Sprint một tháng**, với Sprint ngắn hơn thường cần ít thời gian hơn. Đây là **phiên làm việc** giữa Scrum Team và stakeholder, không đơn thuần một buổi báo cáo một chiều.

Ví dụ: Sau khi xem khách đặt lịch trên điện thoại, đại diện hỗ trợ nhận xét rằng người dùng không nhận ra trạng thái khi mạng chậm. Product Owner cùng nhóm xem phản hồi và cân nhắc ưu tiên làm rõ xác nhận trước chức năng lọc địa điểm. Đây là một **quyết định sản phẩm dựa trên kiểm tra kết quả**, không phải biểu quyết chấm điểm thành viên.

### 8.3. Sprint Review không phải cửa kiểm soát phát hành

Nếu một Increment đạt DoD vào ngày thứ ba và có thể phát hành an toàn, Scrum không yêu cầu phải chờ ngày cuối Sprint để “được Review rồi mới release”. Ngược lại, nếu một phần công việc chưa đạt DoD ở ngày cuối, họp Review **không biến nó thành Done**.

Mốc phát hành có thể phụ thuộc pháp lý, bảo mật, vận hành hoặc kinh doanh; các yêu cầu đó cần được xử lý minh bạch. Sprint Review giúp nhìn kết quả và định hướng, chứ không tự thay thế chính sách kiểm soát chất lượng của tổ chức.

## 9. Sprint Retrospective — kết thúc Sprint bằng cải tiến cách làm

**Sprint Retrospective** là sự kiện kết thúc Sprint, nhằm **lên kế hoạch nâng chất lượng và hiệu quả**. Scrum Team xem lại Sprint vừa qua về cá nhân, tương tác, quy trình, công cụ và Definition of Done; thảo luận những gì diễn ra tốt, những vấn đề đã gặp và cách xử lý.

### 9.1. Phân biệt Review và Retrospective

| Tiêu chí | Sprint Review | Sprint Retrospective |
| --- | --- | --- |
| **Trọng tâm** | Sản phẩm và tiến độ hướng tới Product Goal. | Cách Scrum Team tạo sản phẩm và cải tiến hệ thống làm việc. |
| **Người tham gia** | Scrum Team cùng stakeholder quan trọng. | Scrum Team. |
| **Bằng chứng** | Increment, phản hồi người dùng, thay đổi thị trường, backlog. | Dòng công việc, chất lượng, phối hợp, rủi ro và trải nghiệm làm việc. |
| **Đầu ra** | Điều chỉnh Product Backlog hoặc định hướng khi phù hợp. | Hành động cải tiến chất lượng và hiệu quả, có thể đưa ngay vào Sprint tiếp theo. |
| **Thời điểm** | Gần cuối Sprint, trước Retrospective. | Kết thúc Sprint. |

Sprint Retrospective có timebox **tối đa 3 giờ cho Sprint một tháng**, thường ngắn hơn với Sprint ngắn.

### 9.2. Ví dụ: review code làm chậm việc hoàn tất

Nhóm thấy nhiều story viết mã xong nhưng chờ review ba ngày, khiến tích hợp và kiểm thử dồn vào cuối Sprint.

Một retrospective thực dụng có thể làm:

1. Xem dữ liệu WIP, thời gian chờ review và những hạng mục không đạt DoD.
2. Hỏi vì sao điểm chờ hình thành: mọi người mở quá nhiều việc hay thiếu người hiểu khu vực mã?
3. Đề xuất phương án: giới hạn WIP, ưu tiên review trước việc mới, chia nhỏ story, pair programming.
4. Chọn **một thử nghiệm khả thi**, ví dụ ưu tiên review mỗi sáng và không mở việc mới khi cột Review đầy.
5. Xem lại cycle time, số hạng mục hoàn tất và lỗi hồi quy ở Sprint tiếp theo.

Retrospective không phải buổi truy tìm ai đã “làm trễ Sprint”. Khuyến khích nêu vấn đề thật bằng thái độ tôn trọng, nhưng vẫn phải có trách nhiệm thực hiện thay đổi và theo dõi kết quả.

### 9.3. Kết nối Retrospective với Sprint tiếp theo

Hành động cải tiến có thể đưa vào Sprint Backlog tiếp theo nếu phù hợp, hoặc điều chỉnh chính sách làm việc chung. Không cần lập “Sprint cải tiến riêng” mới được sửa quy trình. Một số cải tiến kỹ thuật có thể trở thành Product Backlog Item để Product Owner và Developers đánh giá giá trị, rủi ro và thứ tự.

**Phản mẫu:** Cuối mỗi Sprint ghi 20 hành động cải tiến nhưng không ai làm, rồi Sprint tiếp theo lặp lại đúng vấn đề cũ. Tập trung vào ít việc đủ ảnh hưởng và có tín hiệu kiểm chứng thường tốt hơn.

## 10. Lịch Sprint hai tuần: hình dung toàn bộ nhịp

Giả sử nhóm dùng Sprint **hai tuần làm việc**, từ thứ Hai tuần đầu tới thứ Sáu tuần tiếp theo. Bảng dưới đây là **một lịch minh họa**, không phải giờ họp bắt buộc trong Scrum Guide. Lịch thực tế cần phù hợp với múi giờ, ngày nghỉ, người dùng và loại sản phẩm.

| Thời điểm | Sự kiện Scrum | Hoạt động diễn ra song song | Đầu ra/tín hiệu chính |
| --- | --- | --- | --- |
| **Ngày 1 (thứ Hai, tuần 1)** | Sprint bắt đầu; Sprint Planning | Xem Product Goal, ưu tiên, năng lực, phụ thuộc; có thể bắt đầu triển khai lát cắt đầu. | Sprint Goal, Sprint Backlog ban đầu. |
| **Ngày 2** | Daily Scrum | Thiết kế nhỏ, làm rõ user story, TDD, tích hợp những thay đổi đầu tiên. | Điều chỉnh kế hoạch theo điểm nghẽn, kiểm thử đầu tiên. |
| **Ngày 3** | Daily Scrum | Hoàn tất trường hợp người dùng đơn giản, code review và CI. | Có thể hình thành Increment đầu tiên nếu đạt DoD. |
| **Ngày 4** | Daily Scrum | Thử với người dùng/đối tác, làm rõ tiêu chí chấp nhận, xử lý lỗi. | Phát hiện giả định đúng/sai, cập nhật công việc. |
| **Ngày 5** | Daily Scrum | Tích hợp, kiểm thử hồi quy, Product Backlog refinement khi cần. | Công việc gần Done được ưu tiên hoàn tất. |
| **Ngày 6 (thứ Hai, tuần 2)** | Daily Scrum | Tiếp tục lát cắt quan trọng, xem dữ liệu thử và phản hồi. | Sprint Backlog phản ánh thực tế; có thể phát hành Increment. |
| **Ngày 7** | Daily Scrum | Xử lý phụ thuộc, kiểm thử cạnh tranh hoặc tình huống mạng chập chờn. | Rủi ro được nhìn thấy, phương án được điều chỉnh. |
| **Ngày 8** | Daily Scrum | Review và tích hợp phần đang làm, chuẩn bị bằng chứng kết quả. | Các mục Done được xác nhận bằng DoD. |
| **Ngày 9** | Daily Scrum | Làm việc có giá trị còn lại, thu thập tín hiệu outcome; không “đóng giả” ticket. | Dự báo rõ những gì đã và chưa hoàn tất. |
| **Ngày 10 (thứ Sáu, tuần 2)** | Daily Scrum, Sprint Review, Sprint Retrospective | Tổng hợp dữ liệu, xem Increment và chọn cải tiến; vẫn có thể làm việc kỹ thuật nếu phù hợp. | Backlog được xem lại; hành động cải tiến; Sprint kết thúc. |
| **Đầu nhịp tiếp theo** | Sprint mới và Sprint Planning | Dùng kiến thức mới, ưu tiên mới và năng lực thực tế. | Sprint Goal tiếp theo; không có khoảng chờ duyệt nhân tạo. |

Các hoạt động kỹ thuật trong bảng **không bị khóa vào ngày cố định**. Có thể kiểm thử, review, refinement, phát hành hoặc thu thập phản hồi vào nhiều ngày. Daily Scrum diễn ra **mỗi ngày làm việc**, thời lượng tối đa **15 phút**; việc tổ chức phù hợp với Sprint Planning ngày đầu là quyết định thực tế của nhóm, không cần tạo một buổi báo cáo hình thức khi vừa lập xong kế hoạch.

### 10.1. Một cách phân bổ thời lượng sự kiện

Scrum Guide đặt **timebox tối đa** đối với Sprint một tháng: Sprint Planning 8 giờ, Sprint Review 4 giờ, Sprint Retrospective 3 giờ; Daily Scrum 15 phút. Với Sprint ngắn hơn, các sự kiện còn lại **thường ngắn hơn**.

Ví dụ nhóm Sprint hai tuần có thể dự kiến:

- Sprint Planning: **2 giờ**, nếu backlog đã đủ rõ.
- Daily Scrum: **15 phút mỗi ngày làm việc**.
- Sprint Review: **60–90 phút**, tùy Increment và số bên liên quan.
- Sprint Retrospective: **45–60 phút**, đủ cho phân tích và hành động cải tiến.

Đây **không phải** chuẩn cố định, và không có quy định tất cả nhóm hai tuần phải dùng các con số này. Nếu Sprint Planning cần lâu hơn vì phụ thuộc phức tạp, nhóm nên xem cả chất lượng refinement và công tác chuẩn bị. Mục tiêu của timebox là giữ cuộc trao đổi **tập trung, minh bạch và không thay thế thời gian làm việc tạo giá trị**.

### 10.2. Làm gì khi có ngày lễ, nghỉ phép hoặc sự cố?

Độ dài Sprint vẫn được chọn theo nhịp nhất quán, nhưng **năng lực thực tế** phải tính ngày nghỉ, lịch trực, đào tạo và phụ thuộc. Không nên giả định hai tuần luôn có mười ngày làm việc đầy đủ của mọi thành viên. Nếu ngày lễ ảnh hưởng lịch sự kiện, nhóm cần sắp xếp để những mục đích kiểm tra và thích ứng vẫn được đáp ứng.

Nếu nhóm bị sự cố production chiếm nhiều năng lực, hãy điều chỉnh dự báo và Sprint Backlog phù hợp với Sprint Goal, chứ không coi mỗi ngày nghỉ hoặc công việc hỗ trợ là “lỗi cam kết” của một cá nhân.

## 11. Ba artifact và commitment tạo xương sống cho Sprint

Scrum gồm **ba artifact**, mỗi artifact có một **commitment** đi kèm:

| Artifact | Commitment | Câu hỏi kiểm tra quan trọng |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Sản phẩm đang hướng tới mục tiêu giá trị dài hạn nào? |
| **Sprint Backlog** | **Sprint Goal** | Sprint này nhóm cần tạo kết quả có ích gì và đang đi tới đó ra sao? |
| **Increment** | **Definition of Done** | Phần sản phẩm nào thực sự hoàn tất theo chuẩn chất lượng thống nhất? |

Những commitment giúp cung cấp tiêu chí để kiểm tra và thích ứng; chúng không chỉ là các trường bắt buộc trong một công cụ quản lý task.

### 11.1. Product Goal và Product Backlog

**Product Goal** mô tả trạng thái tương lai mà sản phẩm hướng tới; các mục còn lại trong Product Backlog xuất hiện như những lựa chọn nhằm tiến đến mục tiêu ấy. Product Backlog là danh sách công việc có thứ tự để cải thiện sản phẩm, được làm rõ khi có thêm hiểu biết.

**Ví dụ Product Goal:**

> “Khách đặt và quản lý lịch tư vấn trực tuyến một cách tin cậy, giảm nhu cầu gọi tổng đài.”

Product Backlog có thể gồm tính năng đặt lịch, thông báo, lỗi chống trùng, cải tiến hiệu năng, nợ kỹ thuật và khảo sát API. Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog, bao gồm thứ tự các mục. Các bên liên quan và Developers cung cấp thông tin để quyết định tốt hơn.

### 11.2. Sprint Goal và Sprint Backlog

**Sprint Goal** được tạo trong Sprint Planning. **Sprint Backlog** là kế hoạch do Developers lập, hiển thị mục tiêu, các Product Backlog Item đã chọn và kế hoạch thực hiện. Sprint Backlog có thể thay đổi suốt Sprint khi nhóm học thêm, miễn là không đe dọa Sprint Goal và không làm giảm chất lượng.

**Ví dụ Sprint Goal:**

> “Khách có thể chọn giờ trống và nhận xác nhận đặt lịch hợp lệ.”

Các hạng mục phù hợp có thể là giao diện chọn giờ, API tạo lịch, kiểm soát chống trùng và kiểm thử tích hợp. Nếu xuất hiện nhu cầu đổi màu giao diện nhưng không phục vụ mục tiêu, nhóm không nên tự động chen nó vào Sprint.

### 11.3. Increment và Definition of Done

**Increment** là bước tiến cụ thể tới Product Goal; nó phải **dùng được**, tích hợp với các Increment trước và đáp ứng **Definition of Done**. Một Product Backlog Item chỉ tạo phần Increment khi đáp ứng DoD.

**Ví dụ DoD minh họa cho hệ thống đặt lịch:**

- Hành vi và các trường hợp chấp nhận đã được kiểm chứng.
- Thay đổi đã tích hợp và kiểm thử hồi quy trọng yếu đạt.
- Không phát sinh lịch trùng trong những tình huống cạnh tranh đã được xác định.
- Quyền truy cập và dữ liệu cá nhân được xử lý đúng tiêu chuẩn áp dụng.
- Có khả năng quan sát lỗi liên quan và phương án triển khai/khôi phục khi cần.

DoD cụ thể phải theo tiêu chuẩn sản phẩm và tổ chức. Ví dụ trên không phải mẫu bắt buộc của Scrum Guide. Nếu tổ chức có chuẩn chất lượng, Scrum Team phải tuân theo chuẩn tối thiểu đó; nếu không, Scrum Team tạo DoD phù hợp với sản phẩm. Một Increment đạt DoD **chưa nhất thiết được phát hành ngay**, nhưng ở trạng thái có thể sử dụng và không cần chờ Sprint Review làm “cửa nghiệm thu”.

### 11.4. Backlog refinement nằm ở đâu trong nhịp?

**Refinement** là hoạt động làm nhỏ và làm rõ Product Backlog Item khi cần. Nhóm có thể trao đổi ví dụ nghiệp vụ, chấp nhận, độ phức tạp và phụ thuộc trong Sprint hiện tại để chuẩn bị việc cho các Sprint tiếp theo. Scrum Guide không có sự kiện riêng mang tên “Backlog Refinement” với timebox bắt buộc.

Nhóm có thể đặt lịch refinement định kỳ nếu có ích, hoặc trao đổi trực tiếp ngay khi phát hiện yêu cầu mơ hồ. Không nên dành cả Sprint cuối để viết tài liệu cho Sprint sau mà không tạo Increment; cũng không nên bỏ refinement khiến Sprint Planning thành buổi tìm hiểu yêu cầu từ đầu kéo dài.

## 12. Trách nhiệm của Scrum Team trong nhịp Sprint

Một Scrum Team có ba **accountabilities**: Product Owner, Scrum Master và Developers. Đây là cách phân chia trách nhiệm của Scrum Guide, không nhất thiết tương ứng với chức danh quản lý truyền thống.

| Trách nhiệm | Vai trò trong Sprint | Việc không nên hiểu sai |
| --- | --- | --- |
| **Product Owner** | Tối đa hóa giá trị, làm rõ Product Goal và quản lý hiệu quả Product Backlog; cộng tác để các quyết định phạm vi phục vụ giá trị. | Không phải người tự phân công từng task hoặc quyết định mọi chi tiết kỹ thuật. |
| **Developers** | Tạo Sprint Backlog, lập kế hoạch hướng Sprint Goal, điều chỉnh hằng ngày, giữ chất lượng và tạo Increment. | Không chỉ là lập trình viên; gồm các kỹ năng cần để tạo Increment, không phải “nhân sự nhận việc rồi báo cáo”. |
| **Scrum Master** | Chịu trách nhiệm về hiệu quả Scrum, giúp nhóm và tổ chức hiểu/vận dụng Scrum, hỗ trợ gỡ trở ngại và cải tiến. | Không mặc nhiên là project manager duyệt từng ticket, chủ trì mọi Daily Scrum hoặc thay Product Owner xếp backlog. |

### 12.1. Cùng một Sprint, có nhiều quyết định khác nhau

**Ở Planning**, Scrum Team cùng tạo Sprint Goal; Product Owner cung cấp góc nhìn giá trị, Developers đánh giá khả năng thực hiện và tạo kế hoạch.

**Trong Daily Scrum**, Developers kiểm tra tiến độ và thích ứng Sprint Backlog. Product Owner phối hợp khi cần thương lượng phạm vi; Scrum Master giúp các trở ngại được giải quyết nhưng không thay Developers ra quyết định cho công việc hằng ngày.

**Ở Review**, Scrum Team và stakeholder cùng kiểm tra kết quả; Product Backlog có thể được thích ứng dựa trên thông tin mới.

**Ở Retrospective**, Scrum Team cùng xem cách làm và lên kế hoạch cải tiến. Không có một trách nhiệm nào tự “sở hữu” toàn bộ tri thức hoặc được phép che thông tin quan trọng khỏi các trách nhiệm khác.

### 12.2. Năm giá trị Scrum làm sự kiện có chất lượng

**Cam kết, tập trung, cởi mở, tôn trọng và can đảm** là nền tảng hành vi:

- Cam kết với mục tiêu chung, thay vì ký nhận danh sách ticket bằng mọi giá.
- Tập trung hoàn tất phần hữu ích, không chạy theo số đầu việc đang mở.
- Cởi mở về tiến độ, giả định sai và rủi ro chất lượng.
- Tôn trọng chuyên môn và sự khác biệt khi phản biện.
- Can đảm nêu vấn đề khó và bảo vệ người dùng khi cần điều chỉnh kế hoạch.

Năm giá trị không phải một sự kiện bổ sung, cũng không phải điểm chấm năng suất cá nhân. Chúng làm các cơ hội **minh bạch–kiểm tra–thích ứng** trong Sprint có thực chất.

## 13. Ví dụ xuyên suốt: Sprint đặt lịch hai tuần

Giả sử một Scrum Team phát triển chức năng **đặt lịch tư vấn qua web**. Product Goal là giúp khách tự đặt lịch hợp lệ thay vì gọi tổng đài. Những tình huống và con số sau đây là **giả định để học**, không phải số liệu từ một sản phẩm thật.

### 13.1. Trước Sprint: backlog đã được làm rõ một phần

Product Owner có các Product Backlog Item:

| Mã | Nội dung | Giá trị/rủi ro chính |
| --- | --- | --- |
| **F1** | Khách xem khung giờ còn trống. | Bước đầu của tác vụ đặt lịch. |
| **F2** | Khách gửi yêu cầu và nhận mã xác nhận. | Hoàn tất tác vụ cốt lõi. |
| **Q1** | Ngăn tạo lịch trùng khi gửi lặp. | Tính đúng đắn và độ tin cậy. |
| **F3** | Gửi SMS sau khi đặt lịch. | Tiện ích bổ sung, cần đánh giá chi phí. |
| **E1** | Thử API đối tác trong trường hợp timeout. | Giảm bất định về tích hợp. |
| **F4** | Bộ lọc nhiều địa điểm. | Có tiềm năng nhưng chưa có bằng chứng ưu tiên cao. |

Nhóm đã refinement để biết F1, F2, Q1 và E1 có quan hệ chặt chẽ. Nếu E1 chưa có câu trả lời, họ không được tự khẳng định phần tích hợp production chắc chắn hoạt động được.

### 13.2. Ngày đầu: Sprint Planning tạo mục tiêu

Sprint Goal được chọn:

> “Người dùng thử có thể chọn giờ trống, tạo đúng một lịch hợp lệ và nhận xác nhận rõ ràng.”

Developers lập kế hoạch tạo lát cắt dọc qua UI, API và lưu trữ; đưa các kiểm thử gửi lặp vào công việc cần đạt DoD. F3 và F4 có thể giữ trong Product Backlog khi chưa cần thiết cho Sprint Goal. Nhóm không xem chúng là “thất bại” chỉ vì không đưa vào Sprint.

### 13.3. Ngày 2–3: Increment đầu tiên hình thành

Nhóm hoàn tất hiển thị giờ trống với dữ liệu phù hợp và kiểm thử tích hợp. Nếu hạng mục đáp ứng DoD và kết hợp được với Increment hiện có, một Increment mới đã hình thành. Nhóm không phải đợi tới ngày 10 để gọi phần đã đạt DoD là Done.

Trong Daily Scrum, Developers thấy công việc review API bị dồn vào một người. Họ ưu tiên hỗ trợ review thay vì mở thêm F4, bảo vệ dòng công việc.

### 13.4. Ngày 4–5: giả định tích hợp sai

Spike E1 cho thấy API đối tác có thể trả timeout sau khi đã lưu lịch. Khả năng này khiến thiết kế “cứ gửi lại request” chưa an toàn.

Nhóm cần:

1. Ghi quan sát, điều kiện thử và phần còn chưa biết.
2. Trao đổi với Product Owner về ảnh hưởng phạm vi, giữ Sprint Goal.
3. Thử phương án idempotency, truy vấn trạng thái hoặc cơ chế trung gian phù hợp với hợp đồng API.
4. Bổ sung trường hợp kiểm thử và phương án xử lý trạng thái chưa xác định.
5. Hoãn phần không cần để tập trung vào sự đúng đắn của luồng đặt lịch.

**Điều không nên làm:** Đóng E1 là “nghiên cứu xong” rồi bỏ qua kết quả để triển khai đúng thiết kế cũ. Giá trị của khảo sát nằm ở **quyết định kỹ thuật và backlog được điều chỉnh**.

### 13.5. Ngày 6–8: hoàn tất lát cắt và có thể phát hành giới hạn

Nhóm sửa xử lý gửi lặp, bổ sung kiểm thử cạnh tranh và tích hợp. Khi phần đặt lịch đạt DoD, họ có thể cho một nhóm người dùng thử trải nghiệm trên môi trường phù hợp, nếu quy trình an toàn và quyền phát hành cho phép.

Nếu đã phát hành giới hạn vào ngày 8, **Sprint Review ngày 10 vẫn cần thiết** để xem toàn bộ kết quả và bối cảnh mới. Review không mất ý nghĩa chỉ vì phần mềm đã đến tay người dùng sớm.

### 13.6. Ngày 9–10: Review và Retrospective

**Sprint Review:** Scrum Team trình bày Increment đạt DoD và các tín hiệu sử dụng ban đầu. Stakeholder nhận xét khách khó phân biệt “đang gửi yêu cầu” với “đã xác nhận”. Product Owner xem xét đưa cải tiến trạng thái lên trên F3/F4 trong Product Backlog.

**Sprint Retrospective:** Nhóm thấy lỗi timeout được phát hiện muộn vì kiểm thử hợp đồng API chưa chạy sớm. Họ chọn cải tiến: ngay khi bắt đầu story tích hợp, thử các kịch bản timeout và retry có rủi ro cao, lưu kết quả để mọi Developer truy cập.

**Kết thúc Sprint:** Nhóm ghi đúng những gì đã Done, những gì chưa và rủi ro còn lại. Sprint tiếp theo bắt đầu với Product Backlog đã được cập nhật, không cần một tuần chờ hoàn tất báo cáo.

### 13.7. Chuỗi học hỏi qua hai Sprint

~~~text
Sprint A
  Planning -> Goal đặt lịch hợp lệ
  Trong Sprint -> F1/F2/Q1, thử API, kiểm thử và phát hành giới hạn
  Review -> khách cần trạng thái xác nhận rõ hơn
  Retrospective -> kiểm thử timeout cần diễn ra sớm

Sprint B
  Planning -> Goal cải thiện khả năng hiểu và độ tin cậy khi xác nhận
  Trong Sprint -> làm rõ trạng thái, áp dụng kiểm thử hợp đồng từ đầu
  Review -> kiểm tra kết quả người dùng và độ ổn định
  Retrospective -> xem thay đổi cách làm có giảm lỗi phát hiện muộn không
~~~

Trong ví dụ này, **không có “giai đoạn lập kế hoạch dự án” tách hẳn khỏi “giai đoạn thực thi dự án” theo kiểu chỉ học ở cuối**. Mỗi Sprint vừa tạo giá trị vừa bổ sung hiểu biết cho Product Backlog và kỹ thuật ở Sprint sau.

## 14. Ứng phó những tình huống thường gặp trong Sprint

### 14.1. Stakeholder yêu cầu thêm tính năng vào giữa Sprint

**Tình huống:** Product Owner nhận yêu cầu thêm SMS, không gắn với Sprint Goal đặt lịch hợp lệ.

**Cách xử lý:** Làm rõ giá trị và mức khẩn cấp, xem thứ tự Product Backlog. Nếu không thực sự cấp bách, để cân nhắc cho các Sprint sau; không chen vào chỉ vì người yêu cầu có chức vụ cao. Nếu liên quan mục tiêu, Developers và Product Owner có thể thảo luận thay đổi phạm vi mà không làm nguy hiểm Sprint Goal.

**Giá trị Scrum liên quan:** Cam kết với mục tiêu, tập trung, cởi mở về tác động, tôn trọng trách nhiệm xếp backlog.

### 14.2. Phát hiện lỗi nghiêm trọng trên production

**Tình huống:** Sự cố tạo lịch trùng đang gây thiệt hại, cần ứng cứu.

**Cách xử lý:** Người có thẩm quyền kích hoạt quy trình ứng cứu, giảm ảnh hưởng và bảo vệ dữ liệu. Scrum Team minh bạch năng lực bị chiếm dụng, tác động tới Sprint Goal và công việc đang dở. Developers điều chỉnh Sprint Backlog; phối hợp với Product Owner để thương lượng phạm vi khi cần. Sau đó xem nguyên nhân, cải tiến kiểm thử và cách làm.

Không dùng câu “Scrum không nhận việc giữa Sprint” để bỏ mặc sự cố. Cũng không tự động coi mọi yêu cầu gắn nhãn “urgent” là sự cố nghiêm trọng.

### 14.3. Một story không đạt DoD trước khi Sprint kết thúc

**Tình huống:** Giao diện đã chạy trong demo nhưng chưa kiểm thử trường hợp lỗi quan trọng và không đạt DoD.

**Cách xử lý:** Không gọi story Done, không trình bày như Increment hoàn tất. Phần chưa Done trở lại Product Backlog để Product Owner cân nhắc lại thứ tự; công việc chưa hoàn tất không mặc nhiên được “chuyển thẳng” sang Sprint sau mà không xem giá trị và kế hoạch mới. Nhóm thảo luận nguyên nhân trong Retrospective nếu cần.

**Quan trọng:** Không giảm DoD để làm số liệu Sprint trông tốt. Nhưng cũng không tự động đánh giá toàn bộ Sprint là thất bại chỉ vì một story dự kiến chưa xong; phải kiểm tra Sprint Goal và Increment thực tế.

### 14.4. Không hoàn thành đủ mọi Product Backlog Item đã chọn

**Tình huống:** Đã chọn năm mục nhưng chỉ ba mục đạt DoD; Sprint Goal có thể vẫn đạt hoặc chưa đạt.

**Cách xử lý:** Nêu rõ kết quả và lý do, không “chốt sổ” dựa trên số lượng. Nếu mục tiêu vẫn đạt nhờ lát cắt hữu ích, nhóm có bằng chứng về khả năng thích ứng. Nếu mục tiêu không đạt, cần phân tích điều gì gây cản trở để chọn hướng cải tiến và điều chỉnh kế hoạch. **Sprint có timebox cố định**; không kéo dài Sprint vô hạn để hoàn tất danh sách.

### 14.5. API đối tác bị chặn kéo dài

**Tình huống:** Nhóm không có môi trường sandbox suốt một tuần.

**Cách xử lý:** Làm hiện rõ điểm chặn, tìm công việc độc lập có giá trị, dùng mock hoặc kiểm thử hợp đồng để làm rõ giao diện nhưng **không coi mock là bằng chứng tích hợp production**. Trao đổi với Product Owner về tác động tới Sprint Goal; nếu mục tiêu không còn khả thi, cần làm rõ lựa chọn và trách nhiệm chốt phù hợp. Không kéo người làm sang quá nhiều việc chỉ để bảng luôn đầy.

### 14.6. Sprint Goal thực sự lỗi thời

**Tình huống:** Chính sách mới khiến tính năng mục tiêu không còn được phép triển khai.

**Cách xử lý:** Product Owner đánh giá việc hủy Sprint theo Scrum Guide và phối hợp trao đổi với các bên liên quan. Hủy Sprint là tình huống bất thường, cần có căn cứ rõ; không phải cách né một cuộc Sprint Review khó hoặc che một Sprint Goal có nguy cơ không đạt.

### 14.7. Nhóm muốn phát hành sớm hơn ngày Review

**Tình huống:** Increment đạt DoD ở ngày 4, có thể mang giá trị sớm và quy trình phát hành cho phép.

**Cách xử lý:** Có thể phát hành theo chính sách sản phẩm mà không đợi Sprint Review. Sau đó theo dõi lỗi, phản hồi và dữ liệu sử dụng; dùng thông tin ấy ở Review. Việc phát hành trước không loại bỏ trách nhiệm có Sprint Review và Retrospective.

### 14.8. Một thành viên mới vào nhóm giữa Sprint

**Tình huống:** Nhóm nhận thêm người, quản lý kỳ vọng throughput tăng ngay.

**Cách xử lý:** Xem onboarding, quyền truy cập, tri thức sản phẩm và khả năng hỗ trợ. Không mặc định người mới có thể thay thế năng lực ngay hoặc bắt mọi Developer khác giảm thời gian review để tăng “số giờ code”. Nhóm có thể dùng pair programming, hạng mục nhỏ và chia sẻ tri thức; điều chỉnh dự báo nếu cần.

## 15. Nhịp Sprint, phát hành liên tục và các thực hành Kanban/XP

Scrum là một **framework** để giải quyết vấn đề phức tạp bằng chủ nghĩa kinh nghiệm; không phải một quy trình phát hành phần mềm cứng. Nhóm có thể kết hợp các thực hành phù hợp:

| Nhu cầu | Scrum đóng góp | Kanban/XP có thể bổ trợ |
| --- | --- | --- |
| Tập trung kết quả trong khoảng thời gian ngắn | Sprint Goal, Sprint Planning, Sprint Review | Giảm kích thước lô, chọn lát cắt nhỏ. |
| Điều chỉnh hằng ngày | Daily Scrum, Sprint Backlog minh bạch | Kanban: nhìn workflow, WIP, thời gian chờ; XP: tích hợp liên tục. |
| Giao Increment an toàn | Definition of Done, kiểm tra Increment | XP: TDD, CI, refactoring, pair programming; triển khai theo chính sách. |
| Xử lý phụ thuộc và sự cố | Scrum Team kiểm tra tác động và thương lượng phạm vi | Kanban: chính sách việc khẩn, trực quan hóa điểm chặn và dòng công việc. |
| Cải tiến hệ thống làm việc | Sprint Retrospective | Kanban: đo cycle time/throughput/WIP; XP: giảm lỗi hồi quy, thiết kế đơn giản. |

### 15.1. Sprint cadence không đồng nhất với release cadence

**Sprint cadence** là chu kỳ kiểm tra và thích ứng của Scrum. **Release cadence** là nhịp cung cấp sản phẩm tới người dùng; có thể nhiều lần trong một Sprint hoặc theo một lịch được kiểm soát. Hai nhịp không bắt buộc trùng nhau.

~~~text
Sprint 1:  |-------------------------|
Increment:    A(DoD)   B(DoD)    C(DoD)
Release:         R1       R2         R3
Review:                              [Review]
Retro:                               [Retro]

Sprint 2:                             |-------------------------|
~~~

Sơ đồ chỉ minh họa khả năng giao nhiều Increment trong một Sprint. Trong một sản phẩm chịu quy định nghiêm ngặt, thời điểm release có thể có bước kiểm soát chuyên môn; Sprint vẫn tạo Increment sử dụng được theo DoD, và Review vẫn xem kết quả thực.

### 15.2. Khác biệt với Kanban không dùng Sprint

Kanban có thể giúp quản lý dòng công việc liên tục bằng workflow minh bạch, giới hạn WIP, kéo việc và các vòng phản hồi thích hợp; **Kanban không đòi mọi đội phải tạo Sprint**. Một nhóm Scrum có thể dùng Kanban như thực hành bổ trợ để cải thiện flow, nhưng không nên gọi bảng Kanban là “Scrum đầy đủ” nếu không có Sprint Goal, các sự kiện và trách nhiệm Scrum tương ứng.

Ngược lại, dùng Scrum không có nghĩa phải bỏ quản lý flow. Nhìn thấy cycle time và WIP có thể giúp Developers điều chỉnh kế hoạch hàng ngày và lựa chọn cải tiến trong Retrospective.

### 15.3. XP giúp mỗi Sprint có Increment thực sự

Nếu chỉ viết mã trong tuần một, kiểm thử trong tuần hai và tích hợp vào cuối ngày 10, khả năng tạo Increment có ích và phản hồi sớm sẽ thấp. XP khuyến khích:

- **TDD:** làm rõ hành vi qua kiểm thử, giữ an toàn khi thay đổi yêu cầu.
- **Continuous integration:** phát hiện lỗi tích hợp sớm và thường xuyên.
- **Refactoring:** giữ cấu trúc đủ đơn giản để thay đổi an toàn.
- **Pair programming:** chia sẻ tri thức, phản hồi kỹ thuật nhanh.
- **Small releases:** tạo phần giá trị nhỏ và phản hồi sớm khi đáp ứng điều kiện phát hành.

Những thực hành này **không phải sự kiện Scrum bắt buộc**, nhưng có thể làm tăng khả năng biến Sprint thành nhịp giao giá trị thay vì nhịp báo cáo tiến độ.

## 16. Dùng chỉ số để biết nhịp Sprint có ích không

Scrum không định nghĩa một chỉ số duy nhất chứng minh hiệu quả Sprint. **Số story point hoàn thành** có thể hỗ trợ dự báo nội bộ trong một số đội nhưng không đo trực tiếp giá trị người dùng hoặc chất lượng. Đếm số cuộc họp đúng lịch càng không chứng minh nhóm đang học hỏi.

Một bộ tín hiệu cân bằng gồm:

| Góc nhìn | Chỉ số/tín hiệu gợi ý | Câu hỏi quyết định |
| --- | --- | --- |
| **Tiến độ hướng Sprint Goal** | Mục tiêu có đạt không, bằng Increment nào, điều kiện nào bị chặn. | Cần đổi thứ tự hoặc phạm vi để tiến tốt hơn không? |
| **Giá trị sản phẩm** | Tỷ lệ hoàn tất tác vụ, mức sử dụng, phản hồi người dùng, giảm nhu cầu hỗ trợ. | Increment giao có giải quyết vấn đề thật không? |
| **Chất lượng/độ tin cậy** | Lỗi hồi quy, lỗi production, độ trễ, thời gian phục hồi, mức đạt DoD. | Nhóm có đang chuyển rủi ro sang người dùng không? |
| **Dòng công việc** | Cycle time, lead time, throughput, WIP, thời gian chờ review. | Điểm chờ nào khiến phản hồi và hoàn tất chậm? |
| **Khả năng thích ứng** | Thời gian phát hiện trở ngại, việc thương lượng phạm vi, backlog thay đổi có lý do. | Thông tin mới có đi vào quyết định kịp thời không? |
| **Cải tiến cách làm** | Hành động Retrospective đã thử, tín hiệu trước/sau và quyết định giữ/đổi. | Nhóm có thay đổi hệ thống làm việc hay chỉ họp xong để đó? |

### 16.1. Một ví dụ đọc tín hiệu đúng

Giả sử nhóm có ba Sprint liên tiếp, mỗi Sprint hoàn thành khoảng 80% số ticket dự kiến. Không nên kết luận ngay “nhóm thiếu cam kết”. Cần hỏi:

- Ticket chưa Done có chủ yếu phụ thuộc API ngoài nhóm hay do chia quá lớn?
- Sprint Goal có bị đe dọa không, hay các ticket phụ bị hoãn hợp lý?
- DoD có được giữ, có lỗi hồi quy tăng không?
- WIP và thời gian chờ review có tăng qua các Sprint?
- Người dùng có nhận giá trị, hoặc backlog đang chứa chức năng ít dùng?

Chỉ số có ích khi dẫn đến hành động cụ thể, chẳng hạn chia nhỏ user story, giảm WIP, kiểm thử tích hợp sớm hoặc làm rõ backlog trước Planning.

### 16.2. Không dùng velocity để xếp hạng đội hoặc cá nhân

Velocity/story point phụ thuộc cách ước lượng của từng đội, cách chia việc và bối cảnh. Ép đội tăng point có thể khuyến khích tăng ước lượng hoặc tách hạng mục hình thức. **Sprint Goal, Increment đạt DoD, kết quả sản phẩm và khả năng học** là bức tranh đáng quan tâm hơn.

Các chỉ số DORA về khả năng giao thay đổi và độ ổn định có thể bổ trợ kiểm tra công việc kỹ thuật; chúng không thay thế tín hiệu outcome hoặc trách nhiệm Scrum.

## 17. Những ngộ nhận về Sprint và sự kiện Scrum

| Ngộ nhận | Vì sao không đúng | Cách hiểu và thực hành phù hợp |
| --- | --- | --- |
| “Sprint chỉ là hai tuần để đóng task.” | Sprint là sự kiện timebox chứa các cơ hội kiểm tra và thích ứng. | Bắt đầu với Sprint Goal và làm ra Increment hữu ích. |
| “Scrum có bốn sự kiện; Sprint không phải sự kiện.” | Scrum Guide xác định Sprint là sự kiện chứa bốn sự kiện còn lại. | Nhận diện đủ năm sự kiện và mục đích của mỗi sự kiện. |
| “Sprint luôn phải đúng hai tuần.” | Scrum cho phép Sprint cố định dài một tháng hoặc ngắn hơn. | Chọn thời lượng ổn định phù hợp rủi ro và nhịp phản hồi. |
| “Các cuộc họp phải chiếm đủ timebox.” | Timebox là giới hạn trên, không phải thời lượng tối thiểu. | Kết thúc khi đạt mục đích trong giới hạn. |
| “Daily Scrum là họp báo cáo cho Scrum Master.” | Sự kiện dành cho Developers kiểm tra tiến độ Sprint Goal. | Developers tự chọn cấu trúc tạo kế hoạch hữu ích. |
| “Refinement là sự kiện Scrum chính thức thứ sáu.” | Scrum Guide xem refinement là hoạt động liên tục, không có timebox sự kiện bắt buộc. | Dành thời gian phù hợp để làm rõ backlog khi cần. |
| “Không được phát hành trước Sprint Review.” | Increment có thể được giao giá trị trước Review. | Phát hành khi đạt DoD và điều kiện vận hành phù hợp. |
| “Review là buổi xin ký duyệt hoàn thành.” | Review nhằm kiểm tra kết quả và thích ứng Product Backlog. | Trao đổi với stakeholder về giá trị, bối cảnh và lựa chọn tiếp. |
| “Retrospective chỉ để phàn nàn.” | Mục tiêu là cải tiến chất lượng và hiệu quả. | Chọn hành động nhỏ, có người thực hiện và kiểm chứng. |
| “Chưa xong story thì cứ kéo dài Sprint.” | Sprint có timebox; Sprint tiếp theo bắt đầu ngay sau đó. | Đánh giá kết quả thật, cập nhật backlog và lập mục tiêu mới. |
| “Có thể cắt DoD để đạt đúng số ticket.” | Chất lượng không được giảm trong Sprint. | Giảm phạm vi hoặc điều chỉnh dự báo; giữ chuẩn cần thiết. |
| “Sprint Goal và danh sách story là một.” | Sprint Goal giải thích vì sao Sprint có giá trị, không phải danh sách đóng cứng. | Dùng Sprint Goal để thương lượng phạm vi khi học thêm. |
| “Chỉ cần đủ họp là dùng Scrum đúng.” | Sự kiện chỉ hữu ích khi có minh bạch, kiểm tra, thích ứng và giá trị thật. | Xem Increment, mục tiêu, tương tác và cải tiến. |
| “Scrum cấm họp kỹ thuật ngoài các sự kiện.” | Developers thường cần trao đổi, review, refinement, phối hợp và xử lý sự cố. | Họp khi cần, đúng người, ngắn và có kết quả; không thêm nghi lễ vô ích. |

## 18. Bài tập tình huống

### Tình huống A — Đầu Sprint có danh sách nhưng không có mục tiêu

Product Owner đưa ra 15 ticket gồm ba tính năng lớn, hai lỗi, bốn cải tiến giao diện và sáu việc kỹ thuật. Nhóm nhận việc theo số người rảnh rồi kết thúc Sprint Planning.

**Câu hỏi:**

1. Sprint Planning còn thiếu câu hỏi nào trong Why – What – How?
2. Vì sao danh sách 15 ticket chưa đủ để Scrum Team biết nên ưu tiên gì nếu có biến động?
3. Hãy viết một Sprint Goal gắn với kết quả khách hàng.
4. Điều gì cần được làm rõ về năng lực và Definition of Done?

**Hướng giải tham khảo:** Nhóm cần xác định giá trị Sprint và tạo Sprint Goal. Sau đó mới lựa chọn các Product Backlog Item khả thi và lập kế hoạch thực hiện. Một mục tiêu ví dụ: “Khách hoàn tất được một đơn đặt lịch hợp lệ, có xác nhận rõ ràng”. Không nên đồng nhất cam kết với hoàn tất cứng toàn bộ 15 ticket.

### Tình huống B — Giữa Sprint xuất hiện lỗi khẩn

Developers đang tập trung vào tính năng thông báo. Một lỗi production có thể tạo lịch trùng làm ảnh hưởng khách thật. Người quản lý nói: “Không được nhận việc ngoài Sprint, cứ đợi Sprint tới”.

**Câu hỏi:**

1. Những ràng buộc nào của Sprint cần cân nhắc?
2. Ai cần kích hoạt quy trình ứng cứu và ai cập nhật kế hoạch Sprint?
3. Làm sao minh bạch việc nào sẽ bị hoãn mà vẫn bảo vệ mục tiêu có giá trị?

**Hướng giải tham khảo:** Sự cố nghiêm trọng cần xử lý theo quyền hạn và chính sách, bảo vệ dữ liệu. Developers điều chỉnh Sprint Backlog, cùng Product Owner thương lượng phạm vi nếu tác động tới Sprint Goal. Không dùng Sprint như lý do bỏ rủi ro và cũng không mặc nhiên làm thêm mọi việc mà không có đánh đổi.

### Tình huống C — Phát hành giữa Sprint

Một Increment đạt DoD vào ngày 5. Bộ phận kinh doanh muốn mở cho nhóm dùng thử ngay, nhưng có người phản đối vì “phải chờ Review ngày 10”.

**Câu hỏi:**

1. Scrum có quy định phải đợi Sprint Review để phát hành không?
2. Increment đạt DoD đã đủ cho mọi điều kiện phát hành sản phẩm cụ thể chưa?
3. Review cuối Sprint còn cần làm gì nếu đã phát hành?

**Hướng giải tham khảo:** Scrum không xem Review là cổng phát hành. Increment đạt DoD có thể được cung cấp sớm khi những điều kiện vận hành, an toàn và thẩm quyền phát hành áp dụng đã đáp ứng. Sprint Review vẫn kiểm tra kết quả, phản hồi và tiến độ Product Goal để điều chỉnh Product Backlog.

### Tình huống D — Daily Scrum kéo dài 50 phút

Mỗi Developer báo cáo chi tiết tất cả thay đổi mã; Scrum Master ghi nhận hoàn thành công việc vào bảng. Cột Review đang quá tải nhưng không ai đề cập.

**Câu hỏi:**

1. Timebox và mục đích đúng của Daily Scrum là gì?
2. Developers có thể đổi cấu trúc buổi trao đổi như thế nào?
3. Những cuộc thảo luận kỹ thuật cần làm tiếp ở đâu?

**Hướng giải tham khảo:** Daily Scrum 15 phút để Developers kiểm tra tiến độ Sprint Goal và điều chỉnh Sprint Backlog. Nhóm nên đi từ điểm nghẽn và mục quan trọng nhất. Các cuộc trao đổi kỹ thuật chi tiết có thể thực hiện ngay sau với đúng người cần tham gia.

### Tình huống E — Review và Retrospective bị gộp thành “buổi tổng kết”

Vào ngày cuối Sprint, nhóm trình diễn màn hình, stakeholder góp ý trong năm phút, sau đó mọi người phân tích ai làm chậm nhất. Product Backlog không được thay đổi, cải tiến quy trình không có người phụ trách.

**Câu hỏi:**

1. Review và Retrospective có mục đích và người tham gia khác nhau thế nào?
2. Phần nào nên xuất hiện trong Product Backlog sau phản hồi người dùng?
3. Làm sao chọn một hành động cải tiến không đổ lỗi và kiểm tra được?

**Hướng giải tham khảo:** Review là phiên làm việc với stakeholder để xem kết quả và thích ứng hướng sản phẩm. Retrospective là cơ hội của Scrum Team để cải tiến chất lượng, hiệu quả và cách phối hợp. Nên tách rõ hai mục đích, ghi thay đổi backlog khi phù hợp và chọn hành động cải tiến có điểm xem lại.

### Tình huống F — Một story chưa Done nhưng đã “đạt 95%”

Đến Sprint Review, story thanh toán đã có giao diện và API nhưng chưa qua kiểm thử chống giao dịch lặp. Người phụ trách muốn gọi Done vì “chỉ còn 5%”.

**Câu hỏi:**

1. Khi nào một Product Backlog Item tạo Increment theo Scrum Guide?
2. Có thể hạ DoD để hợp thức hóa trạng thái Done không?
3. Công việc chưa Done sẽ được quản lý thế nào sau Sprint?

**Hướng giải tham khảo:** Hạng mục chưa đáp ứng DoD không tạo Increment Done, không được trình bày như đã hoàn tất. Phần chưa Done được cân nhắc lại trong Product Backlog; Product Owner sắp thứ tự theo giá trị/rủi ro. Nhóm kiểm tra vì sao chất lượng bị dồn muộn và thử cải tiến ở Sprint tiếp theo.

## 19. Bài thực hành: thiết kế nhịp Scrum cho nhóm giả định

Một nhóm gồm Product Owner, Scrum Master và năm Developers đang xây sản phẩm quản lý lịch hẹn. Họ chọn Sprint hai tuần, làm việc từ thứ Hai đến thứ Sáu, có một số thành viên làm từ xa.

### Yêu cầu

1. Viết **một Product Goal** và **một Sprint Goal** rõ giá trị người dùng.
2. Thiết kế bảng lịch gồm Sprint Planning, Daily Scrum, Review và Retrospective; giữ đúng giới hạn Scrum, nhưng chọn giờ hợp lý cho nhóm.
3. Liệt kê tối thiểu ba hoạt động quan trọng **không phải sự kiện Scrum chính thức**, như refinement, CI, kiểm thử hay hỗ trợ vận hành.
4. Chọn ba Product Backlog Item phục vụ Sprint Goal, nêu tiêu chí Done thiết yếu.
5. Giả sử API đối tác bị chặn hai ngày. Nêu kế hoạch điều chỉnh vẫn giữ Sprint Goal nếu khả thi.
6. Chỉ ra lúc nào một Increment có thể được giao cho người dùng và vai trò còn lại của Sprint Review.
7. Đề xuất một cải tiến sẽ thử sau Retrospective và tín hiệu kiểm tra trong Sprint sau.

### Mẫu kế hoạch điền

| Thành phần | Ghi nhận của nhóm |
| --- | --- |
| Product Goal | ... |
| Sprint dài bao lâu, vì sao chọn độ dài đó? | ... |
| Sprint Goal | ... |
| Sprint Planning: thời gian, người tham gia, kết quả | ... |
| Daily Scrum: thời gian, cách kiểm tra Sprint Goal | ... |
| Review: stakeholder, Increment, câu hỏi phản hồi | ... |
| Retrospective: trở ngại và cách chốt hành động | ... |
| Các hoạt động trong Sprint ngoài bốn sự kiện | ... |
| DoD và điều kiện phát hành phù hợp | ... |
| Điểm có thể thay đổi phạm vi khi có dữ liệu mới | ... |
| Tín hiệu đo giá trị, chất lượng và flow | ... |

### Một hướng làm tham khảo

**Product Goal:** “Người dùng tự đặt lịch tin cậy và không cần gọi hỗ trợ cho các thao tác cơ bản.”

**Sprint Goal:** “Người dùng có thể chọn giờ trống, đặt đúng một lịch hợp lệ và nhận xác nhận rõ ràng.”

**Sprint Planning:** Scrum Team cùng làm rõ Why – What – How, chọn các lát cắt cho UI, API và kiểm thử chống trùng.

**Daily Scrum:** Developers kiểm tra tiến độ mục tiêu, điểm chặn tích hợp và mức sẵn sàng của kiểm thử; thực hiện trao đổi chi tiết sau sự kiện nếu cần.

**Trong Sprint:** Refinement hạng mục tiếp theo, TDD/CI, kiểm thử tích hợp, phát hành giới hạn khi đạt DoD và có điều kiện an toàn, xem phản hồi.

**Sprint Review:** Scrum Team và stakeholder kiểm tra luồng đặt lịch có thể dùng; điều chỉnh Product Backlog dựa trên nhu cầu thực tế.

**Retrospective:** Nhóm nhận thấy review code dồn muộn; thử ưu tiên review trước khi kéo việc mới và đo lại thời gian chờ.

## 20. Checklist trước, trong và cuối Sprint

### Khi bắt đầu Sprint

- [ ] Độ dài Sprint cố định và không quá một tháng; mọi người hiểu thời điểm bắt đầu, kết thúc.
- [ ] Scrum Team tạo Sprint Goal rõ giá trị và liên hệ tới Product Goal.
- [ ] Developers có kế hoạch thực hiện và chọn việc tương xứng với năng lực, phụ thuộc thực tế.
- [ ] Những trường hợp chất lượng, bảo mật và tính đúng đắn đã được xem xét trong DoD.
- [ ] Sprint Backlog thể hiện Sprint Goal, các mục đã chọn và kế hoạch ban đầu.

### Khi Sprint đang diễn ra

- [ ] Daily Scrum phục vụ Developers kiểm tra tiến độ tới Sprint Goal, không thành báo cáo cá nhân cho quản lý.
- [ ] Product Backlog refinement, thiết kế, lập trình, kiểm thử, review và tích hợp diễn ra khi cần.
- [ ] Sprint Backlog được cập nhật theo thực tế; công việc bị chặn và giả định sai được nêu sớm.
- [ ] Thay đổi phạm vi được thương lượng phù hợp, không làm nguy hiểm Sprint Goal.
- [ ] Chất lượng không bị hạ; Product Backlog Item chỉ Done khi đạt DoD.
- [ ] Có thể tạo nhiều Increment và phát hành trước Sprint Review nếu đủ điều kiện.
- [ ] Công việc hỗ trợ vận hành hoặc sự cố được quản lý minh bạch trong năng lực thực.

### Khi Sprint kết thúc

- [ ] Sprint Review kiểm tra Increment, kết quả và bối cảnh cùng stakeholder; Product Backlog được điều chỉnh khi phù hợp.
- [ ] Retrospective xem chất lượng, hiệu quả và hệ thống làm việc; chọn hành động cải tiến thực hiện được.
- [ ] Phần chưa Done không bị trình bày như đã giao; người chịu trách nhiệm xem lại thứ tự backlog.
- [ ] Các cải tiến được đưa vào cách làm của Sprint tiếp theo, có tín hiệu xem lại.
- [ ] Sprint tiếp theo bắt đầu ngay theo nhịp đã chọn, không chờ một cổng ký duyệt giả tạo.

## 21. Ghi nhớ cốt lõi

**Sprint là nhịp bao trùm của Scrum:** Một khoảng thời gian cố định, tối đa một tháng, nơi toàn bộ công việc cần để tiến tới Product Goal được thực hiện. **Sprint Planning** tạo mục tiêu và kế hoạch; **Daily Scrum** giúp Developers kiểm tra và thích ứng hằng ngày; **Sprint Review** nhìn kết quả với stakeholder để điều chỉnh hướng sản phẩm; **Sprint Retrospective** kết thúc Sprint bằng cải tiến chất lượng và hiệu quả.

Trong nhịp đó, Developers **không chỉ tham dự sự kiện**: họ cùng Product Owner và Scrum Master cộng tác để làm rõ nhu cầu, thiết kế, viết mã, kiểm thử, tích hợp, xử lý rủi ro và giao Increment **đạt Definition of Done**. Có thể giao giá trị nhiều lần trước khi Sprint kết thúc; Sprint Review không phải cổng phát hành.

Điều giúp nhịp Sprint có ích là **Sprint Goal rõ, thông tin trung thực, khả năng thay đổi phạm vi có trách nhiệm và chất lượng không bị hy sinh**. Scrum cung cấp nhịp kiểm tra và thích ứng; các thực hành Kanban và XP có thể giúp nhóm kiểm soát WIP, nhận phản hồi kỹ thuật nhanh và giao những lát cắt nhỏ đáng tin cậy.

### Tài liệu tham khảo nền tảng

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — nguồn chính thức về Sprint, bốn sự kiện bên trong, timebox, Scrum Team, ba artifact và ba commitment.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — bốn giá trị Agile, gồm phần mềm hoạt động được và đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao phần mềm thường xuyên, phối hợp, chất lượng và cải tiến liên tục.
- [The Kanban Guide](https://kanbanguides.org/) — quản lý dòng công việc, WIP và đo lường flow khi bổ trợ Scrum.
- [DORA](https://dora.dev/) — tham khảo năng lực giao thay đổi phần mềm và độ ổn định vận hành.
