# Tối ưu toàn hệ thống và nhận diện tác hại của tối ưu cục bộ

> **Chương:** Lean  
> **Học phần:** **AGILE_DEVELOPMENT** — vận dụng giá trị và nguyên tắc Agile vào phát triển phần mềm thích ứng nhờ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để phối hợp hiệu quả.

Một nhóm lập trình tăng tốc độ viết mã lên 40%, nhưng khách hàng vẫn nhận chức năng sau ba tuần. Nhóm kiểm thử có thêm hàng chục yêu cầu đang chờ, người vận hành chỉ triển khai vào cuối tháng, còn các lỗi phát hiện muộn khiến người viết mã liên tục quay lại sửa. Báo cáo từng bộ phận đều có thể đẹp hơn, nhưng **thời gian từ nhu cầu đến giá trị không giảm, thậm chí tăng**.

Đó là biểu hiện điển hình của **tối ưu cục bộ** (*local optimization*): cải thiện chỉ số hoặc năng suất của một người, một nhóm hay một bước riêng lẻ mà không xét tác động lên toàn bộ hệ thống. Trong tư duy **Lean**, lựa chọn tốt hơn là **tối ưu toàn hệ thống** (*optimize the whole*): làm rõ khách hàng cần giá trị gì, theo dõi toàn bộ dòng công việc, xác định điểm cản trở việc giao giá trị và cải tiến mà không chuyển lãng phí hoặc rủi ro sang bước kế tiếp.

Lean không có nghĩa “cắt mọi hoạt động không trực tiếp tạo tính năng” hay “mọi người phải bận 100%”. Kiểm thử an toàn, review quan trọng, thời gian học, trao đổi nghiệp vụ và dự phòng ứng cứu có thể là **những khoản đầu tư cần thiết** cho một hệ thống giao giá trị đáng tin cậy. Bài này đưa ra cách suy nghĩ, dữ liệu và tình huống thực hành để nhận ra sự khác nhau giữa **một bộ phận chạy nhanh** với **một sản phẩm tạo giá trị tốt**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa **tối ưu toàn hệ thống** trong Lean và vì sao thành công cục bộ không tự động tạo thành công của sản phẩm.
2. Vẽ **dòng giá trị** (*value stream*) từ nhu cầu người dùng đến khi nhận và kiểm chứng giá trị; phân biệt thời gian thực hiện, thời gian chờ, công việc dở dang và việc phải làm lại.
3. Nhận diện những phản mẫu: tăng số việc đang làm, đẩy việc sang bước sau, chạy theo số ticket, tối ưu công suất người làm, bỏ kiểm thử để tăng tốc, nhiều điểm bàn giao.
4. Phân tích nút thắt với **WIP, throughput, cycle time, lead time, work item age**, phân bố thời gian và các chỉ số giá trị/chất lượng.
5. Đề xuất thử nghiệm cải tiến có giới hạn, có điều kiện bảo vệ và cách đo tác động trên **toàn hệ thống**, không chỉ ở một cột.
6. Liên hệ Lean với **Scrum, Kanban và XP** để tạo phần mềm hữu ích, ổn định và có khả năng thay đổi khi nhận phản hồi.

## 2. “Toàn hệ thống” trong phát triển phần mềm là gì?

**Hệ thống** ở đây không chỉ là mã nguồn hoặc hạ tầng chạy ứng dụng. Đó là mạng lưới con người, quy trình, công cụ, quyết định, phụ thuộc và vòng phản hồi để biến một nhu cầu thành kết quả.

Với chức năng đặt lịch tư vấn, hệ thống có thể bao gồm:

- Người dùng nêu vấn đề và người làm sản phẩm nhận diện giá trị.
- Product Owner hoặc người chịu trách nhiệm sản phẩm chọn thứ tự ưu tiên.
- Nhóm thiết kế, Developers, QA và vận hành làm rõ, tạo, kiểm tra và phát hành thay đổi.
- API của đối tác, chính sách bảo mật, môi trường kiểm thử và quy trình phê duyệt.
- Công cụ CI/CD, quan sát dữ liệu sử dụng, hệ thống hỗ trợ và cơ chế học từ lỗi.

Mọi phần liên quan đều có thể tác động tới **khoảng thời gian khách hàng phải đợi**, **xác suất tính năng đúng nhu cầu**, **chất lượng khi sử dụng** và **năng lực thay đổi trong tương lai**. Nếu chỉ cải tiến IDE của Developers mà không nhìn thời gian chờ quyền truy cập API, tổng trải nghiệm của khách hàng có thể không thay đổi.

### 2.1. Phân biệt ba lớp mục tiêu

| Lớp mục tiêu | Ví dụ | Khi nào có ích? | Hạn chế nếu dùng một mình |
| --- | --- | --- | --- |
| **Công việc tại một bước (local)** | Số pull request được review mỗi ngày, thời gian chạy test đơn vị. | Chẩn đoán một vấn đề cụ thể và thử cải tiến kỹ thuật. | Có thể làm công việc ùn lại ở bước sau. |
| **Dòng giao giá trị (end-to-end flow)** | Thời gian từ lúc yêu cầu được tiếp nhận đến khi người dùng có thể sử dụng an toàn. | Tìm nơi chờ đợi và kiểm soát khả năng giao. | Giao nhanh không bảo đảm giao **đúng thứ người dùng cần**. |
| **Kết quả sản phẩm và hệ thống (outcome)** | Tỷ lệ đặt lịch thành công, lỗi dữ liệu, sự hài lòng, khả năng giao tiếp các thay đổi. | Xác minh sản phẩm thực sự tạo và giữ giá trị. | Cần nhiều góc nhìn, có độ trễ và chịu ảnh hưởng yếu tố ngoài nhóm. |

**Tối ưu toàn hệ thống** đòi hỏi quan sát cả ba lớp, đặc biệt kết nối các chỉ số cục bộ với **dòng giá trị và outcome**. Điều này không có nghĩa bỏ mọi chỉ số của từng bước; nó có nghĩa **không chọn một chỉ số cục bộ làm mục tiêu tối cao**.

### 2.2. Tối ưu toàn hệ thống không phải cố tối ưu mọi bộ phận cùng lúc

Một hiểu lầm là “tối ưu toàn hệ thống” đồng nghĩa nâng hiệu suất đồng loạt ở mọi nhóm. Thực tế:

- Khi **kiểm thử là nút thắt**, tăng tốc viết code có thể chỉ đẩy nhiều việc hơn tới hàng đợi kiểm thử.
- Khi **chưa biết đúng nhu cầu khách hàng**, tăng cả tốc độ lập trình và kiểm thử vẫn có thể tạo nhiều tính năng ít dùng.
- Khi **sự cố production chiếm phần lớn năng lực**, đầu tư độ tin cậy có thể đem lại giá trị lớn hơn thêm tính năng ngắn hạn.

Nhóm nên tìm **đòn bẩy có tác động lớn nhất lên kết quả toàn hệ thống tại thời điểm hiện tại**, thay vì chia đều ngân sách tối ưu mỗi khâu.

### 2.3. Ranh giới hệ thống quyết định điều nhóm nhìn thấy

Nếu workflow chỉ đo **từ bắt đầu lập trình tới merge**, thời gian chờ backlog, làm rõ nghiệp vụ và phát hành sẽ biến mất khỏi báo cáo. Vì vậy, trước khi dùng số liệu, phải hỏi:

1. **Ai** đang chờ giá trị?
2. **Điểm bắt đầu** tính từ yêu cầu được ghi nhận, chấp nhận hay bắt đầu triển khai?
3. **Điểm kết thúc** là code merge, đạt Definition of Done, phát hành hay kết quả người dùng?
4. **Ràng buộc chất lượng và vận hành** nào nằm ngoài ranh giới đã đo?

Một hệ thống có thể dùng nhiều thước đo với ranh giới khác nhau, nhưng phải **đặt tên và giải thích rõ**, tránh so sánh sai.

## 3. Lean và bảy nguyên tắc phát triển phần mềm Lean

Lean có nguồn gốc từ tư duy cải tiến hệ thống sản xuất và được vận dụng vào nhiều ngành. Trong phát triển phần mềm, một hệ nguyên tắc Lean Software Development phổ biến thường được diễn đạt như sau:

| Nguyên tắc | Câu hỏi thực hành | Liên hệ với Agile |
| --- | --- | --- |
| **Loại bỏ lãng phí (Eliminate waste)** | Công việc và chờ đợi nào không góp phần tạo, bảo vệ hoặc kiểm chứng giá trị? | Giảm việc không cần thiết, lát cắt nhỏ. |
| **Xây chất lượng ngay từ đầu (Build quality in)** | Làm sao ngăn lỗi đi xa thay vì sửa hàng loạt ở cuối? | Definition of Done, TDD, CI, kiểm thử và phản hồi sớm. |
| **Tạo kiến thức (Create knowledge)** | Giả định có ảnh hưởng cao nào cần kiểm chứng? | Discovery, spike có giới hạn, review Increment, thực nghiệm. |
| **Trì hoãn cam kết hợp lý (Defer commitment)** | Quyết định khó đảo ngược nào có thể đợi tới khi có thông tin tốt hơn mà chưa mất cơ hội? | Lập kế hoạch thích ứng, thiết kế có thể thay đổi. |
| **Giao nhanh (Deliver fast)** | Làm sao rút ngắn thời gian tới phản hồi mà vẫn đạt chuẩn? | Giao tăng dần, batch nhỏ, CI/CD, Kanban flow. |
| **Tôn trọng con người (Respect people)** | Người làm việc có điều kiện, quyền chủ động và môi trường để cải tiến không? | Hợp tác, an toàn tâm lý, tự quản lý và nhịp bền vững. |
| **Tối ưu toàn hệ thống (Optimize the whole)** | Một cải tiến tại bước này có giúp toàn bộ dòng và người dùng không? | Kết nối Product Goal, backlog, flow, outcome và chất lượng. |

Các nguyên tắc trên là **khung tư duy**, không phải bảy sự kiện Scrum hoặc danh sách công việc bắt buộc cho một Sprint. Bài tập trung vào nguyên tắc cuối cùng nhưng liên hệ sáu nguyên tắc còn lại: **nếu chỉ tối ưu throughput của một khâu bằng cách bỏ chất lượng hoặc ép con người, ta đang tự phá khả năng tối ưu toàn hệ thống**.

### 3.1. “Trì hoãn cam kết” khác trì hoãn trách nhiệm

Đừng biến câu “defer commitment” thành lý do né quyết định. Khi chưa rõ API đối tác hỗ trợ retry hay không, nhóm có thể giữ hai phương án thiết kế trong một timebox ngắn rồi chọn khi có kết quả. Nhưng nếu lỗi đang gây mất dữ liệu, phải **hành động ngay theo thẩm quyền**, không chờ thêm nghiên cứu vì nguyên tắc trì hoãn.

