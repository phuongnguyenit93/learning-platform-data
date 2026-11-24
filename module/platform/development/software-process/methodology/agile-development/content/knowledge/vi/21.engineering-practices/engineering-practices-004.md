# BDD và trao đổi hành vi bằng ví dụ nghiệp vụ

Một yêu cầu có thể nghe rất rõ khi được phát biểu bằng một câu: “Hệ thống phải lưu tiến độ học tập của học viên”. Nhưng khi bắt đầu phát triển, mỗi người lại hiểu khác nhau. Người làm nghiệp vụ cho rằng “đã lưu” nghĩa là dữ liệu sẽ được khôi phục khi quay lại. Developer giao diện nghĩ chỉ cần gửi yêu cầu lưu thành công. Developer backend tính đến trường hợp dữ liệu cũ đến muộn. Người kiểm thử đặt câu hỏi về mạng chập chờn và học viên đăng nhập trên hai thiết bị.

Nếu những khác biệt này chỉ được phát hiện vào cuối Sprint, nhóm có thể đã xây một chức năng **đúng theo một cách hiểu nhưng sai đối với nhu cầu thực tế**. Một phương pháp hữu ích để giảm rủi ro ấy là **Behavior-Driven Development (BDD)**: cùng mô tả, khám phá và kiểm chứng **hành vi quan sát được của hệ thống** bằng những ví dụ cụ thể, trước và trong khi phát triển.

BDD không đơn giản là “viết kiểm thử bằng Given–When–Then”. Giá trị cốt lõi là **tạo hiểu biết chung giữa những người nhìn sản phẩm từ góc độ nghiệp vụ, phát triển và kiểm thử**, rồi dùng các ví dụ làm điểm tựa cho thiết kế, kiểm chứng và phản hồi. Những ví dụ phù hợp có thể được tự động hóa thành đặc tả có thể thực thi, nhưng **công cụ không thay thế cuộc trao đổi**.

Bài học thuộc chương **Thực hành kỹ thuật** của mô-đun **AGILE_DEVELOPMENT**. Nội dung liên hệ với Agile qua phản hồi sớm, bàn giao sản phẩm tăng dần, cải tiến liên tục, user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc.

**Sau bài học, bạn có thể:**

- Giải thích BDD là cách **khám phá và diễn đạt hành vi mong đợi**, không chỉ là framework kiểm thử.
- Chuyển một yêu cầu mơ hồ thành **quy tắc nghiệp vụ, ví dụ điển hình, trường hợp biên và câu hỏi còn mở**.
- Tổ chức trao đổi theo các góc nhìn **nghiệp vụ – phát triển – kiểm thử** (thường gọi là *Three Amigos*).
- Viết kịch bản **Given–When–Then** và Gherkin tập trung vào hành vi quan sát được.
- Phân biệt BDD với TDD, ATDD, acceptance criteria, Definition of Done và kiểm thử end-to-end.
- Chọn mức tự động hóa phù hợp, quản lý dữ liệu thử và tránh tạo bộ kiểm thử dễ vỡ.
- Dùng phản hồi từ ví dụ để chia nhỏ Product Backlog Item, làm rõ phạm vi và giao Increment có giá trị.

## 1. BDD là gì và giải quyết vấn đề nào?

**Behavior-Driven Development** là cách phát triển chú trọng vào **hành vi phần mềm cần thể hiện để đáp ứng nhu cầu**, được hình thành thông qua trao đổi bằng ngôn ngữ chung và các ví dụ cụ thể. Thay vì bắt đầu với danh sách lớp, API hoặc màn hình phải xây, nhóm đặt câu hỏi:

> “Trong hoàn cảnh nào, khi người dùng hoặc hệ thống thực hiện một hành động, kết quả nghiệp vụ nào phải quan sát được?”

Ví dụ, “Lưu tiến độ” là tên một chức năng; “Khi dịch vụ chưa xác nhận lưu, người học không được thấy thông báo ‘Đã lưu’” là **một hành vi có thể kiểm chứng**.

### Ba hoạt động liên kết với nhau

Một cách diễn giải BDD thực dụng gồm ba hoạt động có thể lặp lại:

1. **Discovery — Khám phá:** Cùng trao đổi mục tiêu, quy tắc, ví dụ, trường hợp ngoại lệ và điều chưa biết.
2. **Formulation — Diễn đạt:** Chọn những ví dụ quan trọng, viết thành ngôn ngữ đủ rõ để cả nhóm cùng hiểu; có thể dùng Given–When–Then.
3. **Automation — Tự động kiểm chứng:** Khi hợp lý, biến các ví dụ thành kiểm thử thực thi để phần mềm thường xuyên cho phản hồi về hành vi đã thống nhất.

~~~mermaid
flowchart LR
    A["Nhu cầu / Product Goal"] --> B["Discovery: trao đổi quy tắc và ví dụ"]
    B --> C["Formulation: hành vi quan sát được"]
    C --> D["Automation: kiểm chứng bằng phần mềm"]
    D --> E["Phản hồi về kết quả và cách hiểu"]
    E --> B
    E --> F["Increment hữu ích / thích ứng backlog"]
~~~

**Automation không phải điểm khởi đầu bắt buộc và cũng không phải mục tiêu duy nhất.** Một ví dụ chưa đủ rõ, chưa được nghiệp vụ xác nhận mà được tự động hóa rất nhanh có thể biến **sự hiểu sai thành một kiểm thử luôn xanh**.

### BDD giúp giảm những khoảng cách nào?

| Khoảng cách | Biểu hiện thường gặp | BDD hỗ trợ thế nào? |
| --- | --- | --- |
| **Nghiệp vụ – kỹ thuật** | “Lưu thành công” được hiểu khác nhau | Dùng một ví dụ cụ thể để xác nhận ý nghĩa |
| **Yêu cầu – kiểm thử** | Kiểm thử chỉ dựa trên suy đoán riêng của tester | Cùng thống nhất kết quả mong đợi trước khi triển khai |
| **Thiết kế – giá trị** | Mọi người tranh luận cấu trúc API nhưng quên vấn đề học viên | Bắt đầu từ hành vi và kết quả người dùng cần |
| **Kế hoạch – phản hồi** | Chỉ biết yêu cầu sai khi demo cuối Sprint | Kiểm chứng những giả định quan trọng sớm hơn |
| **Kiến thức – bảo trì** | Người mới không biết vì sao một điều kiện tồn tại | Ví dụ và kiểm thử rõ giúp giải thích quy tắc |

BDD không loại bỏ hoàn toàn sự mơ hồ; nó tạo **một cách thường xuyên làm lộ và xử lý sự mơ hồ** trước khi chi phí sửa sai trở nên lớn.

## 2. Từ câu yêu cầu mơ hồ đến hành vi quan sát được

Hãy xem ba cách mô tả cùng một nhu cầu:

| Mức diễn đạt | Nội dung | Vấn đề hoặc lợi ích |
| --- | --- | --- |
| **Tên tính năng** | “Lưu tiến độ học” | Quá rộng; chưa nói thành công là gì |
| **User story** | “Là học viên học dở, tôi muốn tiếp tục từ vị trí đã lưu để không phải học lại.” | Làm rõ ai và vì sao, nhưng vẫn thiếu quy tắc cụ thể |
| **Ví dụ nghiệp vụ** | “Học viên đã hoàn thành bước 4 và hệ thống xác nhận lưu; khi quay lại bài, học viên tiếp tục ở bước 4.” | Có bối cảnh, hành động và kết quả có thể kiểm chứng |

User story là **đầu mối hội thoại**, không phải tài liệu hoàn chỉnh của mọi yêu cầu. BDD giúp hội thoại ấy đi sâu đến các trường hợp có thể làm thay đổi thiết kế hoặc sự hài lòng của người dùng.

### Năm câu hỏi làm rõ hữu ích

1. **Ai** được hưởng lợi hoặc chịu tác động?
2. **Điều kiện ban đầu** nào quan trọng để hiểu hành vi?
3. **Sự kiện/hành động** nào kích hoạt quy tắc?
4. **Kết quả nào quan sát được** ở góc nhìn người dùng hoặc hệ thống liên quan?
5. **Ngoại lệ và ranh giới** nào có thể thay đổi câu trả lời?

Ví dụ:

> **Cho trước:** Học viên đã hoàn thành bước 4 và dịch vụ xác nhận đã lưu tiến độ đó.
>
> **Khi:** Học viên đóng rồi mở lại bài trên cùng thiết bị, với cùng tài khoản.
>
> **Thì:** Học viên được đưa về bước 4 theo quy tắc khôi phục đã thống nhất.

Kịch bản trên đủ cụ thể để thảo luận, nhưng vẫn cần kiểm tra “đưa về bước 4” nghĩa là **điểm bắt đầu bước 4 hay vị trí sau khi hoàn thành bước 4**. Những chi tiết nhỏ có thể làm lộ quy tắc bị bỏ quên.

