# Sắp xếp công việc theo giá trị, rủi ro, phụ thuộc và chi phí trì hoãn

## 1. Vì sao backlog cần được sắp xếp có chủ đích?

Trong phát triển phần mềm Agile, **backlog** là tập hợp những điều nhóm có thể cần làm để tạo ra hoặc bảo vệ giá trị sản phẩm. Nguồn ý tưởng có thể là phản hồi người dùng, cơ hội kinh doanh, lỗi, rủi ro bảo mật, phụ thuộc tích hợp, nợ kỹ thuật hoặc kết quả một thử nghiệm. Năng lực thực hiện luôn có giới hạn, trong khi nhu cầu thay đổi theo thời gian. Vì thế, câu hỏi quan trọng không chỉ là **“phải làm những gì?”** mà còn là **“nên làm gì tiếp theo, vì sao, và có thể trì hoãn điều gì?”**

Sắp xếp thứ tự (*ordering*) giúp nhóm tập trung vào kết quả quan trọng, nhận phản hồi sớm và giảm thiểu chi phí của việc chờ đợi. Với module **AGILE_DEVELOPMENT**, đây là cầu nối giữa user story, quản lý backlog, giao Increment, Scrum, Kanban, các thực hành kỹ thuật của XP và đo lường luồng công việc.

Hãy xét một nền tảng học trực tuyến có năm yêu cầu: sửa lỗi đăng ký trùng, thêm bộ lọc khóa học, cho phép tự hủy đăng ký, cải thiện kiểm soát quyền truy cập và làm dashboard báo cáo. Nếu chỉ chọn việc “dễ làm nhất” hoặc “người có chức vụ cao nhất vừa yêu cầu”, nhóm có thể bỏ lỡ vấn đề gây thiệt hại lớn hoặc làm chậm những khả năng có ích nhất.

**Ưu tiên là quyết định đầu tư năng lực có giới hạn.** Mọi lựa chọn đều có đánh đổi: làm việc A hôm nay thường đồng nghĩa với việc B phải chờ thêm. Cách ra quyết định tốt cần có mục tiêu rõ, bằng chứng phù hợp, giải thích được và sẵn sàng thay đổi khi xuất hiện thông tin mới.

## 2. Hiểu đúng backlog và việc ưu tiên

### 2.1. Backlog không phải danh sách cam kết làm tất cả

Trong Scrum, **Product Backlog** là danh sách nổi lên, được sắp xếp của những gì cần thiết để cải thiện sản phẩm. **Product Owner** chịu trách nhiệm tối đa hóa giá trị của sản phẩm và quản lý Product Backlog hiệu quả, bao gồm việc sắp xếp các Product Backlog Items. Người này có thể ủy quyền một phần công việc, nhưng vẫn chịu trách nhiệm cuối cùng.

Trong một nhóm không sử dụng Scrum, backlog vẫn có thể được quản lý theo nguyên tắc tương tự: công việc được mô tả đủ rõ, có người chịu trách nhiệm ưu tiên, có chính sách tiếp nhận và được rà soát định kỳ. Đừng nhầm backlog với lời hứa sẽ thực hiện toàn bộ các mục đã ghi.

Các mục ở gần thời điểm thực hiện nên được làm rõ và chia nhỏ hơn các ý tưởng ở xa. Đây là **lập kế hoạch thích ứng**: dành độ chi tiết cho những quyết định hiện tại, giảm lãng phí mô tả chính xác những việc có thể không bao giờ được ưu tiên.

### 2.2. “Quan trọng”, “khẩn cấp” và “đầu tiên” không đồng nghĩa

Một hạng mục **quan trọng** vì có giá trị hoặc ảnh hưởng lớn; nó **khẩn cấp** khi thời điểm thực hiện làm thay đổi mạnh kết quả hoặc rủi ro; nó được làm **đầu tiên** khi lựa chọn đó phù hợp với các điều kiện thực tế như phụ thuộc, năng lực và giới hạn công việc dở dang.

Ví dụ:

- Tính năng xuất báo cáo có giá trị lớn nhưng người dùng chưa cần đến quý sau.
- Một lỗ hổng đang bị khai thác có thể cần ứng cứu ngay, bất kể điểm ước lượng.
- Chức năng tự hủy đăng ký có giá trị cao nhưng phụ thuộc một API phân quyền chưa sẵn sàng.
- Một thử nghiệm nhỏ có thể rẻ, giúp kiểm chứng giả định lớn trước khi nhóm đầu tư vào giải pháp đắt tiền.

Vì vậy, **ưu tiên cao không luôn đồng nghĩa với khả năng bắt đầu ngay**. Nhóm cần vừa sắp xếp theo giá trị, vừa lập thứ tự triển khai có thể thực hiện.

### 2.3. Bốn góc nhìn bổ sung cho nhau

| Yếu tố | Câu hỏi chính | Ví dụ về quyết định |
| --- | --- | --- |
| **Giá trị (value)** | Làm xong sẽ mang lại hoặc bảo vệ lợi ích nào cho ai? | Ưu tiên luồng đăng ký giúp học viên hoàn tất nhanh hơn. |
| **Rủi ro (risk)** | Điều gì có thể thất bại, tác động ra sao và làm sớm giúp giảm bất định nào? | Kiểm thử xử lý đăng ký đồng thời trước khi tăng lưu lượng. |
| **Phụ thuộc (dependency)** | Việc nào phải có trước, ai cần phối hợp và đâu là đường găng? | Xác nhận hợp đồng API trước khi tích hợp chức năng hủy đăng ký. |
| **Chi phí trì hoãn (cost of delay)** | Mỗi khoảng thời gian chờ khiến chúng ta mất điều gì? | Chậm sửa lỗi mỗi tuần tiếp tục gây yêu cầu hỗ trợ và mất đăng ký. |

Không có một công thức điểm chung đúng cho mọi sản phẩm. Bốn góc nhìn này giúp tổ chức **giải thích được sự đánh đổi** và kiểm tra các thiên lệch trong quyết định.

## 3. Ưu tiên theo giá trị: tìm kết quả, không chỉ đếm tính năng

### 3.1. Tách đầu ra khỏi kết quả

**Đầu ra (output)** là thứ nhóm tạo ra: màn hình, API, báo cáo, đoạn mã. **Kết quả (outcome)** là thay đổi có ích ở hành vi hoặc tình trạng của người dùng/tổ chức: tự hoàn tất đăng ký, giảm thời gian xử lý thủ công, giảm lỗi sản xuất hoặc bảo vệ dữ liệu.

Ví dụ:

| Hạng mục | Đầu ra | Kết quả kỳ vọng | Bằng chứng có thể theo dõi |
| --- | --- | --- | --- |
| Đăng ký khóa học trực tuyến | Form, API và bản ghi đăng ký | Học viên tự đăng ký thành công. | Tỷ lệ hoàn tất, thời gian đăng ký, lỗi đăng ký. |
| Bộ lọc khóa học | Công cụ lọc theo chủ đề | Học viên tìm được lớp phù hợp nhanh hơn. | Tỷ lệ tìm thấy, số thao tác, kết quả thử nghiệm. |
| Sửa lỗi đăng ký trùng | Quy tắc xử lý đồng thời và test | Giảm dữ liệu sai, giảm xử lý thủ công. | Số bản ghi trùng, ticket hỗ trợ, tỷ lệ lỗi. |
| Cải thiện logging | Log và cảnh báo có cấu trúc | Phát hiện, điều tra và khôi phục sự cố nhanh hơn. | Thời gian phát hiện, thời gian phục hồi, chất lượng cảnh báo. |

Một tính năng được giao đúng kỹ thuật nhưng ít người dùng hoặc không giải quyết vấn đề có thể tạo **ít giá trị hơn kỳ vọng**. Vì thế, backlog nên gắn hạng mục với kết quả có thể kiểm chứng, không chỉ ước lượng thời gian hoàn thành.

