# Tổ chức trao đổi giữa nghiệp vụ, phát triển và kiểm thử

## 1. Vì sao trao đổi liên chức năng là nền tảng của yêu cầu thích ứng?

Trong phát triển phần mềm theo **Agile**, yêu cầu không phải lúc nào cũng được hiểu đầy đủ ngay khi dự án bắt đầu. Người làm nghiệp vụ thường hiểu mục tiêu khách hàng và quy tắc vận hành; người phát triển hiểu khả năng của hệ thống, dữ liệu và các ràng buộc kỹ thuật; người kiểm thử hiểu cách đặt câu hỏi để tìm trường hợp thiếu, mâu thuẫn hoặc rủi ro đối với người sử dụng. Nếu ba góc nhìn chỉ gặp nhau ở cuối quá trình, nhóm dễ xây dựng một chức năng chạy đúng theo cách lập trình viên hiểu nhưng chưa đáp ứng nhu cầu thực tế.

Ví dụ, yêu cầu ban đầu là: “Cho khách hàng hủy đơn hàng trước khi gửi đi”. Câu này nghe có vẻ rõ, nhưng thực tế còn nhiều câu hỏi:

- “Trước khi gửi đi” tính từ lúc xác nhận đơn, lúc bắt đầu đóng gói hay lúc bàn giao cho đơn vị vận chuyển?
- Đơn đã thanh toán được hoàn tiền ngay hay cần chờ bên thanh toán xác nhận?
- Nếu nhân viên bắt đầu đóng gói đúng lúc khách bấm hủy thì bên nào được ưu tiên?
- Nếu khách nhấn nút hủy hai lần, hệ thống có tạo hai yêu cầu hoàn tiền không?
- Nếu người khác cố hủy một đơn không thuộc tài khoản của mình thì sao?

Không một vai trò riêng lẻ nào nhất thiết nắm đủ câu trả lời. **Tổ chức trao đổi giữa nghiệp vụ, phát triển và kiểm thử** là cách nhóm tạo ra sự hiểu biết chung, phát hiện bất định sớm, ra quyết định có thể kiểm chứng và cập nhật yêu cầu khi học được điều mới.

Điều này phục vụ trực tiếp mục tiêu của module **AGILE_DEVELOPMENT**: thích ứng qua phản hồi sớm, bàn giao sản phẩm tăng dần và cải tiến liên tục. Trong bối cảnh đó, **user story** giúp khơi gợi cuộc trao đổi, **backlog** biểu thị thứ tự ưu tiên, còn Scrum, Kanban và XP cung cấp những cách phối hợp phù hợp với công việc và luồng phản hồi.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt trách nhiệm và đóng góp của nghiệp vụ, phát triển và kiểm thử khi làm rõ yêu cầu.
2. Tổ chức một cuộc trao đổi ngắn dựa trên user story, ví dụ cụ thể, câu hỏi chưa rõ và rủi ro.
3. Chuyển hiểu biết chung thành tiêu chí chấp nhận, các trường hợp kiểm thử và quyết định được ghi lại.
4. Phối hợp khi yêu cầu thay đổi, khi xuất hiện phụ thuộc hoặc khi ba bên bất đồng.
5. Đánh giá hiệu quả trao đổi qua kết quả bàn giao và chất lượng dòng công việc, thay vì chỉ đếm cuộc họp.

## 2. Mỗi góc nhìn đóng góp điều gì?

**Nghiệp vụ, phát triển và kiểm thử là ba góc nhìn cần có trong cuộc trao đổi**, không nhất thiết là ba phòng ban tách biệt hay đúng ba cá nhân. Một thành viên có thể đảm nhiệm nhiều năng lực; một câu chuyện phức tạp có thể cần thêm chuyên gia bảo mật, vận hành, thiết kế, pháp chế hoặc đại diện người dùng.

| Góc nhìn | Thông tin và quyết định thường đóng góp | Câu hỏi tiêu biểu |
|---|---|---|
| **Nghiệp vụ / sản phẩm** | Vấn đề của người dùng, mục tiêu sản phẩm, quy tắc kinh doanh, thứ tự ưu tiên, phạm vi được phép, tiêu chí giá trị. | “Người dùng cần đạt điều gì?”, “Trường hợp nào phải được phục vụ?”, “Ngoại lệ nào ảnh hưởng doanh thu hoặc cam kết?” |
| **Phát triển / kỹ thuật** | Cách hệ thống hoạt động, dữ liệu, tích hợp, tính khả thi, phụ thuộc, chất lượng kỹ thuật và cách chia nhỏ phần giao. | “Trạng thái đơn được ghi ở đâu?”, “Có xử lý cạnh tranh không?”, “Làm sao giảm rủi ro khi triển khai?” |
| **Kiểm thử / chất lượng** | Kịch bản biên, giả định chưa rõ, rủi ro về hành vi, phương án kiểm tra, khả năng quan sát và tiêu chí xác nhận. | “Nếu thanh toán thất bại?”, “Nếu người dùng thao tác lặp?”, “Làm sao chứng minh hành vi đã đúng?” |

Ở đây, **“nghiệp vụ”** có thể là Product Owner, nhà phân tích nghiệp vụ, chuyên gia miền nghiệp vụ hoặc người đại diện người dùng phù hợp. Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog; điều đó không ngăn Developers hoặc người có kỹ năng kiểm thử tham gia thảo luận về nhu cầu và thứ tự ưu tiên.

Người kiểm thử không chỉ nhận phần mềm ở cuối chu kỳ rồi tìm lỗi. Khi tham gia từ đầu, họ giúp nhóm **ngăn lỗi hiểu nhầm**, chẳng hạn phát hiện yêu cầu thiếu quy tắc cho đơn hàng đã đóng gói trước khi viết mã.

Ngược lại, người phát triển cần đặt câu hỏi về giá trị và cách sử dụng, thay vì chỉ hỏi giao diện có bao nhiêu trường. Người làm nghiệp vụ cũng cần lắng nghe rủi ro kỹ thuật và chi phí thay đổi để ra quyết định ưu tiên thực tế.

### 2.1. Trách nhiệm cùng tạo hiểu biết, không phải chuyển giao tài liệu

Một kiểu phối hợp dễ gặp là nghiệp vụ viết yêu cầu, phát triển thực hiện, kiểm thử xác nhận, rồi khi không khớp thì tài liệu được gửi ngược qua các bước. Mỗi điểm bàn giao làm tăng thời gian chờ và nguy cơ giải thích sai.

