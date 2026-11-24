# Daily Scrum và điều chỉnh kế hoạch của Developers

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Trình bày chính xác **mục đích, người tham gia và giới hạn 15 phút** của Daily Scrum theo *Scrum Guide 2020*.
- Phân biệt **kiểm tra tiến độ hướng tới Sprint Goal** với việc lần lượt báo cáo hôm qua làm gì cho quản lý.
- Giải thích vì sao **Developers** tự tạo, sở hữu và điều chỉnh **Sprint Backlog** trong suốt Sprint, thay vì chờ Scrum Master phân công từng công việc.
- Dùng bản sản phẩm đang chạy, trạng thái hạng mục, phụ thuộc, trở ngại và dữ liệu dòng công việc để quyết định **việc quan trọng nhất tiếp theo**.
- Tổ chức Daily Scrum ngắn gọn nhưng dẫn tới hành động: phối hợp, hỗ trợ nhau, làm rõ phạm vi và xử lý vấn đề chuyên sâu ngoài sự kiện.
- Ứng dụng trong ví dụ đội phát triển nền tảng học trực tuyến và nhận diện các sai lầm như status meeting, cập nhật bảng hình thức hoặc đổi mục tiêu Sprint tùy tiện.

## 1. Daily Scrum không phải buổi điểm danh công việc

Đội phát triển một nền tảng học trực tuyến đang có Sprint Goal:

> **Học viên đã ghi danh khóa Java nhập môn có thể mở bài đầu tiên với quyền truy cập chính xác.**

Mỗi ngày, đội cần biết mình **đã gần đạt mục tiêu hơn chưa** và **cần điều chỉnh cách phối hợp như thế nào**. Đây mới là câu hỏi trung tâm của Daily Scrum.

Giả sử ba người phát biểu:

- “Hôm qua tôi viết API, hôm nay viết tiếp.”
- “Hôm qua tôi dựng giao diện, hôm nay vẫn dựng.”
- “Hôm qua tôi kiểm thử, hôm nay tiếp tục kiểm thử.”

Những câu này có thể hoàn toàn đúng, nhưng nhóm vẫn **chưa biết** giao diện đã kết nối được API hay chưa, quyền truy cập có hoạt động không, có lỗi nào đang chặn mục tiêu và ai sẽ cùng giải quyết.

Thử chuyển sang câu hỏi về kết quả:

- “Luồng ghi danh đã chạy được, nhưng học viên chưa được cấp quyền mở bài đầu. Sprint Goal còn bị chặn ở bước đó.”
- “API đã có trạng thái cấp quyền, song giao diện vẫn dùng hợp đồng cũ. Chúng ta cần ghép cặp tích hợp trước khi bắt đầu giao diện chứng chỉ.”
- “Tôi có thể hỗ trợ kiểm thử phân quyền ngay sau khi phần tích hợp sẵn sàng. Việc này quan trọng hơn mở thêm story mới.”

Sự khác biệt không nằm ở cách nói chuyên nghiệp hơn, mà nằm ở **quyết định mà nhóm có thể đưa ra sau cuộc trao đổi**.

Theo *Scrum Guide 2020*, mục đích của **Daily Scrum** là **kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần, điều chỉnh công việc sắp tới đã được lên kế hoạch**.

> **Câu hỏi cốt lõi:** “Với những gì chúng ta biết hôm nay, Developers cần phối hợp và thay đổi kế hoạch nào để tăng cơ hội đạt Sprint Goal với chất lượng đã cam kết?”

## 2. Daily Scrum được Scrum Guide quy định thế nào?

| Nội dung | Quy định trong Scrum Guide 2020 | Diễn giải thực tế |
| --- | --- | --- |
| **Mục đích** | Kiểm tra tiến độ tới **Sprint Goal** và điều chỉnh **Sprint Backlog** khi cần. | Tìm quyết định tiếp theo hữu ích cho mục tiêu chung. |
| **Thời lượng** | Sự kiện **15 phút**. | Giữ cuộc trao đổi tập trung; phần cần nghiên cứu sâu được làm sau. |
| **Người tham gia chính** | Daily Scrum là sự kiện **dành cho Developers** trong Scrum Team. | Developers tự kiểm tra, quyết định cách phối hợp và cập nhật kế hoạch. |
| **Nhịp tổ chức** | Cùng thời gian, cùng địa điểm vào **mỗi ngày làm việc của Sprint** để giảm phức tạp. | Với đội từ xa, “địa điểm” có thể là một phòng họp trực tuyến nhất quán. |
| **Cấu trúc** | **Developers chọn cấu trúc và kỹ thuật**, miễn tập trung vào tiến độ tới Sprint Goal và tạo kế hoạch khả thi cho ngày tiếp theo. | Không bắt buộc đi một vòng theo người hoặc dùng bộ ba câu hỏi cố định. |
| **Product Owner và Scrum Master** | Nếu đang **chủ động làm các hạng mục trong Sprint Backlog**, họ tham gia với tư cách Developers. | Không mặc định biến Daily Scrum thành buổi báo cáo cho hai vai trò này. |
| **Trao đổi khác trong ngày** | Daily Scrum **không phải lúc duy nhất** Developers được điều chỉnh kế hoạch. | Developers có thể phối hợp, phân tích, tái lập kế hoạch chi tiết bất cứ lúc nào cần. |

**Hai hiểu lầm cần tránh:**

1. Scrum Guide **không yêu cầu** mọi người lần lượt trả lời “hôm qua làm gì, hôm nay làm gì, đang vướng gì?” Đội có thể dùng cách đó nếu thật sự giúp kiểm tra Sprint Goal; không phải nghi thức bắt buộc.
2. Scrum Guide **không yêu cầu** Scrum Master phải chủ trì, gọi tên từng người hoặc phân công task. Developers sở hữu mục đích và cách thực hiện Daily Scrum. Scrum Master giúp Scrum được hiểu và áp dụng hiệu quả.

### 2.1. Ai là Developers?

Trong Scrum, **Developers** là những người trong Scrum Team chịu trách nhiệm tạo ra **Increment hữu dụng** mỗi Sprint. Không chỉ có người viết mã: người làm kiểm thử, thiết kế trải nghiệm, phân tích, dữ liệu hoặc vận hành có thể thuộc Developers nếu họ tham gia tạo Increment.

Một đội nhiều chuyên môn vẫn có một Sprint Goal chung. Daily Scrum không chia thành “báo cáo frontend”, “báo cáo backend”, “báo cáo QA” riêng lẻ nếu điều đó che mất kết quả xuyên suốt.

