# Trách nhiệm Scrum: Quản lý Product Backlog và truyền đạt Product Goal

Trong một nhóm phát triển phần mềm, có thể có hàng trăm đề xuất: khách hàng muốn thêm chức năng, bộ phận hỗ trợ cần sửa lỗi, kỹ sư muốn giảm nợ kỹ thuật, lãnh đạo đặt mục tiêu kinh doanh mới. Nếu thiếu một mục tiêu sản phẩm được hiểu chung và một cơ chế quyết định thứ tự công việc, nhóm dễ trở thành nơi nhận nhiệm vụ từ nhiều phía. Kết quả là làm rất nhiều nhưng khó biết **đang tiến gần đến giá trị nào**.

Trong **Scrum**, **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm phát sinh từ công việc của Scrum Team và chịu trách nhiệm về **quản lý Product Backlog hiệu quả**. Một phần đặc biệt quan trọng là **phát triển và truyền đạt rõ Product Goal** để mọi người biết trạng thái sản phẩm tương lai mà nhóm đang hướng tới. Product Goal giúp định hướng; Product Backlog giúp minh bạch hóa những gì có thể cần làm để tiến gần mục tiêu đó.

Bài học thuộc mô-đun **AGILE_DEVELOPMENT**: thực hành Agile qua phản hồi sớm, giao phần mềm tăng dần, cải tiến liên tục và sử dụng user story, backlog, Scrum, Kanban, XP cùng đo lường dòng công việc để phối hợp phù hợp. Trọng tâm ở đây là **trách nhiệm của Product Owner đối với Product Goal và Product Backlog**, nhưng cũng làm rõ cách Developers, Scrum Master và các bên liên quan hợp tác để quyết định chuyển thành Increment hữu ích.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Product Goal**, **Product Backlog** và sự liên hệ của chúng trong Scrum.
2. Nêu đúng các hoạt động cấu thành trách nhiệm quản lý Product Backlog của Product Owner.
3. Phân biệt **trách nhiệm cuối cùng (accountability)** với công việc có thể **ủy quyền thực hiện**.
4. Phát biểu và truyền đạt Product Goal sao cho mô tả một trạng thái sản phẩm tương lai có giá trị, không chỉ danh sách tính năng.
5. Sắp thứ tự Product Backlog items theo mục tiêu, giá trị, rủi ro, bằng chứng và phụ thuộc, thay vì theo người yêu cầu lớn tiếng nhất.
6. Phối hợp refinement, Sprint Planning và Sprint Review mà không nhầm quyền ưu tiên của Product Owner với quyền lập kế hoạch thực hiện của Developers.
7. Thiết kế cách giao tiếp với stakeholder, xử lý mục tiêu xung đột và kiểm tra tiến triển bằng kết quả người dùng.
8. Vận dụng vào một tình huống có dữ liệu, bảng backlog, quyết định ưu tiên, bài thực hành và checklist.

## 2. Hai khái niệm nền tảng: Product Goal và Product Backlog

### 2.1. Product Goal là gì?

**Product Goal** mô tả **một trạng thái tương lai của sản phẩm** mà Scrum Team có thể dùng làm mục tiêu để lập kế hoạch và tập trung nỗ lực. Trong Scrum, nó là **cam kết (commitment) gắn với Product Backlog**.

Product Goal không nhất thiết là một con số doanh thu. Nó có thể mô tả một năng lực hoặc kết quả rõ ràng mà sản phẩm cần đạt cho người dùng, miễn đủ cụ thể để nhóm cùng định hướng và kiểm tra tiến triển.

Ví dụ sản phẩm đăng ký workshop:

> **Product Goal:** Học viên có thể tự chọn buổi còn chỗ, gửi đăng ký và hiểu rõ mình đã được xác nhận hay chưa, trong khi điều phối viên xử lý số chỗ chính xác mà không cần trao đổi thủ công cho các trường hợp thông thường.

Mục tiêu này nêu **trạng thái tương lai có ích** của sản phẩm, chưa chốt công nghệ, cấu trúc dữ liệu, số màn hình hay thứ tự từng story. Nhóm có thể thiết kế nhiều lát cắt để tiến tới nó.

Theo Scrum, Scrum Team tập trung vào **một Product Goal tại một thời điểm**: cần hoàn thành hoặc chủ động từ bỏ mục tiêu hiện có trước khi nhận mục tiêu kế tiếp. Điều đó không có nghĩa sản phẩm chỉ có một mong muốn dài hạn, mà là tránh đổi đích liên tục trong khi chưa quyết định điều gì đã đạt hoặc không còn đáng theo đuổi.

### 2.2. Product Backlog là gì?

**Product Backlog** là **danh sách có thứ tự, liên tục phát triển** về những gì cần thiết để cải thiện sản phẩm. Trong Scrum, nó là nguồn công việc duy nhất do Scrum Team thực hiện cho sản phẩm.

Các Product Backlog items (PBIs) có thể diễn đạt dưới dạng user story, lỗi cần sửa, cải tiến chất lượng, công việc giảm rủi ro hay những phần việc sản phẩm khác. **Scrum không bắt buộc mọi PBI phải là user story** hoặc dùng một công cụ, một mẫu mô tả hay một thang ước lượng cố định.

Product Backlog được **sắp thứ tự (ordered)**, không chỉ gắn ba mức “cao – vừa – thấp”. Thứ tự phải phản ánh quyết định có căn cứ về điều đáng tập trung tiếp theo. Khi biết thêm thông tin hoặc bối cảnh thay đổi, Product Backlog có thể được điều chỉnh.

### 2.3. Product Goal và Product Backlog khác nhau ra sao?

| Nội dung | Product Goal | Product Backlog |
| --- | --- | --- |
| **Bản chất** | Trạng thái tương lai của sản phẩm, mục tiêu dài hạn | Danh sách có thứ tự những việc có thể cần để cải thiện sản phẩm |
| **Vai trò trong Scrum** | Cam kết của Product Backlog | Một trong ba Scrum artifacts |
| **Câu hỏi chính** | “Chúng ta muốn sản phẩm trở thành gì, mang lại giá trị nào?” | “Những việc nào nên làm và theo thứ tự nào để tiến tới mục tiêu?” |
| **Mức ổn định mong muốn** | Đủ ổn định để tạo định hướng; có thể được hoàn thành hoặc từ bỏ có chủ đích | Liên tục được làm rõ, thêm, bỏ, tách, gộp, sắp lại |
| **Ví dụ** | Học viên tự đăng ký và hiểu kết quả; điều phối viên tránh trùng chỗ | Xem buổi còn chỗ; gửi yêu cầu; thông báo trạng thái; kiểm tra đồng thời |
| **Điều không nên nhầm** | Không phải toàn bộ roadmap hoặc một Sprint Goal | Không phải cam kết tất cả hạng mục sẽ được làm |

**Product Goal trả lời “đích đến”, Product Backlog trả lời “những lựa chọn công việc hiện biết để tiến đến đích”.** Cả hai cần được cập nhật bằng phản hồi thực tế chứ không chỉ tồn tại trên tài liệu.

### 2.4. Phân biệt Product Goal với Sprint Goal

**Sprint Goal** là cam kết của **Sprint Backlog**, nêu mục tiêu duy nhất cho Sprint để tạo sự tập trung và linh hoạt trong cách thực hiện. Nó ngắn hạn hơn Product Goal.

Ví dụ:

- **Product Goal:** học viên tự đăng ký workshop, hiểu trạng thái và điều phối viên kiểm soát chỗ chính xác.
- **Sprint Goal:** học viên trong nhóm thử có thể gửi một yêu cầu đăng ký hợp lệ và nhận trạng thái rõ ràng.
- **Một phần Sprint Backlog:** triển khai một lát cắt đăng ký, kiểm thử trường hợp hết chỗ, hoàn thiện thông báo và xác minh hành vi.

Không nên đổi Sprint Goal thành danh sách “làm xong 12 tickets”. Một Sprint Goal tốt nêu giá trị hoặc mục tiêu nhất quán; Developers có thể điều chỉnh kế hoạch chi tiết trong Sprint khi học thêm, miễn không làm mất Sprint Goal.

## 3. Product Owner chịu trách nhiệm gì?

Scrum xác định Product Owner là người **chịu trách nhiệm tối đa hóa giá trị của sản phẩm** phát sinh từ công việc của Scrum Team. Cách tối đa hóa giá trị có thể khác nhau giữa sản phẩm, tổ chức và bối cảnh.

