# Tạo điều kiện để nhóm tự tổ chức hình thành giải pháp phù hợp

## 1. Nguyên tắc Agile số 11 nói gì?

Một trong 12 nguyên tắc của Tuyên ngôn Agile phát biểu:

> **The best architectures, requirements, and designs emerge from self-organizing teams.**

Có thể diễn đạt bằng tiếng Việt: **Kiến trúc, yêu cầu và thiết kế tốt nhất được hình thành từ những nhóm có khả năng tự tổ chức.**

Ở đây, **tự tổ chức** (*self-organizing*) là khả năng các thành viên cùng điều phối công việc, phối hợp chuyên môn và đưa ra quyết định phù hợp để đạt mục tiêu, dựa trên thông tin họ có và phản hồi thực tế. Họ không chỉ làm theo danh sách nhiệm vụ do người khác phân chi tiết từng bước. Người lãnh đạo và tổ chức tạo điều kiện để nhóm quyết định **cách** giải quyết vấn đề trong một phạm vi trách nhiệm rõ ràng.

Nguyên tắc này liên quan trực tiếp đến mục tiêu của **AGILE_DEVELOPMENT**: phát triển phần mềm thích ứng, giao giá trị tăng dần, nhận phản hồi sớm và cải tiến liên tục. Nếu mọi quyết định nhỏ đều phải đi qua cấp quản lý hoặc một chuyên gia không tham gia làm việc hằng ngày, nhóm thường chậm thử nghiệm, chậm xử lý vấn đề và khó học từ các Increment đã giao.

Tuy nhiên, nguyên tắc không khẳng định mọi quyết định do nhóm đưa ra đều tự động đúng. Kết quả tốt đến từ **quyền tự quyết đi cùng năng lực, trách nhiệm, giới hạn an toàn và cơ chế phản hồi**.

### 1.1. Vì sao đề cập cả kiến trúc, yêu cầu và thiết kế?

Ba khía cạnh có liên hệ nhưng giải quyết các câu hỏi khác nhau:

| Khía cạnh | Câu hỏi cốt lõi | Ví dụ với nền tảng đặt lịch tư vấn |
| --- | --- | --- |
| **Yêu cầu (requirements)** | Người dùng cần kết quả gì, quy tắc và giới hạn nào phải đáp ứng? | Khách không được đặt trùng một khung giờ đã hết chỗ; nhân viên có thể xem lịch được phép quản lý. |
| **Thiết kế (design)** | Người dùng tương tác ra sao, các thành phần và hành vi được tổ chức như thế nào? | Cách hiển thị giờ trống, xác nhận đặt lịch, xử lý lỗi và thiết kế API. |
| **Kiến trúc (architecture)** | Những quyết định cấu trúc nào ảnh hưởng đáng kể đến chất lượng, tích hợp và khả năng thay đổi hệ thống? | Phạm vi giao dịch đặt lịch, lưu trữ dữ liệu, cách đồng bộ với hệ thống nhân viên. |

Yêu cầu không đơn thuần là danh sách tính năng đã được “đóng băng” từ đầu. Kiến trúc cũng không chỉ là bản vẽ hoàn thành trước lập trình. Khi nhóm thiết kế, xây dựng, kiểm thử và quan sát sản phẩm, họ có thể phát hiện yêu cầu chưa rõ, giới hạn kỹ thuật chưa được dự đoán hoặc một lựa chọn thiết kế khó dùng. **Các quyết định tốt dần hình thành qua hợp tác và kiểm chứng.**

### 1.2. “Hình thành” không có nghĩa là tự xuất hiện mà không cần suy nghĩ

Từ **emerge** nhấn mạnh việc giải pháp được khám phá và tinh chỉnh dựa trên thông tin mới, chứ không bắt buộc phải biết hết mọi chi tiết ngay ngày đầu. Để giải pháp hình thành theo hướng tốt, nhóm vẫn cần:

- Trao đổi rõ mục tiêu sản phẩm và nhu cầu người dùng.
- Thiết kế các phần quan trọng trước khi thực hiện khi rủi ro yêu cầu.
- Thử nghiệm giả thuyết và phương án kỹ thuật.
- Có tiêu chuẩn về chất lượng, bảo mật, khả năng vận hành và tính tương thích.
- Tích hợp, kiểm thử, quan sát phản hồi rồi điều chỉnh kiến trúc và thiết kế.
- Ghi lại những quyết định đáng nhớ để người khác hiểu và tiếp tục công việc.

Nguyên tắc này **không phải** “cứ viết mã trước rồi để kiến trúc tự xuất hiện”. Các quyết định khó đảo ngược, có rủi ro lớn hoặc ảnh hưởng nhiều nhóm có thể đòi hỏi phân tích, kiểm chứng và phê duyệt trước theo chính sách của tổ chức.

## 2. Một nhóm tự tổ chức thực sự có những đặc điểm gì?

Nhóm tự tổ chức có thể thống nhất **ai làm gì, phối hợp ra sao, xử lý cản trở thế nào và cách kiểm chứng kết quả** mà không phải đợi chỉ đạo chi tiết cho từng tác vụ. Các thành viên sử dụng hiểu biết đa chuyên môn để lựa chọn cách tạo giá trị.

Điều này khác với hai thái cực: một nhóm chỉ nhận lệnh và một nhóm không có trách nhiệm giải trình.

| Nội dung | Nhóm phụ thuộc chỉ đạo chi tiết | Nhóm có khả năng tự tổ chức |
| --- | --- | --- |
| **Mục tiêu** | Nhận từng việc riêng lẻ, đôi khi không biết vì sao cần làm. | Hiểu mục tiêu sản phẩm, người hưởng lợi và tiêu chí thành công. |
| **Phân chia việc** | Quản lý giao từng tác vụ cho từng người. | Nhóm cùng lập kế hoạch, trao đổi năng lực và nhận việc phù hợp. |
| **Giải pháp kỹ thuật** | Chờ chỉ định cách làm cho mọi thay đổi. | Chủ động đánh giá phương án trong các ràng buộc đã thống nhất. |
| **Vướng mắc** | Chuyển tiếp lên cấp trên rồi chờ. | Phối hợp tháo gỡ trong quyền hạn; chủ động yêu cầu hỗ trợ khi vượt phạm vi. |
| **Chất lượng** | Để một bộ phận phía sau “kiểm tra hộ”. | Cùng chịu trách nhiệm tạo Increment đáp ứng Definition of Done. |
| **Học hỏi** | Đợi tổng kết cuối dự án. | Xem kết quả thường xuyên và điều chỉnh cách làm, backlog, thiết kế. |

