# Sprint Backlog và cam kết Sprint Goal

## 1. Vì sao Scrum cần cả kế hoạch và một mục tiêu chung?

Một Scrum Team phát triển nền tảng học trực tuyến chọn những công việc sau cho Sprint: bổ sung đăng ký khóa miễn phí, hiển thị trạng thái đăng ký, cập nhật danh sách khóa đã học và xử lý lỗi khi người học bấm đăng ký hai lần. Đến giữa Sprint, việc tích hợp khó hơn dự đoán. Một số tác vụ ban đầu không còn phù hợp, trong khi nhóm phát hiện phải bổ sung kiểm thử để ngăn đăng ký trùng.

Nếu chỉ xem Sprint là **danh sách task phải hoàn thành nguyên vẹn**, nhóm dễ chạy theo số lượng hạng mục hoặc làm thêm giờ để giữ kế hoạch cũ, ngay cả khi nhu cầu thực tế đã thay đổi. Nếu chỉ có một khẩu hiệu “tạo giá trị” mà không có kế hoạch minh bạch, nhóm lại khó phối hợp, theo dõi tiến độ và nhận ra rủi ro sớm.

Scrum kết nối hai điều này thông qua:

- **Sprint Goal:** Một mục tiêu duy nhất của Sprint, diễn đạt *vì sao Sprint có giá trị* và tạo sự tập trung, gắn kết cho Scrum Team.
- **Sprint Backlog:** Kế hoạch của Developers, dành cho Developers, gồm Sprint Goal, những Product Backlog Item được chọn và kế hoạch hành động để tạo Increment.

Trong Scrum, **Sprint Backlog là artifact** và **Sprint Goal là commitment gắn với artifact đó**. Sprint Backlog không bị đóng băng sau Sprint Planning; Developers tiếp tục điều chỉnh khi học thêm. Ngược lại, Sprint Goal đem lại định hướng tương đối ổn định để các điều chỉnh ấy không trở thành đổi ưu tiên tùy tiện.

Chủ đề thuộc chương **Tạo tác Scrum** của module **AGILE_DEVELOPMENT**. Hiểu đúng mối quan hệ này giúp nhóm dùng user story và product backlog để giao sản phẩm tăng dần, nhận phản hồi sớm, duy trì chất lượng và cải tiến liên tục. Một số kỹ thuật Kanban hoặc XP có thể bổ trợ, nhưng không làm thay đổi định nghĩa chính thức của Scrum.

## 2. Sprint Backlog là gì?

Theo Scrum, Sprint Backlog gồm **ba thành phần liên kết**:

| Thành phần | Câu hỏi | Chức năng trong Sprint |
| --- | --- | --- |
| **Sprint Goal** | **Why — Vì sao?** | Một mục tiêu thể hiện giá trị mà Scrum Team cùng hướng tới |
| **Product Backlog Item (PBI) được chọn** | **What — Làm gì?** | Những hạng mục Developers dự báo có thể hoàn thành để hỗ trợ mục tiêu |
| **Kế hoạch hành động** | **How — Làm thế nào?** | Cách Developers dự định tạo Increment, phối hợp, kiểm thử và tích hợp |

Ba thành phần không phải ba tài liệu bắt buộc phải lưu ở ba nơi khác nhau. Nhóm có thể thể hiện chúng trên bảng công việc, tài liệu chia sẻ hoặc công cụ quản lý sản phẩm, miễn **đủ minh bạch để Developers và Scrum Team kiểm tra tiến độ tới Sprint Goal**.

~~~mermaid
flowchart TD
    SB["Sprint Backlog"]
    SG["Sprint Goal: Why — mục tiêu và giá trị"]
    PBI["PBI được chọn: What — phạm vi dự báo"]
    PLAN["Kế hoạch hành động: How — cách tạo Increment"]
    DONE["Increment đáp ứng Definition of Done"]
    SB --> SG
    SB --> PBI
    SB --> PLAN
    PLAN --> DONE
    SG -. "Định hướng các lựa chọn" .-> PLAN
~~~

### 2.1. “Kế hoạch của Developers, dành cho Developers”

Sprint Backlog do **Developers** lập và cập nhật. Họ cần tự quản cách phối hợp kỹ thuật, phân chia công việc khi cần, kiểm thử và tích hợp để tạo Increment có thể sử dụng. Product Owner và Scrum Master không đứng ngoài Sprint Planning, nhưng **không thay Developers lập danh sách task như một cấp quản lý giao việc**.

Một Sprint Backlog hữu ích:

- Có Sprint Goal dễ nhận diện và hiểu được.
- Thể hiện những PBI đã chọn và các thông tin cần để phát triển.
- Có kế hoạch đủ chi tiết để nhận ra việc nào gần Done, việc nào đang bị chặn và bước tiếp theo.
- Được cập nhật khi hiểu thêm yêu cầu, rủi ro hoặc cách làm.
- Phản ánh **tiến độ tới mục tiêu**, không chỉ tỷ lệ task riêng lẻ đã đóng.

Sprint Backlog không bắt buộc phải là biểu đồ burndown, bảng Kanban điện tử hoặc bảng tính cố định. Scrum không quy định một công cụ trình bày duy nhất.

### 2.2. Phân biệt Sprint Backlog với Product Backlog

| Tiêu chí | Product Backlog | Sprint Backlog |
| --- | --- | --- |
| Phạm vi | Những gì cần để cải thiện sản phẩm, phát triển liên tục | Kế hoạch công việc cho Sprint đang diễn ra |
| Artifact commitment | **Product Goal** | **Sprint Goal** |
| Trách nhiệm chính | Product Owner chịu trách nhiệm quản lý hiệu quả, gồm sắp thứ tự | Developers tạo và điều chỉnh kế hoạch |
| Nội dung | Các PBI được sắp thứ tự; mức chi tiết thay đổi theo nhu cầu | Sprint Goal, PBI được chọn và kế hoạch giao Increment |
| Thay đổi | Được làm rõ, thêm bớt và sắp thứ tự lại khi học thêm | Được điều chỉnh trong Sprint, với Sprint Goal làm định hướng |

Không nên diễn giải rằng Product Owner “sở hữu mọi task của Sprint”. Product Owner quản lý thứ tự Product Backlog và tối đa hóa giá trị; Developers chịu trách nhiệm tạo kế hoạch thực hiện.

## 3. Sprint Goal là cam kết gì?

**Sprint Goal là mục tiêu duy nhất của Sprint.** Nó tạo sự tập trung và tính gắn kết, giúp Scrum Team làm việc cùng nhau thay vì theo đuổi các sáng kiến rời rạc. Sprint Goal được tạo trong **Sprint Planning**, được thống nhất trước khi kết thúc sự kiện này và được thêm vào Sprint Backlog.

