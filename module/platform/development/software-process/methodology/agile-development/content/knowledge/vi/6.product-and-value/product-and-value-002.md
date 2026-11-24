# Xác định vấn đề, nhóm người dùng và giá trị cần tạo

## 1. Vì sao phải bắt đầu từ vấn đề thay vì tính năng?

Trong phát triển phần mềm theo **Agile**, việc giao sản phẩm sớm, tăng dần và nhận phản hồi liên tục chỉ thực sự hiệu quả khi nhóm đang giải quyết một vấn đề đáng giải quyết. Viết được nhiều tính năng không tự động đồng nghĩa với tạo ra giá trị: người dùng có thể không sử dụng chúng, một công việc vốn đơn giản lại trở nên phức tạp hơn, hoặc tổ chức phải duy trì một giải pháp tốn kém cho nhu cầu hiếm gặp.

Ví dụ, một phòng khám yêu cầu nhóm xây dựng bộ lọc bác sĩ theo 20 tiêu chí. Nếu nhóm lập tức triển khai, sản phẩm có thể đáp ứng đúng mô tả nhưng không cải thiện việc đặt lịch. Khi quan sát thực tế, nhóm có thể nhận ra trở ngại lớn nhất là **người bệnh không biết khung giờ nào còn trống và phải gọi điện nhiều lần để xác nhận**. Một luồng xem giờ trống đáng tin cậy và đặt lịch trực tiếp có thể giải quyết vấn đề tốt hơn bộ lọc phức tạp.

Trước khi viết user story, sắp xếp backlog hay chọn Scrum, Kanban hoặc XP để phối hợp, nhóm cần trả lời ba câu hỏi:

1. **Vấn đề nào đang xảy ra?** Ai gặp khó khăn, trong tình huống nào, hậu quả ra sao và có bằng chứng gì?
2. **Nhóm người dùng nào cần được phục vụ?** Họ có mục tiêu, hành vi, điều kiện sử dụng và ràng buộc gì? Ai mua, ai quyết định và ai bị ảnh hưởng?
3. **Giá trị cần tạo là gì?** Điều gì sẽ tốt lên cho người dùng và tổ chức, và làm sao biết được sự cải thiện đã xảy ra?

Ba câu hỏi này gắn trực tiếp với mục tiêu của module **AGILE_DEVELOPMENT**: phát triển thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Việc xác định vấn đề và giá trị không phải hoạt động chỉ làm một lần khi khởi động dự án; nhóm cần xem xét lại khi có bằng chứng mới.

**Kết quả học tập:** Sau bài này, người học có thể phân biệt vấn đề với giải pháp, xác định và phân đoạn nhóm người dùng, thu thập bằng chứng, mô tả giá trị mong muốn, tạo giả thuyết kiểm chứng được và chuyển kết quả khám phá thành công việc trong Product Backlog.

## 2. Phân biệt vấn đề, nhu cầu, triệu chứng, giải pháp và giá trị

Nhiều cuộc thảo luận về sản phẩm bị rối vì các bên dùng chung một từ cho những khái niệm khác nhau.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ ở sản phẩm đặt lịch khám |
|---|---|---|
| **Bối cảnh (context)** | Người dùng đang làm gì, ở đâu, trong điều kiện nào? | Đặt lịch trên điện thoại vào buổi tối khi tổng đài đã ngừng làm việc. |
| **Mục tiêu/nhu cầu (need)** | Người dùng muốn đạt kết quả gì? | Có một buổi khám phù hợp và được xác nhận rõ ràng. |
| **Vấn đề (problem)** | Điều gì cản trở mục tiêu hoặc gây tổn thất? | Không biết giờ nào còn trống, phải gọi lại hoặc thử nhiều lần. |
| **Triệu chứng (symptom)** | Dấu hiệu nào đang được quan sát? | Nhiều cuộc gọi hỏi giờ trống; nhiều phiên đặt lịch bị bỏ dở. |
| **Nguyên nhân giả định** | Vì sao tình trạng đó có thể xảy ra? | Dữ liệu lịch trống chưa được đồng bộ giữa các kênh. |
| **Giải pháp (solution)** | Ta đề xuất thay đổi điều gì? | Hiển thị giờ trống được đồng bộ và xác nhận đặt lịch trực tiếp. |
| **Giá trị (value)** | Ai được cải thiện điều gì và như thế nào? | Người bệnh đỡ mất thời gian; nhân viên giảm gọi lại; phòng khám ít đặt trùng. |

**“Thêm bộ lọc bác sĩ” là một giải pháp được đề xuất, chưa phải mô tả vấn đề.** Giải pháp đó vẫn có thể hữu ích, nhưng nhóm phải kiểm tra nó giúp người dùng đạt mục tiêu nào và có phải ưu tiên cần giải quyết ngay không.

Một triệu chứng cũng có thể xuất phát từ nhiều nguyên nhân. Số người bỏ dở đặt lịch tăng có thể do giao diện khó dùng, không còn khung giờ phù hợp, yêu cầu xác thực quá rườm rà, lỗi kỹ thuật hoặc thông tin giá chưa rõ. Nhóm không nên biến nguyên nhân đầu tiên được nêu thành kết luận khi chưa kiểm tra.

### 2.1. Nhu cầu của người dùng khác nhiệm vụ được giao cho đội phát triển

Khách hàng có thể nói: “Chúng tôi cần một ứng dụng di động”. Nhu cầu sâu hơn có thể là: “Khách hàng muốn theo dõi đơn hàng mà không phải gọi tổng đài”. Trong một số tình huống, cải thiện website hiện tại, thông báo trạng thái hoặc tích hợp với kênh đang dùng sẽ tạo giá trị nhanh hơn việc xây ứng dụng mới.