**Tự tổ chức không đồng nghĩa** với mỗi người thích làm gì thì làm, quyết định nào cũng cần biểu quyết, không có người chịu trách nhiệm cuối cùng, hoặc nhóm được miễn các yêu cầu chung về an toàn và tuân thủ. Quyền tự quyết cần có **ranh giới và cơ chế phối hợp**.

### 2.1. Tự tổ chức, tự quản lý và liên chức năng

Các thuật ngữ thường đi cùng nhau nhưng không hoàn toàn giống nhau:

- **Tự tổ chức (self-organizing):** nhóm chủ động tìm cách phối hợp và giải quyết công việc để đạt mục tiêu.
- **Tự quản lý (self-managing):** nhóm có quyền chủ động hơn trong điều hành công việc nội bộ, chẳng hạn quyết định ai làm gì, khi nào và bằng cách nào trong phạm vi được giao.
- **Liên chức năng (cross-functional):** nhóm có hoặc tiếp cận được các năng lực cần thiết để tạo ra kết quả, thay vì mỗi bước phải chuyển giao qua nhiều phòng ban độc lập.

**Scrum Guide 2020** sử dụng thuật ngữ *self-managing* cho Scrum Team: nhóm quyết định nội bộ ai làm gì, khi nào và như thế nào, đồng thời có các trách nhiệm được xác định rõ. Nguyên tắc Agile số 11 trong tuyên ngôn gốc sử dụng *self-organizing*. Khi trao đổi trong dự án cần hiểu bối cảnh của từng thuật ngữ thay vì xem chúng là một nhãn tổ chức duy nhất.

Một nhóm có thể có quyền tự tổ chức tốt nhưng vẫn phụ thuộc chuyên gia an ninh cho việc kiểm tra bảo mật chuyên sâu. Điều quan trọng là sự phụ thuộc này được nhận diện, có cơ chế cộng tác và không trở thành điểm chờ đợi vô thời hạn.

### 2.2. Quyền quyết định đi kèm trách nhiệm

Để tránh mơ hồ, tổ chức và nhóm nên làm rõ bốn điều:

1. **Mục tiêu được giao:** nhóm đang hướng tới kết quả nào?
2. **Quyết định nhóm được tự đưa ra:** ví dụ cách phân chia hạng mục, thiết kế trong một dịch vụ hoặc phương pháp kiểm thử.
3. **Ràng buộc phải tôn trọng:** ví dụ quyền riêng tư, tiêu chuẩn bảo mật, ngân sách, công nghệ bắt buộc, cam kết tương thích.
4. **Trường hợp cần tham vấn hoặc nâng cấp quyết định:** ví dụ thay đổi hợp đồng API dùng chung, dữ liệu nhạy cảm hoặc kiến trúc ảnh hưởng nhiều sản phẩm.

Nếu chỉ tuyên bố “các bạn được tự chủ” mà vẫn yêu cầu trưởng nhóm duyệt từng việc nhỏ, mức tự chủ thực tế rất thấp. Nếu trao toàn quyền mà không nêu nghĩa vụ pháp lý hoặc rủi ro tích hợp, nhóm cũng thiếu điều kiện để quyết định đúng.

## 3. Vai trò của lãnh đạo: tạo điều kiện cho nhóm quyết định tốt

Người quản lý, lãnh đạo kỹ thuật và người phụ trách sản phẩm vẫn rất cần thiết. Trách nhiệm thay đổi từ **chỉ đạo chi tiết từng thao tác** sang **thiết lập hướng đi, điều kiện, chuẩn chất lượng và khả năng tháo gỡ vướng mắc**.

### 3.1. Đưa ra mục tiêu rõ, chừa không gian tìm cách đạt mục tiêu

Thay vì giao:

> “Em A viết endpoint X, em B làm bảng Y, em C tạo popup Z, tất cả phải theo bản thiết kế này.”

Có thể giao một mục tiêu có thể kiểm chứng:

> “Khách hàng cần đặt được khung giờ còn trống mà không bị trùng lịch. Hãy đề xuất một lát cắt chức năng dùng được, nêu rủi ro và cách đo kết quả; đảm bảo các chính sách về quyền truy cập và tích hợp.”

Nhóm có cơ hội làm rõ yêu cầu, chọn thứ tự công việc và đưa ra phương án dựa trên kinh nghiệm triển khai thực tế. Mục tiêu rõ là nền tảng để tự tổ chức, bởi không thể phân quyền hiệu quả khi không ai biết thành công nghĩa là gì.

### 3.2. Tạo môi trường an toàn để phản biện và học từ lỗi

Nhóm khó tự tổ chức nếu mọi câu hỏi bị xem là yếu kém hoặc mỗi thử nghiệm không thành công đều dẫn đến đổ lỗi cá nhân. Lãnh đạo nên khuyến khích:

- Nêu ý kiến và rủi ro sớm, kể cả khi trái quan điểm của người có thâm niên.
- Thảo luận phương án dựa trên tiêu chí, dữ liệu và kiểm chứng.
- Thừa nhận điều chưa biết; dùng thử nghiệm nhỏ để giảm bất định.
- Phân tích lỗi theo bối cảnh hệ thống và cách phòng ngừa, đồng thời vẫn xác định trách nhiệm khắc phục.
- Chủ động trao đổi với khách hàng, vận hành, bảo mật và nhóm phụ thuộc thay vì tự suy đoán.

Sự an toàn trong trao đổi không có nghĩa là không đánh giá chất lượng quyết định hoặc không yêu cầu trách nhiệm giải trình.

### 3.3. Cung cấp năng lực và nguồn lực

Tự chủ ít giá trị khi nhóm không có quyền truy cập môi trường thử nghiệm, không thể xem log phù hợp, không có kỹ năng kiểm thử hoặc phải chờ nhiều tuần để xác nhận một yêu cầu nhỏ.

Những điều kiện giúp nhóm hành động:

| Điều kiện | Cách tạo điều kiện | Hậu quả nếu thiếu |
| --- | --- | --- |
| **Mục tiêu và ưu tiên rõ** | Product Goal, mục tiêu Sprint hoặc mục tiêu dòng công việc, backlog được giải thích. | Nhóm tự tối ưu các việc ít giá trị. |
| **Năng lực đủ rộng** | Phát triển, kiểm thử, thiết kế, vận hành và chuyên môn lĩnh vực phù hợp; đào tạo hoặc ghép cặp khi thiếu. | Chuyển giao liên tục, phải chờ chuyên gia cho việc cơ bản. |
| **Quyền tiếp cận công cụ** | Môi trường thử, pipeline, tài liệu tích hợp và quyền được cấp theo nguyên tắc an toàn. | Nhóm khó kiểm tra giả thuyết và chất lượng. |
| **Phản hồi thường xuyên** | Tiếp xúc người dùng, Sprint Review, quan sát hành vi, kết quả kiểm thử. | Quyết định dựa trên giả định lâu ngày không kiểm chứng. |
| **Ranh giới quyết định** | Tiêu chuẩn, quyền hạn, trường hợp phải tham vấn được công bố. | Sợ quyết định hoặc quyết định vượt thẩm quyền. |
| **Đủ thời gian cải tiến** | Dành năng lực cho giảm nợ kỹ thuật, thử nghiệm và retrospective. | Nhóm chỉ xử lý việc gấp, lặp lại nguyên nhân lỗi. |

Vai trò của lãnh đạo là chủ động xử lý những điều kiện mang tính hệ thống đó, thay vì yêu cầu nhóm “tự tổ chức hơn” trong khi mọi nút thắt vẫn giữ nguyên.

## 4. Phân quyền ra quyết định mà vẫn giữ sự nhất quán

Tự tổ chức không buộc tổ chức xóa bỏ kiến trúc chung, chuẩn dữ liệu hay vai trò chuyên môn. Cần chọn **nơi ra quyết định gần thông tin nhất**, đồng thời bảo đảm quyết định có ảnh hưởng rộng được phối hợp đầy đủ.

### 4.1. Phân loại quyết định theo tác động

Một cách thực hành đơn giản:

| Loại quyết định | Ví dụ | Cách xử lý đề xuất |
| --- | --- | --- |
| **Nhỏ, dễ đảo ngược, trong phạm vi nhóm** | Đổi tên hàm, sắp xếp test, chọn cách chia một user story. | Thành viên liên quan tự quyết hoặc trao đổi ngắn trong nhóm, theo chuẩn chung. |
| **Quan trọng trong một thành phần** | Đổi cách tính lịch trống, thêm cache, thay thiết kế module. | Thảo luận phương án và tiêu chí; kiểm chứng bằng test/spike, ghi quyết định khi có ích. |
| **Ảnh hưởng nhiều nhóm hoặc hợp đồng chung** | Thay định dạng sự kiện, schema API, quyền truy cập dữ liệu. | Tham vấn nhóm phụ thuộc, chủ sở hữu hợp đồng, chuyên gia liên quan; thống nhất kế hoạch tương thích. |
| **Rủi ro cao hoặc bắt buộc phê duyệt** | Xử lý thông tin nhạy cảm, thay đổi cơ chế thanh toán, bỏ kiểm soát bảo mật. | Thực hiện đánh giá và phê duyệt theo chính sách; nhóm vẫn đề xuất giải pháp và bằng chứng. |

Mục tiêu là giảm các phê duyệt không cần thiết trong khi giữ được **trách nhiệm chung với hệ thống**. Một quyết định nội bộ có thể trở thành quyết định liên nhóm nếu phát hiện ảnh hưởng đến hợp đồng đang được nhiều nơi sử dụng; khi đó cần điều chỉnh cách phối hợp.

### 4.2. Một quy trình quyết định ngắn và có trách nhiệm

Đối với một vấn đề kỹ thuật đáng kể, nhóm có thể dùng quy trình:

1. **Nêu quyết định cần đưa ra.** Tránh bắt đầu bằng việc bảo vệ giải pháp yêu thích của một người.
2. **Xác định tiêu chí.** Giá trị người dùng, độ tin cậy, an toàn, khả năng thay đổi, chi phí và thời gian phản hồi.
3. **Liệt kê các phương án khả thi.** Không cần tìm ra vô số phương án; đủ để nhìn thấy đánh đổi quan trọng.
4. **Hỏi người bị ảnh hưởng và người có chuyên môn.** Giữ quyền quyết định trong phạm vi đã thống nhất.
5. **Giảm bất định bằng bằng chứng.** Dùng spike giới hạn thời gian, nguyên mẫu, benchmark hoặc test khi cần.
6. **Ra quyết định và ghi lại lý do tương xứng với tác động.** Quyết định nhỏ có thể thể hiện qua code review; quyết định khó đảo ngược nên có ADR.
7. **Thử trong Increment và xem lại kết quả.** Quan sát vấn đề thực tế; điều chỉnh khi bằng chứng cho thấy cần thay.

Một cuộc thảo luận không nhất thiết phải đạt sự đồng thuận tuyệt đối. Nhóm nên có quy tắc rõ **ai quyết định cuối cùng trong trường hợp bất đồng**, cách người có quan điểm khác được lắng nghe và cách các thành viên cùng thực hiện quyết định đã thống nhất.

~~~mermaid
flowchart TD
    A["Mục tiêu, yêu cầu và ràng buộc"] --> B["Nhóm đề xuất phương án"]
    B --> C{"Tác động vượt phạm vi nhóm?"}
    C -- "Không" --> D["Quyết định trong nhóm"]
    C -- "Có" --> E["Tham vấn / phê duyệt liên quan"]
    E --> D
    D --> F["Xây dựng, tích hợp, kiểm thử"]
    F --> G["Increment đáp ứng Definition of Done"]
    G --> H["Phản hồi và chỉ số thực tế"]
    H --> I["Điều chỉnh yêu cầu / thiết kế / cách làm"]
    I --> A
~~~

### 4.3. ADR giúp giữ trí nhớ về những quyết định lớn

