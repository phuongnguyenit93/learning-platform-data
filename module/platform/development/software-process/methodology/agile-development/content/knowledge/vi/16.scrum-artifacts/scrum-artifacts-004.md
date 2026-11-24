# Mối liên hệ giữa ba tạo tác và tính minh bạch trong Scrum

> **Thông điệp chính:** Scrum có ba tạo tác (*artifacts*) là **Product Backlog, Sprint Backlog và Increment**. Mỗi tạo tác đi cùng một cam kết (*commitment*) tương ứng: **Product Goal, Sprint Goal và Definition of Done**. Chúng không phải ba tệp báo cáo rời rạc; kết hợp với nhau, chúng làm rõ **sản phẩm cần đi đến đâu, nhóm đang định đạt điều gì trong Sprint và phần mềm nào thực sự hoàn thành**. Nhờ trạng thái đáng tin, Scrum Team và các bên liên quan mới có cơ sở để kiểm tra và thích ứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nêu đúng **ba tạo tác Scrum** và **ba cam kết** tương ứng theo Scrum Guide.
2. Giải thích cách Product Backlog, Sprint Backlog và Increment kết nối thành một dòng giá trị, thay vì là ba danh sách độc lập.
3. Phân biệt **minh bạch về mục tiêu, minh bạch về kế hoạch và minh bạch về chất lượng/kết quả**.
4. Xác định trách nhiệm của Product Owner, Developers và toàn Scrum Team khi tạo, duy trì và kiểm tra thông tin.
5. Sử dụng user story, acceptance criteria và Definition of Done đúng mục đích mà không biến các công cụ tùy chọn thành quy định bắt buộc của Scrum.
6. Giải thích cách thông tin mới từ Daily Scrum, Sprint Review và các vòng phản hồi sản phẩm làm thay đổi backlog hoặc kế hoạch Sprint.
7. Nhận diện các biểu hiện **minh bạch giả**: ticket báo Done khi chưa đủ chất lượng, Sprint Goal chỉ là tổng số ticket hoặc Product Backlog không phản ánh mục tiêu sản phẩm.
8. Liên hệ ba tạo tác với Scrum, dữ liệu luồng công việc Kanban và thực hành kỹ thuật XP khi phối hợp phát triển phần mềm thích ứng.

## 2. Vì sao phải xét mối liên hệ, không chỉ học thuộc tên tạo tác?

Giả sử một Scrum Team phát triển nền tảng học trực tuyến. Product Owner nhận thấy nhiều người đăng ký tài khoản nhưng không bắt đầu được bài học đầu tiên. Trong Sprint, Developers triển khai màn chào mừng, đường dẫn mở bài, tính năng lưu tiến độ và bộ kiểm thử liên quan.

Cuối tuần đầu:

- **Product Backlog** có nhiều mục liên quan đến việc giúp người học bắt đầu dễ dàng.
- **Sprint Backlog** chứa những mục nhóm đã chọn cùng kế hoạch thực hiện.
- Một số chức năng đã chạy trên máy Developer, nhưng chưa đạt kiểm thử tích hợp.

Nếu nhìn riêng các danh sách, nhóm có thể nói: “Chúng ta đã làm được tám ticket.” Nhưng những câu hỏi quan trọng hơn là:

1. Tám ticket ấy có đưa sản phẩm gần hơn **Product Goal** hay không?
2. Kế hoạch hiện tại có giúp đạt **Sprint Goal** hay không?
3. Phần nào thực sự đáp ứng **Definition of Done** và trở thành **Increment**?
4. Có bằng chứng mới nào đòi hỏi sắp xếp lại Product Backlog hoặc điều chỉnh kế hoạch Sprint?

Ba tạo tác và ba cam kết giúp trả lời những câu hỏi khác nhau nhưng liên quan chặt chẽ. Chúng hỗ trợ **minh bạch → kiểm tra → thích ứng** — ba trụ cột của chủ nghĩa thực nghiệm trong Scrum.

## 3. Tổng quan: ba tạo tác và ba cam kết

| Tạo tác (*artifact*) | Cam kết (*commitment*) | Làm minh bạch điều gì? | Câu hỏi kiểm tra trung tâm |
|---|---|---|---|
| **Product Backlog** | **Product Goal** | Công việc cần thiết để cải thiện sản phẩm và trạng thái tương lai cần hướng tới | “Chúng ta đang ưu tiên đúng những việc giúp sản phẩm tiến gần mục tiêu không?” |
| **Sprint Backlog** | **Sprint Goal** | Vì sao Sprint có giá trị, PBI đã chọn và kế hoạch Developers dùng để thực hiện | “Với tình trạng hiện tại, chúng ta có đang tiến tới mục tiêu của Sprint không?” |
| **Increment** | **Definition of Done (DoD)** | Phần sản phẩm thực sự được tích hợp, sử dụng được và đạt các tiêu chuẩn chất lượng bắt buộc | “Điều gì đã hoàn thành thật, hoạt động đúng và đủ chất lượng?” |

Điểm phân biệt quan trọng:

- **Product Goal** không phải toàn bộ Product Backlog; nó là kết quả tương lai tạo định hướng cho backlog.
- **Sprint Goal** không phải danh sách PBI được chọn; nó giải thích **vì sao** những việc đó đáng làm trong Sprint.
- **Definition of Done** không phải một tỷ lệ hoàn thành hoặc danh sách hứa sẽ kiểm thử sau; đó là chuẩn chất lượng để xác định một phần công việc đã trở thành Increment.

Mối quan hệ có thể mô tả như sau:

~~~mermaid
flowchart TD
    PG["Product Goal: trạng thái tương lai cần đạt"] --> PB["Product Backlog: danh sách công việc sản phẩm được sắp thứ tự"]
    PB --> SP["Sprint Planning: chọn mục tiêu và việc phù hợp"]
    SP --> SG["Sprint Goal: mục tiêu duy nhất của Sprint"]
    SP --> SB["Sprint Backlog: Sprint Goal + PBI đã chọn + kế hoạch thực hiện"]
    SG --> SB
    SB --> WORK["Developers xây dựng, tích hợp, kiểm thử và thích ứng kế hoạch"]
    WORK --> DOD{"Đã đáp ứng Definition of Done?"}
    DOD -->|"Có"| INC["Increment: phần sản phẩm tích hợp và sử dụng được"]
    DOD -->|"Chưa"| SB
    INC --> FEEDBACK["Kiểm tra với bên liên quan và phản hồi sử dụng"]
    FEEDBACK --> PB
    FEEDBACK --> PG
~~~

Sơ đồ chỉ là **mô hình học tập**: thực tế thông tin có thể xuất hiện trong bất kỳ thời điểm nào. Scrum Team không cần chờ hết Sprint mới được tích hợp Increment, phát hành khi đủ điều kiện hoặc điều chỉnh kế hoạch.

## 4. Product Backlog và Product Goal: minh bạch hướng đi

### 4.1. Product Backlog là gì?

Theo Scrum Guide, **Product Backlog** là một danh sách công việc **được sắp thứ tự và liên tục phát triển** về những gì cần để cải thiện sản phẩm. Đây là **nguồn công việc duy nhất** mà Scrum Team thực hiện cho sản phẩm.

Đặc tính quan trọng:

- **Emergent — nổi lên theo hiểu biết:** các hạng mục, mức độ rõ ràng và thứ tự có thể đổi khi nhóm học thêm từ người dùng, thị trường, công nghệ hoặc rủi ro.
- **Ordered — có thứ tự:** việc gần đầu backlog được chú ý trước; thứ tự phản ánh giá trị, rủi ro, phụ thuộc, độ khẩn cấp và lựa chọn của Product Owner.
- **Transparent — dễ hiểu:** người liên quan có thể biết điều gì đang được cân nhắc, vì sao nó quan trọng và trạng thái hiểu biết đến đâu.
- **Product-oriented — hướng sản phẩm:** không phải kho lưu mọi yêu cầu cá nhân, cũng không phải danh sách bất biến từ đầu dự án.

Một Product Backlog Item (PBI) có thể là tính năng, lỗi, nghiên cứu, cải thiện hiệu năng, bảo mật hoặc công việc kỹ thuật cần thiết. **Scrum không bắt buộc PBI phải được viết dưới dạng user story**.

### 4.2. Product Goal định hướng cho backlog

**Product Goal** mô tả trạng thái tương lai của sản phẩm, đóng vai trò mục tiêu dài hơn để Scrum Team lập kế hoạch hướng tới. Đây là commitment của Product Backlog.

Ví dụ:

> **Product Goal:** “Người học mới có thể tìm được bài học phù hợp, bắt đầu học và hoàn thành bài đầu tiên một cách thuận lợi trong tuần đầu sau khi đăng ký.”

Để tiến gần mục tiêu, Product Backlog có thể gồm:

| PBI minh họa | Vấn đề hoặc giá trị liên quan | Điều cần kiểm chứng |
|---|---|---|
| Làm rõ hành trình người học mới | Chưa biết người học bỏ dở ở bước nào | Phản hồi và quan sát hành vi |
| Thêm hành động “Bắt đầu bài đầu” trên màn chào mừng | Người học có thể không tìm được bước tiếp theo | Tỷ lệ mở bài đầu |
| Sửa lỗi lưu tiến độ trên điện thoại | Người học mất công sức, dễ bỏ dở | Lỗi lưu, tỷ lệ hoàn tất bài |
| Tối ưu tải nội dung bài đầu | Trang chậm làm trải nghiệm kém | Thời gian tải, lỗi và hành vi học |
| Thêm bảng xếp hạng thành tích | Có thể hữu ích nhưng liên hệ mục tiêu hiện tại chưa rõ | Nghiên cứu nhu cầu trước khi ưu tiên lớn |

Sự liên kết không phải một công thức cơ học: PBI bảo mật hoặc sửa lỗi mất dữ liệu có thể cần ưu tiên rất cao vì **bảo vệ giá trị và trách nhiệm sản phẩm**, dù khó đo bằng tỷ lệ hoàn thành bài ngay lập tức.

### 4.3. Ai chịu trách nhiệm Product Backlog?

**Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. Công việc này bao gồm phát triển/truyền đạt Product Goal, tạo và truyền đạt rõ PBI, sắp thứ tự PBI và bảo đảm backlog minh bạch, dễ hiểu.

Product Owner có thể ủy quyền thực hiện một số việc, nhưng **vẫn giữ trách nhiệm cuối cùng**. Developers, Scrum Master, người dùng và stakeholder đóng góp bằng chứng và kiến thức. Nếu một stakeholder muốn thay đổi Product Backlog, họ cần làm rõ với Product Owner thay vì âm thầm giao việc riêng cho một Developer.

### 4.4. Product Backlog cần chi tiết tới đâu?

Không cần mô tả thật sâu mọi ý tưởng cho một năm tới. Những PBI gần thời điểm lựa chọn nên được làm rõ và chia nhỏ đủ để lập kế hoạch. Những mục còn xa và nhiều bất định có thể giữ ở mức khái quát.

**Product Backlog refinement** là hoạt động chia nhỏ và bổ sung thông tin cho PBI, diễn ra liên tục khi cần. Nó **không phải một sự kiện Scrum chính thức có timebox bắt buộc**.

Minh bạch ở đây là nhìn thấy **mức độ hiểu biết thực tế**: việc nào đã rõ, việc nào vẫn là giả thuyết, việc nào cần nghiên cứu thêm. Backlog chứa 500 ticket rất chi tiết nhưng nhanh lỗi thời không nhất thiết minh bạch hơn backlog được sắp thứ tự và quản lý theo thông tin mới.

### 4.5. Dấu hiệu Product Backlog chưa minh bạch

- Không ai ngoài một cá nhân biết tại sao PBI đứng đầu.
- Nhiều danh sách công việc song song cùng “giao nhiệm vụ” cho Scrum Team.
- Product Goal không được dùng khi so sánh các lựa chọn.
- Ý tưởng mới được thêm thẳng vào Sprint Backlog mà không có trao đổi trách nhiệm.
- PBI bị đánh dấu “bắt buộc” dù không rõ nghĩa vụ hoặc hậu quả nếu chưa làm.
- Các giả định đã bị bác bỏ vẫn nằm ở đầu backlog chỉ vì kế hoạch cũ.

Để khắc phục, hãy thể hiện mục tiêu, thứ tự, lý do đủ ngắn và nguồn bằng chứng; không cần thêm một hệ thống biểu mẫu nặng nề nếu công cụ hiện tại đã hỗ trợ.

## 5. Sprint Backlog và Sprint Goal: minh bạch kế hoạch đang thực hiện

### 5.1. Sprint Backlog gồm những gì?

**Sprint Backlog** bao gồm:

1. **Sprint Goal — vì sao Sprint có giá trị?**
2. **Các PBI được chọn cho Sprint — làm những gì?**
3. **Kế hoạch hành động để tạo Increment — làm thế nào?**

Đây là kế hoạch **do Developers lập ra và dành cho Developers**, đồng thời đủ minh bạch để Scrum Team nhìn thấy công việc được dự định nhằm đạt Sprint Goal. Sprint Backlog được **cập nhật suốt Sprint** khi hiểu biết tăng lên.

Một ví dụ tối giản:

~~~text
SPRINT GOAL
  Người học mới có thể mở bài đầu và biết trạng thái lưu tiến độ
  trong một luồng đáng tin cậy.

SELECTED PRODUCT BACKLOG ITEMS
  LEARN-21  Mở bài đầu từ màn chào mừng
  LEARN-24  Lưu tiến độ bài đầu
  LEARN-29  Hiển thị lỗi khi lưu tiến độ không thành công

ACTIONABLE PLAN (ví dụ, có thể điều chỉnh)
  - Làm rõ trường hợp mất kết nối
  - Tích hợp giao diện với API lưu tiến độ
  - Tạo kiểm thử hành vi và hồi quy cần thiết
  - Thử luồng từ đăng ký tới mở lại bài

CURRENT RISKS
  - Môi trường thử trên thiết bị di động chưa ổn định
  - Quy tắc đồng bộ sau mất kết nối đang cần làm rõ
~~~

Ví dụ này minh bạch **mục tiêu, phạm vi và kế hoạch**, không quy định Developers phải dùng đúng mẫu hay đúng số cột.

### 5.2. Sprint Goal không phải “làm hết ticket”

Sprint Goal là **mục tiêu duy nhất** của Sprint, tạo sự gắn kết và tập trung. Sprint có timebox cố định, tối đa một tháng, nhưng không vì vậy mà tất cả PBI đã chọn đều là lời hứa chắc chắn phải hoàn thành bất kể thông tin mới.

Ví dụ:

