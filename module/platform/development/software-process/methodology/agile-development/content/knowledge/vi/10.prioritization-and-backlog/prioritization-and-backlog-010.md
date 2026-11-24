# Giữ một nguồn công việc rõ ràng khi nhiều bên cùng đề xuất

Một sản phẩm phần mềm hiếm khi chỉ có một người đề xuất công việc. Người dùng muốn bớt thao tác; bộ phận kinh doanh muốn thêm chức năng bán hàng; chăm sóc khách hàng muốn sửa điểm gây khiếu nại; vận hành cần khắc phục sự cố; đội kỹ thuật cần giảm rủi ro bảo mật và cải thiện khả năng bảo trì. Mỗi đề xuất có thể hợp lý trong góc nhìn riêng, nhưng **nhóm không thể thực hiện tất cả cùng một lúc**.

Nếu công việc nằm rải rác trong email, tin nhắn, bảng tính của từng phòng ban và danh sách riêng của lập trình viên, đội phát triển dễ gặp ba vấn đề:

1. **Không biết đâu là ưu tiên chung.** Hai bên cùng tuyên bố việc của mình là “gấp nhất”.
2. **Không thấy toàn bộ nhu cầu và giới hạn năng lực.** Việc mới được chen vào trong khi những hạng mục đã bắt đầu còn dang dở.
3. **Không theo dõi được quyết định.** Người đề xuất không biết ý tưởng đã được ghi nhận, chấp nhận, trì hoãn hay bác bỏ vì lý do gì.

Giải pháp theo tinh thần Agile là duy trì **một nguồn công việc có thẩm quyền, minh bạch, được làm rõ và sắp thứ tự**, trong đó đề xuất của nhiều bên được xem xét theo mục tiêu sản phẩm và bằng chứng thực tế. Trong **Scrum**, **Product Backlog** chính là danh sách công việc cần thiết để cải thiện sản phẩm, được sắp thứ tự và liên tục phát triển; Scrum Guide mô tả đây là **nguồn công việc duy nhất mà Scrum Team thực hiện**. Với nhóm dùng Kanban hoặc phương thức phối hợp khác, nguyên tắc tương tự có thể được hiện thực qua một luồng tiếp nhận và bảng công việc với chính sách rõ ràng.

Bài học thuộc chương **Ưu tiên và backlog** của mô-đun **AGILE_DEVELOPMENT**. Nội dung kết nối Product Goal, Product Backlog, user story, refinement, Scrum, Kanban, vòng phản hồi và các chỉ số dòng công việc để giúp nhóm chọn **điều đáng làm tiếp**, giải thích quyết định và thích ứng khi có thông tin mới.

## 1. Hiểu đúng “một nguồn công việc”

**Một nguồn công việc rõ ràng** là nơi mọi người có thể tra cứu các hạng mục được nhóm sản phẩm quản lý, xem **mục đích, thứ tự, trạng thái và quyết định** theo cách nhất quán. Nó cung cấp câu trả lời đáng tin cho các câu hỏi:

- Sản phẩm đang hướng tới mục tiêu gì?
- Đề xuất của tôi đã được tiếp nhận và ai đang xem xét?
- Hạng mục nào đang được ưu tiên, và vì sao?
- Việc nào đang làm, bị chặn, đã hoàn thành hoặc chưa được chọn?
- Thay đổi mới ảnh hưởng thế nào tới những việc đã cam kết?
- Khi nào nhóm có thể kiểm chứng kết quả và điều chỉnh backlog?

Điều này **không có nghĩa** mọi trao đổi, nhật ký kỹ thuật, tài liệu thiết kế, sự cố và ý tưởng đều phải nằm trong một tệp duy nhất. Nhóm có thể dùng các công cụ chuyên biệt; điều cần giữ là **một bản ghi có thẩm quyền về thứ tự và trạng thái công việc**, các hệ thống khác liên kết đến bản ghi đó thay vì tạo danh sách ưu tiên cạnh tranh.

| Khái niệm | Vai trò | Điều dễ nhầm |
| --- | --- | --- |
| **Kênh tiếp nhận** | Nơi người dùng, kinh doanh, hỗ trợ hoặc kỹ thuật gửi đề xuất | Mỗi kênh tự cấp quyền ưu tiên và giao việc trực tiếp |
| **Hộp ý tưởng / yêu cầu cần xem xét** | Giữ thông tin đầu vào chưa xác minh hoặc chưa quyết định | Mọi ý tưởng ở đây đều mặc nhiên là việc phải làm |
| **Product Backlog** | Danh sách hạng mục cần thiết để cải thiện sản phẩm, được làm rõ và sắp thứ tự | Một danh sách bất biến hoặc tập hợp mọi mong muốn không phân biệt |
| **Sprint Backlog** | Trong Scrum, gồm Sprint Goal, các Product Backlog Item được chọn và kế hoạch thực hiện | Nơi các bên liên quan tự thêm việc vào giữa Sprint |
| **Bảng công việc / workflow** | Thể hiện hạng mục đang ở bước nào và đang chờ điều gì | Một danh sách ưu tiên thứ hai không đồng bộ với Product Backlog |
| **Nhật ký quyết định / tài liệu liên quan** | Ghi bối cảnh và lý do của lựa chọn quan trọng | Nguồn ưu tiên riêng biệt, không có liên kết đến hạng mục |

Một Product Backlog có thể chứa **tính năng, lỗi, cải tiến chất lượng, nghiên cứu, công việc kỹ thuật, bảo mật và giảm rủi ro**. Những việc này không nhất thiết phải được viết dưới dạng user story. Giá trị của chúng có thể là trải nghiệm tốt hơn hoặc khả năng tạo giá trị ổn định trong tương lai.

### Nguồn công việc rõ ràng không phải “hàng đợi FIFO”

**FIFO (first in, first out)** nghĩa là yêu cầu gửi trước được xử lý trước. Cách này có thể phù hợp với một số loại tác vụ đơn giản, nhưng **Product Backlog được sắp thứ tự theo quyết định về giá trị, rủi ro, mục tiêu và bối cảnh**. Một lỗi làm mất tiến độ học tập có thể cần được xử lý trước một đề xuất giao diện đã gửi từ lâu.

“Được ghi nhận” cũng không đồng nghĩa “được lên lịch”. Người đề xuất cần biết yêu cầu đang ở bước nào, nhưng nhóm phải có quyền cân nhắc và chọn công việc phù hợp với năng lực.

## 2. Khi nhiều bên cùng đề xuất, xung đột đến từ đâu?

Giả sử một nền tảng học trực tuyến đang hướng tới mục tiêu: **học viên mới có thể dễ dàng bắt đầu và hoàn thành bài học đầu tiên**. Trong cùng một tuần, nhiều yêu cầu xuất hiện:

| Người đề xuất | Đề xuất | Lý do từ góc nhìn của họ |
| --- | --- | --- |
| Bộ phận kinh doanh | Làm trang mã giảm giá cho khóa học | Muốn tăng đăng ký trả phí |
| Marketing | Thêm hiệu ứng động cho trang giới thiệu | Muốn tăng hấp dẫn khi chạy chiến dịch |
| Chăm sóc học viên | Sửa lỗi mất tiến độ khi mạng chập chờn | Học viên phải học lại và gửi khiếu nại |
| Nhóm nội dung | Gợi ý bài khởi đầu theo trình độ | Người mới khó biết nên học gì |
| Nhóm kỹ thuật | Cải thiện xử lý đăng nhập và phiên làm việc | Đã có rủi ro bảo mật hoặc lỗi phiên cần giải quyết |
| Người quản lý sản phẩm | Đo tỷ lệ bắt đầu và hoàn thành bài đầu | Chưa đủ dữ liệu để xác định điểm gây bỏ dở |

Không nên kết luận một bên “đúng” và bên khác “sai” chỉ từ tên phòng ban. Xung đột xuất hiện vì mỗi bên đang tối ưu **một mục tiêu cục bộ**. Nhiệm vụ quản lý sản phẩm là liên kết đề xuất với **Product Goal**, hiểu tác động tới người dùng, xem bằng chứng, rủi ro và chi phí cơ hội để quyết định thứ tự chung.

**Chi phí cơ hội** là giá trị mà nhóm phải trì hoãn khi chọn làm một hạng mục khác. Nếu nhóm dành hai tuần cho hiệu ứng trang giới thiệu, điều đó cũng có thể nghĩa là lỗi mất tiến độ tiếp tục ảnh hưởng học viên trong hai tuần ấy.

### Quy tắc quan trọng: mọi ý kiến đều có đường vào, không phải ý kiến nào cũng có quyền xếp thứ tự

Tạo điều kiện để các bên gửi đề xuất, kèm vấn đề và bằng chứng, nhưng **quyền quyết định thứ tự công việc phải rõ ràng**. Nhóm không nên phải đoán xem yêu cầu nào có hiệu lực chỉ vì nó đến từ người có chức vụ cao hoặc được nhắc đi nhắc lại nhiều lần.

## 3. Product Owner và các bên liên quan có trách nhiệm gì?

Trong Scrum, **Product Owner là một người chịu trách nhiệm (accountable) tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả**. Trách nhiệm quản lý gồm phát triển, truyền đạt Product Goal, tạo và truyền đạt rõ Product Backlog Item, sắp thứ tự và bảo đảm backlog minh bạch, dễ hiểu. Product Owner có thể giao người khác thực hiện một phần công việc quản lý nhưng **vẫn chịu trách nhiệm cuối cùng**.

Product Owner **không cần biết mọi vấn đề một mình**. Họ cần lắng nghe stakeholder, sử dụng dữ liệu và hợp tác với Developers để hiểu rủi ro, khả năng triển khai và các lựa chọn. Trong Scrum, tổ chức cần tôn trọng quyết định về nội dung và thứ tự của Product Backlog, thay vì liên tục thay thế chúng qua các kênh chỉ đạo khác.

| Vai trò / góc nhìn | Đóng góp | Điều cần rõ |
| --- | --- | --- |
| **Người dùng và khách hàng** | Khó khăn, hành vi thực tế, phản hồi khi sử dụng | Phản hồi cần được kiểm chứng; đề xuất giải pháp chưa chắc là nhu cầu gốc |
| **Stakeholder kinh doanh / marketing / vận hành** | Mục tiêu, cơ hội, ràng buộc và hệ quả của việc trì hoãn | Có thể đề xuất và trao đổi đánh đổi, không tự động áp thứ tự lên nhóm |
| **Product Owner** | Duy trì mục tiêu, xem xét giá trị và sắp thứ tự Product Backlog | Là đầu mối chịu trách nhiệm trong Scrum |
| **Developers** | Đánh giá khả năng, phụ thuộc, ước lượng, chất lượng và giải pháp kỹ thuật | Được tham gia làm rõ và đề xuất thay đổi, không chỉ nhận lệnh |
| **Người kiểm thử, bảo mật, vận hành** | Rủi ro, ví dụ kiểm chứng, sự cố và tiêu chuẩn cần tuân thủ | Rủi ro bắt buộc cần được đưa vào quyết định kịp thời |
| **Scrum Master** | Hỗ trợ Scrum Team và tổ chức áp dụng Scrum hiệu quả, cải thiện phối hợp | Không thay Product Owner quyết định thứ tự Product Backlog |

### Ai có quyền phê duyệt những ràng buộc bắt buộc?

Ưu tiên sản phẩm không thay thế cơ chế thẩm quyền ở các lĩnh vực như bảo mật, quyền riêng tư, pháp lý hoặc chính sách thương mại. Nếu một đề xuất có thể vi phạm ràng buộc bắt buộc, người có chuyên môn và thẩm quyền liên quan cần tham gia quyết định.

Điều tốt nhất là ghi rõ **quyết định sản phẩm** và **quyết định kiểm soát rủi ro**, để tránh hai hiểu lầm: Product Owner có thể tự bỏ qua quy định, hoặc mọi thay đổi nhỏ đều phải qua một chuỗi phê duyệt không cần thiết.

## 4. Thiết kế luồng tiếp nhận tập trung, từ đề xuất đến quyết định

Một quy trình tiếp nhận có thể đơn giản nhưng nhất quán:

~~~mermaid
flowchart TD
    A["Đề xuất từ người dùng / các phòng ban / kỹ thuật"] --> B["Điểm tiếp nhận chung"]
    B --> C["Ghi vấn đề, bối cảnh, bằng chứng"]
    C --> D{"Có đủ để hiểu và phân loại?"}
    D -->|Chưa| E["Hỏi thêm / quan sát / kiểm chứng"]
    E --> D
    D -->|Có| F["Xem mục tiêu, giá trị, rủi ro, chi phí"]
    F --> G{"Quyết định"}
    G -->|Chọn để theo dõi và ưu tiên| H["Product Backlog được sắp thứ tự"]
    G -->|Chưa phù hợp| I["Ghi lý do và phản hồi"]
    G -->|Cần học thêm| E
    H --> J["Refinement / chọn công việc / bàn giao"]
    J --> K["Kiểm chứng kết quả và điều chỉnh backlog"]
    K --> F
~~~

**Điểm tiếp nhận chung** có thể là một biểu mẫu, một nhãn ticket, kênh hỗ trợ có đồng bộ hoặc một bảng ý tưởng gắn với backlog. Không nhất thiết buộc người dùng tự tạo Product Backlog Item trong công cụ của Developers. Điều cốt lõi là **không làm mất đề xuất và không tạo nguồn ưu tiên song song**.

### Tối thiểu cần ghi gì khi nhận đề xuất?

