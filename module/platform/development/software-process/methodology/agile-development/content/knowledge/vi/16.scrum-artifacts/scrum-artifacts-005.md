# Cập nhật Sprint Backlog trong quá trình học hỏi và thực hiện

Trong Sprint Planning, Scrum Team thống nhất mục tiêu Sprint và Developers lựa chọn các Product Backlog Items (PBIs) có thể hoàn tất, rồi lập kế hoạch tạo Increment. Nhưng ngay ngày đầu thực hiện, nhóm có thể phát hiện một quy tắc nghiệp vụ chưa rõ, API không hoạt động như giả định hoặc người dùng thực sự cần một luồng đơn giản hơn. Nếu Sprint Backlog bị xem là bản kế hoạch không được sửa, Developers phải lựa chọn giữa làm theo một kế hoạch đã lỗi thời và che giấu vấn đề. Cả hai đều đi ngược tinh thần Agile.

**Sprint Backlog là một kế hoạch sống, được Developers cập nhật liên tục khi học được điều mới**, để hướng đến **Sprint Goal** trong khi vẫn bảo đảm Increment đạt **Definition of Done**. Cập nhật không có nghĩa thay mục tiêu tùy hứng hay nhận mọi yêu cầu phát sinh. Cần phân biệt phần nào của kế hoạch được điều chỉnh, ai quyết định, bằng chứng nào dẫn đến thay đổi và cách nhóm giữ minh bạch với Product Owner, Scrum Master cùng các bên liên quan.

Bài thuộc chương **Tạo tác Scrum** của module **AGILE_DEVELOPMENT**. Đây là cách thực hành cụ thể các giá trị Agile: phản hồi sớm, giao sản phẩm tăng dần, cộng tác để làm rõ user story và backlog, phối hợp Scrum với những kỹ thuật quản lý luồng của Kanban và kỹ thuật chất lượng của XP, rồi cải tiến liên tục dựa trên kết quả.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Nêu đúng ba thành phần **Why – What – How** của Sprint Backlog và vai trò của Sprint Goal.
2. Phân biệt những thay đổi **kế hoạch thực hiện**, **chi tiết/phạm vi PBIs** và **mục tiêu Sprint**.
3. Giải thích Developers cập nhật Sprint Backlog như thế nào, khi nào cần trao đổi với Product Owner, và Scrum Master hỗ trợ ra sao.
4. Nhận diện thông tin mới từ kiểm thử, tích hợp, người dùng, phụ thuộc hoặc vận hành; chuyển thông tin đó thành quyết định có thể kiểm tra.
5. Cập nhật kế hoạch theo cách bảo vệ Sprint Goal, Definition of Done và khả năng phát hành Increment có giá trị.
6. Sử dụng bảng công việc, WIP, work item age, cycle time và phản hồi kỹ thuật để phát hiện việc bị chặn mà không biến Scrum thành cơ chế giám sát cá nhân.
7. Thực hành xử lý các tình huống phát sinh trong Sprint và truyền đạt thay đổi minh bạch, có trách nhiệm.

## 2. Sprint Backlog thực sự là gì?

Theo *Scrum Guide 2020*, Sprint Backlog được cấu thành bởi ba phần:

| Thành phần | Câu hỏi trả lời | Ví dụ với tính năng “Học tiếp” |
| --- | --- | --- |
| **Sprint Goal — Why** | Vì sao Sprint này có giá trị? | Học viên đã đăng nhập có thể mở lại đúng bài đang học dở từ trang khóa học một cách an toàn |
| **Những PBIs được chọn — What** | Scrum Team dự kiến sẽ tạo những khả năng nào? | PBI về luồng học tiếp, tình huống chưa có tiến độ và phần quan sát hành vi liên quan nếu đã được chọn |
| **Kế hoạch có thể hành động — How** | Developers sẽ tạo Increment đạt Done bằng cách nào? | Xác minh quy tắc, triển khai lát cắt UI–API–dữ liệu, tích hợp, kiểm thử phân quyền, quan sát lỗi |

Sprint Backlog là **kế hoạch bởi Developers và dành cho Developers**, thể hiện bức tranh dễ nhìn, theo thời gian thực, về công việc họ dự định thực hiện trong Sprint để đạt Sprint Goal. Mức độ chi tiết phải **đủ để kiểm tra tiến độ tại Daily Scrum**, nhưng không bắt buộc dùng một công cụ hay mẫu bảng cụ thể.

### Ba tạo tác và ba commitment trong Scrum

| Tạo tác Scrum | Commitment liên quan | Trách nhiệm cần nhớ |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Product Owner chịu trách nhiệm quản lý Product Backlog hiệu quả và tối đa hóa giá trị |
| **Sprint Backlog** | **Sprint Goal** | Developers tạo và thích ứng kế hoạch, cùng Scrum Team hướng tới Sprint Goal |
| **Increment** | **Definition of Done** | Developers chịu trách nhiệm tạo Increment có thể sử dụng được, đáp ứng tiêu chuẩn chất lượng |

**Sprint Backlog không phải Product Backlog thu nhỏ rồi đóng băng.** Product Backlog là danh sách được sắp xếp thứ tự về những gì cần để cải thiện sản phẩm; Sprint Backlog gồm những PBIs đã chọn **và** Sprint Goal, kế hoạch thực hiện do Developers duy trì. Increment là kết quả sản phẩm đạt Done; bảng có nhiều ô “xong việc” không tự chứng minh đã có Increment.

### Điều gì là ổn định, điều gì có thể thay đổi?

- **Sprint Goal** là commitment định hướng cho Sprint. Không thực hiện những thay đổi gây nguy hại cho Sprint Goal.
- **Phạm vi chi tiết** có thể được làm rõ và thương lượng lại giữa Developers với Product Owner khi học được điều mới.
- **Kế hoạch How** thường xuyên được Developers chỉnh sửa trong Sprint khi công việc tiến triển và phát sinh hiểu biết mới.
- **Chất lượng không được giảm** trong Sprint để theo đuổi lịch biểu hoặc số lượng PBIs Done.

Điểm quan trọng: **tính thích ứng của kế hoạch không làm mất trách nhiệm với mục tiêu và tiêu chuẩn chất lượng**.

## 3. Vòng đời của Sprint Backlog

Sprint Backlog được hình thành trong Sprint Planning nhưng **không hoàn tất quá trình học hỏi** tại thời điểm cuộc họp kết thúc.

~~~mermaid
flowchart TD
    A["Sprint Planning<br/>Sprint Goal + PBIs + kế hoạch"] --> B["Developers thực hiện lát cắt giá trị"]
    B --> C["Nhận thông tin mới<br/>từ mã, kiểm thử, người dùng, phụ thuộc"]
    C --> D["Kiểm tra tiến độ hướng tới Sprint Goal<br/>và điều kiện Done"]
    D --> E{"Cần điều chỉnh gì?"}
    E -->|Thay đổi cách làm| F["Developers cập nhật How,<br/>task, phối hợp và thứ tự"]
    E -->|Đổi/làm rõ phạm vi| G["Developers trao đổi với Product Owner<br/>để làm rõ hoặc thương lượng"]
    E -->|Không đổi đáng kể| H["Tiếp tục kế hoạch hiện tại"]
    F --> I["Cập nhật Sprint Backlog<br/>hiển thị trạng thái và lý do"]
    G --> I
    H --> B
    I --> B
    B --> J["Increment đạt Definition of Done"]
    J --> K["Sprint Review, phản hồi<br/>và Product Backlog tiếp tục thích ứng"]
~~~

Sơ đồ minh họa các hoạt động **có thể xen kẽ nhau**, không phải quy trình phê duyệt cứng bắt mọi thay đổi phải đợi Daily Scrum. Khi phát hiện một lỗi nghiêm trọng hoặc cơ hội học hỏi, nhóm có thể phối hợp ngay.

