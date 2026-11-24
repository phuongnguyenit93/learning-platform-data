# Nhận diện lãng phí: chờ đợi, bàn giao, làm lại và việc chưa hoàn tất

Một nhóm phát triển phần mềm thông báo: “Chúng tôi đã làm việc rất bận rộn trong hai tuần, nhưng chỉ có một user story sẵn sàng cho người dùng.” Khi xem lại luồng công việc, nhóm thấy người lập trình đã hoàn tất phần code từ nhiều ngày trước, pull request nằm chờ review, người kiểm thử chờ môi trường, một lỗi do hiểu sai yêu cầu buộc làm lại và hàng chục story khác cùng được mở nhưng chưa xong.

Những trở ngại này không nhất thiết xuất phát từ việc từng người làm việc chậm. Chúng có thể là **lãng phí ở cấp hệ thống**: thời gian, công sức và nguồn lực được tiêu hao nhưng không đưa giá trị tới người dùng tương xứng.

Trong **Lean**, mục tiêu không phải bắt mọi người luôn bận rộn hay cắt mọi bước kiểm soát. Mục tiêu là **tạo giá trị cho khách hàng với dòng công việc thông suốt, chất lượng được xây ngay từ đầu và khả năng học hỏi liên tục**. Bốn dạng lãng phí đặc biệt đáng chú ý trong phát triển phần mềm là **chờ đợi, bàn giao gây thất thoát, làm lại và công việc chưa hoàn tất**.

Bài thuộc chương **Lean** của module **AGILE_DEVELOPMENT**. Khi kết hợp tư duy Lean với Agile, Scrum, Kanban, XP, user story và các số đo dòng công việc, nhóm có thể giao phần mềm theo những phần tăng trưởng nhỏ, phát hiện rủi ro sớm và cải tiến liên tục thay vì tối đa hóa số task đang thực hiện.

Sau bài học, bạn có thể:

1. Nhận diện chính xác bốn dạng lãng phí trong một dòng giá trị phát triển phần mềm.
2. Phân biệt **hoạt động tạo giá trị**, **hoạt động bắt buộc nhưng chưa tạo giá trị trực tiếp** và **lãng phí có thể loại bỏ/giảm bớt**.
3. Vẽ bản đồ luồng giá trị (*Value Stream Mapping – VSM*) từ nhu cầu đến phần mềm có thể sử dụng.
4. Đo thời gian chờ, thời gian thực hiện, cycle time, lead time, WIP, work item age và công việc phải làm lại.
5. Đề xuất biện pháp như chia lát dọc, giới hạn WIP, giảm kích thước lô, review sớm, tự động hóa và cải thiện chính sách luồng.
6. Giải thích tại sao không nên loại bỏ kiểm thử, bảo mật, trao đổi nghiệp vụ hoặc nghỉ ngơi chỉ để “tăng tốc”.
7. Thử một cải tiến có giới hạn, thu dữ liệu trước/sau và đánh giá kết quả bằng giá trị, chất lượng và khả năng giao hàng.

## 1. Lean nhìn dòng giá trị thay vì mức độ bận rộn của từng người

Trong bối cảnh phần mềm, **giá trị (value)** là kết quả có ích cho người sử dụng hoặc bên hưởng lợi: hoàn thành tác vụ, giảm lỗi, tiết kiệm thời gian, có thông tin đúng lúc, bảo vệ dữ liệu hoặc đáp ứng một nghĩa vụ cần thiết.

Ví dụ, với nền tảng học trực tuyến, **“người học có thể mở lại video đúng vị trí đã dừng”** là một khả năng có giá trị. Việc viết API hoặc tạo bảng cơ sở dữ liệu là **phương tiện** để đạt hành vi đó; tự chúng chưa bảo đảm người học nhận được giá trị.

**Dòng giá trị (value stream)** là chuỗi hoạt động cần thiết để chuyển nhu cầu hoặc ý tưởng thành kết quả có thể sử dụng. Nó có thể bao gồm:

- Hiểu vấn đề và xác định hành vi cần đạt.
- Làm rõ yêu cầu, thiết kế và phân chia công việc.
- Lập trình, tích hợp, review và kiểm thử.
- Triển khai, quyết định mở cho người dùng, hỗ trợ vận hành.
- Quan sát kết quả và điều chỉnh sản phẩm.

Lean yêu cầu **quan sát toàn bộ chuỗi**, không chỉ tối ưu tốc độ ở một bước. Một nhóm viết code nhanh hơn 30% nhưng để pull request chờ thêm ba ngày có thể không cải thiện thời gian người dùng nhận giá trị.

### Ba nhóm hoạt động cần phân biệt

| Nhóm hoạt động | Đặc điểm | Ví dụ |
| --- | --- | --- |
| **Trực tiếp tạo giá trị** | Giúp tạo một khả năng hoặc kết quả hữu ích cho người dùng. | Hoàn thiện luồng người học lưu và khôi phục vị trí video. |
| **Cần thiết nhưng không trực tiếp tạo giá trị** | Đáp ứng điều kiện chất lượng, pháp lý, an toàn, phối hợp hoặc duy trì hệ thống hiện tại. | Kiểm thử phân quyền; duyệt thay đổi theo kiểm soát bảo mật bắt buộc. |
| **Lãng phí có thể giảm** | Tiêu hao thời gian/công sức mà không cải thiện đáng kể kết quả và không phải điều kiện cần. | Chờ duyệt trùng lặp, sửa lỗi do yêu cầu không rõ, nhiều task được bắt đầu rồi nằm im. |

Một hoạt động có thể thuộc nhóm khác tùy bối cảnh. **Review code** có thể rất có giá trị khi phát hiện sai thiết kế và chia sẻ kiến thức, nhưng việc PR đã sẵn sàng mà nằm chờ nhiều ngày vì thiếu chính sách phân công lại là lãng phí.

### Đừng đồng nhất Lean với “cắt người”

Giảm lãng phí là **cải thiện cách công việc di chuyển trong hệ thống**, không phải yêu cầu nhân sự làm liên tục không nghỉ, bỏ thời gian học tập, bỏ chuẩn chất lượng hoặc giảm quyền được nêu rủi ro. Tối đa hóa sử dụng từng cá nhân đến 100% thường làm hàng chờ dài hơn và khả năng ứng phó sự cố kém đi.

## 2. Bốn dạng lãng phí trọng tâm

| Dạng lãng phí | Câu hỏi nhận diện | Ví dụ phần mềm | Dấu hiệu cần kiểm tra |
| --- | --- | --- | --- |
| **Chờ đợi (waiting/delays)** | Công việc có đủ thông tin để tiến nhưng đang đứng yên vì điều gì? | PR chờ reviewer, test chờ môi trường, release chờ xác nhận trùng lặp. | Thời gian ở trạng thái chờ dài, work item age tăng, nhiều mục bị blocked. |
| **Bàn giao gây thất thoát (handoff waste)** | Qua mỗi ranh giới chuyên môn có mất ngữ cảnh hoặc phải giải thích lại không? | BA viết tài liệu rồi “ném” sang Dev; Dev hoàn tất code rồi giao QA không cùng hiểu tiêu chí. | Hỏi lại nhiều lần, đợi xác nhận, yêu cầu bị hiểu sai, số vòng chuyển qua lại cao. |
| **Làm lại (rework)** | Vì sao kết quả đã thực hiện phải sửa hoặc làm lại? | Sửa logic sau khi phát hiện tiêu chí chưa thống nhất; viết lại giao tiếp API do tích hợp muộn. | Nhiều vòng sửa, lỗi bị phát hiện muộn, công việc mở lại. |
| **Việc chưa hoàn tất (partially done work/WIP)** | Bao nhiêu việc đã bắt đầu nhưng chưa tạo được kết quả sử dụng? | 12 story cùng phát triển, không story nào đạt DoD. | WIP lớn, nhiều nhánh lâu ngày, work item age cao, bối cảnh chuyển đổi liên tục. |

Bốn dạng này **liên hệ với nhau**. Nhiều việc mở cùng lúc tạo thêm bàn giao và hàng chờ; chờ lâu khiến ngữ cảnh bị quên; ngữ cảnh mất gây làm lại; làm lại tăng WIP và kéo dài thời gian chờ.

Trong những tài liệu Lean software, còn có các lãng phí như **tính năng dư thừa, học lại, chuyển đổi nhiệm vụ, lỗi**. Bài này tập trung vào bốn nhóm nêu trong tiêu đề; chúng có thể chồng lấp với các cách phân loại lãng phí khác. Mục đích phân loại là **chọn biện pháp hữu ích**, không tranh luận một hiện tượng phải mang duy nhất một nhãn.

## 3. Lãng phí chờ đợi: khi công việc đứng yên dù con người vẫn bận