Những câu hỏi khám phá hữu ích:

- Người dùng đang cố hoàn thành công việc gì và kết quả nào khiến họ hài lòng?
- Họ đang làm việc đó theo cách nào, bước nào mất thời gian hoặc thường thất bại?
- Vấn đề xuất hiện ở đâu, thường xuyên đến mức nào và hậu quả ra sao?
- Họ đang dùng giải pháp thay thế nào? Những điểm chưa tốt của cách đó là gì?
- Nếu vấn đề giảm đi, hành vi hoặc kết quả nào có thể quan sát được?
- Có ràng buộc nào về chi phí, quyền riêng tư, an toàn, khả năng tiếp cận hoặc vận hành?

Các câu hỏi giúp đặt hướng nghiên cứu; **câu trả lời của một người không tự động trở thành bằng chứng đại diện cho tất cả người dùng**.

## 3. Xác định đúng nhóm người dùng

Một sản phẩm thường phục vụ nhiều vai trò với mục tiêu và ràng buộc khác nhau. Câu “sản phẩm dành cho tất cả mọi người” quá rộng để hỗ trợ quyết định thiết kế, nghiên cứu hay ưu tiên backlog.

### 3.1. Phân biệt người dùng, người mua và các bên liên quan

| Vai trò | Ý nghĩa | Ví dụ |
|---|---|---|
| **End user** | Người trực tiếp tương tác với phần mềm để làm việc. | Người bệnh chọn giờ khám; nhân viên tiếp nhận xác nhận lịch. |
| **Customer/buyer** | Cá nhân hoặc tổ chức mua hoặc trả tiền sử dụng sản phẩm. | Ban quản lý phòng khám mua hệ thống đặt lịch. |
| **Decision-maker** | Người có quyền chọn, triển khai hoặc tiếp tục đầu tư giải pháp. | Giám đốc vận hành phê duyệt nhà cung cấp. |
| **Stakeholder** | Người ảnh hưởng hoặc bị ảnh hưởng bởi sản phẩm. | Bác sĩ, nhân viên tổng đài, bộ phận bảo mật, đội vận hành. |
| **Beneficiary** | Người được hưởng lợi dù không trực tiếp thao tác. | Người thân được hỗ trợ sắp xếp lịch theo quyền được cấp. |

Trong sản phẩm B2B, **người mua không nhất thiết là người sử dụng**. Phần mềm có thể đáp ứng yêu cầu mua sắm của quản lý nhưng khiến nhân viên mất quá nhiều thao tác. Ngược lại, một tính năng được người dùng thích nhưng không đáp ứng yêu cầu bảo mật hoặc không thể vận hành với chi phí chấp nhận được cũng khó tồn tại lâu dài.

Nhóm nên làm rõ ai góp ý về **tính hữu ích**, ai xác nhận **phù hợp quy trình**, ai đánh giá **rủi ro** và ai quyết định **đầu tư**. Các tiếng nói này quan trọng nhưng không hoàn toàn thay thế nhau.

### 3.2. Phân đoạn theo mục tiêu, hành vi và bối cảnh

Phân đoạn người dùng (user segmentation) giúp tìm ra những nhu cầu đủ khác biệt để dẫn đến quyết định sản phẩm khác nhau. Ngoài đặc điểm nhân khẩu học, những tiêu chí thường hữu ích trong phần mềm gồm:

- **Công việc muốn hoàn thành:** đặt lịch lần đầu, đặt lịch tái khám, đổi lịch hoặc xác nhận lịch cho người khác.
- **Hành vi và tần suất:** người dùng mới, người dùng thường xuyên, người dùng chỉ có một lượt sử dụng.
- **Bối cảnh thao tác:** điện thoại ngoài giờ hành chính hay máy tính tại quầy; mạng yếu hay ổn định.
- **Mức độ thành thạo:** quen hoặc ít quen với quy trình và công nghệ.
- **Ràng buộc tiếp cận:** nhu cầu dùng bàn phím, trình đọc màn hình, phóng to chữ hoặc hỗ trợ ngôn ngữ.
- **Rủi ro nghiệp vụ:** chỉ xem thông tin khác với đặt lịch, thanh toán hoặc sửa thông tin cá nhân.

Ví dụ, ba nhóm người dùng ban đầu của hệ thống đặt lịch có thể được mô tả như sau:

| Nhóm giả định | Công việc chính | Trở ngại cần xác minh |
|---|---|---|
| Người bệnh đặt lịch lần đầu | Tìm đúng chuyên khoa và giờ khám phù hợp. | Không biết nên chọn dịch vụ nào hoặc giờ trống không rõ ràng. |
| Người bệnh quay lại | Đặt tái khám hoặc đổi lịch thuận tiện. | Phải nhập lại thông tin và lặp nhiều bước. |
| Nhân viên tiếp nhận | Điều phối lịch chính xác và xử lý thay đổi kịp thời. | Lịch giữa các kênh không đồng bộ, nhiều cuộc gọi xác nhận. |

Đây là **giả thuyết phân đoạn**, chưa phải kết luận nghiên cứu. Nhóm cần dùng dữ liệu và phỏng vấn thực tế để kiểm tra.

### 3.3. Chọn nhóm ưu tiên mà không bỏ sót nhóm bị ảnh hưởng

Không nhất thiết phải giải quyết mọi tình huống trong phiên bản đầu tiên. Nhóm có thể chọn một nhóm mục tiêu dựa trên mức độ nghiêm trọng của vấn đề, tần suất, quy mô, giá trị chiến lược, khả năng tiếp cận để nghiên cứu, tác động nếu không giải quyết và các ràng buộc của sản phẩm.