| Thời điểm | Sprint Backlog cần phản ánh điều gì? |
| --- | --- |
| **Sau Sprint Planning** | Sprint Goal, các PBIs đã chọn, kế hoạch đủ để bắt đầu, rủi ro và phụ thuộc quan trọng |
| **Trong lúc phát triển** | Task được tạo thêm hoặc hoàn tất, thay đổi cách phối hợp, trở ngại và bước tiếp theo |
| **Khi biết thêm về nghiệp vụ** | Tiêu chí chấp nhận được làm rõ, có thể cần thay đổi phạm vi PBI qua trao đổi với Product Owner |
| **Khi kiểm thử/tích hợp** | Lỗi, công việc sửa cần thiết để đạt Done, điều chỉnh thứ tự thực hiện, tác động đến dự báo |
| **Khi nhận phản hồi sản phẩm** | Thông tin ảnh hưởng giải pháp hoặc ưu tiên; mục liên quan Sprint Goal được xử lý thích hợp, ý tưởng khác đưa về Product Backlog |
| **Gần cuối Sprint** | Phần đã Done thực tế, rủi ro còn lại, phạm vi có thể hoàn tất và cách trao đổi trung thực về phần chưa Done |

**Tính minh bạch** đòi hỏi cập nhật phản ánh trạng thái thật. Không cần cập nhật mọi thao tác đánh máy, nhưng những thay đổi ảnh hưởng kế hoạch, khả năng đạt Sprint Goal và chất lượng phải được nhóm nhìn thấy.

## 4. Các loại thông tin mới khiến kế hoạch cần thích ứng

Không phải thay đổi nào cũng có cùng hậu quả. Có thể phân loại thông tin mới theo nguồn và cách phản ứng.

| Tín hiệu | Ví dụ | Câu hỏi nhóm cần trả lời | Cách cập nhật thường gặp |
| --- | --- | --- | --- |
| **Làm rõ hành vi người dùng** | “Học tiếp” phải mở bài đã lưu, không chỉ mở khóa học | Phạm vi PBI ban đầu đã phản ánh đúng nhu cầu chưa? | Bổ sung ví dụ/tiêu chí chấp nhận, làm rõ với Product Owner |
| **Quy tắc nghiệp vụ** | Bài hết quyền học không được mở dù có tiến độ | Quy tắc này bắt buộc ngay hay là một biến thể mở rộng? | Cập nhật kế hoạch kiểm thử, có thể thương lượng PBI |
| **Rủi ro kỹ thuật** | Hai phiên đăng nhập có thể ghi đè tiến độ sai | Lát cắt hiện tại có an toàn để giao không? | Ưu tiên kiểm chứng, sửa thiết kế, thêm task chất lượng |
| **Phụ thuộc** | Môi trường kiểm thử chưa cấp quyền | Có thể làm gì để giảm thời gian chờ? | Ghi blocker, phối hợp người có quyền, đổi thứ tự task |
| **Năng lực thực tế** | Một Developer phải hỗ trợ sự cố | Sprint Goal bị ảnh hưởng tới đâu? | Developers điều chỉnh phối hợp và dự báo, trao đổi phạm vi khi cần |
| **Phản hồi người dùng** | Học viên không tìm thấy nút khi dùng điện thoại | Điều này làm thay đổi giả thuyết của luồng đang xây? | Điều chỉnh thiết kế nếu phù hợp mục tiêu; ý tưởng khác quay về Product Backlog |
| **Thông tin thị trường/tổ chức** | Có yêu cầu mới quan trọng nhưng chưa rõ mức khẩn | Liệu yêu cầu đó liên quan Sprint Goal hay cần ưu tiên sau? | Product Owner xem xét Product Backlog; chỉ điều chỉnh Sprint khi phù hợp |
| **Số liệu dòng công việc** | Nhiều item bị chặn ở review/kiểm thử | Có điểm nghẽn làm hại khả năng đạt Done? | Giảm WIP, tập trung hoàn tất, thay kế hoạch phối hợp |

### “Học hỏi” không chỉ là có yêu cầu mới

Developers học qua kiểm thử thất bại, đo hiệu năng, đọc log, review mã và quan sát người dùng. Product Owner học về giá trị và ưu tiên. Scrum Master và Scrum Team học cách cộng tác hiệu quả hơn. Sprint Backlog phải giúp biến những hiểu biết liên quan Sprint thành **hành động rõ ràng**.

Nếu thông tin mới không ảnh hưởng mục tiêu, phạm vi hoặc cách làm hiện tại, không nhất thiết phải sửa kế hoạch. Ví dụ một ý tưởng tính năng tương lai được ghi trong Product Backlog, không tự động tạo task trong Sprint Backlog.

## 5. Ai cập nhật và ai cần tham gia quyết định?

Trong Scrum, quyền tự quản gắn liền với trách nhiệm minh bạch:

| Chủ thể | Trách nhiệm trong quá trình thích ứng | Ví dụ |
| --- | --- | --- |
| **Developers** | Tự tổ chức cách thực hiện và cập nhật Sprint Backlog khi học điều mới; chịu trách nhiệm chất lượng Increment | Đổi trình tự tích hợp, chia thêm task, ghép cặp giải quyết lỗi, sửa kế hoạch kiểm thử |
| **Product Owner** | Tối đa hóa giá trị và quản lý Product Backlog; trao đổi với Developers khi cần làm rõ/thương lượng phạm vi Sprint | Làm rõ quy tắc, cân đối giá trị giữa hai PBI, xem xét yêu cầu mới |
| **Scrum Master** | Hỗ trợ Scrum Team áp dụng Scrum hiệu quả, làm cho trở ngại và thiếu minh bạch được giải quyết | Giúp nhóm hiểu khác nhau giữa Sprint Goal và danh sách task, hỗ trợ cải thiện cách phối hợp |
| **Bên liên quan và chuyên gia được mời** | Cung cấp thông tin về người dùng, an toàn, vận hành hoặc phụ thuộc | Giải thích chính sách dữ liệu hoặc phản hồi từ nhóm học viên |

**Không cần Product Owner phê duyệt từng task kỹ thuật.** Developers có thể thay đổi How khi cần. Nhưng thay đổi PBI được chọn theo cách làm khác giá trị, phạm vi hoặc thứ tự quan trọng cần được **làm rõ và thương lượng với Product Owner**.

Trong Scrum Guide, **không ai khác bảo Developers phải biến Product Backlog Items thành Increment thế nào**. Điều đó không có nghĩa họ quyết định bỏ qua quy định tổ chức, tiêu chuẩn bảo mật hoặc trách nhiệm với khách hàng.

### Một tình huống phân quyền đúng

Developers phát hiện lệnh gọi API hiện tại chậm, quyết định áp dụng cache có kiểm thử và cơ chế hết hạn phù hợp: đó thường là điều chỉnh **How**. Nếu họ muốn bỏ hoàn toàn luồng “Học tiếp” để xây email nhắc học, đây không còn là thay đổi kỹ thuật thông thường; cần trao đổi với Product Owner và xem quyết định có còn phục vụ Sprint Goal không.

### Scrum Master có “quản lý Sprint Backlog” không?

Scrum Master giúp sự kiện và tương tác hiệu quả, nhưng **không sở hữu danh sách task để giao việc**. Nếu bảng đang không được cập nhật, Scrum Master có thể đặt câu hỏi để Developers tự làm rõ và thay đổi thói quen; không nên biến cập nhật bảng thành việc báo cáo lên người điều phối.

## 6. Bảo vệ Sprint Goal khi thay đổi kế hoạch

Sprint Goal là **mục tiêu duy nhất của Sprint**, tạo sự tập trung và gắn kết. Nó cho phép linh hoạt ở phần việc cụ thể, bởi khi hiểu vấn đề sâu hơn nhóm có thể tìm được cách ít tốn kém hoặc an toàn hơn để đạt cùng kết quả.

Ví dụ Sprint Goal:

> “Học viên đã đăng nhập và còn quyền truy cập có thể mở lại đúng bài đang dở từ trang khóa học trên cùng thiết bị, với tiến độ cá nhân được bảo vệ”.

Nhóm học được rằng vị trí hiện tại của nút gây khó hiểu. Thay đổi nhãn và vị trí nút, bổ sung kiểm thử khả dụng hoặc sửa cách đọc tiến độ có thể **ủng hộ Sprint Goal**. Ngược lại, bỏ luồng này để phát triển email thông báo chưa được xác minh thường **không còn phù hợp** với mục tiêu Sprint.

### Ba câu hỏi giữ định hướng