**Chờ đợi** là khoảng thời gian một mục công việc không tiến tới điều kiện hoàn tất vì cần thông tin, nguồn lực, quyết định, môi trường, kiểm tra hoặc một phụ thuộc khác.

### Những điểm chờ thường gặp

- **Đợi làm rõ yêu cầu:** “Chưa biết người học bỏ dở video có được tự động lưu tiến độ không.”
- **Đợi người review:** PR đã sẵn sàng nhưng người có quyền review đang xử lý nhiều việc khác.
- **Đợi môi trường kiểm thử:** môi trường tích hợp hỏng, tài khoản thử chưa cấp, dữ liệu mẫu chưa có.
- **Đợi bên ngoài:** nhà cung cấp không trả lời về API; bộ phận vận hành chưa xác nhận cấu hình.
- **Đợi quyết định ưu tiên:** hai bên đưa yêu cầu mâu thuẫn, không ai rõ ai có quyền kết luận.
- **Đợi phát hành:** Increment đã đạt DoD nhưng nằm chờ một quy trình phê duyệt không rõ giá trị.

### Tại sao dễ bỏ sót thời gian chờ?

Bảng công việc thường chỉ ghi “In progress” từ lúc nhận đến khi Done, nên khó thấy **một giờ làm và ba ngày nằm chờ**. Nếu người lập trình mở story khác trong khi chờ review, bảng càng tạo cảm giác mọi người đang năng động, dù mục trước chưa hoàn tất.

### Ví dụ

Một thay đổi lưu tiến độ video mất **5 giờ lập trình** nhưng chờ **2 ngày làm việc** để được review. Khi review xong, phát hiện một trường hợp phân quyền chưa rõ và phải chờ PO xác nhận thêm một ngày.

Ở đây, việc giảm 5 giờ code xuống 4 giờ **không giải quyết nút thắt chính**. Nên kiểm tra chính sách review, mức WIP, khả năng reviewer và cách làm rõ acceptance criteria từ sớm.

### Biện pháp giảm chờ đợi

1. **Hiển thị trạng thái blocked và lý do:** ai hoặc điều kiện nào đang chặn, thời điểm nào cần xem lại.
2. **Giới hạn WIP:** bớt mở việc mới khi đã có nhiều mục chờ review/verify.
3. **Kéo người tới chỗ tắc:** ưu tiên giúp hoàn tất các mục đang dở hơn là tăng số task mới bắt đầu.
4. **Giảm kích thước thay đổi:** PR nhỏ hơn thường dễ review và tích hợp hơn.
5. **Làm rõ chính sách phản hồi:** người review hoặc đầu mối phụ thuộc biết thời gian phản hồi mong đợi, có người thay thế khi vắng.
6. **Tự động hóa phần lặp lại hợp lý:** kiểm thử, dựng môi trường, kiểm tra định dạng hoặc triển khai an toàn.
7. **Xử lý phụ thuộc sớm:** thử tích hợp quan trọng trước thay vì đợi cuối Sprint.

Không phải mọi chờ đợi đều có thể hoặc nên xóa. Ví dụ, **đợi xác minh quy định bắt buộc** là một ràng buộc thực; Lean khuyến khích chuẩn bị sớm, giảm vòng đi lại và làm rõ điều kiện hoàn tất, **không bỏ bước tuân thủ**.

## 4. Lãng phí bàn giao: mất ngữ cảnh giữa các bước và nhóm

**Bàn giao (handoff)** là lúc một bên chuyển thông tin, quyết định hoặc công việc sang bên khác. Bàn giao không tự động là lãng phí; một số chuyển giao quyền trách nhiệm là cần thiết. **Lãng phí bàn giao** phát sinh khi việc chuyển giao làm tăng chờ đợi, hiểu sai, phải diễn giải lại hoặc mất tính liên tục.

### Một chuỗi bàn giao dễ phát sinh vấn đề

Giả sử quy trình được tổ chức:

> Phân tích nghiệp vụ → Thiết kế → Frontend → Backend → QA → Vận hành.

Mỗi bộ phận hoàn thành gói việc và “giao xong” cho bộ phận kế tiếp. Người QA có thể chỉ được thấy yêu cầu khi code đã hoàn tất; vận hành chỉ biết schema thay đổi ngay trước phát hành; frontend và backend thống nhất hợp đồng API muộn.

Điểm lãng phí không nằm ở **sự tồn tại của chuyên môn**, mà ở **quãng mất thông tin, chờ và sửa lại giữa các ranh giới**.

### Dấu hiệu quan sát được

- Cùng một yêu cầu phải được giải thích lại ở nhiều buổi họp.
- Người nhận việc không biết **vì sao** chọn phương án hoặc điều kiện nào quan trọng.
- Nhiều câu hỏi được gửi qua người trung gian dù người cần trao đổi có thể nói trực tiếp.
- Story “chuyển sang QA” nhưng thiếu dữ liệu thử, acceptance criteria hoặc môi trường.
- Một thay đổi bị gửi qua lại giữa hai nhóm nhiều lần vì mỗi nhóm hiểu “Done” khác nhau.
- Bàn giao xảy ra vào cuối kỳ; mọi lỗi tích hợp dồn vào thời điểm áp lực cao.

### Giảm lãng phí mà không xóa kiểm soát cần thiết

- **Trao đổi trực tiếp giữa người có liên quan:** PO, Developers, QA, UX, bảo mật hoặc vận hành tham gia từ lúc làm rõ hành vi có rủi ro.
- **Dùng ví dụ cụ thể:** user story, acceptance criteria, sơ đồ dữ liệu, hợp đồng API và tình huống lỗi.
- **Chia lát dọc:** một nhóm hoặc nhóm chuyên môn phối hợp hoàn tất hành vi từ đầu tới cuối, không tạo hàng chờ “toàn bộ backend xong mới đến frontend”.
- **Phân định tiêu chuẩn hoàn tất:** Definition of Done (DoD), quy tắc review và điều kiện triển khai rõ.
- **Gắn thông tin với công việc:** người nhận thấy quyết định, rủi ro, kết quả thử và đầu mối cần hỏi.
- **Tạo đường phản hồi ngắn:** nhận ra hiểu sai sớm, trao đổi ngắn trước khi phát triển thêm.

**Ví dụ không nên làm:** thay toàn bộ kiểm soát bảo mật bằng “nhóm tự chịu trách nhiệm” khi hệ thống có dữ liệu nhạy cảm và tổ chức quy định phê duyệt chuyên môn bắt buộc. Cách tốt hơn là **đưa chuyên gia vào sớm và thiết kế cơ chế kiểm soát ít tạo chờ đợi hơn**.

## 5. Lãng phí làm lại: chi phí của việc phát hiện sai quá muộn

**Làm lại (rework)** là công sức phải dùng để sửa hoặc thực hiện lại phần việc đã thực hiện vì kết quả không đáp ứng điều kiện cần thiết hoặc vì thông tin thiết yếu được phát hiện muộn.

Ví dụ:

- Phải viết lại xử lý xác nhận đăng ký vì nghiệp vụ yêu cầu không tạo đăng ký trùng mà nhóm chưa hỏi.
- Đã xây giao diện cho mọi vai trò rồi phải sửa do chưa phân quyền theo lớp.
- Đã viết xong hai service nhưng giao tiếp dữ liệu không tương thích.
- Tính năng được làm lại do kết quả thử với người dùng cho thấy giả thuyết ban đầu sai.

**Điểm cần phân biệt:** không phải mọi thay đổi hay việc viết code mới đều là lãng phí. **Thích ứng theo phản hồi thật có thể là hoạt động tạo giá trị**. Lãng phí cần giảm là phần làm lại có thể phòng ngừa nhờ phản hồi sớm, kiểm thử, trao đổi và thiết kế đủ rõ.

### 5.1. Những nguyên nhân phổ biến

| Nguyên nhân | Biểu hiện | Hướng cải tiến |
| --- | --- | --- |
| **Nhu cầu chưa được làm rõ** | Viết xong mới biết người dùng cần hành vi khác. | Trao đổi vấn đề trước, user story ngắn, ví dụ nghiệp vụ, thử nghiệm sớm. |
| **Acceptance criteria mơ hồ** | QA báo lỗi vì cách hiểu khác Developers. | Thống nhất ví dụ đầu vào/kết quả, bao gồm trường hợp lỗi quan trọng. |
| **Tích hợp muộn** | Giao diện và API đã “xong” riêng nhưng không chạy cùng nhau. | CI, hợp đồng giao tiếp, tích hợp theo lát dọc. |
| **Chất lượng bị dồn về cuối** | Phát hiện lỗi phân quyền/hồi quy vào ngày phát hành. | Kiểm thử sớm, tự động hóa, DoD và review liên tục. |
| **Quá nhiều WIP** | Thành viên chuyển ngữ cảnh, quên giả định và tạo lỗi. | Giới hạn WIP, hoàn tất việc đang dở trước. |
| **Thiết kế quá mức** | Xây khả năng đa kênh chưa ai dùng rồi phải bỏ. | Giải pháp đơn giản cho nhu cầu hiện tại, xác minh giả thuyết giá trị. |
| **Thông tin từ bên ngoài chậm** | Hợp đồng API của đối tác thay đổi sau khi đã triển khai sâu. | Thử tích hợp sớm, theo dõi phiên bản, có phương án tương thích. |

