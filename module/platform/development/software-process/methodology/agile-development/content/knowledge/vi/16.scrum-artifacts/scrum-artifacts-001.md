# Product Backlog và cam kết Product Goal

## 1. Vì sao Scrum cần cả Product Backlog và Product Goal?

Trong một sản phẩm phần mềm, ý tưởng và yêu cầu thường nhiều hơn năng lực của Scrum Team: chức năng mới, lỗi, cải tiến trải nghiệm, kiểm soát bảo mật, thay đổi tích hợp, nợ kỹ thuật và những câu hỏi cần khám phá. Nếu chỉ giữ một danh sách công việc rồi làm lần lượt theo người gửi yêu cầu, nhóm có thể rất bận nhưng không biết liệu sản phẩm có tiến gần hơn tới giá trị mong muốn hay không.

Scrum giải quyết tình trạng đó bằng một cặp khái niệm liên kết:

- **Product Backlog** là artifact chứa **danh sách nổi lên và được sắp thứ tự** của những gì cần thiết để cải thiện sản phẩm. Đây là **nguồn công việc duy nhất** mà Scrum Team thực hiện cho sản phẩm.
- **Product Goal** là **cam kết (commitment) của Product Backlog**: mô tả trạng thái tương lai của sản phẩm mà Scrum Team hướng tới. Nó tạo một đích chung để nhóm lập kế hoạch và kiểm tra tiến độ.

Product Backlog trả lời **“chúng ta có thể cần làm gì, theo thứ tự nào?”**; Product Goal trả lời **“vì sao các lựa chọn đó cùng hướng tới một trạng thái sản phẩm có giá trị?”**.

Ví dụ, một nền tảng học trực tuyến nhận hàng chục đề xuất: thêm bộ lọc khóa học, sửa lỗi đăng ký trùng, tích hợp thanh toán, xây bảng thống kê, gửi SMS, cải thiện quyền truy cập. Nếu Product Goal hiện tại là **giúp học viên tự đăng ký khóa học miễn phí một cách đáng tin cậy**, nhóm sẽ đánh giá các hạng mục theo mức đóng góp vào mục tiêu đó, thay vì mặc định tất cả đề nghị đều phải được làm ngay.

Đây là nội dung quan trọng của **AGILE_DEVELOPMENT**: dùng mục tiêu và backlog để thích ứng với phản hồi sớm, giao Increment có giá trị, cộng tác giữa người dùng và Developers, đồng thời cải tiến cách làm qua những vòng kiểm tra–thích ứng.

> **Thông điệp chính:** Backlog là công cụ ra quyết định và giao tiếp về sản phẩm, không phải kho chứa lời hứa thực hiện mọi yêu cầu. Product Goal làm cho việc sắp thứ tự backlog có một mục đích rõ ràng.

## 2. Product Backlog là artifact nào trong Scrum?

### 2.1. Định nghĩa theo Scrum Guide 2020

**Product Backlog** là một danh sách **nổi lên (emergent)** và **được sắp thứ tự (ordered)** của những điều cần thiết để cải thiện sản phẩm. Nó là **nguồn công việc duy nhất do Scrum Team thực hiện**. “Nổi lên” có nghĩa là nội dung và mức hiểu biết về các hạng mục sẽ thay đổi khi nhóm học thêm từ người dùng, kỹ thuật, thị trường hoặc sản phẩm đang vận hành.

Danh sách này không đòi hỏi mọi yêu cầu phải được biết trước và cũng không yêu cầu mọi hạng mục được đặc tả chi tiết ngay từ ngày đầu. Những mục gần thời điểm thực hiện thường rõ và nhỏ hơn các ý tưởng ở xa.

Một **Product Backlog Item (PBI)** có thể là:

| Loại nhu cầu | Ví dụ | Giá trị hoặc vấn đề cần giải quyết |
| --- | --- | --- |
| **Khả năng sản phẩm** | Học viên tự đăng ký khóa học miễn phí. | Giảm thao tác thủ công, giúp học viên tự phục vụ. |
| **Cải tiến trải nghiệm** | Làm rõ trạng thái đăng ký thất bại. | Giảm nhầm lẫn và yêu cầu hỗ trợ. |
| **Lỗi / khiếm khuyết** | Sửa tình trạng tạo đăng ký trùng. | Bảo vệ dữ liệu và niềm tin người dùng. |
| **Yêu cầu an toàn** | Ngăn học viên xem đăng ký của người khác. | Bảo vệ quyền riêng tư và kiểm soát truy cập. |
| **Cải tiến kỹ thuật** | Bổ sung contract test cho dịch vụ dữ liệu khóa học. | Giảm rủi ro lỗi tích hợp và thời gian sửa về sau. |
| **Khám phá / học hỏi** | Thử nghiệm xem học viên có hiểu thông báo xác nhận không. | Kiểm tra giả định trước khi đầu tư tính năng lớn. |
| **Nghĩa vụ vận hành** | Nâng cấp thành phần hết hỗ trợ trước hạn. | Giảm rủi ro gián đoạn hoặc vi phạm quy định áp dụng. |

Không có quy tắc rằng Product Backlog chỉ được chứa user story hướng tới giao diện hoặc chỉ chứa yêu cầu kinh doanh. Tuy nhiên, các mục cần được xem xét trong **bối cảnh cải thiện sản phẩm và Product Goal**, chứ không chỉ vì người nào đó muốn nhóm “có việc làm”.

### 2.2. “Một nguồn công việc” không có nghĩa chỉ được dùng một công cụ

Một Scrum Team có thể lưu Product Backlog trên hệ thống quản lý công việc và liên kết với tài liệu nghiên cứu, phản hồi khách hàng, mã nguồn hoặc kết quả kiểm thử. Điều quan trọng là các bên có **một nguồn tham chiếu nhất quán về công việc sản phẩm và thứ tự của nó**.

Nếu cùng một sản phẩm có nhiều Scrum Team, Scrum Guide nêu rằng họ sử dụng **một Product Backlog cho sản phẩm đó**. Việc chia các bảng hiển thị riêng theo nhóm có thể hữu ích cho thao tác, nhưng không nên biến thành những thứ tự ưu tiên sản phẩm xung đột và không có đầu mối chịu trách nhiệm.

Ngược lại, tổ chức có nhiều sản phẩm khác nhau cần xác định rõ ranh giới sản phẩm trước khi quyết định có bao nhiêu Product Backlog.

### 2.3. Sản phẩm có ranh giới như thế nào?

Theo Scrum Guide, một **product** là phương tiện để mang lại giá trị, có **ranh giới rõ ràng**, stakeholder đã biết và người dùng hoặc khách hàng được xác định; sản phẩm có thể là dịch vụ, vật thể hữu hình hoặc thứ trừu tượng hơn.

Với nền tảng học trực tuyến, nhóm cần thống nhất:

- Sản phẩm bao gồm chỉ **luồng đăng ký khóa học**, hay toàn bộ hành trình tìm–đăng ký–theo dõi quá trình học?
- Ai là người dùng, khách hàng, stakeholder và bên quản trị?
- Những hệ thống thanh toán, danh tính, quản lý lớp học thuộc phạm vi sản phẩm hay là hệ thống phụ thuộc?
- Kết quả nào cho thấy sản phẩm đang mang lại giá trị?

Nếu ranh giới quá rộng, mục tiêu khó tập trung; nếu ranh giới quá hẹp chỉ theo một tầng công nghệ, backlog dễ biến thành danh sách công việc kỹ thuật tách khỏi giá trị người dùng.

## 3. Product Goal: cam kết của Product Backlog

### 3.1. Product Goal diễn tả trạng thái tương lai

**Product Goal** mô tả **trạng thái tương lai của sản phẩm** có thể đóng vai trò làm mục tiêu để Scrum Team lập kế hoạch. Nó được đặt trong **Product Backlog**, và phần còn lại của Product Backlog nổi lên để xác định những điều có thể đưa sản phẩm tới trạng thái ấy.

Theo Scrum Guide 2020, Product Goal là **mục tiêu dài hạn của Scrum Team**. Scrum Team phải **hoàn thành hoặc từ bỏ một mục tiêu** trước khi nhận mục tiêu kế tiếp. Từ bỏ mục tiêu có thể là một quyết định đúng khi phản hồi chứng minh nhu cầu đã khác; điều quan trọng là **minh bạch việc thay đổi đích**, không để nhiều mục tiêu không liên hệ cạnh tranh âm thầm.

Product Goal không phải:

- Bản danh sách tất cả tính năng sẽ phát triển.
- Cam kết rằng mọi Product Backlog Item đều được hoàn thành.
- Một thời hạn do Scrum bắt buộc áp đặt cho mọi nhóm.
- Một Sprint Goal được kéo dài thêm vài tháng.
- Một câu khẩu hiệu rộng đến mức không thể nhận biết tiến bộ.

