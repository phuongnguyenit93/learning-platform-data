# Làm rõ Product Backlog như hoạt động liên tục

Một Scrum Team phát triển nền tảng học trực tuyến có Product Backlog với hạng mục đứng đầu: **“Cho phép học viên đăng ký khóa học”**. Khi Sprint Planning bắt đầu, Developers mới biết rằng hạng mục này bao gồm cả ghi danh miễn phí, thanh toán bằng nhiều phương thức, gửi email, cấp quyền truy cập, hoàn tiền và báo cáo quản trị. Người phụ trách sản phẩm kỳ vọng có thể giao trong một Sprint; Developers cho rằng cần nhiều Sprint; bộ phận kiểm thử vẫn chưa biết điều kiện nào để coi giao dịch thành công.

Vấn đề không nằm ở việc nhóm thiếu một cuộc họp thật dài. Product Backlog đã không được **làm rõ dần trong suốt quá trình phát triển**. Các câu hỏi về nhu cầu, quy tắc nghiệp vụ, kích thước, rủi ro và phụ thuộc được dồn tới thời điểm cần lựa chọn công việc. Kết quả là Sprint Planning biến thành buổi khám phá yêu cầu, dự báo thiếu căn cứ và nhóm khó tạo Increment có thể sử dụng.

Trong Scrum, **Product Backlog refinement** (làm rõ hoặc tinh chỉnh Product Backlog) là hoạt động thường xuyên nhằm **chia nhỏ và định nghĩa rõ hơn** các Product Backlog Items (PBI). Mục đích không phải tạo ra kho tài liệu hoàn hảo trước khi lập trình, mà giúp nhóm có đủ sự minh bạch để **chọn việc có giá trị, hiểu điều cần kiểm chứng và hoàn tất trong những Sprint gần nhất**.

Đây là bài thuộc chương **Sự kiện Scrum** của module **AGILE_DEVELOPMENT**, với phạm vi học các giá trị và nguyên tắc Agile, phản hồi sớm, giao sản phẩm tăng dần, user story, backlog, Scrum, Kanban và XP. Điểm cần nhớ ngay từ đầu: **refinement không phải một trong các sự kiện Scrum chính thức**. Nhóm có thể tổ chức các phiên trao đổi riêng, nhưng giá trị của refinement xuất hiện qua nhiều hoạt động cộng tác, nghiên cứu, kiểm tra và điều chỉnh, không bị giới hạn trong một lịch họp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đúng vị trí của Product Backlog refinement trong Scrum Guide 2020 và phân biệt với các sự kiện Scrum chính thức.
2. Mô tả những thông tin cần được làm rõ theo mức độ gần của hạng mục: người dùng, giá trị, phạm vi, hành vi, kích thước, rủi ro, phụ thuộc và bằng chứng kiểm chứng.
3. Phân biệt trách nhiệm của **Product Owner**, **Developers**, **Scrum Master** và những người cung cấp chuyên môn hoặc phản hồi trong refinement.
4. Vận dụng user story, ví dụ Given–When–Then và kỹ thuật phân nhỏ theo lát cắt dọc để biến hạng mục quá lớn thành các PBI có thể cân nhắc lựa chọn.
5. Kết nối refinement với Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective, Product Goal, Sprint Goal và Definition of Done mà không biến refinement thành “cổng phê duyệt” mới.
6. Nhận diện phản mẫu như refinement quá sớm, áp đặt ước lượng, checklist Ready cứng nhắc, thiếu tiếng nói Developers và chỉ tối ưu số ticket.
7. Thiết kế nhịp làm rõ liên tục, phù hợp mức bất định và khả năng của nhóm, rồi đánh giá hiệu quả bằng tiến triển thực chứ không phải số giờ họp.

## 1. Product Backlog refinement thực chất là gì?

Theo **The Scrum Guide (2020)**, Product Backlog là danh sách mới nổi, được sắp xếp theo thứ tự, về những gì cần để cải thiện sản phẩm; nó là nguồn công việc duy nhất do Scrum Team thực hiện. **Product Backlog refinement** là hành động **chia nhỏ và định nghĩa thêm** các Product Backlog Items thành những item nhỏ và chính xác hơn. Đây là hoạt động liên tục nhằm bổ sung chi tiết như **mô tả, thứ tự và kích thước**; các thuộc tính cụ thể có thể khác nhau theo lĩnh vực công việc.

Điều này hàm ý bốn đặc điểm:

- **Liên tục:** làm rõ khi câu hỏi quan trọng xuất hiện và khi hạng mục tiến gần thời điểm cần lựa chọn, không đợi một buổi họp duy nhất.
- **Có chọn lọc:** đầu tư công sức chủ yếu vào hạng mục gần, có giá trị hoặc có rủi ro cần giảm; không viết chi tiết toàn bộ ý tưởng xa.
- **Hợp tác:** người hiểu người dùng, quy tắc nghiệp vụ, kỹ thuật và kiểm thử cùng làm giảm những hiểu nhầm ảnh hưởng khả năng hoàn tất.
- **Có kết quả hành động:** sau khi refinement, nhóm biết rõ hơn nên chọn, chia nhỏ, nghiên cứu, lùi thứ tự hoặc bỏ một hạng mục; không phải chỉ có thêm tài liệu.

### 1.1. Refinement không phải sự kiện Scrum thứ sáu

Scrum quy định **Sprint** là sự kiện bao chứa các sự kiện còn lại. Bốn sự kiện trong Sprint là **Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective**. Scrum Guide không quy định một sự kiện chính thức tên **Backlog Refinement Meeting**.

| Hoạt động / sự kiện | Vị trí trong Scrum | Mục đích chính | Có timebox do Scrum Guide quy định? |
|---|---|---|---|
| **Sprint** | Sự kiện bao chứa, dài tối đa một tháng | Tạo nhịp phát triển, kiểm tra và thích ứng hướng tới Product Goal | Có: tối đa một tháng |
| **Sprint Planning** | Sự kiện Scrum trong Sprint | Xác định vì sao Sprint có giá trị, có thể hoàn tất những gì và làm bằng cách nào | Có: tối đa 8 giờ cho Sprint một tháng; Sprint ngắn thường ngắn hơn |
| **Daily Scrum** | Sự kiện Scrum của Developers | Kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog | Có: 15 phút |
| **Sprint Review** | Sự kiện Scrum | Scrum Team và stakeholders kiểm tra kết quả Sprint và thích ứng bước tiếp theo | Có: tối đa 4 giờ cho Sprint một tháng; Sprint ngắn thường ngắn hơn |
| **Sprint Retrospective** | Sự kiện Scrum | Lập kế hoạch nâng cao chất lượng và hiệu quả | Có: tối đa 3 giờ cho Sprint một tháng; Sprint ngắn thường ngắn hơn |
| **Product Backlog refinement** | **Hoạt động liên tục**, không phải sự kiện Scrum chính thức | Làm rõ và chia nhỏ PBI để tăng sự minh bạch và khả năng lựa chọn | **Không có timebox bắt buộc** trong Scrum Guide 2020 |

Nhóm có thể đặt lịch refinement 30 hoặc 60 phút, trao đổi ngay sau một buổi quan sát người dùng, thảo luận với chuyên gia qua kênh không đồng bộ hoặc làm rõ một API trong lúc phát triển. **Lịch họp là cách tổ chức, không phải định nghĩa hoạt động.**

Một số tài liệu đào tạo cũ nhắc mức khoảng **10% năng lực** dành cho refinement. Đây **không phải quy tắc bắt buộc của Scrum Guide 2020**; thời lượng phù hợp tùy độ phức tạp, biến động và mức hiểu biết của nhóm. Dành nhiều giờ không đồng nghĩa refinement tốt, và họp ít cũng không chứng minh nhóm thiếu hợp tác nếu thông tin được làm rõ hiệu quả bằng những cách khác.

### 1.2. Sơ đồ liên hệ hoạt động refinement với các sự kiện Scrum

~~~mermaid
flowchart TD
    A["Product Goal và phản hồi người dùng"] --> B["Product Backlog<br/>mới nổi, có thứ tự"]
    B --> C["Refinement liên tục<br/>làm rõ, chia nhỏ, xem rủi ro"]
    C --> D["Sprint Planning<br/>chọn PBI, Sprint Goal, kế hoạch"]
    D --> E["Phát triển và kiểm chứng<br/>Increment đạt DoD"]
    E --> F["Sprint Review<br/>kiểm tra kết quả và bối cảnh"]
    F --> B
    E --> G["Sprint Retrospective<br/>cải tiến cách làm"]
    G -. "Cải tiến cách refinement" .-> C
    E -. "Thông tin kỹ thuật mới" .-> C
    A -. "Phản hồi liên tục" .-> C
~~~

Sơ đồ mang tính khái quát. **Refinement không chỉ xảy ra trước Sprint Planning**: thông tin từ phát triển, lỗi tích hợp, nghiên cứu người dùng và Sprint Review có thể khiến những item trong Product Backlog được làm rõ hoặc thay đổi bất cứ lúc nào. Các thay đổi trong Sprint vẫn phải tôn trọng Sprint Goal, DoD và trách nhiệm của các bên.

### 1.3. “Làm rõ” không có nghĩa “chốt mọi chi tiết”

Yêu cầu phần mềm có những điều không thể biết đầy đủ từ đầu. Nếu nhóm buộc phải viết mọi tiêu chí và thiết kế cho cả năm tới, nhiều tài liệu sẽ lỗi thời khi Product Goal, người dùng hoặc điều kiện kỹ thuật thay đổi.

Hãy phân biệt:

| Hạng mục gần | Hạng mục xa |
|---|---|
| Cần hiểu ai dùng, hành vi nào, phạm vi và rủi ro thiết yếu | Có thể chỉ cần vấn đề, giả thuyết giá trị và độ ưu tiên sơ bộ |
| Có thể có ví dụ nghiệp vụ, AC và phụ thuộc được làm rõ | Nhiều giải pháp còn để mở |
| Developers có thông tin để đánh giá kích thước và khả năng hoàn tất | Chưa cần ước lượng chi tiết hoặc dự báo ngày chính xác |
| Có thể cân nhắc đưa vào Sprint nếu phù hợp | Cần kiểm chứng giá trị hoặc làm rõ thêm trước khi chọn |

**Làm rõ vừa đủ, đúng thời điểm (just enough, just in time)** không có nghĩa bỏ qua an toàn, bảo mật hay tính đúng đắn. Những ràng buộc bắt buộc vẫn cần được xác định sớm khi có thể tác động tới kiến trúc và cách hoàn tất sản phẩm.

## 2. Vì sao Product Backlog phải được làm rõ liên tục?

### 2.1. Nhu cầu và ưu tiên thay đổi khi người dùng phản hồi

Một Product Backlog Item như “Tạo video hướng dẫn đăng ký” có thể được đề xuất vì nhiều học viên hỏi cách bắt đầu khóa. Sau khi quan sát, nhóm phát hiện vấn đề thực là liên kết xác minh email thường hết hạn mà không có nút yêu cầu lại. Nếu tiếp tục chi tiết hóa và xây video chỉ vì nó đã được đưa vào backlog, đội có thể giao đúng đầu ra nhưng chưa giải quyết vấn đề.

Refinement liên tục giúp Product Owner và Scrum Team:

- Làm rõ **vấn đề** trước khi khóa giải pháp.
- Đưa bằng chứng mới vào việc cân nhắc thứ tự.
- Thử một lát cắt nhỏ để học sớm.
- Dừng hoặc thay đổi item không còn phù hợp.

Việc một PBI thay đổi sau khi có dữ liệu mới không tự chứng minh nhóm “quản lý yêu cầu kém”. Trong sản phẩm phức tạp, đó có thể là **biểu hiện của tính thích ứng**. Điều quan trọng là thay đổi được lý giải và truyền đạt minh bạch.

### 2.2. Thông tin kỹ thuật cũng xuất hiện dần

Developers có thể phát hiện API của nhà cung cấp không trả trạng thái theo cách giả định, dữ liệu khách hàng có định dạng không nhất quán hoặc tốc độ xử lý không đạt nhu cầu. Nếu những phát hiện này không được đưa trở lại backlog, các item tương lai vẫn dựa trên thông tin sai.

Ví dụ: sau thử nghiệm sandbox, nhóm biết giao dịch có thể gửi callback lặp. Các item thanh toán sắp tới cần được làm rõ về **idempotency**, trạng thái chờ và trường hợp hoàn tất muộn. Thay đổi này không phải “thêm việc tùy tiện”; nó phản ánh điều kiện cần để chức năng đúng và an toàn.

### 2.3. Kích thước hạng mục phải được hiểu trước khi lựa chọn

Một epic như “Xây hệ thống quản lý khóa học” có thể liên quan nhiều hành vi, dữ liệu, quy tắc và đội phụ thuộc. Nếu nó được chọn nguyên khối, Developers khó dự báo liệu có thể đạt DoD trong Sprint hay không.

Refinement giúp **chia epic hoặc PBI lớn thành những lát cắt có hành vi và điều kiện hoàn tất rõ ràng**, ưu tiên phần đem lại giá trị hoặc giảm rủi ro trước. Nhờ đó Sprint Planning có thể tập trung vào **vì sao Sprint có giá trị, chọn những gì và lập kế hoạch như thế nào**.

### 2.4. Giảm chi phí chờ đợi và làm lại

Một câu hỏi về quyền truy cập được trả lời trước khi lập trình thường rẻ hơn phát hiện sau khi UI, API và dữ liệu đã hoàn tất. Tương tự, việc biết trước môi trường thanh toán chưa sẵn giúp đội tránh nhận một cam kết không khả thi.

Tuy vậy, refinement quá mức cũng có chi phí: họp dài, nhiều người tham gia không cần thiết, phân tích những tính năng xa rồi bỏ. **Mục tiêu không phải tối đa hóa thời gian làm rõ; mục tiêu là giảm những bất định đang cản trở quyết định và việc giao giá trị.**

## 3. Ai tham gia và ai chịu trách nhiệm?

Scrum không tạo một chức danh “Backlog Refinement Owner” riêng. Trách nhiệm được đặt trong các accountability của Scrum Team; người ngoài đội có thể đóng góp thông tin khi cần.

| Vai trò / nhóm tham gia | Trách nhiệm hoặc đóng góp phù hợp | Điều cần tránh |
|---|---|---|
| **Product Owner** | Chịu trách nhiệm quản lý Product Backlog hiệu quả: truyền đạt Product Goal, tạo sự minh bạch, sắp xếp thứ tự, làm rõ giá trị và quyết định ưu tiên | Chỉ giao danh sách tính năng từ cấp trên mà không làm rõ vấn đề; một mình áp ước lượng kỹ thuật |
| **Developers** | Đánh giá kích thước PBI, phát hiện rủi ro và phụ thuộc, đề xuất lát cắt, điều kiện kiểm chứng và cách tạo Increment | Bị yêu cầu cam kết hoặc ước lượng trước khi hiểu nội dung; chỉ nhận task mà không tham gia làm rõ |
| **Scrum Master** | Giúp Scrum Team và tổ chức hiểu Scrum, nâng hiệu quả cộng tác, hỗ trợ tháo những trở ngại của refinement | Biến refinement thành nghi thức bắt buộc hoặc làm người duyệt Ready thay Product Owner |
| **Stakeholders / chuyên gia nghiệp vụ** | Giải thích quy tắc, nghĩa vụ, vấn đề, giá trị và những điều kiện thực tế | Áp trực tiếp nhiều thứ tự ưu tiên mâu thuẫn cho Developers |
| **Người dùng / hỗ trợ / vận hành** | Cung cấp bằng chứng về trải nghiệm, sự cố, điều kiện triển khai và hành vi thực | Bị thay thế hoàn toàn bằng suy đoán trong phòng họp |
| **Chuyên gia bảo mật, pháp lý, accessibility, dữ liệu** | Làm rõ ràng buộc hoặc rủi ro chuyên biệt khi cần | Chỉ được mời sau khi thiết kế đã khóa và mọi thay đổi trở nên tốn kém |

### 3.1. Product Owner chịu trách nhiệm backlog, không làm mọi việc một mình

Trong Scrum Guide, Product Owner **chịu trách nhiệm tối đa hóa giá trị sản phẩm** từ công việc của Scrum Team và quản lý Product Backlog hiệu quả. Công việc quản lý có thể được ủy nhiệm, nhưng Product Owner vẫn chịu trách nhiệm giải trình.

Ví dụ, Product Owner có thể nhờ một chuyên gia phân tích nghiệp vụ làm rõ quy tắc hoàn tiền hoặc nhờ Developers cùng viết ví dụ chấp nhận. Điều đó không có nghĩa thứ tự backlog trở thành quyết định của người có tiếng nói lớn nhất trong cuộc họp.

Những quyết định về an toàn, pháp lý hoặc ngân sách vượt quyền Product Owner cần được xử lý theo thẩm quyền tổ chức; việc này phải minh bạch để Scrum Team không bị yêu cầu tự cam kết điều mình không thể quyết định.

### 3.2. Developers chịu trách nhiệm về kích thước PBI

Theo Scrum Guide, **Developers chịu trách nhiệm xác định kích thước của Product Backlog Items**. Product Owner có thể ảnh hưởng bằng cách giúp Developers hiểu giá trị, sự đánh đổi và những lựa chọn chia nhỏ.

Nếu người quản lý yêu cầu “hạng mục này phải là 3 story point” chỉ để vừa một kế hoạch, thông tin ước lượng mất tính hữu ích. Cách tốt hơn:

1. Làm rõ những hành vi và ràng buộc bắt buộc.
2. Nêu những phụ thuộc hoặc điều chưa biết.
3. Đề xuất cách chia nhỏ hoặc thử nghiệm giảm rủi ro.
4. Để Developers đánh giá kích thước theo phương pháp phù hợp.
5. Product Owner điều chỉnh phạm vi hoặc thứ tự theo giá trị và thông tin mới.

Scrum **không bắt buộc story point, Planning Poker hay một thang ước lượng cụ thể**. Nếu đội dùng story point, phải nhớ chúng không đo giá trị người dùng và không nên dùng để so năng suất các đội hoặc cá nhân.

### 3.3. Ba góc nhìn trong một cuộc trao đổi ngắn

Nhiều đội sử dụng thực hành thường được gọi là **Three Amigos**:

1. **Góc nhìn giá trị/nghiệp vụ:** Người dùng cần làm gì? Quy tắc nào quan trọng?
2. **Góc nhìn phát triển/kỹ thuật:** Có những phụ thuộc, trạng thái và rủi ro triển khai nào?
3. **Góc nhìn kiểm thử/chất lượng:** Điều kiện nào giúp chứng minh đúng? Trường hợp lỗi nào dễ bỏ sót?

Tên gọi không bắt buộc đúng ba người hay ba chức danh. Khi một item liên quan thanh toán, có thể cần thêm chuyên gia bảo mật và đối tác. Khi liên quan khả năng truy cập, cần người hiểu tiêu chuẩn và người dùng phù hợp. **Mục đích là tạo sự hiểu chung**, không phải bảo đảm một thành phần đại diện cho mọi cuộc họp.

## 4. Làm rõ PBI từ góc nhìn người dùng, giá trị và Product Goal

Đầu tiên, nhóm cần trả lời **vì sao** hạng mục tồn tại. Một PBI mô tả đúng giải pháp vẫn có thể thiếu giá trị nếu không biết nhu cầu của người dùng.

### 4.1. Đặt câu hỏi về vấn đề trước khi viết thêm ticket

Ví dụ đầu vào: “Làm chatbot giải đáp khóa học”.

Hãy hỏi:

- Ai đang gặp khó: học viên mới, người đã thanh toán, hay nhân viên hỗ trợ?
- Họ muốn hoàn thành tác vụ gì và đang bị chặn ở đâu?
- Có dữ liệu hỗ trợ, quan sát, phỏng vấn hoặc nhật ký sự cố nào?
- Chatbot là giả thuyết giải pháp hay là ràng buộc bắt buộc đã được quyết định?
- Nếu chỉ thay đổi thông báo lỗi hoặc giản lược luồng, người dùng có đạt mục tiêu nhanh hơn không?
- Việc này đóng góp thế nào vào Product Goal hiện tại?

Một phát biểu rõ vấn đề hơn:

> Học viên mới không biết cách tiếp tục khi liên kết xác minh email đã hết hạn. Chúng ta muốn họ tự yêu cầu liên kết mới một cách an toàn, không cần gửi yêu cầu hỗ trợ.

Khi đó các lựa chọn có thể gồm **nút yêu cầu gửi lại**, **thông báo lỗi rõ ràng**, **cải thiện thời hạn liên kết** hoặc một phương án khác. Đội có cơ sở ưu tiên điều người dùng cần, không mặc định tính năng có công nghệ phức tạp nhất là tốt nhất.

### 4.2. Dùng user story như điểm bắt đầu thảo luận

Một mẫu thường dùng:

> **Là** [đối tượng], **tôi muốn** [năng lực/hành vi], **để** [lợi ích hoặc việc có thể hoàn tất].

Ví dụ:

> Là học viên đã đăng ký, tôi muốn yêu cầu lại liên kết xác minh email hết hạn để kích hoạt tài khoản và vào khóa học mà không phải liên hệ hỗ trợ.

**User story không phải định dạng bắt buộc cho mọi Product Backlog Item.** Một PBI có thể là lỗi, cải tiến kỹ thuật, thử nghiệm giá trị hoặc công việc liên quan bảo mật. Hình thức nào cũng cần đủ minh bạch để quyết định, nhưng không nhất thiết ép mọi công việc thành câu “Là người dùng, tôi muốn…” gượng ép.

### 4.3. Mục tiêu người dùng khác điều kiện chấp nhận

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Mục tiêu/outcome** | Người dùng thực sự sẽ làm tốt hơn điều gì? | Nhiều học viên tự xác minh thành công trong lần thử tiếp theo |
| **PBI/user story** | Năng lực sản phẩm nào được đề xuất? | Yêu cầu gửi lại liên kết khi liên kết cũ hết hạn |
| **Acceptance criteria (AC)** | Những hành vi cụ thể nào phải đúng? | Liên kết hết hạn bị từ chối; yêu cầu lại tạo liên kết mới hợp lệ, giới hạn chống lạm dụng |
| **Kiểm chứng** | Kiểm tra bằng gì? | Kết quả integration/E2E, kiểm tra bảo mật, hành vi người dùng |
| **Definition of Done** | Điều kiện chất lượng chung của Increment là gì? | Tích hợp, kiểm thử liên quan và kiểm soát áp dụng đạt chuẩn |

