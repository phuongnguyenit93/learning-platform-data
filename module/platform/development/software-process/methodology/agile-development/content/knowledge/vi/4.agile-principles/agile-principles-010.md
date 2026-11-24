# Đơn giản hóa bằng cách giảm công việc không cần thiết

Một nhóm phát triển phần mềm có thể làm việc chăm chỉ, hoàn tất nhiều tính năng đúng hạn và vẫn tạo ra ít giá trị. Chẳng hạn, nhóm xây một trang quản trị với hàng chục biểu đồ trong khi người vận hành chỉ cần biết đơn hàng nào đang chậm xử lý. Số lượng công việc hoàn thành lớn, nhưng phần lớn kết quả không giúp người dùng ra quyết định tốt hơn.

Nguyên tắc thứ mười trong mười hai nguyên tắc của Agile Manifesto đặt ra một câu hỏi ngược lại với thói quen “làm được càng nhiều càng tốt”:

> **Sự đơn giản — nghệ thuật tối đa hóa lượng công việc không cần làm — là điều thiết yếu.**

Tinh thần này không phải là lười biếng, giao sản phẩm sơ sài hay bỏ qua kỹ thuật quan trọng. Đó là **chủ động xác định điều không cần xây, không cần duy trì hoặc chưa cần thực hiện**, để dành thời gian và năng lực cho kết quả thực sự quan trọng.

Bài học thuộc chương **Nguyên tắc Agile** của module **AGILE_DEVELOPMENT**. Trong bối cảnh phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục, đơn giản hóa là một cách giảm thời gian từ ý tưởng tới phản hồi. Các thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc sẽ giúp biến nguyên tắc này thành quyết định cụ thể.

Sau bài này, bạn có thể:

- Giải thích chính xác “tối đa hóa công việc không cần làm” và phân biệt nó với cắt giảm chất lượng.
- Nhận diện những công việc không tạo giá trị hoặc chưa có đủ bằng chứng để thực hiện.
- Dùng mục tiêu sản phẩm, user story, backlog và phản hồi để quyết định **làm gì, chưa làm gì, không làm gì**.
- Vận dụng chia nhỏ công việc theo giá trị, giới hạn WIP, thiết kế đơn giản và refactoring.
- Đánh giá kết quả đơn giản hóa bằng các chỉ số về người dùng, chất lượng và luồng công việc.

## 1. “Đơn giản” trong Agile thực sự có nghĩa gì?

Trong Agile, **đơn giản** trước hết là giảm sự phức tạp và nỗ lực *không cần thiết để đạt mục tiêu*, cả ở sản phẩm lẫn cách làm việc. Đơn giản không nhất thiết đồng nghĩa với giao diện ít nút, hệ thống ít dòng code hoặc số lượng người tham gia ít hơn.

Hãy so sánh hai cách giải quyết nhu cầu “người quản lý cần biết đơn hàng nào sắp trễ”:

| Phương án | Công việc nhóm dự kiến làm | Mức phù hợp với nhu cầu ban đầu |
| --- | --- | --- |
| A: Xây bộ phân tích toàn diện | Kho dữ liệu mới, bộ lọc đa chiều, 20 biểu đồ, xuất nhiều định dạng, cấu hình cá nhân hóa. | Có thể hữu ích về sau, nhưng nhiều tính năng chưa có bằng chứng cần thiết. |
| B: Hiển thị danh sách đơn sắp trễ | Quy tắc xác định trễ, danh sách ưu tiên, đường dẫn tới đơn hàng; kiểm tra với người vận hành. | Có khả năng kiểm chứng nhu cầu cốt lõi nhanh hơn với phạm vi hẹp hơn. |

Không thể kết luận B luôn tốt hơn A. Nếu nhóm phụ trách điều hành đa quốc gia cần phân tích xu hướng phục vụ quyết định lớn, phương án A có thể phù hợp. **Điều cần hỏi là: “Bài toán hiện tại có thật sự cần từng phần việc này không?”**

### Ba kiểu công việc cần phân biệt

1. **Công việc cần làm ngay:** tạo giá trị trực tiếp cho mục tiêu hiện tại, kiểm soát rủi ro cần thiết hoặc tạo khả năng triển khai an toàn.
2. **Công việc có thể trì hoãn:** có giá trị tiềm năng nhưng chưa có bằng chứng, chưa cấp bách hoặc còn phụ thuộc vào điều cần học trước.
3. **Công việc có thể bỏ:** trùng lặp, không phục vụ mục tiêu, phức tạp hơn mức cần thiết hoặc đã được thay thế bằng cách giải quyết đơn giản hơn.

Chữ **“chưa”** rất quan trọng: trì hoãn quyết định khi chưa có bằng chứng có thể là lựa chọn tốt, miễn là nhóm xác định cách kiểm chứng và thời điểm xem lại.

### Đơn giản hóa không đồng nghĩa cắt bỏ điều kiện hoàn thành

Một bản phát hành nhỏ vẫn phải đáp ứng các yêu cầu cần thiết về tính đúng đắn, bảo mật, quyền riêng tư, khả năng truy cập, vận hành và quy định có liên quan. Bỏ kiểm thử, bỏ xử lý lỗi quan trọng hoặc giấu khiếm khuyết để “giao nhanh” tạo ra công việc sửa chữa về sau.

Có thể nhớ bằng công thức tư duy:

> **Phạm vi tối thiểu cần thiết + chất lượng đủ để sử dụng an toàn + khả năng kiểm chứng kết quả = một phần gia tăng có ý nghĩa.**

Đây là nguyên tắc suy nghĩ, không phải công thức tính định lượng.

