# Liên kết yêu cầu với tiêu chí chấp nhận và bằng chứng kiểm chứng

Một nhóm phát triển nhận user story: “Là học viên, tôi muốn lưu khóa học yêu thích để xem lại khi cần”. Nhà phát triển tạo nút hình trái tim và chuyển ticket sang **Done**. Người kiểm thử mở trang, bấm nút, thấy trái tim đổi màu và xác nhận “đạt”. Nhưng khi học viên đăng nhập lại, danh sách yêu thích trống; một người khác thậm chí nhìn thấy khóa học của tài khoản trước đó do dữ liệu bị lưu sai phạm vi.

Vấn đề không chỉ là thiếu một bài kiểm thử. Nhóm chưa nối rõ **nhu cầu của người dùng**, **hành vi phần mềm cần đáp ứng**, **điều kiện nào được xem là chấp nhận được** và **bằng chứng nào đủ để kết luận các điều kiện đó đã được thỏa mãn**.

Trong Agile, yêu cầu có thể được làm rõ và điều chỉnh qua phản hồi, nhưng không có nghĩa tiêu chuẩn hoàn thành được phép mơ hồ. Khi liên kết yêu cầu với tiêu chí chấp nhận và bằng chứng kiểm chứng, nhóm có thể giao những phần nhỏ của sản phẩm, kiểm tra sớm, trao đổi trên cùng một cách hiểu và điều chỉnh giải pháp có cơ sở.

Bài thuộc chương **Yêu cầu thích ứng** của module **AGILE_DEVELOPMENT**. Nội dung giúp vận dụng user story, Product Backlog, Scrum, Kanban, các thực hành kỹ thuật của XP và phép đo dòng công việc để kiểm chứng rằng phần mềm hoạt động đúng yêu cầu, đồng thời tiếp tục học xem nó có tạo giá trị cho người dùng hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **nhu cầu/yêu cầu**, **tiêu chí chấp nhận**, **kịch bản kiểm tra**, **kết quả kiểm tra**, **Definition of Done** và **kết quả sử dụng thực tế**.
2. Chuyển một yêu cầu mơ hồ thành user story hoặc backlog item có ngữ cảnh, phạm vi, ràng buộc và tiêu chí chấp nhận quan sát được.
3. Thiết kế đường liên kết từ mục tiêu người dùng đến yêu cầu, tiêu chí, cách kiểm chứng, bằng chứng và quyết định tiếp theo.
4. Chọn bằng chứng kiểm chứng phù hợp với rủi ro: kiểm thử tự động, kiểm tra thủ công, dữ liệu tích hợp, quan sát khả năng truy cập, hiệu năng và phản hồi từ người dùng.
5. Phân tích trường hợp một bài test “xanh” nhưng bằng chứng vẫn chưa đủ; biết cách ghi nhận môi trường, phiên bản, dữ liệu và giới hạn kiểm tra.
6. Duy trì tính truy vết vừa đủ khi backlog thay đổi, không để tiêu chí chấp nhận hoặc bộ kiểm thử trở thành tài liệu lỗi thời.

## 1. Sáu khái niệm không nên đánh đồng

| Khái niệm | Câu hỏi chính | Ví dụ với chức năng lưu khóa học yêu thích |
|---|---|---|
| **Nhu cầu/vấn đề người dùng** | Người dùng đang cần làm gì và vì sao? | Học viên muốn tìm lại nhanh khóa học quan tâm, không phải tìm kiếm từ đầu |
| **Yêu cầu/backlog item** | Sản phẩm cần hỗ trợ năng lực hoặc hành vi nào? | Cho phép học viên lưu và mở lại danh sách khóa học yêu thích |
| **Tiêu chí chấp nhận (acceptance criteria, AC)** | Điều kiện quan sát được nào phải đúng để yêu cầu được chấp nhận? | Khóa đã lưu vẫn xuất hiện sau khi đăng nhập lại; dữ liệu các tài khoản được tách biệt |
| **Kịch bản kiểm chứng (test/check)** | Sẽ làm gì, với dữ liệu và môi trường nào, để kiểm tra điều kiện? | Đăng nhập tài khoản A, lưu khóa X, đăng xuất, đăng nhập lại và kiểm tra danh sách |
| **Bằng chứng kiểm chứng (verification evidence)** | Kết quả thực tế cho thấy điều gì đã đạt, chưa đạt và trong điều kiện nào? | Kết quả chạy test trên build cụ thể, trạng thái thực tế, log đã che dữ liệu nhạy cảm, ghi nhận lỗi nếu có |
| **Kết quả người dùng (outcome)** | Sau khi dùng sản phẩm, người dùng thực sự làm tốt hơn điều gì? | Học viên tìm lại khóa học đã lưu nhanh hơn, ít phải tìm kiếm lại |

Một **tiêu chí chấp nhận** là phát biểu về hành vi mong đợi; **test** là cách kiểm tra; **test result** là kết quả của một lần kiểm tra. Việc viết ra test case chưa chứng minh test đã chạy. Test chạy thành công chưa tự chứng minh mọi rủi ro đã được bao phủ. Một tính năng đạt tất cả tiêu chí chấp nhận vẫn có thể không giúp người dùng như dự đoán.

### 1.1. “Verification” và “validation” liên quan nhưng khác nhau

Trong bài, có thể dùng hai câu hỏi:

- **Kiểm chứng yêu cầu (verification):** *Chúng ta có xây đúng theo những yêu cầu và tiêu chí đã thống nhất không?* Bằng chứng đến từ kiểm thử, kiểm tra, đánh giá hiện vật hoặc môi trường tích hợp.
- **Xác nhận giá trị/nhu cầu (validation):** *Những gì đã xây có thực sự giải quyết vấn đề đúng người dùng không?* Bằng chứng có thể là thử nghiệm sử dụng, quan sát hành vi, phỏng vấn, dữ liệu sản phẩm và phản hồi thực tế.

Các tổ chức hoặc chuẩn chuyên môn có thể dùng thuật ngữ và ranh giới khác nhau; điều quan trọng là xác định rõ câu hỏi đang kiểm tra. Đừng gọi kết quả test API là bằng chứng người dùng đã tìm lại khóa học nhanh hơn.

### 1.2. Tiêu chí chấp nhận khác Definition of Done

**Tiêu chí chấp nhận** thường cụ thể cho một backlog item: chức năng này phải đáp ứng những điều kiện nghiệp vụ nào? **Definition of Done (DoD)** là mô tả chính thức về trạng thái của Increment khi đạt các tiêu chuẩn chất lượng áp dụng cho sản phẩm trong Scrum.

| Ví dụ | Tiêu chí chấp nhận của câu chuyện cụ thể | Definition of Done chung |
|---|---|---|
| Lưu khóa yêu thích | Khóa đã lưu hiển thị sau khi đăng nhập lại | Mã được tích hợp, kiểm thử liên quan đạt, đáp ứng chính sách chất lượng |
| Đổi mật khẩu | Liên kết hết hạn không thể đổi mật khẩu | Các kiểm tra bảo mật phù hợp được thực hiện, không còn lỗi trái với mức chất lượng đã thống nhất |
| Lọc khóa học | Bộ lọc chỉ hiển thị khóa phù hợp điều kiện | Yêu cầu khả năng truy cập và chất lượng liên quan được đáp ứng |

Không nên biến một tiêu chí chấp nhận của một user story thành chuẩn toàn sản phẩm nếu nó không phù hợp cho mọi Increment. Ngược lại, việc tất cả AC “đạt” **chưa đủ để công nhận Increment Done** nếu vẫn vi phạm DoD, ví dụ chưa tích hợp hoặc còn rủi ro bảo mật bắt buộc phải xử lý.

**Lưu ý trong Scrum:** Chỉ công việc đáp ứng DoD mới được tính vào Increment. Sprint Review giúp Scrum Team và stakeholders kiểm tra kết quả, tiếp tục thích ứng Product Backlog; nó không phải cổng phê duyệt bắt buộc để phát hành.

## 2. Đường liên kết từ nhu cầu đến quyết định

Một đường liên kết thực dụng:

~~~mermaid
flowchart TD
    A["Nhu cầu / mục tiêu người dùng"] --> B["Yêu cầu hoặc Product Backlog Item"]
    B --> C["Tiêu chí chấp nhận"]
    C --> D["Kịch bản / phép kiểm tra"]
    D --> E["Bằng chứng: kết quả thực tế"]
    E --> F{"Đủ căn cứ chấp nhận?"}
    F -->|Chưa| G["Sửa lỗi, làm rõ AC hoặc bổ sung kiểm chứng"]
    G --> C
    F -->|Đủ theo phạm vi và DoD| H["Increment có thể kiểm tra / sử dụng"]
    H --> I["Phản hồi và kết quả người dùng"]
    I --> J["Giữ, điều chỉnh hoặc ưu tiên lại backlog"]
    J -.-> B
~~~

Mỗi mắt xích trả lời một câu hỏi khác nhau:

1. **Tại sao?** Yêu cầu phục vụ nhu cầu và mục tiêu nào?
2. **Cái gì?** Phần mềm cần cung cấp khả năng hoặc hành vi nào?
3. **Thế nào là chấp nhận được?** Ranh giới, trường hợp thành công và thất bại cần được thống nhất ra sao?
4. **Kiểm tra bằng cách nào?** Phải chuẩn bị tình huống, dữ liệu và môi trường nào?
5. **Đã quan sát điều gì?** Kết quả thực tế có khớp mong đợi không và có giới hạn gì?
6. **Quyết định tiếp theo là gì?** Chấp nhận, sửa, tìm hiểu thêm, mở rộng thử nghiệm hay đổi giải pháp?