### Ngôn ngữ chung là tài sản của nhóm

Nếu người kinh doanh dùng “tiến độ đã lưu”, backend dùng “request accepted” và UI dùng “success”, cần phân biệt:

| Thuật ngữ | Định nghĩa nghiệp vụ cần thống nhất |
| --- | --- |
| **Đang lưu** | Yêu cầu đã gửi nhưng chưa có bằng chứng xác nhận thành công |
| **Đã lưu thành công** | Dịch vụ đã xác nhận dữ liệu đạt điều kiện lưu theo hợp đồng đã thống nhất |
| **Lưu thất bại** | Hệ thống xác định thao tác không hoàn tất thành công |
| **Không biết kết quả** | Ví dụ timeout: yêu cầu có thể đã xử lý nhưng bên gọi chưa nhận xác nhận |
| **Tiến độ được khôi phục** | Học viên nhìn thấy trạng thái phù hợp với dữ liệu đã được lưu |

**Không tự đồng nhất timeout với chắc chắn lưu thất bại.** Một request có thể thành công ở máy chủ nhưng phản hồi thất lạc. Cách hiển thị, retry và tránh ghi đè cần được nghiệp vụ và kỹ thuật thảo luận riêng.

## 3. Những người cần tham gia trao đổi: Three Amigos

Trong BDD, thuật ngữ **Three Amigos** thường diễn tả ba **góc nhìn cộng tác**, không bắt buộc đúng ba người hay ba chức danh:

- **Nghiệp vụ/sản phẩm:** Người hiểu vấn đề, giá trị, ưu tiên và quy tắc nghiệp vụ. Có thể là Product Owner, chuyên gia nghiệp vụ hoặc đại diện người dùng.
- **Phát triển/kỹ thuật:** Người hiểu tính khả thi, kiến trúc, dữ liệu, tích hợp, bảo mật và chi phí thay đổi.
- **Kiểm thử/chất lượng:** Người chủ động tìm ví dụ phản chứng, trường hợp biên, trạng thái bất thường và cách quan sát kết quả.

Một Developer có thể đưa ra góc nhìn kiểm thử; một người kiểm thử có thể hiểu nghiệp vụ rất sâu. Điều cốt lõi là **không có góc nhìn quan trọng bị vắng mặt**, chứ không phải kiểm đủ ba chức danh trên lịch họp.

### Ví dụ hội thoại ngắn

**Product Owner:** “Học viên phải tiếp tục được ở chỗ đã học.”

**Developer:** “Nếu ứng dụng gửi yêu cầu lưu nhưng kết nối đứt trước khi nhận phản hồi, chúng ta có thể chưa biết máy chủ đã ghi dữ liệu hay chưa.”

**Tester:** “Vậy có được hiện ‘Đã lưu’ ngay khi bấm nút không? Nếu người học đóng trang trong lúc trạng thái chưa chắc chắn thì sao?”

**Product Owner:** “Không được khẳng định đã lưu khi chưa có xác nhận. Học viên cần hiểu rằng tiến độ có thể chưa được đồng bộ và có lựa chọn phù hợp để kiểm tra lại.”

Cuộc trao đổi tạo ra **quy tắc mới và một tình huống kiểm thử**, không chỉ làm rõ từ ngữ. Đây chính là giá trị của BDD trước khi viết nhiều mã.

### Cách điều phối một phiên trao đổi hiệu quả

1. Chọn **một Product Backlog Item hoặc lát cắt** đủ nhỏ.
2. Nhắc lại **người dùng và kết quả mong muốn**, tránh bắt đầu bằng giải pháp kỹ thuật.
3. Đưa ra **một ví dụ bình thường**, rồi những tình huống thay đổi kết quả.
4. Hỏi “Điều kiện nào làm ví dụ này không còn đúng?”.
5. Ghi **quy tắc, ví dụ, câu hỏi còn mở và quyết định về phạm vi**.
6. Kết thúc khi đã đủ hiểu để chọn bước tiếp: làm tiếp, chia nhỏ, hỏi nghiệp vụ, thử kỹ thuật hoặc hoãn hạng mục.

Không cần biến mỗi buổi Three Amigos thành cuộc họp dài cố định. Nếu mọi người đã hiểu và không có bất định quan trọng, trao đổi có thể rất ngắn. Nếu phát hiện phụ thuộc lớn, việc hữu ích có thể là **một phép thử hoặc quyết định ngoài cuộc họp**, không phải tranh luận thêm về câu chữ.

## 4. Example Mapping: đưa quy tắc, ví dụ và câu hỏi lên cùng một bàn

**Example Mapping** là một kỹ thuật trao đổi nhẹ thường được dùng trong BDD để cấu trúc hiểu biết. Một cách trình bày phổ biến dùng bốn loại thẻ:

| Loại thẻ | Nội dung | Ví dụ |
| --- | --- | --- |
| **Story** | Hạng mục hoặc mục tiêu cần trao đổi | “Tiếp tục bài học từ tiến độ đã lưu” |
| **Rule (quy tắc)** | Điều hệ thống phải tuân theo trong một ngữ cảnh | “Không khẳng định lưu thành công khi chưa có xác nhận” |
| **Example (ví dụ)** | Một tình huống cụ thể chứng minh quy tắc | “Yêu cầu lưu đang pending → hiển thị đang đồng bộ” |
| **Question (câu hỏi)** | Điều chưa được quyết định hoặc chưa biết | “Nếu response thất lạc nhưng máy chủ đã lưu, thông báo gì?” |

Không nhất thiết dùng giấy màu hoặc phần mềm chuyên dụng. Có thể viết trên bảng, Markdown hay công cụ cộng tác, miễn dễ nhìn và dễ chỉnh.

### Example Mapping cho chức năng lưu tiến độ

~~~text
STORY: Học viên tiếp tục được từ tiến độ đã lưu

RULE R1: Chỉ xác nhận lưu thành công khi dịch vụ đã xác nhận
  EXAMPLE E1: Xác nhận thành công -> hiển thị "Đã lưu"
  EXAMPLE E2: Chưa nhận xác nhận -> không hiển thị "Đã lưu"
  EXAMPLE E3: Lưu bị từ chối -> hiển thị trạng thái chưa lưu

RULE R2: Khôi phục theo dữ liệu đã được lưu hợp lệ
  EXAMPLE E4: Đã lưu bước 4 -> mở lại hiển thị vị trí phù hợp bước 4
  EXAMPLE E5: Chưa có dữ liệu -> mở theo hành vi mặc định đã thống nhất

QUESTION Q1: Timeout khác lỗi xác nhận như thế nào?
QUESTION Q2: Dữ liệu cũ từ thiết bị khác có thể ghi đè dữ liệu mới không?
QUESTION Q3: Nếu học viên chủ động học lại bài cũ thì quy tắc là gì?
~~~

**R1 và R2 liên quan nhưng có thể cần các lát cắt khác nhau.** R1 nói về thông báo trạng thái, R2 nói về khôi phục. Q2 và Q3 có thể làm thay đổi thiết kế đồng bộ đa thiết bị. Nhóm không nên ép mọi câu hỏi vào một story chỉ vì chúng đều thuộc “tiến độ học”.

### Khi nào cần chia story?

Dấu hiệu:

- Một story chứa nhiều quy tắc ít phụ thuộc nhau và không thể hoàn tất trong thời gian phù hợp.
- Mỗi quy tắc đòi hỏi đối tượng sử dụng, quyết định hoặc dữ liệu khác nhau.
- Một câu hỏi chưa rõ có thể thay đổi đáng kể kiến trúc hoặc phạm vi.
- Một số ví dụ đã đủ rõ để bàn giao có giá trị, phần còn lại cần nghiên cứu thêm.

Kết quả của Example Mapping có thể là **tách hạng mục hoặc điều chỉnh thứ tự Product Backlog**, không chỉ tạo thêm kiểm thử.

## 5. Given–When–Then: cú pháp đơn giản, tư duy phải chính xác

**Given–When–Then** là một cấu trúc phổ biến để diễn đạt ví dụ:

- **Given (Cho trước):** Bối cảnh hoặc trạng thái cần thiết.
- **When (Khi):** Hành động hoặc sự kiện làm hành vi được kích hoạt.
- **Then (Thì):** Kết quả quan sát được hoặc quy tắc cần được thỏa mãn.

Đọc thành một câu chuyện dễ hiểu:

> **Given** học viên đã được xác nhận lưu tiến độ ở bước 4.
>
> **When** học viên quay lại bài học với cùng tài khoản.
>
> **Then** hệ thống khôi phục tiến độ tương ứng với bước 4.

### Phân biệt đầu vào, kích hoạt và kết quả