**Đạt AC và DoD** cho thấy Increment có thể đã hoàn tất theo phạm vi. **Outcome** cần được quan sát sau khi người dùng tiếp cận giải pháp. Đừng đòi phải đạt một tỷ lệ người dùng trong nhiều tuần mới được công nhận code Done; cũng đừng cho rằng một feature được release có nghĩa giả thuyết giá trị đã đúng.

## 5. Các chiều làm rõ một PBI trước khi lựa chọn

Refinement không chỉ là ước lượng. Một PBI có thể cần được làm rõ qua nhiều chiều, tùy rủi ro.

| Chiều thông tin | Câu hỏi chính | Dấu hiệu đã đủ để thảo luận lựa chọn |
|---|---|---|
| **Người dùng và bối cảnh** | Ai đang gặp khó gì, tại sao? | Các bên mô tả tương đối giống nhau về vấn đề |
| **Giá trị và thứ tự** | Vì sao làm sớm hơn việc khác? | Có liên hệ với Product Goal, phản hồi hoặc rủi ro |
| **Phạm vi** | Lát cắt này bao gồm và loại trừ gì? | Không nhầm chức năng tối thiểu với mọi biến thể mở rộng |
| **Hành vi nghiệp vụ** | Khi thành công, thất bại hoặc dữ liệu đặc biệt, hệ thống phải làm gì? | Có ví dụ/AC quan trọng đủ kiểm chứng |
| **Chất lượng và tuân thủ** | Bảo mật, dữ liệu, khả năng truy cập, hiệu năng nào cần bảo vệ? | Đã xác định điều kiện áp dụng cho AC hoặc DoD |
| **Phụ thuộc** | Có cần API, đội khác, dữ liệu, phê duyệt hoặc môi trường nào? | Các điểm chặn chính được nhận diện và có phương án xử lý |
| **Kích thước và bất định** | Developers có thể hoàn tất trong một Sprint không? | Item được chia nhỏ hoặc có thử nghiệm giảm bất định nếu cần |
| **Bằng chứng và phản hồi** | Làm sao biết đúng về kỹ thuật và có ích cho người dùng? | Có đường kiểm tra thực tế hoặc cách lấy phản hồi phù hợp |
| **Điều chưa biết** | Những giả định nào đang chi phối dự báo? | Không che giấu câu hỏi quan trọng; biết ai giúp làm rõ |

Không cần biến bảng này thành **một bộ hồ sơ với chín chữ ký**. Với chỉnh sửa nhỏ ít rủi ro, một cuộc trao đổi và một vài ví dụ là đủ. Với thanh toán, phân quyền, dữ liệu nhạy cảm hoặc hệ thống có nghĩa vụ kiểm định, cần thêm bằng chứng và chuyên môn theo rủi ro.

### 5.1. Các câu hỏi về dữ liệu và trạng thái thường bị bỏ sót

Ví dụ một item “học viên có thể lưu khóa yêu thích”:

- Dữ liệu được lưu theo tài khoản hay chỉ trong trình duyệt?
- Nếu người dùng đăng xuất rồi đăng nhập lại, trạng thái còn không?
- Nếu lưu cùng khóa hai lần, có tạo bản ghi trùng không?
- Nếu hai tài khoản dùng chung thiết bị, có lộ dữ liệu không?
- Nếu dịch vụ ghi dữ liệu lỗi, UI có hiển thị thành công giả không?
- Nếu khóa bị ẩn hoặc ngừng mở đăng ký, danh sách thể hiện thế nào?

Chỉ khi thảo luận, nhóm mới phát hiện một nút đổi màu **không đủ** để đáp ứng nhu cầu tìm lại khóa sau này.

### 5.2. Chất lượng không phải phần “sẽ làm khi còn thời gian”

Một lát cắt nhỏ vẫn phải đúng và an toàn trong phạm vi hỗ trợ. Ví dụ, xử lý thanh toán “happy path” mà bỏ qua truy cập trái quyền hoặc callback lặp có thể gây sai dữ liệu và tiền.

Khi refinement, hãy hỏi:

1. Điều kiện nào là bắt buộc để chức năng hoạt động đúng?
2. Điều kiện nào thuộc DoD chung và phải được đáp ứng cho mọi Increment liên quan?
3. Trường hợp mở rộng nào có thể làm sau mà không gây hiểu nhầm hoặc rủi ro không chấp nhận được?
4. Có cần mời chuyên gia bảo mật, dữ liệu, vận hành hoặc tuân thủ sớm không?

Nếu một phụ thuộc bảo mật chưa sẵn sàng, cần phản ánh điều đó trong kích thước, thứ tự và khả năng lựa chọn thay vì âm thầm hạ DoD.

## 6. Viết acceptance criteria và ví dụ thay cho suy đoán

**Acceptance criteria** giúp các bên thống nhất hành vi quan sát được của một PBI. Scrum Guide không bắt buộc một mẫu AC riêng, nhưng việc dùng tiêu chí rõ thường giúp refinement và kiểm thử đáng tin hơn.

### 6.1. Từ câu mơ hồ đến điều kiện có thể kiểm tra

**PBI:** “Học viên yêu cầu lại liên kết xác minh email”.

**Tiêu chí mơ hồ:** “Hệ thống gửi lại nhanh, an toàn, không có lỗi”.

**Tiêu chí rõ hơn:**

| ID | Tiêu chí chấp nhận minh họa |
|---|---|
| **AC-01** | Khi liên kết xác minh đã hết hạn, hệ thống không kích hoạt tài khoản bằng liên kết cũ và hiển thị thông báo phù hợp. |
| **AC-02** | Người dùng đủ điều kiện có thể yêu cầu liên kết mới; hệ thống gửi liên kết tới địa chỉ đã đăng ký theo chính sách bảo mật. |
| **AC-03** | Liên kết hợp lệ được dùng theo quy tắc đã thống nhất; liên kết đã dùng hoặc bị thu hồi không thể bị lạm dụng để xác minh lại. |
| **AC-04** | Yêu cầu lặp quá giới hạn được xử lý theo chính sách chống lạm dụng, không tiết lộ thông tin tài khoản một cách không cần thiết. |
| **AC-05** | Nếu dịch vụ gửi email lỗi, sản phẩm không xác nhận chắc chắn đã gửi thành công khi chưa có bằng chứng phù hợp. |
| **AC-06** | Thao tác và thông báo liên quan đáp ứng các yêu cầu khả năng truy cập của sản phẩm. |

Các tiêu chí này chỉ là **ví dụ minh họa**. Ngưỡng giới hạn, chính sách liên kết cũ, định nghĩa “đã gửi” và yêu cầu công bố thông tin phải do nhóm, chuyên gia liên quan và người có thẩm quyền thống nhất theo hệ thống thực.

### 6.2. Dùng Given–When–Then để tìm hiểu khác biệt

~~~gherkin
Feature: Yeu cau lai lien ket xac minh email

  Scenario: Lien ket cu da het han
    Given hoc vien A co lien ket xac minh da het han
    When A mo lien ket cu
    Then tai khoan khong duoc xac minh bang lien ket do
    And he thong dua ra huong dan yeu cau lien ket moi phu hop

  Scenario: Yeu cau lien ket moi hop le
    Given A co tai khoan dang cho xac minh
    And A du dieu kien duoc yeu cau gui lai
    When A yeu cau lien ket xac minh moi
    Then he thong thuc hien yeu cau gui theo chinh sach
    And A nhan duoc thong tin trang thai trung thuc

  Scenario: Yeu cau lap qua gioi han
    Given A da vuot gioi han gui lai duoc phep
    When A tiep tuc yeu cau
    Then he thong ap dung gioi han chong lam dung
    And phan hoi khong de lo du lieu nhay cam
~~~

Đây là **đặc tả bằng ví dụ**; chưa phải bằng chứng test đã chạy. Nhóm có thể chuyển chúng thành kiểm thử tự động bằng công cụ phù hợp, dùng test API/integration/E2E hoặc kiểm chứng thủ công theo rủi ro. Điều quan trọng là mọi bên hiểu cùng một hành vi trước khi coi hạng mục sẵn sàng để chọn.

### 6.3. AC không phải bản thiết kế nội bộ

Ví dụ “liên kết cũ không còn hiệu lực” mô tả hành vi người dùng cần nhận được. Nó thường không cần quy định tên bảng dữ liệu, framework hay cấu trúc lớp. Những quyết định kỹ thuật có thể được ghi trong thiết kế hoặc task liên quan; không ép Product Owner ra quyết định implementation nếu chưa có lý do nghiệp vụ.

Ngoại lệ: nếu một ràng buộc kỹ thuật là điều kiện có thật (ví dụ hệ thống phải dùng giao thức tích hợp do đối tác quy định), cần đưa nó vào thông tin item. **Linh hoạt về cách làm không đồng nghĩa bỏ qua những ràng buộc thực sự.**

## 7. Phân nhỏ Product Backlog Items theo giá trị

Một thành quả quan trọng của refinement là biến một hạng mục quá lớn thành **những phần có khả năng hoàn tất và kiểm chứng độc lập hơn**. Chia một epic thành các ticket frontend, backend, database không đủ nếu người dùng phải chờ tất cả mới có thể thực hiện được một hành vi.

### 7.1. Chia ngang và chia dọc

Hạng mục ban đầu: **“Cho phép học viên đăng ký khóa học”**.

**Cách chia ngang theo thành phần kỹ thuật:**

~~~text
Ticket UI: Xay toan bo cac man hinh dang ky
Ticket API: Xay toan bo API ghi danh va thanh toan
Ticket DB: Tao tat ca bang du lieu dang ky
Ticket TEST: Kiem thu tat ca tinh nang sau khi cac phan tren xong
~~~

Các task kỹ thuật vẫn có thể được dùng trong kế hoạch Developers, nhưng **mỗi task hoàn tất không đồng nghĩa một Increment tạo giá trị**.

**Cách chia theo lát cắt dọc:**

~~~text
PBI 1: Hoc vien da dang nhap ghi danh khoa mien phi
       con nhan dang ky va vao duoc bai hoc dau tien.

PBI 2: Hoc vien nhan thong bao dung khi khong du dieu kien
       ghi danh hoac khoa da dong.

PBI 3: Hoc vien thanh toan mot phuong thuc duoc ho tro,
       nhan trang thai dung va chi co quyen hoc khi hop le.

PBI 4: Hoc vien thay trang thai dang cho, that bai
       va co duong xu ly phu hop.

PBI 5: Mo rong them phuong thuc, quy tac uu dai
       hoac nhung bien the co gia tri.
~~~

Lát cắt đầu tiên cần UI, nghiệp vụ, dữ liệu, kiểm thử và quyền truy cập liên quan; nhưng nó có thể **hoàn tất một hành vi thực** theo phạm vi công bố. Nó không bao gồm mọi biến thể đăng ký trong tương lai.

### 7.2. Các chiều chia thường có ích

