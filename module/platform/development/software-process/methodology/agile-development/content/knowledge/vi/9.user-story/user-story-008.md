# Xây dựng tiêu chí chấp nhận cùng ví dụ cụ thể

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **tiêu chí chấp nhận** (*acceptance criteria*) đối với một **user story**, phân biệt với Definition of Done và các bước kiểm thử kỹ thuật.
2. Cộng tác với người phụ trách sản phẩm, lập trình viên, kiểm thử viên và người dùng để làm rõ quy tắc nghiệp vụ bằng **ví dụ cụ thể** trước và trong khi phát triển.
3. Viết tiêu chí chấp nhận rõ ràng, quan sát được và có thể xác minh; bao phủ luồng chính, trường hợp biên, lỗi quan trọng và ràng buộc an toàn.
4. Sử dụng bảng ví dụ, **Given–When–Then (Gherkin)** và **Example Mapping** ở mức phù hợp để chuyển hiểu biết chung thành kiểm thử.
5. Nhận diện tiêu chí mơ hồ, quá gắn vào cách triển khai hoặc quá rộng; điều chỉnh story và backlog để giao sản phẩm tăng dần, nhận phản hồi sớm.

## 1. Tại sao một câu user story chưa đủ?

Trong Agile, một **user story** diễn đạt một nhu cầu hoặc kết quả có ích từ góc nhìn người dùng. Một cách viết quen thuộc là:

> **Là** học viên, **tôi muốn** tiếp tục bài học đã dừng **để** không phải tìm lại tiến độ sau khi đăng nhập trên thiết bị khác.

Câu chuyện này nói được **ai**, **muốn điều gì** và **vì sao**. Nhưng các thành viên có thể hiểu khác nhau:

- “Tiếp tục” nghĩa là mở **khóa học**, **bài học** hay **đúng giây đã xem**?
- Điều gì xảy ra khi học viên chưa học bài nào?
- Nếu hai thiết bị cập nhật cùng lúc, hệ thống nên hiển thị tiến độ nào?
- Nếu người dùng hết quyền truy cập, có được mở nội dung cũ không?
- Làm thế nào biết hệ thống đáp ứng yêu cầu?

Nếu nhóm bắt đầu code khi chưa trả lời các câu hỏi ảnh hưởng trực tiếp đến kết quả, phần mềm có thể chạy đúng theo cách hiểu của lập trình viên nhưng sai kỳ vọng của Product Owner hoặc người dùng.

**Tiêu chí chấp nhận** diễn đạt các điều kiện phải đúng để một hạng mục được xem là đáp ứng nhu cầu đã thống nhất. **Ví dụ cụ thể** cho thấy các điều kiện đó hoạt động ra sao trong từng tình huống. Hai thứ kết hợp giúp mọi người cùng hiểu thế nào là hành vi đúng.

### Mô hình 3C của user story

Một cách nhìn hữu ích là **Card – Conversation – Confirmation**:

- **Card (thẻ):** tên hoặc mô tả ngắn về nhu cầu, nhắc nhóm cần trao đổi điều gì.
- **Conversation (đối thoại):** các bên cùng làm rõ ý định, quy tắc, ngoại lệ, rủi ro và phạm vi.
- **Confirmation (xác nhận):** các tiêu chí và ví dụ có thể kiểm tra để xác định story có đáp ứng điều đã thống nhất không.

Một user story không phải “hợp đồng một câu”. Giá trị của nó nằm ở việc **khởi tạo và duy trì cuộc đối thoại**, rồi tạo ra một cách xác nhận chung.

## 2. Tiêu chí chấp nhận là gì và không phải là gì?

Tiêu chí chấp nhận mô tả **hành vi hoặc kết quả quan sát được** mà một story cần đáp ứng. Chúng thuộc phạm vi từng hạng mục, nhằm xác định đúng/sai từ góc nhìn nghiệp vụ hoặc người dùng, đồng thời cung cấp cơ sở cho việc xây dựng và kiểm thử.

Ví dụ đối với story “Tiếp tục bài học đã dừng”:

1. Khi học viên có tiến độ hợp lệ, trang chủ hiển thị bài học gần nhất đã lưu.
2. Nhấn “Tiếp tục học” mở đúng bài học tương ứng.
3. Khi không có tiến độ, hệ thống không hiển thị bài học giả hoặc nút dẫn đến nội dung không tồn tại.
4. Một tài khoản không thể xem hoặc mở tiến độ riêng của tài khoản khác.
5. Khi lưu tiến độ thất bại, giao diện không thông báo “Đã lưu” như thể thao tác thành công.

Những tiêu chí này vừa đủ để cùng trao đổi, nhưng vẫn cần **ví dụ** và một số quyết định nghiệp vụ trước khi kiểm thử các ca phức tạp.

### Phân biệt ba lớp yêu cầu

| Thành phần | Trả lời câu hỏi | Phạm vi | Ví dụ |
| --- | --- | --- | --- |
| **User story** | Ai cần gì, vì sao? | Một lát cắt giá trị | “Là học viên, tôi muốn tiếp tục bài đã dừng để học liền mạch.” |
| **Acceptance criteria** | Những điều kiện riêng của story phải đúng là gì? | Hành vi và ngoại lệ của story | “Không hiện tiến độ của tài khoản khác.” |
| **Definition of Done (DoD)** | Tiêu chuẩn chất lượng chung để một increment được xem là hoàn thành? | Các hạng mục/increment theo quy ước của Scrum Team, sản phẩm hoặc tổ chức | “Thay đổi đã được review, qua các kiểm thử bắt buộc, tích hợp và đáp ứng yêu cầu bảo mật áp dụng.” |

Trong **Scrum**, Definition of Done là một cam kết của artefact Increment. Một Product Backlog Item chưa đáp ứng DoD không được tính là một phần của Increment đã hoàn thành. Các tiêu chí chấp nhận giúp xác nhận nội dung riêng của story nhưng **không thay thế DoD**.

Ngoài ra, **test case** là một cách kiểm tra một hay nhiều tiêu chí. Test case có thể mô tả dữ liệu, các bước thực hiện và kết quả mong đợi; tiêu chí chấp nhận không nhất thiết phải liệt kê từng cú nhấp hoặc từng câu lệnh kỹ thuật.

### Tiêu chí tốt thường có những đặc điểm nào?