Cách làm thích ứng tạo **vòng trao đổi ngắn xuyên suốt**:

~~~mermaid
flowchart TD
    A[Nhu cầu và mục tiêu người dùng] --> B[Ba góc nhìn cùng làm rõ]
    B --> C[Ví dụ, quy tắc và câu hỏi còn mở]
    C --> D[Ưu tiên và chọn phần việc nhỏ]
    D --> E[Phát triển, kiểm tra và tích hợp]
    E --> F[Phần mềm có thể đánh giá]
    F --> G[Phản hồi từ người dùng và vận hành]
    G --> B
~~~

Sơ đồ không đòi hỏi một buổi họp ở mỗi mũi tên. Câu hỏi nhỏ có thể giải quyết ngay trong trao đổi trực tiếp hoặc bất đồng bộ; vấn đề phức tạp mới cần thảo luận nhiều bên.

## 3. Chuẩn bị trước khi trao đổi

Một cuộc trao đổi hữu ích bắt đầu bằng **mục tiêu rõ và thông tin tối thiểu**, tránh yêu cầu mọi người đọc hàng chục trang đặc tả trước khi được đặt câu hỏi.

### 3.1. Chọn hạng mục phù hợp

Nhóm nên tập trung vào một hạng mục đang có khả năng được làm trong tương lai gần, đủ quan trọng và còn những điểm cần làm rõ. Các hạng mục có nhiều rủi ro, tích hợp hoặc quy tắc ngoại lệ thường hưởng lợi rõ từ trao đổi ba góc nhìn.

Đầu vào có thể gồm:

- **Vấn đề người dùng và giá trị mong muốn:** ai gặp khó khăn, trong ngữ cảnh nào, điều gì sẽ tốt lên?
- **User story hoặc mô tả công việc:** đủ để biết mục đích, không bắt buộc đúng một mẫu câu.
- **Quy tắc đang biết:** chính sách kinh doanh, quyền truy cập, giới hạn dữ liệu, quy trình liên quan.
- **Bằng chứng hiện có:** phản hồi người dùng, dữ liệu sử dụng, sự cố hoặc thông tin từ vận hành.
- **Các ràng buộc quan trọng:** an toàn, bảo mật, tính sẵn sàng, thời hạn, hệ thống phụ thuộc.

Nếu chưa biết yêu cầu có giá trị hay không, hoạt động phù hợp trước mắt có thể là **khám phá hoặc thử nghiệm**, thay vì cam kết phát triển một tính năng đầy đủ.

### 3.2. Mời đúng người, đúng thời điểm

Một buổi trao đổi thường cần người có khả năng làm rõ **quy tắc nghiệp vụ**, người hiểu **ảnh hưởng kỹ thuật** và người có thể đặt câu hỏi về **hành vi cần xác minh**. Người có quyền quyết định cần tham gia hoặc có đường phản hồi rõ ràng khi phát sinh vấn đề không thể tự giải quyết.

Đừng cố mời mọi bên liên quan vào mọi cuộc trao đổi. Với một câu chuyện liên quan hoàn tiền, có thể mời thêm đại diện tài chính hoặc tích hợp thanh toán; với một thay đổi liên quan dữ liệu cá nhân, có thể cần ý kiến bảo mật. Việc chọn người dựa trên **rủi ro và quyết định cần đưa ra**, không dựa trên sơ đồ tổ chức.

Thông tin đầu vào nên được chia sẻ trước ở mức vừa đủ để các bên chuẩn bị câu hỏi, đặc biệt khi làm việc từ xa hoặc khác múi giờ.

## 4. Thực hành “Three Amigos”: trao đổi bằng ví dụ

**Three Amigos** là một thực hành cộng tác phổ biến, trong đó các góc nhìn nghiệp vụ, phát triển và kiểm thử cùng xem xét một hạng mục trước hoặc trong quá trình thực hiện. Đây **không phải sự kiện bắt buộc của Scrum** và cũng không có yêu cầu cố định về đúng ba người, thời lượng hay công cụ.

Điểm mạnh của phương pháp là cả nhóm sử dụng **ví dụ cụ thể** để phát hiện điều chưa rõ, thay vì chỉ tranh luận trên mô tả tổng quát.

### 4.1. Mục đích và đầu ra của cuộc trao đổi

Một phiên trao đổi có thể đi theo trình tự:

1. **Nêu mục tiêu:** hạng mục giúp ai, giải quyết việc gì và thành công được nhận biết ra sao?
2. **Mô tả hành vi thông thường:** lấy ví dụ đầu vào và kết quả mong đợi.
3. **Tìm ngoại lệ và ranh giới:** trạng thái sai, quyền hạn, dữ liệu thiếu, xung đột, tích hợp không phản hồi.
4. **Làm rõ quy tắc:** nghiệp vụ quyết định điều gì được phép; kỹ thuật và kiểm thử nêu tác động.
5. **Chốt phần đủ rõ để thực hiện:** ghi tiêu chí chấp nhận, ví dụ, vấn đề mở và người chịu trách nhiệm giải đáp.
6. **Quyết định bước tiếp:** làm ngay, chia nhỏ, thử nghiệm thêm, hoặc đưa về backlog vì còn bất định.

Không phải mọi câu hỏi đều phải được trả lời trong một lần họp. Điều quan trọng là **không che giấu bất định**: một quy tắc chưa rõ cần được đánh dấu, gắn với người quyết định và theo dõi đến khi được xử lý.

### 4.2. Example Mapping để nhìn thấy phần chưa rõ

**Example Mapping** giúp nhóm tổ chức suy nghĩ quanh một câu chuyện bằng các loại thông tin:

| Thành phần | Mục đích | Ví dụ hủy đơn hàng |
|---|---|---|
| **Story** | Vấn đề hoặc lợi ích của hạng mục. | Khách hàng muốn hủy đơn trước khi đóng gói để tránh nhận hàng không còn cần. |
| **Rules** | Quy tắc nghiệp vụ phải đúng. | Chỉ chủ đơn được yêu cầu hủy; không hủy khi đóng gói đã bắt đầu. |
| **Examples** | Tình huống cụ thể minh họa quy tắc. | Đơn đã thanh toán nhưng chưa đóng gói có thể hủy, và chờ hoàn tiền. |
| **Questions** | Điểm còn mơ hồ hoặc quyết định đang thiếu. | Nếu hệ thống thanh toán không trả lời, thông báo nào hiển thị? |