### 2.2. Đội dùng Daily Scrum để thanh tra và thích nghi

Daily Scrum góp phần hiện thực hóa ba trụ cột thực nghiệm của Scrum:

- **Minh bạch:** công việc, rủi ro, phụ thuộc và tình trạng đạt mục tiêu được thể hiện rõ.
- **Thanh tra:** Developers nhìn phần mềm, Sprint Backlog và những gì đã xảy ra, thay vì chỉ dựa vào cảm giác “đang ổn”.
- **Thích nghi:** cập nhật kế hoạch, dồn sức giải quyết nút thắt, hỏi người có trách nhiệm hoặc thương lượng phạm vi khi cần.

Daily Scrum sẽ kém hữu ích nếu cả đội biết một vấn đề đang tồn tại nhưng **không có quyết định, hành động hoặc người tiếp nhận** sau cuộc trao đổi.

## 3. Ba thứ Developers cần nhìn cùng nhau

Một Daily Scrum hiệu quả thường kết hợp **Sprint Goal, Sprint Backlog và bằng chứng từ sản phẩm/công việc thực tế**.

### 3.1. Sprint Goal — đích đến chung

**Sprint Goal** là cam kết gắn với Sprint Backlog, giúp Scrum Team tập trung vào một mục tiêu duy nhất cho Sprint. Nó tạo **định hướng và linh hoạt**: nhóm có thể thương lượng chi tiết việc thực hiện trong khi cùng hướng về kết quả đó.

So sánh:

| Mô tả | Hạn chế hoặc ưu điểm |
| --- | --- |
| “Làm 10 user stories và 40 story points.” | Thiên về số lượng đầu ra; chưa chỉ rõ vì sao Sprint tạo giá trị. |
| “Học viên đã ghi danh khóa miễn phí mở được bài đầu tiên một cách hợp lệ.” | Là mục tiêu hành vi có thể trình diễn/kiểm chứng. |
| “Hoàn tất ba API backend.” | Có thể là phần việc cần thiết nhưng chưa bảo đảm hành trình người học hoạt động. |

Không phải Sprint Goal nào cũng phải đo bằng một chỉ số kinh doanh ngay trong Sprint. Nhưng đội cần hiểu **điều kiện thành công** và biết phần mềm nào sẽ chứng minh mục tiêu đang tiến triển.

### 3.2. Sprint Backlog — kế hoạch sống của Developers

Theo Scrum Guide, **Sprint Backlog** gồm:

1. **Sprint Goal** — vì sao công việc có giá trị.
2. **Các Product Backlog Items được chọn cho Sprint** — điều gì được thực hiện.
3. **Kế hoạch khả thi để tạo Increment** — thực hiện bằng cách nào.

Sprint Backlog là **kế hoạch do Developers lập và dành cho Developers**. Nó được cập nhật trong Sprint khi đội học thêm. Mức chi tiết đủ để Developers thanh tra tiến độ trong Daily Scrum; không phải một bản kế hoạch cố định do bên ngoài giao rồi cấm sửa.

Ví dụ:

```text
Sprint Goal: Học viên đã ghi danh có thể mở bài đầu tiên đúng quyền.

Sprint Backlog:
  [Đang làm] Cấp quyền truy cập khóa học sau ghi danh
    - Kiểm tra trạng thái ghi danh
    - Hoàn tất API cấp quyền
    - Kiểm tra trường hợp đăng nhập sai tài khoản
  [Đang làm] Giao diện "Bắt đầu học"
    - Tích hợp kết quả từ API
  [Chờ kiểm chứng] Mở bài đầu tiên
    - Kiểm thử luồng ghi danh → mở bài
  [Chưa bắt đầu] Cải thiện nội dung hướng dẫn trên màn hình
```

Nếu sáng nay phát hiện API trả dữ liệu khác dự kiến, Developers có thể **cập nhật ngay kế hoạch tích hợp**. Không cần giữ nguyên task chỉ vì task đã được viết trong Sprint Planning.

### 3.3. Bằng chứng thực tế — không chỉ màu thẻ

Các tín hiệu có thể xem trước hoặc trong Daily Scrum:

- Một **luồng chạy được** trên môi trường tích hợp, ví dụ “ghi danh → cấp quyền → mở bài”.
- Kiểm thử tự động/kiểm thử thủ công phù hợp đang đạt hay thất bại.
- Hạng mục nào đang **bị chặn**, đang đợi người khác, hoặc đã dở dang quá lâu.
- Có quá nhiều **WIP** khiến nhóm mở thêm việc nhưng không hoàn tất.
- Phụ thuộc nào có nguy cơ làm không đạt Sprint Goal.
- Có một thay đổi nghiệp vụ nào cần Product Owner làm rõ để Developers tiếp tục không.

Bảng thẻ, biểu đồ và chỉ số giúp **nhìn thấy hiện tượng**; chúng không thay được việc nói rõ điều gì đang ngăn nhóm tạo Increment hữu dụng.

## 4. Ba câu hỏi kinh điển: có thể dùng, không bắt buộc

Một cách tổ chức Daily Scrum được nhiều đội biết tới:

1. Tôi đã làm gì hôm qua?
2. Hôm nay tôi dự kiến làm gì?
3. Tôi đang bị cản trở bởi điều gì?

Đó có thể là **cách gợi mở cuộc trò chuyện**, nhưng không phải cấu trúc được Scrum Guide 2020 bắt buộc. Khi ba câu hỏi chỉ khiến từng người báo cáo hoạt động riêng, đội cần thay đổi cách đặt câu hỏi.

| Hỏi theo tiến độ cá nhân | Hỏi theo Sprint Goal và công việc chung |
| --- | --- |
| “Hôm qua em hoàn thành bao nhiêu task?” | “Phần nào của luồng người dùng đã chạy được? Còn điều gì chưa đáp ứng mục tiêu?” |
| “Hôm nay ai viết mã gì?” | “Lát cắt nào gần Done nhất và ai có thể giúp hoàn tất?” |
| “Ai đang chậm hơn kế hoạch?” | “Hạng mục nào bị chặn, phụ thuộc đang ở đâu và bước gỡ chặn tiếp theo là gì?” |
| “Vì sao story chưa chuyển xanh?” | “Điều kiện chấp nhận hoặc DoD nào chưa đạt?” |
| “Mỗi người đã làm đủ giờ chưa?” | “Kế hoạch hôm nay cần đổi gì để tăng khả năng đạt Sprint Goal?” |