| Chiều chia | Hạng mục lớn | Một lát cắt có thể kiểm chứng |
|---|---|---|
| **Bước hành trình** | Quản lý toàn bộ quá trình ghi danh | Học viên ghi danh và mở bài đầu tiên |
| **Loại đối tượng** | Tìm kiếm tất cả loại nội dung | Tìm khóa học theo tên trước khi thêm giảng viên/bài viết |
| **Quy tắc nghiệp vụ** | Hỗ trợ mọi chương trình giảm giá | Áp một mã hợp lệ theo quy tắc cơ bản và kiểm tra tổng tiền |
| **Biến thể kênh** | Mọi thiết bị và kênh | Một kênh được hỗ trợ với chất lượng đầy đủ trong phạm vi đó |
| **Nhóm dữ liệu** | Báo cáo toàn tổ chức | Báo cáo đúng cho một nhóm có quyền truy cập cụ thể |
| **Mức bất định** | Tích hợp nhiều nhà cung cấp chưa rõ | Thử kết nối sandbox và kiểm chứng rủi ro trước khi chọn phạm vi sản phẩm lớn |
| **Hành vi cơ bản → nâng cao** | Hệ thống thông báo phức tạp | Hiển thị một trạng thái quan trọng chính xác, mở rộng theo phản hồi |

Không có chiều chia tốt nhất cho mọi trường hợp. Nhóm cần tìm lát cắt **đủ nhỏ để hoàn tất trong một Sprint, đủ đúng để kiểm chứng và đủ có ý nghĩa để học**.

### 7.3. Dùng INVEST như bộ câu hỏi gợi ý

Một heuristic thường dùng để đánh giá user story là **INVEST**:

| Chữ | Ý nghĩa | Câu hỏi với PBI |
|---|---|---|
| **I — Independent** | Tương đối độc lập | Có thể kiểm chứng và hoàn tất mà không phải chờ toàn bộ epic không? |
| **N — Negotiable** | Có thể thương lượng | Story nêu nhu cầu hay khóa trước mọi giải pháp? |
| **V — Valuable** | Có giá trị | Hành vi này góp phần vào mục tiêu người dùng hoặc giảm rủi ro quan trọng không? |
| **E — Estimable** | Có thể đánh giá kích thước | Developers hiểu đủ phạm vi, phụ thuộc và bất định chưa? |
| **S — Small** | Đủ nhỏ | Có thể đáp ứng DoD trong khoảng thời gian thực hiện gần không? |
| **T — Testable** | Có thể kiểm chứng | Có thể tạo ví dụ và quan sát đúng/sai không? |

INVEST **không phải quy tắc chính thức hoặc checklist chấm điểm bắt buộc của Scrum**. Một item có phụ thuộc thật vẫn có thể đáng làm; điều cần thiết là làm rõ và quản lý phụ thuộc, không chia giả tạo cho đủ sáu chữ.

### 7.4. Không chia nhỏ bằng cách bỏ các điều kiện thiết yếu

Lát cắt “thanh toán thành công” không thể được coi là dùng được nếu:

- UI báo thanh toán thành công trước xác nhận đáng tin.
- Người dùng nhận quyền học khi giao dịch chưa thành công theo quy tắc.
- Callback lặp khiến ghi nhận hai lần hoặc cấp quyền sai.
- Giao diện/API để tài khoản khác truy cập dữ liệu trái quyền.
- Hệ thống không biết cách xử lý lỗi quan trọng đã thuộc phạm vi công bố.

Có thể phân kỳ các phương thức thanh toán, chương trình khuyến mãi hoặc cải tiến giao diện. **Không nên phân kỳ bằng cách bỏ tính đúng đắn, DoD hoặc kiểm soát an toàn bắt buộc khỏi lát cắt hiện tại.**

### 7.5. Spike và nhiệm vụ khám phá cần được gọi đúng tên

Nếu đội chưa biết đối tác có thể gửi trạng thái giao dịch theo yêu cầu, một **spike có thời hạn** có thể hữu ích:

> Trong khoảng thời gian đã thống nhất, kiểm tra API sandbox cho trạng thái thành công, đang chờ, thất bại và callback lặp; ghi lại những giới hạn, rủi ro và phương án đề xuất.

Spike giảm bất định để lựa chọn PBI, **không tự động là Increment hoàn tất của sản phẩm** trong Scrum. Nếu chỉ chạy prototype với mock, không báo rằng hệ thống thanh toán production đã sẵn sàng.

## 8. Refinement và mức độ “sẵn sàng” cho Sprint Planning

Theo Scrum Guide 2020, **Product Backlog Items có thể được Scrum Team hoàn tất trong một Sprint được coi là đủ sẵn sàng để được lựa chọn tại Sprint Planning**. Chúng thường đạt mức minh bạch này sau các hoạt động refinement.

Điều đó không có nghĩa Scrum bắt buộc một con dấu **Ready** hoặc một hội đồng duyệt toàn bộ tài liệu. Đây là cách nhận diện **mức độ hiểu đủ để lập kế hoạch hoàn tất một Increment**.

### 8.1. Một số câu hỏi hỗ trợ quyết định lựa chọn

| Câu hỏi | Tại sao hữu ích? |
|---|---|
| Người dùng và vấn đề đã đủ rõ? | Tránh hoàn tất đúng một tính năng nhưng sai nhu cầu |
| PBI đóng góp gì vào Product Goal/Sprint Goal dự kiến? | Giúp chọn việc có mục đích chung |
| Phạm vi và điều không nằm trong lát cắt đã minh bạch? | Giảm hiểu nhầm và phình phạm vi |
| Có ví dụ/AC quan trọng để biết hành vi đúng? | Giúp kiểm chứng và thống nhất cách hiểu |
| Những ràng buộc bảo mật, dữ liệu, chất lượng đã được nhận diện? | Tránh giao không an toàn hoặc hạ DoD |
| Những phụ thuộc có thể chặn việc đã được xử lý hoặc quản lý? | Giúp dự báo khả năng hoàn tất thực |
| Developers có thông tin đủ để đánh giá kích thước? | Tránh nhận công việc quá rộng hoặc ước lượng giả |
| Có thể đạt DoD trong Sprint bằng năng lực hiện có? | Giữ Increment thực sự hoàn tất |
| Có cách kiểm chứng sau khi xây và nhận phản hồi không? | Gắn đầu ra với học tập và thích ứng |

Không phải mỗi câu cần một tài liệu riêng. Trên một backlog item nhỏ, vài câu mô tả, tiêu chí và đường dẫn phù hợp có thể đủ. Với giao dịch tiền hoặc dữ liệu nhạy cảm, độ sâu kiểm chứng cần lớn hơn.

### 8.2. Phân biệt ba trạng thái mà nhóm hay nhầm

- **Được ưu tiên cao:** Product Owner đánh giá item đáng xem sớm.
- **Đủ rõ và đủ nhỏ để lựa chọn:** Developers có thể cân nhắc khả năng hoàn tất trong Sprint theo DoD.
- **Đã chọn vào Sprint Backlog:** Developers cùng Scrum Team trong Sprint Planning lựa chọn dựa trên Sprint Goal và năng lực thực tế.

Một item rất cấp bách có thể chưa đủ rõ; lúc đó đội ưu tiên **làm rõ hoặc giảm bất định** trước khi cam kết toàn bộ. Một item rất rõ có thể chưa đáng làm vì giá trị thấp. Một item đã chuẩn bị tốt cũng không tự vào Sprint nếu không phục vụ mục tiêu và năng lực hiện tại.

### 8.3. Definition of Ready không phải commitment của Scrum

Một số đội tự xây **Definition of Ready (DoR)** để nhắc những điều cần thảo luận trước khi chọn PBI. Điều này có thể hữu ích nếu nó giúp minh bạch và giảm công việc bị chặn.

Nhưng:

- Scrum Guide **không bắt buộc DoR**.
- Không nên dùng DoR để biến Scrum thành quy trình phê duyệt tài liệu qua nhiều cấp.
- Không nên dùng DoR làm lý do người có chuyên môn từ chối trao đổi trực tiếp.
- Không tự cho rằng một PBI “đã Ready” chắc chắn sẽ được chọn hoặc hoàn tất.
- Không nhầm DoR với **Definition of Done** — commitment chính thức gắn với Increment.

**DoD bảo vệ trạng thái hoàn tất của Increment. DoR nếu được dùng chỉ hỗ trợ mức minh bạch trước khi lựa chọn**, không thay thế DoD và không trở thành một artifact chính thức của Scrum.

## 9. Refinement liên hệ với từng sự kiện Scrum ra sao?

### 9.1. Trước và trong Sprint Planning

Những PBI gần được chọn nên đã có đủ thông tin để Developers đánh giá kích thước và hiểu rủi ro. Khi đó Sprint Planning có thể tập trung vào ba chủ đề:

1. **Vì sao Sprint này có giá trị?** Product Owner đề xuất hướng gia tăng giá trị; Scrum Team cùng xác định Sprint Goal.
2. **Có thể hoàn tất những gì trong Sprint?** Developers trao đổi với Product Owner và lựa chọn PBI dựa trên năng lực, kết quả trước đó, DoD và hiểu biết hiện tại.
3. **Công việc đã chọn sẽ được thực hiện bằng cách nào?** Developers lập kế hoạch tạo Increment và điều chỉnh chi tiết khi học thêm.

Nếu Planning thường xuyên kéo dài vì nhóm chưa biết PBI nghĩa là gì, đó có thể là dấu hiệu refinement chưa đủ hiệu quả. Nhưng không nhất thiết giải pháp là **đưa thêm tất cả item vào một buổi họp hàng tuần**; trước tiên phải xác định những câu hỏi nào thường thiếu và ai có thể làm rõ đúng thời điểm.

### 9.2. Trong Sprint và Daily Scrum

Scrum Team liên tục phát hiện dữ liệu mới khi xây Increment. Developers có thể phát hiện một giả định API sai, một trường hợp dữ liệu chưa được xem xét hoặc một phụ thuộc cản Sprint Goal.

Daily Scrum là **sự kiện 15 phút của Developers** để kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog nếu cần. Nó **không phải một phiên refinement chung cho toàn Product Backlog** và cũng không phải buổi báo cáo cá nhân cho quản lý.

Nếu một câu hỏi nghiệp vụ cần thảo luận sâu, Developers nên kết nối với Product Owner/người liên quan ngoài Daily Scrum để làm rõ; các thành viên không cần giữ toàn bộ đội đứng chờ trong 15 phút. Điều mới học được có thể tác động:

- **PBI đang thực hiện:** làm rõ và thương lượng phạm vi với Product Owner khi phù hợp, không làm giảm chất lượng hay gây nguy hiểm cho Sprint Goal.
- **PBI tương lai:** cập nhật Product Backlog về hành vi, phụ thuộc hoặc rủi ro mới.
- **Cách triển khai:** Developers điều chỉnh Sprint Backlog và các task theo dữ liệu thực tế.

Trong Sprint, **không có thay đổi nào được phép gây nguy hiểm cho Sprint Goal; chất lượng không được giảm**. Phạm vi có thể được làm rõ hoặc thương lượng lại với Product Owner khi học thêm. Điều này tránh cách hiểu sai rằng “Agile linh hoạt” đồng nghĩa thay Sprint Goal liên tục theo mọi yêu cầu mới.

### 9.3. Sau Sprint Review

Sprint Review là cơ hội Scrum Team và stakeholders **kiểm tra kết quả Sprint và điều chỉnh bước tiếp theo**. Đội có thể nhận dữ liệu rằng người dùng không hiểu màn hình xác minh, một quy định vừa thay đổi hoặc tính năng mới ít có giá trị hơn dự kiến.