Nhiều quy tắc khó diễn đạt, ví dụ mâu thuẫn hoặc câu hỏi quan trọng chưa có câu trả lời là tín hiệu rằng hạng mục cần được làm rõ hoặc chia nhỏ. Không nên cố ép những phần chưa chắc chắn vào một tiêu chí chấp nhận có vẻ chính xác.

### 4.3. Dẫn dắt bằng câu hỏi mở

Ví dụ những câu hỏi mỗi góc nhìn có thể đặt cho nhau:

**Nghiệp vụ hỏi phát triển và kiểm thử:** “Nếu chỉ triển khai hủy trước khi đóng gói, phần nào đủ tạo giá trị?”, “Người dùng cần được thông báo khi hoàn tiền đang chờ không?”

**Phát triển hỏi nghiệp vụ:** “Chúng ta lấy trạng thái đóng gói từ đâu?”, “Nếu đơn đổi trạng thái khi yêu cầu đang được xử lý thì quy tắc nào thắng?”, “Chúng ta có thể giảm phạm vi hoàn tiền từng phần ở đợt đầu không?”

**Kiểm thử hỏi cả hai bên:** “Khách không đăng nhập thì sao?”, “Nếu nhấn hủy nhiều lần thì sao?”, “Nếu đơn đã được nhân viên đóng gói thì thông báo thế nào?”, “Dựa vào đâu kiểm tra tiền không bị hoàn hai lần?”

Câu hỏi nên hướng tới **hành vi và rủi ro của sản phẩm**; tránh biến cuộc trao đổi thành truy tìm người viết thiếu yêu cầu.

## 5. Ví dụ xuyên suốt: chức năng hủy đơn hàng

Tình huống dưới đây là **ví dụ giả định**, không phải chính sách áp dụng cho mọi hệ thống thương mại điện tử. Nó cho thấy cách ba góc nhìn cùng làm rõ một user story có nhiều trường hợp biên.

### 5.1. User story ban đầu

> Với vai trò là khách hàng đã đặt hàng, tôi muốn hủy đơn trước khi đơn được xử lý giao hàng, để có thể thay đổi quyết định mua mà không phải liên hệ hỗ trợ.

Story này có giá trị dễ hiểu nhưng còn mơ hồ ở khái niệm “được xử lý giao hàng”. Nếu đưa thẳng cho lập trình viên, người đó có thể cho phép hủy mọi đơn chưa ở trạng thái “đã giao”. Kiểm thử có thể hiểu rằng đơn đang đóng gói vẫn được hủy. Nghiệp vụ lại có thể cho rằng hủy chỉ được thực hiện trước khi kho bắt đầu đóng gói.

### 5.2. Cuộc trao đổi mẫu

| Vai trò | Trao đổi | Điều được làm rõ |
|---|---|---|
| **Nghiệp vụ** | “Chúng ta muốn khách tự hủy khi kho chưa bắt đầu đóng gói. Nếu đã bắt đầu đóng gói, họ cần liên hệ hỗ trợ.” | Ranh giới hủy nằm ở **bắt đầu đóng gói**, không phải bàn giao vận chuyển. |
| **Phát triển** | “Kho và khách có thể thay đổi trạng thái gần cùng lúc. Cần xác định một giao dịch thay đổi trạng thái duy nhất, có xử lý cạnh tranh.” | Cần kiểm soát đồng thời, tránh hai thao tác cùng được chấp nhận. |
| **Kiểm thử** | “Đơn đã trả tiền được hủy rồi thì hoàn tiền thế nào? Nếu hoàn tiền chậm, khách nhìn thấy trạng thái gì?” | Phải phân biệt hủy đơn thành công với hoàn tiền hoàn tất. |
| **Nghiệp vụ** | “Trong phạm vi đợt này, cho hủy toàn bộ đơn trước đóng gói, tạo yêu cầu hoàn tiền nếu đã thanh toán; tiền về theo quy trình nhà cung cấp.” | Đợt đầu không xử lý hủy một phần; quy tắc hoàn tiền được xác định. |
| **Phát triển** | “Nếu khách gửi yêu cầu hai lần, cần tránh tạo hai lệnh hoàn tiền; mã yêu cầu phải xử lý lặp an toàn.” | Cần cơ chế tránh tác động lặp và ghi nhận trạng thái xử lý. |
| **Kiểm thử** | “Cần kiểm tra người dùng chỉ thao tác trên đơn của mình, trạng thái kho thay đổi cùng lúc và nhà cung cấp hoàn tiền lỗi.” | Có kịch bản quyền truy cập, cạnh tranh và lỗi tích hợp. |

Sau trao đổi, nhóm thống nhất **quy tắc minh họa**: người đã xác thực chỉ được hủy toàn bộ đơn của mình khi kho chưa bắt đầu đóng gói. Hủy đơn đã thanh toán tạo một yêu cầu hoàn tiền, quá trình hoàn tiền có thể hoàn tất sau. Khi trạng thái kho đã sang “đang đóng gói”, thao tác hủy trực tuyến bị từ chối và người dùng nhận giải thích phù hợp.

Nhóm vẫn cần làm rõ với đơn dùng nhiều phương thức thanh toán, đơn có hàng đặc biệt, phí dịch vụ hoặc luật hoàn tiền áp dụng. Nếu ngoài phạm vi đợt đầu, những trường hợp đó phải được **đánh dấu có chủ đích**, không ngầm hiểu rằng chúng đã được hỗ trợ.

### 5.3. Bảng ví dụ giúp kiểm tra quy tắc

| Tình huống | Trạng thái đơn trước thao tác | Người yêu cầu | Kết quả mong đợi |
|---|---|---|---|
| A — Chưa thanh toán, chưa đóng gói | Đã xác nhận, chờ đóng gói | Chủ đơn | Hủy thành công, không tạo lệnh hoàn tiền. |
| B — Đã thanh toán, chưa đóng gói | Đã thanh toán, chờ đóng gói | Chủ đơn | Hủy thành công, tạo **một** yêu cầu hoàn tiền; hiển thị đang xử lý hoàn tiền nếu chưa có kết quả. |
| C — Kho đã bắt đầu đóng gói | Đang đóng gói | Chủ đơn | Không hủy qua chức năng này; giải thích lý do và chỉ dẫn cách liên hệ hỗ trợ. |
| D — Người khác muốn hủy | Bất kỳ | Không phải chủ đơn, không có quyền phù hợp | Không cho phép; không tiết lộ dữ liệu đơn hàng không thuộc quyền truy cập. |
| E — Gửi yêu cầu hủy lặp | Đã hủy từ yêu cầu trước | Chủ đơn | Trả trạng thái nhất quán; không tạo thêm lệnh hoàn tiền. |
| F — Kho và khách thao tác đồng thời | Chờ đóng gói ngay trước thao tác | Chủ đơn và nhân viên kho | Chỉ một chuyển trạng thái hợp lệ thành công theo quy tắc đã thiết kế; không xuất hiện đơn vừa đóng gói vừa được hủy thành công. |