Cụ thể, **quản lý Product Backlog hiệu quả** bao gồm bốn nội dung:

1. **Phát triển và truyền đạt rõ Product Goal.**
2. **Tạo và truyền đạt rõ các Product Backlog items.**
3. **Sắp thứ tự các Product Backlog items.**
4. **Bảo đảm Product Backlog minh bạch, dễ thấy và được hiểu.**

Product Owner **có thể ủy quyền việc thực hiện các hoạt động này cho người khác**, nhưng **vẫn là người chịu trách nhiệm cuối cùng**. Không thể biến nhiều người luân phiên ra quyết định mâu thuẫn rồi gọi đó là “cùng sở hữu Product Backlog”.

### 3.1. “Accountability” không đồng nghĩa phải tự làm mọi việc

Ví dụ, Product Owner có thể nhờ:

- Một người hiểu nghiệp vụ mô tả các trường hợp ngoại lệ của chính sách hoàn tiền.
- Developers chia nhỏ một PBI quá lớn và làm rõ rủi ro kỹ thuật.
- Một nhà nghiên cứu sản phẩm tổ chức dùng thử và tổng hợp phản hồi.
- Một thành viên ghi nhận phát hiện từ bộ phận hỗ trợ và liên kết nguồn phản hồi.

Tuy nhiên, Product Owner cần bảo đảm các thông tin này được dùng để **định hướng Product Goal, biểu đạt backlog, xác định thứ tự và truyền đạt quyết định**. Khi xuất hiện xung đột ưu tiên, tổ chức phải biết ai có trách nhiệm giải thích quyết định sản phẩm.

### 3.2. Product Owner là một người, không phải một hội đồng

Trong Scrum, **Product Owner là một người, không phải một ủy ban**. Product Owner có thể đại diện cho nhu cầu của nhiều stakeholder và cần lắng nghe họ. Những ai muốn thay đổi Product Backlog có thể thuyết phục Product Owner bằng thông tin, bằng chứng, đánh đổi và mục tiêu.

Điều này không có nghĩa Product Owner là người “độc đoán” hoặc có thể bỏ qua quy định về bảo mật, pháp lý, chất lượng và vận hành. **Quyền quyết định giá trị và thứ tự sản phẩm** cần được thực thi trong những ràng buộc thực tế và với trách nhiệm giải trình rõ ràng.

### 3.3. Trách nhiệm của Product Owner không phải quản lý con người

Product Owner **không mặc nhiên là trưởng nhóm kỹ thuật, quản lý nhân sự hay người giao việc chi tiết** cho Developers. Developers trong Scrum có trách nhiệm tạo kế hoạch cho Sprint, bảo đảm chất lượng qua Definition of Done và thích ứng kế hoạch mỗi ngày để đạt Sprint Goal.

Product Owner có thể làm rõ điều gì có giá trị và vì sao; Developers lựa chọn cách xây dựng và công việc cụ thể cần thiết. Sự hợp tác tốt tạo một quyết định chung có căn cứ, không phải kiểu “bên kinh doanh ra lệnh, bên kỹ thuật thi hành”.

## 4. Truyền đạt Product Goal rõ ràng và hữu ích

Một Product Goal có ý nghĩa cần giúp người trong nhóm **nối công việc hàng ngày với lý do sản phẩm tồn tại**. Nếu Product Goal chỉ là “xây hệ thống thế hệ mới”, nhóm không biết những kết quả nào quan trọng.

### 4.1. Khung xác định Product Goal

Khi thảo luận, Product Owner có thể dùng các câu hỏi:

1. **Sản phẩm có ranh giới và người dùng nào?** Không lẫn mục tiêu của toàn bộ công ty với một sản phẩm cụ thể.
2. **Vấn đề hoặc cơ hội chính là gì?** Có bằng chứng nào cho thấy vấn đề cần được giải quyết?
3. **Trạng thái tương lai cần đạt là gì?** Người dùng sẽ làm được gì khác trước?
4. **Giá trị với khách hàng và tổ chức ở đâu?** Có rủi ro chất lượng hay tác động không mong muốn phải tránh?
5. **Làm sao biết đang tiến gần mục tiêu?** Chọn tín hiệu kiểm chứng phù hợp.
6. **Có những giả định nào chưa biết?** Việc gì nên thử nhỏ để học trước khi mở rộng?

Một khung diễn đạt hỗ trợ thảo luận:

> **Đối với** [người dùng hoặc bối cảnh], **chúng ta muốn sản phẩm có khả năng** [trạng thái tương lai], **để** [lợi ích chính], **đồng thời bảo đảm** [ràng buộc quan trọng]. **Chúng ta sẽ kiểm tra tiến triển bằng** [những tín hiệu phù hợp].

Đây chỉ là **mẫu hỗ trợ tư duy**, không phải cách viết bắt buộc của Scrum.

### 4.2. Phân biệt mục tiêu và danh sách giải pháp

| Phát biểu | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Xây 20 màn hình và 15 API trước quý tới.” | Liệt kê đầu ra, không nêu người dùng được lợi gì | Nêu khả năng người dùng hoàn thành và tác động mong muốn |
| “Trở thành nền tảng số một.” | Khó kiểm tra, quá rộng | Xác định phạm vi sản phẩm và trạng thái tương lai cụ thể |
| “Tăng velocity mỗi Sprint 20%.” | Tối ưu chỉ số giao việc thay vì giá trị sản phẩm | Tập trung vào nhu cầu người dùng và nhịp giao giá trị bền vững |
| “Ai cũng làm được mọi thứ.” | Không rõ ai, việc gì và vì sao | Nêu luồng trọng yếu cần người dùng tự thực hiện an toàn |
| “Học viên tự hoàn tất đăng ký và biết rõ trạng thái; điều phối viên không xác nhận trùng suất.” | Nêu trạng thái sản phẩm có ý nghĩa | Có thể giữ, rồi xác định chỉ số kiểm chứng và rủi ro |

Một Product Goal có thể đi kèm các chỉ số, nhưng không cần ép một con số chưa có baseline thành cam kết giả. Nếu muốn dùng mốc định lượng, cần làm rõ định nghĩa, nguồn dữ liệu và mức độ chắc chắn.

### 4.3. Ví dụ hoàn chỉnh: ứng dụng đăng ký workshop

**Vấn đề quan sát minh họa:** học viên phải nhắn tin hỏi chỗ và trạng thái; điều phối viên ghi bảng tính nên dễ nhầm khi có nhiều đăng ký gần đồng thời.

**Product Goal đề xuất:**

> Học viên có thể tự tìm workshop phù hợp, gửi đăng ký và theo dõi kết quả rõ ràng; điều phối viên kiểm soát chỗ theo quy tắc thống nhất mà không cần xử lý thủ công những trường hợp thông thường.

**Tín hiệu để kiểm tra tiến triển:**

- Tỷ lệ học viên thử nghiệm **gửi đăng ký thành công** theo định nghĩa rõ.
- Tỷ lệ người dùng **hiểu đúng** “đã tiếp nhận” và “đã xác nhận chỗ”.
- Số lần cần liên hệ ban tổ chức để **hỏi lại trạng thái** trên mỗi đăng ký.
- Tỷ lệ hoặc số trường hợp **xác nhận vượt sức chứa**.
- Thời gian điều phối viên cần để xử lý một yêu cầu đủ điều kiện.

Các chỉ số trên có thể dùng làm tín hiệu; chưa đủ để khẳng định giải pháp đã gây ra kết quả nếu thiếu thiết kế kiểm tra phù hợp. Cần kết hợp quan sát, phỏng vấn và nguồn dữ liệu đáng tin cậy.

**Ràng buộc:** bảo vệ dữ liệu cá nhân, xác định quyền xem thông tin và không xác nhận quá số chỗ được phép. Không thể vì muốn giao sớm mà bỏ qua điều kiện an toàn thiết yếu.

### 4.4. Truyền đạt là hoạt động liên tục, hai chiều

Một slide công bố Product Goal chưa bảo đảm nhóm hiểu. Product Owner nên:

- Dùng cùng một phát biểu mục tiêu nhất quán trong trao đổi backlog và khi thảo luận với stakeholder.
- Giải thích **vì sao** một hạng mục được đặt cao hơn hạng mục khác.
- Cho mọi người cơ hội diễn giải lại mục tiêu bằng tình huống người dùng.
- Chia sẻ bằng chứng mới và công khai khi giả định thay đổi.
- Mời Developers và Scrum Master đặt câu hỏi, phản biện rủi ro và nêu cách tiếp cận khả thi.
- Kiểm tra rằng những bên liên quan hiểu **điều đang được ưu tiên** và **điều chưa được cam kết**.

Một phép kiểm tra đơn giản: hỏi ba thành viên “nếu phải bỏ một tính năng để giữ Product Goal, bạn sẽ cân nhắc điều gì?”. Nếu mỗi người nêu một đích khác nhau, cần làm rõ mục tiêu, không chỉ gửi lại đường dẫn tài liệu.

## 5. Từ Product Goal đến Product Backlog có thứ tự

Product Goal không tự sinh ra danh sách giải pháp đúng. Nhóm cần liên tục chuyển giả thuyết giá trị thành những mục có thể kiểm tra, trao đổi, sắp thứ tự và giao dưới dạng Increment.

### 5.1. Dòng liên kết từ mục tiêu đến kết quả

~~~mermaid
flowchart TD
    A[Product Goal: trạng thái tương lai của sản phẩm] --> B[Giả thuyết giá trị và rủi ro cần kiểm tra]
    B --> C[Product Backlog items có thứ tự]
    C --> D[Sprint Planning: chọn mục tiêu và công việc phù hợp]
    D --> E[Developers tạo Increment đạt Definition of Done]
    E --> F[Kiểm tra với bên liên quan và người dùng]
    F --> G[Phản hồi và dữ liệu kết quả]
    G --> H[Product Owner điều chỉnh thứ tự và cách hiểu backlog]
    H --> C
    G --> I{Product Goal còn phù hợp?}
    I -->|Có| B
    I -->|Đã đạt hoặc cần từ bỏ| J[Quyết định Product Goal kế tiếp khi phù hợp]
~~~

Sơ đồ là **vòng học hỏi minh họa**. Trong Scrum, các sự kiện có thời điểm và trách nhiệm cụ thể; việc kiểm tra và thích ứng cũng xảy ra khi có thông tin mới, không chỉ đến cuối Sprint.

### 5.2. Một backlog minh họa theo Product Goal

| Mã | Product Backlog item | Vai trò và lợi ích chính | Điều còn bất định | Gợi ý thứ tự |
| --- | --- | --- | --- | --- |
| WS-01 | Học viên xem buổi còn chỗ | Tránh chọn buổi không thể đăng ký | Quy tắc tính chỗ | Sớm |
| WS-02 | Học viên gửi đăng ký và nhận trạng thái rõ ràng | Chủ động gửi yêu cầu, bớt hỏi lại | Phân biệt nhận yêu cầu và xác nhận | Sớm |
| WS-03 | Kiểm soát xác nhận đồng thời | Tránh hai đăng ký được xác nhận cho cùng suất | Cách bảo vệ bất biến nghiệp vụ | Rất sớm nếu rủi ro hiện hữu |
| WS-04 | Điều phối viên xem và xử lý yêu cầu chờ | Kiểm soát số chỗ, tránh bỏ sót | Chính sách duyệt | Liên hệ WS-02/03 |
| WS-05 | Học viên tự xem lại trạng thái | Không cần nhắn ban tổ chức | Xác thực và quyền xem | Sau lát cắt đầu nếu phù hợp |
| WS-06 | Báo cáo doanh thu theo giảng viên | Hỗ trợ đối soát, có thể có giá trị | Chưa xác minh người dùng và tần suất | Làm rõ trước khi ưu tiên cao |
| WS-07 | Thêm nhiều hiệu ứng giao diện trang chủ | Trải nghiệm thẩm mỹ | Chưa thấy vấn đề người dùng | Chưa ưu tiên |

Các thứ tự là **gợi ý tình huống**, không phải quy tắc rằng chức năng kỹ thuật luôn đứng trên chức năng người dùng. Nếu WS-03 là điều kiện an toàn để WS-02 có thể hoạt động đúng, nhóm cần đưa bảo vệ dữ liệu vào lát cắt có thể sử dụng, thay vì phát hành WS-02 rồi mới sửa tình huống xác nhận trùng.

### 5.3. Phân biệt hạng mục backlog với kế hoạch thực hiện

Product Owner chịu trách nhiệm **sắp thứ tự Product Backlog** và truyền đạt kết quả mong muốn. Developers chịu trách nhiệm về **cách thực hiện**, ước lượng kích thước công việc và lập kế hoạch chi tiết trong Sprint.

Ví dụ:

- Product Owner: “Người dùng cần nhận kết quả rõ khi gửi yêu cầu; ưu tiên điều này trước báo cáo nâng cao.”
- Developers: “Để làm an toàn, cần kiểm tra đăng ký đồng thời, viết test và chia thành hai lát cắt.”
- Cả nhóm: “Lát cắt nào có thể giao trong Sprint, đạt DoD và hỗ trợ Sprint Goal?”

Không nên coi Product Backlog là danh sách lệnh kỹ thuật mà Product Owner phân công từng giờ cho từng người.

## 6. Sắp thứ tự: quyết định giá trị, rủi ro và đánh đổi

Scrum không bắt buộc một công thức ưu tiên cố định. Product Owner có thể dùng nhiều yếu tố, kết hợp với trao đổi cùng Developers và stakeholder.

| Yếu tố | Câu hỏi thực hành | Ví dụ |
| --- | --- | --- |
| **Giá trị người dùng** | Ai gặp vấn đề? Có bằng chứng? | Học viên hỏi lại trạng thái nhiều lần |
| **Mức độ rủi ro** | Nếu chậm, có lỗi dữ liệu, bảo mật hoặc vận hành? | Xác nhận vượt sức chứa |
| **Chi phí trì hoãn** | Việc chậm một vòng tạo hậu quả gì? | Workshop sắp diễn ra không thể nhận đăng ký đáng tin cậy |
| **Liên kết Product Goal** | Hạng mục có giúp tiến gần trạng thái mong muốn không? | Nhận và hiển thị trạng thái đăng ký |
| **Quy mô và tính khả thi** | Có thể giao phần có ích nào trước, phụ thuộc gì? | Làm lát cắt dọc nhỏ có kiểm thử |
| **Độ bất định** | Cần học gì trước khi đầu tư lớn? | Người dùng thực sự muốn email hay chỉ muốn trạng thái rõ? |
| **Chất lượng và khả năng duy trì** | Công việc có giảm rủi ro tích lũy hoặc tạo năng lực giao an toàn? | Bổ sung test chống đăng ký trùng |

Đây không phải công thức có trọng số bắt buộc. Một rủi ro mất dữ liệu nghiêm trọng đang xảy ra cần được ứng phó phù hợp, không nên chờ đủ điểm RICE/WSJF mới xử lý.

### 6.1. Vì sao Product Backlog là danh sách có thứ tự?

Giả sử tất cả hạng mục đều được gắn mức “High”. Khi Developers cần chọn việc cho Sprint tới, không ai biết điều nào nên làm trước nếu năng lực có hạn.

**Sắp thứ tự** buộc Product Owner diễn đạt quyết định: “WS-03 quan trọng hơn WS-06 hiện tại vì lỗi dữ liệu có thể xảy ra ngay; WS-02 đứng trước WS-07 vì hỗ trợ Product Goal và có phản hồi người dùng.” Thứ tự có thể đổi khi bằng chứng đổi.

### 6.2. Không dùng người yêu cầu lớn tiếng nhất làm quy tắc

Một khách hàng lớn, nhà quản lý hay nhóm kinh doanh có thể nêu nhu cầu rất quan trọng. Nhưng **mức ảnh hưởng của người yêu cầu** không tự động đồng nghĩa **giá trị của giải pháp**.

Product Owner cần hỏi:
- Nhu cầu này phục vụ ai và có vấn đề gì?
- Điều gì xảy ra nếu làm sau một vòng?
- Có cách thử nhỏ hơn hoặc giải pháp thay thế?
- Nếu đưa lên, hạng mục nào phải lùi?
- Điều gì sẽ xác nhận rằng quyết định ưu tiên là đúng?

Một quyết định có thể không làm hài lòng tất cả bên liên quan nhưng phải **có lý do và có thể kiểm tra**.