| Trường | Mục đích | Ví dụ |
| --- | --- | --- |
| **Mã tham chiếu** | Tra cứu và tránh trùng lặp | IDEA-024 |
| **Người gửi / đầu mối** | Hỏi thêm và phản hồi kết quả | Nhóm hỗ trợ học viên |
| **Vấn đề và người bị ảnh hưởng** | Tránh nhầm giải pháp với nhu cầu | Học viên mất tiến độ khi mạng gián đoạn |
| **Bằng chứng hiện có** | Hiểu mức độ tin cậy | Ba ticket hỗ trợ, log lỗi, khả năng tái hiện |
| **Tác động nếu chờ** | Nhận biết sự khẩn cấp và hậu quả | Học viên phải làm lại bài; có thể mất niềm tin |
| **Mục tiêu liên quan** | Gắn đề xuất với Product Goal | Hoàn thành bài học đầu tiên đáng tin cậy |
| **Trạng thái và quyết định** | Biết đề xuất đang ở đâu | Cần làm rõ / Được đưa vào backlog / Hoãn |
| **Liên kết đến PBI / quyết định** | Giữ dấu vết mà không chép dữ liệu nhiều nơi | PBI-108, DEC-012 |

Các trường này chỉ là **gợi ý**. Khi thu thập thông tin, cần tuân thủ giới hạn quyền truy cập và tránh sao chép dữ liệu cá nhân nhạy cảm từ ticket hỗ trợ vào backlog rộng quyền xem.

### Xử lý yêu cầu trùng và đề xuất mâu thuẫn

Nếu nhiều người cùng báo “tiến độ không lưu”, nhóm nên gộp hoặc liên kết những báo cáo tương đương vào **một vấn đề gốc**, vẫn giữ số lượng và hoàn cảnh phát sinh để đánh giá mức độ ảnh hưởng. Tránh tạo năm story gần giống nhau chỉ vì năm người gửi.

Nếu hai đề xuất trái nhau — ví dụ “tự động phát video bài tiếp theo” và “không bao giờ tự phát video” — hãy tìm **nhu cầu và bối cảnh**: người dùng di động có dữ liệu giới hạn có thể có ưu tiên khác người đang học trên máy tính. Có thể phải thử lựa chọn tùy chỉnh hoặc kiểm chứng theo nhóm thay vì chọn bên gửi yêu cầu có tiếng nói lớn hơn.

## 5. Phân biệt ý tưởng, vấn đề được xác nhận và việc đã cam kết

Một nguồn rõ ràng cần ngăn việc **đề xuất biến thành cam kết một cách vô thức**.

| Mức | Ý nghĩa | Điều nhóm có thể nói với người đề xuất |
| --- | --- | --- |
| **Đã nhận** | Hệ thống đã ghi nhận đầu vào | “Chúng tôi đã tiếp nhận và có mã theo dõi.” |
| **Cần tìm hiểu** | Vấn đề hoặc bằng chứng chưa rõ | “Chúng tôi đang kiểm tra trường hợp và mức ảnh hưởng.” |
| **Đã đánh giá** | Đã xem xét mục tiêu, giá trị, rủi ro và chi phí cơ hội | “Đề xuất có ích nhưng hiện ưu tiên những vấn đề khác.” |
| **Trong Product Backlog** | Được quản lý như công việc cần cải thiện sản phẩm, có thứ tự tương đối | “Đã ghi trong backlog; thứ tự có thể đổi khi có thông tin mới.” |
| **Được chọn thực hiện** | Nhóm đã chọn theo cách lập kế hoạch phù hợp | “Đang thực hiện trong phạm vi mục tiêu hiện tại.” |
| **Đã bàn giao / đang kiểm chứng** | Có kết quả cần đo hoặc phản hồi | “Phần mềm đã thay đổi; chúng tôi đang xem tác động thực tế.” |
| **Không theo đuổi hiện tại** | Có quyết định chưa làm hoặc không làm | “Lý do là ...; có thể xem lại khi điều kiện thay đổi.” |

Đây là **mô hình trạng thái gợi ý**, không phải một workflow chuẩn của Scrum. Trong thực hành, một ý tưởng chưa đủ căn cứ có thể ở nơi tiếp nhận trước khi trở thành Product Backlog Item; nhóm cần **liên kết và có đường tra cứu** giữa nơi tiếp nhận với backlog.

**Một Product Backlog Item được đưa vào backlog không đồng nghĩa với lời hứa về ngày bàn giao.** Thời gian dự kiến chỉ nên trao đổi khi có căn cứ về phạm vi, năng lực, phụ thuộc và mức độ bất định.

## 6. Duy trì thứ tự ưu tiên minh bạch, thay vì coi mọi việc là “P0”

Product Owner có thể xem xét các chiều sau khi quyết định:

1. **Giá trị đối với người dùng và Product Goal:** Hạng mục giúp nhóm tiến gần kết quả nào?
2. **Mức độ ảnh hưởng và rủi ro:** Có gây mất dữ liệu, sự cố bảo mật, lỗi thanh toán hoặc phá vỡ chức năng chính không?
3. **Mức độ khẩn cấp theo thời gian:** Có hạn chót bắt buộc hay cơ hội chỉ tồn tại trong thời gian ngắn?
4. **Bằng chứng và độ chắc chắn:** Có dữ liệu, tình huống đã tái hiện hoặc chỉ có suy đoán?
5. **Chi phí, kích thước và phụ thuộc:** Có thể tạo lát cắt nhỏ hoặc kiểm chứng rẻ trước khi đầu tư lớn không?
6. **Sức khỏe dòng công việc:** Nếu bắt đầu mục này, việc đang làm nào bị kéo dài hoặc thiếu người xử lý?

Không có một phép cộng điểm nào tự động quyết định đúng thứ tự cho mọi sản phẩm. **Đặt ưu tiên là một quyết định về đánh đổi**, cần được giải thích và cập nhật khi bối cảnh thay đổi.

### Ví dụ cùng một backlog của nền tảng học trực tuyến

Giả sử nhóm ghi nhận các hạng mục sau; mọi mức đánh giá chỉ là **giả định minh họa**:

| ID | Hạng mục | Giá trị / rủi ro | Bằng chứng | Lựa chọn trước mắt |
| --- | --- | --- | --- | --- |
| PBI-101 | Sửa lỗi mất tiến độ sau khi mạng gián đoạn | Tác động trực tiếp đến khả năng hoàn thành bài; nguy cơ mất dữ liệu | Có lỗi tái hiện và phản hồi hỗ trợ | Điều tra và xử lý sớm |
| PBI-102 | Làm rõ nút “Bắt đầu bài đầu tiên” | Gắn Product Goal; có thể giảm bỏ dở | Quan sát một số học viên không tìm được đường vào bài | Thử bản mẫu/lát cắt nhỏ |
| PBI-103 | Bổ sung sự kiện đo hoàn thành bài | Giúp kiểm chứng kết quả thay vì suy đoán | Thiếu dữ liệu hiện tại | Thực hiện đủ sớm để đo thay đổi |
| PBI-104 | Gợi ý khóa học bằng AI trên toàn bộ danh mục | Cơ hội chưa được xác minh; chi phí lớn và phụ thuộc dữ liệu | Mới là đề xuất | Kiểm chứng nhu cầu bằng cách rẻ hơn |
| PBI-105 | Trang quản lý mã giảm giá nâng cao | Có thể tạo doanh thu, nhưng liên hệ Product Goal hiện tại chưa rõ | Ước tính của kinh doanh, chưa có thử nghiệm | Tiếp tục làm rõ, cân nhắc thời điểm |
| PBI-106 | Khắc phục điểm yếu truy cập dữ liệu học viên | Rủi ro bảo mật có thể nghiêm trọng | Có phát hiện kỹ thuật cần xác minh và xử lý theo mức độ | Đánh giá khẩn cấp với đầu mối bảo mật |