| Thành phần | Nên mô tả | Tránh lạm dụng |
| --- | --- | --- |
| **Given** | Dữ liệu và bối cảnh quan trọng đối với quy tắc | Hàng chục thao tác kỹ thuật để khởi tạo database |
| **When** | Một sự kiện/hành động có ý nghĩa | Mỗi cú click, chờ animation, gọi từng method nội bộ |
| **Then** | Kết quả có thể quan sát và kiểm chứng | “Hàm private X được gọi ba lần” khi nghiệp vụ không yêu cầu |

Không phải mọi hành vi đều cần tác nhân người dùng trực tiếp. Một **sự kiện hệ thống** (ví dụ phản hồi xác nhận lưu) cũng có thể là When. Điều quan trọng là **mối liên hệ nguyên nhân–kết quả được phát biểu rõ**.

### Một kịch bản tốt không cần kể lại tất cả chi tiết giao diện

Ví dụ chưa tốt:

~~~text
Given tôi mở Chrome
And tôi nhấp vào nút có CSS selector "#save-button"
And tôi đợi 1500 mili giây
When tôi bấm vào phần tử thứ ba trên màn hình
Then div có class ".success-green" được hiển thị
~~~

Kịch bản quá phụ thuộc DOM, màu sắc và thời gian cố định; dễ vỡ khi đổi UI dù hành vi nghiệp vụ vẫn đúng.

Ví dụ rõ hơn:

~~~gherkin
Scenario: Thông báo khi chưa nhận xác nhận lưu
  Given học viên đã hoàn thành một bước học
  And dịch vụ lưu tiến độ chưa xác nhận thành công
  When học viên xem trạng thái lưu
  Then hệ thống không thông báo tiến độ đã được lưu thành công
  And học viên thấy trạng thái đang chờ xác nhận phù hợp
~~~

Ví dụ thứ hai **độc lập hơn với cách hiện thực**, nhưng vẫn cần cặp phát triển/kiểm thử quyết định cách điều khiển phản hồi dịch vụ để kiểm thử có thể lặp lại.

## 6. Gherkin là ngôn ngữ diễn đạt kịch bản, không phải toàn bộ BDD

**Gherkin** là cú pháp văn bản có cấu trúc thường dùng với các công cụ như Cucumber. Các từ khóa phổ biến gồm:

- **Feature:** Năng lực hoặc nhóm hành vi được mô tả.
- **Rule:** Một quy tắc nghiệp vụ cần được thực hiện (khi công cụ hỗ trợ cú pháp này).
- **Scenario:** Một ví dụ cụ thể.
- **Given / When / Then:** Bối cảnh, kích hoạt và kết quả.
- **And / But:** Nối thêm điều kiện cùng vai trò.
- **Scenario Outline / Examples:** Biểu diễn cùng một mẫu hành vi với nhiều bộ dữ liệu.
- **Background:** Bối cảnh chung phù hợp cho nhiều kịch bản trong cùng phạm vi.

Trong các ví dụ sau, ta dùng **từ khóa tiếng Anh** để thuận tiện với nhiều bộ công cụ Gherkin; **nội dung từng bước bằng tiếng Việt**. Việc dùng từ khóa theo ngôn ngữ khác tùy hỗ trợ và cấu hình của công cụ. Không cần Gherkin để thực hành BDD: một bảng ví dụ rõ ràng cũng có thể hỗ trợ hội thoại rất tốt.

### Feature và các kịch bản đầu tiên

~~~gherkin
Feature: Thông báo trạng thái lưu tiến độ học
  Để không hiểu nhầm rằng tiến độ đã được bảo toàn
  Là một học viên đang học dở
  Tôi muốn biết khi nào việc lưu thực sự thành công

  Scenario: Dịch vụ xác nhận lưu thành công
    Given học viên đã hoàn thành bước 4 của bài học
    And dịch vụ xác nhận tiến độ bước 4 đã được lưu
    When học viên kiểm tra trạng thái lưu
    Then học viên thấy thông báo "Đã lưu tiến độ"

  Scenario: Chưa nhận được xác nhận
    Given học viên đã hoàn thành bước 4 của bài học
    And dịch vụ chưa xác nhận tiến độ được lưu
    When học viên kiểm tra trạng thái lưu
    Then học viên không thấy thông báo "Đã lưu tiến độ"
    And học viên được thông báo việc lưu chưa được xác nhận

  Scenario: Dịch vụ từ chối lưu
    Given học viên đã hoàn thành bước 4 của bài học
    And dịch vụ xác nhận thao tác lưu không thành công
    When học viên kiểm tra trạng thái lưu
    Then học viên được thông báo chưa thể lưu tiến độ
    And hệ thống không khẳng định dữ liệu đã được bảo toàn
~~~

Các kịch bản này mô tả **hành vi quan sát được**. Chúng chưa tự giải thích cách máy chủ phát trạng thái xác nhận; nhóm cần làm rõ hợp đồng API và các kiểm thử tích hợp riêng.

### Kịch bản được chọn cần minh họa quy tắc, không lập lại mọi biến thể

Nếu có 200 giá trị đầu vào nhưng chỉ ba nhóm kết quả nghiệp vụ, viết 200 kịch bản gần giống nhau có thể làm đặc tả khó đọc. Hãy chọn các trường hợp **đại diện, biên, ngoại lệ và rủi ro cao**. Những tổ hợp dữ liệu kỹ thuật bổ sung có thể kiểm tra bằng unit test hoặc kiểm thử dữ liệu theo lớp thích hợp.

## 7. Scenario Outline và bảng ví dụ

**Scenario Outline** hữu ích khi **cùng một quy tắc** được kiểm tra với vài giá trị khác nhau. Ví dụ:

~~~gherkin
Feature: Hiển thị trạng thái lưu tiến độ

  Scenario Outline: Thông điệp phản ánh kết quả lưu
    Given dịch vụ lưu tiến độ có trạng thái "<trang_thai>"
    When học viên xem thông điệp lưu
    Then thông điệp hiển thị là "<thong_diep>"

    Examples:
      | trang_thai | thong_diep                         |
      | CONFIRMED  | Đã lưu tiến độ                    |
      | PENDING    | Đang đồng bộ, chưa xác nhận lưu   |
      | REJECTED   | Chưa thể lưu tiến độ              |
~~~

Đây là một **bảng ví dụ minh họa hợp đồng hiển thị**, không phải tuyên bố rằng mọi trạng thái lưu của hệ thống thực chỉ có ba giá trị này. Trong thực tế, nhóm cần làm rõ timeout, lỗi xác thực, yêu cầu bị hủy hoặc cập nhật đến muộn.

### Khi nào không nên dùng Scenario Outline?

Không nên gộp những hành vi có **quy tắc và lý do khác nhau** vào một bảng khổng lồ chỉ để giảm số dòng. Ví dụ xác thực quyền truy cập, xử lý xung đột tiến độ và nội dung thông báo có thể cần **những ví dụ độc lập**, vì mỗi nhóm giải thích một quyết định nghiệp vụ khác nhau.

### Một số kỹ thuật chọn ví dụ

| Kỹ thuật | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Phân lớp tương đương** | Những đầu vào nào dẫn đến cùng quy tắc? | CONFIRMED, PENDING, REJECTED |
| **Giá trị biên** | Ở ranh giới nào kết quả đổi? | Hoàn thành bước cuối cùng so với chưa hoàn thành |
| **Chuyển trạng thái** | Hệ thống có thể chuyển từ trạng thái nào sang trạng thái nào? | PENDING → CONFIRMED, PENDING → REJECTED |
| **Ngoại lệ** | Khi không có quyền hoặc dữ liệu không hợp lệ thì sao? | Học viên truy cập tiến độ của người khác |
| **Trình tự sự kiện** | Điều gì xảy ra nếu sự kiện đến muộn hoặc lặp? | Xác nhận của yêu cầu cũ đến sau yêu cầu mới |
| **Ví dụ phản chứng** | Tình huống nào chứng minh quy tắc hiện tại sai? | UI báo thành công ngay khi chỉ mới gửi request |

Không cần dùng tất cả kỹ thuật trong mỗi story. Hãy ưu tiên những ví dụ có **khả năng thay đổi thiết kế, độ tin cậy hoặc quyết định sản phẩm**.

## 8. Từ quy tắc nghiệp vụ đến dữ liệu thử đáng tin cậy

Một ví dụ đúng về ngữ nghĩa vẫn có thể trở thành kiểm thử không ổn định nếu **dữ liệu thử hoặc thời điểm quan sát** không được kiểm soát.

### Dữ liệu cần có ý nghĩa nghiệp vụ

Ví dụ:

~~~text
Học viên: H1, đang đăng nhập hợp lệ
Bài học: L1
Tiến độ đã xác nhận trước đó: bước 3
Hành động: hoàn thành bước 4
Kết quả dịch vụ lưu:
  Chưa xác nhận -> PENDING
  Đã xác nhận lưu bước 4 -> CONFIRMED