## 2. Vì sao làm ít việc hơn có thể mang lại nhiều giá trị hơn?

Năng lực của một nhóm luôn hữu hạn: thời gian phát triển, năng lực xem xét code, kiểm thử, hạ tầng và sự chú ý của người liên quan đều có giới hạn. Mỗi việc được thêm vào tiêu tốn nguồn lực và tạo cơ hội bỏ lỡ việc khác.

### 2.1. Giảm thời gian tới phản hồi

Một tính năng lớn mất nhiều tuần thường kéo dài thời gian nhóm chờ để biết giải pháp có đúng không. Nếu chia thành phần nhỏ có thể sử dụng và kiểm chứng sớm, nhóm sẽ nhận thông tin để sửa hướng trước khi đầu tư sâu.

Ví dụ, trước khi xây bộ gợi ý khóa học dùng mô hình phức tạp, nhóm có thể thử danh sách gợi ý dựa trên chủ đề người học chọn. Nếu người dùng không sử dụng gợi ý vì họ khó tìm nơi xem đề xuất, việc đầu tư thuật toán trước khi hiểu hành vi có thể bị lãng phí.

### 2.2. Giảm chi phí sở hữu dài hạn

Mỗi tính năng thêm vào thường mang theo công việc sau khi phát hành:

- Cần kiểm thử khi hệ thống thay đổi.
- Có thể phát sinh lỗi và yêu cầu hỗ trợ.
- Cần giám sát, cập nhật, xử lý bảo mật và tương thích.
- Tăng số nhánh xử lý khiến người dùng và người bảo trì khó hiểu hơn.

Vì vậy, **không xây một tính năng chưa cần** tiết kiệm cả công xây dựng lẫn công duy trì. Tuy nhiên, không nên vì sợ bảo trì mà loại bỏ khả năng thiết yếu đã được xác nhận.

### 2.3. Giảm số việc đang làm dở

Khi nhóm mở quá nhiều công việc cùng lúc, mỗi công việc có thể phải chờ thiết kế, review, kiểm thử hoặc tích hợp. Thời gian hoàn thành kéo dài mặc dù mọi người đều “bận”. Hạn chế công việc đang thực hiện (*work in progress*, WIP) giúp nhóm tập trung hoàn tất một số ít phần có giá trị trước khi nhận thêm.

### 2.4. Dành thời gian cho việc quan trọng nhưng ít hiện diện trên màn hình

Một backlog đầy tính năng có thể che lấp những công việc nền tảng như sửa lỗi gây mất dữ liệu, cải thiện thời gian khôi phục sự cố hoặc giảm thời gian triển khai. Đơn giản hóa giúp nhóm có không gian thực hiện **đúng việc cần thiết**, bao gồm việc chất lượng kỹ thuật có thể không hiện rõ như tính năng mới.

## 3. Chu trình nhận diện và giảm công việc không cần thiết

Một nhóm không thể biết ngay từ đầu toàn bộ công việc nào “không cần”. Quyết định tốt thường hình thành qua các vòng học ngắn:

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và kết quả mong đợi"] --> B["Liệt kê giả định, nhu cầu và ràng buộc"]
    B --> C{"Phần việc này cần ngay?"}
    C -->|"Có bằng chứng hoặc bắt buộc"| D["Chọn lát cắt nhỏ nhất có thể kiểm chứng"]
    C -->|"Chưa rõ"| E["Thu thập thêm bằng chứng với chi phí phù hợp"]
    C -->|"Không tạo giá trị"| F["Bỏ khỏi phạm vi dự kiến"]
    D --> G["Xây dựng, kiểm thử và giao phần gia tăng"]
    E --> B
    G --> H["Quan sát người dùng, kỹ thuật và luồng công việc"]
    H --> I{"Giả định có được xác nhận?"}
    I -->|"Có"| J["Quyết định mở rộng khi cần"]
    I -->|"Không"| K["Điều chỉnh, thay thế hoặc dừng"]
    J --> A
    K --> A
~~~

Ở đây, **cắt giảm phạm vi** là một quyết định có chủ đích, dựa trên mục tiêu hoặc bằng chứng. Nhóm vẫn cần quay lại quan sát kết quả: có thể công việc tưởng như không cần thực ra lại quyết định trải nghiệm của người dùng.

### Câu hỏi trước khi thêm một mục vào backlog

- **Ai cần kết quả này?** Người dùng, bộ phận vận hành hay một yêu cầu bắt buộc cụ thể?
- **Vấn đề hiện tại là gì?** Có quan sát hay dữ liệu nào xác nhận?
- **Giá trị mong đợi là gì?** Người dùng sẽ làm được điều gì tốt hơn?
- **Điều gì xảy ra nếu không làm trong giai đoạn này?** Mất giá trị, tăng rủi ro hay không có tác động rõ?
- **Có cách nhỏ hơn để đạt cùng kết quả không?** Có thể thay thao tác thủ công được kiểm soát bằng một chức năng tự động phức tạp trong giai đoạn đầu không?
- **Làm sao biết đã đủ?** Điều kiện chấp nhận và cách nhận phản hồi là gì?

Những câu hỏi này không thay thế việc xác định ưu tiên có trách nhiệm. Chúng làm rõ cơ sở để người có trách nhiệm sản phẩm và nhóm kỹ thuật cùng quyết định.

## 4. Xác định giá trị trước khi chọn giải pháp

Tình huống điển hình: một bên liên quan đề nghị **“thêm chức năng xuất Excel có 15 bộ lọc”**. Nếu nhóm bắt đầu bằng việc ước lượng đủ 15 bộ lọc, họ đã mặc nhiên chấp nhận giải pháp được đề xuất.

Thay vào đó, có thể hỏi:

- Người dùng cần làm quyết định nào sau khi xuất dữ liệu?
- Họ đang thao tác trên dữ liệu nào, tần suất ra sao?
- Một bảng tóm tắt trên màn hình hoặc một tệp xuất với ba cột quan trọng có đủ không?
- Có yêu cầu bắt buộc nào về định dạng, phân quyền hay lưu vết không?

**Nhu cầu (problem/outcome)** là điều cần giải quyết. **Giải pháp (solution)** là một giả thuyết về cách đáp ứng nhu cầu. Phân biệt hai tầng này mở ra khả năng giảm lượng việc cần làm.

### Dùng user story để gắn phạm vi với mục tiêu

Ví dụ:

> Là người phụ trách hỗ trợ học viên, tôi muốn xem danh sách người chưa hoàn thành bài học đến hạn, để chủ động nhắc đúng người cần hỗ trợ.

Story thể hiện người hưởng lợi và kết quả, chưa khóa nhóm vào việc phải xây thêm một công cụ báo cáo tổng quát. Sau trao đổi, nhóm có thể chọn phiên bản đầu tiên chỉ gồm danh sách học viên trễ hạn, bộ lọc theo khóa học và thao tác liên hệ.

**Tiêu chí chấp nhận có thể kiểm chứng:**

~~~gherkin
Feature: Xem học viên chưa hoàn thành bài đến hạn

Scenario: Liệt kê học viên cần hỗ trợ
  Given người phụ trách có quyền xem một khóa học
  And khóa học có bài học đã quá hạn
  When người phụ trách mở danh sách chưa hoàn thành
  Then hệ thống hiển thị học viên thuộc khóa học đó chưa hoàn thành bài đến hạn
  And mỗi dòng thể hiện tên học viên, bài học và hạn hoàn thành

Scenario: Không có học viên quá hạn
  Given tất cả học viên của khóa học đã hoàn thành bài đúng hạn
  When người phụ trách mở danh sách chưa hoàn thành
  Then hệ thống hiển thị trạng thái không có học viên quá hạn
~~~

Bộ lọc nâng cao, biểu đồ dự báo rủi ro và báo cáo tổng hợp đa khóa học có thể **để trong backlog chờ thêm bằng chứng**. Nếu phản hồi cho thấy danh sách cơ bản chưa đủ để hỗ trợ học viên, nhóm sẽ bổ sung đúng phần còn thiếu.

## 5. Những kỹ thuật đơn giản hóa thường dùng

### 5.1. Chia nhỏ theo giá trị có thể kiểm chứng

“Chia nhỏ” không chỉ là phân tách nhiệm vụ kỹ thuật như tạo API, viết giao diện, dựng cơ sở dữ liệu. Nếu mỗi phần đơn lẻ không đem lại khả năng sử dụng, nhóm vẫn phải chờ tích hợp toàn bộ mới có phản hồi từ người dùng.

Nên ưu tiên **lát cắt dọc (vertical slice)** có đủ phần cần thiết từ giao diện đến xử lý và lưu trữ để tạo ra một hành vi hoàn chỉnh, dù phạm vi nhỏ.

Ví dụ với tính năng đặt lịch:

| Cách phân chia | Kết quả sau một phần | Khả năng kiểm chứng |
| --- | --- | --- |
| Theo lớp kỹ thuật: toàn bộ database, rồi toàn bộ API, rồi toàn bộ UI | Các thành phần còn rời nhau. | Chủ yếu kiểm tra kỹ thuật từng lớp. |
| Theo lát cắt giá trị: xem giờ trống → đặt một lịch → nhận xác nhận | Mỗi lần có thêm một hành vi người dùng khả dụng. | Có thể đánh giá luồng đặt lịch sớm hơn. |

Không phải thành phần kỹ thuật nào cũng cần giao riêng cho người dùng. Có thể có công việc nền tảng cần thiết; vấn đề là lập kế hoạch sao cho giá trị được kiểm chứng thường xuyên, tránh tích lũy quá nhiều thứ chưa tích hợp.

### 5.2. Tránh xây trước khả năng chưa có nhu cầu

