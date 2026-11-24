# Bàn giao Increment khi sẵn sàng mà không phải chờ Sprint Review

Một Scrum Team phát triển nền tảng học trực tuyến đã hoàn tất chức năng **người học trả lời một câu trắc nghiệm và nhận phản hồi đúng/sai** ngay trong ngày thứ tư của Sprint hai tuần. Phần chức năng đã được tích hợp với sản phẩm hiện có, kiểm thử các trường hợp quan trọng và đáp ứng **Definition of Done (DoD)**.

Nhưng cả nhóm lại nói: “Phải đợi Sprint Review vào cuối tuần sau để được duyệt, rồi mới triển khai cho người học”. Như vậy, một phần mềm có thể sử dụng phải nằm chờ thêm nhiều ngày chỉ vì nhóm đang coi một sự kiện kiểm tra và thích ứng như một **cổng cấp phép phát hành**.

Ngược lại, cũng có nhóm tuyên bố “Scrum cho phát hành bất cứ lúc nào” rồi đưa một phần code chưa kiểm tra quyền truy cập ra production. Cách hiểu đó cũng sai: **khả năng phát hành sớm không đồng nghĩa được bỏ qua chất lượng và kiểm soát cần thiết**.

Bài học thuộc chương **Tạo tác Scrum** của module **AGILE_DEVELOPMENT**. Trong phát triển phần mềm Agile, phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục chỉ đem lại giá trị khi nhóm hiểu **thế nào là một Increment đã hoàn tất**, **khi nào có thể bàn giao/phát hành**, **ai cần tham gia quyết định**, và **Sprint Review còn làm gì khi đã phát hành trước đó**.

Sau bài này, bạn có thể:

1. Giải thích mối quan hệ giữa **Increment**, **Definition of Done**, **Sprint Review**, **deployment** và **release**.
2. Nhận diện các điều kiện cho phép một Increment được bàn giao hoặc phát hành **trước khi Sprint kết thúc**.
3. Phân biệt hoàn tất về chất lượng với quyền quyết định phân phối sản phẩm tới người dùng.
4. Thiết kế các lát user story nhỏ, tích hợp thường xuyên và theo dõi phản hồi sau phát hành.
5. Phối hợp Product Owner, Developers, Scrum Master và các bộ phận vận hành, bảo mật, pháp lý khi cần.
6. Không biến Sprint Review thành cuộc duyệt bàn giao, nhưng vẫn sử dụng sự kiện này để kiểm tra kết quả và điều chỉnh Product Backlog.
7. Đánh giá các tình huống đặc biệt: thiếu DoD, đã Done nhưng chưa được phép release, feature flag, phát hành theo nhóm và rủi ro sự cố.

## 1. Cốt lõi của vấn đề: Sprint Review không phải cổng phát hành

Theo **Scrum Guide 2020**, **Increment** là bước tiến cụ thể hướng tới Product Goal. Mỗi Increment bổ sung vào các Increment trước đó và phải được kiểm tra để bảo đảm chúng hoạt động cùng nhau. Increment phải **có thể sử dụng** (*usable*).

Những điểm cần ghi nhớ:

- **Có thể tạo nhiều Increment trong cùng một Sprint.** Không có yêu cầu chỉ được tạo đúng một Increment ở cuối Sprint.
- Một Increment **có thể được bàn giao cho các bên liên quan trước khi Sprint kết thúc**.
- **Sprint Review không phải cổng bắt buộc để phát hành giá trị**; không cần đợi sự kiện đó mới được cung cấp một Increment phù hợp cho người dùng.
- Một Product Backlog Item chưa đạt **Definition of Done** không thể được coi là một phần của Increment; nếu cần, nó quay lại Product Backlog để được xem xét tiếp.
- Việc phát hành một Increment trước Sprint Review **không làm Sprint Review trở nên thừa**. Sự kiện này vẫn phục vụ kiểm tra kết quả Sprint và cùng các bên liên quan xác định điều chỉnh tiếp theo.

Tuy nhiên, từ “có thể phát hành trước Sprint Review” không suy ra “bắt buộc phát hành mỗi ngày” hoặc “không cần điều kiện đưa lên môi trường thật”. Ngày phát hành, nhóm người dùng được mở, thủ tục bảo mật, yêu cầu pháp lý và năng lực vận hành còn tùy sản phẩm và tổ chức.

**Phát biểu đúng:** Khi một Increment đã đạt DoD và các điều kiện phát hành liên quan được đáp ứng, tổ chức **có thể** đưa nó tới người dùng trước Sprint Review; Sprint Review **không phải một bước phê duyệt mặc định**.

## 2. Ba tạo tác Scrum và cam kết liên quan

Muốn hiểu Increment, cần nhìn nó trong toàn bộ hệ thống minh bạch của Scrum.

| Tạo tác Scrum | Cam kết gắn với tạo tác | Câu hỏi được hỗ trợ |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Sản phẩm cần tiến tới kết quả dài hạn nào, và công việc nào đáng ưu tiên? |
| **Sprint Backlog** | **Sprint Goal** | Trong Sprint hiện tại, nhóm cùng hướng tới mục tiêu gì, và kế hoạch thực hiện ra sao? |
| **Increment** | **Definition of Done** | Phần sản phẩm mới đã hoàn tất theo tiêu chuẩn chất lượng và có thể sử dụng chưa? |

Ba cặp này không chỉ là tên tài liệu:

- **Product Goal** giúp Product Owner và Scrum Team chọn những thay đổi đóng góp vào giá trị dài hạn.
- **Sprint Goal** tạo định hướng ngắn hạn, giúp Developers điều chỉnh Sprint Backlog khi thông tin mới xuất hiện.
- **Definition of Done** bảo đảm kết quả được gọi là Increment **không chỉ là code đã viết**, mà là sản phẩm đạt tiêu chuẩn hoàn tất đã thống nhất.

Sprint Review là **sự kiện** trong Scrum, không phải tạo tác hay cam kết thứ tư. Nó giúp nhóm kiểm tra kết quả và thích ứng kế hoạch, không thay cho Definition of Done.

### Mối quan hệ trong một vòng phát triển

~~~mermaid
flowchart TD
    A["Product Goal"] --> B["Product Backlog có thứ tự"]
    B --> C["Sprint Goal và Sprint Backlog"]
    C --> D["Developers tạo thay đổi nhỏ, tích hợp thường xuyên"]
    D --> E{"Đã đáp ứng Definition of Done?"}
    E -->|"Chưa"| F["Chưa là Increment; hoàn thiện / đưa lại Product Backlog"]
    F --> B
    E -->|"Có"| G["Increment có thể sử dụng"]
    G --> H{"Đủ điều kiện release theo bối cảnh?"}
    H -->|"Có"| I["Có thể phát hành ngay, không chờ Sprint Review"]
    H -->|"Chưa"| J["Giữ Increment Done; giải quyết điều kiện còn thiếu"]
    I --> K["Thu phản hồi sử dụng và vận hành"]
    J --> L["Sprint Review: kiểm tra kết quả, học hỏi, điều chỉnh"]
    K --> L
    L --> B
~~~

Sơ đồ là mô hình quyết định, **không phải quy trình cứng**. Việc xử lý một mục chưa Done có thể tiếp tục trong Sprint khi còn thời gian và phù hợp kế hoạch; mũi tên quay về backlog minh họa tình huống mục vẫn chưa đạt DoD.

## 3. Increment là gì và không phải là gì?

**Increment** trong Scrum là một bước tiến **được tích hợp, kiểm tra để hoạt động với phần sản phẩm trước đó, đáp ứng DoD và có thể sử dụng**. Một Increment không nhất thiết có kích thước lớn hay một tính năng hoàn chỉnh theo kế hoạch marketing.

Ví dụ với sản phẩm học trực tuyến:

- Một Increment bổ sung khả năng **nộp một câu trắc nghiệm và nhận phản hồi** cho nhóm người học đã đăng nhập.
- Increment tiếp theo bổ sung khả năng **lưu kết quả trả lời**.
- Increment khác bổ sung **báo cáo kết quả của lớp** cho giảng viên đúng quyền truy cập.

Các Increment có thể được tạo trong cùng Sprint, miễn là mỗi phần được coi là Done thực sự đáp ứng DoD và tương thích với phần sản phẩm đang có.