Không cần tạo một hệ thống quản lý yêu cầu nặng nề cho mọi câu chuyện. Trong nhóm nhỏ, liên kết có thể nằm ngay trong backlog item: mô tả, AC, đường dẫn tới bài kiểm thử và kết quả pipeline. Với phần mềm có yêu cầu truy vết cao, cần cấu trúc và phê duyệt chi tiết hơn. **Mức độ truy vết nên tương xứng với độ phức tạp, rủi ro và nghĩa vụ của sản phẩm.**

## 3. Từ yêu cầu mơ hồ đến backlog item có thể thảo luận

### 3.1. Bắt đầu với vấn đề, không chốt giải pháp quá sớm

Một stakeholder nói “Thêm nút hình trái tim vào tất cả thẻ khóa học”. Nếu nhóm tiếp nhận nguyên văn, có thể làm đúng giao diện nhưng bỏ qua nhu cầu lưu trữ hoặc xem lại danh sách.

Hãy hỏi:

- Ai đang muốn sử dụng khả năng này? Người chưa đăng nhập hay học viên đã đăng ký?
- Họ cần làm việc gì? Lưu để so sánh, tìm lại, mua sau hay chia sẻ?
- Hiện tại họ gặp khó khăn ở bước nào? Có bằng chứng ban đầu không?
- Phần mềm phải ghi nhớ dữ liệu trong một phiên hay giữa nhiều lần đăng nhập?
- Dữ liệu đó có riêng tư với từng tài khoản không?
- Có ràng buộc về thiết bị, khả năng truy cập, hiệu năng hoặc phạm vi phát hành không?

Một yêu cầu dễ trao đổi hơn:

> **Là** học viên đã đăng nhập, **tôi muốn** lưu khóa học vào danh sách yêu thích và mở lại danh sách này sau, **để** tìm lại những khóa tôi quan tâm mà không cần tìm kiếm từ đầu.

User story giúp diễn đạt người dùng và mục đích; nó **không phải bản đặc tả đầy đủ**. Nội dung còn cần được làm rõ trong thảo luận với người có hiểu biết về nghiệp vụ, kỹ thuật, kiểm thử, vận hành và người dùng khi phù hợp.

### 3.2. Làm rõ phạm vi và giả định

Trước khi viết AC, nhóm có thể thống nhất:

| Vấn đề cần làm rõ | Quyết định minh họa |
|---|---|
| Đối tượng | Học viên đã xác thực |
| Phạm vi đầu tiên | Lưu, xem lại và bỏ lưu khóa học; chưa hỗ trợ chia sẻ danh sách |
| Ngữ cảnh sử dụng | Trang danh sách và chi tiết khóa học trên web được hỗ trợ |
| Dữ liệu | Lựa chọn được lưu theo tài khoản và còn sau khi đăng nhập lại |
| Chính sách khi khóa học bị ẩn/xóa | Cần thống nhất cách hiển thị hoặc loại khỏi danh sách |
| Ràng buộc | Không để tài khoản khác xem danh sách; khả năng điều khiển bằng bàn phím |
| Điều chưa quyết | Có cần đồng bộ thời gian thực giữa nhiều thiết bị ở bản đầu không? |

Mục “điều chưa quyết” rất quan trọng: nếu một quyết định ảnh hưởng đáng kể đến triển khai hoặc kiểm thử, nhóm cần làm rõ trước khi khẳng định yêu cầu đã sẵn sàng. Các chi tiết ít rủi ro có thể được làm rõ trong quá trình phát triển.

### 3.3. Ghi nhận cả yêu cầu phi chức năng và ràng buộc

Yêu cầu không chỉ là nút, API hoặc trang. Chúng có thể bao gồm:

- **Bảo mật và riêng tư:** dữ liệu yêu thích chỉ thuộc về tài khoản hợp lệ.
- **Khả năng truy cập:** trạng thái “đã lưu/chưa lưu” có thể nhận biết và thao tác bằng bàn phím, trình đọc màn hình phù hợp.
- **Hiệu năng:** thao tác phản hồi trong giới hạn đã thỏa thuận ở điều kiện tải, thiết bị và mạng được xác định.
- **Khả dụng và độ tin cậy:** khi dịch vụ lưu dữ liệu lỗi, giao diện không được báo thành công giả.
- **Tính tương thích:** hỗ trợ các thiết bị/trình duyệt đã công bố.
- **Đúng đắn dữ liệu:** lưu lặp không tạo bản ghi trùng gây lỗi; bỏ lưu không tác động tài khoản khác.

Những yêu cầu này có thể được thể hiện trong AC của item, trong DoD hoặc chính sách chung, tùy phạm vi. Điều cần tránh là **để yêu cầu quan trọng không được chủ động kiểm chứng ở đâu cả**.

## 4. Viết tiêu chí chấp nhận có thể quan sát

Một tiêu chí chấp nhận tốt phải giúp các bên hiểu thế nào là “đúng” khi nhìn vào hành vi sản phẩm. Nó không cần mô tả mọi dòng mã hay ép buộc thiết kế kỹ thuật nội bộ.

### 4.1. Các đặc tính cần có

| Đặc tính | Câu hỏi kiểm tra | Ví dụ |
|---|---|---|
| **Rõ ràng** | Có từ mơ hồ như “nhanh”, “đẹp”, “ổn định” mà chưa định nghĩa không? | “Danh sách tải nhanh” cần điều kiện đo và ngưỡng phù hợp |
| **Quan sát/kiểm tra được** | Có thể tạo tình huống và so sánh kết quả với mong đợi không? | Sau đăng nhập lại, khóa X đã lưu vẫn hiển thị |
| **Gắn với nhu cầu** | Đạt tiêu chí có đóng góp vào năng lực người dùng cần không? | Lưu được khóa để mở lại |
| **Có ranh giới** | Đã nêu đối tượng, trạng thái, dữ liệu và điều kiện quan trọng chưa? | Người dùng A không xem được danh sách của B |
| **Bao gồm ngoại lệ có ý nghĩa** | Khi lỗi mạng, dữ liệu không hợp lệ hoặc trạng thái đặc biệt thì sao? | Lưu thất bại phải hiển thị trạng thái không thành công |
| **Không áp đặt giải pháp không cần thiết** | Tiêu chí có đang bắt buộc framework, cấu trúc bảng hay vị trí pixel vô cớ? | Nêu hành vi lưu thay vì tên bảng database |
| **Có khả năng bảo trì** | Khi nghiệp vụ đổi, có thể xác định tiêu chí và test nào bị ảnh hưởng không? | AC có ID ngắn, test/đường dẫn liên quan |

Một AC có thể chứa nhiều điều kiện liên quan, nhưng nếu một tiêu chí vừa nói về lưu dữ liệu, hiệu năng, thông báo lỗi và phân quyền thì khó xác định phần nào chưa đạt. Hãy tách những hành vi độc lập quan trọng mà vẫn giữ số lượng tiêu chí ở mức có thể hiểu.

### 4.2. Ví dụ AC cho một user story

**User story US-FAV-01:** Là học viên đã đăng nhập, tôi muốn lưu khóa học yêu thích để tìm lại khi cần.

| ID | Tiêu chí chấp nhận minh họa |
|---|---|
| **AC-01** | Khi học viên lưu một khóa hợp lệ, trạng thái lưu hiển thị rõ và khóa xuất hiện trong danh sách yêu thích của chính tài khoản đó. |
| **AC-02** | Sau khi đăng xuất và đăng nhập lại, những khóa đã lưu vẫn xuất hiện đúng trong danh sách của học viên. |
| **AC-03** | Thao tác lưu lặp lại không tạo nhiều mục trùng cho cùng một khóa và tài khoản. |
| **AC-04** | Khi bỏ lưu, khóa được loại khỏi danh sách yêu thích của tài khoản đó; khóa học gốc không bị xóa. |
| **AC-05** | Tài khoản A không thể truy vấn hoặc sửa danh sách yêu thích của tài khoản B qua giao diện hay API liên quan. |
| **AC-06** | Nếu lưu thất bại, giao diện không duy trì trạng thái “đã lưu” sai; người dùng nhận thông báo phù hợp và có thể thử lại an toàn. |
| **AC-07** | Thao tác lưu/bỏ lưu và trạng thái tương ứng có thể sử dụng, nhận biết bằng bàn phím và công nghệ hỗ trợ theo tiêu chuẩn sản phẩm. |

Các tiêu chí trên là **giả định để minh họa cách viết**. Một sản phẩm thực tế còn phải thống nhất chuyện khóa học bị xóa, danh sách không giới hạn hay có giới hạn, xử lý nhiều thiết bị, yêu cầu riêng tư và mức hỗ trợ trình duyệt.

### 4.3. Viết tình huống Given–When–Then

Với cách tiếp cận **Specification by Example/Behavior-Driven Development (BDD)**, người có hiểu biết về nghiệp vụ, lập trình viên và người kiểm thử có thể dùng ví dụ để thống nhất hành vi trước khi triển khai.

~~~gherkin
Feature: Luu khoa hoc yeu thich

  Scenario: Luu va xem lai sau khi dang nhap
    Given hoc vien A da dang nhap
    And khoa hoc X ton tai va duoc phep hien thi
    When hoc vien A luu khoa hoc X
    And hoc vien A dang xuat va dang nhap lai
    Then khoa hoc X xuat hien trong danh sach yeu thich cua A

  Scenario: Luu lap lai khong tao ban ghi trung
    Given hoc vien A da luu khoa hoc X
    When hoc vien A yeu cau luu khoa hoc X mot lan nua
    Then danh sach yeu thich cua A chi co mot muc cho X

  Scenario: Hai tai khoan co du lieu rieng
    Given hoc vien A da luu khoa hoc X
    And hoc vien B la mot tai khoan khac
    When hoc vien B xem danh sach yeu thich cua minh
    Then khoa hoc X khong tu dong xuat hien do A da luu
    And hoc vien B khong the thay doi ban ghi cua A

  Scenario: Luu that bai
    Given hoc vien A dang xem khoa hoc X
    And dich vu luu yeu thich tam thoi khong kha dung
    When hoc vien A yeu cau luu khoa hoc X
    Then giao dien khong xac nhan da luu thanh cong
    And hoc vien A duoc thong bao phu hop