### 5.2. Ngăn lỗi càng sớm càng tốt

Trong Lean, tư duy **xây chất lượng ngay từ đầu** giúp giảm sửa lỗi muộn. Ở phần mềm, có thể dùng:

- Kiểm thử tự động theo các hành vi quan trọng.
- Test-driven development (TDD) khi phù hợp.
- Continuous Integration và kiểm tra tương thích.
- Review thiết kế, lập trình cặp hoặc trao đổi nhanh ở chỗ bất định.
- Kiểm tra quyền truy cập, tính toàn vẹn dữ liệu và trường hợp lỗi trước khi gọi Done.
- Demo với người dùng ở các lát nhỏ để xác nhận giải pháp đúng nhu cầu.

Điều này không có nghĩa đầu tư vô hạn vào mọi loại kiểm thử. Hãy chọn mức kiểm soát **tương xứng với rủi ro và tiêu chuẩn chất lượng áp dụng**.

### 5.3. “Sửa theo phản hồi” có phải lãng phí?

Không nên tự động coi việc chỉnh sửa sau phản hồi là thất bại. Có hai tình huống rất khác:

- **Phòng ngừa được:** nhóm không hỏi quy tắc cơ bản về quyền truy cập dù có người chịu trách nhiệm và thông tin sẵn có; phải viết lại nhiều phần.
- **Khám phá có giá trị:** sản phẩm thử giúp xác nhận người học muốn lối vào “Học tiếp” nổi bật hơn dự kiến; nhóm điều chỉnh sản phẩm để đáp ứng nhu cầu mới được kiểm chứng.

Lean khuyến khích **rút ngắn vòng học**, để khoản đầu tư cho giả thuyết sai càng nhỏ càng tốt, không đòi nhóm dự đoán đúng tất cả trước khi bắt đầu.

## 6. Việc chưa hoàn tất: tồn kho vô hình của phát triển phần mềm

Trong sản xuất, tồn kho vật lý dễ nhìn thấy. Ở phần mềm, **việc đã bắt đầu nhưng chưa hoàn thành** dễ bị che bởi các nhánh code, ticket “In Progress”, PR nằm chờ, thiết kế chưa kiểm chứng và các thay đổi chưa tích hợp.

Đây là một dạng **partially done work**, thường liên quan trực tiếp tới **WIP (work in progress)**.

### Vì sao WIP cao có thể gây lãng phí?

1. **Vốn và công sức bị khóa:** đầu tư đã bỏ vào nhiều phần chưa thể tạo giá trị.
2. **Nhiều hàng chờ:** mỗi công đoạn nhận việc đến nhanh hơn khả năng xử lý, làm tăng tuổi công việc.
3. **Tăng chuyển đổi ngữ cảnh:** nhân sự đổi qua lại giữa các story, quên giả định và mất thời gian bắt nhịp.
4. **Tăng rủi ro tích hợp:** nhiều nhánh/phần thay đổi cùng tồn tại, xung đột và phụ thuộc tăng.
5. **Feedback đến muộn:** người dùng chưa thể dùng nên nhóm không biết hướng xây có đúng không.
6. **Dự báo kém ổn định:** phần lớn công việc ở trạng thái “gần xong”, khó xác định bao giờ có Increment thật.

### Ví dụ “mọi người đều bận nhưng không có Done”

Một nhóm có sáu Developers. Mỗi người nhận ba story cùng lúc, tổng cộng **18 story đang dở**. Các story đều phụ thuộc review, kiểm thử hoặc API đang chờ. Cuối tuần, mỗi người đều báo tiến độ cao, nhưng chỉ **hai story đạt DoD**.

Giải pháp không nhất thiết là yêu cầu mỗi người code nhanh hơn. Có thể cần:

- Giảm số story bắt đầu cùng lúc.
- Ưu tiên hoàn tất các story gần Done với trợ giúp liên chuyên môn.
- Phân chia story lớn thành **lát dọc đủ nhỏ**.
- Làm rõ chính sách khi một cột bị đầy WIP.
- Đưa vấn đề phụ thuộc vào tầm nhìn chung của nhóm.

### Không đồng nghĩa mọi WIP đều xấu

Bất kỳ công việc nào cũng cần một giai đoạn đang thực hiện. **Giới hạn WIP** nhằm cân bằng khả năng tiến hành công việc với khả năng hoàn tất, không phải buộc mọi người chỉ làm một việc tuyệt đối. Công việc khẩn cấp có thể cần chính sách riêng; người đang chờ điều kiện ngoài quyền hạn có thể hỗ trợ mục khác trong khi vẫn minh bạch trạng thái blocked.

## 7. Bốn dạng lãng phí khuếch đại nhau như thế nào?

Hãy xét chuỗi sau:

~~~mermaid
flowchart LR
    A["Mở quá nhiều story cùng lúc"] --> B["WIP cao"]
    B --> C["PR / kiểm thử tạo hàng chờ"]
    C --> D["Thời gian chờ tăng"]
    D --> E["Người làm chuyển sang việc khác"]
    E --> F["Mất ngữ cảnh, bàn giao rời rạc"]
    F --> G["Hiểu sai / lỗi tích hợp"]
    G --> H["Làm lại, kiểm thử lại"]
    H --> B
    D --> I["Người dùng nhận phản hồi muộn"]
    I --> J["Thay đổi lớn mới được phát hiện"]
    J --> H
~~~

Đây là một **vòng lặp có thể xuất hiện** trong tổ chức, không phải quy luật rằng cứ có nhiều WIP thì chắc chắn có lỗi. Nhưng nó gợi ý một điểm quan trọng: **đừng giải quyết từng triệu chứng riêng lẻ nếu nguyên nhân chung là cách công việc di chuyển qua hệ thống**.

Ví dụ, thêm người review nhưng vẫn mở gấp đôi số story có thể chỉ chuyển nút thắt sang cột Verify. Tăng tốc lập trình trong khi môi trường test lỗi liên tục có thể tăng số thay đổi chờ tích hợp mà không tăng giá trị.

### Một câu hỏi Lean hữu ích

> “Nếu chúng ta chỉ cải thiện một bước, thời gian từ nhu cầu đến kết quả có thực sự giảm, hay hàng chờ sẽ dịch chuyển sang bước kế tiếp?”

Câu hỏi này dẫn tới việc quan sát **toàn bộ luồng giá trị**, không tối ưu một chỉ số cục bộ.

## 8. Vẽ Value Stream Map: tìm thời gian ở đâu và vì sao

**Value Stream Mapping (VSM)** là cách mô tả hành trình một yêu cầu đi qua các hoạt động, điểm chờ và phản hồi, từ đó tìm cơ hội cải tiến. Trong phần mềm, nhóm có thể bắt đầu bằng một sơ đồ đơn giản trên bảng thay vì công cụ lớn.

### 8.1. Xác định điểm bắt đầu và kết thúc

Đầu tiên, thống nhất đang đo gì:

- Từ lúc **ý tưởng được ghi nhận** tới khi được chọn thực hiện?
- Từ lúc **Developers bắt đầu một PBI** tới khi Increment đạt DoD?
- Từ lúc **Increment Done** tới khi người dùng được mở tính năng?
- Từ lúc người dùng nhận khả năng tới khi nhóm có **phản hồi về giá trị**?

Mỗi cách định nghĩa trả lời một câu hỏi khác nhau. Không nên trộn các khoảng đo rồi so sánh như thể chúng giống nhau.

Để tìm lãng phí phát triển, ví dụ sau dùng ranh giới **từ bắt đầu làm story đến đạt DoD**, tính theo giờ làm việc trong cùng quy ước.

### 8.2. Bản đồ trạng thái hiện tại minh họa

~~~mermaid
flowchart LR
    A["Làm rõ yêu cầu\n1 giờ"] --> Q1["CHỜ quyết định\n8 giờ"]
    Q1 --> B["Lập trình\n7 giờ"]
    B --> Q2["CHỜ review\n16 giờ"]
    Q2 --> C["Review\n1,5 giờ"]
    C --> Q3["CHỜ test\n8 giờ"]
    Q3 --> D["Kiểm thử\n2,5 giờ"]
    D --> E["Làm lại sau lỗi\n3 giờ"]
    E --> Q4["CHỜ kiểm thử lại\n8 giờ"]
    Q4 --> F["Kiểm thử lại\n1 giờ"]
    F --> G["Đạt DoD"]
