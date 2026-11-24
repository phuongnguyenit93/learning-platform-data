# Crystal và lựa chọn cách làm theo quy mô cùng mức độ quan trọng của hệ thống

## 1. Tại sao không có một quy trình Agile phù hợp cho mọi nhóm?

Một nhóm **5 người** đang thử nghiệm giao diện tìm khóa học và một tổ chức có **nhiều nhóm phối hợp** để vận hành dịch vụ thanh toán không đối mặt với cùng một vấn đề. Cả hai đều cần nhận phản hồi sớm, tạo giá trị và cải tiến liên tục, nhưng mức độ phối hợp, lưu dấu quyết định, kiểm thử và quản lý rủi ro có thể khác xa nhau.

Nếu sao chép nguyên xi một quy trình nhiều bước phê duyệt cho nhóm nhỏ, công việc có thể bị chậm vì thủ tục không tương xứng. Nếu dùng cùng một cơ chế trao đổi miệng của nhóm nhỏ cho sản phẩm lớn với rủi ro nghiêm trọng, những phụ thuộc và quyết định quan trọng có thể bị bỏ sót.

**Crystal** là một họ phương pháp phát triển phần mềm Agile gắn với **Alistair Cockburn**, nhấn mạnh rằng cách tổ chức công việc cần thích ứng với **con người, quy mô nhóm và mức hậu quả khi hệ thống thất bại**, thay vì áp một quy trình thống nhất lên mọi dự án.

Ý tưởng trung tâm không phải chọn một màu thật đẹp rồi làm theo từng biểu mẫu. Nhóm cần hỏi:

1. **Có bao nhiêu người phải phối hợp** để tạo phần mềm hoạt động?
2. **Nếu phần mềm sai hoặc không dùng được, hậu quả thực tế nặng tới đâu?**
3. **Những thực hành tối thiểu nào** giúp nhóm giao sản phẩm đáng tin cậy, trao đổi hiệu quả và học từ phản hồi?
4. **Bằng chứng nào** cho thấy cách làm hiện tại còn phù hợp, hoặc cần điều chỉnh?

Trong module **AGILE_DEVELOPMENT**, Crystal bổ sung một góc nhìn khi học user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc: **không chỉ chọn việc gì để làm mà còn chọn cách phối hợp và mức kiểm soát phù hợp với điều kiện của hệ thống**.

> **Điểm mấu chốt:** Crystal không khuyến khích quy trình càng nhẹ càng tốt bằng mọi giá. Mục tiêu là **đủ nhẹ để có phản hồi nhanh và đủ chặt để bảo vệ những rủi ro thực tế**.

## 2. Crystal là một *họ phương pháp*, không phải một công thức duy nhất

### 2.1. Tại sao có nhiều biến thể Crystal?

Crystal thường được mô tả như một **family of methodologies** với các tên như **Crystal Clear, Crystal Yellow, Crystal Orange, Crystal Red** và những biến thể khác. Chúng không phải những phiên bản phần mềm nâng cấp từ thấp lên cao. Mỗi tên gợi ý một cách làm dành cho hoàn cảnh có **yêu cầu phối hợp và tính nghiêm trọng khác nhau**.

Chọn biến thể không đơn giản là “công ty có 30 nhân viên thì dùng màu X”. Điều cần nhìn là **số người trực tiếp phối hợp cho phạm vi sản phẩm**, tính chất rủi ro, cấu trúc nhóm, khả năng giao tiếp, năng lực kỹ thuật và các nghĩa vụ kiểm chứng.

Theo tinh thần Crystal:

- **Con người và tương tác thực tế quan trọng:** kỹ năng, niềm tin, khoảng cách giao tiếp và môi trường làm việc ảnh hưởng hiệu quả của quy trình.
- **Bàn giao phần mềm thường xuyên:** khả năng chạy được giúp kiểm tra giả định và nhận phản hồi sớm.
- **Cải tiến có phản tư (reflective improvement):** nhóm định kỳ xem điều gì cần thay đổi ở cách làm.
- **Mức nghi thức và tài liệu cần tương xứng:** hệ thống nhiều hậu quả có thể cần kiểm soát và bằng chứng chặt hơn.
- **Không giả định mọi dự án giống nhau:** cách làm phải được thiết kế cho hoàn cảnh, không chỉ đổi tên vai trò hoặc cuộc họp.

### 2.2. Những điều Crystal không tự động quy định

Crystal không có nghĩa rằng mọi đội đều phải:

- Tổ chức Sprint cố định hai tuần, có Product Owner và Scrum Master theo định nghĩa của Scrum.
- Dùng cùng bộ cột Kanban hoặc cùng WIP limit.
- Viết mọi yêu cầu thành đúng mẫu user story.
- Dùng một công cụ, ngôn ngữ lập trình hay khung kiểm thử cụ thể.
- Tránh viết tài liệu, kiến trúc, kiểm soát an toàn hoặc quy trình phê duyệt.

Nhóm có thể sử dụng các thực hành Scrum, Kanban, XP hay các kỹ thuật quản trị rủi ro **bổ trợ** cho cách làm Crystal. Nhưng khi áp dụng kết hợp, cần công khai điều gì được dùng, mục đích và ai chịu trách nhiệm; không nên dùng “Crystal linh hoạt” như lý do bỏ chuẩn chất lượng.

### 2.3. Phương pháp được đánh giá bằng kết quả, không phải tên gọi

Một nhóm có thể tự gọi “Crystal Clear” nhưng vẫn:

- Giao sản phẩm nhiều tháng mới kiểm tra với người dùng.
- Không nêu được ai quyết định ưu tiên.
- Không có cách nhận diện lỗi tích hợp.
- Không dám nói khi khả năng chưa đạt điều kiện hoàn tất.

Tên phương pháp không khắc phục những vấn đề đó. Điều cần quan sát là **phần mềm có dùng được không, rủi ro có được kiểm soát không, thông tin có tới đúng người không và nhóm có cải tiến dựa trên phản hồi không**.

## 3. Hai trục quan trọng: quy mô nhóm và mức độ hệ trọng

### 3.1. Trục quy mô: số người phải phối hợp

Trong các mô tả phổ biến về Crystal, nhóm nhỏ được gắn với các biến thể “nhẹ” như Crystal Clear; khi số người tăng, những biến thể như Yellow, Orange hoặc Red thể hiện nhu cầu tổ chức phối hợp chặt hơn.

| Quy mô phối hợp | Rủi ro điển hình | Nhu cầu thực hành thường tăng |
| --- | --- | --- |
| **Nhóm nhỏ** | Thông tin nằm ở một vài người, phụ thuộc cá nhân, thiếu kiểm thử. | Trao đổi trực tiếp, cùng hiểu mục tiêu, giao phần mềm thường xuyên, chia sẻ kiến thức. |
| **Vài nhóm hoặc một nhóm lớn** | Hợp đồng API khác nhau, handoff và xung đột ưu tiên. | Ranh giới sở hữu, quyết định giao diện, lịch tích hợp, cách truyền thông không đồng bộ. |
| **Nhiều nhóm phối hợp** | Phụ thuộc chéo, thay đổi phá tương thích, môi trường và release phức tạp. | Điều phối liên nhóm, kiến trúc tích hợp, quản lý phụ thuộc, bằng chứng kiểm chứng và cơ chế phát hành rõ. |

Quy mô nên tính **những người cần phối hợp chặt để hoàn thành công việc**, không chỉ tổng số nhân viên toàn công ty. Một tổ chức 200 người có một sản phẩm do đội 6 người phụ trách vẫn có những đặc điểm của nhóm nhỏ; ngược lại, 8 người phân tán qua nhiều tổ chức với phụ thuộc khó có thể cần cơ chế phối hợp bổ sung.

### 3.2. Trục hệ trọng (*criticality*): hậu quả khi hệ thống thất bại

Trong cách phân loại gắn với Crystal, một thang thường được trình bày bằng các chữ:

| Ký hiệu | Hậu quả minh họa khi thất bại | Ví dụ để suy nghĩ |
| --- | --- | --- |
| **C — Comfort** | Mất tiện nghi hoặc gây khó chịu; tác động hạn chế trong bối cảnh đã xét. | Bộ lọc khóa học tải chậm ở bản thử nghiệm không có dữ liệu quan trọng. |
| **D — Discretionary money** | Mất tiền hoặc nguồn lực có thể chủ động chi tiêu; thiệt hại không đe dọa hoạt động thiết yếu. | Một thử nghiệm khuyến nghị làm giảm hiệu quả chiến dịch nhỏ. |
| **E — Essential money** | Mất nguồn lực tài chính thiết yếu hoặc đe dọa hoạt động quan trọng. | Thanh toán/hạch toán sai gây tổn thất kinh doanh nghiêm trọng. |
| **L — Life** | Nguy cơ thiệt hại đến tính mạng con người. | Phần mềm điều khiển chức năng an toàn của một thiết bị y tế. |

Các nhãn trên là **mô hình phân loại để thảo luận**, không phải chứng nhận mức an toàn, thang pháp lý hay phép đo chính xác áp dụng cho mọi tổ chức. Việc xếp loại phải dựa trên **hậu quả có thể xảy ra nếu hệ thống sai**, chứ không dựa vào cảm giác “tính năng này quan trọng”.

Chẳng hạn, một màn hình khóa học có thể rất quan trọng đối với tăng trưởng nhưng lỗi trong bản demo chỉ gây bất tiện. Một API ít người nhìn thấy lại có thể ảnh hưởng nghiêm trọng vì quyết định liên quan thanh toán hoặc dữ liệu riêng tư.

### 3.3. “Hệ trọng” khác “ưu tiên cao”

Ba câu hỏi dễ bị nhầm:

- **Business value:** làm xong sẽ tạo hoặc bảo vệ giá trị nào?
- **Urgency / Cost of Delay:** trì hoãn thêm một tuần gây hậu quả ra sao?
- **Criticality:** nếu chức năng thất bại theo cách có thể xảy ra, mức thiệt hại nghiêm trọng tới đâu?