**Không nên suy từ thứ tự trình bày trong bảng ra thứ tự ưu tiên đã được chốt.** Nếu PBI-106 là rủi ro nghiêm trọng đã được xác thực, việc xử lý có thể vượt lên trên các cải tiến tính năng. Nếu chỉ là cảnh báo chưa được xác minh, bước tiếp theo là kiểm tra mức độ tác động. Nếu PBI-101 làm mất tiến độ học tập, nó có thể cần được ưu tiên trước trang mã giảm giá ngay cả khi giá trị tài chính của trang ấy hấp dẫn.

### Sử dụng điểm số như công cụ trao đổi, không thay quyền phán đoán

Một số nhóm dùng phương pháp định lượng như RICE (Reach, Impact, Confidence, Effort) hoặc mô hình điểm số do họ thống nhất. Điều hữu ích là **làm lộ giả định đang nằm sau thứ tự**: phạm vi ảnh hưởng bao nhiêu người, hiệu quả kỳ vọng, độ tin cậy, công sức.

Nhưng điểm số có giới hạn:

- Các ước lượng dựa trên ít bằng chứng có thể tạo cảm giác chính xác giả.
- Những ràng buộc bảo mật, pháp lý hoặc vận hành nghiêm trọng **không nên bị hạ ưu tiên chỉ vì thiếu điểm “reach”**.
- Một hạng mục chỉ có thể bắt đầu sau khi xử lý phụ thuộc cần thiết.
- Các chỉ số được tính ở những kỳ khác nhau không nên so sánh như thể cùng độ tin cậy.

Do đó, hãy ghi **lý do quyết định, giả định quan trọng và điều kiện xem lại**. Điểm số có thể hỗ trợ cuộc trao đổi nhưng không tự chịu trách nhiệm về kết quả.

## 7. Refinement giúp backlog rõ ràng và có thể hành động

**Product Backlog refinement** là hoạt động liên tục làm rõ và chia nhỏ Product Backlog Item. Nó có thể bổ sung mô tả, điều kiện chấp nhận, thứ tự, kích thước và thông tin cần thiết. Đây không phải một nghi thức bắt buộc với thời lượng cố định trong Scrum Guide.

Mỗi lần refinement nên giúp nhóm trả lời:

- Người dùng hoặc hệ thống đang gặp vấn đề cụ thể nào?
- Hạng mục gắn với Product Goal hay rủi ro bắt buộc nào?
- Nhóm biết gì và vẫn đang giả định điều gì?
- Có thể chia nhỏ để giao phần giá trị có thể kiểm chứng sớm không?
- Có quy tắc nghiệp vụ, dữ liệu, phụ thuộc kỹ thuật hoặc ngoại lệ nào phải làm rõ?
- Có tiêu chí chấp nhận và cách kiểm chứng phù hợp chưa?

### Ví dụ chuyển đề xuất thành user story

Đề xuất từ chăm sóc học viên:

> “Cần có nút lưu tiến độ thật nổi bật vì học viên thường mất bài.”

Sau khi tìm hiểu, nhóm phát hiện một số phiên học **không lưu tiến độ khi mạng gián đoạn**. Vấn đề gốc là độ tin cậy của việc lưu, không nhất thiết là kích thước nút.

**User story có thể được làm rõ:**

> Là học viên đang học dở một bài, tôi muốn tiến độ đã được lưu có thể khôi phục khi quay lại, để không phải học lại những phần đã hoàn thành.

**Tiêu chí chấp nhận minh họa:**

1. Khi hệ thống xác nhận đã lưu tiến độ, học viên có thể mở lại bài và thấy vị trí đã được ghi nhận.
2. Khi mạng mất trước lúc lưu thành công, giao diện không báo “đã lưu” sai.
3. Sau khi kết nối được phục hồi, hệ thống xử lý thử lại theo quy tắc đã thống nhất, tránh ghi đè dữ liệu mới hơn bằng dữ liệu cũ.
4. Người học được thông báo rõ khi tiến độ chưa được đồng bộ.

Nếu yêu cầu liên quan đến nhiều thiết bị hoặc đồng bộ offline phức tạp, nhóm cần làm rõ cách xử lý xung đột trước khi cam kết khả năng ấy. Các kiểm thử kỹ thuật có thể chứng minh hành vi lưu/khôi phục, còn phản hồi người học giúp kiểm chứng trải nghiệm và giá trị.

### Dùng INVEST để hỏi về chất lượng story

| Chữ | Câu hỏi khi refinement |
| --- | --- |
| **I – Independent** | Có thể bàn giao và kiểm chứng hạng mục với ít phụ thuộc không cần thiết không? |
| **N – Negotiable** | Mục tiêu đã rõ, còn không gian thương lượng cách làm không? |
| **V – Valuable** | Hạng mục tạo giá trị hoặc giảm rủi ro cho ai, theo mục tiêu nào? |
| **E – Estimable** | Nhóm hiểu đủ để ước lượng hữu ích hoặc cần kiểm chứng bất định trước? |
| **S – Small** | Lát cắt có đủ nhỏ để hoàn thành và nhận phản hồi trong kỳ phù hợp không? |
| **T – Testable** | Có ví dụ và bằng chứng đủ để đánh giá đạt/chưa đạt không? |

INVEST là **hướng dẫn thảo luận cho user story**, không phải điều kiện bắt buộc mọi Product Backlog Item đều phải viết thành story. Một hoạt động nghiên cứu kỹ thuật có thể cần đầu ra là **bằng chứng và quyết định**, còn một hạng mục bảo mật có thể mang giá trị giảm rủi ro.

## 8. Kết nối Product Backlog, Sprint Backlog và công việc đang làm

Trong Scrum, mỗi artifact có mục đích và commitment riêng:

| Artifact | Commitment | Vai trò |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Hướng đi dài hạn và công việc cần cải thiện sản phẩm |
| **Sprint Backlog** | **Sprint Goal** | Mục tiêu Sprint, các PBI được chọn và kế hoạch của Developers |
| **Increment** | **Definition of Done** | Kết quả sản phẩm đạt tiêu chuẩn chất lượng |