**Architecture Decision Record (ADR)** là ghi chép ngắn về một quyết định kiến trúc quan trọng. Nó không cần trở thành bản thiết kế dài; mục đích là giúp người đến sau biết **tại sao** nhóm chọn một hướng và khi nào nên xem lại.

Mẫu tối giản:

~~~markdown
# ADR-007: Kiểm soát chỗ trống khi xác nhận đặt lịch

## Bối cảnh
Nhiều khách có thể cùng xác nhận một khung giờ có số chỗ giới hạn.
Không được xác nhận vượt sức chứa.

## Các phương án
1. Chỉ kiểm tra trên giao diện.
2. Kiểm tra và cập nhật sức chứa nguyên tử trong cơ sở dữ liệu.
3. Dùng một hàng đợi xử lý đặt lịch tập trung.

## Quyết định
Chọn phương án 2 trong phạm vi dịch vụ hiện tại.

## Lý do
Đáp ứng quy tắc nhất quán và mức tải đã biết với độ phức tạp phù hợp.
Kiểm chứng bằng kiểm thử cạnh tranh và theo dõi lỗi xác nhận.

## Hệ quả / Khi xem lại
Cần bảo vệ giao dịch và xử lý trường hợp tranh chấp.
Xem lại nếu quy mô hoặc ranh giới dịch vụ thay đổi đáng kể.
~~~

Đây chỉ là **quyết định minh họa**; không có một lựa chọn lưu trữ đúng cho mọi hệ thống. Nhóm phải kiểm tra đặc tính của cơ sở dữ liệu, mức độ cạnh tranh, yêu cầu nghiệp vụ và cách triển khai thật.

## 5. Ví dụ thực tế: nhóm tự hình thành giải pháp đặt lịch

Giả sử sản phẩm có tính năng đặt lịch tư vấn. Khách hàng thường phải gọi điện để tìm giờ trống; nhóm sản phẩm muốn một Increment đầu tiên cho phép đặt trực tuyến mà không xác nhận trùng chỗ.

### 5.1. Nhận mục tiêu thay vì bản chia việc cố định

**Mục tiêu sản phẩm:** khách có thể chọn một giờ còn chỗ, xác nhận lịch và nhận thông tin cuộc hẹn với ít thao tác.

**Những giới hạn đã biết:**

- Không được xác nhận số cuộc hẹn vượt sức chứa của khung giờ.
- Chỉ người có quyền mới xem hoặc sửa dữ liệu cuộc hẹn.
- Phải tương thích với hệ thống quản lý lịch hiện có.
- Quy tắc sử dụng dữ liệu cá nhân phải được tôn trọng.

Người phụ trách sản phẩm cung cấp bối cảnh, người dùng mục tiêu, ưu tiên trong Product Backlog và giúp làm rõ phạm vi; đội kỹ thuật chủ động quyết định cách tạo Increment trong các giới hạn trên.

### 5.2. Tự tổ chức để làm rõ yêu cầu

Thay vì giao ngay “viết endpoint tạo lịch”, nhóm gồm kỹ sư giao diện, backend, QA và người có kiến thức vận hành cùng hỏi:

- “Khung giờ trống” được tính theo phòng, nhân viên hay tổng số chỗ?
- Khi hai khách cùng bấm xác nhận, trạng thái nào là nguồn sự thật?
- Nếu gửi xác nhận thất bại nhưng giao dịch đã lưu, có thể gửi lại an toàn không?
- Ai được đổi hoặc hủy lịch? Cần kiểm tra quyền ở đâu?
- Khách dùng thiết bị và múi giờ nào? Thông tin nào cần xuất hiện trong xác nhận?

Nhóm trao đổi với Product Owner hoặc chuyên gia nghiệp vụ để xác nhận các quy tắc. **Tự tổ chức không cho phép nhóm tự quyết mọi chính sách kinh doanh** khi chưa có thẩm quyền; nó giúp nhóm chủ động phát hiện và giải quyết câu hỏi thay vì thụ động làm theo giả định.

Một user story có thể là:

> Là khách hàng, tôi muốn chọn một khung giờ còn chỗ và nhận xác nhận để không phải gọi điện nhiều lần.

Ví dụ về tiêu chí chấp nhận:

~~~gherkin
Feature: Đặt lịch tư vấn trong khung giờ giới hạn chỗ

  Scenario: Xác nhận thành công khi còn chỗ
    Given khách đủ điều kiện và khung giờ A còn một chỗ
    When khách xác nhận đặt khung giờ A
    Then hệ thống lưu một cuộc hẹn hợp lệ
    And khách nhận được trạng thái xác nhận thành công

  Scenario: Hai yêu cầu cạnh tranh cho chỗ cuối
    Given khung giờ A chỉ còn một chỗ
    When hai khách đủ điều kiện đồng thời xác nhận khung giờ A
    Then tối đa một cuộc hẹn mới được xác nhận
    And khách không được chỗ nhận thông báo phù hợp

  Scenario: Không lộ thông tin lịch của người khác
    Given khách X đã đăng nhập
    When khách X yêu cầu xem lịch riêng của khách Y
    Then hệ thống từ chối truy cập nếu X không có quyền
~~~

Các tình huống trên là **đặc tả bằng ví dụ**. Chúng chỉ trở thành kiểm thử tự động khi được nối với mã kiểm thử và chạy trong môi trường phù hợp.

### 5.3. Nhóm lựa chọn kiến trúc và thiết kế như thế nào?

Đội kỹ thuật cùng xem xét:

| Phương án | Ưu điểm có thể có | Rủi ro / câu hỏi cần kiểm chứng |
| --- | --- | --- |
| Kiểm tra “còn chỗ” trên giao diện trước khi gửi | Phản hồi sớm cho người dùng, dễ thực hiện. | Không bảo đảm đúng khi nhiều khách đặt đồng thời; chỉ dùng như kiểm tra hỗ trợ. |
| Giao dịch cập nhật sức chứa có điều kiện trong cơ sở dữ liệu | Có thể giúp duy trì ràng buộc nhất quán nếu dùng đúng cơ chế giao dịch và dữ liệu. | Cần thiết kế transaction, isolation, lỗi cạnh tranh và kiểm thử tương ứng. |
| Đưa mọi yêu cầu qua hàng đợi xử lý tập trung | Có thể kiểm soát thứ tự xử lý và hấp thụ tải trong bối cảnh phù hợp. | Phức tạp hơn về phản hồi bất đồng bộ, retry, vận hành và tính nhất quán. |