### 3.2. Phân biệt Product Vision, Product Goal và Sprint Goal

| Tầng định hướng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Tầm nhìn sản phẩm (product vision)** | Sản phẩm tồn tại để giải quyết vấn đề rộng nào, cho ai? | Học viên có thể tiếp cận và quản lý quá trình tham gia khóa học thuận tiện, đáng tin cậy. |
| **Product Goal** | Trạng thái sản phẩm tiếp theo nào đáng theo đuổi trong dài hạn? | Học viên đủ điều kiện có thể tự tìm và đăng ký khóa học miễn phí trên web, không cần nhân viên xử lý các trường hợp thông thường. |
| **Sprint Goal** | Sprint gần này tạo ra hoặc tiến gần một kết quả cụ thể nào? | Học viên thử nghiệm có thể đăng ký một khóa miễn phí còn chỗ và thấy xác nhận chính xác. |
| **Increment** | Khả năng sản phẩm nào đã thực sự được hoàn tất? | Luồng đăng ký tích hợp, bảo vệ quyền, kiểm thử dữ liệu và đáp ứng Definition of Done. |

**Product Vision** là công cụ định hướng hữu ích trong quản lý sản phẩm nhưng không phải một trong ba cam kết của Scrum Guide. **Product Goal, Sprint Goal và Definition of Done** mới là ba cam kết gắn tương ứng với **Product Backlog, Sprint Backlog và Increment**.

### 3.3. Một Product Goal hữu ích có đặc điểm gì?

Một Product Goal nên:

1. **Hướng về giá trị hoặc năng lực sản phẩm**, không chỉ mô tả dự án xây phần mềm.
2. **Nêu rõ người dùng/đối tượng và phạm vi**, để nhóm không phải đoán “sản phẩm” nào đang được nói tới.
3. **Thể hiện trạng thái tương lai đủ cụ thể** để kiểm tra tiến độ và biết khi nào đạt hoặc nên thay đổi.
4. **Tạo trọng tâm** cho việc sắp thứ tự Product Backlog mà không khóa cứng mọi giải pháp kỹ thuật.
5. **Đủ tham vọng cho một giai đoạn dài hơn Sprint**, nhưng vẫn có khả năng tiến tới bằng các Increment.
6. **Được truyền đạt và hiểu chung** bởi Scrum Team cùng những stakeholder phù hợp.

Ví dụ so sánh:

| Cách viết | Nhận xét |
| --- | --- |
| “Xây 25 API và 12 trang giao diện.” | Danh sách đầu ra kỹ thuật, chưa nêu trạng thái người dùng có thể đạt. |
| “Trở thành nền tảng giáo dục tốt nhất.” | Quá rộng; khó định nghĩa bằng chứng đã hoàn thành. |
| “Học viên đủ điều kiện có thể tự đăng ký khóa học miễn phí trên web mà không cần xử lý thủ công trong các trường hợp thông thường.” | Nêu người dùng, năng lực tương lai và ranh giới ban đầu tương đối rõ. |
| “Tăng tỷ lệ học viên hoàn tất đăng ký từ mức nền đã đo lên mức mục tiêu đã thảo luận trong quý này.” | Có thể là mục tiêu outcome hữu ích nếu có dữ liệu nền, cách đo và điều kiện phụ thuộc rõ. |

Scrum **không bắt buộc mọi Product Goal phải viết theo công thức SMART hay OKR**. Những cách biểu đạt đó có thể hỗ trợ cuộc trao đổi nhưng không thay thế việc hiểu đúng giá trị và ranh giới sản phẩm.

### 3.4. Phân biệt điều nhóm giao được và outcome cần kiểm chứng

Một Product Goal định hướng giá trị có thể bao gồm giả thuyết rằng sản phẩm sẽ cải thiện hành vi người dùng. Cần phân biệt:

- **Khả năng sản phẩm nằm trong quyền kiểm soát nhóm:** xây Increment đáp ứng DoD, có thể sử dụng an toàn cho người dùng dự định.
- **Kết quả sử dụng:** tỷ lệ hoàn tất đăng ký, thời gian hỗ trợ, độ hài lòng; còn chịu ảnh hưởng của mùa vụ, nội dung khóa học, lượng truy cập và các yếu tố ngoài sản phẩm.

Nếu chưa có số liệu nền, nhóm có thể bắt đầu bằng một mục tiêu về **trạng thái năng lực sản phẩm**, kèm giả thuyết đo lường. Đừng tự hứa “tăng 50% chuyển đổi” khi chưa biết tỷ lệ hiện tại hoặc cách kiểm chứng.

## 4. Ai chịu trách nhiệm về Product Goal và Product Backlog?

### 4.1. Product Owner có accountability rõ ràng

Theo Scrum Guide 2020, **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm từ công việc của Scrum Team. Product Owner cũng chịu trách nhiệm quản lý Product Backlog hiệu quả, bao gồm:

1. **Phát triển và truyền đạt rõ Product Goal.**
2. **Tạo và truyền đạt rõ các Product Backlog Items.**
3. **Sắp xếp thứ tự Product Backlog Items.**
4. **Bảo đảm Product Backlog minh bạch, dễ thấy và được hiểu.**

Product Owner có thể **ủy quyền người khác thực hiện các hoạt động này**, nhưng **vẫn chịu trách nhiệm cuối cùng**. Product Owner là **một người, không phải một hội đồng**; tổ chức cần tôn trọng các quyết định về Product Backlog để vai trò này có hiệu quả.

### 4.2. Developers và Scrum Master đóng góp thế nào?

| Câu hỏi công việc | Product Owner | Developers | Scrum Master |
| --- | --- | --- | --- |
| **Sản phẩm hướng tới trạng thái nào?** | Chịu trách nhiệm phát triển/truyền đạt Product Goal. | Đóng góp bằng chứng khả thi, rủi ro và hiểu biết sản phẩm. | Hỗ trợ cách xác lập, cộng tác và hiểu rõ mục tiêu. |
| **Nên làm gì trước?** | Chịu trách nhiệm thứ tự Product Backlog. | Cung cấp hiểu biết kích thước, phụ thuộc, kỹ thuật và phương án chia nhỏ. | Giúp Scrum Team và stakeholder hiểu quyết định, tương tác hiệu quả. |
| **Kích thước PBI được đánh giá ra sao?** | Có thể ảnh hưởng thông qua đánh đổi và làm rõ. | **Chịu trách nhiệm sizing** các PBI sẽ thực hiện. | Hỗ trợ kỹ thuật cộng tác khi cần. |
| **Sprint sẽ thực hiện những hạng mục nào?** | Trao đổi về mục tiêu và thứ tự Product Backlog. | Lựa chọn hạng mục có thể làm và lập kế hoạch Sprint trong Sprint Planning. | Hỗ trợ Scrum và sự kiện diễn ra hiệu quả. |
| **PBI đã Done chưa?** | Cung cấp hiểu biết về hành vi/kết quả mong đợi. | Tạo Increment và tuân thủ Definition of Done. | Giúp nhóm duy trì tính minh bạch và hiệu quả. |

Người dùng, khách hàng, chuyên gia nghiệp vụ, bảo mật hoặc các nhóm phụ thuộc là **nguồn thông tin quan trọng**, nhưng không nên biến Product Backlog thành nơi mọi stakeholder đều có thể trực tiếp áp đặt thứ tự riêng.

### 4.3. Product Owner không phải thư ký ghi mọi yêu cầu

Một Product Owner hiệu quả **chủ động lựa chọn, từ chối, trì hoãn, chia nhỏ và thay đổi thứ tự** khi có bằng chứng mới. Họ cần hiểu nhu cầu người dùng và bối cảnh kinh doanh, đồng thời lắng nghe Developers về những giới hạn kỹ thuật, nợ kỹ thuật và rủi ro.

Ngược lại, Product Owner không nên chỉ nhận một danh sách yêu cầu cố định từ cấp trên rồi chuyển nguyên cho Developers. Khi không có quyền xác định thứ tự hoặc không tiếp cận được stakeholder, trách nhiệm quản lý backlog dễ trở thành hình thức.

## 5. Một Product Backlog Item tốt cần đủ thông tin gì?

### 5.1. Không có khuôn mẫu PBI bắt buộc

Scrum Guide không yêu cầu PBI phải là **user story**, **epic**, **feature** hay một định dạng ticket cụ thể. Những cách thể hiện đó là công cụ nhóm có thể lựa chọn. Điều quan trọng là đủ minh bạch để thảo luận giá trị, quy mô, phụ thuộc, rủi ro và khả năng hoàn tất.

Một PBI thường nên trả lời:

- **Nhu cầu/điều kiện nào** cần cải thiện và **ai** nhận lợi ích?
- **Kết quả hoặc hành vi** nào sẽ thay đổi?
- **Vì sao bây giờ** điều đó đáng làm so với các mục khác?
- **Độ lớn và bất định** ra sao, có thể chia nhỏ không?
- **Phụ thuộc, ràng buộc và tình huống lỗi** quan trọng nào cần làm rõ?
- **Tiêu chí chấp nhận hoặc bằng chứng** nào cho biết hành vi mong muốn đã đạt?

Những PBI ở xa có thể chưa cần đủ mọi câu trả lời. Khi đến gần thời điểm Sprint Planning, mức chi tiết cần đủ để Developers dự báo khả năng hoàn tất và tạo Increment đạt DoD.

### 5.2. Cấu trúc tham khảo của một PBI

| Trường tham khảo | Ví dụ | Vì sao hữu ích |
| --- | --- | --- |
| **Tên ngắn** | Học viên đăng ký khóa miễn phí còn chỗ | Giúp nhận ra vấn đề/khả năng. |
| **Bối cảnh giá trị** | Học viên phải nhờ nhân viên xử lý thủ công | Kết nối với Product Goal. |
| **Người dùng / tình huống** | Học viên đã đăng nhập, khóa học còn chỗ | Làm rõ ranh giới sử dụng. |
| **Hành vi kỳ vọng** | Gửi đăng ký, lưu hợp lệ, nhận xác nhận | Dùng cho trao đổi và kiểm thử. |
| **Ngoài phạm vi** | Chưa có thanh toán, danh sách chờ, SMS | Tránh mở rộng âm thầm. |
| **Phụ thuộc/rủi ro** | API sức chứa, tính đồng thời, quyền truy cập | Giúp lập thứ tự và giảm bất định. |
| **Kích thước tương đối** | Developers đánh giá sau refinement | Hỗ trợ dự báo và chia nhỏ. |
| **Điều kiện kiểm chứng** | Không vượt sức chứa, không đăng ký trùng | Cần để biết hành vi đúng. |

Các trường ở đây là **gợi ý thực hành**, không phải cấu trúc artifact bắt buộc của Scrum. Có thể lưu ví dụ, link tài liệu và lịch sử quyết định ở nơi tiện truy cập thay vì sao chép mọi nội dung vào ticket.

### 5.3. User story là lời mời trao đổi, không phải toàn bộ đặc tả

Một cách diễn đạt:

> Là một học viên đã đăng nhập, tôi muốn đăng ký một khóa học miễn phí còn chỗ để tham gia học mà không phải nhờ nhân viên hỗ trợ.

User story giúp nhóm nhớ tới **ai – muốn gì – vì sao**. Nó chưa nói rõ khi nhấn nút hai lần, khi chỗ cuối bị hai người chọn hoặc khi lỗi mạng xảy ra thì hành vi đúng là gì. Những điều ấy cần được **làm rõ qua trao đổi và ví dụ** trước hoặc trong lúc phát triển, tùy mức rủi ro.

Không nên lấy việc có đủ ba vế của câu user story làm bằng chứng rằng hạng mục đã sẵn sàng hoặc đã đúng.

## 6. Product Backlog refinement: từ ý tưởng lớn tới PBI có thể làm

### 6.1. Refinement là hoạt động liên tục

**Product Backlog refinement** là hoạt động **chia nhỏ và làm rõ thêm** các PBI để chúng nhỏ và chính xác hơn. Đây là việc liên tục bổ sung chi tiết, chẳng hạn mô tả, thứ tự và kích thước. Refinement có thể diễn ra qua những cuộc trao đổi ngắn, thử nghiệm, làm rõ ví dụ hoặc các buổi làm việc chung.

Refinement **không phải một sự kiện Scrum chính thức có timebox bắt buộc riêng**. Nhóm có thể lên nhịp họp nhưng không cần tạo thủ tục nặng nếu việc làm rõ đã diễn ra hiệu quả.

Một luồng khám phá và làm rõ có thể như sau:

~~~mermaid
flowchart TD
    A["Ý tưởng, lỗi, phản hồi hoặc rủi ro"] --> B["Đối chiếu Product Goal và giá trị"]
    B --> C{"Có nên giữ trên Product Backlog?"}
    C -- "Chưa / không" --> D["Hoãn, bỏ hoặc tiếp tục khám phá"]
    C -- "Có" --> E["Làm rõ hành vi, dữ liệu, phụ thuộc"]
    E --> F["Chia nhỏ thành PBI có giá trị kiểm chứng"]
    F --> G["Developers sizing và trao đổi rủi ro"]
    G --> H["PO cập nhật thứ tự, minh bạch backlog"]
    H --> I["Ứng viên cho Sprint Planning khi đủ rõ"]
    I -. "Phản hồi và thông tin mới" .-> B
~~~

Đây chỉ là mô hình để tư duy; thực tế các bước có thể đan xen. PO có thể sắp lại thứ tự trước khi nhóm hoàn tất việc chia nhỏ; Developers có thể đề xuất spike nếu rủi ro còn quá lớn.

### 6.2. Ai chịu trách nhiệm kích thước PBI?

Theo Scrum Guide, **Developers thực hiện công việc chịu trách nhiệm về sizing**. Product Owner có thể ảnh hưởng bằng việc giúp Developers hiểu rõ công việc và thảo luận đánh đổi.

Điều này không yêu cầu dùng story points, Planning Poker hay đơn vị ước lượng cố định. Nhóm có thể dùng ước lượng tương đối, khoảng nỗ lực, phân tích rủi ro hoặc dữ liệu flow phù hợp.

**PO chịu trách nhiệm ordering**, **Developers chịu trách nhiệm sizing**. Một PBI có giá trị cao nhưng quá lớn không phải lý do để ép Developers “cam kết làm ngay”; họ có thể chia lát cắt hoặc làm bước khám phá trước.

### 6.3. Thế nào là đủ rõ để chọn vào Sprint?

Theo Scrum Guide, các PBI **có thể được Done trong một Sprint** được xem là đủ sẵn sàng để chọn trong Sprint Planning; chúng thường đạt mức minh bạch này sau refinement.

Nhóm có thể tự sử dụng một danh sách kiểm tra như:

- Mục đích, người dùng và giá trị được hiểu chung.
- Hành vi chính và những trường hợp lỗi quan trọng có ví dụ kiểm chứng.
- Phụ thuộc, giới hạn và rủi ro lớn được nhận diện.
- Developers hiểu cách có thể tạo Increment đáp ứng DoD trong một Sprint.
- Kích thước đủ nhỏ hoặc có phương án chia nhỏ hợp lý.

Danh sách kiểm tra như vậy đôi khi gọi là **Definition of Ready (DoR)**, nhưng **DoR không phải cam kết hay artifact bắt buộc của Scrum**. Không biến nó thành “cổng ký duyệt” khiến Developers và PO không thể học từ thử nghiệm.

### 6.4. Chia lát cắt dọc thay vì chia task theo phòng ban

Giả sử PBI “quản lý toàn bộ đăng ký khóa học” quá lớn. Một cách chia có giá trị:

1. Học viên đăng ký **một khóa miễn phí còn chỗ**, nhận kết quả đúng.
2. Học viên xem **lịch sử đăng ký** của chính mình.
3. Học viên **tự hủy** đăng ký trong điều kiện được cho phép.
4. Học viên đăng ký **khóa trả phí** qua quy trình thanh toán phù hợp.

Mỗi lát cắt nên đi qua các thành phần cần thiết để tạo hành vi dùng được. Tránh chia PBI thành “làm database”, “làm backend”, “làm giao diện” rồi tuyên bố các phần riêng lẻ đã tạo giá trị người dùng.

**Không được chia nhỏ bằng cách bỏ tính đúng đắn hoặc các điều kiện bắt buộc của Definition of Done.** Nếu PBI “đăng ký còn chỗ” không chống vượt sức chứa trong trường hợp đồng thời, phần đó chưa đạt hành vi đã cam kết.

## 7. Sắp thứ tự Product Backlog theo giá trị và bối cảnh

### 7.1. “Ordered” không nhất thiết là xếp theo một điểm số

Product Backlog phải **được sắp thứ tự**. Scrum không bắt buộc dùng một công thức ưu tiên cố định. Product Owner có thể cân nhắc:

- **Giá trị người dùng và kết quả kinh doanh:** lợi ích nào sẽ xuất hiện khi PBI hoàn tất?
- **Mức cấp thiết/chi phí trì hoãn:** nếu chờ thêm một khoảng thời gian, cơ hội hoặc tổn thất nào phát sinh?
- **Rủi ro:** làm sớm có tránh sự cố hoặc kiểm chứng giả định quan trọng không?
- **Phụ thuộc:** PBI nào mở khóa giá trị của những PBI khác?
- **Kích thước và khả năng giao sớm:** có lát cắt nhỏ hơn để nhận phản hồi?
- **Ràng buộc bắt buộc:** bảo mật, nghĩa vụ pháp lý, chất lượng hoặc thời điểm quan trọng.

Mục tiêu là **giải thích được vì sao công việc này nên làm trước công việc kia**, dựa trên Product Goal và thông tin hiện tại.

### 7.2. Ví dụ đánh giá các mục cạnh tranh

Giả sử Product Goal là “Học viên tự đăng ký khóa học miễn phí đáng tin cậy, không cần hỗ trợ thủ công trong các trường hợp thông thường”.

| PBI | Tác động tới Product Goal | Rủi ro/phụ thuộc | Quyết định tham khảo |
| --- | --- | --- | --- |
| Sửa lỗi đăng ký tạo hai bản ghi | Bảo vệ tính chính xác của đăng ký | Có thể gây dữ liệu sai và tăng yêu cầu hỗ trợ | Ưu tiên sớm; mức khẩn cấp dựa trên thực trạng. |
| Học viên tự đăng ký khóa còn chỗ | Khả năng cốt lõi | Cần quy tắc sức chứa và phân quyền | Chia lát cắt và sắp ở đầu. |
| Kiểm thử hợp đồng API dữ liệu khóa | Giúp tích hợp tin cậy | Mở khóa và giảm rủi ro cho đăng ký | Sắp phù hợp với chuỗi phụ thuộc, có thể làm sớm. |
| SMS nhắc lịch học | Giá trị có thể có nhưng ngoài mục tiêu hiện hành | Nhà cung cấp tin nhắn, đồng ý nhận tin | Ghi nhận và xem lại sau hoặc thử nhu cầu nhỏ. |
| Dashboard báo cáo nâng cao | Hữu ích cho quản trị nhưng ít góp phần trực tiếp vào mục tiêu trước mắt | Cần dữ liệu thực tế đủ tin cậy | Hoãn hoặc thay đổi thứ tự nếu bối cảnh đổi. |

Nếu có lỗ hổng quyền truy cập đang đe dọa dữ liệu cá nhân, nhóm phải xử lý theo **chính sách an toàn và mức độ sự cố**, không dùng điểm ưu tiên của tính năng để biện minh cho việc chờ đợi.

### 7.3. Chi phí trì hoãn là một cách đặt câu hỏi về thời gian

**Cost of Delay (CoD)** giúp thảo luận hậu quả kinh tế của việc chờ. Ví dụ giả định: lỗi đăng ký trùng làm phát sinh chi phí xử lý thủ công khoảng **3 triệu đồng/tuần**. Trì hoãn sửa trong **2 tuần** có thể gây khoảng:

\[
3\ \text{triệu đồng/tuần}\times 2\ \text{tuần}=6\ \text{triệu đồng}.
\]

Đây là **ước lượng minh họa**, chưa tính rủi ro dữ liệu, mất niềm tin và công sức sửa lỗi. CoD có thể không tuyến tính, nhất là với hạn chót hoặc sự cố. Nó là **đầu vào của quyết định ordering**, không phải phép đo có độ chính xác tuyệt đối.

Các phương pháp như **WSJF, RICE, MoSCoW, ma trận giá trị–nỗ lực** có thể hữu ích nếu nhóm hiểu giả định. Không có phương pháp nào trong số đó là yêu cầu bắt buộc của Scrum; điểm số không thay thế trách nhiệm quyết định của Product Owner.

### 7.4. Phụ thuộc làm thay đổi thứ tự thực hiện

Một PBI có giá trị cao có thể cần một PBI kỹ thuật trước:

~~~mermaid
flowchart LR
    A["Xác minh hợp đồng API và quyền truy cập"] --> B["Tạo luồng đăng ký"]
    B --> C["Học viên tự quản lý đăng ký"]
    D["Kiểm thử dữ liệu cạnh tranh"] --> B
    E["SMS nhắc lịch"] 
~~~

Không nhất thiết phải xây toàn bộ nền tảng trước khi làm luồng đăng ký. Developers có thể đề xuất hợp đồng tối thiểu, contract test, test double hoặc cách chia nhỏ để giảm phụ thuộc; sau đó vẫn phải kiểm chứng tích hợp thật trước khi tuyên bố Increment Done nếu DoD yêu cầu.

**Giá trị mở khóa** của PBI nền tảng cần được xem xét, nhưng tránh **đếm trùng** toàn bộ giá trị của tính năng cuối vào mọi hạng mục phụ thuộc rồi cộng lại như lợi ích độc lập.

## 8. Product Goal và Product Backlog kết nối với Sprint như thế nào?

### 8.1. Từ Product Goal tới Sprint Goal

Trong Scrum, có ba artifact và ba cam kết liên quan:

| Artifact | Commitment | Vai trò |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Định hướng trạng thái sản phẩm và những cơ hội cải thiện. |
| **Sprint Backlog** | **Sprint Goal** | Làm rõ mục tiêu chung và kế hoạch trong Sprint gần. |
| **Increment** | **Definition of Done** | Minh bạch tiêu chuẩn chất lượng của phần sản phẩm hoàn tất. |

**Product Goal tạo hướng dài hạn**; **Sprint Goal tạo một mục tiêu gần** đóng góp vào hướng đó. Không nên giả định một Sprint phải hoàn thành toàn bộ Product Goal.

### 8.2. Product Backlog không phải Sprint Backlog

| Khía cạnh | Product Backlog | Sprint Backlog |
| --- | --- | --- |
| **Mục đích** | Những gì cần thiết để cải thiện sản phẩm. | Mục tiêu và kế hoạch để tạo giá trị trong Sprint. |
| **Cam kết** | Product Goal. | Sprint Goal. |
| **Trách nhiệm liên quan** | Product Owner chịu trách nhiệm quản lý và ordering. | Developers tạo và cập nhật kế hoạch; Scrum Team cùng tạo Sprint Goal. |
| **Mức độ chi tiết** | Các mục gần và xa, liên tục nổi lên/làm rõ. | Mức chi tiết đủ để Developers theo dõi và điều chỉnh việc thực hiện. |
| **Thời điểm thay đổi** | Bất cứ khi nào có dữ liệu, cơ hội và quyết định phù hợp. | Được Developers điều chỉnh trong Sprint để tiến tới Sprint Goal. |

Trong **Sprint Planning**, Developers thảo luận với Product Owner về giá trị và chọn những PBI có thể hoàn tất để phục vụ Sprint Goal; Developers lập kế hoạch biến chúng thành Increment. PO không tự động “đẩy” tất cả hạng mục được ưu tiên cao nhất vào Sprint mà không xét năng lực và mục tiêu.

### 8.3. Sprint Review là cơ hội điều chỉnh Product Backlog

Trong **Sprint Review**, Scrum Team và stakeholder kiểm tra kết quả Sprint và những thay đổi của môi trường, thảo luận bước phù hợp tiếp theo. Product Backlog có thể được điều chỉnh theo phản hồi mới.

Ví dụ, Increment đăng ký giúp học viên hoàn tất tác vụ nhưng họ hiểu nhầm thông báo thành công. PO có thể tăng thứ tự PBI làm rõ xác nhận; nếu người dùng ít quan tâm SMS như giả định ban đầu, PBI SMS có thể được hoãn hoặc bỏ.

**Sprint Review không phải cổng phê duyệt bắt buộc trước khi phát hành.** Increment đáp ứng DoD có thể được phát hành trước đó; Review vẫn có vai trò kiểm tra giá trị và hướng đi.

### 8.4. DoD là điều kiện giao giá trị, không phải chi tiết tùy chọn

Một PBI có thể được làm rõ bằng **acceptance criteria**; một Increment phải đạt **Definition of Done**. Nếu phát hiện kiểm thử dữ liệu đồng thời thất bại, nhóm không được loại yêu cầu đúng đắn khỏi hạng mục chỉ để đóng PBI. Những phần chưa đạt DoD cần được minh bạch và tiếp tục xem xét trong Product Backlog.

Product Owner có thể thay đổi **ưu tiên và phạm vi khả năng tùy chọn**, nhưng không nên xem các nghĩa vụ bảo mật, pháp lý hoặc tiêu chuẩn chất lượng bắt buộc như một lựa chọn kinh doanh có thể bỏ qua để đạt ngày giao.

## 9. Tình huống xuyên suốt: tạo Product Backlog cho nền tảng học trực tuyến

### 9.1. Bối cảnh và Product Goal minh họa