Sprint Goal vừa **định hướng**, vừa cho phép **linh hoạt về công việc cụ thể** cần làm để đạt mục tiêu. Khi xuất hiện thông tin mới, Developers có thể điều chỉnh kế hoạch, trao đổi với Product Owner về phạm vi, miễn không tạo thay đổi gây nguy hiểm cho Sprint Goal và không hạ chất lượng.

### 3.1. “Cam kết” không đồng nghĩa “mọi PBI là lời hứa bất biến”

Trong Scrum có ba artifact và ba commitment tương ứng:

| Artifact | Commitment | Ý nghĩa |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Đích sản phẩm dài hạn giúp định hướng những thay đổi cần thực hiện |
| **Sprint Backlog** | **Sprint Goal** | Mục tiêu duy nhất của Sprint, tạo sự tập trung và linh hoạt về cách thực hiện |
| **Increment** | **Definition of Done** | Tiêu chuẩn chất lượng để xác định công việc thực sự hoàn tất |

Cam kết với Sprint Goal có nghĩa cả Scrum Team cùng hướng tới mục tiêu đó, kiểm tra và điều chỉnh công việc để đạt được. Nó **không biến mọi PBI được dự báo ở Sprint Planning thành một bản hợp đồng không được thay đổi**, cũng không phải bảo đảm không thể gặp rủi ro.

Không nên nhầm sự linh hoạt này với việc tùy ý thay Sprint Goal mỗi ngày. Nếu mục tiêu đã không còn giá trị, chỉ **Product Owner** có thẩm quyền hủy Sprint; không có quy tắc cho phép Developers tự ý đổi mục tiêu để hợp thức hóa kế hoạch bị trễ.

### 3.2. Sprint Goal tốt cần thể hiện điều gì?

Một Sprint Goal hữu ích thường:

1. **Nêu kết quả mong muốn hoặc giá trị cụ thể**, không chỉ liệt kê task kỹ thuật.
2. **Đủ tập trung** để giúp lựa chọn ưu tiên khi có trở ngại hoặc thay đổi.
3. **Có thể kiểm tra tiến độ và đánh giá mức đạt được** thông qua kết quả sản phẩm hoặc bằng chứng học hỏi thích hợp.
4. **Phù hợp năng lực và rủi ro thực tế** trong độ dài Sprint.
5. **Đủ linh hoạt về giải pháp** để Developers chủ động tìm cách đạt mục tiêu.
6. **Gắn với hướng Product Goal** hoặc nhu cầu sản phẩm có ý nghĩa, không phải nhiệm vụ rời rạc.

Sprint Goal không bắt buộc phải theo một công thức ngôn ngữ hay mẫu SMART cứng. Một số Sprint tập trung giao khả năng người dùng, số khác giảm rủi ro kỹ thuật hoặc khám phá vấn đề. Điểm chung là **một mục tiêu có ý nghĩa để Scrum Team cùng hành động và kiểm tra**.

### 3.3. Phân biệt mục tiêu tốt và yếu

| Cách diễn đạt | Vấn đề hoặc ưu điểm |
| --- | --- |
| “Hoàn thành PBI-12, PBI-13, PBI-14 và PBI-15.” | Chỉ liệt kê item, chưa cho biết vì sao chúng có giá trị chung |
| “Mỗi Developer đóng ít nhất bốn task.” | Tập trung thành tích cá nhân, không phản ánh kết quả người dùng |
| “Làm xong toàn bộ công việc đã ước lượng.” | Không giúp đánh đổi khi xuất hiện thông tin mới |
| “Xây API, UI, database và email service.” | Liệt kê hoạt động kỹ thuật, chưa nói kết quả cho người dùng |
| **“Người học đã đăng nhập có thể đăng ký khóa miễn phí và nhận biết chắc chắn việc đăng ký thành công.”** | Có kết quả sử dụng và hướng ưu tiên khi cần điều chỉnh phạm vi |
| **“Chứng minh luồng cấp quyền học sau thanh toán có thể hoạt động an toàn trên môi trường tích hợp.”** | Có mục tiêu giảm rủi ro rõ, phù hợp Sprint thiên về khám phá kỹ thuật |

Mục tiêu tốt không có nghĩa luôn chỉ gồm một user story. Nhiều PBI có thể cùng hỗ trợ một Sprint Goal. Ngược lại, **không phải mỗi PBI đều cần một Sprint Goal riêng**.

## 4. Sprint Planning: từ mục tiêu đến kế hoạch

Sprint Planning đặt nền tảng cho Sprint và bao gồm ba chủ đề: **Why, What và How**. Toàn Scrum Team cộng tác, trong đó trách nhiệm từng bên được phân định rõ.

### 4.1. Why — Vì sao Sprint này có giá trị?

Product Owner đề xuất cách sản phẩm có thể tăng giá trị và tính hữu ích trong Sprint. Cả Scrum Team trao đổi để tạo Sprint Goal, kết nối công việc sắp làm với nhu cầu người dùng và Product Goal.

Ví dụ, Product Goal của nền tảng học trực tuyến là giúp người mới bắt đầu học thuận lợi. Sprint này có thể tập trung vào khả năng đăng ký khóa miễn phí và thấy xác nhận ngay trong tài khoản. Lý do giá trị rõ hơn việc chỉ nói “tạo ba màn hình”.

### 4.2. What — Có thể làm được gì trong Sprint?

Developers lựa chọn các PBI cho Sprint **thông qua trao đổi với Product Owner**. Để dự báo khả năng hoàn tất, họ cân nhắc:

- Hiểu biết về nội dung, độ phức tạp và các phụ thuộc.
- Năng lực sẵn có, nghỉ phép, vận hành và sự cố có thể ảnh hưởng.
- Hiệu suất giao hàng trước đây khi dữ liệu so sánh được.
- Yêu cầu của **Definition of Done**.
- Khả năng chia thành các lát cắt giá trị nhỏ, kiểm chứng được.

Điểm quan trọng là **chọn công việc dựa trên khả năng tạo Increment đủ chất lượng**, không chỉ chọn những gì Product Owner mong muốn về số lượng. Developers nên nêu rõ rủi ro, không dùng một nhãn “Ready” như bảo đảm chắc chắn sẽ hoàn tất.

### 4.3. How — Sẽ tạo Increment bằng cách nào?

Developers lập kế hoạch để chuyển các PBI đã chọn thành Increment đáp ứng DoD. Họ có thể chia công việc thành các đơn vị nhỏ hơn, thường đủ nhỏ để theo dõi trong ngày, và tiếp tục làm rõ trong Sprint.

Ví dụ:

- Trao đổi ví dụ chấp nhận cho việc đăng ký trùng.
- Thực hiện một lát cắt từ giao diện tới API và dữ liệu.
- Bổ sung xử lý lỗi và trạng thái xác nhận.
- Review, kiểm thử quyền truy cập, kiểm thử hồi quy và tích hợp.
- Chuẩn bị điều kiện vận hành cần thiết để đạt DoD.