**Nhóm dễ tiếp cận để phỏng vấn chưa chắc là nhóm cần ưu tiên nhất.** Người dùng ít dùng công nghệ hoặc có nhu cầu hỗ trợ khả năng tiếp cận có thể ít xuất hiện trong dữ liệu trực tuyến nhưng lại chịu ảnh hưởng lớn nếu quy trình mới thay thế hoàn toàn kênh cũ.

Persona có thể giúp nhóm ghi nhớ mục tiêu và bối cảnh người dùng khi nó **được tổng hợp từ bằng chứng**. Không nên tạo một nhân vật hư cấu với quá nhiều chi tiết rồi coi đó là dữ liệu. Một hồ sơ gọn thường chỉ cần công việc chính, bối cảnh, hành vi, trở ngại và nguồn quan sát hỗ trợ.

## 4. Khám phá và kiểm chứng vấn đề bằng bằng chứng

**Product discovery (khám phá sản phẩm)** nhằm giảm bất định về người dùng, vấn đề, giá trị và giải pháp. Trong Agile, việc khám phá có thể diễn ra song song với phát triển; nhóm thử những phần nhỏ, học từ phản hồi, rồi điều chỉnh lựa chọn tiếp theo.

### 4.1. Phân biệt giả định với quan sát

| Phát biểu | Bản chất | Hành động tiếp theo |
|---|---|---|
| “Người bệnh không thích gọi điện.” | Giả định về cảm nhận. | Phỏng vấn về lần đặt lịch gần nhất và lý do phải gọi. |
| “Nhiều cuộc gọi trong tuần hỏi giờ khám.” | Quan sát có thể kiểm chứng nếu có dữ liệu. | Xác định số liệu, mẫu, thời gian và nguyên nhân liên hệ. |
| “Mọi người sẽ dùng màn hình xem giờ trống.” | Giả thuyết về hành vi tương lai. | Cho thử nguyên mẫu hoặc chức năng tối thiểu, quan sát thao tác. |
| “Sau thay đổi, tỷ lệ hoàn tất tăng.” | Kết quả đo cần xem thiết kế đánh giá. | Kiểm tra cùng cách đo, nhóm người dùng và những thay đổi đồng thời. |

Bằng chứng hữu ích cần có **nguồn, thời điểm, phạm vi và giới hạn**. Một phản hồi riêng lẻ vẫn rất giá trị để khám phá vấn đề, nhưng không chứng minh tần suất trong toàn bộ quần thể.

### 4.2. Chọn phương pháp nghiên cứu phù hợp

| Phương pháp | Phù hợp để hiểu | Giới hạn thường gặp |
|---|---|---|
| **Phỏng vấn người dùng** | Động lực, mục tiêu, trải nghiệm và cách xử lý hiện tại. | Lời kể có thể khác hành vi; câu hỏi dẫn dắt gây thiên lệch. |
| **Quan sát công việc/usability testing** | Các bước thao tác, điểm mắc kẹt và vấn đề giao diện. | Môi trường thử có thể không phản ánh bối cảnh thực. |
| **Phân tích dữ liệu sản phẩm** | Tần suất, hành trình, tỷ lệ hoàn thành, xu hướng. | Biết điều gì xảy ra chưa đủ để biết vì sao. |
| **Nhật ký hỗ trợ và sự cố** | Vấn đề lặp lại, tác động, mức độ khẩn cấp. | Người liên hệ hỗ trợ có thể không đại diện cho mọi người dùng. |
| **Khảo sát** | Mức độ phổ biến của trải nghiệm trong một mẫu xác định. | Chọn mẫu, cách hỏi và tỷ lệ phản hồi ảnh hưởng kết luận. |
| **Thử nguyên mẫu** | Mức độ hiểu, khả năng thao tác và kỳ vọng ban đầu. | Dùng được trong thử nghiệm không bảo đảm sẽ dùng lâu dài. |

Kết hợp phương pháp **định tính** với **định lượng** thường tạo góc nhìn đầy đủ hơn. Dữ liệu có thể cho thấy nhiều người dừng ở bước chọn giờ; quan sát giúp phát hiện họ không hiểu giờ hiển thị đã có người đặt hay chưa.

### 4.3. Hỏi về hành vi thật thay vì xin lời hứa

Thay vì hỏi “Bạn có thích một bộ lọc thông minh không?”, hãy hỏi:

> “Lần gần nhất bạn đặt lịch khám diễn ra như thế nào? Bạn thực hiện những bước nào, điều gì làm bạn mất thời gian và cuối cùng giải quyết ra sao?”

Có thể tiếp tục với “Điều gì khiến bước đó khó?”, “Bạn đã thử cách khác chưa?”, “Nếu không giải quyết được thì hậu quả gì?”, “Ai còn tham gia quyết định?”. Các câu hỏi gắn với sự kiện cụ thể giúp giảm nguy cơ người được hỏi đồng ý xã giao với một ý tưởng mới.

Khi ghi âm, quan sát hoặc sử dụng dữ liệu sản phẩm, cần tuân thủ quy định về đồng ý tham gia, giới hạn mục đích, quyền truy cập và bảo vệ thông tin cá nhân. Với ví dụ y tế, không thu thập dữ liệu sức khỏe nhạy cảm chỉ để kiểm tra một giao diện nếu dữ liệu giả lập hoặc đã ẩn danh là đủ.

### 4.4. Tìm nguyên nhân gốc, nhưng không nhầm giả thuyết với kết luận