Một nền tảng học trực tuyến có danh mục khóa học nhưng học viên phải nhắn nhân viên để đăng ký. Tổ chức muốn thử đưa phần lớn công việc đăng ký thông thường vào sản phẩm. Các yêu cầu đến từ học viên, bộ phận hỗ trợ, nhóm vận hành và đội kỹ thuật.

**Product Goal đề xuất:**

> Học viên đã đăng nhập có thể tự tìm và đăng ký khóa học miễn phí còn chỗ trên web, nhận trạng thái chính xác và không phải nhờ nhân viên xử lý trong những trường hợp thông thường.

Để mục tiêu trở nên cụ thể hơn, PO cùng nhóm cần xác nhận:

- **Ranh giới:** khóa học miễn phí, học viên cá nhân, giao diện web được hỗ trợ.
- **Giá trị:** giảm thời gian chờ và thao tác thủ công, tăng độ tin cậy dữ liệu.
- **Bằng chứng năng lực:** hệ thống có luồng đăng ký đầu cuối, bảo vệ quyền và tính nhất quán.
- **Bằng chứng sử dụng:** thử nghiệm với học viên, quan sát tỷ lệ hoàn tất và tình huống cần hỗ trợ.
- **Phần ngoài phạm vi hiện tại:** thanh toán, đăng ký hộ, danh sách chờ, SMS nhắc học.

Mọi con số đo lường bên dưới chỉ là **ví dụ học tập**; muốn dùng thật, PO phải kiểm tra dữ liệu nền, cách đo và khả năng chịu tác động.

### 9.2. Product Backlog ban đầu

| ID | PBI / cơ hội | Giá trị hoặc rủi ro | Phụ thuộc | Thứ tự ban đầu minh họa |
| --- | --- | --- | --- | --- |
| **PB-01** | Học viên xem khóa còn chỗ | Biết có thể đăng ký khóa nào. | Dữ liệu sức chứa tin cậy. | 1 |
| **PB-02** | Học viên gửi đăng ký miễn phí và nhận kết quả | Tự phục vụ thay nhân viên hỗ trợ. | PB-01, quy tắc nghiệp vụ, phân quyền. | 2 |
| **PB-03** | Chống đăng ký trùng và vượt sức chứa | Bảo vệ tính đúng đắn, tránh lỗi nghiêm trọng. | Gắn với thiết kế và kiểm thử của PB-02. | Ưu tiên bắt buộc trong lát cắt đăng ký. |
| **PB-04** | Thông báo rõ khi khóa vừa hết chỗ | Giảm hiểu nhầm và hỗ trợ thủ công. | Luồng thất bại của PB-02. | 3; có thể làm rõ như một phần PB-02. |
| **PB-05** | Học viên xem danh sách đăng ký của mình | Giảm hỏi nhân viên về kết quả. | Dữ liệu và quyền truy cập. | 4 |
| **PB-06** | Học viên tự hủy đăng ký đúng quy tắc | Mở rộng tự phục vụ. | Quy tắc hủy, dữ liệu đăng ký. | 5 |
| **PB-07** | Thử nghiệm SMS nhắc buổi học | Giả thuyết giảm bỏ lỡ lịch. | Dữ liệu liên hệ, quyền đồng ý, tích hợp. | Xem sau khi có bằng chứng |
| **PB-08** | Cải thiện giám sát lỗi đăng ký | Giảm thời gian phát hiện và khắc phục. | Log/metric hệ thống. | Đánh giá sớm theo rủi ro và DoD |

Bảng này là **bản thảo để trao đổi**, không phải cam kết rằng cả tám mục sẽ được thực hiện. Thứ tự có thể thay đổi khi thông tin về lỗi, người dùng và phụ thuộc thay đổi.

**Lưu ý về PB-03:** ràng buộc chống đăng ký trùng có thể là điều kiện chấp nhận cần thiết của PB-02, không nhất thiết phải trở thành một tính năng độc lập giao sau. Nếu nhóm tách PB-03 thành một PBI riêng để theo dõi kỹ thuật, vẫn phải bảo đảm PB-02 **không bị gọi Done khi tính đúng đắn bắt buộc chưa đạt**. Tách ticket không thể thay đổi bản chất chuẩn chất lượng.

### 9.3. Refinement của PB-02 bằng ví dụ

**User story:**

> Là học viên đã đăng nhập, tôi muốn đăng ký khóa học miễn phí còn chỗ để tự tham gia học mà không phải nhờ nhân viên hỗ trợ.

**Các câu hỏi cần làm rõ:**

1. “Còn chỗ” được tính theo trạng thái nào và tại thời điểm nào?
2. Một học viên có được tạo hai đăng ký hiệu lực cho cùng khóa không?
3. Nếu hai người cùng chọn chỗ cuối, kết quả đúng là gì?
4. Ai được xem hoặc thay đổi đăng ký?
5. Khi lưu dữ liệu thất bại, người học thấy gì, có được thử lại an toàn không?
6. Tiêu chuẩn tích hợp, kiểm thử và quan sát nào nằm trong DoD?

Sau khi PO hoặc chủ sở hữu nghiệp vụ xác nhận quy tắc, Developers có thể sử dụng ví dụ gần Gherkin:

~~~gherkin
Feature: Học viên tự đăng ký khóa học miễn phí

  Scenario: Đăng ký thành công khi còn chỗ
    Given học viên A đã đăng nhập và chưa đăng ký khóa học X
    And khóa học X còn ít nhất một chỗ
    When A xác nhận đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A nhận được thông báo thành công

  Scenario: Gửi đăng ký lặp lại
    Given học viên A đã có đăng ký hiệu lực ở khóa X
    When A gửi lại yêu cầu đăng ký cùng khóa X
    Then hệ thống không tạo thêm đăng ký hiệu lực thứ hai
    And A nhìn thấy trạng thái đăng ký hiện tại

  Scenario: Tranh chỗ cuối
    Given khóa X chỉ còn một chỗ
    When hai học viên hợp lệ đồng thời gửi yêu cầu đăng ký
    Then tối đa một đăng ký mới được xác nhận
    And số đăng ký hiệu lực không vượt sức chứa

  Scenario: Từ chối truy cập trái quyền
    Given người dùng B không có quyền sửa đăng ký của A
    When B cố yêu cầu sửa đăng ký của A
    Then hệ thống từ chối thao tác
~~~

Đây là ví dụ hành vi, **chưa tự động là test chạy được**. Developers cần kết nối chúng với kiểm thử và kiểm chứng thực tế phù hợp. Scrum không bắt buộc viết Gherkin, nhưng việc có các ví dụ rõ giúp PO, Developers và người kiểm thử tránh hiểu sai nhau.

### 9.4. Chia PB-02 thành các lát cắt có thể dùng được

Nếu PB-02 còn quá lớn, có thể thử:

- **Lát cắt A:** học viên đăng ký được **một loại khóa miễn phí**, thấy xác nhận; bao gồm tính nhất quán, quyền và lỗi bắt buộc.
- **Lát cắt B:** hỗ trợ thêm loại khóa học có quy tắc đăng ký khác, nếu nhu cầu được xác nhận.
- **Lát cắt C:** cải thiện hành trình khi một học viên có nhiều đăng ký, nếu có phản hồi phù hợp.

Không nên tách thành “backend trước, frontend sau, kiểm thử ở Sprint kế tiếp” nếu mỗi phần chưa đủ tạo hành vi dùng được. Product Backlog có thể biểu diễn nhiều cấp mục trong công cụ, nhưng **mỗi PBI được chọn nên có hướng rõ tới một phần Increment đạt DoD**.

### 9.5. Sprint đầu tiên và phản hồi

Giả sử Scrum Team chọn Sprint Goal:

> “Học viên thử nghiệm có thể đăng ký một khóa miễn phí còn chỗ và nhận xác nhận đúng.”

Developers dựa trên thứ tự và refinement để chọn những PBI phù hợp, lập Sprint Backlog, chia việc và tích hợp sớm. Trong quá trình kiểm thử, họ phát hiện xử lý yêu cầu đồng thời khó hơn dự kiến.

Nhóm có thể:

1. Chủ động nghiên cứu và sửa cơ chế cập nhật sức chứa.
2. Trao đổi với PO về tác động tới phạm vi phụ của Sprint.
3. Hoãn một khả năng không thiết yếu như bộ lọc nâng cao.
4. Giữ nguyên chuẩn DoD và điều kiện không vượt sức chứa.
5. Chỉ trình bày những phần thực sự Done như Increment.

Khi người dùng thử cho biết thông báo “đăng ký thành công” chưa rõ thời điểm bắt đầu khóa, PO có thể thay đổi thứ tự **PB-04**, làm rõ ví dụ chấp nhận và tiếp tục hướng tới Product Goal.