Scrum **không bắt buộc** task phải gán cố định cho một người, không yêu cầu dùng story point, bảng burndown hoặc một công cụ hoạch định cụ thể. Các kỹ thuật này có thể hữu ích nếu giúp Developers kiểm tra tiến độ và thích ứng.

### 4.4. Kết thúc Sprint Planning cần có gì?

Scrum Team cần có **Sprint Goal** và Sprint Backlog đủ minh bạch để bắt đầu công việc. Developers có kế hoạch hành động mà họ có thể tiếp tục xây dựng chi tiết trong quá trình làm. Không cần giả vờ đã biết trước mọi tình huống biên, nhưng những rủi ro quan trọng có thể cản trở DoD cần được nêu rõ.

~~~mermaid
flowchart LR
    P["Product Goal và Product Backlog đã sắp thứ tự"]
    W["Why: Scrum Team tạo Sprint Goal"]
    T["What: Developers chọn PBI, trao đổi với Product Owner"]
    H["How: Developers lập kế hoạch tạo Increment"]
    S["Sprint Backlog minh bạch"]
    P --> W --> T --> H --> S
    S --> I["Thực hiện, kiểm tra và điều chỉnh trong Sprint"]
~~~

## 5. Ví dụ xuyên suốt: Sprint xây luồng đăng ký khóa miễn phí

Giả sử nền tảng học trực tuyến đang gặp phản hồi: người học chọn “Đăng ký” nhưng không biết hệ thống đã ghi nhận chưa, một số người bấm lại tạo yêu cầu trùng, và họ khó tìm khóa vừa đăng ký.

### 5.1. Product Goal, Sprint Goal và phạm vi ban đầu

**Product Goal ví dụ:** Người mới học có thể tìm, chọn và bắt đầu khóa học phù hợp với ít trở ngại.

**Sprint Goal ví dụ:**

> “Người học đã đăng nhập có thể đăng ký một khóa miễn phí và nhìn thấy xác nhận đáng tin cậy trong tài khoản.”

**Các PBI được chọn cho Sprint (ví dụ giả định):**

| PBI | Giá trị liên quan đến Sprint Goal | Rủi ro cần xem |
| --- | --- | --- |
| A — Đăng ký khóa miễn phí | Người học được ghi nhận đăng ký thành công | Trùng yêu cầu, quyền truy cập |
| B — Xác nhận trạng thái đăng ký | Người học biết yêu cầu đã thành công hay thất bại | Mất mạng, phản hồi không đồng bộ |
| C — Danh sách khóa đã đăng ký | Người học tìm thấy kết quả sau đăng ký | Dữ liệu giữa dịch vụ và giao diện |
| D — Email thông báo bổ sung | Người học có thêm kênh nhận thông tin | Phụ thuộc dịch vụ email ngoài hệ thống |

Giả sử email D được xem là **giá trị bổ sung** chứ không phải điều kiện pháp lý hay cam kết bắt buộc của luồng đăng ký. Với bối cảnh này, nhóm có thể ưu tiên A, B, C trước nếu D gặp rủi ro. Nếu email thực sự là yêu cầu thiết yếu đã được xác nhận, cách đánh đổi sẽ khác.

### 5.2. Kế hoạch How do Developers đề xuất

| Lát cắt công việc | Điều cần kiểm chứng để tiến tới Done | Người phối hợp gợi ý |
| --- | --- | --- |
| Làm rõ đăng ký hợp lệ, trùng và thất bại | Ví dụ chấp nhận rõ | Developers cùng Product Owner |
| Đăng ký qua giao diện, dịch vụ và dữ liệu | Ghi nhận đúng cho tài khoản | Developers chuyên môn liên quan |
| Hiển thị trạng thái đăng ký | Không báo thành công giả | Developers và người hỗ trợ kiểm thử |
| Danh sách khóa đã đăng ký | Người học xem được khóa của mình | Developers cùng kiểm thử luồng tích hợp |
| Review, kiểm thử, tích hợp theo DoD | Increment có thể sử dụng, đạt tiêu chuẩn chất lượng | Cả Developers cùng chịu trách nhiệm |

Bảng trên không biến người kiểm thử thành “người nhận toàn bộ việc ở cuối Sprint”. Developers cùng chịu trách nhiệm chất lượng, phối hợp liên tục theo năng lực và chuyên môn.

### 5.3. Đặt tiêu chí chấp nhận và DoD đúng chỗ

Một số tiêu chí chấp nhận của PBI A và B có thể là:

~~~gherkin
Tính năng: Đăng ký khóa miễn phí

  Tình huống: Đăng ký thành công
    Cho trước An đã đăng nhập
    Và khóa "Java nhập môn" cho phép đăng ký miễn phí
    Và An chưa đăng ký khóa này
    Khi An chọn đăng ký khóa "Java nhập môn"
    Thì hệ thống xác nhận đăng ký thành công
    Và khóa "Java nhập môn" xuất hiện trong danh sách đã đăng ký của An

  Tình huống: Gửi lại yêu cầu không tạo đăng ký trùng
    Cho trước An đã đăng ký khóa "Java nhập môn"
    Khi An gửi thêm yêu cầu đăng ký cùng khóa
    Thì không xuất hiện hai đăng ký đang có hiệu lực giống nhau cho An và khóa đó

  Tình huống: Dịch vụ đăng ký thất bại
    Cho trước An đã đăng nhập
    Và dịch vụ không thể xác nhận việc đăng ký
    Khi An yêu cầu đăng ký
    Thì giao diện không báo đã đăng ký thành công
    Và An nhận được thông tin phù hợp để thử lại hoặc kiểm tra trạng thái
~~~

Các tiêu chí này mô tả **hành vi của những PBI cụ thể**; chúng không thay thế DoD chung của sản phẩm. DoD có thể bao gồm tích hợp, kiểm thử bắt buộc, tiêu chuẩn bảo mật, chất lượng mã và điều kiện vận hành áp dụng. Những chi tiết chính xác phải được nhóm và tổ chức xác lập theo bối cảnh.

## 6. Sprint Backlog phát triển thế nào trong Sprint?

Sprint Backlog là **bức tranh hiển thị theo thời gian thực về công việc Developers dự định thực hiện để đạt Sprint Goal**. Nhóm cập nhật nó khi có hiểu biết mới, nhất là sau kiểm tra Increment, Daily Scrum, phản hồi kỹ thuật hoặc trao đổi với Product Owner.

### 6.1. Một chuỗi thay đổi minh họa

