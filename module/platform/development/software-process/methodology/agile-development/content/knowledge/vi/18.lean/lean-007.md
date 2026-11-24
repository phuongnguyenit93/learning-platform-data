# Xây dựng chất lượng ngay trong quá trình phát triển

> **Trọng tâm:** Trong Lean, chất lượng không phải thứ được “gắn thêm” bằng một đợt kiểm thử cuối dự án. **Xây dựng chất lượng ngay trong quá trình phát triển (built-in quality)** nghĩa là làm rõ thế nào là đúng, ngăn lỗi ngay tại nguồn khi có thể, phát hiện sai lệch sớm, sửa nguyên nhân và duy trì khả năng tạo ra phần mềm đáng tin ở mỗi bước. Kiểm thử, review và vận hành vẫn rất quan trọng, nhưng không nên biến chúng thành nơi duy nhất phải chịu trách nhiệm cho chất lượng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **phát hiện sớm, phòng ngừa lỗi và cải tiến quy trình** là trọng tâm của chất lượng trong tư duy Lean.
2. Phân biệt **xây dựng chất lượng tại nguồn** với **kiểm tra chất lượng ở cổng cuối**, và hiểu vì sao cần cả xác minh sớm lẫn kiểm chứng sau phát hành.
3. Liên hệ các khái niệm **Jidoka, Andon, Poka-yoke, Kaizen, giảm lô công việc và giảm WIP** với hoạt động phát triển phần mềm.
4. Chuyển nhu cầu người dùng thành **user story, acceptance criteria, ví dụ kiểm thử và Definition of Done** có thể cùng kiểm chứng.
5. Thực hành tư duy **TDD/ATDD khi phù hợp, review, tích hợp liên tục, kiểm thử tự động và kiểm soát an toàn** để ngăn lỗi lan tới giai đoạn sau.
6. Xử lý sai lệch phát hiện trong workflow hoặc trên production mà không che giấu tình trạng, không hạ chuẩn chất lượng chỉ để giữ deadline.
7. Thiết kế bộ chỉ số cân bằng giữa **chất lượng, dòng công việc, khả năng phục hồi và giá trị người dùng**.
8. Phân tích tình huống lỗi lưu tiến độ học tập và đề xuất một vòng cải tiến có giả thuyết, bằng chứng, hành động và kết quả cần quan sát.

## 2. Vấn đề: tại sao “kiểm thử thật kỹ vào cuối dự án” chưa đủ?

Giả sử một nhóm phát triển nền tảng học trực tuyến. Trong ba tuần, Developers xây chức năng đăng ký, mở bài và lưu tiến độ. Các phần được viết riêng rồi chờ đến cuối giai đoạn mới tích hợp.

Khi kiểm thử toàn hệ thống, nhóm mới phát hiện:

- Giao diện báo **“Đã lưu”** trước khi dịch vụ lưu tiến độ xác nhận thành công.
- API từ chối một số dữ liệu trên thiết bị di động, nhưng UI không hiển thị lỗi.
- Khi người học bấm lại liên tục sau mất mạng, hệ thống đôi khi ghi trạng thái cũ đè lên trạng thái mới.
- Các tiêu chí chấp nhận của Product Owner chưa nói rõ cách xử lý khi mất kết nối.

Lúc này lỗi không còn nằm trong một hàm riêng. Nó có thể trải qua nhiều tầng giao diện, API, dữ liệu, quy tắc nghiệp vụ và cách kiểm thử. Nhóm phải tìm lại bối cảnh, tái hiện lỗi, chỉnh nhiều nơi, chờ môi trường rồi chạy lại kiểm thử. Công việc làm lại khiến những tính năng khác dồn về cuối.

Tư duy Lean đặt câu hỏi khác:

> “Điều kiện nào cho phép sai lệch này tồn tại qua nhiều bước, và chúng ta có thể phát hiện hoặc ngăn nó **sớm hơn, gần nguồn phát sinh hơn** như thế nào?”

Ví dụ:

- Làm rõ trường hợp mất mạng **trước khi code** giúp cả nhóm hiểu đúng hành vi.
- Viết kiểm thử cho trạng thái chưa được xác nhận **khi thiết kế API** giúp phát hiện lỗi logic sớm.
- Chạy CI sau mỗi thay đổi nhỏ giúp nhận ra hồi quy trong thời gian ngắn.
- Tích hợp luồng đầu–cuối trong từng lát cắt nhỏ giúp tránh dồn rủi ro đến cuối giai đoạn.
- Quan sát lỗi sau phát hành giúp phát hiện trường hợp chưa lường trước và cải thiện cách phòng ngừa.

Đây là **thay đổi cách tạo chất lượng**, không phải chỉ tăng số lượng test case hoặc giao thêm trách nhiệm cho QA.

## 3. “Chất lượng được xây vào” nghĩa là gì?

### 3.1. Chất lượng là thuộc tính của sản phẩm và cách tạo sản phẩm

Đối với phần mềm, chất lượng có thể bao gồm:

| Góc nhìn | Câu hỏi | Ví dụ |
|---|---|---|
| **Đúng nhu cầu** | Có giải quyết vấn đề người dùng thật không? | Người học tiếp tục bài đã học thay vì phải học lại |
| **Đúng chức năng** | Hành vi có đáp ứng quy tắc và các trường hợp biên không? | Chỉ báo đã lưu sau khi có xác nhận hợp lệ |
| **An toàn, bảo mật** | Có ngăn truy cập sai, lộ dữ liệu và thao tác nguy hiểm không? | Không cho tài khoản khác đọc tiến độ học của người dùng |
| **Độ tin cậy** | Hệ thống có ứng xử phù hợp khi dịch vụ hoặc mạng lỗi không? | Mất kết nối không tạo thông báo thành công giả |
| **Hiệu năng và khả năng tiếp cận** | Có dùng được trên thiết bị và trong điều kiện mục tiêu không? | Bài học mở được trên điện thoại/mạng yếu ở mức đã thống nhất |
| **Khả năng vận hành** | Có phát hiện, chẩn đoán và xử lý sự cố hợp lý không? | Theo dõi tỷ lệ lưu thất bại mà không log dữ liệu nhạy cảm |
| **Khả năng bảo trì** | Có thể thay đổi an toàn khi có phản hồi mới không? | Kiểm thử hồi quy và thiết kế giúp sửa quy tắc đồng bộ ít rủi ro |

Chất lượng không chỉ là “không còn bug”. Sản phẩm có thể **không lỗi theo đặc tả** nhưng vẫn không tạo giá trị nếu đặc tả giải quyết sai vấn đề.

### 3.2. Quality assurance không chỉ là phòng QA

Một cách phân biệt hữu ích:

- **Quality assurance (đảm bảo chất lượng):** xây năng lực và phương pháp để công việc đạt chất lượng một cách nhất quán.
- **Quality control (kiểm soát chất lượng):** kiểm tra kết quả để phát hiện sự không phù hợp với yêu cầu hoặc chuẩn.
- **Built-in quality:** đưa việc phòng ngừa, phát hiện và phản hồi vào **toàn bộ dòng tạo sản phẩm** thay vì chỉ kiểm tra đầu ra ở cuối.

Không có nghĩa QA, Tester hoặc chuyên gia bảo mật không còn cần thiết. Họ đóng góp rất quan trọng qua thiết kế kiểm thử, phát hiện rủi ro, tạo chiến lược xác minh và chia sẻ kiến thức với nhóm.

**Cốt lõi:** mọi người liên quan đến Increment có trách nhiệm với chất lượng; không nên chuyển trách nhiệm cho một “cổng kiểm thử cuối”.

### 3.3. “Tại nguồn” là nơi nào?

Nguồn của một sai lệch có thể nằm ở:

- **Yêu cầu:** hiểu sai việc người dùng muốn làm.
- **Thiết kế:** giao thức API không xác định rõ trạng thái thất bại.
- **Code:** nhánh xử lý lỗi hoặc đồng thời bị bỏ sót.
- **Dữ liệu:** ràng buộc hoặc cách ghi dữ liệu không nhất quán.
- **Quy trình:** môi trường tích hợp chỉ được chuẩn bị cuối Sprint.
- **Vận hành:** không có tín hiệu để biết lưu thất bại khi phát hành.

Xây dựng chất lượng tại nguồn đòi hỏi tìm **điểm sớm nhất hợp lý để phòng ngừa hoặc phát hiện**. Không phải mọi lỗi đều có thể thấy từ ngày đầu; vì vậy cần nhiều lớp phòng vệ và tiếp tục học sau phát hành.

## 4. Các ý tưởng Lean nền tảng liên quan đến chất lượng

### 4.1. Jidoka — dừng và xử lý khi xuất hiện điều bất thường