Quyết định nhỏ, đảo ngược được có thể thử sớm; quyết định khó đảo ngược cần bằng chứng mạnh hơn. Mục đích là **giữ lựa chọn hữu ích cho đến lúc hợp lý**, không phải tối đa hóa số quyết định chưa chốt.

### 3.2. Loại bỏ lãng phí không đồng nghĩa cắt người

Những từ “lãng phí” và “hiệu suất” dễ bị hiểu thành yêu cầu giảm nhân sự hoặc theo dõi từng phút làm việc. Trong Lean software, trọng tâm nên là **giảm ma sát và công việc không cần thiết**, để con người dành thời gian cho giải quyết vấn đề, học hỏi và cải tiến.

Một người QA phát hiện sớm lỗi dữ liệu nghiêm trọng **đang tạo giá trị**, dù hoạt động ấy không thêm nút giao diện mới. Một cặp lập trình viên cùng review thiết kế **không mặc nhiên gấp đôi công sức lãng phí**; nó có thể giảm lỗi và giảm phụ thuộc về sau.

## 4. Vẽ value stream: thấy toàn bộ thời gian từ yêu cầu đến giá trị

### 4.1. Ví dụ một dòng công việc trước khi cải tiến

Giả sử một user story “cho phép đổi lịch tư vấn” đi qua các bước sau:

| Bước | Thời gian thực sự làm việc | Thời gian chờ trước/sau bước | Điều gì thường xảy ra? |
| --- | ---: | ---: | --- |
| Làm rõ yêu cầu | 2 giờ | 3 ngày | Chờ người hiểu quy tắc nghiệp vụ xác nhận. |
| Phát triển và kiểm thử đơn vị | 10 giờ | 1 ngày | Chờ Developer phù hợp rảnh tay. |
| Code review | 2 giờ | 4 ngày | Reviewer đang bận nhiều pull request khác. |
| Kiểm thử tích hợp | 4 giờ | 2 ngày | Môi trường và dữ liệu thử chưa sẵn sàng. |
| Triển khai/phát hành | 2 giờ | 3 ngày | Chờ lịch triển khai theo quy trình. |

Tổng thời gian chủ động trong bảng là **20 giờ**; tổng thời gian chờ là **13 ngày**. Nếu giả sử mỗi ngày làm việc có 8 giờ và **toàn bộ thời gian chờ ở đây đều tính theo ngày làm việc**, thì thời gian trong mô hình là:

\[
\text{Tổng thời gian}=20+13\times8=124\text{ giờ làm việc}
\]

Tỷ lệ thời gian xử lý trực tiếp:

\[
\text{Flow efficiency minh họa}=\frac{20}{124}\times100\%
\approx16{,}1\%
\]

**Đây là dữ liệu giả định**, chỉ minh họa một cách lập bản đồ. Thời gian thực tế thường có công việc song song, giao nhận nhiều lần, thời gian lịch khác giờ làm việc và khó phân biệt tuyệt đối “xử lý” với “chờ”. Không sử dụng phép tính này để chấm năng suất cá nhân. Điều đáng chú ý là **thời gian chờ lớn hơn rất nhiều so với thời gian thao tác**.

### 4.2. Nếu chỉ tăng tốc lập trình thì sao?

Giả sử nhờ công cụ mới, thời gian phát triển giảm từ **10 giờ xuống 5 giờ**, trong khi mọi thời gian chờ và khâu khác giữ nguyên.

Tổng thời gian giảm từ **124 xuống 119 giờ**, tức khoảng **4,0%**. Lập trình nhanh hơn 50% **không đồng nghĩa toàn dòng nhanh hơn 50%**. Nếu công cụ mới tạo thêm lỗi hoặc yêu cầu review phức tạp, lợi ích thậm chí có thể bị xóa bỏ.

Ngược lại, nếu nhóm phối hợp để rút **thời gian chờ review từ bốn ngày còn một ngày**, mô hình giảm **24 giờ** chờ. Thời gian toàn dòng giảm từ 124 xuống khoảng **100 giờ**, tương đương gần **19,4%** khi các điều kiện khác không đổi.

**Bài học:** Chọn cải tiến dựa trên **thời gian và rủi ro mà khách hàng thực sự chịu**, không dựa trên bộ phận nào dễ chứng minh “tốc độ tăng”.

### 4.3. Value Stream Mapping (VSM) gồm những gì?

Một buổi **vẽ bản đồ dòng giá trị** có thể làm theo trình tự:

1. Chọn **một loại hạng mục và kết quả cụ thể** (chẳng hạn user story nhỏ từ lúc được chấp nhận tới lúc phát hành).
2. Chọn một vài hạng mục đã hoàn tất gần đây để **truy vết luồng thật**, thay vì vẽ luồng lý tưởng trên giấy.
3. Đánh dấu điểm bắt đầu/kết thúc và từng bước/hàng đợi; ghi thời gian xử lý, thời gian chờ, bàn giao, tỉ lệ làm lại.
4. Xác định ai ra quyết định, nơi bị phụ thuộc, điều kiện an toàn/bảo mật bắt buộc.
5. Hỏi điểm nào làm chậm dòng hoặc tạo lỗi nhiều nhất; phân biệt hiện tượng và nguyên nhân.
6. Chọn một cải tiến giới hạn, đo lại **toàn dòng** và tín hiệu outcome/chất lượng.

~~~mermaid
flowchart LR
    A["Nhu cầu người dùng"] --> B["Làm rõ / ưu tiên"]
    B --> C["Chờ năng lực"]
    C --> D["Phát triển + kiểm thử sớm"]
    D --> E["Hàng đợi Review"]
    E --> F["Kiểm thử tích hợp"]
    F --> G["Chờ phát hành"]
    G --> H["Người dùng nhận giá trị"]
    H --> I["Phản hồi và đo kết quả"]
    I -. "Cập nhật ưu tiên" .-> B
~~~

Sơ đồ có thể có vòng lặp khi phát hiện lỗi: Review trả về phát triển, kiểm thử phát hiện bất tương thích, phản hồi sản phẩm làm đổi user story. **Vòng làm lại (rework)** phải được ghi nhận, không xóa khỏi bản đồ để tạo vẻ “dòng chảy sạch”.

### 4.4. Phân biệt flow efficiency và resource utilization

- **Flow efficiency:** Tỷ lệ thời gian một hạng mục đang được xử lý so với tổng thời gian nó nằm trong luồng, theo định nghĩa đo đã công bố.
- **Resource utilization:** Tỷ lệ năng lực của một nguồn lực (người, hệ thống, máy chủ) được sử dụng.

Một đội có thể đạt **utilization rất cao** nhưng **flow efficiency thấp**: ai cũng bận, ticket liên tục xếp hàng. Việc buộc utilization lên 100% thường làm hệ thống ít năng lực hấp thụ biến động và dễ tạo hàng đợi dài. Tuy nhiên, không thể kết luận mọi môi trường đều nên có cùng một tỷ lệ sử dụng “lý tưởng”; cần xem loại công việc, mức biến động, thời hạn và chi phí công suất dự phòng.

## 5. Bảy dạng lãng phí trong Lean software và tác hại liên hệ hệ thống

Một cách phân loại lãng phí thường dùng trong Lean software gồm: **công việc làm dở, tính năng thừa, học lại, bàn giao, chậm trễ, chuyển ngữ cảnh và lỗi**. Các danh mục giúp đặt câu hỏi; chúng không thay thế việc đánh giá **một hoạt động có thật sự cần cho giá trị hoặc chất lượng**.

| Dạng lãng phí | Biểu hiện trong phần mềm | Tác hại trên toàn hệ thống | Điều nhóm có thể thử |
| --- | --- | --- | --- |
| **Công việc dở dang (partially done work)** | Nhiều nhánh chưa tích hợp, story chờ test. | Vốn công sức bị khóa, rủi ro tích hợp và thời gian nhận giá trị tăng. | Giới hạn WIP, chia lát cắt nhỏ, ưu tiên hoàn tất. |
| **Tính năng thừa (extra features)** | Xây chức năng chưa có bằng chứng giá trị hoặc không ai dùng. | Tăng chi phí làm, kiểm thử, vận hành và bảo trì. | Discovery, đo outcome, loại bỏ hoặc hoãn ý tưởng ít giá trị. |
| **Học lại (relearning)** | Quên lý do quyết định, lỗi cũ tái diễn, tri thức nằm ở một cá nhân. | Mất thời gian điều tra lại và tăng phụ thuộc. | Ghi quyết định vừa đủ, kiểm thử, chia sẻ tri thức, pairing. |
| **Bàn giao không cần thiết (handoffs)** | Mỗi thay đổi phải qua nhiều nhóm chờ phê duyệt không rõ mục đích. | Chờ đợi, mất ngữ cảnh, tăng lỗi truyền đạt. | Đa kỹ năng, chính sách rõ, chuyển giao thông tin đủ dùng. |
| **Chờ đợi (delays)** | Chờ môi trường, quyền truy cập, reviewer hoặc phản hồi nghiệp vụ. | Lead time dài dù tổng công sức nhỏ. | Hiện rõ điểm chặn, giảm batch, cải thiện tự phục vụ khi an toàn. |
| **Chuyển ngữ cảnh (task switching)** | Mỗi người làm nhiều ticket cùng lúc, liên tục bị ngắt. | Giảm tập trung, tăng thời gian phục hồi ngữ cảnh và lỗi. | Giảm WIP, chính sách việc khẩn, bảo vệ thời gian tập trung. |
| **Lỗi (defects)** | Lỗi hồi quy, dữ liệu sai, thiếu tiêu chí chấp nhận hoặc kiểm thử. | Làm lại, hỗ trợ, mất uy tín, nguy cơ người dùng chịu thiệt hại. | TDD, CI, test sớm, review và điều tra nguyên nhân hệ thống. |

### 5.1. Không biến “lãng phí” thành lời phán xét con người

Nếu một Developer bị ngắt việc mười lần vì các yêu cầu gấp, nguyên nhân có thể nằm ở **cách quản lý công việc vào**, không phải cá nhân “thiếu tập trung”. Nếu review chờ một người có quyền phê duyệt, nguyên nhân có thể là **chính sách phân quyền**, thiếu chia sẻ kiến thức hoặc ràng buộc cần thiết.

Tư duy Lean hỏi “**hệ thống đã tạo ra điều kiện nào dẫn tới chờ/làm lại?**” trước khi đổ lỗi cho người đang làm việc trong hệ thống ấy.

