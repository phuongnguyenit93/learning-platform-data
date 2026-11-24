# Phần mềm hoạt động được so với tài liệu đầy đủ

## 1. Giá trị thứ hai của Agile nói điều gì?

Một trong bốn giá trị của **Tuyên ngôn Agile (Agile Manifesto)** là:

> **Working software over comprehensive documentation** — Ưu tiên phần mềm hoạt động được hơn tài liệu đầy đủ.

Đây là một **ưu tiên khi phải lựa chọn**, không phải lời kêu gọi bỏ tài liệu. Tuyên ngôn Agile khẳng định những yếu tố ở vế phải vẫn có giá trị, nhưng coi trọng các yếu tố ở vế trái hơn. Vì vậy, nhóm phát triển nên dùng phần mềm thực sự chạy được, đáp ứng nhu cầu và được kiểm chứng làm bằng chứng chính cho tiến độ; đồng thời tạo và bảo trì **những tài liệu đủ dùng, đúng lúc, đáng tin cậy**.

Giá trị này đặc biệt quan trọng trong phát triển phần mềm thích ứng: nhu cầu thay đổi, phản hồi đến không đồng đều, và giải pháp được học dần qua các lần giao sản phẩm. Một tài liệu dài có thể ghi lại nhiều giả định, nhưng **chỉ khi sản phẩm hoạt động thì người dùng và nhóm mới kiểm tra được phần lớn các giả định về hành vi thực tế**.

Hãy hình dung hai nhóm cùng xây hệ thống đặt lịch:

- **Nhóm A** hoàn thành một bộ đặc tả rất chi tiết, sơ đồ mọi màn hình, bảng tiến độ đẹp, nhưng chưa thể đặt thành công một cuộc hẹn nào.
- **Nhóm B** thống nhất phạm vi nhỏ, ghi lại những quy tắc quan trọng, xây dựng và kiểm thử được luồng xem giờ trống → chọn giờ → xác nhận. Nhóm B đưa chức năng cho người dùng thử và phát hiện họ cần thấy múi giờ rõ hơn.

Nhóm B có bằng chứng mạnh hơn rằng giải pháp đang tiến gần mục tiêu, dù tài liệu có thể ngắn hơn. Tuy nhiên, nếu nhóm B không ghi lại quy tắc tránh đặt trùng, cách khôi phục dữ liệu hoặc hợp đồng tích hợp cần thiết, sản phẩm có thể khó vận hành và mở rộng. **Agile không đánh đổi khả năng bảo trì, an toàn hoặc tuân thủ để lấy một màn trình diễn chạy được.**

Trong module **AGILE_DEVELOPMENT**, giá trị này kết nối trực tiếp với việc giao phần tăng trưởng nhỏ, nhận phản hồi sớm, quản lý backlog và cải tiến liên tục. Scrum, Kanban hay các thực hành kỹ thuật của XP có thể hỗ trợ theo những cách khác nhau, nhưng không phương pháp nào biến số trang tài liệu thành thước đo chính của giá trị sản phẩm.

## 2. Vì sao “phần mềm hoạt động được” là bằng chứng mạnh?

### 2.1. Tài liệu mô tả dự định; phần mềm cho thấy hành vi

Một đặc tả có thể viết rằng “người dùng đặt lịch dễ dàng”, nhưng câu đó chưa cho biết:

- Khi có hai người cùng chọn một giờ trống, hệ thống xử lý ra sao?
- Người dùng có hiểu thông báo lỗi không?
- Dữ liệu có được lưu đúng và khôi phục an toàn khi có sự cố không?
- Giao diện có sử dụng được trên thiết bị và trình duyệt mục tiêu không?
- Phản hồi thực tế có xác nhận rằng đây là chức năng họ cần không?

Một phần mềm chạy được có thể được thử nghiệm để trả lời các câu hỏi đó. Việc **chạy và kiểm chứng** giúp nhóm phát hiện khoảng cách giữa điều đã viết và điều thực sự xảy ra.

Nguyên tắc Agile còn nhấn mạnh **phần mềm hoạt động được là thước đo chính của tiến độ**. “Chính” không có nghĩa là “duy nhất”: nhóm vẫn cần theo dõi giá trị sử dụng, độ tin cậy, rủi ro, mức hài lòng và khả năng duy trì sản phẩm. Ví dụ, phần mềm hoạt động nhưng không giải quyết vấn đề của khách hàng vẫn chưa đạt kết quả kinh doanh mong muốn.

### 2.2. “Hoạt động được” cần được định nghĩa cụ thể

Không nên gọi một tính năng là hoàn tất chỉ vì giao diện hiển thị đẹp hoặc đoạn mã chạy trên máy cá nhân. Cần xét hành vi sản phẩm trong **phạm vi đã thống nhất** và mức chất lượng phù hợp với rủi ro:

| Tiêu chí | Câu hỏi kiểm chứng | Ví dụ với chức năng đặt lịch |
| --- | --- | --- |
| **Đúng hành vi** | Chức năng đáp ứng các tiêu chí chấp nhận đã thống nhất chưa? | Người dùng chỉ xác nhận được một giờ còn trống. |
| **Tích hợp** | Giao diện, API, xử lý nghiệp vụ và dữ liệu phối hợp được chưa? | Cuộc hẹn tạo từ giao diện xuất hiện đúng trong hệ thống lưu trữ. |
| **Kiểm thử** | Đường đi chính, lỗi phổ biến và trường hợp quan trọng đã được xác minh chưa? | Hai yêu cầu đồng thời không tạo hai lịch trùng vượt quá sức chứa. |
| **Chất lượng cần thiết** | Bảo mật, hiệu năng, khả năng tiếp cận và độ tin cậy đã phù hợp với phạm vi sử dụng chưa? | Người không có quyền không xem được lịch riêng tư của người khác. |
| **Khả năng sử dụng hoặc phát hành** | Phần mềm đủ hoàn chỉnh để kiểm tra bởi người dùng thích hợp hoặc đưa vào sử dụng theo quy trình của nhóm chưa? | Người dùng thử hoàn tất một cuộc hẹn từ đầu đến cuối. |
| **Bằng chứng phản hồi** | Nhóm thu được thông tin nào để quyết định bước kế tiếp? | Người dùng thử cho biết họ thường hiểu nhầm múi giờ. |

Mức kiểm chứng cần **tương xứng với rủi ro và giai đoạn**. Một nguyên mẫu giao diện có thể hữu ích để khám phá nhu cầu, nhưng phải gọi đúng là **nguyên mẫu**, không đánh đồng với một phần tăng trưởng hoàn tất có thể vận hành. Với phần mềm y tế, thanh toán hoặc điều khiển thiết bị, điều kiện để coi là đủ an toàn và có thể phát hành sẽ nghiêm ngặt hơn nhiều.

### 2.3. Phân biệt demo, Increment, triển khai và giá trị

Bốn khái niệm thường dễ nhầm:

| Khái niệm | Ý nghĩa | Điều chưa được bảo đảm |
| --- | --- | --- |
| **Demo** | Trình bày một hành vi hoặc tiến độ có thể quan sát. | Chưa chắc đã qua mọi kiểm thử hoặc đáp ứng chuẩn hoàn tất. |
| **Increment** | Phần sản phẩm tăng thêm, được tích hợp với phần trước và đáp ứng Definition of Done. | Chưa nhất thiết đã được phát hành cho mọi người dùng. |
| **Deployment/Release** | Đưa phiên bản tới một môi trường/nhóm người dùng theo kế hoạch. | Chưa chắc sản phẩm mang lại kết quả người dùng mong đợi. |
| **Value/Outcome** | Lợi ích hoặc thay đổi thực tế từ việc sử dụng sản phẩm. | Cần bằng chứng sử dụng hoặc đo lường để xác nhận. |

Trong **Scrum**, một Increment phải dùng được và đáp ứng **Definition of Done (DoD)**; một Sprint có thể tạo nhiều Increment và việc phát hành có thể diễn ra trước khi Sprint kết thúc. Câu nói “code xong là Done” dễ làm sai lệch tiến độ nếu phần việc vẫn đang chờ kiểm thử, tích hợp hoặc xử lý lỗi quan trọng.

## 3. “Tài liệu đầy đủ” có vấn đề ở đâu?

Vấn đề nằm ở việc cố tạo **tài liệu toàn diện ngay từ đầu cho những điều chưa được kiểm chứng**, hoặc dùng số lượng tài liệu như bằng chứng thay cho phần mềm hoàn tất.

### 3.1. Tài liệu có thể tạo cảm giác chắc chắn giả

Một yêu cầu rất chi tiết vẫn có thể dựa trên giả định sai về nhu cầu người dùng. Khi học được điều mới, nhóm phải sửa cả giải pháp và các trang đặc tả tương ứng. Tài liệu càng đồ sộ và trùng lặp, chi phí cập nhật và nguy cơ mâu thuẫn càng lớn.

Ví dụ, nhóm mô tả 25 trạng thái đặt lịch và 40 màn hình trước khi kiểm tra người dùng có muốn tự đặt lịch hay không. Một tuần thử nghiệm có thể cho thấy điểm đau lớn nhất là **không biết giờ trống**, khiến nhiều luồng được đặc tả không còn ưu tiên.

### 3.2. Tài liệu không thay cho kiểm chứng

Những phát biểu như “hệ thống xử lý tốt yêu cầu đồng thời” hoặc “quá trình thanh toán an toàn” cần bằng chứng phù hợp: kiểm thử tự động, kiểm tra tải, review bảo mật, diễn tập phục hồi, kết quả vận hành hoặc đánh giá có thẩm quyền theo bối cảnh. Việc mô tả một tính chất không chứng minh tính chất đó tồn tại.

### 3.3. Tài liệu không được bảo trì dễ trở thành rủi ro

Một trang hướng dẫn API ghi tham số cũ có thể làm nhóm tích hợp triển khai sai. Một runbook thiếu bước xử lý lỗi mới có thể làm kéo dài sự cố. Vì vậy, **ít tài liệu nhưng đúng, tìm được và có người bảo trì** thường hữu ích hơn nhiều trang không còn khớp với sản phẩm.

Điều đó không có nghĩa là chỉ ghi vài câu trong chat. Với quyết định kiến trúc, ràng buộc pháp lý hoặc quy trình vận hành cần truy vết, tài liệu có cấu trúc, được phê duyệt và lưu giữ đúng cách là một phần thiết yếu của sản phẩm và quá trình làm việc.