Ví dụ, một banner tuyển sinh cần giao trước tối mai có **tính cấp thiết cao** nhưng lỗi hiển thị có thể chỉ gây thiệt hại nhỏ. Một cơ chế lưu thông tin tài chính có thể **không được đổi thường xuyên**, nhưng khi sai có hậu quả lớn; nó cần mức kiểm soát tương xứng dù không phải PBI đang được ưu tiên cho một tính năng mới.

**Không lấy điểm ưu tiên backlog thay cho đánh giá hậu quả thất bại.** Cũng không dùng nhãn Crystal để tự tuyên bố rằng các rủi ro bảo mật, riêng tư hoặc nghĩa vụ tuân thủ đã được kiểm soát.

### 3.4. Hậu quả phụ thuộc ngữ cảnh sử dụng

Một chức năng có thể mang mức hậu quả khác nhau theo môi trường:

| Bối cảnh | Nếu lỗi xảy ra | Điều cần đánh giá |
| --- | --- | --- |
| Bộ lọc chủ đề trong bản prototype với dữ liệu giả | Người dùng thử chọn nhầm bộ lọc. | Tác động thấp, kiểm tra trải nghiệm và phản hồi sớm. |
| Đăng ký khóa học thật | Học viên có thể mất chỗ hoặc bị xác nhận trùng. | Tính nhất quán dữ liệu, quyền truy cập, cơ chế xử lý lỗi. |
| Thu học phí và hoàn tiền | Sai số tiền, ghi nhận thanh toán hai lần hoặc không đối soát được. | Thiệt hại tài chính, hợp đồng tích hợp, bảo mật, audit và khôi phục. |
| Hệ thống hỗ trợ quyết định y khoa | Một kết quả sai có thể gây hại cho người bệnh. | Phân tích nguy cơ an toàn, xác minh độc lập, quy định chuyên ngành khi áp dụng. |

Mức nghiêm trọng phải được đánh giá **theo cách hệ thống thực sự được dùng**, phạm vi triển khai và khả năng gây hại, không dựa riêng vào tên ngành. Hệ thống giáo dục vẫn có dữ liệu cá nhân và nghĩa vụ an toàn; nhãn C hay D không phải lý do bỏ kiểm soát phù hợp.

## 4. Hiểu các màu Crystal mà không áp dụng máy móc

### 4.1. Các tên biến thể thường được gặp

Các mô tả nhập môn thường liên hệ màu với quy mô phối hợp xấp xỉ như sau:

| Tên thường gặp | Quy mô minh họa thường được nhắc tới | Cách tư duy |
| --- | --- | --- |
| **Crystal Clear** | Đội nhỏ, thường khoảng **6–8 người hoặc ít hơn** trong một số mô tả. | Giao tiếp gần, giao sản phẩm thường xuyên, ít thủ tục nhưng có kiểm soát kỹ thuật. |
| **Crystal Yellow** | Nhóm lớn hơn, thường được mô tả ở cỡ **vài chục người trở xuống**. | Cần làm rõ thêm vai trò phối hợp, thông tin và điểm giao tiếp. |
| **Crystal Orange** | Quy mô **vài chục người** với nhiều luồng công việc phụ thuộc. | Nhu cầu điều phối nhóm, quyết định kiến trúc, lịch tích hợp và giao tiếp tăng. |
| **Crystal Red và các biến thể lớn hơn** | Tổ chức phát triển có **nhiều người/nhóm hơn**. | Mức cấu trúc và quản trị phụ thuộc tăng, vẫn cần phản hồi sớm và cải tiến. |

**Các khoảng người chỉ là hình dung tham khảo, không phải ranh giới bắt buộc hoặc công thức chính thức để được dùng một tên Crystal.** Tài liệu và cách triển khai Crystal có thể mô tả các ngưỡng khác nhau. Team size không thể quyết định phương pháp khi không xét criticality, kinh nghiệm, phân tán địa lý, phụ thuộc và yêu cầu kiểm chứng.

Một nhóm 7 người làm thiết bị ảnh hưởng tính mạng **không nên chọn “quy trình nhẹ” chỉ vì đủ nhỏ để gọi Clear**. Ngược lại, 30 người làm những công việc tương đối độc lập có thể không cần sao chép toàn bộ nghi thức của một dự án lớn phụ thuộc chặt chẽ.

### 4.2. Màu không phải thang chất lượng hay mức trưởng thành

Không đúng khi kết luận:

- “Red cao cấp hơn Clear nên công ty trưởng thành phải dùng Red.”
- “Clear là không cần tài liệu và kiểm thử.”
- “Càng tăng màu càng phải thêm thật nhiều cuộc họp.”
- “Sản phẩm có rủi ro tài chính cao thì chỉ cần chọn màu đậm là đủ.”

Tên biến thể chỉ hỗ trợ việc **thiết kế phương pháp cho bối cảnh**. Một nhóm trưởng thành có thể dùng cách làm rất nhẹ vì hậu quả thấp và tương tác hiệu quả; một đội nhỏ vẫn cần hồ sơ truy vết và xác minh chặt khi phát triển hệ thống có rủi ro lớn.

### 4.3. Mô hình lựa chọn hai trục

~~~mermaid
flowchart TD
    A["Xác định ranh giới sản phẩm và nhóm"] --> B["Đánh giá quy mô phối hợp"]
    B --> C["Đánh giá hậu quả khi thất bại"]
    C --> D{"Quy mô / criticality hiện tại?"}
    D --> E["Nhỏ, hậu quả thấp: giao tiếp gần, ít nghi thức"]
    D --> F["Lớn, hậu quả thấp: thêm điều phối và hợp đồng"]
    D --> G["Nhỏ, hậu quả cao: thêm kiểm soát và bằng chứng"]
    D --> H["Lớn, hậu quả cao: cả điều phối lẫn assurance"]
    E --> I["Chọn thử bộ thực hành phù hợp"]
    F --> I
    G --> I
    H --> I
    I --> J["Giao phần mềm, quan sát, cải tiến"]
    J -. "Đánh giá lại khi bối cảnh đổi" .-> A
~~~

Đây là sơ đồ **ra quyết định**, không phải thuật toán gán màu. Từ một tên Crystal, nhóm vẫn phải xác định **quy trình cụ thể và bằng chứng cần có**.

## 5. Ma trận quyết định: thêm gì khi quy mô hoặc hậu quả tăng?

Một ma trận thực hành hữu ích:

|  | **Hậu quả thất bại tương đối thấp** | **Hậu quả thất bại tương đối cao** |
| --- | --- | --- |
| **Nhóm nhỏ** | Trao đổi trực tiếp, user story đủ rõ, demo/giao sớm, test tự động phù hợp, retro ngắn. | Vẫn giao sớm nhưng thêm phân tích rủi ro, tiêu chí kiểm chứng, review chuyên môn, truy vết thay đổi và kiểm soát phát hành theo nghĩa vụ. |
| **Nhiều người/nhóm** | Rõ ranh giới sở hữu, hợp đồng tích hợp, điều phối backlog/phụ thuộc, tài liệu tối thiểu có thể tra cứu, CI và lịch tích hợp. | Kết hợp điều phối liên nhóm với quản trị rủi ro, xác minh độc lập khi cần, bằng chứng kiểm thử, quản lý cấu hình và audit, phát hành/khôi phục có kiểm soát. |

**Ví dụ:** một đội 5 người khám phá giao diện tìm khóa học có thể làm việc trực tiếp với học viên, tích hợp mỗi ngày và cập nhật backlog sau các thử nghiệm nhỏ. Nếu cùng đội này xây tính năng ghi nhận học phí với tác động tài chính lớn, họ cần thêm kiểm tra đối soát, kiểm soát quyền, audit và quy trình rollback phù hợp — **mặc dù số người không đổi**.

### 5.1. Điều tăng theo quy mô không chỉ là số cuộc họp

Khi nhiều nhóm cùng tạo một sản phẩm, thông tin truyền miệng dễ mất độ tin cậy. Những cơ chế bổ sung có thể gồm:

- Một nơi công bố **Product Goal và thứ tự ưu tiên**.
- Hợp đồng API, schema và chính sách tương thích có người chịu trách nhiệm.
- Cách thông báo thay đổi ảnh hưởng nhiều nhóm.
- Định nghĩa Done và kiểm thử tích hợp chung cho phần sản phẩm liên quan.
- Lịch/điều kiện tích hợp, release và khôi phục được hiểu chung.
- Quy tắc xử lý blocker và phụ thuộc liên nhóm.
- Hồ sơ quyết định kiến trúc ngắn cho những quyết định khó đảo ngược.

Nếu một cuộc họp có thể thay bằng test hợp đồng và thông báo rõ, không cần giữ cuộc họp chỉ để chứng minh “quy trình chặt”. Ngược lại, một tài liệu thiết kế ngắn có thể cần thiết nếu quyết định ảnh hưởng nhiều nhóm trong thời gian dài.

### 5.2. Điều tăng theo criticality là mức tin cậy của bằng chứng

Với rủi ro nghiêm trọng, nhóm thường cần nâng mức tin cậy thông qua:

- Phân tích hậu quả và kịch bản thất bại.
- Điều kiện chấp nhận có thể kiểm chứng, gồm các trường hợp lỗi quan trọng.
- Kiểm thử tự động và thủ công đúng loại rủi ro.
- Review độc lập hoặc phân tách nhiệm vụ khi chính sách yêu cầu.
- Quản lý phiên bản, cấu hình và truy vết từ yêu cầu/rủi ro đến bằng chứng.
- Kiểm tra an ninh, an toàn, quyền riêng tư và khả năng khôi phục.
- Quy trình phát hành và giám sát theo mức độ ảnh hưởng.