| Đặc điểm | Câu hỏi tự kiểm tra |
| --- | --- |
| **Rõ nghĩa** | Người sản phẩm, dev và tester có hiểu giống nhau không? Thuật ngữ nào cần định nghĩa? |
| **Quan sát/kiểm chứng được** | Có đầu vào, sự kiện và kết quả nào giúp xác định đạt hay chưa đạt? |
| **Gắn với giá trị và phạm vi** | Tiêu chí có phản ánh điều story hứa với người dùng không? |
| **Bao gồm rủi ro đáng kể** | Có bỏ sót phân quyền, dữ liệu sai, lỗi mạng hay trường hợp biên ảnh hưởng kết quả chính không? |
| **Không áp đặt kỹ thuật khi không cần** | Tiêu chí mô tả hành vi thay vì bắt buộc dùng một class, framework hay bảng dữ liệu cụ thể? |
| **Có thể cập nhật khi học được điều mới** | Khi giả định sai, nhóm có thể bàn lại phạm vi và cập nhật tiêu chí minh bạch không? |

Không có quy tắc “mỗi story đúng ba tiêu chí” hoặc “tiêu chí càng nhiều càng tốt”. Số lượng hợp lý phụ thuộc **độ phức tạp, rủi ro và phạm vi story**.

## 3. Viết tiêu chí chấp nhận từ một cuộc trao đổi chung

Một buổi làm rõ hiệu quả thường có ít nhất ba góc nhìn:

- **Sản phẩm/nghiệp vụ:** Người dùng cần đạt kết quả gì, quy tắc nào có giá trị hoặc bắt buộc?
- **Phát triển:** Cách thực hiện khả thi thế nào, dữ liệu và hệ thống hiện tại có giới hạn gì?
- **Kiểm thử/chất lượng:** Làm sao chứng minh hành vi đúng, ngoại lệ nào dễ bị bỏ sót?

Hình thức **Three Amigos** thường dùng ba góc nhìn này trong một cuộc trao đổi ngắn. Đây là **thực hành cộng tác**, không phải một sự kiện bắt buộc của Scrum; thành phần thực tế có thể có thêm UX, vận hành, bảo mật hoặc đại diện khách hàng khi cần.

### Quy trình đề xuất

1. **Nêu mục tiêu người dùng:** “Học viên chuyển thiết bị mà không mất công tìm lại bài.”
2. **Khoanh lát cắt:** Phiên bản này chỉ cần mở đúng **bài gần nhất**, chưa hứa đồng bộ vị trí video từng giây.
3. **Tìm quy tắc chính:** Tài khoản nào được xem tiến độ? Thông tin nào xác định “bài gần nhất”?
4. **Đưa ra ví dụ:** Một trường hợp thông thường, một trường hợp không có dữ liệu, một ngoại lệ quan trọng.
5. **Đặt câu hỏi chưa rõ:** Hai thiết bị cùng cập nhật thì thứ tự nào được ưu tiên?
6. **Viết tiêu chí quan sát được:** Mỗi tiêu chí gắn với cách xác minh hoặc bằng chứng cụ thể.
7. **Ghi quyết định và câu hỏi mở:** Ai xác nhận, khi nào cần trả lời, điều gì bị chặn?

Đừng cố ép nhóm thống nhất ngay mọi kịch bản tương lai. Những câu hỏi **chặn tính đúng đắn hoặc an toàn của lát cắt đang làm** phải được giải quyết; những ý tưởng ngoài phạm vi có thể đưa vào Product Backlog để xem xét sau.

### Ví dụ đối thoại

> **Product Owner:** “Người học cần thấy bài đang học gần nhất.”
>
> **Developer:** “Nếu khóa học bị thu hồi quyền truy cập thì sao?”
>
> **Tester:** “Hãy lấy ví dụ tài khoản A từng học khóa X nhưng hiện không còn quyền. Bản mới có hiện nút dẫn vào X không?”
>
> **Product Owner:** “Không. Chỉ hiển thị bài còn quyền truy cập; nếu không có bài phù hợp thì hiển thị gợi ý chọn khóa.”
>
> **Cả nhóm:** Ghi quy tắc, ví dụ và tiêu chí kiểm tra quyền truy cập.

Sau vài câu hỏi, nhóm đã làm rõ một rủi ro quan trọng mà câu user story ban đầu không thể hiện.

## 4. Dùng ví dụ cụ thể để tìm ra quy tắc ẩn

Những từ như “gần nhất”, “hợp lệ”, “nhanh”, “thành công”, “đủ điều kiện” hoặc “đơn hàng trùng” thường che nhiều quy tắc nghiệp vụ. Hãy thay khái niệm chung bằng **dữ liệu cụ thể và kết quả dự kiến**.

### Từ phát biểu chung sang ví dụ

Giả sử yêu cầu là:

> “Hệ thống chọn bài học được cập nhật gần nhất của học viên.”

Ví dụ 1:

| Học viên | Bài học | Thời điểm máy chủ xác nhận tiến độ | Quyền truy cập hiện tại | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| A | Bài 2, khóa X | 09:15 | Có | Hiển thị nếu không có bản ghi hợp lệ mới hơn |
| A | Bài 4, khóa Y | 10:30 | Có | **Hiển thị bài 4, khóa Y** |

Ví dụ 2:

| Học viên | Bài học | Thời điểm máy chủ xác nhận tiến độ | Quyền truy cập hiện tại | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| A | Bài 2, khóa X | 09:15 | Có | **Hiển thị bài 2, khóa X** |
| A | Bài 4, khóa Y | 10:30 | Không | Không được đưa học viên đến nội dung khóa Y đã hết quyền |

Ví dụ 3 đặt ra câu hỏi chưa giải quyết:

| Dữ kiện | Câu hỏi cần quyết định |
| --- | --- |
| Máy tính và điện thoại cùng gửi cập nhật tiến độ, request từ máy tính đến sau | “Gần nhất” theo thời điểm nhận trên server, thứ tự phiên bản hay thời điểm hoạt động thực tế? |

Hai ví dụ đầu có thể xác nhận quy tắc **lọc theo quyền truy cập trước khi lựa chọn**, còn ví dụ thứ ba cho thấy vẫn có một câu hỏi về xử lý đồng thời. Việc chọn thời gian máy chủ ở đây là **giả định minh họa**, không phải quy tắc chuẩn cho mọi hệ thống.

### Ba lợi ích của ví dụ

