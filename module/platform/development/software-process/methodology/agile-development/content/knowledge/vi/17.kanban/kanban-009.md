# Phát hiện nút thắt và giảm thời gian chờ

Một nhóm phát triển có thể có nhiều thành viên bận rộn, bảng công việc đầy thẻ và hàng chục pull request đang mở, nhưng người dùng vẫn phải chờ nhiều tuần để nhận một thay đổi nhỏ. Vấn đề không nhất thiết là lập trình viên viết mã chậm. Một story có thể được triển khai trong một ngày rồi chờ review ba ngày, chờ môi trường kiểm thử hai ngày, tiếp tục chờ duyệt triển khai bốn ngày. **Tổng thời gian giao giá trị thường bị chi phối bởi thời gian nằm trong hàng đợi, không chỉ thời gian thực sự xử lý.**

**Kanban** giúp nhìn công việc như một **dòng chảy từ lúc được bắt đầu đến khi hoàn tất**. Thay vì chỉ hỏi “Ai đang làm gì?”, nhóm quan sát **công việc đang nằm ở đâu, có bao nhiêu việc chưa xong, tuổi của từng việc, nơi hàng đợi tích tụ và điều gì cản việc hoàn tất**. Nhờ minh bạch dòng chảy, nhóm có thể thử các cải tiến nhỏ, giới hạn công việc đang thực hiện (*Work in Progress — WIP*) và giảm thời gian người dùng phải chờ.

Bài thuộc chương **Kanban** của module **AGILE_DEVELOPMENT**. Nội dung kết nối giá trị Agile — giao sản phẩm tăng dần, nhận phản hồi sớm, cải tiến liên tục — với user story, backlog, phối hợp Scrum/Kanban, thực hành kỹ thuật XP và đo lường dòng công việc. Trọng tâm là **phát hiện đúng nút thắt, xử lý nguyên nhân và kiểm chứng thời gian chờ có thực sự giảm mà chất lượng vẫn được giữ**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **nút thắt**, **hàng đợi**, **công việc bị chặn** và **thời gian xử lý thực tế**.
2. Trực quan hóa các bước của quy trình bằng bảng Kanban với chính sách chuyển trạng thái rõ ràng.
3. Dùng **WIP, throughput, cycle time, work item age, lead time** và thông tin công việc bị chặn để phát hiện dấu hiệu dòng chảy kém.
4. Hiểu ý nghĩa và giới hạn của **Cumulative Flow Diagram (CFD)**, biểu đồ phân bố cycle time và các chỉ báo thời gian chờ.
5. Giải thích vì sao **tăng số việc bắt đầu không đồng nghĩa tăng số việc hoàn tất**, đặc biệt khi nút thắt đang quá tải.
6. Đề xuất cải tiến qua giới hạn WIP, làm việc kéo (*pull*), chia lát cắt nhỏ, phối hợp review/kiểm thử và tháo gỡ phụ thuộc.
7. Giữ các yêu cầu **chất lượng, bảo mật, Definition of Done** và giá trị người dùng trong lúc tăng tốc dòng chảy.
8. Thiết kế thử nghiệm có số liệu trước/sau và biết khi nào cần điều chỉnh hoặc bỏ giải pháp đã thử.

## 2. Nút thắt trong luồng công việc là gì?

**Nút thắt** (*bottleneck*) là một bước, một loại năng lực hoặc một ràng buộc đang giới hạn khả năng công việc đi qua toàn bộ hệ thống. Khi nhu cầu đưa việc tới một bước thường xuyên cao hơn năng lực bước đó có thể xử lý, **hàng đợi trước bước ấy có xu hướng tăng**.

Ví dụ: ba Developers hoàn tất khoảng tám thay đổi mỗi tuần, nhưng chỉ một người có thể review và xác nhận sáu thay đổi mỗi tuần. Nếu các yêu cầu đến đều đặn và không có cơ chế điều phối, hàng đợi review có thể tích tụ. Dù Developers viết code nhanh hơn nữa, **số thay đổi được giao hoàn chỉnh vẫn bị giới hạn bởi năng lực review hoặc một ràng buộc khác phía sau**.

### 2.1. Bốn khái niệm dễ lẫn

| Khái niệm | Dấu hiệu chính | Ví dụ |
| --- | --- | --- |
| **Nút thắt** (*bottleneck*) | Một bước hoặc ràng buộc giới hạn throughput toàn hệ thống trong bối cảnh hiện tại | Review luôn nhận việc nhanh hơn khả năng xử lý |
| **Hàng đợi** (*queue*) | Công việc đã sẵn sàng nhưng chờ bước tiếp theo nhận xử lý | Sáu pull request đang chờ người review |
| **Công việc bị chặn** (*blocked item*) | Hạng mục không thể tiến lên do điều kiện chưa được đáp ứng | Đối tác chưa cung cấp token truy cập môi trường thử |
| **Thời gian xử lý thực tế** (*active/touch time*) | Khoảng người hoặc máy thực sự thực hiện hoạt động liên quan | Người review đọc thay đổi và kiểm tra trong 40 phút |

Một hàng đợi dài **là tín hiệu**, chưa chắc đã chứng minh nguyên nhân là thiếu nhân sự ở bước đó. Có thể đầu vào đến theo đợt, hạng mục quá lớn, chính sách “chỉ review cuối ngày”, kiểm thử thường xuyên thất bại hoặc quy trình phê duyệt không rõ. Cần kiểm tra **tình hình qua thời gian** và cách bước đó vận hành.

### 2.2. Nút thắt có thể dịch chuyển

Sau khi tự động hóa kiểm thử, hàng đợi “Chờ kiểm thử” có thể giảm nhưng “Chờ triển khai” lại tăng. Đây không phải bằng chứng cải tiến thất bại: nút thắt có thể đã chuyển tới công đoạn khác. Nhóm cần đo **lead time/cycle time tổng thể và giá trị được giao**, thay vì chỉ tuyên bố thành công vì một cột đã trống.

**Mục tiêu không phải giữ tất cả mọi người bận tối đa.** Mục tiêu là làm cho **công việc quan trọng được hoàn tất đúng chất lượng và tới tay người dùng sớm hơn**.

## 3. Trực quan hóa dòng công việc thật, không chỉ danh sách nhiệm vụ

Bảng Kanban hữu ích khi thể hiện các bước **thực sự tồn tại** trong công việc, kể cả nơi chờ và các phụ thuộc. Không nên thiết kế bảng đẹp nhưng che phần lớn thời gian trong trạng thái chung “In Progress”.

### 3.1. Ví dụ luồng phát triển tính năng đăng ký workshop

~~~mermaid
flowchart LR
    A["Backlog / Đã chọn ưu tiên"] --> B["Sẵn sàng bắt đầu"]
    B --> C["Đang phát triển"]
    C --> D["Chờ review"]
    D --> E["Đang review"]
    E --> F["Chờ kiểm thử"]
    F --> G["Đang kiểm thử"]
    G --> H["Sẵn sàng triển khai"]
    H --> I["Hoàn tất theo chính sách Done"]
    E -->|"Cần sửa"| C
    G -->|"Phát hiện lỗi"| C
~~~

Bảng có thể gộp hoặc tách cột tùy thực tế. Nếu nhóm dùng review và kiểm thử liên tục ngay trong triển khai, việc tách mọi hoạt động thành một cột riêng có thể không cần thiết. Tuy nhiên, khi **thời gian chờ rất lớn**, phân biệt “Chờ review” và “Đang review” giúp nhìn rõ vấn đề thay vì đổ lỗi chung cho “review chậm”.

### 3.2. Các trạng thái cần chính sách rõ ràng