~~~

Ví dụ dùng nội dung không dấu cho dễ dùng ở môi trường có cấu hình mã hóa khác nhau; trong tài liệu nghiệp vụ vẫn có thể viết tiếng Việt có dấu. Các từ khóa Given/When/Then là cấu trúc để diễn đạt; **chỉ khi có mã hỗ trợ và thực sự chạy**, kịch bản mới trở thành bằng chứng kiểm thử tự động. Một đoạn Gherkin được viết đẹp chưa chứng minh sản phẩm hoạt động.

### 4.4. Đừng dùng AC để cố định mọi chi tiết giao diện

Tiêu chí “nút trái tim màu đỏ, cách mép phải 12 pixel” có thể cần thiết nếu đó là yêu cầu thiết kế/nhận diện đã thống nhất; nhưng với mục tiêu “lưu để tìm lại”, các chi tiết ấy dễ bị thay đổi qua thử nghiệm khả năng sử dụng.

Hãy phân biệt:

- **Hành vi bắt buộc:** người dùng nhận biết được trạng thái lưu, lưu có hiệu lực sau đăng nhập lại.
- **Quy tắc nghiệp vụ:** tài khoản không được xem dữ liệu của nhau.
- **Quyết định thiết kế có thể thay đổi:** dùng trái tim, dấu trang hay nút “Lưu”.

Việc tách này giúp đội thích ứng với phản hồi giao diện mà không gây hiểu nhầm là “thay đổi yêu cầu nghiệp vụ” mỗi khi đổi icon.

## 5. Chuyển từ AC sang kế hoạch kiểm chứng và bằng chứng

Nhóm cần trả lời hai câu hỏi riêng: **“Kiểm tra bằng cách nào?”** và **“Kết quả thực tế đã chứng minh điều gì?”**

### 5.1. Bảng nối yêu cầu, AC, phép kiểm tra, bằng chứng

| Liên kết | Rủi ro/hành vi cần kiểm tra | Phép kiểm tra minh họa | Bằng chứng cần lưu |
|---|---|---|---|
| **US-FAV-01 → AC-01** | Lưu thành công và nhìn thấy trạng thái | Kiểm tra luồng UI–API–data với tài khoản A và khóa X | Kết quả integration/E2E của build, trạng thái dữ liệu sau thao tác |
| **US-FAV-01 → AC-02** | Dữ liệu tồn tại qua phiên đăng nhập | Đăng xuất, đăng nhập lại trên phiên mới, mở danh sách | Kết quả lần chạy, phiên bản và môi trường |
| **US-FAV-01 → AC-03** | Lưu trùng | Gửi yêu cầu lặp lại hoặc bấm lưu nhiều lần theo điều kiện đã xác định | Kiểm tra số mục duy nhất, kết quả API và dữ liệu |
| **US-FAV-01 → AC-04** | Bỏ lưu không xóa khóa gốc | Bỏ lưu, mở lại danh sách và kiểm tra khóa học gốc | Kết quả kiểm thử và trạng thái hệ thống |
| **US-FAV-01 → AC-05** | Truy cập trái quyền | Dùng tài khoản B yêu cầu dữ liệu/điều chỉnh bản ghi của A | Kiểm thử phân quyền âm tính và phản hồi bị từ chối theo chính sách |
| **US-FAV-01 → AC-06** | Lỗi dịch vụ dẫn tới xác nhận sai | Mô phỏng thất bại có kiểm soát ở dịch vụ lưu | Dấu vết tình huống, trạng thái UI, kết quả lỗi và khả năng thử lại |
| **US-FAV-01 → AC-07** | Không thao tác/nhận biết được bằng công nghệ hỗ trợ | Kiểm tra bàn phím, tên/trạng thái điều khiển, công nghệ hỗ trợ được hỗ trợ | Báo cáo kiểm tra accessibility, trường hợp chưa đạt và môi trường |

Bảng không quy định phải viết **một test cho đúng một AC**. Một kiểm thử đầu-cuối có thể cung cấp bằng chứng cho nhiều AC; một AC rủi ro cao có thể cần nhiều phép kiểm tra ở những lớp khác nhau. Việc gắn ID chỉ giúp tra ngược yêu cầu; không cần tạo hàng trăm ID nếu bảng đơn giản hơn vẫn đủ rõ.

### 5.2. Dùng bằng chứng đúng mức rủi ro

| Hình thức kiểm chứng | Mạnh ở loại câu hỏi nào? | Giới hạn thường gặp |
|---|---|---|
| **Unit test** | Quy tắc xử lý, tính toán, trường hợp biên trong phạm vi nhỏ | Không chứng minh luồng tích hợp hoặc trải nghiệm người dùng |
| **Contract/API test** | Định dạng request/response, quyền truy cập, lỗi được trả đúng ở giao diện dịch vụ | Có thể không kiểm tra được hành vi trong UI hoặc phụ thuộc chạy thực |
| **Integration test** | Thành phần kết nối với dữ liệu, dịch vụ khác theo tình huống cụ thể | Môi trường thử có thể khác điều kiện vận hành |
| **End-to-end test** | Luồng sử dụng đi qua nhiều thành phần, từ đầu vào đến kết quả | Thường tốn bảo trì và dễ nhiễu nếu dựng môi trường kém ổn định |
| **Kiểm tra khám phá/thủ công** | Tương tác chưa dự đoán, thông báo khó hiểu, vấn đề trải nghiệm và lỗi giao diện | Phụ thuộc cách thực hiện, nên ghi lại bước và kết quả khi rủi ro cao |
| **Accessibility review** | Khả năng điều khiển, nhận biết trạng thái, trải nghiệm với công nghệ hỗ trợ | Công cụ tự động không bao phủ mọi vấn đề sử dụng |
| **Performance/security checks** | Giới hạn tải, truy cập sai quyền, các yêu cầu an toàn quan trọng | Cần mô hình rủi ro và điều kiện thử có ý nghĩa |
| **Quan sát sử dụng thực tế** | Người dùng có hoàn thành việc cần làm và gặp trở ngại nào? | Xác nhận giá trị sử dụng, không thay thế tất cả kiểm thử kỹ thuật |

Không nhất thiết chạy mọi loại test cho mọi story. Chọn **chiến lược dựa trên rủi ro**: điều gì nếu sai sẽ ảnh hưởng lớn, ở lớp nào có thể phát hiện sớm và bằng chứng nào đủ đáng tin cho quyết định.

### 5.3. Một kết quả kiểm chứng đáng tin gồm gì?

Khi cần truy vết sau phát hành, chỉ có dòng “PASS” trong bảng tính thường chưa đủ. Một bản ghi kiểm chứng nên cho biết:

1. **Tiêu chí hoặc rủi ro được kiểm tra:** ID AC, mô tả hoặc đường dẫn liên quan.
2. **Phiên bản được kiểm tra:** commit, build, gói triển khai hoặc phiên bản API; không cần mọi mục đều hiện trong báo cáo tổng hợp nếu có đường dẫn truy ngược.
3. **Môi trường và điều kiện:** local, staging, production có kiểm soát; cấu hình, loại thiết bị hoặc phụ thuộc giả lập/được dùng thật.
4. **Dữ liệu và các bước trọng yếu:** đủ để tái hiện, nhưng tránh lưu thông tin nhạy cảm của người dùng.
5. **Mong đợi so với quan sát:** kết quả thực tế, số đo nếu phù hợp, pass/fail/skipped và lý do.
6. **Thời điểm và người/hệ thống thực hiện:** khi nào chạy, pipeline nào hoặc ai kiểm tra.
7. **Giới hạn và vấn đề còn mở:** trường hợp chưa kiểm tra, test không ổn định, lỗi được ghi nhận hoặc ngoại lệ được phê duyệt đúng thẩm quyền.

Ví dụ ghi nhận ngắn (dữ liệu minh họa):

~~~text
Backlog item: US-FAV-01
Acceptance criterion: AC-02 (giu danh sach sau dang nhap lai)
Test case: E2E-FAV-RELOGIN
Build: 4f9c2a1 (vi du)
Environment: staging, database duoc khoi tao test rieng
Data: learner-test-A, course-X, khong dung du lieu nguoi dung that
Expected: X van xuat hien trong danh sach sau khi dang nhap lai
Observed: X xuat hien dung mot lan, thuoc tai khoan A
Result: PASS
Executed by: CI job / run minh hoa 1842
Limitations: chua kiem tra dong bo thoi gian thuc hai thiet bi
Evidence: duong dan den ket qua run, log da an du lieu nhay cam
~~~

Đây là **mẫu minh họa**, không phải log của một hệ thống đã chạy thật. Khi áp dụng, dùng đường dẫn đến bằng chứng thực tế, không điền “PASS” dựa trên dự đoán.

### 5.4. Test “xanh” nhưng vẫn chưa đủ bằng chứng

Một số tình huống điển hình:

- **Mock quá nhiều:** test xác nhận gọi hàm lưu thành công, nhưng chưa chạy qua database thật của môi trường tích hợp.
- **Không kiểm tra kết quả quan sát được:** API trả HTTP 200 nhưng dữ liệu không tồn tại khi đăng nhập lại.
- **Chỉ kiểm tra happy path:** chưa xét lưu lặp, lỗi mạng, quyền truy cập và dữ liệu xấu.
- **Môi trường không đại diện:** bản demo dùng tài khoản có quyền đặc biệt hoặc dữ liệu dựng sẵn không giống hành vi thực.
- **Test bị bỏ qua hoặc không ổn định:** pipeline báo tổng thể “green” trong khi phép kiểm chứng quan trọng bị skip, quarantine hoặc thất bại ngẫu nhiên.
- **Bằng chứng cũ:** test pass ở commit trước nhưng chức năng hoặc phụ thuộc đã đổi.
- **Thiếu kết quả sử dụng:** mọi AC đều pass nhưng người dùng không biết tìm danh sách yêu thích ở đâu.

Vì vậy, thay vì hỏi đơn giản “bao nhiêu test pass?”, hãy hỏi **“Các AC và rủi ro quan trọng có được kiểm tra bằng chứng phù hợp ở đúng phiên bản và điều kiện chưa?”**

## 6. Ba góc nhìn giúp làm rõ yêu cầu trước khi viết code

Một cuộc thảo luận ngắn giữa người hiểu nghiệp vụ, người xây dựng và người kiểm chứng thường phát hiện nhiều hiểu nhầm trước khi chúng trở thành lỗi.

Trong cộng đồng Agile, cách làm này thường được gọi là **Three Amigos** (ba góc nhìn), nhưng không bắt buộc đúng ba người hoặc ba chức danh:

| Góc nhìn | Câu hỏi đóng góp |
|---|---|
| **Nghiệp vụ/sản phẩm** | Người dùng cần gì, vì sao, quy tắc và ngoại lệ nào quan trọng, mức nào là đủ để có giá trị? |
| **Phát triển/kỹ thuật** | Hành vi có khả thi, phụ thuộc nào ảnh hưởng, dữ liệu và rủi ro kỹ thuật nào cần làm rõ? |
| **Kiểm thử/chất lượng** | Làm thế nào biết đúng/sai, tình huống biên nào dễ bỏ sót, bằng chứng nào có thể lặp lại? |

Với yêu cầu có rủi ro cao, nên mời thêm chuyên gia bảo mật, accessibility, vận hành, pháp lý hoặc người dùng phù hợp. Họ giúp phát hiện các điều kiện mà nhóm chức năng có thể không nhìn thấy.

### 6.1. Một cuộc trao đổi minh họa

> **Sản phẩm:** “Người dùng đã lưu khóa thì phải tìm lại được sau vài ngày.”
>
> **Phát triển:** “Chúng ta lưu ở tài khoản hay trình duyệt? Người dùng đăng nhập nhiều thiết bị thì sao?”
>
> **Kiểm thử:** “Nếu lưu thất bại mà giao diện đổi màu thì sao? Tài khoản B có thể xem khóa của A không?”
>
> **Sản phẩm:** “Lưu theo tài khoản là bắt buộc. Phiên bản đầu chưa cần đồng bộ tức thời, nhưng sau đăng nhập mới phải có dữ liệu đã lưu.”
>
> **Cả nhóm:** “Viết AC cho lưu qua phiên, lỗi, trùng và phân quyền. Kiểm chứng lớp tích hợp và luồng đầu-cuối trước khi gọi Done.”

Sau cuộc họp, nhóm có **ít bất định hơn** và một cách hiểu chung. Thời gian trao đổi ngắn có thể giúp tiết kiệm nhiều vòng sửa lỗi do mỗi người tự giả định khác nhau.

### 6.2. Ví dụ giúp phát hiện quy tắc còn thiếu

Nói “người dùng có thể bỏ lưu” chưa trả lời:

- Bỏ lưu hai lần liên tiếp thì trạng thái nào được trả về?
- Có được bỏ lưu một khóa đã bị xóa khỏi danh mục?
- Nếu nhiều tab cùng thay đổi danh sách, sản phẩm xử lý trạng thái khác nhau thế nào?
- Nếu đang mất mạng, giao diện hiển thị rõ điều gì?
- Có bao nhiêu khóa tối đa? Nếu chưa có giới hạn, hệ thống có cần cân nhắc hiệu năng không?

Không phải câu hỏi nào cũng cần trở thành AC của lát cắt đầu tiên. Hãy **ưu tiên các quy tắc ảnh hưởng đến hành vi, an toàn và khả năng kiểm chứng**, rồi ghi các quyết định còn mở để được xem xét ở đúng thời điểm.

## 7. Kiểm chứng yêu cầu phi chức năng bằng bằng chứng đo được

Các yêu cầu “dễ dùng”, “nhanh”, “an toàn” thường tạo cảm giác mọi người hiểu giống nhau, nhưng khó xác nhận nếu không có điều kiện rõ.

### 7.1. Hiệu năng: phải có ngữ cảnh đo

Yêu cầu mơ hồ: “Danh sách yêu thích phải tải rất nhanh”.

Một phát biểu có thể kiểm tra hơn:

> Ở cấu hình và bộ dữ liệu thử nghiệm đã thống nhất, trong điều kiện tải mô phỏng mức sử dụng mục tiêu, thời gian phản hồi API danh sách yêu thích ở phân vị thứ 95 (p95) không vượt quá ngưỡng được đội và stakeholders chấp thuận.

Để biến thành AC/bằng chứng thực tế, còn cần **con số ngưỡng**, **cách đo**, **điểm bắt đầu/kết thúc**, **tải đồng thời**, **bộ dữ liệu** và **hệ thống thử**. Không tự chọn một ngưỡng chung cho mọi sản phẩm rồi coi là chuẩn ngành.

### 7.2. Bảo mật: phải thử hành vi trái quyền

Yêu cầu mơ hồ: “Dữ liệu của người dùng phải an toàn”.

Ví dụ tiêu chí và phép kiểm chứng:

- Người dùng không được đọc/sửa mục yêu thích của tài khoản khác thông qua API.
- Kiểm thử đăng nhập dưới hai tài khoản với dữ liệu khác nhau; thử truy cập tài nguyên không thuộc quyền theo chính sách.
- Ghi rõ phản hồi, trạng thái lưu và dấu vết thích hợp, tránh chứa token, mật khẩu hoặc dữ liệu cá nhân không cần thiết trong báo cáo.

Một vài phép thử phân quyền đạt **không đồng nghĩa toàn bộ sản phẩm đã an toàn**. Mức kiểm chứng cần xuất phát từ mô hình đe dọa và chính sách bảo mật thực tế.

### 7.3. Khả năng truy cập: cần quan sát được

Yêu cầu mơ hồ: “Hỗ trợ người khuyết tật”.

Có thể làm rõ:

- Người dùng bàn phím có thể di chuyển tới nút lưu, kích hoạt và bỏ lưu mà không bị mắc kẹt.
- Thành phần điều khiển có tên và trạng thái đủ để công nghệ hỗ trợ nhận biết, ví dụ “Đã lưu vào yêu thích” và “Chưa lưu”.
- Có thông báo có thể nhận biết khi lưu thất bại.
- Nhóm kiểm chứng với tiêu chuẩn khả năng truy cập mà sản phẩm cam kết, trong thiết bị/trình duyệt/công nghệ hỗ trợ phù hợp.

Một công cụ quét accessibility tự động có thể phát hiện một phần lỗi, nhưng **không thay thế** toàn bộ kiểm tra thao tác thực tế.

### 7.4. Chất lượng dữ liệu và vận hành

Với hệ thống có thao tác lưu, sao chép hoặc đồng bộ, cần xem:

- Có ghi trùng hay mất dữ liệu khi người dùng thử lại không?
- Tính nhất quán giữa những lần đọc/ghi có phù hợp chính sách không?
- Khi dịch vụ phụ thuộc lỗi, hệ thống hiển thị trạng thái trung thực hay xác nhận thành công giả?
- Có khả năng quan sát lỗi và hỗ trợ xử lý sự cố mà không làm lộ dữ liệu nhạy cảm không?

Những tiêu chí này phục vụ một kết quả người dùng đơn giản: họ **tin được vào những gì sản phẩm hiển thị**.

## 8. Bằng chứng từ TDD, BDD và kiểm thử liên tục

Những thực hành gắn với **Extreme Programming (XP)** giúp kiểm tra yêu cầu sớm, nhưng cần hiểu đúng vai trò từng kỹ thuật.

### 8.1. TDD kiểm tra logic theo vòng ngắn

Trong Test-Driven Development (TDD), nhà phát triển thường đi theo nhịp **Red → Green → Refactor**: viết kiểm thử cho một hành vi nhỏ chưa có, làm cho test đạt, rồi cải thiện cấu trúc mà vẫn giữ hành vi.

Ví dụ logic “không thêm trùng cùng khóa cho một tài khoản” có thể được kiểm tra trước khi viết đầy đủ chức năng. Kiểm thử hỗ trợ phát hiện hồi quy khi code thay đổi.

Tuy nhiên, unit test đạt không chứng minh:

- Dữ liệu được lưu đúng qua database hoặc session thực.
- API có kiểm soát quyền truy cập đúng.
- Người dùng nhìn thấy trạng thái đúng trên UI.
- Tính năng giải quyết được nhu cầu tìm lại khóa học.

Do đó, TDD là một cách tạo **bằng chứng kỹ thuật ở phạm vi phù hợp**, cần kết hợp kiểm tra tích hợp và người dùng khi rủi ro yêu cầu.

### 8.2. BDD giúp cùng hiểu hành vi nghiệp vụ