### 3.1. Những thứ chưa đủ để gọi là Increment

| Hiện vật/trạng thái | Có thể hữu ích vì sao? | Vì sao chưa tự động là Increment? |
| --- | --- | --- |
| Một bản thiết kế giao diện có thể bấm | Thử khả năng hiểu và điều hướng. | Có thể chưa có hành vi sản phẩm và tích hợp thật. |
| Một endpoint chạy được trên máy lập trình viên | Kiểm tra ý tưởng triển khai. | Chưa chắc có quyền truy cập đúng, kiểm thử hay tích hợp với sản phẩm. |
| Một pull request đã được merge | Tăng tiến độ tích hợp mã. | Merge không tự chứng minh tất cả điều kiện DoD đã đạt. |
| Một tính năng chạy được nhưng lỗi nghiêm trọng | Cho thấy một phần khả năng hiện thực. | Không có tính khả dụng/chất lượng theo tiêu chuẩn đã thỏa thuận. |
| Một danh sách task UI/API/database đều đóng | Các phần kỹ thuật đã được thực hiện. | Luồng người dùng cuối cùng có thể chưa hoạt động đầu cuối. |
| Một bản build đã deploy | Phần mềm đã được triển khai trên một môi trường. | Chưa chắc đáp ứng DoD hoặc đã mở cho người dùng. |

Một thay đổi nhỏ như sửa lỗi ảnh hưởng người dùng cũng có thể đóng góp vào Increment. Điều cốt lõi là **bước tiến sản phẩm đạt chuẩn**, không phải số lượng màn hình hay số story points.

### 3.2. Increment phải phối hợp với phần trước

Giả sử Increment mới thêm cơ chế xác thực cho trang làm bài trắc nghiệm. Nếu nó làm hỏng luồng đăng nhập hoặc không tương thích với API đang dùng, nhóm cần giải quyết vấn đề tích hợp và DoD trước khi gọi đó là Increment hoàn tất.

Với nhiều Scrum Teams cùng làm trên **một sản phẩm**, cần có một **Definition of Done chung cho sản phẩm** và các Increment phải làm việc cùng nhau. Không thể nhóm A tuyên bố Done theo chuẩn thấp hơn trong khi nhóm B cần tích hợp một phần chưa đủ chất lượng.

### 3.3. Đạt DoD không có nghĩa đã chứng minh giá trị thị trường

Tính năng trả lời trắc nghiệm có thể đạt kiểm thử, an toàn và tích hợp tốt, nhưng học viên có thể không dùng hoặc không thấy hữu ích. DoD trả lời câu hỏi **phần mềm có hoàn tất đúng chuẩn không**; phản hồi người dùng giúp trả lời **nó có tạo giá trị mong muốn không**.

Vì vậy, khả năng phát hành sớm có lợi: nhóm có cơ hội học về giá trị **trước khi đầu tư thêm** vào các phần nâng cao.

## 4. Phân biệt Done, bàn giao, triển khai và phát hành

Từ “bàn giao” trong tổ chức có thể mang nhiều nghĩa: chuyển công việc sang bộ phận kiểm thử, bàn giao cho vận hành, cung cấp bản dùng thử, nghiệm thu hợp đồng hoặc mở tính năng cho khách hàng. Khi bàn về Scrum, cần **đặt tên rõ hành động thực tế**.

| Trạng thái/hành động | Câu hỏi thực chất | Có bắt buộc chờ Sprint Review không? |
| --- | --- | --- |
| **Code complete** | Mã chính đã viết xong? | Không, nhưng đây chưa phải tiêu chuẩn Increment. |
| **Done theo DoD** | Phần thay đổi đã tích hợp, kiểm tra, đáp ứng chất lượng để có thể sử dụng? | **Không.** Đạt DoD không phụ thuộc Sprint Review. |
| **Bàn giao kết quả đã Done cho bên liên quan** | Người liên quan có thể xem/sử dụng Increment theo điều kiện phù hợp? | **Không.** Có thể trước khi Sprint kết thúc. |
| **Deploy** | Đã đưa mã/phần mềm lên một môi trường chạy? | **Không.** Deploy là hoạt động kỹ thuật/vận hành riêng. |
| **Release** | Đã cho một nhóm người dùng tiếp cận khả năng sản phẩm? | **Không.** Thời điểm do điều kiện và quyết định liên quan quyết định. |
| **Nghiệm thu hợp đồng (nếu có)** | Bên có thẩm quyền đã xác nhận nghĩa vụ theo hợp đồng? | Tùy điều khoản, không mặc nhiên là Sprint Review. |
| **Sprint Review** | Scrum Team và các bên liên quan kiểm tra kết quả Sprint, tiến độ hướng Product Goal và định hướng tiếp theo? | Đây là sự kiện Scrum theo nhịp Sprint, **không phải cổng release**. |

### Ví dụ có feature flag

Một nhóm đưa mã tính năng “Làm lại bài trắc nghiệm” lên production nhưng để **feature flag tắt**. Tình trạng có thể là:

- **Deployed:** Có, nếu mã đã có trên môi trường production.
- **Released tới người học:** Chưa, nếu người học chưa thể sử dụng chức năng.
- **Done:** Chỉ có thể kết luận khi phần công việc đáp ứng DoD của sản phẩm; feature flag tự nó không biến code chưa xong thành Done.
- **Đủ điều kiện release:** Cần đánh giá kiểm thử, quyền truy cập, giám sát, vận hành và các yêu cầu liên quan trước khi bật cho người dùng.

Đừng lấy dấu mốc “đã deploy” để ngầm báo rằng tính năng đã tạo giá trị, hoặc dùng flag để che một phần chưa hoàn tất rồi tuyên bố hoàn thành.

## 5. Definition of Done là nền tảng để giao sớm an toàn

**Definition of Done (DoD)** là mô tả chính thức trạng thái của Increment khi đã đáp ứng các tiêu chí chất lượng cần thiết cho sản phẩm.

Theo Scrum, nếu tổ chức có các chuẩn chất lượng áp dụng cho sản phẩm thì chúng là **mức tối thiểu phải tuân thủ**; nếu không có chuẩn như vậy, Scrum Team phải tạo một DoD phù hợp cho sản phẩm. Developers chịu trách nhiệm tuân thủ DoD khi tạo Increment.

DoD không nhất thiết giống hệt ở mọi tổ chức, nhưng phải đủ rõ để tránh việc “đã xong” trở thành nhận định cảm tính.

### 5.1. Một DoD minh họa

Với chức năng trắc nghiệm trên nền tảng học, DoD có thể gồm những điều kiện như:

- Thay đổi được **tích hợp** với sản phẩm hiện tại và không làm hỏng luồng học quan trọng.
- **Acceptance criteria** của các Product Backlog Items liên quan được kiểm tra.
- Các bài kiểm thử tự động thiết yếu và kiểm thử tích hợp phù hợp đều đạt.
- Quy tắc nghiệp vụ, dữ liệu và **quyền truy cập** đáp ứng chính sách.
- Không còn lỗi nghiêm trọng chưa xử lý vượt ngưỡng cho phép.
- Có khả năng quan sát lỗi hoặc chẩn đoán sự cố theo nhu cầu vận hành.
- Thay đổi cấu hình/cơ sở dữ liệu, hướng dẫn hỗ trợ hoặc tài liệu cần thiết được cập nhật nếu DoD quy định.
- Tiêu chuẩn an toàn, bảo mật và tuân thủ bắt buộc được đáp ứng.

Đây là **ví dụ học tập**, không phải DoD áp dụng nguyên xi cho mọi sản phẩm. Cần phân biệt điều kiện DoD và những việc chỉ cần cho một lần phát hành đặc biệt.

### 5.2. Acceptance criteria khác với DoD

**Acceptance criteria** mô tả các tình huống hành vi cụ thể của một story. Ví dụ, học viên chọn đáp án và nhận phản hồi đúng/sai; nếu hết giờ thì thấy trạng thái hợp lệ.

**DoD** mô tả tiêu chuẩn chất lượng, tích hợp và tính hoàn tất của Increment nói chung.

Một story có thể vượt qua các acceptance criteria nhưng **chưa đạt DoD** vì chưa có kiểm thử tích hợp, phân quyền hay cấu hình cần thiết. Ngược lại, đạt DoD không thay cho kiểm tra liệu mục tiêu kinh doanh có đạt được không.