- **Danh sách việc:** “Màn chào mừng, nút mở bài, lưu tiến độ, hiệu ứng trang và bảng thông báo.”
- **Sprint Goal:** “Người học mới mở được bài đầu và có phản hồi đáng tin khi lưu tiến độ.”

Nếu kiểm thử phát hiện chức năng lưu báo thành công sai, Developers có thể trao đổi với Product Owner về việc **hoãn hiệu ứng trang** để hoàn tất phần quan trọng đối với Sprint Goal. Thay đổi này có thể hợp lý nếu Sprint Goal được bảo vệ và chất lượng không giảm.

### 5.3. Ai sở hữu Sprint Backlog?

**Developers** chịu trách nhiệm tạo và điều chỉnh Sprint Backlog. Tại Sprint Planning, Scrum Team hình thành Sprint Goal; Developers chọn các PBI có thể thực hiện và lập kế hoạch công việc cần thiết.

Product Owner giúp làm rõ giá trị và thương lượng phạm vi khi cần. Scrum Master hỗ trợ Scrum được hiểu và Scrum Team hiệu quả hơn. Không nên biến Sprint Backlog thành danh sách nhiệm vụ được cấp trên phân công đơn phương rồi chỉ dùng Daily Scrum để kiểm điểm.

### 5.4. Khi nào và vì sao Sprint Backlog thay đổi?

Khi triển khai, Developers có thể:

- Phát hiện PBI lớn hơn dự kiến, cần chia nhỏ bước thực hiện.
- Tìm thấy rủi ro tích hợp hoặc lỗi nghiêm trọng cần xử lý để đạt DoD.
- Cập nhật kế hoạch kiểm thử hoặc cách phối hợp.
- Thương lượng phạm vi với Product Owner khi hiểu biết mới thay đổi điều cần làm.

Theo Scrum Guide, trong Sprint **không được thực hiện thay đổi gây nguy hại Sprint Goal**, và **chất lượng không được giảm**. Product Backlog có thể được làm rõ và điều chỉnh. Nếu Sprint Goal thực sự trở nên lỗi thời, **Product Owner có quyền hủy Sprint**.

Vì thế, minh bạch không có nghĩa Sprint Backlog phải giữ nguyên từ ngày đầu; ngược lại, nó phải phản ánh **kế hoạch thật đang được Developers sử dụng**.

### 5.5. Một Daily Scrum có mục đích

Daily Scrum là sự kiện 15 phút cho Developers, để kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog. Không có công thức ba câu hỏi bắt buộc.

Ví dụ:

> “Sprint Goal yêu cầu luồng mở và lưu bài đáng tin. Phần mở bài đã đạt kiểm thử chính, nhưng việc lưu tiến độ đang bị chặn bởi lỗi tích hợp. Hôm nay nhóm ưu tiên tái hiện lỗi và hoàn tất kiểm thử thay vì mở thêm PBI phụ.”

Đó là inspection dẫn đến adaptation. Một lượt từng cá nhân đọc tình trạng ticket cho quản lý nhưng không thay đổi kế hoạch chưa chắc đạt mục đích này.

### 5.6. Khi Scrum Team dùng Kanban để nhìn Sprint Backlog

Một số nhóm Scrum trực quan hóa Sprint Backlog bằng bảng và dùng các phép đo Kanban như **Work in Progress (WIP), throughput, cycle time, work item age**. Chúng giúp thấy công việc bị chặn, quá nhiều việc đang mở hay dự báo hoàn thành.

Tuy nhiên, **Kanban board, WIP limit, burndown chart và story point không phải ba artifact của Scrum**. Nếu nhóm dùng, hãy xem chúng là công cụ hỗ trợ sự minh bạch và ra quyết định, không phải chuẩn thay thế Sprint Goal.

## 6. Increment và Definition of Done: minh bạch điều thực sự hoàn thành

### 6.1. Increment là gì?

**Increment** là bước tiến cụ thể hướng tới Product Goal. Mỗi Increment cần:

- **Bổ sung vào những Increment trước**, không tách rời thành các mảnh không hoạt động cùng nhau.
- **Được kiểm chứng có thể hoạt động cùng những phần trước**.
- **Đáp ứng Definition of Done** để được coi là hoàn thành.
- **Có thể sử dụng được** theo mục đích của sản phẩm, dù nhóm có thể chọn thời điểm phát hành phù hợp.

Một Sprint có thể tạo **nhiều Increment**; chúng có thể được giao cho stakeholder trước Sprint Review. Sprint Review **không phải cổng phê duyệt bắt buộc để được phát hành**.

**Một đoạn code chỉ chạy trên máy cá nhân chưa chắc là Increment.** Một màn hình đã thiết kế xong nhưng chưa tích hợp hành vi cốt lõi cũng chưa đủ để tự gọi là Increment nếu không đáp ứng DoD của sản phẩm.

### 6.2. Definition of Done là gì?

**Definition of Done (DoD)** là mô tả chính thức về trạng thái của Increment khi nó đáp ứng các tiêu chuẩn chất lượng bắt buộc của sản phẩm.

Khi một PBI đáp ứng Definition of Done, một Increment được tạo ra. Nếu PBI **chưa đáp ứng DoD**, công việc đó **không phải Increment**, không được phát hành hay trình bày tại Sprint Review như đã hoàn thành; PBI được đưa lại Product Backlog để cân nhắc công việc tiếp theo.

DoD tạo **một cách hiểu chung về “hoàn thành”**, tránh việc Developer, Tester, Product Owner và stakeholder đánh giá trạng thái theo những tiêu chuẩn khác nhau.

Ví dụ DoD ở một sản phẩm học trực tuyến có thể bao gồm:

- Hành vi quan trọng được kiểm thử với trường hợp thành công và lỗi phù hợp.
- Thay đổi được tích hợp, không phá vỡ luồng đang hoạt động.
- Kiểm soát truy cập và bảo vệ dữ liệu theo tiêu chuẩn sản phẩm.
- Luồng sử dụng đáp ứng mức tiếp cận và hiệu năng đã thống nhất.
- Có thông tin cần thiết để vận hành, theo dõi lỗi và hỗ trợ.

Đây là **ví dụ tùy bối cảnh**, không phải danh sách DoD bắt buộc chung cho mọi sản phẩm. Nếu tổ chức có tiêu chuẩn DoD áp dụng, Scrum Team phải tuân thủ ít nhất tiêu chuẩn đó; nếu chưa có, Scrum Team xây DoD phù hợp. Khi nhiều Scrum Team cùng làm một sản phẩm, họ cần xác lập và tuân thủ **cùng một Definition of Done**.

### 6.3. Acceptance criteria khác Definition of Done

Hai khái niệm có vai trò khác nhau:

| Tiêu chí | Acceptance criteria | Definition of Done |
|---|---|---|
| **Phạm vi** | Điều kiện hành vi/nghiệp vụ của **một PBI cụ thể** | Chuẩn chất lượng chung để Increment của sản phẩm được coi là hoàn thành |
| **Ví dụ** | “Khi mất mạng trước lúc lưu thành công, hệ thống không thông báo đã lưu.” | “Kiểm thử tích hợp và hồi quy liên quan phải đạt; không có rủi ro bảo mật chưa xử lý vượt ngưỡng cho phép.” |
| **Mục đích** | Làm rõ kỳ vọng và giúp kiểm chứng PBI | Bảo đảm mọi người dùng chung tiêu chuẩn minh bạch về chất lượng |
| **Vị thế trong Scrum** | Thực hành làm rõ thường hữu ích, không được Scrum Guide quy định là artifact | Commitment chính thức của Increment |