| Thời điểm | Điều nhóm học được | Thích ứng Sprint Backlog |
| --- | --- | --- |
| Ngày 1 | Luồng đăng ký cơ bản đã được làm rõ | Developers bắt đầu lát cắt từ UI tới dữ liệu, lên kiểm thử tích hợp |
| Ngày 3 | Bấm đăng ký hai lần có thể tạo bản ghi trùng | Thêm bước xử lý và kiểm thử thao tác lặp; ưu tiên hoàn tất trước |
| Ngày 5 | Dịch vụ email chưa sẵn sàng | Làm rõ với Product Owner liệu D có thiết yếu cho Sprint Goal không |
| Ngày 6 | Xác nhận trong ứng dụng đáp ứng kết quả cốt lõi đã thống nhất | Nếu hợp lệ, ưu tiên A–C và điều chỉnh phạm vi D theo trao đổi với Product Owner |
| Ngày 8 | Hàng chờ review và kiểm thử tích hợp tăng | Developers hỗ trợ review, gỡ nghẽn thay vì kéo thêm việc mới |
| Ngày 10 | Luồng A–C đáp ứng DoD | Minh bạch phần Done; PBI chưa Done quay về Product Backlog để cân nhắc lại |

Đây là **tình huống giả định**. Nó không có nghĩa mục tiêu Sprint chắc chắn sẽ đạt nếu bỏ email, mà cho thấy nhóm có thể giữ mục đích người dùng khi cách thực hiện và chi tiết phạm vi thay đổi **trong giới hạn đã trao đổi và được phép**.

### 6.2. Bản cập nhật Sprint Backlog cần rõ điều gì?

Một ghi chú ngắn sau Daily Scrum có thể là:

> **Sprint Goal:** Đăng ký khóa miễn phí và thấy xác nhận đáng tin cậy.  
> **Đã Done:** Lưu đăng ký vào tài khoản theo luồng cơ bản, đã tích hợp.  
> **Đang làm:** Ngăn bản ghi trùng và hiển thị xác nhận khi dịch vụ lỗi.  
> **Bị chặn:** Kiểm thử tích hợp trên thiết bị di động vì dữ liệu môi trường chưa sẵn sàng.  
> **Điều chỉnh:** Hai Developers ưu tiên tạo dữ liệu kiểm thử và review luồng đăng ký; chưa mở chức năng ít liên quan.  
> **Cần trao đổi:** Product Owner xác nhận giá trị và mức bắt buộc của email thông báo.

Nội dung như trên giúp đồng đội và các bên liên quan hiểu **rủi ro thật** mà không cần một người quản lý đi hỏi trạng thái của từng cá nhân.

## 7. Daily Scrum giúp kiểm tra và thích ứng kế hoạch ra sao?

**Daily Scrum** là sự kiện **15 phút** dành cho Developers trong Scrum Team, được tổ chức cùng thời gian và địa điểm mỗi ngày làm việc của Sprint nhằm giảm sự phức tạp khi phối hợp.

Mục đích là **kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần**, tạo một kế hoạch có thể hành động cho công việc tiếp theo. Developers có thể chọn hình thức trao đổi phù hợp, không bắt buộc theo mẫu “hôm qua tôi làm gì, hôm nay tôi làm gì, có trở ngại gì”.

### 7.1. Câu hỏi tốt để kiểm tra Sprint Backlog

- Có phần Increment nào thực sự **đáp ứng DoD** và đưa nhóm gần Sprint Goal hơn?
- Điều gì vẫn thiếu để người học đạt kết quả đã nêu trong Sprint Goal?
- Công việc nào đang bị chặn hoặc nằm chờ review, kiểm thử, tích hợp?
- Hôm nay có cần chuyển năng lực để hoàn tất một lát cắt thay vì mở thêm việc mới?
- Thông tin mới có đòi hỏi trao đổi phạm vi với Product Owner không?
- Sprint Backlog cần cập nhật task, rủi ro hoặc bước kiểm chứng nào?

Daily Scrum **không phải báo cáo tiến độ cho Scrum Master hoặc cấp trên**. Người cần xử lý vấn đề kỹ thuật chi tiết có thể trao đổi thêm sau sự kiện. Developers cũng không cần chờ Daily Scrum hôm sau để điều chỉnh khi một trở ngại khẩn cấp xuất hiện.

### 7.2. Ví dụ cách Daily Scrum tạo quyết định

Giả sử nhóm đang chờ kiểm thử A và B, trong khi một thành viên định bắt đầu tính năng gắn thẻ khóa học không trực tiếp phục vụ Sprint Goal.

> **Developer 1:** “Chúng ta chưa có luồng đăng ký đáng tin cậy trên môi trường tích hợp; dù API đã xong, Sprint Goal vẫn có rủi ro.”  
> **Developer 2:** “Tôi sẽ giúp chuẩn bị dữ liệu kiểm thử và review xử lý đăng ký trùng thay vì mở gắn thẻ.”  
> **Developer 3:** “Tôi sẽ xác nhận giao diện chỉ báo thành công sau khi dịch vụ trả kết quả hợp lệ.”  
> **Cả nhóm:** “Ưu tiên hoàn tất A và B hôm nay, cập nhật hai việc bị chặn trên Sprint Backlog. Nhóm sẽ kiểm tra DoD trước khi nhận thêm công việc.”

Cuộc trao đổi đã tạo **kế hoạch mới phục vụ mục tiêu**, không chỉ một lượt đọc trạng thái.

## 8. Điều gì được thay đổi và điều gì cần bảo vệ?

Trong Sprint, Scrum yêu cầu:

- **Không có thay đổi nào làm nguy hiểm Sprint Goal.**
- **Chất lượng không bị giảm.**
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được **làm rõ và thương lượng lại với Product Owner** khi nhóm học thêm.

Một bảng quyết định hữu ích:

| Tình huống | Developers có thể tự điều chỉnh gì? | Cần phối hợp hoặc bảo vệ điều gì? |
| --- | --- | --- |
| Phát hiện cách triển khai tốt hơn | Thay đổi thiết kế kỹ thuật, thứ tự thực hiện, cách review/kiểm thử | Tiếp tục đáp ứng DoD và Sprint Goal |
| Một task bị chặn | Chuyển người hỗ trợ, ưu tiên gỡ nghẽn, chia việc kỹ thuật | Nếu ảnh hưởng phạm vi hoặc giá trị, trao đổi Product Owner |
| PBI lớn hơn dự tính | Phân rã công việc, tìm lát cắt nhỏ, trình bày rủi ro | Thương lượng phạm vi PBI với Product Owner, giữ Sprint Goal |
| Bên liên quan đề xuất tính năng mới | Đánh giá tác động về năng lực và phụ thuộc | Product Owner quản lý Product Backlog; không tự thêm việc khiến Goal gặp nguy hiểm |
| Sự cố production quan trọng | Xử lý theo cơ chế ứng cứu; cập nhật năng lực và kế hoạch | Tuân thủ quyền hạn tổ chức; minh bạch tác động tới Sprint Goal |
| Một kiểm thử quan trọng thất bại | Sửa lỗi, bổ sung kiểm thử, chuyển năng lực để đạt DoD | Không hạ DoD để tuyên bố đã Done |
| Sprint Goal đã thực sự lỗi thời | Thông báo bằng chứng và trao đổi khả năng tiếp tục | Chỉ Product Owner có thẩm quyền hủy Sprint |