Nhóm có thể chọn phương án giao dịch có điều kiện nếu phù hợp kiến trúc hiện tại và được kiểm chứng. Họ tự phân công người kiểm tra xử lý đồng thời, người xây giao diện báo lỗi, người viết test, người xác minh yêu cầu với sản phẩm. Không ai phải được giao từng dòng việc bởi quản lý.

Điểm quan trọng là **khả năng tranh luận và quyết định dựa trên tiêu chí**, không phải công nghệ cụ thể được chọn.

### 5.4. Tạo một Increment nhỏ nhưng hoàn tất

Nhóm chọn lát cắt từ đầu đến cuối:

1. Hiển thị các khung giờ có thể đặt.
2. Cho khách xác nhận một giờ.
3. Kiểm soát quyền truy cập và tranh chấp chỗ trống.
4. Lưu kết quả và trả trạng thái rõ ràng.
5. Kiểm thử hành vi chính, trường hợp đồng thời, tích hợp và lỗi quan trọng.

Lát cắt này đáp ứng **Definition of Done** đã thống nhất trước khi được gọi là hoàn tất. DoD có thể bao gồm kiểm thử thành công, review mã, cập nhật hợp đồng API, yêu cầu bảo mật, khả năng vận hành và tích hợp với phiên bản hiện hành.

Đội không cần hoàn thành toàn bộ bộ lọc nâng cao, thông báo đa kênh và tính năng đặt lại lịch trước khi kiểm tra giá trị của luồng đầu tiên.

### 5.5. Phản hồi làm thay đổi giải pháp

Sau khi dùng thử, nhóm nhận thấy khách ở khu vực khác thường hiểu nhầm giờ hiển thị. Họ cùng người phụ trách sản phẩm điều chỉnh thứ tự ưu tiên, bổ sung cách hiển thị múi giờ và kiểm thử liên quan.

Một quyết định khác cũng có thể xuất hiện: hệ thống quản lý lịch cũ không trả đủ dữ liệu để cập nhật theo cách ban đầu. Nhóm mời chủ sở hữu hệ thống đó cùng phân tích hợp đồng tích hợp, chứ không tự sửa giao diện chung rồi gây lỗi cho các nhóm khác.

**Giải pháp hình thành qua các vòng hợp tác, thực hiện và phản hồi**. Đây là ý nghĩa thực hành của nguyên tắc Agile số 11.

## 6. Áp dụng trong Scrum, Kanban và XP

Tự tổ chức là nguyên tắc chung; từng cách thực hành hỗ trợ nó bằng cơ chế khác nhau.

### 6.1. Trong Scrum

Theo Scrum Guide 2020, **Scrum Team** là một đơn vị liên chức năng và tự quản lý, trong đó có ba nhóm trách nhiệm:

- **Product Owner:** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. Người này làm rõ *mục tiêu/ưu tiên*, không cần chỉ đạo từng quyết định lập trình.
- **Developers:** chịu trách nhiệm tạo Increment dùng được trong mỗi Sprint và lập kế hoạch công việc để đáp ứng Sprint Goal, duy trì chất lượng theo DoD, điều chỉnh kế hoạch hằng ngày.
- **Scrum Master:** chịu trách nhiệm về hiệu quả của Scrum Team và giúp nhóm, tổ chức hiểu, áp dụng Scrum, tháo gỡ trở ngại, cải thiện hợp tác.

Khi lập **Sprint Backlog**, Developers tự lập kế hoạch để biến Product Backlog Items thành Increment hướng tới Sprint Goal. Trong **Daily Scrum**, họ kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch. **Sprint Review** cung cấp phản hồi về kết quả sản phẩm, còn **Sprint Retrospective** giúp nhóm cải thiện chất lượng và hiệu quả phối hợp.

Không nên hiểu “tự quản lý” là Product Owner không được tham gia làm rõ yêu cầu hoặc Scrum Master không được hỗ trợ quyết định khó. Vai trò rõ ràng giúp nhóm tự chủ mà vẫn duy trì mục tiêu chung.

### 6.2. Trong Kanban

Kanban làm rõ cách công việc di chuyển qua các trạng thái. Nhóm có thể cùng:

- Định nghĩa **workflow** và điều kiện để một hạng mục vào/ra từng bước.
- Giới hạn **work in progress (WIP)** để tập trung hoàn tất trước khi mở thêm việc.
- Dùng cơ chế **pull**: nhận việc mới khi có năng lực, thay vì đẩy việc vô hạn vào các cột.
- Quan sát **cycle time, throughput, work item age** và nơi xảy ra tắc nghẽn.
- Thử một thay đổi nhỏ trong cách phối hợp rồi kiểm tra kết quả.

Ví dụ, nếu công việc thường bị chờ review quá lâu, nhóm tự đề xuất review theo cặp, điều chỉnh WIP hoặc giảm kích thước hạng mục. Những thay đổi này phải tôn trọng tiêu chuẩn kỹ thuật và phụ thuộc của các nhóm liên quan.

**Kanban không bắt buộc phải chia công việc thành Sprint.** Nhóm có thể học và điều chỉnh liên tục thông qua các đợt xem xét phù hợp.

### 6.3. Với Extreme Programming (XP)

Các thực hành kỹ thuật của XP giúp quyền tự quyết mang lại phần mềm có chất lượng:

- **Pair programming / pairing:** trao đổi hiểu biết ngay lúc giải quyết vấn đề.
- **Test-driven development (TDD) khi phù hợp:** làm rõ hành vi qua chu kỳ test–code–refactor; không thay thế các mức kiểm thử khác.
- **Continuous integration:** tích hợp và kiểm tra thường xuyên để giảm rủi ro tích lũy.
- **Refactoring:** cải thiện thiết kế từng bước khi có mạng lưới kiểm thử bảo vệ.
- **Collective code ownership:** nhóm cùng chịu trách nhiệm cho mã nguồn trong những ranh giới và quy ước đã thống nhất.

Những thực hành này tạo điều kiện để **thiết kế tốt xuất hiện qua học hỏi liên tục**. Một nhóm có thể kết hợp Scrum để có nhịp kiểm tra–thích ứng, Kanban để cải thiện luồng và XP để duy trì chất lượng kỹ thuật.