| Trạng thái | Điều kiện vào | Điều kiện ra | Cần quan sát |
| --- | --- | --- | --- |
| **Sẵn sàng** | Hạng mục có mục đích, tiêu chí chấp nhận và phụ thuộc đủ hiểu | Có năng lực để kéo bắt đầu | Số việc tồn và tuổi chờ trước khi bắt đầu |
| **Đang phát triển** | Nhóm chủ động bắt đầu xử lý, nằm trong giới hạn WIP | Mã và kiểm tra cần thiết sẵn sàng review | Tuổi hạng mục, mức phân tán, lỗi hoặc phụ thuộc |
| **Chờ review** | Thay đổi đã đủ điều kiện được review | Reviewer nhận và bắt đầu xử lý | Độ dài hàng đợi, tuổi pull request |
| **Đang review** | Có người thực sự xem xét | Chấp thuận hoặc yêu cầu sửa với phản hồi rõ | Thời gian xử lý, vòng lặp làm lại |
| **Chờ/đang kiểm thử** | Bản tích hợp có thể kiểm chứng | Đạt hoặc không đạt tiêu chí đã thống nhất | Lỗi, hàng đợi môi trường, mức tái kiểm thử |
| **Hoàn tất** | Đạt chính sách hoàn thành/DoD của phạm vi công việc | Công việc đã được ghi nhận đúng trạng thái | Increment có thực sự sẵn sàng tạo giá trị? |

**Không được đánh dấu Done chỉ để giảm WIP trên bảng.** Nếu tiêu chuẩn yêu cầu tích hợp, kiểm thử, kiểm tra quyền và cập nhật tài liệu vận hành, những điều đó vẫn phải được đáp ứng.

### 3.3. Cần phân biệt “thẻ” và “lát cắt giá trị”

Nếu nhóm chia một user story thành năm thẻ “viết giao diện”, “viết API”, “thêm repository”, “viết test”, “merge”, bảng có thể cho thấy throughput cao mà chưa có phần mềm dùng được. Nên ưu tiên những lát cắt dọc như **“Học viên xem được workshop còn chỗ”** hoặc **“Học viên đăng ký chỗ hợp lệ và nhận xác nhận đúng”**, đủ điều kiện hoàn tất về chất lượng.

Thẻ kỹ thuật vẫn có thể hữu ích cho phối hợp nội bộ, nhưng **phải biết đang đo loại hạng mục nào và tại ranh giới nào**.

## 4. Đo lường dòng công việc để phát hiện điểm chờ

Nhiều chỉ số của Kanban bổ sung cho nhau. Không chỉ số nào đủ để chẩn đoán một nút thắt nếu tách khỏi bối cảnh.

| Chỉ số | Cách hiểu | Giúp phát hiện | Giới hạn |
| --- | --- | --- | --- |
| **WIP** | Số hạng mục đã bắt đầu nhưng chưa hoàn tất, theo ranh giới quy trình | Tắc nghẽn, nhiều việc cùng mở, áp lực lên bước sau | WIP lớn chưa tự nói rõ hàng đợi xuất hiện ở đâu |
| **Throughput** | Số hạng mục hoàn tất trong một khoảng thời gian | Năng lực hoàn tất thực tế và biến động | Đếm hạng mục không giống nhau có thể gây hiểu sai |
| **Cycle time** | Thời gian từ lúc bắt đầu xử lý tới hoàn tất theo chính sách đo | Tốc độ dòng chảy của hạng mục hoàn tất | Không cho biết ngay hạng mục đang mở bị kẹt bao lâu |
| **Work item age** | Tuổi của hạng mục đang thực hiện nhưng chưa Done | Phát hiện hạng mục có nguy cơ kéo dài trước khi hoàn tất | Cần so với công việc cùng loại và chính sách đo |
| **Lead time** | Thời gian từ mốc khách hàng/nhóm chấp nhận nhu cầu tới mốc giao đã thống nhất | Mức chờ tổng thể nhìn từ bên yêu cầu | Điểm bắt đầu khác nhau sẽ làm số liệu khác nhau |
| **Blocked time** | Phần thời gian hạng mục không thể tiến lên do trở ngại được ghi nhận | Phụ thuộc môi trường, quyền, API, phê duyệt | Không bao gồm mọi kiểu chờ nếu chỉ gắn nhãn “blocked” khi có sự cố rõ |
| **Queue time** | Thời gian hạng mục chờ trước khi có người hoặc công đoạn nhận xử lý | Hàng đợi review, kiểm thử, triển khai | Cần bảng có ranh giới trạng thái đủ rõ |
| **Flow efficiency** | Tỷ lệ thời gian chủ động xử lý so với thời gian đi qua quy trình theo cùng cách đo | Nhìn thấy tỷ trọng chờ lớn | Khó thu thập và định nghĩa touch time nhất quán; không phải KPI tuyệt đối |

### 4.1. Thống nhất điểm đầu và điểm cuối trước khi tính

Giả sử story được yêu cầu ngày 1, vào trạng thái “Đang phát triển” ngày 6 và đạt Done ngày 13:

- Nếu **lead time** tính từ ngày 1 tới ngày 13, con số bao gồm thời gian chờ trước khi nhóm bắt đầu.
- Nếu **cycle time** tính từ ngày 6 tới ngày 13, nó chỉ phản ánh phần thời gian story đi qua luồng đang làm.

Đừng so hai nhóm hoặc hai quý nếu một bên tính Done khi merge code, bên còn lại chỉ tính Done khi đạt toàn bộ tiêu chuẩn triển khai. **Cùng một tên chỉ số không bảo đảm cùng một định nghĩa.**

### 4.2. Phân biệt thời gian chờ, thời gian làm và thời gian lịch

Một item có thể mất 2 ngày để xử lý tích cực nhưng chờ thêm 7 ngày trong các hàng đợi. Nếu đo trên ngày làm việc, phải nói rõ cách loại trừ cuối tuần, ngày nghỉ, giờ ngoài ca và các bước diễn ra song song. Nếu đo theo thời gian lịch 24/7, cả tử số và mẫu số phải dùng cùng quy tắc.

Không nên lấy **tổng giờ công của nhiều người** rồi chia trực tiếp cho **số ngày lịch của item** để tuyên bố flow efficiency: các đơn vị và tính song song không tương thích.

## 5. Ví dụ phân rã thời gian chờ của một user story

Giả sử nhóm theo dõi một story “Học viên tự hủy đăng ký workshop”. Bảng sau dùng **ngày làm việc tương đương theo thời gian trôi qua**, với hoạt động tuần tự và không chồng lấn để dễ minh họa; đây không phải dữ liệu thực tế của một tổ chức.

| Công đoạn | Thời gian xử lý tích cực | Thời gian chờ |
| --- | ---: | ---: |
| Làm rõ yêu cầu đã được kéo vào luồng | 0,5 ngày | 0,5 ngày |
| Phát triển và kiểm tra ban đầu | 1,5 ngày | 0,5 ngày |
| Code review | 0,25 ngày | 3 ngày |
| Kiểm thử tích hợp | 0,5 ngày | 2 ngày |
| Triển khai và xác minh | 0,25 ngày | 1 ngày |
| **Tổng** | **3 ngày** | **7 ngày** |

Trong mô hình minh họa này:

\[
\text{Cycle time}=3+7=10\ \text{ngày làm việc}.
\]

\[
\text{Flow efficiency}=\frac{3}{10}\times100\%=30\%.
\]

Nghĩa là **70% thời gian đi qua luồng là thời gian chờ** theo cách đo đã định nghĩa. Một nhà quản lý chỉ yêu cầu “code nhanh hơn 20%” có thể chỉ giảm được 0,3 ngày nếu phần phát triển tích cực là 1,5 ngày, trong khi giải quyết thời gian chờ review ba ngày có thể đem lại thay đổi lớn hơn.

### 5.1. Không nên diễn giải con số 30% thế nào?

**30% không phải mức kém hay mức chuẩn tuyệt đối cho mọi loại công việc.** Có những khoảng chờ cần thiết để kiểm soát chất lượng, an toàn, xử lý bằng chứng hay đồng bộ hệ thống. Vấn đề là **chờ đợi đó có cần thiết, tương xứng với rủi ro và có thể giảm mà không tạo hại khác không?**

Ví dụ, việc review bảo mật có thể cần chuyên gia. Giảm chờ có thể đến từ **gọi chuyên gia sớm hơn, chia sẻ kiến thức hoặc chuẩn hóa thông tin review**, không phải bỏ bước review.

### 5.2. Phân biệt một item chậm với nút thắt của toàn hệ thống

Một story gặp sự cố hiếm và chờ review ba ngày chưa chứng minh **mọi story đều bị nghẽn review**. Hãy kiểm tra một nhóm hạng mục đủ đại diện:

- Bao nhiêu item chờ ở bước review?
- Thời gian chờ điển hình và phần đuôi phân phối là bao nhiêu?
- Hàng đợi có tăng trong nhiều ngày hoặc nhiều tuần?
- Năng lực xử lý review so với dòng công việc đến ra sao?
- Có loại thay đổi nào đặc biệt hay bị chặn?

**Một trường hợp là tín hiệu để điều tra; xu hướng và nguyên nhân mới là cơ sở để can thiệp ở cấp hệ thống.**

## 6. Năm dấu hiệu phổ biến của nút thắt

| Dấu hiệu quan sát | Nguyên nhân có thể | Việc kiểm tra tiếp |
| --- | --- | --- |
| **Thẻ tích tụ trước một bước** | Bước sau xử lý chậm hơn tốc độ đến | Xem số việc đến/đi qua bước, chính sách chọn việc, độ lớn item |
| **Work item age tăng** | Việc bị chặn, quá lớn hoặc liên tục bị chen ngang | Xem nhật ký chờ, người có thể hỗ trợ, WIP và phụ thuộc |
| **Throughput không tăng dù số việc bắt đầu tăng** | Nút thắt toàn hệ thống chưa được cải thiện | So sánh tốc độ bắt đầu và hoàn tất, nơi WIP tích tụ |
| **Nhiều vòng sửa sau review/kiểm thử** | Tiêu chí không rõ, kiểm tra muộn, chất lượng đầu vào thấp | Phân tích loại lỗi, phản hồi review, thời điểm kiểm thử |
| **Cycle time dao động rất lớn giữa các item tương tự** | Chính sách ưu tiên bị ngắt, phụ thuộc thất thường, batching | Phân nhóm theo loại việc, xem item ngoại lệ và các thời điểm chờ |

Các dấu hiệu có thể cùng xuất hiện. Ví dụ một hàng đợi review dài làm work item age tăng; để kịp lịch, nhóm mở thêm story mới, khiến WIP tiếp tục tăng. **Phản ứng đúng thường là hỗ trợ hoàn tất việc cũ trước khi bắt đầu thêm việc mới.**

## 7. Cumulative Flow Diagram: nhìn hàng đợi hình thành qua thời gian

**Cumulative Flow Diagram (CFD)** là biểu đồ vùng xếp chồng thể hiện sự phân bố công việc qua các trạng thái theo thời gian. Mỗi dải màu đại diện cho một trạng thái; **độ dày dải** giúp quan sát số hạng mục ở trạng thái đó tại từng thời điểm, tùy cách hệ thống ghi dữ liệu.

### 7.1. Ví dụ quan sát số thẻ tại các công đoạn

Bảng minh họa dưới đây là **số hạng mục đang nằm ở mỗi trạng thái tại thời điểm chụp**, không phải một biểu đồ CFD hoàn chỉnh. Nó giúp hiểu vì sao nhóm cần nhìn sự thay đổi theo nhiều ngày.

| Ngày | Đang phát triển | Chờ review | Đang review | Chờ kiểm thử | Đang kiểm thử |
| --- | ---: | ---: | ---: | ---: | ---: |
| Thứ Hai | 3 | 2 | 1 | 1 | 1 |
| Thứ Ba | 3 | 4 | 1 | 1 | 1 |
| Thứ Tư | 3 | 6 | 1 | 1 | 1 |
| Thứ Năm | 3 | 8 | 1 | 2 | 1 |
| Thứ Sáu | 3 | 9 | 1 | 2 | 1 |

“Chờ review” tăng từ 2 lên 9, trong khi “Đang review” luôn quanh 1. Đây là **dấu hiệu mạnh** rằng công việc đến vùng review nhanh hơn khả năng chuyển qua trong giai đoạn này, hoặc có chính sách khiến việc chờ bị tích tụ. Nhóm cần xem lý do: chỉ một người có quyền review, PR quá lớn, thiếu thông tin hay người review liên tục bị chuyển sang việc khẩn?

### 7.2. Cách đọc một CFD thực sự

Trên CFD:

1. **Các dải trạng thái rộng dần:** Nhiều công việc tích tụ ở trạng thái đó; có thể là hàng đợi hoặc ràng buộc.
2. **Khoảng cách giữa các đường ranh giới tăng:** WIP ở phần quy trình tương ứng có thể tăng.
3. **Đường đầu ra đi ngang hoặc tăng chậm:** Số công việc hoàn tất ít trong thời gian quan sát.
4. **Khoảng cách theo chiều ngang dài hơn:** Có thể chỉ thời gian đi qua các trạng thái tăng, tùy cách xác định ranh giới.
5. **Các thay đổi đột ngột:** Cần kiểm tra batch lớn, thay đổi chính sách hoặc việc chuyển trạng thái trên công cụ.

CFD **không tự chỉ ra nguyên nhân gốc**. Một dải rộng hơn có thể do một đợt yêu cầu lớn ngắn hạn, lỗi nhập dữ liệu, công việc khác kích thước hoặc thiếu năng lực. Nên kết hợp board review, work item age, cycle time và trao đổi với người trực tiếp làm việc.

### 7.3. Không “sửa” CFD bằng cách đổi nhãn

Nếu nhóm dời mọi thẻ “Chờ review” sang “Đang review” để trông bớt tắc, luồng thực tế không cải thiện. Một chính sách tốt phải có **điều kiện vào/ra có thể quan sát**: thẻ chỉ được xem là đang review khi công việc review thực sự bắt đầu.

## 8. Little's Law và mối quan hệ giữa WIP, throughput, cycle time

Một quan hệ quan trọng trong lý thuyết hàng đợi, áp dụng cho **hệ thống ổn định dưới những điều kiện phù hợp**, là **Little's Law**:

\[
\overline{\text{WIP}}
=\overline{\text{Throughput}}\times\overline{\text{Cycle time}}.
\]

Nếu throughput đo bằng **hạng mục/tuần**, cycle time đo bằng **tuần/hạng mục**, thì WIP có đơn vị là **hạng mục**.

### Ví dụ minh họa

Giả sử luồng công việc trong một giai đoạn đủ ổn định có:

- Throughput trung bình: **5 hạng mục/tuần**.
- Cycle time trung bình: **2 tuần/hạng mục**.

Khi đó WIP trung bình tương ứng:

\[
5\times2=10\ \text{hạng mục}.
\]

Nếu nhóm tăng WIP lên **15 hạng mục** nhưng throughput toàn hệ thống **vẫn quanh 5 hạng mục/tuần**, quan hệ này gợi ý cycle time trung bình có thể lên quanh:

\[
15/5=3\ \text{tuần/hạng mục},
\]

**nếu hệ thống tiếp tục đáp ứng những giả định ổn định của quan hệ**. Đây là ví dụ lý giải mối liên hệ, **không phải lời bảo đảm rằng áp một giới hạn WIP sẽ tức khắc tạo chính xác một cycle time nhất định**.

### 8.1. Những điều kiện phải nhớ

- Đo WIP, throughput và cycle time **trên cùng ranh giới hệ thống**.
- Dùng cùng loại công việc hoặc đủ hiểu sự khác biệt.
- Trong khoảng quan sát dài thích hợp, số việc đến và hoàn tất không thể lệch nhau mãi nếu xem hệ thống là ổn định.
- Không áp công thức cho một Sprint biến động mạnh, một dự án mới chưa có luồng ổn định, hoặc một bảng có hàng nghìn việc bị mở rồi không bao giờ đóng.
- Trường hợp work item age tăng bất thường hoặc hàng đợi liên tục phình ra là dấu hiệu cần điều tra giả định ổn định.

Ý nghĩa quan trọng của Little's Law là **giảm công việc đang dang dở có thể cải thiện thời gian hoàn tất khi throughput được duy trì**, không phải cứ nhân một công thức là có thể bỏ quản lý rủi ro và quy trình.

## 9. Vì sao mức sử dụng năng lực quá cao thường làm thời gian chờ tăng?

Trực giác quản lý thường là “người review còn 10% thời gian thì cứ nhận thêm việc”. Nhưng hàng đợi chịu ảnh hưởng của **biến động về thời gian xử lý và thời điểm công việc đến**. Khi một bước luôn gần kín năng lực, ngay cả một đợt đến dồn hoặc một yêu cầu khó bất ngờ cũng có thể làm hàng đợi kéo dài.