- **Làm lộ ngôn ngữ mơ hồ:** “Mới nhất” phải có mốc và điều kiện xác định.
- **Tạo đối tượng thảo luận cụ thể:** Các bên có thể nói “trong trường hợp A có hai bản ghi thì…” thay vì tranh luận trừu tượng.
- **Cung cấp nguyên liệu kiểm thử:** Khi quy tắc được thống nhất, cùng bộ ví dụ có thể dùng cho test ở cấp phù hợp.

Ví dụ tốt còn giúp phát hiện story đang quá lớn. Nếu mỗi ví dụ làm lộ một quy tắc độc lập và cần nhiều hệ thống khác nhau, nhóm có thể chia thành các lát cắt có giá trị.

## 5. Kỹ thuật Example Mapping: Quy tắc – Ví dụ – Câu hỏi

**Example Mapping** là một cách tổ chức cuộc trao đổi để mọi người thấy những gì đã hiểu và chưa hiểu. Một cách dùng phổ biến:

| Loại thẻ | Nội dung | Ví dụ |
| --- | --- | --- |
| **Story** | Mục tiêu, giá trị cần tạo | Học viên mở lại bài gần nhất trên thiết bị khác |
| **Rule – Quy tắc** | Hành vi/điều kiện phải đúng | Chỉ xem được tiến độ của chính tài khoản và khóa còn quyền |
| **Example – Ví dụ** | Trường hợp cụ thể chứng minh hoặc làm rõ rule | A có tiến độ X và Y; Y hết quyền; hệ thống chọn X |
| **Question – Câu hỏi** | Điểm mơ hồ cần quyết định hoặc tìm hiểu | Xung đột hai cập nhật gần nhau giải quyết theo thứ tự nào? |

### Minh họa nhóm thông tin

~~~text
STORY: Học viên tiếp tục bài gần nhất
|
+-- RULE: Chỉ xem tiến độ thuộc tài khoản đang đăng nhập
|   +-- EXAMPLE: A đăng nhập thấy bài 4 của A, không thấy dữ liệu B
|   +-- EXAMPLE: B dùng cùng thiết bị sau khi A đăng xuất, không thấy tiến độ A
|
+-- RULE: Không mở khóa học đã mất quyền truy cập
|   +-- EXAMPLE: Bài mới nhất thuộc khóa hết quyền -> chọn bài hợp lệ trước đó
|   +-- QUESTION: Nếu không còn bài nào hợp lệ, nên hiển thị gì?
|
+-- RULE: Đưa học viên tới bài đã lưu gần nhất
    +-- EXAMPLE: Bài X lúc 09:15, bài Y lúc 10:30 -> chọn Y
    +-- QUESTION: Hai thiết bị cập nhật gần cùng lúc thì chọn bản nào?
~~~

**Cách tổ chức một phiên Example Mapping ngắn:**

1. Chỉ chọn **một story** đang gần thời điểm thực hiện.
2. Ghi các quy tắc đã chắc, sau đó đưa ra ví dụ minh họa từng quy tắc.
3. Đặt câu hỏi mở riêng để tránh ngầm coi giả định là quyết định đã được chốt.
4. Nếu có quá nhiều quy tắc, thử chia story; nếu quá nhiều câu hỏi rủi ro cao, cần trao đổi với đúng người hoặc một hoạt động khám phá.
5. Kết thúc bằng các quyết định, người cần trả lời câu hỏi và thời điểm xem lại.

Example Mapping **không bắt buộc** dùng công cụ hay màu giấy cụ thể. Mục tiêu là chia sẻ hiểu biết nhanh và nhìn thấy lỗ hổng trong phạm vi cần giao.

## 6. Viết tiêu chí bằng Given–When–Then

Một cách diễn đạt ví dụ có cấu trúc là:

- **Given (Cho trước):** Bối cảnh và dữ liệu cần thiết.
- **When (Khi):** Hành động hoặc sự kiện kích hoạt.
- **Then (Thì):** Kết quả có thể quan sát và xác minh.

Định dạng này thường được viết bằng **Gherkin** trong các nhóm thực hành Behavior-Driven Development (BDD). Nó giúp người sản phẩm, dev và tester cùng đọc được; **không phải mọi tiêu chí chấp nhận đều phải viết thành Gherkin** và cũng không phải tất cả ví dụ cần tự động hóa.

### Mẫu một kịch bản cơ bản

~~~gherkin
Feature: Tiếp tục bài học gần nhất

  Scenario: Học viên mở bài đã lưu trên thiết bị khác
    Given học viên A đã đăng nhập và có quyền truy cập khóa X
    And tiến độ gần nhất hợp lệ của A là bài 4 thuộc khóa X
    When A chọn "Tiếp tục học" trên trang chủ
    Then hệ thống mở bài 4 thuộc khóa X
    And không hiển thị dữ liệu tiến độ của người dùng khác
~~~

Một kịch bản khác:

~~~gherkin
Scenario: Không có bài đã lưu hợp lệ
  Given học viên A chưa có tiến độ học hợp lệ
  When A mở trang chủ
  Then hệ thống không hiển thị nút "Tiếp tục học" gắn với bài không tồn tại
  And A có thể chọn một khóa học để bắt đầu
~~~

Một kịch bản về lỗi:

~~~gherkin
Scenario: Không báo đã lưu khi thao tác ghi tiến độ thất bại
  Given học viên A đang học bài 3 của khóa X
  And dịch vụ lưu tiến độ đang không thể xác nhận yêu cầu ghi
  When A yêu cầu lưu vị trí đang học
  Then hệ thống không thông báo "Đã lưu thành công"
  And hệ thống cho A biết trạng thái lưu chưa thành công
~~~

Trong thực tế, cần thống nhất ứng dụng cho phép **lưu lại/đợi đồng bộ/thử lại** thế nào trước khi triển khai. Đây là ví dụ về hành vi cần rõ, chưa phải mô tả trọn vẹn giải pháp khôi phục.

### Chọn mức chi tiết cho Gherkin

**Nên diễn đạt ở mức nghiệp vụ:**

~~~gherkin
Given học viên A đã hết quyền truy cập khóa X
When A chọn "Tiếp tục học" với tiến độ thuộc khóa X
Then A không được xem nội dung bài học của khóa X
~~~

**Tránh áp đặt chi tiết giao diện không liên quan:**

~~~text
Given ứng dụng đã mount React component ProgressCard
When người dùng click CSS selector "#resume-btn"
Then hàm fetch("/api/v3/last-progress") được gọi đúng một lần
~~~