**Không có phương pháp Agile nào, kể cả Crystal, tự động thay thế tiêu chuẩn an toàn, pháp luật hoặc yêu cầu chứng nhận chuyên ngành.** Với hệ thống có khả năng gây hại đến tính mạng, phải theo quy trình kỹ thuật an toàn và tiêu chuẩn áp dụng, có chuyên gia đủ thẩm quyền đánh giá.

## 6. Bảy đặc tính thường được nhắc tới ở Crystal Clear

Crystal Clear là biến thể thường được giới thiệu rõ nhất trong các bài nhập môn. Một tập hợp **bảy thuộc tính quan trọng** được Alistair Cockburn trình bày cho môi trường Crystal Clear gồm: **frequent delivery, reflective improvement, osmotic communication, personal safety, focus, easy access to expert users, technical environment with automated tests, configuration management and frequent integration**.

Không nên xem đây là checklist dùng một lần. Mỗi đặc tính nhằm giải quyết một vấn đề cụ thể về tốc độ học hỏi, cộng tác hoặc chất lượng.

### 6.1. Frequent delivery — bàn giao thường xuyên

Nhóm đưa phần mềm có thể dùng được đến người có khả năng kiểm chứng **theo nhịp ngắn và đều**, thay vì chờ nhiều tháng mới kết nối các thành phần.

**Ví dụ:** trước tiên giao một luồng đăng ký miễn phí đầu cuối, chưa có thanh toán hay SMS. Học viên thử thực hiện thao tác; nhóm biết liệu trạng thái “đăng ký thành công” có dễ hiểu không.

Nhịp “thường xuyên” cần phù hợp khả năng tích hợp, rủi ro và bối cảnh người dùng; không bắt buộc một số ngày cố định. **Bàn giao không đồng nghĩa bỏ kiểm thử**. Với hệ thống cần phê duyệt phát hành, nhóm có thể tạo các Increment đã được xác minh sớm và tổ chức release theo quy định.

### 6.2. Reflective improvement — cải tiến có phản tư

Nhóm định kỳ nhìn lại:

1. Điều gì tạo giá trị hoặc giảm rủi ro?
2. Điều gì gây chờ đợi, làm lại hoặc hiểu lầm?
3. Một thay đổi nhỏ nào có khả năng cải thiện?
4. Làm sao biết thay đổi đó có ích?

**Ví dụ:** review mã thường mất bốn ngày vì chỉ một người có quyền duyệt. Nhóm thử bổ sung người dự phòng và thống nhất điều kiện review, theo dõi thời gian chờ cùng lỗi sau phát hành.

Mục tiêu là **cải thiện có thể quan sát**, không chỉ tổ chức buổi họp lấy ý kiến rồi bỏ đó.

### 6.3. Osmotic communication — giao tiếp thẩm thấu

Trong nhóm ngồi gần hoặc có không gian hợp tác phù hợp, thành viên có thể **tình cờ nghe và nắm được bối cảnh công việc liên quan** mà không cần mọi thông tin đều trở thành cuộc họp riêng.

Ví dụ, kỹ sư giao diện nghe cuộc trao đổi rằng API đã đổi cách báo hết chỗ và kịp chỉnh thông báo trước khi tích hợp.

Khái niệm này **không có nghĩa ai cũng phải nghe mọi cuộc nói chuyện** hoặc công việc nên bị gián đoạn liên tục. Với nhóm phân tán, có thể tạo những cơ chế tương đương: kênh quyết định rõ, phiên pairing, demo ngắn, bản ghi thay đổi có thể tra cứu, tài liệu thiết kế vừa đủ và những buổi trao đổi đồng bộ khi cần.

Thông tin nhạy cảm, dữ liệu người dùng và quyền truy cập vẫn phải được bảo vệ; không phải mọi chi tiết đều nên phát tán rộng.

### 6.4. Personal safety — an toàn để lên tiếng

Thành viên cần có khả năng:

- Báo rằng kế hoạch không còn khả thi.
- Hỏi khi không hiểu nghiệp vụ hoặc kỹ thuật.
- Nêu rủi ro bảo mật/chất lượng.
- Nhận trách nhiệm về sai sót và xin trợ giúp.
- Phản biện ý kiến có ảnh hưởng lớn bằng bằng chứng.

**An toàn để lên tiếng không đồng nghĩa không có trách nhiệm nghề nghiệp.** Nhóm vẫn phải tuân thủ DoD, bảo mật và quy tắc làm việc; nhưng không được làm nhục hay trả đũa người phát hiện lỗi.

### 6.5. Focus — sự tập trung

Nhóm có điều kiện tập trung vào **một số ít kết quả quan trọng**, hạn chế đổi ngữ cảnh và công việc dở dang. Nếu người quản lý liên tục chen yêu cầu “khẩn cấp”, một nhóm nhỏ cũng có thể mất năng lực giao hàng.

**Ví dụ:** khi kiểm thử đăng ký trùng thất bại, nhóm ưu tiên sửa lỗi và hoàn tất lát cắt đầu tiên thay vì bắt đầu thêm bộ lọc nâng cao, dashboard và SMS cùng lúc.

Thực hành hỗ trợ gồm mục tiêu ngắn hạn rõ, giới hạn WIP phù hợp, chính sách xử lý việc khẩn cấp và thời gian hợp lý cho kiểm thử/tích hợp.

### 6.6. Easy access to expert users — dễ tiếp cận người hiểu nghiệp vụ

Nhóm cần kênh phản hồi nhanh từ người **thực sự hiểu nhu cầu và các quy tắc liên quan**, không buộc mọi câu hỏi đi qua quá nhiều lớp chuyển tiếp.

Ví dụ, trước khi xác định xử lý học viên hủy sau hạn đăng ký, Developers có thể trao đổi với Product Owner và chuyên gia vận hành khóa học để làm rõ ví dụ, hậu quả và người có thẩm quyền quyết định.

“Tiếp cận dễ” không có nghĩa người dùng phải trực online 24/7 hoặc mọi kỹ sư được quyền yêu cầu dữ liệu cá nhân tùy tiện. Có thể dùng phiên làm rõ định kỳ, ví dụ hành vi, môi trường thử nghiệm và đầu mối phản hồi nhanh.

### 6.7. Technical environment — môi trường kỹ thuật hỗ trợ chất lượng

Một cách làm nhẹ cần **năng lực kỹ thuật đáng tin cậy** để không che giấu lỗi:

- **Automated tests** kiểm chứng các hành vi quan trọng.
- **Configuration management** giúp theo dõi và tái hiện phiên bản, thay đổi.
- **Frequent integration** phát hiện xung đột và lỗi tích hợp sớm.

Những thực hành này không thay thế kiểm thử phi chức năng, kiểm tra bảo mật hay yêu cầu chứng nhận khi hệ thống có rủi ro cao. Nhưng thiếu chúng, một nhóm giao tiếp tốt vẫn có thể liên tục giao phần mềm sai.

### 6.8. Tổng hợp tác dụng

| Thuộc tính | Cần bảo vệ điều gì? | Dấu hiệu đang thiếu |
| --- | --- | --- |
| **Frequent delivery** | Phản hồi giá trị sớm. | Chỉ có demo giả lập, nhiều tháng không có phần chạy được. |
| **Reflective improvement** | Cách làm được cải tiến qua thực tế. | Lỗi/chờ đợi lặp lại, không có hành động sau retrospective. |
| **Osmotic communication** | Bối cảnh được chia sẻ với chi phí thấp. | Thay đổi API quan trọng gây bất ngờ tới ngày tích hợp. |
| **Personal safety** | Rủi ro được nêu đúng lúc. | Người biết lỗi nhưng im lặng do sợ bị quy trách nhiệm. |
| **Focus** | Năng lực hoàn tất thay vì bắt đầu nhiều việc. | Rất nhiều hạng mục in progress, ít hạng mục Done. |
| **Access to expert users** | Hiểu đúng vấn đề và quy tắc nghiệp vụ. | Quyết định được đưa ra trên giả định không ai xác nhận. |
| **Technical environment** | Tính đúng đắn, tích hợp và khả năng đổi hướng. | “Máy tôi chạy được”, phát hiện lỗi hồi quy muộn. |

## 7. Chọn cách làm cho nhóm nhỏ: thực hành nhẹ nhưng đủ trách nhiệm

Giả sử **5 Developers cùng một Product Owner kiêm đầu mối nghiệp vụ** làm một ứng dụng nội bộ thử nghiệm tìm khóa học. Hậu quả khi bộ lọc chưa chính xác là bất tiện; bản thử dùng dữ liệu không nhạy cảm.

Nhóm có thể chọn những thực hành gần tinh thần **Crystal Clear**:

- Thống nhất một mục tiêu giá trị ngắn hạn và một backlog có thứ tự.
- Làm rõ hành vi bằng ví dụ, trao đổi trực tiếp khi phát hiện câu hỏi.
- Cùng review các thay đổi ảnh hưởng nhiều người.
- Tích hợp thường xuyên, dùng kiểm thử tự động phù hợp.
- Giao lát cắt có thể dùng để học từ người thử.
- Cập nhật trạng thái công việc và trở ngại trên bảng đơn giản.
- Định kỳ xem lại chất lượng, thời gian chờ và phản hồi người dùng.

**Không nhất thiết cần:** nhiều nhóm phê duyệt trung gian, biên bản dài cho mọi quyết định nhỏ, cuộc họp đồng bộ hằng ngày kéo dài hoặc hàng chục chỉ số mà không ai dùng.

Nhưng nhóm vẫn cần:

- Quản lý phiên bản và quyền truy cập.
- Tiêu chí hoàn tất/DoD phù hợp.
- Cách xử lý khi test không đạt.
- Đầu mối quyết định ưu tiên và nghiệp vụ.
- Điều kiện phát hành/khôi phục theo môi trường sử dụng.

Nhóm nhỏ không được miễn các tiêu chuẩn bắt buộc chỉ vì chọn phương pháp nhẹ.