Các cách đặt câu hỏi như “5 Whys”, bản đồ hành trình hoặc sơ đồ nguyên nhân–kết quả giúp nhóm nhìn sâu hơn triệu chứng:

1. Người bệnh gọi tổng đài nhiều lần. **Vì sao?** Có thể họ không chắc giờ nào trống.
2. Họ không chắc giờ nào trống. **Vì sao?** Có thể trang web không hiển thị lịch cập nhật.
3. Trang web không cập nhật. **Vì sao?** Có thể các kênh đặt lịch đang dùng cơ chế đồng bộ khác nhau.

Chuỗi trên là **giả thuyết để kiểm tra**, chưa phải chẩn đoán chắc chắn. Nhóm cần quan sát trải nghiệm, kiểm tra dữ liệu đồng bộ và trao đổi với người vận hành trước khi quyết định thay đổi hệ thống.

## 5. Viết problem statement rõ ràng

**Problem statement** mô tả vấn đề, người chịu ảnh hưởng và kết quả mong muốn, đồng thời để ngỏ cách giải quyết. Một cấu trúc có thể dùng:

> **[Nhóm người dùng]**, khi **[bối cảnh/công việc]**, gặp **[trở ngại cụ thể]**, dẫn đến **[hậu quả]**. Bằng chứng hiện có là **[quan sát/dữ liệu và phạm vi]**. Nhóm cần cải thiện **[kết quả mong muốn]** trong khi bảo đảm **[ràng buộc quan trọng]**.

**Ví dụ giả định:**

> Người bệnh đặt lịch ngoài giờ hành chính, khi cần chọn buổi khám phù hợp, không nhìn thấy những khung giờ trống đáng tin cậy nên phải thử lại hoặc gọi tổng đài vào hôm sau. Quan sát các phiên sử dụng thử và phản hồi hỗ trợ ban đầu cho thấy bước chọn giờ gây lúng túng. Nhóm cần giúp họ hoàn tất một lịch hẹn hợp lệ nhanh hơn, đồng thời tránh đặt trùng và bảo vệ dữ liệu cá nhân.

Trong công việc thực tế, câu “quan sát ban đầu” phải được thay bằng nguồn và số liệu khi có dữ liệu. Ví dụ này không phải kết quả nghiên cứu thật.

Một mô tả vấn đề tốt có các đặc điểm:

- Nói rõ **ai** gặp vấn đề và **ở bối cảnh nào**.
- Nêu **trở ngại** và **hậu quả**, chưa khóa vào một tính năng cụ thể.
- Đánh dấu rõ điều **đã biết** và điều **cần kiểm chứng**.
- Có kết quả mong muốn quan sát được và ràng buộc quan trọng.
- Đủ hẹp để nhóm có thể thử cải thiện trong một vài phần bàn giao.

Câu “Cần xây dashboard dùng AI để tăng tương tác” vẫn chủ yếu là **ý tưởng giải pháp**. Cần làm rõ ai thiếu thông tin nào để quyết định, quá trình hiện tại có trở ngại gì và vì sao dashboard có khả năng giúp ích.

## 6. Định nghĩa giá trị từ nhiều góc nhìn

**Giá trị** là sự cải thiện có ý nghĩa đối với người dùng, tổ chức hoặc bên chịu tác động khi vấn đề được giải quyết. Giá trị không nhất thiết chỉ là doanh thu và không thể suy ra trực tiếp từ số tính năng đã phát hành.

### 6.1. Những loại giá trị thường gặp

| Góc nhìn | Giá trị cần quan tâm | Dấu hiệu có thể đo |
|---|---|---|
| **Người dùng** | Tiết kiệm thời gian, giảm công sức, hoàn thành công việc dễ hơn, tăng sự tin cậy. | Tỷ lệ hoàn thành tác vụ, thời gian thực hiện, số lần phải làm lại. |
| **Kinh doanh** | Tăng khả năng phục vụ, duy trì khách hàng, giảm chi phí phù hợp. | Chi phí xử lý một yêu cầu, tỷ lệ khách quay lại, tỷ lệ đặt lịch thành công. |
| **Vận hành** | Giảm lỗi thủ công, giảm hỗ trợ lặp lại, tăng tính ổn định. | Số yêu cầu xử lý bằng tay, tỷ lệ đặt trùng, số sự cố. |
| **An toàn và tuân thủ** | Bảo vệ dữ liệu, giảm rủi ro, đáp ứng yêu cầu bắt buộc. | Lỗi kiểm soát, sự cố bảo mật, mức đáp ứng tiêu chí tiếp cận. |
| **Dài hạn** | Giữ khả năng thay đổi, chất lượng kỹ thuật và học hỏi. | Lỗi hồi quy, thời gian thay đổi an toàn, thời gian phục hồi sự cố. |

Cần làm rõ **giá trị cho ai** vì cải thiện cho một phía có thể gây bất lợi cho phía khác. Ví dụ, giảm thời gian xử lý ở quầy bằng cách bắt người bệnh nhập rất nhiều dữ liệu có thể chuyển gánh nặng từ nhân viên sang người bệnh. Nhóm nên đánh giá tác động tổng thể.

### 6.2. Output, outcome và impact

- **Output (đầu ra):** những thứ nhóm bàn giao, như màn hình chọn giờ, API lịch trống hoặc bản phát hành.
- **Outcome (kết quả):** sự thay đổi hành vi hoặc trải nghiệm, chẳng hạn người dùng hoàn tất đặt lịch dễ hơn, ít phải gọi điện hoặc ít gặp lỗi.
- **Impact (tác động rộng hơn):** cải thiện khả năng tiếp cận dịch vụ, giảm chi phí vận hành hoặc tăng mức hài lòng bền vững.