**Không phải mọi thay đổi đều cần một cuộc họp lớn.** Developers có quyền tự quản cách làm; chỉ những vấn đề ảnh hưởng giá trị, phạm vi, quyền quyết định hoặc ràng buộc bên ngoài mới cần phối hợp đúng người. Ngược lại, khi tác động lớn, nhóm không nên dùng từ “tự quản” để che việc tự ý đổi cam kết.

### 8.1. Khi Sprint Goal trở nên lỗi thời

Giả sử một quy định mới khiến sản phẩm không còn được phép sử dụng phương án cấp quyền học hiện tại. Sprint Goal “triển khai cơ chế cấp quyền cũ” có thể mất ý nghĩa. Scrum cho phép **hủy Sprint nếu Sprint Goal trở nên lỗi thời**, và **chỉ Product Owner có thẩm quyền hủy Sprint**.

Đây là ngoại lệ liên quan đến giá trị của mục tiêu, không phải thủ thuật để bắt đầu Sprint mới khi một task bị trễ hoặc khi nhóm ước lượng sai.

### 8.2. Khi Sprint Goal có nguy cơ không đạt

Một kế hoạch có rủi ro không có nghĩa nhóm phải giấu thông tin hoặc tự làm thêm giờ. Developers nên:

1. Xác định phần giá trị tối thiểu còn thiếu để đạt mục tiêu.
2. Kiểm tra chất lượng và các phụ thuộc quan trọng.
3. Chuyển nguồn lực hợp lý sang công việc gần tạo Increment.
4. Trao đổi với Product Owner về phạm vi có thể thương lượng.
5. Minh bạch tác động tới Sprint Goal cho Scrum Team và các bên liên quan.

Nếu kết thúc Sprint mà mục tiêu chưa đạt, nhóm cần phản ánh tình trạng đúng sự thật, kiểm tra nguyên nhân và học để lập kế hoạch tốt hơn. **Không gắn nhãn Done cho phần việc chưa đạt DoD chỉ để báo cáo Sprint thành công.**

## 9. Sprint Goal, tiêu chí chấp nhận và Definition of Done

Những khái niệm này bổ sung nhau nhưng không thay thế nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Sprint Goal** | Kết quả chung nào làm Sprint có giá trị? | Người học đăng ký khóa miễn phí và nhận biết kết quả đáng tin cậy |
| **Acceptance criteria** | Hành vi cụ thể nào của một PBI phải đúng? | Không tạo hai đăng ký trùng; lỗi lưu không bị báo thành công |
| **Definition of Done** | Chuẩn chất lượng nào cần đạt để công việc trở thành Increment? | Kiểm thử phù hợp đạt, tích hợp, đáp ứng yêu cầu chất lượng và bảo mật áp dụng |

Một PBI có thể đạt tiêu chí nghiệp vụ nhưng **chưa Done** vì thiếu kiểm thử tích hợp bắt buộc. Một Increment có thể đáp ứng DoD nhưng **chưa đủ để đạt toàn bộ Sprint Goal** nếu còn thiếu lát cắt giá trị quan trọng.

Nếu một PBI chưa đáp ứng DoD, công việc đó **không thể coi là một phần của Increment**. Nó cần được xử lý minh bạch trong Product Backlog để xem xét lại; không được trình bày như một Increment hoàn tất chỉ vì Sprint đã hết thời gian.

### 9.1. Increment và phát hành không đồng nghĩa hoàn toàn

Scrum hướng tới Increment có thể sử dụng, đáp ứng Definition of Done. Một Increment có thể được giao cho các bên liên quan hoặc người dùng trước cuối Sprint nếu phù hợp; Sprint Review không phải cổng phê duyệt phát hành bắt buộc.

Ngược lại, không phải cứ đạt DoD là lập tức được phép phát hành công khai nếu còn các quy trình vận hành, pháp lý hoặc hợp đồng cần thực hiện. Vì vậy, khi nói Sprint Goal liên quan “người dùng sử dụng được”, nhóm cần hiểu rõ **mốc Increment Done** và **mốc phát hành/khả dụng thật**.

### 9.2. Kết quả kỹ thuật và kết quả người dùng

Một Sprint Goal có thể hướng tới khả năng sản phẩm có thể sử dụng hoặc một kết quả kiểm chứng quan trọng. Đừng đồng nhất nó với chỉ số kinh doanh dài hạn mà nhóm không thể quan sát trong một Sprint.

Ví dụ:

- **Increment:** Người học đăng ký được khóa và thấy xác nhận đúng.
- **Phản hồi ngắn hạn:** Trong buổi thử nghiệm, người học hiểu rõ trạng thái đăng ký.
- **Outcome dài hạn:** Giảm tỷ lệ bỏ dở đăng ký, tăng tỷ lệ bắt đầu học thành công.

Outcome dài hạn có thể cần nhiều Sprint và dữ liệu thực tế. Sprint Goal nên đủ rõ để nhóm biết hướng làm, nhưng không nên biến một mục tiêu kinh doanh bất định thành lời hứa không thể kiểm chứng trong thời hạn Sprint.

## 10. Đo tiến độ hướng tới Sprint Goal như thế nào?

Không có một biểu đồ bắt buộc cho Sprint Backlog. Scrum chú trọng tính minh bạch để nhóm **kiểm tra kết quả và thích ứng**. Developers có thể chọn tín hiệu phù hợp với mục tiêu.

| Tín hiệu | Câu hỏi hữu ích | Giới hạn cần lưu ý |
| --- | --- | --- |
| **Increment đã Done** | Phần nào đã thực sự đáp ứng DoD? | Số PBI Done không tự thể hiện giá trị chung |
| **Khả năng thực hiện luồng người dùng** | Người học đã hoàn tất hành trình cốt lõi chưa? | Phải xác minh điều kiện thực tế, không chỉ bản demo giả lập |
| **PBI đang thực hiện và bị chặn** | Điều gì ngăn nhóm tạo kết quả? | Tránh đo tiến độ bằng số task từng cá nhân |
| **WIP** | Có mở quá nhiều việc cùng lúc không? | Ranh giới đếm phải nhất quán |
| **Work item age / cycle time** | Hạng mục nào nằm lâu trong luồng? | Dữ liệu lịch sử không dự đoán chắc thời gian từng PBI |
| **Hàng chờ review và kiểm thử** | Có thể ưu tiên hoàn tất thay vì mở thêm việc mới? | Chuyển việc cần cân nhắc kỹ năng và phụ thuộc |
| **Kiểm thử và lỗi tích hợp** | Những điều kiện chất lượng nào còn cản trở Done? | Pipeline xanh không tự chứng minh nghiệp vụ đúng |
| **Phản hồi người dùng** | Increment có giúp người dùng đạt mục đích? | Phản hồi định tính cần diễn giải đúng bối cảnh |

### 10.1. Vì sao “50% task Done” có thể gây hiểu lầm?