### 5.3. Không thay DoD bằng chữ ký trong Sprint Review

Giả sử chức năng nộp đáp án trả về đúng kết quả nhưng để lộ đáp án của người học khác. Việc PO, PM hoặc khách hàng nói “đồng ý nghiệm thu” trong cuộc họp không làm rủi ro biến mất. Phần đó **chưa đáp ứng chất lượng và không được coi là Done** nếu điều kiện quyền truy cập cần thiết chưa đạt.

Trường hợp DoD thật sự không đầy đủ, Scrum Team và tổ chức cần cải thiện nó theo chính sách chất lượng. Không nên âm thầm hạ chuẩn riêng cho một story để giữ số liệu Sprint.

## 6. Khi nào một Increment có thể release ngay?

Cần tách hai câu hỏi:

1. **Increment đã Done và có thể sử dụng chưa?** Đây là điều kiện để gọi đúng tạo tác Scrum.
2. **Có phù hợp và được phép mở Increment đó cho nhóm người dùng cụ thể ngay bây giờ không?** Đây là quyết định phát hành trong bối cảnh sản phẩm và tổ chức.

Một Increment đạt DoD là **điều kiện quan trọng**, nhưng không tự bảo đảm mọi hoạt động phát hành đều sẵn sàng. Ví dụ, môi trường production đang có sự cố, cửa sổ bảo trì của bên thanh toán chưa mở hoặc hợp đồng chưa cho phép cung cấp tính năng cho khách hàng nhất định.

### 6.1. Những nhóm điều kiện release cần xem xét

| Nhóm | Câu hỏi nên kiểm tra | Ví dụ |
| --- | --- | --- |
| **Giá trị/phạm vi** | Người dùng nào sẽ nhận khả năng gì, đúng thời điểm này có giá trị không? | Một lớp học thử có thể dùng một bài trắc nghiệm ngắn. |
| **DoD và chất lượng** | Increment đã thực sự Done, tích hợp và hoạt động với hệ thống hiện tại chưa? | Bài kiểm thử nộp đáp án và phân quyền đạt. |
| **Bảo mật và riêng tư** | Có bảo vệ thông tin người học, đáp án, quyền xem kết quả không? | Học viên không được xem kết quả riêng của người khác. |
| **Vận hành** | Có giám sát, hỗ trợ, xử lý lỗi và phương án khôi phục phù hợp? | Theo dõi lỗi nộp bài và cách xử lý nếu dữ liệu lỗi. |
| **Dữ liệu và tương thích** | Thay đổi schema, migration, phiên bản client cũ có an toàn? | Bản mới không làm mất lịch sử bài đã nộp. |
| **Phạm vi triển khai** | Mở cho tất cả hay nhóm thử, có giới hạn tải và hỗ trợ? | Bật cho 20 học viên thuộc lớp thử trước. |
| **Thẩm quyền và nghĩa vụ** | Cần ai quyết định/được thông báo theo quy định tổ chức? | Người phụ trách phát hành phối hợp với PO và vận hành. |
| **Đo lường phản hồi** | Có tín hiệu để biết release hữu ích và có gây lỗi không? | Tỷ lệ nộp thành công, phản hồi học viên, lỗi production. |

Không phải mọi sản phẩm đều cần một buổi họp release riêng. Những điều kiện có thể được tự động hóa trong pipeline và chính sách rõ ràng. Điều cần tránh là **tự tạo Sprint Review thành một cổng phê duyệt mặc định không có trong Scrum**.

### 6.2. DoD và “release readiness” có thể trùng nhưng không đồng nhất

Một số tổ chức định nghĩa DoD bao gồm các điều kiện đủ để release ngay; tổ chức khác có những điều kiện cụ thể theo từng lần phát hành (ví dụ phê duyệt chiến dịch truyền thông hoặc đổi cấu hình ngoài giờ). Cần nói rõ ranh giới để không dùng “release chưa được phép” làm lý do coi một Increment đã Done là chưa Done, hoặc dùng “DoD đã đạt” để bỏ qua nghĩa vụ phát hành riêng.

Ví dụ:

> “Increment đã đạt DoD lúc 14:00 thứ Ba. Chúng ta chưa mở cho khách hàng vì nhà cung cấp thanh toán đang bảo trì; dự kiến đánh giá lại điều kiện release lúc 09:00 thứ Tư.”

Thông điệp này minh bạch hơn “story chưa xong” hoặc “đã release” khi cả hai đều không đúng.

## 7. Ai chịu trách nhiệm và ai quyết định phát hành?

Scrum định nghĩa ba **accountabilities** trong Scrum Team, nhưng **không quy định một chức danh duy nhất phải phê duyệt mọi release**. Quyền phát hành có thể phụ thuộc vào cơ cấu sản phẩm, vận hành, nghĩa vụ pháp lý và chính sách tổ chức.

| Bên tham gia | Đóng góp chính | Điều không nên suy ra |
| --- | --- | --- |
| **Product Owner (PO)** | Tối đa hóa giá trị sản phẩm, quản lý Product Goal và thứ tự Product Backlog; cung cấp bối cảnh giá trị và đối tượng thử khi quyết định release. | Không mặc nhiên tự kiểm soát mọi biện pháp kỹ thuật hoặc thay DoD. |
| **Developers** | Tạo Increment đạt DoD, làm rõ khả năng triển khai, kiểm thử, rủi ro kỹ thuật và cách vận hành phù hợp. | Không bắt buộc giao cho PO quyết định từng chi tiết triển khai kỹ thuật. |
| **Scrum Master** | Hỗ trợ hiệu quả Scrum, gỡ trở ngại và ngăn hiểu sai Sprint Review như cổng phát hành. | Không tự động là release manager hoặc người ký phê duyệt. |
| **Vận hành/SRE, bảo mật, pháp lý, hỗ trợ** | Tham gia những điều kiện thuộc chuyên môn và thẩm quyền được tổ chức quy định. | Không nên tạo các cổng duyệt trùng lặp vô mục đích. |
| **Project Manager/Release Manager nếu có** | Điều phối lịch, nhà cung cấp, truyền thông và các nghĩa vụ phát hành theo quyền tổ chức. | Chức danh không tự trao quyền đánh dấu một Increment chưa đạt DoD thành Done. |
| **Bên liên quan/người dùng** | Cung cấp phản hồi, đánh giá kết quả và ảnh hưởng của release. | Không bắt buộc phải dự Sprint Review để mọi giá trị mới được mở. |

Điều nên ghi rõ trong **working agreement hoặc chính sách release**:

- Ai có quyền bật tính năng cho nhóm người dùng cụ thể?
- Các điều kiện tự động và các trường hợp phải phê duyệt thủ công là gì?
- Khi có rủi ro nghiêm trọng, ai dừng rollout?
- Ai quyết định rollback hoặc tắt feature flag?
- Ai thông báo cho người dùng, hỗ trợ và các bên liên quan?
- Ai theo dõi tín hiệu sau release và đưa thông tin về Product Backlog?

Nếu một tổ chức chưa có câu trả lời, **khoảng trống trách nhiệm cần được giải quyết**, không nên mặc định chuyển tất cả quyền về Sprint Review.

## 8. Ví dụ xuyên suốt: phát hành nhiều Increment trong một Sprint

Giả sử Scrum Team có **Sprint dài hai tuần** và Sprint Goal:

> “Người học mới có thể hoàn tất một bài trắc nghiệm ngắn và nhận phản hồi đáng tin cậy để biết bước ôn tập tiếp theo.”

Nhóm chọn các Product Backlog Items được chia thành những lát đầu cuối, không phải “xây toàn bộ giao diện” rồi “xây toàn bộ API”.

### 8.1. Kế hoạch ứng viên