Trong thiết kế phần mềm, nguyên tắc **YAGNI** (*You Aren't Gonna Need It*, tạm hiểu “đừng xây điều chưa thực sự cần”) nhắc nhóm tránh đầu tư vào khả năng chỉ *có thể* được dùng trong tương lai.

Ví dụ: hệ thống hiện chỉ xử lý một loại giảm giá theo phần trăm. Chưa có bằng chứng cần mười quy tắc kết hợp, thứ tự ưu tiên phức tạp hoặc ngôn ngữ cấu hình riêng. Một thiết kế giải quyết tốt yêu cầu hiện tại, có kiểm thử rõ, có thể dễ mở rộng khi cần hơn là xây sẵn bộ máy quy tắc tổng quát chưa được dùng.

Nhưng YAGNI không phải lý do bỏ thiết kế cơ bản. Nếu nhu cầu bảo mật, tính nhất quán dữ liệu, tải thực tế hoặc yêu cầu pháp lý đã biết, chúng là nhu cầu **hiện tại**, không phải “có thể sau này”.

### 5.3. Giữ backlog gọn và có thể thay đổi

Backlog không phải danh sách cam kết xây mọi ý tưởng từng được nêu. Nó là công cụ làm rõ, sắp thứ tự và quản lý các lựa chọn sản phẩm.

Khi xem lại backlog, nhóm có thể:

1. Loại hoặc lưu trữ mục trùng lặp, không còn phù hợp.
2. Gộp các yêu cầu thể hiện cùng một vấn đề.
3. Phân tách mục quá lớn thành phần có giá trị độc lập.
4. Trì hoãn việc phân tích chi tiết các mục chưa gần thời điểm thực hiện.
5. Làm rõ phụ thuộc và yêu cầu bắt buộc đối với những mục ưu tiên cao.
6. Dừng hướng giải pháp không còn được bằng chứng ủng hộ.

**Làm rõ theo nhu cầu gần (just-in-time refinement)** giúp tránh đầu tư nhiều giờ mô tả và ước lượng một tính năng có thể bị loại khi mục tiêu thay đổi. Tuy nhiên, yêu cầu có rủi ro cao hoặc phụ thuộc lớn vẫn cần được nghiên cứu đủ sớm.

### 5.4. Giới hạn WIP và hoàn tất trước khi bắt đầu thêm

Giả sử một nhóm có tám công việc “Đang phát triển”, năm công việc “Chờ review” và chỉ một công việc hoàn tất. Thêm hai story mới làm số thẻ đang chạy tăng, nhưng chưa tạo thêm giá trị cho người dùng.

Kanban giúp nhóm nhìn thấy các hàng chờ. Một thử nghiệm hợp lý có thể là: **không kéo thêm việc mới khi cột review đạt giới hạn đã thỏa thuận; người có năng lực phù hợp hỗ trợ xử lý các mục đang chờ**.

Giới hạn WIP phải phù hợp thực tế nhóm, không phải con số áp dụng giống nhau ở mọi nơi. Nếu giới hạn khiến công việc có rủi ro hoặc khẩn cấp bị xử lý chậm bất hợp lý, nhóm cần có chính sách xử lý ngoại lệ minh bạch.

### 5.5. Giảm thủ tục và bàn giao không tạo giá trị

Mỗi lần chuyển giao, chờ phê duyệt hoặc nhập lại dữ liệu có thể làm kéo dài lead time. Nên xem xét:

- Có thể đưa người cần quyết định vào cuộc trao đổi sớm thay vì gửi qua nhiều cấp không?
- Có hai hệ thống đang yêu cầu nhập cùng một thông tin không?
- Báo cáo nào có người sử dụng và hành động cụ thể sau khi đọc?
- Buổi họp nào có thể rút ngắn hoặc thay bằng cập nhật bất đồng bộ?

Không xóa các điểm kiểm soát cần cho bảo mật, tài chính, quản trị thay đổi hoặc tuân thủ. Đơn giản hóa quy trình là **giữ kiểm soát có ích bằng cách làm ít gây trì hoãn hơn**.

### 5.6. Duy trì code đơn giản bằng kiểm thử và refactoring

Trong XP, **simple design** và **refactoring** giúp thiết kế đáp ứng đúng yêu cầu hiện tại mà vẫn có khả năng thay đổi. Tích hợp liên tục, kiểm thử tự động phù hợp và review code là cơ chế tạo phản hồi nhanh, tránh chất lượng suy giảm sau mỗi lần sửa.

Ví dụ, hai chức năng có xử lý gần giống nhau xuất hiện. Nhóm chưa nhất thiết phải tạo một framework khổng lồ để “phòng khả năng có 20 chức năng tương tự”. Có thể giữ giải pháp rõ ràng, bổ sung kiểm thử hành vi và trích xuất thành phần dùng chung khi sự trùng lặp đã đủ rõ.

**Đơn giản hóa thiết kế** không đồng nghĩa với “ít lớp nhất” hoặc “ít dòng code nhất”. Một hàm dài khó hiểu có thể có ít dòng code hơn nhiều hàm nhỏ nhưng khó thay đổi hơn. Thước đo hữu ích là tính đúng đắn, khả năng hiểu, mức độ rủi ro và chi phí thay đổi.

## 6. Tình huống thực tế: nền tảng học trực tuyến cần tăng tỉ lệ hoàn thành

Một nhóm phát triển nền tảng học tập nhận mục tiêu: **giúp nhiều người học hoàn thành khóa học đã đăng ký hơn**. Trong cuộc họp, các ý tưởng được đưa ra gồm:

1. Tạo hệ thống điểm thưởng.
2. Làm bảng xếp hạng người học.
3. Gửi email nhắc học.
4. Xây bộ đề xuất bài tiếp theo bằng AI.
5. Tạo bảng theo dõi tiến độ theo khóa học.
6. Cho phép học viên mở lại bài tại vị trí đang xem.
7. Xây giao diện quản trị tùy biến cho mọi vai trò.

Nếu triển khai tất cả cùng lúc, nhóm sẽ tiêu tốn nhiều tháng mà vẫn chưa biết ý tưởng nào giải quyết đúng nguyên nhân bỏ dở.

### Bước 1 — Tìm hiểu trở ngại thực tế

Nhóm xem dữ liệu sản phẩm và phỏng vấn một nhóm người học. Giả sử trong tình huống minh họa:

- Nhiều người thoát giữa video và phải dò lại vị trí khi quay lại.
- Một số người không biết mình đã hoàn thành được bao nhiêu phần.
- Chưa có bằng chứng đáng tin cậy rằng bảng xếp hạng sẽ giúp họ tiếp tục học.

Nhóm không coi đây là sự thật áp dụng cho mọi nền tảng; dữ liệu chỉ dẫn tới **giả thuyết ưu tiên kiểm chứng** trong sản phẩm cụ thể.

### Bước 2 — Lọc phạm vi theo vấn đề và mức độ cấp thiết

| Ý tưởng | Quyết định ban đầu | Lý do |
| --- | --- | --- |
| Tiếp tục xem video tại vị trí đã lưu | **Làm trước** | Có tín hiệu thực tế về trở ngại; thử nghiệm tương đối trực tiếp. |
| Thanh tiến độ khóa học rõ ràng | **Làm ở lát cắt kế tiếp nếu cần** | Phù hợp vấn đề quan sát nhưng vẫn cần kiểm chứng giá trị. |
| Email nhắc học | **Thử với nhóm phù hợp** | Có tiềm năng, cần xem sự đồng ý nhận thông báo và khả năng gây phiền. |
| Điểm thưởng, bảng xếp hạng | **Chưa làm** | Chưa rõ có giải quyết nguyên nhân bỏ dở không; có thể gây động lực sai. |
| Gợi ý bằng AI | **Chưa làm** | Phạm vi và chi phí lớn, chưa có bằng chứng là điểm nghẽn chính. |
| Quản trị tùy biến toàn diện | **Không thuộc phạm vi mục tiêu hiện tại** | Chưa trực tiếp hỗ trợ việc hoàn thành khóa học. |

Quyết định “chưa làm” ở đây **không phải bác bỏ vĩnh viễn**. Nếu sau đó dữ liệu chỉ ra vấn đề mới, nhóm có thể xem xét lại.

### Bước 3 — Giao phần nhỏ nhưng hoàn chỉnh

Nhóm viết một user story:

> Là người học, tôi muốn tiếp tục video từ vị trí gần nhất đã xem, để không phải mất thời gian tìm lại nội dung khi quay lại.

Lát cắt đầu tiên có thể hỗ trợ một thiết bị, trạng thái đã đăng nhập và trường hợp có kết nối mạng. Các điều kiện về quyền truy cập, dữ liệu tiến độ và trải nghiệm khi không có tiến độ lưu phải được xác định rõ. Khả năng đồng bộ nhiều thiết bị có thể làm sau nếu phản hồi cho thấy nhu cầu đủ lớn.

### Bước 4 — Quan sát kết quả

Thay vì báo cáo “đã hoàn thành một tính năng”, nhóm theo dõi:

- Tỉ lệ người quay lại video và tiếp tục học.
- Tỉ lệ hoàn thành bài/khóa học trong nhóm được trải nghiệm.
- Sự cố lưu tiến độ và phản ánh người dùng.
- Cycle time của lát cắt và lượng việc phát sinh sau khi phát hành.

Nếu tỉ lệ quay lại tốt hơn nhưng tỉ lệ hoàn thành không cải thiện, nhóm cần điều tra thêm về độ khó nội dung, lịch học hoặc chất lượng trải nghiệm. **Đơn giản hóa giúp thử nhanh hơn; phản hồi mới quyết định có nên tiếp tục mở rộng hay không.**

### Điều gì được “không làm” trong ví dụ?

Nhóm tạm thời **không xây** hệ thống điểm, bảng xếp hạng, thuật toán AI và giao diện quản trị phức tạp; cũng **không phân tích chi tiết** toàn bộ các tính năng này. Năng lực được tiết kiệm có thể dành cho xác minh giả thuyết, sửa lỗi và cải thiện trải nghiệm có tác động trực tiếp.

Đây là ví dụ minh họa cách ra quyết định; số liệu cụ thể của một tổ chức cần được thu thập thực tế trước khi kết luận.

## 7. Scrum, Kanban và XP hiện thực hóa nguyên tắc này như thế nào?

Agile là hệ giá trị và nguyên tắc; các phương pháp cung cấp những thực hành khác nhau. Không phương pháp nào tự động tạo ra sự đơn giản nếu nhóm vẫn xem số lượng đầu việc hoặc nghi thức là mục tiêu cuối cùng.

| Cách thực hành | Cơ chế giúp giảm công việc không cần thiết | Cạm bẫy cần tránh |
| --- | --- | --- |
| **Scrum** | Product Goal và Sprint Goal định hướng giá trị; Product Backlog được sắp thứ tự; Sprint Review tạo phản hồi để điều chỉnh hướng đi. | Nhồi Sprint với càng nhiều story càng tốt dù không phục vụ mục tiêu; coi mọi yêu cầu mới đều phải thêm ngay. |
| **Kanban** | Trực quan hóa dòng công việc, giới hạn WIP, nhìn nút thắt và đo thời gian hoàn tất. | Chỉ dịch chuyển thẻ để tăng throughput mà không quan tâm chất lượng hoặc giá trị mỗi mục. |
| **XP** | Simple design, TDD, refactoring, CI và phản hồi kỹ thuật thường xuyên giúp tránh thiết kế thừa và giảm chi phí thay đổi. | Hiểu “simple design” thành bỏ kiểm thử hoặc trì hoãn sửa cấu trúc code cần thiết. |

### Trong Scrum: bảo vệ mục tiêu khỏi phạm vi thừa

Ở **Sprint Planning**, Scrum Team làm rõ Sprint Goal, rồi Developers lựa chọn công việc phù hợp để hướng tới mục tiêu đó. Một yêu cầu mới xuất hiện giữa Sprint không đương nhiên phải được thêm vào. Những bên chịu trách nhiệm có thể trao đổi về tác động và điều chỉnh Sprint Backlog trong khi giữ định hướng Sprint Goal.

Ở **Sprint Review**, nhóm xem phần gia tăng đã tạo ra và phản hồi của các bên liên quan. Đây là cơ hội quyết định một ý tưởng từng được ưu tiên nay không còn cần thiết. Ở **Sprint Retrospective**, nhóm cũng có thể nhận diện thủ tục, chuyển giao hoặc cuộc họp gây lãng phí.

### Trong Kanban: bớt khởi động, tăng hoàn tất

Một bảng Kanban minh bạch giúp nhóm thấy hàng đợi, công việc đang dở và các bước bị nghẽn. Khi review code là nút thắt, giải pháp có thể là hỗ trợ review trước khi kéo thêm việc mới, chứ không phải bổ sung hàng loạt story vào “Đang phát triển”.

Các chính sách luồng như giới hạn WIP, điều kiện kéo việc và cách xử lý việc khẩn cần được nhóm thống nhất, công khai và cải tiến khi có dữ liệu mới.

### Trong XP: chỉ xây cấu trúc đủ dùng ở hiện tại

XP khuyến khích thiết kế đủ đơn giản để đáp ứng yêu cầu và thay đổi khi có bằng chứng mới. TDD tạo các ví dụ hành vi có thể chạy; CI sớm cho biết thay đổi có phá vỡ chức năng cũ không; refactoring giảm độ phức tạp tích tụ. Nhờ đó, nhóm có thể tránh cả hai cực đoan: **thiết kế trước cho mọi khả năng tưởng tượng** và **viết code khó sửa chỉ để giao sớm**.

## 8. Đo lường để biết việc đơn giản hóa có hiệu quả

Không nên đo sự đơn giản bằng số ticket bị xóa, số dòng code ít hơn hoặc số cuộc họp bị hủy. Một quyết định cắt phạm vi chỉ có ý nghĩa nếu **giá trị cần thiết vẫn được cung cấp và chất lượng được duy trì**.

### 8.1. Đo kết quả sản phẩm

Tùy mục tiêu, nhóm có thể theo dõi:

- **Tỉ lệ hoàn tất tác vụ:** bao nhiêu người thực hiện được hành động mục tiêu, ví dụ hoàn tất đặt lịch hoặc tiếp tục bài học.
- **Thời gian đạt mục tiêu:** từ lúc bắt đầu đến khi người dùng hoàn thành tác vụ.
- **Mức độ sử dụng tính năng:** những chức năng được xây có đang giải quyết nhu cầu thật không.
- **Phản hồi định tính:** người dùng gặp trở ngại nào, điều gì chưa đáp ứng nhu cầu.

Một tính năng ít được sử dụng không tự động là “vô ích”: chức năng khôi phục dữ liệu hoặc điều khiển sự cố có thể rất quan trọng dù hiếm sử dụng. Cần xét **mục đích và rủi ro**, không chỉ tần suất truy cập.

### 8.2. Đo dòng công việc

| Chỉ số | Cách diễn giải | Dấu hiệu cần tìm hiểu |
| --- | --- | --- |
| **Lead time** | Thời gian từ khi ghi nhận yêu cầu tới khi hoàn tất, theo mốc thống nhất của nhóm. | Công việc đang chờ ưu tiên, quyết định, phụ thuộc hay phê duyệt quá lâu? |
| **Cycle time** | Thời gian từ khi bắt đầu thực hiện tới khi hoàn tất. | Mục có quá lớn, có nhiều lần bàn giao hoặc bị tắc ở bước nào? |
| **Throughput** | Số mục hoàn tất trong một khoảng thời gian. | Mức tăng có do các mục nhỏ hơn hay do bỏ sót tiêu chuẩn hoàn tất? |
| **WIP** | Số mục đã bắt đầu nhưng chưa hoàn thành. | Nhóm có khởi động nhiều việc hơn khả năng xử lý không? |
| **Work item age** | Thời gian đã trôi qua của một mục vẫn đang mở. | Có mục nào đang già đi và có nguy cơ kéo dài bất thường không? |

Các thước đo này cho biết **năng lực giao hàng và dòng chảy**, nhưng không trực tiếp chứng minh giá trị với người dùng. Nếu cycle time giảm trong khi số lỗi production tăng, nhóm cần xem lại việc đánh đổi chất lượng.

### 8.3. Đo chất lượng và năng lực thay đổi

- Số lỗi ảnh hưởng người dùng sau phát hành; mức nghiêm trọng và xu hướng.
- Thời gian khôi phục khi có sự cố, nếu phù hợp với sản phẩm.
- Thời gian từ phát hiện vấn đề đến khi có phần cải tiến được kiểm chứng.
- Lượng công việc sửa lại do hiểu sai yêu cầu.
- Phản hồi của nhóm về việc thay đổi tính năng có khó hơn theo thời gian không.

**Ví dụ diễn giải thận trọng:** Sau khi chia một tính năng thành ba lát cắt nhỏ, median cycle time giảm từ 12 ngày xuống 5 ngày; tỷ lệ lỗi nghiêm trọng giữ ổn định. Đây là tín hiệu tích cực, nhưng chưa đủ chứng minh rằng chia nhỏ là nguyên nhân duy nhất. Cần xem kích thước mục, sự thay đổi nhân sự, thời gian quan sát và các điều kiện liên quan.

## 9. Những giới hạn và đánh đổi cần nhận diện

### 9.1. “Đơn giản nhất” phải xét toàn bộ chi phí

Một đoạn code ngắn có thể khó hiểu, khó kiểm thử và gây lỗi về sau. Một bước phê duyệt có thể làm tăng thời gian nhưng giúp tránh rủi ro an toàn lớn. Hãy xem **chi phí vòng đời**, không chỉ công sức viết tính năng ban đầu.

### 9.2. Không đánh đổi bảo mật, dữ liệu và quyền truy cập

Công việc liên quan mã hóa, kiểm soát truy cập, dữ liệu cá nhân, sao lưu, giám sát hoặc khả năng phục hồi có thể không tạo ra chức năng người dùng thấy ngay, nhưng vẫn là điều kiện thiết yếu để phát hành an toàn.

Một MVP (*minimum viable product*) không phải bản thử nghiệm vô trách nhiệm. “Tối thiểu” chỉ nên áp dụng cho **phạm vi cần kiểm chứng**, không phải cắt bỏ yêu cầu chất lượng hay nghĩa vụ bắt buộc.

### 9.3. Không trì hoãn mọi quyết định kiến trúc

Một số quyết định như quy tắc bảo vệ dữ liệu, giới hạn hiệu năng đã biết, giao tiếp với hệ thống bên ngoài hoặc khả năng khôi phục sự cố cần được giải quyết từ sớm vì thay đổi sau rất tốn kém. Đơn giản hóa yêu cầu nhóm **nhận diện được rủi ro thực tế** để chọn mức đầu tư phù hợp.

### 9.4. Không biến “không làm” thành cách né tránh phản hồi

Nếu người dùng liên tục phản ánh lỗi nghiêm trọng, việc gắn nhãn “không nằm trong phạm vi” không làm lỗi biến mất. Nhóm cần đánh giá tác động, mức khẩn cấp và trách nhiệm hỗ trợ; khi cần, điều chỉnh ưu tiên ngay cả khi phải trì hoãn tính năng khác.

### 9.5. Không xem mọi công việc chưa tạo giá trị tức thì là lãng phí

Học kỹ năng, thử nghiệm công nghệ, đào tạo người mới, chuẩn hóa kiến thức hoặc giảm nợ kỹ thuật có thể tạo giá trị gián tiếp và dài hạn. Câu hỏi cần đặt là **mục đích, mức đầu tư và cách kiểm chứng lợi ích**, không phải “việc này có lên giao diện ngay không?”.

## 10. Một quy trình áp dụng trong nhóm

Có thể dùng chu trình sáu bước dưới đây cho một mục backlog hoặc kế hoạch Sprint. Đây là gợi ý thực hành, không phải một nghi thức bắt buộc mới:

| Bước | Câu hỏi nhóm cần trả lời | Kết quả mong đợi |
| --- | --- | --- |
| **1. Xác định mục tiêu** | Người dùng hay tổ chức cần kết quả gì? | Một phát biểu mục tiêu có thể đánh giá. |
| **2. Làm rõ vấn đề** | Quan sát nào cho thấy vấn đề đang tồn tại? | Giả định, bằng chứng và giới hạn hiểu biết được ghi nhận. |
| **3. Chọn việc cần thiết** | Việc nào bắt buộc, việc nào có thể trì hoãn hoặc bỏ? | Phạm vi nhỏ gắn với mục tiêu; backlog được cập nhật. |
| **4. Chia nhỏ để kiểm chứng** | Lát cắt nhỏ nhất có thể sử dụng và đo kết quả là gì? | User story, tiêu chí chấp nhận, tiêu chuẩn chất lượng. |
| **5. Giao và quan sát** | Người dùng có đạt kết quả? Phần mềm có vận hành an toàn? | Phản hồi từ sản phẩm, kỹ thuật và dòng công việc. |
| **6. Điều chỉnh hoặc dừng** | Nên mở rộng, sửa, giữ nguyên hay bỏ hướng giải pháp? | Quyết định có căn cứ cho vòng tiếp theo. |

### Ví dụ một buổi trao đổi ngắn trước khi triển khai

Một nhóm chuẩn bị xây chức năng “lọc danh sách đơn hàng theo 12 tiêu chí”. Thay vì bắt đầu với tất cả bộ lọc, họ cùng người vận hành xem năm trường hợp thực tế. Kết quả cho thấy người vận hành thường chỉ tìm theo trạng thái, ngày và mã đơn. Nhóm chọn ba bộ lọc đó cho bản đầu tiên, giữ các tiêu chí còn lại trong backlog và đánh giá hành vi sau khi phát hành.

**Điểm tạo giá trị không nằm ở việc số lượng bộ lọc giảm từ 12 xuống 3.** Điểm tạo giá trị là nhóm kiểm chứng được ba bộ lọc có giúp giải quyết tác vụ mục tiêu không, đồng thời tránh đầu tư sớm vào chín khả năng chưa rõ giá trị.

## 11. Bài tập vận dụng

Một nhóm đang xây ứng dụng đặt lịch khám. Chủ sở hữu sản phẩm đặt mục tiêu **giảm số người bỏ dở trước khi xác nhận lịch**. Backlog hiện có các mục:

- A. Đặt lịch khám cho một chuyên khoa, xem giờ còn trống và xác nhận.
- B. Thêm mười kiểu giao diện cá nhân hóa lịch.
- C. Hiển thị thông báo rõ khi khung giờ vừa được người khác đặt.
- D. Tạo hệ thống gợi ý bác sĩ bằng AI với nhiều tham số.
- E. Bảo vệ dữ liệu bệnh nhân và kiểm soát quyền truy cập theo yêu cầu áp dụng.
- F. Thêm bộ lọc theo chuyên khoa, ngày và địa điểm.
- G. Xây trang quản trị báo cáo tùy biến với hơn ba mươi biểu đồ.
- H. Kiểm thử luồng đặt lịch và xử lý lỗi khi mạng gián đoạn.

**Yêu cầu thực hành:**

1. Phân loại từng mục thành *cần làm sớm*, *cần thêm bằng chứng*, *có thể trì hoãn* hoặc *bắt buộc theo ràng buộc*. Nêu giả định đã sử dụng.
2. Đề xuất lát cắt đầu tiên để người dùng có thể đặt được một lịch hợp lệ. Chỉ rõ các điều kiện chất lượng không được bỏ.
3. Nêu hai câu hỏi cần hỏi người dùng hoặc nhân viên tiếp nhận trước khi xây tính năng gợi ý bằng AI.
4. Chọn một chỉ số giá trị sản phẩm và hai chỉ số dòng công việc để kiểm tra hiệu quả của quyết định giảm phạm vi.
5. Nếu trong quá trình thử nghiệm người dùng liên tục không tìm được bác sĩ phù hợp, bạn sẽ thay đổi kế hoạch như thế nào?

### Gợi ý hướng giải

**A, C, E, H** có liên quan trực tiếp đến việc hoàn tất một lượt đặt lịch đúng và an toàn. **F** có thể cần ở mức đủ giúp người dùng chọn nơi khám, nhưng số lượng và cách tổ chức bộ lọc nên được kiểm chứng với người dùng. **B, D, G** chưa cho thấy đóng góp trực tiếp vào vấn đề bỏ dở nên có thể trì hoãn hoặc cần thêm bằng chứng. Mức độ cần thiết của từng mục vẫn phụ thuộc yêu cầu cụ thể, chẳng hạn quy định bảo vệ dữ liệu và cách tổ chức hoạt động của cơ sở y tế.

Lát cắt đầu tiên có thể là chọn chuyên khoa, xem giờ còn trống, chọn một giờ, xác nhận và nhận kết quả rõ ràng. Khi giờ đã bị đặt, người dùng cần biết và chọn giờ khác; quyền truy cập và dữ liệu cá nhân cần được xử lý đúng; lỗi mạng không được dẫn đến việc đặt trùng một cách âm thầm.

Nhóm có thể đo **tỉ lệ đặt lịch hoàn tất** để phản ánh mục tiêu sản phẩm, cùng **cycle time** và **WIP** để theo dõi khả năng giao hàng. Nếu người dùng không tìm được bác sĩ phù hợp, cần điều tra nguyên nhân rồi cân nhắc cải tiến tìm kiếm hoặc khả năng lọc trước khi đầu tư ngay vào hệ thống gợi ý phức tạp.

## 12. Tự kiểm tra hiểu biết

**Câu 1.** Một nhóm bỏ toàn bộ kiểm thử tự động để hoàn thành story nhanh hơn. Đây có phải là “tối đa hóa công việc không cần làm” không?

**Đáp án:** Không. Kiểm thử phù hợp là cơ chế giúp giảm rủi ro và giữ năng lực thay đổi. Bỏ kiểm thử có thể tạo ra lỗi và công việc sửa lại lớn hơn.

**Câu 2.** Một tính năng chưa có bằng chứng về giá trị thì có phải xóa vĩnh viễn khỏi backlog không?

**Đáp án:** Không nhất thiết. Nhóm có thể trì hoãn, thu thêm phản hồi hoặc thử một phần nhỏ. Nếu mục tiêu thay đổi hoặc bằng chứng cho thấy tính năng không còn cần thiết, có thể loại bỏ.

**Câu 3.** Tại sao chia nhỏ theo lát cắt người dùng thường giúp đơn giản hóa hiệu quả hơn chỉ chia theo lớp kỹ thuật?

**Đáp án:** Lát cắt có hành vi dùng được giúp kiểm chứng giả thuyết sớm. Nhóm có thể dừng hoặc đổi hướng trước khi đầu tư vào toàn bộ các thành phần chưa có giá trị được xác nhận.

**Câu 4.** Nhóm giảm WIP, cycle time tốt hơn nhưng người dùng không nhận được cải thiện. Có thể coi là thành công không?

**Đáp án:** Dòng công việc có tín hiệu cải thiện nhưng kết quả sản phẩm chưa đạt. Cần xem lại ưu tiên, giả thuyết về giá trị và cách chọn công việc.

**Câu 5.** Vì sao không nên đo mức độ đơn giản bằng số dòng code đã xóa?

**Đáp án:** Ít dòng code có thể kém rõ ràng hoặc khó duy trì hơn. Cần xét khả năng sử dụng, tính đúng đắn, chất lượng, tốc độ nhận phản hồi và chi phí thay đổi.

## 13. Ghi nhớ cốt lõi

- **Đơn giản hóa là chọn đúng việc cần làm và can đảm chưa làm phần không cần thiết.** Đây là một quyết định về giá trị, không phải chỉ là giảm số lượng đầu việc.
- **Hiểu vấn đề trước khi cam kết giải pháp.** User story và trao đổi với người dùng giúp nhóm nhận diện mục tiêu thực.
- **Giao phần gia tăng nhỏ, đủ chất lượng và có thể kiểm chứng.** Phản hồi sớm cho phép dừng những hướng không còn đáng đầu tư.
- **Backlog gọn, giới hạn WIP và giảm bàn giao thừa** giúp nhóm tập trung hoàn tất công việc tạo giá trị.
- **Scrum, Kanban và XP** đưa nguyên tắc vào nhịp lập kế hoạch, quản lý dòng chảy và thiết kế kỹ thuật.
- **Không hy sinh tính đúng đắn, bảo mật, tuân thủ hoặc khả năng bảo trì** để tạo vẻ ngoài “đơn giản”.
- **Đo kết quả người dùng cùng chất lượng và dòng công việc.** Làm ít hơn chỉ có ý nghĩa khi nhóm học nhanh hơn hoặc đem lại giá trị phù hợp hơn.

Một nhóm Agile trưởng thành không chứng minh hiệu quả bằng số lượng tính năng được xây. Nhóm liên tục đặt câu hỏi **“Điều gì thực sự cần để giải quyết vấn đề này?”**, thử phạm vi nhỏ nhất có giá trị, học từ phản hồi và dành nguồn lực cho những thay đổi quan trọng. Đó là nghệ thuật giảm công việc không cần thiết để phát triển phần mềm thích ứng và cải tiến liên tục.