### 3.2. Giá trị có nhiều hình thức

Giá trị không đồng nhất với doanh thu:

- **Giá trị người dùng:** giảm thao tác, tăng khả năng tiếp cận, tăng độ tin cậy và mức hài lòng.
- **Giá trị kinh doanh:** tăng chuyển đổi, giữ chân, tiết kiệm chi phí, đáp ứng cam kết dịch vụ.
- **Giá trị bảo vệ:** tránh tổn thất, vi phạm bảo mật, lỗi dữ liệu hoặc gián đoạn vận hành.
- **Giá trị hỗ trợ khả năng tương lai:** cải thiện nền tảng kỹ thuật, kiến trúc, tự động hóa để có thể giao nhiều giá trị khác nhanh hơn.
- **Giá trị học hỏi:** một thử nghiệm nhỏ có thể giúp tránh đầu tư lớn vào giả định sai.

Một hạng mục kỹ thuật như bổ sung kiểm thử cạnh tranh cơ sở dữ liệu hoặc nâng cấp thư viện có thể không có màn hình mới, nhưng vẫn đáng ưu tiên vì **bảo vệ khả năng giao hàng và niềm tin của người dùng**.

### 3.3. Hỏi “giá trị cho ai?” và “bằng chứng mạnh tới đâu?”

Khi đánh giá một mục, hãy xác định:

1. Ai hưởng lợi, và vấn đề của họ hiện nghiêm trọng tới đâu?
2. Kết quả thay đổi nào được kỳ vọng? Có số liệu hiện trạng không?
3. Bằng chứng dựa trên hành vi thật, thử nghiệm nhỏ, phỏng vấn hay chỉ giả định?
4. Có phương án nhỏ hơn để nhận cùng phần lớn giá trị không?
5. Điều gì xảy ra nếu không làm mục đó trong khoảng thời gian hiện tại?

Một ý tưởng có **giá trị dự kiến rất cao nhưng bằng chứng yếu** có thể nên được ưu tiên cho một *spike* hoặc thử nghiệm khám phá trước khi xây toàn bộ tính năng. Không nên xem “độ chắc chắn thấp” là lý do tự động loại bỏ cơ hội; nó là tín hiệu cần thiết kế cách học hiệu quả.

## 4. Ưu tiên theo rủi ro: xử lý điều nguy hiểm và điều chưa biết

### 4.1. Phân biệt rủi ro với sự không chắc chắn

**Rủi ro** là khả năng một sự kiện hoặc điều kiện không chắc chắn gây tác động lên mục tiêu. Mỗi rủi ro cần nhìn ít nhất vào **khả năng xảy ra** và **mức độ tác động**. Trong thực hành, một đánh giá định tính như thấp/vừa/cao đôi khi hữu ích hơn một điểm số chính xác giả tạo.

**Sự không chắc chắn** bao gồm những điều chưa được biết: người dùng có thật sự cần tính năng không, API đối tác có đáp ứng hiệu năng không, cách chống đăng ký trùng có hoạt động trong tải thực tế không.

Làm sớm một phần việc có thể:

- Giảm xác suất hoặc tác động của một rủi ro, ví dụ sửa kiểm soát truy cập.
- Cung cấp thông tin để đưa ra quyết định, ví dụ spike kiểm chứng khả năng chịu tải.
- Tránh phát hiện muộn vấn đề có chi phí sửa cao, ví dụ hợp đồng dữ liệu không tương thích.
- Bảo vệ công việc đang được xây trên một giả định kỹ thuật quan trọng.

### 4.2. Ma trận rủi ro chỉ là công cụ thảo luận

Một nhóm có thể dùng thang định tính:

| Rủi ro | Khả năng | Tác động | Hành động ưu tiên tham khảo |
| --- | --- | --- | --- |
| Sai phân quyền làm lộ thông tin cá nhân | Chưa rõ | Rất cao | Kiểm tra, khoanh vùng và xử lý phù hợp chính sách bảo mật trước khi mở rộng sử dụng. |
| API bên ngoài thay đổi cấu trúc response | Vừa | Cao | Liên hệ chủ sở hữu hợp đồng, viết contract test và phương án tương thích. |
| Bộ lọc khóa học ít người dùng | Vừa | Thấp đến vừa | Thử giao diện/prototype, đo mức quan tâm trước khi phát triển toàn bộ. |
| Một lỗi bố cục nhỏ ở màn phụ | Thấp | Thấp | Sắp xếp theo tác động thực tế và DoD đã thống nhất. |

Không được dùng điểm trung bình để trì hoãn **nghĩa vụ bắt buộc** như bảo vệ dữ liệu, ứng cứu sự cố hoặc yêu cầu pháp lý có hạn chót. Những điều này tạo **ràng buộc quyết định** trước khi so sánh điểm ưu tiên thông thường.

### 4.3. Chọn cách giảm rủi ro với chi phí hợp lý

Ví dụ, nhóm định tích hợp một nhà cung cấp thanh toán mới. Chưa biết API có hỗ trợ xử lý giao dịch lặp an toàn không. Thay vì ưu tiên ngay UI thanh toán hoàn chỉnh, nhóm có thể:

1. Làm rõ yêu cầu idempotency và đối soát với người có thẩm quyền nghiệp vụ.
2. Thực hiện spike giới hạn thời gian để thử tình huống kết nối gián đoạn, retry và phản hồi trùng.
3. Viết ra phát hiện, rủi ro còn lại và quyết định thiết kế.
4. Chia phần triển khai sau đó thành các Increment có thể kiểm chứng.

Spike tạo **giá trị học hỏi**, nhưng chưa phải Increment tính năng hoàn tất cho người dùng. Cần hạn chế thời gian, có câu hỏi rõ và quyết định tiếp theo để tránh biến mọi công việc khó thành “nghiên cứu vô thời hạn”.

### 4.4. Nợ kỹ thuật cũng cần được đánh giá theo rủi ro và giá trị

Không nên ưu tiên nợ kỹ thuật chỉ vì “mã chưa đẹp”, cũng không nên chỉ làm tính năng mới. Với mỗi khoản nợ, hãy hỏi:

- Nó đang gây lỗi, chậm phát hành hoặc khó kiểm thử ở mức nào?
- Tần suất nhóm phải sửa hoặc đụng tới thành phần này?
- Chi phí tiếp tục trì hoãn việc cải thiện có tăng theo thời gian không?
- Có cách cải thiện từng phần, được bảo vệ bằng kiểm thử không?
- Nó là điều kiện cần để triển khai giá trị sắp tới hay không?

Một thay đổi kiến trúc có thể đáng làm sớm khi giảm rủi ro nghiêm trọng hoặc mở đường cho nhiều tính năng; nhưng **không nên tự động xếp mọi bản refactor trước công việc người dùng**.

## 5. Ưu tiên theo phụ thuộc: thứ tự giá trị và thứ tự thực hiện

### 5.1. Các loại phụ thuộc thường gặp

**Phụ thuộc** là quan hệ trong đó một công việc cần điều kiện, đầu ra, quyết định hoặc nguồn lực của công việc/bên khác để có thể bắt đầu hoặc hoàn tất.