Giả sử Sprint Backlog có mười task, năm task đã Done, nhưng năm task còn lại chứa toàn bộ kiểm thử tích hợp và xử lý đăng ký trùng. Con số 50% không nói rằng Sprint Goal đã đạt một nửa. Một số task “nhỏ” là điều kiện bắt buộc để chức năng có thể sử dụng an toàn.

Developers cần xem **luồng giá trị đã hoàn tất**, **điều kiện DoD** và **rủi ro đối với mục tiêu** thay vì chỉ lấy tỷ lệ task đóng.

### 10.2. Burndown, burnup và velocity có bắt buộc không?

Không. Burndown, burnup, velocity hoặc story point là những kỹ thuật có thể hỗ trợ dự báo và quan sát. **Scrum không bắt buộc dùng một biểu đồ, thang điểm ước lượng hoặc chỉ số velocity cụ thể.**

Nếu được sử dụng, chúng phải phản ánh công việc thật, không khuyến khích đánh đổi chất lượng hoặc so sánh cá nhân. Ví dụ, tăng số điểm đóng bằng cách chia task giả tạo không khiến Increment hữu ích hơn.

## 11. Ai chịu trách nhiệm cho Sprint Goal và Sprint Backlog?

Scrum có một Scrum Team với ba accountabilities: **Product Owner, Scrum Master và Developers**. Không có “Project Manager” như một accountability thứ tư bắt buộc của Scrum, dù tổ chức vẫn có thể dùng chức danh quản lý khác.

| Trách nhiệm | Product Owner | Developers | Scrum Master |
| --- | --- | --- | --- |
| Định hướng giá trị và thứ tự Product Backlog | Chịu trách nhiệm quản lý hiệu quả và tối đa hóa giá trị | Cung cấp hiểu biết kỹ thuật và rủi ro | Hỗ trợ hiệu quả Scrum, năng lực quản lý backlog |
| Tạo Sprint Goal | Cùng Scrum Team trao đổi giá trị | Cùng Scrum Team tạo mục tiêu khả thi | Hỗ trợ Sprint Planning và Scrum hiệu quả |
| Chọn PBI trong Sprint Planning | Làm rõ ưu tiên, giá trị và PBI | Chọn PBI qua trao đổi với Product Owner | Hỗ trợ cách phối hợp và hiểu Scrum |
| Tạo kế hoạch How | Trao đổi khi cần làm rõ nhu cầu | Chịu trách nhiệm lập và điều chỉnh kế hoạch | Hỗ trợ tự quản, gỡ trở ngại |
| Kiểm tra tiến độ hằng ngày | Sẵn sàng trao đổi phạm vi và giá trị | Thực hiện Daily Scrum, điều chỉnh Sprint Backlog | Hỗ trợ nhóm hiệu quả, không nhận báo cáo task |
| Khi phạm vi cần đổi | Cộng tác thương lượng phạm vi, chịu trách nhiệm giá trị | Nêu tác động, đề xuất cách làm, giữ DoD và Sprint Goal | Hỗ trợ minh bạch, Scrum và xử lý trở ngại |

**Sprint Goal là mục tiêu chung của cả Scrum Team**, không phải mệnh lệnh riêng từ Product Owner. Cũng không nên nói Developers “chỉ cần đạt Sprint Goal là có thể tùy ý bỏ qua PBI”: các thay đổi về phạm vi, giá trị phải được trao đổi phù hợp, với chất lượng được bảo vệ.

### Trách nhiệm chuyên môn và tự quản

Developers chịu trách nhiệm tạo Sprint Backlog, duy trì chất lượng theo DoD, điều chỉnh kế hoạch hằng ngày hướng tới Sprint Goal và giữ trách nhiệm nghề nghiệp với nhau. Scrum Team tự quản cách thực hiện trong phạm vi thẩm quyền.

Ví dụ, khi review bị nghẽn, Developers có thể chuyển người sang hỗ trợ review và kiểm thử. Họ không cần Product Owner phân từng task. Nhưng nếu cần thay đổi quy tắc sản phẩm, ví dụ ai được phép đăng ký khóa miễn phí, họ cần trao đổi với Product Owner hoặc người có thẩm quyền nghiệp vụ thay vì tự suy đoán.

## 12. Sprint Backlog kết nối với các sự kiện Scrum

| Sự kiện | Sprint Goal và Sprint Backlog liên quan thế nào? |
| --- | --- |
| **Sprint Planning** | Scrum Team tạo Sprint Goal; Developers chọn PBI và lập kế hoạch hành động, tạo Sprint Backlog |
| **Daily Scrum** | Developers kiểm tra tiến độ hướng tới Sprint Goal, điều chỉnh Sprint Backlog, có kế hoạch cho công việc sắp tới |
| **Sprint Review** | Scrum Team và các bên liên quan kiểm tra kết quả, bối cảnh sản phẩm và thích ứng Product Backlog khi cần |
| **Sprint Retrospective** | Scrum Team đánh giá cách làm, chất lượng, hiệu quả; xác định thay đổi cải tiến cho những Sprint tiếp theo |
| **Sprint** | Khoảng thời gian cố định chứa các sự kiện; Sprint Goal tạo sự tập trung xuyên suốt |

Sprint Backlog được tạo ở Sprint Planning, nhưng **không chỉ được cập nhật trong các sự kiện**. Khi một lỗi nghiêm trọng xuất hiện trong ngày hoặc nhóm nhận phản hồi cần xử lý ngay, Developers có thể trao đổi và điều chỉnh kế hoạch phù hợp.

### Sprint Review không phải buổi kiểm điểm từng task

Ở Sprint Review, trọng tâm là **điều gì đã đạt, điều gì đã thay đổi và nên thích ứng hướng sản phẩm ra sao**. Không nên tổ chức chỉ để từng người đọc trạng thái ticket hoặc để “ký duyệt” một Increment chưa đạt DoD.

### Sprint Retrospective có vai trò gì?

Nếu nhiều Sprint liên tục gặp cùng vấn đề — ví dụ kiểm thử dồn cuối kỳ, story quá lớn, Daily Scrum biến thành báo cáo — nhóm có thể điều chỉnh working agreement, cách chia PBI hoặc thực hành tích hợp. Sự cải tiến đó ảnh hưởng Sprint Backlog và khả năng đạt Sprint Goal ở các Sprint sau.

## 13. Kết hợp Kanban và XP mà không làm sai Scrum

Scrum định nghĩa Sprint Backlog và Sprint Goal. Kanban và Extreme Programming (XP) cung cấp những thực hành có thể hỗ trợ quản lý dòng công việc, phản hồi nhanh và chất lượng kỹ thuật.

### 13.1. Kanban: nhìn luồng, giảm WIP và gỡ nghẽn

Nhóm có thể trực quan hóa PBI và task của Sprint Backlog trên một bảng:

~~~text
Sprint Goal: Người học đăng ký khóa miễn phí và nhận biết kết quả đáng tin cậy

