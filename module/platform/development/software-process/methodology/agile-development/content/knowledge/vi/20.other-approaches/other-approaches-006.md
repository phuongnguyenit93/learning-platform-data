# FDD: danh sách tính năng cùng lập kế hoạch, thiết kế và xây dựng theo tính năng

Một nhóm phát triển nền tảng học trực tuyến nhận yêu cầu “Học viên cần lưu tiến độ, tiếp tục học trên nhiều thiết bị và biết mình đã hoàn thành bao nhiêu phần trăm khóa học”. Nhóm có nhiều đối tượng nghiệp vụ liên quan như học viên, khóa học, bài học, đăng ký học, bản ghi tiến độ và quy tắc quyền truy cập. Nếu bắt đầu bằng danh sách hàng trăm task kỹ thuật, khó biết lúc nào người dùng thật sự nhận được một khả năng mới. Nếu cố thiết kế toàn bộ hệ thống đến từng chi tiết trước khi triển khai, nhóm cũng có nguy cơ học quá muộn về những giả định sai.

**Feature-Driven Development (FDD)** là một cách tiếp cận phát triển phần mềm lặp và tăng dần, tổ chức công việc xung quanh **những tính năng nhỏ có giá trị đối với khách hàng/nghiệp vụ**. FDD kết hợp việc hiểu mô hình miền nghiệp vụ với **danh sách tính năng**, **kế hoạch theo tính năng**, **thiết kế theo tính năng** và **xây dựng theo tính năng**. Mỗi tính năng nên đủ nhỏ để được thiết kế, triển khai, kiểm thử và tích hợp trong một khoảng ngắn, thay vì đợi cả hệ thống hoàn tất.

Bài học thuộc chương **Các cách tiếp cận khác** của module **AGILE_DEVELOPMENT**. Mục tiêu là hiểu FDD như một lựa chọn trong bức tranh Agile: giao sản phẩm tăng dần, nhận phản hồi sớm và cải tiến liên tục, đồng thời biết cách kết hợp hay phân biệt với **user story, backlog, Scrum, Kanban, XP** và các phép đo dòng công việc. FDD không phải công thức bắt buộc cho mọi nhóm; giá trị của nó nằm ở cách làm rõ miền nghiệp vụ, biến nhu cầu thành các kết quả nhỏ và đưa các kết quả đó qua một quy trình kỹ thuật minh bạch.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích FDD là gì, giải quyết vấn đề nào và trong bối cảnh nào có thể hữu ích.
2. Mô tả chính xác **năm hoạt động cốt lõi**: Develop an Overall Model, Build a Features List, Plan by Feature, Design by Feature và Build by Feature.
3. Viết một **feature** nhỏ theo hành vi/nghiệp vụ, phân biệt feature với epic, user story, task kỹ thuật và yêu cầu phi chức năng.
4. Tổ chức features thành **feature, feature set và major feature set**, làm rõ ranh giới, phụ thuộc và thứ tự ưu tiên.
5. Hiểu trách nhiệm của **domain experts, chief programmer, class owner, Developers và các vai trò hỗ trợ** trong FDD cổ điển.
6. Thực hiện một chu kỳ **thiết kế–xây dựng theo tính năng**, gồm làm rõ quy tắc, thiết kế, review, triển khai, kiểm thử và tích hợp.
7. Lập kế hoạch theo tính năng với dữ liệu năng lực, rủi ro và các giới hạn về chất lượng, không coi ước lượng là lời hứa chắc chắn.
8. Phân biệt FDD với Scrum, Kanban và XP; chọn thực hành bổ trợ mà không ghép các framework một cách máy móc.
9. Nhận diện các phản mẫu như **feature quá lớn, mô hình hóa quá mức, hoàn thành từng lớp kỹ thuật, đo tiến độ sai và phụ thuộc vào một cá nhân**.

## 2. FDD là gì và vì sao xuất hiện?

Feature-Driven Development được hình thành trong bối cảnh các dự án phần mềm có **miền nghiệp vụ nhiều quy tắc**, nhiều đối tượng liên quan và cần cách tổ chức công việc để triển khai tăng dần. Cách tiếp cận này gắn với công việc của **Jeff De Luca** và **Peter Coad** từ cuối thập niên 1990; các nguyên tắc và thực hành được trình bày trong tài liệu *Java Modeling in Color with UML* và *A Practical Guide to Feature-Driven Development*.

Khác với cách chỉ giao từng module hoặc từng thành phần kỹ thuật, FDD đặt một đơn vị nhỏ có ý nghĩa đối với người nhận giá trị làm trung tâm:

> **Một feature là một khả năng nhỏ, hữu ích theo góc nhìn khách hàng hoặc nghiệp vụ, có thể xác định và hoàn thành trong một khoảng thời gian tương đối ngắn.**

Ví dụ:

- “Ghi nhận vị trí học cuối cùng của một học viên trong một bài học.”
- “Hiển thị bài học đang dở cho học viên tại trang khóa học.”
- “Từ chối truy cập bài học khi người dùng không còn quyền học.”
- “Tính tỷ lệ hoàn thành khóa học từ các bài học đã đạt điều kiện hoàn tất.”

Các feature trên biểu diễn **kết quả chức năng** chứ không phải các bước kỹ thuật riêng lẻ như “tạo bảng progress”, “viết endpoint” hay “thiết kế nút”. Trong quá trình thực hiện mỗi feature, nhóm vẫn cần làm công việc về giao diện, API, dữ liệu, bảo mật và kiểm thử.

### Những vấn đề FDD muốn giải quyết

| Vấn đề trong dự án | FDD đề xuất cách nhìn | Lợi ích kỳ vọng |
| --- | --- | --- |
| Nhu cầu nghiệp vụ lớn, nhiều quan hệ | Xây dựng mô hình miền ở mức đủ hiểu | Nhóm có ngôn ngữ chung về đối tượng và quy tắc |
| Danh sách việc chỉ gồm task kỹ thuật | Phân rã thành các feature có ý nghĩa nghiệp vụ | Dễ nhìn phần giá trị sẽ được giao |
| Khó biết triển khai cái gì trước | Sắp xếp và lập kế hoạch theo feature | Thứ tự có cơ sở về giá trị, phụ thuộc và rủi ro |
| Nhiều lập trình viên sửa cùng miền phức tạp | Phối hợp thiết kế theo feature, sử dụng vai trò kỹ thuật rõ | Giảm bất đồng về mô hình và giao diện tích hợp |
| Tích hợp lớn ở cuối dự án | Xây và tích hợp các feature nhỏ thường xuyên | Nhận tín hiệu lỗi và tiến độ sớm hơn |
| Báo cáo phần trăm hoàn thành thiếu cơ sở | Theo dõi milestone và số feature đạt chất lượng | Minh bạch hơn về trạng thái công việc thật |

Các lợi ích trên **không tự xuất hiện chỉ vì đổi tên ticket thành feature**. FDD chỉ phát huy tác dụng khi feature được chọn đúng kích thước, có mô hình nghiệp vụ đủ dùng, có kiểm thử và được giao/tích hợp thực sự.

## 3. Năm hoạt động cốt lõi của FDD

Tài liệu FDD cổ điển thường mô tả **năm quy trình/hoạt động** theo thứ tự sau:

| Hoạt động | Tên tiếng Anh | Câu hỏi chính | Đầu ra quan trọng |
| --- | --- | --- | --- |
| **1. Phát triển mô hình tổng thể** | Develop an Overall Model | Hệ thống cần hiểu những đối tượng, quan hệ và quy tắc miền nào? | Một mô hình miền tổng thể đủ để các bên thảo luận |
| **2. Xây dựng danh sách tính năng** | Build a Features List | Khả năng nhỏ nào tạo giá trị cho khách hàng/nghiệp vụ? | Danh sách features được nhóm theo cấu trúc nghiệp vụ |
| **3. Lập kế hoạch theo tính năng** | Plan by Feature | Feature nào cần trước, ai phụ trách phần việc và phụ thuộc gì? | Thứ tự, phân công trách nhiệm, dự báo và kế hoạch |
| **4. Thiết kế theo tính năng** | Design by Feature | Một tập features nhỏ sẽ được hiện thực hóa bằng thiết kế nào? | Thiết kế chi tiết, thay đổi mô hình, kiểm tra thiết kế |
| **5. Xây dựng theo tính năng** | Build by Feature | Làm cách nào triển khai, kiểm thử, review và tích hợp tính năng đã chọn? | Phần mềm được tích hợp, kiểm chứng theo từng feature |

~~~mermaid
flowchart TD
    A["1. Develop an Overall Model<br/>Hiểu miền nghiệp vụ"] --> B["2. Build a Features List<br/>Phân rã thành các giá trị nhỏ"]
    B --> C["3. Plan by Feature<br/>Sắp xếp và dự báo"]
    C --> D["4. Design by Feature<br/>Thiết kế nhóm features"]
    D --> E["5. Build by Feature<br/>Mã hóa, kiểm thử, tích hợp"]
    E --> F["Increment nhỏ<br/>và bằng chứng thực tế"]
    F -. "Phản hồi thay đổi danh sách<br/>hoặc mô hình nếu cần" .-> A
    F -. "Cập nhật ưu tiên<br/>và kế hoạch" .-> C
    E -. "Tiếp tục feature kế tiếp" .-> D
~~~

**Đừng hiểu sơ đồ như mô hình thác nước năm giai đoạn chỉ chạy đúng một lần.** Mô hình tổng thể và danh sách feature cung cấp định hướng ban đầu; hoạt động thiết kế và xây dựng theo tính năng **lặp lại nhiều lần**. Khi phát hiện hành vi, quy tắc hoặc dữ liệu mới, nhóm phải có khả năng cập nhật mô hình, danh sách features và kế hoạch tương ứng.

FDD có xu hướng chú trọng **mô hình miền và cấu trúc tổ chức kỹ thuật** hơn nhiều phương pháp Agile khác. Điều đó có thể hữu ích trong hệ thống nghiệp vụ phức tạp nhưng cũng gây rủi ro nếu nhóm biến bước mô hình hóa thành một dự án dài không kiểm chứng bằng phần mềm.

## 4. Hoạt động 1 — Develop an Overall Model: hiểu miền trước khi chia tính năng

Trong FDD, người hiểu nghiệp vụ và những người kỹ thuật cùng xây **bức tranh tổng thể về miền**: đối tượng nào quan trọng, chúng có quan hệ gì và những quy tắc cốt lõi được áp dụng ra sao.

### Ví dụ miền nền tảng học trực tuyến

Một số khái niệm xuất hiện khi xây chức năng theo dõi học tập:

| Khái niệm miền | Ý nghĩa nghiệp vụ | Quy tắc hoặc câu hỏi cần làm rõ |
| --- | --- | --- |
| **Learner / học viên** | Người tham gia học | Một người có nhiều đăng ký khóa học không? |
| **Course / khóa học** | Tập bài học có cấu trúc | Bài nào phải hoàn thành trước bài nào? |
| **Lesson / bài học** | Đơn vị học tập | “Hoàn thành” được quyết định theo video, quiz hay bài tập? |
| **Enrollment / đăng ký học** | Mối liên hệ giữa học viên và quyền học một khóa | Khi hết hạn đăng ký, tiến độ có được xem nhưng không mở nội dung không? |
| **LearningProgress / tiến độ** | Trạng thái và vị trí học | Có lưu nhiều loại điểm dừng? Khi nào cập nhật là hợp lệ? |
| **CompletionRule / quy tắc hoàn thành** | Chính sách xác định bài được tính xong | Có điều kiện về điểm quiz hoặc tỷ lệ xem video? |
| **ProgressEvent / sự kiện tiến độ** | Một hành vi cập nhật hoặc quan sát | Làm sao tránh ghi đè dữ liệu khi có nhiều thiết bị? |

Một mô hình khái niệm minh họa:

~~~mermaid
classDiagram
    class Learner {
      learnerId
    }
    class Enrollment {
      status
      accessUntil
    }
    class Course {
      courseId
      title
    }
    class Lesson {
      lessonId
      order
    }
    class LearningProgress {
      lessonId
      position
      completionStatus
    }
    Learner "1" --> "0..*" Enrollment : có
    Course "1" --> "0..*" Enrollment : nhận đăng ký
    Course "1" --> "1..*" Lesson : bao gồm
    Enrollment "1" --> "0..*" LearningProgress : theo dõi
    LearningProgress "*" --> "1" Lesson : của bài
~~~

**Đây là sơ đồ miền để trao đổi, không phải schema database hoặc kiến trúc triển khai bắt buộc.** Ví dụ, lưu tiến độ theo enrollment hay theo cặp learner–lesson phụ thuộc quy tắc thật của sản phẩm. Không nên sao chép mô hình minh họa vào code mà chưa kiểm tra nghiệp vụ.

### Quy trình dựng mô hình ở mức đủ dùng

1. **Domain walkthrough:** Người hiểu nghiệp vụ mô tả các hành trình thật, ví dụ học một bài, hoàn thành quiz, đổi thiết bị hoặc hết quyền học.
2. **Nhận diện khái niệm chính:** Xác định các đối tượng, thuật ngữ và mối quan hệ có thể làm rõ bằng ví dụ.
3. **Thảo luận phương án mô hình:** Kỹ thuật có thể đề xuất nhiều cách biểu diễn; kiểm tra với quy tắc nghiệp vụ thay vì mặc định phương án đầu đúng.
4. **Chọn mô hình tổng thể đủ nhất quán:** Ghi các giả định, điều chưa biết và ranh giới cần kiểm chứng.
5. **Giữ khả năng điều chỉnh:** Khi một feature bộc lộ trường hợp mới, cập nhật hiểu biết về miền và các phụ thuộc.

### Mức chi tiết đến đâu là hợp lý?

Mô hình phải đủ rõ để nhóm **xác định và phân nhóm tính năng**, không nhất thiết mô tả từng trường dữ liệu, từng bảng, từng endpoint và mọi ngoại lệ ngay từ đầu. Một mô hình quá sơ sài gây bất đồng khi chia feature; một mô hình quá chi tiết có thể khiến kế hoạch trở nên cứng nhắc trước khi có phản hồi.

**Mục tiêu của hoạt động đầu là tạo hiểu biết chung về miền, không phải chứng minh đội đã thiết kế đúng toàn bộ sản phẩm.**

## 5. Hoạt động 2 — Build a Features List: từ mô hình sang đơn vị giá trị

Sau khi có bức tranh nghiệp vụ, nhóm chuyển các hoạt động miền thành **danh sách feature**. Trong cách mô tả FDD cổ điển, một feature thường được diễn đạt theo khuôn **hành động – kết quả – đối tượng** (*action–result–object*), ví dụ tiếng Anh “Calculate the total of a sale”.

Trong tiếng Việt, không cần ép đúng thứ tự từ nếu gây gượng; điều cần giữ là **động từ hành vi rõ, kết quả quan sát được và đối tượng nghiệp vụ cụ thể**.

| Cách diễn đạt | Ví dụ | Đánh giá |
| --- | --- | --- |
| **Hành động + kết quả + đối tượng** | “Tính tỷ lệ hoàn thành của một khóa học từ các bài đã đạt điều kiện.” | Có hành vi, quy tắc và kết quả nghiệp vụ |
| **Hành động người dùng + giá trị** | “Hiển thị bài đang học dở cho học viên tại trang khóa học.” | Có thể kiểm tra từ trải nghiệm người học |
| **Quy tắc bảo vệ có kết quả** | “Từ chối truy cập nội dung của học viên không còn quyền học.” | Kết quả nghiệp vụ an toàn, có thể kiểm thử |
| **Tên thành phần kỹ thuật** | “Tạo bảng progress trong database.” | Một task, chưa là feature có giá trị độc lập |
| **Yêu cầu quá rộng** | “Xây toàn bộ hệ thống tiến độ đa thiết bị, offline, báo cáo và nhắc học.” | Quá lớn, cần phân rã |
| **Nhãn mơ hồ** | “Nâng cấp trải nghiệm học.” | Chưa cho biết hành vi và điều kiện hoàn thành |

### Ba cấp tổ chức thường gặp

Trong FDD, danh sách có thể được tổ chức theo các cấp:

1. **Major feature set:** Nhóm năng lực lớn của miền, ví dụ “Quản lý hành trình học tập”.
2. **Feature set:** Hoạt động con tạo một nhóm chức năng, ví dụ “Quản lý tiến độ từng bài”.
3. **Feature:** Hành vi/kết quả nhỏ để thiết kế và xây, ví dụ “Lưu vị trí học gần nhất cho một bài”.

~~~text
Major feature set: Quản lý hành trình học tập
|
|-- Feature set: Theo dõi tiến độ từng bài
|   |-- F-01 Ghi nhận vị trí học hợp lệ của học viên
|   |-- F-02 Hiển thị bài đang học dở trên trang khóa học
|   |-- F-03 Đánh dấu bài hoàn thành khi đạt quy tắc
|   '-- F-04 Từ chối sửa tiến độ khi không đủ quyền
|
|-- Feature set: Tổng hợp tiến độ khóa học
|   |-- F-05 Tính số bài đã hoàn thành trong khóa học
|   '-- F-06 Hiển thị tỷ lệ hoàn thành khóa học
|
'-- Feature set: Tiếp tục học giữa thiết bị
    |-- F-07 Đọc tiến độ của cùng tài khoản từ thiết bị khác
    '-- F-08 Giải quyết cập nhật tiến độ đồng thời
~~~

Cấu trúc trên **không nhất thiết trùng với cấu trúc package, microservice hoặc nhóm nhân sự**. Đây là cách phân loại khả năng nghiệp vụ; những feature trong các feature set khác nhau có thể cùng sử dụng một lớp dữ liệu hay dịch vụ kỹ thuật.

### Kích thước feature

Trong mô tả FDD truyền thống, một feature thường được kỳ vọng có thể hoàn thành trong **khoảng hai tuần hoặc ít hơn**, và feature lớn hơn thường cần chia nhỏ. Đây là **quy tắc thực hành có tính lịch sử**, không phải tiêu chuẩn đo lường bắt buộc hoặc bảo đảm mọi nhóm sẽ hoàn thành đúng thời lượng.

Một feature đủ nhỏ cần:

- Có kết quả rõ để người hiểu nghiệp vụ xác nhận.
- Được Developers hiểu tương đối đủ để thiết kế và triển khai.
- Có kiểm thử/điều kiện hoàn tất phù hợp.
- Không yêu cầu tất cả feature khác phải xong mới có thể kiểm tra.
- Không được thu hẹp bằng cách bỏ qua quy tắc bảo mật hoặc tính đúng đắn bắt buộc.

## 6. Feature khác epic, user story, task và yêu cầu chất lượng thế nào?

Các khái niệm có thể liên hệ nhau nhưng không đồng nhất:

| Đơn vị | Vai trò thường gặp | Ví dụ | Cách dùng cùng FDD |
| --- | --- | --- | --- |
| **Epic / nhu cầu lớn** | Mục tiêu hoặc khả năng lớn cần chia | “Học viên tiếp tục học xuyên thiết bị.” | Phân thành feature sets và features nhỏ |
| **User story** | Lời mời trao đổi về nhu cầu, thường nêu vai trò – mong muốn – lợi ích | “Là học viên, tôi muốn quay lại đúng bài dở để không tìm thủ công.” | Có thể làm nguồn phân tích feature; không nhất thiết ánh xạ 1–1 |
| **FDD feature** | Khả năng nhỏ có kết quả nghiệp vụ cụ thể | “Hiển thị bài dở mới nhất của học viên trên trang khóa học.” | Đơn vị dùng để lập kế hoạch, thiết kế và xây dựng tăng dần |
| **Task kỹ thuật** | Bước thực hiện bên trong feature | “Thêm truy vấn tìm checkpoint hợp lệ.” | Là một phần Design/Build by Feature |
| **Quality constraint** | Điều kiện cần bảo vệ xuyên nhiều feature | “Không cho đọc tiến độ tài khoản khác.” | Được tích hợp vào thiết kế, kiểm thử và điều kiện Done của các feature liên quan |
| **Increment/release** | Phần sản phẩm sử dụng được hoặc được phát hành | “Học viên hợp lệ đã dùng được nút Học tiếp.” | Thường là kết quả tích hợp một hay nhiều features đạt chuẩn |

### Feature có cần mẫu “Là người dùng...” không?

Không. Mẫu user story giúp giao tiếp nhu cầu, còn feature trong FDD thường nhấn mạnh **hành động và kết quả cụ thể trong miền**. Có thể dùng cả hai:

> **Story:** “Là học viên đã đăng nhập, tôi muốn nhìn thấy bài đang học dở để tiếp tục nhanh.”
>
> **Feature:** “Hiển thị bài học dở gần nhất của học viên trong trang khóa học.”

Story tạo bối cảnh **vì sao**, còn feature giúp nhóm xác định **khả năng gì cần hiện thực hóa**. Hai bên phải cùng hiểu quy tắc và điều kiện chấp nhận; không nên dùng hai loại ticket trùng lặp chỉ để tạo thêm thủ tục quản lý.

### “Khách hàng có giá trị” không chỉ là màu nút

Một feature quan trọng có thể phục vụ **an toàn, tính chính xác, kiểm soát truy cập hoặc yêu cầu tuân thủ**, ngay cả khi người dùng không bấm thêm một nút mới. Nhưng cũng không nên gọi bất cứ task nội bộ nào là feature chỉ để dễ báo tiến độ. Cần chứng minh nó đem lại **một kết quả nghiệp vụ hoặc khả năng phục vụ có thể xác nhận**.