### 5.2. Không xóa những bước bảo vệ chất lượng

Review bảo mật với sản phẩm xử lý dữ liệu nhạy cảm có thể là bước cần thiết. Vấn đề đáng tối ưu là **chuẩn bị hồ sơ đầy đủ, tự động hóa kiểm tra có thể tự động và giảm thời gian xếp hàng** trong khi giữ kiểm soát quan trọng. Loại bỏ review hoàn toàn để tăng chỉ số tốc độ có thể làm hỏng sản phẩm và dẫn tới chi phí lớn hơn.

Tương tự, retrospective, huấn luyện người mới và chia sẻ tri thức có thể không tạo một feature ngay lập tức, nhưng giúp hệ thống **tránh lỗi lặp, giảm phụ thuộc và duy trì năng lực dài hạn**.

## 6. Nút thắt: nơi cải tiến cục bộ có khả năng ảnh hưởng toàn dòng nhất

Một **nút thắt (bottleneck)** là bước hoặc nguồn lực đang hạn chế lưu lượng công việc của hệ thống theo điều kiện hiện tại. Khái niệm này gần với tư duy **Theory of Constraints (TOC)**: tìm giới hạn hệ thống, tổ chức các hoạt động khác theo giới hạn ấy, cải thiện nó và tiếp tục kiểm tra vì giới hạn có thể dịch chuyển.

### 6.1. Ví dụ throughput ba khâu

Giả sử một luồng đơn giản có ba bước với **năng lực xử lý minh họa**:

| Bước | Năng lực nếu được cung cấp đủ việc |
| --- | ---: |
| Phát triển | 10 hạng mục/tuần |
| Review + kiểm thử | 4 hạng mục/tuần |
| Phát hành | 8 hạng mục/tuần |

Trong mô hình đơn giản, luồng không thể bền vững hoàn tất vượt năng lực khâu **Review + kiểm thử: 4 mục/tuần**, nếu mỗi hạng mục phải đi qua cả ba bước và không có thay đổi về loại việc.

Nếu phát triển tăng từ **10 lên 15 mục/tuần**, toàn hệ thống vẫn chỉ giao được khoảng **4 mục/tuần** trong điều kiện đó. Việc còn lại tích ở hàng đợi Review; **đầu ra bộ phận tăng, đầu ra hệ thống không tăng**.

### 6.2. Tác động của việc đẩy nhiều việc qua nút thắt

Giả sử nhóm **bắt đầu 7 mục/tuần** và chỉ **hoàn tất 4 mục/tuần**. Nếu điều kiện không đổi, tồn đọng trong hệ thống tăng ròng khoảng:

\[
7-4=3\ \text{mục mỗi tuần}
\]

Sau bốn tuần, tồn đọng có thể tăng **12 mục** so với ban đầu trong mô hình không có hủy/chuyển luồng. Cùng với WIP tăng, tuổi hạng mục và sự bất định thời gian hoàn tất thường trở thành vấn đề. Đây là giả định đơn giản để nhìn động học, không phải dự báo chính xác cho hệ thống có công việc biến động.

**Không giải quyết bằng cách:** yêu cầu bước phát triển nhận thêm việc hoặc thúc giục Reviewer “cố lên” mà không điều chỉnh hệ thống.

**Có thể cải tiến bằng cách:**

1. Không để khâu trước tiếp tục đẩy lượng việc vượt khả năng hoàn tất.
2. Ưu tiên giúp các mục đang ở/đợi nút thắt đi qua với đủ chất lượng.
3. Chia hạng mục nhỏ hơn, chuẩn bị điều kiện review và test rõ.
4. Thử tăng khả năng tại nút thắt theo cách an toàn: pairing, tự động kiểm tra, chia sẻ kỹ năng hoặc giảm bàn giao.
5. Đo **throughput toàn dòng, WIP, cycle time, lỗi** sau cải tiến.

### 6.3. Cải tiến nút thắt làm giới hạn chuyển nơi khác

Giả sử sau khi tự động kiểm thử và chia sẻ review, năng lực khâu Review + kiểm thử tăng từ **4 lên 6 hạng mục/tuần**, còn phát hành vẫn có năng lực 8. Nếu lượng việc phù hợp, throughput lý thuyết của dòng có thể tăng tới khoảng **6 mục/tuần**. Lúc này cần xem nút thắt khác có xuất hiện, ví dụ môi trường tích hợp, phát hành hoặc hoạt động xác định giá trị.

Đầu tư để mọi khâu đều đạt 15 mục/tuần ngay lập tức có thể không cần thiết. Tư duy toàn hệ thống giúp chọn **bước cải tiến tiếp theo có lợi ích thực** thay vì mở chương trình tối ưu đồng loạt thiếu trọng tâm.

### 6.4. Không nhầm nút thắt ổn định với biến động tạm thời

Một tuần Reviewer nghỉ phép làm hàng đợi tăng không nhất thiết là giới hạn dài hạn của workflow. Một quyết định chuyển người sang review chỉ vì dữ liệu một tuần có thể làm phát triển thiếu năng lực ở tuần tiếp theo.

Để xác định nút thắt cần xem:

- Xu hướng qua nhiều tuần và phân bố theo loại hạng mục.
- WIP tại từng bước, work item age, tỷ lệ bị chặn.
- Năng lực danh nghĩa so với khả năng thực, gồm nghỉ, lỗi và yêu cầu khẩn.
- Những phụ thuộc hoặc quy định làm công việc phải chờ.
- Tác động của cải tiến thử lên **toàn luồng**, không chỉ thời gian một khâu.

**Nút thắt có thể thay đổi theo thời gian**; cải tiến nên mang tính thực nghiệm và được đánh giá lại.

## 7. Utilization cao, hàng đợi dài và chi phí của đa nhiệm

Khi một bước làm việc luôn kín 100%, chỉ cần một yêu cầu đến không đều, một ca kiểm thử khó hơn dự kiến hoặc một sự cố ngắn cũng có thể tạo hàng đợi. Với công việc tri thức có biến động, **dự phòng năng lực hợp lý** giúp hệ thống phản ứng và hoàn tất việc nhanh hơn.

### 7.1. Một ví dụ về điểm nghẽn do công suất

Giả sử một người Reviewer có thể xử lý khoảng năm hạng mục mỗi tuần trong điều kiện bình thường:

- Nếu trung bình chỉ có ba mục/tuần đến Review, thường có khoảng trống để hấp thụ biến động.
- Nếu trung bình đến gần năm mục/tuần, một tuần có bảy mục hoặc người Reviewer bận sự cố có thể tạo tồn đọng kéo dài.
- Nếu trung bình hơn năm mục/tuần trong thời gian dài, tồn đọng sẽ tăng nếu không đổi cấu trúc luồng.

Đây không phải một công thức rằng “mọi nguồn lực luôn cần utilization 70%”. Điều cần hiểu là **mức biến động, tính cấp bách, khả năng chuyển giao và hậu quả nếu phải chờ**. Dự phòng có thể là thời gian để review, khắc phục sự cố, học kỹ năng mới và kiểm soát rủi ro, không nhất thiết là thời gian nhàn rỗi vô ích.

### 7.2. Tối ưu mức bận rộn có thể gây nghịch lý

Quản lý thấy người kiểm thử đôi lúc chờ việc, liền giao họ thêm nhiệm vụ khác ở đội khác để “không lãng phí”. Sau đó, khi feature quan trọng hoàn tất, người kiểm thử phải đợi xong việc đội kia. Lead time của sản phẩm tăng dù utilization của người kiểm thử tốt lên.

**Câu hỏi đúng hơn:** Khi giao thêm việc, ảnh hưởng tới thời gian hoàn tất, chất lượng, khả năng phản ứng với sự cố và giá trị sản phẩm là gì?

### 7.3. Chuyển ngữ cảnh là chi phí ẩn của WIP

Nếu một Developer đang xử lý ba yêu cầu từ ba khu vực hệ thống:

- Mỗi lần quay lại cần đọc trạng thái cũ và tái dựng hiểu biết.
- Một thay đổi có thể bị treo ở nhánh riêng lâu hơn, tăng xung đột merge.
- Tìm nguyên nhân lỗi và review mất nhiều ngữ cảnh.
- Phản hồi từ user story trước có thể tới khi người làm đã chuyển sang việc khác.

Không phải mọi công việc song song đều xấu, nhưng **đa nhiệm không chủ đích** dễ làm hạng mục hoàn tất chậm. Giảm WIP, chia lát cắt nhỏ, dùng chính sách pull và ưu tiên giúp việc gần Done là các thử nghiệm phổ biến.

## 8. Little’s Law: nhìn mối quan hệ giữa WIP, throughput và thời gian

Với một hệ thống dòng đủ ổn định và ranh giới đo nhất quán, **định luật Little** mô tả mối quan hệ giữa lượng việc trung bình trong hệ thống, tốc độ hoàn tất trung bình và thời gian trung bình một hạng mục ở trong hệ thống:

\[
\text{WIP trung bình}
=\text{Throughput trung bình}\times\text{Thời gian trung bình trong hệ thống}
\]

Suy ra:

\[
\text{Thời gian trung bình}
\approx\frac{\text{WIP trung bình}}{\text{Throughput trung bình}}
\]

Nếu một workflow có **WIP trung bình 12 mục** và **throughput trung bình 4 mục/tuần**, mô hình cho **thời gian trung bình xấp xỉ 3 tuần/mục**. Khi nhóm giảm WIP xuống **8 mục** và vẫn duy trì throughput 4 mục/tuần trong điều kiện tương tự, mô hình cho **xấp xỉ 2 tuần/mục**.

Điều này giúp giải thích vì sao **giảm công việc đang làm** có thể cải thiện thời gian đến giá trị, dù nhóm không tăng số giờ làm thêm.

### 8.1. Điều kiện và giới hạn khi dùng Little’s Law

- Các đại lượng phải cùng **ranh giới hệ thống**: WIP của cùng workflow với throughput và cycle time đang xét.
- Lưu lượng vào/ra và tồn đọng không được tăng hoặc giảm mãi không kiểm soát trong khoảng phân tích.
- Cần đủ dữ liệu và định nghĩa nhất quán; hạng mục có thể khác nhau về kích thước và rủi ro.
- Đây là quan hệ **trung bình**, không phải dự báo chắc chắn cho từng ticket.
- Không thể giảm WIP bằng cách xóa việc khỏi hệ thống đo rồi tuyên bố cycle time tốt lên.

Nếu backlog mới liên tục tăng và đội đang có sự cố kéo dài, áp dụng phép tính như một công thức cam kết có thể sai lệch đáng kể. Muốn dự báo, phải xem **phân bố cycle time, work item age, các mức ưu tiên, năng lực và phụ thuộc**.