Kết quả mong đợi:
  Chỉ sau xác nhận mới hiển thị "Đã lưu tiến độ".
~~~

Nếu API chỉ nhận request nhưng chưa ghi dữ liệu, nhóm **không được mô phỏng trạng thái CONFIRMED** rồi dùng kiểm thử UI để tuyên bố toàn bộ luồng lưu là đúng. Kiểm thử UI có thể kiểm tra thông điệp; kiểm thử tích hợp phải kiểm chứng ngữ nghĩa xác nhận và việc khôi phục.

### Những nguồn kiểm thử không ổn định

- Phụ thuộc trực tiếp vào môi trường dùng chung đang thay đổi.
- Dùng dữ liệu thật không được kiểm soát hoặc dữ liệu cá nhân nhạy cảm.
- Giả định thao tác mạng hoàn tất trong một khoảng chờ cố định.
- Dùng thứ tự thực thi test để chuẩn bị trạng thái của test sau.
- Không làm sạch dữ liệu, khiến chạy lại ra kết quả khác.
- Mô phỏng toàn bộ hệ thống tới mức không còn kiểm chứng tích hợp thực tế.

**Giải pháp:** Thiết lập dữ liệu thử độc lập, sử dụng clock/stub/fake có kiểm soát khi hợp lý, tạo cơ chế chờ theo điều kiện quan sát được và có những kiểm thử tích hợp với thành phần thực tại các ranh giới quan trọng.

### BDD không cho phép bỏ ràng buộc an toàn

Khi kịch bản liên quan tài khoản học viên, không được dùng dữ liệu thật không có quyền hoặc bỏ qua xác thực để “test dễ hơn”. Nên dùng **dữ liệu tổng hợp, tài khoản thử, quyền tối thiểu** và kiểm tra điều kiện bảo vệ dữ liệu theo quy định.

## 9. Khi nhiều ví dụ liên quan nhau: trạng thái và chuỗi sự kiện

Những hệ thống bất đồng bộ thường có quy tắc phức tạp hơn một đầu vào đơn.

### Một sơ đồ trạng thái minh họa

~~~mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Pending: Học viên hoàn thành bước
    Pending --> Confirmed: Nhận xác nhận lưu hợp lệ
    Pending --> Rejected: Nhận kết quả từ chối lưu
    Pending --> Unknown: Hết thời gian chờ nhưng chưa biết kết quả
    Unknown --> Confirmed: Kiểm tra thấy đã lưu
    Unknown --> Rejected: Xác minh chắc chắn chưa lưu
    Confirmed --> Pending: Có thay đổi tiến độ mới
    Rejected --> Pending: Thử lưu lại theo chính sách
~~~

**Sơ đồ chỉ là một mô hình ví dụ**, không phải máy trạng thái chuẩn cho mọi ứng dụng. Nhóm cần xác nhận liệu “Unknown” có phải trạng thái nghiệp vụ cần hiển thị, hệ thống kiểm tra lại ra sao và khi nào được phép thử lại.

### Ba tình huống nên tách để thảo luận

1. **Mất phản hồi:** Server đã lưu nhưng client không biết. Không được mặc định “thất bại” nếu chưa có bằng chứng.
2. **Yêu cầu lặp:** Người học bấm lưu nhiều lần hoặc client retry. Hệ thống cần quy tắc chống tác động lặp ngoài ý muốn, thường liên quan idempotency.
3. **Phản hồi cũ đến muộn:** Yêu cầu lưu tiến độ cũ hoàn tất sau yêu cầu mới. Cần quyết định thế nào là cập nhật hợp lệ; không tự mặc định “lấy số bước lớn nhất” nếu người học có thể chủ động học lại.

Những câu hỏi này có thể là **hạng mục riêng hoặc spike kỹ thuật** trước khi mở rộng đa thiết bị. BDD giúp làm lộ rủi ro sớm, không bảo đảm mọi bài toán khó đều được giải bằng vài dòng Gherkin.

## 10. Tự động hóa ví dụ: chọn đúng lớp kiểm chứng

Trong thực tế, tự động hóa kiểm thử BDD có thể diễn ra ở **nhiều lớp**:

| Lớp | Ví dụ cần chứng minh | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Domain / unit** | Với PENDING, không được tạo thông điệp “Đã lưu” | Nhanh, ít phụ thuộc, dễ xác định lỗi | Không chứng minh API đã lưu dữ liệu thật |
| **Service / API** | Gửi yêu cầu lưu, đọc lại tiến độ theo hợp đồng | Kiểm chứng luồng dịch vụ và dữ liệu | Chưa chứng minh hiển thị và thao tác người dùng |
| **Contract** | Client/server thống nhất trạng thái và ý nghĩa response | Phát hiện hợp đồng không tương thích | Không tự xác nhận kết quả nghiệp vụ end-to-end |
| **UI / end-to-end** | Học viên thao tác và nhìn đúng trạng thái khôi phục | Gần hành trình sử dụng thực tế | Thường chậm và dễ phụ thuộc môi trường |
| **Quan sát sau phát hành** | Học viên có ít mất tiến độ và ít hiểu nhầm hơn không? | Kiểm tra giá trị thực, độ tin cậy trong vận hành | Không thay thế kiểm thử trước phát hành |

**Không phải kịch bản nghiệp vụ nào cũng cần chạy qua trình duyệt.** Nếu một quy tắc có thể được kiểm chứng ở domain/service với tín hiệu rõ, chạy toàn bộ qua UI có thể làm tăng chi phí, thời gian chờ và test flakiness. Những hành trình trọng yếu vẫn cần một số kiểm chứng end-to-end có chọn lọc.

### Ví dụ Java/JUnit: kiểm chứng quy tắc hiển thị

Ta dùng một hàm thuần nhỏ để minh họa một quy tắc đã thống nhất. **Mã chỉ mô tả cách hiển thị trạng thái**, không triển khai cơ chế lưu dữ liệu thật.

~~~java
enum SaveState {
    CONFIRMED,
    PENDING,
    REJECTED
}

final class SaveStatusText {
    private SaveStatusText() {}

    static String from(SaveState state) {
        return switch (state) {
            case CONFIRMED -> "Đã lưu tiến độ";
            case PENDING -> "Đang đồng bộ, chưa xác nhận lưu";
            case REJECTED -> "Chưa thể lưu tiến độ";
        };
    }
}
~~~

Kiểm thử tương ứng bằng JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SaveStatusTextTest {
    @Test
    void pendingMustNotClaimSaved() {
        assertEquals(
            "Đang đồng bộ, chưa xác nhận lưu",
            SaveStatusText.from(SaveState.PENDING)
        );
    }

    @Test
    void confirmedCanBeShownAsSaved() {
        assertEquals(
            "Đã lưu tiến độ",
            SaveStatusText.from(SaveState.CONFIRMED)
        );
    }

    @Test
    void rejectedMustNotClaimSaved() {
        assertEquals(
            "Chưa thể lưu tiến độ",
            SaveStatusText.from(SaveState.REJECTED)
        );
    }
}
~~~

Ví dụ dùng **switch expression của Java hiện đại** và cú pháp JUnit 5. Để chạy thật cần có dự án Java, dependency JUnit phù hợp và cấu hình test. Kiểm thử xanh chỉ chứng minh **hàm chuyển trạng thái theo đầu vào đã cho**; một kiểm thử tích hợp cần xác minh dịch vụ chỉ phát CONFIRMED theo quy tắc lưu thực.

### Gherkin và step definitions

Trong công cụ như Cucumber, mỗi bước Gherkin được **liên kết với mã thực thi (step definition)**. Đoạn mã này có thể chuẩn bị dữ liệu, gọi hệ thống và kiểm tra kết quả. Nên tránh:

- Viết step definition chỉ in ra “pass” mà không kiểm chứng hành vi.
- Nhét toàn bộ nghiệp vụ vào mã bước Gherkin khiến người kỹ thuật không thể tái sử dụng.
- Tạo một bước chung quá mơ hồ (“hệ thống hoạt động đúng”) che giấu điều được quan sát.
- Dùng mỗi bước để thao tác từng phần tử DOM thay vì nói ngôn ngữ nghiệp vụ.

**Đặc tả có thể thực thi phải kiểm chứng đúng hành vi**; số dòng Gherkin không tự bảo đảm điều đó.

## 11. BDD, TDD và ATDD: liên quan nhưng không đồng nhất