| Thời điểm minh họa | Increment/lát giá trị | Điều kiện Done | Cách đưa giá trị tới người dùng |
| --- | --- | --- | --- |
| **Ngày 3** | **I1:** Người học có quyền mở một câu hỏi, chọn đáp án và nhận kết quả đúng/sai. | Giao diện, logic, dữ liệu và kiểm thử được tích hợp; quyền truy cập và DoD đạt. | Có thể mở cho nhóm học viên thử ngay khi điều kiện release sẵn sàng. |
| **Ngày 6** | **I2:** Lưu kết quả trả lời để người học thấy lại tiến độ trong phạm vi hỗ trợ. | Tích hợp với I1, kiểm thử dữ liệu và trường hợp lỗi, DoD đạt. | Có thể đưa ra cho cùng nhóm thử hoặc mở rộng dần. |
| **Ngày 8** | **I3:** Người học thấy gợi ý ôn tập cơ bản sau khi nộp bài. | Hành vi, quyền truy cập, kiểm thử và tích hợp đạt DoD. | Có thể mở trước Sprint Review khi phù hợp. |
| **Cuối Sprint** | **Sprint Review:** Scrum Team và các bên liên quan cùng kiểm tra kết quả, phản hồi và hướng tiếp theo. | Đây là hoạt động kiểm tra/thích ứng, không phải điều kiện chứng nhận I1–I3 được Done. | Nhận định giá trị và cập nhật Product Backlog. |

Các ngày trên chỉ minh họa. Trong thực tế, có thể không tạo đủ ba Increment; hoặc một Increment có thể hoàn tất nhưng chưa được phát hành do điều kiện vận hành. **Không nên ép ngày 3/6/8 thành deadline cá nhân chỉ để bảng trông đẹp**.

### 8.2. Vì sao I1 đủ nhỏ nhưng vẫn có giá trị?

I1 cho phép người học **làm một tác vụ trọn vẹn**: mở câu hỏi, chọn đáp án, nộp, nhận phản hồi. Nó không chỉ là UI giả hoặc một endpoint chưa nối với người dùng.

I1 có thể **chưa** hỗ trợ lưu kết quả giữa nhiều phiên, báo cáo chi tiết cho giáo viên hay gợi ý cá nhân hóa. Việc chưa có các tính năng nâng cao **không ngăn** I1 trở thành một Increment nếu phạm vi đã thỏa thuận thực sự dùng được, tích hợp, an toàn và đạt DoD.

Ngược lại, nếu I1 tuyên bố cho người học nộp đáp án nhưng **trả kết quả sai** hoặc để người học xem thông tin thuộc tài khoản khác, không thể gọi nó là Done chỉ vì đó là “bản đầu tiên”.

### 8.3. User story và tiêu chí chấp nhận của I1

> **Là** người học đã được cấp quyền làm bài, **tôi muốn** chọn một đáp án và nhận phản hồi sau khi nộp, **để** biết mình hiểu nội dung bài học tới đâu.

~~~gherkin
Feature: Làm một câu hỏi trắc nghiệm

Scenario: Nộp một đáp án hợp lệ
  Given người học đã đăng nhập và có quyền làm bài "Java cơ bản"
  And câu hỏi hiện có một tập đáp án hợp lệ
  When người học chọn một đáp án và bấm "Nộp"
  Then hệ thống đánh giá lựa chọn theo đáp án đúng đã cấu hình
  And hiển thị phản hồi đúng hoặc sai rõ ràng
  And không để lộ dữ liệu riêng của người học khác

Scenario: Chưa chọn đáp án
  Given người học có quyền làm bài
  And chưa chọn đáp án cho câu hỏi hiện tại
  When người học bấm "Nộp"
  Then hệ thống không ghi nhận một câu trả lời hợp lệ
  And hướng dẫn người học chọn đáp án trước khi nộp

Scenario: Người học không có quyền làm bài
  Given một người dùng không có quyền làm bài "Java cơ bản"
  When người đó gửi yêu cầu nộp đáp án
  Then hệ thống từ chối thao tác theo chính sách
  And không cung cấp thông tin riêng tư từ bài làm của người khác

Scenario: Hệ thống không thể xử lý lần nộp bài
  Given người học có quyền làm bài và đã chọn đáp án
  And dịch vụ xử lý nộp bài gặp lỗi
  When người học bấm "Nộp"
  Then giao diện không hiển thị kết quả thành công sai sự thật
  And cung cấp thông báo hoặc cách thử lại phù hợp
~~~

Tiêu chí chấp nhận mô tả **hành vi**. DoD còn phải bao gồm các tiêu chuẩn chất lượng, kiểm thử tích hợp và điều kiện hoàn tất được áp dụng cho sản phẩm. Với I1, nhóm cần kiểm tra các trường hợp nộp trùng, sai dữ liệu hoặc mất kết nối nếu chúng thuộc phạm vi thiết yếu đã thống nhất.

### 8.4. Phản hồi sớm giúp đổi thứ tự backlog

Sau khi I1 được mở cho lớp thử, nhóm thấy nhiều học viên trả lời xong nhưng không hiểu **vì sao câu trả lời sai**. Đây là phản hồi giá trị. PO có thể ưu tiên giải thích đáp án thay vì một bảng xếp hạng trò chơi hóa đã được đề xuất trước đó.

Nếu đợi đến cuối Sprint mới có người học thật thử I1, nhóm có thể mất nhiều ngày xây I2 và I3 dựa trên giả định chưa được kiểm chứng.

Tuy nhiên, việc có phản hồi sớm **không mặc nhiên cho phép bỏ Sprint Goal giữa chừng**. Scrum Team cần thảo luận tác động tới mục tiêu hiện tại và cách thích ứng Sprint Backlog phù hợp, giữ chất lượng và minh bạch.

## 9. Kiến trúc giao hàng: chia lát dọc và tích hợp liên tục

Phát hành sớm thường khó hơn khi công việc được chia thành các hạng mục ngang theo lớp: “toàn bộ database”, “toàn bộ backend”, “toàn bộ frontend”. Mỗi nhóm chuyên môn có thể hoàn tất phần mình nhưng người dùng chưa thực hiện được tác vụ hoàn chỉnh.

### 9.1. Chia lát theo giá trị có thể kiểm chứng

Ví dụ với bài trắc nghiệm:

| Chia ngang dễ chờ tích hợp | Chia dọc hướng giá trị |
| --- | --- |
| Xây toàn bộ bảng cho mọi loại bài kiểm tra. | Một câu hỏi nhiều lựa chọn có dữ liệu cần thiết và quyền truy cập đúng. |
| Tạo mọi API trắc nghiệm trước. | Một luồng mở câu hỏi – nộp đáp án – nhận phản hồi đầu cuối. |
| Thiết kế toàn bộ giao diện cho nhiều chế độ. | Giao diện đủ dùng cho một luồng thật và được kiểm thử. |
| Đợi cuối Sprint mới ghép. | Tích hợp, kiểm thử và xem xét phát hành từng lát Done. |

**Chia dọc không đòi hỏi mỗi lát phải xây một database mới hoặc một lớp UI mới.** Nó đòi hỏi kết quả của lát có thể sử dụng trọn vẹn trong phạm vi đã chọn.

### 9.2. Continuous Integration (CI)

Tích hợp thường xuyên cùng kiểm thử tự động giúp nhóm phát hiện sớm xung đột giữa các thay đổi. Ví dụ, mỗi thay đổi liên quan câu hỏi trắc nghiệm chạy kiểm thử đơn vị, kiểm thử API và kiểm tra những luồng quan trọng đã có.

Điều đó hỗ trợ tạo nhiều Increment trong Sprint thay vì gom tất cả thay đổi vào một lần tích hợp lớn cuối kỳ.

### 9.3. Continuous Delivery và Continuous Deployment

Cần phân biệt:

- **Continuous Delivery:** phần mềm được duy trì ở trạng thái có thể đưa vào sử dụng khi quyết định phát hành phù hợp; không có nghĩa mọi thay đổi đều tự động mở cho người dùng.
- **Continuous Deployment:** thay đổi vượt qua các bước tự động hóa đã quy định có thể được triển khai tự động lên production; điều này vẫn **không đồng nghĩa** mọi người dùng đã thấy một tính năng đang bị tắt bằng flag.
- **Release theo nhóm:** chọn đối tượng được dùng, có thể qua canary, rollout theo tỷ lệ hoặc feature flag, theo điều kiện kiểm soát.

Đội ngũ có thể áp dụng các thực hành XP như **test-driven development (TDD), refactoring, lập trình cặp và thiết kế đơn giản** để giữ mã dễ thay đổi và khả năng tích hợp ổn định.

### 9.4. Chất lượng là khả năng phát hành nhanh lâu dài