## 8. Khi cùng sản phẩm có nhiều nhóm: tăng cấu trúc để giảm chi phí phối hợp

Giả sử nền tảng học trực tuyến phát triển thêm **dịch vụ đăng ký, thanh toán, quản lý lớp, thông báo và hỗ trợ**, với khoảng 30 người chia nhiều nhóm. Hậu quả khi một API đổi hợp đồng mà không thông báo có thể ảnh hưởng đến toàn bộ hành trình người dùng.

Không thể trông đợi mọi người “nghe tình cờ” cuộc trao đổi của nhau. Nhóm cần bổ sung **đường truyền thông và bằng chứng có cấu trúc**:

### 8.1. Cấu trúc sản phẩm và trách nhiệm

- Một định hướng sản phẩm và cách quyết định **ưu tiên liên nhóm** không mâu thuẫn.
- Chủ sở hữu hợp đồng API và các quyết định kiến trúc ảnh hưởng nhiều nhóm.
- Điểm liên hệ để xử lý blocker, sự cố và phụ thuộc.
- Lịch/nội dung tích hợp được công bố.
- Chính sách chất lượng áp dụng cho hành vi xuyên nhiều dịch vụ.

### 8.2. Tài liệu “vừa đủ” khi số người tăng

Những tài liệu và dấu vết thường có giá trị:

| Thứ cần lưu | Vấn đề được giảm |
| --- | --- |
| **Hợp đồng API, schema, mã lỗi** | Mỗi nhóm hiểu một cách về dữ liệu và tương tác. |
| **Quyết định kiến trúc ngắn và lý do** | Quyết định quan trọng bị quên khi người tham gia thay đổi. |
| **Danh sách phụ thuộc và người phụ trách** | Blocker không rõ đường tháo gỡ. |
| **Kịch bản tích hợp, contract test, regression** | Lỗi chỉ xuất hiện vào thời điểm release. |
| **Chính sách triển khai, rollback, sự cố** | Tự ý thay đổi production hoặc phản ứng không nhất quán. |
| **Mục tiêu, kế hoạch giao phần giá trị** | Mỗi nhóm tối ưu tính năng riêng mà hành trình tổng thể chưa dùng được. |

Crystal không yêu cầu “tài liệu càng dài càng tốt”. **Chi phí viết và giữ tài liệu** nên tương xứng với chi phí hiểu sai, chuyển giao hoặc hậu quả khi tài liệu thiếu. Tài liệu lỗi thời cũng là một nguồn rủi ro.

### 8.3. Làm sao không biến phối hợp thành quan liêu?

Nhóm có thể ưu tiên:

1. Hợp đồng máy kiểm tra được thay vì cuộc họp kiểm tra thủ công lặp đi lặp lại.
2. Quyết định kiến trúc ngắn, có đường dẫn và người chịu trách nhiệm.
3. Demo lát cắt tích hợp theo nhịp đủ ngắn.
4. Cơ chế nâng cấp blocker rõ thay vì chờ từng tầng quản lý.
5. Một số ít số đo gắn với chất lượng và dòng giá trị.

Nếu tăng từ 5 lên 30 người mà chỉ tăng số cuộc họp, nhóm có thể vẫn gặp lỗi tích hợp; **thêm cấu trúc phải tạo được thông tin tốt hơn hoặc giảm rủi ro, không chỉ tạo dấu vết hoạt động**.

## 9. Khi hậu quả thất bại cao: không được dùng “linh hoạt” để bỏ kiểm soát

### 9.1. Từ mô tả hậu quả tới các rủi ro có thể kiểm chứng

Giả sử sản phẩm có chức năng thu học phí. Những rủi ro có thể gồm:

- Thanh toán bị ghi nhận thành công hai lần.
- Người dùng bị trừ tiền nhưng hệ thống không xác nhận.
- Lỗi retry tạo giao dịch trùng.
- Thông tin thanh toán hoặc dữ liệu cá nhân bị truy cập trái quyền.
- Không thể đối soát hoặc hoàn tiền theo quy định.

Không đủ khi nói “đây là hạng mục critical E, hãy tăng tài liệu”. Nhóm cần chỉ ra **từng kịch bản thất bại**, tác động, kiểm soát cần thiết, bằng chứng test và chủ sở hữu quyết định.

| Rủi ro | Kiểm soát tham khảo | Bằng chứng cần xem |
| --- | --- | --- |
| **Giao dịch trùng** | Idempotency, ràng buộc dữ liệu và quy tắc retry phù hợp. | Test lặp request, test cạnh tranh, đối soát. |
| **Bản ghi thanh toán sai** | Giao dịch nhất quán, theo dõi trạng thái và phục hồi. | Integration test, scenario timeout, thử khôi phục. |
| **Truy cập trái quyền** | Xác thực, phân quyền, phân tách dữ liệu. | Security test, review quyền và log truy cập phù hợp. |
| **Thay đổi hợp đồng đối tác** | Versioning, contract test, cơ chế tương thích. | Bộ test hợp đồng và kết quả tích hợp. |
| **Lỗi sau triển khai** | Quan sát, cảnh báo, rollback và quy trình ứng cứu. | Diễn tập/kiểm tra khôi phục khi rủi ro yêu cầu. |

Các kỹ thuật trên là gợi ý, không bảo đảm an toàn cho mọi hệ thống; chuyên gia có thẩm quyền cần chọn kiểm soát tương xứng với rủi ro và tiêu chuẩn áp dụng.

### 9.2. Hệ thống an toàn tính mạng cần cách tiếp cận kỹ thuật chuyên ngành

Ở mức **L — Life**, hậu quả có thể bao gồm thương tích hoặc tử vong. Một nhóm phải sử dụng **quy trình quản lý rủi ro, xác minh/kiểm định, truy vết, phân tích hazard và chuẩn chuyên ngành phù hợp**, tùy lĩnh vực và pháp luật áp dụng.

**Không thể chỉ chọn “Crystal Red” hoặc “Crystal Clear có thêm test” rồi coi đáp ứng yêu cầu an toàn.** Những yêu cầu nghiêm ngặt có thể cần đánh giá độc lập, bằng chứng chính thức, kiểm soát thay đổi và phê duyệt. Crystal có thể cung cấp tư duy hợp tác và phản hồi ngắn **bên trong** khung kỹ thuật an toàn được yêu cầu, nhưng không thay thế khung ấy.

### 9.3. Bằng chứng nhiều hơn không đồng nghĩa thay đổi chậm mãi

Nhóm có thể vừa nghiêm ngặt về chất lượng vừa nhận phản hồi sớm bằng cách:

- Tách các phần hành vi nhỏ nhưng đủ nghĩa để xác minh.
- Tự động hóa test và truy vết nơi thích hợp.
- Làm rõ kịch bản lỗi và rủi ro sớm, không chờ cuối dự án.
- Kiểm tra contract liên nhóm thường xuyên.
- Sử dụng môi trường thử và dữ liệu an toàn để giảm rủi ro trước release.
- Phân biệt **Increment đã kiểm chứng** với **quyết định mở sử dụng rộng** khi tổ chức cần release gate.

Mục tiêu là **giảm độ trễ học hỏi mà không bỏ bảo vệ cần thiết**.

## 10. Tình huống xuyên suốt: chọn cách làm Crystal cho nền tảng học trực tuyến

### 10.1. Giai đoạn A — Năm người thử nghiệm chức năng tìm khóa học

**Bối cảnh giả định:**

- 5 người trực tiếp xây và thử sản phẩm.
- Học viên dùng bản thử với dữ liệu không nhạy cảm.
- Chức năng chính là tìm và lọc danh mục khóa học.
- Nếu bộ lọc thất bại, hậu quả chủ yếu là bất tiện và mất thời gian trong thử nghiệm.
- Người hiểu nghiệp vụ có thể trao đổi với nhóm hằng tuần hoặc khi phát sinh câu hỏi.

Nhóm cân nhắc cách làm gần **Crystal Clear**. Họ:

1. Chọn mục tiêu “học viên thử tìm được khóa phù hợp bằng bộ lọc cơ bản”.
2. Ghi các khả năng vào backlog, ưu tiên lát cắt nhỏ có thể quan sát.
3. Thiết lập CI và những test quan trọng của bộ lọc.
4. Bàn giao bản thử sớm, ghi nhận cách người dùng thao tác.
5. Cải tiến mỗi tuần dựa trên kết quả và trở ngại thật.

Nhóm **không cần tự đặt tên role Scrum Master hoặc Sprint** nếu không áp dụng Scrum. Họ vẫn cần người chịu trách nhiệm ưu tiên, chất lượng và kết quả.

### 10.2. Giai đoạn B — Sản phẩm có luồng đăng ký thật

Sản phẩm mở rộng: học viên đã đăng nhập có thể tự đăng ký khóa miễn phí còn chỗ. Nếu chức năng sai:

- Học viên có thể bị xác nhận trùng.
- Hệ thống có thể nhận vượt sức chứa.
- Người khác có thể thấy dữ liệu đăng ký trái quyền.
- Nhân viên hỗ trợ phải sửa dữ liệu thủ công.

Quy mô người thực hiện **có thể vẫn chỉ 5 người**, nhưng mức hậu quả khác hẳn bản demo. Cách làm cần thêm kiểm soát:

| Điều trước đây đủ cho bản thử | Điều cần bổ sung khi đăng ký thật |
| --- | --- |
| Quan sát thao tác lọc trên dữ liệu giả. | Kiểm thử đúng quyền, sức chứa, lỗi mạng, đăng ký lặp và dữ liệu nhất quán. |
| Có thể sửa nhanh nếu hiển thị sai. | Cần chính sách khôi phục khi dữ liệu đăng ký bị lỗi. |
| Thảo luận miệng hầu hết quy tắc. | Ghi lại những quy tắc quan trọng thành ví dụ có thể test. |
| Release bản thử ít rủi ro. | Phân quyền, review và kiểm chứng môi trường sử dụng thực theo chính sách. |
| Chủ yếu đo khả năng tìm khóa. | Đo tỷ lệ đăng ký hoàn tất, lỗi dữ liệu, thời gian xử lý hỗ trợ và độ tin cậy. |