Acceptance criteria có thể được ghi bằng ví dụ Gherkin, bảng điều kiện hoặc mô tả rõ bằng ngôn ngữ tự nhiên. Chỉ khi **hành vi mong muốn và DoD đều được đáp ứng** thì mới nên báo hạng mục Done.

### 6.4. Ví dụ acceptance criteria cho một PBI

**User story:**

> Là người học mới, tôi muốn lưu tiến độ bài đầu để có thể tiếp tục học mà không phải làm lại phần đã hoàn thành.

**Các kịch bản minh họa:**

~~~gherkin
Tính năng: Lưu tiến độ của bài học đầu tiên

Kịch bản: Lưu tiến độ thành công
  Cho trước người học đã đăng nhập và đang học một bài hợp lệ
  Khi hệ thống xác nhận đã lưu tiến độ
  Thì người học thấy trạng thái lưu thành công phù hợp
  Và tiến độ được đọc lại đúng theo quy tắc sản phẩm

Kịch bản: Dịch vụ lưu gặp lỗi
  Cho trước người học đang có tiến độ chưa được xác nhận lưu
  Khi dịch vụ lưu trả lỗi
  Thì hệ thống không thông báo sai rằng tiến độ đã lưu
  Và người học nhận hướng xử lý phù hợp

Kịch bản: Mở lại bài trên thiết bị được hỗ trợ
  Cho trước tiến độ của người học đã được xác nhận lưu
  Khi người học mở lại bài bằng thiết bị được hỗ trợ khác
  Thì hệ thống hiển thị tiến độ đã lưu theo quy tắc đồng bộ
  Và không tùy tiện ghi đè dữ liệu mới bằng dữ liệu cũ
~~~

Các kịch bản giúp kiểm chứng **hành vi của PBI**. Việc tích hợp, kiểm thử hồi quy, bảo mật và chất lượng cần có vẫn được đánh giá theo **DoD**, không bị thay thế bằng ba kịch bản trên.

### 6.5. “Đạt DoD” chưa phải “Product Goal đã đạt”

Increment đạt DoD cho biết **phần mềm đã thực sự hoàn thành theo chuẩn chất lượng**. Nhưng Product Goal là một trạng thái kết quả sản phẩm rộng hơn, có thể cần dữ liệu sử dụng thực tế.

Ví dụ:

- **Đã đạt DoD:** luồng lưu tiến độ hoạt động đúng trong các điều kiện cần hỗ trợ.
- **Cần quan sát thêm:** sau khi có lưu tiến độ, người học có hoàn thành bài đầu nhiều hơn không?

Đánh đồng hai điều sẽ khiến nhóm chỉ tối ưu số PBI hoàn tất, bỏ qua khả năng giải pháp không xử lý đúng vấn đề người dùng.

## 7. Ba tạo tác minh bạch ba góc nhìn của cùng một sản phẩm

Hãy đọc bảng sau theo **từng lớp thông tin**:

| Góc nhìn | Product Backlog + Product Goal | Sprint Backlog + Sprint Goal | Increment + DoD |
|---|---|---|---|
| **Thời gian** | Dài hơn, tiến hóa khi có hiểu biết mới | Trong Sprint hiện tại, cập nhật liên tục | Mỗi bước sản phẩm hoàn thành |
| **Đơn vị trọng tâm** | Cơ hội, hạng mục cần thiết để cải thiện sản phẩm | Mục tiêu Sprint, PBI được chọn và cách thực hiện | Phần sản phẩm tích hợp hoạt động được |
| **Câu hỏi “Vì sao?”** | Vì sao sản phẩm theo đuổi mục tiêu này? | Vì sao Sprint này có giá trị? | Vì sao phần đã giao đủ tin cậy để dùng? |
| **Cần minh bạch** | Thứ tự, giá trị, mức hiểu biết, rủi ro | Kế hoạch thật, blocker, nguy cơ đối với Sprint Goal | Hành vi, kiểm thử, tích hợp, chuẩn chất lượng |
| **Kiểm tra qua** | Dữ liệu sản phẩm, nhu cầu stakeholder, Sprint Review | Daily Scrum và quá trình làm việc hằng ngày | Kiểm thử, tích hợp, phản hồi Increment |
| **Có thể thích ứng** | Sắp thứ tự, chia nhỏ, sửa hoặc bỏ PBI; xem lại Product Goal | Kế hoạch và phạm vi chi tiết theo thông tin mới | Giải pháp, kiểm thử, cách tích hợp và tiêu chuẩn phù hợp theo trách nhiệm |

Ba tạo tác **không cạnh tranh vai trò**:

- Product Backlog nói rõ **những cơ hội và công việc nên xem xét**.
- Sprint Backlog nói rõ **nhóm đang thực hiện phần nào và bằng cách gì**.
- Increment nói rõ **điều đã được tạo ra thật sự với chất lượng đủ để dùng**.

Không nên suy luận rằng Product Backlog phải đóng băng sau Sprint Planning. Cũng không nên suy luận rằng Increment chỉ xuất hiện vào cuối Sprint. Minh bạch là phản ánh **thực tế liên tục**, không phải chụp một bức ảnh kế hoạch rồi buộc mọi người làm theo bất kể thay đổi.

## 8. Dòng truy vết qua một Sprint hoàn chỉnh

Một ví dụ từ mục tiêu tới kết quả:

~~~text
PRODUCT GOAL
  Người học mới bắt đầu và hoàn thành bài học đầu tiên thuận lợi
      |
PRODUCT BACKLOG
  PBI-11: Khắc phục lỗi không lưu tiến độ trên di động
  PBI-12: Mở bài đầu trực tiếp từ màn chào mừng
  PBI-13: Cải thiện thông báo lỗi
      |
SPRINT PLANNING
  Sprint Goal: Người học mới mở bài và lưu tiến độ đáng tin cậy
      |
SPRINT BACKLOG
  PBI được chọn + kế hoạch xây dựng, tích hợp và kiểm thử
      |
DEVELOPMENT + INSPECTION
  Một số việc đạt DoD; một việc còn lỗi tích hợp nên chưa Done
      |
INCREMENT
  Luồng mở bài và lưu tiến độ đã tích hợp, đạt DoD
      |
SPRINT REVIEW / PHẢN HỒI SỬ DỤNG
  Người học mở bài dễ hơn, nhưng nhiều người vẫn dừng giữa bài
      |
PRODUCT BACKLOG THÍCH ỨNG
  Xem lại ưu tiên hỗ trợ học giữa chừng, không chỉ thêm nút mở bài
~~~

Không nhất thiết mỗi dòng là một công cụ hoặc biểu mẫu riêng. Một issue tracker, kho mã, công cụ kiểm thử và nguồn dữ liệu sản phẩm có thể **liên kết đủ để tìm lại quyết định**, nhưng không phải sao chép toàn bộ nội dung vào ba nơi.

### 8.1. Cần giữ những liên kết nào?