### 9.6. Khi nào mục tiêu sản phẩm được xem là hoàn tất?

Không nên kết luận Product Goal đã đạt chỉ vì mọi mục gần đầu Product Backlog được đóng. Nhóm cần kiểm tra **trạng thái sản phẩm** so với mục tiêu ban đầu:

- Học viên mục tiêu có thể tự tìm và đăng ký khóa miễn phí hợp lệ hay không?
- Hành vi đã dùng được trong phạm vi đã thống nhất, đáp ứng DoD và các kiểm soát bắt buộc chưa?
- Những trường hợp thông thường có còn cần nhân viên can thiệp không?
- Có bằng chứng từ thử nghiệm hoặc vận hành cho kết quả mong đợi chưa?
- Có giới hạn nào cần công khai trước khi quyết định hoàn thành hay từ bỏ Product Goal?

PO cùng Scrum Team và stakeholder dùng những thông tin đó để xác định nên tiếp tục đầu tư, điều chỉnh backlog, hay tuyên bố Product Goal đã đạt. Nếu bối cảnh thay đổi làm mục tiêu không còn giá trị, Scrum Team có thể **minh bạch quyết định từ bỏ** và hướng tới một Product Goal tiếp theo thay vì tiếp tục xây chỉ vì kế hoạch cũ.

## 10. Tiếp nhận yêu cầu mới mà không làm Product Backlog mất trọng tâm

### 10.1. Phân biệt thu thập ý tưởng và cam kết thực hiện

Một stakeholder nói “cần thêm SMS ngay” chưa đồng nghĩa với việc đó đã được ưu tiên hoặc cam kết vào Sprint. Một quy trình gọn có thể là:

1. Ghi nhận nhu cầu, nguồn và giá trị kỳ vọng.
2. Kiểm tra liên hệ với Product Goal hiện tại.
3. Hỏi bằng chứng, tính cấp thiết, rủi ro, phụ thuộc và giải pháp nhỏ hơn.
4. Product Owner quyết định thêm, đổi thứ tự, để khám phá, hoãn hoặc từ chối.
5. Truyền đạt kết quả, lý do và điều kiện xem xét lại.

**Không phải ý tưởng nào cũng phải được giữ mãi trên Product Backlog**. Backlog quá lớn với hàng nghìn mục cũ và không còn giá trị sẽ làm khó việc hiểu và ưu tiên.

### 10.2. Mẫu ghi nhận đề nghị ngắn

~~~text
Đề nghị: SMS nhắc lịch học trước một ngày
Người hưởng lợi: Học viên dễ quên lịch học
Giá trị kỳ vọng: Giảm số học viên bỏ lỡ buổi đầu
Bằng chứng: Phản hồi từ một nhóm nhỏ, chưa có dữ liệu nền đầy đủ
Liên hệ Product Goal hiện tại: Gián tiếp; không bắt buộc để tự đăng ký
Rủi ro: Quyền đồng ý nhận tin, dữ liệu số điện thoại, tích hợp nhà cung cấp
Phương án: Phỏng vấn hoặc thử thông báo trong ứng dụng trước
Quyết định hiện tại: Giữ để khám phá, không thêm vào Sprint đang làm
Người chịu trách nhiệm ordering: Product Owner
~~~

Không cần biến mẫu này thành một biểu mẫu phê duyệt nặng nề. Với đề nghị nhỏ và rõ, cập nhật PBI cùng trao đổi trực tiếp có thể đủ.

### 10.3. Xử lý khi stakeholder có ưu tiên xung đột

Giả sử bộ phận kinh doanh yêu cầu thanh toán, bộ phận hỗ trợ muốn xử lý lỗi đăng ký, còn kỹ sư muốn cải thiện CI. PO không nhất thiết chọn một yêu cầu chỉ vì người đề xuất có chức vụ cao nhất.

Họ cần tổng hợp:

- Product Goal và giá trị hiện tại.
- Mức độ rủi ro dữ liệu hoặc sự cố.
- Tác động nếu trì hoãn từng mục.
- Phụ thuộc và khả năng chia nhỏ.
- Năng lực, DoD và thời gian nhận phản hồi.

Các bên có thể thảo luận công khai về đánh đổi; **PO chịu trách nhiệm cuối cùng với Product Backlog order**. Nếu có chính sách hoặc sự cố bắt buộc, tổ chức vẫn phải xử lý theo đúng thẩm quyền và quy trình tương ứng.

## 11. Đo hiệu quả Product Backlog và tiến độ Product Goal

Một Product Backlog đẹp trên công cụ không tự tạo giá trị. Nên theo dõi cả **mức tiến gần Product Goal** và **chất lượng của quyết định ưu tiên**.

| Tín hiệu | Câu hỏi hữu ích | Cách diễn giải cẩn trọng |
| --- | --- | --- |
| **Outcome sản phẩm** | Học viên tự đăng ký được nhiều hơn, thời gian chờ có giảm không? | Có dữ liệu nền và phân biệt tác động của sản phẩm với yếu tố ngoài sản phẩm. |
| **Increment đạt DoD** | Sản phẩm có thêm hành vi dùng được nào góp phần vào Product Goal? | Không đếm task hoặc demo giả lập như Increment hoàn tất. |
| **Thời gian tới phản hồi** | Mất bao lâu từ giả thuyết đến thử nghiệm với người dùng phù hợp? | Phản hồi nhanh nhưng sai đối tượng vẫn có thể dẫn tới quyết định sai. |
| **Độ rõ của PBI gần** | Developers có hiểu mục tiêu, điều kiện, rủi ro và kích thước không? | Không yêu cầu làm rõ toàn bộ backlog xa. |
| **Cycle time / work item age** | Việc đang làm có bị kéo dài do phụ thuộc, mở rộng phạm vi hoặc chờ test không? | Mốc đo phải nhất quán; dùng để phát hiện tắc nghẽn. |
| **WIP / throughput** | Có quá nhiều PBI đang dở, ít PBI Done không? | Số lượng không đồng nghĩa giá trị; việc chia nhỏ ảnh hưởng metric. |
| **Tần suất đổi thứ tự có căn cứ** | Thay đổi backlog đến từ bằng chứng hay yêu cầu đột ngột chưa xem xét? | Không xem “ít thay đổi” tự động là tốt; Agile cần thích ứng. |
| **Giả định bị bác bỏ sớm** | Nhóm có dừng đầu tư khi kết quả thử nghiệm không như kỳ vọng? | Học ra điều không nên làm tiếp cũng có thể tiết kiệm nguồn lực. |

### 11.1. Phân biệt outcome và output

**Output** là thứ được giao: form, API, hệ thống xác nhận. **Outcome** là thay đổi trong hành vi/kết quả của người dùng: tự hoàn tất đăng ký, ít phải liên hệ nhân viên, giảm dữ liệu sai.

Ví dụ giả định: nhóm mời **40 học viên** đủ điều kiện thử luồng mới, trong đó **28 người** tự đăng ký thành công không cần hỗ trợ. Tỷ lệ trong nhóm thử:

\[
\frac{28}{40}\times 100\%=70\%.
\]

Con số **70% là minh họa** cho nhóm thử nhỏ; chưa đủ để kết luận mọi người dùng sẽ đạt tỷ lệ này hoặc Increment là nguyên nhân duy nhất của thay đổi. PO có thể dùng phản hồi định tính và dữ liệu phù hợp để xem trở ngại nào nên xử lý trước.

### 11.2. Đừng đo backlog bằng số lượng ticket càng nhiều càng tốt

Những cách đo dễ sai:

- Đếm số PBI được tạo như thành tích.
- Yêu cầu 100% PBI phải có story points ngay từ lúc được đề xuất.
- Dùng velocity để so năng suất cá nhân hoặc các Scrum Team.
- Gọi mọi PBI có trạng thái “code complete” là giá trị đã giao.
- Xem backlog thay đổi là thất bại lập kế hoạch.

Chỉ số nên giúp nhóm **đưa ra quyết định tốt hơn, giao Increment đáng tin cậy và học nhanh**, không khuyến khích che giấu rủi ro hoặc sản xuất ticket.

## 12. Các phản mẫu thường gặp