~~~

Tất cả số liệu ở sơ đồ là **giả định học tập** cho một story có phát sinh lỗi. Tổng thời gian hoạt động trực tiếp:

\[
T_{\text{active}}=1+7+1{,}5+2{,}5+3+1=16\ \text{giờ}
\]

Tổng thời gian chờ:

\[
T_{\text{wait}}=8+16+8+8=40\ \text{giờ}
\]

Tổng thời gian từ bắt đầu tới Done, theo cùng cách tính giờ làm việc:

\[
T_{\text{elapsed}}=16+40=56\ \text{giờ làm việc}
\]

**Hiệu suất luồng theo thời gian chủ động (flow efficiency)** trong cách đo đơn giản này:

\[
\frac{16}{56}\times100\%\approx28{,}6\%
\]

Số **28,6%** chỉ có nghĩa **khoảng 28,6% thời gian tính trong mẫu minh họa được phân loại là hoạt động chủ động**. Nó **không phải** tỷ lệ năng suất nhân sự, cũng không chứng minh 71,4% thời gian còn lại có thể xóa bỏ hoàn toàn. Bước làm lại 3 giờ được tính là **active** dù có thể là công sức lãng phí phòng ngừa được.

### 8.3. Vì sao phải quan sát thực tế?

Nếu chỉ nhìn ngày bắt đầu và ngày Done, nhóm thấy 56 giờ nhưng không biết 40 giờ nằm ở hàng chờ. Nếu chỉ hỏi Developers “đã code bao nhiêu giờ”, nhóm thấy 7 giờ và có thể kết luận lập trình đã nhanh, bỏ qua khả năng giao hàng chậm.

**Bản đồ giá trị tốt phải làm rõ cả hoạt động và thời gian chờ**, cùng những ranh giới người/bộ phận và điều kiện làm việc cần thiết.

### 8.4. Bản đồ tương lai không phải lời hứa bằng cách xóa ô chờ

Giả sử nhóm đề xuất:

- Làm rõ ví dụ nghiệp vụ sớm để giảm chờ quyết định.
- Giới hạn WIP ở Review và dùng review theo cặp cho thay đổi rủi ro.
- Chuẩn bị môi trường kiểm thử tự động.
- Chạy kiểm thử tự động cùng CI để phát hiện lỗi trước khi chuyển tới QA.

Hãy vẽ **future-state map** và nêu **giả thuyết** thời gian nào có thể giảm. Sau khi thử, đo lại để xác nhận chứ không tự xem số mới trên sơ đồ là kết quả đạt được.

## 9. Các số đo cần thiết để nhận diện lãng phí

Một nhóm không cần đo mọi thứ. Nên chọn ít chỉ số giúp giải quyết điểm nghẽn cụ thể.

| Chỉ số | Định nghĩa thực hành | Giúp phát hiện | Cần cẩn trọng |
| --- | --- | --- | --- |
| **Lead time** | Thời gian từ mốc yêu cầu được ghi nhận/được chấp nhận tới mốc hoàn tất, theo chính sách nhóm. | Khả năng đáp ứng nhu cầu từ góc nhìn yêu cầu. | Phải nói rõ điểm bắt đầu/kết thúc. |
| **Cycle time** | Thời gian từ lúc bắt đầu thực hiện tới khi hoàn tất. | Công việc bị chờ và mất bao lâu để Done. | Không đồng nhất với giờ code. |
| **Throughput** | Số mục hoàn tất trong một khoảng thời gian. | Năng lực hoàn tất của hệ thống theo loại việc. | Đếm nhiều ticket nhỏ hơn không tự tăng giá trị. |
| **WIP** | Số mục đã bắt đầu nhưng chưa Done. | Tồn kho việc dở và khả năng tạo hàng chờ. | Phải có ranh giới bắt đầu và Done nhất quán. |
| **Work item age** | Thời gian một mục đang mở đã tồn tại từ lúc bắt đầu. | Việc đang có nguy cơ kẹt lâu. | Mục lớn/khó cần ngữ cảnh, không dùng để phạt cá nhân. |
| **Blocked time** | Thời gian mục không thể tiến vì một điều kiện cụ thể. | Chờ quyết định, review, môi trường, phụ thuộc. | Cần chính sách đánh dấu blocked rõ và trung thực. |
| **Rework effort/rate** | Công sức hoặc tỷ lệ mục phải sửa do lỗi/hiểu sai đã xác định. | Chất lượng phản hồi đầu vào và tích hợp. | Không coi mọi thay đổi sau feedback là “lỗi”. |
| **Flow efficiency** | Tỷ lệ thời gian hoạt động chủ động trên tổng thời gian trong một ranh giới luồng. | Quy mô chờ so với thời gian xử lý. | Phân loại hoạt động/chờ nhất quán; không suy ra năng suất cá nhân. |

### 9.1. Cần nhìn phân bố, không chỉ trung bình

Nếu 9 story hoàn tất trong hai ngày nhưng một story kéo dài 30 ngày, thời gian trung bình có thể không phản ánh trải nghiệm thông thường và rủi ro tồn đọng. Nhóm nên xem **trung vị, phân vị, các mục già bất thường** và loại công việc khác nhau khi cần.

Một **service level expectation (SLE)** trong Kanban có thể nêu kỳ vọng dựa trên dữ liệu: “Theo lịch sử của loại công việc tương tự, 85% mục hoàn thành trong tối đa 8 ngày làm việc.” SLE là tín hiệu để theo dõi và hỗ trợ mục đang lâu, **không phải deadline cá nhân**.

### 9.2. Little's Law giúp hiểu WIP ở cấp hệ thống

Trong một hệ thống tương đối ổn định với các điều kiện áp dụng phù hợp:

\[
\overline{WIP}\approx \text{Throughput trung bình}\times\text{Cycle time trung bình}
\]

Ví dụ, nếu trung bình có **12 mục đang dở** và hệ thống hoàn tất **3 mục mỗi tuần**, thì thời gian trung bình ước tính trong ranh giới luồng tương ứng là:

\[
\text{Cycle time trung bình}\approx\frac{12}{3}=4\ \text{tuần}
\]

Con số này chỉ minh họa mối quan hệ ở **cấp hệ thống**, với giả định điểm đếm, độ ổn định và đơn vị phù hợp. Nó **không** cho phép kết luận mỗi story mất đúng bốn tuần hay mỗi Developer phải hoàn tất trong thời gian đó. Nếu hệ thống không ổn định hoặc WIP tăng liên tục, áp dụng phép chia trực tiếp có thể gây hiểu nhầm.

### 9.3. Thời gian chờ và chất lượng cần được đọc cùng nhau

Giảm cycle time từ 10 ngày xuống 6 ngày là tín hiệu tốt **nếu Definition of Done và chất lượng không bị hạ**. Nếu nhóm rút ngắn bằng cách bỏ kiểm thử, số lỗi production tăng có thể làm tổng dòng giá trị chậm hơn sau đó.

Hãy kết hợp **flow metrics** với lỗi sau phát hành, trường hợp hồi quy, phản hồi người dùng và kết quả sản phẩm.

## 10. Cách đọc bảng Kanban để phát hiện hàng chờ

Một bảng luồng minh họa:

~~~text
Ready | Develop (WIP <= 3) | Review (WIP <= 2) | Verify (WIP <= 2) | Done
      |                    |                    |                    |
      |  A - đang làm      | D - 4 ngày         | F - chờ môi trường| H
      |  B - đang làm      | E - 3 ngày         | G - đang test     | I
      |  C - đang làm      |                    |                    |
~~~

Các giới hạn WIP và ngày tuổi trong bảng chỉ là **ví dụ**, không phải ngưỡng khuyến nghị chung cho mọi nhóm.

### Những câu hỏi nhóm nên hỏi

- Review có liên tục đầy WIP trong khi Develop vẫn muốn mở story mới không?
- Các mục D/E chờ vì thiếu người review, PR quá lớn hay tiêu chí chưa rõ?
- Mục F chờ môi trường có đầu mối và thời điểm xử lý không?
- Developers có thể hỗ trợ review/kiểm thử hoặc chia nhỏ thay đổi để hoàn tất trước không?
- Có loại việc nào (sự cố khẩn, bảo mật, phát hành) cần chính sách ưu tiên riêng?

### Chính sách luồng hữu ích