Một nhóm bỏ kiểm thử để phát hành sớm có thể phải dành tuần sau sửa lỗi, rollback hoặc xử lý sự cố. **Tốc độ phản hồi bền vững** đến từ việc giữ chất lượng đủ tốt trong từng lát, không phải chuyển tất cả chi phí kiểm tra sang người dùng production.

## 10. Feature flag, canary và rollout theo giai đoạn

Các kỹ thuật phát hành theo giai đoạn giúp nhóm giảm mức độ ảnh hưởng khi đưa một Increment ra sử dụng, nhưng phải đi cùng kiểm soát phù hợp.

### 10.1. Feature flag

Feature flag cho phép bật/tắt khả năng mà không nhất thiết deploy lại toàn bộ code. Nhóm có thể:

1. Deploy Increment đã Done với flag tắt cho người dùng thông thường.
2. Bật cho tài khoản nội bộ hoặc nhóm thử có quyền.
3. Quan sát lỗi, hiệu năng và hành vi.
4. Mở rộng dần khi điều kiện cho phép.
5. Tắt flag nếu xuất hiện vấn đề và cách này thực sự làm giảm tác động.

**Giới hạn:** Flag không sửa được dữ liệu đã bị ghi sai; tắt giao diện không nhất thiết dừng mọi xử lý nền. Do đó cần đánh giá ảnh hưởng dữ liệu, tác vụ bất đồng bộ, cache và tương thích phiên bản.

### 10.2. Canary release

**Canary** đưa thay đổi tới một phần nhỏ lưu lượng hoặc người dùng trước. Mục tiêu là phát hiện vấn đề với mức ảnh hưởng có kiểm soát.

Ví dụ, nhóm có thể mở I1 cho một lớp học nội bộ, kiểm tra tỷ lệ nộp bài thành công và lỗi truy cập, rồi mới mở cho nhiều lớp. Điều kiện chuyển bước phải có **ngưỡng chất lượng và người chịu trách nhiệm theo dõi**, tránh “mở dần” chỉ vì đã đến ngày.

### 10.3. Blue-green deployment và rollback

Ở hệ thống phù hợp, có thể dùng hai môi trường tương tự để chuyển lưu lượng giữa bản cũ và bản mới. Nhưng việc rollback mã **không bảo đảm dữ liệu luôn quay lại như cũ**, nhất là khi schema hoặc dữ liệu đã thay đổi.

Vì vậy, với các thay đổi có migration, cần cân nhắc tương thích ngược, sao lưu, khả năng khôi phục và kế hoạch xử lý khi rollback không đủ.

### 10.4. Đừng nhầm phát hành giới hạn với thử nghiệm thiếu an toàn

Phát hành cho 1% người dùng có thể giảm **phạm vi ảnh hưởng**, nhưng không biến một lỗ hổng bảo mật nghiêm trọng thành chấp nhận được. Những ràng buộc bắt buộc vẫn cần đáp ứng trước khi mở cho **bất kỳ** người dùng thật nào.

## 11. Quy trình ra quyết định release ngắn gọn

Một nhóm có thể dùng quy trình dưới đây mà không biến nó thành hàng loạt cuộc họp bắt buộc.

~~~mermaid
flowchart TD
    A["Phần thay đổi đã sẵn sàng để kiểm tra?"] --> B{"Đáp ứng DoD chưa?"}
    B -->|"Chưa"| C["Không gọi là Increment Done; hoàn thiện và kiểm tra lại"]
    C --> B
    B -->|"Có"| D["Increment đã Done và có thể sử dụng"]
    D --> E{"Giá trị/phạm vi phát hành có rõ?"}
    E -->|"Chưa"| F["PO và các bên liên quan làm rõ mục tiêu và đối tượng"]
    F --> E
    E -->|"Có"| G{"Đủ điều kiện bảo mật, vận hành, quyền release?"}
    G -->|"Chưa"| H["Giữ Increment Done; giải quyết điều kiện còn thiếu"]
    H --> G
    G -->|"Có"| I["Release ngay khi phù hợp, không cần chờ Sprint Review"]
    I --> J["Quan sát lỗi, tác động, phản hồi; rollback khi cần"]
    J --> K["Sprint Review kiểm tra kết quả và điều chỉnh hướng đi"]
~~~

### Bộ câu hỏi một phút trước release

- Phần thay đổi này **đã thực sự đạt DoD** chưa?
- Đối tượng nào sẽ sử dụng, và họ **nhận được kết quả gì**?
- Có yêu cầu **bảo mật, riêng tư, dữ liệu, hợp đồng hoặc vận hành** nào chưa được đáp ứng không?
- Người có **thẩm quyền release** đã rõ, có cơ chế dừng/khôi phục phù hợp chưa?
- Sau khi mở, nhóm sẽ biết **nó hoạt động và có ích** bằng cách nào?
- Có đang chờ Sprint Review **chỉ vì thói quen** hay vì một ràng buộc thực sự cần giải quyết?

Nếu tất cả điều kiện phù hợp đều đạt, không cần giữ một Increment đang tạo giá trị trong trạng thái chờ chỉ để “được trình diễn cuối Sprint”.

## 12. Sprint Review còn đóng vai trò gì sau khi release sớm?

Một ngộ nhận là: “Nếu đã release liên tục thì Sprint Review chỉ là cuộc demo lại, có thể bỏ”. Điều đó không đúng với Scrum.

**Mục đích của Sprint Review** là kiểm tra kết quả Sprint và xác định những điều chỉnh tiếp theo. Scrum Team cùng các bên liên quan xem **điều đã hoàn thành**, tiến độ hướng tới **Product Goal**, **điều gì đã thay đổi trong môi trường sản phẩm** và **việc nên làm tiếp**. Product Backlog có thể được điều chỉnh để nắm bắt cơ hội mới.

### 12.1. Nội dung cuộc Review khi I1 đã ra mắt từ ngày 3

Tại Sprint Review cuối Sprint, nhóm không cần giả vờ I1 mới được bàn giao. Thay vào đó:

- Tóm tắt **Sprint Goal** và những Increment đã Done.
- Cho thấy tính năng đã được đưa tới nhóm người dùng nào, vào thời điểm nào.
- Chia sẻ dữ liệu sử dụng, lỗi, phản hồi định tính, giới hạn của thử nghiệm.
- Thảo luận nguyên nhân người học gặp khó khăn, cơ hội cải thiện và các giả định bị bác bỏ.
- Cùng các bên liên quan xem Product Goal còn phù hợp và Product Backlog nên đổi thứ tự ra sao.
- Nhìn những Increment **Done nhưng chưa release**, làm rõ lý do và kế hoạch phù hợp.

Sprint Review nên là **buổi làm việc giữa Scrum Team và các bên liên quan**, không chỉ là trình diễn một chiều để xin chữ ký. Đầu ra quan trọng là **hiểu biết tốt hơn và lựa chọn tiếp theo**, không phải một biên bản “cho phép Done”.

### 12.2. Sprint Review không phải nơi đợi để mới lộ vấn đề

Nếu lỗi nghiêm trọng xuất hiện ngày thứ năm, nhóm cần phản ứng ngay theo trách nhiệm vận hành; không chờ tới Sprint Review mới nêu. Tương tự, nếu phản hồi của người học cho thấy một giả thuyết quan trọng sai, PO và Developers có thể trao đổi để điều chỉnh các quyết định liên quan, giữ tính minh bạch và phù hợp Sprint Goal.

### 12.3. Sprint Review cũng không thay thế nghiệm thu hợp đồng

Một dự án có thể phải có **chứng cứ nghiệm thu** hoặc chữ ký của khách hàng theo điều khoản cụ thể. Tổ chức cần thực hiện nghĩa vụ đó, nhưng không nên đánh đồng thủ tục hợp đồng với Sprint Review. Có thể phối hợp lịch và dùng dữ liệu/Increment đã Done làm cơ sở, miễn là vai trò và mục tiêu của từng hoạt động được phân biệt.

## 13. Những tình huống thường gây tranh cãi

### Tình huống A — Chức năng đã đạt DoD, nhưng chưa có chiến dịch thông báo

Increment đã Done, nhóm có thể sử dụng nội bộ và sản phẩm ổn định. Bộ phận marketing muốn mở cùng một chiến dịch đã định vào tuần sau.