Ví dụ:

- Reviewer có thể xử lý trung bình năm thay đổi/tuần.
- Trung bình cũng có năm thay đổi tới mỗi tuần, nhưng có tuần tới tám và tuần khác chỉ hai.
- Khi công việc dồn vào những ngày đầu, backlog review tăng; các thay đổi nhỏ có thể phải chờ lâu dù người review làm liên tục.

Vì vậy, mục tiêu **100% bận rộn mọi lúc** có thể xung đột với mục tiêu **thời gian phản hồi ngắn và ổn định**.

### 9.1. Ba cách cải thiện thay vì chỉ tăng áp lực

1. **Giảm đợt vào quá lớn:** Chia PR nhỏ, tích hợp thường xuyên, kéo việc phù hợp năng lực bước sau.
2. **Tăng khả năng xử lý nơi thật sự giới hạn:** Chia sẻ kiến thức review, tự động hóa kiểm tra lặp lại, ưu tiên phản hồi sớm.
3. **Giảm biến động và công việc làm lại:** Làm rõ tiêu chí chấp nhận, review sớm, kiểm thử tự động phù hợp, xử lý lỗi ngay.

Không cần giữ mọi người nhàn rỗi; cần **mức dự phòng phù hợp để hấp thụ biến động**, nhất là ở bước khan hiếm hoặc có nhiều yêu cầu khẩn.

## 10. Phân tích nguyên nhân gốc thay vì chữa triệu chứng

Thấy chín PR đang chờ review, phản ứng dễ nhất là “thêm reviewer”. Nhưng nếu nguyên nhân thực là PR quá lớn, thiếu tiêu chí, hoặc review phát hiện nhiều lỗi phải làm lại, chỉ thêm người có thể không cải thiện lâu dài.

### 10.1. Khung hỏi năm lần “vì sao?” mang tính gợi mở

Ví dụ:

| Câu hỏi | Phát hiện giả định |
| --- | --- |
| Vì sao story mất nhiều thời gian? | Chờ code review gần bốn ngày |
| Vì sao chờ review lâu? | Một số PR lớn chỉ được một người có thể duyệt |
| Vì sao chỉ một người review? | Những thành viên còn lại chưa hiểu ranh giới nghiệp vụ và kiểm tra liên quan |
| Vì sao kiến thức tập trung? | Các thay đổi thường được làm một mình rồi gửi review cuối Sprint |
| Vì sao review dồn cuối Sprint? | Nhóm mở nhiều hạng mục đồng thời và không có chính sách ưu tiên hoàn tất |

Đây **không phải một chuỗi nguyên nhân chắc chắn**. Nhóm cần xác minh bằng dữ liệu PR, buổi quan sát quy trình, trao đổi với người thực hiện và các loại thay đổi khác nhau.

### 10.2. Cẩn trọng với việc tối ưu cục bộ

Nếu Development hoàn tất nhiều item hơn nhưng Review vẫn giới hạn toàn hệ thống, hàng đợi sẽ lớn hơn. Nếu Review được tối ưu nhưng kiểm thử trở thành nút thắt, tổng cycle time có thể không giảm nhiều.

Một thứ tự xem xét hữu ích:

1. Nhìn **kết quả toàn hệ thống** đang bị hạn chế ở đâu.
2. Ưu tiên cải thiện điểm đang giới hạn khả năng hoàn tất.
3. Điều chỉnh các bước trước để **không đẩy thêm WIP** tới bước tắc.
4. Thử nâng năng lực hoặc thay chính sách của điểm tắc.
5. Đo lại kết quả; khi nút thắt chuyển, tiếp tục kiểm tra.

Đây là tư duy tương tự **Theory of Constraints**, nhưng nhóm không cần triển khai một phương pháp riêng đầy đủ để bắt đầu thực hành. Quan trọng là tránh nhầm **tối đa hóa sản lượng của từng công đoạn** với **tối đa hóa giá trị được giao xuyên suốt**.

## 11. Giảm thời gian chờ bằng giới hạn WIP

**WIP limit** là giới hạn số công việc đang thực hiện trong một phần hoặc toàn bộ luồng theo chính sách đã thống nhất. Mục đích không phải làm chậm mọi người một cách máy móc; nó tạo tín hiệu để nhóm **hoàn tất, hỗ trợ nhau hoặc gỡ trở ngại trước khi mở thêm việc**.

### 11.1. Ví dụ chính sách WIP minh họa

| Trạng thái | WIP limit đề xuất để thử | Ý nghĩa |
| --- | ---: | --- |
| Đang phát triển | 3 | Không mở vô hạn story mới khi nhóm chưa hoàn tất việc cũ |
| Chờ + đang review | 2 | Khi đầy, ưu tiên giúp review xong hoặc gỡ nguyên nhân chờ |
| Chờ + đang kiểm thử | 2 | Đưa kiểm chứng gần với triển khai, tránh dồn cuối kỳ |
| Tổng vùng đang làm | 6 | Theo dõi toàn bộ việc dang dở thay vì chỉ giới hạn riêng từng cột |

**Những con số trong bảng chỉ là điểm khởi đầu cho thử nghiệm**, không phải chuẩn của Kanban. Một bảng dùng giới hạn vừa theo cột vừa toàn luồng cần tránh chính sách mâu thuẫn; thực tế nhóm phải thống nhất **ranh giới WIP**, cách xử lý trường hợp vượt giới hạn và cách đo kết quả.

### 11.2. Khi đạt giới hạn thì làm gì?

Ví dụ “Đang phát triển” đã có ba hạng mục theo giới hạn ba. Một Developer vừa hoàn tất phần code của mình:

- Không tự động kéo hạng mục thứ tư nếu làm vậy khiến WIP tăng mà không có năng lực hoàn tất.
- Hỏi “Việc nào gần Done nhất và có thể giúp đưa tới Done?”
- Hỗ trợ review, viết kiểm thử, giải quyết trở ngại hoặc chia sẻ kiến thức theo kỹ năng/quy định phù hợp.
- Nếu thực sự không thể hỗ trợ vì rào cản kỹ năng hoặc quyền, ghi rõ vấn đề và đề xuất cải tiến dài hạn.

**Giới hạn WIP là chính sách quản lý dòng chảy, không phải lệnh bắt người không có chuyên môn review an toàn phức tạp hoặc ngồi không vô ích.** Khi có ngoại lệ hợp lý, nhóm cần định nghĩa cách xử lý và ghi nhận.

### 11.3. Đừng làm giảm WIP bằng cách giấu việc

Nếu một item đang chờ nhà cung cấp nhưng bị chuyển về “Backlog” chỉ để bảng bớt đỏ, dữ liệu WIP và tuổi công việc sẽ bị bóp méo. Cần quy tắc xử lý công việc bị chặn và quyết định dừng/hủy thật sự, không đổi trạng thái tượng trưng.

## 12. Từ push sang pull: chỉ bắt đầu khi hệ thống có khả năng tiếp nhận

Trong hệ thống **push**, công việc được đẩy vào một bước ngay khi công đoạn trước hoàn tất, bất kể bước sau có khả năng xử lý hay không. Trong hệ thống **pull**, một bước chỉ nhận việc mới **khi có năng lực và thỏa mãn chính sách kéo việc**.

### Ví dụ

Nhóm có năm pull request “sẵn sàng review” nhưng người review đang xử lý hai thay đổi lớn. Nếu Developers tiếp tục tạo PR mới để “không ai rảnh”, số item chờ có thể tăng. Một cách tiếp cận pull là:

1. Không mở thêm nhiều hạng mục mới khi hàng đợi review đã quá giới hạn.
2. Ưu tiên hoàn tất và kiểm chứng những thay đổi gần Done.
3. Hỗ trợ reviewer bằng kiểm tra tự động, phân tách PR nhỏ hoặc chia sẻ kiến thức.
4. Chỉ kéo thêm item khi có khả năng đưa nó xuyên qua quy trình mà không tạo hàng đợi không kiểm soát.