## 4. Tài liệu nào vẫn cần thiết trong Agile?

Một tài liệu nên trả lời được ít nhất một câu hỏi thực tế: **ai cần dùng nó, để quyết định hoặc làm việc gì, cần đúng trong bao lâu, và điều gì xảy ra nếu nó thiếu hoặc sai?**

| Loại tài liệu | Mục đích | Cách giữ gọn và hữu ích |
| --- | --- | --- |
| **Mục tiêu sản phẩm và backlog** | Thống nhất vấn đề, thứ tự ưu tiên và kết quả mong đợi. | Mô tả ngắn người hưởng lợi, giá trị và bằng chứng; cập nhật theo phản hồi. |
| **User story và acceptance criteria** | Xác nhận hành vi cần xây dựng, các tình huống đúng/sai. | Dùng ví dụ cụ thể, điều kiện có thể kiểm thử thay vì văn xuôi dài và mơ hồ. |
| **Hợp đồng API và mô hình dữ liệu** | Giúp các thành phần/nhóm tích hợp ổn định. | Quản lý phiên bản, kiểm tra tự động khi có thể, cập nhật cùng thay đổi giao diện API. |
| **Quyết định kiến trúc (ADR)** | Ghi lại bối cảnh, lựa chọn, lý do và đánh đổi của quyết định khó đảo ngược. | Một quyết định một bản ghi ngắn; liên kết tài liệu thay vì sao chép. |
| **README và hướng dẫn phát triển** | Giúp người mới cài đặt, chạy và kiểm thử hệ thống. | Ghi lệnh thực tế, yêu cầu môi trường và lỗi thường gặp; kiểm tra lại định kỳ. |
| **Runbook, giám sát và phục hồi** | Cho phép vận hành, xử lý sự cố và khôi phục dịch vụ. | Có quy trình xác minh và người chịu trách nhiệm; diễn tập nếu rủi ro lớn. |
| **Bảo mật, pháp lý, kiểm toán** | Thể hiện kiểm soát, phê duyệt, truy vết và nghĩa vụ tuân thủ. | Đáp ứng yêu cầu bắt buộc của ngành/tổ chức; lưu bằng chứng có thể kiểm tra. |
| **Hướng dẫn người dùng và hỗ trợ** | Giúp người dùng sử dụng tính năng đúng và tự giải quyết vấn đề. | Tập trung thao tác thực tế, hình ảnh cần thiết và thông tin phiên bản. |
| **Kiểm thử tự động và ví dụ thực thi** | Kiểm chứng hành vi, phát hiện hồi quy và làm rõ kỳ vọng. | Viết dễ đọc, đáng tin cậy, thực thi trong quy trình tích hợp liên tục. |

**Kiểm thử không thay thế mọi tài liệu.** Test cho biết một hành vi được kỳ vọng và đã được kiểm tra; nó thường không giải thích đầy đủ **vì sao** nhóm chọn kiến trúc, **cách** khôi phục sau sự cố hoặc **ai** có quyền chấp thuận thay đổi.

Tương tự, tài liệu không nhất thiết luôn là một tệp Word dài. Nó có thể là sơ đồ kiến trúc được bảo trì, trang hướng dẫn, hợp đồng OpenAPI, ví dụ hành vi, bản ghi quyết định hoặc một checklist được quản lý phiên bản. **Hình thức nên theo người sử dụng và mục đích.**

### 4.1. Mức tài liệu tối thiểu hữu ích không cố định

Với một thử nghiệm giao diện ít rủi ro, nhóm có thể chỉ cần mục tiêu, giả thuyết, cách đo và lưu ý về dữ liệu giả. Với cơ chế chuyển tiền, nhóm cần nhiều hơn: quy tắc nghiệp vụ, mô hình quyền truy cập, yêu cầu bảo mật, dấu vết phê duyệt, cách hoàn tác, kiểm thử và quy trình ứng phó sự cố.

Sự khác biệt đến từ **hệ quả khi sai**, không phải sở thích viết ít hay nhiều. “Đủ dùng” phải được xác định theo người đọc, yêu cầu pháp lý, chi phí chuyển giao và mức rủi ro, chứ không phải một số trang mặc định cho mọi dự án.

### 4.2. Tài liệu sống và tài liệu tại thời điểm quyết định

Có hai nhu cầu khác nhau:

- **Tài liệu sống (living documentation):** phải phản ánh hệ thống hiện hành, ví dụ cách gọi API, cách chạy test, quy trình triển khai. Khi hành vi đổi, tài liệu liên quan cần đổi cùng.
- **Hồ sơ quyết định hoặc bằng chứng lịch sử:** cần giữ lại bối cảnh tại thời điểm quyết định, ví dụ lý do chọn một phương án, phê duyệt tuân thủ hoặc kết quả kiểm tra trong kỳ. Không được tự ý “viết lại lịch sử” để khớp với bản mới.

Phân biệt hai loại giúp nhóm vừa tránh tài liệu lỗi thời, vừa duy trì khả năng truy vết.

## 5. Ví dụ xuyên suốt: phát triển chức năng đăng ký khóa học