| Liên kết | Câu hỏi nó giúp trả lời |
|---|---|
| PBI → Product Goal/vấn đề người dùng | “Tại sao chúng ta ưu tiên công việc này?” |
| PBI được chọn → Sprint Goal | “Tại sao việc này liên quan kết quả Sprint?” |
| PBI → acceptance criteria | “Hành vi đúng được mô tả và kiểm chứng ra sao?” |
| PBI/PR/build/test → Increment | “Thay đổi nào đã tích hợp và đáp ứng DoD?” |
| Increment → kết quả quan sát | “Sau khi có phần mềm, người dùng có hành động khác đi không?” |
| Phản hồi mới → Product Backlog | “Thông tin mới dẫn tới quyết định ưu tiên nào?” |

Độ chi tiết của dấu vết nên **tương xứng rủi ro**. Thay đổi bảo mật hoặc quy tắc tài chính quan trọng có thể cần bằng chứng nhiều hơn sửa thông báo giao diện đơn giản. Mục đích là giúp ra quyết định và kiểm tra, không phải tạo kho tài liệu khó bảo trì.

## 9. Khi một PBI được chọn nhưng chưa đạt DoD

Đây là tình huống kiểm tra mức minh bạch thực sự của Scrum Team.

Giả sử Sprint Backlog có PBI “Lưu tiến độ bài đầu”. Developer hoàn tất code và đánh dấu Done. Tester phát hiện trên mạng chập chờn, giao diện báo “Đã lưu” trong khi backend chưa xác nhận.

### 9.1. Cách trình bày thiếu minh bạch

> “PBI đã hoàn thành 100%, chỉ còn một lỗi nhỏ; cho vào Increment rồi sửa sau.”

Cách này làm mờ nghĩa “Done”, gây rủi ro mất dữ liệu và khiến Sprint Review hiểu nhầm về phần sản phẩm đã dùng được.

### 9.2. Cách xử lý theo ba tạo tác

**Ở Product Backlog:** PBI vẫn là công việc cần được hoàn tất; nếu không đạt DoD trong Sprint, đưa lại Product Backlog để xem xét trong tương lai và sắp thứ tự theo giá trị/rủi ro thực.

**Ở Sprint Backlog:** Developers minh bạch lỗi, cập nhật kế hoạch xử lý và kiểm tra tác động tới Sprint Goal. Nhóm có thể thương lượng phạm vi với Product Owner, ví dụ hoãn hiệu ứng màn hình phụ để tập trung hoàn tất hành vi lưu.

**Ở Increment:** chỉ bao gồm phần thực sự đạt DoD và được tích hợp. Không gộp PBI chưa đạt DoD vào Increment hoặc trình bày nó như đã Done.

### 9.3. Khi nào cần hỏi Product Owner?

Developers có trách nhiệm về kế hoạch và chất lượng, nhưng khi việc xử lý lỗi làm thay đổi phạm vi sản phẩm, thứ tự ưu tiên hoặc khả năng đạt Sprint Goal, nên trao đổi với Product Owner. Nếu có ràng buộc an toàn, hợp đồng hoặc vận hành, cần tham vấn người có thẩm quyền tương ứng.

**Không được hạ DoD để giữ số ticket Done đẹp.** Trường hợp cần điều chỉnh tiêu chuẩn chất lượng phải được đánh giá minh bạch, tuân thủ chuẩn tổ chức và không hợp thức hóa phần còn thiếu chỉ vì gần hết Sprint.

## 10. Tình huống xuyên suốt: nền tảng học và ba lớp minh bạch

### 10.1. Product Goal và bằng chứng ban đầu

Một Scrum Team quản lý nền tảng học trực tuyến có Product Goal:

> “Người học mới có thể đăng ký, bắt đầu và hoàn thành bài đầu tiên thuận lợi, với tiến độ được lưu tin cậy.”

Quan sát **giả định minh họa** cho thấy có người hoàn thành đăng ký nhưng không bắt đầu học; hỗ trợ khách hàng cũng nhận phản ánh về lỗi lưu tiến độ trên điện thoại.

Product Owner cùng Developers và người liên quan làm rõ vấn đề, sau đó sắp thứ tự Product Backlog:

| Thứ tự minh họa | PBI | Vì sao liên quan Product Goal? | Điều còn chưa rõ |
|---|---|---|---|
| 1 | Sửa lỗi lưu tiến độ không nhất quán | Tránh mất công sức và bỏ dở khi học | Lỗi phụ thuộc thiết bị hay mạng? |
| 2 | Nút mở bài đầu từ màn chào mừng | Giảm khó khăn ở bước bắt đầu | Có thực sự làm tăng tỷ lệ hoàn thành không? |
| 3 | Cải thiện thông báo khi lưu lỗi | Người học hiểu trạng thái và xử lý | Thông điệp nào dễ hiểu trên thiết bị di động? |
| 4 | Tùy chọn giao diện nền tối toàn bộ | Có thể có giá trị về trải nghiệm | Liên hệ với vấn đề trọng tâm chưa được chứng minh |

Backlog không che điều chưa biết. Việc chia nhỏ các PBI ưu tiên cao được thực hiện khi cần để có thể chọn lát cắt đáng tin.

### 10.2. Sprint Planning: mục tiêu và phạm vi lựa chọn

Scrum Team hình thành Sprint Goal:

> “Người học mới có thể mở bài đầu và biết chính xác khi nào tiến độ đã được lưu.”

Developers chọn các PBI và lập kế hoạch tích hợp theo luồng đầu–cuối. Phần giao diện nền tối được giữ trong Product Backlog, không trở thành “việc bắt buộc” chỉ vì đã xuất hiện trong một kế hoạch trước.

### 10.3. Trong Sprint: thông tin thực tế thay đổi

Trong khi kiểm thử, nhóm phát hiện:

- Đường dẫn mở bài hoạt động trên desktop nhưng có lỗi phiên đăng nhập trên mobile.
- Luồng lưu tiến độ có rủi ro báo thành công khi dịch vụ gửi lỗi.
- Một số PBI đang chờ môi trường thử, tạo WIP cao.

Developers dùng Daily Scrum để kiểm tra tiến độ tới Sprint Goal. Nhóm minh bạch blocker và điều chỉnh kế hoạch: giảm nhận việc mới, ưu tiên kiểm thử tích hợp và làm rõ quy tắc hiển thị lỗi.

Đây là **Sprint Backlog thích ứng**, không phải dấu hiệu Sprint Backlog “bị làm sai” vì không giữ nguyên ảnh chụp ban đầu.

### 10.4. Increment được kiểm chứng bằng DoD

Cuối Sprint, giả sử:

| Phần công việc | Trạng thái thực | Có thuộc Increment? |
|---|---|---|
| Mở bài đầu từ màn chào mừng | Đã tích hợp, đạt các kiểm thử và DoD liên quan | **Có** |
| Lưu tiến độ trong luồng chính và khi mất kết nối | Đã xử lý trường hợp biên, kiểm thử và đạt DoD | **Có** |
| Hiệu ứng hình ảnh nâng cao | Mới có bản thiết kế, chưa tích hợp | **Không** |
| Báo cáo phân tích học tập | Chưa được chọn hoặc chưa hoàn thành | **Không** |

Trong Sprint Review, nhóm minh họa **Increment thực sự** và trao đổi giới hạn phạm vi. Việc một ý tưởng khác chưa triển khai không làm mất giá trị Increment, miễn phần được coi là Done đáp ứng DoD và tích hợp hoạt động.

### 10.5. Sprint Review: kiểm tra tác động, không chỉ trình diễn output

Stakeholder và Scrum Team kiểm tra luồng học hoạt động, phản hồi từ người dùng thử, các tình huống lỗi đã xử lý. Giả sử chỉ số **hoàn toàn minh họa**:

| Tín hiệu | Trước thay đổi | Sau thay đổi | Diễn giải thận trọng |
|---|---:|---:|---|
| Người mới mở bài trong phiên đầu | 50% | 63% | Tín hiệu tốt về việc bắt đầu, cần kiểm tra phân khúc |
| Người mới hoàn thành bài đầu trong 7 ngày | 24% | 25% | Mức thay đổi nhỏ, chưa đủ để khẳng định Product Goal đạt |
| Lỗi lưu tiến độ nghiêm trọng được báo | 7 | 2 | Cần so phạm vi, lượng người dùng và thời gian quan sát |

Các số trên không chứng minh quan hệ nhân quả. Nhóm có thể cần nghiên cứu vì sao người học mở bài nhiều hơn nhưng vẫn chưa hoàn thành, đồng thời tiếp tục theo dõi độ ổn định lưu tiến độ.

### 10.6. Product Backlog đổi theo điều vừa học

Product Owner có thể ưu tiên nghiên cứu nội dung bài đầu quá khó hoặc cải thiện hướng dẫn học giữa bài, thay vì tự động tăng đầu tư vào màn chào mừng. Scrum Team đã khép vòng:

**Product Goal → Product Backlog → Sprint Goal/Sprint Backlog → Increment đạt DoD → bằng chứng sử dụng → Product Backlog được thích ứng.**

Mỗi tạo tác làm minh bạch một lớp của quyết định, và kết quả của Increment tạo dữ liệu mới cho lớp tiếp theo.

## 11. Những tình huống đặc biệt cần hiểu đúng

### 11.1. Nhiều Increment trong cùng một Sprint

Scrum không yêu cầu đợi đến ngày cuối Sprint để tạo Increment. Mỗi khi PBI đáp ứng DoD và phần mới được tích hợp với các Increment trước, Increment có thể xuất hiện. Có thể có nhiều Increment trong một Sprint và có thể phát hành trước Sprint Review theo điều kiện sản phẩm.

Việc phát hành hay mở cho người dùng sử dụng cần tuân thủ quy trình an toàn, vận hành và ràng buộc áp dụng. **“Đạt DoD” và “đã phát hành tới tất cả người dùng” không phải một khái niệm.**

### 11.2. Nhiều Scrum Team cùng làm một sản phẩm

Khi nhiều Scrum Team làm chung một sản phẩm, họ cần dùng **cùng một Product Goal, Product Backlog và Product Owner**. Increment phải hoạt động tích hợp; các Scrum Team cần **cùng một Definition of Done** để không có hai cách hiểu trái ngược về chất lượng sản phẩm.

Mỗi Scrum Team vẫn tự quản lý công việc của mình và sử dụng Sprint Backlog phù hợp. Nếu mỗi nhóm có một chuẩn Done khác nhau, tình trạng “nhóm A đã xong nhưng sản phẩm chưa dùng được” có thể lặp lại.

### 11.3. Công việc đang làm chỉ tạo kiến thức, chưa tạo tính năng

Phỏng vấn người dùng, spike kỹ thuật hay khảo sát rủi ro có thể rất hữu ích để điều chỉnh Product Backlog. Nhưng **kết quả nghiên cứu không tự động là Increment phần mềm có thể sử dụng**.

Nên báo đúng loại kết quả:

- **Điều đã học:** phát hiện nguyên nhân người học bỏ dở hoặc điều kiện API không được hỗ trợ.
- **Điều đã hoàn thành theo DoD:** phần sản phẩm hoạt động, được tích hợp và đạt chuẩn chất lượng.

Scrum Team có thể làm cả hai, miễn không đánh đồng kiến thức thu được với Increment đã tạo.

### 11.4. Một PBI phải chia qua nhiều Sprint

Chia một hạng mục lớn thành những lát cắt nhỏ **có giá trị và có thể hoàn tất** thường giúp nhận phản hồi sớm. Không nên dùng việc một epic có “70% hoàn thành” để khẳng định 70% giá trị đã được giao nếu chưa có Increment đạt DoD.

Nếu PBI không đạt DoD trong Sprint, việc chưa Done quay lại Product Backlog để xem xét tiếp. Developers không cần gắn điểm thành tích giả cho phần chưa hoàn thành để giữ số liệu tiến độ.

### 11.5. Product Goal được hoàn thành hoặc thay thế

Scrum Team tập trung vào **một Product Goal tại một thời điểm**. Nhóm cần hoàn thành hoặc từ bỏ Product Goal hiện tại trước khi nhận mục tiêu tiếp theo. Khi bối cảnh đổi, việc điều chỉnh Product Goal cần được truyền đạt rõ ràng để Product Backlog không giữ thứ tự dựa trên mục tiêu đã lỗi thời.

Điều này không ngăn đội xử lý lỗi, an toàn hoặc các nghĩa vụ vận hành trong quá trình theo đuổi mục tiêu.

## 12. Minh bạch trong công cụ: không đồng nghĩa với nhiều biểu đồ

### 12.1. Một bảng minh bạch tối thiểu

Nhóm có thể chọn thể hiện:

| Nguồn thông tin | Điều tối thiểu nên rõ | Ai dùng để quyết định? |
|---|---|---|
| Product Goal | Kết quả tương lai và đối tượng hưởng giá trị | Scrum Team, stakeholders, Product Owner |
| Product Backlog | PBI được sắp thứ tự, rủi ro, vấn đề chưa rõ | Product Owner và Scrum Team |
| Sprint Goal | Mục tiêu duy nhất cần bảo vệ trong Sprint | Developers, Product Owner, Scrum Master |
| Sprint Backlog | PBI đã chọn, kế hoạch thật, blocker, các thay đổi quan trọng | Developers và Scrum Team |
| Definition of Done | Chuẩn chất lượng được thống nhất, nhất quán | Scrum Team và người nhận Increment |
| Increment | Điều đã tích hợp, kiểm chứng và đủ chất lượng | Scrum Team và stakeholders |
| Phản hồi sản phẩm | Outcome, lỗi, nhu cầu mới và giới hạn của số liệu | Product Owner và Scrum Team |

Không phải mỗi hàng cần một trang hoặc một dashboard riêng. Dữ liệu chỉ tạo minh bạch khi **đúng, cập nhật và có ý nghĩa đối với quyết định**.

### 12.2. Kết hợp chỉ số dòng công việc

Các phép đo của Kanban có thể bổ trợ:

- **WIP:** số hạng mục bắt đầu nhưng chưa hoàn thành; giúp thấy khi nhóm mở quá nhiều việc.
- **Work item age:** công việc đang dở bao lâu; giúp phát hiện nguy cơ tắc.
- **Cycle time:** thời gian hạng mục đã hoàn thành đi qua workflow.
- **Throughput:** số hạng mục hoàn tất trong một khoảng thời gian.

Muốn dùng số đo, cần thống nhất **điểm bắt đầu, điểm kết thúc và định nghĩa Done**. Nếu chuyển PBI chưa đạt DoD thành Done để cải thiện throughput, nhóm đang làm **mất minh bạch**.

Những số đo này giúp dự báo và cải thiện luồng, **không thay thế Product Goal hay đo trực tiếp giá trị người dùng**.

### 12.3. Kết hợp thực hành XP để Increment đáng tin