Developers có thể dùng một, ba hoặc nhiều câu hỏi; có thể đi theo từng hạng mục trên bảng hoặc một luồng người dùng. **Tiêu chí đánh giá** là cuộc trao đổi có tạo ra kế hoạch khả thi và sự phối hợp tốt hơn không.

## 5. Một cách điều phối 15 phút theo mục tiêu

Dưới đây là **mẫu tùy chọn** cho đội phát triển phần mềm. Đây không phải công thức bắt buộc của Scrum:

| Khoảng thời gian minh họa | Nội dung | Quyết định/kết quả cần có |
| --- | --- | --- |
| **0–2 phút** | Nhắc Sprint Goal và kiểm tra điều gì đã trở thành phần mềm hữu dụng từ hôm qua. | Cả nhóm cùng hiểu mức tiến triển. |
| **2–7 phút** | Xem các hạng mục gần Done, việc đang chờ kiểm thử/tích hợp. | Chọn phần nên hoàn thành trước, ai có thể hỗ trợ chéo. |
| **7–12 phút** | Nhận diện trở ngại, phụ thuộc và thay đổi mới ảnh hưởng mục tiêu. | Chốt hành động mở chặn và những người cần phối hợp. |
| **12–15 phút** | Điều chỉnh kế hoạch hôm nay, cập nhật Sprint Backlog nếu cần, xác định cuộc trao đổi tiếp theo. | Một kế hoạch cụ thể, không chỉ thông báo tình trạng. |

Không cần mất thời gian gọi tuần tự tất cả thành viên nếu họ không có thông tin ảnh hưởng tới tiến độ chung. Nhưng phải tạo cơ hội để người đang nhìn thấy rủi ro **nêu thông tin kịp thời**, kể cả rủi ro nằm ngoài công việc chính của họ.

### 5.1. Chỉ đi sâu đến mức đủ để ra quyết định

Giả sử Developers phát hiện lỗi truy cập khóa học chỉ xảy ra khi học viên đổi tài khoản. Tìm nguyên nhân có thể cần 45 phút xem log và tái hiện. Nếu cố gỡ toàn bộ lỗi trong Daily Scrum, sự kiện sẽ kéo dài, những người khác bị cuốn vào chi tiết không cần thiết.

Cách phù hợp hơn:

- Trong Daily Scrum: xác nhận **lỗi đang chặn Sprint Goal**, mức độ nghiêm trọng và ai phối hợp xử lý.
- Ngay sau Daily Scrum: hai hoặc ba người liên quan kiểm tra log, thử giả thuyết, sửa mã và kiểm thử.
- Khi đã biết kết quả: **cập nhật Sprint Backlog và chia sẻ thông tin** cần thiết với nhóm, không đợi Daily Scrum hôm sau.

Daily Scrum **không cấm** Developers thảo luận chuyên sâu; nó giúp phân biệt cuộc họp kiểm tra/kế hoạch ngắn với **công việc giải quyết vấn đề thực sự**.

## 6. Ví dụ xuyên suốt: Sprint phát triển nền tảng học trực tuyến

### 6.1. Bối cảnh và Sprint Goal

Một Scrum Team xây nền tảng học Java có:

- Một Product Owner phụ trách giá trị và thứ tự Product Backlog.
- Một Scrum Master hỗ trợ hiệu quả của Scrum Team.
- Các Developers có năng lực backend, frontend, UX và kiểm thử/tích hợp.

**Sprint Goal**:

> “Học viên đã ghi danh một khóa miễn phí có thể mở được bài học đầu tiên, với quyền truy cập hợp lệ.”

Các Product Backlog Items đã được chọn gồm:

| ID | Hạng mục | Vai trò với Sprint Goal | Trạng thái đầu ví dụ |
| --- | --- | --- | --- |
| **S1** | Ghi nhận trạng thái ghi danh hợp lệ | Cần biết học viên có quyền hay không. | Đã đáp ứng điều kiện hoàn thành. |
| **S2** | Cấp và kiểm tra quyền xem bài học theo ghi danh | Bảo vệ truy cập và dữ liệu. | Đang triển khai. |
| **S3** | Nút “Bắt đầu học” và điều hướng bài đầu | Giúp người học sử dụng luồng. | Đang triển khai. |
| **S4** | Kiểm thử xuyên suốt từ ghi danh tới bài đầu | Chứng minh luồng đáp ứng chất lượng. | Đang chờ tích hợp. |
| **S5** | Cải thiện màn hình thông báo thành công | Hữu ích, nhưng không phải nút thắt quan trọng nhất. | Chưa bắt đầu. |

**Lưu ý:** đây là trạng thái của **ví dụ**. Một hạng mục chỉ được coi là “hoàn thành” khi đáp ứng Definition of Done của sản phẩm, không phải khi một người nói “đã viết xong mã”.

### 6.2. Buổi Daily Scrum: phát hiện điều quan trọng hơn việc mở task mới

Sáng thứ tư, các Developers thấy:

- S1 đã hoàn thành.
- S2 bị lỗi: một học viên đã ghi danh vẫn bị trả về “không có quyền”.
- S3 hiển thị nút nhưng chưa gọi được API cấp quyền vì dữ liệu trả về khác hợp đồng đã trao đổi.
- S4 chưa thể kiểm thử toàn luồng.
- S5 chưa có ai làm.

Một Daily Scrum kém hiệu quả có thể kết thúc bằng:

> “Backend sửa S2; frontend tiếp tục S3; QA chưa có gì để test; mọi người cứ làm như kế hoạch.”

Câu này không sai hoàn toàn, nhưng **chưa thay đổi sự phối hợp để xử lý phụ thuộc**. Những người tham gia sẽ dễ tiếp tục làm riêng lẻ.

Một cuộc trao đổi hữu ích hơn:

**Developer phụ trách tích hợp:** “Sprint Goal phụ thuộc vào việc mở bài đúng quyền; hiện API và giao diện chưa kết nối thành luồng hoạt động.”

**Developer backend:** “Tôi đã xác định một trường hợp quyền bị từ chối sau ghi danh. Cần cùng người làm kiểm thử tái hiện trên môi trường tích hợp.”

**Developer frontend:** “Tôi có thể ghép cặp để xác nhận hợp đồng API, sau đó cập nhật phần tích hợp. Tôi chưa cần bắt đầu S5.”

**Developer phụ trách kiểm thử:** “Tôi sẽ chuẩn bị dữ liệu hai tài khoản: đã ghi danh và chưa ghi danh, rồi kiểm thử phân quyền ngay khi S2 có bản sửa.”