## 7. Ví dụ chi tiết: xây danh sách tính năng cho chức năng tiến độ học tập

Giả sử Product Owner cùng chuyên gia nghiệp vụ và Developers xác nhận mục tiêu:

> “Giúp học viên biết mình đã học tới đâu và quay lại đúng nội dung đã dừng, đồng thời bảo vệ dữ liệu tiến độ.”

Danh sách tính năng minh họa:

| Mã | Feature | Feature set | Giá trị/kết quả | Điều kiện liên quan |
| --- | --- | --- | --- | --- |
| **F-01** | Ghi nhận vị trí học hợp lệ cho một bài | Theo dõi tiến độ | Có checkpoint để tiếp tục học | Quyền sửa, tính hợp lệ, chống mất dữ liệu |
| **F-02** | Hiển thị bài đang dở trên trang khóa học | Theo dõi tiến độ | Học viên nhận ra điểm tiếp tục | Tài khoản, trạng thái bài, dữ liệu không hợp lệ |
| **F-03** | Mở bài đang dở tại vị trí đã lưu | Theo dõi tiến độ | Học viên tiếp tục học nhanh | Quyền đọc nội dung, vị trí được phép |
| **F-04** | Xác định một bài đã hoàn thành theo quy tắc loại bài | Hoàn tất bài học | Trạng thái hoàn thành nhất quán | Quy tắc video, quiz hoặc bài tập được làm rõ |
| **F-05** | Tính tỷ lệ hoàn thành của một khóa học | Tổng hợp khóa học | Có tiến độ tổng quan | Mẫu số và điều kiện hoàn thành rõ |
| **F-06** | Hiển thị tỷ lệ hoàn thành trong trang khóa học | Tổng hợp khóa học | Học viên nhìn thấy quá trình học | Không làm người học hiểu sai nếu dữ liệu chưa đủ |
| **F-07** | Truy xuất checkpoint từ thiết bị khác cùng tài khoản | Nhiều thiết bị | Có thể quay lại hành trình giữa thiết bị | Xác thực, dữ liệu đồng bộ |
| **F-08** | Bảo toàn checkpoint khi hai thiết bị cập nhật gần nhau | Nhiều thiết bị | Tránh ghi đè/mất tiến độ | Chính sách xung đột, thử tích hợp |
| **F-09** | Thông báo trạng thái lưu khi mạng gián đoạn | Khả năng phục hồi | Người dùng biết dữ liệu đã/ chưa được lưu | Không hiển thị thành công giả |
| **F-10** | Từ chối mở bài khi quyền học đã hết hạn | Quyền truy cập | Bảo vệ nội dung và dữ liệu | Quy tắc Enrollment bắt buộc |

**Thứ tự trong bảng không phải thứ tự triển khai bắt buộc.** Ví dụ F-10 là quy tắc bảo mật cần được đáp ứng **trong mọi lát cắt phát hành có truy cập nội dung**, chứ không phải “đợi tới feature cuối rồi mới khóa nội dung”. Nhóm có thể biểu diễn F-10 như một feature được xây/kiểm chứng sớm **và** một tiêu chuẩn áp dụng liên tục cho các feature sau.

### Một lát cắt sản phẩm có thể cần vài features

Để học viên thật sự dùng nút “Học tiếp”, sản phẩm có thể cần F-01 + F-02 + F-03 và kiểm soát quyền truy cập. Nếu chỉ giao F-01, khách hàng chưa chắc có trải nghiệm mới. Vì vậy, khi lập kế hoạch release, cần xác định **tập feature tối thiểu tạo ra hành vi end-to-end**, thay vì mặc định mỗi feature được tích hợp thì chắc chắn người dùng đã nhận đầy đủ giá trị.

**Feature nhỏ là đơn vị lập kế hoạch và triển khai; Increment có giá trị là kết quả tích hợp phù hợp.** Nhận biết sự khác biệt này giúp áp dụng FDD mà không rơi vào việc chỉ đếm số feature hoàn tất.

## 8. Phân rã feature lớn theo luồng, quy tắc và rủi ro

Một mục “Đồng bộ tiến độ trên mọi thiết bị trong mọi tình huống” quá lớn. Có thể tách theo ba góc nhìn:

| Góc nhìn | Cách tách | Ví dụ |
| --- | --- | --- |
| **Luồng sử dụng** | Từ hành trình phổ biến tới nhánh thay thế có giá trị | Tiếp tục trên một thiết bị → đọc checkpoint trên thiết bị thứ hai → xử lý kết nối lại |
| **Quy tắc nghiệp vụ** | Theo trạng thái và điều kiện thay đổi hành vi | Bài đang học → bài đã hoàn thành → khóa hết quyền → điều kiện tiên quyết |
| **Rủi ro** | Kiểm chứng sớm phần có hậu quả hoặc bất định cao | Xung đột ghi tiến độ, retry, quyền truy cập, migration |

### Ví dụ tách một feature quá lớn

**Quá lớn:** “Đồng bộ trạng thái toàn bộ khóa học giữa các thiết bị”.

**Các feature nhỏ hơn có thể kiểm chứng:**

1. Truy xuất checkpoint hợp lệ của cùng tài khoản trên một thiết bị thứ hai.
2. Hiển thị checkpoint vừa truy xuất để người học chọn bài cần tiếp tục.
3. Ghi checkpoint mới với cơ chế kiểm tra phiên bản theo chính sách miền.
4. Xử lý retry cho một cập nhật bị gián đoạn theo chính sách dữ liệu.
5. Thông báo khi có xung đột không thể giải quyết tự động một cách an toàn.

Đây là cách phân chia *gợi ý*. Nếu feature (1) thiếu kiểm soát truy cập hoặc có thể ghi đè dữ liệu của phiên khác thì **chưa đủ an toàn để giao riêng**. Không biến việc chia nhỏ thành lý do trì hoãn chất lượng bắt buộc.

### Kiểm tra từng feature bằng câu hỏi

- Hành vi này có kết quả nghiệp vụ cụ thể và quan sát được không?
- Có thể thiết kế, xây, kiểm thử và tích hợp trong một khoảng ngắn theo năng lực nhóm không?
- Cần đối tượng miền, lớp hoặc dịch vụ nào phối hợp?
- Rủi ro/phụ thuộc quan trọng đã được nêu rõ?
- Có thể đánh giá trạng thái Done thật, thay vì chỉ có tỷ lệ mã đã viết?
- Nếu phát hành riêng, người dùng hiểu rõ ranh giới và không bị tổn hại?

## 9. Hoạt động 3 — Plan by Feature: lập kế hoạch có căn cứ

Sau khi xây danh sách features, FDD tổ chức **thứ tự và trách nhiệm thực hiện theo feature**. Ở cách triển khai cổ điển, nhóm có thể gán **feature sets** cho những người dẫn dắt kỹ thuật và phân công trách nhiệm đối với các lớp trong mô hình. Kế hoạch phải xét **phụ thuộc, độ phức tạp, năng lực và giá trị**, không chỉ xếp theo mã số.

### Những đầu vào cần có

| Đầu vào | Câu hỏi | Minh họa |
| --- | --- | --- |
| **Giá trị và mục tiêu sản phẩm** | Feature nào giúp người dùng nhận kết quả mong muốn sớm? | F-01/02/03 tạo luồng “Học tiếp” |
| **Ưu tiên nghiệp vụ** | Trường hợp nào quan trọng cho phân khúc hiện tại? | Người học thường quay lại cùng thiết bị hay đổi thiết bị? |
| **Phụ thuộc mô hình** | Feature nào cần cùng đối tượng miền hoặc API? | F-05 cần quy tắc xác định trạng thái bài từ F-04 |
| **Rủi ro lớn** | Điều gì có thể gây hại nếu phát hiện muộn? | F-08 có thể ghi đè dữ liệu |
| **Năng lực kỹ thuật** | Những lớp, kiến thức hoặc môi trường nào có giới hạn? | Một số thay đổi cùng tác động Enrollment |
| **Dữ liệu hoàn tất trước đây** | Độ biến thiên của việc giao feature nhỏ là bao nhiêu? | Số feature Done và thời gian qua các bước |
| **Điều kiện chất lượng** | Có yêu cầu gì không được hoãn? | Phân quyền, kiểm thử, tích hợp, xử lý dữ liệu sai |

### Một kế hoạch minh họa

| Đợt định hướng | Features ưu tiên | Kết quả có thể học | Rủi ro phải kiểm soát |
| --- | --- | --- | --- |
| **Đợt A — Học tiếp trong phạm vi hẹp** | F-01, F-02, F-03 và kiểm soát quyền bắt buộc | Người học có tìm và mở lại đúng bài không? | Dữ liệu tiến độ, quyền theo tài khoản |
| **Đợt B — Tiến độ tổng quan** | F-04, F-05, F-06 | Tỷ lệ hoàn thành có giúp học viên hiểu lộ trình không? | Quy tắc hoàn thành theo loại bài |
| **Đợt C — Nhiều thiết bị** | F-07, F-08 và kiểm chứng xung đột | Chuyển thiết bị có hữu ích và đáng tin không? | Đồng thời, dữ liệu phiên, nhất quán |
| **Đợt D — Phục hồi** | F-09 và các mở rộng an toàn cần thiết | Người dùng mạng yếu có bớt mất tiến độ không? | Retry, thông báo trạng thái và mất dữ liệu |

Đây là **lộ trình dự kiến**, không phải hợp đồng khóa thứ tự hay ngày phát hành. Nếu nghiên cứu cho thấy học viên đổi thiết bị thường xuyên, nhóm có thể cần ưu tiên Đợt C sớm; nếu mô hình checkpoint chưa đủ an toàn, phải kiểm chứng trước khi mở rộng.

### Lập kế hoạch theo feature không có nghĩa lên lịch từng phút

FDD cổ điển nhấn mạnh việc theo dõi các feature nhỏ, nhưng trong môi trường phức tạp, ước lượng cần được xem là **dự báo với giả định**. Không thể từ việc feature trước xong trong ba ngày suy ra mọi feature còn lại cũng xong đúng ba ngày, đặc biệt khi loại quy tắc, dữ liệu và phụ thuộc khác nhau.

Kế hoạch nên có **điểm cập nhật khi học được thông tin mới**: phát hiện lỗi mô hình, dữ liệu nghiệp vụ thay đổi, năng lực giảm hoặc phản hồi người dùng bác bỏ ưu tiên.

## 10. Vai trò và cấu trúc tổ chức trong FDD cổ điển