Kịch bản thứ hai mô tả cách triển khai có thể thay đổi mà không làm đổi giá trị người dùng. Chi tiết selector, endpoint hoặc số request có thể thuộc test kỹ thuật, nhưng thường **không phải** cách diễn đạt tốt cho tiêu chí chấp nhận ở cấp nghiệp vụ.

## 7. Bao phủ luồng chính, ca biên và các tình huống lỗi

Chỉ viết một kịch bản “đường hạnh phúc” (*happy path*) là chưa đủ cho nhiều story. Hãy tìm những trường hợp có khả năng khiến người dùng nhận kết quả sai hoặc chịu rủi ro.

### Ma trận câu hỏi tìm ví dụ

| Nhóm ví dụ | Câu hỏi | Trường hợp với “Tiếp tục học” |
| --- | --- | --- |
| **Luồng chính** | Khi mọi điều kiện hợp lệ, điều gì phải xảy ra? | Học viên có một bài gần nhất còn quyền -> mở đúng bài. |
| **Không có dữ liệu** | Nếu dữ liệu trống hoặc thiếu thì sao? | Người mới chưa học -> không hiển thị bài giả. |
| **Ca biên** | Điều gì xảy ra tại giới hạn hoặc khi bằng nhau? | Hai cập nhật có cùng thời điểm; tiến độ vừa bị xóa. |
| **Lỗi/gián đoạn** | Khi mạng hoặc dịch vụ không xác nhận được kết quả thì sao? | Mất mạng lúc ghi tiến độ -> không báo thành công giả. |
| **Phân quyền** | Người dùng có thể thấy hoặc sửa dữ liệu không thuộc mình? | B đăng nhập trên thiết bị cũ của A -> không thấy tiến độ A. |
| **Dữ liệu không nhất quán** | Nếu trạng thái đã thay đổi giữa hai thao tác thì sao? | Khóa bị thu hồi quyền sau khi trang chủ đã tải. |
| **Đồng thời/lặp yêu cầu** | Hai thiết bị hoặc request gửi lặp có tạo kết quả sai? | Hai cập nhật cùng lúc; request lưu được gửi lại. |
| **Khả năng truy cập/thiết bị** | Người dùng có thao tác được trên thiết bị mục tiêu? | Nút vẫn đọc/điều hướng được bằng bàn phím hoặc công cụ hỗ trợ phù hợp. |
| **Hiệu năng/khả năng vận hành** | Khi nhiều người sử dụng, hành vi có đáp ứng mức dịch vụ? | Mở bài không chậm vượt ngưỡng chất lượng đã thống nhất. |

Không cần viết toàn bộ ma trận cho mọi story. Chọn ví dụ theo **mức tác động, rủi ro và phạm vi**; trường hợp liên quan tiền, dữ liệu cá nhân, phân quyền hoặc an toàn thường cần kiểm tra sớm hơn.

### Các giá trị biên phải có quy tắc rõ

Xét tiêu chí: “Chỉ mở bài kiểm tra khi học viên đạt từ 80 điểm trở lên.” Ví dụ:

| Điểm | Kết quả mong đợi |
| ---: | --- |
| 79 | Không mở bài kiểm tra tiếp theo |
| 80 | Cho phép mở |
| 81 | Cho phép mở |
| Không có điểm | Chưa đủ điều kiện; thông báo phù hợp |

Các ví dụ **79–80–81** giúp xác định ranh giới. Nhưng nhóm còn phải hỏi: điểm có thể là số thập phân không, thang điểm từ bao nhiêu đến bao nhiêu, điểm được xác nhận lúc nào, ai có quyền sửa điểm? Nếu không làm rõ dữ liệu đầu vào, một tiêu chí tưởng chừng đơn giản vẫn có thể sai.

## 8. Phân biệt quy tắc nghiệp vụ với chi tiết kỹ thuật

Tiêu chí chấp nhận nên nói **người dùng/đối tượng nghiệp vụ quan sát được gì**. Đội kỹ thuật vẫn phải có thiết kế, test và quyết định triển khai ở cấp phù hợp.

| Cách viết mơ hồ hoặc áp đặt | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Tải nhanh.” | Không có thao tác, điều kiện và ngưỡng đo rõ. | “Trên cấu hình thử nghiệm và điều kiện tải đã thống nhất, thời gian mở trang bài học đáp ứng mục tiêu hiệu năng của sản phẩm.” |
| “Hệ thống phải đẹp và thân thiện.” | Khó xác nhận đạt/chưa đạt. | “Người học tìm và mở lại bài gần nhất theo luồng được kiểm tra trên thiết bị mục tiêu.” |
| “Dùng Redis để lưu tiến độ.” | Ép giải pháp kỹ thuật; chưa thể hiện giá trị. | “Khi yêu cầu lưu được xác nhận, tiến độ của A có thể được đọc lại đúng sau khi A đăng nhập trên thiết bị khác.” |
| “API trả HTTP 200.” | 200 vẫn có thể chứa dữ liệu sai. | “Khi đủ quyền truy cập, học viên mở được đúng bài đã lưu; khi không đủ quyền, không nhận nội dung riêng tư.” |
| “Không có lỗi nào.” | Không thể chứng minh một cách tuyệt đối. | Chỉ rõ luồng, mức nghiêm trọng lỗi và tiêu chuẩn chất lượng cần đạt trước khi hoàn thành. |
| “Càng nhiều càng tốt.” | Thiếu giới hạn, không thể kiểm tra. | Chọn mục tiêu, đo lường và điều kiện ngừng hoặc xử lý ngoại lệ phù hợp. |

Không nên đưa ra ngưỡng như “99,99%” hoặc “dưới 100 ms” chỉ vì thấy cụ thể. Các ngưỡng phải dựa trên **nhu cầu, tải, thiết bị, dữ liệu nền và nghĩa vụ sản phẩm**.

### Quy tắc chung và tiêu chí riêng

Ví dụ, “mọi thao tác phải kiểm tra quyền truy cập” có thể là **tiêu chuẩn bảo mật áp dụng toàn sản phẩm**. Với story xem tiến độ, cần bổ sung ví dụ riêng về **đối tượng dữ liệu nào A được xem và B không được xem**. Điều này làm rõ hành vi của story mà không lặp toàn bộ tiêu chuẩn bảo mật vào mọi ticket.

## 9. Một bộ ví dụ đầy đủ: ghi danh khóa học miễn phí

Để thấy sự khác biệt giữa câu chuyện, quy tắc và ví dụ, hãy xét một user story khác.