1. **Định nghĩa rõ “Ready”, “Develop”, “Review”, “Verify”, “Done”.**
2. **Giới hạn WIP nơi phù hợp**, thay đổi theo dữ liệu và năng lực thực tế.
3. **Chính sách blocked:** ghi lý do, thời điểm phát hiện, người/cơ chế hỗ trợ; không giấu mục bị chặn.
4. **Kéo việc dựa trên năng lực còn trống:** ưu tiên hoàn tất việc gần Done trước khi mở thêm.
5. **Xem work item age:** kiểm tra mục đang quá lâu, không đợi đến khi quá hạn.
6. **Cải tiến chính sách thường xuyên:** một quy tắc WIP không phải con số bất biến.

Câu nói thực hành có ích: **“Stop starting, start finishing” – giảm bắt đầu việc mới, tập trung hoàn tất việc đang dở**. Nó là lời nhắc về ưu tiên, không phải mệnh lệnh bất chấp sự cố hoặc trách nhiệm vận hành.

## 11. Giảm lãng phí bằng cách chia lát dọc và giảm kích thước lô

Một nguyên nhân của nhiều bàn giao và WIP là nhóm chia công việc theo **lớp kỹ thuật**:

- Hoàn thành toàn bộ database.
- Hoàn thành toàn bộ backend.
- Hoàn thành toàn bộ frontend.
- Cuối cùng mới kiểm thử tích hợp.

Các lớp có thể “xong” riêng nhưng người dùng chưa làm được tác vụ. Khi ghép lại, yêu cầu thay đổi hoặc lỗi tích hợp gây làm lại lớn.

**Chia lát dọc (vertical slicing)** chọn một hành vi nhỏ từ đầu tới cuối: giao diện/thao tác → quy tắc nghiệp vụ → dữ liệu → phản hồi đúng và kiểm thử, ở mức cần thiết cho hành vi đó.

### Ví dụ: “Học tiếp” trên nền tảng học trực tuyến

**Story quá lớn:** “Ghi nhớ tiến độ mọi loại bài trên mọi thiết bị, hoạt động khi mất mạng, gợi ý bài kế tiếp và báo cáo cho giảng viên.”

Có thể chia thành các lát:

| Lát | Kết quả đầu cuối người dùng có được | Điều có thể kiểm chứng |
| --- | --- | --- |
| **V1 – Một video đã cấp quyền, có mạng** | Người học mở lại video ở vị trí đã lưu. | Lưu/đọc đúng tài khoản và video, lỗi được phản hồi, phân quyền đúng. |
| **V2 – Đường vào bài đang học** | Người học tìm nhanh bài đang dở từ trang chủ. | Điều hướng đúng, dữ liệu thật, trạng thái không có bài đang dở rõ. |
| **V3 – Nhiều thiết bị** | Người học đổi thiết bị vẫn tiếp tục vị trí phù hợp. | Đồng bộ và tình huống xung đột được xử lý theo quy tắc. |
| **V4 – Mất mạng nếu nhu cầu được xác minh** | Người học có khả năng tiếp tục theo chế độ offline được hỗ trợ. | Lưu cục bộ, đồng bộ an toàn và phản hồi lỗi khi kết nối lại. |

Mỗi lát **phải thật sự chạy đầu cuối trong phạm vi được công bố**, không chỉ tạo API giả hay màn hình mẫu. Các task database, API, UI và kiểm thử nằm trong lát; Done nghĩa là tích hợp và đáp ứng DoD.

### Tại sao lát nhỏ có thể giảm lãng phí?

- Bàn giao ít lần hơn trước khi có một kết quả hoàn chỉnh.
- PR/thay đổi nhỏ hơn, dễ review và kiểm thử hơn.
- Phụ thuộc được phát hiện sớm ở phạm vi hẹp.
- Người dùng có thể thử V1 trước khi nhóm xây V3/V4.
- Khi nhận phản hồi, phần cần sửa nhỏ hơn so với tính năng lớn đã hoàn tất toàn bộ.

**Lưu ý:** giảm phạm vi không cho phép bỏ các điều kiện chất lượng bắt buộc. Nếu tính năng lưu tiến độ cho tài khoản, **không được trì hoãn phân quyền sang lát sau** chỉ để V1 “Done nhanh”.

## 12. Liên hệ Lean với Scrum, Kanban và XP

Lean, Scrum, Kanban và XP có thể bổ trợ nhau. Không nên coi chúng là những tên gọi thay thế hoàn toàn hoặc một bộ công cụ bắt buộc đồng loạt.

### 12.1. Scrum: Increment có thể sử dụng và nhịp kiểm tra/thích ứng

Trong Scrum:

- **Product Owner** chịu trách nhiệm Product Goal và thứ tự Product Backlog theo giá trị.
- **Developers** lập Sprint Backlog, thích ứng kế hoạch mỗi ngày và tạo Increment đáp ứng Definition of Done.
- **Scrum Master** hỗ trợ Scrum Team hiệu quả hơn, làm cho trở ngại được tháo gỡ và hỗ trợ cải tiến cách phối hợp.
- **Sprint Goal** tạo mục tiêu chung giúp nhóm quyết định hoàn tất việc nào trước.
- **Sprint Review** kiểm tra kết quả và phản hồi, từ đó điều chỉnh Product Backlog.
- **Sprint Retrospective** giúp nhóm xem lại chất lượng và cách cộng tác, thử cải tiến.

Nếu Sprint kết thúc với 14 PBI đã mở nhưng chỉ một Increment Done, nhóm cần hỏi WIP, chia lát, phụ thuộc và DoD. Không nên lấy việc tăng story points được ghi nhận làm giải pháp thay thế.

**Một Increment đã Done có thể được bàn giao trước khi Sprint kết thúc; Sprint Review không phải cổng phát hành mặc định.** Giảm chờ phát hành có thể rút ngắn vòng phản hồi, với điều kiện release phù hợp và an toàn.

### 12.2. Kanban: nhìn luồng và giới hạn công việc đang dở

Kanban giúp nhóm:

- Trực quan hóa các bước và hàng chờ.
- Đặt các chính sách công khai (bao gồm WIP).
- Quan sát flow metrics và tuổi công việc.
- Quản lý luồng dựa trên khả năng hoàn tất.
- Cải tiến cách làm bằng thử nghiệm.

Một Scrum Team có thể áp dụng các kỹ thuật Kanban để cải thiện luồng trong Sprint; một nhóm dùng Kanban có thể duy trì mục tiêu sản phẩm và nhịp review phù hợp mà không phải mô phỏng mọi sự kiện Scrum.

### 12.3. XP: giảm làm lại bằng kỹ thuật phản hồi sớm

Các thực hành **Extreme Programming (XP)** góp phần giảm việc phát hiện lỗi muộn:

- **TDD/kiểm thử tự động:** mô tả hành vi kỳ vọng, chạy lại khi thay đổi.
- **Continuous Integration:** tích hợp thường xuyên để phát hiện xung đột sớm.
- **Refactoring:** duy trì thiết kế dễ sửa khi cần thêm lát mới.
- **Pair Programming:** tăng trao đổi ngữ cảnh, giảm phụ thuộc thông tin vào một người trong công việc phù hợp.
- **Simple Design:** không xây trước hàng loạt khả năng chưa có nhu cầu xác thực.
- **Collective ownership** trong bối cảnh phù hợp: tránh việc mọi thay đổi phải chờ một cá nhân duy nhất, nhưng vẫn giữ kiểm soát chuyên môn cần thiết.

Kỹ thuật tốt không tự giải quyết mọi lãng phí; nếu phê duyệt hợp đồng mất một tháng, CI tốt vẫn cần phối hợp quản trị để giảm điểm chờ đó.

## 13. Tình huống xuyên suốt: từ ý tưởng “Học tiếp” tới kết quả thật

Một nhóm Agile đang phát triển khả năng người học **mở lại video tại vị trí đã dừng**. Nhóm quan sát một story từ lúc bắt đầu đến khi đạt DoD:

| Bước | Trạng thái ban đầu | Dấu hiệu lãng phí |
| --- | --- | --- |
| Làm rõ nghiệp vụ | Developers đã bắt đầu nhưng còn chờ quy tắc lúc nào lưu tiến độ. | Chờ đợi do làm rõ muộn. |
| Thiết kế API | Backend dựa trên giả định không được frontend/QA cùng kiểm tra. | Bàn giao và mất ngữ cảnh. |
| Lập trình | Ba story khác cùng mở, người làm chuyển qua lại. | WIP cao, chuyển đổi bối cảnh. |
| Review | PR lớn nằm chờ người chuyên trách. | Chờ và phụ thuộc một người. |
| Kiểm thử | Phát hiện thiếu trường hợp tài khoản khác đọc tiến độ. | Làm lại do thiếu tiêu chí phân quyền sớm. |
| Chuẩn bị phát hành | Increment đã Done nhưng nằm chờ cuộc họp không có kiểm soát phát hành bắt buộc. | Có thể là chờ không cần thiết. |

### 13.1. Tìm nguyên nhân thay vì đổ lỗi