Một đặc điểm đáng chú ý của FDD là những vai trò kỹ thuật tương đối rõ. Tên gọi và phân công thực tế có thể thay đổi theo tổ chức; **không nên bê nguyên một sơ đồ chức danh vào nhóm nhỏ nếu không mang lại lợi ích phối hợp**.

| Vai trò thường thấy | Đóng góp chủ yếu | Điều cần hiểu đúng |
| --- | --- | --- |
| **Domain expert** | Mô tả quy tắc, đối tượng và cách nghiệp vụ vận hành; xác nhận ví dụ | Không chỉ “ký duyệt tài liệu cuối cùng”; cần tham gia đủ sớm để giảm hiểu sai |
| **Chief architect** | Hỗ trợ mô hình và sự nhất quán kiến trúc giữa nhiều feature sets | Không nên biến thành người duy nhất được phép quyết định mọi chi tiết |
| **Chief programmer** | Dẫn dắt thiết kế/xây dựng một tập features và phối hợp feature team | Là vai trò điều phối kỹ thuật trong FDD cổ điển, không đồng nghĩa line manager |
| **Class owner** | Chịu trách nhiệm chính với thiết kế, mã và chất lượng những lớp được giao | *Individual class ownership* có thể tạo nút thắt nếu chỉ một người biết lớp đó |
| **Feature team** | Nhóm tạm thời tập hợp những người liên quan để thiết kế và xây feature | Có thể thay đổi theo feature, cần phối hợp tích hợp xuyên lớp |
| **Development manager / project manager** | Điều phối năng lực, lịch và phụ thuộc ở cấp phù hợp | Không thay chuyên môn kỹ thuật hoặc quyết định giá trị của người chịu trách nhiệm sản phẩm |
| **Vai trò hỗ trợ** | Kiểm thử, build, công cụ, triển khai, tài liệu và vận hành | Có thể được chia sẻ hoặc tích hợp trong team theo quy mô |

### Chief programmer và class owner phối hợp ra sao?

Giả sử F-03 cần thay đổi các lớp liên quan:

~~~text
Feature F-03: Mở đúng bài đang dở tại vị trí đã lưu

Chief programmer
  |
  +-- Class owner: Enrollment / AccessPolicy
  +-- Class owner: LearningProgress
  +-- Class owner: LessonNavigation
  '-- Developers hỗ trợ kiểm thử, giao diện, tích hợp và review
~~~

Chief programmer tập hợp những người có liên quan, giúp làm rõ thiết kế và ranh giới tương tác. Class owners xem xét các thay đổi thuộc phần mình chịu trách nhiệm; nhóm cần bảo đảm feature **hoạt động end-to-end**, không chỉ từng lớp riêng rẽ.

**Rủi ro:** nếu class owner nghỉ hoặc quá tải, công việc có thể bị chặn. Nhóm nên chia sẻ hiểu biết qua review, pair programming, tài liệu vừa đủ và thỏa thuận người thay thế. FDD cổ điển có **individual class ownership**, còn XP thường đề cao **collective code ownership**; đây là khác biệt thực sự cần cân nhắc, không nên nói hai thực hành giống nhau.

### Feature team không nhất thiết là bộ phận tồn tại cố định

Feature team theo FDD thường được **hình thành quanh công việc của một feature hoặc một nhóm nhỏ features**, gồm người sở hữu những lớp liên quan. Đó là một cách phối hợp xuyên thành phần; không nên mặc định mỗi feature tạo một phòng ban mới hoặc được gán cứng cho một cá nhân từ đầu đến cuối.

## 11. Hoạt động 4 — Design by Feature: thiết kế một tập nhỏ để có thể xây ngay

Sau khi chọn một nhóm features đủ nhỏ, **Design by Feature** tập trung vào giải pháp cho chính nhóm đó, dựa trên mô hình tổng thể đã có. Cách mô tả FDD cổ điển thường nhắc đến các bước như tập hợp feature team, walkthrough miền, nghiên cứu phương án, tạo **sequence diagram**, làm rõ các lớp liên quan và **design inspection**.

### Một chu trình thiết kế minh họa

1. **Chọn tập features nhỏ liên quan:** Ví dụ F-01 + F-03 cho lưu và mở lại tiến độ.
2. **Tập hợp người cần thiết:** Chief programmer, class owners liên quan và domain expert khi cần làm rõ quy tắc.
3. **Walkthrough bằng ví dụ nghiệp vụ:** Một học viên đã đăng nhập, có quyền học, checkpoint hợp lệ.
4. **Thiết kế tương tác:** Những thành phần nào kiểm tra quyền, đọc checkpoint và điều hướng tới bài?
5. **Kiểm tra các trường hợp khó:** Quyền học hết hạn, checkpoint cũ, cập nhật đồng thời.
6. **Review/inspection thiết kế:** Kiểm tra tính nhất quán với mô hình miền và các giới hạn chất lượng.
7. **Điều chỉnh mô hình hoặc kế hoạch nếu cần:** Không cố bảo vệ một sơ đồ khi bằng chứng chứng minh nó sai.

### Sequence diagram đơn giản cho F-03

~~~mermaid
sequenceDiagram
    actor Learner as Học viên
    participant UI as Trang khóa học
    participant Access as Kiểm tra quyền học
    participant Progress as Dịch vụ tiến độ
    participant Lesson as Điều hướng bài
    Learner->>UI: Chọn Học tiếp
    UI->>Access: Kiểm tra quyền vào khóa học
    alt Không có quyền
        Access-->>UI: Từ chối
        UI-->>Learner: Thông báo không thể truy cập
    else Có quyền
        Access-->>UI: Được phép
        UI->>Progress: Lấy checkpoint hợp lệ
        Progress-->>UI: Bài và vị trí được lưu
        UI->>Lesson: Mở bài tại vị trí hợp lệ
        Lesson-->>Learner: Nội dung đang học
    end
~~~

Sơ đồ chỉ phục vụ **thảo luận thiết kế**. Nó chưa mô tả đầy đủ xác thực, cache, thời hạn phiên, xử lý dữ liệu không hợp lệ hay cách API giao tiếp trong kiến trúc thực tế. Những ràng buộc ảnh hưởng tính an toàn phải được làm rõ và đưa vào kiểm thử, không được bỏ qua vì sơ đồ chỉ có “happy path”.

### Design inspection khác kéo dài thiết kế vô hạn

Một design inspection có mục tiêu rõ: người tham gia hiểu thiết kế có đáp ứng quy tắc và tích hợp được với mô hình hiện tại không. Nếu feature nhỏ mà cuộc review kéo dài nhiều tuần, nhóm cần xét có đang:

- Chọn feature quá lớn hoặc phụ thuộc quá nhiều không?
- Mô hình tổng thể quá cứng, không cho phép điều chỉnh?
- Thiếu người có thẩm quyền làm rõ quy tắc?
- Thiếu tiêu chí chất lượng và cách xác nhận?

**Thiết kế đủ để xây có trách nhiệm** là mục tiêu; không cần chứng minh mọi yêu cầu tương lai đã được giải quyết.

## 12. Hoạt động 5 — Build by Feature: từ thiết kế đến phần mềm đã tích hợp

**Build by Feature** đưa thiết kế của tập features nhỏ vào mã, kiểm thử, review và build tích hợp. Trong FDD cổ điển, các mô tả thường nhắc tới **class ownership, code inspection, unit testing và promote to build**. Cách triển khai cụ thể khác nhau theo công nghệ; điều quan trọng là **feature phải hoạt động và được tích hợp**, không chỉ “code đã viết xong”.

### Các hoạt động thực hành

| Bước | Câu hỏi chất lượng | Ví dụ |
| --- | --- | --- |
| **Viết/điều chỉnh mã theo feature** | Kết quả nghiệp vụ đã được hiện thực hóa chưa? | API lưu checkpoint đúng tài khoản và đúng bài |
| **Kiểm thử đơn vị** | Quy tắc và điều kiện biên có đúng không? | Không chấp nhận vị trí học ngoài phạm vi hợp lệ |
| **Kiểm tra mã / code inspection** | Thiết kế, tính dễ đọc, lỗi logic và rủi ro có được xem xét? | Review truy xuất dữ liệu và kiểm soát quyền |
| **Kiểm thử tích hợp** | Các lớp/dịch vụ có phối hợp chính xác không? | UI–API–dữ liệu thực sự mở đúng bài |
| **Promote/integrate to build** | Mã đạt điều kiện để đưa vào bản tích hợp chung chưa? | Pipeline CI xanh với tiêu chuẩn được thống nhất |
| **Xác nhận feature hoàn tất** | Điều kiện chấp nhận và chất lượng đã đủ chưa? | Người học hợp lệ sử dụng được luồng đã hứa |

### Minh họa kịch bản chấp nhận

~~~gherkin
Feature: Tiếp tục một bài học đang dở

  Scenario: Học viên có quyền tiếp tục bài học
    Given học viên đã đăng nhập và còn quyền truy cập khóa học K
      And học viên đang học dở bài B
      And checkpoint của bài B có giá trị hợp lệ
    When học viên chọn "Học tiếp" trên trang khóa học K
    Then hệ thống mở bài B tại vị trí checkpoint
      And không hiển thị tiến độ của tài khoản khác

  Scenario: Học viên không còn quyền truy cập
    Given học viên đã đăng nhập nhưng không còn quyền vào khóa học K
    When học viên yêu cầu mở bài B bằng tiến độ đã lưu
    Then hệ thống không trả nội dung được bảo vệ của bài B
      And phản hồi rõ rằng nội dung hiện không thể truy cập
~~~

**Kiểm thử chấp nhận không thay thế mọi kiểm thử kỹ thuật.** Với tiến độ học tập, kiểm thử concurrency, retry, migration, bảo mật và phục hồi có thể cần thiết dù không nằm trong hai kịch bản ngắn trên.

### “Promoted to build” có phải đã phát hành không?

Không nhất thiết. **Tích hợp thành công vào bản build chung** không đồng nghĩa tính năng đã được phát hành cho người dùng. Cần phân biệt:

- **Code complete:** người viết mã cho rằng phần thay đổi đã được triển khai.
- **Integrated/build verified:** tính năng đã hòa vào hệ thống và vượt các kiểm tra kỹ thuật đã thỏa thuận.
- **Feature Done:** đáp ứng điều kiện chức năng và chất lượng được định nghĩa.
- **Released:** người dùng/đối tượng được phép đã có thể sử dụng.
- **Outcome:** hành vi người dùng hoặc kết quả kinh doanh thực sự có thay đổi.

Một hệ thống có nhiều features “promoted to build” vẫn có thể chưa tạo **giá trị sử dụng được** nếu các chức năng chưa kết nối hoặc chưa được bật. Vì vậy, nhóm cần theo dõi cả **kết quả end-to-end**, không chỉ mốc kỹ thuật.

## 13. Một chu trình Design–Build by Feature thực tế