| Loại phụ thuộc | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Kỹ thuật** | Chức năng hủy đăng ký cần API xác nhận quyền học viên. | Xác định hợp đồng tối thiểu, thực hiện hoặc giả lập có kiểm soát trước khi tích hợp. |
| **Dữ liệu / nghiệp vụ** | Hệ thống cần quy tắc thế nào là “hết chỗ”. | Làm rõ với Product Owner/chuyên gia nghiệp vụ trước khi cố định thiết kế. |
| **Liên nhóm** | Đội khác sở hữu dịch vụ email, thanh toán hoặc dữ liệu chung. | Thống nhất người phụ trách, hợp đồng, thời điểm và cách kiểm tra tích hợp. |
| **Phê duyệt / tuân thủ** | Chưa có đánh giá quyền riêng tư hoặc quyền truy cập sandbox. | Chuẩn bị bằng chứng sớm; phối hợp người có thẩm quyền theo quy trình. |
| **Năng lực / tài nguyên** | Một môi trường thử nghiệm hoặc chuyên gia chỉ phục vụ được một số việc cùng lúc. | Lập kế hoạch năng lực, giảm WIP và ưu tiên phần việc chặn nhiều hạng mục. |
| **Tri thức / phát hiện** | Chưa biết dịch vụ đối tác có đạt yêu cầu tải hay không. | Thử nghiệm giới hạn thời gian để giảm rủi ro trước quyết định lớn. |

Phụ thuộc cần được nhìn thấy trên backlog hoặc công cụ công việc, không chỉ được ghi trong một bản kế hoạch ít người đọc.

### 5.2. Phân biệt “phải xong trước” với “thuận tiện hơn nếu xong trước”

Có những quan hệ thực sự bắt buộc, ví dụ không thể kiểm thử tích hợp trên hệ thống thật khi chưa có quyền truy cập. Nhưng cũng có những phụ thuộc do cách tổ chức công việc tạo ra: “toàn bộ database phải xong rồi frontend mới được bắt đầu”.

Nhóm có thể giảm phụ thuộc bằng:

- **Lát cắt dọc (vertical slice):** xây một hành vi người dùng hoàn chỉnh xuyên qua các lớp cần thiết.
- **Hợp đồng giao tiếp rõ:** thống nhất API schema, mã lỗi, ví dụ, thời điểm tương thích.
- **Test double và contract test:** phát triển song song khi hợp đồng đủ rõ, sau đó kiểm chứng với dịch vụ thật.
- **Tách khả năng thành phần nhỏ:** giao luồng đăng ký cơ bản trước khi xây nhiều báo cáo, bộ lọc và nhắc lịch.
- **Phối hợp sớm với nhóm phụ thuộc:** công khai điều kiện cần, chủ sở hữu và bằng chứng hoàn tất.

Không được đánh dấu tích hợp là Done chỉ vì test với mock đạt nếu DoD yêu cầu xác minh trên hệ thống thật.

### 5.3. Sơ đồ phụ thuộc và đường đi đến giá trị

Giả sử **C — Tự hủy đăng ký** cần **B — API kiểm tra quyền**. Các tính năng **A — Sửa lỗi đăng ký trùng** và **D — Bộ lọc khóa học** có thể làm độc lập:

~~~mermaid
flowchart LR
    B["B: API kiểm tra quyền"] --> C["C: Tự hủy đăng ký"]
    A["A: Sửa lỗi đăng ký trùng"]
    D["D: Bộ lọc khóa học"]
~~~

Nếu C có giá trị rất cao nhưng B chưa hoàn tất, thứ tự thực hiện khả thi phải tính đến B. Có thể:

1. Làm B với phạm vi tối thiểu để mở đường cho C.
2. Phát triển song song phần không phụ thuộc của C trên một hợp đồng đã thống nhất.
3. Hỏi có cách chia C thành lát cắt nhỏ không cần toàn bộ B hay không.
4. Rà soát mức ưu tiên của cả **chuỗi B → C**, thay vì chấm riêng B là “ít giá trị” và để chuỗi bị tắc.

Một hạng mục hỗ trợ (*enabler*) có thể có giá trị gián tiếp lớn vì nó mở khóa những hạng mục khác. Tránh cộng toàn bộ giá trị của C vào B rồi lại tính giá trị đó lần nữa trong C; nếu dùng điểm số, cần công bố quy tắc tránh **đếm trùng giá trị**.

### 5.4. Không nên biến mọi phụ thuộc thành lý do hoãn việc

Khi thấy phụ thuộc, nhóm cần hỏi liệu có thể:

- Thống nhất giao diện tối thiểu để phát triển song song.
- Thay đổi thứ tự thử nghiệm để kiểm chứng điều rủi ro nhất trước.
- Sử dụng dữ liệu giả/ẩn danh đúng quy định cho thử nghiệm sớm.
- Giảm kích thước hạng mục thay vì đợi một hệ thống hoàn chỉnh.

Nếu phụ thuộc nằm ngoài quyền kiểm soát, cần công khai nguy cơ và người phối hợp. **Sự chờ đợi không được tự động biến thành thêm hàng loạt việc đang dở**, khiến WIP và cycle time tăng lên.

## 6. Chi phí trì hoãn (Cost of Delay) là gì?

### 6.1. Định nghĩa

**Cost of Delay (CoD)** là **giá trị kinh tế bị mất hoặc chi phí phát sinh do trì hoãn việc giao một kết quả**, so với một mốc giao sớm hơn. Nó giúp chuyển câu hỏi “việc nào quan trọng?” thành “mỗi tuần chậm thêm sẽ gây hậu quả thế nào?”.

CoD có thể bao gồm:

- Doanh thu hoặc cơ hội chuyển đổi bị bỏ lỡ.
- Chi phí xử lý thủ công hoặc hỗ trợ khách hàng tiếp tục phát sinh.
- Nguy cơ mất khách hàng và giảm mức hài lòng.
- Tổn thất từ lỗi, sự cố hoặc rủi ro tiếp tục tồn tại.
- Giá trị phụ thuộc của những tính năng khác vẫn chưa được mở khóa.
- Thiệt hại do bỏ lỡ một sự kiện, mùa kinh doanh hoặc hạn chót.

CoD là một **ước lượng phụ thuộc giả định**, đặc biệt khi liên quan tới phản ứng người dùng và cơ hội tương lai. Đừng coi số ước lượng có hai chữ số thập phân là thực tế chắc chắn.

### 6.2. Ví dụ tính đơn giản

Giả sử lỗi đăng ký khiến một nhóm nhân viên phải xử lý thủ công với chi phí ước tính **4 triệu đồng mỗi tuần**, và giả định chi phí này tiếp tục ở mức tương tự nếu chưa sửa. Nếu trì hoãn việc sửa thêm **3 tuần**, chi phí trực tiếp ước tính là:

\[
\text{Chi phí trì hoãn} \approx 4\ \text{triệu đồng/tuần}\times 3\ \text{tuần}=12\ \text{triệu đồng}.
\]

Con số **12 triệu đồng** chỉ phản ánh giả định chi phí thủ công trong ví dụ. Nó chưa tính mức hài lòng, khách rời bỏ, những vụ việc nghiêm trọng, công sức xây giải pháp và lợi ích có thể đạt được bằng việc khác. Nếu chi phí thay đổi theo tuần, phải ước lượng từng giai đoạn hoặc dùng mô hình phù hợp.

Nếu làm việc A trong tuần này khiến việc B chậm thêm một tuần, hãy cân nhắc **chi phí trì hoãn biên** của B trong tuần đó, thay vì chỉ nhìn tổng lợi ích dài hạn.

### 6.3. Chi phí trì hoãn không phải lúc nào cũng tuyến tính