Giả sử nhóm xây một nền tảng học trực tuyến. Học viên muốn **đăng ký khóa học còn chỗ** và biết ngay kết quả. Nhóm đang phân vân giữa hai cách:

**Cách thiên về tài liệu trước:** viết đặc tả toàn bộ quy trình đăng ký, hủy, hoàn tiền, ưu đãi, danh sách chờ, thông báo đa kênh và nhiều sơ đồ chi tiết trước khi chạy được luồng nào.

**Cách theo giá trị Agile:** thống nhất các quy tắc quan trọng, chọn lát cắt giá trị đầu tiên và nhanh chóng tạo một hành vi chạy được để kiểm tra.

### 5.1. Bắt đầu bằng mục tiêu, giả định và câu chuyện người dùng

**Mục tiêu:** học viên đủ điều kiện có thể đăng ký khóa học đang mở và nhận xác nhận đáng tin cậy.

**Giả định cần kiểm chứng:** một luồng đăng ký ngắn sẽ giúp học viên hoàn tất nhanh hơn; người dùng hiểu trạng thái “còn chỗ”, “đã hết chỗ” và “đăng ký thành công”.

**User story:**

> Là một học viên đã đăng nhập, tôi muốn đăng ký một khóa học còn chỗ để có thể bắt đầu học mà không cần liên hệ nhân viên hỗ trợ.

User story là lời mở đầu cho cuộc trao đổi, chưa phải đặc tả đầy đủ. Nhóm cần làm rõ các ví dụ quan trọng với người phụ trách sản phẩm và các bên liên quan.

**Tiêu chí chấp nhận có thể kiểm chứng:**

1. Học viên đủ điều kiện và khóa học còn chỗ thì đăng ký thành công, thấy xác nhận.
2. Học viên đã đăng ký thì thao tác lặp lại không tạo thêm bản ghi trùng.
3. Khóa học hết chỗ thì hệ thống giải thích rõ và không xác nhận đăng ký.
4. Hai yêu cầu đến gần đồng thời không làm số đăng ký vượt quá sức chứa đã quy định.
5. Chỉ học viên có quyền mới xem được thông tin đăng ký riêng của mình.

Tại giai đoạn này, nhóm cần **làm rõ hành vi**, chưa cần dự đoán mọi chức năng có thể xuất hiện trong tương lai.

### 5.2. Dùng ví dụ cụ thể làm tài liệu chung và điểm tựa kiểm thử

Các bên liên quan có thể thống nhất tiêu chí bằng ví dụ theo cú pháp gần với Gherkin:

~~~gherkin
Feature: Đăng ký khóa học

  Scenario: Đăng ký thành công khi còn chỗ
    Given học viên A đã đăng nhập và chưa đăng ký khóa học X
    And khóa học X còn ít nhất một chỗ
    When học viên A đăng ký khóa học X
    Then hệ thống tạo đúng một đăng ký cho A
    And hệ thống hiển thị xác nhận thành công

  Scenario: Đăng ký lặp lại không tạo bản ghi trùng
    Given học viên A đã đăng ký khóa học X
    When học viên A gửi lại yêu cầu đăng ký khóa học X
    Then hệ thống không tạo đăng ký thứ hai
    And hệ thống hiển thị trạng thái đăng ký hiện tại

  Scenario: Không xác nhận quá sức chứa
    Given khóa học X chỉ còn một chỗ
    When hai học viên đủ điều kiện cùng yêu cầu đăng ký
    Then tối đa một yêu cầu được xác nhận thêm
    And yêu cầu còn lại nhận kết quả phù hợp
~~~

Đây là **mô tả ví dụ**, chỉ trở thành kiểm thử tự động khi được nối với mã kiểm thử và chạy trong hệ thống kiểm thử thực tế. Ngay cả khi tự động hóa, nhóm vẫn cần xem xét trường hợp ngoại lệ, chất lượng triển khai và mức phủ phù hợp.

### 5.3. Xây một lát cắt dọc thay vì hoàn tất từng tầng riêng lẻ

Đội phát triển chọn phạm vi đầu tiên:

- Giao diện cho học viên xem trạng thái và gửi yêu cầu đăng ký.
- API xác thực yêu cầu, xử lý điều kiện đủ chỗ, tránh đăng ký trùng.
- Lưu trữ và kiểm soát đồng thời nhất quán.
- Kiểm thử hành vi quan trọng, thông báo trạng thái và kiểm tra tích hợp.
- Một hướng dẫn ngắn để chạy ứng dụng, chạy test, cùng mô tả hợp đồng API cho thành phần liên quan.

~~~mermaid
flowchart LR
    A["User story và ví dụ hành vi"] --> B["Giao diện + API + dữ liệu"]
    B --> C["Tích hợp và kiểm thử"]
    C --> D["Increment đáp ứng DoD"]
    D --> E["Dùng thử / đo phản hồi"]
    E --> F["Điều chỉnh backlog và tài liệu"]
    F --> A
~~~

Đây là **lát cắt dọc (vertical slice)** vì nó tạo một hành vi xuyên qua các lớp cần thiết. Phân chia “xong database”, “xong API” và “xong UI” có thể hữu ích để phối hợp kỹ thuật, nhưng từng phần riêng lẻ chưa bảo đảm học viên đăng ký được.