## 7. Giải quyết bất đồng mà không đánh mất tự chủ

Tự tổ chức không có nghĩa mọi người luôn đồng ý. Những nhóm có chuyên môn đa dạng thường nhìn thấy các rủi ro khác nhau: backend lo tính nhất quán, frontend lo trải nghiệm, QA lo trường hợp lỗi, vận hành lo khả năng khôi phục.

Một cách xử lý bất đồng:

1. **Viết ra câu hỏi cần quyết định**: chẳng hạn “cần xử lý đặt lịch đồng thời ở đâu?”.
2. **Thống nhất các tiêu chí không thể bỏ qua**: không vượt sức chứa, bảo vệ dữ liệu cá nhân, mức tải dự kiến, giới hạn thời gian.
3. **Cho từng phương án cơ hội được trình bày ngắn gọn**, nêu bằng chứng và giả định còn thiếu.
4. **Thử nghiệm có giới hạn** khi vấn đề là kỹ thuật có thể đo được.
5. **Dùng quyền quyết định đã công bố**; nếu ảnh hưởng nhiều nhóm hoặc vượt ranh giới an toàn, tham vấn và phê duyệt theo quy định.
6. **Ghi lại lý do và cách kiểm chứng**, rồi theo dõi bằng chứng sau triển khai.

Ví dụ, hai kỹ sư tranh luận “có nên thêm cache lịch trống ngay không?”. Thay vì quyết định theo cấp bậc, nhóm đo độ trễ, khối lượng truy cập và đánh giá rủi ro dữ liệu cũ. Nếu chưa có vấn đề hiệu năng và cache làm tăng rủi ro hiển thị sai, nhóm có thể hoãn lựa chọn cho tới khi có bằng chứng cần thiết.

Nhóm cũng cần nhận ra khi bất đồng thực chất là **thiếu thẩm quyền nghiệp vụ**: kỹ sư không tự quyết cho phép khách đặt chỗ vượt sức chứa hoặc công khai dữ liệu riêng chỉ để dễ triển khai.

## 8. Những hiểu lầm và mô hình tổ chức dễ gây thất bại

| Hiểu lầm / phản mẫu | Tác động | Cách khắc phục |
| --- | --- | --- |
| **“Tự tổ chức là không cần lãnh đạo.”** | Nhóm thiếu ưu tiên, hỗ trợ và cơ chế xử lý phụ thuộc. | Lãnh đạo xác định mục tiêu, ranh giới, cấp nguồn lực và tháo gỡ trở ngại. |
| **“Nhóm được tự chủ” nhưng mọi việc đều phải chờ duyệt.** | Tự chủ hình thức, quyết định chậm, mất trách nhiệm chủ động. | Công bố loại quyết định nhóm được tự xử lý và thời điểm cần phê duyệt. |
| **Ai cũng tự chọn việc theo sở thích.** | Việc quan trọng, khó hoặc ít hấp dẫn bị bỏ lại. | Thống nhất mục tiêu, ưu tiên backlog, WIP và trách nhiệm hoàn tất. |
| **Không cần kiến trúc hoặc tiêu chuẩn chung.** | Các thành phần không tương thích, nợ kỹ thuật và rủi ro an toàn tăng. | Duy trì các nguyên tắc cấu trúc, hợp đồng và chuẩn kiểm thử cần thiết. |
| **Một chuyên gia quyết tất cả mà không lắng nghe.** | Nhóm không học, tri thức tập trung, điểm nghẽn quyết định. | Làm rõ phạm vi chuyên gia, trao đổi dữ liệu và phân phối hiểu biết. |
| **Mọi quyết định đều phải đồng thuận tuyệt đối.** | Cuộc họp kéo dài, không có ai chịu trách nhiệm quyết định. | Dùng quy tắc ra quyết định tương xứng với rủi ro, có người chịu trách nhiệm cuối cùng. |
| **Nhóm tự chủ nhưng thiếu kỹ năng và môi trường thử.** | Dễ thử sai tốn kém hoặc vẫn phải chờ hỗ trợ liên tục. | Đào tạo, pairing, xây công cụ và hỗ trợ chuyên gia. |
| **Tối ưu chỉ số của nhóm, bỏ qua hệ thống chung.** | API, dữ liệu hoặc thời gian chờ của nhóm khác bị ảnh hưởng. | Kiểm tra tác động liên nhóm và chỉ số kết quả toàn dòng giá trị. |
| **Nhận phản hồi rồi nhưng không điều chỉnh quyết định.** | Nhóm chỉ duy trì quy trình, không phát huy khả năng thích ứng. | Dùng review/retrospective và dữ liệu thực để thay đổi backlog, thiết kế, workflow. |

### 8.1. Tự chủ khác với tự cô lập

Một nhóm có khả năng tự tổ chức cần được tiếp xúc với chuyên gia lĩnh vực, bảo mật, vận hành và các nhóm liên quan. Nếu nhóm không được phép hoặc không chủ động tham vấn, họ có thể đưa ra quyết định tối ưu cục bộ nhưng gây hại cho sản phẩm chung.

Vì vậy, nhóm cần **kết nối rõ ràng với người khác**: thỏa thuận hợp đồng tích hợp, chia sẻ tiêu chuẩn, cập nhật những thay đổi ảnh hưởng lớn và đo kết quả từ góc nhìn người dùng.

### 8.2. Trao quyền tăng dần theo năng lực và rủi ro

Không phải mọi nhóm đều có sẵn cùng mức kinh nghiệm. Tổ chức có thể bắt đầu bằng các quyết định nhỏ, dễ đảo ngược; ghép cặp người ít kinh nghiệm với chuyên gia; dùng các tiêu chuẩn và ví dụ; sau đó mở rộng quyền khi nhóm chứng minh khả năng quản lý rủi ro.

Ví dụ:

- Giai đoạn đầu: nhóm tự quyết thứ tự và cách triển khai các task trong một thành phần đã có hợp đồng rõ.
- Giai đoạn tiếp theo: nhóm tự đề xuất thay đổi thiết kế bên trong dịch vụ, cung cấp test và ADR khi cần.
- Giai đoạn trưởng thành: nhóm chủ động phối hợp quyết định kiến trúc có ảnh hưởng liên nhóm, tuân thủ cơ chế phê duyệt thích hợp.