| Cách tiếp cận | Điểm nhấn | Một dạng câu hỏi |
| --- | --- | --- |
| **BDD** | Cùng khám phá và diễn đạt hành vi có ý nghĩa bằng ví dụ, có thể tự động kiểm chứng | “Trong tình huống này, người học phải quan sát điều gì?” |
| **TDD** | Chu trình phát triển test-first ở mức kỹ thuật, thường Red–Green–Refactor | “Kiểm thử nhỏ nhất nào dẫn ta tới thiết kế và hành vi đúng?” |
| **ATDD (Acceptance Test-Driven Development)** | Đồng thuận tiêu chí chấp nhận và kiểm thử trước hoặc song hành với triển khai | “Làm sao biết hạng mục đáp ứng kỳ vọng chấp nhận?” |
| **Specification by Example** | Sử dụng các ví dụ cụ thể để tạo và duy trì đặc tả chung | “Ví dụ nào làm sáng tỏ quy tắc, ngoại lệ và phạm vi?” |

Các cách tiếp cận **có phần giao nhau**. Một nhóm có thể dùng BDD để làm rõ hành vi, viết tiêu chí chấp nhận theo ATDD, rồi dùng TDD để phát triển hàm hoặc dịch vụ bảo vệ hành vi ấy. Không cần tranh luận một kịch bản “thuộc phương pháp nào” nhiều hơn giá trị của nó cho việc ra quyết định.

### BDD không đồng nghĩa “viết Gherkin trước rồi thôi”

Nếu Product Owner không tham gia làm rõ quy tắc, Developer suy đoán kết quả, tester tự động hóa và mọi người chỉ nhìn báo cáo xanh, nhóm có thể có **nhiều test BDD nhưng ít hiểu biết chung**.

Ngược lại, một nhóm có thể thực hành BDD hiệu quả bằng các bảng ví dụ và cuộc trao đổi rõ ràng dù chưa triển khai Cucumber. Tự động hóa thích hợp sẽ làm quy tắc được kiểm tra lặp lại, nhưng **không quyết định bản chất cuộc trao đổi**.

## 12. Acceptance criteria, Definition of Done và ví dụ BDD

Ba khái niệm bổ trợ nhau nhưng không thay thế nhau.

| Khái niệm | Trả lời | Ví dụ |
| --- | --- | --- |
| **Acceptance criteria** | Hành vi hoặc điều kiện riêng của Product Backlog Item là gì? | “Khi dịch vụ chưa xác nhận lưu, không hiển thị trạng thái đã lưu thành công.” |
| **Ví dụ BDD** | Một tình huống cụ thể minh họa quy tắc và kết quả | “Học viên hoàn thành bước 4; phản hồi lưu còn pending; UI hiển thị đang đồng bộ.” |
| **Definition of Done (Scrum)** | Increment phải đáp ứng tiêu chuẩn chất lượng nào để được coi hoàn thành? | Kiểm thử phù hợp, tích hợp, tuân thủ kiểm soát dữ liệu và chất lượng theo tiêu chuẩn nhóm/tổ chức |

Một Product Backlog Item có thể đáp ứng ba kịch bản BDD nhưng **chưa đạt Definition of Done** nếu chưa kiểm thử tích hợp thiết yếu hoặc chưa đáp ứng tiêu chuẩn bảo mật. Ngược lại, một quy trình kỹ thuật tốt không bảo đảm nhóm đã chọn **đúng hành vi đem lại giá trị**.

### Có cần “Definition of Ready” không?

Một số nhóm dùng những tiêu chí làm rõ PBI trước khi chọn làm, nhưng **Definition of Ready không phải commitment chính thức của Scrum Guide**. BDD và Example Mapping giúp nhóm đánh giá mức hiểu biết và bất định, không nên bị biến thành cổng phê duyệt cứng khiến mọi học hỏi phải hoàn tất trước Sprint.

### Ví dụ chấp nhận không phải hợp đồng bất biến

Khi người dùng hoặc nhóm tìm được bằng chứng mới, Product Owner và Developers có thể trao đổi, điều chỉnh phạm vi hoặc ví dụ phù hợp. Những thay đổi cần **minh bạch, giải thích lý do và bảo vệ mục tiêu chung**, không âm thầm sửa kiểm thử chỉ để hệ thống xanh.

## 13. Những giới hạn của BDD và trách nhiệm kiểm chứng bổ sung

BDD giúp mô tả hành vi nhưng **không tự bao phủ mọi thuộc tính chất lượng**:

- **Hiệu năng:** Thời gian phản hồi khi nhiều học viên học đồng thời.
- **Bảo mật:** Chỉ đúng tài khoản có quyền mới xem hoặc thay đổi tiến độ.
- **Khả năng phục hồi:** Dịch vụ tiếp tục hoặc khôi phục sau lỗi hạ tầng.
- **Khả năng tiếp cận:** Thông báo trạng thái có thể được người dùng dùng công nghệ hỗ trợ nhận biết.
- **Tính nhất quán dữ liệu:** Không ghi đè tiến độ sai khi có nhiều cập nhật.
- **Khả năng quan sát:** Có log, metric và tín hiệu để phát hiện lỗi thật.
- **Quy định/tuân thủ:** Dữ liệu cá nhân được xử lý theo chính sách thích hợp.

Một số điều kiện có thể được nêu bằng ví dụ BDD, nhưng thường cần **kiểm thử chuyên biệt, phân tích rủi ro, quan sát vận hành và chính sách kỹ thuật**. Không nên ép mọi yêu cầu phi chức năng vào một kịch bản Gherkin dài.

### Ghi rõ giới hạn phạm vi ví dụ

Ví dụ “khôi phục tiến độ sau tải lại trên cùng thiết bị” **không tự chứng minh** “đồng bộ offline trên mọi thiết bị”. Khi chưa có quy tắc cho dữ liệu xung đột, hãy ghi là **câu hỏi mở** thay vì dùng kết quả mặc định của code để lấp chỗ trống.

### Kịch bản xanh chưa chứng minh outcome

Ngay cả khi mọi kiểm thử chấp nhận đều đạt, người học vẫn có thể khó hiểu từ “đang đồng bộ”. Cần quan sát phản hồi và hành vi sử dụng thật; BDD cung cấp một **vòng phản hồi về tính đúng**, không thay thế hoàn toàn **vòng phản hồi về giá trị**.

## 14. Tình huống xuyên suốt: làm rõ chức năng tiến độ qua ba vòng BDD

**Bối cảnh giả định:** Nền tảng học trực tuyến nhận phản ánh người học mất tiến độ hoặc hiểu lầm đã lưu thành công. Product Goal là giúp học viên tiếp tục học đáng tin cậy. Product Owner chọn một lát cắt nhỏ: thông báo đúng trạng thái lưu và khôi phục tiến độ đã xác nhận trên cùng tài khoản, trong phạm vi có kết nối.

### Vòng 1 — Khám phá nhu cầu thực

Một yêu cầu ban đầu:

> “Bổ sung thông báo lưu tiến độ khi học viên hoàn thành bước.”

Nhóm thảo luận và ghi:

| Phát hiện | Loại | Tác động |
| --- | --- | --- |
| Học viên chỉ cần tin rằng phần đã hoàn thành sẽ không mất | **Mục tiêu** | Tập trung tính đáng tin cậy, không chỉ giao diện đẹp |
| UI đang báo thành công khi request vừa được gửi | **Giả định sai có rủi ro** | Cần phân biệt gửi yêu cầu và xác nhận lưu |
| Dịch vụ có thể trả phản hồi trễ | **Bất định kỹ thuật** | Cần làm rõ trạng thái chưa xác nhận |
| Học viên muốn được biết khi nào nên thử lại | **Nhu cầu** | Thiết kế thông điệp và hành động phù hợp |
| Quy tắc đồng bộ đa thiết bị chưa rõ | **Câu hỏi ngoài lát cắt đầu** | Ghi nhận và xem xét riêng |

Đầu ra quan trọng không phải số lượng tài liệu mà là **một quy tắc được thống nhất**:

> Chỉ được khẳng định “Đã lưu” khi hệ thống đã có xác nhận lưu hợp lệ; khi chưa biết kết quả phải thông báo trung thực, không giả định thành công.

### Vòng 2 — Diễn đạt ví dụ và chia nhỏ

Nhóm xây ba ví dụ điển hình:

| Tình huống | Kết quả được xác nhận | Điều không được làm |
| --- | --- | --- |
| Dịch vụ xác nhận lưu | Hiển thị “Đã lưu tiến độ” | Không duy trì trạng thái pending sai |
| Yêu cầu còn chờ/không biết kết quả | Thông báo chưa xác nhận | Không khẳng định đã lưu |
| Dịch vụ xác nhận từ chối | Thông báo chưa thể lưu và hướng xử lý phù hợp | Không để người dùng nghĩ dữ liệu đã bảo toàn |

Sau trao đổi, nhóm nhận ra một số câu hỏi thuộc **đồng bộ nhiều thiết bị** có thể làm sau. Lát cắt đầu vẫn phải giữ tính đúng đắn của thông báo và bảo vệ dữ liệu liên quan. Product Owner cập nhật Product Backlog, Developers xác định cách kiểm thử.