### 8.2. Phân biệt hai mục tiêu dễ nhầm

**Giảm cycle time** là mục tiêu về thời gian hạng mục di chuyển qua workflow. **Tăng throughput** là mục tiêu về lượng hạng mục hoàn tất. Hai chỉ số liên quan nhưng không phải một; đôi khi một biện pháp giảm WIP có thể cải thiện cycle time trước khi throughput đổi rõ. Mục tiêu cao hơn vẫn là **người dùng nhận giá trị và hệ thống vận hành đáng tin cậy**.

### 8.3. Bốn flow metrics cần xem cùng nhau

| Chỉ số | Định nghĩa thực hành | Cách hỗ trợ tối ưu toàn hệ thống |
| --- | --- | --- |
| **WIP** | Số mục đã bắt đầu nhưng chưa hoàn tất. | Nhận biết lượng việc bị giữ trong dòng và quá tải. |
| **Throughput** | Số mục hoàn tất mỗi đơn vị thời gian. | Nhìn khả năng giao, lưu ý loại và kích thước hạng mục. |
| **Cycle time** | Thời gian từ start tới finish cho các mục đã hoàn tất. | Phân tích tốc độ dòng và phân bố chờ đợi. |
| **Work item age** | Thời gian từ start đến hiện tại cho mục chưa hoàn tất. | Phát hiện việc có nguy cơ chậm trước khi trở thành số liệu lịch sử. |

**Lead time** có thể tính từ khi yêu cầu được ghi nhận/tiếp nhận tới khi giao, rộng hơn cycle time nếu điểm bắt đầu của workflow là lúc Developers bắt đầu thực hiện. Cần công khai cách định nghĩa tại từng nhóm.

## 9. Một cải tiến có lợi cho bộ phận nhưng gây hại toàn dòng trông như thế nào?

| “Thành công” cục bộ | Tác động tiêu cực có thể xuất hiện | Cần đo bổ sung |
| --- | --- | --- |
| Developers tăng số pull request tạo mỗi ngày. | Review/test quá tải, nhiều nhánh lâu merge. | WIP, tuổi PR, lead time tới release, lỗi. |
| QA tăng số test case chạy bằng cách bỏ kiểm tra kết quả khó. | Lỗi nghiêm trọng lọt production, tăng làm lại. | Lỗi thoát, chi phí ứng cứu, khả năng hoàn tất tác vụ. |
| Đội vận hành giảm số lần deploy để “giảm rủi ro”. | Mỗi đợt phát hành lớn, phản hồi chậm, rollback khó. | Kích thước batch, tỷ lệ lỗi thay đổi, thời gian phục hồi. |
| Product Owner tăng số story bắt đầu để chiều mọi stakeholder. | WIP tăng, Sprint Goal mất tập trung. | Outcome, cycle time, số hạng mục chưa Done. |
| Nhóm kỹ thuật giải quyết mọi “nợ” bằng cách viết lại toàn bộ. | Trì hoãn tính năng có giá trị, tăng rủi ro chuyển đổi. | Giá trị mở khóa, chi phí thay đổi, khả năng rollback. |
| Bộ phận hỗ trợ đóng ticket thật nhanh. | Khách phải mở lại cùng vấn đề hoặc liên hệ nhiều lần. | Tỷ lệ giải quyết dứt điểm, số yêu cầu mở lại, trải nghiệm khách. |
| Quản lý ép utilization của tất cả thành viên gần 100%. | Khó xử lý sự cố, hàng đợi tăng, căng thẳng và lỗi. | WIP, biến động cycle time, sự cố, nhịp bền vững. |

### 9.1. “Đóng ticket nhanh” chưa phải “giải quyết vấn đề”

Ví dụ một lỗi thanh toán được đánh dấu Done vì lập trình viên đã merge patch. Nhưng kiểm thử hồi quy thất bại, phần mềm chưa phát hành, và khách vẫn bị tính phí trùng. Số ticket đóng có thể tăng trong khi **giá trị bằng không hoặc âm**. Nhóm cần thống nhất định nghĩa hoàn tất và theo dõi kết quả sau phát hành.

### 9.2. Chuyển lãng phí sang nhóm khác không phải loại bỏ lãng phí

Để làm cột Development “nhẹ”, nhóm có thể yêu cầu QA chuẩn bị toàn bộ dữ liệu và điều tra cả lỗi môi trường; QA trở thành nút thắt, thời gian toàn dòng không giảm. Hoặc để giảm thời gian xử lý ở hỗ trợ, tổ chức yêu cầu khách điền nhiều biểu mẫu khó hiểu và đẩy chi phí sang khách hàng. **Tối ưu toàn hệ thống phải tính cả những người chịu chi phí ngoài nhóm**.

### 9.3. Cần chú ý những hệ quả có độ trễ

Một quyết định cắt kiểm thử có thể tăng throughput trong một tuần, nhưng hai tháng sau tạo lỗi tái diễn và chi phí ứng cứu. Để không bị đánh lừa bởi số liệu ngắn hạn, phải đo:

- Lỗi phát sinh sau phát hành, sự cố và khả năng khôi phục.
- Tỷ lệ người dùng hoàn tất tác vụ và cần hỗ trợ.
- Thời gian thay đổi các khu vực mã sau khi “tối ưu”.
- Tốc độ triển khai của các vòng tiếp theo, không chỉ vòng hiện tại.

**Lean coi chất lượng và khả năng học tiếp là một phần của giá trị**, không phải chi phí bên lề có thể dời vô hạn.

## 10. Chọn mục tiêu toàn hệ thống trước khi chọn giải pháp cục bộ

Một cuộc cải tiến có thể thất bại ngay từ đầu nếu nhóm chỉ viết mục tiêu “giảm thời gian review 30%” mà không biết **vì sao cần giảm** và **điều gì không được làm xấu đi**.

### 10.1. Mẫu mục tiêu có ba lớp

Hãy diễn đạt mục tiêu theo ba lớp:

1. **Outcome người dùng/tổ chức:** Khách hoàn tất việc gì nhanh và đáng tin hơn?
2. **Flow từ đầu tới cuối:** Bao lâu để đưa một thay đổi có ích từ ý tưởng tới khi được sử dụng?
3. **Điều kiện bảo vệ:** Chất lượng, bảo mật, tính bền vững, chi phí hoặc nghĩa vụ nào không được suy giảm?

**Ví dụ cho hệ thống đặt lịch:**

> “Trong các vòng thử cải tiến tiếp theo, rút ngắn thời gian từ lúc một nhu cầu đặt lịch đã được chấp nhận đến khi khách dùng được, ưu tiên các thay đổi giúp tỷ lệ đặt lịch thành công tăng; đồng thời không tăng lỗi tạo lịch trùng, sự cố bảo mật hoặc thời gian khôi phục.”

Mục tiêu này định hướng hành động hơn câu “đội backend phải hoàn tất nhiều API hơn”, vì nó mô tả **khách hàng nhận gì**, **đường giao giá trị** và **giới hạn an toàn**.

### 10.2. Cây câu hỏi trước một đề xuất cải tiến

~~~mermaid
flowchart TD
    A["Có đề xuất làm một bước nhanh hơn"] --> B["Bước này liên quan kết quả người dùng nào?"]
    B --> C["Dòng end-to-end đang bị hạn chế ở đâu?"]
    C --> D{"Đây có phải nút thắt có tác động lớn?"}
    D -->|Không rõ| E["Quan sát WIP, chờ đợi, tuổi việc, lỗi"]
    D -->|Có| F["Thiết kế thử nghiệm nhỏ"]
    E --> D
    F --> G["Đo toàn dòng + outcome + guardrails"]
    G --> H{"Có cải thiện thực và an toàn?"}
    H -->|Có| I["Duy trì, xem nút thắt tiếp theo"]
    H -->|Không / chưa rõ| J["Điều chỉnh hoặc dừng thử nghiệm"]
~~~

Quy trình không buộc phải chờ nhiều tuần mới sửa được một lỗi hiển nhiên. Với vấn đề an toàn hoặc sự cố đang ảnh hưởng người dùng, **ưu tiên giảm thiệt hại và xử lý theo thẩm quyền**; việc đo và phân tích cải tiến diễn ra trong và sau ứng cứu.

### 10.3. Thiết kế thước đo cân bằng

| Loại tín hiệu | Ví dụ | Dùng để tránh điều gì? |
| --- | --- | --- |
| **Outcome** | Tỷ lệ đặt lịch thành công, số cuộc gọi hỗ trợ, kết quả người dùng. | Giao nhanh nhiều tính năng không ai cần. |
| **Flow** | Lead time tới người dùng, cycle time, WIP, throughput, thời gian chờ. | Tối ưu một bước nhưng tăng hàng đợi ở bước khác. |
| **Chất lượng** | Lỗi hồi quy, giao dịch trùng, sự cố, thời gian khôi phục. | Giao nhanh bằng cách giảm kiểm thử hoặc kiểm soát rủi ro. |
| **Học hỏi** | Thời gian từ giả định tới bằng chứng và quyết định, tỷ lệ giả thuyết bị bác bỏ hữu ích. | Xây sản phẩm hoàn chỉnh rồi mới hỏi người dùng có cần không. |
| **Khả năng bền vững** | Việc khẩn chiếm dụng năng lực, giờ trực quá tải, năng lực chia sẻ kiến thức. | Đạt mục tiêu một vòng bằng kiệt sức và nợ kỹ thuật dài hạn. |

Không nhất thiết có dashboard lớn cho tất cả bảng. Chọn **một vài tín hiệu liên quan quyết định**, có định nghĩa dễ hiểu và thay đổi khi vấn đề của hệ thống dịch chuyển.

## 11. Goodhart và nguy cơ biến số đo thành mục tiêu

Một nguyên lý thường được nhắc tới trong quản lý đo lường là: **khi một thước đo bị dùng như mục tiêu tối thượng, nó có thể mất khả năng phản ánh điều ta muốn đo**. Với phát triển phần mềm, hiện tượng này dễ xuất hiện khi số ticket, số story point, số pull request hay độ bận rộn cá nhân quyết định khen thưởng.

### 11.1. Một số phản ứng ngoài ý muốn