1. **Vì sao thay đổi?** Có bằng chứng, rủi ro hoặc quy tắc mới nào làm kế hoạch cũ không còn hợp lý?
2. **Còn phục vụ Sprint Goal không?** Người dùng có vẫn nhận được hành vi hoặc giá trị mà Scrum Team đang theo đuổi không?
3. **Chất lượng có được bảo vệ không?** Increment cuối cùng có đạt Definition of Done, không che giấu lỗi và không vi phạm các giới hạn an toàn không?

| Đề xuất thay đổi | Đánh giá | Cách xử lý |
| --- | --- | --- |
| Đổi thiết kế nút “Học tiếp” để người dùng tìm thấy dễ hơn | Thường vẫn giữ mục tiêu | Developers điều chỉnh How và xác nhận với người hiểu nhu cầu khi cần |
| Bổ sung kiểm thử tránh trả dữ liệu tiến độ của người khác | Bảo vệ chất lượng bắt buộc | Đưa vào kế hoạch ngay, không hoãn vì không “có thêm tính năng” |
| Lùi phần hướng dẫn cho bài đã hoàn thành, giữ luồng đang học dở | Có thể giảm phạm vi nâng cao | Developers làm rõ/thương lượng với Product Owner, kiểm tra Goal và Done |
| Thêm hệ thống gợi ý nội dung toàn diện giữa Sprint | Có thể làm mất tập trung, không trực tiếp phục vụ Goal | Đưa vào Product Backlog để Product Owner đánh giá ưu tiên |
| Bỏ xác thực để kịp hạn | Làm giảm chất lượng và có nguy cơ bảo mật | Không được thực hiện |
| Đổi toàn bộ Sprint Goal để khớp các task đã làm | Không phải cách cập nhật thông thường | Nếu Sprint Goal thật sự lỗi thời, Product Owner cân nhắc quyền hủy Sprint |

### Sprint Goal không phải khẩu hiệu để ép nhóm bằng mọi giá

Nếu Sprint Goal không còn khả thi với chất lượng bắt buộc, nhóm phải nói rõ rủi ro, xem những phương án phạm vi hợp lý và điều chỉnh dự báo. **Không ép Developers gọi công việc chưa Done là hoàn tất** chỉ để báo mục tiêu xanh. Một mục tiêu rõ giúp đưa ra đánh đổi có trách nhiệm, không phải giấy phép bỏ qua thực tế.

## 7. Phân biệt cập nhật How và thương lượng What

Hai loại thay đổi thường bị trộn lẫn, dẫn đến tranh cãi quyền quyết định.

### 7.1. Thay đổi How: Developers chủ động

Ví dụ:

- Chuyển từ làm UI rồi mới làm API sang dựng một lát cắt end-to-end sớm.
- Cặp hai Developers giải quyết lỗi tích hợp thay vì mỗi người tiếp tục task riêng.
- Thêm task kiểm thử trường hợp tiến độ cũ không hợp lệ.
- Thay thứ tự việc để xử lý API đang chặn các phần khác.
- Tự động hóa một bài kiểm thử, bổ sung logging cần thiết hoặc refactor để giảm lỗi hồi quy.
- Bỏ một bước kỹ thuật không còn cần sau khi chọn giải pháp đơn giản hơn.

Những thay đổi đó cần được thể hiện trong Sprint Backlog khi ảnh hưởng kế hoạch thực hiện, nhưng không đòi phải lập lại Sprint Planning. Developers vẫn phải tôn trọng Definition of Done và các ràng buộc sản phẩm, tổ chức áp dụng.

### 7.2. Làm rõ hoặc thương lượng What: Developers trao đổi Product Owner

Ví dụ:

- Chia PBI “đồng bộ mọi thiết bị” thành lát cắt “một thiết bị” trước nếu vẫn phù hợp Sprint Goal và giá trị mong muốn.
- Phát hiện thêm quy tắc nghiệp vụ bắt buộc làm PBI lớn hơn và cần điều chỉnh các PBI được chọn.
- Bỏ một biến thể chưa cần để có đủ năng lực hoàn tất hành vi cốt lõi.
- Bổ sung một PBI thực sự thiết yếu để tạo Increment sử dụng được và đáp ứng mục tiêu.
- Đưa một ý tưởng không còn giá trị ra khỏi phạm vi Sprint, điều chỉnh Product Backlog cho đúng.

Không có quy định “mỗi lần điều chỉnh PBI phải họp một giờ” hoặc “phải có change request riêng” trong Scrum Guide. Điều quan trọng là **trao đổi trực tiếp, đủ bằng chứng, giữ Sprint Goal và tính minh bạch**.

### 7.3. Không dùng từ “học được điều mới” để hợp thức hóa scope creep

Phát hiện mới có thể quan trọng, nhưng thêm bất kỳ PBI nào vào Sprint đều tiêu tốn năng lực. Hãy hỏi:

1. Đây là **quy tắc bắt buộc** để phần đã chọn hoạt động đúng hay là **tính năng mở rộng**?
2. Nếu thêm, công việc gì cần bớt hoặc điều chỉnh để không làm hại Sprint Goal?
3. Product Owner và Developers có cùng hiểu biết về giá trị, rủi ro và giới hạn không?
4. Có thể ghi nhu cầu vào Product Backlog cho Sprint sau thay vì nhận ngay không?

Việc dự báo thay đổi không phải là dấu hiệu thiếu trách nhiệm; **bỏ qua hậu quả của thay đổi và giấu phạm vi mới** mới làm mất khả năng dự báo.

## 8. Daily Scrum: nơi Developers kiểm tra tiến độ và thích ứng Sprint Backlog

**Daily Scrum** là sự kiện **15 phút dành cho Developers** nhằm kiểm tra tiến độ hướng tới Sprint Goal và thích ứng Sprint Backlog khi cần. Nhóm chọn cấu trúc phù hợp, miễn tạo tập trung vào mục tiêu và kế hoạch có thể hành động cho ngày tiếp theo.

Một cách trao đổi:

> “Sprint Goal hôm nay đang ở trạng thái nào? Những việc nào cản trở khả năng tạo Increment đạt Done? Chúng ta cần đổi thứ tự, phối hợp hay làm rõ phạm vi gì trước lần kiểm tra tiếp theo?”

### Ví dụ Daily Scrum không biến thành báo cáo cá nhân

**Trạng thái trước Daily Scrum:**

- Hai Developers đang xây phần giao diện trong khi API lưu tiến độ chưa có hợp đồng ổn định.
- Task kiểm thử phân quyền bị chặn vì thiếu tài khoản dữ liệu thử.
- Một item đã ở trạng thái Doing sáu ngày nhưng chưa có luồng end-to-end.

**Phần kiểm tra:**

> Developer A: “Nếu tiếp tục hai màn hình riêng, chúng ta khó đạt luồng dùng được trong tuần này. Tôi đề xuất cùng Developer B hoàn tất hợp đồng API và chạy được một đường đi trước.”  
> Developer B: “Tôi đồng ý. Tôi sẽ tạm dừng nhánh UI thứ hai để cặp tích hợp.”  
> Developer C: “Bộ kiểm thử phân quyền cần tài khoản thử. Tôi sẽ nhờ bộ phận liên quan cấp quyền đúng phạm vi và chuẩn bị dữ liệu an toàn.”  
> Developers: “Cập nhật task, đánh dấu việc bị chặn và kiểm tra lại cuối ngày.”

**Sau Daily Scrum:** Sprint Backlog phản ánh việc đổi thứ tự, người phối hợp, blocker và điều kiện để mở lại task. Những người cần xử lý kỹ thuật có thể trao đổi sâu hơn **sau** sự kiện, không bắt cả nhóm ngồi quá timebox.

Daily Scrum là cơ hội chính thức, nhưng **Developers có thể điều chỉnh kế hoạch trong ngày bất kỳ khi nào có thông tin mới**. Scrum không đòi đợi cuộc họp hôm sau mới gỡ lỗi.

## 9. Cách biểu diễn một Sprint Backlog có khả năng thích ứng

Không có định dạng bắt buộc: bảng vật lý, bảng điện tử, tài liệu hoặc công cụ quản lý công việc đều có thể dùng. Nhưng một biểu diễn hữu ích cần cho thấy **mục tiêu, công việc được chọn, trạng thái thực tế, phụ thuộc và kế hoạch tiếp theo**.