Chính sách pull cần kết hợp **thứ tự backlog theo giá trị/rủi ro**, không chỉ làm item nào nhỏ nhất cho dễ đóng. Một lỗi dữ liệu nghiêm trọng vẫn có thể cần được ưu tiên cao hơn thay đổi giao diện đơn giản.

## 13. Những biện pháp giảm chờ theo nguyên nhân

| Nguyên nhân đã xác minh | Biện pháp có thể thử | Bằng chứng cần quan sát |
| --- | --- | --- |
| **Review tích tụ do PR lớn** | Chia thay đổi nhỏ, review sớm, quy tắc mô tả PR rõ | Tuổi PR, số vòng review, lỗi sau tích hợp |
| **Chỉ một người có thể review** | Pairing, mentoring, chia sẻ tri thức, đồng thuận quyền duyệt | Số người đủ năng lực, độ trễ chờ, chất lượng review |
| **Kiểm thử dồn cuối Sprint** | Kiểm thử theo lát cắt, tự động hóa phù hợp, phối hợp Developers/QA từ sớm | WIP ở chờ kiểm thử, cycle time, lỗi sau phát hành |
| **Môi trường kiểm thử tranh chấp** | Cấp môi trường theo nhu cầu, thiết lập dữ liệu thử lặp lại được, ưu tiên cải tiến hạ tầng | Số lần bị chặn, thời gian chờ, độ ổn định kiểm thử |
| **Phụ thuộc nhà cung cấp/API** | Làm rõ hợp đồng sớm, thử tích hợp nhỏ, có mock/stub với kiểm chứng cuối thực | Thời gian blocked, lỗi tích hợp phát hiện muộn |
| **Phê duyệt triển khai theo đợt lớn** | Tăng tự động hóa kiểm soát, chính sách phê duyệt theo rủi ro, triển khai nhỏ hơn | Thời gian từ đạt DoD tới phát hành, số sự cố rollback |
| **Thiếu thông tin đầu vào** | Refinement vừa đủ, ví dụ chấp nhận, làm rõ quyền quyết định | Số lần hạng mục quay lại làm rõ, thời gian chờ quyết định |
| **WIP cao và đổi việc liên tục** | Giới hạn WIP, ưu tiên hoàn tất, giảm ngắt việc không cần thiết | Work item age, throughput ổn định, cycle time |
| **Lỗi làm lại nhiều vòng** | Kiểm thử tự động, review sớm, cải tiến DoD và chất lượng đầu vào | Tỷ lệ làm lại, lỗi sau phát hành, thời gian chờ tái kiểm tra |
| **Yêu cầu khẩn chen ngang liên tục** | Chính sách lớp dịch vụ rõ ràng, minh bạch tác động với việc thường | Số lần ngắt, thời gian việc thường bị trì hoãn |

Không nên chọn mười biện pháp cùng lúc. **Chọn một nguyên nhân có bằng chứng, thử một hoặc hai thay đổi, theo dõi tác động rồi tiếp tục** sẽ giúp nhóm biết điều gì thực sự cải thiện dòng chảy.

## 14. Swarming: nhiều người cùng giúp một hạng mục tiến tới Done

**Swarming** là cách một số thành viên cùng tập trung hỗ trợ công việc đang bị chậm hoặc gần hoàn tất thay vì mỗi người bắt đầu một item mới. Đây là lựa chọn phối hợp, không phải yêu cầu Kanban bắt buộc.

### Ví dụ tại hàng đợi kiểm thử

Một nhóm có ba story đã hoàn thành phần phát triển nhưng chưa kiểm thử tích hợp. Developers đang định bắt đầu ba story khác; QA không thể xử lý hết phần tồn.

Nhóm có thể thử:

- Developers và QA cùng chuẩn bị dữ liệu thử, viết kiểm thử tự động phù hợp và xử lý lỗi nhanh.
- Những người có chuyên môn kiểm thử review kịch bản phức tạp, người khác hỗ trợ các phần an toàn trong phạm vi kỹ năng.
- Hạn chế mở việc mới cho đến khi ít nhất một story đạt DoD.
- Sau khi dòng chảy ổn định, xem lại vì sao kiểm thử liên tục trở thành chỗ chờ.

Không phải cứ đưa thêm người vào một công việc sẽ nhanh hơn. Một số nhiệm vụ không chia song song được; thêm người có thể tăng thời gian trao đổi hoặc rủi ro sai sót. **Swarming hiệu quả khi có phần việc hỗ trợ thực chất và ranh giới chất lượng rõ**.

## 15. Quản lý công việc bị chặn và phụ thuộc bên ngoài

Nút thắt bên trong quy trình và công việc **bị chặn từ bên ngoài** thường cần can thiệp khác nhau.

### 15.1. Hiển thị blocked item

Một thẻ bị chặn nên thể hiện vừa đủ:

~~~text
HẠNG MỤC: Học viên nhận email xác nhận workshop
TRẠNG THÁI: Đang tích hợp — bị chặn
LÝ DO: Nhà cung cấp chưa cấp thông tin thử nghiệm
BẮT ĐẦU BỊ CHẶN: Thứ Ba, 10:00
ẢNH HƯỞNG: Chưa thể kiểm chứng trạng thái gửi và lỗi tích hợp
NGƯỜI PHỤ TRÁCH PHỐI HỢP: Đại diện nhóm tích hợp
HÀNH ĐỘNG KẾ TIẾP: Xác nhận lịch cấp quyền; thử stub cho phần có thể kiểm chứng
MỐC XEM LẠI: Cuộc trao đổi với nhà cung cấp tiếp theo
~~~

**Không gắn nhãn blocked chung chung mà không có lý do và hành động tiếp theo.** Nếu thẻ bị chặn lâu, hãy làm rõ có thể tách phần độc lập, chuyển nguồn lực sang việc khác mà vẫn bảo đảm minh bạch WIP, hoặc cần quyết định dừng/hủy theo giá trị.

### 15.2. Phân biệt “waiting” và “blocked”

- **Waiting:** Hạng mục sẵn sàng bước tiếp theo nhưng chưa có người hoặc nguồn lực nhận xử lý. Ví dụ PR chờ reviewer; không phải lỗi bất thường.
- **Blocked:** Có rào cản ngăn tiến trình theo chính sách hiện tại. Ví dụ thiếu quyền truy cập, chờ quyết định của đối tác, dữ liệu bị hỏng.

Có thể đặt chính sách đếm cả thời gian waiting và blocked trong cycle time để phản ánh thời gian thực người dùng chờ. Nếu tổ chức cần báo cáo riêng, vẫn phải **giữ cách đo nhất quán và minh bạch**.

## 16. Chính sách ưu tiên và công việc khẩn không được phá vỡ dòng chảy

Kanban có thể sử dụng **lớp dịch vụ** (*classes of service*) hoặc chính sách ưu tiên khác nhau cho những công việc có hậu quả trì hoãn khác nhau. Chẳng hạn lỗi lộ dữ liệu cần phản ứng nhanh hơn một đề xuất đổi màu giao diện.

### Ví dụ chính sách

| Loại công việc | Dấu hiệu | Cách xử lý cần thống nhất |
| --- | --- | --- |
| **Khẩn cấp thật sự** | Sự cố sản xuất ảnh hưởng lớn, rủi ro bảo mật nghiêm trọng | Quy trình ứng phó sự cố, người có quyền kích hoạt, giới hạn số việc khẩn cùng lúc khi phù hợp |
| **Có ngày bắt buộc** | Nghĩa vụ hoặc thay đổi cần có hiệu lực vào ngày cụ thể | Ưu tiên dựa trên thời hạn, phụ thuộc và mức rủi ro; theo dõi từ sớm |
| **Luồng tiêu chuẩn** | Cải tiến chức năng thông thường | Kéo theo ưu tiên sản phẩm và khả năng tiếp nhận |
| **Cải tiến nền tảng** | Giảm lỗi, nâng khả năng kiểm thử hoặc vận hành | Dành cơ chế ưu tiên rõ để không bị đẩy lùi vô hạn |

Không có bộ tên lớp dịch vụ nào bắt buộc mọi nhóm phải áp dụng. Nếu mọi yêu cầu đều được gắn “expedite”, **chính sách khẩn đã mất tác dụng**. Cần đánh giá tác động, người có thẩm quyền và hậu quả đối với những item đang chờ.