**Cách hiểu:** Increment đã Done; **chưa release rộng** vì lựa chọn kinh doanh. Không cần giữ story ở trạng thái “In Progress” chỉ vì chiến dịch chưa diễn ra. Hãy ghi rõ trạng thái phát hành và kế hoạch truyền thông.

### Tình huống B — Code đã deploy nhưng bài kiểm thử phân quyền thất bại

Một endpoint trắc nghiệm đã lên production, nhưng kiểm thử phát hiện người học có thể xem bài làm của tài khoản khác.

**Cách hiểu:** Không đủ điều kiện coi phần công việc đó là Increment Done theo tiêu chuẩn bảo mật cần thiết. Phải kích hoạt xử lý rủi ro/sự cố tùy mức độ, bảo vệ dữ liệu và khắc phục. Không viện dẫn “release sớm theo Scrum” để biện minh.

### Tình huống C — Increment Done nhưng chờ nhà cung cấp thanh toán

Bản thay đổi đã tích hợp vào sản phẩm và đạt DoD; tuy nhiên, nhà cung cấp thanh toán thông báo cửa sổ bảo trì, không an toàn để mở luồng mới trong thời gian đó.

**Cách hiểu:** Có thể giữ Increment đã Done và **dời thời điểm release** vì ràng buộc vận hành thực. Cần phân biệt rõ “Done nhưng chưa mở” với “chưa Done”.

### Tình huống D — PM yêu cầu Sprint Review mới được ký phát hành

Tổ chức có PM chịu trách nhiệm về hợp đồng và mốc ra mắt. PM yêu cầu “phải có chữ ký ở Sprint Review” vì quy định cũ, dù chính sách hiện hành không bắt buộc ký duyệt vào ngày đó.

**Cách xử lý:** Làm rõ thẩm quyền và nghĩa vụ thực. Nếu không có yêu cầu kiểm soát bắt buộc, có thể đề xuất quy trình release theo điều kiện sẵn sàng và báo cáo kết quả tại Sprint Review. Nếu hợp đồng cần nghiệm thu, duy trì nghiệm thu theo quy định **tách khỏi mục đích Scrum của Sprint Review**.

### Tình huống E — Nhóm muốn release mỗi story ngay khi merge

Một story có thể chỉ mới merge giao diện, trong khi API hoặc dữ liệu còn chưa hoàn tất.

**Cách hiểu:** Merge không đồng nghĩa Done. Chỉ công bố phần đã tạo thành Increment đáp ứng DoD và điều kiện release; tập trung vào **lát đầu cuối** thay vì số lượng pull request.

### Tình huống F — Có nhiều Scrum Teams cùng một sản phẩm

Nhóm A hoàn tất thay đổi API, nhóm B hoàn tất giao diện, nhưng hai phần không tương thích trên môi trường tích hợp.

**Cách hiểu:** Các bên cần phối hợp để có một Increment tích hợp, dùng được, phù hợp cùng DoD của sản phẩm. Không gọi hai thành phần rời rạc là hai Increment đã tạo giá trị nếu chúng chưa phối hợp hoạt động theo tiêu chuẩn.

## 14. Phát hành sớm trong Scrum và dòng công việc Kanban

Các kỹ thuật **Kanban** có thể hỗ trợ Scrum Team quan sát những điểm nghẽn giữa Done kỹ thuật và giá trị tới người dùng.

Ví dụ bảng theo luồng:

~~~text
Ready -> Development -> Review -> Verify -> Done -> Released
             WIP 3       WIP 2

Done     : Increment đã đáp ứng Definition of Done.
Released : Chức năng đã được mở cho đối tượng người dùng xác định.
~~~

Các cột và giới hạn WIP chỉ minh họa; **Scrum không bắt buộc dùng bảng Kanban này**. Nếu nhóm có cột “Done” và “Released”, hãy giữ **định nghĩa nhất quán**. Release có thể phụ thuộc vào lịch marketing hoặc nghĩa vụ tổ chức mà không làm thay đổi trạng thái Done.

### 14.1. Một số chỉ số hữu ích

| Chỉ số | Phục vụ câu hỏi | Lưu ý |
| --- | --- | --- |
| **Cycle time đến Done** | Mất bao lâu từ khi bắt đầu một mục tới khi đạt DoD? | Định nghĩa mốc bắt đầu/kết thúc rõ, không coi một mục lâu là lỗi cá nhân. |
| **Thời gian chờ từ Done đến Released** | Một Increment đã sẵn sàng nằm chờ phát hành bao lâu và vì sao? | Có chờ hợp lý do kinh doanh/tuân thủ, không phải mọi chờ đều là lãng phí. |
| **Lead time đến giá trị sử dụng** | Từ yêu cầu đến khi người dùng thực sự có thể dùng là bao lâu? | Phải định nghĩa rõ điểm bắt đầu và nhóm người dùng. |
| **Deployment frequency** | Thay đổi được đưa lên môi trường chạy thường xuyên ra sao? | Deploy nhiều không tự chứng minh giá trị tăng. |
| **Change failure rate** | Tỷ lệ thay đổi triển khai gây sự cố cần xử lý là bao nhiêu? | Định nghĩa sự cố và mức nghiêm trọng thống nhất. |
| **Thời gian phục hồi dịch vụ** | Khi có sự cố, nhóm khôi phục trải nghiệm ổn định nhanh thế nào? | Không tối ưu số đo bằng cách giấu sự cố. |
| **Outcome sản phẩm** | Người dùng hoàn tất tác vụ, quay lại, học tốt hơn không? | Cần kết hợp dữ liệu và bối cảnh, tránh quy mọi biến động cho một release. |

Những số đo này hỗ trợ cải tiến luồng giao hàng. **Không nên tạo bảng xếp hạng cá nhân dựa trên số release hoặc số commit**, vì sản phẩm và đóng góp thường là kết quả tập thể.

### 14.2. Giảm WIP trước khi đòi release nhanh hơn

Nếu bảng có nhiều mục ở Review/Verify mà ít mục đạt Done, nhóm nên xem lại kích thước story, tiêu chí chấp nhận, thiếu kiểm thử tự động hoặc phụ thuộc. Việc yêu cầu “release ngày nào cũng phải có” khi chưa có Increment Done dễ tạo sức ép cắt chất lượng.

Mục tiêu không phải tần suất phát hành cao bằng mọi giá, mà là **giảm độ trễ từ ý tưởng có giá trị tới phản hồi đáng tin cậy**.

## 15. Tổ chức thông tin phát hành để minh bạch

Để phát hành sớm mà không gây nhầm lẫn, nhóm có thể ghi một bản tóm tắt ngắn cho mỗi lần mở tính năng. Không nhất thiết tạo tài liệu dài hay một cuộc họp mới.

### Mẫu thông tin release

~~~text
MỤC TIÊU GIÁ TRỊ:
  Người dùng cần làm được gì / nhóm đang kiểm chứng giả thuyết nào?

INCREMENT:
  Phạm vi đã đạt DoD; các biến thể CHƯA nằm trong phạm vi.

TRẠNG THÁI:
  Done / Deployed / Released (ghi riêng, không đánh đồng).

ĐỐI TƯỢNG VÀ THỜI ĐIỂM:
  Nhóm dùng thử hoặc người dùng rộng; khi nào được mở.

ĐIỀU KIỆN SẴN SÀNG:
  Bằng chứng DoD, bảo mật, dữ liệu, vận hành, thẩm quyền nếu cần.

KIỂM SOÁT RỦI RO:
  Theo dõi lỗi, giới hạn rollout, phương án tắt hoặc khôi phục.

PHẢN HỒI:
  Chỉ số sản phẩm, phản hồi định tính, người theo dõi.

NGƯỜI CHỊU TRÁCH NHIỆM:
  Ai quyết định release, ai hỗ trợ, khi nào xem lại?
~~~

**Ví dụ ngắn:**

> “I1 — Trả lời một câu hỏi trắc nghiệm — đã đạt DoD và được bật cho một lớp học thử vào ngày thứ tư của Sprint. Chưa hỗ trợ lưu lịch sử nhiều lần làm bài. Nhóm theo dõi tỷ lệ nộp thành công, lỗi truy cập và phản hồi về sự rõ ràng của kết quả. Nếu xuất hiện vấn đề nghiêm trọng, người phụ trách vận hành và Developers sẽ xử lý theo phương án đã thống nhất; dữ liệu được mang tới Sprint Review để quyết định lát tiếp theo.”