Đây là cách **xây dựng năng lực ra quyết định**, không phải tước quyền phản biện của thành viên mới.

## 9. Đo xem cách tự tổ chức có tạo ra kết quả tốt không

Không nên dùng một con số để “chấm điểm mức độ tự tổ chức” hoặc đếm số cuộc họp nhóm đã tự chủ trì. Cần kết hợp bằng chứng về giá trị sản phẩm, chất lượng, khả năng thích ứng và sức khỏe luồng công việc.

| Nhóm chỉ số / tín hiệu | Ví dụ | Cách đọc |
| --- | --- | --- |
| **Giá trị sản phẩm** | Tỷ lệ đặt lịch thành công, số cuộc gọi hỗ trợ giảm, mức hài lòng. | Sản phẩm có giải quyết vấn đề thực tế không? |
| **Chất lượng** | Lỗi sản xuất, tần suất sự cố, khả năng phục hồi, kết quả kiểm thử. | Quyết định nhóm có duy trì tính tin cậy không? |
| **Lead time / cycle time** | Thời gian từ yêu cầu đến hoàn tất; từ bắt đầu làm đến hoàn tất theo quy ước. | Có chậm trễ do chờ quyết định, chuyển giao hoặc quá nhiều việc dở không? |
| **WIP và work item age** | Số việc đang làm và tuổi các hạng mục chưa xong. | Quyền tự chủ có giúp nhóm tập trung hoàn tất và tháo gỡ vướng mắc không? |
| **Tốc độ học hỏi** | Thời gian từ giả thuyết đến phản hồi, số quyết định được điều chỉnh bởi bằng chứng. | Nhóm có thực sự kiểm tra và thích ứng không? |
| **Phụ thuộc và chờ đợi** | Thời gian chờ phê duyệt hoặc môi trường; số lần phải chuyển giao. | Tổ chức có đang cản trở quyền tự quyết không? |
| **Chia sẻ kiến thức** | Mức độ nhiều thành viên hiểu mô-đun quan trọng, khả năng tiếp tục công việc khi vắng một người. | Nhóm có bớt phụ thuộc vào một cá nhân không? |

Khi đo, cần ghi rõ **định nghĩa bắt đầu và kết thúc** của lead time/cycle time để so sánh nhất quán. Throughput hoặc số story point **không nên dùng để xếp hạng cá nhân**; chúng dễ bị ảnh hưởng bởi cách chia việc và có thể thúc đẩy hành vi sai lệch.

Một tín hiệu đáng quan tâm: nhóm giao nhiều tính năng hơn nhưng lỗi tăng, các nhóm khác liên tục phải sửa tương thích. Điều này cho thấy “tự chủ” đang tối ưu cục bộ. Ngược lại, nhóm giảm được thời gian chờ tích hợp, giao Increment nhỏ hơn và nhận phản hồi nhanh hơn trong khi chất lượng giữ ổn định là dấu hiệu tốt.

## 10. Các bước triển khai thực tế trong một nhóm mới

Có thể thử trong hai vòng làm việc hoặc một khoảng thời gian quan sát phù hợp, rồi đánh giá kết quả:

### Bước 1 — Viết rõ mục tiêu và ranh giới

Mô tả kết quả người dùng cần đạt và rủi ro quan trọng. Ghi rõ các loại quyết định nhóm tự đưa ra, quyết định phải tham vấn và những quy định không được vượt qua.

Ví dụ: “Trong hai tuần, nhóm cung cấp luồng đặt lịch dùng thử có thể kiểm chứng; nhóm tự chọn thiết kế trong dịch vụ hiện có, nhưng thay đổi hợp đồng API dùng chung phải trao đổi với chủ sở hữu tích hợp.”

### Bước 2 — Trực quan hóa công việc và phụ thuộc

Thể hiện backlog và workflow rõ ràng, đánh dấu hạng mục bị chặn bởi ai hoặc điều kiện gì. Với Kanban, cân nhắc giới hạn WIP; với Scrum, thảo luận kế hoạch đạt Sprint Goal và cập nhật hằng ngày.

### Bước 3 — Tổ chức các cuộc trao đổi có mục đích

Thay vì họp để báo cáo từng người đang làm gì cho quản lý, nhóm tập trung vào:

- Quyết định nào đang thiếu?
- Hạng mục nào cần hỗ trợ để hoàn tất?
- Rủi ro nào có thể làm Increment không đáp ứng DoD?
- Phản hồi mới có khiến kế hoạch thay đổi không?

Các cuộc họp không cần kéo dài nếu thông tin có thể xử lý trực tiếp hoặc bất đồng được giải bằng thử nghiệm ngắn.

### Bước 4 — Thử một quyết định kỹ thuật có ghi nhận

Chọn một vấn đề thực tế, đưa ra ít nhất hai phương án, đặt tiêu chí, thực hiện thử nghiệm nhỏ nếu cần và ghi ngắn lý do quyết định. Sau khi tích hợp, kiểm tra bằng kết quả sản phẩm, kiểm thử và quan sát vận hành.

### Bước 5 — Xem lại cách làm cùng kết quả

Trong buổi review, kiểm tra Increment dùng được và phản hồi từ người liên quan. Trong retrospective hoặc cuộc họp cải tiến luồng, chọn một nút thắt có thể hành động: chờ duyệt quá lâu, thiếu quyền truy cập, phụ thuộc chuyên gia hoặc hạng mục quá lớn. Đề xuất cải tiến có người chịu trách nhiệm và cách kiểm tra hiệu quả.

Nếu giải pháp tốt nhưng thời gian chờ phê duyệt quá dài, vấn đề nằm một phần ở **cơ chế tổ chức**, không thể chỉ yêu cầu kỹ sư “chủ động hơn”.

## 11. Bài tập tình huống và câu hỏi tự kiểm tra

### Tình huống A — Hai phương án cùng có lý

Nhóm cần thêm thông báo xác nhận đặt lịch. Một người đề xuất gửi ngay trong request tạo lịch để đơn giản; người khác muốn dùng hàng đợi để không làm chậm phản hồi khi dịch vụ thông báo gặp sự cố.