### 6.3. Việc kỹ thuật có nằm trong Product Backlog không?

Có thể có. Nếu công việc cải thiện sản phẩm, giảm rủi ro quan trọng hoặc cho phép nhóm bàn giao an toàn, Product Backlog có thể thể hiện nó. Không cần ép mọi việc thành câu chuyện giả kiểu “Là học viên, tôi muốn nâng phiên bản thư viện”.

Ví dụ:

> **Mục tiêu kỹ thuật:** ngăn hệ thống xác nhận hai yêu cầu cho cùng một suất cuối. **Giá trị/rủi ro:** bảo vệ tính đúng đắn đăng ký của học viên. **Kiểm chứng:** các tình huống đồng thời theo quy tắc nghiệp vụ đều được kiểm thử và đạt DoD.

Product Owner cần hiểu **giá trị và rủi ro**; Developers có trách nhiệm làm rõ giải pháp và kích thước. Hai bên cùng cân nhắc khi sắp thứ tự.

## 7. Tạo và truyền đạt Product Backlog items rõ ràng

Product Owner chịu trách nhiệm **tạo và truyền đạt rõ các PBI**, nhưng người thực hiện phần mô tả có thể là người khác khi được giao. Điều cần có là nhóm hiểu vấn đề, giá trị, phạm vi và thông tin cần thiết cho quyết định tiếp theo.

### 7.1. Sử dụng user story khi phù hợp

Mẫu phổ biến:

> Là [người dùng], tôi muốn [hành vi/nhu cầu], để [lợi ích].

Ví dụ:

> **Là học viên đã gửi đăng ký**, tôi muốn **xem trạng thái yêu cầu thuộc về mình**, để **biết còn phải chờ hay đã được xác nhận mà không phải nhắn lại ban tổ chức**.

Một story chỉ là **điểm neo của cuộc trao đổi**, không phải hợp đồng bất biến. Nhóm cần hỏi: những trạng thái nào tồn tại, ai được xem yêu cầu nào, khi nào chỗ được xác nhận, trường hợp mạng lỗi thì sao?

### 7.2. Tiêu chí chấp nhận giúp thống nhất hành vi

Với story trên, một số tình huống có thể là:

~~~gherkin
Tính năng: Xem trạng thái đăng ký workshop

  Tình huống: Học viên xem yêu cầu của mình
    Cho trước học viên có quyền xem yêu cầu đã gửi
    Khi học viên mở chi tiết đăng ký
    Thì hệ thống hiển thị đúng trạng thái hiện tại
    Và giải thích rõ bước tiếp theo nếu còn chờ xử lý

  Tình huống: Người dùng không có quyền
    Cho trước người dùng không có quyền xem đăng ký X
    Khi người đó cố truy cập đăng ký X
    Thì hệ thống không tiết lộ thông tin riêng tư của đăng ký X

  Tình huống: Yêu cầu chưa được xác nhận chỗ
    Cho trước điều phối viên chưa duyệt yêu cầu
    Khi học viên xem trạng thái
    Thì giao diện không khẳng định đã giữ chỗ thành công
~~~

Các tình huống trên là **minh họa**, không phải hợp đồng hệ thống thật. Quy tắc xác thực, phân quyền, giữ chỗ và cập nhật trạng thái cần được xác nhận với bên có trách nhiệm nghiệp vụ và kỹ thuật.

### 7.3. Acceptance criteria không thay thế Definition of Done

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| **Acceptance criteria** | Làm rõ hành vi mong muốn của một PBI cụ thể | Học viên không thể xem thông tin đăng ký của người khác |
| **Definition of Done** | Mô tả trạng thái chất lượng để Increment được xem là hoàn tất | Mã tích hợp, kiểm thử phù hợp đạt, bảo mật và chất lượng được kiểm tra theo chuẩn nhóm |

Một PBI có thể được phát triển gần xong nhưng **chưa đạt DoD**, vì vậy không được coi là một phần Increment hoàn tất. Product Owner không nên hứa “đã bàn giao” chỉ vì màn hình đã được trình diễn trong môi trường của lập trình viên.

### 7.4. Refinement là hoạt động liên tục, không phải sự kiện bắt buộc riêng

**Product Backlog refinement** là việc chia nhỏ và định nghĩa thêm các hạng mục, bao gồm mô tả, thứ tự, kích thước khi phù hợp. Scrum không quy định một sự kiện refinement cố định với thời lượng bắt buộc.

Trong refinement:

- Product Owner giúp làm rõ **vì sao** mục quan trọng và lợi ích với người dùng.
- Developers đặt câu hỏi về phạm vi, rủi ro, khả năng thực hiện và **chịu trách nhiệm về sizing** các PBIs.
- Product Owner có thể ảnh hưởng đến cách sizing qua làm rõ các đánh đổi; điều đó không có nghĩa Product Owner tự quyết định số điểm.
- Những bên liên quan hiểu nghiệp vụ có thể tham gia để xác nhận trường hợp đặc biệt, nhưng không biến cuộc họp thành nơi nhiều người đồng thời thay đổi ưu tiên.
- Nhóm chia hạng mục lớn thành lát cắt có ích, có thể kiểm chứng và đáp ứng DoD.

Hạng mục ở xa có thể chưa chi tiết; những mục gần được chọn cần hiểu đủ. **Không cần hoàn thiện toàn bộ backlog từ đầu**, vì Product Backlog phát triển khi nhóm học thêm.

## 8. Minh bạch, dễ thấy và được hiểu nghĩa là gì?

Một công cụ backlog hiển thị cho mọi người **chưa đủ minh bạch** nếu các thẻ chứa thuật ngữ khó hiểu, thiếu lý do ưu tiên hoặc dùng các trạng thái không thống nhất.

### 8.1. Những điều người tham gia nên tìm được

| Câu hỏi | Bằng chứng minh bạch |
| --- | --- |
| Product Goal hiện nay là gì? | Phát biểu mục tiêu được chia sẻ và được giải thích nhất quán |
| Vì sao hạng mục này đứng trên hạng mục khác? | Giá trị, rủi ro, phụ thuộc hoặc phản hồi được liên kết |
| Người dùng nào sẽ nhận giá trị? | Vai trò, bối cảnh và kết quả mong muốn |
| Điều gì còn chưa chắc? | Giả định, câu hỏi mở, rủi ro và người cần xác nhận |
| Hạng mục nào đã hoàn tất? | Trạng thái theo DoD và liên kết Increment thực tế |
| Có phản hồi mới cần thay đổi thứ tự không? | Quyết định mới, nguồn thông tin và thời điểm kiểm tra lại |
| Ai chịu trách nhiệm ra quyết định ưu tiên? | Product Owner được xác định rõ và có quyền thực hiện trách nhiệm |

Minh bạch không có nghĩa công khai dữ liệu khách hàng hay thông tin bí mật cho bất kỳ ai. Các bên cần **quyền truy cập phù hợp** nhưng vẫn hiểu trạng thái và cơ sở ra quyết định.

### 8.2. Làm rõ sự khác biệt giữa backlog và cam kết phát hành

Không nên nói “nằm trong backlog” nghĩa là chắc chắn được làm. Một PBI có thể được bổ sung để theo dõi một giả thuyết chưa đủ bằng chứng, rồi bị thay thế hoặc loại khỏi thứ tự ưu tiên.

Gợi ý cách phản hồi stakeholder:

> “Chúng tôi đã ghi nhận nhu cầu báo cáo số người tham gia. Hiện backlog ưu tiên tính đúng đắn của đăng ký và trạng thái rõ ràng theo Product Goal. Chúng tôi cần ví dụ đối soát thực tế để đánh giá báo cáo và sẽ xem lại khi có dữ liệu đó.”

Cách nói này **công nhận phản hồi**, giải thích mục tiêu và giữ cơ hội thay đổi quyết định mà không hứa một thời hạn chưa có căn cứ.

### 8.3. Tránh duy trì nhiều backlog cạnh tranh

Nếu có “backlog chính”, “danh sách ưu tiên của sếp”, “danh sách việc kỹ thuật riêng” và “những việc xin qua tin nhắn” nhưng không được liên kết, Scrum Team khó thấy một nguồn công việc đáng tin cậy.