Những thông tin này ảnh hưởng Product Backlog: có item được nâng thứ tự, có item cần chia nhỏ, có item không còn cần thiết. Refinement tiếp tục với **những quyết định mới từ Review**, không chỉ với yêu cầu kỹ thuật đã xác định từ đầu.

Sprint Review **không phải cổng phê duyệt bắt buộc để phát hành**; Increment đạt DoD có thể được phát hành trước thời điểm Review nếu điều kiện vận hành và tuân thủ cho phép.

### 9.4. Sau Sprint Retrospective

Retrospective giúp Scrum Team lập kế hoạch tăng chất lượng và hiệu quả. Nếu liên tục có PBI bị chặn vì thiếu test data hoặc Product Owner không thể trả lời quy tắc trong lúc phát triển, nhóm có thể cải thiện **cách refinement được tổ chức**:

- Mời người hiểu nghiệp vụ tham gia sớm hơn với những item rủi ro.
- Thống nhất bộ ví dụ nghiệp vụ tối thiểu cho nhóm PBI tương tự.
- Chuẩn bị môi trường thử hoặc dữ liệu đại diện trước khi chọn.
- Giảm số item mở cùng lúc để tập trung hoàn tất.
- Thử một phiên trao đổi ngắn không đồng bộ trước Planning.
- Tạo cơ chế nhanh để giải quyết câu hỏi cần thẩm quyền ngoài đội.

Một cải tiến có giá trị là thay đổi **được thử, đo và xem lại**, không chỉ một quy tắc mới ghi trong biên bản.

## 10. Tổ chức refinement liên tục trong thực tế

Không có lịch bắt buộc, nhưng nhóm cần **khả năng trao đổi đủ thường xuyên** để Product Backlog không trở thành danh sách thiếu căn cứ.

### 10.1. Minh họa nhịp hoạt động trong Sprint hai tuần

| Thời điểm minh họa | Hoạt động có thể thực hiện | Tại sao? |
|---|---|---|
| **Trước Sprint** | Product Owner chia sẻ mục tiêu, những PBI có khả năng được chọn và vấn đề chưa rõ | Developers có bối cảnh trước Planning |
| **Đầu Sprint** | Trao đổi ngắn về một hoặc hai PBI rủi ro cao của Sprint tới | Tạo thời gian xử lý phụ thuộc trước khi cần chọn |
| **Giữa Sprint** | Phiên thảo luận với nghiệp vụ, phát triển và kiểm thử; chia nhỏ, tìm phản ví dụ, kiểm tra AC | Giảm hiểu nhầm và đánh giá kích thước |
| **Bất cứ khi nào có phát hiện mới** | Làm rõ trực tiếp hoặc không đồng bộ với người phù hợp, cập nhật item liên quan | Không phải chờ lịch họp cố định để sửa giả định sai |
| **Sau Sprint Review** | Xem phản hồi và thay đổi thứ tự, phạm vi hoặc giả thuyết của PBI | Đưa thông tin mới vào Product Backlog |
| **Sau Retrospective** | Điều chỉnh chính sách/chất lượng refinement nếu cần | Cải thiện cách phối hợp và giảm chờ đợi |

Đây là **lịch minh họa**, không phải quy định Scrum. Nếu Sprint chỉ một tuần, hoạt động có thể gọn hơn; nếu sản phẩm phức tạp, cần nhiều phiên thảo luận khác nhau. Điểm cần giữ là **sự liên tục và tác dụng thực tế**, không phải số phiên họp.

### 10.2. Mẫu một phiên refinement 45–60 phút

| Khoảng thời gian | Hoạt động | Kết quả mong muốn |
|---|---|---|
| **0–10 phút** | Làm rõ Product Goal, người dùng, vấn đề và lý do ưu tiên | Cùng hiểu vì sao item quan trọng |
| **10–20 phút** | Thảo luận hành vi, ví dụ thành công/lỗi và ràng buộc | Tìm những giả định khác nhau |
| **20–35 phút** | Đề xuất lát cắt dọc và phạm vi không bao gồm | Có một số PBI nhỏ có thể kiểm chứng |
| **35–45 phút** | Kiểm tra phụ thuộc, dữ liệu, DoD và phương án kiểm chứng | Biết rủi ro và điều kiện hoàn tất |
| **45–55 phút** | Developers đánh giá kích thước; Product Owner trao đổi giá trị và thứ tự | Có căn cứ lựa chọn hoặc làm rõ thêm |
| **55–60 phút** | Ghi quyết định, người theo dõi câu hỏi và thời điểm xem lại | Backlog thay đổi thực, không chỉ có biên bản |

Không bắt buộc phải hoàn tất tất cả item trong một phiên. Nếu một rủi ro cần chuyên gia bên ngoài, kết quả tốt có thể là **một câu hỏi rõ, người cần trả lời và mốc quyết định**, thay vì ép nhóm đoán và ghi Ready.

### 10.3. Giữ thảo luận có trọng tâm

Những cách giúp giảm thời gian chờ:

1. Chọn **ít item** có khả năng được ưu tiên gần, không trình bày toàn bộ backlog.
2. Gửi trước bối cảnh, phản hồi người dùng hoặc ví dụ hiện có.
3. Mời **đúng người** cần trả lời câu hỏi; không yêu cầu cả tổ chức dự mọi cuộc trao đổi.
4. Phân biệt câu hỏi **cần quyết ngay để chọn** với câu hỏi có thể tìm hiểu trong khi phát triển.
5. Khi hạng mục quá lớn, ưu tiên tìm **lát cắt** thay vì tranh luận độ chính xác của ước lượng.
6. Ghi lại thông tin ngay trong PBI hoặc liên kết đáng tin, tránh tạo hai nguồn mô tả dễ lệch nhau.
7. Không để refinement biến thành một cuộc họp giao từng task cho mỗi Developer.

### 10.4. Làm rõ không đồng bộ

Với đội phân tán hoặc người hiểu nghiệp vụ có ít thời gian, một số câu hỏi có thể được giải quyết qua văn bản có cấu trúc:

~~~text
PBI: US-VERIFY-04 — Gui lai lien ket xac minh

VAN DE:
  Hoc vien bi chan khi lien ket cu het han.

GIA THUYET:
  Cho phep yeu cau lai mot cach an toan giup ho tu xac minh.

CAU HOI CAN QUYET:
  1. Chinh sach gioi han gui lai la gi?
  2. Lien ket cu con hieu luc khi phat lien ket moi khong?
  3. Co can thong bao cho ho tro khi gui that bai khong?

RUI RO:
  Lo thong tin tai khoan, spam email, hien thi trang thai sai.

NGUOI CO THE TRA LOI:
  Product Owner + chuyen gia bao mat + Developers.

MOC CAN:
  Truoc khi item duoc can nhac cho Sprint Planning.

QUYET DINH SAU TRAO DOI:
  [Ghi quy tac, AC, pham vi va nhung dieu chua ro.]
~~~

Một nội dung ngắn như vậy hữu ích hơn mười tin nhắn “ai có thể giải thích item này?”. Tuy nhiên, với vấn đề phức tạp dễ hiểu khác nhau, trao đổi đồng bộ có thể nhanh hơn gửi nhiều vòng văn bản.

## 11. Tình huống xuyên suốt: đăng ký khóa học từ epic đến những PBI có thể chọn

> **Tình huống giả định phục vụ học tập.** Những ví dụ, quyết định và kết quả dưới đây không phải dữ liệu thực tế của một nền tảng cụ thể.

Scrum Team có Product Goal: **“Học viên đủ điều kiện tự đăng ký và vào học đúng khóa thuận lợi, an toàn.”** Trước Sprint Planning, Product Backlog có item ưu tiên cao:

> **EPIC-ENROLL:** Xây hệ thống đăng ký khóa học cho tất cả hình thức và phương thức thanh toán.

### 11.1. Phát hiện mức độ mơ hồ

Trong trao đổi ban đầu:

- Product Owner muốn giảm tỷ lệ học viên bỏ dở sau khi chọn khóa.
- Developers chưa rõ khi nào cấp quyền học sau giao dịch.
- Chuyên gia kiểm thử hỏi về ghi danh lặp và trạng thái thất bại.
- Hỗ trợ cho biết người học thường không hiểu “Đang xử lý”.
- Vận hành xác nhận sandbox của một nhà cung cấp thanh toán chưa có đủ quyền thử.
- Bảo mật yêu cầu xác định các tình huống truy cập dữ liệu trái quyền.

Nếu cố đưa nguyên epic vào Sprint, Developers không có căn cứ để khẳng định khả năng hoàn tất theo DoD.

### 11.2. Chuyển sang các PBI có hành vi riêng

| PBI minh họa | Giá trị hoặc rủi ro được giải quyết | Điều kiện cần làm rõ thêm |
|---|---|---|
| **ENR-01** — Ghi danh khóa miễn phí | Học viên hợp lệ ghi danh và mở bài đầu | Điều kiện khóa mở, quyền truy cập, yêu cầu lặp |
| **ENR-02** — Xử lý từ chối ghi danh | Trạng thái bị từ chối rõ và không cấp quyền sai | Khóa đóng, thiếu quyền, hết chỗ nếu áp dụng |
| **ENR-03** — Xem trạng thái đơn | Người học biết đã được xác nhận hay đang chờ | Nguồn dữ liệu đáng tin, các trạng thái |
| **ENR-04** — Thanh toán một phương thức | Đăng ký trả phí có xác nhận giao dịch hợp lệ | API đối tác, callback lặp, xử lý lỗi, bảo mật |
| **ENR-05** — Hoàn tiền/hủy theo chính sách | Xử lý vòng đời giao dịch sau mua | Quy tắc hoàn tiền, trạng thái quyền học |
| **ENR-06** — Báo cáo quản trị nâng cao | Hỗ trợ vận hành/đánh giá kinh doanh | Nhu cầu người dùng nội bộ, phạm vi dữ liệu |

Đây chỉ là cách chia ban đầu. Nếu không có khóa miễn phí trong sản phẩm, **ENR-01 không tự nhiên có giá trị** và không nên chọn chỉ vì dễ hơn thanh toán. Product Owner và Scrum Team cần kiểm tra đối tượng sử dụng thực và Product Goal.

### 11.3. Làm rõ ENR-01 bằng trao đổi liên chức năng

**Story minh họa:**

> Là học viên đã đăng nhập, tôi muốn ghi danh một khóa miễn phí còn nhận đăng ký để bắt đầu học mà không phải chờ nhân viên hỗ trợ.

**Giới hạn phạm vi:** khóa miễn phí và đủ điều kiện; chưa bao gồm thanh toán, mã giảm giá hay hoàn tiền. Tuy nhiên, điều kiện phân quyền, dữ liệu và lỗi thiết yếu vẫn phải được xử lý.

**Acceptance criteria:**

| ID | Hành vi cần đúng |
|---|---|
| AC-01 | Khi học viên đủ điều kiện ghi danh khóa miễn phí đang mở, hệ thống tạo đúng quan hệ ghi danh cho tài khoản và khóa. |
| AC-02 | Sau ghi danh hợp lệ, học viên nhìn thấy khóa trong danh sách của mình và mở được nội dung được phép. |
| AC-03 | Khi yêu cầu được lặp lại, hệ thống không tạo ghi danh trùng gây sai dữ liệu hoặc quyền. |
| AC-04 | Khi khóa đóng đăng ký hoặc tài khoản không đủ điều kiện, hệ thống từ chối đúng và không cấp quyền. |
| AC-05 | Tài khoản khác không thể đọc/sửa ghi danh hoặc cấp quyền trái phép qua UI/API. |
| AC-06 | Khi dịch vụ ghi danh lỗi, sản phẩm không xác nhận thành công giả và có thông báo phù hợp. |