### Vòng 3 — Tự động kiểm chứng và nhận phản hồi

Developers cùng tester:

1. Viết kiểm thử domain cho cách hiển thị trạng thái.
2. Viết kiểm thử hợp đồng để phân biệt trạng thái máy chủ.
3. Kiểm thử tích hợp lưu/đọc lại dữ liệu trên cùng tài khoản.
4. Kiểm thử trường hợp timeout, mất mạng hoặc phản hồi trễ trong môi trường có thể kiểm soát.
5. Chọn một hoặc vài kiểm thử UI end-to-end cho hành trình quan trọng.
6. Tích hợp thay đổi theo CI và đánh giá theo Definition of Done.

Khi Increment đáp ứng tiêu chuẩn chất lượng, nhóm có thể đưa đến phạm vi thí điểm phù hợp theo quy trình phát hành. Trong Sprint Review, stakeholder thử các tình huống. Một người học phản hồi: “Tôi vẫn không biết trạng thái đang đồng bộ có an toàn để đóng trang chưa.” Nhóm ghi lại, làm rõ và cân nhắc một ví dụ nghiệp vụ mới.

### Điều đã thay đổi qua ba vòng

| Trước khi trao đổi | Sau khi làm rõ bằng ví dụ |
| --- | --- |
| “Thông báo lưu tiến độ” là tên tính năng chung chung | Có quy tắc xác nhận và ba trường hợp cụ thể |
| Frontend và backend tự suy đoán ý nghĩa “thành công” | Hai bên dùng một hợp đồng trạng thái được kiểm chứng |
| Kiểm thử chỉ kiểm tra thông báo xuất hiện | Kiểm thử xác minh thông báo **đúng với kết quả lưu** |
| Mọi khả năng bị gộp vào epic tiến độ lớn | Có lát cắt đầu và những câu hỏi cần xem xét sau |
| Phản hồi chủ yếu đến khi người học phàn nàn | Có phản hồi trong trao đổi, tự động kiểm chứng và sau thí điểm |

**Giá trị BDD nằm ở chuỗi trao đổi → làm rõ → kiểm chứng → học thêm**, không phải số lượng kịch bản Gherkin đã tạo.

## 15. Tích hợp BDD với Scrum

Trong Scrum, BDD có thể là cách làm giúp Scrum Team **biến Product Backlog Item thành Increment đúng hành vi**, nhưng không thay thế các accountability hoặc event của Scrum.

### Product Backlog refinement

Product Owner và Developers có thể trao đổi cùng người hiểu nghiệp vụ/kiểm thử để:

- Làm rõ giá trị và quy tắc của PBI ưu tiên.
- Chọn ví dụ điển hình cùng tình huống có rủi ro cao.
- Xác định bất định làm thay đổi ước lượng hoặc thứ tự.
- Chia hạng mục thành lát cắt có thể hoàn thành, kiểm chứng và bàn giao.

Product Backlog refinement là hoạt động diễn ra khi cần, **không phải một Scrum event chính thức** theo Scrum Guide 2020.

### Sprint Planning

Scrum Team xác định **vì sao Sprint có giá trị**, chọn hạng mục phù hợp và Developers lập kế hoạch thực hiện. Những ví dụ BDD giúp đánh giá liệu một lát cắt đã đủ hiểu để bắt đầu và làm thế nào chứng minh nó hoàn thành. Tuy nhiên, **Sprint Goal không phải tổng số kịch bản Gherkin**.

### Trong Sprint

Developers dùng ví dụ để thiết kế, viết kiểm thử, tích hợp và điều chỉnh kế hoạch khi phát hiện điều chưa rõ. Daily Scrum kiểm tra tiến độ hướng tới Sprint Goal; **không phải cuộc họp để đọc số kịch bản đã viết cho Scrum Master**.

### Sprint Review và Retrospective

**Sprint Review:** Scrum Team và stakeholder kiểm tra Increment thực, xem kết quả nghiệp vụ và điều chỉnh Product Backlog. Các ví dụ BDD giúp trình bày những tình huống đã hỗ trợ nhưng không nên biến Review thành buổi chạy hàng loạt test mà thiếu trao đổi giá trị.

**Sprint Retrospective:** Nhóm đánh giá BDD có giảm hiểu sai, giảm làm lại và rút ngắn thời gian làm rõ không, sau đó thử cải tiến cách phối hợp.

**Product Owner** vẫn chịu trách nhiệm quản lý giá trị và Product Backlog; **Developers** chịu trách nhiệm tạo Increment và chất lượng; **Scrum Master** hỗ trợ Scrum Team hiệu quả. BDD là **thực hành cộng tác và kỹ thuật**, không tạo thêm một chức danh có quyền quyết định thay các accountability này.

## 16. BDD kết hợp với Kanban, Lean và XP

### Kanban và Lean: làm rõ sớm để công việc không nằm chờ

Một Kanban workflow có thể gồm “Sẵn sàng → Đang phát triển → Chờ review → Đang kiểm thử → Done”. Nếu nhiều thẻ bị chặn vì quy tắc nghiệp vụ chưa rõ, BDD giúp làm lộ và xử lý **nguồn chờ đợi** trước khi công việc đi sâu vào phát triển.

Điều này không nghĩa nhóm phải viết **mọi ví dụ cho toàn bộ dự án từ đầu**. Theo Lean, hãy làm rõ **đúng lúc, vừa đủ cho lát cắt có giá trị**, nhận phản hồi rồi thích ứng; tránh lãng phí do đặc tả chi tiết cho những hạng mục có thể sẽ không được làm.

### XP và TDD: vòng phản hồi từ nghiệp vụ đến mã

BDD có thể giúp cả nhóm chọn **hành vi cần có**. TDD giúp Developers triển khai từng bước nhỏ và bảo vệ thiết kế bằng kiểm thử. Pair programming hỗ trợ thảo luận quy tắc và trường hợp biên ngay khi viết mã. Continuous Integration bảo đảm những kiểm chứng được chạy thường xuyên.

~~~mermaid
flowchart LR
    A["Ví dụ nghiệp vụ thống nhất"] --> B["Kiểm thử chấp nhận / quy tắc"]
    B --> C["TDD và phát triển lát cắt nhỏ"]
    C --> D["CI + kiểm tra chất lượng"]
    D --> E["Increment có thể sử dụng"]
    E --> F["Phản hồi người dùng / vận hành"]
    F --> A
~~~

### Không tạo nút thắt mới vì tự động hóa

Nếu viết một kịch bản Gherkin phải qua ba lớp phê duyệt, cần một môi trường UI đắt đỏ và chạy 30 phút cho mọi thay đổi nhỏ, bộ kiểm thử có thể **làm chậm vòng phản hồi**. Hãy xem thử:

- Quy tắc có thể kiểm chứng ở lớp domain/service nhanh hơn không?
- Có cần UI end-to-end cho mọi tổ hợp dữ liệu không?
- Những ví dụ nào thực sự có giá trị lâu dài để giữ?
- Có thể quản lý test data và môi trường hiệu quả hơn không?

BDD hiệu quả là **đúng hành vi, phản hồi kịp thời và chi phí duy trì hợp lý**.

## 17. Quản lý đặc tả và kiểm thử khi yêu cầu thay đổi

Ví dụ nghiệp vụ nên phản ánh **hiểu biết hiện tại đã được thống nhất**, không phải tài liệu bất biến. Khi Product Owner điều chỉnh phạm vi hoặc người dùng phản hồi cách hiểu cũ chưa đúng, nhóm cần cập nhật cả kịch bản và mã kiểm chứng.

### Một quy trình sửa đặc tả minh bạch

1. Xác nhận **bằng chứng hoặc lý do** yêu cầu đổi quy tắc.
2. Phân biệt **hành vi cũ sai** với **hành vi mới được bổ sung**.
3. Thảo luận ví dụ minh họa mới với các góc nhìn liên quan.
4. Cập nhật acceptance criteria và kịch bản có thể thực thi.
5. Cập nhật sản phẩm và kiểm thử ở lớp thích hợp.
6. Chạy lại kiểm chứng hồi quy, xác nhận không phá các quy tắc còn hiệu lực.
7. Ghi quyết định quan trọng hoặc tác động cần truyền đạt cho stakeholder.

### Đừng sửa test chỉ để pipeline xanh

Khi kiểm thử BDD thất bại, có ít nhất ba khả năng:

- **Sản phẩm sai** so với hành vi đã thống nhất.
- **Đặc tả lỗi thời** vì quy tắc đã thay đổi có chủ đích.
- **Kiểm thử hỏng** do môi trường, dữ liệu hoặc cách tự động hóa.