Thông tin có thể đến từ nhiều kênh, nhưng những phần việc mà Scrum Team sẽ thực hiện cho sản phẩm cần được phản ánh qua Product Backlog theo chính sách phù hợp. Khi có sự cố cần xử lý khẩn, nhóm phải theo quy trình ứng phó rồi minh bạch tác động lên công việc; không cần trì hoãn bảo vệ người dùng chỉ để chờ buổi refinement.

## 9. Ranh giới cộng tác giữa Product Owner, Developers và Scrum Master

Ba accountability của Scrum không tạo ra ba phòng ban độc lập. Đây là **một Scrum Team** gồm các thành viên phối hợp để tạo Increment có giá trị.

| Tình huống | Product Owner | Developers | Scrum Master |
| --- | --- | --- | --- |
| **Chọn trạng thái sản phẩm cần hướng tới** | Chịu trách nhiệm phát triển/truyền đạt Product Goal và tối đa hóa giá trị | Đóng góp hiểu biết kỹ thuật, rủi ro, cơ hội sản phẩm | Giúp Scrum Team hiểu Scrum và cải thiện cách cộng tác |
| **Sắp thứ tự Product Backlog** | Chịu trách nhiệm cuối cùng về thứ tự | Tư vấn phụ thuộc, rủi ro và phạm vi có thể giao | Hỗ trợ minh bạch và cách làm việc hiệu quả |
| **Làm rõ PBI** | Chịu trách nhiệm nội dung dễ hiểu, giá trị và thứ tự | Đặt câu hỏi, phân rã, sizing và chỉ ra rủi ro | Giúp nhóm cải thiện refinement khi cần |
| **Lập kế hoạch Sprint** | Đề xuất cách tăng giá trị, làm rõ các PBIs quan trọng | Chọn công việc khả thi, xây Sprint Backlog và kế hoạch | Bảo đảm sự kiện có hiệu quả theo Scrum |
| **Trong Sprint** | Sẵn sàng làm rõ và thương lượng phạm vi khi cần | Chủ động điều chỉnh kế hoạch hướng tới Sprint Goal, giữ DoD | Giúp nhóm tự quản lý, loại bỏ cản trở |
| **Sprint Review** | Trao đổi giá trị, cập nhật Product Backlog dựa trên phản hồi | Trình bày/kiểm tra Increment cùng stakeholder | Hỗ trợ một buổi kiểm tra và thích ứng hiệu quả |
| **Cải tiến quy trình** | Phối hợp cải tiến giá trị và chất lượng làm việc | Phản ánh vấn đề kỹ thuật và dòng công việc | Chịu trách nhiệm thiết lập hiệu quả Scrum Team |

### 9.1. Sizing là trách nhiệm của Developers

Nếu PBI còn mơ hồ, Developers có thể nói: “Chúng tôi chưa đủ thông tin để ước lượng đáng tin; cần biết trường hợp đăng ký trùng xảy ra thế nào”. Product Owner giúp làm rõ giá trị, phạm vi, điều kiện nghiệp vụ; Developers đánh giá kích thước và cách thực hiện.

Không nên suy ra “Product Owner quyết định thứ tự” nên “Product Owner cũng quyết định Developers phải ước lượng bao nhiêu points”.

### 9.2. Sắp thứ tự không đồng nghĩa can thiệp Sprint Backlog theo giờ

Product Owner có thể điều chỉnh Product Backlog khi có bằng chứng mới. Nhưng **Sprint Backlog là kế hoạch của Developers**, được cập nhật trong Sprint. Nếu phát sinh điều cần đổi, Product Owner và Developers trao đổi về phạm vi để giữ Sprint Goal; Product Owner không đơn phương biến Sprint thành danh sách nhiệm vụ mới.

### 9.3. Product Owner và Scrum Master không thay thế nhau

Scrum Master giúp mọi người hiểu Scrum, hỗ trợ Product Owner quản lý Product Backlog hiệu quả và thúc đẩy hợp tác với stakeholder khi cần. Scrum Master **không mặc nhiên ra quyết định ưu tiên thay Product Owner**. Ngược lại, Product Owner không cần tự tổ chức mọi hoạt động hỗ trợ quy trình; nên phối hợp với Scrum Master để tháo gỡ cản trở ở cấp nhóm và tổ chức.

## 10. Truyền đạt Product Goal qua các sự kiện Scrum

### 10.1. Sprint Planning: từ Product Goal đến một Sprint Goal có giá trị

Một câu hỏi trong Sprint Planning là **“Vì sao Sprint này có giá trị?”** Product Owner đề xuất cách sản phẩm có thể tăng giá trị và tiện ích trong Sprint. **Toàn bộ Scrum Team cùng xác định Sprint Goal** trước khi kết thúc Sprint Planning.

Ví dụ:
- Product Goal: học viên tự đăng ký và hiểu trạng thái; ban tổ chức tránh trùng chỗ.
- Product Owner nêu phản hồi: học viên gửi yêu cầu nhưng không biết chỗ đã được xác nhận.
- Developers trình bày khả năng: có thể hoàn tất luồng “gửi yêu cầu + trạng thái rõ” cùng kiểm thử chỗ trong Sprint.
- Sprint Goal thống nhất: “Một học viên thử nghiệm gửi yêu cầu và biết nó đang chờ hay đã được xác nhận mà không cần giải thích riêng.”

Các PBIs được chọn, cùng kế hoạch thực hiện, hình thành **Sprint Backlog**. Sprint Goal không chỉ là tổng story points.

### 10.2. Daily Scrum: Developers kiểm tra tiến độ về Sprint Goal

**Daily Scrum** dành cho Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần. Product Owner không dùng Daily Scrum để yêu cầu từng người báo cáo công việc cho mình.

Nếu Product Owner đồng thời đang làm công việc như một Developer trong Sprint, họ tham gia với vai trò đó. Điều quan trọng là sự kiện hỗ trợ tự quản lý của Developers, không trở thành một buổi kiểm soát vi mô.

### 10.3. Sprint Review: kiểm tra Increment và hướng đi sản phẩm

Sprint Review không chỉ là trình diễn vài màn hình hoặc báo cáo những ticket đã đóng. Scrum Team cùng bên liên quan **kiểm tra kết quả Sprint và tiến triển hướng đến Product Goal**, thảo luận điều đã thay đổi trong môi trường kinh doanh/sản phẩm và cân nhắc thích ứng.

Một luồng Review hiệu quả có thể:
1. Nhắc lại **Product Goal** và Sprint Goal.
2. Quan sát Increment đã đạt **Definition of Done**.
3. Xem phản hồi người dùng, số liệu chất lượng, vấn đề mới và giả định được kiểm chứng hoặc bác bỏ.
4. Thảo luận **những việc nào tiếp theo có thể tạo giá trị cao hơn**.
5. Cập nhật Product Backlog khi phù hợp.

Nếu tính năng đã hoạt động nhưng người dùng vẫn phải gọi hỏi trạng thái, Product Owner cần xem xét ưu tiên sửa thông báo hoặc quy trình thay vì chỉ tuyên bố “story đã Done”.

### 10.4. Sprint Retrospective: cải thiện khả năng cùng giao giá trị

Retrospective tập trung vào cách Scrum Team cải thiện chất lượng và hiệu quả. Có thể kiểm tra: PBI có thường mơ hồ không, quyết định ưu tiên có bị đổi qua tin nhắn riêng không, người liên quan có hiểu Product Goal không, Developers có gặp phụ thuộc không được xử lý không?

Ví dụ hành động: thử một định dạng làm rõ PBI theo người dùng – nhu cầu – lợi ích và trường hợp chấp nhận trước khi chọn vào Sprint; cuối Sprint sau kiểm tra xem số việc phải chờ xác nhận nghiệp vụ có giảm không.

### 10.5. Product Goal có thể đổi trong hoàn cảnh nào?

Scrum Team theo đuổi một Product Goal tại một thời điểm cho đến khi **hoàn thành hoặc từ bỏ** nó. Nếu cơ hội sản phẩm biến mất, quy định thay đổi hoặc có bằng chứng khách hàng không còn nhu cầu, Product Owner cần cùng nhóm và stakeholder đánh giá có nên từ bỏ Product Goal hiện tại để chọn mục tiêu khác.

Đừng âm thầm thay Product Goal mỗi khi có một yêu cầu mới. Ngược lại, đừng cố giữ mục tiêu cũ chỉ vì đã viết thành slide. Sự thay đổi cần được **giải thích công khai bằng bằng chứng và quyết định**.