Ví dụ A–F làm rõ ranh giới nghiệp vụ và rủi ro kỹ thuật. Chúng cũng cung cấp đầu vào cho kiểm thử, nhưng **chưa thay thế toàn bộ chiến lược kiểm thử**, chẳng hạn hiệu năng, bảo mật, lỗi mạng và khả năng tiếp cận.

### 5.4. Tiêu chí chấp nhận từ cuộc trao đổi

**Acceptance criteria (tiêu chí chấp nhận)** mô tả điều kiện để hạng mục được xem là đáp ứng yêu cầu nghiệp vụ. Có thể viết dưới dạng bảng, câu ngắn hoặc cấu trúc Given–When–Then. Định dạng không quan trọng bằng sự rõ ràng và khả năng kiểm chứng.

Ví dụ:

~~~gherkin
Feature: Hủy toàn bộ đơn hàng trước khi kho bắt đầu đóng gói

  Scenario: Chủ đơn hủy đơn đã thanh toán và chưa đóng gói
    Given khách hàng đã đăng nhập và sở hữu đơn O-123
    And đơn O-123 đã thanh toán nhưng kho chưa bắt đầu đóng gói
    When khách hàng yêu cầu hủy đơn O-123
    Then đơn được ghi nhận là đã hủy
    And hệ thống tạo đúng một yêu cầu hoàn tiền
    And khách hàng thấy trạng thái hoàn tiền đang được xử lý

  Scenario: Kho đã bắt đầu đóng gói
    Given khách hàng sở hữu đơn O-124
    And kho đã bắt đầu đóng gói đơn O-124
    When khách hàng yêu cầu hủy đơn O-124
    Then hệ thống không hủy đơn
    And khách hàng thấy lý do và hướng dẫn liên hệ hỗ trợ

  Scenario: Khách gửi lại yêu cầu hủy thành công
    Given đơn O-123 đã được hủy từ một yêu cầu trước
    And đã có một yêu cầu hoàn tiền tương ứng
    When khách hàng gửi lại yêu cầu hủy O-123
    Then hệ thống không tạo yêu cầu hoàn tiền thứ hai
    And khách hàng nhận được trạng thái hiện tại của đơn
~~~

Các bước trong ví dụ là mô tả hành vi; không bắt buộc dùng Cucumber hoặc viết tự động hóa theo đúng cú pháp này. Nếu tự động hóa, nhóm cần lựa chọn mức kiểm thử phù hợp và bảo đảm kết quả không phụ thuộc vào dữ liệu thử thiếu ổn định.

### 5.5. Phân biệt tiêu chí chấp nhận và thiết kế kiểm thử

Tiêu chí chấp nhận trả lời **“người dùng và nghiệp vụ mong đợi hành vi nào?”**; thiết kế kiểm thử đi sâu vào **“làm thế nào kiểm tra và tìm sai sót của hành vi đó?”**.

Ví dụ, tiêu chí “người không có quyền không thể hủy đơn” có thể dẫn đến nhiều kiểm thử: người dùng chưa đăng nhập, người dùng đăng nhập nhưng thuộc tài khoản khác, mã đơn không tồn tại, dữ liệu truy cập qua API thay vì giao diện, và thông tin trả về không làm lộ dữ liệu cá nhân. Những kiểm thử bổ sung cần bám vào mức rủi ro, không nhất thiết phải ghi từng trường hợp thành tiêu chí nghiệp vụ riêng.

## 6. Xác định đầu ra chung của cuộc trao đổi

Sau phiên trao đổi, nhóm nên có một **nguồn thông tin chung, ngắn gọn và có thể cập nhật**. Đầu ra không cần thành tài liệu dài nhưng phải giảm được các câu hỏi lặp lại.

| Đầu ra | Nội dung tối thiểu | Vì sao hữu ích? |
|---|---|---|
| **Mục tiêu/story** | Ai cần gì, tại sao, kết quả mong muốn. | Giữ trọng tâm vào giá trị thay vì danh sách thao tác. |
| **Quy tắc nghiệp vụ** | Điều kiện cho phép, từ chối và các trường hợp đặc biệt. | Tránh lập trình hoặc kiểm thử theo cách hiểu riêng. |
| **Ví dụ cụ thể** | Đầu vào, trạng thái ban đầu, hành động, kết quả kỳ vọng. | Phát hiện mâu thuẫn và hỗ trợ kiểm chứng. |
| **Tiêu chí chấp nhận** | Điều kiện có thể kiểm tra để xác nhận hạng mục. | Tạo cơ sở trao đổi và chấp nhận sản phẩm. |
| **Giả định / câu hỏi mở** | Điều chưa biết, mức ảnh hưởng, ai cần quyết định, thời điểm cần câu trả lời. | Tránh biến bất định thành cam kết ngầm. |
| **Rủi ro và phụ thuộc** | Hệ thống liên quan, bảo mật, dữ liệu, độ tin cậy, vận hành. | Giúp lập kế hoạch thử nghiệm và chia nhỏ công việc. |
| **Quyết định đã thống nhất** | Điều được chọn, lý do, phạm vi, người quyết định và thời điểm. | Tránh tranh luận lại do mất ngữ cảnh. |

**Quyết định và giả định không giống nhau**: “Đợt đầu chỉ hỗ trợ hủy toàn bộ đơn trước đóng gói” là quyết định phạm vi; “dịch vụ thanh toán sẽ trả kết quả trong vài giây” là giả định cần kiểm chứng. Hai thông tin nên được ghi riêng.

### 6.1. Mẫu ghi nhận gọn cho một hạng mục

~~~text
Story: Khách hàng tự hủy toàn bộ đơn trước khi kho đóng gói
Outcome mong muốn: Giảm yêu cầu liên hệ hỗ trợ để hủy đơn hợp lệ
Quy tắc đã chốt:
  - Chủ đơn được hủy khi trạng thái kho chưa bắt đầu đóng gói
  - Đơn đã trả tiền tạo một yêu cầu hoàn tiền
  - Thao tác lặp không tạo thêm yêu cầu hoàn tiền