**Bằng chứng kỹ thuật:** kiểm tra UI–API–dữ liệu, đăng nhập bằng hai tài khoản thử, yêu cầu lặp, luồng lỗi, test tích hợp trên build xác định. **Bằng chứng giá trị:** sau khi cung cấp cho học viên phù hợp, quan sát họ có tự ghi danh và vào bài đầu dễ hơn không.

**Những điều còn mở:** có giới hạn số người đăng ký không? Trạng thái của khóa mới ẩn có khác không? Nếu câu trả lời ảnh hưởng lát cắt đang chọn, cần làm rõ trước khi dự báo; nếu là biến thể nâng cao không cần cho phạm vi này, có thể ghi thành PBI sau.

### 11.4. Làm rõ ENR-04 bằng giảm rủi ro trước

Với thanh toán, Developers chưa có sandbox và chưa biết cơ chế callback lặp. Không nên chọn “tích hợp mọi phương thức” chỉ vì PBI đứng cao trong Product Backlog.

Nhóm có thể:

1. Đề nghị thử một **spike tích hợp có giới hạn thời gian**.
2. Xác định câu hỏi cần trả lời: trạng thái đáng tin, lỗi, callback lặp, idempotency, điều kiện cấp quyền.
3. Làm rõ yêu cầu bảo mật và người có quyền phê duyệt.
4. Sau khi có dữ liệu, chia phần triển khai thành một lát cắt dọc có thể đạt DoD.
5. Công khai rủi ro còn lại trong Sprint Planning và dự báo release.

Nếu kết quả spike chỉ dựa vào mock, cần ghi rõ **chưa chứng minh tích hợp với dịch vụ thật**. Không ghi Done cho luồng production dựa trên demo sandbox.

### 11.5. Sau refinement, điều gì có thể thay đổi?

Trước refinement:

> “Xây hệ thống đăng ký khóa học. Ưu tiên cao. Developers hãy ước lượng.”

Sau refinement:

> “ENR-01 có phạm vi ghi danh miễn phí, AC kiểm tra được, phụ thuộc đã biết, Developers đánh giá có thể hoàn tất theo DoD trong một Sprint. ENR-04 cần thêm kết quả thử tích hợp. ENR-06 có giá trị chưa đủ rõ, Product Owner cân nhắc giữ thấp hơn các trở ngại của người học.”

Tại **Sprint Planning**, Scrum Team vẫn phải xét Sprint Goal và năng lực, Developers vẫn chịu trách nhiệm lựa chọn công việc. **Refinement tốt không tự động có nghĩa mọi item đã làm rõ đều phải vào Sprint.**

### 11.6. Phản hồi tiếp tục tác động backlog

Giả sử ENR-01 được hoàn tất, Sprint Review cho thấy nhiều học viên vẫn không tìm thấy nút ghi danh. Product Owner cân nhắc một PBI làm rõ vị trí/hướng dẫn và quan sát hành vi thực, thay vì mặc định bước tiếp là thanh toán.

Refinement bắt đầu **lại** từ điều mới học được. Chính vòng lặp này giúp Product Backlog là danh sách mới nổi, thay vì một bản hợp đồng đóng băng từ đầu dự án.

## 12. Refinement không được đánh đổi Sprint Goal, DoD và quyền tự quản lý

### 12.1. Đừng dùng refinement để “đổi scope trong bóng tối”

Khi học thêm trong Sprint, có thể cần làm rõ hành vi của item đang triển khai hoặc thương lượng phạm vi với Product Owner. Nhưng nếu yêu cầu mới gây nguy hiểm cho Sprint Goal, Scrum Team phải kiểm tra lại quyết định; không nên tự động thêm việc mà không cân nhắc tác động.

Trong Scrum, một Sprint có thể bị hủy nếu **Sprint Goal trở nên lỗi thời**, và **chỉ Product Owner có quyền hủy Sprint**. Đây là trường hợp đặc biệt, không phải một cách quản lý thay đổi thông thường mỗi khi xuất hiện yêu cầu mới.

### 12.2. Refinement không phải nơi Product Owner giao task kỹ thuật

Trong refinement, Developers cần được nghe vấn đề và tự đánh giá kích thước/cách thực hiện. Product Owner có thể làm rõ giá trị, phạm vi và thứ tự, nhưng không nên giao cố định từng task cho mỗi Developer như một cơ chế quản lý trực tiếp. **Developers tự quản lý kế hoạch công việc** trong phạm vi Scrum Team.

### 12.3. Không dùng AC để hạ DoD

Một PBI có thể đáp ứng tất cả acceptance criteria riêng nhưng vẫn chưa đạt DoD chung vì thiếu tích hợp hoặc kiểm tra bảo mật áp dụng. Khi đó chưa thể xem nó là một phần của Increment hoàn tất. Nếu hạng mục được làm rõ thành một lát cắt nhỏ hơn, lát cắt ấy vẫn phải đạt DoD cho phạm vi của nó.

### 12.4. Khách hàng cần giá trị, không cần một backlog “đẹp”

Một backlog có tiêu đề, user story, story point, AC và tag đầy đủ nhưng không được dùng để ra quyết định thì vẫn có thể là gánh nặng hành chính. Trái lại, một PBI ngắn, được nhóm hiểu thống nhất và có bằng chứng rõ, có thể đủ để phát triển an toàn.

**Chất lượng refinement được thể hiện qua khả năng chọn và hoàn tất công việc có ý nghĩa, không qua số trường đã điền.**

## 13. Đánh giá hiệu quả refinement bằng dữ liệu và hành vi

Scrum không bắt buộc một chỉ số riêng để đo backlog refinement. Nhóm có thể chọn một số tín hiệu để thấy hoạt động làm rõ có giảm hiểu nhầm và rủi ro hay không.

| Tín hiệu | Gợi ý điều cần kiểm tra | Giới hạn diễn giải |
|---|---|---|
| **PBI thường xuyên không hoàn tất vì quá lớn** | Việc chia lát cắt trước khi chọn có đủ không? | Công việc phức tạp vẫn có bất định; không tự quy lỗi refinement |
| **Thời gian chờ quyết định nghiệp vụ** | Có đưa đúng người vào trao đổi sớm không? | Chờ có thể đến từ quyền hạn tổ chức ngoài đội |
| **Tỉ lệ làm lại do hiểu sai AC** | Các bên có cùng hiểu hành vi trước khi xây không? | Thay đổi do phản hồi mới không luôn là “làm lại lãng phí” |
| **Work item age và cycle time** | Item bị chặn lâu ở đâu trong dòng công việc? | Phải nhất quán định nghĩa bắt đầu/kết thúc và loại item |
| **WIP** | Có kéo quá nhiều item chưa rõ vào làm cùng lúc? | WIP thấp không tự chứng minh giá trị |
| **Throughput** | Có hoàn tất item đều đặn hơn sau cải tiến không? | Chia ticket nhỏ giả tạo có thể làm số item tăng |
| **Increment đạt DoD** | Bao nhiêu khả năng thực sự hoàn tất, tích hợp và kiểm chứng? | Vẫn cần xem có tạo kết quả cho người dùng không |
| **Phản hồi người dùng sớm** | Những giả định sai có được phát hiện trước khi đầu tư lớn không? | Định tính và định lượng cần đúng bối cảnh |
| **Thời gian và số người tham gia refinement** | Có lãng phí thời gian do quá nhiều cuộc họp không? | Ít giờ họp không đồng nghĩa ít hiểu nhầm, nhiều giờ họp không đồng nghĩa chất lượng cao |

Các phép đo flow như WIP, work item age, throughput và cycle time đến từ cách nhìn của Kanban và có thể bổ sung cho Scrum. **Chúng không phải các sự kiện hoặc cam kết bắt buộc của Scrum Guide**. Nên dùng để cải tiến hệ thống, tránh biến thành cơ sở chấm điểm cá nhân.

### 13.1. Một thử nghiệm cải tiến có thể kiểm tra

Giả sử trong ba Sprint, nhiều PBI đến lúc phát triển mới phát hiện thiếu quy tắc xử lý lỗi thanh toán. Nhóm thử:

- Trước khi chọn các PBI thanh toán, tổ chức một phiên trao đổi ngắn gồm Product Owner, Developers, người kiểm thử và chuyên gia bảo mật.
- Viết ba đến năm ví dụ về thành công, thất bại và yêu cầu lặp.
- Ghi các quyết định chưa rõ và người chịu trách nhiệm làm rõ.
- Theo dõi trong hai Sprint tiếp theo: số item bị chặn do quy tắc nghiệp vụ, thời gian chờ quyết định, lỗi phát hiện sau tích hợp.

Nếu điểm chặn giảm mà thời gian họp tăng rất ít, giữ cách làm. Nếu các ví dụ không cải thiện được vì mọi vấn đề đến từ môi trường đối tác, chuyển trọng tâm sang phụ thuộc kỹ thuật. **Refinement là đối tượng có thể được cải tiến qua Retrospective**, không phải nghi thức bất biến.

## 14. Những ngộ nhận và phản mẫu thường gặp

### Ngộ nhận 1: “Mỗi Sprint bắt buộc phải có một buổi Backlog Refinement cố định”

Scrum Guide 2020 không quy định refinement là sự kiện hoặc timebox chính thức.

**Cách làm tốt hơn:** Thỏa thuận nhịp cộng tác phù hợp, kết hợp trao đổi trực tiếp, làm rõ không đồng bộ và phản hồi từ công việc thực tế.

### Ngộ nhận 2: “Refinement là lúc cả đội chấm story point”

Kích thước chỉ là một phần thông tin. Một item có điểm ước lượng nhưng thiếu giá trị, AC, phụ thuộc hoặc rủi ro vẫn chưa đủ minh bạch.

**Cách làm tốt hơn:** Bắt đầu từ vấn đề và hành vi cần kiểm chứng; chỉ đánh giá kích thước khi có cơ sở.

### Ngộ nhận 3: “Càng nhiều PBI Ready càng tốt”

Một kho PBI được mô tả chi tiết cho nhiều quý có thể nhanh chóng lỗi thời khi nhu cầu đổi; công sức làm rõ bị lãng phí.

**Cách làm tốt hơn:** Đầu tư mức chi tiết theo khoảng cách tới thời điểm lựa chọn, giá trị và rủi ro.

### Ngộ nhận 4: “Chỉ Product Owner cần làm refinement”

Product Owner chịu trách nhiệm quản lý backlog, nhưng Developers cần tham gia để đánh giá kích thước, phụ thuộc và khả năng hoàn tất; những vai trò khác có thể cung cấp chuyên môn.

**Cách làm tốt hơn:** Tạo hiểu biết chung với người phù hợp thay vì chỉ truyền ticket một chiều.

### Ngộ nhận 5: “Developers phải ước lượng dù chưa hiểu”

Một con số bị ép có thể trông như dự báo nhưng không có cơ sở.

**Cách làm tốt hơn:** Phân nhỏ, xác định bất định hoặc thử spike phù hợp trước khi đánh giá kích thước.

### Ngộ nhận 6: “Hạng mục đã vào Sprint thì không được làm rõ nữa”