**Bài học:** không nhất thiết đổi màu ngay khi quy mô đội giữ nguyên, nhưng **mức kiểm chứng và những ranh giới an toàn phải đổi khi hậu quả đổi**.

### 10.3. User story và ví dụ rủi ro

**User story:**

> Là học viên đã đăng nhập, tôi muốn đăng ký khóa miễn phí còn chỗ để tự tham gia học mà không phải nhờ nhân viên hỗ trợ.

Nhóm cần thống nhất với người có thẩm quyền nghiệp vụ về hành vi:

~~~gherkin
Feature: Đăng ký khóa học miễn phí

  Scenario: Đăng ký thành công khi còn chỗ
    Given học viên A đã đăng nhập và chưa đăng ký khóa X
    And khóa X còn ít nhất một chỗ
    When A xác nhận đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A thấy xác nhận thành công

  Scenario: Gửi lại yêu cầu không tạo đăng ký trùng
    Given A đã có đăng ký hiệu lực cho khóa X
    When A gửi lại yêu cầu đăng ký khóa X
    Then hệ thống không tạo đăng ký hiệu lực thứ hai
    And A nhận được trạng thái đăng ký hiện tại

  Scenario: Hai học viên tranh chỗ cuối
    Given khóa X chỉ còn một chỗ
    When hai học viên hợp lệ đồng thời xác nhận đăng ký
    Then tối đa một đăng ký mới được xác nhận
    And số đăng ký hiệu lực không vượt sức chứa

  Scenario: Truy cập dữ liệu ngoài quyền
    Given người dùng B không có quyền xem đăng ký của A
    When B yêu cầu đọc thông tin đăng ký của A
    Then hệ thống từ chối truy cập
~~~

Các tình huống trên là **ví dụ hành vi**, chưa phải test tự động nếu chưa nối với mã kiểm thử. Chọn cách làm Crystal nhẹ không làm giảm nhu cầu có bằng chứng test tích hợp và kiểm tra quyền khi hậu quả có thể nghiêm trọng.

### 10.4. Giai đoạn C — Nhiều nhóm và tích hợp thanh toán

Sau một giai đoạn phát triển, sản phẩm có khoảng **30 người phối hợp** ở các nhóm danh mục, đăng ký, thanh toán và hỗ trợ. Một tính năng hủy đăng ký có thể liên quan cả quản lý chỗ, đối soát học phí, hoàn tiền và email.

Nhóm cần điều chỉnh **cả hai trục**:

- **Quy mô tăng:** hợp đồng API, trách nhiệm sở hữu, kiểm thử tương thích, phối hợp release và giải quyết phụ thuộc cần rõ hơn.
- **Hậu quả tăng:** thanh toán sai hoặc mất dữ liệu có thể dẫn đến thiệt hại tài chính, rủi ro pháp lý/riêng tư; cần tăng mức kiểm soát và bằng chứng.

Một phương án không nên làm:

> “Vì đã có 30 người, từ nay tất cả thay đổi phải qua bốn hội đồng; không cần giao Increment nhỏ nữa.”

Một phương án có mục đích hơn:

1. Thống nhất ranh giới sản phẩm, mục tiêu và trách nhiệm ưu tiên.
2. Công bố hợp đồng API cùng chính sách thay đổi và kiểm tra tương thích.
3. Giao các lát cắt tích hợp nhỏ có thể kiểm chứng.
4. Dùng test hồi quy/contract/security tương xứng rủi ro.
5. Công khai phụ thuộc và điều kiện release.
6. Xem dữ liệu lỗi, thời gian chờ và phản hồi người dùng để điều chỉnh.

### 10.5. Điều gì thay đổi và điều gì phải giữ?

| Tính chất | Giai đoạn A: bản thử nhỏ | Giai đoạn B: đăng ký thật | Giai đoạn C: nhiều nhóm + thanh toán |
| --- | --- | --- | --- |
| **Quy mô phối hợp** | Nhỏ. | Có thể giữ nhỏ. | Lớn hơn, nhiều phụ thuộc. |
| **Hậu quả lỗi** | Chủ yếu bất tiện. | Dữ liệu sai, mất chỗ, riêng tư. | Có thể thiệt hại tài chính và ảnh hưởng nhiều người. |
| **Giao tiếp** | Trực tiếp, liên tục. | Trực tiếp + ghi rõ quy tắc quan trọng. | Hợp đồng/tài liệu quyết định tra cứu được, nhịp phối hợp liên nhóm. |
| **Kiểm chứng** | Test phù hợp, quan sát thử. | Test cạnh tranh, quyền và tích hợp. | Test liên dịch vụ, đối soát, an ninh, khôi phục theo rủi ro. |
| **Bàn giao** | Bản thử nhỏ thường xuyên. | Increment đăng ký đáng tin cậy. | Increment tích hợp, release có kiểm soát khi cần. |
| **Cải tiến** | Phản hồi người dùng trực tiếp. | Phản hồi + lỗi dữ liệu và vận hành. | Thêm số đo luồng liên nhóm, chất lượng toàn hành trình. |

Điều **không đổi** là giá trị Agile: cộng tác, giao phần mềm hoạt động, nhận phản hồi, cải tiến liên tục và tôn trọng người dùng. Điều **phải thích ứng** là mức phối hợp và kiểm soát tương xứng với quy mô/hậu quả.

## 11. Xây một bộ thực hành tối thiểu cho tình huống của mình

Một đội không cần chọn một phương pháp chỉ bằng tên màu. Họ có thể lập **bảng quyết định thực hành**:

| Nhu cầu | Nhóm nhỏ / hậu quả thấp | Khi quy mô hoặc hậu quả tăng |
| --- | --- | --- |
| **Mục tiêu và ưu tiên** | Một mục tiêu ngắn hạn, backlog có thứ tự, người chịu trách nhiệm rõ. | Đồng bộ mục tiêu và phụ thuộc giữa các nhóm, minh bạch quyền ưu tiên. |
| **Trao đổi** | Trao đổi trực tiếp và demo ngắn. | Ghi quyết định quan trọng, hợp đồng và cơ chế thông báo. |
| **Làm rõ yêu cầu** | Ví dụ hành vi đủ cho lát cắt sắp làm. | Truy vết thêm các yêu cầu/rủi ro quan trọng và tiêu chí kiểm chứng. |
| **Tích hợp** | CI, code review, test phù hợp. | Contract test và integration test liên nhóm, phối hợp release. |
| **Chất lượng** | DoD/điều kiện hoàn tất rõ. | Mức kiểm chứng, review và bằng chứng tăng theo rủi ro. |
| **Theo dõi công việc** | Bảng đơn giản, ít WIP, chú ý item bị chặn. | Trực quan phụ thuộc, work item age và SLE của chuỗi bàn giao. |
| **Phát hành** | Đưa bản thử vào sử dụng an toàn khi đạt chuẩn. | Kiểm soát quyền, giám sát, kế hoạch rollback/audit khi cần. |
| **Cải tiến** | Retro ngắn, thay đổi nhỏ. | Đánh giá cả điểm nghẽn liên nhóm và sự cố hệ thống. |

### 11.1. Mẫu quyết định ngắn

~~~text
Sản phẩm/phạm vi: Đăng ký và quản lý khóa học trực tuyến
Người dùng: Học viên đã đăng nhập và nhân viên hỗ trợ
Quy mô phối hợp: 6 người trực tiếp, 1 dịch vụ ngoài nhóm
Hậu quả thất bại đáng chú ý:
  - Đăng ký vượt sức chứa / tạo bản ghi trùng
  - Quyền truy cập thông tin học viên
  - Gián đoạn giao tiếp với dịch vụ dữ liệu khóa học

Định hướng cách làm:
  - Giao tiếp gần và demo thường xuyên như nhóm nhỏ
  - Ghi quy tắc nghiệp vụ bằng ví dụ có thể kiểm chứng
  - CI + test tích hợp trường hợp đồng thời + kiểm tra quyền
  - Hợp đồng API với dịch vụ ngoài nhóm
  - Phần tăng trưởng chỉ Done khi đạt chuẩn chất lượng đã thống nhất

Chính sách phản hồi:
  - Nhận phản hồi từ học viên thử nghiệm sau Increment dùng được
  - Xem blocker, lỗi và chất lượng trong buổi cải tiến định kỳ

Điều kiện xem lại:
  - Khi tăng số nhóm, thêm thanh toán, thay đổi rủi ro,
    hoặc thời gian chờ/lỗi vượt mức có thể chấp nhận
~~~

Không cần biến bảng này thành tài liệu hàng chục trang. **Một trang quyết định đủ rõ** có thể hữu ích hơn bộ quy trình dài không được áp dụng.

### 11.2. Định nghĩa điều kiện hoàn tất cho từng loại kết quả

Nếu nhóm dùng Scrum, **Definition of Done (DoD)** là cam kết chính thức của Increment. Nếu không dùng Scrum, nhóm vẫn nên có **chính sách hoàn tất minh bạch** cho công việc và sản phẩm.

Một lát cắt đăng ký có thể yêu cầu:

- [ ] Hành vi và trường hợp lỗi quan trọng đã được xác minh.
- [ ] Các thành phần giao diện, API và dữ liệu hoạt động cùng nhau.
- [ ] Không tạo đăng ký trùng hoặc vượt sức chứa trong các trường hợp kiểm thử bắt buộc.
- [ ] Quyền truy cập và dữ liệu cá nhân được bảo vệ theo chính sách.
- [ ] Test và review cần thiết đã đạt trên bản tích hợp.
- [ ] Công cụ giám sát, hợp đồng API/tài liệu chịu ảnh hưởng được cập nhật khi cần.
- [ ] Có bằng chứng rằng phần mềm có thể sử dụng trong phạm vi công bố.