Trong Lean/Toyota Production System, **Jidoka** thường được diễn giải là tự động hóa có khả năng nhận biết bất thường và ngăn lỗi tiếp tục lan qua các công đoạn. Khi chuyển sang phần mềm, đây là **phép tương tự để tổ chức phản hồi và xử lý sai lệch**, không phải yêu cầu phải dừng mọi máy chủ hay mọi lập trình viên mỗi khi có test lỗi.

Ví dụ phần mềm:

- Pipeline CI dừng việc hợp nhất hoặc phát hành khi kiểm thử quan trọng thất bại.
- Một kiểm tra hợp đồng API phát hiện sự không tương thích trước khi tích hợp thay đổi.
- Hệ thống giám sát cảnh báo tăng đột biến lỗi và kích hoạt kênh ứng cứu.
- Developers tạm ngừng kéo việc mới để xử lý lỗi chặn khả năng giao Increment.

Điều đáng học là: **đừng để sản phẩm lỗi tiếp tục đi qua quy trình trong khi mọi người vẫn báo trạng thái “ổn”**.

### 4.2. Andon — làm sai lệch nhìn thấy được

Trong bối cảnh Lean, **Andon** gắn với việc hiển thị và báo hiệu trạng thái bất thường để người phù hợp có thể phản ứng. Trong phần mềm có thể là:

- CI hiển thị build đỏ và nguyên nhân thất bại.
- Bảng công việc ghi PBI bị chặn và thời gian chờ.
- Dashboard cảnh báo lỗi lưu tiến độ tăng sau triển khai.
- Một thông báo cụ thể trong kênh sự cố thay vì tin nhắn riêng tới một cá nhân.

Andon hiệu quả không phải vì có nhiều cảnh báo, mà vì **tín hiệu rõ, đáng tin, có người và cách xử lý**. Cảnh báo ồn ào không có ai phụ trách cũng có thể trở thành lãng phí.

### 4.3. Poka-yoke — thiết kế để khó mắc lỗi

**Poka-yoke** là tư duy thiết kế cơ chế ngăn sai sót hoặc khiến sai sót dễ bị phát hiện. Ví dụ:

| Sai sót dễ xảy ra | Thiết kế phòng ngừa minh họa |
|---|---|
| Nhập dữ liệu tiến độ không hợp lệ | Kiểu dữ liệu, ràng buộc đầu vào và kiểm thử ở ranh giới API |
| Người dùng bấm lưu nhiều lần gây ghi trùng | Thiết kế thao tác lặp an toàn khi nghiệp vụ cho phép |
| Cấu hình production nhầm môi trường thử | Kiểm tra cấu hình có kiểu/nguồn rõ, nguyên tắc least privilege, kiểm tra trước phát hành |
| Vô tình đưa khóa bí mật vào repository | Secret scanning, cơ chế quản lý secret và kiểm soát quyền |
| Bỏ quên kiểm thử trường hợp lỗi | Mẫu acceptance criteria có nhắc tình huống thất bại quan trọng |

Các cơ chế này **giảm xác suất lỗi**, không cho phép tuyên bố hệ thống an toàn tuyệt đối. Chúng phải được thiết kế theo mối đe dọa và hành vi thực tế.

### 4.4. Kaizen — cải tiến liên tục từ vấn đề thật

**Kaizen** nhấn mạnh cải tiến theo vòng lặp thực tế. Khi một lỗi xảy ra:

1. Làm rõ **tác động** và bảo vệ người dùng.
2. Khôi phục hoặc sửa hành vi sai phù hợp.
3. Tìm hiểu **nguyên nhân hệ thống** và điều kiện khiến lỗi lọt qua.
4. Thêm cơ chế phòng ngừa/phát hiện hữu ích.
5. Đo xem thay đổi có giảm lỗi tương tự mà không gây tác dụng phụ không.

Không cần tổ chức một cuộc họp kéo dài cho mọi lỗi nhỏ. Với lỗi nghiêm trọng hoặc lặp lại, **hậu kiểm không đổ lỗi** có thể giúp tạo cải tiến đáng tin hơn việc chỉ hỏi “Ai viết đoạn code này?”.

### 4.5. Giảm lô công việc và giảm WIP

Một khối tính năng lớn được xây nhiều tuần rồi mới tích hợp khiến sai lệch tích tụ. Những **lát cắt dọc nhỏ** từ giao diện qua backend, dữ liệu và kiểm thử có thể nhận phản hồi sớm hơn.

Kết hợp **giới hạn Work in Progress (WIP)** giúp nhóm ưu tiên hoàn tất phần đang làm, thay vì mở thêm nhiều tính năng khi review và kiểm thử đang nghẽn. Giá trị đến từ Increment hoàn chỉnh, không phải số hạng mục “đang tiến triển”.

## 5. Nhìn chất lượng qua dòng giá trị, không chỉ từng chức danh

Một workflow minh họa:

~~~mermaid
flowchart TD
    A["Vấn đề người dùng / Product Goal"] --> B["Làm rõ ví dụ và rủi ro"]
    B --> C["PBI nhỏ, acceptance criteria rõ"]
    C --> D["Thiết kế + kiểm thử sớm + code"]
    D --> E["Review và CI"]
    E --> F{"Đạt DoD và kiểm chứng cần thiết?"}
    F -->|"Chưa"| G["Làm rõ, sửa nguyên nhân, chạy lại kiểm tra"]
    G --> D
    F -->|"Có"| H["Increment tích hợp"]
    H --> I["Phát hành có kiểm soát + quan sát"]
    I --> J["Phản hồi sản phẩm, lỗi, outcome"]
    J --> A
~~~

Điểm đáng chú ý là **vòng sửa ngắn**. Khi lỗi được phát hiện ngay sau thay đổi nhỏ, nhóm thường còn nhớ bối cảnh và có thể sửa nhanh. Khi lỗi chỉ lộ ra sau nhiều tuần, chi phí truy tìm và tác động có thể lớn hơn.

### 5.1. Chất lượng phải đi xuyên các ranh giới

| Bước | Rủi ro thường gặp | Cơ chế xây chất lượng ngay ở bước đó |
|---|---|---|
| Khám phá sản phẩm | Xây đúng đặc tả nhưng sai nhu cầu | Phỏng vấn, quan sát, giả thuyết có thể kiểm chứng |
| Làm rõ PBI | Những người tham gia hiểu khác nhau | Ví dụ nghiệp vụ, acceptance criteria, Three Amigos |
| Thiết kế | Bỏ sót trường hợp lỗi, bảo mật hoặc vận hành | Threat modeling theo rủi ro, review thiết kế trọng yếu, contract tests |
| Viết code | Sai điều kiện, hồi quy, xử lý đồng thời không đúng | Kiểm thử ở mức phù hợp, TDD, pair programming, review |
| Tích hợp | Phần chạy riêng nhưng không hoạt động chung | CI, kiểm thử tích hợp và khả năng quan sát khi thất bại |
| Chuẩn bị phát hành | Không rõ hành vi khi lỗi, không có phương án phục hồi | DoD, kiểm tra triển khai, rollout/rollback theo rủi ro |
| Sử dụng thật | Trường hợp thực tế khác giả định thử nghiệm | Telemetry, phản hồi người dùng, ứng cứu và hậu kiểm |

Không nhất thiết tạo bảy phòng ban hay bảy cổng ký duyệt. Cần **thông tin và kiểm chứng đúng lúc**, với trách nhiệm chất lượng được chia sẻ xuyên suốt.

### 5.2. Phân biệt ngăn lỗi và phát hiện lỗi

**Ngăn lỗi**: ví dụ thiết kế API chỉ trả trạng thái “đã lưu” sau xác nhận hợp lệ, tránh trạng thái thành công giả.

**Phát hiện lỗi**: ví dụ kiểm thử tự động xác nhận khi backend báo lỗi, UI phải hiển thị thông báo tương ứng.

Hai cơ chế bổ sung nhau. Một API được thiết kế tốt vẫn có thể bị code sai; một bộ kiểm thử tốt không thể mô phỏng mọi trường hợp người dùng thật.

## 6. Làm rõ chất lượng trước khi bắt đầu code

### 6.1. Bắt đầu từ kết quả người dùng

Ví dụ Product Goal:

> “Người học có thể tiếp tục bài học mà không mất tiến độ khi chuyển thiết bị hoặc gặp gián đoạn mạng trong các điều kiện sản phẩm hỗ trợ.”

Nếu nhóm chỉ viết “Làm API lưu tiến độ”, có thể xây được API trả HTTP 200 nhưng không giải quyết hành vi quan trọng của người học.

Một user story hữu ích:

> **Là** người học đang học dở, **tôi muốn** biết tiến độ đã được lưu thành công hay chưa **để** có thể tiếp tục học mà không hiểu nhầm trạng thái và mất công sức.

Cách viết user story là thực hành có thể dùng trong Agile, **không phải định dạng bắt buộc của mọi PBI trong Scrum**.

### 6.2. Three Amigos: cùng làm rõ điều đúng

Trong một buổi trao đổi ngắn có thể có ba góc nhìn:

- **Nghiệp vụ/sản phẩm:** trường hợp nào có giá trị, kết quả người học cần là gì?
- **Phát triển/thiết kế:** làm sao lưu trạng thái, giao thức và lỗi kỹ thuật nào có thể xảy ra?
- **Kiểm thử/chất lượng:** cần những ví dụ nào để phân biệt đúng và sai?

**Three Amigos** là tên một thực hành cộng tác, không phải ba vai trò hoặc sự kiện bắt buộc của Scrum. Người tham gia có thể là các Developers có chuyên môn khác nhau cùng Product Owner hoặc chuyên gia phù hợp.

### 6.3. Acceptance criteria theo ví dụ Gherkin

~~~gherkin
Tính năng: Lưu tiến độ học đáng tin cậy

Kịch bản: Dịch vụ xác nhận lưu thành công
  Cho trước người học đã đăng nhập và đang học bài được phép
  Khi hệ thống xác nhận đã lưu tiến độ mới
  Thì giao diện cho người học biết tiến độ đã được lưu
  Và tiến độ có thể được đọc lại theo quy tắc sản phẩm

Kịch bản: Lưu thất bại do mất kết nối
  Cho trước người học có thay đổi chưa được xác nhận lưu
  Khi yêu cầu lưu không nhận được xác nhận thành công
  Thì giao diện không báo sai rằng đã lưu hoàn tất
  Và cung cấp trạng thái cùng hướng xử lý phù hợp

Kịch bản: Người học yêu cầu lưu lặp lại
  Cho trước một thao tác lưu được gửi lặp do lỗi mạng
  Khi dịch vụ xử lý những yêu cầu tương đương
  Thì tiến độ không bị giảm hoặc ghi trùng trái với quy tắc đồng bộ
  Và trạng thái phản hồi nhất quán với kết quả đã xử lý

Kịch bản: Người học khác yêu cầu đọc tiến độ
  Cho trước một người dùng không được cấp quyền với dữ liệu tiến độ
  Khi người dùng đó yêu cầu đọc tiến độ của tài khoản khác
  Thì hệ thống không tiết lộ dữ liệu học tập không được phép truy cập
  Và xử lý yêu cầu theo chính sách an toàn áp dụng
~~~

Đây là **kịch bản minh họa**, chưa xác lập chính sách retry, đồng bộ xung đột hoặc dữ liệu nhận dạng của một sản phẩm thật. Với yêu cầu bảo mật, cần người có chuyên môn xác nhận quy tắc và kiểm thử theo bối cảnh.

### 6.4. Thêm trường hợp biên trước khi chúng thành lỗi

Có thể dùng bảng tình huống:

| Điều kiện | Hành vi mong muốn | Điều cần xác minh |
|---|---|---|
| Mạng ổn định, dịch vụ lưu thành công | Thông báo đã lưu sau xác nhận | Kết quả đọc lại trùng dữ liệu đã lưu |
| Mất mạng trước xác nhận | Không báo thành công giả | Người học nhận trạng thái và hướng xử lý đúng |
| Yêu cầu được gửi lặp | Không gây thao tác có hại hoặc dữ liệu lùi trạng thái | Quy tắc lặp và tính nhất quán |
| Ghi từ hai thiết bị | Xử lý theo chính sách xung đột đã được xác định | Không âm thầm ghi đè ngoài ý muốn |
| Tài khoản hết quyền | Từ chối thao tác không hợp lệ | Không lộ dữ liệu hoặc quyền truy cập |
| Lưu thành công nhưng UI mất phản hồi | Không tạo lời khẳng định không có căn cứ | Cách làm mới trạng thái và truy vấn kết quả |

Tư duy Lean là **đưa lỗi và bất định ra ánh sáng sớm**. Không phải phải có hàng trăm acceptance criteria trước khi bắt đầu; chọn trường hợp mang rủi ro và giá trị lớn nhất, rồi làm rõ dần.

## 7. Definition of Done: chất lượng không bị thương lượng âm thầm

Trong Scrum, **Definition of Done (DoD)** là commitment của **Increment**, mô tả chính thức về trạng thái Increment khi đáp ứng những tiêu chuẩn chất lượng cần thiết. Khi một Product Backlog Item đáp ứng DoD, một Increment được tạo ra.

Nếu PBI chưa đạt DoD, nó **không phải một phần Increment hoàn thành** và không nên được phát hành hay trình bày ở Sprint Review như đã Done. Công việc chưa Done cần trở lại Product Backlog để xem xét tiếp.

### 7.1. Phân biệt acceptance criteria và DoD

| Khía cạnh | Acceptance criteria | Definition of Done |
|---|---|---|
| Đối tượng | Một PBI cụ thể | Chuẩn chất lượng chung của Increment |
| Ví dụ | “Không báo đã lưu khi chưa xác nhận” | “Mã được tích hợp và các kiểm thử liên quan đạt” |
| Mục đích | Xác nhận hành vi nghiệp vụ mong muốn | Tạo cách hiểu chung về hoàn thành và chất lượng |
| Trong Scrum | Cách mô tả hữu ích, không phải artifact chính thức | Commitment chính thức của Increment |

Acceptance criteria đúng nhưng kiểm thử tích hợp thất bại **chưa đạt Done**. Ngược lại, CI xanh nhưng hành vi nghiệp vụ không đúng acceptance criteria cũng **không phải Increment đúng nhu cầu**.

### 7.2. DoD minh họa cho nền tảng học

- PBI có hành vi được xác minh theo tiêu chí chấp nhận đã thống nhất.
- Các kiểm thử tự động thích hợp và kiểm thử tích hợp liên quan đạt.
- Thay đổi đã tích hợp, tương thích với các Increment trước.
- Những kiểm soát bảo mật, quyền truy cập, dữ liệu và chất lượng áp dụng được đáp ứng.
- Các tình huống lỗi quan trọng có hành vi an toàn và có khả năng quan sát.
- Tài liệu vận hành, cấu hình và phương án khôi phục được cập nhật nếu thay đổi ảnh hưởng tới chúng.

Đây là **ví dụ theo ngữ cảnh**, không phải DoD chung bắt buộc do Scrum quy định. Nếu tổ chức có chuẩn áp dụng, Scrum Team phải tuân thủ tối thiểu chuẩn đó; nếu nhiều Scrum Team cùng làm một sản phẩm, họ cần cùng một DoD.

### 7.3. Bảo vệ chất lượng khi sát deadline

Nếu Sprint sắp hết mà PBI quan trọng chưa đạt DoD:

1. Minh bạch điều đã hoàn tất và chưa hoàn tất.
2. Kiểm tra ảnh hưởng đối với Sprint Goal.
3. Developers thương lượng phạm vi với Product Owner khi cần.
4. Ưu tiên sửa lỗi, kiểm thử và tích hợp của lát cắt cốt lõi.
5. Đưa phần chưa Done trở lại Product Backlog để sắp thứ tự phù hợp.

Không lấy lý do “cần đạt velocity”, “đã hứa demo” hoặc “chỉ còn một test đỏ” để gắn nhãn Done sai. **Cắt phạm vi hoặc đàm phán kỳ vọng khác với cắt giảm chuẩn chất lượng bắt buộc.**

## 8. Kỹ thuật XP: đưa phản hồi chất lượng vào từng thay đổi nhỏ

**Extreme Programming (XP)** có các thực hành kỹ thuật rất phù hợp với Lean built-in quality: TDD, pair programming, continuous integration, refactoring và phát triển từng phần. Không có một kỹ thuật nào thay thế được việc hiểu nhu cầu người dùng, nhưng chúng giảm thời gian giữa **tạo lỗi → phát hiện lỗi → sửa lỗi**.

### 8.1. Test-Driven Development (TDD)

Chu trình **Red → Green → Refactor**:

1. **Red:** viết một kiểm thử nhỏ mô tả hành vi mong muốn, xác nhận nó thất bại vì hành vi chưa có.
2. **Green:** viết lượng code tối thiểu cần thiết để kiểm thử đạt.
3. **Refactor:** cải thiện cấu trúc code trong khi giữ hành vi và bộ test vẫn đạt.

Ví dụ về hành vi xác nhận lưu:

~~~text
RED:
  Test: khi repository báo lưu thất bại,
        dịch vụ không trả trạng thái SAVE_CONFIRMED.