Giả sử nhóm ưu tiên hai features F-01 và F-03 để tạo luồng “Học tiếp”. Một chu trình triển khai có thể diễn ra như sau:

| Giai đoạn | Hoạt động | Dấu hiệu hoàn tất |
| --- | --- | --- |
| **Làm rõ** | Domain expert nêu quy tắc quyền học, vị trí hợp lệ và trạng thái bài | Developers có ví dụ đúng/sai rõ |
| **Thiết kế** | Feature team rà mô hình và tương tác UI–API–dữ liệu | Thiết kế được review, rủi ro lớn lộ ra |
| **Xây lát cắt nhỏ** | Triển khai hành trình đầu-cuối tối thiểu | Học viên thử được luồng hợp lệ trên môi trường phù hợp |
| **Kiểm thử và sửa** | Test đơn vị, tích hợp, phân quyền, dữ liệu lỗi | Không còn điều kiện chất lượng bắt buộc chưa đạt |
| **Tích hợp** | CI và build chung được xác nhận | Tính năng không gây lỗi hồi quy đã biết |
| **Phản hồi** | Demo/quan sát với người dùng hoặc bên hiểu nghiệp vụ | Có quyết định rõ về mở rộng, sửa hoặc thay ưu tiên |

Những bước này **có thể lặp và chồng lấn**, không cần chờ mọi sơ đồ được “đóng dấu xong” trước khi bắt đầu kiểm chứng một phần code. Khi F-01 hoạt động, thiết kế của F-03 có thể được làm rõ dựa trên kết quả vừa học được.

### Điều gì được chuyển sang feature sau?

Những phần **mở rộng phạm vi** có thể được lập kế hoạch ở feature tiếp theo, ví dụ đồng bộ offline hoặc lịch sử tiến độ nhiều khóa học. Nhưng những phần **bắt buộc để tính năng đang giao an toàn và đúng** không được hoãn:

- Xác thực và quyền truy cập theo tài khoản.
- Tính đúng đắn của checkpoint trong phạm vi hỗ trợ.
- Xử lý dữ liệu sai, mất kết nối và lỗi theo cách không báo thành công giả.
- Kiểm thử và yêu cầu chất lượng đã thỏa thuận.

Đó là nguyên tắc giúp việc giao tăng dần không trở thành phát hành phần mềm thiếu tin cậy.

## 14. Kiểm soát phụ thuộc khi nhiều feature dùng chung mô hình

FDD có lợi thế khi làm rõ đối tượng miền, nhưng một feature có thể chạm nhiều lớp. Hai feature được phát triển song song cũng có thể thay đổi cùng một lớp hoặc chính sách dữ liệu.

### Ba kiểu phụ thuộc thường gặp

| Loại phụ thuộc | Ví dụ | Cách giảm rủi ro |
| --- | --- | --- |
| **Nghiệp vụ** | F-05 tỷ lệ hoàn thành cần quy tắc bài hoàn thành ở F-04 | Làm rõ quy tắc mẫu số và thứ tự phát hành |
| **Mô hình/kỹ thuật** | F-01 và F-08 cùng sửa LearningProgress | Phối hợp class owners, kiểm thử tích hợp, contract rõ |
| **Tổ chức** | Cần domain expert xác nhận quyền học trước khi tích hợp | Đặt nhịp trao đổi sớm, ghi câu hỏi và người quyết định |

### Quản lý công việc cùng chạm một lớp

Nếu class owner của **LearningProgress** liên tục bị ba feature teams yêu cầu sửa cùng lúc, không thể chỉ “tăng số feature đang làm” để tăng tốc. Cần:

1. Quan sát số công việc cùng dở và thời gian chờ class owner.
2. Ưu tiên feature tạo giá trị sớm hoặc rủi ro cần kiểm chứng.
3. Làm rõ hợp đồng và các thay đổi tương thích.
4. Chia sẻ kiến thức, review và thử pair programming để giảm phụ thuộc một người.
5. Điều chỉnh thứ tự features và năng lực trước khi bắt đầu quá nhiều việc.

Điều này nối FDD với tư duy **giới hạn WIP và quản lý flow trong Kanban**. Số lượng feature teams không phải chỉ số tốt nếu tất cả đều chờ một điểm nghẽn chung.

### “Class ownership” có cần giữ nguyên khi tích hợp XP?

Không có một câu trả lời áp dụng mọi nơi. **Individual class ownership** giúp rõ trách nhiệm về mô hình và thay đổi; **collective ownership** của XP giúp nhiều Developers có thể cải thiện mã khi cần. Khi kết hợp, nhóm cần một **chính sách ownership nhất quán**: ai được sửa, ai cần review, xử lý blocker ra sao và bằng chứng chất lượng nào bảo vệ các thay đổi.

Không nên tuyên bố vừa có “chỉ class owner được sửa mã” vừa có “mọi Developers được sửa mọi mã không cần phối hợp” mà không giải quyết xung đột chính sách.

## 15. Lập kế hoạch phát hành theo features, không nhầm với nhịp kỹ thuật

FDD nhấn mạnh việc **thiết kế và xây các feature nhỏ**. Tuy nhiên, một feature hoàn tất **không tự bắt buộc** một lần deploy hoặc public release. Tùy bối cảnh, nhóm có thể tích hợp liên tục và phát hành nhiều features cùng tạo một hành vi.

### Bốn câu hỏi cho một đợt phát hành

1. **Người dùng nhận được điều gì?** Một thao tác có ích hay chỉ vài lớp kỹ thuật?
2. **Chất lượng đã đủ chưa?** Feature đã tích hợp, kiểm thử, bảo vệ dữ liệu và giám sát phù hợp?
3. **Phạm vi hỗ trợ là gì?** Có cần feature flag, thử với nhóm người dùng giới hạn hoặc thông báo giới hạn?
4. **Sau phát hành ta học được gì?** Có dữ liệu hành vi, lỗi và phản hồi định tính đủ để điều chỉnh ưu tiên?

### Ví dụ các mốc độc lập

~~~text
Feature F-01 được thiết kế + triển khai
         |
         v
Feature F-02 được tích hợp với F-01
         |
         v
Kiểm thử hành trình "Học tiếp" + quyền truy cập
         |
         v
Increment đủ chất lượng để phát hành an toàn
         |
         v
Release cho nhóm học viên phù hợp
         |
         v
Quan sát giá trị và lỗi, cập nhật Features List
~~~

Nếu dùng **feature flag**, nhóm có thể deploy code nhưng chưa bật tính năng cho người dùng. Do đó phải nói rõ **“tích hợp”, “deploy”, “release” và “đạt outcome”** là các sự kiện khác nhau.

### Kiểm thử và vận hành không phải bước tùy chọn

Một lát cắt nhỏ có thể làm hỏng hệ thống lớn nếu thay đổi schema sai hoặc lộ dữ liệu. Kế hoạch phát hành phù hợp cần:

- Kiểm tra tương thích API và dữ liệu.
- Xác định cách phát hiện lỗi ngay sau release.
- Có phương án rollback hoặc roll-forward; lưu ý rollback code không luôn đảo được thay đổi dữ liệu.
- Rõ người chịu trách nhiệm vận hành và xử lý sự cố.
- Không công bố tính năng đã hỗ trợ những trường hợp mà thực tế chưa có.

## 16. Đo tiến độ FDD: mốc kỹ thuật và kết quả hoàn tất

FDD được biết đến với các cơ chế **theo dõi tiến độ theo feature**. Những mô tả cổ điển có thể chia vòng đời feature thành các milestone như:

1. **Domain walkthrough** — rà soát miền nghiệp vụ.
2. **Design** — tạo thiết kế cho feature.
3. **Design inspection** — kiểm tra thiết kế.
4. **Code** — triển khai mã.
5. **Code inspection** — kiểm tra mã.
6. **Promote to build** — tích hợp vào bản build chung.

Đây là **cách biểu diễn tiến độ trong một số tài liệu FDD cổ điển**; không nên coi tên từng milestone hay trọng số phần trăm của chúng là quy tắc áp dụng cho mọi nhóm hiện đại.

### Ví dụ trạng thái thực tế

| Feature | Domain/design | Code/inspection | Tích hợp và kiểm thử | Trạng thái giá trị |
| --- | --- | --- | --- | --- |
| **F-01 Lưu checkpoint** | Đã rà soát | Đã triển khai | Đạt kiểm thử theo phạm vi | Có khả năng lưu dữ liệu hợp lệ, cần tích hợp trải nghiệm |
| **F-02 Hiển thị bài dở** | Đã rà soát | Đang review | Chưa có luồng hoàn chỉnh | Chưa Done |
| **F-03 Mở bài tại checkpoint** | Đang thiết kế | Chưa triển khai | Chưa kiểm thử | Chưa Done |
| **F-08 Tránh ghi đè cạnh tranh** | Rủi ro đã nhận diện | Chưa đủ phương án | Cần thử kỹ thuật trước | Chưa Done; nếu ảnh hưởng phạm vi hiện tại phải ưu tiên xử lý |

Mọi người có thể thấy tiến độ kỹ thuật nhưng không nên tuyên bố **“75% tính năng đã đem tới người dùng”** chỉ vì phần lớn milestone đã được đánh dấu. Một feature có thể hoàn thành 90% code và vẫn thiếu kiểm thử bảo mật quan trọng, khiến sản phẩm chưa thể dùng an toàn.

### Tiến độ theo feature cần gắn với kết quả

Nên phân biệt:

- **Milestone kỹ thuật đã đạt:** cho biết công việc đang ở đâu.
- **Feature Done theo chính sách chất lượng:** năng lực cụ thể đã hoàn thành.
- **Tập features thành Increment sử dụng được:** có một hành vi đầu-cuối cho người nhận giá trị.
- **Outcome:** thực tế người dùng có sử dụng và được lợi không.

Một báo cáo tốt nên làm rõ cả bốn mức, thay vì đổi tên milestone kỹ thuật thành kết quả kinh doanh.

## 17. Kết hợp dữ liệu flow với kế hoạch FDD

Khi một nhóm có hàng chục features, **chỉ nhìn số feature đang phát triển** chưa đủ. Những số đo dòng công việc của Kanban giúp nhận ra việc nào đang trì hoãn kết quả.