| Kiểu biến thiên | Đặc điểm | Ví dụ |
| --- | --- | --- |
| **Gần tuyến tính** | Mỗi đơn vị thời gian chậm gây tổn thất tương đối ổn định trong một khoảng. | Chi phí nhân viên sửa lỗi thủ công mỗi tuần. |
| **Có hạn chót cố định** | Trước mốc có thể ít tác động; qua mốc xuất hiện thiệt hại lớn. | Tính năng bắt buộc cho một sự kiện hoặc nghĩa vụ tuân thủ có ngày hiệu lực. |
| **Mất cơ hội dần theo thời gian** | Giá trị giảm khi cửa sổ thị trường đóng hoặc đối thủ tiến lên. | Ưu đãi mùa khai giảng chỉ còn ý nghĩa trong giai đoạn tuyển sinh. |
| **Rủi ro tích tụ hoặc phi tuyến** | Mức nguy hiểm có thể tăng mạnh theo quy mô, tải hoặc số người bị ảnh hưởng. | Lỗ hổng bảo mật hoặc lỗi mất dữ liệu chưa được xử lý. |
| **Có thể gần bằng không trong một giai đoạn** | Hoãn ngắn không làm mất nhiều giá trị ở thời điểm hiện tại. | Báo cáo ít được sử dụng trước khi có đủ dữ liệu. |

Với hạn chót bắt buộc hoặc sự cố nghiêm trọng, trước tiên phải tuân theo chính sách quản trị rủi ro. Không nên dùng một phép tính CoD đơn giản để hợp lý hóa việc bỏ qua kiểm soát cần thiết.

### 6.4. Cách ước lượng khi không có số tiền tin cậy

Nhóm có thể bắt đầu bằng **khoảng giá trị** hoặc **thứ bậc tương đối**:

1. Nêu rõ kết quả và người bị ảnh hưởng khi công việc chậm.
2. Chọn khoảng thời gian để so sánh (một tuần, tháng hoặc tới một mốc).
3. Liệt kê bằng chứng: số ticket hỗ trợ, lỗi sản xuất, số phiên sử dụng, doanh thu thực tế, thời gian nhân sự.
4. Ước lượng khoảng thấp/trung bình/cao hoặc mức tương đối.
5. Ghi giả định và độ tin cậy; điều chỉnh khi có dữ liệu mới.

**Không được cộng các chỉ số không cùng đơn vị** như “8 điểm hài lòng + 3 triệu đồng + 5 story point” rồi trình bày như một con số kinh tế. Nếu dùng điểm quy ước, hãy gọi rõ là **điểm để thảo luận** chứ không phải tiền hoặc mức thiệt hại đo được.

## 7. Một số kỹ thuật hỗ trợ sắp xếp backlog

Các kỹ thuật dưới đây chỉ giúp **cấu trúc cuộc trao đổi**. Product Owner, nhóm và các bên liên quan vẫn phải kiểm tra rủi ro, phụ thuộc, hạn chót, giá trị học hỏi và mục tiêu sản phẩm.

### 7.1. Sắp xếp theo giá trị và nỗ lực

Một ma trận đơn giản:

| Giá trị kỳ vọng | Nỗ lực/chi phí thấp | Nỗ lực/chi phí cao |
| --- | --- | --- |
| **Cao** | Thường nên xem sớm, nếu không bị chặn hoặc có rủi ro đặc biệt. | Cân nhắc chia lát cắt hoặc spike giảm bất định. |
| **Thấp** | Có thể làm khi có lý do rõ và không chen mất việc quan trọng hơn. | Thường nên hoãn hoặc bỏ, trừ khi là điều kiện bắt buộc/hỗ trợ chiến lược. |

Ma trận dễ dùng nhưng bỏ qua **tính cấp thiết theo thời gian** và **quan hệ phụ thuộc**, nên chỉ thích hợp làm bước đầu.

### 7.2. Weighted Shortest Job First (WSJF)

**WSJF** là cách ưu tiên dựa trên **chi phí trì hoãn tương đối so với quy mô công việc**:

\[
\text{WSJF}=\frac{\text{Cost of Delay}}{\text{Job Size}}.
\]

Một cách triển khai được sử dụng trong một số khung thực hành như SAFe ước lượng Cost of Delay bằng ba thành phần **User/Business Value**, **Time Criticality** và **Risk Reduction / Opportunity Enablement** theo **điểm tương đối**, rồi chia cho **Job Size** tương đối. Cần hiểu đây là **một mô hình ưu tiên có giả định và quy ước**, không phải công thức kinh tế chính xác hoặc yêu cầu bắt buộc của Agile/Scrum.

Lưu ý:

- So sánh các mục ở cùng bối cảnh và cùng quy ước chấm điểm.
- Job Size phải khác 0 và cần phản ánh khối lượng/độ phức tạp tương đối đã được trao đổi.
- Một mục có WSJF cao vẫn có thể bị chặn bởi phụ thuộc.
- Cần xét các công việc bắt buộc và giới hạn chất lượng trước khi áp dụng thứ tự.
- Không lấy một điểm WSJF làm lý do bỏ qua khả năng học hỏi hoặc tác động lan tỏa không được chấm đủ.

Nếu có ước lượng CoD bằng tiền/tuần và quy mô bằng ngày công như trong ví dụ sau, thương số là **chỉ số so sánh có đơn vị**, không tự động là “WSJF chuẩn SAFe”. Sự so sánh chỉ có ý nghĩa khi giả định đủ tương đồng.

### 7.3. RICE, MoSCoW và các cách khác

| Kỹ thuật | Cách nhìn | Giới hạn cần nhớ |
| --- | --- | --- |
| **RICE** | Reach × Impact × Confidence / Effort để so sánh cơ hội sản phẩm. | Dễ bị thổi phồng giả định; không mô tả đầy đủ phụ thuộc, hạn chót và nghĩa vụ bắt buộc. |
| **MoSCoW** | Must have, Should have, Could have, Won't have (hiện tại) để thương lượng phạm vi. | Nếu mọi mục đều gắn “Must”, phương pháp mất giá trị; cần mốc phạm vi rõ. |
| **WSJF** | CoD tương đối / kích thước công việc, chú ý chi phí của việc chờ. | Điểm số phụ thuộc cách ước lượng; chưa tự giải quyết chuỗi phụ thuộc. |
| **Value–Effort Matrix** | So sánh giá trị và nỗ lực trên hai trục. | Đơn giản nhưng dễ bỏ qua đường thời gian, rủi ro và giới hạn bắt buộc. |

Không nên áp dụng tất cả kỹ thuật cùng lúc để tạo cảm giác chính xác. Chọn phương pháp **vừa đủ phức tạp để ra quyết định tốt** và kiểm tra hiệu quả bằng kết quả sau khi giao.

## 8. Tình huống thực tế: sắp xếp backlog cho nền tảng học trực tuyến

Nhóm đang phát triển khả năng đăng ký và quản lý khóa học. Các mục đều có lý do hợp lệ nhưng nhóm chỉ có năng lực xử lý một phần trong chu kỳ tới.

### 8.1. Tập hợp mục tiêu và ràng buộc

**Mục tiêu sản phẩm hiện tại:** học viên tự hoàn tất đăng ký và quản lý chỗ học đáng tin cậy, giảm lỗi và công sức hỗ trợ.

**Ràng buộc:** không để lộ dữ liệu cá nhân, không xác nhận đăng ký vượt sức chứa, các Increment cần đáp ứng Definition of Done. Nếu có sự cố đang xảy ra, nhóm phải thực hiện theo quy trình ứng cứu phù hợp trước khi sắp xếp công việc thông thường.

**Thông tin ước lượng giả định** dưới đây dùng để học cách suy nghĩ. CoD chỉ phản ánh thành phần kinh tế giả định theo triệu đồng/tuần, quy mô là số ngày công ước tính; dữ liệu **không phải quan sát của một sản phẩm thực**.