**Cả nhóm thống nhất:** “Hôm nay dồn sức hoàn thành S2 và nối S3–S4. S5 tạm chờ; sau sự kiện chúng ta có buổi làm việc kỹ thuật để xử lý lỗi quyền.”

**Kết quả:** nhóm không chỉ biết “ai đang làm gì” mà còn biết **thứ tự và cách phối hợp mới** dựa trên rủi ro của Sprint Goal.

### 6.3. Kế hoạch trước và sau Daily Scrum

| Yếu tố | Kế hoạch trước cuộc trao đổi | Kế hoạch sau thanh tra |
| --- | --- | --- |
| Ưu tiên công việc | S2, S3 và có thể bắt đầu S5 song song. | Tập trung S2 rồi tích hợp S3–S4; S5 chờ. |
| Phối hợp | Mỗi chuyên môn xử lý riêng. | Backend + kiểm thử tái hiện lỗi; frontend + backend xác nhận hợp đồng API. |
| Kiểm chứng | Đợi tới cuối tuần để kiểm thử toàn luồng. | Kiểm thử phân quyền theo lát cắt nhỏ ngay khi tích hợp. |
| Trở ngại | “API lỗi” nhưng chưa rõ ai phối hợp. | Có hành động, người tham gia và điểm xem lại trong ngày. |
| Sprint Goal | Chưa biết khả năng đạt. | Rủi ro được nhận diện và có kế hoạch giảm rủi ro. |

Developers **cập nhật Sprint Backlog** để phản ánh cách thực hiện mới. Một thay đổi như vậy không có nghĩa Sprint Goal bị đổi; nó chính là **thích nghi kế hoạch để phục vụ Sprint Goal**.

### 6.4. Hành vi cần kiểm chứng sau tích hợp

Một số ví dụ nghiệp vụ có thể được dùng để cùng hiểu đúng:

```gherkin
Feature: Quyền truy cập bài đầu tiên sau khi ghi danh

  Scenario: Người học đã ghi danh được phép mở bài
    Given Lan đã đăng nhập
    And Lan đã ghi danh hợp lệ khóa "Java nhập môn"
    When Lan mở bài học đầu tiên của khóa đó
    Then hệ thống cho phép Lan xem nội dung của bài

  Scenario: Người học chưa ghi danh không được truy cập
    Given Nam đã đăng nhập
    And Nam chưa ghi danh khóa "Java nhập môn"
    When Nam yêu cầu mở bài học chỉ dành cho học viên đã ghi danh
    Then hệ thống từ chối truy cập nội dung của bài
    And Nam không nhìn thấy dữ liệu chỉ dành cho người đã ghi danh
```

Các ví dụ được đưa vào **kiểm thử phù hợp** và được rà soát theo yêu cầu quyền truy cập thực tế. Chúng giúp nhóm xác định **đúng là gì**, thay vì đánh dấu story hoàn thành ngay khi giao diện đã hiển thị nút.

## 7. Cập nhật Sprint Backlog: thay đổi kế hoạch như thế nào?

Sprint Backlog là hiện vật thuộc Scrum, còn **cách thể hiện** có thể là bảng vật lý, bảng điện tử hoặc công cụ khác. Quan trọng là nó minh bạch và phản ánh công việc thật của Developers.

### 7.1. Khi nào cần điều chỉnh?

Một hoặc nhiều tình huống có thể làm kế hoạch cần thay đổi:

1. **Có thông tin kỹ thuật mới:** hợp đồng API khác dự tính hoặc phải thêm trường hợp đồng bộ.
2. **Một trở ngại đã lộ rõ:** thiếu quyền truy cập môi trường, thiếu dữ liệu kiểm thử, phụ thuộc dịch vụ ngoài.
3. **Công việc đang dở kéo dài:** nhóm cần cùng hoàn thành một hạng mục trước khi kéo thêm việc.
4. **Phạm vi của một item được làm rõ:** cần chia lại cách làm hoặc thay đổi số tác vụ, miễn mục tiêu Sprint không bị nguy hại.
5. **Đã đạt một kết quả sớm:** Developers có thể lựa chọn cách tiếp tục tạo Increment theo Sprint Goal.
6. **Phát hiện lỗi chất lượng:** phải sửa và kiểm chứng trước khi coi hạng mục là Done.

### 7.2. Điều gì có thể thay đổi?

| Thành phần | Ai chịu trách nhiệm và giới hạn |
| --- | --- |
| **Cách thực hiện / task / trình tự kỹ thuật** | **Developers** tự tổ chức và điều chỉnh; không cần Scrum Master phân công. |
| **Cách phối hợp và hỗ trợ nhau** | Developers quyết định ghép cặp, trao đổi chuyên môn, giảm việc song song, xử lý nút thắt. |
| **Chi tiết phạm vi hạng mục đang thực hiện** | Được làm rõ và thương lượng với **Product Owner** khi nhóm hiểu hơn, miễn không làm nguy hại Sprint Goal. |
| **Thứ tự Product Backlog** | Product Owner chịu trách nhiệm, có trao đổi với Scrum Team và stakeholders. |
| **Sprint Goal** | Không được thay tùy tiện trong Sprint; không thay đổi công việc làm nguy hại mục tiêu. Nếu mục tiêu trở nên lỗi thời, **Product Owner** có quyền hủy Sprint theo Scrum Guide. |
| **Tiêu chuẩn chất lượng** | **Không giảm chất lượng** để giữ số liệu tiến độ. Increment chỉ tính là hoàn thành khi đạt DoD. |

Các thành phần trên giúp phân biệt **thay đổi kế hoạch** với **đổi mục tiêu sản phẩm hoặc phá vỡ ràng buộc chất lượng**. Cần có đúng người chịu trách nhiệm khi một quyết định vượt khỏi phạm vi tự quản của Developers.

### 7.3. Sprint Backlog cần rõ vừa đủ

Không cần cập nhật từng phút làm việc của mỗi thành viên. Hãy ghi những gì giúp đội:

- Biết **điều gì đã đạt** trong luồng giá trị.
- Biết **điều gì vẫn chưa đạt DoD**.
- Phát hiện **việc bị chặn và người/công việc phụ thuộc**.
- Thấy **thứ tự thực hiện tiếp theo** và thay đổi quan trọng đã quyết định.
- Tự điều chỉnh công việc trong Sprint khi xuất hiện thông tin mới.

Một Sprint Backlog chỉ đổi trạng thái thẻ cho đẹp, nhưng không phản ánh phần mềm và rủi ro thật, sẽ **làm giảm tính minh bạch**.