Điểm quan trọng là **báo đúng điều đã xảy ra**. Một Increment chưa release không nên được trình bày là đã tạo ra kết quả sử dụng thực tế, và một release cho 20 người học không nên được mô tả như đã mở cho toàn bộ khách hàng.

## 16. Quản lý phụ thuộc và sự cố khi phát hành giữa Sprint

### 16.1. Phụ thuộc cần hiển thị sớm

Một Increment có thể cần API ngoài, cấu hình môi trường, thay đổi schema hoặc điều kiện hạ tầng. Nhóm nên:

1. Làm rõ phụ thuộc ngay khi refinement và Sprint Planning.
2. Thử kết nối hoặc thực hiện phần tích hợp rủi ro sớm.
3. Chia story thành lát có hành vi đầu cuối, không dồn ghép các lớp vào cuối Sprint.
4. Phản ánh trạng thái bị chặn và ảnh hưởng tới Sprint Goal.
5. Trao đổi với Product Owner khi dự báo và lựa chọn phạm vi cần thay đổi.
6. Nhờ Scrum Master hỗ trợ làm cho trở ngại được tháo gỡ, với đúng người có thẩm quyền ngoài nhóm khi cần.

Một prototype hoặc mock có thể giúp giảm rủi ro, nhưng **không thay thế kiểm thử tích hợp thật** khi chức năng cần tương tác thật để được coi là Done.

### 16.2. Sự cố sau release không chờ Sprint Review

Nếu tính năng I1 được mở ngày thứ tư rồi gây lỗi nộp bài, nhóm cần xử lý theo **mức độ nghiêm trọng và quy trình ứng phó sự cố**. Việc sửa lỗi, rollback hoặc tắt flag có thể được thực hiện ngay bởi người có quyền, không đợi sự kiện cuối Sprint.

Sau khi xử lý, Scrum Team có thể phân tích nguyên nhân, cải thiện DoD, kiểm thử, pipeline và cách vận hành trong **Sprint Retrospective**. Tại Sprint Review, nhóm có thể thảo luận tác động tới giá trị và hướng sản phẩm, không biến cuộc họp thành buổi xét lỗi cá nhân.

### 16.3. Không bỏ Sprint Goal vì có nhiều cơ hội release

Được phép tạo nhiều Increment và release sớm không có nghĩa **mỗi Increment phải có mục tiêu kinh doanh độc lập hoàn toàn**. Chúng có thể cùng tiến tới Sprint Goal. Developers vẫn cần lập và điều chỉnh kế hoạch để hướng tới mục tiêu thống nhất, không mở nhiều công việc chỉ để đạt chỉ tiêu số lần release.

## 17. Những ngộ nhận phổ biến

| Ngộ nhận | Vì sao không chính xác | Cách hiểu phù hợp |
| --- | --- | --- |
| **“Sprint Review là cuộc họp ký duyệt để được release.”** | Scrum Guide không xem Sprint Review là cổng phát hành. | Release khi Increment đạt DoD và đủ điều kiện thực tế; Review để kiểm tra và thích ứng. |
| **“Mỗi Sprint chỉ có đúng một Increment.”** | Có thể có nhiều Increment trong một Sprint. | Tích hợp và đạt DoD cho từng phần hoàn tất. |
| **“Phải đợi hết Sprint mới giao giá trị.”** | Một Increment có thể được bàn giao trước khi Sprint kết thúc. | Đưa giá trị tới người dùng sớm khi phù hợp và an toàn. |
| **“Đã deploy tức là đã release.”** | Mã có thể triển khai nhưng chưa mở qua feature flag. | Báo riêng deployed và released. |
| **“Release sớm thì bỏ qua kiểm thử.”** | Làm vậy trái mục tiêu Increment có thể sử dụng và DoD. | Giữ chất lượng, tăng tự động hóa, chia lát nhỏ. |
| **“PO đồng ý thì code chưa đạt DoD cũng gọi là Done.”** | Sự đồng ý không thay tiêu chuẩn chất lượng. | Hoàn thiện và kiểm tra tới DoD trước khi gọi Increment. |
| **“Chưa release nghĩa là story chưa Done.”** | Quyết định release có thể phụ thuộc kinh doanh/vận hành. | Phân biệt Increment Done với trạng thái mở cho người dùng. |
| **“Đã release rồi thì bỏ Sprint Review.”** | Review còn kiểm tra kết quả, phản hồi và hướng Product Goal. | Sử dụng dữ liệu từ release sớm để thảo luận quyết định kế tiếp. |
| **“Bật flag cho một người thì không cần bảo mật.”** | Dữ liệu và quyền vẫn cần bảo vệ. | Kiểm soát rủi ro trước bất kỳ release thật nào. |
| **“Cần ít nhất một release mỗi ngày mới là Agile.”** | Scrum không đặt quota phát hành, nhịp phù hợp tùy sản phẩm. | Tối ưu giá trị, phản hồi, chất lượng và khả năng giao hàng bền vững. |
| **“Release thuộc quyền Scrum Master vì SM quản lý quy trình.”** | Scrum không giao mặc định quyền phát hành cho SM. | Làm rõ thẩm quyền tổ chức; giữ đúng accountability Scrum. |
| **“Các đội cùng sản phẩm tự dùng DoD khác nhau cho tiện.”** | Với một sản phẩm, các Increment cần đáp ứng cùng DoD và tích hợp. | Thống nhất DoD phù hợp trong bối cảnh nhiều Scrum Teams. |

## 18. Bài tập thực hành: một Sprint và ba lựa chọn release

Nhóm bạn phát triển **nền tảng luyện tập kiến thức Java**. Sprint hiện tại có Sprint Goal: “Người học làm được một bài kiểm tra ngắn và biết kết quả đáng tin cậy.”

Đến **ngày thứ năm** của Sprint hai tuần:

- **PBI-A:** Người học chọn đáp án và nhận phản hồi. Đã tích hợp, qua kiểm thử, đáp ứng DoD.
- **PBI-B:** Lưu lịch sử bài làm. Chưa kiểm tra trường hợp người học gửi yêu cầu trùng; có khả năng lưu hai lần.
- **PBI-C:** Gửi email nhắc ôn tập. Code và API đã viết, nhưng chưa tích hợp với dịch vụ email thật; mới dùng mock.
- **Hạ tầng:** Production đang ổn định; vận hành cho phép release giới hạn cho một lớp đã đăng ký thử, có giám sát và cơ chế tắt tính năng.
- **Bên liên quan:** Quản lý dự án muốn đợi Sprint Review cuối Sprint mới mở mọi tính năng vì “chưa được duyệt”.
- **Phản hồi đã có từ nguyên mẫu:** Người học chưa hiểu thông báo “đáp án không hợp lệ”.

### Yêu cầu

1. Phân loại A, B, C: mục nào có thể coi là **Increment Done** theo thông tin đã cho? Mục nào chưa? Giải thích.
2. Đề xuất một phương án **release trước Sprint Review** cho phạm vi có giá trị và đủ điều kiện.
3. Viết checklist tối thiểu cho bản release thử: chất lượng, quyền truy cập, vận hành, đối tượng và phản hồi.
4. Nếu người quản lý nói “cần ký tại Sprint Review”, bạn sẽ hỏi những câu nào để phân biệt **thói quen** và **nghĩa vụ bắt buộc**?
5. Dự kiến tại Sprint Review nhóm sẽ trình bày **điều gì khác một cuộc demo**?
6. Sau release A, dữ liệu cho thấy 40% người dùng thử nộp bài thành công nhưng nhiều người thoát ở bước đọc kết quả. Chọn hai giả thuyết cần kiểm tra trước khi đầu tư tiếp B/C.
7. Nếu xuất hiện lỗi lộ đáp án riêng tư, bạn sẽ đợi Sprint Review hay xử lý ngay? Ai cần tham gia?
8. Nêu một chỉ số dòng công việc và một chỉ số giá trị sản phẩm giúp đánh giá lợi ích của phát hành sớm.

### Hướng giải tham khảo

**Phân loại:** A được mô tả là đã đạt DoD và có thể sử dụng trong phạm vi đã kiểm tra; B chưa đạt điều kiện đúng đắn về lưu dữ liệu, C chưa kiểm chứng tích hợp thật. Không nên gọi B/C là Increment Done chỉ vì code đã có hoặc đã dùng mock.