| Chỉ số | Câu hỏi | Lưu ý khi dùng trong FDD |
| --- | --- | --- |
| **Throughput** | Bao nhiêu features đạt điểm kết thúc được định nghĩa trong mỗi tuần? | Chỉ so sánh khi kích thước/loại feature và tiêu chuẩn Done tương đối nhất quán |
| **Cycle time** | Một feature từ lúc bắt đầu đến điểm Done mất bao lâu? | Không nhầm với chỉ số thời lượng code riêng lẻ |
| **Work item age** | Feature nào chưa Done đã nằm trong workflow quá lâu? | Có thể chỉ ra chờ class owner, domain expert hoặc tích hợp |
| **WIP** | Có bao nhiêu features đã bắt đầu nhưng chưa hoàn tất? | WIP quá lớn có thể làm mọi feature team dở dang |
| **Defects / rework** | Có bao nhiêu phần bị sửa lại hoặc gây lỗi sau tích hợp? | Flow nhanh do bỏ quality gate có thể làm rủi ro tăng |
| **Outcome metrics** | Khách hàng nhận giá trị mong muốn chưa? | Feature Done không tự chứng minh giá trị sản phẩm |

### Ví dụ diễn giải throughput

Trong bốn tuần, nhóm hoàn thành các feature theo tuần: **3, 4, 2, 5**. Tổng throughput của bốn tuần là:

\[
3+4+2+5=14\ \text{features}
\]

Throughput trung bình là:

\[
\frac{14}{4}=3{,}5\ \text{features/tuần}
\]

Nếu còn 14 features, phép chia 14/3,5 cho một **ước lượng sơ bộ bốn tuần**, **không phải xác suất chắc chắn hoàn tất sau bốn tuần**. Sẽ sai nếu những feature còn lại khó hơn, có phụ thuộc API mới, nhiều người nghỉ hoặc scope tăng.

### Cách dùng số liệu có trách nhiệm

1. Ghi rõ **điểm bắt đầu, điểm kết thúc và điều kiện Done** của một feature.
2. Xem phân bố thời gian, không chỉ một trung bình.
3. Tách những loại feature rất khác nhau nếu dữ liệu quá không đồng dạng.
4. Theo dõi blocked time và work item age để gỡ tắc trước khi quá muộn.
5. Cập nhật dự báo khi mô hình, phạm vi, team hoặc năng lực thay đổi.
6. Không dùng số feature hay số ticket để xếp hạng năng suất từng cá nhân.

**Các con số trên chỉ minh họa phép tính**, không phải dữ liệu thực nghiệm xác minh FDD sẽ đạt một mức throughput cụ thể.

## 18. Ví dụ xuyên suốt: áp dụng năm hoạt động FDD cho “Học tiếp”

Đây là **case study giả định** nhằm nối tất cả các phần của bài.

### 18.1. Bối cảnh

Một nền tảng có nhiều khóa học, mỗi khóa có thể có video và bài kiểm tra. Học viên phàn nàn mất nhiều thời gian tìm bài đang dở. Nhóm sản phẩm muốn học viên mở lại đúng vị trí nhanh hơn, nhưng chưa biết nhu cầu đồng bộ giữa thiết bị lớn đến đâu. Hệ thống có ràng buộc quan trọng: **không làm lộ dữ liệu tiến độ giữa tài khoản và không cho học nội dung hết quyền**.

### 18.2. Hoạt động 1 — Develop an Overall Model

Domain experts cùng Developers rà các khái niệm **Learner, Enrollment, Course, Lesson, LearningProgress** và quy tắc:

- Học viên có thể có nhiều khóa học.
- Tiến độ được xác định cho bài và chủ thể học phù hợp.
- Chỉ học viên có quyền mới được truy cập nội dung tương ứng.
- Bài đã hoàn thành có hành vi khác với bài đang học.
- Cần làm rõ cách chọn checkpoint khi có nhiều phiên cập nhật.

Đầu ra là **bức tranh miền đủ dùng** và danh sách câu hỏi còn thiếu, không phải cơ sở dữ liệu chi tiết đã đóng băng.

### 18.3. Hoạt động 2 — Build a Features List

Nhóm phân thành các sets:

- **Theo dõi tiến độ:** lưu checkpoint, đọc checkpoint, hiển thị bài dở.
- **Điều hướng học:** mở bài hợp lệ, xử lý bài đã hoàn thành.
- **Kiểm soát truy cập:** bảo vệ quyền đọc nội dung và dữ liệu tiến độ.
- **Đa thiết bị:** truy xuất xuyên thiết bị và bảo toàn cập nhật cạnh tranh.

Mỗi feature được viết bằng **kết quả**, không chia thành “tạo bảng – làm API – làm UI”.

### 18.4. Hoạt động 3 — Plan by Feature

Người quyết định sản phẩm ưu tiên **luồng “Học tiếp” trực tuyến trên cùng thiết bị** nhằm kiểm chứng vấn đề. Developers chỉ ra phải kiểm tra phân quyền và tính nhất quán dữ liệu ngay. Nhóm chọn tập feature nhỏ tạo được luồng hoàn chỉnh, đánh dấu những feature đa thiết bị là phần mở rộng có rủi ro cao cần nghiên cứu sớm.

### 18.5. Hoạt động 4 — Design by Feature

Feature team đi qua kịch bản:

> “Học viên đã đăng nhập, còn quyền vào khóa học và có checkpoint hợp lệ → chọn ‘Học tiếp’ → hệ thống mở đúng bài tại đúng vị trí.”

Họ xác định nơi kiểm tra quyền, cách lấy checkpoint và phản hồi khi không có checkpoint. Thiết kế được review cùng người hiểu quy tắc; phần mô hình phát hiện sai được điều chỉnh trước khi đầu tư lớn.

### 18.6. Hoạt động 5 — Build by Feature

Developers triển khai một lát cắt end-to-end, kiểm thử, code review và tích hợp thường xuyên. Một kiểm thử phát hiện checkpoint có thể bị ghi đè khi người học mở hai tab đồng thời. Nhóm **không đợi feature “đồng bộ đa thiết bị” về sau mới xử lý** nếu lỗi có thể ảnh hưởng hành vi đã hứa. Họ thêm kiểm thử và giải pháp bảo toàn dữ liệu cần thiết, đồng thời làm rõ phạm vi thử nghiệm.

### 18.7. Release và nhận phản hồi

Khi Increment đủ chất lượng, nhóm bật tính năng cho đối tượng học viên phù hợp, quan sát:

- Người học có tìm thấy nút và tiếp tục đúng bài không?
- Thời gian để mở lại bài thay đổi thế nào?
- Có lỗi mất checkpoint hoặc truy cập sai quyền không?
- Những người đổi thiết bị có thực sự cần hỗ trợ tốt hơn không?

Product Owner/người chịu trách nhiệm giá trị sử dụng bằng chứng đó cùng Developers để **cập nhật Features List và Plan by Feature**. Nếu dữ liệu chỉ ra bài kiểm tra không hỗ trợ checkpoint như video, nhóm có thể ưu tiên điều chỉnh mô hình và quy tắc thay vì tiếp tục theo thứ tự cũ.

## 19. FDD và phản hồi sớm: điểm mạnh lẫn giới hạn

FDD có những lợi thế rõ trong hệ thống nghiệp vụ phức tạp, nhưng cần tránh xem “có danh sách feature” là tương đương “đã kiểm chứng giá trị”.

### Những điểm có thể mạnh

| Điểm mạnh | Ý nghĩa thực tế |
| --- | --- |
| **Mô hình miền giúp giao tiếp** | Hệ thống có nhiều quy tắc được mô tả bằng ngôn ngữ chung, giảm hiểu nhầm giữa kinh doanh và kỹ thuật |
| **Danh sách features có cấu trúc** | Dễ nhìn các năng lực nhỏ và mối quan hệ giữa chúng |
| **Chu kỳ Design/Build by Feature** | Giảm kích thước lô thay đổi, giúp tích hợp và kiểm tra từng phần |
| **Trách nhiệm kỹ thuật cụ thể** | Nhóm lớn có thể biết người liên quan tới lớp và nhóm feature nào |
| **Milestone rõ** | Giúp phát hiện feature nào đang ở thiết kế, kiểm tra hay tích hợp |

### Những điểm cần thận trọng

| Rủi ro | Hậu quả có thể xảy ra | Cách giảm thiểu |
| --- | --- | --- |
| **Mô hình hóa quá lâu trước khi giao** | Phản hồi người dùng đến muộn, mô hình không được kiểm chứng | Đặt giới hạn cho mô hình ban đầu, thử lát cắt nhỏ sớm |
| **Feature list bị đóng băng** | Kế hoạch không còn phản ánh nhu cầu | Đưa phản hồi vào list và thứ tự ưu tiên |
| **Nhấn mạnh class ownership quá mức** | Nút thắt một người, silo kiến thức | Review, pairing, chia sẻ hiểu biết, chính sách ownership rõ |
| **Đếm milestone thay vì giá trị** | Báo cáo “gần 100%” nhưng người dùng chưa dùng được | Theo dõi Increment, release và outcome riêng |
| **Thiếu người đại diện khách hàng** | Feature đúng mô hình kỹ thuật nhưng sai nhu cầu | Tổ chức tiếp xúc domain experts và người dùng |
| **Feature quá nhỏ thành task** | Throughput tăng giả, mất kết quả nghiệp vụ | Kiểm tra từng feature có hành vi/kết quả độc lập |

**FDD không tự bảo đảm việc học nhanh từ thị trường.** Muốn thích ứng tốt, nhóm vẫn cần **phát hành các lát cắt sử dụng được, quan sát người dùng và sắp xếp lại thứ tự dựa trên bằng chứng**.

## 20. So sánh FDD với Scrum, Kanban và XP

Các cách tiếp cận có trọng tâm khác nhau, có thể bổ trợ nhưng không nên đồng nhất:

| Khía cạnh | **FDD** | **Scrum** | **Kanban** | **XP** |
| --- | --- | --- | --- | --- |
| **Đơn vị tổ chức nổi bật** | Feature nhỏ có ý nghĩa nghiệp vụ, gắn với mô hình miền | Product Backlog Items được chọn để đạt Sprint Goal | Work items qua Definition of Workflow | User stories/khả năng nhỏ và các thực hành kỹ thuật |
| **Nhịp làm việc** | Design/Build theo từng feature; có thể lập lịch theo nhóm feature | Sprint timebox cố định, tối đa một tháng | Flow có thể liên tục, kéo theo năng lực | Các vòng phản hồi kỹ thuật và kế hoạch ngắn, small releases |
| **Lập kế hoạch** | Plan by Feature sau mô hình và Features List | Sprint Planning: Why–What–How | Replenishment, chính sách pull/WIP, điều hành flow | Planning Game, cộng tác nghiệp vụ–kỹ thuật |
| **Cách phản hồi** | Kiểm tra thiết kế, mã, tích hợp từng feature; cần bổ sung feedback người dùng | Daily Scrum, Sprint Review, Retrospective và phản hồi trong Sprint | WIP, cycle time, age, throughput, SLE và vòng phản hồi | TDD, CI, pair programming, phát hành nhỏ và khách hàng gần nhóm |
| **Trách nhiệm kỹ thuật** | Chief programmer, feature teams, class owners trong FDD cổ điển | Developers tự quản; Scrum Guide không quy định class owner | Không quy định vai trò kỹ thuật cụ thể | Thường nhấn mạnh hợp tác và collective code ownership |
| **Điểm dễ lạm dụng** | Mô hình và milestone trở thành mục đích | Sprint bị biến thành danh sách ticket cố định | Có bảng mà không có chính sách/flow | “Ra thật nhanh” nhưng bỏ kỷ luật kỹ thuật |