Thông tin mới vẫn xuất hiện khi phát triển. Scrum cho phép phạm vi được làm rõ hoặc thương lượng lại với Product Owner khi học thêm, nhưng phải giữ Sprint Goal và chất lượng.

**Cách làm tốt hơn:** Minh bạch tác động của thay đổi và điều chỉnh kế hoạch trong phạm vi trách nhiệm.

### Ngộ nhận 7: “Có Definition of Ready là làm Scrum chuẩn”

DoR có thể là thỏa thuận nội bộ nhưng không phải commitment chính thức trong Scrum Guide.

**Cách làm tốt hơn:** Dùng checklist như câu hỏi hỗ trợ, không như cổng giấy tờ khiến đội ngừng trao đổi.

### Ngộ nhận 8: “Tách UI, API và database thành ba story là đã chia đủ nhỏ”

Các phần kỹ thuật có thể hoàn tất riêng nhưng chưa tạo ra chức năng người dùng có thể kiểm chứng.

**Cách làm tốt hơn:** Chia lát cắt dọc theo hành vi, rồi để Developers tổ chức các task kỹ thuật bên trong.

### Ngộ nhận 9: “Có AC thì chắc chắn sản phẩm tạo giá trị”

AC giúp xác nhận hành vi mong đợi của đầu ra; outcome cần được kiểm tra bằng phản hồi của người dùng.

**Cách làm tốt hơn:** Liên kết PBI với mục tiêu người dùng và nhận phản hồi sau khi Increment tiếp cận đối tượng phù hợp.

### Ngộ nhận 10: “Để story nhỏ, có thể chuyển toàn bộ kiểm thử và bảo mật sang Sprint sau”

Việc này tạo tiến độ ảo và rủi ro không chấp nhận được.

**Cách làm tốt hơn:** Mỗi Increment phải đáp ứng DoD và kiểm soát bắt buộc cho phạm vi đã chọn; chỉ hoãn các biến thể thật sự không cần thiết.

### Ngộ nhận 11: “Refinement hiệu quả nghĩa là Sprint Planning không có câu hỏi nào”

Sprint Planning vẫn phải làm rõ Sprint Goal, lựa chọn và kế hoạch; bất định không biến mất hoàn toàn.

**Cách làm tốt hơn:** Đánh giá refinement qua khả năng lập kế hoạch và thực hiện có căn cứ, không qua sự im lặng trong buổi họp.

### Ngộ nhận 12: “Backlog chỉ cần cập nhật sau Sprint Review”

Thông tin mới có thể xuất hiện từ người dùng, sự cố hoặc phát triển trong bất kỳ ngày nào.

**Cách làm tốt hơn:** Cập nhật backlog theo quyền hạn và mục tiêu ngay khi cần, không đợi một sự kiện cụ thể.

### Ngộ nhận 13: “Scrum Master là người duyệt item Ready”

Scrum Master chịu trách nhiệm giúp Scrum Team hiệu quả, không phải thay Product Owner quyết định giá trị hoặc thay Developers đánh giá kích thước.

**Cách làm tốt hơn:** Giúp các accountability phối hợp và minh bạch trở ngại.

### Ngộ nhận 14: “Các hạng mục ưu tiên cao đều phải làm trước, dù không rõ”

Một item cấp bách có thể cần một hành động khám phá hoặc giải quyết phụ thuộc trước khi được chọn triển khai đầy đủ.

**Cách làm tốt hơn:** Ưu tiên giảm rủi ro và thu bằng chứng sớm; không cam kết một phạm vi chưa thể đánh giá.

## 15. Một quy trình thực hành refinement liên tục

Nhóm có thể thử chu trình sau với các hạng mục đang tiến gần thời điểm được lựa chọn:

~~~mermaid
flowchart TD
    A["Nhận tín hiệu: nhu cầu, phản hồi, rủi ro"] --> B["Làm rõ người dùng và giá trị"]
    B --> C["Thảo luận hành vi, ngoại lệ, phụ thuộc"]
    C --> D{"Item đủ nhỏ và rõ?"}
    D -->|Chưa| E["Chia lát cắt / thử giảm bất định"]
    E --> C
    D -->|Có| F["Developers đánh giá kích thước"]
    F --> G["Product Owner xem thứ tự theo giá trị"]
    G --> H["Ứng viên cho Sprint Planning"]
    H --> I["Xây Increment đạt DoD / kiểm chứng"]
    I --> J["Phản hồi và điều học được"]
    J -. "Cập nhật backlog" .-> B
~~~

### Bước 1 — Chọn đúng item để làm rõ

Nhìn Product Goal, thứ tự backlog, mức cấp bách và rủi ro. Ưu tiên item có khả năng được chọn sớm hoặc chứa giả định lớn. Không cần dành giờ làm rõ cho các ý tưởng xa chỉ vì có mặt trong công cụ quản lý.

### Bước 2 — Mô tả vấn đề và đối tượng

Viết một hoặc hai câu về ai cần làm gì và vì sao. Nếu vấn đề chưa được kiểm chứng, ghi nó là **giả thuyết**, không giả định nó đã là sự thật.

### Bước 3 — Tạo ví dụ nghiệp vụ

Thảo luận một đường thành công và các trường hợp lỗi/biên có ý nghĩa. Viết AC khi chúng giúp nhóm xác định đúng/sai; chọn độ chi tiết theo rủi ro.

### Bước 4 — Chia nhỏ và xem phụ thuộc

Tìm lát cắt dọc có thể đạt DoD trong Sprint. Nếu còn bất định kỹ thuật lớn, chọn thử nghiệm có giới hạn để giảm rủi ro; không ngụy trang prototype thành sản phẩm hoàn tất.

### Bước 5 — Đánh giá kích thước và thứ tự

Developers đánh giá kích thước. Product Owner cân nhắc thứ tự theo giá trị, Product Goal, nghĩa vụ và các điều kiện mới. Không biến kích thước nhỏ thành lý do tự động ưu tiên.

### Bước 6 — Ghi thông tin và quyết định tiếp theo

Điều gì đã rõ? Điều gì còn mở? Ai có thể trả lời, vào thời điểm nào? Item có thể được cân nhắc chọn, cần chia thêm, làm spike, trì hoãn hay loại bỏ?

### Bước 7 — Cập nhật sau thực nghiệm

Khi Increment được kiểm tra hoặc người dùng phản hồi, điều chỉnh Product Backlog và cách refinement. Điều mới học có thể quan trọng hơn bản mô tả đã viết từ tuần trước.

### 15.1. Mẫu thông tin tối thiểu cho một PBI gần được lựa chọn

~~~text
PBI / ID:

NGUOI DUNG VA VAN DE:
  [Ai can lam gi? Vi sao? Co bang chung nao?]

LIEN HE PRODUCT GOAL:
  [Gia tri du kien hoac rui ro can giam]

PHAM VI LAT CAT:
  Bao gom:
  Khong bao gom:

VI DU / ACCEPTANCE CRITERIA:
  AC-01:
  AC-02:
  AC-03:

CHAT LUONG / RANG BUOC:
  [DoD ap dung, bao mat, du lieu, accessibility, van hanh...]

PHU THUOC VA BAT DINH:
  [API, moi truong, quyet dinh nghiep vu, nguoi can tham van]

KICH THUOC:
  [Danh gia cua Developers; dieu kien va gia dinh]

BANG CHUNG KIEM CHUNG:
  [Test/quan sat/moi truong phu hop]

QUYET DINH:
  [Co the can nhac Sprint / can chia nho / can nghien cuu / de sau]
  Nguoi phu trach lam ro:
  Moc xem lai:
~~~

Đây là mẫu **tùy chọn** để hỗ trợ trao đổi, không phải biểu mẫu chính thức của Scrum. Một số thông tin có thể nằm trong công cụ quản lý backlog, mô tả AC, đường dẫn kiểm thử hoặc tài liệu kỹ thuật liên quan. Không tạo nhiều bản sao nếu việc đó khiến thông tin dễ sai lệch.

## 16. Bài tập vận dụng

### Bài tập A — Phân biệt sự kiện và hoạt động

Một nhóm tuyên bố: “Scrum có năm cuộc họp bắt buộc trong Sprint, gồm Planning, Daily, Review, Retro và Backlog Refinement, mỗi lần refinement tối đa 2 giờ”.

**Yêu cầu:** Hãy chỉ ra những điểm chưa chính xác theo Scrum Guide 2020 và đề xuất cách tổ chức refinement tốt hơn.

<details>
<summary>Gợi ý đáp án</summary>

Scrum có Sprint là sự kiện bao chứa và bốn sự kiện trong Sprint: Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective. Refinement là hoạt động liên tục, không phải một sự kiện có timebox chính thức. Đội có thể tổ chức phiên 2 giờ nếu thấy phù hợp, nhưng không được mô tả đó là quy tắc Scrum bắt buộc. Có thể trao đổi ít item có khả năng chọn gần, làm rõ không đồng bộ và cập nhật ngay khi có phát hiện.

</details>

### Bài tập B — Hạng mục lớn nhưng đang ưu tiên cao

Backlog có item “Xây hệ thống thanh toán gồm thẻ, ví điện tử, mã giảm giá, trả góp, hoàn tiền và xuất hóa đơn”. Product Owner đánh giá rất quan trọng và yêu cầu Developers đưa toàn bộ vào Sprint tới.

**Yêu cầu:** Viết năm câu hỏi refinement, hai lát cắt có thể kiểm chứng, một thử nghiệm giảm rủi ro và một nguyên tắc chất lượng không được đánh đổi.

<details>
<summary>Gợi ý đáp án</summary>

Hỏi ai dùng, phương thức nào thực sự bắt buộc cho Product Goal, trạng thái giao dịch được xác nhận từ nguồn nào, cách xử lý callback lặp, nghĩa vụ về tiền và dữ liệu, phụ thuộc sandbox/phê duyệt. Hai lát cắt có thể là một giao dịch bằng phương thức được hỗ trợ có xác nhận đáng tin và hiển thị trạng thái đang chờ/thất bại. Thử nghiệm rủi ro: kiểm chứng API sandbox theo trường hợp thành công/lặp/hết hạn với giới hạn rõ. Không được bỏ xác thực giao dịch, phân quyền hay kiểm soát bảo mật để lấy story nhỏ; item chỉ Done khi đáp ứng DoD áp dụng.

</details>

### Bài tập C — Viết acceptance criteria rõ ràng

PBI: “Học viên muốn nhận thông báo khi đăng ký khóa học xong”. AC hiện tại chỉ là “Thông báo nhanh và thân thiện”.

**Yêu cầu:** Viết ít nhất ba AC có thể quan sát, trong đó có trạng thái thành công, chờ xử lý và lỗi; nêu bằng chứng kiểm chứng cần thu.

<details>
<summary>Gợi ý đáp án</summary>

Khi ghi danh đã được xác nhận hợp lệ, thông báo phản ánh đúng khóa và trạng thái; khi giao dịch đang chờ, không báo thành công hoặc cấp quyền sớm; khi dịch vụ gửi thông báo lỗi, không xác nhận đã gửi nếu không có bằng chứng đáng tin; trạng thái và thông báo không để lộ thông tin tài khoản khác. Kiểm tra bằng test UI–API–dữ liệu với dữ liệu thử, kết quả build/môi trường xác định và các trường hợp lỗi quan trọng. Cần định nghĩa thế nào là “nhanh” theo điều kiện và ngưỡng phù hợp nếu có yêu cầu hiệu năng.