~~~mermaid
flowchart LR
    A[Vấn đề có bằng chứng] --> B[Giả thuyết giải pháp]
    B --> C[Output: phần mềm đã bàn giao]
    C --> D[Outcome: hành vi và kết quả]
    D --> E[Impact: giá trị dài hạn]
    D --> F[Phản hồi và dữ liệu]
    F --> B
~~~

“Đã phát hành màn hình đặt lịch” là output. “Người bệnh đặt được lịch mà không cần gọi điện” là outcome. “Phòng khám phục vụ thuận tiện hơn mà không tăng gánh nặng vận hành” là impact có thể kỳ vọng nhưng cần thời gian và bằng chứng để xác nhận.

**Đo output cho biết nhóm có bàn giao hay không; đo outcome giúp kiểm tra phần bàn giao có giải quyết vấn đề hay không.** Cả hai đều hữu ích nhưng không thể dùng thay nhau.

### 6.3. Định nghĩa chỉ số trước khi triển khai

| Vai trò thước đo | Chỉ số minh họa | Ý nghĩa và điều kiện |
|---|---|---|
| **Outcome chính** | Tỷ lệ phiên bắt đầu đặt lịch dẫn đến xác nhận lịch hợp lệ. | Định nghĩa rõ “phiên”, “bắt đầu” và “xác nhận hợp lệ”. |
| **Outcome hỗ trợ** | Thời gian từ lúc chọn dịch vụ đến lúc đặt lịch thành công. | So sánh theo nhóm người dùng và bối cảnh tương đồng. |
| **Outcome hỗ trợ** | Số cuộc gọi hỏi giờ trống trên một lượng yêu cầu tương đương. | Tính đến thay đổi lưu lượng và kênh tiếp nhận. |
| **Guardrail (chỉ số bảo vệ)** | Tỷ lệ đặt trùng, hủy bất thường, lỗi hệ thống, sự cố dữ liệu cá nhân. | Không để tốc độ cải thiện bằng cách làm giảm độ tin cậy và an toàn. |

Công thức ví dụ:

~~~text
Tỷ lệ hoàn tất đặt lịch (%)
  = Số phiên đặt lịch được xác nhận hợp lệ
    / Số phiên bắt đầu quy trình đặt lịch
    × 100
~~~

**Đơn vị đo phải rõ ràng.** Một người có thể bắt đầu nhiều phiên; tùy mục tiêu, nhóm có thể đo theo phiên, theo người hoặc theo yêu cầu. Nếu đổi định nghĩa ở giữa giai đoạn, các số liệu không còn so sánh trực tiếp được.

Khi chọn chỉ số, cần ghi:

1. **Baseline:** giá trị ban đầu trước thay đổi, dùng cùng cách đo.
2. **Hướng cải thiện mong muốn:** tăng, giảm hoặc nằm trong ngưỡng phù hợp.
3. **Phân đoạn áp dụng:** nhóm người dùng và bối cảnh đang đánh giá.
4. **Khung thời gian:** khi nào bắt đầu và kết thúc đánh giá.
5. **Guardrail:** các điều kiện chất lượng và an toàn không được xấu đi.

Một mục tiêu định lượng cần có căn cứ; không nên tự đặt tỷ lệ tăng bất kỳ rồi mặc định đạt tỷ lệ đó là bằng chứng tính năng đã thành công.

## 7. Xây dựng giả thuyết giá trị có thể kiểm chứng

Khi đã xác định một vấn đề đáng quan tâm, nhóm còn phải kiểm tra **giải pháp nào có thể tạo ra outcome mong muốn**. Giả thuyết giá trị nên kết nối nhóm người dùng, thay đổi đề xuất, kết quả kỳ vọng và cách kiểm chứng.

Mẫu:

> Chúng tôi tin rằng với **[nhóm người dùng]** đang **[làm công việc cụ thể]**, nếu cung cấp **[thay đổi/giải pháp giả định]**, họ sẽ **[đạt hành vi hoặc kết quả tốt hơn]**. Chúng tôi sẽ kiểm tra bằng **[thử nghiệm]**, theo dõi **[chỉ số và phản hồi]**, đồng thời bảo đảm **[guardrail]**.

Ví dụ:

> Với người bệnh đặt lịch ngoài giờ hành chính, nếu hiển thị khung giờ còn trống được đồng bộ và cho phép xác nhận đặt lịch trực tiếp, chúng tôi kỳ vọng tỷ lệ hoàn tất đặt lịch tăng và số cuộc gọi hỏi giờ trống giảm. Nhóm sẽ thử trên phạm vi giới hạn, theo dõi tỷ lệ hoàn tất, thời gian đặt lịch và phản hồi người bệnh, đồng thời kiểm tra lỗi đặt trùng.

Một giả thuyết chỉ thực sự hữu ích khi nhóm có thể xác định điều gì sẽ được quan sát và **kết quả nào có thể khiến nhóm thay đổi hoặc bác bỏ ý tưởng**. “Tạo trải nghiệm tuyệt vời” là kỳ vọng tốt nhưng chưa đủ rõ để thử nghiệm.

### 7.1. Bốn loại giả định quan trọng