## 11. Tình huống: Product Owner xử lý xung đột ưu tiên

### 11.1. Bối cảnh và các đề xuất

Nhóm phát triển sản phẩm workshop. Product Goal hiện tại là giúp học viên tự đăng ký và theo dõi kết quả chính xác, giảm trao đổi thủ công.

Có bốn yêu cầu xuất hiện cùng tuần:

1. **Bộ phận marketing:** thêm giao diện trang chủ có hiệu ứng đẹp để quảng bá sự kiện.
2. **Điều phối viên:** sửa lỗi có thể xác nhận hai người vào cùng một suất cuối.
3. **Học viên dùng thử:** thông báo “đã tiếp nhận” gây hiểu nhầm rằng đã có chỗ.
4. **Bộ phận tài chính:** xuất bảng kê doanh thu theo giảng viên, nhưng chưa rõ cách sử dụng và kỳ báo cáo.

Nếu Product Owner chỉ hỏi “ai cần trước?”, cuộc thảo luận dễ bị chi phối bởi chức danh hoặc độ lớn tiếng. Cần quay lại Product Goal và các rủi ro cụ thể.

### 11.2. Bảng quyết định minh họa

| Yêu cầu | Liên hệ Product Goal | Bằng chứng/tác động | Quyết định ban đầu |
| --- | --- | --- | --- |
| Lỗi xác nhận trùng | Trực tiếp ảnh hưởng tính đúng đắn | Có khả năng khiến học viên nhận thông tin sai | Điều tra mức nghiêm trọng, khắc phục và kiểm chứng sớm; khẩn cấp nếu đang ảnh hưởng thực tế |
| Thông báo trạng thái khó hiểu | Trực tiếp ảnh hưởng khả năng tự đăng ký | Phản hồi dùng thử cụ thể | Ưu tiên cải thiện thông điệp và thử lại |
| Hiệu ứng trang chủ | Gián tiếp, chưa thấy vấn đề hiện tại | Chưa có bằng chứng giúp người dùng hoàn tất đăng ký | Trì hoãn hoặc yêu cầu thử nghiệm giá trị |
| Báo cáo tài chính | Có thể có giá trị riêng nhưng chưa rõ kết nối mục tiêu | Thiếu ví dụ nghiệp vụ và ràng buộc thời gian | Làm rõ trước khi quyết định vị trí ưu tiên |

Đây là **đánh giá dựa trên bối cảnh giả định**, không phải quy tắc Product Owner luôn phải chọn lỗi trước mọi thứ. Nếu có ràng buộc pháp lý với báo cáo tài chính hoặc điều kiện hợp đồng, thứ tự có thể khác. Quan trọng là **lý do được ghi nhận và có thể xem lại**.

### 11.3. Trao đổi với các bên liên quan

Product Owner có thể nói:

> “Product Goal hiện tại là học viên tự đăng ký và nhận kết quả đáng tin. Rủi ro xác nhận trùng cùng phản hồi về trạng thái trực tiếp ảnh hưởng mục tiêu đó, nên chúng tôi kiểm tra và xử lý trước. Đề xuất giao diện quảng bá và báo cáo tài chính đã được ghi nhận; tôi cần tình huống sử dụng, thời hạn thật và tác động nếu trì hoãn để sắp thứ tự phù hợp. Khi có bằng chứng mới, chúng ta sẽ xem lại quyết định.”

Lời giải thích vừa rõ **điều ưu tiên**, vừa chỉ ra **điều chưa cam kết** và **điều kiện thay đổi quyết định**. Product Owner không phải luôn đồng ý với mọi yêu cầu mới để thể hiện sự hợp tác.

### 11.4. Nếu việc khẩn xuất hiện trong Sprint

Giả sử Developers đang thực hiện một lát cắt gửi đăng ký thì phát hiện lỗi có thể xác nhận vượt số chỗ đang ảnh hưởng dữ liệu thật. Cần thực hiện quy trình xử lý sự cố phù hợp để bảo vệ người dùng và dữ liệu, đồng thời Product Owner và Developers trao đổi tác động lên Sprint Goal, phạm vi và công việc còn lại.

- **Không tự ý yêu cầu “làm thêm việc” nhưng giữ nguyên mọi cam kết**, vì năng lực có hạn.
- **Không bỏ qua DoD**, kiểm thử hoặc quy tắc bảo mật để đưa lỗi vào trạng thái Done cho kịp.
- **Không trì hoãn xử lý rủi ro nghiêm trọng** chỉ vì việc đó chưa có trong Product Backlog đầu Sprint.
- **Minh bạch** phần công việc bị hoãn, người chịu ảnh hưởng và cách nhóm kiểm chứng kết quả.

Nếu Sprint Goal trở nên lỗi thời do thay đổi căn bản, **Product Owner có thẩm quyền hủy Sprint** theo Scrum. Đây là trường hợp đặc biệt, không phải giải pháp thường dùng mỗi khi có yêu cầu mới.

## 12. Dùng bằng chứng để biết Product Goal đang được tiến gần

### 12.1. Đầu ra không tự bằng kết quả người dùng

| Mức quan sát | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Hoạt động (activity)** | Refinement, lập trình, review mã | Nhóm đã làm việc |
| **Đầu ra (output)** | Phát hành trang đăng ký, thêm API trạng thái | Sản phẩm có khả năng mới |
| **Kết quả (outcome)** | Học viên tự hoàn tất và hiểu trạng thái, ít hỏi lại | Hành vi hoặc lợi ích người dùng thay đổi |
| **Tác động (impact)** | Công điều phối giảm, người tham gia nhận dịch vụ đáng tin hơn | Giá trị rộng hơn cần quan sát theo thời gian |

Velocity, số story hoàn tất hay throughput có thể giúp theo dõi **khả năng hoàn tất công việc**. Nhưng chúng không tự chứng minh Product Goal đã đạt. Product Owner cần nhìn cả khả năng sản phẩm được sử dụng đúng, chất lượng và lợi ích được quan sát.

### 12.2. Ví dụ dữ liệu giả định

Trước khi cải thiện thông báo trạng thái, nhóm thử với 20 học viên; sau thay đổi thử lại với 20 học viên khác có bối cảnh gần giống:

| Tín hiệu | Trước | Sau | Diễn giải ban đầu |
| --- | ---: | ---: | --- |
| Hoàn tất gửi đăng ký | 12/20 | 17/20 | Tăng từ 60% lên 85% trong mẫu |
| Hiểu đúng “chờ xác nhận” | 8/20 | 16/20 | Tăng từ 40% lên 80% trong mẫu |
| Phải hỏi lại ban tổ chức | 9/20 | 4/20 | Giảm từ 45% xuống 20% trong mẫu |
| Lỗi xác nhận trùng ghi nhận | 1 | 0 | Tín hiệu tích cực, nhưng mẫu nhỏ không chứng minh rủi ro đã hết |

**Toàn bộ dữ liệu là giả định để học cách đánh giá**, không phải kết quả thực tế. Những khác biệt cho thấy tín hiệu đáng kiểm tra; chúng chưa chứng minh nguyên nhân duy nhất là thay đổi giao diện. Cần xem cách chọn người dùng, quy tắc đo và các thay đổi xảy ra cùng lúc.

Một Product Owner có thể sử dụng phát hiện này để ưu tiên mở rộng dùng thử có kiểm soát, đồng thời yêu cầu kiểm thử bảo vệ dữ liệu và tiếp tục nghiên cứu những trường hợp chưa hiểu trạng thái.

### 12.3. Chỉ số sản phẩm và chỉ số dòng công việc phục vụ những câu hỏi khác nhau

| Loại bằng chứng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Kết quả người dùng** | Product Goal có đang tạo ích lợi không? | Tỷ lệ hoàn tất, hiểu đúng trạng thái, số lần hỏi lại |
| **Chất lượng** | Lợi ích có đi kèm độ tin cậy không? | Lỗi, sự cố, sai quyền, trường hợp xác nhận trùng |
| **Dòng công việc** | Nhóm giao Increment có ổn định và học nhanh không? | Cycle time, throughput, work item age, WIP |
| **Mức độ học được** | Giả định nào đã được xác minh hoặc bác bỏ? | Kết quả dùng thử, phỏng vấn, thí nghiệm nhỏ |
| **Giá trị rộng hơn** | Sản phẩm có hỗ trợ mục tiêu tổ chức không? | Công điều phối, khả năng phục vụ, chi phí phù hợp |