**Câu hỏi:**

1. Nhóm cần làm rõ những yêu cầu và rủi ro nào trước khi chọn?
2. Ai cần được tham vấn?
3. Thử nghiệm nào cung cấp bằng chứng hữu ích?
4. Quyết định này có thể tự xử lý trong nhóm hay ảnh hưởng hợp đồng chung?

**Gợi ý phân tích:** làm rõ yêu cầu xác nhận có nhất thiết tức thời không, xử lý retry và thông báo trùng ra sao, mức tải và độ tin cậy mong muốn. Trao đổi với người phụ trách sản phẩm và đơn vị vận hành; đo độ trễ, kiểm tra tình huống dịch vụ thông báo không khả dụng. Nếu dùng hạ tầng thông báo chung, cần phối hợp chủ sở hữu. Có thể ra quyết định có điều kiện theo kết quả thử nghiệm thay vì theo sở thích công nghệ.

### Tình huống B — Trao quyền nhưng vẫn phải xin phép

Ban quản lý nói “đội tự tổ chức”, song để thêm một test tự động, đổi thứ tự hai hạng mục nhỏ hoặc sửa một component nội bộ, nhóm đều phải được ba cấp phê duyệt. Mỗi yêu cầu duyệt chờ từ một đến ba ngày.

**Câu hỏi:** vấn đề nào thuộc nhóm, vấn đề nào thuộc tổ chức? Bạn đề xuất thay đổi gì có thể kiểm chứng?

**Gợi ý:** nhóm có thể chuẩn hóa test, tăng chất lượng đề xuất và chia sẻ minh bạch kết quả. Tổ chức cần xem lại quyền quyết định, loại bỏ bước duyệt không liên quan rủi ro và xác định tiêu chí cần phê duyệt. Có thể thí điểm trao quyền cho quyết định nội bộ dễ đảo ngược, theo dõi thời gian chờ, lỗi và chất lượng trong một vài vòng làm việc.

### Tình huống C — Tự chủ gây ra xung đột tích hợp

Hai nhóm tự tối ưu API theo nhu cầu riêng. Nhóm A đổi tên trường dữ liệu đang được nhóm B sử dụng, khiến chức năng của B lỗi sau triển khai. Cả hai đều cho rằng mình đã “làm đúng tinh thần Agile”.

**Câu hỏi:** ranh giới nào chưa rõ, và nhóm có thể duy trì quyền tự chủ mà vẫn bảo vệ hệ thống chung thế nào?

**Gợi ý:** cần hợp đồng API, quy tắc tương thích, thông báo thay đổi, kiểm thử hợp đồng hoặc phối hợp với chủ sở hữu giao diện chung. Quyết định có ảnh hưởng liên nhóm phải được xem xét ở cấp phối hợp tương xứng; trong phạm vi nội bộ, các nhóm vẫn có thể tự chọn chi tiết triển khai.

### Câu hỏi ghi nhớ

1. Vì sao việc giao “mục tiêu” tạo điều kiện tự tổ chức tốt hơn việc giao chi tiết từng thao tác?
2. Điểm khác nhau giữa *self-organizing*, *self-managing* và *cross-functional* là gì?
3. Khi nào quyết định thiết kế nên nằm trong nhóm, khi nào cần phối hợp hoặc phê duyệt?
4. Vì sao cần Definition of Done, kiểm thử và phản hồi để kiến trúc “hình thành” theo hướng tốt?
5. Scrum, Kanban và XP mỗi cách hỗ trợ tự tổ chức bằng những thực hành nào?
6. Nếu nhóm bàn giao nhanh hơn nhưng tăng lỗi liên nhóm, cần xem lại điều gì?

## 12. Tổng kết

Nguyên tắc Agile số 11 nhấn mạnh rằng **giải pháp tốt được hình thành khi người trực tiếp xây dựng sản phẩm có khả năng phối hợp, quyết định và học hỏi cùng nhau**. Để làm được điều đó, tổ chức cần cung cấp **mục tiêu rõ, quyền hạn tương xứng, năng lực đa chuyên môn, thông tin, sự tin cậy và cơ chế xử lý rủi ro**.

Tự tổ chức không xóa vai trò của quản lý, Product Owner, chuyên gia hay tiêu chuẩn kiến trúc. Các vai trò đó giúp nhóm nhìn thấy mục tiêu, hiểu giới hạn, nhận phản hồi nhanh và xử lý những vấn đề ngoài phạm vi tự quyết.

Trong phát triển phần mềm Agile, kết quả cuối cùng phải được kiểm chứng qua **Increment hoạt động được, giá trị người dùng, chất lượng và khả năng thay đổi**. Nhóm tự tổ chức hiệu quả là nhóm không chỉ ra quyết định nhanh, mà còn **chịu trách nhiệm cho tác động của quyết định và liên tục cải thiện dựa trên bằng chứng**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa ngắn |
| --- | --- |
| **Self-organizing team** | Nhóm chủ động điều phối và chọn cách giải quyết công việc để đạt mục tiêu. |
| **Self-managing team** | Nhóm chủ động quản lý công việc nội bộ trong phạm vi trách nhiệm và quyền hạn. |
| **Cross-functional team** | Nhóm có đủ hoặc tiếp cận đủ năng lực cần thiết để tạo giá trị. |
| **Emergent design/architecture** | Thiết kế/kiến trúc được hình thành và điều chỉnh dần nhờ thực hành, kiểm chứng và phản hồi. |
| **Decision boundary** | Ranh giới xác định loại quyết định nào nhóm được tự thực hiện và loại nào cần phối hợp/phê duyệt. |
| **ADR** | Bản ghi ngắn về quyết định kiến trúc, bối cảnh, lý do và hệ quả. |
| **Product Backlog** | Danh sách công việc hướng tới cải thiện sản phẩm, được sắp xếp và điều chỉnh theo nhu cầu. |
| **Definition of Done** | Tiêu chuẩn chất lượng chung để xác định phần tăng trưởng đã hoàn tất. |
| **Increment** | Phần sản phẩm tăng thêm, tích hợp với phần trước, có thể sử dụng và đáp ứng DoD. |
| **WIP** | Công việc đang thực hiện nhưng chưa hoàn tất; quản lý WIP giúp giảm phân tán và chờ đợi. |