| Loại giả định | Câu hỏi | Cách giảm bất định |
|---|---|---|
| **Giá trị (value)** | Người dùng có thật sự cần và sẽ dùng giải pháp không? | Phỏng vấn hành vi, thử nguyên mẫu, đo sử dụng thực tế. |
| **Khả dụng (usability)** | Họ có thể hiểu, tiếp cận và hoàn thành tác vụ không? | Thử nghiệm khả năng sử dụng, kiểm tra trường hợp biên và tiếp cận. |
| **Khả thi (feasibility)** | Nhóm có thể triển khai đáng tin cậy với công nghệ và nguồn lực hiện tại không? | Spike kỹ thuật, kiểm tra dữ liệu và tích hợp. |
| **Khả năng tồn tại (viability)** | Giải pháp có phù hợp chi phí, chiến lược, vận hành và ràng buộc tổ chức không? | Phân tích chi phí, rủi ro, yêu cầu pháp lý và trao đổi với bên quyết định. |

Các loại giả định có liên hệ với nhau. Một tính năng hữu ích nhưng không thể đồng bộ lịch chính xác sẽ không đem lại giá trị bền vững. Một tính năng khả thi kỹ thuật nhưng làm lộ dữ liệu nhạy cảm cũng không nên được triển khai theo cách đó.

### 7.2. Chọn thử nghiệm nhỏ nhất để học điều quan trọng nhất

Không phải mọi giả thuyết đều cần lập trình:

- **Phỏng vấn hoặc quan sát:** kiểm tra vấn đề, hoàn cảnh và mức ảnh hưởng.
- **Nguyên mẫu tương tác:** kiểm tra người dùng có hiểu luồng và thực hiện được thao tác không.
- **Thử nghiệm thủ công có kiểm soát:** học về nhu cầu trước khi tự động hóa toàn bộ.
- **Spike kỹ thuật:** kiểm chứng khả năng tích hợp, độ chính xác dữ liệu hoặc giới hạn hiệu năng.
- **Pilot/phát hành giới hạn:** kiểm tra hành vi thực tế và tác động vận hành ở phạm vi nhỏ.
- **Thử nghiệm so sánh có thiết kế phù hợp:** đánh giá tác động của những phương án khác nhau khi có điều kiện so sánh đáng tin.

**MVP (Minimum Viable Product)** có thể là phiên bản đủ nhỏ để mang lại giá trị hoặc kiểm tra giả định cốt lõi qua phản hồi thực. “Minimum” không có nghĩa bỏ qua an toàn, quyền riêng tư hoặc chất lượng thiết yếu. Với đặt lịch khám, phiên bản giới hạn vẫn cần kiểm soát đặt trùng, sai giờ và quyền truy cập.

Khi phân tích kết quả, nhóm cần xem xét thiên lệch mẫu, số quan sát, yếu tố mùa vụ và các thay đổi diễn ra đồng thời. Dữ liệu sớm thường giúp ra **quyết định tiếp theo**, không phải lúc nào cũng cho phép kết luận nhân quả chắc chắn.

## 8. Kết nối phát hiện với Product Backlog

Agile tạo giá trị theo từng phần nhỏ. Nhóm đưa các vấn đề đã được ưu tiên và giả thuyết cần kiểm chứng vào **Product Backlog**, rồi làm rõ thành những hạng mục đủ nhỏ để phát triển và đánh giá.

~~~mermaid
flowchart TD
    A[Mục tiêu sản phẩm] --> B[Nhóm người dùng ưu tiên]
    B --> C[Vấn đề và bằng chứng]
    C --> D[Outcome và chỉ số]
    D --> E[Giả thuyết giải pháp]
    E --> F[Backlog được ưu tiên]
    F --> G[Thử nghiệm hoặc Increment nhỏ]
    G --> H[Phản hồi và điều chỉnh]
    H --> C
~~~

Backlog không nên chỉ là danh sách tính năng đã được yêu cầu. Nó có thể chứa hoạt động nghiên cứu, thử nghiệm kỹ thuật, khắc phục lỗi, cải tiến chất lượng và phát triển chức năng; thứ tự ưu tiên phản ánh giá trị, mức khẩn cấp, độ bất định và chi phí tương đối.

### 8.1. Viết user story từ nhu cầu thật

Mẫu thường dùng:

> Với vai trò là **[người dùng]**, tôi muốn **[khả năng]** để **[lợi ích/kết quả]**.

Ví dụ:

> Với vai trò là người bệnh đặt lịch ngoài giờ hành chính, tôi muốn xem các khung giờ còn trống của chuyên khoa đã chọn để có thể đặt lịch mà không phải gọi tổng đài.

User story là lời nhắc để **trao đổi**, không phải đặc tả kỹ thuật hoàn chỉnh. Nhóm phải làm rõ tiêu chí chấp nhận và những ràng buộc cần thiết, chẳng hạn:

1. Chỉ hiển thị những khung giờ hiện có thể đặt.
2. Nếu hai người cùng chọn một giờ, hệ thống không tạo hai lịch trùng nhau; người đến sau được thông báo và chọn lại.
3. Sau khi đặt thành công, người dùng nhận xác nhận đúng địa điểm, ngày và giờ.
4. Khi không tải được lịch, hệ thống không đưa ra xác nhận giả.
5. Dữ liệu cá nhân được xử lý theo quyền truy cập đã thống nhất.

Ví dụ trên cần được kiểm tra với nghiệp vụ và kiến trúc thực tế, không thể lấy làm đặc tả triển khai cho mọi phòng khám.

### 8.2. Chia nhỏ theo phần giá trị và phần rủi ro

| Giai đoạn | Phần bàn giao hoặc thử nghiệm | Câu hỏi được học |
|---|---|---|
| 1 | Nguyên mẫu chọn chuyên khoa và giờ; cho người dùng thử. | Người dùng có hiểu cách tìm giờ không? |
| 2 | Luồng xem giờ trống đáng tin cậy trong phạm vi giới hạn. | Dữ liệu từ các kênh có đồng bộ đúng không? |
| 3 | Đặt và xác nhận lịch hợp lệ, xử lý trùng lịch. | Người dùng có hoàn tất mà không cần gọi điện không? |
| 4 | Mở rộng phạm vi và theo dõi hành vi thực tế. | Giá trị có duy trì khi quy mô sử dụng tăng không? |
| 5 | Ưu tiên đổi lịch, nhắc lịch hoặc tìm kiếm theo phản hồi. | Vấn đề quan trọng tiếp theo là gì? |