> **Là** học viên đã đăng nhập, **tôi muốn** ghi danh vào khóa học miễn phí còn nhận học viên **để** bắt đầu học mà không cần thao tác thanh toán.

### Bước 1 — Thống nhất các quy tắc

Giả sử đội và Product Owner đã xác nhận:

1. Chỉ người đã đăng nhập mới ghi danh được.
2. Khóa học phải ở trạng thái đang nhận ghi danh và có giá bằng 0 theo thông tin đã được xác nhận.
3. Mỗi học viên chỉ có **một ghi danh đang hiệu lực** cho cùng khóa học; gửi lại yêu cầu không tạo bản ghi trùng.
4. Nếu khóa bị đóng nhận học viên, việc ghi danh mới phải bị từ chối với thông báo phù hợp.
5. Khi thành công, khóa xuất hiện trong danh sách học của chính người ghi danh.

Đây là các **quy tắc giả định cho ví dụ học tập**. Sản phẩm thật có thể có điều kiện tiên quyết, giới hạn số chỗ, thời hạn, quyền truy cập hoặc các quy tắc khác cần được xác nhận.

### Bước 2 — Viết bảng ví dụ

| Đã đăng nhập? | Khóa còn nhận? | Giá | Đã ghi danh? | Kết quả mong đợi |
| --- | --- | ---: | --- | --- |
| Có | Có | 0 | Chưa | Ghi danh thành công, khóa xuất hiện trong danh sách học |
| Không | Có | 0 | Chưa | Yêu cầu đăng nhập, chưa tạo ghi danh |
| Có | Không | 0 | Chưa | Không tạo ghi danh, thông báo khóa không còn nhận |
| Có | Có | Lớn hơn 0 | Chưa | Không dùng luồng ghi danh miễn phí |
| Có | Có | 0 | Rồi | Không tạo bản ghi trùng, thông báo trạng thái ghi danh hiện có |

### Bước 3 — Viết kịch bản Gherkin

~~~gherkin
Feature: Ghi danh khóa học miễn phí

  Scenario: Học viên hợp lệ ghi danh thành công
    Given học viên A đã đăng nhập
    And khóa X đang nhận học viên và có giá bằng 0
    And A chưa ghi danh vào X
    When A chọn "Ghi danh" cho khóa X
    Then hệ thống ghi nhận đúng một ghi danh có hiệu lực của A vào X
    And khóa X xuất hiện trong danh sách học của A

  Scenario: Yêu cầu ghi danh được gửi lại
    Given học viên A đã đăng nhập
    And khóa X đang nhận học viên và có giá bằng 0
    And A đã có một ghi danh có hiệu lực vào X
    When yêu cầu ghi danh vào X được gửi lại
    Then hệ thống không tạo thêm ghi danh có hiệu lực trùng cho A và X
    And A nhận thông tin nhất quán về trạng thái ghi danh

  Scenario: Khóa đã dừng nhận học viên
    Given học viên A đã đăng nhập
    And khóa X không còn nhận ghi danh mới
    When A chọn "Ghi danh" cho khóa X
    Then hệ thống không tạo ghi danh mới cho A vào X
    And A nhận thông báo khóa hiện không còn nhận ghi danh
~~~

### Bước 4 — Tìm điểm còn mở trước khi code

- Khóa có giới hạn chỗ không? Nếu hai người cùng ghi danh chỗ cuối thì xử lý thế nào?
- Ai có quyền thay đổi trạng thái đang nhận ghi danh?
- Khi giá chuyển từ 0 sang có phí đúng lúc người dùng thao tác, quy tắc kiểm tra giá ở đâu?
- “Đã ghi danh” nghĩa là bản ghi đang hiệu lực, đã hủy hay từng ghi danh?
- Nếu ghi dữ liệu thành công nhưng phản hồi mạng thất bại, hệ thống hiển thị và xử lý lần thử lại thế nào?

Những câu hỏi ảnh hưởng tính đúng đắn phải được trả lời trước khi giao lát cắt liên quan. Câu hỏi ngoài phạm vi (ví dụ hỗ trợ mã giảm giá) có thể trở thành story tiếp theo.

### Bước 5 — Kiểm tra độ phù hợp của scope

Story này có thể đủ nhỏ nếu hệ thống đã có đăng nhập, danh sách học và mô hình ghi danh. Nếu cần đồng thời xây hệ thống thanh toán, quản lý quyền phức tạp và cổng duyệt, có thể cần tách lát cắt hoặc tìm hiểu phụ thuộc trước.

## 10. Từ ví dụ sang kiểm thử chấp nhận

**Acceptance test** là phép kiểm tra xác nhận hệ thống đáp ứng một hay nhiều tiêu chí chấp nhận. Các ví dụ đã được thống nhất có thể trở thành:

- **Kiểm thử thủ công:** Tester hoặc người đại diện sản phẩm chạy tình huống và xác nhận kết quả.
- **Kiểm thử tự động ở cấp phù hợp:** API, service, integration hoặc UI, tùy rủi ro và mức phản hồi mong muốn.
- **Kiểm thử khám phá:** Tìm các trường hợp chưa nghĩ đến từ hành vi thực tế.
- **Kiểm chứng giá trị với người dùng:** Xem chức năng có giúp người dùng giải quyết nhu cầu hay không, vượt ra ngoài việc code đúng quy tắc.

### Chọn cấp kiểm thử

Ví dụ với ghi danh:

| Điều cần xác nhận | Cách kiểm thử khả thi | Lý do |
| --- | --- | --- |
| Không tạo bản ghi trùng khi request gửi lại | Integration/API test với dữ liệu và tình huống gửi lại | Cần kiểm tra hành vi nghiệp vụ và tính nhất quán dữ liệu. |
| Người dùng không đăng nhập không thể ghi danh | API test phân quyền kết hợp kiểm tra UI thích hợp | Không chỉ dựa vào việc ẩn nút trên giao diện. |
| Khóa xuất hiện trong danh sách học sau ghi danh | Integration test hoặc E2E cho luồng chính | Xác minh kết quả xuyên qua các thành phần. |
| Nút và thông báo dễ hiểu trên điện thoại | Kiểm thử sử dụng hoặc khả năng truy cập phù hợp | Khó chứng minh đầy đủ chỉ qua test API. |

Không phải mọi ví dụ Gherkin đều cần được chuyển một-một thành **UI E2E test**. Test quá nhiều ở lớp giao diện có thể chậm và khó bảo trì. Chọn cấp test cung cấp bằng chứng đáng tin cậy với chi phí phù hợp.