**Giảm thời gian chờ cho một việc khẩn bằng cách làm tất cả việc còn lại chậm vô hạn cũng không phải cải thiện tổng thể.** Theo dõi tác động tới các nhóm công việc và người dùng khác.

## 17. Kích thước lô và lát cắt dọc ảnh hưởng đến thời gian chờ

Việc gom thay đổi lớn trước khi review, kiểm thử hoặc triển khai có thể tăng thời gian chờ:

- Người review cần hiểu nhiều phần thay đổi cùng lúc và dễ yêu cầu chỉnh sửa nhiều vòng.
- Lỗi tích hợp xuất hiện muộn, khó biết thay đổi nào gây ra.
- Mỗi lần phê duyệt phụ thuộc vào một lô lớn, làm mọi phần nhỏ đều phải chờ phần chậm nhất.
- Phản hồi người dùng đến muộn hơn, khiến nhóm có thể tiếp tục xây hướng ít giá trị.

### Ví dụ chia lát cắt

Thay vì một PBI lớn **“Hoàn thiện hệ thống quản lý workshop”**, có thể chia:

1. Xem workshop còn chỗ và điều kiện tham gia.
2. Đăng ký một workshop hợp lệ, kiểm tra quyền và chống vượt sức chứa.
3. Xem các đăng ký của chính mình.
4. Hủy đăng ký theo chính sách và cập nhật chỗ chính xác.
5. Nhận thông báo nhắc lịch khi trạng thái dữ liệu đã đáng tin.

Mỗi lát cắt cần đi qua những bước kỹ thuật và kiểm chứng cần thiết để có thể xem là hoàn chỉnh. **Chia nhỏ không có nghĩa bỏ bảo mật, tính nhất quán dữ liệu hoặc kiểm thử của phần được mở cho người dùng.**

### Lợi ích đối với nút thắt

Item nhỏ hơn thường giúp review sớm, giảm thời gian chờ cả lô, phát hiện vấn đề gần nơi tạo ra và làm dữ liệu cycle time có ý nghĩa hơn. Nhưng item nhỏ chưa chắc mọi loại công việc đều dễ: thay đổi dữ liệu lớn hoặc tích hợp bên ngoài có thể cần kế hoạch riêng.

## 18. Kanban kết hợp với Scrum và XP ra sao?

**Kanban** giúp cải thiện cách công việc chảy qua hệ thống, còn **Scrum** tạo nhịp kiểm tra/thích ứng và các trách nhiệm sản phẩm; **XP** cung cấp nhiều thực hành kỹ thuật để thay đổi an toàn.

| Cách tiếp cận | Đóng góp cho việc giảm chờ | Ví dụ thực hành |
| --- | --- | --- |
| **Kanban** | Làm hiện trạng thái công việc, WIP, thời gian chờ và chính sách pull | Tách “Chờ review” khỏi “Đang review”, theo dõi work item age, giới hạn WIP |
| **Scrum** | Tạo mục tiêu Sprint và cơ hội kiểm tra, thích ứng thường xuyên | Daily Scrum kiểm tra tiến độ tới Sprint Goal; Retrospective tìm cải tiến |
| **XP** | Tăng khả năng hoàn tất Increment nhỏ và an toàn, giảm lỗi làm lại | TDD khi phù hợp, tích hợp liên tục, refactoring, pair programming |
| **Quản lý sản phẩm** | Giữ thứ tự công việc theo giá trị và rủi ro | Product Owner làm rõ điều quan trọng, không chỉ item nào dễ đóng |

Trong Scrum, **Developers tự quản Sprint Backlog**, **Product Owner chịu trách nhiệm thứ tự Product Backlog**, **Scrum Master giúp nhóm áp dụng Scrum hiệu quả và tháo gỡ trở ngại**. Một Scrum Team có thể dùng bảng Kanban, flow metrics và WIP limit để tăng khả năng giao Increment đạt Definition of Done.

### Ví dụ Daily Scrum hướng tới dòng chảy

Thay vì mỗi người báo cáo “Hôm qua code gì?”, Developers có thể cùng nhìn bảng và hỏi:

> “Story nào đang già nhất? Có việc nào gần đạt DoD nhưng bị chờ review hoặc kiểm thử? Chúng ta cần phối hợp thế nào hôm nay để tiến gần Sprint Goal, thay vì mở thêm việc mới?”

Đây là một cách dùng Daily Scrum hiệu quả, không phải công thức bắt buộc. Mục đích là **kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch của Developers**.

## 19. Tình huống xuyên suốt: review là nút thắt của nhóm workshop

Một nhóm sáu người phát triển nền tảng học tập có nhiệm vụ mở tính năng đăng ký workshop trước kỳ học mới. Nhóm đang làm việc theo một bảng Kanban, mỗi item là một lát cắt chức năng đã có tiêu chí chấp nhận.

### 19.1. Hiện trạng ban đầu

Qua bốn tuần gần đây, nhóm thấy:

- Nhiều item được đưa vào phát triển mỗi tuần, nhưng **chỉ khoảng ba item/tuần** đạt Done theo chính sách chung.
- Bảng thường có **bốn đến sáu item chờ code review**, nhiều PR lớn.
- Một chuyên gia backend thường là người duy nhất đủ thông tin để duyệt thay đổi về quyền và nhất quán dữ liệu.
- Người review còn phải xử lý sự cố sản xuất, nên các PR thường đợi một đến vài ngày.
- Trong khi chờ, Developers bắt đầu thêm item mới, làm WIP tăng.
- Khi review bắt đầu, nhiều sai lệch yêu cầu được phát hiện khiến item quay về Development.

Các số này là **tình huống học tập giả định**, chưa phải bằng chứng rằng chỉ review là nguyên nhân duy nhất. Nhóm cần xem thời điểm đến/hoàn tất, loại item, mức độ lỗi và những phụ thuộc thực tế.

### 19.2. Chẩn đoán dựa trên dữ liệu

| Câu hỏi | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Hàng đợi review có tăng liên tục? | Đếm item chờ review mỗi ngày; xem CFD | Biết có xu hướng tích tụ hay chỉ đợt ngắn |
| Item chờ bao lâu? | Đo queue time và work item age | Nhận ra trường hợp vượt mức thường thấy |
| Reviewer có đủ năng lực? | Xem số PR tới/đi, thời gian xử lý và loại thay đổi | Phân biệt thiếu năng lực với PR khó |
| Vì sao PR thường bị trả lại? | Phân loại phản hồi review theo lỗi, thiếu thông tin và thay đổi yêu cầu | Tìm nguyên nhân làm lại |
| Một item thực sự tới người dùng mất bao lâu? | Cycle time/lead time theo ranh giới chung | Đo cải thiện tổng thể, không chỉ thời gian review |
| Chất lượng có đang ổn không? | Lỗi phát hành, kiểm thử quyền, lỗi trùng chỗ | Tránh cải thiện tốc độ bằng cách giảm kiểm soát |

### 19.3. Giả thuyết cải tiến

Nhóm thống nhất một thử nghiệm hai tuần:

1. Giữ ít hạng mục **đang phát triển** hơn, ưu tiên giúp item cũ đạt Done.
2. Chia PR lớn thành thay đổi nhỏ, mỗi thay đổi có bối cảnh và kiểm thử phù hợp.
3. Cùng chuyên gia backend chuẩn hóa checklist review quyền và tính nhất quán dữ liệu.
4. Pair programming hoặc review sớm ở các luồng rủi ro để tăng hiểu biết trong nhóm.
5. Tạo chính sách **kéo review trong ngày khi có năng lực**, không dồn toàn bộ đến cuối Sprint.
6. Ghi blocked time và lý do cho những thay đổi đợi chuyên gia hoặc bị sự cố chen ngang.

Các bước trên là **giả thuyết cần thử**, không bảo đảm thành công. Nếu PR được chia quá nhỏ nhưng không thể kiểm chứng độc lập, thời gian điều phối có thể tăng; nhóm phải xem chất lượng và kết quả thật.

### 19.4. Kiểm chứng sau thử nghiệm