Một số giai đoạn là thử nghiệm khám phá, một số tạo **Increment** có thể dùng được. Nhóm cần phân biệt trạng thái của chúng và chỉ tính phần mềm đạt **Definition of Done** là hoàn thành.

### 8.3. Ưu tiên công việc theo giá trị và ràng buộc

Nhóm nên cùng xem:

- **Giá trị kỳ vọng:** vấn đề được giảm đến đâu, cho ai và mức ảnh hưởng có đáng kể không?
- **Bằng chứng:** độ tin cậy của những điều đã biết và phần còn là giả định.
- **Mức khẩn cấp:** thời gian, nghĩa vụ bắt buộc hoặc chi phí trì hoãn.
- **Nỗ lực và phụ thuộc:** công sức phát triển, kỹ năng cần có và tích hợp liên quan.
- **Rủi ro:** bảo mật, dữ liệu, khả năng tiếp cận, chất lượng, vận hành và bảo trì.

Ma trận giá trị so với nỗ lực hoặc cách chấm điểm khác có thể hỗ trợ thảo luận. Điểm số phụ thuộc giả định đầu vào, vì vậy không nên trở thành quyết định tự động.

## 9. Tình huống xuyên suốt: sản phẩm đặt lịch khám

**Toàn bộ ví dụ dưới đây là giả định để minh họa phương pháp, không phải kết quả nghiên cứu thực tế.**

### 9.1. Từ yêu cầu ban đầu đến câu hỏi đúng

Ban quản lý nói: “Hãy xây bộ lọc thông minh cho phép người bệnh tìm bác sĩ nhanh hơn.” Nhóm làm rõ kết quả mà quản lý mong muốn: giảm số người bỏ dở đặt lịch và giảm tải cuộc gọi cho tổng đài. Nhóm không phủ nhận ý tưởng bộ lọc nhưng vẫn kiểm tra xem vướng mắc chính nằm ở tìm bác sĩ, chọn giờ hay xác nhận lịch.

### 9.2. Tìm nhóm mục tiêu và bằng chứng

Nhóm tạm ưu tiên người bệnh đặt lịch trên điện thoại ngoài giờ hành chính, kết hợp quan sát hành trình dùng thử, phân tích phiên đặt lịch có quản lý quyền truy cập phù hợp và trao đổi với nhân viên tiếp nhận.

| Quan sát giả định | Hàm ý cần kiểm tra |
|---|---|
| Người dùng thường quay lại bước chọn giờ. | Trạng thái giờ trống có thể khó hiểu hoặc không đáng tin. |
| Nhiều người hỏi tổng đài còn giờ nào. | Cách công bố lịch hoặc chất lượng dữ liệu có thể chưa tốt. |
| Một số yêu cầu đặt lịch không được xác nhận ngay. | Cần kiểm tra luồng đồng bộ và thông báo. |

Các quan sát gợi ý vấn đề nhưng chưa chứng minh bộ lọc là không cần thiết.

### 9.3. Thống nhất vấn đề và giá trị

**Problem statement:** Người bệnh đặt lịch ngoài giờ hành chính khó xác định và xác nhận khung giờ còn trống; họ phải thử nhiều lần hoặc gọi vào hôm sau, khiến bản thân và nhân viên tiếp nhận tốn thêm công sức.

**Outcome:** Người bệnh hoàn thành lịch hẹn hợp lệ, hiểu trạng thái xác nhận và ít cần liên hệ hỗ trợ hơn.

**Giá trị tổ chức:** Giảm thao tác xác nhận thủ công và tăng độ tin cậy của lịch hẹn.

**Guardrail:** Không tạo lịch trùng, không làm lộ dữ liệu cá nhân và không gửi xác nhận trước khi ghi nhận thành công.

### 9.4. Thử nghiệm và điều chỉnh backlog

Giả thuyết: “Hiển thị giờ trống nhất quán và xác nhận trực tiếp giúp người bệnh hoàn tất đặt lịch dễ hơn so với chỉ thêm bộ lọc bác sĩ ở giai đoạn đầu.”

Nhóm cho nhóm mục tiêu thử nguyên mẫu, kiểm tra phương án đồng bộ lịch, rồi phát hành giới hạn luồng đặt lịch có tiêu chí chấp nhận rõ ràng. Họ theo dõi tỷ lệ hoàn tất, thời gian đặt, cuộc gọi hỏi giờ và lỗi đặt trùng. Định nghĩa chỉ số, giai đoạn đo và cách ra quyết định được thống nhất từ trước.

Nếu phản hồi vẫn cho thấy người dùng không biết chọn bác sĩ hoặc chuyên khoa nào, nhóm có thể ưu tiên chức năng hướng dẫn hoặc tìm kiếm phù hợp hơn ở lần tiếp theo. **Phản hồi có thể xác nhận, bác bỏ hoặc thay đổi giả thuyết**: đó là giá trị của vòng lặp Agile.