Các kỹ thuật **Extreme Programming (XP)** như kiểm thử tự động, TDD khi phù hợp, tích hợp liên tục, pair programming và refactoring giúp giảm chi phí của thay đổi và phản hồi kỹ thuật sớm.

Ví dụ, một kiểm thử tích hợp phát hiện lỗi lưu tiến độ ngay trong ngày có thể giúp Developers điều chỉnh Sprint Backlog trước khi rủi ro lan rộng. Đây là cách thực hành kỹ thuật hỗ trợ **minh bạch chất lượng** của Increment.

Scrum không bắt buộc phải áp dụng một kỹ thuật XP cụ thể. Điều cần giữ là **trách nhiệm tạo Increment đạt DoD**, có thể đạt bằng các thực hành phù hợp với bối cảnh.

## 13. Các ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai hoặc nguy hiểm? | Cách hiểu đúng |
|---|---|---|
| “Ba tạo tác Scrum là Product Backlog, burndown chart và user story.” | Nhầm công cụ tùy chọn với artifacts chính thức | Ba artifact: Product Backlog, Sprint Backlog, Increment |
| “Product Goal là danh sách tất cả tính năng cần làm.” | Mất định hướng kết quả người dùng | Product Goal mô tả trạng thái tương lai; PBI là việc có thể giúp đạt mục tiêu |
| “Backlog đã chốt đầu dự án thì không được sửa.” | Không thể thích ứng khi có phản hồi mới | Product Backlog là emergent, được sắp thứ tự và cập nhật |
| “Sprint Backlog thuộc Product Owner hoặc quản lý.” | Developers mất quyền tự quản lý kế hoạch thực hiện | Sprint Backlog là kế hoạch của Developers và cho Developers |
| “Sprint Goal là tổng tất cả ticket của Sprint.” | Không còn mục tiêu gắn kết để thương lượng phạm vi | Sprint Goal là mục tiêu duy nhất giải thích vì sao Sprint có giá trị |
| “Bất kỳ thay đổi nào trong Sprint đều sai Scrum.” | Bỏ qua thông tin mới và giữ kế hoạch không khả thi | Điều chỉnh Sprint Backlog khi học thêm, bảo vệ Sprint Goal và chất lượng |
| “Code merge rồi thì chắc chắn Done.” | Có thể chưa kiểm thử, chưa tích hợp hoạt động hoặc chưa đạt chuẩn | Done phải theo Definition of Done |
| “Acceptance criteria và DoD là một.” | Bỏ sót chuẩn chung như tích hợp, bảo mật, hồi quy | AC cho hành vi PBI; DoD cho chất lượng Increment |
| “Sprint Review là buổi ký duyệt release.” | Nhầm cơ hội kiểm tra và thích ứng với cổng phát hành | Increment có thể giao sớm, Review để kiểm tra kết quả và bối cảnh |
| “Chỉ cuối Sprint mới được có Increment.” | Phản hồi bị chậm, tích hợp có thể dồn cuối | Nhiều Increment có thể hình thành trong một Sprint |
| “Mỗi Scrum Team có một DoD riêng dù cùng một sản phẩm.” | Không có chuẩn chất lượng thống nhất khi tích hợp | Các Scrum Team trên cùng sản phẩm phải cùng DoD |
| “Tám ticket Done chứng minh Product Goal đã đạt.” | Đếm output không xác nhận outcome người dùng | Cần xem Increment, DoD và bằng chứng từ sản phẩm |
| “Càng nhiều dashboard càng minh bạch.” | Dữ liệu trùng, sai định nghĩa hoặc khó hiểu | Dùng nguồn thông tin đáng tin và câu hỏi ra quyết định cụ thể |
| “Thấy một lỗi tức là Sprint thất bại.” | Khuyến khích giấu lỗi và đánh giá sai cơ chế học | Làm rõ lỗi, ảnh hưởng tới DoD/Sprint Goal, điều chỉnh có trách nhiệm |

## 14. Checklist đánh giá tính minh bạch của ba tạo tác

### Với Product Backlog

- Product Goal có được mô tả dễ hiểu đối với Scrum Team và stakeholders không?
- PBI ở đầu có lý do ưu tiên và vấn đề người dùng hoặc rủi ro liên quan không?
- Có một nguồn công việc rõ cho sản phẩm, hay có backlog riêng ẩn?
- Các giả định, phụ thuộc và điều chưa biết của PBI quan trọng có được làm rõ không?
- Backlog có thay đổi khi có bằng chứng mới hay chỉ lặp lại kế hoạch cũ?

### Với Sprint Backlog

- Sprint Goal có diễn đạt **kết quả cần đạt**, không chỉ số việc phải đóng không?
- Developers có nhìn thấy kế hoạch thực và cập nhật nó khi học thêm thông tin không?
- Có biết PBI nào bị chặn và ảnh hưởng tới Sprint Goal không?
- Khi phạm vi thay đổi, nhóm có trao đổi với Product Owner để bảo vệ mục tiêu không?
- Daily Scrum có giúp điều chỉnh kế hoạch hay chỉ là lượt báo cáo cá nhân?

### Với Increment và Definition of Done

- Có một DoD rõ, phù hợp tiêu chuẩn tổ chức và được các thành viên hiểu giống nhau không?
- Những hạng mục gọi là Done có thực sự đạt DoD và tích hợp với phần trước không?
- Có xử lý đúng trường hợp lỗi, an toàn và chất lượng liên quan thay vì chỉ demo đường đi thuận lợi không?
- Phần chưa đạt DoD có được loại khỏi Increment và phản ánh đúng trong backlog không?
- Sprint Review cho thấy phần sản phẩm hoàn thành thật và thảo luận kết quả sử dụng không?

### Với toàn vòng phản hồi

- Mỗi quyết định thay đổi ưu tiên có nối lại với Product Goal hoặc rủi ro rõ ràng không?
- Phản hồi từ Increment có được sử dụng để kiểm tra và thích ứng không?
- Những chỉ số đang đo có nhất quán với cách nhóm xác định hoàn thành không?
- Nhóm có phân biệt **output đã giao**, **outcome đã quan sát** và **điều chưa biết** không?

## 15. Bài tập thực hành

### Bài tập 1 — Ghép artifact với commitment

Hoàn thiện bảng sau và giải thích vì sao từng cặp hỗ trợ minh bạch:

| Artifact | Commitment cần điền | Câu hỏi giúp trả lời |
|---|---|---|
| Product Backlog | ? | Sản phẩm hướng tới trạng thái tương lai nào? |
| Sprint Backlog | ? | Sprint này cần đạt một mục tiêu gắn kết nào? |
| Increment | ? | Phần đã giao có đáp ứng chuẩn chất lượng không? |

**Gợi ý:** lần lượt là Product Goal, Sprint Goal và Definition of Done. Không nhầm Sprint Goal với Definition of Ready hoặc Product Goal với roadmap tính năng.

### Bài tập 2 — Phát hiện báo cáo “Done” sai

Một Sprint có năm PBI, trong đó ba PBI đã tích hợp và đạt DoD, một PBI chưa hoàn thành kiểm thử bảo mật, một PBI chỉ có giao diện mẫu chưa nối backend. Quản lý yêu cầu báo cáo “5/5 Done vì code đã được đẩy lên repository”.

**Yêu cầu:**

1. Hãy nêu điều gì thực sự có thể coi là Increment.
2. Giải thích vì sao hai PBI còn lại không được gọi là Done.
3. Viết một cập nhật minh bạch không đổ lỗi cá nhân.
4. Nêu câu hỏi cần trao đổi nếu việc chưa xong ảnh hưởng Sprint Goal.