**Sprint Planning** sử dụng Product Backlog để Scrum Team thảo luận vì sao Sprint có giá trị, mục tiêu Sprint, những gì có thể thực hiện và cách tạo Increment. Developers chọn Product Backlog Item cho Sprint thông qua thảo luận với Product Owner; Developers chịu trách nhiệm về kế hoạch triển khai trong Sprint Backlog.

### Khi stakeholder gửi yêu cầu mới giữa Sprint

Không nên để một phòng ban tự gán việc vào Sprint Backlog chỉ vì yêu cầu vừa xuất hiện. Nhóm cần:

1. Ghi nhận và hiểu vấn đề, mức ảnh hưởng và bằng chứng.
2. Phân biệt yêu cầu quan trọng với sự cố hoặc rủi ro buộc phải xử lý ngay.
3. Trao đổi với Product Owner và Developers về tác động đến Sprint Goal, năng lực và công việc đang làm.
4. Nếu phù hợp, cập nhật Product Backlog và chọn thời điểm thực hiện; nếu cần thay đổi phạm vi Sprint, Developers thương lượng với Product Owner trong khi giữ Sprint Goal không bị ảnh hưởng.
5. Minh bạch thay đổi cho người liên quan, kể cả công việc nào bị trì hoãn.

Trong Scrum, **Sprint Goal tạo sự tập trung**, nhưng không có nghĩa nhóm phải bỏ qua sự cố nghiêm trọng chỉ vì không nằm trong kế hoạch đầu Sprint. Khi Sprint Goal không còn phù hợp với hoàn cảnh, **chỉ Product Owner có quyền hủy Sprint**.

### Bảo vệ công việc đang làm khỏi luồng yêu cầu ngầm

Một ví dụ thường gặp: lập trình viên nhận yêu cầu trực tiếp qua tin nhắn và “làm giúp cho nhanh”, nhưng backlog vẫn ghi họ đang hoàn thành story khác. Sau vài ngày, nhóm tưởng chậm tiến độ do năng suất thấp, trong khi thực tế công sức đã chuyển sang việc không được ghi nhận.

Cần có nguyên tắc: **việc ảnh hưởng tới khả năng bàn giao, mức ưu tiên hoặc năng lực phải được nhìn thấy trong nguồn công việc chung**. Câu hỏi kỹ thuật nhỏ hoặc trao đổi hỗ trợ vẫn có thể xử lý ngay theo cách nhóm thống nhất, nhưng không nên để một hạng mục đủ lớn trở thành “dự án bí mật”.

## 9. Kanban: một luồng nhìn thấy được và chính sách xử lý rõ ràng

Nhóm sử dụng Kanban không bắt buộc có Sprint hay Sprint Backlog theo Scrum. Họ vẫn cần **đường vào công việc rõ**, **thứ tự hoặc chính sách chọn việc**, **giới hạn WIP** và **các trạng thái phản ánh công việc thực tế**.

Ví dụ luồng:

~~~text
Đề xuất / Phản hồi
       ↓
Tiếp nhận → Làm rõ → Đã chọn theo thứ tự → Sẵn sàng
                                               ↓
                                         Đang phát triển
                                               ↓
                                       Review / Kiểm thử
                                               ↓
                                        Đã bàn giao
                                               ↓
                                    Quan sát và học hỏi
~~~

Một số nhóm giữ vùng khám phá và vùng thực hiện trên hai bảng khác nhau để dễ quản lý, nhưng cần **liên kết hạng mục và quy tắc chuyển giao** để không tạo hai danh sách ưu tiên đối lập.

### Chính sách minh bạch của một workflow

| Điểm quyết định | Chính sách mẫu |
| --- | --- |
| **Từ tiếp nhận sang làm rõ** | Có mô tả vấn đề, người bị ảnh hưởng, đầu mối và bằng chứng sơ bộ |
| **Từ làm rõ sang sẵn sàng** | Đã xác định giá trị, điều kiện chấp nhận chính và phụ thuộc ảnh hưởng lớn |
| **Bắt đầu thực hiện** | Chọn hạng mục phù hợp ưu tiên và năng lực WIP hiện có |
| **Bị chặn** | Đánh dấu nguyên nhân, người có thể tháo gỡ và ngày cần xem lại |
| **Hoàn thành** | Đạt tiêu chuẩn chất lượng và điều kiện bàn giao đã thống nhất |
| **Sau bàn giao** | Có cách nhận phản hồi và cập nhật quyết định nếu cần |

Các chính sách trên là **ví dụ để nhóm tùy chỉnh**. “Ready” không phải artifact bắt buộc của Scrum; không nên biến nó thành cửa phê duyệt kéo dài nếu yêu cầu có thể được làm rõ nhanh trong quá trình phối hợp.

### Giới hạn WIP giúp ưu tiên có hiệu lực

Nếu nhóm mở đồng thời mười hạng mục nhưng chỉ có khả năng kiểm thử hai hạng mục, nhiều việc sẽ chờ lâu trước khi đến tay người dùng. **Giới hạn công việc đang làm (WIP)**, hỗ trợ hoàn tất những việc gần xong và tháo gỡ nút thắt thường giúp dòng chảy rõ hơn.

Một backlog được sắp thứ tự đẹp vẫn kém hiệu quả nếu mọi người liên tục bỏ việc đang làm để chạy theo đề xuất mới. Quy tắc WIP làm lộ **chi phí của việc chen ngang** và thúc đẩy nhóm thống nhất đánh đổi.

## 10. Xử lý yêu cầu khẩn cấp mà vẫn minh bạch

Không phải mọi việc đều có thể đợi vòng refinement định kỳ. Ví dụ: lỗi làm mất dữ liệu học viên, sự cố không đăng nhập được trên diện rộng hoặc lỗ hổng bảo mật đã được xác nhận có thể đòi hỏi phản ứng theo cơ chế khẩn cấp.

### Phân biệt “được gọi là gấp” với “có ảnh hưởng khẩn cấp”

| Tình huống | Cách nhìn nhận phù hợp |
| --- | --- |
| “Lãnh đạo cần bản demo chiều mai” | Có hạn thời gian; cần đánh giá phạm vi và công việc bị trì hoãn |
| “Học viên đang mất tiến độ và không khôi phục được” | Có khả năng gây tổn hại dữ liệu/nghiệp vụ; cần xác minh và xử lý sớm |
| “Tính năng đối thủ vừa ra mắt” | Có thể là tín hiệu thị trường; cần đánh giá giá trị và bằng chứng |
| “Có lỗ hổng cho phép xem dữ liệu học viên khác” | Rủi ro bảo mật nghiêm trọng; kích hoạt xử lý theo quy trình sự cố và thẩm quyền phù hợp |
| “Ý tưởng mới được nhắc lại nhiều lần” | Tần suất yêu cầu là thông tin, không tự chứng minh giá trị hoặc độ khẩn cấp |