Sẵn sàng       Đang làm           Review / kiểm thử     Done
-------------- ------------------ -------------------- ----------------
Email bổ sung  Xác nhận lỗi mạng  Kiểm tra đăng ký trùng Lưu đăng ký cơ bản
               Danh sách khóa     Phân quyền tài khoản
~~~

Một bảng như vậy giúp thấy hàng chờ kiểm thử và các hạng mục đã gần Done. Nhóm có thể thử giới hạn WIP, ưu tiên hoàn tất trước khi kéo việc mới, theo dõi work item age hoặc cycle time.

Những kỹ thuật đó **không biến Sprint Goal thành một thang chỉ số Kanban**, cũng không xóa bỏ trách nhiệm và sự kiện Scrum. Không có WIP limit cụ thể nào được Scrum Guide bắt buộc cho mọi đội.

### 13.2. XP: giúp Increment luôn đủ chất lượng

Thực hành như **test-driven development, pair programming, tích hợp liên tục, refactoring và các đợt giao nhỏ** có thể giảm rủi ro khi Developers cần thay đổi kế hoạch trong Sprint.

Ví dụ, nếu kiểm thử tự động đã mô tả hành vi chống đăng ký trùng, Developers có thể thay cách triển khai dịch vụ mà nhanh chóng nhận phản hồi về tính đúng đắn. Nhưng kiểm thử đơn vị xanh **không thay thế** tiêu chí chấp nhận nghiệp vụ hoặc DoD.

### 13.3. Khi nào nên dùng kỹ thuật bổ trợ?

| Vấn đề thật | Kỹ thuật có thể thử | Tác động kỳ vọng |
| --- | --- | --- |
| Nhiều PBI đang làm, ít PBI Done | Giới hạn WIP, ưu tiên cùng hoàn tất | Giảm dở dang, tập trung Sprint Goal |
| Review bị nghẽn cuối Sprint | Pull request nhỏ, review liên tục, làm việc cặp | Giảm thời gian chờ tích hợp |
| Sửa một phần gây lỗi phần khác | TDD, kiểm thử hồi quy tự động, CI | Phản hồi nhanh về chất lượng |
| Story quá lớn, khó đạt mục tiêu | Chia lát cắt dọc theo giá trị sử dụng | Có Increment nhỏ hơn, dễ kiểm chứng |
| Yêu cầu nghiệp vụ thay đổi | Conversation, ví dụ chấp nhận, phối hợp Product Owner | Thay đổi phạm vi có căn cứ, giữ hướng giá trị |

## 14. Những hiểu lầm thường gặp

**1. “Sprint Backlog chỉ là danh sách PBI đã chọn.”** Thiếu Sprint Goal và kế hoạch hành động sẽ không phản ánh đủ ba thành phần Why–What–How của artifact.

**2. “Product Owner phải chia task và giao việc cho từng Developer.”** Developers tạo và cập nhật kế hoạch How; Product Owner chịu trách nhiệm quản lý Product Backlog và giá trị.

**3. “Sprint Goal chính là hoàn thành 100% PBI.”** Sprint Goal là mục tiêu duy nhất tạo sự tập trung; PBI được chọn là phạm vi dự báo giúp đạt mục tiêu, không phải định nghĩa duy nhất của mục tiêu.

**4. “Mỗi PBI cần một Sprint Goal riêng.”** Scrum có một Sprint Goal cho Sprint, dù có thể có nhiều PBI phục vụ mục tiêu.

**5. “Sprint Backlog phải giữ nguyên cả Sprint.”** Developers liên tục làm rõ và cập nhật kế hoạch khi học thêm; phạm vi có thể thương lượng với Product Owner trong giới hạn Scrum.

**6. “Agile cho phép thay Sprint Goal tùy ý.”** Không thay đổi theo cách gây nguy hiểm cho Sprint Goal. Khi mục tiêu trở nên lỗi thời, chỉ Product Owner có thẩm quyền hủy Sprint.

**7. “Đạt Sprint Goal thì có thể bỏ DoD.”** Sprint Goal liên quan định hướng giá trị; DoD là chuẩn chất lượng bắt buộc để công việc trở thành Increment.

**8. “Daily Scrum là báo cáo hằng ngày cho Scrum Master.”** Đây là sự kiện của Developers để kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog.

**9. “Chỉ số burndown là bằng chứng Sprint Goal đã đạt.”** Biểu đồ task không tự chứng minh Increment Done hoặc hành vi người dùng mong muốn.

**10. “Story chưa Done có thể đưa vào Increment để giữ tiến độ.”** Công việc chưa đạt DoD không phải là một phần của Increment.

**11. “Sprint Review là cổng duyệt phát hành bắt buộc.”** Increment có thể được giao trước Sprint Review nếu phù hợp; sự kiện nhằm kiểm tra và thích ứng sản phẩm.

**12. “Sprint Goal phải là một chỉ số kinh doanh dài hạn.”** Sprint Goal cần có ý nghĩa và kiểm tra được trong bối cảnh Sprint; kết quả kinh doanh có thể cần quan sát qua nhiều Sprint.

**13. “Scrum bắt buộc dùng story point và burndown.”** Đó là các kỹ thuật tùy chọn, không phải thành phần bắt buộc của Sprint Backlog.

**14. “Tự quản nghĩa là không cần trao đổi với Product Owner.”** Developers tự quyết cách thực hiện nhưng cần cộng tác về giá trị, phạm vi và quy tắc sản phẩm.

**15. “Cứ nhiều hạng mục Done là Sprint thành công.”** Số hạng mục có thể tăng mà kết quả cốt lõi vẫn thiếu; phải nhìn mục tiêu và chất lượng.

## 15. Bài tập tình huống: Sprint Goal đứng trước thay đổi phạm vi

Một Scrum Team xây dựng nền tảng học trực tuyến có Sprint dài hai tuần. Sprint Goal:

> “Người học có thể hoàn tất một bài kiểm tra ngắn và xem kết quả chính xác, đáng tin cậy.”

Nhóm chọn các PBI:

- **A:** Nộp câu trả lời của người học.
- **B:** Chấm điểm và trả kết quả.
- **C:** Lưu lịch sử bài làm trong tài khoản.
- **D:** Gửi email tóm tắt kết quả.

Đến ngày thứ sáu:

1. A đã đáp ứng DoD.
2. B chạy được trong môi trường cục bộ nhưng kiểm thử tích hợp phát hiện có thể chấm hai lần khi người học nhấn nộp lại.
3. C đang chờ review phân quyền và bảo mật dữ liệu.
4. D chưa bắt đầu vì dịch vụ email gặp sự cố.
5. Một bên liên quan yêu cầu thêm chức năng “bảng xếp hạng” ngay trong Sprint.
6. Daily Scrum chủ yếu dành thời gian hỏi mỗi người “đã đóng bao nhiêu task?”.

### Câu hỏi