**Crystal không tạo ra ngoại lệ với chất lượng.** Nếu một yêu cầu quan trọng chưa đạt, phải minh bạch và tiếp tục khắc phục thay vì đổi nhãn trạng thái để báo hoàn thành.

## 12. Crystal, Scrum, Kanban và XP: khác nhau và bổ trợ thế nào?

| Góc nhìn | Crystal | Scrum | Kanban | Extreme Programming (XP) |
| --- | --- | --- | --- | --- |
| **Câu hỏi trọng tâm** | Chọn và điều chỉnh cách làm nào theo con người, quy mô và criticality? | Tạo giá trị cho vấn đề phức tạp qua khung trách nhiệm, sự kiện và artifact thế nào? | Làm sao định nghĩa, quản lý và cải thiện flow? | Làm sao phát triển phần mềm có phản hồi kỹ thuật và chất lượng cao? |
| **Cấu trúc** | Họ phương pháp, các biến thể tùy bối cảnh. | Scrum Team, Sprint, 5 events, 3 artifacts và commitments. | Definition of Workflow, quản lý WIP, flow metrics và cải tiến. | Các giá trị, nguyên tắc và thực hành kỹ thuật. |
| **Nhịp phản hồi** | Bàn giao thường xuyên, reflective improvement. | Sprint có timebox và Review/Retrospective. | Luồng liên tục và các nhịp phản hồi phù hợp. | Test nhanh, tích hợp và phản hồi thường xuyên. |
| **Định hướng quy mô** | Quy mô và criticality là hai yếu tố chọn biến thể. | Không dùng màu hay ma trận criticality để phân biến thể. | Có thể áp dụng cho nhiều workflow, điều chỉnh chính sách theo thực tế. | Tập trung khả năng phát triển phần mềm, cần thích ứng khi mở rộng phối hợp. |
| **Kiểm soát chất lượng** | Tăng mức kiểm chứng theo hậu quả; dùng kỹ thuật phù hợp. | DoD chính thức cho Increment. | Chính sách Started/Finished và điều kiện chuyển trạng thái. | TDD, refactoring, CI, pairing và các kỹ thuật tương ứng. |

### 12.1. Có thể kết hợp mà không nhập nhằng?

Ví dụ một Scrum Team 7 người có thể:

- Dùng **Scrum** cho Product Goal, Sprint Goal, Sprint Planning, Review và DoD.
- Dùng **Kanban** trên Sprint Backlog để giới hạn WIP và thấy item bị chặn.
- Dùng **XP** cho TDD, CI, pair programming và refactoring.
- Dùng **tư duy Crystal** để tự hỏi những thực hành này có phù hợp quy mô và hậu quả hệ thống hay chưa.

Nhóm phải làm rõ **thành phần nào là yêu cầu của Scrum đang áp dụng**, thực hành nào là lựa chọn bổ sung. Nếu tuyên bố dùng Scrum nhưng tự ý bỏ các accountability hoặc artifact của nó, không nên mô tả đó là “Scrum đầy đủ” chỉ vì cách kết hợp có tên nghe hợp lý.

### 12.2. Không có phương pháp nào thay thế việc hiểu sản phẩm

Một bộ nghi thức không giúp nhóm biết người học cần gì nếu họ không nhận phản hồi người dùng. Một pipeline test xanh không chứng minh giải pháp có giá trị nếu tính năng ít ai sử dụng. Ngược lại, phản hồi tốt không bù được lỗi dữ liệu hoặc vi phạm quyền truy cập.

**Lựa chọn phương pháp là phương tiện** để tạo giá trị, có chất lượng và học hỏi trong điều kiện hiện tại, không phải đích đến tự thân.

## 13. Nhóm phân tán và kiến thức khó chia sẻ: điều chỉnh Crystal ra sao?

Một nhóm 6 người làm ở ba múi giờ có thể có **chi phí truyền thông** không giống sáu người làm cùng phòng. Khái niệm osmotic communication nhắc ta rằng giao tiếp tốt thường có tính tự nhiên, nhưng không thể dựa vào những cuộc trao đổi tình cờ khi mọi người ít trùng giờ.

### 13.1. Tạo cơ chế thay thế giao tiếp thẩm thấu

| Rủi ro | Thực hành nhẹ có thể dùng |
| --- | --- |
| Quyết định kỹ thuật bị mất sau cuộc gọi | Ghi quyết định và lý do ngắn vào nơi tra cứu chung. |
| API thay đổi mà nhóm liên quan không biết | Dùng contract test, changelog và kênh thông báo đúng người. |
| Thành viên mới khó hiểu sản phẩm | Duy trì ví dụ nghiệp vụ, hướng dẫn chạy/test và pairing. |
| Người cần trả lời ở múi giờ khác | Công bố thời gian phản hồi kỳ vọng, đầu mối dự phòng và câu hỏi có bối cảnh đầy đủ. |
| Họp quá nhiều làm mất tập trung | Phân biệt nội dung cần trao đổi đồng bộ với thông tin có thể bất đồng bộ. |
| Lỗi bảo mật/riêng tư bị đưa lên kênh công khai | Định nghĩa kênh và quyền truy cập phù hợp cho dữ liệu nhạy cảm. |

### 13.2. Không phải mọi vấn đề đều giải quyết bằng công cụ chat

Một kênh chat nhiều tin nhắn nhưng thiếu quyết định cuối cùng có thể gây khó hiểu hơn một tài liệu ngắn. Với những điều quan trọng và lâu dài, cần **ghi kết luận có thể tra cứu**. Với thảo luận phức tạp hoặc nhạy cảm, cần tổ chức cuộc trao đổi có người liên quan, sau đó tóm tắt quyết định và bước tiếp theo.

Độ “nhẹ” của cách làm phải được đánh giá bằng **chi phí giao tiếp và chất lượng quyết định thật**, không bằng số lượng tài liệu ít nhất.

## 14. Đánh giá xem phương pháp được chọn có còn phù hợp không

Crystal nhấn mạnh **reflective improvement**, vì vậy chọn cách làm không phải quyết định một lần.

### 14.1. Theo dõi kết quả và chi phí phối hợp

| Tín hiệu | Câu hỏi cần xem | Lưu ý |
| --- | --- | --- |
| **Increment/khả năng dùng được** | Đã giao hành vi sản phẩm nào thực sự hoạt động? | Không đếm prototype hoặc mã chưa tích hợp như Increment hoàn tất. |
| **Thời gian tới phản hồi** | Từ ý tưởng đến lúc học được điều quan trọng mất bao lâu? | Phản hồi nhanh nhưng từ sai đối tượng có thể gây hiểu lầm. |
| **Cycle time / work item age** | Các hạng mục bị chặn và chờ lâu ở đâu? | Thống nhất mốc Started/Finished. |
| **WIP và throughput** | Có quá nhiều việc dở hoặc quá ít việc hoàn tất? | Không xem số ticket là giá trị; phụ thuộc cách chia việc. |
| **Lỗi và rework** | Những sai lệch nào lặp lại, được phát hiện sớm hay muộn? | Tránh dùng số lỗi để quy trách nhiệm cá nhân. |
| **Thời gian chờ liên nhóm** | Hợp đồng, môi trường và quyết định bị chậm ở bước nào? | Tìm nguyên nhân toàn chuỗi giá trị, không chỉ trong từng team. |
| **Khả năng truy vết và phục hồi** | Có đủ bằng chứng để hiểu thay đổi và khôi phục sự cố? | Mức yêu cầu tăng theo criticality. |
| **Outcome người dùng** | Người dùng thực hiện tác vụ tốt hơn, rủi ro giảm không? | Kiểm tra dữ liệu nền và ảnh hưởng ngoại cảnh. |
| **Sức khỏe nhóm** | Có quá tải, gián đoạn hoặc sợ nêu vấn đề không? | Thông tin cần được sử dụng tôn trọng và bảo mật. |

### 14.2. Ví dụ phân tích kết quả mà không quy nhân quả vội

Một nhóm nhỏ có dữ liệu minh họa:

- Trước khi cải tiến, cycle time trung vị của các lát cắt tương tự là **9 ngày**.
- Sau khi dùng contract test và review sớm, trung vị là **6 ngày**.
- Số lần lỗi tích hợp được phát hiện sau khi bàn giao cũng giảm.

Đây có thể là tín hiệu tích cực, nhưng phải kiểm tra **loại/kích thước công việc, mức rủi ro, định nghĩa Done và quy mô nhóm có còn tương đương không**. Nếu giai đoạn sau toàn việc dễ hơn, không thể quy toàn bộ cải thiện cho phương pháp.

### 14.3. Dấu hiệu nên điều chỉnh cách làm

- Sản phẩm từ thử nghiệm chuyển sang xử lý giao dịch hoặc dữ liệu quan trọng.
- Số nhóm phối hợp tăng, hợp đồng API trở thành nguồn lỗi chính.
- Có thêm nghĩa vụ kiểm tra, báo cáo hoặc chứng nhận.
- Nhóm chuyển từ cùng địa điểm sang phân tán.
- Hạng mục thường bị chặn vì những quyết định không rõ người chịu trách nhiệm.
- Có nhiều lỗi sau phát hành dù throughput tăng.
- Người dùng chưa nhận được giá trị dù bảng công việc trông thông suốt.

Không phải mọi tín hiệu đều yêu cầu đổi “màu Crystal”. Đôi khi **chỉ một cải tiến nhỏ về test, vai trò quyết định hoặc chính sách tích hợp** đã đủ.

## 15. Quy trình thực hành để chọn và tinh chỉnh cách làm

### Bước 1 — Xác định sản phẩm và kết quả mong muốn

Nêu rõ người dùng, ranh giới sản phẩm, mục tiêu giá trị và phần khả năng cần giao. Tránh bắt đầu bằng câu “chúng ta phải dùng Crystal Orange” trước khi biết bài toán.