### Ví dụ Sprint Backlog sau Planning

~~~text
SPRINT GOAL (Why)
  Học viên hợp lệ có thể mở lại đúng bài đang dở
  từ trang khóa học trên cùng thiết bị.

SELECTED PBIs (What)
  PBI-21: Luồng "Học tiếp" cho bài chưa hoàn thành
  PBI-22: Trạng thái khi chưa có tiến độ (nếu đã chọn tại Planning)

PLAN (How) — Developers duy trì
  [ ] Làm rõ quy tắc tiếp tục bài và phân quyền
  [ ] Xác minh hợp đồng dữ liệu tiến độ
  [ ] Dựng luồng UI + API có thể chạy sớm
  [ ] Kiểm thử truy cập đúng tài khoản và dữ liệu không hợp lệ
  [ ] Chạy kiểm thử tích hợp và kiểm tra Definition of Done
  [ ] Chuẩn bị quan sát hành vi học tiếp trong phạm vi an toàn

RISKS / BLOCKERS
  Rủi ro cập nhật từ thiết bị khác; chờ môi trường thử.
~~~

### Ví dụ cùng Sprint Backlog sau khi học thêm

~~~text
SPRINT GOAL (Why) — GIỮ NGUYÊN
  Học viên hợp lệ có thể mở lại đúng bài đang dở
  từ trang khóa học trên cùng thiết bị.

SELECTED PBIs (What)
  PBI-21: Luồng "Học tiếp" [đang làm]
  PBI-22: Thảo luận với Product Owner để làm rõ phạm vi
          vì phát hiện lỗi dữ liệu cũ ảnh hưởng Goal

PLAN (How) — ĐÃ ĐIỀU CHỈNH
  [x] Làm rõ quy tắc và phân quyền chính
  [x] Xác minh hợp đồng dữ liệu
  [ ] Developers ghép cặp xử lý trường hợp tiến độ cũ không hợp lệ [ưu tiên]
  [ ] Hoàn tất luồng UI + API end-to-end
  [ ] Kiểm thử phân quyền và lỗi dữ liệu cũ [bổ sung]
  [ ] Kiểm thử tích hợp, Definition of Done và quan sát lỗi

RISKS / BLOCKERS
  Truy cập dữ liệu test [đã tháo chặn];
  lỗi tiến độ cũ [đã có người xử lý và cách kiểm chứng].
~~~

**Ghi chú:** Hai ví dụ đều là mô phỏng. Nếu PBI-22 thực sự bị đưa ra khỏi Sprint hoặc thay bằng PBI khác, sự thay đổi phạm vi cần được thương lượng với Product Owner và phản ánh nhất quán ở cả Sprint Backlog lẫn Product Backlog. Câu “sẽ xem xét” chưa phải quyết định bỏ PBI.

### Bảng các cột tối thiểu có ích

| Trường | Để trả lời điều gì? | Gợi ý |
| --- | --- | --- |
| Sprint Goal | Mục tiêu nào đang định hướng mọi quyết định? | Đặt nơi dễ thấy, không chôn trong tài liệu |
| PBI / kết quả mong muốn | Luồng giá trị nào được chọn? | Liên kết với tiêu chí chấp nhận và Product Backlog |
| Các task thực hiện | Developers sẽ làm gì tiếp để đạt Done? | Có thể thêm/bớt/chia/gộp khi học được điều mới |
| Trạng thái | Đã bắt đầu, đang chờ hay đạt Done? | Dùng trạng thái phản ánh sự thật |
| Blocker/phụ thuộc | Điều gì đang ngăn hoàn thành? | Nêu việc cần làm và người có thể hỗ trợ |
| Tín hiệu chất lượng | Còn kiểm thử hoặc rủi ro quan trọng gì? | Không gọi PBI Done khi còn thiếu chuẩn |
| Cập nhật gần nhất | Nhóm đã đổi kế hoạch vì điều gì? | Chỉ ghi thay đổi đáng kể; tránh gánh nặng hành chính |

## 10. Tình huống xuyên suốt: hai tuần triển khai “Học tiếp”

Đây là **tình huống giả định để học**, không phải số liệu hoặc timeline chuẩn cho mọi Scrum Team.

### 10.1. Sprint Planning — trạng thái ban đầu

**Product Goal:** Giúp học viên mới duy trì lộ trình học thuận tiện, đáng tin cậy.

**Sprint Goal:** “Học viên đã đăng nhập và còn quyền học có thể mở lại đúng bài đang dở từ trang khóa học trên cùng thiết bị”.

**PBIs được chọn:**

- **PBI-A:** Từ trang khóa học, học viên mở lại đúng bài đang dở, với dữ liệu của chính mình.
- **PBI-B:** Nếu học viên chưa có tiến độ, hệ thống đề xuất bài được phép bắt đầu; nhóm đã dự báo có năng lực cho nhánh này.
- **PBI-C:** Ghi tín hiệu quan trọng để quan sát luồng học tiếp và lỗi truy xuất, theo các chính sách dữ liệu cần thiết.

**How ban đầu:** Làm rõ quy tắc → chạy lát cắt API–UI → tích hợp sớm → kiểm thử bảo mật và trạng thái biên → xác nhận Done → thử với người dùng phù hợp.

Developers đã trao đổi về năng lực, Definition of Done, các rủi ro và phụ thuộc trước khi lựa chọn PBIs. Không ai giả định mọi task sẽ diễn ra đúng từng ngày.

### 10.2. Ngày 2 — phát hiện API trả dữ liệu cũ

Trong kiểm thử tích hợp, Developers phát hiện trường tiến độ có thể bị lưu ở phiên cũ sau khi người học chuyển trang nhanh. Nếu bỏ qua, nút “Học tiếp” có thể đưa học viên đến sai bài.

**Quyết định:** Developers ưu tiên phân tích và kiểm thử lỗi này trước khi mở rộng giao diện. Họ bổ sung task kiểm tra tính nhất quán dữ liệu và đổi thứ tự thực hiện. Đây chủ yếu là thay đổi **How**, vì hành vi đúng tiến độ đã nằm trong mục tiêu và tiêu chuẩn chất lượng.

**Cập nhật Sprint Backlog:** đánh dấu rủi ro; gắn task sửa lỗi vào PBI-A; tạm dừng công việc không thiết yếu; nêu điều kiện xác nhận lỗi đã được xử lý.

### 10.3. Ngày 4 — người dùng gặp khó với tên nút

Phiên thử khả dụng cho thấy một số học viên không hiểu nút “Tiếp tục”, nhưng tìm thấy nút “Học tiếp bài đang dở” dễ hơn. Nghiên cứu định tính này không đủ để khẳng định tác động của toàn bộ người dùng, nhưng hữu ích để đề xuất thiết kế.

**Quyết định:** Developers cùng Product Owner và người làm thiết kế làm rõ hành vi/nhãn trong phạm vi Sprint Goal, cập nhật task UI và ví dụ kiểm thử. Nhóm tiếp tục đo/quan sát ở lát cắt thật sau khi có Increment.

**Không suy diễn:** “Ba người thích nhãn mới” chưa chứng minh retention tăng; đây là bằng chứng khả dụng có giới hạn, không phải kết luận cuối cùng về giá trị kinh doanh.

### 10.4. Ngày 5 — PBI-B rộng hơn dự tính

Khi làm rõ “chưa có tiến độ”, nhóm phát hiện nhiều loại khóa học với chính sách bài đầu khác nhau. Triển khai đầy đủ PBI-B sẽ tốn thêm thời gian, trong khi PBI-A còn cần kiểm thử.

Developers trình bày với Product Owner:

> “Để bảo vệ Sprint Goal và Definition of Done, chúng tôi đề xuất tập trung hoàn tất PBI-A và các kiểm tra quan trọng, chuyển phần quy tắc nâng cao của PBI-B về Product Backlog. Nếu còn khả năng sau khi PBI-A Done, chúng ta có thể lựa chọn một lát cắt nhỏ đã làm rõ.”