BDD/Specification by Example tập trung trao đổi các ví dụ cụ thể của hành vi mong đợi trước hoặc trong quá trình phát triển. Những ví dụ này có thể trở thành các kiểm thử tự động khi có công cụ và mã thực thi, nhưng giá trị cốt lõi là **thu hẹp khoảng cách hiểu giữa các vai trò**.

Một công cụ có thể thực thi Gherkin sai với ý định nghiệp vụ nếu các bước được mã hóa không đúng. Vì vậy phải kiểm tra cả **đặc tả**, **bước chạy** và **kết quả sản phẩm**; không tin vào tên kịch bản như “should be secure” mà thiếu phép kiểm tra liên quan.

### 8.3. Tích hợp liên tục và bằng chứng mới theo từng phiên bản

Khi mã được tích hợp thường xuyên, pipeline có thể chạy các kiểm thử liên quan ở từng thay đổi, giúp nhận phản hồi sớm hơn việc đợi cuối Sprint. Một báo cáo CI có thể cho thấy:

- Build/commit nào được kiểm tra.
- Các bài test liên quan AC nào đã chạy và kết quả.
- Những test nào bị bỏ qua hoặc không ổn định.
- Những kiểm tra chất lượng, phân tích tĩnh hay bảo mật phù hợp đã được thực hiện.

Các thông tin này mạnh hơn lời khẳng định “đã test rồi”. Nhưng kiểm thử tự động vẫn cần được cập nhật theo yêu cầu và đánh giá mức bao phủ thực chất. **Một đường pipeline xanh không miễn trừ trách nhiệm kiểm tra hành vi và rủi ro ngoài phạm vi pipeline**.

## 9. Tình huống xuyên suốt: từ yêu cầu đến bằng chứng kiểm chứng

> **Tình huống và mọi số liệu bên dưới đều là giả định phục vụ học tập**, không phải kết quả đo của một sản phẩm thực tế hoặc chuẩn dùng chung.

Một nền tảng học trực tuyến nhận phản hồi: học viên phải tìm lại khóa học đang quan tâm mỗi khi quay lại. Stakeholder đề nghị bổ sung nút “Lưu”.

### 9.1. Bước 1 — Làm rõ kết quả muốn tạo

Đội thống nhất vấn đề: học viên đã đăng nhập muốn đánh dấu và quay lại các khóa học quan tâm, tránh tìm lại qua danh sách lớn.

- **Outcome mong muốn:** người học tìm lại khóa đã đánh dấu thuận lợi hơn.
- **Đầu ra dự kiến:** khả năng lưu, xem và bỏ lưu yêu thích.
- **Giới hạn:** bản đầu hỗ trợ web và tài khoản đăng nhập; chưa bao gồm chia sẻ danh sách.
- **Ràng buộc:** không lộ dữ liệu giữa tài khoản; trạng thái phải trung thực khi hệ thống lỗi.
- **Điều cần kiểm chứng sau phát hành:** thời gian tìm lại khóa và phản hồi người học, không chỉ số lần bấm lưu.

### 9.2. Bước 2 — Chia nhỏ để có một lát cắt chạy xuyên suốt

Thay vì tạo ba ticket lớn “frontend”, “backend”, “database” rồi kết luận từng bộ phận xong, nhóm ưu tiên một lát cắt nhỏ:

> Học viên A có thể lưu một khóa hợp lệ, thấy nó trong danh sách cá nhân và xem lại sau khi đăng nhập lần khác.

Lát cắt này có thể cần thay đổi UI, API, lưu trữ và kiểm thử nhưng tạo ra một **hành vi sử dụng được**. Các trường hợp nâng cao như gợi ý khóa tương tự hoặc đồng bộ tức thời đa thiết bị có thể nằm trong backlog để được ưu tiên sau.

### 9.3. Bước 3 — Thống nhất AC và phương án kiểm chứng

Ba góc nhìn thảo luận và quyết định những tiêu chí quan trọng trước tiên: lưu thành công, tồn tại qua phiên, không trùng, không lộ dữ liệu, hiển thị lỗi. Các yếu tố còn tranh luận được ghi lại rõ.

Nhóm chọn lớp kiểm chứng:

| AC | Kiểm tra trước và trong phát triển | Kiểm tra tích hợp/trước phát hành | Kiểm tra sau khi đưa vào sử dụng |
|---|---|---|---|
| AC-01 | Logic ghi nhận, phản hồi API | UI–API–database với tài khoản thử | Người dùng có nhận biết trạng thái lưu không? |
| AC-02 | Quy tắc truy xuất theo tài khoản | Đăng xuất/đăng nhập lại trên phiên mới | Tỷ lệ quay lại danh sách, vấn đề phát sinh |
| AC-03 | Logic không tạo trùng | Yêu cầu lặp liên tiếp qua API và trạng thái dữ liệu | Theo dõi lỗi trùng có phát sinh không |
| AC-05 | Luật phân quyền | Thử truy cập và sửa dữ liệu của tài khoản khác | Theo dõi cảnh báo liên quan theo chính sách |
| AC-06 | Logic lỗi và thử lại | Mô phỏng dịch vụ lưu không khả dụng | Phản hồi người dùng khi lưu thất bại |

Đội không cần đợi mọi tính năng mở rộng hoàn thành mới kiểm chứng được những hành vi cơ bản. Nhưng nếu AC trọng yếu của lát cắt đầu chưa đạt, không nên gọi nó là hoàn tất.

### 9.4. Bước 4 — Thu bằng chứng và phát hiện lỗi thật

Giả sử ở lần chạy đầu, các phép kiểm tra cho kết quả minh họa:

| AC | Kết quả quan sát | Kết luận | Hành động |
|---|---|---|---|
| AC-01 | Lưu và hiển thị ngay thành công | PASS trong điều kiện kiểm tra | Giữ bằng chứng của build |
| AC-02 | Đăng nhập lại thì danh sách trống | FAIL | Kiểm tra lưu theo session hay theo tài khoản |
| AC-03 | Lưu lặp tạo hai bản ghi | FAIL | Sửa xử lý trùng, bổ sung kiểm thử hồi quy |
| AC-05 | B không xem được dữ liệu A | PASS với kịch bản đã thử | Xem còn đường truy cập trái quyền nào rủi ro cao |
| AC-06 | Dịch vụ lỗi nhưng nút vẫn hiển thị “đã lưu” | FAIL | Sửa trạng thái giao diện và thông báo lỗi |

Dù frontend đã “xong”, nhóm không thể tuyên bố backlog item đạt AC hoặc Increment đạt DoD. Việc phát hiện sớm ba lỗi là một **kết quả có ích của kiểm chứng**, giúp giảm rủi ro phát hành.

Sau khi sửa, đội chạy lại kiểm tra các AC chịu ảnh hưởng và các phép kiểm tra hồi quy liên quan. Chỉ ghi PASS dựa trên kết quả thực tế của lần chạy mới; không đổi trạng thái theo dự báo rằng “chắc đã ổn”.

### 9.5. Bước 5 — Xác nhận DoD và trình bày bằng chứng

Khi các AC đã đạt, đội vẫn kiểm tra DoD chung: tích hợp, kiểm thử phù hợp, bảo mật, chất lượng, khả năng phát hành và việc cập nhật cần thiết. Báo cáo có thể tóm tắt:

> **Backlog item:** US-FAV-01 — Lưu khóa yêu thích.  
> **Yêu cầu đã được kiểm chứng:** lưu, xem lại, bỏ lưu, phân quyền, lỗi dịch vụ và khả năng truy cập theo phạm vi đã thống nhất.  
> **Bằng chứng:** kết quả kiểm thử gắn build và môi trường tích hợp, các lỗi đã sửa và chạy lại, trạng thái các kiểm tra DoD.  
> **Giới hạn:** chưa kiểm tra đồng bộ tức thời nhiều thiết bị vì không thuộc phạm vi lát cắt đầu.  
> **Bước tiếp theo:** phát hành có kiểm soát và thu phản hồi về khả năng tìm lại khóa đã lưu.

Đây là cấu trúc minh họa, không phải báo cáo một sản phẩm thật. Trong thực tế, các đường dẫn bằng chứng phải trỏ đến kết quả kiểm tra có thể xem lại.

### 9.6. Bước 6 — Phân biệt kiểm chứng thành công với đạt outcome

Giả sử sau khi phát hành, phần mềm lưu đúng theo các AC và DoD. Tuy nhiên, người học ít mở lại danh sách yêu thích vì nó nằm trong menu khó tìm.

- **Verification:** những hành vi lưu, đọc và phân quyền đã đạt trong phạm vi được kiểm chứng.
- **Validation:** giả thuyết “tính năng này giúp người học tìm lại khóa nhanh hơn” chưa được xác nhận đầy đủ.
- **Quyết định sản phẩm:** quan sát hành trình thực tế, thử làm lối vào danh sách dễ thấy hơn, hoặc xem lại liệu lưu yêu thích có phải nhu cầu chính.

**Không sửa kết quả test đã pass thành fail chỉ vì outcome chưa cải thiện.** Hãy tách chất lượng đầu ra khỏi hiệu quả sử dụng, sau đó tạo yêu cầu hoặc giả thuyết mới khi bằng chứng cho thấy cần thay đổi.

## 10. Cách điều chỉnh yêu cầu mà vẫn giữ tính truy vết

Yêu cầu thích ứng không có nghĩa liên tục thay đổi “điều kiện đạt” để mọi việc luôn xanh. Khi học được điều mới, nhóm cần cập nhật tiêu chí và bằng chứng theo cách minh bạch.

### 10.1. Khi AC thay đổi, những gì phải được xem lại?