## 8. Khi nào cần thương lượng với Product Owner?

Daily Scrum là sự kiện của Developers, nhưng không có nghĩa Developers phải tự quyết những đánh đổi về **giá trị sản phẩm hoặc phạm vi nghiệp vụ** mà chưa được thống nhất.

**Ví dụ:** trong lúc xây “Bắt đầu học”, nhóm phát hiện có hai nhóm học viên: người học khóa miễn phí và người học khóa có phí. Sprint Goal chỉ nói học viên “đã ghi danh” có thể mở bài đầu. Nếu chính sách cấp quyền với khóa có phí còn mơ hồ, cần hỏi Product Owner để xác nhận ý nghĩa và phạm vi.

Hướng xử lý:

1. Developers nhận diện trường hợp ảnh hưởng Sprint Goal.
2. Ghi **quy tắc chưa rõ và các phương án**: chỉ khóa miễn phí, cả khóa có phí, hoặc một lát giá trị đã được giới hạn rõ.
3. Cùng Product Owner thương lượng phần phạm vi phù hợp với mục tiêu và ràng buộc.
4. Điều chỉnh Sprint Backlog sau khi quyết định; giữ DoD cho phạm vi đã chọn.
5. Kiểm chứng hành vi thật, trình bày minh bạch trong Sprint Review.

Đừng biến Product Owner thành người phê duyệt mọi task kỹ thuật. Ngược lại, đừng tự sửa quy tắc thanh toán, quyền truy cập hoặc chính sách học tập mà không có quyết định nghiệp vụ phù hợp.

### 8.1. Stakeholder đưa yêu cầu mới vào giữa Sprint

Giả sử bộ phận marketing muốn bổ sung trang chứng chỉ mới ngay hôm nay. Nếu yêu cầu đó không hỗ trợ Sprint Goal hiện tại, Developers không nên tự động chuyển sang làm chỉ vì một bên liên quan giao việc trực tiếp.

Cách làm:

- Ghi nhận yêu cầu và lý do, đưa vào trao đổi với Product Owner.
- Làm rõ **giá trị, cấp thiết và chi phí cơ hội**.
- Nếu không cấp bách, cập nhật thứ tự Product Backlog và cân nhắc ở kế hoạch sau.
- Nếu là sự cố nghiêm trọng hoặc nghĩa vụ bắt buộc, ứng phó phù hợp chính sách tổ chức và minh bạch tác động tới Sprint.
- Nếu Sprint Goal đã lỗi thời, Product Owner cân nhắc quyền hủy Sprint; không lấy việc hủy Sprint làm phản ứng mặc định cho mọi thay đổi.

**Thích nghi không phải phục tùng mọi thay đổi ngay lập tức.** Nó là ra quyết định dựa trên thông tin mới trong khi bảo vệ mục tiêu và chất lượng.

## 9. Xử lý trở ngại sau Daily Scrum

Một **trở ngại (impediment)** là yếu tố đang cản Scrum Team tiến tới mục tiêu. Không phải mọi trở ngại đều cần Scrum Master “đến giải quyết thay”; nhiều việc Developers có thể tự phối hợp xử lý.

Một bảng theo dõi ngắn:

| Trở ngại | Tác động tới Sprint Goal | Bước tiếp theo sau Daily Scrum | Ai phối hợp? |
| --- | --- | --- | --- |
| API cấp quyền trả trạng thái sai. | Người đã ghi danh chưa mở được bài đầu. | Tái hiện và sửa trên môi trường tích hợp. | Developers backend và kiểm thử. |
| Môi trường staging thiếu dữ liệu hai tài khoản. | Chưa kiểm thử được tình huống được/không được phép truy cập. | Chuẩn bị dữ liệu thử và quyền cần thiết. | Kiểm thử, vận hành và người sở hữu dữ liệu. |
| Quy tắc quyền cho khóa có phí chưa rõ. | Có thể hiểu sai phạm vi Sprint Goal. | Làm rõ với Product Owner, thống nhất lát cần kiểm chứng. | Developers và Product Owner. |
| Pipeline kiểm thử tích hợp bị gián đoạn bởi quyền hạ tầng. | Không thể xác nhận chất lượng Increment. | Mời người quản lý hệ thống hỗ trợ; nếu kéo dài, nhờ Scrum Master giúp gỡ trở ngại tổ chức. | Developers, vận hành, Scrum Master khi cần. |

### 9.1. Ai cần làm gì?

- **Developers** chịu trách nhiệm chủ động phối hợp tạo Increment, điều chỉnh kế hoạch, xử lý các vấn đề trong khả năng và chia sẻ thông tin cần thiết.
- **Scrum Master** chịu trách nhiệm về hiệu quả Scrum Team, giúp xác định và tháo gỡ trở ngại, hỗ trợ tổ chức xử lý giới hạn mà đội khó tự giải quyết.
- **Product Owner** làm rõ vấn đề giá trị, thứ tự Product Backlog và các quyết định phạm vi cần thiết.
- **Các bên bên ngoài đội** có thể hỗ trợ về chính sách, quyền truy cập, vận hành hoặc chuyên môn nhưng không nên tạo một cơ chế cấp việc làm suy yếu khả năng tự quản của Developers.

### 9.2. Không cần chờ tới Daily Scrum hôm sau

Nếu lỗi nghiêm trọng được phát hiện lúc 14:00, nhóm cần phối hợp ngay theo mức độ ưu tiên và rủi ro. Daily Scrum sáng mai sẽ **kiểm tra kết quả và điều chỉnh tiếp**, không phải “cửa” duy nhất cho phép Developers nói chuyện hay thay đổi kế hoạch.

Scrum Guide nhấn mạnh rằng Developers thường xuyên gặp nhau trong ngày để thảo luận chi tiết hơn và thích nghi công việc còn lại. Tần suất phối hợp cần đủ để phát hiện vấn đề sớm mà không gây gián đoạn không cần thiết.

## 10. Sử dụng bảng công việc và thước đo dòng chảy

Một đội có thể bổ sung các thực hành **Kanban** để làm rõ dòng công việc, chẳng hạn trực quan hóa trạng thái, **giới hạn WIP**, theo dõi tuổi công việc đang làm, cycle time và các điểm nghẽn.

Đây là những **kỹ thuật bổ sung tùy chọn**; Scrum Guide không bắt buộc Daily Scrum phải có một bảng Kanban với các giới hạn WIP cụ thể.

### 10.1. Đi qua bảng theo công việc thay vì theo người