Kết thúc hai tuần, nhóm so sánh với đường cơ sở phù hợp:

| Tiêu chí | Điều cần xem |
| --- | --- |
| **Review queue** | Hàng đợi và thời gian chờ có giảm theo nhiều ngày không? |
| **Work item age** | Những item đã bắt đầu còn bị mắc kẹt lâu hơn bình thường không? |
| **Cycle time** | Một lát cắt đi qua toàn quy trình nhanh và ổn định hơn không? |
| **Throughput** | Số item đạt Done có giữ hoặc tăng mà không làm giảm chất lượng? |
| **Làm lại** | Số vòng review, lỗi tích hợp và lỗi sản xuất có thay đổi? |
| **Năng lực nhóm** | Có thêm người đủ kỹ năng review những thay đổi phù hợp? |
| **Giá trị người dùng** | Học viên có nhận được chức năng đăng ký/hủy đáng tin sớm hơn? |

Nếu hàng đợi review giảm nhưng kiểm thử tăng chờ, nhóm xác định **nút thắt mới** rồi tiếp tục cải tiến. Nếu review nhanh hơn nhờ bỏ kiểm tra phân quyền, kết quả không được coi là thành công.

## 20. Kế hoạch thực hành trong một tuần làm việc

Nhóm có thể bắt đầu mà không cần thay toàn bộ công cụ.

### Ngày 1 — Vẽ luồng và thỏa thuận chính sách

- Cùng những người trực tiếp làm việc vẽ các bước thật, bao gồm **chờ review, chờ kiểm thử, chờ triển khai**.
- Thống nhất điểm vào WIP, điểm Done và cách đánh dấu blocked.
- Chọn một loại item để theo dõi trước, tránh trộn các công việc có quy mô quá khác nhau.
- Không đổi dữ liệu cũ chỉ để bảng mới trông đầy đủ.

### Ngày 2 — Quan sát hàng đợi và tuổi công việc

- Xem tổng WIP và số item ở mỗi trạng thái.
- Xác định những item già nhất, nguyên nhân chờ và phụ thuộc.
- Ghi số item hoàn tất và thời gian đã đi qua các bước; nếu chưa có lịch sử, bắt đầu thu.
- Hỏi thành viên trực tiếp làm việc điều gì làm họ phải dừng hoặc chuyển việc.

### Ngày 3 — Chọn một nút thắt cần xác minh

- Kiểm tra dấu hiệu tích tụ qua thời gian.
- Phân biệt thiếu năng lực với nguyên nhân PR lớn, làm lại, thiếu quyền hoặc chính sách bất hợp lý.
- Chọn một giả thuyết có thể kiểm tra, chẳng hạn “review sớm và PR nhỏ hơn sẽ giảm thời gian chờ”.
- Nêu rõ điều **không được đánh đổi**, ví dụ kiểm thử phân quyền và tính nhất quán dữ liệu.

### Ngày 4 — Thử can thiệp nhỏ

- Đặt WIP limit thử nghiệm với lý do rõ.
- Phân công hỗ trợ hoàn tất việc đang chờ trong ranh giới chuyên môn phù hợp.
- Làm rõ chính sách kéo việc và cách phản ứng với ngoại lệ.
- Ghi tác động lên hàng đợi và những việc bị ngắt để tránh hiểu sai kết quả.

### Ngày 5 — Đánh giá và quyết định tiếp

- So sánh với số liệu ban đầu, nhưng thừa nhận dữ liệu một tuần còn ít.
- Hỏi điều gì tốt hơn, điều gì xấu đi và điểm nghẽn có dịch chuyển không.
- Giữ, điều chỉnh hoặc bỏ thử nghiệm; định thời điểm xem lại sau nhiều chu kỳ hơn.
- Gắn cải tiến với người phụ trách phối hợp, không để thành một lời hứa chung.

Một tuần đủ để **bắt đầu thấy vấn đề và thử cải tiến**, thường chưa đủ để khẳng định tác động bền vững. Tiếp tục quan sát nhiều chu kỳ để tránh kết luận từ biến động ngẫu nhiên.

## 21. Mẫu phân tích nút thắt và thử nghiệm cải tiến

~~~text
TÊN LUỒNG CÔNG VIỆC:
GIÁ TRỊ / NGƯỜI DÙNG BỊ ẢNH HƯỞNG:
RANH GIỚI ĐO: Bắt đầu từ ... / Hoàn tất tại ...
CHÍNH SÁCH DONE / CHẤT LƯỢNG BẮT BUỘC:

DỮ LIỆU HIỆN TẠI:
- WIP tổng / theo trạng thái:
- Throughput theo khoảng thời gian:
- Cycle time và phân bố:
- Work item age của các việc đang làm:
- Hàng đợi / blocked time / số lần làm lại:
- Những thay đổi năng lực hoặc loại việc so với lịch sử:

DẤU HIỆU NÚT THẮT:
GIẢ THUYẾT NGUYÊN NHÂN:
BẰNG CHỨNG XÁC MINH:
RỦI RO NẾU KHÔNG XỬ LÝ:

THỬ NGHIỆM CẢI TIẾN:
- Hành động:
- Phạm vi / người phối hợp:
- Chính sách WIP / pull cần thay:
- Điều kiện chất lượng không được bỏ:
- Thời điểm bắt đầu và xem lại:

ĐÁNH GIÁ:
- Queue time / cycle time thay đổi thế nào?
- Throughput và work item age thay đổi thế nào?
- Có phát sinh lỗi, làm lại hoặc dịch chuyển nút thắt không?
- Phản hồi người dùng và stakeholder ra sao?
- Quyết định: Giữ / Sửa / Bỏ / Thử thêm:
~~~

Không cần điền mọi trường cho một vấn đề nhỏ. Với nút thắt liên nhóm hoặc ảnh hưởng phát hành quan trọng, ghi lại **dữ liệu, quyết định và người chịu trách nhiệm** giúp tránh xử lý lặp lại mà không biết cải tiến nào hữu ích.

## 22. Bài tập ứng dụng: tìm nút thắt và chọn can thiệp

**Bối cảnh:** Nhóm phát triển nền tảng học tập đo được các hạng mục ở trạng thái sau vào sáng thứ Sáu:

| Hạng mục | Trạng thái | Tuổi từ khi bắt đầu | Lý do chờ nếu có |
| --- | --- | ---: | --- |
| A. Đăng ký workshop | Chờ review | 9 ngày | PR lớn, một người đủ quyền review |
| B. Xem đăng ký của mình | Chờ review | 7 ngày | Reviewer đang xử lý A |
| C. Tự hủy workshop | Đang phát triển | 5 ngày | Chưa rõ chính sách hủy |
| D. Lọc workshop | Đang phát triển | 3 ngày | Không |
| E. Theo dõi lỗi đăng ký | Chờ kiểm thử | 8 ngày | Môi trường kiểm thử bị chiếm |
| F. Sửa lỗi sai chỗ trống | Đang review | 6 ngày | Cần kiểm tra trường hợp đồng thời |
| G. Cải thiện nút đăng ký | Đang phát triển | 2 ngày | Không |
| H. Thông báo email | Bị chặn khi tích hợp | 10 ngày | Chờ nhà cung cấp xác nhận API |

Trong bốn tuần gần đây, throughput hạng mục đạt Done lần lượt là **3, 2, 4, 3 hạng mục/tuần**. Nhóm đang có tám item chưa Done và đề xuất bắt đầu thêm bốn item mới cho “mọi người có việc”.

### Câu hỏi

1. Throughput trung bình trong bốn tuần là bao nhiêu item/tuần?
2. Trong bảng, có những **dấu hiệu nút thắt hoặc thời gian chờ** nào cần điều tra trước?
3. Tại sao số item ở “Chờ review” chưa đủ để kết luận chính xác năng lực review đang thiếu? Cần thêm dữ liệu gì?
4. Item nào có **work item age** đáng chú ý? Vì sao không nên chỉ nhìn số ngày mà bỏ qua loại việc và chính sách?
5. Nếu giữ throughput trung bình như cũ và WIP tăng từ 8 lên 12 trong một hệ thống giả định ổn định, Little's Law gợi ý điều gì về cycle time trung bình? Giả định nào đang rất dễ bị vi phạm?
6. Đề xuất **hai thử nghiệm nhỏ** để giảm chờ review mà không bỏ kiểm soát quyền và tính nhất quán dữ liệu.
7. Với item E và H, bạn cần phân biệt loại phụ thuộc nào và phối hợp với ai?
8. Nếu hàng đợi review giảm sau thử nghiệm nhưng số lỗi sản xuất tăng, bạn sẽ đánh giá kết quả thế nào?
9. Trong Scrum Team, ai tự điều chỉnh kế hoạch trong Sprint, ai sắp thứ tự Product Backlog, Scrum Master hỗ trợ gì?
10. Bạn sẽ thu những dữ liệu nào trong hai tuần tới để biết điểm nghẽn có thực sự được cải thiện?