| ID | Công việc | CoD ước tính (triệu đồng/tuần) | Quy mô (ngày công) | CoD / quy mô | Phụ thuộc |
| --- | --- | ---: | ---: | ---: | --- |
| **A** | Sửa lỗi tạo đăng ký trùng | 12 | 3 | 4,00 | Không |
| **B** | Hoàn thiện API phân quyền học viên | 5 | 4 | 1,25 | Không; cần trước C |
| **C** | Cho phép học viên tự hủy đăng ký | 10 | 5 | 2,00 | Cần B |
| **D** | Thêm bộ lọc khóa học theo chủ đề | 4 | 2 | 2,00 | Không |
| **F** | Thử nghiệm cải thiện bước hướng dẫn học viên mới | 3 | 1 | 3,00 | Không |

Ví dụ phép tính:

\[
\text{Tỷ số của A}=\frac{12}{3}=4,\qquad
\text{Tỷ số của C}=\frac{10}{5}=2.
\]

Nếu chỉ xếp theo tỷ số, ta sẽ có thứ tự gần như **A → F → C/D → B** (C và D cùng điểm). Nhưng **C không thể hoàn tất trước B** theo giả định đã nêu. Vì thế đây **chưa phải kế hoạch thực hiện hợp lệ**.

Giả sử còn mục **E — Khắc phục lỗ hổng quyền truy cập dữ liệu** đã được đánh giá là nghiêm trọng và phải xử lý theo chính sách an toàn. Nhóm cần xác minh mức độ, triển khai biện pháp phù hợp và dành năng lực cần thiết theo quy trình bắt buộc. **Không đưa E vào một bảng CoD giả định rồi cho phép điểm thấp khiến nó bị bỏ qua.**

### 8.2. Từ thứ tự điểm số đến kế hoạch khả thi

Sau khi xử lý nghĩa vụ cấp thiết, nhóm có thể thảo luận:

1. **A** có CoD giả định cao, quy mô nhỏ và bảo vệ luồng đăng ký chính; đây là ứng viên mạnh để xử lý sớm.
2. **F** có tỷ số cao nhưng giá trị mới là giả thuyết; có thể thử một mẫu nhỏ để lấy phản hồi với ít nỗ lực.
3. **C** mang lại lợi ích đáng kể nhưng cần **B**; không nên chỉ so B và C như hai mục độc lập. Cần xem tổng giá trị, quy mô, thời điểm có thể giao và khả năng chia nhỏ B.
4. **D** độc lập và tương đối nhỏ; có thể giao nhanh khi giúp đạt mục tiêu sản phẩm hoặc tận dụng năng lực đang sẵn có.
5. Những giả định CoD hoặc kích thước còn yếu nên được cập nhật sau trao đổi với nhóm kỹ thuật, người dùng và chủ sở hữu sản phẩm.

Một **phương án minh họa**, sau khi kiểm tra năng lực và hoàn cảnh, là làm A, thực hiện thử nghiệm F, chuẩn bị lát cắt tối thiểu của B, rồi hoàn tất C; D có thể được xếp vào thời điểm phù hợp. Đây **không phải thứ tự duy nhất đúng**: nếu bộ lọc D đang cần gấp trước mùa tuyển sinh còn C chưa có bằng chứng nhu cầu, nhóm có thể ưu tiên D.

### 8.3. Xem giá trị của cả chuỗi phụ thuộc

Nếu B có giá trị trực tiếp thấp, nhưng **mở khóa C và nhiều hạng mục khác**, chỉ số độc lập của B sẽ đánh giá thiếu tác dụng của nó.

~~~mermaid
flowchart LR
    A["A: Sửa đăng ký trùng"] --> G["Luồng đăng ký đáng tin cậy"]
    B["B: API phân quyền"] --> C["C: Tự hủy đăng ký"]
    C --> H["Giảm thao tác hỗ trợ"]
    F["F: Thử nghiệm onboarding"] --> I["Học từ hành vi học viên mới"]
    D["D: Bộ lọc"] --> J["Tìm khóa phù hợp"]
~~~

Câu hỏi không chỉ là “B có điểm bao nhiêu?” mà là:

- Nếu bỏ B, ta mất hoặc hoãn những giá trị nào?
- Có cách xây **phiên bản B tối thiểu** chỉ phục vụ C không?
- Có thể bắt đầu phần thiết kế/giao diện của C trong khi chờ B mà không làm tăng WIP vô ích không?
- Có cần thống nhất hợp đồng API trước khi các nhóm phát triển song song không?

Thứ tự ưu tiên **đánh giá điều nên đầu tư**; kế hoạch triển khai **kiểm tra điều có thể giao thật**. Hai bước phải được nối với nhau.

### 8.4. Điều gì xảy ra khi bằng chứng thay đổi?

Sau thử nghiệm, nhóm phát hiện tính năng F không cải thiện tỷ lệ học viên hoàn tất bước đầu như kỳ vọng. Họ có thể giảm ưu tiên việc mở rộng F, thay vì tiếp tục chỉ vì nó từng có tỷ số tốt.

Nếu lỗi A được khắc phục và số ticket hỗ trợ giảm mạnh, chi phí trì hoãn của A không còn là lý do cho những hạng mục cùng loại khác khi chưa có bằng chứng mới.

Nếu mùa khai giảng đến gần khiến D có cửa sổ giá trị ngắn, **tính cấp thiết theo thời gian** của D thay đổi, và backlog cần được sắp xếp lại. Đây chính là bản chất của ưu tiên thích ứng: **quyết định dựa trên thông tin mới, không bảo vệ thứ tự cũ bằng mọi giá**.

## 9. Một quy trình thực hành để sắp xếp backlog

### Bước 1 — Thống nhất mục tiêu và điều kiện không thể thương lượng

Nêu rõ Product Goal hoặc mục tiêu trong giai đoạn. Xác định:

- Người dùng cần kết quả gì?
- Tiêu chí nào để kiểm chứng thành công?
- Nghĩa vụ bảo mật, pháp lý, chất lượng và vận hành nào bắt buộc?
- Có hạn chót, sự cố hoặc phụ thuộc quan trọng nào đang tồn tại?

Không thể xếp thứ tự nhất quán nếu mỗi bên đang tối ưu một mục tiêu riêng.

### Bước 2 — Làm rõ từng hạng mục ở mức đủ để so sánh

Với các mục nhiều khả năng thực hiện sớm, ghi:

- Người hưởng lợi, vấn đề và giá trị kỳ vọng.
- Ví dụ hành vi hoặc kết quả có thể kiểm chứng.
- Rủi ro nếu làm/không làm, mức độ chắc chắn của giả định.
- Chi phí trì hoãn hoặc dấu hiệu tính cấp thiết, nếu có.
- Quy mô/nỗ lực tương đối, các phụ thuộc và người liên quan.
- Một lát cắt nhỏ hơn nếu mục quá lớn.

Các mục xa hơn có thể được mô tả ở mức ý tưởng; không cần làm rõ mọi tiêu chí chấp nhận ngay.

### Bước 3 — Phát hiện và xử lý các mục bắt buộc hoặc khẩn cấp

Đánh dấu rõ việc ứng cứu sự cố, kiểm soát bảo mật, nghĩa vụ tuân thủ và deadline có hậu quả thực tế. Xác định cách hành động theo quy trình phù hợp trước khi dùng mô hình chấm điểm thông thường.

Điều này không có nghĩa **mọi công việc được gắn nhãn “khẩn cấp” đều phải ưu tiên cao nhất**. Nên yêu cầu nêu bằng chứng tác động và người có thẩm quyền xác nhận.

### Bước 4 — So sánh các cơ hội còn lại theo giá trị, rủi ro, CoD và quy mô

Có thể dùng bảng thảo luận đơn giản:

| Câu hỏi | Dữ liệu hỗ trợ |
| --- | --- |
| Mục nào tạo/bảo vệ giá trị rõ nhất? | Outcome metric, phản hồi người dùng, doanh thu/chi phí, lỗi. |
| Mục nào đang tích lũy chi phí trì hoãn? | Thời gian chờ, cơ hội mất theo mùa, chi phí hỗ trợ mỗi tuần. |
| Mục nào giảm rủi ro hoặc bất định lớn? | Mức ảnh hưởng, bằng chứng lỗi, spike, kiểm thử, đánh giá an toàn. |
| Mục nào mở đường cho những mục khác? | Sơ đồ phụ thuộc, hợp đồng tích hợp, đường găng. |
| Có lát cắt nhỏ hơn để giao sớm không? | Phân tích user journey, phương án MVP/experiment, ước lượng nhóm. |

Nếu dùng RICE/WSJF, hãy công bố cách chấm và giả định; **không biến công thức thành người ra quyết định**.

### Bước 5 — Kiểm tra thứ tự thực hiện với năng lực và luồng công việc

Một backlog được sắp xếp hợp lý chưa phải lịch thực hiện. Developers cần kiểm tra:

- Năng lực thực tế, kỹ năng cần thiết và khả năng phối hợp.
- Phụ thuộc có thể hoàn tất hay cần lập kế hoạch mở khóa.
- Hạng mục nào đang thực hiện, giới hạn WIP và tác động đổi ngữ cảnh.
- Kiểm thử, tích hợp, phát hành và Definition of Done.
- Rủi ro khi làm nhiều việc song song hoặc giao quá muộn.

Tránh chọn đồng loạt nhiều hạng mục “top priority” nếu không đủ năng lực hoàn tất. **Một phần tăng trưởng Done và dùng được thường tạo phản hồi tốt hơn nhiều hạng mục mới bắt đầu**.

### Bước 6 — Giao, đo kết quả và sắp xếp lại

Sau khi giao Increment hoặc hoàn tất thử nghiệm:

1. Xác minh phần mềm đáp ứng tiêu chí chấp nhận và DoD.
2. Đo kết quả sử dụng/kinh doanh và chất lượng phù hợp.
3. Kiểm tra giả định giá trị, thời gian giao, rủi ro và phụ thuộc.
4. Cập nhật backlog: bổ sung, chia nhỏ, đổi thứ tự, hoãn hoặc bỏ ý tưởng.
5. Ghi ngắn quyết định quan trọng và tác động với người liên quan.

Ưu tiên tốt là một **quá trình liên tục học hỏi**, không phải một lần chấm điểm để giữ nguyên cả quý.

## 10. Scrum và Kanban vận dụng ưu tiên khác nhau thế nào?

### 10.1. Trong Scrum: Product Backlog và Sprint Goal

Trong Scrum, Product Owner chịu trách nhiệm **ordering** của Product Backlog. Các Developers cung cấp thông tin về kích thước, kỹ thuật, phụ thuộc, rủi ro và khả năng thực hiện; người dùng và stakeholder cung cấp bối cảnh giá trị.

**Backlog refinement** giúp chia nhỏ và làm rõ những Product Backlog Items sắp được chọn. Trong **Sprint Planning**, Scrum Team thống nhất Sprint Goal; Developers chọn và lập kế hoạch thực hiện các hạng mục phù hợp với mục tiêu trong năng lực dự kiến. Sau đó, trong Sprint, nhóm kiểm tra và thích ứng với thông tin mới.

Điểm cần phân biệt:

- **Product Backlog order** cho biết các cơ hội cải thiện sản phẩm đang được ưu tiên như thế nào.
- **Sprint Goal** cho biết mục tiêu chung mà Sprint cần hướng tới.
- **Sprint Backlog** là kế hoạch do Developers sở hữu và cập nhật để đạt Sprint Goal.
- **Definition of Done** là chuẩn chất lượng mà Increment phải đạt; không được giảm chuẩn để làm đẹp tiến độ.

Không nên tự động lấy tất cả mục có điểm số cao nhất vào một Sprint nếu chúng không cùng phục vụ Sprint Goal hoặc không thể hoàn tất. Khi phát hiện điều mới, phạm vi có thể được làm rõ và thương lượng lại với Product Owner, nhưng không nên thay đổi theo cách gây nguy hiểm cho Sprint Goal.

### 10.2. Trong Kanban: ưu tiên gắn với chính sách nhận việc và WIP

Kanban nhấn mạnh **trực quan hóa workflow, chủ động quản lý công việc dở dang, điều hành luồng và cải thiện liên tục**. Nhóm có thể có một hàng đợi đã sắp thứ tự trước cột “Sẵn sàng”, rồi dùng chính sách **pull** để nhận việc khi có năng lực.

Ví dụ về chính sách đơn giản:

| Thời điểm | Quy tắc |
| --- | --- |
| **Tiếp nhận** | Ghi mục tiêu, người hưởng lợi và tác động; phân biệt ý tưởng với sự cố thực sự. |
| **Xếp ưu tiên** | Xem giá trị, thời gian cấp thiết, rủi ro, phụ thuộc và quy mô. |
| **Sẵn sàng** | Hạng mục đủ rõ để nhóm làm, có điều kiện chấp nhận và phụ thuộc quan trọng được xác định. |
| **Bắt đầu** | Chỉ kéo thêm việc khi có năng lực, theo chính sách WIP. |
| **Bị chặn** | Hiển thị blocker, người phối hợp và cách xử lý; không giấu tuổi hạng mục. |
| **Hoàn tất** | Đáp ứng tiêu chuẩn chất lượng; thu phản hồi để cập nhật thứ tự tiếp theo. |

Kanban không bắt buộc có Sprint, nhưng nhóm vẫn cần nhịp xem lại backlog, phụ thuộc và kết quả. Một việc “khẩn cấp” không nên được sử dụng như nhãn miễn phí cho phép phá mọi WIP limit; ngoại lệ cần được định nghĩa rõ và được quan sát tác động.

### 10.3. XP và chất lượng kỹ thuật bảo vệ giá trị đã ưu tiên

Các thực hành của **Extreme Programming (XP)** như tích hợp liên tục, kiểm thử tự động, refactoring và làm việc gần với người hiểu nghiệp vụ giúp biến backlog thành Increment đáng tin cậy.

Ví dụ, nếu nhóm ưu tiên sửa lỗi đăng ký trùng, các test cạnh tranh, kiểm tra tích hợp và refactoring có kiểm soát có thể cần thiết để sửa đúng nguyên nhân. Không nên cắt chúng chỉ vì có nhiều hạng mục giá trị cao đang chờ; **phần mềm chưa đủ chất lượng không tạo ra giá trị bền vững**.

## 11. Những quyết định khó: giá trị cao nhưng rủi ro, chi phí và phụ thuộc cũng cao

### 11.1. Công việc lớn có giá trị lớn

Nếu chức năng tự hủy đăng ký có lợi ích lớn nhưng cần nhiều thành phần, lựa chọn không chỉ có “làm cả” hoặc “hoãn cả”. Hãy tìm lát cắt dọc:

1. Cho học viên hủy trong một điều kiện đơn giản được thống nhất.
2. Ghi lại lịch sử thay đổi trạng thái.
3. Mở rộng quy tắc thời hạn hủy.
4. Bổ sung thông báo hoặc luồng xử lý ngoại lệ sau khi có phản hồi.

Mỗi lát cắt cần đáp ứng chuẩn chất lượng và dùng được trong phạm vi đã công bố. Không chia công việc thành “làm database tuần đầu, API tuần sau, giao diện tuần thứ ba” rồi gọi các phần riêng lẻ chưa tích hợp là Increment tạo giá trị.

### 11.2. Việc rẻ nhưng tác động thấp

Hạng mục mất một giờ không tự động nên được làm trước một hạng mục quan trọng đang chờ. Việc “nhặt hết task dễ” có thể tạo cảm giác throughput cao trong khi những vấn đề cốt lõi vẫn tồn tại.