GREEN:
  Viết logic chỉ trả SAVE_CONFIRMED khi có xác nhận hợp lệ.
  Khi thất bại, trả trạng thái thất bại hoặc chưa xác định
  theo hợp đồng API đã được thống nhất.

REFACTOR:
  Tách việc xử lý kết quả repository khỏi phần tạo phản hồi.
  Chạy lại bộ kiểm thử để bảo vệ hành vi.

TIẾP TỤC:
  Thêm kịch bản gửi lặp, mất phản hồi, quyền truy cập, race condition
  theo mức rủi ro và phạm vi cần hỗ trợ.
~~~

**TDD không bảo đảm code không lỗi.** Test có thể thiếu trường hợp, mô tả sai kỳ vọng hoặc chỉ kiểm tra chi tiết triển khai. Vì vậy, vẫn cần kiểm thử ở các mức khác và phản hồi thực tế.

### 8.2. Acceptance Test-Driven Development (ATDD)

**ATDD** đặt các ví dụ chấp nhận của nghiệp vụ/người dùng vào đầu quá trình. Product Owner, Developers, Tester và chuyên gia cùng làm rõ trường hợp quan trọng; kiểm thử chấp nhận có thể được tự động hóa ở mức phù hợp.

Phân biệt:

- TDD thường xoay quanh **thiết kế và hành vi nhỏ của code**.
- ATDD giúp làm rõ **kết quả nghiệp vụ và tiêu chí chấp nhận**.
- Hai cách có thể bổ trợ, không cần lựa chọn như hai phe đối lập.

### 8.3. Pair programming và review sớm

Pair programming cho phép hai người cùng suy nghĩ về giải pháp, phát hiện hiểu nhầm và chia sẻ kiến thức khi tạo code. Review thay đổi nhỏ cũng giúp phát hiện rủi ro trước khi chúng lan rộng.

Không nên biến code review thành nơi người review **chịu toàn bộ trách nhiệm chất lượng**. Người tạo thay đổi vẫn cần tự kiểm thử và hiểu ảnh hưởng; review là thêm góc nhìn, không phải thay thế các bước khác.

### 8.4. Refactoring giúp duy trì khả năng thay đổi

Code khó hiểu và phụ thuộc chéo khiến mỗi lần sửa yêu cầu có thể gây lỗi hồi quy. **Refactoring** cải thiện cấu trúc bên trong mà không cố ý thay đổi hành vi bên ngoài, thường được hỗ trợ bằng kiểm thử.

Ví dụ khi quy tắc lưu tiến độ xuất hiện ở nhiều chỗ, nhóm có thể tập trung xử lý trạng thái xác nhận trong một ranh giới rõ, giảm nguy cơ chỗ này báo “đã lưu” còn chỗ kia báo “đang chờ”.

Không coi “refactor cho đẹp” là mục tiêu tự thân; cân nhắc rủi ro, lợi ích bảo trì và khả năng tiến gần mục tiêu sản phẩm.

## 9. Continuous Integration: phản hồi ngay khi thay đổi được tích hợp

**Continuous Integration (CI)** là thực hành tích hợp thay đổi thường xuyên vào codebase chung và dùng các kiểm tra tự động phù hợp để phát hiện vấn đề sớm.

Trong một hệ thống tích hợp tốt, bộ kiểm tra không chỉ báo **đã chạy**, mà phải có ý nghĩa với hành vi và rủi ro sản phẩm.

### 9.1. Các lớp xác minh bổ trợ nhau

| Mức kiểm tra | Câu hỏi | Ví dụ |
|---|---|---|
| Static checks / lint / type checks | Có sai sót dễ phát hiện trước khi chạy không? | Sai kiểu, quy tắc code, secret vô tình bị đưa vào thay đổi |
| Unit tests | Một quy tắc nhỏ có đúng trong các trường hợp đã xác định không? | Chỉ xác nhận “đã lưu” sau kết quả thành công |
| Component/service tests | Một phần dịch vụ xử lý hợp đồng và lỗi phù hợp không? | API lưu tiến độ trả trạng thái có ý nghĩa |
| Contract/integration tests | Các thành phần hợp tác đúng qua ranh giới không? | UI–API–repository; hợp đồng dịch vụ bên ngoài |
| End-to-end tests chọn lọc | Hành trình quan trọng có chạy được từ góc nhìn người dùng không? | Đăng nhập → mở bài → lưu → mở lại |
| Security/performance checks theo rủi ro | Có lỗ hổng hoặc suy giảm đáng chú ý không? | Kiểm soát truy cập, độ trễ lưu, giới hạn tải |
| Kiểm tra sau triển khai | Phần mềm có hoạt động ổn trong môi trường thực không? | Theo dõi tỷ lệ lỗi và tín hiệu hoàn tất bài |

Không cần bắt mọi kiểm thử chạy ở mọi commit nếu chi phí quá lớn. Có thể tổ chức **phản hồi nhanh trước, kiểm tra chuyên sâu khi thích hợp**, nhưng các điều kiện cần thiết trước khi tích hợp hoặc phát hành phải rõ.

### 9.2. Pipeline CI minh họa

~~~yaml
# Pseudocode YAML minh họa, không phụ thuộc nền tảng CI cụ thể.
pipeline:
  on_change:
    - compile_and_static_checks
    - unit_tests
    - component_tests
    - secret_and_dependency_checks_if_configured
  before_integration:
    - critical_contract_and_integration_tests
    - required_review_and_quality_policy
  before_release:
    - product_risk_based_checks
    - operational_readiness
    - rollback_or_recovery_plan_when_needed
  after_release:
    - observe_error_rate_latency_and_product_outcomes
    - respond_and_roll_back_when_thresholds_require
~~~

Không có một tập kiểm tra hoặc ngưỡng chuẩn duy nhất cho mọi nhóm. Pipeline thực tế phải phản ánh rủi ro sản phẩm, quy định và năng lực kỹ thuật.

### 9.3. Khi CI đỏ phải làm gì?

1. **Làm rõ nguyên nhân:** lỗi code, môi trường, dữ liệu thử, hạ tầng hay kiểm thử không ổn định?
2. **Giới hạn ảnh hưởng:** không đưa thay đổi chưa đủ điều kiện vào nơi yêu cầu kết quả đáng tin.
3. **Phân công phối hợp:** người có thể giải quyết cùng làm rõ và khôi phục trạng thái kiểm tra đáng tin.
4. **Sửa nguyên nhân:** bổ sung kiểm thử hoặc cải thiện môi trường khi cần, thay vì chỉ chạy lại vô hạn.
5. **Theo dõi lặp lại:** nếu kiểm thử flaky thường xuyên, nó cần được ưu tiên cải thiện; đừng âm thầm vô hiệu hóa test quan trọng.

**Không phải mọi lỗi CI đều phải “dừng cả công ty”**. Mức ứng phó cần dựa trên ảnh hưởng và chính sách, nhưng lỗi phải được hiển thị minh bạch và xử lý có trách nhiệm.

## 10. Chuyển chất lượng từ “cổng cuối” sang nhiều vòng phản hồi

### 10.1. Shift-left: phát hiện sớm khi có thể

*Shift-left* thường nói đến việc đưa việc suy nghĩ và kiểm chứng chất lượng tới sớm hơn:

- Thảo luận tiêu chí chấp nhận khi làm rõ PBI.
- Kiểm tra rủi ro bảo mật khi quyết định thiết kế.
- Xây test, code và tích hợp theo lát cắt nhỏ.
- Chuẩn bị môi trường hoặc hợp đồng API trước khi phụ thuộc thành blocker.

**Shift-left không có nghĩa QA phải kiểm thử mọi thứ sớm bằng mọi giá**. Nó nghĩa là đưa loại phản hồi phù hợp tới điểm sớm nhất có ích.

### 10.2. Shift-right: học tiếp từ production

Một số vấn đề chỉ lộ ra trong điều kiện thật: hành vi thiết bị hiếm, tải cao, mạng bất thường, dữ liệu lịch sử phức tạp hoặc cách người dùng thực hiện tác vụ.

Các biện pháp có thể gồm:

- Theo dõi tín hiệu lỗi, độ trễ và tỷ lệ tác vụ hoàn thành.
- Phát hành theo đợt nhỏ, giới hạn nhóm dùng thử khi phù hợp.
- Dùng feature flag có chiến lược quản lý và gỡ bỏ rõ ràng.
- Có quy trình rollback, khôi phục hoặc vô hiệu hóa chức năng khi cần.
- Tiếp nhận hỗ trợ khách hàng và phản hồi sản phẩm có cấu trúc.

**Quan sát sau phát hành không thay thế kiểm thử trước phát hành.** Hai chiều kết hợp để học và bảo vệ người dùng.