Mỗi chỉ số cần định nghĩa rõ mẫu số, kỳ quan sát, nguồn và giới hạn. **Đừng biến Product Goal thành bảng KPI không có ý nghĩa với người dùng**, cũng đừng bỏ qua chất lượng chỉ vì một chỉ số trải nghiệm tăng.

### 12.4. Product Goal đạt hay chưa?

Nên xác định **bằng chứng đủ để ra quyết định** theo bối cảnh. Ví dụ, nhóm có thể cần xác nhận luồng đăng ký hoạt động an toàn, phần lớn người thử hiểu kết quả, điều phối viên xử lý chỗ đúng và không có rủi ro nghiêm trọng chưa kiểm soát trong phạm vi đưa vào sử dụng.

Không nên tuyên bố hoàn thành chỉ vì toàn bộ backlog ban đầu được đánh dấu Done, vì backlog có thể chứa ý tưởng thừa và thiếu nhu cầu mới. Ngược lại, Product Goal có thể đạt trước khi mọi đề xuất tính năng được xây dựng. **Mục tiêu là trạng thái sản phẩm có giá trị**, không phải số lượng hạng mục.

## 13. Những sai lầm phổ biến khi quản lý Product Goal và Product Backlog

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Product Goal là khẩu hiệu hoặc danh sách tính năng | Nhóm không có định hướng giá trị rõ | Viết trạng thái sản phẩm tương lai và cách kiểm chứng |
| Product Owner chỉ đóng vai “người ghi ticket” | Thứ tự phản ánh người yêu cầu gần nhất, không phản ánh giá trị | Nhận trách nhiệm về Product Goal, thứ tự và quyết định |
| Có nhiều “Product Owner” cùng quyết định mâu thuẫn | Developers không biết theo ưu tiên nào | Xác định một Product Owner chịu trách nhiệm, cơ chế lắng nghe stakeholder |
| Product Owner tự quyết định điểm ước lượng | Kế hoạch thiếu thực tế; Developers mất quyền tự quản lý | Developers chịu trách nhiệm sizing, PO làm rõ giá trị và đánh đổi |
| Xem backlog là hợp đồng mọi tính năng sẽ được xây | Không thể thích ứng khi học điều mới | Công khai rằng backlog có thứ tự và liên tục phát triển |
| Tất cả hạng mục đều “ưu tiên cao” | Không thể chọn khi thiếu năng lực | Ra quyết định thứ tự có lý do và sẵn sàng bỏ bớt |
| Đánh đồng story đạt acceptance criteria một phần với Increment hoàn tất | Tuyên bố giao hàng sớm sai thực tế | Áp dụng Definition of Done nhất quán |
| Chỉ cập nhật backlog trước Sprint Planning | Phản hồi bị bỏ quên, story trở nên cũ | Refinement liên tục và xem lại sau khi có bằng chứng mới |
| Product Owner can thiệp từng task của Developers | Nhóm mất tự quản lý, tập trung vào báo cáo thay vì Sprint Goal | Trao đổi mục tiêu và phạm vi; để Developers lập kế hoạch thực hiện |
| Sprint Review chỉ trình bày velocity và màn hình | Không kiểm tra giá trị hay tiến triển Product Goal | Dùng Increment và phản hồi bên liên quan để quyết định tiếp theo |
| Luôn chọn việc theo yêu cầu người có chức danh cao | Có thể bỏ qua rủi ro hoặc nhu cầu người dùng quan trọng | So sánh giá trị, chi phí trì hoãn, rủi ro và bằng chứng |
| Không nói rõ lý do hoãn hoặc đóng yêu cầu | Stakeholder mất tin cậy; cùng yêu cầu được gửi nhiều lần | Liên kết phản hồi, giải thích quyết định và điều kiện xem lại |
| Đổi Product Goal liên tục để phù hợp mọi đề xuất | Không có định hướng đủ dài để kiểm tra kết quả | Hoàn thành hoặc từ bỏ mục tiêu hiện tại có chủ đích trước khi chọn mục tiêu mới |

Những vấn đề trên không được giải quyết chỉ bằng một cuộc họp dài hơn. Nhóm cần **trách nhiệm minh bạch, quyền quyết định thực sự, thông tin đáng tin cậy và cơ hội kiểm tra kết quả sau mỗi Increment**.

## 14. Bài thực hành: làm Product Owner trong một phiên ưu tiên

### 14.1. Bối cảnh

Một Scrum Team gồm một Product Owner, một Scrum Master và các Developers đang xây ứng dụng hỗ trợ đăng ký workshop. Các stakeholder gồm học viên, điều phối viên, marketing và bộ phận tài chính.

**Product Goal hiện tại:**

> Học viên có thể tự đăng ký workshop còn chỗ và hiểu kết quả; điều phối viên có thể xác nhận đúng số chỗ mà không phải xử lý thủ công những tình huống thông thường.

Danh sách dưới đây là **dữ liệu giả định**:

| Mã | Yêu cầu | Nguồn | Bằng chứng hiện có |
| --- | --- | --- | --- |
| A | Hiển thị trạng thái sau khi gửi đăng ký | Học viên thử nghiệm | 7/10 người hỏi lại “đã có chỗ chưa?” |
| B | Hiệu ứng mới trên trang giới thiệu | Marketing | Chưa có thử nghiệm |
| C | Kiểm thử và sửa lỗi xác nhận hai người vào một suất cuối | Điều phối viên | Lỗi tái hiện trong môi trường thử |
| D | Xuất bảng kê doanh thu theo giảng viên | Tài chính | Chưa rõ kỳ báo cáo và hậu quả nếu trễ |
| E | Tự hủy đăng ký trước hạn | Học viên cũ | Hai cuộc phỏng vấn đề cập |
| F | Tối ưu môi trường CI để kiểm thử đăng ký đáng tin cậy | Developers | Thỉnh thoảng pipeline lỗi, làm chậm xác nhận |

### 14.2. Nhiệm vụ A – Diễn giải Product Goal (10 phút)

1. Gạch chân **đối tượng**, **năng lực sản phẩm** và **giá trị mong muốn** trong Product Goal.
2. Nêu ba tín hiệu để biết mục tiêu đang tiến gần; ít nhất một tín hiệu phản ánh chất lượng.
3. Chỉ ra một điều **không phải** Product Goal, ví dụ “đóng 30 tickets” hoặc “đạt 50 points/Sprint”.
4. Thử yêu cầu một thành viên khác diễn giải lại mục tiêu bằng ví dụ người dùng.

### 14.3. Nhiệm vụ B – Sắp thứ tự Product Backlog (15 phút)

Với sáu yêu cầu A–F:

1. Đề xuất thứ tự từ sớm đến muộn theo Product Goal, giá trị, rủi ro và phụ thuộc.
2. Giải thích vì sao **C** có thể cần ưu tiên sớm nếu rủi ro xác nhận trùng có thật.
3. Nêu thông tin còn thiếu trước khi quyết định vị trí của **D**.
4. Phân biệt việc **B** là một đề xuất giải pháp với việc người dùng có thật sự gặp vấn đề.
5. Quyết định F là công việc chất lượng nên xử lý trong lát cắt liên quan hay PBI riêng, và vì sao.

**Không có một thứ tự duy nhất đúng cho mọi bối cảnh.** Bài làm cần thể hiện lập luận, hậu quả của trì hoãn và điều kiện có thể khiến quyết định đổi.

### 14.4. Nhiệm vụ C – Trao đổi với Developers (15 phút)

Developers nêu ba thông tin:
- Hạng mục A cần được chia để có thể kiểm thử trong Sprint.
- Hạng mục C có tình huống đồng thời khó, cần làm rõ quy tắc xác nhận.
- Hạng mục F có thể giúp giảm lỗi pipeline nhưng cần kiểm tra phạm vi ảnh hưởng.

Hãy tổ chức cuộc trao đổi ngắn: Product Owner làm rõ **vì sao** ưu tiên; Developers xác định **những lát cắt khả thi, sizing và rủi ro kỹ thuật**. Viết một Sprint Goal đề xuất dựa trên năng lực thực tế, không chỉ cộng story points.

### 14.5. Nhiệm vụ D – Phản hồi stakeholder (10 phút)

Đóng vai Product Owner, viết hai thông điệp:

- Cho marketing: giải thích tại sao B chưa được đặt trước A/C, bằng chứng nào có thể thay đổi quyết định.
- Cho tài chính: hỏi thông tin cần xác nhận về D mà không mặc định yêu cầu của họ vô giá trị.

Mỗi thông điệp cần có **mục tiêu sản phẩm, quyết định hiện tại, lý do, điều chưa biết và bước xem lại**.

### 14.6. Nhiệm vụ E – Kiểm tra kết quả sau một Sprint (10 phút)

Nhóm đã giao lát cắt hiển thị trạng thái có DoD. Trong đợt thử mới với 10 học viên:
- 9 người gửi đăng ký hoàn tất.
- 7 người hiểu đúng sự khác biệt giữa “đã tiếp nhận” và “đã xác nhận”.
- 3 người vẫn phải hỏi lại ban tổ chức.
- Không phát hiện lỗi xác nhận trùng trong 10 lượt thử, nhưng nhóm chưa kiểm thử đủ tình huống đồng thời.

Hãy trả lời:

1. Điều gì đã có bằng chứng tích cực về Product Goal?
2. Điều gì chưa thể kết luận từ mười lượt thử?
3. Product Backlog nên điều chỉnh hạng mục nào trước?
4. Product Owner cần trao đổi thêm với Developers và người dùng về điều gì?
5. Nhóm cần làm rõ điều kiện nào trước khi tuyên bố Product Goal đạt?

**Gợi ý:** 7/10 hiểu đúng là tín hiệu bước đầu, không chứng minh mọi học viên đều hiểu. Không gặp lỗi trong mười lượt thử không chứng minh xử lý cạnh tranh đã an toàn. Product Owner có thể ưu tiên cải thiện thông báo và bảo vệ dữ liệu trước khi mở rộng tính năng phụ.

### 14.7. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Hiểu Product Goal** | Chỉ liệt kê tính năng | Mô tả được trạng thái sản phẩm mong muốn | Gắn với người dùng, rủi ro và bằng chứng kiểm chứng |
| **Hiểu trách nhiệm PO** | Cho rằng PO giao mọi task hoặc nhiều người cùng quyết định | Nêu đúng bốn trách nhiệm quản lý Product Backlog | Phân biệt ủy quyền và accountability, biết hợp tác với Developers |
| **Sắp thứ tự** | Chọn theo chức danh người gửi | Giải thích dựa trên giá trị, rủi ro và mục tiêu | Nêu đánh đổi, thông tin còn thiếu và điều kiện thay đổi quyết định |
| **Cộng tác Scrum** | Nhầm Sprint Backlog là kế hoạch do PO áp đặt | Tôn trọng sizing và kế hoạch của Developers | Kết hợp Sprint Goal, DoD, refinement và phản hồi stakeholder |
| **Kiểm tra giá trị** | Chỉ đếm story/points | Dùng tín hiệu kết quả và chất lượng | Diễn giải giới hạn dữ liệu và cập nhật backlog có căn cứ |

## 15. Biểu mẫu áp dụng ngay

### 15.1. Phiếu Product Goal

~~~text
SẢN PHẨM / RANH GIỚI:
Người dùng chính:
Vấn đề hoặc cơ hội đã xác minh:
Trạng thái tương lai mong muốn:
Giá trị với người dùng và tổ chức:
Những điều phải bảo vệ (chất lượng, quyền, dữ liệu):
Bằng chứng và giả định hiện có:
Tín hiệu để kiểm tra tiến triển:
Điều chưa chắc và cần thử:
Product Owner chịu trách nhiệm:
Ngày thảo luận với Scrum Team / stakeholder:
Điều kiện xem lại / hoàn thành / từ bỏ Product Goal:
~~~

### 15.2. Phiếu ra quyết định ưu tiên PBI

~~~text
Mã PBI:
Người dùng / vấn đề:
Kết quả mong muốn:
Liên hệ với Product Goal:
Tác động nếu trì hoãn:
Rủi ro và điều kiện an toàn:
Bằng chứng / phản hồi:
Phụ thuộc và câu hỏi kỹ thuật:
Lát cắt giá trị có thể giao trước:
Thứ tự hiện tại và lý do:
Ai chịu trách nhiệm quyết định thứ tự:
Ý kiến Developers / stakeholder:
Bằng chứng nào khiến thứ tự đổi:
Khi nào kiểm tra lại:
~~~

### 15.3. Mẫu giải thích quyết định cho stakeholder

~~~text
Nhu cầu của bên liên quan:
Điều chúng tôi hiểu về giá trị mong muốn:
Product Goal hiện tại:
Quyết định ưu tiên lúc này:
Bằng chứng và rủi ro đã cân nhắc:
Điều sẽ bị ảnh hưởng nếu đưa yêu cầu lên cao:
Thông tin còn thiếu:
Lần xem lại / điều kiện thay đổi quyết định:
Người liên hệ để bổ sung bằng chứng:
~~~

Không cần biến các mẫu này thành thủ tục hành chính bắt buộc cho mọi câu hỏi nhỏ. Chúng chỉ hữu ích khi giúp **người liên quan hiểu mục tiêu, lập luận và quyết định**.

## 16. Checklist quản lý Product Backlog và truyền đạt Product Goal

**Về Product Goal:**

- [ ] Scrum Team biết Product Goal hiện tại là trạng thái sản phẩm tương lai nào.
- [ ] Product Goal gắn với đối tượng người dùng và giá trị thực tế, không chỉ danh sách chức năng.
- [ ] Đã phân biệt Product Goal với Sprint Goal và các chỉ tiêu output như story points.
- [ ] Nhóm hiểu tín hiệu và giới hạn dữ liệu dùng để kiểm tra tiến triển.
- [ ] Có cách công khai quyết định khi Product Goal hoàn thành hoặc cần từ bỏ.

**Về Product Backlog:**

- [ ] Product Owner chịu trách nhiệm về Product Goal, mô tả PBI, thứ tự và sự minh bạch của backlog.
- [ ] Các nhiệm vụ được ủy quyền vẫn có một Product Owner chịu trách nhiệm cuối cùng.
- [ ] Product Backlog có thứ tự có lý do, không chỉ các nhãn ưu tiên chung chung.
- [ ] Những hạng mục gần được làm rõ bằng câu hỏi, ví dụ và tiêu chí chấp nhận phù hợp.
- [ ] Developers tham gia refinement, nhận diện rủi ro và chịu trách nhiệm sizing.
- [ ] Công việc kỹ thuật và chất lượng được cân nhắc theo giá trị/rủi ro, không bị ép viết user story giả.
- [ ] Nhu cầu cũ, trùng hoặc mới phát sinh được cập nhật và liên kết minh bạch.
- [ ] Không xem mọi PBI trong backlog là lời hứa sẽ phát hành.

**Về cộng tác và kiểm tra kết quả:**

- [ ] Product Owner lắng nghe stakeholder nhưng không để nhiều người ra các quyết định ưu tiên mâu thuẫn.
- [ ] Sprint Planning xuất phát từ giá trị và tạo một Sprint Goal rõ.
- [ ] Developers tự quản lý Sprint Backlog, Product Owner không phân công chi tiết từng task.
- [ ] Increment được đánh giá theo Definition of Done, không chỉ theo tiến độ lập trình.
- [ ] Sprint Review kiểm tra kết quả và tiến triển đến Product Goal cùng các bên liên quan.
- [ ] Phản hồi người dùng, chất lượng và dữ liệu dòng công việc được dùng để điều chỉnh thứ tự Product Backlog.
- [ ] Khi ưu tiên thay đổi, nhóm giải thích điều gì phải lùi và vì sao.
- [ ] Mọi bên hiểu rằng Product Backlog có thể thích ứng với bằng chứng mới.

**Kết luận:** Product Owner không chỉ “quản lý danh sách ticket”. Người đảm nhiệm trách nhiệm này cần **giữ một Product Goal được hiểu chung**, làm cho **Product Backlog có thứ tự, minh bạch và dễ hiểu**, và cùng Scrum Team kiểm tra giá trị của những Increment được giao. Khi mục tiêu và quyết định ưu tiên đủ rõ, Developers có không gian tự quản lý cách thực hiện; stakeholder có thể đóng góp bằng chứng; và nhóm Agile liên tục thích ứng để đưa sản phẩm tiến tới kết quả thực sự có ích.