### Bước 2 — Đếm quy mô **phối hợp thực tế**

Ai phải trao đổi để tạo ra phần mềm đúng? Có một đội hay nhiều đội? Những quyết định nào cần cùng hiểu? Nhóm có phân tán hoặc phụ thuộc nhà cung cấp ngoài tổ chức không?

### Bước 3 — Đánh giá hậu quả của các kịch bản thất bại

Liệt kê điều có thể sai và ảnh hưởng tới người dùng, tiền, dữ liệu, vận hành hoặc tính mạng. Xác minh với người có thẩm quyền về nghiệp vụ, bảo mật, an toàn và pháp lý nếu cần. Đừng chỉ lấy “độ ưu tiên” hoặc doanh thu của tính năng làm criticality.

### Bước 4 — Xác định các thực hành cốt lõi

Giữ cơ hội nhận phản hồi sớm, giao phần mềm hoạt động, giao tiếp hiệu quả, an toàn để nêu vấn đề, tập trung và môi trường kỹ thuật hỗ trợ chất lượng.

### Bước 5 — Bổ sung phối hợp và kiểm chứng theo hai trục

Quy mô tăng thì thêm hợp đồng, chủ sở hữu và cơ chế phối hợp. Hậu quả tăng thì thêm quản lý rủi ro, kiểm thử, truy vết và kiểm soát. Những điều bổ sung phải có **lý do, người chịu trách nhiệm và bằng chứng**.

### Bước 6 — Thử phương pháp với một phần giá trị có thể giao

Chọn lát cắt nhỏ nhưng có nghĩa, áp dụng chính sách chất lượng, giao cho đối tượng kiểm chứng phù hợp. Nếu công việc chỉ là spike khám phá, mô tả trung thực kết quả học hỏi, không gọi là Increment chức năng khi chưa có khả năng sử dụng.

### Bước 7 — Kiểm tra và điều chỉnh

Dựa vào lỗi, phản hồi, thời gian chờ, WIP, phụ thuộc và cảm nhận của người trực tiếp làm. Nếu thêm một cuộc họp không giải quyết được vấn đề phối hợp, hãy thay hoặc bỏ nó. Nếu test hiện tại không phát hiện lỗi nghiêm trọng, cần tăng kiểm chứng, không giữ cách làm chỉ vì tên màu.

~~~mermaid
flowchart LR
    A["Mục tiêu & người dùng"] --> B["Quy mô phối hợp"]
    B --> C["Hậu quả khi thất bại"]
    C --> D["Chọn thực hành & kiểm soát"]
    D --> E["Giao lát cắt có kiểm chứng"]
    E --> F["Đo giá trị, flow và chất lượng"]
    F --> G["Reflective improvement"]
    G -. "Bối cảnh và rủi ro đổi" .-> B
~~~

## 16. Những phản mẫu thường gặp khi áp dụng Crystal

| Phản mẫu | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| **Chọn màu chỉ theo tổng nhân viên công ty** | Không phản ánh quy mô nhóm thực sự phải phối hợp. | Xác định ranh giới sản phẩm và số người phụ thuộc trực tiếp. |
| **Nhầm màu đậm là trình độ trưởng thành cao** | Thêm thủ tục không cần thiết cho đội nhỏ. | Chọn mức cấu trúc theo chi phí giao tiếp và rủi ro. |
| **Nhóm nhỏ thì không cần tài liệu/test** | Tri thức bị mất, lỗi khó phát hiện, rủi ro vận hành tăng. | Ghi điều quan trọng và dùng kiểm chứng phù hợp. |
| **Hậu quả thất bại cao nhưng vẫn dùng quy trình demo** | Không đủ bằng chứng an toàn hoặc chất lượng. | Quản lý rủi ro, tăng kiểm tra và tuân thủ chuẩn chuyên ngành. |
| **Càng nhiều người càng phải họp nhiều** | Chuyển ngữ cảnh tăng, không giảm lỗi hợp đồng. | Dùng tài liệu, test hợp đồng và kênh quyết định rõ. |
| **Coi feedback người dùng thay thế review kỹ thuật** | Tính năng được thích nhưng không đáng tin cậy. | Kết hợp outcome, acceptance criteria và kiểm thử chất lượng. |
| **Đếm story point hoặc ticket làm thước đo duy nhất** | Tối ưu số liệu, không thấy giá trị hoặc lỗi. | Đo Increment, outcome, flow và chất lượng. |
| **Không có quyền ưu tiên rõ** | Yêu cầu stakeholder mâu thuẫn khiến nhóm đổi hướng liên tục. | Có đầu mối chịu trách nhiệm giá trị và backlog order. |
| **Áp dụng nguyên kiểu làm việc cùng phòng cho nhóm phân tán** | Quyết định bị bỏ sót, phụ thuộc bị chặn. | Tạo kênh bất đồng bộ và ghi quyết định quan trọng. |
| **Chỉ giao prototype rồi gọi là đã giao giá trị** | Người dùng không thể sử dụng thật; rủi ro tích hợp đến muộn. | Phân biệt thử nghiệm khám phá và Increment đạt chuẩn. |
| **Đổi mọi thứ khi có một lỗi** | Tăng biến động, không biết thay đổi nào tạo tác dụng. | Thử cải tiến nhỏ, đo kết quả và kiểm soát rủi ro. |
| **Né quản lý rủi ro vì “Agile phải nhẹ”** | Có thể gây thiệt hại tài chính, riêng tư hoặc an toàn. | Giữ nguyên các nghĩa vụ bắt buộc, thích ứng hình thức thực hiện. |
| **Sao chép Crystal Clear như công thức cố định** | Bỏ qua khác biệt về criticality, đội ngũ và phụ thuộc. | Tùy biến trên bằng chứng và đánh giá định kỳ. |

## 17. Bài tập thực hành

### Bài tập 1 — Chọn cách làm theo hai trục

Xét bốn tình huống:

| Tình huống | Quy mô phối hợp | Hậu quả nếu lỗi |
| --- | --- | --- |
| A — Prototype bộ lọc khóa học với dữ liệu giả | 5 người | Chủ yếu bất tiện, dễ phục hồi. |
| B — Hệ thống thu học phí thật | 5 người | Có thể gây thiệt hại tài chính và rủi ro dữ liệu. |
| C — Trang cung cấp thông tin khóa học có nhiều nhóm biên tập/kỹ thuật | 35 người | Chủ yếu ảnh hưởng trải nghiệm và hiệu quả vận hành. |
| D — Nền tảng có nhiều nhóm xử lý giao dịch quan trọng | 35 người | Hậu quả tài chính và riêng tư nghiêm trọng. |

**Yêu cầu:** với mỗi tình huống, nêu những thực hành phối hợp và kiểm chứng tối thiểu. Có nên chọn một màu Crystal chỉ bằng số người không?

**Gợi ý đáp án:**

- **A:** giao tiếp gần, giao bản thử nhỏ thường xuyên, test cơ bản và phản hồi người dùng.
- **B:** dù quy mô nhỏ, cần tăng review, test giao dịch/đối soát, bảo mật, truy vết và khôi phục theo chính sách.
- **C:** làm rõ hợp đồng/đầu mối, nhịp tích hợp và cách truyền thông, tránh phê duyệt không cần thiết.
- **D:** cần **cả** điều phối liên nhóm và các kiểm soát chất lượng/rủi ro nghiêm ngặt.

Không thể suy phương pháp chỉ từ số người; phải đánh giá thêm hậu quả, phụ thuộc và các yêu cầu áp dụng.

### Bài tập 2 — Phân biệt criticality với priority

Một đội có hai việc:

1. Giao banner tuyển sinh trước sự kiện ngày mai.
2. Sửa khả năng ghi nhận thanh toán trùng ở chức năng ít được thay đổi nhưng đang có rủi ro thực.

**Câu hỏi:**

- Việc nào có tính cấp thiết theo lịch cao?
- Việc nào có thể có hậu quả lỗi nghiêm trọng?
- Có thể dùng duy nhất điểm giá trị tính năng để xếp mức kiểm chứng không?
- Nếu đang xảy ra sự cố thanh toán, ai cần được thông báo và áp dụng quy trình nào?

**Gợi ý:** banner có deadline rõ nhưng không tự động có criticality cao; lỗi thanh toán có thể gây tổn thất lớn và cần kiểm soát/ứng cứu phù hợp. Ưu tiên và criticality là **hai chiều quyết định khác nhau**; sự cố thực phải được xử lý theo chính sách.

### Bài tập 3 — Chọn thực hành Crystal Clear cho nhóm nhỏ

Một đội 6 người phát triển sản phẩm nội bộ với hậu quả lỗi thấp. Tuy nhiên họ:

- Chỉ tích hợp một lần mỗi tháng.
- Không có test tự động.
- Người dùng chỉ được xem demo sau ba tháng.
- Thành viên ngại báo khi ước lượng sai.

**Yêu cầu:** chọn bốn thay đổi gắn với các thuộc tính Crystal Clear, nêu bằng chứng để biết hiệu quả.

**Gợi ý:** tăng frequent integration và kiểm thử tự động, giao lát cắt nhỏ cho người dùng thường xuyên, tạo an toàn để lên tiếng, tổ chức reflective improvement với hành động cụ thể. Đo thời gian nhận phản hồi, lỗi tích hợp, work item age và số Increment có thể dùng.

### Bài tập 4 — Từ một nhóm thành ba nhóm

Một sản phẩm phát triển từ 7 người lên ba đội, tổng khoảng 27 người. Những vấn đề xuất hiện:

- API thay đổi nhưng không thông báo.
- Các nhóm dùng định nghĩa Done khác nhau.
- Một tính năng được gọi Done ở backend nhưng frontend vẫn chưa dùng được.
- Release chung bị chậm vì môi trường tích hợp.

**Yêu cầu:** đề xuất năm cơ chế phối hợp **có mục đích**, và nêu cơ chế nào có thể thay bằng tự động hóa.