### Phân biệt “đạt kiểm thử” với “có giá trị”

Một story có thể vượt toàn bộ test chấp nhận nhưng người dùng không dùng đến. Lý do: tiêu chí xác nhận đúng **giải pháp đã chọn**, chưa chắc xác nhận đúng **giả thuyết sản phẩm**. Do đó Agile còn cần Sprint Review, phản hồi người dùng, đo outcome và thích nghi Product Backlog.

## 11. Khi tiêu chí xuất hiện quá nhiều: kiểm tra lại kích thước story

Một story có 30–40 quy tắc, nhiều hệ thống và nhiều tuần triển khai có thể đang gom quá nhiều kết quả khác nhau. Đừng giải quyết bằng cách tiếp tục bổ sung tài liệu vô hạn; hãy hỏi có thể **chia theo giá trị** không.

Ví dụ yêu cầu tổng:

> “Học viên tiếp tục học trên mọi thiết bị, cả khi mất mạng, đồng bộ từng giây và không bao giờ mất dữ liệu.”

Có thể tìm các lát cắt:

1. Hiển thị bài học gần nhất đã lưu trên thiết bị mới khi có mạng.
2. Mở đúng bài và vị trí phát đã thống nhất trong điều kiện mạng ổn định.
3. Thông báo rõ trạng thái lưu tiến độ khi mạng gián đoạn.
4. Xử lý xung đột đồng bộ giữa hai thiết bị.
5. Hỗ trợ một loại nội dung ngoại tuyến có quyền truy cập hợp lệ, đồng bộ khi có mạng.

Mỗi lát cắt cần có **tiêu chí chấp nhận riêng**, liên hệ rõ giá trị người dùng và đáp ứng các điều kiện chất lượng bắt buộc khi được giao. Chia nhỏ không cho phép “để sau” những yêu cầu như phân quyền hoặc không làm hỏng dữ liệu trong phần đã phát hành.

### Kiểm tra trước khi tách

- Người dùng có thể nhận và thử một hành vi có ích sau lát cắt này không?
- Có thể xác minh hành vi trên luồng tích hợp phù hợp không?
- Có đang tách thành “chỉ database”, “chỉ backend”, “chỉ frontend” khiến không có luồng nào dùng được?
- Những câu hỏi còn mở có chặn **lát cắt hiện tại** hay thuộc lát cắt sau?

Một **technical spike** có thể cần thiết để trả lời rủi ro kỹ thuật; spike tạo kiến thức chứ không nhất thiết là increment có giá trị trực tiếp cho người dùng.

## 12. Làm rõ và thay đổi tiêu chí trong Scrum, Kanban, XP

### Scrum: refinement và Sprint

Trong Scrum, **Product Backlog refinement** là hoạt động liên tục để làm rõ và chia nhỏ Product Backlog Item. Nó không phải một sự kiện Scrum bắt buộc riêng với timebox cố định. Product Owner chịu trách nhiệm với Product Backlog; Developers tham gia làm rõ cách thực hiện và những vấn đề kỹ thuật cần biết.

Một hạng mục được chọn trong Sprint Planning cần đủ hiểu biết để xây kế hoạch ban đầu hướng tới **Sprint Goal**. Sau khi bắt đầu, Developers vẫn có thể làm rõ chi tiết và thương lượng phạm vi với Product Owner khi có thêm thông tin, miễn không làm nguy hiểm Sprint Goal. Yêu cầu mới hoặc câu hỏi lớn có thể dẫn đến điều chỉnh Product Backlog cho các Sprint tiếp theo.

**Definition of Ready** đôi khi được nhóm tự thỏa thuận để nhận diện thông tin cần có trước khi bắt đầu; nó **không phải artefact hoặc cam kết bắt buộc của Scrum Guide**. Không dùng checklist “sẵn sàng” để ép viết mọi chi tiết quá sớm hoặc ngăn hoạt động học hỏi có kiểm soát.

### Kanban: điều kiện kéo việc và dòng chảy

Với Kanban, nhóm có thể quy định **chính sách rõ ràng** cho việc chuyển một item từ “Ý tưởng” sang “Sẵn sàng”, chẳng hạn đã có mục tiêu, tác động, ví dụ tối thiểu và người có thể trả lời câu hỏi nghiệp vụ. Khi thiếu thông tin, bảng cần thể hiện việc bị chặn, nguyên nhân và thời gian chờ.

**Giới hạn WIP** giúp nhóm tránh bắt đầu quá nhiều ticket chưa rõ rồi chuyển qua chuyển lại. Đối với sự cố khẩn, chính sách ngoại lệ có thể cho phép hành động ngay để khôi phục dịch vụ; không chờ điền đủ biểu mẫu.

### XP: kiểm thử và phản hồi sớm

Thực hành **Extreme Programming** như TDD, kiểm thử tự động, tích hợp liên tục, lập trình cặp và refactor giúp đội kiểm tra hành vi thường xuyên và thay đổi code an toàn hơn. Trong các đội thực hành BDD hoặc Acceptance Test-Driven Development (ATDD), những ví dụ chấp nhận có thể được thống nhất trước khi triển khai và chuyển thành test tự động thích hợp.

**Lưu ý:** TDD, BDD, ATDD không phải những thuật ngữ hoàn toàn đồng nghĩa. TDD thường tổ chức vòng viết test kỹ thuật–code–refactor; BDD nhấn mạnh hợp tác về hành vi và ví dụ; ATDD nhấn mạnh tiêu chí chấp nhận được kiểm thử để hướng dẫn phát triển. Mọi cách làm đều cần phản hồi nghiệp vụ, không chỉ test xanh.

## 13. Quản lý thay đổi tiêu chí sau khi bắt đầu

Ví dụ: Đội đang xây chức năng ghi danh miễn phí, nhưng phát hiện một khóa có thể bị đóng đúng lúc học viên nhấn nút.

Thay vì âm thầm đổi code, nhóm nên:

1. **Nêu thông tin mới:** Có nguy cơ người học ghi danh thành công sau thời điểm khóa dừng nhận.
2. **Đánh giá tác động:** Quy tắc mới ảnh hưởng tính đúng đắn, dữ liệu và trải nghiệm ở mức nào?
3. **Trao đổi với người có quyền quyết định:** Product Owner hoặc người phụ trách nghiệp vụ xác nhận hành vi mong đợi; kỹ thuật đề xuất giải pháp khả thi.
4. **Cập nhật tiêu chí và ví dụ:** Thêm kịch bản giao dịch đồng thời hoặc thay đổi trạng thái đúng lúc thao tác.
5. **Cập nhật test và kế hoạch:** Thống nhất phần nào cần thay đổi trong Sprint, phụ thuộc và dự báo.
6. **Kiểm chứng kết quả:** Xem increment và phản hồi; điều chỉnh tiếp nếu giả thuyết còn sai.