Một cấu trúc hữu ích là **“walk the board”** từ các hạng mục gần hoàn thành tới hạng mục mới:

```text
Chưa bắt đầu  →  Đang làm  →  Đang kiểm chứng  →  Done (đạt DoD)
    S5             S2, S3           S4                S1

Câu hỏi:
- S4 cần điều kiện nào để vào kiểm chứng?
- S2/S3 đang phụ thuộc điều gì?
- Có ai giúp giải quyết để hoàn tất một lát cắt trước khi mở S5?
```

Cách này giúp ưu tiên **hoàn thành và tích hợp** thay vì bắt đầu nhiều việc.

### 10.2. Dùng chỉ số đúng mục đích

| Tín hiệu | Daily Scrum có thể học được gì? | Điều không nên suy ra |
| --- | --- | --- |
| **WIP** | Có quá nhiều hạng mục đang mở gây dàn trải không? | Một con số thấp luôn tốt trong mọi tình huống. |
| **Work item age** | Hạng mục nào đang dở lâu và cần giúp đỡ? | Hạng mục lâu là do một cá nhân lười hoặc yếu. |
| **Cycle time** | Luồng có chậm bất thường ở bước tích hợp, kiểm thử hay không? | Mỗi story phải hoàn thành đúng bằng trung bình. |
| **Throughput** | Nhóm đang hoàn thành bao nhiêu hạng mục theo định nghĩa nhất quán? | Nhiều thẻ Done tự động tương đương giá trị cao. |
| **Lỗi hồi quy và sự cố** | Việc tăng tốc có ảnh hưởng chất lượng không? | Tốc độ quan trọng hơn tiêu chuẩn Done. |

Các chỉ số có ích khi chúng giúp **đưa ra quyết định cải tiến**. Daily Scrum không phải buổi phân tích dữ liệu dài; chỉ cần nhìn tín hiệu quan trọng, sau đó hẹn trao đổi sâu nếu phát hiện vấn đề hệ thống.

## 11. Daily Scrum trong đội từ xa hoặc khác múi giờ

Một đội làm việc từ xa vẫn cần tạo được mục đích của Daily Scrum: Developers có thông tin đủ đáng tin để **cùng kiểm tra Sprint Goal và thích nghi kế hoạch**, không chỉ gửi báo cáo riêng lẻ.

### 11.1. Cách tổ chức thực tế

- Dùng **một khung giờ ổn định trong các ngày làm việc của Sprint** và một phòng trực tuyến cố định khi có thể.
- Cập nhật các hạng mục và trạng thái bị chặn **trước hoặc ngay khi trao đổi**, để 15 phút dành cho quyết định thay vì đọc từng thẻ.
- Đặt Sprint Goal và hạng mục gần Done ở vị trí dễ nhìn.
- Dùng văn bản ngắn để chia sẻ kết luận và người phối hợp sau họp, đặc biệt khi có người cần làm việc khác múi giờ.
- Nếu phát hiện vấn đề cần giải quyết chuyên sâu, chỉ mời người liên quan vào cuộc trao đổi tiếp theo.

### 11.2. Có thể thay bằng báo cáo bất đồng bộ không?

Một bảng cập nhật bất đồng bộ có thể **bổ trợ** Daily Scrum, nhất là khi đội lệch giờ, nhưng không nên tự gọi một chuỗi tin nhắn cá nhân là **Daily Scrum theo Scrum Guide** nếu nó không thực hiện sự kiện 15 phút dành cho Developers vào mỗi ngày làm việc với mục đích kiểm tra và điều chỉnh kế hoạch chung.

Nếu tổ chức quyết định vận hành hoàn toàn bất đồng bộ, họ có thể có một cách làm Agile hữu ích khác, nhưng cần **phân biệt lựa chọn tổ chức với yêu cầu Scrum**. Nếu đang dùng Scrum, ưu tiên thiết kế cách phối hợp để thực hiện đúng sự kiện trong điều kiện đội thực tế.

## 12. Các sai lầm phổ biến và cách khắc phục

### Sai lầm 1 — Daily Scrum biến thành cuộc họp báo cáo cấp trên

**Biểu hiện:** từng người hướng về Scrum Master hoặc quản lý và lần lượt khai báo việc đã làm; các Developers ít trao đổi trực tiếp với nhau.

**Vì sao sai:** Developers không cùng kiểm tra Sprint Goal và điều chỉnh Sprint Backlog; cuộc họp dễ trở thành kiểm soát cá nhân.

**Khắc phục:** để Developers chủ động dẫn dắt, đặt Sprint Goal cạnh Sprint Backlog, hỏi cần phối hợp gì để hoàn thành luồng giá trị.

### Sai lầm 2 — Ba câu hỏi được thực hiện máy móc

**Biểu hiện:** tất cả mọi người lặp lại “hôm qua vẫn làm task A, hôm nay vẫn làm A” mà không chỉ ra phụ thuộc chung.

**Khắc phục:** có thể chuyển sang “hạng mục nào gần Done?”, “điều gì đang chặn mục tiêu?”, “kế hoạch hôm nay nên đổi gì?”. Cách hỏi là tùy chọn; **mục đích Scrum là bắt buộc**.

### Sai lầm 3 — Bắt đầu thêm việc dù công việc dở đang bị chặn

**Biểu hiện:** backend mở ba story mới trong khi kiểm thử tích hợp chưa thể thực hiện vì lỗi của story cũ.

**Khắc phục:** xem dòng giá trị, giới hạn việc đang làm khi cần, hỗ trợ chéo và tập trung giải quyết nguyên nhân chặn. Không phải mọi người đều cần làm cùng một task, nhưng **mục tiêu chung quan trọng hơn việc mỗi người luôn bận**.

### Sai lầm 4 — Mọi vấn đề chuyên sâu đều xử lý ngay trong 15 phút

**Biểu hiện:** một lỗi kỹ thuật kéo cả nhóm vào phân tích log, cuộc họp mất 45 phút và không ai biết kế hoạch chung.

**Khắc phục:** trong Daily Scrum xác nhận mức ảnh hưởng, ai xử lý và điểm xem lại; **khám phá chi tiết diễn ra ngay sau đó** với người cần thiết.

### Sai lầm 5 — Không cập nhật Sprint Backlog sau khi quyết định

**Biểu hiện:** nhóm nói đã đổi thứ tự xử lý nhưng bảng vẫn phản ánh kế hoạch cũ, dẫn tới người khác làm sai việc ưu tiên.

**Khắc phục:** cập nhật kế hoạch, trạng thái và trở ngại tại nơi đội dùng chung. Chỉ ghi thông tin có ích để giữ minh bạch.