Có thể tận dụng năng lực rảnh cho việc nhỏ khi phụ thuộc tạm thời chưa mở, nhưng phải cân đối **chuyển ngữ cảnh, WIP và mục tiêu hiện tại**.

### 11.3. Việc cần thiết nhưng khó nhìn thấy giá trị

Nâng cấp bảo mật, chuẩn bị khả năng khôi phục hoặc sửa pipeline có thể không có người dùng trực tiếp bấm vào. Hãy chuyển mô tả từ “nâng cấp thư viện” thành **kết quả bảo vệ** như giảm rủi ro lỗ hổng, loại bỏ phiên bản hết hỗ trợ hoặc giảm số lần triển khai lỗi.

Những hạng mục như vậy nên có tiêu chí kiểm chứng rõ, không phải lời hứa “sẽ giúp mọi thứ nhanh hơn” không thể đánh giá.

### 11.4. Người có ảnh hưởng lớn yêu cầu một hạng mục

Nguồn đề nghị là thông tin cần xem xét, nhưng **chức vụ người đề nghị không tự động là tiêu chí giá trị**. Có thể hỏi: mục tiêu nào bị ảnh hưởng, người dùng nào hưởng lợi, nếu chậm thì thiệt hại gì, việc này thay thế công việc nào?

Đồng thời cần tôn trọng những quyết định có thẩm quyền theo chính sách tổ chức. Sự minh bạch giúp tránh xung đột do các bên tưởng rằng mọi đề nghị đều được cam kết.

## 12. Đo lường để kiểm tra cách ưu tiên có hiệu quả không

Một bảng điểm đẹp không bảo đảm backlog được sắp xếp đúng. Sau khi thực hiện, nhóm nên đo **giá trị thực tế và chất lượng luồng giao hàng**:

| Tín hiệu | Mục đích | Cần lưu ý |
| --- | --- | --- |
| **Outcome metrics** | Kiểm tra thay đổi có mang lại lợi ích người dùng/tổ chức không. | Chọn chỉ số phù hợp mục tiêu, tránh kết luận nhân quả vội vàng. |
| **Lead time** | Theo dõi thời gian từ một mốc yêu cầu đến mốc hoàn tất/giao đã định nghĩa. | Điểm bắt đầu/kết thúc phải thống nhất và được công bố. |
| **Cycle time** | Thời gian từ khi bắt đầu xử lý tới khi hoàn tất. | So sánh các loại công việc tương đương; phân tích phân bố và hạng mục bất thường. |
| **Throughput** | Số hạng mục hoàn tất trong một khoảng thời gian. | Số lượng nhiều không chứng minh giá trị cao; dễ bị ảnh hưởng bởi cách chia việc. |
| **WIP / work item age** | Nhìn thấy số việc chưa xong và mục đang chờ quá lâu. | Dùng để phát hiện tắc nghẽn, không đổ lỗi cá nhân. |
| **Chất lượng** | Lỗi sau phát hành, thời gian phục hồi, thất bại triển khai. | Không đánh đổi chất lượng để tối ưu điểm ưu tiên hoặc throughput. |
| **CoD thực tế so với giả định** | Kiểm tra ước lượng thiệt hại khi trì hoãn có hợp lý không. | Nhiều lợi ích khó quy tiền và có yếu tố bên ngoài ảnh hưởng. |
| **Thời gian học hỏi** | Từ giả thuyết đến phản hồi đủ tốt để quyết định. | Thử nghiệm nhanh vẫn cần đúng đối tượng và chất lượng dữ liệu. |

**Ví dụ:** nhóm ưu tiên bộ lọc khóa học vì tin rằng nó tăng chuyển đổi, nhưng sau khi giao tỷ lệ đăng ký không cải thiện. Họ nên kiểm tra thiết kế thử nghiệm, đối tượng sử dụng và giả định giá trị, rồi cập nhật backlog. Tiếp tục đầu tư chỉ vì “đã chấm điểm cao” sẽ đi ngược tinh thần Agile.

### 12.1. Đừng biến điểm số thành KPI cho cá nhân

Story point, số ticket hay điểm WSJF/RICE không phải phép đo năng suất cá nhân. Nếu đánh giá nhân viên theo số điểm hoàn thành, họ có thể chia nhỏ việc giả tạo hoặc ưu tiên công việc dễ chấm, làm méo cách ra quyết định.

Hãy dùng dữ liệu để đặt câu hỏi như “vì sao nhóm chờ API quá lâu?”, “hạng mục nào đang chặn giá trị lớn?” và “kết quả nào chứng minh lần ưu tiên trước đúng?”.

## 13. Các phản mẫu khi sắp xếp backlog

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Ai nói lớn nhất được ưu tiên trước** | Backlog thay đổi thất thường, mục tiêu sản phẩm mất rõ ràng. | Công bố tiêu chí giá trị, rủi ro, CoD và quyền quyết định. |
| **Mọi thứ đều “P0” hoặc “Must have”** | Không còn cách phân biệt tính cấp thiết. | Định nghĩa rõ mức ưu tiên và bằng chứng cho công việc khẩn cấp. |
| **Chỉ chọn việc dễ hoặc điểm ratio cao** | Bỏ sót phụ thuộc, rủi ro lớn và cơ hội có giá trị lâu dài. | Kiểm tra chuỗi phụ thuộc và ràng buộc bắt buộc trước khi lập kế hoạch. |
| **Chấm điểm như một phép đo chính xác tuyệt đối** | Tranh luận số lẻ, bỏ qua giả định và bối cảnh. | Dùng khoảng giá trị, mức tin cậy và giải thích bằng chứng. |
| **Đếm trùng giá trị ở hạng mục nền tảng và tính năng sử dụng nó** | Thổi phồng lợi ích của một chuỗi công việc. | Rà soát giá trị trực tiếp và giá trị mở khóa, tránh cộng hai lần. |
| **Tự động làm theo deadline không được xác minh** | Công việc quan trọng hơn bị chen mất chỗ. | Hỏi nguồn mốc thời gian và hậu quả thực sự nếu chậm. |
| **Không cập nhật backlog sau phản hồi** | Tiếp tục đầu tư vào giả định đã không còn đúng. | Rà soát outcome, rủi ro, CoD và phụ thuộc thường xuyên. |
| **Không tính công việc bảo trì và kiểm thử** | Increment khó phát hành, chất lượng suy giảm. | Đưa rủi ro kỹ thuật và điều kiện DoD vào kế hoạch. |
| **Mở quá nhiều mục ưu tiên cùng lúc** | WIP lớn, thời gian phản hồi tăng, ít hạng mục Done. | Giới hạn WIP, tập trung hoàn tất lát cắt có giá trị. |
| **Không giải thích lý do hoãn một đề nghị** | Stakeholder tưởng yêu cầu bị bỏ quên hoặc âm thầm cam kết. | Ghi rõ quyết định, điều kiện xem lại và các đánh đổi. |

## 14. Bài tập thực hành

### Bài tập 1 — Tính và phản biện thứ tự CoD / quy mô

Một nhóm có ba hạng mục độc lập, với **số liệu minh họa**:

| Hạng mục | CoD (triệu đồng/tuần) | Quy mô (ngày công) |
| --- | ---: | ---: |
| X — Giảm thao tác hỗ trợ | 9 | 3 |
| Y — Cải thiện tìm kiếm | 8 | 4 |
| Z — Sửa cảnh báo lỗi | 6 | 2 |

1. Tính tỷ số CoD / quy mô cho từng mục.
2. Nếu chỉ xét tỷ số, thứ tự ưu tiên là gì?
3. Điều gì có thể khiến nhóm chọn thứ tự khác?