| Phản mẫu | Vấn đề | Cách điều chỉnh |
| --- | --- | --- |
| **Backlog là danh sách mọi ý tưởng, không có thứ tự** | Nhóm không rõ công việc nào quan trọng. | PO sắp thứ tự theo Product Goal và thông tin thực tế. |
| **Product Goal là khẩu hiệu quá rộng** | Không biết trạng thái nào được coi là đạt. | Nêu người dùng, ranh giới và năng lực/kết quả tương lai. |
| **Product Goal là danh sách task** | Nhóm tối ưu đầu ra, không biết giá trị. | Tập trung trạng thái sản phẩm, để backlog thể hiện các lựa chọn công việc. |
| **PO không có quyền quyết định thứ tự** | Stakeholder áp đặt ưu tiên mâu thuẫn. | Làm rõ accountability và sự ủng hộ của tổ chức. |
| **Developers bị áp sẵn story points** | Sizing mất giá trị kỹ thuật và tạo cam kết giả. | Developers chịu trách nhiệm sizing, PO cung cấp bối cảnh. |
| **Refinement thành thủ tục cổng duyệt cứng** | Học hỏi chậm; DoR bị nhầm thành yêu cầu Scrum. | Làm rõ liên tục, đủ cho Sprint, tương xứng với rủi ro. |
| **Mọi PBI phải đầy đủ đặc tả trước khi bắt đầu sản phẩm** | Đầu tư lớn vào chi tiết có thể không bao giờ được dùng. | Làm rõ gần chi tiết, xa ở mức ý tưởng. |
| **Tách theo backend/frontend/test rồi gọi Increment** | Phản hồi đến muộn và khó đánh giá giá trị. | Chia lát cắt có hành vi sử dụng đầu cuối. |
| **Đẩy hạng mục chưa đạt DoD sang Done** | Minh bạch sai, tích lũy lỗi và rủi ro. | Giữ chất lượng và báo trạng thái đúng. |
| **Giữ mãi PBI cũ không còn giá trị** | Backlog phình to và gây nhiễu quyết định. | Hoãn, bỏ, gộp hoặc làm mới theo thông tin hiện tại. |
| **Chỉ chọn tính năng nhìn thấy được, bỏ nợ kỹ thuật** | Rủi ro chất lượng và tốc độ giao hàng tích tụ. | Gắn công việc kỹ thuật với giá trị bảo vệ và Product Goal. |
| **Mỗi team cùng sản phẩm có backlog mục tiêu riêng** | Phụ thuộc khó điều phối và ưu tiên không nhất quán. | Làm rõ ranh giới sản phẩm và một Product Backlog chung. |
| **Tuyên bố Product Goal đã đạt vì đóng hết ticket** | Trạng thái sản phẩm và outcome chưa được kiểm chứng. | Xem bằng chứng sử dụng được, DoD và kết quả người dùng. |
| **Không đổi thứ tự dù phản hồi đã khác** | Tiếp tục đầu tư vào giả định sai. | Dùng Sprint Review và dữ liệu mới để thích ứng Product Backlog. |

## 13. Quy trình áp dụng khi xây Product Backlog đầu tiên

Một Scrum Team mới có thể bắt đầu theo chu trình nhẹ:

### Bước 1 — Xác định sản phẩm và Product Goal

Nêu rõ người dùng, ranh giới và trạng thái tương lai có giá trị. PO phát triển và truyền đạt Product Goal; Scrum Team cùng hiểu mục đích, khả năng kiểm chứng và các giới hạn.

### Bước 2 — Thu thập cơ hội, vấn đề và rủi ro

Lắng nghe người dùng, stakeholder, Developers và hệ thống vận hành. Ghi những đề nghị có ích vào Product Backlog ở mức chi tiết phù hợp. Không mặc định mỗi ý tưởng là cam kết làm.

### Bước 3 — PO sắp thứ tự và giải thích đánh đổi

Xem giá trị, rủi ro, chi phí trì hoãn, phụ thuộc và ràng buộc. Truyền đạt vì sao mục A cần sớm hơn B; sẵn sàng cập nhật khi có bằng chứng mới.

### Bước 4 — Refinement những PBI gần nhất

PO và Developers làm rõ hành vi, đặt câu hỏi nghiệp vụ, chia lát cắt, nhận diện phụ thuộc và đánh giá kích thước. Nếu còn bất định lớn, xem xét thử nghiệm nhỏ hoặc spike trước quyết định đầu tư.

### Bước 5 — Sprint Planning theo mục tiêu

Scrum Team tạo Sprint Goal đóng góp vào Product Goal. Developers chọn những PBI có thể Done trong Sprint và lập Sprint Backlog. Kế hoạch được điều chỉnh khi có thông tin mới, không giảm chuẩn chất lượng.

### Bước 6 — Giao Increment, kiểm tra và thích ứng

Developers tích hợp và kiểm chứng Increment theo DoD. Scrum Team cùng stakeholder xem kết quả và hướng đi; PO cập nhật Product Backlog khi có điều cần học. Nếu Product Goal đã đạt hoặc không còn phù hợp, minh bạch quyết định trước khi hướng tới mục tiêu tiếp theo.

~~~mermaid
flowchart TD
    PG["Product Goal: trạng thái sản phẩm tương lai"] --> PB["Product Backlog được sắp thứ tự"]
    PB --> RF["Refinement: chia nhỏ, làm rõ, sizing"]
    RF --> SP["Sprint Planning: chọn mục tiêu và công việc"]
    SP --> INC["Developers tạo Increment đạt DoD"]
    INC --> FEED["Kiểm tra kết quả và phản hồi"]
    FEED --> PB
    FEED -. "Xem Product Goal còn đúng?" .-> PG
~~~

## 14. Bài tập và tình huống thảo luận

### Bài tập 1 — Chọn Product Goal tốt hơn

Ba mục tiêu giả định:

1. “Làm 12 trang giao diện, 9 API và sửa toàn bộ lỗi.”
2. “Trở thành nền tảng học tốt nhất thị trường.”
3. “Học viên đã đăng nhập có thể tự tìm và đăng ký khóa miễn phí trên web, nhận kết quả chính xác trong các trường hợp thông thường.”

**Yêu cầu:** chọn cách diễn đạt có thể dùng làm Product Goal và giải thích vì sao. Hãy đề xuất một tín hiệu chứng minh sản phẩm tiến gần mục tiêu.

**Gợi ý:** phương án 3 rõ hơn về đối tượng, năng lực và ranh giới. Phương án 1 là danh sách đầu ra; phương án 2 quá rộng. Có thể đo khả năng đăng ký đầu cuối, số trường hợp phải nhờ hỗ trợ hoặc tỷ lệ hoàn tất trong nhóm thử phù hợp.

### Bài tập 2 — Product Backlog Item hay task triển khai?

Một nhóm đề xuất:

- A. “Học viên xem được trạng thái đăng ký của chính mình.”
- B. “Tạo bảng database registration.”
- C. “Nhân viên hỗ trợ không còn phải sửa đăng ký trùng thủ công.”
- D. “Chạy kiểm thử tích hợp chống vượt sức chứa.”
- E. “Học viên tự hủy đăng ký trong thời hạn cho phép.”

Hãy phân biệt **nhu cầu/khả năng sản phẩm**, **kết quả mong muốn**, **công việc kỹ thuật**. Những mục nào phù hợp làm PBI độc lập, mục nào có thể là task hoặc tiêu chí DoD trong PBI khác?

**Gợi ý:** A và E là các khả năng sản phẩm rõ; C là kết quả mong muốn có thể dẫn tới PBI sửa lỗi; B thường là task kỹ thuật; D có thể là công việc kiểm chứng bắt buộc trong lát cắt đăng ký. Cách biểu diễn cụ thể có thể thay đổi theo rủi ro và mục tiêu, nhưng không dùng ticket tách riêng để bỏ qua DoD của chức năng chính.

### Bài tập 3 — Refinement một hạng mục quá lớn

PBI ban đầu: “Quản lý tất cả hoạt động đăng ký, thanh toán, hủy, hoàn tiền và thông báo khóa học”.

Hãy:

1. Viết một user story cho lát cắt đầu tiên.
2. Xác định hai hoặc ba tiêu chí chấp nhận trọng yếu.
3. Nêu những phần nằm ngoài lát cắt này.
4. Chỉ ra một rủi ro/phụ thuộc cần xác nhận sớm.
5. Giải thích tại sao chia theo backend–frontend–QA chưa tạo khả năng giao sớm.

**Gợi ý:** bắt đầu bằng đăng ký khóa miễn phí, không trùng và không vượt sức chứa; thanh toán, hoàn tiền và SMS để sau; kiểm thử giao dịch đồng thời là bắt buộc để đảm bảo tính đúng đắn của lát cắt.

### Bài tập 4 — Ai có trách nhiệm?

Tình huống:

| Câu hỏi | Trách nhiệm chính |
| --- | --- |
| Ai chịu trách nhiệm phát triển và truyền đạt Product Goal? | **Product Owner** |
| Ai chịu trách nhiệm sắp thứ tự Product Backlog? | **Product Owner** |
| Ai chịu trách nhiệm sizing các PBI sẽ được làm? | **Developers** |
| Ai lựa chọn các PBI có thể Done trong Sprint Planning? | **Developers**, qua trao đổi trong Scrum Team. |
| Ai tạo và cập nhật kế hoạch Sprint Backlog? | **Developers** |
| Ai chịu trách nhiệm xây Increment tuân thủ DoD? | **Developers**, trong trách nhiệm chung của Scrum Team. |
| Ai giúp Scrum Team cải thiện hiệu quả, tháo gỡ trở ngại? | **Scrum Master** hỗ trợ, phối hợp với cả nhóm và tổ chức. |