Product Owner cùng Developers làm rõ những trường hợp nào **bắt buộc** với luồng đang hỗ trợ và những trường hợp nào **có thể hoãn an toàn**. Họ thương lượng điều chỉnh phạm vi PBI-B, cập nhật Sprint Backlog và Product Backlog phù hợp. **Không thể hoãn phân quyền hoặc tính đúng đắn của PBI-A** vì các công việc đó là điều kiện để Increment an toàn.

### 10.5. Ngày 7 — phát sinh yêu cầu email nhắc học

Một bên liên quan đề nghị xây thêm hệ thống email trong Sprint vì thấy doanh nghiệp đang cần tăng lượt quay lại.

**Quyết định:** Product Owner đánh giá giá trị và mức khẩn, ghi đề xuất vào Product Backlog để sắp xếp thứ tự. Scrum Team nhận thấy email không cần để đạt Sprint Goal hiện tại và không tự đưa yêu cầu vào Sprint Backlog. Nếu có nghĩa vụ khẩn mới, nhóm phải làm rõ hậu quả và quyền quyết định thay vì coi mọi yêu cầu mới như mệnh lệnh tức thì.

### 10.6. Ngày 9 — chất lượng quyết định trạng thái Done

Luồng UI–API chạy được, nhưng kiểm thử phát hiện quyền truy cập không được kiểm tra đúng sau khi phiên đăng nhập hết hạn. PBI-A **chưa đạt Definition of Done**.

**Quyết định:** Developers sửa và kiểm thử vấn đề bắt buộc; cập nhật Sprint Backlog minh bạch; báo cho Product Owner và các bên liên quan về tác động dự báo. Không phát hành hoặc trình bày PBI-A như Increment Done khi còn vi phạm điều kiện chất lượng.

Nếu chỉ còn thời gian ngắn, nhóm không được “tắt test tạm” để đóng ticket. Kết quả có thể là một phần công việc chưa hoàn tất vào cuối Sprint, cần được Product Owner xem xét lại trong Product Backlog.

### 10.7. Cuối Sprint — điều gì được báo cáo?

Giả sử PBI-A được sửa và đạt Done trước cuối Sprint, nhưng PBI-B không hoàn thành:

- Sprint Review xem **Increment thực sự đạt Done** và những phản hồi từ người dùng/bên liên quan.
- Phần PBI-B chưa Done được minh bạch và đưa về Product Backlog để Product Owner xem xét tiếp; **không tự động coi là hoàn thành hoặc bắt buộc nhận nguyên vẹn vào Sprint kế tiếp**.
- Sprint Retrospective kiểm tra nguyên nhân làm PBI-B khó dự báo: quy tắc chưa rõ, chia câu chuyện quá rộng hay thiếu tiếp xúc người hiểu nghiệp vụ?
- Cách cập nhật Sprint Backlog trong Sprint được xem xét như một thực hành của nhóm: thay đổi có được ghi rõ? Trở ngại có được nhìn thấy sớm? Các quyết định phạm vi có đúng trách nhiệm?

Nếu PBI-A cũng chưa Done, nhóm phải nêu đúng trạng thái đó. **Một Sprint kết thúc theo timebox dù không phải mọi PBI đã hoàn thành**; không nên kéo dài Sprint tùy ý để làm bảng trông đẹp hơn.

## 11. Theo dõi thay đổi bằng quyết định ngắn, không tạo hành chính nặng

Khi thay đổi lớn ảnh hưởng phạm vi hoặc cách làm, một ghi chú vài dòng có thể tránh các cuộc tranh luận lặp lại. Không cần quy trình phê duyệt phức tạp cho mọi task.

~~~text
Cập nhật Sprint Backlog — ngày/giờ:
Sprint Goal hiện tại:
Tín hiệu mới / bằng chứng:
Điều hiểu thêm / giả định còn thiếu:
Phần bị ảnh hưởng: How / PBI được chọn / phụ thuộc / chất lượng
Quyết định:
Ai cần phối hợp hoặc được thông báo:
Ảnh hưởng tới khả năng đạt Sprint Goal:
Ảnh hưởng đến Definition of Done / rủi ro an toàn:
Bước tiếp theo và điều kiện kiểm tra:
Trạng thái cập nhật trên bảng:
~~~

### Ví dụ một bản ghi tốt

> **Ngày 5:** Kiểm tra cho thấy nhánh “chưa có tiến độ” chứa ba chính sách khóa học khác nhau. Developers và Product Owner thống nhất giữ luồng học viên đang học dở làm ưu tiên; các biến thể không bắt buộc chuyển về Product Backlog để refinement. Task kiểm thử bảo vệ quyền truy cập vẫn ở Sprint Backlog. Sprint Goal giữ nguyên; cần xem lại khả năng hoàn tất PBI-A tại Daily Scrum tiếp theo.

Bản ghi này có **lý do, phạm vi thay đổi và hành động**, thay vì chỉ có “đổi ticket vì yêu cầu mới”. Nó cũng cho phép những người vắng mặt hiểu vì sao bảng công việc hôm nay khác hôm qua.

### Khi nào không cần decision record?

Nếu Developers đổi thứ tự hai task nhỏ mà không ảnh hưởng phụ thuộc, giá trị, Done hoặc dự báo, cập nhật trạng thái trên bảng thường đủ. Tính minh bạch nên phục vụ điều phối và học hỏi, **không khiến chi phí báo cáo vượt giá trị quyết định**.

## 12. Cập nhật Sprint Backlog bằng cách nhìn theo luồng công việc

Một Sprint Backlog có thể kết hợp bảng workflow để Developers nhận ra việc đang chờ. Chẳng hạn:

~~~text
Selected PBI → Ready → In progress → Review/Test → Done
                  |            |
                WIP giới hạn theo chính sách nhóm

Blocked là tín hiệu cản trở, không phải nơi để giấu việc vô thời hạn.
Sprint Goal luôn hiển thị phía trên bảng.
~~~

### Thông tin đáng xem, không chỉ số cột

| Tín hiệu | Nói lên điều gì | Phản ứng phù hợp |
| --- | --- | --- |
| **WIP (Work in Progress)** tăng liên tục | Nhiều việc được bắt đầu hơn khả năng hoàn thành | Giảm bắt đầu việc mới; ưu tiên hoàn tất hoặc tháo chặn |
| **Work item age** của item đang làm lớn | Item bị kéo dài so với những item tương tự | Hỏi vì sao, cần phối hợp hay chia lại việc không? |
| **Cycle time** tăng, nhất là đuôi dài | Luồng có biến thiên hoặc chờ đợi | Quan sát ranh giới đo và nút thắt, không đổ lỗi cá nhân |
| **Throughput** ít dù nhiều item “gần xong” | Có thể có vấn đề hoàn tất, tích hợp hoặc kiểm thử | Tập trung đưa ít item về Done đúng chuẩn |
| **Blocker lâu không đổi** | Phụ thuộc chưa được xử lý | Nêu người cần hỗ trợ, thời điểm và phương án thay thế |
| **Lỗi kiểm thử quan trọng** | Chất lượng chưa đáp ứng yêu cầu | Đưa công việc sửa/kiểm chứng vào kế hoạch trước khi gọi Done |

Các chỉ số này đến từ cách tiếp cận **quản lý flow của Kanban**, có thể hỗ trợ Scrum Team mà không thay vai trò của Sprint Goal hoặc các sự kiện Scrum. Chúng giúp hỏi “Hệ thống đang vướng ở đâu?” chứ không phải “Ai có số ticket thấp nhất?”.

### Ví dụ số liệu minh họa

Trong một Sprint hai tuần, ngày thứ sáu nhóm có:

- 7 item đã bắt đầu nhưng chỉ 1 item Done.
- 3 item đang chờ review, 2 item đang chờ môi trường kiểm thử.
- Một item đã ở Doing năm ngày nhưng chưa chạy được end-to-end.

Kết luận hợp lý không phải ngay lập tức “nhóm lười” hay “phải tăng giờ làm”. Developers có thể tập trung ghép cặp hoàn tất review, nhờ hỗ trợ cấp môi trường, giảm WIP và chọn một lát cắt để đưa đến Done. Sau đó quan sát xem thời gian chờ có giảm không. **Những con số này là giả định, không phải ngưỡng KPI chuẩn cho mọi nhóm**.

## 13. XP giúp cập nhật kế hoạch mà không làm mất chất lượng