Nhóm cần xác định nguyên nhân. Xóa hoặc làm lỏng assertion chỉ để build xanh có thể che một lỗi sản phẩm thật. Ngược lại, giữ một kịch bản không còn phù hợp cũng gây lãng phí và thông tin sai.

### Ví dụ cần được tổ chức để người mới đọc được

Tránh một kho hàng nghìn kịch bản trùng lặp. Nhóm có thể:

- Nhóm kịch bản theo **quy tắc hoặc khả năng sản phẩm**.
- Dùng tên kịch bản mô tả hành vi, không chỉ mã ticket.
- Giữ phần Given ngắn, chỉ chứa ngữ cảnh cần thiết.
- Dùng Scenario Outline khi cùng một quy tắc áp dụng cho nhiều dữ liệu.
- Chuyển các tổ hợp kỹ thuật chi tiết xuống unit/integration tests.
- Loại bỏ ví dụ trùng ý nghĩa khi không còn cung cấp tín hiệu mới.

Tập đặc tả chất lượng tốt là **dễ hiểu, có liên hệ với nghiệp vụ và đáng tin khi chạy**, không nhất thiết là tập có nhiều file nhất.

## 18. Phản mẫu thường gặp khi áp dụng BDD

| Phản mẫu | Vì sao gây hại? | Cách cải thiện |
| --- | --- | --- |
| **BDD = mua công cụ Gherkin** | Có syntax nhưng không có hiểu biết chung | Bắt đầu từ trao đổi quy tắc và ví dụ |
| **Tester viết mọi kịch bản một mình** | Thiếu góc nhìn nghiệp vụ và kỹ thuật | Mời đủ góc nhìn đúng lúc |
| **Viết scenario sau khi code xong chỉ để hợp thức hóa** | Bỏ lỡ cơ hội phát hiện hiểu sai sớm | Trao đổi ví dụ trước hoặc song hành phát triển |
| **Given–When–Then mô tả click/selector** | Kịch bản dễ vỡ khi đổi UI | Viết bằng ngôn ngữ hành vi quan sát được |
| **Một kịch bản chứa toàn bộ hành trình nhiều tháng** | Khó hiểu, khó chẩn đoán và chậm chạy | Chia theo quy tắc và lát cắt có giá trị |
| **Hàng trăm ví dụ gần giống nhau** | Tăng chi phí duy trì, tín hiệu nhiễu | Chọn đại diện, biên và rủi ro cao |
| **Mọi ví dụ đều chạy qua UI** | Bộ test chậm và không ổn định | Dùng lớp domain/API/contract phù hợp |
| **Mock mọi thứ, không có kiểm thử tích hợp** | Test xanh nhưng hợp đồng thực sai | Kiểm chứng các ranh giới quan trọng |
| **Suy diễn quy tắc nghiệp vụ từ code hiện có** | Có thể tự động hóa hành vi sai | Xác nhận hành vi mong đợi với đúng người |
| **Timeout bị coi chắc chắn lưu thất bại** | Có thể báo sai trạng thái dữ liệu | Tách “không biết kết quả” và quy tắc xác minh |
| **Chỉ chạy ví dụ đẹp, bỏ ngoại lệ** | Lỗi chỉ lộ khi sử dụng thực tế | Tìm trường hợp phản chứng, trạng thái và phụ thuộc |
| **Gherkin được coi là toàn bộ Definition of Done** | Bỏ qua bảo mật, hiệu năng, tích hợp và chất lượng | Kết hợp tiêu chí riêng với DoD |
| **Sửa kịch bản để che kiểm thử thất bại** | Mất bằng chứng lỗi và sự minh bạch | Xác định sản phẩm sai, đặc tả cũ hay test hỏng |
| **Bắt mọi PBI phải có cuộc họp BDD dài** | Tăng hàng chờ và chi phí trao đổi | Chọn cách trao đổi vừa đủ theo bất định và rủi ro |
| **Chỉ đo số lượng scenario** | Khuyến khích viết nhiều test hình thức | Đánh giá hiểu biết, thời gian phản hồi và chất lượng |

## 19. Đo lường hiệu quả trao đổi hành vi và vòng phản hồi

BDD nên được đánh giá bằng khả năng **giảm hiểu sai và tạo phản hồi đáng tin cậy**, không bằng số file feature.

| Tín hiệu | Câu hỏi cần trả lời | Cẩn trọng |
| --- | --- | --- |
| **Thời gian chờ làm rõ yêu cầu** | PBI bị chặn do thiếu quy tắc bao lâu? | Không ép đóng câu hỏi khi chưa có quyết định |
| **Lỗi do hiểu sai nghiệp vụ** | Có giảm các lỗi hành vi bị phát hiện muộn? | Phân loại lỗi phải nhất quán |
| **Làm lại sau kiểm thử/chấp nhận** | Ví dụ sớm có giúp giảm thay đổi muộn? | Không quy mọi thay đổi cho thiếu BDD |
| **Thời gian phản hồi của pipeline** | Kiểm chứng có đủ nhanh để dùng thường xuyên? | Nhanh nhưng test thiếu chất lượng là vô ích |
| **Độ ổn định của test** | Kịch bản thất bại có thực sự chỉ ra vấn đề? | Flaky test dễ khiến mọi người bỏ qua cảnh báo |
| **Khả năng đọc hiểu** | Product Owner, tester, Developer có giải thích được quy tắc? | Không đo chỉ bằng số trang tài liệu |
| **Cycle time, WIP** | Công việc có ít bị chặn và nhanh tới Done? | Chú ý độ lớn hạng mục và rủi ro khác nhau |
| **Outcome người dùng** | Hành vi xây dựng có giải quyết nhu cầu không? | Kết quả có nhiều yếu tố tác động |

### Một thử nghiệm cải tiến có điều kiện

Nhóm nhận thấy nhiều lỗi chỉ được phát hiện sau khi UI và API tích hợp. Họ thử **trao đổi Example Mapping ngắn cho những PBI có quy tắc trạng thái phức tạp** trong hai Sprint.

~~~text
Giả thuyết:
  Làm rõ quy tắc và ví dụ có rủi ro sớm
  sẽ giảm chờ quyết định và lỗi hiểu sai khi tích hợp.

Phạm vi:
  Chọn 3-5 PBI có nhiều trạng thái/ngoại lệ;
  không bắt buộc áp dụng nghi thức dài cho mọi task.

Thay đổi:
  Cùng trao đổi góc nhìn nghiệp vụ, phát triển, kiểm thử;
  ghi quy tắc, ví dụ và câu hỏi;
  tự động hóa ví dụ quan trọng ở lớp phù hợp.

Quan sát:
  Số lần phải hỏi lại nghiệp vụ,
  thời gian bị chặn, lỗi hành vi,
  thời gian chạy và độ ổn định kiểm thử,
  phản hồi sau bàn giao.

Xem lại:
  Cuối từng Sprint và sau hai Sprint;
  tiếp tục, điều chỉnh hoặc dừng theo bằng chứng.
~~~

Không thể chắc chắn toàn bộ cải thiện do BDD: việc chia story tốt hơn, môi trường ổn định hoặc nhân sự có kinh nghiệm cũng ảnh hưởng. Hãy **ghi bối cảnh và quan sát nhiều vòng**.

## 20. Bài thực hành: từ yêu cầu mơ hồ tới đặc tả có thể kiểm chứng

**Bối cảnh:** Nền tảng học trực tuyến cần hỗ trợ học viên tiếp tục học từ tiến độ đã lưu; hiện có lỗi thông báo “Đã lưu” xuất hiện trước khi hệ thống xác nhận.

### Bài 1 — Tìm các câu hỏi nghiệp vụ

Yêu cầu ban đầu:

> “Sau khi người học hoàn thành một bước, hệ thống tự động lưu tiến độ và hiển thị thông báo.”

Hãy liệt kê ít nhất **sáu câu hỏi**. Gợi ý:

1. “Hoàn thành bước” được xác định ở thời điểm nào?
2. Khi nào được dùng từ “Đã lưu”?
3. Nếu mạng mất ngay sau thao tác, điều gì hiển thị?
4. Nếu server xử lý xong nhưng response thất lạc, hệ thống biết kết quả cách nào?
5. Nếu người dùng tải lại trang khi đang pending, trạng thái nào được khôi phục?
6. Nếu có yêu cầu cũ đến muộn, hệ thống tránh ghi đè thế nào?
7. Quyền xem/sửa tiến độ của tài khoản khác được bảo vệ ra sao?
8. Có cần hỗ trợ offline hoặc đa thiết bị trong lát cắt đầu không?

**Đáp án mở:** Câu hỏi tốt là câu có thể thay đổi hành vi, phạm vi, rủi ro hoặc tiêu chí kiểm chứng, không nhất thiết có một bộ đúng duy nhất.

### Bài 2 — Tạo Example Mapping