Ví dụ, phản hồi thực tế cho thấy học viên cần xem danh sách yêu thích trên thiết bị thứ hai ngay sau khi lưu. Trước đây AC chỉ yêu cầu dữ liệu tồn tại qua đăng nhập lại. Đội cần:

1. Xác định đây là yêu cầu mới, làm rõ nhu cầu và mức độ ưu tiên.
2. Thảo luận các tình huống: độ trễ đồng bộ chấp nhận được, xung đột cập nhật, thiết bị mất mạng, quyền truy cập.
3. Quyết định cập nhật AC của item đang làm hay tạo backlog item mới, phù hợp thời điểm và phạm vi.
4. Bổ sung hoặc điều chỉnh test cho hành vi đồng bộ; tránh giữ test cũ không còn phản ánh điều mong đợi.
5. Xác định lại những bằng chứng hiện có còn hợp lệ cho AC nào, bằng chứng nào cần chạy lại.
6. Làm rõ ảnh hưởng tới kế hoạch, DoD, rủi ro và mục tiêu đang theo đuổi.

Không xóa lịch sử lỗi hoặc bằng chứng cũ chỉ để tạo báo cáo đẹp. Một bản ghi thay đổi ngắn giúp người khác hiểu **tại sao** tiêu chí mới xuất hiện.

### 10.2. Quản lý thay đổi trong Scrum

Product Backlog được điều chỉnh khi có thông tin mới; Product Owner chịu trách nhiệm quản lý và sắp xếp ưu tiên hiệu quả. Trong Sprint, Developers cập nhật kế hoạch thực hiện hướng tới Sprint Goal; phạm vi có thể được làm rõ hoặc thương lượng lại với Product Owner khi học thêm, nhưng không nên làm mất Sprint Goal hoặc âm thầm giảm DoD.

Ví dụ:

- **Làm rõ một AC còn mơ hồ** trước khi triển khai: thường là hoạt động tinh chỉnh bình thường.
- **Phát hiện lỗi khiến mục tiêu Sprint có rủi ro:** Developers minh bạch và phối hợp xử lý, điều chỉnh kế hoạch; trao đổi với Product Owner khi ảnh hưởng phạm vi.
- **Xuất hiện nhu cầu mới không cần cho Sprint Goal hiện tại:** cân nhắc đưa vào Product Backlog và ưu tiên theo giá trị thay vì chen ngang mặc định.
- **Yêu cầu bảo mật bắt buộc:** xử lý theo mức độ rủi ro và thẩm quyền phù hợp, không chờ nghi thức họp nếu cần hành động khẩn.

Scrum không bắt buộc dùng một “Definition of Ready” cố định. Nhóm có thể thống nhất điều kiện cần để backlog item đủ hiểu trước khi chọn làm, nhưng không nên biến danh sách kiểm tra nội bộ thành quy tắc chính thức của Scrum hoặc thành cổng trì hoãn phản hồi.

### 10.3. Quản lý yêu cầu trong Kanban

Nhóm dùng Kanban có thể thể hiện những trạng thái như:

~~~text
Yeu cau moi
    |
    v
Can lam ro AC --> San sang --> Dang thuc hien --> Dang kiem chung --> Dat chinh sach hoan tat
                       |             |                   |
                       |             +-- Bi chan --------+
                       +-- Quy tac uu tien / gioi han WIP
~~~

Đây là một workflow minh họa, không phải một bảng Kanban bắt buộc. Nhóm cần chính sách rõ:

- Khi nào một mục có đủ thông tin để kéo vào thực hiện?
- Khi nào kết quả kiểm chứng cho phép chuyển sang hoàn tất?
- Trường hợp AC chưa rõ hoặc bằng chứng chưa đủ được đánh dấu thế nào?
- Ai tham gia giải quyết và khi nào cần ưu tiên tháo chặn?

Giới hạn WIP, work item age và cycle time giúp phát hiện công việc bị dừng lâu ở bước làm rõ hoặc kiểm chứng. **Đếm số ticket Done** mà không có chính sách hoàn tất đáng tin sẽ tạo cảm giác tiến độ ảo.

### 10.4. Ma trận truy vết đủ dùng

Với yêu cầu thông thường, một bảng nhỏ có thể là đủ:

| ID yêu cầu | Giá trị/nguồn | AC liên quan | Bằng chứng kiểm chứng | Trạng thái | Việc tiếp theo |
|---|---|---|---|---|---|
| US-FAV-01 | Học viên cần tìm lại khóa quan tâm | AC-01…AC-07 | Kết quả test theo build và môi trường | Minh họa: đạt sau khi sửa lỗi | Theo dõi phản hồi khi sử dụng |
| US-FAV-02 | Người dùng cần đồng bộ giữa thiết bị | Chưa làm rõ | Chưa có | Đang khám phá | Phỏng vấn và xác định kỳ vọng đồng bộ |

Điều quan trọng hơn số cột là **có thể đi từ một thay đổi yêu cầu đến những tiêu chí và kiểm chứng chịu ảnh hưởng**. Không sao chép thủ công những thông tin mà công cụ đã liên kết đáng tin nếu điều đó tạo thêm hai nguồn dễ lệch nhau.

## 11. Khi nào bằng chứng là “đủ” để ra quyết định?

Không có số lượng test hay tỷ lệ coverage chung bảo đảm mọi sản phẩm đều đúng. **Độ đầy đủ của bằng chứng phụ thuộc rủi ro và quyết định cần đưa ra.**

Đối với thay đổi giao diện nhỏ, thử nghiệm trên các tình huống chính cùng kiểm tra accessibility phù hợp có thể là đủ cho bước phát hành giới hạn. Đối với thanh toán, phân quyền, di chuyển dữ liệu hoặc xử lý thông tin nhạy cảm, cần kiểm chứng sâu hơn, kiểm soát phê duyệt theo quy định và khả năng quay lui khi phù hợp.

### 11.1. Câu hỏi đánh giá chất lượng bằng chứng

| Câu hỏi | Dấu hiệu tốt | Dấu hiệu cần xem lại |
|---|---|---|
| **Liên quan?** | Bằng chứng kiểm tra đúng AC và rủi ro | Chỉ kiểm tra chi tiết kỹ thuật không chứng minh hành vi mong đợi |
| **Mới và đúng phiên bản?** | Kết quả từ build/phiên bản định phát hành | Test pass ở nhánh hoặc phiên bản cũ |
| **Có thể tái hiện?** | Biết dữ liệu, điều kiện và kết quả mong đợi | “Tôi từng bấm thấy chạy” nhưng không có ngữ cảnh |
| **Đủ đại diện?** | Môi trường và tình huống gần rủi ro thực | Chỉ thử trên local với mock, trong khi lỗi có thể nằm ở tích hợp |
| **Bao phủ tình huống quan trọng?** | Có happy path, lỗi và trường hợp trái quyền quan trọng | Chỉ có một luồng thành công |
| **Độc lập với kết luận mong muốn?** | Test kiểm tra hành vi thực, không mã hóa kết quả giả | Test luôn pass vì stub trả đúng dữ liệu định sẵn |
| **Minh bạch giới hạn?** | Có danh sách điều chưa kiểm chứng và rủi ro còn lại | Báo “đã kiểm thử đầy đủ” mà không biết đã thử gì |
| **Đúng thẩm quyền?** | Người có trách nhiệm được cung cấp thông tin cần thiết để quyết định | Người không có quyền tự bỏ qua kiểm soát bắt buộc |

### 11.2. Các loại bằng chứng không nên thay thế cho nhau

- **Unit tests pass** không thay thế kiểm tra truy cập trái quyền ở giao diện hệ thống thực.
- **Ảnh chụp màn hình** không chứng minh dữ liệu còn sau phiên đăng nhập mới.
- **Tỷ lệ test coverage cao** không đồng nghĩa các trường hợp quan trọng đã được kiểm tra.
- **Người dùng thích bản prototype** không chứng minh hệ thống tích hợp đã hoạt động.
- **Increment đạt DoD** không tự chứng minh tỷ lệ người dùng hoàn thành tác vụ tăng.
- **Một biểu đồ outcome tăng** không tự chứng minh thay đổi cụ thể gây ra mức tăng nếu còn yếu tố nhiễu.

Hãy giữ rõ ranh giới giữa **chứng minh hành vi đúng**, **chứng minh chất lượng**, **nhận phản hồi**, và **đánh giá giá trị thực tế**.

### 11.3. Chấp nhận có điều kiện và vấn đề còn mở

Trong một số sản phẩm, tổ chức có cơ chế chấp nhận rủi ro có điều kiện. Nếu một phép kiểm tra chưa thể hoàn tất do môi trường thử thiếu dữ liệu, không nên ghi PASS. Cần ghi rõ **NOT RUN/BLOCKED**, lý do, tác động và người có quyền quyết định xử lý.

Nếu điều kiện đó là một phần bắt buộc của DoD trong Scrum, Increment **chưa được xem là Done** cho tới khi đáp ứng DoD. Việc có ai đó “đồng ý tạm thời” không tự động làm thay đổi sự thật kiểm chứng hoặc quy tắc chất lượng. Khi cần thay đổi chuẩn áp dụng, phải tuân theo cơ chế trách nhiệm của nhóm/tổ chức, không lặng lẽ sửa báo cáo.

## 12. Quy trình thực hành 10 bước cho một backlog item

Một quy trình ngắn, có thể điều chỉnh theo độ phức tạp:

1. **Xác định nhu cầu:** ghi ai gặp vấn đề gì, tại sao công việc có giá trị.
2. **Nêu đầu ra dự kiến:** chọn một hành vi phần mềm đủ nhỏ để giao và kiểm tra.
3. **Làm rõ phạm vi:** đối tượng, điều kiện, phụ thuộc và giả định còn mở.
4. **Viết AC:** mô tả hành vi thành công, thất bại và ràng buộc quan trọng bằng ngôn ngữ quan sát được.
5. **Trao đổi liên vai trò:** mời nghiệp vụ, phát triển, kiểm thử và chuyên gia liên quan nêu ví dụ, phản ví dụ.
6. **Lập đường kiểm chứng:** xác định AC nào cần unit/API/integration/E2E/manual/accessibility/performance/security check.
7. **Xây và kiểm tra theo lát cắt:** kiểm chứng sớm, không đợi tất cả thành phần hoàn thành mới tích hợp.
8. **Ghi bằng chứng:** kết quả thực tế, build, môi trường, dữ liệu, giới hạn, lỗi và trạng thái sửa/chạy lại.
9. **Xem AC và DoD:** phân biệt AC đã đạt với điều kiện chất lượng chung còn thiếu; chỉ báo Done khi đạt chuẩn áp dụng.
10. **Học từ sử dụng:** thu phản hồi của người dùng, đánh giá outcome, cập nhật backlog/AC/test khi có giả thuyết hoặc yêu cầu mới.

### 12.1. Mẫu ngắn dùng ngay trong backlog item

~~~text
ID / TEN:
NGUOI DUNG VA VAN DE:
GIA TRI MONG MUON:

PHAM VI:
  Co trong lat cat nay:
  Chua co / can xem lai:

AC:
  AC-01:
  AC-02:
  AC-03:

RUI RO / RANG BUOC:
  Bao mat, du lieu, accessibility, hieu nang, phu thuoc...

KE HOACH KIEM CHUNG:
  AC-01 -> test / phuong phap / moi truong
  AC-02 -> test / phuong phap / moi truong
  AC-03 -> test / phuong phap / moi truong

BANG CHUNG SAU KHI CHAY:
  Build / version:
  Ket qua thuc te:
  PASS / FAIL / NOT RUN:
  Duong dan bao cao / loi:
  Gioi han kiem chung:

DEFINITION OF DONE:
  Da dat / Chua dat va ly do:

PHAN HOI / OUTCOME:
  Du lieu quan sat:
  Dieu chua the ket luan:

QUYET DINH TIEP THEO:
  Giu / sua / mo rong / dung / thu them:
~~~

Không cần điền đủ mọi dòng cho một thay đổi nhỏ. Nội dung có thể nằm trong ticket, bảng kiểm thử hoặc kết quả CI miễn liên kết dễ tra ngược. Với rủi ro cao, các trường cần chi tiết và được phê duyệt theo quy trình thích hợp.

## 13. Những lỗi thường gặp và cách sửa

### Lỗi 1: AC chỉ lặp lại câu user story

“Là học viên, tôi muốn lưu yêu thích” và AC “Học viên có thể lưu yêu thích” không làm rõ kết quả kiểm tra.

**Sửa:** Nêu sau khi lưu điều gì xảy ra, dữ liệu tồn tại qua phiên ra sao, xử lý lỗi và quyền truy cập thế nào.

### Lỗi 2: Tiêu chí dùng từ không đo được

“Trang tải nhanh, hoạt động ổn định, giao diện thân thiện” không có điều kiện đo.

**Sửa:** Làm rõ bối cảnh, ngưỡng và cách đánh giá phù hợp; không nhất thiết phải biến mọi nhận định định tính thành một con số duy nhất.

### Lỗi 3: Viết AC sau khi hoàn tất code để hợp thức hóa

Nếu tiêu chí được viết theo đúng những gì code tình cờ làm, nhóm có thể bỏ qua nhu cầu ban đầu.

**Sửa:** Thảo luận các ví dụ nghiệp vụ trước hoặc sớm trong khi phát triển; khi thay đổi AC, ghi lý do và kiểm tra lại với người chịu trách nhiệm.

### Lỗi 4: Đếm test case như bằng chứng chất lượng

Một trăm test case chưa chạy không hơn một nhóm kiểm tra phù hợp thực sự có kết quả khi ra quyết định.

**Sửa:** Theo dõi trạng thái chạy, phiên bản, điều kiện và các rủi ro được bao phủ.

### Lỗi 5: Một bài test E2E khổng lồ cho mọi hành vi

Một kịch bản quá dài dễ khó chẩn đoán khi thất bại, chậm và khó bảo trì.

**Sửa:** Phân lớp kiểm thử theo hành vi và rủi ro; chỉ dùng E2E cho các luồng cần chứng minh toàn hệ thống phối hợp.

### Lỗi 6: Chỉ kiểm tra trường hợp thành công

Hệ thống chạy đẹp khi dữ liệu hợp lệ nhưng có thể lỗi nghiêm trọng khi người dùng thử lại, mất mạng hoặc truy cập trái quyền.

**Sửa:** Dùng phản ví dụ và tình huống biên có ý nghĩa; ưu tiên lỗi có tác động lớn hoặc khả năng xảy ra cao.

### Lỗi 7: AC thay đổi nhưng test không thay đổi

Tiêu chí đã yêu cầu dữ liệu sau đăng nhập mới, test vẫn chỉ kiểm tra nút đổi màu.

**Sửa:** Khi yêu cầu/AC đổi, xem lại liên kết tới test, dữ liệu, môi trường và bằng chứng cần chạy lại.

### Lỗi 8: Đã pass AC thì tự động đóng Done

Một chức năng có thể đạt hành vi nghiệp vụ nhưng chưa đạt tiêu chuẩn bảo mật, kiểm thử hồi quy hoặc tích hợp theo DoD.

**Sửa:** Kiểm tra AC và DoD như hai lớp bổ sung; chỉ công nhận Increment Done khi điều kiện áp dụng được đáp ứng.

### Lỗi 9: Nhầm nghiệm thu kỹ thuật với thành công sản phẩm

Người dùng có thể lưu khóa đúng nhưng không tìm thấy danh sách lưu. Test đạt, outcome vẫn chưa đạt.

**Sửa:** Tiếp tục quan sát người dùng và phản hồi thực tế sau kiểm chứng; điều chỉnh giải pháp theo vấn đề.

### Lỗi 10: Đòi hỏi ma trận truy vết quá nặng cho mọi ticket

Một nhóm mất nhiều giờ chép thông tin qua nhiều biểu mẫu, dữ liệu dễ lệch và phản hồi chậm.

**Sửa:** Giữ liên kết có ích cho quyết định, tái sử dụng đường dẫn trong công cụ hiện có, tăng chi tiết khi rủi ro/tuân thủ đòi hỏi.

## 14. Bài tập vận dụng

### Bài tập A — Viết lại tiêu chí chấp nhận

Yêu cầu: “**Là người dùng, tôi muốn nhận thông báo khi thanh toán xong.**”

Đội hiện có AC duy nhất: “Hệ thống gửi thông báo nhanh và chính xác.”

**Yêu cầu bài tập:** Viết lại ít nhất bốn AC có thể kiểm tra, trong đó có đường thành công, trường hợp giao dịch thất bại hoặc chưa xác định, hành vi gửi lặp và bảo vệ thông tin. Nêu phương pháp kiểm chứng phù hợp cho mỗi AC.

<details>
<summary>Gợi ý đáp án</summary>

Có thể viết: khi giao dịch được xác nhận thành công bởi nguồn trạng thái tin cậy, người mua nhìn thấy trạng thái đúng; khi giao dịch thất bại hoặc chờ xử lý, không gửi thông báo “đã thanh toán” giả; sự kiện gửi lặp không làm hệ thống tạo nhiều đơn hoặc trạng thái sai; thông báo không để lộ dữ liệu thanh toán nhạy cảm; khi dịch vụ gửi thông báo tạm thời lỗi, trạng thái thanh toán vẫn được lưu đúng và có cơ chế xử lý phù hợp. Kiểm chứng bằng integration/contract tests, kiểm tra lỗi và thao tác lặp, đánh giá bảo mật theo chính sách, kiểm tra trạng thái UI. Ngưỡng “nhanh” phải được định nghĩa theo bối cảnh thực tế trước khi kiểm chứng.

</details>

### Bài tập B — Tìm lỗ hổng trong bằng chứng

Một nhóm trình bằng chứng cho AC “danh sách yêu thích vẫn còn khi đăng nhập lại”: ảnh chụp màn hình có trái tim màu đỏ và một unit test kiểm tra hàm đổi màu nút. Cả hai đều thành công.

**Yêu cầu bài tập:** Giải thích vì sao chưa đủ. Đề xuất hai phép kiểm tra bổ sung và những thông tin cần lưu trong bằng chứng.

<details>
<summary>Gợi ý đáp án</summary>

Ảnh và unit test chỉ chứng minh trạng thái UI hoặc logic cục bộ; chưa chứng minh dữ liệu được lưu theo tài khoản và có thể đọc sau phiên mới. Cần kiểm tra UI–API–database với tài khoản thử, sau đó đăng xuất/đăng nhập lại và kiểm tra danh sách. Có thể bổ sung trường hợp dùng tài khoản khác để kiểm tra dữ liệu riêng. Bằng chứng cần có AC, build, môi trường, dữ liệu thử, expected/actual, trạng thái pass/fail và giới hạn đã kiểm chứng.

</details>

### Bài tập C — Nhận diện AC và DoD

Cho các phát biểu:

1. “Liên kết đặt lại mật khẩu đã hết hạn không còn dùng được.”
2. “Mã được tích hợp vào nhánh chính và các kiểm thử phù hợp đã chạy đạt.”
3. “Sau khi đổi mật khẩu, người dùng có thể đăng nhập bằng mật khẩu mới.”
4. “Các yêu cầu bảo mật áp dụng cho sản phẩm đã được kiểm tra theo quy trình chung.”