### 10.3. Khi phát hiện lỗi sản xuất nghiêm trọng

Ví dụ hệ thống ghi mất tiến độ của người học:

- **Ưu tiên bảo vệ người dùng và dữ liệu** theo mức độ sự cố.
- Kích hoạt phản ứng theo chính sách, xác định người chịu trách nhiệm và truyền thông phù hợp.
- Cô lập tác động, tạm dừng phát hành liên quan hoặc khôi phục phiên bản khi cần và khả thi.
- Xác minh sửa lỗi/khôi phục bằng bằng chứng, không chỉ vì log báo “đã deploy”.
- Hậu kiểm nguyên nhân hệ thống: vì sao lỗi lọt qua, tín hiệu nào bị bỏ qua, bước phòng ngừa nào đáng đầu tư?

Tư duy Jidoka được vận dụng ở đây theo nghĩa **không tiếp tục lan rộng lỗi đã nhận biết**, chứ không tự động tắt tất cả dịch vụ nếu điều đó còn gây hại hơn.

## 11. Tích hợp Lean với Scrum và Kanban

### 11.1. Scrum: DoD bảo vệ Increment, Sprint Goal giữ định hướng

Scrum dựa trên **minh bạch, kiểm tra và thích ứng**. Với chất lượng:

- **Product Goal** giúp nhóm xác định giá trị thật cần tạo.
- **Sprint Goal** giữ sự tập trung khi có thông tin mới.
- **Increment + DoD** tạo chuẩn chung về phần sản phẩm thật sự hoàn thành.
- **Daily Scrum** giúp Developers kiểm tra tiến độ và điều chỉnh kế hoạch.
- **Sprint Review** giúp cùng stakeholder kiểm tra Increment và bối cảnh sản phẩm.
- **Sprint Retrospective** giúp cải tiến chất lượng và hiệu quả cách làm.

Trong Sprint, **chất lượng không được giảm**; Developers có thể thương lượng phạm vi với Product Owner khi hiểu biết tăng, miễn không gây nguy hại Sprint Goal. Không đồng nhất “Scrum có timebox” với “được phép gắn Done cho phần chưa đạt DoD”.

### 11.2. Kanban: quản lý dòng công việc và phơi bày vấn đề sớm

Nếu PBI bị chờ review và kiểm thử trong nhiều ngày, ngay cả người viết code giỏi cũng khó đưa Increment tới người dùng.

Kanban giúp:

- Định nghĩa rõ **workflow**, điểm bắt đầu và kết thúc.
- **Kiểm soát WIP** để giảm mở việc dở dang.
- Làm hiển thị **blocked items**, work item age và các hàng chờ.
- Dùng **throughput, cycle time, WIP và work item age** để xem hiệu quả của cải tiến.
- Thử chính sách pull phù hợp, ưu tiên hoàn tất việc đang mở thay vì tăng số ticket bắt đầu.

Không xem giảm WIP là bảo đảm throughput sẽ tăng; cần đo thực tế và xem chất lượng cùng outcome.

### 11.3. XP: thực hành kỹ thuật hỗ trợ chất lượng ở nguồn

XP bổ trợ bằng **TDD, CI, refactoring, pair programming và kiểm thử tự động**. Kết hợp thực tế có thể như sau:

| Vấn đề | Lean đặt câu hỏi | Scrum/Kanban/XP hỗ trợ |
|---|---|---|
| Lỗi chỉ xuất hiện cuối Sprint | Vì sao phản hồi tới quá muộn? | PBI nhỏ, kiểm thử sớm, CI, WIP hợp lý |
| Không ai biết “Done” có nghĩa gì | Chuẩn chất lượng ở đâu? | DoD, acceptance criteria, minh bạch trạng thái |
| Review và QA bị quá tải | Hệ thống đang tạo hàng chờ ở đâu? | Kanban WIP limit, chia sẻ kỹ năng, pairing |
| Người dùng vẫn gặp khó dù test xanh | Có đang xây sai điều người dùng cần? | Product Goal, Sprint Review, feedback, thử nghiệm |
| Lỗi hồi quy lặp lại | Có thể phòng ngừa từ nguồn nào? | TDD khi phù hợp, refactoring, contract tests, hậu kiểm |

Đây không phải công thức phải áp dụng mọi thực hành cho mọi dự án. Điều quan trọng là chọn cơ chế giúp **phát hiện sai lệch sớm và giảm chi phí làm lại** theo rủi ro thực.

## 12. Tình huống xuyên suốt: sửa lỗi lưu tiến độ bằng built-in quality

### 12.1. Bối cảnh và tín hiệu

Một nền tảng học trực tuyến có Product Goal:

> “Người học có thể hoàn thành bài đầu và tiếp tục học mà không mất tiến độ trong các điều kiện được hỗ trợ.”

Người dùng phản ánh rằng khi mạng yếu, ứng dụng đôi khi báo đã lưu nhưng sau khi mở lại bài không thấy tiến độ. Bộ phận hỗ trợ gặp nhiều trường hợp khó tái hiện.

Nhóm kiểm tra dữ liệu, log được phép truy cập và các bước tái hiện. Họ nhận thấy:

1. Frontend hiển thị thành công khi yêu cầu được gửi đi, **chưa chờ xác nhận lưu**.
2. API có thể trả lỗi tạm thời, nhưng cách phân biệt các trạng thái thất bại chưa rõ.
3. Kiểm thử hiện tại chỉ có đường đi thành công trên mạng ổn định.
4. PBI từng được đánh dấu Done vì code hoàn thành, mặc dù thử nghiệm trên mạng yếu chưa nằm trong tiêu chí.

Đây là vấn đề **hành vi, quá trình và minh bạch chất lượng**, không chỉ là một lỗi ở một hàm.

### 12.2. Làm rõ trạng thái đúng với Product Owner và Tester

Nhóm thảo luận:

- Khi nào mới có bằng chứng đã lưu thành công?
- Người học cần thấy trạng thái gì trong lúc đang chờ?
- Nếu mất kết nối, hành vi thử lại được phép như thế nào?
- Nếu có thao tác từ hai thiết bị, quy tắc xung đột là gì?
- Những dữ liệu hoặc trạng thái nào không được để lộ sang người dùng khác?

Sau đó chuyển thành acceptance criteria, kiểm thử và các mục chất lượng áp dụng trong DoD.

### 12.3. Cắt một lát dọc nhỏ

Thay vì xây đồng thời một hệ thống đồng bộ offline rất lớn, nhóm chọn lát cắt:

> “Với một bài học và một thiết bị trong phạm vi đã chọn, giao diện chỉ xác nhận đã lưu khi dịch vụ có kết quả hợp lệ; khi thất bại, người học thấy trạng thái phù hợp và có thể xử lý theo chính sách.”

Lát cắt này đi qua **UI → API → lưu dữ liệu → kiểm thử → khả năng quan sát**. Nó chưa giải quyết mọi kịch bản hai thiết bị hoặc offline dài ngày, nhưng có thể tích hợp và kiểm chứng một hành vi quan trọng.

### 12.4. Dùng nhiều lớp xây chất lượng

| Lớp | Hành động | Bằng chứng kiểm chứng |
|---|---|---|
| Làm rõ nghiệp vụ | Thống nhất trạng thái “đang lưu”, “đã xác nhận”, “thất bại” | Acceptance criteria đã được xem bằng ví dụ |
| Thiết kế | Tách trạng thái xác nhận khỏi sự kiện bấm nút | Hợp đồng phản hồi API phù hợp |
| Unit/component | Kiểm thử nhánh kết quả thành công và lỗi | Test tự động đỏ trước sửa, xanh sau sửa nếu dùng TDD |
| Integration | Kiểm tra UI–API–repository trên mạng không ổn định giả lập | Không có thông báo thành công giả ở kịch bản đã chọn |
| Review | Xem xử lý trạng thái, rủi ro đồng thời, quyền truy cập | Nhận xét và quyết định được xử lý |
| CI | Chạy kiểm thử thường xuyên khi tích hợp | Build và kiểm thử bắt buộc đạt |
| DoD | Xác minh chất lượng của lát cắt | Increment tích hợp đạt chuẩn |
| Production | Theo dõi lỗi lưu và phản hồi người dùng | Có dữ liệu để quyết định mở rộng hoặc sửa tiếp |

### 12.5. Chặn lỗi lan thay vì đẩy việc qua cổng

Giả sử một kiểm thử tích hợp phát hiện UI vẫn báo đã lưu trước khi backend xác nhận. Nhóm:

1. **Không chuyển PBI sang Done**.
2. Ghi rõ trường hợp thất bại trên bảng và trong kết quả CI.
3. Developers phối hợp xử lý, tránh mở thêm nhiều PBI nếu WIP đang cao.
4. Sửa nguyên nhân, chạy lại kiểm thử và review phần ảnh hưởng.
5. Chỉ tạo Increment hoàn thành khi lát cắt đạt DoD.

Đây là cách áp dụng tinh thần **Jidoka/Andon** trong quá trình làm phần mềm: tín hiệu lỗi được hiển thị và giải quyết gần nơi phát sinh, không đẩy trách nhiệm sửa sang bước sau.

### 12.6. Phát hành có kiểm soát và quan sát

Giả sử nhóm triển khai cho một nhóm người dùng thử phù hợp, có cách theo dõi lỗi lưu và khả năng khôi phục khi cần. Họ quan sát:

- Tỷ lệ thao tác lưu không được xác nhận.
- Tỷ lệ người dùng nhìn thấy trạng thái lỗi nhưng không thể tiếp tục học.
- Số báo cáo mất tiến độ có thể xác minh.
- Tỷ lệ người học tiếp tục bài hoặc hoàn thành bài đầu.
- Độ trễ lưu và các lỗi mới phát sinh sau thay đổi.

**Ví dụ số liệu giả định**, để luyện cách đọc:

| Chỉ báo | Trước thay đổi | Sau thay đổi | Điều cần xem thêm |
|---|---:|---:|---|
| Báo cáo mất tiến độ được xác minh trong giai đoạn đo | 18 | 5 | Lượng người dùng và thời gian quan sát có tương đương? |
| Tỷ lệ thao tác lưu gặp lỗi đo được | 4,0% | 1,5% | Định nghĩa sự kiện và phân khúc có giữ nguyên? |
| Tỷ lệ hoàn thành bài đầu trong 7 ngày | 27% | 29% | Có thay đổi đồng thời về nội dung, chiến dịch hoặc thiết bị? |

Các con số **không chứng minh quan hệ nhân quả** và không phải chuẩn tham chiếu. Giảm số lỗi báo cáo có thể đến từ việc ít người dùng hơn, hệ thống đo thay đổi hoặc việc người dùng không phát hiện lỗi. Cần kiểm tra mẫu số, độ phủ theo dõi và những yếu tố gây nhiễu.

### 12.7. Cải tiến sau khi xử lý lỗi

Trong Sprint Retrospective hoặc hậu kiểm phù hợp, nhóm đặt câu hỏi:

> “Tại sao trạng thái lưu chưa xác nhận vẫn lọt tới môi trường dùng thử, và cơ chế tối thiểu nào giúp tránh lỗi cùng loại lặp lại?”

Giả thuyết cải tiến:

- Đưa tình huống **thành công–thất bại–chưa biết kết quả** vào buổi làm rõ PBI liên quan thao tác dữ liệu.
- Thêm kiểm thử hợp đồng/CI để phát hiện phản hồi không nhất quán.
- Tích hợp sớm các lát cắt qua giao diện và API.
- Làm rõ Definition of Done với các thay đổi ảnh hưởng dữ liệu người dùng.

Không tự động yêu cầu tất cả PBI của toàn sản phẩm phải có hàng chục trường hợp lỗi. Chọn **cơ chế theo mức rủi ro**, rồi theo dõi chi phí và lợi ích thực tế.

## 13. Đo chất lượng mà không biến chỉ số thành mục tiêu tự thân

Một nhóm chỉ đo **số bug tìm thấy** có thể khuyến khích ghi nhiều bug nhỏ nhưng bỏ qua vấn đề lớn. Nếu chỉ đo **tỷ lệ test pass**, nhóm có thể xóa hoặc bỏ qua test khó. Nếu chỉ đo **throughput**, nhóm có thể chia ticket nhỏ hoặc báo Done sớm.

Cần xem một tập tín hiệu cân bằng:

| Nhóm tín hiệu | Ví dụ | Câu hỏi nên hỏi | Giới hạn |
|---|---|---|---|
| **Phòng ngừa** | Tỷ lệ PBI có ví dụ lỗi quan trọng được làm rõ sớm | Nhóm có ngăn hiểu sai trước khi code không? | Không phải càng nhiều case càng tốt |
| **Phản hồi kỹ thuật** | Thời gian từ commit tới kết quả CI, lỗi kiểm thử lặp | Kiểm tra có nhanh, đáng tin và hữu ích không? | CI xanh không bảo đảm đúng nhu cầu |
| **Chất lượng sau phát hành** | Lỗi nghiêm trọng, lỗi hồi quy, lỗi ảnh hưởng dữ liệu | Có lỗi lọt tới người dùng không? | Số lỗi phụ thuộc lượng dùng và khả năng phát hiện |
| **Khả năng phục hồi** | Thời gian phát hiện, khôi phục hoặc cô lập sự cố | Khi có lỗi, nhóm phản ứng có hiệu quả không? | Cần phân loại mức độ, không chỉ lấy một trung bình |
| **Dòng công việc** | WIP, cycle time, throughput, work item age | Chất lượng có bị dồn ở một khâu không? | Không tự đo giá trị người dùng |
| **Giá trị sản phẩm** | Người học hoàn thành bài, giữ được tiến độ, phản hồi | Sản phẩm có giải quyết vấn đề không? | Outcome chịu ảnh hưởng bởi nhiều biến |
| **Sức khỏe nhóm** | Tỷ lệ làm lại, thời gian chờ review, áp lực ngoài giờ | Cách tạo chất lượng có bền vững không? | Cần xem ngữ cảnh và phản hồi định tính |

### 13.1. Một số phép tính dễ dùng

**Tỷ lệ lỗi thao tác lưu** với cách đo nhất quán:

\[
\text{Tỷ lệ lỗi lưu} =
\frac{\text{Số thao tác lưu lỗi theo định nghĩa}}
{\text{Tổng thao tác lưu đủ điều kiện được quan sát}}
\times 100\%.
\]

**Thời gian sửa lỗi có ý nghĩa** nên đo từ một điểm bắt đầu tới kết thúc được thống nhất, chẳng hạn từ lúc xác nhận sự cố tới khi khôi phục hành vi; không tự động trộn thời gian nhận phản ánh với thời gian sửa code nếu mục đích đo khác nhau.

**Tỷ lệ làm lại do lỗi** có thể tính bằng số hạng mục phải mở lại vì sai hành vi trên tổng số hạng mục cùng loại trong một giai đoạn. Nhưng cần phân biệt **làm lại vì lỗi** với **đổi giải pháp có chủ đích sau phản hồi người dùng** — học hỏi hợp lý không nhất thiết là lãng phí.

### 13.2. Số liệu nên dùng để ra quyết định

Ví dụ:

> “Ba Sprint gần đây, số PBI chờ tích hợp quá lâu tăng và lỗi hồi quy phát hiện cuối Sprint nhiều hơn. Nhóm sẽ thử giảm WIP và đưa kiểm thử tích hợp của luồng chính vào sớm. Ta sẽ xem lại cycle time, work item age, lỗi và khả năng đạt DoD, không chỉ số ticket Done.”

Đây là **một giả thuyết cải tiến**. Nếu các chỉ báo không tiến triển, nhóm phải điều chỉnh phương pháp, không ép số liệu chứng minh lựa chọn ban đầu luôn đúng.

## 14. Chất lượng cũng là vấn đề tổ chức và cộng tác

### 14.1. Ai chịu trách nhiệm?

Trong Scrum, **Scrum Team** chịu trách nhiệm tạo Increment có giá trị và hữu ích. **Developers** có trách nhiệm bảo đảm chất lượng bằng cách tuân thủ DoD, lập kế hoạch, thích ứng công việc và chịu trách nhiệm nghề nghiệp với nhau. **Product Owner** tối đa hóa giá trị và làm rõ Product Backlog; **Scrum Master** hỗ trợ hiệu quả Scrum Team và cách áp dụng Scrum.

Chức danh QA, Tester, SRE, Security Engineer hoặc UX Designer không tự xác định người đó có hay không thuộc Developers; điều này phụ thuộc việc họ có là thành viên Scrum Team cùng tạo Increment hay là chuyên gia bên ngoài được mời hỗ trợ.

**Chất lượng được chia sẻ nhưng không có nghĩa mọi người làm mọi việc.** Cần biết rõ ai cung cấp chuyên môn và các quyền phê duyệt bắt buộc theo chính sách tổ chức.

### 14.2. Không biến quy trình chất lượng thành hàng chờ mới

Một quy trình yêu cầu mọi thay đổi nhỏ chờ ba người ký có thể tạo thời gian chờ lớn mà không tăng chất lượng tương ứng. Ngược lại, bỏ review cần thiết ở thay đổi quyền truy cập có thể tạo rủi ro nghiêm trọng.