Điền bảng:

| Thẻ | Nội dung cần điền |
| --- | --- |
| **Story** | Học viên biết tiến độ đã lưu hay chưa và quay lại an toàn |
| **Rule 1** | ... |
| **Example 1** | ... |
| **Example 2** | ... |
| **Rule 2** | ... |
| **Example 3** | ... |
| **Question 1** | ... |
| **Question 2** | ... |

**Gợi ý:** Rule 1 có thể là “chỉ báo thành công khi có xác nhận”. Rule 2 có thể là “khôi phục đúng dữ liệu đã được lưu”. Câu hỏi mở có thể liên quan timeout hoặc xung đột; không cần tự tạo câu trả lời nếu nghiệp vụ chưa quyết định.

### Bài 3 — Viết kịch bản Given–When–Then

Hãy viết ba kịch bản với những tình huống:

- Dịch vụ xác nhận lưu thành công.
- Yêu cầu đang pending.
- Dịch vụ xác nhận từ chối lưu.

Mỗi kịch bản cần rõ **Given, When, Then** và không phụ thuộc CSS selector hoặc việc chờ cố định. Sau đó trao đổi với người hiểu nghiệp vụ xem thông điệp nào đã được xác nhận.

### Bài 4 — Thử tìm phản chứng

Một người đề xuất quy tắc:

> “Nếu request lưu trả HTTP 200 thì luôn hiển thị ‘Đã lưu’.”

Hãy hỏi:

1. HTTP 200 xác nhận điều gì theo hợp đồng API: nhận yêu cầu hay lưu bền vững?
2. Nếu phản hồi bị mất nhưng máy chủ đã lưu, UI nên xử lý thế nào?
3. Nếu một request cũ nhận response sau request mới, trạng thái nào đúng?
4. Kiểm thử ở **lớp nào** chứng minh được hợp đồng API thực sự phù hợp?
5. Có cần hỏi Product Owner về quy tắc nghiệp vụ trước khi quyết định không?

**Điểm quan trọng:** Kịch bản BDD không thể tự thay thế việc xác định hợp đồng và nguồn sự thật của dữ liệu.

### Bài 5 — Phân loại lớp kiểm thử

| Điều cần chứng minh | Lớp đề xuất | Vì sao? |
| --- | --- | --- |
| PENDING không tạo thông điệp “Đã lưu” | **Unit/domain** | Quy tắc hiển thị có thể kiểm chứng nhanh |
| API chỉ xác nhận theo đúng ngữ nghĩa lưu | **Service/API + tích hợp** | Cần kiểm tra nguồn dữ liệu và xử lý lưu |
| Client/server cùng hiểu mã trạng thái | **Contract** | Phát hiện sai lệch hợp đồng |
| Học viên tải lại và được khôi phục đúng tiến độ | **End-to-end chọn lọc** | Hành trình gồm nhiều thành phần |
| Người học hiểu trạng thái “đang đồng bộ” | **Thử khả dụng/phản hồi thực** | Kiểm thử tự động không đo đầy đủ sự hiểu của người dùng |

Hãy giải thích tại sao **không nên dùng test UI cho tất cả tổ hợp dữ liệu**, và cũng không nên chỉ mock mọi tầng.

### Bài 6 — Thiết kế một cải tiến hai Sprint

Giả sử trong ba Sprint gần đây, nhóm phải sửa nhiều logic lưu tiến độ vì hiểu khác quy tắc giữa PO, backend và frontend. Thiết kế một thử nghiệm BDD:

- Chọn các PBI có trạng thái hoặc ngoại lệ phức tạp.
- Mời đủ góc nhìn nghiệp vụ, phát triển và kiểm thử.
- Dùng Example Mapping ghi quy tắc, ví dụ và câu hỏi.
- Tự động hóa ít kịch bản có giá trị cao ở lớp phù hợp.
- Đo thời gian chờ làm rõ, lỗi hành vi, làm lại và tính ổn định test.
- Xem kết quả tại Retrospective và quyết định tiếp tục hay điều chỉnh.

**Thành công không phải viết được nhiều kịch bản**, mà là đội hiểu cùng hành vi, phát hiện sai sớm và giao Increment có chất lượng hơn.

## 21. Checklist trao đổi hành vi bằng ví dụ nghiệp vụ

- [ ] Bắt đầu từ **người dùng, giá trị và vấn đề**, không chỉ từ danh sách thành phần cần xây.
- [ ] Có đủ **góc nhìn nghiệp vụ, phát triển và kiểm thử** cho những quy tắc quan trọng.
- [ ] Phân biệt **mục tiêu, quy tắc, ví dụ, giả định và câu hỏi còn mở**.
- [ ] Mỗi ví dụ có **bối cảnh, sự kiện và kết quả quan sát được**.
- [ ] Kịch bản diễn đạt **ngôn ngữ nghiệp vụ**, không phụ thuộc chi tiết DOM hoặc method nội bộ nếu không cần.
- [ ] Có ví dụ **điển hình, biên và ngoại lệ** tương xứng với rủi ro.
- [ ] Câu hỏi chưa quyết được được **giao đúng người có thẩm quyền**, không âm thầm tự đoán.
- [ ] Phạm vi và phần **chưa bao gồm** của lát cắt được nêu rõ.
- [ ] Acceptance criteria và các ví dụ hỗ trợ **thỏa thuận hành vi**, không thay Definition of Done.
- [ ] Các ví dụ cần tự động hóa được đặt ở **lớp kiểm thử phù hợp**, tránh dồn mọi thứ qua UI.
- [ ] Kiểm thử có dữ liệu đáng tin, độc lập và **không làm lộ thông tin nhạy cảm**.
- [ ] Test xanh được hiểu đúng phạm vi chứng minh; có kiểm chứng tích hợp ở ranh giới cần thiết.
- [ ] Khi quy tắc thay đổi, **đặc tả và kiểm thử** được cập nhật có lý do.
- [ ] Nhóm không xóa assertion để che lỗi hoặc giữ vô hạn ví dụ đã lỗi thời.
- [ ] Kết quả được đánh giá bằng **hiểu biết chung, thời gian phản hồi, chất lượng và outcome**, không bằng số kịch bản.

## 22. Câu hỏi tự kiểm tra

1. BDD giải quyết vấn đề nào trước khi Developer bắt đầu viết mã?
2. Vì sao BDD không đồng nghĩa với việc sử dụng Cucumber hay Gherkin?
3. Ba hoạt động discovery, formulation và automation liên hệ thế nào?
4. Three Amigos là ba chức danh bắt buộc hay ba góc nhìn? Những góc nhìn đó là gì?
5. Example Mapping giúp phân biệt những loại thông tin nào?
6. Một user story có giá trị khác một ví dụ Given–When–Then ở điểm nào?
7. Given, When, Then nên mô tả gì và tránh phụ thuộc điều gì?
8. Khi nào Scenario Outline phù hợp và khi nào nên tách kịch bản?
9. Vì sao timeout không thể tự động được coi là chắc chắn lưu thất bại?
10. Những ví dụ nào cần kiểm tra khi có phản hồi cũ đến muộn hoặc thao tác lặp?
11. Unit test cho thông điệp CONFIRMED có chứng minh máy chủ thực sự lưu bền vững không? Vì sao?
12. BDD, TDD và ATDD khác nhau ở trọng tâm nào?
13. Acceptance criteria khác Definition of Done thế nào?
14. Vì sao một kịch bản BDD đi qua UI có thể dễ vỡ và chậm hơn kiểm thử domain/API?
15. Làm sao nhận biết một đặc tả đã lỗi thời, một kiểm thử bị hỏng và một lỗi sản phẩm?
16. BDD có thể hỗ trợ Product Backlog refinement, Sprint Planning và Sprint Review bằng cơ chế nào?
17. Khi nào một câu hỏi mở nên được tách thành hạng mục nghiên cứu hoặc spike?
18. Những tín hiệu nào có ích hơn số file Gherkin để đánh giá hiệu quả BDD?

**Ghi nhớ:** **BDD là hoạt động cộng tác để khám phá và thống nhất hành vi mong đợi bằng ví dụ nghiệp vụ**, không chỉ là một cú pháp hay bộ công cụ kiểm thử. Những người hiểu sản phẩm, phát triển và chất lượng cùng tìm **quy tắc, tình huống điển hình, ngoại lệ và điều chưa biết**; diễn đạt chúng thành ví dụ quan sát được; rồi tự động hóa những ví dụ phù hợp để nhận phản hồi sớm. Hãy dùng BDD để **làm rõ user story, giảm hiểu sai, tạo Increment đáng tin cậy và thích ứng từ kết quả thực**, không để biến nhu cầu người dùng thành hàng trăm kịch bản khó hiểu hoặc một báo cáo kiểm thử xanh nhưng sai ngữ nghĩa.