| Chỉ số được tối đa hóa | Hành vi có thể bị khuyến khích | Tác hại với toàn hệ thống |
| --- | --- | --- |
| **Số story point/tuần** | Nâng điểm ước lượng hoặc chia ticket hình thức. | Số liệu đẹp nhưng người dùng chưa nhận nhiều giá trị hơn. |
| **Số bug đóng** | Chọn lỗi dễ, đóng khi chưa kiểm chứng, tránh lỗi khó. | Lỗi nghiêm trọng tồn tại và khách phải báo lại. |
| **Số PR merge** | Tạo PR nhỏ thiếu kết nối hoặc đẩy review quá nhanh. | Gánh nặng tích hợp, lỗi hồi quy và thời gian tới release tăng. |
| **Tỷ lệ sử dụng nhân sự** | Nhận thêm việc để không ai có khoảng trống. | WIP và thời gian chờ tăng, không còn năng lực phản ứng. |
| **Cycle time trung bình** | Giấu mục khó, chuyển start muộn, đóng Done sớm. | Dự báo sai, hạng mục thực sự chậm bị bỏ quên. |
| **Số lần deploy** | Triển khai thay đổi không tạo ích lợi hoặc bỏ chất lượng. | Giao nhiều nhưng outcome và độ tin cậy không tăng. |
| **Số tính năng được giao** | Ưu tiên feature hơn sửa lỗi, khám phá hoặc đầu tư giảm nợ. | Chất lượng và khả năng đổi hướng giảm về sau. |

Không phải các chỉ số trên đều vô dụng. Chúng có thể hữu ích khi được dùng **để học và hỗ trợ quyết định**, không để thưởng phạt một chiều.

### 11.2. Cách giảm tác hại khi đo lường

1. **Định nghĩa ranh giới đo rõ:** Khi nào hạng mục bắt đầu, kết thúc, chuyển trạng thái, bị hủy?
2. **Kết hợp đối trọng:** Đo tốc độ cùng chất lượng và outcome; đo throughput cùng WIP và tuổi việc.
3. **Xem phân bố và ngoại lệ:** Đừng chỉ xem trung bình của những mục đã hoàn tất; nhìn cả mục đang già.
4. **Ghi thay đổi về loại công việc:** Một tháng xử lý sự cố phức tạp không tương đương tháng toàn lỗi giao diện nhỏ.
5. **Không so năng suất cá nhân bằng chỉ số flow nhóm:** Các chỉ số mô tả hệ thống và phụ thuộc.
6. **Khuyến khích báo cáo trung thực:** Nếu giảm số sự cố được báo bằng cách giấu chúng, đó không phải cải tiến.

### 11.3. Phân biệt “tốc độ thực hiện”, “tốc độ học” và “tốc độ giao giá trị”

Một nhóm có thể:

- **Viết code nhanh**, nhưng học chậm vì không tương tác với người dùng.
- **Thử nghiệm rất nhiều**, nhưng không ra quyết định hoặc không giao giải pháp hữu ích.
- **Phát hành thường xuyên**, nhưng không biết kết quả nào đã cải thiện.

Tối ưu toàn hệ thống là thiết kế sao cho **mỗi vòng làm nhỏ tạo được một kết quả sử dụng được hoặc bằng chứng làm quyết định tiếp theo tốt hơn**. Công việc khám phá có timebox không nhất thiết tạo Increment đã phát hành, nhưng phải dẫn tới quyết định; Increment phải đạt chuẩn chất lượng chứ không chỉ có báo cáo thử nghiệm.

## 12. Ví dụ xuyên suốt: nhóm đặt lịch tối ưu sai chỗ

Giả sử một nhóm sản phẩm có Product Owner, Developers, QA, người phụ trách phát hành và chuyên gia tích hợp. Mục tiêu là **khách đặt và đổi lịch tư vấn tin cậy, không phải gọi tổng đài cho những thao tác cơ bản**.

### 12.1. Cách quản lý cũ: từng bộ phận có chỉ tiêu riêng

Nhóm ban đầu có các mục tiêu:

- Developers phải tăng số story hoàn tất mã lên 25%.
- QA phải tối đa hóa số test case chạy mỗi ngày.
- Vận hành phải giảm số lần thay đổi production để “tránh rủi ro”.
- Product Owner phải bảo đảm tất cả stakeholder có yêu cầu được đưa vào Sprint.

Từng mục tiêu có thể nghe hợp lý nếu tách riêng. Nhưng khi ghép lại:

1. Developers mở nhiều story hơn; mã nằm chờ review và test.
2. QA bị dồn việc vào cuối kỳ, ưu tiên kiểm thử số lượng lớn nhưng ít thời gian phân tích trường hợp rủi ro.
3. Đợt deploy lớn làm lỗi khó cô lập; khách nhận giá trị chậm.
4. Product Backlog phình to, mục tiêu bị phân tán và nhiều tính năng ít dùng.

**Kết quả cục bộ:** Một số chỉ số báo cáo đẹp.

**Kết quả toàn hệ thống:** Thời gian tới giá trị kéo dài, công việc làm lại tăng và phản hồi người dùng tới quá muộn.

### 12.2. Nhóm chọn một dòng giá trị cần cải thiện

Thay vì “sửa toàn bộ quy trình công ty”, nhóm chọn dòng:

> “Thay đổi nhỏ liên quan chức năng đặt lịch, tính từ lúc hạng mục được ưu tiên chấp nhận tới lúc khách dùng được và hệ thống ổn định.”

Họ quan sát các hạng mục đã hoàn tất và ghi nhận dữ liệu **minh họa**:

| Khâu | Thời gian xử lý điển hình | Thời gian chờ điển hình | Khó khăn |
| --- | ---: | ---: | --- |
| Làm rõ nghiệp vụ | 3 giờ | 2 ngày | Cần nhiều bên xác nhận quy tắc. |
| Phát triển | 12 giờ | 1 ngày | Mỗi Developer đang làm nhiều mục. |
| Review | 2 giờ | 4 ngày | Thiếu khả năng review phần tích hợp. |
| Kiểm thử tích hợp | 5 giờ | 3 ngày | Môi trường thiếu dữ liệu ổn định. |
| Phát hành | 2 giờ | 4 ngày | Gom thay đổi thành một batch lớn. |

Nhóm không kết luận ngay “QA làm chậm”. Họ nhìn thấy **nhiều hàng đợi nối tiếp**, đặc biệt chờ Review, chờ môi trường và lịch phát hành. Họ cũng biết **cần kiểm tra nhu cầu** trước khi thêm tính năng ít dùng.

### 12.3. Thay đổi đầu tiên: kiểm soát lượng việc vào

Nhóm đặt chính sách:

- Không kéo thêm user story tiêu chuẩn khi WIP toàn luồng đã chạm giới hạn thử nghiệm.
- Ưu tiên hỗ trợ review hoặc test những mục gần Done.
- Không chèn một yêu cầu mới vào luồng mà không xác định **việc nào phải chờ**.
- Hạng mục bị chặn vẫn hiển thị tuổi và nguyên nhân.
- Lỗi nghiêm trọng được xử lý theo chính sách ứng cứu, không bị giữ ở hàng đợi tiêu chuẩn.

Đây là một lựa chọn **thay cách phối hợp toàn dòng**, không chỉ yêu cầu một người “làm nhanh hơn”.

### 12.4. Thay đổi thứ hai: giảm lãng phí từ thiết kế và kiểm thử

Developers và QA phối hợp:

1. Làm rõ tiêu chí chấp nhận ở đầu lát cắt.
2. Viết kiểm thử tích hợp cho trường hợp cạnh tranh đồng thời và timeout.
3. Dùng CI để chạy kiểm thử tự động sớm thay vì đợi cuối Sprint.
4. Dùng pair programming khi một khu vực mã chỉ có một người hiểu rõ.
5. Cải tiến dữ liệu/môi trường thử để không chờ cấu hình thủ công mỗi lần.

Những thay đổi này có thể làm **thời gian xử lý một PR ban đầu dài hơn** nếu nhìn riêng lẻ, nhưng lại giảm thời gian làm lại và lỗi ở các bước sau. Tối ưu toàn hệ thống cho phép một bước mất thêm công sức **khi tổng chi phí giảm và chất lượng tốt hơn**.

### 12.5. Thay đổi thứ ba: giao lát cắt nhỏ và nhận phản hồi sớm

Thay vì gom “đặt lịch, đổi lịch, email, SMS, bộ lọc” thành một phát hành lớn, nhóm chọn:

- Lần đầu: khách xem giờ trống, đặt một lịch hợp lệ và nhận xác nhận.
- Lần sau: khách hiểu rõ trạng thái khi mạng chậm và có cơ chế retry an toàn.
- Lần tiếp: tự đổi lịch cơ bản khi kết quả khảo sát API đã đủ.
- SMS và bộ lọc nâng cao: chỉ đưa lên ưu tiên khi có bằng chứng giá trị thích hợp.

Đối với sản phẩm có hạn chế pháp lý hoặc vận hành, **phát hành nhỏ** vẫn phải tuân thủ chính sách; không đồng nghĩa tự ý bỏ kiểm soát bảo mật hoặc thay đổi cơ sở dữ liệu rủi ro cao.

### 12.6. Đánh giá kết quả bằng bộ chỉ số cân bằng

Giả sử trong các kỳ tương đương, nhóm quan sát **số liệu hoàn toàn giả định**:

| Tín hiệu | Trước cải tiến | Sau cải tiến |
| --- | ---: | ---: |
| WIP trung bình của dòng | 14 mục | 8 mục |
| Throughput trung bình | 4 mục/tuần | 5 mục/tuần |
| Cycle time trung vị | 15 ngày | 9 ngày |
| Thời gian chờ review trung vị | 4 ngày | 1,5 ngày |
| Lỗi hồi quy nghiêm trọng sau phát hành | 3 | 1 |
| Tỷ lệ khách hoàn tất đặt lịch hợp lệ | 48% | 55% |

Những số liệu trên **không chứng minh nhân quả**. Chúng gợi ý nhóm nên tiếp tục quan sát, xem đặc điểm người dùng, kích thước hạng mục và số việc đang mở. Một phần kết quả có thể do thay đổi nguồn nhu cầu, cơ cấu nhân sự hoặc đặc điểm sản phẩm. Nhưng việc **xem cùng lúc flow, chất lượng và outcome** đáng tin hơn chỉ nhìn số PR đã merge.

### 12.7. Kết luận của tình huống

Điểm mạnh nhất của cải tiến không phải một con số tăng, mà là **cách nhóm ra quyết định**:

- Đo từ nhu cầu tới giá trị, không chỉ công việc ở bước Development.
- Dành năng lực giúp **hoàn tất** thay vì luôn **bắt đầu**.
- Bảo vệ chất lượng và trải nghiệm người dùng.
- Làm rõ giả định trước khi đầu tư feature lớn.
- Chọn thử nghiệm nhỏ rồi xem lại dựa trên bằng chứng.