### Sai lầm 6 — Giữ task đã chốt dù dữ liệu mới chứng minh sai

**Biểu hiện:** nhóm biết luồng API phải thay để cấp quyền đúng, nhưng vẫn hoàn thành task thiết kế cũ vì đã “commit”.

**Khắc phục:** Developers được **thích nghi kế hoạch kỹ thuật**. Nếu thay đổi ảnh hưởng phạm vi nghiệp vụ, thương lượng với Product Owner; **không làm nguy hại Sprint Goal hoặc giảm chất lượng**.

### Sai lầm 7 — Dùng Daily Scrum để xét hiệu suất cá nhân

**Biểu hiện:** đếm số phút phát biểu, task “đã làm hôm qua”, điểm số hoặc số giờ cá nhân để chấm KPI.

**Khắc phục:** đánh giá Daily Scrum bằng khả năng nhóm **phát hiện vấn đề, tạo kế hoạch khả thi, hoàn thành Increment và học hỏi**, không bằng mức độ “báo cáo chăm chỉ”.

### Sai lầm 8 — Scrum Master phải giải quyết hộ mọi trở ngại

**Biểu hiện:** Developers nhìn thấy lỗi có thể tự xử lý nhưng không chủ động, chỉ chờ Scrum Master “giao việc và gỡ”.

**Khắc phục:** Developers xử lý hoặc phối hợp xử lý những trở ngại trong khả năng. Scrum Master hỗ trợ loại bỏ các cản trở và giúp Scrum Team hiệu quả, đặc biệt khi phụ thuộc nằm ngoài quyền kiểm soát của đội.

### Sai lầm 9 — Đánh dấu Done dù kiểm thử hoặc quyền truy cập chưa đạt

**Biểu hiện:** code đã chạy trên máy cá nhân được tính Done dù luồng tích hợp hoặc kiểm thử bảo mật thất bại.

**Khắc phục:** giữ Definition of Done. Trong Scrum, công việc **chưa đạt DoD không là phần của Increment hoàn thành**. Không giảm chất lượng để đạt số liệu Sprint đẹp.

## 13. Khung thực hành để Developers tự điều chỉnh kế hoạch

Không cần một mẫu phức tạp. Đội có thể dùng khung sau trước và sau mỗi Daily Scrum.

### 13.1. Trước Daily Scrum

- Biết **Sprint Goal** hiện tại.
- Xem hạng mục nào đã thực sự đáp ứng **DoD**.
- Kiểm tra **hạng mục gần Done** và những điểm chặn đang còn.
- Ghi lại **thông tin mới** có thể làm thay đổi kế hoạch.
- Chuẩn bị **đề xuất phối hợp** thay vì chỉ báo trạng thái cá nhân.

### 13.2. Trong Daily Scrum

```text
Sprint Goal: [Kết quả chung cần đạt trong Sprint]

Đã có bằng chứng tiến độ gì?
- [Một Increment, một luồng chạy được, một tiêu chí đã kiểm chứng]

Điều gì đang cản mục tiêu?
- [Hạng mục / phụ thuộc / rủi ro / chất lượng chưa đạt]

Kế hoạch sắp tới cần điều chỉnh gì?
- [Việc cần hoàn tất trước, phối hợp, giảm công việc dở]

Cần làm rõ/nhờ hỗ trợ từ ai?
- [PO / chuyên gia / vận hành / Scrum Master khi thích hợp]

Sau Daily Scrum:
- [Người liên quan, hành động cụ thể, điểm cập nhật]
```

Đây chỉ là **mẫu lựa chọn** giúp cuộc trao đổi đi đến quyết định, không phải biểu mẫu bắt buộc hay tài liệu mới cần tạo mỗi ngày.

### 13.3. Sau Daily Scrum

- Những Developers liên quan **bắt đầu xử lý việc đã thống nhất**, không chờ đến cuộc họp sau.
- Sprint Backlog được **cập nhật nếu kế hoạch thay đổi**.
- Trở ngại vượt quyền đội được **chuyển đúng người phụ trách**.
- Nếu cần làm rõ giá trị/phạm vi, nhóm **trao đổi với Product Owner**.
- Khi đã có bằng chứng mới, **chia sẻ sớm**; không giữ thông tin cho lần Daily Scrum kế tiếp.

## 14. Bài tập tình huống và gợi ý đáp án

### Bài tập A — Từ báo cáo cá nhân sang kế hoạch chung

Sprint Goal: “Học viên ghi danh được khóa miễn phí và mở bài đầu.”

Trong Daily Scrum, các Developers nói:

- A: “Hôm qua tôi tạo bảng đăng ký. Hôm nay tôi tiếp tục với API.”
- B: “Hôm qua tôi làm trang ghi danh. Hôm nay tôi làm tiếp giao diện.”
- C: “Hôm qua tôi chưa có gì để kiểm thử. Hôm nay có lẽ vẫn chưa có.”
- D: “Hôm nay tôi định bắt đầu tính năng đánh giá khóa học.”

**Câu hỏi:**

1. Nhóm đang thiếu thông tin nào để biết tiến độ tới Sprint Goal?
2. Hãy viết **bốn câu hỏi** giúp chuyển cuộc trò chuyện sang mục tiêu chung.
3. Nếu tính năng đánh giá khóa học không hỗ trợ Sprint Goal, nhóm nên cân nhắc gì trước khi bắt đầu?
4. Kết luận Daily Scrum nên dẫn tới **hai hành động phối hợp cụ thể** nào?

**Gợi ý:** hỏi luồng ghi danh đã chạy xuyên suốt chưa, API–UI còn lệch ở đâu, kiểm thử cần điều kiện gì, ai cùng tích hợp và kiểm chứng. Ưu tiên dứt điểm luồng để đạt Sprint Goal trước khi mở công việc mới không cần thiết. Developers tự điều chỉnh kế hoạch; nếu phạm vi thay đổi quan trọng, trao đổi với Product Owner.

### Bài tập B — Phân biệt quyết định của Developers và Product Owner

Giữa Sprint, nhóm phát hiện:

1. Hợp đồng API cần đổi tên một trường để hai phần tích hợp đúng.
2. Quy tắc khóa học có phí chưa xác định thời điểm cấp quyền xem bài.
3. Stakeholder muốn ưu tiên tính năng cấp chứng chỉ thay cho mục tiêu ghi danh đang thực hiện.
4. Kiểm thử phân quyền thất bại ở trường hợp học viên chưa đăng nhập.
5. Một Developer cần ghép cặp với kiểm thử viên để tái hiện lỗi.