Khi Sprint Backlog thay đổi, công việc kỹ thuật có thể phải sửa nhiều lần. Các thực hành của **Extreme Programming (XP)** giúp chi phí thay đổi được kiểm soát:

| Thực hành | Vòng phản hồi | Liên hệ đến cập nhật Sprint Backlog |
| --- | --- | --- |
| **Test-Driven Development (TDD)** | Kiểm thử nhỏ cho hành vi mới, triển khai, refactor | Khi phát hiện quy tắc mới, Developers bổ sung ví dụ kiểm tra và điều chỉnh cách làm |
| **Continuous Integration (CI)** | Kiểm thử/tích hợp sớm sau thay đổi | Phát hiện công việc sửa lỗi hoặc tích hợp cần đưa lên ưu tiên |
| **Refactoring** | Cải thiện cấu trúc trong khi giữ hành vi | Hỗ trợ thay đổi hướng kỹ thuật mà không tạo nhiều lỗi hồi quy |
| **Pair programming / review** | Phản hồi giữa Developers | Phối hợp gỡ blocker; chia sẻ hiểu biết để tránh phụ thuộc một người |
| **Small releases** | Increment nhỏ đưa tới người dùng khi an toàn | Nhận phản hồi giá trị sớm, tác động đến Product Backlog và đôi khi kế hoạch Sprint hiện tại |

### Ví dụ: quy tắc mới được khám phá

Ban đầu nhóm kiểm thử: “Nếu có bài đang dở, nút ‘Học tiếp’ mở bài đó”. Sau đó phát hiện quy tắc: “Nếu bài đã hết quyền truy cập, không được mở nội dung dù đã lưu tiến độ”.

Developers có thể:

1. Viết thêm trường hợp kiểm thử từ chối truy cập phù hợp.
2. Làm rõ tiêu chí chấp nhận với Product Owner/người hiểu nghiệp vụ.
3. Điều chỉnh luồng API và giao diện; cập nhật task và phụ thuộc trong Sprint Backlog.
4. Chạy CI, kiểm thử tích hợp và đánh giá Definition of Done.
5. Báo minh bạch nếu quy tắc làm thay đổi khả năng hoàn tất các PBI khác.

Điều chỉnh Sprint Backlog và kỷ luật kỹ thuật **hỗ trợ nhau**. Nếu mỗi thay đổi chỉ được ghi trên bảng mà không có kiểm thử bảo vệ, bảng có thể “xanh” trong khi Increment không đáng tin.

## 14. Học từ phản hồi người dùng: khi nào sửa ngay, khi nào để Product Backlog?

Trong Agile, phản hồi sớm giúp giảm nguy cơ xây sai sản phẩm. Tuy vậy, không phải mọi ý kiến người dùng đều phải chuyển thành việc của Sprint hiện tại.

### Phân biệt bốn dạng tín hiệu

| Tín hiệu | Ví dụ | Cách cân nhắc |
| --- | --- | --- |
| **Sai hành vi đã hứa của PBI** | Nút “Học tiếp” mở sai bài | Sửa trong kế hoạch hiện tại để đạt tiêu chí chấp nhận và Done |
| **Phát hiện làm rõ Sprint Goal** | Học viên khó tìm nút trên màn hình nhỏ | Có thể thay giải pháp để bảo vệ kết quả mục tiêu; xem tác động phạm vi |
| **Ý tưởng mở rộng không cần cho mục tiêu** | Cá nhân hóa email nhắc học cho từng người | Product Owner ghi và ưu tiên trong Product Backlog |
| **Thay đổi chiến lược lớn** | Nghiên cứu cho thấy nhu cầu cốt lõi đang giải quyết không còn tồn tại | Scrum Team kiểm tra bằng chứng; nếu Sprint Goal lỗi thời, Product Owner cân nhắc hủy Sprint |

Phản hồi định tính từ vài người dùng là **gợi ý về vấn đề và giả thuyết**, không tự động chứng minh tác động với toàn bộ thị trường. Ngược lại, số liệu sản phẩm cũng cần xem định nghĩa, phạm vi, thời gian và cách đo. **Không chuyển từng bình luận đơn lẻ thành “ưu tiên mới số một” khi chưa hiểu bối cảnh**.

### Output, outcome và Done là những khái niệm khác nhau

- **Output:** nút “Học tiếp” được xây và tích hợp.
- **Increment Done:** hành vi đáp ứng Definition of Done và có thể sử dụng trong phạm vi đã hứa.
- **Outcome:** người học thật sự tìm đúng bài nhanh hơn hoặc tăng khả năng tiếp tục học sau một khoảng quan sát phù hợp.

Increment Done là điều kiện để giao giá trị tin cậy, nhưng chưa tự chứng minh outcome. Sprint Backlog cần hỗ trợ làm sản phẩm đúng; phản hồi từ outcome có thể định hướng **Product Backlog** cho các Sprint tiếp theo.

## 15. Điều gì không được đánh đổi khi cập nhật?

Thích ứng không đồng nghĩa được tùy ý giảm điều kiện hoàn tất.

### Definition of Done là ranh giới chất lượng

Definition of Done là mô tả chính thức trạng thái của Increment khi đáp ứng các tiêu chuẩn chất lượng cần có. Nếu một Product Backlog Item không đạt Definition of Done, nó **không thể được xem là một phần của Increment**. Theo Scrum Guide, công việc chưa đạt Done không được phát hành hoặc trình bày tại Sprint Review như một Increment hoàn tất; nó trở về Product Backlog để xem xét trong tương lai.

Ví dụ với tiến độ học viên, kiểm tra phân quyền và bảo toàn dữ liệu là điều kiện an toàn quan trọng. Nếu nhóm phát hiện nguy cơ lộ dữ liệu, không được chuyển phần kiểm tra ấy thành “tính năng nâng cao Sprint sau” trong khi vẫn gọi luồng hiện tại là Done.

### Một số tình huống cần phân biệt

| Tình huống | Có thể cập nhật gì? | Điều không được làm |
| --- | --- | --- |
| Test fail vì dữ liệu cũ không hợp lệ | Thêm task sửa xử lý dữ liệu, đổi thứ tự công việc, xem ảnh hưởng dự báo | Bỏ test hoặc gọi PBI Done khi hành vi sai |
| Phụ thuộc API chưa sẵn sàng | Thử mock có kiểm chứng, trao đổi bên liên quan, đổi cách tích hợp | Dùng mock rồi tuyên bố tính năng production đã hoạt động thật nếu chưa được chứng minh |
| Bên liên quan muốn tính năng mới không thuộc Goal | Product Owner cân nhắc Product Backlog | Tự thêm toàn bộ vào Sprint và áp lực giữ mọi cam kết cũ |
| Nhóm thiếu người vì sự cố | Developers thay phối hợp, thương lượng phạm vi với Product Owner | Ép tăng ca như mặc định và che giấu rủi ro chất lượng |
| Một PBI có phần Done, phần chưa Done | Làm rõ có thể tách thành lát cắt độc lập đạt Done không, xử lý backlog minh bạch | Chia ticket chỉ để đổi phần chưa kiểm thử thành “xong” |

**Chất lượng không giảm** là một nguyên tắc vận hành trong Sprint. Nếu không thể vừa giữ toàn bộ phạm vi vừa đảm bảo Done, cần đối thoại về phạm vi, năng lực hoặc dự báo, không hợp thức hóa làm tắt.

## 16. Khi gần cuối Sprint: minh bạch thay vì chạy theo biểu đồ

Các ngày cuối Sprint thường xuất hiện áp lực “đóng nốt cho đủ điểm”. Đó là lúc cập nhật Sprint Backlog cần trung thực nhất.

### Một bảng kiểm tra cuối Sprint

1. **Sprint Goal:** Kết quả nào đã có, điều kiện gì còn cản trở? Có thể kiểm chứng điều đã đạt bằng Increment không?
2. **PBIs đã chọn:** Mục nào thật sự đạt Definition of Done? Mục nào còn kiểm thử, review hoặc phụ thuộc?
3. **Kế hoạch How:** Những bước cuối nào thiết yếu để giao an toàn? Có phần việc không còn cần sau khi đã học điều mới?
4. **Phạm vi:** Developers và Product Owner đã làm rõ những PBI cần thương lượng chưa?
5. **Truyền đạt:** Những giả định, rủi ro và thay đổi ảnh hưởng bên liên quan đã được nói rõ chưa?