Nếu sau đó điểm nghẽn chuyển từ Review sang phê duyệt phát hành, nhóm phải cập nhật nơi tập trung cải tiến. **Tối ưu toàn hệ thống là quá trình tiếp diễn**, không phải dự án làm một lần rồi tuyên bố hoàn tất.

## 13. Tối ưu toàn hệ thống ở ranh giới nhiều đội và nhiều sản phẩm

Một rủi ro quan trọng là nhóm đã tối ưu toàn workflow **của mình** nhưng chưa nhìn **toàn chuỗi dịch vụ**.

### 13.1. Đội nền tảng và đội sản phẩm dùng chung

Giả sử ba nhóm sản phẩm sử dụng một đội platform phụ trách quyền truy cập và triển khai. Nếu mỗi nhóm sản phẩm tăng tốc đưa yêu cầu tới platform, hàng đợi platform có thể quá tải.

**Tối ưu cục bộ:** Từng nhóm đo số yêu cầu gửi sang platform và tuyên bố “đã giao xong phần mình”.

**Tối ưu toàn hệ thống:** Các nhóm và platform thống nhất cách ưu tiên chung, khả năng tự phục vụ an toàn, tiêu chuẩn giao diện, năng lực và mức dịch vụ. Khi phù hợp, đầu tư tự động hóa một thao tác lặp lại có thể đem lại lợi ích lớn hơn việc tăng tốc riêng một feature.

### 13.2. Chuyển chi phí sang khách hàng cũng là tối ưu cục bộ

Một ứng dụng muốn giảm tải hỗ trợ nên yêu cầu khách tự điền nhiều thông tin phức tạp. Số cuộc gọi giảm, nhưng tỷ lệ bỏ dở và thời gian khách hoàn tất tác vụ tăng. Nếu tổ chức chỉ đo chi phí hỗ trợ, nó có thể nghĩ đã thành công.

Một mục tiêu toàn hệ thống hơn là:

> “Khách giải quyết được vấn đề với tổng công sức thấp, chính xác và an toàn; tổ chức có chi phí phục vụ bền vững.”

Điều này khuyến khích xem **customer effort, tỷ lệ giải quyết dứt điểm, khiếu nại và tác động sản phẩm**, không chỉ cắt chi phí ở một bộ phận.

### 13.3. Tối ưu theo thời điểm khác nhau

Một quyết định có thể tạo lợi ích ngay và chi phí về sau:

| Quyết định | Lợi ích ngắn hạn | Rủi ro dài hạn cần xem |
| --- | --- | --- |
| Bỏ kiểm thử tự động để kịp demo | Code hoàn tất nhanh hơn. | Lỗi hồi quy, giảm khả năng phát hành thường xuyên. |
| Dùng API tạm thời không có hợp đồng rõ | Prototype sớm. | Khó tích hợp, lỗi khi đối tác đổi hành vi. |
| Để một người duyệt mọi thay đổi | Tính nhất quán trong ngắn hạn. | Nút thắt, thiếu dự phòng khi người đó vắng. |
| Viết lại toàn bộ hệ thống để “giảm nợ” | Cơ hội có kiến trúc mới. | Dời giá trị, rủi ro chuyển đổi, làm lại kiến thức nghiệp vụ. |
| Dành năng lực đào tạo và pair programming | Mất một phần thời gian lập trình trực tiếp. | Có thể giảm phụ thuộc và tăng khả năng thay đổi về sau. |

Đánh giá **tổng chi phí sở hữu, chất lượng và năng lực phản ứng trong nhiều vòng**, không chỉ tốc độ của tuần hiện tại.

## 14. Kết hợp Lean với Scrum, Kanban và XP

Tư duy tối ưu toàn hệ thống có thể được dùng cùng các thực hành Agile phổ biến. Mỗi cách tiếp cận đóng góp một phần:

| Nhu cầu tối ưu | Scrum có thể hỗ trợ | Kanban có thể hỗ trợ | XP có thể hỗ trợ |
| --- | --- | --- | --- |
| Chọn đúng giá trị và tập trung | Product Goal, Sprint Goal, Product Backlog có thứ tự, Review. | Chính sách bổ sung công việc theo giá trị, quan sát thời gian tới Done. | Chia phần nhỏ và nhận phản hồi kỹ thuật sớm. |
| Giảm WIP và thời gian chờ | Sprint Backlog minh bạch; Developers thích ứng kế hoạch. | Trực quan hóa, pull, giới hạn WIP, quản lý blocked. | Tích hợp thường xuyên, giảm nhánh dài. |
| Giữ chất lượng khi giao nhanh | Increment và Definition of Done. | Chính sách chuyển trạng thái, chỉ số lỗi và flow. | TDD, CI, refactoring, pair programming. |
| Giảm bất định | Refinement, Sprint Review, kiểm tra kết quả. | Timebox discovery trong workflow khi phù hợp. | Spike kỹ thuật và thử nghiệm nhỏ. |
| Học từ hệ thống | Sprint Retrospective và điều chỉnh cách làm. | Các vòng phản hồi, flow metrics, cải tiến workflow. | Phản hồi ở cấp mã và tích hợp. |

### 14.1. Scrum: tối ưu theo Sprint Goal và Increment

Trong Scrum, **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog; **Developers** tạo kế hoạch Sprint, giữ chất lượng và tạo Increment; **Scrum Master** giúp nhóm và tổ chức áp dụng Scrum hiệu quả.

**Tối ưu cục bộ dễ gặp:** Từng Developer tối đa hóa story point của mình. Sprint cuối cùng có nhiều mã viết xong nhưng chưa tích hợp, mục tiêu chưa được đáp ứng.

**Cách nhìn toàn hệ thống:** Developers cùng giúp hoàn tất Increment đạt Definition of Done, tập trung vào Sprint Goal, kiểm tra phản hồi trong Sprint Review và cải tiến điểm chờ trong Retrospective. Khi một story gặp rủi ro, nhóm có thể làm rõ và thương lượng phạm vi với Product Owner mà không làm giảm chất lượng.

Scrum Guide không yêu cầu tối đa hóa số story trong Sprint. **Sprint Goal không đồng nghĩa danh sách tất cả Product Backlog Item đã chọn**.

### 14.2. Kanban: nhìn hệ thống qua workflow và WIP

Kanban làm rõ **hạng mục đi qua những bước nào**, điểm nào bị chặn, hạng mục đang già ra sao và dòng có ổn định không. Các khái niệm hữu ích:

- **Definition of Workflow:** loại công việc, ranh giới bắt đầu/kết thúc, các trạng thái, chính sách rõ.
- **WIP limit và pull:** cân bằng lượng công việc đang làm với khả năng hoàn tất.
- **Throughput, cycle time, WIP, work item age:** nhìn flow của việc đã hoàn tất và chưa hoàn tất.
- **Service Level Expectation (SLE):** kỳ vọng có cơ sở về thời gian hoàn tất cho loại việc phù hợp, không phải lời hứa chắc chắn.
- **Cải tiến workflow:** dùng quan sát và thử nghiệm nhỏ để xem thay đổi có thực sự giảm thời gian tới giá trị.

Một Scrum Team có thể dùng các thực hành Kanban mà **không bỏ các trách nhiệm, sự kiện, artifact và commitment của Scrum**. Một đội Kanban không dùng Sprint vẫn có thể thực hành Lean tốt nếu quyết định ưu tiên, chất lượng và vòng phản hồi rõ.

### 14.3. XP: giảm chi phí thay đổi và làm lại

Các thực hành Extreme Programming giúp chất lượng kỹ thuật được xây vào dòng:

- **Test-driven development (TDD):** làm rõ hành vi và giảm lỗi hồi quy khi thay đổi.
- **Continuous integration (CI):** phát hiện xung đột và lỗi tích hợp sớm.
- **Refactoring:** cải thiện cấu trúc mà vẫn giữ hành vi, giúp chi phí đổi hướng không tăng quá nhanh.
- **Pair programming:** chia sẻ tri thức, cải thiện phản hồi và giảm phụ thuộc vào một cá nhân.
- **Small releases:** giảm batch size để học và phục hồi sớm nếu đủ điều kiện vận hành.

Nếu một thay đổi làm tăng thời gian viết mã thêm một giờ nhưng ngăn ba ngày sửa lỗi và giảm nguy cơ cho khách, đó có thể là **quyết định tối ưu toàn hệ thống**. Tuy nhiên, cần đo bằng chứng lâu dài chứ không mặc định mọi hoạt động kỹ thuật thêm vào đều tạo lợi ích.

### 14.4. Agile và Lean không mâu thuẫn với quản trị rủi ro

Một hệ thống y tế, thanh toán hoặc dữ liệu nhạy cảm có thể bắt buộc phê duyệt, truy vết hoặc kiểm thử chuyên sâu. Tối ưu toàn hệ thống **không loại bỏ yêu cầu bắt buộc** mà tìm cách cải tiến phần chờ, công việc làm lại, tài liệu trùng lặp và chuẩn bị đầu vào. Việc phát hành thường xuyên vẫn phải đáp ứng trách nhiệm an toàn và pháp lý thực tế.

## 15. Chọn việc cải tiến nào trước trong backlog?

Không phải tất cả vấn đề đã quan sát đều cần sửa ngay. Năng lực dùng cho cải tiến cũng có **chi phí cơ hội**. Nhóm cần so lợi ích với những hạng mục giá trị khác: tính năng, sửa lỗi, giảm nợ và khám phá.

### 15.1. Bộ câu hỏi sắp thứ tự

1. **Tác động tới outcome:** Khách nào bị ảnh hưởng, nhu cầu nào đang chậm hoặc sai?
2. **Độ lớn của điểm chờ/rủi ro:** Bao nhiêu hạng mục hoặc bao nhiêu lần lỗi chịu tác động?
3. **Chi phí trì hoãn:** Nếu không cải tiến trong tháng này, hệ thống sẽ mất gì?
4. **Khả năng thử nhỏ:** Có phương án đảo ngược được, đủ an toàn, ít tốn kém không?
5. **Bằng chứng:** Vấn đề có lặp lại không, dữ liệu đủ tin cậy không?
6. **Phụ thuộc:** Cần thay chính sách của đội khác hoặc quyền quyết định ở đâu?
7. **Chất lượng và con người:** Cải tiến có tăng gánh nặng, làm mờ trách nhiệm hoặc phá nhịp bền vững không?

### 15.2. Bảng ưu tiên minh họa