### Khi nhóm dùng Scrum muốn học từ FDD

Một Scrum Team có thể sử dụng:

- **Mô hình miền nhẹ** để làm rõ những quy tắc phức tạp của Product Backlog.
- **Feature sets** để nhóm các PBIs theo khả năng nghiệp vụ.
- **Design/Build by Feature** như cách Developers tổ chức kỹ thuật trong Sprint.
- **Review mô hình và kiểm thử theo từng feature** để tăng tính nhất quán.

Nhưng Scrum Team vẫn giữ **Product Goal, Sprint Goal, Sprint Backlog, Increment và Definition of Done**, cùng các trách nhiệm của Scrum. Không tự biến chief programmer thành người thay Product Owner quyết định ưu tiên.

### Khi nhóm dùng Kanban muốn áp dụng FDD

Nhóm có thể định nghĩa **feature** là work item, sử dụng **Definition of Workflow, WIP và flow metrics** để giới hạn số feature đang làm, theo dõi tuổi việc và cải tiến tắc nghẽn giữa thiết kế–review–tích hợp.

Không nhất thiết thêm Sprint hay một kế hoạch cố định hai tuần mới có thể áp dụng FDD. **FDD không thay thế việc quản lý luồng**; nó cung cấp cấu trúc feature và cách tổ chức xây dựng.

### Khi kết hợp XP

TDD, CI, refactoring, pair programming và các kiểm thử chấp nhận có thể giúp **Build by Feature** diễn ra nhanh và an toàn hơn. Tuy nhiên, cần chủ động giải quyết khác biệt về **class ownership** và sự tự chủ của Developers.

## 21. Lựa chọn FDD khi nào: một khung quyết định

FDD có thể đáng cân nhắc khi:

- Miền nghiệp vụ có **nhiều đối tượng, quy tắc và tương tác** cần thống nhất ngôn ngữ.
- Sản phẩm có thể chia thành **nhiều khả năng nhỏ có giá trị** và được tích hợp dần.
- Nhóm có đủ người hiểu miền và năng lực kỹ thuật để review thiết kế, code và tích hợp thường xuyên.
- Tổ chức muốn minh bạch tiến độ theo những tính năng nhỏ thay vì theo từng phòng ban.
- Cần điều phối một số nhóm làm việc trên mô hình dùng chung, với chính sách ownership rõ.

FDD có thể không phải lựa chọn đầu tiên nếu:

- Sản phẩm chỉ là prototype rất nhỏ, miền đơn giản, giá trị cần kiểm chứng ngay với người dùng.
- Người hiểu nghiệp vụ không sẵn sàng tham gia, khiến feature list được tạo từ suy đoán.
- Phần lớn công việc là vận hành không dự báo được và không có các features nhỏ tương đối ổn định; một workflow Kanban rõ có thể phù hợp hơn làm khung chính.
- Nhóm có năng lực triển khai nhỏ, dùng chức danh chief programmer/class owner riêng biệt sẽ tạo thêm thủ tục.
- Tổ chức có xu hướng **đóng băng mô hình và kế hoạch**, biến FDD thành phân đoạn thác nước.

### Các câu hỏi kiểm tra trước khi chọn

1. Vấn đề lớn nhất của nhóm là **không hiểu miền**, **không biết ưu tiên**, **chậm tích hợp**, **WIP cao** hay **thiếu phản hồi người dùng**?
2. Có thể định nghĩa đơn vị feature nhỏ mà **khách hàng nhận ra kết quả** không?
3. Có người hiểu nghiệp vụ đủ gần để làm rõ quy tắc và xác nhận giả định không?
4. Những vai trò và chính sách ownership nào **thực sự giảm phụ thuộc**, thay vì tạo thêm nút thắt?
5. Nhóm có năng lực kiểm thử, tích hợp, release và đo outcome đủ để học từ feature không?
6. Có cách **cập nhật Features List** khi phản hồi thực tế khác dự đoán không?

**Chọn phương pháp vì loại vấn đề cần giải quyết, không vì nó có tên viết tắt hay sơ đồ quy trình đẹp.**

## 22. Những phản mẫu phổ biến trong FDD

### 22.1. Đổi tên mọi task thành feature

“Tạo repository”, “viết DTO”, “thêm cột database” là công việc kỹ thuật cần thiết, nhưng nếu đứng riêng thường chưa có kết quả nghiệp vụ. Hãy nhóm task vào feature có hành vi và tiêu chí xác nhận rõ.

### 22.2. Mô hình tổng thể phải hoàn hảo mới được viết mã

Đợi giải quyết mọi quy tắc và đối tượng có thể gặp trong ba năm tới khiến nhóm khó nhận phản hồi từ hệ thống thật. Hãy xây mô hình **đủ dùng**, thử một lát cắt nhỏ và cập nhật khi có bằng chứng.

### 22.3. Feature list không bao giờ đổi sau khi được phê duyệt

Nếu người dùng không cần tính năng dự đoán trước đó, tiếp tục xây chỉ để bảo vệ danh sách là đánh mất khả năng thích ứng. Cần cho phép **sắp xếp lại, tách, gộp, bổ sung hoặc bỏ feature** có lý do.

### 22.4. Cứ đúng hai tuần là mọi feature phải hoàn thành

Thời lượng hai tuần là heuristic lịch sử về **kích thước mục tiêu**, không phải giấy phép tuyên bố Done trước khi kiểm thử. Nếu quá lớn, chia nhỏ có giá trị và xử lý rủi ro; không hạ tiêu chuẩn chất lượng.

### 22.5. Chỉ giao các lớp kỹ thuật

Một feature bị chia thành đợt database, đợt API, đợt UI nhưng chưa có hành trình người dùng có thể thử không tạo feedback sản phẩm sớm. Cần đưa một lát cắt **end-to-end** đến Done.

### 22.6. Xem chief programmer là người duy nhất có quyền quyết định

Vai trò kỹ thuật quan trọng không thay thế phản hồi khách hàng, sự phối hợp của các Developers hoặc trách nhiệm quản trị giá trị. Cần tránh mô hình “một người giao việc, những người còn lại chỉ thực hiện”.

### 22.7. Class owner là người duy nhất được phép hiểu hoặc sửa lớp

Ownership quá chặt gây chờ đợi và silo kiến thức. Review, pairing, tài liệu vừa đủ và người thay thế giúp giảm rủi ro.

### 22.8. Đánh đồng % milestone với % giá trị đã giao

Hoàn thành nhiều bước design/inspection nhưng chưa kiểm thử tích hợp không chứng minh hệ thống đã dùng được. Báo cáo riêng các mốc **technical, feature Done, release và outcome**.

### 22.9. Làm thật nhiều feature cùng lúc để tận dụng nhân sự

WIP cao có thể khiến nhiều features chờ class owner và kiểm thử, cycle time kéo dài. Hãy ưu tiên hoàn tất công việc đã bắt đầu trước khi kéo thêm.

### 22.10. Dồn kiểm thử và tích hợp tới cuối chu kỳ

Nếu từng lớp chạy riêng nhưng cuối cùng mới tích hợp, lỗi quan hệ miền và API lộ ra muộn. CI, kiểm thử tự động, review và tích hợp thường xuyên giúp giảm rủi ro.

### 22.11. Mở rộng chức năng trước khi xử lý an toàn bắt buộc

Phân quyền và tính đúng đắn dữ liệu không phải “feature nâng cao có thể làm sau” nếu hệ thống đã cho phép truy cập dữ liệu thật. Những điều kiện bắt buộc phải được tích hợp từ lát cắt đầu.

### 22.12. Dùng số feature đóng để xếp hạng từng người

Số lượng feature Done phụ thuộc kích thước, rủi ro, phối hợp và cách chia. Đo cá nhân đơn giản khuyến khích chia vụn, né việc khó và che giấu lỗi. Nên dùng số liệu để **cải thiện hệ thống**, không làm chỉ tiêu thiếu bối cảnh.

### 22.13. Đã tích hợp là đã tạo giá trị khách hàng

Code có thể ở production sau feature flag mà chưa ai dùng, hoặc UI đã bật nhưng không giải quyết vấn đề. Cần theo dõi release thật và phản hồi người dùng.

### 22.14. Sao chép nguyên mọi vai trò FDD vào nhóm nhỏ

Một nhóm năm người không nhất thiết cần nhiều chức danh chuyên biệt để thực hành feature list và design/build theo tính năng. Giữ **trách nhiệm rõ, chi phí điều phối thấp và phản hồi nhanh**.

## 23. Workshop thực hành: từ nhu cầu tới feature và kế hoạch

Đây là **bài tập mô phỏng 60–90 phút** dành cho nhóm học Agile, không phải thời lượng bắt buộc trong FDD.

| Bước | Thời lượng tham khảo | Việc thực hiện | Sản phẩm đầu ra |
| --- | --- | --- | --- |
| **1. Hiểu mục tiêu** | 10 phút | Làm rõ người dùng, vấn đề và kết quả muốn có | Một câu mục tiêu giá trị |
| **2. Domain walkthrough** | 15 phút | Vẽ các đối tượng miền và quy tắc quan trọng | Mô hình miền đơn giản và câu hỏi mở |
| **3. Lập Features List** | 15–20 phút | Phân major feature set → feature set → features | Danh sách tính năng nhỏ theo kết quả |
| **4. Plan by Feature** | 10–15 phút | Sắp theo giá trị, rủi ro, phụ thuộc và năng lực | Tập features ưu tiên, thứ tự có lý do |
| **5. Design by Feature** | 10–15 phút | Chọn 1–2 features, lập sơ đồ tương tác và tình huống biên | Thiết kế đủ dùng, rủi ro cần kiểm chứng |
| **6. Build/release plan** | 10–15 phút | Xác định kiểm thử, review, CI, Done và cách nhận phản hồi | Kế hoạch xây và giao lát cắt an toàn |

### Tình huống cho workshop

> “Trung tâm đào tạo muốn học viên đăng ký khóa học, theo dõi tỷ lệ hoàn thành và nhận chứng nhận sau khi đạt điều kiện.”

Hãy bắt đầu bằng các đối tượng **Learner, Course, Enrollment, Lesson, CompletionRule, Certificate**. Đừng viết code trước khi đã thống nhất ít nhất các quy tắc nền tảng:

- Đăng ký nào tạo quyền học?
- Khi nào một bài được tính hoàn thành?
- Có điều kiện tiên quyết, điểm trắc nghiệm và giới hạn thời gian không?
- Khi nào được cấp chứng nhận và có thể bị thu hồi không?
- Những dữ liệu cá nhân nào phải được bảo vệ?

Sau đó thử tạo danh sách:

~~~text
Major feature set: Quản lý hoàn thành khóa học
  Feature set: Đánh giá hoàn tất bài học
    - Xác định trạng thái hoàn tất của một bài theo loại bài
    - Tổng hợp số bài đạt điều kiện trong khóa học
  Feature set: Cấp chứng nhận
    - Xác nhận học viên đạt điều kiện nhận chứng nhận
    - Tạo chứng nhận cho một học viên đã đủ điều kiện
    - Hiển thị chứng nhận cho đúng chủ tài khoản
~~~

**Câu hỏi cuối workshop:** Feature nào có thể phát triển đầu tiên để tạo giá trị nhỏ nhưng có thật? Nếu “Cấp chứng nhận” chưa thể thử vì quy tắc hoàn tất còn mơ hồ, nên làm rõ điều gì hoặc thử feature nào trước? Cần chính sách bảo mật nào ngay từ đầu?

## 24. Bài tập tự kiểm tra và gợi ý

### Bài tập A — Nhận diện năm hoạt động

Phân loại các mô tả:

1. “Người hiểu nghiệp vụ và Developers xác định Enrollment liên quan Course và Learner thế nào.”
2. “Nhóm viết ‘Tính tỷ lệ hoàn thành khóa học’ thay cho ‘Xây hệ thống tiến độ’.”
3. “Nhóm chọn feature ưu tiên theo giá trị, phụ thuộc và năng lực của class owners.”
4. “Feature team tạo sequence diagram và tổ chức design inspection.”
5. “Developers triển khai, unit test, review và tích hợp vào build chung.”

**Gợi ý:** (1) Develop an Overall Model; (2) Build a Features List; (3) Plan by Feature; (4) Design by Feature; (5) Build by Feature.

### Bài tập B — Feature hay task kỹ thuật?

Phân loại:

| Mục | Đề xuất |
| --- | --- |
| A | “Tạo bảng progress và migration cho cơ sở dữ liệu.” |
| B | “Hiển thị bài đang học dở trên trang khóa học cho học viên hợp lệ.” |
| C | “Từ chối truy cập nội dung đã hết quyền.” |
| D | “Refactor tên biến trong module tiến độ.” |
| E | “Tính phần trăm hoàn thành dựa trên các bài đạt điều kiện.” |
| F | “Làm lại toàn bộ nền tảng học trực tuyến.” |

**Gợi ý:** B, C, E có thể là features với kết quả nghiệp vụ; A, D chủ yếu là task/công việc kỹ thuật; F là nhu cầu quá rộng cần phân rã. Công việc kỹ thuật vẫn quan trọng và có thể cần backlog item riêng, nhưng không nhất thiết là feature có giá trị độc lập.

### Bài tập C — Lập Features List cho thanh toán

Yêu cầu lớn:

> “Khách hàng có thể áp mã giảm giá khi thanh toán và hệ thống luôn tính đúng tổng tiền.”

Hãy:

1. Xác định ít nhất **bốn khái niệm miền** như Customer, Cart, Promotion, Order.
2. Tạo một **major feature set**, hai **feature sets** và ít nhất **năm features**.
3. Chia theo **loại mã, điều kiện áp dụng và rủi ro tính tiền**.
4. Xác định quy tắc nào **bắt buộc ngay từ release đầu**.
5. Chọn 2–3 features đầu có thể kết hợp tạo trải nghiệm thanh toán an toàn.

**Lưu ý:** Không được “để sau” việc tránh tính tổng âm hoặc áp ưu đãi sai nếu release đầu đã có thể gây lỗi đó. Một feature quá rộng có thể cần tách, nhưng mọi phần được phát hành phải tính tiền đúng.

### Bài tập D — Kế hoạch khi có phụ thuộc class owner

Ba features cùng cần chỉnh lớp Enrollment, nhưng chỉ một người đang hiểu lớp này; người ấy còn trực sự cố.

1. Điều gì xảy ra nếu nhóm bắt đầu đồng thời cả ba features?
2. Có thể sắp xếp thứ tự dựa trên giá trị và rủi ro ra sao?
3. Có nên dùng review/pair programming để chia sẻ hiểu biết?
4. Cơ chế ownership có cần thay đổi không?
5. Bạn đo điều gì để biết điểm nghẽn đã giảm?

**Gợi ý:** WIP, thời gian chờ, work item age và cycle time có thể hữu ích. Không dùng tổng số người đang coding như chỉ số duy nhất cho khả năng giao feature.

### Bài tập E — Đọc tiến độ đúng

Một feature đã xong model walkthrough, design, design inspection và code, nhưng chưa code inspection, chưa kiểm thử tích hợp và chưa promote to build.

1. Có thể báo đã Done không?
2. Có thể phát hành cho người dùng không?
3. Báo cáo tiến độ kỹ thuật nên diễn đạt thế nào?
4. Nếu cần demo cho bên nghiệp vụ, có thể trình bày điều gì mà không gây hiểu nhầm?

**Gợi ý:** Không được đánh đồng “đã làm phần lớn các bước kỹ thuật” với Done. Có thể minh bạch phần đã có và rủi ro còn lại; chưa tuyên bố tạo Increment sử dụng được khi điều kiện bắt buộc chưa đạt.

### Bài tập F — So sánh FDD, Scrum, Kanban và XP

Một nhóm có 14 Developers và miền nghiệp vụ phức tạp, nhưng hiện sử dụng Scrum với Sprint hai tuần. Các PBIs thường bị chặn do không hiểu quy tắc và nhiều thay đổi cùng lớp dữ liệu.

Đề xuất **hai thực hành FDD** có thể bổ trợ Scrum mà không thay thế Sprint Goal, **một thực hành Kanban** để nhìn điểm nghẽn và **một thực hành XP** để giảm rủi ro kỹ thuật.

**Gợi ý:** Mô hình miền được cập nhật theo ví dụ, nhóm feature theo những lớp liên quan, WIP/work item age và CI/TDD có thể phù hợp. Cần xác định ai phối hợp và bằng chứng cho thấy cách làm được cải thiện.

## 25. Checklist áp dụng FDD có trách nhiệm

- [ ] Đã xác định người dùng/người nhận giá trị và **vấn đề sản phẩm**, không chỉ module kỹ thuật.
- [ ] Domain experts và Developers có **mô hình miền chung** đủ dùng, không biến mô hình thành vật bất biến.
- [ ] Các thuật ngữ, đối tượng và quy tắc có ví dụ cụ thể để kiểm tra hiểu biết.
- [ ] Danh sách được tổ chức theo **major feature set → feature set → feature** khi cách phân nhóm ấy hữu ích.
- [ ] Mỗi feature diễn đạt một **hành động/kết quả nghiệp vụ rõ**, không chỉ là tên file, API hay bảng.
- [ ] Feature đủ nhỏ để có thể thiết kế, xây, kiểm thử và tích hợp trong thời gian ngắn theo năng lực thực tế.
- [ ] Không dùng quy tắc “hai tuần” làm cớ bỏ kiểm thử hoặc gắn Done giả.
- [ ] Kế hoạch theo feature phản ánh **giá trị, rủi ro, phụ thuộc, năng lực và giới hạn chất lượng**.
- [ ] Thứ tự được cập nhật khi phản hồi người dùng hoặc kỹ thuật làm thay đổi giả định.
- [ ] Chief programmer, class owners, domain experts và Developers hiểu trách nhiệm, không biến ownership thành silo.
- [ ] Feature team có những người cần thiết để thiết kế và xây một kết quả end-to-end.
- [ ] Design by Feature có walkthrough, kiểm tra thiết kế và xem xét trường hợp biên.
- [ ] Build by Feature có code review/inspection, kiểm thử, tích hợp và xác nhận điều kiện hoàn tất.
- [ ] Phân quyền, dữ liệu, tính đúng đắn và quy định bắt buộc được bảo vệ từ phần mềm đầu tiên được giao.
- [ ] Nhóm phân biệt **milestone kỹ thuật, feature Done, Increment, release và outcome**.
- [ ] Nếu dùng chỉ số throughput/cycle time, định nghĩa work item và Done nhất quán.
- [ ] Nhóm không kéo quá nhiều feature đồng thời khi class owner hoặc kiểm thử đang tắc.
- [ ] Có cơ chế tiếp xúc bên nhận giá trị và đo phản hồi sau release.
- [ ] Những thực hành Scrum/Kanban/XP được kết hợp có chủ đích, không xung đột trách nhiệm và ownership.
- [ ] Nhóm có thể chỉ ra **một quyết định được thay đổi nhờ bằng chứng mới** và kết quả cải tiến tương ứng.

## 26. Tài liệu đọc tiếp và tổng kết

- Peter Coad, Eric Lefebvre và Jeff De Luca, *Java Modeling in Color with UML: Enterprise Components and Process* (1999): các ý tưởng mô hình miền và cách tiếp cận liên quan tới FDD.
- Stephen R. Palmer và John M. Felsing, *A Practical Guide to Feature-Driven Development* (2002): năm quy trình, feature lists, vai trò, thiết kế và xây theo feature.
- [Agile Manifesto](https://agilemanifesto.org/): các giá trị và nguyên tắc về giao phần mềm thường xuyên, cộng tác và thích ứng.
- [The Scrum Guide](https://scrumguides.org/): Product Backlog, Sprint Goal, Sprint Backlog, Increment và Definition of Done khi nhóm muốn dùng một số kỹ thuật FDD bên trong Scrum.
- [The Kanban Guide](https://kanbanguides.org/): workflow, WIP, throughput, cycle time, work item age và Service Level Expectation.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): test-first, refactoring, CI, pair programming và khả năng thay đổi mã an toàn.
- Jeff Patton, *User Story Mapping* (2014): dùng hành trình người dùng để nhận diện lát cắt phát hành có giá trị.

**Điểm cần nhớ:** FDD không đơn giản là viết một danh sách tính năng. Nó kết nối **mô hình miền** với **danh sách features nhỏ có giá trị**, rồi **lập kế hoạch, thiết kế và xây dựng theo từng feature**, kiểm tra và tích hợp liên tục. Cách làm này có ích khi tổ chức cần hiểu miền phức tạp và điều phối nhiều khả năng nghiệp vụ, nhưng phải tránh mô hình hóa quá mức, feature list đóng băng và báo cáo milestone thay cho giá trị thực tế. Chỉ khi các features dẫn đến **phần mềm sử dụng được, đúng chất lượng, có phản hồi từ người dùng và kế hoạch được điều chỉnh bằng bằng chứng**, FDD mới phát huy tinh thần Agile thích ứng.