**Lời giải gợi ý:** X = 9/3 = **3**, Y = 8/4 = **2**, Z = 6/2 = **3**. Theo tỷ số, **X và Z đồng hạng**, rồi đến Y. Cần xem tính cấp thiết, rủi ro, giá trị học hỏi, ràng buộc và phụ thuộc. Nếu cảnh báo Z là điều kiện để phát hiện sự cố nghiêm trọng, nó có thể được xử lý trước dù cùng điểm với X; nếu dữ liệu CoD của X kém tin cậy, nhóm cần kiểm chứng thêm.

### Bài tập 2 — Xử lý phụ thuộc

Nhóm muốn giao **T — Học viên tự đổi lịch học**, nhưng T phụ thuộc **P — API kiểm tra quyền đổi lịch**. Một đề nghị **R — Bộ lọc theo chủ đề** độc lập và có thể hoàn tất nhanh.

Hãy trả lời:

1. Vì sao không thể chỉ so điểm T với R?
2. Có thể chia P thành lát cắt nhỏ nào để mở khóa T?
3. Nhóm cần phối hợp với ai để xác nhận quyền thay đổi lịch?
4. Khi đang chờ P, nên làm gì để tránh tăng WIP không cần thiết?
5. Bằng chứng nào cho thấy T đã hoàn tất đúng DoD?

**Gợi ý:** xem chuỗi P → T và khả năng làm song song dựa trên hợp đồng API; thống nhất quy tắc với Product Owner/chủ sở hữu nghiệp vụ; phát triển phần độc lập có giới hạn, hoàn tất test tích hợp trước khi tuyên bố Done.

### Bài tập 3 — Ước lượng chi phí trì hoãn với hạn chót

Một đơn vị cần cập nhật chức năng xuất dữ liệu để tuân thủ quy định có hiệu lực vào một ngày xác định. Một nhà quản lý đề nghị đánh giá hạng mục này bằng **“2 điểm giá trị người dùng vì ít người bấm nút xuất”**.

Hãy giải thích:

1. Vì sao cách chấm như vậy có thể bỏ sót yếu tố quan trọng?
2. Cần làm rõ nghĩa vụ, hậu quả và thời điểm nào?
3. Hạng mục được ưu tiên và kiểm chứng theo ràng buộc nào?
4. Nếu có thể chia nhỏ, phần nào phải giao trước hạn?

**Gợi ý:** yêu cầu tuân thủ có thể là ràng buộc bắt buộc với thiệt hại lớn tại hạn chót. Nhóm cần xác minh quy định áp dụng, sự phê duyệt và các tiêu chuẩn dữ liệu, rồi lập kế hoạch giao khả năng đáp ứng tối thiểu đúng chất lượng trước mốc yêu cầu.

### Bài tập 4 — Ra quyết định trong một buổi backlog refinement

Hãy chọn bốn đến sáu hạng mục trong sản phẩm bạn biết. Với mỗi mục, viết:

- Người hưởng lợi và kết quả kỳ vọng.
- Mức rủi ro hoặc giả định chưa được kiểm chứng.
- Phụ thuộc quan trọng và người có quyền quyết định.
- Dấu hiệu cấp thiết hoặc chi phí trì hoãn.
- Kích thước tương đối và lát cắt nhỏ khả thi.
- Quyết định: làm sớm, thử nghiệm trước, tách nhỏ, hoãn hay bỏ.

Sau đó đối chiếu thứ tự khi **giả định thay đổi**, ví dụ một API phụ thuộc bị hoãn một tháng hoặc một hạng mục gần deadline thực. Mục tiêu của bài tập là **giải thích được quyết định**, không phải đưa ra một bộ điểm không thể tranh luận.

## 15. Checklist trước khi chốt thứ tự ưu tiên

- [ ] Mục tiêu sản phẩm và kết quả người dùng cần đạt đã rõ.
- [ ] Mỗi mục gần thời điểm thực hiện có mô tả giá trị và cách kiểm chứng phù hợp.
- [ ] Đã đánh giá rủi ro bảo mật, chất lượng, vận hành và bất định quan trọng.
- [ ] Đã kiểm tra hạn chót thật, nghĩa vụ bắt buộc và cách xử lý sự cố.
- [ ] Đã nhận diện phụ thuộc, người chịu trách nhiệm và khả năng chia lát cắt nhỏ.
- [ ] Đã xem chi phí trì hoãn hoặc dấu hiệu mất giá trị khi chờ, kèm giả định.
- [ ] Nếu dùng điểm, cả nhóm hiểu quy ước, nguồn dữ liệu và giới hạn của công thức.
- [ ] Thứ tự thực hiện phù hợp năng lực, WIP và khả năng tích hợp/kiểm thử.
- [ ] Các quyết định hoãn, thay thế hoặc loại bỏ được thông báo minh bạch.
- [ ] Có thời điểm xem lại sau phản hồi và số liệu thực tế.

Checklist là công cụ hỗ trợ cuộc trao đổi, không thay thế phán đoán nghề nghiệp. Với sự cố khẩn cấp hoặc nghĩa vụ bắt buộc, áp dụng quy trình tương ứng trước khi cân nhắc thứ tự công việc thông thường.

## 16. Ghi nhớ

**Giá trị** cho biết điều gì đáng theo đuổi. **Rủi ro** cho biết điều gì cần bảo vệ hoặc kiểm chứng sớm. **Phụ thuộc** cho biết thứ tự nào có thể thực hiện và công việc nào mở khóa giá trị khác. **Chi phí trì hoãn** cho biết thời gian chờ làm mất điều gì. Kết hợp chúng với quy mô, năng lực và chuẩn chất lượng giúp sắp xếp backlog có chủ đích.

Agile không yêu cầu một công thức ưu tiên cố định. Điều cốt lõi là **giải thích được sự đánh đổi, chọn một phần giá trị có thể giao, nhận phản hồi sớm và thay đổi thứ tự khi bằng chứng thay đổi**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa ngắn |
| --- | --- |
| **Backlog** | Danh sách công việc, cơ hội và nhu cầu được xem xét để tạo hoặc bảo vệ giá trị. |
| **Product Backlog** | Danh sách nổi lên, được sắp xếp của những gì cần thiết để cải thiện sản phẩm trong Scrum. |
| **Ordering / prioritization** | Quyết định thứ tự tương đối của công việc dựa trên mục tiêu và các đánh đổi. |
| **Value / outcome** | Lợi ích hoặc thay đổi có ý nghĩa cho người dùng, tổ chức hay các bên liên quan. |
| **Risk** | Khả năng điều không chắc chắn tác động đến mục tiêu; cần xét khả năng và hậu quả. |
| **Dependency** | Quan hệ yêu cầu điều kiện, đầu ra hoặc quyết định khác trước khi có thể thực hiện/hoàn tất. |
| **Enabler** | Công việc hỗ trợ, giảm rủi ro hoặc mở khóa khả năng tạo giá trị khác. |
| **Cost of Delay (CoD)** | Giá trị mất đi hoặc chi phí phát sinh do trì hoãn kết quả. |
| **WSJF** | Phương pháp so sánh tỷ lệ chi phí trì hoãn tương đối với quy mô công việc. |
| **Job Size** | Quy mô/nỗ lực tương đối cần để hoàn tất một mục trong mô hình ưu tiên. |
| **Backlog refinement** | Hoạt động liên tục làm rõ, chia nhỏ và cập nhật hiểu biết về Product Backlog Items. |
| **Definition of Done (DoD)** | Tiêu chuẩn chất lượng chung để xác định Increment đã hoàn tất. |
| **Increment** | Phần sản phẩm tăng thêm, tích hợp và có thể sử dụng, đáp ứng DoD. |
| **WIP** | Số hạng mục đã bắt đầu nhưng chưa hoàn tất. |
| **Lead time / cycle time** | Hai cách đo thời gian chờ/giao và thời gian xử lý theo các điểm bắt đầu, kết thúc được xác định rõ. |