### 5.4. Giữ một bộ tài liệu nhỏ nhưng có chủ đích

Một số nội dung nhóm nên lưu cùng phần mềm:

| Nội dung | Vì sao cần giữ? | Ví dụ ngắn |
| --- | --- | --- |
| Quy tắc nghiệp vụ | Để các bên thống nhất cách hệ thống hành xử. | “Mỗi học viên chỉ có tối đa một đăng ký hiệu lực cho mỗi khóa học”. |
| Hợp đồng tích hợp | Để client và server hiểu dữ liệu, mã lỗi và yêu cầu xác thực. | Phương thức, đường dẫn, cấu trúc kết quả, lỗi “hết chỗ”. |
| Quyết định kỹ thuật quan trọng | Để giải thích lựa chọn ảnh hưởng tới tính nhất quán. | Lý do kiểm tra sức chứa trong giao dịch thay vì chỉ dựa vào giao diện. |
| Hướng dẫn chạy/kiểm thử | Để người khác xác minh và tiếp tục công việc. | Cách tạo dữ liệu thử, chạy kiểm thử đăng ký đồng thời. |
| Thông tin vận hành cần thiết | Để phát hiện và xử lý lỗi khi phát hành. | Tín hiệu lỗi đăng ký, cảnh báo tăng đột biến, cách điều tra. |

Nhóm không cần một bản tài liệu 100 trang để chứng minh ba kịch bản trên. Nhưng nếu bỏ qua quy tắc đồng thời hoặc cách xử lý sự cố, họ có thể tạo một tính năng trông như chạy được nhưng thiếu tin cậy.

### 5.5. Nhận phản hồi rồi quyết định Increment tiếp theo

Sau khi cho một nhóm học viên đại diện dùng thử, dữ liệu cho thấy nhiều người **không hiểu “đăng ký thành công” đã đồng nghĩa với quyền vào lớp hay chưa**. Nhóm cập nhật nội dung xác nhận và có thể thêm trạng thái rõ ràng trước khi xây danh sách chờ hoặc thông báo nâng cao.

Phần mềm chạy được giúp lộ ra nhu cầu này. Tài liệu ngắn và cập nhật giúp mọi thành viên cùng hiểu hành vi mới. **Giá trị Agile xuất hiện ở cách hai yếu tố hỗ trợ nhau để học nhanh và giao sản phẩm đáng tin cậy.**

## 6. Phối hợp giữa phần mềm và tài liệu trong quy trình hằng ngày

### 6.1. Trước khi làm: viết đủ để giảm hiểu nhầm

Trước một hạng mục, nhóm trao đổi:

1. Người dùng hoặc bên liên quan đang gặp vấn đề gì?
2. Kết quả mong muốn và dấu hiệu thành công là gì?
3. Một hành vi nhỏ nhất có thể kiểm chứng là gì?
4. Những quy tắc, phụ thuộc và rủi ro nào **phải làm rõ trước khi code**?
5. Cần ghi lại điều gì để người khác có thể kiểm tra, tích hợp hoặc vận hành?

Kết quả thường gồm một user story, vài tiêu chí chấp nhận, các câu hỏi đang mở và những hợp đồng kỹ thuật cần thiết. Nếu chưa thể trả lời vấn đề bảo mật hoặc nghĩa vụ pháp lý, nhóm phải làm rõ trước khi đưa chức năng vào sử dụng tương ứng.

### 6.2. Trong khi làm: kết hợp kiểm chứng và cập nhật tài liệu

Một số thực hành hữu ích từ phát triển Agile và XP:

- **Tích hợp liên tục (CI):** tích hợp mã thường xuyên, chạy bộ kiểm thử phù hợp để phát hiện vấn đề sớm.
- **Kiểm thử tự động:** ghi lại kỳ vọng có thể thực thi; kết hợp kiểm thử đơn vị, tích hợp và đầu cuối tùy rủi ro.
- **Review mã và pairing khi phù hợp:** phát hiện hiểu nhầm về yêu cầu, lựa chọn thiết kế và khả năng bảo trì.
- **Refactoring có bảo vệ bởi kiểm thử:** cải thiện cấu trúc mà không cố ý đổi hành vi đã được cam kết.
- **Documentation as code:** giữ tài liệu kỹ thuật gần mã, review và quản lý phiên bản cùng thay đổi khi phù hợp; kiểm tra link, ví dụ hoặc hợp đồng một cách tự động nếu có thể.

Những thực hành này tăng xác suất có **phần mềm hoạt động được lặp lại và ổn định**, thay vì chỉ chạy tại một thời điểm trình diễn.

### 6.3. Trước khi gọi là Done: kiểm tra cả phần mềm và tài liệu cần thiết

Ví dụ về các mục trong **Definition of Done** có thể được nhóm điều chỉnh theo sản phẩm:

- Chức năng đáp ứng tiêu chí chấp nhận đã thống nhất.
- Mã được tích hợp; các kiểm thử bắt buộc chạy đạt và lỗi nghiêm trọng được xử lý theo chính sách.
- Các yêu cầu phi chức năng liên quan như quyền truy cập, bảo mật, hiệu năng hoặc khả năng tiếp cận được xác minh ở mức phù hợp.
- Hợp đồng API, hướng dẫn vận hành và tài liệu chịu tác động bởi thay đổi đã cập nhật.
- Bằng chứng kiểm tra, dấu vết phê duyệt hoặc hồ sơ tuân thủ bắt buộc được lưu đúng chỗ.
- Increment có thể sử dụng/kiểm tra trong phạm vi dự định và không làm hỏng hành vi đã hoàn tất trước đó.

Definition of Done là **cam kết chất lượng chung**, khác với **acceptance criteria** là điều kiện riêng của một hạng mục. Tùy bối cảnh, “Done” có thể khác với “đã release”: một Increment hoàn tất có thể được giữ lại trước khi phát hành vì chiến lược triển khai hoặc yêu cầu vận hành.

### 6.4. Tại buổi xem xét: trình diễn hành vi, không chỉ đọc báo cáo

Thay cho báo cáo “đã viết 80% tài liệu”, “đã hoàn thành 12 task” hoặc “mã đã đẩy lên nhánh”, nhóm nên:

1. Trình diễn hành vi người dùng từ đầu đến cuối trên phiên bản tích hợp thích hợp.
2. Nêu rõ phạm vi hoạt động, giới hạn và những rủi ro còn tồn tại.
3. Cùng bên liên quan kiểm tra các kịch bản quan trọng.
4. Ghi nhận phản hồi, quyết định điều chỉnh backlog và xác định tài liệu cần cập nhật.

Nếu chỉ có bản mô phỏng, nhóm cần nói rõ đó là nguyên mẫu dùng để học hỏi. Minh bạch về mức hoàn tất giúp các bên quyết định chính xác.

## 7. Khi nào phải ưu tiên viết tài liệu trước hoặc song song?

Giá trị Agile không quy định “mọi trường hợp đều code trước”. Cách làm hợp lý phụ thuộc **chi phí hiểu sai, mức độ bất định, số người phụ thuộc và khả năng đảo ngược quyết định**.

| Bối cảnh | Tài liệu hoặc bằng chứng cần ưu tiên | Phần mềm và kiểm chứng đi kèm |
| --- | --- | --- |
| Thử nghiệm hành vi người dùng ít rủi ro | Giả thuyết, kịch bản thử và cách đo ngắn gọn. | Nguyên mẫu hoặc increment nhỏ để nhận phản hồi sớm. |
| API công khai cho nhiều đối tác | Hợp đồng API, phiên bản, quy tắc tương thích, mã lỗi, bảo mật. | Contract test, kiểm thử tích hợp, ví dụ chạy được. |
| Thay đổi dữ liệu khó hoàn tác | Kế hoạch migration, sao lưu, kiểm tra tính toàn vẹn, phương án phục hồi. | Kiểm thử migration và diễn tập rollback hoặc khôi phục phù hợp. |
| Hệ thống có yêu cầu pháp lý/kiểm toán | Chính sách, phân quyền, truy vết, phê duyệt và hồ sơ theo yêu cầu áp dụng. | Kiểm chứng kiểm soát, bằng chứng kiểm thử và đánh giá tương ứng. |
| Dịch vụ vận hành 24/7 | Runbook, giám sát, quy trình ứng cứu, người chịu trách nhiệm. | Quan sát hành vi, cảnh báo và diễn tập sự cố theo mức rủi ro. |
| Quyết định kiến trúc khó đảo ngược | ADR ngắn ghi bối cảnh, phương án, đánh đổi và tác động. | Spike/prototype hoặc thử nghiệm kỹ thuật để giảm bất định. |
| Onboarding và chuyển giao đội ngũ | README, kiến trúc mức cần thiết, cách chạy/test, hướng dẫn nghiệp vụ cốt lõi. | Người mới thực sự làm theo và tự xác minh tài liệu còn đúng. |

Trong các trường hợp trên, tài liệu là **công cụ giảm rủi ro**. Nó có thể cần được hoàn thành và phê duyệt trước khi triển khai một bước nguy hiểm. Ưu tiên phần mềm hoạt động được không có nghĩa là phá bỏ quy trình phê duyệt bắt buộc.

Một câu hỏi thực dụng là: **Nếu hôm nay người viết tài liệu nghỉ việc, ai cần dùng thông tin nào để tiếp tục hoặc vận hành an toàn?** Nếu không trả lời được, nhóm rất có thể đang thiếu tài liệu quan trọng.

## 8. Các dấu hiệu tối ưu sai và cách điều chỉnh