| Đề xuất | Tác động dự kiến | Công sức/khó khăn | Cách làm có trách nhiệm |
| --- | --- | --- | --- |
| Giảm thời gian chờ review bằng hỗ trợ chéo | Cao nếu Review thường xuyên nghẽn | Nhỏ đến vừa | Thử WIP limit và quy tắc review trong hai tuần. |
| Xây môi trường kiểm thử tự phục vụ | Cao nếu hầu hết story bị chặn ở test | Vừa hoặc lớn | Thử một luồng trước, đo thời gian chờ và lỗi. |
| Viết lại toàn bộ module cũ | Chưa rõ, có thể mở khóa thay đổi | Lớn, rủi ro cao | Chia lát cắt và thu thập bằng chứng trước khi cam kết. |
| Thêm báo cáo đẹp cho số PR | Lợi ích vận hành chưa chứng minh | Nhỏ | Không ưu tiên chỉ vì dễ làm; xem quyết định nào cần dữ liệu đó. |
| Spike xác minh hợp đồng API | Giảm rủi ro tích hợp có ảnh hưởng lớn | Nhỏ, timebox | Chỉ rõ câu hỏi, tiêu chí dừng và quyết định backlog. |

**Không tự động chọn việc có tỷ lệ “giá trị / công sức” lớn nhất theo điểm số** khi tồn tại sự cố an toàn, ngày hạn bắt buộc hoặc nghĩa vụ hợp đồng. Những giới hạn đó cần xem riêng và quyết định đúng thẩm quyền.

### 15.3. Cải tiến thường là một thí nghiệm, không phải dự án cố định

Ví dụ:

> “Trong hai tuần, Developers sẽ ưu tiên giúp hoàn tất các PR đang chờ quá một ngày trước khi mở story mới. Chúng tôi theo dõi thời gian chờ Review, work item age, throughput toàn workflow và lỗi hồi quy. Nếu các chỉ số flow tốt hơn mà lỗi không tăng, tiếp tục thử; nếu công việc bị chặn vì thiếu quyền review, xử lý nút thắt phân quyền.”

Đây là một quyết định Lean hữu ích vì có **giả thuyết, giới hạn, tín hiệu toàn hệ thống và tiêu chí đánh giá**, thay vì chỉ yêu cầu “tăng năng suất review”.

## 16. Những phản mẫu phổ biến và hướng khắc phục

| Phản mẫu | Vì sao là tối ưu cục bộ | Điều chỉnh theo góc nhìn toàn hệ thống |
| --- | --- | --- |
| Mỗi nhóm có KPI riêng nhưng không có outcome chung. | Thành công của bước này không gắn với khách hàng. | Thống nhất kết quả chung, theo dõi flow và chất lượng liên nhóm. |
| Tối đa hóa giờ bận rộn của mọi thành viên. | Không còn năng lực xử lý biến động, hàng đợi dài. | Quản lý WIP, dự phòng hợp lý, đo thời gian tới Done. |
| Bắt đầu nhiều story để tăng số lượng đang làm. | Hạng mục dở dang tăng, giá trị chưa giao. | Kéo việc theo năng lực, ưu tiên hoàn tất, chia lát cắt nhỏ. |
| Cắt kiểm thử/review để “giảm lãng phí”. | Chi phí lỗi và làm lại chuyển về sau. | Tự động hóa, kiểm tra sớm, giữ chuẩn chất lượng bắt buộc. |
| Đo thời gian tới merge nhưng báo là thời gian tới khách hàng. | Loại bỏ thời gian chờ release khỏi số liệu. | Công khai ranh giới, đo thêm từ yêu cầu tới sử dụng. |
| Vẽ value stream theo quy trình lý tưởng. | Che chờ, blocked và rework thực tế. | Truy vết các hạng mục đã hoàn tất và còn đang làm. |
| Tăng tốc bước không phải nút thắt. | Tạo thêm tồn đọng trước giới hạn hiện có. | Quan sát toàn dòng, cải tiến nơi tác động lớn nhất. |
| Phân loại mọi bước phê duyệt là lãng phí. | Bỏ kiểm soát pháp lý/an toàn cần thiết. | Phân biệt giá trị bảo vệ và chờ đợi có thể giảm. |
| Đánh giá velocity giữa các Scrum Team. | Điểm ước lượng không tương thích, thúc tối ưu báo cáo. | Dùng Product Goal, Increment, flow và outcome theo bối cảnh. |
| Chỉ xem cycle time của việc đã Done. | Hạng mục khó đang mở bị che, “survivorship bias”. | Xem work item age, blocked và phân bố thời gian. |
| Viết lại toàn bộ để “xóa nợ kỹ thuật”. | Dời giá trị và tăng rủi ro mà chưa chứng minh lợi ích. | Refactor lát cắt có kiểm thử, đo chi phí thay đổi. |
| Đổ lỗi cho cá nhân ở nút thắt. | Bỏ qua phân quyền, phụ thuộc, WIP và chính sách. | Cùng phân tích nguyên nhân hệ thống và trao quyền cải tiến. |
| Đưa mọi việc vào làn khẩn cấp. | Luồng tiêu chuẩn liên tục bị ngắt, kỳ vọng không còn đáng tin. | Chính sách expedite có tiêu chí và quyền quyết định rõ. |
| Tối ưu chi phí của một bộ phận bằng cách đẩy gánh nặng cho khách. | Chỉ số nội bộ đẹp nhưng trải nghiệm kém. | Đo tổng công sức người dùng, giải quyết dứt điểm và chi phí toàn dịch vụ. |

## 17. Bài tập phân tích và ra quyết định

### Tình huống A — Lập trình nhanh hơn nhưng khách vẫn đợi

Một nhóm trước đây viết xong tám story mỗi tuần. Sau khi đưa công cụ sinh mã vào, họ viết xong mười hai story. QA chỉ có năng lực kiểm thử sáu story mỗi tuần, đội phát hành chỉ triển khai một lần mỗi tháng.

**Câu hỏi:**

1. Vì sao không thể kết luận khả năng giao giá trị tăng 50%?
2. Nút thắt có thể ở đâu? Cần xác minh điều gì?
3. Nếu chưa thể tăng năng lực QA, nhóm có thể thay chính sách kéo việc thế nào?
4. Rủi ro nào xuất hiện nếu “tối ưu” bằng cách bỏ kiểm thử?

**Hướng giải:** Năng lực viết mã tăng nhưng toàn dòng có thể bị giới hạn bởi kiểm thử và phát hành. Cần xem WIP, tuổi hạng mục, chất lượng, lịch sử năng lực QA và mức độ sẵn sàng release. Giảm số hạng mục được bắt đầu, ưu tiên review/test và chia lát cắt. Tự động hóa kiểm thử phù hợp có thể cải thiện nút thắt nhưng không được bỏ kiểm soát rủi ro.

### Tình huống B — Giảm chi phí hỗ trợ nhưng khách làm việc nhiều hơn

Bộ phận hỗ trợ muốn bắt khách hàng tự điền thêm ba biểu mẫu trước khi được gặp nhân viên, với mục tiêu giảm số cuộc gọi. Không có dữ liệu về tỷ lệ khách bỏ dở.

**Câu hỏi:**

1. Đây có thể là tối ưu cục bộ như thế nào?
2. Outcome nào cần đo cho khách hàng?
3. Có thể thử một phương án nhỏ nào ít rủi ro hơn?

**Hướng giải:** Giảm số cuộc gọi chưa chắc giảm tổng chi phí cho khách và tổ chức. Nên đo tỷ lệ giải quyết thành công, thời gian khách hoàn tất việc, cuộc gọi lặp và phản hồi. Có thể thử trang trạng thái tự phục vụ cho một nhu cầu phổ biến, quan sát khả năng tìm được thông tin và cho phép liên hệ hỗ trợ dễ dàng khi cần.

### Tình huống C — Nợ kỹ thuật hay một feature mới?

Nhóm sản phẩm muốn có tính năng đổi lịch. Developers cho biết logic giờ trống bị lặp trong ba service, mỗi lần đổi dễ gây lỗi và phải kiểm thử thủ công hai ngày. Một bên liên quan nói “đó là việc nội bộ, cứ xây feature trước”.

**Câu hỏi:**

1. Cách nào diễn đạt giá trị giảm nợ kỹ thuật để các bên cùng hiểu?
2. Có nên viết lại toàn bộ ba service không?
3. Lát cắt nào vừa phục vụ feature, vừa cải thiện khả năng đổi hướng?

**Hướng giải:** Ghi tác động thực tế: làm lại, lỗi hồi quy, thời gian chờ và rủi ro cho khách. Chọn lát cắt có kiểm thử bảo vệ hành vi, gom quy tắc liên quan tới tính năng đổi lịch và tích hợp thường xuyên; đánh giá số lỗi, thời gian sửa và cycle time sau thay đổi. Không quyết định viết lại lớn chỉ từ cảm giác mã “không sạch”.

### Tình huống D — KPI Review được cải thiện nhưng lỗi tăng

Một đội đặt mục tiêu giảm thời gian review trung vị từ hai ngày còn hai giờ. Họ đạt chỉ số bằng cách chỉ đọc nhanh tiêu đề PR và bỏ kiểm thử tích hợp. Một tháng sau số lỗi hồi quy tăng đáng kể.

**Câu hỏi:**

1. Chỉ số cục bộ nào bị tối ưu sai?
2. Vì sao chất lượng là một phần của dòng giá trị?
3. Có cách giảm chờ review mà không giảm độ sâu kiểm tra không?

**Hướng giải:** Mục tiêu thời gian review bị tách khỏi chất lượng và tổng thời gian tới giá trị. Cần tìm điểm chờ thực tế, giảm kích thước PR, cung cấp bối cảnh/tiêu chí review, dùng kiểm thử tự động và pair programming khi phù hợp. Đo end-to-end lead time, lỗi thoát production và chi phí làm lại.

### Tình huống E — Đội dùng Scrum có velocity cao nhưng Sprint Goal thường trượt

Mỗi Developer chọn những story dễ đóng để tối đa hóa story point. Nhiều hạng mục phục vụ Sprint Goal bị chặn ở khâu tích hợp. Daily Scrum chỉ nghe báo cáo cá nhân, Sprint Review chủ yếu đếm ticket.

**Câu hỏi:**

1. Những dấu hiệu tối ưu cục bộ nào đang xuất hiện?
2. Sprint Goal, Increment và DoD nên được dùng ra sao?
3. Scrum Team có thể dùng thực hành Kanban hay XP nào để cải thiện?

**Hướng giải:** Tập trung vào Sprint Goal, giúp hoàn tất phần quan trọng, bảo vệ DoD và cập nhật Sprint Backlog khi học thêm. Thử WIP limit, nhìn blocked/age, CI, TDD, pairing hoặc review nhanh theo hạng mục. Đo giá trị người dùng và chất lượng, không dùng điểm để xếp năng suất thành viên.

### Tình huống F — Tăng công suất ở nút thắt