## 10. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Bắt đầu từ tính năng do người có chức vụ cao đề xuất. | Đầu tư vào giải pháp chưa chắc đúng vấn đề. | Hỏi mục tiêu, bối cảnh và bằng chứng; xem nhiều phương án. |
| Coi vài cuộc phỏng vấn đại diện cho tất cả người dùng. | Bỏ sót nhóm có nhu cầu khác. | Ghi phạm vi mẫu, phân đoạn và đối chiếu dữ liệu. |
| Tạo persona hư cấu quá chi tiết. | Quyết định dựa trên câu chuyện không có bằng chứng. | Ghi rõ dữ liệu nghiên cứu và giả định chưa xác minh. |
| Đồng nhất người mua với người sử dụng. | Hệ thống có thể bán được nhưng khó dùng. | Nghiên cứu end user cùng yêu cầu của người quyết định. |
| Đo số tính năng, điểm story point như giá trị. | Output tăng mà outcome không cải thiện. | Theo dõi hành vi thực, kết quả và chất lượng. |
| Chỉ tối ưu chi phí trước mắt cho tổ chức. | Chuyển gánh nặng sang người dùng và tạo rủi ro dài hạn. | Đánh giá giá trị cho các bên, chất lượng và vận hành. |
| Bảo vệ ý tưởng ban đầu bất kể phản hồi. | Tiếp tục đầu tư vào giả định yếu. | Xác định dấu hiệu thành công/thất bại và điều chỉnh backlog. |
| Chờ “nghiên cứu hoàn hảo” mới giao phần mềm. | Phản hồi thực đến quá muộn. | Chọn thử nghiệm nhỏ có kiểm soát, học dần. |
| Bỏ qua an toàn hoặc quyền riêng tư vì “chỉ là MVP”. | Giải pháp có thể gây hại hoặc không sử dụng được. | Đưa ràng buộc thiết yếu vào thử nghiệm và Definition of Done. |

## 11. Mẫu làm việc cho một nhóm Agile

Nhóm có thể dùng một bảng ngắn như sau khi làm rõ sản phẩm; mỗi ô nên phân biệt **điều đã có bằng chứng** và **điều còn là giả định**.

| Ô thông tin | Câu hỏi |
|---|---|
| **Nhóm người dùng ưu tiên** | Ai đang gặp vấn đề? Trong bối cảnh nào? |
| **Công việc cần hoàn thành** | Họ muốn đạt kết quả gì? Hiện làm bằng cách nào? |
| **Vấn đề và tác động** | Trở ngại nào xảy ra và gây hậu quả ra sao? |
| **Bằng chứng hiện có** | Dữ liệu, phản hồi hoặc quan sát nào hỗ trợ? Có giới hạn gì? |
| **Giá trị mong muốn** | Điều gì sẽ tốt hơn cho người dùng, tổ chức và bên liên quan? |
| **Outcome và guardrail** | Đo sự cải thiện thế nào? Điều gì không được xấu đi? |
| **Giả thuyết cần kiểm tra** | Nguyên nhân hoặc giải pháp nào chưa chắc chắn? |
| **Thử nghiệm/Increment nhỏ** | Hành động nào giảm bất định với chi phí phù hợp? |
| **Quyết định tiếp theo** | Dựa trên dữ liệu nào để tiếp tục, thay đổi hoặc dừng? |

Quy trình thực hành:

1. **Làm rõ mục tiêu sản phẩm:** chọn một kết quả quan trọng trước khi liệt kê tính năng.
2. **Chọn nhóm người dùng trọng tâm:** mô tả công việc, hoàn cảnh và người chịu tác động.
3. **Thu thập bằng chứng đủ để quyết định:** kết hợp quan sát, phản hồi và dữ liệu, ghi rõ giới hạn.
4. **Viết problem statement và giả thuyết giá trị:** tách sự thật quan sát được khỏi điều cần kiểm tra.
5. **Định nghĩa outcome, baseline và guardrail:** thống nhất cách đo trước khi thay đổi.
6. **Chọn thử nghiệm hoặc Increment nhỏ:** làm rõ tiêu chí chấp nhận rồi ưu tiên vào backlog.
7. **Nhận phản hồi và cải tiến:** xem xét hành vi thực tế, chất lượng và chi phí, sau đó điều chỉnh hướng tiếp theo.

Quy trình này không bắt buộc một cuộc họp hay biểu mẫu riêng. Trong **Scrum**, kết quả khám phá giúp hình thành Product Goal và làm rõ Product Backlog. Với **Kanban**, nhóm có thể trực quan hóa cả công việc khám phá và phát triển, theo dõi thời gian chờ và giới hạn WIP. Với **XP**, thử nghiệm kỹ thuật, kiểm thử tự động và phần phát hành nhỏ giúp kiểm chứng giải pháp an toàn. Các cách phối hợp hỗ trợ việc bàn giao; **vấn đề và giá trị** vẫn là cơ sở lựa chọn việc cần làm.

## 12. Kết luận

Trong Agile, xác định vấn đề, nhóm người dùng và giá trị cần tạo là một vòng học hỏi liên tục. Nhóm bắt đầu từ **mục tiêu và bối cảnh của người dùng**, kiểm chứng vấn đề bằng dữ liệu và quan sát, nhận diện các bên chịu tác động và định nghĩa **kết quả mong muốn** trước khi đầu tư lớn vào giải pháp.

Giá trị cần được đánh giá bằng thay đổi có ý nghĩa đối với người dùng và tổ chức, đồng thời bảo đảm chất lượng, an toàn và khả năng duy trì. Nhóm chuyển những giả thuyết có ưu tiên cao thành thử nghiệm hoặc phần sản phẩm nhỏ, đưa vào Product Backlog, bàn giao, đo lường và học từ phản hồi. Nhờ vậy, phát triển tăng dần và cải tiến liên tục giúp tạo ra **phần mềm giải quyết đúng vấn đề cho đúng nhóm người dùng**.