Ví dụ: A, B, C, D, E, F (xem bảng đã thống nhất)
Tiêu chí chấp nhận: Hành vi hủy, từ chối, quyền truy cập, xử lý lặp
Câu hỏi mở: Hoàn tiền qua nhiều phương thức thanh toán
Quyết định phạm vi: Hủy từng phần và hoàn tiền phức hợp để backlog sau
Phụ thuộc: Hệ thống kho và cổng thanh toán
Người giải đáp câu hỏi mở: Đại diện nghiệp vụ thanh toán
~~~

Với hệ thống quản lý công việc, nhóm có thể đính kèm hoặc liên kết thông tin trên cùng một hạng mục backlog. Không nhất thiết lập thêm một kho tài liệu mới nếu các quyết định đã dễ tìm, được quản lý thay đổi và hiển thị cho người liên quan.

## 7. Trao đổi trong suốt vòng đời của yêu cầu

Ba góc nhìn cần cộng tác **trước, trong và sau khi phát triển**, với mức độ và nhịp phù hợp.

| Thời điểm | Câu hỏi chính | Hoạt động gợi ý |
|---|---|---|
| **Khám phá vấn đề** | Nhu cầu có thật không? Giá trị cho ai? | Nghiệp vụ đưa bối cảnh, kỹ thuật và kiểm thử tham gia đánh giá tính khả thi và rủi ro sớm. |
| **Làm rõ backlog** | Phạm vi nào đủ nhỏ và đủ rõ để bắt đầu? | Trao đổi Three Amigos, ví dụ, tiêu chí chấp nhận, phụ thuộc và câu hỏi còn mở. |
| **Chuẩn bị triển khai** | Môi trường, dữ liệu, giao diện tích hợp và phương án kiểm tra đã sẵn sàng đến đâu? | Chốt các giả định có tác động lớn, phân chia công việc, thiết lập cách kiểm chứng. |
| **Trong lúc phát triển** | Có phát hiện mới làm thay đổi hành vi mong đợi không? | Trao đổi ngắn theo vấn đề, cập nhật ví dụ, kiểm thử liên tục, hỏi ngay khi mâu thuẫn. |
| **Trước khi xem là hoàn thành** | Có đáp ứng tiêu chí và Definition of Done? | Xem kết quả kiểm thử, hành vi thực tế và rủi ro còn lại; xử lý lỗi và ngoại lệ quan trọng. |
| **Sau khi bàn giao** | Người dùng có đạt kết quả mong muốn không? | Thu phản hồi, quan sát chỉ số, đưa phát hiện về backlog và cải tiến cách phối hợp. |

Không nên đợi đến cuối Sprint mới hỏi nghiệp vụ về một quy tắc đang chặn lập trình. Ngược lại, không phải mọi câu hỏi đều cần một cuộc họp lớn. Nhóm có thể quyết định ngay trong trao đổi hai hoặc ba người, sau đó ghi lại kết luận tại nơi mọi người có thể tìm.

### 7.1. Definition of Ready và Definition of Done

Một số nhóm dùng **Definition of Ready (DoR)** như bộ tiêu chí giúp xem một hạng mục đã đủ thông tin để bắt đầu hay chưa: mục tiêu rõ, có ví dụ cơ bản, phụ thuộc quan trọng được nhận diện, phạm vi phù hợp. DoR là **thực hành tùy chọn**, không phải thành phần bắt buộc của Scrum. Nếu dùng quá cứng nhắc, nó có thể trở thành cổng phê duyệt khiến nhóm không dám bắt đầu các công việc khám phá còn bất định.

**Definition of Done (DoD)** xác định tiêu chuẩn chất lượng chung của Increment đã hoàn thành. Với hạng mục hủy đơn, nó có thể liên quan đến kiểm thử tự động cho quy tắc cốt lõi, tích hợp đã kiểm tra, quyền truy cập, ghi nhận sự kiện cần thiết, khả năng triển khai và tài liệu vận hành phù hợp. Một câu chuyện có tiêu chí chấp nhận đạt nhưng vẫn còn lỗi tích hợp nghiêm trọng chưa đáp ứng DoD thì chưa thể xem là Done.

Tiêu chí chấp nhận nói về **hành vi riêng của hạng mục**; DoD nói về **tiêu chuẩn chất lượng chung của phần mềm hoàn thành**. Chúng bổ sung cho nhau.

## 8. Kiểm thử sớm và liên tục: “shift left” theo hướng cộng tác

Đưa hoạt động kiểm thử sớm vào quá trình phát triển không có nghĩa chỉ giao cho kiểm thử viên thêm nhiệm vụ. Mục tiêu là các thành viên cùng chủ động làm rõ hành vi và kiểm soát rủi ro **trước khi lỗi được tạo ra hoặc lan rộng**.

### 8.1. Việc cần làm trước khi viết mã

- Hỏi lại các khái niệm nghiệp vụ mơ hồ: “đã gửi”, “hợp lệ”, “ngay lập tức”, “thành công”.
- Tìm trường hợp biên: giá trị rỗng, trạng thái chuyển tiếp, dữ liệu không nhất quán, yêu cầu lặp.
- Làm rõ quyền truy cập, tính riêng tư, khả năng tiếp cận và yêu cầu phi chức năng phù hợp.
- Xác định khả năng tạo dữ liệu thử và quan sát kết quả khi tích hợp với dịch vụ khác.
- Đề xuất phần việc nhỏ nhất có thể kiểm tra nhưng vẫn mang lại giá trị.

### 8.2. Việc cần làm trong khi phát triển

- Người phát triển và kiểm thử viên phối hợp kiểm tra hành vi mới từ sớm, không đợi gộp toàn bộ tính năng.
- Kiểm thử tự động được áp dụng nơi có giá trị: quy tắc nghiệp vụ, hợp đồng API, luồng tích hợp quan trọng và lỗi hồi quy đã biết.
- Kiểm thử khám phá được dùng để tìm các hành vi chưa có trong ví dụ ban đầu.
- Kết quả phát hiện được phản hồi ngay cho nghiệp vụ nếu liên quan tới quyết định quy tắc.
- Nhóm kiểm tra luồng lỗi và khôi phục, không chỉ đường đi “thành công”.

### 8.3. Chọn mức kiểm tra phù hợp

Trong ví dụ hủy đơn:

| Rủi ro | Kiểu kiểm tra có thể dùng | Ai cần phối hợp? |
|---|---|---|
| Quy tắc hủy theo trạng thái sai | Kiểm thử đơn vị hoặc lớp nghiệp vụ với các trạng thái. | Nghiệp vụ xác nhận quy tắc; phát triển và kiểm thử thiết kế trường hợp. |
| Tạo hai yêu cầu hoàn tiền | Kiểm thử xử lý lặp và tích hợp, có thể mô phỏng yêu cầu đồng thời. | Phát triển, kiểm thử, nhóm thanh toán khi cần. |
| Không đồng bộ trạng thái kho | Kiểm thử tích hợp/hợp đồng và tình huống cạnh tranh phù hợp. | Phát triển, kiểm thử, nhóm kho. |
| Người dùng hủy đơn của người khác | Kiểm tra phân quyền qua API và giao diện. | Phát triển, kiểm thử, chuyên gia bảo mật nếu cần. |
| Trạng thái hoàn tiền khó hiểu | Kiểm thử luồng người dùng và nội dung thông báo. | Nghiệp vụ, thiết kế, kiểm thử và người dùng đại diện. |
| Phát hành gây lỗi luồng đơn hiện có | Bộ kiểm thử hồi quy phù hợp và theo dõi sau phát hành. | Cả nhóm cùng chịu trách nhiệm về chất lượng. |

Không phải mọi kịch bản đều cần tự động hóa giao diện đầu cuối. Nhóm nên chọn mức kiểm thử có khả năng phát hiện rủi ro hiệu quả, dễ duy trì và cho phản hồi đủ nhanh.

## 9. Xử lý khi yêu cầu thay đổi hoặc các bên bất đồng

Agile khuyến khích phản hồi với thay đổi, nhưng thay đổi cần được **đánh giá có chủ đích**. Mục tiêu của trao đổi là ra quyết định dựa trên giá trị, rủi ro và năng lực, không phải mặc định nhận mọi yêu cầu mới hoặc bảo vệ tài liệu cũ bằng mọi giá.

### 9.1. Khi có yêu cầu thay đổi

Giả sử giữa quá trình làm chức năng hủy đơn, bộ phận kinh doanh đề nghị cho khách hủy **một phần đơn đã thanh toán**. Điều đó có thể ảnh hưởng quy tắc hoàn tiền, giá khuyến mại, tồn kho, phí vận chuyển và báo cáo kế toán.

Nhóm có thể thực hiện trình tự ngắn:

1. **Làm rõ động cơ:** người dùng nào cần hủy từng phần, vấn đề hiện tại nghiêm trọng đến đâu?
2. **Đánh giá tác động:** quy tắc nào, tích hợp nào, kiểm thử nào và lịch bàn giao nào bị ảnh hưởng?
3. **So sánh lựa chọn:** làm ngay, chia thành thử nghiệm riêng, hoãn vào backlog hoặc điều chỉnh phạm vi hiện tại.
4. **Ra quyết định với người có thẩm quyền:** Product Owner hoặc người chịu trách nhiệm ưu tiên phối hợp với các bên cần thiết.
5. **Cập nhật thông tin chung:** story, tiêu chí chấp nhận, ví dụ, câu hỏi mở, thử nghiệm và dự báo liên quan.

Trong Scrum, khi có thông tin mới trong Sprint, Developers và Product Owner có thể làm rõ và thương lượng phạm vi mà vẫn bảo vệ **Sprint Goal**. Trong Kanban, nhóm áp dụng quy tắc ưu tiên và chính sách xử lý công việc khẩn cấp; thay đổi không đồng nghĩa với mở vô hạn hạng mục đang làm.

### 9.2. Khi hai góc nhìn không thống nhất

Ví dụ: nghiệp vụ muốn thông báo “Hủy đơn thành công” ngay khi khách nhấn nút; kiểm thử cho rằng thông điệp đó sai nếu máy chủ chưa ghi nhận; phát triển cho biết hoàn tiền có thể xử lý bất đồng bộ.

Thay vì tranh luận ai “đúng hơn”, nhóm trở lại hai câu hỏi:

- **Sự thật nghiệp vụ nào cần được bảo đảm?** Đơn chỉ được coi là đã hủy khi hệ thống ghi nhận việc hủy hợp lệ.
- **Người dùng cần biết gì tại mỗi trạng thái?** Hủy đã thành công, còn hoàn tiền vẫn đang xử lý; nếu hủy thất bại thì không được thông báo thành công.

Từ đó, các bên có thể thống nhất nội dung hiển thị và tiêu chí chấp nhận phù hợp với trạng thái hệ thống. **Ví dụ cụ thể giúp chuyển bất đồng trừu tượng thành quyết định có thể kiểm tra.**

### 9.3. Quản lý câu hỏi chưa có lời giải

Với câu hỏi quan trọng chưa được quyết định, nên ghi lại:

| Trường thông tin | Ví dụ |
|---|---|
| Câu hỏi | Hệ thống hỗ trợ hoàn tiền một phần qua thẻ và ví điện tử ở giai đoạn nào? |
| Rủi ro nếu bỏ ngỏ | Có thể triển khai luồng hủy sai phạm vi hoặc tính tiền không chính xác. |
| Người quyết định/cung cấp bằng chứng | Người phụ trách sản phẩm và chuyên gia thanh toán. |
| Hạn cần giải đáp | Trước khi bắt đầu hạng mục hoàn tiền một phần. |
| Tạm thời xử lý | Đưa hủy một phần ngoài phạm vi Increment đầu tiên. |

Không cần viết tài liệu dài, nhưng phải tránh tình trạng mỗi người tự giả định một câu trả lời rồi phát triển theo hướng khác nhau.

## 10. Tổ chức trao đổi hiệu quả khi làm việc phân tán

Nhóm làm việc từ xa hoặc nhiều múi giờ càng cần một nơi lưu thông tin dễ tìm và một quy tắc phản hồi phù hợp.

- **Ghi quyết định gần nơi thực hiện công việc:** ví dụ gắn với user story, tiêu chí chấp nhận và liên kết tới thảo luận liên quan.
- **Dùng trao đổi bất đồng bộ cho câu hỏi đơn giản:** mô tả rõ bối cảnh, điều cần quyết định, ví dụ cụ thể và thời điểm cần trả lời.
- **Chuyển sang thảo luận trực tiếp khi cần:** nếu có nhiều giả định, tranh luận kéo dài, ảnh hưởng hệ thống hoặc liên quan nhiều vai trò.
- **Kết thúc bằng kết luận có thể tra cứu:** điều gì đã thống nhất, điều gì vẫn mở, ai cần làm gì và có tác động nào đến backlog.
- **Tránh thông tin nằm trong tin nhắn riêng:** một quyết định thay đổi hành vi hệ thống cần được chia sẻ cho người phát triển và kiểm thử liên quan.