Một workflow có ba khâu bắt buộc theo thứ tự: **Phát triển 9 mục/tuần**, **Kiểm thử 4 mục/tuần**, **Phát hành 7 mục/tuần**. Giả sử loại việc tương đối nhất quán, không có làm lại và đầu vào đủ.

**Câu hỏi:**

1. Throughput lý thuyết tối đa của toàn dòng là bao nhiêu?
2. Nếu nâng Phát triển lên 15 mục/tuần thì toàn dòng tăng được bao nhiêu?
3. Nếu tăng năng lực Kiểm thử lên 6 mục/tuần, giới hạn tiếp theo là gì?
4. Vì sao đây vẫn chỉ là mô hình cần đối chiếu số liệu thật?

**Đáp án tham khảo:** (1) **4 mục/tuần** do Kiểm thử; (2) **không tăng** nếu các khâu khác giữ nguyên; (3) tối đa **6 mục/tuần** trong mô hình, Kiểm thử vẫn là giới hạn trước khi tới Phát hành 7 và Phát triển 9; (4) công việc có kích thước, lỗi, nghỉ, hàng đợi và phụ thuộc biến động.

### Bài tập tính Little’s Law có điều kiện

Một luồng đủ ổn định có **WIP trung bình 10 hạng mục** và **throughput trung bình 5 hạng mục/tuần**.

1. Thời gian trung bình một hạng mục ở trong hệ thống khoảng bao nhiêu?
2. Nếu giảm WIP còn 6 và throughput giữ nguyên, mô hình cho khoảng thời gian bao nhiêu?
3. Có được hứa mọi ticket chắc chắn hoàn tất trong thời gian trung bình vừa tính không?
4. Hạng mục chưa hoàn tất sau 15 ngày cần theo dõi **cycle time hay work item age**?

**Đáp án:** (1) \(10/5=2\) tuần; (2) \(6/5=1{,}2\) tuần; (3) không, vì đây là quan hệ trung bình trong điều kiện ổn định; (4) **work item age** cùng lý do bị chặn và độ lệch so với SLE nếu có.

## 18. Workshop 60 phút: từ value stream tới một thí nghiệm cải tiến

Chọn một dòng giá trị đủ cụ thể, ví dụ **“một user story nhỏ từ khi được chấp nhận tới khi người dùng sử dụng được”**. Mời người có thông tin ở từng bước: Product Owner hoặc người ưu tiên, Developers, kiểm thử, vận hành và người hỗ trợ khách hàng khi thích hợp.

### 18.1. Gợi ý điều phối

| Thời lượng | Hoạt động | Đầu ra |
| --- | --- | --- |
| 0–10 phút | Xác định người nhận giá trị, mục tiêu và ranh giới dòng. | Một câu mô tả outcome, start và finish. |
| 10–25 phút | Truy vết vài hạng mục thật, vẽ bước, hàng đợi, thời gian chờ, làm lại. | Bản đồ value stream hiện tại. |
| 25–35 phút | Xem dữ liệu WIP, throughput, cycle time, tuổi việc và lỗi; xác định giới hạn chính. | Một giả thuyết về nút thắt hoặc lãng phí quan trọng. |
| 35–45 phút | Sinh vài lựa chọn, so tác động trên toàn dòng và điều kiện bảo vệ. | Các phương án được ghi cùng rủi ro/chi phí. |
| 45–55 phút | Chọn một thử nghiệm nhỏ, người phụ trách, thời hạn và phép đo. | Kế hoạch thử nghiệm có thể thực hiện. |
| 55–60 phút | Xác nhận quyền quyết định, thông tin cần chia sẻ và thời điểm xem lại. | Quyết định và cách học từ kết quả. |

Đây chỉ là khung minh họa. Một nhóm có ít dữ liệu có thể dành thêm thời gian đo **trước khi** đổi chính sách. Không cần mở cuộc họp 60 phút chỉ để xử lý một trở ngại đơn giản có thể giải quyết trực tiếp.

### 18.2. Mẫu báo cáo cải tiến một trang

~~~text
Dòng giá trị          : Từ user story ưu tiên tới khi khách dùng được.
Mục tiêu người dùng    : ...
Ranh giới đo           : Bắt đầu ... / Kết thúc ...
Các khâu/hàng đợi      : ...
Thực trạng và bằng chứng: ...
Điểm chờ/nút thắt      : ...
Giả thuyết nguyên nhân : ...
Phương án đã cân nhắc  : ...
Thử nghiệm được chọn  : ...
Giới hạn / timebox     : ...
Người phối hợp/chịu trách nhiệm: ...
Chỉ số toàn dòng       : Lead time, cycle time, WIP, throughput ...
Điều kiện bảo vệ       : Lỗi, quyền riêng tư, sự cố, trải nghiệm ...
Outcome người dùng     : ...
Thời điểm xem lại      : ...
Quyết định sau thử     : Giữ / sửa / dừng; bằng chứng đi kèm.
~~~

### 18.3. Một ví dụ kế hoạch thử nghiệm hoàn chỉnh

**Vấn đề:** Hơn một nửa số story bị kéo dài vì chờ review và test; nhóm thường bắt đầu việc mới khi gặp điểm chặn.

**Giả thuyết:** Giảm WIP và ưu tiên hỗ trợ hoàn tất sẽ giảm cycle time toàn dòng mà không giảm throughput hoặc chất lượng.

**Thử nghiệm trong hai tuần:** Giới hạn ba hạng mục trong phát triển, hai mục trong review (các giá trị minh họa); khi Review đầy, Developers ưu tiên hỗ trợ review; blocked hiển thị rõ.

**Thước đo:** WIP trung bình, phân bố cycle time, work item age, throughput; thêm lỗi hồi quy và tỷ lệ giao hạng mục có ích theo mục tiêu sản phẩm.

**Quy tắc xem lại:** Nếu flow cải thiện nhưng lỗi tăng, không coi thử nghiệm là thành công. Nếu flow không đổi do chờ quyền môi trường, chuyển trọng tâm sang phụ thuộc môi trường thay vì tăng sức ép lên Developers.

## 19. Checklist để tránh tối ưu cục bộ

### Trước khi quyết định cải tiến

- [ ] Đã nêu người dùng hoặc tổ chức cần **kết quả gì**, không chỉ chỉ số bộ phận.
- [ ] Đã xác định ranh giới từ đầu vào tới **giá trị được giao**, hoặc công khai phần ngoài phạm vi.
- [ ] Có dữ liệu về thời gian xử lý, chờ, làm lại và điều kiện chất lượng cần giữ.
- [ ] Đã nhìn công việc đang mở, bị chặn và hàng đợi; không chỉ việc đã Done.
- [ ] Đã xem **nút thắt hiện tại** và khả năng nó dịch chuyển sau cải tiến.
- [ ] Nếu đề xuất tăng công suất một bước, đã kiểm tra bước tiếp theo có hấp thụ được không.
- [ ] Người chịu ảnh hưởng ở các nhóm liên quan có cơ hội cung cấp thông tin.

### Khi thực hiện

- [ ] Thử nghiệm có phạm vi, thời gian, người phụ trách và cơ chế điều chỉnh.
- [ ] WIP và chính sách kéo việc không bị phá thường xuyên chỉ để giữ mọi người bận.
- [ ] Điều kiện chất lượng, an toàn, bảo mật và nghĩa vụ bắt buộc được giữ.
- [ ] Có kế hoạch xử lý sự cố và việc khẩn cấp theo thẩm quyền.
- [ ] Có đủ không gian cho review, kiểm thử, học hỏi và cải tiến.
- [ ] Không chuyển chi phí sang người dùng hoặc nhóm khác mà không ghi nhận.

### Khi đánh giá

- [ ] Chỉ số cục bộ được đối chiếu với **flow đầu cuối** và **outcome**.
- [ ] Có tín hiệu chất lượng, nợ kỹ thuật và khả năng duy trì nhịp làm việc.
- [ ] Không dùng một trung bình hoặc số ticket đóng để kết luận nhân quả.
- [ ] Việc chưa hoàn tất được theo dõi qua work item age, không bị che khỏi dashboard.
- [ ] Nhóm có thể nói điều gì đã học, điều gì còn chưa biết và cải tiến tiếp theo là gì.
- [ ] Chính sách được giữ, thay đổi hoặc hủy dựa trên bằng chứng, không dựa vào sĩ diện hoặc chỉ tiêu cũ.

## 20. Ghi nhớ cốt lõi

**Tối ưu cục bộ** xảy ra khi một người, một nhóm hoặc một bước làm tốt chỉ số riêng nhưng khiến toàn dòng chậm hơn, nhiều lỗi hơn hoặc giao ít giá trị hơn. **Tối ưu toàn hệ thống** bắt đầu từ kết quả người dùng, theo dõi cả dòng giá trị và điều kiện chất lượng, rồi chọn nơi cải tiến có tác động thật.

Ba câu hỏi cần nhớ:

1. **Ta đang tối ưu điều gì cho ai?** Nếu câu trả lời chỉ là “số ticket” hoặc “độ bận rộn”, cần nhìn lại mục tiêu giá trị.
2. **Dòng bị giới hạn ở đâu?** Quan sát WIP, hàng đợi, work item age, cycle time và những bước làm lại trước khi tăng công suất một khâu.
3. **Cải tiến có giúp cả hệ thống tốt hơn không?** Kiểm tra thời gian tới giá trị, outcome, chất lượng, rủi ro và năng lực bền vững, không chỉ tốc độ của một bộ phận.

Trong phát triển Agile, Scrum giúp nhóm có **mục tiêu và nhịp kiểm tra–thích ứng**, Kanban làm hiện rõ **workflow và lượng việc đang làm**, XP giúp **giữ chất lượng và giảm chi phí thay đổi**. Tư duy Lean kết nối những thực hành đó để tránh một nghịch lý phổ biến: **tất cả mọi người đều rất bận, nhưng khách hàng vẫn phải đợi**.

### Tài liệu tham khảo để đọc tiếp

- [Lean Enterprise Institute](https://www.lean.org/) — tư duy giá trị, dòng giá trị, dòng chảy và cải tiến toàn hệ thống.
- [The Kanban Guide](https://kanbanguides.org/) — định nghĩa workflow, WIP, throughput, cycle time, work item age và cải tiến flow.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Goal, Sprint Goal, Definition of Done và vòng kiểm tra–thích ứng.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — ưu tiên phần mềm hoạt động, cộng tác và đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — đơn giản, chất lượng kỹ thuật, giao thường xuyên và nhịp bền vững.
- [DORA](https://dora.dev/) — nghiên cứu về năng lực giao thay đổi phần mềm, độ ổn định và tác động của các thực hành kỹ thuật.