### Luồng khẩn cấp gợi ý

1. **Tiếp nhận và xác minh ảnh hưởng.** Ai bị ảnh hưởng? Có bằng chứng gì? Có nguy cơ an toàn, dữ liệu hoặc dịch vụ không?
2. **Kích hoạt người chịu trách nhiệm xử lý.** Dùng quy trình sự cố phù hợp; không chờ một cuộc họp backlog thường kỳ nếu cần giảm tác động ngay.
3. **Hiển thị công việc và năng lực được chuyển hướng.** Ghi sự cố hoặc PBI liên quan vào nguồn quản lý và liên kết nhật ký sự cố; minh bạch hạng mục nào sẽ chậm.
4. **Khắc phục và kiểm chứng.** Cần đáp ứng các yêu cầu chất lượng và giám sát phù hợp trước khi khẳng định đã giải quyết.
5. **Học hỏi sau sự cố.** Ghi nguyên nhân, biện pháp phòng ngừa, backlog item cần làm và mức ưu tiên mới.

Khi áp dụng Scrum, trách nhiệm của Product Owner, Developers và các quy tắc xử lý rủi ro của tổ chức vẫn có hiệu lực. Không phải mọi thao tác khắc phục tức thời đều phải đợi Product Owner nhập ticket trước khi nhóm bảo vệ hệ thống; tuy nhiên **công việc và ảnh hưởng đến kế hoạch phải được ghi nhận minh bạch** ngay khi có thể.

### Minh bạch cả quyết định “không làm”

Một yêu cầu có thể hợp lý nhưng chưa đáng đầu tư. Phản hồi tốt nên nói rõ:

> “Đề xuất gợi ý khóa học bằng AI đã được ghi nhận. Hiện nhóm ưu tiên khắc phục lỗi mất tiến độ và đo tỷ lệ hoàn thành bài đầu tiên vì hai vấn đề này gắn trực tiếp với Product Goal. Chúng tôi giữ liên kết đến đề xuất để xem lại khi có thêm bằng chứng về nhu cầu gợi ý.”

Đây là một **mẫu phản hồi minh họa**, không phải cam kết thời hạn. Nó giúp người đề xuất hiểu quyết định và gửi thêm bằng chứng nếu có.

## 11. Khi nhiều đội phát triển cùng một sản phẩm

Trong Scrum, nếu nhiều Scrum Team cùng làm việc trên **một sản phẩm**, họ cần chia sẻ **Product Goal, Product Backlog và Product Owner**. Tạo Product Backlog riêng độc lập cho mỗi đội với quyền ưu tiên mâu thuẫn có thể làm các đội tối ưu cục bộ và bỏ lỡ kết quả chung.

Những đội khác nhau vẫn có thể có cách hiển thị công việc, kế hoạch Sprint và kỹ thuật phối hợp riêng. Điều quan trọng là:

- Nhìn được **cùng mục tiêu sản phẩm** và thứ tự ưu tiên tổng thể.
- Có thể phát hiện **phụ thuộc giữa các đội** trước khi hứa thời hạn hoặc chia lát cắt.
- Cùng thống nhất **định nghĩa chất lượng của Increment** theo yêu cầu tổ chức và sản phẩm.
- Biết ai chịu trách nhiệm khi có xung đột ưu tiên hoặc phạm vi.
- Tránh một PBI được nhiều đội làm trùng hoặc bị bỏ qua vì ai cũng nghĩ đội khác sở hữu.

Nếu tổ chức có nhiều sản phẩm độc lập, **mỗi sản phẩm có thể có backlog riêng**, miễn ranh giới sản phẩm và quyền quyết định rõ ràng. “Một nguồn công việc” cần được hiểu **theo phạm vi sản phẩm/nhóm phù hợp**, không có nghĩa toàn công ty phải gộp mọi việc vào một backlog khổng lồ.

## 12. Đo mức minh bạch và hiệu quả của luồng ưu tiên

Nên đánh giá bằng **khả năng quyết định, thời gian nhận phản hồi và kết quả người dùng**, thay vì số lượng ticket được tạo.

| Chỉ số / tín hiệu | Câu hỏi giúp trả lời | Giới hạn |
| --- | --- | --- |
| **Thời gian từ tiếp nhận đến quyết định** | Đề xuất có bị bỏ quên hoặc chờ quá lâu không? | Quyết định nhanh nhưng thiếu bằng chứng vẫn có thể sai |
| **Số hạng mục trùng lặp / không rõ đầu mối** | Nguồn công việc đã được đồng bộ và ghi rõ trách nhiệm chưa? | Số trùng giảm có thể do người dùng ngại gửi phản hồi |
| **WIP và số việc bị chặn** | Nhóm có mở quá nhiều việc hoặc bị tắc ở một bước không? | Ít WIP không tự chứng minh nhiều giá trị |
| **Cycle time** | Hạng mục mất bao lâu từ lúc bắt đầu làm đến khi hoàn thành theo quy ước? | Giảm bằng cách bỏ kiểm thử không phải cải tiến |
| **Lead time** | Hạng mục mất bao lâu từ mốc tiếp nhận quy định đến khi được bàn giao? | Cần thống nhất mốc, vì có thể bao gồm thời gian chờ backlog |
| **Tần suất chen ngang và ảnh hưởng** | Việc khẩn cấp làm thay đổi công việc đang làm ra sao? | Không nên coi mọi việc khẩn cấp là sai; cần xem tác động thật |
| **Time to feedback / learning** | Bao lâu mới có bằng chứng để điều chỉnh quyết định sản phẩm? | Có bản phát hành không đồng nghĩa đã học đủ |
| **Outcome và chỉ số bảo vệ** | Người dùng có đạt mục tiêu tốt hơn mà không tăng lỗi, rủi ro không? | Cần thiết kế phép đo có bối cảnh, tránh quy kết vội |

### Ví dụ tìm nút thắt bằng dữ liệu

Giả sử nhóm đo một số hạng mục đã hoàn tất và thấy mô hình thời gian điển hình:

| Bước | Thời gian minh họa |
| --- | ---: |
| Chờ làm rõ sau khi được ưu tiên | 3 ngày |
| Phát triển | 2 ngày |
| Chờ review và kiểm thử | 4 ngày |
| Triển khai | 1 ngày |
| **Tổng tuần tự** | **10 ngày** |

Nếu chỉ yêu cầu Developers viết mã nhanh hơn 20%, mức tiết kiệm lý thuyết cho 2 ngày phát triển chỉ là **0,4 ngày**, trong khi 7 ngày nằm ở hai khoảng chờ. Cách cải tiến hợp lý hơn có thể là **làm rõ hạng mục sớm hơn, giới hạn WIP, hỗ trợ review và tự động hóa kiểm tra phù hợp**, rồi đo xu hướng qua nhiều hạng mục.