1. Chỉ ra **Why, What và How** của Sprint Backlog trong tình huống.
2. Những vấn đề nào đang trực tiếp đe dọa Sprint Goal?
3. Developers nên thay đổi kế hoạch hôm nay như thế nào?
4. Có thể bỏ hoặc hoãn D không? Cần điều kiện và trao đổi gì trước khi quyết định?
5. Xử lý yêu cầu bảng xếp hạng theo trách nhiệm Scrum ra sao?
6. Nếu B còn lỗi chấm trùng và C chưa đạt DoD ở ngày cuối, nhóm có thể coi chúng là Increment hoàn tất không?
7. Hãy viết một thông báo ngắn cho các bên liên quan về tiến độ thực chất, không dùng phần trăm task đóng.

### Gợi ý lời giải

**Câu 1:** **Why** là Sprint Goal người học nộp bài và xem kết quả đáng tin cậy; **What** là A–D được chọn; **How** là kế hoạch tích hợp nộp bài, xử lý chấm điểm, kiểm thử thao tác lặp, phân quyền, lưu lịch sử, thông báo và các hoạt động đạt DoD. How được Developers tiếp tục làm rõ.

**Câu 2:** B có thể chấm hai lần làm kết quả không đáng tin cậy; C chưa kiểm tra quyền dữ liệu; đây là rủi ro trực tiếp. D chỉ có thể được xem là ít thiết yếu nếu Product Owner và nhóm xác nhận email không phải điều kiện bắt buộc cho mục tiêu; không tự suy đoán.

**Câu 3:** Developers nên ưu tiên cùng sửa B, tạo kiểm thử tái hiện lỗi nộp lại, hoàn tất review phân quyền C và kiểm thử luồng “nộp → chấm → xem kết quả”. Giảm WIP, hoãn mở việc không góp phần vào mục tiêu và cập nhật Sprint Backlog theo tình trạng thực.

**Câu 4:** Phải trao đổi với Product Owner về giá trị và tính bắt buộc của email, tác động tới Sprint Goal và yêu cầu bên ngoài. Nếu kết quả người học đã đáng tin cậy trong ứng dụng và D không bắt buộc, nhóm có thể thương lượng phạm vi và ưu tiên D ở Product Backlog. Nếu D là điều kiện không thể bỏ, cần nêu rủi ro hoặc phương án khác phù hợp.

**Câu 5:** Product Owner quản lý Product Backlog và thứ tự ưu tiên. Developers đánh giá tác động của bảng xếp hạng tới Sprint Goal, năng lực và DoD; không tự đưa việc mới làm nguy hiểm mục tiêu hiện tại. Có thể trao đổi để xếp ưu tiên cho Sprint sau hoặc lựa chọn phù hợp khác.

**Câu 6:** Không. PBI chưa đáp ứng DoD không trở thành phần của Increment. Nhóm cần minh bạch phần còn lại và điều chỉnh Product Backlog; không làm đẹp tiến độ bằng cách gọi “gần Done” là Done.

**Câu 7 — Ví dụ thông báo:**

> “Nhóm đã hoàn tất luồng nhận câu trả lời. Việc chấm điểm và lưu kết quả chưa đạt tiêu chuẩn hoàn tất vì còn lỗi khi nộp lặp và cần kiểm tra quyền dữ liệu. Developers đang ưu tiên giải quyết hai rủi ro này để bảo vệ Sprint Goal. Dịch vụ email gặp trở ngại; nhóm sẽ trao đổi với Product Owner về phạm vi hợp lý, sau đó cập nhật kế hoạch và những phần thực sự có thể Done.”

### Bài tập mở rộng: cải thiện Sprint Goal

Viết lại những Sprint Goal dưới đây để có kết quả rõ hơn:

| Mục tiêu ban đầu | Hướng viết lại gợi ý |
| --- | --- |
| “Làm 12 task trong Sprint.” | “Người học mới có thể tìm một khóa phù hợp và nhận biết điều kiện đầu vào trước khi đăng ký.” |
| “Code API và UI của quiz.” | “Người học có thể làm bài kiểm tra cơ bản và xem điểm được xác nhận chính xác.” |
| “Xong 30 story point.” | “Chứng minh luồng đăng ký khóa miễn phí có thể hoạt động ổn định trên môi trường tích hợp.” |

## 16. Checklist sử dụng Sprint Backlog và Sprint Goal

Trước hoặc ngay sau Sprint Planning:

1. **Vì sao:** Scrum Team có thể diễn đạt một Sprint Goal duy nhất, có giá trị và đủ tập trung chưa?
2. **Cái gì:** PBI được chọn có thực sự hỗ trợ mục tiêu và dự báo khả thi theo năng lực không?
3. **Thực hiện:** Developers đã có kế hoạch tạo Increment, gồm kiểm thử và tích hợp cần thiết, chưa?
4. **Chất lượng:** Definition of Done và các ràng buộc bắt buộc đã được tính đến chưa?
5. **Phụ thuộc:** Câu hỏi nghiệp vụ, quyền truy cập và môi trường có nguy cơ chặn mục tiêu đã được nêu chưa?

Trong Sprint:

6. **Minh bạch:** Sprint Backlog có phản ánh kế hoạch thực tế, công việc bị chặn và bước tiếp theo không?
7. **Kiểm tra:** Daily Scrum có tập trung vào tiến độ tới Sprint Goal thay vì báo cáo cá nhân không?
8. **Thích ứng:** Developers có điều chỉnh How và phối hợp gỡ nghẽn khi có thông tin mới không?
9. **Phạm vi:** Thay đổi cần thương lượng với Product Owner đã được trao đổi rõ chưa?
10. **DoD:** Nhóm có tránh gọi công việc chưa hoàn tất là Increment Done không?
11. **Giá trị:** Những phần đã Done có tạo thành kết quả người dùng cần không?
12. **Học hỏi:** Phản hồi trong Sprint và tại Sprint Review có được dùng để điều chỉnh kế hoạch sản phẩm phù hợp không?

Sau Sprint:

13. **Trung thực:** Mức đạt Sprint Goal và những phần Increment thực sự Done có được trình bày đúng không?
14. **Cải tiến:** Sprint Retrospective đã chọn thay đổi khả thi để tăng khả năng đạt mục tiêu trong các Sprint tới chưa?

**Ghi nhớ:** **Sprint Backlog = Sprint Goal (Why) + PBI được chọn (What) + kế hoạch hành động (How).** Developers tạo và cập nhật kế hoạch đó để kiểm tra, thích ứng hằng ngày. **Sprint Goal là commitment giúp cả Scrum Team tập trung vào một mục tiêu có giá trị**, không phải cam kết hoàn tất bất biến từng task. Khả năng thay đổi How và thương lượng phạm vi giúp Scrum thích ứng; **Definition of Done** bảo vệ chất lượng để kết quả thật sự trở thành Increment. Kết hợp những điều này, nhóm có thể giao phần mềm tăng dần, nhận phản hồi sớm và tiếp tục cải tiến.