**Gợi ý:** ba PBI đã đạt DoD có thể góp phần vào Increment nếu chúng được tích hợp, hoạt động cùng nhau và đáp ứng chất lượng. Hai PBI còn lại cần được đánh giá đúng trạng thái; không dùng “95% code” thay cho Done.

### Bài tập 3 — Liên kết mục tiêu dài và mục tiêu Sprint

Product Goal của nền tảng đặt lịch là **“Giảm tỷ lệ người dùng bỏ dở trước khi xác nhận lịch hẹn.”** Product Backlog có:

- Hiển thị thời gian và địa điểm rõ trước khi xác nhận.
- Thêm hiệu ứng giao diện trang chủ.
- Sửa lỗi bấm xác nhận hai lần tạo lịch trùng.
- Nghiên cứu vì sao người dùng không hoàn thành bước cuối.
- Bổ sung một kênh thông báo mới chưa có bằng chứng về nhu cầu.

**Yêu cầu:** đề xuất một Sprint Goal có giá trị, chọn một số PBI phù hợp, giải thích vì sao không chọn các mục khác và nêu phần Increment tối thiểu đủ kiểm chứng.

**Gợi ý:** có thể tập trung vào xác nhận lịch chính xác và tin cậy; việc sửa lỗi trùng có rủi ro cao. Không bắt buộc phải “làm tất cả” trong Sprint.

### Bài tập 4 — Viết acceptance criteria và DoD đúng vai trò

PBI: **“Người học có thể gửi lại email kích hoạt tài khoản khi chưa nhận được thư.”**

**Yêu cầu:**

1. Viết ba acceptance criteria cho trường hợp gửi thành công, yêu cầu liên tiếp và lỗi dịch vụ gửi.
2. Đề xuất bốn điểm trong Definition of Done phù hợp sản phẩm.
3. Giải thích vì sao kiểm thử acceptance criteria đạt nhưng vẫn chưa tích hợp hoặc chưa đạt bảo mật thì PBI chưa Done.
4. Nêu một outcome cần theo dõi sau phát hành.

**Gợi ý:** DoD có thể gồm tích hợp, kiểm thử hồi quy, an toàn thông tin và quan sát vận hành; outcome có thể là tỷ lệ kích hoạt thành công hoặc giảm yêu cầu hỗ trợ.

### Bài tập 5 — Sprint Backlog phải thích ứng như thế nào?

Sprint Goal: **“Người mua có thể xem giá cuối và xác nhận đơn hàng chính xác.”** Giữa Sprint, Developers phát hiện lỗi tính phí vận chuyển; nếu xử lý triệt để, tính năng trang trí khác có thể chưa kịp.

**Yêu cầu:** lập bảng gồm dữ kiện mới, ảnh hưởng tới Sprint Goal, các PBI đang làm, phương án thương lượng với Product Owner và thay đổi kế hoạch kiểm thử. Chỉ rõ điều không được đánh đổi.

**Gợi ý:** ưu tiên độ chính xác tổng tiền và kiểm soát lỗi; có thể hoãn trang trí, nhưng không hạ Definition of Done để giữ báo cáo Done.

### Bài tập 6 — Đọc chỉ số mà không nhầm với giá trị

Một nhóm báo cáo tăng throughput từ 12 lên 20 PBI/tuần. Cùng lúc, lỗi sau phát hành tăng và người dùng vẫn gặp khó hoàn thành bước thanh toán.

**Yêu cầu:**

1. Phép đo throughput nói được gì, không nói được gì?
2. Có cần kiểm tra xem định nghĩa Done hoặc cách chia PBI đã thay đổi không?
3. Hãy chọn hai tín hiệu chất lượng và hai tín hiệu outcome bổ sung.
4. Đề xuất một điều chỉnh trong Product Backlog hoặc Sprint Backlog dựa trên bằng chứng.

**Gợi ý:** throughput giúp nhìn luồng; nó không tự cho biết Product Goal đạt hay Increment đáng tin. Đừng kết luận nhóm hiệu quả hơn chỉ từ một số tăng.

### Bài tập 7 — Vẽ dòng truy vết cho dự án của bạn

Chọn một tính năng trong dự án thật và điền:

~~~text
Product Goal:
Vấn đề người dùng / rủi ro sản phẩm:
Product Backlog Item và lý do ưu tiên:
Sprint Goal:
PBI được chọn trong Sprint:
Kế hoạch Developers đang thực hiện:
Acceptance criteria:
Definition of Done áp dụng:
Increment thực sự hoàn thành:
Phần chưa đạt DoD, nếu có:
Tín hiệu chất lượng:
Outcome người dùng cần quan sát:
Điều học được và thay đổi Product Backlog tiếp theo:
~~~

**Tự đánh giá:** một người mới vào nhóm có thể phân biệt được **mục tiêu dài hạn**, **mục tiêu Sprint**, **phần đã hoàn thành theo DoD** và **bằng chứng cần kiểm tra** chỉ từ những liên kết này hay không?

## 16. Tổng kết

Ba tạo tác Scrum không chỉ để lưu công việc hoặc báo cáo tiến độ. Chúng là ba góc nhìn bổ trợ cho **một sản phẩm và một chu trình học hỏi thực nghiệm**.

1. **Product Backlog + Product Goal:** minh bạch **đích đến và thứ tự công việc** để cải thiện sản phẩm; các PBI có thể thay đổi khi xuất hiện thông tin mới.
2. **Sprint Backlog + Sprint Goal:** minh bạch **mục tiêu ngắn hạn và kế hoạch của Developers**; kế hoạch có thể thích ứng trong Sprint khi hiểu biết tăng, nhưng không làm nguy hại Sprint Goal.
3. **Increment + Definition of Done:** minh bạch **phần sản phẩm thực sự hoàn thành**; chỉ phần tích hợp đạt chuẩn chất lượng mới được coi là Increment.
4. **Artifacts hỗ trợ ba trụ cột:** minh bạch đủ tin cậy cho phép kiểm tra thực tế; inspection có ý nghĩa dẫn tới thích ứng, thay vì chỉ duy trì nghi thức.
5. **Đếm việc không bằng tạo giá trị:** output hoàn thành phải được phân biệt với outcome người dùng và mức tiến tới Product Goal.
6. **Công cụ hỗ trợ không thay framework:** user story, acceptance criteria, bảng Kanban, chỉ số luồng và thực hành XP có thể làm minh bạch và chất lượng tốt hơn khi được dùng đúng mục đích.

> **Câu hỏi ghi nhớ:** “Nhìn vào Product Backlog, Sprint Backlog và Increment hôm nay, chúng ta có thể giải thích rõ **vì sao làm**, **đang làm gì** và **điều gì thật sự đã hoàn thành** — mà không cần tô đẹp trạng thái công việc hay không?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — định nghĩa ba artifacts và commitments, trách nhiệm Product Owner/Developers, Increment, Definition of Done và sự kiểm tra/thích ứng.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giao phần mềm có giá trị, cộng tác và thích ứng qua phản hồi sớm.
- [The Kanban Guide](https://kanbanguides.org/) — WIP, throughput, work item age và cycle time hỗ trợ quan sát dòng công việc.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — kiểm thử, tích hợp thường xuyên và thực hành kỹ thuật hỗ trợ Increment chất lượng.