Các số này chỉ minh họa số học; dữ liệu thật có thể chồng lấn bước, có ngày nghỉ, phát sinh lỗi và độ biến động lớn. Cần đo bằng quy ước ổn định, nhìn phân phối và tác động tới chất lượng.

## 13. Những phản mẫu cần tránh

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Mỗi phòng ban có một backlog “ưu tiên số một” | Developers nhận chỉ đạo mâu thuẫn | Tạo một nguồn thứ tự có thẩm quyền theo sản phẩm |
| Mọi ý tưởng tự động thành việc đã cam kết | Backlog phình lớn, kỳ vọng sai | Tách ghi nhận, đánh giá, ưu tiên và cam kết |
| Ưu tiên dựa trên chức danh người gửi | Bỏ qua bằng chứng và Product Goal | Minh bạch tiêu chí, quyền quyết định và đánh đổi |
| PO là nút cổ chai cho mọi câu hỏi nhỏ | Nhiều việc chờ dù thông tin có thể được chia sẻ | Trao quyền làm rõ phù hợp, PO vẫn giữ trách nhiệm Product Backlog |
| Không ghi lý do hoãn hoặc từ chối | Người đề xuất gửi lại nhiều lần; giảm niềm tin | Ghi quyết định và điều kiện xem lại |
| Gom mọi đề xuất trùng thành một câu quá chung | Mất dữ liệu về đối tượng và mức ảnh hưởng | Liên kết báo cáo, giữ bằng chứng và bối cảnh |
| Backlog chứa toàn task kỹ thuật rời rạc | Không thấy dòng giá trị người dùng | Liên kết task vào lát cắt/PBI có mục tiêu |
| Mọi hạng mục đều là P0 | Không có thứ tự thật; nhóm làm quá nhiều | Đánh giá tác động, khẩn cấp, chi phí cơ hội |
| Dùng điểm số để thay mọi quyết định | Độ chính xác giả, bỏ qua rủi ro bắt buộc | Dùng điểm để thảo luận, ghi ngoại lệ và lý do |
| Chen việc qua tin nhắn riêng | Mất khả năng dự báo, công việc không hiện trên bảng | Đồng bộ việc ảnh hưởng năng lực vào nguồn chung |
| Đóng ticket ngay khi code xong | Người dùng chưa nhận giá trị, lỗi có thể chưa được phát hiện | Phân biệt Done theo DoD, bàn giao và đo outcome |
| Không điều chỉnh backlog sau khi học | Nhóm làm theo kế hoạch cũ dù bằng chứng đã thay đổi | Tổ chức vòng phản hồi và quyết định cập nhật |
| “Một nguồn” = một file chứa mọi thứ | Khó tra cứu, lộ thông tin nhạy cảm, cản phối hợp | Duy trì một bản ghi có thẩm quyền và liên kết nguồn chuyên biệt |

## 14. Bài thực hành: xử lý sáu đề xuất cho cùng một sản phẩm

**Bối cảnh:** Một đội phát triển nền tảng học trực tuyến có Product Goal: “Học viên mới có thể bắt đầu và hoàn thành bài học đầu tiên một cách đáng tin cậy trong tuần đầu”. Đội có năng lực hữu hạn và đang chuẩn bị chọn công việc ngắn hạn.

### Nhiệm vụ 1 — Phân loại đầu vào

Các đề xuất:

1. **Hỗ trợ học viên:** Có báo cáo mất tiến độ sau khi dùng mạng di động.
2. **Marketing:** Muốn thêm hoạt ảnh trang chủ trước chiến dịch tháng tới.
3. **Đội nội dung:** Muốn người mới được gợi ý đúng bài đầu.
4. **Bảo mật:** Có cảnh báo về quyền truy cập hồ sơ học viên cần xác minh.
5. **Kinh doanh:** Muốn có mã giảm giá theo từng nhóm khách hàng.
6. **Phân tích sản phẩm:** Muốn đo sự kiện hoàn thành bài học đầu.

Với mỗi đề xuất, hãy ghi:

- **Ai bị ảnh hưởng** và vấn đề gốc cần giải quyết?
- Đây là **bằng chứng đã có**, **giả định** hay **đề xuất giải pháp**?
- Có **rủi ro bắt buộc** hoặc thời hạn thực sự không?
- Nó đóng góp trực tiếp, gián tiếp hay chưa rõ cho Product Goal?
- **Cần hỏi ai** và **bước kiểm chứng nhỏ nhất** là gì?

### Nhiệm vụ 2 — Tạo bảng quyết định minh bạch

Một cách ghi nhận ban đầu:

| Đề xuất | Bước tiếp theo có căn cứ | Lý do |
| --- | --- | --- |
| Mất tiến độ | Tái hiện lỗi, đo ảnh hưởng và xử lý theo mức nghiêm trọng | Có nguy cơ làm người dùng mất kết quả học |
| Hoạt ảnh trang chủ | Ghi lại mục tiêu chiến dịch và bằng chứng kỳ vọng | Chưa chứng minh tác động tới việc hoàn thành bài |
| Gợi ý bài đầu | Phỏng vấn và quan sát một nhóm học viên mới; thử lát cắt nhỏ | Gắn Product Goal nhưng giải pháp còn cần kiểm chứng |
| Cảnh báo quyền truy cập | Kiểm tra khẩn cấp theo quy trình bảo mật; giảm tác động nếu xác thực | Rủi ro dữ liệu có thể vượt ưu tiên tính năng |
| Mã giảm giá | Đánh giá tác động doanh thu, thời điểm và chi phí cơ hội | Có thể hợp lý cho mục tiêu khác, nhưng cần so với mục tiêu hiện tại |
| Sự kiện đo hoàn thành | Làm rõ định nghĩa “hoàn thành”, triển khai cách đo đáng tin | Giúp nhóm biết những thay đổi có tạo outcome không |

Đây là **gợi ý về hành động**, chưa phải bảng xếp hạng chắc chắn. Nếu cảnh báo bảo mật được xác thực nghiêm trọng, phải xử lý theo thẩm quyền phù hợp. Nếu lỗi mất tiến độ chỉ xảy ra ở một phiên bản cũ không còn được dùng, mức ưu tiên có thể thay đổi.

### Nhiệm vụ 3 — Viết hai Product Backlog Item đủ rõ

**PBI A — Khôi phục tiến độ:**

> Là học viên đang học dở, tôi muốn khi quay lại bài có thể tiếp tục từ tiến độ đã được lưu thành công, để không phải học lại.

**Ví dụ chấp nhận:** Khi hệ thống xác nhận lưu tiến độ ở mốc A, tải lại trang hiển thị đúng mốc A; khi không lưu được do lỗi mạng, giao diện không thông báo sai là đã lưu.

**PBI B — Bắt đầu bài đầu tiên:**

> Là học viên mới, tôi muốn thấy đường dẫn rõ ràng đến bài khởi đầu phù hợp sau khi đăng ký, để không phải tìm kiếm trong toàn bộ danh mục.