Hãy hỏi bằng thái độ tìm hiểu hệ thống:

- Tại sao quy tắc lưu tiến độ không được làm rõ trước khi code?
- Vì sao chỉ một reviewer biết khu vực thay đổi?
- Vì sao QA chỉ thấy câu chuyện khi đã viết xong?
- Điều gì khiến một Developer phải giữ ba story cùng lúc?
- DoD và acceptance criteria có thể giúp phát hiện thiếu phân quyền sớm hơn không?
- Vì sao cần cuộc họp phát hành? Có nghĩa vụ thực sự hay chỉ là thói quen?

Không cần giả định các cá nhân thiếu trách nhiệm. Có thể vấn đề nằm ở **chính sách luồng, cấu trúc chuyên môn, cách ra quyết định và kiểm soát chất lượng**.

### 13.2. Thiết kế cách làm cải tiến

Nhóm có thể thử:

1. Trong refinement, PO và Developers thống nhất user story V1 cùng ví dụ thành công/thất bại.
2. Chia lát nhỏ đủ để một nhịp làm việc hoàn tất đầu cuối.
3. Giới hạn WIP ở Develop và Review, ưu tiên xử lý các mục gần Done.
4. Dùng review ngắn hoặc lập trình cặp cho phần quyền truy cập nhiều rủi ro.
5. Chạy kiểm thử đơn vị, API và các trường hợp tích hợp trong pipeline.
6. Giữ DoD đầy đủ; nếu phát hiện rủi ro mới, thông báo sớm.
7. Khi Increment Done và đủ điều kiện release, mở thử có kiểm soát mà không chờ sự kiện không cần thiết.
8. Thu phản hồi người học, cập nhật Product Backlog theo giá trị thật.

### 13.3. Ví dụ tiêu chí chấp nhận giúp ngăn làm lại

~~~gherkin
Feature: Tiếp tục xem video từ vị trí đã lưu

Scenario: Người học có tiến độ được lưu
  Given người học đã đăng nhập và có quyền xem "Bài A"
  And hệ thống lưu vị trí 05:20 của người học cho "Bài A"
  When người học mở lại "Bài A"
  Then video có thể tiếp tục ở vị trí đã lưu trong sai số đã thỏa thuận

Scenario: Chưa từng lưu tiến độ
  Given người học có quyền xem "Bài A"
  And chưa có tiến độ lưu cho người học và "Bài A"
  When người học mở "Bài A"
  Then video bắt đầu ở đầu bài
  And giao diện không thông báo sai rằng đã khôi phục tiến độ

Scenario: Không có quyền đọc tiến độ người khác
  Given một tài khoản không được phép xem tiến độ của học viên khác
  When tài khoản đó yêu cầu dữ liệu tiến độ của học viên khác
  Then hệ thống từ chối truy cập theo chính sách
  And không tiết lộ dữ liệu tiến độ riêng tư

Scenario: Không thể lưu tiến độ
  Given người học đang xem video có quyền truy cập
  And thao tác lưu tiến độ gặp lỗi
  When ứng dụng nhận phản hồi thất bại
  Then không hiển thị thông báo lưu thành công sai sự thật
  And người học nhận hướng dẫn phù hợp để tiếp tục
~~~

Acceptance criteria mô tả các tình huống của story. **Definition of Done** xác định mức chất lượng hoàn tất của Increment; không thể bỏ kiểm thử và tích hợp chỉ vì các ví dụ trên đã được viết.

### 13.4. Đo hiệu quả sau cải tiến

Nhóm không chỉ hỏi “số ticket có tăng không?” mà xem:

- Thời gian chờ review/kiểm thử có giảm?
- Cycle time đến Done có ngắn hơn với cùng chính sách DoD?
- WIP và tuổi các mục đang dở thay đổi ra sao?
- Tỷ lệ phải mở lại story hoặc lỗi sau release có tăng không?
- Người học có thực sự tiếp tục video dễ hơn không?
- Những phụ thuộc nào vẫn chưa xử lý được?

Nếu cycle time giảm nhưng rủi ro dữ liệu tăng, cải tiến chưa đáp ứng mục tiêu. Nếu người học không dùng V1, nhóm nên **xem lại giả thuyết giá trị** chứ không chỉ làm nhanh các lát tiếp theo.

## 14. Cải tiến một nút thắt: cách thử thay vì tái tổ chức lớn

Lean khuyến khích cải tiến nhỏ, quan sát được. Nhóm có thể dùng chu trình thử nghiệm **Plan – Do – Check – Act (PDCA)**:

- **Plan:** xác định vấn đề, giả thuyết và số đo.
- **Do:** thử thay đổi ở phạm vi có thể kiểm soát.
- **Check:** đọc kết quả, kiểm tra cả hiệu ứng phụ.
- **Act:** giữ, điều chỉnh hoặc bỏ thử nghiệm; ghi điều học được.

### Ví dụ: giảm chờ review

**Vấn đề:** PR của một loại story thường chờ review lâu, dù thời gian lập trình không cao.

**Giả thuyết:** “Nếu chúng ta chia PR nhỏ hơn và dành ưu tiên cho các PR đã chờ, thời gian từ yêu cầu review đến kết luận sẽ giảm, trong khi lỗi sau phát hành không tăng.”

**Thử nghiệm gợi ý trong hai tuần hoặc một lượng mẫu phù hợp:**

1. Xác định trước **loại PR** đưa vào thử.
2. Ghi thời gian từ “ready for review” tới “review hoàn tất” trước và trong thử nghiệm.
3. Khi Review đạt WIP limit, nhóm ưu tiên hỗ trợ xử lý hàng chờ trước khi mở nhiều việc mới.
4. Chia thay đổi theo hành vi nhỏ hơn nếu có thể tích hợp an toàn.
5. Ghi số lỗi lọt ra, sửa lại sau review, cảm nhận về chất lượng trao đổi.
6. Sau thử nghiệm, so sánh phân bố và các trường hợp bất thường, không chỉ một giá trị trung bình.

**Không kết luận trước:** Có thể review nhanh hơn nhưng số lần sửa lại tăng. Khi đó cần tìm nguyên nhân: PR thiếu ngữ cảnh, chất lượng đầu vào giảm hay phạm vi thử quá khác với dữ liệu cũ.

### Cần tránh “thử nghiệm không có điểm dừng”

Một thử nghiệm tốt có **ngày/điều kiện xem lại, người chịu trách nhiệm, giả thuyết và tiêu chí thành công**. “Chúng ta sẽ thử làm nhanh hơn từ nay về sau” không đủ để tạo học hỏi có thể kiểm chứng.

## 15. Phân biệt lãng phí thật với hoạt động bảo vệ giá trị

Lean bị hiểu sai khi người ta gọi tất cả thời gian không gõ code là “lãng phí”.

| Hoạt động | Có thể gây chờ/lãng phí khi nào? | Vì sao vẫn có thể cần thiết? |
| --- | --- | --- |
| **Kiểm thử tự động và thủ công** | Lặp lại vô mục đích, môi trường lỗi, đợi test tới cuối kỳ. | Bảo vệ chất lượng, dữ liệu và người dùng; phát hiện lỗi trước release. |
| **Review code** | PR nằm chờ, quá nhiều vòng qua lại không có tiêu chí. | Chia sẻ kiến thức, phát hiện thiết kế sai, tăng khả năng bảo trì. |
| **Kiểm soát bảo mật/tuân thủ** | Phê duyệt trùng, gửi hồ sơ qua nhiều cấp không rõ mục đích. | Nghĩa vụ an toàn, quyền riêng tư và pháp lý cần được bảo đảm. |
| **Làm rõ yêu cầu** | Tổ chức họp lặp lại nhưng không có quyết định; thông tin không tới người cần. | Giảm hiểu sai và làm lại, định hướng tới nhu cầu thật. |
| **Refactoring** | Sửa cấu trúc tùy hứng, không gắn nhu cầu hoặc rủi ro. | Duy trì thiết kế dễ thay đổi, giảm lỗi/chi phí dài hạn. |
| **Đào tạo và chia sẻ kiến thức** | Chương trình không phục vụ nhu cầu thực tế, kiến thức không được áp dụng. | Giảm phụ thuộc vào một người, cải thiện năng lực và khả năng phối hợp. |
| **Nghỉ ngơi, thời gian tập trung** | Không nên mặc nhiên coi là lãng phí. | Năng lực nhận thức và sức khỏe cần thiết cho chất lượng bền vững. |

Câu hỏi không phải “làm sao xóa hoạt động này?” mà là **“nó phục vụ điều kiện giá trị/chất lượng nào, và cách thực hiện hiện tại có đơn giản, nhanh, đáng tin hơn được không?”**

### Tối ưu toàn hệ thống thay vì gây áp lực cá nhân