Hãy cho biết nếu người quản lý áp đặt sizing và thứ tự công việc hằng ngày, Scrum Team có thể gặp hậu quả gì đối với tự quản lý và minh bạch.

### Bài tập 5 — Thay đổi backlog sau phản hồi

Product Goal đang hướng tới tự đăng ký khóa học miễn phí. Sprint Review cho thấy:

- Luồng đăng ký hoạt động và đáp ứng DoD.
- Học viên thường không biết mình đã đăng ký thành công hay chưa.
- Một stakeholder muốn có tính năng SMS nâng cao.
- Nhóm phát hiện pipeline đôi khi bỏ qua một kiểm thử quan trọng.

**Yêu cầu:** đề xuất cách PO sắp thứ tự và Developers làm rõ các mục tiếp theo. Những mục nào liên quan trực tiếp đến Product Goal? Những yêu cầu nào cần xử lý như chất lượng/rủi ro? Có bắt buộc nhận SMS ngay không?

**Gợi ý:** ưu tiên làm rõ trạng thái xác nhận nếu đây là nút thắt người dùng; kiểm tra lỗi pipeline và xử lý theo mức độ rủi ro/DoD; SMS có thể được giữ để khám phá hoặc ưu tiên sau theo giá trị và phụ thuộc. PO quyết định ordering sau khi tham vấn, không mặc định yêu cầu mới nhất được làm ngay.

### Bài tập 6 — Có nên thay Product Goal không?

Sau một thời gian thử nghiệm, tổ chức nhận thấy phần lớn học viên thích đặt khóa học qua đối tác, còn nhu cầu tự đăng ký trực tiếp thấp hơn giả định. Đồng thời, một cơ hội chiến lược mới xuất hiện.

Hãy thảo luận:

1. Bằng chứng nào cần thu thập trước khi kết luận?
2. Product Goal cũ đã đạt, còn giá trị hay nên từ bỏ?
3. PO phải truyền đạt quyết định ra sao để không gây hiểu nhầm?
4. Những PBI cũ nào nên giữ, hoãn, bỏ hoặc chuyển cách tiếp cận?
5. Sprint đang diễn ra cần được xem xét thế nào nếu mục tiêu không còn giá trị?

**Gợi ý:** việc từ bỏ Product Goal dựa trên bằng chứng có thể là thích ứng đúng đắn; không nên giữ mục tiêu chỉ vì đã đầu tư. Với Sprint đang chạy, không tự ý đổi tất cả công việc. Scrum có cơ chế hủy Sprint khi Sprint Goal trở nên lỗi thời, và **chỉ Product Owner có thẩm quyền hủy**; đây là trường hợp đặc biệt, không phải phản ứng tự động với mọi phản hồi.

## 15. Checklist tự đánh giá Product Backlog và Product Goal

- [ ] Sản phẩm có ranh giới, người dùng và stakeholder được hiểu rõ.
- [ ] Product Goal thể hiện một trạng thái tương lai có giá trị, không chỉ là danh sách tính năng.
- [ ] Product Goal được PO truyền đạt và Scrum Team hiểu chung.
- [ ] Scrum Team đang tập trung vào một Product Goal trước khi nhận mục tiêu kế tiếp.
- [ ] Product Backlog là nguồn công việc sản phẩm nhất quán, minh bạch và được sắp thứ tự.
- [ ] PO có quyền và chịu trách nhiệm cuối cùng về thứ tự Product Backlog.
- [ ] Các PBI gần có giá trị, hành vi, rủi ro và phụ thuộc được làm rõ phù hợp.
- [ ] Developers chịu trách nhiệm sizing và đánh giá khả năng thực hiện.
- [ ] PBI lớn được chia thành lát cắt có thể tạo Increment đạt DoD.
- [ ] Backlog có chỗ cho lỗi, chất lượng, nợ kỹ thuật và khám phá, không chỉ tính năng giao diện.
- [ ] Sự khác biệt giữa Product Backlog, Sprint Backlog và Increment được hiểu rõ.
- [ ] Phản hồi người dùng và kết quả Sprint Review có thể thay đổi backlog khi hợp lý.
- [ ] Tiêu chuẩn bảo mật, dữ liệu và Definition of Done không bị bỏ qua vì áp lực ưu tiên.
- [ ] Các ý tưởng không còn giá trị được hoãn hoặc bỏ, không giữ như lời hứa vĩnh viễn.
- [ ] Khi Product Goal đạt hoặc không còn phù hợp, quyết định được minh bạch trước mục tiêu kế tiếp.

Checklist giúp nhóm thảo luận và cải tiến, không phải một danh sách thủ tục Scrum bắt buộc cần ký duyệt. Hãy đánh giá bằng **khả năng định hướng và giao giá trị thật**, không bằng số trường dữ liệu được điền.

## 16. Ghi nhớ

**Product Backlog** là artifact Scrum: danh sách nổi lên, có thứ tự của những điều cần thiết để cải thiện sản phẩm, cũng là nguồn công việc duy nhất do Scrum Team thực hiện. **Product Goal** là **cam kết của Product Backlog**: trạng thái tương lai của sản phẩm, tạo trọng tâm để lập kế hoạch và kiểm tra tiến độ.

**Product Owner** chịu trách nhiệm Product Goal và quản lý Product Backlog hiệu quả, gồm tạo, truyền đạt, ordering và minh bạch; họ có thể ủy quyền công việc nhưng vẫn chịu trách nhiệm cuối cùng. **Developers** đóng góp hiểu biết kỹ thuật, chịu trách nhiệm sizing, chọn công việc phù hợp khi Sprint Planning và tạo Increment đạt DoD. **Scrum Master** hỗ trợ Scrum Team và tổ chức làm việc hiệu quả theo Scrum.

Backlog không phải một hợp đồng làm hết mọi ticket. Nó được **làm rõ, chia nhỏ, sắp lại, thêm hoặc bớt** khi có bằng chứng mới. Các Sprint Goal và Increment giúp Scrum Team tiến tới Product Goal từng bước, nhận phản hồi sớm và điều chỉnh có căn cứ — đúng tinh thần **phát triển phần mềm Agile thích ứng**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Product** | Phương tiện cung cấp giá trị có ranh giới, stakeholder và người dùng/khách hàng được xác định. |
| **Product Backlog** | Danh sách nổi lên, được sắp thứ tự của mọi điều cần thiết để cải thiện sản phẩm trong Scrum. |
| **Product Backlog Item (PBI)** | Một hạng mục trong Product Backlog, được làm rõ đến mức phù hợp với quyết định hiện tại. |
| **Product Goal** | Cam kết của Product Backlog, mô tả trạng thái tương lai của sản phẩm. |
| **Product Owner** | Người chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. |
| **Ordering** | Sắp thứ tự các PBI theo giá trị, rủi ro, chi phí trì hoãn, phụ thuộc và bối cảnh thực. |
| **Refinement** | Hoạt động liên tục chia nhỏ, làm rõ PBI, cập nhật chi tiết, thứ tự và kích thước. |
| **Sizing** | Đánh giá kích thước PBI; Developers chịu trách nhiệm theo Scrum. |
| **User story** | Cách mô tả nhu cầu để khởi đầu trao đổi, không phải định dạng Scrum bắt buộc. |
| **Sprint Goal** | Cam kết của Sprint Backlog, thể hiện mục tiêu chung của Sprint. |
| **Sprint Backlog** | Sprint Goal, các PBI được chọn và kế hoạch thực hiện do Developers tạo/cập nhật. |
| **Increment** | Phần sản phẩm tích hợp, có thể sử dụng và đáp ứng Definition of Done. |
| **Definition of Done (DoD)** | Cam kết về chuẩn chất lượng xác định khi Increment hoàn tất. |
| **Acceptance criteria** | Điều kiện làm rõ hành vi/kết quả mong đợi của một PBI cụ thể. |
| **Definition of Ready (DoR)** | Công cụ làm rõ mức sẵn sàng có thể được nhóm chọn, không bắt buộc trong Scrum Guide. |
| **Cost of Delay** | Chi phí hoặc giá trị bị mất khi trì hoãn một kết quả, tùy giả định và thời gian. |
| **Vertical slice** | Lát cắt khả năng sản phẩm đi qua những thành phần cần thiết để tạo hành vi sử dụng được. |