| Dấu hiệu | Vì sao có vấn đề? | Hành động gợi ý |
| --- | --- | --- |
| Có nhiều đặc tả và slide nhưng chưa có luồng người dùng chạy được | Tiến độ được chứng minh bằng dự định; giả định cốt lõi chưa được kiểm tra. | Chọn lát cắt dọc nhỏ, tích hợp và cho người dùng kiểm tra sớm. |
| Demo chạy một lần trên laptop nhưng không thể tái hiện | Chưa có bằng chứng về tích hợp, kiểm thử và độ tin cậy. | Xác định DoD rõ, ổn định môi trường và tự động hóa kiểm tra phù hợp. |
| “Agile nên không viết tài liệu” | Rủi ro chuyển giao, vận hành, bảo mật và tuân thủ tăng. | Xác định người đọc/mục đích, viết tài liệu tối thiểu cần thiết và sở hữu việc cập nhật. |
| Mỗi thay đổi phải cập nhật nhiều bản mô tả trùng nhau | Tốn chi phí, dễ sinh mâu thuẫn và làm phản hồi chậm. | Chọn nguồn thông tin chuẩn, tạo liên kết và tự động sinh dữ liệu/tài liệu có thể sinh. |
| Test qua nhưng người dùng không hoàn tất tác vụ | Kiểm thử kỹ thuật chưa bao phủ nhu cầu sử dụng thực tế. | Bổ sung thử nghiệm với người dùng và chỉ số kết quả. |
| Đóng nhiều ticket nhưng tích hợp cuối kỳ mới phát hiện lỗi | Đầu ra của từng cá nhân chưa tạo thành phần sản phẩm hoàn tất. | Giảm quy mô hạng mục, tích hợp thường xuyên, hạn chế WIP. |
| Tài liệu API không khớp bản đang chạy | Người dùng tài liệu có thể tích hợp sai dù phần mềm hiện tại hoạt động. | Quản lý phiên bản tài liệu với thay đổi API; thêm contract test hoặc kiểm tra ví dụ. |
| Sprint Review chỉ chiếu số liệu tiến độ | Bên liên quan khó xác nhận hành vi và thay đổi nhu cầu. | Đưa Increment vào trung tâm buổi review, nêu rõ bằng chứng và vấn đề còn mở. |

## 9. Đo tiến độ và sức khỏe sản phẩm thế nào cho đúng?

Vì Agile ưu tiên phần mềm hoạt động được, nhóm nên nhìn vào **khả năng hoàn tất hành vi có ích** cùng chất lượng và kết quả, thay vì chỉ đếm trang tài liệu, dòng mã, số commit hoặc story point.

| Nhóm tín hiệu | Ví dụ đo lường | Cách diễn giải cẩn trọng |
| --- | --- | --- |
| **Sản phẩm hoạt động** | Hạng mục đáp ứng DoD, hành vi đầu cuối chạy qua kiểm thử. | “Xong” phải theo cùng một định nghĩa chất lượng; không chỉ tính task đã đóng. |
| **Giá trị thực tế** | Tỷ lệ học viên hoàn tất đăng ký, số lỗi thao tác, phản hồi hỗ trợ. | Đo kết quả liên quan mục tiêu; phân biệt tương quan với nguyên nhân. |
| **Tốc độ phản hồi** | Thời gian từ ý tưởng đến lúc kiểm tra được với người dùng. | Ngắn hơn hữu ích khi chất lượng và đối tượng thử vẫn phù hợp. |
| **Luồng công việc** | Lead time, cycle time, throughput, WIP, tuổi hạng mục đang làm. | Dùng để cải thiện hệ thống làm việc, không xếp hạng cá nhân. |
| **Chất lượng** | Lỗi hồi quy, sự cố sau phát hành, thời gian phục hồi, thất bại triển khai. | Tốc độ tăng mà độ ổn định giảm có thể là tiến độ không bền vững. |
| **Khả năng duy trì tài liệu** | Tỷ lệ hướng dẫn quan trọng còn chạy đúng, độ trễ cập nhật tài liệu theo thay đổi. | Ít trang hơn không tự động tốt; ưu tiên tài liệu giúp thực hiện công việc đúng. |

**Ví dụ:** nhóm đóng 15 task trong tuần nhưng không có luồng đăng ký nào đạt DoD. Tuần tiếp theo nhóm chỉ đóng 5 task, song một lát cắt đăng ký có thể sử dụng được, tích hợp và được học viên thử nghiệm. Chỉ dựa vào số task, tuần đầu trông năng suất hơn; dựa trên khả năng kiểm chứng giá trị, tuần sau tạo được bằng chứng tiến độ rõ ràng hơn.

Không nên biến số Increment hoặc story point thành chỉ tiêu buộc nhóm chia việc giả tạo. Đo lường nên giúp ra quyết định như “vướng mắc nào khiến học viên chờ lâu?” hoặc “cần cải thiện độ tin cậy ở bước nào?”.

## 10. Thực hành nhanh trong nhóm

### Bài tập 1: Chọn bằng chứng tiến độ

Bạn nhận hai báo cáo về chức năng đăng ký:

- **Báo cáo A:** “Đã hoàn thành tài liệu nghiệp vụ 65 trang, sơ đồ kiến trúc và kế hoạch 12 tuần”.
- **Báo cáo B:** “Đã đăng ký thành công từ giao diện tới dữ liệu trên môi trường thử nghiệm, kiểm tra được trường hợp hết chỗ và đăng ký trùng; chưa có hồ sơ phục hồi sự cố”.

**Câu hỏi:** Nhóm nào có bằng chứng mạnh hơn về hành vi sản phẩm? Nhóm nào cần làm tiếp điều gì để đủ điều kiện phát hành?

**Gợi ý:** Báo cáo B chứng minh được nhiều hành vi hơn, nhưng không đủ để khẳng định sẵn sàng phát hành ở mọi bối cảnh. Cần xem DoD, các rủi ro còn mở, khả năng phục hồi và yêu cầu vận hành/pháp lý. Báo cáo A vẫn có thể chứa thông tin cần thiết; tuy nhiên, tài liệu chưa chứng minh giải pháp chạy đúng.