**Yêu cầu bài tập:** Chỉ ra phát biểu nào phù hợp làm AC của user story đặt lại mật khẩu, phát biểu nào phù hợp làm tiêu chuẩn DoD chung, và giải thích vì sao hai loại đều cần thiết.

<details>
<summary>Gợi ý đáp án</summary>

1 và 3 là AC về hành vi cụ thể của chức năng đặt lại mật khẩu. 2 và 4 có thể thuộc DoD chung nếu đó là tiêu chuẩn chất lượng của sản phẩm. Đội cần AC để biết chức năng giải quyết đúng hành vi nào, và cần DoD để bảo đảm Increment đạt tiêu chuẩn chất lượng chung. Một tình huống bảo mật cụ thể cũng có thể được nêu đồng thời ở AC và được kiểm tra trong khung DoD khi phù hợp.

</details>

### Bài tập D — Phân loại PASS, FAIL, NOT RUN

Một CI report có ba mục:

- Test đăng nhập lại: **PASS** trên build A.
- Test phân quyền: **SKIPPED** vì thiếu tài khoản kiểm thử.
- Test lỗi dịch vụ lưu: **FAIL** trên build A.

Ngày hôm sau đội sửa lỗi và chuẩn bị phát hành build B nhưng chưa chạy pipeline mới.

**Yêu cầu bài tập:** Có thể báo “tất cả AC đạt” không? Đội cần làm gì trước khi kết luận, và phải nêu giới hạn nào?

<details>
<summary>Gợi ý đáp án</summary>

Không. Trên build A còn một kiểm tra thất bại và một kiểm tra chưa chạy; kết quả của build A cũng không tự xác nhận build B. Đội cần sửa điều kiện chạy test phân quyền, kiểm chứng lại lỗi dịch vụ, chạy các test liên quan và hồi quy phù hợp trên build B, kiểm tra các tiêu chí DoD áp dụng. Báo cáo phải giữ phân biệt PASS/FAIL/NOT RUN và ghi rõ những giới hạn chưa được kiểm chứng.

</details>

### Bài tập E — Yêu cầu thay đổi giữa Sprint

Trong Sprint, người dùng phản hồi muốn đồng bộ danh sách yêu thích tức thời giữa hai thiết bị. Sprint Goal hiện tại là “học viên có thể lưu và tìm lại khóa sau khi đăng nhập lại”. Một stakeholder đề nghị lập tức thêm đồng bộ nhiều thiết bị vào AC hiện tại.

**Yêu cầu bài tập:** Nhóm cần làm rõ những điều gì? Ai tham gia quyết định? Khi nào nên đổi AC hiện tại, khi nào nên tạo backlog item mới?

<details>
<summary>Gợi ý đáp án</summary>

Làm rõ giá trị, mức độ cần thiết để đạt Sprint Goal, rủi ro dữ liệu, độ trễ đồng bộ và phụ thuộc. Developers đánh giá ảnh hưởng kỹ thuật, kế hoạch và DoD; Product Owner cân nhắc giá trị/ưu tiên và trao đổi phạm vi khi cần. Nếu yêu cầu mới là phần không thể thiếu của mục tiêu đang theo đuổi và còn khả thi, nhóm có thể thảo luận điều chỉnh tiêu chí và kế hoạch. Nếu đó là khả năng mở rộng không thiết yếu, nên ghi thành Product Backlog Item để ưu tiên sau. Không tự ý tăng phạm vi rồi hạ DoD hoặc làm mất Sprint Goal.

</details>

### Bài tập F — Test đạt nhưng outcome chưa đạt

Nhóm có đầy đủ bằng chứng lưu và xem lại danh sách yêu thích đúng yêu cầu. Tuy nhiên, quan sát người dùng cho thấy họ vẫn mất nhiều thời gian tìm lại khóa vì lối vào danh sách khó thấy.

**Yêu cầu bài tập:** Kết luận nào thuộc verification, kết luận nào thuộc validation? Đề xuất một giả thuyết điều chỉnh và cách kiểm chứng.

<details>
<summary>Gợi ý đáp án</summary>

Verification đã có thể xác nhận các hành vi lưu và xem lại đúng theo AC trong phạm vi được thử. Validation cho thấy giải pháp chưa giúp người dùng tìm lại khóa thuận tiện như mong muốn. Có thể giả thuyết rằng việc hiển thị mục “Đã lưu” rõ hơn sẽ giảm thời gian tìm lại. Kiểm chứng bằng quan sát tác vụ với nhóm người dùng phù hợp và theo dõi tỷ lệ hoàn tất/thời gian tìm lại sau khi triển khai có kiểm soát; đồng thời kiểm tra guardrail về khả năng truy cập và phân quyền.

</details>

## 15. Checklist tự đánh giá trước khi kết luận một yêu cầu đã hoàn tất

Với mỗi câu, hãy tìm bằng chứng hoặc nêu rõ điều chưa được kiểm tra:

1. Yêu cầu có mô tả **người dùng, nhu cầu và phạm vi** đủ rõ không?
2. Mỗi AC quan trọng có thể tạo tình huống và xác định kết quả đúng/sai không?
3. Các trường hợp lỗi, dữ liệu xấu, truy cập trái quyền hoặc thao tác lặp phù hợp đã được thảo luận chưa?
4. Các yêu cầu phi chức năng và nghĩa vụ bắt buộc có được đưa vào AC/DoD/chính sách có thể kiểm chứng không?
5. Những người hiểu nghiệp vụ, phát triển và kiểm thử có cùng hiểu ví dụ về hành vi mong đợi không?
6. Có cách truy ngược từ AC đến phép kiểm tra và kết quả thực tế không?
7. Kết quả kiểm tra có gắn **đúng phiên bản, môi trường và điều kiện** dự kiến không?
8. Test bị skip, không ổn định, thất bại hoặc còn điều kiện chưa kiểm tra có được thể hiện trung thực không?
9. Bằng chứng có chứa dữ liệu nhạy cảm hoặc thông tin cá nhân không cần thiết không?
10. Có phân biệt rõ AC đã đạt và DoD chung đã đạt hay chưa?
11. Khi yêu cầu đổi, test và bằng chứng liên quan có được xem lại không?
12. Khi phần mềm đạt tiêu chí kỹ thuật, nhóm có cách nhận phản hồi để xem người dùng thực sự có đạt mục tiêu không?
13. Có quyết định tiếp theo rõ ràng dựa trên bằng chứng, thay vì chỉ đổi trạng thái ticket không?

Một nhóm trả lời được những câu này bằng ví dụ cụ thể sẽ giảm nguy cơ tiến độ ảo và trao đổi thiếu căn cứ. Không nhất thiết mọi câu được thể hiện thành một biểu mẫu mới; điều cốt lõi là **thông tin cần thiết thật sự có sẵn để kiểm tra và quyết định**.

## 16. Ghi nhớ

- **Yêu cầu nói điều cần đạt; tiêu chí chấp nhận mô tả điều kiện để biết hành vi đó đã đúng; bằng chứng kiểm chứng cho thấy kết quả thực tế sau khi kiểm tra.** Ba lớp phải nối với nhau.
- **User story là điểm bắt đầu của trao đổi**, không phải bản mô tả đầy đủ. Cần làm rõ phạm vi, quy tắc nghiệp vụ, tình huống lỗi và ràng buộc quan trọng.
- **Tiêu chí chấp nhận và Definition of Done bổ sung cho nhau.** Một Increment trong Scrum chỉ được công nhận Done khi đạt chuẩn DoD áp dụng, dù các AC riêng lẻ đã pass.
- **Không coi test case, dấu tích xanh hoặc ảnh demo là bằng chứng vô điều kiện.** Phải biết test kiểm tra gì, chạy trên phiên bản nào, môi trường nào và còn giới hạn gì.
- **Kiểm chứng đúng yêu cầu vẫn khác xác nhận giá trị người dùng.** Tính năng có thể hoạt động chuẩn nhưng không giải quyết vấn đề; phản hồi thực tế giúp điều chỉnh giải pháp.
- **Yêu cầu có thể thích ứng nhưng không được tùy tiện sửa tiêu chuẩn hoàn thành.** Khi thay đổi, hãy cập nhật tiêu chí, phép kiểm chứng, bằng chứng liên quan và quyết định backlog minh bạch.
- **Scrum, Kanban và XP đều hỗ trợ vòng phản hồi:** làm rõ giá trị, tập trung Increment, quản lý dòng công việc và tạo bằng chứng kỹ thuật sớm, đáng tin.

Khi chuẩn bị đánh dấu một hạng mục là hoàn tất, hãy hỏi: **“Yêu cầu này giúp ai làm được điều gì? Những điều kiện nào phải đúng? Chúng ta đã quan sát bằng chứng gì trên phiên bản nào? Và phản hồi tiếp theo có thể thay đổi quyết định nào?”** Câu trả lời rõ ràng giúp đội giao sản phẩm tăng dần, thích ứng nhanh và duy trì chất lượng.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development — Principles](https://agilemanifesto.org/principles.html): giao phần mềm hoạt động được, hợp tác và chấp nhận thay đổi.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Backlog, Sprint Goal, Increment, Definition of Done và kiểm tra/thích ứng trong Scrum.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): biểu diễn các ví dụ hành vi bằng Given/When/Then.
- [Agile Alliance — Acceptance Criteria](https://agilealliance.org/glossary/acceptance-criteria/): khái niệm tiêu chí chấp nhận và cách sử dụng trong phát triển Agile.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): chính sách dòng công việc, quản lý WIP và phép đo dòng công việc.