### “Gần xong” khác với Done

Giả sử PBI-A đã có UI và API, nhưng chưa kiểm thử trường hợp hết quyền truy cập. Không thể tuyên bố Increment hoàn tất chỉ vì “90% task được tick”. Nếu Developers phát hiện không còn đủ thời gian, họ báo trạng thái thật và cân nhắc cách làm phù hợp với Sprint Goal, chất lượng.

Nếu một PBI chưa đạt Done vào cuối Sprint, nó quay về Product Backlog để Product Owner xem xét; **không có luật Scrum rằng mọi PBI chưa Done tự động trở thành công việc bắt buộc của Sprint tiếp theo**. Scrum Team phải tiếp tục sắp xếp ưu tiên và lập kế hoạch theo giá trị cùng thông tin mới.

### Khi Sprint Goal trở nên lỗi thời

Theo Scrum Guide, **chỉ Product Owner có thẩm quyền hủy Sprint nếu Sprint Goal trở nên lỗi thời**. Đây không phải thao tác sửa bảng thông thường và không phải phản ứng mặc định khi một task trễ. Cần phân biệt:

- **Khó khăn thực hiện:** vẫn có thể đạt mục tiêu bằng thay đổi How hoặc thương lượng phạm vi.
- **Mục tiêu lỗi thời:** nhu cầu hoặc bối cảnh khiến việc theo đuổi Sprint Goal không còn có ý nghĩa.

Sự khác biệt này ngăn việc “đổi Goal” mỗi khi công việc trở nên khó, đồng thời giữ khả năng thích ứng với thay đổi chiến lược thật sự.

## 17. Phản mẫu thường gặp khi quản lý Sprint Backlog

### 17.1. Đóng băng toàn bộ Sprint Backlog sau Planning

**Hậu quả:** Kiến thức mới không được đưa vào hành động; Developers có động cơ làm theo task cũ dù sai.  
**Cách cải thiện:** Giữ Sprint Goal, cho phép kế hoạch How tiến hóa và thương lượng phạm vi với Product Owner khi cần.

### 17.2. Không có Sprint Goal rõ, chỉ có danh sách ticket

**Hậu quả:** Khi có trở ngại, không biết ưu tiên PBI nào để tạo giá trị chung.  
**Cách cải thiện:** Làm rõ Why trong Sprint Planning và giữ Goal dễ nhìn trong bảng công việc.

### 17.3. Cập nhật bảng như một buổi báo cáo cho quản lý

**Hậu quả:** Mọi người tập trung làm đẹp trạng thái thay vì minh bạch về rủi ro và phối hợp.  
**Cách cải thiện:** Developers cập nhật vì cần điều hành công việc và đạt Sprint Goal; Daily Scrum không phải nơi kiểm tra chấm công.

### 17.4. Thêm mọi yêu cầu mới vào Sprint ngay lập tức

**Hậu quả:** Scope creep, gián đoạn, WIP tăng, Sprint Goal mất tập trung.  
**Cách cải thiện:** Product Owner quản lý nhu cầu mới trong Product Backlog; trao đổi những thay đổi thật sự cần cho Sprint Goal.

### 17.5. Dùng “có thêm hiểu biết” để tự ý bỏ chất lượng

**Hậu quả:** Lỗi, nợ kỹ thuật, vi phạm bảo mật hoặc mất dữ liệu bị che giấu dưới nhãn “thích ứng”.  
**Cách cải thiện:** Bảo vệ Definition of Done và quy tắc chất lượng, điều chỉnh phạm vi/dự báo thay vì hạ chuẩn.

### 17.6. Giữ mọi task quá chi tiết từ đầu tới cuối

**Hậu quả:** Kế hoạch thành khối tài liệu cứng, không theo kịp thực tế.  
**Cách cải thiện:** Lập kế hoạch đủ để bắt đầu, bổ sung chi tiết đúng lúc, xóa task không còn cần và giữ dấu vết thay đổi quan trọng.

### 17.7. Xếp hạng cá nhân theo số task hoặc story point

**Hậu quả:** Khuyến khích chia nhỏ giả, né việc phức tạp, ngại giúp đồng đội.  
**Cách cải thiện:** Dùng chỉ số flow và kết quả Done để học về hệ thống, không làm thước đo năng suất cá nhân thiếu ngữ cảnh.

### 17.8. Chỉ chờ đến Daily Scrum mới tháo blocker

**Hậu quả:** Vấn đề kỹ thuật hoặc vận hành bị chờ thêm gần một ngày dù có thể xử lý ngay.  
**Cách cải thiện:** Trao đổi, cập nhật kế hoạch và phối hợp ngay khi có thông tin đủ; Daily Scrum là nhịp kiểm tra chính thức, không phải thời điểm duy nhất được thích ứng.

### 17.9. Đóng việc chưa Done để báo cáo Sprint thành công

**Hậu quả:** Mất minh bạch, Increment không tin cậy, dự báo tương lai càng sai.  
**Cách cải thiện:** Phân biệt task đã làm với PBI/Increment đạt Done; công việc chưa Done được nhìn nhận thật và quay về Product Backlog khi Sprint kết thúc.

### 17.10. Ghi blocker mà không có hành động

**Hậu quả:** Bảng phản ánh tắc nghẽn nhưng không giúp giảm nó.  
**Cách cải thiện:** Mỗi trở ngại cần có đề xuất hành động, người cần phối hợp và mốc xem lại phù hợp với mức ảnh hưởng.

## 18. Một phương pháp thực hành ngắn để cập nhật mỗi ngày

Developers có thể dùng chu trình **Quan sát → Đánh giá → Quyết định → Cập nhật → Kiểm chứng**. Đây là kỹ thuật hỗ trợ, **không phải sự kiện Scrum bổ sung bắt buộc**.

| Bước | Câu hỏi | Đầu ra |
| --- | --- | --- |
| **Quan sát** | Điều gì mới xảy ra? Dữ liệu nào đủ tin cậy? | Sự kiện, blocker, kết quả kiểm thử hoặc phản hồi |
| **Đánh giá** | Sprint Goal và Definition of Done bị ảnh hưởng thế nào? | Phân biệt vấn đề kỹ thuật, phạm vi, chất lượng và ưu tiên |
| **Quyết định** | Developers tự điều chỉnh How hay cần trao đổi phạm vi với Product Owner? | Quyết định nằm đúng trách nhiệm |
| **Cập nhật** | Task, trạng thái PBI, thứ tự, phụ thuộc và kế hoạch tiếp theo thay đổi gì? | Sprint Backlog dễ hiểu, phản ánh thực tế |
| **Kiểm chứng** | Sau thay đổi, dấu hiệu nào chứng minh đã giảm rủi ro hoặc tiến gần Goal? | Kết quả test, Increment Done, thời gian chờ giảm, phản hồi người dùng |

### Mẫu câu dùng ngay

> “Hôm nay nhóm phát hiện **[bằng chứng mới]**. Điều này ảnh hưởng **[PBI/How/Done]** và **[mức ảnh hưởng đến Sprint Goal]**. Chúng tôi sẽ **[thay đổi cách làm hoặc trao đổi phạm vi]**, cập nhật Sprint Backlog tại **[vị trí]**, và kiểm tra kết quả bằng **[bằng chứng cụ thể]** vào **[mốc thích hợp]**.”

Cách diễn đạt này giúp tránh hai cực đoan: không nói gì cho đến cuối Sprint hoặc tạo một hệ thống giấy tờ lớn cho mọi điều chỉnh nhỏ.

## 19. Bài tập tình huống

### Bài tập A — Phân loại loại thay đổi

Giả sử Sprint Goal là “Học viên đang học dở mở lại đúng bài trên cùng thiết bị”. Hãy đánh dấu từng thay đổi là **How**, **What cần trao đổi Product Owner**, **yêu cầu chất lượng bắt buộc**, hoặc **ý tưởng để Product Backlog**, và giải thích:

1. Developers đổi thứ tự từ xây UI trước sang thử API end-to-end.
2. Nhóm phát hiện phải chặn truy cập tiến độ từ tài khoản không được phép.
3. Một bên liên quan đề nghị thêm chương trình giới thiệu bạn bè.
4. PBI về màn hình “đã hoàn thành” quá rộng, muốn chuyển phần nâng cao sang Sprint sau.
5. Hai Developers ghép cặp xử lý lỗi tích hợp thay vì mỗi người làm một task.
6. Nhóm đề xuất bỏ kiểm thử phân quyền để hoàn thành đúng ngày.

**Gợi ý:** (1), (5) chủ yếu thuộc How; (2) là điều kiện chất lượng bắt buộc; (3) về Product Backlog; (4) cần thương lượng What với Product Owner; (6) không được chấp nhận.

### Bài tập B — Đọc bảng bị tắc

Trong một Sprint, bảng có trạng thái:

| PBI | Trạng thái | Dấu hiệu |
| --- | --- | --- |
| A — Học tiếp đúng bài | In progress | API chưa có hợp đồng dữ liệu ổn định |
| B — Gợi ý bài đầu | In progress | UI gần xong nhưng chưa tích hợp |
| C — Theo dõi lỗi tiến độ | Review | Chờ xác nhận quy tắc dữ liệu riêng tư |
| D — Đồng bộ hai thiết bị | In progress | Có thay đổi cạnh tranh chưa được kiểm thử |

Nhóm mới hoàn tất rất ít PBI. Hãy viết ba thay đổi Sprint Backlog có thể giúp tiến gần Sprint Goal. Cần làm rõ PBI nào không phục vụ Goal, công việc nào đang bị chặn, điều kiện Done nào chưa đạt và phạm vi nào nên trao đổi với Product Owner.

**Gợi ý:** Không cần cố giữ cả bốn PBI trong trạng thái Doing. Nhóm có thể tập trung hoàn tất lát cắt A, tháo hợp đồng dữ liệu, làm rõ quy tắc quyền riêng tư của C; đưa phần không cần hoặc rủi ro cao vào cuộc trao đổi phạm vi với Product Owner. Không coi PBI nào Done chỉ vì một lớp kỹ thuật đã xong.

### Bài tập C — Quyết định trước một yêu cầu mới

Ngày thứ sáu, bên kinh doanh yêu cầu ngay tính năng email nhắc học vì có chiến dịch sắp bắt đầu. Developers đang sửa lỗi lưu tiến độ có nguy cơ mất dữ liệu.

Hãy trả lời:

1. Yêu cầu email có liên quan Sprint Goal hiện tại hay không?
2. Ai chịu trách nhiệm quyết định thứ tự Product Backlog?
3. Nếu đó là nghĩa vụ kinh doanh thực sự khẩn cấp, nhóm cần làm rõ thông tin gì trước khi điều chỉnh?
4. Developers có thể thay đổi How thế nào để bảo vệ Increment?
5. Nếu không thể đáp ứng mọi yêu cầu, cần truyền đạt đánh đổi ra sao?

**Gợi ý:** Phân biệt nhu cầu mới cần ưu tiên ở Product Backlog với rủi ro làm hại Sprint Goal và Definition of Done. Việc thêm scope không được mặc nhiên xảy ra chỉ vì có người cấp cao yêu cầu.

### Bài tập D — Viết một cập nhật Sprint Backlog

Dựa trên câu chuyện “Học tiếp”, hãy điền mẫu:

~~~text
Sprint Goal:
Các PBI đã chọn:
Trạng thái ban đầu:
Điều mới học được (nguồn và giới hạn bằng chứng):
Ảnh hưởng đến Sprint Goal:
Ảnh hưởng đến Definition of Done:
Đề xuất thay đổi How:
Đề xuất thương lượng What với Product Owner (nếu có):
Task và blocker mới:
Cách kiểm chứng rằng thay đổi có ích:
Ai cần trao đổi và khi nào:
~~~

Một câu trả lời tốt phải thể hiện **điều đã biết, điều chưa chắc, quyết định đúng trách nhiệm và cách bảo vệ chất lượng**.

### Bài tập E — Đánh giá lúc cuối Sprint

Cuối Sprint, PBI-A còn thiếu kiểm thử quyền truy cập; PBI-B đã đạt Done; PBI-C hoàn tất mã nhưng thiếu kiểm thử tích hợp.

1. PBI nào thực sự đạt Definition of Done?
2. Sprint Review có thể kiểm tra điều gì là Increment hoàn tất?
3. Những PBI chưa Done cần được xử lý ở Product Backlog ra sao?
4. Sprint Retrospective nên điều tra điểm nghẽn nào?
5. Có được chuyển toàn bộ việc chưa Done vào Sprint mới mà không xem ưu tiên không?

**Gợi ý:** Chỉ PBI-B được giả định là Done theo đề bài. A và C chưa Done. Product Owner cần xem xét Product Backlog dựa trên giá trị và thông tin mới; không tự động chuyển mọi phần dở dang như một cam kết bất biến.

## 20. Checklist trước và sau mỗi lần điều chỉnh

- [ ] Sprint Goal vẫn rõ, dễ nhìn và được sử dụng để đánh giá đề xuất thay đổi.
- [ ] Developers phân biệt thay đổi **How** với làm rõ/thương lượng **What**.
- [ ] Product Owner được trao đổi khi điều chỉnh phạm vi PBI có ảnh hưởng đến giá trị hoặc ưu tiên.
- [ ] Scrum Master hỗ trợ minh bạch và tháo gỡ trở ngại, không giao task thay Developers.
- [ ] Có bằng chứng hoặc lý do rõ cho thay đổi, tránh chạy theo ý kiến mới nhất.
- [ ] Bảng phản ánh trạng thái thực tế của PBI, task, phụ thuộc và việc đang bị chặn.
- [ ] Work in Progress không tăng vô tội vạ; nhóm ưu tiên đưa lát cắt giá trị đến Done.
- [ ] Các trường hợp mới về phân quyền, dữ liệu, chất lượng và bảo mật được xử lý đúng mức bắt buộc.
- [ ] Không bỏ Definition of Done hoặc gắn nhãn Done giả để bảo vệ tiến độ.
- [ ] Những ý tưởng chưa cần cho Sprint Goal được đưa về Product Backlog để Product Owner cân nhắc.
- [ ] Nhóm biết thay đổi nào cần truyền đạt cho bên liên quan và tác động lên dự báo.
- [ ] Kế hoạch có thể hành động trong ngày tiếp theo; không chỉ là danh sách trạng thái.
- [ ] Khi gần cuối Sprint, chỉ PBIs đạt Done được xem là Increment hoàn tất.
- [ ] Phần việc chưa Done được minh bạch và quay về Product Backlog để xem xét, không tự động là cam kết Sprint sau.
- [ ] Nhóm rút kinh nghiệm từ phản hồi kỹ thuật, sản phẩm và dòng công việc để cải tiến liên tục.

## 21. Tài liệu tham khảo và điểm ghi nhớ

Các nguồn nền tảng nên đọc trực tiếp:

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): định nghĩa Sprint Backlog, ba thành phần Why–What–How, Sprint Goal, quyền tự quản của Developers, Daily Scrum và Definition of Done.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/): giá trị ưu tiên con người và tương tác, phần mềm hoạt động, hợp tác và thích ứng với thay đổi.
- [The Kanban Guide](https://kanbanguides.org/): quản lý dòng công việc, WIP, throughput, cycle time và work item age — những kỹ thuật có thể dùng để cải thiện sự minh bạch về tiến độ.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): TDD, tích hợp thường xuyên, refactoring, phản hồi kỹ thuật và giao phần mềm nhỏ.

**Kết luận:** Sprint Backlog không phải lời hứa “mọi task ở Planning phải giữ nguyên và chắc chắn xong”. Nó là **kế hoạch sống do Developers sở hữu**, luôn gắn với **Sprint Goal**, các **PBIs đã chọn** và **cách tạo Increment đạt Definition of Done**. Khi học được điều mới, nhóm cập nhật cách làm, thương lượng phạm vi đúng trách nhiệm và minh bạch về rủi ro. Chính khả năng thích ứng có kỷ luật đó giúp Scrum Team giao giá trị tăng dần, phản hồi sớm và liên tục cải tiến mà không hy sinh chất lượng.