Hãy phân loại theo **rủi ro và tác động**:

- Thay đổi nhỏ, dễ đảo ngược: kiểm tra và review vừa đủ.
- Thay đổi hành vi nghiệp vụ: acceptance criteria và kiểm thử hồi quy có liên quan.
- Thay đổi dữ liệu, xác thực, tài chính hoặc an toàn: mức kiểm chứng, tham vấn và phê duyệt phù hợp theo chính sách.
- Thay đổi kiến trúc nhiều nhóm: kiểm tra hợp đồng, kế hoạch chuyển đổi và vận hành, bằng chứng tương thích.

**Lean tìm cách giảm lãng phí**, không cho phép cắt bỏ kiểm soát thiết yếu chỉ vì chúng mất thời gian.

### 14.3. Giao tiếp trực tiếp và dấu vết vừa đủ

Khi xuất hiện bất đồng “đã lưu” có nghĩa gì, một cuộc trao đổi ngắn với ví dụ cụ thể có thể sửa hiểu nhầm nhanh. Sau đó ghi **quyết định, acceptance criteria, kiểm thử và rủi ro** ở nơi người khác tìm được.

Không nên đẩy toàn bộ kiến thức vào tin nhắn cá nhân, cũng không bắt mọi quyết định nhỏ phải có biên bản dài. Mục tiêu là **đúng thông tin, đúng lúc, đủ để làm và kiểm chứng**.

## 15. Những cách hiểu sai thường gặp

| Cách hiểu sai | Vì sao không phù hợp | Cách điều chỉnh |
|---|---|---|
| “Chất lượng là việc của QA.” | Sai lệch từ yêu cầu, thiết kế, code và vận hành đã phát sinh trước khi QA kiểm tra | Cùng làm rõ và xác minh trong toàn dòng phát triển |
| “Càng nhiều test case càng chất lượng.” | Có thể lặp, giòn, chậm và không kiểm tra rủi ro thật | Ưu tiên kịch bản quan trọng, khả năng bảo trì và nhiều lớp phản hồi |
| “CI xanh nghĩa là người dùng sẽ hài lòng.” | Tính năng có thể đúng code nhưng sai nhu cầu | Quan sát outcome và phản hồi sản phẩm |
| “Không cần kiểm thử sau phát hành vì đã shift-left.” | Production có điều kiện khác môi trường thử | Kết hợp kiểm tra trước với quan sát/khả năng phục hồi sau |
| “Jidoka nghĩa là dừng mọi công việc nếu một test lỗi.” | Vận dụng quá máy móc có thể gây hại | Hiển thị và xử lý sai lệch theo mức rủi ro, không lan lỗi |
| “Poka-yoke loại bỏ mọi khả năng mắc lỗi.” | Cơ chế phòng ngừa vẫn có giới hạn | Dùng nhiều lớp phòng vệ và tiếp tục kiểm chứng |
| “Muốn kịp deadline thì hạ Definition of Done.” | Làm mất ý nghĩa Done và đẩy rủi ro sang người dùng | Thương lượng phạm vi/ngày, bảo vệ tiêu chuẩn chất lượng |
| “Code review càng lâu càng chắc chắn.” | Có thể tạo điểm tắc, người review quá tải | Review theo rủi ro, thay đổi nhỏ, kiểm thử và tự động hóa phù hợp |
| “Giảm WIP luôn tăng throughput.” | Giới hạn quá thấp hoặc kỹ năng thiếu có thể làm chậm | Thử nghiệm, xem cycle time, throughput và chất lượng |
| “Bug trong production chứng minh người viết code yếu.” | Khuyến khích giấu vấn đề, bỏ qua điều kiện hệ thống | Hậu kiểm không đổ lỗi, tìm nguyên nhân và kiểm soát |
| “Refactoring không tạo tính năng nên là lãng phí.” | Nợ kỹ thuật có thể gây lỗi và cản việc thay đổi | Đánh giá rủi ro, lợi ích và khả năng bảo trì |
| “Tất cả lỗi phải sửa ngay bất kể mức tác động.” | Đẩy nhóm vào thay đổi ưu tiên tùy hứng | Phân loại nghiêm trọng, liên kết mục tiêu và nghĩa vụ |
| “Nhiều dashboard đồng nghĩa minh bạch.” | Dữ liệu có thể sai định nghĩa hoặc không có hành động | Dùng chỉ số có câu hỏi và quyết định rõ |
| “Đã qua cuối Sprint thì PBI chưa kiểm thử vẫn tính Done.” | Trái DoD và tính minh bạch Increment | Đánh dấu chưa Done, xem lại trong Product Backlog |

## 16. Checklist thực hành built-in quality

### Trước khi bắt đầu một PBI

1. **Giá trị:** hạng mục giúp Product Goal hoặc giảm rủi ro quan trọng nào?
2. **Người dùng:** tình huống sử dụng bình thường và lỗi quan trọng đã rõ chưa?
3. **Ví dụ:** Product Owner, Developers và Tester có thống nhất được hành vi kiểm chứng không?
4. **Rủi ro:** có liên quan dữ liệu, truy cập, an toàn, hiệu năng hay vận hành không?
5. **Phạm vi:** có thể chia thành lát dọc nhỏ, tích hợp và kiểm chứng sớm không?

### Khi phát triển

6. **Kiểm thử ở nguồn:** logic nào có thể được phòng ngừa hoặc phát hiện sớm qua test/thiết kế?
7. **Tích hợp:** các thay đổi có được tích hợp và kiểm tra thường xuyên không?
8. **Review:** có phản hồi phù hợp về hành vi, thiết kế và rủi ro không?
9. **Workflow:** WIP và blocker có hiển thị, nhóm có ưu tiên hoàn tất không?
10. **Sai lệch:** build đỏ, test lỗi hoặc hành vi bất thường được xử lý theo chính sách không?
11. **DoD:** mọi người đang dùng cùng định nghĩa hoàn thành chứ?

### Trước và sau phát hành

12. **Increment:** phần sẽ giao đã tích hợp và đạt tiêu chuẩn bắt buộc chưa?
13. **Giới hạn và kế hoạch:** nếu chưa đạt, có giảm phạm vi thay vì che lỗi không?
14. **Vận hành:** có theo dõi, cảnh báo, khôi phục hoặc rollback phù hợp với mức rủi ro không?
15. **Phản hồi:** outcome nào của người dùng cần đo, và bao lâu thì có đủ dữ liệu?
16. **Học hỏi:** nếu xảy ra lỗi, nhóm có sửa cả nguyên nhân hệ thống chứ không chỉ triệu chứng không?
17. **Cải tiến:** có xác định một thay đổi vừa đủ và điểm xem lại kết quả không?

Checklist là **công cụ đặt câu hỏi**, không phải biểu mẫu chữ ký bắt buộc cho mọi PBI. Quy trình kiểm soát phải tương xứng với mức rủi ro.

## 17. Bài tập vận dụng

### Bài tập 1 — Tìm điểm có thể xây chất lượng sớm hơn

Một đội xây tính năng thanh toán. Product Owner chỉ nói “Không được thanh toán hai lần”, Developers code API và UI độc lập, Tester chỉ nhận bản tích hợp cuối Sprint. Lỗi mạng khiến người mua bấm lại và tạo giao dịch trùng.

**Yêu cầu:** lập bảng ít nhất bốn điểm trong workflow có thể ngăn hoặc phát hiện lỗi sớm hơn: yêu cầu, thiết kế, code, tích hợp, phát hành. Nêu ai cần tham gia và bằng chứng kiểm chứng cho mỗi điểm.

**Gợi ý:** ví dụ nghiệp vụ về bấm lặp; chính sách idempotency nếu nghiệp vụ phù hợp; contract/integration test; trạng thái thanh toán chưa xác nhận; giám sát giao dịch trùng.

### Bài tập 2 — Phân biệt acceptance criteria và Definition of Done

PBI: “Người học có thể gửi lại email kích hoạt tài khoản”.

**Yêu cầu:**

1. Viết ba acceptance criteria cho gửi thành công, yêu cầu gửi liên tục và dịch vụ gửi lỗi.
2. Viết năm điều kiện DoD phù hợp (tích hợp, kiểm thử, bảo mật, quan sát, vận hành...).
3. Giải thích vì sao acceptance criteria đã đạt nhưng bộ kiểm thử hồi quy bắt buộc chưa chạy thì chưa nên báo Done.
4. Nêu một outcome cần quan sát sau phát hành.

**Gợi ý:** không được hiển thị trạng thái thành công sai, không lộ dữ liệu nhạy cảm và phải giữ tiêu chuẩn chất lượng chung của Increment.

### Bài tập 3 — Phân loại biện pháp Jidoka, Andon, Poka-yoke