Với từng tình huống, hãy cho biết:

- Developers có thể **tự điều chỉnh kế hoạch thực hiện** không?
- Khi nào cần **thương lượng với Product Owner**?
- Điều gì thuộc **chất lượng bắt buộc** thay vì tính năng có thể cắt giảm?
- Việc nào nên đưa ra khỏi cuộc họp 15 phút để thảo luận chuyên sâu?

**Gợi ý:** (1) và (5) thường nằm trong cách thực hiện của Developers; (2) cần làm rõ nghiệp vụ với Product Owner; (3) cần xem Product Goal, Sprint Goal và quyền ưu tiên của Product Owner; (4) phải xử lý/kiểm chứng theo DoD, không bỏ qua để báo Done. Phân tích kỹ thuật dài có thể tổ chức ngay sau Daily Scrum.

### Bài tập C — Thực hành một Daily Scrum 15 phút

Chia nhóm 4–6 người thành các vai Developers, với Sprint Goal và các trạng thái S1–S5 của ví dụ mục 6.

1. Một người chuẩn bị Sprint Backlog ngắn.
2. Một người đưa thêm **trở ngại mới**: môi trường staging lỗi hoặc quy tắc phân quyền mơ hồ.
3. Nhóm có 15 phút để **kiểm tra Sprint Goal và tạo kế hoạch cho ngày tiếp theo**.
4. Ghi các thay đổi vào Sprint Backlog; xác định cuộc trao đổi chuyên sâu sau sự kiện.
5. Người quan sát đánh giá cuộc trao đổi có tập trung vào **Increment và mục tiêu** hay rơi vào báo cáo cá nhân.

**Tiêu chí tự chấm:**

| Tiêu chí | Biểu hiện tốt |
| --- | --- |
| Đúng mục đích | Mọi quyết định đều liên quan tiến độ tới Sprint Goal. |
| Minh bạch | Nhóm nói rõ luồng nào chạy được, phần nào chưa đạt DoD và các trở ngại. |
| Tự quản | Developers tự quyết định cách phối hợp và cập nhật kế hoạch. |
| Thích nghi | Có thay đổi ưu tiên hoặc cách thực hiện khi thông tin mới xuất hiện. |
| Đúng giới hạn | Phân tích sâu được tách sau 15 phút khi cần. |
| Bảo vệ chất lượng | Không đánh dấu Done nếu còn lỗi nghiêm trọng hoặc chưa đạt DoD. |
| Có hành động | Vấn đề quan trọng có bước xử lý cụ thể, không chỉ được nhắc tên. |

### Bài tập D — Điều chỉnh khi mục tiêu bị đe dọa

Một Sprint còn ba ngày. Hai hạng mục đã xong, nhưng API quyền truy cập vẫn có lỗi: người chưa ghi danh có thể mở bài. Một bên liên quan đề xuất “ẩn lỗi đó đi, cứ trình diễn giao diện trước, rồi Sprint sau sửa”.

Hãy giải thích:

1. Có thể coi phần này là Increment đạt DoD không nếu phân quyền là điều kiện chất lượng bắt buộc?
2. Developers nên làm gì ngay hôm nay?
3. Scrum Master có thể hỗ trợ thế nào mà không phân công task thay đội?
4. Product Owner cần biết điều gì về mục tiêu và rủi ro?
5. Nếu không đạt Sprint Goal, nhóm cần minh bạch và học hỏi thế nào trong Sprint Review và Sprint Retrospective?

**Định hướng:** không đánh dấu Increment đạt DoD khi kiểm soát quyền truy cập cần thiết chưa đạt. Developers cùng ưu tiên sửa, kiểm thử và rà soát rủi ro; Product Owner cùng nhóm hiểu giá trị/phạm vi; Scrum Master hỗ trợ tháo gỡ cản trở. Sprint Review kiểm tra kết quả thực, Retrospective giúp cải thiện cách phát hiện và phòng ngừa lỗi muộn.

## 15. Tổng kết

- **Daily Scrum là sự kiện 15 phút dành cho Developers**, diễn ra mỗi ngày làm việc của Sprint, tập trung **kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog**.
- **Không có quy định bắt buộc phải trả lời ba câu hỏi**, phân công theo từng người hay báo cáo cho Scrum Master. Developers chọn cấu trúc phù hợp với mục đích sự kiện.
- **Sprint Backlog là kế hoạch sống do Developers lập**: gồm Sprint Goal, những Product Backlog Items được chọn và kế hoạch thực hiện; được cập nhật khi nhóm học thêm.
- **Tự quản** nghĩa là Developers chủ động quyết định ai làm gì, khi nào và như thế nào trong phạm vi trách nhiệm, đồng thời phối hợp với Product Owner khi thay đổi liên quan giá trị và phạm vi.
- **Sprint Goal và Definition of Done không phải những thứ có thể hy sinh** chỉ để giữ task hay tốc độ bề ngoài.
- Công việc phân tích lỗi, ghép cặp và xử lý trở ngại có thể diễn ra **ngay sau Daily Scrum hoặc bất kỳ lúc nào cần**, không phải chờ cuộc họp hôm sau.
- Bảng Kanban, WIP, cycle time, ba câu hỏi truyền thống hay mẫu ghi chú là **thực hành bổ sung có thể lựa chọn**; thước đo cuối cùng là khả năng tạo Increment hữu dụng và thích nghi với thông tin mới.

Khi Daily Scrum kết thúc, hãy hỏi: **“Nếu không tổ chức sự kiện này, kế hoạch và cách phối hợp hôm nay có khác đi không?”** Nếu câu trả lời luôn là “không”, nhóm nên xem lại cách kiểm tra tiến độ và đưa ra quyết định — không chỉ xem lại lịch họp.

## Nguồn tham khảo

- [The Scrum Guide — Scrum Guide 2020](https://scrumguides.org/scrum-guide.html) — nguồn chính thức về Daily Scrum, Developers, Sprint Goal, Sprint Backlog, điều chỉnh kế hoạch và Definition of Done.
- [Scrum Guides](https://scrumguides.org/) — các bản hướng dẫn và bản dịch chính thức để đối chiếu thuật ngữ.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — nhấn mạnh tương tác, phần mềm hoạt động được và phản ứng với thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — cộng tác, trao đổi thường xuyên, kỹ thuật tốt và cải tiến liên tục.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/) — tham khảo cách quản lý WIP và đo dòng công việc khi đội lựa chọn thực hành bổ sung.