Một cuộc họp thành công không phải cuộc họp dài nhất hay có nhiều người tham dự nhất. Nó tạo ra **quyết định hoặc hiểu biết mới**, giúp công việc tiếp tục với ít rủi ro hiểu nhầm hơn.

### 10.1. Ví dụ cấu trúc phiên trao đổi ngắn

Với một user story có phạm vi vừa, nhóm có thể thử lịch trình minh họa dưới đây. Thời lượng chỉ mang tính gợi ý, tùy độ phức tạp và số câu hỏi thực tế.

| Phần | Nội dung | Đầu ra |
|---|---|---|
| 5 phút | Nghiệp vụ trình bày người dùng, vấn đề và giá trị mong muốn. | Mục tiêu và phạm vi sơ bộ được hiểu chung. |
| 10 phút | Ba bên nêu quy tắc và minh họa trường hợp thông thường. | Các ví dụ chính, hành vi mong đợi. |
| 10 phút | Tìm trường hợp biên, phụ thuộc và rủi ro; phát triển và kiểm thử đặt câu hỏi. | Tiêu chí chấp nhận, câu hỏi chưa rõ và rủi ro được ghi. |
| 5 phút | Chốt việc có thể bắt đầu, việc cần chia nhỏ, người phụ trách giải đáp. | Quyết định và bước tiếp theo. |

Nếu cuộc trao đổi cho thấy hạng mục quá lớn, đừng kéo dài chỉ để “chốt cho xong”. Hãy chia nhỏ công việc hoặc xác định thử nghiệm kỹ thuật/nghiệp vụ cần làm trước.

## 11. Đo lường chất lượng phối hợp và cải tiến

Hiệu quả trao đổi cần được xem qua **tác động lên công việc**, không chỉ số lượng cuộc họp, số comment hoặc số kịch bản kiểm thử. Các chỉ số sau giúp nhóm đặt câu hỏi cải tiến:

| Tín hiệu | Cần quan sát | Cách diễn giải thận trọng |
|---|---|---|
| **Thời gian bị chặn vì thiếu quyết định** | Hạng mục chờ bao lâu để có quy tắc hoặc thông tin cần thiết? | Chờ lâu có thể cần mời đúng người sớm hơn hoặc rõ quyền quyết định. |
| **Công việc phải làm lại do hiểu sai yêu cầu** | Bao nhiêu thay đổi phát sinh vì thiếu thống nhất hành vi? | Tỷ lệ tăng có thể cho thấy ví dụ và tiêu chí chấp nhận chưa đủ rõ. |
| **Lỗi lọt ra sau bàn giao** | Lỗi nghiệp vụ, tích hợp, quyền truy cập có lặp lại không? | Xem nguyên nhân cụ thể thay vì quy lỗi cho riêng kiểm thử. |
| **Cycle time và work item age** | Một hạng mục mất bao lâu từ lúc bắt đầu đến lúc hoàn thành, và việc nào đang già đi bất thường? | Tắc nghẽn có thể ở yêu cầu, kiểm thử, tích hợp hoặc phối hợp ngoài nhóm. |
| **Tỷ lệ hạng mục quay lại bước làm rõ** | Khi đang thực hiện, có nhiều câu hỏi quan trọng mới xuất hiện không? | Không phải mọi câu hỏi mới là thất bại; xem câu hỏi nào đáng lẽ được phát hiện sớm. |
| **Phản hồi người dùng** | Phần mềm có thực sự giúp người dùng đạt kết quả mong muốn không? | Hoàn thành đúng tiêu chí ban đầu vẫn có thể cần điều chỉnh nếu giá trị chưa đạt. |

Ví dụ, nếu nhiều hạng mục chỉ bị chặn khi bắt đầu kiểm thử tích hợp, nhóm có thể thử mời người hiểu hệ thống phụ thuộc vào buổi làm rõ và chuẩn bị dữ liệu thử sớm hơn. Sau vài chu kỳ, xem số trường hợp bị chặn, thời gian chờ và lỗi tích hợp có thay đổi hay không.

Các chỉ số không nên biến thành bảng xếp hạng cá nhân hoặc công cụ gây áp lực buộc mọi người báo “không có vấn đề”. Khi nhóm an toàn để nêu câu hỏi và rủi ro, họ có cơ hội phát hiện và giải quyết vấn đề sớm hơn.

## 12. Những sai lầm thường gặp

| Cách làm dễ gây vấn đề | Tác động | Thử cải thiện |
|---|---|---|
| Nghiệp vụ chỉ đưa một danh sách tính năng rồi rời khỏi quá trình. | Các quyết định ngầm được giao cho người triển khai; kết quả dễ lệch nhu cầu. | Cung cấp mục tiêu, ví dụ và người có thể trả lời câu hỏi khi phát sinh. |
| Kiểm thử chỉ tham gia khi “code xong”. | Ngoại lệ và ranh giới được phát hiện quá muộn. | Mời góc nhìn kiểm thử ngay khi làm rõ hạng mục nhiều rủi ro. |
| Phát triển chỉ hỏi thông số kỹ thuật mà không hiểu giá trị. | Dễ tối ưu sai thứ tự ưu tiên hoặc xây giải pháp phức tạp không cần thiết. | Mở đầu bằng vấn đề và outcome của người dùng. |
| Story rất lớn nhưng vẫn cố “chốt” trong một buổi. | Nhiều giả định bị che giấu, ước lượng thiếu tin cậy. | Chia nhỏ theo lát giá trị hoặc thử nghiệm giảm bất định. |
| Tiêu chí chấp nhận chỉ ghi “hoạt động đúng”. | Không đủ để thống nhất hoặc kiểm tra. | Thêm ví dụ cho trường hợp thông thường, biên và lỗi. |
| Viết hàng trăm bước kiểm thử mà không có quy tắc và mục tiêu. | Nặng bảo trì, khó nhìn thấy hành vi quan trọng. | Trước tiên chốt quy tắc và ví dụ; thiết kế kiểm thử theo rủi ro. |
| Câu trả lời nằm trong cuộc trò chuyện riêng, không cập nhật backlog. | Người khác tiếp tục làm theo hiểu biết cũ. | Ghi quyết định và cập nhật tiêu chí chấp nhận tại nơi làm việc chung. |
| Mọi thay đổi đều bổ sung ngay vào phạm vi đang làm. | Mất tập trung, công việc dang dở tăng, khó bàn giao. | Đánh giá giá trị, chi phí, rủi ro và thương lượng thứ tự ưu tiên. |
| Dùng cuộc họp làm cổng phê duyệt hình thức. | Tăng thời gian chờ nhưng không giảm bất định. | Chỉ họp khi cần trao đổi để ra quyết định; dùng cách bất đồng bộ khi đủ. |
| Coi người kiểm thử là người duy nhất chịu trách nhiệm chất lượng. | Thiếu phối hợp từ lúc định nghĩa đến khi vận hành. | Cả nhóm cùng tạo Increment đạt chất lượng; phân rõ đóng góp theo chuyên môn. |