### Gợi ý hướng giải

Throughput trung bình:

\[
\frac{3+2+4+3}{4}=3\ \text{hạng mục/tuần}.
\]

Với **8 item đang làm**, một phép minh họa thuần lý thuyết theo Little's Law trong trạng thái ổn định là:

\[
\text{Cycle time trung bình}\approx\frac{8}{3}\approx2{,}67\ \text{tuần}.
\]

Nếu WIP là **12** mà throughput vẫn **3 item/tuần**, con số tương ứng là **4 tuần**. Nhưng trong tình huống này có item blocked, phụ thuộc ngoài, tuổi item khác nhau và WIP chưa chắc ổn định. **Không được dùng các con số đó làm dự báo chắc chắn**; chúng chỉ cho thấy rủi ro kéo dài thời gian khi mở thêm nhiều việc mà không tăng khả năng hoàn tất.

Các dấu hiệu nổi bật là A/B chờ review, E chờ môi trường, H chờ nhà cung cấp và C đang thiếu quy tắc nghiệp vụ. Cần xác minh nguyên nhân, không gộp tất cả thành “review chậm”. Hai thử nghiệm có thể là **chia PR thành lát cắt nhỏ có kiểm chứng** và **review/pairing sớm để chia sẻ kiến thức**, kết hợp giới hạn WIP hợp lý. Với E cần làm rõ chủ sở hữu môi trường kiểm thử; với H cần cơ chế phối hợp nhà cung cấp và kế hoạch thử phần có thể kiểm chứng. Sau thử nghiệm, theo dõi thời gian chờ, WIP, throughput, cycle time và **chất lượng Increment**.

## 23. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| **Ai cũng bận là hệ thống hiệu quả** | WIP tăng, thời gian chờ và đổi ngữ cảnh tăng | Tập trung hoàn tất việc có giá trị, nhìn throughput toàn luồng |
| **Chỉ cần thêm người vào cột đang tắc** | Không giải quyết PR lớn, chính sách chờ hoặc làm lại | Xác minh nguyên nhân bằng dữ liệu và quan sát |
| **Giới hạn WIP áp dụng máy móc cho mọi tình huống** | Người không có kỹ năng bị ép kiểm tra rủi ro cao hoặc bị bỏ không | Chính sách có ngoại lệ minh bạch và kế hoạch nâng năng lực |
| **Xóa nhãn blocked để board đẹp hơn** | Mất tín hiệu rào cản, số liệu WIP sai | Giữ trạng thái trung thực, làm rõ hành động tiếp |
| **Kéo item mới vào vì người làm đã code xong** | Hàng đợi review/kiểm thử tích tụ | Áp dụng pull theo khả năng hệ thống, hỗ trợ item gần Done |
| **Chia story thành vô số task kỹ thuật** | Số item Done tăng nhưng giá trị chưa được giao | Dùng lát cắt dọc và chính sách Done phản ánh Increment |
| **Chỉ đo cycle time trung bình** | Che item rất chậm và nút thắt ở phần đuôi | Xem phân bố, item age và các ngoại lệ |
| **CFD có dải rộng là kết luận đủ về nguyên nhân** | Chữa sai chỗ, có thể dịch chuyển nút thắt xấu hơn | Kết hợp dòng đến/đi, hàng đợi, phỏng vấn và dữ liệu chất lượng |
| **Bỏ review hoặc kiểm thử để giảm thời gian chờ** | Lỗi và rủi ro người dùng tăng | Giảm chờ bằng tổ chức công việc, tự động hóa phù hợp và phối hợp sớm |
| **Mọi yêu cầu đều gắn “khẩn cấp”** | Luồng chuẩn luôn bị ngắt và khó dự báo | Có tiêu chí, thẩm quyền và minh bạch tác động |
| **Dùng Little's Law làm công thức dự báo chính xác mọi Sprint** | Dùng sai điều kiện ổn định và ranh giới đo | Chỉ sử dụng như quan hệ hệ thống có giả định; kiểm chứng bằng dữ liệu |
| **Nhìn tốc độ một cột thay vì toàn hệ thống** | Review nhanh hơn nhưng chờ deploy dài hơn | Theo dõi cycle time/lead time toàn luồng và chất lượng |
| **So sánh số thẻ Done để xếp hạng cá nhân** | Tạo động cơ chia giả hoặc che việc khó | Đo lường cho học hỏi và điều phối ở cấp nhóm |
| **Thử quá nhiều cải tiến cùng lúc** | Không rõ thay đổi nào có tác dụng | Giả thuyết nhỏ, đo trước/sau và xem lại |
| **Không cập nhật chính sách khi sản phẩm thay đổi** | Dữ liệu đo không còn đại diện, quy trình rườm rà | Cùng nhóm xem lại workflow, WIP và cách đo theo bối cảnh |

## 24. Ghi nhớ và tự kiểm tra

**Kanban giúp nhìn và cải thiện dòng công việc, đặc biệt ở những khoảng chờ bị che khuất phía sau hoạt động bận rộn.** Nhóm nên trực quan hóa các công đoạn và hàng đợi thật, đặt chính sách pull/WIP rõ, dùng throughput, cycle time, work item age, WIP cùng dữ liệu blocked/queue time để tìm dấu hiệu. Sau đó, nhóm cần **xác minh nguyên nhân, chọn can thiệp nhỏ và kiểm chứng kết quả trên toàn luồng**. Giảm thời gian chờ không có nghĩa bỏ review, bảo mật, kiểm thử hoặc hạ tiêu chuẩn Done.

Tự kiểm tra:

1. Nút thắt khác hàng đợi và công việc bị chặn như thế nào?
2. Vì sao “mọi thành viên đang bận” không chứng minh hệ thống giao giá trị nhanh?
3. Nên tách “Chờ review” và “Đang review” khi nào, và việc tách đem lại thông tin gì?
4. Throughput, cycle time, work item age và WIP hỗ trợ nhau thế nào khi phát hiện nút thắt?
5. Trong ví dụ flow efficiency 30%, đâu là phần xử lý và đâu là phần chờ? Cần thận trọng điều gì về đơn vị đo?
6. Một dải trạng thái rộng lên trên CFD báo hiệu điều gì và chưa chứng minh được điều gì?
7. Little's Law có dạng nào và cần những giả định gì để diễn giải đúng?
8. Khi WIP đã đạt giới hạn, nhóm có thể làm gì ngoài bắt đầu hạng mục mới?
9. Vì sao review sớm, PR nhỏ và chia sẻ kiến thức có thể giảm chờ tốt hơn ép reviewer làm nhanh hơn?
10. Vì sao một yêu cầu “expedite” có thể làm chậm nhiều việc thường, và cần chính sách nào?
11. Làm thế nào kiểm tra một cải tiến giảm thời gian chờ mà vẫn giữ chất lượng?
12. Nếu nút thắt chuyển từ review sang kiểm thử, nhóm nên đánh giá và hành động ra sao?

Trước khi mở thêm công việc, hãy hỏi: **“Hạng mục nào đang chờ lâu nhất, điều gì thực sự ngăn nó hoàn tất và chúng ta có thể hỗ trợ giảm thời gian chờ mà vẫn giữ chất lượng không?”** Khi mọi người cùng ưu tiên **kết thúc công việc có giá trị** thay vì chỉ bắt đầu thêm việc, nhóm sẽ phản hồi sớm hơn, dự báo đáng tin hơn và cải tiến được luồng phát triển phần mềm qua từng vòng học hỏi.