**Phát hành:** Xem xét mở A cho lớp thử trước Sprint Review, sau khi xác nhận quyền release, điều kiện bảo mật và vận hành. B/C chưa nằm trong phạm vi công bố. Nếu A phụ thuộc thực tế vào B/C để chạy được, cần kiểm tra lại; dữ kiện bài tập giả định A độc lập trong phạm vi cốt lõi.

**Checklist:** DoD và trường hợp lỗi của A; xác thực, quyền truy cập; giám sát lỗi; tài khoản thử; cơ chế dừng/khôi phục; người chịu trách nhiệm theo dõi; tín hiệu nộp thành công và phản hồi khó hiểu.

**Làm rõ “phê duyệt”:** Có điều khoản pháp lý/hợp đồng nào bắt buộc đúng ngày Sprint Review không? Ai thực sự có thẩm quyền release? Có thể thực hiện các bước kiểm soát khi Increment đạt DoD, không đợi cuộc họp không? Ai và cách nào báo cho người liên quan?

**Sprint Review:** Cùng kiểm tra tiến độ hướng Sprint Goal/Product Goal; trình bày kết quả dùng thật, lỗi, khó khăn đọc phản hồi, giá trị sản phẩm và các lựa chọn Product Backlog tiếp theo, không yêu cầu chữ ký mới coi A đã Done.

**Giả thuyết mới:** Nội dung phản hồi đúng/sai có thể chưa đủ dễ hiểu; hoặc người học kỳ vọng giải thích đáp án và bước ôn tập tiếp theo. Cần kiểm tra với dữ liệu/trao đổi, không tự suy nguyên nhân từ một tỷ lệ.

**Sự cố:** Xử lý ngay theo quy trình, hạn chế ảnh hưởng, phối hợp Developers, vận hành, bảo mật và người có thẩm quyền; cập nhật PO về tác động. Không đợi Sprint Review.

**Đo lường:** Thời gian từ Done tới Released cho một Increment; tỷ lệ người học hoàn thành bài và hiểu phản hồi hoặc tín hiệu học tập liên quan, thay vì chỉ đếm số release.

## 19. Tự kiểm tra kiến thức

**Câu 1.** Một Increment đạt DoD vào thứ Tư. Sprint Review vào thứ Sáu. Scrum có bắt buộc đợi thứ Sáu mới release không?

**Đáp án:** Không. Increment có thể được bàn giao hoặc release trước Sprint Review khi đủ điều kiện liên quan. Sprint Review không phải cổng phát hành.

**Câu 2.** Sprint có thể tạo và phát hành hơn một Increment không?

**Đáp án:** Có thể tạo nhiều Increment trong một Sprint. Mỗi Increment phải tích hợp, hoạt động với các Increment trước và đáp ứng DoD. Phát hành từng Increment hay theo nhóm là quyết định phù hợp với điều kiện tổ chức.

**Câu 3.** Code của một story đã merge nhưng kiểm thử phân quyền thất bại. Có gọi là Increment Done không?

**Đáp án:** Không. Phần chưa đạt tiêu chuẩn chất lượng cần thiết không thể coi là Increment Done, dù đã merge hoặc deploy.

**Câu 4.** Một Increment đã Done nhưng chưa release do cửa sổ bảo trì bên ngoài. Có cần sửa trạng thái thành “chưa Done” không?

**Đáp án:** Không tự động. Cần ghi rõ Increment đã đạt DoD và còn chờ điều kiện release. Nếu phát hiện vấn đề làm DoD thực tế không đạt, khi đó mới phải xem lại nhận định Done.

**Câu 5.** Deploy và release khác nhau thế nào?

**Đáp án:** Deploy đưa phần mềm lên môi trường chạy; release mở khả năng sản phẩm cho đối tượng người dùng. Có thể deploy với feature flag tắt mà chưa release.

**Câu 6.** Nếu release vào ngày thứ ba và đã nhận phản hồi, Sprint Review có còn cần thiết trong Scrum không?

**Đáp án:** Có. Scrum Team và các bên liên quan dùng Sprint Review để kiểm tra kết quả Sprint, tiến độ Product Goal và xác định điều chỉnh tiếp theo. Phản hồi sớm làm buổi Review nhiều thông tin hơn.

**Câu 7.** Scrum Guide chỉ định Product Owner, Scrum Master hay Project Manager là người duyệt mọi release?

**Đáp án:** Không. Scrum xác định các accountabilities của PO, SM và Developers, nhưng quyền phê duyệt release cụ thể cần được tổ chức làm rõ theo bối cảnh và trách nhiệm liên quan.

**Câu 8.** Feature flag có thể thay thế kiểm thử hoặc bảo mật cho một tính năng chưa đạt DoD không?

**Đáp án:** Không. Flag hỗ trợ kiểm soát phạm vi mở, nhưng không biến một phần chưa hoàn tất thành Increment có thể sử dụng, cũng không xóa rủi ro dữ liệu.

**Câu 9.** Vì sao không nên dùng số lần phát hành trong một Sprint làm thước đo duy nhất của nhóm?

**Đáp án:** Tần suất phát hành không tự cho biết giá trị người dùng, chất lượng hay mức rủi ro. Cần xem kết quả sản phẩm, sự cố và năng lực giao hàng trong bối cảnh phù hợp.

**Câu 10.** Những điều gì có thể được điều chỉnh ở Sprint Review khi các Increment đã phát hành sớm?

**Đáp án:** Cách hiểu kết quả người dùng, cơ hội, rủi ro, thứ tự Product Backlog và các lựa chọn để tiến tới Product Goal. Review không phải nơi hợp thức hóa hồi tố chất lượng của một Increment.

## 20. Ghi nhớ trọng tâm

- **Increment trong Scrum là bước tiến sản phẩm đã tích hợp, có thể sử dụng và đáp ứng Definition of Done.** Một phần chỉ “code xong” chưa đủ để gọi là Done.
- **Có thể tạo nhiều Increment trong một Sprint, và bàn giao/phát hành Increment trước khi Sprint kết thúc.**
- **Sprint Review không phải cổng bắt buộc để phát hành giá trị.** Đây là sự kiện Scrum để kiểm tra kết quả, tương tác với các bên liên quan và điều chỉnh hướng đi.
- **Done, deploy, release và nghiệm thu hợp đồng là những khái niệm khác nhau.** Báo cáo rõ trạng thái để tránh “xanh giả” hoặc trì hoãn vô ích.
- **Không đánh đổi chất lượng để giao sớm.** DoD, quyền truy cập, bảo mật, tính đúng đắn dữ liệu và yêu cầu vận hành bắt buộc vẫn phải được đáp ứng.
- **Thẩm quyền release cần rõ**, nhưng Scrum không quy định phải là PO, SM hay PM ký duyệt mọi lần mở tính năng.
- **Chia lát dọc, tích hợp và kiểm thử liên tục** giúp tạo những Increment nhỏ, đáng tin và đủ sức đưa cho người dùng sớm.
- **Feature flag, canary và rollout theo giai đoạn** hỗ trợ quản lý phạm vi ảnh hưởng; không thay thế DoD hoặc xử lý rủi ro nghiêm trọng.
- **Phản hồi sau release là đầu vào để thích ứng.** Dùng dữ liệu sử dụng, lỗi, chất lượng và số đo luồng để quyết định nên xây phần nào tiếp.
- **Mục tiêu không phải release nhiều bằng mọi giá**, mà là rút ngắn khoảng cách từ một ý tưởng có giá trị tới phần mềm dùng được và phản hồi thực tế.

Khi một Increment đã Done và đủ điều kiện đưa vào sử dụng, nhóm có thể **bàn giao hoặc phát hành ngay thay vì chờ Sprint Review như một cửa phê duyệt**. Việc phát hành sớm giúp người dùng nhận giá trị và Scrum Team học nhanh hơn; Sprint Review sau đó trở thành nơi trao đổi có dữ liệu thực, đánh giá tiến bộ hướng Product Goal và lựa chọn các bước tiếp theo. Đây là cách Scrum hỗ trợ Agile: **chất lượng rõ ràng, giá trị giao tăng dần và thích ứng liên tục bằng phản hồi**.