**Ví dụ chấp nhận:** Với học viên thuộc nhóm đầu vào đã thống nhất, trang sau đăng ký hiển thị bài khởi đầu; nếu chưa có đủ dữ liệu để cá nhân hóa, hiển thị lựa chọn mặc định đã được Product Owner và chuyên gia nội dung thống nhất.

Hãy thảo luận **INVEST** cho hai story: phần nào còn phụ thuộc, cách giải quyết có thể thương lượng không, có kiểm chứng được không và lát cắt đầu tiên có đủ nhỏ không?

### Nhiệm vụ 4 — Diễn tập một yêu cầu chen ngang

Giữa Sprint, trưởng bộ phận kinh doanh gửi tin:

> “Bên tôi cần trang mã giảm giá hôm nay. Nhờ lập trình viên dừng việc lưu tiến độ và làm trước.”

Hãy viết phản hồi của nhóm theo các ý:

1. Ghi nhận nhu cầu và xác định hậu quả của việc không làm ngay.
2. Đưa yêu cầu qua **đầu mối ưu tiên** thay vì giao việc ngầm.
3. Nêu Sprint Goal hiện tại và ảnh hưởng nếu đổi phạm vi.
4. Thảo luận với Product Owner và Developers về cách xử lý thích hợp.
5. Ghi lại quyết định, công việc bị dời và thời điểm xem lại.

**Mẫu phản hồi tham khảo:**

> “Nhóm đã ghi nhận yêu cầu mã giảm giá và cần biết mục tiêu, hạn chót thực tế cùng tác động nếu lùi. Hiện Sprint đang tập trung vào khả năng học viên tiếp tục bài từ tiến độ đã lưu. Product Owner sẽ đánh giá yêu cầu với Developers để xác định phạm vi có thể xử lý và công việc phải đánh đổi; kết quả sẽ được cập nhật tại hạng mục chung để các bên cùng theo dõi.”

### Nhiệm vụ 5 — Chọn chỉ số theo dõi

Đề xuất ít nhất ba phép đo, trong đó:

- Một phép đo **độ minh bạch tiếp nhận** (ví dụ thời gian từ tiếp nhận đến quyết định).
- Một phép đo **dòng công việc** (ví dụ cycle time hoặc thời gian bị chặn).
- Một phép đo **giá trị sản phẩm** (ví dụ tỷ lệ học viên hoàn thành bài đầu trong bảy ngày, kèm tỷ lệ lỗi lưu tiến độ).

Hãy giải thích cách định nghĩa mẫu và cách tránh ngộ nhận từ từng phép đo. Không nên coi “đã xử lý 50 ticket” là bằng chứng duy nhất rằng sản phẩm tốt hơn.

## 15. Checklist vận hành nguồn công việc chung

Trước khi kết thúc một buổi xem xét backlog hoặc lập kế hoạch, nhóm có thể kiểm tra:

- [ ] Có **một bản ghi có thẩm quyền** về công việc và thứ tự theo phạm vi sản phẩm.
- [ ] Các kênh gửi đề xuất có **đầu mối tiếp nhận và liên kết tra cứu**.
- [ ] Đề xuất được phân biệt rõ với **việc đã được ưu tiên hoặc chọn thực hiện**.
- [ ] Product Goal hoặc mục tiêu tương đương được dùng để giải thích lựa chọn.
- [ ] Người có trách nhiệm quản lý thứ tự và các thẩm quyền liên quan được xác định.
- [ ] Những vấn đề trùng được liên kết, không làm mất bằng chứng về tác động.
- [ ] Các hạng mục sắp thực hiện đủ rõ về giá trị, rủi ro, phụ thuộc và tiêu chí chấp nhận.
- [ ] Công việc kỹ thuật, chất lượng và bảo mật được nhìn thấy khi cần thiết.
- [ ] Việc đang làm, việc bị chặn và yêu cầu chen ngang có trạng thái minh bạch.
- [ ] Người gửi nhận được **quyết định và lý do**, kể cả khi chưa làm.
- [ ] Kết quả bàn giao được kiểm chứng và phản hồi quay lại backlog.

Checklist này là công cụ tự rà soát. Nhóm có thể rút gọn hoặc điều chỉnh theo quy mô, nhưng cần giữ khả năng trả lời câu hỏi **“ai đang quyết định điều gì, dựa trên căn cứ nào, và công việc tiếp theo là gì?”**.

## 16. Câu hỏi ôn tập

1. “Một nguồn công việc” có nghĩa tất cả thông tin dự án phải nằm trong một file duy nhất không? Vì sao?
2. Trong Scrum, Product Backlog có vai trò gì và ai chịu trách nhiệm quản lý hiệu quả?
3. Vì sao người gửi đề xuất không mặc nhiên được quyết định thứ tự công việc?
4. Điểm khác nhau giữa yêu cầu đã tiếp nhận, Product Backlog Item đã được sắp thứ tự và công việc đã chọn cho Sprint là gì?
5. Nếu ba phòng ban gửi ba yêu cầu có cùng nhãn “khẩn cấp”, nhóm cần bằng chứng và tiêu chí nào để đánh giá?
6. Tại sao một sửa lỗi mất dữ liệu có thể đáng ưu tiên hơn tính năng giao diện mới, dù ít người nhìn thấy thay đổi?
7. Làm sao kết hợp các báo cáo trùng mà vẫn giữ thông tin về mức độ ảnh hưởng?
8. Nếu stakeholder yêu cầu đổi việc giữa Sprint, trách nhiệm của Product Owner và Developers được thực hiện như thế nào?
9. Trong Kanban, WIP và chính sách chuyển trạng thái giúp duy trì sự rõ ràng ra sao?
10. Với nhiều Scrum Team cùng làm một sản phẩm, những yếu tố nào phải được chia sẻ?
11. Vì sao điểm ưu tiên tính bằng công thức không thể thay thế mọi quyết định?
12. Chỉ số nào cho thấy minh bạch backlog đang cải thiện **việc học và tạo giá trị**, không chỉ tăng số ticket đã đóng?

**Ghi nhớ:** Khi nhiều bên cùng đề xuất, Agile cần **một đường tiếp nhận rõ và một nguồn công việc có thẩm quyền để nhìn thấy, sắp thứ tự và điều chỉnh quyết định**. Trong Scrum, Product Backlog tạo tính minh bạch cho công việc của Scrum Team và Product Owner chịu trách nhiệm quản lý hiệu quả. Cộng tác tốt không phải là nhận hết mọi yêu cầu; đó là **lắng nghe đủ rộng, đánh giá bằng giá trị và bằng chứng, nêu rõ chi phí cơ hội, bảo vệ dòng công việc và phản hồi quyết định cho người liên quan**. Khi kết quả sử dụng thay đổi hiểu biết, backlog cũng phải được thích ứng để nhóm tiếp tục hướng tới giá trị sản phẩm.