Nếu thay đổi mới mở rộng phạm vi thành một năng lực riêng và không cần cho giá trị hiện tại, có thể đưa vào Product Backlog sau. Nếu nó liên quan **tính đúng đắn, bảo mật hoặc nghĩa vụ bắt buộc**, không được bỏ qua chỉ để giữ cam kết số ticket.

### Ví dụ ghi nhận thay đổi ngắn

~~~text
Story: Ghi danh vào khóa học miễn phí
Thông tin mới: Trạng thái "đang nhận" có thể đổi khi request đang xử lý.
Rủi ro: Tạo ghi danh sau khi khóa đóng.
Quy tắc được xác nhận: Chỉ tạo ghi danh khi điều kiện còn hợp lệ tại điểm xử lý có thẩm quyền.
Ví dụ bổ sung: Khóa đổi sang "đóng" trước điểm xử lý -> từ chối ghi danh mới.
Người xác nhận: Product Owner cùng người phụ trách nghiệp vụ.
Kiểm chứng: Integration test tình huống cập nhật trạng thái gần đồng thời.
~~~

Đây là bản ghi minh họa. “Điểm xử lý có thẩm quyền” cần được thiết kế cụ thể bởi đội kỹ thuật; tiêu chí chấp nhận mô tả kết quả nghiệp vụ thay vì ấn định công nghệ lưu trữ.

## 14. Những lỗi phổ biến khi viết tiêu chí chấp nhận

| Sai lầm | Ví dụ | Cách sửa |
| --- | --- | --- |
| **Mơ hồ** | “Hệ thống dễ dùng và tải nhanh.” | Gọi tên tác vụ, người dùng, bối cảnh và cách đo phù hợp. |
| **Chỉ có happy path** | “Bấm ghi danh thì thành công.” | Thêm trường hợp chưa đăng nhập, khóa đóng, ghi danh trùng, lỗi quan trọng. |
| **Không có quyết định nghiệp vụ** | “Khi hai thiết bị cùng ghi thì xử lý hợp lý.” | Đưa ra ví dụ xung đột; người có quyền quyết định thống nhất quy tắc. |
| **Mô tả cách code thay vì hành vi** | “Phải gọi Redis cache và API X.” | Nêu điều cần đúng; đưa thiết kế API/cache vào tài liệu kỹ thuật khi cần. |
| **Lặp DoD vào mọi story** | “Code được review, CI xanh, không còn lỗi nghiêm trọng…” | Đặt tiêu chuẩn chung trong DoD và ràng buộc sản phẩm; giữ tiêu chí story cho hành vi riêng. |
| **Quá nhiều tiêu chí không liên quan** | Một story bao cả ghi danh, thanh toán, chứng chỉ, chat | Chia thành lát cắt giá trị phù hợp và ưu tiên backlog. |
| **Không cập nhật sau khi học được điều mới** | Tester phát hiện ngoại lệ nhưng chỉ sửa code, không cập nhật ví dụ | Ghi lại quy tắc mới, cập nhật tiêu chí và test. |
| **Chỉ viết kịch bản mà không trao đổi** | Gherkin dài nhưng Product Owner chưa xác nhận quy tắc | Tổ chức Conversation/Three Amigos, nhận xác nhận và lưu quyết định. |
| **Coi tất cả Gherkin là UI E2E bắt buộc** | Chạy hàng trăm test UI mong manh cho logic dữ liệu đơn giản | Chọn cấp test phù hợp; giữ ví dụ nghiệp vụ dễ đọc. |
| **Định lượng giả tạo** | “Mọi trang dưới 100 ms” không có dữ liệu nền | Thống nhất ngữ cảnh, phép đo, nghĩa vụ và rủi ro trước khi chọn ngưỡng. |
| **Coi test xanh là đủ giá trị** | Mọi tiêu chí đạt nhưng không ai sử dụng tính năng | Lấy phản hồi người dùng và theo dõi outcome sau giao increment. |

## 15. Checklist trước khi nhận một story vào thực hiện

Checklist dưới đây là công cụ tự rà soát theo bối cảnh, không phải quy định bắt buộc về Definition of Ready:

- [ ] Người dùng/vai trò, nhu cầu và kết quả mong muốn đã được hiểu?
- [ ] Story có phạm vi đủ nhỏ để kiểm chứng một lát cắt giá trị?
- [ ] Các **quy tắc nghiệp vụ chính** đã được ghi rõ và có người có quyền xác nhận?
- [ ] Có ít nhất một **ví dụ luồng chính** với đầu vào và kết quả dự kiến?
- [ ] Đã xem xét ca biên/ngoại lệ/rủi ro quan trọng theo bối cảnh?
- [ ] Các tiêu chí có **quan sát, xác minh được**, tránh từ ngữ mơ hồ?
- [ ] Có phân biệt tiêu chí riêng của story với **Definition of Done** và yêu cầu sản phẩm chung?
- [ ] Đã làm rõ ràng buộc phân quyền, quyền riêng tư, tính toàn vẹn dữ liệu, hiệu năng hoặc nghĩa vụ bắt buộc nếu liên quan?
- [ ] Câu hỏi mở được ghi lại, có người trả lời và thời điểm cần giải quyết?
- [ ] Nhóm đã thống nhất cách kiểm chứng phù hợp: test thủ công, tự động, tích hợp, khả dụng hoặc phản hồi từ người dùng?
- [ ] Các tiêu chí phản ánh **điều cần đạt** thay vì khóa cứng cách triển khai không cần thiết?
- [ ] Nếu có thông tin mới, ai quyết định cập nhật phạm vi và backlog đã rõ?

Không cần tất cả câu hỏi có cùng mức chi tiết cho mọi loại công việc. Với lỗi bảo mật nghiêm trọng hoặc giao dịch tài chính, một số điều kiện phải được làm rõ kỹ trước khi phát hành; với thay đổi nhỏ, cách diễn đạt ngắn có thể đã đủ.

## 16. Bài tập vận dụng

### Bài tập 1 — Tìm tiêu chí mơ hồ