</details>

### Bài tập D — Product Owner, Developers và Scrum Master

Trong refinement, người quản lý tuyên bố: “Product Owner phải tự ước lượng toàn bộ user story, Scrum Master xác nhận đã Ready, Developers chỉ cần nhận task”.

**Yêu cầu:** Nêu điểm sai lệch so với accountability của Scrum và cách tổ chức lại trao đổi.

<details>
<summary>Gợi ý đáp án</summary>

Product Owner chịu trách nhiệm tối đa hóa giá trị, thứ tự và minh bạch của Product Backlog, nhưng Developers chịu trách nhiệm xác định kích thước PBI và kế hoạch thực hiện. Scrum Master giúp Scrum Team hiệu quả, không phải người duyệt một Definition of Ready bắt buộc. Nên đưa Developers vào làm rõ phạm vi, phụ thuộc và rủi ro; Product Owner cung cấp giá trị và quy tắc; Scrum Master hỗ trợ cách cộng tác và tháo trở ngại.

</details>

### Bài tập E — Đổi yêu cầu giữa Sprint

Sprint Goal hiện tại: “Người học có thể tự yêu cầu lại liên kết xác minh email và kích hoạt tài khoản đúng quy tắc”. Giữa Sprint, stakeholder muốn bổ sung dashboard quản trị; đồng thời Developers phát hiện liên kết cũ có thể bị dùng lại.

**Yêu cầu:** Nhóm nên xử lý hai thông tin này thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Lỗi liên kết cũ ảnh hưởng tính đúng đắn và bảo mật của Sprint Goal, cần được làm rõ, sửa và kiểm chứng theo DoD. Developers điều chỉnh kế hoạch và trao đổi Product Owner khi ảnh hưởng phạm vi. Dashboard mới cần Product Owner cân nhắc thứ tự trong Product Backlog; không tự động chen vào Sprint làm nguy hiểm Sprint Goal. Scrum cho phép phạm vi được làm rõ hoặc thương lượng lại khi học thêm, nhưng không giảm chất lượng.

</details>

### Bài tập F — “Done” nhưng chưa tạo Increment

Nhóm chia tính năng lưu yêu thích thành ba PBI: giao diện trái tim, API lưu, bảng dữ liệu. Cả ba được báo Done sau một Sprint, nhưng chưa tích hợp. Sprint Review chỉ trình diễn giao diện với dữ liệu giả.

**Yêu cầu:** Tại sao đây là dấu hiệu refinement và Done chưa hiệu quả? Hãy đề xuất một lát cắt thay thế và bằng chứng cần có.

<details>
<summary>Gợi ý đáp án</summary>

Ba hạng mục thiên về phần kỹ thuật riêng lẻ; nếu chưa tích hợp và chưa đạt DoD, không thể gọi là Increment hoàn tất chỉ vì các task kỹ thuật đã được chuyển trạng thái. Một lát cắt phù hợp là “học viên A lưu khóa X và vẫn xem lại được sau khi đăng nhập lại, tài khoản B không thể xem/sửa mục lưu của A”. Cần kiểm chứng UI–API–lưu trữ, đăng nhập lại, phân quyền và lỗi dịch vụ trên phiên bản/môi trường phù hợp.

</details>

### Bài tập G — Có nên refinement toàn bộ roadmap?

Một Product Owner yêu cầu đội viết AC chi tiết và ước lượng cho 120 ý tưởng của sáu tháng tới trước khi bắt đầu Sprint. Trong khi đó, một phần lớn ý tưởng vẫn chưa được kiểm tra với người dùng.

**Yêu cầu:** Hãy đề xuất nguyên tắc phân bổ công sức refinement và cách xác nhận nhu cầu.

<details>
<summary>Gợi ý đáp án</summary>

Giữ ý tưởng xa ở mức vấn đề, giá trị và giả thuyết; làm rõ sâu những hạng mục có khả năng được chọn gần hoặc rủi ro cần kiểm tra sớm. Dùng quan sát người dùng, phỏng vấn, prototype hoặc thử nghiệm giới hạn để giảm bất định về nhu cầu. Chỉ đánh giá kích thước khi Developers có đủ thông tin; cập nhật Product Backlog khi Product Goal hoặc phản hồi thay đổi. Đặc tả chi tiết toàn bộ roadmap từ đầu dễ lãng phí và tạo cảm giác chắc chắn giả.

</details>

### Bài tập H — Đo hiệu quả refinement

Nhóm tăng thời gian họp refinement từ 1 giờ lên 4 giờ mỗi tuần. Sau hai Sprint, số ticket được tạo nhiều hơn nhưng nhiều item vẫn bị chặn vì dữ liệu thử không có sẵn.

**Yêu cầu:** Có thể kết luận refinement đã cải thiện không? Chọn hai chỉ số và một thử nghiệm cần làm.

<details>
<summary>Gợi ý đáp án</summary>

Chưa thể kết luận từ số giờ họp và ticket. Có thể theo dõi thời gian item bị chặn ở bước kiểm chứng, work item age, cycle time của item tương đồng hoặc số Increment đạt DoD. Thử đưa việc chuẩn bị dữ liệu/môi trường thử phù hợp vào làm rõ sớm, xác định người sở hữu phụ thuộc rồi kiểm tra trong vài Sprint. Nếu trở ngại nằm ở môi trường do tổ chức quản lý, cần hỗ trợ từ cấp có quyền thay đổi thay vì chỉ kéo dài họp.

</details>

## 17. Checklist tự đánh giá cách làm rõ Product Backlog

Hãy tìm ví dụ thực tế cho từng câu hỏi:

1. Product Goal hiện tại có giúp Product Owner giải thích vì sao các PBI đứng cao không?
2. Người dùng và nhu cầu của các PBI gần được chọn đã đủ rõ chưa?
3. Các bên có phân biệt vấn đề với giải pháp được đề xuất không?
4. Những PBI gần được chọn có phạm vi, ví dụ nghiệp vụ và điều kiện chất lượng đáng tin không?
5. Các PBI lớn đã được chia theo hành vi hoặc lát cắt dọc thay vì chỉ theo tầng kỹ thuật chưa?
6. Developers có thể đánh giá kích thước từ thông tin thực, hay đang bị ép đoán?
7. Product Owner có quyền quyết định thứ tự theo giá trị và phản hồi không?
8. Scrum Master có hỗ trợ cách trao đổi và giải quyết trở ngại mà không biến thành người duyệt Ready không?
9. Những phụ thuộc về dữ liệu, API, môi trường, nhà cung cấp hoặc phê duyệt đã được nhìn thấy đủ sớm chưa?
10. Điều kiện bảo mật, dữ liệu, accessibility và vận hành bắt buộc có được làm rõ không?
11. Mỗi PBI có cách kiểm chứng hành vi và có thể đạt Definition of Done trong Sprint không?
12. Những item xa có bị đặc tả quá mức dù giá trị chưa chắc không?
13. Có cơ chế làm rõ khi phát hiện mới xuất hiện, ngoài buổi họp theo lịch không?
14. Sprint Planning có thể tập trung vào Sprint Goal và lựa chọn thay vì dành phần lớn thời gian giải thích lại backlog không?
15. Những item được chọn có thể hoàn tất thành Increment tích hợp, hay liên tục chuyển qua Sprint khác?
16. Sprint Review có tạo thông tin mới để điều chỉnh Product Backlog không?
17. Retrospective có dẫn đến một thay đổi cụ thể trong cách refinement và có xem lại tác dụng không?
18. Các phép đo dùng đánh giá khả năng giao giá trị, hay chỉ đếm giờ họp và ticket?
19. Có phân biệt rõ DoR (nếu dùng), AC, DoD và outcome người dùng không?
20. Khi còn điều chưa rõ, có người cần trả lời, bước giảm bất định và mốc xem lại cụ thể không?

Nếu chưa thể trả lời tốt nhiều câu, hãy chọn **một loại PBI thường gây chậm** — chẳng hạn thanh toán, quyền truy cập hoặc tích hợp nhà cung cấp — rồi thử cải thiện cách làm rõ của loại đó trước. Không cần biến cả Product Backlog thành dự án chuẩn hóa tài liệu.

## 18. Ghi nhớ

- **Product Backlog refinement là hoạt động liên tục, không phải sự kiện Scrum chính thức.** Nhóm tự chọn nhịp trao đổi; Scrum Guide 2020 không quy định timebox hoặc tỉ lệ giờ bắt buộc.
- **Mục đích là chia nhỏ và định nghĩa rõ hơn Product Backlog Items**, thường bổ sung mô tả, thứ tự và kích thước để tăng sự minh bạch. Những item gần được chọn cần đủ rõ để có thể hoàn tất trong một Sprint.
- **Product Owner chịu trách nhiệm quản lý Product Backlog hiệu quả và thứ tự theo giá trị; Developers chịu trách nhiệm xác định kích thước PBI; Scrum Master giúp đội nâng hiệu quả.** Cộng tác có thể cần thêm người dùng và chuyên gia liên quan.
- **Chia lát cắt dọc theo hành vi có ý nghĩa**, không chỉ tách thành frontend/backend/database rồi báo nhiều ticket Done. Một Increment phải đạt Definition of Done.
- **AC giúp kiểm chứng hành vi riêng; DoD xác định chuẩn chất lượng chung; outcome cho biết giá trị sử dụng thực tế.** Không thay thế các khái niệm bằng nhau.
- **Definition of Ready không phải commitment chính thức của Scrum.** Nếu có checklist, hãy dùng để làm rõ, không biến thành cổng phê duyệt quan liêu.
- **Refinement kết nối các nhịp kiểm tra của Scrum:** trước Sprint Planning, trong lúc phát triển, sau Sprint Review và qua các cải tiến từ Retrospective. Bằng chứng mới có thể thay đổi backlog bất cứ khi nào.
- **Đánh giá refinement bằng tác dụng:** ít chờ và hiểu sai hơn, nhiều Increment đúng chất lượng, khả năng lựa chọn tốt hơn và phản hồi người dùng sớm hơn.

Khi nhìn một PBI đứng cao trong Product Backlog, đừng chỉ hỏi: **“Item này bao nhiêu story point?”** Hãy hỏi: **“Nó giúp ai đạt điều gì, phần nhỏ nhất có thể hoàn tất đúng chuẩn là gì, chúng ta còn chưa biết điều gì và bằng chứng nào sẽ làm lựa chọn tiếp theo tốt hơn?”** Việc liên tục trả lời bốn câu hỏi đó giúp Scrum Team chuẩn bị công việc đủ rõ mà vẫn giữ khả năng học và thích ứng.

## Tài liệu tham khảo định hướng

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): định nghĩa Product Backlog refinement, trách nhiệm Product Owner và Developers, các sự kiện Scrum, Sprint Goal và Definition of Done.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/): hợp tác với khách hàng, phần mềm hoạt động được và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm thường xuyên, hợp tác hằng ngày và thích ứng với thay đổi.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): biểu diễn ví dụ hành vi với Given–When–Then.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): giới hạn WIP, work item age, cycle time và throughput khi nhìn dòng công việc.
- [Agile Alliance — Agile Glossary](https://agilealliance.org/agile101/agile-glossary/): khái niệm user story, backlog và các kỹ thuật thực hành Agile.