**Gợi ý:** hợp đồng API + contract test; DoD chung cho luồng tích hợp; chủ sở hữu phụ thuộc; tích hợp sớm và môi trường ổn định; lịch/thông báo thay đổi; kiểm tra flow liên nhóm. Có thể tự động hóa nhiều test và kiểm tra schema thay vì tăng họp.

### Bài tập 5 — Điều chỉnh phương pháp khi hậu quả đổi

Một ứng dụng thử nghiệm miễn phí quyết định thêm **thanh toán và hoàn tiền**. Nhóm vẫn chỉ có 6 người, muốn giữ cách làm nhanh và giao tính năng từng phần.

**Câu hỏi:**

1. Những kịch bản lỗi mới cần được xem xét?
2. Những kiểm soát nào có thể bổ sung mà vẫn giữ feedback ngắn?
3. Khi nào cần chuyên gia hoặc quyết định ngoài quyền nhóm?
4. Vì sao “vẫn là Crystal Clear nên không cần audit” là lập luận không đúng?

**Gợi ý:** thêm rủi ro trùng giao dịch, đối soát, hoàn tiền, dữ liệu cá nhân và sự cố; dùng test/idempotency phù hợp, review, quan sát và rollback, tham vấn chủ sở hữu bảo mật/tài chính theo quy định. Số người ít không loại bỏ hậu quả của sai sót.

### Bài tập 6 — Phân tích quyết định chọn quy trình

Hai phương án cho nhóm 10 người phát triển nền tảng học:

- **Phương án X:** mọi thay đổi phải qua bốn hội đồng, kiểm thử tích hợp cuối quý; tổng cộng nhiều tài liệu nhưng phản hồi muộn.
- **Phương án Y:** hợp đồng API được kiểm thử tự động, review rủi ro theo tác động, CI thường xuyên, demo mỗi tuần, những thay đổi nhạy cảm có phê duyệt riêng.

Hãy phân tích:

- Cái nào có cơ chế giảm **chi phí phối hợp**?
- Cái nào cho phản hồi sớm hơn?
- Cơ chế nào bảo vệ hậu quả nghiêm trọng?
- Có cần kết hợp một số điểm của cả hai tùy lĩnh vực không?

**Gợi ý:** Y thường có khả năng cân bằng tốt hơn nếu các kiểm soát áp dụng được chứng minh là đủ. Nhưng không nên kết luận chỉ qua tên phương án; với hệ thống chịu quy định nghiêm ngặt, một số kiểm chứng/chứng nhận chính thức có thể bắt buộc và phải được tích hợp vào quy trình.

### Bài tập 7 — Lập phương án tinh chỉnh sau một tháng

Nhóm dùng cách làm Crystal nhẹ đã giao bốn Increment. Sau một tháng:

- Phản hồi người dùng đến sớm hơn.
- Cycle time trung vị giảm.
- Lỗi liên nhóm sau phát hành lại tăng.

Hãy viết một **thử nghiệm cải tiến nhỏ**, gồm giả thuyết, biện pháp, số đo và điều kiện dừng/điều chỉnh. Đừng tự kết luận rằng tốc độ cao nghĩa là phương pháp thành công toàn diện.

**Gợi ý:** giả thuyết lỗi đến từ thiếu contract test hoặc giao tiếp thay đổi API; thử thêm contract test và thông báo schema có chủ sở hữu. Theo dõi rework, lỗi production, thời gian review và cycle time. Giữ các chính sách bảo mật/chất lượng bắt buộc.

## 18. Checklist khi chọn Crystal hoặc điều chỉnh một cách làm Agile

### Hiểu sản phẩm và nhóm

- [ ] Đã xác định ranh giới sản phẩm, người dùng và mục tiêu giá trị.
- [ ] Đã phân biệt quy mô phối hợp thực tế với quy mô toàn công ty.
- [ ] Đã đánh giá hậu quả khi thất bại bằng kịch bản cụ thể.
- [ ] Đã phân biệt criticality với business priority và deadline.
- [ ] Đã xác minh những ràng buộc pháp lý, an toàn, bảo mật và tổ chức cần tuân thủ.
- [ ] Đã tính tới phân tán địa lý, kỹ năng, phụ thuộc và mức tiếp cận người hiểu nghiệp vụ.

### Chọn thực hành

- [ ] Có cách giao phần mềm hoạt động và nhận phản hồi đủ thường xuyên.
- [ ] Có cơ chế minh bạch rủi ro, trở ngại và quyền quyết định.
- [ ] Người trực tiếp làm có thể lên tiếng và xin hỗ trợ.
- [ ] Nhóm tập trung hoàn tất phần giá trị, không mở quá nhiều việc.
- [ ] Môi trường kỹ thuật có test, quản lý cấu hình và tích hợp phù hợp.
- [ ] Khi quy mô lớn, có hợp đồng, đầu mối phối hợp và thông báo thay đổi rõ.
- [ ] Khi criticality cao, có kiểm soát, review, truy vết và bằng chứng tương xứng.
- [ ] Quy định về DoD/hoàn tất và release được hiểu chung.
- [ ] Không bỏ yêu cầu bắt buộc chỉ vì chọn phương pháp “nhẹ”.

### Kiểm tra và cải tiến

- [ ] Theo dõi được Increment có thể dùng, phản hồi và kết quả người dùng.
- [ ] Nhìn thấy thời gian chờ, phụ thuộc, WIP và lỗi chất lượng.
- [ ] Có nhịp reflective improvement với hành động kiểm chứng được.
- [ ] Có điều kiện xem lại cách làm khi quy mô, đội ngũ hoặc hậu quả thay đổi.
- [ ] Những thủ tục bổ sung tạo giá trị bảo vệ hoặc giảm chi phí phối hợp thực tế.

Checklist hỗ trợ một cuộc trao đổi có căn cứ, không phải chứng chỉ “đã áp dụng Crystal”. Với hệ thống chịu rủi ro chuyên ngành, phải bổ sung đánh giá và kiểm chứng của người có thẩm quyền.

## 19. Tổng kết

**Crystal là họ phương pháp Agile** nhấn mạnh lựa chọn và điều chỉnh cách làm theo **quy mô nhóm cần phối hợp** và **mức hậu quả khi hệ thống thất bại**, đồng thời xem trọng con người, giao tiếp, giao sản phẩm thường xuyên, môi trường kỹ thuật đáng tin cậy và cải tiến liên tục.

**Crystal Clear** gợi ý những đặc tính cho nhóm nhỏ: frequent delivery, reflective improvement, osmotic communication, personal safety, focus, easy access to expert users và môi trường có test tự động/quản lý cấu hình/tích hợp thường xuyên. Khi số người tăng, cần rõ hơn về phối hợp và hợp đồng. Khi criticality tăng, cần tăng mức kiểm chứng, truy vết và bảo vệ chất lượng — **ngay cả khi nhóm vẫn nhỏ**.

Tên màu chỉ là phương tiện để suy nghĩ về hoàn cảnh, **không phải cấp bậc trưởng thành hoặc chứng nhận an toàn**. Phương pháp phù hợp là phương pháp giúp nhóm **giao giá trị có thể kiểm chứng, hạn chế rủi ro, phối hợp hiệu quả và thay đổi dựa trên phản hồi**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa ngắn |
| --- | --- |
| **Crystal** | Họ phương pháp phát triển phần mềm Agile gắn với Alistair Cockburn, nhấn mạnh thích ứng theo quy mô và hậu quả thất bại. |
| **Crystal Clear / Yellow / Orange / Red** | Một số tên biến thể Crystal, gợi ý mức phối hợp và cấu trúc cho các bối cảnh khác nhau. |
| **Team size** | Số người thực tế cần phối hợp để giao sản phẩm trong ranh giới đã chọn. |
| **Criticality** | Mức nghiêm trọng của hậu quả khi hệ thống thất bại trong bối cảnh sử dụng. |
| **C / D / E / L** | Các nhãn hậu quả minh họa: Comfort, Discretionary money, Essential money, Life. |
| **Frequent delivery** | Bàn giao phần mềm dùng được thường xuyên để nhận phản hồi và giảm rủi ro. |
| **Reflective improvement** | Định kỳ nhìn lại và thay đổi cách làm dựa trên kết quả quan sát. |
| **Osmotic communication** | Chia sẻ bối cảnh qua tương tác gần/tự nhiên, cần thích ứng với nhóm phân tán. |
| **Personal safety** | Khả năng lên tiếng, hỏi và báo rủi ro mà không sợ bị làm nhục hoặc trả đũa. |
| **Focus** | Tập trung vào các mục tiêu và phần việc quan trọng, giảm chuyển ngữ cảnh. |
| **Expert users** | Những người hiểu nhu cầu hoặc nghiệp vụ, có thể làm rõ và phản hồi sớm. |
| **Configuration management** | Quản lý phiên bản và trạng thái cấu hình để thay đổi có thể truy vết, tái hiện. |
| **Frequent integration / CI** | Tích hợp và kiểm tra thay đổi thường xuyên nhằm phát hiện lỗi sớm. |
| **Contract test** | Kiểm tra một giao diện/hợp đồng giao tiếp giữa các thành phần/dịch vụ. |
| **Increment** | Phần tăng trưởng sản phẩm tích hợp và có thể sử dụng, đáp ứng chuẩn hoàn tất phù hợp. |
| **Definition of Done (DoD)** | Cam kết chất lượng của Increment trong Scrum; cũng gợi ý minh bạch hoàn tất cho nhóm khác. |
| **WIP / cycle time** | Các số đo công việc đang dở và thời gian từ bắt đầu tới hoàn tất theo ranh giới xác định. |
| **Tailoring** | Tinh chỉnh phương pháp, thực hành và kiểm soát cho bối cảnh thực tế. |
| **Assurance** | Những hoạt động/bằng chứng nhằm tăng độ tin cậy rằng rủi ro và yêu cầu quan trọng đã được kiểm soát. |