Story: “Là học viên, tôi muốn hệ thống thông báo khi sắp hết thời gian làm bài để không nộp muộn.”

Tiêu chí hiện có:

1. Hệ thống thông báo kịp thời.
2. Thông báo phải đẹp.
3. Người dùng sẽ không quên nộp bài.

**Yêu cầu:** Viết lại ít nhất ba tiêu chí có thể kiểm chứng. Nêu các câu hỏi phải hỏi về mốc thời gian, múi giờ, thiết bị, quyền truy cập, mất mạng hoặc những tình huống có thể gây hiểu lầm.

**Gợi ý:** Nên hỏi “sắp hết” là bao nhiêu phút theo đồng hồ nào, khi trình duyệt ở nền thì xử lý thế nào, khi thời gian đã hết thì bài có tự nộp không. Không tự giả định toàn bộ câu trả lời.

### Bài tập 2 — Example Mapping cho phiếu giảm giá

Story: “Là học viên, tôi muốn nhập mã giảm giá khi mua khóa học.”

**Yêu cầu:** Viết ít nhất ba **Rule**, mỗi rule hai **Example**, và ba **Question** chưa biết. Tập trung vào: mã hết hạn, số lần dùng, quyền áp dụng, giá âm, gửi yêu cầu lặp và thay đổi trạng thái khi thanh toán.

**Gợi ý:** Câu hỏi “Mã hết hạn đúng lúc người dùng nhấn thanh toán thì điều gì xảy ra?” có thể làm thay đổi quy tắc; không tự chọn cách xử lý khi chưa xác nhận nghiệp vụ.

### Bài tập 3 — Viết Given–When–Then

Story: “Học viên ghi danh khóa miễn phí đang nhận học viên.”

**Yêu cầu:** Viết tối thiểu bốn scenario: thành công, chưa đăng nhập, ghi danh trùng, khóa đã đóng. Mỗi scenario nêu Given, When, Then ở mức nghiệp vụ, tránh mô tả chi tiết framework hoặc CSS selector.

**Gợi ý:** Kiểm tra xem scenario “ghi danh trùng” có thật sự khẳng định **không có thêm bản ghi có hiệu lực** hay chỉ xác nhận nút báo thành công.

### Bài tập 4 — Phân biệt tiêu chí chấp nhận và DoD

Cho các phát biểu:

A. “Học viên A không thể xem tiến độ của tài khoản B.”

B. “Code thay đổi đã được review theo tiêu chuẩn nhóm.”

C. “Khi tài khoản chưa có tiến độ, trang chủ không hiện bài học giả.”

D. “Kiểm thử hồi quy quan trọng của Increment đạt yêu cầu.”

**Yêu cầu:** Phân loại cái nào là tiêu chí riêng của story, cái nào thường thuộc DoD. Nếu một phát biểu có thể xuất hiện ở cả hai mức, giải thích ý nghĩa và cách tránh lặp hình thức.

**Gợi ý đáp án:** A và C là hành vi riêng của story; B và D thường là tiêu chuẩn chất lượng chung thuộc DoD. Một yêu cầu bảo mật chung có thể nằm ở DoD, còn A làm rõ tình huống quyền truy cập cụ thể cần kiểm chứng.

### Bài tập 5 — Chọn phạm vi đủ nhỏ

Yêu cầu tổng: “Người học xem offline mọi video, đồng bộ từng giây, hỗ trợ mọi thiết bị và không bao giờ mất dữ liệu.”

**Yêu cầu:** Chia thành ít nhất ba lát cắt có giá trị; với lát cắt đầu, viết một story, ba tiêu chí và hai ví dụ. Chỉ rõ điều kiện chất lượng không thể trì hoãn dù chọn phạm vi nhỏ.

**Gợi ý:** Có thể xác minh nhu cầu ngoại tuyến trước bằng một loại nội dung được phép, hoặc triển khai xem lại bài đã lưu khi có mạng. Phải kiểm soát quyền truy cập và dữ liệu của phần được giao.

### Bài tập 6 — Đóng vai Three Amigos

Trong 20 phút, chia vai:

1. **Product Owner** nêu nhu cầu “Tiếp tục học” và quyết định quy tắc nghiệp vụ.
2. **Developer** đặt câu hỏi về dữ liệu, đồng thời, phụ thuộc và tính khả thi.
3. **Tester** đưa ví dụ đối chứng, ca biên và phương án xác minh.

Sau buổi trao đổi, nộp: một story, 3–5 quy tắc, tối thiểu sáu ví dụ, tối đa ba câu hỏi còn mở **có người giải quyết** và đề xuất một lát cắt phù hợp cho Sprint tới. Đánh giá xem một thành viên không tham dự có thể hiểu đúng hành vi và cách xác nhận không.

## 17. Ghi nhớ

- **User story bắt đầu cuộc đối thoại; tiêu chí chấp nhận xác định điều phải đúng; ví dụ cụ thể giúp mọi người hiểu giống nhau.**
- Tiêu chí nên **rõ, có thể quan sát, liên quan giá trị và phù hợp phạm vi**; tránh ép chi tiết triển khai hoặc đặt ngưỡng không có căn cứ.
- Dùng **Three Amigos**, **Example Mapping** và **Given–When–Then** khi chúng giúp lộ quy tắc, ngoại lệ và câu hỏi mở. Không biến kỹ thuật diễn đạt thành thủ tục hình thức.
- Phân biệt **acceptance criteria**, **acceptance test** và **Definition of Done**. Một story được kiểm tra đúng hành vi vẫn phải đáp ứng các tiêu chuẩn chất lượng chung khi trở thành Increment.
- Chọn những ví dụ có ích: luồng chính, không có dữ liệu, ranh giới, lỗi, đồng thời, phân quyền và vận hành theo mức rủi ro.
- Làm rõ vừa đủ trước quyết định gần nhất, chia story thành lát cắt giá trị, giao tăng dần, nhận phản hồi sớm và cập nhật tiêu chí khi học được điều mới.
- Scrum hỗ trợ refinement và kiểm tra Increment; Kanban làm rõ chính sách và dòng công việc; các thực hành XP/BDD/ATDD giúp phản hồi kỹ thuật sớm và bảo vệ khả năng thay đổi.

Khi nhìn một user story, hãy hỏi: **“Nếu hai người hiểu khác nhau về chữ ‘thành công’, ví dụ cụ thể nào sẽ làm sự khác biệt đó hiện rõ — và chúng ta cần thống nhất điều gì trước khi giao phần mềm này?”**