Xem các biện pháp:

- A. CI báo đỏ khi kiểm thử hợp đồng API thất bại.
- B. API từ chối giá trị tiến độ nằm ngoài miền hợp lệ.
- C. Dashboard cảnh báo lỗi ghi dữ liệu tăng bất thường.
- D. Nhóm tạm dừng triển khai thay đổi có lỗi bảo mật nghiêm trọng cho đến khi được xử lý đúng.
- E. Một checklist PR nhắc kiểm tra trường hợp quyền truy cập.

**Yêu cầu:** giải thích biện pháp nào chủ yếu hỗ trợ **phòng lỗi**, **phát hiện/hiển thị lỗi** hoặc **ngăn lỗi lan**, và vì sao một biện pháp có thể góp vào nhiều ý tưởng cùng lúc.

**Gợi ý:** đừng coi các khái niệm Lean như nhãn loại trừ nhau. Điều quan trọng là cơ chế tạo phản hồi và hành động.

### Bài tập 4 — Chọn kiểm thử theo rủi ro

Tính năng “Lưu tiến độ bài học” có các nguy cơ: trả thông báo thành công giả, mất trạng thái khi mạng lỗi, người dùng khác đọc được tiến độ, tăng độ trễ khi có nhiều người học.

**Yêu cầu:** chọn ít nhất một kiểm tra phù hợp ở từng mức unit, integration, end-to-end và vận hành. Nêu điều gì mỗi mức **không thể tự chứng minh**.

**Gợi ý:** unit test kiểm tra logic phản hồi; integration test kiểm tra UI–API–lưu dữ liệu; E2E thử hành trình quan trọng; production cần quan sát lỗi và hiệu năng thực.

### Bài tập 5 — Sửa một quy trình dồn lỗi về cuối

Nhóm có 14 PBI đang mở, code review và kiểm thử bị dồn cuối Sprint. Mọi người thường bắt đầu PBI mới khi xong phần code của mình. Ba Sprint gần đây phát hiện nhiều lỗi hồi quy muộn.

**Yêu cầu:** đề xuất một thử nghiệm cải tiến trong hai Sprint gồm:

- Vấn đề và bằng chứng hiện có.
- Giả thuyết về nguyên nhân.
- Chính sách WIP và cách hỗ trợ công việc gần Done.
- Cách dùng CI/review/kiểm thử sớm mà không tăng thủ tục vô ích.
- Chỉ số về flow, chất lượng, và một tín hiệu guardrail.
- Điều kiện giữ, đổi hoặc dừng thử nghiệm.

**Gợi ý:** không hứa “giảm WIP 50% sẽ tăng tốc gấp đôi”; theo dõi throughput, cycle time, work item age, lỗi và mức quá tải.

### Bài tập 6 — Đọc số liệu để tránh kết luận vội

Sau cải tiến, tỷ lệ lỗi lưu đo được giảm từ **4,0% xuống 1,5%**, số báo cáo mất tiến độ giảm từ **18 xuống 5**, tỷ lệ người học hoàn thành bài đầu trong bảy ngày tăng từ **27% lên 29%**.

**Yêu cầu:**

1. Nêu ít nhất bốn điều phải kiểm tra trước khi kết luận cải tiến có tác dụng.
2. Tính mức giảm tuyệt đối của tỷ lệ lỗi lưu theo **điểm phần trăm**.
3. Phân biệt tác động tới chất lượng kỹ thuật và outcome sản phẩm.
4. Đề xuất một quyết định sản phẩm/kỹ thuật hợp lý khi dữ liệu còn bất định.

**Gợi ý:** mức giảm tuyệt đối của tỷ lệ lỗi là **2,5 điểm phần trăm**. Cần xem mẫu số, thời gian, nhóm người dùng, thay đổi hệ thống đo và tác động của thay đổi khác.

### Bài tập 7 — Hậu kiểm không đổ lỗi

Một bản phát hành khiến người dùng bị đăng xuất đột ngột. Sau sự cố, quản lý muốn kết luận “Do Developer quên kiểm thử”.

**Yêu cầu:** viết một bản hậu kiểm ngắn gồm:

~~~text
Sự cố và tác động đã xác nhận:
Mốc phát hiện và hành động bảo vệ người dùng:
Điều đã biết / chưa biết:
Nguyên nhân kỹ thuật đang nghi vấn:
Điều kiện quy trình khiến lỗi có thể lọt qua:
Kiểm soát phòng ngừa ở nguồn:
Kiểm tra/quan sát sau phát hành cần bổ sung:
Người phối hợp và trách nhiệm quyết định:
Tín hiệu sẽ dùng đánh giá cải tiến:
Thời điểm xem lại:
~~~

**Gợi ý:** tránh biến việc tìm nguyên nhân thành truy trách nhiệm cá nhân; vẫn cần minh bạch về quyết định, hành động và các nghĩa vụ thực tế.

### Bài tập 8 — Thiết kế chất lượng cho PBI của bạn

Chọn một PBI trong dự án của bạn và điền:

~~~text
Product Goal / giá trị người dùng:
PBI và hành vi mong muốn:
Ba trường hợp quan trọng, kể cả lỗi:
Rủi ro chất lượng cao nhất:
Cách phòng ngừa lỗi từ thiết kế:
Unit/component test:
Contract/integration test:
End-to-end/kiểm thử thủ công theo rủi ro:
Điều kiện DoD liên quan:
Trạng thái CI / điểm chặn khi sai lệch:
Cách triển khai và quan sát sau phát hành:
Outcome người dùng / chất lượng cần theo dõi:
Điều kiện thay đổi quyết định:
~~~

**Tự đánh giá:** thay vì chỉ có câu “QA sẽ test”, người đọc có thấy được **chất lượng được tạo ra từ lúc hiểu vấn đề đến lúc phần mềm được dùng** hay chưa?

## 18. Tổng kết

Lean nhắc chúng ta rằng **lãng phí lớn nhất không chỉ là làm chậm**, mà còn là tạo ra công việc, lỗi và quyết định phải sửa lại vì phản hồi đến quá muộn.

Hãy ghi nhớ:

1. **Chất lượng tại nguồn:** làm rõ điều đúng trước khi code, thiết kế cơ chế khó mắc lỗi và phát hiện sai lệch càng sớm càng hữu ích.
2. **Jidoka/Andon/Poka-yoke:** làm bất thường nhìn thấy được, ngăn lỗi lan và giảm sai sót bằng thiết kế; vận dụng theo bối cảnh phần mềm, không máy móc.
3. **Lát cắt nhỏ và WIP hợp lý:** ưu tiên hoàn tất, tích hợp và nhận phản hồi sớm thay vì mở nhiều việc rồi dồn kiểm thử cuối kỳ.
4. **Acceptance criteria và DoD bổ trợ nhau:** một cái làm rõ hành vi PBI, một cái tạo chuẩn chất lượng chung của Increment.
5. **XP và CI tăng tốc phản hồi kỹ thuật:** TDD/ATDD, review, pairing, tích hợp thường xuyên và kiểm thử phù hợp giúp phát hiện/sửa lỗi gần nguồn.
6. **Shift-left và shift-right đi cùng nhau:** xác minh sớm không thay thế khả năng quan sát, ứng cứu và học hỏi sau phát hành.
7. **Số liệu là phương tiện học hỏi:** xem lỗi, thời gian phản hồi, flow, khả năng phục hồi và outcome người dùng; không tối ưu một chỉ số đơn lẻ.
8. **Trách nhiệm được chia sẻ:** chất lượng không chỉ thuộc một phòng ban. Khi sát hạn, hãy minh bạch và quản lý phạm vi thay vì báo Done sai hoặc hạ chuẩn bắt buộc.

> **Câu hỏi ghi nhớ:** “Nếu lỗi quan trọng được phát hiện ở cuối Sprint hoặc sau phát hành, **phần nào của dòng tạo sản phẩm có thể phòng ngừa, nhận biết hoặc dừng lỗi sớm hơn** — và chúng ta sẽ kiểm chứng cải tiến đó như thế nào?”

### Tài liệu tham khảo

- [Lean Enterprise Institute](https://www.lean.org/) — nền tảng Lean, tư duy tạo giá trị, giảm lãng phí và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — empiricism, Lean thinking, Sprint Goal, Increment, Definition of Done, trách nhiệm Developers và kiểm tra–thích ứng.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, work item age và cycle time để quản lý và cải thiện dòng công việc.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — kiểm thử, TDD, tích hợp liên tục, refactoring và thực hành kỹ thuật giúp giảm chi phí thay đổi.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — chú trọng phần mềm hoạt động được, sự xuất sắc kỹ thuật, giao giá trị sớm và cải tiến thường xuyên.