## 13. Áp dụng trong Scrum, Kanban và XP

### Với Scrum

**Product Backlog refinement** là hoạt động làm rõ và chia nhỏ các Product Backlog Item; Scrum không quy định một cuộc họp Three Amigos cố định. Nhóm có thể dùng trao đổi ba góc nhìn trong quá trình refinement để làm rõ ví dụ, tiêu chí và phụ thuộc.

Khi Sprint bắt đầu, Developers lập kế hoạch hướng tới **Sprint Goal**; nếu phát hiện quy tắc mới trong Sprint, nhóm trao đổi ngay để điều chỉnh kế hoạch, thương lượng phạm vi với Product Owner khi cần. **Sprint Review** tạo cơ hội kiểm tra Increment cùng bên liên quan và cập nhật backlog theo phản hồi, còn **Sprint Retrospective** giúp cải thiện cách phối hợp.

### Với Kanban

Kanban phù hợp với luồng công việc liên tục. Nhóm có thể thể hiện rõ các trạng thái như **cần làm rõ**, **sẵn sàng xử lý**, **đang làm**, **đang kiểm tra**, **hoàn thành**, cùng chính sách chuyển trạng thái và giới hạn WIP phù hợp.

Khi có việc chờ câu trả lời từ nghiệp vụ, cần nhìn thấy điểm nghẽn trên bảng. Nhóm nên chủ động giải quyết hạng mục đang chờ thay vì liên tục mở thêm việc mới. Các thước đo dòng công việc hỗ trợ nhận biết nơi trao đổi chậm hoặc thiếu quyết định.

### Với Extreme Programming (XP)

XP coi phản hồi nhanh và chất lượng kỹ thuật là nền tảng. **Thực hành cùng làm rõ ví dụ** kết hợp với TDD, lập trình cặp, tích hợp liên tục và kiểm thử tự động có thể giảm khoảng cách giữa yêu cầu và phần mềm chạy được.

Nhóm vẫn cần trao đổi về giá trị và quy tắc nghiệp vụ, không nên coi bộ kiểm thử tự động là đủ để chứng minh người dùng đã nhận được kết quả họ cần.

Ba cách tiếp cận có thể bổ sung cho nhau khi phù hợp: Scrum giúp tạo nhịp mục tiêu và phản hồi, Kanban giúp nhìn thấy dòng công việc và điểm tắc, XP củng cố khả năng thay đổi mã an toàn. **Cuộc trao đổi liên chức năng phục vụ sự hiểu biết chung**, không phụ thuộc tên phương pháp mà nhóm sử dụng.

## 14. Danh sách kiểm tra để tự áp dụng

Trước khi bắt đầu thực hiện một hạng mục có rủi ro hoặc chưa rõ, nhóm có thể tự hỏi:

- [ ] Đã biết nhóm người dùng, mục tiêu và vấn đề cần giải quyết chưa?
- [ ] Có người làm rõ quy tắc nghiệp vụ và người có quyền quyết định khi cần chưa?
- [ ] Người phát triển đã nêu phụ thuộc, trạng thái dữ liệu và tác động kỹ thuật chính chưa?
- [ ] Người có góc nhìn kiểm thử đã xem hành vi thông thường, ngoại lệ, phân quyền và tình huống lỗi chưa?
- [ ] Có ví dụ đủ cụ thể để phân biệt các trường hợp dễ hiểu khác nhau chưa?
- [ ] Tiêu chí chấp nhận có thể kiểm tra được, không chỉ ghi “chạy đúng” chưa?
- [ ] Câu hỏi còn mở được ghi rõ người xử lý và tác động tới phạm vi chưa?
- [ ] Hạng mục đã đủ nhỏ để tạo ra kết quả có thể đánh giá chưa?
- [ ] Cả nhóm hiểu Definition of Done và cách kiểm chứng chất lượng chưa?
- [ ] Có cách tiếp nhận phản hồi sau bàn giao và cập nhật backlog chưa?

Đây là **công cụ hỗ trợ trao đổi**, không phải quy định mọi hạng mục bắt buộc phải qua một cổng phê duyệt cố định. Công việc khám phá bản thân nó có thể bắt đầu khi còn nhiều điều chưa biết, miễn là mục tiêu học hỏi và cách đánh giá kết quả được xác định rõ.

## 15. Kết luận

**Tổ chức trao đổi giữa nghiệp vụ, phát triển và kiểm thử** giúp nhóm Agile chuyển một yêu cầu còn mơ hồ thành sự hiểu biết chung về **giá trị, quy tắc, hành vi và cách kiểm chứng**. Nghiệp vụ góp bối cảnh và quyết định ưu tiên; phát triển góp hiểu biết hệ thống và cách triển khai; kiểm thử giúp phát hiện ranh giới, rủi ro và xây dựng chiến lược xác minh. Chất lượng phần mềm là trách nhiệm phối hợp của cả nhóm.

Thực hành Three Amigos, Example Mapping, user story, tiêu chí chấp nhận và ví dụ Given–When–Then có thể hỗ trợ quá trình này, nhưng giá trị thực nằm ở những câu hỏi được giải đáp và quyết định được chia sẻ kịp thời. Khi phản hồi làm thay đổi yêu cầu, nhóm đánh giá tác động, điều chỉnh backlog và tiếp tục giao sản phẩm từng phần. Nhờ vậy, **yêu cầu thích ứng trở thành khả năng học hỏi và phản hồi liên tục**, thay vì chuỗi tài liệu chuyển giao giữa các bộ phận.