Nếu một hệ thống luôn có hàng chờ review, yêu cầu reviewer “làm nhanh gấp đôi” có thể làm lỗi lọt qua và tăng rework. Nên điều tra số PR tới, kích thước PR, chính sách phân phối review, năng lực dự phòng và độ rõ tiêu chí.

Chỉ số luồng được dùng để cải thiện **hệ thống phối hợp**, không tạo bảng xếp hạng ai “chờ nhiều nhất” hoặc ai “sửa lỗi nhiều nhất” mà không xét loại việc và bối cảnh.

## 16. Những sai lầm thường gặp khi áp dụng Lean

| Sai lầm | Vì sao gây hại | Điều nên làm |
| --- | --- | --- |
| **Đếm tất cả thời gian không code là lãng phí.** | Bỏ qua kiểm thử, thiết kế, trao đổi và an toàn cần thiết. | Phân loại hoạt động theo giá trị và ràng buộc thật. |
| **Tối ưu một bộ phận mà không xem luồng end-to-end.** | Nút thắt dịch chuyển, người dùng vẫn nhận kết quả muộn. | Dùng VSM và số đo tới Done/Released. |
| **Mở nhiều việc để mọi người luôn bận.** | WIP cao, hàng chờ dài và chuyển ngữ cảnh. | Giới hạn WIP và ưu tiên hoàn tất. |
| **Chia UI, API, database thành “story Done” độc lập.** | Chưa có hành vi đầu cuối, tích hợp dồn về cuối. | Chia lát dọc với DoD thực sự. |
| **Xóa mọi bàn giao.** | Có thể phá kiểm soát độc lập, quyền hạn hoặc yêu cầu chuyên môn. | Giảm mất ngữ cảnh, tự động hóa và tham gia sớm thay vì bỏ bước cần thiết. |
| **Đổ lỗi khi phát hiện rework.** | Nhóm giấu lỗi, cắt kiểm thử và giảm minh bạch. | Phân tích nguyên nhân, điều chỉnh phản hồi đầu vào và kỹ thuật. |
| **Coi mọi thay đổi theo phản hồi người dùng là rework vô ích.** | Ngăn học hỏi và thích ứng. | Phân biệt khám phá giá trị với sai sót phòng ngừa được. |
| **Đo số ticket đóng thay cho giá trị.** | Chia vụn ticket làm số đẹp, người dùng vẫn chưa dùng được. | Kết hợp flow metrics, DoD và outcome. |
| **Giảm cycle time bằng cách đổi định nghĩa Done.** | Số liệu đẹp nhưng lỗi và chi phí vận hành tăng. | Giữ tiêu chuẩn Done nhất quán; báo rõ thay đổi cách đo. |
| **Áp WIP limit cứng mà không xét công việc khẩn.** | Gây phản tác dụng trong sự cố hoặc yêu cầu kiểm soát. | Có chính sách ngoại lệ rõ và đánh giá tác động. |
| **Thử cải tiến rồi không xem lại.** | Không biết thay đổi tạo lợi ích hay vấn đề mới. | Có giả thuyết, số đo và thời điểm Check/Act. |
| **Dùng flow efficiency làm KPI cá nhân.** | Khuyến khích sửa số liệu hoạt động/chờ, che điểm nghẽn. | Đo ở cấp hệ thống, dùng để hỏi và cải tiến. |

## 17. Bài tập: tìm lãng phí trong một Sprint

Một Scrum Team phát triển **ứng dụng đặt lịch tư vấn**. Sprint Goal là: “Người dùng có thể đặt một lịch hợp lệ và nhận xác nhận rõ, không tạo trùng lịch.” Nhóm gồm Developers có chuyên môn frontend, backend, kiểm thử và vận hành.

Trong tuần đầu:

- Năm story khác nhau được bắt đầu song song.
- Yêu cầu “không đặt trùng lịch” chưa có ví dụ trường hợp hai người xác nhận cùng lúc.
- Frontend phát triển giao diện dựa trên API giả, backend thiết kế API theo giả định riêng.
- Khi tích hợp, tên trường và trạng thái lỗi không khớp.
- Hai PR chờ review ba ngày vì chỉ một người được phép duyệt.
- Môi trường test chưa được cấp quyền dữ liệu, chờ thêm hai ngày.
- Trong thời gian chờ, nhóm mở thêm hai story mới.
- Cuối tuần, nhiều task được ghi “90%”, nhưng chưa có luồng đặt lịch nào đạt DoD.

### Nhiệm vụ

1. **Phân loại:** Tìm ít nhất hai ví dụ cho từng nhóm chờ đợi, bàn giao, làm lại và việc chưa hoàn tất. Một tình huống có thể thuộc nhiều nhóm.
2. **Xác định mục tiêu:** Viết một hành vi đầu cuối nhỏ nhất có thể tạo giá trị và có thể demo.
3. **Ngăn làm lại:** Viết ba tiêu chí chấp nhận, gồm trường hợp hai người đặt cùng khung giờ và trường hợp không có quyền.
4. **Vẽ VSM:** Chọn một story và ghi các bước, thời gian làm/thời gian chờ. Nêu điểm bắt đầu và Done.
5. **Chọn cải tiến:** Nếu chỉ được thử hai thay đổi trong Sprint sau, bạn chọn gì? Dự kiến số đo nào sẽ phản ánh kết quả?
6. **Ràng buộc:** Chỉ ra những bước không được bỏ dù nhóm muốn hoàn tất nhanh, và giải thích vì sao.
7. **Dữ liệu:** Nếu cycle time giảm nhưng lỗi đặt trùng sau phát hành tăng, bạn sẽ kết luận gì?
8. **Phân tích nguyên nhân:** Viết ba câu hỏi “tại sao” theo hướng hệ thống, không quy chụp cá nhân.

### Hướng giải tham khảo

**Chờ đợi:** PR chờ reviewer; môi trường test chờ quyền; Developers có thể còn chờ làm rõ quy tắc không trùng lịch. **Bàn giao:** frontend/backend dùng các giả định không khớp; kiểm thử chỉ nhận được thông tin khi quá muộn; phụ thuộc một reviewer duy nhất. **Làm lại:** sửa hợp đồng giao tiếp API; sửa trạng thái lỗi; có thể phải bổ sung kiểm soát đặt trùng khi phát hiện quy tắc muộn. **Việc chưa hoàn tất:** năm rồi thêm hai story cùng mở; nhiều task “90%” nhưng không có Increment đạt DoD.

**Lát dọc đề xuất:** “Người dùng có quyền xem khung giờ trống, đặt một lịch và nhận xác nhận đúng, trong khi hệ thống không tạo hai lịch cho cùng khung giờ khi không được phép.” Đây là hành vi từ đầu đến cuối, không phải riêng task database hoặc frontend.

**Tiêu chí chấp nhận minh họa:**

~~~gherkin
Feature: Đặt lịch tư vấn hợp lệ

Scenario: Khung giờ còn trống
  Given người dùng đã đăng nhập và có quyền đặt lịch
  And khung giờ được chọn còn chỗ tại lúc xác nhận
  When người dùng xác nhận đặt lịch
  Then hệ thống ghi nhận đúng một lịch hợp lệ
  And hiển thị xác nhận nhất quán với dữ liệu đã lưu

Scenario: Hai yêu cầu cạnh tranh cùng khung giờ
  Given một khung giờ chỉ cho phép một lịch hẹn
  And hai người dùng đủ quyền cùng xác nhận khung giờ đó
  When hệ thống xử lý các yêu cầu gần đồng thời
  Then chỉ một yêu cầu có thể chiếm khung giờ thành công
  And yêu cầu còn lại nhận thông tin khung giờ không còn chỗ

Scenario: Người dùng không có quyền
  Given một người dùng không được quyền đặt lịch cho tài nguyên đã chọn
  When người dùng gửi yêu cầu đặt lịch
  Then hệ thống từ chối theo chính sách
  And không ghi nhận lịch hẹn trái quyền
~~~

**Hai thử nghiệm cải tiến:** (1) refinement sớm với ví dụ nghiệp vụ cùng frontend/backend/QA và chia lát dọc; (2) giảm WIP và dùng review cùng nhau/đầu mối dự phòng khi Review đầy. Đo thời gian chờ review, cycle time, work item age, số lần sửa do hiểu sai và lỗi sau release.

**Không được bỏ:** kiểm thử đúng đắn xử lý đồng thời, kiểm tra quyền truy cập, tích hợp thật và điều kiện chất lượng bắt buộc. Nếu phải giảm phạm vi, bỏ bộ lọc nâng cao hoặc tùy chỉnh giao diện trước, **không bỏ tính toàn vẹn lịch hẹn**.