### Bài tập 2: Quyết định tài liệu nào phải tồn tại

Một đội tích hợp thanh toán tự động với đối tác thứ ba. Hãy tự chọn **ba tài liệu hoặc bằng chứng** không thể thiếu trong tình huống này, giải thích ai sử dụng và hậu quả nếu thiếu. Sau đó đề xuất một kiểm thử hoặc màn trình diễn thực thi chứng minh hệ thống đáp ứng một quy tắc quan trọng.

**Gợi ý tham khảo:** hợp đồng API và xác thực, quy tắc xử lý giao dịch lặp/idempotency, hướng dẫn đối soát và xử lý lỗi; kết hợp kiểm thử tích hợp đối với thông báo lặp lại và tình huống kết nối gián đoạn. Sự lựa chọn cuối cùng phải dựa trên rủi ro và yêu cầu thực tế của hệ thống.

### Bài tập 3: Rà soát một user story trước khi gọi Done

Với user story “học viên đăng ký khóa học còn chỗ”, hãy điền bảng:

| Câu hỏi | Nội dung nhóm cần trả lời |
| --- | --- |
| Hành vi kiểm chứng được là gì? | Đăng ký thành công, hết chỗ, đăng ký lặp và tình huống đồng thời. |
| Các thành phần nào cần tích hợp? | Giao diện, API, xử lý nghiệp vụ, lưu trữ và xác thực. |
| Những kiểm tra chất lượng nào cần có? | Kiểm thử hành vi cốt lõi, quyền truy cập, xử lý lỗi và rủi ro liên quan. |
| Tài liệu nào cần giữ lại? | Quy tắc nghiệp vụ, hợp đồng API, hướng dẫn chạy/test và thông tin vận hành cần thiết. |
| Ai xác nhận giá trị? | Người phụ trách sản phẩm và đại diện học viên/người sử dụng thích hợp. |
| Thông tin nào có thể thay đổi backlog? | Khó hiểu thông báo, tỷ lệ hoàn tất thấp, hành vi đăng ký thực tế. |

Sau khi nhóm trả lời, chọn **một thay đổi nhỏ** giúp rút ngắn thời gian từ hiểu yêu cầu đến nhận phản hồi mà vẫn giữ chất lượng.

## 11. Ghi nhớ và câu hỏi tự kiểm tra

**“Phần mềm hoạt động được hơn tài liệu đầy đủ”** có nghĩa là ưu tiên **bằng chứng từ hành vi phần mềm đã kiểm chứng** khi đánh giá tiến độ và học hỏi, đồng thời viết tài liệu **đúng mức để cộng tác, tích hợp, bảo trì, vận hành và đáp ứng nghĩa vụ cần thiết**. Tài liệu tốt giúp làm ra phần mềm tốt; phần mềm hoạt động được giúp kiểm tra những gì tài liệu mô tả.

Trước khi kết thúc một hạng mục, hãy tự hỏi:

1. Hành vi nào đã chạy được từ đầu đến cuối và ai đã kiểm tra?
2. Tiêu chí chấp nhận và Definition of Done đã được đáp ứng chưa?
3. Chúng ta học được gì từ phiên bản thực tế hoặc thử nghiệm?
4. Những quy tắc, quyết định, hợp đồng và hướng dẫn nào cần được lưu lại hoặc cập nhật?
5. Nếu người khác tiếp quản ngày mai, họ có thể hiểu, chạy, kiểm thử và vận hành phần này an toàn không?

Nếu năm câu hỏi đều có câu trả lời rõ ràng và bằng chứng phù hợp, nhóm đã tiến gần hơn tới mục tiêu Agile: **giao phần mềm tăng dần có ích, nhận phản hồi sớm và cải tiến liên tục**, thay vì chỉ tích lũy tài liệu hoặc công việc đang làm dở.

### Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Working software** | Phần mềm có hành vi sử dụng được và được kiểm chứng trong phạm vi, chất lượng đã thống nhất. |
| **Comprehensive documentation** | Bộ tài liệu mô tả toàn diện; có thể tốn kém và nhanh lỗi thời nếu tạo quá sớm/không được duy trì. |
| **Increment** | Phần sản phẩm tăng thêm đã tích hợp và đáp ứng Definition of Done. |
| **Acceptance criteria** | Các điều kiện cụ thể để xác nhận một hạng mục đáp ứng yêu cầu. |
| **Definition of Done (DoD)** | Tiêu chuẩn chất lượng chung để kết luận một Increment đã hoàn tất. |
| **Vertical slice** | Lát cắt chức năng đi qua những lớp cần thiết để tạo hành vi kiểm chứng được. |
| **Living documentation** | Tài liệu được cập nhật cùng sản phẩm để luôn phản ánh trạng thái hiện tại. |
| **ADR** | Bản ghi quyết định kiến trúc, gồm bối cảnh, lựa chọn, lý do và hệ quả. |
| **Documentation as code** | Cách quản lý tài liệu như mã nguồn: version control, review và kiểm tra tự động khi phù hợp. |