**Diễn giải số đo:** Cycle time giảm nhưng đặt trùng tăng là tín hiệu cải tiến đang đánh đổi chất lượng. Cần xem DoD và kiểm thử có bị hạ hay không; giảm lãng phí đúng nghĩa phải nhìn **toàn hệ thống**, bao gồm tác động người dùng.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Hai Developers luôn bận, nhưng PR chờ review ba ngày. Đó có thể là lãng phí gì?

**Đáp án:** Chờ đợi và tồn kho việc chưa hoàn tất; có thể thêm lãng phí bàn giao nếu ngữ cảnh review bị mất. Cần quan sát luồng, không suy từ mức độ bận rộn của cá nhân.

**Câu 2.** Có nên bỏ kiểm thử tích hợp để giảm cycle time khi rủi ro mất dữ liệu chưa được xử lý không?

**Đáp án:** Không. Kiểm thử là hoạt động bảo vệ chất lượng cần thiết. Nên giảm thời gian chờ kiểm thử và tự động hóa phù hợp, không bỏ kiểm soát bắt buộc.

**Câu 3.** Một nhóm có 20 ticket In Progress và không có Done. Làm thế nào cải thiện?

**Đáp án:** Xem WIP, điểm nghẽn và phụ thuộc; ưu tiên hoàn tất lát có giá trị, giới hạn công việc mới và phối hợp xử lý hàng chờ. Không mặc định mỗi người phải code nhanh hơn.

**Câu 4.** Mọi handoff giữa chuyên gia bảo mật và Developers đều là lãng phí?

**Đáp án:** Không. Chuyển giao hoặc kiểm soát chuyên môn có thể cần thiết; lãng phí nằm ở chờ, mất ngữ cảnh và vòng lặp không cần thiết. Nên đưa chuyên gia vào sớm và làm rõ tiêu chí.

**Câu 5.** Vì sao 16 giờ hoạt động trên tổng 56 giờ không đồng nghĩa Developers chỉ đạt 28,6% năng suất?

**Đáp án:** Đây là tỷ lệ thời gian chủ động trong luồng của một mục, bao gồm hàng chờ giữa các công đoạn; nó không đo nỗ lực hay hiệu quả của từng người. Hơn nữa một số hoạt động chủ động có thể là làm lại.

**Câu 6.** Nếu một story thay đổi sau khi nhóm thử với người dùng và hiểu đúng nhu cầu hơn, đó luôn là lãng phí làm lại?

**Đáp án:** Không. Phản hồi tạo ra học hỏi có giá trị; cần phân biệt thay đổi thích ứng hợp lý với lỗi phòng ngừa được từ yêu cầu mơ hồ hoặc tích hợp muộn.

**Câu 7.** Kanban WIP limit có tác dụng gì?

**Đáp án:** Giúp quản lý số việc đang dở, làm lộ điểm nghẽn và khuyến khích hoàn tất trước khi kéo thêm việc; giới hạn cần phù hợp bối cảnh và có chính sách ngoại lệ.

**Câu 8.** Tại sao không nên đo thành công Lean chỉ bằng số ticket đóng?

**Đáp án:** Số ticket có thể tăng do chia vụn hoặc hạ DoD, trong khi người dùng chưa có giá trị. Cần nhìn thời gian luồng, chất lượng và kết quả sản phẩm.

**Câu 9.** Một bản đồ VSM có ích cần thể hiện những gì?

**Đáp án:** Ranh giới từ đâu đến đâu, các bước xử lý, điểm chờ, người/nhóm liên quan, thời gian chủ động và thời gian trôi qua, nguyên nhân bị chặn và cơ hội học hỏi.

**Câu 10.** Sau hai tuần thử giảm thời gian review, cycle time không cải thiện. Có thể kết luận thử nghiệm hoàn toàn vô ích không?

**Đáp án:** Chưa đủ cơ sở. Có thể hàng chờ đã chuyển sang Verify, công việc thay đổi, mẫu chưa đủ hoặc cải tiến không tác động nút thắt lớn nhất. Cần đọc dữ liệu và điều chỉnh giả thuyết.

## 19. Checklist nhận diện lãng phí trong một nhóm

Dùng các câu hỏi sau khi xem bảng công việc hoặc trong một cuộc Retrospective. Không nhất thiết phải trả lời tất cả trong một lần.

### Chờ đợi

- [ ] Có biết story nào đang blocked và vì sao không?
- [ ] Có bước review/kiểm thử/phê duyệt nào thường tạo hàng chờ lâu?
- [ ] Người chịu trách nhiệm hoặc cơ chế gỡ phụ thuộc đã rõ chưa?
- [ ] Nhóm có ưu tiên hoàn tất những mục gần Done trước khi kéo việc mới không?

### Bàn giao

- [ ] Người nhận có đủ bối cảnh, ví dụ hành vi và tiêu chí hoàn tất không?
- [ ] Frontend, backend, kiểm thử và vận hành có được trao đổi sớm khi cần?
- [ ] Có bước bàn giao trung gian nào chỉ chuyển thông điệp chứ không thêm giá trị?
- [ ] Các kiểm soát bắt buộc đã được thiết kế thuận tiện, không bị bỏ qua?

### Làm lại

- [ ] Những lỗi phổ biến có bị phát hiện quá muộn không?
- [ ] Acceptance criteria có bao gồm điều kiện đúng đắn và lỗi quan trọng?
- [ ] Nhóm có tích hợp, chạy test và nhận phản hồi đủ sớm?
- [ ] Có phân biệt thay đổi vì học hỏi giá trị với sửa do sai sót phòng ngừa được?

### Việc chưa hoàn tất

- [ ] Có quá nhiều story cùng In Progress?
- [ ] Có nhiều PR hoặc nhánh tồn tại lâu chưa được tích hợp?
- [ ] WIP, work item age và chính sách kéo việc đã được quan sát?
- [ ] Nhóm có demo được Increment đạt DoD thường xuyên không?

**Điều kiện thành công của checklist:** Không phải tích vào tất cả các ô bằng mọi giá, mà là xác định **một nút thắt có ảnh hưởng lớn, một thử nghiệm cải tiến và cách kiểm tra kết quả**.

## 20. Ghi nhớ trọng tâm

- **Lean tối ưu dòng tạo giá trị, không tối đa hóa sự bận rộn của từng người.** Hãy nhìn từ nhu cầu đến hành vi phần mềm có thể sử dụng và phản hồi sau đó.
- **Chờ đợi** là công việc đứng yên vì hàng chờ, phụ thuộc, quyết định hoặc môi trường; giảm bằng cách hiển thị blocked, quản lý WIP và xử lý nút thắt.
- **Bàn giao gây lãng phí** khi mất ngữ cảnh và tạo nhiều vòng hỏi lại; giảm bằng cộng tác sớm, tiêu chí rõ và lát dọc đầu cuối, nhưng vẫn giữ kiểm soát cần thiết.
- **Làm lại** thường tăng khi yêu cầu mơ hồ, tích hợp trễ và kiểm thử dồn cuối; giảm bằng ví dụ nghiệp vụ, feedback sớm, CI, TDD và DoD.
- **Việc chưa hoàn tất** là tồn kho vô hình: nhiều thay đổi đang dở nhưng chưa tạo giá trị. Giới hạn WIP và **hoàn tất trước khi bắt đầu thêm** giúp giảm dòng chờ.
- **Bốn dạng lãng phí có thể tạo vòng lặp khuếch đại nhau.** Sửa một bước mà không xem toàn hệ thống dễ chỉ chuyển nút thắt đi nơi khác.
- **Value Stream Mapping** giúp thấy thời gian chủ động, thời gian chờ và điểm mất ngữ cảnh. Flow efficiency là chỉ số của luồng, không phải KPI cá nhân.
- **Cycle time, throughput, WIP, work item age, blocked time** cần được định nghĩa nhất quán và đọc cùng chất lượng, phản hồi người dùng.
- **Scrum, Kanban và XP** có thể hỗ trợ Lean: mục tiêu và Increment, chính sách luồng/WIP, kỹ thuật tích hợp và kiểm thử sớm.
- **Cải tiến nhỏ, có giả thuyết và đo lường** đáng tin cậy hơn thay đổi quy trình lớn chỉ dựa trên cảm giác.
- **Không gọi chất lượng, bảo mật, trao đổi hoặc sự nghỉ ngơi là lãng phí mặc định.** Hệ thống giao hàng phải an toàn và bền vững.

Khi nhìn một story đang chờ, nhóm Lean không chỉ hỏi **“Ai làm chậm?”** mà hỏi **“Công việc đang bị chặn ở đâu, vì sao, và cách nào giúp đưa giá trị tới người dùng sớm hơn mà vẫn giữ chất lượng?”** Chính sự chuyển đổi góc nhìn đó giúp Agile giao sản phẩm tăng dần, thu phản hồi sớm và cải tiến liên tục.
